#!/usr/bin/env python3
"""Start the existing Cay Studio installation; no downloads, resets or kills."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request

RUNTIME=Path('/home/alihu/ki-video/studio')
URL='http://127.0.0.1:8787'

def health():
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(URL+'/api/health',timeout=4) as response:return json.load(response)
    except (OSError,ValueError):return None

def logs():
    print('\nDie letzten Dashboard-Meldungen:')
    path=RUNTIME/'logs/dashboard.log'
    if path.exists():
        with path.open('rb') as f:
            f.seek(max(0,path.stat().st_size-14000));text=f.read().decode('utf-8',errors='replace')
        print('\n'.join(text.splitlines()[-45:]))
    else:print('Noch keine dashboard.log vorhanden.')

def main():
    print('CAY STUDIO - START UND DIAGNOSE',flush=True)
    if sys.platform!='linux':
        print('Bitte Cay_Studio_Starten.cmd doppelklicken oder im Ubuntu-Terminal starten.');return 1
    config_path=RUNTIME/'config/ablage.json'
    if not config_path.is_file():
        print('Die Studio-Konfiguration fehlt in dieser WSL-Distribution: '+str(config_path));return 1
    config=json.loads(config_path.read_text(encoding='utf-8'));root=Path(config['wsl_root'])
    print('Projektablage: '+str(root));print('Aktives Programm: '+str((RUNTIME/'current').resolve()))
    if not root.is_dir():print('Die Projektablage ist nicht erreichbar. Ist Laufwerk D: vorhanden?');return 1
    python=RUNTIME/'venv/bin/python'
    launcher=RUNTIME/'current/launcher.py'
    if not launcher.is_file():launcher=RUNTIME/'start_studio.py'
    if not python.is_file() or not launcher.is_file():
        print('Vorhandener Studio-Starter oder Dashboard-Python fehlt. Keine Neuinstallation ausgeführt.');logs();return 1
    info=health()
    if info and info.get('app')=='CayStudio':
        if info.get('root')!=str(root.resolve()):
            print('Port 8787 gehört zu einer anderen Cay-Studio-Ablage. Nichts beendet.');return 1
        print('Dashboard antwortet bereits: Version '+str(info.get('version')),flush=True)
    else:
        with socket.socket() as sock:
            sock.settimeout(2);occupied=sock.connect_ex(('127.0.0.1',8787))==0
        if occupied:
            print('Port 8787 ist belegt, aber Cay Studio antwortet dort nicht korrekt. Kein Prozess wurde beendet.');logs();return 1
    print('Starte bzw. übernehme Dashboard, ComfyUI und Ollama. Das kann beim ersten Start etwas dauern.',flush=True)
    env=os.environ.copy();env['CAY_STUDIO_RUNTIME']=str(RUNTIME)
    result=subprocess.run([str(python),str(launcher)],env=env)
    info=health()
    if not info or info.get('app')!='CayStudio':
        print('Dashboard ist noch nicht erreichbar.');logs();return 1
    print('\nDASHBOARD ANTWORTET: '+URL,flush=True)
    print('Version: '+str(info.get('version'))+' | Wartungsmodus: '+str(info.get('maintenance',False)))
    if info.get('maintenance'):print('Das Dashboard befindet sich im Wartungsmodus. Ein eventuell laufendes Update zuerst abschließen lassen.')
    print('Unter Windows wird jetzt zusätzlich die Verbindung zum Browser geprüft.',flush=True)
    return result.returncode

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as error:print('STARTFEHLER: '+str(error),flush=True);sys.exit(1)
