"""'Mein Drehbuch' (0.18): Cay pastes or uploads his own script (.md or .txt) and the studio films it
word for word. The script is read without any model (own_script.read); planning takes the cast, the
episodes and every spoken line from it and only lets the planner write picture and motion text.

Proves: a realistic German series script (Folge headings, moods in brackets and parentheses, AKTION
lines in three spellings, FIGUR lines, umlauts, 'Frau Müller') is read word for word; the lines a
planned project voices are exactly the script's lines in order; no model is asked to write or doctor
dialogue; an idea without the new field plans exactly as at git 6ac0794 (recorded reference)."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import studio_fakes  # noqa: E402  (puts cay_studio_app on the path)
import plan_fakes  # noqa: E402
import own_script  # noqa: E402
import screenplay  # noqa: E402
from factory_audio import turns  # noqa: E402

SCRIPT = '''# Der Kuchenklau von Hausnummer 7

## Figuren
FIGUR: Oma Hilde – 72 Jahre, graue Dutt-Frisur, geblümte Schürze, streng, aber herzlich
FIGUR: Frau Müller – Nachbarin, Mitte fünfzig, roter Mantel, neugierig und spitzzüngig
- Tim: 9 Jahre, Sommersprossen, rote Kappe, frech

## Folge 1: Der leere Teller

### Szene 1 – Küche – Oma steht vor einem leeren Kuchenteller, Krümel auf dem Boden
OMA HILDE (wütend): Wer hat meinen Kuchen gegessen? Ich zähl bis drei!
TIM [ängstlich]: Ich war's nicht, ehrlich! Ich war die ganze Zeit … im Bad.
Oma Hilde: (spöttisch) „Im Bad. Mit Sahne an der Nase?“
AKTION: Tim wischt sich hastig die Nase und versteckt die Hände hinter dem Rücken.
TIM (kleinlaut): Okay, okay. Vielleicht war es nur ein ganz kleines Stück.

### Szene 2 – Hausflur – Frau Müller lauscht an der offenen Tür
FRAU MÜLLER (neugierig): Hilde, ist alles in Ordnung? Ich hab Geschrei gehört!
OMA HILDE (genervt): Alles bestens, Frau Müller. Nur ein kleiner Kuchendieb.
[Aktion: Frau Müller hebt eine Augenbraue und mustert Tim von oben bis unten.]
FRAU MÜLLER (gelangweilt): Bei mir fehlt übrigens auch ein Stück Apfelstrudel.

## Folge 2: Die Spur der Krümel

### Szene 1 – Garten – Krümel führen zum Gartenhaus
TIM (aufgeregt): Oma, guck mal! Die Krümel führen direkt zum Gartenhaus!
OMA HILDE (überrascht): Tatsächlich. Und da drin brennt Licht.
Aktion: Die Tür des Gartenhauses knarrt langsam auf.
FRAU MÜLLER (flüsternd): Ich wusste es. Da wohnt jemand Fremdes!
TIM (begeistert): Ein echter Kuchenräuber! Wir müssen ihn schnappen!
OMA HILDE (drohend): Wer auch immer da drin ist: Komm sofort raus!
'''

# (speaker, spoken text exactly as written, mood) per episode, in script order.
LINES = [[('Oma Hilde', 'Wer hat meinen Kuchen gegessen? Ich zähl bis drei!', 'wütend'),
          ('Tim', "Ich war's nicht, ehrlich! Ich war die ganze Zeit … im Bad.", 'ängstlich'),
          ('Oma Hilde', 'Im Bad. Mit Sahne an der Nase?', 'spöttisch'),
          ('Tim', 'Okay, okay. Vielleicht war es nur ein ganz kleines Stück.', 'ängstlich'),
          ('Frau Müller', 'Hilde, ist alles in Ordnung? Ich hab Geschrei gehört!', 'überrascht'),
          ('Oma Hilde', 'Alles bestens, Frau Müller. Nur ein kleiner Kuchendieb.', 'genervt'),
          ('Frau Müller', 'Bei mir fehlt übrigens auch ein Stück Apfelstrudel.', 'genervt')],
         [('Tim', 'Oma, guck mal! Die Krümel führen direkt zum Gartenhaus!', 'begeistert'),
          ('Oma Hilde', 'Tatsächlich. Und da drin brennt Licht.', 'überrascht'),
          ('Frau Müller', 'Ich wusste es. Da wohnt jemand Fremdes!', 'flüsternd'),
          ('Tim', 'Ein echter Kuchenräuber! Wir müssen ihn schnappen!', 'begeistert'),
          ('Oma Hilde', 'Wer auch immer da drin ist: Komm sofort raus!', 'drohend')]]
ACTIONS = [['Tim wischt sich hastig die Nase und versteckt die Hände hinter dem Rücken.',
            'Frau Müller hebt eine Augenbraue und mustert Tim von oben bis unten.'],
           ['Die Tür des Gartenhauses knarrt langsam auf.']]
NAMES = ['Oma Hilde', 'Frau Müller', 'Tim']


def parsed(text, names=NAMES):
    title, beats, lines, problems = screenplay.parse(text, names)
    assert not problems
    return title, beats, lines


def test_realistic_script_is_read_word_for_word():
    r = own_script.read(SCRIPT)
    assert r['ok'] and not [p for p in r['problems'] if p['blocking']], r['problems']
    assert r['title'] == 'Der Kuchenklau von Hausnummer 7' and r['series']
    assert [f['name'] for f in r['figures']] == NAMES
    assert r['figures'][1]['description'] == 'Nachbarin, Mitte fünfzig, roter Mantel, neugierig und spitzzüngig'
    assert r['figures'][2]['description'] == '9 Jahre, Sommersprossen, rote Kappe, frech'
    assert [e['title'] for e in r['episodes']] == ['Der leere Teller', 'Die Spur der Krümel']
    for ep, spoken, actions in zip(r['episodes'], LINES, ACTIONS):
        title, beats, lines = parsed(ep['text'])
        assert title == ep['title']
        assert [(l['speaker'], l['text'], l['emotion']) for l in lines if l['kind'] == 'line'] == spoken
        assert [l['text'] for l in lines if l['kind'] == 'action'] == actions
        assert ep['lines'] == len(spoken) and ep['speakers'] == list(dict.fromkeys(s for s, _, _ in spoken))
    beats = parsed(r['episodes'][0]['text'])[1]
    assert beats == [{'place': 'Küche', 'what': 'Oma steht vor einem leeren Kuchenteller, Krümel auf dem Boden'},
                     {'place': 'Hausflur', 'what': 'Frau Müller lauscht an der offenen Tür'}]
    # Length from the script itself: about 35 s and 19 s; planned with a little less as the minimum.
    assert [e['seconds'] for e in r['episodes']] == [35, 19] and r['duration'] == 17
    assert r['words'] == 100 and r['lines'] == 12 and r['scenes'] == 3


def test_moods_map_to_the_nearest_emotion_and_default_to_calm():
    assert own_script.emotion_for('wütend') == ('wütend', True)
    assert own_script.emotion_for('sehr verärgert und laut')[0] == 'wütend'
    assert own_script.emotion_for('flüstert')[0] == 'flüsternd' and own_script.emotion_for('leise')[0] == 'flüsternd'
    assert own_script.emotion_for('wuetend')[0] == 'wütend' and own_script.emotion_for('lachend')[0] == 'fröhlich'
    assert own_script.emotion_for('kleinlaut')[0] == 'ängstlich' and own_script.emotion_for('schreit')[0] == 'schreiend'
    assert own_script.emotion_for('quer gestreift') == ('ruhig', False)
    r = own_script.read('### Szene 1 – Büro\nLENA (quer gestreift): Hallo Markus, schön dich zu sehen heute Morgen.\n'
                        'MARKUS: Hallo Lena, gleichfalls, wie war denn dein Wochenende so?\n' * 3)
    assert any('Sprechhaltung „quer gestreift“ kennt das Studio nicht, gesprochen wird „ruhig“' in p['text'] for p in r['problems'])
    assert all(e in screenplay.EMOTIONS for e in parsed(r['episodes'][0]['text'], ['Lena', 'Markus'])[2] for e in [e['emotion']])


def test_the_internal_format_reads_back_unchanged():
    from test_screenplay_timing import GOOD, CAST
    text = ''.join(f'FIGUR: {n}\n' for n in CAST) + GOOD
    r = own_script.read(text)
    assert r['ok'] and [f['name'] for f in r['figures']] == CAST and r['title'] == 'Der Einbruch im Krusty-Versteck'
    original = screenplay.parse(GOOD, CAST)[2]; mine = parsed(r['episodes'][0]['text'], CAST)[2]
    assert [(l['kind'], l['speaker'], l['text'], l['emotion']) for l in mine] == [(l['kind'], l['speaker'], l['text'], l['emotion']) for l in original]


def test_screenplay_style_cues_prose_and_stage_directions():
    text = '''Titel: Der Einbruch

Eine kleine Komödie in einer Bäckerei.

INNEN. BÄCKEREI – NACHT
Es ist dunkel, nur die Kühltheke leuchtet.

MAX
(flüsternd)
Pssst! Hier drüben ist der Tresor.
Mach bloß keinen Lärm.

LENA
Ich mach doch gar nichts!

Lena stolpert über einen Mehlsack. Eine weiße Wolke steigt auf.

MAX (panisch): Lena! Das ganze Mehl!
Plötzlich: Das Licht geht an.
KAMERA: Nahaufnahme auf den Lichtschalter.
MUSIK: Spannende Musik
Herr Bäcker [wütend]: Was ist denn hier los?
Herr Bäcker (sehr verärgert und laut): Ihr zwei schon wieder! **Raus** aus meiner Backstube!
MAX: (nickt)
Erzähler: Und so endete ihre Karriere als Einbrecher.
ENDE
'''
    r = own_script.read(text)
    names = [f['name'] for f in r['figures']]
    assert r['ok'] and names == ['Max', 'Lena', 'Herr Bäcker', 'Erzähler'] and r['title'] == 'Der Einbruch'
    title, beats, lines = parsed(r['episodes'][0]['text'], names)
    assert beats[0]['place'] == 'Bäckerei' and 'Kühltheke leuchtet' in beats[0]['what'] and 'Nahaufnahme' in beats[0]['what']
    assert [(l['kind'], l['speaker'], l['text'], l['emotion']) for l in lines] == [
        ('line', 'Max', 'Pssst! Hier drüben ist der Tresor. Mach bloß keinen Lärm.', 'flüsternd'),
        ('line', 'Lena', 'Ich mach doch gar nichts!', 'ruhig'),
        ('action', '', 'Lena stolpert über einen Mehlsack. Eine weiße Wolke steigt auf.', ''),
        ('line', 'Max', 'Lena! Das ganze Mehl!', 'panisch'),
        ('action', '', 'Plötzlich: Das Licht geht an.', ''),
        ('line', 'Herr Bäcker', 'Was ist denn hier los?', 'wütend'),
        ('line', 'Herr Bäcker', 'Ihr zwei schon wieder! Raus aus meiner Backstube!', 'wütend'),
        ('action', '', 'Max nickt', ''),
        ('line', 'Erzähler', 'Und so endete ihre Karriere als Einbrecher.', 'ruhig')]
    texts = ' '.join(p['text'] for p in r['problems'])
    assert 'Zeile 21: Musik-Angaben setzt das Studio selbst' in texts and '„Erzähler“ ist im Film eine sichtbare Figur' in texts
    assert 'Eine kleine Komödie' in r['episodes'][0]['plot']


def test_problems_carry_line_numbers_and_block_the_film():
    def blocking(text): return [p['text'] for p in own_script.read(text)['problems'] if p['blocking']]
    long = '### Szene 1 – Büro – Lena und Markus am Kaffeeautomaten\n' + ''.join(
        f'{"LENA" if i % 2 else "MARKUS"} (ruhig): Das ist Satz Nummer {i}, und er hat ungefähr zwölf Wörter, damit es lang wird.\n' for i in range(24))
    assert not blocking(long)                                     # 24 long lines (~120 s): a hint, no stop
    assert any('höchstens 180 s gehen' in t and '## Folge 1' in t for t in blocking(long * 2))
    assert any('nur etwa' in t and 'mindestens 15 s' in t for t in blocking('LENA: Hallo!\nMARKUS: Hallo zurück!'))
    assert any('kein gesprochener Satz' in t for t in blocking('# Nur ein Titel\nEin bisschen Beschreibung ohne Sätze.'))
    before = blocking('# Serie\nLENA: Ich stehe zu früh im Text, noch vor jeder Folge hier.\n## Folge 1: Start\n' + long.split('\n', 1)[1][:400])
    assert any(t.startswith('Zeile 2: Der Satz steht vor „Folge 1“') for t in before)
    assert any('fortlaufend ab Folge 1' in t for t in blocking('## Folge 1\nLENA: Eins, zwei, drei, vier, fünf.\n## Folge 3\nLENA: Sechs, sieben, acht.'))
    r = own_script.read('# Titel\n## Küche\nLENA: Ein Satz.\nKRABS: Ein Satz.\nMR. KRABS: Noch ein Satz.')
    hints = ' '.join(p['text'] for p in r['problems'] if not p['blocking'])
    assert 'Zeile 2: Überschrift „Küche“ ist keine Folge und keine Szene' in hints
    assert '„Krabs“ und „Mr. Krabs“ sind zwei Figuren' in hints and 'Kein Ort angegeben' in hints
    # The check's findings read as advice, never as orders to rewrite.
    short = ' '.join(p['text'] for p in own_script.read('### Szene 1 – Küche\nLENA: Hallo Markus, schön dich zu sehen heute Morgen.\n'
                                                        'MARKUS: Hallo Lena, gleichfalls, wie war denn dein Wochenende so?')['problems'])
    assert 'Hinweis: Wenig Sprecherwechsel: 2, empfohlen sind mindestens 3.' in short and 'nötig' not in short and 'schreiben.' not in short
    # Blocking problems come first in the list the app shows.
    problems = own_script.read(long * 2 + '\nMUSIK: laut')['problems']
    assert problems[0]['blocking'] and not problems[-1]['blocking']


def test_a_very_long_line_is_split_without_changing_a_word():
    sentence = 'Das ist ein ziemlich langer Satz über den Kuchen, den Garten und die Nachbarin. '
    text = '### Szene 1 – Küche\nOMA (wütend): ' + sentence * 6 + '\nTIM: Okay, ich hab verstanden, Oma, ich sag ja nichts mehr dazu.'
    r = own_script.read(text)
    lines = parsed(r['episodes'][0]['text'], ['Oma', 'Tim'])[2]
    oma = [l['text'] for l in lines if l['speaker'] == 'Oma']
    assert len(oma) == 2 and all(len(t) <= own_script.MAX_SPOKEN for t in oma)
    assert ' '.join(oma).split() == (sentence * 6).split() and all(l['emotion'] == 'wütend' for l in lines if l['speaker'] == 'Oma')
    assert any('Zeile 2: Sehr langer Satz, in 2 Teile geteilt. Die Wörter bleiben gleich.' == p['text'] for p in r['problems'])


def test_prepare_takes_episodes_length_cast_and_title_from_the_script():
    idea = {'idea': SCRIPT, 'story': 'script', 'title': '', 'episodes': 1, 'duration': 60, 'characters': 'invent',
            'participants': [{'name': 'frau müller', 'traits': '', 'image': None, 'voice': None}]}
    script = own_script.prepare(idea)
    assert idea['episodes'] == 2 and idea['duration'] == 17 and idea['characters'] == 'provided'
    assert idea['title'] == 'Der Kuchenklau von Hausnummer 7' and idea['participants'][0]['name'] == 'Frau Müller'
    assert 'preview' not in script and [e['seconds'] for e in script['episodes']] == [35, 19]
    with pytest.raises(ValueError, match='„Opa“ kommt im Drehbuch nicht vor'):
        own_script.prepare({**idea, 'participants': [{'name': 'Opa'}]})
    with pytest.raises(ValueError, match='mindestens 15 s'):
        own_script.prepare({**idea, 'idea': 'LENA: Hallo!\nMARKUS: Hallo zurück!', 'participants': []})
    plain = {'idea': 'Zwei Kollegen streiten um einen Keks.', 'story': 'ai', 'episodes': 1}
    assert own_script.prepare(plain) is None and 'story' not in plain


def planned_lines(d):
    """The lines exactly as factory_quality.quality_voices hands them to the voices (d['lines'])."""
    return [[(l['speaker'], l['text'], l['emotion']) for sc in ep['scenes'] for l in turns(sc)] for ep in d['episodes']]


def test_a_script_project_plans_word_for_word_and_no_model_writes_dialogue(tmp_path, monkeypatch):
    f = studio_fakes.factory(tmp_path, monkeypatch); client = studio_fakes.client(f)
    d, planner = plan_fakes.plan(f, client, {'request_key': 'c' * 32, 'idea': SCRIPT, 'story': 'script', 'duration': 60, 'episodes': 1,
                                             'characters': 'provided', 'participants': [{'name': 'Tim', 'traits': ''}]}, write=False)
    assert d['state'] == 'pictures' and d['idea']['story'] == 'script' and d['title'] == 'Der Kuchenklau von Hausnummer 7'
    assert planned_lines(d) == LINES
    # No model writes or doctors dialogue, plans an outline, a story goal, a cast from the text or a story review.
    assert [c[0] for c in planner.calls] == ['llm'] * len(planner.calls)
    assert {c[1] for c in planner.calls} == {'SeriesHeader', 'ShotVisuals', 'SocialPost'}
    header = next(c for c in planner.calls if c[1] == 'SeriesHeader')
    assert header[2] == own_script.HEADER and [p['name'] for p in header[3]['participants']] == NAMES
    assert header[3]['participants'][0]['traits'] == '72 Jahre, graue Dutt-Frisur, geblümte Schürze, streng, aber herzlich'
    # The planner reads the whole script for the pictures; the shots list the script's own lines.
    visuals = [c for c in planner.calls if c[1] == 'ShotVisuals']
    assert [c[3]['drehbuch'] for c in visuals] == [e['text'] for e in d['script']['episodes']]
    assert 'Das vollständige Drehbuch steht in drehbuch' in visuals[0][2]
    # Titles and figures are the script's; the FIGUR text wins over the planner's personality.
    assert [e['title'] for e in d['episodes']] == ['Der leere Teller', 'Die Spur der Krümel'] and d['plan']['title'] == d['title']
    assert [p['name'] for p in d['plan']['cast']] == NAMES
    assert d['plan']['cast'][1]['personality'] == 'Nachbarin, Mitte fünfzig, roter Mantel, neugierig und spitzzüngig'
    # Silent shots are only the script's own AKTION lines (plus wide shots of a new place, without text).
    for ep, actions in zip(d['episodes'], ACTIONS):
        assert [s['action'] for s in ep['scenes'] if s['kind'] == 'action'] == actions
        assert all(not turns(s) for s in ep['scenes'] if s['kind'] in ('action', 'establish'))
        assert ep['own_script'] and ep['spine'] is None and ep['story_policy'] == screenplay.POLICY
    stores = d['screenplays']
    assert [stores[str(i)]['final'] for i in range(2)] == [e['text'] for e in d['script']['episodes']]
    assert all(s['own'] and 'draft' not in s and 'doctor_error' not in s for s in stores.values()) and 'spines' not in d


def test_a_long_script_film_without_aktion_gets_no_invented_action(tmp_path, monkeypatch):
    dialogue = ''.join(f'{"LENA (fröhlich)" if i % 2 else "MARKUS (genervt)"}: Das ist Satz {i} in unserem langen Gespräch über den letzten Keks im Büro.\n'
                       for i in range(14))
    text = '# Der letzte Keks\n### Szene 1 – Teeküche – Lena und Markus vor der leeren Keksdose\n' + dialogue
    f = studio_fakes.factory(tmp_path, monkeypatch); client = studio_fakes.client(f)
    d, planner = plan_fakes.plan(f, client, {'request_key': 'd' * 32, 'idea': text, 'story': 'script', 'characters': 'provided'}, write=False)
    assert d['idea']['duration'] >= 30          # ensure_action would add a silent reaction here for an AI script
    scenes = d['episodes'][0]['scenes']
    assert not any(s['kind'] == 'action' for s in scenes) and not any('reagiert stumm' in s['action'] for s in scenes)
    assert [t for _, t, _ in planned_lines(d)[0]] == [line.split(': ', 1)[1] for line in dialogue.strip().split('\n')]
    assert any(w.startswith('Hinweis zu deinem Drehbuch: Wenig AKTION-Zeilen: 0, empfohlen sind mindestens 2.') for w in d['episodes'][0].get('warnings', []))


def test_an_idea_without_the_new_field_plans_exactly_as_before(tmp_path, monkeypatch):
    """Recorded from git 6ac0794 with the same fake planner: every call (instruction and data) and
    the whole resulting plan must stay identical; the stored idea gets no new key."""
    reference = json.loads((ROOT / 'tests/fixtures/v18_ai_plan_reference.json').read_text(encoding='utf-8'))
    bodies = {'film_invent_30s': {'request_key': 'a' * 32, 'idea': 'Zwei Kollegen streiten um den letzten Keks. Am Ende hat ihn die Praktikantin.',
                                  'duration': 30, 'episodes': 1, 'look': 'clay', 'characters': 'invent', 'cover': 'start', 'autopilot': True, 'cast_check': True},
              'series_provided_classic': {'request_key': 'b' * 32, 'idea': 'Lena und Markus streiten in zwei Folgen um Kekse im Büro.', 'episodes': 2,
                                          'duration': 60, 'characters': 'provided',
                                          'participants': [{'name': 'Lena', 'traits': 'Projektleiterin'}, {'name': 'Markus', 'traits': 'Praktikant'}]}}
    for name, body in bodies.items():
        case = tmp_path / name; case.mkdir()
        f = studio_fakes.factory(case, monkeypatch)
        now = plan_fakes.record(f, studio_fakes.client(f), body)
        assert now == reference[name], name
        assert 'story' not in now['project']['idea'] and 'script' not in now['project']
    # An explicit 'ai' (the new app in its default mode) is stored exactly like no field at all.
    case = tmp_path / 'explicit'; case.mkdir(); f = studio_fakes.factory(case, monkeypatch)
    now = plan_fakes.record(f, studio_fakes.client(f), {**bodies['film_invent_30s'], 'story': 'ai'})
    assert now == reference['film_invent_30s']


def test_api_check_create_and_the_guards_of_a_script_project(tmp_path, monkeypatch):
    f = studio_fakes.factory(tmp_path, monkeypatch); client = studio_fakes.client(f)
    check = client.post('/api/factory/script/check', json={'text': SCRIPT}).json()
    assert check['ok'] and [f_['name'] for f_ in check['figures']] == NAMES and len(check['episodes']) == 2
    assert '## Folge 2' in check['preview'] and check['duration'] == 17
    assert client.post('/api/factory/script/check', json={'text': 'x' * 100001}).status_code == 400
    bad = client.post('/api/factory', json={'request_key': 'e' * 32, 'idea': 'LENA: Hallo!\nMARKUS: Hallo zurück, Lena!', 'story': 'script'})
    assert bad.status_code == 400 and 'mindestens 15 s' in bad.json()['detail']
    stranger = client.post('/api/factory', json={'request_key': 'e' * 32, 'idea': SCRIPT, 'story': 'script', 'participants': [{'name': 'Opa'}]})
    assert stranger.status_code == 400 and '„Opa“ kommt im Drehbuch nicht vor' in stranger.json()['detail']
    made = client.post('/api/factory', json={'request_key': 'e' * 32, 'idea': SCRIPT, 'story': 'script', 'episodes': 1, 'duration': 60}).json()
    assert made['idea']['episodes'] == 2 and made['idea']['duration'] == 17 and made['idea']['characters'] == 'provided'
    assert made['title'] == 'Der Kuchenklau von Hausnummer 7' and made['script']['episodes'][1]['title'] == 'Die Spur der Krümel'
    # Same request again: the same project (idempotent), nothing doubled.
    again = client.post('/api/factory', json={'request_key': 'e' * 32, 'idea': SCRIPT, 'story': 'script', 'episodes': 1, 'duration': 60}).json()
    assert again['id'] == made['id']
    # 'Dialoge ergänzen' is refused: the script stays as Cay wrote it.
    d = f.get(made['id']); d.update(state='voice_review', episodes=[{'title': 'x', 'scenes': [{'title': 'x', 'cast': ['Tim']}]}]); f.save(d)
    refused = client.post(f'/api/factory/{made["id"]}/correction', json={'request_key': 'f' * 32, 'revision': f.get(made['id'])['revision'],
                                                                       'kind': 'dialogue', 'episode': 0, 'scene': 0, 'message': 'mehr Dialog'})
    assert refused.status_code == 409 and 'Wort für Wort' in refused.json()['detail']
    # A new edition plans the same script anew; no 'Überarbeitung' line is added to it.
    edition = client.post(f'/api/factory/{made["id"]}/new-edition', json={'note': 'mehr Streit'}).json()
    assert edition['idea']['idea'] == SCRIPT and edition['idea']['story'] == 'script' and edition['id'] != made['id']
    # Without the field: no 'story' key in the stored idea, no script.
    plain = client.post('/api/factory', json={'request_key': '1' * 32, 'idea': 'Zwei Kollegen streiten um den letzten Keks.'}).json()
    assert 'story' not in plain['idea'] and 'script' not in plain


def test_the_template_is_a_valid_script():
    text = (ROOT / 'cay_studio_app/web/app2/Drehbuch_Vorlage.md').read_text(encoding='utf-8')
    r = own_script.read(text)
    assert r['ok'], [p for p in r['problems'] if p['blocking']]
    assert not r['problems'], r['problems']
    assert r['title'] and len(r['figures']) >= 2 and all(f['description'] for f in r['figures'])
    assert all(15 <= e['seconds'] <= 90 for e in r['episodes'])
    # The hints at the top are not filmed.
    assert 'Sprechhaltung' not in r['preview'] and 'NAME' not in r['preview']


# Real-world spellings (Markdown, ChatGPT, Word paste): every spoken word stays, or a hint with the line says why not.
def said(r):
    names = [f['name'] for f in r['figures']]
    return [(l['speaker'], l['text']) for ep in r['episodes'] for l in parsed(ep['text'], names)[2] if l['kind'] == 'line']


def notes(r): return [p['text'] for p in r['problems']]


def test_emphasis_and_list_marks_around_names_and_directions_keep_the_line():
    r = own_script.read('''# Der Kuchenklau
### Szene 1 – Küche – Oma vor dem leeren Teller
OMA *(schreit)*: Wer hat meinen Kuchen gegessen? Ich zähle jetzt bis drei!
TIM _(zuckt zusammen)_: Ich war's nicht, Oma!
*OMA*: Ach ja? Und was ist das da an deinem Mund?
_TIM_: Das ist Zahnpasta!
*OMA:* Zahnpasta mit Schokostreuseln.
1. TIM: Okay… vielleicht ein kleines Stück.
**Opa:** *(lachend)* Lass ihn, Hilde. Ich hab die Hälfte gegessen.
*OMA: Du auch?!*
''')
    assert said(r) == [('Oma', 'Wer hat meinen Kuchen gegessen? Ich zähle jetzt bis drei!'), ('Tim', "Ich war's nicht, Oma!"),
                       ('Oma', 'Ach ja? Und was ist das da an deinem Mund?'), ('Tim', 'Das ist Zahnpasta!'), ('Oma', 'Zahnpasta mit Schokostreuseln.'),
                       ('Tim', 'Okay… vielleicht ein kleines Stück.'), ('Opa', 'Lass ihn, Hilde. Ich hab die Hälfte gegessen.'), ('Oma', 'Du auch?!')]
    text = r['episodes'][0]['text']
    assert '*' not in text and '_' not in text and 'AKTION' not in text
    assert 'Oma [schreiend]: Wer hat' in text and 'Opa [fröhlich]: Lass ihn' in text


def test_role_names_speak_and_group_or_prose_labels_are_reported():
    r = own_script.read('''# Das Paket
### Szene 1 – Haustür – Oma öffnet die Tür
Oma: Wer klingelt denn um diese Uhrzeit noch an meiner Tür, bitte schön?
Der Postbote: Ein Paket für Sie, Frau Berger! Bitte hier unterschreiben.
Oma: Ein Paket? Ich habe doch gar nichts bestellt, junger Mann.
Die Nachbarin: Das ist meins! Das hab ich zu Ihnen liefern lassen.
Alle: Schönen Abend noch!
Ein Kind: Ist da Schokolade drin?
Tim & Opa: Sorry, Oma!
Plötzlich: Das Licht geht aus.
''')
    assert said(r) == [('Oma', 'Wer klingelt denn um diese Uhrzeit noch an meiner Tür, bitte schön?'),
                       ('Der Postbote', 'Ein Paket für Sie, Frau Berger! Bitte hier unterschreiben.'),
                       ('Oma', 'Ein Paket? Ich habe doch gar nichts bestellt, junger Mann.'),
                       ('Die Nachbarin', 'Das ist meins! Das hab ich zu Ihnen liefern lassen.'), ('Ein Kind', 'Ist da Schokolade drin?')]
    assert [f['name'] for f in r['figures']] == ['Oma', 'Der Postbote', 'Die Nachbarin', 'Ein Kind']
    found = notes(r)
    assert 'Zeile 7: „Alle: Schönen Abend noch!“ wird nicht gesprochen, sondern als stumme Handlung gezeigt. Im Film sagt jeden Satz genau eine Figur: ' \
           'schreib einen Namen davor, zum Beispiel „NAME: …“.' in found
    assert any(t.startswith('Zeile 9: „Tim & Opa: Sorry, Oma!“ wird nicht gesprochen') and '„TIM: …“' in t for t in found)
    assert any(t.startswith('Zeile 10: „Plötzlich: Das Licht geht aus.“ wird nicht gesprochen') and '„PLÖTZLICH: …“' in t for t in found)
    assert 'Zeile 4: „Der Postbote“ spricht nur einmal. Ist das wirklich eine Figur? Wenn nicht, lösch die Zeile oder schreib „AKTION:“ davor.' in found


def test_a_notes_heading_inside_a_scene_ends_at_the_next_spoken_line():
    r = own_script.read('''# Der Kuchenklau
### Szene 1 – Küche – Oma vor dem leeren Teller
OMA (wütend): Wer hat meinen Kuchen gegessen? Ich zähle jetzt bis drei!
TIM (ängstlich): Ich war's nicht, Oma! Ehrlich nicht, ich schwöre es dir!

#### Hinweis
Ab hier soll es richtig lustig werden.

OMA: Dein Mund ist voller Krümel, und du lügst mich einfach so an!
TIM: Okay, okay. Es war vielleicht ein ganz kleines Stück vom Kuchen.
''')
    assert [t for _, t in said(r)][2:] == ['Dein Mund ist voller Krümel, und du lügst mich einfach so an!',
                                           'Okay, okay. Es war vielleicht ein ganz kleines Stück vom Kuchen.']
    assert 'Zeile 6–7: Abschnitt „Hinweis“ wird nicht verfilmt. Danach geht das Drehbuch weiter.' in notes(r)
    assert 'lustig' not in r['preview']


def test_metadata_lines_are_no_figures():
    r = own_script.read('''# 🎬 Der Kuchenklau
Genre: Komödie
Dauer: ca. 40 Sekunden
Stil: Knetanimation
**Länge:** ca. 45 Sekunden
**Figuren:** Oma Hilde, Tim (9)
Produktion: Cay

### Szene 1 – Küche – Oma vor dem leeren Teller
OMA HILDE (wütend): Wer hat meinen Kuchen gegessen? Ich zähle jetzt bis drei!
TIM (ängstlich): Ich war's nicht, Oma! Ehrlich nicht, ich schwöre es dir!
OMA HILDE: Dein Mund ist voller Krümel, und du lügst mich einfach so an!
TIM: Okay, okay. Es war vielleicht ein ganz kleines Stück vom Kuchen.
''')
    assert [(f['name'], f['description']) for f in r['figures']] == [('Oma Hilde', ''), ('Tim', '9'), ('Produktion', '')]
    found = notes(r)
    assert 'Zeile 2: „Genre: Komödie“ wird nicht verfilmt.' in found and 'Zeile 5: „Länge: ca. 45 Sekunden“ wird nicht verfilmt.' in found
    assert 'Zeile 7: „Produktion“ spricht nur einmal. Ist das wirklich eine Figur? Wenn nicht, lösch die Zeile oder schreib „AKTION:“ davor.' in found
    assert 'Komödie' not in r['preview'] and 'Sekunden' not in r['preview']


def test_a_screenplay_pasted_from_word_without_blank_lines_keeps_each_speaker():
    r = own_script.read('''Titel: Der Tresor

INNEN. BÄCKEREI – NACHT
MAX
(flüsternd)
Pssst! Hier drüben ist der Tresor.
LENA
Ich mach doch gar nichts!
Lena stolpert über einen Mehlsack.
MAX
Lena! Das ganze Mehl! Jetzt sieht uns jeder, wenn wir hier rausgehen.
LENA
Dann putzen wir eben alles weg, bevor der Bäcker morgen früh kommt.
''')
    assert said(r) == [('Max', 'Pssst! Hier drüben ist der Tresor.'), ('Lena', 'Ich mach doch gar nichts!'),
                       ('Max', 'Lena! Das ganze Mehl! Jetzt sieht uns jeder, wenn wir hier rausgehen.'),
                       ('Lena', 'Dann putzen wir eben alles weg, bevor der Bäcker morgen früh kommt.')]
    lines = parsed(r['episodes'][0]['text'], ['Max', 'Lena'])[2]
    assert [l['text'] for l in lines if l['kind'] == 'action'] == ['Lena stolpert über einen Mehlsack.'] and lines[0]['emotion'] == 'flüsternd'
    assert any(t.startswith('Zeile 9: „Lena stolpert über einen Mehlsack.“ ist eine stumme Handlung, kein Satz von Lena.') for t in notes(r))
    # With blank lines a speech may run over several rows; the studio says which rows it joins.
    joined = own_script.read('### Szene 1 – Küche\nTIM\nHallo Oma.\nTim versteckt die Hände.\n\nOMA\nZeig mal her, mein Freund!')
    assert said(joined)[0] == ('Tim', 'Hallo Oma. Tim versteckt die Hände.')
    assert any(t.startswith('Zeile 3–4: Tim spricht diese Zeilen in einem Stück.') for t in notes(joined))


def test_rules_time_marks_and_emoji_headings_invent_no_shots():
    r = own_script.read('''**Titel: Der Kuchenklau**

---

## 🎥 Szene 1: Küche
**[0:00–0:05] Hook**
OMA HILDE *(schreit)*: WER HAT MEINEN KUCHEN GEGESSEN?!
**[0:05–0:12]**
TIM: Ich war's nicht, Oma! Ehrlich nicht, ich schwöre es dir, wirklich!
(0:12) OMA HILDE: Ach ja? Und was ist das da an deinem Mund, hm?

* * *

## 🎥 Szene 2: Flur
TIM: Das ist Zahnpasta! Ganz normale Zahnpasta, Oma, ganz ehrlich!
**Outro / CTA:** Folgt für Teil 2!
''')
    title, beats, lines = parsed(r['episodes'][0]['text'], ['Oma Hilde', 'Tim'])
    assert [b['place'] for b in beats] == ['Küche', 'Flur'] and not [l for l in lines if l['kind'] == 'action']
    assert [t for _, t in said(r)] == ['WER HAT MEINEN KUCHEN GEGESSEN?!', "Ich war's nicht, Oma! Ehrlich nicht, ich schwöre es dir, wirklich!",
                                       'Ach ja? Und was ist das da an deinem Mund, hm?', 'Das ist Zahnpasta! Ganz normale Zahnpasta, Oma, ganz ehrlich!']
    found = notes(r)
    assert 'Zeile 6: Zeitangaben wie „[0:00–0:05]“ setzt das Studio selbst, sie werden übersprungen.' in found
    assert 'Zeile 16: „Outro / CTA: Folgt für Teil 2!“ wird nicht verfilmt.' in found and not any('Kein Ort' in t or 'Überschrift' in t for t in found)


def test_a_figure_list_ends_where_the_dialogue_starts():
    r = own_script.read('''# Der Kuchenklau

## Figuren
- Oma: 72 Jahre, Schürze, streng
- Tim: 9 Jahre, rote Kappe, frech

Küche, Oma steht vor dem leeren Teller.

OMA (wütend): Wer hat meinen Kuchen gegessen? Ich zähle jetzt bis drei!
TIM (ängstlich): Ich war's nicht, Oma! Ehrlich nicht, ich schwöre es dir!
MAMA (genervt): Was ist denn hier schon wieder los? Man hört euch bis in den Keller!
OMA: Dein Sohn hat meinen ganzen Kuchen aufgegessen, und er lügt mich an!
''')
    assert [(f['name'], f['description'], f['lines']) for f in r['figures']] == [
        ('Oma', '72 Jahre, Schürze, streng', 2), ('Tim', '9 Jahre, rote Kappe, frech', 1), ('Mama', '', 1)]
    assert r['ok'] and len(said(r)) == 4 and 'Küche, Oma steht' in r['episodes'][0]['plot']
    # Without a blank line, a spoken line with a mood or a question still ends the list.
    tight = own_script.read('## Figuren\nOma: 72 Jahre, streng\nTim: 9 Jahre, frech\nOMA: Wer hat meinen Kuchen gegessen?\nTIM (ängstlich): Ich nicht!')
    assert said(tight) == [('Oma', 'Wer hat meinen Kuchen gegessen?'), ('Tim', 'Ich nicht!')] and tight['figures'][0]['description'] == '72 Jahre, streng'


def test_quotes_around_part_of_a_line_go_in_pairs():
    r = own_script.read('''### Szene 1 – Küche – Oma vor dem leeren Teller
OMA (wütend): „Wer hat meinen Kuchen gegessen?“ Ich zähl bis drei!
TIM: Okay… vielleicht ein kleines Stück. Er sagte „Nein“
TIM: (leise) „Opa war es.“ Er hatte Hunger!
OMA: »Im Bad. Mit Sahne an der Nase?«
''')
    assert [t for _, t in said(r)] == ['Wer hat meinen Kuchen gegessen? Ich zähl bis drei!', 'Okay… vielleicht ein kleines Stück. Er sagte Nein',
                                       'Opa war es. Er hatte Hunger!', 'Im Bad. Mit Sahne an der Nase?']
    # Prose with words in quotes is shown, not spoken: the studio says so.
    prose = own_script.read('### Szene 1 – Küche\nOMA: Hallo Tim, schön dich zu sehen heute.\n„Wo ist der Kuchen?“, fragt Tim leise.')
    assert any(t.startswith('Zeile 3: „„Wo ist der Kuchen?“, fragt Tim leise.“ wird nicht gesprochen') for t in notes(prose))


def test_deep_brackets_and_many_speakers_stay_fast_and_the_check_runs_beside_the_server(tmp_path, monkeypatch):
    import time
    start = time.monotonic(); r = own_script.read('TIM: ' + '(' * 30000 + 'x' + ')' * 29990)
    assert time.monotonic() - start < 3 and not r['ok']
    nested = own_script.read('### Szene 1 – Küche\nTIM: (((leise))) Hallo Oma, ich bin wieder da.\nOMA: (((((wütend))))) Wo warst du?')
    assert said(nested)[0] == ('Tim', 'Hallo Oma, ich bin wieder da.') and not nested['ok']      # deeper than four: the check stops the film
    start = time.monotonic(); many = own_script.read('\n'.join(f'FIGUR{chr(65 + i // 26)}{chr(65 + i % 26)}: Das ist ein Satz.' for i in range(600)))
    assert time.monotonic() - start < 3 and any('höchstens 30 sind möglich' in p['text'] for p in many['problems'])
    # The live check reads the script in a worker thread, so a long script never holds up the other requests.
    f = studio_fakes.factory(tmp_path, monkeypatch); client = studio_fakes.client(f); seen = []; real = own_script.read
    def spy(text):
        try: asyncio.get_running_loop(); seen.append('event loop')
        except RuntimeError: seen.append('thread')
        return real(text)
    monkeypatch.setattr(own_script, 'read', spy)
    assert client.post('/api/factory/script/check', json={'text': SCRIPT}).json()['ok'] and seen == ['thread']


def test_the_long_sentence_hint_reads_as_plain_german():
    long = 'Das ist mein Satz, und ich sage ihn mit großer Freude und sehr viel Gefühl, weil heute ein ganz besonderer Tag für uns alle ist.'
    r = own_script.read(f'### Szene 1 – Küche\nANNA: {long}\nBERND: Ja, das stimmt, heute ist wirklich ein schöner Tag.\nANNA: {long}')
    assert any(t.startswith('Hinweis: Sätze mit mehr als 22 Wörtern: in zwei kürzere Sätze geteilt klingen sie lebendiger. Das ist mein Satz')
               for t in notes(r)), notes(r)
    assert not any('wirken geteilt' in t for t in notes(r))


def test_a_long_own_episode_is_a_hint_not_a_stop():
    """Cay: 'keine Textlängen-Sperre'. Up to 180 s and 90 shots per own episode; the planned minimum stays at most 90 s."""
    import own_script
    lines = '\n'.join(f'{"OMA" if i % 2 else "TIM"}: Das ist Satz Nummer {i}, und er ist ganz normal lang für einen Film.' for i in range(28))
    result = own_script.read('# Langer Film\n### Szene 1 – Küche – Oma und Tim am Tisch\n' + lines)
    seconds = result['episodes'][0]['seconds']
    assert 90 < seconds <= 180, seconds
    assert result['ok'], [p['text'] for p in result['problems'] if p['blocking']]
    assert any('rechnet aber entsprechend länger' in p['text'] for p in result['problems'])
