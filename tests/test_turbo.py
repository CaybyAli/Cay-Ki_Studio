"""Turbo is used only when proven, after a ComfyUI restart, and switches itself off on failure."""
import asyncio
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path.insert(0, str(APP))

import render_studio  # noqa: E402
import turbo  # noqa: E402

INFO = {'WanVideoModelLoader': {'input': {'required': {'attention_mode': [['sdpa', 'flash_attn_2', 'sageattn']]}}}}


def runtime_with_comfy(tmp_path, pid=None):
    (tmp_path / 'logs').mkdir(exist_ok=True)
    (tmp_path / 'logs/comfyui_prozess.json').write_text(json.dumps({'pid': pid or os.getpid(), 'args': []}))
    return tmp_path


def test_turbo_states_and_attention(tmp_path):
    rt = runtime_with_comfy(tmp_path)
    assert turbo.state(rt)['state'] == 'missing' and turbo.attention(rt, INFO) == 'sdpa'
    turbo.write(rt, {'installed': time.time() + 60})                  # installed after ComfyUI started
    assert turbo.state(rt)['state'] == 'restart' and turbo.attention(rt, INFO) == 'sdpa'
    turbo.write(rt, {'installed': turbo.comfy_started(rt) - 60})       # ComfyUI started after installation
    assert turbo.state(rt)['state'] == 'active' and turbo.attention(rt, INFO) == 'sageattn'
    without = {'WanVideoModelLoader': {'input': {'required': {'attention_mode': [['sdpa']]}}}}
    assert turbo.attention(rt, without) == 'sdpa'                      # wrapper does not offer it
    turbo.disable(rt, 'Abschnitt fehlgeschlagen')
    assert turbo.state(rt)['state'] == 'off' and turbo.attention(rt, INFO) == 'sdpa'


def fake_python(tmp_path, probe_ok=True):
    script = tmp_path / 'python'
    probe = '{"mean_abs_error": 0.001, "seconds": 0.4, "torch": "2.8"}' if probe_ok else ''
    script.write_text('#!/bin/sh\n'
                      'if [ "$1" = "-m" ]; then echo "Successfully installed sageattention-1.0.6"; exit 0; fi\n'
                      + (f"echo '{probe}'; exit 0\n" if probe_ok else 'echo "AssertionError: 0.4"; exit 1\n'))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_setup_writes_marker_only_after_a_good_probe(tmp_path):
    rt = runtime_with_comfy(tmp_path)
    probe = asyncio.run(turbo.setup(rt, fake_python(tmp_path), tmp_path / 'turbo.log'))
    assert probe['mean_abs_error'] < .02 and turbo.read(rt)['package'] == turbo.PACKAGE
    assert 'Successfully installed' in (tmp_path / 'turbo.log').read_text()
    bad = tmp_path / 'bad'; bad.mkdir(); rt2 = runtime_with_comfy(bad)
    with pytest.raises(RuntimeError, match='AssertionError'):
        asyncio.run(turbo.setup(rt2, fake_python(bad, probe_ok=False), bad / 'turbo.log'))
    assert turbo.state(rt2)['state'] == 'missing'


def test_lip_sync_graph_uses_requested_attention(monkeypatch):
    monkeypatch.setattr(render_studio, 'node', lambda info, kind, **kw: {'class_type': kind, 'inputs': kw})
    monkeypatch.setattr(render_studio, 'talk_models', lambda info, fast=False: {k: k for k in ('model', 'talk', 'wav', 'vae', 'text', 'vision', 'lora')})
    monkeypatch.setattr(render_studio, 'validate_graph', lambda info, graph: None)
    graph = render_studio.audio_graph({'CayWanVideoSampler': {'input': {'optional': {'cay_audio_cfg_steps': ('INT', {'default': 0})}}}}, 'a.png', 'a.wav', 'p', 1, 5, 'fast', attention='sageattn')
    assert graph['10']['inputs']['attention_mode'] == 'sageattn'
    assert render_studio.audio_graph({'CayWanVideoSampler': {'input': {'optional': {'cay_audio_cfg_steps': ('INT', {'default': 0})}}}}, 'a.png', 'a.wav', 'p', 1, 5, 'fast')['10']['inputs']['attention_mode'] == 'sdpa'
