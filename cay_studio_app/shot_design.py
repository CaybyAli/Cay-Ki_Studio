"""0.19 picture dynamics, only for projects pinned with shot_policy 19 (factory.py create).

Cay after 0.18 ("Preis der Familie", "Weißes Gold"): far too many static frontal medium shots at
eye level, no close-ups, talking heads stand still, silent action barely moves and feels slow.
Measured in both films (r019 diagnosis): 31 of 34 shots frontal, 0 close-ups, 8 of 9 talking shots
without any camera move, every silent shot 3.20 s of 16 fps Wan frames interpolated to 25 fps.

1) Stills: shot size and angle lead the image text, from a deterministic rotation per episode
   (never the same type twice in a row, close-ups for emotional lines, wide for a new place).
   FLUX.2 klein at cfg 1 follows the start of the text most; the fixed 'Medium shot of X alone'
   opening and the late 'Framing:' gave almost every frame the same frontal medium shot.
2) A CPU camera (export zoompan, after InfiniteTalk, so lip-sync safe) on every talking shot.
3) Silent Wan clips play their frames 1:1 at the delivery rate instead of minterpolate 16->25;
   silent shots last a whole Wan frame count (4k+1 frames), 1.64 to 2.76 s, never 3.20 s each.
4) Motion text without damping words, with one concrete fast camera move per silent shot.

Projects without the pin never call into this module (same prompts, graphs, specs and bytes).
How the angles, moves and Wan clips look can only be judged on Cay's GPU and screen.
"""
import math, re

POLICY = 19


def active(d):
    """True for a project (or an export spec) pinned with shot_policy 19."""
    return int((d or {}).get('shot_policy', 0) or 0) >= POLICY


def spec(d):
    """Export and part specs carry the pin only when present: factory_post keys are a digest of the spec."""
    return {'shot_policy': d['shot_policy']} if active(d) else {}


# --- 1) Shot types for the stills ------------------------------------------------------------

# Speaking shots never get a pure profile, an extreme close-up or a wide shot: the lip-sync model
# needs a readable face. Over-the-shoulder needs a second figure in the frame (a shoulder without a
# reference image would be drawn as a stranger).
ROLES = {'talk': ('mcu', 'low', 'cu', 'ms', 'dutch', 'high', 'ots'),
         'react': ('cu', 'ecu', 'mcu', 'high', 'low', 'dutch'),
         'action': ('wide', 'low', 'profile', 'high', 'dutch', 'ecu', 'ms', 'ots'),
         'establish': ('wide', 'high', 'low', 'dutch', 'profile'),
         'empty': ('wide', 'high', 'low', 'dutch', 'ecu')}
EMOTION_FIRST = ('cu', 'mcu', 'low', 'dutch')      # a strong feeling is read in the face
PLACE_FIRST = {'talk': ('ms', 'low'), 'react': ('mcu', 'high')}   # a new place: show more of it
STRONG = {'angry', 'shout', 'panic', 'afraid', 'threat', 'surprised', 'sad', 'pleading', 'triumph', 'excited', 'whisper'}
# Cay's own camera words in his script ("Kamera: Großaufnahme ...") win over the rotation.
WISHES = (('ecu', r'extreme?\s*(?:nah|close)|detailaufnahme|\bdetail\b|makro'),
          ('ots', r'über\s+die\s+schulter|over[- ]the[- ]shoulder'),
          ('dutch', r'dutch|gekippt|schräge?\s+kamera|schräglage'),
          ('profile', r'\bprofil|seitenansicht|von\s+der\s+seite|side\s+view'),
          ('low', r'froschperspektive|untersicht|von\s+unten|low[- ]angle'),
          ('high', r'vogelperspektive|aufsicht|draufsicht|von\s+oben|high[- ]angle|top[- ]down'),
          ('mcu', r'halbnah|medium\s+close'),
          ('cu', r'großaufnahme|nahaufnahme|close[- ]?up|\bnah\b'),
          ('ms', r'halbtotale|amerikanisch|medium\s+shot'),
          ('wide', r'\btotale\b|weitwinkel|\bwide\b|establishing|panorama'))


def role(scene):
    if not scene.get('cast'): return 'empty'
    kind = scene.get('kind') or 'line'
    if kind == 'reaction': return 'react'
    if kind == 'establish': return 'establish'
    return 'talk' if scene.get('dialogues') or scene.get('dialogue') else 'action'


def emotional(scene):
    from speech_quality import performance_key
    lines = scene.get('dialogues') or ([{'emotion': scene.get('emotion')}] if scene.get('dialogue') else [])
    return any(performance_key(l.get('emotion') or '') in STRONG for l in lines)


