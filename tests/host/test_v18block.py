"""tests/host/test_v18block.py — §V18: what one 4096-byte AUDIO block contains (Issue #82).

Synthetic blocks first, so the classifier is shown to do what it says before it
is pointed at the archive; then every figure §V18 quotes is recomputed from the
VERSIONED fixtures (captures/fixtures/, Issue #81), so none of them depends on a
local file; then the drain figures quoted from the run logs, where the logs are.
"""
import gzip
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import awinparse  # noqa: E402
import v18block as v  # noqa: E402

FIX = os.path.join(ROOT, "captures", "fixtures")
RUNS = {"RUN33": "hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz",
        "RUN34": "hw-gamecube-gbp-2026-09-23-stream-0016-run34-audio.bin.gz"}
LOGS = {"RUN33": os.path.join(ROOT, "logs", "run33", "GBP-AUDIO-001_stream-0016.log"),
        "RUN34": os.path.join(ROOT, "logs", "run34", "GBP-AUDIO-001_stream-0016.log")}


def slice_block(counts_like):
    """A synthetic block whose slice i holds `counts_like[i]` one-bits (leading ones)."""
    out = bytearray()
    for c in counts_like:
        s = bytearray(v.SLICE)
        for bit in range(c):
            s[bit // 8] |= 0x80 >> (bit % 8)
        out += s
    return bytes(out)


class TheClassifierOnSyntheticBlocks(unittest.TestCase):

    def test_slice_counts_and_identity(self):
        b = slice_block([785] * 16)
        self.assertEqual(v.slice_counts(b), [785] * 16)
        self.assertTrue(v.byte_identical(b))
        self.assertFalse(v.byte_identical(slice_block([785] * 15 + [786])))

    def test_flat_step_and_other(self):
        self.assertEqual(v.shape([1025] * 15 + [1028])["kind"], "flat")
        s = v.shape([785] * 8 + [1266] * 8)
        self.assertEqual((s["kind"], s["k"], s["before"], s["after"]), ("step", 8, 785.0, 1266.0))
        s = v.shape([1266] * 14 + [785, 786])
        self.assertEqual((s["kind"], s["k"]), ("step", 14))
        # two transitions in one block is neither flat nor one step
        self.assertEqual(v.shape([785] * 5 + [1266] * 5 + [785] * 6)["kind"], "other")
        self.assertEqual(v.shape([1025] * 15 + [1029])["kind"], "step")   # a 4-bit jump at the end IS a step

    def test_sample_is_81s_exact_arithmetic_including_a_half(self):
        # +4096 one-bits over a silent rest is 0.125 of the block -> 80 % of full scale
        self.assertEqual(v.sample(16384 + 4096, 16384 * 256, 256), 26214)
        self.assertEqual(v.sample(16384, 16384 * 256, 256), 0)
        self.assertEqual(v.sample(32768, 0, 1), 32767)          # clipped
        # an EXACT half (7021.5) goes to the even neighbour; a float computation reads
        # 7021.4999... here and would give 7021. None occurs in the archive (#81).
        self.assertEqual(v.sample(17228, 112916, 7), 7022)


class Archive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="v18block-")
        cls.r, cls.counts = {}, {}
        for lab, name in RUNS.items():
            with open(os.path.join(FIX, name), "rb") as f:
                raw = gzip.decompress(f.read())
            p = os.path.join(cls.tmp, lab + ".bin")
            with open(p, "wb") as f:
                f.write(raw)
            cls.r[lab] = v.analyse(p)
            _, _, _, wins = awinparse.load(p)
            cls.counts[lab] = [[v.slice_counts(b) for b in w] for w in wins]


