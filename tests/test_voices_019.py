"""0.19 voices (diagnosis r019, area 'voices': B5c recordings cleaned, B5e emotion and monotony, NFD delivery words).
Projects created with sound_policy 19 voice with voice_policy 19; every older project keeps voice policy 16/17/18,
its references, takes and cache signatures. Real FFmpeg for the cleaning; the voices are synthetic signals and the
models are fakes (tests/voice_fakes.py): this proves levels, noise floor, takes and the job, not how a real clone sounds."""
import asyncio
import contextlib
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'cay_studio_app'
sys.path[:0] = [str(APP), str(ROOT / 'tests')]

import voice_fakes as vf  # noqa: E402
from speech_quality import performance_key, sampling  # noqa: E402

RATE = 24000
NFD = {'wütend': 'angry', 'ängstlich': 'afraid', 'flüsternd': 'whisper', 'spöttisch': 'mocking', 'überrascht': 'surprised', 'fröhlich': 'joy'}


def nfd(text): return unicodedata.normalize('NFD', text)


# --- (3) delivery words in decomposed Unicode ---------------------------------------------------------------------
def test_nfd_delivery_words_keep_their_category_only_with_voice_policy_19():
    for word, key in NFD.items():
        assert nfd(word) != word and performance_key(word) == key
        assert performance_key(nfd(word), 19) == key                       # 0.19: macOS spelling reaches its reference
        assert performance_key(nfd(word)) == performance_key(nfd(word), 18) == 'natural'    # older projects: as before
    assert sampling(nfd('wütend'), 19) == sampling('wütend', 19) != sampling(nfd('wütend'), 18)
    assert sampling(nfd('wütend'), 18) == sampling('ruhig', 18)


