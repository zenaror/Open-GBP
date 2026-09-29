"""tests/host/test_v28latency.py -- GitHub Issue #139 (U-GBP-049): tools/v28latency.py, the definition of the native path's latency, its arithmetic, its
table, the account of what became of #122's 122.9 ms, and its agreement with the host test that proves the definition on the real chain."""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v28latency as V  # noqa: E402

RUN55 = os.path.join(ROOT, "captures", "local", "GBP-AUDIO-V28_v28-validation-0001-run55.log")
STOCK_C = os.path.join(ROOT, "tests", "unit", "test_v28_stock.c")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class TheClocksAreMeasured(unittest.TestCase):
    def test_the_playout_rate_is_the_ais_measured_clock_not_the_nominal(self):
        self.assertAlmostEqual(V.PERIOD_MS, 1000.0 / 32028.483 * 1000.0, places=9)
        self.assertAlmostEqual(V.RATE, 2048 / (1000 / 32028.483), places=6)
        self.assertNotAlmostEqual(V.RATE, 2048 / (1000 / 32000.0), places=0)
        self.assertLess(abs(V.PERIOD_MS - 31.25), 0.03)
        self.assertGreater(abs(V.PERIOD_MS - 31.25), 0.02)

    def test_the_host_test_uses_the_same_clocks_and_cadence(self):
        c = read(STOCK_C)
        self.assertIn("#define AI_HZ           32028.483", c)
        self.assertIn("#define CALLS_PER_PERIOD 122.8", c)
        self.assertIn("#define FEED_HZ         65536.0", c)


class TheArithmetic(unittest.TestCase):
    def test_the_stock_at_a_chunk_start(self):
        self.assertEqual(V.stock_at_chunk_start(3828, 1, 0.0), 3828 + 2048 * 2)
        self.assertAlmostEqual(V.stock_at_chunk_start(3828, 1, 0.5), 3828 + 4096 - 1024)
        self.assertEqual(V.stock_at_chunk_start(3828, 4, 0.0), 3828 + 2048 * 5)

    def test_run_55s_hold(self):
        stock = (3828 + 4096 - 2048 * V.PHI_START) / V.RATE * 1000 + V.RESAMPLER_MS
        self.assertAlmostEqual(V.latency_ms(3828, 1), stock + V.dup_delay_ms(3828), places=9)
        self.assertAlmostEqual(V.latency_ms(3828, 1), 121.01, places=2)
        self.assertAlmostEqual(stock, 120.80, places=1)                   # the stock alone, before the DUP delay the review found

    def test_the_dup_delay_is_the_rings_mean_times_the_deficit_over_the_playout_rate(self):
        self.assertAlmostEqual(V.dup_delay_ms(3828), (3828 - 758.5) * 0.00442 / V.RATE * 1000, places=9)
        self.assertAlmostEqual(V.dup_delay_ms(10996), 0.69, places=2)
        self.assertEqual(V.dup_delay_ms(100), 0.0)
        self.assertGreater(V.dup_delay_ms(10996), 3 * V.dup_delay_ms(3828))     # it grows with TARGET
        self.assertLess(V.dup_delay_ms(3828, delta=0.0027), V.dup_delay_ms(3828))   # and with the deficit

    def test_the_host_tagging_test_and_the_tool_agree_on_the_formula(self):
        c = read(os.path.join(ROOT, "tests", "unit", "test_v28_latency_tag.c"))
        self.assertIn("(c - (2048 - feed x tau) / 2) x delta / playout", c)
        self.assertIn("#define AI_HZ       32028.483", c)
        self.assertIn("#define CALLS       122.8", c)

    def test_each_ahead_adds_exactly_one_chunk_period(self):
        for c in (2049, 3828, 10996):
            for a in (1, 2, 3):
                self.assertAlmostEqual(V.latency_ms(c, a + 1) - V.latency_ms(c, a), V.PERIOD_MS, places=9)

    def test_the_ladder(self):
        rows = V.ladder()
        self.assertEqual(len(rows), 24)
        for t, a, c, l in rows:
            self.assertEqual(c, t - 268)                              # every rung is above the production gate
            self.assertAlmostEqual(l, V.latency_ms(t - 268, a), places=9)
        by = {(t, a): l for t, a, c, l in rows}
        self.assertAlmostEqual(by[(4096, 1)], 121.01, places=2)
        self.assertAlmostEqual(by[(3072, 1)], 105.33, places=2)
        self.assertAlmostEqual(by[(11264, 4)], 324.44, places=2)
        self.assertAlmostEqual(by[(7168, 2)], 199.28, places=2)
        self.assertGreater(by[(9216, 1)], by[(7168, 1)])

    def test_the_gate_floors_c(self):
        self.assertEqual(V.c_of_target(2048), 2049)
        self.assertEqual(V.c_of_target(2317), 2049)
        self.assertEqual(V.c_of_target(2318), 2050)
        for a in (1, 2, 3, 4):
            self.assertAlmostEqual(V.floor_ms(a), V.latency_ms(2049, a), places=9)
            self.assertLess(V.floor_ms(a), V.latency_ms(V.c_of_target(3072), a))
        self.assertAlmostEqual(V.gate_level_ms(1), 93.8, places=1)
        self.assertIs(V.floor_ms, V.gate_level_ms)


