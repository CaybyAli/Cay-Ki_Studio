"""0.19 voices (diagnosis r019, area 'voices': B5c recordings cleaned, B5e emotion and monotony, NFD delivery words).
Projects created with sound_policy 19 voice with voice_policy 19; every older project keeps voice policy 16/17/18,
its references, takes and cache signatures. Real FFmpeg for the cleaning; the voices are synthetic signals and the
models are fakes (tests/voice_fakes.py): this proves levels, noise floor, takes and the job, not how a real clone sounds."""
import asyncio
import contextlib
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'cay_studio_app'
sys.path[:0] = [str(APP), str(ROOT / 'tests')]

import voice_fakes as vf  # noqa: E402
from speech_quality import performance_key, sampling  # noqa: E402

RATE = 24000
NFD = {'wütend': 'angry', 'ängstlich': 'afraid', 'flüsternd': 'whisper', 'spöttisch': 'mocking', 'überrascht': 'surprised', 'fröhlich': 'joy'}


def nfd(text): return unicodedata.normalize('NFD', text)


# --- (3) delivery words in decomposed Unicode ---------------------------------------------------------------------
def test_nfd_delivery_words_keep_their_category_only_with_voice_policy_19():
    for word, key in NFD.items():
        assert nfd(word) != word and performance_key(word) == key
        assert performance_key(nfd(word), 19) == key                       # 0.19: macOS spelling reaches its reference
        assert performance_key(nfd(word)) == performance_key(nfd(word), 18) == 'natural'    # older projects: as before
    assert sampling(nfd('wütend'), 19) == sampling('wütend', 19) != sampling(nfd('wütend'), 18)
    assert sampling(nfd('wütend'), 18) == sampling('ruhig', 18)


class Speaking:
    """Quality.quality_voices() with a fake speech run: records the voice jobs (design and speech)."""
    def __init__(self, folder, voices=None):
        self.posts = []; self.jobs = []; self.base = folder / 'base'; self.g = {}; self.folder_path = folder; self.voices = voices or {}
        (self.base / 'envs/chatterbox/bin').mkdir(parents=True); (self.base / 'envs/chatterbox/bin/python').write_text('')
    def apply_pending(self, d): return False
    def paused(self, rid): return False
    def save(self, d): pass
    def folder(self, d): return self.folder_path
    def asset(self, aid, kind=None):
        path = self.voices.get(aid, self.folder_path.parent / 'voice.wav')
        return {'path': str(path), 'sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else 'x' * 64}
    def queue_post(self, d, kind, ei, spec): self.posts.append(spec)
    def atomic(self, path, data): Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_bytes(data)
    async def idle(self, client, wait): pass
    def measured(self, d, stage): return contextlib.nullcontext()
    async def command(self, args, timeout):
        args = [str(a) for a in args]; job = json.loads(Path(args[args.index('--job') + 1]).read_text()); self.jobs.append(job)
        out = Path(job['output']); out.mkdir(parents=True, exist_ok=True)
        (out / 'Ergebnis.json').write_text(json.dumps({'lines': [{**l, 'file': 'x.wav', 'duration': 1.5, 'sha256': 'y'} for l in job['lines']]}))


def project(pin, emotion='wütend', participants=None):
    scenes = [{'kind': 'line', 'cast': ['Tim'], 'seconds': 4, 'dialogues': [{'speaker': 'Tim', 'text': 'Das ist mein Kuchen!', 'emotion': emotion}]},
              {'kind': 'line', 'cast': ['Oma'], 'seconds': 4, 'dialogues': [{'speaker': 'Oma', 'text': 'Dann iss ihn doch, Tim.', 'emotion': 'ruhig'}]}]
    return {'id': 'v' * 32, 'idea': {'duration': 15, 'episodes': 1, 'fps': 25, 'lip_sync': 'audio', 'speech_engine': 'chatterbox',
                                     'participants': participants or [{'name': 'Tim', 'voice': 'a'}, {'name': 'Oma', 'voice': 'b'}]},
            'plan': {'cast': [{'name': 'Tim'}, {'name': 'Oma'}], 'mood': 'playful'}, 'episodes': [{'scenes': scenes, 'dialogue_mode': 'rich'}], **pin}


def voice_job(tmp_path, pin, **kw):
    from factory_quality import Quality
    folder = tmp_path / ('new' if pin else 'old'); folder.mkdir(parents=True, exist_ok=True)
    d = project(pin, **{k: v for k, v in kw.items() if k in ('emotion', 'participants')})
    studio = Speaking(folder, kw.get('voices')); asyncio.run(Quality.quality_voices(studio, d))
    return d, studio.jobs[-1]


def test_new_projects_voice_with_voice_policy_19_and_nfc_delivery_words(tmp_path):
    old_d, old = voice_job(tmp_path, {}, emotion=nfd('wütend'))
    new_d, new = voice_job(tmp_path, {'sound_policy': 19}, emotion=nfd('wütend'))
    assert old_d['voice_policy'] == old['voice_policy'] == 18 and new_d['voice_policy'] == new['voice_policy'] == 19
    assert old['lines'][0]['emotion'] == nfd('wütend')                   # an old project's job keeps the stored word
    assert new['lines'][0]['emotion'] == 'wütend' and performance_key(new['lines'][0]['emotion']) == 'angry'
    # A project voiced once keeps its pin, whatever its sound policy says.
    again = project({'sound_policy': 19}); again['voice_policy'] = 18
    from factory_quality import Quality
    studio = Speaking(tmp_path / 'again'); asyncio.run(Quality.quality_voices(studio, again))
    assert studio.jobs[-1]['voice_policy'] == 18