def wish(scene):
    text = str(scene.get('action') or '').lower()
    return next((kind for kind, pattern in WISHES if re.search(pattern, text)), None)


def allowed(kind, scene):
    return kind != 'ots' or len(scene.get('cast') or []) >= 2


def plan(episode, offset=0):
    """Shot type per scene: [{'type': ..., 'alt': ..., 'role': ...}]. Variant 0 of the scene image
    uses 'type', variant 1 'alt'. Neighbours never share a type in any choice of variants:
    type != previous type, alt differs from its own type, both neighbour types and the previous alt."""
    scenes = episode.get('scenes') or []; own = bool(episode.get('own_script'))
    out = []; counters = {}; place = text = None
    for scene in scenes:
        r = role(scene); pool = [k for k in ROLES[r] if allowed(k, scene)]
        n = counters.get(r, 0) + offset; counters[r] = counters.get(r, 0) + 1
        first = []
        if r == 'talk' and emotional(scene): first += [k for k in EMOTION_FIRST if k in pool]
        if r == 'react' and emotional(scene): first += ['cu', 'ecu']
        if scene.get('location') != place: first += list(PLACE_FIRST.get(r, ('wide',) if 'wide' in pool else ()))
        # Pool of at least five types: the alternative below always finds one.
        order = list(dict.fromkeys(first + pool[n % len(pool):] + pool[:n % len(pool)]))
        # Cay's camera line counts once, for the first shot of its scene section.
        asked = wish(scene) if own and scene.get('action') != text else None
        previous = [x['type'] for x in out[-2:]][::-1]
        kind = (asked if asked and allowed(asked, scene) else
                next((k for k in order if k not in previous), None) or next(k for k in order if k not in previous[:1]))
        out.append({'type': kind, 'role': r, 'pool': order})
        place, text = scene.get('location'), scene.get('action')
    for i, shot in enumerate(out):
        avoid = {shot['type'], out[i - 1]['type'] if i else None, out[i - 1]['alt'] if i else None,
                 out[i + 1]['type'] if i + 1 < len(out) else None}
        shot['alt'] = next(k for k in shot.pop('pool') if k not in avoid)
    return out


def lead(kind, names, speaker=''):
    """The camera sentence that opens the still prompt."""
    who = ' and '.join(names)
    if not names:
        return {'ecu': 'Extreme close-up of one telling prop of the location, filling the frame',
                'high': 'High-angle wide shot looking down over the whole location',
                'low': 'Low-angle wide shot from near the ground, the location towering over the camera',
                'dutch': 'Dutch-angle wide shot, the camera tilted about 15 degrees, the whole location in view'}.get(
            kind, 'Wide establishing shot of the whole location in depth, foreground, middle ground and background')
    one = speaker if speaker in names else names[0]
    other = next((n for n in names if n != one), '')
    return {'ecu': f"Extreme close-up of {one}'s face: the eyes and the mouth fill the frame, the camera very close",
            'cu': f'Close-up of {who}: head and shoulders fill the frame, three-quarter view from the side, slightly off-centre',
            'mcu': f'Medium close-up of {who} from the chest up, three-quarter view, placed on the left third of the frame',
            'ms': f'Medium shot of {who} from the waist up, three-quarter view, placed on the right third, an out-of-focus prop in the foreground',
            'wide': f'Wide shot: the whole location in depth, {who} full body in the middle distance',
            'low': f'Low-angle shot from below chin height looking up at {who}, waist up, imposing, three-quarter view',
            'high': f'High-angle shot looking down at {who} from above, three-quarter view, the floor around visible',
            'ots': f"Over-the-shoulder shot: the blurred back of {other}'s shoulder and head in the near foreground, {one} beyond it facing the camera",
            'profile': f'Profile shot: {who} seen exactly from the side, full body, moving across the frame',
            'dutch': f'Dutch-angle shot, the camera tilted about 15 degrees: {who} from the waist up, tense energy'}[kind]


def pose(r, names):
    """The pose comes from the moment, never from the design sheet (frontal, standing, arms down)."""
    who = ' and '.join(names)
    if not names: return ''
    return {'talk': f'{who} acts out the line with a big expressive gesture, leaning into it, the head turned; not a stiff standing pose. ',
            'react': f'{who} reacts with the whole body, the head turned toward the voice; not a stiff standing pose. ',
            'establish': f'{who} busy in the place, caught in the middle of a movement. '}.get(
        r, f'{who} caught in the middle of the action: a dynamic pose with clear motion, weight shifted, limbs in action; not a standing pose. ')


