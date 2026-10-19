"""Films from a Windows drive that answers reads with an I/O error (0.19, Cay's dashboard.log), played in the real app.

The real dashboard runs in this process (uvicorn as on Cay's PC), so the drive can fail on purpose at chosen bytes of a
film: two short bad moments, one long one at the same byte (the server ends that answer, the player asks again) and a
drive that stays silent (one quiet reload, then a note with the studio's text and 'Neu laden'). Every film must play to
the end, the log gets one German line per case and never a traceback.

Chromium here plays no H.264, so the test films are VP9 in MP4; the server only moves bytes.
Run: python tests/manual/film_stream_check.py <empty dir>   (screenshots in <dir>/shots)
"""
import errno, http.server, json, logging, os, subprocess, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import APP, BASE, COMFY_PORT, PORT, FakeComfy, Report

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
runtime, root = work / 'studio', work / 'ablage'
(runtime / 'config').mkdir(parents=True, exist_ok=True); root.mkdir(exist_ok=True)
(runtime / 'config/ablage.json').write_text(json.dumps({'wsl_root': str(root), 'windows_root': 'D:\\Cay_Studio',
    'local_services': {'comfyui': f'http://127.0.0.1:{COMFY_PORT}', 'ollama': 'http://127.0.0.1:11434'}}))
os.environ.update(CAY_STUDIO_RUNTIME=str(runtime), CAY_STUDIO_PORT=str(PORT))
comfy = http.server.ThreadingHTTPServer(('127.0.0.1', COMFY_PORT), FakeComfy)
threading.Thread(target=comfy.serve_forever, daemon=True).start()
r = Report()

# ---------- the drive: reads of a film fail at chosen bytes, as /mnt/d did ----------
import anyio
DRIVE = {}                                     # (file name, byte) -> how many more reads there fail
real_open = anyio.open_file


class Drive:
    def __init__(self, inner, name): self.inner, self.name, self.at = inner, name, 0
    async def __aenter__(self): await self.inner.__aenter__(); return self
    async def __aexit__(self, *a): return await self.inner.__aexit__(*a)
    async def seek(self, offset): self.at = offset; return await self.inner.seek(offset)
    async def read(self, size):
        for (name, byte), left in list(DRIVE.items()):
            if name == self.name and self.at <= byte < self.at + size and left > 0:
                DRIVE[name, byte] = left - 1; raise OSError(errno.EIO, 'Input/output error')
        data = await self.inner.read(size); self.at += len(data); return data


async def shaky_open(path, mode='r', *a, **kw): return Drive(await real_open(path, mode, *a, **kw), Path(str(path)).name)
anyio.open_file = shaky_open

# ---------- the real dashboard in this process ----------
sys.path.insert(0, str(APP))
import uvicorn
import server, steady_files
lines, records = [], []
for layer in server.app.user_middleware:
    if layer.cls is steady_files.SteadyFiles: layer.kwargs['log'] = lambda text: (lines.append(text), print('  Log: ' + text))


class Collect(logging.Handler):
    def emit(self, record): records.append(record)
logging.getLogger().addHandler(Collect(logging.WARNING))
uv = uvicorn.Server(uvicorn.Config(server.app, host='127.0.0.1', port=PORT, http='h11', access_log=False, log_config=None))
threading.Thread(target=uv.run, daemon=True).start()
for _ in range(200):
    if uv.started: break
    time.sleep(.05)
import sqlite3
db = sqlite3.connect(runtime / 'data/cay_studio.sqlite3')


def project(rid, title, film_name):
    film = root / '03_Fertige_Videos/Studio' / rid / film_name; film.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=360x640:r=25:d=6', '-f', 'lavfi', '-i', 'sine=f=440:d=6',
                    '-c:v', 'libvpx-vp9', '-b:v', '2M', '-deadline', 'realtime', '-cpu-used', '8', '-c:a', 'libopus', '-movflags', '+faststart', '-shortest', str(film)], check=True)
    idea = {'idea': 'Kekse', 'duration': 15, 'episodes': 1, 'quality': 'fast', 'fps': 25, 'characters': 'invent', 'lip_sync': 'audio', 'participants': [], 'examples': []}
    doc = {'id': rid, 'request_key': rid, 'title': title, 'state': 'done', 'phase': '-', 'idea': idea, 'plan': {'cast': [], 'style': 'x', 'mood': 'playful'},
           'episodes': [{'title': title, 'scenes': []}], 'lines': [], 'exports': [{'file': str(film), 'sha256': 'x', 'episode': 0, 'seconds': 6}]}
    db.execute('INSERT INTO factory_runs VALUES(?,?,?,?,?,?)', (rid, rid, 'done', json.dumps(doc), '2026-10-19', '2026-10-19'))
    db.execute('INSERT INTO factory_control VALUES(?,?)', (rid, 1)); db.commit()
    return film


