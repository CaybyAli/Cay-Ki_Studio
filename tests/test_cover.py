"""Title card (0.18): lettering, card clip, sound, export with the card, choice and autopilot.

Real FFmpeg/libass and the real finish(). Pictures are flat colours and voices
synthetic signals, no AI models: this proves layout, timing, frame counts and the
speech checks, not the look of a real key art.
"""
import asyncio
import hashlib
import json
import subprocess
import sys
import wave
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path[:0] = [str(APP), str(Path(__file__).parent)]

import audio_fixtures as fx  # noqa: E402
import cast_design  # noqa: E402
import cover  # noqa: E402
import speech_check  # noqa: E402
from factory_audio import mix  # noqa: E402
from factory_video import file_hash, finish, probe  # noqa: E402
from image_workflow import png_info  # noqa: E402


def picture(path, colour, size='864x1536'):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c={colour}:s={size}:d=1', '-frames:v', '1', str(path)], check=True)
    return path


def gray(path, index=None):
    """Width, height and 8-bit gray pixels of a PNG (or of one frame of a video)."""
    args = ['-vf', f'select=eq(n\\,{index})'] if index is not None else []
    out = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), *args, '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                         capture_output=True, check=True).stdout
    return 1080, len(out) // 1080, out


def box(pixels, width, keep):
    """Bounding box (left, top, right, bottom) of the pixels that satisfy keep."""
    xs, ys = [], []
    for y in range(len(pixels) // width):
        row = pixels[y * width:(y + 1) * width]
        hits = [x for x in range(0, width) if keep(row[x])]
        if hits: xs += [hits[0], hits[-1]]; ys.append(y)
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1) if ys else None


