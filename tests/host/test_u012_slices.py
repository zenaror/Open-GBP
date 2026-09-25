"""tests/host/test_u012_slices.py -- GitHub Issue #118: does decoding the AUDIO block's slices recover the bandwidth
the runtime's one-value-per-block decode throws away? tools/u012slices.py, on the versioned RUN 33 / RUN 34 raw
captures (whole 4 096-byte blocks, the only game-free raw blocks that are versioned; no game's blocks were ever stored).

DESCRIPTIVE. The method is first proved on constructions (a synthetic square is decoded to itself; a signal with no
energy above 2 048 Hz reads 0; a staircase built from one value per block reads as the runtime would see it), then
every figure of the record is pinned:
  * the block decode's "nothing above 2 048 Hz" is an IDENTITY of its rate (its Nyquist is the cut), documented as
    such and never tabulated as a measurement; what it does to the tone is a boxcar-and-decimate with no anti-alias
    stage, whose in-band harmonic ratios are pinned beside the pair decode's;
  * the pair decode (32 768/s nominal) is the programmed square wave: correlation >= 0.99998 with the ideal square at
    its best phase, the same fraction of energy above 2 048 Hz within 0.0001 (2.5 % at 128 Hz .. 18.7 % at
    1 024 Hz), and the same odd-harmonic amplitudes to 0.0003 up to the 127th;
  * the slice decode (65 536/s nominal) adds nothing beyond the pair decode's grid, as GBP-HW-315's even-slice
    transitions predict;
  * every Hz figure of the pair and slice decodes is conditional on uniform slices (U-GBP-041).
"""
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import u012slices  # noqa: E402
import v18block  # noqa: E402


class Result(object):
    _r = None

    @classmethod
    def get(cls):
        if cls._r is None:
            cls._r = dict((run, u012slices.analyse(path)) for run, path in u012slices.FIXTURES.items())
        return cls._r


def synthetic_blocks(period_blocks, edge_slice, n_blocks, lo=1024, hi=1536):
    """Blocks whose sixteen slices carry a 50 % square wave of `period_blocks`, switching at slice `edge_slice`
    of the edge blocks: every 256-byte slice is `count` one-bits (0xFF bytes then a partial byte then 0x00)."""
    def slice_bytes(count):
        full, rest = divmod(count, 8)
        return bytes([0xFF] * full + ([0xFF << (8 - rest) & 0xFF] if rest else []) +
                     [0x00] * (256 - full - (1 if rest else 0)))
    half = period_blocks // 2
    blocks = []
    for i in range(n_blocks):
        phase = i % period_blocks
        level_before = hi if phase < half else lo
        level_after = hi if (phase + 1) % period_blocks < half or phase + 1 == half else lo
        if phase == half - 1 or phase == period_blocks - 1:       # an edge falls inside this block
            nxt = lo if phase == half - 1 else hi
            b = b"".join(slice_bytes(level_before if s < edge_slice else nxt) for s in range(16))
        else:
            b = b"".join(slice_bytes(level_before) for _ in range(16))
        blocks.append(b)
    return blocks