# Planner framing words in a still ('Close-up of X in ...', 'Wide establishing view, ...') would
# contradict the leading camera sentence; the subject stays.
FRAMING = re.compile(r'(?i)\b(?:extreme\s+)?(?:medium\s+close-up|medium(?:\s+wide)?\s+shot|close-up|wide(?:\s+establishing)?\s+(?:shot|view)|establishing\s+(?:shot|view)|full[- ]body\s+shot)(?:\s+of\b)?[,:]?\s*')


def unframed(text):
    return re.sub(r'\s{2,}', ' ', FRAMING.sub('', str(text or ''))).strip(' ,;')


# --- 2) CPU camera on talking shots (export) ---------------------------------------------------

MOVES = ('push', 'pull', 'drift', 'punch')
CENTRE = ('(iw-iw/zoom)/2', '(ih-ih/zoom)*0.40')   # a bit above the middle: faces
LIMIT = 1.18          # largest zoom: 576x1024 material gets soft above ~1.25, faces stay in the frame


def talking(scene):
    return (scene.get('kind') or 'line') == 'line' and bool(scene.get('lines'))


def punch_at(line):
    """Caption boundary nearest the middle of a line (the visual cut lands on a caption change)."""
    from factory_video import caption_chunks
    start, length = float(line.get('offset', 0)), float(line['duration'])
    edges = [b for _, b, _ in caption_chunks(line.get('text_de', ''), start, length)[:-1]]
    edges = [b for b in edges if start + .6 <= b <= start + length - .6]
    return min(edges, key=lambda b: abs(b - start - length / 2)) if edges else None


