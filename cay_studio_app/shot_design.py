"""0.19 picture dynamics, only for projects pinned with shot_policy 19 (factory.py create).

Cay after 0.18 ("Preis der Familie", "Weißes Gold"): far too many static frontal medium shots at
eye level, no close-ups, talking heads stand still, silent action barely moves and feels slow.
Measured in both films (r019 diagnosis): 31 of 34 shots frontal, 0 close-ups, 8 of 9 talking shots
without any camera move, every silent shot 3.20 s of 16 fps Wan frames interpolated to 25 fps.

1) Stills: shot size and angle lead the image text, from a deterministic rotation per episode
   (never the same type twice in a row, close-ups for emotional lines, the widest allowed shot at
   a new place). FLUX.2 klein at cfg 1 follows the start of the text most; the fixed 'Medium shot
   of X alone' opening and the late 'Framing:' gave almost every frame the same frontal medium shot.
2) A CPU camera (export zoompan, after InfiniteTalk, so lip-sync safe) on every talking shot.
3) Silent Wan clips play their frames 1:1 at the delivery rate instead of minterpolate 16->25;
   silent action shots last whole Wan clips (4k+1 frames, 1.64 to 2.76 s at 25 fps) with on average
   the 53 frames every 0.18 silent shot rendered, so a silent shot costs the same GPU time.
4) Motion text without damping words, with one concrete fast camera move per silent shot, and a
   lip-sync text that asks for big gestures while the voice speaks.

The Wan sampler, its LoRAs and steps stay as they are. Projects without the pin never take any of
these paths (same prompts, graphs, specs, cache keys and bytes; tests/test_shots_019.py).
How the angles, moves and Wan clips look can only be judged on Cay's GPU and screen.
"""
import math, re

POLICY = 19


def active(d):
    """True for a project (or an export spec) pinned with shot_policy 19."""
    try: return int((d or {}).get('shot_policy', 0) or 0) >= POLICY
    except (TypeError, ValueError): return False


def spec(d):
    """Export and part specs carry the pin only when present: factory_post keys are a digest of the spec."""
    return {'shot_policy': d['shot_policy']} if active(d) else {}


# --- 1) Shot types for the stills ------------------------------------------------------------

# Speaking shots never get a pure profile, an extreme close-up or a wide shot: the lip-sync model
# needs a readable face of a fair size. Over-the-shoulder needs a second figure in the frame (a
# shoulder without a reference image would be drawn as a stranger).
ROLES = {'talk': ('mcu', 'low', 'cu', 'ms', 'dutch', 'high', 'ots'),
         'react': ('cu', 'ecu', 'mcu', 'high', 'low', 'dutch'),
         'action': ('wide', 'low', 'profile', 'high', 'dutch', 'ecu', 'ms', 'ots'),
         'establish': ('wide', 'high', 'low', 'dutch', 'profile'),
         'empty': ('wide', 'high', 'low', 'dutch', 'ecu')}
CLOSE = {'talk': ('cu', 'mcu', 'low', 'dutch'), 'react': ('cu', 'ecu', 'mcu')}    # a strong feeling is read in the face
PLACE = {'talk': ('ms', 'high', 'low'), 'react': ('mcu', 'high')}                   # a new place: show more of it
SIZE = {'ecu': 0, 'cu': 0, 'mcu': 1, 'ms': 1, 'low': 1, 'high': 1, 'dutch': 1, 'ots': 1, 'wide': 2, 'profile': 2}
STRONG = {'shout', 'panic', 'angry', 'threat', 'triumph', 'excited', 'surprised', 'afraid', 'pleading', 'sad', 'whisper'}
# Cay's own camera words in his script ('Kamera: Großaufnahme ...') win over the rotation. Only
# unambiguous camera terms: the same text also holds his prose ('kommt von oben herein').
WISHES = (('ecu', r'extreme?\s*(?:nah|close)|detailaufnahme|makro'),
          ('ots', r'über\s+die\s+schulter|over[- ]the[- ]shoulder'),
          ('dutch', r'dutch[- ]angle|gekippte\s+kamera|schräge\s+kamera|kamera\s+(?:ist\s+)?(?:gekippt|schräg)'),
          ('profile', r'im\s+profil\b|seitenansicht|side\s+view'),
          ('low', r'froschperspektive|untersicht|kamera\s+von\s+unten|low[- ]angle'),
          ('high', r'vogelperspektive|aufsicht|draufsicht|kamera\s+von\s+oben|high[- ]angle|top[- ]down'),
          ('mcu', r'\bhalbnah|medium\s+close'),
          ('cu', r'großaufnahme|nahaufnahme|close[- ]?up'),
          ('ms', r'halbtotale|amerikanische\s+einstellung|medium\s+shot'),
          ('wide', r'\btotale\b|weitwinkel|establishing|panorama'))


