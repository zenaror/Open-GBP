"""Offline reference model for the indexed stimulus — tests, not the ROM.

Everything here is DESIGN VERIFICATION. Nothing in this file touches the
physical candidate, the runtime or the protocol.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import istim  # noqa: E402


class Geometry(unittest.TestCase):
    """§11: the column plan must tile 0..239 exactly once."""

    def test_the_columns_tile_the_width_with_no_gap_and_no_overlap(self):
        cover = []
        cover.append(istim.X_FLAG)
        cover += list(istim.STRIP_L)
        cover.append(istim.X_GUARD_A)
        cover += list(istim.CONTENT)
        cover.append(istim.X_GUARD_B)
        cover += list(istim.STRIP_R)
        cover.append(istim.X_GUARD_C)
        self.assertEqual(len(cover), istim.WIDTH, "columns must sum to 240")
        self.assertEqual(sorted(cover), list(range(istim.WIDTH)), "no gap, no overlap")

    def test_the_strips_are_exactly_the_payload_width(self):
        self.assertEqual(len(istim.STRIP_L), istim.STRIP_BITS)
        self.assertEqual(len(istim.STRIP_R), istim.STRIP_BITS)
        self.assertEqual(istim.STRIP_BITS, 8 + 24 + 6 + 8 + 8)
        self.assertEqual(istim.PAYLOAD_BITS, 24 + 6 + 8)

    def test_the_blocks_tile_the_height(self):
        rows = []
        for b in range(istim.BLOCKS):
            rows += list(range(b * istim.LINES_PER_BLOCK, (b + 1) * istim.LINES_PER_BLOCK))
        self.assertEqual(sorted(rows), list(range(istim.HEIGHT)))
        self.assertEqual(istim.BLOCKS * istim.LINES_PER_BLOCK, istim.HEIGHT)
        self.assertEqual(istim.LINES_PER_BLOCK * istim.WIDTH * 4, istim.BLOCK_BYTES)

    def test_the_pixel_function_is_total(self):
        for f in (0, 1, 0x7FFFFF, 0xFFFFFF):
            for y in (0, 1, 79, 158, 159):
                for x in (0, 1, 54, 55, 56, 183, 184, 185, 238, 239):
                    w = istim.expected_agb(f, x, y)
                    self.assertTrue(0 <= w <= 0x7FFF, "bit 15 is never written by the stimulus")

    def test_out_of_range_is_refused_rather_than_guessed(self):
        for x, y in ((-1, 0), (240, 0), (0, -1), (0, 160)):
            with self.assertRaises(ValueError):
                istim.expected_agb(0, x, y)


class ColourMapping(unittest.TestCase):
    """The instrumentation symbols are fixed points of the confirmed mapping, so
    the ID decode does not depend on U-GBP-011 being right."""

    def test_the_symbols_survive_the_outer_group_exchange_unchanged(self):
        for v in (istim.ZERO, istim.ONE, istim.FLAG, istim.GUARD):
            self.assertEqual(istim.swap_outer(v), v)

    def test_the_exchange_is_an_involution(self):
        for w in (0x0000, 0x001F, 0x03E0, 0x7C00, 0x7FFF, 0x1234, 0x5AD6):
            self.assertEqual(istim.swap_outer(istim.swap_outer(w)), w)

    def test_the_exchange_moves_the_outer_groups_and_not_the_middle(self):
        self.assertEqual(istim.swap_outer(0x001F), 0x7C00)
        self.assertEqual(istim.swap_outer(0x7C00), 0x001F)
        self.assertEqual(istim.swap_outer(0x03E0), 0x03E0)

    def test_the_bar_colour_is_distinct_from_every_palette_entry(self):
        self.assertNotIn(istim.BAR, istim.PAL16)
        self.assertNotIn(istim.BAR, (istim.ZERO, istim.ONE, istim.FLAG))
        for v in istim.PAL16:
            self.assertTrue(0 <= v <= 0x7FFF)


class Crc8(unittest.TestCase):
    """§5: the CRC is specified bit by bit, not inherited from a library."""

    # FROZEN for format version 1: the payload is FRAME_ID || BLOCK_INDEX || STATUS
    VECTORS = {
        (0x000000, 0, 0x7F): 0xB6, (0x000000, 39, 0x7F): 0x73,
        (0x000001, 0, 0x7F): 0xED, (0x000001, 39, 0x7F): 0x28,
        (0xFFFFFF, 0, 0x7F): 0xC7, (0xFFFFFF, 39, 0x7F): 0x02,
        (0x123456, 17, 0x42): 0xD3,
        (0x000000, 0, 0x00): 0xCC, (0x000000, 0, 0x80): 0x45,
        (0xFFFFFF, 39, 0xFF): 0x8B,
    }

    def test_the_known_answer_vectors(self):
        for (f, b, st), want in self.VECTORS.items():
            self.assertEqual(istim.crc8_payload(f, b, st), want,
                             "f=0x%06x b=%d st=0x%02x" % (f, b, st))

    def test_the_payload_is_thirty_eight_bits_msb_first(self):
        bits = istim.payload_bits(0xA5A5A5, 0b100101, 0xC3)
        self.assertEqual(len(bits), 38)
        self.assertEqual(bits[:24], [int(c) for c in format(0xA5A5A5, "024b")])
        self.assertEqual(bits[24:30], [1, 0, 0, 1, 0, 1])
        self.assertEqual(bits[30:], [int(c) for c in format(0xC3, "08b")])

    def test_a_single_bit_flip_in_the_payload_always_changes_the_crc(self):
        """A CRC-8 cannot miss a single-bit error in a 38-bit message."""
        for f, b, st in ((0, 0, 0x7F), (0x0F0F0F, 13, 0x00), (0xFFFFFF, 39, 0xFF)):
            base = istim.payload_bits(f, b, st)
            ref = istim.crc8_bits(base)
            for i in range(istim.PAYLOAD_BITS):
                m = list(base)
                m[i] ^= 1
                self.assertNotEqual(istim.crc8_bits(m), ref, "bit %d" % i)

    def test_the_fault_bit_is_protected_by_the_crc(self):
        """STATUS is inside the CRC because it gates the decisive claim."""
        for f, b in ((0, 0), (0x123456, 17)):
            clean = istim.crc8_payload(f, b, 0x7F)
            faulted = istim.crc8_payload(f, b, 0x7F | istim.STATUS_FAULT_MASK)
            self.assertNotEqual(clean, faulted)

    def test_the_status_range_is_checked(self):
        with self.assertRaises(ValueError):
            istim.payload_bits(0, 0, 256)

    def test_the_range_checks_refuse_impossible_inputs(self):
        with self.assertRaises(ValueError):
            istim.payload_bits(1 << 24, 0)
        with self.assertRaises(ValueError):
            istim.payload_bits(0, 40)


class RedundancyDecoder(unittest.TestCase):
    """§12: normalise inversion and reversal, then compare exactly."""

    @staticmethod
    def rows_for(f, b):
        return [[istim.swap_outer(istim.expected_agb(f, x, y))
                 for x in range(istim.WIDTH)]
                for y in range(b * 4, b * 4 + 4)]

    def test_an_intact_block_decodes_unanimously(self):
        for f, b in ((0, 0), (1, 39), (0x123456, 17), (0xFFFFFF, 7)):
            r = istim.decode_block(self.rows_for(f, b), b)
            self.assertEqual(r["outcome"], istim.VALID_UNANIMOUS, (f, b))
            self.assertEqual(r["frame_id"], f)
            self.assertEqual(r["block_index_field"], b)
            self.assertTrue(r["index_ok"])
            self.assertEqual(r["copies_valid"], 8)

    def test_bit15_anywhere_on_a_strip_cannot_change_the_decoded_id(self):
        """§7: the decoder reads colour15, so the device's flag is invisible here."""
        f, b = 0x00BEEF, 5
        rows = self.rows_for(f, b)
        for x in (1, 27, 54, 185, 220, 238):
            rows[0][x] |= 0x8000
        r = istim.decode_block(rows, b)
        self.assertEqual(r["outcome"], istim.VALID_UNANIMOUS)
        self.assertEqual(r["frame_id"], f)
        self.assertEqual(r["crc_failures"], 0)

    def test_a_corrupted_row_still_leaves_a_majority(self):
        f, b = 0x001234, 9
        rows = self.rows_for(f, b)
        for x in istim.STRIP_L:
            rows[1][x] = 0x1234           # not a symbol at all
        r = istim.decode_block(rows, b)
        self.assertEqual(r["frame_id"], f)
        self.assertIn(r["outcome"], (istim.VALID_MAJORITY, istim.VALID_UNANIMOUS))
        self.assertEqual(r["copies_valid"], 7)

    def test_a_block_carrying_another_frames_strips_reports_that_frame(self):
        b = 11
        rows = self.rows_for(0x000100, b)
        other = self.rows_for(0x000101, b)
        for row in range(4):
            for x in list(istim.STRIP_L) + list(istim.STRIP_R):
                rows[row][x] = other[row][x]
        r = istim.decode_block(rows, b)
        self.assertEqual(r["frame_id"], 0x000101, "the strip is the authority")

    def test_a_misplaced_block_is_detected_by_the_index_field(self):
        rows = self.rows_for(0x000042, 7)
        r = istim.decode_block(rows, 8)          # delivered as block 8
        self.assertEqual(r["block_index_field"], 7)
        self.assertFalse(r["index_ok"])

    def test_destroying_both_strips_yields_no_majority(self):
        rows = self.rows_for(0x000001, 3)
        for row in range(4):
            for x in list(istim.STRIP_L) + list(istim.STRIP_R):
                rows[row][x] = 0x0555
        r = istim.decode_block(rows, 3)
        self.assertIsNone(r["frame_id"])
        self.assertEqual(r["outcome"], istim.INVALID_NO_MAJORITY)


