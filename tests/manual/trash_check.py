"""The trash (0.19, B1), clicked in the real app against the real dashboard: trash button on every project card
(mouse, keyboard, touch) with a question and 'Rückgängig', the trash page, restore, delete for good, empty the trash,
and the visible delete button in a project.

Run: python tests/manual/trash_check.py <empty dir>   (screenshots in <dir>/shots)
"""
import hashlib, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report(); db = studio.db
COLOURS = ['0xffd23f', '0x3ec1d3', '0xee4266', '0x8ac926', '0x6a4c93', '0xff924c']


def picture(rid, colour):
    """A finished scene picture of the project (a real PNG and its finished step), for the card."""
    path = studio.root / '01_Projekte/Studio' / rid / '02_Bilder' / 'szene.png'; path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'gradients=s=288x512:c0={colour}:c1=0x1d1d1f:d=1', '-frames:v', '1', str(path)], check=True)
    sid = hashlib.md5(rid.encode()).hexdigest()
    db.execute('INSERT INTO factory_steps(id,run_id,step_key,status,graph,output,sha256) VALUES(?,?,?,?,?,?,?)',
               (sid, rid, 'image:0:0:0:0', 'done', '{}', str(path), hashlib.sha256(path.read_bytes()).hexdigest()))
    return sid


def project(rid, title, state, colour, films=0, paused=1):
    sid = picture(rid, colour)
    scene = {'title': 'S', 'action': 'x', 'cast': [], 'dialogues': [], 'variants': [{'id': sid, 'key': 'image:0:0:0:0'}], 'selected': sid}
    exports = []
    for i in range(films):
        film = studio.root / '03_Fertige_Videos/Studio' / rid / f'Folge_{i + 1:02}.mp4'; film.parent.mkdir(parents=True, exist_ok=True); film.write_bytes(b'mp4')
        exports.append({'file': str(film), 'sha256': 'x', 'episode': i, 'seconds': 30})
    studio.project(rid, state, {'title': title, 'episodes': [{'title': title, 'scenes': [scene]}], 'exports': exports, 'created': '2026-10-1' + rid[0]},
                   {'episodes': max(1, films)}, paused)


def doc(rid): return studio.call('/api/factory/' + rid)[1]
def opacity(page, rid): return float(page.evaluate(f"getComputedStyle(document.querySelector('.tile-trash[data-id=\"{rid}\"]')).opacity"))


