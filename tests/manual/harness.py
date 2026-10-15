"""Real dashboard + fake ComfyUI for end-to-end checks without GPU or models."""
import http.server, json, os, sqlite3, subprocess, sys, threading, time, urllib.error, urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / 'cay_studio_app'
# Ports are overridable so several checks (e.g. in parallel worktrees) can run at once:
# CAY_TEST_STUDIO_PORT (default 8787) and CAY_TEST_COMFY_PORT (default 8188).
PORT = int(os.environ.get('CAY_TEST_STUDIO_PORT', '8787'))
COMFY_PORT = int(os.environ.get('CAY_TEST_COMFY_PORT', '8188'))
BASE = f'http://127.0.0.1:{PORT}'
COMFY = {'running': [], 'pending': [], 'history': {}, 'calls': []}


class FakeComfy(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def reply(self, data, code=200):
        body = json.dumps(data).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path.startswith('/queue'): return self.reply({'queue_running': COMFY['running'], 'queue_pending': COMFY['pending']})
        if self.path.startswith('/history'):
            pid = self.path.split('/history/', 1)[1] if '/history/' in self.path else None
            return self.reply({pid: COMFY['history'][pid]} if pid and pid in COMFY['history'] else ({} if pid else COMFY['history']))
        self.reply({}, 404)
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0)); body = json.loads(self.rfile.read(length) or b'{}')
        COMFY['calls'].append((self.path, body)); self.reply({})


class Studio:
    def __init__(self, work, env_extra=None):
        work = Path(work); self.runtime = work / 'studio'; self.root = work / 'ablage'
        (self.runtime / 'config').mkdir(parents=True, exist_ok=True); self.root.mkdir(exist_ok=True)
        (self.runtime / 'config/ablage.json').write_text(json.dumps({'wsl_root': str(self.root), 'windows_root': 'D:\\Cay_Studio',
            'local_services': {'comfyui': f'http://127.0.0.1:{COMFY_PORT}', 'ollama': 'http://127.0.0.1:11434'}}))
        self.comfy = http.server.ThreadingHTTPServer(('127.0.0.1', COMFY_PORT), FakeComfy)
        self.url = BASE
        threading.Thread(target=self.comfy.serve_forever, daemon=True).start()
        env = {**os.environ, 'CAY_STUDIO_RUNTIME': str(self.runtime), 'CAY_STUDIO_PORT': str(PORT), **(env_extra or {})}
        self.server = subprocess.Popen([sys.executable, 'server.py'], cwd=APP, env=env, stdout=open(work / 'server.log', 'w'), stderr=subprocess.STDOUT)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.token = None
        for _ in range(80):
            try: self.token = json.load(self.opener.open(BASE + '/api/bootstrap', timeout=2))['csrf']; break
            except OSError: time.sleep(.5)
        self.db = sqlite3.connect(self.runtime / 'data/cay_studio.sqlite3')

    def call(self, path, body=None, method=None):
        request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                         headers={'Content-Type': 'application/json', 'X-Cay-Token': self.token}, method=method or ('POST' if body is not None else 'GET'))
        try:
            with self.opener.open(request, timeout=20) as r: return r.status, json.load(r)
        except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')

    def project(self, rid, state, doc_extra=None, idea_extra=None, paused=1):
        idea = {'idea': 'Kekse streiten', 'duration': 15, 'episodes': 1, 'quality': 'fast', 'fps': 25, 'characters': 'invent', 'lip_sync': 'audio',
                'participants': [], 'examples': [], **(idea_extra or {})}
        doc = {'id': rid, 'request_key': rid, 'title': 'Der letzte Keks', 'state': state, 'phase': '-', 'idea': idea,
               'plan': {'cast': [], 'style': 'x', 'mood': 'playful'}, 'episodes': [], 'lines': [], **(doc_extra or {})}
        self.db.execute('INSERT INTO factory_runs VALUES(?,?,?,?,?,?)', (rid, rid, state, json.dumps(doc), '2026-10-13', '2026-10-13'))
        self.db.execute('INSERT INTO factory_control VALUES(?,?)', (rid, paused)); self.db.commit()

    def close(self):
        self.server.terminate(); self.server.wait(20); self.comfy.shutdown()


class Report:
    def __init__(self): self.ok = True
    def check(self, label, condition):
        self.ok &= bool(condition); print(('OK   ' if condition else 'FEHL ') + label)
    def done(self):
        print('ERGEBNIS:', 'alles bestanden' if self.ok else 'FEHLER'); sys.exit(0 if self.ok else 1)