class CanonicalWitness(unittest.TestCase):
    """The DECISIVE evidence: one lossless strip copy per block."""

    def test_the_shape_and_cost_are_what_the_design_declares(self):
        self.assertIs(istim.WITNESS_STRIP, istim.STRIP_L)
        self.assertEqual(istim.WITNESS_LOCAL_ROW, 0)
        self.assertEqual(istim.WITNESS_WORDS_PER_BLOCK, 54)
        self.assertEqual(istim.WITNESS_BYTES_PER_BLOCK, 108)
        self.assertEqual(istim.WITNESS_BYTES_PER_FRAME, 4320)

    def test_the_witness_row_is_the_first_line_of_the_block_on_the_wire(self):
        """So a runtime copy is one stride at the head of the delivery."""
        for b in (0, 17, 39):
            y = b * istim.LINES_PER_BLOCK + istim.WITNESS_LOCAL_ROW
            self.assertEqual(y, b * 4)

    def test_an_intact_witness_decodes_to_the_whole_payload(self):
        for f, b, st in ((0, 0, 0x7F), (0x123456, 17, 0x42), (0xFFFFFF, 39, 0x00)):
            d = istim.decode_canonical(istim.witness_words(f, b, st), b)
            self.assertEqual(d["outcome"], istim.CANONICAL_OK)
            self.assertEqual(d["frame_id"], f)
            self.assertEqual(d["block_index_field"], b)
            self.assertTrue(d["index_ok"])
            self.assertEqual(d["status"], st)

    def test_the_fault_bit_round_trips(self):
        d = istim.decode_canonical(
            istim.witness_words(7, 3, 0x7F | istim.STATUS_FAULT_MASK), 3)
        self.assertTrue(d["fault"])
        self.assertEqual(d["vmargin"], 0x7F)
        d = istim.decode_canonical(istim.witness_words(7, 3, 0x05), 3)
        self.assertFalse(d["fault"])
        self.assertEqual(d["vmargin"], 5)

    def test_bit15_is_split_off_and_reported_never_consumed(self):
        w = istim.witness_words(0x00BEEF, 0, 0x11)
        w[0] |= 0x8000
        w[13] |= 0x8000
        d = istim.decode_canonical(w, 0)
        self.assertEqual(d["outcome"], istim.CANONICAL_OK)
        self.assertEqual(d["frame_id"], 0x00BEEF)
        self.assertEqual(d["flag15_indices"], [0, 13])

    def test_a_non_symbol_pixel_invalidates_the_witness(self):
        w = istim.witness_words(1, 1, 0x7F)
        w[20] = 0x1234
        d = istim.decode_canonical(w, 1)
        self.assertEqual(d["outcome"], istim.INVALID_CANONICAL_STRIP)
        self.assertEqual(d["reason"], "symbol")

    def test_a_broken_sync_invalidates_the_witness(self):
        w = istim.witness_words(1, 1, 0x7F)
        w[0] = istim.ONE if w[0] == istim.ZERO else istim.ZERO
        d = istim.decode_canonical(w, 1)
        self.assertEqual(d["outcome"], istim.INVALID_CANONICAL_STRIP)
        self.assertEqual(d["reason"], "sync")

    def test_a_single_flipped_payload_bit_is_caught_by_the_crc(self):
        for i in range(8, 8 + istim.PAYLOAD_BITS):
            w = istim.witness_words(0x0055AA, 12, 0x33)
            w[i] = istim.ONE if w[i] == istim.ZERO else istim.ZERO
            d = istim.decode_canonical(w, 12)
            self.assertEqual(d["outcome"], istim.INVALID_CANONICAL_STRIP, "bit %d" % i)
            self.assertEqual(d["reason"], "crc")


