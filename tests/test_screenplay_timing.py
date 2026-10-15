"""0.17: screenplay first, enforced word budget, no silent tails in lip-sync shots.

Cay's Krusty film (0.16.1): 63 words in 60 s, telegram lines, ~3 s silence after
every line in which the lip-sync model kept moving mouths, figures in the image
that were only named in the text. The LLM is replaced by fixed answers; this
proves parsing, checks, cutting and timing, not the quality of a real plan.
"""
import asyncio
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path.insert(0, str(APP))

import screenplay as sp  # noqa: E402
from factory_timing import audio_layout, talk_plan, talk_windows, fill_target, TALK_TAIL_MAX, TAIL  # noqa: E402

CAST = ['SpongeBob', 'Mr. Krabs', 'Patrick', 'Plankton']

GOOD = '''TITEL: Der Einbruch im Krusty-Versteck
# 1 | Düstere Knete-Höhle mit Holztisch | SpongeBob zählt Schutzgeld, Mr. Krabs beugt sich drohend über ihn
SPONGEBOB [ängstlich]: Mister Krabs, es ist alles da, ich hab das Geld dreimal gezählt!
MR. KRABS [drohend]: Dreimal? Dann erklär mir mal, warum hier ein ganzer Dollar fehlt, Junge.
SPONGEBOB [panisch]: Ein Dollar? Vielleicht hat ihn ja der Wind weggeweht, Mister Krabs?
MR. KRABS [spöttisch]: Der Wind. In einer Höhle. Unter Wasser. Versuch es noch einmal.
# 2 | Höhleneingang | Patrick lauert mit einem Fischernetz
AKTION: Patrick springt mit einem riesigen Fischernetz aus dem Schatten.
PATRICK [begeistert]: Überraschung! Keiner rührt sich, das hier ist ein echter Überfall!
MR. KRABS [wütend]: Patrick! Das ist mein Versteck, nicht dein Spielplatz, raus hier!
PATRICK [verwirrt]: Ach so. Und wo genau ist dann der Spielplatz, Mister Krabs?
MR. KRABS [genervt]: Großartig. Jetzt habe ich zwei Probleme.
# 3 | Hinter dem Holztisch | Plankton klettert auf die Geldkassette
AKTION: Plankton zieht sich mit einem Seil auf die Geldkassette und grinst.
PLANKTON [triumphierend]: Während ihr drei streitet, gehört die ganze Kasse endlich mir! Hahaha!
MR. KRABS [schreiend]: Plankton! Finger weg von meinem Geld, du winziger Wurm!
PLANKTON [spöttisch]: Winzig, aber schlau. Und dein Dollar steckt übrigens in SpongeBobs Socke.
SPONGEBOB [überrascht]: In meiner Socke? Oh nein, da hab ich ihn ja versteckt!
MR. KRABS [triumphierend]: Her damit! Und ihr zwei schrubbt die Höhle!
'''


def test_good_screenplay_passes_and_is_cut_per_turn():
    title, beats, lines, problems = sp.parse(GOOD, CAST)
    assert not problems and title == 'Der Einbruch im Krusty-Versteck' and len(beats) == 3
    assert sp.check(title, beats, lines, problems, CAST, 60) == []
    cut = sp.shots(title, beats, lines, CAST)
    assert [c['kind'] for c in cut].count('action') == 2
    assert all(c['visible'] == [c['lines'][0]['speaker']] for c in cut if c['kind'] == 'line')
    assert next(c for c in cut if c['kind'] == 'action')['visible'] == ['Patrick']
    assert cut[0]['lines'][0]['emotion'] == 'ängstlich'