def until(page, expression, wait):
    """Polls from here: the app's CSP forbids the eval behind Playwright's wait_for_function."""
    end = time.time() + wait
    while time.time() < end and not page.evaluate(expression): time.sleep(.25)
    return page.evaluate(expression)


def play(page, rid, wait=30):
    """Open the project, play its film muted at 4x; returns (ended, events of the player, ranges asked)."""
    asked = []
    page.on('request', lambda q: asked.append(q.headers.get('range', 'alles')) if '/export/' in q.url else None)
    page.goto(f'{BASE}/#p={rid}'); page.wait_for_selector('.film video')
    page.evaluate("""() => { const v = document.querySelector('.film video'); window.ev = [];
      for (const e of ['error', 'waiting', 'playing', 'ended']) v.addEventListener(e, () => window.ev.push(e));
      v.muted = true; v.playbackRate = 4; v.play().catch(() => window.ev.push('play-refused')); }""")
    return until(page, "document.querySelector('.film video').ended", wait), page.evaluate('window.ev'), asked


try:
    films = {'calm': project('a' * 32, 'Ruhiger Film', 'Ruhig.mp4'), 'short': project('b' * 32, 'Kurze Aussetzer', 'Aussetzer.mp4'),
             'long': project('c' * 32, 'Langer Aussetzer', 'Lang.mp4'), 'silent': project('d' * 32, 'Stilles Laufwerk', 'Still.mp4')}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}); errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        ended, ev, asked = play(page, 'a' * 32)
        r.check('Gesundes Laufwerk: Film läuft bis zum Ende, kein Logeintrag', ended and not lines)

        DRIVE.update({('Aussetzer.mp4', 300_000): 1, ('Aussetzer.mp4', 700_000): 1})
        ended, ev, asked = play(page, 'b' * 32)
        r.check('Zwei kurze Aussetzer: Film läuft bis zum Ende, ohne Fehler im Player', ended and 'error' not in ev)
        r.check('… eine deutsche Zeile im Log: ab dem Byte neu gelesen', len(lines) == 1 and 'neu gelesen, Wiedergabe läuft weiter' in lines[-1])

        DRIVE.update({('Lang.mp4', 300_000): 6}); before = len(lines)
        ended, ev, asked = play(page, 'c' * 32); print(f'  Player: {ev}, Anfragen: {asked}')
        r.check('Langer Aussetzer an derselben Stelle: Antwort endet, der Player fragt neu an und spielt bis zum Ende',
                ended and 'error' not in ev and len(asked) >= 3 and lines[before:] and 'diese Antwort endet' in lines[before])

        DRIVE.update({('Still.mp4', 0): 10 ** 6}); before = len(lines)
        page.goto(f'{BASE}/#p={"d" * 32}'); page.wait_for_selector('.film video')
        page.wait_for_selector('#toast.show .toast-action', timeout=15000)
        toast = page.locator('#toast').inner_text()
        page.screenshot(path=str(shots / '01_laufwerk_still.png'))
        r.check('Stilles Laufwerk: nach einem stillen zweiten Versuch eine Meldung mit dem Text des Studios und „Neu laden“',
                'Das Laufwerk mit deinen Filmen antwortet gerade nicht.' in toast and 'Neu laden' in toast)
        r.check('… im Log nur „Antwort 503 mit Hinweis“', lines[before:] == [f'Laufwerk-Lesefehler (Errno 5) bei /api/factory/{"d" * 32}/export/0: Antwort 503 mit Hinweis'])
        DRIVE.clear()
        page.click('#toast .toast-action'); until(page, "document.querySelector('.film video').readyState >= 1", 10)
        page.evaluate("() => { const v = document.querySelector('.film video'); v.muted = true; v.playbackRate = 4; return v.play(); }")
        r.check('„Neu laden“, sobald das Laufwerk wieder antwortet: Film läuft bis zum Ende', until(page, "document.querySelector('.film video').ended", 20))

        phone = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        DRIVE.update({('Still.mp4', 0): 10 ** 6})
        phone.goto(f'{BASE}/#p={"d" * 32}'); phone.wait_for_selector('#toast.show .toast-action', timeout=15000)
        box = phone.locator('#toast').bounding_box()
        phone.screenshot(path=str(shots / '02_handy_meldung.png'))
        r.check('Handy: Meldung ganz im Bild und lesbar', box and box['x'] >= 0 and box['x'] + box['width'] <= 390 and box['y'] + box['height'] <= 844)
        DRIVE.clear()
        r.check('Keine Skriptfehler in der App', not errors)
        browser.close()
finally:
    uv.should_exit = True; time.sleep(1.5); comfy.shutdown()
noisy = [x for x in records if x.exc_info or 'Exception in ASGI' in x.getMessage() or 'without completing' in x.getMessage()]
r.check('Log: kein Traceback, keine Serverfehlerzeile für die abgebrochenen Antworten', not noisy)
for x in noisy[:3]: print('  ', x.getMessage())
r.done()
