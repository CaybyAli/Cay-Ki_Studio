"""0.16: look templates stay style, figures keep one face, films keep moving.

Cay's report on 0.15: people from the template appeared in the film,
SpongeBob changed his face three or four times, nobody moved, it felt like
slow motion and the planner had no idea of the film's goal. These tests pin
the code paths behind each point. They cannot prove how a real image or
animation looks; that needs a render on Cay's PC.
"""
import asyncio
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path.insert(0, str(APP))

import cast_design  # noqa: E402
from factory_timing import audio_layout, fill_target, talk_window_seconds, talk_windows  # noqa: E402
from lipsync_shots import split_scene  # noqa: E402
from story_policy import StorySpine, DIRECTION  # noqa: E402
from studio_quality_policy import motion_direction  # noqa: E402

SPONGE = {'name': 'SpongeBob', 'original': 'SpongeBob SquarePants from the animated series SpongeBob SquarePants',
          'appearance': 'yellow rectangular sea sponge, big blue eyes, two buck teeth, white shirt, red tie, brown square pants',
          'personality': 'fröhlich'}
KRABS = {'name': 'Mr. Krabs', 'original': 'Mr. Krabs from the animated series SpongeBob SquarePants',
         'appearance': 'red crab, eyes on long stalks, blue shirt', 'personality': 'geizig'}
INVENTED = {'name': 'Keksi', 'appearance': 'round cookie with chocolate chips', 'personality': 'frech'}


class FakeFactory:
    """Records image prompts instead of calling ComfyUI."""
    def __init__(self):
        self.calls = []

    async def render(self, document, key, graph, video=False):
        refs = [n['inputs']['image'] for n in graph.values() if n['class_type'] == 'LoadImage']
        prompt = next(n['inputs']['text'] for n in graph.values() if n['class_type'] == 'CLIPTextEncode')
        self.calls.append({'key': key, 'refs': refs, 'prompt': prompt})
        return {'id': key, 'output': f'/out/{key}.png'}

    def stage(self, path):
        return 'staged/' + Path(path).name


def test_known_character_is_designed_as_the_original_not_an_original_design():
    prompt = cast_design.identity_prompt(SPONGE, 'Handmade claymation look.', ['SpongeBob', 'Mr. Krabs'])
    assert 'SpongeBob SquarePants from the animated series' in prompt
    assert 'not a look-alike' in prompt
    assert 'One original character design' not in prompt
    assert 'well-known' not in cast_design.identity_prompt(INVENTED, 'clay')


def test_other_figures_never_named_in_a_design():
    """0.16.1: 'Mr. Krabs from the animated series SpongeBob SquarePants' put SpongeBob into
    every Krabs design; Plankton came out as a green SpongeBob."""
    names = ['SpongeBob', 'Mr. Krabs', 'Plankton']
    krabs = cast_design.identity_prompt(KRABS, 'Claymation in the world of SpongeBob, warm light.', names)
    assert 'SpongeBob' not in krabs and 'Character sheet of Mr. Krabs.' in krabs
    assert 'neutral standing pose' not in krabs and 'natural body shape' in krabs


def test_known_originals_skip_the_template_style_pass():
    factory = FakeFactory()
    document = {'plan': {'style': 'Handmade claymation look.', 'cast': [SPONGE, INVENTED]}}
    asyncio.run(cast_design.design(factory, document, SPONGE, ['tpl/a.png', 'tpl/b.png'], {}))
    assert len(factory.calls) == 1 and factory.calls[0]['refs'] == []


def test_invented_figure_style_pass_keeps_identity():
    factory = FakeFactory()
    document = {'plan': {'style': 'Handmade claymation look.', 'cast': [SPONGE, INVENTED]}}
    out = asyncio.run(cast_design.design(factory, document, INVENTED, ['tpl/a.png', 'tpl/b.png'], {}))
    identity, styled = factory.calls
    assert identity['refs'] == []                       # pass 1: text only, no template people
    assert styled['refs'][0] == 'staged/' + Path(identity['key'] + '.png').name
    assert styled['refs'][1:] == ['tpl/a.png', 'tpl/b.png']
    assert 'Take no person, character, face' in styled['prompt']
    assert out == styled['key'].join(['/out/', '.png'])


