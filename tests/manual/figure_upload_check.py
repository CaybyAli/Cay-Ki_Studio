"""'Eigenes Bild hochladen' in a running project (0.19, B4), clicked in the real app against the real dashboard.

The fake ComfyUI really "draws": every image job copies its first reference picture to the output (grey without
one), so a redraw of Cay's upload has the upload's colour and the app can be checked by pixel colour.
Run: python tests/manual/figure_upload_check.py <empty dir>   (screenshots in <dir>/shots)
"""
import json, shutil, struct, subprocess, sys, time, zlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import harness
from harness import Studio, Report, COMFY_PORT

work = Path(sys.argv[1]); shots = work / 'shots'; shots.mkdir(parents=True, exist_ok=True)
COMFY_DIR = work / 'apps/ComfyUI'
DRAW = {'n': 0, 'delay': 0.0, 'jobs': []}
OBJECT_INFO = {c: {'input': {'required': {}}} for c in ['KSamplerSelect', 'Flux2Scheduler', 'CFGGuider', 'SamplerCustomAdvanced', 'VAEDecode', 'EmptyFlux2LatentImage',
               'PrimitiveInt', 'RandomNoise', 'CLIPTextEncode', 'ConditioningZeroOut', 'SaveImage', 'LoadImage', 'ImageScaleToTotalPixels', 'VAEEncode', 'ReferenceLatent']}
OBJECT_INFO.update({'UNETLoader': {'input': {'required': {'unet_name': [['flux-2-klein-4b-fp8.safetensors']]}}},
                    'CLIPLoader': {'input': {'required': {'clip_name': [['qwen_3_4b.safetensors']]}}},
                    'VAELoader': {'input': {'required': {'vae_name': [['flux2-vae.safetensors']]}}}})


def png_bytes(rgb, w=8, h=8):
    def chunk(kind, data): return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b''.join(b'\x00' + bytes(rgb) * w for _ in range(h))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


class DrawingComfy(harness.FakeComfy):
    def do_GET(self):
        if self.path.startswith('/object_info'): return self.reply(OBJECT_INFO)
        if self.path.startswith('/api/ps') or self.path.startswith('/api/tags'): return self.reply({'models': []})
        if self.path.startswith('/history/'):
            pid = self.path.split('/history/', 1)[1]; item = harness.COMFY['history'].get(pid)
            return self.reply({pid: item['data']} if item and time.time() >= item['ready'] else {})
        return super().do_GET()

    def do_POST(self):
        if self.path != '/prompt': return super().do_POST()
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        DRAW['n'] += 1; pid = f'pid{DRAW["n"]}'; graph = body['prompt']
        refs = [n['inputs']['image'] for _, n in sorted(graph.items(), key=lambda x: int(x[0])) if n['class_type'] == 'LoadImage']
        out = COMFY_DIR / 'output' / (pid + '.png'); out.parent.mkdir(parents=True, exist_ok=True)
        if refs: shutil.copy(COMFY_DIR / 'input' / refs[0], out)
        else: out.write_bytes(png_bytes((128, 128, 128)))
        DRAW['jobs'].append(refs)
        harness.COMFY['history'][pid] = {'ready': time.time() + DRAW['delay'], 'data': {'status': {'completed': True, 'status_str': 'success'},
                                         'outputs': {'77': {'images': [{'filename': pid + '.png', 'subfolder': '', 'type': 'output'}]}}}}
        self.reply({'prompt_id': pid, 'number': DRAW['n'], 'node_errors': {}})


harness.FakeComfy = DrawingComfy
studio = Studio(work, ollama=f'http://127.0.0.1:{COMFY_PORT}'); r = Report(); db = studio.db
CAST = [{'name': 'Lena', 'appearance': 'woman', 'personality': 'klug', 'voice_preset': 'young_woman'},
        {'name': 'Markus', 'appearance': 'man', 'personality': 'stur', 'voice_preset': 'man'}]


def scene(cast):
    return {'title': 'Szene 1', 'action': 'Lena hält den Keks.', 'still': 'Lena holds a cookie', 'location': 'Küche', 'camera': 'Halbnah', 'cast': cast,
            'dialogues': [{'speaker': cast[0], 'text': 'Hallo, Markus!', 'emotion': 'Natürlich', 'pause_after': .18}], 'dialogue': '', 'speaker': '',
            'continuity': 'x', 'beat': 'problem', 'because': 'x', 'round': 0, 'selected': None, 'render_seconds': 4.4, 'seconds': 4.4, 'variants': []}


