"""0.18 cutting rhythm: speech blocks, reaction shots (L-cut), establishing shots, layout 18.

Cay after his second film: "ist es mir noch zu viel 1 Person spricht, nächste Szene, andere
Person spricht." Measured: 17 shots, 13 lip-sync shots with exactly one line each, 12 speaker
changes, silent shots always 2.52 s. The LLM is replaced by fixed screenplays; these tests prove
the cut, the scene fields, the sound layout and the render routing, not how a real film looks.

Part 1 pins the 0.17 behaviour: tests/fixtures/v17_reference.json holds what commit 201ef32 made
from the inputs in tests/cut_samples.py. Projects planned or voiced before 0.18 keep exactly that.
"""
import asyncio
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))
sys.path.insert(0, str(ROOT / 'tests'))

import cast_design  # noqa: E402
import cut_samples as cs  # noqa: E402
import screenplay as sp  # noqa: E402
from factory_timing import (audio_layout, plan_seconds, talk_plan, rendered_windows, off_screen,  # noqa: E402
                            REACTION_CAP, REACTION_MIN, ACTION_BASE, ESTABLISH_BASE)
from studio_quality_policy import motion_direction  # noqa: E402

REF = json.loads((ROOT / 'tests/fixtures/v17_reference.json').read_text(encoding='utf-8'))
PEOPLE = {name: [{'name': n, 'appearance': 'x'} for n in cast] for name, (_, cast) in cs.TEXTS.items()}


