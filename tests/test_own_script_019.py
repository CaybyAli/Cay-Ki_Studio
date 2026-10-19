"""'Mein Drehbuch' 0.19 (diagnosis r019, complaint C2): scripts as chat assistants and Cay write them.

Proves, for projects created from 0.19 on (own_script.read with POLICY, the default):
- the r019 corpus (46 typical ChatGPT, Claude and Gemini spellings of the same 8 lines) keeps every line
  with its speaker, invents no figure and films no heading as a silent shot (the 0.18 reader lost,
  invented or misfiled something in 25 of them; two known limits stay listed below);
- Cay's real script 'Weißes Gold' keeps all 52 lines word for word, its time windows leave place and
  picture and become the length hint (58 s), an AKTION that only sets the scene is the picture of the
  next line instead of a silent shot, and every episode gets a plain warning with numbers;
- (off), (V.O.) and 'Stimme (X)' are heard from off-screen over another figure's face;
- the reading report accounts for every row.
And for older projects: own_script.read(text, 0) returns exactly what the 0.18 reader at git e5da1cd
returned (tests/fixtures/own_script_018_reference.json, recorded from that commit)."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import studio_fakes  # noqa: E402  (puts cay_studio_app on the path)
import plan_fakes  # noqa: E402
import own_script  # noqa: E402
import screenplay  # noqa: E402
from factory_cast import name_key  # noqa: E402

CORPUS = json.loads((ROOT / 'tests/fixtures/script_formats_019.json').read_text(encoding='utf-8'))
REFERENCE_018 = json.loads((ROOT / 'tests/fixtures/own_script_018_reference.json').read_text(encoding='utf-8'))
GOLD = (ROOT / 'tests/fixtures/Weisses_Gold_Drehbuch.md').read_text(encoding='utf-8')
CAST = {'spongebob', 'patrick', 'mr. krabs', 'plankton', 'sandy'}
# Known limits: 'Folge 1 endet …' inside '## Hinweise' still counts as an episode heading (story_source.manifest
# is shared with the AI mode), and a narrator without a figure needs a voice, so it stays a cast member.
LIMITS = {'43_hinweis_mentions_folge', '44_erzaehler_vo'}
HEADINGISH = re.compile(r'(?i)^\(?\s*(?:\d+[.)]\s*)?(?:szene|scene|int\.?|ext\.?|innen|aussen|außen|beat|wendepunkt|cliffhanger|hook|outro)\b')


def plain(text):
    return ' '.join(str(text).replace('„', '').replace('“', '').replace('"', '').split()).strip()


def cut_of(r, ep):
    names = [f['name'] for f in r['figures']]
    title, beats, lines, problems = screenplay.parse(ep['text'], names, own=True)
    assert not problems, problems
    return beats, lines, screenplay.shots(title, beats, lines, names)


@pytest.mark.parametrize('name', sorted(n for n in CORPUS if n not in LIMITS))
def test_chat_assistant_spellings_keep_every_line(name):
    r = own_script.read(CORPUS[name]['text'])
    assert r['ok'], [p['text'] for p in r['problems'] if p['blocking']]
    said, actions = [], []
    for ep in r['episodes']:
        _, lines, _ = cut_of(r, ep)
        said += [(name_key(l['speaker']), plain(l['text'])) for l in lines if l['kind'] == 'line']
        actions += [l['text'] for l in lines if l['kind'] == 'action']
    assert said == [(name_key(s), plain(t)) for s, t in CORPUS[name]['expected']]
    assert {name_key(f['name']) for f in r['figures']} <= CAST, r['figures']
    assert not [a for a in actions if HEADINGISH.match(a)]
    assert r['report']['unread_count'] == 0, r['report']['unread']


def test_the_old_reader_lost_lines_in_many_of_these_spellings():
    """The same corpus through the 0.18 reader (recorded): what this release fixes."""
    def wrong(name):
        old = REFERENCE_018[name]; names = [f['name'] for f in old['figures']]; said = []
        for ep in old['episodes']:
            said += [(name_key(l['speaker']), plain(l['text'])) for l in screenplay.parse(ep['text'], names)[2] if l['kind'] == 'line']
        return said != [(name_key(s), plain(t)) for s, t in CORPUS[name]['expected']] or not {name_key(f['name']) for f in old['figures']} <= CAST
    assert sum(wrong(n) for n in CORPUS) >= 20


@pytest.mark.parametrize('name', sorted(REFERENCE_018))
def test_older_projects_read_their_script_exactly_as_before(name):
    text = GOLD if name == 'Weisses_Gold_Drehbuch.md' else CORPUS[name]['text']
    assert own_script.read(text, 0) == REFERENCE_018[name]


def gold_lines():
    """Every 'NAME (stimmung): Text' row of Cay's script, as written."""
    return [(m.group(1), m.group(2)) for m in re.finditer(r'^([A-ZÄÖÜ][A-ZÄÖÜ. ]+?) \([^)]*\): (.+)$', GOLD, re.M)]


