"""
tests/host/test_record_ids.py — GitHub Issue #98: what the "expiring pins" were said to protect,
checked on the record itself, computed rather than maintained.

THE PINS, AND WHAT THEY COULD SEE. Twenty host tests pinned the record's CURRENT highest id ("the
highest GBP-HW id is 321", "the highest U-GBP id is 44"); three pinned the NEXT free id or run
number ("GBP-HW-322 is not in EVIDENCE", "RUN 38 is not in HARDWARE_TESTS"); two a window of ids no
record may cite yet. Each said ITS checkpoint minted nothing, and each was moved by hand at every
ingestion that minted something, which is every ingestion. The history records moves and no catch.

The case for keeping them was that a sentinel on the next id makes an accidental REUSE visible.
It cannot: a reused id is an EXISTING number written again, which changes neither the highest id
nor the next free one. `ThePinsCouldNotSeeIt` below builds that reuse and runs both pins on it; both
pass. The pins now read the record at `guards.CHECKPOINTS_CLOSED_AT` (`guards.at_close`), where
they were last true, and are never moved again.

WHAT IS CHECKED HERE INSTEAD, on the record as it is, with nothing to edit when an id is minted:
  * every evidence id is defined by exactly one heading (reuse is caught);
  * every family is numbered from 001 with no gap (a skipped or mistyped number is caught);
  * every evidence id the HANDOFF and the ROADMAP cite is defined (a record citing evidence nobody
    has written is caught -- the pages in docs/protocol and docs/hardware already are, by
    test_page_citations.py).

WHAT IT DOES NOT DO. It cannot tell whether a checkpoint that should mint nothing (a build, a
pre-registration) minted something: that depends on what kind of checkpoint is running, which the
record does not say. That stays the Orchestrator's validation, as it effectively always was.
Test ids used as section headings (the families in test_page_citations.TEST_FAMILIES, e.g.
GBP-VIDEO-004 over several runs) are headings of experiments, not evidence ids, and are excluded
from uniqueness by that one declaration.
"""
import os
import re
import unittest

from test_page_citations import TEST_FAMILIES

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
CITERS = (os.path.join(ROOT, "docs", "HANDOFF.md"), os.path.join(ROOT, "docs", "ROADMAP.md"))
HOST = os.path.dirname(os.path.abspath(__file__))
HEADING = re.compile(r"^#{2,4} +((?:GBP|ENV)-([A-Z]+)-(\d{3})|U-(?:GBP|ENV)-(\d{3}))\b", re.M)
ID = re.compile(r"\b((?:GBP|ENV)-([A-Z]+)-\d{3}|U-(?:GBP|ENV)-\d{3})\b")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def headings(text):
    """(id, family) for every evidence-id heading; test-id headings are left out."""
    out = []
    for m in HEADING.finditer(text):
        if m.group(2) in TEST_FAMILIES:
            continue
        out.append((m.group(1), m.group(1).rsplit("-", 1)[0]))
    return out


def duplicates(text):
    seen, dup = set(), set()
    for i, _fam in headings(text):
        if i in seen:
            dup.add(i)
        seen.add(i)
    return sorted(dup)


def gaps(text):
    fams = {}
    for i, fam in headings(text):
        fams.setdefault(fam, set()).add(int(i.rsplit("-", 1)[1]))
    return {fam: [n for n in range(1, max(ns) + 1) if n not in ns] for fam, ns in fams.items()
            if any(n not in ns for n in range(1, max(ns) + 1))}