def plain(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


# --- Part 1: 0.17 stays exactly as it was ------------------------------------------------

def test_policy_13_budget_is_unchanged():
    for key, value in REF['budget'].items():
        duration, speakers = map(int, key.split(':'))
        assert sp.budget(duration, speakers, sp.LEGACY_POLICY) == value, key


@pytest.mark.parametrize('name', sorted(cs.TEXTS))
def test_policy_13_cut_scenes_checks_and_faces_are_unchanged(name):
    text, cast = cs.TEXTS[name]; ref = REF['texts'][name]; people = PEOPLE[name]
    title, beats, lines, problems = sp.parse(text, cast)
    assert plain([title, beats, lines, problems]) == ref['parsed']
    cut = sp.shots(title, beats, lines, cast, sp.LEGACY_POLICY)
    assert plain(cut) == ref['cut']
    ensured = sp.ensure_action(cut, 60)
    assert plain(ensured) == ref['ensured']
    for seconds, errors in ref['check'].items():
        assert sp.check(title, beats, lines, problems, cast, int(seconds), sp.LEGACY_POLICY) == errors
    episode = sp.assemble(title, {'goal': 'Ziel', 'stakes': 'Einsatz', 'payoff': 'Pointe'}, {'title': 'x'}, ensured,
                          cs.visuals_for(ensured), people, {}, sp.LEGACY_POLICY)
    cliff = sp.assemble(title, None, {'title': 'x', 'plot': 'p', 'ending': 'e'}, ensured, {'shots': []}, people, {'end_with': 'offen'}, sp.LEGACY_POLICY)
    assert plain(cliff) == ref['cliff']
    plan_seconds(episode, 60, 25)
    assert plain(episode) == ref['episode']
    assert [cast_design.faces(s) for s in episode['scenes']] == ref['faces']
    assert [cast_design.scene_text(s, people) for s in episode['scenes']] == ref['scene_text']
    lines_timed = cs.timed_lines(episode)
    for run in (lambda e, l: audio_layout(e, l, 60, 25), lambda e, l: audio_layout(e, l, 60, 25, version=17)):
        timed, timed_lines = copy.deepcopy(episode), copy.deepcopy(lines_timed)
        report = run([timed], timed_lines)
        assert plain(report) == ref['layout']['report'] and plain(timed['scenes']) == ref['layout']['scenes']
        assert plain(timed_lines) == ref['layout']['lines']


class Planner:
    """Same stand-in as in the capture script: returns the text, records every prompt."""
    def __init__(self, text):
        self.text = text; self.calls = []
    async def write(self, instruction, data, label='', check=None, attempts=3):
        self.calls.append({'kind': 'write', 'label': label, 'instruction': instruction, 'data': plain(data)})
        return self.text
    async def llm(self, schema, instruction, data):
        self.calls.append({'kind': 'llm', 'schema': schema.__name__, 'instruction': instruction, 'data': plain(data)})
        return {'shots': [{'shot': s['shot'], 'still': f'{(s["visible"] or ["The place"])[0]} in the cave, Mr. Krabs looming behind',
                           'motion': 'waves at Patrick', 'camera': 'medium shot', 'ambience': 'room'} for s in data['shots']]}
    def save(self, d): pass


def document(cast, store=None):
    d = {'idea': {'duration': 60, 'episodes': 1}, 'episodes': [],
         'plan': {'title': 'Krusty', 'style': 'clay', 'cast': [{'name': n, 'appearance': 'x'} for n in cast], 'episodes': [{'title': 'x'}]}}
    if store is not None: d['screenplays'] = {'0': store}
    return d


@pytest.mark.parametrize('name', sorted(cs.TEXTS))
def test_policy_13_screenplay_prompts_and_episode_are_unchanged(name):
    text, cast = cs.TEXTS[name]; ref = REF['texts'][name]['write_episode']
    d = document(cast, {'policy': 13}); planner = Planner(text)
    episode = asyncio.run(sp.write_episode(planner, d, 0, {'title': 'x'}, 'Idee', {}, None))
    assert planner.calls == ref['calls']
    assert plain(episode) == ref['episode'] and plain(d['screenplays']['0']) == ref['store']


@pytest.mark.parametrize('name', sorted(cs.TEXTS))
def test_screenplay_written_before_0_18_keeps_its_cut(name):
    """A 0.17 project mid-planning has a stored screenplay without a policy: it stays policy 13."""
    text, cast = cs.TEXTS[name]; ref = REF['texts'][name]['write_episode']
    store = {k: v for k, v in copy.deepcopy(ref['store']).items() if k != 'policy'}
    d = document(cast, store); planner = Planner(text)
    episode = asyncio.run(sp.write_episode(planner, d, 0, {'title': 'x'}, 'Idee', {}, None))
    assert planner.calls == [] and plain(episode) == ref['episode'] and d['screenplays']['0']['policy'] == 13


def test_a_series_planned_before_0_18_keeps_policy_13_for_its_next_episodes():
    """A 0.17 project still planning: episode 1 was written with 13, episode 2 is written now."""
    text, cast = cs.TEXTS['cay_blocks']
    for earlier in ({'screenplays': {'0': {'draft': 'x', 'final': 'x'}}}, {'screenplays': {'0': {'policy': 13, 'final': 'x'}}},
                    {'episodes': [{'title': 'Folge 1', 'script': 'screenplay', 'story_policy': 13, 'scenes': []}]}):
        d = document(cast); d.update(copy.deepcopy(earlier)); planner = Planner(text)
        episode = asyncio.run(sp.write_episode(planner, d, 1, {'title': 'x'}, 'Idee', {}, None))
        assert d['screenplays']['1']['policy'] == 13 and episode['story_policy'] == 13 and 'reaction' not in [s['kind'] for s in episode['scenes']]
    d = document(cast); planner = Planner(text)                                  # a new project
    episode = asyncio.run(sp.write_episode(planner, d, 0, {'title': 'x'}, 'Idee', {}, None))
    assert d['screenplays']['0']['policy'] == 14 and episode['story_policy'] == 14 and 'reaction' in [s['kind'] for s in episode['scenes']]
    assert 'Redeblöcken' in planner.calls[0]['instruction'] and 'role' in planner.calls[-1]['data']['shots'][0]
    d['episodes'].append(episode); planner = Planner(text)                       # its next episode stays 14
    assert asyncio.run(sp.write_episode(planner, d, 1, {'title': 'x'}, 'Idee', {}, None))['story_policy'] == 14


def test_layout_17_and_motion_text_are_unchanged():
    from factory_audio import layout
    for case, ref in zip(cs.layout_cases(), REF['layouts']):
        for run in (lambda e, l: audio_layout(e, l, case['minimum'], 25), lambda e, l: layout(e, l, case['minimum'], 25, 17)):
            episode, lines = copy.deepcopy(case['episode']), copy.deepcopy(case['lines'])
            assert plain(run([episode], lines)) == ref['report']
            assert plain(episode['scenes']) == ref['scenes'] and plain(lines) == ref['lines']
    for scene, lines, ref in zip(cs.MOTION_SCENES, cs.MOTION_LINES, REF['motion']):
        for policy in (0, 13):
            assert [motion_direction(scene, lines, 0, 4.0, policy), motion_direction(scene, [], 0, 3.2, policy)] == ref
        assert [motion_direction(scene, lines, 0, 4.0), motion_direction(scene, [], 0, 3.2)] == ref


def test_policy_13_prompt_texts_are_unchanged():
    strings = REF['strings']
    assert sp.rules(13) == sp.RULES == strings['RULES'] and sp.example(13) == sp.EXAMPLE == strings['EXAMPLE']
    assert sp.FORMAT == strings['FORMAT'] and sp.VISUAL_REPAIR == strings['VISUAL_REPAIR']
    assert sp.visual_instruction(13) == sp.VISUAL_INSTRUCTION == strings['VISUAL_INSTRUCTION']


# --- Part 2: the 0.18 script and cut ------------------------------------------------------

def test_budget_asks_for_speech_blocks():
    b60 = sp.budget(60)
    assert (b60['min_turns'], b60['max_turns']) == (6, 15) and b60['words'] == 120
    assert (sp.budget(15)['min_turns'], sp.budget(15)['max_turns']) == (3, 6)
    assert sp.budget(180)['max_turns'] == sp.MAX_SHOTS - sp.budget(180)['max_actions'] - 4    # MAX_SHOTS logic kept
    assert sp.budget(60, 1)['min_turns'] == 0 and sp.budget(60, 1)['max_turns'] == sp.MAX_SHOTS
    assert sp.budget(60, policy=13)['min_turns'] == 12                                       # what forced ping-pong
    assert 'Redeblöcken' in sp.rules() and 'Kein Ping-Pong' in sp.rules() and 'Telegrammstil' in sp.rules()
    # The new example itself is a valid block screenplay.
    example = sp.example().split('\n', 1)[1]
    title, beats, lines, problems = sp.parse(example, ['Oma', 'Tim', 'Opa'])
    assert not problems and sum(1 for i, l in enumerate(lines) if i and l['kind'] == 'line' and lines[i - 1].get('speaker') == l['speaker']) >= 3


def test_block_screenplay_passes_the_check_and_ping_pong_still_passes():
    for name in ('cay_blocks', 'cay_pingpong'):
        text, cast = cs.TEXTS[name]
        assert sp.check(*sp.parse(text, cast), cast, 60) == [], name
    bad = '# 1 | Höhle | x\n' + '\n'.join(f'SPONGEBOB [fröhlich]: Das ist meine Zeile Nummer {i} in einem sehr langen Monolog.' for i in range(12))
    assert any('Sprecherwechsel' in e for e in sp.check(*sp.parse(bad, cs.CAST), cs.CAST, 60))


def describe(cut):
    rows = []
    for i, s in enumerate(cut, 1):
        who = '+'.join(s['visible']) or '-'
        heard = f" (Stimme: {s['voice_of']})" if s.get('voice_of') else ''
        rows.append(f"{i:>2} {s['kind']:<9} {who:<20} {len(s['lines'])} Zeile(n){heard}")
    return rows


def lip_sync_windows(cut, rate=cs.SPEECH_RATE):
    """Lip-sync windows with the real talk_plan math, durations from words/2.6 s + 0.2 s."""
    total = 0
    for s in cut:
        if s['kind'] != 'line' or not s['lines']: continue
        group = [{'duration': len(l['text'].split()) / rate + .2, 'pause_after': .15} for l in s['lines']]
        total += rendered_windows(talk_plan(group)['seconds'])
    return total


def test_cay_film_before_and_after(capsys):
    """Cay's 0.17 film as a 13-line ping-pong, cut by 0.17 and by 0.18, and the same story
    written in speech blocks as the 0.18 rules ask for it."""
    text, cast = cs.TEXTS['cay_pingpong']
    title, beats, lines, _ = sp.parse(text, cast)
    before = sp.ensure_action(sp.shots(title, beats, lines, cast, 13), 60)
    same = sp.ensure_action(sp.shots(title, beats, lines, cast), 60)
    blocks = sp.ensure_action(sp.shots(*sp.parse(cs.CAY_BLOCKS, cast)[:3], cast), 60)
    with capsys.disabled():
        for label, cut in (('0.17, Ping-Pong', before), ('0.18, gleiches Ping-Pong', same), ('0.18, Redeblöcke', blocks)):
            print(f'\n{label}: {len(cut)} Einstellungen, {sum(s["kind"] == "line" for s in cut)} Lippen, {lip_sync_windows(cut)} Lippenfenster')
            print('\n'.join(describe(cut)))
    kinds = lambda cut: [s['kind'] for s in cut]
    # 0.17: every line its own lip-sync shot, every figure alone.
    assert len(before) == 17 and kinds(before).count('line') == 13 and all(len(s['lines']) == 1 for s in before if s['kind'] == 'line')
    # The same ping-pong text under 0.18: nothing to merge, only the new place gets a wide shot.
    assert kinds(same).count('line') == 13 and kinds(same).count('establish') == 1 and 'reaction' not in kinds(same)
    assert same[kinds(same).index('establish') + 1]['visible'] == ['Patrick']
    # Blocks: 7 lip-sync shots instead of 13, two lines heard over the listener, one wide shot.
    assert kinds(blocks).count('line') == 7 and kinds(blocks).count('reaction') == 2 and kinds(blocks).count('establish') == 1
    assert lip_sync_windows(blocks) < lip_sync_windows(before)
    changes = lambda cut: sum(1 for a, b in zip(cut, cut[1:]) if a['kind'] == b['kind'] == 'line' and a['visible'] != b['visible'])
    assert changes(blocks) < changes(before)


def block_text(blocks, place='Höhle'):
    """Screenplay from [(speaker, [words per line], emotion)] in one section."""
    out = [f'# 1 | {place} | x']
    for speaker, sizes, emotion in blocks:
        for n in sizes:
            out.append(f'{speaker.upper()} [{emotion}]: ' + ' '.join(['wort'] * (n - 1)) + ' ende!')
    return '\n'.join(out)


def test_lines_of_one_speaker_merge_by_estimated_length():
    cast = ['SpongeBob', 'Patrick']
    cut = sp.shots(*sp.parse(block_text([('SpongeBob', [10, 10], 'ruhig'), ('Patrick', [9], 'ruhig')]), cast)[:3], cast)
    assert [len(s['lines']) for s in cut] == [2, 1]                      # 7.9 s: one shot
    cut = sp.shots(*sp.parse(block_text([('SpongeBob', [13, 13], 'ruhig'), ('Patrick', [9], 'ruhig')]), cast)[:3], cast)
    assert [len(s['lines']) for s in cut] == [1, 1, 1]                   # 10.2 s: over three windows
    cut = sp.shots(*sp.parse(block_text([('SpongeBob', [5, 5, 5, 5], 'ruhig'), ('Patrick', [9], 'ruhig')]), cast)[:3], cast)
    assert [len(s['lines']) for s in cut[:2]] == [3, 1]                  # at most three lines
    assert sp.spoken_seconds([{'text': ' '.join(['w'] * 13)}] * 2) == pytest.approx(26 / 2.6 + .18)
    # 0.17 merged by words: 24 words = 9.4 s, four windows.
    old = sp.shots(*sp.parse(block_text([('SpongeBob', [12, 12], 'ruhig'), ('Patrick', [9], 'ruhig')]), cast)[:3], cast, 13)
    assert len(old[0]['lines']) == 2


def reactions(cut):
    return [(i, s) for i, s in enumerate(cut) if s['kind'] == 'reaction']


def test_reaction_moves_the_last_line_to_the_listener():
    cast = ['SpongeBob', 'Mr. Krabs']
    text = block_text([('SpongeBob', [8, 8], 'flehend'), ('Mr. Krabs', [9, 7], 'drohend'), ('SpongeBob', [9], 'ängstlich'), ('Mr. Krabs', [8, 8], 'wütend')])
    cut = sp.shots(*sp.parse(text, cast)[:3], cast)
    assert [s['kind'] for s in cut] == ['line', 'line', 'reaction', 'line', 'line']
    block, reaction = cut[1], cut[2]
    assert len(block['lines']) == 1 and reaction['visible'] == ['SpongeBob'] and reaction['voice_of'] == 'Mr. Krabs'
    assert [l['speaker'] for l in reaction['lines']] == ['Mr. Krabs'] and sp.words(reaction['lines'][0]['text']) == 7
    assert reaction['emotion'] == 'ängstlich'                            # the listener's upcoming line
    # First block (hook) and last block (payoff) stay on a face with all their lines.
    assert len(cut[0]['lines']) == 2 and len(cut[-1]['lines']) == 2


def test_reaction_rules_word_limit_alternation_and_cap():
    cast = ['SpongeBob', 'Mr. Krabs']
    long_last = block_text([('SpongeBob', [8], 'ruhig'), ('Mr. Krabs', [6, 13], 'wütend'), ('SpongeBob', [8], 'ruhig')])
    assert not reactions(sp.shots(*sp.parse(long_last, cast)[:3], cast))          # a 13-word line stays on the face
    # Ten eligible blocks between hook and payoff: every second one at most, at most a third of the speaking shots.
    many = [('SpongeBob', [6], 'ruhig')] + [(('Mr. Krabs', 'SpongeBob')[i % 2], [6, 6], 'ruhig') for i in range(10)] + [('Mr. Krabs', [6], 'ruhig')]
    cut = sp.shots(*sp.parse(block_text(many), cast)[:3], cast)
    found = reactions(cut); speaking = [s for s in cut if s['kind'] in ('line', 'reaction')]
    assert len(found) == 5 and 3 * len(found) <= len(speaking) + 1
    blocks_before = [sum(1 for s in cut[:i] if s['kind'] == 'line') for i, _ in found]
    assert all(b - a >= 2 for a, b in zip(blocks_before, blocks_before[1:]))   # never two eligible blocks in a row
    # Five speaking blocks (the payoff is another speaker, so nothing merges): two reactions at most.
    few = [('SpongeBob', [6], 'ruhig')] + [(('Mr. Krabs', 'SpongeBob')[i % 2], [6, 6], 'ruhig') for i in range(3)] + [('SpongeBob', [6], 'ruhig')]
    cut = sp.shots(*sp.parse(block_text(few), cast)[:3], cast)
    assert len(reactions(cut)) == 2 and 3 * len(reactions(cut)) <= len([s for s in cut if s['lines']]) + 1
    # A payoff line of the same speaker joins the block before it: that block is the last one and stays on the face.
    merged = few[:-1] + [('Mr. Krabs', [6], 'ruhig')]
    cut = sp.shots(*sp.parse(block_text(merged), cast)[:3], cast)
    assert [len(s['lines']) for s in cut if s['kind'] == 'line'][-1] == 3 and len(reactions(cut)) == 1


def test_listener_is_never_someone_from_another_place():
    cast = ['SpongeBob', 'Mr. Krabs', 'Patrick']
    text = ('# 1 | Höhle | x\nSPONGEBOB [ruhig]: Eins zwei drei vier fünf sechs!\n'
            'MR. KRABS [wütend]: Eins zwei drei vier fünf sechs sieben!\nMR. KRABS [wütend]: Raus aus meiner Höhle, sofort!\n'
            '# 2 | Nebliges Dorf | Patrick schaut\nPATRICK [überrascht]: Hey, ist das da unten SpongeBob?')
    cut = sp.shots(*sp.parse(text, cast)[:3], cast)
    found = reactions(cut)
    assert len(found) == 1 and found[0][1]['visible'] == ['SpongeBob'] and found[0][1]['emotion'] == 'ruhig'   # earlier speaker, calm
    alone = ('# 1 | Höhle | x\nSPONGEBOB [ruhig]: Eins zwei drei vier fünf sechs!\n# 2 | Bühne | y\n'
             'MR. KRABS [wütend]: Eins zwei drei vier fünf sechs sieben!\nMR. KRABS [wütend]: Raus aus meiner Höhle, sofort!\n'
             '# 3 | Dorf | z\nPATRICK [überrascht]: Hey, ist das da unten SpongeBob?')
    assert not reactions(sp.shots(*sp.parse(alone, cast)[:3], cast))         # nobody else in that section: no split


def test_establishing_shot_only_at_a_new_place():
    cast = ['Oma', 'Tim', 'Opa']
    cut = sp.shots(*sp.parse(cs.OMA, cast)[:3], cast)
    est = [(i, s) for i, s in enumerate(cut) if s['kind'] == 'establish']
    assert len(est) == 1 and est[0][0] > 0 and cut[est[0][0] + 1]['beat'] == est[0][1]['beat'] == 1
    assert est[0][1]['visible'] == ['Oma', 'Opa'] and not est[0][1]['lines'] and est[0][1]['place'] == 'Garten mit Hängematte'
    places = ['Küche', 'Garten', 'Küche', 'Dach', 'Keller']
    text = '\n'.join(f'# {i + 1} | {p} | x\nOMA [ruhig]: Zeile {i} mit ein paar Wörtern mehr.\nTIM [ruhig]: Antwort {i} mit ein paar Wörtern.' for i, p in enumerate(places))
    cut = sp.shots(*sp.parse(text, cast)[:3], cast)
    est = [s for s in cut if s['kind'] == 'establish']
    assert [s['place'] for s in est] == ['Garten', 'Dach'] and cut[0]['kind'] == 'line'    # at most two, a known place gets none
    opens_with_action = '# 1 | Küche | x\nOMA [ruhig]: Hallo Tim, schön dass du da bist.\n# 2 | Garten | y\nAKTION: Tim rennt in den Garten.\nTIM [ruhig]: Hier draußen ist es viel schöner, Oma.'
    assert 'establish' not in [s['kind'] for s in sp.shots(*sp.parse(opens_with_action, cast)[:3], cast)]


def test_optional_shots_never_exceed_the_shot_cap():
    cast = ['SpongeBob', 'Patrick']
    rows = [('SpongeBob', [6, 6], 'ruhig') if i % 2 else ('Patrick', [6, 6], 'ruhig') for i in range(30)]
    text = block_text(rows[:15]) + '\n' + block_text(rows[15:], 'Garten').replace('# 1 |', '# 2 |')
    title, beats, lines, problems = sp.parse(text, cast)
    base = sp.shots(title, beats, lines, cast, 13)
    cut = sp.shots(title, beats, lines, cast)
    assert len(base) == 30 and len(sp.ensure_action(cut, 60)) <= sp.MAX_SHOTS
    assert len(cut) == sp.MAX_SHOTS - 1 and sum(s['kind'] == 'establish' for s in cut) == 1
    assert not any('Zu viele Einstellungen' in e for e in sp.check(title, beats, lines, problems, cast, 120))


def test_added_action_never_splits_a_block_from_its_reaction():
    cast = ['SpongeBob', 'Mr. Krabs']
    text = block_text([('SpongeBob', [8], 'ruhig'), ('Mr. Krabs', [8, 8], 'wütend'), ('SpongeBob', [8], 'ruhig'), ('Mr. Krabs', [8], 'ruhig')])
    cut = sp.shots(*sp.parse(text, cast)[:3], cast)
    assert [s['kind'] for s in cut] == ['line', 'line', 'reaction', 'line', 'line']
    ensured = sp.ensure_action(cut, 60)
    i = [s['kind'] for s in ensured].index('action')
    assert [s['kind'] for s in ensured[:i + 1]] == ['line', 'line', 'reaction', 'action'] and ensured[i]['visible'] == ['SpongeBob']


# --- Part 3: scenes, pictures and motion ----------------------------------------------------

def blocks_episode(visuals=None):
    text, cast = cs.TEXTS['cay_blocks']
    title, beats, lines, _ = sp.parse(text, cast)
    cut = sp.ensure_action(sp.shots(title, beats, lines, cast), 60)
    episode = sp.assemble(title, {'goal': 'Ziel', 'stakes': 'Einsatz', 'payoff': 'Pointe'}, {'title': 'x'}, cut,
                          visuals if visuals is not None else cs.visuals_for(cut), PEOPLE['cay_blocks'], {})
    return cut, episode


def test_reaction_and_establish_scene_fields():
    cut, episode = blocks_episode()
    assert episode['story_policy'] == 14 == sp.POLICY
    scenes = episode['scenes']
    reaction = next(s for s in scenes if s['kind'] == 'reaction')
    assert reaction['cast'] == ['SpongeBob'] and reaction['voice_of'] == 'Mr. Krabs' and reaction['camera'] == 'close-up'
    assert reaction['title'] == 'Reaktion: SpongeBob hört Mr. Krabs zu'
    assert [l['speaker'] for l in reaction['dialogues']] == ['Mr. Krabs'] and reaction['emotion'] == 'ängstlich'
    for text in (reaction['still'], reaction['animation_prompt']):
        assert 'Krabs' not in text and not sp.OPEN_MOUTH.search(text)
    # The planner's own still is kept (without the off-screen figure); the face comes with the picture text.
    assert reaction['still'] == 'SpongeBob in the cave'
    picture = cast_design.scene_text(reaction, PEOPLE['cay_blocks'])
    assert 'lips pressed together, listening in silence' in picture and 'Framing: close-up.' in picture and 'Krabs' not in picture
    establish = next(s for s in scenes if s['kind'] == 'establish')
    assert establish['camera'] == 'wide establishing shot' and establish['dialogues'] == [] and establish['title'].startswith('Totale: ')
    assert len(establish['cast']) <= 2
    # Speaking shots get different framings; nothing new on a speaking scene.
    speaking = [s for s in scenes if s['kind'] == 'line']
    assert len({s['camera'] for s in speaking}) >= 2 and all('voice_of' not in s for s in speaking)
    for scene in scenes:
        assert not sp.offscreen_names(scene['still'] + ' ' + scene['animation_prompt'], scene['cast'], cs.CAST), scene['title']


def test_speaking_shots_change_framing_and_silent_faces_keep_their_mouths_closed():
    """Cay's film: thirteen frontal medium shots in a row and grinning, talking mouths in silent shots."""
    cut, _ = blocks_episode()
    same = {'shots': [{'shot': i + 1, 'still': f'{(s["visible"] or ["The place"])[0]} grins widely in the cave', 'motion': 'moves',
                       'camera': 'medium shot', 'ambience': 'room'} for i, s in enumerate(cut)]}
    _, episode = blocks_episode(same)
    scenes = episode['scenes']
    for a, b in zip(scenes, scenes[1:]):
        if a['kind'] == b['kind'] == 'line': assert a['camera'] != b['camera'], (a['title'], b['title'])
    after_reaction = [b for a, b in zip(scenes, scenes[1:]) if a['kind'] == 'reaction' and b['kind'] == 'line' and b['cast'] == a['cast']]
    assert all('close' not in s['camera'] for s in after_reaction)
    actions = [s for s in scenes if s['kind'] == 'action']
    assert actions and all(s['still'].endswith(('mouth closed', 'mouths closed')) for s in actions)
    assert all(not s['still'].endswith('closed') for s in scenes if s['kind'] == 'line')
    establish = next(s for s in scenes if s['kind'] == 'establish')
    assert establish['still'].startswith('Wide establishing view') and establish['camera'] == 'wide establishing shot'


def test_who_may_speak_where():
    from factory_timing import allowed_speakers
    assert allowed_speakers({'kind': 'reaction', 'cast': ['SpongeBob'], 'voice_of': 'Mr. Krabs'}) == ['Mr. Krabs']
    assert allowed_speakers({'kind': 'establish', 'cast': ['Oma']}) == []
    for old in ({'cast': ['Oma', 'Tim']}, {'kind': 'line', 'cast': ['Oma']}, {'kind': 'action', 'cast': ['Tim']}, {'kind': 'scene', 'cast': []}):
        assert allowed_speakers(old) == old['cast']


def test_planner_text_with_an_open_mouth_never_reaches_a_reaction():
    cut, _ = blocks_episode()
    index = next(i for i, s in enumerate(cut) if s['kind'] == 'reaction')
    visuals = {'shots': [{'shot': index + 1, 'still': 'SpongeBob shouting back at Mr. Krabs, mouth wide open', 'motion': 'SpongeBob yells and waves',
                          'camera': 'medium shot', 'ambience': 'room'}]}
    _, episode = blocks_episode(visuals)
    reaction = episode['scenes'][index]
    assert not sp.OPEN_MOUTH.search(reaction['still'] + reaction['animation_prompt']) and 'Krabs' not in reaction['still']
    calm = {'shots': [{'shot': index + 1, 'still': 'SpongeBob clutches his spatula, trembling in the cave, Mr. Krabs looming', 'motion': 'SpongeBob shrinks back slowly',
                       'camera': 'medium shot', 'ambience': 'room'}]}
    _, episode = blocks_episode(calm)
    assert episode['scenes'][index]['still'].startswith('SpongeBob clutches his spatula') and 'Krabs' not in episode['scenes'][index]['still']
    assert episode['scenes'][index]['camera'] == 'close-up'


def test_reaction_picture_gets_a_closed_mouth_face_and_never_the_off_screen_speaker():
    _, episode = blocks_episode()
    reaction = next(s for s in episode['scenes'] if s['kind'] == 'reaction')
    face = cast_design.faces(reaction)
    assert face.startswith("SpongeBob's facial expression:") and 'lips pressed together' in face and 'Krabs' not in face
    picture = cast_design.scene_text(reaction, PEOPLE['cay_blocks'])
    assert 'Krabs' not in picture and 'Framing: close-up.' in picture
    # Every closed-mouth face really keeps the mouth closed.
    assert not any(sp.OPEN_MOUTH.search(f) or 'open' in f for f in sp.REACTION_EXPRESSIONS.values())
    speaking = next(s for s in episode['scenes'] if s['kind'] == 'line')
    assert cast_design.faces(speaking).startswith(f"{speaking['cast'][0]}'s facial expression:")


def test_motion_text_for_reaction_establish_and_new_silent_action():
    reaction = motion_direction({'cast': ['SpongeBob'], 'kind': 'reaction'}, [], 0, 3.0, 14)
    assert 'SpongeBob listens in silence' in reaction and 'lips stay closed' in reaction and 'Camera: steady close-up' in reaction
    assert 'no ' not in reaction.split('Normal real-time speed, never slow motion. ')[1].lower()       # positive phrasing
    establish = motion_direction({'cast': ['Oma', 'Opa'], 'kind': 'establish'}, [], 0, 2.4, 14)
    assert 'wide view' in establish and 'closed lips' in establish and 'slow, smooth movement' in establish
    action = motion_direction({'cast': ['Tim'], 'kind': 'action'}, [], 0, 3.2, 14)
    assert 'Every mouth stays closed the whole time' in action and 'nobody talks' not in action
    assert 'nobody talks' in motion_direction({'cast': ['Tim'], 'kind': 'action'}, [], 0, 3.2, 13)


# --- Part 4: layout 18 ------------------------------------------------------------------------

def timed_blocks():
    cut, episode = blocks_episode()
    plan_seconds(episode, 60, 25)
    return cut, episode, cs.timed_lines(episode)


def test_layout_18_numbers_and_windows_saved(capsys):
    cut, episode, lines = timed_blocks()
    e17, l17 = copy.deepcopy(episode), copy.deepcopy(lines)
    old = audio_layout([e17], l17, 60, 25)[0]               # 0.17 layout: the reaction would be lip-sync
    report = audio_layout([episode], lines, 60, 25, version=18)[0]
    scenes = episode['scenes']
    assert report['layout'] == 18 and report['minimum_met'] and report['reaction_shots'] == 2 and report['establish_shots'] == 1
    assert report['lip_sync_shots'] == 7 and report['talk_windows'] < old['talk_windows']
    talk = [s['render_seconds'] for s in scenes if s['kind'] == 'line']
    assert report['talk_windows'] == sum(rendered_windows(t) for t in talk)
    for si, scene in enumerate(scenes):
        own = [l for l in lines if l['scene'] == si]
        for line in own:                                     # "Dialog passt nicht zur Szenendauer" keeps holding
            assert line['offset'] + line['duration'] <= scene['render_seconds'] + 1e-6
        if scene['kind'] == 'reaction':
            natural = .08 + sum(l['duration'] for l in own) + .45
            assert REACTION_MIN <= scene['render_seconds'] <= max(REACTION_CAP, natural) + .04
            assert own[0]['offset'] == pytest.approx(.08)
        if scene['kind'] == 'action': assert scene['render_seconds'] >= ACTION_BASE
        if scene['kind'] == 'establish': assert scene['render_seconds'] >= ESTABLISH_BASE
    # Cay's measured film: one line per lip-sync shot, layout 17.
    text, cast = cs.TEXTS['cay_pingpong']
    title, beats, plines, _ = sp.parse(text, cast)
    ping = sp.assemble(title, None, {'title': 'x'}, sp.ensure_action(sp.shots(title, beats, plines, cast, 13), 60), {'shots': []}, PEOPLE['cay_pingpong'], {}, 13)
    plan_seconds(ping, 60, 25)
    film = audio_layout([ping], cs.timed_lines(ping), 60, 25)[0]
    with capsys.disabled():
        print(f"\nLippenfenster: 0.17-Film (Ping-Pong, Layout 17) {film['talk_windows']}, Redeblöcke mit Layout 17 {old['talk_windows']}, "
              f"Redeblöcke mit Layout 18 {report['talk_windows']} (gespart gegenüber Layout 17: {old['talk_windows'] - report['talk_windows']}, "
              f"gegenüber dem 0.17-Film: {film['talk_windows'] - report['talk_windows']}); GPU etwa {film['talk_windows'] * 2.25:.1f} → "
              f"{report['talk_windows'] * 2.25 + 0.8 * sum(-(-s['render_seconds'] // 5) for s in scenes if s['kind'] != 'line'):.1f} min")
        print('Einstellungen Layout 18: ' + ', '.join(f"{s['kind'][:5]} {s['render_seconds']:.2f}s" for s in scenes))
    assert film['talk_windows'] - report['talk_windows'] >= 8


def test_reaction_absorbs_extra_time_only_up_to_its_cap():
    scenes = [{'kind': 'line', 'seconds': 4}, {'kind': 'reaction', 'seconds': 3, 'voice_of': 'A', 'cast': ['B']}, {'kind': 'action', 'seconds': 4}]
    lines = [{'episode': 0, 'scene': 0, 'turn': 0, 'duration': 2.0, 'pause_after': .15},
             {'episode': 0, 'scene': 1, 'turn': 0, 'duration': 1.5, 'pause_after': .15}]
    episode = {'scenes': scenes, 'dialogue_mode': 'rich'}
    report = audio_layout([episode], lines, 30, 25, version=18)[0]
    assert scenes[1]['render_seconds'] == pytest.approx(REACTION_CAP, abs=.04) and scenes[2]['render_seconds'] > 20
    assert report['talk_windows'] == rendered_windows(scenes[0]['render_seconds']) and report['silent_shots'] == 1
    # Without an action shot the rest goes back to the speaking shot, never past the reaction cap.
    episode = {'scenes': scenes[:2], 'dialogue_mode': 'rich'}
    audio_layout([episode], copy.deepcopy(lines), 12, 25, version=18)
    assert scenes[1]['render_seconds'] == pytest.approx(REACTION_CAP, abs=.04) and scenes[0]['render_seconds'] > 7
    # Short film: the reaction keeps its own length (voice plus a visible beat), at least 1.4 s.
    episode = {'scenes': [{'kind': 'line'}, {'kind': 'reaction', 'voice_of': 'A', 'cast': ['B']}], 'dialogue_mode': 'rich'}
    short = [{'episode': 0, 'scene': 0, 'turn': 0, 'duration': 2.0}, {'episode': 0, 'scene': 1, 'turn': 0, 'duration': .5}]
    audio_layout([episode], short, 1, 25, version=18)
    assert episode['scenes'][1]['render_seconds'] == pytest.approx(REACTION_MIN, abs=.04)


class Voicing:
    """Quality.quality_voices() for a project whose lines are already spoken (audio_only):
    layout pin, timing and the mix order, no speech model."""
    def __init__(self, folder):
        self.posts = []; self.folder_path = folder
    def apply_pending(self, d): return False
    def paused(self, rid): return False
    def save(self, d): pass
    def folder(self, d): return self.folder_path
    def asset(self, aid, kind=None): raise AssertionError('no music or recordings in this test')
    def queue_post(self, d, kind, ei, spec): self.posts.append((kind, ei, spec))


def voiced(episode, lines, timing=None, **extra):
    d = {'id': 'v' * 32, 'idea': {'duration': 60, 'episodes': 1, 'fps': 25, 'participants': [], 'lip_sync': 'audio'},
         'plan': {'cast': [{'name': n} for n in cs.CAST], 'mood': 'playful'}, 'episodes': [episode], 'lines': lines,
         'audio_only': True, 'voice_policy': 18, **extra}
    if timing is not None: d['timing'] = timing
    return d


def speak(lines, folder):
    """A real WAV of the planned length for every line (sine tones, 24 kHz mono)."""
    import hashlib, subprocess
    folder.mkdir(parents=True, exist_ok=True)
    for i, line in enumerate(lines):
        f = folder / f'l{i}.wav'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=frequency={180 + 15 * i}:duration={line["duration"]}',
                        '-ar', '24000', '-ac', '1', str(f)], check=True)
        line.update(file=str(f), sha256=hashlib.sha256(f.read_bytes()).hexdigest())
    return lines


