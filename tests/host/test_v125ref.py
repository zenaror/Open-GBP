"""tests/host/test_v125ref.py -- GitHub Issue #125, step 3: tools/v125ref.py, the reference implementations' audio
parameters recomputed from the private binaries.

What is proved here, on constructions only:
  * the responses are the stated arithmetic: a FIR's DC-normalised gain on known kernels, the 8-cycle byte boxcar's
    null at the byte rate, a biquad reduced to a known FIR, the phase-averaged resampler on identity phases, the
    -3 dB search on a first-order curve (and its refusal when -3 dB is not bracketed), and the peak search on
    unrounded values (a resonance, and a curve whose maximum is at DC);
  * the first-rising-edge table is constructed from first principles for all 256 bytes;
  * a 16.16 step becomes the output rate it implies from a 32 768 Hz input, and its offset from 32 000 and from the
    AI rate RUN 38 measured;
  * a byte LUT's per-bit weights, centre and departure from linearity;
  * the centred-popcount tables are built from first principles, never read from a binary;
  * the SDA base and the addresses the code builds are reconstructed from hand-assembled words: directly off the lis
    register, or in two steps through an addi whose destination the second load must read, each step within its own
    lookahead, never through rA = 0 at either step, and one site listed once;
  * a known blob is found by its sha256 alone, only at aligned offsets.
On the private inputs (skipped where they are absent), the figures #125's records quote from the references' TABLES and
SDA constants: they are this tool's output, so a change to the tool or to the record that separates them fails here or
in test_v125_records.py. The code-read figures (rings, delays, buffers) are not the tool's and are not checked here.
"""
import math
import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v125const  # noqa: E402
import v125ref  # noqa: E402
from test_v125const import addi, lis, ori, NOP  # noqa: E402
import gbi_unpack  # noqa: E402

BASE = 0x80003100


def lfs(fr, d, ra):
    return (48 << 26) | (fr << 21) | (ra << 16) | (d & 0xFFFF)


def lbz(rd, d, ra):
    return (34 << 26) | (rd << 21) | (ra << 16) | (d & 0xFFFF)


def hits(ws, t):
    return v125ref.built_addresses([(BASE, struct.pack(">%dI" % len(ws), *ws), True)], [t])[t]


class TheResponses(unittest.TestCase):
    def test_fir_gain_on_known_kernels(self):
        self.assertAlmostEqual(v125ref.fir_response([1, 1], 0.0, 8.0), 1.0)
        self.assertAlmostEqual(v125ref.fir_response([1, 1], 4.0, 8.0), 0.0)          # a null at Nyquist
        self.assertAlmostEqual(v125ref.fir_response([1, 2, 1], 2.0, 8.0), 0.5)       # |1 - 2j - 1| / 4

    def test_the_byte_boxcar_nulls_at_the_byte_rate(self):
        self.assertEqual(v125ref.boxcar8(0), 1.0)
        self.assertAlmostEqual(v125ref.boxcar8(v125ref.BYTE_HZ), 0.0)
        self.assertEqual(v125ref.BYTE_HZ * 8, 2 ** 24)

    def test_a_biquad_with_no_poles_is_its_fir(self):
        h = lambda f: v125ref.biquad_response(0.25, 0.5, 0.25, 0.0, 0.0, f, fs=8.0)
        self.assertAlmostEqual(h(0.0), 1.0)
        self.assertAlmostEqual(h(2.0), 0.5)
        self.assertAlmostEqual(h(4.0), 0.0)

    def test_identity_phases_pass_everything(self):
        taps = [0, 32768, 0, 0] * 128
        for f in (0.0, 5256.0, 16000.0):
            self.assertAlmostEqual(v125ref.resampler_response(taps, f), 1.0)

    def test_minus3db_on_a_first_order_curve(self):
        h = lambda f: 1.0 / math.sqrt(1.0 + (f / 1000.0) ** 2)
        self.assertAlmostEqual(v125ref.minus3db(h, 10.0, 50000.0), 1000.0, delta=0.01)
        with self.assertRaises(ValueError):
            v125ref.minus3db(h, 2000.0, 50000.0)                     # h(lo) is already below -3 dB
        with self.assertRaises(ValueError):
            v125ref.minus3db(h, 10.0, 500.0)                         # h(hi) is still above it

    def test_the_peak_is_found_on_unrounded_values(self):
        # a resonance whose top is flat to 4 decimals over tens of Hz: a rounded max would drift to the plateau's edge
        h = lambda f: 1.5 - 1e-9 * (f - 9081.4) ** 2
        v, f = v125ref.peak(h)
        self.assertAlmostEqual(f, 9081.4, delta=0.02)
        self.assertAlmostEqual(v, 1.5, places=9)
        v, f = v125ref.peak(lambda f: 1.0 / (1.0 + f))            # the maximum is at DC
        self.assertEqual((round(v, 6), round(f)), (1.0, 0))


