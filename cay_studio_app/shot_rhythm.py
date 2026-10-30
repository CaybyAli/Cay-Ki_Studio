"""0.20 rhythm and physical acting, only for projects pinned with shot_policy 20 (factory.py create).

Cay after 0.19 ("Villa der süßen Lügen", Folge 1): the figures are no longer rigid, but they still
stand still too much, and the cut is monotonous: one person speaks, cut, the next person speaks.
Measured on his script (r020): 100 of 107 dialogue shots show the speaker alone and frontal, 2 % of
the dialogue shots show anyone else, 3.9 s per dialogue shot; his reference films ('Crane', 'Moin')
cut every 1.2 s between close-ups, over-the-shoulder shots, listeners, hands and props.

1) Cut (cut()): a line of two or more sentences is cut at a sentence end into up to three pieces,
   each its own voice clip and shot (a voice never continues across a cut inside a clip). Each piece
   is shown one of four ways: the speaker's face (lip-sync), the speaker over the listener's blurred
   shoulder (lip-sync, only the speaker's face readable), the listener reacting while the voice comes
   from off-screen (silent Wan, the 0.18 L-cut), or, between two lines, a silent insert of about one
   second: the hands, the prop the line names (Handy, Foto, Geld, Pistole ...) or the eyes. The same
   speaker is never on screen for more than two shots in a row while someone else is there, a listener
   shot never follows a listener shot, and two shots with a second figure in the frame never follow
   each other (the shot plan needs a new framing on every cut).
2) Movement (direction()): reactions and inserts get a concrete physical action from the feeling of
   the moment (threat: steps closer, grabs the collar; afraid: backs away, glances at the door;
   triumph: leans back, spreads the arms) and a handheld or push-in camera. Talking shots keep the
   lip-sync-safe 0.19 text (gestures, no head turns).
3) Two figures in one frame: an over-the-shoulder still gets the reference images of both figures,
   the one in front only from behind (shot_design.still_names, cast_design.shot_prompt).

GPU: a reaction or an insert is a silent Wan clip, far cheaper per second than InfiniteTalk; a piece
heard over a listener needs no lip-sync window at all. test_rhythm_020.py measures it on Cay's scripts.
The cast of every shot stays one figure for lip-sync; the second figure lives in 'shoulder'.
How the stills and clips look can only be judged on Cay's GPU and screen.
"""
import re

POLICY = 20


def active(d):
    """True for a project (or an export spec) pinned with shot_policy 20."""
    try: return int((d or {}).get('shot_policy', 0) or 0) >= POLICY
    except (TypeError, ValueError): return False


# --- 1) Cut ---------------------------------------------------------------------------------------

SPLIT_WORDS = 6        # a line this long with two sentences or more is cut at a sentence end
PIECE_WORDS = 2        # no piece shorter, except a one-word question or call before a longer rest ('Sia? Was machst du hier?')
PIECES = 3
MERGE_SECONDS = 2.4    # consecutive short lines of one speaker share one shot up to this
REACT_WORDS = 8        # a whole line heard over a listener: about 4 s with the reaction's tail
PIECE_REACT_WORDS = 12 # the rest of a split line over the listener (it continues what was just seen)
REACT_SHARE = .4       # listener shots among the voiced shots of the film (the reference films: about half)
RUN = 2                # the same speaker at most this many shots in a row while someone else is there
INSERT_GAP = 4         # at least this many voiced shots between two inserts; a feeling at most once per section
ABBREVIATION = re.compile(r'(?i)(?:(?<!\w)(?:mr|mrs|ms|dr|prof|st|nr|hr|fr|ca|bzw|usw|vgl|z\.\s?b)|\d)\.$')


def sentences(text):
    """Sentences of one line, split after . ! ? or … (never after 'Mr.' or '7.')."""
    out = []
    for part in re.split(r'(?<=[.!?…])\s+', str(text or '').strip()):
        if out and ABBREVIATION.search(out[-1]): out[-1] += ' ' + part
        elif part: out.append(part)
    return out


