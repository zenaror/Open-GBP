"""tests/host/test_u012_game.py -- GitHub Issue #120: tools/u012game.py, RUN 43's ride-along -- the first raw AUDIO
blocks of a GAME (sync-0001, Yoshi's Island) -- decoded by block, pair and slice. DESCRIPTIVE.

The method is proved on CONSTRUCTIONS first, with nothing from the capture:
  * a sample-and-hold stream at a known period, quantised to slice boundaries, with ±1-bit noise and blocks removed at
    known places, is fitted back to its period and to exactly those gaps, with the coherence at its quantisation
    bound; a slightly wrong period is NOT what the cost chooses;
  * the radix-2 FFT equals a direct DFT; a pure tone's energy falls in its own band; a tone above 2 048 Hz folds
    wholly into the block decode and one below does not; the window-free fractions read 0 and 1 where they must.
Then every figure the record quotes is pinned on the archived capture, which is NOT versioned (0.16 s of a commercial
game's audio output, kept in captures/local/ pending that decision): those tests skip on a host without it.
"""
import cmath
import math
import os
import random
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import u012game  # noqa: E402

P_TRUE = 1596 / 256.0          # 6.234375 slices

# The figures GBP-HW-345 / GBP-HW-346 and the U-GBP-012 / U-GBP-041 addenda quote, pinned here against the tool
# (RUN43, where the raw window is present) and by tests/host/test_run43.py against the record (on every host).
PINS = {
    "transitions": 1286, "even": 588, "odd": 698, "intervals": {6: 493, 7: 136, 12: 16, 13: 14},
    "neighbours": {"1": [502, 583], "2": [129, 135], "3+": [19, 20]}, "adjacent": 0,
    "P": "6.23438", "cycles": "1 596.0", "hz": "10 512.0",
    "gaps": [96, 131, 261, 265, 276, 388, 392, 404, 521, 532, 536, 566], "timing": "11.99",
    "R": "0.9583", "bound": "0.9582", "sd": "0.0011",
    "boundaries": [91, 80, 93, 83, 89, 92, 93, 81, 85, 84, 79, 83, 79, 85, 89], "chi2": "4.19", "tail": "0.0058",
    "pair": ["0.9852", "0.0040", "0.0108"], "slice": ["0.9781", "0.0040", "0.0123", "0.0055"],
    "above_pair": "0.0148", "above_slice": "0.0219",
    "within_block": "0.1165", "within_pair": "0.0082", "fold": "0.0009", "droop": "0.1023",
    "slots": 652, "window_hz": "6.28", "longest": 130, "run_hz": "31.5", "segment_hz": "64",
}


def hold_stream(n_blocks, P, phase, seed, levels=(700, 1100), noise=1):
    """Slice counts of a held sample stream: a change at time phase + j*P shows at the next slice boundary."""
    rng = random.Random(seed)
    total = n_blocks * 16
    vals, lvl, j = [], rng.randint(*levels), 0
    nxt = math.ceil(phase)
    for x in range(total):
        while x >= nxt:
            new = rng.randint(*levels)
            while abs(new - lvl) < 20:
                new = rng.randint(*levels)
            lvl = new
            j += 1
            nxt = math.ceil(phase + j * P)
        vals.append(lvl + rng.randint(-noise, noise))
    return [vals[k * 16:(k + 1) * 16] for k in range(n_blocks)]


def integrating_stream(n_blocks, P, phase, seed, levels=(700, 1100)):
    """A source that changes level at CONTINUOUS instants phase + j*P, read by slices that integrate what falls
    inside them: the slice holding a change reads an intermediate count."""
    rng = random.Random(seed)
    total = n_blocks * 16
    changes, lv = [], [rng.randint(*levels)]
    t, j = phase, 0
    while t < total + P:
        changes.append(t)
        new = rng.randint(*levels)
        while abs(new - lv[-1]) < 20:
            new = rng.randint(*levels)
        lv.append(new)
        j += 1
        t = phase + j * P
    vals, k = [], 0
    for x in range(total):
        while k < len(changes) and changes[k] <= x:
            k += 1
        acc, cur = 0.0, float(x)
        kk = k
        while kk < len(changes) and changes[kk] < x + 1:
            acc += lv[kk] * (changes[kk] - cur)
            cur = changes[kk]
            kk += 1
        acc += lv[kk] * (x + 1 - cur)
        vals.append(int(round(acc)))
    return [vals[i * 16:(i + 1) * 16] for i in range(n_blocks)]


