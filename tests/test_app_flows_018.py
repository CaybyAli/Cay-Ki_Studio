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
    db = sqlite3.connect(':memory:', check_same_thread=False); db.row_factory = sqlite3.Row
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


def test_form_errors_are_german_name_the_field_and_never_echo_the_input(tmp_path, monkeypatch):
    """Cay saw 'List should have at most 6 items after validation, not 7' and 'String should have at least 1 character'."""
    runtime = tmp_path / 'studio'; (runtime / 'config').mkdir(parents=True); (tmp_path / 'ablage').mkdir()
    (runtime / 'config/ablage.json').write_text(json.dumps({'wsl_root': str(tmp_path / 'ablage'), 'windows_root': 'D:\\Cay_Studio',
                                                            'local_services': {'comfyui': 'http://127.0.0.1:9', 'ollama': 'http://127.0.0.1:9'}}))
    monkeypatch.setenv('CAY_STUDIO_RUNTIME', str(runtime)); sys.modules.pop('server', None)
    import server
    from fastapi.testclient import TestClient
    server.execute('CREATE TABLE IF NOT EXISTS studio_trash(id TEXT PRIMARY KEY, deleted_at TEXT NOT NULL)')
    client = TestClient(server.app, base_url='http://127.0.0.1'); head = {'X-Cay-Token': server.CSRF}
    seven = {'episode': 0, 'scene': 0, 'action': 'Lena hält den Keks hoch.', 'dialogues': [{'speaker': 'Lena', 'text': 'Hallo.'}] * 7}
    answer = client.put('/api/factory/' + 'a' * 32 + '/dialogues', json=seven, headers=head)
    assert answer.status_code == 422 and answer.json() == {'detail': 'Zu viele Sätze: höchstens 6.'}
    answer = client.post('/api/library', json={'name': '  ', 'label': ' '}, headers=head)
    assert answer.json()['detail'] == 'Bitte „Name“ ausfüllen. Bitte „Profilname“ ausfüllen.'
    secret = '7712345678:AAHk3xQ9vYfZpL2mN8rT5wB1cD4eF6gH7iJ' * 9                   # too long, still a secret
    answer = client.post('/api/notify/telegram/token', json={'token': secret, 'consent': True}, headers=head)
    assert answer.status_code == 422 and answer.json()['detail'] == '„Bot-Schlüssel“ ist zu lang: höchstens 400 Zeichen.' and 'AAHk3x' not in answer.text


def test_a_damaged_audio_file_gets_a_german_message_without_paths(tmp_path, capsys):
    """Cay saw "Command '['ffprobe', ... /ablage/00_Eingang/...source.mp3']' returned non-zero exit status 1." and "'duration'"."""
    import subprocess
    from fastapi.testclient import TestClient
    f, db, _ = studio(tmp_path)
    db.execute('CREATE TABLE factory_assets(id TEXT PRIMARY KEY,kind TEXT NOT NULL,path TEXT NOT NULL,sha256 TEXT NOT NULL,name TEXT NOT NULL)')
    app = FastAPI(); f.routes(app); client = TestClient(app)
    flac = subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=3', '-f', 'flac', 'pipe:'], capture_output=True, check=True).stdout
    for name, data in (('kaputt.mp3', bytes(range(256)) * 40), ('ohne_dauer.flac', flac)):
        answer = client.post(f'/api/factory/assets?kind=voice&name={name}', content=data)
        assert answer.status_code == 400 and answer.json()['detail'] == 'Diese Audiodatei lässt sich nicht lesen. Bitte als WAV oder MP3 neu speichern und erneut wählen.', answer.text
    assert 'Audio-Upload nicht lesbar' in capsys.readouterr().out                     # the detail stays in the server log
    assert not list((tmp_path / '00_Eingang/Studio_Referenzen').glob('*'))           # nothing left behind
    wav = tmp_path / 'kurz.wav'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=1', str(wav)], check=True)
    answer = client.post('/api/factory/assets?kind=voice&name=kurz.wav', content=wav.read_bytes())
    assert answer.json()['detail'] == 'Stimmprobe: 2–90 Sekunden; Musik: höchstens 15 Minuten.'   # the real reason stays
    subprocess.run(['ffmpeg', '-nostdin', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=220:duration=3', str(wav)], check=True)
    assert client.post('/api/factory/assets?kind=voice&name=gut.wav', content=wav.read_bytes()).status_code == 200
