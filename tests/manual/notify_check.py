"""Notifications end to end: real dashboard, a tiny fake Telegram Bot API and a fake ntfy server on this PC.

The real api.telegram.org and ntfy.sh are NOT contacted: CAY_TELEGRAM_API and CAY_NTFY_URL point the
studio at the fakes. Checks: token -> getMe, connect -> chat id, test messages, a project reaching
'done' (text + photo + film), a 'blocked' one (with a 429 retry), 'Du bist dran', no repeats on later
saves, the token never in any API answer, diagnostics or log, and the sheet in the browser
(1280/390 px, light/dark, no horizontal scroll, no JS errors, browser notification on this PC).

Run: CAY_TEST_STUDIO_PORT=8814 CAY_TEST_COMFY_PORT=8214 python tests/manual/notify_check.py <empty dir>
     (fake internet port: CAY_TEST_NET_PORT, default 8914)
"""
import hashlib, http.server, io, json, os, stat, subprocess, sys, threading, time, urllib.request, zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

NET_PORT = int(os.environ.get('CAY_TEST_NET_PORT', '8914'))
NET_URL = f'http://127.0.0.1:{NET_PORT}'
TOKEN = '7712345678:AAHk3xQ9vYfZpL2mN8rT5wB1cD4eF6gH7iJ'
NET = {'updates': [], 'telegram': [], 'ntfy': [], 'fail': []}