def split_line(text):
    """Pieces of one spoken line at sentence ends: each at least PIECE_WORDS words, at most PIECES.
    The pieces joined with a space give the line back word for word."""
    from screenplay import words
    parts = sentences(text)
    if len(parts) < 2 or words(text) < SPLIT_WORDS: return [text]
    pieces, current = [], []
    for i, part in enumerate(parts):
        current.append(part)
        rest = sum(words(x) for x in parts[i + 1:]); size = words(' '.join(current))
        short = size == 1 and current[-1].endswith(('?', '!')) and rest >= 4
        if (size >= PIECE_WORDS or short) and rest >= PIECE_WORDS and len(pieces) < PIECES - 1:
            pieces.append(' '.join(current)); current = []
    if current: pieces.append(' '.join(current))
    return pieces


# Props a line may name, as German nouns (capitalised, with their usual endings) -> English for the image text.
PROPS = (('Handy', 'smartphone'), ('Smartphone', 'smartphone'), ('Telefon', 'phone'), ('Display', 'phone display'), ('Foto', 'photo'),
         ('Bild', 'photo'), ('Geld', 'money, a bundle of banknotes'), ('Scheine', 'banknotes'), ('Münzen', 'coins'), ('Euro', 'banknotes'),
         ('Pistole', 'pistol'), ('Waffe', 'gun'), ('Revolver', 'revolver'), ('Messer', 'knife'), ('Schlüssel', 'key'), ('Brief', 'letter'),
         ('Umschlag', 'envelope'), ('Koffer', 'suitcase'), ('Reisetasche', 'travel bag'), ('Tasche', 'bag'), ('Paket', 'package'),
         ('Kiste', 'crate'), ('Ware', 'package of goods'), ('Ring', 'ring'), ('Glas', 'glass'), ('Flasche', 'bottle'),
         ('Zigarette', 'cigarette'), ('Feuerzeug', 'lighter'), ('Vertrag', 'contract'), ('Akte', 'file folder'), ('Karte', 'card'),
         ('Aufnahme', 'audio recording on a phone'), ('Clip', 'audio clip on a phone'), ('Tonclip', 'audio clip on a phone'),
         ('Video', 'video on a phone'), ('Laptop', 'laptop'), ('Bildschirm', 'screen'), ('Mikrofon', 'microphone'), ('Schuh', 'shoe'),
         ('Tür', 'door handle'), ('Uhr', 'wristwatch'))
PROP = re.compile(r'(?<![\wÄÖÜäöüß])(' + '|'.join(re.escape(p) for p, _ in sorted(PROPS, key=lambda x: -len(x[0])))
                  + r')(?:e|en|n|s|es|er|ern)?(?![\wÄÖÜäöüß])')
ENGLISH = dict(PROPS)
CLOCK = re.compile(r'\d\s*Uhr\b')        # 'sieben Uhr', '7 Uhr' is a time, not a watch


def prop_of(text):
    """The first prop a line names, as written in the script ('Foto'), else None."""
    text = str(text or '')
    for m in PROP.finditer(text):
        if m.group(1) == 'Uhr' and (CLOCK.search(text[max(0, m.start() - 4):m.end()]) or re.search(r'(?i)\b(?:eins|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn|elf|zwölf)\s+$', text[:m.start()])): continue
        if m.group(1) == 'Bild' and re.search(r'(?i)\b(?:im|ins)\s+$', text[:m.start()]): continue      # 'im Bild' is no photo
        return m.group(1)
    return None


HANDS = {'threat', 'angry', 'shout', 'triumph', 'panic'}     # a feeling the hands show best
EYES = {'afraid', 'surprised', 'whisper'}                    # ... the eyes


def mood(emotion):
    from speech_quality import performance_key
    return performance_key(emotion or '')


def _addressed(text, speaker, present, cast):
    """Figures named in the line, in the order the line names them (the first is the one spoken to)."""
    from screenplay import _spans
    found = []
    for name in present:
        if name == speaker: continue
        spans = _spans(str(text), [name], [o for o in cast if o != name])
        if spans: found.append((spans[0][0], name))
    return [n for _, n in sorted(found)]


