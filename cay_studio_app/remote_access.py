"""Unterwegs-Zugriff (0.18.1): the studio on Cay's phone or laptop, the work stays on his PC.

How it works
  Tailscale (free personal plan) is a private network of only Cay's own devices. On his Windows PC,
  `tailscale serve --bg <port>` publishes the studio port to those devices as
  https://<pc>.<tailnet>.ts.net and proxies to http://127.0.0.1:<port>, which WSL2 forwards to this
  server. uvicorn stays bound to 127.0.0.1. Tailscale Funnel (public internet) is never used, and a
  request that came through Funnel is refused.

  The server reaches the Windows CLI through WSL interop (tailscale.exe), reads the PC's DNS name,
  runs serve (idempotent) and stores the host in config/unterwegs.json. From then on local_guard
  accepts exactly that host (and https://<host> as Origin) besides localhost: no wildcard, no other
  port. Whether Serve passes the original Host header or rewrites it to 127.0.0.1 is not documented;
  both work, because a rewritten Host is local and the Origin is https://<host> either way.

  Switching on or off is refused unless the request really comes from the PC: a localhost Host, no
  foreign Origin and no proxy headers. So Cay cannot lock himself out from the train, and a remote
  page can neither widen nor end the access.
"""
from __future__ import annotations

import glob
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from pathlib import Path

from fastapi import HTTPException, Request

SETTINGS_FILE = 'unterwegs.json'
LOCAL_HOSTS = ('127.0.0.1', 'localhost', '[::1]')
# Headers a reverse proxy (Tailscale Serve) adds. A request carrying one did not come from the PC's own browser.
PROXY_HEADERS = ('forwarded', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto', 'x-real-ip',
                 'tailscale-user-login', 'tailscale-user-name', 'tailscale-user-profile-pic', 'tailscale-headers-info', 'tailscale-funnel-request')
FUNNEL_HEADER = 'tailscale-funnel-request'
HOST_RE = re.compile(r'^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+ts\.net$')
CANDIDATES = ('/mnt/c/Program Files/Tailscale/tailscale.exe', '/mnt/c/Program Files (x86)/Tailscale/tailscale.exe')
LINK_RE = re.compile(r'https://login\.tailscale\.com/[A-Za-z0-9/?=&._%-]+')
DOWNLOAD = 'tailscale.com/download/windows'

MISSING = f'Tailscale ist auf diesem PC nicht installiert. Lade es von {DOWNLOAD}, installiere es und melde dich an.'
NO_INTEROP = 'Das Studio kann Tailscale nicht starten, weil WSL gerade keine Windows-Programme starten darf. Starte den PC neu und versuche es noch einmal.'
NOT_RUNNING = 'Tailscale läuft auf dem PC gerade nicht. Starte die Tailscale-App (Startmenü → Tailscale) und melde dich an.'
NO_ANSWER = 'Tailscale antwortet nicht. Starte die Tailscale-App auf dem PC neu und versuche es noch einmal.'
LOGGED_OUT = 'Tailscale ist installiert, aber nicht angemeldet. Klick unten rechts in der Taskleiste auf das Tailscale-Symbol und melde dich an.'
STOPPED = 'Tailscale ist auf dem PC ausgeschaltet. Klick unten rechts in der Taskleiste auf das Tailscale-Symbol und wähle „Connect“.'
MACHINE_AUTH = 'Dein PC wartet in Tailscale noch auf Freigabe. Öffne login.tailscale.com/admin/machines und gib ihn frei.'
STARTING = 'Tailscale startet gerade. Versuch es in ein paar Sekunden noch einmal.'
NO_DNS = 'In deinem Tailscale-Netz ist MagicDNS aus, deshalb hat dein PC keine Adresse. Schalte es auf login.tailscale.com/admin/dns ein.'
NEEDS_ENABLE = 'Tailscale muss die Studio-Adresse für dein Netz einmal erlauben. Öffne den Link, bestätige dort und schalte den Unterwegs-Zugriff dann hier noch einmal ein.'
TOO_OLD = f'Deine Tailscale-Version ist zu alt für den Unterwegs-Zugriff. Installiere die aktuelle von {DOWNLOAD}.'
FUNNEL = ('Für diese Adresse ist Tailscale Funnel an. Damit wäre das Studio öffentlich im Internet, deshalb nimmt es darüber nichts an. '
          'Schalte Funnel aus: Eingabeaufforderung öffnen und „tailscale funnel reset“ eingeben.')