class Speaking:
    """Quality.quality_voices() with a fake speech run: records the voice jobs (design and speech)."""
    def __init__(self, folder, voices=None):
        self.posts = []; self.jobs = []; self.base = folder / 'base'; self.g = {}; self.folder_path = folder; self.voices = voices or {}
        (self.base / 'envs/chatterbox/bin').mkdir(parents=True); (self.base / 'envs/chatterbox/bin/python').write_text('')
    def apply_pending(self, d): return False
    def paused(self, rid): return False
    def save(self, d): pass
    def folder(self, d): return self.folder_path
    def asset(self, aid, kind=None):
        path = self.voices.get(aid, self.folder_path.parent / 'voice.wav')
        return {'path': str(path), 'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else 'x' * 64}
    def queue_post(self, d, kind, ei, spec): self.posts.append(spec)
    def atomic(self, path, data): Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_bytes(data)
    async def idle(self, client, wait): pass
    def measured(self, d, stage): return contextlib.nullcontext()
    async def command(self, args, timeout):
        args = [str(a) for a in args]; job = json.loads(Path(args[args.index('--job') + 1]).read_text()); self.jobs.append(job)
        out = Path(job['output']); out.mkdir(parents=True, exist_ok=True)
        (out / 'Ergebnis.json').write_text(json.dumps({'lines': [{**l, 'file': 'x.wav', 'duration': 1.5, 'sha256': 'y'} for l in job['lines']]}))


def project(pin, emotion='wütend', participants=None):
    scenes = [{'kind': 'line', 'cast': ['Tim'], 'seconds': 4, 'dialogues': [{'speaker': 'Tim', 'text': 'Das ist mein Kuchen!', 'emotion': emotion}]},
              {'kind': 'line', 'cast': ['Oma'], 'seconds': 4, 'dialogues': [{'speaker': 'Oma', 'text': 'Dann iss ihn doch, Tim.', 'emotion': 'ruhig'}]}]
    return {'id': 'v' * 32, 'idea': {'duration': 15, 'episodes': 1, 'fps': 25, 'lip_sync': 'audio', 'speech_engine': 'chatterbox',
                                     'participants': participants or [{'name': 'Tim', 'voice': 'a'}, {'name': 'Oma', 'voice': 'b'}]},
            'plan': {'cast': [{'name': 'Tim'}, {'name': 'Oma'}], 'mood': 'playful'}, 'episodes': [{'scenes': scenes, 'dialogue_mode': 'rich'}], **pin}


def voice_job(tmp_path, pin, **kw):
    from factory_quality import Quality
    folder = tmp_path / ('new' if pin else 'old'); folder.mkdir(parents=True, exist_ok=True)
    d = project(pin, **{k: v for k, v in kw.items() if k in ('emotion', 'participants')})
    studio = Speaking(folder, kw.get('voices')); asyncio.run(Quality.quality_voices(studio, d))
    return d, studio.jobs[-1]


def test_new_projects_voice_with_voice_policy_19_and_nfc_delivery_words(tmp_path):
    old_d, old = voice_job(tmp_path, {}, emotion=nfd('wütend'))
    new_d, new = voice_job(tmp_path, {'sound_policy': 19}, emotion=nfd('wütend'))
    assert old_d['voice_policy'] == old['voice_policy'] == 18 and new_d['voice_policy'] == new['voice_policy'] == 19
    assert old['lines'][0]['emotion'] == nfd('wütend')                   # an old project's job keeps the stored word
    assert new['lines'][0]['emotion'] == 'wütend' and performance_key(new['lines'][0]['emotion']) == 'angry'
    # A project voiced once keeps its pin, whatever its sound policy says.
    again = project({'sound_policy': 19}); again['voice_policy'] = 18
    from factory_quality import Quality
    studio = Speaking(tmp_path / 'again'); asyncio.run(Quality.quality_voices(studio, again))
    assert studio.jobs[-1]['voice_policy'] == 18


# --- (1) recordings cleaned before cloning ----------------------------------------------------------------------
def sample(path, level_db, noise_db, words=24, music=False, seed=3):
    """A synthetic recording: speech-like take at level_db (RMS of the voice) with a lead-in, a long pause and a tail,
    plus white noise or a music-like chord bed at noise_db."""
    rng = np.random.default_rng(seed); v = vf.take(' '.join(['wort'] * words), 1).astype(np.float64)
    v = np.concatenate([np.zeros(RATE), v[:len(v) // 2], np.zeros(int(1.5 * RATE)), v[len(v) // 2:], np.zeros(RATE)])
    v *= 10 ** (level_db / 20) / np.sqrt(np.mean(v[v != 0] ** 2))
    if music:
        t = np.arange(len(v)) / RATE; bed = sum(np.sin(2 * np.pi * f * t) for f in (220, 277, 330)) * (.6 + .4 * np.sin(2 * np.pi * .5 * t))
        v += bed * 10 ** (noise_db / 20) / np.sqrt(np.mean(bed ** 2))
    else: v += rng.normal(0, 10 ** (noise_db / 20), len(v))
    vf.write_wav(path, v.astype(np.float32), RATE)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def peak_dbfs(path):
    import wave
    with wave.open(str(path)) as w: x = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(float) / 32768
    return 20 * np.log10(np.abs(x).max())


def test_a_quiet_hissy_recording_is_levelled_and_denoised_into_a_copy(tmp_path):
    import voice_reference as vr
    src = tmp_path / 'abc.wav'; original = sample(src, -40, -70)
    info = vr.clean(src)
    dest = Path(info['file'])
    assert dest == tmp_path / 'abc.ref19.wav' and (tmp_path / 'abc.ref19.json').is_file()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == original == info['source_sha256']        # original untouched
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == info['sha256'] != original
    assert info['steps'] == ['highpass', 'afftdn', 'trim', 'level']
    assert abs(info['after']['lufs'] - vr.TARGET_LUFS) <= 1 and info['before']['lufs'] < -40 and info['gain_db'] > 18
    # The hiss sits clearly further under the voice than before (afftdn, about 15 dB).
    assert info['after']['snr_db'] >= info['before']['snr_db'] + 8
    assert info['after']['seconds'] < info['before']['seconds'] - 2 and info['after']['speech_seconds'] >= info['before']['speech_seconds'] - .2
    assert peak_dbfs(dest) <= vr.PEAK_DBFS + .1 and info['warnings'] == []
    assert vr.notes('Tim', info) == ['Stimmprobe gereinigt: Rauschen gemindert, +' + str(round(info['gain_db'])) + ' dB angeglichen.']


def test_a_cleaned_copy_is_made_once_and_again_when_the_original_changes(tmp_path, monkeypatch):
    import voice_reference as vr
    src = tmp_path / 'abc.wav'; sample(src, -30, -70); first = vr.clean(src)
    def forbidden(*a, **k): raise AssertionError('cleaned again')
    monkeypatch.setattr(vr.fa, 'r128', forbidden)
    assert vr.clean(src) == first
    monkeypatch.undo(); sample(src, -30, -70, seed=4)
    assert vr.clean(src)['source_sha256'] != first['source_sha256']


def test_a_loud_recording_comes_down_and_background_or_a_short_sample_is_reported(tmp_path):
    import voice_reference as vr
    sample(tmp_path / 'loud.wav', -8, -80); loud = vr.clean(tmp_path / 'loud.wav')
    assert abs(loud['after']['lufs'] - vr.TARGET_LUFS) <= 1 and loud['gain_db'] < -6 and peak_dbfs(loud['file']) <= vr.PEAK_DBFS + .1
    sample(tmp_path / 'music.wav', -25, -33, music=True); music = vr.clean(tmp_path / 'music.wav')
    assert 'afftdn' not in music['steps'] and music['warnings'] == ['noisy'] and abs(music['after']['lufs'] - vr.TARGET_LUFS) <= 1
    assert 'viel Hintergrund' in ' '.join(vr.notes('Oma', music)) and 'Oma' in vr.notes('Oma', music)[1]
    sample(tmp_path / 'short.wav', -25, -80, words=4); short = vr.clean(tmp_path / 'short.wav')
    assert short['warnings'] == ['short'] and 'Die Stimmprobe von Tim ist kurz' in ' '.join(vr.notes('Tim', short))
    assert vr.notes('Tim', None) == ['Die Stimmprobe von Tim ließ sich nicht reinigen. Das Studio klont das Original.']


def test_demucs_is_used_only_when_it_is_there_and_the_sample_has_background(tmp_path, monkeypatch):
    import subprocess
    import voice_reference as vr
    calls = []; real = subprocess.run
    def run(args, **kw):
        if args[1:2] != ['-c']: return real(args, **kw)
        calls.append(args); out = Path(args[-1]) / 'htdemucs' / Path(args[-2]).stem; out.mkdir(parents=True)
        sample(out / 'vocals.wav', -25, -90)               # Demucs' result: the voice without the music
        return subprocess.CompletedProcess(args, 0, b'', b'')
    monkeypatch.setattr(vr.subprocess, 'run', run)
    python = tmp_path / 'python'; python.write_text('')
    sample(tmp_path / 'music.wav', -25, -33, music=True)
    assert 'demucs' not in vr.clean(tmp_path / 'music.wav', tmp_path / 'missing-python')['steps'] and not calls   # never required
    for f in vr.paths(tmp_path / 'music.wav'): f.unlink()
    isolated = vr.clean(tmp_path / 'music.wav', python)
    assert len(calls) == 1 and isolated['steps'][0] == 'demucs' and isolated['warnings'] == [] and isolated['after']['snr_db'] > 40
    assert '955717e8' in calls[0][2] and 'Musik und Geräusche abgetrennt' in vr.notes('Tim', isolated)[0]
    sample(tmp_path / 'clean.wav', -25, -80); vr.clean(tmp_path / 'clean.wav', python)
    assert len(calls) == 1                                                             # a clean sample needs no separation


def test_projects_with_voice_policy_19_clone_the_cleaned_copy(tmp_path):
    voices = {'a': tmp_path / 'tim.wav', 'b': tmp_path / 'oma.wav'}
    shas = {k: sample(p, -38, -68, seed=i) for i, (k, p) in enumerate(voices.items())}
    old_d, old = voice_job(tmp_path, {}, voices=voices)
    assert [p['voice_file'] for p in old['cast']] == [str(voices['a']), str(voices['b'])]
    assert 'reference' not in old_d['voice_profiles']['Tim']
    new_d, new = voice_job(tmp_path, {'sound_policy': 19}, voices=voices)
    tim = new['cast'][0]
    assert tim['voice_file'] == str(tmp_path / 'tim.ref19.wav') and tim['voice_hash'] == hashlib.sha256(Path(tim['voice_file']).read_bytes()).hexdigest()
    assert {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in voices.items()} == shas
    reference = new_d['voice_profiles']['Tim']['reference']
    assert reference['cleaned'] and reference['mode'] == 'x-vector' and abs(reference['lufs_after'] + 20) <= 1 and reference['gain_db'] > 15
    assert new_d['voice_profiles']['Tim']['file'] == tim['voice_file']


def test_a_recording_that_cannot_be_cleaned_is_cloned_as_it_is(tmp_path):
    broken = tmp_path / 'broken.wav'; broken.write_bytes(b'RIFF not audio')
    d, job = voice_job(tmp_path, {'sound_policy': 19}, voices={'a': broken, 'b': broken})
    assert job['cast'][0]['voice_file'] == str(broken)
    assert d['voice_profiles']['Tim']['reference'] == {'mode': 'x-vector', 'cleaned': False,
                                                       'notes': ['Die Stimmprobe von Tim ließ sich nicht reinigen. Das Studio klont das Original.']}
