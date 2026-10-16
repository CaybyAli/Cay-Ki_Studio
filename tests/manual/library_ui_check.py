"""Figure library in the browser: page, editor, picker in a new film and in a running project.

Run: python tests/manual/library_ui_check.py <empty dir>   (screenshots in <dir>/shots)
"""
import json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report(); db = studio.db


def png(path, a='0xffd23f', b='0xee4266'):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'gradients=s=768x1024:c0={a}:c1={b}:d=1', '-frames:v', '1', str(path)], check=True)
    return path


def wav(path, seconds=3, freq=180):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=frequency={freq}:duration={seconds}', '-af', 'volume=0.6,tremolo=f=3:d=0.9',
                    '-ar', '24000', '-ac', '1', str(path)], check=True)
    return path


def upload(kind, path):
    import urllib.request
    req = urllib.request.Request(f'{studio.url}/api/factory/assets?kind={kind}&name={path.name}', data=path.read_bytes(), headers={'X-Cay-Token': studio.token}, method='POST')
    with studio.opener.open(req, timeout=20) as resp: return json.load(resp)['id']


CAST = [{'name': 'Patrick', 'appearance': 'pink starfish', 'personality': 'dreamy', 'voice_preset': 'man'},
        {'name': 'SpongeBob', 'appearance': 'yellow sponge', 'personality': 'eager', 'voice_preset': 'young_man'}]


def scene(who, line):
    return {'title': f'{who} spricht', 'action': f'{who} winkt am Strand.', 'location': 'Strand', 'camera': 'Halbnah', 'cast': [who],
            'dialogues': [{'speaker': who, 'text': line, 'emotion': 'fröhlich', 'pause_after': .18}], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'problem', 'because': 'x', 'round': 0, 'selected': None, 'render_seconds': 4, 'seconds': 4, 'variants': []}


