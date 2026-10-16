"""Notifications: which transitions count (incl. autopilot), dedupe, outbox retry/backoff,
Telegram connect, ntfy topic and encoding, token masking, secrets never in diagnostics."""
import asyncio
import importlib.util
import json
import logging
import re
import sqlite3
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'cay_studio_app'))

import notify  # noqa: E402
from autopilot import Autopilot  # noqa: E402
from factory import Factory  # noqa: E402
from notify import Notifier, event_of, signature, transition_key, scrub, mask, new_topic  # noqa: E402

TOKEN = '7712345678:AAHk3xQ9vYfZpL2mN8rT5wB1cD4eF6gH7iJ'
CHAT = {'id': 424242, 'name': 'Cay'}


def studio(tmp_path):
    path = tmp_path / 'db.sqlite3'

    @contextmanager
    def conn():
        db = sqlite3.connect(path, timeout=15); db.row_factory = sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def execute(sql, args=()):
        with conn() as db: db.execute(sql, args)

    def rows(sql, args=()):
        with conn() as db: return [dict(x) for x in db.execute(sql, args).fetchall()]
    events = []
    root = tmp_path / 'ablage'; root.mkdir()
    runtime = tmp_path / 'studio'; (runtime / 'config').mkdir(parents=True)
    g = {'conn': conn, 'execute': execute, 'rows': rows, 'now': lambda: datetime.now(timezone.utc).isoformat(), 'RUNTIME': runtime,
         'ROOT': root, 'PORT': 8787, 'STOPPING': False, 'record': lambda kind, detail: events.append((kind, detail)),
         'allowed': lambda p: Path(p).resolve()}
    execute('CREATE TABLE factory_runs(id TEXT PRIMARY KEY,request_key TEXT UNIQUE NOT NULL,state TEXT NOT NULL,document TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL)')
    n = Notifier(g); n.init(); g['notifier'] = n

    async def no_wait(): pass
    n.telegram_wait = no_wait
    factory = Factory.__new__(Factory); factory.g = g; factory.init_post()
    return g, n, factory, events


def run(rid='p1', state='rendering', **extra):
    return {'id': rid, 'title': 'Der Keks-Krieg', 'state': state, 'idea': {'autopilot': False, 'episodes': 1}, 'episodes': [], **extra}


def insert(g, d):
    g['execute']('INSERT INTO factory_runs VALUES(?,?,?,?,?,?)', (d['id'], d['id'], d['state'], json.dumps(d), 'x', 'x'))


def connect_telegram(n):
    n.change(lambda d: d['telegram'].update(token=TOKEN, chat=CHAT, bot={'id': 1, 'name': 'Cay Bot', 'username': 'cay_test_bot'}))


def outbox(g):
    return g['rows']('SELECT * FROM notify_outbox ORDER BY id')


# ---------- which transitions count ----------

def test_events_with_and_without_autopilot():
    on = {'autopilot': True}
    assert event_of(run(state='done')) == 'done'
    assert event_of(run(state='blocked', error='x')) == 'blocked'
    assert event_of(run(state='cast_review', idea=on)) == 'turn'                       # figure check: always Cay
    for state in ('image_review', 'voice_review', 'sample_review'):
        assert event_of(run(state=state)) == 'turn'                                    # autopilot off
        assert event_of(run(state=state, idea=on)) is None                             # autopilot passes it in seconds
        stopped = run(state=state, idea=on, audio_revision=3, autopilot_stopped={'state': state, 'audio_revision': 3, 'reason': 'Tondatei verändert'})
        assert event_of(stopped) == 'turn'                                             # autopilot gave up here
        old_stop = run(state=state, idea=on, audio_revision=4, autopilot_stopped={'state': state, 'audio_revision': 3, 'reason': 'x'})
        assert event_of(old_stop) is None                                              # new sound version: it tries again
    for state in ('planning', 'pictures', 'voicing', 'rendering', 'audio_mixing', 'finishing', 'correcting'):
        assert event_of(run(state=state)) is None
    assert event_of(run(state='image_review', paused=True)) is None                    # Cay paused it himself
    assert event_of(run(state='done', deleted=True)) is None


