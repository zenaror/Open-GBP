"""tests/host/test_v124taps.py -- GitHub Issue #124, Round A: tools/v124taps.py, the 16-vs-32-tap measurement.

PRE-REGISTERED. The tool's criterion and this file's constructions were committed before the tool read any archived
capture. What is proved here, on constructions only: the floor is the stated arithmetic; the two filters are evaluated
at the same instants (a sinusoid comes out undelayed from both); the band power obeys Parseval on a known tone; the
split into content below and above 16 kHz is exact; the fold-in sees a tone above the output's Nyquist and a longer
kernel lets less of it through; and the decision rule reads as written.
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


if __name__ == "__main__":
    unittest.main()
