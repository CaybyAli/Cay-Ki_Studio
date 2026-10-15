"""0.17 voices: every common German delivery word reaches an acted reference,
livelier takes win, shouts and whispers keep their level in the mix.
Real Qwen/Chatterbox output cannot be judged here; these tests pin the logic."""
import sys
import wave
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path.insert(0, str(APP)); sys.path.insert(0, str(Path(__file__).parent))

from speech_quality import performance_key, prosody_score, sampling, level_db  # noqa: E402
import screenplay  # noqa: E402

WORDS = ['panisch', 'schreiend', 'brüllend', 'empört', 'überrascht', 'entsetzt', 'triumphierend', 'höhnisch', 'flehend',
         'gierig', 'gereizt', 'befehlend', 'fröhlich', 'aufgeregt', 'ängstlich', 'flüsternd', 'drohend', 'spöttisch',
         'verwirrt', 'genervt', 'traurig', 'wütend', 'begeistert']


def test_delivery_words_reach_an_acted_reference():
    """0.16: 29 of 40 common words fell back to the calm narrator reference."""
    assert all(performance_key(w) != 'natural' for w in WORDS)
    assert performance_key('Natürlich') == performance_key('ruhig') == 'natural'
    assert all(performance_key(e) != 'natural' for e in screenplay.EMOTIONS if e != 'ruhig')


def test_every_delivery_has_a_matching_reference_text():
    import factory_voice
    keys = {performance_key(e) for e in screenplay.EMOTIONS} - {'natural'}
    assert keys <= set(factory_voice.EMOTION_TEXTS)
    assert factory_voice.EMOTION_TEXTS['angry'][1] != factory_voice.EMOTION_TEXTS['whisper'][1]
    assert 'Heute beginnt unsere Geschichte' not in factory_voice.REFERENCE_TEXT


def test_cartoon_looks_get_cartoon_delivery():
    import factory_voice
    sponge = {'name': 'SpongeBob', 'voice_preset': 'young_man', 'original': 'SpongeBob SquarePants', 'personality': 'fröhlich'}
    lena = {'name': 'Lena', 'voice_preset': 'woman', 'personality': 'klug'}
    assert 'cartoon dubbing' in factory_voice.description(sponge, 0, 'film')
    assert 'cartoon dubbing' in factory_voice.description(lena, 0, 'clay')
    assert 'cartoon dubbing' not in factory_voice.description(lena, 0, 'film')
    assert 'never' not in factory_voice.CARTOON


def test_chatterbox_strong_emotions_use_the_dramatic_recipe():
    assert sampling('schreiend')['exaggeration'] >= .85 and sampling('schreiend')['cfg_weight'] <= .3
    assert sampling('ruhig')['exaggeration'] == .5
    assert sampling('flüsternd')['exaggeration'] < .5


def test_prosody_score_prefers_melody_over_monotone():
    sr = 24000; t = np.arange(sr * 2) / sr
    mono = .3 * np.sin(2 * np.pi * 150 * t) * ((.6 + .4 * np.sin(2 * np.pi * 4 * t)) > .3)
    f = 150 * 2 ** (3 * np.sin(2 * np.pi * .7 * t) / 12)
    lively = .3 * np.sin(2 * np.pi * np.cumsum(f) / sr) * (.4 + .6 * np.abs(np.sin(2 * np.pi * 3 * t)))
    assert prosody_score(lively, sr) > prosody_score(mono, sr) + .5
    assert prosody_score(np.zeros(100), sr) == 0.


def test_shout_and_whisper_keep_their_level_in_the_mix(tmp_path):
    from audio_fixtures import line, speech
    from factory_audio import mix
    scenes = []
    for si, emotion in enumerate(['schreiend', 'flüsternd', 'ruhig']):
        voice = line(tmp_path / 'v', f'l{si}', 0, si, 0, 'Lena', 'Hallo du da', speech(1.6))
        voice.update(duration=1.6, offset=.08, emotion=emotion)
        scenes.append({'seconds': 2.4, 'lines': [voice], 'ambience': 'none', 'sound_cues': []})
    out = mix(tmp_path / 'mix', scenes, 'playful', None, {'music_mode': 'off'})
    with wave.open(str(tmp_path / 'mix' / 'Dialogschnitt.wav')) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float); sr = w.getframerate()
    rms = [np.sqrt(np.mean(x[int((i * 2.4 + .1) * sr):int((i * 2.4 + 1.6) * sr)] ** 2)) for i in range(3)]
    db = [20 * np.log10(r) for r in rms]
    # Shout louder, whisper quieter than neutral (whisper only -2 dB: the music ducking ignores the gain).
    assert db[0] > db[2] + 1 and db[1] < db[2] - .8
    assert level_db('schreiend') > 0 > level_db('flüsternd') and Path(out).is_file()
