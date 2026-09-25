"""tests/host/test_v123chain.py -- GitHub Issue #123: tools/v123chain.py, what a native-rate decode would cost the
chain: the production cost RUN 40 measured on hardware, the filters, and the budget's arithmetic. DESCRIPTIVE.

On constructions: a prototype's gain is L at DC and its response falls in the stopband; today's filter, rebuilt from
the committed table, has unit gain at DC; the budget's arithmetic is the stated formula; the instruction model counts
what its docstring says. Then the figures are pinned: the hardware cost (RUN 40's floorless sample), each filter's
delay and attenuation on the grid, the correction capacity, the decode's counts, and the calibrated model's native
budget with its price in refill and AHEAD margin.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v123chain  # noqa: E402


class OnConstructions(unittest.TestCase):
    def test_a_prototype_has_gain_l_and_a_stopband(self):
        h = v123chain.prototype(16, 5.65, 65536, 16000.0, 125)
        self.assertAlmostEqual(sum(h), 125.0, places=9)
        fs = 65536 * 125
        self.assertAlmostEqual(v123chain.response(h, 0.0, fs), 125.0, places=6)
        self.assertLess(v123chain.response(h, 40000.0, fs) / 125.0, 1e-2)

    def test_todays_table_rebuilds_with_unit_gain(self):
        h, L, taps = v123chain.todays_filter()
        self.assertEqual((L, taps), (125, 16))
        self.assertAlmostEqual(sum(h) / L, 1.0, places=3)             # every phase sums to 32768, i.e. 1.0

    def test_the_nominal_refill_is_below_the_measured_one(self):
        # the model's refill is one call a pump run with no gap; RUN 40's 8-push arm measured more, and the two worst
        # readings carry RUN 40's own nominal exactly onto its largest measured refill
        b = v123chain.analyse()["model"]["refill_basis"]
        self.assertLess(b["run40_nominal_ms"], b["run40_median_ms"])
        self.assertLess(b["run40_median_ms"], b["run40_max_ms"])
        self.assertAlmostEqual(b["run40_nominal_ms"] * b["ratio_max"], b["run40_max_ms"], places=9)
        self.assertAlmostEqual(b["run40_nominal_ms"] + b["excess_max_ms"], b["run40_max_ms"], places=9)
        self.assertEqual((round(b["run40_nominal_ms"], 2), round(b["run40_median_ms"], 2), round(b["run40_max_ms"], 2),
                          round(b["ratio_max"], 3), round(b["excess_max_ms"], 2)), (4.23, 4.86, 6.12, 1.447, 1.89))

    def test_the_capacity_formula(self):
        c = v123chain.analyse()["corrections"]
        for name, x in c.items():
            rate, k = (int(v) for v in name.replace("_k", " ").split())
            self.assertAlmostEqual(x["ms_per_s"], k * v123chain.CHUNKS_PER_S * 1000.0 / rate, places=9)

    def test_the_instruction_model(self):
        # today: 128 inputs of 7.8125 outputs; 16 taps; mono
        want = 128 * (46 + 15) + 1000 * (27 + 9 * 16) + 1000 * 8
        self.assertEqual(v123chain.chunk_instructions(4096, 16, 1), want)
        # native: 2 048 inputs a channel, 1 000 of them with an output
        n = 1000 * 46 + 1048 * 28 + 2048 * 15 + 1000 * (27 + 9 * 16)
        self.assertEqual(v123chain.chunk_instructions(65536, 16, 2), 2 * n + 1000 * 8)


class TheFigures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = v123chain.analyse()

    def test_the_hardware_cost_of_production_today(self):
        p = self.r["production_today"]
        self.assertEqual((p["median"]["8"], p["median"]["16"], p["median"]["8first"]), (1021, 1974, 1680))
        self.assertEqual((round(p["per_push"], 1), round(p["per_call"], 1), round(p["per_mac"], 3)), (119.1, 68.0, 0.953))
        self.assertEqual(p["chunk_8push"], 16995)
        self.assertEqual(round(100 * p["cpu_share"], 2), 1.34)

    def test_the_filters(self):
        f = self.r["filters"]
        got = dict((k, (round(v["delay_ms"], 3), dict((fp, (round(x[0], 2), round(x[1], 1))) for fp, x in v["fp"].items())))
                   for k, v in f.items())
        self.assertEqual(got["today_4096_N16"], (1.953, {"1500": (0.05, 44.9)}))
        self.assertEqual(got["65536_N16_b5.65"], (0.122, {"5256": (0.01, 63.4), "12000": (0.87, 20.5)}))
        self.assertEqual(got["65536_N32_b5.65"], (0.244, {"5256": (0.0, 70.5), "12000": (0.01, 59.6)}))
        self.assertEqual(got["65536_N32_b7.86"], (0.244, {"5256": (0.0, 89.0), "12000": (0.08, 41.3)}))
        self.assertEqual(got["65536_N48_b7.86"][0], 0.366)
        self.assertEqual(got["65536_N64_b7.86"][0], 0.488)

    def test_the_corrections(self):
        c = self.r["corrections"]
        self.assertEqual(dict((k, round(v["ms_per_s"], 2)) for k, v in c.items()),
                         {"4096_k1": 7.82, "32768_k8": 7.82, "65536_k16": 7.82, "65536_k8": 3.91})
        self.assertEqual(round(c["65536_k16"]["each_us"], 1), 15.3)

    def test_the_budget(self):
        pr = self.r["production"]
        self.assertEqual((pr["N16_ch2"]["macs"], pr["N32_ch2"]["macs"]), (32000, 64000))
        self.assertEqual(round(100 * pr["N32_ch2"]["cpu_if_mac_scaled"], 2), 5.38)
        self.assertEqual(self.r["decode"], {"bytes_counted": {"today": 4096, "per_channel_slice": 1024},
                                            "values_per_block": {"today": 1, "per_channel_slice": 32}})
        self.assertEqual(self.r["inputs_per_chunk"], {"32768": 1024, "65536": 2048})
        self.assertEqual(self.r["memory"]["target_0125s_stereo_65536"], 32768)

    def test_the_calibrated_native_budget(self):
        m = self.r["model"]
        self.assertEqual((round(m["today_ticks"]), round(m["calibration"], 3)), (15567, 1.092))
        got = dict((k, (round(v["ticks"]), round(100 * v["cpu"], 2), v["calls_at_todays_length"],
                        round(v["refill_ms"], 1), round(v["margin_ms"]["1"], 1), round(v["margin_ms"]["2"], 1)))
                   for k, v in m["native"].items())
        self.assertEqual(got["65536_N16_ch2"], (51140, 4.04, 51, 13.9, 17.3, 48.6))
        self.assertEqual(got["65536_N32_ch2"], (77341, 6.12, 76, 20.7, 10.5, 41.8))
        self.assertEqual(got["65536_N16_ch1"][:3], (25934, 2.05, 26))
        self.assertEqual(round(m["today_refill_ms"], 1), 4.4)
        # the same margins on tools/v28ahead.py's basis, the largest refill RUN 40 measured, two readings
        forms = dict((k, tuple(round(v["margin_forms_ms"][f][a], 1) for f in ("worst_scaled", "worst_additive")
                               for a in ("1", "2")))
                     for k, v in m["native"].items())
        self.assertEqual(forms["65536_N16_ch2"], (11.1, 42.4, 15.5, 46.7))
        self.assertEqual(forms["65536_N32_ch2"], (1.3, 32.5, 8.7, 39.9))
        self.assertEqual(tuple(round(m["today_refill_forms_ms"][f], 1) for f in ("worst_scaled", "worst_additive")),
                         (6.3, 6.2))
        self.assertEqual(m["decode_instr_per_block"], {"today": 16384, "per_channel_slice": 4096})
        self.assertEqual(m["values_per_s"], {"today": 4096, "native_stereo": 131072})


if __name__ == "__main__":
    unittest.main()
