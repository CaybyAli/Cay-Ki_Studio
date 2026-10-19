"""Contact sheet of the 0.19 talking-shot camera (shot_policy 19) on a real lip-sync clip.

Run: venv/bin/python tests/manual/camera_sheet_check.py <talking clip .mp4> <empty out dir>
No ports, no GPU, no models. For each move (push-in, pull-back, lateral drift, punch-in at a caption
change, a second line, and the same for a close-up) it renders the export camera exactly as
factory_video.prepare does, checks the frame count and writes one row of first / middle / last
frame into <out dir>/Kamera_019.png. Look at it: every head must stay in the frame.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))
import factory_video as fv  # noqa: E402
import shot_design as sd  # noqa: E402

source, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
info = fv.probe(source); stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
seconds = min(4.0, float(stream.get('duration', info['format']['duration']))); frames = round(seconds * 25)
line = lambda offset, duration, text: {'offset': offset, 'duration': duration, 'text_de': text}
one = [line(.08, seconds - .3, 'Ich hab dir gesagt, du sollst die Finger davon lassen!')]
two = [line(.08, seconds / 2 - .2, 'Hör gut zu!'), line(seconds / 2, seconds / 2 - .2, 'Das war das letzte Mal!')]
cases = [('Push', 0, one, None), ('Pull', 1, one, None), ('Drift', 2, one, None), ('Punch', 3, one, None),
         ('Zweite Zeile', 0, two, None), ('Nah: Pull', 1, one, 'cu'), ('Nah: zweite Zeile', 3, two, 'cu')]
rows = []; failed = []
for name, slot, lines, shot in cases:
    scenes = [{'seconds': 2.0, 'kind': 'line', 'lines': [line(.08, 1.5, 'eins zwei drei')]} for _ in range(slot)]
    scenes.append({'seconds': seconds, 'kind': 'line', 'lines': lines, **({'shot': shot} if shot else {})})
    zoom, (x, y) = sd.camera(scenes, slot, 0., 25)
    camera = ('setpts=PTS-STARTPTS,fps=25,' + f'trim=end_frame={frames},setpts=PTS-STARTPTS,'
              'scale=1080:1920:flags=lanczos:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,'
              f"scale={fv.ZOOM_UPSCALE}:flags=bicubic,zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s=1080x1920:fps=25,setsar=1")
    clip = out / f'{len(rows)}.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source), '-an', '-vf', camera, '-frames:v', str(frames),
                    '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', str(clip)], check=True)
    count = int(fv.probe(clip)['streams'][0].get('nb_frames', 0))
    if count != frames: failed.append(f'{name}: {count} statt {frames} Bilder')
    row = out / f'{len(rows)}.png'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(clip), '-vf',
                    f"select='eq(n\\,0)+eq(n\\,{frames // 2})+eq(n\\,{frames - 1})',scale=270:480,tile=3x1", '-frames:v', '1', str(row)], check=True)
    rows.append(row); print(f'{name:18} zoom {zoom[:70]}')
inputs = [arg for row in rows for arg in ('-i', str(row))]
subprocess.run(['ffmpeg', '-v', 'error', '-y', *inputs, '-filter_complex', ''.join(f'[{i}:v]' for i in range(len(rows))) + f'vstack=inputs={len(rows)}',
                str(out / 'Kamera_019.png')], check=True)
print('Bildanzahl: ' + ('; '.join(failed) if failed else 'alle exakt') + f'. Kontaktbogen: {out / "Kamera_019.png"}')
sys.exit(1 if failed else 0)
