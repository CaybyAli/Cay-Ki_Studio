#!/usr/bin/env python3
"""Cay Studio Diagnose: reads facts about the newest projects. Changes nothing.

Database opened read-only, no downloads, no restarts, no deletions.
Output goes to the console; Cay_Studio_Diagnose.cmd also saves it as text.
"""
import json, math
import os
import re
import shutil
from pathlib import Path
import sqlite3
import subprocess
import urllib.request

RUNTIME = Path(os.environ.get('CAY_STUDIO_RUNTIME', '/home/alihu/ki-video/studio'))
BASE = RUNTIME.parent


def health():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:8787/api/health', timeout=4) as response: return json.load(response)
    except (OSError, ValueError) as error: return {'fehler': str(error)}


def words(scene):
    lines = scene.get('dialogues') or ([{'text': scene['dialogue']}] if scene.get('dialogue') else [])
    return len(lines), sum(len(str(line.get('text', '')).split()) for line in lines)


def loudness(path):
    """Mean/max volume of the whole audio track and of each second (silence check)."""
    try:
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_type,codec_name,duration',
                                '-of', 'json', str(path)], capture_output=True, text=True, timeout=60)
        streams = json.loads(probe.stdout or '{}').get('streams', [])
        volume = subprocess.run(['ffmpeg', '-nostdin', '-v', 'info', '-i', str(path), '-map', '0:a:0?', '-af', 'volumedetect',
                                 '-f', 'null', '-'], capture_output=True, text=True, timeout=300).stderr
        values = [l.split('] ')[-1] for l in volume.splitlines() if 'mean_volume' in l or 'max_volume' in l]
        return {'streams': [(s.get('codec_type'), s.get('codec_name'), s.get('duration')) for s in streams], 'lautstaerke': values}
    except (OSError, ValueError, subprocess.SubprocessError) as error: return {'fehler': str(error)}


def newest_mix(folder):
    mixes = sorted((folder / '03_Stimmen').glob('Mischung_*/Folge_*'))
    result = []
    for mix in mixes[-2:]:
        entry = {'ordner': str(mix.relative_to(folder))}
        for name in ('Tonbericht.json', 'Sprachpruefung.json'):
            path = mix / name
            if path.is_file():
                data = json.loads(path.read_text(encoding='utf-8'))
                if name == 'Sprachpruefung.json':
                    data = {k: data.get(k) for k in ('checked', 'blocking', 'warnings', 'speakers_missing')} | {
                        'auffaellig': [l['label'] + ' – ' + l['status'] for l in data.get('lines', []) if l.get('status') != 'ok'][:8]}
                entry[name] = data
            else: entry[name] = 'fehlt'
        result.append(entry)
    return result


def minutes(seconds):
    return f'{seconds / 60:5.1f} min'


def timing(db, d, row):
    """Measured GPU/CPU time per stage plus total elapsed time of the project."""
    try:
        rows = db.execute('SELECT stage,resource,COUNT(*) AS n,SUM(seconds) AS s,MIN(started) AS first,MAX(started) AS last '
                          'FROM performance_stages WHERE project=? GROUP BY stage,resource ORDER BY MIN(started)', (d.get('id'),)).fetchall()
    except sqlite3.Error as error:
        print('Zeitmessung nicht lesbar:', error); return
    if not rows: print('Zeitmessung: keine Einträge'); return
    print('ZEITMESSUNG (gemessene Rechenzeit je Arbeitsschritt):')
    for r in rows: print(f'   {r["stage"][:34]:34} {r["resource"]:6} {r["n"]:3}x  {minutes(r["s"] or 0)}')
    total = sum(r['s'] or 0 for r in rows)
    voices = any(r['stage'].startswith(('Sprache', 'Stimmgestaltung')) for r in rows)
    print(f'   {"Summe gemessen":34} {"":6} {"":4}  {minutes(total)}  ('
          + ('' if voices else 'Stimmen in dieser Version noch nicht gemessen; ') + 'Wartezeit auf deine Freigaben nicht enthalten)')
    print('   Projekt angelegt:', row['created'], '| zuletzt geändert:', row['updated'])


