"""0.19 script and dialogue (diagnosis r019, area 'Drehbuch und Dialog', complaints C1 and C2).

C1: a word in capitals ('DIR') reached Qwen3-TTS / Chatterbox as written and was spelled D-I-R.
Projects created with sound_policy 19 hand the voice model tts_text.speakable(text); initialisms
(USA, FBI, PC, KI, OK, LKW …) stay, subtitles keep the writer's text, and a project without the pin
gets exactly the job, text and cache signature it got before."""
import asyncio
import contextlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import studio_fakes  # noqa: E402,F401  (puts cay_studio_app on the path)
import voice_fakes as vf  # noqa: E402
import tts_text  # noqa: E402

VOCAB = tts_text.vocabulary(['Wer hat meinen Kuchen gegessen?', 'Der Koffer bleibt zu.'], ['SpongeBob', 'Patrick', 'Mr. Krabs'])
CAPS = [('Ich sag es DIR zum letzten Mal!', 'Ich sag es dir zum letzten Mal!'),
        ('NIE wieder, hörst du? NIE!', 'Nie wieder, hörst du? Nie!'),
        ('JETZT oder nie.', 'Jetzt oder nie.'),
        ('WER HAT MEINEN KUCHEN GEGESSEN?!', 'Wer hat meinen Kuchen gegessen?!'),
        ('Aber NIEMAND öffnet den KOFFER!', 'Aber niemand öffnet den Koffer!'),
        ('GELD. JETZT. SOFORT.', 'Geld. Jetzt. Sofort.'),
        ('PATRICK, HILF MIR!', 'Patrick, hilf mir!'),
        ('SPONGEBOB! Komm sofort her!', 'SpongeBob! Komm sofort her!'),
        ('Mr. KRABS zahlt fünfhundert.', 'Mr. Krabs zahlt fünfhundert.'),
        ('Das ist eine ENTSCHEIDUNG!', 'Das ist eine Entscheidung!'),
        ('ÄRGER gibt es GROß!', 'Ärger gibt es groß!'),
        ('ICH? Niemals.', 'Ich? Niemals.'),
        ('NEEEIN!', 'Neeein!'),
        ("WAR'S das?", "War's das?"),
        ('PSST! Hier drüben.', 'Psst! Hier drüben.'),
        ('Ein UFO über der NASA.', 'Ein Ufo über der Nasa.'),
        # Initialisms stay exactly as written.
        ('Die USA, das FBI und die CIA suchen dich.', 'Die USA, das FBI und die CIA suchen dich.'),
        ('Mach den PC und den TV aus, DJ!', 'Mach den PC und den TV aus, DJ!'),
        ('OK, die KI ist schuld.', 'OK, die KI ist schuld.'),
        ('Der CEO ist ein VIP, sein GPS kaputt.', 'Der CEO ist ein VIP, sein GPS kaputt.'),
        ('Die DNA, eine SMS, das WLAN, der LKW und der PKW.', 'Die DNA, eine SMS, das WLAN, der LKW und der PKW.'),
        ('Ludwig XIV und sein MP3-Player.', 'Ludwig XIV und sein MP3-Player.'),
        # Emoji and emphasis marks go, no word changes.
        ('Kokain. 😏', 'Kokain.'),
        ('Das ist *wirklich* wichtig.', 'Das ist wirklich wichtig.'),
        ('Wo ist mein Geld?', 'Wo ist mein Geld?')]


@pytest.mark.parametrize('written,spoken', CAPS)
def test_capitals_are_spoken_as_words_and_initialisms_stay(written, spoken):
    assert tts_text.speakable(written, VOCAB) == spoken
    # Not a single word added, removed or moved.
    assert [w.lower() for w in tts_text.LETTERS.findall(spoken)] == [w.lower() for w in tts_text.LETTERS.findall(written)]


def test_a_word_seen_only_at_a_sentence_start_says_nothing_about_its_casing():
    vocab = tts_text.vocabulary(['Nie wieder sag ich das.', 'Komm her, Patrick.'], ['Patrick'])
    assert 'nie' not in vocab and vocab['patrick'] == 'Patrick'
    assert tts_text.speakable('Das sag ich NIE.', vocab) == 'Das sag ich nie.'


