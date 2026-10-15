"""Runs factory_voice / factory_speech without GPU or models: fake torch, qwen_tts
and soundfile record every model call. Used to show that a project voiced before
0.17 keeps its cache signatures (same file names) and its 0.16 sampling."""
import importlib
import json
import sys
import types
import wave
from array import array
from pathlib import Path

import numpy as np

RATE = 24000


def take(text, seed=0):
    """Speech-like take long enough for finish_voice: ~0.45 s per word."""
    words = max(1, len(str(text).split()))
    t = np.arange(int(RATE * (words * .45 + .4))) / RATE
    syllable = np.maximum(0, np.sin(np.pi * 4 * t)) ** .6
    pitch = 160 * 2 ** (np.sin(2 * np.pi * (1.5 + seed % 3) * t) / 12)
    phase = 2 * np.pi * np.cumsum(pitch) / RATE
    return (.25 * syllable * sum(np.sin(k * phase) / k for k in range(1, 5))).astype(np.float32)


def write_wav(path, data, sr, subtype=None):
    pcm = array('h', (int(max(-32767, min(32767, round(float(x) * 32767)))) for x in np.asarray(data).reshape(-1)))
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm.tobytes())


def info(path):
    with wave.open(str(path)) as w:
        return types.SimpleNamespace(duration=w.getnframes() / w.getframerate())


class Model:
    calls = []

    @classmethod
    def from_pretrained(cls, *args, **kwargs): return cls()

    def generate_voice_design(self, **kw):
        Model.calls.append(('design', {k: v for k, v in kw.items()}))
        return [take(kw['text'], len(Model.calls))], RATE

    def create_voice_clone_prompt(self, **kw): return ('prompt', kw.get('ref_text'))

    def generate_voice_clone(self, **kw):
        Model.calls.append(('clone', {k: v for k, v in kw.items() if k != 'voice_clone_prompt'}))
        return [take(kw['text'], len(Model.calls))], RATE


def install(monkeypatch=None):
    Model.calls = []
    fakes = {'torch': types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: True), bfloat16='bf16', manual_seed=lambda s: None),
             'qwen_tts': types.SimpleNamespace(Qwen3TTSModel=Model),
             'soundfile': types.SimpleNamespace(write=write_wav, info=info)}
    for name, module in fakes.items():
        if monkeypatch: monkeypatch.setitem(sys.modules, name, module)
        else: sys.modules[name] = module


def base_dir(root):
    root = Path(root)
    for f in ['envs/studio-voices/bin/python', 'models/studio-voices/VoiceDesign/config.json',
              'models/studio-voices/Base/config.json', 'models/studio-voices/Base/bereit.json']:
        (root / f).parent.mkdir(parents=True, exist_ok=True); (root / f).write_text('{}')
    (root / 'models/studio-voices/Base/source.json').write_text(json.dumps({'repo': 'Qwen/Qwen3-TTS-12Hz-1.7B-Base', 'revision': 'fixed'}))
    return root


CAST = [{'name': 'Mr. Krabs', 'voice_preset': 'man', 'personality': 'geizig', 'voice_description': 'gravelly', 'original': 'Mr. Krabs'},
        {'name': 'Plankton', 'voice_preset': 'creature', 'personality': 'listig'}]
LINES = [{'key': f'E01_S01_T{i + 1:02}_abc', 'episode': 0, 'scene': 0, 'turn': i, 'speaker': s, 'text': t, 'text_de': t, 'emotion': e,
          'pause_after': .18, 'seed': 1000 + i}
         for i, (s, t, e) in enumerate([('Mr. Krabs', 'Wo ist mein Geld geblieben?', 'wütend'),
                                        ('Plankton', 'Ich weiß von nichts, ehrlich!', 'ängstlich'),
                                        ('Mr. Krabs', 'Dann such es eben mit mir.', 'Natürlich'),
                                        ('Plankton', 'Psst, hier liegt es ja!', 'flüsternd')])]


def run_design(module, root, policy=None):
    """Voice design for CAST; returns profile file names and the design calls."""
    root = base_dir(root); out = root / 'profile'
    job = {'run_id': 'run1', 'cast': CAST, 'lines': LINES, 'performances': True, 'look': 'cartoon', 'output': str(out)}
    if policy is not None: job['voice_policy'] = policy
    (root / 'job.json').write_text(json.dumps(job))
    module.generate(root, root / 'job.json')
    profiles = json.loads((out / 'Profile.json').read_text())
    names = {n: {'base': Path(p['file']).name, 'moods': {k: Path(v['file']).name for k, v in p.get('emotion_profiles', {}).items()}}
             for n, p in profiles.items()}
    return names, profiles, [c for c in Model.calls if c[0] == 'design']


def run_speech(module, root, profiles, policy=None):
    """Speak LINES with the designed profiles; returns line file names and clone calls."""
    root = Path(root); out = root / 'lines'
    cast = [{**p, 'voice_file': profiles[p['name']]['file'], 'voice_hash': profiles[p['name']]['sha256'],
             'voice_text': profiles[p['name']]['voice_text'], 'emotion_profiles': profiles[p['name']].get('emotion_profiles', {})} for p in CAST]
    job = {'cast': cast, 'lines': LINES, 'output': str(out)}
    if policy is not None: job['voice_policy'] = policy
    (root / 'speech.json').write_text(json.dumps(job))
    Model.calls = []
    module.generate(root, root / 'speech.json')
    result = json.loads((out / 'Ergebnis.json').read_text())['lines']
    return [Path(l['file']).name for l in result], [c for c in Model.calls if c[0] == 'clone']


def load(app_dir, name):
    """Fresh import of a module from app_dir (0.16.1 sources or the current app)."""
    for mod in [name, 'speech_quality']:
        sys.modules.pop(mod, None)
    sys.path.insert(0, str(app_dir))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(app_dir))
