"""Screenplay first: the whole film as one conversation, then shots.

Up to 0.16 dialogue was one field among sixteen per scene, in a fixed budget of
ten scenes with one speaker each. Cay's 60 s film got 63 words, lines like
"Geld. Jetzt. Sofort." and three seconds of silence after every line, in which
the lip-sync model kept moving mouths.

Now: 1) the planner writes a continuous screenplay as plain text, with
thinking, in a strict line format; 2) the text is parsed and checked (word
budget, turns, speakers, no telegram style) and sent back with the concrete
errors; 3) a script doctor rewrites it once; 4) the screenplay is cut into
shots deterministically: one shot per speaker turn, silent action shots for
AKTION lines; 5) a separate JSON pass writes the image and motion text, which
may only describe the visible figures. The dialogue cannot change there.

0.18 (policy 14), after Cay's second film ("1 Person spricht, nächste Szene,
andere Person spricht"): 13 lip-sync shots with exactly one line each, 12
speaker changes, every figure alone and frontal. The budget no longer forces a
change every five seconds, the rules ask for speech blocks, one shot holds a
block up to three lip-sync windows, the last line of every second block is
heard off-screen over the listener's silent reaction (L-cut), and a new place
opens with a wide establishing shot. Screenplays written before keep policy 13:
the policy is stored with the screenplay and with the episode (story_policy).
"""
import math
import re
from typing import Literal
from pydantic import Field
from factory_models import Strict
from factory_cast import name_key, resolve_name

POLICY = 14
LEGACY_POLICY = 13          # screenplays written before 0.18: one shot per speaker turn
WORDS_PER_SECOND = 2.0      # target for the script; Qwen speaks ~2.5 words/s
MAX_LINE_WORDS = 22
MERGE_WORDS = 24            # policy 13: consecutive lines of one speaker share a shot up to this
SPEECH_RATE = 2.6           # words per second measured in Cay's 0.17 film
LINE_PAUSE = .18
MERGE_SECONDS = 8.6         # policy 14: one shot holds a block up to three lip-sync windows (8.96 s)
REACTION_WORDS = 12         # a line heard over the listener's reaction stays short
MAX_ESTABLISH = 2
EMOTIONS = ('ruhig', 'fröhlich', 'begeistert', 'wütend', 'schreiend', 'ängstlich', 'panisch', 'traurig', 'flüsternd',
            'drohend', 'spöttisch', 'überrascht', 'triumphierend', 'flehend', 'genervt', 'verwirrt')
AMBIENCE = ('room', 'wind', 'forest', 'rain', 'train', 'none')


MAX_SHOTS = 44
OWN_MAX_SHOTS = 90         # Cay's own script (own_script): his episodes may run longer than the planner's


def budget(duration, speakers=2, policy=POLICY):
    """Word band, turns and silent action lines for one film of `duration` seconds.
    A single figure has no speaker changes: turns are not required then.

    Policy 13 asked for a speaker change every five seconds (12 for 60 s), so every
    line became its own shot. Policy 14: speech blocks, 6 to 15 changes for 60 s."""
    target = round(duration * WORDS_PER_SECOND)
    actions = max(2, round(duration / 12))
    if policy >= 14: low, high = max(3, round(duration / 10)), max(6, round(duration / 4))
    else: low, high = max(4, round(duration / 5)), max(8, round(duration / 2.2))
    return {'words': target, 'min_words': math.floor(target * .85), 'max_words': math.ceil(target * 1.3),
            'min_turns': low if speakers > 1 else 0,
            'max_turns': min(high, MAX_SHOTS - actions - 4) if speakers > 1 else MAX_SHOTS,
            'min_actions': 1 if duration < 40 else 2, 'max_actions': actions}


FORMAT = '''Format, exakt so, eine Angabe pro Zeile:
TITEL: <Filmtitel>
# <Nummer> | <Ort> | <was in diesem Abschnitt sichtbar passiert>
<NAME> [<Sprechhaltung>]: <gesprochener Text>
AKTION: <sichtbare Handlung ohne Sprache, höchstens zwei Figuren, Münder geschlossen>
Sprechhaltung ist genau eines von: ''' + ', '.join(EMOTIONS) + '''.
NAME exakt wie in der Besetzung. Keine weiteren Zeilen, keine Erklärungen, keine Regieanweisungen im gesprochenen Text.'''

EXAMPLE = '''Beispiel für Ton und Format (andere Figuren, nicht übernehmen):
TITEL: Der verschwundene Kuchen
# 1 | Küche | Oma steht vor einem leeren Teller, Krümel auf dem Boden
OMA [wütend]: Wer hat meinen Kuchen gegessen? Ich zähl bis drei!
TIM [ängstlich]: Ich war's nicht, ehrlich! Ich war die ganze Zeit … im Bad.
OMA [spöttisch]: Im Bad. Mit Sahne an der Nase?
AKTION: Tim wischt sich hastig die Nase und versteckt die Hände hinter dem Rücken.
TIM [flehend]: Okay, okay! Aber es war nur ein ganz kleines Stück!'''

RULES = '''Regeln für das Drehbuch:
- Ein durchgehendes Gespräch: Jede Zeile reagiert auf die vorige, mit Widerspruch, Ausrede, Drohung, Witz oder Überraschung. Keine Zeile ohne Bezug.
- Natürliches gesprochenes Deutsch, meist 7 bis 14 Wörter pro Zeile, ab und zu ein kurzer Ausruf. Kein Telegrammstil wie "Geld. Jetzt. Sofort." oder "Dein X. Mein Y.".
- Lebendig sprechbar: Fragen, Ausrufe, Unterbrechungen mit "–", Zögern mit "…", Interjektionen wie "Hey!", "Au!", "Ha!".
- Jede Figur klingt wie sie selbst. Bekannte Figuren reden und handeln wie im Original (Wortwahl, Ticks, Eigenheiten).
- Spannung: Haken in der ersten Zeile, klares Ziel, zwei echte Steigerungen, eine vorbereitete Wendung, eine Pointe am Schluss. Setup und Payoff für den Witz.
- Die Ereignisse aus der Idee des Nutzers kommen in seiner Reihenfolge vor.
- AKTION-Zeilen für Momente ohne Worte: Verfolgung, Enthüllung, Schreck, Reaktion. Nicht mehr als zwei Figuren.
- Nur Figuren aus der Besetzung. Keine Namen anderer Figuren erfinden.'''

# Policy 14: speech blocks instead of one sentence per speaker change.
EXAMPLE_BLOCKS = '''Beispiel für Ton, Redeblöcke und Format (andere Figuren, nicht übernehmen):
TITEL: Der verschwundene Kuchen
# 1 | Küche | Oma steht vor einem leeren Teller, Krümel auf dem Boden
OMA [wütend]: Wer hat meinen Kuchen gegessen? Ich zähl bis drei!
OMA [drohend]: Und wer jetzt lügt, kriegt eine Woche lang keinen Nachtisch.
TIM [ängstlich]: Ich war's nicht, ehrlich! Ich war die ganze Zeit … im Bad.
TIM [flehend]: Frag doch Opa, der hat mich da gesehen!
OMA [spöttisch]: Im Bad. Mit Sahne an der Nase?
AKTION: Tim wischt sich hastig die Nase und versteckt die Hände hinter dem Rücken.
# 2 | Garten mit Hängematte | Opa schläft, ein leerer Teller liegt auf seinem Bauch
OPA [verwirrt]: Hm? Ach, das … das ist nur ein Kissen, Liebling.
OPA [fröhlich]: Ein sehr leckeres Kissen übrigens, mit Kirschen drauf.
TIM [panisch]: Opa! Das solltest du doch nicht verraten!'''

RULES_BLOCKS = '''Regeln für das Drehbuch:
- Ein durchgehendes Gespräch in Redeblöcken: Eine Figur sagt oft zwei oder drei Sätze nacheinander, jeder Satz als eigene Zeile derselben Figur, bevor die andere antwortet. Jeder Block reagiert auf den vorigen, mit Widerspruch, Ausrede, Drohung, Witz oder Überraschung. Kein Ping-Pong mit nur einem Satz pro Sprecherwechsel. Keine Zeile ohne Bezug.
- Natürliches gesprochenes Deutsch, meist 7 bis 14 Wörter pro Zeile, ab und zu ein kurzer Ausruf. Kein Telegrammstil wie "Geld. Jetzt. Sofort." oder "Dein X. Mein Y.".
- Lebendig sprechbar: Fragen, Ausrufe, Unterbrechungen mit "–", Zögern mit "…", Interjektionen wie "Hey!", "Au!", "Ha!".
- Jede Figur klingt wie sie selbst. Bekannte Figuren reden und handeln wie im Original (Wortwahl, Ticks, Eigenheiten).
- Spannung: Haken in der ersten Zeile, klares Ziel, zwei echte Steigerungen, eine vorbereitete Wendung, eine Pointe am Schluss. Setup und Payoff für den Witz.
- Die Ereignisse aus der Idee des Nutzers kommen in seiner Reihenfolge vor.
- AKTION-Zeilen für Momente ohne Worte: Verfolgung, Enthüllung, Schreck, Reaktion. Nicht mehr als zwei Figuren.
- Nur Figuren aus der Besetzung. Keine Namen anderer Figuren erfinden.'''