def role(scene):
    if not scene.get('cast'): return 'empty'
    kind = scene.get('kind') or 'line'
    if kind == 'reaction': return 'react'
    if kind == 'establish': return 'establish'
    return 'talk' if scene.get('dialogues') or scene.get('dialogue') else 'action'


def emotional(scene):
    from speech_quality import performance_key
    lines = scene.get('dialogues') or ([{'emotion': scene.get('emotion')}] if scene.get('dialogue') else [])
    if scene.get('kind') == 'reaction': lines = [{'emotion': scene.get('emotion')}] + list(lines)
    return any(performance_key(l.get('emotion') or '') in STRONG for l in lines)


def wish(scene):
    text = str(scene.get('action') or '').lower()
    return next((kind for kind, pattern in WISHES if re.search(pattern, text)), None)


def allowed(kind, scene):
    return kind != 'ots' or len(scene.get('cast') or []) >= 2


def rotate(items, n):
    items = list(items)
    return items[n % len(items):] + items[:n % len(items)] if items else []


def plan(episode):
    """Shot type per scene: [{'type', 'alt', 'role', 'pool'}]. Variant 0 of the scene image uses
    'type', variant 1 'alt' (another size where possible, so Cay has a real choice). Neighbours
    never share a type in any choice of variants: type != previous type (and, where possible, the
    one before), alt differs from its own type, both neighbour types and the previous alt.
    Only Cay's own camera wish may repeat a type, when he asks for it twice in a row."""
    scenes = episode.get('scenes') or []; own = bool(episode.get('own_script'))
    # Cay's camera line counts once, for the first shot of its scene section (same action text).
    asked = [wish(s) if own and (not i or s.get('action') != scenes[i - 1].get('action')) else None for i, s in enumerate(scenes)]
    asked = [a if a and allowed(a, s) else None for a, s in zip(asked, scenes)]
    out = []; counters = {}; place = object()
    for i, scene in enumerate(scenes):
        r = role(scene); pool = [k for k in ROLES[r] if allowed(k, scene)]
        n = counters.get(r, 0); counters[r] = n + 1
        moved = scene.get('location') != place; first = []
        if moved: first = [k for k in PLACE.get(r, ('wide',)) if k in pool]
        elif emotional(scene) and r in CLOSE:
            m = counters.get(r + ':close', 0); counters[r + ':close'] = m + 1; first = rotate(CLOSE[r], m)
        order = [k for k in dict.fromkeys(first + rotate(pool, n)) if k in pool]
        # Hard: never the previous type. Soft: not the one before either, nor the type Cay asked for next.
        hard = [x['type'] for x in out[-1:]]; soft = [x['type'] for x in out[-2:-1]] + [asked[i + 1] if i + 1 < len(scenes) else None]
        kind = (asked[i] or next((k for k in first if moved and k not in hard and k not in soft[1:]), None)
                or next((k for k in order if k not in hard + soft), None) or next(k for k in order if k not in hard))
        out.append({'type': kind, 'role': r, 'pool': order})
        place = scene.get('location')
    for i, shot in enumerate(out):
        avoid = {shot['type'], out[i - 1]['type'] if i else None, out[i - 1]['alt'] if i else None,
                 out[i + 1]['type'] if i + 1 < len(out) else None}
        free = [k for k in shot['pool'] if k not in avoid]
        shot['alt'] = next((k for k in free if SIZE[k] != SIZE[shot['type']]), None) or free[0]
    return out