def test_new_sound_version_gets_layout_18_and_the_real_mix_accepts_it(tmp_path):
    """factory_quality pins the layout once: a project without any sound version gets 18. The mix
    order then goes through the real FFmpeg mix with its checks ("Dialog passt nicht zur
    Szenendauer", per-line speech check): every off-screen line stays inside its reaction shot."""
    import shutil
    if not shutil.which('ffmpeg'): pytest.skip('ffmpeg fehlt')
    from factory_quality import Quality
    from factory_audio import mix
    _, episode = blocks_episode(); plan_seconds(episode, 60, 25)
    studio = Voicing(tmp_path); d = voiced(episode, speak(cs.timed_lines(episode), tmp_path / 'lines'))
    asyncio.run(Quality.quality_voices(studio, d))
    assert d['timing_layout'] == 18 and d['timing'][0]['layout'] == 18 and d['timing'][0]['reaction_shots'] == 2 and d['state'] == 'audio_mixing'
    (kind, ei, spec), = studio.posts
    reaction = next(i for i, s in enumerate(d['episodes'][0]['scenes']) if s['kind'] == 'reaction')
    assert [l['speaker'] for l in spec['scenes'][reaction]['lines']] == ['Mr. Krabs']          # the voice stays in the mix
    result = mix(tmp_path / 'mix', spec['scenes'], spec['mood'], None, {'music_mode': 'off'})
    assert Path(result).is_file() and json.loads((tmp_path / 'mix' / 'Sprachpruefung.json').read_text())['checked'] == len(d['lines'])


