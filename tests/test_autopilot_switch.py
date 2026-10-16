"""Cay: switching the autopilot off and on again during a film made it work "nur noch schrittweise".
Cause: a running step saves its own copy of the document after every section and wrote the old
switch back. The switch now lives beside the document (like the pause flag)."""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))

from factory import Factory  # noqa: E402


def studio(tmp_path):
    db = sqlite3.connect(':memory:'); db.row_factory = sqlite3.Row
    db.executescript('''CREATE TABLE factory_runs(id TEXT PRIMARY KEY,request_key TEXT,state TEXT,document TEXT,created TEXT,updated TEXT);
CREATE TABLE factory_control(id TEXT PRIMARY KEY,paused INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS factory_switches(id TEXT PRIMARY KEY,autopilot INTEGER NOT NULL);
CREATE TABLE studio_trash(id TEXT PRIMARY KEY,deleted TEXT);
CREATE TABLE factory_post(id TEXT PRIMARY KEY,run_id TEXT,kind TEXT,episode INTEGER,generation INTEGER,spec TEXT,status TEXT,result TEXT,error TEXT);''')
    f = Factory.__new__(Factory)
    f.g = {'ROOT': tmp_path, 'allowed': lambda p: Path(p), 'now': lambda: '2026-10-16T00:00:00+00:00'}
    f.rows = lambda q, a=(): db.execute(q, a).fetchall()
    f.sql = lambda q, a=(): (db.execute(q, a), db.commit())
    return f, db


def test_a_running_step_cannot_switch_the_autopilot_back(tmp_path):
    f, db = studio(tmp_path)
    doc = {'id': 'r' * 32, 'state': 'rendering', 'idea': {'autopilot': False}, 'episodes': [], 'exports': []}
    db.execute('INSERT INTO factory_runs VALUES(?,?,?,?,?,?)', (doc['id'], doc['id'], 'rendering', json.dumps(doc), 'x', 'x')); db.commit()
    worker_copy = f.get(doc['id'])                                   # the step reads the project once
    # Cay switches the autopilot on (what the route does)
    f.sql('INSERT INTO factory_switches(id,autopilot) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET autopilot=excluded.autopilot', (doc['id'], 1))
    d = f.get(doc['id']); d['idea']['autopilot'] = True; f.save(d)
    worker_copy['phase'] = 'Animation · Abschnitt 4/10'; f.save(worker_copy)   # the step saves its old copy
    assert f.get(doc['id'])['idea']['autopilot'] is True
    f.sql('UPDATE factory_switches SET autopilot=0 WHERE id=?', (doc['id'],))
    assert f.get(doc['id'])['idea']['autopilot'] is False


def test_projects_never_switched_keep_their_own_setting(tmp_path):
    f, db = studio(tmp_path)
    doc = {'id': 's' * 32, 'state': 'image_review', 'idea': {'autopilot': True}, 'episodes': [], 'exports': []}
    db.execute('INSERT INTO factory_runs VALUES(?,?,?,?,?,?)', (doc['id'], doc['id'], 'image_review', json.dumps(doc), 'x', 'x')); db.commit()
    assert f.get(doc['id'])['idea']['autopilot'] is True


def test_reopened_sound_waits_for_cay_even_with_autopilot(tmp_path):
    """Cay: the music volume could not be changed. The sliders sit at the sound stop, which the
    autopilot used to approve at once. Reopening the sound of a film now keeps that stop for Cay,
    across every remix, until he approves it himself."""
    from fastapi import FastAPI
    f, db = studio(tmp_path)
    f.busy = None; f.g['RUNTIME'] = tmp_path
    app = FastAPI(); f.quality_routes(app); f.routes(app)
    route = {r.path.rsplit('/', 1)[-1]: r.endpoint for r in app.routes if getattr(r, 'path', '').startswith('/api/factory/{rid}/')}
    rid = 't' * 32
    doc = {'id': rid, 'state': 'done', 'idea': {'autopilot': True, 'duration': 30}, 'episodes': [{'scenes': []}], 'exports': [{'file': 'x.mp4'}]}
    db.execute('INSERT INTO factory_runs VALUES(?,?,?,?,?,?)', (rid, rid, 'done', json.dumps(doc), 'x', 'x')); db.commit()
    import asyncio
    from factory_models import Review
    asyncio.run(route['reopen-output'](rid, Review(revision=f.get(rid)['revision'])))
    d = f.get(rid)
    assert d['state'] == 'voice_review' and d['sound_edit'] is True and d['exports'] == []
    assert d['export_history'][0]['exports'] == [{'file': 'x.mp4'}]          # the finished film stays listed
    f.auto_voices = lambda d: (d.update(state='rendering'), True)[1]         # a mix that passes every check
    f.autopilot_tick()
    assert f.get(rid)['state'] == 'voice_review'                             # not approved behind Cay's back
    d['audio_revision'] = 5; f.save(d); f.autopilot_tick()                   # a slider remix: still his stop
    assert f.get(rid)['state'] == 'voice_review'
    # Switching the autopilot hands the stop back to it.
    asyncio.run(route['autopilot'](rid, type('Switch', (), {'enabled': True})()))
    assert 'sound_edit' not in f.get(rid)
    f.autopilot_tick()
    assert f.get(rid)['state'] == 'rendering'


def test_the_hold_only_applies_to_the_sound_stop():
    from autopilot import Autopilot
    pilot = Autopilot()
    assert pilot.autopilot_waits({'state': 'voice_review', 'sound_edit': True})
    assert not pilot.autopilot_waits({'state': 'sample_review', 'sound_edit': True})
    assert not pilot.autopilot_waits({'state': 'voice_review'})
