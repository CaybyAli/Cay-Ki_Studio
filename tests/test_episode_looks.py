"""Looks per episode (0.18). Cay: "Wenn ich 6 Folgen mache, will ich entweder [wählen:] jede Person sieht auf
allen Folgen gleich aus. Oder jede Folge [ändern sich] die Personen bzw. die Klamotten. Ich hab eine Idee, wo
SpongeBob am Anfang mit zerrissenen Klamotten ist und am Ende mit Anzug."

A real Factory on a temporary database (tests/studio_fakes.py): the planner is a fake Ollama, ComfyUI a fake that
finishes every image at once with a small real PNG whose content depends only on the step key. So the graphs handed
to ComfyUI are deterministic and can be compared with what the code before this feature drew (OLD_DRAWING)."""
import asyncio
import hashlib
import json
import struct
import zlib

import httpx
import pytest

from studio_fakes import client, factory as studio, project

RID = 'e' * 32
CAST = [{'name': 'SpongeBob', 'appearance': 'yellow square sea sponge, white shirt, red tie, brown square pants', 'original': '',
         'personality': 'fröhlich', 'voice_preset': 'young_man'},
        {'name': 'Patrick', 'appearance': 'pink starfish, green shorts with purple flowers', 'original': '', 'personality': 'langsam', 'voice_preset': 'man'}]
LOOKS = [{'SpongeBob': 'torn dirty shirt, ripped shorts, barefoot'}, {'SpongeBob': 'expensive tailored navy suit, silk tie'}]
# What the code before looks per episode (2145ba4) drew for series() without 'looks': digest of drawing() over the
# key and graph (without file names) of every image in order. Made by running this file's helpers on that commit.
OLD_DRAWING = 'f15c0a9506930735b98224546c3cf7d66b5558d2e6dc972a4512d9c21c852dc4'


def png(path, text):
    """A real 2 x 2 PNG; its pixels come from the text, so equal steps give equal files."""
    def chunk(kind, data): return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    seed = hashlib.sha256(text.encode()).digest()
    raw = b''.join(b'\x00' + seed[row * 6:row * 6 + 6] for row in range(2))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
    return path


def finishing(f):
    """ComfyUI that finishes every image the moment it is handed over."""
    comfy = f.services

    def done():
        n, pid, graph, extra, _ = comfy.pending.pop()
        key = f.rows('SELECT step_key FROM factory_steps WHERE id=?', (extra['cay_factory_step'],))[0]['step_key']
        png(f.comfy / 'output' / (pid + '.png'), key)
        comfy.history[pid] = {'prompt': [n, pid, graph, extra, []], 'status': {'completed': True, 'status_str': 'success'},
                              'outputs': {'77': {'images': [{'filename': pid + '.png', 'subfolder': '', 'type': 'output'}]}}}
    comfy.on_prompt = done


def scene(cast, still):
    return {'title': 'Szene', 'action': still, 'still': still, 'kind': 'line', 'location': 'Krusty Krab', 'camera': 'medium shot', 'cast': cast,
            'dialogues': [{'speaker': cast[0], 'text': 'Ich schaffe das heute.', 'emotion': 'ruhig', 'pause_after': .18}], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'attempt', 'variants': [], 'selected': None, 'round': 0}


