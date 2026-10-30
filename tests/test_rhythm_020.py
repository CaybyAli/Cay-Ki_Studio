"""0.20 rhythm and physical acting for projects pinned with shot_policy 20 (new projects of the new app).

Cay after 0.19 ("Villa der süßen Lügen", Folge 1): "Die Figuren stehen immer noch zu viel still. Das Schema ist
zu monoton (1 Person spricht – Schnitt – nächste Person spricht). Hier muss mehr Spannung rein." His reference
films cut every 1.2 s between close-ups, over-the-shoulder shots, listeners, hands and props.

Measured here on his two real scripts (Weißes Gold, tests/fixtures/Weisses_Gold_Drehbuch.md, and Villa der süßen
Lügen, tests/fixtures/Villa_Drehbuch_020.md) with the speech rate of his films: the 0.19 cut against the 0.20 cut.
Projects without the pin keep exactly the 0.19 cut, prompts and graphs (also tests/test_compat_016.py and the
fixtures of 0.17/0.18). How stills and clips look can only be judged on Cay's GPU and screen.
"""
import asyncio
import copy
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
import studio_fakes  # noqa: E402  (puts cay_studio_app on the path)
import plan_fakes  # noqa: E402
import cut_samples as cs  # noqa: E402
import own_script  # noqa: E402
import screenplay as sp  # noqa: E402
import shot_design as sd  # noqa: E402
import cast_design  # noqa: E402
from factory_timing import audio_layout, plan_seconds, off_screen  # noqa: E402

GOLD = (ROOT / 'tests/fixtures/Weisses_Gold_Drehbuch.md').read_text(encoding='utf-8')
VILLA = (ROOT / 'tests/fixtures/Villa_Drehbuch_020.md').read_text(encoding='utf-8')
RHYTHM = {'rhythm': True, 'limit': sp.OWN_MAX_SHOTS}


def episodes(text, rhythm):
    """Every episode of Cay's script as the planner assembles it (no planner pictures), laid out with layout 18 and
    the 0.19 native silent shots, speech at 2.6 words per second as in his films."""
    r = own_script.read(text); names = [f['name'] for f in r['figures']]; cast = [{'name': n, 'appearance': 'x'} for n in names]; out = []
    for ep in r['episodes']:
        title, beats, lines, _ = sp.parse(ep['text'], names, own=True)
        e = sp.assemble(title, {}, {'title': 'x'}, sp.shots(title, beats, lines, names, **(RHYTHM if rhythm else {})), {}, cast, {})
        e['own_script'] = True; plan_seconds(e, r['duration'], 25); timed = cs.timed_lines(e)
        report = audio_layout([e], timed, r['duration'], 25, version=18, shots=True)[0]
        out.append((e, timed, report, lines))
    return out


def gpu_frames(scene, talk):
    """Frames the GPU computes for one shot: fitted InfiniteTalk windows (render_policy 19) or Wan frames."""
    from render_studio import talk_window_plan
    from studio_quality_policy import scene_segments
    T = scene['render_seconds']
    if talk: return sum(w + (n - 1) * (w - 9) for w, n in (talk_window_plan(x) for x in scene_segments(T, 25, True)))
    if sd.native(scene, T, 25): return sum(sd.native_frames(x, 25) for x in scene_segments(T, 25, False, native=True))
    return sum(4 * math.ceil(x * 16 / 4) + 1 for x in scene_segments(T, 25, False))


