"""0.19 speed (render_policy 19): lip-sync windows fitted to the shot, no idle GPU between jobs,
one scene image per scene under the autopilot. Projects without the pin keep their exact graphs,
keys, polling and image variants (the guard tests below make the new paths fail loudly there)."""
import asyncio
import copy
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'cay_studio_app'
sys.path.insert(0, str(APP))
sys.path.insert(0, str(ROOT / 'tests'))

import render_studio  # noqa: E402
from factory_timing import talk_windows  # noqa: E402
from test_compat_016 import fake_graphs  # noqa: E402


# --- 1. InfiniteTalk windows ----------------------------------------------------------------

PLAN = {1.4: (37, 1), 1.48: (37, 1), 2.16: (57, 1), 3.0: (77, 1), 3.2: (81, 1), 3.24: (81, 1), 3.28: (49, 2),
        4.0: (57, 2), 5.0: (69, 2), 6.08: (81, 2), 7.5: (69, 3), 8.96: (81, 3), 12.0: (69, 5), 15.0: (73, 6)}


@pytest.mark.parametrize('seconds', sorted(PLAN))
def test_window_plan_table(seconds):
    assert render_studio.talk_window_plan(seconds) == PLAN[seconds]


def test_window_plan_never_adds_windows_and_always_covers_the_cut():
    for frames in range(35, 15 * 25 + 1):                # every talking shot from 1.4 s to the 15 s prompt limit
        seconds = frames / 25
        window, count = render_studio.talk_window_plan(seconds)
        assert (window - 1) % 4 == 0 and render_studio.MIN_WINDOW <= window <= 81
        assert count <= talk_windows(seconds)            # never an extra window or transition
        # The wrapper may count one audio frame fewer (float rounding): the clip still holds every frame of the cut.
        for audio in (frames - 1, frames):
            out = render_studio.window_output(window, audio)
            assert out >= frames, (seconds, window, audio, out)
            used = 1 if window >= audio else 1 + math.ceil((audio - window) / (window - 9))
            assert used <= count
        assert render_studio.window_output(window, frames) <= render_studio.window_output(81, frames)


def test_window_output_follows_the_wrapper_loop():
    # multitalk_loop.py (088128b): first window, then window-9 new frames until the audio end is reached.
    assert render_studio.window_output(81, 37) == 81 and render_studio.window_output(81, 82) == 153
    assert render_studio.window_output(49, 85) == 89 and render_studio.window_output(57, 105) == 105


def talk_info(loaded=True):
    return {'CayWanVideoSampler': {'input': {'optional': {'cay_audio_cfg_steps': ('INT', {'default': 0})} if loaded else {}}}}


@pytest.mark.parametrize('quality', ['fast', 'balanced', 'high', 'draft'])
def test_default_graph_is_the_81_frame_graph(monkeypatch, quality):
    fake_graphs(monkeypatch)
    for seconds in (1.4, 3.24, 6.12, 14.96):
        old = render_studio.audio_graph(talk_info(), 'a.png', 'a.wav', 'p', 7, seconds, quality)
        assert old['11']['inputs']['frame_window_size'] == 81 and old['11']['inputs']['motion_frame'] == 9
        assert render_studio.audio_graph(talk_info(), 'a.png', 'a.wav', 'p', 7, seconds, quality, window=81) == old
        window = render_studio.talk_window_plan(seconds)[0]
        fitted = render_studio.audio_graph(talk_info(), 'a.png', 'a.wav', 'p', 7, seconds, quality, window=window)
        assert fitted['11']['inputs']['frame_window_size'] == window and fitted['11']['inputs']['motion_frame'] == 9
        # Only the window size differs: same audio frames, prompt, sampler and models.
        fitted['11']['inputs']['frame_window_size'] = 81
        assert fitted == old