def _people(result, i, cast):
    """(addressee, witness) for the speaking shot i: the figure spoken to (named in the line, else the
    one who spoke before in this section, else the next one) and someone else present, or None."""
    shot = result[i]; speaker = shot['visible'][0]; beat = shot['beat']
    same = [(j, s) for j, s in enumerate(result) if s['beat'] == beat]
    voice = lambda s: s['voice_of'] if s['kind'] == 'reaction' else s['visible'][0] if s['kind'] == 'line' and s['visible'] else None
    present = list(dict.fromkeys([n for _, s in same for n in ([voice(s)] if voice(s) else []) + list(s['visible'])]))
    if not [n for n in present if n != speaker]: return None, None
    before = next((voice(s) for j, s in reversed(same) if j < i and voice(s) and voice(s) != speaker), None)
    after = next((voice(s) for j, s in same if j > i and voice(s) and voice(s) != speaker), None)
    named = _addressed(' '.join(l['text'] for l in shot['lines']), speaker, present, cast)
    addressee = (named or [before or after or next(n for n in present if n != speaker)])[0]
    witness = next((n for n in [after, before] + present if n and n not in (speaker, addressee)), None)
    return addressee, witness


def _mood_of(result, i, listener):
    """The listener's feeling: from the listener's next line in this section, else the one before, else the line heard."""
    beat = result[i]['beat']
    said = lambda s: [l for l in s['lines'] if l['speaker'] == listener] if s['kind'] == 'line' and s['visible'] == [listener] else []
    later = next((l for s in result[i + 1:] if s['beat'] == beat for l in said(s)), None)
    earlier = next((l for s in reversed(result[:i]) if s['beat'] == beat for l in reversed(said(s))), None)
    return (later or earlier or result[i]['lines'][-1])['emotion']


def _pieces(beats, lines, cast, policy, limit):
    """Shots before the views: actions, off-screen lines as in block_cut, every spoken line split at its
    sentence ends while the shot limit allows it, consecutive short lines of one speaker merged."""
    from screenplay import emotion_of, spoken_seconds, _off_listener, MAX_ESTABLISH
    planned = [split_line(l['text']) if l['kind'] == 'line' and not l.get('off') else [l['text']] for l in lines]
    spare = limit - 1 - MAX_ESTABLISH - len(lines)
    for k, pieces in enumerate(planned):
        if len(pieces) > 1:
            if spare >= len(pieces) - 1: spare -= len(pieces) - 1
            else: planned[k] = [lines[k]['text']]
    result = []
    for index, line in enumerate(lines):
        beat = beats[line['beat']] if line['beat'] < len(beats) else {'place': 'Ort', 'what': ''}
        context = {'context': line['context']} if line.get('context') else {}
        last = result[-1] if result else None
        if line['kind'] == 'action':
            from screenplay import _mentions
            visible = [c for c in cast if _mentions(line['text'], [c], [o for o in cast if o != c])][:2]
            if not visible and context: visible = [c for c in cast if _mentions(context['context'], [c], [o for o in cast if o != c])][:2]
            result.append({'kind': 'action', 'beat': line['beat'], 'place': beat['place'], 'what': line['text'],
                           'visible': visible or ([last['visible'][0]] if last and last['visible'] else cast[:1]), 'lines': [], **context})
            continue
        entry = {'speaker': line['speaker'], 'text': line['text'], 'emotion': emotion_of(line['emotion'])}
        listener = _off_listener(lines, index, result) if line.get('off') else None
        if listener:
            if (last and last['kind'] == 'reaction' and last['voice_of'] == line['speaker'] and last['visible'] == [listener[0]]
                    and last['beat'] == line['beat'] and len(last['lines']) < 3 and spoken_seconds(last['lines'] + [entry]) <= MERGE_SECONDS):
                last['lines'].append(entry); continue
            result.append({'kind': 'reaction', 'beat': line['beat'], 'place': beat['place'], 'what': beat['what'], 'visible': [listener[0]],
                           'lines': [entry], 'voice_of': line['speaker'], 'emotion': listener[1], **context})
            continue
        pieces = planned[index]
        if (len(pieces) == 1 and last and last['kind'] == 'line' and last['visible'] == [line['speaker']] and last['beat'] == line['beat']
                and not last.get('piece') and len(last['lines']) < 3 and spoken_seconds(last['lines'] + [entry]) <= MERGE_SECONDS):
            last['lines'].append(entry)
            if context: last['context'] = (last.get('context', '') + ' ' + context['context']).strip()
            continue
        for k, text in enumerate(pieces):
            result.append({'kind': 'line', 'beat': line['beat'], 'place': beat['place'], 'what': beat['what'], 'visible': [line['speaker']],
                           'lines': [dict(entry, text=text)], **({'piece': [index, k]} if len(pieces) > 1 else {}), **(context if not k else {})})
    return result


