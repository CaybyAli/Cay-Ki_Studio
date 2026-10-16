"""Recovery after a crash or restart: the studio keeps going on its own or with one honest click.
Real factory code on a temporary database; ComfyUI and Ollama are faked (tests/studio_fakes.py)."""
import asyncio

from studio_fakes import client, factory, project, step


def steps(f, rid):
    return {r['step_key']: (r['status'], r['prompt_id']) for r in f.rows('SELECT * FROM factory_steps WHERE run_id=?', (rid,))}


def test_resume_drops_only_jobs_comfyui_forgot(tmp_path, monkeypatch):
    """ComfyUI lost a scene image after a restart: „Fortsetzen“ must not loop back to blocked.
    A job that is still queued, running or finished in ComfyUI is never thrown away."""
    f = factory(tmp_path, monkeypatch); comfy = f.services; rid = 'a' * 32
    project(f, rid, 'blocked', {'resume_state': 'pictures', 'uncertain': True,
                                'error': 'Der Auftrag fehlt in ComfyUIs Warteschlange und Verlauf. Keine automatische Doppelproduktion.'})
    lost = step(f, rid, 'image:0:0:0:0', 'submitted', 'pid-before-restart')
    step(f, rid, 'image:0:0:0:1', 'submitting')                                      # handed over, then ComfyUI died
    queued = step(f, rid, 'image:0:1:0:0', 'submitted', 'pid-queued')
    running = step(f, rid, 'image:0:1:0:1', 'submitting')                             # no id stored, but ComfyUI knows it
    step(f, rid, 'cast:Lena', 'submitted', 'pid-finished')
    comfy.pending = [[1, 'pid-queued', {}, {'cay_factory_step': queued}, []]]
    comfy.running = [[0, 'pid-running', {}, {'cay_factory_step': running}, []]]
    comfy.history = {'pid-finished': {'prompt': [2, 'pid-finished', {}, {}, []], 'status': {'completed': True, 'status_str': 'success'}}}
    code = client(f).post(f'/api/factory/{rid}/resume').status_code
    d = f.get(rid)
    assert code == 200 and d['state'] == 'pictures' and not d.get('uncertain') and not d['paused']
    assert set(steps(f, rid)) == {'image:0:1:0:0', 'image:0:1:0:1', 'cast:Lena'}       # only the two lost jobs are gone
    assert comfy.calls == []                                                          # nothing deleted or stopped in ComfyUI
    # The worker now renders the lost image exactly once instead of polling the forgotten id again.
    comfy.running = comfy.pending = []

    def stop(): f.g['STOPPING'] = True                                                 # end right after the hand-over
    comfy.on_prompt = stop
    graph = {'77': {'class_type': 'SaveImage', 'inputs': {}}}
    try: asyncio.run(f.render(d, 'image:0:0:0:0', graph))
    except Exception as e: assert 'Studio wird beendet' in str(e)
    assert len(comfy.prompts()) == 1 and comfy.prompts()[0][1]['extra_data']['cay_factory_step'] != lost
    assert steps(f, rid)['image:0:0:0:0'][0] == 'submitted'


def test_resume_without_comfyui_changes_nothing(tmp_path, monkeypatch):
    f = factory(tmp_path, monkeypatch); rid = 'b' * 32
    project(f, rid, 'blocked', {'resume_state': 'rendering', 'uncertain': True, 'error': 'Der Auftrag braucht ungewöhnlich lange.'})
    step(f, rid, 'video09:0:0:0:abc', 'submitted', 'pid-running'); f.services.down = True
    r = client(f).post(f'/api/factory/{rid}/resume')
    assert r.status_code == 503 and 'ComfyUI antwortet gerade nicht' in r.json()['detail']
    assert f.get(rid)['state'] == 'blocked' and steps(f, rid) == {'video09:0:0:0:abc': ('submitted', 'pid-running')}


def test_resume_rechecks_a_long_running_section_without_restarting_it(tmp_path, monkeypatch):
    """4-hour timeout: the job is still running. „Fortsetzen“ waits for it again, it does not interrupt it."""
    f = factory(tmp_path, monkeypatch); rid = 'c' * 32
    project(f, rid, 'blocked', {'resume_state': 'rendering', 'uncertain': True, 'error': 'Der Auftrag braucht ungewöhnlich lange.'}, {'quality': 'high'})
    sid = step(f, rid, 'video09:0:0:0:abc', 'submitted', 'pid-long')
    f.services.running = [[0, 'pid-long', {}, {'cay_factory_step': sid}, []]]
    assert client(f).post(f'/api/factory/{rid}/resume').status_code == 200
    d = f.get(rid)
    assert d['state'] == 'rendering' and d['idea']['quality'] == 'high' and f.services.calls == []
    assert steps(f, rid) == {'video09:0:0:0:abc': ('submitted', 'pid-long')}


def test_abort_step_uses_the_same_proof(tmp_path, monkeypatch):
    """abort-step keeps its behaviour: own queued job deleted, own running job interrupted, finished kept."""
    f = factory(tmp_path, monkeypatch); comfy = f.services; rid = 'd' * 32
    project(f, rid, 'rendering', idea={'quality': 'high'})
    done = step(f, rid, 'video09:0:0:0:a', 'submitted', 'pid-done')
    waiting = step(f, rid, 'video09:0:0:1:b', 'submitted', 'pid-wait')
    busy = step(f, rid, 'video09:0:1:0:c', 'submitting')
    step(f, rid, 'image:0:0:0:0', 'submitted', 'pid-image')                          # no animation: untouched
    comfy.pending = [[1, 'pid-wait', {}, {'cay_factory_step': waiting}, []], [2, 'pid-other', {}, {}, []]]
    comfy.running = [[0, 'pid-busy', {}, {'cay_factory_step': busy}, []]]
    comfy.history = {'pid-done': {'prompt': [3, 'pid-done', {}, {'cay_factory_step': done}, []], 'status': {'completed': True}}}
    r = client(f).post(f'/api/factory/{rid}/abort-step', json={'fast': False})
    assert r.status_code == 200 and r.json()['idea']['quality'] == 'high'
    assert comfy.calls == [('/queue', {'delete': ['pid-wait']}), ('/interrupt', {'prompt_id': 'pid-busy'})]
    assert steps(f, rid) == {'video09:0:0:0:a': ('submitted', 'pid-done'), 'image:0:0:0:0': ('submitted', 'pid-image')}
