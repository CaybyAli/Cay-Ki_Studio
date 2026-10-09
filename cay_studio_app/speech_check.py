"""Per-line speech presence checks for preview mix and export (stdlib only).

A valid WAV, an audio stream or one loudness value for the whole track does not
prove that every planned line is audible. These checks look at each scheduled
line in the rendered dialogue track and against the background that plays at
the same time. Intentionally silent scenes have no lines and are not checked.
"""
from array import array
import json
import math
import subprocess
import sys
import wave

MARK = 'SPRACHPRÜFUNG'
POLICY = 1
HOP = .01
VOICED_FLOOR = 328        # about -40 dBFS on 16-bit PCM after dialogue loudnorm
MASKED_DB = 3.            # dialogue not clearly above music/ambience/effects
CROWDED_DB = 8.           # audible, but worth a warning
QUIET_DB = 15.            # much quieter than the other lines of the film


class SpeechCheckError(RuntimeError):
    def __init__(self, message, report):
        super().__init__(message)
        self.report = report


def read_wav(path):
    with wave.open(str(path)) as stream:
        if stream.getsampwidth() != 2 or stream.getnchannels() != 1:
            raise RuntimeError('Sprachprüfung erwartet Mono-PCM mit 16 Bit: ' + str(path))
        rate = stream.getframerate()
        samples = array('h', stream.readframes(stream.getnframes()))
    if sys.byteorder != 'little': samples.byteswap()
    return samples, rate