OTHER = 'Unter dieser Adresse zeigt Tailscale schon etwas anderes an ({proxy}). Prüfe es in einer Eingabeaufforderung mit „tailscale serve status“; „tailscale serve reset“ gibt die Adresse frei.'
SERVE_OFF = 'Die Weiterleitung in Tailscale ist aus, unterwegs kommt nichts an. Tipp am PC auf „Neu einrichten“.'
RENAMED = 'Tailscale nennt deinen PC jetzt {name}. Tipp am PC auf „Neu einrichten“, dann gilt die neue Adresse.'
PC_ONLY = ('Den Unterwegs-Zugriff schaltest du nur am PC selbst ein oder aus (dort im Browser: http://127.0.0.1:{port}). '
           'So sperrst du dich unterwegs nicht aus.')
PC_OFF = 'Ist der PC aus, ist das Studio nicht erreichbar. Die Tailscale-App zeigt, ob dein PC online ist.'
OFF_STUCK = ('Tailscale hat die Weiterleitung nicht beendet. Das Studio nimmt über die Adresse trotzdem nichts mehr an. '
             'Zum Aufräumen: Eingabeaufforderung öffnen und „tailscale serve reset“ eingeben.')
OFF_UNREACHABLE = 'Tailscale war nicht erreichbar. Das Studio nimmt über die Adresse trotzdem nichts mehr an.'


class CliError(Exception):
    def __init__(self, state, text, link=None):
        super().__init__(text); self.state = state; self.text = text; self.link = link


def split_host(value):
    """Host header -> (name, port), lower case. '[::1]:8787' keeps its brackets."""
    value = str(value or '').strip().lower()
    if value.startswith('['):
        end = value.find(']')
        if end < 0: return value, None
        rest = value[end + 1:]
        return value[:end + 1], rest[1:] if rest.startswith(':') else None
    name, _, port = value.partition(':')
    return name, port or None


def clean_host(value):
    name = str(value or '').strip().rstrip('.').lower()
    return name if HOST_RE.match(name) else None


def _join(chunks):
    return b''.join(chunks).decode('utf-8', 'replace').replace('\r\n', '\n')


def _short(text, limit=160):
    text = re.sub(r'tskey-[A-Za-z0-9_-]+', '[entfernt]', ' '.join(str(text or '').split()))
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


