"""
tests/host/test_icoord.py — the OGBPCOORD1 model (tools/icoord.py): the
contract §V6.6 promised, checked as mathematics before any ROM ran.
"""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import icoord  # noqa: E402
import istim  # noqa: E402


class TheField(unittest.TestCase):
    def test_injective_full_domain_and_bit_15_clear(self):
        vals = [icoord.field(x, y) for y in range(160) for x in icoord.FIELD]
        self.assertEqual(len(vals), 29280)
        self.assertEqual(len(set(vals)), 29280)
        self.assertEqual((min(vals), max(vals)), (0, 29279))
        self.assertTrue(all(v < 0x8000 for v in vals))
        for v in (0, 1, 182, 183, 29279):
            self.assertEqual(icoord.field(*icoord.field_inverse(v)), v)

    def test_every_pixel_has_an_expected_value_and_bit_15_is_never_set(self):
        for fid in (0, 479, 480, 519, 520, 1920):
            fr = icoord.render_agb(fid)
            self.assertEqual((len(fr), len(fr[0])), (160, 240))
            self.assertTrue(all(w < 0x8000 for row in fr for w in row))

    def test_shifts_swaps_and_permutations_change_a_pixel(self):
        f = icoord.field
        X0, X1, W = icoord.FIELD_X0, icoord.FIELD_X1, icoord.FIELD_W
        for k in range(1, 160):
            self.assertTrue(any(f(x, 0) != f(x, k % 160) for x in range(X0, X1 + 1)), k)
        for k in range(1, W):
            self.assertTrue(any(f(x, 5) != f(X0 + ((x - X0 + k) % W), 5) for x in range(X0, X1 + 1)), k)
        self.assertTrue(any(f(X0 + i, j) != f(X0 + j, i) for i in range(160) for j in range(160) if i != j))
        tiles = set()
        for ty in range(40):
            for tx in range(W // 4):
                key = tuple(f(X0 + 4 * tx + i, 4 * ty + j) for j in range(4) for i in range(4))
                self.assertNotIn(key, tiles)
                tiles.add(key)


class TheWitnessIsOgbpidx1(unittest.TestCase):
    def test_flag_strip_l_and_guard_a_are_byte_identical_to_the_frozen_model(self):
        for fid in (0, 1, 73, 480, 0x123456, 0xFFFFFF):
            for st in (0x7F, 0x00, 0x80, 0x18):
                for y in range(160):
                    for x in range(0, 56):
                        self.assertEqual(icoord.expected_agb(fid, x, y, st), istim.expected_agb(fid, x, y, st), (fid, st, x, y))
                for b in range(40):
                    self.assertEqual(icoord.witness_words(fid, b, st), istim.witness_words(fid, b, st))

    def test_the_canonical_decoder_reads_the_coord_witness(self):
        for fid in (0, 480, 2120):
            for b in range(40):
                d = istim.decode_canonical(icoord.witness_words(fid, b, 0x18), b)
                self.assertEqual(d["outcome"], istim.CANONICAL_OK)
                self.assertEqual((d["frame_id"], d["index_ok"], d["status"]), (fid, True, 0x18))

    def test_guard_c_and_no_strip_r_no_bar(self):
        for fid in (0, 480):
            for y in (0, 77, 159):
                self.assertEqual(icoord.expected_agb(fid, 239, y), 0)
                self.assertEqual(icoord.expected_agb(fid, 185, y), icoord.field(185, y))
                self.assertEqual(icoord.expected_agb(fid, 238, y), icoord.field(238, y))


class TheGlyphSchedule(unittest.TestCase):
    def test_period_width_and_ordinal(self):
        self.assertEqual((icoord.GLYPH_P, icoord.GLYPH_W), (480, 40))
        self.assertFalse(any(icoord.glyph_shown(f) for f in range(0, 480)))
        for k in range(1, 6):
            self.assertEqual(list(icoord.appearance_range(k)), list(range(k * 480, k * 480 + 40)))
            self.assertTrue(all(icoord.glyph_shown(f) for f in icoord.appearance_range(k)))
            self.assertFalse(icoord.glyph_shown(k * 480 + 40))
            self.assertFalse(icoord.glyph_shown(k * 480 - 1))

    def test_geometry_and_digit(self):
        fid = 3 * 480 + 5                      # digit 3, counter 5 = 000101
        fr = icoord.render_agb(fid)
        # the glyph box and the squares box are the only places the field is not shown
        for y in range(160):
            for x in icoord.FIELD:
                in_digit = 123 <= x < 171 and 40 <= y < 120
                in_sq = 123 <= x < 171 and 128 <= y < 136
                if not (in_digit or in_sq):
                    self.assertEqual(fr[y][x], icoord.field(x, y), (x, y))
        # digit 3 = a b c d g: top row lit across, left column dark except nothing (f, e off)
        self.assertEqual(fr[40][140], 0x7FFF)          # a
        self.assertEqual(fr[80][140], 0x7FFF)          # g (rows 76..83)
        self.assertEqual(fr[119][140], 0x7FFF)         # d
        self.assertEqual(fr[60][170], 0x7FFF)          # b
        self.assertEqual(fr[100][170], 0x7FFF)         # c
        self.assertEqual(fr[60][123], icoord.field(123, 60))    # f off
        self.assertEqual(fr[100][123], icoord.field(123, 100))  # e off
        # squares: 000101 -> squares 3 and 5 lit (MSB left)
        lit = [fr[131][123 + 8 * i + 3] == 0x7FFF for i in range(6)]
        self.assertEqual(lit, [False, False, False, True, False, True])

    def test_every_digit_is_distinct_and_the_counter_covers_all_forty_frames(self):
        pics = set()
        for k in range(1, 11):
            fid = k * 480
            pics.add(tuple(icoord.expected_agb(fid, x, y) for y in range(40, 120) for x in range(123, 171)))
        self.assertEqual(len(pics), 10)
        counters = set()
        for f in icoord.appearance_range(2):
            counters.add(tuple(icoord.expected_agb(f, 123 + 8 * i + 3, 131) for i in range(6)))
        self.assertEqual(len(counters), 40)


class TheTiledOracle(unittest.TestCase):
    def test_tile_index_is_a_bijection_and_the_oracle_is_opaque(self):
        idx = sorted(icoord.tile_index(x, y) for y in range(160) for x in range(240))
        self.assertEqual(idx, list(range(38400)))
        t = icoord.tiled_oracle(480)
        self.assertEqual(len(t), 38400)
        self.assertTrue(all(v & 0x8000 for v in t))
        self.assertEqual(t[icoord.tile_index(0, 0)], (icoord.expected_video(480, 0, 0) | 0x8000))

    def test_the_raw_block_carries_the_swapped_word_in_bytes_1_and_3(self):
        raw = icoord.render_block_raw(480, 7, filler=0x5A)
        self.assertEqual(len(raw), 0xF00)
        for row in range(4):
            for x in (0, 1, 56, 123, 238, 239):
                o = row * 960 + x * 4
                w = (raw[o + 1] << 8) | raw[o + 3]
                self.assertEqual(w, icoord.expected_video(480, x, 28 + row))
                self.assertEqual((raw[o], raw[o + 2]), (0x5A, 0x5A))


if __name__ == "__main__":
    unittest.main()
