"""New studio UI against the real dashboard: every project state, light/dark, phone width.

Run: python tests/manual/ui_check.py <empty dir>
Seeds projects with real PNG/WAV/MP4 files (FFmpeg), no AI models.
Writes screenshots into <dir>/shots and prints functional checks.
"""
import hashlib, json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1]))
from harness import Studio, Report

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report(); db = studio.db
COLORS = [('0x1e3c72', '0x2a5298'), ('0x614385', '0x516395'), ('0x134e5e', '0x71b280'), ('0x833ab4', '0xfd1d1d'), ('0x0f2027', '0x2c5364'), ('0xc94b4b', '0x4b134f')]


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def picture(rid, sid, n):
    out = studio.root / '01_Projekte/Studio' / rid / '02_Bilder' / f'{sid}.png'; out.parent.mkdir(parents=True, exist_ok=True)
    a, b = COLORS[n % len(COLORS)]
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'gradients=s=576x1024:c0={a}:c1={b}:x0=0:y0=0:x1=576:y1=1024:d=1',
                    '-frames:v', '1', str(out)], check=True)
    db.execute("INSERT INTO factory_steps(id,run_id,step_key,status,prompt_id,graph,output,sha256) VALUES(?,?,?,?,?,?,?,?)",
               (sid, rid, f'image:0:{n}:0:{n % 2}', 'done', None, '{}', str(out), sha(out)))
    return sid


def media(path, kind, seconds=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    if kind == 'wav':
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=frequency=220:duration={seconds}', '-ar', '24000', str(path)], check=True)
    else:
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'gradients=s=1080x1920:c0=0x1e3c72:c1=0xfd1d1d:d={seconds}', '-f', 'lavfi', '-i', f'sine=frequency=330:duration={seconds}',
                        '-shortest', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(path)], check=True)
    return {'file': str(path), 'sha256': sha(path)}


def scene(title, cast, lines, variants=(), selected=None):
    return {'title': title, 'action': 'Lena hält den letzten Keks hoch, Markus verschränkt die Arme.', 'location': 'Büroküche', 'camera': 'Halbnah',
            'cast': cast, 'dialogues': [{'speaker': s, 'text': t, 'emotion': 'Natürlich', 'pause_after': .18} for s, t in lines], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'problem', 'because': 'x', 'round': 0, 'selected': selected, 'render_seconds': 4.4, 'seconds': 4.4,
            'variants': [{'id': v, 'key': f'image:0:0:0:{i}'} for i, v in enumerate(variants)]}


CAST = [{'name': 'Lena', 'appearance': 'woman', 'personality': 'klug', 'voice_preset': 'young_woman'}, {'name': 'Markus', 'appearance': 'man', 'personality': 'stur', 'voice_preset': 'man'}]
SOCIAL = {'caption': 'Wer bekommt den letzten Keks? Die Antwort überrascht beide.', 'hashtags': ['büro', 'kollegen', 'keks', 'comedy']}
ids = iter(f'{i:032x}' for i in range(1, 400))


def project(rid, state, title, extra=None, idea=None, paused=1, episodes=None):
    studio.project(rid, state, {'title': title, 'plan': {'title': title, 'cast': CAST, 'style': 'x', 'mood': 'playful', 'episodes': [{'title': title}]},
                                'episodes': episodes or [], **(extra or {})}, {'idea': 'Zwei Kollegen streiten um den letzten Keks im Büro.', **(idea or {})}, paused)