def measure(text, rhythm):
    m = {'shots': 0, 'seconds': 0., 'dialogue': [], 'listener': 0, 'lip_sync': 0., 'talk_frames': 0, 'wan_frames': 0, 'runs': 0,
         'same_framing': 0, 'inserts': [], 'cut_ins': 0}
    for e, timed, report, _ in episodes(text, rhythm):
        scenes = e['scenes']; plan = sd.plan(e); talkers = {l['scene'] for l in timed if not off_screen(scenes[l['scene']])}
        m['shots'] += len(scenes); m['seconds'] += report['seconds']
        run, previous = 0, None
        for i, s in enumerate(scenes):
            talk = i in talkers; kind = s.get('kind')
            m['talk_frames' if talk else 'wan_frames'] += gpu_frames(s, talk)
            if talk: m['lip_sync'] += s['render_seconds']
            if kind in ('line', 'reaction') or s.get('insert'):
                m['dialogue'].append(s['render_seconds']); m['listener'] += kind != 'line'
                # a long one-sentence talking shot cuts in closer at a caption change (shot_design.camera, 'cut_in')
                m['cut_ins'] += bool(rhythm and kind == 'line' and len(s['dialogues']) == 1 and s['render_seconds'] >= sd.CUT_IN_SECONDS)
            if s.get('insert'): m['inserts'].append((s['insert'], s.get('prop')))
            others = {n for x in scenes if x.get('location') == s.get('location') for n in x['cast']} - set(s['cast'])
            who = s['cast'][0] if kind == 'line' and s['cast'] else None
            run = run + 1 if who and who == previous else (1 if who else 0); previous = who
            if run > 2 and others: m['runs'] += 1
            if i and plan[i]['type'] == plan[i - 1]['type']: m['same_framing'] += 1
    n = len(m['dialogue'])
    return {**m, 'average': sum(m['dialogue']) / n, 'perceived': sum(m['dialogue']) / (n + m['cut_ins']), 'listener_share': m['listener'] / n,
            'lip_per_second': m['lip_sync'] / m['seconds'], 'talk_per_second': m['talk_frames'] / m['seconds'],
            'frames_per_second': (m['talk_frames'] + m['wan_frames']) / m['seconds']}


# --- Projects without the pin: exactly as before -----------------------------------------------------------

@pytest.mark.parametrize('name', sorted(cs.TEXTS))
def test_without_the_pin_the_cut_is_the_019_cut(name):
    text, cast = cs.TEXTS[name]
    title, beats, lines, _ = sp.parse(text, cast)
    old = sp.block_cut(beats, lines, cast)
    assert sp.shots(title, beats, lines, cast) == old and sp.shots(title, beats, lines, cast, rhythm=False) == old
    assert not any(k in s for s in old for k in ('shoulder', 'insert', 'piece'))
    new = sp.shots(title, beats, lines, cast, **RHYTHM)
    assert new != old and sp.shots(title, beats, lines, cast, sp.LEGACY_POLICY, rhythm=True) == sp.shots(title, beats, lines, cast, sp.LEGACY_POLICY)


def test_old_requests_stay_019_and_the_new_app_pins_020(tmp_path, monkeypatch):
    f = studio_fakes.factory(tmp_path, monkeypatch); client = studio_fakes.client(f)
    body = {'idea': 'Zwei Kollegen streiten um den letzten Keks. Am Ende hat ihn die Praktikantin.', 'duration': 30, 'episodes': 1, 'characters': 'invent'}
    old = client.post('/api/factory', json={**body, 'request_key': 'a' * 32}).json()
    new = client.post('/api/factory', json={**body, 'request_key': 'b' * 32, 'rhythm': 20}).json()
    assert old['shot_policy'] == 19 and new['shot_policy'] == 20
    assert 'rhythm' not in old['idea'] and 'rhythm' not in new['idea'] and dict(old['idea'], request_key='') == dict(new['idea'], request_key='')
    assert client.post('/api/factory', json={**body, 'request_key': 'c' * 32, 'rhythm': 19}).status_code == 422
    app = (ROOT / 'cay_studio_app/web/app2/app.js').read_text(encoding='utf-8')
    assert app.count('rhythm: 20') + app.count('body.rhythm = 20') == 2          # both create paths of the new app ask for it


