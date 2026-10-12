#!/usr/bin/env python3
"""Cay Studio Diagnose: reads facts about the newest projects. Changes nothing.

Database opened read-only, no downloads, no restarts, no deletions.
Output goes to the console; Cay_Studio_Diagnose.cmd also saves it as text.
"""
import json
import os
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


def project(row, root):
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
    lines = d.get('lines', [])
    print('Erzeugte Sprachdateien:', len(lines), '| Sprachmodell:', d.get('audio_engine'), '| Neuaufnahmen:', d.get('speech_takes'))
    for line in lines[:12]:
        exists = Path(line.get('file', '')).is_file()
        print(f'   F{line.get("episode", 0) + 1} S{line.get("scene", 0) + 1} {line.get("speaker")}: {line.get("duration", 0):.2f} s, '
              f'Datei {"da" if exists else "FEHLT"}, Text: {str(line.get("text", ""))[:60]}')
    for t in d.get('timing', []): print('Zeitplan:', {k: t.get(k) for k in ('seconds', 'speech_seconds', 'speech_share', 'longest_speech_gap')})
    print('Fehler:', (d.get('error') or '-')[:600], '| Fortsetzen bei:', d.get('resume_state'))
    folder = root / '01_Projekte' / 'Studio' / str(d.get('id'))
    if folder.is_dir():
        for mix in newest_mix(folder): print('Tonmischung:', json.dumps(mix, ensure_ascii=False)[:900])
    for preview in d.get('previews', []): print('Tonvorschau', preview.get('episode'), loudness(preview.get('file', '')))
    for export in d.get('exports', []): print('Fertiges Video', export.get('file'), loudness(export.get('file', '')))


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
    rows = db.execute('SELECT * FROM factory_runs ORDER BY updated DESC LIMIT 3').fetchall()
    for row in rows: project(row, root)
    for name, count in (('dashboard.log', 25), ('comfyui.log', 40)):
        log = RUNTIME / 'logs' / name
        if log.is_file():
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 60000)); text = stream.read().decode(errors='replace')
            print(f'\nLetzte Meldungen {name}:'); print('\n'.join(text.splitlines()[-count:]))


if __name__ == '__main__':
    try: main()
    except Exception as error: print('DIAGNOSE UNVOLLSTÄNDIG:', repr(error))
