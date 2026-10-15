"""Projects started before 0.17 must not be re-rendered or re-voiced.

Reference: tests/fixtures/v16_reference.json, made from the 0.16.1 sources (git
9fbc214) by running the same inputs through the old code. Lip-sync windows are
cached by graph digest and voices by file signature, so equal graphs and equal
file names mean the finished work of an old project is reused."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'cay_studio_app'
sys.path.insert(0, str(APP))
sys.path.insert(0, str(ROOT / 'tests'))

import render_studio  # noqa: E402
import voice_fakes as vf  # noqa: E402
from factory_audio import layout  # noqa: E402
from factory_timing import audio_layout_v16  # noqa: E402

REF = json.loads((ROOT / 'tests/fixtures/v16_reference.json').read_text())


def plain(value):
    return json.loads(json.dumps(value))


@pytest.mark.parametrize('case', REF['layouts'], ids=lambda c: f"min{c['input']['minimum']}")
def test_v16_layout_is_unchanged(case):
    for run in (audio_layout_v16, lambda e, l, m, f: layout(e, l, m, f, version=16)):
        episode, lines = copy.deepcopy(case['input']['episode']), copy.deepcopy(case['input']['lines'])
        report = run([episode], lines, case['input']['minimum'], 25)
        for r in report: assert r.pop('layout') == 16
        assert plain(report) == case['report']
        assert plain(episode['scenes']) == case['scenes'] and plain(lines) == case['lines']


def fake_graphs(monkeypatch):
    monkeypatch.setattr(render_studio, 'node', lambda info, kind, **kw: {'class_type': kind, 'inputs': kw})
    monkeypatch.setattr(render_studio, 'talk_models', lambda info, fast=False: {k: k for k in ('model', 'talk', 'wav', 'vae', 'text', 'vision', 'lora')})
    monkeypatch.setattr(render_studio, 'validate_graph', lambda info, graph: None)


@pytest.mark.parametrize('loaded', [False, True], ids=['before-restart', 'after-restart'])
def test_legacy_lip_sync_graph_is_unchanged(monkeypatch, loaded):
    fake_graphs(monkeypatch)
    info = {'CayWanVideoSampler': {'input': {'optional': {'cay_audio_cfg_steps': ('INT', {'default': 0})} if loaded else {}}}}
    for name, graph in REF['graphs'].items():
        quality, seconds = name.split(':')
        now = render_studio.audio_graph(info, 'a.png', 'a.wav', 'p', 7, float(seconds), quality, attention='sdpa', legacy_text=True)
        assert plain(now) == graph, name


def test_new_fast_graph_needs_restarted_comfyui(monkeypatch):
    fake_graphs(monkeypatch)
    old = {'CayWanVideoSampler': {'input': {'optional': {}}}}
    with pytest.raises(ValueError, match='neu starten'):
        render_studio.audio_graph(old, 'a.png', 'a.wav', 'p', 7, 6.08, 'fast')
    assert 'cay_audio_cfg_steps' not in render_studio.audio_graph(old, 'a.png', 'a.wav', 'p', 7, 6.08, 'high')['12']['inputs']


def test_sampler_version_stays(monkeypatch):
    import types
    import comfy_sampler_compat as compat

    class Upstream:
        @classmethod
        def INPUT_TYPES(cls): return {'required': {'steps': ('INT', {'default': 4})}, 'optional': {}}

    monkeypatch.setitem(sys.modules, 'nodes', types.SimpleNamespace(NODE_CLASS_MAPPINGS={'WanVideoSampler': Upstream}))
    required = compat.CayWanVideoSampler.INPUT_TYPES()['required']
    # Required inputs go into every graph; a new version string would re-render old windows.
    assert plain({k: v for k, v in required.items() if k.startswith('cay_')}) == REF['compat_required']


def test_v16_sampling_and_categories_are_unchanged():
    import speech_quality as sq
    for emotion, expected in REF['voice']['sampling'].items():
        assert sq.sampling(emotion, 16) == expected == sq.sampling_v16(emotion)
    for emotion, expected in REF['voice']['performance_key'].items():
        assert sq.performance_key_v16(emotion) == expected


def test_voice_policy_16_reuses_0161_voices_and_lines(monkeypatch, tmp_path):
    vf.install(monkeypatch)
    voice = vf.load(APP, 'factory_voice')
    names, profiles, design = vf.run_design(voice, tmp_path, policy=16)
    assert names == REF['voice']['design_files']
    assert plain(design) == REF['voice']['design_calls']
    speech = vf.load(APP, 'factory_speech')
    lines, clone = vf.run_speech(speech, tmp_path, profiles, policy=16)
    assert lines == REF['voice']['line_files']
    assert plain(clone) == REF['voice']['clone_calls']      # 0.7 / 0.9, no top_k, one take per line


def test_voice_policy_17_uses_new_voices(monkeypatch, tmp_path):
    vf.install(monkeypatch)
    names, profiles, design = vf.run_design(vf.load(APP, 'factory_voice'), tmp_path)
    assert names['Mr. Krabs']['base'] != REF['voice']['design_files']['Mr. Krabs']['base']
    assert set(names['Plankton']['moods']) == {'afraid', 'whisper'}
    lines, clone = vf.run_speech(vf.load(APP, 'factory_speech'), tmp_path, profiles)
    assert lines != REF['voice']['line_files']
    assert all(c[1]['temperature'] == .9 and c[1]['top_k'] == 50 for c in clone)
    assert len(clone) == 7                                   # two takes for each emotional line, one for 'Natürlich'


def test_failed_mood_falls_back_to_base_voice(monkeypatch, tmp_path, capsys):
    vf.install(monkeypatch)
    real = vf.Model.generate_voice_design

    def silent_when_afraid(self, **kw):
        waves, sr = real(self, **kw)
        return ([waves[0] * 0] if 'afraid' in kw['instruct'] else waves), sr

    monkeypatch.setattr(vf.Model, 'generate_voice_design', silent_when_afraid)
    names, profiles, _ = vf.run_design(vf.load(APP, 'factory_voice'), tmp_path)
    assert set(names['Plankton']['moods']) == {'whisper'} and 'Gefühlsprobe übersprungen' in capsys.readouterr().out
