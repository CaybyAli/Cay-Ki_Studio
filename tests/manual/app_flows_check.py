"""App flows from the 0.18 review, clicked in the real app against the real dashboard.

Run: python tests/manual/app_flows_check.py <empty dir>
Seeds projects with real PNG/WAV/MP4 files (FFmpeg), no AI models. Screenshots in <dir>/shots.
"""
import hashlib, json, subprocess, sys, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report(); db = studio.db


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def media(path, kind, seconds=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == 'wav':
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=frequency=220:duration={seconds}', '-ar', '24000', str(path)], check=True)
    elif kind == 'png':
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'gradients=s=576x1024:c0=0x1e3c72:c1=0x2a5298:d=1', '-frames:v', '1', str(path)], check=True)
    else:
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'gradients=s=1080x1920:c0=0x1e3c72:c1=0xfd1d1d:d={seconds}', '-f', 'lavfi', '-i', f'sine=frequency=330:duration={seconds}',
                        '-shortest', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(path)], check=True)
    return {'file': str(path), 'sha256': sha(path)}


def scene(title, cast, lines):
    return {'title': title, 'action': 'Lena hält den letzten Keks hoch, Markus verschränkt die Arme.', 'location': 'Büroküche', 'camera': 'Halbnah',
            'cast': cast, 'dialogues': [{'speaker': s, 'text': t, 'emotion': 'Natürlich', 'pause_after': .18} for s, t in lines], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'problem', 'because': 'x', 'round': 0, 'selected': None, 'render_seconds': 4.4, 'seconds': 4.4, 'variants': []}


CAST = [{'name': 'Lena', 'appearance': 'woman', 'personality': 'klug', 'voice_preset': 'young_woman'},
        {'name': 'Markus', 'appearance': 'man', 'personality': 'stur', 'voice_preset': 'man', 'voice_description': 'Tiefe, raue Stimme, spricht langsam und trocken.'}]


def project(rid, state, title, extra=None, idea=None, paused=1, episodes=None):
    studio.project(rid, state, {'title': title, 'plan': {'title': title, 'cast': CAST, 'style': 'x', 'mood': 'playful', 'episodes': [{'title': title}]},
                                'episodes': episodes or [], **(extra or {})}, {'idea': 'Zwei Kollegen streiten um den letzten Keks im Büro.', **(idea or {})}, paused)


def doc(rid): return studio.call('/api/factory/' + rid)[1]


def status(url):
    try:
        with studio.opener.open(studio.url + url, timeout=10) as answer: return answer.status
    except urllib.error.HTTPError as e: return e.code