def lower_half_rgb(video, index):
    out = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(video), '-vf', f'select=eq(n\\,{index}),scale=36:64', '-frames:v', '1',
                          '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
    lower = out[len(out) // 2:]
    return [sum(lower[c::3]) / (len(lower) // 3) for c in range(3)]


def is_card(video, index):
    r, g, b = lower_half_rgb(video, index)       # the key art below the title is flat magenta
    return r > 190 and g < 60 and b > 190


def make_clip(path, seconds):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc2=size=480x832:rate=16:duration={seconds}',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(path)], check=True)
    return {'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'seconds': seconds}


def char_widths(texts):
    """Stand-in for the libass measurement: 0.72 em per character at REF."""
    return [round(len(t) * cover.REF * .72) for t in texts]


# ---------- lettering ----------

def test_lettering_is_1080x1920_fits_and_sits_in_the_upper_third(tmp_path):
    out = tmp_path / 'Titelbild.png'
    plan = cover.letter(picture(tmp_path / 'grau.png', '0x808080'), out, 'Phineas in the Hood', 'Teil 2')
    info = png_info(out)
    assert (info['width'], info['height']) == (1080, 1920)
    assert plan['lines'] == ['PHINEAS IN', 'THE HOOD'] and plan['pill']['text'] == 'TEIL 2'
    width, _, pixels = gray(out)
    left, top, right, bottom = box(pixels, width, lambda v: v >= 235)     # white letters (title and "TEIL 2")
    assert .6 * 1080 <= right - left <= cover.TARGET * 1080 + 2, (left, right)
    assert top >= cover.SAFE_TOP and bottom <= .4 * 1920, (top, bottom)    # inside TikTok's 3:4 grid crop, upper part
    assert sum(1 for v in pixels if v <= 40) > 20000                       # thick dark outline


@pytest.mark.parametrize('colour', ['white', 'black', '0xffd23f'])
def test_lettering_reads_on_any_background(tmp_path, colour):
    out = tmp_path / 'Titelbild.png'
    cover.letter(picture(tmp_path / 'bg.png', colour), out, 'Der letzte Keks', '')
    width, _, pixels = gray(out)
    band = pixels[cover.SAFE_TOP * width:700 * width]
    assert sum(1 for v in band if v >= 235) > 15000 and sum(1 for v in band if v <= 40) > 15000   # white fill and dark edge


def test_teil_pill_only_for_a_series(tmp_path):
    base = picture(tmp_path / 'bg.png', '0x808080')
    single, series = tmp_path / 'einzeln.png', tmp_path / 'serie.png'
    cover.letter(base, single, 'Keks', ''); plan = cover.letter(base, series, 'Keks', 'Teil 12')
    width, _, a = gray(single); _, _, b = gray(series)
    pill = plan['pill']; rows = range(pill['y'] + 4, pill['y'] + pill['h'] - 4); cols = range(pill['x'] + 6, pill['x'] + pill['w'] - 6)
    dark_a = sum(1 for y in rows for x in cols if a[y * width + x] <= 60)
    dark_b = sum(1 for y in rows for x in cols if b[y * width + x] <= 60)
    assert dark_a == 0 and dark_b > .5 * len(rows) * len(cols)               # a dark pill with light text under the title
    assert pill['y'] > plan['tops'][-1] + plan['size']


def test_layout_one_or_two_lines_and_shortened_titles():
    one = cover.layout('Keks', '', char_widths)
    assert one['lines'] == ['KEKS'] and one['size'] == cover.MAX_SIZE[1] and one['pill'] is None
    two = cover.layout('Der Einbruch im Krusty-Versteck', 'Teil 3', char_widths)
    assert len(two['lines']) == 2 and two['pill']['text'] == 'TEIL 3'
    widest = max(len(line) for line in two['lines']) * .72 * two['size'] + 2 * cover.BORDER * two['size']
    assert widest <= cover.TARGET * 1080 + 1 and two['size'] >= cover.MIN_SIZE
    long = cover.layout('Grüße aus München: die unglaubliche Reise der kleinen Schnecke über die Alpen bis nach Rom', 'Teil 1', char_widths)
    assert len(long['lines']) <= 2 and long['lines'][-1].endswith('…') and long['size'] >= cover.MIN_SIZE
    assert 'GRÜSSE' in long['lines'][0]                                       # upper case, ß as SS
    for plan in (one, two, long): assert plan['tops'][0] >= cover.SAFE_TOP and plan['tops'][-1] + plan['size'] < 1920 / 3 + 120


def test_title_and_label():
    assert cover.cover_title({'title': 'Der letzte Keks · neue Fassung · neue Fassung'}) == 'Der letzte Keks'
    assert cover.part_label({'idea': {'episodes': 3}, 'episodes': [{}, {}, {}]}, 1) == 'Teil 2'
    assert cover.part_label({'idea': {'episodes': 1}, 'episodes': [{}]}, 0) == ''


# ---------- card clip and sound ----------

@pytest.mark.parametrize('fps', [25, 30])
def test_card_is_one_second_with_a_push_in(tmp_path, fps):
    still = tmp_path / 'Titelbild.png'
    cover.letter(picture(tmp_path / 'bg.png', '0x808080'), still, 'Keks', '')
    clip = tmp_path / 'Titelkarte.mp4'
    assert cover.card_clip(still, clip, fps, tmp_path) == fps
    stream = next(s for s in probe(clip)['streams'] if s['codec_type'] == 'video')
    assert int(stream['nb_frames']) == fps and (stream['width'], stream['height']) == (1080, 1920)
    assert stream['avg_frame_rate'] == f'{fps}/1' and stream['pix_fmt'] == 'yuv420p'
    first = box(gray(clip, 0)[2], 1080, lambda v: v >= 235); last = box(gray(clip, fps - 1)[2], 1080, lambda v: v >= 235)
    zoom = (last[2] - last[0]) / (first[2] - first[0])
    assert 1.07 <= zoom <= 1.13, zoom                                         # about 1.00 -> 1.10


def test_impact_is_a_short_sub_bass_hit():
    rate = 48000; hit = cover.impact(rate, 1.0)
    assert len(hit) == rate and max(abs(v) for v in hit) <= .9
    rms = lambda a, b: (sum(v * v for v in hit[round(a * rate):round(b * rate)]) / ((b - a) * rate)) ** .5
    assert rms(0, .3) > 10 * rms(.9, 1.0) and abs(hit[-1]) < 1e-3          # decays, lands at zero on the cut
    body = hit[round(.05 * rate):round(.5 * rate)]
    crossings = sum(1 for x, y in zip(body, body[1:]) if (x < 0) != (y < 0))
    assert 35 <= crossings / 2 / .45 <= 100                                   # fundamental between 40 and 90 Hz


def test_splice_is_sample_exact(tmp_path):
    source = tmp_path / 'mix.wav'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', '-ar', '48000', '-ac', '2',
                    '-c:a', 'pcm_s16le', str(source)], check=True)
    out = cover.splice(source, tmp_path / 'mit_karte.wav', 1.0, 1.0)
    with wave.open(str(source)) as a, wave.open(str(out)) as b:
        assert b.getnframes() == a.getnframes() + 48000 and b.getframerate() == 48000 and b.getnchannels() == 2
        original = a.readframes(a.getnframes()); spliced = b.readframes(b.getnframes())
    edge = round(cover.SPLICE_FADE * 48000) * 4
    assert spliced[:48000 * 4 - edge] == original[:48000 * 4 - edge]                        # before the card: untouched
    assert spliced[2 * 48000 * 4 + edge:] == original[48000 * 4 + edge:]                    # after it: the film, one second later


def test_insertion_and_speech_shift():
    scenes = [{'seconds': 2.08, 'clips': [{'seconds': 1.0}, {'seconds': 1.08}]}, {'seconds': 3., 'clips': [{'seconds': 3.}]}]
    assert cover.insertion(scenes, 25, 'start') == (0, 0.)
    assert cover.insertion(scenes, 25, 'after_hook') == (2, 2.08)
    from array import array
    approved = array('h', [7] * 24000 * 4)
    placed = [(.12, 1.5, {'speaker': 'Max'}), (2.2, 3.0, {'speaker': 'Lina'})]
    lines, shifted = cover.shift_check(placed, approved, {'at': 2.08, 'seconds': 1.0})
    assert [(round(s, 2), round(e, 2)) for s, e, _ in lines] == [(.12, 1.5), (3.2, 4.0)]
    assert len(shifted) == len(approved) + 24000 and shifted[round(2.08 * 24000)] == 0 and shifted[-1] == 7


# ---------- export with the card ----------

def film(tmp_path, position=None, fps=25):
    a = fx.line(tmp_path, 'E01_S01_T01', 0, 0, 0, 'Max', 'Wo warst du?', fx.speech(1.5))
    b = fx.line(tmp_path, 'E01_S02_T01', 0, 1, 0, 'Lina', 'Weg von hier!', fx.speech(1.2, pitch=220))
    scenes = [{'seconds': 2., 'lines': [line], 'ambience': 'room', 'sound_cues': []} for line in (a, b)]
    approved = Path(mix(tmp_path / 'mix', scenes, 'playful'))
    for i, scene in enumerate(scenes): scene['clips'] = [make_clip(tmp_path / f'clip{i}.mp4', 2.)]
    spec = {'folder': str(tmp_path / 'work'), 'fps': fps, 'smooth': False, 'scenes': scenes, 'title': 'Test',
            'output': str(tmp_path / 'Fertig' / 'Folge_01.mp4'), 'minimum_seconds': 4, 'mood': 'playful', 'mix': None, 'music': None,
            'audio_mix': {'file': str(approved), 'sha256': file_hash(approved)}}
    if position:
        art = picture(tmp_path / 'keyart.png', '0xff00ff')
        spec['cover'] = {'position': position, 'image': str(art), 'sha256': file_hash(art), 'title': 'Der letzte Keks', 'label': 'Teil 1'}
    return spec


@pytest.mark.parametrize('position,fps', [('start', 25), ('after_hook', 25), ('start', 30)])
def test_export_with_title_card(tmp_path, position, fps):
    spec = film(tmp_path, position, fps)
    result = finish(spec)
    out = Path(spec['output']); info = probe(out); video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    assert result['seconds'] == 5.0 and int(video['nb_frames']) == 5 * fps and abs(float(info['format']['duration']) - 5.0) < .12
    at = 0 if position == 'start' else 2 * fps                                 # the card: frames at .. at+fps-1
    assert is_card(out, at) and is_card(out, at + fps - 1) and not is_card(out, at + fps)
    if at: assert not is_card(out, 0) and not is_card(out, at - 1)
    decoded = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(out), '-f', 'null', '-'], capture_output=True)
    assert decoded.returncode == 0 and not decoded.stderr                       # the copied concat decodes cleanly across the card
    report = json.loads((Path(spec['folder']) / 'Exportpruefung.json').read_text())
    assert report['checked'] == 2 and report['blocking'] == 0
    assert [e['start'] for e in report['lines']] == ([1.12, 3.12] if position == 'start' else [.12, 3.12])
    poster = out.with_name('Cover_Folge_01.png')
    assert result['cover'] == {'file': str(poster), 'sha256': file_hash(poster), 'position': position, 'seconds': 1.0}
    assert (png_info(poster)['width'], png_info(poster)['height']) == (1080, 1920)
    sound = speech_check.decode(out); card = sound[round(at / fps * 24000):round((at / fps + 1) * 24000)]
    assert (sum(v * v for v in card) / len(card)) ** .5 > 1000                  # the impact is under the card


