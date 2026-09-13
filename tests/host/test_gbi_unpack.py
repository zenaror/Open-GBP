"""Synthetic tests for tools/gbi_unpack.py and tools/bin2dol.py."""
import lzma
import os
import struct
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import bin2dol      # noqa: E402
import dolinfo      # noqa: E402
import gbi_unpack   # noqa: E402

KEY = b"Copyright (c) 2026, Extrems' Corner.org\0"


def make_packed_dol(payload_plain: bytes, prefix: bytes = b"libogc-rice r0000.0000000\0\0\0"):
    assert len(KEY) == gbi_unpack.KEY_LEN
    xz = lzma.compress(payload_plain, format=lzma.FORMAT_XZ)
    obf = bytes(b ^ KEY[i % gbi_unpack.KEY_LEN] for i, b in enumerate(xz))
    text = KEY + b"\x60\x00\x00\x00" * 8
    data = prefix + obf
    text_off = 0x100
    data_off = text_off + len(text)
    hdr = bytearray(0x100)
    struct.pack_into(">I", hdr, 0x00, text_off)
    struct.pack_into(">I", hdr, 0x1C, data_off)               # data0 offset (slot 7)
    struct.pack_into(">I", hdr, 0x48, 0x800b6720)
    struct.pack_into(">I", hdr, 0x64, 0x800b8e40)             # data0 address
    struct.pack_into(">I", hdr, 0x90, len(text))
    struct.pack_into(">I", hdr, 0xAC, len(data))              # data0 size
    struct.pack_into(">I", hdr, 0xE0, 0x800b674c)
    return bytes(hdr) + text + data


class GbiUnpack(unittest.TestCase):
    def test_roundtrip(self):
        plain = b"\x48\x00\x00\x20_arg" + bytes(range(256)) * 40
        packed = make_packed_dol(plain)
        out, start, size = gbi_unpack.unpack(packed)
        self.assertEqual(out, plain)
        self.assertEqual(start, 0x100 + len(KEY) + 32 + len(b"libogc-rice r0000.0000000\0\0\0"))

    def test_wrong_key_is_rejected(self):
        plain = b"x" * 100
        packed = bytearray(make_packed_dol(plain))
        packed[0x100:0x109] = b"Notright!"
        with self.assertRaises(ValueError):
            gbi_unpack.unpack(bytes(packed))

    def test_no_payload(self):
        packed = bytearray(make_packed_dol(b"y" * 10))
        # destroy the XZ magic by flipping the first payload byte
        _, start, _ = gbi_unpack.unpack(bytes(packed))
        packed[start] ^= 0xFF
        with self.assertRaises(ValueError):
            gbi_unpack.unpack(bytes(packed))

    def test_cli(self):
        d = tempfile.mkdtemp()
        src, dst = os.path.join(d, "p.dol"), os.path.join(d, "u.bin")
        with open(src, "wb") as f:
            f.write(make_packed_dol(b"payload" * 100))
        self.assertEqual(gbi_unpack.main([src, dst]), 0)
        self.assertEqual(open(dst, "rb").read(), b"payload" * 100)


class Bin2Dol(unittest.TestCase):
    def test_wrap(self):
        d = tempfile.mkdtemp()
        src, dst = os.path.join(d, "img.bin"), os.path.join(d, "img.dol")
        with open(src, "wb") as f:
            f.write(b"\x60\x00\x00\x00" * 9)   # 36 bytes -> padded to 64
        self.assertEqual(bin2dol.main([src, "80003100", dst, "80003104"]), 0)
        info = dolinfo.parse_dol_file(dst)
        self.assertTrue(info.dolphin_loadable)
        t = info.text_sections[0]
        self.assertEqual((t.load_address, t.size, info.entry_point), (0x80003100, 64, 0x80003104))


if __name__ == "__main__":
    unittest.main()
