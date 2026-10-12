"""Issue #164: compare published history with original evidence identities."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'docs/maintenance/ai-coauthor-2026-10-12.json'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args]).decode().strip()


def translate(commit, direction):
    full = git('rev-parse', commit + '^{commit}')
    rows = json.loads(MANIFEST.read_text())['mapping']
    source, target = ('old', 'new') if direction == 'published' else ('new', 'old')
    row = next((r for r in rows if r[source] == full), None)
    if row is None:
        return full
    mapped = row[target]
    if git('rev-parse', full + '^{tree}') != git('rev-parse', mapped + '^{tree}'):
        raise AssertionError('history map changed a tree: ' + full)
    return mapped


def is_ancestor(ancestor, descendant='HEAD'):
    return subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor',
                           translate(ancestor, 'published'), translate(descendant, 'published')],
                          capture_output=True).returncode == 0


def last_original_change(path):
    return translate(git('log', '--format=%H', '-1', '--', path), 'original')
