"""Synthetic speech-like WAVs for mix/export checks. No AI models involved."""
from array import array
from pathlib import Path
import hashlib
import math
import wave

RATE = 24000


def write(path, samples, rate=RATE):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    pcm = array('h', (max(-32767, min(32767, round(x * 32767))) for x in samples))
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())
    return path


def speech(seconds, level=.5, pitch=140., rate=RATE):
    """Voiced harmonics with ~4 syllables per second and short gaps."""
    out = []
    for i in range(round(seconds * rate)):
        t = i / rate
        syllable = max(0., math.sin(math.pi * 4 * t)) ** .6
        tone = sum(math.sin(math.tau * pitch * k * t) / k for k in range(1, 6))
        out.append(level * .45 * syllable * tone)
    return out


def near_silence(seconds, rate=RATE):
    """What a failed TTS take can look like: a click, then almost nothing."""
    out = [0.] * round(seconds * rate)
    for i in range(40): out[1000 + i] = .02 * (1 if i % 2 else -1)
    return out


def line(folder, key, episode, scene, turn, speaker, text, samples, offset=.12):
    path = write(Path(folder) / (key + '.wav'), samples)
    return {'key': key, 'episode': episode, 'scene': scene, 'turn': turn, 'speaker': speaker,
            'text': text, 'text_de': text, 'emotion': 'Natürlich', 'pause_after': .18,
            'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'duration': len(samples) / RATE, 'offset': offset}
