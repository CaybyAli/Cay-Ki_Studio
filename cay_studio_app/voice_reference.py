"""0.19 voice references (diagnosis r019, area 'voices', B5c/B5b): a recording is cleaned once before it is cloned.

Qwen's clone with a transcript (ICL) continues its reference acoustically: the level, the room, the music and the hiss
of Cay's YouTube samples went into every line, and a sample at -38 LUFS gave lines that were 20 dB too quiet. Up to
0.18 the upload was only converted (mono, 24 kHz). For projects with voice_policy 19 (pinned from sound_policy 19)
factory_quality hands Qwen and Chatterbox a cleaned copy of every own or library recording without a design recipe
(a designed voice is already clean studio speech):

1. vocals separated with Demucs, only when the sample has background (estimated SNR under BACKGROUND_DB), Demucs is
   importable in the voice environment and its htdemucs weights are already on disk. Never installed or downloaded
   here; without it the step is skipped;
2. high-pass at 70 Hz (rumble, handling noise);
3. gentle FFT denoise (FFmpeg afftdn, the mix's own factory_audio.denoise) with the hiss learnt from the quietest pause,
   only when the sample has a noise floor; kept only if the speech level stays within 1 dB. arnndn (RNNoise) is not used:
   no model file with a clear free licence ships with the studio;
4. silence at both ends trimmed and pauses over PAUSE_LONG shortened; a word is never cut, so a transcript stays exact;
5. levelled to TARGET_LUFS by one measured gain (at most +MAX_BOOST dB), peaks limited to PEAK_DBFS.

The copy sits next to the original as '<name>.ref19.wav' with its own sha256 and a recipe '<name>.ref19.json'
(steps, gain, loudness and SNR before and after); it is made again only when the original or the recipe changes.
The original is never touched. FFmpeg and numpy only; runs in the studio server process."""
import hashlib
import json
import os
import subprocess
import wave
from array import array
from pathlib import Path

import numpy as np

import factory_audio as fa

POLICY = 19
RECIPE = 'ref19-v1'          # part of the cache check: a new recipe cleans every sample again
RATE = fa.RATE
TARGET_LUFS = -20.           # the level every take is mixed at (factory_audio.SPEECH_LUFS)
PEAK_DBFS = -2.
MAX_BOOST, MAX_CUT = 30., 12.
HIGHPASS = 70
BACKGROUND_DB = 30.          # estimated SNR under this: music or noise under the voice (try Demucs)
NOISY_DB = 25.               # still under this after cleaning: warn, the clone may carry the rest
SHORT_SECONDS = 5.           # less speech than this: warn, the clone gets less like the voice
PAUSE_LONG, PAUSE_KEEP = .8, .4
LEAD, TAIL = .12, .25
DEMUCS = r'''import pathlib,sys
try:
    import torch,demucs.separate
except Exception:sys.exit(3)
if not any(pathlib.Path(torch.hub.get_dir(),'checkpoints').glob('955717e8-*.th')):sys.exit(4)   # htdemucs weights: never downloaded here
demucs.separate.main(['-n','htdemucs','--two-stems','vocals','-d','cuda' if torch.cuda.is_available() else 'cpu','-o',sys.argv[2],sys.argv[1]])'''


def frames_db(x, hop_seconds=.01):
    """RMS level (dBFS) per frame; numpy, so a 90 s sample takes milliseconds."""
    x = np.asarray(x, dtype=np.float64); hop = max(1, int(RATE * hop_seconds)); n = len(x) // hop
    if not n: return np.zeros(0)
    return 20 * np.log10(np.sqrt((x[:n * hop].reshape(n, hop) ** 2).mean(1)) + 1e-9)