def change_times(n_blocks, P, phase, seed, levels=(700, 1100)):
    """A held sample stream: the instants of its changes and the level after each (lv[0] before the first)."""
    rng = random.Random(seed)
    total = n_blocks * 16
    times, lv, j = [], [rng.randint(*levels)], 0
    while phase + j * P < total + 2:
        new = rng.randint(*levels)
        while abs(new - lv[-1]) < 20:
            new = rng.randint(*levels)
        times.append(phase + j * P)
        lv.append(new)
        j += 1
    return times, lv


def level_at(times, lv, t):
    k = 0
    lo, hi = 0, len(times)
    while lo < hi:                                   # the number of changes at or before t
        mid = (lo + hi) // 2
        if times[mid] <= t:
            lo = mid + 1
        else:
            hi = mid
    k = lo
    return lv[k]


# a fixed displacement of each slice boundary within a block: rms 0.194 slice, at most 0.29
DISPLACE = [0.0, 0.21, -0.12, 0.29, -0.25, 0.08, -0.19, 0.24, -0.28, 0.15, -0.05, 0.27, -0.22, 0.11, -0.16, 0.19]


def point_read(n_blocks, P, phase, seed, displace=None, at=0.5, noise=1):
    """A source changing at CONTINUOUS instants, each slice reading its level ONCE, at x + at (+ its displacement)."""
    times, lv = change_times(n_blocks, P, phase, seed)
    rng = random.Random(seed + 1)
    out = []
    for x in range(n_blocks * 16):
        d = displace[x % 16] if displace else 0.0
        out.append(level_at(times, lv, x + at + d) + rng.randint(-noise, noise))
    return [out[k * 16:(k + 1) * 16] for k in range(n_blocks)]


def pwm_frames(n_blocks, P, phase, seed, displace=None, noise=1, full=2048):
    """A source QUANTISED to one-slice frames (a change at t shows from frame ceil(t)), each frame a PWM pulse at its
    start of duty level/full, read by slices that INTEGRATE a one-slice window [x + d, x + 1 + d)."""
    times, lv = change_times(n_blocks, P, phase, seed)
    rng = random.Random(seed + 1)
    duty = [level_at(times, lv, float(k)) / float(full) for k in range(n_blocks * 16 + 2)]
    out = []
    for x in range(n_blocks * 16):
        d = displace[x % 16] if displace else 0.0
        a, b = x + d, x + 1 + d
        ones = 0.0
        for k in (x - 1, x, x + 1):
            if k < 0:
                continue
            lo, hi = max(a, k), min(b, k + duty[k])
            ones += max(0.0, hi - lo)
        out.append(int(round(ones * full)) + rng.randint(-noise, noise))
    return [out[k * 16:(k + 1) * 16] for k in range(n_blocks)]


def drop(S, missing):
    """Remove the blocks at the given ORIGINAL indices."""
    return [s for k, s in enumerate(S) if k not in set(missing)]


