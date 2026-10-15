"""0.18 cut in the browser: reaction and establishing shots in the picture choice and the line editor.

Run: python tests/manual/cut_ui_check.py <empty dir>   (screenshots in <dir>/shots)
Seeds one project planned with screenplay policy 14 (real PNG files, no AI models): a speaking
shot, a reaction (SpongeBob listens, Mr. Krabs is heard from off-screen), a wide establishing
shot and the next speaking shot. Checks the labels, that the line editor offers only the voice
from off-screen in a reaction and nobody in a wide shot, and that the server refuses the rest.
"""
import hashlib, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report(); db = studio.db
RID = '7' * 32
COLORS = [('0xffe066', '0xc49a00'), ('0xffd23f', '0x7a5c00'), ('0x2a6f97', '0x013a63'), ('0xd03030', '0x401010')]


def picture(sid, n):
    out = studio.root / '01_Projekte/Studio' / RID / '02_Bilder' / f'{sid}.png'; out.parent.mkdir(parents=True, exist_ok=True)
    a, b = COLORS[n % len(COLORS)]
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'gradients=s=576x1024:c0={a}:c1={b}:x0=0:y0=0:x1=576:y1=1024:d=1',
                    '-frames:v', '1', str(out)], check=True)
    db.execute("INSERT INTO factory_steps(id,run_id,step_key,status,prompt_id,graph,output,sha256) VALUES(?,?,?,?,?,?,?,?)",
               (sid, RID, f'image:0:{n}:0:0', 'done', None, '{}', str(out), hashlib.sha256(out.read_bytes()).hexdigest()))
    return sid


def scene(n, kind, title, action, cast, lines, camera, **extra):
    sid = picture(f'{n + 1:032x}', n)
    return {'title': title, 'action': action, 'location': 'Düstere Höhle', 'camera': camera, 'cast': cast, 'kind': kind,
            'dialogues': [{'speaker': s, 'text': t, 'emotion': e, 'pause_after': .15} for s, t, e in lines], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'attempt', 'because': 'x', 'round': 0, 'selected': sid, 'render_seconds': 4.0, 'seconds': 4.0,
            'variants': [{'id': sid, 'key': f'image:0:{n}:0:0'}], **extra}


CAST = [{'name': 'SpongeBob', 'appearance': 'yellow sponge', 'personality': 'eager', 'voice_preset': 'young_man'},
        {'name': 'Mr. Krabs', 'appearance': 'red crab', 'personality': 'greedy', 'voice_preset': 'man'}]
SCENES = [
    scene(0, 'line', 'SpongeBob: Herr Krabs, ich hab nur noch diese paar Münzen.', 'SpongeBob zahlt Mr. Krabs Schutzgeld.', ['SpongeBob'],
          [('SpongeBob', 'Herr Krabs, ich hab nur noch diese paar Münzen.', 'flehend'), ('SpongeBob', 'Bitte, mehr hab ich wirklich nicht!', 'flehend')], 'medium shot'),
    scene(1, 'reaction', 'Reaktion: SpongeBob hört Mr. Krabs zu', 'SpongeBob hört schweigend zu, die Stimme von Mr. Krabs kommt aus dem Off.', ['SpongeBob'],
          [('Mr. Krabs', 'Ich nehme nur, was mir zusteht. Das ist doch fair.', 'wütend')], 'close-up', voice_of='Mr. Krabs', emotion='ängstlich'),
    scene(2, 'establish', 'Totale: Höhleneingang mit Lieferwagen', 'Plankton fährt mit einem Lieferwagen vor.', ['Mr. Krabs'], [], 'wide establishing shot'),
    scene(3, 'line', 'Mr. Krabs: Raus aus meiner Höhle!', 'Mr. Krabs zeigt auf den Ausgang.', ['Mr. Krabs'], [('Mr. Krabs', 'Raus aus meiner Höhle, du winziger Wurm!', 'wütend')], 'low angle medium shot'),
]


