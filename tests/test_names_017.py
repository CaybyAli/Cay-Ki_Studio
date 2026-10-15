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