class TheFitOnConstructions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        S = hold_stream(420, P_TRUE, 0.37, 7)
        cls.missing = [150, 151, 260, 333]            # one gap of 2 blocks, two of 1
        cls.S = drop(S, cls.missing)
        cls.TR = u012game.transitions(cls.S)
        cls.fit = u012game.solve(cls.TR)

    def test_the_period_is_recovered(self):
        self.assertAlmostEqual(self.fit["P"], P_TRUE, delta=5e-5)

    def test_the_gaps_are_recovered_exactly(self):
        # stored block 150 is original 152: after stored block 149, two missing; stored 258 is original 261: after
        # stored 257, one; stored 330 is original 334: after stored 329, one
        self.assertEqual(self.fit["gaps"], [(149, 2), (257, 1), (329, 1)])
        self.assertEqual(self.fit["missing"], 4)

    def test_the_coherence_sits_at_the_quantisation_bound(self):
        n = sum(len(t) for t in self.TR)
        m, sd = u012game.bound_spread(n, self.fit["P"], draws=400)
        self.assertLess(abs(self.fit["R"] - u012game.quantisation_bound(self.fit["P"])), 4 * sd)
        self.assertAlmostEqual(m, u012game.quantisation_bound(self.fit["P"]), delta=2 * sd)

    def test_a_contiguous_stream_has_no_gap(self):
        S = hold_stream(200, P_TRUE, 2.1, 11)
        self.assertEqual(u012game.solve(u012game.transitions(S))["gaps"], [])

    def test_a_slightly_wrong_period_costs_more(self):
        """The circularity the first version fell into: at P + 0.0007 extra gaps absorb the drift, but the cost the
        fit minimises is higher than at the true P."""
        c_true = u012game.at_period(self.TR, P_TRUE)[0]
        c_off, G_off, _ = u012game.at_period(self.TR, P_TRUE + 0.0007)
        self.assertGreater(c_off, c_true)

    def test_transitions_land_on_both_parities_for_a_non_pair_period(self):
        p = u012game.parity(self.TR)
        self.assertGreater(p["odd"], 0.3 * (p["odd"] + p["even"]))
        self.assertEqual(set(u012game.intervals(self.TR)) - {6, 7, 12, 13, 18, 19}, set())

    def test_the_per_boundary_counts_are_uniform_for_uniform_slices(self):
        b = u012game.boundary_counts(self.TR)
        self.assertEqual(len(b["counts"]), 15)
        self.assertLess(b["chi2"], 36.1)                          # chi-square 0.999 point on 14 dof


class WhetherChangesSplitSlices(unittest.TestCase):
    """The review of Issue #120: under a source that quantises its own changes to the slice grid, the coherence cannot
    test sub-slice uniformity. What tells the two sources apart is the neighbour of every change."""

    def test_a_frame_quantised_source_leaves_no_same_sign_neighbours(self):
        S = hold_stream(300, P_TRUE, 0.37, 7)
        nb = u012game.neighbours(S, u012game.transitions(S))
        self.assertEqual(nb["adjacent_transitions"], 0)
        self.assertEqual(nb["steps"]["3+"], [0, 0])

    def test_a_continuous_source_read_by_integrating_slices_splits_them(self):
        S = integrating_stream(300, P_TRUE, 0.37, 7)
        nb = u012game.neighbours(S, u012game.transitions(S))
        same, opp = nb["steps"]["3+"]
        self.assertGreater(same, 10 * max(opp, 1))
        self.assertGreater(nb["adjacent_transitions"], 0)

    def fit(self, S):
        TR = u012game.transitions(S)
        f = u012game.solve(TR)
        n = sum(len(t) for t in TR)
        _, sd = u012game.bound_spread(n, f["P"], draws=300)
        return f, sd, u012game.neighbours(S, TR)

    def test_two_models_give_the_capture_signature(self):
        """A source quantised on the slice grid read by integrating slices, and a source changing at continuous
        instants read once per slice: both leave no split slice and a coherence on the bound. The capture cannot
        tell them apart; which holds is U-GBP-012's physical half."""
        for S in (pwm_frames(640, P_TRUE, 0.37, 7), point_read(640, P_TRUE, 0.37, 7)):
            f, sd, nb = self.fit(S)
            self.assertEqual(nb["adjacent_transitions"], 0)
            self.assertEqual(nb["steps"]["3+"], [0, 0])
            self.assertLess(abs(f["R"] - u012game.quantisation_bound(f["P"])), 2 * sd)

    def test_displaced_slices_are_invisible_on_the_grid_and_visible_to_a_point_read(self):
        """The same displacement (DISPLACE, rms 0.194 slice) of the slice boundaries: under the quantised-grid model no
        slice's count changes, so nothing below one slice is tested; under the point-read model the coherence falls
        well below the bound, which is where tools/u012game.py's sigma_2sd would apply."""
        rms = math.sqrt(sum(d * d for d in DISPLACE) / 16.0)
        self.assertAlmostEqual(rms, 0.1942, places=3)
        self.assertEqual(pwm_frames(640, P_TRUE, 0.37, 7, DISPLACE), pwm_frames(640, P_TRUE, 0.37, 7))
        f, sd, _ = self.fit(point_read(640, P_TRUE, 0.37, 7, DISPLACE))
        self.assertLess(f["R"], u012game.quantisation_bound(f["P"]) - 4 * sd)

    def test_the_chi_square_tail(self):
        self.assertAlmostEqual(u012game.chi2_cdf_even(2.0, 2), 1 - math.exp(-1.0), places=12)
        self.assertEqual(round(u012game.chi2_cdf_even(4.19, 14), 4), 0.0058)
        self.assertGreater(u012game.chi2_cdf_even(14.0, 14), 0.5)


