"""Looks per episode (0.18): the same figure, other clothes in each episode of a series.

Cay: "Wenn ich 6 Folgen mache, will ich entweder [wählen:] jede Person sieht auf allen Folgen
gleich aus. Oder jede Folge [ändern sich] die Personen bzw. die Klamotten. Ich hab eine Idee, wo
SpongeBob am Anfang mit zerrissenen Klamotten ist und am Ende mit Anzug."

- Planning: one small planner call per episode once its scenes exist: which visible figures look
  different from their base design, and how. Only what can be put on or taken off (clothing,
  accessories, hair styling, dirt and damage, props worn); never face, body, species or body
  colours. On the episode: ep['looks'] = {name: text for the image model (English preferred)},
  ep['look_labels'] = {name: the same in a few German words for Cay}.
- Pictures: after the base designs, one variant per episode and figure with the base design as its
  only reference: d['episode_refs'][str(ei)][name]. Scene images of that episode take the variant
  instead of the base design, and the prompt names the episode look. The title card keeps the base.
- Figure check: the variants are part of the approval (cast_design.signature). 'Neu gestalten' draws
  one variant again (a new round, Cay's wish replaces the text) and only the scenes of that episode
  with that figure.

Single films, series with the same look in every episode and every project from before 0.18 have no
'looks' in their idea: no planner call, no variant, the same prompts and references as before.
"""
from fastapi import HTTPException
from fastapi.responses import FileResponse

import cast_design
from factory_cast import name_key, resolve_name
from factory_editor import regenerate
from factory_models import EpisodeLooks, LookRedo
from image_workflow import build_graph

POLICY = 1   # part of every variant key: a new prompt version never takes an old picture

INSTRUCTION = ('Du bist Kostümbildner einer Kurzfilmserie. Lege für genau diese Folge fest, welche Figuren anders aussehen als in ihrem '
               'Grunddesign (cast.appearance) und wie. Ändern darf sich nur, was man an- und ablegen kann: Kleidung, Accessoires, Frisur und '
               'Styling, Schmutz und Schäden, getragene Requisiten. Gesicht, Kopfform, Körperform, Größe, Art und Körperfarben bleiben immer gleich. '
               'Leite es aus der Idee des Nutzers (idea, episode_source) und der Handlung dieser Folge (outline) ab. Eine Entwicklung über die Staffel '
               'muss in den Folgen sichtbar werden, zum Beispiel am Anfang zerrissene Kleidung, am Ende ein Anzug; previous zeigt, wie die Figuren '
               'in den Folgen davor aussahen. Wer aussieht wie im Grunddesign, fehlt in der Liste; ändert sich nichts, ist die Liste leer. '
               'look: kurze konkrete Beschreibung auf Englisch für das Bildmodell, nur Kleidung und Zustand, ohne Namen anderer Figuren '
               '(zum Beispiel "torn dirty white shirt, ripped brown shorts, barefoot"). label: dasselbe in wenigen deutschen Wörtern für den '
               'Regisseur (zum Beispiel "zerrissene Kleidung").')


# ---------- project ----------

def wanted(d):
    """True for a series whose figures change their clothes from episode to episode."""
    idea = d.get('idea') or {}
    return idea.get('looks') == 'per_episode' and idea.get('episodes', 1) > 1


def stored(idea):
    """The idea document of a new project: 'looks' only for a series that chose it."""
    if idea.get('looks') != 'per_episode' or idea.get('episodes', 1) < 2: idea.pop('looks', None)
    return idea


def visible(episode):
    """Figures seen in at least one scene of this episode, in the order they first appear."""
    seen = []
    for scene in episode.get('scenes', []):
        seen += [name for name in scene.get('cast', []) if name not in seen]
    return seen


def looks(d, ei):
    return ((d.get('episodes') or [])[ei].get('looks') or {}) if wanted(d) and 0 <= ei < len(d.get('episodes') or []) else {}


