"""A library voice keeps its emotional range: emotion takes are designed from its recipe."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))
sys.path.insert(0, str(ROOT / 'tests'))

import voice_fakes as vf  # noqa: E402


def job(root, cast, lines, policy=17):
    out = root / 'profile'
    (root / 'job.json').write_text(json.dumps({'run_id': 'run9', 'cast': cast, 'lines': lines, 'performances': True, 'look': 'clay',
                                               'voice_policy': policy, 'output': str(out)}))
    return out


def test_library_voice_gets_emotion_takes_from_its_recipe(monkeypatch, tmp_path):
    vf.install(monkeypatch)
    root = vf.base_dir(tmp_path)
    base = root / 'patrick.wav'; vf.write_wav(base, vf.take('Na endlich, komm rein'), vf.RATE)
    import hashlib
    sha = hashlib.sha256(base.read_bytes()).hexdigest()
    recipe = {'instruction': 'An adult man, resonant voice. German cartoon dubbing voice actor.', 'seed': 4242}
    cast = [{'name': 'Patrick', 'voice_file': str(base), 'voice_hash': sha, 'voice_text': 'Na endlich', 'voice_design': recipe},
            {'name': 'Gary', 'voice_file': str(base), 'voice_hash': sha, 'voice_text': ''}]
    lines = [dict(vf.LINES[0], speaker='Patrick', emotion='wütend'), dict(vf.LINES[1], speaker='Gary', emotion='ängstlich')]
    out = job(root, cast, lines)
    voice = vf.load(ROOT / 'cay_studio_app', 'factory_voice')
    voice.generate(root, root / 'job.json')
    profiles = json.loads((out / 'Profile.json').read_text())
    designs = [c[1] for c in vf.Model.calls if c[0] == 'design']
    assert profiles['Patrick']['file'] == str(base) and profiles['Patrick']['voice_text'] == 'Na endlich'
    assert set(profiles['Patrick']['emotion_profiles']) == {'angry'}                 # emotion take in the library voice
    assert len(designs) == 1 and designs[0]['instruct'].startswith(recipe['instruction'] + ' Acting for this take')
    assert profiles['Gary'].get('emotion_profiles', {}) == {}                      # own recording: no designed takes
    assert profiles['Gary']['voice_text'] == ''


def test_legacy_projects_ignore_recipes(monkeypatch, tmp_path):
    vf.install(monkeypatch)
    root = vf.base_dir(tmp_path)
    base = root / 'patrick.wav'; vf.write_wav(base, vf.take('Na endlich'), vf.RATE)
    import hashlib
    cast = [{'name': 'Patrick', 'voice_file': str(base), 'voice_hash': hashlib.sha256(base.read_bytes()).hexdigest(), 'voice_text': 'Na endlich',
             'voice_design': {'instruction': 'An adult man, resonant voice.', 'seed': 1}}]
    out = job(root, cast, [dict(vf.LINES[0], speaker='Patrick', emotion='wütend')], policy=16)
    vf.load(ROOT / 'cay_studio_app', 'factory_voice').generate(root, root / 'job.json')
    profiles = json.loads((out / 'Profile.json').read_text())
    assert 'voice_text' not in profiles['Patrick'] and not profiles['Patrick'].get('emotion_profiles')