def project(row, root, db=None):
    d = json.loads(row['document']); idea = d.get('idea', {})
    print('\n' + '=' * 70)
    print('PROJEKT', d.get('title'), '| id', d.get('id'), '| Zustand', d.get('state'), '| aktualisiert', row['updated'])
    print('Idee (Anfang):', ' '.join(str(idea.get('idea', '')).split())[:220])
    print('Einstellungen:', {k: idea.get(k) for k in ('duration', 'episodes', 'characters', 'lip_sync', 'quality', 'speech_engine', 'fps', 'look')})
    print('Besetzung:', [p.get('name') for p in d.get('plan', {}).get('cast', [])])
    for ei, ep in enumerate(d.get('episodes', [])):
        counts = [words(s) for s in ep.get('scenes', [])]
        print(f'Folge {ei + 1}: {len(counts)} Szenen, Szenen mit Dialog {sum(1 for c in counts if c[0])}, '
              f'Zeilen {sum(c[0] for c in counts)}, Wörter {sum(c[1] for c in counts)}, Modus {ep.get("dialogue_mode")}')
        for si, s in enumerate(ep.get('scenes', [])):
            print(f'   Szene {si + 1}: sichtbar {s.get("cast")}, Zeilen {words(s)[0]}, Sekunden {s.get("render_seconds", s.get("seconds"))}')
        for warning in ep.get('warnings', [])[:4]: print('   Warnung:', warning[:220])
    figures(d)
    script(d)
    windows(d, db)
    render_modes(d, db)
    lines = d.get('lines', [])
    print('Erzeugte Sprachdateien:', len(lines), '| Sprachmodell:', d.get('audio_engine'), '| Neuaufnahmen:', d.get('speech_takes'))
    for line in lines[:12]:
        exists = Path(line.get('file', '')).is_file()
        print(f'   F{line.get("episode", 0) + 1} S{line.get("scene", 0) + 1} {line.get("speaker")}: {line.get("duration", 0):.2f} s, '
              f'Datei {"da" if exists else "FEHLT"}, Text: {str(line.get("text", ""))[:60]}')
    for t in d.get('timing', []): print('Zeitplan:', {k: t.get(k) for k in ('seconds', 'speech_seconds', 'speech_share', 'longest_speech_gap')})
    print('Fehler:', (d.get('error') or '-')[:600], '| Fortsetzen bei:', d.get('resume_state'))
    if db is not None: timing(db, d, row)
    folder = root / '01_Projekte' / 'Studio' / str(d.get('id'))
    if folder.is_dir():
        for mix in newest_mix(folder): print('Tonmischung:', json.dumps(mix, ensure_ascii=False)[:900])
    for preview in d.get('previews', []): print('Tonvorschau', preview.get('episode'), loudness(preview.get('file', '')))
    for export in d.get('exports', []): print('Fertiges Video', export.get('file'), loudness(export.get('file', '')))


def figures(d):
    """Where each figure's look comes from: own picture, known original, template style."""
    idea = d.get('idea', {}); own = {p.get('name') for p in idea.get('participants', []) if p.get('image')}
    print('Look-Vorlagen:', len(idea.get('examples', [])), '| Figuren-Gestaltung:', d.get('cast_refs') and 'vorhanden' or 'noch keine')
    for p in d.get('plan', {}).get('cast', []):
        print(f'   {p.get("name")}: ' + ('eigenes Bild' if p.get('name') in own else 'Original: ' + p['original'] if p.get('original') else 'erfunden')
              + f', neu gestaltet {p.get("design_round", 0)}x, Aussehen: {str(p.get("appearance", ""))[:90]}')


def script(d):
    """0.17 screenplay: words, lines, silent actions, shots, doctor and visual pass."""
    for ei, ep in enumerate(d.get('episodes', [])):
        st = ep.get('screenplay_stats')
        if st: print(f'Drehbuch Folge {ei + 1}: {st.get("words")} Wörter (Ziel {st.get("budget", {}).get("words")}), {st.get("lines")} Zeilen, '
                     f'{st.get("actions")} stumme Aktionen, {st.get("shots")} Einstellungen')
        store = (d.get('screenplays') or {}).get(str(ei), {})
        for key in ('doctor_error', 'visual_error'):
            if store.get(key): print(f'   {key}: {store[key][:200]}')