class FrameComposition(unittest.TestCase):
    """§7: three integrity questions, decided separately."""

    @staticmethod
    def frame(f, st=0x7F):
        return [istim.witness_words(f, b, st) for b in range(istim.BLOCKS)]

    def test_an_intact_frame(self):
        r = istim.classify_frame(self.frame(0x001000))
        self.assertEqual(r["outcome"], istim.FRAME_OK)
        self.assertEqual(r["frame_id"], 0x001000)
        self.assertFalse(r["fault"])

    def test_a_frame_built_from_two_source_ids_is_MIXED(self):
        w = self.frame(0x001000)
        w[20] = istim.witness_words(0x001001, 20, 0x7F)
        r = istim.classify_frame(w)
        self.assertEqual(r["outcome"], istim.MIXED_BLOCK_IDS)
        self.assertIsNone(r["frame_id"])

    def test_a_block_delivered_in_the_wrong_position_is_MISPLACED(self):
        w = self.frame(0x001000)
        w[5], w[6] = w[6], w[5]
        r = istim.classify_frame(w)
        self.assertEqual(r["outcome"], istim.MISPLACED_BLOCK_INDEX)

    def test_one_broken_block_invalidates_the_frame(self):
        w = self.frame(0x001000)
        w[31][7] = 0x0555
        self.assertEqual(istim.classify_frame(w)["outcome"], istim.INVALID_CANONICAL_STRIP)

    def test_a_disagreeing_status_is_refused(self):
        w = self.frame(0x001000)
        w[9] = istim.witness_words(0x001000, 9, 0x7F | istim.STATUS_FAULT_MASK)
        self.assertEqual(istim.classify_frame(w)["outcome"], istim.MIXED_BLOCK_IDS)

    def test_the_fault_latch_is_visible_at_frame_level(self):
        r = istim.classify_frame(self.frame(0x001000, 0x00 | istim.STATUS_FAULT_MASK))
        self.assertEqual(r["outcome"], istim.FRAME_OK)
        self.assertTrue(r["fault"])
        self.assertEqual(r["vmargin"], 0)