class WhatTheBlocksAre(Archive):

    def test_byte_identity_is_798_and_180_and_not_802(self):
        self.assertEqual([w["identical"] for w in self.r["RUN33"]["windows"]], [235, 174, 143, 164, 82])
        self.assertEqual([w["identical"] for w in self.r["RUN34"]["windows"]], [65, 45, 19, 19, 32])
        self.assertEqual(sum(w["identical"] for w in self.r["RUN33"]["windows"]), 798)
        self.assertEqual(sum(w["identical"] for w in self.r["RUN34"]["windows"]), 180)

    def test_identical_bytes_iff_identical_counts(self):
        """Slices that differ in bytes always differ in count too: identity IS spread 0."""
        for lab in RUNS:
            for w in self.r[lab]["windows"]:
                self.assertEqual(w["identical"], w["spreads"][0], (lab, w["index"]))

    def test_every_block_is_flat_or_one_step(self):
        spreads = [0, 0, 0, 0]
        for lab in RUNS:
            for w in self.r[lab]["windows"]:
                self.assertEqual(w["other"], 0, (lab, w["index"]))
                self.assertEqual(w["flat"] + w["step"], 256)
                spreads = [a + b for a, b in zip(spreads, w["spreads"])]
        self.assertEqual(spreads, [978, 1039, 232, 7])

    def test_the_split_does_not_depend_on_the_threshold(self):
        allc = [c for lab in RUNS for w in self.counts[lab] for c in w]
        base = [v.shape(c)["kind"] for c in allc]
        same = [t for t in range(0, 130) if [v.shape(c, t)["kind"] for c in allc] == base]
        self.assertEqual((same[0], same[-1], len(same)), (3, 61, 59))
        region = [c for lab in RUNS for i, w in enumerate(self.counts[lab]) for c in (w if i == 0 else w[96:])]
        base = [v.shape(c)["kind"] for c in region]
        same = [t for t in range(0, 200) if [v.shape(c, t)["kind"] for c in region] == base]
        self.assertEqual((same[0], same[-1], len(same)), (3, 97, 95))

    def test_the_control_windows_never_step(self):
        for lab in RUNS:
            w = self.r[lab]["windows"][0]
            self.assertEqual((w["kind"], w["step"], w["flat"]), (0, 0, 256))


class TheFiguresTheVerifiersCorrected(Archive):
    """§V18 quotes these; each was either found or corrected by the independent verifiers
    and re-derived before it was written down."""

    def raw(self, lab):
        with open(os.path.join(FIX, RUNS[lab]), "rb") as f:
            return gzip.decompress(f.read())

    def test_the_orchestrators_802_is_an_8_byte_late_read_of_run_33(self):
        for lab, want in (("RUN33", (798, 802)), ("RUN34", (180, 176))):
            raw = self.raw(lab)
            _h, _a, off = awinparse.parse(raw)
            self.assertEqual(off, 0x380)
            got = tuple(sum(1 for i in range(1280) if v.byte_identical(raw[off + s + i * 4096:off + s + (i + 1) * 4096]))
                        for s in (0, 8))
            self.assertEqual(got, want, lab)

    def test_every_transition_in_the_archive_is_on_an_even_slice(self):
        ks = [v.shape(c)["k"] for lab in RUNS for w in self.counts[lab] for c in w if v.shape(c)["kind"] == "step"]
        self.assertEqual(len(ks), 304)
        self.assertEqual(sorted(set(ks)), [4, 6, 8, 10, 12, 14])

    def test_a_count_does_not_fix_a_slices_bytes(self):
        pairs, blocks = 0, 0
        for lab in RUNS:
            with tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, "x.bin")
                with open(p, "wb") as f:
                    f.write(self.raw(lab))
                _, _, _, wins = awinparse.load(p)
            for w in wins:
                for b in w:
                    sl = [b[i * 256:(i + 1) * 256] for i in range(16)]
                    c = v.slice_counts(b)
                    n = sum(1 for i in range(16) for j in range(i + 1, 16) if sl[i] != sl[j] and c[i] == c[j])
                    pairs += n
                    blocks += 1 if n else 0
        self.assertEqual((pairs, blocks), (3059, 619))

    def test_the_plateaus_match_their_neighbours_within_one_and_a_quarter_bits(self):
        worst = 0.0
        for lab in RUNS:
            for w in self.counts[lab][1:]:
                sh = [v.shape(c) for c in w]
                for i in range(96, len(sh)):
                    if sh[i]["kind"] == "step":
                        worst = max(worst, abs(sh[i - 1]["level"] - sh[i]["before"]))
                        if i + 1 < len(sh):
                            worst = max(worst, abs(sh[i + 1]["level"] - sh[i]["after"]))
        self.assertEqual(worst, 1.25)

    def test_below_three_bits_exactly_one_block_is_other(self):
        other = [(lab, wi, bi) for lab in RUNS for wi, w in enumerate(self.counts[lab])
                 for bi, c in enumerate(w) if v.shape(c, 2)["kind"] == "other"]
        self.assertEqual(other, [("RUN34", 4, 114)])

    def test_one_slice_before_the_onset_slice(self):
        for lab, want in (("RUN33", 192), ("RUN34", 199)):
            w0 = self.counts[lab][0]
            rs = sum(sum(c) for c in w0)
            worst = max(abs(v.sample(16 * x, rs, 256) - v.sample(sum(c), rs, 256))
                        for w in self.counts[lab][1:] for c in w[:96] if v.shape(c)["kind"] == "flat" for x in c)
            self.assertEqual(worst, want, lab)


