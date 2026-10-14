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
    prompt = cast_design.identity_prompt(SPONGE, 'Handmade claymation look.')
    assert 'SpongeBob SquarePants from the animated series' in prompt
    assert 'not a look-alike' in prompt
    assert 'One original character design' not in prompt
    assert 'well-known' not in cast_design.identity_prompt(INVENTED, 'clay')


def test_figure_design_never_sees_templates_and_style_pass_keeps_identity():
    factory = FakeFactory()
    document = {'plan': {'style': 'Handmade claymation look.'}}
    out = asyncio.run(cast_design.design(factory, document, SPONGE, ['tpl/a.png', 'tpl/b.png'], {}))
    identity, styled = factory.calls
    assert identity['refs'] == []                       # pass 1: text only, no template people
    assert styled['refs'][0] == 'staged/' + Path(identity['key'] + '.png').name
    assert styled['refs'][1:] == ['tpl/a.png', 'tpl/b.png']
    assert 'Take no person, character, face' in styled['prompt']
    assert out == styled['key'].join(['/out/', '.png'])


def test_without_templates_only_one_image_prompt():
    factory = FakeFactory()
    asyncio.run(cast_design.design(factory, {'plan': {'style': 'clay'}}, INVENTED, [], {}))
    assert len(factory.calls) == 1 and factory.calls[0]['refs'] == []


def test_scene_images_get_only_the_figures_of_that_scene():
    refs = {'SpongeBob': '/a/sponge.png', 'Mr. Krabs': '/a/krabs.png'}
    assert cast_design.scene_references(refs, ['SpongeBob']) == ['/a/sponge.png']
    assert cast_design.scene_references(refs, []) == []
    prompt = cast_design.scene_prompt({}, [SPONGE, KRABS], ['SpongeBob', 'Mr. Krabs'], 'clay')
    assert 'Reference image 1 is the approved design of SpongeBob (SpongeBob SquarePants' in prompt
    assert 'Reference image 2 is the approved design of Mr. Krabs' in prompt
    assert 'style examples' not in prompt
    assert 'No characters' in cast_design.scene_prompt({}, [SPONGE], [], 'clay')


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


def test_lively_motion_direction():
    text = motion_direction({}, [{'speaker': 'SpongeBob', 'offset': 0, 'duration': 2}], 0, 3)
    assert 'restrained' not in text and 'never slow motion' in text and 'gesturing' in text


def test_split_shots_keep_the_planned_movement():
    scene = {'title': 'Streit', 'action': 'Beide streiten.', 'location': 'Krosse Krabbe', 'camera': 'Halbtotale',
             'cast': ['SpongeBob', 'Mr. Krabs'], 'dialogue': '', 'speaker': '', 'emotion': 'x', 'continuity': 'x',
             'dialogues': [{'speaker': 'SpongeBob', 'text': 'Nein!'}, {'speaker': 'Mr. Krabs', 'text': 'Doch!'}],
             'animation_prompt': 'SpongeBob slams the spatula on the grill', 'sound_cues': []}
    shots = split_scene(scene)
    assert len(shots) == 2
    assert all('slams the spatula' in s['animation_prompt'] for s in shots)
    assert shots[0]['animation_prompt'].split(' of ')[0] != shots[1]['animation_prompt'].split(' of ')[0]


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
    assert len(casts) == 4 and len(scenes) == 6 and d['state'] == 'image_review'
    assert all(template not in c['refs'] for c in scenes)
    assert [len(c['refs']) for c in scenes] == [1, 1, 2, 2, 0, 0]
    assert scenes[0]['refs'] == ['staged/' + Path(d['cast_refs']['SpongeBob']).name]
