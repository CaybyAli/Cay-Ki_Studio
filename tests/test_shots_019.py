"""0.19 picture dynamics for projects pinned with shot_policy 19 (new projects only).

Cay after episode 1 of "Preis der Familie" and "Weißes Gold": far too many static frontal medium
shots at eye level, no close-ups, talking heads stand still, silent action barely moves and feels
like slow motion. Measured: 31 of 34 shots frontal, 0 close-ups, 8 of 9 talking shots without any
camera move, every silent shot exactly 3.20 s of 16 fps frames interpolated to 25 fps.

Part 1 pins the old path: projects without the pin build exactly the same prompts, graphs, export
filters, specs and shot lengths (digests recorded on commit 11c4745), and never call shot_design.
Part 2 checks the 0.19 path. How the stills, moves and Wan clips look can only be judged on Cay's
GPU and screen; these tests prove the text, the rotation, the frame plan and the filters.
"""
import asyncio
import copy
import hashlib
import json
import shutil
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


def h(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def blocks_episode():
    text, cast = cs.TEXTS['cay_blocks']
    title, beats, lines, _ = sp.parse(text, cast)
    cut = sp.ensure_action(sp.shots(title, beats, lines, cast), 60)
    return sp.assemble(title, {'goal': 'Ziel', 'stakes': 'Einsatz', 'payoff': 'Pointe'}, {'title': 'x'}, cut, cs.visuals_for(cut), PEOPLE, {})


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
    def queue_post(self, d, name, ei, spec): self.posts.append((name, spec))
    async def render(self, d, key, graph, video=False):
        self.renders.append((key, graph)); return {'id': key, 'output': f'/clips/{len(self.renders)}.mp4', 'sha256': 'c' * 64}


def movie_project(**pins):
    cast = [{'name': 'SpongeBob', 'appearance': 'yellow sponge'}, {'name': 'Mr. Krabs', 'appearance': 'red crab'}]
    scene = lambda kind, who, seconds, **extra: {'kind': kind, 'cast': who, 'render_seconds': seconds, 'selected': 's' * 32, 'camera': 'medium shot',
                                                 'action': 'Szene in der Höhle.', 'motion': ['moves'], 'animation_prompt': 'moves', **extra}
    episode = {'title': 'Folge', 'story_policy': 14, 'scenes': [
        scene('line', ['SpongeBob'], 4.0, animation_prompt='Medium shot with a slow push-in of SpongeBob alone, talking calmly with subtle gestures'),
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


def picture_project(**pins):
    episode = blocks_episode()
    for scene in episode['scenes']: scene['variants'] = []
    return {'id': 'p' * 32, 'idea': {'participants': [], 'examples': []}, 'plan': {'style': 'claymation stop-motion look', 'cast': copy.deepcopy(PEOPLE)},
            'episodes': [episode], **pins}


def run_pictures(monkeypatch, d):
    factory = pytest.importorskip('factory')
    monkeypatch.setattr(factory, 'validate_nodes', lambda info: {})
    fake = Pictures()
    asyncio.run(factory.Factory.pictures(fake, d))
    return [c for c in fake.calls if c['key'].startswith('image:')]


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


# --- Part 1: projects without the pin stay exactly as they were ---------------------------------

def old_path_values():
    graphs = [fv.motion_graph('i.png', 'p', 7, '', MODELS, s, q) for s in (1.0, 2.12, 3.2, 4.6, 5.0) for q in ('fast', 'balanced')]
    episode = blocks_episode()
    stills = [cast_design.scene_prompt(s, PEOPLE, s['cast'], 'clay style') + cast_design.scene_text(s, PEOPLE) for s in episode['scenes']]
    motions = [qp.motion_direction(s, [{'speaker': s['cast'][0]}] if s.get('dialogues') and s['kind'] == 'line' else [], 0, 3, 14) for s in episode['scenes']]
    plan_seconds(episode, 60, 25)
    e, lines = copy.deepcopy(episode), cs.timed_lines(episode)
    report = audio_layout([e], lines, 60, 25, version=18)
    return {'motion_graph': h(graphs), 'stills': h(stills), 'motion_text': h(motions), 'layout18': h([report, e['scenes'], lines])}


OLD = {'motion_graph': '144a71eaba4e2246', 'stills': 'c4ddd1003c023f8f', 'motion_text': '86776fc1bfb173df', 'layout18': '5f4764ffe03d09f7'}


def test_old_prompts_graphs_and_layout_are_byte_identical():
    assert old_path_values() == OLD