def test_old_texts_and_graphs_without_the_pin():
    """The 0.19 motion text, still text and export fields of a scene are the same with and without the module's new fields
    as long as the project is not pinned with 20."""
    scene = {'kind': 'reaction', 'cast': ['SpongeBob'], 'voice_of': 'Mr. Krabs', 'emotion': 'drohend', 'dialogues': [{'speaker': 'Mr. Krabs', 'text': 'x', 'emotion': 'drohend'}]}
    assert sd.motion_prompt('clay', 'moves', scene, [], 3) == sd.motion_prompt('clay', 'moves', dict(scene, shoulder='Mr. Krabs'), [], 3)
    assert 'collar' not in sd.motion_prompt('clay', 'moves', scene, [], 3)
    line = {'kind': 'line', 'cast': ['SpongeBob'], 'variants': [{'id': 'a', 'shot': 'cu'}], 'selected': 'a'}
    assert sd.export_fields({'shot_policy': 19}, line) == {'shot': 'cu'} and sd.export_fields({'shot_policy': 20}, line) == {'shot': 'cu', 'cut_in': True}
    assert sd.export_fields({}, line) == {}
    assert sd.still_names({'cast': ['A']}, 'ots') == ['A'] and sd.still_names({'cast': ['A'], 'shoulder': 'B'}, 'cu') == ['A']


# --- The cut on Cay's scripts ------------------------------------------------------------------------------

@pytest.mark.parametrize('text,most', [(GOLD, 2.3), (VILLA, 2.7)], ids=['weisses_gold', 'villa'])
def test_cays_scripts_get_a_faster_cut_with_listeners(text, most):
    before, after = measure(text, False), measure(text, True)
    # 0.19: one speaker per shot, nobody else in a dialogue (Villa: 100 dialogue shots, 2 of them a listener, 3.9 s each).
    assert before['listener_share'] < .05 and after['listener_share'] >= .35
    assert after['average'] <= most and after['average'] < before['average'] * .9 and after['perceived'] <= 2.5
    assert after['runs'] == 0 and after['same_framing'] == 0
    assert after['shots'] > before['shots'] * 1.15


def test_inserts_show_the_props_the_lines_name():
    props = {p for k, p in measure(VILLA, True)['inserts'] if k == 'prop'}
    assert {'Foto', 'Geld', 'Aufnahme'} <= props, props
    kinds = {k for k, _ in measure(VILLA, True)['inserts'] + measure(GOLD, True)['inserts']}
    assert kinds == {'prop', 'hands', 'eyes'}
    for e, _, _, _ in episodes(VILLA, True):
        scenes = e['scenes']
        for i, s in enumerate(scenes):
            if not s.get('insert'): continue
            assert 0 < i < len(scenes) - 1 and s['kind'] == 'action' and not s['dialogues'] and len(s['cast']) == 1
            assert scenes[i - 1]['dialogues'] and scenes[i + 1]['dialogues'] and not scenes[i + 1].get('insert')
            assert 21 <= round(s['render_seconds'] * 25) <= 33 and round(s['render_seconds'] * 25) % 4 == 1


def test_every_word_is_spoken_once_in_order_and_pieces_end_at_sentences():
    for text in (GOLD, VILLA):
        for e, timed, _, lines in episodes(text, True):
            said = [l['text'] for l in lines if l['kind'] == 'line']
            heard = [l['text'] for s in e['scenes'] for l in s['dialogues']]
            assert ' '.join(heard) == ' '.join(said)
            assert all(re.search(r'[.!?…]["“”»]?$', h) or h in said for h in heard)
            for s in e['scenes']:
                if s['kind'] == 'reaction': assert s['voice_of'] not in s['cast'] and s.get('shoulder') in (None, s['voice_of'])
                if s['kind'] == 'line' and s['dialogues']: assert s['cast'] == [s['dialogues'][0]['speaker']] and s.get('shoulder') != s['cast'][0]