def test_only_pinned_projects_get_the_spoken_text_in_their_speech_job():
    lines = [{'text': 'Das ist MEIN Geld!'}]
    assert tts_text.job_fields({}, lines, []) == {} and tts_text.job_fields({'sound_policy': 18}, lines, []) == {}
    fields = tts_text.job_fields({'sound_policy': 19}, lines, [{'name': 'Mr. Krabs'}])
    assert fields['speech_text'] == 19 and fields['vocabulary']['krabs'] == 'Krabs'
    line = {'text': 'Das ist MEIN Geld!'}
    assert tts_text.spoken(line, {}) == 'Das ist MEIN Geld!' and tts_text.signature_fields(line, {}) == {}
    assert tts_text.spoken(line, fields) == 'Das ist mein Geld!' and tts_text.signature_fields(line, fields) == {'spoken': 'Das ist mein Geld!'}
    # A line without capitals reads the same and keeps its signature under the pin as well.
    assert tts_text.signature_fields({'text': 'Wo ist mein Geld?'}, fields) == {}


def caps_lines():
    lines = [dict(line) for line in vf.LINES]
    lines[0].update(text='Wo ist MEIN Geld geblieben?', text_de='Wo ist MEIN Geld geblieben?')
    return lines


@pytest.mark.parametrize('engine', ['factory_speech', 'factory_tts'])
def test_the_speech_adapters_read_the_spoken_text_only_with_the_flag(tmp_path, monkeypatch, engine):
    """Both adapters with fake models: without the flag the model gets the written text and every file
    name (cache signature) is the one of the unchanged formula; with it only the line in capitals
    differs, and the result keeps the written text for the subtitles."""
    vf.install(monkeypatch)
    calls = []
    if engine == 'factory_tts':
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
                calls.append(text); return Wave(vf.take(text))
        chatterbox = type(sys)('chatterbox'); mtl = type(sys)('chatterbox.mtl_tts'); mtl.ChatterboxMultilingualTTS = Model
        monkeypatch.setitem(sys.modules, 'chatterbox', chatterbox); monkeypatch.setitem(sys.modules, 'chatterbox.mtl_tts', mtl)
        monkeypatch.setattr(sys.modules['torch'], 'cuda', type('C', (), {'is_available': staticmethod(lambda: True)}), raising=False)
    module = vf.load(ROOT / 'cay_studio_app', engine)
    root = vf.base_dir(tmp_path)
    if engine == 'factory_tts': monkeypatch.setattr(module, 'checkpoint', lambda base: tmp_path)
    voice = tmp_path / 'voice.wav'; vf.write_wav(voice, vf.take('Stimme'), vf.RATE)
    import hashlib
    sha = hashlib.sha256(voice.read_bytes()).hexdigest()
    cast = [{'name': p['name'], 'voice_file': str(voice), 'voice_hash': sha, 'voice_text': ''} for p in vf.CAST]

    def run(flag, out):
        job = {'cast': cast, 'lines': caps_lines(), 'voice_policy': 18, 'output': str(tmp_path / out)}
        if flag: job.update(tts_text.job_fields({'sound_policy': 19}, job['lines'], vf.CAST))
        (tmp_path / f'{out}.json').write_text(json.dumps(job))
        vf.Model.calls = []; calls.clear()
        if engine == 'factory_speech': module.generate(root, tmp_path / f'{out}.json')
        else:
            monkeypatch.setattr(sys, 'argv', ['factory_tts.py', '--base', str(root), '--job', str(tmp_path / f'{out}.json')]); module.main()
        said = [c[1]['text'] for c in vf.Model.calls if c[0] == 'clone'] if engine == 'factory_speech' else list(calls)
        result = json.loads((tmp_path / out / 'Ergebnis.json').read_text())['lines']
        return said, [Path(l['file']).name for l in result], result

    old_said, old_files, old_result = run(False, 'old')
    new_said, new_files, new_result = run(True, 'new')
    # (an emotional line gets two takes: the same text twice)
    assert {t for t in old_said if 'Geld' in t} == {'Wo ist MEIN Geld geblieben?'} and {t for t in new_said if 'Geld' in t} == {'Wo ist mein Geld geblieben?'}
    assert [t for t in old_said if 'Geld' not in t] == [t for t in new_said if 'Geld' not in t]
    assert old_files[0] != new_files[0] and old_files[1:] == new_files[1:]
    assert new_result[0]['text'] == new_result[0]['text_de'] == 'Wo ist MEIN Geld geblieben?'
    # The old signature formula, recomputed: a project without the pin keeps every cached line.
    if engine == 'factory_speech':
        identity = (root / 'models/studio-voices/Base/source.json').read_text()
        line = caps_lines()[0]
        signature = hashlib.sha256(json.dumps({'line': line, 'voice': sha, 'ref_text': '', 'model': identity, 'processing': module.SPEECH_POLICY,
                                               'engine': 'qwen-base-17-takes'}, sort_keys=True).encode()).hexdigest()
        assert old_files[0] == line['key'] + '_' + signature[:12] + '.wav'