def render_modes(d, db):
    """Which attention mode and size the lip-sync steps really used (Turbo needs a ComfyUI restart)."""
    if db is None: return
    try:
        rows = db.execute("SELECT graph FROM factory_steps WHERE run_id=? AND step_key LIKE 'video09:%'", (d.get('id'),)).fetchall()
    except sqlite3.Error: return
    modes = {}
    for row in rows:
        try: graph = json.loads(row[0])
        except (TypeError, ValueError): continue
        for node in graph.values():
            inputs = node.get('inputs', {})
            if node.get('class_type') == 'WanVideoModelLoader':
                key = f'{inputs.get("attention_mode")} {inputs.get("quantization")}'; modes[key] = modes.get(key, 0) + 1
            if node.get('class_type') == 'CayWanVideoSampler':
                key = 'Audio-Führung nur Schritt 1' if inputs.get('cay_audio_cfg_steps') == 1 else 'Audio-Führung alle Schritte'
                modes[key] = modes.get(key, 0) + 1
    if modes: print('Animation lief mit (Aufmerksamkeit, Gewichte):', modes)
    try:
        nodes = db.execute("SELECT detail FROM factory_metrics WHERE run_id=?", (d.get('id'),)).fetchall()
        totals = {}
        for row in nodes:
            for nid, info in (json.loads(row[0] or '{}').get('nodes') or {}).items():
                totals[nid] = totals.get(nid, 0) + float(info.get('seconds') or 0)
        top = sorted(totals.items(), key=lambda x: -x[1])[:6]
        if top: print('Rechenzeit je Knoten (Summe, Minuten):', ', '.join(f'{k}: {v / 60:.1f}' for k, v in top))
    except (sqlite3.Error, ValueError, TypeError): pass


def windows(d, db):
    """Lip-sync windows (81 frames, then 72) versus silent motion clips and measured time."""
    def count(seconds):
        frames = 4 * math.ceil(seconds * 25 / 4 - 1e-9) + 1
        return 1 + max(0, math.ceil((frames - 81) / 72))
    talk = silent = film = 0; switches = 0; last = None
    for ei, ep in enumerate(d.get('episodes', [])):
        for si, s in enumerate(ep.get('scenes', [])):
            seconds = float(s.get('render_seconds') or s.get('seconds') or 0); film += seconds
            speaking = any(l.get('episode') == ei and l.get('scene') == si for l in d.get('lines', []))
            if speaking: talk += count(seconds)
            else: silent += max(1, math.ceil(seconds / 5))
            family = 'talk' if speaking else 'motion'
            switches += bool(last and last != family); last = family
    if not film: return
    gpu = None
    if db is not None:
        try:
            row = db.execute("SELECT SUM(seconds) FROM performance_stages WHERE project=? AND stage='Animation' AND resource='GPU'", (d.get('id'),)).fetchone()
            gpu = row[0] if row else None
        except sqlite3.Error: pass
    print(f'Animation: {film:.1f} s Film, {talk} Sprech-Rechenfenster, {silent} Bewegungs-Abschnitte, '
          f'Modellwechsel in Szenenreihenfolge {switches} (ab 0.16 gebündelt)')
    if gpu and talk and not silent: print(f'   gemessen: {gpu / talk / 60:.1f} min pro Sprech-Rechenfenster, {gpu / film / 60:.1f} min pro Filmsekunde')
    elif gpu: print(f'   gemessen: {gpu / film / 60:.1f} min Animation pro Filmsekunde')


def meminfo():
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, rest = line.split(':', 1); values[key] = int(rest.split()[0]) * 1024
    return values


def gb(n): return f'{n / 1024 ** 3:.1f} GB'