def _views(result, cast):
    """Who is seen while each piece is heard: the speaker (face or over the listener's shoulder) or the listener."""
    from screenplay import words
    voiced = [i for i, s in enumerate(result) if s['kind'] == 'line']
    people = {i: _people(result, i, cast) for i in voiced}
    out = []; reacts = 0; seen = 0; talks = {}
    for i, shot in enumerate(result):
        if shot['kind'] != 'line':
            out.append(shot); continue
        speaker = shot['visible'][0]; addressee, witness = people[i]; prev = out[-1] if out else None
        face = prev['visible'][0] if prev and prev['visible'] else None
        listener = next((n for n in (addressee, witness) if n and n != face), None)
        run = 0
        for s in reversed(out):
            if s['kind'] != 'line' or s['visible'] != [speaker]: break
            run += 1
        size = sum(words(l['text']) for l in shot['lines'])
        continuing = bool(prev and prev['kind'] == 'line' and prev['visible'] == [speaker] and prev['beat'] == shot['beat'])
        allowed = bool(listener and prev and prev['beat'] == shot['beat'] and prev['kind'] != 'reaction' and i not in (voiced[0], voiced[-1]))
        if continuing: react = allowed and (size <= PIECE_REACT_WORDS or run >= RUN)
        else: react = allowed and size <= REACT_WORDS and reacts < REACT_SHARE * (seen + 1)
        seen += 1
        if react:
            reacts += 1
            out.append({**{k: v for k, v in shot.items() if k != 'visible'}, 'kind': 'reaction', 'visible': [listener], 'voice_of': speaker,
                        'emotion': _mood_of(result, i, listener), **({'shoulder': speaker} if reacts % 2 == 0 else {})})
            continue
        k = talks.get(shot['beat'], 0); talks[shot['beat']] = k + 1
        other = addressee if addressee and addressee != speaker else witness
        out.append(dict(shot, **({'shoulder': other} if other and (k % 2 == 1 or (continuing and not prev.get('shoulder'))) else {})))
    # Never two shots with a second figure in the frame in a row: the plan needs a new framing on every cut.
    for a, b in zip(out, out[1:]):
        if a.get('shoulder') and b.get('shoulder'): b.pop('shoulder')
    return out


def _inserts(result, room):
    """Silent inserts of about one second between two lines: the prop a line names, else for a strong
    feeling the hands or the eyes. Never next to a silent shot, never inside a split line, at most one
    per INSERT_GAP voiced shots, never more than the shot limit leaves room for."""
    voice = lambda s: s['kind'] in ('line', 'reaction')
    out = []; gap = INSERT_GAP; used = set(); felt = set(); added = 0
    for i, shot in enumerate(result):
        out.append(shot)
        gap += voice(shot)
        after = result[i + 1] if i + 1 < len(result) else None
        if not (voice(shot) and after and voice(after) and after['beat'] == shot['beat'] and added < room and gap >= INSERT_GAP): continue
        if shot.get('piece') and after.get('piece') and after['piece'][0] == shot['piece'][0]: continue      # inside one line
        line = shot['lines'][-1]; owner = line['speaker']; feeling = mood(line['emotion'])
        prop = prop_of(line['text'])
        if prop and (shot['beat'], prop) not in used: kind = 'prop'; used.add((shot['beat'], prop))
        elif feeling in HANDS | EYES and shot['beat'] not in felt: kind = 'hands' if feeling in HANDS else 'eyes'; prop = None; felt.add(shot['beat'])
        else: continue
        who = owner if kind != 'eyes' or shot['kind'] == 'line' else shot['visible'][0]
        what = {'prop': f'Detail: {prop} bei {who}', 'hands': f'Detail: die Hände von {who}', 'eyes': f'Detail: die Augen von {who}'}[kind]
        out.append({'kind': 'action', 'beat': shot['beat'], 'place': shot['place'], 'what': what, 'visible': [who], 'lines': [],
                    'insert': kind, **({'prop': prop} if prop else {}), 'mood': line['emotion'], 'heard': line['text']})
        gap = 0; added += 1
    return out


