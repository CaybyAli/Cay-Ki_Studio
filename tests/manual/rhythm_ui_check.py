"""0.20 rhythm in the browser: over-the-shoulder shots, listeners and details in the picture choice and the line editor.

Run: python tests/manual/rhythm_ui_check.py <empty dir>   (screenshots in <dir>/shots)
Seeds one project pinned with shot_policy 20 (real PNG files, no AI models): Sia speaks over Mira's shoulder, Mira
listens while Sia's voice continues (Sia from behind in the foreground), a one-second detail of the photo, Mira speaks.
Checks the labels, the check line, that the line editor offers nobody in a detail and that the server refuses it,
and that the new app asks for the rhythm cut when it creates a film (project pinned with 20).
"""
import hashlib, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report(); db = studio.db
RID = '8' * 32
COLORS = [('0xff7aa2', '0x8a1c40'), ('0xffd23f', '0x7a5c00'), ('0x2a6f97', '0x013a63'), ('0x7ad38a', '0x1c6a2a')]


def picture(sid, n):
    out = studio.root / '01_Projekte/Studio' / RID / '02_Bilder' / f'{sid}.png'; out.parent.mkdir(parents=True, exist_ok=True)
    a, b = COLORS[n % len(COLORS)]
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'gradients=s=576x1024:c0={a}:c1={b}:x0=0:y0=0:x1=576:y1=1024:d=1',
                    '-frames:v', '1', str(out)], check=True)
    db.execute("INSERT INTO factory_steps(id,run_id,step_key,status,prompt_id,graph,output,sha256) VALUES(?,?,?,?,?,?,?,?)",
               (sid, RID, f'image:0:{n}:0:0', 'done', None, '{}', str(out), hashlib.sha256(out.read_bytes()).hexdigest()))
    return sid


def scene(n, kind, title, action, cast, lines, camera, shot, **extra):
    sid = picture(f'{n + 1:032x}', n)
    return {'title': title, 'action': action, 'location': 'Gartenbank', 'camera': camera, 'cast': cast, 'kind': kind,
            'dialogues': [{'speaker': s, 'text': t, 'emotion': e, 'pause_after': .15} for s, t, e in lines], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'attempt', 'because': 'x', 'round': 0, 'selected': sid, 'render_seconds': 2.0, 'seconds': 2.0,
            'variants': [{'id': sid, 'key': f'image:0:{n}:0:0', 'shot': shot}], **extra}


CAST = [{'name': 'Sia', 'appearance': 'pineapple head', 'personality': 'fearless', 'voice_preset': 'woman'},
        {'name': 'Mira', 'appearance': 'strawberry head', 'personality': 'sweet', 'voice_preset': 'woman'}]
SCENES = [
    scene(0, 'line', 'Sia: Hier. Ein Foto von Ben und Valentina.', 'Sia zeigt Mira das Handy.', ['Sia'], [('Sia', 'Hier. Ein Foto von Ben und Valentina.', 'ruhig')],
          'medium shot', 'ots', shoulder='Mira'),
    scene(1, 'reaction', 'Reaktion: Mira hört Sia zu', 'Mira hört schweigend zu, die Stimme von Sia kommt aus dem Off.', ['Mira'],
          [('Sia', 'Zwei Tage vor dem Einzug.', 'ruhig')], 'close-up', 'ots', voice_of='Sia', emotion='flüsternd', shoulder='Sia'),
    scene(2, 'action', 'Detail: Foto bei Sia', 'Detail: Foto bei Sia', ['Sia'], [], 'extreme close-up insert', 'ecu', insert='prop', prop='Foto', mood='ruhig'),
    scene(3, 'line', 'Mira: Sie halten Händchen.', 'Mira spricht.', ['Mira'], [('Mira', 'Sie halten Händchen.', 'flüsternd')], 'close-up', 'cu'),
]