def test_split_line_at_sentence_ends():
    from shot_rhythm import split_line
    assert split_line('Vorsicht, Niko. Valentina hört jedes Wort.') == ['Vorsicht, Niko.', 'Valentina hört jedes Wort.']
    assert split_line('Sia? Was machst du hier?') == ['Sia?', 'Was machst du hier?']
    assert split_line('Lass sie doch mal in Ruhe, Valentina. Du bist nicht mein Sprachrohr. Kümmere dich lieber um dich selbst.') == [
        'Lass sie doch mal in Ruhe, Valentina.', 'Du bist nicht mein Sprachrohr.', 'Kümmere dich lieber um dich selbst.']
    assert split_line('Falls Ben dir wehtut, sitze ich an der Feuerstelle neben dir. Versprochen.') == ['Falls Ben dir wehtut, sitze ich an der Feuerstelle neben dir. Versprochen.']
    assert split_line('Mr. Krabs zahlt am 7. Mai. Das weiß jeder hier.') == ['Mr. Krabs zahlt am 7. Mai.', 'Das weiß jeder hier.']
    assert split_line('Ich bin die Ruhe selbst, Schatz.') == ['Ich bin die Ruhe selbst, Schatz.']


def test_gpu_cost_per_film_second_is_not_higher():
    """InfiniteTalk frames cost more than Wan frames (audio guidance on top of the same 14B model): fewer lip-sync
    frames and not more frames in all per film second means the GPU time per film second does not grow."""
    for text in (GOLD, VILLA):
        before, after = measure(text, False), measure(text, True)
        assert after['talk_per_second'] < before['talk_per_second'] * .8
        assert after['frames_per_second'] <= before['frames_per_second']
        assert after['lip_per_second'] < before['lip_per_second']


def test_ai_screenplays_get_the_rhythm_within_the_shot_limit():
    for name, (text, cast) in cs.TEXTS.items():
        title, beats, lines, _ = sp.parse(text, cast)
        cut = sp.ensure_action(sp.shots(title, beats, lines, cast, rhythm=True), 60)
        assert len(cut) <= sp.MAX_SHOTS and ' '.join(l['text'] for s in cut for l in s['lines']) == ' '.join(l['text'] for l in lines if l['kind'] == 'line')
    # A screenplay at the shot limit: pieces and inserts never push it over.
    long = 'TITEL: Lang\n# 1 | Küche | Streit\n' + '\n'.join(f'{"OMA" if i % 2 else "TIM"} [wütend]: Das ist Satz {i}. Und noch ein Satz dazu, Geld!' for i in range(42))
    title, beats, lines, _ = sp.parse(long, ['Oma', 'Tim'])
    assert len(sp.ensure_action(sp.shots(title, beats, lines, ['Oma', 'Tim'], rhythm=True), 60)) <= sp.MAX_SHOTS


# --- Pictures: two figures in one frame ---------------------------------------------------------------------

def test_an_over_the_shoulder_still_gets_both_reference_images(monkeypatch):
    factory = pytest.importorskip('factory')
    monkeypatch.setattr(factory, 'validate_nodes', lambda info: {})
    e = episodes(VILLA, True)[0][0]
    cast = [{'name': n, 'appearance': f'{n} look'} for n in {n for s in e['scenes'] for n in s['cast'] + [s.get('shoulder')] if n}]
    for s in e['scenes']: s['variants'] = []
    d = {'id': 'p' * 32, 'idea': {'participants': [], 'examples': []}, 'plan': {'style': 'glossy 3D animation', 'cast': cast}, 'episodes': [e],
         'shot_policy': 20, 'cast_refs': {p['name']: f'/refs/{p["name"]}.png' for p in cast}}
    calls = []
    class Pictures:
        async def render(self, document, key, graph, video=False):
            calls.append({'key': key, 'refs': [n['inputs']['image'] for n in graph.values() if n['class_type'] == 'LoadImage'],
                          'prompt': next(n['inputs']['text'] for n in graph.values() if n['class_type'] == 'CLIPTextEncode')})
            return {'id': key, 'output': f'/out/{key}.png'}
        def stage(self, path): return 'staged/' + Path(path).name
        async def object_info(self): return {}
        def asset(self, aid, kind=None): return {'path': f'/assets/{aid}.png'}
        def save(self, d): pass
        def paused(self, rid): return False
        def apply_pending(self, d): return False
    asyncio.run(factory.Factory.pictures(Pictures(), d))
    by_key = {c['key']: c for c in calls}
    shoulders = [(i, s) for i, s in enumerate(e['scenes']) if s.get('shoulder')]
    assert shoulders
    for i, s in shoulders:
        ots = next(v for v in s['variants'] if v['shot'] == 'ots'); call = by_key[ots['key']]
        front = s['shoulder']; face = s['cast'][0]
        assert call['refs'] == [f'staged/{face}.png', f'staged/{front}.png']
        assert call['prompt'].startswith(f"Over-the-shoulder shot: in the near foreground the out-of-focus back of {front}'s head")
        assert f'{face} faces the camera' in call['prompt'] and f'{front} only from behind' in call['prompt']
        other = next(v for v in s['variants'] if v['shot'] != 'ots')            # the second variant: the face alone, one reference
        assert by_key[other['key']]['refs'] == [f'staged/{face}.png'] and front not in by_key[other['key']]['prompt'].split('Reference image')[0]
    insert = next(s for s in e['scenes'] if s.get('insert'))
    call = by_key[insert['variants'][0]['key']]
    assert call['prompt'].startswith('Extreme close-up insert') and len(call['refs']) == 1