class TheSteps(unittest.TestCase):
    def test_a_step_is_an_output_rate(self):
        (one,) = v125ref.step_rates([0x10000])
        self.assertEqual(one["ratio"], 1.0)
        self.assertEqual(one["outputs_per_s"], 32768.0)
        self.assertEqual(one["vs_32000_pct"], 2.4)
        (nom,) = v125ref.step_rates([round(65536 * 32768 / 32000)])
        self.assertAlmostEqual(nom["outputs_per_s"], 32000.0, delta=0.5)
        self.assertEqual(v125ref.AI_MEASURED, 32028.483)                              # GBP-HW-325


class TheTables(unittest.TestCase):
    def test_lut_linearity(self):
        lut = [(bin(b).count("1") - 4) * 7000.0 for b in range(256)]
        w, centre, dev = v125ref.lut_linearity(lut)
        self.assertEqual((set(w), centre, dev), ({7000.0}, -28000.0, 0.0))
        lut[0xFF] += 1.0
        self.assertEqual(v125ref.lut_linearity(lut)[2], 1.0)

    def test_the_first_rising_edge_table(self):
        t = v125ref.first_rising_edge_table()
        want = {0x7F: 1, 0x3F: 2, 0x0F: 4, 0x01: 7, 0x55: 1, 0x05: 5, 0x00: 0, 0xFF: 0, 0x80: 0, 0xF0: 0, 0xFE: 0}
        for b, p in want.items():
            self.assertEqual(t[b], p, hex(b))
        self.assertEqual(len(t), 256)

    def test_the_centred_tables_are_constructed(self):
        s16 = v125ref.centred_popcount_s16()
        f32 = v125ref.centred_popcount_f32()
        self.assertEqual((len(s16), len(f32)), (512, 1024))
        self.assertEqual(struct.unpack(">h", s16[0:2])[0], -4)
        self.assertEqual(struct.unpack(">h", s16[2 * 0xFF:2 * 0xFF + 2])[0], 4)
        self.assertEqual(struct.unpack(">f", f32[4 * 0x0F:4 * 0x0F + 4])[0], 0.0)
        self.assertEqual(struct.unpack(">f", f32[4 * 0xFF:4 * 0xFF + 4])[0], 32768.0)


