"""Title card (0.18): one key-art picture per project with the film's title on it.

Cay: "Am Anfang siehst du auch immer ein Bild mit dem Cover ... damit ich bei
TikTok, wenn man auf mein Kanal geht, sieht welche Videoreihe das jetzt ist."
TikTok shows the first frame of a video on the channel grid. The card is the
film's first second (or follows the first shot, like the template's cold open):
the main cast at the main location, the title in big letters, for a series a
small "Teil N" under it. Template measured: 1.0 s, push-in ~10 %/s, sub-bass hit.

Pieces:
- cast choice and prompt for the FLUX key art (two variants, Cay picks one),
- lettering with FFmpeg/libass, the engine that already burns the subtitles of
  every film. Pillow is not a dependency of the dashboard (no dashboard module
  imports it, the test environment with all dashboard packages has none) and
  the update never installs packages, so the card adds no new dependency.
  Widths are measured by rendering the candidate lines with the same font, so
  the fit is exact for the real output,
- the 1 s card clip (slow push-in, same encoder settings as every film part),
- the sub-bass impact under the card and the sample-exact sound around it,
- the factory mixin: key art, choice, new variants, preview and download.

Only projects created since 0.18 (edit_policy 18) get a card. Older projects
have no 'cover' in their export spec, so finish() runs exactly as before.
"""
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import wave
from array import array
from collections import Counter
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

import cast_design
from factory_editor import active_variants, image_rounds, regenerate
from factory_video import ff, file_hash, probe
from image_workflow import build_graph, png_info

