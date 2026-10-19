"""0.19 picture dynamics for projects pinned with shot_policy 19 (new projects only).

Cay after episode 1 of "Preis der Familie" and "Weißes Gold": far too many static frontal medium
shots at eye level, no close-ups, talking heads stand still, silent action barely moves and feels
like slow motion. Measured: 31 of 34 shots frontal, 0 close-ups, 8 of 9 talking shots without any
camera move, every silent shot exactly 3.20 s of 16 fps frames interpolated to 25 fps.

Part 1 pins the old path: projects without the pin build exactly the same prompts, graphs, export
filters, specs and shot lengths (digests recorded on commit 11c4745), and never take a 0.19 path.
Part 2 checks the 0.19 path. How the stills, moves and Wan clips look can only be judged on Cay's
GPU and screen; these tests prove the text, the rotation, the frame plan and the filters.
"""
import asyncio
import copy
import hashlib
import itertools
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))
sys.path.insert(0, str(ROOT / 'tests'))

import cast_design  # noqa: E402
import cut_samples as cs  # noqa: E402
import factory_video as fv  # noqa: E402
import screenplay as sp  # noqa: E402
import studio_quality_policy as qp  # noqa: E402
from factory_timing import audio_layout, plan_seconds  # noqa: E402

PEOPLE = [{'name': n, 'appearance': 'x'} for n in cs.CAST]
MODELS = {'high': 'h.safetensors', 'low': 'l.safetensors', 'clip': 'c.safetensors', 'vae': 'v.safetensors',
          'fast_loras': {'high': 'fh', 'low': 'fl'}, 'tiled_vae': True}
PIN = {'shot_policy': 19}


