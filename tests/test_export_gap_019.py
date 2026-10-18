"""Cay 0.18.2, episode 6 of 'Die Krone der Ananasstraße' after ~12 h: "Exportprüfung fehlgeschlagen: Bildlänge oder
Bildgröße stimmt nicht." FFmpeg's setpts adds offset/TB in double precision and truncates; with offset/TB just below a
whole frame the timestamps jump by two at 16, 32, ..., 1024 frames. FFmpeg 7.1+ writes mp4 as VFR, so the jump stays in
the part as a gap, and from the third gap on '-t' dropped the last frame. This box has FFmpeg 6.1 (CFR default), so the
newer behaviour is emulated by adding '-fps_mode vfr' to the part encodes - proven to reproduce Cay's block."""
import subprocess
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path[:0] = [str(APP), str(Path(__file__).parent)]

import factory_video  # noqa: E402
from factory_video import file_hash, finish, probe, shift  # noqa: E402

FPS = 25
SHOTS = [47, 66, 80, 35, 52, 52, 35, 80, 47]      # frames; with the title card first this gave three gaps


def ffmpeg_pts(expression, frames, fps=FPS):
    """What FFmpeg's setpts makes of PTS 0..frames-1 (D2TS truncates the double)."""
    text = expression.split('PTS+', 1)[1]
    if text.endswith('/TB'): c = float(text[:-3]) / (1 / fps)
    else: c = float(text.split('/')[0]) / ((1 / fps) * fps)
    return [int(i + c) for i in range(frames)]


def test_shift_never_leaves_a_gap_and_keeps_good_parts_unchanged():
    changed = 0
    for k in range(0, 4000, 3):
        offset = sum([k / FPS])                     # how prepare() accumulates whole-frame offsets
        for frames in (25, 37, 81, 160, 375):
            expression = shift(offset, frames, FPS)
            pts = ffmpeg_pts(expression, frames)
            assert pts == list(range(pts[0], pts[0] + frames)) and abs(pts[0] - round(offset * FPS)) <= 1   # captions as before
            if expression != f'setpts=PTS+{offset:.9f}/TB': changed += 1
    assert changed > 0                              # the defect exists, and only those parts get the new text


def clip(path, frames):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc2=size=480x832:rate={FPS}',
                    '-frames:v', str(frames + 4), '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(path)], check=True)
    return {'file': str(path), 'sha256': file_hash(path), 'seconds': frames / FPS}


def series_episode(tmp_path):
    import math, wave
    from array import array
    scenes = []
    for i, frames in enumerate(SHOTS):
        scenes.append({'seconds': frames / FPS, 'lines': [], 'ambience': 'room', 'sound_cues': [], 'kind': 'line',
                       'clips': [clip(tmp_path / f'shot{i}.mp4', frames)]})
    seconds = sum(SHOTS) / FPS
    with wave.open(str(tmp_path / 'mix.wav'), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(array('h', (int(3000 * math.sin(i * .03)) for i in range(round(seconds * 24000)))).tobytes())
    art = tmp_path / 'keyart.png'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0x3366aa:s=864x1536:d=1', '-frames:v', '1', str(art)], check=True)
    return {'folder': str(tmp_path / 'work'), 'fps': FPS, 'smooth': False, 'scenes': scenes, 'title': 'T', 'output': str(tmp_path / 'out' / 'Folge_06.mp4'),
            'minimum_seconds': 0, 'mood': 'playful', 'mix': None, 'music': None, 'edit_policy': 18, 'part_label': 'Teil 6/6',
            'audio_mix': {'file': str(tmp_path / 'mix.wav'), 'sha256': file_hash(tmp_path / 'mix.wav')},
            'cover': {'position': 'start', 'image': str(art), 'sha256': file_hash(art), 'title': 'Die Krone der Ananasstraße', 'label': 'Teil 6'}}


@pytest.fixture
def newer_ffmpeg(monkeypatch):
    """FFmpeg 7.1+/8 behaviour: mp4 parts keep variable timing (gaps stay in the file)."""
    real = factory_video.ff

    def ff(args, cwd=None):
        args = list(args)
        if 'libx264' in args: args[-1:-1] = ['-fps_mode', 'vfr']
        return real(args, cwd)
    monkeypatch.setattr(factory_video, 'ff', ff)


def test_the_episode_6_export_passes_with_newer_ffmpeg(tmp_path, newer_ffmpeg):
    spec = series_episode(tmp_path)
    result = finish(spec)
    video = next(s for s in probe(result['file'])['streams'] if s['codec_type'] == 'video')
    assert int(video['nb_frames']) == sum(SHOTS) + FPS                                   # every frame plus the 1-s card
    work = Path(spec['folder'])
    for name in [line.split("'")[1] for line in (work / 'Clips.txt').read_text().splitlines()]:
        info = probe(work / name); stream = info['streams'][0]
        assert abs(float(stream['duration']) - int(stream['nb_frames']) / FPS) < 1e-3, name   # no gap inside a part


def test_an_unpredicted_gap_is_repaired_once(tmp_path, newer_ffmpeg, monkeypatch):
    # If some FFmpeg computes differently than predicted, the timeline check re-encodes with whole frames.
    monkeypatch.setattr(factory_video, 'shift', lambda offset, frames, fps, exact=False:
                        f'setpts=PTS+{round(offset * fps)}/(TB*{fps})' if exact else f'setpts=PTS+{offset:.9f}/TB')
    spec = series_episode(tmp_path)
    result = finish(spec)
    assert int(next(s for s in probe(result['file'])['streams'] if s['codec_type'] == 'video')['nb_frames']) == sum(SHOTS) + FPS