def series(looks=None, cast_check=False):
    """Two episodes; SpongeBob changes his clothes, Patrick does not. The episodes carry looks even where the idea
    does not ask for them: only the idea's choice may switch them on."""
    idea = {'idea': 'SpongeBob ist arm und trägt zerrissene Kleidung, am Ende trägt er einen Anzug.', 'episodes': 2, 'duration': 15, 'look': 'cartoon',
            'cover': 'start', 'cast_check': cast_check, **({'looks': looks} if looks else {})}
    episodes = [{'title': 'Arm', 'scenes': [scene(['SpongeBob'], 'SpongeBob counts his last coins'), scene(['SpongeBob', 'Patrick'], 'SpongeBob and Patrick share a crumb')],
                 'looks': dict(LOOKS[0]), 'look_labels': {'SpongeBob': 'zerrissene Kleidung'}},
                {'title': 'Reich', 'scenes': [scene(['SpongeBob', 'Patrick'], 'SpongeBob shows Patrick his new office'), scene(['Patrick'], 'Patrick stares at a gold coin')],
                 'looks': dict(LOOKS[1]), 'look_labels': {'SpongeBob': 'teurer Anzug'}}]
    return idea, {'edit_policy': 18, 'plan': {'title': 'Vom Schwamm zum Boss', 'cast': [dict(p) for p in CAST], 'style': 'Bright cartoon look.', 'mood': 'playful'},
                  'episodes': episodes, 'cast_refs': {}}


def run(tmp_path, monkeypatch, looks=None, cast_check=False):
    import factory
    f = studio(tmp_path, monkeypatch); finishing(f)
    monkeypatch.setattr(factory, 'validate_nodes', lambda info: {})

    async def info(): return {}
    f.object_info = info
    idea, extra = series(looks, cast_check)
    project(f, RID, 'pictures', extra, idea)
    asyncio.run(f.pictures(f.get(RID)))
    return f


def drawing(f, start=0):
    """(step key, graph without file names) of every image handed to ComfyUI, in order."""
    out = []
    for _, body in f.services.prompts()[start:]:
        key = f.rows('SELECT step_key FROM factory_steps WHERE id=?', (body['extra_data']['cay_factory_step'],))[0]['step_key']
        graph = json.loads(json.dumps(body['prompt'])); graph['77']['inputs'].pop('filename_prefix')
        out.append((key, graph))
    return out


def fingerprint(f):
    return hashlib.sha256(json.dumps(drawing(f), sort_keys=True).encode()).hexdigest()


def references(graph): return [n['inputs']['image'] for _, n in sorted(graph.items(), key=lambda x: int(x[0])) if n['class_type'] == 'LoadImage']
def text(graph): return next(n['inputs']['text'] for n in graph.values() if n['class_type'] == 'CLIPTextEncode')


def staged(f, path):
    return 'CayStudio/factory_refs/' + hashlib.sha256(open(path, 'rb').read()).hexdigest() + '.png'


# ---------- what a new project stores ----------

def test_only_a_series_that_chose_it_stores_looks(tmp_path, monkeypatch):
    from factory_models import Idea
    from episode_looks import stored, wanted
    base = {'request_key': 'a' * 32, 'idea': 'SpongeBob wird vom armen Schwamm zum Boss.', 'episodes': 6}
    assert 'looks' not in stored(Idea.model_validate(base).model_dump())                                    # classic view, old scripts
    assert 'looks' not in stored(Idea.model_validate({**base, 'looks': 'same'}).model_dump())
    assert 'looks' not in stored(Idea.model_validate({**base, 'episodes': 1, 'looks': 'per_episode'}).model_dump())   # a single film
    assert stored(Idea.model_validate({**base, 'looks': 'per_episode'}).model_dump())['looks'] == 'per_episode'
    with pytest.raises(ValueError): Idea.model_validate({**base, 'looks': 'random'})
    assert not wanted({'idea': {'episodes': 6}}) and not wanted({'idea': {'episodes': 1, 'looks': 'per_episode'}}) and wanted({'idea': {'episodes': 2, 'looks': 'per_episode'}})
    api = client(studio(tmp_path, monkeypatch))
    run = api.post('/api/factory', json={**base, 'request_key': 'b' * 32, 'looks': 'per_episode'}).json()
    assert run['idea']['looks'] == 'per_episode'
    same = api.post('/api/factory', json={**base, 'request_key': 'c' * 32}).json()
    assert 'looks' not in same['idea']
    assert api.post('/api/factory', json={**base, 'request_key': 'c' * 32}).json()['id'] == same['id']      # the same request stays one project


