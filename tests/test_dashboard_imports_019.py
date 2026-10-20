"""Cay 0.19.0: "UPDATE ANGEHALTEN: Neue Dashboard-Version startet nicht." voice_reference.py imported numpy at the top,
and the dashboard venv on Cay's PC has only requirements.lock (no numpy, no torch). The installer rolled back.
Every module the dashboard loads must import without numpy/torch/soundfile; heavy work runs in the voice env."""
import ast
import json
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'cay_studio_app'
PY = sys.executable
BLOCK = "import sys\nfor m in ('numpy','torch','soundfile','torchaudio','demucs'): sys.modules[m]=None\n"


def test_the_dashboard_starts_without_numpy_and_torch():
    code = BLOCK + f"sys.path.insert(0,{str(APP)!r})\nimport os\nos.environ.setdefault('CAY_STUDIO_RUNTIME','/nonexistent')\n" \
        "import importlib\nfor m in ('factory','factory_quality','factory_video','factory_audio','voice_reference','tts_text','shot_design','steady_files','own_script','autopilot','render_studio'):\n    importlib.import_module(m)\nprint('ok')"
    r = subprocess.run([PY, '-c', code], capture_output=True, text=True, cwd=str(APP))
    assert r.returncode == 0 and r.stdout.strip().endswith('ok'), r.stderr[-1500:]


def test_no_module_of_the_app_imports_numpy_at_the_top():
    lock = (APP / 'requirements.lock').read_text().lower()
    for path in APP.glob('*.py'):
        for node in ast.parse(path.read_text(encoding='utf-8')).body:          # top level only; function-level imports run in their env
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
            for name in names:
                top = name.split('.')[0]
                assert top not in ('numpy', 'torch', 'soundfile', 'torchaudio') or top in lock, f'{path.name}: top-level import {name}'


def test_cleaning_runs_in_the_voice_env_when_the_dashboard_has_no_numpy(tmp_path):
    import math, wave
    from array import array
    sample = tmp_path / 'probe.wav'
    with wave.open(str(sample), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(array('h', (int(2000 * math.sin(i * .05) * (1 if (i // 6000) % 2 else .02)) for i in range(24000 * 8))).tobytes())
    code = BLOCK + f"sys.path.insert(0,{str(APP)!r})\nimport voice_reference, json\nprint(json.dumps(voice_reference.clean({str(sample)!r}, {PY!r})))"
    r = subprocess.run([PY, '-c', code], capture_output=True, text=True, cwd=str(APP))
    assert r.returncode == 0, r.stderr[-1500:]
    info = json.loads(r.stdout.strip().splitlines()[-1])
    assert Path(info['file']).is_file() and 'level' in info['steps'] and info['source_sha256']