class ModularClassification(unittest.TestCase):
    """§6: frozen exactly, and the half-range case is NOT a forward gap."""

    def test_the_five_classes(self):
        self.assertEqual(istim.classify_delta(10, 10), istim.OBSERVED_DUPLICATE_ID)
        self.assertEqual(istim.classify_delta(10, 11), istim.OBSERVED_ID_CONTIGUOUS)
        self.assertEqual(istim.classify_delta(10, 12), istim.OBSERVED_ID_GAP)
        self.assertEqual(istim.classify_delta(10, 10 + (1 << 23) - 1), istim.OBSERVED_ID_GAP)
        self.assertEqual(istim.classify_delta(10, 10 + (1 << 23)), istim.UNRESOLVED_HALF_RANGE)
        self.assertEqual(istim.classify_delta(10, 10 + (1 << 23) + 1), istim.OBSERVED_REORDER)
        self.assertEqual(istim.classify_delta(10, 9), istim.OBSERVED_REORDER)

    def test_the_wrap_is_contiguous(self):
        seq = [0xFFFFFE, 0xFFFFFF, 0x000000, 0x000001]
        for a, b in zip(seq, seq[1:]):
            self.assertEqual(istim.classify_delta(a, b), istim.OBSERVED_ID_CONTIGUOUS,
                             "0x%06x -> 0x%06x" % (a, b))

    def test_the_half_range_is_never_called_a_gap(self):
        self.assertNotEqual(istim.classify_delta(0, 1 << 23), istim.OBSERVED_ID_GAP)


