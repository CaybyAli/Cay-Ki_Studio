"""Autopilot decisions. Pure logic with real files; no models."""
import hashlib
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path.insert(0, str(APP))

from autopilot import Autopilot  # noqa: E402
from factory_timing import POLICY  # noqa: E402


class Fake(Autopilot):
    def path(self, p): return Path(p)


def scene(*ids, selected=None):
    return {'variants': [{'id': i, 'key': f'image:0:0:0:{slot}'} for slot, i in enumerate(ids)], 'selected': selected, 'round': 0}


def test_images_take_first_variant_and_continue():
    d = {'idea': {'autopilot': True}, 'state': 'image_review',
         'episodes': [{'scenes': [scene('a' * 32, 'b' * 32), scene('c' * 32, 'd' * 32, selected='d' * 32)]}]}
    assert Fake().apply_autopilot(d)
    assert [s['selected'] for s in d['episodes'][0]['scenes']] == ['a' * 32, 'd' * 32]   # Cay's own choice stays
    assert d['state'] == 'voicing'


def sound(tmp_path, seconds=15.0):
    wav = tmp_path / 'mix.wav'; wav.write_bytes(b'RIFF-test')
    digest = hashlib.sha256(wav.read_bytes()).hexdigest()
    return {'idea': {'autopilot': True, 'duration': 15, 'fps': 25}, 'state': 'voice_review', 'audio_revision': 3,
            'timing_policy': POLICY, 'timing_fps': 25, 'episodes': [{}],
            'lines': [{'file': str(wav), 'sha256': digest}], 'previews': [{'file': str(wav), 'sha256': digest, 'seconds': seconds}]}


def test_sound_approved_only_when_consistent(tmp_path):
    d = sound(tmp_path)
    assert Fake().apply_autopilot(d) and d['state'] == 'rendering' and d['voice_approval'] == 'autopilot'
    short = sound(tmp_path, seconds=12.0)
    assert Fake().apply_autopilot(short) and short['state'] == 'voice_review'
    assert Fake().autopilot_waits(short) and 'Mindestdauer' in short['phase']
    short['audio_revision'] = 4                                   # new sound version: autopilot may try again
    assert not Fake().autopilot_waits(short)


def test_sample_stop_is_skipped_and_manual_mode_untouched(tmp_path):
    d = {'idea': {'autopilot': True}, 'state': 'sample_review', 'sample': {'key': 'k1'}}
    assert Fake().apply_autopilot(d) and d['state'] == 'rendering' and d['sample_approval'] == 'k1'
    manual = sound(tmp_path); manual['idea']['autopilot'] = False
    assert not Fake().apply_autopilot(manual) and manual['state'] == 'voice_review'
