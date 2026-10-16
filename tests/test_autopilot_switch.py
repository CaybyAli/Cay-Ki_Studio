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
