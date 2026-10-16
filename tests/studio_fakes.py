"""A real Factory on a temporary SQLite file with a fake ComfyUI and Ollama (httpx.MockTransport).
No server process, no GPU, no models: the factory's own code, routes and worker run unchanged."""
import asyncio
import json
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path.insert(0, str(APP))

COMFY_URL = 'http://comfy.test'
OLLAMA_URL = 'http://ollama.test'


class Services:
    """ComfyUI and Ollama as Cay's PC would answer them. 'chat' decides each /api/chat reply."""
    def __init__(self):
        self.running = []; self.pending = []; self.history = {}; self.calls = []; self.down = False
        self.chat = None; self.on_prompt = None

    def handler(self, request):
        path = request.url.path
        if self.down: raise httpx.ConnectError('All connection attempts failed', request=request)
        if request.method == 'GET':
            if path == '/queue': return httpx.Response(200, json={'queue_running': self.running, 'queue_pending': self.pending})
            if path.startswith('/history/'):
                pid = path.split('/history/', 1)[1]
                return httpx.Response(200, json={pid: self.history[pid]} if pid in self.history else {})
            if path == '/history': return httpx.Response(200, json=self.history)
            if path == '/api/ps': return httpx.Response(200, json={'models': []})
            return httpx.Response(404, json={})
        body = json.loads(request.content or b'{}'); self.calls.append((path, body))
        if path == '/api/chat' and self.chat: return self.chat(request, body)
        if path == '/prompt':
            pid = 'pid-new-%d' % len(self.calls)
            self.pending.append([len(self.calls), pid, body.get('prompt'), body.get('extra_data', {}), []])
            if self.on_prompt: self.on_prompt()
            return httpx.Response(200, json={'prompt_id': pid, 'number': 1, 'node_errors': {}})
        return httpx.Response(200, json={})

    def prompts(self): return [c for c in self.calls if c[0] == '/prompt']


async def get_json(client, url):           # same contract as server.get_json
    try:
        r = await client.get(url, timeout=3); r.raise_for_status(); value = r.json()
        return value if isinstance(value, dict) else None
    except (httpx.HTTPError, ValueError):
        return None


def factory(tmp_path, monkeypatch, services=None):
    """Factory wired like server.py, every httpx client of the studio talks to `services`."""
    from factory import Factory
    services = services or Services()
    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda *a, **kw: real(*a, **{**kw, 'transport': httpx.MockTransport(services.handler)}))
    db_path = tmp_path / 'studio.sqlite3'; events = []

    @contextmanager
    def conn():
        db = sqlite3.connect(db_path, timeout=15); db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def execute(sql, args=()):
        with conn() as db: db.execute(sql, args)

    def rows(sql, args=()):
        with conn() as db: return [dict(x) for x in db.execute(sql, args).fetchall()]

    root = (tmp_path / 'ablage').resolve(); (tmp_path / 'studio').mkdir(exist_ok=True); root.mkdir(exist_ok=True)
    g = {'RUNTIME': tmp_path / 'studio', 'ROOT': root, 'conn': conn, 'execute': execute, 'rows': rows,
         'allowed': lambda p: Path(p).resolve(), 'now': lambda: datetime.now(timezone.utc).isoformat(),
         'COMFY': COMFY_URL, 'OLLAMA': OLLAMA_URL, 'MODEL': 'planner', 'get_json': get_json,
         'record': lambda kind, detail: events.append((kind, detail)), 'events': events,
         'STOPPING': False, 'MAINTENANCE': False, 'GPU_LOCK': asyncio.Lock()}
    f = Factory(g); f.init(); f.services = services
    return f


def project(f, rid, state, extra=None, idea=None, paused=0):
    idea = {'idea': 'Kekse streiten', 'duration': 15, 'episodes': 1, 'quality': 'fast', 'fps': 25, 'characters': 'invent',
            'lip_sync': 'audio', 'participants': [], 'examples': [], **(idea or {})}
    doc = {'id': rid, 'request_key': rid, 'title': 'Der letzte Keks', 'state': state, 'phase': '-', 'idea': idea,
           'plan': {'cast': [], 'style': 'x', 'mood': 'playful'}, 'episodes': [], 'lines': [], **(extra or {})}
    f.sql('INSERT INTO factory_runs VALUES(?,?,?,?,?,?)', (rid, rid, state, json.dumps(doc), '2026-10-13', '2026-10-13'))
    f.sql('INSERT INTO factory_control VALUES(?,?)', (rid, paused))


def step(f, rid, key, status, pid=None, sid=None, graph='{}'):
    sid = sid or 'step-' + key.replace(':', '-')
    f.sql('INSERT INTO factory_steps(id,run_id,step_key,status,prompt_id,graph) VALUES(?,?,?,?,?,?)', (sid, rid, key, status, pid, graph))
    return sid


def client(f):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI(); f.routes(app)
    return TestClient(app)