def pick(shots, i, variant, round_=0):
    """The shot type of one scene image. Round 0 is the plan; each 'Neue Bilder' round takes the next
    type of the scene's own order that neither neighbour planned, so a new round looks new."""
    if not round_: return shots[i]['alt' if variant else 'type']
    near = {shots[j][x] for j in (i - 1, i + 1) if 0 <= j < len(shots) for x in ('type', 'alt')}
    choices = [k for k in shots[i]['pool'] if k not in near] or shots[i]['pool']
    return choices[(2 * round_ + variant) % len(choices)]


def lead(kind, names, speaker='', r='talk'):
    """The camera sentence that opens the still prompt: shot size and angle first."""
    who = ' and '.join(names)
    if not names:
        return {'ecu': 'Extreme close-up of one telling prop of the location, filling the frame',
                'high': 'High-angle wide shot looking down over the whole location',
                'low': 'Low-angle wide shot from near the ground, the location towering over the camera',
                'dutch': 'Dutch-angle wide shot, the camera tilted about 15 degrees, the whole location in view'}.get(
            kind, 'Wide establishing shot of the whole location in depth, foreground, middle ground and background')
    one = speaker if speaker in names else names[0]
    other = next((n for n in names if n != one), '')
    if kind == 'ecu' and r == 'action':
        return f"Extreme close-up insert: {who}'s hands in the middle of the action, the key object filling the frame"
    if r == 'establish' and kind in ('high', 'low', 'dutch', 'profile'):
        return {'high': f'High-angle wide shot looking down over the whole location, {who} small in it',
                'low': f'Low-angle wide shot from near the ground, the location towering over the camera, {who} full body in it',
                'dutch': f'Dutch-angle wide shot, the camera tilted about 15 degrees: the whole location, {who} full body in it',
                'profile': f'Wide side view of the location, {who} seen from the side, full body, crossing the frame'}[kind]
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


def pose(r, names, kind=''):
    """The pose comes from the moment, never from the design sheet (frontal, standing, arms down).
    Phrased positively: at cfg 1 a 'not standing' can draw the standing pose. A close-up gets a
    head-and-hands pose, so the text does not pull the camera back to the whole body."""
    who = ' and '.join(names)
    if not names: return ''
    if kind in TIGHT and r in ('talk', 'react'):
        return (f'{who} in the middle of the line: the head tilted, eyebrows raised, a hand gesture entering the frame. ' if r == 'talk' else
                f'{who} reacts: the head snapped toward the voice, the eyes wide or narrowed, the eyebrows high. ')
    return {'talk': f'{who} acts out the line with a big expressive gesture: leaning into it, the head turned, one hand raised, weight on one leg. ',
            'react': f'{who} reacts with the whole body: the head turned toward the voice, shoulders drawn up, hands caught mid-gesture. ',
            'establish': f'{who} busy in the place, caught in the middle of a movement. '}.get(
        r, f'{who} caught in the middle of the action: a dynamic asymmetric pose, weight shifted, arms and legs in motion. ')


# Planner framing words in a still ('Close-up of X in ...', 'Wide establishing view, ...') would
# contradict the leading camera sentence; the subject stays.
FRAMING = re.compile(r'(?i)\b(?:extreme\s+)?(?:medium\s+close-up|medium(?:\s+wide)?\s+shot|close-up|wide(?:\s+establishing)?\s+(?:shot|view)|establishing\s+(?:shot|view)|full[- ]body\s+shot)(?:\s+of\b)?[,:]?\s*')


def unframed(text):
    return re.sub(r'\s{2,}', ' ', FRAMING.sub('', str(text or ''))).strip(' ,;')


# Each later image round varies the moment and the pose; the camera comes from pick().
FRESH = ('Fresh take: a different moment of the same action, different arm and head positions.',
         'Fresh take: a different gesture and a stronger expression.',
         'Fresh take: a different body pose, turned further toward the camera.',
         'Fresh take: a different composition with clear foreground and background depth.')


def fresh(round_, variant):
    return FRESH[(round_ * 2 + variant) % len(FRESH)] if round_ else ''


# --- 2) CPU camera on talking shots (export) ---------------------------------------------------