def refs_for(d, ei):
    """Variants of episode ei by figure name (empty without looks per episode)."""
    return dict((d.get('episode_refs') or {}).get(str(ei)) or {}) if wanted(d) else {}


def cast_for(d, ei):
    """The plan's cast as the pictures of episode ei see it: each changed figure's appearance ends with
    ' In this episode: <look>'. Without looks it is the plan's own list, so every prompt stays as it was."""
    changed = looks(d, ei)
    if not changed: return d['plan']['cast']
    return [{**p, 'appearance': p['appearance'].rstrip().rstrip('.') + '. In this episode: ' + changed[p['name']].strip().rstrip('.')}
            if p['name'] in changed else p for p in d['plan']['cast']]


def missing(d):
    """(episode, name) of every look whose variant is not drawn yet."""
    return [(ei, name) for ei in range(len(d.get('episodes') or [])) for name in looks(d, ei) if name not in refs_for(d, ei)]


def invalidate(d, ei, name):
    """One figure's look in one episode changed: its variant and the scene images of that episode
    showing it are drawn again (scenes without pictures yet simply use the new variant)."""
    ((d.get('episode_refs') or {}).get(str(ei)) or {}).pop(name, None)
    d.pop('cast_approval', None); count = 0
    for scene in d['episodes'][ei]['scenes']:
        if name in scene.get('cast', []) and scene.get('variants'): regenerate(scene, [0, 1]); count += 1
    return count


# ---------- planning ----------

def clean(text):
    return ' '.join(str(text or '').split())


async def plan_episode(factory, d, index, outline, idea_text, episode_text, episode):
    """ep['looks'] and ep['look_labels'] of one planned episode. Advisory: if the planner fails, the
    figures keep their base design in this episode and Cay can set a look in the cast panel."""
    cast = {p['name']: p for p in d['plan']['cast']}; names = [n for n in visible(episode) if n in cast]
    episode['looks'] = {}; episode['look_labels'] = {}
    if not names: return episode
    data = {'idea': idea_text, 'episode_source': episode_text if episode_text != idea_text else '',
            'series': {k: d['plan'].get(k, '') for k in ('title', 'synopsis')}, 'episode': index + 1, 'total': d['idea']['episodes'],
            'outline': outline, 'cast': [{'name': n, 'appearance': cast[n]['appearance']} for n in names],
            'previous': [{'episode': i + 1, 'looks': ep.get('looks') or {}} for i, ep in enumerate(d['episodes'])]}
    try: answer = await factory.llm(EpisodeLooks, INSTRUCTION, data)
    except RuntimeError as error:
        episode.setdefault('warnings', []).append(f'Das Aussehen der Figuren für Folge {index + 1} ließ sich nicht planen. Sie sehen aus wie im '
                                                  'Grunddesign. Tippe unter „Besetzung“ auf eine Figur, um ihr Aussehen in dieser Folge festzulegen.')
        factory.atomic(factory.folder(d) / 'Diagnose' / f'Aussehen_Folge_{index + 1}.txt', str(error).encode())
        return episode
    for item in answer['looks']:
        name = resolve_name(item['name'], names); text = clean(item['look']) or clean(item['label'])
        if name not in names or not text or name in episode['looks']: continue
        episode['looks'][name] = text; episode['look_labels'][name] = clean(item['label']) or text[:80]
    return episode


# ---------- pictures ----------

def look_prompt(person, look, style, cast_names=()):
    """The base design as reference image 1, only clothing and condition change."""
    name = person['name']; others = [n for n in cast_names if n != name]
    return (f'Character sheet of {name}, the same character as in reference image 1: identical face, head shape, eyes, mouth, body shape, '
            'size, proportions, skin and body colours, the same species, materials and surface texture. Only the clothing and condition change, to: '
            + cast_design.strip_names(look, others, [name]).strip().rstrip('.') + '. Full body, front three-quarter view, neutral relaxed expression, '
            'mouth closed, eyes open looking forward, standing upright in a neutral pose, arms relaxed. Plain light background, soft even light, '
            'a single character, nothing else, no text. Same art style and rendering as reference image 1. ' + cast_design.strip_names(style, others, [name]).strip())