def test_speech_check_block_waits_for_the_autopilot_retake():
    d = run(state='blocked', idea={'autopilot': True}, resume_state='audio_mixing', error='SPRACHPRÜFUNG: Zeile 3 unhörbar')
    assert event_of(d) is None                         # autopilot_tick retakes the lines by itself
    assert event_of(d, settled=True) == 'blocked'      # still blocked after the settle time: Cay is needed
    d['idea']['autopilot'] = False
    assert event_of(d) == 'blocked'


def test_events_follow_the_real_autopilot_rules():
    """An event is suppressed exactly where autopilot.apply_autopilot really moves the project on."""
    class Pilot(Autopilot):
        def path(self, p): return Path(p)
    scenes = [{'variants': [{'id': 'a' * 32, 'key': 'image:0:0:0:0'}], 'selected': None, 'round': 0}]
    d = run(state='image_review', idea={'autopilot': True}, episodes=[{'scenes': scenes}])
    assert event_of(d) is None and Pilot().apply_autopilot(d) and d['state'] == 'voicing'
    sample = run(state='sample_review', idea={'autopilot': True}, sample={'key': 'k'})
    assert event_of(sample) is None and Pilot().apply_autopilot(sample)


def test_transition_keys_are_stable_and_change_with_new_material():
    a = run(state='done', exports=[{'file': '/f/1.mp4', 'sha256': 'aa', 'seconds': 62.0}], export_generation=1)
    assert transition_key(a, 'done') == transition_key(json.loads(json.dumps(a)), 'done')
    b = dict(a, exports=[{'file': '/f/1.mp4', 'sha256': 'bb', 'seconds': 62.0}], export_generation=2)
    assert transition_key(a, 'done') != transition_key(b, 'done')
    e1, e2 = run(state='blocked', error='A', resume_state='rendering'), run(state='blocked', error='B', resume_state='rendering')
    assert transition_key(e1, 'blocked') != transition_key(e2, 'blocked')
    assert signature(run(state='cast_review')) != signature(run(state='image_review'))


def test_texts_are_lively_addressed_and_name_the_situation():
    d = run(state='done', exports=[{'file': '/f/1.mp4', 'sha256': 'aa', 'seconds': 61.6, 'cover': {'file': '/f/Cover_1.png'}}])
    done = notify.compose(d, 'done')
    assert 'Sir Cay' in done['head'] and done['head'][0] in '🎬✨🏆' and '„Der Keks-Krieg“' in done['lines'][0] and '62' in done['lines'][0]
    assert done['films'][0]['cover'] == '/f/Cover_1.png'
    assert notify.compose(d, 'done') == done                                     # same transition, same words
    assert 'Chef' in notify.compose(d, 'done', name='Chef')['head']
    series = run(state='done', idea={'episodes': 3}, exports=[{'file': f'/f/{i}.mp4', 'seconds': 60} for i in range(3)])
    assert '3 Folgen' in ' '.join(notify.compose(series, 'done')['lines'])
    blocked = notify.compose(run(state='blocked', error='x ' * 300), 'blocked')
    assert blocked['head'] == '⚠️ Sir Cay, „Der Keks-Krieg“ hat angehalten.' and len(blocked['lines'][0]) <= 200
    stop = run(state='voice_review', idea={'autopilot': True}, audio_revision=1, autopilot_stopped={'state': 'voice_review', 'audio_revision': 1, 'reason': 'Mindestdauer nicht erreicht'})
    turn = notify.compose(stop, 'turn')
    assert turn['head'] == '🎧 Ohren auf, Sir Cay!' and turn['lines'] == ['„Der Keks-Krieg“: Der Ton wartet auf deine Freigabe.', 'Der Autopilot wartet: Mindestdauer nicht erreicht']


# ---------- hook in Factory.save and dedupe ----------

