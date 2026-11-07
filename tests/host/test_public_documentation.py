"""Current contributor entry points must work without private context."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUIDES = ('AGENTS.md', 'README.md', 'docs/README.md', 'docs/DEVELOPMENT.md',
          'docs/VALIDATION.md', 'docs/RESEARCH_METHOD.md', 'docs/ROADMAP.md')
RETIRED = ('INITIAL_PROMPT.md', 'docs/HANDOFF.md', 'docs/ONBOARDING.md',
           *('docs/research/' + n + '.md' for n in (
               'DEVLOG', 'EVIDENCE', 'HARDWARE_TESTS', 'UNKNOWNS', 'GBC_PATH',
               'INPUT_PATH', 'VIDEO_PATH', 'PHASE4_ASSESSMENT', 'PHASE5_ASSESSMENT',
               'PHASE6_ENTRY', 'PHASE7_ENTRY')))


class PublicDocumentation(unittest.TestCase):
    def test_working_records_are_retired(self):
        for path in RETIRED:
            self.assertFalse((ROOT / path).exists(), path)

    def test_entry_is_compact_and_self_contained(self):
        agent = (ROOT / 'AGENTS.md').read_text()
        self.assertLess(len(agent.splitlines()), 100)
        for path in GUIDES:
            text = (ROOT / path).read_text()
            self.assertNotRegex(text, r'(?i)\bOMM\b|/home/[^/\s]+|OneMindMachine|plugin://')
        for term in ('physical', 'SHA-256', 'Link Port', 'rumble', 'dirty build',
                     'read-only', 'bounded waits', 'RAM', 'force-push'):
            self.assertIn(term, agent)

    def test_public_method_preserves_distinct_scientific_contracts(self):
        method = re.sub(r'\s+', ' ', (ROOT / 'docs/RESEARCH_METHOD.md').read_text())
        for phrase in ('before opening or interpreting new machine',
                       'later direct', 'ordinal position', 'append a visible pointer',
                       'inside the instrument span', 'worst-case arithmetic',
                       'false-positive rates', 'affected code',
                       'local commit graph', 'deferral names',
                       'does not replace the content'):
            self.assertIn(phrase, method)

    def test_tracked_public_markdown_links_resolve(self):
        paths = subprocess.check_output(['git', 'ls-files', '*.md'], cwd=ROOT, text=True).splitlines()
        for name in paths + list(GUIDES):
            path = ROOT / name
            if not path.exists():
                continue
            text = re.sub(r'```.*?```', '', path.read_text(), flags=re.S)
            for target in re.findall(r'\]\(([^)\s]+)\)', text):
                if re.match(r'(?:[a-z]+:|#)', target):
                    continue
                target = target.split('#', 1)[0]
                self.assertTrue((path.parent / target).exists(), '%s -> %s' % (name, target))
