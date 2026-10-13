"""Speed profiles and segmentation. Graph values only: no GPU, no timing claim."""
import math
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path.insert(0, str(APP))

import render_studio  # noqa: E402
from studio_quality_policy import PROFILES, cadence, scene_segments, segments  # noqa: E402


def talk_graph(monkeypatch, quality):
    monkeypatch.setattr(render_studio, 'node', lambda info, kind, **kw: {'class_type': kind, 'inputs': kw})
    monkeypatch.setattr(render_studio, 'talk_models', lambda info, fast=False: {k: k for k in ('model', 'talk', 'wav', 'vae', 'text', 'vision', 'lora')})
    monkeypatch.setattr(render_studio, 'validate_graph', lambda info, graph: None)
    return render_studio.audio_graph({'CayWanVideoSampler': {}}, 'a.png', 'a.wav', 'p', 1, 6.87, quality)


def test_lip_sync_profiles(monkeypatch):
    draft, standard, high = (talk_graph(monkeypatch, q) for q in ('draft', 'fast', 'high'))
    assert (draft['11']['inputs']['width'], draft['11']['inputs']['height']) == (480, 832)
    assert (standard['11']['inputs']['width'], standard['11']['inputs']['height']) == (576, 1024)
    assert draft['12']['inputs']['steps'] == standard['12']['inputs']['steps'] == 4 and high['12']['inputs']['steps'] == 40
    assert '16' in draft and '16' in standard and '16' not in high      # 4-step distill weights


def test_motion_profiles_match_talking_shots():
    assert (PROFILES['draft']['width'], PROFILES['draft']['height']) == (480, 832)
    assert (PROFILES['fast']['width'], PROFILES['fast']['height']) == (576, 1024)


def test_no_interpolation_for_native_25_fps():
    assert cadence(25, True, 25.0) == 'fps=25'               # talking clips: untouched
    assert cadence(25, True, 16.0).startswith('tpad=')        # silent motion clips: smoothed


def windows(seconds):
    """InfiniteTalk computes full 81-frame windows that overlap by 9 frames (ComfyUI log: indices 72-153)."""
    frames = 4 * math.ceil(seconds * 25 / 4) + 1
    return 1 if frames <= 81 else 1 + math.ceil((frames - 81) / 72)


def test_one_prompt_per_talking_scene_saves_windows():
    keks = [3.97, 6.87, 4.4]                                   # measured scene lengths of Cay's 15 s film
    old = sum(windows(s) for scene in keks for s in segments(scene, 25))
    new = sum(windows(s) for scene in keks for s in scene_segments(scene, 25, True))
    assert (old, new) == (8, 7)
    assert scene_segments(6.87, 25, False) == segments(6.87, 25)     # motion model limit stays 5 s
    assert len(scene_segments(20, 25, True)) == 2
