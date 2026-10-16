"""Notifications (0.18): Cay hears about it when a film is done, when he is needed or when a project stopped.

Everything is off until Cay switches a channel on, and every channel that sends data off the PC
says beforehand what goes where.

  Am PC     the studio tab shows a browser notification. Nothing leaves the PC. The tab reads the
            event feed below (GET /api/notify/feed); this module only records the events.
  Telegram  his own bot (created with @BotFather). Free, official API, can carry a preview and the film.
  ntfy      a random topic on ntfy.sh, no account. Free, preview up to 2 MB.

WhatsApp is not offered: Meta bills every message a business sends on its own, and the free
gateways are unofficial third parties.

How it works
  1. Factory.save() asks before() and after() around its write. Only a change of the project's
     notification signature (event + state) counts, compared with the stored previous document.
     Every event also has a dedupe key (project + event + a stable key of what is waiting), so a
     transition is never announced twice, whatever saves follow.
  2. The event is stored in notify_events (local, feeds the browser) and, for every enabled
     channel, in notify_outbox. A background sender delivers with a 10 s timeout and backs off
     30 s, 2 min, 10 min, 30 min before it gives up.
  3. Secrets (bot token, ntfy topic) live only in config/benachrichtigungen.json (0600) in the
     runtime folder. The database, which the updater also backs up to the Ablage, never holds them;
     the API shows the token masked; errors and logs are scrubbed.

A notification problem must never break saving or rendering: every hook swallows its own errors.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException

from autopilot import Autopilot
from factory_models import Strict
from pydantic import Field

TELEGRAM = os.environ.get('CAY_TELEGRAM_API', 'https://api.telegram.org').rstrip('/')
NTFY = os.environ.get('CAY_NTFY_URL', 'https://ntfy.sh').rstrip('/')
SETTINGS_FILE = 'benachrichtigungen.json'

EVENTS = ('done', 'turn', 'blocked')
REVIEWS = ('cast_review', 'image_review', 'voice_review', 'sample_review')
CHANNELS = ('telegram', 'ntfy')
BACKOFF = (30, 120, 600, 1800)      # seconds after the 1st..4th failed attempt; the 5th failure is final
STALE = 6 * 3600                    # a message older than this is not sent any more (e.g. PC was off)
SETTLE = 180                        # the autopilot normally moves on within seconds; after this it is stuck
TIMEOUT = 10.0
TELEGRAM_FILM_LIMIT = 49 * 1024 * 1024
NTFY_ATTACHMENT_LIMIT = 2 * 1024 * 1024
TELEGRAM_PHOTO_LIMIT = 10 * 1024 * 1024

TOKEN_RE = re.compile(r'\d{5,15}:[A-Za-z0-9_-]{20,80}')
TOPIC_RE = re.compile(r'cay-studio-[a-z0-9]{24}')
TOPIC_CHARS = 'abcdefghijklmnopqrstuvwxyz0123456789'

ASK = {'cast_review': 'Bitte die Figuren ansehen und freigeben.',
       'image_review': 'Bitte die Bilder auswählen und freigeben.',
       'voice_review': 'Bitte den Ton anhören und freigeben.',
       'sample_review': 'Bitte die Probe ansehen und freigeben.'}
STYLE = {'done': ('✅', 'white_check_mark', 3), 'turn': ('👉', 'point_right', 4), 'blocked': ('⚠️', 'warning', 4)}

PILOT = Autopilot()     # the same rules the worker uses (autopilot_on / autopilot_waits)


def scrub(text, *hidden):
    """Remove bot tokens and ntfy topics from any text that may be stored, shown or logged."""
    text = str(text)
    for value in hidden:
        if value: text = text.replace(str(value), '[entfernt]')
    return TOPIC_RE.sub('[Thema]', TOKEN_RE.sub('[entfernt]', text))


class _RedactLog(logging.Filter):
    """httpx logs request URLs at INFO level; the Telegram URL contains the token."""
    def filter(self, record):
        try:
            text = record.getMessage()
            clean = scrub(text)
            if clean != text: record.msg, record.args = clean, ()
        except Exception:      # a log line must never fail
            pass
        return True


for _name in ('httpx', 'httpcore'):
    logging.getLogger(_name).addFilter(_RedactLog())


def mask(token):
    return (token[:4] + '…' + token[-4:]) if token and len(token) > 12 else ('…' if token else '')


def new_topic():
    return 'cay-studio-' + ''.join(secrets.choice(TOPIC_CHARS) for _ in range(24))


def loopback(url):
    host = urlsplit(url).hostname or ''
    if host == 'localhost': return True
    try: return ipaddress.ip_address(host).is_loopback
    except ValueError: return False


def client(base, timeout=TIMEOUT, transport=None):
    # Local services (ComfyUI, Ollama) are always called with trust_env=False so that a proxy
    # setting can never intercept them. These calls go to the internet instead: if Cay's WSL needs
    # a proxy (HTTPS_PROXY) or its own CA bundle (SSL_CERT_FILE) to reach it, honouring them is the
    # only way out, and no local service is reached through this client. A loopback base URL (tests,
    # a self-hosted ntfy on this PC) keeps trust_env=False like every other local call.
    return httpx.AsyncClient(timeout=timeout, trust_env=not loopback(base), transport=transport, follow_redirects=False)


class Retry(Exception):
    def __init__(self, message, delay=None, count=True):
        super().__init__(message); self.delay = delay; self.count = count


class Permanent(Exception):
    pass


# ---------- which event is it ----------

def autopilot_handles(d):
    """True while the autopilot is expected to move the project on by itself (autopilot.autopilot_tick)."""
    if not PILOT.autopilot_on(d) or d.get('paused') or PILOT.autopilot_waits(d): return False
    state = d.get('state')
    if state in ('image_review', 'voice_review', 'sample_review'): return True
    if state == 'blocked':
        return d.get('resume_state') == 'audio_mixing' and 'SPRACHPRÜFUNG' in (d.get('error') or '')
    return False


def event_of(d, settled=False):
    """'done', 'turn' (Cay is needed), 'blocked' or None. settled=True: the autopilot had its chance."""
    if not isinstance(d, dict) or d.get('deleted'): return None
    state = d.get('state')
    if state == 'done': return 'done'
    if not settled and autopilot_handles(d): return None
    if state == 'blocked': return 'blocked'
    if state in REVIEWS and not d.get('paused'): return 'turn'
    return None


def signature(d, settled=False):
    event = event_of(d, settled)
    return (event, d.get('state')) if event else None


def _material(d):
    state = d.get('state')
    if state == 'cast_review':
        return [d.get('cast_refs') or {}, [p.get('design_round', 0) for p in (d.get('plan') or {}).get('cast', []) if isinstance(p, dict)]]
    if state == 'image_review':
        return [[[v.get('id') for v in (s.get('variants') or []) if isinstance(v, dict)] for s in ep.get('scenes', [])] for ep in d.get('episodes', [])]
    if state == 'voice_review':
        return [p.get('sha256') for p in d.get('previews', []) if isinstance(p, dict)]
    if state == 'sample_review':
        return (d.get('sample') or {}).get('key')
    return None


def transition_key(d, event):
    """Stable for one transition, new for the next one (new export, new error, new material to review)."""
    if event == 'done':
        basis = [d.get('export_generation', 0), [e.get('sha256') or e.get('file') for e in d.get('exports', []) if isinstance(e, dict)]]
    elif event == 'blocked':
        basis = [d.get('resume_state'), (d.get('error') or '')[:500], d.get('audio_revision'), d.get('export_generation', 0)]
    else:
        basis = [d.get('state'), d.get('audio_revision'), d.get('export_generation', 0), _material(d)]
    return hashlib.sha256(json.dumps(basis, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()[:20]


def _short(text, limit=200):
    text = ' '.join(str(text or '').split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


ADDRESS = 'Sir Cay'     # how the studio addresses its owner in messages (setting "Anrede")

# Lively, but honest: every message says what happened and what to do. One template per message,
# picked from the transition key, so a retry or a second channel says exactly the same thing.
DONE_FILM = (('🎬 {name}, dein Film ist fertig!', '„{title}“ · {seconds} Sekunden', 'Popcorn bereit? 🍿 Ansehen, herunterladen, hochladen.'),
             ('✨ Applaus, {name}!', '„{title}“ ist im Kasten: {seconds} Sekunden.', 'Bereit für TikTok. 🚀'),
             ('🏆 Mission erfüllt, {name}!', '„{title}“ wartet auf seinen großen Auftritt ({seconds} s).', 'Viel Erfolg beim Hochladen! 🎉'))
DONE_SERIES = (('📺 {name}, deine Serie ist komplett!', '„{title}“: {episodes} Folgen sind fertig.', 'Folge für Folge bereit zum Hochladen. 🎉'),
               ('🍿 Staffel im Kasten, {name}!', '„{title}“ · {episodes} Folgen.', 'Zeit für die Premiere. 🚀'))
TURN = {'cast_review': ('👀 {name}, deine Besetzung wartet.', '„{title}“: Bitte die Figuren ansehen und freigeben.'),
        'image_review': ('🖼️ {name}, die Szenenbilder sind da.', '„{title}“: Pro Szene ein Bild wählen, dann geht es weiter.'),
        'voice_review': ('🎧 Ohren auf, {name}!', '„{title}“: Der Ton wartet auf deine Freigabe.'),
        'sample_review': ('🎞️ {name}, eine kurze Probe wartet.', '„{title}“: Passen Mund, Stimme und Figur?')}
BLOCKED = ('⚠️ {name}, „{title}“ hat angehalten.', 'Im Studio steht der passende Knopf, meist „Fortsetzen“.')


def _pick(options, key):
    return options[int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % len(options)]


def compose(d, event, settled=False, name=ADDRESS):
    """German message: head (first line, with its emoji) and body lines, addressed to `name`."""
    name = _short(name or ADDRESS, 40)
    title = _short(d.get('title') or 'Ohne Titel', 90)
    films = [e for e in d.get('exports', []) if isinstance(e, dict) and e.get('file')]
    key = transition_key(d, event)
    if event == 'done':
        episodes = max(len(films), int((d.get('idea') or {}).get('episodes') or 1))
        seconds = round(float(films[0].get('seconds') or 0)) if films else 0
        template = _pick(DONE_SERIES, key) if episodes > 1 else _pick(DONE_FILM, key)
        head, *lines = [t.format(name=name, title=title, seconds=seconds, episodes=episodes) for t in template]
        if episodes == 1 and not seconds: lines[0] = f'„{title}“ ist fertig.'
    elif event == 'turn':
        head, line = (t.format(name=name, title=title) for t in TURN.get(d.get('state'), ('👉 {name}, das Studio wartet auf dich.', '„{title}“')))
        lines = [line]
        stop = d.get('autopilot_stopped')
        if PILOT.autopilot_on(d) and PILOT.autopilot_waits(d) and isinstance(stop, dict) and stop.get('reason'):
            lines.append(_short('Der Autopilot wartet: ' + str(stop['reason']), 200))
        elif settled:
            lines.append('Der Autopilot kommt hier nicht allein weiter.')
    else:
        head, hint = (t.format(name=name, title=title) for t in BLOCKED)
        lines = [_short(d.get('error') or 'Unbekannter Fehler.', 200), hint]
    return {'run_id': d.get('id'), 'event': event, 'state': d.get('state'), 'head': head, 'lines': lines,
            'films': [{'file': e['file'], 'seconds': e.get('seconds'), 'episode': e.get('episode', i),
                       **({'cover': e['cover']['file']} if isinstance(e.get('cover'), dict) and e['cover'].get('file') else {})}
                      for i, e in enumerate(films)] if event == 'done' else []}


# ---------- request bodies ----------

class NotifyOptions(Strict):
    address: str | None = Field(default=None, max_length=40)
    done: bool | None = None
    turn: bool | None = None
    blocked: bool | None = None
    link: bool | None = None
    telegram_preview: bool | None = None
    telegram_film: bool | None = None
    ntfy_preview: bool | None = None


class TelegramToken(Strict):
    token: str = Field(min_length=1, max_length=400)
    consent: bool = False


class Consent(Strict):
    consent: bool = False


class NotifyTest(Strict):
    channel: Literal['telegram', 'ntfy']


class Notifier:
    def __init__(self, g):
        self.g = g
        self.lock = threading.Lock()
        self.transport = None           # tests inject an httpx transport here
        self.last_sweep = 0.0
        self.last_telegram = 0.0

    # ---------- storage ----------
    def init(self):
        with self.g['conn']() as db:
            db.executescript('''
CREATE TABLE IF NOT EXISTS notify_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,key TEXT UNIQUE NOT NULL,run_id TEXT NOT NULL,event TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notify_outbox(id INTEGER PRIMARY KEY AUTOINCREMENT,dedupe TEXT UNIQUE NOT NULL,channel TEXT NOT NULL,run_id TEXT,event TEXT NOT NULL,status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,next_try REAL NOT NULL,error TEXT,payload TEXT NOT NULL,created REAL NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notify_status(channel TEXT PRIMARY KEY,ok INTEGER NOT NULL,at TEXT NOT NULL,detail TEXT NOT NULL);
''')
            db.execute("UPDATE notify_outbox SET status='queued' WHERE status='sending'")
            db.execute('DELETE FROM notify_events WHERE created<?', ((datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),))
            db.execute("DELETE FROM notify_outbox WHERE status IN ('sent','failed','dropped') AND created<?", (time.time() - 60 * 86400,))
        self.prune_previews()

    def settings_path(self):
        return Path(self.g['RUNTIME']) / 'config' / SETTINGS_FILE

    def load(self):
        data = {}
        path = self.settings_path()
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            if path.stat().st_mode & 0o077: os.chmod(path, 0o600)
        except FileNotFoundError: pass
        except (OSError, ValueError): data = {}     # unreadable: everything stays off, nothing crashes
        if not isinstance(data, dict): data = {}
        events = data.get('events') if isinstance(data.get('events'), dict) else {}
        data['events'] = {e: bool(events.get(e, True)) for e in EVENTS}
        data['link'] = bool(data.get('link', True))
        data['address'] = _short(data.get('address') or ADDRESS, 40)
        for channel in CHANNELS:
            if not isinstance(data.get(channel), dict): data[channel] = {}
        return data

    def store(self, data):
        target = self.settings_path(); target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + '.' + secrets.token_hex(6) + '.partial')
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=1); stream.flush(); os.fsync(stream.fileno())
            os.chmod(temp, 0o600); os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

    def change(self, update):
        with self.lock:
            data = self.load(); update(data); self.store(data); return data

    def hidden(self, data=None):
        data = data or self.load()
        return [data['telegram'].get('token'), data['ntfy'].get('topic')]

    def enabled(self, data):
        return {'telegram': bool(data['telegram'].get('token') and data['telegram'].get('chat')),
                'ntfy': bool(data['ntfy'].get('topic'))}

    def note(self, channel, ok, detail):
        self.g['execute']('INSERT INTO notify_status(channel,ok,at,detail) VALUES(?,?,?,?) ON CONFLICT(channel) DO UPDATE SET ok=excluded.ok,at=excluded.at,detail=excluded.detail',
                          (channel, int(bool(ok)), self.g['now'](), scrub(detail, *self.hidden())[:300]))

    def trouble(self, error):
        try: self.g['record']('notify_error', scrub(f'{type(error).__name__}: {error}', *self.hidden())[:400])
        except Exception: pass

    # ---------- hook in Factory.save ----------
    def before(self, d):
        """Called before the write. Returns the new signature if it differs from the stored one."""
        try:
            new = signature(d)
            if not new: return None
            found = self.g['rows']('SELECT document FROM factory_runs WHERE id=?', (d['id'],))
            # The stored trash/pause flags are ignored: restoring or resuming a project is Cay's own
            # click at the PC and must not announce the state it was already in.
            old = signature({**json.loads(found[0]['document']), 'deleted': False, 'paused': False}) if found else None
            return None if old == new else new
        except Exception as error:
            self.trouble(error); return None

    def after(self, pending, d):
        """Called after the write succeeded."""
        if not pending: return
        try: self.record(d, pending[0])
        except Exception as error: self.trouble(error)

    def record(self, d, event, settled=False):
        key = f"{d['id']}:{event}:{transition_key(d, event)}"
        payload = compose(d, event, settled, self.load()['address'])
        if event == 'done':
            # Measured compute time, if the studio knows it (the clock on the project tile).
            try:
                seconds = (self.g['factory'].clocks(d['id']).get(d['id']) or {}).get('seconds') if self.g.get('factory') else None
                if seconds:
                    h, m = divmod(round(seconds / 60), 60)
                    payload['lines'].insert(1, f'⏱ Rechenzeit: {h} h {m:02} min' if h else f'⏱ Rechenzeit: {m} min')
            except Exception as error: self.trouble(error)
        created = self.g['now']()
        with self.g['conn']() as db:
            fresh = db.execute('INSERT OR IGNORE INTO notify_events(key,run_id,event,payload,created) VALUES(?,?,?,?,?)',
                               (key, d['id'], event, json.dumps(payload, ensure_ascii=False), created)).rowcount
            if not fresh: return False
            data = self.load()
            if not data['events'].get(event): return True
            for channel, on in self.enabled(data).items():
                if on:
                    db.execute("INSERT OR IGNORE INTO notify_outbox(dedupe,channel,run_id,event,status,attempts,next_try,payload,created,updated) VALUES(?,?,?,?,'queued',0,?,?,?,?)",
                               (channel + ':' + key, channel, d['id'], event, time.time(), json.dumps(payload, ensure_ascii=False), time.time(), created))
        return True

    def sweep(self):
        """A project the autopilot should have moved on but did not (for SETTLE seconds): Cay is needed."""
        factory = self.g.get('factory')
        if not factory: return
        now = datetime.now(timezone.utc)
        rows = self.g['rows']("SELECT id FROM factory_runs WHERE state IN ('image_review','voice_review','sample_review','blocked') AND updated<? AND updated>?",
                              ((now - timedelta(seconds=SETTLE)).isoformat(), (now - timedelta(hours=24)).isoformat()))
        for row in rows:
            try:
                d = factory.get(row['id'])
                if autopilot_handles(d): self.record(d, event_of(d, settled=True), settled=True)
            except Exception as error:
                self.trouble(error)

    # ---------- sending ----------
    async def worker(self):
        while not self.g['STOPPING']:
            try:
                if time.monotonic() - self.last_sweep > 60:
                    self.last_sweep = time.monotonic(); await asyncio.to_thread(self.sweep)
                await self.send_due()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.trouble(error)
            await asyncio.sleep(2)

    async def send_due(self):
        rows = self.g['rows']("SELECT * FROM notify_outbox WHERE status='queued' AND next_try<=? ORDER BY id LIMIT 10", (time.time(),))
        for row in rows:
            if self.g['STOPPING']: return
            await self.process(row)

    async def process(self, row):
        data = self.load()
        if not self.enabled(data).get(row['channel']):
            self.finish(row, 'dropped', 'Kanal wurde getrennt.'); return
        if time.time() - row['created'] > STALE:
            self.finish(row, 'failed', 'Nicht gesendet: älter als 6 Stunden.')
            self.note(row['channel'], False, 'Eine ältere Nachricht wurde nicht mehr gesendet (das Studio war zu lange ohne Verbindung).'); return
        attempts = row['attempts'] + 1
        self.g['execute']("UPDATE notify_outbox SET status='sending',attempts=?,updated=? WHERE id=?", (attempts, self.g['now'](), row['id']))
        payload = json.loads(row['payload'])
        try:
            if row['channel'] == 'telegram': await self.deliver_telegram(data, payload)
            else: await self.deliver_ntfy(data, payload)
        except Retry as error:
            if not error.count: attempts -= 1
            message = scrub(error, *self.hidden(data))
            if attempts > len(BACKOFF):
                self.finish(row, 'failed', message, attempts); self.note(row['channel'], False, message)
            else:
                delay = error.delay if error.delay is not None else BACKOFF[attempts - 1]
                self.g['execute']("UPDATE notify_outbox SET status='queued',attempts=?,next_try=?,error=?,payload=?,updated=? WHERE id=?",
                                  (attempts, time.time() + max(1, delay), message, json.dumps(payload, ensure_ascii=False), self.g['now'](), row['id']))
                self.note(row['channel'], False, message + ' Neuer Versuch folgt.')
            return
        except (Permanent, Exception) as error:
            message = scrub(error, *self.hidden(data)) if isinstance(error, Permanent) else 'Interner Fehler beim Senden: ' + scrub(type(error).__name__)
            if not isinstance(error, Permanent): self.trouble(error)
            self.finish(row, 'failed', message, attempts, payload); self.note(row['channel'], False, message)
            return
        self.finish(row, 'sent', None, attempts, payload)
        self.note(row['channel'], True, 'Gesendet: ' + payload['head'])

    def finish(self, row, status, error, attempts=None, payload=None):
        self.g['execute']('UPDATE notify_outbox SET status=?,error=?,attempts=COALESCE(?,attempts),payload=COALESCE(?,payload),updated=? WHERE id=?',
                          (status, error, attempts, json.dumps(payload, ensure_ascii=False) if payload else None, self.g['now'](), row['id']))

    def text(self, data, payload):
        lines = list(payload['lines'])
        if data['link'] and payload.get('run_id'):
            lines.append(f"Am PC öffnen: http://127.0.0.1:{self.g.get('PORT', 8787)}/#p={payload['run_id']}")
        return lines

    # ---------- preview picture ----------
    def preview_folder(self):
        return Path(self.g['RUNTIME']) / 'cache' / 'notify'

    def prune_previews(self):
        try:
            for path in self.preview_folder().glob('*.jpg'):
                if time.time() - path.stat().st_mtime > 30 * 86400: path.unlink(missing_ok=True)
        except OSError: pass

    def preview(self, payload):
        """JPG, 540 px wide: the film's title card (cover with the title) if it has one, else a frame
        about 1 s into the first film. None if there is none."""
        films = payload.get('films') or []
        if not films: return None
        try:
            film = self.g['allowed'](films[0]['file'])
            if films[0].get('cover'):
                cover = self.g['allowed'](films[0]['cover'])
                if cover.is_file(): film = cover
            if not film.is_file(): return None
            stat = film.stat()
            folder = self.preview_folder(); folder.mkdir(parents=True, exist_ok=True)
            target = folder / (hashlib.sha256(f'{film}:{stat.st_size}:{stat.st_mtime_ns}'.encode()).hexdigest()[:24] + '.jpg')
            if not target.is_file():
                ffmpeg = shutil.which('ffmpeg') or 'ffmpeg'
                for start in ('1', '0'):
                    temp = target.with_suffix('.partial.jpg')
                    result = subprocess.run([ffmpeg, '-nostdin', '-y', '-hide_banner', '-loglevel', 'error', '-ss', start, '-i', str(film),
                                             '-frames:v', '1', '-vf', 'scale=540:-2', '-q:v', '4', str(temp)], capture_output=True, timeout=30)
                    if not result.returncode and temp.is_file() and temp.stat().st_size:
                        os.replace(temp, target); break
                    temp.unlink(missing_ok=True)
            return target.read_bytes() if target.is_file() else None
        except Exception as error:
            self.trouble(error); return None

    # ---------- Telegram ----------
    async def telegram(self, http, token, method, *, json_body=None, data=None, files=None, timeout=None):
        url = f'{TELEGRAM}/bot{token}/{method}'
        try:
            response = await http.post(url, json=json_body, data=data, files=files, timeout=timeout or httpx.USE_CLIENT_DEFAULT)
        except httpx.TimeoutException:
            raise Retry('Telegram hat nicht rechtzeitig geantwortet.')
        except httpx.HTTPError:
            raise Retry('Telegram ist nicht erreichbar. Bitte die Internetverbindung prüfen.')
        try: body = response.json()
        except ValueError: body = {}
        if not isinstance(body, dict): body = {}
        if response.status_code == 200 and body.get('ok'): return body.get('result')
        code = body.get('error_code') or response.status_code
        description = str(body.get('description') or '')
        if code == 429:
            after = (body.get('parameters') or {}).get('retry_after')
            delay = int(after) + 1 if isinstance(after, (int, float)) else 30
            raise Retry(f'Telegram bremst gerade (zu viele Nachrichten), neuer Versuch in {delay} s.', delay=delay, count=False)
        if code in (401, 404):
            raise Permanent('Telegram kennt diesen Bot-Schlüssel nicht (mehr). Bitte den Schlüssel noch einmal aus der Nachricht von @BotFather kopieren und einfügen.')
        if code == 403:
            raise Permanent('Der Bot darf dir nicht schreiben. Öffne deinen Bot in Telegram und tippe auf „Start“.')
        if code == 409:
            raise Permanent('Für diesen Bot ist bei Telegram ein Webhook eingerichtet. Bitte einen eigenen, neuen Bot nur für Cay Studio anlegen.')
        if code == 413:
            raise Permanent('Die Datei ist zu groß für Telegram.')
        if code == 400 and 'chat not found' in description.lower():
            raise Permanent('Telegram findet den Chat nicht. Bitte „Verbindung prüfen“ erneut ausführen.')
        if isinstance(code, int) and code >= 500:
            raise Retry('Telegram meldet eine Störung.')
        raise Permanent('Telegram hat die Nachricht abgelehnt: ' + _short(scrub(description, token), 160))

    async def telegram_wait(self):
        # Telegram allows about one message per second in one chat.
        wait = 1.1 - (time.monotonic() - self.last_telegram)
        if wait > 0: await asyncio.sleep(wait)
        self.last_telegram = time.monotonic()

    async def deliver_telegram(self, data, payload):
        settings = data['telegram']; token = settings['token']; chat = settings['chat']['id']
        message = '\n'.join([payload['head'], *self.text(data, payload)])
        if 'parts' not in payload:
            parts = ['message']
            if payload['event'] == 'done' and settings.get('film'):
                for index, film in enumerate(payload.get('films') or []):
                    try: size = self.g['allowed'](film['file']).stat().st_size
                    except Exception: size = None
                    if size and size <= TELEGRAM_FILM_LIMIT: parts.append(f'film:{index}')
                    elif size: payload.setdefault('too_big', []).append(round(size / 1024 ** 2))
            payload['parts'] = parts; payload['sent'] = []
        if payload.get('too_big'):
            message += '\nDer Film ist zu groß für Telegram (über 49 MB). Er liegt auf deinem PC.'
        async with client(TELEGRAM, transport=self.transport) as http:
            for part in payload['parts']:
                if part in payload['sent']: continue
                await self.telegram_wait()
                if part == 'message':
                    picture = await asyncio.to_thread(self.preview, payload) if settings.get('preview', True) and payload['event'] == 'done' else None
                    if picture and len(picture) <= TELEGRAM_PHOTO_LIMIT:
                        await self.telegram(http, token, 'sendPhoto', data={'chat_id': str(chat), 'caption': message[:1024]},
                                            files={'photo': ('vorschau.jpg', picture, 'image/jpeg')})
                    else:
                        await self.telegram(http, token, 'sendMessage', json_body={'chat_id': chat, 'text': message[:4000], 'disable_web_page_preview': True})
                else:
                    film = payload['films'][int(part.split(':')[1])]
                    path = self.g['allowed'](film['file'])
                    content = await asyncio.to_thread(path.read_bytes)
                    caption = payload['head'] if len(payload['films']) == 1 else f"{payload['head']} · Folge {int(part.split(':')[1]) + 1}"
                    # A film upload needs longer than the 10 s for a reply; connect and every single
                    # write still have to make progress within 10 s.
                    await self.telegram(http, token, 'sendVideo', timeout=httpx.Timeout(TIMEOUT, read=180.0),
                                        data={'chat_id': str(chat), 'caption': caption[:1024], 'supports_streaming': 'true',
                                              'duration': str(round(float(film.get('seconds') or 0)))},
                                        files={'video': (path.name, content, 'video/mp4')})
                payload['sent'].append(part)

    # ---------- ntfy ----------
    async def ntfy(self, topic, head, lines, tag, priority, picture=None):
        # Title and message travel as URL-encoded query parameters: headers are ASCII only, umlauts are not.
        params = {'title': head, 'tags': tag, 'priority': str(priority)}
        try:
            async with client(NTFY, transport=self.transport) as http:
                if picture:
                    params.update(message='\n'.join(lines), filename='vorschau.jpg')
                    response = await http.put(f'{NTFY}/{topic}', params=params, content=picture)
                else:
                    response = await http.post(f'{NTFY}/{topic}', params=params, content='\n'.join(lines).encode('utf-8'))
        except httpx.TimeoutException:
            raise Retry('ntfy.sh hat nicht rechtzeitig geantwortet.')
        except httpx.HTTPError:
            raise Retry('ntfy.sh ist nicht erreichbar. Bitte die Internetverbindung prüfen.')
        if response.status_code == 200: return
        if response.status_code == 429: raise Retry('ntfy.sh bremst gerade (Tageslimit oder zu viele Nachrichten).', delay=300, count=False)
        if response.status_code == 413: raise Permanent('Das Vorschaubild ist zu groß für ntfy.sh.')
        if response.status_code >= 500: raise Retry('ntfy.sh meldet eine Störung.')
        raise Permanent(f'ntfy.sh hat die Nachricht abgelehnt (Fehler {response.status_code}).')

    async def deliver_ntfy(self, data, payload):
        _, tag, priority = STYLE[payload['event']]
        picture = None
        if data['ntfy'].get('preview', True) and payload['event'] == 'done':
            picture = await asyncio.to_thread(self.preview, payload)
            if picture and len(picture) > NTFY_ATTACHMENT_LIMIT: picture = None
        await self.ntfy(data['ntfy']['topic'], payload['head'], self.text(data, payload), tag, priority, picture)

    # ---------- what the page sees (never a secret except the ntfy topic Cay must type into his app) ----------
    def public(self):
        data = self.load()
        status = {r['channel']: {'ok': bool(r['ok']), 'at': r['at'], 'text': r['detail']} for r in self.g['rows']('SELECT * FROM notify_status')}
        pending = {r['channel']: r['n'] for r in self.g['rows']("SELECT channel,COUNT(*) AS n FROM notify_outbox WHERE status IN ('queued','sending') GROUP BY channel")}
        tg, nt = data['telegram'], data['ntfy']
        bot = tg.get('bot') or {}
        telegram = {'state': 'connected' if tg.get('token') and tg.get('chat') else 'token' if tg.get('token') else 'off',
                    'token': mask(tg.get('token')), 'preview': bool(tg.get('preview', True)), 'film': bool(tg.get('film', False)),
                    'bot': {'name': bot.get('name', ''), 'username': bot.get('username', ''), 'link': f"https://t.me/{bot['username']}" if bot.get('username') else ''} if tg.get('token') else None,
                    'chat': {'name': (tg.get('chat') or {}).get('name', '')} if tg.get('chat') else None,
                    'last': status.get('telegram'), 'pending': pending.get('telegram', 0)}
        ntfy = {'state': 'on' if nt.get('topic') else 'off', 'topic': nt.get('topic', ''), 'url': f"{NTFY}/{nt['topic']}" if nt.get('topic') else '',
                'server': NTFY, 'preview': bool(nt.get('preview', True)), 'last': status.get('ntfy'), 'pending': pending.get('ntfy', 0)}
        return {'events': data['events'], 'link': data['link'], 'address': data['address'], 'pc': f"http://127.0.0.1:{self.g.get('PORT', 8787)}", 'telegram': telegram, 'ntfy': ntfy}

    def feed(self, after):
        """Events for the browser tab after cursor `after`. Without `after`: only the cursor (a newly
        opened tab does not replay what happened while no tab was open)."""
        latest = (self.g['rows']('SELECT MAX(seq) AS s FROM notify_events')[0]['s']) or 0
        if after is None: return {'latest': latest, 'events': []}
        events = self.load()['events']
        rows = self.g['rows']('SELECT * FROM notify_events WHERE seq>? ORDER BY seq LIMIT 20', (after,))
        out = []
        for row in rows:
            if not events.get(row['event']): continue
            payload = json.loads(row['payload'])
            out.append({'seq': row['seq'], 'key': row['key'], 'run_id': row['run_id'], 'event': row['event'],
                        'title': payload['head'], 'body': '\n'.join(payload['lines'])})
        return {'latest': rows[-1]['seq'] if len(rows) == 20 else latest, 'events': out}

    # ---------- setup steps ----------
    async def check_token(self, raw):
        found = TOKEN_RE.search(raw or '')
        if not found:
            raise HTTPException(400, 'Das ist kein Bot-Schlüssel. Kopiere die ganze Zeile aus der Nachricht von @BotFather (Zahlen, Doppelpunkt, Buchstaben).')
        token = found.group(0)
        try:
            async with client(TELEGRAM, transport=self.transport) as http:
                me = await self.telegram(http, token, 'getMe')
        except Retry as error:
            raise HTTPException(502, scrub(error, token))
        except Permanent as error:
            raise HTTPException(400, scrub(error, token))
        if not isinstance(me, dict) or not me.get('is_bot') or not me.get('username'):
            raise HTTPException(400, 'Telegram meldet keinen Bot zu diesem Schlüssel. Bitte den Schlüssel aus @BotFather prüfen.')
        return token, {'id': me.get('id'), 'name': _short(me.get('first_name') or me['username'], 60), 'username': str(me['username'])}

    async def find_chat(self, token):
        try:
            async with client(TELEGRAM, transport=self.transport) as http:
                updates = await self.telegram(http, token, 'getUpdates', json_body={'limit': 100, 'timeout': 0})
        except Retry as error:
            raise HTTPException(502, scrub(error, token))
        except Permanent as error:
            raise HTTPException(409, scrub(error, token))
        newest = None
        for update in updates if isinstance(updates, list) else []:
            if not isinstance(update, dict): continue
            for kind in ('message', 'my_chat_member', 'edited_message'):
                chat = (update.get(kind) or {}).get('chat') if isinstance(update.get(kind), dict) else None
                if isinstance(chat, dict) and chat.get('type') == 'private' and isinstance(chat.get('id'), int):
                    if newest is None or update.get('update_id', 0) >= newest[0]:
                        name = ' '.join(x for x in (chat.get('first_name'), chat.get('last_name')) if x) or chat.get('username') or 'Telegram'
                        newest = (update.get('update_id', 0), {'id': chat['id'], 'name': _short(name, 60)})
                    break
        return newest[1] if newest else None

    async def send_test(self, channel):
        data = self.load()
        if not self.enabled(data).get(channel):
            raise HTTPException(409, 'Dieser Kanal ist noch nicht fertig eingerichtet.')
        payload = {'run_id': None, 'event': 'done', 'head': f"🔔 Hallo {data['address']}! Cay Studio meldet sich.", 'films': [], 'parts': ['message'], 'sent': [],
                   'lines': ['So klingen die Nachrichten: wenn ein Film fertig ist, wenn du dran bist oder wenn etwas angehalten hat. 🎬']}
        try:
            if channel == 'telegram': await self.deliver_telegram(data, payload)
            else: await self.deliver_ntfy(data, payload)
        except (Retry, Permanent) as error:
            message = scrub(error, *self.hidden(data)); self.note(channel, False, message)
            raise HTTPException(502 if isinstance(error, Retry) else 409, message)
        self.note(channel, True, 'Testnachricht gesendet.')

    def disconnect(self, channel):
        def update(data): data[channel] = {}
        self.change(update)
        self.g['execute']("UPDATE notify_outbox SET status='dropped',error='Kanal wurde getrennt.',updated=? WHERE channel=? AND status IN ('queued','sending')", (self.g['now'](), channel))
        self.g['execute']('DELETE FROM notify_status WHERE channel=?', (channel,))

    # ---------- routes ----------
    def routes(self, app):
        @app.get('/api/notify')
        def notify_state():
            return self.public()

        @app.get('/api/notify/feed')
        def notify_feed(after: int | None = None):
            return self.feed(after)

        @app.put('/api/notify')
        def notify_options(body: NotifyOptions):
            values = body.model_dump(exclude_none=True)

            def update(data):
                for event in EVENTS:
                    if event in values: data['events'][event] = values[event]
                if 'link' in values: data['link'] = values['link']
                if 'address' in values: data['address'] = _short(values['address'], 40) or ADDRESS
                if 'telegram_preview' in values: data['telegram']['preview'] = values['telegram_preview']
                if 'telegram_film' in values: data['telegram']['film'] = values['telegram_film']
                if 'ntfy_preview' in values: data['ntfy']['preview'] = values['ntfy_preview']
            self.change(update)
            return self.public()

        @app.post('/api/notify/telegram/token')
        async def telegram_token(body: TelegramToken):
            if not body.consent:
                raise HTTPException(400, 'Bitte zuerst bestätigen, dass Benachrichtigungen über Telegram gehen dürfen.')
            token, bot = await self.check_token(body.token)

            def update(data):
                old = data['telegram']
                same = old.get('token') == token
                data['telegram'] = {'token': token, 'bot': bot, 'consent_at': self.g['now'](),
                                    'preview': old.get('preview', True), 'film': old.get('film', False),
                                    **({'chat': old['chat']} if same and old.get('chat') else {})}
            self.change(update)
            return self.public()

        @app.post('/api/notify/telegram/connect')
        async def telegram_connect():
            data = self.load(); token = data['telegram'].get('token')
            if not token: raise HTTPException(409, 'Bitte zuerst den Bot-Schlüssel einfügen.')
            chat = await self.find_chat(token)
            if not chat:
                raise HTTPException(409, 'Noch keine Nachricht an deinen Bot gefunden. Öffne den Bot in Telegram, tippe auf „Start“ und dann hier noch einmal auf „Verbindung prüfen“.')

            def update(data):
                if data['telegram'].get('token') == token: data['telegram']['chat'] = chat
            self.change(update)
            return self.public()

        @app.post('/api/notify/ntfy/enable')
        def ntfy_enable(body: Consent):
            if not body.consent:
                raise HTTPException(400, 'Bitte zuerst bestätigen, dass Benachrichtigungen über ntfy.sh gehen dürfen.')

            def update(data):
                if not data['ntfy'].get('topic'):
                    data['ntfy'] = {'topic': new_topic(), 'consent_at': self.g['now'](), 'preview': data['ntfy'].get('preview', True)}
            self.change(update)
            return self.public()

        @app.post('/api/notify/test')
        async def notify_test(body: NotifyTest):
            await self.send_test(body.channel)
            return self.public()

        @app.delete('/api/notify/{channel}')
        def notify_disconnect(channel: str):
            if channel not in CHANNELS: raise HTTPException(404, 'Unbekannter Kanal.')
            self.disconnect(channel)
            return self.public()
