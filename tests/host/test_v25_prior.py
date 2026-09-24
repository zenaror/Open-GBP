"""
tests/host/test_v25_prior.py — GitHub Issue #110: the RUN 40 figures §V25.8 records as checked before §V25's
numbers froze, recomputed from the versioned fixtures (captures/fixtures/…-split-0001-run40*).

Everything goes through frozen code: tools/v22report.py (R's `not_drained`), tools/v24report.py (the trace),
tools/v23accept.py's audio_losses (the tone-located losses and their k) and tools/u045arms.py's cycle -> arm
rule. Pinned: that the count R now uses agrees with the tone detector it replaces; the half arm's prior in
blocks per second, 8.39, and 9.23 beside it by the per-cycle count; and RUN 40's AI span, which puts its own
44 incomplete frames at 0.69418/s, just above §V25's literal 0.694.
"""
import bisect
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import u045arms  # noqa: E402
import v22report  # noqa: E402
import v23accept  # noqa: E402
import v24report  # noqa: E402
import v25accept  # noqa: E402

FX = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-24-split-0001-run40")
TB = 40500000.0


def read(p, mode="r"):
    with open(p, mode, **({} if "b" in mode else {"encoding": "utf-8", "errors": "replace"})) as f:
        return f.read()


class RUN40AsSection25SawIt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = read(FX + ".log")
        cls.rep = v24report.build(cls.log, read(FX + "-trace.bin", "rb"))
        a = cls.rep["audio"]
        cls.ticks = a["ticks"]
        cls.losses = v23accept.audio_losses(a["decoded"], a["ticks"])
        cls.ent, cls.arm_of = u045arms.arms_of_cycles(cls.rep)

    def arm(self, arm):
        cyc = [c for c, x in self.arm_of.items() if x == arm]
        dur = sum(self.ent[c + 1] - self.ent[c] for c in cyc) / TB
        ls = [x for x in self.losses if self.arm_of.get(bisect.bisect_right(self.ent, x["t"]) - 1) == arm]
        counted = sum(bisect.bisect_left(self.ticks, self.ent[c + 1]) - bisect.bisect_left(self.ticks, self.ent[c])
                      for c in cyc)
        return {"cycles": len(cyc), "seconds": dur, "gaps": len(ls), "sum_k": sum(x["k"] for x in ls),
                "count_deficit": 4096 * dur - counted}

    def test_the_count_agrees_with_the_tone_detector_it_replaces(self):
        w = v22report.build(self.log)["window"]
        self.assertEqual((w["not_drained"], len(w["coverage"])), (1217, 64))
        self.assertEqual(sum(x["k"] for x in self.losses), 1215)
        span = (self.ticks[-1] - self.ticks[0]) / TB
        self.assertAlmostEqual(4096 * span - (len(self.ticks) - 1), 1216.2, places=1)

    def test_the_half_arms_prior_in_blocks_per_second(self):
        h = self.arm(1)
        self.assertEqual((h["cycles"], h["gaps"], h["sum_k"]), (1015, 257, 266))
        self.assertAlmostEqual(h["seconds"], 31.690, places=3)
        self.assertEqual(round(h["sum_k"] / h["seconds"], 2), float(v25accept.R_PRIOR))          # 8.39
        self.assertAlmostEqual(h["count_deficit"], 292.6, places=1)
        self.assertEqual(round(h["count_deficit"] / h["seconds"], 2), float(v25accept.R_BESIDE))  # 9.23
        self.assertAlmostEqual(h["gaps"] / float(h["cycles"]), 0.2532, places=4)   # §V25.2's figure, in gaps
        self.assertAlmostEqual(h["gaps"] / h["seconds"], 8.11, places=2)           # 8.11 GAPS/s, not blocks

    def test_the_full_arm_and_the_boundary_jitter(self):
        f, h = self.arm(0), self.arm(1)
        self.assertEqual((f["gaps"], f["sum_k"]), (752, 943))
        self.assertAlmostEqual(f["count_deficit"], 943.6, places=1)
        self.assertEqual(round(h["count_deficit"] + f["count_deficit"]), 1236)       # against the window's 1216.2

    def test_RUN_40s_own_video_rate_sits_just_above_the_literal(self):
        t2 = v22report._kv(v22report.records(self.log)["LIVET2"][0])
        span = int(t2["t_ai_stop"], 16) - int(t2["t_ai_start"], 16)
        self.assertEqual(span, 2567047476)
        rate = 44 * TB / span
        self.assertAlmostEqual(rate, 0.69418, places=5)
        self.assertGreater(rate, float(v25accept.V_RATE_MAX))
        self.assertIn("incomplete=57", self.log)                     # 57 = 13 + 44
        self.assertTrue(re.search(r"FRAMECAP frames=\d+ complete=\d+ incomplete=57 ", self.log))


if __name__ == "__main__":
    unittest.main()
