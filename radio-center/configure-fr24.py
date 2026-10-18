#!/usr/bin/python3
"""Configure the local Beast source without printing the FR24 sharing key."""
import getpass
import grp
import os
import re
from pathlib import Path


def configure(text, key):
    if not re.fullmatch(r'[A-Za-z0-9]{16}', key):
        raise ValueError('Sharing key musí mít 16 písmen nebo číslic.')
    values = {'receiver': 'beast-tcp', 'host': '127.0.0.1:30005',
              'fr24key': key, 'bs': 'no', 'raw': 'no', 'mlat': 'no',
              'mlat-without-gps': 'no', 'bind-interface': '127.0.0.1'}
    lines = [line for line in text.splitlines()
             if line.split('=', 1)[0].strip() not in {*values, 'path', 'procargs'}]
    return '\n'.join(lines + [f'{name}="{value}"' for name, value in values.items()]) + '\n'


if __name__ == '__main__':
    path = Path('/etc/fr24feed.ini')
    text = path.read_text() if path.exists() else ''
    match = re.search(r'^fr24key\s*=\s*"?([A-Za-z0-9]{16})"?\s*$', text, re.M)
    key = match[1] if match else getpass.getpass('Flightradar24 sharing key (skrytý vstup): ').strip()
    result = configure(text, key)
    feeder_group = grp.getgrnam('fr24').gr_gid
    # Create private from the beginning; never expose the key in stdout or argv.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as output:
        os.fchown(output.fileno(), 0, feeder_group)
        os.fchmod(output.fileno(), 0o640)
        output.write(result)