class TheRecordAsItIs(unittest.TestCase):
    def test_every_evidence_id_is_defined_once(self):
        for p in (EVIDENCE, UNKNOWNS):
            self.assertEqual(duplicates(read(p)), [], "%s defines these ids more than once" % p)

    def test_every_family_is_numbered_without_a_gap(self):
        for p in (EVIDENCE, UNKNOWNS):
            self.assertEqual(gaps(read(p)), {}, "%s: numbers missing inside a family" % p)

    def test_the_handoff_and_the_roadmap_cite_only_defined_ids(self):
        defined = {i for p in (EVIDENCE, UNKNOWNS) for i, _f in headings(read(p))}
        for p in CITERS:
            cited = {m.group(1) for m in ID.finditer(read(p)) if m.group(2) not in TEST_FAMILIES}
            self.assertEqual(sorted(cited - defined), [], "%s cites evidence nobody has written" % p)

    def test_the_test_ids_they_cite_name_real_experiments(self):
        hw = read(os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md"))
        for p in CITERS:
            tests = {m.group(1) for m in ID.finditer(read(p)) if m.group(2) in TEST_FAMILIES}
            self.assertEqual(sorted(i for i in tests if i not in hw), [], "%s names experiments HARDWARE_TESTS does not" % p)

    def test_it_sees_the_whole_record(self):
        """A heading pattern that silently stopped matching would pass everything."""
        ev = headings(read(EVIDENCE))
        self.assertGreater(len(ev), 350)
        self.assertIn(("GBP-HW-001", "GBP-HW"), ev)
        self.assertIn(("ENV-HW-001", "ENV-HW"), ev)      # a different family from GBP-HW, not a duplicate
        self.assertGreater(len(headings(read(UNKNOWNS))), 40)


class ThePinsCouldNotSeeIt(unittest.TestCase):
    """The case for the expiring pins, tested rather than assumed (Issue #98)."""

    def setUp(self):
        self.ev = read(EVIDENCE)
        top = max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", self.ev, re.M))
        self.reused = self.ev + "\n### GBP-HW-%03d — an id written a second time (mutation)\n" % (top // 2)
        self.top = top

    def test_a_reused_id_passes_both_kinds_of_pin(self):
        highest = max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", self.reused, re.M))
        self.assertEqual(highest, self.top, "the highest-id pin still reads the same number")
        self.assertNotIn("GBP-HW-%03d" % (self.top + 1), self.reused, "and the next-id sentinel is still absent")

    def test_the_computed_checks_catch_it(self):
        self.assertEqual(duplicates(self.reused), ["GBP-HW-%03d" % (self.top // 2)])
        skipped = self.ev + "\n### GBP-HW-%03d — a number skipped (mutation)\n" % (self.top + 2)
        self.assertEqual(gaps(skipped), {"GBP-HW": [self.top + 1]})
        cites = "the trail names GBP-HW-%03d" % (self.top + 1)
        defined = {i for i, _f in headings(self.ev)}
        self.assertNotIn("GBP-HW-%03d" % (self.top + 1), defined)
        self.assertTrue({m.group(1) for m in ID.finditer(cites)} - defined)


class NoPinOnTheRecordsCurrentHighestId(unittest.TestCase):
    """The shape that expired at every ingestion does not come back through a new test."""

    def test_every_highest_id_computation_reads_the_closed_record(self):
        offenders = []
        pat = re.compile(r'max\(int\(n\) for n in re\.findall\(\s*r"\^#\{2,4\} \+[A-Z-]+\(\\d\{3\}\)\\b",\s*(.+?),\s*re\.M\)\)', re.S)
        for f in sorted(os.listdir(HOST)):
            if not (f.startswith("test_") and f.endswith(".py")) or f == os.path.basename(__file__):
                continue
            for m in pat.finditer(read(os.path.join(HOST, f))):
                if not m.group(1).startswith("guards.at_close("):
                    offenders.append("%s: max over %s" % (f, m.group(1)[:60]))
        self.assertEqual(offenders, [], "a pin on the record's CURRENT highest id expires at every minting; "
                                        "read it with guards.at_close(), or check a property of the record "
                                        "instead:\n" + "\n".join(offenders))

    def test_the_converted_pins_are_all_still_there(self):
        n = sum(read(os.path.join(HOST, f)).count("guards.at_close(") for f in os.listdir(HOST)
                if f.startswith("test_") and f.endswith(".py"))
        self.assertGreaterEqual(n, 25, "20 highest-id pins, 3 next-id / run pins and 2 citation windows read the "
                                       "closed record; if this collapses they were deleted, not closed")


if __name__ == "__main__":
    unittest.main()
