"""0.19 sound for projects created with sound_policy 19 (diagnosis 0.19, complaints B5a/B5b/B5d and the
Sprachprüfung stops for Patrick): no automatic whoosh, every take levelled and gently denoised on its own,
measured linear loudness stages instead of the single-pass loudnorm that pumped music and hiss between the
lines, music well under the voices, one ambience bed per location. Projects without the pin mix exactly as
before. Real FFmpeg and the real mix code; the voices are synthetic signals, not AI speech: this proves
levels, timing and the checks, not how a real voice sounds."""
import asyncio
import copy
import hashlib
import json
import math
import random
import re
import statistics
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'cay_studio_app'), str(ROOT / 'tests')]

import audio_fixtures as fx  # noqa: E402
import factory_audio as fa  # noqa: E402
import speech_check  # noqa: E402

RATE = 24000
SETTINGS = {'music_mode': 'auto', 'music_level': .7, 'effects_level': .65, 'ambience_level': .6}   # a new project's mix
NEW_HELPERS = ('mix19', 'prepare_take', 'shape_take', 'denoise', 'afftdn_delay', 'run_f32', 'r128', 'loudness', 'kweight',
               'synth_ambience', 'bed_texture', 'places', 'bridged', 'noise_window', 'speech_loudness')


def take(folder, key, scene, speaker, seconds, level=.6, pitch=140., noise_db=None, lead=None, emotion='Natürlich'):
    """A TTS-like take: 70 ms lead-in before the first word (what finish_voice leaves), optional hiss."""
    rng = random.Random(scene)
    samples = [0.] * int(.07 * RATE) + fx.speech(seconds - .07, level=level, pitch=pitch)
    if noise_db is not None:
        a = 10 ** (noise_db / 20) * 3 ** .5; samples = [v + a * rng.uniform(-1, 1) for v in samples]
    if lead is not None:
        a = 10 ** (lead / 20) * 3 ** .5
        for i in range(int(.01 * RATE), int(.065 * RATE)): samples[i] += a * rng.uniform(-1, 1)      # a breath
    line = fx.line(folder, key, 0, scene, 0, speaker, 'Text', samples, offset=.08)
    line['emotion'] = emotion
    return line


# Seconds are whole video frames. Patrick's reference voice is quiet: his takes come in 14, 20 and 26 dB
# under the others (Cay's 8624: "1 von 21 Dialogbeiträgen nicht hörbar", Patrick).
SHOTS = [(2.4, None, 0, 0, 'Krosse Krabbe', 'room'), (3.0, 'SpongeBob', 260., 0, 'Krosse Krabbe', 'room'),
         (2.4, None, 0, 0, 'Krosse Krabbe', 'room'), (3.2, 'Patrick', 120., -14, 'Krosse Krabbe', 'room'),
         (2.8, 'Mr. Krabs', 110., 0, 'Krosse Krabbe', 'wind'), (2.4, None, 0, 0, 'Straße', 'wind'),
         (3.0, 'Patrick', 120., -20, 'Straße', 'wind'), (2.6, 'Sandy', 220., 0, 'Straße', 'wind'),
         (3.2, 'Patrick', 120., -26, 'Straße', 'wind'), (2.4, None, 0, 0, 'Straße', 'wind')]


def episode(folder):
    scenes = []
    for si, (seconds, speaker, pitch, db, where, ambience) in enumerate(SHOTS):
        lines = [take(folder, f'E01_S{si + 1:02}_T01', si, speaker, seconds - .4, .6 * 10 ** (db / 20), pitch)] if speaker else []
        scenes.append({'seconds': seconds, 'lines': lines, 'ambience': ambience, 'sound_cues': [], 'kind': 'line' if speaker else 'action',
                       'location': fa.place({'location': where})})
    return scenes


def lufs(path, a=0., b=999.):
    r = subprocess.run(['ffmpeg', '-nostdin', '-v', 'info', '-ss', f'{a:.3f}', '-t', f'{b - a:.3f}', '-i', str(path), '-af', 'ebur128', '-f', 'null', '-'],
                       capture_output=True, text=True)
    return float(re.findall(r'I:\s+(-?[\d.]+) LUFS', r.stderr)[-1])


def windows(scenes):
    """(speaker or None, start, end): the spoken part of every line, the silent shots after 0.5 s."""
    cursor = 0.; out = []
    for s in scenes:
        if s['lines']:
            l = s['lines'][0]; out.append((l['speaker'], cursor + l['offset'], cursor + l['offset'] + l['duration']))
        else:
            out.append((None, cursor + .5, cursor + s['seconds']))
        cursor += s['seconds']
    return out