def run_movies(monkeypatch, tmp_path, d, forbid_plan=False):
    """factory.Factory.movies() with the real audio_graph (fake ComfyUI schema) and everything else faked."""
    factory = pytest.importorskip('factory')
    import wan_text_encoder
    from test_cut_018 import Movies
    fake_graphs(monkeypatch)
    calls = []
    real = render_studio.audio_graph

    def audio_graph(*args, **kw):
        calls.append((args, kw)); return real(*args, **kw)
    monkeypatch.setattr(render_studio, 'audio_graph', audio_graph)
    if forbid_plan:
        def forbidden(seconds): raise AssertionError('fitted windows used without render_policy 19')
        monkeypatch.setattr(render_studio, 'talk_window_plan', forbidden)
    monkeypatch.setattr(render_studio, 'dialogue_window', lambda lines, start, duration, path: str(path))
    monkeypatch.setattr(wan_text_encoder, 'validate_selected', lambda comfy, clip: None)
    monkeypatch.setattr(factory, 'video_models', lambda info, comfy: {'fast_loras': True, 'clip': 'clip'})
    monkeypatch.setattr(factory, 'motion_graph', lambda image, prompt, seed, negative, models, duration, quality: {'motion': [prompt, duration]})
    monkeypatch.setattr(factory, 'file_hash', lambda p: 'h')
    monkeypatch.setattr(factory, 'ff', lambda args: None)
    monkeypatch.setattr(factory.turbo, 'attention', lambda runtime, info: 'sdpa')
    fake = Movies(tmp_path)
    fake.object_info = lambda: asyncio.sleep(0, talk_info())
    asyncio.run(factory.Factory.movies(fake, d))
    talk = [(k, g) for k, g in fake.renders if 'motion' not in g]
    return talk, calls


def movie(policy=None, prompt_policy=17):
    from test_cut_018 import movie_project
    d = movie_project(); d['prompt_policy'] = prompt_policy
    if policy is not None: d['render_policy'] = policy
    return d


def test_movies_without_the_pin_keep_81_frame_windows_and_keys(monkeypatch, tmp_path):
    old, old_calls = run_movies(monkeypatch, tmp_path, movie(), forbid_plan=True)
    assert [g['11']['inputs']['frame_window_size'] for _, g in old] == [81, 81]
    assert all('window' not in kw for _, kw in old_calls)                     # the argument stays out: same digest as before
    eighteen, _ = run_movies(monkeypatch, tmp_path, movie(18), forbid_plan=True)
    assert eighteen == old


def test_movies_with_the_pin_fit_each_window(monkeypatch, tmp_path):
    old, _ = run_movies(monkeypatch, tmp_path, movie())
    new, calls = run_movies(monkeypatch, tmp_path, movie(19))
    # Scene 1 talks 4.0 s (2 windows of 57 instead of 81), scene 4 talks 3.0 s (1 window of 77).
    assert [g['11']['inputs']['frame_window_size'] for _, g in new] == [57, 77]
    assert [kw.get('window') for _, kw in calls[1:]] == [57, 77]
    assert [k.split(':')[:4] for k, _ in new] == [k.split(':')[:4] for k, _ in old]
    assert all(a != b for (a, _), (b, _) in zip(new, old))                    # a new graph is a new render key
    for (_, a), (_, b) in zip(new, old):
        a = copy.deepcopy(a); a['11']['inputs']['frame_window_size'] = 81
        assert a == b


def test_projects_with_0_16_prompts_keep_81_frames_even_with_the_pin(monkeypatch, tmp_path):
    talk, calls = run_movies(monkeypatch, tmp_path, movie(19, prompt_policy=16), forbid_plan=True)
    assert [g['11']['inputs']['frame_window_size'] for _, g in talk] == [81, 81] and all('window' not in kw for _, kw in calls)


# --- 2. No idle GPU between jobs ------------------------------------------------------------

RID = 'f' * 32


def image_job(tmp_path, monkeypatch, policy):
    from studio_fakes import factory as studio, project
    tmp_path.mkdir(parents=True, exist_ok=True)
    f = studio(tmp_path, monkeypatch)
    project(f, RID, 'pictures', {'render_policy': policy} if policy else {})
    return f