class Speaking:
    """Quality.quality_voices() with a fake speech run: records the speech job."""
    def __init__(self, folder):
        self.posts = []; self.jobs = []; self.base = folder / 'base'; self.g = {}; self.folder_path = folder
        (self.base / 'envs/chatterbox/bin').mkdir(parents=True); (self.base / 'envs/chatterbox/bin/python').write_text('')
    def apply_pending(self, d): return False
    def paused(self, rid): return False
    def save(self, d): pass
    def folder(self, d): return self.folder_path
    def asset(self, aid, kind=None): return {'path': str(self.folder_path.parent / 'voice.wav'), 'sha256': 'x' * 64}
    def queue_post(self, d, kind, ei, spec): self.posts.append(spec)
    def atomic(self, path, data): Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_bytes(data)
    async def idle(self, client, wait): pass
    def measured(self, d, stage): return contextlib.nullcontext()
    async def command(self, args, timeout):
        args = [str(a) for a in args]; job = json.loads(Path(args[args.index('--job') + 1]).read_text()); self.jobs.append(job)
        out = Path(job['output']); out.mkdir(parents=True, exist_ok=True)
        (out / 'Ergebnis.json').write_text(json.dumps({'lines': [{**l, 'file': 'x.wav', 'duration': 1.5, 'sha256': 'y'} for l in job['lines']]}))


def test_the_speech_job_carries_the_flag_only_for_new_projects(tmp_path):
    from factory_quality import Quality
    jobs = {}
    for pin in ({}, {'sound_policy': 19}):
        folder = tmp_path / str(bool(pin)); folder.mkdir()
        scenes = [{'kind': 'line', 'cast': ['Tim'], 'seconds': 4, 'dialogues': [{'speaker': 'Tim', 'text': 'Das ist MEIN Kuchen, OMA!', 'emotion': 'wütend'}]},
                  {'kind': 'line', 'cast': ['Oma'], 'seconds': 4, 'dialogues': [{'speaker': 'Oma', 'text': 'Dann iss ihn doch, Tim.', 'emotion': 'ruhig'}]}]
        d = {'id': 'v' * 32, 'idea': {'duration': 15, 'episodes': 1, 'fps': 25, 'lip_sync': 'audio', 'speech_engine': 'chatterbox',
                                      'participants': [{'name': 'Tim', 'voice': 'a'}, {'name': 'Oma', 'voice': 'b'}]},
             'plan': {'cast': [{'name': 'Tim'}, {'name': 'Oma'}], 'mood': 'playful'}, 'episodes': [{'scenes': scenes, 'dialogue_mode': 'rich'}], **pin}
        studio = Speaking(folder); asyncio.run(Quality.quality_voices(studio, d)); jobs[bool(pin)], = studio.jobs
        assert [l['text'] for l in d['lines']] == ['Das ist MEIN Kuchen, OMA!', 'Dann iss ihn doch, Tim.']      # captions as written
    old, new = jobs[False], jobs[True]
    assert set(old) == {'cast', 'lines', 'voice_policy', 'output'}
    assert {k: v for k, v in new.items() if k not in ('speech_text', 'vocabulary', 'output')} == {k: v for k, v in old.items() if k != 'output'}
    assert new['speech_text'] == 19 and tts_text.spoken(new['lines'][0], new) == 'Das ist mein Kuchen, Oma!'