class TheMethodOnConstructions(unittest.TestCase):
    def test_a_synthetic_square_decodes_to_itself_at_pair_rate(self):
        blocks = synthetic_blocks(8, 12, 160)
        r = u012slices.analyse_window(blocks, 8)
        pair = r["decodes"]["pair"]
        self.assertGreater(pair["corr"], 0.9999)
        self.assertAlmostEqual(pair["high"], pair["ideal_high"], places=6)
        self.assertEqual(r["decodes"]["block"]["values"], 160)
        self.assertEqual((pair["values"], r["decodes"]["slice"]["values"]), (1280, 2560))

    def test_the_block_decodes_high_fraction_is_an_identity_not_a_measurement(self):
        """kmax = n / 2 at the block rate: Parseval's whole sum is 'low', so ANY input reads 0. Documented, not used."""
        import random
        rng = random.Random(12)
        for _ in range(3):
            x = [rng.random() * 1000 for _ in range(160)]
            self.assertAlmostEqual(u012slices.high_fraction(x, 4096), 0.0, places=9)

    def test_a_pure_low_tone_has_no_energy_above_the_cut(self):
        n = 1280
        x = [math.sin(2 * math.pi * 5 * t / n) for t in range(n)]        # 5 periods over 1 280 at 32 768/s = 128 Hz
        self.assertAlmostEqual(u012slices.high_fraction(x, 32768), 0.0, places=9)
        x = [math.sin(2 * math.pi * 100 * t / n) for t in range(n)]      # 2 560 Hz
        self.assertAlmostEqual(u012slices.high_fraction(x, 32768), 1.0, places=9)

    def test_the_ideal_squares_high_fraction_is_the_harmonic_series(self):
        """A 50 % square's energy above 2 048 Hz is its odd harmonics there: 1/n^2 over 8/pi^2, sampled."""
        for period, want in ((256, 0.0250), (32, 0.1868)):             # 128 Hz and 1 024 Hz at 32 768/s
            ideal = u012slices.square(1280, period, 0)
            self.assertAlmostEqual(u012slices.high_fraction(ideal, 32768), want, places=4)
        # the continuous series, for the 128 Hz case: odd n >= 17 of sum 1/n^2 = pi^2/8
        cont = sum(1.0 / n ** 2 for n in range(17, 100001, 2)) / (math.pi ** 2 / 8)
        self.assertAlmostEqual(cont, 0.0250, places=3)

    def test_the_reference_has_one_free_parameter_the_phase(self):
        x = u012slices.square(256, 32, 7)
        self.assertEqual(u012slices.best_square(x, 32), (1.0, 7))


