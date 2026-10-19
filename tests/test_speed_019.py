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
