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
    assert short['warnings'] == ['short'] and 'Stimmprobe von Tim: nur ' in ' '.join(vr.notes('Tim', short))
    assert vr.notes('Tim', None) == ['Stimmprobe von Tim ließ sich nicht reinigen. Das Studio klont das Original.']


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
                                                       'notes': ['Stimmprobe von Tim ließ sich nicht reinigen. Das Studio klont das Original.']}


# --- (2) more emotion: performed references for recordings, more takes, the speaker kept ---------------------------
def recordings(root, transcript=''):
    cast = []
    for i, p in enumerate(vf.CAST):
        f = root / f'rec{i}.wav'; vf.write_wav(f, vf.take('Na endlich, komm rein, schnell jetzt', i), RATE)
        cast.append({**p, 'voice_file': str(f), 'voice_hash': hashlib.sha256(f.read_bytes()).hexdigest(), 'voice_text': transcript})
    return cast


def speak(module, root, cast, policy, out='lines'):
    job = {'cast': cast, 'lines': vf.LINES, 'output': str(root / out), 'voice_policy': policy}
    (root / f'{out}.json').write_text(json.dumps(job)); vf.Model.calls = []
    module.generate(root, root / f'{out}.json')
    result = json.loads((root / out / 'Ergebnis.json').read_text())
    return result, [c[1] for c in vf.Model.calls if c[0] == 'clone']


def test_recordings_get_performed_references_and_every_line_more_takes(monkeypatch, tmp_path):
    from factory_voice import EMOTION_TEXTS
    vf.install(monkeypatch); root = vf.base_dir(tmp_path); cast = recordings(root)
    speech = vf.load(APP, 'factory_speech')
    old, old_calls = speak(speech, root, cast, 18, 'old')
    assert len(old_calls) == 7 and 'references' not in old                       # 0.18: 2 takes per emotional line, 1 for 'Natürlich'
    assert not any(c['text'] in {t for _, t in EMOTION_TEXTS.values()} for c in old_calls)
    new, calls = speak(speech, root, cast, 19)
    performed = [c['text'] for c in calls if c['text'] in {t for _, t in EMOTION_TEXTS.values()}]
    # Mr. Krabs needs 'angry', Plankton 'afraid' and 'whisper': three acted texts, three takes each.
    assert performed == [EMOTION_TEXTS['angry'][1]] * 3 + [EMOTION_TEXTS['afraid'][1]] * 3 + [EMOTION_TEXTS['whisper'][1]] * 3
    lines = [c['text'] for c in calls if c['text'] not in performed]
    assert [lines.count(l['text']) for l in vf.LINES] == [3, 3, 2, 3]            # 0.19: emotional lines 3 takes, 'Natürlich' 2
    assert new['references'] == {'Mr. Krabs': {'mode': 'x-vector', 'emotions': ['angry'], 'performed': ['angry']},
                                 'Plankton': {'mode': 'x-vector', 'emotions': ['afraid', 'whisper'], 'performed': ['afraid', 'whisper']}}
    metas = [json.loads(Path(l['file']).with_suffix('.json').read_text())['quality'] for l in new['lines']]
    assert [m['takes'] for m in metas] == [3, 3, 2, 3]
    assert [Path(l['file']).name for l in new['lines']] != [Path(l['file']).name for l in old['lines']]
    assert all(c['temperature'] == .9 and c['top_k'] == 50 for c in calls)
    # The performed references and the lines are made once: a second run reads them from the cache.
    again, calls = speak(speech, root, cast, 19)
    assert calls == [] and again == new
    references = sorted((root / 'lines/Gefuehle').glob('*.wav'))
    assert len(references) == 3 and all(json.loads(f.with_suffix('.json').read_text())['takes'] == 3 for f in references)


def test_a_designed_voice_keeps_its_designed_references(monkeypatch, tmp_path):
    vf.install(monkeypatch)
    names, profiles, _ = vf.run_design(vf.load(APP, 'factory_voice'), tmp_path, policy=19)
    assert set(names['Plankton']['moods']) == {'afraid', 'whisper'} and set(names['Mr. Krabs']['moods']) == {'angry'}
    lines, clone = vf.run_speech(vf.load(APP, 'factory_speech'), tmp_path, profiles, policy=19)
    from factory_voice import EMOTION_TEXTS
    assert not any(c[1]['text'] in {t for _, t in EMOTION_TEXTS.values()} for c in clone) and len(clone) == 11