def measure(x):
    """Loudness (LUFS), speech and floor level (90th/10th percentile of 20 ms frames), their distance as estimated SNR,
    and the seconds of speech (frames within 20 dB of the speech level). Model-free (r019 snr_est.py)."""
    r = frames_db(x, .02)
    if len(r) < 5: return {'seconds': round(len(x) / RATE, 2), 'lufs': -70., 'speech_dbfs': -120., 'floor_dbfs': -120., 'snr_db': 0., 'speech_seconds': 0.}
    speech, floor = float(np.percentile(r, 90)), float(np.percentile(r, 10))
    lufs = fa.r128(fa.PIPE, '', array('f', np.asarray(x, dtype=np.float32).tobytes()))[0]
    return {'seconds': round(len(x) / RATE, 2), 'lufs': round(lufs, 1), 'speech_dbfs': round(speech, 1), 'floor_dbfs': round(max(-120., floor), 1),
            'snr_db': round(min(90., speech - floor), 1), 'speech_seconds': round(float(np.sum(r >= speech - 20)) * .02, 1)}


def trim(x):
    """Silence off both ends, pauses over PAUSE_LONG down to PAUSE_KEEP. Only frames under the threshold (40 dB under
    the loud end, at least 6 dB over the floor) are removed: every word stays, in order."""
    r = frames_db(x); hop = int(RATE * .01)
    if len(r) < 20: return x
    loud = float(np.percentile(r, 98)); floor = float(np.percentile(r, 10))
    sound = np.flatnonzero(r > max(loud - 40, floor + 6))
    if not len(sound): return x
    keep = np.zeros(len(r), bool); keep[max(0, sound[0] - int(LEAD / .01)):min(len(r), sound[-1] + 1 + int(TAIL / .01))] = True
    for a, b in zip(sound[:-1], sound[1:]):
        if (b - a) * .01 > PAUSE_LONG:
            half = int(PAUSE_KEEP / .02); keep[a + 1 + half:b - half] = False
    out = np.asarray(x)[:len(r) * hop].reshape(len(r), hop)[keep].reshape(-1)
    return out if len(out) >= RATE else x


def separate(src, python, work):
    """Vocals of src by Demucs in the voice environment; None when it is not there (the normal case) or fails."""
    if not python or not Path(python).is_file(): return None
    try: r = subprocess.run([str(python), '-c', DEMUCS, str(src), str(work)], capture_output=True, timeout=900)
    except (OSError, subprocess.SubprocessError): return None
    vocals = Path(work) / 'htdemucs' / Path(src).stem / 'vocals.wav'
    if r.returncode or not vocals.is_file(): return None
    try: return np.asarray(fa.read_f32(vocals), dtype=np.float32)
    except RuntimeError: return None


def denoise(x):
    """afftdn with the hiss of the quietest pause (factory_audio.denoise); None for a clean sample, no pause, a noise
    floor too close to the voice (music: afftdn does not help) or when the speech level moved more than 1 dB."""
    data = array('f', np.asarray(x, dtype=np.float32).tobytes())
    fr = list(10 ** (frames_db(x) / 20)); active = fa.active_level(fr); window = fa.noise_window(fr, active)
    if not window: return None
    out = fa.denoise(data, window[0], window[1])
    if out is None: return None
    after = fa.active_level(list(10 ** (frames_db(out) / 20)))
    return np.asarray(out, dtype=np.float32) if after is not None and abs(after - active) <= 1 else None


