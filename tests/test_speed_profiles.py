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


def test_audio_guidance_only_in_first_step(monkeypatch):
    """Wrapper 088128b: at cfg 1 every audio-guided step runs a second transformer pass.
    0.17 guides step 1 of 4 only (8 -> 5 passes per window); in-flight projects keep their graph."""
    fast = talk_graph(monkeypatch, 'fast')['12']['inputs']
    assert fast['cay_audio_cfg_steps'] == 1
    assert 'cay_audio_cfg_steps' not in talk_graph(monkeypatch, 'high')['12']['inputs']
    legacy = render_studio.audio_graph({'CayWanVideoSampler': {}}, 'a.png', 'a.wav', 'p', 1, 6.87, 'fast', legacy_text=True)
    assert 'cay_audio_cfg_steps' not in legacy['12']['inputs'] and 'body keeps moving' in legacy['9']['inputs']['positive_prompt']


def test_cay_inputs_never_added_by_default():
    info = {'X': {'input': {'required': {'a': ('INT', {'default': 1})}, 'optional': {'cay_audio_cfg_steps': ('INT', {'default': 0}), 'b': ('INT', {'default': 2})}}}}
    assert render_studio.node(info, 'X')['inputs'] == {'a': 1, 'b': 2}
    assert render_studio.node(info, 'X', cay_audio_cfg_steps=1)['inputs']['cay_audio_cfg_steps'] == 1


def test_sampler_adapter_turns_scalar_audio_cfg_into_schedule(monkeypatch):
    import types
    import comfy_sampler_compat as compat

    class Upstream:
        @classmethod
        def INPUT_TYPES(cls): return {'required': {'steps': ('INT', {'default': 4}), 'multitalk_embeds': ('MULTITALKEMBEDS',)}, 'optional': {}}
        def process(self, **inputs): return inputs

    monkeypatch.setitem(sys.modules, 'nodes', types.SimpleNamespace(NODE_CLASS_MAPPINGS={'WanVideoSampler': Upstream}))
    assert 'cay_audio_cfg_steps' in compat.CayWanVideoSampler.INPUT_TYPES()['optional']
    shared = {'audio_cfg_scale': 2.0, 'audio': 'x'}
    out = compat.CayWanVideoSampler().process(cay_compatibility='17.0', steps=4, multitalk_embeds=shared, cay_audio_cfg_steps=1)
    assert out['multitalk_embeds']['audio_cfg_scale'] == [2.0, 1.0, 1.0, 1.0, 1.0] and shared['audio_cfg_scale'] == 2.0
    same = compat.CayWanVideoSampler().process(cay_compatibility='17.0', steps=4, multitalk_embeds=shared)
    assert same['multitalk_embeds'] is shared