@pytest.fixture(scope='module')
def mixed(tmp_path_factory):
    folder = tmp_path_factory.mktemp('sound19')
    scenes = episode(folder / 'lines')
    out = fa.mix(folder / 'mix', scenes, 'suspense', None, SETTINGS, 18, 19)
    return Path(out), folder / 'mix', scenes


def test_one_constant_gain_no_pumping_and_platform_loudness(mixed):
    out, folder, scenes = mixed
    # Diagnosis: the single-pass loudnorm applied +1.1 dB on a loud line and +12.3 dB in a silent shot.
    gains = [lufs(out, a, b) - lufs(folder / 'Vormischung.wav', a, b) for _, a, b in windows(scenes)]
    assert max(gains) - min(gains) <= .5, gains
    assert abs(lufs(out) + 14) <= 1
    report = json.loads((folder / 'Tonbericht.json').read_text())
    assert report['sound_policy'] == 19 and report['loudness']['true_peak_dbtp'] <= -1.
    duration = sum(s['seconds'] for s in scenes)
    with wave.open(str(out)) as w:
        assert w.getframerate() == 48000 and w.getnchannels() == 2 and abs(w.getnframes() - duration * 48000) <= 1
    with wave.open(str(folder / 'Dialogschnitt.wav')) as w:
        assert abs(w.getnframes() - duration * RATE) <= 1


def test_quiet_takes_end_as_loud_as_the_others(mixed):
    out, folder, scenes = mixed
    levels = [(who, lufs(out, a, b)) for who, a, b in windows(scenes) if who]
    others = statistics.mean(v for who, v in levels if who != 'Patrick')
    patrick = [v for who, v in levels if who == 'Patrick']
    assert len(patrick) == 3 and all(abs(v - others) <= 1.5 for v in patrick), levels
    report = json.loads((folder / 'Tonbericht.json').read_text())
    gains = report['line_gain_db']
    assert set(gains) == {l['key'] for s in scenes for l in s['lines']}
    assert gains['E01_S07_T01'] > 12 and gains['E01_S09_T01'] > 12 and len(report['quiet_takes']) >= 2
    assert any('Szene 9, Figur Patrick' in q for q in report['quiet_takes'])
    check = json.loads((folder / 'Sprachpruefung.json').read_text())
    assert check['blocking'] == 0 and not any(e['status'] in ('überdeckt', 'fehlt', 'leise') for e in check['lines'])
    flagged = next(e for e in check['lines'] if e['key'] == 'E01_S09_T01')
    assert flagged['status'] == 'angehoben' and 'Stimmprobe sehr leise' in flagged['note'] and flagged['line_gain_db'] > 12


def test_music_stays_well_under_speech_and_no_automatic_whoosh(mixed):
    out, folder, scenes = mixed
    spans = windows(scenes)
    speech = statistics.median(lufs(out, a, b) for who, a, b in spans if who)
    pauses = statistics.median(lufs(out, a, b) for who, a, b in spans if not who)
    assert speech - pauses >= 8, (speech, pauses)          # diagnosis: 3.3-4.9 LU in Cay's two films
    effects, _ = speech_check.read_wav(folder / 'Effekte.wav')
    assert any(s['kind'] == 'action' for s in scenes) and max(map(abs, effects)) == 0


