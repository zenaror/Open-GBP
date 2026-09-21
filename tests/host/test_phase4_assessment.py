"""
tests/host/test_phase4_assessment.py — the Phase-4 acceptance assessment and
the consolidation that came with it (GitHub Issue #17, 2026-09-21).

Pinned: the verdict is stated once, in the same words, in the ROADMAP, in the
HANDOFF and in the assessment; every evidence or unknown id cited by the
promoted video page, the refreshed hardware/protocol rows and the assessment
exists in EVIDENCE.md / UNKNOWNS.md; no id was minted (the highest GBP-HW and
GBP-VID ids are the ones the last ingestion left); every row of the promoted
video page carries an id and a status of F or C; the assessment covers the
four terms of the criterion and names an owner for every residual; the
ROADMAP keeps the criterion verbatim and still points at Phase 9 for
presentation; no unknown was closed by this checkpoint.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ROADMAP = os.path.join(ROOT, "docs", "ROADMAP.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
ASSESS = os.path.join(ROOT, "docs", "research", "PHASE4_ASSESSMENT.md")
VIDEO = os.path.join(ROOT, "docs", "protocol", "VIDEO.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNKNOWNS = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
PROMOTED = [VIDEO,
            os.path.join(ROOT, "docs", "hardware", "ARCHITECTURE.md"),
            os.path.join(ROOT, "docs", "hardware", "GBS-DOL.md"),
            os.path.join(ROOT, "docs", "protocol", "REGISTERS.md")]
VERDICT = "PHASE 4 VERDICT: SATISFIED WITH NAMED RESIDUALS"
# evidence / unknown ids only: experiment names (GBP-VIDEO-007, GBP-BBA-001, GBP-INIT-003A, ...) are not ids
ID = re.compile(r"\b(GBP-(?!VIDEO|BBA|INIT|AV|PROBE|BASELINE|INPUT)[A-Z]+-\d{3}|ENV-[A-Z]+-\d{3}|U-GBP-\d{3}|U-ENV-\d{3})\b")   # GBP-INPUT-001 is an experiment name (Issue #26)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r"\s+", " ", s)


def defined_ids():
    ids = set()
    for p in (EVIDENCE, UNKNOWNS):
        for m in re.finditer(r"^#{2,4} +((?:GBP|ENV)-[A-Z]+-\d{3}|U-(?:GBP|ENV)-\d{3})\b", read(p), re.M):
            ids.add(m.group(1))
    return ids


def expand_ranges(text):
    """Turn 'GBP-HW-205…211' / 'GBP-HW-205, 206, 207' style citations into ids."""
    out = set(ID.findall(text))
    for m in re.finditer(r"\b(GBP-[A-Z]+)-(\d{3})\s*(?:…|\.\.\.|-|–|—|to)\s*(\d{3})\b", text):
        pfx, a, b = m.group(1), int(m.group(2)), int(m.group(3))
        if b > a and b - a < 60:
            out.update("%s-%03d" % (pfx, n) for n in range(a, b + 1))
    for m in re.finditer(r"\b(GBP-[A-Z]+)-(\d{3})((?:,\s*\d{3})+)\b", text):
        pfx = m.group(1)
        out.update("%s-%s" % (pfx, n) for n in re.findall(r"\d{3}", m.group(3)))
    return out


class TheVerdictIsStatedOnceAndConsistently(unittest.TestCase):
    def test_roadmap_handoff_and_assessment_carry_the_same_verdict_once(self):
        for p in (ROADMAP, HANDOFF, ASSESS):
            self.assertEqual(read(p).count(VERDICT), 1, p)
        for other in ("PHASE 4 VERDICT: SATISFIED\n", "PHASE 4 VERDICT: NOT SATISFIED"):
            for p in (ROADMAP, HANDOFF, ASSESS):
                self.assertNotIn(other, read(p), (p, other))

    def test_the_roadmap_keeps_the_criterion_verbatim_and_the_phase_9_ownership(self):
        t = read(ROADMAP)
        self.assertIn("A real cartridge running on the physical GBP produces stable,\ncorrect video through the open-source runtime.", t)
        self.assertEqual(t.count("### Phase 4 assessment"), 1)
        self.assertLess(t.index("## Phase 4 — Video"), t.index("### Phase 4 assessment"))
        self.assertLess(t.index("### Phase 4 assessment"), t.index("## Phase 5 — Input"))
        f = flat(t)
        self.assertIn("Presentation requirement — pixel-perfect scaling (recorded 2026-09-20, GBP-VID-032)", f)
        self.assertIn("pixel-perfect requirement GBP-VID-032 | **Phase 9** — the requirement is written there", f)
        self.assertIn("docs/research/PHASE4_ASSESSMENT.md", f)

    def test_the_handoff_repeats_the_verdict_and_names_what_it_does_not_authorise(self):
        f = flat(read(HANDOFF))
        self.assertIn("Phase 4 ASSESSED", f)
        self.assertIn("does not authorise Phase 9", f)
        self.assertIn("docs/research/PHASE4_ASSESSMENT.md", f)


class TheAssessmentCoversTheCriterion(unittest.TestCase):
    def test_four_terms_and_the_asymmetry(self):
        t = read(ASSESS)
        for h in ('### 2.1 "A real cartridge"', '### 2.2 "stable"', '### 2.3 "correct video"', '### 2.4 "through the open-source runtime"',
                  "## 3. The asymmetry, stated", "## 4. Verdict", "## 5. Named residuals and their owners", "## 6. What this assessment does not do"):
            self.assertEqual(t.count(h), 1, h)
        for term in ("indexed-0003", "coord-0001", "coord-0002", "stream-0003", "GBP-VIDEO-005"):
            self.assertIn(term, t)
        self.assertIn("CORROBORATED (by the identical machine-side metrics on retail", flat(t))
        self.assertIn("and it is not FACT", flat(t))

    def test_every_residual_names_an_owner(self):
        t = read(ASSESS)
        rows = [l for l in t.splitlines() if re.match(r"^\| R\d+ \|", l)]
        self.assertGreaterEqual(len(rows), 10)
        for l in rows:
            cells = [c.strip() for c in l.strip().strip("|").split("|")]
            self.assertEqual(len(cells), 4, l)
            self.assertRegex(cells[3], r"\*\*Phase \d+\*\*|\*\*not scheduled\*\*|\*\*Phase 4 research residuals\*\*", l)

    def test_nothing_re_judged_and_no_unknown_closed(self):
        f = flat(read(ASSESS))
        self.assertIn("RUN 12 remains GBP-VIDEO-007 INCONCLUSIVE / GBP-VIDEO-008 INCONCLUSIVE", f)
        self.assertIn("It closes no unknown", f)
        unk = read(UNKNOWNS)
        for u in ("U-GBP-008", "U-GBP-014", "U-GBP-029", "U-GBP-030", "U-GBP-031", "U-GBP-033", "U-GBP-034"):
            m = re.search(r"^#{2,3} %s\b.*$" % u, unk, re.M)
            self.assertIsNotNone(m, u)
            self.assertNotIn("CLOSED", m.group(0), u)


class PromotionIsTraceableAndMintsNothing(unittest.TestCase):
    def test_every_cited_id_exists(self):
        defined = defined_ids()
        for p in PROMOTED + [ASSESS]:
            cited = expand_ranges(read(p))
            missing = sorted(i for i in cited if i not in defined)
            self.assertEqual(missing, [], (p, missing))

    def test_no_new_evidence_or_finding_id(self):
        t = read(EVIDENCE)
        hw = max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", t, re.M))
        vid = max(int(n) for n in re.findall(r"^#{2,4} +GBP-VID-(\d{3})\b", t, re.M))
        # Issue #17 minted no id: it left GBP-HW-260 and GBP-VID-035. Issue #24 (RUN 14 / RUN 15, §V7.2) later minted
        # GBP-HW-261..265, and Issue #26 promoted them into the keypad rows of the hardware / register pages; the
        # assessment itself still cites nothing beyond what Issue #17 saw.
        self.assertEqual((hw, vid), (271, 35))   # Issue #33 (RUN 16 / 17 / 18, §V7.4) minted GBP-HW-266..271
        self.assertNotRegex(read(ASSESS), r"GBP-HW-26[1-9]|GBP-HW-2[7-9]\d|GBP-HW-[3-9]\d\d|GBP-VID-03[6-9]|GBP-VID-0[4-9]\d")
        for p in PROMOTED + [ROADMAP, HANDOFF]:
            self.assertNotRegex(read(p), r"GBP-HW-27[2-9]|GBP-HW-2[8-9]\d|GBP-HW-[3-9]\d\d|GBP-VID-03[6-9]|GBP-VID-0[4-9]\d", p)

    def test_every_row_of_the_video_page_carries_an_id_and_a_fact_or_corroborated_status(self):
        t = read(VIDEO)
        rows = [l for l in t.splitlines() if l.startswith("| ") and not l.startswith("| Property") and not l.startswith("| ---")]
        self.assertGreaterEqual(len(rows), 25)
        for l in rows:
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", l.strip()[1:-1])]      # `\|` inside a cell is not a separator
            self.assertEqual(len(cells), 4, l)
            self.assertTrue(ID.search(cells[3]), "no id: " + l)
            self.assertRegex(cells[2], r"^(F|C)\b", "status must be F or C, never H or U: " + l)
            self.assertNotRegex(cells[2], r"\bH\b|\bU\b|HYPOTHESIS|UNKNOWN")

    def test_the_video_page_states_its_own_boundaries(self):
        f = flat(read(VIDEO))
        for s in ("Nothing whose status is HYPOTHESIS or UNKNOWN is stated here as a property of the device",
                  "do not consume them", "not excluded by the stimulus used", "no nominal rate promoted",
                  "a digit bound to a 40-frame set, never to one frame", "deliberately absent; Phase 9 policy",
                  "## 6. Not established by Phase 4"):
            self.assertIn(s, f, s)
        self.assertNotIn("GBP-VIDEO-008" + " PASS", f)

    def test_the_refreshed_rows_cite_the_hardware_facts_they_now_rest_on(self):
        arch = flat(read(PROMOTED[1]))
        self.assertIn("GBP-HW-081", arch)
        self.assertIn("GBP-HW-131", arch)
        self.assertNotIn("exact hardware word layout H", arch)
        gbs = flat(read(PROMOTED[2]))
        self.assertIn("geometry F (hw)", gbs)
        self.assertIn("GBP-HW-078", gbs)
        regs = flat(read(PROMOTED[3]))
        self.assertIn("GBP-HW-081", regs)
        self.assertIn("GBP-HW-129", regs)
        self.assertIn("VIDEO.md", regs)
        readme = flat(read(os.path.join(ROOT, "docs", "protocol", "README.md")))
        self.assertNotIn("not yet verified on hardware", readme)
        self.assertIn("VIDEO.md", readme)


if __name__ == "__main__":
    unittest.main()
