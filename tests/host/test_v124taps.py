"""tests/host/test_v124taps.py -- GitHub Issue #124, Round A: tools/v124taps.py, the 16-vs-32-tap measurement.

PRE-REGISTERED. The tool's criterion and this file's constructions were committed before the tool read any archived
capture. What is proved here, on constructions only: the floor is the stated arithmetic; the two filters are evaluated
at the same instants (a sinusoid comes out undelayed from both); the band power obeys Parseval on a known tone; the
split into content below and above 16 kHz is exact; the fold-in sees a tone above the output's Nyquist and a longer
kernel lets less of it through; and the decision rule reads as written. The archive's figures (TheArchive) were
added after that commit was pushed and the tool was run: the rule's verdict is NOT SETTLED.
"""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v124taps  # noqa: E402


def tone(freq, amp, n, fs=v124taps.FIN, dc=0.0):
    return [dc + amp * math.sin(2 * math.pi * freq * t / fs) for t in range(n)]


class TheCriterion(unittest.TestCase):
    def test_the_floor_is_the_stated_arithmetic(self):
        self.assertEqual(round(v124taps.floor_rms(5256.0), 4), 0.1156)
        self.assertEqual(round(v124taps.floor_rms(12000.0), 4), 0.1747)

    def test_the_candidates_are_v123chains(self):
        self.assertEqual(v124taps.SIXTEEN, (16, 5.65))
        self.assertEqual(v124taps.THIRTY_TWO, ((32, 5.65), (32, 7.86)))
        self.assertEqual(v124taps.BANDS, (5256.0, 12000.0))

    def test_the_rule(self):
        def res(r1, r2):
            return {"bands": {"5256": {"floor_rms": 0.1, "diff": {"a": {"rms": r1}}},
                              "12000": {"floor_rms": 0.2, "diff": {"a": {"rms": r2}}}}}
        self.assertTrue(v124taps.settled(res(0.09, 0.19)))
        self.assertFalse(v124taps.settled(res(0.11, 0.19)))       # one band over
        self.assertFalse(v124taps.settled(res(0.09, 0.2)))        # equal is not below
        self.assertFalse(v124taps.settled(res(None, 0.1)))        # no segment is no evidence


class OnConstructions(unittest.TestCase):
    def test_zero_phase_at_the_same_instants(self):
        # a 1 kHz tone: output m sits at input time 256 m / 125, i.e. m / 32 000 s, undelayed by either filter
        x = tone(1000.0, 100.0, 4096)
        for f in (v124taps.SIXTEEN,) + v124taps.THIRTY_TWO:
            h, c = v124taps.kernel(*f)
            y = v124taps.trimmed(v124taps.resample(x, h, c))
            g = v124taps.GUARD
            err = max(abs(v - 100.0 * math.sin(2 * math.pi * 1000.0 * (m + g) / 32000.0)) for m, v in enumerate(y))
            self.assertLess(err, 0.1, f)                          # 0.1 % of the amplitude

    def test_unit_gain_at_dc(self):
        x = [300.0] * 2048
        for f in (v124taps.SIXTEEN,) + v124taps.THIRTY_TWO:
            h, c = v124taps.kernel(*f)
            y = v124taps.trimmed(v124taps.resample(x, h, c))
            self.assertLess(max(abs(v - 300.0) for v in y), 0.3, f)

    def test_band_power_obeys_parseval(self):
        # a 1 kHz tone of amplitude 1 at the output rate: power 1/2 in any band that holds it, none in one that doesn't
        y = [math.sin(2 * math.pi * 1000.0 * t / 32000.0) for t in range(4096)]
        p, n = v124taps.band_power(y, 5256.0)
        self.assertAlmostEqual(p / n, 0.5, places=3)
        p, n = v124taps.band_power(y, 500.0)
        self.assertLess(p / n, 1e-4)

    def test_the_split_is_exact(self):
        x = [a + b for a, b in zip(tone(1000.0, 50.0, 3000), tone(20000.0, 5.0, 3000))]
        lo, hi = v124taps.split(x)
        self.assertLess(max(abs(a + b - v) for a, b, v in zip(lo, hi, x)), 1e-9)
        p_hi, n = v124taps.band_power(hi[500:2500], 32768.0, fs=v124taps.FIN)
        self.assertAlmostEqual(p_hi / n, 12.5, delta=1.0)        # the 20 kHz tone, amplitude 5: 5^2 / 2

    def test_the_fold_in_sees_what_aliases_and_a_longer_kernel_lets_less_through(self):
        # 20 kHz lands at 32 000 - 20 000 = 12 000 Hz: inside [0, 12 000], outside [0, 5 256]
        hi = tone(20000.0, 10.0, 4096)
        got = {}
        for f in (v124taps.SIXTEEN,) + v124taps.THIRTY_TWO:
            h, c = v124taps.kernel(*f)
            y = v124taps.trimmed(v124taps.resample(hi, h, c))
            p12, n = v124taps.band_power(y, 12000.0)
            p5, _ = v124taps.band_power(y, 5256.0)
            got[f] = (math.sqrt(p12 / n), math.sqrt(p5 / n))
        self.assertGreater(got[(16, 5.65)][0], 0.1)               # 16 taps pass a visible part of it
        self.assertLess(got[(32, 7.86)][0], got[(16, 5.65)][0])
        for f, (r12, r5) in got.items():
            self.assertLess(r5, 0.05 * max(r12, 1e-12) + 1e-3, f)  # nothing lands below 5 256 Hz