def rules(policy=POLICY):
    return RULES_BLOCKS if policy >= 14 else RULES


def example(policy=POLICY):
    return EXAMPLE_BLOCKS if policy >= 14 else EXAMPLE


class ParsedLine(Strict):
    kind: Literal['line', 'action']
    beat: int = Field(ge=0)
    speaker: str = ''
    emotion: str = 'ruhig'
    text: str


class ShotVisual(Strict):
    shot: int = Field(ge=1, le=60)
    still: str = Field(min_length=10, max_length=600)
    motion: str = Field(min_length=5, max_length=400)
    camera: str = Field(min_length=3, max_length=200)
    ambience: Literal['room', 'wind', 'forest', 'rain', 'train', 'none'] = 'room'


class ShotVisuals(Strict):
    shots: list[ShotVisual] = Field(min_length=1, max_length=60)


VISUAL_INSTRUCTION = ('Du bist Kameramann und Bildregisseur. Für jede Einstellung genau ein Eintrag mit derselben Nummer. '
    'still: ENGLISCHE Bildbeschreibung des Standbilds, nur mit den Figuren aus visible: Pose, Gesichtsausdruck, Requisit, Ort, Licht. '
    'Figuren, die nicht in visible stehen, sind außerhalb des Bildes und werden NICHT genannt, auch nicht im Hintergrund. '
    'Bei einer sichtbaren Figur ist sie allein im Bild. '
    'motion: ENGLISCH, eine klar sichtbare Körperbewegung in normaler Geschwindigkeit, die zur Zeile passt; '
    'bei stummen Einstellungen die Handlung selbst. camera: Bildausschnitt, zum Beispiel "medium shot", "close-up", "low angle". '
    'ambience: Umgebungsgeräusch. Ort und Licht über aufeinander folgende Einstellungen gleich halten. '
    'Figuren immer genau mit ihrem Namen aus visible nennen, nie mit Originalnamen, Spitznamen oder Übersetzungen '
    '(nicht "Squidward" für Thaddäus, nicht "Grandma" für Oma). '
    'Im still steht der Gesichtsausdruck passend zur Emotion der Zeile auf Englisch (z. B. "afraid, wide eyes, tense"), '
    'nie ein Ausdruck aus einem Referenzbild.')
# Policy 14: every shot has a role in the cut; speaking shots vary the framing.
SHOT_ROLES = {'line': 'speaking', 'reaction': 'reaction: listens silently, voice from off-screen, mouth closed',
              'action': 'action', 'establish': 'establish: wide view of the new place'}
VISUAL_INSTRUCTION_CUT = ('Du bist Kameramann und Bildregisseur. Für jede Einstellung genau ein Eintrag mit derselben Nummer. '
    'role sagt, was die Einstellung im Schnitt tut: speaking = die Figur aus visible spricht ihre lines; '
    'reaction = die Figur aus visible hört schweigend zu, die Stimme (hears) kommt von außerhalb des Bildes, ihr Mund bleibt geschlossen, '
    'sie reagiert nur mit Augen, Augenbrauen, Kopf und Körper (nicken, zurückweichen, Arme verschränken); '
    'action = stumme Handlung, alle Münder geschlossen; establish = weite Totale, die den neuen Ort zeigt. '
    'still: ENGLISCHE Bildbeschreibung des Standbilds, nur mit den Figuren aus visible: Pose, Gesichtsausdruck, Requisit, Ort, Licht. '
    'Figuren, die nicht in visible stehen, sind außerhalb des Bildes und werden NICHT genannt, auch nicht im Hintergrund '
    'und auch nicht als Stimme aus dem Off. Nur die Figuren aus visible sind im Bild. '
    'motion: ENGLISCH, eine klar sichtbare Körperbewegung in normaler Geschwindigkeit, die zur Zeile passt; '
    'bei reaction eine kleine stumme Reaktion mit geschlossenem Mund; bei action die Handlung selbst; bei establish ruhige Bewegung im Ort. '
    'camera: Bildausschnitt mit Abwechslung. Sprechende Einstellungen wechseln zwischen "medium shot", "medium close-up", '
    '"low angle shot", "high angle medium shot" und "medium shot from the side", nie zweimal hintereinander derselbe Ausschnitt; '
    'reaction "close-up"; establish "wide establishing shot"; action "medium wide shot" oder eine dynamische Perspektive. '
    'ambience: Umgebungsgeräusch. Ort und Licht über aufeinander folgende Einstellungen gleich halten. '
    'Figuren immer genau mit ihrem Namen aus visible nennen, nie mit Originalnamen, Spitznamen oder Übersetzungen '
    '(nicht "Squidward" für Thaddäus, nicht "Grandma" für Oma). '
    'Im still steht der Gesichtsausdruck passend zur Emotion der Zeile auf Englisch (z. B. "afraid, wide eyes, tense"), '
    'bei reaction mit geschlossenem Mund (z. B. "worried, lips pressed together"), nie ein Ausdruck aus einem Referenzbild.')


def visual_instruction(policy=POLICY):
    return VISUAL_INSTRUCTION_CUT if policy >= 14 else VISUAL_INSTRUCTION


# English face for each delivery: the scene image decides the expression of the whole shot.
EXPRESSIONS = {'natural': 'relaxed, attentive', 'firm': 'determined, firm look', 'threat': 'menacing, narrowed eyes',
               'mocking': 'smug, mocking grin', 'annoyed': 'annoyed frown', 'angry': 'angry, furrowed brows',
               'shout': 'shouting, mouth wide open', 'panic': 'panicked, wide eyes', 'afraid': 'afraid, wide eyes, raised eyebrows, tense',
               'joy': 'happy smile', 'excited': 'excited, big grin', 'triumph': 'triumphant grin', 'surprised': 'surprised, raised eyebrows',
               'sad': 'sad, drooping eyes', 'whisper': 'secretive, leaning in', 'pleading': 'pleading, worried eyebrows',
               'confused': 'confused, one eyebrow raised'}


def expression(emotion):
    from speech_quality import performance_key
    return EXPRESSIONS.get(performance_key(emotion), EXPRESSIONS['natural'])


# A silent face never opens its mouth: no 'shouting', 'mouth wide open' or 'big grin' for a
# listener. Wan 2.2 opened mouths in Cay's silent shots; over an off-screen voice that reads
# as the wrong figure speaking.
REACTION_EXPRESSIONS = {'natural': 'attentive, listening, lips closed', 'firm': 'determined look, lips pressed together',
                        'threat': 'narrowed eyes, lips pressed together', 'mocking': 'smug closed-mouth smirk, one eyebrow raised',
                        'annoyed': 'annoyed frown, lips pressed together', 'angry': 'angry frown, furrowed brows, lips pressed together',
                        'shout': 'furious glare, clenched jaw, lips pressed together', 'panic': 'panicked wide eyes, lips pressed together',
                        'afraid': 'afraid, wide eyes, raised eyebrows, lips pressed together', 'joy': 'warm closed-mouth smile',
                        'excited': 'excited sparkling eyes, closed-mouth smile', 'triumph': 'satisfied closed-mouth smirk',
                        'surprised': 'surprised, raised eyebrows, wide eyes, lips closed', 'sad': 'sad, drooping eyes, lips closed',
                        'whisper': 'secretive look, leaning in, lips closed', 'pleading': 'pleading, worried eyebrows, lips closed',
                        'confused': 'confused, one eyebrow raised, lips closed'}
REACTION_GESTURES = {'angry': 'frowns and crosses the arms', 'shout': 'clenches the fists and glares',
                     'annoyed': 'sighs through the nose and rolls the eyes', 'mocking': 'rolls the eyes and folds the arms',
                     'afraid': 'flinches and leans back a little', 'panic': 'flinches, eyes darting, hands gripping each other',
                     'surprised': 'eyebrows shoot up and the head pulls back', 'sad': 'lowers the eyes, the shoulders sink',
                     'joy': 'a small closed-mouth smile and a nod', 'excited': 'bounces slightly with a closed-mouth smile',
                     'triumph': 'lifts the chin with a closed-mouth smirk', 'confused': 'tilts the head, one eyebrow raised',
                     'pleading': 'clasps the hands, worried eyebrows', 'threat': 'narrows the eyes and leans in slowly'}


def reaction_expression(emotion):
    from speech_quality import performance_key
    return REACTION_EXPRESSIONS.get(performance_key(emotion), REACTION_EXPRESSIONS['natural'])


def reaction_gesture(emotion):
    from speech_quality import performance_key
    return REACTION_GESTURES.get(performance_key(emotion), 'a small nod, eyes following the voice')


# Words that open a mouth in a still or motion text; a reaction shot falls back to its own text then.
OPEN_MOUTH = re.compile(r'(?i)\b(?:shout|yell|scream|talk|speak|say|laugh|grin|sing|whisper|cheer|exclaim|gasp|argu|answer|repl|call)'
                        r'(?:s|es|ed|ing|ning|ned|ies|ied|e|y)?\b|\b(?:spoke|said|sang)\b|\bmouth\s+(?:wide\s+)?open'
                        r'|\bopen(?:s|ed|ing)?\s+(?:the\s+|his\s+|her\s+|its\s+|their\s+)?mouth')
