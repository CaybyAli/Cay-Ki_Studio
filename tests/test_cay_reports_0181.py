"""Cay's report from 0.18.1 ('Gangster SpongeBob – Die Krone der Ananasstraße', 6 episodes):
"SPRACHPRÜFUNG: 1 von 21 Dialogbeiträgen nicht hörbar. Folge 1, Szene 29, Figur Patrick: „Sag ihm nicht, dass du Angst
hast, Sponge.“ – Musik/Geräusche übertönen die Stimme (2.1 dB Abstand)."
A retake speaks the same quiet line again and the effect stays as loud, so the project stopped again and again.
The mix now lowers music, ambience and effects under exactly that line. Real FFmpeg and the real mix code;
the voices are synthetic signals."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path[:0] = [str(APP), str(Path(__file__).parent)]

import audio_fixtures as fx  # noqa: E402
import speech_check  # noqa: E402
from factory_audio import mix  # noqa: E402


def quiet_line_under_an_effect(tmp_path, level=.03):
    loud = fx.line(tmp_path, 'E01_S28_T01', 0, 27, 0, 'SpongeBob', 'Ich habe keine Angst!', fx.speech(2., level=.6))
    quiet = fx.line(tmp_path, 'E01_S29_T01', 0, 28, 0, 'Patrick', 'Sag ihm nicht, dass du Angst hast, Sponge.', fx.speech(2.4, level=level))
    quiet['emotion'] = 'flüsternd'
    return [{'seconds': 3., 'lines': [loud], 'ambience': 'room', 'sound_cues': []},
            {'seconds': 3., 'lines': [quiet], 'ambience': 'wind', 'sound_cues': [{'kind': 'magic', 'position': .2}, {'kind': 'bell', 'position': .45}]}]


def test_a_quiet_line_under_an_effect_no_longer_stops_the_film(tmp_path):
    report = None
    mix(tmp_path / 'mix', quiet_line_under_an_effect(tmp_path), 'suspense')
    report = json.loads((tmp_path / 'mix/Sprachpruefung.json').read_text())
    patrick = next(e for e in report['lines'] if e['speaker'] == 'Patrick')
    assert report['blocking'] == 0 and patrick['margin_db'] >= speech_check.CROWDED_DB
    assert patrick['cleared_db'] > 0 and 'Hintergrund hier um' in patrick['note']
    assert next(e for e in report['lines'] if e['speaker'] == 'SpongeBob')['status'] == 'ok'
    assert (tmp_path / 'mix/Tonmischung.wav').is_file()


def test_the_bed_is_lowered_only_under_that_line(tmp_path):
    mix(tmp_path / 'mix', quiet_line_under_an_effect(tmp_path), 'suspense')
    patrick = next(e for e in json.loads((tmp_path / 'mix/Sprachpruefung.json').read_text())['lines'] if e['speaker'] == 'Patrick')
    music, rate = speech_check.read_wav(tmp_path / 'mix/Musik_Dialogabsenkung.wav')
    reference = tmp_path / 'ref'
    # Same mix without the quiet line's problem: the music before the line is untouched.
    scenes = quiet_line_under_an_effect(reference, level=.6)
    mix(reference / 'mix', scenes, 'suspense')
    plain, _ = speech_check.read_wav(reference / 'mix/Musik_Dialogabsenkung.wav')
    before = round((patrick['start'] - .1) * rate)
    assert music[:before] == plain[:before]


def test_a_mix_without_masking_stays_byte_identical(tmp_path):
    scenes = quiet_line_under_an_effect(tmp_path, level=.6)
    first = Path(mix(tmp_path / 'a', scenes, 'suspense')).read_bytes()
    report = json.loads((tmp_path / 'a/Sprachpruefung.json').read_text())
    assert all('cleared_db' not in e for e in report['lines'])
    assert hashlib.sha256(Path(mix(tmp_path / 'b', scenes, 'suspense')).read_bytes()).digest() == hashlib.sha256(first).digest()


def test_a_line_that_is_really_missing_still_stops(tmp_path):
    scenes = quiet_line_under_an_effect(tmp_path)
    missing = fx.line(tmp_path, 'E01_S29_T01b', 0, 28, 0, 'Patrick', 'Sag ihm nicht, dass du Angst hast, Sponge.', fx.near_silence(2.4))
    scenes[1]['lines'] = [missing]
    with pytest.raises(speech_check.SpeechCheckError, match='Figur Patrick'):
        mix(tmp_path / 'mix', scenes, 'suspense')