class Similar(vf.Model):
    """Takes alternate between a calm and a very lively one; the lively one is another voice (different embedding)."""
    def __init__(self): self.model = self

    def generate_voice_clone(self, **kw):
        vf.Model.calls.append(('clone', {k: v for k, v in kw.items() if k != 'voice_clone_prompt'}))
        n = len(vf.Model.calls); t = np.arange(int(RATE * (len(kw['text'].split()) * .45 + .4))) / RATE
        depth = 7 if n % 2 == 0 else 1                                                    # semitones of melody
        pitch = 160 * 2 ** (depth * np.sin(2 * np.pi * 1.3 * t) / 12); phase = 2 * np.pi * np.cumsum(pitch) / RATE
        amp = .6 if depth == 7 else .25
        return [(amp * np.maximum(0, np.sin(np.pi * 4 * t)) ** .6 * np.sin(phase)).astype(np.float32)], RATE

    def extract_speaker_embedding(self, audio, sr):
        return np.array([0., 1.]) if np.abs(audio).max() > .45 else np.array([1., 0.])


def test_the_liveliest_take_wins_only_while_it_sounds_like_the_speaker(monkeypatch, tmp_path):
    vf.install(monkeypatch); monkeypatch.setitem(sys.modules['qwen_tts'].__dict__, 'Qwen3TTSModel', Similar)
    root = vf.base_dir(tmp_path); cast = recordings(root)
    speech = vf.load(APP, 'factory_speech')
    old, _ = speak(speech, root, cast, 18, 'old')
    new, _ = speak(speech, root, cast, 19)
    quality = lambda r: [json.loads(Path(l['file']).with_suffix('.json').read_text())['quality'] for l in r['lines']]
    # 0.18 keeps the livelier take whoever speaks; 0.19 only takes that sound like the recording (cosine 1.0).
    assert any(q['prosody'] > 2 for q in quality(old))
    assert all(q['similarity'] == 1.0 and q['prosody'] < 2 for q in quality(new))
    for f in (root / 'lines/Gefuehle').glob('*.json'):
        assert json.loads(f.read_text())['quality']['similarity'] == 1.0


def test_chatterbox_gives_every_line_two_takes_only_with_voice_policy_19(monkeypatch, tmp_path):
    vf.install(monkeypatch); calls = []
    monkeypatch.setitem(sys.modules, 'perth', type(sys)('perth')); sys.modules['perth'].PerthImplicitWatermarker = object
    class Wave:
        def __init__(self, data): self.data = data
        def detach(self): return self
        def cpu(self): return self
        def numpy(self): return self.data
    class Model:
        sr = vf.RATE; conds = {'default': 1}
        @classmethod
        def from_local(cls, ckpt, device='cuda'): return cls()
        def generate(self, text, language_id, audio_prompt_path=None, **kw):
            calls.append(text); return Wave(vf.take(text, len(calls)))
    mtl = type(sys)('chatterbox.mtl_tts'); mtl.ChatterboxMultilingualTTS = Model
    monkeypatch.setitem(sys.modules, 'chatterbox', type(sys)('chatterbox')); monkeypatch.setitem(sys.modules, 'chatterbox.mtl_tts', mtl)
    tts = vf.load(APP, 'factory_tts'); root = vf.base_dir(tmp_path); cast = recordings(root)
    monkeypatch.setattr(tts, 'checkpoint', lambda base: tmp_path)
    files = {}
    for policy in (18, 19):
        job = {'cast': cast, 'lines': vf.LINES, 'voice_policy': policy, 'output': str(root / str(policy))}
        (root / f'{policy}.json').write_text(json.dumps(job)); calls.clear()
        monkeypatch.setattr(sys, 'argv', ['factory_tts.py', '--base', str(root), '--job', str(root / f'{policy}.json')]); tts.main()
        lines = json.loads((root / str(policy) / 'Ergebnis.json').read_text())['lines']
        files[policy] = [Path(l['file']).name for l in lines]
        metas = [json.loads(Path(l['file']).with_suffix('.json').read_text())['quality'] for l in lines]
        assert len(calls) == (4 if policy == 18 else 8)
        assert all(('takes' in m) == (policy == 19) for m in metas) and all(m.get('takes', 2) == 2 for m in metas)
    assert not set(files[18]) & set(files[19])


