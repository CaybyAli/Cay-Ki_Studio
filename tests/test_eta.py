"""Remaining animation time: lip-sync and motion sections are timed apart (a film mixes both),
with earlier films on this PC as fallback. Cay saw only "Restzeit nach drei fertigen Abschnitten"
at 6 of 10 sections because the old rule needed every remaining section to be of one kind."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))

from factory_progress import RenderProgress, profile_key  # noqa: E402

TALK = {'width': 576, 'height': 1024, 'steps': 4, 'audio_conditioned': True, 'frames': 81, 'native_fps': 25}
MOTION = {'width': 576, 'height': 1024, 'steps': 4, 'audio_conditioned': False, 'frames': 81, 'native_fps': 16}


def progress(history):
    class F:
        def rows(self, q, a=()): return history
    rp = RenderProgress.__new__(RenderProgress); rp.f = F()
    return rp


def hist(profile, seconds, n=3):
    return [{'started': 0., 'ended': seconds, 'detail': json.dumps({'status': 'done', 'profile': profile})}] * n


def test_mixed_remaining_sections_get_an_estimate_from_this_project():
    rp = progress([])
    samples = {profile_key(TALK): [2.0, 2.1, 1.9], profile_key(MOTION): [.5, .6, .55]}
    rows = [{'id': 'a', 'status': 'done'}, {'id': 'b', 'status': 'done'}]
    metrics = {'a': {'detail': {'profile': TALK}}, 'b': {'detail': {'profile': MOTION}}}
    eta, note = rp.estimate({'state': 'rendering'}, [(None, 161, True), (None, 81, False), (None, 81, False)], samples, rows, metrics, None, {'width': 576})
    assert note is None and eta['source'] == 'project'
    assert 161 * 1.9 * .9 + 162 * .5 * .9 <= eta['low'] < eta['high'] <= 161 * 2.1 * 1.15 + 162 * .6 * 1.15 + 1e-6


def test_a_kind_not_yet_rendered_here_uses_earlier_films():
    rp = progress(hist(MOTION, 40.5))                                   # 0.5 s per frame in an earlier film
    samples = {profile_key(TALK): [2.0, 2.0, 2.0]}
    eta, note = rp.estimate({'state': 'rendering'}, [(None, 81, False)], samples, [{'id': 'a', 'status': 'done'}],
                            {'a': {'detail': {'profile': TALK}}}, None, {'width': 576})
    assert eta['source'] == 'history' and eta['low'] > 0


def test_without_any_measurement_the_note_says_what_is_missing():
    eta, note = progress([]).estimate({'state': 'rendering'}, [(None, 81, False)], {}, [], {}, None, {'width': 576})
    assert eta is None and note == 'Restzeit folgt nach drei fertigen Bewegungsabschnitten'
    assert progress([]).estimate({'state': 'rendering', 'paused': True}, [(None, 81, False)], {}, [], {}, None, {}) == (None, None)