def project(rid, state, paused=0, scenes=1, autopilot=True, check=True, **extra):
    folder = studio.root / '01_Projekte/Studio' / rid / '02_Bilder'; folder.mkdir(parents=True, exist_ok=True)
    (folder / 'lena.png').write_bytes(png_bytes((30, 60, 220), 64, 96)); (folder / 'markus.png').write_bytes(png_bytes((30, 200, 60), 64, 96))
    studio.project(rid, state, {'title': 'Figurencheck', 'plan': {'title': 'Figurencheck', 'cast': [dict(c) for c in CAST], 'style': 'Bright cartoon look.', 'mood': 'playful'},
                                'episodes': [{'title': 'Figurencheck', 'scenes': [scene(['Lena', 'Markus']) for _ in range(scenes)]}],
                                'cast_refs': {'Lena': str(folder / 'lena.png'), 'Markus': str(folder / 'markus.png')}, **extra},
                   {'cast_check': check, 'autopilot': autopilot, 'look': 'auto'}, paused)


def doc(rid): return studio.call('/api/factory/' + rid)[1]


COLOUR = """async (name) => { const hit = [...document.querySelectorAll('.cast .role')].find(r => r.querySelector('.role-name').textContent === name);
    const img = hit && hit.querySelector('.figure-pic img'); if (!img) return null;
    await img.decode().catch(() => {}); const c = document.createElement('canvas'); c.width = 4; c.height = 4; const x = c.getContext('2d');
    x.drawImage(img, 0, 0, 4, 4); const px = x.getImageData(1, 1, 1, 1).data; return [px[0], px[1], px[2]]; }"""
# The toast is readable: the topmost element at its centre is the toast itself, not the sheet's backdrop or the sheet.
ON_TOP = """() => { const t = document.querySelector('#toast'); if (!t.classList.contains('show')) return false; const b = t.getBoundingClientRect();
    const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2); return !!hit && t.contains(hit); }"""


def red(rgb): return bool(rgb) and rgb[0] > 200 and rgb[1] < 80 and rgb[2] < 80