class TheSweepsRule(unittest.TestCase):
    """The beta sweep's choice and fallback, registered with the grid before the sweep ran; on constructions."""

    def fake(self, r5, r12):
        return {"bands": {"5256": {"floor_rms": 1.0, "diff": {"a": {"rms": r5, "ratio_to_floor": r5}}},
                          "12000": {"floor_rms": 1.0, "diff": {"a": {"rms": r12, "ratio_to_floor": r12}}}}}

    def test_the_grid_is_registered(self):
        self.assertEqual(v124taps.BETA_GRID, (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 5.65, 6.5, 7.86))

    def test_the_smallest_worst_cell_passes_and_ties_go_to_the_larger_beta(self):
        by = {2.0: [self.fake(0.2, 0.9)], 4.0: [self.fake(0.3, 0.6)], 6.0: [self.fake(0.6, 0.3)],
              7.0: [self.fake(0.5, 1.2)]}
        self.assertEqual(v124taps.choose(by), (6.0, 0.6))                # 4.0 and 6.0 tie at 0.6: the larger beta
        by[5.0] = [self.fake(0.4, 0.55)]
        self.assertEqual(v124taps.choose(by), (5.0, 0.55))

    def test_a_beta_must_pass_on_every_capture(self):
        by = {3.0: [self.fake(0.2, 0.3), self.fake(0.2, 1.01)]}
        self.assertEqual(v124taps.choose(by), (None, None))              # the fallback: 32 taps

    def test_per_phase_normalisation_is_the_chains(self):
        # every output of a constant is the constant, for every beta: no phase gain left for a DC to turn into a pattern
        x = [256.0] * 2048
        for beta in (0.0, 2.0, 5.65, 7.86):
            h, c = v124taps.kernel(16, beta, per_phase=True)
            y = v124taps.trimmed(v124taps.resample(x, h, c))
            self.assertLess(max(abs(v - 256.0) for v in y), 1e-9, beta)
        h, c = v124taps.kernel(16, 2.0)                                  # the whole-normalised one does not
        y = v124taps.trimmed(v124taps.resample(x, h, c))
        self.assertGreater(max(abs(v - 256.0) for v in y), 0.5)

    def test_the_sweep_runs_on_a_construction(self):
        # a 1 kHz tone of 60 steps: beta 5.65 and 7.86 pass and the smaller worst cell is chosen; beta 2.0 FAILS, with
        # the phases normalised: its sidelobes let the tone's own images through (64 536 Hz upsampled lands on 536 Hz),
        # a property of that design, not of the measure
        r = v124taps.sweep({"T": [tone(1000.0, 60.0, 3000, dc=256.0)]}, grid=(2.0, 5.65, 7.86), with_32=False)
        self.assertEqual(sorted(r["betas"]), ["2.00", "5.65", "7.86"])
        self.assertEqual([r["betas"][b]["settled"] for b in ("2.00", "5.65", "7.86")], [False, True, True])
        best = min(("5.65", "7.86"), key=lambda b: r["betas"][b]["worst_ratio"])
        self.assertEqual("%.2f" % r["chosen_beta"], best)
        self.assertFalse(r["fallback_32_taps"])
        self.assertEqual(r["captures"], ["T"])
        self.assertIn("whole", r["betas"]["2.00"])                       # both normalisations reported
        self.assertFalse(r["betas"]["2.00"]["whole"]["settled"])         # the whole-sum DC term adds to beta 2.0's

    def test_the_reference_and_the_32_tap_choice(self):
        self.assertEqual(v124taps.REFERENCE, (128, 10.0))
        # a 1 kHz tone: both 32-tap designs sit far under the floor against the reference, and a choice is made
        t = v124taps.choose_32({"T": [tone(1000.0, 60.0, 3000, dc=256.0)]})
        self.assertEqual(t["reference"], "N128_b10.00")
        self.assertEqual(sorted(t["candidates"]), ["N32_b5.65", "N32_b7.86"])
        self.assertIn(t["chosen"], t["candidates"])
        w = dict((k, c["worst_ratio"]) for k, c in t["candidates"].items())
        self.assertEqual(t["chosen"], min(w, key=lambda k: (w[k], -t["candidates"][k]["beta"])))


