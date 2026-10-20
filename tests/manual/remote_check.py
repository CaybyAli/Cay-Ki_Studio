"""Unterwegs-Zugriff end to end: real dashboard, a fake tailscale.exe (tests/tailscale_fake.py) and a
"phone" browser that opens https://cay-pc.tail1234.ts.net.

The phone's requests are intercepted in the browser and passed to the dashboard the way Tailscale
Serve does it: once with the original Host header, once rewritten to 127.0.0.1, both with
X-Forwarded-* and the https Origin. No extra port, no real Tailscale, nothing leaves this PC
(CAY_TELEGRAM_API points at a closed local port).

Checks: the sheet (steps, Tailscale missing / not signed in / one-time approval link / on, address,
copy), 1280/390 px light/dark without horizontal scroll, from the phone: create a film with own
picture, voice and music, the figure library, watch (Range request) and download a film, the switch
locked with the reason, switching off refused; the studio link in browser notifications; switching
off at the PC ends serve and the phone is refused.

Run: CAY_TEST_STUDIO_PORT=8903 CAY_TEST_COMFY_PORT=8303 python tests/manual/remote_check.py <empty dir>
"""
import hashlib, json, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urlsplit
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1]))
from harness import Studio, Report, PORT
from tailscale_fake import FakeTailscale