def test_weisses_gold_keeps_all_52_lines_and_shows_fewer_silent_shots():
    r = own_script.read(GOLD)
    assert r['ok'] and r['lines'] == 52 and r['words'] == 257 and len(r['episodes']) == 6
    said = [(name_key(l['speaker']), l['text']) for ep in r['episodes'] for l in cut_of(r, ep)[1] if l['kind'] == 'line']
    assert said == [(name_key(s), t) for s, t in gold_lines()] and len(said) == 52
    # The script's own spelling of its figures (the 0.18 reader made 'Spongebob' of 'SPONGEBOB').
    assert [f['name'] for f in r['figures']] == ['SpongeBob', 'Patrick', 'Mr. Krabs', 'Plankton', 'Thaddäus', 'Larry', 'Sandy']
    old = REFERENCE_018['Weisses_Gold_Drehbuch.md']; old_names = [f['name'] for f in old['figures']]
    silent = lambda cut: sum(1 for s in cut if not s['lines'])
    old_silent = [silent(screenplay.shots(*screenplay.parse(ep['text'], old_names)[:3], old_names)) for ep in old['episodes']]
    new_silent = [silent(cut_of(r, ep)[2]) for ep in r['episodes']]
    assert sum(new_silent) < sum(old_silent) and all(n <= o for n, o in zip(new_silent, old_silent)), (new_silent, old_silent)
    # Folge 1 used to open with 6.4 s of silence (two silent shots): now Sandy speaks right away, the
    # opening description is the picture of her shot, and no AKTION word is lost.
    beats, lines, cut = cut_of(r, r['episodes'][0])
    assert cut[0]['kind'] == 'line' and cut[0]['lines'][0]['speaker'] == 'Sandy'
    assert cut[0]['context'].startswith('Ruhiger Beginn. Unter einem rostigen Vordach sitzt SpongeBob')
    assert r['episodes'][0]['pacing']['first_word'] < 1
    shown = ' '.join(x for l in lines for x in (l.get('context', ''), l['text'] if l['kind'] == 'action' else '') if x)
    for m in re.finditer(r'^AKTION: (.+)$', GOLD.split('## Folge 2')[0], re.M):
        assert plain(m.group(1)) in plain(shown) or all(plain(s) in plain(shown) for s in own_script._sentences(m.group(1)))
    # An AKTION with a real event stays a silent shot of its own.
    assert any(s['kind'] == 'action' and s['what'].startswith('SpongeBob sieht auf seinen kaputten Schuh') for s in cut)