try:
    ids = {name: ch * 32 for name, ch in (('butter', '1'), ('doener', '2'), ('harry', '3'), ('saeure', '4'), ('villa', '5'), ('tresor', '6'))}
    project(ids['butter'], 'Butterblitz', 'done', COLOURS[0], films=2)
    project(ids['doener'], 'Der Döner-Detektiv', 'image_review', COLOURS[1])
    project(ids['harry'], 'Harry Butter und der Stein der Speisen', 'done', COLOURS[2], films=1)
    project(ids['saeure'], 'Säure & Glanz', 'rendering', COLOURS[3], paused=0)
    project(ids['villa'], 'Villa der Früchte', 'done', COLOURS[4], films=1)
    project(ids['tresor'], 'Der Tresor', 'voice_review', COLOURS[5])
    for name in ('harry', 'villa'): studio.call(f'/api/factory/{ids[name]}/delete', {})

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}); errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(studio.url + '/#projects'); page.wait_for_selector('.tile'); page.wait_for_timeout(800)
        page.screenshot(path=str(shots / '01_projekte.png'), full_page=True)
        r.check('Projekte: Papierkorb als Knopf mit Anzahl, keine Linkzeile mehr', page.locator('.trash-link').inner_text().split() == ['Papierkorb', '2']
                and page.locator('.project-foot').count() == 0 and page.locator('.tile').count() == 4)
        r.check('Mülleimer auf der Karte: ohne Zeiger unsichtbar', opacity(page, ids['butter']) == 0)
        page.hover(f'.tile:has([data-id="{ids["butter"]}"]) .frame'); page.wait_for_timeout(300)
        page.screenshot(path=str(shots / '02_karte_hover.png'))
        box = page.locator(f'.tile-trash[data-id="{ids["butter"]}"]').bounding_box(); frame = page.locator(f'.tile:has([data-id="{ids["butter"]}"]) .frame').bounding_box()
        r.check('Mit Zeiger: Mülleimer oben rechts auf dem Bild', opacity(page, ids['butter']) == 1 and box['x'] + box['width'] <= frame['x'] + frame['width'] - 4
                and box['y'] >= frame['y'] and box['y'] < frame['y'] + 24)
        page.mouse.move(5, 5); page.focus(f'.tile:has([data-id="{ids["tresor"]}"]) .tile-link'); page.keyboard.press('Tab'); page.wait_for_timeout(250)
        r.check('Tastatur: Tab vom Projekt erreicht seinen Mülleimer, sichtbar', page.evaluate('document.activeElement.dataset.id') == ids['tresor'] and opacity(page, ids['tresor']) == 1)

        # Card: ask, trash, 'Rückgängig' - a running project goes on again.
        page.hover(f'.tile:has([data-id="{ids["saeure"]}"]) .frame'); page.click(f'.tile-trash[data-id="{ids["saeure"]}"]'); page.wait_for_selector('[data-action="trash-confirm"]')
        page.screenshot(path=str(shots / '03_frage.png'))
        r.check('Frage im Blatt mit Titel und Hinweis, dass die Arbeit anhält', '„Säure & Glanz“' in page.locator('#sheet').inner_text() and 'hält nach dem laufenden Schritt an' in page.locator('#sheet').inner_text())
        page.click('[data-action="trash-confirm"]'); page.wait_for_timeout(900)
        page.screenshot(path=str(shots / '04_rueckgaengig.png'))
        r.check('Weg aus der Liste, im Papierkorb, Rückgängig angeboten', page.locator('.tile').count() == 3 and doc(ids['saeure'])['deleted']
                and page.locator('#toast .toast-action').inner_text() == 'Rückgängig' and page.locator('.trash-link .count').inner_text() == '3')
        page.click('#toast .toast-action'); page.wait_for_timeout(1000)
        d = doc(ids['saeure'])
        r.check('Rückgängig: wieder da und läuft weiter wie vorher', not d['deleted'] and not d['paused'] and page.locator('.tile').count() == 4)
        page.hover(f'.tile:has([data-id="{ids["doener"]}"]) .frame'); page.click(f'.tile-trash[data-id="{ids["doener"]}"]'); page.wait_for_selector('[data-action="trash-confirm"]')
        page.click('[data-action="close"]'); page.wait_for_timeout(300)
        r.check('Abbrechen lässt das Projekt stehen', not doc(ids['doener'])['deleted'] and page.locator('.tile').count() == 4)

        # Project page: a visible delete button at the top.
        page.goto(studio.url + '/#p=' + ids['tresor']); page.wait_for_selector('.trash-button')
        top = page.locator('.trash-button').bounding_box()
        r.check('Im Projekt: roter Knopf „In den Papierkorb“ oben, gut sichtbar', top['y'] < 200 and top['height'] >= 30 and 'In den Papierkorb' in page.locator('.trash-button').inner_text())
        page.screenshot(path=str(shots / '05_projekt_knopf.png'))
        page.click('.trash-button'); page.click('[data-action="trash-confirm"]'); page.wait_for_selector('.trash-link'); page.wait_for_timeout(600)
        r.check('Aus dem Projekt gelöscht: zurück in „Projekte“, Rückgängig angeboten', doc(ids['tresor'])['deleted'] and page.locator('#toast .toast-action').count() == 1)

        # Trash page: cards, restore, delete for good, empty.
        page.click('.trash-link'); page.wait_for_selector('.tile.trashed'); page.wait_for_timeout(700)
        page.screenshot(path=str(shots / '06_papierkorb.png'), full_page=True)
        cards = page.locator('.tile.trashed')
        loaded = page.evaluate("[...document.querySelectorAll('.tile.trashed img')].every(i => i.complete && i.naturalWidth > 0)")
        r.check('Papierkorb: Karte mit Bild, Titel, Datum, Filmen und zwei Knöpfen', cards.count() == 3 and loaded and 'Gelöscht am' in cards.first.inner_text()
                and '1 fertiger Film' in page.locator('.tile.trashed', has_text='Villa').inner_text()
                and page.locator('.tile.trashed [data-action="trash-restore"]').count() == 3 and page.locator('[data-action="trash-empty"]').count() == 1)
        page.click(f'[data-action="trash-restore"][data-id="{ids["tresor"]}"]'); page.wait_for_timeout(900)
        d = doc(ids['tresor'])
        r.check('Wiederherstellen: wieder unter „Projekte“, pausiert bis „Fortsetzen“', not d['deleted'] and d['paused'] and cards.count() == 2)
        page.click(f'[data-action="trash-purge"][data-id="{ids["harry"]}"]'); page.wait_for_selector('#purge-films')
        page.screenshot(path=str(shots / '07_endgueltig.png'))
        r.check('Endgültig löschen fragt, Filme-Haken aus', not page.locator('#purge-films').is_checked() and 'nicht rückgängig' in page.locator('#sheet').inner_text())
        page.click('[data-action="purge-confirm"]'); page.wait_for_timeout(900)
        film = studio.root / '03_Fertige_Videos/Studio' / ids['harry'] / 'Folge_01.mp4'
        r.check('Endgültig gelöscht, der fertige Film bleibt', studio.call('/api/factory/' + ids['harry'])[0] == 404 and film.exists() and cards.count() == 1)
        page.click('[data-action="trash-empty"]'); page.wait_for_selector('[data-action="purge-confirm"]')
        r.check('Papierkorb leeren fragt mit Anzahl', '1 Projekt wird endgültig gelöscht' in page.locator('#sheet').inner_text())
        page.click('[data-action="purge-confirm"]'); page.wait_for_timeout(900)
        page.screenshot(path=str(shots / '08_leer.png'), full_page=True)
        r.check('Leer: Hinweis, Filme bleiben', 'Der Papierkorb ist leer.' in page.locator('main').inner_text()
                and (studio.root / '03_Fertige_Videos/Studio' / ids['villa'] / 'Folge_01.mp4').exists() and 'geleert' in page.locator('#toast').inner_text())
        page.emulate_media(color_scheme='dark'); page.goto(studio.url + '/#projects'); page.wait_for_selector('.tile'); page.wait_for_timeout(500)
        page.hover('.tile .frame'); page.wait_for_timeout(300); page.screenshot(path=str(shots / '09_dunkel.png'), full_page=True)
        r.check('Keine Seitenfehler (PC)', not errors)
        browser.close()

        # Phone (touch, no hover): the trash button is always there and big enough to hit.
        # Own browser: Chromium takes the touch emulation only in a browser's first context.
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        phone = browser.new_context(viewport={'width': 390, 'height': 844}, has_touch=True, is_mobile=True).new_page(); errors = []
        phone.on('pageerror', lambda e: errors.append(str(e)))
        phone.goto(studio.url + '/#projects'); phone.wait_for_selector('.tile'); phone.wait_for_timeout(700)
        size = phone.locator('.tile-trash').first.bounding_box()           # before a full-page screenshot (it resets the touch emulation)
        r.check(f'Handy: Mülleimer ohne Zeiger sichtbar und antippbar ({opacity(phone, ids["butter"])}, {size["width"]} px)', opacity(phone, ids['butter']) > .8 and size['width'] >= 32)
        phone.screenshot(path=str(shots / '10_handy.png'))
        r.check('Handy: Projekte ohne waagerechtes Scrollen', phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        phone.tap(f'.tile-trash[data-id="{ids["butter"]}"]'); phone.wait_for_selector('[data-action="trash-confirm"]')
        phone.tap('[data-action="trash-confirm"]'); phone.wait_for_timeout(900)
        phone.screenshot(path=str(shots / '11_handy_rueckgaengig.png'))
        r.check('Handy: gelöscht, Rückgängig lesbar', doc(ids['butter'])['deleted'] and phone.locator('#toast .toast-action').is_visible())
        phone.goto(studio.url + '/#trash'); phone.wait_for_selector('.tile.trashed'); phone.wait_for_timeout(500)
        phone.screenshot(path=str(shots / '12_handy_papierkorb.png'))
        r.check('Handy: Papierkorb ohne waagerechtes Scrollen', phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        r.check('Keine Seitenfehler (Handy)', not errors)
        browser.close()
finally:
    studio.close()
r.done()