def camera(scenes, index, t0, fps):
    """(zoom, (x, y)) zoompan expressions for talking shot `index` (t0 = start of this clip within the
    shot), or None for every other shot (they keep the 0.18 camera). Moves rotate over the talking
    shots of the episode: push-in, pull-back, lateral drift, punch-in at a caption change; a second
    line always punches in as well. Captions are burnt in after the zoom, so they never move."""
    scene = scenes[index]
    if not talking(scene): return None
    k = sum(talking(s) for s in scenes[:index]); lines = scene['lines']; T = float(scene['seconds'])
    t = f'(on/{fps}+{t0:.6f})'; p = f'{t}/{T:.6f}'; x, y = CENTRE; move = MOVES[k % len(MOVES)]
    at = punch_at(lines[0]) if move == 'punch' and len(lines) == 1 else None
    if move == 'pull': zoom = f'(1.12-0.10*{p})'
    elif move == 'drift':
        a, b = (.2, .8) if (k // len(MOVES)) % 2 == 0 else (.8, .2)
        zoom = '1.10'; x = f'(iw-iw/zoom)*({a:.2f}+{b - a:.2f}*{p})'
    elif at is not None: zoom = f'(1+0.04*{p})*if(gte({t}\\,{at:.6f})\\,1.12\\,1)'
    else: zoom = f'(1+0.10*{p})'
    if len(lines) >= 2: zoom = f'min({LIMIT}\\,{zoom}*if(gte({t}\\,{float(lines[1].get("offset", 0)):.6f})\\,1.10\\,1))'
    return zoom, (x, y)


# --- 3) Native cadence and silent shot lengths ---------------------------------------------------

NATIVE_FRAMES = 81    # longest Wan clip (as before); at 25 fps played 1:1 it lasts 3.24 s
# Frames of the silent action shots, in turn: 4k+1 each (whole Wan clips, nothing stretched or
# frozen), 1.64 to 2.76 s at 25 fps. The mean is 53 frames, the clip size of every 0.18 silent shot,
# so a silent shot costs the same GPU time as before; it is just shorter and faster.
ACTION_FRAMES = (53, 41, 61, 45, 69, 49, 57, 49)
ESTABLISH_FRAMES = 49


def native_frames(seconds, fps):
    """Wan frames for a silent clip shown 1:1: the next 4k+1 count that covers every delivered frame."""
    shown = round(float(seconds) * fps)
    frames = 4 * math.ceil((shown - 1) / 4) + 1
    if shown < 2 or frames > NATIVE_FRAMES: raise ValueError('Ein Bewegungsabschnitt muss zwischen 0,1 und 3,2 Sekunden dauern.')
    return frames


def snap(frames, fps):
    """A 25 fps frame count at another delivery rate, again 4k+1."""
    return 4 * round((frames * fps / 25 - 1) / 4) + 1


def silent_lengths(scenes, talking_flags, base, fps):
    """Layout 18 bases with the 0.19 silent lengths: action shots in turn from ACTION_FRAMES, a wide
    establishing shot ESTABLISH_FRAMES. Talking shots and reactions (their voice decides) stay."""
    from factory_timing import off_screen
    out = list(base); k = 0
    for i, (scene, talk) in enumerate(zip(scenes, talking_flags)):
        if talk or off_screen(scene): continue
        frames = ESTABLISH_FRAMES if scene.get('kind') == 'establish' else ACTION_FRAMES[k % len(ACTION_FRAMES)]
        if scene.get('kind') != 'establish': k += 1
        out[i] = snap(frames, fps) / fps
    return out


# --- 4) Motion text ------------------------------------------------------------------------------

# Damping words in the motion text slow Wan down further (4-step LoRA, cfg 1: the text is the
# only steering). 'stop-motion' in the clay look asks for choppy, slow movement.
DAMPING = re.compile(r'(?i)\b(?:calm(?:ly)?|stead(?:y|ily)|subtl(?:e|y)|slow(?:ly)?(?:[- ]motion)?|gentl(?:e|y)|stop[- ]motion)\b')


def undamp(text):
    out = DAMPING.sub('', str(text or ''))
    out = re.sub(r'\b(an?|the)\s+(?=[,.;]|$)', '', out)
    out = re.sub(r'\b(a)\s+(?=[aeiou])', 'an ', out)
    out = re.sub(r'(?:\s*,){2,}', ',', re.sub(r'\s+([,.;:])', r'\1', re.sub(r'\s{2,}', ' ', out)))
    return re.sub(r'\b(an?|and|with)\s*([,.;]|$)', r'\2', out).strip(' ,;')


# The lip-sync split (lipsync_shots.CAMERAS) opens animation text with a framing; the still decides it now.
OPENING = re.compile(r'(?i)^(?:dynamic\s+|low-angle\s+)?medium\s+(?:close-up|shot)(?:\s+with\s+a\s+(?:slow\s+)?push-in)?\s+of\s+')
CAMERA_MOVES = ('whip pan following the move', 'fast dolly in toward the action', 'crash zoom onto the action',
                'handheld camera following the action closely', 'fast tracking shot alongside the movement', 'quick low-angle push-in')
TALK_SUFFIX = (' Only the single visible character speaks, exactly when the supplied voice speaks; the mouth is closed whenever the voice is silent. '
               'Lively head, shoulders and hands the whole time. The same face in every frame.')


def direction(scene, lines, index):
    """0.19 behaviour text for one shot (studio_quality_policy.motion_direction stays for older projects)."""
    names = list(scene.get('cast') or [])
    frame = (f'Exactly one character in the whole frame: {names[0]}. No other characters or figures anywhere, also not in the background. '
             if len(names) == 1 else f'Only {" and ".join(names)} in the frame, nobody else. ' if names else 'No characters in the frame. ')
    base = ('One continuous full-frame shot. No cut, no montage, no split screen, no border. '
            'No written language, letters, subtitles, captions, menus or watermark in any frame. ' + frame +
            'The same faces, proportions, materials, costume, head shape, props and lighting as in the starting image. '
            'Full real-time speed with snappy cartoon timing. ')
    move = CAMERA_MOVES[index % len(CAMERA_MOVES)]; kind = scene.get('kind')
    if kind == 'reaction':
        who = names[0] if names else 'The character'
        return base + (f'{who} hears a voice from outside the frame with the lips closed the whole time: a sharp, clearly visible reaction, '
                       'the eyes widen or narrow, the eyebrows jump, the head snaps toward the voice, shoulders and hands react. Camera: quick push-in on the face.')
    if kind == 'establish':
        who = ' and '.join(names)
        return base + ('A fast, dynamic reveal of the location' + (f', {who} moving with purpose, lips closed. ' if names else ', the place and its props. ')
                       + 'Camera: fast crane down and dolly in into the location.')
    if lines:
        return base + (f'{lines[0]["speaker"]} talks with big expressive cartoon acting while the voice speaks: the head turns and nods, '
                       'leans toward the camera, shoulders and hands move with the rhythm of the words. Mouth closed whenever the voice is silent.')
    return base + ('Fast, energetic, clearly visible physical action at full speed with anticipation and overshoot, big readable poses, '
                   f'things in the scene react to the movement. Every mouth stays closed the whole time, faces show the feeling with the eyes and eyebrows. Camera: {move}.')


def motion_prompt(style, movement, scene, lines, index):
    """Wan / InfiniteTalk text under 0.19: look and movement without damping words, then the direction."""
    movement = undamp(OPENING.sub('', str(movement or '').strip())) or 'moves with a clear, fast physical action'
    return undamp(style).rstrip('.') + '. ' + movement.rstrip('.') + '. ' + direction(scene, lines, index)