def test_weisses_gold_time_windows_are_a_length_hint_and_the_warning_has_numbers():
    r = own_script.read(GOLD)
    for ep in r['episodes']:
        beats = cut_of(r, ep)[0]
        assert not any(re.search(r'\d:\d\d', b['place'] + b['what']) for b in beats)
        assert ep['pacing']['stated_seconds'] == 58
    first = cut_of(r, r['episodes'][0])[0][0]
    assert first == {'place': 'Vor Sandys Werkstatt, früher Abend', 'what': 'Warmes Licht fällt durch ein halb geöffnetes Garagentor'}
    notes = [p['text'] for p in r['problems']]
    assert 'Folge 1: 50 gesprochene Wörter für ca. 58 s – etwa 65 % ohne Sprache. Für etwa zwei Drittel Sprache wären es rund 100 Wörter.' in notes
    assert any(n.startswith('Folge 6: 21 gesprochene Wörter für ca. 58 s – etwa 85 % ohne Sprache.') for n in notes)
    assert not any(p['blocking'] for p in r['problems'])
    # The planned minimum never stretches the shorter 0.19 silent shots back up (shot_design.ACTION_FRAMES).
    assert r['duration'] <= min(e['pacing']['seconds'] for e in r['episodes']) and r['duration'] < REFERENCE_018['Weisses_Gold_Drehbuch.md']['duration']
    report = r['report']
    assert report['spoken'] == 52 and report['unread_count'] == 0 and report['rows'] == sum(report[k] for k in own_script.REPORT_KINDS)


def test_a_long_silent_start_is_reported():
    text = ('### Szene 1 – Hafen – Nebel\nAKTION: Patrick stellt eine schwere Kiste ab und wischt sich die Stirn.\n'
            'AKTION: SpongeBob rennt mit einem Koffer über den Steg.\n'
            'SANDY: Montag, sieben Uhr. Arbeit hätte ich für euch beide, wenn ihr wollt.\n'
            'PATRICK: Ich wäre dabei. Bin ich zu spät zum Frühstück, oder gibt es noch was?\n'
            'SANDY: Für dich gibt es immer noch was, Patrick. Komm einfach rein.\n')
    notes = [p['text'] for p in own_script.read(text)['problems']]
    assert any(n.startswith('Dein Film: Das erste Wort fällt erst nach etwa 4 s.') for n in notes), notes
    assert not any('Das erste Wort' in p['text'] for p in own_script.read(text, 0)['problems'])


def off_scene(marker):
    return ('### Szene 1 – Büro – Krabs am Schreibtisch\n'
            'SANDY: Montag, sieben Uhr. Arbeit hätte ich für euch beide.\n'
            f'{marker}: Fünfhundert für euch beide. Plankton bezahlt euch bei der Übergabe.\n'
            'SANDY: Das klingt nach Ärger, aber gut, wir sind dabei.\n'
            'SANDY: Patrick holt den Wagen, und ich passe auf, dass niemand den Koffer öffnet.\n')


@pytest.mark.parametrize('marker', ['MR. KRABS (off)', 'MR. KRABS (V.O.)', 'MR. KRABS (O.S.)', 'MR. KRABS (am Telefon)', 'MR. KRABS (aus dem Off, wütend)',
                                    'Stimme (Mr. Krabs)'])
def test_a_line_from_off_screen_is_heard_over_the_listener(marker):
    r = own_script.read('FIGUR: Mr. Krabs – Krebs\n' + off_scene(marker))
    assert r['ok'] and [f['name'] for f in r['figures']] == ['Mr. Krabs', 'Sandy']
    assert not any('kennt das Studio nicht' in p['text'] or 'sichtbare Figur' in p['text'] for p in r['problems'])
    _, lines, cut = cut_of(r, r['episodes'][0])
    off = next(s for s in cut if s['kind'] == 'reaction' and s['voice_of'] == 'Mr. Krabs')
    assert off['visible'] == ['Sandy'] and off['lines'][0]['text'] == 'Fünfhundert für euch beide. Plankton bezahlt euch bei der Übergabe.'
    assert not any(s['kind'] == 'line' and 'Mr. Krabs' in s['visible'] for s in cut)
    if 'wütend' in marker: assert off['lines'][0]['emotion'] == 'wütend'
    # The same script read for an older project: the 0.18 reader, Mr. Krabs speaks in the frame.
    old = own_script.read('FIGUR: Mr. Krabs – Krebs\n' + off_scene(marker), 0)
    assert '|off' not in old['episodes'][0]['text']


