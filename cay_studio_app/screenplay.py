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
"""
import math
import re
from typing import Literal
from pydantic import Field
from factory_models import Strict
from factory_cast import name_key, resolve_name

POLICY = 13
WORDS_PER_SECOND = 2.0      # target for the script; Qwen speaks ~2.5 words/s
MAX_LINE_WORDS = 22
MERGE_WORDS = 24            # consecutive lines of one speaker share a shot up to this
EMOTIONS = ('ruhig', 'fröhlich', 'begeistert', 'wütend', 'schreiend', 'ängstlich', 'panisch', 'traurig', 'flüsternd',
            'drohend', 'spöttisch', 'überrascht', 'triumphierend', 'flehend', 'genervt', 'verwirrt')
AMBIENCE = ('room', 'wind', 'forest', 'rain', 'train', 'none')


MAX_SHOTS = 44


def budget(duration, speakers=2):
    """Word band, turns and silent action lines for one film of `duration` seconds.
    A single figure has no speaker changes: turns are not required then."""
    target = round(duration * WORDS_PER_SECOND)
    actions = max(2, round(duration / 12))
    return {'words': target, 'min_words': math.floor(target * .85), 'max_words': math.ceil(target * 1.3),
            'min_turns': max(4, round(duration / 5)) if speakers > 1 else 0,
            'max_turns': min(max(8, round(duration / 2.2)), MAX_SHOTS - actions - 4) if speakers > 1 else MAX_SHOTS,
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
    'ambience: Umgebungsgeräusch. Ort und Licht über aufeinander folgende Einstellungen gleich halten.')


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
        row = re.sub(r'\*\*|__|`', '', raw).strip().strip('*').strip()
        if not row or row.startswith('```'): continue
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


def check(title, beats, lines, problems, cast, duration):
    """Concrete, countable problems the planner gets back. Empty list = usable."""
    b = budget(duration, len(cast)); errors = list(problems)
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
    count = len(ensure_action(shots(title, beats, lines, cast), duration))
    if count > MAX_SHOTS: errors.append(f'Zu viele Einstellungen: {count}, höchstens {MAX_SHOTS}. Aufeinander folgende Zeilen derselben Figur zusammenfassen, weniger AKTION-Zeilen.')
    return errors


def emotion_of(raw):
    raw = (raw or '').lower()
    return next((e for e in EMOTIONS if e in raw or raw in e), raw or 'ruhig')


def shots(title, beats, lines, cast):
    """Deterministic cut: one shot per speaker turn, one per AKTION line."""
    result = []
    for line in lines:
        beat = beats[line['beat']] if line['beat'] < len(beats) else {'place': 'Ort', 'what': ''}
        if line['kind'] == 'action':
            visible = [c for c in cast if _mentions(line['text'], [c])][:2]
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


def name_patterns(names, protected=()):
    """Regexes for figure names: the full name as written or in capitals (with possessive 's / German
    genitive s); name parts of 4+ letters only capitalised as written, so 'sandy seabed'
    or 'stars' stay, and never a part that also belongs to a visible figure
    ('Captain' of Captain Smee stays when only Captain Hook is off-screen)."""
    keep = {q.lower() for v in protected for q in re.split(r'[\s.]+', v) if q}
    out = []
    for name in names:
        # As written or in capitals; 'Sandy' must not catch 'sandy seabed'.
        out.append(re.compile(r"(?<!\w)(?:" + re.escape(name) + '|' + re.escape(name.upper()) + r")(?:'s|s)?(?!\w)"))
        for part in {q for q in re.split(r'[\s.]+', name) if len(q) >= 4 and q != name and q.lower() not in keep}:
            out.append(re.compile(r"(?<!\w)" + re.escape(part) + r"(?:'s|s)?(?!\w)"))
    return out


def _mentions(text, names, protected=()):
    return any(p.search(str(text)) for p in name_patterns(names, protected))


def sanitize(text, visible, cast):
    """Image and motion text may only describe figures in the frame.

    A clause naming someone off-screen is dropped ("SpongeBob at the table,
    Mr. Krabs looming over him" -> "SpongeBob at the table"): the image model
    draws every figure it reads about, without a reference, so as a wrong or
    blended figure. Leftover names are removed as a last resort."""
    hidden = [n for n in cast if n not in visible]
    clauses = re.split(r'(?:,|;|\bwhile\b|\bas\b|\bwhereas\b|\bwährend\b|\s-\s)', str(text or ''))
    kept = [c.strip() for c in clauses if c.strip() and not _mentions(c, hidden, visible)]
    out = ', '.join(kept)
    for pattern in name_patterns(hidden, visible):
        out = pattern.sub('', out)
    out = re.sub(r'\b(?:at|to|with|and|towards|behind|next to|und|mit|zu)\s*(?=[,.]|$)', '', out)
    return re.sub(r'\s{2,}', ' ', re.sub(r'\s+,', ',', out)).strip(' ,')


def ensure_action(cut, duration):
    """Missing time needs a silent shot to go to; otherwise it ends up as silence in
    lip-sync shots (mouths move without a voice). If the planner wrote no AKTION
    line, a short silent reaction of the figure who spoke last is added mid-film."""
    if duration < 30 or not cut or any(s['kind'] == 'action' for s in cut): return cut
    middle = len(cut) // 2; before = cut[max(0, middle - 1)]
    who = before['visible'][:1]
    reaction = {'kind': 'action', 'beat': before['beat'], 'place': before['place'], 'visible': who, 'lines': [],
                'what': f'{who[0] if who else "Die Figur"} reagiert stumm mit einer großen, deutlichen Geste.'}
    return cut[:middle] + [reaction] + cut[middle:]


def beat_label(index, count, cliffhanger):
    if index == 0: return 'problem'
    if index == count - 1: return 'cliffhanger' if cliffhanger else 'payoff'
    if cliffhanger and index == count - 2: return 'payoff'
    return 'turn' if index == round(count * .65) else 'attempt'


def assemble(title, spine, outline, cut, visuals, cast, continuity):
    """EpisodePlan-compatible dict; old downstream code keeps working."""
    by_number = {v['shot']: v for v in (visuals or {}).get('shots', [])}
    scenes = []
    for i, shot in enumerate(cut):
        v = by_number.get(i + 1, {})
        visible = shot['visible']
        speaker = shot['lines'][0]['speaker'] if shot['lines'] else ''
        fallback_still = (f'{" and ".join(visible)} in {shot["place"]}, ' + (f'{speaker} speaking, {shot["lines"][0]["emotion"]} expression' if speaker else shot['what']))
        names = [c['name'] for c in cast]
        still = sanitize(v.get('still') or fallback_still, visible, names)
        if len(still) < 10: still = sanitize(fallback_still, visible, names) or f'{" and ".join(visible)} in {shot["place"]}'
        motion = sanitize(v.get('motion') or ('talks with expressive face and natural gestures' if speaker else shot['what']), visible, names)
        if len(motion) < 5: motion = 'talks with expressive face and natural gestures' if speaker else 'moves quickly with a clear physical action'
        scenes.append({
            'title': (shot['what'] if shot['kind'] == 'action' else f'{speaker}: {shot["lines"][0]["text"]}')[:100] or f'Einstellung {i + 1}',
            'action': (shot['what'] or shot['place'])[:800] if shot['kind'] == 'action' else (shot['what'] or f'{speaker} spricht.')[:800],
            'location': shot['place'][:250] or 'Ort',
            'camera': (v.get('camera') or ('medium shot' if speaker else 'wide shot'))[:250],
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
            'scenes': scenes, 'story_policy': POLICY, 'dialogue_mode': 'rich', 'script': 'screenplay'}


def render_text(title, beats, lines):
    """Back to the screenplay format, e.g. to show the planner its own last valid draft."""
    out = [f'TITEL: {title}'] if title else []; current = None
    for line in lines:
        if line['beat'] != current:
            current = line['beat']; b = beats[current] if current < len(beats) else {'place': '', 'what': ''}
            out.append(f'# {current + 1} | {b["place"]} | {b["what"]}')
        out.append(f'AKTION: {line["text"]}' if line['kind'] == 'action' else f'{line["speaker"].upper()} [{line["emotion"]}]: {line["text"]}')
    return '\n'.join(out)


async def write_episode(factory, d, index, outline, source, continuity, spine):
    """Screenplay -> check -> doctor -> shots -> visuals. Stored drafts survive a restart."""
    idea = d['idea']; cast = [p['name'] for p in d['plan']['cast']]; b = budget(idea['duration'], len(cast))
    store = d.setdefault('screenplays', {}).setdefault(str(index), {})
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
                   + series + RULES + '\n' + FORMAT + '\n' + EXAMPLE)
    def problems(text): return check(*parse(text, cast), cast, idea['duration'])
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
                  'das Wortbudget bleiben. Antworte nur mit dem vollständigen überarbeiteten Drehbuch. ' + series + RULES + '\n' + FORMAT)
        try:
            final = await factory.write(doctor, {**context, 'drehbuch': draft}, label='Drehbuch-Doktor', check=problems)
            # Advisory: a rewrite that breaks more rules than the draft is dropped.
            if len(problems(final)) > len(problems(draft)): store['doctor_error'] = 'Überarbeitung verworfen: ' + '; '.join(problems(final))[:400]; final = draft
        except RuntimeError as error:
            final = draft; store['doctor_error'] = str(error)[:500]
        store['final'] = final; factory.save(d)
    title, beats, lines, problems = parse(store['final'], cast)
    remaining = check(title, beats, lines, problems, cast, idea['duration'])
    cut = ensure_action(shots(title, beats, lines, cast), idea['duration'])
    if not cut or len(cut) > MAX_SHOTS:
        # Unusable: forget it, so "Neu planen" really writes a new one (it used to parse the same text again).
        d['screenplays'].pop(str(index), None); factory.save(d)
        raise RuntimeError('Das Drehbuch enthält keine verwertbaren Zeilen.' if not cut else
                           f'Das Drehbuch ergibt {len(cut)} Einstellungen; höchstens {MAX_SHOTS}.' + ' „Neu planen“ schreibt es neu.')
    if not store.get('visuals'):
        d['phase'] = f'Folge {index + 1}: Bilder und Bewegungen der {len(cut)} Einstellungen beschreiben'; factory.save(d)
        listing = [{'shot': i + 1, 'visible': s['visible'], 'place': s['place'], 'situation': s['what'],
                    'lines': [{'speaker': l['speaker'], 'emotion': l['emotion'], 'text': l['text']} for l in s['lines']]} for i, s in enumerate(cut)]
        try:
            answer = await factory.llm(ShotVisuals, VISUAL_INSTRUCTION + f' Genau {len(cut)} Einträge, Nummer 1 bis {len(cut)}.',
                                       {'style': d['plan'].get('style', ''), 'cast': d['plan']['cast'], 'shots': listing})
            # Partial answers are usable: assemble() falls back per missing shot.
            seen = {}
            for v in answer['shots']:
                if 1 <= v['shot'] <= len(cut) and v['shot'] not in seen: seen[v['shot']] = v
            missing = [n for n in range(1, len(cut) + 1) if n not in seen]
            if missing: store['visual_error'] = 'Ohne eigene Bildbeschreibung: Einstellung ' + ', '.join(map(str, missing))
            store['visuals'] = {'shots': list(seen.values())}; factory.save(d)
        except (RuntimeError, ValueError) as error:
            # Not stored: a resume asks again; this run uses the per-shot fallbacks.
            store['visual_error'] = str(error)[:500]
    episode = assemble(title, spine, outline, cut, store.get('visuals') or {'shots': []}, d['plan']['cast'], continuity)
    episode['screenplay'] = store['final']
    stats = {'words': sum(words(l['text']) for l in lines if l['kind'] == 'line'), 'lines': sum(l['kind'] == 'line' for l in lines),
             'actions': sum(l['kind'] == 'action' for l in lines), 'shots': len(cut), 'budget': b}
    episode['screenplay_stats'] = stats
    if remaining: episode['warnings'] = ['Drehbuch prüfen: ' + '; '.join(remaining)[:900]]
    return episode