def test_existing_sound_versions_keep_their_layout(tmp_path):
    from factory_audio import layout
    from factory_quality import Quality
    text, cast = cs.TEXTS['cay_pingpong']
    title, beats, lines, _ = sp.parse(text, cast)
    ping = sp.assemble(title, None, {'title': 'x'}, sp.ensure_action(sp.shots(title, beats, lines, cast, 13), 60), {'shots': []}, PEOPLE['cay_pingpong'], {}, 13)
    plan_seconds(ping, 60, 25)
    for timing, expected in (([{'seconds': 60, 'layout': 17}], 17), ([{'seconds': 60, 'silent_shots': 4}], 17), ([{'seconds': 60}], 16)):
        d = voiced(copy.deepcopy(ping), cs.timed_lines(ping), timing)
        asyncio.run(Quality.quality_voices(Voicing(tmp_path), d))
        reference, reference_lines = copy.deepcopy(ping), cs.timed_lines(ping)
        report = layout([reference], reference_lines, 60, 25, expected)
        assert d['timing_layout'] == expected and d['timing'] == report, expected
        assert d['episodes'][0]['scenes'] == reference['scenes'] and d['lines'] == reference_lines
    # Pinned: a project re-voiced later keeps 18 even though it now has a sound version.
    _, episode = blocks_episode(); plan_seconds(episode, 60, 25)
    d = voiced(episode, cs.timed_lines(episode), [{'seconds': 60, 'layout': 18}], timing_layout=18)
    asyncio.run(Quality.quality_voices(Voicing(tmp_path), d))
    assert d['timing'][0]['layout'] == 18