class TheSpectralPiecesOnConstructions(unittest.TestCase):
    def test_the_fft_is_a_dft(self):
        rng = random.Random(3)
        x = [rng.uniform(-1, 1) for _ in range(64)]
        X = u012game.fft(x)
        for k in range(64):
            d = sum(x[t] * cmath.exp(-2j * math.pi * k * t / 64) for t in range(64))
            self.assertAlmostEqual(abs(X[k] - d), 0.0, places=9)
        y = u012game.ifft(X)
        self.assertTrue(all(abs(a - b.real) < 1e-9 for a, b in zip(x, y)))
        with self.assertRaises(ValueError):
            u012game.fft([0.0] * 48)

    def tone_blocks(self, hz, n_blocks=128, amp=60.0):
        fs = 65536.0
        vals = [900.0 + amp * math.sin(2 * math.pi * hz * t / fs) for t in range(n_blocks * 16)]
        return [vals[k * 16:(k + 1) * 16] for k in range(n_blocks)]

    def test_a_tone_falls_in_its_own_band(self):
        edges = [0.0, 2048.0, 5256.0, 16384.0, 32768.0]
        for hz, band in ((1000.0, 0), (3000.0, 1), (9000.0, 2), (20000.0, 3)):
            S = self.tone_blocks(hz)
            e = u012game.band_energies(S, [(0, 64), (64, 128)], 16, edges)
            self.assertGreater(e[band], 0.99, (hz, e))

    def test_the_fold(self):
        above = u012game.fold(self.tone_blocks(3000.0), [(0, 64), (64, 128)])
        below = u012game.fold(self.tone_blocks(500.0), [(0, 64), (64, 128)])
        self.assertGreater(above["folded_fraction"], 0.99)
        self.assertLess(below["folded_fraction"], 0.01)
        # the boxcar's own in-band loss at 500 Hz: 1 - |H(500)|^2, within the Hann window's spread
        self.assertAlmostEqual(below["droop"], 1.0 - u012game.boxcar2(500.0), delta=0.01)
        self.assertAlmostEqual(u012game.boxcar2(2048.0) ** 0.5, 0.6376, places=4)

    def test_the_window_free_fractions(self):
        flat_blocks = [[800 + 10 * k] * 16 for k in range(32)]
        self.assertAlmostEqual(u012game.window_free(flat_blocks)["within_block"], 0.0, places=12)
        alt = [[900 + (30 if i % 2 else -30) for i in range(16)] for _ in range(32)]
        w = u012game.window_free(alt)
        self.assertAlmostEqual(w["within_pair"], 1.0, places=12)
        self.assertAlmostEqual(w["within_block"], 1.0, places=12)

    def test_the_uniformity_bound(self):
        self.assertEqual(u012game.sigma_bound(0.961, 0.9582, 0.001, 6.2), 0.0)       # R - 2 sd above the bound
        sig = u012game.sigma_bound(0.95, 0.9582, 0.001, 6.2)
        self.assertAlmostEqual(0.9582 * math.exp(-(2 * math.pi * sig / 6.2) ** 2 / 2), 0.948, places=9)

    def test_the_timing_count(self):
        h = {"t_first": 1000, "t_last": 1000 + int(round(651 * 40500000 / 4096.0)), "tb_hz": 40500000}
        self.assertAlmostEqual(u012game.timing_missing(h, 640), 12.0, places=3)

    def test_runs_and_segments(self):
        G = [0] * 100 + [1] * 70 + [3] * 130
        self.assertEqual(u012game.runs(G), [(0, 100), (100, 170), (170, 300)])
        self.assertEqual(u012game.segments(G), [(0, 64), (100, 164), (170, 234), (234, 298)])


