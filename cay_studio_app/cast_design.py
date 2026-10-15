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


def identity_prompt(person, style, cast_names=()):
    others = [n for n in cast_names if n != person['name']]
    who = strip_names(own_name(person, cast_names), others, [person['name']]) or person['name']
    known = ('The well-known cartoon character exactly as in the original, instantly recognisable, not a look-alike or a new version. '
             if is_known(person) else '')
    return (f'Character sheet of {who}. Body and look: ' + strip_names(person['appearance'], others, [person['name']]).strip().rstrip('.') + '. ' + known
            + 'Rendered as: ' + strip_names(style, others, [person['name']]).strip() + ' ' + SHEET)


def style_prompt(person, style, cast_names=()):
    name = person['name']; others = [n for n in cast_names if n != name]
    return (f'Image 1 shows {name}. Redraw exactly this character from image 1: identical face, eyes, mouth, colours, '
            'body shape, size and outfit. From the other images take only the visual style: material, surface texture, '
            'lighting and rendering. Take no person, character, face, body, hair, clothing, text or background from '
            'the other images. ' + SHEET + ' Style: ' + strip_names(style, others, [name]).strip())


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
    if len(names) == 1: prompt += f'Medium shot of {names[0]} alone. '
    for i, name in enumerate(names, 1):
        person = next(p for p in cast if p['name'] == name)
        prompt += (f'Reference image {i} is the approved design of {name}: copy {name}\'s face, eyes, mouth, colours, '
                   f'body shape, size and outfit exactly from reference image {i}. {strip_names(person["appearance"], hidden, names, aliases).rstrip(".")}. ')
    if len(names) == 1: prompt += f'{names[0]} is the only character in the whole picture; the background shows only the location and its props. '
    elif not names: prompt += 'Only the location and its props, no characters. '
    else: prompt += f'Only {" and ".join(names)} are in the picture, nobody else. '
    return prompt + 'Never swap, blend or redesign identities. No screenshot interfaces, captions, logos, watermarks or phone controls. '


def scene_text(scene, cast):
    """What the image shows. Prefers the planner's 'still' (0.17 screenplay); older plans use the
    action with every clause about an off-screen figure removed."""
    from screenplay import sanitize, figure_aliases
    names = [p['name'] for p in cast]; visible = scene.get('cast', []); aliases = figure_aliases(cast)
    picture = sanitize(scene.get('still') or scene.get('action', ''), visible, names, aliases)
    place = strip_names(scene.get('location', ''), [n for n in names if n not in visible], visible, aliases)
    framing = sanitize(scene.get('camera', ''), visible, names, aliases)
    return ' '.join(x for x in (f'Scene: {picture}.' if picture else '', f'Location: {place}.' if place else '', f'Framing: {framing}.' if framing else ''))


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
    document.pop('cast_approval', None)
    count = 0
    for episode in document.get('episodes', []):
        for scene in episode['scenes']:
            if name in scene.get('cast', []):
                regenerate(scene, [0, 1]); count += 1
    return count


def signature(document):
    """Approval is bound to exactly these figure designs; a redesign needs a new look."""
    return digest(sorted((document.get('cast_refs') or {}).items()))


def needs_review(document):
    """Stop once before scene images if a figure was designed (not uploaded) and Cay wants to see it."""
    if not document['idea'].get('cast_check', False): return False
    own = {p['name'] for p in document['idea'].get('participants', []) if p.get('image')}
    designed = [p['name'] for p in document['plan']['cast'] if p['name'] not in own]
    return bool(designed) and document.get('cast_approval') != signature(document)


async def design(factory, document, person, examples, models):
    """Return the design path for one figure; two image prompts at most."""
    style = document['plan']['style']; names = [p['name'] for p in document['plan'].get('cast', [])]
    base_key, style_key = keys(person, examples)
    round_ = person.get('design_round', 0)
    base = await factory.render(document, base_key, build_graph(identity_prompt(person, style, names), [], seed(person['name'], round_), '', models))
    # Known originals keep their own body; templates turned Mr. Krabs into a human shape.
    if not examples or is_known(person): return base['output']
    styled = await factory.render(document, style_key, build_graph(style_prompt(person, style, names), [factory.stage(base['output'])] + examples[:3],
                                                                    seed(person['name'], round_ + 1000), '', models))
    return styled['output']