POLICY = 18                  # d['edit_policy'] from which projects have a title card
LETTER_POLICY = 1            # lettering version: part of the preview cache name
POSITIONS = ('start', 'after_hook')
WIDTH, HEIGHT = 1080, 1920
TARGET = .88                 # widest title line including its outline: 88 % of the frame width
BORDER = .08                 # outline thickness relative to the font size
MAX_SIZE = {1: 190, 2: 150}  # font size cap for one and for two lines (px)
MIN_SIZE = 64                # below this a title is shortened with "…" rather than shrunk further
MAX_CHARS = 56               # longer titles cannot be read on a phone in two lines
PITCH = 1.02                 # line distance relative to the font size (capitals only)
CENTER_Y = .245              # middle of the title block: upper third of the frame
SAFE_TOP = 250               # TikTok's 3:4 channel grid cuts ~240 px off the top of a 9:16 frame
REF = 48                     # measuring size (px)
ZOOM = .10                   # push-in over the card: 1.00 -> 1.10
RATE_CHECK = 24000           # sample rate of the export speech check (speech_check.decode)
SPLICE_FADE = .008           # seconds of fade at the edges of the film sound around the card
FONTS = (('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 'DejaVu Sans'),
         ('/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf', 'Liberation Sans'),
         ('/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf', 'Liberation Sans'),
         ('/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf', 'Noto Sans'),
         ('/usr/share/fonts/truetype/freefont/FreeSansBold.ttf', 'FreeSans'))
COMPOSITION = ('Eye-level medium-wide shot, the figures fill the lower two thirds. ',
               'Low camera angle, slightly wider shot, heroic and bold. ')


# ---------- project ----------

def wanted(d):
    """True if this project gets a title card (new projects only, and Cay did not switch it off)."""
    return d.get('edit_policy', 0) >= POLICY and (d.get('idea') or {}).get('cover', 'off') in POSITIONS


def idea_document(body):
    """The idea as a new project stores it. Only the new app offers the title card: a client that
    does not send the field (the classic view, older scripts) cannot show the choice, so no card."""
    idea = body.model_dump()
    if 'cover' not in body.model_fields_set: idea['cover'] = 'off'
    return idea


def chosen(d):
    box = d.get('cover') or {}
    return bool(box.get('selected')) and box['selected'] in [v['id'] for v in active_variants(box)]


def cover_title(d):
    """The film or series title as it goes on the card. "· neue Fassung" names the project, not the series."""
    title = re.sub(r'(\s*·\s*neue Fassung)+\s*$', '', str(d.get('title') or (d.get('plan') or {}).get('title') or '')).strip()
    return title or str((d.get('plan') or {}).get('title') or 'Film')


def part_label(d, episode):
    """'Teil N' for a series (the same key art, the episode differs), empty for a single film."""
    return f'Teil {episode + 1}' if len(d.get('episodes') or []) > 1 or (d.get('idea') or {}).get('episodes', 1) > 1 else ''


def turns(scene):
    return scene.get('dialogues') or ([{'speaker': scene.get('speaker')}] if scene.get('dialogue') else [])


def main_cast(d, limit=3):
    """Up to three figures with the most lines (then the most scenes): the faces of the series."""
    cast = [p['name'] for p in (d.get('plan') or {}).get('cast', [])]
    lines, seen = Counter(), Counter()
    for episode in d.get('episodes', []):
        for scene in episode.get('scenes', []):
            for name in scene.get('cast', []): seen[name] += 1
            for line in turns(scene): lines[line.get('speaker')] += 1
    ranked = sorted(cast, key=lambda n: (-lines[n], -seen[n], cast.index(n)))
    return [n for n in ranked if lines[n] or seen[n]][:limit] or cast[:limit]


def main_location(d, names):
    """The place where the main cast is seen most (first one on a tie)."""
    counts, first = Counter(), {}
    for episode in d.get('episodes', []):
        for scene in episode.get('scenes', []):
            place = str(scene.get('location') or '').strip()
            if not place: continue
            first.setdefault(place, len(first))
            counts[place] += 1 + 2 * len(set(scene.get('cast', [])) & set(names))
    return min(counts, key=lambda p: (-counts[p], first[p])) if counts else ''


def prompt(d, names, variant, note=''):
    """Poster key art in the film's style: main cast side by side at the main location,
    an empty upper third for the title, and no lettering of any kind (FLUX writes gibberish)."""
    from screenplay import figure_aliases
    plan = d['plan']; cast = plan.get('cast', []); aliases = figure_aliases(cast)
    hidden = [p['name'] for p in cast if p['name'] not in names]
    def clean(text): return cast_design.strip_names(text, hidden, names, aliases).strip()
    text = ('One coherent vertical 9:16 poster key art image for a short film series, not a collage. '
            'Visual style: ' + clean(plan.get('style', '')).rstrip('.') + '. ')
    if names:
        who = names[0] if len(names) == 1 else ', '.join(names[:-1]) + ' and ' + names[-1]
        text += (f'{who} {"stands" if len(names) == 1 else "stand side by side"} in the lower two thirds of the picture, facing the viewer, '
                 'full body or from the knees up, confident dynamic poses, '
                 + ('the figure fully visible. ' if len(names) == 1 else 'each figure clearly separated and fully visible. '))
        for i, name in enumerate(names, 1):
            person = next(p for p in cast if p['name'] == name)
            text += (f'Reference image {i} is the approved design of {name}: copy {name}\'s head and face shape, colours, materials, '
                     f'body shape, size and outfit exactly from reference image {i}; pose and expression come from this poster. '
                     f'{clean(person.get("appearance", "")).rstrip(".")}. ')
        text += f'{"Only " + who + " is" if len(names) == 1 else "Only " + who + " are"} in the picture, nobody else. '
    else:
        text += 'No characters: the place itself is the hero of the poster. '
    place = clean(main_location(d, names))
    if place: text += f'Setting: {place}, with its signature props in the background. '
    text += (COMPOSITION[variant % len(COMPOSITION)]
             + 'The upper third of the image is calm and empty, plain sky, wall or soft out-of-focus background, kept free for a title added later. '
             'Dramatic cinematic lighting, strong silhouettes, rich contrast. '
             'Absolutely no text, letters, words, numbers, logos, captions, signs with writing, watermarks, panels or frames.')
    if note: text += ' Specific correction: ' + clean(note)
    return text


# ---------- lettering ----------

def find_font():
    """A bold sans font that Ubuntu/WSL ships (DejaVu comes with FFmpeg's own dependencies)."""
    for path, family in FONTS:
        if Path(path).is_file(): return Path(path), family
    try:
        found = subprocess.run(['fc-match', '-f', '%{family[0]}\n%{file}', 'sans-serif:bold'], capture_output=True, text=True, timeout=15)
        family, _, path = found.stdout.partition('\n')
        if not found.returncode and path.strip() and Path(path.strip()).is_file():
            return Path(path.strip()), family.replace(',', ' ').strip() or 'Sans'
    except (OSError, subprocess.SubprocessError): pass
    raise RuntimeError('Für das Titelbild fehlt eine Schrift. Im Ubuntu-Terminal einmal „sudo apt install fonts-dejavu-core“ ausführen, danach „Fortsetzen“.')


def ass_text(text):
    """Plain text for an ASS event: no override blocks, no escapes, one line."""
    return ' '.join(str(text).replace('\\', '/').replace('{', '(').replace('}', ')').split())


def ass_document(width, height, family, size, events):
    return ('[Script Info]\nScriptType: v4.00+\n'
            f'PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n'
            '[V4+ Styles]\n'
            'Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,'
            'ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n'
            f'Style: T,{family},{size},&H00FFFFFF,&H00FFFFFF,&H00141414,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n'
            '[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'
            + ''.join(f'Dialogue: {layer},0:00:00.00,0:00:10.00,T,,0,0,0,,{text}\n' for layer, text in events))


def measure(texts, folder, family):
    """Ink width in px of each text at REF px, rendered by libass with the cover's font."""
    row = round(REF * 1.5)
    width = max(64, max(len(t) for t in texts) * round(REF * 1.2) + 2 * REF); height = row * len(texts)
    events = [(0, f'{{\\pos({REF},{i * row + REF // 4})}}{ass_text(t)}') for i, t in enumerate(texts)]
    (Path(folder) / 'Messung.ass').write_text(ass_document(width, height, family, REF, events), encoding='utf-8')
    result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', f'color=c=black:s={width}x{height}:d=1',
                             '-vf', 'format=rgb24,subtitles=Messung.ass:fontsdir=Schrift', '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                            cwd=folder, capture_output=True, timeout=180)
    if result.returncode or len(result.stdout) != width * height:
        raise RuntimeError('Titelbild: Die Schrift lässt sich nicht setzen. ' + result.stderr.decode(errors='replace')[-500:])
    data = result.stdout; background = data[:1]; widths = []
    for i in range(len(texts)):
        left, right = width, 0
        for y in range(i * row, (i + 1) * row):
            line = data[y * width:(y + 1) * width]; ink = line.rstrip(background)
            if ink: right = max(right, len(ink)); left = min(left, len(line) - len(line.lstrip(background)))
        widths.append(max(0, right - left))
    return widths


def fit(ink, lines):
    """Largest font size whose line (ink plus outline on both sides) stays within TARGET."""
    if not ink: return MAX_SIZE[lines]
    return max(8, min(MAX_SIZE[lines], math.floor(TARGET * WIDTH / (ink / REF + 2 * BORDER))))


def shorten(title, limit=MAX_CHARS):
    words = title.split()
    if len(title) <= limit or len(words) < 2: return title
    out = words[0]
    for word in words[1:]:
        if len(out) + 1 + len(word) + 1 > limit: break
        out += ' ' + word
    return out + '…'


def layout(title, label, measure_text):
    """Lines, size and positions of the title block: at most two lines, the largest size that fits
    TARGET; a title that would need less than MIN_SIZE is shortened with "…" at a word boundary."""
    words = shorten(' '.join(str(title).upper().split()) or 'FILM').split()
    label = ' '.join(str(label or '').upper().split())
    attempts = [words] + [words[:k - 1] + [words[k - 1] + '…'] for k in range(len(words) - 1, 0, -1)]
    chosen_layout = None; label_ink = 0
    for n, attempt in enumerate(attempts):
        splits = [[' '.join(attempt)]] + [[' '.join(attempt[:i]), ' '.join(attempt[i:])] for i in range(1, len(attempt))]
        texts = sorted({t for split in splits for t in split})
        widths = measure_text(texts + ([label] if label and not n else []))
        if label and not n: label_ink = widths.pop()
        ink = dict(zip(texts, widths))
        best = max(((fit(max(ink[t] for t in split), len(split)), -len(split), split) for split in splits))
        if chosen_layout is None: chosen_layout = best
        if best[0] >= MIN_SIZE: chosen_layout = best; break
    size, _, lines = chosen_layout
    label_size = max(38, min(56, round(size * .36))) if label else 0
    pill_h = round(label_size * 1.65); gap = max(6, round(size * .04))
    block = (len(lines) - 1) * round(size * PITCH) + round(size * 1.17) + (gap + pill_h if label else 0)
    top = max(SAFE_TOP, round(HEIGHT * CENTER_Y - block / 2))
    tops = [top + i * round(size * PITCH) for i in range(len(lines))]
    pill = None
    if label:
        w = round(label_ink * label_size / REF + label_size * 1.3)
        pill = {'x': WIDTH // 2 - w // 2, 'y': tops[-1] + round(size * 1.17) + gap, 'w': w, 'h': pill_h, 'size': label_size, 'text': label}
    return {'lines': lines, 'size': size, 'tops': tops, 'outline': max(3, round(size * BORDER)), 'pill': pill}


def pill_path(w, h):
    """Rounded pill as an ASS drawing (two half circles from cubic curves)."""
    r = h / 2; k = .5523 * r
    pts = [('m', r, 0), ('l', w - r, 0), ('b', w - r + k, 0, w, r - k, w, r), ('b', w, r + k, w - r + k, h, w - r, h),
           ('l', r, h), ('b', r - k, h, 0, r + k, 0, r), ('b', 0, r - k, r - k, 0, r, 0)]
    return ' '.join(p[0] + ' ' + ' '.join(str(round(v)) for v in p[1:]) for p in pts)


def title_events(plan):
    size, outline = plan['size'], plan['outline']
    shadow, blur = max(4, round(size * .06)), max(6, round(size * .1))
    events = []
    for line, top in zip(plan['lines'], plan['tops']):
        # Soft drop shadow on its own layer, then the crisp white letters with the dark outline.
        events.append((0, f'{{\\an8\\pos({WIDTH // 2},{top})\\fs{size}\\bord{outline}\\1a&HFF&\\3a&HFF&\\4c&H000000&\\4a&H48&\\shad{shadow}\\blur{blur}}}{ass_text(line)}'))
        events.append((1, f'{{\\an8\\pos({WIDTH // 2},{top})\\fs{size}\\bord{outline}\\shad0}}{ass_text(line)}'))
    pill = plan['pill']
    if pill:
        events.append((2, f'{{\\an7\\pos({pill["x"]},{pill["y"]})\\bord0\\shad0\\1c&H141414&\\1a&H28&\\p1}}{pill_path(pill["w"], pill["h"])}{{\\p0}}'))
        events.append((3, f'{{\\an5\\pos({WIDTH // 2},{pill["y"] + pill["h"] // 2})\\fs{pill["size"]}\\bord0\\shad0}}{ass_text(pill["text"])}'))
    return events


def letter(image, out, title, label=''):
    """Write the lettered title card (PNG, 1080x1920): the picture filled to 9:16, the title in the
    upper third, white with a thick dark outline and a soft shadow, for a series a "Teil N" pill."""
    out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
    font, family = find_font()
    with tempfile.TemporaryDirectory(dir=out.parent, prefix='.Titelbild_') as work:
        work = Path(work); (work / 'Schrift').mkdir()
        shutil.copy2(font, work / 'Schrift' / font.name)
        plan = layout(title, label, lambda texts: measure(texts, work, family))
        (work / 'Titel.ass').write_text(ass_document(WIDTH, HEIGHT, family, plan['size'], title_events(plan)), encoding='utf-8')
        temp = work / 'Titelbild.png'
        ff(['-i', Path(image).resolve(), '-vf', f'scale={WIDTH}:{HEIGHT}:flags=lanczos:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},'
            'setsar=1,format=rgb24,subtitles=Titel.ass:fontsdir=Schrift', '-frames:v', '1', '-update', '1', temp], work)
        info = png_info(temp)
        if (info['width'], info['height']) != (WIDTH, HEIGHT): raise RuntimeError('Titelbild hat nicht 1080 × 1920 Pixel.')
        os.replace(temp, out)
    return plan


# ---------- card clip and sound ----------

def card_clip(still, out, fps, folder):
    """One second (round(fps) frames) of the lettered card with a slow push-in, encoded exactly like
    the film's parts (libx264 medium, CRF 17, yuv420p, 1080x1920, same fps), so the concat stays a copy."""
    frames = round(fps)
    # Zoom on a twice as large picture: whole-pixel crop steps stay invisible.
    vf = (f'scale={2 * WIDTH}:{2 * HEIGHT}:flags=lanczos,'
          f'zoompan=z=1+{ZOOM}*on/{max(1, frames - 1)}:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2):d={frames}:s={WIDTH}x{HEIGHT}:fps={fps},setsar=1')
    temp = Path(out).with_name(Path(out).stem + '.' + uuid.uuid4().hex + '.partial.mp4')
    try:
        ff(['-i', Path(still).resolve(), '-an', '-vf', vf, '-frames:v', frames, '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-pix_fmt', 'yuv420p', temp], folder)
        stream = next(s for s in probe(temp)['streams'] if s['codec_type'] == 'video')
        if int(stream.get('nb_frames', 0)) != frames or (stream['width'], stream['height']) != (WIDTH, HEIGHT):
            raise RuntimeError('Die Titelkarte ist unvollständig. Animationen und Ton bleiben erhalten.')
        os.replace(temp, out)
    finally: temp.unlink(missing_ok=True)
    return frames


def impact(rate, seconds):
    """Sub-bass hit under the card: a short soft transient, then a sine falling from 90 to 42 Hz that
    fades within about a second. Gentle saturation adds overtones that phone speakers can play."""
    n = round(seconds * rate); out = array('f', bytes(4 * n)); rng = random.Random(18); phase = smooth = 0.
    for i in range(n):
        t = i / rate
        phase += math.tau * (42 + 48 * math.exp(-t / .12)) / rate
        body = math.sin(phase) * math.exp(-t / .32) * min(1., t / .004)
        smooth = .7 * smooth + .3 * rng.uniform(-1, 1)
        out[i] = (math.tanh(1.8 * body) / math.tanh(1.8) * .62 + .25 * smooth * math.exp(-t / .012)) * min(1., (seconds - t) / .06)
    return out


def fade(data, channels, rate, ending):
    """Fade SPLICE_FADE seconds at one edge of 16-bit PCM: no click where the card cuts in or out."""
    frame = 2 * channels; n = min(len(data) // frame, round(SPLICE_FADE * rate))
    if not n: return data
    start = len(data) - n * frame if ending else 0
    pcm = array('h'); pcm.frombytes(data[start:start + n * frame])
    if sys.byteorder != 'little': pcm.byteswap()
    for i in range(len(pcm)):
        k = i // channels; pcm[i] = round(pcm[i] * ((n - k) / (n + 1) if ending else (k + 1) / (n + 1)))
    if sys.byteorder != 'little': pcm.byteswap()
    return data[:start] + pcm.tobytes() + data[start + n * frame:]


def splice(mix, out, at_seconds, card_seconds):
    """Film sound before the card + impact + film sound after it, sample-exact in PCM (one AAC encode later)."""
    with wave.open(str(mix)) as stream:
        rate, channels, width = stream.getframerate(), stream.getnchannels(), stream.getsampwidth()
        if width != 2: raise RuntimeError('Titelkarte: unerwartetes Tonformat der freigegebenen Mischung.')
        data = stream.readframes(stream.getnframes())
    frame = 2 * channels; cut = min(len(data) // frame, round(at_seconds * rate)) * frame
    hit = array('h', (max(-32767, min(32767, round(v * 32767))) for v in impact(rate, card_seconds) for _ in range(channels)))
    if sys.byteorder != 'little': hit.byteswap()
    temp = Path(out).with_name(Path(out).name + '.' + uuid.uuid4().hex + '.partial')
    try:
        with wave.open(str(temp), 'wb') as stream:
            stream.setnchannels(channels); stream.setsampwidth(2); stream.setframerate(rate)
            stream.writeframes(fade(data[:cut], channels, rate, True) + hit.tobytes() + fade(data[cut:], channels, rate, False))
        os.replace(temp, out)
    finally: temp.unlink(missing_ok=True)
    return Path(out)


def insertion(scenes, fps, position):
    """Index in the part list and time (s) where the card goes: before the first part, or after all
    parts of the first shot. Always a part boundary, measured in whole frames like the parts."""
    if position == 'start': return 0, 0.
    clips = scenes[0]['clips']
    return len(clips), sum(round(c['seconds'] * fps) for c in clips) / fps


def build(folder, spec, scenes, fps):
    """Lettered still and card clip for finish(). Returns where it goes and how long it is."""
    if spec.get('position') not in POSITIONS: raise RuntimeError('Unbekannte Position des Titelbilds.')
    image = Path(spec['image'])
    if file_hash(image) != spec['sha256']: raise RuntimeError('Das gewählte Titelbild wurde verändert.')
    folder = Path(folder); still = folder / 'Titelbild.png'
    letter(image, still, spec['title'], spec.get('label', ''))
    frames = card_clip(still, folder / 'Titelkarte.mp4', fps, folder)
    index, at = insertion(scenes, fps, spec['position'])
    return {'part': 'Titelkarte.mp4', 'still': str(still), 'index': index, 'at': at, 'seconds': frames / fps,
            'frames': frames, 'position': spec['position']}


def shift_check(placed, approved, card, rate=RATE_CHECK):
    """Lines and approved speech as they must appear in the export: everything from the insertion
    point on moves by the card's length. The reference stays the approved mix itself, so a line
    lost while splicing is still found."""
    at, seconds = card['at'], card['seconds']
    lines = [(s + seconds, e + seconds, line) if s >= at - 1e-6 else (s, e, line) for s, e, line in placed]
    cut = min(len(approved), round(at * rate))
    return lines, approved[:cut] + array('h', bytes(2 * round(seconds * rate))) + approved[cut:]


def publish(card, out):
    """Cover_<film>.png next to the film, for TikTok's own cover choice. Copied and confirmed like the film."""
    target = Path(out).with_name('Cover_' + Path(out).stem + '.png'); source = Path(card['still'])
    transfer = target.with_name(target.name + '.' + uuid.uuid4().hex + '.partial')
    try:
        with source.open('rb') as reader, transfer.open('xb') as writer:
            shutil.copyfileobj(reader, writer, 4 * 1024 ** 2); writer.flush(); os.fsync(writer.fileno())
        if file_hash(transfer) != file_hash(source): raise RuntimeError('Titelbild-Kopie konnte nicht bestätigt werden.')
        os.replace(transfer, target)
    finally: transfer.unlink(missing_ok=True)
    return {'file': str(target), 'sha256': file_hash(target), 'position': card['position'], 'seconds': card['seconds']}


# ---------- factory ----------

class TitleCard:
    """Factory mixin: key art in pictures(), Cay's choice, new variants, lettered preview, download."""

    async def cover_pictures(self, d, refs, models):
        """Two key-art variants after the figure designs, before the scene images.
        False: stopped at a safe point (paused, or a kept library choice was applied)."""
        if not wanted(d): return True
        box = d.setdefault('cover', {'variants': [], 'selected': None, 'round': 0})
        names = main_cast(d)
        for variant in range(2):
            if self.paused(d['id']) or self.apply_pending(d): return False
            key = f'cover:0:{image_rounds(box)[variant]}:{variant}'
            if any(v.get('key') == key for v in box['variants']): continue
            d['phase'] = f'Titelbild {variant + 1}/2'; self.save(d)
            references = [self.stage(path) for path in cast_design.scene_references(refs, names)]
            graph = build_graph(prompt(d, names, variant, box.get('note', '')), references, int(cast_design.digest(d['id'] + key)[:12], 16), '', models)
            step = await self.render(d, key, graph)
            # The figures on it: a new design of one of them draws the key art again (cast_design.invalidate).
            box['variants'].append({'id': step['id'], 'key': key}); box['cast'] = names; self.save(d)
        return True

    def cover_spec(self, d, episode):
        """The export's 'cover' entry: the chosen key art, its title and the episode label."""
        box = d.get('cover') or {}
        found = self.rows("SELECT output,sha256 FROM factory_steps WHERE id=? AND run_id=? AND status='done'", (box.get('selected'), d['id']))
        if not found: raise RuntimeError('Das gewählte Titelbild fehlt. Fehlerbericht speichern und mitschicken.')
        if file_hash(self.path(found[0]['output'])) != found[0]['sha256']: raise RuntimeError('Das gewählte Titelbild wurde außerhalb des Studios verändert.')
        return {'position': d['idea']['cover'], 'image': found[0]['output'], 'sha256': found[0]['sha256'],
                'title': cover_title(d), 'label': part_label(d, episode)}

    def cover_routes(self, app):
        from factory_models import CoverChoice, CoverRevise

        @app.post('/api/factory/{rid}/cover/choose')
        async def choose_cover(rid: str, body: CoverChoice):
            d = self.get(rid)
            if d['state'] != 'image_review' or not wanted(d): raise HTTPException(409, 'Das Titelbild wird gerade nicht gewählt.')
            if body.step_id not in [v['id'] for v in active_variants(d.get('cover') or {})]:
                raise HTTPException(400, 'Bild gehört nicht zur aktuellen Titelbild-Auswahl.')
            d['cover']['selected'] = body.step_id; self.save(d); return self.get(rid)

        @app.post('/api/factory/{rid}/cover/revise')
        async def revise_cover(rid: str, body: CoverRevise):
            d = self.get(rid)
            if d['state'] != 'image_review' or not wanted(d): raise HTTPException(409, 'Neue Titelbilder nur während der Bildauswahl.')
            box = d.setdefault('cover', {'variants': [], 'selected': None, 'round': 0})
            if body.note: box['note'] = ((box.get('note') or '') + ' ' + body.note).strip()[-1200:]
            regenerate(box, [0, 1]); d['state'] = 'pictures'; d['phase'] = 'Zwei neue Titelbilder angefordert'
            self.save(d); return self.get(rid)

        @app.get('/api/factory/{rid}/cover/preview/{sid}')
        def cover_preview(rid: str, sid: str):
            """A key-art variant with the real lettering, as the film will show it."""
            d = self.get(rid)
            if not wanted(d) or sid not in [v['id'] for v in (d.get('cover') or {}).get('variants', [])]: raise HTTPException(404, 'Titelbild nicht gefunden.')
            found = self.rows("SELECT output,sha256 FROM factory_steps WHERE run_id=? AND id=? AND status='done'", (rid, sid))
            if not found: raise HTTPException(404, 'Titelbild noch nicht fertig.')
            source = self.path(found[0]['output']); title = cover_title(d); label = part_label(d, 0)
            cache = self.folder(d) / '02_Bilder' / f'Titelbild_{sid}_{cast_design.digest([found[0]["sha256"], title, label, LETTER_POLICY])[:12]}.png'
            if not cache.is_file():
                try: letter(source, cache, title, label)
                except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as error:
                    # The picture itself stays choosable; the export reports the same problem with its cause.
                    self.g['record']('cover_preview_error', str(error)[:800])
                    return FileResponse(source, media_type='image/png')
            return FileResponse(cache, media_type='image/png')

        @app.get('/api/factory/{rid}/cover/export/{index}')
        def cover_file(rid: str, index: int, download: bool = False):
            d = self.get(rid); exports = d.get('exports', [])
            if not 0 <= index < len(exports) or not exports[index].get('cover'): raise HTTPException(404, 'Zu diesem Film gibt es kein Titelbild.')
            path = self.path(exports[index]['cover']['file'])
            return FileResponse(path, media_type='image/png', filename=path.name if download else None)