def test_the_project_keeps_how_each_figure_was_cloned(tmp_path):
    """quality_voices stores the speech adapter's per-figure result (0.19 'references') next to the cleaning summary."""
    from factory_quality import Quality
    voices = {'a': tmp_path / 'tim.wav', 'b': tmp_path / 'oma.wav'}
    for i, p in enumerate(voices.values()): sample(p, -30, -70, seed=i)
    class Adapter(Speaking):
        async def command(self, args, timeout):
            await Speaking.command(self, args, timeout); job = self.jobs[-1]; out = Path(job['output']) / 'Ergebnis.json'
            result = json.loads(out.read_text()); result['references'] = {'Tim': {'mode': 'x-vector', 'emotions': ['angry'], 'performed': ['angry']}}
            out.write_text(json.dumps(result))
    d = project({'sound_policy': 19}); folder = tmp_path / 'p'; folder.mkdir()
    asyncio.run(Quality.quality_voices(Adapter(folder, voices), d))
    assert d['voice_profiles']['Tim']['speech'] == {'mode': 'x-vector', 'emotions': ['angry'], 'performed': ['angry']}
    assert d['voice_profiles']['Tim']['reference']['cleaned'] and 'speech' not in d['voice_profiles']['Oma']


# --- (4) the diagnosis shows it per figure -----------------------------------------------------------------------------
def test_the_diagnosis_shows_mode_cleaning_takes_and_deliveries_per_figure(tmp_path, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location('cay_diagnose_voices', ROOT / 'Cay_Studio_Diagnose.py')
    diag = importlib.util.module_from_spec(spec); spec.loader.exec_module(diag)
    files = []
    for i, takes in enumerate((3, 2, 3)):
        f = tmp_path / f'l{i}.wav'; f.write_bytes(b''); f.with_suffix('.json').write_text(json.dumps({'quality': {'takes': takes, 'prosody': 1.5 + i}}))
        files.append(str(f))
    d = {'voice_policy': 19, 'audio_engine': 'qwen', 'idea': {'participants': [{'name': 'Tim', 'voice': 'a'}, {'name': 'Oma', 'voice': 'b', 'library_voice': 'x'}]},
         'voice_profiles': {'Tim': {'file': 't.ref19.wav', 'source': 'upload', 'reference': {'cleaned': True, 'mode': 'x-vector', 'steps': ['highpass', 'afftdn', 'level'],
                                                                                              'gain_db': 18.2, 'lufs_before': -38.1, 'lufs_after': -20.0, 'snr_before': 31.9,
                                                                                              'snr_after': 46.8, 'warnings': []},
                                    'speech': {'mode': 'x-vector', 'emotions': ['angry'], 'performed': ['angry']}},
                            'Oma': {'file': 'o.wav', 'source': 'upload', 'voice_text': 'Na endlich', 'reference': {'cleaned': False, 'mode': 'icl', 'notes': []}},
                            'Gary': {'file': 'g.wav', 'source': 'designed', 'emotion_profiles': {'joy': {}}}},
         'lines': [{'speaker': 'Tim', 'emotion': 'wütend', 'file': files[0]}, {'speaker': 'Tim', 'emotion': 'ruhig', 'file': files[1]},
                   {'speaker': 'Oma', 'emotion': 'begeistert', 'file': files[2]}]}
    diag.voices(d); out = capsys.readouterr().out
    assert 'Stimmen: Stimmregel 19 | Sprachmodell qwen' in out
    assert ('Tim: Aufnahme, Modus ohne Text (x-vector), gereinigt ja (highpass, afftdn, level, +18.2 dB, -38.1 -> -20.0 LUFS, SNR 31.9 -> 46.8 dB), '
            'Gefühls-Referenzen angry (aus der Aufnahme gespielt: angry), Zeilen 2, Takes 2–3, Lebendigkeit 2.00, Sprechhaltung wütend 1, ruhig 1') in out
    assert 'Oma: Aufnahme aus deinen Figuren, Modus mit Text (ICL), gereinigt nein (nicht reinigbar), Gefühls-Referenzen keine, Zeilen 1, Takes 3–3' in out
    assert 'Gary: vom Studio gestaltet, Modus ohne Text (x-vector), gereinigt nicht nötig, Gefühls-Referenzen joy, Zeilen 0, Takes -' in out


# --- (2) own-script lines without a delivery: one from the text, punctuation reaches the voice model ---------------
DERIVED = {'Ich hab nichts gemacht!': 'genervt', 'Wir haben es geschafft!': 'begeistert', 'Hilfe! Da ist ein Hai!': 'panisch', 'Raus aus meiner Küche!': 'wütend',
           'Was?! Das glaub ich nicht.': 'überrascht', 'Echt!? Du auch?': 'überrascht', 'NEIN! NIEMALS! HÖRST DU?': 'schreiend',
           'Nein!! Das nicht.': 'schreiend', 'Wer war es dann?': 'verwirrt', 'Ich weiß nicht…': 'ängstlich',
           'Ich... ich hab doch... nur kurz geschaut.': 'ängstlich', 'Na gut, dann eben nicht.': 'ruhig', 'Das FBI kommt gleich.': 'ruhig'}


def test_a_delivery_from_the_text_for_lines_written_without_one():
    import screenplay
    import tts_text
    for text, mood in DERIVED.items():
        assert tts_text.delivery(text) == mood, text
        assert mood in screenplay.EMOTIONS
    assert performance_key(tts_text.delivery('Super, komm mit!')) == 'excited' and performance_key(tts_text.delivery('Wer?')) == 'confused'


OWN = '''# Kuchen
### Szene 1 – Küche – Oma steht am leeren Teller
OMA: Wer hat meinen Kuchen gegessen?
TIM: Ich war's nicht!
OMA (ruhig): Komm sofort her!
TIM (quer gestreift): Na gut.
OMA: Was?! Das ist doch nicht dein Ernst… Wirklich…
TIM (zu Oma): Ich... ich hab doch nur probiert...
OMA: Dann gibt es heute eben keinen Nachtisch mehr für dich, mein Lieber.
'''


def test_own_script_lines_without_a_delivery_get_one_and_a_written_one_wins():
    import own_script
    import screenplay
    def moods(policy):
        r = own_script.read(OWN, policy)
        lines = [l for l in screenplay.parse(r['episodes'][0]['text'], ['Oma', 'Tim'], own=bool(policy))[2] if l['kind'] == 'line']
        return r, [(l['text'], l['emotion']) for l in lines]
    r, new = moods(own_script.POLICY)
    assert [m for _, m in new] == ['verwirrt', 'genervt', 'ruhig', 'ruhig', 'überrascht', 'ängstlich', 'ruhig']
    assert r['report']['delivery'] == {'written': 2, 'derived': 4, 'calm': 1}
    assert any('Sprechhaltung „quer gestreift“ kennt das Studio nicht' in p['text'] for p in r['problems'])
    old_r, old = moods(0)                                                        # projects from before 0.19: as before
    assert [m for _, m in old] == ['ruhig'] * 7 and 'report' not in old_r
    assert [t for t, _ in new] == [t for t, _ in old]                            # the words never change


def test_punctuation_reaches_the_voice_model(tmp_path):
    import own_script
    import screenplay
    import tts_text
    r = own_script.read(OWN)
    lines = [l for l in screenplay.parse(r['episodes'][0]['text'], ['Oma', 'Tim'], own=True)[2] if l['kind'] == 'line']
    job = tts_text.job_fields({'sound_policy': 19}, lines, [{'name': 'Oma'}, {'name': 'Tim'}])
    said = [tts_text.spoken(l, job) for l in lines]
    assert said[0].endswith('?') and said[1].endswith('!') and said[4] == 'Was?! Das ist doch nicht dein Ernst… Wirklich…'
    assert said[5] == 'Ich... ich hab doch nur probiert...'
    # And through the planned project: quality_voices hands the same text and the derived delivery to the speech job.
    scenes = [{'kind': 'line', 'cast': ['Oma'], 'seconds': 4, 'dialogues': [{'speaker': l['speaker'], 'text': l['text'], 'emotion': l['emotion']}]}
              for l in lines[:2]]
    from factory_quality import Quality
    d = project({'sound_policy': 19}); d['episodes'][0]['scenes'] = scenes
    d['idea']['participants'] = [{'name': 'Oma', 'voice': 'a'}, {'name': 'Tim', 'voice': 'b'}]; d['plan']['cast'] = [{'name': 'Oma'}, {'name': 'Tim'}]
    studio = Speaking(tmp_path / 'p'); asyncio.run(Quality.quality_voices(studio, d))
    job = studio.jobs[-1]
    assert [(l['text'], l['emotion']) for l in job['lines']] == [('Wer hat meinen Kuchen gegessen?', 'verwirrt'), ("Ich war's nicht!", 'genervt')]
    assert [tts_text.spoken(l, job) for l in job['lines']] == ['Wer hat meinen Kuchen gegessen?', "Ich war's nicht!"]
