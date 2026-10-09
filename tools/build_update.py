#!/usr/bin/env python3
"""Rebuild Cay_Studio_Update_Produktion.py from cay_studio_app/.

The installer logic stays in the existing update script; only VERSION, the
embedded ZIP payload and its SHA256 are replaced. The result is verified by
unpacking it again and comparing every file byte for byte.

Usage: python3 tools/build_update.py
"""
import ast
import base64
import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'cay_studio_app'
UPDATE = ROOT / 'Cay_Studio_Update_Produktion.py'
STAMP = (2026, 1, 1, 0, 0, 0)   # fixed timestamps: same sources give the same payload


def app_version():
    match = re.search(r"^VERSION = '([0-9.]+)'$", (APP / 'server.py').read_text(encoding='utf-8'), re.M)
    if not match: raise SystemExit('VERSION in cay_studio_app/server.py nicht gefunden.')
    return match.group(1)


def payload():
    files = sorted(p for p in APP.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            name = path.relative_to(APP).as_posix()
            data = path.read_bytes()
            if path.suffix == '.py': ast.parse(data.decode('utf-8'), filename=name)
            info = zipfile.ZipInfo(name, STAMP); info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return buffer.getvalue(), {p.relative_to(APP).as_posix(): p.read_bytes() for p in files}


def main():
    version = app_version(); raw, files = payload(); sha = hashlib.sha256(raw).hexdigest()
    if sum(len(v) for v in files.values()) > 5_000_000: raise SystemExit('Paket größer als die Installergrenze von 5 MB.')
    text = UPDATE.read_text(encoding='utf-8')
    previous = re.search(r"^VERSION = '([0-9.]+)'$", text, re.M).group(1)
    replaced = []
    for line in text.split('\n'):
        if line.startswith('PAYLOAD = '): line = 'PAYLOAD = ' + repr(base64.b64encode(raw).decode())
        elif line.startswith('PAYLOAD_SHA256 = '): line = 'PAYLOAD_SHA256 = ' + repr(sha)
        elif previous != version: line = line.replace(previous, version)
        replaced.append(line)
    text = '\n'.join(replaced); ast.parse(text)
    # Verify exactly as the installer will read it.
    tree = ast.parse(text); values = {n.targets[0].id: n.value.value for n in tree.body
                                      if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)}
    check = base64.b64decode(values['PAYLOAD'])
    assert values['VERSION'] == version and hashlib.sha256(check).hexdigest() == values['PAYLOAD_SHA256']
    with zipfile.ZipFile(io.BytesIO(check)) as archive:
        assert sorted(archive.namelist()) == sorted(files)
        assert all(archive.read(name) == data for name, data in files.items())
    UPDATE.write_text(text, encoding='utf-8')
    print(f'{UPDATE.name}: Version {version}, {len(files)} Dateien, Payload-SHA256 {sha}')


if __name__ == '__main__':
    sys.exit(main())
