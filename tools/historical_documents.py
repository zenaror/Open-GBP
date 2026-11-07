"""Immutable text oracles for regressions of previously published behavior.

This reads existing Git objects, never a private service or a fallback copy.
It is not the project's current state. Non-oracle files always use the working
tree, so source mutations and missing public files remain visible to tests.
"""
import builtins
from functools import lru_cache
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((Path(__file__).with_suffix('.json')).read_text())
REVISION = MANIFEST['revision']


def relative_document(path):
    if isinstance(path, int):
        return None
    try:
        p = Path(os.fspath(path))
        if not p.is_absolute():
            p = Path.cwd() / p
        rel = p.resolve().relative_to(ROOT).as_posix()
    except (TypeError, ValueError):
        return None
    return rel if rel in MANIFEST['documents'] else None


@lru_cache(maxsize=None)
def _blob(relative, expected):
    result = subprocess.run(['git', '-C', str(ROOT), 'show', REVISION + ':' + relative],
                            capture_output=True, check=False)
    if result.returncode:
        raise AssertionError('Historical regression revision unavailable: ' + REVISION +
                             '. Use a full Git clone; this oracle must not silently skip.')
    if hashlib.sha256(result.stdout).hexdigest() != expected:
        raise AssertionError('Historical document digest mismatch: ' + relative)
    return result.stdout


def document_bytes(relative):
    """Only explicitly pinned paths are accepted; arbitrary Git reads are refused."""
    if relative not in MANIFEST['documents']:
        raise ValueError('Not a pinned historical document: ' + relative)
    return _blob(relative, MANIFEST['documents'][relative])


def open_document(path, mode='r', *args, **kwargs):
    relative = relative_document(path)
    if relative is None:
        return builtins.open(path, mode, *args, **kwargs)
    if any(c in mode for c in 'wax+'):
        raise ValueError('Historical regression oracles are read-only')
    raw = document_bytes(relative)
    if 'b' in mode:
        return io.BytesIO(raw)
    return io.StringIO(raw.decode(kwargs.get('encoding') or 'utf-8',
                                 errors=kwargs.get('errors') or 'strict'))


def read_text(path, encoding=None, errors=None):
    with open_document(path, encoding=encoding or 'utf-8', errors=errors or 'strict') as stream:
        return stream.read()


def read_bytes(path):
    with open_document(path, 'rb') as stream:
        return stream.read()