def test_export_without_title_card_is_unchanged(tmp_path):
    spec = film(tmp_path)
    result = finish(spec)
    out = Path(spec['output']); video = next(s for s in probe(out)['streams'] if s['codec_type'] == 'video')
    assert set(result) == {'file', 'sha256', 'seconds', 'fps', 'performance'} and result['seconds'] == 4.0 and int(video['nb_frames']) == 100
    work = Path(spec['folder'])
    assert 'Titelkarte' not in (work / 'Clips.txt').read_text() and len((work / 'Clips.txt').read_text().splitlines()) == 2
    assert not list(work.glob('Titel*')) and not list(out.parent.glob('Cover_*'))
    assert [e['start'] for e in json.loads((work / 'Exportpruefung.json').read_text())['lines']] == [.12, 2.12]


def test_line_lost_around_the_card_is_still_caught(tmp_path, monkeypatch):
    spec = film(tmp_path, 'after_hook')
    real = cover.splice

    def lossy(source, target, at, seconds):
        path = real(source, target, at, seconds)
        with wave.open(str(path)) as stream: params = stream.getparams(); data = bytearray(stream.readframes(stream.getnframes()))
        start = round(3.0 * params.framerate) * params.nchannels * 2
        data[start:] = bytes(len(data) - start)                               # Lina's line (3.12 s in the film) lost
        with wave.open(str(path), 'wb') as stream: stream.setparams(params); stream.writeframes(bytes(data))
        return path
    monkeypatch.setattr(cover, 'splice', lossy)
    with pytest.raises(speech_check.SpeechCheckError) as caught:
        finish(spec)
    assert 'Lina' in str(caught.value) and not Path(spec['output']).exists()