# --- Movement ---------------------------------------------------------------------------------------------

def test_reactions_and_inserts_act_out_the_conflict():
    react = lambda mood, heard='ruhig', **x: sd.motion_prompt('clay', 'listens', {'kind': 'reaction', 'cast': ['Ben'], 'voice_of': 'Sia', 'emotion': mood,
                                                                                  'dialogues': [{'speaker': 'Sia', 'text': 'x', 'emotion': heard}], **x}, [], 0, rhythm=True)
    assert 'backs away' in react('ängstlich') and 'door' in react('ängstlich') and 'handheld' in react('ängstlich')
    assert 'leans back, spreads the arms' in react('triumphierend') and 'slams' in react('wütend')
    assert 'backs away' in react('ruhig', 'drohend')                         # a calm listener answers a threat with the body
    ots = react('drohend', variants=[{'id': 'v', 'shot': 'ots'}], selected='v', shoulder='Sia')
    assert 'grabs the collar of the figure in the foreground' in ots and "Sia is only seen from behind" in ots and 'lips closed' in ots
    assert 'grabs the collar' not in react('drohend', variants=[{'id': 'v', 'shot': 'cu'}], selected='v', shoulder='Sia')     # not drawn over the shoulder
    insert = lambda kind, mood, **x: sd.motion_prompt('clay', 'moves', {'kind': 'action', 'cast': ['Sia'], 'insert': kind, 'mood': mood, **x}, [], 0, rhythm=True)
    assert "Sia's hand holds the photo up to the camera" in insert('prop', 'triumphierend', prop='Foto') and 'no face' in insert('prop', 'ruhig', prop='Foto')
    assert 'fist' in insert('hands', 'drohend') or 'finger' in insert('hands', 'drohend')
    assert 'the mouth stays out of frame' in insert('eyes', 'ängstlich')
    talk = {'kind': 'line', 'cast': ['Mira'], 'shoulder': 'Ben', 'variants': [{'id': 'v', 'shot': 'ots'}], 'selected': 'v'}
    text = sd.motion_prompt('clay', 'talks', talk, [{'speaker': 'Mira'}], 0, rhythm=True)
    assert "Mira is the only face in the frame" in text and "Ben's face never visible" in text and 'the face stays toward the camera' in text
    assert 'head turn' not in text and 'turns the head' not in text
    plain = sd.motion_prompt('clay', 'talks', dict(talk, shoulder=None), [{'speaker': 'Mira'}], 0)
    assert sd.motion_prompt('clay', 'talks', dict(talk, shoulder=None), [{'speaker': 'Mira'}], 0, rhythm=True) == plain    # talking shots: 0.19 text


