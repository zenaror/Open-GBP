"""
tests/host/test_page_citations.py — the cheap mechanical half of GitHub Issue
#29: every evidence id a consolidated page cites must EXIST.

Issue #29 asked whether a guard could compare a consolidated page's status with
the status `EVIDENCE.md` carries for the same id, and invited the answer "the
pages are not machine-readable enough for that" if that is what the data says.
IT IS WHAT THE DATA SAYS, measured on 2026-09-21 and recorded in
`tools/reconcile.py`'s header: of 278 table rows, 44 carry both a status letter
and a defined id, and 8 of those 44 read "weaker" than their evidence under a
naive comparison — all 8 CORRECTLY, because a row's status is compound and
aspect-scoped ("C (format and polarity …); F (hw, run-scoped)") while an
EVIDENCE entry has one status for one claim. A gate on that comparison would be
~18 % false on the rows it can see and blind to the rest, and it would be
switched off within two checkpoints. The sweep is a REPORT a person reads
(`tools/reconcile.py`), instructed by `RESEARCH_METHOD.md`'s promotion section.

What IS a gate is this: a citation that does not resolve. A page pointing at an
id nothing defines is unambiguous drift — the id was renamed, retired or never
written — and it cannot be argued about. That is checked here, for every page,
on every run.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
HW_TESTS = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
PAGE_DIRS = ("docs/protocol", "docs/hardware")
ID = re.compile(r"\b((?:GBP|ENV)-[A-Z]+-\d{3}|U-(?:GBP|ENV)-\d{3})\b")
# families that name an EXPERIMENT rather than a piece of evidence; they are defined in HARDWARE_TESTS.md
# and are listed here so the exclusion is deliberate and reviewable, never an accident of a regex
TEST_FAMILIES = ("VIDEO", "INIT", "AV", "PROBE", "BASELINE", "PLAY", "INPUT", "BBA")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def defined_ids():
    out = set()
    for p in (EVIDENCE, UNKNOWNS):
        for m in re.finditer(r"^#{2,4} +((?:GBP|ENV)-[A-Z]+-\d{3}|U-(?:GBP|ENV)-\d{3})\b", read(p), re.M):
            out.add(m.group(1))
    return out


def pages():
    for d in PAGE_DIRS:
        full = os.path.join(ROOT, d)
        for fn in sorted(os.listdir(full)):
            if fn.endswith(".md"):
                yield os.path.join(d, fn), read(os.path.join(full, fn))


class EveryCitationResolves(unittest.TestCase):
    def test_no_consolidated_page_cites_an_id_nothing_defines(self):
        defined = defined_ids()
        missing = []
        for rel, t in pages():
            for n, line in enumerate(t.splitlines(), 1):
                for i in ID.findall(line):
                    if i in defined or i.split("-")[1] in TEST_FAMILIES:
                        continue
                    missing.append("%s:%d cites %s, which no heading in EVIDENCE.md or UNKNOWNS.md defines" % (rel, n, i))
        self.assertEqual(missing, [], "\n".join(missing))

    def test_the_test_id_families_the_pages_may_cite_are_defined_somewhere(self):
        """The exclusion above is not a hole: a test id must still name a real experiment."""
        hw = read(HW_TESTS)
        cited = set()
        for _rel, t in pages():
            cited |= {i for i in ID.findall(t) if i.split("-")[1] in TEST_FAMILIES}
        cited -= defined_ids()
        unknown = sorted(i for i in cited if i not in hw)
        self.assertEqual(unknown, [], "test ids cited by a consolidated page and named nowhere in HARDWARE_TESTS.md: "
                                      + ", ".join(unknown))

    def test_the_pages_cite_enough_to_make_this_worth_checking(self):
        n = sum(len(ID.findall(t)) for _rel, t in pages())
        self.assertGreater(n, 300, "the consolidated pages cite %d ids; if this collapses, the guard is checking nothing" % n)


class TheSweepExistsAndIsInstructed(unittest.TestCase):
    def test_the_tool_reports_and_judges_nothing(self):
        src = read(os.path.join(ROOT, "tools", "reconcile.py"))
        for tok in ("IT JUDGES NOTHING", "--since", "--all", "ESCALATED, never fixed by",
                    "WHY IT IS NOT A GATE, measured rather than assumed"):
            self.assertIn(tok, src, tok)

    def test_the_promotion_section_instructs_the_sweep(self):
        m = read(os.path.join(ROOT, "docs", "RESEARCH_METHOD.md"))
        section = m[m.index("## Documentation promotion"):]
        section = section[:section.index("\n## ")]
        flat = re.sub(r"\s+", " ", section)
        for tok in ("Reconciliation sweep — before promoting anything", "tools/reconcile.py",
                    'including "nothing"', "escalated", "never resolved by editing the page to match a guess",
                    "Why this is an instruction and not a test"):
            self.assertIn(tok, flat, tok)


if __name__ == "__main__":
    unittest.main()