def test_off_screen_needs_someone_else_in_the_scene():
    r = own_script.read('### Szene 1 – Büro\nMR. KRABS (off): Wo ist mein Geld? Ich zähle es jeden Abend zweimal nach.\n'
                        'MR. KRABS: Und heute fehlt ein Dollar, ein ganzer Dollar, verstehst du das? Ein ganzer Dollar!\n'
                        'MR. KRABS: Ich werde ihn finden, und wenn ich die ganze Nacht suchen muss, das schwöre ich.\n')
    assert any('kommt nicht aus dem Off' in p['text'] for p in r['problems'])
    assert all(s['kind'] == 'line' for s in cut_of(r, r['episodes'][0])[2])


def test_a_narrator_with_voice_over_is_never_shown():
    r = own_script.read(CORPUS['44_erzaehler_vo']['text'])
    cut = cut_of(r, r['episodes'][0])[2]
    narrator = [s for s in cut if any(l['speaker'] == 'Erzähler' for l in s['lines'])]
    assert narrator and all(s['kind'] == 'reaction' and 'Erzähler' not in s['visible'] for s in narrator)
    assert any('„Erzähler“ spricht nur aus dem Off und ist im Film nie zu sehen' in p['text'] for p in r['problems'])


def test_a_scene_setting_becomes_the_picture_of_the_next_line_in_the_plan(tmp_path, monkeypatch):
    """Through planning: the BILD context reaches the planner's listing and the scene; the section that the
    script itself describes gets no extra wide shot; the AKTION with an event stays a silent shot."""
    text = ('# Der Auftrag\n### Szene 1 – Hafen – Nebel über dem Wasser\n'
            'AKTION: Kaltes Licht fällt durch den Nebel. Patrick steht neben einem Stapel Kisten und trägt einen grünen Hoodie.\n'
            'SANDY: Montag, sieben Uhr. Arbeit hätte ich für euch beide, wenn ihr wollt.\n'
            'PATRICK: Ich wäre dabei. Bin ich zu spät zum Frühstück, oder gibt es noch was?\n'
            '### Szene 2 – Büro – Krabs zählt Geld\n'
            'AKTION: Mr. Krabs sitzt hinter dem Schreibtisch. Er schiebt einen Koffer über den Tisch.\n'
            'MR. KRABS: Fünfhundert für euch beide. Plankton bezahlt euch bei der Übergabe.\n'
            'SANDY: Das klingt nach Ärger, aber gut, wir sind dabei, Mr. Krabs.\n')
    f = studio_fakes.factory(tmp_path, monkeypatch); client = studio_fakes.client(f)
    d, planner = plan_fakes.plan(f, client, {'request_key': '9' * 32, 'idea': text, 'story': 'script', 'characters': 'provided'}, write=False)
    assert d['shot_policy'] == 19 and d['script']['policy'] == 19
    scenes = d['episodes'][0]['scenes']
    first = scenes[0]
    assert first['kind'] == 'line' and first['context'] == 'Kaltes Licht fällt durch den Nebel. Patrick steht neben einem Stapel Kisten und trägt einen grünen Hoodie.'
    assert [s['action'] for s in scenes if s['kind'] == 'action'] == ['Er schiebt einen Koffer über den Tisch.']
    action = next(s for s in scenes if s['kind'] == 'action')
    assert action['context'] == 'Mr. Krabs sitzt hinter dem Schreibtisch.' and action['cast'] == ['Mr. Krabs']
    assert not any(s['kind'] == 'establish' for s in scenes[:3])
    listing = next(c for c in planner.calls if c[1] == 'ShotVisuals')[3]['shots']
    assert listing[0]['situation'] == 'Nebel über dem Wasser Kaltes Licht fällt durch den Nebel. Patrick steht neben einem Stapel Kisten und trägt einen grünen Hoodie.'
    assert 'BILD: Kaltes Licht' in d['screenplays']['0']['final']