def h(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def sample_episode(name='cay_blocks'):
    text, cast = cs.TEXTS[name]
    title, beats, lines, _ = sp.parse(text, cast)
    cut = sp.ensure_action(sp.shots(title, beats, lines, cast), 60)
    return sp.assemble(title, {'goal': 'Ziel', 'stakes': 'Einsatz', 'payoff': 'Pointe'}, {'title': 'x'}, cut, cs.visuals_for(cut),
                       [{'name': n, 'appearance': 'x'} for n in cast], {})


def blocks_episode():
    return sample_episode('cay_blocks')


# --- Harnesses: Factory.movies(), Factory.pictures() and the export with the outside world replaced ---

class Movies:
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
    def queue_post(self, d, name, ei, spec): self.posts.append((name, copy.deepcopy(spec)))
    async def render(self, d, key, graph, video=False):
        self.renders.append((key, graph)); return {'id': key, 'output': f'/clips/{len(self.renders)}.mp4', 'sha256': 'c' * 64}


def movie_project(**pins):
    cast = [{'name': 'SpongeBob', 'appearance': 'yellow sponge'}, {'name': 'Mr. Krabs', 'appearance': 'red crab'}]
    scene = lambda kind, who, seconds, **extra: {'kind': kind, 'cast': who, 'render_seconds': seconds, 'selected': 's' * 32, 'camera': 'medium shot',
                                                 'action': 'Szene in der Höhle.', 'motion': ['moves'], 'animation_prompt': 'moves', **extra}
    variants = [{'id': 's' * 32, 'key': 'image:0:0:0:0', **({'shot': 'cu'} if pins else {})}]
    episode = {'title': 'Folge', 'story_policy': 14, 'scenes': [
        scene('line', ['SpongeBob'], 4.0, variants=variants, animation_prompt='Medium shot with a slow push-in of SpongeBob alone, talking calmly with subtle gestures'),
        scene('reaction', ['SpongeBob'], 6.0, voice_of='Mr. Krabs', animation_prompt='listens in silence with lips closed, a small nod'),
        scene('action', ['SpongeBob', 'Mr. Krabs'], 2.12, animation_prompt='Mr. Krabs slowly and gently grabs SpongeBob, calm steady movement'),
        scene('establish', [], 1.96, animation_prompt='slow smooth camera movement across the location, calm natural movement'),
        scene('line', ['Mr. Krabs'], 3.0)]}
    line = lambda si, who: {'episode': 0, 'scene': si, 'turn': 0, 'speaker': who, 'offset': .08, 'duration': 2.0, 'file': '/l.wav', 'sha256': 'x'}
    return {'id': 'r' * 32, 'idea': {'duration': 15, 'fps': 25, 'quality': 'fast', 'lip_sync': 'audio'}, 'prompt_policy': 17, 'edit_policy': 18,
            'plan': {'style': 'claymation stop-motion look', 'cast': cast, 'mood': 'playful'}, 'episodes': [episode], 'exports': [],
            'lines': [line(0, 'SpongeBob'), line(1, 'Mr. Krabs'), line(4, 'Mr. Krabs')],
            'timing': [{'seconds': 17.08}], 'timing_policy': 3, 'timing_fps': 25, 'audio_revision': 1, 'previews': [], **pins}


def run_movies(monkeypatch, tmp_path, d):
    factory = pytest.importorskip('factory')
    import render_studio
    import wan_text_encoder
    calls = {'talk': [], 'motion': [], 'ff': []}
    def audio_graph(info, image, audio, prompt, seed, duration, quality, **kw):
        calls['talk'].append((prompt, duration, kw)); return {'talk': [image, audio, prompt, duration, kw.get('suffix')]}
    def motion_graph(image, prompt, seed, negative, models, duration, quality, **kw):
        calls['motion'].append((prompt, duration, kw)); return {'motion': [image, prompt, duration, kw]}
    monkeypatch.setattr(render_studio, 'audio_graph', audio_graph)
    monkeypatch.setattr(render_studio, 'dialogue_window', lambda lines, start, duration, path: str(path))
    monkeypatch.setattr(wan_text_encoder, 'validate_selected', lambda comfy, clip: None)
    monkeypatch.setattr(factory, 'video_models', lambda info, comfy: {'fast_loras': True, 'clip': 'clip'})
    monkeypatch.setattr(factory, 'motion_graph', motion_graph)
    monkeypatch.setattr(factory, 'file_hash', lambda p: 'h')
    monkeypatch.setattr(factory, 'ff', lambda args: calls['ff'].append([str(a) for a in args]))
    monkeypatch.setattr(factory.turbo, 'attention', lambda runtime, info: 'sdpa')
    fake = Movies(tmp_path)
    asyncio.run(factory.Factory.movies(fake, d))
    return fake, calls


def movies_digest(fake, calls, tmp_path):
    text = json.dumps([fake.renders, fake.posts, calls], ensure_ascii=False, sort_keys=True).replace(str(tmp_path), '<tmp>')
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class Pictures:
    """Records every image prompt instead of calling ComfyUI."""
    def __init__(self):
        self.calls = []
    async def render(self, document, key, graph, video=False):
        refs = [n['inputs']['image'] for n in graph.values() if n['class_type'] == 'LoadImage']
        prompt = next(n['inputs']['text'] for n in graph.values() if n['class_type'] == 'CLIPTextEncode')
        self.calls.append({'key': key, 'refs': refs, 'prompt': prompt})
        return {'id': key, 'output': f'/out/{key}.png'}
    def stage(self, path): return 'staged/' + Path(path).name
    async def object_info(self): return {}
    def asset(self, aid, kind=None): return {'path': f'/assets/{aid}.png'}
    def save(self, d): pass
    def paused(self, rid): return False
    def apply_pending(self, d): return False


def picture_project(episode=None, **pins):
    episode = episode or blocks_episode()
    for scene in episode['scenes']: scene['variants'] = []
    return {'id': 'p' * 32, 'idea': {'participants': [], 'examples': []}, 'plan': {'style': 'claymation stop-motion look', 'cast': copy.deepcopy(PEOPLE)},
            'episodes': [episode], **pins}


def run_pictures(monkeypatch, d):
    factory = pytest.importorskip('factory')
    monkeypatch.setattr(factory, 'validate_nodes', lambda info: {})
    fake = Pictures()
    asyncio.run(factory.Factory.pictures(fake, d))
    return fake.calls


def tone_clip(path, seconds, rate=25):
    src = f'color=c=black:s=576x1024:r={rate}:d={seconds},drawbox=x=480:y=0:w=96:h=1024:color=white:t=fill'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', src, '-pix_fmt', 'yuv420p', str(path)], check=True)
    return {'file': str(path), 'sha256': fv.file_hash(path), 'seconds': seconds}


def speech(path, offset, duration, text, emotion='ruhig'):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=frequency=200:duration={duration}', '-ar', '24000', '-ac', '1', str(path)], check=True)
    return {'file': str(path), 'sha256': fv.file_hash(path), 'offset': offset, 'duration': duration, 'text_de': text, 'emotion': emotion}


def export_scenes(tmp):
    """Two talking shots (one line, two lines), a silent action shot and a reaction, as the export spec has them."""
    tmp.mkdir(parents=True, exist_ok=True)
    a = speech(tmp / 'a.wav', .08, 1.6, 'Wo ist mein Stein?')
    b = speech(tmp / 'b.wav', .08, 1.4, 'Ich hab ihn nicht!', 'wütend'); c = speech(tmp / 'c.wav', 1.7, 1.2, 'Ehrlich nicht!')
    return [{'seconds': 2.0, 'clips': [tone_clip(tmp / 't1.mp4', 2.0)], 'kind': 'line', 'lines': [a]},
            {'seconds': 3.2, 'clips': [tone_clip(tmp / 't2.mp4', 3.2)], 'kind': 'line', 'lines': [b, c]},
            {'seconds': 1.64, 'clips': [tone_clip(tmp / 'w.mp4', 1.64)], 'kind': 'action', 'lines': []},
            {'seconds': 2.4, 'clips': [tone_clip(tmp / 'r.mp4', 2.4)], 'kind': 'reaction', 'lines': []}]


def run_export(monkeypatch, tmp, scenes, **pins):
    filters = []; real = fv.ff
    def ff(args, cwd=None):
        if '-vf' in args: filters.append(str(args[args.index('-vf') + 1]))
        return real(args, cwd)
    monkeypatch.setattr(fv, 'ff', ff)
    spec = {'folder': str(tmp), 'fps': 25, 'smooth': True, 'scenes': copy.deepcopy(scenes), 'edit_policy': 18, **pins}
    result = fv.prepare(spec)
    monkeypatch.setattr(fv, 'ff', real)
    return result, filters


def frames(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v', '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', str(path)],
                         capture_output=True, text=True, check=True).stdout
    return int(out.strip())


def lengths(episode, minimum=0, **flags):
    """Layout 18 (the cut of every new project) of one sample episode, with the speech rate of the samples."""
    e = copy.deepcopy(episode); plan_seconds(e, 60, 25); lines = cs.timed_lines(e)
    report = audio_layout([e], lines, minimum, 25, version=18, **flags)[0]
    return e, report


# --- Part 1: projects without the pin stay exactly as they were ---------------------------------

def old_path_values():
    graphs = [fv.motion_graph('i.png', 'p', 7, '', MODELS, s, q) for s in (1.0, 2.12, 3.2, 4.6, 5.0) for q in ('fast', 'balanced')]
    episode = blocks_episode()
    stills = [cast_design.scene_prompt(s, PEOPLE, s['cast'], 'clay style') + cast_design.scene_text(s, PEOPLE) for s in episode['scenes']]
    motions = [qp.motion_direction(s, [{'speaker': s['cast'][0]}] if s.get('dialogues') and s['kind'] == 'line' else [], 0, 3, 14) for s in episode['scenes']]
    plan_seconds(episode, 60, 25)
    e, lines = copy.deepcopy(episode), cs.timed_lines(episode)
    report = audio_layout([e], lines, 60, 25, version=18)
    rounds = [cast_design.revision_prompt('p', 'Mehr Licht', r, v, 18) for r in range(3) for v in range(2)]
    designs = [f(PEOPLE[0], 'clay style', cs.CAST) for f in (cast_design.identity_prompt, cast_design.neutral_prompt, cast_design.restyle_prompt, cast_design.style_prompt)]
    segments = [qp.scene_segments(s, 25, t) for s in (1.0, 3.2, 4.6, 6.0, 9.3, 16.0) for t in (True, False)]
    return {'motion_graph': h(graphs), 'stills': h(stills), 'motion_text': h(motions), 'layout18': h([report, e['scenes'], lines]),
            'rounds': h(rounds), 'designs': h(designs), 'segments': h(segments)}


OLD = {'motion_graph': '144a71eaba4e2246', 'stills': 'c4ddd1003c023f8f', 'motion_text': '86776fc1bfb173df', 'layout18': '5f4764ffe03d09f7',
       'rounds': '39d971eb22e4c7a1', 'designs': '50858868c9b1e633', 'segments': '99495a3686a2543a'}


def test_old_prompts_graphs_and_layout_are_byte_identical():
    assert old_path_values() == OLD


def test_old_project_renders_exactly_as_before(monkeypatch, tmp_path):
    """Graph keys, render prompts, part and export specs of an unpinned project (digest from 11c4745)."""
    fake, calls = run_movies(monkeypatch, tmp_path, movie_project())
    assert movies_digest(fake, calls, tmp_path) == '6c63209f5dd5ca3f'
    assert all('shot_policy' not in spec for _, spec in fake.posts)


def test_old_project_draws_the_same_scene_images(monkeypatch):
    calls = [c for c in run_pictures(monkeypatch, picture_project()) if c['key'].startswith('image:')]
    assert h(calls) == 'eda24f7085a32c5b'
    assert calls[0]['prompt'].startswith('One coherent vertical 9:16 film frame') and 'Medium shot of SpongeBob alone.' in calls[0]['prompt']


def test_old_export_filters_are_unchanged(monkeypatch, tmp_path):
    result, filters = run_export(monkeypatch, tmp_path / 'old', export_scenes(tmp_path / 'src'))
    assert h(filters) == '38595e003144c760'
    assert sum('zoompan' in f for f in filters) == 2          # the 0.18 camera: the two-line shot and the reaction only


def test_without_the_pin_no_019_path_is_taken(monkeypatch, tmp_path):
    """Guard: every 0.19 behaviour function raises; an unpinned project still plans, draws, renders,
    lays out and exports."""
    import shot_design
    def boom(*a, **k): raise AssertionError('0.19 path taken without shot_policy 19')
    for name in ('plan', 'pick', 'lead', 'pose', 'fresh', 'unframed', 'camera', 'punch_at', 'native_frames', 'clip_frames', 'whole_clips',
                 'silent_base', 'snap_silent', 'undamp', 'direction', 'motion_prompt'):
        monkeypatch.setattr(shot_design, name, boom)
    run_pictures(monkeypatch, picture_project())
    run_movies(monkeypatch, tmp_path, movie_project())
    lengths(blocks_episode(), 60)
    old_path_values()
    run_export(monkeypatch, tmp_path / 'guard', export_scenes(tmp_path / 'src'))
    assert shot_design.export_fields({}, {'variants': [{'id': 'a', 'shot': 'cu'}], 'selected': 'a'}) == {} and shot_design.spec({}) == {}


# --- Part 2: the 0.19 path -----------------------------------------------------------------------

import shot_design as sd  # noqa: E402

OPENINGS = {'ecu': 'Extreme close-up', 'cu': 'Close-up', 'mcu': 'Medium close-up', 'ms': 'Medium shot', 'wide': 'Wide',
            'low': 'Low-angle', 'high': 'High-angle', 'ots': 'Over-the-shoulder', 'profile': ('Profile', 'Wide side view'), 'dutch': 'Dutch-angle'}


def test_new_projects_pin_the_shot_policy():
    source = (ROOT / 'cay_studio_app' / 'factory.py').read_text()
    assert 'd.update(sound_policy=19,shot_policy=19,render_policy=19)' in source
    assert sd.active({'shot_policy': 19}) and not sd.active({}) and not sd.active({'shot_policy': 18})
    assert sd.spec({'shot_policy': 19}) == {'shot_policy': 19} and sd.spec({'edit_policy': 18}) == {}


def test_still_prompts_lead_with_shot_size_and_angle_and_rotate(monkeypatch):
    d = picture_project(**PIN); episode = d['episodes'][0]
    calls = {c['key']: c for c in run_pictures(monkeypatch, d) if c['key'].startswith('image:')}
    shots = []
    for si, scene in enumerate(episode['scenes']):
        pair = []
        for variant, entry in enumerate(scene['variants']):
            kind = entry['shot']; prompt = calls[entry['key']]['prompt']; pair.append(kind)
            assert prompt.startswith(OPENINGS[kind]), (kind, prompt[:80])
            assert 'Medium shot of' not in prompt or kind == 'ms'
            assert 'Framing:' not in prompt and 'alone in the frame' not in prompt
            # Identity stays with the references; their pose and pedestal do not.
            assert len(calls[entry['key']]['refs']) == len(scene['cast'])
            for name in scene['cast']: assert f'Reference image {scene["cast"].index(name) + 1} shows {name}: take only the identity' in prompt
            assert 'No pedestal, display base' in prompt and 'pose, framing, camera angle and background come from this scene' in prompt
        assert len(set(pair)) == 2, pair
        shots.append(pair)
    # No two neighbours share a type, whichever image Cay picks; real variety over the episode.
    assert all(a != b for left, right in zip(shots, shots[1:]) for a in left for b in right)
    assert len({k for pair in shots for k in pair}) >= 7
    assert any(k in ('cu', 'ecu') for pair in shots for k in pair[:1])


def test_shot_plan_rules_on_every_sample_cut():
    for name in cs.TEXTS:
        episode = sample_episode(name); scenes = episode['scenes']; plan = sd.plan(episode)
        for i, (scene, shot) in enumerate(zip(scenes, plan)):
            assert shot['type'] in sd.ROLES[shot['role']] and shot['alt'] in sd.ROLES[shot['role']]
            if shot['role'] == 'talk': assert shot['type'] not in ('wide', 'profile', 'ecu') and shot['alt'] not in ('wide', 'profile', 'ecu')
            if i and scene['location'] != scenes[i - 1]['location'] and shot['role'] in ('action', 'establish', 'empty'):
                assert shot['type'] == 'wide' or plan[i - 1]['type'] == 'wide'          # a new place opens wide
            if i and scene['location'] == scenes[i - 1]['location'] and shot['role'] == 'talk' and sd.emotional(scene):
                assert shot['type'] in sd.CLOSE['talk'], (name, i, shot)               # a strong feeling in the face
        for left, right in zip(plan, plan[1:]):
            assert {left['type'], left['alt']}.isdisjoint({right['type'], right['alt']}), (name, left, right)
        # Later rounds take other angles than both neighbours planned.
        for i in range(len(plan)):
            near = {plan[j][x] for j in (i - 1, i + 1) if 0 <= j < len(plan) for x in ('type', 'alt')}
            for round_ in (1, 2, 3):
                assert sd.pick(plan, i, 0, round_) not in near and sd.pick(plan, i, 0, round_) != sd.pick(plan, i, 1, round_)
        # Deterministic: the same episode gives the same plan.
        assert sd.plan(sample_episode(name)) == plan
    first = sd.plan(sample_episode('cay_pingpong'))
    assert first[0]['type'] == 'ms'          # the first talking shot at a new place shows more of it


def test_cays_own_camera_line_wins_once_per_section():
    episode = sample_episode('cay_pingpong'); episode['own_script'] = True
    talk = next(i for i, s in enumerate(episode['scenes']) if s['kind'] == 'line' and i)
    episode['scenes'][talk]['action'] = 'Kamera: Froschperspektive auf Mr. Krabs. Er droht.'
    plan = sd.plan(episode)
    assert plan[talk]['type'] == 'low' and plan[talk - 1]['type'] != 'low'
    assert sd.wish({'action': 'Er kommt von oben herein und ist ganz nah.'}) is None      # prose is no camera wish
    episode.pop('own_script'); assert sd.plan(episode)[talk]['type'] == sd.plan(sample_episode('cay_pingpong'))[talk]['type']


def test_new_rounds_vary_the_moment_not_with_the_old_camera_text(monkeypatch):
    d = picture_project(**PIN); scene = d['episodes'][0]['scenes'][1]
    run_pictures(monkeypatch, d)
    first = {v['key']: v['shot'] for v in scene['variants']}
    scene['image_rounds'] = [1, 1]
    calls = {c['key']: c['prompt'] for c in run_pictures(monkeypatch, d) if c['key'].startswith('image:0:1:1:')}
    shots = {v['key']: v['shot'] for v in scene['variants'] if v['key'].startswith('image:0:1:1:')}
    assert len(calls) == 2 and set(shots.values()).isdisjoint(set(first.values())) is False or set(shots.values()) != set(first.values())
    for key, prompt in calls.items():
        assert prompt.startswith(OPENINGS[shots[key]]) and 'Fresh take: a different' in prompt and 'camera angle (slightly low angle)' not in prompt


def test_design_sheets_lose_the_pedestal_only_under_the_pin():
    for f in (cast_design.identity_prompt, cast_design.neutral_prompt, cast_design.restyle_prompt, cast_design.style_prompt):
        assert 'pedestal' not in f(PEOPLE[0], 'clay style', cs.CAST) and 'No pedestal' in f(PEOPLE[0], 'clay style', cs.CAST, 19)


def evaluate(expr, n, zoom=1.):
    """Value of a zoompan expression at output frame n (iw = ih = 1). The expressions come from
    shot_design.camera itself (numbers, on, iw, ih, zoom, if, gte, min); eval runs without builtins."""
    text = re.sub(r'\bif\(', 'iff(', expr.replace('\\,', ','))
    return eval(text, {'__builtins__': {}}, {'on': n, 'iff': lambda c, a, b: a if c else b, 'gte': lambda a, b: float(a >= b),
                                             'min': min, 'iw': 1., 'ih': 1., 'zoom': zoom})


def talk_scenes(count=8, tight=()):
    line = lambda offset, duration, text: {'offset': offset, 'duration': duration, 'text_de': text}
    out = []
    for k in range(count):
        lines = [line(.08, 2.6, 'Ich hab dir gesagt, du sollst die Finger davon lassen!')] + ([line(2.9, 1.4, 'Kapiert?')] if k % 3 == 2 else [])
        out.append({'seconds': 4.5 if k % 3 == 2 else 2.96, 'kind': 'line', 'lines': lines, **({'shot': 'cu'} if k in tight else {})})
        out.append({'seconds': 2.12, 'kind': 'action', 'lines': []})
    return out


def test_every_talking_shot_moves_and_faces_stay_in_the_frame():
    scenes = talk_scenes(tight=(5,)); moves = []
    for i, scene in enumerate(scenes):
        move = sd.camera(scenes, i, 0., 25)
        if scene['kind'] != 'line': assert move is None; continue
        zoom, (x, y) = move; n = round(scene['seconds'] * 25)
        values = [evaluate(zoom, f) for f in range(n)]; offsets = [evaluate(x, f, z) for f, z in enumerate(values)]
        top = 1 + (sd.LIMIT - 1) * (.5 if scene.get('shot') == 'cu' else 1)
        assert all(1 - 1e-9 <= v <= top + 1e-9 for v in values), (i, zoom)
        assert max(values) - min(values) >= .019 or max(offsets) - min(offsets) >= .019, (i, zoom, x)   # it really moves
        assert all(-1e-9 <= o <= 1 - 1 / z + 1e-9 for o, z in zip(offsets, values))                   # never outside the picture
        assert all(evaluate(y, 0, z) <= .05 for z in values)                                           # at most 5 % off the top: heads stay
        if len(scene['lines']) >= 2:
            at = math.ceil(scene['lines'][1]['offset'] * 25 - 1e-9)
            assert values[at] > values[at - 1] * 1.03                                                   # the second line punches in
        moves.append(('drift' if 'iw-iw/zoom)*(' in x else 'pull' if values[0] > values[-1] else 'punch' if max(b - a for a, b in zip(values, values[1:])) > .03 else 'push'))
    assert len(set(moves[:4])) == 4 and moves[:4] == moves[4:8]


def test_camera_works_across_clips_of_one_shot():
    scenes = talk_scenes(1); scenes[0]['seconds'] = 4.0
    whole, _ = sd.camera(scenes, 0, 0., 25); second, _ = sd.camera(scenes, 0, 2.0, 25)
    assert abs(evaluate(whole, 50) - evaluate(second, 0)) < 1e-9


def test_export_moves_every_talking_part_keeps_captions_and_frames(monkeypatch, tmp_path):
    scenes = export_scenes(tmp_path / 'src')
    old, old_filters = run_export(monkeypatch, tmp_path / 'old', scenes)
    new, filters = run_export(monkeypatch, tmp_path / 'new', scenes, **PIN)
    assert [('zoompan' in f) for f in filters] == [True, True, False, True]       # both talking shots, the reaction as in 0.18
    assert filters[3] == old_filters[3] and filters[2] == old_filters[2]          # silent action and reaction unchanged
    assert filters[0] != old_filters[0] and filters[1] != old_filters[1]
    for f in filters[:2]: assert f.index('zoompan') < f.index('subtitles=')        # captions are burnt in after the zoom: they never move
    assert (tmp_path / 'old' / 'Untertitel.ass').read_bytes() == (tmp_path / 'new' / 'Untertitel.ass').read_bytes()
    for name, scene in zip(new['parts'], scenes): assert frames(tmp_path / 'new' / name) == round(scene['seconds'] * 25)


def test_silent_wan_clips_render_and_play_native_frames():
    graph = fv.motion_graph('i.png', 'p', 7, '', MODELS, 2.12, 'fast', native=25)
    assert graph['14']['inputs']['fps'] == 25 and graph['8']['inputs']['length'] == 53
    old = fv.motion_graph('i.png', 'p', 7, '', MODELS, 2.12, 'fast')
    assert old['14']['inputs']['fps'] == 16 and old['8']['inputs']['length'] == 37
    # Sampler, LoRAs, steps and negative text stay the 0.18 ones.
    for key in ('2', '3', '7', '9', '10', '11', '12', '16', '17'): assert graph[key] == old[key]
    assert [sd.native_frames(s, 25) for s in (1.64, 2.12, 2.0, 3.24)] == [41, 53, 53, 81]
    with pytest.raises(ValueError): sd.native_frames(3.3, 25)
    assert qp.cadence(25, True, 25.0) == 'fps=25'                                 # no minterpolate for a native clip


def test_native_clip_exports_frame_exact_without_interpolation(monkeypatch, tmp_path):
    tmp_path.mkdir(exist_ok=True)
    clip = tone_clip(tmp_path / 'n.mp4', 53 / 25)                                 # 53 Wan frames at 25 fps
    scenes = [{'seconds': 53 / 25, 'clips': [clip], 'kind': 'action', 'lines': []}]
    result, filters = run_export(monkeypatch, tmp_path / 'out', scenes, **PIN)
    assert 'minterpolate' not in filters[0] and filters[0].startswith('setpts=PTS-STARTPTS,fps=25,')
    assert frames(tmp_path / 'out' / result['parts'][0]) == 53
    old = tone_clip(tmp_path / 'o.mp4', 3.4, rate=16)
    _, filters = run_export(monkeypatch, tmp_path / 'old', [{'seconds': 3.2, 'clips': [dict(old, seconds=3.2)], 'kind': 'action', 'lines': []}])
    assert 'minterpolate' in filters[0]                                            # 0.18: unchanged


def test_silent_shot_lengths_vary_and_match_rendered_frames():
    episode = sample_episode('cay_pingpong')
    old, _ = lengths(episode)
    new, report = lengths(episode, shots=True)
    old_silent = [s['render_seconds'] for s in old['scenes'] if s['kind'] == 'action']
    silent = [s['render_seconds'] for s in new['scenes'] if s['kind'] == 'action']
    assert old_silent == [3.2] * len(old_silent)                                  # the 0.18 rhythm Cay felt
    assert len(set(silent)) >= 3 and all(1.6 <= s <= 2.8 for s in silent) and 3.2 not in silent
    for scene in new['scenes']:
        if scene['kind'] == 'line': continue
        clips = qp.scene_segments(scene['render_seconds'], 25, False, native=True)
        assert abs(sum(clips) - scene['render_seconds']) < 1e-9
        for c in clips:                                                           # every rendered frame is shown, nothing frozen or cut
            assert round(c * 25) % 4 == 1 and sd.native_frames(c, 25) == round(c * 25) <= 81
    # No more GPU: the silent action shots render at most the Wan frames of the 0.18 layout.
    wan = lambda s, rate: sum(fv.motion_graph('i', 'p', 1, '', MODELS, c, 'fast', **({'native': 25} if rate == 25 else {}))['8']['inputs']['length']
                              for c in qp.scene_segments(s, 25, False, native=rate == 25))
    assert sum(wan(s, 25) for s in silent) <= sum(wan(s, 16) for s in old_silent) + 16
    # Talking shots and every line offset stay where layout 18 puts them.
    for a, b in zip(old['scenes'], new['scenes']):
        if a['kind'] == 'line': assert a['render_seconds'] == b['render_seconds']
    assert report['minimum_met']


def test_minimum_length_still_met_with_whole_clips():
    for name in cs.TEXTS:
        new, report = lengths(sample_episode(name), 75, shots=True)
        assert report['minimum_met'] and report['seconds'] >= 75
        for scene in new['scenes']:
            if scene['kind'] in ('action', 'establish', 'reaction'):
                assert all(round(c * 25) % 4 == 1 for c in qp.scene_segments(scene['render_seconds'], 25, False, native=True)), (name, scene['render_seconds'])
    assert [sd.whole_clips(n) for n in (40, 41, 81, 82, 83, 161, 162, 163)] == [41, 41, 81, 82, 86, 162, 162, 163]
    assert sd.clip_frames(150) == [77, 73] and sd.clip_frames(163) == [57, 53, 53]


def test_motion_text_has_no_damping_words_and_concrete_camera(monkeypatch, tmp_path):
    d = movie_project(**PIN)
    fake, calls = run_movies(monkeypatch, tmp_path, d)
    damping = re.compile(r'(?i)\b(?:calm|calmly|steady|steadily|subtle|subtly|slow|slowly|gentle|gently|smooth|smoothly|stop-motion)\b')
    for prompt, duration, kw in calls['motion'] + calls['talk']:
        assert not damping.search(prompt), prompt
        assert not prompt.startswith('Medium shot') and 'Medium shot with a' not in prompt
    silent = [p for p, _, kw in calls['motion']]
    assert all(kw == {'native': 25} for _, _, kw in calls['motion'])
    assert 'grabs SpongeBob' in silent[2] and 'Camera:' in silent[2] and 'Full real-time speed' in silent[2]
    # The reaction (6.0 s) is two whole native clips; the action and wide shot one each.
    assert [round(dur * 25) for _, dur, _ in calls['motion']] == [77, 73, 53, 49]
    assert all(kw['suffix'] == sd.TALK_SUFFIX for _, _, kw in calls['talk'])
    assert 'big expressive' in sd.TALK_SUFFIX and 'calm' not in sd.TALK_SUFFIX and 'mouth stays closed' in sd.TALK_SUFFIX
    # The next clip of the reaction starts from its last native frame.
    assert any('select=eq(n\\,76)' in ' '.join(args) for args in calls['ff'])
    # Specs carry the pin and the chosen shot type; the 0.18 project above does not.
    assert all(spec['shot_policy'] == 19 for _, spec in fake.posts)
    assert fake.posts[-1][1]['scenes'][0]['shot'] == 'cu' and 'shot' not in fake.posts[-1][1]['scenes'][1]


def test_talk_suffix_only_with_the_pin():
    import render_studio
    info = {'CayWanVideoSampler': {'input': {'required': {}, 'optional': {'cay_audio_cfg_steps': ['INT']}}}}
    source = (ROOT / 'cay_studio_app' / 'render_studio.py').read_text()
    assert 'SUFFIX if suffix is None else suffix' in source and render_studio.SUFFIX.startswith(' Only the single visible character speaks')
    assert info and 'body calm' in render_studio.SUFFIX                           # the 0.18 text stays for every older project


def test_undamp_keeps_the_action():
    assert sd.undamp('Mr. Krabs slowly and gently grabs SpongeBob, calm steady movement') == 'Mr. Krabs and grabs SpongeBob, movement'
    assert sd.undamp('claymation stop-motion look') == 'claymation look'
    assert sd.undamp('a subtle push-in') == 'a push-in' and sd.undamp('a slow, angry turn') == 'an angry turn'
    prompt = sd.motion_prompt('claymation stop-motion look', 'Medium shot of Patrick alone, talking: he slams the door', {'kind': 'line', 'cast': ['Patrick']}, [{'speaker': 'Patrick'}], 0)
    assert prompt.startswith('claymation look. He slams the door') or prompt.startswith('claymation look. Patrick alone')