# --- C2, AI mode: writing policy 15 (only for ideas with 'writing': 19, sent by the new app) -------------------
import screenplay as sp  # noqa: E402
import plan_fakes  # noqa: E402

WEAK = '''TITEL: Der Koffer
# 1 | Hafen | Nebel über dem Hafen
AKTION: Patrick schleppt eine schwere Kiste über den Steg.
AKTION: SpongeBob schaut sich nervös nach allen Seiten um.
SPONGEBOB [ruhig]: Patrick, wir sollten den Koffer zu Mr. Krabs bringen, sofort.
PATRICK [ruhig]: SpongeBob, ich weiß, dass wir den Koffer zu Mr. Krabs bringen sollen.
SPONGEBOB [ruhig]: Patrick, dann lass uns jetzt den Koffer zu Mr. Krabs bringen.
PATRICK [ruhig]: SpongeBob, ja, wir bringen jetzt den Koffer zu Mr. Krabs, okay.
# 2 | Krusty Krab | Büro
AKTION: Mr. Krabs zählt Geld.
AKTION: SpongeBob stellt den Koffer auf den Tisch.
MR. KRABS [ruhig]: SpongeBob, Patrick, danke, dass ihr den Koffer gebracht habt.
SPONGEBOB [ruhig]: Mr. Krabs, gern geschehen, wir haben den Koffer gerne gebracht.
MR. KRABS [ruhig]: SpongeBob, ich gebe euch jetzt fünfhundert Dollar für den Koffer.
PATRICK [ruhig]: Mr. Krabs, danke für die fünfhundert Dollar für den Koffer, wirklich.
MR. KRABS [ruhig]: Patrick, gern, und jetzt geht bitte wieder an die Arbeit, ihr zwei.
SPONGEBOB [ruhig]: Mr. Krabs, ja, wir gehen jetzt wieder an die Arbeit, versprochen.
PATRICK [ruhig]: SpongeBob, dann gehen wir jetzt wieder an die Arbeit, komm mit.
MR. KRABS [ruhig]: Patrick, SpongeBob, gut so, bis morgen dann, ihr beiden.
'''
WEAK_CAST = ['SpongeBob', 'Patrick', 'Mr. Krabs']


def test_the_word_budget_of_policy_15_fits_the_chosen_length():
    assert sp.budget(60, 2, 15) == {'words': 98, 'min_words': 86, 'max_words': 110, 'min_turns': 6, 'max_turns': 15, 'min_actions': 2, 'max_actions': 4}
    assert sp.budget(90, 2, 15)['words'] == 147 and sp.budget(90, 2, 15)['max_words'] == 165
    # Policy 14 (every project without the field) keeps its budget.
    assert sp.budget(60, 2) == {'words': 120, 'min_words': 102, 'max_words': 156, 'min_turns': 6, 'max_turns': 15, 'min_actions': 2, 'max_actions': 5}