try:
    A, B, C = '1' * 32, '2' * 32, '3' * 32
    project(A, 'cast_review'); project(B, 'cast_review', paused=1); project(C, 'pictures', paused=1, scenes=4, autopilot=False, check=False)   # draws its scenes at once
    picture = work / 'eigenes_bild.jpg'; broken = work / 'IMG_0042.heic'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0xff2020:s=600x900:d=1', '-frames:v', '1', str(picture)], check=True)
    broken.write_bytes(b'\x00\x00\x00\x18ftypheic' + b'\x00' * 400)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/opt/pw-browsers/chromium')
        for label, viewport in (('pc', {'width': 1280, 'height': 900}), ('handy', {'width': 390, 'height': 844})):
            page = browser.new_page(viewport=viewport); errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            if label == 'handy':
                # The phone: an unreadable picture (HEIC) says why, above the open sheet.
                page.goto(studio.url + '/#p=' + B); page.wait_for_selector('.cast .role'); page.wait_for_timeout(600)
                page.click('.cast [data-action="figure-menu"][data-name="Markus"]'); page.wait_for_selector('.menu-row')
                page.set_input_files('.menu input[data-upload="cast"][data-name="Markus"]', str(broken)); page.wait_for_timeout(700)
                page.screenshot(path=str(shots / 'handy_01_fehler_lesbar.png'))
                r.check('Handy: Fehler eines unlesbaren Bildes über dem offenen Blatt lesbar', page.evaluate(ON_TOP)
                        and 'Bildformat' in page.locator('#toast').inner_text() and page.evaluate("document.querySelector('#sheet').open"))
                r.check('Handy: Zeile wieder bereit, keine Seitenfehler', 'neutralem Gesicht' in page.locator('[data-upload-row]').inner_text() and not errors)
                page.close(); continue

            # 1. Figure check: the upload is drawn and shown; the confirmation is readable.
            page.goto(studio.url + '/#p=' + A); page.wait_for_selector('.cast .role'); page.wait_for_timeout(800)
            r.check('Vorher: Markus grün', page.evaluate(COLOUR, 'Markus') == [30, 200, 60])
            page.click('.cast [data-action="figure-menu"][data-name="Markus"]'); page.wait_for_selector('.menu-row')
            page.set_input_files('.menu input[data-upload="cast"][data-name="Markus"]', str(picture)); page.wait_for_timeout(500)
            r.check('Bestätigung lesbar, Blatt geschlossen', page.evaluate(ON_TOP) and 'wird verwendet' in page.locator('#toast').inner_text()
                    and not page.evaluate("document.querySelector('#sheet').open"))
            for _ in range(40):
                page.wait_for_timeout(500)
                if doc(A)['state'] == 'cast_review' and red(page.evaluate(COLOUR, 'Markus')): break
            page.screenshot(path=str(shots / 'pc_01_eigenes_bild.png'), full_page=True)
            d = doc(A)
            r.check('Figurencheck: Markus aus deinem Bild neu gezeichnet und angezeigt', d['state'] == 'cast_review' and red(page.evaluate(COLOUR, 'Markus'))
                    and 'markus.png' not in d['cast_refs']['Markus'] and 'Dein Bild, neutral nachgezeichnet' in page.locator('.role', has_text='Markus').inner_text())

            # 2. Paused: the picture shows at once and the app says it waits for 'Fortsetzen'.
            page.goto(studio.url + '/#p=' + B); page.wait_for_selector('.cast .role'); page.wait_for_timeout(600)
            page.click('.cast [data-action="figure-menu"][data-name="Markus"]'); page.wait_for_selector('.menu-row')
            page.set_input_files('.menu input[data-upload="cast"][data-name="Markus"]', str(picture)); page.wait_for_timeout(1200)
            page.screenshot(path=str(shots / 'pc_02_pausiert.png'), full_page=True)
            r.check('Pausiert: Hinweis auf Fortsetzen, dein Bild sofort sichtbar mit „Wird nachgezeichnet“', 'Fortsetzen' in page.locator('#toast').inner_text()
                    and red(page.evaluate(COLOUR, 'Markus')) and 'Wird nachgezeichnet' in page.locator('.role', has_text='Markus').inner_text())

            # 3. While the studio draws: the picture is kept and taken after the current image.
            DRAW['delay'] = 4.0; studio.call(f'/api/factory/{C}/resume', {})
            page.goto(studio.url + '/#p=' + C); page.wait_for_selector('.cast .role')
            for _ in range(30):
                page.wait_for_timeout(400)
                if (doc(C).get('cast_windows') or {}).get('image') == 'later': break
            page.wait_for_timeout(2600)                                          # the app polls every 2.5 s
            page.click('.cast [data-action="figure-menu"][data-name="Markus"]'); page.wait_for_selector('.menu-row')
            r.check('Während das Studio zeichnet: Hochladen angeboten, wird vorgemerkt', 'Wird vorgemerkt' in page.locator('[data-upload-row]').inner_text())
            page.screenshot(path=str(shots / 'pc_03_vormerken.png'))
            page.set_input_files('.menu input[data-upload="cast"][data-name="Markus"]', str(picture)); page.wait_for_timeout(500)
            r.check('Vorgemerkt: Meldung lesbar, Karte zeigt die Vormerkung', 'vorgemerkt' in page.locator('#toast').inner_text()
                    and 'Vorgemerkt: dein eigenes Bild' in page.locator('.role', has_text='Markus').inner_text())
            for _ in range(80):
                page.wait_for_timeout(500)
                d = doc(C)
                if not d.get('pending_cast') and 'Markus' in d.get('cast_refs', {}) and 'markus.png' not in d['cast_refs']['Markus']: break
            page.wait_for_timeout(2800)
            page.screenshot(path=str(shots / 'pc_04_uebernommen.png'), full_page=True)
            d = doc(C); part = next((x for x in d['idea']['participants'] if x['name'] == 'Markus'), {})
            r.check('Nach dem laufenden Bild übernommen und neu gezeichnet', part.get('image') and not d.get('pending_cast')
                    and 'markus.png' not in d['cast_refs'].get('Markus', 'markus.png') and red(page.evaluate(COLOUR, 'Markus')))
            r.check('Keine Seitenfehler', not errors)
            page.close()
        browser.close()
finally:
    studio.close()
r.done()
