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

        r.check('Keine JavaScript-Fehler', not [e for e in errors if 'Failed to load resource' not in e]); print('   ', errors[:3])
        browser.close()
finally:
    studio.close()
r.done()
