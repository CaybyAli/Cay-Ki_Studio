"""End-to-end check of /abort-step with the real dashboard and a fake ComfyUI.

Run: venv/bin/python tests/manual/abort_step_check.py <empty work dir>
Needs free ports 8787 and 8188. No GPU, no models.
"""
import http.server, json, os, sqlite3, subprocess, sys, threading, time, urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / 'cay_studio_app'
work = Path(sys.argv[1]); runtime = work / 'studio'; root = work / 'ablage'
(runtime / 'config').mkdir(parents=True, exist_ok=True); root.mkdir(exist_ok=True)
(runtime / 'config/ablage.json').write_text(json.dumps({'wsl_root': str(root), 'windows_root': 'D:\\Cay_Studio',
    'local_services': {'comfyui': 'http://127.0.0.1:8188', 'ollama': 'http://127.0.0.1:11434'}}))
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


threading.Thread(target=http.server.ThreadingHTTPServer(('127.0.0.1', 8188), FakeComfy).serve_forever, daemon=True).start()
env = {**os.environ, 'CAY_STUDIO_RUNTIME': str(runtime)}
server = subprocess.Popen([sys.executable, 'server.py'], cwd=APP, env=env, stdout=open(work / 'server.log', 'w'), stderr=subprocess.STDOUT)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def call(path, body=None):
    request = urllib.request.Request('http://127.0.0.1:8787' + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type': 'application/json', 'X-Cay-Token': token}, method='POST' if body is not None else 'GET')
    try:
        with opener.open(request, timeout=20) as r: return r.status, json.load(r)
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')


token = None
for _ in range(60):
    try: token = json.load(opener.open('http://127.0.0.1:8787/api/bootstrap', timeout=2))['csrf']; break
    except OSError: time.sleep(.5)
db = sqlite3.connect(runtime / 'data/cay_studio.sqlite3')


def project(rid, state, extra, step_status, pid):
    doc = {'id': rid, 'request_key': rid, 'title': 'Der letzte Keks', 'state': state, 'phase': 'Animation',
           'idea': {'idea': 'Kekse streiten', 'duration': 15, 'episodes': 1, 'quality': 'high', 'fps': 30, 'characters': 'invent', 'lip_sync': 'audio',
                    'participants': [], 'examples': []}, 'plan': {'cast': [], 'style': 'x', 'mood': 'playful'}, 'episodes': [], 'lines': [], **extra}
    db.execute('INSERT INTO factory_runs VALUES(?,?,?,?,?,?)', (rid, rid, state, json.dumps(doc), '2026-10-12', '2026-10-12'))
    db.execute('INSERT INTO factory_control VALUES(?,1)', (rid,))   # paused: the worker leaves it alone
    db.execute('INSERT INTO factory_steps(id,run_id,step_key,status,prompt_id,graph) VALUES(?,?,?,?,?,?)',
               ('step-' + rid[:4], rid, 'video09:0:0:0:abc', step_status, pid, '{}')); db.commit()


def steps(rid): return db.execute('SELECT status FROM factory_steps WHERE run_id=?', (rid,)).fetchall()


ok = True
def check(label, condition):
    global ok; ok &= bool(condition); print(('OK   ' if condition else 'FEHL ') + label)


try:
    # 1) Running and stalled: our prompt is interrupted, nobody else's.
    a = 'a' * 32; project(a, 'rendering', {}, 'submitted', 'pid-ours')
    COMFY['running'] = [[0, 'pid-ours', {}, {'cay_factory_step': 'step-aaaa'}, []]]; COMFY['pending'] = [[1, 'pid-other', {}, {}, []]]
    code, d = call(f'/api/factory/{a}/abort-step', {'fast': True})
    check('Abbruch angenommen (200)', code == 200)
    check('nur eigener Auftrag unterbrochen', COMFY['calls'] == [('/interrupt', {'prompt_id': 'pid-ours'})])
    check('Abschnitt verworfen', steps(a) == [])
    check('Qualität jetzt „Schnell“', d['idea']['quality'] == 'fast')
    check('läuft weiter (nicht pausiert)', db.execute('SELECT paused FROM factory_control WHERE id=?', (a,)).fetchone()[0] == 0)
    # 2) After a PC restart: blocked as uncertain, ComfyUI knows nothing → safe to drop.
    COMFY.update(running=[], pending=[], calls=[]); b = 'b' * 32
    project(b, 'blocked', {'resume_state': 'rendering', 'uncertain': True, 'error': 'Der Auftrag fehlt in ComfyUIs Warteschlange'}, 'submitted', 'pid-gone')
    code, d = call(f'/api/factory/{b}/abort-step', {'fast': False})
    check('Neustart-Fall: Abschnitt verworfen', code == 200 and steps(b) == [])
    check('Neustart-Fall: Zustand wieder „rendering“, nicht mehr unklar', d['state'] == 'rendering' and not d.get('uncertain'))
    check('Neustart-Fall: bleibt pausiert, Qualität unverändert', d['paused'] and d['idea']['quality'] == 'high')
    check('Neustart-Fall: ComfyUI nicht angefasst', COMFY['calls'] == [])
    # 3) Finished in ComfyUI meanwhile: never thrown away.
    c = 'c' * 32; project(c, 'rendering', {}, 'submitted', 'pid-done')
    COMFY['history'] = {'pid-done': {'prompt': [0, 'pid-done', {}, {'cay_factory_step': 'step-cccc'}, []], 'status': {'completed': True, 'status_str': 'success'}}}
    code, d = call(f'/api/factory/{c}/abort-step', {'fast': False})
    check('fertiger Abschnitt bleibt erhalten', code == 200 and steps(c) == [('submitted',)])
    # 4) Wrong state is refused.
    e = 'e' * 32; project(e, 'voice_review', {}, 'done', None)
    check('falscher Zustand abgelehnt (409)', call(f'/api/factory/{e}/abort-step', {'fast': True})[0] == 409)
finally:
    server.terminate(); server.wait(20)
print('ERGEBNIS:', 'alles bestanden' if ok else 'FEHLER'); sys.exit(0 if ok else 1)
