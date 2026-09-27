"""tests/host/test_v125const.py -- GitHub Issue #125, steps 1 and 2: tools/v125const.py, the constant hits and the
gbi/gbihf/gbisr differential.

What is proved here, on constructions only (PowerPC words assembled by hand, IEEE constants packed, ASCII runs):
  * a 16-bit immediate is found in each form the tool names (li, ori, cmpwi, cmplwi, mulli), and addi with a base
    register is not li;
  * a 32-bit constant BUILT from two halves is reconstructed -- lis + addi (a negative low half included), lis + ori,
    and lis + a load or store off the lis register (an MMIO address) -- only when the second instruction reads the lis
    register within LOOKAHEAD instructions, never through rA = 0 (a literal zero); a lis counts alone only when
    nothing consumes it, and once per site however many consumers reach the same value (#125's reviews);
  * data words, singles and 8-aligned doubles are found anywhere, a misaligned double is not; the targets are also
    found as little-endian words;
  * keywords are found case-insensitively in printable runs of at least four characters;
  * the differential lists exactly the targets whose counts differ between gbi and gbihf;
  * gbi_unpack.unpack returns (image, payload offset, payload length) on a constructed packed DOL (the tuple was the
    bug found on #125).
On the private inputs (skipped where they are absent), the steps-1-2 findings #125 posted: no binary builds or holds the
AGB's SOUNDBIAS address in any scanned form, while the same scan finds the AI's (a positive control); `li 125` is in gbi
and gbisr and not in gbihf; and the AI register constants count the same in all three editions.
"""
import lzma
import os
import struct
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gbi_unpack  # noqa: E402
import v125const  # noqa: E402

BASE = 0x80003100


def li(rd, v):
    return (14 << 26) | (rd << 21) | (v & 0xFFFF)


def lis(rd, hi):
    return (15 << 26) | (rd << 21) | (hi & 0xFFFF)


def addi(rd, ra, v):
    return (14 << 26) | (rd << 21) | (ra << 16) | (v & 0xFFFF)


def ori(ra, rs, v):
    return (24 << 26) | (rs << 21) | (ra << 16) | (v & 0xFFFF)


def cmpwi(ra, v):
    return (11 << 26) | (ra << 16) | (v & 0xFFFF)


def cmplwi(ra, v):
    return (10 << 26) | (ra << 16) | (v & 0xFFFF)


def mulli(rd, ra, v):
    return (7 << 26) | (rd << 21) | (ra << 16) | (v & 0xFFFF)


def lhz(rd, d, ra):
    return (40 << 26) | (rd << 21) | (ra << 16) | (d & 0xFFFF)


def sth(rs, d, ra):
    return (44 << 26) | (rs << 21) | (ra << 16) | (d & 0xFFFF)


NOP = ori(0, 0, 0)


def code(*words):
    return [(BASE, struct.pack(">%dI" % len(words), *words), True)]


class TheImmediates(unittest.TestCase):
    def test_each_form_is_found_at_its_address(self):
        imm, _c = v125const.scan_code(code(li(3, 125), ori(4, 4, 4096), cmpwi(5, 512), cmplwi(6, 256), mulli(7, 8, 32000)))
        self.assertEqual(imm[125], [BASE])
        self.assertEqual(imm[4096], [BASE + 4])
        self.assertEqual(imm[512], [BASE + 8])
        self.assertEqual(imm[256], [BASE + 12])
        self.assertEqual(imm[32000], [BASE + 16])

    def test_li_with_a_base_register_is_addi_not_li(self):
        imm, _c = v125const.scan_code(code(addi(3, 4, 125)))
        self.assertNotIn(125, imm)

    def test_a_value_outside_the_targets_is_not_reported(self):
        imm, c32 = v125const.scan_code(code(li(3, 124), NOP))
        self.assertEqual((imm, c32), ({}, {}))


