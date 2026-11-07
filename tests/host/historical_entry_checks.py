"""Run the original entry-policy assertions unchanged at their fixed revision."""
from functools import lru_cache
from pathlib import Path
import ast
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from archived_documents import REVISION

ROOT = Path(__file__).resolve().parents[2]
MODULES = ('test_handoff.py', 'test_onboarding.py', 'test_agents_md_alignment.py')


@lru_cache(maxsize=1)
def results():
    with tempfile.TemporaryDirectory(prefix='open-gbp-historical-entry-') as tmp:
        repo = Path(tmp) / 'repo'
        subprocess.run(['git', 'clone', '--shared', '--no-checkout', str(ROOT), str(repo)],
                       check=True, capture_output=True)
        subprocess.run(['git', '-C', str(repo), 'checkout', '--detach', REVISION],
                       check=True, capture_output=True)
        subprocess.run(['python3', str(repo / 'tools/history_recover.py')],
                       check=True, capture_output=True)
        expected = {
            (name[:-3], node.name)
            for name in MODULES
            for node in ast.walk(ast.parse((repo / 'tests/host' / name).read_text()))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith('test_')
        }
        env = dict(os.environ)
        env.pop('PYTEST_ADDOPTS', None)
        report = Path(tmp) / 'results.xml'
        run = subprocess.run(['python3', '-m', 'pytest', '-q', '-ra',
                              '--junitxml=' + str(report),
                              *('tests/host/' + name for name in MODULES)],
                             cwd=repo, env=env, capture_output=True, text=True, timeout=180)
        if run.returncode:
            raise AssertionError('Original historical entry checks failed:\n' +
                                 run.stdout + run.stderr)
        cases = ET.parse(report).findall('.//testcase')
        if len(cases) < len(expected) or any(c.find('skipped') is not None for c in cases):
            raise AssertionError('Historical entry checks must execute without skips')
        for module, method in expected:
            if not any(module in case.get('classname', '') and
                       case.get('name', '').split('[', 1)[0] == method
                       for case in cases):
                raise AssertionError('Historical assertion did not execute: ' + module + '.' + method)
        return len(cases), run.stdout