class ContentPattern(unittest.TestCase):
    """§20."""

    def test_the_bar_always_stays_inside_the_content_region(self):
        for f in range(istim.BAR_PERIOD * 3):
            for b in range(istim.BLOCKS):
                r = istim.bar_range(f, b)
                self.assertGreaterEqual(r.start, istim.CONTENT.start)
                self.assertLessEqual(r.stop - 1, istim.CONTENT.stop - 1)

    def test_the_period_matches_the_content_width(self):
        cells = len(istim.CONTENT) // istim.CELL
        self.assertEqual(istim.BAR_PERIOD, cells - istim.BAR_CELLS + 1)

    def test_the_last_bar_position_touches_the_last_content_column(self):
        self.assertEqual(istim.CONTENT.start + istim.CELL * (istim.BAR_PERIOD - 1)
                         + istim.CELL * istim.BAR_CELLS - 1, istim.CONTENT.stop - 1)

    def test_the_background_is_restorable_from_the_frame_id_alone(self):
        """Erasing the previous bar must be exactly `background`, so the ROM can
        restore it without remembering anything."""
        f, b = 500, 12
        for x in istim.bar_range(f, b):
            for row in range(4):
                y = b * 4 + row
                self.assertEqual(istim.expected_agb(f + 1, x, y)
                                 if x not in istim.bar_range(f + 1, b) else istim.BAR,
                                 istim.BAR if x in istim.bar_range(f + 1, b)
                                 else istim.background(x, y))

    def test_the_phase_multiplier_is_coprime_with_the_period(self):
        """The first proposal used 7, and gcd(7,35)=7 collapsed 40 blocks onto 5
        phases. The bar is a freshness witness, not an identifier, but a phase
        that repeats every 5 blocks is still a defect worth refusing."""
        from math import gcd
        self.assertEqual(gcd(istim.BAR_PHASE_MUL, istim.BAR_PERIOD), 1)
        phases = {istim.barpos(0, b) for b in range(istim.BLOCKS)}
        self.assertEqual(len(phases), istim.BAR_PERIOD,
                         "40 blocks over a %d-phase bar: %d distinct phases is the maximum"
                         % (istim.BAR_PERIOD, istim.BAR_PERIOD))

    def test_the_bar_moves_every_frame(self):
        for b in (0, 17, 39):
            self.assertNotEqual(istim.barpos(0, b), istim.barpos(1, b))