try:
    folder = studio.root / '01_Projekte/Studio' / ('a' * 32)
    sheet = png(folder / '02_Bilder/patrick.png', '0xff8fb1', '0x7a2e4d'); sb = png(folder / '02_Bilder/sb.png', '0xffe066', '0xc49a00')
    voice = wav(folder / '03_Stimmen/Profile/p.wav'); voice.with_suffix('.json').write_text(json.dumps({'description': 'An adult man, warm voice, cartoon actor.', 'seed': 7}))
    episodes = [{'title': 'Strandtag', 'scenes': [scene('Patrick', 'Hallo SpongeBob!'), scene('SpongeBob', 'Hallo Patrick!'), scene('Patrick', 'Wo ist mein Stein?')]}]
    studio.project('a' * 32, 'cast_review', {'plan': {'cast': CAST, 'style': 'clay', 'mood': 'playful'}, 'episodes': episodes,
                   'cast_refs': {'Patrick': str(sheet), 'SpongeBob': str(sb)},
                   'voice_profiles': {'Patrick': {'file': str(voice), 'sha256': 'x', 'source': 'designed', 'voice_text': 'Na endlich!'}}},
                   {'look': 'clay', 'cast_check': True}, paused=1)
    code, patrick = studio.call('/api/library/from-project', {'project': 'a' * 32, 'name': 'Patrick', 'label': 'Patrick Knete'})
    krabs = studio.call('/api/library', {'name': 'Mr. Krabs', 'label': 'Mr. Krabs Cartoon', 'look': 'cartoon', 'traits': 'red crab',
                                         'image': upload('image', png(work / 'k.png', '0xd03030', '0x401010')), 'voice': upload('voice', wav(work / 'k.wav', 4, 140))})[1]
    studio.call('/api/library', {'name': 'Oma', 'label': 'Oma Erna', 'look': 'film', 'image': upload('image', png(work / 'o.png', '0x9ad0ec', '0x1f4e79'))})
    studio.project('b' * 32, 'cast_review', {'plan': {'cast': [dict(c) for c in CAST], 'style': 'clay', 'mood': 'playful'}, 'episodes': episodes,
                   'cast_refs': {'Patrick': str(sheet), 'SpongeBob': str(sb)}}, {'look': 'clay', 'cast_check': True}, paused=1)
    studio.project('c' * 32, 'audio_mixing', {'plan': {'cast': [dict(c) for c in CAST], 'style': 'clay', 'mood': 'playful'}, 'episodes': episodes,
                   'cast_refs': {'Patrick': str(sheet), 'SpongeBob': str(sb)}, 'voice_profiles': {'Patrick': {'file': str(voice), 'sha256': 'x', 'source': 'designed'}}},
                   {'look': 'clay'}, paused=1)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}); errors = []
        page.on('pageerror', lambda e: errors.append(str(e))); page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
        base = studio.url + '/'
        page.goto(base + '#library'); page.wait_for_selector('.card'); page.wait_for_timeout(600)
        page.screenshot(path=str(shots / '01_figuren.png'), full_page=True)
        r.check('Figuren-Seite: 3 Karten, Reiter aktiv', page.locator('.card').count() == 3 and page.locator('[data-nav="library"][aria-current="page"]').count() == 1)
        r.check('Karte mit Stimme zeigt Wellenform, ohne Stimme den Hinweis', page.locator('.card .wave rect').count() > 30 and page.locator('.voice-strip.none').count() == 1)
        page.locator('.card .voice-strip .play').first.click(); page.wait_for_timeout(300)
        r.check('▶ spielt ab und öffnet nicht den Editor', not page.locator('#sheet').evaluate('d => d.open'))
        page.fill('[data-libq="lib-cards"]', 'krabs'); page.wait_for_timeout(200)
        r.check('Suche filtert und behält den Fokus', page.locator('.card').count() == 1 and page.evaluate("document.activeElement.dataset.libq") == 'lib-cards')
        page.fill('[data-libq="lib-cards"]', ''); page.click('[data-liblook="clay"]'); page.wait_for_timeout(200)
        r.check('Look-Filter Knete', page.locator('.card').count() == 1 and 'Patrick Knete' in page.locator('.card').inner_text())
        page.click('[data-liblook="all"]')
        page.click('.card-open >> text=Patrick Knete'); page.wait_for_timeout(400)
        page.screenshot(path=str(shots / '02_figur_bearbeiten.png'))
        r.check('Editor: Felder vorbefüllt, Look Knete, Aufnahme aus Projekt', page.locator('#lib-form [name="label"]').input_value() == 'Patrick Knete'
                and page.locator('#lib-form input[name="look"][value="clay"]').is_checked() and 'Aufgenommen aus' in page.locator('#lib-form').inner_text())
        page.fill('#lib-form [name="label"]', 'Patrick Knete Strand'); page.click('#lib-form [type="submit"]'); page.wait_for_timeout(700)
        r.check('Speichern: Karte umbenannt', page.locator('.card-open >> text=Patrick Knete Strand').count() == 1)
        page.click('[data-action="lib-new"] >> nth=0'); page.wait_for_timeout(300)
        page.fill('#lib-form [name="label"]', 'Leer'); page.fill('#lib-form [name="name"]', 'Leer'); page.click('#lib-form [type="submit"]'); page.wait_for_timeout(400)
        r.check('Neue Figur ohne Bild und Stimme: klare Meldung, Sheet bleibt offen', page.locator('#sheet').evaluate('d => d.open') and 'Wähle ein Bild' in page.locator('#toast').inner_text())
        page.locator('#lib-form input[data-upload="lib-image"]').set_input_files(str(png(work / 'neu.png', '0x80ffdb', '0x2a7f62'))); page.wait_for_timeout(800)
        page.click('#lib-form [type="submit"]'); page.wait_for_timeout(700)
        r.check('Neue Figur mit Bild angelegt', page.locator('.card').count() == 4)
        page.emulate_media(color_scheme='dark'); page.wait_for_timeout(300); page.screenshot(path=str(shots / '03_figuren_dunkel.png'), full_page=True); page.emulate_media(color_scheme='light')

        # New film: pick from the library
        page.goto(base + '#new'); page.wait_for_timeout(500); page.click('[data-set="look"][data-value="clay"]'); page.click('details.more summary')
        page.click('[data-action="lib-pick-compose"]'); page.wait_for_selector('#pick-grid .pick')
        page.click('#pick-grid .pick >> text=Patrick Knete Strand'); page.click('#pick-grid .pick >> text=Mr. Krabs Cartoon'); page.wait_for_timeout(200)
        page.screenshot(path=str(shots / '04_auswahl_neuer_film.png'))
        r.check('Auswahl: 2 gewählt, anderer Look wird nachgezeichnet', '2 gewählt' in page.locator('#pick-foot').inner_text() and 'wird im Look deines Films nachgezeichnet' in page.locator('#pick-grid').inner_text())
        page.click('[data-action="lib-add-compose"]'); page.wait_for_timeout(400)
        draft = page.evaluate("JSON.parse(localStorage.getItem('cay-draft'))")
        names = [x['name'] for x in draft['participants']]
        r.check('Neuer Film: Figuren mit Bild, Stimme und Profil übernommen', names == ['Patrick', 'Mr. Krabs'] and all(x['library_id'] and x['image'] for x in draft['participants'])
                and draft['participants'][0]['voice_design']['seed'] == 7 and page.locator('.person .chip.accent').count() == 2
                and draft['participants'][1]['image_look'] == 'cartoon' and draft['participants'][1]['library_voice'] == krabs['id'])
        page.screenshot(path=str(shots / '05_neuer_film_figuren.png'), full_page=True)

        # Running project in the figure check: tap a figure, suggestion by name, picker, apply now
        page.goto(base + '#p=' + 'b' * 32); page.wait_for_selector('.cast .role')
        page.screenshot(path=str(shots / '06_besetzung.png'), full_page=True)
        r.check('Besetzung: 2 Figuren, Quelle von Bild und Stimme sichtbar', page.locator('.cast .role').count() == 2
                and 'Vom Studio gestaltet' in page.locator('.role', has_text='Patrick').inner_text() and 'Stimme' in page.locator('.role-src').first.inner_text())
        r.check('Vorschlag nach Namen: nur bei Patrick', page.locator('.role-suggest').count() == 1 and 'Patrick Knete Strand verwenden' in page.locator('.role', has_text='Patrick').inner_text())
        page.click('.role-hit[data-name="Patrick"]'); page.wait_for_selector('.menu-section'); page.wait_for_timeout(300)
        page.screenshot(path=str(shots / '06b_figur_menue.png'))
        sheet = page.locator('#sheet').inner_text()
        r.check('Figur-Menü: Bibliothek, Bild, Stimme, Aufnehmen', page.locator('#sheet .menu-section').count() == 4 and 'Patrick Knete Strand verwenden' in sheet
                and 'Neu gestalten' in sheet and 'Eigene Aufnahme hochladen' in sheet and 'In 2 Szenen zu sehen' in sheet)
        page.click('.menu-row[data-action="lib-pick-project"]'); page.wait_for_selector('#pick-grid .pick')
        r.check('Auswahl im Projekt: passende Figur zuerst', 'Patrick Knete Strand' in page.locator('#pick-grid .pick-title').first.inner_text()
                and 'Passt zu Patrick' in page.locator('#pick-grid .pick').first.inner_text())
        page.click('#pick-grid .pick >> text=Patrick Knete Strand'); page.wait_for_timeout(200)
        page.screenshot(path=str(shots / '07_auswahl_projekt.png'))
        foot = page.locator('#pick-foot').inner_text()
        r.check('Projekt-Auswahl: Folgen klar benannt (2 Szenen, 2 Sätze)', '2 Szenen werden neu gezeichnet' in foot and '2 Sätze werden neu eingesprochen' in foot
                and 'übernehmen' in page.locator('[data-action="lib-apply"]').inner_text())
        page.click('[data-action="lib-apply"]'); page.wait_for_timeout(900)
        d = json.loads(page.evaluate("fetch('/api/factory/" + 'b' * 32 + "').then(r=>r.text())"))
        part = next(x for x in d['idea']['participants'] if x['name'] == 'Patrick')
        r.check('Projekt: Patrick hat Bild und Stimme des Profils, Szenen werden neu gezeichnet', part['library_image'] == patrick['id'] and part['library_voice'] == patrick['id']
                and d['state'] == 'pictures' and 'Patrick' not in d.get('cast_refs', {}))
        page.wait_for_timeout(600)
        r.check('Karte zeigt das Profil als Quelle, kein Vorschlag mehr', page.locator('.role-suggest').count() == 0
                and page.locator('.role', has_text='Patrick').inner_text().count('Patrick Knete Strand') == 2)

        # Project mixing its sound: the voice is kept for later, the image is closed with the reason
        page.goto(base + '#p=' + 'c' * 32); page.wait_for_selector('.cast .role')
        page.click('.role-hit[data-name="SpongeBob"]'); page.wait_for_selector('.menu-section'); page.wait_for_timeout(200)
        sheet = page.locator('#sheet').inner_text()
        r.check('Beim Mischen: Bild geschlossen mit Grund, Stimme vormerkbar', 'Szenenbilder sind schon gewählt' in sheet and 'sobald der Ton gemischt ist' in sheet)
        page.click('.menu-row[data-action="lib-pick-project"]'); page.wait_for_selector('#pick-grid .pick')
        page.click('#pick-grid .pick >> text=Mr. Krabs Cartoon'); page.wait_for_timeout(200)
        page.screenshot(path=str(shots / '07b_vormerken.png'))
        r.check('Vormerken: Bild gesperrt, Stimme vorgemerkt, Knopf sagt es', page.locator('#pick-image').is_disabled() and page.locator('#pick-voice').is_checked()
                and 'vormerken' in page.locator('[data-action="lib-apply"]').inner_text())
        page.click('[data-action="lib-apply"]'); page.wait_for_timeout(900)
        r.check('Vorgemerkt auf der Karte und als Meldung', 'Vorgemerkt: Stimme von „Mr. Krabs Cartoon“' in page.locator('.role', has_text='SpongeBob').inner_text()
                and 'Vorgemerkt' in page.locator('#toast').inner_text())
        page.screenshot(path=str(shots / '07c_vorgemerkt.png'), full_page=True)
        page.click('.role-hit[data-name="SpongeBob"]'); page.wait_for_selector('.notice'); page.click('[data-action="cast-cancel"]'); page.wait_for_timeout(700)
        r.check('Vormerkung aufheben', page.locator('.role-pending').count() == 0 and not json.loads(page.evaluate("fetch('/api/factory/" + 'c' * 32 + "').then(r=>r.text())"))['pending_cast'])
        page.set_viewport_size({'width': 390, 'height': 844}); page.goto(base + '#p=' + 'c' * 32); page.wait_for_selector('.cast .role'); page.wait_for_timeout(400)
        page.screenshot(path=str(shots / '07d_besetzung_handy.png'), full_page=True)
        r.check('Handy: Besetzung ohne waagerechte Scrollleiste', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        page.click('.role-hit[data-name="SpongeBob"]'); page.wait_for_selector('.menu-section'); page.wait_for_timeout(300)
        page.screenshot(path=str(shots / '07e_figur_menue_handy.png'))
        page.keyboard.press('Escape'); page.set_viewport_size({'width': 1280, 'height': 900})
        # Save SpongeBob from the first project
        page.goto(base + '#p=' + 'a' * 32); page.wait_for_selector('.cast .role')
        page.click('.role-hit[data-name="SpongeBob"]'); page.wait_for_selector('.menu-row'); page.click('.menu-row[data-action="lib-save"]'); page.wait_for_timeout(300)
        r.check('Aufnehmen: Profilname vorgeschlagen', page.locator('#lib-save-form [name="label"]').input_value() == 'SpongeBob Knete')
        page.click('#lib-save-form [type="submit"]'); page.wait_for_timeout(700)
        lib = json.loads(page.evaluate("fetch('/api/library').then(r=>r.text())"))
        r.check('SpongeBob Knete in deinen Figuren (nur Bild, noch keine Stimme)', any(f['label'] == 'SpongeBob Knete' and f['image'] and not f['voice'] for f in lib['figures']))

        page.set_viewport_size({'width': 390, 'height': 844}); page.goto(base + '#library'); page.wait_for_selector('.card'); page.wait_for_timeout(400)
        page.screenshot(path=str(shots / '08_figuren_handy.png'), full_page=True)
        r.check('Handy: keine waagerechte Scrollleiste', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        page.click('.card-open >> nth=0'); page.wait_for_timeout(300); page.screenshot(path=str(shots / '09_editor_handy.png'))
        # Removed by mistake: "Rückgängig" in the message brings the figure back with image and voice
        label = page.locator('#lib-form [name="label"]').input_value(); cards = page.locator('.card').count()
        page.once('dialog', lambda d: d.accept()); page.click('#lib-form [data-action="lib-delete"]'); page.wait_for_selector('#toast .toast-action'); page.wait_for_timeout(400)
        page.screenshot(path=str(shots / '10_entfernt_rueckgaengig_handy.png'))
        r.check('Entfernen: Meldung mit „Rückgängig“, Karte weg, keine waagerechte Scrollleiste', f'„{label}“ entfernt.' in page.locator('#toast').inner_text()
                and page.locator('#toast .toast-action').inner_text() == 'Rückgängig' and page.locator('.card').count() == cards - 1
                and page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        page.click('#toast .toast-action'); page.wait_for_timeout(700)
        lib = json.loads(page.evaluate("fetch('/api/library').then(r=>r.text())"))
        r.check('Rückgängig: Figur wieder da, Meldung sagt es', page.locator('.card').count() == cards and any(f['label'] == label for f in lib['figures'])
                and f'„{label}“ ist wieder da.' in page.locator('#toast').inner_text() and page.locator('#toast .toast-action').count() == 0)
        r.check('Keine JavaScript-Fehler', not [e for e in errors if 'Failed to load resource' not in e]); print('   ', errors[:3])
        browser.close()
finally:
    studio.close()
r.done()
