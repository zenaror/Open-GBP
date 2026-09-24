"""tests/host/test_u045_arms.py -- GitHub Issue #108: RUN 40 by arm, DESCRIPTIVE.

Recomputed from the versioned fixtures (captures/fixtures/hw-gamecube-gbp-2026-09-24-split-0001-run40*) through
the frozen tools/v24report.py, then tools/u045arms.py, which uses only frozen rules: §V24.7's cycle -> arm,
tools/v23accept.py's losses, question_P and video_gaps. Pinned: P split by arm; the `neither` gaps by arm; the
VIDEO gaps by arm, by gap time and for the clear gaps only; that no incomplete frame lies wholly inside one cycle
(every one straddles a callback, the gaps completing just after it), so a per-frame assignment is unavailable by
construction; and that the record labels all of it descriptive, with the readings HYPOTHESES.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import u045arms  # noqa: E402
import v24report  # noqa: E402

FX = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-24-split-0001-run40")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")


def read(p, mode="r"):
    with open(p, mode, **({} if "b" in mode else {"encoding": "utf-8", "errors": "replace"})) as f:
        return f.read()


class ByArm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = u045arms.by_arm(v24report.build(read(FX + ".log"), read(FX + "-trace.bin", "rb")))

    def test_the_cycles_are_S_s(self):
        self.assertEqual((self.r["cycles"]["half"], self.r["cycles"]["full"]), (1015, 1014))
        self.assertEqual(self.r["losses_outside_analysed_cycles"], 4)

    def test_P_by_arm_the_residue_is_still_produce(self):
        h, f = self.r["P_by_arm"]["half"], self.r["P_by_arm"]["full"]
        self.assertEqual(h["counts"], {"recorder": 0, "isr": 0, "produce": 229, "flush_queue": 0, "process": 6,
                                       "neither": 22})
        self.assertEqual(f["counts"], {"recorder": 0, "isr": 0, "produce": 673, "flush_queue": 0, "process": 0,
                                       "neither": 79})
        self.assertEqual((h["losses"], f["losses"]), (257, 752))
        self.assertGreater(h["counts"]["produce"] / float(h["losses"]), 0.85)   # 89 %: still mostly produce

    def test_the_neither_gaps_followed_the_arms_too(self):
        n = self.r["neither_by_arm"]
        self.assertEqual((n["half"], n["full"]), (22, 79))
        self.assertLess(n["binomial_tail_le"], 1e-8)

    def test_the_video_gaps_followed_the_arms(self):
        v = self.r["video"]
        self.assertEqual(v["gaps_inside_ai_span"], 44)
        self.assertEqual((v["by_gap_time"]["half"], v["by_gap_time"]["full"], v["by_gap_time"]["unassigned"]), (6, 38, 0))
        self.assertLess(v["by_gap_time"]["binomial_tail_le"], 1e-6)
        self.assertEqual((v["clear_gaps_only"]["half"], v["clear_gaps_only"]["full"]), (3, 7))
        self.assertGreater(v["clear_gaps_only"]["binomial_tail_le"], 0.05)       # the clear subset alone decides nothing
        self.assertEqual(v["gap_phase_deciles"][0], 42)

    def test_a_per_frame_assignment_is_unavailable_by_construction(self):
        w = self.r["video"]["whole_frames"]
        self.assertEqual((w["half"], w["full"], w["straddling_or_unassigned"]), (0, 0, 44))

    def test_it_is_labelled_descriptive(self):
        self.assertIn("DESCRIPTIVE", self.r["status"])


class TheRecordSaysWhatItIs(unittest.TestCase):
    def entry(self):
        t = read(EV)
        i = t.index("\n### GBP-HW-334 ")
        j = t.find("\n### ", i + 1)
        return re.sub(r"\s+", " ", (t[i:j] if j >= 0 else t[i:]).replace("**", "").replace("`", ""))

    def test_the_evidence_is_narrow(self):
        e = self.entry()
        for tok in ("FACT (post hoc counts from one run, recomputable; no gate was pre-registered)",
                    "HYPOTHESIS", "K's NOT COINCIDENT and correlated rates are compatible",
                    "per-frame assignment is unavailable by construction"):
            self.assertIn(tok, e, tok)

    def test_the_unknown_is_rescoped_on_top(self):
        self.assertIn("RESCOPED 2026-09-24 (GitHub Issue #108, RUN 40 by arm), on top; nothing above is rewritten.",
                      read(UNK))


if __name__ == "__main__":
    unittest.main()