# ---------- planning ----------

def planning(tmp_path, monkeypatch, looks=None, episodes=2, answers=None):
    """plan() for a series whose header and outlines exist; screenplays are faked, the planner answers looks and posts."""
    import factory
    import screenplay
    f = studio(tmp_path, monkeypatch); calls = []
    f.idle = lambda *a, **kw: asyncio.sleep(0)
    monkeypatch.setattr(factory, 'plan_seconds', lambda *a: None)

    async def write(fac, d, index, outline, source, continuity, spine):
        visible = (['SpongeBob', 'Patrick'], ['SpongeBob'])[index % 2]
        return {'title': outline['title'], 'scenes': [scene(visible, 'x'), scene(visible[:1], 'y'), scene(visible[-1:], 'z')], 'story_policy': 14}
    monkeypatch.setattr(screenplay, 'write_episode', write)

    def chat(request, body):
        props = body['format'].get('properties', {}); data = json.loads(body['messages'][1]['content'])
        if 'looks' in props:
            calls.append((body, data)); content = {'looks': (answers or {}).get(data['episode'], [])}
        elif 'caption' in props: content = {'caption': 'Wer gewinnt heute den letzten Keks?', 'hashtags': ['keks', 'serie', 'comedy']}
        else: raise AssertionError('Unerwarteter Planungsaufruf: ' + json.dumps(props)[:200])
        return httpx.Response(200, json={'done': True, 'done_reason': 'stop', 'message': {'content': json.dumps(content)}})
    f.services.chat = chat
    outlines = [{'title': f'Folge {n}', 'plot': 'SpongeBob arbeitet sich nach oben.', 'ending': 'Er hat es geschafft.', 'pickup': '', 'cliffhanger': ''}
                for n in range(1, episodes + 1)]
    idea = {'idea': 'SpongeBob ist am Anfang arm und trägt zerrissene Kleidung, am Ende trägt er einen Anzug.', 'episodes': episodes,
            **({'looks': looks} if looks else {})}
    project(f, RID, 'planning', {'preflight': {'checks': []}, 'spines': {str(i): None for i in range(episodes)},
                                 'plan': {'title': 'Vom Schwamm zum Boss', 'synopsis': 'Ein armer Schwamm wird reich.', 'style': 'cartoon',
                                          'visual': 'cartoon', 'mood': 'playful', 'cast': [dict(p) for p in CAST], 'episodes': outlines}}, idea)
    f.sql("UPDATE factory_runs SET document=json_remove(document,'$.source') WHERE id=?", (RID,))
    asyncio.run(f.plan(f.get(RID)))
    return f.get(RID), calls


RAGS = {1: [{'name': 'SpongeBob', 'label': 'zerrissene Kleidung', 'look': 'torn dirty shirt, ripped brown shorts, barefoot'},
            {'name': 'Plankton', 'label': 'Hut', 'look': 'tiny top hat'}],                           # not in the cast: dropped
        2: [{'name': 'SpongeBob', 'label': 'teurer Anzug', 'look': 'Expensive tailored navy suit with a silk tie. ' * 12}]}   # too long: cut


def test_looks_are_planned_per_episode_from_the_idea(tmp_path, monkeypatch):
    d, calls = planning(tmp_path, monkeypatch, 'per_episode', answers=RAGS)
    assert d['state'] == 'pictures' and len(calls) == 2                                              # one small call per episode
    first, second = calls
    assert first[0]['format']['$defs']['FigureLook']['properties']['name']['enum'] == ['SpongeBob', 'Patrick']   # only who is seen in it
    assert second[0]['format']['$defs']['FigureLook']['properties']['name']['enum'] == ['SpongeBob']
    assert 'zerrissene Kleidung' in first[1]['idea'] and first[1]['outline']['title'] == 'Folge 1' and first[1]['previous'] == []
    assert 'Körperform' in first[0]['messages'][0]['content'] and 'Kleidung' in first[0]['messages'][0]['content']
    assert second[1]['previous'] == [{'episode': 1, 'looks': {'SpongeBob': 'torn dirty shirt, ripped brown shorts, barefoot'}}]
    one, two = d['episodes']
    assert one['looks'] == {'SpongeBob': 'torn dirty shirt, ripped brown shorts, barefoot'} and one['look_labels'] == {'SpongeBob': 'zerrissene Kleidung'}
    assert list(two['looks']) == ['SpongeBob'] and len(two['looks']['SpongeBob']) <= 300 and two['looks']['SpongeBob'].endswith('tie.')