# --- Part 5: downstream ---------------------------------------------------------------------

def test_render_order_and_lip_sync_lock_skip_reactions():
    pytest.importorskip('fastapi')
    from factory import render_order
    scenes = [{'kind': 'line'}, {'kind': 'reaction'}, {'kind': 'action'}, {'kind': 'line'}]
    lines = [{'episode': 0, 'scene': 0}, {'episode': 0, 'scene': 1}, {'episode': 0, 'scene': 3}]
    assert [i for i, _ in render_order(scenes, 0, lines)] == [0, 3, 1, 2]
    assert off_screen(scenes[1]) and not off_screen(scenes[0]) and not off_screen('a')


class Movies:
    """Factory.movies() with ComfyUI, ffmpeg and the database replaced."""
    def __init__(self, folder):
        self.renders = []; self.posts = []; self.folder_path = folder; self.g = {'RUNTIME': folder, 'ROOT': folder}; self.comfy = folder
    async def object_info(self): return {}
    def autopilot_on(self, d): return True
    def post_rows(self, d, kind): return []
    def rows(self, query, args=()): return [{'output': '/img.png', 'sha256': 'h'}]
    def path(self, p): return Path(p)
    def stage(self, p): return 'staged/' + Path(str(p)).name
    def paused(self, rid): return False
    def save(self, d): pass
    def folder(self, d): return self.folder_path
    def asset(self, aid, kind=None): raise AssertionError('no music in this test')
    def queue_post(self, d, name, ei, spec): self.posts.append((name, spec))
    async def render(self, d, key, graph, video=False):
        self.renders.append((key, graph)); return {'id': key, 'output': f'/clips/{len(self.renders)}.mp4', 'sha256': 'c' * 64}