VISUAL_REPAIR = ('Diese Einstellungen nennen Figuren, die NICHT im Bild sind. Schreibe still und motion dieser Einstellungen neu, '
                 'nur mit den Figuren aus visible; die anderen Figuren kommen überhaupt nicht vor, auch nicht als Objekt, Besitzer oder im Hintergrund.')


def offscreen_names(shot_text, visible, cast, aliases=None):
    """Off-screen figures a still/motion text names (with original names and spellings)."""
    seen = _expand(visible, aliases)
    return [n for n in cast if n not in visible and _mentions(shot_text, _expand([n], aliases), seen)]


def _resolve(raw, cast):
    raw = re.sub(r'[*_`]', '', raw).strip()
    name = resolve_name(raw, cast)
    if name in cast: return name
    plain = lambda x: re.sub(r'[^\w\s]', '', name_key(x)).strip()
    exact = [c for c in cast if plain(c) == plain(raw)]
    if len(exact) == 1: return exact[0]
    key = name_key(raw)
    # "KRABS" or "Krabs" for "Mr. Krabs": a unique name part of four or more letters.
    parts = [c for c in cast if any(len(p) >= 4 and p == key for p in name_key(c).replace('.', ' ').split())]
    return parts[0] if len(parts) == 1 else None


LINE = re.compile(r'^\s*(?:[-*]\s*)?([^\[\]:#]{1,60}?)\s*(?:\[([^\]]{1,40})\])?\s*:\s*(.+?)\s*$')
BEAT = re.compile(r'^\s*#+\s*(\d+)?\s*\|?\s*([^|]*)\|?\s*(.*)$')


def parse(text, cast):
    """Return (title, beats, lines, problems). Never guesses an unknown speaker."""
    title = ''; beats = []; lines = []; problems = []
    for number, raw in enumerate(str(text).replace('\r', '').split('\n'), 1):
        if raw.strip().startswith('```'): continue
        row = re.sub(r'\*\*|__|`', '', raw).strip().strip('*').strip()
        if not row: continue
        upper = row.upper()
        if upper.startswith('TITEL:'): title = row.split(':', 1)[1].strip()[:100]; continue
        if row.startswith('#'):
            m = BEAT.match(row)
            beats.append({'place': (m.group(2) or '').strip()[:250] or (beats[-1]['place'] if beats else 'Ort'),
                          'what': (m.group(3) or '').strip()[:800]})
            continue
        if not beats: beats.append({'place': 'Ort', 'what': ''})
        if upper.startswith(('AKTION:', 'ACTION:')):
            what = row.split(':', 1)[1].strip()
            if what: lines.append({'kind': 'action', 'beat': len(beats) - 1, 'speaker': '', 'emotion': '', 'text': what[:400]})
            continue
        m = LINE.match(row)
        if not m:
            problems.append(f'Zeile {number} passt nicht ins Format: "{row[:80]}"'); continue
        speaker = _resolve(m.group(1).strip(), cast)
        if speaker is None:
            problems.append(f'Zeile {number}: "{m.group(1).strip()[:40]}" gehört nicht zur Besetzung ({", ".join(cast)})'); continue
        emotion = (m.group(2) or 'ruhig').strip().lower()
        spoken = re.sub(r'\([^)]*\)', '', m.group(3)).strip().strip('"„“').strip()
        if spoken: lines.append({'kind': 'line', 'beat': len(beats) - 1, 'speaker': speaker, 'emotion': emotion[:40], 'text': spoken[:240]})
    return title, beats, lines, problems


def words(text):
    return len(re.findall(r"[\wÄÖÜäöüß'-]+", text))


def telegram(text):
    """'Geld. Jetzt. Sofort.' / 'Dein Geld. Mein Tisch.': only full stops between one- or two-word fragments.
    'Halt! Bleib stehen!' stays allowed: exclamations are natural speech."""
    text = re.sub(r'\b(Mr|Mrs|Ms|Dr|St|Prof|Hr|Fr|Nr|bzw|ca|z\. ?B|u\. ?a)\.', r'\1', str(text))
    parts = [p for p in text.split('.') if p.strip()]
    return len(parts) >= 2 and all(words(p) <= 2 for p in parts) and not re.search(r'[!?]', text)


