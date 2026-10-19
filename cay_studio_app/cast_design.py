"""Character identity: one design per figure, reused unchanged in every scene.

0.16: templates only restyle a design that was made from text; scene images
get the figure designs and nothing else.

0.17, after the Krusty film (Mr. Krabs a red sausage, Plankton a green
SpongeBob, extra figures in single-figure shots):
1) Known originals skip the template style pass; templates turned their body
   into the templates' human shapes. 2) The identity prompt names a figure by
   its own name only; "... from the animated series SpongeBob SquarePants" put
   the word SpongeBob into every design and scene. 3) Body plan and size come
   first, no "neutral standing pose" that turns crabs into humans. 4) Image text
   only names figures in the frame; other names are removed from style and
   scene text. 5) Optional check stop: Cay sees the figures before ~2 minutes of
   scene images and before any animation.
"""
import hashlib, json, re
from image_workflow import build_graph

POLICY = 3
SHEET = ("Full body, front three-quarter view, the character's own natural body shape and size "
         '(not turned into a human unless the original is human), plain light background, a single character, no text.')


def is_known(person):
    return bool(str(person.get('original', '')).strip())


def name_parts(name):
    return sorted({name} | {p for p in re.split(r'[\s.]+', name) if len(p) >= 4}, key=len, reverse=True)


def strip_names(text, names, protected=(), aliases=None):
    """Remove figure names from free text (same matching as screenplay.sanitize:
    full name in any case, capitalised name parts, never a part of a visible figure)."""
    from screenplay import _strip, _expand
    seen = _expand(protected, aliases)
    out = _strip(str(text or ''), [n for n in _expand(names, aliases) if n not in seen], seen)
    return re.sub(r'\s{2,}', ' ', re.sub(r'\s+([,.;])', r'\1', out)).strip()


def own_name(person, cast_names=()):
    """'Mr. Krabs from the animated series SpongeBob SquarePants' -> 'Mr. Krabs'.
    The series stays only if it names no other figure of this cast."""
    original = str(person.get('original', '')).strip()
    if not original: return person['name']
    who, _, series = original.partition(' from ')
    others = [n for n in cast_names if n != person['name']]
    if series and not any(re.search(r'(?i)(?<!\w)' + re.escape(p) + r'(?!\w)', series) for o in others for p in name_parts(o)):
        return f'{who.strip()} from {series.strip()}'
    return who.strip() or person['name']


# 0.19 (shot_policy 19): Cay's figures stood on their display base in the scenes (Weißes Gold).
NO_BASE = ' No pedestal, display base, stand or turntable under the figure.'


def identity_prompt(person, style, cast_names=(), policy=0):
    others = [n for n in cast_names if n != person['name']]
    who = strip_names(own_name(person, cast_names), others, [person['name']]) or person['name']
    known = ('The well-known cartoon character exactly as in the original, instantly recognisable, not a look-alike or a new version. '
             if is_known(person) else '')
    return (f'Character sheet of {who}. Body and look: ' + strip_names(person['appearance'], others, [person['name']]).strip().rstrip('.') + '. ' + known
            + 'Rendered as: ' + strip_names(style, others, [person['name']]).strip() + ' ' + SHEET + (NO_BASE if policy >= 19 else ''))


def neutral_prompt(person, style, cast_names=(), policy=0):
    """Redraw an uploaded figure with a neutral face: identity from the upload, expression from
    each scene later. Cay's laughing SpongeBob photo made him laugh in every afraid line (0.17)."""
    name = person['name']; others = [n for n in cast_names if n != name]
    return (f'Character sheet of {name}, the same character as in reference image 1: copy the head shape, face shape, '
            'body shape, size, proportions, colours, materials, surface texture, clothing and accessories exactly. '
            'Neutral relaxed expression, mouth closed, eyes open looking forward, standing upright, arms relaxed, full body, front view. '
            'Plain light grey background, soft even light, a single character, nothing else, no text. '
            'Keep the rendering style of reference image 1. ' + strip_names(style, others, [name]).strip() + (NO_BASE if policy >= 19 else ''))


