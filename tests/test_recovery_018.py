"""Recovery after a crash or restart: the studio keeps going on its own or with one honest click.
Real factory code on a temporary database; ComfyUI and Ollama are faked (tests/studio_fakes.py)."""
import asyncio
import sqlite3

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


DISK_FULL = 'database or disk is full'


def fast_sleep(monkeypatch):
    real = asyncio.sleep
    monkeypatch.setattr(asyncio, 'sleep', lambda s, *a, **kw: real(min(s, .02), *a, **kw))
    return real


def test_factory_worker_survives_a_full_disk(tmp_path, monkeypatch):
    """The disk fills for a moment while the worker saves a phase: production goes on once space is free."""
    f = factory(tmp_path, monkeypatch); rid = '2' * 32; real = fast_sleep(monkeypatch); disk = {'full': True}
    project(f, rid, 'pictures', {'episodes': [{'title': 'K', 'scenes': []}], 'cast_refs': {}})
    f.services.down = True                                                            # ComfyUI restarting: the worker waits
    write = f.g['execute']

    def execute(sql, args=()):
        if disk['full'] and sql.lstrip().upper().startswith(('UPDATE', 'INSERT')): raise sqlite3.OperationalError(DISK_FULL)
        return write(sql, args)

    def record(kind, detail):
        if disk['full']: raise sqlite3.OperationalError(DISK_FULL)
    f.g.update(execute=execute, record=record)

    async def run():
        worker = asyncio.create_task(f.worker())
        await real(.3); disk['full'] = False; await real(.3)
        alive = not worker.done(); f.g['STOPPING'] = True
        await asyncio.wait_for(worker, 5)
        return alive
    assert asyncio.run(run())
    assert f.get(rid)['phase'].startswith('Wartet auf ComfyUI')                       # saved again after the disk was freed


def test_post_worker_survives_a_failed_status_write(monkeypatch):
    """Mixing finished but its status could not be written: the job is queued again, mixing and export go on."""
    from factory_post import PostProduction
    real = fast_sleep(monkeypatch)
    row = {'id': 'p1', 'run_id': 'r1', 'kind': 'mix', 'episode': 0, 'generation': 0, 'spec': '{}', 'status': 'queued'}

    class Resources:
        options = {'workers': 1}
        async def cpu(self, run, label, job): post.runs += 1; return {'episode': 0, 'file': 'mix.wav', 'sha256': 'x', 'seconds': 15}

    class Post(PostProduction):
        def __init__(self):
            self.g = {'STOPPING': False, 'MAINTENANCE': False, 'resources': Resources(), 'record': lambda *a: None}
            self.post_tasks = {}; self.status = 'running'; self.full = True; self.runs = 0
        def get(self, rid): return {'id': rid}
        def rows(self, sql, args=()): return [row] if self.status == 'queued' else []
        def sql(self, sql, args=()):
            if self.full: raise sqlite3.OperationalError(DISK_FULL)
            new = sql.split("status='", 1)[1].split("'", 1)[0]
            need = sql.split("AND status='", 1)[1].split("'", 1)[0] if 'AND status=' in sql else None
            if need is None or self.status == need: self.status = new

    post = Post()                                                                    # taken by the worker, then the disk filled

    async def run():
        post.post_tasks['p1'] = asyncio.create_task(post.post_execute(row))
        worker = asyncio.create_task(post.post_worker())
        await real(.3); post.full = False; await real(.5)
        alive = not worker.done(); post.g['STOPPING'] = True
        await asyncio.wait_for(worker, 5)
        return alive
    assert asyncio.run(run())
    assert post.status == 'done' and post.runs == 2


def planning(tmp_path, monkeypatch, chat):
    """A new film in planning; every /api/chat call goes to `chat`. The worker runs ~0.6 s."""
    f = factory(tmp_path, monkeypatch); rid = '3' * 32; real = fast_sleep(monkeypatch)
    f.services.chat = chat; f.release_planner = lambda: real(0)
    project(f, rid, 'planning', {'preflight': {'checks': []}},
            {'idea': 'Lena und Tom streiten um den letzten Keks. Lena: Der gehört mir! Tom: Nein, mir!'})
    f.sql("UPDATE factory_runs SET document=json_remove(json_remove(document,'$.plan'),'$.source') WHERE id=?", (rid,))

    async def run():
        worker = asyncio.create_task(f.worker())
        await real(.6); f.g['STOPPING'] = True
        await asyncio.wait_for(worker, 5)
    asyncio.run(run())
    return f.get(rid), sum(1 for c in f.services.calls if c[0] == '/api/chat')


def test_ollama_drop_during_planning_waits_and_tries_again(tmp_path, monkeypatch):
    """Ollama restarts mid-answer: the project is not blocked with an English error, it waits and retries."""
    import httpx

    def drop(request, body): raise httpx.RemoteProtocolError('Server disconnected without sending a response.', request=request)
    d, calls = planning(tmp_path, monkeypatch, drop)
    assert d['state'] == 'planning' and not d.get('error') and calls >= 2
    assert d['phase'].startswith('Verbindung zu Ollama unterbrochen.')


def test_ollama_timeout_blocks_with_a_german_cause(tmp_path, monkeypatch):
    import httpx

    def silent(request, body): raise httpx.ReadTimeout('', request=request)    # str() is empty, as in httpx
    d, calls = planning(tmp_path, monkeypatch, silent)
    assert d['state'] == 'blocked' and d['resume_state'] == 'planning' and calls == 1
    assert d['error'].startswith('Das Sprachmodell hat zu lange nicht geantwortet.') and '„Planung fortsetzen“' in d['error']


def test_remix_worker_survives_a_full_disk(monkeypatch):
    from factory import Wait
    from remix import Remix
    real = fast_sleep(monkeypatch)

    class Fake:
        worker = Remix.worker
        def __init__(self):
            self.g = {'STOPPING': False, 'MAINTENANCE': False, 'GPU_LOCK': asyncio.Lock(), 'record': self.record}
            self.full = True; self.phases = []; self.busy = None
        def record(self, *a):
            if self.full: raise sqlite3.OperationalError(DISK_FULL)
        def rows(self, sql, args=()): return [{'id': 'r1'}]
        def get(self, rid): return {'id': rid, 'state': 'tracking'}
        def ready(self): return True
        async def prepare(self, d): raise Wait('Wartet auf ComfyUI.')
        async def release_planner(self): pass
        def save(self, d):
            if self.full: raise sqlite3.OperationalError(DISK_FULL)
            self.phases.append(d['phase'])

    fake = Fake()

    async def run():
        worker = asyncio.create_task(fake.worker())
        await real(.3); fake.full = False; await real(.3)
        alive = not worker.done(); fake.g['STOPPING'] = True
        await asyncio.wait_for(worker, 5)
        return alive
    assert asyncio.run(run()) and fake.phases[-1] == 'Wartet auf ComfyUI.'