def movie_project():
    cast = [{'name': 'SpongeBob', 'appearance': 'yellow sponge'}, {'name': 'Mr. Krabs', 'appearance': 'red crab'}]
    scene = lambda kind, who, seconds, **extra: {'kind': kind, 'cast': who, 'render_seconds': seconds, 'selected': 's' * 32, 'camera': 'medium shot',
                                                 'action': 'Szene in der Höhle.', 'motion': ['moves'], 'animation_prompt': 'moves', **extra}
    episode = {'title': 'Folge', 'story_policy': 14, 'scenes': [
        scene('line', ['SpongeBob'], 4.0), scene('reaction', ['SpongeBob'], 6.0, voice_of='Mr. Krabs', animation_prompt='listens in silence with lips closed, a small nod'),
        scene('action', ['SpongeBob', 'Mr. Krabs'], 3.2), scene('line', ['Mr. Krabs'], 3.0)]}
    line = lambda si, who: {'episode': 0, 'scene': si, 'turn': 0, 'speaker': who, 'offset': .08, 'duration': 2.0, 'file': '/l.wav', 'sha256': 'x'}
    return {'id': 'r' * 32, 'idea': {'duration': 15, 'fps': 25, 'quality': 'balanced', 'lip_sync': 'audio'}, 'prompt_policy': 17,
            'plan': {'style': 'clay', 'cast': cast, 'mood': 'playful'}, 'episodes': [episode], 'exports': [],
            'lines': [line(0, 'SpongeBob'), line(1, 'Mr. Krabs'), line(3, 'Mr. Krabs')],
            'timing': [{'seconds': 16.2}], 'timing_policy': 3, 'timing_fps': 25, 'audio_revision': 1, 'previews': []}


