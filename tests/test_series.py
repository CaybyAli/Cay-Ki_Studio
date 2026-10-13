"""Series continuity rules, part label in the film, tolerant pre-encoding queue."""
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
sys.path[:0] = [str(APP), str(Path(__file__).parent)]

from story_policy import structure_errors  # noqa: E402


def episode(*beats):
    return {'scenes': [{'beat': b, 'because': 'weil vorher etwas passiert ist'} for b in beats]}


def test_cliffhanger_allowed_only_for_series_episodes_before_the_last():
    series = episode('problem', 'attempt', 'payoff', 'cliffhanger')
    assert not any('Serienfolge' in e or 'Auflösung' in e for e in structure_errors(series, 24, False, cliffhanger_ok=True))
    assert any('Auflösung/Pointe' in e for e in structure_errors(series, 24, False))               # final episode / single film
    missing_payoff = episode('problem', 'attempt', 'turn', 'cliffhanger')
    assert any('Serienfolge' in e for e in structure_errors(missing_payoff, 24, False, cliffhanger_ok=True))


def test_part_label_is_burned_into_series_episodes(tmp_path):
    import audio_fixtures as fx
    from factory_audio import mix
    from factory_video import finish, file_hash
    line = fx.line(tmp_path, 'E03_S01_T01', 2, 0, 0, 'Lena', 'Wer war das?', fx.speech(1.4))
    scenes = [{'seconds': 2., 'lines': [line], 'ambience': 'room', 'sound_cues': []}]
    approved = Path(mix(tmp_path / 'mix', scenes, 'playful'))
    clip = tmp_path / 'c.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=480x832:rate=25:duration=2',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(clip)], check=True)
    scenes[0]['clips'] = [{'file': str(clip), 'sha256': hashlib.sha256(clip.read_bytes()).hexdigest(), 'seconds': 2.}]
    finish({'folder': str(tmp_path / 'work'), 'fps': 25, 'smooth': True, 'scenes': scenes, 'title': 'T', 'part_label': 'Teil 3/12',
            'output': str(tmp_path / 'Folge_03.mp4'), 'minimum_seconds': 2, 'mood': 'playful', 'mix': None, 'music': None,
            'audio_mix': {'file': str(approved), 'sha256': file_hash(approved)}})
    ass = (tmp_path / 'work/Untertitel.ass').read_text(encoding='utf-8')
    assert ',Part,,0,0,0,,Teil 3/12' in ass and (tmp_path / 'Folge_03.mp4').stat().st_size > 0


class Queue:
    """factory_post.PostProduction.queue_post on a real SQLite table."""
    def __init__(self):
        from factory_post import PostProduction
        self.db = sqlite3.connect(':memory:'); self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE factory_post(id TEXT PRIMARY KEY,run_id TEXT,kind TEXT,episode INTEGER,generation INTEGER,spec TEXT,status TEXT,result TEXT,error TEXT,UNIQUE(run_id,kind,generation,episode))')
        self.queue_post = PostProduction.queue_post.__get__(self)
    def sql(self, q, a=()): self.db.execute(q, a); self.db.commit()
    def rows(self, q, a=()): return [dict(r) for r in self.db.execute(q, a)]


def test_outdated_pre_encoding_is_replaced_not_fatal():
    q = Queue(); d = {'id': 'r1', 'export_generation': 0}
    q.queue_post(d, 'prepare:1:0', 0, {'clips': ['old 5 s piece']})
    q.queue_post(d, 'prepare:1:0', 0, {'clips': ['whole scene']})                  # after the update: one prompt per scene
    assert [json.loads(r['spec'])['clips'] for r in q.rows('SELECT spec FROM factory_post')] == [['whole scene']]
    q.queue_post(d, 'export', 0, {'v': 1})
    try:
        q.queue_post(d, 'export', 0, {'v': 2}); raised = False
    except RuntimeError: raised = True
    assert raised                                                                    # exports stay strict
