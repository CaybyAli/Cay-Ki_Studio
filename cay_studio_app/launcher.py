"""One-click WSL service launcher. Reuses existing services; never kills jobs."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

RUNTIME = Path(os.environ.get('CAY_STUDIO_RUNTIME', '/home/alihu/ki-video/studio'))
BASE = RUNTIME.parent
CONFIG = json.loads((RUNTIME / 'config/ablage.json').read_text(encoding='utf-8'))
RELEASE = Path(__file__).resolve().parent
PORT = int(os.environ.get('CAY_STUDIO_PORT', '8787'))
URL = f'http://127.0.0.1:{PORT}'
LOGS = RUNTIME / 'logs'
LOGS.mkdir(parents=True, exist_ok=True)


def get(url):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=2) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def wait(url, seconds=60):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        data = get(url)
        if data is not None: return data
        time.sleep(.6)
    return None


def occupied(port):
    with socket.socket() as sock:
        sock.settimeout(.5)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def spawn(name, args, cwd, env=None):
    record = LOGS / (name + '_prozess.json')
    if record.is_file():
        try:
            pid = json.loads(record.read_text())['pid']
            cmdline = Path(f'/proc/{pid}/cmdline').read_bytes().decode(errors='replace')
            if [x for x in cmdline.split('\0') if x]==list(map(str,args)):
                return pid
        except (OSError, ValueError, KeyError):
            pass
    with (LOGS / (name + '.log')).open('ab') as log:
        process = subprocess.Popen(args, cwd=str(cwd), env=env,
                                   stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                   start_new_session=True)
    record.write_text(json.dumps({'pid': process.pid, 'args': args}), encoding='utf-8')
    return process.pid


def ensure_comfy():
    url = CONFIG['local_services']['comfyui'] + '/system_stats'
    if get(url) is not None: return 'ComfyUI: vorhandenen Dienst übernommen.'
    address=urlsplit(CONFIG['local_services']['comfyui']);port=address.port or 8188
    if address.hostname not in ('localhost','127.0.0.1'):return 'ComfyUI: konfigurierter externer Dienst nicht erreichbar; bitte dort starten.'
    if occupied(port): return f'ComfyUI: Port {port} ist belegt; keine zweite Instanz gestartet.'
    python = BASE / 'envs/comfyui/bin/python'
    app = BASE / 'apps/ComfyUI'
    if not python.is_file() or not (app / 'main.py').is_file():
        return 'ComfyUI: vorhandene Installation nicht gefunden. Pfade prüfen.'
    spawn('comfyui', [str(python), str(app / 'main.py'), '--listen', '127.0.0.1', '--port', str(port), '--disable-auto-launch'], app)
    return ('ComfyUI: gestartet.' if wait(url, 100) is not None else
            'ComfyUI: noch nicht erreichbar. Log: ' + str(LOGS / 'comfyui.log'))


def ensure_ollama():
    url = CONFIG['local_services']['ollama'] + '/api/version'
    if get(url) is not None: return 'Ollama: vorhandenen Dienst übernommen.'
    address=urlsplit(CONFIG['local_services']['ollama']);port=address.port or 11434
    if address.hostname not in ('localhost','127.0.0.1'):return 'Ollama: konfigurierter externer Dienst nicht erreichbar; bitte dort starten.'
    if occupied(port): return f'Ollama: Port {port} ist belegt; keine zweite Instanz gestartet.'
    # Use an existing service first, without password prompts or installing anything.
    if port==11434 and shutil.which('systemctl'):
        for scope in (['--user'], []):
            try:
                check = subprocess.run(['systemctl', *scope, 'show', '-p', 'LoadState', '--value', 'ollama.service'],
                                       capture_output=True, text=True, timeout=4)
                if check.stdout.strip() != 'loaded': continue
                result = subprocess.run(['systemctl', *scope, '--no-ask-password', 'start', 'ollama.service'],
                                        capture_output=True, text=True, timeout=15)
                if result.returncode == 0 and wait(url, 12) is not None:
                    return 'Ollama: vorhandenen Systemdienst gestartet.'
            except (OSError, subprocess.TimeoutExpired):
                pass
    # Fallback only with an existing readable model store: no empty second installation.
    stores = [Path(os.environ['OLLAMA_MODELS'])] if os.environ.get('OLLAMA_MODELS') else []
    stores += [Path.home() / '.ollama/models', Path('/usr/share/ollama/.ollama/models'), BASE / 'models/ollama']
    binary = shutil.which('ollama')
    for store in stores:
        model=CONFIG.get('planner_model','qwen3.8:27b');name,_,tag=model.partition(':')
        manifest=store/'manifests/registry.ollama.ai/library'/name/(tag or 'latest')
        if not binary or not os.access(manifest, os.R_OK): continue
        env = os.environ.copy()
        env.update(OLLAMA_MODELS=str(store), OLLAMA_HOST=f'127.0.0.1:{port}', OLLAMA_NUM_PARALLEL='1', OLLAMA_MAX_LOADED_MODELS='1')
        spawn('ollama', [binary, 'serve'], RUNTIME, env)
        if wait(url, 20) is not None: return 'Ollama: mit vorhandenem Modellordner gestartet.'
        break
    return 'Ollama: Start noch nicht möglich. Vorhandenen Dienst starten; es wurde kein Modell heruntergeladen.'


def browser():
    binary = shutil.which('explorer.exe')
    if not binary:
        candidate = Path('/mnt/c/Windows/explorer.exe')
        if candidate.exists(): binary = str(candidate)
    if binary:
        try:
            subprocess.Popen([binary, f'http://localhost:{PORT}'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


def main():
    if not Path(CONFIG['wsl_root']).is_dir():
        raise RuntimeError('Die Ablage auf D: ist nicht erreichbar. Laufwerk prüfen.')
    with (RUNTIME / 'start.lock').open('a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Cay Studio wird bereits gestartet. Einen Moment bitte.', flush=True)
            if wait(URL + '/api/health', 20) and '--open-browser' in sys.argv: browser()
            return
        existing = get(URL + '/api/health')
        if existing and existing.get('app') == 'CayStudio':
            if existing.get('root') != str(Path(CONFIG['wsl_root']).resolve()):
                raise RuntimeError('Auf diesem Port läuft Cay Studio mit einer anderen Ablage.')
            print('Dashboard: vorhandene Instanz übernommen.', flush=True)
        else:
            if occupied(PORT):
                raise RuntimeError(f'Port {PORT} wird von einem anderen Dienst verwendet. Es wurde nichts beendet.')
            spawn('dashboard', [sys.executable, str(RELEASE / 'server.py')], RELEASE)
            if not wait(URL + '/api/health', 20):
                raise RuntimeError('Dashboard startet nicht. Log: ' + str(LOGS / 'dashboard.log'))
            print('Dashboard: gestartet.', flush=True)
        if '--open-browser' in sys.argv: browser()
        print('Prüfe die vorhandenen Dienste …', flush=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(ensure_comfy), pool.submit(ensure_ollama)]
            for future in futures:
                try: print(future.result(), flush=True)
                except Exception as error: print('Dienststart: ' + str(error), flush=True)
        print('\nDASHBOARD: http://127.0.0.1:' + str(PORT), flush=True)
        print('Ob alle KI-Dienste bereit sind, steht in den Meldungen oben und im Systemstatus.',flush=True)
        print('Browser schließen beendet die Hintergrunddienste nicht.', flush=True)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('STARTFEHLER: ' + str(error), file=sys.stderr)
        sys.exit(1)