def test_krusty_dialogue_is_rejected_with_countable_errors():
    bad = '''# 1 | Höhle | SpongeBob am Tisch
SPONGEBOB [ängstlich]: Lass mich los!
SPONGEBOB [ängstlich]: Nicht die Hand!
MR. KRABS [drohend]: Geld. Jetzt. Sofort.
MR. KRABS [drohend]: Dein Geld. Mein Tisch.
PLANKTON [ruhig]: Dein Werkzeug. Mein Eigentum.
Erzähler: Und dann passierte es.
'''
    errors = sp.check(*sp.parse(bad, CAST), CAST, 60)
    text = ' '.join(errors)
    assert 'Zu wenig Dialog' in text and 'Telegrammstil' in text and 'Sprecherwechsel' in text
    assert 'AKTION' in text and '"Erzähler" gehört nicht zur Besetzung' in text


def test_natural_exclamations_are_not_telegram():
    assert sp.telegram('Geld. Jetzt. Sofort.') and sp.telegram('Dein Geld. Mein Tisch.')
    assert not sp.telegram('Halt! Bleib stehen!') and not sp.telegram('Der Wind. In einer Höhle. Unter Wasser.')


def test_speaker_aliases_resolve_and_unknown_never_guessed():
    title, beats, lines, problems = sp.parse('KRABS [wütend]: Raus hier, sofort!\nGARY [ruhig]: Miau.', CAST)
    assert lines[0]['speaker'] == 'Mr. Krabs' and problems and 'GARY' in problems[0]


def test_budget_scales_with_length():
    b15, b60 = sp.budget(15), sp.budget(60)
    assert b60['words'] == 120 and b60['min_words'] < 120 < b60['max_words']
    assert b15['min_actions'] == 1 and b60['min_actions'] == 2 and b15['max_turns'] < b60['max_turns']


def test_same_speaker_lines_share_a_shot_up_to_the_limit():
    text = '# 1 | Ort | x\nSPONGEBOB [fröhlich]: Hallo Patrick, schau mal hier!\nSPONGEBOB [fröhlich]: Ich hab einen Burger für dich.\nPATRICK [begeistert]: Wow, einen ganzen Burger?'
    cut = sp.shots(*sp.parse(text, CAST)[:3], CAST)
    assert len(cut) == 2 and len(cut[0]['lines']) == 2


def test_assembled_episode_is_compatible_and_image_text_clean():
    title, beats, lines, _ = sp.parse(GOOD, CAST)
    cut = sp.shots(title, beats, lines, CAST)
    visuals = {'shots': [{'shot': 1, 'still': 'SpongeBob at the wooden table counting coins, Mr. Krabs looming over him',
                          'motion': 'counts coins nervously, glances up at Mr. Krabs', 'camera': 'medium shot', 'ambience': 'room'}]}
    ep = sp.assemble(title, {'goal': 'Dollar finden', 'stakes': 'Ärger', 'payoff': 'Socke'}, {'title': 'x'}, cut, visuals,
                     [{'name': n} for n in CAST], {})
    first = ep['scenes'][0]
    assert first['still'] == 'SpongeBob at the wooden table counting coins' and 'Krabs' not in first['animation_prompt']
    assert first['cast'] == ['SpongeBob'] and first['dialogues'][0]['emotion'] == 'ängstlich'
    assert ep['story_policy'] == sp.POLICY and ep['dialogue_mode'] == 'rich' and ep['goal'] == 'Dollar finden'
    assert ep['scenes'][-1]['beat'] == 'payoff' and ep['scenes'][0]['beat'] == 'problem'
    from factory_models import Shot
    for scene in ep['scenes']: Shot.model_validate(scene)


class FakePlanner:
    """Stands in for Factory.write/llm/save: returns fixed texts, records prompts."""
    def __init__(self, texts):
        self.texts = list(texts); self.calls = []
    async def write(self, instruction, data, label='', check=None, attempts=3):
        self.calls.append(label)
        for _ in range(attempts):
            text = self.texts.pop(0)
            if not check or not check(text): return text
        return text
    async def llm(self, schema, instruction, data):
        self.calls.append(schema.__name__)
        return {'shots': [{'shot': i + 1, 'still': f'{s["visible"][0]} in the cave', 'motion': 'waves', 'camera': 'medium', 'ambience': 'room'}
                          for i, s in enumerate(data['shots'])]}
    def save(self, d): pass


