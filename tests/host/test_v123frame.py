"""tests/host/test_v123frame.py -- GitHub Issue #123: tools/v123frame.py, a 256-byte AUDIO slice read as eight
stride-8 streams, and the update grid each archived capture's level follows. DESCRIPTIVE; a reading of the bytes,
never a gate.

On constructions: slices built stream by stream read back what was put in (A, B, the rise, the extras, the identity);
a slice whose odd streams disagree, or whose stream holds two pulses, is reported so; a block whose level changes only
between pairs reads as a 512-cycle grid, one that changes inside a pair as a 256-cycle grid, and a still one as
neither. Then the versioned tones are pinned (RUN 33, RUN 34), and RUN 43's raw window when this checkout has it (a
commercial game's output, captures/local only: aggregates, never bytes).
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v123frame  # noqa: E402


def pulse(start, width):
    """A 256-bit stream, MSB first, with ones at [start, start + width)."""
    return ((1 << width) - 1) << (256 - start - width)


def slice_from(streams):
    """256 bytes whose stream j is streams[j]."""
    out = bytearray(256)
    for j, s in enumerate(streams):
        b = s.to_bytes(32, "big")
        for g in range(32):
            out[g * 8 + j] = b[g]
    return bytes(out)


def block_from(levels):
    """A block of 16 slices, slice i a pulse of width levels[i] in A and B alike, rising at 7."""
    return b"".join(slice_from([pulse(7, w)] * 8) for w in levels)


class OnConstructions(unittest.TestCase):
    def test_a_slice_reads_back(self):
        a, b = pulse(7, 128), pulse(7, 100)
        extra = 1 << (256 - 6)                          # bit 5, two before the rise, in an even stream only
        sl = slice_from([a | extra, a, a, a, b, b, b, b])
        r = v123frame.slice_record(sl)
        self.assertEqual((r["pairs"], r["superset"], r["one_pulse"], r["rise"], r["wa"], r["wb"], r["extras"]),
                         (True, True, True, 7, 128, 100, 1))
        self.assertTrue(r["identity"])
        self.assertFalse(r["a_eq_b"])
        self.assertEqual(sum(bin(x).count("1") for x in sl), 4 * 128 + 4 * 100 + 1)
        self.assertEqual(r["even_runs"], [2, 1, 1, 1])  # bit 6 is clear: the extra is a second run
        touch = 1 << (256 - 7)                          # bit 6, touching the pulse: still one run
        far = 1 << 10                                   # an extra far from the pulse, in stream 2
        r = v123frame.slice_record(slice_from([a | touch, a, a | far, a, b, b, b, b]))
        self.assertEqual((r["even_runs"], r["extras"], r["identity"]), ([1, 2, 1, 1], 2, True))

    def test_what_breaks_the_reading_is_reported(self):
        a = pulse(7, 128)
        r = v123frame.slice_record(slice_from([a, a, a, pulse(7, 127), a, a, a, a]))
        self.assertFalse(r["pairs"])                    # stream 3 differs from stream 1
        two = pulse(7, 40) | pulse(100, 40)
        r = v123frame.slice_record(slice_from([two] * 8))
        self.assertFalse(r["one_pulse"])
        r = v123frame.slice_record(slice_from([0, a, a, a, a, a, a, a]))
        self.assertFalse(r["superset"])                 # an even stream lacking its odd partner's bits

    def test_a_flat_block_can_trade_a_for_b(self):
        # the counts spread by nothing, and A and B trade a bit: flat, and not constant
        def blk(pairs):
            return b"".join(slice_from([pulse(7, wa)] * 4 + [pulse(7, wb)] * 4) for wa, wb in pairs)
        cases = ((blk([(111, 114)] * 8 + [(112, 113)] * 8), (1, 0)), (blk([(111, 114)] * 16), (1, 1)),
                 (blk([(111, 114)] * 8 + [(113, 116)] * 8), (0, 0)))
        for b, want in cases:
            orig = v123frame.load
            v123frame.load = lambda kind, path, _b=b: [(None, [_b])]
            try:
                r = v123frame.analyse_capture("synthetic", "")
            finally:
                v123frame.load = orig
            self.assertEqual((r["flat"], r["flat_ab_constant"]), want)

    def test_the_grid(self):
        cases = {"512-cycle (pair) grid": [128] * 6 + [140] * 10,
                 "256-cycle (slice) grid": [128] * 7 + [140] * 9,
                 "no level change": [128] * 16}
        for grid, levels in cases.items():
            orig = v123frame.load
            v123frame.load = lambda kind, path, _b=block_from(levels): [(None, [_b])]
            try:
                r = v123frame.analyse_capture("synthetic", "")
            finally:
                v123frame.load = orig
            self.assertEqual(r["grid"], grid)


class TheTones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = dict((n, v123frame.analyse_capture(*v123frame.CAPTURES[n])) for n in ("RUN33", "RUN34"))

    def test_the_reading_holds_in_every_slice(self):
        for n, r in self.r.items():
            self.assertEqual(r["slices"], 20480)
            for k in ("pairs", "superset", "one_pulse", "identity", "a_eq_b"):
                self.assertEqual(r[k], 20480, (n, k))
            self.assertLessEqual(r["extras_max"], 3)
            self.assertEqual((r["wa_min"], r["wa_max"]), (98, 158))
            self.assertEqual(r["rest"], {"128,128": 4096})
            self.assertEqual(r["side_share"], 0.0)                 # A == B: no side at all
            self.assertEqual(r["flat"], r["flat_ab_constant"])       # every flat tone block: A and B constant
        self.assertEqual(self.r["RUN33"]["rise"], {"6": 20480})
        self.assertEqual(self.r["RUN34"]["rise"], {"7": 20480})
        self.assertEqual((self.r["RUN33"]["flat"], self.r["RUN34"]["flat"]), (1039, 1217))
        # the even streams are NOT single runs: their extras also sit away from the pulse
        self.assertEqual(self.r["RUN33"]["even_multi_run"], {"0": 8429, "2": 15, "4": 12, "6": 7})
        self.assertEqual(self.r["RUN34"]["even_multi_run"], {"0": 8978, "2": 0, "4": 0, "6": 0})

    def test_the_tones_follow_the_pair_grid(self):
        for n, even in (("RUN33", 241), ("RUN34", 63)):
            r = self.r[n]
            self.assertEqual((r["pair_equal"], r["pair_n"], r["change_even"], r["change_odd"]), (10240, 10240, even, 0))
            self.assertEqual(r["grid"], "512-cycle (pair) grid")
        self.assertEqual(self.r["RUN33"]["change_even"] + self.r["RUN34"]["change_even"], 304)   # GBP-HW-315's 304


class TheGameWindow(unittest.TestCase):
    def test_run43(self):
        kind, path = v123frame.CAPTURES["RUN43"]
        if not os.path.isfile(path):
            self.skipTest("the RUN 43 raw window is kept in captures/local/ only (tools/v123frame.py)")
        r = v123frame.analyse_capture(kind, path)
        self.assertEqual(r["slices"], 10240)
        for k in ("pairs", "superset", "one_pulse", "identity"):
            self.assertEqual(r[k], 10240, k)
        self.assertEqual((r["a_eq_b"], r["rise"], r["wa_min"], r["wa_max"]), (1267, {"7": 10240}, 83, 135))
        self.assertLessEqual(r["extras_max"], 10)
        self.assertEqual((r["pair_equal"], r["pair_n"], r["change_even"], r["change_odd"]), (4312, 5120, 703, 808))
        self.assertEqual(r["grid"], "256-cycle (slice) grid")
        self.assertEqual(round(r["side_share"], 4), 0.0446)
        self.assertEqual(r["even_multi_run"], {"0": 10240, "2": 459, "4": 1574, "6": 172})
        self.assertEqual((r["flat"], r["flat_ab_constant"]), (1, 0))  # its one flat block trades A for B


if __name__ == "__main__":
    unittest.main()
