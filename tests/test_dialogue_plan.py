"""A film in which people should talk must never become silent by accident.

The LLM is replaced by fixed answers: this proves the planning rules and the
data flow, not the quality of a real Ollama plan.
"""
import asyncio
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path.insert(0, str(APP))

from dialogue_density import enrich  # noqa: E402
from factory_timing import plan_seconds, scene_lines  # noqa: E402
from lipsync_shots import split_episode, silent_by_accident, spoken_words  # noqa: E402
from story_policy import dialogue_errors  # noqa: E402

CAST = [{'name': 'Max', 'appearance': 'boy, red jacket', 'personality': 'mutig'},
        {'name': 'Lina', 'appearance': 'girl, yellow coat', 'personality': 'klug'}]


def scene(title, cast, lines=(), cues=()):
    return {'title': title, 'action': 'Max und Lina stehen vor der verschlossenen Tür.', 'location': 'Flur',
            'camera': 'Halbtotale', 'cast': list(cast), 'dialogue': '', 'speaker': '', 'emotion': 'Natürlich',
            'continuity': 'gleiches Licht', 'beat': 'problem', 'because': 'Start',
            'dialogues': [{'speaker': s, 'text': t, 'emotion': 'Natürlich', 'pause_after': .18} for s, t in lines],
            'ambience': 'room', 'sound_cues': list(cues), 'motion': ['walk'], 'animation_prompt': 'both walk'}


def fifteen_seconds_two_people():
    """Typical 15 s plan: 3 scenes, both characters visible, no dialogue."""
    return {'title': 'Die Tür', 'goal': 'raus', 'obstacle': 'Tür zu', 'resolution': 'Schlüssel',
            'scenes': [scene('Tür', ['Max', 'Lina']), scene('Suche', ['Max', 'Lina']), scene('Schlüssel', ['Max', 'Lina'])]}


def test_two_visible_speakers_become_shot_reverse_shot():
    cue = {'kind': 'door', 'position': .5, 'reason': 'Tür knallt'}
    episode = {'scenes': [scene('Streit', ['Max', 'Lina'], [('Max', 'Wer hat abgeschlossen?'), ('Lina', 'Nicht ich!'),
                                                             ('Max', 'Dann such den Schlüssel.')], [cue])]}
    shots = split_episode(episode)['scenes']
    assert [s['cast'] for s in shots] == [['Max'], ['Lina'], ['Max']]
    assert [line['text'] for s in shots for line in scene_lines(s)] == ['Wer hat abgeschlossen?', 'Nicht ich!', 'Dann such den Schlüssel.']
    assert shots[0]['sound_cues'] == [cue] and shots[1]['sound_cues'] == [] and shots[2]['shot_part'] == [3, 3]
    assert dialogue_errors({'scenes': shots}) == []           # the render check in movies() passes


def test_valid_and_silent_scenes_stay_unchanged():
    episode = {'scenes': [scene('Allein', ['Max'], [('Max', 'Hallo?')]), scene('Stille', ['Max', 'Lina'])]}
    assert split_episode(episode)['scenes'] == episode['scenes']
    one_speaker = {'scenes': [scene('Zuhören', ['Max', 'Lina'], [('Lina', 'Hör mir zu.')])]}
    assert split_episode(one_speaker)['scenes'][0]['cast'] == ['Lina']


def test_split_refuses_after_pictures_and_beyond_limit():
    pictured = {'scenes': [{**scene('A', ['Max', 'Lina'], [('Max', 'Ja'), ('Lina', 'Nein')]), 'selected': 'x'}]}
    with pytest.raises(ValueError, match='fertigen Bildern'): split_episode(pictured)
    crowded = {'scenes': [scene(str(i), ['Max', 'Lina'], [('Max', 'a'), ('Lina', 'b'), ('Max', 'c'), ('Lina', 'd')]) for i in range(8)]}
    with pytest.raises(ValueError, match='höchstens 30'): split_episode(crowded)


class FakePlanner:
    """Answers like a planner that writes natural dialogue between two visible people."""
    def __init__(self, answer): self.answer = answer
    async def llm(self, schema, instruction, data): return self.answer


def test_dialogue_extension_keeps_lines_for_two_visible_people():
    # 0.13.1 discarded this whole answer ("nur einen sichtbaren Sprecher"): the film stayed silent.
    answer = {'scenes': [{'scene': 1, 'lines': [{'speaker': 'Max', 'text': 'Die Tür ist zu, wir kommen nicht raus.', 'emotion': 'ängstlich', 'pause_after': .2},
                                                 {'speaker': 'Lina', 'text': 'Dann suchen wir den Schlüssel, sofort.', 'emotion': 'bestimmt', 'pause_after': .2}]},
                         {'scene': 3, 'lines': [{'speaker': 'Lina', 'text': 'Hier ist er, unter der Matte!', 'emotion': 'begeistert', 'pause_after': .2}]}]}
    document = {'idea': {'duration': 15, 'lip_sync': 'audio', 'idea': 'Zwei Kinder sind eingesperrt', 'characters': 'invent'},
                'plan': {'cast': CAST}}
    episode = asyncio.run(enrich(FakePlanner(answer), document, fifteen_seconds_two_people(), 0))
    assert not any('nicht übernommen' in w for w in episode.get('warnings', []))
    assert spoken_words(episode) == 20 and dialogue_errors(episode) == []
    assert [s['cast'] for s in episode['scenes'] if scene_lines(s)] == [['Max'], ['Lina'], ['Lina']]
    seconds = plan_seconds(episode, 15)
    assert sum(seconds) >= 15 and len(seconds) == 4


def test_silent_film_detection_respects_intent():
    talking = {'idea': 'Zwei Kinder streiten', 'characters': 'invent'}
    assert silent_by_accident(talking, CAST, [fifteen_seconds_two_people()]) is True
    assert silent_by_accident({'idea': 'Ein Stummfilm über zwei Kinder', 'characters': 'invent'}, CAST, [fifteen_seconds_two_people()]) is False
    assert silent_by_accident({'idea': 'Nur Landschaft, rein visuell', 'characters': 'none'}, [], [fifteen_seconds_two_people()]) is False
    with_line = fifteen_seconds_two_people(); with_line['scenes'][0] = scene('Tür', ['Max'], [('Max', 'Abgeschlossen!')])
    assert silent_by_accident(talking, CAST, [with_line]) is False