def document():
    return {'idea': {'duration': 60, 'episodes': 1}, 'episodes': [],
            'plan': {'title': 'Krusty', 'style': 'clay', 'cast': [{'name': n, 'appearance': 'x'} for n in CAST], 'episodes': [{'title': 'x'}]}}


def test_write_episode_retries_until_budget_and_keeps_draft_when_doctor_is_worse():
    bad = '# 1 | Höhle | x\nSPONGEBOB [ängstlich]: Lass mich los!\nMR. KRABS [drohend]: Geld. Jetzt. Sofort.'
    planner = FakePlanner([bad, GOOD, bad, bad, bad])
    d = document()
    ep = asyncio.run(sp.write_episode(planner, d, 0, {'title': 'x'}, 'Idee', {}, None))
    assert planner.calls == ['Drehbuch', 'Drehbuch-Doktor', 'ShotVisuals']
    assert ep['screenplay'] == GOOD and 'Überarbeitung verworfen' in d['screenplays']['0']['doctor_error']
    assert ep['screenplay_stats']['words'] >= sp.budget(60)['min_words'] and not ep.get('warnings')
    # Restart: stored drafts are reused, no new LLM call.
    again = FakePlanner([])
    assert asyncio.run(sp.write_episode(again, d, 0, {'title': 'x'}, 'Idee', {}, None))['screenplay'] == GOOD and again.calls == []


def line(scene, duration, turn=0, pause=.18):
    return {'episode': 0, 'scene': scene, 'turn': turn, 'duration': duration, 'pause_after': pause, 'speaker': 'x'}


def test_krusty_case_no_long_silence_in_lip_sync_shots():
    """10 speaking shots, 24.8 s speech, 60 s minimum, now with 2 silent action shots:
    every lip-sync shot ends at most TAIL+TALK_TAIL_MAX after its last word."""
    durations = [(0.98, 1.04), (2.4, 1.56), (0.91, 1.59), (1.7, 0.94), (1.16,), (0.88, 2.23), (0.98, 1.4), (1.3, 1.2), (1.5, 1.1), (1.3, 1.2)]
    scenes = [{'seconds': 4} for _ in durations] + [{'seconds': 4}, {'seconds': 4}]
    lines = [line(si, dur, t) for si, group in enumerate(durations) for t, dur in enumerate(group)]
    episode = {'scenes': scenes, 'dialogue_mode': 'rich', 'minimum_seconds': 60}
    report = audio_layout([episode], lines, 60, 25)[0]
    assert report['minimum_met'] and report['silent_shots'] == 2
    for si, group in enumerate(durations):
        last = max((l for l in lines if l['scene'] == si), key=lambda l: l['turn'])
        tail = scenes[si]['render_seconds'] - (last['offset'] + last['duration'])
        assert tail <= TAIL + TALK_TAIL_MAX + .05, (si, tail)
    assert scenes[-1]['render_seconds'] > 10      # the action shots carry the rest


def test_shot_just_over_a_window_is_tightened():
    group = [{'duration': 1.35, 'pause_after': .3}, {'duration': 1.35, 'pause_after': .3}]   # 0.08+2.7+0.3+0.25 = 3.33 s
    assert talk_windows(3.33) == 2
    plan = talk_plan(group)
    assert talk_windows(plan['seconds']) == 1 and plan['pauses'][0] >= .06


def test_far_over_a_window_is_not_squeezed():
    plan = talk_plan([{'duration': 4.0, 'pause_after': .2}])
    assert talk_windows(plan['seconds']) == 2 and plan['tail'] == TAIL


def test_without_silent_shots_window_capacity_is_used_first():
    times = fill_target([2.0, 4.0], [True, True], 9, [1, 1])
    assert sum(times) == pytest.approx(9)
    assert sum(talk_windows(t) for t in times) == 3       # [1, 2]: every second fits windows already paid for