class TheArchive(unittest.TestCase):
    """The result, recorded after the criterion above was committed (10fa60a) and pushed: 16 taps are NOT SETTLED.
    One cell of the grid is over the floor -- RUN 33's tones in [0, 12 000] Hz -- and every other cell is under it."""

    @classmethod
    def setUpClass(cls):
        cls.r = dict((n, v124taps.measure(v124taps.tone_runs(n))) for n in ("RUN33", "RUN34"))

    def ratios(self, r):
        return dict((B, tuple(round(b["diff"][k]["ratio_to_floor"], 3) for k in ("N32_b5.65", "N32_b7.86")))
                    for B, b in r["bands"].items())

    def test_run33_is_over_the_floor_in_the_12_khz_band_only(self):
        r = self.r["RUN33"]
        self.assertEqual((r["runs"], r["inputs"]), (5, 20480))
        self.assertEqual(self.ratios(r), {"5256": (0.158, 0.251), "12000": (1.275, 1.223)})
        self.assertFalse(v124taps.settled(r))
        self.assertEqual(round(r["bands"]["12000"]["fold"]["N16_b5.65"]["ratio_to_floor"], 3), 0.545)
        self.assertEqual(round(r["bands"]["12000"]["diff"]["N32_b5.65"]["max_abs"], 3), 2.469)

    def test_run34_is_under_it_everywhere(self):
        r = self.r["RUN34"]
        self.assertEqual(self.ratios(r), {"5256": (0.132, 0.236), "12000": (0.269, 0.288)})
        self.assertTrue(v124taps.settled(r))

    def test_run43_is_under_it_everywhere(self):
        kind, path = v124taps.v123frame.CAPTURES["RUN43"]
        if not os.path.isfile(path):
            self.skipTest("the RUN 43 raw window is kept in captures/local/ only (tools/v124taps.py)")
        r = v124taps.measure(v124taps.game_runs())
        self.assertEqual((r["runs"], r["inputs"]), (13, 10240))
        self.assertEqual(self.ratios(r), {"5256": (0.118, 0.211), "12000": (0.455, 0.444)})
        self.assertTrue(v124taps.settled(r))

    def test_the_rule_says_not_settled(self):
        self.assertFalse(all(v124taps.settled(r) for r in self.r.values()))