try:
    # done film with exports (sound edit and its undo)
    done = 'd' * 32; folder = studio.root / '03_Fertige_Videos/Studio' / done
    exports = [{**media(folder / 'Folge_01.mp4', 'mp4', 3), 'episode': 0, 'seconds': 3, 'fps': 25}]
    project(done, 'done', 'Butterblitz', {'exports': exports, 'export_generation': 0, 'audio_revision': 2, 'render_segments': {'0:0:0': 'x'}},
            {'autopilot': True}, episodes=[{'title': 'Butterblitz', 'scenes': [scene('S', ['Lena'], [('Lena', 'Hallo')])]}])
    # image review: a scene with two speakers and an old single-line scene (line editor)
    lines = 'e' * 32
    old = scene('Alt', ['Lena'], []); old.update(dialogue='Alter Satz.', speaker='Lena', emotion='flüsternd')
    project(lines, 'image_review', 'Textprobe', episodes=[{'title': 'Textprobe', 'scenes': [scene('Zwei', ['Lena', 'Markus'], [('Lena', 'Hallo.')]), old]}])
    # voice review: Markus has a planned voice description ('Neue Stimme')
    voices = 'b' * 32
    project(voices, 'voice_review', 'Stimmprobe', {'mix': {'music_mode': 'off'}, 'previews': [], 'timing': [{'seconds': 15}]},
            episodes=[{'title': 'Stimmprobe', 'scenes': [scene('S', ['Markus'], [('Markus', 'Nein.')])]}])
    db.commit()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}); errors = []
        page.on('pageerror', lambda e: errors.append(str(e))); page.on('console', lambda m: m.type == 'error' and errors.append(m.text))

        # 1. "Lautstärke und Ton ändern" asks first, and "Abbrechen" brings the finished film back.
        page.goto(studio.url + '/#p=' + done); page.wait_for_selector('.film video')
        asked = []
        page.once('dialog', lambda dlg: (asked.append(dlg.message), dlg.dismiss()))
        page.click('[data-action="reopen-output"]'); page.wait_for_timeout(800)
        r.check('Ton ändern fragt zuerst; Nein lässt den Film fertig', asked and 'Downloads' in asked[0] and doc(done)['state'] == 'done' and page.locator('.film video').count() == 1)
        page.once('dialog', lambda dlg: dlg.accept())
        page.click('[data-action="reopen-output"]'); page.wait_for_selector('[data-action="cancel-sound-edit"]', timeout=10000)
        r.check('Ton ändern: Downloads weg, Abbrechen angeboten', doc(done)['state'] == 'voice_review' and status(f'/api/factory/{done}/export/0') == 404)
        page.screenshot(path=str(shots / '01_ton_bearbeiten.png'), full_page=True)
        page.click('[data-action="cancel-sound-edit"]'); page.wait_for_selector('.film video', timeout=10000)
        d = doc(done)
        r.check('Abbrechen: fertiger Film und Download wieder da, gleiche Fassung', d['state'] == 'done' and d['export_generation'] == 0 and d['exports'] == exports
                and 'sound_edit' not in d and status(f'/api/factory/{done}/export/0') == 200)

        # 2. Line editor: every row stays in place; 'Entfernen' removes exactly its own row.
        def rows(): return page.eval_on_selector_all('#lines-form [data-key="text"]', 'els => els.map(e => e.value)')
        page.goto(studio.url + '/#p=' + lines); page.wait_for_selector('[data-action="edit-lines"]')
        page.click('[data-action="edit-lines"][data-scene="0"]'); page.wait_for_selector('#lines-form')
        page.click('#lines-form [data-action="add-line"]'); page.click('#lines-form [data-action="add-line"]')
        r.check(f'Satz hinzufügen zweimal: drei Zeilen ({rows()})', rows() == ['Hallo.', '', ''])
        page.fill('#lines-form [data-line="2"][data-key="text"]', 'Dritter Satz.')
        page.click('#lines-form [data-action="drop-line"][data-index="1"]')
        r.check(f'Entfernen auf leerer Zeile: getippter Satz bleibt ({rows()})', rows() == ['Hallo.', 'Dritter Satz.'])
        page.fill('#lines-form [data-line="0"][data-key="text"]', '')
        page.click('#lines-form [data-action="add-line"]'); page.click('#lines-form [data-action="drop-line"][data-index="2"]')
        r.check(f'Geleerte Zeile bleibt beim Bearbeiten stehen ({rows()})', rows() == ['', 'Dritter Satz.'])
        page.fill('#lines-form [data-line="0"][data-key="text"]', 'Neu.')
        page.click('#lines-form button[type="submit"]'); page.wait_for_timeout(1200)
        said = doc(lines)['episodes'][0]['scenes'][0]['dialogues']
        r.check('Speichern nimmt nur Zeilen mit Text', [x['text'] for x in said] == ['Neu.', 'Dritter Satz.'])
        page.click('[data-action="edit-lines"][data-scene="1"]'); page.wait_for_selector('#lines-form')
        page.click('#lines-form [data-action="drop-line"][data-index="0"]')
        r.check(f'Alte Einzelzeile: Entfernen leert die Szene ({rows()})', rows() == [])
        page.click('#sheet [data-action="close"]')

        # 3. Limits and empty names are said in German before anything is sent.
        page.click('[data-action="edit-lines"][data-scene="0"]'); page.wait_for_selector('#lines-form')
        for _ in range(4): page.click('#lines-form [data-action="add-line"]')
        r.check('Sechs Sätze: kein weiterer Satz, Hinweis auf das Limit', len(rows()) == 6 and page.locator('#lines-form [data-action="add-line"]').count() == 0
                and 'Höchstens 6 Sätze pro Szene' in page.locator('#lines-form').inner_text())
        page.click('#sheet [data-action="close"]')
        page.goto(studio.url + '/#library'); page.wait_for_selector('[data-action="lib-new"]'); page.click('[data-action="lib-new"]')
        page.fill('#lib-form [name="label"]', '   '); page.fill('#lib-form [name="name"]', ' '); page.click('#lib-form [type="submit"]'); page.wait_for_timeout(400)
        r.check(f'Figur ohne Namen: deutsche Meldung ({page.locator("#toast").inner_text()})', page.locator('#toast').inner_text() == 'Bitte Profilname und Namen im Film ausfüllen.')
        page.click('#sheet [data-action="close"]')
        page.evaluate("fetch('/api/library', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Cay-Token': S.token}, body: JSON.stringify({name: ' ', label: 'x'})}).then(r => r.json()).then(j => window.__lib = j.detail)")
        page.wait_for_function('window.__lib !== undefined')
        r.check(f'Server: Formfehler auf Deutsch ({page.evaluate("window.__lib")})', page.evaluate('window.__lib') == 'Bitte „Name“ ausfüllen.')

        # 4. New film: a figure with a picture but no name is not dropped silently.
        png = media(work / 'figur.png', 'png')['file']
        page.goto(studio.url + '/#new'); page.wait_for_selector('#idea')
        page.fill('#idea', 'Ein blauer Roboter mit Schnurrbart erklärt der Katze die Spülmaschine.')
        page.click('details.more summary'); page.click('[data-action="add-person"]')
        page.set_input_files('input[data-upload="image"][data-index="0"]', png); page.wait_for_selector('.person img', timeout=15000)
        page.fill('input[data-person="0"][data-key="traits"]', 'Blauer Roboter mit Schnurrbart')
        before = len(studio.call('/api/factory')[1]['runs'])
        page.click('#create'); page.wait_for_timeout(800)
        r.check(f'Figur mit Bild ohne Namen: Hinweis, Fokus aufs Namensfeld, kein Film ({page.locator("#toast").inner_text()})',
                page.locator('#toast').inner_text() == 'Gib jeder Figur einen Namen oder entferne sie.' and len(studio.call('/api/factory')[1]['runs']) == before
                and page.evaluate("document.activeElement.matches('input[data-person=\"0\"][data-key=\"name\"]')"))

        # 5. Sound step 'Neue Stimme': same type keeps the planned description, another type drops it.
        def markus(): return next(x for x in doc(voices)['plan']['cast'] if x['name'] == 'Markus')
        page.goto(studio.url + '/#p=' + voices); page.wait_for_selector('[data-action="new-voice"][data-name="Markus"]')
        r.check('Ton: Knopf „Neue Stimme“ und Hinweis zum Stimmtyp', page.locator('[data-action="new-voice"][data-name="Markus"]').inner_text() == 'Neue Stimme'
                and 'Stimmtyp wählen und „Neue Stimme“ antippen' in page.locator('.section').first.inner_text())
        page.click('[data-action="new-voice"][data-name="Markus"]'); page.wait_for_timeout(1200)
        m = markus()
        r.check(f'Neue Stimme, gleicher Typ: Beschreibung bleibt ({m.get("voice_description")!r})', m['voice_preset'] == 'man' and m.get('voice_variant') == 1
                and m.get('voice_description') == 'Tiefe, raue Stimme, spricht langsam und trocken.')
        db.execute("UPDATE factory_runs SET state='voice_review', document=json_set(document,'$.state','voice_review') WHERE id=?", (voices,)); db.commit()
        page.goto(studio.url + '/#p=' + voices); page.wait_for_selector('[data-voice="Markus"]')
        page.select_option('[data-voice="Markus"]', 'grandpa'); page.click('[data-action="new-voice"][data-name="Markus"]'); page.wait_for_timeout(1200)
        m = markus()
        r.check('Neue Stimme, anderer Typ: Typ übernommen, alte Beschreibung weg', m['voice_preset'] == 'grandpa' and m.get('voice_description') == '' and m.get('voice_variant') == 2)

        # 6. New film: own music can be listened to and removed again (also after a reload).
        wav = media(work / 'musik.wav', 'wav', 4)['file']
        page.goto(studio.url + '/#new'); page.wait_for_selector('#idea'); page.click('details.more summary')
        page.set_input_files('input[data-upload="music"]', wav); page.wait_for_selector('[data-action="remove-music"]', timeout=15000)
        page.reload(); page.wait_for_selector('#idea'); page.click('details.more summary')
        r.check('Eigene Musik: nach dem Neuladen mit Anhören und Entfernen', page.locator('[data-action="remove-music"]').count() == 1
                and page.locator('[aria-label="Eigene Musik anhören"]').count() == 1)
        page.click('[data-action="remove-music"]'); page.wait_for_timeout(300)
        r.check('Musik entfernt: Entwurf ohne Musik, Hochladen wieder angeboten', page.evaluate("JSON.parse(localStorage.getItem('cay-draft')).music") is None
                and 'Eigene Musik hochladen' in page.locator('details.more').inner_text() and page.locator('details.more').get_attribute('open') is not None)

        # 7. Uploads with the keyboard: Tab reaches every file input, and its pill or tile shows the focus.
        def tab_uploads(limit=90):
            found, ring = [], []
            for _ in range(limit):
                page.keyboard.press('Tab')
                kind = page.evaluate("document.activeElement && document.activeElement.type === 'file' ? document.activeElement.dataset.upload : null")
                if kind and kind not in found:
                    found.append(kind)
                    ring.append(page.evaluate("getComputedStyle(document.activeElement.closest('label')).outlineStyle"))
            return found, ring
        page.goto(studio.url + '/#new'); page.wait_for_selector('#idea'); page.evaluate("document.querySelector('details.more').open = true"); page.wait_for_timeout(300)
        page.focus('#idea'); found, ring = tab_uploads()
        r.check(f'Tastatur: alle Uploads im neuen Film erreichbar ({found})', {'example', 'image', 'voice', 'music'} <= set(found))
        r.check(f'Tastatur: fokussierter Upload zeigt einen Rahmen ({ring})', ring and all(x == 'solid' for x in ring))
        page.screenshot(path=str(shots / '07_tastatur.png'))
        page.goto(studio.url + '/#library'); page.wait_for_selector('[data-action="lib-new"]'); page.click('[data-action="lib-new"]'); page.wait_for_selector('#lib-form')
        page.focus('#sheet [data-action="close"]'); found, ring = tab_uploads(30)
        r.check(f'Tastatur: Bild und Aufnahme einer neuen Figur erreichbar ({found})', {'lib-image', 'lib-voice'} <= set(found) and all(x == 'solid' for x in ring))
        page.click('#sheet [data-action="close"]')

        # 8. Delete a project: asks first, goes to the trash, stays findable and can be restored.
        page.goto(studio.url + '/#p=' + voices); page.wait_for_selector('[data-action="delete-project"]')
        asked = []
        page.once('dialog', lambda dlg: (asked.append(dlg.message), dlg.accept()))
        page.click('[data-action="delete-project"]'); page.wait_for_selector('.tile', timeout=10000); page.wait_for_timeout(600)
        r.check('Löschen fragt zuerst und legt das Projekt in den Papierkorb', asked and 'Papierkorb' in asked[0] and doc(voices)['deleted']
                and page.locator('.tile', has_text='Stimmprobe').count() == 0)
        page.screenshot(path=str(shots / '08_papierkorb.png'), full_page=True)
        page.click(f'.project-foot a[href="#p={voices}"]'); page.wait_for_selector('[data-action="restore"]', timeout=10000)
        r.check('Papierkorb: Projekt über „Projekte“ erreichbar, ohne Löschlink', page.locator('[data-action="delete-project"]').count() == 0)
        page.click('[data-action="restore"]'); page.wait_for_timeout(1200)
        r.check('Wiederherstellen: Projekt wieder da', not doc(voices)['deleted'])
        page.goto(studio.url + '/#p=' + lines); page.wait_for_selector('.steps')
        db.execute("UPDATE factory_control SET paused=0 WHERE id=?", (lines,)); db.execute("UPDATE factory_runs SET state='rendering', document=json_set(document,'$.state','rendering') WHERE id=?", (lines,)); db.commit()
        page.reload(); page.wait_for_selector('.steps'); page.wait_for_timeout(500)
        r.check('Während gerechnet wird, kein Löschlink', page.locator('[data-action="delete-project"]').count() == 0)
        db.execute("UPDATE factory_control SET paused=1 WHERE id=?", (lines,)); db.commit()

        # 9. 'Neue Fassung planen' asks what should change; the wish goes into the new plan.
        page.goto(studio.url + '/#p=' + done); page.wait_for_selector('[data-action="new-edition"]')
        page.click('[data-action="new-edition"]'); page.wait_for_selector('#edition-form')
        r.check('Neue Fassung: Blatt mit optionalem Wunsch, noch nichts angelegt', len(studio.call('/api/factory')[1]['runs']) == before)
        page.fill('#edition-form [name="note"]', 'Mehr Streit, die Pointe schon nach der Hälfte.'); page.click('#edition-form [type="submit"]')
        for _ in range(40):
            if '#p=' in page.url and done not in page.url: break
            page.wait_for_timeout(250)
        page.wait_for_selector('.steps')
        new = doc(page.evaluate('location.hash.slice(3)'))
        r.check(f'Neue Fassung: Wunsch im Plan, Titel mit einem Zusatz ({new["title"]})', new['idea']['idea'].endswith('Überarbeitung: Mehr Streit, die Pointe schon nach der Hälfte.')
                and new['title'] == 'Butterblitz · neue Fassung')

        r.check('Keine JavaScript-Fehler', not [e for e in errors if 'Failed to load resource' not in e]); print('   ', errors[:3])
        browser.close()
finally:
    studio.close()
r.done()