def key(d, ei, name, base):
    """Stable for a restart: episode, figure, round, and the base design and look it was drawn from
    (a new base design or text never takes the old picture)."""
    ep = d['episodes'][ei]
    return f'look:{ei}:{name_key(name)}:{(ep.get("look_rounds") or {}).get(name, 0)}:' + cast_design.digest([base, ep['looks'][name], POLICY])[:12]


async def render(factory, d, refs, models):
    """One variant per episode and figure with a look, after the base designs and before the figure check.
    False: stopped at a safe point (paused, or a kept library choice was applied), like the loops around it."""
    if not wanted(d): return True
    store = d.setdefault('episode_refs', {}); names = [p['name'] for p in d['plan']['cast']]
    for ei, ep in enumerate(d['episodes']):
        for name, look in (ep.get('looks') or {}).items():
            if factory.paused(d['id']) or factory.apply_pending(d): return False
            person = next((p for p in d['plan']['cast'] if p['name'] == name), None)
            if person is None or name not in refs or name in (store.get(str(ei)) or {}): continue
            d['phase'] = f'Folge {ei + 1}: Aussehen von {name} gestalten'; factory.save(d)
            k = key(d, ei, name, refs[name])
            step = await factory.render(d, k, build_graph(look_prompt(person, look, d['plan']['style'], names), [factory.stage(refs[name])],
                                                          int(cast_design.digest(d['id'] + k)[:12], 16), '', models))
            store.setdefault(str(ei), {})[name] = step['output']; factory.save(d)
    return True


# ---------- routes ----------

def add_routes(factory, app):
    """One look variant drawn again (with Cay's wish) and its picture."""
    f = factory

    @app.post('/api/factory/{rid}/look/redo')
    async def look_redo(rid: str, body: LookRedo):
        d = f.get(rid); f.image_open(d)
        if not wanted(d): raise HTTPException(409, 'In diesem Projekt sehen die Figuren in allen Folgen gleich aus.')
        if not 0 <= body.episode < len(d.get('episodes') or []): raise HTTPException(404, 'Folge fehlt.')
        if body.name not in [p['name'] for p in d['plan']['cast']]: raise HTTPException(404, 'Figur gehört nicht zu diesem Projekt.')
        ep = d['episodes'][body.episode]; note = clean(body.note); n = body.episode + 1
        if body.name not in visible(ep): raise HTTPException(400, f'{body.name} ist in Folge {n} nicht zu sehen.')
        if not note and not (ep.get('looks') or {}).get(body.name): raise HTTPException(400, f'Beschreib, wie {body.name} in Folge {n} aussehen soll.')
        # Cay's wish replaces the planned text; his own words are then also what he reads.
        if note: ep.setdefault('looks', {})[body.name] = note; ep.setdefault('look_labels', {}).pop(body.name, None)
        rounds = ep.setdefault('look_rounds', {}); rounds[body.name] = rounds.get(body.name, 0) + 1
        count = invalidate(d, body.episode, body.name)
        if d['state'] != 'blocked': d['state'] = 'pictures'
        d['phase'] = f'{body.name} in Folge {n} wird neu gestaltet' + (f' · {count} Szenen folgen' if count > 1 else ' · 1 Szene folgt' if count else ''); f.save(d)
        return f.get(rid)

    @app.get('/api/factory/{rid}/look-image/{episode}/{index}')
    def look_image(rid: str, episode: int, index: int):
        d = f.get(rid); cast = d.get('plan', {}).get('cast', [])
        path = refs_for(d, episode).get(cast[index]['name']) if 0 <= index < len(cast) else None
        if not path: raise HTTPException(404, 'Bild für diese Folge noch nicht verfügbar.')
        picture = f.path(path)
        if picture.suffix.lower() != '.png': raise HTTPException(400, 'Kein Figurenbild.')
        return FileResponse(picture, media_type='image/png')
