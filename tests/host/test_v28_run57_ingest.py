"""tests/host/test_v28_run57_ingest.py -- GitHub Issue #139 / #141 (RUN 57): the ingested readings, re-derived from the archived log by the tools.

The numbers HARDWARE_TESTS.md V28.30 and GBP-HW-374 quote are recomputed here from captures/local (ignored by Git, so the test skips, with the registered reason, on a host without
the archive). The marked-block reading (M1, 29 of 29) is the one that lifts the perceptual run's stop condition.
"""
import hashlib
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v28latency  # noqa: E402
import v28verdict  # noqa: E402

RUN57 = os.path.join(ROOT, "captures", "local", "GBP-AUDIO-V28_v28-validation-0001-run57.log")
SHA = "538406c398854f3841178c9c8dc1dbfb199ed9b57adf5ddc8df29fccceedf95b"


class TheArchivedLogReadsAsRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(RUN57):
            raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
        with open(RUN57, "rb") as f:
            raw = f.read()
        assert hashlib.sha256(raw).hexdigest() == SHA, "captures/local's RUN 57 archive is not the recorded one (a defect in the archive, never a skip)"
        cls.text = raw.decode("utf-8", "replace")
        cls.out = v28verdict.render(v28verdict.analyse(cls.text))

    def test_m1_by_the_registered_rule(self):
        d = v28latency.dma_semantics(self.text)
        mk = d["mark"]
        self.assertEqual((mk["reading"], mk["marks"], mk["complete"], mk["arms"]), ("M1", 29, 29, {"1/1": 29}))
        self.assertEqual((d["offset_ms"], d["offset_max_ms"]), (0.0, 0.0), "resolved: the bound is closed")
        self.assertFalse(d.get("conflict"))
        self.assertEqual(d["post"], [6975, 0, 187, 0], "the address register is still a write-through latch: the mark, not the address, resolves it")

    def test_every_mark_reads_3712_then_ordinary_and_the_marked_interval_is_short(self):
        marks = v28latency.read_marks(self.text)
        self.assertEqual(len(marks), 29)
        for m in marks:
            self.assertEqual(m["left"], [3712, 3968, 3968])
            self.assertLess(m["dur"][1], v28latency.MARK_DUR_SPLIT)
            self.assertTrue(all(x > v28latency.MARK_DUR_SPLIT for i, x in enumerate(m["dur"]) if i != 1))

    def test_the_verdict_and_the_hooks(self):
        self.assertIn("ADMISSIBILITY: PASS", self.out)
        self.assertIn("'clean' is OBSERVED", self.out)
        self.assertIn("SWEEP: 28 records (18 GATE, 10 INFO); verdict=PASS", self.out)
        self.assertIn("mean ring at chunk start 3830 (-266 vs target) over 1914 chunks", self.out)
        self.assertIn("DMA MARKED BLOCK (V28MARK, 29 marks, 29 complete; bytes lag / timing lag: 1/1: 29): M1", self.out)

    def test_p4_dwells_as_scored(self):
        rows = [int(l.split("dup=")[1].split()[0]) for l in self.text.splitlines() if " V28_3A n=" in l][:9]
        self.assertEqual(rows, [3104, 3072, 2896, 1762, 1610, 1652, 1712, 1744, 0])
        self.assertTrue(all(r >= 2800 for r in rows[1:3]), "the first two dwells saturated: the recovery criterion held")
        self.assertLess(rows[2], 3060, "the narrower registered range (3 060-3 110) is missed at T5120")
        self.assertTrue(all(1400 <= r <= 2100 for r in rows[3:8]), "the steady band holds at all five dwells")


if __name__ == "__main__":
    unittest.main()