class TheSweep(unittest.TestCase):
    """The beta sweep, run after b5588e7..50a0c1a were pushed: per-phase kernels decide, beta 4.0 and 5.0 pass, the
    registered choice is 4.0; under whole-sum kernels none passes, so the correction is DECISIVE for the pass. The
    tones carry every worst cell; RUN 43 is checked where present."""

    @classmethod
    def setUpClass(cls):
        cls.r = v124taps.sweep(dict((n, v124taps.tone_runs(n)) for n in ("RUN33", "RUN34")))

    def test_which_betas_pass(self):
        b = self.r["betas"]
        self.assertEqual([k for k in sorted(b, key=float) if b[k]["settled"]], ["4.00", "5.00"])
        self.assertEqual(dict((k, round(v["worst_ratio"], 3)) for k, v in b.items()),
                         {"0.00": 11.344, "1.00": 8.75, "2.00": 4.542, "3.00": 1.847, "4.00": 0.63, "5.00": 0.981,
                          "5.65": 1.271, "6.50": 1.631, "7.86": 2.168})

    def test_the_registered_choice_is_beta_4(self):
        self.assertEqual((self.r["chosen_beta"], round(self.r["chosen_worst"], 3)), (4.0, 0.63))
        self.assertFalse(self.r["fallback_32_taps"])

    def test_under_whole_sum_kernels_nothing_passes(self):
        w = dict((k, v["whole"]) for k, v in self.r["betas"].items())
        self.assertFalse(any(v["settled"] for v in w.values()))
        self.assertEqual((round(w["4.00"]["worst_ratio"], 3), round(w["5.00"]["worst_ratio"], 3)), (1.207, 1.006))

    def test_the_32_tap_choice_as_registered(self):
        t = self.r["thirty_two"]
        self.assertEqual(t["chosen"], "N32_b7.86")
        self.assertEqual(dict((k, round(c["worst_ratio"], 3)) for k, c in t["candidates"].items()),
                         {"N32_b5.65": 0.071, "N32_b7.86": 0.063})

    def test_run43_passes_at_beta_4_and_5(self):
        kind, path = v124taps.v123frame.CAPTURES["RUN43"]
        if not os.path.isfile(path):
            self.skipTest("the RUN 43 raw window is kept in captures/local/ only (tools/v124taps.py)")
        g = v124taps.game_runs()
        for beta, want in ((4.0, {"5256": (0.081, 0.1), "12000": (0.208, 0.185)}),
                           (5.0, {"5256": (0.007, 0.022), "12000": (0.354, 0.327)})):
            r = v124taps.measure(g, (16, beta), per_phase=True)
            self.assertTrue(v124taps.settled(r), beta)
            self.assertEqual(dict((B, tuple(round(b["diff"][k]["ratio_to_floor"], 3) for k in ("N32_b5.65", "N32_b7.86")))
                                  for B, b in r["bands"].items()), want, beta)


class TheShippedObject(unittest.TestCase):
    """What runs is a [125][16] Q15 table, not the ideal kernel: beta 4.0 with phase 0's t = +8 tap dropped (a 16-tap
    table cannot hold it), quantised as tools/gen_aresamp.py quantises, by the same rule. SETTLED; the rounding error
    alone is under 0.005 of the floor and the dropped tap's effect under 0.035, on every capture."""

    def test_every_phase_sums_to_exactly_32768_with_at_most_16_taps(self):
        self.assertEqual(set(v124taps.q15_phase_sums(16, 4.0)), {32768})
        self.assertLessEqual(max(v124taps.phase_tap_counts(16, 4.0)), 16)
        self.assertEqual(max(v124taps.phase_tap_counts(16, 4.0, representable=False)), 17)   # the prototype's phase 0
        h, c = v124taps.kernel(16, 4.0, per_phase=True, q15=True, representable=True)
        y = v124taps.trimmed(v124taps.resample([256.0] * 2048, h, c))
        self.assertLess(max(abs(v - 256.0) for v in y), 1e-9)             # a DC passes exactly

    def test_the_representable_table_passes_on_the_tones(self):
        r = v124taps.shipped(dict((n, v124taps.tone_runs(n)) for n in ("RUN33", "RUN34")))
        self.assertTrue(r["settled"])
        self.assertTrue(r["phase_sums_exact"])
        self.assertEqual(round(r["worst_ratio"], 3), 0.628)
        for n in r["captures"]:
            self.assertLess(max(r["rounding"][n].values()), 0.005, n)
            self.assertLess(max(r["dropped_tap"][n].values()), 0.035, n)


if __name__ == "__main__":
    unittest.main()
