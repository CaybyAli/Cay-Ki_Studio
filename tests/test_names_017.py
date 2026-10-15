"""Image and motion text may only name figures that are in the shot.

Sentences from the independent review rounds (German and English planner text).
Hard rule: no off-screen figure survives. Then: the visible figure keeps its own
action, and the off-screen figure's action is not handed to it."""
import itertools
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cay_studio_app'))
import screenplay as sp  # noqa: E402
from cast_design import strip_names  # noqa: E402

SB = ['SpongeBob', 'Patrick Star', 'Sandy', 'Mr. Krabs', 'Plankton', 'Thaddäus']
PF = ['Phineas', 'Ferb', 'Candace', 'Dr. Doofenshmirtz', 'Perry']
PP = ['Captain Hook', 'Captain Smee', 'Peter Pan']
TIM = ['Tim', 'Tims Oma', 'Tims Mama', 'Lena']
SIMP = ['Bart Simpson', 'Lisa Simpson', 'Homer Simpson', 'Marge']

CASES = [
    # off-screen co-subject leaves the list, the visible figure keeps the action
    (PF, ['Ferb'], 'Phineas und Ferb bauen eine Achterbahn im Garten.', 'Ferb bauen eine Achterbahn im Garten.'),
    (SB, ['SpongeBob'], 'Patrick and SpongeBob argue loudly at the counter of the Krusty Krab', 'SpongeBob argue loudly at the counter of the Krusty Krab'),
    (PF, ['Phineas', 'Candace'], 'Phineas, Ferb and Candace stare at the empty backyard', 'Phineas and Candace stare at the empty backyard'),
    (SIMP, ['Lisa Simpson', 'Marge'], 'Homer und Marge sitzen auf dem Sofa, Bart und Lisa auf dem Boden.', 'Marge sitzen auf dem Sofa, Lisa auf dem Boden.'),
    (TIM, ['Tim'], 'Tim und Oma backen Kekse.', 'Tim backen Kekse.'),
    # off-screen subject: its clause goes
    (SB, ['SpongeBob'], 'Mr. Krabs grabs SpongeBob by the collar and shakes him', ''),
    (PP, ['Captain Smee'], 'Captain Hook yells at Captain Smee.', ''),
    (SB, ['SpongeBob'], 'SpongeBob laughs and Patrick scratches his head in confusion', 'SpongeBob laughs'),
    (SB, ['SpongeBob'], 'SpongeBob lacht und Patrick weint.', 'SpongeBob lacht'),
    (SIMP, ['Homer Simpson'], 'Homer reaches for a donut and Marge slaps his hand', 'Homer reaches for a donut'),
    (SB, ['SpongeBob'], 'SpongeBob gasps as Plankton steals the formula', 'SpongeBob gasps'),
    (SB, ['SpongeBob'], 'SpongeBob freezes when Mr. Krabs walks in', 'SpongeBob freezes'),
    (SB, ['SpongeBob'], 'Als Plankton kommt, versteckt sich SpongeBob.', 'versteckt sich SpongeBob.'),
    (SB, ['SpongeBob', 'Plankton'], 'Als Plankton kommt, versteckt sich SpongeBob.', 'Als Plankton kommt, versteckt sich SpongeBob.'),
    # after a preposition or as a possessive the off-screen name is no subject
    (SB, ['SpongeBob'], 'Hinter Thaddäus schleicht SpongeBob auf Zehenspitzen vorbei.', 'schleicht SpongeBob auf Zehenspitzen vorbei.'),
    (SB, ['SpongeBob'], "Plankton's robot chases SpongeBob through the dining room", 'robot chases SpongeBob through the dining room'),
    (SB, ['SpongeBob'], "SpongeBob sneaks into Mr. Krabs' office, holding a flashlight", 'SpongeBob sneaks into office, holding a flashlight'),
    (SB, ['SpongeBob'], 'SpongeBob is grabbed by Mr. Krabs and pulled into the office', 'SpongeBob is grabbed and pulled into the office'),
    (SB, ['SpongeBob'], "SpongeBob juggles a spatula and Patrick's rock", 'SpongeBob juggles a spatula and rock'),
    (SB, ['SpongeBob'], 'SpongeBob gibt Patrick und Sandy je einen Burger.', 'SpongeBob gibt je einen Burger.'),
    (PF, ['Candace'], 'Candace yells at Phineas and Ferb from the porch', 'Candace yells from the porch'),
    # relative clauses follow the figure named before them
    (SB, ['Sandy'], 'SpongeBob looks at Sandy, who is smiling inside her air helmet', 'Sandy is smiling inside her air helmet'),
    (PP, ['Peter Pan'], 'Hook swings his sword at Peter Pan, who dodges', 'Peter Pan dodges'),
    (PP, ['Captain Smee'], 'Hook swings his sword at Peter Pan, who dodges', ''),
    (SB, ['SpongeBob'], 'SpongeBob zeigt auf Patrick, der auf einem Stein schläft.', 'SpongeBob zeigt'),
    # nothing removed, nothing changed (German verb particles stay)
    (SB, ['SpongeBob'], 'SpongeBob macht die Tür zu.', 'SpongeBob macht die Tür zu.'),
    (SB, ['SpongeBob'], 'SpongeBob hört gespannt zu, die Augen weit offen.', 'SpongeBob hört gespannt zu, die Augen weit offen.'),
    (SB, ['SpongeBob'], 'SpongeBob runs as fast as he can', 'SpongeBob runs as fast as he can'),
    (SB, ['SpongeBob'], 'SpongeBob stands on the sandy seabed, holding a spatula', 'SpongeBob stands on the sandy seabed, holding a spatula'),
    (SB, ['SpongeBob'], 'SpongeBob winkt Herrn Krabs zu.', 'SpongeBob winkt zu.'),
    # a dropped sentence keeps the sentence boundary
    (SB, ['SpongeBob'], 'SpongeBob stands at the grill, Thaddäus rolls his eyes... Warm kitchen light.', 'SpongeBob stands at the grill. Warm kitchen light.'),
    # short last word of a longer name ('Oma' for 'Tims Oma')
    (TIM, ['Tim'], 'Oma holt den Kuchen aus dem Ofen, Tim schaut hungrig zu.', 'Tim schaut hungrig zu.'),
    (['Frau Müller', 'Herr Müller'], ['Frau Müller'], 'Frau Müller schimpft mit Herrn Müller', 'Frau Müller schimpft'),
    # review round 4
    (SB, ['SpongeBob'], 'SpongeBob giggles while Patrick poses as a pirate with an eye patch', 'SpongeBob giggles'),
    (SB, ['SpongeBob'], 'SpongeBob flips a patty while Patrick dances behind him, waving his arms', 'SpongeBob flips a patty'),
    (SB, ['SpongeBob'], 'SpongeBob dresses as a pirate for Patrick.', 'SpongeBob dresses as a pirate.'),
    (['Tom', 'Jerry', 'Spike'], ['Jerry'], 'Jerry steals the cheese but Tom catches him by the tail', 'Jerry steals the cheese'),
    (['Tom', 'Jerry', 'Spike'], ['Tom'], 'Jerry steals the cheese but Tom catches him by the tail', 'Tom catches him by the tail'),
    (['Tom', 'Jerry', 'Spike'], ['Tom'], 'Tom creeps closer to the matchbox where Jerry sleeps', 'Tom creeps closer to the matchbox'),
    (SB, ['SpongeBob'], 'SpongeBob öffnet die Tür und dann rennt Patrick herein.', 'SpongeBob öffnet die Tür'),
    (['Mario', 'Princess Peach', 'Toad'], ['Mario', 'Princess Peach'], 'Peach umarmt Mario und Toad jubelt.', 'Peach umarmt Mario'),
    (['Mario', 'Princess Peach', 'Toad'], ['Toad'], 'Peach umarmt Mario und Toad jubelt.', 'Toad jubelt.'),
    (SB, ['SpongeBob'], 'Hinter SpongeBob schleicht Plankton zum Tresor.', ''),
    (SB, ['SpongeBob'], 'Mr. Krabs, rot vor Wut, packt SpongeBob am Kragen.', ''),
    (SB, ['Mr. Krabs'], 'Mr. Krabs, rot vor Wut, packt SpongeBob am Kragen.', 'Mr. Krabs, rot vor Wut, packt am Kragen.'),
    (SB, ['SpongeBob'], 'SpongeBob stands at the grill. Patrick bursts in. He grabs the spatula.', 'SpongeBob stands at the grill.'),
    (TIM, ['Lena'], 'Lena sits on the swing. She waves at Tim and laughs.', 'Lena sits on the swing. She waves and laughs.'),
    (['Chase', 'Marshall', 'Ryder'], ['Chase'], 'Chase springt zu Ryder, den roten Ball im Maul.', 'Chase springt, den roten Ball im Maul.'),
    (SB, ['SpongeBob', 'Sandy'], 'SpongeBob hugs Sandy, Patrick and Plankton cry.', 'SpongeBob hugs Sandy'),
    (SB, ['SpongeBob'], 'SpongeBob grins and Mr Krabs counts money.', 'SpongeBob grins'),
    (SB, ['SpongeBob'], 'SpongeBob grins at Sandy and Patrick waves', 'SpongeBob grins'),
    (SB, ['SpongeBob'], 'SpongeBob schaut erschrocken zu, wie Plankton die Formel stiehlt.', 'SpongeBob schaut erschrocken zu'),
    (SB, ['SpongeBob'], 'Als Plankton kommt, versteckt sich SpongeBob.', 'versteckt sich SpongeBob.'),
    (PF, ['Dr. Doofenshmirtz'], 'Dr. Doofenshmirtz shakes his fist at Perry the Platypus', 'Dr. Doofenshmirtz shakes his fist'),
    # other spellings of a name
    (SB, ['SpongeBob'], 'SpongeBob dances while Thaddaeus plays the clarinet', 'SpongeBob dances'),
    (['Mario', 'Bowser', 'Bowser Jr.'], ['Bowser Jr.'], 'Bowser Jr laughs and sticks out his tongue at the camera', 'Bowser Jr laughs and sticks out his tongue at the camera'),
    (['Mario', 'Bowser', 'Bowser Jr.'], ['Bowser'], 'Bowser Jr laughs and sticks out his tongue at the camera', ''),
    (['Peter Pan', 'Tinker Bell'], ['Peter Pan'], 'Peter Pan laughs as Tinkerbell glows next to him', 'Peter Pan laughs'),
    (TIM + ['Papa'], ['Tim'], "Tim's grandma knits a scarf by the fireplace", ''),
    (['Kim Possible', 'Ron Stoppable'], ['Kim Possible'], 'Kim and Ron run to the car.', 'Kim run to the car.'),
]


