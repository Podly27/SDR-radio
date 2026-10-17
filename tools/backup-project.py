#!/usr/bin/python3
"""Create a public source/config snapshot and a private, consistent runtime archive.

Run with sudo. Credentials and received data never enter the public snapshot.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ('station.json', 'dashboard-layout.json', 'eme-config.json',
           'meteo-config.json', 'iss-auto-config.json', 'adsb-config.json',
           'ism-tuning.json', 'ft-tuning.json', 'msk-tuning.json', 'sonde-tuning.json')
SECRET_KEYS = {'magic_key', 'receiver_keys', 'receiver_admin', 'google_maps_api_key',
               'openweathermap_api_key', 'password', 'passwd', 'token', 'secret',
               'api_key', 'access_token', 'private_key'}

def clean(value):
    if isinstance(value, dict):
        return {k: ([] if isinstance(v, list) else {} if isinstance(v, dict) else '')
                if k.lower() in SECRET_KEYS or any(x in k.lower() for x in
                  ('password', 'secret', 'token', 'api_key', 'private_key'))
                else clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value

def json_file(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

def output(command):
    return subprocess.run(command, text=True, capture_output=True, check=True).stdout

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--public-dir', type=Path, required=True)
    ap.add_argument('--private-dir', type=Path, required=True)
    args = ap.parse_args()
    public = args.public_dir.resolve()
    private = args.private_dir.resolve()
    public.mkdir(parents=True, exist_ok=True)
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    private.chmod(0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    # Copy only project-owned paths; never copy a parent directory recursively.
    for name in ('radio-center', 'tools', 'docs'):
        if (ROOT/name).exists():
            shutil.copytree(ROOT/name, public/name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'build-work'))
    for name in ('README.md', '.gitignore', 'THIRD-PARTY.md',
                 'configure-radio-bookmarks.py', 'openwebrx-hf-profiles.json',
                 'repeater-import-summary.json'):
        if (ROOT/name).exists():
            copy_file(ROOT/name, public/name)
    config = public/'configuration'
    for name in CONFIGS:
        source = Path('/var/lib/radio-center')/name
        if source.exists():
            json_file(config/'var/lib/radio-center'/name, clean(json.loads(source.read_text())))
    for name in ('settings.json', 'bookmarks.json'):
        source = Path('/var/lib/openwebrx')/name
        if source.exists():
            json_file(config/'var/lib/openwebrx'/name, clean(json.loads(source.read_text())))
    for source in Path('/etc/openwebrx').glob('*'):
        if source.is_file():
            copy_file(source, config/'etc/openwebrx'/source.name)
    for source in Path('/etc/systemd/system').glob('radio-*'):
        if source.is_file() and not source.is_symlink():
            copy_file(source, config/'etc/systemd/system'/source.name)
    for source in (Path('/etc/nginx/sites-available/openwebrx'),
                   Path('/etc/sudoers.d/radio-center')):
        if source.exists():
            copy_file(source, config/source.relative_to('/'))
    inventory = public/'inventory'
    inventory.mkdir(exist_ok=True)
    (inventory/'packages.tsv').write_text(output(['dpkg-query', '-W',
        '-f=${binary:Package}\t${Version}\t${Architecture}\t${db:Status-Abbrev}\n']))
    (inventory/'radio-services.json').write_text(output(['systemctl', 'list-unit-files',
        'radio-*', 'openwebrx.service', '--output=json']))
    json_file(inventory/'system.json', {'captured_utc': stamp,
        'architecture': output(['dpkg', '--print-architecture']).strip(),
        'kernel': output(['uname', '-srmo']).strip(),
        'os_release': Path('/etc/os-release').read_text(),
        'model': Path('/proc/device-tree/model').read_text().strip('\x00')
                 if Path('/proc/device-tree/model').exists() else None})
    # Private archive: live SQLite backup API includes committed WAL data and
    # does not stop receivers. Raw state is for diagnosis, not automatic restore.
    with tempfile.TemporaryDirectory(prefix='radio-private-') as temporary:
        staging = Path(temporary)
        for base in ('/var/lib/radio-center', '/var/lib/openwebrx'):
            source = Path(base)
            target = staging/source.relative_to('/')
            if source.exists():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns(
                    '*.sqlite', '*.sqlite-wal', '*.sqlite-shm', '*.lock',
                    'meteo-work', 'meteo-native-check'))
                for db in source.glob('*.sqlite'):
                    origin = sqlite3.connect('file:'+str(db)+'?mode=ro', uri=True, timeout=10)
                    destination = sqlite3.connect(target/db.name)
                    try:
                        origin.backup(destination)
                        if destination.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                            raise RuntimeError('SQLite integrity check failed: '+str(db))
                    finally:
                        destination.close()
                        origin.close()
        for base in ('/opt/radio-center', '/etc/openwebrx', '/etc/nginx',
                     '/etc/udev/rules.d', '/etc/modprobe.d', '/etc/apt/sources.list.d'):
            source = Path(base)
            if source.exists():
                shutil.copytree(source, staging/source.relative_to('/'), symlinks=True,
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for source in Path('/etc/systemd/system').glob('radio-*'):
            if source.is_file() and not source.is_symlink():
                copy_file(source, staging/source.relative_to('/'))
        copy_file(Path('/etc/sudoers.d/radio-center'), staging/'etc/sudoers.d/radio-center')
        archive = private/('radio-center-private-'+stamp+'.tar.gz')
        with tarfile.open(archive, 'w:gz') as tar:
            for entry in staging.iterdir():
                tar.add(entry, arcname=entry.name)
    archive.chmod(0o600)
    checksum = archive.with_suffix(archive.suffix+'.sha256')
    checksum.write_text(hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
                        +'  '+archive.name+'\n')
    checksum.chmod(0o600)
    # Avoid making publishable config files inaccessible after a sudo export.
    uid, gid = int(os.environ.get('SUDO_UID', os.getuid())), int(os.environ.get('SUDO_GID', os.getgid()))
    for base in (public, private):
        for path in [base, *base.rglob('*')]:
            if path.is_symlink():
                continue
            os.chown(path, uid, gid)
            if base == public:
                path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    print('Public project snapshot:', public)
    print('Private archive (contains credentials; never publish):', archive)

if __name__ == '__main__':
    main()
