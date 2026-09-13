"""Synthetic tests for tools/gciso.py (GameCube disc image parser)."""
import json
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import gciso  # noqa: E402


def build_image():
    """Minimal disc: header, bi2, apploader, a DOL, FST with one dir and two files."""
    img = bytearray(0x4000)
    img[0:6] = b"TEST01"
    struct.pack_into(">I", img, 0x1C, gciso.DISC_MAGIC)
    img[0x20:0x2A] = b"Test Disc\0"
    apl = bytearray(0x20 + 0x40 + 0x10)
    apl[0:10] = b"2026/09/13"
    struct.pack_into(">III", apl, 0x10, 0x81200000, 0x40, 0x10)
    img[gciso.APPLOADER_OFFSET:gciso.APPLOADER_OFFSET + len(apl)] = apl
    dol_off = 0x3000
    dol = bytearray(0x100 + 0x40)
    struct.pack_into(">I", dol, 0x00, 0x100)
    struct.pack_into(">I", dol, 0x48, 0x80003100)
    struct.pack_into(">I", dol, 0x90, 0x40)
    struct.pack_into(">I", dol, 0xE0, 0x80003100)
    img[dol_off:dol_off + len(dol)] = dol
    # FST: root, dir "d", file "d/a.bin", file "b.bin"
    names = b"d\0a.bin\0b.bin\0"
    fst = bytearray(12 * 4)
    struct.pack_into(">III", fst, 0, 0x01000000, 0, 4)
    struct.pack_into(">III", fst, 12, 0x01000000 | 0, 0, 3)          # dir d, parent 0, next 3
    struct.pack_into(">III", fst, 24, 0x00000000 | 2, 0x3800, 8)     # file a.bin
    struct.pack_into(">III", fst, 36, 0x00000000 | 8, 0x3900, 4)     # file b.bin
    fst += names
    fst_off = 0x3400
    img[fst_off:fst_off + len(fst)] = fst
    struct.pack_into(">IIII", img, 0x420, dol_off, fst_off, len(fst), len(fst))
    img[0x3800:0x3808] = b"AAAAAAAA"
    img[0x3900:0x3904] = b"BBBB"
    return bytes(img)


class GcIsoParse(unittest.TestCase):
    def setUp(self):
        self.img = build_image()

    def test_header(self):
        h = gciso.parse_header(self.img[:gciso.BOOT_SIZE])
        self.assertEqual(h.game_id, "TEST")
        self.assertEqual(h.maker_code, "01")
        self.assertEqual(h.game_name, "Test Disc")
        self.assertEqual(h.dol_offset, 0x3000)
        self.assertEqual(h.fst_offset, 0x3400)

    def test_bad_magic(self):
        bad = bytearray(self.img[:gciso.BOOT_SIZE])
        struct.pack_into(">I", bad, 0x1C, 0)
        with self.assertRaises(gciso.GcIsoError):
            gciso.parse_header(bytes(bad))

    def test_fst(self):
        h = gciso.parse_header(self.img[:gciso.BOOT_SIZE])
        entries = gciso.parse_fst(self.img[h.fst_offset:h.fst_offset + h.fst_size])
        paths = [(e.path, e.is_dir, e.offset, e.size) for e in entries]
        self.assertEqual(paths, [("d", True, 0, 3), ("d/a.bin", False, 0x3800, 8), ("b.bin", False, 0x3900, 4)])

    def test_dol_size(self):
        h = gciso.parse_header(self.img[:gciso.BOOT_SIZE])
        self.assertEqual(gciso.dol_total_size(self.img[h.dol_offset:h.dol_offset + 0x100]), 0x140)

    def test_extract_manifest(self):
        d = tempfile.mkdtemp()
        src = os.path.join(d, "t.iso")
        with open(src, "wb") as f:
            f.write(self.img)
        out = os.path.join(d, "out")
        self.assertEqual(gciso.main(["extract", src, out]), 0)
        m = json.load(open(os.path.join(out, "manifest.json")))
        names = {p["name"]: p for p in m["parts"]}
        self.assertEqual(set(names), {"boot.bin", "bi2.bin", "apploader.img", "main.dol", "fst.bin",
                                      "files/d/a.bin", "files/b.bin"})
        self.assertEqual(names["main.dol"]["size"], 0x140)
        self.assertEqual(names["apploader.img"]["size"], 0x70)
        self.assertEqual(open(os.path.join(out, "files", "d", "a.bin"), "rb").read(), b"AAAAAAAA")
        self.assertEqual(len(names["files/b.bin"]["sha256"]), 64)
        # source image untouched
        self.assertEqual(open(src, "rb").read(), self.img)


if __name__ == "__main__":
    unittest.main()
