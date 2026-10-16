"""Installer (Cay_Studio_Update_Produktion.py): an older update never replaces a newer studio,
running or stopped; an upgrade, a reinstall and an unnamed base install still go through.
Only activate() runs; stopping, starting, backup and the release switch are recorded."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def installer(monkeypatch, tmp_path, installed, running):
    spec = importlib.util.spec_from_file_location('cay_update', ROOT / 'Cay_Studio_Update_Produktion.py')
    up = importlib.util.module_from_spec(spec); spec.loader.exec_module(up)
    monkeypatch.setattr(up, 'VERSION', '0.18.0')
    runtime = tmp_path / 'studio'; root = tmp_path / 'Cay_Studio'; root.mkdir()
    old = runtime / 'releases' / installed; old.mkdir(parents=True)
    (runtime / 'current').symlink_to(old, target_is_directory=True)
    release = runtime / 'releases' / '0.18.0_abcdef123456'; release.mkdir()
    version = installed.split('_', 1)[0]
    info = {'app': 'CayStudio', 'root': str(root.resolve()), 'version': version, 'pid': 1}
    steps = []
    answers = {'jobs_exist': False, 'http_json': {'csrf': 't'}, 'start_dashboard': {'version': '0.18.0', 'root': str(root.resolve())}}
    monkeypatch.setattr(up, 'health', lambda url: info if running else None)
    for name in ('jobs_exist', 'verify_process', 'stop_dashboard', 'backup_database', 'install_sampler_adapter', 'switch_release', 'start_dashboard', 'http_json'):
        monkeypatch.setattr(up, name, lambda *a, name=name, **k: steps.append(name) or answers.get(name))
    return up, runtime, root, release, steps


@pytest.mark.parametrize('running', [True, False])
def test_an_older_update_never_replaces_a_newer_studio(monkeypatch, tmp_path, running):
    up, runtime, root, release, steps = installer(monkeypatch, tmp_path, '0.19.0_0123456789ab', running)
    with pytest.raises(RuntimeError, match='schon die neuere Version 0.19.0 installiert'):
        up.activate(runtime, root, release, 'http://127.0.0.1:9')
    assert steps == [] and (runtime / 'current').resolve().name == '0.19.0_0123456789ab'      # nothing stopped, saved or switched


@pytest.mark.parametrize('installed', ['0.17.0_139e893ce379', '0.9.0_aaaaaaaaaaaa', 'cay_studio_app'])
def test_upgrades_and_unnamed_installs_still_go_through(monkeypatch, tmp_path, installed):
    up, runtime, root, release, steps = installer(monkeypatch, tmp_path, installed, False)
    up.activate(runtime, root, release, 'http://127.0.0.1:9')
    assert 'switch_release' in steps and 'start_dashboard' in steps