class TheAddresses(unittest.TestCase):
    def test_the_sda_base_in_both_forms(self):
        regions = [(BASE, struct.pack(">3I", NOP, lis(13, 0x8027), ori(13, 13, 0x90A0)), True)]
        self.assertEqual(v125ref.sda_base(regions, 13), 0x802790A0)
        regions = [(BASE, struct.pack(">2I", lis(2, 0x8028), addi(2, 2, -0x5E60)), True)]
        self.assertEqual(v125ref.sda_base(regions, 2), 0x8027A1A0)
        self.assertIsNone(v125ref.sda_base(regions, 13))

    def test_built_addresses_through_a_load(self):
        regions = [(BASE, struct.pack(">4I", lis(3, 0x8009), lfs(1, 0x5FB0, 3), lis(4, 0x800A), lfs(2, -0x5FB0, 5)),
                    True)]
        hits = v125ref.built_addresses(regions, [0x80095FB0, 0x8009A050])
        self.assertEqual(hits[0x80095FB0], [BASE])
        self.assertEqual(hits[0x8009A050], [])                    # what r4 would build: the load reads r5, not r4

    def test_built_addresses_only_within_the_lookahead(self):
        for nops, want in ((7, [BASE]), (8, [])):
            ws = [lis(3, 0x8009)] + [NOP] * nops + [lfs(1, 0x5FB0, 3)]
            regions = [(BASE, struct.pack(">%dI" % len(ws), *ws), True)]
            self.assertEqual(v125ref.built_addresses(regions, [0x80095FB0])[0x80095FB0], want, nops)

    def test_built_addresses_in_two_steps_and_never_through_r0(self):
        # a structure's field: lis r3,0x800B ; addi r4,r3,0x0A10 ; lbz r5,0xC9(r4) reaches 0x800B0AD9
        regions = [(BASE, struct.pack(">3I", lis(3, 0x800B), addi(4, 3, 0x0A10), lbz(5, 0xC9, 4)), True)]
        hits = v125ref.built_addresses(regions, [0x800B0AD9, 0x800B0A10])
        self.assertEqual((hits[0x800B0AD9], hits[0x800B0A10]), ([BASE], [BASE]))
        regions = [(BASE, struct.pack(">3I", lis(0, 0x800B), addi(4, 0, 0x0A10), lbz(5, 0xC9, 4)), True)]
        self.assertEqual(v125ref.built_addresses(regions, [0x800B0AD9])[0x800B0AD9], [])

    def test_the_second_step_guards(self):
        self.assertEqual(hits([lis(3, 0x800B), addi(0, 3, 0x0A10), lbz(5, 0xC9, 0)], 0x800B0AD9), [])   # addi into r0
        self.assertEqual(hits([lis(3, 0x800B), addi(4, 3, 0x0A10), lbz(5, 0xC9, 6)], 0x800B0AD9), [])   # wrong base
        self.assertEqual(hits([lis(3, 0x800B), addi(4, 3, 0x0A10), lbz(5, 0, 4)], 0x800B0A10), [BASE])  # once
        for nops, want in ((7, [BASE]), (8, [])):                    # the second window counts from the addi
            ws = [lis(3, 0x800B), addi(4, 3, 0x0A10)] + [NOP] * nops + [lbz(5, 0xC9, 4)]
            self.assertEqual(hits(ws, 0x800B0AD9), want, nops)

    def test_a_redefined_register_stops_further_credit(self):
        # addi r3,r3,0x0A10 redefines r3 itself: 0x800B0A10 is credited once, but r3 no longer holds hi afterwards,
        # so the following lbz off r3 must NOT be read as hi + 0xC9 (#125's review)
        ws = [lis(3, 0x800B), addi(3, 3, 0x0A10), lbz(5, 0xC9, 3)]
        self.assertEqual(hits(ws, 0x800B0AD9), [BASE])
        self.assertEqual(hits(ws, 0x800B00C9), [])

    def test_a_blob_is_found_by_its_hash_at_aligned_offsets(self):
        import hashlib
        blob = bytes(range(64))
        img = bytes(32) + blob + bytes(16) + b"\0" + blob
        sha = hashlib.sha256(blob).hexdigest()
        self.assertEqual(v125ref.find_by_hash(img, sha, 64), [v125ref.GBI_LOAD + 32])     # the second copy is unaligned


class ThePrivateInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = [os.path.join(ROOT, "input", "gbi", "apps", e, e + ".dol") for e in v125const.EDITIONS]
        if not (all(os.path.isfile(p) for p in paths) and os.path.isfile(v125const.DISC_DOL)):
            raise unittest.SkipTest("the private reference inputs are not present on this host")
        cls.r = v125ref.analyse()

    def test_the_disc_decode(self):
        d = self.r["disc"]
        self.assertTrue(d["lut"]["is_centred_popcount_times_7000"])
        self.assertEqual((d["window"]["taps"], d["window"]["symmetric"], d["window"]["peak_index"]), (256, True, 127))
        self.assertAlmostEqual(d["window"]["sum"], 1.0, places=8)
        self.assertEqual(d["decimator"]["minus3db_hz"], 8660)
        self.assertEqual(d["chain"]["minus3db_hz"], 6483)
        self.assertEqual((d["resampler"]["row_sum_min"], d["resampler"]["row_sum_max"]), (32753, 32784))
        self.assertEqual(d["classes_bytes"], [32, 16, 8, -1])
        self.assertTrue(d["gain"]["monotone"])
        self.assertLess(d["gain"]["square_law_127_max_dev"], 1e-5)
        self.assertTrue(d["edgepos"]["is_first_rising_edge_table"])
        self.assertTrue(d["masks_are_ff_shifted"])
        self.assertEqual(d["constants"], {"zero": 0.0, "clip_hi": 32767.0, "clip_lo": -32768.0, "norm": 32768.0,
                                          "mono": 0.5})
        self.assertEqual([s["ratio"] for s in d["steps"]], [1.019989, 1.023987, 1.025986])
        self.assertEqual([s["vs_measured_pct"] for s in d["steps"]], [0.304, -0.088, -0.282])

    def test_the_gbi_editions(self):
        built = {"gbi": ("0x80096F9C", "0x80095FB0"), "gbihf": ("0x80085CDC", "0x80085EDC"),
                 "gbisr": ("0x800962E0", "0x80095EE0")}
        for e, (it, ft) in built.items():
            g = self.r["gbi"][e]
            self.assertEqual((g["int_table_at"], g["float_table_at"]), ([it], [ft]), e)
            self.assertEqual(sorted(g["built_by_code"].values()), [1, 1, 1, 2], e)       # load 0x80003100 holds
            self.assertTrue(g["default_coefs_are_analog"] and g["presets_equal_gbi"], e)
            self.assertEqual(g["aesnd_default_rate_doubles"], 1, e)
            self.assertEqual((g["analog_minus3db_hz"], g["original_minus3db_hz"]), (14828, 8192), e)
            self.assertEqual(g["analog_peak"], (1.5118, 9081), e)
            self.assertEqual(g["original_peak"], (1.0001, 0), e)
        flags = dict((e, (self.r["gbi"][e]["filter_flag_initial"], self.r["gbi"][e]["filter_flag_built_at"]))
                     for e in built)
        # GBIHF defaults to digital; each flag is built by the lis 8 bytes into its edition's hand-off
        self.assertEqual(flags, {"gbi": (1, ["0x8000B764"]), "gbihf": (0, ["0x8000ADE0"]), "gbisr": (1, ["0x8000C0FC"])})
        mixer = dict((e, self.r["gbi"][e]["aesnd_mixer_at"]) for e in built)
        self.assertEqual(mixer, {"gbi": ["0x800B0FC0"], "gbihf": ["0x800999A0"], "gbisr": ["0x800AAC20"]})

    def test_the_analog_peak_by_an_independent_dense_scan(self):
        # the preset read here, not through the tool's record; a 0.1 Hz scan around the tool's answer
        img = gbi_unpack.unpack(open(os.path.join(ROOT, "input", "gbi", "apps", "gbi", "gbi.dol"), "rb").read())[0]
        a = v125ref.GBI_PRESETS["gbi"][0] - v125ref.GBI_LOAD
        b0, b1, a1, a2 = struct.unpack(">4f", img[a:a + 16])
        h = lambda f: v125ref.biquad_response(b0, b1, b0, a1, a2, f)
        best = max((h(8900.0 + k / 10.0), 8900.0 + k / 10.0) for k in range(4001))
        self.assertLessEqual(abs(best[1] - self.r["gbi"]["gbi"]["analog_peak"][1]), 1.0)


if __name__ == "__main__":
    unittest.main()