def pc_team():
    """How CPU, RAM, disk and GPU share the work. Read-only facts plus plain advice."""
    print('\nPC ALS TEAM')
    m = meminfo(); total, avail = m.get('MemTotal', 0), m.get('MemAvailable', 0)
    swap_used = m.get('SwapTotal', 0) - m.get('SwapFree', 0)
    print(f'Arbeitsspeicher in WSL: {gb(total)} gesamt, {gb(avail)} frei, Auslagerung belegt {gb(swap_used)} von {gb(m.get("SwapTotal", 0))}')
    try:
        vm = dict(l.split() for l in Path('/proc/vmstat').read_text().splitlines() if l.startswith(('pswpin', 'pswpout')))
        print(f'Seit Start ausgelagert: {int(vm.get("pswpout", 0)) * 4096 / 1024 ** 3:.1f} GB raus, {int(vm.get("pswpin", 0)) * 4096 / 1024 ** 3:.1f} GB wieder rein')
    except (OSError, ValueError): pass
    print('CPU-Threads für WSL:', os.cpu_count())
    configs = sorted(Path('/mnt/c/Users').glob('*/.wslconfig')) if Path('/mnt/c/Users').is_dir() else []
    for c in configs:
        try: print(f'WSL-Einstellung {c}:', ' | '.join(l.strip() for l in c.read_text(errors='replace').splitlines() if l.strip() and not l.strip().startswith('#')) or '(leer)')
        except OSError as error: print('WSL-Einstellung nicht lesbar:', error)
    if not configs: print('WSL-Einstellung: keine .wslconfig gefunden (Windows-Standard)')
    try:
        smi = subprocess.run([shutil.which('nvidia-smi') or '/usr/lib/wsl/lib/nvidia-smi', '--query-gpu=pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,pcie.link.width.max,power.limit',
                              '--format=csv,noheader'], capture_output=True, text=True, timeout=20)
        print('Grafikkarte PCIe (Gen jetzt, Gen max, Breite jetzt, Breite max, Leistungsgrenze):', smi.stdout.strip() or smi.stderr.strip())
    except (OSError, subprocess.SubprocessError): pass
    models = BASE / 'apps/ComfyUI/models'
    try:
        fs = subprocess.run(['df', '-T', '-h', str(models.resolve())], capture_output=True, text=True, timeout=20).stdout.splitlines()[-1].split()
        print(f'Modelle liegen auf: {fs[1]} ({fs[6]}), frei {fs[4]}' + ('  ACHTUNG: Windows-Laufwerk, Laden ist langsam' if fs[1] in ('9p', 'drvfs', 'v9fs') else ''))
    except (OSError, IndexError, subprocess.SubprocessError): pass
    try:
        top = subprocess.run(['ps', '-eo', 'rss,comm', '--sort=-rss'], capture_output=True, text=True, timeout=20).stdout.splitlines()[1:7]
        print('Größte Programme in WSL:', ', '.join(f'{l.split()[1]} {int(l.split()[0]) / 1024 ** 2:.1f} GB' for l in top))
    except (OSError, ValueError, IndexError, subprocess.SubprocessError): pass
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:11434/api/ps', timeout=4) as r: loaded = json.load(r).get('models', [])
        print('Planungsmodell im Speicher:', ', '.join(f'{x["name"]} {x.get("size", 0) / 1024 ** 3:.1f} GB' for x in loaded) or 'keins (gut während der Animation)')
    except (OSError, ValueError): print('Planungsmodell im Speicher: Ollama nicht erreichbar')
    try:
        print('ComfyUI gestartet mit:', ' '.join(json.loads((RUNTIME / 'logs/comfyui_prozess.json').read_text())['args'][1:]))
    except (OSError, ValueError, KeyError): pass
    print('Turbo:', (RUNTIME / 'config/turbo.json').read_text() if (RUNTIME / 'config/turbo.json').is_file() else 'nicht eingerichtet')
    log = RUNTIME / 'logs/comfyui.log'
    if log.is_file():
        with log.open('rb') as stream:
            stream.seek(max(0, log.stat().st_size - 3_000_000)); text = stream.read().decode(errors='replace')
        runs = [float(x) for x in re.findall(r'Prompt executed in ([0-9.]+) seconds', text)][-20:]
        speeds = re.findall(r'([0-9.]+)s/it\]', text)[-12:]
        loads = len(re.findall(r'(?i)(loading model|requested to load|loaded completely|load_model)', text))
        if runs: print('ComfyUI-Aufträge zuletzt (Sekunden):', ', '.join(f'{x:.0f}' for x in runs), f'| schnellster {min(runs):.0f}, langsamster {max(runs):.0f}')
        if speeds: print('Sekunden pro Rechenschritt zuletzt:', ', '.join(speeds))
        print('Modell-Ladevorgänge im Protokollausschnitt:', loads, '| RAM-Druck gemeldet:', 'ja' if 'RAM pressure' in text else 'nein')
    advice = []
    if swap_used > 2 * 1024 ** 3: advice.append('WSL lagert aus. Mehr Arbeitsspeicher für WSL freigeben und andere Programme schließen.')
    if total and total < 40 * 1024 ** 3: advice.append(f'WSL hat nur {gb(total)}. Für 14B-Videomodelle sind etwa 48 GB sinnvoll.')
    print('Empfehlung:', ' '.join(advice) or 'Keine Auffälligkeit in den gelesenen Werten.')