try:
    # image review: 3 scenes with two variants each
    rid = 'a' * 32; eps = []
    for si in range(3):
        v = [picture(rid, next(ids), si * 2), picture(rid, next(ids), si * 2 + 1)]
        eps.append(scene(['Der Fund', 'Der Anspruch', 'Die Wendung'][si], ['Lena'] if si != 1 else ['Markus'],
                         [('Lena', 'Das ist mein Keks. Ich habe ihn um elf bestellt.')] if si != 1 else [('Markus', 'Seniorität schlägt Bestellzeit.')], v, v[0] if si == 0 else None))
    spine = {'logline': 'Lena will den letzten Keks retten, bevor Markus ihn sich mit einer Regel schnappt.', 'viewer_question': 'Wer isst ihn?',
             'hook': 'Der Keks liegt allein auf dem Teller.', 'goal': 'Keks', 'stakes': 'Ehre', 'escalations': ['Regel', 'Gegenregel'],
             'twist': 'Der Chef isst ihn.', 'payoff': 'Beide teilen sich einen neuen.', 'final_moment': 'Krümel', 'running_gag': ''}
    figure = studio.root / '01_Projekte/Studio' / rid / '02_Bilder/figur.png'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'gradients=s=864x1536:c0=0xffd23f:c1=0xee4266:d=1', '-frames:v', '1', str(figure)], check=True)
    project(rid, 'image_review', 'Der letzte Keks', {'cast_refs': {'Lena': str(figure), 'Markus': str(figure)}},
            episodes=[{'title': 'Der letzte Keks', 'scenes': eps, 'social': SOCIAL, 'spine': spine}], paused=0)
    # image review for the figure redesign (paused: the worker must not start rendering)
    rid = 'f' * 32; eps = []
    for si, who in enumerate((['Lena'], ['Markus'], ['Lena'])):
        v = [picture(rid, next(ids), si * 2), picture(rid, next(ids), si * 2 + 1)]
        eps.append(scene(f'Szene {si + 1}', who, [(who[0], 'Hallo.')], v, v[0]))
    eps[0]['dialogues'][0].update(emotion='schreiend', pause_after=.3)   # the line editor must keep the delivery
    eps[2].update(dialogues=[], dialogue='Hallo.', speaker='Lena', emotion='flüsternd')   # old single-line scene
    project(rid, 'image_review', 'Neue Gesichter', {'cast_refs': {'Lena': str(figure), 'Markus': str(figure)}}, episodes=[{'title': 'Neue Gesichter', 'scenes': eps}])
    # figure check stop (0.17): designs ready, no scene images yet
    rid = '1' * 32
    project(rid, 'cast_review', 'Figurencheck', {'cast_refs': {'Lena': str(figure), 'Markus': str(figure)}}, {'cast_check': True, 'autopilot': True},
            episodes=[{'title': 'Figurencheck', 'scenes': [scene('Szene 1', ['Lena'], [('Lena', 'Hallo, Markus!')])],
                       'screenplay_stats': {'words': 118, 'lines': 19, 'actions': 2, 'shots': 19, 'budget': {'words': 120}}}], paused=0)
    # voice review
    rid = 'b' * 32; folder = studio.root / '01_Projekte/Studio' / rid
    pics = [picture(rid, next(ids), n) for n in range(3)]
    lines = []
    for i, (spk, text) in enumerate([('Lena', 'Das ist mein Keks.'), ('Markus', 'Seniorität schlägt Bestellzeit.'), ('Lena', 'Dann teilen wir eben.')]):
        m = media(folder / f'03_Stimmen/l{i}.wav', 'wav', 2)
        lines.append({**m, 'key': f'E01_S{i + 1:02}_T01', 'episode': 0, 'scene': i, 'turn': 0, 'speaker': spk, 'text': text, 'text_de': text, 'duration': 2.0, 'offset': .12})
    mixf = media(folder / '03_Stimmen/mix.wav', 'wav', 15)
    project(rid, 'voice_review', 'Kaffee für zwei', {'lines': lines, 'previews': [{**mixf, 'episode': 0, 'seconds': 15}],
            'timing': [{'seconds': 15.2, 'speech_seconds': 9.6, 'speech_share': .63, 'longest_speech_gap': 1.1}], 'mix': {'music_mode': 'off'},
            'voice_profiles': {'Lena': mixf, 'Markus': mixf}},
            episodes=[{'title': 'Kaffee für zwei', 'scenes': [scene('Szene', ['Lena'], [('Lena', 'Das ist mein Keks.')], [p], p) for p in pics]}])
    # rendering with a stalled section
    rid = 'c' * 32; pics = [picture(rid, next(ids), n + 2) for n in range(4)]
    project(rid, 'rendering', 'Der Tresor', {'render_tracking_version': 10, 'render_segments': {f'0:{i}:0': f's{i}' for i in range(3)},
            'lines': [{'episode': 0, 'scene': i, 'speaker': 'Lena', 'duration': 2, 'file': 'x', 'sha256': 'x'} for i in range(4)], 'phase': 'Animation, Szene 3 von 4'},
            {'episodes': 3}, episodes=[{'title': 'Der Tresor', 'scenes': [scene('S', ['Lena'], [('Lena', 'Pst.')], [p], p) for p in pics]}] * 3)
    now = time.time()
    for i in range(3):
        db.execute("INSERT INTO factory_steps(id,run_id,step_key,status,prompt_id,graph) VALUES(?,?,?,?,?,?)", (f's{i}', rid, f'video09:0:{i}:0:k', 'done' if i < 2 else 'submitted', f'p{i}', '{}'))
        detail = {'profile': {'frames': 129, 'width': 576, 'height': 1024, 'steps': 4}, 'nodes': {}, 'cached': [], 'coverage': 'events', 'status': 'running' if i == 2 else 'done',
                  'label': 'Mundbewegung animieren', **({'node': '12', 'progress': {'value': 5, 'max': 8}} if i == 2 else {})}
        db.execute('INSERT INTO factory_metrics VALUES(?,?,?,?,?,?,?)', (f's{i}', rid, now - 3000 + i * 600, now - 2990 + i * 600, None if i == 2 else now - 2500 + i * 600, now - 900 if i == 2 else now - 2500 + i * 600, json.dumps(detail)))
    # done series with exports and captions
    rid = 'd' * 32; folder = studio.root / '03_Fertige_Videos/Studio' / rid; pics = [picture(rid, next(ids), n) for n in range(2)]
    exports = [{**media(folder / f'Folge_0{i + 1}.mp4', 'mp4', 3), 'episode': i, 'seconds': 3, 'fps': 25} for i in range(2)]
    project(rid, 'done', 'Butterblitz', {'exports': exports}, {'episodes': 2},
            episodes=[{'title': t, 'social': SOCIAL, 'scenes': [scene('S', ['Lena'], [('Lena', 'Hallo')], [p], p)]} for t, p in zip(['Der Löffel', 'Das Müsli'], pics)])
    # measured compute time (timer on tiles and project page); notes are written when a step ends
    for proj, stage, sec in (('c' * 32, 'Animation', 700.4), ('c' * 32, 'Bilder', 54), ('d' * 32, 'Animation', 3725)):
        db.execute('INSERT INTO performance_stages(project,stage,resource,started,seconds,status,detail) VALUES(?,?,?,?,?,?,?)',
                   (proj, stage, 'GPU', '2026-01-01T00:00:00+00:00', sec, 'done', '{}'))
    # blocked: speech check
    project('e' * 32, 'blocked', 'Funkstille', {'resume_state': 'audio_mixing', 'error': 'Nachbearbeitung: SPRACHPRÜFUNG: 1 von 6 Dialogbeiträgen nicht hörbar. Ohne hörbare Stimme: Markus. Folge 1, Szene 3, Figur Markus: „Lass mich los!“ – keine hörbare Sprache an dieser Stelle.'})
    db.commit()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}); errors = []
        page.on('pageerror', lambda e: errors.append(str(e))); page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
        def shot(name, url, full=True, wait=2200):
            page.goto('http://127.0.0.1:8787/' + url); page.wait_for_timeout(wait); page.screenshot(path=str(shots / f'{name}.png'), full_page=full)
        shot('01_neu', '#new', full=False)
        jpg = work / 'vorlage.jpg'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'gradients=s=1200x800:c0=0xe0a060:c1=0x603020:d=1', '-frames:v', '1', str(jpg)], check=True)
        page.click('details.more summary'); page.click('[data-action="add-person"]'); page.wait_for_timeout(300)
        page.set_input_files('input[data-upload="example"]', str(jpg)); page.wait_for_selector('.thumb img', timeout=15000); page.wait_for_timeout(800)
        r.check('JPG als Look-Vorlage übernommen und angezeigt', page.evaluate("[...document.querySelectorAll('.thumbs .thumb img')].filter(i => i.naturalWidth > 0).length") == 1)
        overlaps = page.evaluate('''(() => { const els = [...document.querySelectorAll('details.more .button, details.more .file-pill, details.more .thumb, details.more .input, details.more .icon-remove, details.more .segmented')];
          const r = els.map(e => e.getBoundingClientRect()); let n = 0;
          for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) { if (els[i].contains(els[j]) || els[j].contains(els[i])) continue;
            const w = Math.min(r[i].right, r[j].right) - Math.max(r[i].left, r[j].left), h = Math.min(r[i].bottom, r[j].bottom) - Math.max(r[i].top, r[j].top); if (w > 1 && h > 1) n++; }
          return n; })()''')
        r.check(f'Figuren und Vorlagen: keine Überlappung ({overlaps} Überschneidungen)', overlaps == 0)
        page.locator('details.more').screenshot(path=str(shots / '01b_vorlagen.png'))
        page.click('[data-set="look"][data-value="clay"]'); page.wait_for_timeout(200)
        r.check('Look „Knete“ wählbar', page.locator('#preview').get_attribute('data-look') == 'clay')
        r.check('Startseite: Eingabe und Startknopf sichtbar', page.locator('#idea').is_visible() and page.locator('#create').inner_text() == 'Film starten')
        page.click('[data-set="episodes"][data-value="12"]'); page.click('[data-set="quality"][data-value="draft"]'); page.wait_for_timeout(300)
        r.check('Serie gewählt: Knopftext und Teil-Etikett', page.locator('#create').inner_text() == 'Serie mit 12 Folgen starten' and page.locator('#preview-part').inner_text() == 'Teil 1/12')
        page.screenshot(path=str(shots / '02_neu_serie.png'))
        shot('03_projekte', '#projects')
        r.check('Projektliste: 7 Projekte als Hochkantkacheln', page.locator('.tile').count() == 7)
        r.check('Figurencheck wartet auf Cay (auch mit Autopilot)', 'Wartet auf dich' in page.locator('.tile', has_text='Figurencheck').inner_text())
        r.check('Wartende Projekte stehen vorn', 'Wartet auf dich' in page.locator('.tile').first.inner_text())
        r.check('Timer: Rechenzeit auf den Kacheln', '12:34' in page.locator('.tile', has_text='Der Tresor').inner_text()
                and 'Rechenzeit 1:02:05' in ' '.join(page.locator('.tile', has_text='Butterblitz').inner_text().split()))
        shot('04_bilder_waehlen', '#p=' + 'a' * 32)
        r.check('Bildwahl: Figurenleiste mit 2 geladenen Figurenbildern', page.evaluate("[...document.querySelectorAll('.cast .figure-pic img')].filter(i => i.naturalWidth > 0).length") == 2)
        r.check('Bildwahl: Ziel des Films sichtbar', 'Lena will den letzten Keks retten' in page.locator('.spine').inner_text())
        page.locator('.cast').screenshot(path=str(shots / '04b_figuren.png'))
        page.click('.scene:nth-child(2) .variant >> nth=1'); page.wait_for_timeout(1200)
        page.click('.scene:nth-child(3) .variant >> nth=0'); page.wait_for_timeout(1200)
        r.check('Bildwahl: alle Szenen gewählt, Übernehmen aktiv', page.locator('.dock button').is_enabled())
        page.click('.dock button'); page.wait_for_timeout(1500)
        r.check('Bilder übernommen: Zustand Stimmen', json.loads(page.evaluate("fetch('/api/factory/" + 'a' * 32 + "').then(r=>r.text())"))['state'] in ('voicing', 'blocked'))
        shot('04c_figur_neu', '#p=' + 'f' * 32)
        page.click('[data-action="edit-lines"][data-scene="0"]'); page.wait_for_timeout(500)
        page.fill('#lines-form [data-line="0"][data-key="text"]', 'Hallo, Markus!')
        page.click('#lines-form [data-action="add-line"]'); page.wait_for_timeout(300)
        page.fill('#lines-form [data-line="1"][data-key="text"]', 'Wo ist der Keks?')
        page.click('#lines-form button[type="submit"]'); page.wait_for_timeout(1200)
        said = json.loads(page.evaluate("fetch('/api/factory/" + 'f' * 32 + "').then(r=>r.text())"))['episodes'][0]['scenes'][0]['dialogues']
        page.click('[data-action="edit-lines"][data-scene="2"]'); page.wait_for_timeout(500)
        page.click('#lines-form button[type="submit"]'); page.wait_for_timeout(1200)
        old = json.loads(page.evaluate("fetch('/api/factory/" + 'f' * 32 + "').then(r=>r.text())"))['episodes'][0]['scenes'][2]['dialogues']
        r.check('Text ändern (alte Einzelzeile): Sprechhaltung bleibt', [(x['text'], x['emotion']) for x in old] == [('Hallo.', 'flüsternd')])
        r.check('Text ändern: Sprechhaltung und Pause bleiben, neuer Satz natürlich',
                [(x['text'], x['emotion'], x['pause_after']) for x in said] == [('Hallo, Markus!', 'schreiend', .3), ('Wo ist der Keks?', 'Natürlich', .18)]); print('     ', [(x['text'], x['emotion'], x['pause_after']) for x in said])
        page.once('dialog', lambda dlg: dlg.accept())
        page.click('.cast [data-action="figure-menu"][data-name="Lena"]'); page.wait_for_selector('.menu-row')
        page.click('.menu-row[data-action="cast-redo"]'); page.wait_for_timeout(1500)
        f = json.loads(page.evaluate("fetch('/api/factory/" + 'f' * 32 + "').then(r=>r.text())"))
        scenes = f['episodes'][0]['scenes']
        r.check('Figur neu gestalten: alle Lena-Szenen neu, Markus-Szene bleibt',
                f['state'] == 'pictures' and f['plan']['cast'][0].get('design_round') == 1 and 'Lena' not in f.get('cast_refs', {})
                and scenes[0]['selected'] is None and scenes[2]['selected'] is None and scenes[1]['selected'] is not None)
        shot('04d_figurencheck', '#p=' + '1' * 32)
        r.check('Figurencheck: Überschrift, 2 Figuren, Prüfzeile', 'Prüf deine Figuren' in page.locator('.next h2').inner_text()
                and page.locator('.cast .figure').count() == 2 and '118 Wörter' in page.locator('.check-line').inner_text())
        own = work / 'eigenes_bild.jpg'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0xff6b6b:s=600x900:d=1', '-frames:v', '1', str(own)], check=True)
        page.click('.cast [data-action="figure-menu"][data-name="Markus"]'); page.wait_for_selector('.menu-row')
        page.set_input_files('.menu input[data-upload="cast"][data-name="Markus"]', str(own)); page.wait_for_timeout(2500)
        g = json.loads(page.evaluate("fetch('/api/factory/" + '1' * 32 + "').then(r=>r.text())"))
        markus = next((p for p in g['idea']['participants'] if p['name'] == 'Markus'), {})
        r.check('Eigenes Figurenbild: übernommen, Figur wird neu aufgebaut', bool(markus.get('image')) and 'Markus' not in g.get('cast_refs', {})
                and (g['state'] == 'pictures' or g.get('resume_state') == 'pictures'))
        db.execute("UPDATE factory_runs SET state='cast_review', document=json_set(document,'$.state','cast_review','$.cast_refs',json(?)) WHERE id=?", (json.dumps({'Lena': str(figure), 'Markus': str(figure)}), '1' * 32)); db.commit()
        page.goto('http://127.0.0.1:8787/classic#project=' + '1' * 32); page.wait_for_timeout(2500)
        r.check('Klassische Ansicht: Figurencheck mit Weiter-Knopf und Link', page.locator('[data-action="cast-approve-classic"]').count() == 1
                and page.locator('a[href="/#p=' + '1' * 32 + '"]').count() == 1)
        page.goto('http://127.0.0.1:8787/#p=' + '1' * 32); page.wait_for_timeout(2000)
        page.click('[data-action="cast-approve"]'); page.wait_for_timeout(1500)
        g = json.loads(page.evaluate("fetch('/api/factory/" + '1' * 32 + "').then(r=>r.text())"))
        r.check('Figuren freigegeben: Szenenbilder sind dran', g['state'] in ('pictures', 'blocked') and bool(g.get('cast_approval')))
        shot('05_ton', '#p=' + 'b' * 32)
        page.click('.line-row .play >> nth=0'); page.wait_for_timeout(600)
        r.check('Ton: Satz abspielbar (Knopf zeigt Pause)', 'path' in page.locator('.line-row .play >> nth=0').inner_html())
        shot('06_animation', '#p=' + 'c' * 32, wait=3500)
        r.check('Animation: Fortschritt 2 von 12 und Hänger-Hinweis', '2 von 12' in page.locator('#progress-slot').inner_text() and page.locator('.stall').count() == 1)
        r.check('Timer: Projektseite zeigt die Rechenzeit', '12:34' in page.locator('#clock-slot').inner_text())
        shot('07_fertig', '#p=' + 'd' * 32)
        r.check('Fertig: 2 Folgen mit Beschreibung', page.locator('.film video').count() == 2 and page.locator('.caption-box').count() >= 2)
        shot('08_angehalten', '#p=' + 'e' * 32)
        r.check('Angehalten: klare Überschrift und Fortsetzen', 'nicht hörbar' in page.locator('.next h2').inner_text() and page.locator('.next [data-action="resume"]').count() == 1)
        r.check('Kein Reiter „Filme“ mehr', page.locator('[data-nav="films"]').count() == 0)
        page.goto('http://127.0.0.1:8787/#p=' + 'd' * 32); page.wait_for_selector('.film video', timeout=15000)
        for _ in range(60):
            if page.evaluate("[...document.querySelectorAll('.film video')].every(v => v.readyState >= 1)"): break
            page.wait_for_timeout(250)
        widths = page.evaluate("[...document.querySelectorAll('.film video')].map(v => v.getBoundingClientRect().width)")
        r.check(f'Videos 1080×1920 bleiben in ihrer Kachel ({[round(w) for w in widths]} px)', widths and max(widths) < 320)
        page.emulate_media(color_scheme='dark'); shot('10_neu_dunkel', '#new', full=False); shot('11_projekt_dunkel', '#p=' + 'a' * 32)
        page.set_viewport_size({'width': 390, 'height': 844}); page.emulate_media(color_scheme='light')
        shot('12_handy_neu', '#new'); shot('13_handy_projekte', '#projects', full=False)
        r.check('Handy: keine waagerechte Scrollleiste', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        page.set_viewport_size({'width': 1280, 'height': 900}); shot('14_neu_anlegen', '#new', full=False)
        page.click('[data-action="settings"]'); page.wait_for_timeout(4000); page.screenshot(path=str(shots / '16_einrichtung.png'))
        r.check('Einrichtung: Prüfliste und Figurentausch-Link', page.locator('#sheet .check-row').count() >= 3 and page.locator('#sheet a[href="/classic#remix"]').count() == 1)
        r.check('Einrichtung: Turbo-Bereich mit Einrichten-Knopf', page.locator('#sheet [data-action="turbo-setup"]').count() == 1)
        page.click('#sheet [data-action="close"]'); page.wait_for_timeout(300)
        page.fill('#idea', 'Ein Hamster plant den perfekten Raubzug in der Küche, doch die Katze ist schneller.'); page.click('[data-set="duration"][data-value="15"]')
        page.click('#create'); page.wait_for_timeout(2500)
        r.check('Film anlegen: Projektseite öffnet sich', page.url.split('#')[-1].startswith('p=') and page.locator('.steps').count() == 1)
        page.screenshot(path=str(shots / '15_nach_anlegen.png'), full_page=True)
        r.check('Keine JavaScript-Fehler', not [e for e in errors if 'Failed to load resource' not in e]); print('   ', errors[:3])
        browser.close()
finally:
    studio.close()
r.done()