def check(title, beats, lines, problems, cast, duration, policy=POLICY):
    """Concrete, countable problems the planner gets back. Empty list = usable."""
    b = budget(duration, len(cast), policy); errors = list(problems)
    spoken = [l for l in lines if l['kind'] == 'line']; actions = [l for l in lines if l['kind'] == 'action']
    total = sum(words(l['text']) for l in spoken)
    if total < b['min_words']: errors.append(f'Zu wenig Dialog: {total} Wörter, nötig {b["min_words"]} bis {b["max_words"]} (Ziel {b["words"]}). Mehr Wortwechsel, längere natürliche Sätze.')
    if total > b['max_words']: errors.append(f'Zu viel Dialog: {total} Wörter, höchstens {b["max_words"]}. Kürzen, ohne die Pointe zu verlieren.')
    turns = sum(1 for i, l in enumerate(spoken) if not i or spoken[i - 1]['speaker'] != l['speaker'])
    if turns < b['min_turns']: errors.append(f'Zu wenig Sprecherwechsel: {turns}, nötig mindestens {b["min_turns"]}. Echte Wortwechsel schreiben.')
    if turns > b['max_turns']: errors.append(f'Zu viele Sprecherwechsel: {turns}, höchstens {b["max_turns"]}.')
    if len(actions) < b['min_actions']: errors.append(f'Zu wenig AKTION-Zeilen: {len(actions)}, nötig mindestens {b["min_actions"]}.')
    if len(actions) > b['max_actions']: errors.append(f'Zu viele AKTION-Zeilen: {len(actions)}, höchstens {b["max_actions"]}.')
    long = [l['text'] for l in spoken if words(l['text']) > MAX_LINE_WORDS]
    if long: errors.append(f'Zu lange Zeilen (mehr als {MAX_LINE_WORDS} Wörter) aufteilen: ' + ' | '.join(t[:60] for t in long[:3]))
    tele = [l['text'] for l in spoken if telegram(l['text'])]
    if tele: errors.append('Telegrammstil umschreiben in natürliche Sätze: ' + ' | '.join(tele[:4]))
    tiny = sum(1 for l in spoken if words(l['text']) <= 2)
    if spoken and tiny > max(2, len(spoken) // 4): errors.append(f'{tiny} Zeilen haben höchstens zwei Wörter. Höchstens jede vierte Zeile darf ein kurzer Ausruf sein.')
    if cast and len({l['speaker'] for l in spoken}) < min(2, len(cast)): errors.append('Mindestens zwei Figuren müssen miteinander sprechen.')
    count = len(ensure_action(shots(title, beats, lines, cast, policy), duration))
    if count > MAX_SHOTS: errors.append(f'Zu viele Einstellungen: {count}, höchstens {MAX_SHOTS}. Aufeinander folgende Zeilen derselben Figur zusammenfassen, weniger AKTION-Zeilen.')
    return errors


def emotion_of(raw):
    raw = (raw or '').lower()
    return next((e for e in EMOTIONS if e in raw or raw in e), raw or 'ruhig')


def spoken_seconds(entries):
    """Estimated speaking time of lines said in one go: 2.6 words/s plus a short pause between lines."""
    return sum(words(x['text']) for x in entries) / SPEECH_RATE + LINE_PAUSE * max(0, len(entries) - 1)


def shots(title, beats, lines, cast, policy=POLICY):
    """Deterministic cut. Policy 13: one shot per speaker turn, one per AKTION line.
    Policy 14: speech blocks, reaction shots (L-cut) and establishing shots, see block_cut()."""
    if policy >= 14: return block_cut(beats, lines, cast)
    result = []
    for line in lines:
        beat = beats[line['beat']] if line['beat'] < len(beats) else {'place': 'Ort', 'what': ''}
        if line['kind'] == 'action':
            visible = [c for c in cast if _mentions(line['text'], [c], [o for o in cast if o != c])][:2]
            result.append({'kind': 'action', 'beat': line['beat'], 'place': beat['place'], 'what': line['text'],
                           'visible': visible or ([result[-1]['visible'][0]] if result and result[-1]['visible'] else cast[:1]), 'lines': []})
            continue
        entry = {'speaker': line['speaker'], 'text': line['text'], 'emotion': emotion_of(line['emotion'])}
        last = result[-1] if result else None
        if (last and last['kind'] == 'line' and last['visible'] == [line['speaker']] and last['beat'] == line['beat']
                and sum(words(x['text']) for x in last['lines']) + words(line['text']) <= MERGE_WORDS and len(last['lines']) < 3):
            last['lines'].append(entry); continue
        result.append({'kind': 'line', 'beat': line['beat'], 'place': beat['place'], 'what': beat['what'],
                       'visible': [line['speaker']], 'lines': [entry]})
    return result


def block_cut(beats, lines, cast):
    """Policy 14 cut, in three steps.

    1) Blocks: consecutive lines of one speaker in one section share a lip-sync shot while
       their estimated length fits three lip-sync windows (8.6 s) and at most three lines.
    2) Establishing shots: a section at a new place opens with a silent wide shot (at most two
       per film, never before the first shot, not where an AKTION line already opens it).
    3) Reactions (L-cut at a line boundary): the last line of every second eligible block is
       heard off-screen over the listener's silent reaction. Never in the first or the last
       speaking block (hook and payoff stay on a face), only lines of at most 12 words, at most
       about a third of all speaking shots. The listener is the next other speaker of the same
       section, else the previous one; nobody from another place.
    Optional shots never push the film over MAX_SHOTS (one place stays free for ensure_action)."""
    result = []
    for line in lines:
        beat = beats[line['beat']] if line['beat'] < len(beats) else {'place': 'Ort', 'what': ''}
        if line['kind'] == 'action':
            visible = [c for c in cast if _mentions(line['text'], [c], [o for o in cast if o != c])][:2]
            result.append({'kind': 'action', 'beat': line['beat'], 'place': beat['place'], 'what': line['text'],
                           'visible': visible or ([result[-1]['visible'][0]] if result and result[-1]['visible'] else cast[:1]), 'lines': []})
            continue
        entry = {'speaker': line['speaker'], 'text': line['text'], 'emotion': emotion_of(line['emotion'])}
        last = result[-1] if result else None
        if (last and last['kind'] == 'line' and last['visible'] == [line['speaker']] and last['beat'] == line['beat']
                and len(last['lines']) < 3 and spoken_seconds(last['lines'] + [entry]) <= MERGE_SECONDS):
            last['lines'].append(entry); continue
        result.append({'kind': 'line', 'beat': line['beat'], 'place': beat['place'], 'what': beat['what'],
                       'visible': [line['speaker']], 'lines': [entry]})
    # Few establishing shots first (a new place matters more than one more reaction), then reactions.
    room = lambda shots: MAX_SHOTS - len(shots) - (0 if any(s['kind'] == 'action' for s in shots) else 1)
    result = _establishing(result, beats, room(result))
    return _reactions(result, room(result))


def _listener(result, index):
    """(listener, emotion of the reaction) for the block at `index`, or (None, None)."""
    speaker = result[index]['visible'][0]; beat = result[index]['beat']
    others = lambda shots: [l for s in shots if s['kind'] == 'line' and s['beat'] == beat for l in s['lines'] if l['speaker'] != speaker]
    later = others(result[index + 1:])
    # The listener answers next: the reaction already carries the emotion of that answer.
    if later: return later[0]['speaker'], later[0]['emotion']
    earlier = others(result[:index])
    return (earlier[-1]['speaker'], 'ruhig') if earlier else (None, None)


def _reactions(result, room):
    speaking = [i for i, s in enumerate(result) if s['kind'] == 'line']
    eligible = []
    for i in speaking[1:-1]:
        block = result[i]
        if len(block['lines']) < 2 or words(block['lines'][-1]['text']) > REACTION_WORDS: continue
        who, mood = _listener(result, i)
        if who: eligible.append((i, who, mood))
    chosen = {i: (who, mood) for i, who, mood in eligible[::2][:max(0, min(room, len(speaking) // 2))]}
    out = []
    for i, shot in enumerate(result):
        if i not in chosen:
            out.append(shot); continue
        who, mood = chosen[i]; heard = shot['lines'][-1]
        out.append(dict(shot, lines=shot['lines'][:-1]))
        out.append({'kind': 'reaction', 'beat': shot['beat'], 'place': shot['place'], 'what': shot['what'], 'visible': [who],
                    'lines': [heard], 'voice_of': heard['speaker'], 'emotion': mood})
    return out


def _place_key(place):
    return re.sub(r'[\W_]+', '', str(place).lower())


def _establishing(result, beats, room):
    out, seen, added = [], set(), 0
    for i, shot in enumerate(result):
        key = _place_key(shot['place'])
        opens = i and result[i - 1]['beat'] != shot['beat']
        if opens and key and key not in seen and shot['kind'] != 'action' and added < min(MAX_ESTABLISH, room):
            figures = list(dict.fromkeys(n for s in result if s['beat'] == shot['beat'] for n in s['visible']))[:2]
            what = beats[shot['beat']]['what'] if shot['beat'] < len(beats) else ''
            out.append({'kind': 'establish', 'beat': shot['beat'], 'place': shot['place'], 'what': what, 'visible': figures, 'lines': []})
            added += 1
        seen.add(key); out.append(shot)
    return out


# Possessive / genitive after a name: 's, ’s, s, or a bare apostrophe after s ("Mr. Krabs' office").
SUFFIX = r"(?P<pos>['’]s|s|(?<=s)['’](?!\w))?"
TITLES = {'mr', 'mrs', 'ms', 'dr', 'jr', 'sr', 'st', 'prof', 'herr', 'herrn', 'frau', 'the', 'der', 'die', 'das', 'von', 'van', 'de', 'of', 'le', 'la'}
# English role words for German family names: 'Tims Oma' is 'Grandma' in an English still.
ROLES = {'oma': ('grandma', 'granny', 'grandmother', 'nana'), 'opa': ('grandpa', 'granddad', 'grandfather'),
         'mama': ('mom', 'mum', 'mommy', 'mummy', 'mother'), 'mutter': ('mom', 'mum', 'mother'), 'papa': ('dad', 'daddy', 'father'),
         'vater': ('dad', 'father'), 'tante': ('aunt', 'auntie'), 'onkel': ('uncle',), 'oma': ('grandma', 'granny', 'grandmother', 'nana')}
FOLD = str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ß': 'ss'})
PLAIN = str.maketrans({'ä': 'a', 'ö': 'o', 'ü': 'u', 'Ä': 'A', 'Ö': 'O', 'Ü': 'U'})


def _forms(word):
    """Spellings of one name: as written, without dots ('Mr Krabs', 'Bowser Jr'), joined
    ('Tinkerbell'), without umlauts ('Thaddaeus'), genitive with apostrophe ("Tim's Oma"),
    declined title ('Herrn Müller')."""
    forms = {word, word.replace('.', '').strip(), word.translate(FOLD), word.translate(PLAIN)}
    words = word.split()
    if len(words) == 2 and all(w[:1].isupper() for w in words) and words[0].lower().strip('.') not in TITLES:
        forms.add(''.join(words))
    if len(words) >= 2 and len(words[0]) > 2 and words[0].endswith('s'):
        forms |= {words[0][:-1] + q + ' ' + ' '.join(words[1:]) for q in ("'s", '’s')}
    if word.startswith('Herr '): forms.add('Herrn ' + word[5:])
    return {f for f in forms if f}


def _variants(word):
    return {v for f in _forms(word) for v in (f, f.upper(), f.capitalize(), f[:1].upper() + f[1:])}


def _words(name):
    return [q for q in re.split(r'[\s.]+', name) if q]


def _parts(name):
    """Name parts that stand for the figure: words of 4+ letters, and the first and last
    word of a longer name ('Kim' in 'Kim Possible', 'Oma' in 'Tims Oma')."""
    words = _words(name)
    parts = {q for q in words if len(q) >= 4 and q.lower() not in TITLES}
    if len(words) > 1:
        parts |= {q for q in (words[0], words[-1]) if len(q) >= 3 and q[0].isupper() and q.lower() not in TITLES}
    return parts


def _roles(name):
    return {r for q in _words(name) for r in ROLES.get(q.lower(), ())}


def name_patterns(names, protected=()):
    """Regexes for figure names: the full name and its parts, as written, capitalised or in
    capitals, with possessive ending; English role words in any case ('grandma'). Never a
    plain lower-case name, so 'sandy seabed' or 'stars' stay; never a part or role that
    also belongs to a protected (visible) figure ('Captain' when only Captain Hook is off-screen)."""
    keep = {q.lower() for v in protected for q in _words(v)}
    keep_roles = {r for v in protected for r in _roles(v)}
    out = []
    for name in names:
        for word in {name} | {q for q in _parts(name) if q.lower() not in keep}:
            alternatives = '|'.join(re.escape(v) for v in sorted(_variants(word), key=len, reverse=True))
            out.append(re.compile(r"(?<!\w)(?:" + alternatives + r")" + SUFFIX + r"(?!\w)"))
        roles = sorted(_roles(name) - keep_roles, key=len, reverse=True)
        if roles: out.append(re.compile(r'(?<!\w)(?i:' + '|'.join(roles) + r')' + SUFFIX + r'(?!\w)'))
    return out


def _full_spans(text, names):
    """(start, end) of every full name (any listed spelling, with possessive ending)."""
    return [m.span() for name in names for variant in _variants(name)
            for m in re.finditer(r'(?<!\w)' + re.escape(variant) + SUFFIX + r'(?!\w)', text)]


def _blank(text, protected, names=()):
    """Hide full names of protected figures before matching others ('Tims Mama' is not 'Tim').
    Where a protected name overlaps a longer full name of a figure we look for, the
    longer one wins: protecting 'Tim' must not eat the 'Tims' of 'Tims Oma'."""
    text = str(text)
    targets = _full_spans(text, names)
    for a, b in sorted(_full_spans(text, protected), key=lambda s: s[0] - s[1]):
        if any(x < b and a < y and y - x > b - a for x, y in targets): continue
        text = text[:a] + ' ' * (b - a) + text[b:]
    return text


def _spans(text, names, protected=()):
    """Mentions of names as (start, end, possessive), longest first at each start, no overlaps."""
    masked = _blank(text, protected, names)
    found = sorted({(m.start(), m.end(), bool(m.group('pos'))) for p in name_patterns(names, protected) for m in p.finditer(masked)},
                   key=lambda s: (s[0], -s[1]))
    out = []
    for span in found:
        if out and span[0] < out[-1][1]: continue
        out.append(span)
    return out


def _mentions(text, names, protected=()):
    return bool(_spans(str(text), names, protected))


def figure_aliases(cast):
    """Other names the planner may use for a figure: the original's own name
    ('Squidward Tentacles' for 'Thaddäus', from 'original')."""
    out = {}
    for person in cast or []:
        if not isinstance(person, dict): continue
        own = str(person.get('original') or '').partition(' from ')[0].strip()
        if own and own.lower() != str(person.get('name', '')).lower(): out[person['name']] = [own]
    return out


def _expand(names, aliases):
    return list(names) + [a for n in names for a in (aliases or {}).get(n, []) if a not in names]


TITLE = r'(?:(?<!\w)(?:Mr|Mrs|Ms|Dr|Prof|Herrn?|Frau)\.?\s+)'
ARTICLE = r'(?i:the|a|an|his|her|their|its|der|die|das|den|dem|ein|eine|einen|sein|seine|ihr|ihre)'
PREPOSITION = (r'(?<!\w)(?i:at|to|toward|towards|with|behind|beside|next to|near|from|for|of|by|on|onto|into|in|inside|under|over|above|around|'
               r'against|like|than|past|mit|zu|zum|zur|neben|hinter|vor|bei|von|vom|an|am|auf|unter|über|gegen|für|um|ohne|laut)\s+')
BEFORE_NAME = re.compile('(?:' + PREPOSITION + ')?' + TITLE + '?$')
AFTER_PREPOSITION = re.compile(PREPOSITION + '(?:' + ARTICLE + r'\s+)?' + TITLE + '?$')
BEFORE_TITLE = re.compile(TITLE + '?$')
PRONOUN = re.compile(r'\s*(?i:he|she|they|it|we|er|sie|es|wir)\b')
# Sentence ends, punctuation, dashes and linking words split clauses; not after a title
# ('Mr. Krabs' stays one name). A linking word splits only before a new subject (a name or an
# article): 'while Plankton watches', 'as the crocodile ticks'; not 'runs as fast as he can'.
LINK = (r'(?i:while|whereas|as|when|whenever|where|because|until|although|but|or|während|als|wie|wo|weil|wenn|sobald|nachdem|bevor|obwohl|aber|doch|oder)')
DELIMS = re.compile(r'(,|;|:|\s+[-–—]\s+|[–—]|\n+|\s(?i:and then|und dann|then|dann)\b|\b(?i:who)\b|'
                    r'\b' + LINK + r'\b(?=\s+(?:[A-ZÄÖÜ]|' + ARTICLE + r'\b))|'
                    r'(?<=[.!?])(?<!\bMr\.)(?<!\bMrs\.)(?<!\bMs\.)(?<!\bDr\.)(?<!\bSt\.)(?<!\bJr\.)(?<!\bHr\.)(?<!\bFr\.)(?<!\bProf\.)\s+)')
# ', der auf einem Stein schläft' is a relative clause; ', die blaue Mütze im Gesicht' is not.
RELATIVE = re.compile(r'^\s*(?:(?i:who|whose|whom)\b|(?:der|die|das|dem|den|deren|dessen)\s+(?![A-ZÄÖÜ])(?!(?!(?:der|die|das|dem|den)\b)[a-zäöüß]+(?:e|en|er|es|em)\s+[A-ZÄÖÜ]))')
PARTICLES = {'', 'zu', 'an', 'auf', 'mit', 'ab', 'aus', 'ein', 'vor', 'nach', 'her', 'hin', 'zurück', 'nach', 'hinterher'}


def _strip(text, names, protected):
    """Remove mentions of names, never inside a protected full name ('Captain Hook'
    goes, 'Captain Smee' stays; 'Tim' does not cut into 'Tims Mama'). A title and a
    preposition in front go too ('waves to Mr Krabs', 'hinter Thaddäus'); in front of
    a possessive only the title ('into Mr. Krabs' office' -> 'into office')."""
    out, last = '', 0
    for a, b, possessive in _spans(text, names, protected):
        if a < last: continue
        if last and re.fullmatch(r'\s*(?:,\s*)?(?:(?:and|und|sowie|&)\s*)?', text[last:a]):
            a = last                                     # 'Patrick und Sandy': the joiner goes with both
        else:
            a = max(last, (BEFORE_TITLE if possessive else BEFORE_NAME).search(text[:a]).start())
        epithet = re.match(r'\s+the\s+[A-Z][\w-]+', text[b:])          # 'Perry the Platypus'
        out += text[last:a]; last = b + (epithet.end() if epithet and not possessive else 0)
    return out + text[last:]


def _is_list(text, start, end, opening=False):
    """Names joined by and/und are one subject or object ('Phineas und Ferb bauen',
    'grins at Patrick and Sandy') when they open a clause or end in punctuation, an
    article or a preposition; 'Peach umarmt Mario und Toad jubelt' are two clauses."""
    before = text[:start]
    # Not after a preposition: 'grins at Sandy and Patrick waves' is an object and a new clause.
    opens = opening or not before.strip() or re.search(r'(?:[.!?,;:\n]|\b' + LINK + r')\s*$', before)
    ends = re.match(r'\s*(?:$|[.!?,;:)\n]|(?:' + ARTICLE + r'|with|to|at|from|for|mit|zu|von|bei|je|both|beide|together|zusammen)\b)', text[end:])
    return bool(opens or ends)


def _groups(text, visible, hidden):
    """A list of names is one subject: its off-screen members leave the list and the
    visible ones keep the action ('Phineas und Ferb bauen' -> 'Ferb bauen')."""
    names = sorted([(a, b, p, True) for a, b, p in _spans(text, visible, hidden)] +
                   [(a, b, p, False) for a, b, p in _spans(text, hidden, visible)])
    runs, run = [], []
    for span in names:
        gap = text[run[-1][1]:span[0]] if run else ''
        if run and not run[-1][2] and gap.strip() and re.fullmatch(r'\s*(?:,\s*)?(?:(?:and|und|sowie|&)\s*)?|\s*,\s*', gap):
            run.append(span)
        else:
            if len(run) > 1: runs.append(run)
            run = [span]
    if len(run) > 1: runs.append(run)
    lists = []
    for run in runs:
        if _is_list(text, run[0][0], run[-1][1]): lists.append(run); continue
        # 'SpongeBob hugs Sandy, Patrick and Plankton cry': the list starts after the comma.
        pieces, piece = [], [run[0]]
        for x, y in zip(run, run[1:]):
            if ',' in text[x[1]:y[0]]: pieces.append(piece); piece = [y]
            else: piece.append(y)
        pieces.append(piece)
        lists += [p for i, p in enumerate(pieces) if len(p) > 1 and _is_list(text, p[0][0], p[-1][1], opening=i > 0)]
    for run in sorted(lists, reverse=True):
        gaps = [text[x[1]:y[0]] for x, y in zip(run, run[1:])]
        kept = [text[a:b] for a, b, _, seen in run if seen]
        if not kept or len(kept) == len(run) or not any(re.search(r'\b(?:and|und|sowie)\b|&', g) for g in gaps): continue
        word = 'und' if any('und' in g for g in gaps) else 'and'
        joined = kept[0] if len(kept) == 1 else ', '.join(kept[:-1]) + f' {word} ' + kept[-1]
        text = text[:run[0][0]] + joined + text[run[-1][1]:]
    return text


def _coordinated(clause, cast):
    """'SpongeBob laughs and Patrick cries' is two clauses: split before 'and/und [title or
    article] <Name>' unless the names around 'and' form a list or the name is a possessive."""
    spans = _spans(clause, cast)
    pieces, last = [], 0
    for i, (a, b, possessive) in enumerate(spans):
        m = re.search(r'\s(and|und|&)\s+(?:' + TITLE + '|' + ARTICLE + r'\s+(?:[a-zäöüß-]+\s+){0,2})?$', clause[last:a])
        if not m or possessive: continue
        if i and not clause[spans[i - 1][1]:last + m.start()].strip() and _is_list(clause, spans[i - 1][0], b): continue
        pieces += [clause[last:last + m.start()], m.group(1)]; last = last + m.start() + 1 + len(m.group(1))
    return pieces + [clause[last:]]


def sanitize(text, visible, cast, aliases=None):
    """Image and motion text may only describe figures in the frame.

    The image model draws every figure it reads about, without a reference, so as a
    wrong or blended figure. A clause whose subject is off-screen is dropped ("Mr.
    Krabs grabs SpongeBob", "SpongeBob laughs and Patrick cries" -> "SpongeBob
    laughs"), and so is what continues it ("…, waving his arms"); off-screen
    co-subjects, objects and possessives lose only the name ("Phineas und Ferb bauen"
    -> "Ferb bauen", "waves at Squidward" -> "waves")."""
    visible = [n for n in visible if n in cast] or list(visible)
    seen_names = _expand(visible, aliases)
    hidden_names = _expand([n for n in cast if n not in visible], aliases)
    hidden_names = [n for n in hidden_names if n not in seen_names]
    every = seen_names + hidden_names
    text = _groups(str(text or ''), seen_names, hidden_names)
    # Never split inside a name ('Herr Dann', 'Spider–Man', 'Batman: Beyond').
    names_at = [(a, b) for a, b, _ in _spans(text, every)]
    parts, last = [], 0
    for m in DELIMS.finditer(text):
        if any(a < m.end() and m.start() < b for a, b in names_at): continue
        parts += [text[last:m.start()], m.group(0)]; last = m.end()
    parts.append(text[last:])
    pieces = [(parts[0], '')] + list(zip(parts[2::2], parts[1::2]))
    clauses = []
    for clause, delim in pieces:
        sub = _coordinated(clause, every)
        clauses += [(sub[0], delim)] + list(zip(sub[2::2], sub[1::2]))
    out, last_name, prev_dropped, owner, lost, first, sentence_owner = '', None, False, None, False, True, None
    carry = ''                                          # punctuation in front of an empty piece (', who …')
    for clause, delim in clauses:
        d = delim.strip()
        boundary = not d                                # start of text or of a sentence
        if boundary: prev_dropped, first, sentence_owner = False, True, None
        if not clause.strip():
            carry = d if d in (',', ';', ':') else carry; continue
        # 'Als Plankton kommt, versteckt sich SpongeBob': a fronted subordinate clause does not
        # carry its fate over to the main clause after it.
        fronted = first and bool(re.fullmatch(LINK, d)); first = False
        dropped = False
        relative = d.lower() == 'who' or bool(RELATIVE.match(clause))
        if relative and last_name:
            # 'who dodges' belongs to the figure named just before it: gone with it if that
            # figure is off-screen; named again if only its clause was dropped.
            if not last_name[1]:
                prev_dropped = lost = True; continue
            if last_name[2]:
                clause = last_name[0] + ' ' + re.sub(r'^\s*(?:(?i:who)|der|die|das|dem|den)\b\s*', '', clause)
                d = ''
        gone = _spans(clause, hidden_names, seen_names)
        seen = _spans(clause, seen_names, hidden_names)
        start = len(clause) - len(clause.lstrip())
        pronoun = PRONOUN.match(clause)
        named_first = any(s[0] <= start + 4 for s in gone + seen)
        if boundary and pronoun and owner == 'hidden': dropped = True           # 'Patrick bursts in. He grabs …'
        elif not boundary and prev_dropped and not (named_first or pronoun or clause.lstrip()[:1].isupper()):
            dropped = True                                                     # continues a dropped clause
        else:
            # A possessive at the start is the subject's owner: "Sandy's helmet glints" is about
            # Sandy unless a visible figure takes part ("Plankton's robot chases SpongeBob").
            subject = [s for s in gone if (not s[2] or (not seen and s[0] <= start + 4)) and not AFTER_PREPOSITION.search(clause[:s[0]])]
            own = [s for s in seen if not s[2] and not AFTER_PREPOSITION.search(clause[:s[0]])]
            if pronoun: own = [(start, start, False)] + own
            # 'Mr. Krabs, rot vor Wut, packt SpongeBob': a comma piece starting with a verb
            # continues the visible subject before it; the names in it are objects.
            if d in (',', ';') and sentence_owner == 'visible' and clause.lstrip()[:1].islower() and not pronoun: subject = []
            if subject and (not own or subject[0][0] < own[0][0]): dropped = True; owner = sentence_owner = 'hidden'
            elif own: owner = sentence_owner = 'visible'
        named = sorted([(s, True) for s in seen] + [(s, False) for s in gone])
        tail = named[-1] if named and clause[named[-1][0][1]:].strip(' .!?').lower() in PARTICLES else None
        last_name = (clause[tail[0][0]:tail[0][1]], tail[1], dropped) if tail else (last_name if not named else None)
        if not dropped and gone:
            clause = re.sub(r'(?<!\w)(?i:at|to|with|towards|and|und|&)\s*(?=[,.!?]|$)', '', _strip(clause, hidden_names, seen_names)).rstrip()
            dropped = not clause.strip(' .!?,;:')
        prev_dropped = dropped and not fronted
        if dropped:
            lost = True; continue
        if out:
            # The delimiter belongs to the clause after it; a dropped sentence end is restored.
            sentence = out[-1] in '.!?'
            if not d: out += ' ' if sentence else '. '
            elif d in (',', ';', ':'): out += ' ' if sentence else d + ' '
            else: out += (carry if carry and not sentence else '') + f' {d} '
        elif d and not lost and re.fullmatch(LINK + '|(?i:and then|und dann|then|dann)', d):
            out = d + ' '                                # the text opens with it: 'Als Plankton kommt, …'
        out += clause.strip(); carry = ''
    out = re.sub(r'\s{2,}', ' ', re.sub(r'\s+([,.;:!?])', r'\1', out))
    return out.strip(' ,;:-–—')


def ensure_action(cut, duration):
    """Missing time needs a silent shot to go to; otherwise it ends up as silence in
    lip-sync shots (mouths move without a voice). If the planner wrote no AKTION
    line, a short silent reaction of the figure who spoke last is added mid-film."""
    if duration < 30 or not cut or any(s['kind'] == 'action' for s in cut): return cut
    middle = len(cut) // 2
    # Policy 14: never between a block and the reaction that carries its last line.
    while middle < len(cut) and cut[middle]['kind'] == 'reaction': middle += 1
    before = cut[max(0, middle - 1)]
    # An establishing shot may show nobody: take the last shot with a figure.
    who = next((s['visible'][:1] for s in reversed(cut[:middle]) if s['visible']), before['visible'][:1])
    reaction = {'kind': 'action', 'beat': before['beat'], 'place': before['place'], 'visible': who, 'lines': [],
                'what': f'{who[0] if who else "Die Figur"} reagiert stumm mit einer großen, deutlichen Geste.'}
    return cut[:middle] + [reaction] + cut[middle:]


def beat_label(index, count, cliffhanger):
    if index == 0: return 'problem'
    if index == count - 1: return 'cliffhanger' if cliffhanger else 'payoff'
    if cliffhanger and index == count - 2: return 'payoff'
    return 'turn' if index == round(count * .65) else 'attempt'


SPEAK_CAMERAS = ('medium shot', 'medium close-up', 'low angle medium shot')


def assemble(title, spine, outline, cut, visuals, cast, continuity, policy=POLICY):
    """EpisodePlan-compatible dict; old downstream code keeps working. Policy 14 adds two shot
    kinds that exist only here: 'reaction' (with voice_of) and 'establish'. They are never
    validated against factory_models.Shot, whose JSON schema the older scene planner still sends
    to the model unchanged."""
    by_number = {v['shot']: v for v in (visuals or {}).get('shots', [])}
    scenes = []
    for i, shot in enumerate(cut):
        v = by_number.get(i + 1, {})
        if policy >= 14 and shot['kind'] in ('reaction', 'establish'):
            scenes.append(_cut_scene(i, shot, v, cut, cast, continuity)); continue
        visible = shot['visible']
        speaker = shot['lines'][0]['speaker'] if shot['lines'] else ''
        fallback_still = (f'{" and ".join(visible)} in {shot["place"]}, ' + (f'{speaker} speaking, {expression(shot["lines"][0]["emotion"])} expression' if speaker else shot['what']))
        names = [c['name'] for c in cast]; aliases = figure_aliases(cast)
        still = sanitize(v.get('still') or fallback_still, visible, names, aliases)
        if len(still) < 10: still = sanitize(fallback_still, visible, names, aliases) or f'{" and ".join(visible)} in {shot["place"]}'
        if policy >= 14 and not speaker and visible:
            # A silent face keeps its mouth closed: in Cay's 0.17 film a grin in the still became a
            # mouth moving without any voice.
            still = still[:580].rstrip(' .,') + (', mouth closed' if len(visible) == 1 else ', mouths closed')
        motion = sanitize(v.get('motion') or ('talks with expressive face and natural gestures' if speaker else shot['what']), visible, names, aliases)
        if len(motion) < 5: motion = 'talks with expressive face and natural gestures' if speaker else 'moves quickly with a clear physical action'
        scenes.append({
            'title': (shot['what'] if shot['kind'] == 'action' else f'{speaker}: {shot["lines"][0]["text"]}')[:100] or f'Einstellung {i + 1}',
            # At least 5 characters: the text editor validates action with min_length 5.
            'action': (shot['what'] if len(shot['what'].strip()) >= 5 else (f'{speaker} spricht in {shot["place"]}.' if speaker else f'Stumme Szene in {shot["place"]}.'))[:800],
            'location': shot['place'][:250] or 'Ort',
            'camera': ((v.get('camera') or ('medium shot' if speaker else 'wide shot')) if policy < 14 else _camera(i, shot, v, cut, scenes))[:250],
            'cast': visible,
            'dialogue': '', 'speaker': '', 'emotion': shot['lines'][0]['emotion'] if shot['lines'] else 'Natürlich',
            'continuity': 'same location and lighting as the previous shot',
            'beat': beat_label(i, len(cut), bool(continuity.get('end_with'))),
            'because': 'Fortsetzung des Gesprächs' if i else 'Einstieg',
            'dialogues': [{'speaker': l['speaker'], 'text': l['text'], 'emotion': l['emotion'], 'pause_after': .15} for l in shot['lines']],
            'ambience': v.get('ambience') if v.get('ambience') in AMBIENCE else 'room',
            'sound_cues': [],
            'motion': [motion],
            'animation_prompt': motion[:1400],
            'still': still[:600],
            'kind': shot['kind'],
        })
    spine = spine or {}
    return {'title': (title or outline.get('title') or 'Folge')[:100],
            'goal': (spine.get('goal') or outline.get('plot', ''))[:400] or 'Ziel',
            'obstacle': (spine.get('stakes') or (spine.get('escalations') or [''])[0] or 'Hindernis')[:400],
            'resolution': (spine.get('payoff') or outline.get('ending', ''))[:400] or 'Auflösung',
            'scenes': scenes, 'story_policy': policy, 'dialogue_mode': 'rich', 'script': 'screenplay'}


def _same_framing(a, b):
    return str(a).strip().lower() == str(b).strip().lower()


def _camera(i, shot, v, cut, scenes):
    """Policy 14 framing: the planner's choice, else speaking shots alternate medium shot,
    medium close-up and low angle. Two speaking shots in a row never share a framing (Cay's
    film: thirteen frontal medium shots), and after a close-up reaction the same figure
    speaks in a medium shot, not in a second close-up (a jump cut)."""
    if shot['kind'] != 'line': return v.get('camera') or 'wide shot'
    k = sum(1 for s in cut[:i] if s['kind'] == 'line')
    camera = v.get('camera') or SPEAK_CAMERAS[k % len(SPEAK_CAMERAS)]
    before = cut[i - 1] if i else None
    if not before: return camera
    if before['kind'] == 'reaction' and before['visible'] == shot['visible'] and 'close' in camera.lower(): return 'medium shot'
    if before['kind'] == 'line' and scenes and _same_framing(camera, scenes[-1]['camera']):
        return next(c for c in SPEAK_CAMERAS if not _same_framing(c, camera))
    return camera


def _cut_scene(i, shot, v, cut, cast, continuity):
    """A reaction (the listener in the frame, the voice off-screen) or an establishing shot.
    The off-screen speaker is never named in the picture or motion text."""
    names = [c['name'] for c in cast]; aliases = figure_aliases(cast); visible = shot['visible']; place = shot['place']
    common = {'location': place[:250] or 'Ort', 'cast': visible, 'dialogue': '', 'speaker': '',
              'continuity': 'same location and lighting as the previous shot', 'beat': beat_label(i, len(cut), bool(continuity.get('end_with'))),
              'ambience': v.get('ambience') if v.get('ambience') in AMBIENCE else 'room', 'sound_cues': [], 'kind': shot['kind']}
    if shot['kind'] == 'reaction':
        listener, speaker, mood = visible[0], shot['voice_of'], shot['emotion']
        own_still = f'Close-up of {listener} in {place}, listening in silence to a voice from outside the frame, {reaction_expression(mood)}'
        still = sanitize(v.get('still') or '', visible, names, aliases)
        if len(still) < 10 or OPEN_MOUTH.search(still): still = sanitize(own_still, visible, names, aliases)
        own_motion = f'listens in silence with lips closed, {reaction_gesture(mood)}'
        motion = sanitize(v.get('motion') or '', visible, names, aliases)
        if len(motion) < 5 or OPEN_MOUTH.search(motion): motion = own_motion
        return {**common, 'title': f'Reaktion: {listener} hört {speaker} zu'[:100],
                'action': f'{listener} hört schweigend zu, die Stimme von {speaker} kommt aus dem Off.'[:800],
                'camera': 'close-up', 'emotion': mood, 'because': f'Reaktion auf {speaker}'[:400],
                'dialogues': [{'speaker': l['speaker'], 'text': l['text'], 'emotion': l['emotion'], 'pause_after': .15} for l in shot['lines']],
                'motion': [motion], 'animation_prompt': motion[:1400], 'still': still[:600], 'voice_of': speaker}
    own_still = f'Wide establishing view of {place}' + (f', {" and ".join(visible)} small in the frame' if visible else ', no characters')
    still = sanitize(v.get('still') or '', visible, names, aliases)
    if len(still) < 10 or OPEN_MOUTH.search(still): still = sanitize(own_still, visible, names, aliases) or f'Wide view of {place}'
    # The planner may describe the figures up close; this shot exists to show the place.
    if not re.search(r'(?i)\bwide\b', still): still = 'Wide establishing view, ' + still
    motion = sanitize(v.get('motion') or '', visible, names, aliases)
    if len(motion) < 5: motion = 'slow smooth camera movement across the location, calm natural movement'
    what = shot['what'].strip()
    return {**common, 'title': f'Totale: {place}'[:100], 'action': (what if len(what) >= 5 else f'Weite Ansicht: {place}.')[:800],
            'camera': 'wide establishing shot', 'emotion': 'Natürlich', 'because': 'Neuer Ort', 'dialogues': [],
            'motion': [motion], 'animation_prompt': motion[:1400], 'still': still[:600]}


def render_text(title, beats, lines):
    """Back to the screenplay format, e.g. to show the planner its own last valid draft."""
    out = [f'TITEL: {title}'] if title else []; current = None
    for line in lines:
        if line['beat'] != current:
            current = line['beat']; b = beats[current] if current < len(beats) else {'place': '', 'what': ''}
            out.append(f'# {current + 1} | {b["place"]} | {b["what"]}')
        out.append(f'AKTION: {line["text"]}' if line['kind'] == 'action' else f'{line["speaker"].upper()} [{line["emotion"]}]: {line["text"]}')
    return '\n'.join(out)


async def repair_visuals(factory, d, cut, listing, answer, instruction=VISUAL_INSTRUCTION):
    """The planner writes the image text; it also gets its own mistakes back. Shots whose
    still or motion name an off-screen figure are written again once with that error
    (local model, about a minute). The text filter stays the last safety net."""
    names = [c['name'] for c in d['plan']['cast']]; aliases = figure_aliases(d['plan']['cast'])
    wrong = {}
    for v in answer['shots']:
        shot = cut[v['shot'] - 1]
        others = offscreen_names(v.get('still', '') + ' ' + v.get('motion', ''), shot['visible'], names, aliases)
        if others: wrong[v['shot']] = others
    if not wrong: return answer
    ask = [dict(x, error='nennt ' + ', '.join(wrong[x['shot']]) + ', nicht im Bild') for x in listing if x['shot'] in wrong]
    try:
        fixed = await factory.llm(ShotVisuals, instruction + ' ' + VISUAL_REPAIR + ' Genau diese Nummern: ' + ', '.join(map(str, wrong)) + '.',
                                  {'style': d['plan'].get('style', ''), 'cast': d['plan']['cast'], 'shots': ask})
    except Exception:
        # Advisory only: a timeout, a crashed model or a busy GPU must not stop the planning
        # (CancelledError is no Exception and still stops it). sanitize() removes the names.
        return answer
    better = {v['shot']: v for v in fixed['shots'] if v['shot'] in wrong
              and not offscreen_names(v.get('still', '') + ' ' + v.get('motion', ''), cut[v['shot'] - 1]['visible'], names, aliases)}
    return {**answer, 'shots': [better.get(v['shot'], v) for v in answer['shots']]}


def shot_listing(entry, shot):
    """Policy 14: the shot's role in the cut. A reaction lists what the listener hears, not
    who says it: the off-screen speaker must not end up in the picture text."""
    entry = dict(entry, role=SHOT_ROLES.get(shot['kind'], shot['kind']))
    if shot['kind'] == 'reaction': entry.update(lines=[], hears=shot['lines'][0]['text'] if shot['lines'] else '')
    return entry


async def write_episode(factory, d, index, outline, source, continuity, spine, own=None):
    """Screenplay -> check -> doctor -> shots -> visuals. Stored drafts survive a restart.

    own (0.18, 'Mein Drehbuch'): Cay's script in the internal format (own_script.read). It is the
    final screenplay as it is: no draft, no Script Doctor, no invented AKTION (ensure_action), its
    check results are advisory notes. Only the image and motion text come from the planner."""
    idea = d['idea']; cast = [p['name'] for p in d['plan']['cast']]
    stores = d.setdefault('screenplays', {}); store = stores.setdefault(str(index), {})
    # Pinned with the screenplay and per project: a project that began writing screenplays before
    # 0.18 (a stored draft without a policy, or an episode planned with 13) keeps the 0.17 rules
    # and cut for all its episodes, so a series does not change its cut halfway.
    started = (any(s.get('policy', LEGACY_POLICY if s.get('draft') or s.get('final') else None) == LEGACY_POLICY for s in stores.values())
               or any(ep.get('script') == 'screenplay' and ep.get('story_policy', LEGACY_POLICY) == LEGACY_POLICY for ep in d.get('episodes', [])))
    policy = store.setdefault('policy', LEGACY_POLICY if started else POLICY)
    # After the pin: a stored text without a policy would read as a screenplay from before 0.18.
    if own is not None: store.update(final=own, own=True)
    b = budget(idea['duration'], len(cast), policy)
    context = {'idee_des_nutzers': source, 'serie': {k: v for k, v in d['plan'].items() if k not in ('episodes',)},
               'folge': index + 1, 'folgen_gesamt': idea['episodes'], 'outline': outline, 'ziel_des_films': spine,
               'fortsetzung': continuity, 'dauer_sekunden': idea['duration'],
               'wortbudget': {'ziel': b['words'], 'mindestens': b['min_words'], 'höchstens': b['max_words']},
               'sprecherwechsel': {'mindestens': b['min_turns'], 'höchstens': b['max_turns']},
               'aktion_zeilen': {'mindestens': b['min_actions'], 'höchstens': b['max_actions']},
               'vorherige_folgen': [{'title': x['title'], 'resolution': x.get('resolution', '')} for x in d['episodes']]}
    series = ('Serie: Ist fortsetzung.pick_up gesetzt, greift die erste Zeile diesen offenen Punkt sofort auf. '
              'Ist fortsetzung.end_with gesetzt, wird die Hauptfrage vorher aufgelöst und der letzte Abschnitt zeigt genau diesen Cliffhanger. ')
    instruction = ('Du bist Head-Autor für virale deutsche Kurzfilme auf TikTok und YouTube Shorts. Schreibe das komplette Drehbuch dieser Folge '
                   f'als ein durchgehendes Gespräch für etwa {idea["duration"]} Sekunden. Gesamt {b["min_words"]} bis {b["max_words"]} gesprochene Wörter '
                   f'(Ziel {b["words"]}), ' + (f'{b["min_turns"]} bis {b["max_turns"]} Sprecherwechsel, ' if len(cast) > 1 else 'ein Monolog der einzigen Figur, ')
                   + f'{b["min_actions"]} bis {b["max_actions"]} AKTION-Zeilen, höchstens {MAX_SHOTS} Einstellungen. '
                   + series + rules(policy) + '\n' + FORMAT + '\n' + example(policy))
    def problems(text): return check(*parse(text, cast), cast, idea['duration'], policy)
    if not store.get('final'):
        draft = store.get('draft')
        if not draft:
            d['phase'] = f'Folge {index + 1}: Drehbuch schreiben'; factory.save(d)
            draft = await factory.write(instruction, context, label='Drehbuch', check=problems)
            store['draft'] = draft; factory.save(d)
        d['phase'] = f'Folge {index + 1}: Drehbuch überarbeiten (Script Doctor)'; factory.save(d)
        doctor = ('Du bist Script Doctor für virale Kurzfilme. Lies das Drehbuch laut im Kopf, Zeile für Zeile. Finde: Zeilen ohne Sinn oder Bezug, '
                  'Antworten, die nicht reagieren, Logikfehler (wer hat was, wo ist wer), fehlende Spannung oder Steigerung, schwache Pointe, '
                  'Telegrammstil, Wiederholungen, Figuren, die nicht wie sie selbst klingen. Verbessere alles davon. Ereignisse aus der Idee und '
                  'das Wortbudget bleiben. Antworte nur mit dem vollständigen überarbeiteten Drehbuch. ' + series + rules(policy) + '\n' + FORMAT)
        try:
            final = await factory.write(doctor, {**context, 'drehbuch': draft}, label='Drehbuch-Doktor', check=problems)
            # Advisory: a rewrite that breaks more rules than the draft is dropped.
            if len(problems(final)) > len(problems(draft)): store['doctor_error'] = 'Überarbeitung verworfen: ' + '; '.join(problems(final))[:400]; final = draft
        except RuntimeError as error:
            final = draft; store['doctor_error'] = str(error)[:500]
        store['final'] = final; factory.save(d)
    title, beats, lines, problems = parse(store['final'], cast)
    if own is not None:
        from own_script import advice
        remaining = problems + advice(title, beats, lines, cast)
        cut = shots(title, beats, lines, cast, policy)
    else:
        remaining = check(title, beats, lines, problems, cast, idea['duration'], policy)
        cut = ensure_action(shots(title, beats, lines, cast, policy), idea['duration'])
    if own is not None and (not cut or len(cut) > OWN_MAX_SHOTS):
        raise RuntimeError(f'Folge {index + 1} deines Drehbuchs ' + ('hat keine verwertbare Zeile.' if not cut else
                           f'ergibt {len(cut)} Einstellungen, höchstens {OWN_MAX_SHOTS}. Bitte in mehrere Folgen teilen.'))
    if own is None and (not cut or len(cut) > MAX_SHOTS):
        # Unusable: forget it, so "Neu planen" really writes a new one (it used to parse the same text again).
        d['screenplays'].pop(str(index), None); factory.save(d)
        raise RuntimeError('Das Drehbuch enthält keine verwertbaren Zeilen.' if not cut else
                           f'Das Drehbuch ergibt {len(cut)} Einstellungen; höchstens {MAX_SHOTS}.' + ' „Neu planen“ schreibt es neu.')
    if not store.get('visuals'):
        d['phase'] = f'Folge {index + 1}: Bilder und Bewegungen der {len(cut)} Einstellungen beschreiben'; factory.save(d)
        listing = [{'shot': i + 1, 'visible': s['visible'], 'place': s['place'], 'situation': s['what'],
                    'lines': [{'speaker': l['speaker'], 'emotion': l['emotion'], 'text': l['text']} for l in s['lines']]} for i, s in enumerate(cut)]
        if policy >= 14: listing = [shot_listing(x, s) for x, s in zip(listing, cut)]
        # Cay's own script: the planner reads all of it, so pictures and motion show what it says.
        reading = ({'drehbuch': store['final']}, ' Das vollständige Drehbuch steht in drehbuch: Bilder und Bewegungen zeigen genau, was dort passiert.') if own is not None else ({}, '')
        try:
            answer = await factory.llm(ShotVisuals, visual_instruction(policy) + f' Genau {len(cut)} Einträge, Nummer 1 bis {len(cut)}.' + reading[1],
                                       {'style': d['plan'].get('style', ''), 'cast': d['plan']['cast'], 'shots': listing, **reading[0]})
            # Partial answers are usable: assemble() falls back per missing shot.
            numbers = [v['shot'] for v in answer['shots']]
            # Gaps are fine (fallback per shot); duplicates or numbers out of range mean the
            # numbering is shifted, and shifted motions would land on the wrong shots.
            if len(set(numbers)) != len(numbers) or any(not 1 <= n <= len(cut) for n in numbers):
                raise ValueError('Einstellungsnummern verschoben: ' + ', '.join(map(str, numbers))[:200])
            missing = [n for n in range(1, len(cut) + 1) if n not in numbers]
            if missing: store['visual_error'] = 'Ohne eigene Bildbeschreibung: Einstellung ' + ', '.join(map(str, missing))
            store['visuals'] = answer; factory.save(d)          # kept even if the repair below is interrupted
            store['visuals'] = await repair_visuals(factory, d, cut, listing, answer, visual_instruction(policy)); factory.save(d)
        except (RuntimeError, ValueError) as error:
            store['visual_error'] = 'Bildbeschreibungen fehlen, einfache Beschreibungen verwendet: ' + str(error)[:400]
    episode = assemble(title, spine, outline, cut, store.get('visuals') or {'shots': []}, d['plan']['cast'], continuity, policy)
    episode['screenplay'] = store['final']
    stats = {'words': sum(words(l['text']) for l in lines if l['kind'] == 'line'), 'lines': sum(l['kind'] == 'line' for l in lines),
             'actions': sum(l['kind'] == 'action' for l in lines), 'shots': len(cut), 'budget': b}
    if policy >= 14: stats.update(reactions=sum(s['kind'] == 'reaction' for s in cut), establishing=sum(s['kind'] == 'establish' for s in cut),
                                  lip_sync=sum(s['kind'] == 'line' for s in cut))
    episode['screenplay_stats'] = stats
    if own is not None: episode['own_script'] = True
    if remaining: episode['warnings'] = [('Hinweis zu deinem Drehbuch: ' if own is not None else 'Drehbuch prüfen: ') + '; '.join(remaining)[:900]]
    if store.get('visual_error'): episode.setdefault('warnings', []).append(store['visual_error'][:400])
    return episode