def test_a_silent_shot_always_exists_for_the_missing_time():
    text = '# 1 | Höhle | x\n' + '\n'.join(f'{"SPONGEBOB" if i % 2 else "PATRICK"} [fröhlich]: Das ist Zeile Nummer {i} in unserem kleinen Gespräch hier.' for i in range(14))
    cut = sp.ensure_action(sp.shots(*sp.parse(text, CAST)[:3], CAST), 60)
    actions = [c for c in cut if c['kind'] == 'action']
    assert len(actions) == 1 and actions[0]['visible'] and not actions[0]['lines']
    assert sp.ensure_action(cut, 60) == cut and len(sp.ensure_action(cut[:3], 15)) == 3


# --- Fixes from the 0.17 review -------------------------------------------------

def test_unusable_screenplay_is_forgotten_so_replanning_writes_a_new_one():
    huge = '# 1 | Ort | x\n' + '\n'.join(f'{"SPONGEBOB" if i % 2 else "PATRICK"} [fröhlich]: Zeile {i} ist hier.' for i in range(50))
    planner = FakePlanner([huge] * 6)
    d = document()
    with pytest.raises(RuntimeError, match='höchstens 44'):
        asyncio.run(sp.write_episode(planner, d, 0, {'title': 'x'}, 'Idee', {}, None))
    assert '0' not in d['screenplays']


def test_shot_cap_is_fed_back_to_the_writer():
    huge = '# 1 | Ort | x\n' + '\n'.join(f'{"SPONGEBOB" if i % 2 else "PATRICK"} [fröhlich]: Das ist die Zeile Nummer {i}.' for i in range(50))
    assert any('Zu viele Einstellungen' in e for e in sp.check(*sp.parse(huge, CAST), CAST, 90))


def test_partial_visuals_are_kept_and_failed_visuals_not_cached():
    class Partial(FakePlanner):
        async def llm(self, schema, instruction, data):
            self.calls.append(schema.__name__)
            return {'shots': [{'shot': i + 1, 'still': f'{s["visible"][0]} in the cave', 'motion': 'waves', 'camera': 'medium', 'ambience': 'room'}
                              for i, s in enumerate(data['shots'])][:-1]}
    d = document()
    asyncio.run(sp.write_episode(Partial([GOOD, GOOD]), d, 0, {'title': 'x'}, 'Idee', {}, None))
    store = d['screenplays']['0']
    assert len(store['visuals']['shots']) == store['visuals']['shots'][-1]['shot'] and 'Einstellung' in store['visual_error']

    class Broken(FakePlanner):
        async def llm(self, schema, instruction, data): raise RuntimeError('kaputt')
    d = document()
    ep = asyncio.run(sp.write_episode(Broken([GOOD, GOOD]), d, 0, {'title': 'x'}, 'Idee', {}, None))
    assert 'visuals' not in d['screenplays']['0'] and ep['scenes'][0]['still']


def test_single_figure_film_needs_no_speaker_changes():
    mono = '# 1 | Bühne | Oma erzählt\n' + '\n'.join(f'OMA [fröhlich]: Und dann hab ich den Kuchen ganz allein gegessen, Nummer {i}!' for i in range(12)) + \
           '\nAKTION: Oma tanzt.\nAKTION: Oma fällt um.'
    errors = sp.check(*sp.parse(mono, ['Oma']), ['Oma'], 60)
    assert not any('Sprecherwechsel' in e for e in errors) and sp.budget(60, 1)['min_turns'] == 0


def test_action_shot_sees_the_figure_by_first_name_and_genitive():
    cast = ['SpongeBob', 'Patrick Star']
    title, beats, lines, _ = sp.parse('# 1 | Ort | x\nAKTION: Patrick springt mit einem Netz aus dem Schatten.\nAKTION: SpongeBobs Spatel fliegt durch die Luft.', cast)
    cut = sp.shots(title, beats, lines, cast)
    assert cut[0]['visible'] == ['Patrick Star'] and cut[1]['visible'] == ['SpongeBob']