@pytest.mark.parametrize('cast,visible,text,expected', CASES, ids=[c[2][:40] for c in CASES])
def test_sanitize_keeps_only_visible_figures(cast, visible, text, expected):
    assert sp.sanitize(text, visible, cast) == expected


def test_no_off_screen_figure_survives_any_visible_subset():
    for cast, _, text, _ in CASES:
        for k in (1, 2):
            for visible in itertools.combinations(cast, k):
                hidden = [c for c in cast if c not in visible]
                out = sp.sanitize(text, list(visible), cast)
                assert not sp._mentions(out, hidden, list(visible)), (text, visible, out)


def test_aktion_visibility_with_short_and_shared_names():
    for cast, line, seen in [(TIM, 'AKTION: Oma stellt den Kuchen wütend auf den Tisch.', ['Tims Oma']),
                             (TIM, 'AKTION: Tims Mama backt Kekse.', ['Tims Mama']),
                             (PP, 'AKTION: Captain Hook zieht sein Schwert.', ['Captain Hook'])]:
        title, beats, lines, _ = sp.parse('# 1 | Küche | x\n' + line, cast)
        assert sp.shots(title, beats, lines, cast)[0]['visible'] == seen


def test_strip_names_in_appearance_texts():
    assert strip_names("Wears a hat and Opa's old scarf", ['Opa'], ['Tim']) == 'Wears a hat and old scarf'
    assert 'Oma' not in strip_names('A boy in a red scarf knitted by Tims Oma', ['Tims Oma'], ['Tim'])