def test_inserts_keep_their_second_and_the_minimum_is_met():
    for e, timed, report, _ in episodes(VILLA, True):
        assert report['minimum_met']
        for s in e['scenes']:
            if s.get('insert'): assert s['render_seconds'] in [n / 25 for n in sd.INSERT_FRAMES]
    # A film far too short for its minimum: the extra time goes to other silent shots, never to an insert.
    e = episodes(VILLA, True)[1][0]; timed = cs.timed_lines(e)
    report = audio_layout([e], timed, 120, 25, version=18, shots=True)[0]
    assert report['minimum_met'] and all(s['render_seconds'] * 25 <= 33 for s in e['scenes'] if s.get('insert'))


def test_a_long_talking_shot_cuts_in_at_a_caption_change():
    lines = [{'speaker': 'Sia', 'text_de': 'Dann erzähl doch selbst, warum ihr zusammen im Hotel wart, und zwar jetzt sofort.', 'offset': .08, 'duration': 4.2}]
    scenes = [{'kind': 'line', 'seconds': 4.6, 'lines': lines, 'cut_in': True}]
    zoom = sd.camera(scenes, 0, 0., 25)[0]
    assert 'if(gte(' in zoom and zoom != sd.camera([dict(scenes[0], cut_in=False)], 0, 0., 25)[0]
    assert sd.camera([dict(scenes[0], seconds=2.4, lines=[dict(lines[0], duration=2.)])], 0, 0., 25) == sd.camera(
        [dict(scenes[0], seconds=2.4, lines=[dict(lines[0], duration=2.)], cut_in=False)], 0, 0., 25)


# --- Through planning: an own script and an AI screenplay ---------------------------------------------------

def test_own_script_plans_with_the_rhythm_word_for_word(tmp_path, monkeypatch):
    f = studio_fakes.factory(tmp_path, monkeypatch); client = studio_fakes.client(f)
    text = VILLA.split('## Folge 3')[0]
    d, planner = plan_fakes.plan(f, client, {'request_key': '7' * 32, 'idea': text, 'story': 'script', 'characters': 'provided', 'rhythm': 20}, write=False)
    assert d['shot_policy'] == 20 and d['script']['episodes'][0]['shots'] == len(d['episodes'][0]['scenes'])
    scenes = [s for ep in d['episodes'] for s in ep['scenes']]
    assert any(s['kind'] == 'reaction' for s in scenes) and any(s.get('insert') == 'prop' and s['prop'] == 'Foto' for s in scenes)
    assert any(s.get('shoulder') for s in scenes)
    r = own_script.read(text)
    for ep, own in zip(d['episodes'], r['episodes']):
        said = [l['text'] for l in sp.parse(own['text'], [x['name'] for x in r['figures']], own=True)[2] if l['kind'] == 'line']
        assert ' '.join(l['text'] for s in ep['scenes'] for l in s['dialogues']) == ' '.join(said)
        assert ep['screenplay_stats']['inserts'] == sum(1 for s in ep['scenes'] if s.get('insert'))
    listing = next(c for c in planner.calls if c[1] == 'ShotVisuals')
    assert 'insert = stumme Detailaufnahme' in listing[2]
    assert any(x['role'].startswith('insert:') for x in listing[3]['shots']) and any(x.get('behind') for x in listing[3]['shots'])
    # The duration the film is planned with stays the one of the 0.19 cut (never longer than the new cut).
    assert d['idea']['duration'] == own_script.read(text)['duration']


def test_ai_screenplay_plans_with_the_rhythm(tmp_path, monkeypatch):
    f = studio_fakes.factory(tmp_path, monkeypatch); client = studio_fakes.client(f)
    d, _ = plan_fakes.plan(f, client, {'request_key': '8' * 32, 'idea': 'Zwei Kollegen streiten um den letzten Keks.', 'duration': 30,
                                       'episodes': 1, 'characters': 'invent', 'rhythm': 20, 'writing': 19})
    scenes = d['episodes'][0]['scenes']
    assert d['shot_policy'] == 20 and any(s['kind'] == 'reaction' for s in scenes) and any(s.get('insert') for s in scenes)
    said = [l['text'] for l in sp.parse(plan_fakes.SCREENPLAY, ['Lena', 'Markus'])[2] if l['kind'] == 'line']
    assert ' '.join(l['text'] for s in scenes for l in s['dialogues']) == ' '.join(said)