def restyle_prompt(person, style, cast_names=(), policy=0):
    """A library figure from another look (a clay profile in a cartoon film): same character,
    the film's look. Mixed looks in one frame read as a mistake."""
    name = person['name']; others = [n for n in cast_names if n != name]
    return (f'Character sheet of {name}, the same character as in reference image 1: keep the head shape, face shape, '
            'body shape, proportions, colours, clothing and accessories, so that everyone recognises the character. '
            'Redraw it completely in the visual style below: change material, surface texture and rendering to that style. '
            'Neutral relaxed expression, mouth closed, eyes open looking forward, standing upright, arms relaxed, full body, front view. '
            'Plain light grey background, soft even light, a single character, nothing else, no text. Visual style: '
            + strip_names(style, others, [name]).strip() + (NO_BASE if policy >= 19 else ''))


def other_look(image_look, film_look):
    """True if a figure's image comes from another look than the film (never for 'auto')."""
    return bool(image_look and film_look and 'auto' not in (image_look, film_look) and image_look != film_look)


def upload_key(person, upload_sha, restyle=False, style=''):
    parts = [upload_sha, person.get('design_round', 0), POLICY] + (['restyle', style] if restyle else [])
    return 'castup:' + person['name'] + ':' + digest(parts)[:12]


async def from_upload(factory, document, person, upload, upload_sha, models, restyle=False):
    """Design from Cay's own image (or a library image of another look): one image prompt with
    the upload as reference."""
    names = [p['name'] for p in document['plan'].get('cast', [])]; style = document['plan']['style']
    prompt = (restyle_prompt if restyle else neutral_prompt)(person, style, names, document.get('shot_policy', 0))
    sheet = await factory.render(document, upload_key(person, upload_sha, restyle, style),
                                 build_graph(prompt, [factory.stage(upload)],
                                             seed(person['name'], person.get('design_round', 0) + 2000), '', models))
    return sheet['output']


def style_prompt(person, style, cast_names=(), policy=0):
    name = person['name']; others = [n for n in cast_names if n != name]
    return (f'Image 1 shows {name}. Redraw exactly this character from image 1: identical face, eyes, mouth, colours, '
            'body shape, size and outfit. From the other images take only the visual style: material, surface texture, '
            'lighting and rendering. Take no person, character, face, body, hair, clothing, text or background from '
            'the other images. ' + SHEET + ' Style: ' + strip_names(style, others, [name]).strip() + (NO_BASE if policy >= 19 else ''))


def digest(value):
    # Same as factory.digest; kept local so this module stays importable alone.
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def seed(name, round_):
    return abs(int(digest(name if not round_ else [name, round_])[:12], 16))


def keys(person, examples):
    round_ = person.get('design_round', 0)
    base = 'cast3:' + person['name'] + ':' + digest([person['appearance'], person.get('original', ''), round_, POLICY])[:12]
    return base, 'caststyle:' + person['name'] + ':' + digest([base, examples])[:12]


def scene_prompt(scene, cast, names, style):
    """Positive framing: the reference images carry identity, the text says who is in the picture.
    No 'original' label (it named SpongeBob in every Krabs shot), no other figure names."""
    from screenplay import figure_aliases
    hidden = [p['name'] for p in cast if p['name'] not in names]; aliases = figure_aliases(cast)
    prompt = 'One coherent vertical 9:16 film frame, no text or panels. ' + strip_names(style, hidden, names, aliases).strip().rstrip('.') + '. '
    # 0.18 reactions (close-up) and establishing shots (wide) bring their own framing.
    if len(names) == 1: prompt += f'{names[0]} alone in the frame. ' if scene.get('kind') in ('reaction', 'establish') else f'Medium shot of {names[0]} alone. '
    for i, name in enumerate(names, 1):
        person = next(p for p in cast if p['name'] == name)
        prompt += (f'Reference image {i} is the approved design of {name}: copy {name}\'s head and face shape, colours, '
                   f'materials, body shape, size and outfit exactly from reference image {i}; facial expression, mouth, eyes and pose '
                   f'come from this scene, not from the reference image. {strip_names(person["appearance"], hidden, names, aliases).rstrip(".")}. ')
    if len(names) == 1: prompt += f'{names[0]} is the only character in the whole picture; the background shows only the location and its props. '
    elif not names: prompt += 'Only the location and its props, no characters. '
    else: prompt += f'Only {" and ".join(names)} are in the picture, nobody else. '
    return prompt + 'Never swap, blend or redesign identities. No screenshot interfaces, captions, logos, watermarks or phone controls. '