def test_changed_key_art_stops_the_export(tmp_path):
    spec = film(tmp_path, 'start')
    picture(Path(spec['cover']['image']), '0x00ff00')
    with pytest.raises(RuntimeError, match='Titelbild wurde verändert'):
        finish(spec)


# ---------- project rules ----------

def variants(*ids, round_=0):
    return [{'id': i, 'key': f'cover:0:{round_}:{slot}'} for slot, i in enumerate(ids)]


def test_only_new_projects_need_a_cover():
    assert not cover.wanted({'idea': {'cover': 'start'}})                     # before 0.18: no edit_policy
    assert not cover.wanted({'edit_policy': 18, 'idea': {'cover': 'off'}})
    d = {'edit_policy': 18, 'idea': {'cover': 'after_hook'}, 'cover': {'variants': variants('a' * 32, 'b' * 32), 'selected': None, 'round': 0}}
    assert cover.wanted(d) and not cover.chosen(d)
    d['cover']['selected'] = 'b' * 32; assert cover.chosen(d)
    from factory_editor import regenerate
    regenerate(d['cover'], [0, 1]); assert not cover.chosen(d)                # new round: choose again


def test_old_idea_documents_validate_and_new_clients_choose():
    from pydantic import ValidationError
    from factory_models import Idea
    old = {'request_key': 'a' * 32, 'idea': 'Zwei Kollegen streiten um den letzten Keks.', 'title': '', 'episodes': 1, 'duration': 60,
           'look': 'auto', 'characters': 'invent', 'participants': [], 'examples': [], 'music': None, 'fps': 25, 'quality': 'fast',
           'smooth': True, 'speech_engine': 'auto', 'lip_sync': 'audio', 'autopilot': False, 'cast_check': False}
    body = Idea.model_validate(old)
    assert body.cover == 'start' and cover.idea_document(body)['cover'] == 'off'   # classic view and old scripts: no card
    assert cover.idea_document(Idea.model_validate({**old, 'cover': 'after_hook'}))['cover'] == 'after_hook'
    assert cover.idea_document(Idea.model_validate({**old, 'cover': 'start'}))['cover'] == 'start'
    with pytest.raises(ValidationError):
        Idea.model_validate({**old, 'cover': 'middle'})