def test_without_templates_only_one_image_prompt():
    factory = FakeFactory()
    asyncio.run(cast_design.design(factory, {'plan': {'style': 'clay', 'cast': [INVENTED]}}, INVENTED, [], {}))
    assert len(factory.calls) == 1 and factory.calls[0]['refs'] == []


def test_scene_images_get_only_the_figures_of_that_scene():
    refs = {'SpongeBob': '/a/sponge.png', 'Mr. Krabs': '/a/krabs.png'}
    assert cast_design.scene_references(refs, ['SpongeBob']) == ['/a/sponge.png']
    assert cast_design.scene_references(refs, []) == []
    two = cast_design.scene_prompt({}, [SPONGE, KRABS], ['SpongeBob', 'Mr. Krabs'], 'clay')
    assert 'Reference image 1 is the approved design of SpongeBob:' in two
    assert 'Reference image 2 is the approved design of Mr. Krabs:' in two
    assert 'Only SpongeBob and Mr. Krabs are in the picture' in two and 'style examples' not in two
    one = cast_design.scene_prompt({}, [SPONGE, KRABS], ['Mr. Krabs'], 'Claymation SpongeBob world')
    assert 'SpongeBob' not in one and 'Medium shot of Mr. Krabs alone.' in one
    assert 'No characters' not in one and 'Only the location' in cast_design.scene_prompt({}, [SPONGE], [], 'clay')


def test_scene_text_only_describes_visible_figures():
    scene = {'cast': ['Mr. Krabs'], 'action': 'SpongeBob zählt Schutzgeld, Mr. Krabs droht ihm, Plankton lauert.',
             'location': 'Höhle', 'camera': 'Einzeleinstellung auf Mr. Krabs, SpongeBob außerhalb.'}
    text = cast_design.scene_text(scene, [SPONGE, KRABS, {'name': 'Plankton', 'appearance': 'x'}])
    assert 'SpongeBob' not in text and 'Plankton' not in text and 'Mr. Krabs droht ihm' in text
    still = {**scene, 'still': 'Mr. Krabs slams his claw on the table, SpongeBob trembling behind him'}
    assert cast_design.scene_text(still, [SPONGE, KRABS]).startswith('Scene: Mr. Krabs slams his claw on the table.')


def test_redesign_round_gives_new_cache_key_and_seed():
    a = cast_design.keys(SPONGE, [])
    b = cast_design.keys({**SPONGE, 'design_round': 1}, [])
    assert a[0] != b[0] and a[1] != b[1]
    assert cast_design.seed('SpongeBob', 0) != cast_design.seed('SpongeBob', 1)
    assert cast_design.keys(SPONGE, ['x.png'])[1] != cast_design.keys(SPONGE, ['y.png'])[1]


def test_changed_figure_redoes_every_scene_with_it():
    def sc(cast):
        return {'cast': cast, 'variants': [{'id': 'v1', 'key': 'image:0:0:0:0'}, {'id': 'v2', 'key': 'image:0:0:0:1'}], 'selected': 'v1'}
    document = {'cast_refs': {'SpongeBob': '/x.png', 'Mr. Krabs': '/y.png'},
                'episodes': [{'scenes': [sc(['SpongeBob']), sc(['Mr. Krabs']), sc(['SpongeBob', 'Mr. Krabs'])]}]}
    assert cast_design.invalidate(document, 'SpongeBob') == 2
    scenes = document['episodes'][0]['scenes']
    assert 'SpongeBob' not in document['cast_refs'] and 'Mr. Krabs' in document['cast_refs']
    assert scenes[0]['image_rounds'] == [1, 1] and scenes[0]['selected'] is None
    assert 'image_rounds' not in scenes[1] and scenes[1]['selected'] == 'v1'
    assert scenes[2]['image_rounds'] == [1, 1]


def test_lip_sync_window_capacity_matches_audio_graph_frames():
    assert talk_windows(3.2) == 1 and talk_windows(3.21) == 2
    assert talk_window_seconds(1.8) == 3.2 and talk_window_seconds(4) == 6.08