def shot_prompt(scene, cast, names, style, plan_cast, kind, r):
    """0.19 (shot_policy 19): the camera leads (shot type `kind` from shot_design.pick, role `r`),
    then the moment and the pose, then the look and the identities. FLUX.2 klein at cfg 1 follows
    the start of the text and copied the design sheet's frontal, standing, full-body pose (with its
    pedestal in Cay's clay film); the reference images now give the identity only."""
    import shot_design
    from screenplay import figure_aliases
    hidden = [p['name'] for p in cast if p['name'] not in names]; aliases = figure_aliases(cast)
    speaker = next((l.get('speaker') for l in scene.get('dialogues') or [] if l.get('speaker') in names), '')
    prompt = (shot_design.lead(kind, names, speaker, r) + '. Vertical 9:16 film frame, one coherent image, no text or panels. '
              + scene_text(scene, plan_cast, unframed=True) + ' ' + shot_design.pose(r, names, kind)
              + strip_names(style, hidden, names, aliases).strip().rstrip('.') + '. ')
    for i, name in enumerate(names, 1):
        person = next(p for p in cast if p['name'] == name)
        prompt += (f'Reference image {i} shows {name}: take only the identity from it (head and face shape, colours, materials, body shape, size and outfit); '
                   'its pose, framing, camera angle and background come from this scene instead. '
                   f'{strip_names(person["appearance"], hidden, names, aliases).rstrip(".")}. ')
    if len(names) == 1: prompt += f'{names[0]} is the only character in the whole picture; the background shows only the location and its props. '
    elif not names: prompt += 'Only the location and its props, no characters. '
    else: prompt += f'Only {" and ".join(names)} are in the picture, nobody else. '
    return prompt + ('Never swap, blend or redesign identities. No pedestal, display base, stand or turntable under any figure. '
                     'No screenshot interfaces, captions, logos, watermarks or phone controls. ')


def scene_text(scene, cast, unframed=False):
    """What the image shows. Prefers the planner's 'still' (0.17 screenplay); older plans use the
    action with every clause about an off-screen figure removed. unframed (0.19 shot_prompt): the
    leading camera sentence decides the framing, so no 'Framing:' and no framing words in the still."""
    from screenplay import sanitize, figure_aliases
    names = [p['name'] for p in cast]; visible = scene.get('cast', []); aliases = figure_aliases(cast)
    picture = sanitize(scene.get('still') or scene.get('action', ''), visible, names, aliases)
    place = strip_names(scene.get('location', ''), [n for n in names if n not in visible], visible, aliases)
    framing = sanitize(scene.get('camera', ''), visible, names, aliases)
    if unframed:
        from shot_design import unframed as bare
        picture = bare(picture); framing = ''
    return ' '.join(x for x in (f'Scene: {picture}.' if picture else '', f'Location: {place}.' if place else '', f'Framing: {framing}.' if framing else '',
                                faces(scene)))


def faces(scene):
    """Each speaking figure's face from its line's delivery, in English: the planner's still may
    leave it out, and the design sheet must not decide it (a laughing upload laughed in every
    afraid line). Image keys carry no prompt digest, so finished images stay as they are.

    0.18 reaction shot (story policy 14): the figure in the frame listens with a closed-mouth
    face; the voice belongs to a figure off-screen, which gets no face and is never named."""
    from screenplay import expression, reaction_expression
    if scene.get('kind') == 'reaction':
        face = reaction_expression(scene.get('emotion') or '')
        return ' '.join(f"{name}'s facial expression: {face}, listening in silence." for name in scene.get('cast', []))
    seen = {}
    for line in scene.get('dialogues') or ([{'speaker': scene.get('speaker'), 'emotion': scene.get('emotion')}] if scene.get('dialogue') else []):
        name = line.get('speaker')
        if name in scene.get('cast', []) and name not in seen: seen[name] = expression(line.get('emotion') or '')
    return ' '.join(f"{name}'s facial expression: {face}." for name, face in seen.items())