def test_autopilot_takes_the_first_cover():
    from autopilot import Autopilot

    class Fake(Autopilot):
        def path(self, p): return Path(p)
    scene = {'variants': [{'id': 'c' * 32, 'key': 'image:0:0:0:0'}, {'id': 'd' * 32, 'key': 'image:0:0:0:1'}], 'selected': None, 'round': 0}
    d = {'edit_policy': 18, 'idea': {'autopilot': True, 'cover': 'start'}, 'state': 'image_review', 'episodes': [{'scenes': [dict(scene)]}],
         'cover': {'variants': variants('a' * 32, 'b' * 32), 'selected': None, 'round': 0}}
    assert Fake().apply_autopilot(d) and d['cover']['selected'] == 'a' * 32 and d['state'] == 'voicing'
    waiting = {**d, 'state': 'image_review', 'cover': {'variants': [], 'selected': None, 'round': 0}, 'episodes': [{'scenes': [dict(scene)]}]}
    assert not Fake().apply_autopilot(waiting) and waiting['state'] == 'image_review'
    old = {'idea': {'autopilot': True, 'cover': 'start'}, 'state': 'image_review', 'episodes': [{'scenes': [dict(scene)]}]}
    assert Fake().apply_autopilot(old) and 'cover' not in old and old['state'] == 'voicing'


# ---------- key art ----------

CAST = [{'name': 'SpongeBob', 'appearance': 'yellow sponge with square pants', 'original': ''},
        {'name': 'Patrick', 'appearance': 'pink starfish', 'original': ''},
        {'name': 'Mr. Krabs', 'appearance': 'red crab', 'original': ''},
        {'name': 'Gary', 'appearance': 'small snail', 'original': ''}]


def scene(cast, lines, location='Krusty Krab kitchen'):
    return {'title': 't', 'action': 'a', 'location': location, 'camera': 'c', 'continuity': 'x', 'cast': cast, 'variants': [],
            'dialogues': [{'speaker': s, 'text': 'Hallo', 'emotion': 'ruhig'} for s in lines]}


def project():
    return {'id': 'r9', 'title': 'Der letzte Keks', 'edit_policy': 18, 'idea': {'cover': 'start', 'participants': [], 'examples': [], 'episodes': 1},
            'plan': {'style': 'Handmade claymation look, Gary-style shell props', 'cast': [dict(p) for p in CAST]},
            'episodes': [{'scenes': [scene(['Patrick', 'SpongeBob'], ['Patrick', 'SpongeBob', 'Patrick']), scene(['Mr. Krabs'], ['Mr. Krabs']),
                                     scene(['Gary'], [], 'Garden'), scene(['Patrick'], ['Patrick'])]}]}


def test_main_cast_and_prompt():
    d = project(); names = cover.main_cast(d)
    assert names == ['Patrick', 'SpongeBob', 'Mr. Krabs']                    # most lines first, at most three
    text = cover.prompt(d, names, 0)
    assert all(f'approved design of {n}' in text for n in names) and 'Gary' not in text
    assert 'Krusty Krab kitchen' in text and 'upper third' in text and 'no text, letters' in text
    assert text != cover.prompt(d, names, 1) and 'Specific correction: closer together' in cover.prompt(d, names, 0, 'closer together')
    silent = {'plan': {'style': 'film', 'cast': []}, 'episodes': [{'scenes': [scene([], [], 'Harbour')]}]}
    assert cover.main_cast(silent) == [] and 'No characters' in cover.prompt(silent, [], 0)


class Recorder(cover.TitleCard):
    """Only what cover_pictures and pictures need; ComfyUI replaced by a recorder."""
    def __init__(self, paused=False):
        self.calls = []; self.paused_ = paused
    async def render(self, document, key, graph, video=False):
        refs = [n['inputs']['image'] for n in graph.values() if n['class_type'] == 'LoadImage']
        prompt = next(n['inputs']['text'] for n in graph.values() if n['class_type'] == 'CLIPTextEncode')
        self.calls.append({'key': key, 'refs': refs, 'prompt': prompt})
        return {'id': hashlib.md5(key.encode()).hexdigest(), 'output': f'/out/{key}.png'}
    def stage(self, path): return 'staged/' + Path(path).name
    def save(self, d): pass
    def paused(self, rid): return self.paused_
    def apply_pending(self, d): return False


