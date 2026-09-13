"""
Synthetic-vector tests for tools/dolinfo.py (DOL header parser).

No build artifacts are needed: DOL images are constructed in memory.
Runs under pytest or `python3 -m unittest`.
"""
import os
import struct
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import dolinfo  # noqa: E402


def make_dol(text=(), data=(), bss=(0, 0), entry=None, pad_to=None):
    """
    Build a DOL image. text/data are lists of (load_address, payload_bytes).
    Sections are laid out sequentially after the header.
    """
    hdr = bytearray(dolinfo.DOL_HEADER_SIZE)
    body = bytearray()
    offsets = [0] * dolinfo.DOL_SECTIONS
    addrs = [0] * dolinfo.DOL_SECTIONS
    sizes = [0] * dolinfo.DOL_SECTIONS

    def place(slot, addr, payload):
        offsets[slot] = dolinfo.DOL_HEADER_SIZE + len(body)
        addrs[slot] = addr
        sizes[slot] = len(payload)
        body.extend(payload)

    for i, (addr, payload) in enumerate(text):
        place(i, addr, payload)
    for i, (addr, payload) in enumerate(data):
        place(dolinfo.DOL_TEXT_SECTIONS + i, addr, payload)

    struct.pack_into(">%dI" % dolinfo.DOL_SECTIONS, hdr, 0x00, *offsets)
    struct.pack_into(">%dI" % dolinfo.DOL_SECTIONS, hdr, 0x48, *addrs)
    struct.pack_into(">%dI" % dolinfo.DOL_SECTIONS, hdr, 0x90, *sizes)
    if entry is None:
        entry = text[0][0] if text else 0
    struct.pack_into(">III", hdr, 0xD8, bss[0], bss[1], entry)
    img = bytes(hdr) + bytes(body)
    if pad_to is not None and len(img) < pad_to:
        img += b"\0" * (pad_to - len(img))
    return img


class ParseValidDol(unittest.TestCase):
    def setUp(self):
        self.img = make_dol(
            text=[(0x80003100, b"\x60\x00\x00\x00" * 8)],   # 32 bytes of nop
            data=[(0x80004000, b"\xAA" * 16), (0x80005000, b"\xBB" * 64)],
            bss=(0x80010000, 0x2000),
            entry=0x80003104,
        )

    def test_header_fields(self):
        info = dolinfo.parse_dol(self.img)
        self.assertEqual(info.entry_point, 0x80003104)
        self.assertEqual(info.bss_address, 0x80010000)
        self.assertEqual(info.bss_size, 0x2000)
        self.assertEqual(info.file_size, len(self.img))

    def test_sections(self):
        info = dolinfo.parse_dol(self.img)
        self.assertEqual(len(info.text_sections), 1)
        self.assertEqual(len(info.data_sections), 2)
        t = info.text_sections[0]
        self.assertEqual((t.file_offset, t.load_address, t.size), (0x100, 0x80003100, 32))
        d1 = info.data_sections[1]
        self.assertEqual((d1.file_offset, d1.load_address, d1.size), (0x100 + 32 + 16, 0x80005000, 64))
        self.assertEqual(d1.end_address, 0x80005040)

    def test_section_containing(self):
        info = dolinfo.parse_dol(self.img)
        self.assertEqual(info.section_containing(0x80003100).kind, "text")
        self.assertEqual(info.section_containing(0x8000311F).kind, "text")
        self.assertIsNone(info.section_containing(0x80003120))
        self.assertEqual(info.section_containing(0x80005000).index, 1)

    def test_alignment_reporting(self):
        info = dolinfo.parse_dol(self.img)   # text 32 bytes ok, data 16 and 64
        self.assertTrue(info.text_sections[0].aligned32)
        self.assertFalse(info.data_sections[0].aligned32)
        self.assertTrue(info.data_sections[1].aligned32)
        self.assertFalse(info.dolphin_loadable)
        self.assertEqual([s.index for s in info.unaligned_sections], [0])
        self.assertIn("NO", dolinfo.format_summary(info))
        self.assertFalse(info.to_dict()["dolphin_loadable"])

    def test_require_aligned_flag(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".dol", delete=False) as f:
            f.write(self.img)
            path = f.name
        try:
            self.assertEqual(dolinfo.main(["--require-aligned", path]), 1)
        finally:
            os.unlink(path)

    def test_to_dict_and_summary(self):
        info = dolinfo.parse_dol(self.img)
        d = info.to_dict()
        self.assertEqual(d["text_section_count"], 1)
        self.assertEqual(d["data_section_count"], 2)
        self.assertIn("0x80003104", dolinfo.format_summary(info))


class RejectMalformedDol(unittest.TestCase):
    def test_too_short(self):
        with self.assertRaises(dolinfo.DolError):
            dolinfo.parse_dol(b"\0" * (dolinfo.DOL_HEADER_SIZE - 1))

    def test_all_zero_header_has_no_text(self):
        with self.assertRaises(dolinfo.DolError):
            dolinfo.parse_dol(b"\0" * dolinfo.DOL_HEADER_SIZE)

    def test_section_past_eof(self):
        img = make_dol(text=[(0x80003100, b"\0" * 64)])
        with self.assertRaises(dolinfo.DolError):
            dolinfo.parse_dol(img[:-1])

    def test_entry_outside_text(self):
        img = make_dol(text=[(0x80003100, b"\0" * 16)],
                       data=[(0x80004000, b"\0" * 16)], entry=0x80004000)
        with self.assertRaises(dolinfo.DolError):
            dolinfo.parse_dol(img)

    def test_unaligned_entry(self):
        img = make_dol(text=[(0x80003100, b"\0" * 16)], entry=0x80003102)
        with self.assertRaises(dolinfo.DolError):
            dolinfo.parse_dol(img)

    def test_load_address_outside_mem1(self):
        img = make_dol(text=[(0x00003100, b"\0" * 16)])
        with self.assertRaises(dolinfo.DolError):
            dolinfo.parse_dol(img)
        img = make_dol(text=[(0x817FFFF0, b"\0" * 32)])  # crosses 0x81800000
        with self.assertRaises(dolinfo.DolError):
            dolinfo.parse_dol(img)

    def test_section_overlapping_header(self):
        img = bytearray(make_dol(text=[(0x80003100, b"\0" * 16)]))
        struct.pack_into(">I", img, 0x00, 0x80)  # text0 offset inside header
        with self.assertRaises(dolinfo.DolError):
            dolinfo.parse_dol(bytes(img))


class CommandLine(unittest.TestCase):
    def test_json_output(self):
        import json
        import tempfile
        import io
        import contextlib
        img = make_dol(text=[(0x80003100, b"\0" * 16)])
        with tempfile.NamedTemporaryFile(suffix=".dol", delete=False) as f:
            f.write(img)
            path = f.name
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = dolinfo.main(["--json", path])
            self.assertEqual(rc, 0)
            parsed = json.loads(out.getvalue())
            self.assertEqual(parsed["entry_point"], 0x80003100)
        finally:
            os.unlink(path)

    def test_missing_file_is_error(self):
        import io
        import contextlib
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = dolinfo.main(["/nonexistent/x.dol"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