def test_extra_time_goes_to_action_not_to_new_windows():
    base = [2.0, 3.5, 2.5]
    times = fill_target(base, [True, True, False], 12, [1, 2, 4])
    assert sum(times) == pytest.approx(12)
    assert [talk_windows(t) for t in times[:2]] == [talk_windows(b) for b in base[:2]]
    assert times[2] > base[2]                           # the silent action scene absorbs the rest


def line(scene, duration, turn=0, speaker='SpongeBob'):
    return {'episode': 0, 'scene': scene, 'turn': turn, 'duration': duration, 'pause_after': .18, 'speaker': speaker}


def test_speech_starts_on_the_cut_and_minimum_is_met():
    episode = {'dialogue_mode': 'rich', 'minimum_seconds': 15,
               'scenes': [{'seconds': 4}, {'seconds': 4}, {'seconds': 4}]}
    lines = [line(0, 2.0), line(1, 2.4, speaker='Mr. Krabs')]
    report = audio_layout([episode], lines, 15, 25)[0]
    assert report['minimum_met'] and report['seconds'] >= 15
    assert all(l['offset'] == pytest.approx(.08) for l in lines)       # was centred after spare/2 silence
    assert episode['scenes'][2]['render_seconds'] > 2.5                 # silent action shot fills the target
    assert report['talk_windows'] == 2


def test_motion_direction_moves_only_while_speaking():
    """0.16.1: 'keep moving the whole time' + 3 s silence = mouths and hands moving without a voice."""
    text = motion_direction({'cast': ['SpongeBob']}, [{'speaker': 'SpongeBob', 'offset': 0, 'duration': 2}], 0, 3)
    assert 'whole time' not in text and 'never slow motion' in text
    assert 'mouth stays closed' in text and 'Exactly one character in the whole frame: SpongeBob' in text
    silent = motion_direction({'cast': ['Patrick', 'Plankton']}, [], 0, 3)
    assert 'nobody talks' in silent and 'Only Patrick and Plankton in the frame' in silent


def test_split_shots_name_only_the_visible_speaker():
    scene = {'title': 'Streit', 'action': 'Beide streiten.', 'location': 'Krosse Krabbe', 'camera': 'Halbtotale',
             'cast': ['SpongeBob', 'Mr. Krabs'], 'dialogue': '', 'speaker': '', 'emotion': 'x', 'continuity': 'x',
             'dialogues': [{'speaker': 'SpongeBob', 'text': 'Nein!'}, {'speaker': 'Mr. Krabs', 'text': 'Doch!'}],
             'animation_prompt': 'SpongeBob slams the spatula on the grill', 'sound_cues': []}
    shots = split_scene(scene)
    assert len(shots) == 2
    assert 'slams the spatula' in shots[0]['animation_prompt']
    assert 'SpongeBob' not in shots[1]['animation_prompt'] and 'SpongeBob' not in shots[1]['still']
    assert 'außerhalb' not in shots[0]['camera'] or 'Mr. Krabs' not in shots[0]['camera']


def test_story_spine_is_complete_and_direction_demands_motion():
    spine = StorySpine.model_validate({'logline': 'SpongeBob will die Formel retten, bevor Plankton sie klaut.',
        'viewer_question': 'Wer hat die Formel?', 'hook': 'Der Tresor steht offen.', 'goal': 'Formel finden',
        'stakes': 'Krosse Krabbe schließt', 'escalations': ['Plankton im Rohr', 'Mr. Krabs verdächtigt SpongeBob'],
        'twist': 'Gary hat sie gefressen', 'payoff': 'Formel zurück', 'final_moment': 'Gary rülpst'})
    assert spine.running_gag == ''
    with pytest.raises(Exception):
        StorySpine.model_validate({**spine.model_dump(), 'escalations': ['nur eine']})
    assert 'Niemand steht nur da und redet' in DIRECTION and 'spine' in DIRECTION