class Remote:
    def __init__(self, g):
        self.g = g
        self.lock = threading.Lock()
        self.failure = None          # the last failed switch-on: {'text', 'link'}, shown in the sheet
        self.data = self.load()

    # ---------- storage ----------
    def settings_path(self):
        return Path(self.g['RUNTIME']) / 'config' / SETTINGS_FILE

    def load(self):
        try: data = json.loads(self.settings_path().read_text(encoding='utf-8'))
        except (OSError, ValueError): data = {}
        if not isinstance(data, dict): data = {}
        host = clean_host(data.get('host'))
        # A damaged or hand-edited file never widens access: no valid *.ts.net name, no remote access.
        return {'enabled': bool(data.get('enabled')) and bool(host), 'host': host if data.get('enabled') else None, 'since': data.get('since')}

    def store(self, data):
        target = self.settings_path(); target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + '.' + secrets.token_hex(6) + '.partial')
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=1); stream.flush(); os.fsync(stream.fileno())
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        self.data = data

    def host(self):
        return self.data['host'] if self.data.get('enabled') and self.data.get('host') else None

    def url(self):
        host = self.host()
        return 'https://' + host if host else None

    def link(self, rid):
        """'https://<host>/#p=<id>' while remote access is on, else None."""
        base = self.url()
        return f'{base}/#p={rid}' if base and rid else None

    # ---------- the guard (server.local_guard) ----------
    def local_origins(self):
        port = self.g.get('PORT', 8787)
        return (f'http://localhost:{port}', f'http://127.0.0.1:{port}')

    def accepts_host(self, header):
        name, port = split_host(header)
        if name in LOCAL_HOSTS: return True
        host = self.host()
        return bool(host) and name == host and port in (None, '443')

    def accepts_origin(self, origin):
        if origin in self.local_origins(): return True
        host = self.host()
        return bool(host) and str(origin).lower() == 'https://' + host

    def from_pc(self, request: Request):
        """The PC's own browser: localhost Host, no proxy header, no Origin other than the local one."""
        name, _ = split_host(request.headers.get('host', ''))
        if name not in LOCAL_HOSTS: return False
        if any(h in request.headers for h in PROXY_HEADERS): return False
        origin = request.headers.get('origin')
        return not origin or origin in self.local_origins()

    def require_pc(self, request: Request):
        if not self.from_pc(request):
            raise HTTPException(403, PC_ONLY.format(port=self.g.get('PORT', 8787)))

    # ---------- Tailscale CLI on Windows (WSL interop) ----------
    def cli(self):
        override = os.environ.get('CAY_TAILSCALE')
        if override: return override if Path(override).is_file() else None
        found = shutil.which('tailscale.exe')
        if found: return found
        for candidate in (*CANDIDATES, *sorted(glob.glob('/mnt/[d-z]/Program Files/Tailscale/tailscale.exe'))):
            if Path(candidate).is_file(): return candidate
        return None

    def run(self, args, timeout=10.0, until=None):
        """(exit code, stdout, stderr). Exit code None: no end in time (or `until` matched), process stopped."""
        exe = self.cli()
        if not exe: raise CliError('missing', MISSING)
        try:
            proc = subprocess.Popen([exe, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(Path(exe).parent))
        except OSError:
            raise CliError('no_interop', NO_INTEROP)
        out, err = [], []

        def pump(stream, sink):
            for chunk in iter(lambda: stream.read1(4096), b''): sink.append(chunk)
        readers = [threading.Thread(target=pump, args=(s, b), daemon=True) for s, b in ((proc.stdout, out), (proc.stderr, err))]
        for reader in readers: reader.start()
        end = time.monotonic() + timeout
        while proc.poll() is None and time.monotonic() < end:
            if until and until(_join(out) + _join(err)): break
            time.sleep(0.05)
        code = proc.poll()
        if code is None:
            proc.kill()
            try: proc.wait(3)
            except subprocess.TimeoutExpired: pass
        for reader in readers: reader.join(2)
        return code, _join(out), _join(err)

    def probe(self):
        """What Tailscale on this PC says, in German. Never raises."""
        result = {'state': 'missing', 'text': MISSING, 'found': False, 'name': None, 'online': None, 'version': None}
        try:
            code, out, err = self.run(['status', '--json'], timeout=8)
        except CliError as error:
            return {**result, 'state': error.state, 'text': error.text, 'found': error.state != 'missing'}
        result['found'] = True
        try: data = json.loads(out)
        except ValueError: data = None
        if not isinstance(data, dict):
            return {**result, 'state': 'no_answer' if code is None else 'not_running', 'text': NO_ANSWER if code is None else NOT_RUNNING}
        me = data.get('Self') if isinstance(data.get('Self'), dict) else {}
        result.update(version=str(data.get('Version') or '').split('-')[0] or None, online=me.get('Online'))
        backend = data.get('BackendState')
        known = {'NeedsLogin': ('logged_out', LOGGED_OUT), 'NoState': ('logged_out', LOGGED_OUT), 'Stopped': ('stopped', STOPPED),
                 'NeedsMachineAuth': ('machine_auth', MACHINE_AUTH), 'Starting': ('starting', STARTING)}
        if backend in known:
            state, text = known[backend]; return {**result, 'state': state, 'text': text}
        if backend != 'Running':
            return {**result, 'state': 'unknown', 'text': f'Tailscale meldet „{_short(backend, 40)}“. Öffne die Tailscale-App auf dem PC und prüfe, ob du angemeldet bist.'}
        tailnet = data.get('CurrentTailnet') if isinstance(data.get('CurrentTailnet'), dict) else {}
        name = clean_host(me.get('DNSName'))
        if not name or tailnet.get('MagicDNSEnabled') is False:
            return {**result, 'state': 'no_dns', 'text': NO_DNS}
        return {**result, 'state': 'ready', 'text': 'Angemeldet.', 'name': name}

    def serve_state(self, host):
        """'on' (this studio), 'off', 'other' (something else on that address) or 'unknown'; plus funnel."""
        try: code, out, _ = self.run(['serve', 'status', '--json'], timeout=8)
        except CliError: return {'state': 'unknown', 'funnel': False, 'config': None}
        try: config = json.loads(out) if out.strip() else ({} if code == 0 else None)
        except ValueError: config = {} if code == 0 and 'no serve config' in out.lower() else None
        if not isinstance(config, dict): return {'state': 'unknown', 'funnel': False, 'config': None}
        web = config.get('Web') if isinstance(config.get('Web'), dict) else {}
        site = web.get(f'{host}:443') if isinstance(web.get(f'{host}:443'), dict) else {}
        handler = (site.get('Handlers') or {}).get('/') if isinstance(site.get('Handlers'), dict) else None
        proxy = str((handler or {}).get('Proxy') or '') if isinstance(handler, dict) else ''
        funnel = bool((config.get('AllowFunnel') or {}).get(f'{host}:443')) if isinstance(config.get('AllowFunnel'), dict) else False
        port = self.g.get('PORT', 8787)
        ours = re.fullmatch(rf'(https?://)?(127\.0\.0\.1|localhost):{port}/?', proxy) is not None
        return {'state': 'on' if ours else 'other' if (proxy or site) else 'off', 'funnel': funnel, 'proxy': proxy, 'config': config}

    def only_ours(self, config, host):
        """True if the serve config holds nothing but this studio (then 'serve reset' loses nothing)."""
        if not isinstance(config, dict) or config.get('AllowFunnel') or config.get('Services'): return False
        web, tcp = config.get('Web') or {}, config.get('TCP') or {}
        return set(web) == {f'{host}:443'} and set((web[f'{host}:443'] or {}).get('Handlers') or {}) == {'/'} and set(tcp) <= {'443'}

    # ---------- switching ----------
    def enable(self):
        if not self.lock.acquire(blocking=False):
            raise HTTPException(409, 'Der Unterwegs-Zugriff wird gerade eingerichtet. Einen Moment bitte.')
        try:
            self.failure = None
            ts = self.probe()
            if ts['state'] != 'ready': self.fail(ts['text'])
            host = ts['name']
            serve = self.serve_state(host)
            if serve['funnel']: self.fail(FUNNEL)
            if serve['state'] == 'other': self.fail(OTHER.format(proxy=_short(serve['proxy'] or 'eigene Einstellung', 80)))
            if serve['state'] != 'on':
                code, out, err = self.run(['serve', '--bg', str(self.g.get('PORT', 8787))], timeout=25, until=lambda text: LINK_RE.search(text) is not None)
                text = out + '\n' + err
                link = LINK_RE.search(text)
                if link: self.fail(NEEDS_ENABLE, link.group(0))
                if code is None: self.fail(NO_ANSWER)
                if code != 0:
                    if 'flag provided but not defined' in text or 'unknown flag' in text: self.fail(TOO_OLD)
                    first = next((line for line in text.split('\n') if line.strip()), '')
                    self.fail('Tailscale konnte die Adresse nicht einrichten. Tailscale meldet: „' + _short(first) + '“')
                after = self.serve_state(host)
                if after['state'] == 'off': self.fail('Tailscale hat die Weiterleitung nicht übernommen. Versuch es noch einmal oder starte die Tailscale-App neu.')
            self.store({'enabled': True, 'host': host, 'since': self.g['now'](), 'port': self.g.get('PORT', 8787)})
            self.event('Unterwegs-Zugriff eingeschaltet')
        finally:
            self.lock.release()

    def fail(self, text, link=None):
        self.failure = {'text': text, 'link': link}
        raise HTTPException(409, text)

    def disable(self):
        """Remove the host first (the guard refuses from this moment), then end the serve proxy. Returns a note or None."""
        with self.lock:
            was = self.data.get('host')
            self.failure = None
            self.store({'enabled': False, 'host': None, 'since': None})
            self.event('Unterwegs-Zugriff ausgeschaltet')
            if not was: return None
            try:
                serve = self.serve_state(was)
                if serve['state'] in ('off', 'other'): return None
                if not self.cli(): return OFF_UNREACHABLE
                self.run(['serve', '--https=443', 'off'], timeout=15)
                after = self.serve_state(was)
                if after['state'] == 'on' and self.only_ours(after['config'], was):
                    self.run(['serve', 'reset'], timeout=15); after = self.serve_state(was)
                if after['state'] == 'unknown': return OFF_UNREACHABLE
                return OFF_STUCK if after['state'] == 'on' else None
            except CliError:
                return OFF_UNREACHABLE

    def ensure(self):
        """At studio start: if remote access is on, make sure Tailscale still forwards to it (serve
        normally survives a reboot; an older Tailscale or a 'serve reset' may have removed it)."""
        host = self.host()
        if not host: return
        try:
            ts = self.probe()
            if ts['state'] != 'ready' or ts['name'] != host: return
            serve = self.serve_state(host)
            if serve['state'] == 'off' and not serve['funnel']:
                self.run(['serve', '--bg', str(self.g.get('PORT', 8787))], timeout=20, until=lambda text: LINK_RE.search(text) is not None)
        except Exception as error:      # a start must never fail because of Tailscale
            self.event('Unterwegs-Zugriff beim Start nicht geprüft: ' + type(error).__name__)

    def event(self, text):
        try: self.g['record']('remote', text)
        except Exception: pass

    # ---------- what the page sees ----------
    def telegram_ready(self):
        notifier = self.g.get('notifier')
        try: return bool(notifier and notifier.enabled(notifier.load())['telegram'])
        except Exception: return False

    def public(self, request: Request, quick=False):
        host = self.host()
        out = {'enabled': bool(host), 'host': host, 'url': self.url(), 'here': 'pc' if self.from_pc(request) else 'remote',
               'local': f"http://127.0.0.1:{self.g.get('PORT', 8787)}", 'telegram': self.telegram_ready(), 'pc_off': PC_OFF,
               'failure': self.failure}
        if quick: return out
        ts = self.probe()
        name = ts['name']
        serve = self.serve_state(host or name) if ts['state'] == 'ready' else None
        problem = None
        if host:
            if ts['state'] != 'ready': problem = ts['text']
            elif name != host: problem = RENAMED.format(name=name)
            elif serve['funnel']: problem = FUNNEL
            elif serve['state'] == 'off': problem = SERVE_OFF
            elif serve['state'] == 'other': problem = OTHER.format(proxy=_short(serve['proxy'] or 'eigene Einstellung', 80))
        checks = [{'name': 'Tailscale auf dem PC', 'ready': ts['found'] and ts['state'] not in ('no_interop',),
                   'detail': ('Gefunden' + (f' (Version {ts["version"]}).' if ts['version'] else '.')) if ts['found'] and ts['state'] != 'no_interop' else ts['text']}]
        if ts['found'] and ts['state'] != 'no_interop':
            short = name.split('.')[0] if name else ''
            checks.append({'name': 'Angemeldet', 'ready': ts['state'] == 'ready',
                           'detail': (f'Ja. Dein PC heißt in Tailscale „{short}“.' + (' Tailscale meldet gerade aber keine Verbindung: Prüfe das Internet am PC.' if ts['online'] is False else ''))
                           if ts['state'] == 'ready' else ts['text']})
        if ts['state'] == 'ready':
            reach = 'https://' + name
            if host and not problem: detail, ok = reach + ' – erreichbar für deine Geräte mit Tailscale.', True
            elif host: detail, ok = problem, False
            else: detail, ok = reach + ' – wird beim Einschalten freigegeben.', True
            checks.append({'name': 'Adresse', 'ready': ok, 'detail': detail})
        out.update(tailscale={k: ts[k] for k in ('state', 'text', 'version', 'online')}, serve=serve['state'] if serve else None,
                   problem=problem, checks=checks, name=name)
        return out

    # ---------- routes ----------
    def routes(self, app):
        @app.get('/api/remote')
        def remote_state(request: Request, quick: bool = False):
            return self.public(request, quick)

        @app.post('/api/remote/enable')
        def remote_enable(request: Request):
            self.require_pc(request)
            self.enable()
            return self.public(request)

        @app.post('/api/remote/disable')
        def remote_disable(request: Request):
            self.require_pc(request)
            note = self.disable()
            return {**self.public(request), 'note': note}

        @app.post('/api/remote/telegram')
        async def remote_telegram():
            """Only on Cay's click: the studio address as a Telegram message to his own chat."""
            url = self.url()
            if not url: raise HTTPException(409, 'Erst den Unterwegs-Zugriff am PC einschalten, dann gibt es eine Adresse zum Senden.')
            notifier = self.g['notifier']
            data = notifier.load()
            await notifier.send_now('telegram', f"🔗 {data['address']}, dein Studio für unterwegs",
                                    [url, 'Am Handy oder Laptop: Tailscale einschalten, dann den Link öffnen. Speichere ihn am besten als Lesezeichen.'],
                                    'Studio-Adresse gesendet.')
            return {'ok': True}
