"""Looks per episode (0.18) in the browser: the choice in a new series, the variants under each figure in the
figure check, a new design of one variant with a wish, and the redraw of only that episode's scenes.

Run: python tests/manual/looks_check.py <empty dir>   (screenshots in <dir>/shots)
Figures and variants are FFmpeg pictures, no AI models: this checks the flow on the real server.
"""
import hashlib, json, subprocess, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report(); db = studio.db
ids = iter(f'{i:032x}' for i in range(1, 400))


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def figure(path, body, clothes):
    """A figure-like test picture: light background, a body, clothes in another colour."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0xeeeeee:s=576x1024:d=1',
                    '-vf', f'drawbox=x=168:y=150:w=240:h=300:color={body}@1:t=fill,drawbox=x=148:y=450:w=280:h=420:color={clothes}@1:t=fill',
                    '-frames:v', '1', str(path)], check=True)
    return path


def scene(rid, ei, si, cast, drawn):
    variants = []
    for k in range(2 if drawn else 0):
        sid = next(ids); out = figure(studio.root / '01_Projekte/Studio' / rid / f'02_Bilder/{sid}.png', '0x134e5e', '0x71b280')
        db.execute("INSERT INTO factory_steps(id,run_id,step_key,status,prompt_id,graph,output,sha256) VALUES(?,?,?,?,?,?,?,?)",
                   (sid, rid, f'image:{ei}:{si}:0:{k}', 'done', None, '{}', str(out), sha(out)))
        variants.append({'id': sid, 'key': f'image:{ei}:{si}:0:{k}'})
    return {'title': f'Szene {si + 1}', 'action': f'{" und ".join(cast)} im Krusty Krab.', 'location': 'Krusty Krab', 'camera': 'Halbnah', 'cast': cast,
            'dialogues': [{'speaker': cast[0], 'text': 'Heute wird alles anders.', 'emotion': 'ruhig', 'pause_after': .18}], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'problem', 'because': 'x', 'round': 0, 'selected': variants[0]['id'] if variants else None, 'render_seconds': 4, 'seconds': 4,
            'variants': variants}


CAST = [{'name': 'SpongeBob', 'appearance': 'yellow sea sponge, white shirt, brown square pants', 'personality': 'eifrig', 'voice_preset': 'young_man'},
        {'name': 'Patrick', 'appearance': 'pink starfish, green shorts', 'personality': 'langsam', 'voice_preset': 'man'}]
LOOKS = [({'SpongeBob': 'torn dirty white shirt, ripped brown shorts, barefoot'}, {'SpongeBob': 'zerrissene Kleidung'}),
         ({'Patrick': 'wet swimming trunks, snorkel mask on the forehead'}, {'Patrick': 'nasse Badehose mit Schnorchel'}),
         ({'SpongeBob': 'expensive tailored navy suit, silk tie, polished shoes'}, {'SpongeBob': 'teurer Anzug'})]
COLOURS = {('0', 'SpongeBob'): '0x8a6d3b', ('1', 'Patrick'): '0x1f6fb2', ('2', 'SpongeBob'): '0x1b2a4a'}


def project(rid, state, drawn, paused=1):
    folder = studio.root / '01_Projekte/Studio' / rid
    refs = {'SpongeBob': str(figure(folder / '02_Bilder/spongebob.png', '0xffd23f', '0xf5f5f5')), 'Patrick': str(figure(folder / '02_Bilder/patrick.png', '0xff8fb1', '0x3bceac'))}
    looks = {ei: {name: str(figure(folder / f'02_Bilder/look_{ei}_{name}.png', '0xffd23f' if name == 'SpongeBob' else '0xff8fb1', colour))}
             for (ei, name), colour in COLOURS.items()}
    episodes = [{'title': title, 'looks': dict(LOOKS[ei][0]), 'look_labels': dict(LOOKS[ei][1]),
                 'scenes': [scene(rid, ei, si, cast, drawn) for si, cast in enumerate(casts)]}
                for ei, (title, casts) in enumerate((('Pleite', (['SpongeBob'], ['SpongeBob', 'Patrick'])), ('Am Strand', (['Patrick'], ['SpongeBob', 'Patrick'])),
                                                     ('Der Boss', (['SpongeBob'], ['SpongeBob', 'Patrick']))))]
    episode_refs = {}
    for ei, box in looks.items():
        episode_refs.setdefault(ei, {}).update(box)
    studio.project(rid, state, {'title': 'Vom Schwamm zum Boss', 'plan': {'title': 'Vom Schwamm zum Boss', 'cast': CAST, 'style': 'cartoon', 'mood': 'playful'},
                                'episodes': episodes, 'cast_refs': refs, 'episode_refs': episode_refs},
                   {'idea': 'SpongeBob ist am Anfang arm und trägt zerrissene Kleidung, am Ende trägt er einen Anzug.', 'episodes': 3, 'looks': 'per_episode',
                    'cast_check': True, 'look': 'cartoon'}, paused)


def doc(page, rid): return json.loads(page.evaluate(f"fetch('/api/factory/{rid}').then(r => r.text())"))


def loaded(page, selector):
    for _ in range(40):
        if page.evaluate(f"[...document.querySelectorAll('{selector}')].every(i => i.complete && i.naturalWidth > 0)"): return True
        page.wait_for_timeout(250)
    return False


try:
    A, B = 'a' * 32, 'b' * 32
    project(A, 'cast_review', drawn=False)
    project(B, 'image_review', drawn=True)
    db.commit()

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}); errors = []
        page.on('pageerror', lambda e: errors.append(str(e))); page.on('console', lambda m: m.type == 'error' and errors.append(m.text))
        base = studio.url + '/'

        # ---------- new film: the choice appears only for a series ----------
        page.goto(base + '#new'); page.wait_for_selector('#idea')
        r.check('Einzelfilm: keine Wahl „Aussehen der Figuren“', page.locator('#looks-choice').is_hidden())
        page.click('[data-set="episodes"][data-value="6"]'); page.wait_for_timeout(200)
        choice = page.locator('#looks-choice')
        r.check('6 Folgen: Wahl sichtbar, „Gleich in allen Folgen“ vorgewählt', choice.is_visible()
                and page.locator('[data-set="looks"][data-value="same"]').get_attribute('aria-pressed') == 'true'
                and 'Jede Figur sieht in allen Folgen gleich aus.' in page.locator('#looks-hint').inner_text())
        page.click('[data-set="looks"][data-value="per_episode"]'); page.wait_for_timeout(200)
        r.check('Pro Folge anpassen: Hinweis zu Gesicht, Körper und Kleidung, Entwurf gespeichert',
                page.locator('#looks-hint').inner_text() == 'Gesicht und Körper bleiben gleich. Kleidung und Zustand passen sich jeder Folge an, z. B. Folge 1 zerrissene Kleidung, Folge 6 Anzug.'
                and page.evaluate("JSON.parse(localStorage.getItem('cay-draft')).looks") == 'per_episode')
        r.check('Gleiche Gestaltung wie die anderen Wahlen (Zeile mit Beschriftung und Segmenten)',
                choice.evaluate("e => e.className") == 'choice' and choice.locator('.segmented').count() == 1 and choice.locator('> span').inner_text() == 'Aussehen der Figuren')
        page.locator('.choices').screenshot(path=str(shots / '01_neue_serie_aussehen.png'))
        page.emulate_media(color_scheme='dark'); page.wait_for_timeout(250)
        page.locator('.choices').screenshot(path=str(shots / '01b_neue_serie_aussehen_dunkel.png')); page.emulate_media(color_scheme='light')
        page.set_viewport_size({'width': 390, 'height': 844}); page.wait_for_timeout(300)
        choice.screenshot(path=str(shots / '01c_neue_serie_aussehen_handy.png'))
        boxes = page.evaluate("[...document.querySelectorAll('#looks-choice .segmented button')].map(b => { const r = b.getBoundingClientRect(); return [r.top, r.width]; })")
        r.check('Handy: beide Optionen in einer Reihe, gleich breit, keine waagerechte Scrollleiste', len(boxes) == 2 and abs(boxes[0][0] - boxes[1][0]) < 1
                and abs(boxes[0][1] - boxes[1][1]) < 2 and page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        page.set_viewport_size({'width': 1280, 'height': 900})
        page.fill('#idea', 'SpongeBob ist am Anfang arm und trägt zerrissene Kleidung, am Ende trägt er einen Anzug.')
        with page.expect_response(lambda x: x.url.endswith('/api/factory') and x.request.method == 'POST') as created:
            page.click('#create')
        run = created.value.json(); sent = json.loads(created.value.request.post_data)
        r.check('Serie starten sendet „Pro Folge anpassen“, das Projekt speichert es', sent['looks'] == 'per_episode' and run['idea']['looks'] == 'per_episode' and run['idea']['episodes'] == 6)
        studio.call(f'/api/factory/{run["id"]}/pause', {})
        # A draft that once chose looks per episode, then a single film: nothing changes for it.
        page.goto(base + '#new'); page.wait_for_selector('#idea')
        page.click('[data-set="episodes"][data-value="3"]'); page.click('[data-set="looks"][data-value="per_episode"]'); page.click('[data-set="episodes"][data-value="1"]')
        page.wait_for_timeout(200)
        r.check('Zurück zum Einzelfilm: Wahl wieder ausgeblendet', page.locator('#looks-choice').is_hidden())
        page.fill('#idea', 'Zwei Kollegen streiten um den letzten Keks im Büro.')
        with page.expect_response(lambda x: x.url.endswith('/api/factory') and x.request.method == 'POST') as created:
            page.click('#create')
        single = created.value.json(); sent = json.loads(created.value.request.post_data)
        r.check('Einzelfilm sendet „gleich“ und speichert kein Aussehen pro Folge', sent['looks'] == 'same' and 'looks' not in single['idea'])
        studio.call(f'/api/factory/{single["id"]}/pause', {})

        # ---------- figure check: variants grouped by episode under each figure ----------
        page.goto(base + '#p=' + A); page.wait_for_selector('.cast .role-looks')
        roles = page.evaluate("[...document.querySelectorAll('.cast .role')].map(r => [r.querySelector('.role-name').textContent, [...r.querySelectorAll('.look-item')].map(b => b.textContent.trim().replace(/\\s+/g, ' '))])")
        r.check('Unter jeder Figur ihre Folgen in Reihenfolge mit dem Text', roles == [['SpongeBob', ['Folge 1: zerrissene Kleidung', 'Folge 3: teurer Anzug']], ['Patrick', ['Folge 2: nasse Badehose mit Schnorchel']]])
        r.check('Bilder der Varianten geladen', page.locator('.look-item img').count() == 3 and loaded(page, '.look-item img'))
        r.check('Prüftext nennt die Kleidung pro Folge, Einstellungszeile „Aussehen pro Folge“',
                'darunter ihre Kleidung in einzelnen Folgen' in page.locator('.next').inner_text() and 'Aussehen pro Folge' in page.locator('.project-head').inner_text())
        page.screenshot(path=str(shots / '02_figurencheck.png'), full_page=True)
        page.locator('.cast').screenshot(path=str(shots / '02b_figurencheck_besetzung.png'))
        page.emulate_media(color_scheme='dark'); page.wait_for_timeout(250)
        page.locator('.cast').screenshot(path=str(shots / '02c_figurencheck_dunkel.png')); page.emulate_media(color_scheme='light')
        page.set_viewport_size({'width': 390, 'height': 844}); page.wait_for_timeout(300)
        page.screenshot(path=str(shots / '02d_figurencheck_handy.png'), full_page=True)
        r.check('Handy (Figurencheck): keine waagerechte Scrollleiste', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        page.set_viewport_size({'width': 1280, 'height': 900}); page.wait_for_timeout(200)

        # Figure menu: one row per episode the figure is seen in
        page.click('.role-hit[data-name="SpongeBob"]'); page.wait_for_selector('#sheet .figure-sheet')
        page.locator('#sheet .menu-row[data-action="look-menu"]').last.scroll_into_view_if_needed()   # the thumbnails load lazily
        rows = page.evaluate("[...document.querySelectorAll('#sheet .menu-row[data-action=\"look-menu\"]')].map(b => b.querySelector('b').textContent + ' ' + b.querySelector('span:last-child').textContent)")
        r.check('Figurenmenü: „Aussehen pro Folge“ mit jeder Folge, in der die Figur spielt', 'aussehen pro folge' in page.locator('#sheet').inner_text().lower()
                and rows == ['Folge 1 zerrissene Kleidung', 'Folge 2 Wie im Grunddesign', 'Folge 3 teurer Anzug']
                and loaded(page, '#sheet .menu-row .mini img') and page.locator('#sheet .menu-row .mini img').count() == 3)
        page.locator('#sheet .sheet-body').screenshot(path=str(shots / '03_figurenmenue.png'))
        page.click('#sheet .menu-row[data-episode="2"]'); page.wait_for_selector('#look-form')
        sheet = page.locator('#sheet').inner_text()
        r.check('Folge 3: Bild, „teurer Anzug“, Text für das Bild, Wunschfeld', page.locator('#sheet h2').inner_text() == 'SpongeBob in Folge 3'
                and 'teurer Anzug' in sheet and 'Für das Bild: expensive tailored navy suit' in sheet and loaded(page, '#sheet .figure-pic img')
                and 'Gesicht und Körper bleiben gleich.' in sheet)
        page.fill('#look-form textarea', 'grauer Anzug mit roter Krawatte, Aktentasche')
        page.locator('#sheet .sheet-body').screenshot(path=str(shots / '04_aussehen_neu.png'))
        page.click('#look-form [type="submit"]'); page.wait_for_timeout(1000)
        a = doc(page, A); boss = a['episodes'][2]
        r.check('Neu gestalten: Text ersetzt, neue Runde, nur diese Variante entfällt, Studio zeichnet', boss['looks']['SpongeBob'] == 'grauer Anzug mit roter Krawatte, Aktentasche'
                and boss['look_rounds'] == {'SpongeBob': 1} and 'SpongeBob' not in a['episode_refs']['2'] and a['episode_refs']['0'] and a['state'] == 'pictures')
        item = page.locator('.look-item[data-name="SpongeBob"][data-episode="2"]')
        r.check('Karte zeigt den neuen Text, Bild entsteht', 'Folge 3: grauer Anzug mit roter Krawatte' in item.inner_text() and item.locator('img').count() == 0)
        page.locator('.cast').screenshot(path=str(shots / '05_besetzung_nach_wunsch.png'))

        # ---------- image review: only that episode's scenes with that figure are drawn again ----------
        page.goto(base + '#p=' + B); page.wait_for_selector('.cast .look-item')
        page.click('.look-item[data-name="Patrick"][data-episode="1"]'); page.wait_for_selector('#look-form')
        r.check('Hinweis nennt, welche Szenen neue Bilder bekommen', '2 Szenen in Folge 2 mit Patrick bekommen neue Bilder, alle anderen bleiben.' in page.locator('#sheet').inner_text())
        page.click('#look-form [type="submit"]'); page.wait_for_timeout(1000)
        b = doc(page, B)
        rounds = [[s.get('image_rounds') for s in ep['scenes']] for ep in b['episodes']]
        r.check('Ohne Wunsch: gleicher Text, neue Runde; nur Folge 2 mit Patrick wird neu gezeichnet', b['episodes'][1]['looks'] == LOOKS[1][0]
                and b['episodes'][1]['look_rounds'] == {'Patrick': 1} and rounds == [[None, None], [[1, 1], [1, 1]], [None, None]] and b['state'] == 'pictures'
                and 'Patrick in Folge 2 wird neu gestaltet · 2 Szenen folgen' == b['phase'])
        r.check('Keine JavaScript-Fehler', not [e for e in errors if 'Failed to load resource' not in e]); print('   ', errors[:3])
        browser.close()
finally:
    studio.close()
r.done()