def run_movies(monkeypatch, tmp_path, d):
    factory = pytest.importorskip('factory')
    import render_studio
    import wan_text_encoder
    calls = {'talk': [], 'motion': []}
    def audio_graph(info, image, audio, prompt, seed, duration, quality, **kw):
        calls['talk'].append((prompt, duration)); return {'talk': [image, audio, prompt, duration]}
    def motion_graph(image, prompt, seed, negative, models, duration, quality):
        calls['motion'].append((prompt, duration)); return {'motion': [image, prompt, duration]}
    monkeypatch.setattr(render_studio, 'audio_graph', audio_graph)
    monkeypatch.setattr(render_studio, 'dialogue_window', lambda lines, start, duration, path: str(path))
    monkeypatch.setattr(wan_text_encoder, 'validate_selected', lambda comfy, clip: None)
    monkeypatch.setattr(factory, 'video_models', lambda info, comfy: {'fast_loras': True, 'clip': 'clip'})
    monkeypatch.setattr(factory, 'motion_graph', motion_graph)
    monkeypatch.setattr(factory, 'file_hash', lambda p: 'h')
    monkeypatch.setattr(factory, 'ff', lambda args: None)
    monkeypatch.setattr(factory.turbo, 'attention', lambda runtime, info: 'sdpa')
    fake = Movies(tmp_path)
    asyncio.run(factory.Factory.movies(fake, d))
    return fake, calls


def test_movies_renders_a_reaction_as_silent_motion_and_keeps_its_voice(monkeypatch, tmp_path):
    d = movie_project()
    fake, calls = run_movies(monkeypatch, tmp_path, d)
    # Lip-sync only for the two speaking shots (probe call first), all of them before any motion.
    assert [p for p, _ in calls['talk']][0] == 'check' and len(calls['talk']) == 3
    keys = [k.split(':')[2] for k, _ in fake.renders]
    assert keys == ['0', '3', '1', '1', '2']                     # the 6 s reaction is two motion clips of 3 s, no 15 s talk prompt
    reaction_prompts = [p for p, _ in calls['motion'][:2]]
    assert all('SpongeBob listens in silence' in p and 'lips stay closed' in p and 'Krabs' not in p for p in reaction_prompts)
    assert 'Every mouth stays closed the whole time' in calls['motion'][2][0]
    export = next(spec for name, spec in fake.posts if name == 'export')
    assert [l['speaker'] for l in export['scenes'][1]['lines']] == ['Mr. Krabs']      # the voice stays in the mix
    assert [c['seconds'] for c in export['scenes'][1]['clips']] == [3.0, 3.0]


def test_movies_refuses_a_reaction_that_shows_its_speaker(monkeypatch, tmp_path):
    d = movie_project()
    d['lines'][1]['speaker'] = 'SpongeBob'
    with pytest.raises(RuntimeError, match='Reaktion zeigt die sprechende Figur'):
        run_movies(monkeypatch, tmp_path, d)


