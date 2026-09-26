"""tests/host/test_v124_records.py -- GitHub Issue #124: the records of Round A and Round C, against the tools and
against what the records said before them.

What is held here:
  * ON TOP, NEVER REWRITTEN: every block of 4e4ff48 (the last records commit before #124) in EVIDENCE, UNKNOWNS,
    RESEARCH_METHOD, HARDWARE_TESTS and the DEVLOG still starts its block now, in order (tests/host/test_v123_records.py's
    walk); GBP-HW-351 and GBP-HW-352 follow the base's last id, once each, in order.
  * THE AMENDMENTS ARE THERE: GBP-HW-347 (|wA - wB|), GBP-HW-349 (k = rate / 4 096, the sixteenth, corr_forgone),
    GBP-HW-350 (the sum before the resampler, stereo's cost recorded in advance), U-GBP-047 (the readings, the refuted
    one with its right predicate, the one-side prediction at the rest width 128) and U-GBP-048 (the three reads, the
    flash cart's menu, the per-candidate predictions, the click read one way).
  * THE FIGURES ARE THE TOOLS': the tap ratios in GBP-HW-351 are v124taps's own output on the versioned tones.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import test_v123_records as base  # noqa: E402
import v124taps  # noqa: E402

BASE = "4e4ff48"
EV, UN, DEVLOG = base.EV, base.UN, base.DEVLOG
NEW_EV = (("GBP-HW-351", "16 or 32 taps"), ("GBP-HW-352", "`agb-route`"))


def entry(text, eid, head_re=base.EV_HEAD):
    e, _ids = base.entries(text, head_re)
    return e[eid]


class OnTopNeverRewritten(unittest.TestCase):
    def test_every_block_of_the_base_starts_its_block_now(self):
        saved = base.BASE
        base.BASE = BASE
        try:
            for path in (EV, UN, base.METHOD, base.HT, DEVLOG):
                self.assertGreater(base.walk_on_top(self, path), 20, path)
        finally:
            base.BASE = saved

    def test_the_new_entries_follow_the_base_once_each(self):
        now_ids = [m.group(1) for m in re.finditer(base.EV_HEAD, base.now(EV), re.M)]
        self.assertEqual(now_ids[now_ids.index("GBP-HW-350") + 1:now_ids.index("GBP-HW-350") + 3],
                         [e for e, _ in NEW_EV])
        for eid, lead in NEW_EV:
            self.assertEqual(now_ids.count(eid), 1, eid)
            self.assertIn(lead, entry(base.now(EV), eid)[0], eid)


class TheAmendments(unittest.TestCase):
    def body(self, eid, path=EV, head_re=base.EV_HEAD):
        return base.flat(entry(base.now(path), eid, head_re)[1])

    def test_evidence(self):
        b = self.body("GBP-HW-347")
        self.assertIn("2026-09-25 (GitHub Issue #124), on top: |wA - wB|, counted.", b)
        self.assertIn("At most 1 in 3 452 of 10 240 slices, and 2 to 10 in the other 6 788.", b)
        b = self.body("GBP-HW-349")
        self.assertIn("k = decode_rate / 4 096", b)
        self.assertIn("falls from 244.141 us to 15.259 us, a sixteenth", b)
        self.assertIn("corr_forgone", b)
        b = self.body("GBP-HW-350")
        self.assertIn("the sum goes BEFORE the resampler (the Orchestrator's decision)", b)
        self.assertIn("Recorded in advance: turning stereo on costs AHEAD 1's safety.", b)

    def test_unknowns(self):
        b = self.body("U-GBP-047", UN, base.UN_HEAD)
        self.assertIn("2026-09-25 (GitHub Issue #124), on top: three readings, one refuted", b)
        self.assertIn("predicts |wA - wB| <= 1 (an odd value's halves differ by one) -- not A == B", b)
        self.assertIn("PINS within noise of 128", b)
        b = self.body("U-GBP-048", UN, base.UN_HEAD)
        self.assertIn("E is not \"the GBP\".", b)
        self.assertIn("the GBP, the BIOS OR the flash cart's menu", b)
        self.assertIn("route-both's E reads resolution bits 14-15 = 0.", b)
        self.assertIn("The click is a one-directional partial readout", b)


class TheFiguresAreTheTools(unittest.TestCase):
    def test_gbp_hw_351s_first_rule_ratios(self):
        b = base.flat(entry(base.now(EV), "GBP-HW-351")[1])
        for name in ("RUN33", "RUN34"):
            r = v124taps.measure(v124taps.tone_runs(name))
            for B in ("5256", "12000"):
                d = r["bands"][B]["diff"]
                self.assertIn("%.3f / %.3f" % (d["N32_b5.65"]["ratio_to_floor"], d["N32_b7.86"]["ratio_to_floor"]),
                              b, (name, B))


if __name__ == "__main__":
    unittest.main()
