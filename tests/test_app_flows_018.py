"""App flows found in the 0.18 review: what Cay clicks in the new app must be reversible,
German and honest (sound edit of a finished film, new edition, uploads, form errors)."""
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))

from factory import Factory  # noqa: E402
from factory_models import Review  # noqa: E402


def studio(tmp_path):
    db = sqlite3.connect(':memory:'); db.row_factory = sqlite3.Row
    db.executescript('''CREATE TABLE factory_runs(id TEXT PRIMARY KEY,request_key TEXT,state TEXT,document TEXT,created TEXT,updated TEXT);
CREATE TABLE factory_control(id TEXT PRIMARY KEY,paused INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS factory_switches(id TEXT PRIMARY KEY,autopilot INTEGER NOT NULL);
CREATE TABLE studio_trash(id TEXT PRIMARY KEY,deleted TEXT);
CREATE TABLE factory_post(id TEXT PRIMARY KEY,run_id TEXT,kind TEXT,episode INTEGER,generation INTEGER,spec TEXT,status TEXT,result TEXT,error TEXT);''')
    f = Factory.__new__(Factory)
    f.g = {'ROOT': tmp_path, 'RUNTIME': tmp_path, 'allowed': lambda p: Path(p), 'now': lambda: '2026-10-16T00:00:00+00:00'}
    f.rows = lambda q, a=(): db.execute(q, a).fetchall()
    f.sql = lambda q, a=(): (db.execute(q, a), db.commit())
    f.busy = None
    app = FastAPI(); f.quality_routes(app); f.routes(app)
    route = {r.path.rsplit('/', 1)[-1]: r.endpoint for r in app.routes if getattr(r, 'path', '').startswith('/api/factory/{rid}/')}
    return f, db, route


def finished(db, rid='d' * 32):
    exports = [{'file': '/ablage/03_Fertige_Videos/Studio/x/Folge_01.mp4', 'sha256': 'aa', 'episode': 0, 'seconds': 30}]
    doc = {'id': rid, 'title': 'Butterblitz', 'state': 'done', 'phase': 'Alle Folgen sind fertig.', 'idea': {'autopilot': True, 'duration': 30, 'episodes': 1},
           'plan': {'cast': [{'name': 'Lena', 'voice_preset': 'woman'}]}, 'episodes': [{'scenes': []}], 'exports': exports, 'export_generation': 2,
           'audio_revision': 3, 'lines': [{'text': 'Hallo.', 'sha256': 'l1'}], 'mix': {'music_mode': 'off'}, 'voice_approval': 'v' * 64,
           'render_segments': {'0:0:0': 's1'}, 'render_tracking_version': 9}
    db.execute('INSERT INTO factory_runs VALUES(?,?,?,?,?,?)', (rid, rid, 'done', json.dumps(doc), 'x', 'x')); db.commit()
    return rid, doc


def call(route, name, f, rid, *extra):
    return asyncio.run(route[name](rid, Review(revision=f.get(rid)['revision']), *extra))


def test_cancel_sound_edit_brings_back_the_finished_film_exactly(tmp_path):
    """Cay: one click on 'Lautstärke und Ton ändern' removed the downloads with no way back."""
    f, db, route = studio(tmp_path)
    rid, doc = finished(db)
    before = {k: v for k, v in f.get(rid).items() if k not in ('updated', 'revision')}
    call(route, 'reopen-output', f, rid)
    d = f.get(rid)
    assert d['state'] == 'voice_review' and d['exports'] == [] and d['sound_edit_undo']['audio_revision'] == 3
    call(route, 'cancel-sound-edit', f, rid)
    after = {k: v for k, v in f.get(rid).items() if k not in ('updated', 'revision')}
    assert after == before                       # exports, generation, approval, segments, phase: all as before


def test_cancel_is_refused_once_the_sound_changed(tmp_path):
    f, db, route = studio(tmp_path)
    rid, _ = finished(db)
    call(route, 'reopen-output', f, rid)
    d = f.get(rid); d['audio_revision'] = 4; f.save(d)                   # a slider remix finished
    with pytest.raises(HTTPException) as refused:
        call(route, 'cancel-sound-edit', f, rid)
    assert refused.value.status_code == 409 and 'schon geändert' in refused.value.detail
    d = f.get(rid); d['audio_revision'] = 3; d['plan']['cast'][0]['voice_preset'] = 'grandma'; f.save(d)
    with pytest.raises(HTTPException):                                   # same revision, other material
        call(route, 'cancel-sound-edit', f, rid)
    assert f.get(rid)['state'] == 'voice_review'


def test_no_undo_after_the_autopilot_switch(tmp_path):
    f, db, route = studio(tmp_path)
    rid, _ = finished(db)
    call(route, 'reopen-output', f, rid)
    asyncio.run(route['autopilot'](rid, type('Switch', (), {'enabled': True})()))
    assert 'sound_edit_undo' not in f.get(rid)
    with pytest.raises(HTTPException):
        call(route, 'cancel-sound-edit', f, rid)


def test_cancel_sends_no_second_film_ready_message(tmp_path):
    from test_notify import studio as notify_studio, insert, connect_telegram, outbox, run
    g, n, factory, _ = notify_studio(tmp_path); connect_telegram(n)
    done = run(state='done', idea={'autopilot': True, 'episodes': 1}, audio_revision=3, export_generation=0,
               exports=[{'file': '/x.mp4', 'sha256': 'aa', 'seconds': 30}]); insert(g, done)   # finished before notifications
    reopened = dict(done, state='voice_review', sound_edit=True, exports=[], export_generation=1)
    factory.save(reopened)
    factory.save(dict(done))                                             # "Abbrechen, fertigen Film behalten"
    assert not outbox(g)