def test_the_doctor_check_of_policy_15_finds_what_counting_missed():
    title, beats, lines, problems = sp.parse(WEAK, WEAK_CAST)
    assert sp.check(title, beats, lines, problems, WEAK_CAST, 60) == []            # policy 14: nothing to fix
    found = ' | '.join(sp.check(title, beats, lines, problems, WEAK_CAST, 60, 15))
    for part in ('Zu viel Dialog: 127 Wörter, höchstens 110', 'Die erste Zeile ist gesprochen', '2x zwei AKTION-Zeilen hintereinander',
                 'Kein Konflikt hörbar', 'Zu gleichförmig: 12 von 12 Zeilen "ruhig"', '12 von 12 Zeilen beginnen mit dem Namen',
                 'Wiederholungen statt Entwicklung', 'Zu lange ohne Wort: etwa 6.7 s'):
        assert part in found, (part, found)
    # The prompt's own crime example passes; Cay's 0.17 lines in capitals and a first line without a hook do not.
    crime = sp.EXAMPLE_V15.split('nicht übernehmen):\n')[-1]
    title, beats, lines, problems = sp.parse(crime, ['Boss', 'Kurier'])
    assert not problems and sp.check15(lines, ['Boss', 'Kurier'], 20, sp.ensure_action(sp.shots(title, beats, lines, ['Boss', 'Kurier'], 15), 20)) == []
    import cut_samples as cs
    text, cast = cs.TEXTS['cay_pingpong']; title, beats, lines, _ = sp.parse(text, cast)
    assert any(e.startswith('Keine Wörter in Großbuchstaben zur Betonung: MEIN, PLANKTON, UNSER, DU, ZURÜCK')
               for e in sp.check15(lines, cast, 60, sp.shots(title, beats, lines, cast, 15)))
    text, cast = cs.TEXTS['cay_blocks']; title, beats, lines, _ = sp.parse(text, cast)
    assert any(e.startswith('Der erste Satz hat keinen Haken') for e in sp.check15(lines, cast, 60, sp.shots(title, beats, lines, cast, 15)))


def test_policy_15_sets_no_wide_shot_right_after_a_silent_shot():
    text = sp.EXAMPLE_BLOCKS.split('\n', 1)[1]; cast = ['Oma', 'Tim', 'Opa']
    title, beats, lines, _ = sp.parse(text, cast)
    kinds = lambda policy: [s['kind'] for s in sp.shots(title, beats, lines, cast, policy)]
    assert 'establish' in kinds(14) and kinds(14)[kinds(14).index('establish') - 1] == 'action'      # 0.18: 5.6 s without a word
    assert 'establish' not in kinds(15) and [k for k in kinds(14) if k != 'establish'] == kinds(15)
    assert sp.estimate(sp.shots(title, beats, lines, cast, 15))[2] < sp.estimate(sp.shots(title, beats, lines, cast, 14))[2]


def test_only_an_idea_with_the_field_plans_with_policy_15(tmp_path, monkeypatch):
    body = {'request_key': 'f' * 32, 'idea': 'Lena und Markus streiten um den letzten Keks im Büro.', 'duration': 60, 'episodes': 1,
            'characters': 'provided', 'participants': [{'name': 'Lena', 'traits': 'Projektleiterin'}, {'name': 'Markus', 'traits': 'Praktikant'}]}
    f = studio_fakes.factory(tmp_path, monkeypatch); client = studio_fakes.client(f)
    d, planner = plan_fakes.plan(f, client, {**body, 'writing': 19})
    assert d['idea']['writing'] == 19 and d['screenplays']['0']['policy'] == 15 and d['episodes'][0]['story_policy'] == 15
    writes = [c for c in planner.calls if c[0] == 'write']
    assert 'Die erste Zeile ist gesprochen und ein Haken' in writes[0][2] and 'Gesamt 86 bis 110 gesprochene Wörter' in writes[0][2]
    assert 'pruefung' in writes[1][3] and 'Ist der erste Satz ein Haken?' in writes[1][2]
    # An explicit 0 (or no field) is stored like no field at all: policy 14 and the recorded 0.18 plan (test_own_script).
    case = tmp_path / 'zero'; case.mkdir(); f = studio_fakes.factory(case, monkeypatch); client = studio_fakes.client(f)
    d, planner = plan_fakes.plan(f, client, {**body, 'request_key': 'e' * 32, 'writing': 0})
    assert 'writing' not in d['idea'] and d['screenplays']['0']['policy'] == 14
    first = next(c for c in planner.calls if c[0] == 'write' and c[1] == 'Drehbuch')
    assert sp.RULES_BLOCKS in first[2] and 'Die erste Zeile ist gesprochen und ein Haken' not in first[2]