def test_save_announces_each_transition_once(tmp_path):
    g, n, factory, _ = studio(tmp_path); connect_telegram(n)
    d = run(); insert(g, d)
    factory.save(dict(d, phase='rechnet'))                                   # no event state
    assert not g['rows']('SELECT * FROM notify_events')
    done = dict(d, state='done', exports=[{'file': str(tmp_path / 'f.mp4'), 'sha256': 'aa', 'seconds': 62}])
    factory.save(done); factory.save(dict(done, phase='angesehen')); factory.save(done)
    assert [r['event'] for r in g['rows']('SELECT * FROM notify_events')] == ['done']
    assert [(r['channel'], r['event'], r['status']) for r in outbox(g)] == [('telegram', 'done', 'queued')]
    # A stale copy flips the state back and forth: same material, still only one message.
    factory.save(dict(d, state='finishing')); factory.save(done)
    assert len(outbox(g)) == 1


def test_same_failure_again_is_not_repeated_but_a_new_one_is(tmp_path):
    g, n, factory, _ = studio(tmp_path); connect_telegram(n)
    d = run(); insert(g, d)
    factory.save(dict(d, state='blocked', resume_state='rendering', error='ComfyUI: out of memory'))
    factory.save(dict(d, state='rendering'))
    factory.save(dict(d, state='blocked', resume_state='rendering', error='ComfyUI: out of memory'))
    factory.save(dict(d, state='rendering'))
    factory.save(dict(d, state='blocked', resume_state='rendering', error='Datei fehlt'))
    assert [json.loads(r['payload'])['lines'][0] for r in outbox(g)] == ['ComfyUI: out of memory', 'Datei fehlt']


def test_states_reached_before_the_update_are_not_announced(tmp_path):
    g, n, factory, _ = studio(tmp_path); connect_telegram(n)
    old = run(state='done', exports=[{'file': '/x.mp4', 'sha256': 'aa', 'seconds': 30}]); insert(g, old)
    factory.save(dict(old, phase='Alle Folgen sind fertig.'))
    review = run('p2', state='image_review'); insert(g, review)
    factory.save(dict(review, episodes=[{'scenes': [{'variants': [], 'selected': 'x'}]}]))   # Cay picks an image
    assert not g['rows']('SELECT * FROM notify_events')


def test_restore_and_resume_do_not_announce_the_old_state(tmp_path):
    g, n, factory, _ = studio(tmp_path); connect_telegram(n)
    done = run(state='done', deleted=True, paused=True, exports=[{'file': '/x.mp4', 'sha256': 'aa', 'seconds': 30}]); insert(g, done)
    factory.save(dict(done, deleted=False, paused=False))                       # back from the trash
    review = run('p2', state='image_review', paused=True); insert(g, review)
    factory.save(dict(review, paused=False))                                    # Cay presses "Fortsetzen"
    assert not g['rows']('SELECT * FROM notify_events')


def test_reopening_the_sound_is_not_announced_but_the_finished_remix_is(tmp_path):
    g, n, factory, _ = studio(tmp_path); connect_telegram(n)
    done = run(state='done', idea={'autopilot': True, 'episodes': 1}, audio_revision=3, exports=[{'file': '/x.mp4', 'sha256': 'aa', 'seconds': 30}]); insert(g, done)
    reopened = dict(done, state='voice_review', sound_edit=True, exports=[], export_generation=1)
    factory.save(reopened)                                                      # Cay clicks "Lautstärke und Ton ändern"
    assert not outbox(g)
    factory.save(dict(reopened, state='voicing', audio_only=True))              # a slider remixes
    factory.save(dict(reopened, audio_revision=4, previews=[{'sha256': 'bb'}])) # remix ready: Cay may have walked away
    assert [r['event'] for r in outbox(g)] == ['turn']


def test_autopilot_stop_is_announced_but_its_passing_is_not(tmp_path):
    g, n, factory, _ = studio(tmp_path); connect_telegram(n)
    d = run(state='voicing', idea={'autopilot': True}, audio_revision=2); insert(g, d)
    factory.save(dict(d, state='voice_review'))                                 # autopilot will approve it
    assert not outbox(g)
    stopped = dict(d, state='voice_review', autopilot_stopped={'state': 'voice_review', 'audio_revision': 2, 'reason': 'Tondatei verändert'})
    factory.save(stopped); factory.save(stopped)
    assert [r['event'] for r in outbox(g)] == ['turn']
    cast = run('p3', state='pictures', idea={'autopilot': True}); insert(g, cast)
    factory.save(dict(cast, state='cast_review'))
    assert [r['event'] for r in outbox(g)] == ['turn', 'turn']