class TheOldFigure(unittest.TestCase):
    def test_122_9_is_reproduced_and_the_change_is_accounted_for_term_by_term(self):
        self.assertAlmostEqual(V.old_formula_ms(4096, 1), 122.9, places=1)
        o, n = V.old_terms_ms(4096, 1), V.new_terms_ms(4096, 1)
        # old: ring, chunks, resampler.  new: ring, chunks, phase, resampler
        self.assertAlmostEqual(sum(o), V.old_formula_ms(4096, 1), places=9)
        self.assertAlmostEqual(sum(n), V.latency_ms(V.c_of_target(4096), 1), places=9)
        delta = (n[0] - o[0]) + (n[1] - o[1]) + n[2] + (n[3] - o[2]) + n[4]
        self.assertAlmostEqual(V.latency_ms(V.c_of_target(4096), 1) - V.old_formula_ms(4096, 1), delta, places=9)
        self.assertLess(n[3] - o[2], -1.7)                 # the resampler dominates (1.95 ms -> 0.12 ms)
        self.assertLess(abs(n[0] - o[0]), 0.2)             # c sits at TARGET - BAND - 12 in both
        self.assertLess(abs(n[1] - o[1]), 0.1)             # the AI's measured clock against the nominal
        self.assertLess(abs(n[2]), 0.3)                    # the phase
        self.assertGreater(n[4], 0.15)                     # the DUP delay: a term #122's formula did not have


class TheRealLog(unittest.TestCase):
    def test_run_55(self):
        if not os.path.isfile(RUN55):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        m = V.from_log(read(RUN55))
        self.assertEqual((m["target"], m["mean_cs"], m["mean_ring"], m["min_ring_late"], m["chunk_starts"]), (4096, 3828, 3097, 2272, 1914))
        self.assertAlmostEqual(m["calls_per_period"], 122.8, delta=0.3)
        self.assertAlmostEqual(m["blocks_s"], 4081.5, delta=1.0)
        self.assertAlmostEqual(m["L_mean_ms"], 121.01, delta=0.03)
        self.assertTrue(m["in_domain"])
        self.assertAlmostEqual(m["loss"], 0.00355, delta=0.0002)
        self.assertAlmostEqual(m["c_min"], 3789, delta=3)
        self.assertAlmostEqual(m["L_low_ms"], 120.41, delta=0.05)
        self.assertLess(abs(m["mean_ring"] - m["ring_mean_model"]), 40)          # the model's own check
        self.assertIn("EXCLUDED", V.render(m))

    def test_a_log_without_the_records_gives_none(self):
        self.assertIsNone(V.from_log("000001 IDENT x"))

    def test_the_table_says_what_it_excludes_and_what_it_is_not(self):
        text = V.render(None)
        for needed in ("EXCLUDED: everything before the tap", "everything after the AI", "NOT the audio-versus-video OFFSET", "measured",
                       "32028.483", "ASSUMED, NOT MEASURED", "VALID ONLY WHILE THE LOSS IS BELOW", "not a level the chain holds without underruns"):
            self.assertIn(needed, text)


if __name__ == "__main__":
    unittest.main()