class TheStepsAreTheEdges(Archive):

    EXPECT = {"RUN33": [(32, 10, [8]), (8, 40, [12]), (16, 20, [10]), (4, 80, [14])],
              "RUN34": [(32, 10, [14]), (32, 10, [10]), (32, 10, [6]), (32, 10, [14])]}

    def test_one_edge_every_half_period_at_one_slice_index(self):
        for lab, rows in self.EXPECT.items():
            for w, (period, n, ks) in zip(self.r[lab]["windows"][1:], rows):
                e = w["edges"]
                self.assertEqual(w["period"], period, (lab, w["index"]))
                self.assertTrue(e["ok_spacing"], (lab, w["index"], e["gaps"]))
                self.assertEqual(e["gaps"], [period // 2])
                self.assertEqual(e["n_steps"], n)
                self.assertEqual(e["expected_n"], (n, n))
                self.assertEqual(e["ks"], ks)
                self.assertEqual(e["other"], 0)

    def test_the_plateaus_are_the_neighbouring_blocks_so_slice_order_is_time_order(self):
        for lab in RUNS:
            for w in self.r[lab]["windows"][1:]:
                self.assertTrue(w["edges"]["neighbours_ok"], (lab, w["index"]))

    def test_the_block_sample_is_the_sum_of_the_slices_so_the_1024_hz_levels_follow(self):
        """§V17.6.1's four levels at 1024 Hz: the straddle blocks are steps at k = 14, and
        (14 x 785 + 2 x 1266) / 16 and (14 x 1266 + 2 x 785) / 16 are 845 and 1206."""
        self.assertEqual(round((14 * 785 + 2 * 1266) / 16.0), 845)
        self.assertEqual(round((14 * 1266 + 2 * 785) / 16.0), 1206)
        w4 = self.counts["RUN33"][4][96:]
        levels = sorted({round(sum(c) / 16.0) for c in w4})
        self.assertEqual(levels, [785, 845, 1206, 1266])


class OneSliceIsNotTheBlock(Archive):

    def test_flat_blocks_differ_by_the_spread_only(self):
        worst = {lab: max(x["flat"] for w in self.r[lab]["windows"][1:] for x in w["one_slice"]) for lab in RUNS}
        self.assertEqual(worst, {"RUN33": 96, "RUN34": 250})

    def test_at_every_edge_one_slice_misses_and_by_how_much(self):
        per = {lab: [max(x["step"] for x in w["one_slice"]) for w in self.r[lab]["windows"][1:]] for lab in RUNS}
        self.assertEqual(per["RUN33"], [24723, 36946, 30880, 43109])
        self.assertEqual(per["RUN34"], [43020, 22732, 14560, 8864])
        # and NO slice index j reproduces the block at every edge
        for lab in RUNS:
            for w in self.r[lab]["windows"][1:]:
                self.assertTrue(all(x["step"] > 0 for x in w["one_slice"]), (lab, w["index"]))


class TheDrainFiguresFromTheRunLogs(unittest.TestCase):
    """Quoted in §V18 from the raw logs, which live under logs/ and are never versioned."""

    def read(self, lab):
        if not all(os.path.exists(p) for p in LOGS.values()):
            self.skipTest("the RUN 33 / RUN 34 logs are not in this checkout (logs/ is ignored)")
        with open(LOGS[lab], encoding="utf-8", errors="replace") as f:
            return f.read()

    def test_every_audio_block_was_read_in_full_and_none_failed(self):
        for lab, (n, s) in {"RUN33": (114342, "27.932"), "RUN34": (157803, "38.542")}.items():
            t = self.read(lab)
            self.assertIn("AUDIOAGG selected=%d attempted=%d completed=%d failures=0 bytes=%d"
                          % (n, n, n, n * 4096), t)
            self.assertRegex(t, r"CLOCKSEC capture_s=%s baseline_s=0\.077 " % re.escape(s))

    def test_the_logged_dma_reads_are_whole_blocks_and_about_65_us(self):
        dts = []
        for lab in RUNS:
            t = self.read(lab)
            rows = re.findall(r"AUDIOREAD idx=8 addr=(\w+) len=(\w+) .*? dt=(\d+) wait_ticks=(\d+) polls=(\d+)", t)
            self.assertEqual(len(rows), 4)
            self.assertEqual({(a, l) for a, l, _d, _w, _p in rows}, {("01800000", "1000")})
            dts += [int(d) for _a, _l, d, _w, _p in rows]
        dts.sort()
        self.assertEqual((dts[0], dts[-1]), (2585, 2781))
        self.assertAlmostEqual((dts[3] + dts[4]) / 2.0 / 40.5, 64.7, places=1)