@unittest.skipUnless(os.path.isfile(u012game.DEFAULT), "the RUN 43 raw window is kept in captures/local/ only")
class RUN43(unittest.TestCase):
    _r = None

    @classmethod
    def r(cls):
        if cls._r is None:
            cls._r = u012game.analyse()
        return cls._r

    def test_the_container(self):
        h = self.r()["header"]
        self.assertEqual((h["blocks"], h["seq_first"], h["seq_last"]), (640, 30899, 31538))
        self.assertEqual((h["copy_min"], h["copy_max"], h["copy_sum"], h["copy_n"]), (1125, 1363, 763874, 640))

    def test_the_transitions(self):
        t = self.r()["transitions"]
        self.assertEqual(t["n"], PINS["transitions"])
        self.assertEqual(t["parity"], {"even": PINS["even"], "odd": PINS["odd"]})
        self.assertEqual(t["intervals"], PINS["intervals"])
        self.assertEqual(t["neighbours"]["steps"], PINS["neighbours"])
        self.assertEqual(t["neighbours"]["adjacent_transitions"], PINS["adjacent"])
        self.assertEqual(t["alt"]["4"]["parity"], {"even": 655, "odd": 748})
        self.assertEqual(t["alt"]["8"]["parity"], {"even": 554, "odd": 656})

    def test_the_hold_period(self):
        f = self.r()["fit"]
        self.assertEqual("%.5f" % f["P"], PINS["P"])
        self.assertAlmostEqual(f["agb_cycles_nominal"], 1596.0, delta=0.05)
        self.assertAlmostEqual(f["hz_nominal"], 10512.0, delta=0.5)
        self.assertEqual("%.4f" % f["R"], PINS["R"])
        self.assertEqual("%.4f" % f["bound"], PINS["bound"])
        self.assertEqual("%.4f" % f["bound_spread"][1], PINS["sd"])
        self.assertEqual(round(f["sigma_2sd"], 3), 0.064)

    def test_the_missing_blocks_two_ways(self):
        f, t = self.r()["fit"], self.r()["timing"]
        self.assertEqual(f["gaps"], [(k, 1) for k in PINS["gaps"]])
        self.assertEqual(f["missing"], 12)
        self.assertEqual("%.2f" % t["missing_implied"], PINS["timing"])
        self.assertEqual(f["robust_mu"], {"1.0": True, "6.0": True})

    def test_the_boundaries(self):
        b = self.r()["boundaries"]
        self.assertEqual(b["counts"], PINS["boundaries"])
        self.assertEqual("%.2f" % b["chi2"], PINS["chi2"])
        self.assertEqual("%.4f" % b["lower_tail"], PINS["tail"])

    def test_the_bands(self):
        b = self.r()["bands"]
        self.assertEqual(b["segments"], 6)
        self.assertEqual(["%.4f" % v for v in b["pair"]], PINS["pair"])
        self.assertEqual(["%.4f" % v for v in b["slice"]], PINS["slice"])
        self.assertEqual("%.4f" % sum(b["pair"][1:]), PINS["above_pair"])
        self.assertEqual("%.4f" % sum(b["slice"][1:]), PINS["above_slice"])
        self.assertEqual(round(b["game_nyquist_hz"]), 5256)

    def test_the_window_free_fractions_and_the_fold(self):
        w = self.r()["window_free"]
        self.assertEqual(("%.4f" % w["within_block"], "%.4f" % w["within_pair"]),
                         (PINS["within_block"], PINS["within_pair"]))
        self.assertEqual("%.4f" % self.r()["fold"]["folded_fraction"], PINS["fold"])
        self.assertEqual("%.4f" % self.r()["fold"]["droop"], PINS["droop"])

    def test_the_resolution(self):
        r = self.r()["resolution"]
        self.assertEqual(r["window_slots"], PINS["slots"])
        self.assertEqual("%.2f" % r["window_bin_hz"], PINS["window_hz"])
        self.assertEqual(r["longest_run_blocks"], PINS["longest"])
        self.assertEqual("%.1f" % r["longest_run_bin_hz"], PINS["run_hz"])
        self.assertEqual("%.0f" % r["segment_bin_hz"], PINS["segment_hz"])


if __name__ == "__main__":
    unittest.main()