def test_progress_counts_a_reaction_as_motion_clips():
    pytest.importorskip('fastapi')
    from factory_progress import RenderProgress

    class F:
        def rows(self, *a): return []
    progress = RenderProgress(F())
    d = movie_project(); d.update(state='rendering', paused=False)
    assert progress.snapshot(d)['total'] == 1 + 2 + 1 + 1        # talk 4 s: 1 prompt; reaction 6 s: 2 motion clips
    d['episodes'][0]['scenes'][1]['kind'] = 'line'
    assert progress.snapshot(d)['total'] == 1 + 1 + 1 + 1        # the same shot as lip-sync: one 15 s prompt


class Editing:
    def __init__(self, d):
        self.docs = {d['id']: copy.deepcopy(d)}; self.busy = None
    def get(self, rid): return copy.deepcopy(self.docs[rid])
    def save(self, d): self.docs[d['id']] = copy.deepcopy(d)


def route(app, path, method):
    return next(r.endpoint for r in app.routes if getattr(r, 'path', '') == path and method in (getattr(r, 'methods', None) or set()))


def app_text(studio, tmp_path):
    """Factory.routes() with only its own routes (the editor, quality and library routes are other tests)."""
    import fastapi
    factory = pytest.importorskip('factory')
    app = fastapi.FastAPI()
    studio.editor_routes = studio.quality_routes = studio.library_routes = lambda app: None
    studio.g = {'RUNTIME': tmp_path}
    factory.Factory.routes(studio, app)
    return app


def editing_project():
    d = movie_project(); d['state'] = 'voice_review'
    d['episodes'][0]['scenes'].append({'kind': 'establish', 'cast': ['SpongeBob', 'Mr. Krabs'], 'action': 'Weite Ansicht der Höhle.', 'dialogues': []})
    for s in d['episodes'][0]['scenes']: s.setdefault('dialogues', [])
    return d


def test_dialogue_editor_keeps_a_reaction_on_its_off_screen_voice(tmp_path):
    fastapi = pytest.importorskip('fastapi')
    from fastapi import HTTPException
    from factory_models import SceneDialogueEdit
    from factory_quality import Quality
    app = fastapi.FastAPI(); studio = Editing(editing_project()); Quality.quality_routes(studio, app)
    edit = route(app, '/api/factory/{rid}/dialogues', 'PUT'); rid = 'r' * 32
    body = lambda scene, who: SceneDialogueEdit(episode=0, scene=scene, action=studio.get(rid)['episodes'][0]['scenes'][scene]['action'],
                                                dialogues=[{'speaker': who, 'text': 'Raus hier, sofort!', 'emotion': 'wütend'}])
    with pytest.raises(HTTPException) as refused:
        asyncio.run(edit(rid, body(1, 'SpongeBob')))                       # the listener in the frame never speaks
    assert refused.value.status_code == 400 and 'hört SpongeBob nur zu' in refused.value.detail and 'Mr. Krabs' in refused.value.detail
    d = asyncio.run(edit(rid, body(1, 'Mr. Krabs')))
    assert d['episodes'][0]['scenes'][1]['dialogues'][0]['speaker'] == 'Mr. Krabs' and d['state'] == 'voicing'
    reopen = lambda: studio.docs[rid].update(state='voice_review')
    reopen()
    for who in ('SpongeBob', 'Mr. Krabs'):                                  # a wide establishing shot stays silent
        with pytest.raises(HTTPException) as refused:
            asyncio.run(edit(rid, body(4, who)))
        assert refused.value.status_code == 400 and 'Totale' in refused.value.detail
    with pytest.raises(HTTPException) as refused:
        asyncio.run(edit(rid, body(0, 'Mr. Krabs')))                       # unchanged: a speaking shot needs its visible speaker
    assert refused.value.detail == 'Sprecher muss zur Besetzung der Szene gehören.'
    d = asyncio.run(edit(rid, body(0, 'SpongeBob')))
    assert d['episodes'][0]['scenes'][0]['dialogues'][0]['speaker'] == 'SpongeBob'
    # The older single-line editor follows the same rule.
    reopen(); text = route(app_text(studio, tmp_path), '/api/factory/{rid}/text', 'PUT')
    from factory_models import SceneText
    line = lambda scene, who: SceneText(episode=0, scene=scene, action=studio.get(rid)['episodes'][0]['scenes'][scene]['action'], dialogue='Raus hier, sofort!', speaker=who)
    for scene, who in ((1, 'SpongeBob'), (4, 'SpongeBob')):
        with pytest.raises(HTTPException) as refused:
            asyncio.run(text(rid, line(scene, who)))
        assert refused.value.status_code == 400
    assert asyncio.run(text(rid, line(1, 'Mr. Krabs')))['episodes'][0]['scenes'][1]['dialogue'] == 'Raus hier, sofort!'


def test_story_rules_and_dialogue_additions_respect_reactions():
    from story_policy import dialogue_errors
    from lipsync_shots import split_episode
    from dialogue_density import apply_additions
    d = editing_project(); episode = d['episodes'][0]
    episode['scenes'][1]['dialogues'] = [{'speaker': 'Mr. Krabs', 'text': 'Raus hier!', 'emotion': 'wütend'}]
    episode['scenes'][0]['dialogues'] = [{'speaker': 'SpongeBob', 'text': 'Hallo!', 'emotion': 'ruhig'}]
    assert dialogue_errors(episode) == []
    unpictured = {k: v for k, v in episode['scenes'][1].items() if k not in ('selected', 'variants')}
    assert split_episode({'scenes': [unpictured]})['scenes'] == [unpictured]                        # never split into a talking shot
    silent_wide = copy.deepcopy(episode); silent_wide['scenes'][4]['dialogues'] = [{'speaker': 'SpongeBob', 'text': 'Hallo!', 'emotion': 'ruhig'}]
    assert any('Totale' in e for e in dialogue_errors(silent_wide))
    wrong = copy.deepcopy(episode); wrong['scenes'][1]['dialogues'][0]['speaker'] = 'SpongeBob'
    assert dialogue_errors(wrong) and 'Reaktion' in dialogue_errors(wrong)[0]
    added = apply_additions(episode, {'scenes': [{'scene': 2, 'lines': [{'speaker': 'SpongeBob', 'text': 'Ich hör ja zu!', 'emotion': 'ruhig', 'pause_after': .2}]},
                                                 {'scene': 1, 'lines': [{'speaker': 'SpongeBob', 'text': 'Noch ein Satz von mir.', 'emotion': 'ruhig', 'pause_after': .2}]}]},
                            ['SpongeBob', 'Mr. Krabs'], 'off')
    assert added['scenes'][1]['dialogues'] == episode['scenes'][1]['dialogues'] and len(added['scenes'][0]['dialogues']) == 2