def test_key_art_variants_and_redraw_after_a_figure_change():
    d = project(); refs = {p['name']: f'/designs/{p["name"]}.png' for p in CAST}; fake = Recorder()
    assert asyncio.run(fake.cover_pictures(d, refs, {})) is True
    assert [c['key'] for c in fake.calls] == ['cover:0:0:0', 'cover:0:0:1']
    assert fake.calls[0]['refs'] == ['staged/Patrick.png', 'staged/SpongeBob.png', 'staged/Mr. Krabs.png']
    assert asyncio.run(fake.cover_pictures(d, refs, {})) and len(fake.calls) == 2   # done variants are kept
    d['cover']['selected'] = d['cover']['variants'][0]['id']
    cast_design.invalidate(d, 'Gary')
    assert d['cover']['selected'] and 'image_rounds' not in d['cover']           # not on the cover: unchanged
    cast_design.invalidate(d, 'SpongeBob')
    assert d['cover']['selected'] is None and d['cover']['image_rounds'] == [1, 1]
    asyncio.run(fake.cover_pictures(d, refs, {}))
    assert [c['key'] for c in fake.calls[2:]] == ['cover:0:1:0', 'cover:0:1:1']
    paused = Recorder(paused=True)
    assert asyncio.run(paused.cover_pictures(project(), refs, {})) is False and not paused.calls


def test_pictures_draws_the_cover_between_figures_and_scenes():
    pytest.importorskip('fastapi')
    import factory

    class Fake(Recorder):
        async def object_info(self): return {}
        def asset(self, aid, kind=None): return {'path': f'/assets/{aid}.png'}
    original = factory.validate_nodes
    factory.validate_nodes = lambda info: {}
    try:
        fake = Fake(); d = project()
        asyncio.run(factory.Factory.pictures(fake, d))
    finally:
        factory.validate_nodes = original
    kinds = [c['key'].split(':')[0] for c in fake.calls]
    assert kinds == ['cast3'] * 4 + ['cover'] * 2 + ['image'] * 8 and d['state'] == 'image_review'
    old = project(); old.pop('edit_policy'); fake = Fake()
    factory.validate_nodes = lambda info: {}
    try: asyncio.run(factory.Factory.pictures(fake, old))
    finally: factory.validate_nodes = original
    assert not [c for c in fake.calls if c['key'].startswith('cover')] and 'cover' not in old


# ---------- choice, new variants, preview, download (the routes of the mixin) ----------

class Routes(cover.TitleCard):
    """The mixin's routes on an in-memory project store; steps as rows like factory_steps."""
    def __init__(self, tmp_path):
        import copy
        self.copy = copy; self.docs = {}; self.steps = {}; self.base = tmp_path; self.records = []
        self.g = {'record': lambda kind, text: self.records.append((kind, text))}
    def get(self, rid):
        from factory_editor import active_variants
        from fastapi import HTTPException
        if rid not in self.docs: raise HTTPException(404, 'Projekt nicht gefunden.')
        d = self.copy.deepcopy(self.docs[rid])
        if isinstance(d.get('cover'), dict): d['cover']['active_variants'] = active_variants(d['cover'])
        return d
    def save(self, d): self.docs[d['id']] = self.copy.deepcopy(d)
    def rows(self, query, args):
        return [self.steps[a] for a in args if a in self.steps]
    def path(self, p): return Path(p)
    def folder(self, d): return self.base / d['id']


def endpoints(fake):
    from fastapi import FastAPI
    app = FastAPI(); fake.cover_routes(app)
    return {(next(iter(r.methods)), r.path.split('/cover/')[1].split('/')[0]): r.endpoint for r in app.routes if '/cover/' in getattr(r, 'path', '')}


def call(endpoint, *args, **kwargs):
    result = endpoint(*args, **kwargs)
    return asyncio.run(result) if asyncio.iscoroutine(result) else result