class TheSplitConstants(unittest.TestCase):
    def test_lis_addi_and_lis_ori_are_reconstructed(self):
        _i, c32 = v125const.scan_code(code(lis(4, 0xCC00), addi(5, 4, 0x6C00), lis(6, 0x0400), ori(6, 6, 0x0088)))
        self.assertEqual(c32[0xCC006C00], [BASE])
        self.assertEqual(c32[0x04000088], [BASE + 8])

    def test_a_negative_low_half_is_subtracted(self):
        # 48000 = 0xBB80: the low half is >= 0x8000, so a compiler writes lis 1 ; addi -0x4480
        _i, c32 = v125const.scan_code(code(lis(4, 0x0001), addi(4, 4, -0x4480)))
        self.assertEqual(c32[48000], [BASE])
        self.assertNotIn(65536, c32)                                       # the lis is consumed, not alone

    def test_a_load_or_store_off_the_lis_builds_an_address(self):
        _i, c32 = v125const.scan_code(code(lis(4, 0x0400), lhz(5, 0x88, 4), lis(6, 0xCC00), sth(7, 0x6C00, 6)))
        self.assertEqual(c32[0x04000088], [BASE])
        self.assertEqual(c32[0xCC006C00], [BASE + 8])

    def test_a_site_counts_once_however_many_consumers(self):
        _i, c32 = v125const.scan_code(code(lis(4, 0xCC00), lhz(5, 0x6C00, 4), sth(6, 0x6C00, 4)))
        self.assertEqual(c32[0xCC006C00], [BASE])

    def test_ra_zero_is_a_literal_zero(self):
        _i, c32 = v125const.scan_code(code(lis(0, 0xCC00), addi(5, 0, 0x6C00), lhz(6, 0x6C00, 0)))
        self.assertNotIn(0xCC006C00, c32)

    def test_only_the_lis_register_and_only_within_the_lookahead(self):
        far = [lis(4, 0xCC00)] + [NOP] * v125const.LOOKAHEAD + [addi(5, 4, 0x6C00)]
        _i, c32 = v125const.scan_code(code(*far))
        self.assertNotIn(0xCC006C00, c32)
        near = [lis(4, 0xCC00)] + [NOP] * (v125const.LOOKAHEAD - 1) + [addi(5, 4, 0x6C00)]
        _i, c32 = v125const.scan_code(code(*near))
        self.assertEqual(c32[0xCC006C00], [BASE])
        _i, c32 = v125const.scan_code(code(lis(4, 0xCC00), addi(5, 3, 0x6C00)))
        self.assertNotIn(0xCC006C00, c32)

    def test_a_bare_lis_counts_its_high_half_only_when_unconsumed(self):
        _i, c32 = v125const.scan_code(code(lis(3, 0x0001), NOP))          # 0x00010000 == 65536
        self.assertEqual(c32[65536], [BASE])
        _i, c32 = v125const.scan_code(code(lis(3, 0x0001), addi(3, 3, 0x100)))
        self.assertNotIn(65536, c32)

    def test_data_regions_are_not_scanned_as_code(self):
        regions = [(BASE, struct.pack(">2I", lis(4, 0xCC00), addi(5, 4, 0x6C00)), False)]
        self.assertEqual(v125const.scan_code(regions), ({}, {}))


class TheData(unittest.TestCase):
    def test_words_singles_and_aligned_doubles(self):
        buf = (struct.pack(">I", 0xCC006C00) + struct.pack(">f", 32000.0) + struct.pack(">d", 65536.0)
               + struct.pack(">I", 0) + struct.pack(">d", 48000.0) + struct.pack(">I", 0x0200))
        w32, flt = v125const.scan_data([(BASE, buf, False)])
        self.assertEqual(w32, {0xCC006C00: [BASE]})                        # 0x0200 is left to the imm scan
        self.assertEqual(flt[32000.0], [(BASE + 4, "s")])
        self.assertEqual(flt[65536.0], [(BASE + 8, "d")])
        self.assertNotIn(48000.0, flt)                                     # its first word sits at an odd index

    def test_little_endian_words(self):
        le = {}
        w32, _f = v125const.scan_data([(BASE, struct.pack("<I", 0x04000088) + struct.pack(">I", 7), False)], le)
        self.assertEqual((le, w32), ({0x04000088: [BASE]}, {}))

    def test_keywords_are_case_insensitive_and_need_four_characters(self):
        buf = b"\0Sound Mode\0dsp\0OUTPUT RATE\0"
        strs = v125const.scan_strings([(BASE, buf, False)])
        self.assertIn((BASE + 1, "sound"), strs)
        self.assertIn((BASE + 16, "rate"), strs)
        self.assertNotIn("dsp", [k for _a, k in strs])


