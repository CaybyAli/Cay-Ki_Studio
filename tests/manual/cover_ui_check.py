"""Title card (0.18) in the browser: choice in the image review, new variants, compose control, download.

Run: python tests/manual/cover_ui_check.py <empty dir>   (screenshots in <dir>/shots)
Key art and films are FFmpeg pictures, no AI models: this checks the flow and the
lettering on the real server, not the look of a real FLUX key art.
"""
import hashlib, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import APP, Studio, Report
sys.path.insert(0, str(APP))
import cover  # noqa: E402

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report(); db = studio.db
ids = iter(f'{i:032x}' for i in range(1, 400))


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def keyart(path, a, b):
    """A poster-like test picture: gradient sky, three figures in the lower two thirds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    boxes = ','.join(f'drawbox=x={x}:y={y}:w=180:h={1536 - y - 120}:color={c}@1:t=fill' for x, y, c in ((90, 760, '0xffd23f'), (342, 700, '0xee4266'), (594, 780, '0x3bceac')))
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'gradients=s=864x1536:c0={a}:c1={b}:x0=0:y0=0:x1=0:y1=1536:d=1',
                    '-vf', boxes, '-frames:v', '1', str(path)], check=True)
    return path


def step(rid, key, path):
    sid = next(ids)
    db.execute("INSERT INTO factory_steps(id,run_id,step_key,status,prompt_id,graph,output,sha256) VALUES(?,?,?,?,?,?,?,?)",
               (sid, rid, key, 'done', None, '{}', str(path), sha(path)))
    return sid


def scene(rid, ei, si, who, line):
    v = [step(rid, f'image:{ei}:{si}:0:{k}', keyart(studio.root / '01_Projekte/Studio' / rid / f'02_Bilder/s{ei}{si}{k}.png', '0x134e5e', '0x71b280')) for k in range(2)]
    return {'title': f'{who} spricht', 'action': f'{who} steht am Hafen.', 'location': 'Hafen', 'camera': 'Halbnah', 'cast': [who],
            'dialogues': [{'speaker': who, 'text': line, 'emotion': 'ruhig', 'pause_after': .18}], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'problem', 'because': 'x', 'round': 0, 'selected': v[0], 'render_seconds': 4, 'seconds': 4,
            'variants': [{'id': x, 'key': f'image:{ei}:{si}:0:{k}'} for k, x in enumerate(v)]}


CAST = [{'name': 'Phineas', 'appearance': 'boy', 'personality': 'clever', 'voice_preset': 'child_boy'},
        {'name': 'Ferb', 'appearance': 'boy', 'personality': 'quiet', 'voice_preset': 'child_boy'}]


def project(rid, state, title, episodes, cover_position, policy=True, paused=1, extra=None):
    art = [step(rid, f'cover:0:0:{k}', keyart(studio.root / '01_Projekte/Studio' / rid / f'02_Bilder/cover{k}.png', c0, c1))
           for k, (c0, c1) in enumerate((('0x0f2027', '0x2c5364'), ('0x833ab4', '0xfd1d1d')))] if policy else []
    doc = {'title': title, 'plan': {'title': title, 'cast': CAST, 'style': 'clay', 'mood': 'playful'}, 'episodes': episodes,
           'cast_refs': {}, **({'edit_policy': 18, 'cover': {'variants': [{'id': x, 'key': f'cover:0:0:{k}'} for k, x in enumerate(art)],
                                                             'selected': None, 'round': 0, 'cast': ['Phineas', 'Ferb']}} if policy else {}), **(extra or {})}
    studio.project(rid, state, doc, {'idea': 'Phineas und Ferb lösen einen Fall im Hafen.', 'episodes': len(episodes),
                                     **({'cover': cover_position} if cover_position else {})}, paused)
    return art


def doc(page, rid): return json.loads(page.evaluate(f"fetch('/api/factory/{rid}').then(r => r.text())"))


try:
    A, B, C, D = 'a' * 32, 'b' * 32, 'c' * 32, 'd' * 32
    art_a = project(A, 'image_review', 'Phineas in the Hood', [{'title': f'Folge {e + 1}', 'scenes': [scene(A, e, s, w, 'Wo ist er?') for s, w in enumerate(('Phineas', 'Ferb'))]} for e in range(2)], 'start', paused=0)
    art_b = project(B, 'image_review', 'Der Hafen', [{'title': 'Der Hafen', 'scenes': [scene(B, 0, 0, 'Phineas', 'Los!')]}], 'after_hook')
    project(C, 'image_review', 'Alter Film', [{'title': 'Alter Film', 'scenes': [scene(C, 0, 0, 'Phineas', 'Hallo.')]}], None, policy=False)
    # Finished series with a lettered title card next to each film
    films = studio.root / '03_Fertige_Videos/Studio' / D; exports = []
    for e in range(2):
        out = films / f'Folge_{e + 1:02}.mp4'; out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'gradients=s=1080x1920:c0=0x1e3c72:c1=0xfd1d1d:d=2', '-f', 'lavfi', '-i', 'sine=frequency=330:duration=2',
                        '-shortest', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(out)], check=True)
        poster = films / f'Cover_Folge_{e + 1:02}.png'
        cover.letter(keyart(work / f'art{e}.png', '0x0f2027', '0x2c5364'), poster, 'Phineas in the Hood', f'Teil {e + 1}')
        exports.append({'file': str(out), 'sha256': sha(out), 'episode': e, 'seconds': 2, 'fps': 25, 'title': f'Folge {e + 1}',
                        'cover': {'file': str(poster), 'sha256': sha(poster), 'position': 'start', 'seconds': 1.0}})
    project(D, 'done', 'Phineas in the Hood', [{'title': f'Folge {e + 1}', 'scenes': [scene(D, e, 0, 'Phineas', 'Hallo.')]} for e in range(2)], 'start', extra={'exports': exports})
    db.commit()

    code, refused = studio.call(f'/api/factory/{A}/approve-images', {'revision': studio.call(f'/api/factory/{A}')[1]['revision']})
    r.check('Ohne gewähltes Titelbild: Freigabe abgelehnt mit klarem Grund', code == 409 and refused.get('detail') == 'Wähle zuerst ein Titelbild.')

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}); errors = []
        page.on('pageerror', lambda e: errors.append(str(e))); page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
        base = studio.url + '/'

        # Image review with a title card: lettered previews, choice, approval
        page.goto(base + '#p=' + A); page.wait_for_selector('.cover .variant img')
        for _ in range(60):   # the lettered previews are rendered on first request (CSP forbids wait_for_function)
            if page.evaluate("[...document.querySelectorAll('.cover .variant img')].every(i => i.complete && i.naturalWidth > 0)"): break
            page.wait_for_timeout(500)
        sizes = page.evaluate("[...document.querySelectorAll('.cover .variant img')].map(i => [i.naturalWidth, i.naturalHeight])")
        r.check('Titelbild-Karte über den Szenen, zwei Varianten mit Schrift (1080 × 1920 statt Rohbild 864 × 1536)',
                sizes == [[1080, 1920], [1080, 1920]] and page.evaluate("(document.querySelector('.cover').compareDocumentPosition(document.querySelector('.scenes')) & 4) !== 0"))
        r.check('Text: erste Sekunde, Kanal, Serie mit Teil-Hinweis', 'Die erste Sekunde deines Films.' in page.locator('.cover').inner_text()
                and 'Gleiches Bild für alle 2 Folgen' in page.locator('.cover').inner_text())
        r.check('Übernehmen gesperrt, Dock nennt das fehlende Titelbild', page.locator('.dock button').is_disabled() and 'Titelbild fehlt' in page.locator('.dock').inner_text()
                and page.locator('.next [data-action="approve-images"]').is_disabled())
        page.screenshot(path=str(shots / '01_titelbild_wahl.png'), full_page=True)
        page.locator('.cover').screenshot(path=str(shots / '01b_titelbild_karte.png'))
        page.click('.cover .variant >> nth=1'); page.wait_for_timeout(900)
        r.check('Variante 2 gewählt: Haken, gespeichert, Übernehmen aktiv', page.locator('.cover .variant[aria-pressed="true"]').count() == 1
                and doc(page, A)['cover']['selected'] == art_a[1] and page.locator('.dock button').is_enabled() and 'Titelbild 2 gewählt' in page.locator('.cover').inner_text())
        page.locator('.cover').screenshot(path=str(shots / '02_titelbild_gewaehlt.png'))
        page.emulate_media(color_scheme='dark'); page.wait_for_timeout(300)
        page.locator('.cover').screenshot(path=str(shots / '03_titelbild_dunkel.png')); page.emulate_media(color_scheme='light')
        page.set_viewport_size({'width': 390, 'height': 844}); page.wait_for_timeout(400)
        page.screenshot(path=str(shots / '04_titelbild_handy.png'), full_page=True)
        r.check('Handy: keine waagerechte Scrollleiste', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        page.emulate_media(color_scheme='dark'); page.wait_for_timeout(300)
        page.locator('.cover').screenshot(path=str(shots / '04b_titelbild_handy_dunkel.png')); page.emulate_media(color_scheme='light')
        page.set_viewport_size({'width': 1280, 'height': 900})
        page.click('.dock button'); page.wait_for_timeout(1200)
        r.check('Freigabe mit Titelbild: Bilder übernommen', doc(page, A)['state'] != 'image_review' and doc(page, A)['image_approval'])

        # New variants with a note (paused project: the worker does not draw)
        page.goto(base + '#p=' + B); page.wait_for_selector('.cover .variant img')
        r.check('Nach dem Einstieg: eigener Text', 'Eine Sekunde nach der ersten Einstellung.' in page.locator('.cover').inner_text()
                and 'Folgen' not in page.locator('.cover').inner_text())
        page.click('[data-action="cover-revise"]'); page.wait_for_selector('#cover-revise-form')
        page.fill('#cover-revise-form textarea', 'Beide näher zusammen'); page.screenshot(path=str(shots / '05_neue_titelbilder.png'))
        page.click('#cover-revise-form [type="submit"]'); page.wait_for_timeout(1000)
        b = doc(page, B)
        r.check('Neue Titelbilder: neue Runde, Wunsch gespeichert, Studio zeichnet', b['state'] == 'pictures' and b['cover']['image_rounds'] == [1, 1]
                and b['cover']['note'] == 'Beide näher zusammen' and not b['cover']['selected'] and b['cover']['active_variants'] == [])
        r.check('Karte zeigt „Titelbild entsteht“', page.locator('.cover .frame-empty', has_text='Titelbild entsteht').count() == 2)
        page.locator('.cover').screenshot(path=str(shots / '06_titelbild_entsteht.png'))

        # A project from before 0.18: no card, approval as before
        page.goto(base + '#p=' + C); page.wait_for_selector('.scenes .variant')
        r.check('Altes Projekt: keine Titelbild-Karte, Übernehmen aktiv', page.locator('.cover').count() == 0 and page.locator('.dock button').is_enabled()
                and 'Titelbild' not in page.locator('.dock').inner_text())

        # Done: download the title card of each episode
        page.goto(base + '#p=' + D); page.wait_for_selector('.film')
        links = page.locator('.film a', has_text='Titelbild herunterladen')
        head = page.evaluate("fetch(document.querySelector('.film a[href*=\"/cover/export/1\"]').href).then(r => [r.status, r.headers.get('content-type'), r.headers.get('content-disposition')])")
        r.check('Fertig: „Titelbild herunterladen“ je Folge, liefert Cover_Folge_02.png', links.count() == 2 and head[0] == 200 and head[1] == 'image/png' and 'Cover_Folge_02.png' in (head[2] or ''))
        page.screenshot(path=str(shots / '07_fertig_download.png'), full_page=True)

        # Compose: the switch and what a new film sends
        page.goto(base + '#new'); page.wait_for_timeout(500); page.click('details.more summary')
        group = page.locator('details.more .group', has_text='Titel und Musik')
        r.check('Neuer Film: Titelbild „Am Anfang“ vorgewählt mit Kanal-Hinweis', page.locator('[data-set="cover"][data-value="start"]').get_attribute('aria-pressed') == 'true'
                and 'TikTok zeigt das erste Bild' in page.locator('#cover-hint').inner_text())
        group.screenshot(path=str(shots / '08_neuer_film_titelbild.png'))
        page.click('[data-set="cover"][data-value="after_hook"]'); page.wait_for_timeout(200)
        r.check('Umschalten: Hinweis passt, Entwurf gespeichert', 'Erst die erste Einstellung' in page.locator('#cover-hint').inner_text()
                and page.evaluate("JSON.parse(localStorage.getItem('cay-draft')).cover") == 'after_hook')
        page.emulate_media(color_scheme='dark'); page.wait_for_timeout(300); group.screenshot(path=str(shots / '08b_neuer_film_titelbild_dunkel.png')); page.emulate_media(color_scheme='light')
        page.set_viewport_size({'width': 390, 'height': 844}); page.wait_for_timeout(300)
        group.screenshot(path=str(shots / '08c_neuer_film_titelbild_handy.png'))
        r.check('Handy (neuer Film): keine waagerechte Scrollleiste', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        page.set_viewport_size({'width': 1280, 'height': 900})
        page.fill('#idea', 'Phineas und Ferb suchen im Hafen einen verschwundenen Schatz.')
        with page.expect_response(lambda x: x.url.endswith('/api/factory') and x.request.method == 'POST') as created:
            page.click('#create')
        run = created.value.json(); sent = json.loads(created.value.request.post_data)
        r.check('Film starten sendet die Wahl, Projekt ist auf 0.18 gepinnt', sent['cover'] == 'after_hook' and run['idea']['cover'] == 'after_hook' and run['edit_policy'] == 18)
        r.check('Keine JavaScript-Fehler', not [e for e in errors if 'Failed to load resource' not in e]); print('   ', errors[:3])
        browser.close()
finally:
    studio.close()
r.done()