def finish(f, pid, history=True):
    from test_episode_looks import png
    n, _, graph, extra, _ = next(row for row in f.services.pending if row[1] == pid)
    if not history: return
    f.services.pending = [row for row in f.services.pending if row[1] != pid]
    png(f.comfy / 'output' / (pid + '.png'), 'same picture')
    f.services.history[pid] = {'prompt': [n, pid, graph, extra, []], 'status': {'completed': True, 'status_str': 'success'},
                               'outputs': {'77': {'images': [{'filename': pid + '.png', 'subfolder': '', 'type': 'output'}]}}}


def render_once(f, messages, delay=.3):
    """render_step for one image; ComfyUI finishes after `delay` s and sends `messages` (kind, history written yet)."""
    graph = {'77': {'class_type': 'SaveImage', 'inputs': {'images': ['9', 0]}}, '9': {'class_type': 'EmptyImage', 'inputs': {}}}

    async def comfy():
        while not f.services.pending: await asyncio.sleep(.01)
        pid = f.services.pending[-1][1]
        await asyncio.sleep(delay)
        for kind, written in messages:
            finish(f, pid, written)
            f.progress.event({'type': kind, 'data': {'prompt_id': pid, **({'node': None} if kind == 'executing' else {})}})
            await asyncio.sleep(.05)

    async def main():
        started = asyncio.get_running_loop().time()
        step, _ = await asyncio.wait_for(asyncio.gather(f.render_step(f.get(RID), 'image:0:0:0:0', graph), comfy()), 10)
        return step, asyncio.get_running_loop().time() - started
    return asyncio.run(main())


def submitted(f):
    graph = f.services.prompts()[-1][1]['prompt']
    graph['77']['inputs'].pop('filename_prefix')
    return graph


def test_pinned_render_is_handed_back_when_comfyui_reports_the_end(tmp_path, monkeypatch):
    f = image_job(tmp_path / 'new', monkeypatch, 19)
    step, seconds = render_once(f, [('execution_success', False), ('executing', True)])
    # Success arrives a moment before ComfyUI writes its history: the studio looks again on the next message.
    assert step['status'] == 'done' and seconds < 1.2, seconds
    assert f.progress.waiting.keys() == {step['prompt_id']}
    monkeypatch.undo()                                     # the second fake ComfyUI gets its own client patch
    old = image_job(tmp_path / 'old', monkeypatch, None)

    def forbidden(pid, seconds): raise AssertionError('new polling without the pin')
    monkeypatch.setattr(old.progress, 'settle', forbidden)
    old_step, old_seconds = render_once(old, [('execution_success', False), ('executing', True)])
    assert old_seconds >= 1.9 and old.progress.waiting == {}                       # the plain 2 s poll, as before
    # Scheduling changes nothing that is rendered or kept.
    assert submitted(f) == submitted(old) and step['sha256'] == old_step['sha256'] and step['step_key'] == old_step['step_key']


def test_pinned_render_falls_back_to_the_poll_without_a_message(tmp_path, monkeypatch):
    f = image_job(tmp_path, monkeypatch, 19)
    step, seconds = render_once(f, [('progress', True)], delay=.1)     # socket silent about the end (disconnected)
    assert step['status'] == 'done' and 1.9 <= seconds < 4


def test_settle_only_wakes_for_the_watched_prompt():
    from factory_progress import RenderProgress

    class F:
        def rows(self, *a): return []

    async def main():
        progress = RenderProgress(F()); progress.watch('a')
        loop = asyncio.get_running_loop()
        loop.call_later(.05, progress.event, {'type': 'executing', 'data': {'prompt_id': 'b', 'node': None}})
        loop.call_later(.1, progress.event, {'type': 'executing', 'data': {'prompt_id': 'a', 'node': '12'}})
        loop.call_later(.3, progress.event, {'type': 'executing', 'data': {'prompt_id': 'a', 'node': None}})
        t = loop.time(); await progress.settle('a', 2); woke = loop.time() - t
        t = loop.time(); await progress.settle('unknown', .05); slept = loop.time() - t
        return woke, slept
    woke, slept = asyncio.run(main())
    assert .25 <= woke < 1 and slept >= .04