class TheArchive(unittest.TestCase):
    WINDOWS = {(33, 1): (32, 128.0), (33, 2): (8, 512.0), (33, 3): (16, 256.0), (33, 4): (4, 1024.0),
               (34, 1): (32, 128.0), (34, 2): (32, 128.0), (34, 3): (32, 128.0), (34, 4): (32, 128.0)}
    HIGH = {32: (0.0250, 0.0252), 16: (0.0497, 0.0502), 8: (0.0981, 0.0990), 4: (0.1868, 0.1888)}   # the IDEAL square's

    def rows(self):
        for run, r in sorted(Result.get().items()):
            for w in r["windows"]:
                yield run, w

    def test_the_windows_are_the_programmed_tones(self):
        got = dict(((run, w["index"]), (w["period_blocks"], w["f0_hz"])) for run, w in self.rows())
        self.assertEqual(got, self.WINDOWS)
        self.assertEqual((Result.get()[33]["axis"], Result.get()[34]["axis"]), ("F", "V"))
        for run, w in self.rows():
            d = w["decodes"]
            self.assertEqual((d["block"]["values"], d["pair"]["values"], d["slice"]["values"]), (160, 1280, 2560))
            self.assertEqual((d["block"]["rate"], d["pair"]["rate"], d["slice"]["rate"]), (4096, 32768, 65536))

    def test_the_block_decodes_in_band_harmonics_are_distorted_by_the_fold(self):
        """The runtime's value is a boxcar over eight pair values, decimated by eight, with no anti-alias stage."""
        ib = dict(((run, w["index"]), w["decodes"]["in_band"]) for run, w in self.rows())
        self.assertEqual((round(ib[(33, 2)][3]["block"], 3), round(ib[(33, 2)][3]["pair"], 3)), (0.263, 0.334))
        self.assertEqual((round(ib[(33, 3)][7]["block"], 3), round(ib[(33, 3)][7]["pair"], 3)), (0.063, 0.144))
        self.assertEqual((round(ib[(33, 1)][15]["block"], 3), round(ib[(34, 1)][15]["block"], 3),
                          round(ib[(33, 1)][15]["pair"], 3), round(ib[(34, 1)][15]["pair"], 3)),
                         (0.010, 0.074, 0.067, 0.067))                       # the same tone, two edge positions
        self.assertEqual(ib[(33, 4)], {})                                     # 1 024 Hz: no harmonic below the cut
        for key, d in ib.items():
            self.assertEqual(sorted(d), [n for n in range(3, 16, 2) if n * 4096.0 / {1: 32, 2: 8, 3: 16, 4: 4}[key[1]]
                                                                     < 2048] if key[0] == 33 else list(range(3, 16, 2)), key)

    def test_the_pair_decode_is_the_square_wave(self):
        for run, w in self.rows():
            p = w["decodes"]["pair"]
            self.assertGreaterEqual(p["corr"], 0.99998, (run, w["index"]))
            self.assertLessEqual(abs(p["high"] - p["ideal_high"]), 0.0001, (run, w["index"]))
            self.assertEqual(round(p["ideal_high"], 4), self.HIGH[w["period_blocks"]][0], (run, w["index"]))
            dev = max(abs(p["harmonics"][n] - p["ideal_harmonics"][n]) for n in p["harmonics"])
            self.assertLessEqual(dev, 0.0003, (run, w["index"]))
            self.assertEqual(max(p["harmonics"]), {32: 127, 16: 63, 8: 31, 4: 15}[w["period_blocks"]])
            self.assertAlmostEqual(p["harmonics"][3], p["ideal_harmonics"][3], places=3, msg=(run, w["index"]))
            self.assertEqual(round(p["ideal_harmonics"][3], 3), {32: 0.333, 16: 0.334, 8: 0.334, 4: 0.338}
                             [w["period_blocks"]], (run, w["index"]))                 # sin(pi/M)/sin(3pi/M), M = 8P

    def test_the_slice_decode_adds_nothing_beyond_the_pair_grid(self):
        """The slice decode is the pair decode held: its best phase is twice the pair's in every window. A
        construction with an odd edge slice shows the discriminating assertion is the pair one, not the slice one."""
        for run, w in self.rows():
            s, p = w["decodes"]["slice"], w["decodes"]["pair"]
            self.assertGreaterEqual(s["corr"], 0.9999, (run, w["index"]))
            self.assertEqual(s["phase"], 2 * p["phase"], (run, w["index"]))
            self.assertEqual(round(s["high"], 4), self.HIGH[w["period_blocks"]][1], (run, w["index"]))
            self.assertEqual(round(s["ideal_high"], 4), self.HIGH[w["period_blocks"]][1], (run, w["index"]))
        odd = u012slices.analyse_window(synthetic_blocks(8, 7, 160), 8)["decodes"]
        self.assertGreater(odd["slice"]["corr"], 0.9999)                    # the slice decode still fits
        self.assertLess(odd["pair"]["corr"], 0.999)                         # the pair decode no longer does
        self.assertEqual(odd["slice"]["phase"] % 2, 1)

    def test_the_energy_the_runtime_throws_away_per_tone(self):
        """2.5 %, 5.0 %, 9.8 % and 18.7 % of the tone at 128, 256, 512 and 1 024 Hz -- the pair decode's own."""
        got = dict((w["period_blocks"], round(w["decodes"]["pair"]["high"], 3)) for run, w in self.rows() if run == 33)
        self.assertEqual(got, {32: 0.025, 16: 0.05, 8: 0.098, 4: 0.187})

    def test_the_controls_noise_floor(self):
        got = dict((run, [round(c["pair_sd_bits"], 3) for c in r["controls"]]) for run, r in Result.get().items())
        self.assertEqual(got, {33: [0.108], 34: [0.362]})

    def test_the_pair_grid_is_GBP_HW_315s(self):
        """Every transition on an even slice: the slice decode's odd samples repeat the even ones' levels."""
        for run, path in u012slices.FIXTURES.items():
            anchors, wins = u012slices.load(path)
            for wi, w in enumerate(wins):
                if anchors[wi]["kind"] != 1:
                    continue
                ks, other = set(), 0
                for b in w[u012slices.ONSET:]:
                    s = v18block.shape(v18block.slice_counts(b))
                    if s["kind"] == "step":
                        ks.add(s["k"])
                    other += s["kind"] == "other"
                self.assertTrue(ks and all(k % 2 == 0 for k in ks), (run, wi, ks))
                self.assertEqual(other, 0, (run, wi))


