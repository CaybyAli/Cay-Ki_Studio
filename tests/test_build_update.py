"""tools/build_update.py packs exactly the committed cay_studio_app/: a stray or unsaved file there
stops the build, ignored files (__pycache__) never get in. Runs on a tiny git repository."""
import base64
import importlib.util
import io
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(repo, *args):
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', *args],
                   check=True, capture_output=True)


def builder(monkeypatch, repo):
    spec = importlib.util.spec_from_file_location('build_update', ROOT / 'tools/build_update.py')
    bu = importlib.util.module_from_spec(spec); spec.loader.exec_module(bu)
    monkeypatch.setattr(bu, 'ROOT', repo); monkeypatch.setattr(bu, 'APP', repo / 'cay_studio_app'); monkeypatch.setattr(bu, 'UPDATE', repo / 'Cay_Studio_Update_Produktion.py')
    return bu


def packed(update):
    text = update.read_text(encoding='utf-8')
    raw = base64.b64decode(re.search(r"^PAYLOAD = '([^']*)'$", text, re.M).group(1))
    return sorted(zipfile.ZipFile(io.BytesIO(raw)).namelist())


def test_only_the_committed_app_is_packed(monkeypatch, tmp_path):
    if not shutil.which('git'): pytest.skip('git fehlt')
    repo = tmp_path / 'repo'; app = repo / 'cay_studio_app'; (app / 'web').mkdir(parents=True)
    (app / 'server.py').write_text("VERSION = '0.18.0'\n"); (app / 'web/app.js').write_text('let a = 1;\n')
    (repo / '.gitignore').write_text('__pycache__/\n')
    update = repo / 'Cay_Studio_Update_Produktion.py'; update.write_text("VERSION = '0.17.0'\nPAYLOAD_SHA256 = ''\nPAYLOAD = ''\n")
    git(repo, 'init', '-q'); git(repo, 'add', '-A'); git(repo, 'commit', '-q', '-m', 'app')
    bu = builder(monkeypatch, repo); before = update.read_text()
    stray = app / 'tmp_check/studio/config/benachrichtigungen.json'; stray.parent.mkdir(parents=True); stray.write_text('{"token": "7712345678:AAH"}')
    with pytest.raises(SystemExit, match='fremde Dateien in cay_studio_app'):
        bu.main()
    assert update.read_text() == before                                                    # nothing built
    shutil.rmtree(app / 'tmp_check'); (app / 'server.py').write_text("VERSION = '0.18.0'\nDEBUG = True\n")
    with pytest.raises(SystemExit, match='Ungespeicherte'):                                # changed but not committed
        bu.main()
    git(repo, 'checkout', '--', 'cay_studio_app/server.py')
    (app / '__pycache__').mkdir(); (app / '__pycache__/server.cpython-313.pyc').write_bytes(b'\0')
    bu.main()
    assert packed(update) == ['server.py', 'web/app.js'] and "VERSION = '0.18.0'" in update.read_text()