def test_a_prompt_finished_before_its_id_came_back_wakes_at_once():
    from factory_progress import RenderProgress

    class F:
        def rows(self, *a): return []

    async def main():
        progress = RenderProgress(F())
        progress.event({'type': 'execution_success', 'data': {'prompt_id': 'cached'}})   # all nodes cached: done at once
        progress.watch('cached')
        loop = asyncio.get_running_loop(); t = loop.time(); await progress.settle('cached', 2)
        return loop.time() - t
    assert asyncio.run(main()) < .5


# --- 3. One scene image under the autopilot ---------------------------------------------------

def stills_project(policy=None, autopilot=True, scenes=3):
    from test_shots_019 import picture_project, blocks_episode
    episode = blocks_episode(); episode['scenes'] = episode['scenes'][:scenes]
    d = picture_project(episode, **({'render_policy': policy} if policy else {}))
    d['idea']['autopilot'] = autopilot
    return d


def scene_keys(monkeypatch, d):
    from test_shots_019 import run_pictures
    return [c['key'] for c in run_pictures(monkeypatch, d) if c['key'].startswith('image:')]


def test_pinned_autopilot_draws_one_image_per_scene_old_projects_two(monkeypatch):
    assert scene_keys(monkeypatch, stills_project(19)) == ['image:0:0:0:0', 'image:0:1:0:0', 'image:0:2:0:0']
    two = [f'image:0:{si}:0:{v}' for si in range(3) for v in (0, 1)]
    assert scene_keys(monkeypatch, stills_project(18)) == two                 # render_policy 18: as before
    assert scene_keys(monkeypatch, stills_project(None)) == two               # no pin at all: as before
    assert scene_keys(monkeypatch, stills_project(19, autopilot=False)) == two  # Cay chooses: both images
    old = stills_project(None); scene_keys(monkeypatch, old)
    assert all('stills' not in s for s in old['episodes'][0]['scenes'])       # old documents stay unchanged


def test_unpinned_pictures_never_ask_for_the_still_rule(monkeypatch):
    import factory

    def forbidden(d, scene):
        if d.get('render_policy', 0) >= 19: raise AssertionError
        return 2
    monkeypatch.setattr(factory, 'still_count', forbidden)
    d = stills_project(None)
    assert len(scene_keys(monkeypatch, d)) == 6


def test_second_image_only_on_demand_and_the_first_stays(monkeypatch):
    import autopilot
    from factory_editor import active_variants, regenerate
    d = stills_project(19)
    first = scene_keys(monkeypatch, d)
    scenes = d['episodes'][0]['scenes']
    assert all(len(active_variants(s)) == 1 and s['stills'] == {'round': 0, 'count': 1} for s in scenes)
    # The autopilot takes the only image of every scene.
    trial = copy.deepcopy(d); trial['state'] = 'image_review'
    assert autopilot.Autopilot().auto_images(trial) and [s['selected'] for s in trial['episodes'][0]['scenes']] == [v['id'] for s in scenes for v in active_variants(s)]
    # Autopilot off afterwards: nothing is drawn that nobody asked for.
    d['idea']['autopilot'] = False
    assert scene_keys(monkeypatch, d) == []
    # 'Zweites Bild' for scene 2: exactly that image, scene 2 keeps its first one.
    assert autopilot.second_still(scenes[1]) and not autopilot.second_still(scenes[1])
    assert scene_keys(monkeypatch, d) == ['image:0:1:0:1']
    assert [v['key'] for v in active_variants(scenes[1])] == ['image:0:1:0:0', 'image:0:1:0:1']
    assert not autopilot.second_still(scenes[0] | {'stills': {'round': 0, 'count': 2}})
    # 'Neue Bilder' starts a new round, decided afresh: Cay chooses, so two new ones.
    regenerate(scenes[0], [0, 1])
    assert scene_keys(monkeypatch, d) == ['image:0:0:1:0', 'image:0:0:1:1'] and first[0] == 'image:0:0:0:0'