class TheDifferential(unittest.TestCase):
    def test_only_the_targets_that_differ_between_gbi_and_gbihf(self):
        a = v125const.analyse_regions(code(li(3, 125), li(4, 256)))
        b = v125const.analyse_regions(code(li(4, 256), NOP))
        table, differ = v125const.differential({"gbi": a, "gbihf": b, "gbisr": a})
        self.assertEqual([(k, t) for k, t, _r in differ], [("imm", "0x7D")])
        self.assertEqual(table["imm"]["0x100"], {"gbi": 1, "gbihf": 1, "gbisr": 1})

    def test_an_absent_edition_is_none_not_zero(self):
        a = v125const.analyse_regions(code(li(3, 125)))
        table, _d = v125const.differential({"gbi": a, "gbihf": None, "gbisr": a})
        self.assertIsNone(table["imm"]["0x7D"]["gbihf"])


def packed_dol(image):
    """A DOL shaped like GBI's loader: a 40-byte key starting "Copyright" at text0, and in data section 0 the image
    as an XZ stream XOR-ed with that key (key index = payload offset mod 40)."""
    key = b"Copyright (c) a constructed test key..."[:gbi_unpack.KEY_LEN].ljust(gbi_unpack.KEY_LEN, b".")
    xz = lzma.compress(image, format=lzma.FORMAT_XZ)
    obf = bytes(b ^ key[i % gbi_unpack.KEY_LEN] for i, b in enumerate(xz))
    hdr = bytearray(0x100)
    struct.pack_into(">I", hdr, 0x00, 0x100)                  # text0 offset
    struct.pack_into(">I", hdr, 0x90, 0x40)                   # text0 size
    struct.pack_into(">I", hdr, 0x1C, 0x140)                  # data0 (section 7) offset
    struct.pack_into(">I", hdr, 0xAC, len(obf))               # data0 size
    return bytes(hdr) + key.ljust(0x40, b"\0") + obf, len(obf)


class TheUnpacker(unittest.TestCase):
    def test_unpack_returns_the_image_its_offset_and_its_length(self):
        image = bytes(range(256)) * 3
        dol, n = packed_dol(image)
        self.assertEqual(gbi_unpack.unpack(dol), (image, 0x140, n))


class ThePrivateInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = [os.path.join(ROOT, "input", "gbi", "apps", e, e + ".dol") for e in v125const.EDITIONS]
        if not (all(os.path.isfile(p) for p in paths) and os.path.isfile(v125const.DISC_DOL)):
            raise unittest.SkipTest("the private reference inputs are not present on this host")
        cls.r = v125const.analyse()

    def test_no_binary_builds_or_holds_soundbias_while_the_ai_is_found(self):
        for name, b in self.r["binaries"].items():
            for kind in ("const32", "word32", "word32le"):
                self.assertNotIn("0x04000088", b[kind], (name, kind))
            self.assertGreater(len(b["const32"].get("0xCC006C00", [])), 0, name)      # the positive control

    def test_li_125_is_in_gbi_and_gbisr_and_not_in_gbihf(self):
        imm = dict((e, len(self.r["binaries"][e]["imm"].get("0x7D", []))) for e in v125const.EDITIONS)
        self.assertEqual(imm, {"gbi": 3, "gbihf": 0, "gbisr": 3})

    def test_the_ai_register_counts_agree_across_editions(self):
        for reg in ("0xCC006C00", "0xCC006C04", "0xCC006C08", "0xCC006C0C"):
            counts = set(len(self.r["binaries"][e]["const32"].get(reg, [])) for e in v125const.EDITIONS)
            self.assertEqual(len(counts), 1, reg)

    def test_the_images_are_the_recorded_ones(self):
        import hashlib
        want = {"gbi": "0b2c44ea", "gbihf": "2f59aac9", "gbisr": "4c44dc92"}
        for e, h in want.items():
            img = gbi_unpack.unpack(open(os.path.join(ROOT, "input", "gbi", "apps", e, e + ".dol"), "rb").read())[0]
            self.assertTrue(hashlib.sha256(img).hexdigest().startswith(h), e)


if __name__ == "__main__":
    unittest.main()