def test_stuck_autopilot_is_found_by_the_sweep(tmp_path):
    g, n, factory, _ = studio(tmp_path); connect_telegram(n); g['factory'] = factory
    factory.controlled = lambda d: d
    d = run(state='image_review', idea={'autopilot': True}, episodes=[{'scenes': [{'variants': [], 'selected': None}]}])
    insert(g, d)
    ago = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    g['execute']('UPDATE factory_runs SET updated=? WHERE id=?', (ago, d['id']))
    n.sweep(); n.sweep()
    rows = outbox(g)
    assert [r['event'] for r in rows] == ['turn'] and 'nicht allein weiter' in rows[0]['payload']


def test_event_switches_and_channels(tmp_path):
    g, n, factory, _ = studio(tmp_path)
    d = run(); insert(g, d)
    factory.save(dict(d, state='blocked', error='A'))
    assert g['rows']('SELECT * FROM notify_events') and not outbox(g)          # browser feed only: no channel on
    connect_telegram(n); n.change(lambda s: s.update(events={'done': True, 'turn': True, 'blocked': False}))
    factory.save(dict(d, state='rendering')); factory.save(dict(d, state='blocked', error='B'))
    assert not outbox(g)
    assert n.feed(None)['events'] == [] and n.feed(0)['events'] == []          # switched off for the browser too


def test_a_broken_notifier_never_breaks_saving(tmp_path):
    g, n, factory, events = studio(tmp_path)
    d = run(); insert(g, d)

    def broken(*a, **k): raise RuntimeError('kaputt ' + TOKEN)
    n.record = broken
    factory.save(dict(d, state='done'))
    assert g['rows']('SELECT state FROM factory_runs')[0]['state'] == 'done'
    assert events and events[0][0] == 'notify_error' and TOKEN not in events[0][1]
    n.g = {}                                                                    # even a notifier without any access
    factory.save(dict(d, state='blocked', error='x'))
    assert g['rows']('SELECT state FROM factory_runs')[0]['state'] == 'blocked'


# ---------- outbox: retry, backoff, Telegram answers ----------

def sender(tmp_path, answers):
    g, n, factory, events = studio(tmp_path); connect_telegram(n)
    seen = []

    def handler(request):
        seen.append(request)
        status, body = answers.pop(0) if answers else (200, {'ok': True, 'result': {}})
        return httpx.Response(status, json=body)
    n.transport = httpx.MockTransport(handler)
    d = run(); insert(g, d)
    factory.save(dict(d, state='blocked', error='Kaputt'))
    return g, n, seen, events


def due_now(g):
    g['execute']("UPDATE notify_outbox SET next_try=0 WHERE status='queued'")


def test_backoff_then_gives_up(tmp_path):
    answers = [(500, {'ok': False, 'error_code': 500, 'description': 'Internal'})] * 5
    g, n, seen, _ = sender(tmp_path, answers)
    delays = []
    for _ in range(5):
        due_now(g); before = time.time()
        asyncio.run(n.send_due())
        row = outbox(g)[0]
        if row['status'] == 'queued': delays.append(round(row['next_try'] - before))
    assert delays == [30, 120, 600, 1800]
    row = outbox(g)[0]
    assert row['status'] == 'failed' and row['attempts'] == 5 and 'Störung' in row['error'] and len(seen) == 5
    status = g['rows']('SELECT * FROM notify_status')[0]
    assert not status['ok'] and 'Störung' in status['detail']