def decode(path, rate=24000):
    """Decode any audio/video file to mono 16-bit PCM with FFmpeg."""
    result = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-map', '0:a:0', '-ac', '1',
                             '-ar', str(rate), '-f', 's16le', '-'], capture_output=True, timeout=600)
    if result.returncode: raise RuntimeError('Tonspur nicht lesbar: ' + result.stderr.decode(errors='replace')[-600:])
    samples = array('h'); samples.frombytes(result.stdout[:len(result.stdout) // 2 * 2])
    if sys.byteorder != 'little': samples.byteswap()
    return samples


def frames(samples, rate, start, end, extra=()):
    """RMS per 10 ms frame between start and end seconds; extra tracks are summed."""
    hop = max(1, round(rate * HOP)); first = max(0, round(start * rate)); last = min(len(samples), round(end * rate))
    result = []
    for begin in range(first, last, hop):
        stop = min(last, begin + hop); total = 0.
        for i in range(begin, stop):
            value = samples[i]
            for track in extra: value += track[i] if i < len(track) else 0
            total += value * value
        result.append(math.sqrt(total / max(1, stop - begin)))
    return result


def db(ratio):
    return round(20 * math.log10(max(ratio, 1e-9)), 1)


def label(line):
    text = ' '.join(str(line.get('text_de') or line.get('text') or '').split())
    if len(text) > 48: text = text[:45].rstrip() + '…'
    return (f'Folge {int(line.get("episode", 0)) + 1}, Szene {int(line.get("scene", 0)) + 1}, '
            f'Figur {line.get("speaker") or "?"}: „{text}“')


def placed(scenes):
    """(start, end, line) for every scheduled line, using the same offsets as mix/export."""
    cursor = 0.; result = []
    for scene in scenes:
        for line in scene.get('lines') or ([scene['line']] if scene.get('line') else []):
            start = cursor + float(line.get('offset', .15))
            result.append((start, start + float(line['duration']), line))
        cursor += float(scene['seconds'])
    return result


def check_lines(dialogue, rate, lines, background=()):
    """Return one report entry per line. blocking=True means not audible."""
    entries = []
    for start, end, line in lines:
        voice = frames(dialogue, rate, start, end)
        voiced = [v for v in voice if v >= VOICED_FLOOR]
        duration = max(HOP, end - start)
        voiced_seconds = len(voiced) * HOP
        level = math.sqrt(sum(v * v for v in voiced) / len(voiced)) if voiced else 0.
        entry = {'key': line.get('key'), 'episode': line.get('episode'), 'scene': line.get('scene'),
                 'turn': line.get('turn'), 'speaker': line.get('speaker'), 'label': label(line),
                 'start': round(start, 3), 'seconds': round(duration, 3),
                 'voiced_seconds': round(voiced_seconds, 2), 'level_dbfs': db(level / 32768) if level else None,
                 'status': 'ok', 'blocking': False, 'note': ''}
        if voiced_seconds < max(.1, .2 * duration):
            entry.update(status='fehlt', blocking=True, note='keine hörbare Sprache an dieser Stelle')
        elif background:
            # Compare the voice with everything else in the final mix at the same frames.
            bed = frames(background[0], rate, start, end, background[1:])
            loud = [b for v, b in zip(voice, bed) if v >= VOICED_FLOOR]
            bed_level = math.sqrt(sum(b * b for b in loud) / len(loud)) if loud else 0.
            margin = db(level / bed_level) if bed_level > 1 else 60.
            entry['margin_db'] = margin
            if margin < MASKED_DB:
                entry.update(status='überdeckt', blocking=True, note=f'Musik/Geräusche übertönen die Stimme ({margin} dB Abstand)')
            elif margin < CROWDED_DB:
                entry.update(status='knapp', note=f'Stimme nur {margin} dB über Musik/Geräuschen')
        entries.append(entry)
    levels = sorted(e['level_dbfs'] for e in entries if e['level_dbfs'] is not None and not e['blocking'])
    if len(levels) >= 3:
        median = levels[len(levels) // 2]
        for e in entries:
            if e['status'] == 'ok' and e['level_dbfs'] is not None and e['level_dbfs'] < median - QUIET_DB:
                e.update(status='leise', note=f'{round(median - e["level_dbfs"], 1)} dB leiser als die übrigen Beiträge')
    return entries


def summary(entries, kind):
    blocking = [e for e in entries if e['blocking']]
    warnings = [e for e in entries if not e['blocking'] and e['status'] != 'ok']
    return {'policy': POLICY, 'kind': kind, 'lines': entries, 'checked': len(entries),
            'blocking': len(blocking), 'warnings': len(warnings),
            'speakers_missing': sorted({e['speaker'] for e in blocking} - {e['speaker'] for e in entries if not e['blocking']})}


def message(report, action):
    blocking = [e for e in report['lines'] if e['blocking']]
    shown = '; '.join(e['label'] + ' – ' + e['note'] for e in blocking[:6])
    more = f' und {len(blocking) - 6} weitere' if len(blocking) > 6 else ''
    who = (' Ohne hörbare Stimme: ' + ', '.join(report['speakers_missing']) + '.') if report['speakers_missing'] else ''
    return (f'{MARK}: {len(blocking)} von {report["checked"]} Dialogbeiträgen nicht hörbar.{who} {shown}{more}. '
            f'Nächster Schritt: {action}')


def write_report(path, report):
    temp = path.with_name(path.name + '.partial')
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    temp.replace(path)


def compare_export(export, approved, rate, lines):
    """The exported film must carry the same speech as the approved mix."""
    entries = []
    for start, end, line in lines:
        ref = frames(approved, rate, start, end); got = frames(export, rate, start, end)
        ref_level = math.sqrt(sum(v * v for v in ref) / max(1, len(ref)))
        got_level = math.sqrt(sum(v * v for v in got) / max(1, len(got)))
        delta = db(got_level / ref_level) if ref_level > 1 else 0.
        entry = {'key': line.get('key'), 'episode': line.get('episode'), 'scene': line.get('scene'),
                 'speaker': line.get('speaker'), 'label': label(line), 'start': round(start, 3),
                 'difference_db': delta, 'status': 'ok', 'blocking': False, 'note': ''}
        if delta < -6:
            entry.update(status='fehlt', blocking=True, note=f'im Video {abs(delta)} dB leiser als in der freigegebenen Tonvorschau')
        entries.append(entry)
    return entries