class TheCostsAreArithmeticInTodaysUnits(unittest.TestCase):
    def test_the_multipliers(self):
        c = u012slices.costs()
        self.assertEqual(c["decoded_per_s"], {"block": 4096, "pair": 32768, "slice": 65536})
        self.assertEqual(c["ring_1s_kib"], {"block": 8.0, "pair": 64.0, "slice": 128.0})
        self.assertEqual(c["target_0_5s_samples"], {"block": 2048, "pair": 16384, "slice": 32768})
        self.assertEqual(c["pushes_per_1000_frame_chunk"], {"block": 128, "pair": 1024, "slice": 2048})
        self.assertEqual(round(c["correction_ceiling_per_s"], 3), 32.028)             # 32 028.483 Hz / 1 000 frames
        self.assertEqual(dict((k, round(v, 2)) for k, v in c["one_correction_per_chunk_ms_per_s"].items()),
                         {"block": 7.82, "pair": 0.98, "slice": 0.49})

    def test_the_need_is_derived_from_the_record_not_guessed(self):
        """The AI's 32 028.483 frames/s (GBP-HW-325) through 125/16 against 4 096 minus the losses (GBP-HW-322/337)."""
        c = u012slices.costs()
        self.assertEqual(round(c["consumed_decoded_per_s"], 2), 4099.65)
        self.assertEqual(dict((k, round(v, 2)) for k, v in c["need_samples_per_s"].items()),
                         {"RUN 38": 29.05, "RUN 42": 10.91})
        self.assertEqual(dict((k, round(v, 2)) for k, v in c["need_ms_per_s"].items()), {"RUN 38": 7.09, "RUN 42": 2.66})
        self.assertEqual(round(c["observed_dup_ms_per_s"]["RUN 38"], 2), 7.50)
        self.assertEqual(round(100 * c["observed_dup_per_s"]["RUN 38"] / c["correction_ceiling_per_s"]), 96)
        self.assertLess(c["one_correction_per_chunk_ms_per_s"]["pair"], min(c["need_ms_per_s"].values()))
        ev = open(os.path.join(ROOT, "docs", "research", "EVIDENCE.md"), encoding="utf-8").read()
        self.assertIn("- Observed: 30.703 net DUP/s.", ev)                             # GBP-HW-325
        self.assertIn("32 028.483", ev)
        h = open(os.path.join(ROOT, "src", "audio", "gbp_aplay.h"), encoding="utf-8").read()
        # AMENDED 2026-09-25 (GitHub Issue #121), on top: "today's units" are #118's, and #121 moved the default
        # cushion to 0.125 s (512); TARGET's 2048 is read from the header #118 was written against (b1a72a4),
        # through guards.show (a moved path fails, an absent commit skips), AFTER the checks HEAD still answers. The
        # original line was:
        #   for tok in ("#define GBP_APLAY_RING          4096u", "#define GBP_APLAY_TARGET        2048u", ...
        for tok in ("#define GBP_APLAY_RING          4096u",
                    "#define GBP_APLAY_PUSHES         128u"):
            self.assertIn(tok, h)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import guards
        self.assertIn("#define GBP_APLAY_TARGET        2048u", guards.show("b1a72a4", "src/audio/gbp_aplay.h"))


if __name__ == "__main__":
    unittest.main()