@pytest.mark.parametrize('looks,episodes', [(None, 2), ('same', 2), ('per_episode', 1)], ids=['old-project', 'same', 'single-film'])
def test_no_looks_call_without_the_choice(tmp_path, monkeypatch, looks, episodes):
    d, calls = planning(tmp_path, monkeypatch, looks, episodes, answers=RAGS)
    assert d['state'] == 'pictures' and calls == [] and not any('looks' in ep for ep in d['episodes'])


def test_a_failed_looks_call_keeps_the_base_designs(tmp_path, monkeypatch):
    d, calls = planning(tmp_path, monkeypatch, 'per_episode', answers={1: [{'name': 'SpongeBob', 'label': 'x', 'look': 'y', 'extra': 'nicht im Schema'}]})
    assert d['state'] == 'pictures' and len(calls) == 4                                              # three attempts for episode 1, then go on
    assert d['episodes'][0]['looks'] == {} and 'ließ sich nicht planen' in d['episodes'][0]['warnings'][-1]


# ---------- pictures ----------

@pytest.mark.parametrize('looks', [None, 'same'], ids=['old-project', 'same'])
def test_same_and_old_projects_draw_exactly_as_before(tmp_path, monkeypatch, looks):
    f = run(tmp_path, monkeypatch, looks); keys = [k for k, _ in drawing(f)]
    assert keys[:2] == [k for k in keys if k.startswith('cast3:')] and not [k for k in keys if k.startswith('look:')]
    assert fingerprint(f) == OLD_DRAWING                                                             # same keys, prompts, references and seeds
    d = f.get(RID)
    assert d['state'] == 'image_review' and 'episode_refs' not in d


def test_variants_from_the_base_design_and_scenes_per_episode(tmp_path, monkeypatch):
    f = run(tmp_path, monkeypatch, 'per_episode'); d = f.get(RID); steps = dict(drawing(f))
    kinds = [k.split(':')[0] for k, _ in drawing(f)]
    assert kinds == ['cast3', 'cast3', 'look', 'look', 'cover', 'cover'] + ['image'] * 8 and d['state'] == 'image_review'
    base = {name: staged(f, path) for name, path in d['cast_refs'].items()}
    look = {ei: staged(f, d['episode_refs'][str(ei)]['SpongeBob']) for ei in (0, 1)}
    assert set(d['episode_refs']) == {'0', '1'} and all(set(v) == {'SpongeBob'} for v in d['episode_refs'].values())
    for ei in (0, 1):
        k = next(k for k in steps if k.startswith(f'look:{ei}:spongebob:0:'))
        assert references(steps[k]) == [base['SpongeBob']]                                           # drawn from the base design only
        assert 'identical face' in text(steps[k]) and LOOKS[ei]['SpongeBob'] in text(steps[k]) and 'Patrick' not in text(steps[k])
    # Episode 2: SpongeBob's suit variant, Patrick's own base design; the prompt names the suit, not the rags.
    both = steps['image:1:0:0:0']
    assert references(both) == [look[1], base['Patrick']]
    assert 'In this episode: expensive tailored navy suit, silk tie' in text(both) and 'torn' not in text(both)
    assert references(steps['image:1:1:0:0']) == [base['Patrick']] and 'In this episode' not in text(steps['image:1:1:0:0'])
    assert references(steps['image:0:0:0:1']) == [look[0]] and 'In this episode: torn dirty shirt' in text(steps['image:0:0:0:1'])
    # The title card keeps the base designs.
    assert sorted(references(steps['cover:0:0:0'])) == sorted(base.values())
    # The image of a variant and the cast list for the animation
    import episode_looks
    picture = client(f).get(f'/api/factory/{RID}/look-image/1/0')
    assert picture.status_code == 200 and picture.headers['content-type'] == 'image/png'
    assert client(f).get(f'/api/factory/{RID}/look-image/0/1').status_code == 404                     # Patrick has no look
    assert [p['appearance'] for p in episode_looks.cast_for(d, 1)][1] == CAST[1]['appearance'] and episode_looks.cast_for(d, 0)[0]['appearance'].endswith('In this episode: torn dirty shirt, ripped shorts, barefoot')


