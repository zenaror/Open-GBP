"""
tests/host/test_video007_design.py — the GBP-VIDEO-007 / GBP-VIDEO-008 design
(HARDWARE_TESTS §V6): physical scanout and full-frame fidelity as SEPARATE
claims, designed for GitHub Issue #6 and, since Issue #7, IMPLEMENTED IN
SOFTWARE (§V6.18) but NOT physically executed and with no run reserved.

What is pinned here is the CONTRACT of the design: the section exists with its
numbered parts in order, it commits to nothing it has not done, it allocates no
evidence ID and reserves no run, it keeps the five claims apart, it says exactly
which frozen formats stay frozen and which names are new, it records the
equipment dependency instead of inventing it, and — the one thing a document
cannot prove by prose — the coordinate field it proposes really is injective
and really makes shifts, swaps and permutations falsifiable. The field model
below is written from the section's formula and is not an implementation of
the stimulus: nothing here touches a ROM, a runtime or a sidecar.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
HANDOFF = os.path.join(ROOT, "docs", "HANDOFF.md")
_C = {}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def v6():
    if "v6" not in _C:
        t = read(HW)
        i = t.index("\n## V6 — GBP-VIDEO-007 / GBP-VIDEO-008")
        _C["v6"] = t[i:]
    return _C["v6"]


def flat(s):
    return re.sub(r"\s+", " ", s)


def part(n):
    t = v6()
    i = t.index("### V6.%d " % n)
    j = t.find("### V6.%d " % (n + 1), i)
    return t[i:] if j < 0 else t[i:j]


# ---------------------------------------------------------------- the field --
# §V6.6: x = 56..238 carries value = y*183 + (x-56); FLAG, STRIP-L and the guards
# keep OGBPIDX1's bytes; bit 15 is never set. This is the model of the CONTRACT,
# not the stimulus.
W, H = 240, 160
FIELD_X0, FIELD_X1 = 56, 238
FIELD_W = FIELD_X1 - FIELD_X0 + 1        # 183


def field(x, y):
    return y * FIELD_W + (x - FIELD_X0)


def field_pixels():
    return [(x, y) for y in range(H) for x in range(FIELD_X0, FIELD_X1 + 1)]


class SectionsExist(unittest.TestCase):
    def test_the_section_exists_and_its_seventeen_parts_are_in_order(self):
        t = v6()
        pos = [t.index("### V6.%d " % n) for n in range(1, 18)]
        self.assertEqual(pos, sorted(pos))
        # Issue #7: the heading now carries the implementation status; the design
        # provenance (Issue #6) stays in the same heading.
        self.assertIn("DESIGN (Issue #6)", t.splitlines()[1])
        self.assertIn("IMPLEMENTED IN SOFTWARE", t.splitlines()[1])
        # Issues #8 / #9 / #10: pre-registered, executed, ingested -- both INCONCLUSIVE.
        self.assertIn("RUN 12 PRE-REGISTERED (Issue #8, \u00a7V6.19), EXECUTED (Issue #9), INGESTED (Issue #10, \u00a7V6.20)", t.splitlines()[1])
        self.assertIn("GBP-VIDEO-007 INCONCLUSIVE", t.splitlines()[1])
        self.assertIn("GBP-VIDEO-008 INCONCLUSIVE", t.splitlines()[1])
        for part_h in ("### V6.18 ", "### V6.19 ", "### V6.20 "):
            self.assertIn(part_h, t)

    def test_the_thirteen_required_items_are_mapped(self):
        head = v6().split("### V6.1 ")[0]
        for n in range(1, 14):
            self.assertIsNotNone(re.search(r"^\s*%d\s{2}\S" % n, head, re.M), "item %d is not in the map" % n)
        for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13):
            self.assertIn("(item %d" % n if n not in (2, 3) else "(items 2, 3)", v6())


class ItCommitsNothingItHasNotDone(unittest.TestCase):
    def test_it_says_plainly_what_is_implemented_and_what_is_not(self):
        """Issue #6 wrote the design; Issue #7 implemented it in software. The
        head must say both, keep the design text as provenance, and still say
        that nothing touched hardware and nothing is reserved."""
        head = flat(v6().split("### V6.1 ")[0])
        self.assertIn("IMPLEMENTED IN SOFTWARE", head)
        self.assertIn("NOT PHYSICALLY EXECUTED", head)          # the Issue #7 status, as written then
        # Issues #8 / #9 / #10: pre-registered, executed, ingested; the outcome named plainly
        self.assertIn("RUN 12 was PRE-REGISTERED in \u00a7V6.19", head)
        self.assertIn("EXECUTED under Hardware Issue #9", head)
        self.assertIn("INGESTED in \u00a7V6.20", head)
        self.assertIn("GBP-VIDEO-007 INCONCLUSIVE and GBP-VIDEO-008 INCONCLUSIVE", head)
        # Issue #14 / #15 / #16: RUN 13 pre-registered in §V6.24 with coord-0002, executed, ingested in §V6.25
        self.assertIn("RUN 13 — the same experiments with coord-0002 and the same stream-0013 — was PRE-REGISTERED in §V6.24 (Issue #14), EXECUTED under Hardware Issue #15 and INGESTED in §V6.25 (Issue #16)", head)
        self.assertIn("GBP-VIDEO-007 = PASS (CLAIM-D only) and GBP-VIDEO-008 = PASS (CLAIM-A / CLAIM-B, the eight sampled frames only)", head)
        self.assertIn("No frozen format changes", head)
        self.assertIn("DESIGN ONLY", head)
        self.assertIn("kept verbatim as provenance", head)
        self.assertIn("V6.18", head)

    def test_the_design_and_implementation_parts_allocate_nothing_and_reserve_no_run(self):
        """\u00a7V6.1-\u00a7V6.18 are provenance: written before any run, they name no
        evidence id and reserve no run name. The reservation belongs to \u00a7V6.19
        (test_run12_prereg) and the evidence ids to the result \u00a7V6.20 and the head
        (test_run12)."""
        t = v6()
        design = t[t.index("### V6.1 "):t.index("### V6.19 ")]
        self.assertNotRegex(design, r"GBP-HW-2[5-9]\d|GBP-HW-[3-9]\d\d")
        self.assertNotRegex(design, r"GBP-VID-03[4-9]|GBP-VID-0[4-9]\d")
        self.assertNotRegex(design, r"captures/local/\S*run1[2-9]")
        self.assertIn("No name is reserved here", part(14))
        self.assertIn("run<N>", part(14))

    def test_the_new_names_were_verified_unused_and_are_named_by_the_design(self):
        """At design time (Issue #6) none of these existed anywhere in the tree;
        Issue #7 then implemented them, so this test pins that the design named
        them and that no OTHER experiment id was minted since."""
        for name in ("stream-0013", "coord-0001", "OGBPCOORD1", "OGBPFULL1", "OGBPVI1", "GBP-VIDEO-007", "GBP-VIDEO-008"):
            self.assertIn(name, v6())
        self.assertNotRegex(read(HW), r"GBP-VIDEO-009|GBP-VIDEO-01\d")

    def test_pixel_perfect_is_not_measured_or_implemented(self):
        t = flat(v6())
        self.assertIn("GBP-VID-032", t)
        self.assertIn("not implemented, not validated and not approached", t)
        self.assertIn("NOT MEASURED HERE", t)


class TheClaimsStayApart(unittest.TestCase):
    def test_the_five_claims_are_named_and_may_not_promote_each_other(self):
        p = part(2)
        for c in ("CLAIM-A", "CLAIM-B", "CLAIM-C", "CLAIM-D", "CLAIM-E"):
            self.assertIn(c, p)
        self.assertIn("A result for one letter may not automatically promote another", flat(p))
        self.assertIn("CLAIM-C is a register write and a software mirror, never scanout", flat(p))

    def test_two_experiments_and_the_one_run_rule(self):
        p = flat(part(1))
        self.assertIn("two experiments with two IDs, two gate sets and two verdicts", p)
        self.assertIn("one physical run may produce both data sets", p)
        self.assertIn("a run may be PASS for one and INCONCLUSIVE for the other", p)
        self.assertIn("Neither verdict consults the other's evidence", flat(part(13)))

    def test_software_evidence_is_never_promoted_to_scanout(self):
        p = flat(part(4))
        self.assertIn("VIDEO_GetCurrentFramebuffer()", p)
        self.assertIn("currentFb = nextFb", p)
        self.assertIn("still software evidence", p)
        self.assertIn("binds the observation to the set R_k, not to one frame", p.replace("**", ""))

    def test_the_fidelity_claim_stops_at_the_texture_and_says_why(self):
        p = flat(part(5)).replace("**", "")
        self.assertIn("stops at source", p)
        self.assertIn("Physical display pixel equality is not claimed", p.replace("**", ""))
        self.assertIn("U-GBP-034", p)
        self.assertIn("U-GBP-029", p)
        self.assertIn("never corrected", p)
        self.assertIn("displacement map", p.replace("**", ""))


class TheStimulusDecision(unittest.TestCase):
    def test_indexed_0003_is_rejected_for_stated_reasons_not_reused_for_convenience(self):
        p = flat(part(6))
        self.assertIn("is not sufficient for CLAIM-B", p)
        self.assertIn("repeats every 64 px", p)
        self.assertIn("31 phases for 40 blocks", p)
        self.assertIn("in-block row swap changes nothing", p)

    def test_the_witness_bytes_stay_identical_and_istim_is_not_edited(self):
        p = flat(part(6))
        self.assertIn("byte-identical to OGBPIDX1", p.replace("**", ""))
        self.assertIn("tools/istim.py is not edited", p.replace("`", "").replace("**", ""))
        self.assertIn("No runtime recognition of the expected answer is required", p)

    def test_the_glyph_schedule_is_stated(self):
        p = part(6)
        self.assertIn("k*480", p)
        self.assertIn("k*480+40", p)
        self.assertIn("48x80", p)


class TheCoordinateFieldReallyFalsifies(unittest.TestCase):
    """The formula of §V6.6, checked as mathematics. The stimulus is not
    implemented; the CONTRACT must already be sound."""

    def test_injective_and_bit_15_clear(self):
        vals = [field(x, y) for x, y in field_pixels()]
        self.assertEqual(len(vals), 183 * 160)
        self.assertEqual(len(set(vals)), len(vals))
        self.assertEqual((min(vals), max(vals)), (0, 29279))
        self.assertTrue(all(v < 0x8000 for v in vals))

    def test_every_row_and_column_shift_changes_a_pixel(self):
        for k in range(1, H):
            self.assertTrue(any(field(x, y) != field(x, (y + k) % H) for x, y in field_pixels()[:FIELD_W]), k)
        for k in range(1, FIELD_W):
            self.assertTrue(any(field(x, y) != field(FIELD_X0 + ((x - FIELD_X0 + k) % FIELD_W), y)
                                for x, y in field_pixels()[:FIELD_W]), k)

    def test_an_axis_swap_and_any_tile_permutation_change_a_pixel(self):
        # axis swap on the square part of the field
        self.assertTrue(any(field(FIELD_X0 + i, j) != field(FIELD_X0 + j, i) for i in range(160) for j in range(160) if i != j))
        # 4x4 tiles: no two tiles carry the same 16 values, so no permutation is invisible
        tiles = {}
        for ty in range(H // 4):
            for tx in range(FIELD_W // 4):
                key = tuple(field(FIELD_X0 + 4 * tx + i, 4 * ty + j) for j in range(4) for i in range(4))
                self.assertNotIn(key, tiles, "two tiles are identical")
                tiles[key] = (tx, ty)

    def test_a_block_placed_at_another_position_fails_every_field_pixel(self):
        for b in range(40):
            for b2 in range(40):
                if b == b2:
                    continue
                self.assertTrue(all(field(x, 4 * b + r) != field(x, 4 * b2 + r)
                                    for r in range(4) for x in range(FIELD_X0, FIELD_X1 + 1)))

    def test_the_document_states_the_same_formula(self):
        p = part(6)
        self.assertIn("value = y*183 + (x-56)", p)
        self.assertIn("0..29279, injective, bit 15 clear", p)


class FormatsAndEquipment(unittest.TestCase):
    def test_frozen_formats_stay_frozen_and_new_names_are_new(self):
        p = flat(part(8))
        self.assertIn("extending a frozen contract in place is forbidden", p)
        for name in ("OGBPFULL1 v1", "OGBPVI1 v1"):
            self.assertIn(name, p)
        self.assertIn("OGBPIDX1, OGBPIDXCAP1 v1, OGBPDISP2 v2 unchanged", flat(part(7)))
        self.assertIn("content-blind", p)
        self.assertIn("No callback, no wait", p)

    def test_the_architecture_constraints_are_named(self):
        p = flat(part(9))
        for phrase in ("never between the ACK and the RE-ARM", "Policy A is untouched", "Two XFBs stay two",
                       "No `VIDEO_WaitVSync`", "no VI callback", "no frame-sized work in one slice"):
            self.assertIn(phrase, p, phrase)

    def test_the_equipment_dependency_is_documented_not_invented(self):
        p = flat(part(10))
        self.assertIn("NOT DECLARED IN THE REPOSITORY", p)
        self.assertIn("declared by precedent", p)
        self.assertIn("capture device", p)
        self.assertIn("frame-accurate timestamps", p)
        self.assertIn("at least one frame of R_k was scanned out", p)
        self.assertIn("no classification changes because a photograph", p)
        self.assertIn("DISPLAY / CABLE NOT DECLARED", part(17))

    def test_verdicts_are_per_experiment_and_admissibility_reuses_the_frozen_gates(self):
        p = part(13)
        self.assertEqual(p.count("PASS  "), 2)
        self.assertEqual(p.count("FAIL  "), 2)
        self.assertEqual(p.count("INCONCLUSIVE  "), 2)
        a = flat(part(12))
        self.assertIn("tools/vindex.py", a.replace("`", ""))
        self.assertIn("OBSERVED_CONTIGUOUS", a)
        self.assertIn("STATUS.FAULT = 0", a.replace("`", ""))


class TheHandoffPointsHere(unittest.TestCase):
    def test_the_handoff_names_the_design_and_says_it_is_implemented_but_not_run(self):
        t = read(HANDOFF)
        self.assertIn("§V6", t)
        self.assertIn("§V6.18", t)
        self.assertIn("GBP-VIDEO-007", t)
        self.assertIn("GBP-VIDEO-008", t)
        self.assertRegex(t, r"IMPLEMENTED IN SOFTWARE[^\n]*NOT PHYSICALLY EXECUTED",
                         "the handoff must say the design is implemented in software and not physically executed")
        self.assertIn("stream-0013", t)
        self.assertIn("coord-0001", t)


if __name__ == "__main__":
    unittest.main()