def test_choose_revise_preview_and_download(tmp_path):
    from fastapi import HTTPException
    from factory_models import CoverChoice, CoverRevise
    fake = Routes(tmp_path); routes = endpoints(fake); rid = 'e' * 32
    art = [picture(tmp_path / f'art{k}.png', colour) for k, colour in enumerate(('0xff00ff', '0x00aaff'))]
    for k, path in enumerate(art): fake.steps[f'{k:032x}'] = {'output': str(path), 'sha256': file_hash(path)}
    d = {'id': rid, 'title': 'Der letzte Keks', 'state': 'image_review', 'edit_policy': 18, 'idea': {'cover': 'start', 'episodes': 2},
         'episodes': [{}, {}], 'cover': {'variants': variants(f'{0:032x}', f'{1:032x}'), 'selected': None, 'round': 0}}
    fake.save(d)
    with pytest.raises(HTTPException) as foreign:
        call(routes['POST', 'choose'], rid, CoverChoice(step_id='f' * 32))
    assert foreign.value.status_code == 400
    assert call(routes['POST', 'choose'], rid, CoverChoice(step_id=f'{1:032x}'))['cover']['selected'] == f'{1:032x}'
    preview = call(routes['GET', 'preview'], rid, f'{1:032x}')
    lettered = Path(preview.path)
    assert lettered != art[1] and (png_info(lettered)['width'], png_info(lettered)['height']) == (1080, 1920) and not fake.records
    assert call(routes['GET', 'preview'], rid, f'{1:032x}').path == preview.path            # cached: lettered once
    after = call(routes['POST', 'revise'], rid, CoverRevise(note='Alle drei näher zusammen'))
    assert after['state'] == 'pictures' and after['cover']['selected'] is None and after['cover']['image_rounds'] == [1, 1]
    assert after['cover']['note'] == 'Alle drei näher zusammen' and after['cover']['active_variants'] == []
    with pytest.raises(HTTPException) as busy:                                              # no choice while the studio draws
        call(routes['POST', 'choose'], rid, CoverChoice(step_id=f'{1:032x}'))
    assert busy.value.status_code == 409
    # Old project: no card, nothing to choose or preview
    old = {**d, 'id': 'o' * 32, 'state': 'image_review'}; old.pop('edit_policy'); fake.save(old)
    with pytest.raises(HTTPException) as refused:
        call(routes['POST', 'choose'], old['id'], CoverChoice(step_id=f'{0:032x}'))
    assert refused.value.status_code == 409
    with pytest.raises(HTTPException) as missing:
        call(routes['GET', 'preview'], old['id'], f'{0:032x}')
    assert missing.value.status_code == 404
    # Done: the title card of the export, as a download
    poster = tmp_path / 'Cover_Folge_01.png'; cover.letter(art[0], poster, 'Der letzte Keks', 'Teil 1')
    fake.save({**d, 'state': 'done', 'exports': [{'file': 'x.mp4', 'cover': {'file': str(poster)}}, {'file': 'y.mp4'}]})
    response = call(routes['GET', 'export'], rid, 0, download=True)
    assert Path(response.path) == poster and 'Cover_Folge_01.png' in response.headers['content-disposition']
    with pytest.raises(HTTPException) as none:
        call(routes['GET', 'export'], rid, 1)
    assert none.value.status_code == 404


def test_export_spec_carries_the_chosen_card(tmp_path):
    fake = Routes(tmp_path); art = picture(tmp_path / 'art.png', '0xff00ff'); sid = 'a' * 32
    fake.steps[sid] = {'output': str(art), 'sha256': file_hash(art)}
    d = {'id': 'e' * 32, 'title': 'Der letzte Keks · neue Fassung', 'edit_policy': 18, 'idea': {'cover': 'after_hook', 'episodes': 3},
         'episodes': [{}, {}, {}], 'cover': {'variants': variants(sid, 'b' * 32), 'selected': sid, 'round': 0}}
    assert fake.cover_spec(d, 2) == {'position': 'after_hook', 'image': str(art), 'sha256': file_hash(art), 'title': 'Der letzte Keks', 'label': 'Teil 3'}
    picture(art, '0x00ff00')                                                                 # changed outside the studio
    with pytest.raises(RuntimeError, match='außerhalb des Studios verändert'):
        fake.cover_spec(d, 0)