def test_rate_limit_waits_as_told_and_does_not_count(tmp_path):
    g, n, seen, _ = sender(tmp_path, [(429, {'ok': False, 'error_code': 429, 'description': 'Too Many Requests: retry after 7', 'parameters': {'retry_after': 7}})])
    before = time.time(); asyncio.run(n.send_due())
    row = outbox(g)[0]
    assert row['status'] == 'queued' and row['attempts'] == 0 and 7 <= row['next_try'] - before <= 9
    due_now(g); asyncio.run(n.send_due())
    assert outbox(g)[0]['status'] == 'sent' and len(seen) == 2


def test_blocked_bot_fails_at_once_with_a_clear_german_message(tmp_path):
    g, n, seen, _ = sender(tmp_path, [(403, {'ok': False, 'error_code': 403, 'description': 'Forbidden: bot was blocked by the user'})])
    asyncio.run(n.send_due())
    row = outbox(g)[0]
    assert row['status'] == 'failed' and row['attempts'] == 1 and '„Start“' in row['error']
    assert n.public()['telegram']['last']['ok'] is False


def test_unreachable_network_retries_and_never_stores_the_token(tmp_path):
    g, n, factory, _ = studio(tmp_path); connect_telegram(n)

    def handler(request): raise httpx.ConnectError(f'cannot connect to {request.url}', request=request)
    n.transport = httpx.MockTransport(handler)
    d = run(); insert(g, d); factory.save(dict(d, state='blocked', error='x'))
    asyncio.run(n.send_due())
    row = outbox(g)[0]
    assert row['status'] == 'queued' and 'nicht erreichbar' in row['error']
    everything = json.dumps([g['rows'](f'SELECT * FROM {t}') for t in ('notify_outbox', 'notify_status', 'notify_events')], ensure_ascii=False)
    assert TOKEN not in everything and TOKEN.split(':')[1] not in everything


def test_message_text_and_photo(tmp_path):
    g, n, factory, _ = studio(tmp_path); connect_telegram(n)
    film = tmp_path / 'ablage' / 'Film.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=1080x1920:r=25:d=2', '-pix_fmt', 'yuv420p', str(film)], check=True)
    seen = []
    n.transport = httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json={'ok': True, 'result': {}}))
    d = run(); insert(g, d)
    factory.save(dict(d, state='done', exports=[{'file': str(film), 'sha256': 'aa', 'seconds': 2.0}]))
    asyncio.run(n.send_due())
    assert [r.url.path.rsplit('/', 1)[1] for r in seen] == ['sendPhoto']
    body = seen[0].content
    assert b'\xff\xd8' in body and 'Sir Cay'.encode() in body and '„Der Keks-Krieg“'.encode() in body and b'Am PC \xc3\xb6ffnen: http://127.0.0.1:8787/#p=p1' in body
    assert outbox(g)[0]['status'] == 'sent'


def test_film_is_sent_after_the_message_and_retried_alone(tmp_path):
    g, n, factory, _ = studio(tmp_path); connect_telegram(n)
    n.change(lambda s: s['telegram'].update(film=True, preview=False))
    film = tmp_path / 'ablage' / 'Film.mp4'; film.write_bytes(b'\0' * 2048)
    answers = [(200, {'ok': True, 'result': {}}), (502, {'ok': False, 'error_code': 502, 'description': 'Bad Gateway'}), (200, {'ok': True, 'result': {}})]
    seen = []

    def handler(request):
        seen.append(request.url.path.rsplit('/', 1)[1]); status, body = answers.pop(0); return httpx.Response(status, json=body)
    n.transport = httpx.MockTransport(handler)
    d = run(); insert(g, d)
    factory.save(dict(d, state='done', exports=[{'file': str(film), 'sha256': 'aa', 'seconds': 62.0}]))
    asyncio.run(n.send_due()); due_now(g); asyncio.run(n.send_due())
    assert seen == ['sendMessage', 'sendVideo', 'sendVideo'] and outbox(g)[0]['status'] == 'sent'


# ---------- setup: Telegram token and chat, ntfy ----------