try:
    figures = {}
    for name, (a, b) in (('Sia', ('0xfff07a', '0xd9b300')), ('Mira', ('0xff6b5b', '0x8a1c12'))):
        figures[name] = studio.root / '01_Projekte/Studio' / RID / '02_Bilder' / f'figur_{name[:3]}.png'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'gradients=s=864x1536:c0={a}:c1={b}:d=1', '-frames:v', '1', str(figures[name])], check=True)
    studio.project(RID, 'image_review', {'title': 'Villa der süßen Lügen', 'shot_policy': 20, 'cast_refs': {k: str(v) for k, v in figures.items()},
                   'plan': {'title': 'Villa', 'cast': CAST, 'style': '3D', 'mood': 'drama', 'episodes': [{'title': 'x'}]},
                   'episodes': [{'title': 'Die Neue kennt das Geheimnis', 'scenes': SCENES, 'story_policy': 14, 'dialogue_mode': 'rich', 'script': 'screenplay',
                                 'screenplay_stats': {'words': 15, 'lines': 3, 'actions': 0, 'shots': 4, 'reactions': 1, 'establishing': 0, 'lip_sync': 2,
                                                      'inserts': 1, 'shoulder': 2}}]},
                   {'idea': 'Sia zeigt Mira ein Foto.'}, paused=1)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}); errors = []
        page.on('pageerror', lambda e: errors.append(str(e))); page.on('console', lambda m: m.type == 'error' and errors.append(m.text))

        def open_project(width, scheme, name):
            page.set_viewport_size({'width': width, 'height': 900 if width > 500 else 844}); page.emulate_media(color_scheme=scheme)
            page.goto(f'{studio.url}/#p={RID}'); page.wait_for_selector('.scene .scene-role', timeout=15000); page.wait_for_timeout(900)
            page.screenshot(path=str(shots / f'{name}.png'), full_page=True)

        open_project(1280, 'light', '01_rhythmus_1280_hell')
        roles = [' '.join(t.split()) for t in page.locator('.scene .scene-role').all_inner_texts()]
        r.check(f'Beschriftung: über die Schulter, Reaktion mit Figur von hinten, Detail ({roles})',
                roles == ['Über die Schulter Mira von hinten im Vordergrund', 'Reaktion Stimme von Sia aus dem Off · Sia von hinten im Vordergrund',
                          'Detail Foto in Großaufnahme, etwa eine Sekunde'])
        line = page.locator('.check-line').first.inner_text() if page.locator('.check-line').count() else ''
        r.check(f'Prüfzeile nennt Reaktionen und Details ({line})', '1 Reaktion ·' in line and line.endswith('1 Detail'))

        page.click('[data-action="edit-lines"][data-scene="2"]'); page.wait_for_selector('#lines-form'); page.wait_for_timeout(300)
        page.locator('#sheet').screenshot(path=str(shots / '02_detail_text.png'))
        r.check('Text ändern (Detail): kein Satz- und kein Speichern-Knopf, klarer Hinweis', page.locator('#lines-form [data-action="add-line"]').count() == 0
                and page.locator('#lines-form button[type="submit"]').count() == 0 and 'Dieses Detail dauert etwa eine Sekunde' in page.locator('#lines-form').inner_text())
        page.click('#sheet [data-action="close"]'); page.wait_for_timeout(300)
        s = studio.call(f'/api/factory/{RID}')[1]['episodes'][0]['scenes'][2]
        code, body = studio.call(f'/api/factory/{RID}/dialogues', {'episode': 0, 'scene': 2, 'action': s['action'],
                                 'dialogues': [{'speaker': 'Sia', 'text': 'Ich sag auch was!', 'emotion': 'Natürlich', 'pause_after': .18}]}, 'PUT')
        r.check(f'Server: im Detail spricht niemand ({code}: {body.get("detail")})', code == 400 and 'Detail' in body.get('detail', ''))

        open_project(1280, 'dark', '03_rhythmus_1280_dunkel')
        open_project(390, 'light', '04_rhythmus_390_hell')
        r.check('Handy: keine waagerechte Scrollleiste', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        open_project(390, 'dark', '05_rhythmus_390_dunkel')

        # The new app asks for the rhythm cut when it creates a film: the request carries rhythm 20, the project is pinned with 20.
        app = (Path(__file__).resolve().parents[2] / 'cay_studio_app/web/app2/app.js').read_text(encoding='utf-8')
        r.check('Neue App fragt bei beiden Wegen (KI-Drehbuch, Mein Drehbuch) nach dem Rhythmus-Schnitt',
                app.count('rhythm: 20') + app.count('body.rhythm = 20') == 2)
        code, made = studio.call('/api/factory', {'request_key': '9' * 32, 'idea': 'Zwei Kollegen streiten um den letzten Keks.', 'duration': 30,
                                                  'episodes': 1, 'characters': 'invent', 'rhythm': 20})
        code_old, old = studio.call('/api/factory', {'request_key': 'a' * 32, 'idea': 'Zwei Kollegen streiten um den letzten Keks.', 'duration': 30,
                                                     'episodes': 1, 'characters': 'invent'})
        r.check(f'Server: neue App -> shot_policy 20, alte Anfrage -> 19 ({made.get("shot_policy")}, {old.get("shot_policy")})',
                code == 200 and code_old == 200 and made.get('shot_policy') == 20 and old.get('shot_policy') == 19 and 'rhythm' not in made['idea'])
        r.check('Keine JavaScript-Fehler', not [e for e in errors if 'Failed to load resource' not in e]); print('   ', errors[:3])
        browser.close()
finally:
    studio.close()
r.done()