class VsigAgreesWithTheC(unittest.TestCase):
    """§9: the reference model must reproduce gbp_vsig_block() exactly."""

    SHIM = r'''
#include <stdio.h>
#include <stdlib.h>
#include "gbp_vsig.h"
int main(void) {
    static unsigned char buf[0x0F00];
    size_t n = fread(buf, 1, sizeof buf, stdin);
    if (n != sizeof buf) return 2;
    printf("%08x\n", gbp_vsig_block(buf, (unsigned)sizeof buf));
    return 0;
}
'''

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="istim-vsig-")
        src = os.path.join(cls.tmp, "shim.c")
        with open(src, "w") as f:
            f.write(cls.SHIM)
        cls.bin = os.path.join(cls.tmp, "shim")
        r = subprocess.run(["gcc", "-std=gnu11", "-O1", "-Wall", "-Wextra",
                            "-I", os.path.join(ROOT, "src", "gbp"),
                            "-o", cls.bin, src,
                            os.path.join(ROOT, "src", "gbp", "gbp_vsig.c")],
                           capture_output=True, text=True)
        cls.built = (r.returncode == 0)
        cls.build_err = r.stderr

    def _c(self, raw):
        r = subprocess.run([self.bin], input=raw, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return int(r.stdout.strip(), 16)

    def test_the_python_model_matches_the_c_on_real_stimulus_blocks(self):
        if not self.built:
            self.skipTest("gcc unavailable: %s" % self.build_err[:200])
        for f, b in ((0, 0), (1, 0), (7, 13), (0x123456, 39)):
            raw = istim.render_block_raw(f, b)
            self.assertEqual(istim.vsig_block(raw), self._c(raw), (f, b))

    def test_the_fast_path_matches_the_byte_path(self):
        for f, b in ((0, 0), (3, 1), (34, 39), (0xFFFFFF, 20)):
            self.assertEqual(istim.vsig_block_fast(f, b),
                             istim.vsig_block(istim.render_block_raw(f, b)))

    def test_the_signature_includes_bit15_although_the_id_decode_does_not(self):
        a = istim.vsig_block(istim.render_block_raw(0, 0, flag15_at_origin=False))
        c = istim.vsig_block(istim.render_block_raw(0, 0, flag15_at_origin=True))
        self.assertNotEqual(a, c, "bit 15 at (0,0) shifts sig[0] of block 0")
        self.assertEqual(istim.vsig_block_fast(0, 0, True), c)

    def test_bytes_0_and_2_cannot_change_the_signature(self):
        if not self.built:
            self.skipTest("gcc unavailable")
        a = istim.render_block_raw(0, 5, filler=0x00)
        b = istim.render_block_raw(0, 5, filler=0xA5)
        self.assertNotEqual(a, b)
        self.assertEqual(self._c(a), self._c(b))


class SignatureIsAChecksumNotAHash(unittest.TestCase):
    """§8/§9: state the collision structure instead of hoping it is absent."""

    def test_it_is_blind_to_permutations_within_one_parity_class(self):
        raw = bytearray(istim.render_block_raw(0x000abc, 6))
        # swap two pixels that are both at even x in the same row
        o1, o2 = 100 * 4, 120 * 4
        for k in (1, 3):
            raw[o1 + k], raw[o2 + k] = raw[o2 + k], raw[o1 + k]
        self.assertEqual(istim.vsig_block(bytes(raw)),
                         istim.vsig_block(istim.render_block_raw(0x000abc, 6)),
                         "an even-x permutation is invisible to an additive checksum")

    def test_a_compensating_pair_of_changes_is_invisible(self):
        base = istim.render_block_raw(0x000abc, 6)
        raw = bytearray(base)
        # +1 on one even-x pixel, -1 on another even-x pixel
        raw[100 * 4 + 3] = (raw[100 * 4 + 3] + 1) & 0xFF
        raw[120 * 4 + 3] = (raw[120 * 4 + 3] - 1) & 0xFF
        self.assertEqual(istim.vsig_block(bytes(raw)), istim.vsig_block(base))


class AdversarialCharacterisationOfTheSignature(unittest.TestCase):
    """§14. These are CHARACTERISATION results, locked so a later round cannot
    quietly assume the signature is stronger than it is. A MISS here is not a
    bug in gbp_vsig_block — it is a checksum doing exactly what a checksum does,
    and the point is that the experiment must not lean on it."""

    F, B = 0x001234, 9

    def setUp(self):
        self.base_raw = istim.render_block_raw(self.F, self.B)
        self.base = istim.vsig_block(self.base_raw)

    def _changed(self, mutated):
        return istim.vsig_block(bytes(mutated)) != self.base

    def test_it_detects_a_single_bit_in_a_consumed_pixel(self):
        for px in (500, 501):
            r = bytearray(self.base_raw)
            r[px * 4 + 3] ^= 0x01
            self.assertTrue(self._changed(r), "pixel %d" % px)

    def test_it_detects_a_block_from_the_adjacent_frame(self):
        self.assertNotEqual(istim.vsig_block(istim.render_block_raw(self.F + 1, self.B)),
                            self.base)

    def test_it_MISSES_a_block_from_frame_plus_one_bar_period(self):
        self.assertEqual(istim.vsig_block(istim.render_block_raw(self.F + istim.BAR_PERIOD, self.B)),
                         self.base, "the period-35 collision is structural")

    def test_it_MISSES_a_strip_substituted_from_another_frame_id(self):
        r = bytearray(self.base_raw)
        other = istim.render_block_raw(self.F + 0x8765, self.B)
        for row in range(4):
            for x in list(istim.STRIP_L) + list(istim.STRIP_R):
                for k in (1, 3):
                    r[row * 960 + x * 4 + k] = other[row * 960 + x * 4 + k]
        self.assertFalse(self._changed(r),
                         "the complement-pair strip is invisible to an additive checksum")

    def test_it_MISSES_a_strip_substituted_from_another_block_index(self):
        r = bytearray(self.base_raw)
        other = istim.render_block_raw(self.F, self.B + 1)
        for row in range(4):
            for x in list(istim.STRIP_L) + list(istim.STRIP_R):
                for k in (1, 3):
                    r[row * 960 + x * 4 + k] = other[row * 960 + x * 4 + k]
        self.assertFalse(self._changed(r))

    def test_it_MISSES_a_duplicated_row(self):
        r = bytearray(self.base_raw)
        r[960:1920] = self.base_raw[0:960]
        self.assertFalse(self._changed(r))

    def test_it_MISSES_a_compensating_pair(self):
        r = bytearray(self.base_raw)
        r[100 * 4 + 3] = (r[100 * 4 + 3] + 1) & 0xFF
        r[120 * 4 + 3] = (r[120 * 4 + 3] - 1) & 0xFF
        self.assertFalse(self._changed(r))

    def test_it_MISSES_bytes_0_and_2_BY_DESIGN(self):
        r = bytearray(self.base_raw)
        r[100 * 4 + 0] = 0xA5
        r[100 * 4 + 2] = 0x5A
        self.assertFalse(self._changed(r), "U-GBP-029 must not be able to move it")


class Ddr2SignatureFeasibility(unittest.TestCase):
    """§13: answered by construction, not by sampling."""

    def test_the_strip_contributes_a_constant_to_the_signature(self):
        """The complement-pair layout makes the per-parity ONE count constant, so
        the frame id cannot reach an additive checksum through the strips."""
        def counts(f, b):
            ev = od = 0
            for row in range(4):
                y = b * 4 + row
                for x in list(istim.STRIP_L) + list(istim.STRIP_R):
                    if istim.swap_outer(istim.expected_agb(f, x, y)) == istim.ONE:
                        if x & 1:
                            od += 1
                        else:
                            ev += 1
            return ev, od
        ref = counts(0, 0)
        for f in (1, 2, 0x5A5A5A, 0xFFFFFF):
            self.assertEqual(counts(f, 0), ref)
        # 54 bits per strip, 27 odd and 27 even positions, two strips, two
        # (true, complement) row pairs: 2 * 2 * 27 = 108 per parity class,
        # constant whatever the payload is.
        self.assertEqual(ref, (108, 108))

    def test_the_signature_has_the_bar_period_in_the_frame_id(self):
        for b in (0, 1, 19, 39):
            for f in range(0, 12):
                self.assertEqual(istim.vsig_block_fast(f, b),
                                 istim.vsig_block_fast(f + istim.BAR_PERIOD, b))

    def test_the_signature_therefore_cannot_identify_a_frame_id(self):
        """At most BAR_PERIOD distinct values exist per block, and in fact fewer."""
        for b in (0, 20, 39):
            vals = {istim.vsig_block_fast(f, b) for f in range(istim.BAR_PERIOD)}
            self.assertLessEqual(len(vals), istim.BAR_PERIOD)
            self.assertLess(len(vals), istim.BAR_PERIOD,
                            "even the bar phase is not recoverable")


if __name__ == "__main__":
    unittest.main()


class WitnessCapacity(unittest.TestCase):
    """§11: derived from the population and the measured free memory."""

    def test_the_capacity_covers_the_expected_thirty_second_population(self):
        expected = 30 * 59.737
        self.assertGreater(istim.WITNESS_CAPACITY_FRAMES, expected * 1.10,
                           "capacity must exceed the population plus margin")
        self.assertEqual(istim.WITNESS_CAPACITY_FRAMES, 2048)

    def test_the_footprint_fits_what_stream_0003_leaves_free(self):
        mib = istim.WITNESS_CAPACITY_BYTES / 1048576.0
        self.assertLess(mib, 13.97, "must fit the measured free MEM1")
        self.assertAlmostEqual(mib, 8.44, places=1)

    def test_the_per_frame_cost_is_the_declared_one(self):
        self.assertEqual(istim.WITNESS_BYTES_PER_FRAME, 4320)
        self.assertEqual(istim.WITNESS_CAPACITY_BYTES,
                         istim.WITNESS_CAPACITY_FRAMES * 4320)


class DecisivePopulation(unittest.TestCase):
    """§18/§19: the status delay and the edges, applied rather than described."""

    @staticmethod
    def frame(f, st=0x40):
        return istim.classify_frame([istim.witness_words(f, b, st)
                                     for b in range(istim.BLOCKS)])

    def test_the_status_delay_removes_the_last_intact_frame(self):
        seq = [self.frame(100 + i) for i in range(6)]
        r = istim.decisive_population(seq)
        self.assertEqual(r["observed_intact"], 6)
        self.assertEqual(r["decisive_frames"], [100, 101, 102, 103, 104],
                         "frame 105's own update is certified by nothing")
        self.assertEqual(len(r["decisive_transitions"]), 4)
        self.assertEqual(r["verdict"], "OBSERVED_CONTIGUOUS")

    def test_the_excluded_set_is_reported_not_hidden(self):
        r = istim.decisive_population([self.frame(100 + i) for i in range(4)])
        kinds = {k for k, _ in r["excluded"]}
        self.assertEqual(kinds, {"trailing_frame_uncertified",
                                 "leading_edge", "trailing_edge"})

    def test_a_gap_inside_the_decisive_set_is_reported(self):
        seq = [self.frame(x) for x in (100, 101, 103, 104, 105)]
        r = istim.decisive_population(seq)
        self.assertEqual(r["verdict"], "OBSERVED_DISCONTINUITY")
        self.assertIn((101, 103, istim.OBSERVED_ID_GAP), r["decisive_transitions"])

    def test_a_fault_latch_anywhere_invalidates_the_decisive_claim(self):
        seq = [self.frame(100), self.frame(101, 0x40 | istim.STATUS_FAULT_MASK),
               self.frame(102), self.frame(103)]
        r = istim.decisive_population(seq)
        self.assertTrue(r["fault_seen"])
        self.assertEqual(r["verdict"], "STIMULUS_INVALID_FOR_DECISIVE_CLAIM")

    def test_too_few_intact_frames_is_inconclusive_not_pass(self):
        self.assertEqual(istim.decisive_population([self.frame(1)])["verdict"],
                         "INCONCLUSIVE_TOO_FEW_INTACT_FRAMES")
        self.assertEqual(istim.decisive_population([])["verdict"],
                         "INCONCLUSIVE_TOO_FEW_INTACT_FRAMES")

    def test_the_wrap_is_contiguous_in_the_decisive_set(self):
        seq = [self.frame(x) for x in (0xFFFFFE, 0xFFFFFF, 0x000000, 0x000001)]
        r = istim.decisive_population(seq)
        self.assertEqual(r["verdict"], "OBSERVED_CONTIGUOUS")


class StatusSemantics(unittest.TestCase):
    """§15/§16: the stimulus's own verdict on whether it met VBlank."""

    def test_the_gba_facts_the_mechanism_rests_on(self):
        self.assertEqual(istim.VCOUNT_VBLANK_FIRST, 160)
        self.assertEqual(istim.VCOUNT_LAST, 227)
        self.assertEqual(istim.VBLANK_CYCLES, 68 * 1232)
        self.assertEqual(istim.TIMER_HZ, 16777216 // 64)
        self.assertEqual(istim.VBLANK_TICKS, 83776 // 64)

    def test_the_margin_field_can_express_the_whole_vblank(self):
        vblank_lines = istim.VCOUNT_LAST - istim.VCOUNT_VBLANK_FIRST + 1
        self.assertEqual(vblank_lines, 68)
        self.assertLessEqual(vblank_lines, istim.STATUS_MARGIN_MASK,
                             "7 bits must hold the largest possible margin")

    def test_the_init_value_means_no_update_measured_yet(self):
        self.assertEqual(istim.STATUS_MARGIN_INIT, 0x7F)
        self.assertGreater(istim.STATUS_MARGIN_INIT,
                           istim.VCOUNT_LAST - istim.VCOUNT_VBLANK_FIRST + 1,
                           "the init value must be unreachable by a real margin")

    def test_fault_and_margin_do_not_overlap(self):
        self.assertEqual(istim.STATUS_FAULT_MASK & istim.STATUS_MARGIN_MASK, 0)
        self.assertEqual(istim.STATUS_FAULT_MASK | istim.STATUS_MARGIN_MASK, 0xFF)
