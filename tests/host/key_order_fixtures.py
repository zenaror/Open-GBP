"""Minimal public excerpts for historical keypad/order checks, never raw captures."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'captures/fixtures/key-order'
PATTERN = rb'^\d+ (?:KEY |KEYLOG |SESSION |STARTUPT )'


def extract(raw, run):
    pattern = PATTERN if run in (25, 26) else rb'^\d+ STARTUPT '
    return b''.join(line for line in raw.splitlines(keepends=True) if re.match(pattern, line))


def manifest():
    return json.loads((FIXTURES / 'manifest.json').read_text())


def read_excerpt(run):
    entry = manifest()['runs'][str(run)]
    raw = (FIXTURES / entry['file']).read_bytes()
    if len(raw) != entry['excerpt_bytes'] or hashlib.sha256(raw).hexdigest() != entry['excerpt_sha256']:
        raise AssertionError('Public key-order excerpt integrity mismatch: RUN ' + str(run))
    return raw.decode('utf-8')
