"""tests/host/test_v28_run56_ingest.py -- GitHub Issue #139 / #140 (RUN 56): the ingested readings, re-derived from the archived log by the tools.

The numbers HARDWARE_TESTS.md V28.25 and GBP-HW-371 / GBP-HW-372 quote are recomputed here from captures/local (ignored by Git, so the test skips, with the
registered reason, on a host without the archive).
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

RUN56 = os.path.join(ROOT, "captures", "local", "GBP-AUDIO-V28_v28-validation-0001-run56.log")
SHA = "c74f701b3f862e7fe2d9e19d9e656a8813e4902e41d056a46bd85caf9cf20e1f"


class TheArchivedLogReadsAsRecorded(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(RUN56):
            raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
        with open(RUN56, "rb") as f:
            raw = f.read()
        assert hashlib.sha256(raw).hexdigest() == SHA, "captures/local's RUN 56 archive is not the recorded one (a defect in the archive, never a skip)"
        cls.text = raw.decode("utf-8", "replace")
        cls.a = v28verdict.analyse(cls.text)
        cls.out = v28verdict.render(cls.a)

    def test_the_verdict_and_the_hooks(self):
        self.assertIn("ADMISSIBILITY: PASS", self.out)
        self.assertIn("'clean' is OBSERVED", self.out)
        self.assertIn("SWEEP: 28 records (18 GATE, 10 INFO); verdict=PASS", self.out)
        self.assertIn("mean ring at chunk start 3827 (-269 vs target) over 1914 chunks", self.out)

    def test_the_dma_arm(self):
        d = v28latency.dma_semantics(self.text)
        self.assertEqual((d["n"], d["prev1"], d["prev2"], d["none"], d["same12"]), (7425, 7238, 0, 0, 187))
        self.assertEqual((d["left_min"], d["left_mean"], d["left_max"]), (3968, 3968, 3968))
        self.assertEqual(d["post"], [7238, 0, 187, 0])
        self.assertEqual(d["latch"], "write-through")
        self.assertEqual((d["reading"], d["offset_ms"], d["offset_max_ms"]), ("R1", 0.0, v28latency.PERIOD_MS))

    def test_p4_dwells_as_scored(self):
        rows = [int(l.split("dup=")[1].split()[0]) for l in self.text.splitlines() if " V28_3A n=" in l][:9]
        self.assertEqual(rows, [3102, 3074, 3072, 2240, 1744, 1648, 1712, 1824, 0])
        steady = rows[3:8]
        self.assertEqual([r for r in steady if not 1400 <= r <= 2100], [2240], "the band is missed at exactly one dwell")
        self.assertTrue(all(r < 2800 for r in steady), "and not refuted (the line is 2 800)")
        self.assertTrue(all(r >= 2800 for r in rows[1:3]), "the first two dwells are saturated: the recovery prediction held")


if __name__ == "__main__":
    unittest.main()