def test_token_is_found_in_pasted_text_and_checked_with_getme(tmp_path):
    g, n, _, _ = studio(tmp_path)
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(200, json={'ok': True, 'result': {'id': 7712345678, 'is_bot': True, 'first_name': 'Cay Studio', 'username': 'cay_studio_bot'}})
    n.transport = httpx.MockTransport(handler)
    token, bot = asyncio.run(n.check_token(f'Done! Use this token to access the HTTP API:\n{TOKEN}\nKeep your token secure'))
    assert token == TOKEN and bot == {'id': 7712345678, 'name': 'Cay Studio', 'username': 'cay_studio_bot'} and urls[0].endswith(f'/bot{TOKEN}/getMe')
    with pytest.raises(Exception) as wrong:
        asyncio.run(n.check_token('hallo'))
    assert 'kein Bot-Schlüssel' in wrong.value.detail
    n.transport = httpx.MockTransport(lambda r: httpx.Response(401, json={'ok': False, 'error_code': 401, 'description': 'Unauthorized'}))
    with pytest.raises(Exception) as unknown:
        asyncio.run(n.check_token(TOKEN))
    assert unknown.value.status_code == 400 and 'kennt diesen Bot-Schlüssel nicht' in unknown.value.detail and TOKEN not in unknown.value.detail


def test_connect_takes_the_newest_private_chat(tmp_path):
    g, n, _, _ = studio(tmp_path)
    updates = [{'update_id': 10, 'message': {'chat': {'id': -100, 'type': 'group', 'title': 'Familie'}}},
               {'update_id': 11, 'message': {'chat': {'id': 111, 'type': 'private', 'first_name': 'Alt'}, 'text': '/start'}},
               {'update_id': 12, 'my_chat_member': {'chat': {'id': 222, 'type': 'private', 'first_name': 'Cay', 'last_name': 'H.'}}},
               {'update_id': 13, 'channel_post': {'chat': {'id': -5, 'type': 'channel'}}}]
    n.transport = httpx.MockTransport(lambda r: httpx.Response(200, json={'ok': True, 'result': updates}))
    assert asyncio.run(n.find_chat(TOKEN)) == {'id': 222, 'name': 'Cay H.'}
    n.transport = httpx.MockTransport(lambda r: httpx.Response(200, json={'ok': True, 'result': []}))
    assert asyncio.run(n.find_chat(TOKEN)) is None


def test_ntfy_topic_is_random_and_long():
    topics = {new_topic() for _ in range(50)}
    assert len(topics) == 50 and all(re.fullmatch(r'cay-studio-[a-z0-9]{24}', t) for t in topics)


def test_ntfy_sends_umlauts_as_url_encoded_parameters_and_a_small_preview(tmp_path):
    g, n, factory, _ = studio(tmp_path)
    n.change(lambda s: s['ntfy'].update(topic='cay-studio-' + 'a' * 24, preview=True))
    film = tmp_path / 'ablage' / 'Film.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=1080x1920:r=25:d=2', '-pix_fmt', 'yuv420p', str(film)], check=True)
    seen = []
    n.transport = httpx.MockTransport(lambda r: seen.append(r) or httpx.Response(200, json={'id': 'x'}))
    d = run(title='Kekse für Ömer'); insert(g, d)
    factory.save(dict(d, state='done', exports=[{'file': str(film), 'sha256': 'aa', 'seconds': 2.0}]))
    asyncio.run(n.send_due())
    request = seen[0]
    query = parse_qs(urlsplit(str(request.url)).query)
    assert request.method == 'PUT' and request.url.path == '/cay-studio-' + 'a' * 24
    assert 'Sir Cay' in query['title'][0] and 'Ömer' in query['message'][0] and '%C3%96' in str(request.url) and query['filename'] == ['vorschau.jpg']
    assert query['tags'] == ['white_check_mark'] and 'Am PC öffnen' in query['message'][0]
    assert request.content[:2] == b'\xff\xd8' and len(request.content) <= 2 * 1024 * 1024
    assert all(ord(c) < 128 for k, v in request.headers.items() for c in k + v)   # nothing non-ASCII in headers


