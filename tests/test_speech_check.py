"""Speech must be audible per line in preview mix and export.

Uses real FFmpeg and the real mix/export code. Voices are synthetic signals,
not AI speech: this proves the checks and the mapping, not voice quality.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path[:0] = [str(APP), str(Path(__file__).parent)]

import audio_fixtures as fx  # noqa: E402
import speech_check  # noqa: E402
from factory_audio import mix  # noqa: E402


def scenes_for(*lines, seconds=4.):
    return [{'seconds': seconds, 'lines': [line], 'ambience': 'room', 'sound_cues': []} for line in lines]


def test_complete_dialogue_passes_and_is_reported(tmp_path):
    a = fx.line(tmp_path, 'E01_S01_T01', 0, 0, 0, 'Max', 'Wo warst du die ganze Nacht?', fx.speech(2.))
    b = fx.line(tmp_path, 'E01_S02_T01', 0, 1, 0, 'Lina', 'Das geht dich nichts an!', fx.speech(1.6, pitch=220))
    mix(tmp_path / 'mix', scenes_for(a, b), 'suspense')
    report = json.loads((tmp_path / 'mix/Sprachpruefung.json').read_text())
    assert report['checked'] == 2 and report['blocking'] == 0
    assert all(e['status'] == 'ok' for e in report['lines'])
    assert json.loads((tmp_path / 'mix/Tonbericht.json').read_text())['speech_check']['blocking'] == 0


def test_one_silent_line_blocks_with_episode_scene_and_speaker(tmp_path):
    # 0.13.0 accepted exactly this mix because only the whole track was measured.
    a = fx.line(tmp_path, 'E01_S01_T01', 0, 0, 0, 'Max', 'Wo warst du die ganze Nacht?', fx.speech(2.))
    b = fx.line(tmp_path, 'E01_S02_T01', 0, 1, 0, 'Lina', 'Lass mich los!', fx.near_silence(1.6))
    with pytest.raises(speech_check.SpeechCheckError) as caught:
        mix(tmp_path / 'mix', scenes_for(a, b), 'suspense')
    text = str(caught.value)
    assert speech_check.MARK in text and 'Folge 1, Szene 2, Figur Lina' in text and 'Max' not in text.split('Ohne')[0]
    report = json.loads((tmp_path / 'mix/Sprachpruefung.json').read_text())
    assert [e['key'] for e in report['lines'] if e['blocking']] == ['E01_S02_T01']
    assert report['speakers_missing'] == ['Lina']
    assert not (tmp_path / 'mix/Tonmischung.wav').exists()


def test_intentionally_silent_scene_is_allowed(tmp_path):
    a = fx.line(tmp_path, 'E01_S01_T01', 0, 0, 0, 'Max', 'Wo warst du die ganze Nacht?', fx.speech(2.))
    scenes = scenes_for(a) + [{'seconds': 4., 'lines': [], 'ambience': 'wind', 'sound_cues': []}]
    mix(tmp_path / 'mix', scenes, 'gentle')
    assert json.loads((tmp_path / 'mix/Sprachpruefung.json').read_text())['blocking'] == 0


def test_loud_music_is_reported_and_masking_blocks(tmp_path):
    # Real mix: ducking keeps even maximum music below the voice, but it is reported.
    a = fx.line(tmp_path, 'E01_S01_T01', 0, 0, 0, 'Max', 'Wo warst du die ganze Nacht?', fx.speech(2.))
    music = fx.write(tmp_path / 'laut.wav', fx.speech(8., level=.9, pitch=180))
    asset = {'file': str(music), 'sha256': hashlib.sha256(music.read_bytes()).hexdigest()}
    mix(tmp_path / 'mix', scenes_for(a), 'suspense', asset, {'music_mode': 'uploaded', 'music_level': 12.})
    entry = json.loads((tmp_path / 'mix/Sprachpruefung.json').read_text())['lines'][0]
    assert entry['status'] == 'knapp' and not entry['blocking']
    assert 'Stimme nur' in json.loads((tmp_path / 'mix/Tonbericht.json').read_text())['speech_warnings'][0]
    # Direct check: a bed louder than the voice blocks.
    from array import array
    voice = array('h', (round(x * 8000) for x in fx.speech(2.)))
    bed = array('h', (round(x * 16000) for x in fx.speech(2., pitch=300)))
    entry = speech_check.check_lines(voice, 24000, [(0., 2., {'speaker': 'Max', 'text': 'Hallo'})], (bed,))[0]
    assert entry['status'] == 'überdeckt' and entry['blocking']


def test_finish_voice_rejects_click_but_keeps_real_short_line():
    np = pytest.importorskip('numpy')
    from speech_quality import finish_voice
    for text in ('Nein!', 'Lass mich los!'):
        with pytest.raises(RuntimeError, match='Kaum hörbare Sprache'):
            finish_voice(np.array(fx.near_silence(1.6)), 24000, text)
    data, quality = finish_voice(np.array(fx.speech(.7)), 24000, 'Nein!')
    assert quality['voiced_seconds'] >= .19 and len(data) > 0
    data, quality = finish_voice(np.array(fx.speech(3.)), 24000, 'Wir müssen sofort hier raus, bevor sie zurückkommen.')
    assert quality['voiced_seconds'] > .8


def make_clip(path, seconds):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc2=size=480x832:rate=16:duration={seconds}',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(path)], check=True)
    return {'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'seconds': seconds}


def test_export_carries_every_approved_line(tmp_path):
    from factory_video import finish, file_hash
    a = fx.line(tmp_path, 'E01_S01_T01', 0, 0, 0, 'Max', 'Wo warst du?', fx.speech(1.5))
    b = fx.line(tmp_path, 'E01_S02_T01', 0, 1, 0, 'Lina', 'Weg von hier!', fx.speech(1.2, pitch=220))
    scenes = scenes_for(a, b, seconds=2.)
    approved = Path(mix(tmp_path / 'mix', scenes, 'playful'))
    for i, scene in enumerate(scenes): scene['clips'] = [make_clip(tmp_path / f'clip{i}.mp4', 2.)]
    out = tmp_path / 'Folge_01.mp4'
    result = finish({'folder': str(tmp_path / 'work'), 'fps': 25, 'smooth': False, 'scenes': scenes, 'title': 'Test',
                     'output': str(out), 'minimum_seconds': 4, 'mood': 'playful', 'mix': None, 'music': None,
                     'audio_mix': {'file': str(approved), 'sha256': file_hash(approved)}})
    report = json.loads((tmp_path / 'work/Exportpruefung.json').read_text())
    assert result['file'] == str(out) and report['checked'] == 2 and report['blocking'] == 0


def test_export_comparison_detects_lost_line(tmp_path):
    a = fx.line(tmp_path, 'E01_S01_T01', 0, 0, 0, 'Max', 'Wo warst du?', fx.speech(1.5))
    b = fx.line(tmp_path, 'E01_S02_T01', 0, 1, 0, 'Lina', 'Weg von hier!', fx.speech(1.2, pitch=220))
    scenes = scenes_for(a, b, seconds=2.)
    approved = speech_check.decode(mix(tmp_path / 'mix', scenes, 'playful'))
    broken = approved[:]
    for i in range(round(2.0 * 24000), len(broken)): broken[i] = 0   # scene 2 lost in the film
    report = speech_check.summary(speech_check.compare_export(broken, approved, 24000, speech_check.placed(scenes)), 'export')
    assert [e['speaker'] for e in report['lines'] if e['blocking']] == ['Lina']


class FakeFactory:
    """Only what speech_retake needs: failed mix rows and the allowed-path check."""
    def __init__(self, rows): self.rows_ = rows
    def post_rows(self, d, kind): return self.rows_
    def path(self, p): return Path(p)


def test_resume_after_failed_check_retakes_only_failed_lines(tmp_path):
    from factory_quality import Quality
    a = fx.line(tmp_path, 'E01_S01_T01_aaaa', 0, 0, 0, 'Max', 'Wo warst du die ganze Nacht?', fx.speech(2.))
    b = fx.line(tmp_path, 'E01_S02_T01_bbbb', 0, 1, 0, 'Lina', 'Lass mich los!', fx.near_silence(1.6))
    folder = tmp_path / 'mix'
    with pytest.raises(speech_check.SpeechCheckError) as caught:
        mix(folder, scenes_for(a, b), 'suspense')
    rows = [{'status': 'failed', 'error': 'Nachbearbeitung: ' + str(caught.value), 'spec': json.dumps({'folder': str(folder)})}]
    d = {'state': 'blocked', 'resume_state': 'audio_mixing', 'error': str(caught.value), 'previews': []}
    assert Quality.speech_retake(FakeFactory(rows), d) is True
    assert d['state'] == 'voicing' and d['speech_takes'] == {'E01_S02_T01_bbbb': 1} and 'resume_state' not in d
    assert Quality.speech_retake(FakeFactory(rows), {'state': 'blocked', 'resume_state': 'rendering'}) is False
    other = [{'status': 'failed', 'error': 'Tonmischung: ffmpeg kaputt', 'spec': json.dumps({'folder': str(folder)})}]
    assert Quality.speech_retake(FakeFactory(other), {'state': 'blocked', 'resume_state': 'audio_mixing'}) is False


def test_resume_after_failed_generation_retakes_that_line(tmp_path):
    from factory_quality import Quality
    fake = FakeFactory([]); fake.folder = lambda d: tmp_path
    marker = tmp_path / '03_Stimmen/Dialoge/Fehlgeschlagen.json'; marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({'key': 'E01_S03_T02_cccc'}))
    d = {'state': 'blocked', 'resume_state': 'voicing', 'speech_takes': {'E01_S03_T02_cccc': 1}}
    assert Quality.speech_retake(fake, d) is True
    assert d['speech_takes'] == {'E01_S03_T02_cccc': 2} and d['state'] == 'voicing' and not marker.exists()
    # Other generation failures (e.g. model missing) keep the normal resume path.
    assert Quality.speech_retake(fake, {'state': 'blocked', 'resume_state': 'voicing'}) is False