def write_wav(path, x):
    pcm = np.clip(np.round(np.asarray(x, dtype=np.float64) * 32767), -32767, 32767).astype('<i2')
    temp = Path(path).with_suffix('.partial.wav')
    with wave.open(str(temp), 'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm.tobytes())
    os.replace(temp, path)


def paths(src):
    src = Path(src); return src.with_name(src.stem + '.ref19.wav'), src.with_name(src.stem + '.ref19.json')


def clean(src, python=None):
    """Cleaned copy of the recording src (see the module text). Returns its recipe: file, sha256, source_sha256, steps,
    gain_db, before/after measurements and warning codes ('short', 'noisy'). Raises RuntimeError when FFmpeg fails;
    the caller then clones the original."""
    src = Path(src); source = hashlib.sha256(src.read_bytes()).hexdigest(); dest, meta = paths(src)
    try:
        info = json.loads(meta.read_text())
        if info['source_sha256'] == source and info['recipe'] == RECIPE and hashlib.sha256(dest.read_bytes()).hexdigest() == info['sha256']: return info
    except (OSError, ValueError, KeyError, TypeError): pass
    x = np.asarray(fa.read_f32(src), dtype=np.float32); before = measure(x); steps = []
    if before['snr_db'] < BACKGROUND_DB:
        work = dest.with_name(dest.stem + '.demucs'); vocals = separate(src, python, work)
        if vocals is not None and len(vocals): x = vocals; steps.append('demucs')
    high = fa.run_f32(f'highpass=f={HIGHPASS}:poles=2', array('f', x.tobytes()))
    if high is not None and len(high) == len(x): x = np.asarray(high, dtype=np.float32); steps.append('highpass')
    quiet = denoise(x)
    if quiet is not None: x = quiet; steps.append('afftdn')
    cut = trim(x)
    if len(cut) < len(x): steps.append('trim')
    x = cut; loud = fa.r128(fa.PIPE, '', array('f', x.tobytes()))[0]; gain = 0.
    if loud > -70:
        gain = max(-MAX_CUT, min(MAX_BOOST, TARGET_LUFS - loud))
        chain = (f'apad=pad_dur=0.1,volume={gain:+.2f}dB,alimiter=limit={10 ** (PEAK_DBFS / 20):.5f}:release=80:level=0:latency=1,'
                 f'asetpts=N/SR/TB,atrim=end_sample={len(x)},')
        _, _, out = fa.r128(fa.PIPE, chain, array('f', x.tobytes()))
        if len(out) != len(x): raise RuntimeError('Stimmprobe: Pegelung unvollständig.')
        x = np.asarray(out, dtype=np.float32); steps.append('level')
    after = measure(x); write_wav(dest, x)
    warnings = [w for w, bad in (('short', after['speech_seconds'] < SHORT_SECONDS), ('noisy', after['snr_db'] < NOISY_DB)) if bad]
    info = {'file': str(dest), 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(), 'source': str(src), 'source_sha256': source,
            'recipe': RECIPE, 'steps': steps, 'gain_db': round(gain, 1), 'before': before, 'after': after, 'warnings': warnings,
            'arnndn': 'nicht verwendet: kein Modell mit klarer freier Lizenz im Studio'}
    temp = meta.with_suffix('.partial.json'); temp.write_text(json.dumps(info, ensure_ascii=False)); os.replace(temp, meta)
    return info


def notes(name, info):
    """Short German notes for the figure card and the diagnosis."""
    if not info: return [f'Stimmprobe von {name} ließ sich nicht reinigen. Das Studio klont das Original.']
    out = []
    if 'demucs' in info['steps']: out.append('Musik und Geräusche abgetrennt')
    if 'afftdn' in info['steps']: out.append('Rauschen gemindert')
    if abs(info['gain_db']) >= 3: out.append(f'{"+" if info["gain_db"] > 0 else "−"}{abs(round(info["gain_db"]))} dB angeglichen')
    text = [f'Stimmprobe gereinigt: {", ".join(out)}.' if out else 'Stimmprobe geprüft: sauber.']
    if 'noisy' in info['warnings']:
        text.append(f'Stimmprobe von {name}: viel Hintergrund (Musik oder Rauschen). Der Klon kann ihn übernehmen. Besser eine Aufnahme ohne Musik.')
    if 'short' in info['warnings']:
        text.append(f'Stimmprobe von {name}: nur {str(info["after"]["speech_seconds"]).replace(".", ",")} s Sprache. Mit 10 bis 20 s klingt der Klon ähnlicher.')
    return text


def summary(name, info, transcript):
    """What the project keeps per figure (voice_profiles[name]['reference']): shown in the app and the diagnosis."""
    base = {'mode': 'icl' if transcript else 'x-vector', 'notes': notes(name, info)}
    if not info: return {**base, 'cleaned': False}
    return {**base, 'cleaned': True, 'steps': info['steps'], 'gain_db': info['gain_db'], 'original_sha256': info['source_sha256'],
            'lufs_before': info['before']['lufs'], 'lufs_after': info['after']['lufs'], 'snr_before': info['before']['snr_db'],
            'snr_after': info['after']['snr_db'], 'seconds': info['after']['seconds'], 'warnings': info['warnings']}
