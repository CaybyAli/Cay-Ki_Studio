"""End-to-end check of /abort-step with the real dashboard and a fake ComfyUI.

Run: venv/bin/python tests/manual/abort_step_check.py <empty work dir>
Needs free ports 8787 and 8188. No GPU, no models.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import COMFY, Studio, Report

studio = Studio(sys.argv[1]); r = Report(); db = studio.db; call = studio.call


def project(rid, state, extra, step_status, pid):
    studio.project(rid, state, extra, {'quality': 'high'})
    db.execute('INSERT INTO factory_steps(id,run_id,step_key,status,prompt_id,graph) VALUES(?,?,?,?,?,?)',
               ('step-' + rid[:4], rid, 'video09:0:0:0:abc', step_status, pid, '{}')); db.commit()


def steps(rid): return db.execute('SELECT status FROM factory_steps WHERE run_id=?', (rid,)).fetchall()
check = r.check

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
    studio.close()
r.done()