def test_sanitize_keeps_common_words_and_shared_name_parts():
    assert sp.sanitize('SpongeBob stands on the sandy seabed, holding a spatula', ['SpongeBob'], ['SpongeBob', 'Sandy']) == \
        'SpongeBob stands on the sandy seabed, holding a spatula'
    assert sp.sanitize('SpongeBob looks up at the stars, smiling', ['SpongeBob'], ['SpongeBob', 'Patrick Star']).startswith('SpongeBob looks up at the stars')
    assert sp.sanitize('Captain Smee polishing a cannon, Captain Hook shouting', ['Captain Smee'], ['Captain Smee', 'Captain Hook']) == 'Captain Smee polishing a cannon'
    assert sp.sanitize("SpongeBob grins, Sandy's helmet glints", ['SpongeBob'], ['SpongeBob', 'Sandy']) == 'SpongeBob grins'


def test_abbreviations_and_markdown_do_not_break_lines():
    assert not sp.telegram('Danke, Mr. Krabs.') and not sp.telegram('Ja, Mr. Krabs.')
    title, beats, lines, problems = sp.parse('**SPONGEBOB** [wütend]: **Lass das, Patrick!**\nMR KRABS [drohend]: Und jetzt alle raus hier!', CAST)
    assert not problems and lines[0]['speaker'] == 'SpongeBob' and lines[0]['text'] == 'Lass das, Patrick!'
    assert lines[1]['speaker'] == 'Mr. Krabs'


def test_overlapping_names_longest_wins():
    # 'Tim' must not eat the 'Tims' of 'Tims Oma' (review round 3).
    family = ['Tim', 'Tims Oma']
    assert sp.sanitize('Tim backt Kekse mit Tims Oma.', ['Tim'], family) == 'Tim backt Kekse.'
    assert sp.sanitize('Tims Oma holt ein Blech aus dem Ofen.', ['Tims Oma'], family) == 'Tims Oma holt ein Blech aus dem Ofen.'
    assert sp.sanitize('Tims Oma winkt Tim zu.', ['Tims Oma'], family).startswith('Tims Oma winkt')
    assert sp.sanitize('Tim umarmt Tims Mama.', ['Tim'], ['Tim', 'Tims Mama']) == 'Tim umarmt.'
    for line, seen in [('AKTION: Tims Oma holt ein Blech aus dem Ofen.', ['Tims Oma']), ('AKTION: Tim rennt zu Tims Oma.', ['Tim', 'Tims Oma'])]:
        title, beats, lines, _ = sp.parse('# 1 | Küche | Backen\n' + line, family)
        assert sp.shots(title, beats, lines, family)[0]['visible'] == seen
    from cast_design import strip_names
    assert 'Tims Oma' not in strip_names('A boy in a red scarf knitted by Tims Oma', ['Tims Oma'], ['Tim'])


def test_hidden_figure_as_subject_drops_the_clause():
    sb = ['SpongeBob', 'Mr. Krabs', 'Patrick Star', 'Plankton']
    assert sp.sanitize('Mr. Krabs grabs SpongeBob by the collar and shakes him', ['SpongeBob'], sb) == ''
    assert sp.sanitize('Captain Hook yells at Captain Smee.', ['Captain Smee'], ['Captain Smee', 'Captain Hook']) == ''
    assert sp.sanitize('SpongeBob und Patrick tanzen auf dem Tisch.', ['SpongeBob'], sb) == 'SpongeBob tanzen auf dem Tisch.'
    assert sp.sanitize('SpongeBob waves to Mr Krabs.', ['SpongeBob'], sb) == 'SpongeBob waves.'
    assert sp.sanitize('SpongeBob winkt Herrn Krabs zu.', ['SpongeBob'], sb) == 'SpongeBob winkt zu.'   # 'zu' is part of the verb
    assert sp.sanitize('SpongeBob hands Mr. Krabs the money while Plankton watches', ['SpongeBob', 'Mr. Krabs'], sb) == 'SpongeBob hands Mr. Krabs the money'
    assert sp.sanitize('Plankton watches, SpongeBob flips a patty, Patrick waves', ['SpongeBob'], sb) == 'SpongeBob flips a patty'