try:
    figures = {}
    for name, (a, b) in (('SpongeBob', ('0xfff07a', '0xd9b300')), ('Mr. Krabs', ('0xff6b5b', '0x8a1c12'))):
        figures[name] = studio.root / '01_Projekte/Studio' / RID / '02_Bilder' / f'figur_{name[:3]}.png'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'gradients=s=864x1536:c0={a}:c1={b}:d=1', '-frames:v', '1', str(figures[name])], check=True)
    studio.project(RID, 'image_review', {'title': 'Krusty-Versteck', 'cast_refs': {k: str(v) for k, v in figures.items()}, 'plan': {'title': 'Krusty-Versteck', 'cast': CAST, 'style': 'clay', 'mood': 'playful', 'episodes': [{'title': 'x'}]},
                   'episodes': [{'title': 'Der Einbruch im Krusty-Versteck', 'scenes': SCENES, 'story_policy': 14, 'dialogue_mode': 'rich', 'script': 'screenplay',
                                 'screenplay_stats': {'words': 38, 'lines': 5, 'actions': 0, 'shots': 4, 'reactions': 1, 'establishing': 1, 'lip_sync': 2}}]},
                   {'idea': 'SpongeBob zahlt Schutzgeld, Plankton kommt dazu.'}, paused=1)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}); errors = []
        page.on('pageerror', lambda e: errors.append(str(e))); page.on('console', lambda m: m.type == 'error' and errors.append(m.text))

        def open_project(width, scheme, name):
            page.set_viewport_size({'width': width, 'height': 900 if width > 500 else 844}); page.emulate_media(color_scheme=scheme)
            page.goto(f'{studio.url}/#p={RID}'); page.wait_for_selector('.scene .scene-role', timeout=15000); page.wait_for_timeout(900)
            page.screenshot(path=str(shots / f'{name}.png'), full_page=True)

        open_project(1280, 'light', '01_szenen_1280_hell')
        roles = [' '.join(t.split()) for t in page.locator('.scene .scene-role').all_inner_texts()]
        r.check(f'Beschriftung: Reaktion mit Stimme aus dem Off und Totale ({roles})',
                roles == ['Reaktion Stimme von Mr. Krabs aus dem Off', 'Totale zeigt den neuen Ort'])
        r.check('Sprechszenen ohne Zusatzbeschriftung', page.locator('.scene:nth-child(1) .scene-role').count() == 0 and page.locator('.scene:nth-child(4) .scene-role').count() == 0)
        r.check('Reaktion zeigt den Satz aus dem Off', 'Mr. Krabs: Ich nehme nur' in ' '.join(page.locator('.scene:nth-child(2) .line').all_inner_texts()))

        page.click('[data-action="edit-lines"][data-scene="1"]'); page.wait_for_selector('#lines-form'); page.wait_for_timeout(300)
        page.locator('#sheet').screenshot(path=str(shots / '02_reaktion_text.png'))
        options = page.locator('#lines-form select[data-key="speaker"] >> nth=0').locator('option').all_inner_texts()
        r.check(f'Text ändern (Reaktion): nur die Stimme aus dem Off wählbar ({options})', options == ['Mr. Krabs'])
        r.check('Text ändern (Reaktion): Hinweis, dass SpongeBob nur zuhört', 'SpongeBob hört hier nur zu' in page.locator('#lines-form').inner_text())
        page.click('#lines-form [data-action="add-line"]'); page.wait_for_timeout(300)
        page.fill('#lines-form [data-line="1"][data-key="text"]', 'Und jetzt her mit dem Rest!')
        page.locator('#sheet').screenshot(path=str(shots / '02b_reaktion_zwei_saetze.png'))
        page.click('#lines-form button[type="submit"]'); page.wait_for_timeout(1500)
        saved = studio.call(f'/api/factory/{RID}')[1]['episodes'][0]['scenes'][1]
        r.check('Reaktion gespeichert: beide Sätze von Mr. Krabs, Bild bleibt',
                [(l['speaker'], l['text']) for l in saved['dialogues']] == [('Mr. Krabs', 'Ich nehme nur, was mir zusteht. Das ist doch fair.'), ('Mr. Krabs', 'Und jetzt her mit dem Rest!')]
                and saved['kind'] == 'reaction' and saved['selected'] == f'{2:032x}')

        page.click('[data-action="edit-lines"][data-scene="2"]'); page.wait_for_selector('#lines-form'); page.wait_for_timeout(300)
        page.locator('#sheet').screenshot(path=str(shots / '03_totale_text.png'))
        r.check('Text ändern (Totale): kein Satz- und kein Speichern-Knopf, klarer Hinweis', page.locator('#lines-form [data-action="add-line"]').count() == 0
                and page.locator('#lines-form button[type="submit"]').count() == 0 and 'Hier spricht niemand' in page.locator('#lines-form').inner_text())
        page.click('#sheet [data-action="close"]'); page.wait_for_timeout(300)

        def put(scene, speaker):
            s = studio.call(f'/api/factory/{RID}')[1]['episodes'][0]['scenes'][scene]
            return studio.call(f'/api/factory/{RID}/dialogues', {'episode': 0, 'scene': scene, 'action': s['action'],
                               'dialogues': [{'speaker': speaker, 'text': 'Ich sag auch was!', 'emotion': 'Natürlich', 'pause_after': .18}]}, 'PUT')
        code, body = put(1, 'SpongeBob')
        r.check(f'Server: Zuhörer in der Reaktion spricht nicht ({code}: {body.get("detail")})', code == 400 and 'hört SpongeBob nur zu' in body.get('detail', ''))
        code, body = put(2, 'Mr. Krabs')
        r.check(f'Server: Totale bleibt ohne Text ({code}: {body.get("detail")})', code == 400 and 'Totale' in body.get('detail', ''))

        open_project(1280, 'dark', '04_szenen_1280_dunkel')
        open_project(390, 'light', '05_szenen_390_hell')
        r.check('Handy: keine waagerechte Scrollleiste', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        open_project(390, 'dark', '06_szenen_390_dunkel')
        page.click('[data-action="edit-lines"][data-scene="1"]'); page.wait_for_selector('#lines-form'); page.wait_for_timeout(300)
        page.screenshot(path=str(shots / '07_reaktion_text_390_dunkel.png'))
        r.check('Keine JavaScript-Fehler', not [e for e in errors if 'Failed to load resource' not in e]); print('   ', errors[:3])
        browser.close()
finally:
    studio.close()
r.done()