def test_consent_text_matches_what_is_sent_by_default(tmp_path):
    """The text Cay agrees to must say that the preview picture goes out unless he switches it off."""
    _, n, _, _ = studio(tmp_path); state = n.public()
    assert state['telegram']['preview'] and state['ntfy']['preview'] and not state['telegram']['film']
    app = (ROOT / 'cay_studio_app/web/app2/app.js').read_text(encoding='utf-8')
    for channel in ('Telegram', 'ntfy.sh'):
        disclosure = app.split(f'<b>Was an {channel} geht</b>')[1].split('</ul>')[0]
        assert 'Vorschaubild' in disclosure and 'von Anfang an eingeschaltet' in disclosure and 'auf Wunsch ein Vorschaubild' not in disclosure
    assert 'Den fertigen Film nur, wenn du das einschaltest' in app.split('<b>Was an Telegram geht</b>')[1].split('</ul>')[0]


# ---------- secrets ----------

def test_token_is_masked_and_the_settings_file_is_private(tmp_path):
    g, n, _, _ = studio(tmp_path); connect_telegram(n)
    state = json.dumps(n.public(), ensure_ascii=False)
    assert TOKEN not in state and TOKEN.split(':')[1] not in state and mask(TOKEN) in state
    mode = stat.S_IMODE((g['RUNTIME'] / 'config/benachrichtigungen.json').stat().st_mode)
    assert mode == 0o600
    (g['RUNTIME'] / 'config/benachrichtigungen.json').chmod(0o644); n.load()
    assert stat.S_IMODE((g['RUNTIME'] / 'config/benachrichtigungen.json').stat().st_mode) == 0o600


def test_disconnect_forgets_the_secret_and_drops_waiting_messages(tmp_path):
    g, n, seen, _ = sender(tmp_path, [])
    n.disconnect('telegram')
    assert n.load()['telegram'] == {} and outbox(g)[0]['status'] == 'dropped'
    assert TOKEN not in (g['RUNTIME'] / 'config/benachrichtigungen.json').read_text()


def test_scrub_and_log_filter_remove_token_and_topic():
    topic = 'cay-studio-' + 'k' * 24
    assert scrub(f'GET https://api.telegram.org/bot{TOKEN}/getMe failed, topic {topic}') == 'GET https://api.telegram.org/bot[entfernt]/getMe failed, topic [Thema]'
    captured = []

    class Keep(logging.Handler):
        def emit(self, record): captured.append(record.getMessage())
    logger = logging.getLogger('httpx'); handler = Keep(); logger.addHandler(handler); old = logger.level; logger.setLevel(logging.INFO)
    try:
        logger.info('HTTP Request: %s %s "%s"', 'POST', f'https://api.telegram.org/bot{TOKEN}/sendMessage', 'HTTP/1.1 200 OK')
    finally:
        logger.removeHandler(handler); logger.setLevel(old)
    assert captured and TOKEN not in captured[0] and '[entfernt]' in captured[0]


def test_diagnose_report_never_prints_the_secrets(tmp_path, capsys):
    g, n, _, _ = studio(tmp_path); connect_telegram(n)
    topic = 'cay-studio-' + 'q' * 24
    n.change(lambda s: s['ntfy'].update(topic=topic))
    # Even a detail that slipped through unscrubbed must not reach the report.
    g['execute']("INSERT INTO notify_status VALUES('telegram',0,'2026-10-15',?)", (f'Fehler bei https://api.telegram.org/bot{TOKEN}/sendPhoto und {topic}',))
    spec = importlib.util.spec_from_file_location('cay_diagnose', ROOT / 'Cay_Studio_Diagnose.py')
    diagnose = importlib.util.module_from_spec(spec); spec.loader.exec_module(diagnose)
    diagnose.RUNTIME = g['RUNTIME']
    db = sqlite3.connect(tmp_path / 'db.sqlite3'); db.row_factory = sqlite3.Row
    diagnose.notifications(db)
    print(diagnose.cleaner()(f'log: token={TOKEN} topic={topic}'))
    out = capsys.readouterr().out
    assert 'Telegram verbunden' in out and 'ntfy an' in out
    assert TOKEN not in out and TOKEN.split(':')[1] not in out and topic not in out
