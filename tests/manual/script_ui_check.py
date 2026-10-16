"""'Mein Drehbuch' (0.18) in the browser: the choice, paste and upload, the live check, the template,
the PDF message, figures from the script, creating the film, and the AI mode's unchanged request.

Run: CAY_TEST_STUDIO_PORT=8897 CAY_TEST_COMFY_PORT=8297 python tests/manual/script_ui_check.py <empty dir>
Screenshots in <dir>/shots (1280x900 and 390x844, light and dark). No AI models are needed: the
script is read by the server without one; planning afterwards stops at the missing planner.
"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report()

SCRIPT = (Path(__file__).resolve().parents[1] / 'test_own_script.py').read_text(encoding='utf-8').split("SCRIPT = '''", 1)[1].split("'''", 1)[0]
SHORT = 'LENA: Hallo!\nMARKUS: Hallo zurück, Lena!'
SCRIPT_RID = '5' * 32

try:
    # A script project waiting at the sound stop: no 'Dialoge ergänzen' there.
    studio.project(SCRIPT_RID, 'voice_review', {'title': 'Der Kuchenklau', 'script': {'episodes': [{'number': 1, 'seconds': 35}]},
                   'plan': {'title': 'Der Kuchenklau', 'cast': [{'name': 'Tim', 'appearance': 'boy', 'personality': 'frech', 'voice_preset': 'child_boy'}], 'style': 'x', 'mood': 'playful'},
                   'episodes': [{'title': 'Der leere Teller', 'own_script': True, 'warnings': ['Hinweis zu deinem Drehbuch: Wenig AKTION-Zeilen: 0, empfohlen sind mindestens 1. Eine stumme Handlung bringt Bewegung in den Film.'],
                                 'scenes': [{'title': 'Tim: Hallo', 'action': 'Tim spricht in Küche.', 'cast': ['Tim'], 'kind': 'line', 'variants': [], 'selected': None,
                                             'dialogues': [{'speaker': 'Tim', 'text': 'Ich war es nicht, ehrlich!', 'emotion': 'ängstlich'}]}]}],
                   'timing': [{'seconds': 20, 'speech_seconds': 12, 'longest_speech_gap': 1}]},
                   {'idea': '### Szene 1 – Küche\nTIM: Ich war es nicht, ehrlich!', 'story': 'script', 'characters': 'provided', 'duration': 15}, paused=1)
    png = work / 'mueller.png'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'gradients=s=600x900:c0=0xd03030:c1=0x401010:d=1', '-frames:v', '1', str(png)], check=True)
    ansi = work / 'Drehbuch_ANSI.txt'
    ansi.write_bytes('# Die Wüste\n### Szene 1 – Düne – Jörg und Bärbel im Sand\nJÖRG (wütend): Wo ist das Wasser, Bärbel? Ich hab so großen Durst!\n'
                     'BÄRBEL (spöttisch): Im Kühlschrank, Jörg. Der steht leider zu Hause.\nAKTION: Jörg lässt sich rückwärts in den Sand fallen.\n'
                     'JÖRG (flehend): Dann lass uns sofort umdrehen, bitte, bitte, bitte!\n'.encode('cp1252'))
    utf16 = work / 'Drehbuch_Unicode.txt'                     # Windows Editor 'Unicode': UTF-16 with a byte order mark
    utf16.write_bytes('# Die Oase\n### Szene 1 – Oase – Jörg am Brunnen\nJÖRG (fröhlich): Wasser, Bärbel! Endlich wieder Wasser für uns beide!\n'
                      'BÄRBEL (überrascht): Das glaub ich nicht. Ist das wirklich echt, Jörg?\n'.encode('utf-16'))
    pdf = work / 'Drehbuch.pdf'; pdf.write_bytes(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n')

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}, accept_downloads=True); errors = []; posts = []
        page.on('pageerror', lambda e: errors.append(str(e))); page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
        page.on('request', lambda q: q.method == 'POST' and q.url.endswith('/api/factory') and posts.append(json.loads(q.post_data or '{}')))
        page.goto(studio.url + '/#new'); page.wait_for_selector('#idea'); page.wait_for_timeout(600)
        story = page.locator('[data-set="story"]')
        r.check('Auswahl: „Die KI schreibt“ und „Mein Drehbuch“, KI ist vorgewählt',
                story.all_inner_texts() == ['Die KI schreibt', 'Mein Drehbuch'] and page.get_attribute('[data-set="story"][data-value="ai"]', 'aria-pressed') == 'true')
        page.click('[data-set="story"][data-value="script"]'); page.wait_for_selector('#script'); page.wait_for_timeout(400)
        r.check('Mein Drehbuch: großes Textfeld, Dateiwahl, kein Ideenfeld', page.locator('#script').is_visible() and page.locator('#idea').count() == 0
                and page.locator('input[data-upload="script"]').count() == 1)
        r.check('Längenwahl ersetzt durch „Länge nach Drehbuch“', page.locator('[data-set="duration"]').count() == 0
                and page.locator('#script-length').inner_text().startswith('Länge nach Drehbuch'))
        r.check('Ohne Text: freundlicher Hinweis statt Prüfung', 'Sobald dein Drehbuch hier steht' in page.locator('#script-check').inner_text())
        page.screenshot(path=str(shots / '01_drehbuch_leer_1280_hell.png'))

        with page.expect_download() as info: page.click('a[download="Drehbuch_Vorlage.md"]')
        template = Path(info.value.path()).read_text(encoding='utf-8')
        r.check(f'Vorlage herunterladen: {info.value.suggested_filename} mit Beispiel', info.value.suggested_filename == 'Drehbuch_Vorlage.md'
                and template.startswith('# Der verschwundene Kuchen') and 'OMA HILDE (wütend):' in template)

        page.fill('#script', SCRIPT); page.wait_for_selector('#script-check .script-check', timeout=8000); page.wait_for_timeout(700)
        check = ' '.join(page.locator('#script-check').inner_text().split())
        r.check(f'Prüfung: Länge je Folge ({check[:90]}…)', 'Länge nach Drehbuch' in check and 'Folge 1 etwa 35 s · Folge 2 etwa 19 s' in check)
        r.check('Prüfung: Figuren, Szenen, Sätze, Wörter, Folgen', all(x in check for x in ('3 Figuren', '3 Szenen', '12 Sätze', '100 Wörter', '2 Folgen',
                                                                                         'Es spielen Oma Hilde, Frau Müller, Tim.')))
        r.check('Prüfung ohne Probleme: „Passt.“', 'Passt. Der Film kann so entstehen.' in check and not page.locator('#script-check .problems').count())
        page.fill('#script', SCRIPT + 'MUSIK: leise Geigen\nERZÄHLER (gelangweilt): Und so begann die Jagd.\n'); page.wait_for_timeout(1200)
        line = SCRIPT.count('\n') + 1; hints = page.locator('#script-check .problems').inner_text()
        r.check(f'Prüfung: Hinweise mit Zeilennummer (Zeile {line}, {line + 1})', f'Zeile {line}: Musik-Angaben setzt das Studio selbst' in hints
                and f'Zeile {line + 1}: „Erzähler“ ist im Film eine sichtbare Figur' in hints and 'Die Hinweise sind Vorschläge' in page.locator('#script-check').inner_text())
        page.screenshot(path=str(shots / '02a_drehbuch_hinweise_1280_hell.png'))
        page.fill('#script', SCRIPT); page.wait_for_timeout(1200)
        r.check('Länge und Folgen aus dem Drehbuch in den Einstellungen', page.locator('#script-length').inner_text() == 'Länge nach Drehbuch: Folge 1 etwa 35 s, Folge 2 etwa 19 s'
                and page.locator('#script-episodes').inner_text() == '2 Folgen aus deinem Drehbuch' and page.locator('#create').inner_text() == 'Serie mit 2 Folgen verfilmen')
        page.click('.script-preview summary'); page.wait_for_timeout(200)
        r.check('„So liest das Studio dein Drehbuch“ zeigt das Format', 'Frau Müller [überrascht]: Hilde, ist alles in Ordnung?' in page.locator('.script-preview pre').inner_text())
        page.click('details.more summary'); page.wait_for_timeout(300)
        names = page.locator('details.more .person-name').all_inner_texts()
        r.check(f'Figuren aus dem Drehbuch im Bereich Figuren ({names})', names == ['Oma Hilde', 'Frau Müller', 'Tim']
                and page.locator('details.more [data-action="add-person"]').count() == 0 and page.locator('details.more [data-set="characters"]').count() == 0
                and 'Nachbarin, Mitte fünfzig' in page.locator('details.more .person-about').nth(1).inner_text())
        page.set_input_files('details.more .person:nth-child(2) input[data-upload="image"]', str(png))
        page.wait_for_selector('details.more .person:nth-child(2) .thumb img', timeout=15000); page.wait_for_timeout(400)
        r.check('Eigenes Bild für Frau Müller übernommen', page.locator('details.more .person:nth-child(2) .thumb img').count() == 1)
        page.screenshot(path=str(shots / '02_drehbuch_geprueft_1280_hell.png'), full_page=True)

        page.set_input_files('input[data-upload="script"]', str(pdf)); page.wait_for_timeout(500)
        r.check('PDF: deutscher Hinweis, Text bleibt', 'PDF kann das Studio nicht zuverlässig lesen. Öffne das PDF, kopiere den Text und füge ihn hier ein, oder speichere es als .txt.'
                in page.locator('#script-check').inner_text() and page.input_value('#script') == SCRIPT)
        page.screenshot(path=str(shots / '03_pdf_hinweis_1280_hell.png'))

        page.set_input_files('input[data-upload="script"]', str(ansi)); page.wait_for_timeout(1200)
        r.check('Datei (ANSI, Umlaute) übernommen und geprüft', page.input_value('#script').startswith('# Die Wüste') and 'JÖRG (wütend)' in page.input_value('#script')
                and 'Es spielen Jörg, Bärbel.' in page.locator('#script-check').inner_text() and 'PDF' not in page.locator('#script-check').inner_text())

        page.set_input_files('input[data-upload="script"]', str(utf16)); page.wait_for_timeout(1200)
        r.check('Datei (UTF-16 „Unicode“ aus dem Windows-Editor) übernommen und geprüft', page.input_value('#script').startswith('# Die Oase')
                and 'JÖRG (fröhlich): Wasser, Bärbel!' in page.input_value('#script') and 'Es spielen Jörg, Bärbel.' in page.locator('#script-check').inner_text()
                and 'kein Text' not in page.locator('#script-check').inner_text())
        page.screenshot(path=str(shots / '03b_utf16_datei_1280_hell.png'))

        page.fill('#script', SHORT); page.wait_for_timeout(1200)
        r.check('Zu kurz: blockierender Hinweis', 'mindestens 15 s' in page.locator('#script-check .problems.block').inner_text())
        before = len(posts); page.click('#create'); page.wait_for_timeout(800)
        r.check('Zu kurz: kein Film angelegt, Meldung sichtbar', len(posts) == before and page.url.endswith('#new') and 'mindestens 15 s' in page.locator('#toast').inner_text())

        page.fill('#script', SCRIPT); page.wait_for_timeout(1200)
        page.click('#create'); page.wait_for_url('**/#p=*', timeout=15000); page.wait_for_timeout(1500)
        body = posts[-1]; rid = page.url.split('#p=')[1]; doc = studio.call(f'/api/factory/{rid}')[1]
        r.check('Anfrage: story=script, Folgen und Länge aus dem Drehbuch, nur Figuren aus dem Drehbuch',
                body.get('story') == 'script' and 'script' not in body and body['episodes'] == 2 and body['duration'] == 17 and body['characters'] == 'provided'
                and [p_['name'] for p_ in body['participants']] == ['Frau Müller'] and body['participants'][0]['image'])
        r.check('Projekt: wortgetreues Drehbuch gespeichert', doc['idea']['story'] == 'script' and doc['idea']['idea'] == SCRIPT
                and doc['title'] == 'Der Kuchenklau von Hausnummer 7' and len(doc['script']['episodes']) == 2)
        r.check('Projektseite: „Mein Drehbuch“ in der Zeile', 'Mein Drehbuch' in page.locator('.project-head').inner_text())

        page.goto(studio.url + '/#new'); page.wait_for_selector('#script'); page.wait_for_timeout(500)
        r.check('Nach dem Anlegen bleibt „Mein Drehbuch“ gewählt, Feld leer', page.get_attribute('[data-set="story"][data-value="script"]', 'aria-pressed') == 'true'
                and page.input_value('#script') == '')
        page.click('[data-set="story"][data-value="ai"]'); page.wait_for_selector('#idea'); page.wait_for_timeout(300)
        page.fill('#idea', 'Zwei Kollegen streiten um den letzten Keks. Am Ende hat ihn die Praktikantin.'); page.click('[data-set="duration"][data-value="30"]')
        page.click('#create'); page.wait_for_url('**/#p=*', timeout=15000); page.wait_for_timeout(800)
        r.check('Die KI schreibt: Anfrage ohne story und script (wie vor 0.18)', 'story' not in posts[-1] and 'script' not in posts[-1] and posts[-1]['duration'] == 30)

        page.goto(f'{studio.url}/#p={SCRIPT_RID}'); page.wait_for_selector('.mix', timeout=15000); page.wait_for_timeout(600)
        r.check('Drehbuch-Projekt: kein „Dialoge ergänzen“, „Ton neu erzeugen“ bleibt', page.locator('[data-action="more-dialogue"]').count() == 0
                and page.locator('[data-action="rebuild-audio"]').count() == 1)
        r.check('Drehbuch-Projekt: Hinweis zum Drehbuch sichtbar', 'Hinweis zu deinem Drehbuch' in page.locator('.warn-line').first.inner_text())
        page.screenshot(path=str(shots / '04_drehbuch_projekt_ton_1280_hell.png'), full_page=True)

        def compose(width, scheme, name, text=SCRIPT):
            page.set_viewport_size({'width': width, 'height': 900 if width > 500 else 844}); page.emulate_media(color_scheme=scheme)
            page.goto(studio.url + '/#new'); page.wait_for_selector('[data-set="story"]'); page.wait_for_timeout(300)
            if not page.locator('#script').count(): page.click('[data-set="story"][data-value="script"]')
            page.wait_for_selector('#script'); page.fill('#script', text)
            page.wait_for_selector('#script-check .script-check', timeout=8000); page.wait_for_timeout(700)
            page.screenshot(path=str(shots / f'{name}.png'), full_page=True)
        compose(1280, 'dark', '05_drehbuch_1280_dunkel')
        compose(390, 'light', '06_drehbuch_390_hell')
        r.check('Handy: keine waagerechte Scrollleiste', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        compose(390, 'dark', '07_drehbuch_390_dunkel', SHORT)
        r.check('Handy dunkel: keine waagerechte Scrollleiste', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        r.check('Keine JavaScript-Fehler', not [e for e in errors if 'Failed to load resource' not in e]); print('   ', errors[:3])
        browser.close()
finally:
    studio.close()
r.done()
