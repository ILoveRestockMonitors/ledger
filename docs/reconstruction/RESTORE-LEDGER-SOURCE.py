#!/usr/bin/env python3
"""Recover the pinned Ledger source from its self-contained Markdown manual."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re

RECORD = re.compile(
    r'^<!-- LEDGER_SOURCE (\{[^\r\n]+\}) -->\n'
    r'(?P<fence>`{12,})(?:[a-z0-9_-]+)?\n'
    r'(?P<payload>.*?)\n(?P=fence)\n<!-- END_LEDGER_SOURCE -->',
    re.MULTILINE | re.DOTALL,
)


def extract(manual, destination, with_mobile=False):
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError('Destination must be a new directory; existing files will not be overwritten.')
    text = Path(manual).read_bytes().decode('utf-8')
    parsed = []
    seen = set()
    for match in RECORD.finditer(text):
        meta = json.loads(match.group(1))
        name = meta['path']
        path = PurePosixPath(name)
        if (path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name
                or not path.parts or path.parts[0] == '.git' or name in seen):
            raise ValueError('Unsafe or duplicate source path: ' + name)
        seen.add(name)
        payload = match.group('payload')
        if meta['encoding'] == 'base64':
            data = base64.b64decode(''.join(payload.split()), validate=True)
        elif meta['encoding'] == 'utf-8':
            data = payload.encode('utf-8')
        else:
            raise ValueError('Unknown encoding: ' + name)
        if len(data) != meta['bytes'] or hashlib.sha256(data).hexdigest() != meta['sha256']:
            raise ValueError('Content check failed: ' + name)
        parsed.append((path, data, int(meta['mode'], 8)))
    if len(parsed) != 75:
        raise ValueError(f'Expected 75 source records; found {len(parsed)}. The manual may be incomplete.')
    if with_mobile:
        mobile_record = re.compile(RECORD.pattern.replace('LEDGER_SOURCE', 'LEDGER_MOBILE_SOURCE'), RECORD.flags)
        expected = {'web/index.html', 'web/mobile.css', 'web/mobile.js', 'web/manifest.json',
                    'web/apple-touch-icon.png', 'web/icon-192.png', 'web/icon-512.png',
                    'web/comfort.js', 'tests/test_finance.py'}
        overlay = {}
        for match in mobile_record.finditer(text):
            meta = json.loads(match.group(1))
            name = meta['path']
            if name not in expected or name in overlay:
                raise ValueError('Unexpected or duplicate mobile source: ' + name)
            payload = match.group('payload')
            if meta['encoding'] == 'base64':
                data = base64.b64decode(''.join(payload.split()), validate=True)
            elif meta['encoding'] == 'utf-8':
                data = payload.encode('utf-8')
            else:
                raise ValueError('Unknown mobile encoding: ' + name)
            if len(data) != meta['bytes'] or hashlib.sha256(data).hexdigest() != meta['sha256']:
                raise ValueError('Mobile content check failed: ' + name)
            overlay[name] = (PurePosixPath(name), data, int(meta['mode'], 8))
        if set(overlay) != expected:
            raise ValueError('Expected all nine update source records.')
        combined = {str(path): (path, data, mode) for path, data, mode in parsed}
        combined.update(overlay)
        parsed = list(combined.values())
    destination.mkdir(parents=True, exist_ok=False)
    for path, data, mode in parsed:
        target = destination.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if os.name != 'nt':
            target.chmod(mode & 0o777)
    print(f'Restored and SHA256-verified {len(parsed)} files into {destination.resolve()}')
    return len(parsed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manual', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--with-mobile', action='store_true', help='Apply the verified phone-layout and home-screen overlay')
    args = parser.parse_args()
    extract(args.manual, args.destination, with_mobile=args.with_mobile)