def test_original_names_are_aliases():
    cast = [{'name': 'SpongeBob'}, {'name': 'Thaddäus', 'original': 'Squidward Tentacles from the animated series SpongeBob SquarePants'}]
    aliases = sp.figure_aliases(cast)
    assert aliases == {'Thaddäus': ['Squidward Tentacles']}
    assert sp.sanitize('SpongeBob waves at Squidward through the kitchen window', ['SpongeBob'], ['SpongeBob', 'Thaddäus'], aliases) == 'SpongeBob waves through the kitchen window'
    assert sp.offscreen_names('Squidward rolls his eyes', ['SpongeBob'], ['SpongeBob', 'Thaddäus'], aliases) == ['Thaddäus']


def test_visuals_naming_offscreen_figures_are_written_again():
    import asyncio
    cut = [{'visible': ['SpongeBob'], 'lines': [], 'kind': 'action', 'place': 'Kitchen', 'what': 'x', 'beat': 0},
           {'visible': ['Thaddäus'], 'lines': [], 'kind': 'action', 'place': 'Kitchen', 'what': 'x', 'beat': 0}]
    d = {'plan': {'style': 'clay', 'cast': [{'name': 'SpongeBob'}, {'name': 'Thaddäus', 'original': 'Squidward Tentacles from the series'}]}}
    first = {'shots': [{'shot': 1, 'still': 'SpongeBob grins at Squidward', 'motion': 'waves', 'camera': 'medium', 'ambience': 'room'},
                       {'shot': 2, 'still': 'Thaddäus plays the clarinet', 'motion': 'sways', 'camera': 'medium', 'ambience': 'room'}]}

    class Planner:
        calls = []
        async def llm(self, schema, instruction, data):
            Planner.calls.append([x['shot'] for x in data['shots']])
            return {'shots': [{'shot': 1, 'still': 'SpongeBob grins at the grill, alone', 'motion': 'waves', 'camera': 'medium', 'ambience': 'room'}]}

    listing = [{'shot': i + 1, 'visible': s['visible']} for i, s in enumerate(cut)]
    fixed = asyncio.run(sp.repair_visuals(Planner(), d, cut, listing, first))
    assert Planner.calls == [[1]]                                     # only the wrong shot is asked again
    assert fixed['shots'][0]['still'] == 'SpongeBob grins at the grill, alone' and fixed['shots'][1] == first['shots'][1]