def test_a_restart_never_draws_a_finished_look_again(tmp_path, monkeypatch):
    f = run(tmp_path, monkeypatch, 'per_episode'); before = f.get(RID); handed = len(f.services.prompts())
    # The studio stopped after the look was drawn, before the project was saved: the step itself is kept.
    f.sql("UPDATE factory_runs SET document=json_set(json_remove(document,'$.episode_refs'),'$.state','pictures') WHERE id=?", (RID,))
    asyncio.run(f.pictures(f.get(RID)))
    after = f.get(RID)
    assert len(f.services.prompts()) == handed and after['episode_refs'] == before['episode_refs'] and after['state'] == 'image_review'


def test_new_look_redraws_only_that_episode_with_that_figure(tmp_path, monkeypatch):
    f = run(tmp_path, monkeypatch, 'per_episode'); api = client(f); before = f.get(RID); handed = len(f.services.prompts())
    reply = api.post(f'/api/factory/{RID}/look/redo', json={'episode': 1, 'name': 'SpongeBob', 'note': 'grauer Anzug mit roter Krawatte'})
    assert reply.status_code == 200
    d = f.get(RID); one, two = d['episodes']
    assert d['state'] == 'pictures' and d['phase'] == 'SpongeBob in Folge 2 wird neu gestaltet · 1 Szene folgt'
    assert two['looks']['SpongeBob'] == 'grauer Anzug mit roter Krawatte' and 'SpongeBob' not in two['look_labels'] and two['look_rounds'] == {'SpongeBob': 1}
    assert two['scenes'][0]['image_rounds'] == [1, 1] and 'image_rounds' not in two['scenes'][1]               # Patrick alone keeps his pictures
    assert all('image_rounds' not in s for s in one['scenes']) and one['looks'] == before['episodes'][0]['looks']
    assert 'SpongeBob' not in d['episode_refs']['1'] and d['episode_refs']['0'] == before['episode_refs']['0']
    asyncio.run(f.pictures(f.get(RID)))
    again = drawing(f, handed)
    assert [k.rsplit(':', 1)[0] if k.startswith('look:') else k for k, _ in again] == ['look:1:spongebob:1', 'image:1:0:1:0', 'image:1:0:1:1']
    assert 'grauer Anzug mit roter Krawatte' in text(again[0][1]) and references(again[0][1]) == [staged(f, d['cast_refs']['SpongeBob'])]
    assert references(again[1][1])[0] == staged(f, f.get(RID)['episode_refs']['1']['SpongeBob']) and 'In this episode: grauer Anzug' in text(again[1][1])
    assert f.get(RID)['state'] == 'image_review'
    # Without a wish: a new round of the same text; a figure not seen in that episode or a 'same' project is refused.
    assert api.post(f'/api/factory/{RID}/look/redo', json={'episode': 0, 'name': 'SpongeBob'}).status_code == 200
    assert f.get(RID)['episodes'][0]['looks'] == LOOKS[0] and f.get(RID)['episodes'][0]['look_rounds'] == {'SpongeBob': 1}
    plain = api.post(f'/api/factory/{RID}/look/redo', json={'episode': 1, 'name': 'Patrick'})
    assert plain.status_code == 400 and 'Beschreib, wie Patrick in Folge 2 aussehen soll' in plain.json()['detail']