def test_render_order_groups_lip_sync_before_motion():
    pytest.importorskip('fastapi')
    from factory import render_order
    scenes = ['a', 'b', 'c', 'd']
    lines = [{'episode': 0, 'scene': 1}, {'episode': 0, 'scene': 3}, {'episode': 1, 'scene': 0}]
    assert [i for i, _ in render_order(scenes, 0, lines)] == [1, 3, 0, 2]
    assert [i for i, _ in render_order(scenes, 0, lines, 'off')] == [0, 1, 2, 3]


def test_pictures_step_end_to_end_without_templates_in_scenes():
    """Factory.pictures with ComfyUI replaced: which references each image prompt gets."""
    pytest.importorskip('fastapi')
    import factory

    class Fake(FakeFactory):
        def __init__(self):
            super().__init__(); self.saved = 0
        async def object_info(self): return {}
        def asset(self, aid, kind=None): return {'path': f'/assets/{aid}.png'}
        def save(self, d): self.saved += 1
        def paused(self, rid): return False
        def apply_pending(self, d): return False

    original = factory.validate_nodes
    factory.validate_nodes = lambda info: {}
    try:
        fake = Fake()
        sc = lambda cast: {'title': 't', 'location': 'l', 'action': 'a', 'camera': 'c', 'continuity': 'x', 'cast': cast, 'variants': []}
        d = {'id': 'r1', 'idea': {'participants': [], 'examples': ['e' * 32]},
             'plan': {'style': 'clay', 'cast': [SPONGE, KRABS]},
             'episodes': [{'scenes': [sc(['SpongeBob']), sc(['SpongeBob', 'Mr. Krabs']), sc([])]}]}
        asyncio.run(factory.Factory.pictures(fake, d))
    finally:
        factory.validate_nodes = original
    template = 'staged/' + 'e' * 32 + '.png'
    casts = [c for c in fake.calls if c['key'].startswith('cast')]
    scenes = [c for c in fake.calls if c['key'].startswith('image:')]
    # Known originals: identity pass only (no template style pass).
    assert len(casts) == 2 and len(scenes) == 6 and d['state'] == 'image_review'
    assert all(template not in c['refs'] for c in scenes)
    assert [len(c['refs']) for c in scenes] == [1, 1, 2, 2, 0, 0]
    assert scenes[0]['refs'] == ['staged/' + Path(d['cast_refs']['SpongeBob']).name]


def test_cast_check_stops_once_before_scene_images():
    pytest.importorskip('fastapi')
    import factory

    class Fake(FakeFactory):
        async def object_info(self): return {}
        def asset(self, aid, kind=None): return {'path': f'/assets/{aid}.png'}
        def save(self, d): pass
        def paused(self, rid): return False
        def apply_pending(self, d): return False

    original = factory.validate_nodes
    factory.validate_nodes = lambda info: {}
    try:
        fake = Fake()
        d = {'id': 'r2', 'idea': {'participants': [], 'examples': [], 'cast_check': True},
             'plan': {'style': 'clay', 'cast': [SPONGE, KRABS]},
             'episodes': [{'scenes': [{'title': 't', 'location': 'l', 'action': 'a', 'camera': 'c', 'continuity': 'x', 'cast': ['SpongeBob'], 'variants': []}]}]}
        asyncio.run(factory.Factory.pictures(fake, d))
        assert d['state'] == 'cast_review' and not [c for c in fake.calls if c['key'].startswith('image:')]
        d['cast_approval'] = cast_design.signature(d); d['state'] = 'pictures'
        asyncio.run(factory.Factory.pictures(fake, d))
        assert d['state'] == 'image_review' and len([c for c in fake.calls if c['key'].startswith('image:')]) == 2
        assert cast_design.invalidate(d, 'SpongeBob') == 1 and cast_design.needs_review(d)
    finally:
        factory.validate_nodes = original


def test_design_never_names_other_figures_in_appearance():
    plankton = {'name': 'Plankton', 'original': 'Plankton', 'appearance': 'tiny green copepod with one red eye, smaller than SpongeBob'}
    prompt = cast_design.identity_prompt(plankton, 'clay', ['SpongeBob', 'Plankton'])
    assert 'SpongeBob' not in prompt and 'one red eye' in prompt