HOST = 'cay-pc.tail1234.ts.net'
TOKEN = '7712345678:AAHk3xQ9vYfZpL2mN8rT5wB1cD4eF6gH7iJ'
work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
exe = work / 'tailscale' / 'tailscale.exe'                                   # not there yet: "Tailscale nicht installiert"
studio = Studio(work, {'CAY_TAILSCALE': str(exe), 'CAY_TELEGRAM_API': 'http://127.0.0.1:9'}); r = Report(); db = studio.db
direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
seen = {'keep': [], 'rewrite': []}


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def media(path, kind, seconds=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == 'png':
        cmd = ['-f', 'lavfi', '-i', 'gradients=s=576x1024:c0=0x1e3c72:c1=0xfd1d1d:d=1', '-frames:v', '1']
    elif kind == 'wav':
        cmd = ['-f', 'lavfi', '-i', f'sine=frequency=220:duration={seconds}', '-ar', '24000']
    else:
        cmd = ['-f', 'lavfi', '-i', f'testsrc2=s=1080x1920:r=25:d={seconds}', '-f', 'lavfi', '-i', f'sine=frequency=330:duration={seconds}',
               '-shortest', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac']
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', *cmd, str(path)], check=True)
    return path


def serve_like_tailscale(mode):
    """Browser -> dashboard as Tailscale Serve would pass it: 'keep' the Host or 'rewrite' it to 127.0.0.1."""
    def handle(route, request):
        url = urlsplit(request.url)
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ('host', 'connection', 'accept-encoding', 'content-length')}
        if request.method not in ('GET', 'HEAD'): headers.setdefault('origin', 'https://' + HOST)      # what the browser on that page sends
        headers.update({'Host': HOST if mode == 'keep' else f'127.0.0.1:{PORT}', 'X-Forwarded-For': '100.101.102.103', 'X-Forwarded-Proto': 'https',
                        'X-Forwarded-Host': HOST, 'Tailscale-User-Login': 'cay@example.com'})
        call = urllib.request.Request(studio.url + url.path + ('?' + url.query if url.query else ''), data=request.post_data_buffer, headers=headers, method=request.method)
        try:
            with direct.open(call, timeout=60) as answer: status, body, back = answer.status, answer.read(), answer.headers
        except urllib.error.HTTPError as error: status, body, back = error.code, error.read(), error.headers
        seen[mode].append((request.method, url.path, status, headers.get('origin')))
        route.fulfill(status=status, body=body, headers={k: v for k, v in back.items() if k.lower() not in ('content-length', 'transfer-encoding', 'connection')})
    return handle


def flat(page):
    return page.evaluate("() => { const b = document.querySelector('#sheet .sheet-body'); return document.documentElement.scrollWidth <= innerWidth && (!b || b.scrollWidth <= b.clientWidth); }")


def shoot(page, name):
    size = page.viewport_size; page.set_viewport_size({'width': size['width'], 'height': 2400}); page.wait_for_timeout(250)
    page.locator('#sheet').screenshot(path=str(shots / name)); ok = flat(page); page.set_viewport_size(size); page.wait_for_timeout(150)
    return ok


def sheet(page): return page.locator('#sheet').inner_text()


def until(page, expression, seconds=20):
    """wait_for_function evaluates a string in the page, which the studio's CSP (no 'unsafe-eval') refuses."""
    end = time.time() + seconds
    while time.time() < end:
        try:
            if page.evaluate(expression): return True
        except Exception: pass
        time.sleep(.2)
    raise TimeoutError(expression)


def recheck(page):
    page.click('#sheet [data-action="remote"]'); page.wait_for_selector('#sheet [data-remote-switch]', timeout=20000); page.wait_for_timeout(150)


try:
    # A finished film to watch and download from the phone.
    film = media(studio.root / '03_Fertige_Videos' / 'Kekse_fuer_Oemer.mp4', 'mp4')
    rid = 'd' * 32
    studio.project(rid, 'finishing', {'title': 'Kekse für Ömer', 'episodes': [{'title': 'Kekse', 'scenes': []}]}, paused=0)
    db.execute("INSERT INTO factory_post(id,run_id,kind,episode,generation,spec,status,result) VALUES(?,?,?,?,?,?,?,?)",
               ('x1', rid, 'export', 0, 0, '{}', 'done', json.dumps({'file': str(film), 'sha256': sha(film), 'seconds': 3.0, 'fps': 25, 'episode': 0, 'title': 'Kekse für Ömer'}))); db.commit()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        errors = []

        def watch(page):
            page.on('pageerror', lambda e: errors.append('pageerror: ' + str(e))); page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
            page.on('dialog', lambda d: d.accept())
        pc_context = browser.new_context(viewport={'width': 1280, 'height': 900}); pc_context.grant_permissions(['clipboard-read', 'clipboard-write'])
        pc = pc_context.new_page(); watch(pc)
        pc.goto(studio.url + '/#projects'); pc.wait_for_timeout(500)
        pc.click('[data-action="settings"]'); pc.wait_for_selector('[data-action="remote"]', timeout=20000)
        r.check('Einrichtung: Abschnitt „Unterwegs-Zugriff“, Status aus', 'Unterwegs-Zugriff' in sheet(pc) and 'Aus. Damit öffnest du das Studio auch am Handy' in sheet(pc))
        pc.screenshot(path=str(shots / '01_einrichtung.png'))
        pc.click('[data-action="remote"]'); pc.wait_for_selector('#sheet [data-remote-switch]', timeout=20000)
        text = sheet(pc)
        r.check('Blatt: Schritte (PC, Handy mit demselben Konto, einschalten, Lesezeichen), Energiesparmodus, PC aus',
                all(x in text for x in ('tailscale.com/download/windows', 'demselben Konto', 'Unterwegs-Zugriff einschalten', 'Lesezeichen',
                                         'Energiesparmodus: Nie', 'Ist der PC aus, ist das Studio nicht erreichbar. Die Tailscale-App zeigt, ob dein PC online ist.')))
        r.check('Tailscale fehlt: ein Satz, was zu tun ist', 'Tailscale ist auf diesem PC nicht installiert. Lade es von tailscale.com/download/windows' in text)
        r.check('Ohne Tailscale: keine waagerechte Scrollleiste', shoot(pc, '02_tailscale_fehlt_1280.png'))

        fake = FakeTailscale(exe.parent, backend='NeedsLogin')
        recheck(pc)
        r.check('Nicht angemeldet: gefunden mit Version, Hinweis zum Anmelden', 'Gefunden (Version 1.88.2).' in sheet(pc) and 'nicht angemeldet' in sheet(pc))
        pc.click('[data-remote-switch]'); pc.wait_for_selector('#sheet .notify-error', timeout=20000)
        r.check('Einschalten ohne Anmeldung: Meldung, Schalter bleibt aus', 'nicht angemeldet' in pc.locator('#sheet .notify-error').inner_text() and not pc.is_checked('[data-remote-switch]'))
        shoot(pc, '03_nicht_angemeldet.png')

        fake.set(backend='Running', serve_mode='needs_enable')
        recheck(pc)
        r.check('Angemeldet: Adresse wird beim Einschalten freigegeben', f'https://{HOST} – wird beim Einschalten freigegeben.' in sheet(pc) and '„cay-pc“' in sheet(pc))
        started = time.time(); pc.click('[data-remote-switch]'); pc.wait_for_selector('#sheet .notify-error a', timeout=30000)
        r.check(f'Tailscale will einmal freigeben: Link zur Freigabe ({time.time() - started:.1f} s)', pc.locator('#sheet .notify-error a').get_attribute('href') == 'https://login.tailscale.com/f/serve?node=nFAKE123'
                and 'einmal erlauben' in pc.locator('#sheet .notify-error').inner_text() and not pc.is_checked('[data-remote-switch]'))
        shoot(pc, '04_freigabe_noetig.png')

        fake.set(serve_mode='ok')
        pc.click('[data-remote-switch]'); pc.wait_for_selector('#sheet .notify-topic code', timeout=30000)
        r.check('Eingeschaltet: Adresse groß, Kopieren, Chip „An“, kein Fehler', pc.locator('#sheet .notify-topic code').inner_text() == 'https://' + HOST
                and pc.locator('#sheet .chip.on').inner_text() == 'An' and pc.locator('#sheet .notify-error').count() == 0 and pc.is_checked('[data-remote-switch]'))
        r.check('Tailscale: „serve --bg“ für den Studio-Port, nie Funnel', ['serve', '--bg', str(PORT)] in fake.calls() and not any('funnel' in c for c in fake.calls()))
        pc.click('#sheet [data-action="remote-copy"]'); pc.wait_for_timeout(300)
        r.check('Kopieren: Adresse in der Zwischenablage', pc.evaluate('navigator.clipboard.readText()') == 'https://' + HOST)
        r.check('Ohne Telegram: kein Sende-Knopf, Tipp stattdessen', pc.locator('[data-action="remote-telegram"]').count() == 0 and 'Benachrichtigungen' in sheet(pc))
        results = [shoot(pc, '05_an_1280_hell.png')]
        pc.emulate_media(color_scheme='dark'); results.append(shoot(pc, '06_an_1280_dunkel.png')); pc.emulate_media(color_scheme='light')
        pc.set_viewport_size({'width': 390, 'height': 844}); pc.wait_for_timeout(300); results.append(shoot(pc, '07_an_390_hell.png'))
        pc.screenshot(path=str(shots / '07b_an_390_sichtbar.png'))
        pc.emulate_media(color_scheme='dark'); results.append(shoot(pc, '08_an_390_dunkel.png')); pc.emulate_media(color_scheme='light')
        pc.set_viewport_size({'width': 1280, 'height': 900})
        r.check('An: keine waagerechte Scrollleiste (1280/390, hell/dunkel)', all(results))

        # Telegram connected: the button appears; sending happens only on the click (here: Telegram unreachable, said in German).
        settings = studio.runtime / 'config/benachrichtigungen.json'
        settings.write_text(json.dumps({'telegram': {'token': TOKEN, 'chat': {'id': 424242, 'name': 'Cay'}, 'bot': {'id': 1, 'name': 'Bot', 'username': 'cay_bot'}}}))
        recheck(pc)
        r.check('Mit Telegram: Knopf „Adresse an Telegram senden“', pc.locator('[data-action="remote-telegram"]').inner_text() == 'Adresse an Telegram senden')
        pc.click('[data-action="remote-telegram"]'); pc.wait_for_selector('#sheet .notify-error', timeout=20000)
        r.check('Telegram nicht erreichbar: deutsche Meldung im Blatt', 'Telegram ist nicht erreichbar' in pc.locator('#sheet .notify-error').inner_text())
        settings.unlink()

        # ---------- the phone: https://cay-pc.tail1234.ts.net through "Serve", Host kept ----------
        phone_context = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        phone_context.route(f'https://{HOST}/**', serve_like_tailscale('keep'))
        phone = phone_context.new_page(); watch(phone)
        phone.goto(f'https://{HOST}/#projects'); phone.wait_for_selector('.tile, .card, .empty, .project', timeout=20000); phone.wait_for_timeout(500)
        r.check('Handy: Studio lädt über die Tailscale-Adresse (sichere Seite, Sitzung da)', phone.evaluate('isSecureContext && !!S.token') and 'Cay Studio 0.' in phone.locator('#version').inner_text())
        phone.screenshot(path=str(shots / '09_handy_projekte.png'), full_page=True)
        phone.click('[data-action="settings"]'); phone.wait_for_selector('[data-action="remote"]', timeout=20000)
        phone.click('[data-action="remote"]'); phone.wait_for_selector('#sheet [data-remote-switch]', timeout=20000)
        r.check('Handy: Schalter gesperrt mit Grund (nur am PC, Adresse des PCs)', phone.is_disabled('[data-remote-switch]') and phone.is_checked('[data-remote-switch]')
                and f'nur am PC selbst (dort im Browser: http://127.0.0.1:{PORT})' in sheet(phone))
        r.check('Handy: Blatt ohne waagerechte Scrollleiste', shoot(phone, '10_handy_unterwegs_blatt.png'))
        phone.click('#sheet [data-action="close"]')
        answer = phone.evaluate("fetch('/api/remote/disable', {method: 'POST', headers: {'X-Cay-Token': S.token}}).then(async x => [x.status, (await x.json()).detail])")
        r.check(f'Handy: Ausschalten verweigert ({answer[0]})', answer[0] == 403 and 'nur am PC selbst' in answer[1])
        answer = phone.evaluate("fetch('/api/system/maintenance', {method: 'POST', headers: {'X-Cay-Token': S.token, 'Content-Type': 'application/json'}, body: '{\"enabled\": true}'}).then(x => x.status)")
        r.check('Handy: Wartungsmodus verweigert', answer == 403)

        # New film from the phone: own picture, voice and music uploads, then start.
        png = media(work / 'figur.png', 'png'); wav = media(work / 'stimme.wav', 'wav', 4); music = media(work / 'musik.wav', 'wav', 6)
        phone.goto(f'https://{HOST}/#new'); phone.wait_for_selector('#idea')
        phone.fill('#idea', 'Ein blauer Roboter mit Schnurrbart erklärt der Katze die Spülmaschine.')
        phone.click('details.more summary'); phone.click('[data-action="add-person"]')
        phone.fill('input[data-person="0"][data-key="name"]', 'Robo')
        phone.set_input_files('input[data-upload="image"][data-index="0"]', str(png)); phone.wait_for_selector('.person img', timeout=20000)
        phone.set_input_files('input[data-upload="voice"][data-index="0"]', str(wav)); phone.wait_for_timeout(1500)
        phone.set_input_files('input[data-upload="music"]', str(music)); phone.wait_for_selector('[data-action="remove-music"]', timeout=20000)
        draft = phone.evaluate("JSON.parse(localStorage.getItem('cay-draft'))")
        r.check('Handy: Bild, Stimme und Musik hochgeladen', bool(draft['participants'][0]['image'] and draft['participants'][0]['voice'] and draft['music']))
        before = len(studio.call('/api/factory')[1]['runs'])
        phone.click('#create'); until(phone, "location.hash.startsWith('#p=')")
        r.check('Handy: Film gestartet, das Projekt öffnet sich', len(studio.call('/api/factory')[1]['runs']) == before + 1)
        phone.screenshot(path=str(shots / '11_handy_neuer_film.png'), full_page=True)

        # Figure library from the phone.
        phone.goto(f'https://{HOST}/#library'); phone.wait_for_selector('[data-action="lib-new"]', timeout=20000)
        phone.click('[data-action="lib-new"] >> nth=0'); phone.wait_for_selector('#lib-form')
        phone.fill('#lib-form [name="label"]', 'Robo Blau'); phone.fill('#lib-form [name="name"]', 'Robo')
        phone.locator('#lib-form input[data-upload="lib-image"]').set_input_files(str(png)); phone.wait_for_selector('#lib-form .lib-photo img', timeout=20000)
        phone.click('#lib-form [type="submit"]'); phone.wait_for_selector('.card >> text=Robo Blau', timeout=20000)
        r.check('Handy: Figur in der Bibliothek angelegt', any(f['label'] == 'Robo Blau' for f in studio.call('/api/library')[1]['figures']))

        # Watch and download the finished film.
        phone.goto(f'https://{HOST}/#p={rid}'); phone.wait_for_selector('video.frame', timeout=30000)
        src = phone.get_attribute('video.frame', 'src')
        part = phone.evaluate("src => fetch(src.split('#')[0], {headers: {Range: 'bytes=0-99'}}).then(async x => [x.status, x.headers.get('content-range'), (await x.arrayBuffer()).byteLength])", src)
        whole = phone.evaluate("href => fetch(href).then(async x => [x.status, x.headers.get('content-disposition'), (await x.arrayBuffer()).byteLength])",
                               phone.get_attribute('.film a[download]', 'href'))
        r.check(f'Handy: Film abspielbar (Range {part[0]} {part[1]})', part[0] == 206 and part[2] == 100 and part[1].startswith('bytes 0-99/'))
        r.check(f'Handy: Herunterladen ({whole[0]}, {whole[2]} Bytes)', whole[0] == 200 and 'attachment' in (whole[1] or '') and whole[2] == film.stat().st_size)
        phone.screenshot(path=str(shots / '12_handy_fertiger_film.png'), full_page=True)
        posts = [x for x in seen['keep'] if x[0] != 'GET']
        r.check(f'Alle Schreibzugriffe vom Handy mit Origin https://{HOST} ({len(posts)})', posts and all(x[3] == 'https://' + HOST for x in posts))

        # ---------- the same through "Serve" with a rewritten Host (127.0.0.1) ----------
        other = browser.new_context(viewport={'width': 390, 'height': 844}); other.route(f'https://{HOST}/**', serve_like_tailscale('rewrite'))
        phone2 = other.new_page(); watch(phone2)
        phone2.goto(f'https://{HOST}/#new'); phone2.wait_for_selector('#idea', timeout=30000); until(phone2, '!!S.token')
        ok = phone2.evaluate("fetch('/api/notify', {method: 'PUT', headers: {'X-Cay-Token': S.token, 'Content-Type': 'application/json'}, body: JSON.stringify({address: 'Sir Cay'})}).then(x => x.status)")
        phone2.click('details.more summary')
        phone2.set_input_files('input[data-upload="music"]', str(music)); phone2.wait_for_selector('[data-action="remove-music"]', timeout=20000)
        up = [x[2] for x in seen['rewrite'] if x[1] == '/api/factory/assets'][-1]
        off = phone2.evaluate("fetch('/api/remote/disable', {method: 'POST', headers: {'X-Cay-Token': S.token}}).then(x => x.status)")
        r.check(f'Umgeschriebener Host: Einstellungen {ok}, Musik-Upload {up}, Ausschalten {off}', ok == 200 and up == 200 and off == 403)

        # ---------- notifications carry the studio link while it is on ----------
        studio.project('e' * 32, 'audio_mixing', {'title': 'Der Keks-Krieg', 'episodes': [{'title': 'Keks', 'scenes': []}]}, paused=0)
        db.execute("INSERT INTO factory_post(id,run_id,kind,episode,generation,spec,status,error) VALUES(?,?,?,?,?,?,?,?)",
                   ('x2', 'e' * 32, 'mix', 0, 0, '{}', 'failed', 'Tonspur zu kurz')); db.commit()
        for _ in range(80):
            events = studio.call('/api/notify/feed?after=0')[1]['events']
            if any(e['run_id'] == 'e' * 32 for e in events): break
            time.sleep(.25)
        mine = [e for e in events if e['run_id'] == 'e' * 32]
        r.check(f'Meldungen im Browser: „Im Studio öffnen: https://…/#p=…“ ({len(events)})', mine and all(e['body'].endswith(f'Im Studio öffnen: https://{HOST}/#p=' + e['run_id']) and e['link'] == f'https://{HOST}/#p=' + e['run_id'] for e in events))
        code, state = studio.call('/api/notify')
        r.check('Benachrichtigungen kennen die Studio-Adresse', state['studio'] == 'https://' + HOST)

        # ---------- switch off at the PC ----------
        pc.click('#sheet [data-action="settings"]'); pc.wait_for_selector('[data-action="remote"]', timeout=20000)
        r.check('Einrichtung zeigt „An: https://…“', f'An: https://{HOST}' in sheet(pc))
        pc.click('[data-action="remote"]'); pc.wait_for_selector('#sheet [data-remote-switch]', timeout=20000)
        pc.click('[data-remote-switch]'); until(pc, "!document.querySelector('#sheet [data-remote-switch]').checked && !document.querySelector('#sheet .notify-topic')")
        r.check('Am PC ausgeschaltet: „serve --https=443 off“, Weiterleitung leer', ['serve', '--https=443', 'off'] in fake.calls() and fake.read()['serve'] == {})
        shoot(pc, '13_aus_am_pc.png')
        refused = phone.evaluate("fetch('/api/health').then(async x => [x.status, (await x.json()).detail])")
        r.check(f'Handy danach abgewiesen ({refused[0]} {refused[1]})', refused == [403, 'Nur lokaler Zugriff erlaubt.'])
        r.check('Keine JavaScript-Fehler', not [e for e in errors if 'Failed to load resource' not in e]); print('   ', errors[:4])
        browser.close()
finally:
    studio.close()
r.done()