def cut(beats, lines, cast, policy, limit):
    """The 0.20 cut (see the module text). limit: the shot limit of the episode (screenplay.MAX_SHOTS, or
    OWN_MAX_SHOTS for Cay's own script); optional shots never push the cut over it."""
    from screenplay import _establishing
    result = _views(_pieces(beats, lines, cast, policy, limit), cast)
    room = lambda shots: limit - len(shots) - (0 if any(s['kind'] == 'action' and not s.get('insert') for s in shots) else 1)
    result = _establishing(result, beats, room(result), policy)
    return _inserts(result, max(0, room(result)))


def stats(cut_):
    """Numbers of the cut for the plan's check line."""
    return {'inserts': sum(1 for s in cut_ if s.get('insert')), 'shoulder': sum(1 for s in cut_ if s.get('shoulder'))}


# --- 2) Movement ----------------------------------------------------------------------------------

# Per feeling: (reaction toward the voice, reaction toward the figure in the foreground, hands, eyes, camera).
ACTING = {
    'threat': ('takes a step toward the voice and leans in close, the jaw set, a finger pointing hard', "steps right up and grabs the collar of the figure in the foreground",
               'a finger jabs forward hard, then the fist closes', 'the eyes narrow to slits and lock on', 'handheld camera, sharp push-in'),
    'angry': ('takes a hard step forward and slams a flat hand down on the table', "steps in and grabs the foreground figure's collar with both hands",
              'a hand slams flat on the table, things on it jump', 'the eyes flare, the brows crash down', 'handheld camera, sharp push-in'),
    'shout': ('lunges a step forward, both fists clenched, the chest pushed out', 'shoves the figure in the foreground back with both hands',
              'a fist hammers down onto the table', 'the eyes go wide with fury', 'handheld camera, crash zoom in'),
    'firm': ('plants both feet, squares the shoulders and points a finger at the voice', 'puts a firm hand on the shoulder of the figure in the foreground',
             'a finger taps hard on the table, twice', 'the eyes hold steady, unblinking', 'handheld camera, quick push-in'),
    'panic': ('stumbles back, looks around for a way out, both hands up', 'pushes away from the figure in the foreground and backs off',
              'hands fumble and almost drop what they hold', 'the eyes dart from side to side', 'shaky handheld camera'),
    'afraid': ('backs away a step, the eyes dart to the door, the hands half raised', 'shrinks back from the figure in the foreground, glancing at the door',
               'the fingers tremble and clutch the edge of the table', 'the eyes widen and flick toward the door', 'handheld camera, quick pull back'),
    'pleading': ('steps closer with open palms, the hands pressed together', 'reaches out and clutches the sleeve of the figure in the foreground',
                 'the hands press together, knuckles white', 'the eyes plead, glistening', 'handheld camera, push-in'),
    'triumph': ('leans back, spreads the arms wide, the chin up', 'leans back and spreads the arms wide, looking down at the figure in the foreground',
                'the hands spread open in a wide, victorious gesture', 'the eyes narrow with a satisfied glint', 'push-in, then a quick tilt up'),
    'excited': ('bounces up on the toes and throws the arms up', 'claps the figure in the foreground on the shoulder',
                'the hands clap together and rub fast', 'the eyes sparkle wide open', 'handheld camera, whip pan in'),
    'mocking': ('crosses the arms, tilts the head and rolls the eyes', 'leans in close past the shoulder in the foreground with a smirk',
                'the fingers drum slowly on the table', 'one eyebrow rises, the eyes roll', 'push-in'),
    'annoyed': ('throws the hands up and turns half away', 'brushes past the shoulder in the foreground',
                'the fingers drum fast on the table', 'the eyes roll to the ceiling', 'handheld camera, quick push-in'),
    'surprised': ('jerks back a step, the eyebrows shoot up, a hand flies up', 'jerks back from the figure in the foreground, both hands up',
                  'a hand freezes in mid-air and something slips from the fingers', 'the eyes go wide, the pupils sharp', 'crash zoom in'),
    'sad': ('turns the shoulders away, the head drops, a hand to the chest', 'turns away from the figure in the foreground, the head down',
            'the fingers twist a piece of fabric', 'the eyes lower and glisten', 'handheld camera, push-in'),
    'whisper': ('leans in close and glances over the shoulder', 'leans in close to the ear of the figure in the foreground, glancing around',
                'a hand slides something across the table, hidden', 'the eyes flick sideways, checking who listens', 'handheld camera, push-in'),
    'confused': ('tilts the head, steps half a step back, one hand rises', 'turns from the figure in the foreground and back again, one hand raised',
                 'the fingers stop mid-gesture and spread open', 'the eyes squint and dart', 'push-in'),
    'joy': ('steps forward with an open gesture and a nod', 'puts a hand on the shoulder of the figure in the foreground',
            'the hands open warmly', 'the eyes light up', 'push-in'),
    'natural': ('shifts the weight, crosses the arms and turns toward the voice', 'turns toward the figure in the foreground and folds the arms',
                'the fingers tap on the table', 'the eyes narrow, thinking', 'handheld camera, push-in'),
}
# A calm listener of a strong line still answers with the body: the line's feeling decides then.
ANSWER = {'threat': 'afraid', 'angry': 'afraid', 'shout': 'afraid', 'panic': 'surprised', 'afraid': 'firm', 'pleading': 'firm', 'triumph': 'angry',
          'mocking': 'annoyed', 'surprised': 'firm', 'firm': 'annoyed', 'whisper': 'whisper', 'sad': 'pleading', 'excited': 'surprised', 'annoyed': 'mocking'}