# Each new round of a scene image takes another camera and pose, so "Neue Bilder" really differs.
VARIATIONS = ('Fresh take: a different camera angle (slightly low angle) and a different body pose.',
              'Fresh take: closer framing on the faces and a different gesture.',
              'Fresh take: wider framing that shows more of the location, different pose.',
              'Fresh take: a different moment of the same action, different arm and head positions.',
              'Fresh take: camera from a three-quarter side angle, the figure placed off-centre.',
              'Fresh take: a different composition with clear foreground and background depth.')


def revision_prompt(prompt, note, round_, variant, policy=0, shots=False):
    """Prompt for one image round. Round 0 is the plan as written. Later rounds vary camera and pose;
    a wish from Cay (policy 18) leads the prompt as the main instruction. Older notes keep their place.
    shots (0.19, shot_policy 19): the leading camera sentence already took the round's new angle
    (shot_design.pick), so a later round only varies the moment and the pose."""
    if note and policy >= 18: prompt = f'Most important, requested by the director: {note.strip().rstrip(".")}. ' + prompt
    elif note: prompt += ' Specific correction: ' + note
    if round_ > 0 and shots:
        from shot_design import fresh
        prompt += ' ' + fresh(round_, variant)
    elif round_ > 0: prompt += ' ' + VARIATIONS[(round_ * 2 + variant) % len(VARIATIONS)]
    return prompt


def scene_references(refs, names):
    """Approved figure designs only. Look templates never enter a scene."""
    return [refs[name] for name in names]


def invalidate(document, name):
    """A figure changed: its design and every scene image showing it are redone.

    Before 0.16 only the corrected scene was redone; the other scenes kept the
    old face, which is exactly the drift Cay saw.
    """
    from factory_editor import regenerate
    document.setdefault('cast_refs', {}).pop(name, None)
    # 0.18 looks per episode: its variants were drawn from the old design.
    for box in (document.get('episode_refs') or {}).values(): box.pop(name, None)
    document.pop('cast_approval', None)
    count = 0
    for episode in document.get('episodes', []):
        for scene in episode['scenes']:
            if name in scene.get('cast', []):
                regenerate(scene, [0, 1]); count += 1
    # 0.18 title card: the key art shows the main figures; one of them changed, so it is drawn again.
    cover = document.get('cover')
    if isinstance(cover, dict) and name in cover.get('cast', []): regenerate(cover, [0, 1])
    return count


def signature(document):
    """Approval is bound to exactly these figure designs; a redesign needs a new look.
    0.18: and to the look variants per episode (without any, the digest is the one from before)."""
    refs = sorted((document.get('cast_refs') or {}).items())
    looks = sorted((ei, sorted(box.items())) for ei, box in (document.get('episode_refs') or {}).items() if box)
    return digest([refs, looks] if looks else refs)


def needs_review(document):
    """Stop once before scene images if a figure was designed (not uploaded) and Cay wants to see it."""
    if not document['idea'].get('cast_check', False): return False
    # Uploads used exactly as they are need no look; a neutral redraw of an upload does.
    # (projects from before 0.18 carry no image_mode: their uploads were always used as they are).
    look = document['idea'].get('look', 'auto')
    own = {p['name'] for p in document['idea'].get('participants', [])
           if p.get('image') and p.get('image_mode', 'exact') == 'exact' and not other_look(p.get('image_look'), look)}
    designed = [p['name'] for p in document['plan']['cast'] if p['name'] not in own]
    # A look variant per episode is always drawn by the studio, also from an upload used as it is.
    looks = any((document.get('episode_refs') or {}).values())
    return bool(designed or looks) and document.get('cast_approval') != signature(document)


async def design(factory, document, person, examples, models):
    """Return the design path for one figure; two image prompts at most."""
    style = document['plan']['style']; names = [p['name'] for p in document['plan'].get('cast', [])]
    base_key, style_key = keys(person, examples)
    round_ = person.get('design_round', 0)
    policy = document.get('shot_policy', 0)
    base = await factory.render(document, base_key, build_graph(identity_prompt(person, style, names, policy), [], seed(person['name'], round_), '', models))
    # Known originals keep their own body; templates turned Mr. Krabs into a human shape.
    if not examples or is_known(person): return base['output']
    styled = await factory.render(document, style_key, build_graph(style_prompt(person, style, names, policy), [factory.stage(base['output'])] + examples[:3],
                                                                    seed(person['name'], round_ + 1000), '', models))
    return styled['output']
