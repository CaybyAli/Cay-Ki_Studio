"""0.18 export look for new projects: captions higher and in short chunks, a directed camera on
the CPU, an audible sound bed. Projects without edit_policy 18 render exactly as before."""
import hashlib
import math
import subprocess
import sys
import wave
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))

import factory_audio as fa  # noqa: E402
import factory_video as fv  # noqa: E402


def test_captions_are_two_to_four_words_in_capitals_timed_by_characters():
    chunks = fv.caption_chunks('Herr Krabs, ich hab nur noch diese paar Münzen, bitte!', 1.0, 4.0)
    texts = [c[2] for c in chunks]
    assert texts == ['HERR KRABS,', 'ICH HAB NUR NOCH', 'DIESE PAAR MÜNZEN,', 'BITTE!']
    assert [c[2] for c in fv.caption_chunks('Wo ist mein Stein, Patrick?', 0, 2)] == ['WO IST MEIN STEIN,', 'PATRICK?']
    assert abs(chunks[0][0] - 1.0) < 1e-9 and abs(chunks[-1][1] - 5.0) < 1e-9
    assert all(abs(a[1] - b[0]) < 1e-9 for a, b in zip(chunks, chunks[1:]))          # seamless, no gaps
    assert fv.caption_chunks('Groß', 0, 1)[0][2] == 'GROSS'


def test_a_short_trailing_word_never_stands_alone():
    for text, last in (('eins zwei drei vier fünf', 'VIER FÜNF'), ('eins zwei drei vier fünf sechs sieben acht neun', 'ACHT NEUN'),
                       ('Ha, das war knapp, Leute', 'LEUTE'), ('Das glaub ich dir nicht ja', 'NICHT JA')):
        chunks = [c[2] for c in fv.caption_chunks(text, 0, 3)]
        assert chunks[-1] == last and all(len(c.split()) <= 4 for c in chunks), chunks
        assert sum(len(c.split()) for c in chunks) == len(text.split())


def test_camera_per_shot_type():
    talk = {'seconds': 6.0, 'lines': [{'offset': .08}, {'offset': 3.1}], 'kind': 'line'}
    z = fv.camera(talk, 0., 25)
    assert '0.06' in z and '1.12' in z and '3.100000' in z                    # push-in plus punch-in at line 2
    assert fv.camera({'seconds': 3.0, 'lines': [{'offset': .08}], 'kind': 'line'}, 0., 25) is None    # short single line: still
    assert '0.04' in fv.camera({'seconds': 3.0, 'lines': [{'offset': .08}], 'kind': 'reaction'}, 0., 25)
    assert fv.camera({'seconds': 3.2, 'lines': [], 'kind': 'action'}, 0., 25) is None             # Wan already moves
    assert '+1.500000' in fv.camera(talk, 1.5, 25)                                 # second clip continues the move


def clip(path, seconds=5.04, edge=True):
    src = 'color=c=black:s=576x1024:r=25:d=%s' % seconds + (',drawbox=x=480:y=0:w=96:h=1024:color=white:t=fill' if edge else '')
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', src, '-pix_fmt', 'yuv420p', str(path)], check=True)
    return {'file': str(path), 'sha256': fv.file_hash(path), 'seconds': seconds}


def line(path, offset, duration, text):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=frequency=200:duration={duration}', '-ar', '24000', '-ac', '1', str(path)], check=True)
    return {'file': str(path), 'sha256': fv.file_hash(path), 'offset': offset, 'duration': duration, 'text_de': text}


def run(tmp, policy):
    folder = tmp / f'out{policy}'
    scene = {'seconds': 5.04, 'clips': [clip(tmp / 'c.mp4')], 'kind': 'line',
             'lines': [line(tmp / 'a.wav', .08, 2.4, 'Wo ist mein Stein, Patrick?'), line(tmp / 'b.wav', 2.7, 2.0, 'Ich hab ihn nicht!')]}
    spec = {'folder': str(folder), 'fps': 25, 'smooth': False, 'scenes': [scene], 'part_label': 'Teil 1/3', **({'edit_policy': 18} if policy == 18 else {})}
    result = fv.prepare(spec)
    return folder, result


def edge_x(part, t):
    import numpy as np
    raw = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-ss', str(t), '-i', str(part), '-frames:v', '1', '-vf', 'format=gray', '-f', 'rawvideo', '-'],
                         capture_output=True, check=True).stdout
    row = np.frombuffer(raw, dtype=np.uint8).reshape(1920, 1080).astype(float)[1300]
    i = int(np.argmax(row > 128)); return i - 1 + (128 - row[i - 1]) / (row[i] - row[i - 1])