class FakeNet(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def reply(self, code, data):
        body = json.dumps(data).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    def handle_any(self):
        url = urlsplit(self.path); raw = self.rfile.read(int(self.headers.get('Content-Length', 0) or 0))
        if url.path.startswith('/bot'):
            token, method = url.path[4:].split('/', 1)
            if token != TOKEN: return self.reply(401, {'ok': False, 'error_code': 401, 'description': 'Unauthorized'})
            NET['telegram'].append({'method': method, 'raw': raw, 'type': self.headers.get('Content-Type', '')})
            for i, (name, code, data) in enumerate(NET['fail']):
                if name == method: NET['fail'].pop(i); return self.reply(code, data)
            if method == 'getMe': return self.reply(200, {'ok': True, 'result': {'id': 7712345678, 'is_bot': True, 'first_name': 'Cay Studio Test', 'username': 'cay_studio_test_bot'}})
            if method == 'getUpdates': return self.reply(200, {'ok': True, 'result': NET['updates']})
            return self.reply(200, {'ok': True, 'result': {'message_id': len(NET['telegram'])}})
        if url.path.startswith('/ntfy/'):
            NET['ntfy'].append({'method': self.command, 'topic': url.path[6:], 'query': parse_qs(url.query), 'raw': raw, 'url': self.path})
            return self.reply(200, {'id': 'x', 'event': 'message'})
        self.reply(404, {})
    do_GET = do_POST = do_PUT = handle_any


def wait(condition, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        if condition(): return True
        time.sleep(.25)
    return False


def sent(method):
    return [m for m in NET['telegram'] if m['method'] == method]


def film(path, seconds=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'testsrc2=s=1080x1920:r=25:d={seconds}', '-f', 'lavfi', '-i', f'sine=frequency=330:duration={seconds}',
                    '-shortest', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(path)], check=True)
    return {'file': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'seconds': float(seconds), 'fps': 25}


work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
net = http.server.ThreadingHTTPServer(('127.0.0.1', NET_PORT), FakeNet); threading.Thread(target=net.serve_forever, daemon=True).start()
studio = Studio(work, {'CAY_TELEGRAM_API': NET_URL, 'CAY_NTFY_URL': NET_URL + '/ntfy'}); r = Report(); db = studio.db
answers = []


def call(path, body=None, method=None):
    code, data = studio.call(path, body, method); answers.append(json.dumps(data, ensure_ascii=False)); return code, data


def shoot(page, name, full=True):
    """Whole sheet (tall viewport) plus the facts the check needs."""
    if full:
        size = page.viewport_size; page.set_viewport_size({'width': size['width'], 'height': 2600}); page.wait_for_timeout(250)
        page.locator('#sheet').screenshot(path=str(shots / name)); page.set_viewport_size(size); page.wait_for_timeout(150)
    else:
        page.screenshot(path=str(shots / name))
    return page.evaluate("() => { const b = document.querySelector('#sheet .sheet-body'); return document.documentElement.scrollWidth <= innerWidth && b.scrollWidth <= b.clientWidth; }")


try:
    code, state = call('/api/notify')
    r.check('Anfangs alles aus, Ereignisse vorgewählt', code == 200 and state['telegram']['state'] == 'off' and state['ntfy']['state'] == 'off' and all(state['events'].values()))

    # ---------- the sheet in the browser: off state, then the Telegram wizard by hand ----------
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        # Record browser notifications instead of showing them (headless has no notification centre).
        context.add_init_script("""(() => { window.__notes = [];
          class FakeNote { constructor(title, options) { this.title = title; Object.assign(this, options || {}); window.__notes.push(this); }
            close() {} static get permission() { return localStorage.getItem('perm') || 'default'; }
            static requestPermission() { localStorage.setItem('perm', 'granted'); return Promise.resolve('granted'); } }
          window.Notification = FakeNote; })();""")
        page = context.new_page(); errors = []
        page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e))); page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
        page.on('dialog', lambda d: d.accept())
        base = studio.url + '/'
        page.goto(base + '#projects'); page.wait_for_timeout(500)
        page.click('[data-action="settings"]'); page.wait_for_selector('[data-action="notify"]', timeout=15000)
        r.check('Einrichtung: Abschnitt Benachrichtigungen mit Status „Aus“', 'Benachrichtigungen' in page.locator('#sheet').inner_text() and 'Aus.' in page.locator('#sheet').inner_text())
        page.screenshot(path=str(shots / '01_einrichtung.png'))
        page.click('[data-action="notify"]'); page.wait_for_selector('.notify-when')
        text = page.locator('#sheet').inner_text()
        r.check('Blatt: Wann, Am PC, Telegram, ntfy, WhatsApp-Satz', all(x in text for x in ('Wann', 'Am PC', 'Telegram', 'ntfy', 'WhatsApp gibt es hier nicht')))
        r.check('Hinweise vor dem Einschalten: was wohin geht, nicht Ende-zu-Ende, Schlüssel bleibt am PC',
                'Was an Telegram geht' in text and 'nicht Ende-zu-Ende verschlüsselt' in text and 'Der Bot-Schlüssel bleibt auf deinem PC' in text
                and 'Was an ntfy.sh geht' in text and 'kann mitlesen' in text and 'keine Daten den PC' in text)
        page.screenshot(path=str(shots / '02_benachrichtigungen_1280.png'))
        flat = [shoot(page, '03_aus_1280_hell.png')]
        page.emulate_media(color_scheme='dark'); page.wait_for_timeout(200); flat.append(shoot(page, '04_aus_1280_dunkel.png')); page.emulate_media(color_scheme='light')
        page.set_viewport_size({'width': 390, 'height': 844}); page.wait_for_timeout(300)
        flat.append(shoot(page, '05_aus_390_hell.png')); page.screenshot(path=str(shots / '05b_aus_390_sichtbar.png'))
        page.emulate_media(color_scheme='dark'); page.wait_for_timeout(200); flat.append(shoot(page, '06_aus_390_dunkel.png')); page.emulate_media(color_scheme='light')
        r.check('Keine waagerechte Scrollleiste (1280/390, hell/dunkel)', all(flat))
        page.set_viewport_size({'width': 1280, 'height': 900}); page.wait_for_timeout(200)

        page.focus('[data-notify="done"]'); page.keyboard.press('Tab'); page.wait_for_timeout(100)
        focus = page.evaluate("() => { const s = getComputedStyle(document.activeElement); return [document.activeElement.dataset.notify, s.outlineStyle, s.outlineWidth]; }")
        r.check('Tastatur: sichtbarer Fokus auf dem Schalter', focus[0] == 'turn' and focus[1] != 'none' and focus[2] != '0px')

        # Telegram wizard by hand
        page.fill('#tg-token', 'irgendwas'); page.click('[data-action="tg-token"]'); page.wait_for_timeout(300)
        r.check('Ohne Haken: Hinweis direkt beim Kanal', 'Einverstanden' in page.locator('section[aria-labelledby="nc-tg"] .notify-error').inner_text())
        # Wait for the server's answer itself: the box from the step before ('Einverstanden') is still there.
        page.check('#tg-consent'); page.click('[data-action="tg-token"]'); page.locator('#sheet .notify-error', has_text='kein Bot-Schlüssel').wait_for(timeout=15000)
        r.check('Falscher Schlüssel: klare Meldung, Eingabe und Haken bleiben', 'kein Bot-Schlüssel' in page.locator('#sheet .notify-error').inner_text()
                and page.input_value('#tg-token') == 'irgendwas' and page.is_checked('#tg-consent'))
        page.screenshot(path=str(shots / '07_falscher_schluessel.png'))
        page.fill('#tg-token', f'Use this token to access the HTTP API:\n{TOKEN}'); page.click('[data-action="tg-token"]')
        page.wait_for_selector('[data-action="tg-connect"]')
        r.check('Bot geprüft (getMe): Name und t.me-Link', 'Cay Studio Test' in page.locator('#sheet').inner_text() and page.locator('a[href="https://t.me/cay_studio_test_bot"]').count() == 1
                and sent('getMe'))
        page.click('[data-action="tg-connect"]'); page.locator('#sheet .notify-error', has_text='„Start“').wait_for(timeout=15000)
        r.check('Noch nicht „Start“ getippt: sagt, was zu tun ist', '„Start“' in page.locator('#sheet .notify-error').inner_text())
        page.screenshot(path=str(shots / '08_noch_kein_start.png'))
        NET['updates'] = [{'update_id': 5, 'message': {'chat': {'id': -77, 'type': 'group', 'title': 'Familie'}, 'text': 'hi'}},
                          {'update_id': 6, 'message': {'chat': {'id': 424242, 'type': 'private', 'first_name': 'Cay'}, 'text': '/start'}}]
        page.click('[data-action="tg-connect"]'); page.wait_for_selector('[data-action="notify-test"][data-channel="telegram"]')
        r.check('Verbunden mit dem privaten Chat (nicht der Gruppe)', 'Verbunden mit Cay' in page.locator('#sheet').inner_text())
        page.click('[data-action="notify-test"][data-channel="telegram"]'); page.wait_for_timeout(800)
        r.check('Testnachricht über Telegram', any('Cay Studio meldet sich'.encode() in m['raw'] and b'424242' in m['raw'] for m in sent('sendMessage')))

        # ntfy and "Am PC"
        page.click('[data-action="ntfy-on"]'); page.wait_for_timeout(300)
        r.check('ntfy ohne Haken: Hinweis', 'Einverstanden' in page.locator('#sheet .notify-error').inner_text())
        page.check('#ntfy-consent'); page.click('[data-action="ntfy-on"]'); page.wait_for_selector('.notify-topic code')
        topic = page.locator('.notify-topic code').inner_text()
        r.check('ntfy: Zufallsthema groß angezeigt mit Link', len(topic) == 35 and topic.startswith('cay-studio-') and page.locator(f'a[href="{NET_URL}/ntfy/{topic}"]').count() == 1)
        page.click('[data-action="notify-test"][data-channel="ntfy"]'); page.wait_for_timeout(800)
        r.check('Testnachricht über ntfy', NET['ntfy'] and NET['ntfy'][-1]['topic'] == topic and 'Cay Studio meldet sich' in NET['ntfy'][-1]['query']['title'][0])
        page.click('[data-action="pc-on"]'); page.wait_for_selector('[data-action="pc-test"]')
        r.check('Am PC eingeschaltet, Probe-Meldung gezeigt', page.evaluate('window.__notes.length') == 1)
        page.click('[data-notify="telegram_film"]'); page.wait_for_timeout(500)
        flat = [shoot(page, '09_verbunden_1280_hell.png')]
        page.emulate_media(color_scheme='dark'); page.wait_for_timeout(200); flat.append(shoot(page, '10_verbunden_1280_dunkel.png')); page.emulate_media(color_scheme='light')
        page.set_viewport_size({'width': 390, 'height': 844}); page.wait_for_timeout(300); flat.append(shoot(page, '11_verbunden_390_hell.png'))
        page.emulate_media(color_scheme='dark'); page.wait_for_timeout(200); flat.append(shoot(page, '12_verbunden_390_dunkel.png')); page.emulate_media(color_scheme='light')
        page.set_viewport_size({'width': 1280, 'height': 900})
        r.check('Verbunden: keine waagerechte Scrollleiste', all(flat))
        page.keyboard.press('Escape')

        code, state = call('/api/notify')
        settings_file = studio.runtime / 'config/benachrichtigungen.json'
        r.check('Zustand: Telegram verbunden, Film an, Schlüssel nur maskiert', state['telegram']['state'] == 'connected' and state['telegram']['film']
                and TOKEN not in json.dumps(state) and state['telegram']['token'] == TOKEN[:4] + '…' + TOKEN[-4:])
        r.check('Einstellungsdatei nur für den Besitzer lesbar (0600)', stat.S_IMODE(settings_file.stat().st_mode) == 0o600)

        # ---------- real transitions through the factory worker ----------
        export = film(studio.root / '03_Fertige_Videos' / 'Kekse_fuer_Oemer.mp4')
        studio.project('d' * 32, 'finishing', {'title': 'Kekse für Ömer', 'episodes': [{'title': 'Kekse', 'scenes': []}]}, paused=0)
        db.execute("INSERT INTO factory_post(id,run_id,kind,episode,generation,spec,status,result) VALUES(?,?,?,?,?,?,?,?)",
                   ('x1', 'd' * 32, 'export', 0, 0, '{}', 'done', json.dumps({**export, 'episode': 0, 'title': 'Kekse für Ömer'}))); db.commit()
        r.check('Fertig erkannt (Worker setzt „done“)', wait(lambda: studio.call('/api/factory/' + 'd' * 32)[1]['state'] == 'done'))
        r.check('Telegram: Foto mit Text, danach der Film', wait(lambda: sent('sendVideo')) and any(b'Sir Cay' in m['raw'] and 'Kekse für Ömer'.encode() in m['raw'] and b'\xff\xd8' in m['raw'] for m in sent('sendPhoto')))
        r.check('ntfy: Vorschaubild ≤ 2 MB, Umlaute als URL-Parameter', wait(lambda: any(m['method'] == 'PUT' for m in NET['ntfy'])) and any(
            m['method'] == 'PUT' and 'Sir Cay' in m['query']['title'][0] and 'Kekse für Ömer' in m['query']['message'][0] and '%C3%96' in m['url'] and m['raw'][:2] == b'\xff\xd8' and len(m['raw']) <= 2 * 1024 * 1024
            and m['query']['filename'] == ['vorschau.jpg'] and any('Am PC öffnen: http://127.0.0.1:' in x for x in m['query']['message']) for m in NET['ntfy']))
        r.check('Am PC: Meldung im offenen Studio-Tab', wait(lambda: any('Sir Cay' in n['title'] for n in page.evaluate('window.__notes.map(n => ({title: n.title}))'))))
        page.evaluate("window.__notes.find(n => n.title.includes('Sir Cay')).onclick()"); page.wait_for_timeout(300)
        r.check('Klick auf die Meldung öffnet das Projekt', page.evaluate('location.hash') == '#p=' + 'd' * 32)
        counts = (len(NET['telegram']), len(NET['ntfy']), page.evaluate('window.__notes.length'))
        for enabled in (False, True, False):
            call('/api/factory/' + 'd' * 32 + '/autopilot', {'enabled': enabled})     # three more saves of the finished project
        time.sleep(5)
        r.check('Keine Wiederholung bei weiteren Speichervorgängen', (len(NET['telegram']), len(NET['ntfy']), page.evaluate('window.__notes.length')) == counts)

        NET['fail'].append(('sendMessage', 429, {'ok': False, 'error_code': 429, 'description': 'Too Many Requests: retry after 2', 'parameters': {'retry_after': 2}}))
        studio.project('e' * 32, 'audio_mixing', {'title': 'Der Keks-Krieg', 'episodes': [{'title': 'Keks', 'scenes': []}]}, paused=0)
        db.execute("INSERT INTO factory_post(id,run_id,kind,episode,generation,spec,status,error) VALUES(?,?,?,?,?,?,?,?)",
                   ('x2', 'e' * 32, 'mix', 0, 0, '{}', 'failed', 'Tonspur zu kurz: 12,0 s statt 15,0 s')); db.commit()
        r.check('Angehalten erkannt', wait(lambda: studio.call('/api/factory/' + 'e' * 32)[1]['state'] == 'blocked'))
        blocked_tries = lambda: [m for m in sent('sendMessage') if '„Der Keks-Krieg“ hat angehalten'.encode() in m['raw'] and b'Tonspur zu kurz' in m['raw']]
        started = time.time()
        r.check('Telegram: nach 429 („retry_after“: 2 s) erneut gesendet, mit Fehlertext', wait(lambda: len(blocked_tries()) == 2, 25) and time.time() - started >= 2
                and wait(lambda: call('/api/notify')[1]['telegram']['pending'] == 0))
        r.check('ntfy: Angehalten', wait(lambda: any('hat angehalten' in (m['query'].get('title') or [''])[0] for m in NET['ntfy'])))

        studio.project('f' * 32, 'sample_review', {'title': 'Probe', 'sample': {'key': 'k1', 'file': export['file'], 'sha256': export['sha256']}}, paused=0)
        code, run = call('/api/factory/' + 'f' * 32)
        code, _ = call('/api/factory/' + 'f' * 32 + '/reject-sample', {'revision': run['revision']})
        r.check('Du bist dran: Ton wartet auf Freigabe', code == 200 and wait(lambda: any('Ohren auf, Sir Cay'.encode() in m['raw'] and 'Der Ton wartet auf deine Freigabe'.encode() in m['raw'] for m in sent('sendMessage'))))

        code, feed = call('/api/notify/feed?after=0')
        r.check('Ereignisliste für den Browser: fertig, angehalten, dran', [e['event'] for e in feed['events']] == ['done', 'blocked', 'turn'])
        code, state = call('/api/notify')
        r.check('Letztes Ergebnis je Kanal sichtbar', state['telegram']['last']['ok'] and state['ntfy']['last']['ok'] and state['telegram']['pending'] == 0)

        # ---------- the token never leaves the settings file ----------
        code, diag = call('/api/system/diagnose')
        with studio.opener.open(studio.url + '/api/factory/' + 'e' * 32 + '/diagnostics/download', timeout=30) as resp: archive = resp.read()
        report = ''.join(zipfile.ZipFile(io.BytesIO(archive)).read(n).decode() for n in zipfile.ZipFile(io.BytesIO(archive)).namelist())
        everything = '\n'.join(answers) + report + (work / 'server.log').read_text(errors='replace')
        everything += '\n'.join(json.dumps(list(x)) for x in db.execute('SELECT * FROM notify_outbox UNION ALL SELECT seq,key,run_id,event,payload,created,0,0,0,0,0,0 FROM notify_events'))
        r.check('Schlüssel nie in Antworten, Fehlerbericht, Diagnose, Datenbank oder Log', TOKEN not in everything and TOKEN.split(':')[1] not in everything)
        r.check('ntfy-Thema nicht im Fehlerbericht, in der Diagnose oder im Log', topic not in report + json.dumps(diag) + (work / 'server.log').read_text(errors='replace'))
        env = {**os.environ, 'CAY_STUDIO_RUNTIME': str(studio.runtime)}
        out = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[2] / 'Cay_Studio_Diagnose.py')], env=env, capture_output=True, text=True, timeout=120).stdout
        r.check('Cay_Studio_Diagnose: Status ja, Schlüssel und Thema nein', 'Benachrichtigungen: Telegram verbunden, ntfy an' in out and TOKEN not in out and topic not in out)

        # ---------- disconnect ----------
        code, state = call('/api/notify/telegram', method='DELETE')
        r.check('Trennen: Schlüssel gelöscht', code == 200 and state['telegram']['state'] == 'off' and TOKEN not in settings_file.read_text())
        r.check('Keine JavaScript-Fehler', not [e for e in errors if 'Failed to load resource' not in e]); print('   ', errors[:4])
        browser.close()
finally:
    studio.close(); net.shutdown()
r.done()