def feeling(scene):
    """The feeling a reaction or insert acts out: its own, else the answer to the line heard, else calm."""
    own = mood(scene.get('mood') if scene.get('insert') else scene.get('emotion'))
    heard = mood(((scene.get('dialogues') or [{}])[0]).get('emotion') or scene.get('mood'))
    return own if own != 'natural' else ANSWER.get(heard, 'natural')


def react_text(scene, who):
    act = ACTING[feeling(scene)]; front = scene.get('shoulder')
    if front: return (f'{who} hears {front} talk with the lips closed the whole time and reacts with the whole body: {act[1]}. '
                      f'{front} is only seen from behind in the near foreground, the face hidden, the lips never visible. Camera: {act[4]}.')
    return (f'{who} hears a voice from outside the frame with the lips closed the whole time and reacts with the whole body: {act[0]}. '
            f'Camera: {act[4]}.')


def insert_text(scene):
    act = ACTING[feeling(scene)]; who = (scene.get('cast') or ['the character'])[0]; kind = scene.get('insert')
    if kind == 'prop':
        thing = ENGLISH.get(scene.get('prop'), 'object')
        verb = {'threat': 'slams the {} down hard', 'angry': 'slams the {} down hard', 'shout': 'slams the {} down hard',
                'afraid': 'clutches the {}, the fingers trembling', 'panic': 'fumbles with the {} and almost drops it',
                'triumph': 'holds the {} up to the camera and turns it', 'mocking': 'dangles the {} teasingly in front of the camera',
                'whisper': 'slides the {} into view, hidden from the others'}.get(feeling(scene), 'pushes the {} fast into the frame')
        return (f"Extreme close-up insert of the {thing}: {who}'s hand {verb.format(thing)}. Only the hand and the {thing} in the frame, "
                f'no face. Camera: snap push-in onto the {thing}, then the focus holds.')
    if kind == 'eyes':
        return (f"Extreme close-up insert of {who}'s eyes: {act[3]}. Only the eyes and the brows fill the frame, the mouth stays out of frame. "
                'Camera: snap push-in, a slight handheld shake.')
    return f"Extreme close-up insert of {who}'s hands: {act[2]}. Only the hands in the frame, no face. Camera: handheld, a fast push-in."


def still_text(scene):
    """English picture of an insert for the still (the planner may add its own detail)."""
    who = (scene.get('cast') or ['the character'])[0]; kind = scene.get('insert')
    if kind == 'prop': return f"{who}'s hand with the {ENGLISH.get(scene.get('prop'), 'object')}, tension in the fingers"
    if kind == 'eyes': return f"{who}'s eyes, {ACTING[feeling(scene)][3]}"
    return f"{who}'s hands in the middle of a tense gesture, {ACTING[feeling(scene)][2]}"
