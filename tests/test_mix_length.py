"""0.16.0 stopped Cay's film at "Tonmischung unvollständig; keine Freigabe".

FFmpeg's loudnorm drops the last partial 100 ms block. Since 0.16 a film is a
whole number of video frames (60.12 s), no longer a whole number of tenths
(60.0 s), so the mix came out up to 0.1 s short and was rejected. Real FFmpeg.
"""
import sys
import wave
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path.insert(0, str(APP)); sys.path.insert(0, str(Path(__file__).parent))

from audio_fixtures import line, speech  # noqa: E402
from factory_audio import mix  # noqa: E402


@pytest.mark.parametrize('seconds', [(3.36, 3.4, 3.28), (4.04, 2.0, 4.08), (3.0, 3.0, 4.0)])
def test_mix_keeps_exact_frame_length(tmp_path, seconds):
    total = round(sum(seconds), 4)
    scenes = []
    for si, s in enumerate(seconds):
        voice = line(tmp_path / 'v', f'l{si}', 0, si, 0, 'SpongeBob', 'Hallo', speech(min(2.0, s - .4)))
        voice.update(duration=min(2.0, s - .4), offset=.08)
        scenes.append({'seconds': s, 'lines': [voice], 'ambience': 'room', 'sound_cues': []})
    out = mix(tmp_path / 'mix', scenes, 'playful', None, {'music_mode': 'auto'})
    with wave.open(out) as w:
        assert abs(w.getnframes() / w.getframerate() - total) <= .005
    with wave.open(str(tmp_path / 'mix' / 'Dialogschnitt.wav')) as w:
        assert abs(w.getnframes() / w.getframerate() - total) <= .005
