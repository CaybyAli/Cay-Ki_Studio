"""0.19 one scene image under the autopilot: the image review in the browser when the autopilot drew one.

Run: CAY_TEST_STUDIO_PORT=8933 CAY_TEST_COMFY_PORT=8333 python tests/manual/stills_check.py <empty dir>
(screenshots in <dir>/shots). Pictures are FFmpeg test images, no AI models: this checks the flow on
the real server (button only where one image is missing, the first image stays chosen), not a real still.
"""
import hashlib, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report(); db = studio.db
ids = iter(f'{i:032x}' for i in range(1, 400))


def picture(rid, name, colour):
    path = studio.root / '01_Projekte/Studio' / rid / f'02_Bilder/{name}.png'; path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=c={colour}:s=576x1024', '-frames:v', '1', str(path)], check=True)
    sid = next(ids)
    db.execute("INSERT INTO factory_steps(id,run_id,step_key,status,prompt_id,graph,output,sha256) VALUES(?,?,?,?,?,?,?,?)",
               (sid, rid, 'image:' + name, 'done', None, '{}', str(path), hashlib.sha256(path.read_bytes()).hexdigest()))
    return sid


def scene(rid, si, slots, stills):
    variants = [{'id': picture(rid, f'0:{si}:0:{k}', ('0x2c5364', '0xee4266')[k]), 'key': f'image:0:{si}:0:{k}'} for k in range(slots)]
    return {'title': f'Szene {si + 1}', 'action': 'Lena steht am Hafen.', 'cast': ['Lena'], 'camera': 'Halbnah', 'round': 0,
            'dialogues': [{'speaker': 'Lena', 'text': 'Wo ist er?', 'pause_after': .18}], 'selected': None, 'variants': variants,
            'render_seconds': 3, 'seconds': 3, **({'stills': stills} if stills else {})}


def doc(page, rid): return json.loads(page.evaluate(f"fetch('/api/factory/{rid}').then(r => r.text())"))


try:
    A, B = 'a' * 32, 'b' * 32
    cast = {'plan': {'cast': [{'name': 'Lena', 'appearance': 'x'}], 'style': 'clay', 'mood': 'playful'}}
    # Autopilot switched off after the images: scene 1 has one image (kept so), scene 2 had both drawn.
    studio.project(A, 'image_review', {**cast, 'render_policy': 19, 'episodes': [{'title': 'Hafen', 'scenes': [
        scene(A, 0, 1, {'round': 0, 'count': 1}), scene(A, 1, 2, {'round': 0, 'count': 2})]}]}, {'autopilot': False})
    # A project from before 0.19 with an old single image: no new button.
    studio.project(B, 'image_review', {**cast, 'episodes': [{'title': 'Alt', 'scenes': [scene(B, 0, 1, None)]}]}, {'autopilot': False})
    db.commit()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}); errors = []
        page.on('pageerror', lambda e: errors.append(str(e))); page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
        page.goto(studio.url + '/#p=' + A); page.wait_for_selector('.scenes .variant img')
        scenes = page.locator('.scenes .scene')
        r.check('Szene mit einem Bild: ein Bild, Knopf „Zweites Bild“', scenes.nth(0).locator('.variant').count() == 1
                and scenes.nth(0).locator('[data-action="second-still"]').inner_text() == 'Zweites Bild')
        r.check('Szene mit zwei Bildern: kein Knopf', scenes.nth(1).locator('.variant').count() == 2 and scenes.nth(1).locator('[data-action="second-still"]').count() == 0)
        page.screenshot(path=str(shots / '01_ein_bild.png'), full_page=True)
        scenes.nth(0).locator('.variant').click(); page.wait_for_timeout(700)
        first = doc(page, A)['episodes'][0]['scenes'][0]['selected']
        scenes.nth(0).locator('[data-action="second-still"]').click(); page.wait_for_timeout(1200)
        note = page.locator('#toast').inner_text()
        a = doc(page, A); s = a['episodes'][0]['scenes'][0]
        r.check('Zweites Bild angefordert: Studio zeichnet, erstes Bild bleibt gewählt',
                a['state'] == 'pictures' and s['stills'] == {'round': 0, 'count': 2} and s['selected'] == first and len(s['active_variants']) == 1)
        r.check('Hinweis nach dem Klick', note == 'Ein zweites Bild entsteht. Das erste bleibt.')
        page.screenshot(path=str(shots / '02_zweites_bild_angefordert.png'), full_page=True)
        code, again = studio.call(f'/api/factory/{A}/second-still', {'episode': 0, 'scene': 0})
        r.check('Doppelter Klick: abgelehnt mit klarem Grund', code == 409 and again.get('detail') == 'Nur während der Bildauswahl möglich.')

        page.goto(studio.url + '/#p=' + B); page.wait_for_selector('.scenes .variant img')
        r.check('Altes Projekt mit einem Bild: kein Knopf', page.locator('[data-action="second-still"]').count() == 0)
        code, refused = studio.call(f'/api/factory/{B}/second-still', {'episode': 0, 'scene': 0})
        r.check('Altes Projekt: Anfrage abgelehnt', code == 409)

        page.set_viewport_size({'width': 390, 'height': 844}); page.goto(studio.url + '/#p=' + A); page.wait_for_timeout(1200)
        page.screenshot(path=str(shots / '03_handy.png'), full_page=True)
        r.check('Handy: keine waagerechte Scrollleiste', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        r.check('Keine Fehler in der Konsole', not errors)
        if errors: print(errors)
        browser.close()
finally:
    studio.close()
r.done()