def test_an_explicit_cue_still_sounds(tmp_path):
    scenes = [{'seconds': 2.4, 'lines': [take(tmp_path, 'E01_S01_T01', 0, 'SpongeBob', 2.)], 'ambience': 'room', 'sound_cues': [], 'kind': 'line'},
              {'seconds': 2.0, 'lines': [], 'ambience': 'room', 'sound_cues': [{'kind': 'door', 'position': .3}], 'kind': 'action'}]
    fa.mix(tmp_path / 'mix', scenes, 'playful', None, {**SETTINGS, 'music_mode': 'off'}, 18, 19)
    effects, _ = speech_check.read_wav(tmp_path / 'mix/Effekte.wav')
    door = round((2.4 + .3 * 2.0) * RATE)
    assert max(map(abs, effects[door:door + RATE // 4])) > 1000 and max(map(abs, effects[:door])) == 0


def hiss(x, a, b):
    """Noise floor 4-11 kHz by minimum statistics (median per bin over 20 ms frames); the voice has no energy there."""
    n = 480; frames = np.array([x[k:k + n] * np.hanning(n) for k in range(int(a * RATE), int(b * RATE) - n, 240)])
    power = np.abs(np.fft.rfft(frames, axis=1)) ** 2; f = np.fft.rfftfreq(n, 1 / RATE)
    return 10 * np.log10(np.median(power[:, (f >= 4000) & (f <= 11000)], axis=0).sum() + 1e-20)


def speech_lufs(x):
    return fa.r128(fa.PIPE, '', fa.array('f', x[int(.1 * RATE):]))[0]


@pytest.mark.parametrize('lead,how', [(None, 'Vorlauf'), (-22, 'Pause')])
def test_denoise_lowers_the_hiss_and_keeps_the_voice(tmp_path, lead, how):
    line = take(tmp_path, 'E01_S01_T01', 3, 'SpongeBob', 2.6, pitch=200., noise_db=-45., lead=lead)
    raw = fa.read_f32(line['file']); prepared = fa.prepare_take(line)
    assert prepared['denoise'] == how                       # a breath in the lead-in: learn from a pause instead
    x, y = np.array(raw, dtype=float), np.array(prepared['data'], dtype=float)
    assert len(y) == len(x)
    assert hiss(y, .2, 2.5) <= hiss(x, .2, 2.5) - 12
    assert abs(speech_lufs(prepared['data']) - speech_lufs(raw)) <= .5
    # Same timing: the voice starts in the same 10 ms frame (afftdn delays its output by itself).
    def onset(v):
        fr = speech_check.frames(v, RATE, 0, len(v) / RATE); top = max(fr); return next(i for i, e in enumerate(fr) if e > top / 10)
    assert onset(raw) == onset(prepared['data'])


def test_a_failing_denoise_mixes_the_take_as_it_is(tmp_path, monkeypatch):
    monkeypatch.setattr(fa, 'run_f32', lambda graph, data: None)
    monkeypatch.setattr(fa, 'afftdn_measured', [])
    line = take(tmp_path, 'E01_S01_T01', 3, 'SpongeBob', 2.6, noise_db=-45.)
    prepared = fa.prepare_take(line)
    assert prepared['denoise'] == 'Fehler' and list(prepared['data']) == list(fa.read_f32(line['file']))
    scenes = [{'seconds': 3.0, 'lines': [line], 'ambience': 'room', 'sound_cues': [], 'kind': 'line'}]
    assert Path(fa.mix(tmp_path / 'mix', scenes, 'playful', None, {**SETTINGS, 'music_mode': 'off'}, 18, 19)).is_file()
    assert json.loads((tmp_path / 'mix/Tonbericht.json').read_text())['denoise'] == {'E01_S01_T01': 'Fehler'}


def test_a_clean_take_is_left_alone(tmp_path):
    line = take(tmp_path, 'E01_S01_T01', 3, 'SpongeBob', 2.)
    prepared = fa.prepare_take(line)
    assert prepared['denoise'] == 'sauber' and list(prepared['data']) == list(fa.read_f32(line['file']))


def rms_db(x):
    return 10 * math.log10(max(float(np.mean(np.square(x))), 1e-20))


def test_one_continuous_bed_per_location(tmp_path):
    scenes = [{'seconds': 2.0, 'ambience': 'room', 'location': 'kueche'}, {'seconds': 1.6, 'ambience': 'wind', 'location': 'kueche'},
              {'seconds': 2.0, 'ambience': 'room', 'location': 'kueche'}, {'seconds': 2.0, 'ambience': 'rain', 'location': 'garten'},
              {'seconds': 2.0, 'ambience': 'none', 'location': 'keller'}]
    beds = fa.synth_ambience(tmp_path / 'Umgebung.wav', scenes, .6)
    assert [(b['location'], b['kind']) for b in beds] == [('kueche', 'room'), ('garten', 'rain'), ('keller', 'none')]
    data, _ = speech_check.read_wav(tmp_path / 'Umgebung.wav'); x = np.array(data, dtype=float) / 32768
    kitchen = x[int(.4 * RATE):int(5.4 * RATE)]
    assert abs(rms_db(kitchen) - (fa.AMBIENCE_DBFS['room'] + 20 * math.log10(.6))) <= 1.5
    frame = RATE // 20
    for cut in (2.0, 3.6):                                   # shots of the same place: no fade, no level step
        around = [rms_db(x[i:i + frame]) for i in range(int((cut - .2) * RATE), int((cut + .2) * RATE), frame)]
        assert min(around) >= rms_db(kitchen) - 5 and max(around) <= rms_db(kitchen) + 5, (cut, around)
        assert abs(rms_db(x[int((cut - .3) * RATE):int(cut * RATE)]) - rms_db(x[int(cut * RATE):int((cut + .3) * RATE)])) <= 1.5
    # Where the place changes: a crossfade, no hole.
    change = [rms_db(x[i:i + frame]) for i in range(int(5.4 * RATE), int(5.8 * RATE), frame)]
    assert min(change) >= min(rms_db(kitchen), rms_db(x[int(6 * RATE):int(7.4 * RATE)])) - 5, change
    assert max(map(abs, data[int(7.85 * RATE):])) == 0      # 'none' stays silent


@pytest.mark.parametrize('kind', ['wind', 'rain', 'room', 'train', 'forest'])
def test_beds_do_not_hiss(tmp_path, kind):
    fa.synth_ambience(tmp_path / 'bed.wav', [{'seconds': 3.0, 'ambience': kind, 'location': 'x'}], 1.)
    data, _ = speech_check.read_wav(tmp_path / 'bed.wav'); x = np.array(data[RATE // 2:-RATE // 2], dtype=float)
    power = np.abs(np.fft.rfft(x)) ** 2; f = np.fft.rfftfreq(len(x), 1 / RATE)
    assert 10 * np.log10(power[f >= 4000].sum() / power.sum()) <= -25, kind   # white noise: about -1.6 dB


def test_a_missing_line_still_stops_and_a_masked_quiet_line_is_lifted(tmp_path):
    loud = fx.line(tmp_path, 'E01_S28_T01', 0, 27, 0, 'SpongeBob', 'Ich habe keine Angst!', fx.speech(2., level=.6))
    quiet = fx.line(tmp_path, 'E01_S29_T01', 0, 28, 0, 'Patrick', 'Sag ihm nicht, dass du Angst hast, Sponge.', fx.speech(2.4, level=.03))
    quiet['emotion'] = 'flüsternd'
    scenes = [{'seconds': 3., 'lines': [loud], 'ambience': 'room', 'sound_cues': []},
              {'seconds': 3., 'lines': [quiet], 'ambience': 'wind', 'sound_cues': [{'kind': 'magic', 'position': .2}, {'kind': 'bell', 'position': .45}]}]
    fa.mix(tmp_path / 'mix', scenes, 'suspense', None, None, 18, 19)
    patrick = next(e for e in json.loads((tmp_path / 'mix/Sprachpruefung.json').read_text())['lines'] if e['speaker'] == 'Patrick')
    assert patrick['status'] not in ('überdeckt', 'fehlt') and patrick['margin_db'] >= speech_check.CROWDED_DB
    scenes[1]['lines'] = [fx.line(tmp_path, 'E01_S29_T01b', 0, 28, 0, 'Patrick', 'Sag ihm nicht.', fx.near_silence(2.4))]
    with pytest.raises(speech_check.SpeechCheckError, match='Figur Patrick'):
        fa.mix(tmp_path / 'mix2', scenes, 'suspense', None, None, 18, 19)
    assert not (tmp_path / 'mix2/Tonmischung.wav').exists()


# --- Projects without the pin -------------------------------------------------------------------------

def test_without_the_pin_the_old_mix_runs_byte_identical_and_never_the_new_path(tmp_path, monkeypatch):
    def forbidden(*a, **k): raise AssertionError('0.19 sound used without sound_policy 19')
    for name in NEW_HELPERS: monkeypatch.setattr(fa, name, forbidden)
    scenes = [{'seconds': 2.4, 'lines': [take(tmp_path, 'E01_S01_T01', 0, 'SpongeBob', 2.)], 'ambience': 'room', 'sound_cues': [], 'kind': 'line'},
              {'seconds': 2.0, 'lines': [], 'ambience': 'wind', 'sound_cues': [], 'kind': 'action', 'location': 'x'}]
    first = Path(fa.mix(tmp_path / 'a', copy.deepcopy(scenes), 'suspense', None, SETTINGS, 18)).read_bytes()
    second = Path(fa.mix(tmp_path / 'b', copy.deepcopy(scenes), 'suspense', None, SETTINGS, 18, 0)).read_bytes()
    assert hashlib.sha256(first).digest() == hashlib.sha256(second).digest()
    assert 'sound_policy' not in json.loads((tmp_path / 'a/Tonbericht.json').read_text())
    effects, _ = speech_check.read_wav(tmp_path / 'a/Effekte.wav')
    assert max(map(abs, effects)) > 0                        # 0.18 still opens the action shot with its whoosh
    assert fa.mix(tmp_path / 'c', copy.deepcopy(scenes), 'suspense', None, SETTINGS, 17, 18)       # 18 is no 0.19 pin


def test_specs_carry_the_pin_and_the_place_only_when_pinned():
    scenes = [{'kind': 'action', 'location': '  Krosse   Krabbe '}, {'location': 'Straße'}]
    assert fa.sound_spec({}) == {} and fa.sound_spec({'sound_policy': 18}) == {} and fa.sound_spec({'sound_policy': 19}) == {'sound_policy': 19}
    assert fa.scene_kinds({}, scenes) == [{}, {}]
    assert fa.scene_kinds({'edit_policy': 18}, scenes) == [{'kind': 'action'}, {'kind': 'line'}]
    assert fa.scene_kinds({'edit_policy': 18, 'sound_policy': 19}, scenes) == [{'kind': 'action', 'location': 'krosse krabbe'}, {'kind': 'line', 'location': 'straße'}]


def test_the_post_queue_and_the_export_pass_the_pin(tmp_path, monkeypatch):
    import factory_post
    import factory_video
    calls = []
    def record(folder, scenes, mood, music=None, settings=None, policy=17, sound=0):
        calls.append((policy, sound)); path = tmp_path / f'mix{len(calls)}.wav'; path.write_bytes(b'x'); return str(path)
    monkeypatch.setattr(factory_post, 'mix', record)

    class Resources:
        async def cpu(self, run, label, job): return job()

    class Post(factory_post.PostProduction):
        def __init__(self): self.g = {'resources': Resources()}
        def sql(self, sql, args=()): pass
    for spec in ({'edit_policy': 18}, {'edit_policy': 18, 'sound_policy': 19}, {}):
        row = {'id': 'p', 'run_id': 'r', 'kind': 'mix', 'episode': 0, 'spec': json.dumps({'folder': str(tmp_path), 'scenes': [], 'mood': 'playful', 'seconds': 1, **spec})}
        asyncio.run(Post().post_execute(row))
    assert calls == [(18, 0), (18, 19), (17, 0)]

    class Stop(Exception): pass
    def stop(folder, scenes, mood, music=None, settings=None, policy=17, sound=0):
        calls.append(('export', policy, sound)); raise Stop()
    monkeypatch.setattr(fa, 'mix', stop)
    monkeypatch.setattr(factory_video, 'prepare', lambda spec: {'parts': [], 'seconds': 1., 'performance': {}})
    (tmp_path / 'export').mkdir()
    for spec in ({'edit_policy': 18}, {'edit_policy': 18, 'sound_policy': 19}):
        with pytest.raises(Stop):
            factory_video.finish({'folder': str(tmp_path / 'export'), 'fps': 25, 'scenes': [], 'mood': 'playful', 'output': str(tmp_path / 'x.mp4'), **spec})
    assert calls[-2:] == [('export', 18, 0), ('export', 18, 19)]


def test_the_queued_mix_spec_has_the_pin_and_places_only_for_new_projects(tmp_path):
    import cut_samples as cs
    import screenplay as sp
    from factory_quality import Quality
    from factory_timing import plan_seconds
    text, cast = cs.TEXTS['cay_blocks']
    title, beats, lines, _ = sp.parse(text, cast)
    cut = sp.ensure_action(sp.shots(title, beats, lines, cast), 60)
    base = sp.assemble(title, {'goal': 'Ziel', 'stakes': 'Einsatz', 'payoff': 'Pointe'}, {'title': 'x'}, cut, cs.visuals_for(cut),
                       [{'name': n, 'appearance': 'x'} for n in cast], {})
    plan_seconds(base, 60, 25)

    class Voicing:
        def __init__(self): self.posts = []
        def apply_pending(self, d): return False
        def paused(self, rid): return False
        def save(self, d): pass
        def folder(self, d): return tmp_path
        def asset(self, aid, kind=None): raise AssertionError('no music in this test')
        def queue_post(self, d, kind, ei, spec): self.posts.append(spec)
    specs = {}
    for pin in ({}, {'sound_policy': 19}):
        episode = copy.deepcopy(base)
        d = {'id': 'v' * 32, 'idea': {'duration': 60, 'episodes': 1, 'fps': 25, 'participants': [], 'lip_sync': 'audio'},
             'plan': {'cast': [{'name': n} for n in cs.CAST], 'mood': 'playful'}, 'episodes': [episode], 'lines': cs.timed_lines(episode),
             'audio_only': True, 'voice_policy': 18, 'edit_policy': 18, **pin}
        studio = Voicing(); asyncio.run(Quality.quality_voices(studio, d)); specs[bool(pin)], = studio.posts
    old, new = specs[False], specs[True]
    assert 'sound_policy' not in old and not any('location' in s for s in old['scenes'])
    assert new['sound_policy'] == 19 and all(s['location'] for s in new['scenes'])
    assert [{k: v for k, v in s.items() if k != 'location'} for s in new['scenes']] == old['scenes']