def test_second_still_endpoint(tmp_path, monkeypatch):
    from studio_fakes import factory as studio, project, client
    f = studio(tmp_path, monkeypatch)
    one = {'variants': [{'id': 'a' * 32, 'key': 'image:0:0:0:0'}], 'stills': {'round': 0, 'count': 1}, 'selected': None}
    two = {'variants': [{'id': 'a' * 32, 'key': 'image:0:1:0:0'}, {'id': 'b' * 32, 'key': 'image:0:1:0:1'}], 'selected': None}
    project(f, RID, 'image_review', {'render_policy': 19, 'episodes': [{'title': 'F', 'scenes': [one, two]}]})
    api = client(f)
    assert api.post(f'/api/factory/{RID}/second-still', json={'episode': 0, 'scene': 1}).status_code == 409
    assert api.post(f'/api/factory/{RID}/second-still', json={'episode': 0, 'scene': 5}).status_code == 404
    r = api.post(f'/api/factory/{RID}/second-still', json={'episode': 0, 'scene': 0})
    assert r.status_code == 200 and r.json()['state'] == 'pictures'
    assert f.get(RID)['episodes'][0]['scenes'][0]['stills'] == {'round': 0, 'count': 2}
    assert api.post(f'/api/factory/{RID}/second-still', json={'episode': 0, 'scene': 0}).status_code == 409   # not in the image choice any more


# --- 5. Diagnose texts --------------------------------------------------------------------------