def notify_settings():
    try:
        data = json.loads((RUNTIME / 'config/benachrichtigungen.json').read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def cleaner():
    """Removes the notification secrets (bot token, ntfy topic) from any text this report prints."""
    data = notify_settings()
    part = lambda name: data.get(name) if isinstance(data.get(name), dict) else {}
    hidden = [str(x) for x in (part('telegram').get('token'), part('ntfy').get('topic')) if x]

    def clean(text):
        text = str(text or '')
        for value in hidden: text = text.replace(value, '[entfernt]')
        return re.sub(r'cay-studio-[a-z0-9]{24}', '[Thema]', re.sub(r'\d{5,15}:[A-Za-z0-9_-]{20,80}', '[entfernt]', text))
    return clean


def notifications(db=None):
    """Notifications: only whether and how they are connected. Never the bot token or the ntfy topic
    (both are secrets in config/benachrichtigungen.json); error texts are cleaned of them, too."""
    data = notify_settings(); clean = cleaner()
    telegram = data.get('telegram') if isinstance(data.get('telegram'), dict) else {}
    ntfy = data.get('ntfy') if isinstance(data.get('ntfy'), dict) else {}
    state = ['Telegram ' + ('verbunden' if telegram.get('token') and telegram.get('chat') else 'Schlüssel ohne Chat' if telegram.get('token') else 'aus'),
             'ntfy ' + ('an' if ntfy.get('topic') else 'aus')]
    events = data.get('events') if isinstance(data.get('events'), dict) else {}
    names = {'done': 'Fertig', 'turn': 'Du bist dran', 'blocked': 'Angehalten'}
    print('Benachrichtigungen:', ', '.join(state), '| Ereignisse:', ', '.join(n for k, n in names.items() if events.get(k, True)) or 'keine')
    if db is None: return
    try:
        counts = db.execute('SELECT channel,status,COUNT(*) AS n FROM notify_outbox GROUP BY channel,status ORDER BY channel,status').fetchall()
        if counts: print('   Nachrichten:', ', '.join(f'{r["channel"]} {r["status"]} {r["n"]}' for r in counts))
        for r in db.execute('SELECT channel,ok,at,detail FROM notify_status ORDER BY channel').fetchall():
            print(f'   Zuletzt {r["channel"]}: {"ok" if r["ok"] else "Fehler"} {r["at"]} {clean(r["detail"])[:200]}')
    except sqlite3.Error:
        pass


def remote_access():
    """Unterwegs-Zugriff (0.18.1): only on or off; the Tailscale address stays out of the report."""
    try: data = json.loads((RUNTIME / 'config/unterwegs.json').read_text(encoding='utf-8'))
    except (OSError, ValueError): data = {}
    print('Unterwegs-Zugriff:', 'an (Tailscale)' if isinstance(data, dict) and data.get('enabled') and data.get('host') else 'aus')


def main():
    print('CAY STUDIO DIAGNOSE (liest nur, ändert nichts)')
    print('Dashboard:', health())
    print('Aktives Programm:', (RUNTIME / 'current').resolve() if (RUNTIME / 'current').exists() else 'fehlt')
    config = json.loads((RUNTIME / 'config/ablage.json').read_text(encoding='utf-8')); root = Path(config['wsl_root'])
    for label, path in [('Stimmenstudio', BASE / 'envs/studio-voices/bereit.json'), ('Qwen-Dialogmodell', BASE / 'models/studio-voices/Base/bereit.json'),
                        ('Chatterbox', BASE / 'envs/chatterbox/bin/python'), ('Sampler-Adapter', BASE / 'apps/ComfyUI/custom_nodes/cay_studio_sampler/__init__.py')]:
        print(f'{label}: {"vorhanden" if path.exists() else "FEHLT"}')
    loras = BASE / 'apps/ComfyUI/models/loras'
    fast = sorted(str(x.relative_to(loras)) for x in loras.rglob('*.safetensors')
                  if any(k in x.name.lower() or k in str(x.parent).lower() for k in ('lightx2v', 'lightning', '4steps'))) if loras.is_dir() else []
    print('Schnell-Gewichte (LoRA):', fast or 'KEINE gefunden – „Schnell“ braucht zuerst „Animation einrichten“')
    try:
        smi = subprocess.run([shutil.which('nvidia-smi') or '/usr/lib/wsl/lib/nvidia-smi', '--query-gpu=name,memory.used,memory.total,utilization.gpu',
                              '--format=csv,noheader'], capture_output=True, text=True, timeout=20)
        print('GPU jetzt:', smi.stdout.strip() or smi.stderr.strip())
    except (OSError, subprocess.SubprocessError) as error: print('GPU jetzt: nicht lesbar', error)
    db = sqlite3.connect(f'file:{RUNTIME / "data/cay_studio.sqlite3"}?mode=ro', uri=True); db.row_factory = sqlite3.Row
    pc_team()
    notifications(db)
    remote_access()
    rows =db.execute('SELECT * FROM factory_runs ORDER BY updated DESC LIMIT 3').fetchall()
    for row in rows: project(row, root, db)
    for name, count in (('dashboard.log', 25), ('comfyui.log', 40)):
        log = RUNTIME / 'logs' / name
        if log.is_file():
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 60000)); text = stream.read().decode(errors='replace')
            print(f'\nLetzte Meldungen {name}:'); print(cleaner()('\n'.join(text.splitlines()[-count:])))


if __name__ == '__main__':
    try: main()
    except Exception as error: print('DIAGNOSE UNVOLLSTÄNDIG:', repr(error))