def test_legacy_export_is_unchanged_and_018_adds_captions_and_camera(tmp_path):
    folder, result = run(tmp_path, 17)
    ass = (folder / 'Untertitel.ass').read_text()
    assert 'Caption' not in ass and 'Teil 1/3' in ass and ',Default,,0,0,0,,Wo ist mein Stein, Patrick?' in ass
    assert len(result['parts']) == 1
    folder18, result18 = run(tmp_path, 18)
    ass18 = (folder18 / 'Untertitel.ass').read_text()
    assert fv.CAPTION_STYLE in ass18 and ',Caption,,0,0,0,,WO IST MEIN STEIN,\n' in ass18 and 'Teil 1/3' in ass18
    assert result18['parts'][0] != result['parts'][0]                             # own cache key for the 0.18 look
    part = folder18 / result18['parts'][0]
    frames = int(subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-select_streams', 'v', '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', str(part)], capture_output=True, text=True).stdout.strip())
    assert frames == 126
    shots = {}
    for name, t in (('start', .2), ('before', 2.6), ('after', 2.8), ('end', 4.9)):
        shots[name] = edge_x(part, t)
    # Edge at x=900 of 1080 moves out as the camera pushes in; the punch-in at line 2 jumps.
    assert shots['start'] < shots['before'] < shots['after'] < shots['end']
    assert shots['after'] - shots['before'] > 30 and shots['before'] - shots['start'] < 15


def test_cover_first_hides_the_part_label(tmp_path):
    scene = {'seconds': 2.0, 'clips': [clip(tmp_path / 'c.mp4', 2.0, False)], 'lines': [], 'kind': 'action'}
    spec = {'folder': str(tmp_path / 'o'), 'fps': 25, 'smooth': False, 'scenes': [scene], 'part_label': 'Teil 2/3', 'edit_policy': 18, 'cover': {'position': 'start'}}
    fv.prepare(spec)
    assert 'Teil 2/3' not in (tmp_path / 'o' / 'Untertitel.ass').read_text()


def voice(path, seconds):
    n = int(seconds * 24000); data = array('f', [0]) * n
    for i in range(n):
        t = i / 24000; env = max(0, math.sin(math.pi * 4 * t)) ** .5
        data[i] = .25 * env * (math.sin(math.tau * 160 * t) + .5 * math.sin(math.tau * 320 * t))
    fa.write_wav(path, data)
    return {'file': str(path), 'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(), 'duration': seconds, 'offset': .08, 'emotion': 'ruhig', 'key': Path(path).name, 'speaker': 'A'}


def rms_db(path, a, b):
    with wave.open(str(path)) as w:
        rate = w.getframerate(); ch = w.getnchannels(); data = array('h', w.readframes(w.getnframes()))
    seg = data[int(a * rate) * ch:int(b * rate) * ch]
    return 20 * math.log10(max(1e-9, math.sqrt(sum(x * x for x in seg) / len(seg)) / 32768))


def test_sound_bed_is_audible_and_continuous_only_for_018(tmp_path):
    l1 = voice(tmp_path / 'l1.wav', 3.0)
    settings = {'music_mode': 'off', 'music_level': .7, 'effects_level': .65, 'ambience_level': .6}
    levels = {}
    for ambience in ('room', 'wind'):
        scenes = [{'seconds': 3.4, 'lines': [l1], 'ambience': ambience, 'sound_cues': [], 'kind': 'line'},
                  {'seconds': 3.0, 'lines': [], 'ambience': ambience, 'sound_cues': [], 'kind': 'establish'}]
        for policy in (17, 18):
            out = fa.mix(tmp_path / f'{ambience}{policy}', scenes, 'playful', None, settings, policy)
            levels[ambience, policy] = (rms_db(out, .3, 3.0), rms_db(out, 3.6, 6.2))
    for ambience in ('room', 'wind'):
        speech17, bed17 = levels[ambience, 17]; speech18, bed18 = levels[ambience, 18]
        assert abs(speech18 - speech17) < .5                                       # dialogue loudness unchanged
        assert -44 < bed18 < -37, (ambience, bed18)                                # about 25 dB under the dialogue
    assert levels['room', 17][1] < -60                                             # 0.17 room tone stays as it was


def test_action_shots_open_with_a_whoosh_only_in_018():
    scenes = [{'seconds': 2, 'kind': 'action'}, {'seconds': 2, 'kind': 'action', 'sound_cues': [{'kind': 'door', 'position': .5}]}, {'seconds': 2, 'kind': 'line'}]
    cues = [s['sound_cues'] for s in fa.bed_cues(scenes)]
    assert cues == [[{'kind': 'whoosh', 'position': 0}], [{'kind': 'door', 'position': .5}], []]
    assert fa.edit_spec({'edit_policy': 18}) == {'edit_policy': 18} and fa.edit_spec({}) == {}