def test_the_dashboard_imports_the_new_module_without_numpy():
    app = ROOT / 'cay_studio_app'
    code = ("import sys\nfor m in ('numpy','torch','soundfile','torchaudio'): sys.modules[m]=None\n"
            f"sys.path.insert(0,{str(app)!r})\nimport shot_rhythm, screenplay, shot_design\nprint('ok')")
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, cwd=str(app))
    assert r.returncode == 0 and r.stdout.strip() == 'ok', r.stderr[-800:]


def test_numbers_for_the_report(capsys):
    """Not a rule: prints the before/after numbers of Cay's two scripts (pytest -s)."""
    for name, text in (('Weißes Gold', GOLD), ('Villa', VILLA)):
        for label, rhythm in (('0.19', False), ('0.20', True)):
            m = measure(text, rhythm)
            print(json.dumps({'script': name, 'cut': label, 'shots': m['shots'], 'seconds': round(m['seconds'], 1), 'dialogue_shots': len(m['dialogue']),
                              'average': round(m['average'], 2), 'perceived': round(m['perceived'], 2), 'listener_share': round(m['listener_share'], 2),
                              'inserts': len(m['inserts']), 'lip_sync_seconds': round(m['lip_sync'], 1), 'lip_per_second': round(m['lip_per_second'], 3),
                              'talk_frames_per_second': round(m['talk_per_second'], 2), 'frames_per_second': round(m['frames_per_second'], 2)},
                             ensure_ascii=False))


def test_render_a_pinned_project_with_listeners_shoulders_and_a_detail(monkeypatch, tmp_path):
    """Factory.movies with ComfyUI replaced: the detail renders as one native Wan clip of about a second with its own
    text, the listener over Mr. Krabs' shoulder acts with the body, SpongeBob over his shoulder keeps the lip-sync-safe text."""
    import test_shots_019 as t19
    d = t19.movie_project(shot_policy=20)
    v = lambda shot: [{'id': 's' * 32, 'key': 'image:0:0:0:0', 'shot': shot}]
    scenes = d['episodes'][0]['scenes']
    scenes[0].update(shoulder='Mr. Krabs', variants=v('ots'))
    scenes[1].update(shoulder='Mr. Krabs', emotion='ängstlich', variants=v('ots'), render_seconds=2.4)
    scenes[2].update(cast=['Mr. Krabs'], insert='prop', prop='Geld', mood='drohend', render_seconds=29 / 25, variants=v('ecu'))
    d19 = copy.deepcopy(d); d19['shot_policy'] = 19
    fake, calls = t19.run_movies(monkeypatch, tmp_path, d)
    talk = calls['talk'][1]; react, detail = calls['motion'][0], calls['motion'][1]
    assert 'SpongeBob is the only face in the frame' in talk[0] and "Mr. Krabs's face never visible" in talk[0] and talk[2]['suffix'] == sd.TALK_SUFFIX
    assert 'backs away' in react[0] or 'shrinks back' in react[0]
    assert 'Mr. Krabs is only seen from behind' in react[0] and react[2] == {'native': 25} and round(react[1] * 25) == 60
    assert 'Extreme close-up insert of the money' in detail[0] and 'slams' in detail[0] and detail[2] == {'native': 25} and round(detail[1] * 25) == 29
    assert all(spec['shot_policy'] == 20 for _, spec in fake.posts) and fake.posts[-1][1]['scenes'][0].get('cut_in') is True
    # The same project pinned with 19 renders with the 0.19 texts: no body acting, no figure from behind, no cut-in.
    (tmp_path / 'p19').mkdir(); fake19, calls19 = t19.run_movies(monkeypatch, tmp_path / 'p19', d19)
    assert 'only seen from behind' not in calls19['motion'][0][0] and 'only face' not in calls19['talk'][1][0]
    assert 'Extreme close-up insert' not in calls19['motion'][1][0] and 'cut_in' not in fake19.posts[-1][1]['scenes'][0]
