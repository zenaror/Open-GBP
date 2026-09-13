"""
Synthetic-vector tests for tools/dolpad.py (32-byte section size padding).

Runs under pytest or `python3 -m unittest`.
"""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import dolinfo  # noqa: E402
import dolpad   # noqa: E402
from test_dolinfo import make_dol  # noqa: E402


class PadDol(unittest.TestCase):
    def test_unaligned_sizes_are_padded(self):
        text = bytes(range(1, 41))          # 40 bytes -> 64
        data = b"\xAB" * 17                 # 17 bytes -> 32
        img = make_dol(text=[(0x80003100, text)], data=[(0x80004000, data)],
                       bss=(0x80005000, 0x100))
        self.assertFalse(dolinfo.parse_dol(img).dolphin_loadable)

        out = dolpad.pad_dol(img)
        info = dolinfo.parse_dol(out)
        self.assertTrue(info.dolphin_loadable)
        t, d = info.text_sections[0], info.data_sections[0]
        self.assertEqual((t.load_address, t.size), (0x80003100, 64))
        self.assertEqual((d.load_address, d.size), (0x80004000, 32))
        self.assertEqual(t.file_offset % 32, 0)
        self.assertEqual(d.file_offset % 32, 0)
        # payload preserved, padding is zero
        self.assertEqual(out[t.file_offset:t.file_offset + 40], text)
        self.assertEqual(out[t.file_offset + 40:t.file_offset + 64], b"\0" * 24)
        self.assertEqual(out[d.file_offset:d.file_offset + 17], data)
        # header scalars untouched
        self.assertEqual(info.entry_point, 0x80003100)
        self.assertEqual((info.bss_address, info.bss_size), (0x80005000, 0x100))

    def test_already_aligned_is_identity_modulo_layout(self):
        img = make_dol(text=[(0x80003100, b"\x60\0\0\0" * 8)],
                       data=[(0x80004000, b"\1" * 32)])
        out = dolpad.pad_dol(img)
        self.assertEqual(out, img)

    def test_idempotent(self):
        img = make_dol(text=[(0x80003100, b"\x60\0\0\0" * 5)],
                       data=[(0x80004000, b"\1" * 33)])
        once = dolpad.pad_dol(img)
        twice = dolpad.pad_dol(once)
        self.assertEqual(once, twice)

    def test_padding_may_extend_into_gap_or_bss(self):
        # text ends at 0x80003114; data starts at 0x80003120 (8 bytes gap, 32-aligned)
        img = make_dol(text=[(0x80003100, b"\0" * 20)],
                       data=[(0x80003120, b"\0" * 20)],
                       bss=(0x80003140, 0x40))  # data padding 0x80003134->0x80003140 hits nothing
        out = dolpad.pad_dol(img)
        info = dolinfo.parse_dol(out)
        self.assertEqual(info.text_sections[0].end_address, 0x80003120)
        self.assertEqual(info.data_sections[0].end_address, 0x80003140)

    def test_rejects_padding_that_would_overlap_another_section(self):
        # text 0x80003100+20 pads to 0x80003120, but data already lives at 0x80003114? no:
        # addresses must be 32-aligned, so build the overlap with two data sections
        # separated by less than the padding: data0 at 0x80004000 size 40 pads to 0x80004040,
        # data1 at 0x80004020 -> overlap.
        img = make_dol(text=[(0x80003100, b"\0" * 32)],
                       data=[(0x80004000, b"\0" * 40), (0x80004020, b"\0" * 32)])
        with self.assertRaises(dolinfo.DolError):
            dolpad.pad_dol(img)

    def test_rejects_unaligned_load_address(self):
        img = make_dol(text=[(0x80003104, b"\0" * 32)])
        with self.assertRaises(dolinfo.DolError):
            dolpad.pad_dol(img)

    def test_multiple_sections_keep_order_and_offsets_aligned(self):
        img = make_dol(text=[(0x80003100, b"\1" * 33), (0x80010000, b"\2" * 1)],
                       data=[(0x80020000, b"\3" * 100), (0x80030000, b"\4" * 31)])
        out = dolpad.pad_dol(img)
        info = dolinfo.parse_dol(out)
        sizes = [(s.kind, s.index, s.size) for s in info.sections]
        self.assertEqual(sizes, [("text", 0, 64), ("text", 1, 32), ("data", 0, 128), ("data", 1, 32)])
        offs = [s.file_offset for s in info.sections]
        self.assertEqual(offs, sorted(offs))
        self.assertTrue(all(o % 32 == 0 for o in offs))
        self.assertEqual(out[info.data_sections[0].file_offset:][:100], b"\3" * 100)


class CommandLine(unittest.TestCase):
    def test_check_and_convert(self):
        import tempfile
        img = make_dol(text=[(0x80003100, b"\0" * 20)])
        d = tempfile.mkdtemp()
        src, dst = os.path.join(d, "in.dol"), os.path.join(d, "out.dol")
        with open(src, "wb") as f:
            f.write(img)
        self.assertEqual(dolpad.main(["--check", src]), 1)
        self.assertEqual(dolpad.main([src, dst]), 0)
        self.assertEqual(dolpad.main(["--check", dst]), 0)
        self.assertTrue(dolinfo.parse_dol_file(dst).dolphin_loadable)


if __name__ == "__main__":
    unittest.main()
