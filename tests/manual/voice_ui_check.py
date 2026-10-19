"""0.19 voices in the browser: the figure card says when a recording was cleaned and shows the studio's notes about it
(short, music behind it, could not be cleaned); the script check says how many lines without a delivery get one from
their punctuation. No GPU, no voices are made here.

Run: CAY_TEST_STUDIO_PORT=8935 CAY_TEST_COMFY_PORT=8335 python tests/manual/voice_ui_check.py <empty dir>   (screenshots in <dir>/shots)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from harness import Studio, Report

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
studio = Studio(work); r = Report()
RID = 'v' * 32
CAST = [{'name': 'Tim', 'appearance': 'boy', 'personality': 'frech', 'voice_preset': 'child_boy'},
        {'name': 'Oma', 'appearance': 'old woman', 'personality': 'streng', 'voice_preset': 'grandma'}]
NOISY = 'Stimmprobe von Tim: viel Hintergrund (Musik oder Rauschen). Der Klon kann ihn übernehmen. Besser eine Aufnahme ohne Musik.'
FAILED = 'Stimmprobe von Oma ließ sich nicht reinigen. Das Studio klont das Original.'
SCRIPT = '''# Kuchen
### Szene 1 – Küche – Oma steht am leeren Teller
OMA: Wer hat meinen Kuchen gegessen?
TIM: Ich war's nicht!
OMA (ruhig): Komm sofort her, Tim, und zwar jetzt gleich.
TIM: Ich... ich hab doch nur probiert...
OMA: Dann gibt es heute eben keinen Nachtisch mehr für dich, mein Lieber.
'''


def scene(who, line):
    return {'title': f'{who} spricht', 'action': f'{who} steht in der Küche.', 'location': 'Küche', 'camera': 'Halbnah', 'cast': [who],
            'dialogues': [{'speaker': who, 'text': line, 'emotion': 'ruhig', 'pause_after': .18}], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'problem', 'because': 'x', 'round': 0, 'selected': None, 'render_seconds': 4, 'seconds': 4, 'variants': []}


try:
    profiles = {'Tim': {'file': 't.ref19.wav', 'sha256': 'x', 'source': 'upload',
                        'reference': {'cleaned': True, 'mode': 'x-vector', 'warnings': ['noisy'], 'gain_db': 18.2,
                                      'notes': ['Stimmprobe gereinigt: Rauschen gemindert, +18 dB angeglichen.', NOISY]}},
                'Oma': {'file': 'o.wav', 'sha256': 'x', 'source': 'upload', 'reference': {'cleaned': False, 'mode': 'x-vector', 'notes': [FAILED]}}}
    studio.project(RID, 'voice_review', {'plan': {'cast': CAST, 'style': 'clay', 'mood': 'playful'}, 'voice_profiles': profiles, 'voice_policy': 19,
                                         'episodes': [{'title': 'Kuchen', 'scenes': [scene('Tim', 'Ich war es nicht!'), scene('Oma', 'Wer dann?')]}]},
                   {'participants': [{'name': 'Tim', 'voice': 'a' * 32, 'traits': ''}, {'name': 'Oma', 'voice': 'b' * 32, 'traits': ''}]}, paused=1)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        page = browser.new_page(viewport={'width': 1280, 'height': 900}); errors = []
        page.on('pageerror', lambda e: errors.append(str(e))); page.on('console', lambda m: m.type == 'error' and 'Failed to load resource' not in m.text and errors.append(m.text))
        page.goto(studio.url + '/#p=' + RID); page.wait_for_selector('.cast .role'); page.wait_for_timeout(600)
        roles = page.locator('.cast .role'); tim, oma = roles.nth(0).inner_text(), roles.nth(1).inner_text()
        r.check('Tim: „Deine Aufnahme · gereinigt“ und der Hinweis auf den Hintergrund', 'Deine Aufnahme · gereinigt' in tim and NOISY in tim)
        r.check('Tim: die Zusammenfassung steht nicht als Warnung da', 'Rauschen gemindert' not in tim)
        r.check('Oma: nicht gereinigt, Hinweis, kein „gereinigt“', 'gereinigt' not in oma.replace('nicht reinigen', '') and FAILED in oma)
        page.screenshot(path=str(shots / '01_figuren_hinweise_1280_hell.png'), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844}); page.goto(studio.url + '/#p=' + RID); page.wait_for_selector('.cast .role'); page.wait_for_timeout(500)
        r.check('390 px: kein waagerechtes Scrollen', page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        page.screenshot(path=str(shots / '02_figuren_hinweise_390_hell.png'), full_page=True)
        page.set_viewport_size({'width': 1280, 'height': 900})
        page.goto(studio.url + '/#new'); page.wait_for_selector('#idea'); page.wait_for_timeout(500)
        page.click('[data-set="story"][data-value="script"]'); page.wait_for_selector('#script')
        page.fill('#script', SCRIPT); page.wait_for_selector('#script-check .script-check', timeout=8000); page.wait_for_timeout(700)
        check = ' '.join(page.locator('#script-check').inner_text().split())
        r.check('Drehbuchprüfung: Sätze ohne Sprechhaltung klingen nach ihrem Satzzeichen',
                '3 Sätze ohne Sprechhaltung klingen nach ihrem Satzzeichen (! lebhaft, ? fragend, … zögernd). Eine Angabe in Klammern hat Vorrang.' in check)
        page.screenshot(path=str(shots / '03_drehbuch_sprechhaltung_1280_hell.png'), full_page=True)
        r.check('keine Skriptfehler im Browser', not errors)
        if errors: print(errors[:5])
        browser.close()
finally:
    studio.close()
r.done()