def test_redo_refused_where_it_does_not_apply(tmp_path, monkeypatch):
    f = run(tmp_path, monkeypatch, 'per_episode'); api = client(f)
    f.sql("UPDATE factory_runs SET document=json_set(document,'$.episodes[1].scenes[0].cast',json('[\"Patrick\"]')) WHERE id=?", (RID,))
    hidden = api.post(f'/api/factory/{RID}/look/redo', json={'episode': 1, 'name': 'SpongeBob', 'note': 'Anzug'})
    assert hidden.status_code == 400 and 'nicht zu sehen' in hidden.json()['detail']
    assert api.post(f'/api/factory/{RID}/look/redo', json={'episode': 4, 'name': 'SpongeBob', 'note': 'Anzug'}).status_code == 404
    f.sql("UPDATE factory_runs SET document=json_remove(document,'$.idea.looks') WHERE id=?", (RID,))
    assert api.post(f'/api/factory/{RID}/look/redo', json={'episode': 0, 'name': 'SpongeBob', 'note': 'Anzug'}).status_code == 409


def test_figure_check_covers_the_looks(tmp_path, monkeypatch):
    import cast_design
    f = run(tmp_path, monkeypatch, 'per_episode', cast_check=True); api = client(f); d = f.get(RID)
    assert d['state'] == 'cast_review' and set(d['episode_refs']) == {'0', '1'}                    # stops after the looks, before any scene
    assert not [k for k, _ in drawing(f) if k.startswith(('image', 'cover'))]
    assert cast_design.signature(d) != cast_design.digest(sorted(d['cast_refs'].items()))
    assert api.post(f'/api/factory/{RID}/cast/approve').json()['cast_approval'] == cast_design.signature(d)
    # A new look after the approval: the approval goes, the figure check comes again with the new variant.
    f.sql("UPDATE factory_runs SET document=json_set(document,'$.state','cast_review') WHERE id=?", (RID,))
    api.post(f'/api/factory/{RID}/look/redo', json={'episode': 0, 'name': 'SpongeBob', 'note': 'Lumpen und eine Mütze'})
    d = f.get(RID)
    assert 'cast_approval' not in d and cast_design.needs_review(d)
    f.sql("UPDATE factory_runs SET document=json_set(document,'$.state','cast_review') WHERE id=?", (RID,))
    assert api.post(f'/api/factory/{RID}/cast/approve').status_code == 409                           # the new variant is not drawn yet
    f.sql("UPDATE factory_runs SET document=json_set(document,'$.state','pictures') WHERE id=?", (RID,))
    asyncio.run(f.pictures(f.get(RID)))
    assert f.get(RID)['state'] == 'cast_review' and api.post(f'/api/factory/{RID}/cast/approve').status_code == 200


def test_a_new_base_design_draws_its_looks_again():
    import cast_design
    d = {'cast_refs': {'SpongeBob': 'a.png', 'Patrick': 'b.png'}, 'episode_refs': {'0': {'SpongeBob': 'l0.png'}, '1': {'SpongeBob': 'l1.png', 'Patrick': 'p1.png'}},
         'cast_approval': 'x', 'episodes': [{'scenes': []}]}
    cast_design.invalidate(d, 'SpongeBob')
    assert d['episode_refs'] == {'0': {}, '1': {'Patrick': 'p1.png'}} and 'cast_approval' not in d
    old = {'cast_refs': {'SpongeBob': 'a.png'}}
    assert cast_design.signature(old) == cast_design.digest(sorted(old['cast_refs'].items()))       # approvals from before stay valid
    assert cast_design.signature({**old, 'episode_refs': {'0': {}}}) == cast_design.signature(old)