def diagnose():
    import importlib.util
    spec = importlib.util.spec_from_file_location('cay_diagnose_speed', ROOT / 'Cay_Studio_Diagnose.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


BANNER = '\x1b[32m[INFO]\x1b[0m Using RAM pressure cache.\n\x1b[32m[INFO]\x1b[0m Prompt executed in 59.12 seconds\n'


def test_ram_pressure_is_not_the_cache_banner():
    diag = diagnose()
    # Cay's 0.18.2 report: banner in the log, swap full but 1.5 GB read back in since start -> 'ja' before, wrongly.
    verdict = diag.ram_pressure(BANNER * 50, None, int(1.5 * 1024 ** 3), 2 * 86400)
    assert verdict.startswith('nein') and 'Zwischenspeicher-Modus' in verdict
    assert diag.ram_pressure(BANNER, {'some': 12.0, 'full': 3.5}, 0, 100).startswith('ja')
    assert diag.ram_pressure(BANNER, {'some': .4, 'full': 0.}, 0, 100).startswith('nein')
    assert diag.ram_pressure(BANNER + "RuntimeError: [enforce fail at alloc_cpu.cpp:121] DefaultCPUAllocator: can't allocate memory\n").startswith('ja')
    assert diag.ram_pressure('torch.OutOfMemoryError: CUDA out of memory.').startswith('nein')     # graphics memory, not RAM
    assert diag.ram_pressure('', None, 4 * 1024 ** 3, 1000).startswith('ja')                     # 4 MB/s read back from swap


def talk_step(sid, seconds, window=81, sampler=129.7, text=6.3, cached_text=False):
    graph = {'6': {'class_type': 'MultiTalkWav2VecEmbeds', 'inputs': {'num_frames': 4 * math.ceil(seconds * 25 / 4) + 1}},
             '9': {'class_type': 'WanVideoTextEncodeCached', 'inputs': {}}, '10': {'class_type': 'WanVideoModelLoader', 'inputs': {}},
             '11': {'class_type': 'WanVideoImageToVideoMultiTalk', 'inputs': {'frame_window_size': window, 'motion_frame': 9}},
             '12': {'class_type': 'CayWanVideoSampler', 'inputs': {}}}
    nodes = {'9': {'seconds': .03 if cached_text else text}, '11': {'seconds': 6.}, '12': {'seconds': sampler}}
    if sid == 't0': nodes['10'] = {'seconds': 52.}                     # the wrapper's model loader runs once per block
    return json.dumps({'nodes': nodes, 'coverage': 'events'}), json.dumps(graph)


def motion_step():
    graph = {'2': {'class_type': 'UNETLoader', 'inputs': {}}, '11': {'class_type': 'KSamplerAdvanced', 'inputs': {}},
             '12': {'class_type': 'KSamplerAdvanced', 'inputs': {}}, '9': {'class_type': 'ModelSamplingSD3', 'inputs': {}}}
    return json.dumps({'nodes': {'11': {'seconds': 20.2}, '12': {'seconds': 21.5}, '9': {'seconds': .1}}, 'coverage': 'partial'}), json.dumps(graph)


def test_node_time_by_kind_real_loads_and_time_per_window():
    diag = diagnose()
    rows = [talk_step('t0', 1.5), talk_step('t1', 4.0), talk_step('t2', 2.0, cached_text=True), motion_step()]
    times, loads, windows = diag.node_report(rows)
    # Node '12' is the lip-sync sampler in one graph and the second motion half in the other: no longer summed.
    assert 'Lippen-Sampler mit Modell bereitstellen und allen Fenstern [CayWanVideoSampler] 6.5 min/3x' in times
    assert 'Bewegungs-Sampler (beide Hälften) mit Modell bereitstellen [KSamplerAdvanced] 0.7 min/2x' in times
    assert 'Knoten 12' not in times and '12:' not in times
    # Loads: the text model twice (once from its cache), the wrapper's model loader once; not every log line.
    assert '11-GB-Textmodell [WanVideoTextEncodeCached] 2x' in loads and '[WanVideoModelLoader] 1x' in loads
    assert 'UNETLoader' not in loads and '1 von 4 Aufträgen nur teilweise gemessen' in loads
    assert windows == 'Sprech-Rechenfenster laut Graph: 4, Fenstergröße 81 Bilder, Lippen-Sampler 1.62 min pro Fenster'
    fitted = diag.node_report([talk_step('t0', 1.5, 41), talk_step('t1', 4.0, 57)])[2]
    assert fitted.startswith('Sprech-Rechenfenster laut Graph: 3, Fenstergröße 41 bis 57 Bilder (an die Szene angepasst)')


def test_window_count_of_the_report_follows_the_wrapper():
    diag = diagnose()
    for seconds in (1.4, 3.24, 3.28, 6.08, 8.96, 12.0, 15.0):
        window, count = render_studio.talk_window_plan(seconds)
        graph = {'a': {'class_type': 'MultiTalkWav2VecEmbeds', 'inputs': {'num_frames': 4 * math.ceil(seconds * 25 / 4 - 1e-9) + 1}},
                 'b': {'class_type': 'WanVideoImageToVideoMultiTalk', 'inputs': {'frame_window_size': window}}}
        assert diag.windows_of(graph, seconds) == (window, count)
        old = {**graph, 'b': {'class_type': 'WanVideoImageToVideoMultiTalk', 'inputs': {'frame_window_size': 81}}}
        assert diag.windows_of(old, seconds)[1] == count and diag.windows_of(old)[1] == talk_windows(seconds)   # without seconds: as before
    # The prompt's seconds come from the shot as factory.movies splits it (a 20 s talking shot = 2 prompts of 10 s).
    d = {'idea': {'fps': 25}, 'render_segments': {'0:0:0': 'a', '0:0:1': 'b', '0:1:0': 'c'},
         'episodes': [{'scenes': [{'render_seconds': 20.04}, {'render_seconds': 3.24}]}]}
    assert diag.segment_seconds(d) == {'a': 10.04, 'b': 10.0, 'c': 3.24}
