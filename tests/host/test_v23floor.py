"""
tests/host/test_v23floor.py — §V23.10: `QUESTION P`'s `neither` set against what the step floor did
not keep (tools/v23floor.py, GitHub Issue #101), on synthetic reports only.

Pinned: the sub-floor count is exact when the step buffer dropped nothing and an interval when it
dropped some; the sub-floor time is always an interval, built from the log2 histogram's edges and the
floor, and the bin the floor falls in contributes only its part not kept; `neither` is the frozen
gate's; the comparison is printed with no threshold; and a report whose histogram does not add up, or
whose kept steps break the floor rule, is refused.
"""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import v23floor  # noqa: E402

TB = 40500000
P = 9888


def tone(lost=()):
    """Decoded samples of sweep-0002's first tone and their ticks, with the (half, index) pairs lost."""
    d, t = [], []
    for h in range(40):
        for k in range(16):
            if (h, k) in lost:
                continue
            d.append(0 if k == 15 else (20000 if h % 2 == 0 else -20000))
            t.append(1000000 + (h * 16 + k) * P)
    return d, t


def report(hist_produce, hist_process, steps, dropped=0, lost=((10, 7), (30, 4))):
    d, t = tone(lost)
    return {"tb_hz": TB, "audio": {"decoded": d, "ticks": t}, "steps": steps, "callbacks": [],
            "window": {"t_origin": 1000000, "t_end": 1000000 + 2 * TB, "coverage": [4096, 4096]},
            "trace": {"floor": 200, "calls": {"produce": sum(hist_produce), "flush_queue": 0,
                                              "process": sum(hist_process)},
                      "hist": {"produce": hist_produce, "process": hist_process},
                      "dropped": {"step_dropped": dropped}}}


def hist(**bins):
    h = [0] * 32
    for k, v in bins.items():
        h[int(k[1:])] = v
    return h


# produce: 1000 calls in [32, 63], 300 in [128, 255] of which 100 kept (200..255), 50 kept at 4000
KEPT = ([[50000000 + 10000 * i, 50000000 + 10000 * i + 200 + i % 56, "produce", 50000000 + 10000 * i + 300]
         for i in range(100)] +
        [[60000000 + 10000 * i, 60000000 + 10000 * i + 4000, "produce", 60000000 + 10000 * i + 4040]
         for i in range(50)])
PRODUCE = hist(b5=1000, b7=300, b11=50)
PROCESS = hist(b3=500)            # 500 calls in [8, 15], none kept


class TheCountAndTheTime(unittest.TestCase):

    def test_exact_count_and_time_interval_with_nothing_dropped(self):
        out = v23floor.compare(report(PRODUCE, PROCESS, KEPT))
        pr = out["sub_floor"]["produce"]
        self.assertEqual((pr["calls"], pr["kept"], pr["count_min"], pr["count_max"]), (1350, 150, 1200, 1200))
        self.assertEqual((pr["time_ticks_min"], pr["time_ticks_max"]), (1000 * 32 + 200 * 128, 1000 * 63 + 200 * 199))
        ps = out["sub_floor"]["process"]
        self.assertEqual((ps["count_min"], ps["count_max"]), (500, 500))
        self.assertEqual((ps["time_ticks_min"], ps["time_ticks_max"]), (500 * 8, 500 * 15))
        tot = out["sub_floor_total"]
        self.assertEqual((tot["count_min"], tot["count_max"]), (1700, 1700))
        self.assertEqual((tot["time_ticks_min"], tot["time_ticks_max"]), (61600, 110300))
        self.assertLessEqual(tot["time_ticks_max"], 2 * tot["time_ticks_min"] + 200 * 1700)
        self.assertAlmostEqual(tot["per_second_max"], 850.0)

    def test_a_dropped_step_turns_the_count_into_an_interval(self):
        out = v23floor.compare(report(PRODUCE, PROCESS, KEPT, dropped=50))
        tot = out["sub_floor_total"]
        self.assertEqual((tot["count_min"], tot["count_max"]), (1650, 1700))
        self.assertEqual(tot["time_ticks_min"], 1000 * 32 + 500 * 8 + 150 * 128)

    def test_neither_is_the_frozen_gates_and_no_threshold_is_set(self):
        out = v23floor.compare(report(PRODUCE, PROCESS, KEPT))
        self.assertEqual((out["P"]["losses"], out["P"]["neither"]), (2, 2))
        self.assertIn("no threshold", out["reading"])
        self.assertIn("2 of 2 loss gaps went to `neither`", out["reading"])

    def test_the_bins_are_the_recorders(self):
        """src/audio/gbp_atrace.c: while (v > 1 && b < 31) { v >>= 1; b++; }"""
        for v, b in ((0, 0), (1, 0), (2, 1), (3, 1), (127, 6), (128, 7), (199, 7), (200, 7), (255, 7), (256, 8)):
            self.assertEqual(v23floor._bin(v), b, v)
        self.assertEqual(v23floor._edges(7), (128, 255))
        self.assertEqual(v23floor._edges(0), (0, 1))


class ItRefusesRatherThanGuesses(unittest.TestCase):

    def test_a_histogram_that_does_not_add_up(self):
        r = report(PRODUCE, PROCESS, KEPT)
        r["trace"]["calls"]["produce"] += 1
        with self.assertRaisesRegex(ValueError, "histogram holds"):
            v23floor.compare(r)

    def test_a_kept_step_under_the_floor(self):
        steps = KEPT + [[70000000, 70000150, "produce", 70000160]]
        with self.assertRaisesRegex(ValueError, "under the floor"):
            v23floor.compare(report(hist(b5=1000, b7=301, b11=50), PROCESS, steps))

    def test_more_kept_steps_than_calls_in_a_bin(self):
        with self.assertRaisesRegex(ValueError, "fewer calls than kept"):
            v23floor.compare(report(hist(b5=1000, b7=50, b11=50), PROCESS, KEPT))


if __name__ == "__main__":
    unittest.main()
