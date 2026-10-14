"""Character identity: one design per figure, reused unchanged in every scene.

Look templates are style only. Up to 0.15 they went into the character design
and, as filler, into every scene image as reference latents. The image model
then copied people from the templates into the film and blended them with the
cast, so one figure changed its face from shot to shot.

Now: 1) the figure is designed from text alone (identity), 2) only if templates
exist, that design is restyled with them (material and light, nothing else),
3) scene images receive the approved figure designs and nothing else.
"""
import hashlib, json
from image_workflow import build_graph

POLICY = 2
SHEET = 'Full body, front view, neutral standing pose, plain light background, a single character, no text.'


def is_known(person):
    return bool(str(person.get('original', '')).strip())


def identity_prompt(person, style):
    name = person['name']
    if is_known(person):
        who = (f"Character design of {person['original'].strip()}, the well-known character {name}, "
               'exactly as in the original: same face, eyes, mouth, colours, proportions and outfit. '
               'Instantly recognisable, not a look-alike or a new version. ')
    else:
        who = f'Character design of {name}. '
    return (who + person['appearance'].strip().rstrip('.') + '. Personality: ' + person.get('personality', '').strip()
            + '. Rendered as: ' + style.strip() + ' ' + SHEET)


def style_prompt(person, style):
    name = person['name']
    return (f'Image 1 shows {name}. Redraw exactly this character from image 1: identical face, eyes, mouth, colours, '
            'proportions and outfit. From the other images take only the visual style: material, surface texture, '
            'lighting and rendering. Take no person, character, face, body, hair, clothing, text or background from '
            'the other images. ' + SHEET + ' Style: ' + style.strip())


def digest(value):
    # Same as factory.digest; kept local so this module stays importable alone.
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def seed(name, round_):
    return abs(int(digest(name if not round_ else [name, round_])[:12], 16))


def keys(person, examples):
    round_ = person.get('design_round', 0)
    base = 'cast2:' + person['name'] + ':' + digest([person['appearance'], person.get('original', ''), round_])[:12]
    return base, 'caststyle:' + person['name'] + ':' + digest([base, examples])[:12]


def scene_prompt(scene, cast, names, style):
    prompt = 'One coherent vertical 9:16 film frame, no text or panels. ' + style.strip().rstrip('.') + '. '
    for i, name in enumerate(names, 1):
        person = next(p for p in cast if p['name'] == name)
        label = name + (f" ({person['original'].strip()})" if is_known(person) else '')
        prompt += (f'Reference image {i} is the approved design of {label}: copy {name}\'s face, eyes, mouth, colours, '
                   f'proportions and outfit exactly from reference image {i}. {person["appearance"].strip().rstrip(".")}. ')
    if len(names) == 1: prompt += 'Exactly one visible character and one face, all listeners outside the frame. '
    elif not names: prompt += 'No characters, people or creatures in this frame. '
    else: prompt += 'Only the characters from the reference images appear, no other people or creatures. '
    return prompt + 'Never swap, blend or redesign identities. Remove screenshot interfaces, captions, logos, watermarks and phone controls. '


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
    count = 0
    for episode in document.get('episodes', []):
        for scene in episode['scenes']:
            if name in scene.get('cast', []):
                regenerate(scene, [0, 1]); count += 1
    return count


async def design(factory, document, person, examples, models):
    """Return the design path for one figure; two image prompts at most."""
    style = document['plan']['style']
    base_key, style_key = keys(person, examples)
    round_ = person.get('design_round', 0)
    base = await factory.render(document, base_key, build_graph(identity_prompt(person, style), [], seed(person['name'], round_), '', models))
    if not examples: return base['output']
    styled = await factory.render(document, style_key, build_graph(style_prompt(person, style), [factory.stage(base['output'])] + examples[:3],
                                                                    seed(person['name'], round_ + 1000), '', models))
    return styled['output']