MOVES = ('push', 'pull', 'drift', 'punch')
Y = .35               # zoom centre a bit higher than 0.18 (0.42): the top crop stays small, faces stay in the frame
LIMIT = 1.16          # largest zoom: 576x1024 material gets soft above ~1.25
TIGHT = {'ecu': .5, 'cu': .5}    # a close-up already fills the frame with the face: half the move


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
    line always punches in as well. A close-up ('shot' from the chosen image) moves half as much.
    Captions are burnt in after the zoom, so they never move."""
    scene = scenes[index]
    if not talking(scene): return None
    k = sum(talking(s) for s in scenes[:index]); lines = scene['lines']; T = float(scene['seconds'])
    a = TIGHT.get(scene.get('shot'), 1.); top = 1 + (LIMIT - 1) * a
    t = f'(on/{fps}+{t0:.6f})'; p = f'{t}/{T:.6f}'; x, y = '(iw-iw/zoom)/2', f'(ih-ih/zoom)*{Y:.2f}'; move = MOVES[k % len(MOVES)]
    at = punch_at(lines[0]) if move == 'punch' and len(lines) == 1 else None
    if move == 'pull': zoom = f'({1 + .12 * a:.3f}-{.10 * a:.3f}*{p})'
    elif move == 'drift':
        start, end = (.15, .85) if (k // len(MOVES)) % 2 == 0 else (.85, .15)
        zoom = f'{1 + .10 * a:.3f}'; x = f'(iw-iw/zoom)*({start:.2f}{end - start:+.2f}*{p})'
    elif at is not None: zoom = f'(1+{.04 * a:.3f}*{p})*if(gte({t}\\,{at:.6f})\\,{1 + .11 * a:.3f}\\,1)'
    else: zoom = f'(1+{.10 * a:.3f}*{p})'
    if len(lines) >= 2: zoom = f'min({top:.3f}\\,{zoom}*if(gte({t}\\,{float(lines[1].get("offset", 0)):.6f})\\,{1 + .10 * a:.3f}\\,1))'
    return zoom, (x, y)


def chosen(scene):
    """Shot type of the image Cay chose (recorded with each variant under the pin), else None."""
    return next((v.get('shot') for v in scene.get('variants') or [] if v.get('id') == scene.get('selected')), None)


def export_fields(d, scene):
    """Per-scene export spec fields under the pin: the chosen shot type (the camera keeps faces in the frame)."""
    shot = chosen(scene) if active(d) else None
    return {'shot': shot} if shot else {}


# --- 3) Native cadence and silent shot lengths ---------------------------------------------------

NATIVE_FRAMES = 81    # longest Wan clip (as before); played 1:1 it lasts 3.24 s at 25 fps
# Frames of the silent action shots, in turn: 4k+1 each (whole Wan clips, nothing stretched,
# frozen or thrown away), 1.64 to 2.76 s at 25 fps. The mean is 53 frames, the clip of every 0.18
# silent action shot (3.2 s at 16 fps), so a silent shot costs the same GPU time; it is shorter
# and its motion plays at full speed. A wide shot keeps the 41 frames of the 0.18 one (2.4 s).
ACTION_FRAMES = (53, 41, 61, 45, 69, 49, 57, 49)
ESTABLISH_FRAMES = 41


def native_frames(seconds, fps):
    """Wan frames for a silent clip shown 1:1: the next 4k+1 count that covers every delivered frame."""
    shown = round(float(seconds) * fps)
    frames = 4 * math.ceil((shown - 1) / 4) + 1
    if shown < 2 or frames > NATIVE_FRAMES: raise ValueError(f'Ein Bewegungsabschnitt muss zwischen 2 und {NATIVE_FRAMES} Bildern lang sein.')
    return frames


def clip_frames(frames):
    """Delivered frames per Wan clip of a silent shot: at most NATIVE_FRAMES each, all 4k+1 when the
    total allows it (whole_clips), else an even split (covered by native_frames, the rest trimmed)."""
    frames = int(frames); count = max(1, math.ceil(frames / NATIVE_FRAMES))
    if (frames - count) % 4 == 0 and frames >= 5 * count:
        units = (frames - count) // 4
        return [4 * (units // count + (i < units % count)) + 1 for i in range(count)]
    return [frames // count + (i < frames % count) for i in range(count)]


def whole_clips(frames):
    """The smallest frame count >= frames that splits into whole Wan clips (4k+1 frames each)."""
    frames = int(frames); count = max(1, math.ceil(frames / NATIVE_FRAMES))
    return max(5 * count, frames + (count - frames) % 4)


def silent_base(scenes, talking_flags, base, fps):
    """Layout 18 bases with the 0.19 silent lengths: action shots in turn from ACTION_FRAMES, a wide
    establishing shot ESTABLISH_FRAMES. Talking shots and reactions (their voice decides) stay."""
    from factory_timing import off_screen
    out = list(base); k = 0
    for i, (scene, talk) in enumerate(zip(scenes, talking_flags)):
        if talk or off_screen(scene): continue
        if scene.get('kind') == 'establish': out[i] = ESTABLISH_FRAMES / fps
        else: out[i] = ACTION_FRAMES[k % len(ACTION_FRAMES)] / fps; k += 1
    return out


def snap_silent(times, talking_flags, fps):
    """Silent shots (Wan) last whole clips after the minimum length was distributed: only ever adds
    at most three frames per shot, so the minimum stays met and no rendered frame is thrown away."""
    return [t if talk else whole_clips(round(t * fps)) / fps for t, talk in zip(times, talking_flags)]


# --- 4) Motion text ------------------------------------------------------------------------------

# Damping words in the motion text slow Wan down further (4-step LoRA, cfg 1: the text is the
# only steering). 'stop-motion' in the clay look asks for choppy, slow movement.
DAMPING = re.compile(r'(?i)\b(?:calm(?:ly)?|stead(?:y|ily)|subtl(?:e|y)|slow(?:ly)?(?:[- ]motion)?|gentl(?:e|y)|smooth(?:ly)?|soft(?:ly)?|'
                     r'leisurely|relaxed|stop[- ]motion)\b')


def undamp(text):
    out = DAMPING.sub('', str(text or ''))
    out = re.sub(r'\b(an?|the)\s+(?=[,.;]|$)', '', out)
    out = re.sub(r'\b([Aa])\s+(?=[aeiouAEIOU])', r'\1n ', out)
    out = re.sub(r'(?:\s*,){2,}', ',', re.sub(r'\s+([,.;:])', r'\1', re.sub(r'\s{2,}', ' ', out)))
    return re.sub(r'\b(an?|and|with)\s*([,.;]|$)', r'\2', out).strip(' ,;')


# The lip-sync split (lipsync_shots.CAMERAS) opens animation text with a framing; the still decides it now.
OPENING = re.compile(r'(?i)^(?:dynamic\s+|low-angle\s+)?medium\s+(?:close-up|shot)(?:\s+with\s+a\s+(?:slow\s+)?push-in)?\s+of\s+')
CAMERA_MOVES = ('whip pan following the move', 'fast dolly in toward the action', 'crash zoom onto the action',
                'handheld camera following the action closely', 'fast tracking shot alongside the movement', 'quick low-angle push-in')
# InfiniteTalk's text after the shot text (render_studio.SUFFIX asked for a calm body in every pause).
TALK_SUFFIX = (' Only the single visible character speaks, exactly when the supplied voice speaks. While the voice speaks: big expressive '
               'head turns, nods, shoulder and hand gestures. Whenever the voice is silent the mouth stays closed and the eyes and head keep '
               'reacting. Stable identity, the same face in every frame.')


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
        return base + ('A fast, dynamic reveal of the location' + (f', {who} moving with purpose, lips closed. ' if names else ', the place and its props in motion. ')
                       + 'Camera: fast crane down and dolly in into the location.')
    if lines:
        return base + (f'{lines[0]["speaker"]} talks with big expressive cartoon acting while the voice speaks: the head turns and nods, '
                       'leans toward the camera, shoulders and hands move with the rhythm of the words. Mouth closed whenever the voice is silent.')
    return base + ('Fast, energetic, clearly visible physical action at full speed with anticipation and overshoot, big readable poses, '
                   f'things in the scene react to the movement. Every mouth stays closed the whole time, faces show the feeling with the eyes and eyebrows. Camera: {move}.')


def motion_prompt(style, movement, scene, lines, index):
    """Wan / InfiniteTalk text under 0.19: look and movement without damping words, then the direction."""
    movement = undamp(OPENING.sub('', str(movement or '').strip())) or 'moves with a clear, fast physical action'
    return undamp(style).rstrip('.') + '. ' + movement[:1].upper() + movement[1:].rstrip('.') + '. ' + direction(scene, lines, index)
