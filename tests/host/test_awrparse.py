"""tests/host/test_awrparse.py -- GitHub Issue #117: tools/awrparse.py, the strict reader of the OGBPAWR1
ride-along capture (src/gbp/gbp_awr.h), against files built here in Python from the DOCUMENTED layout.

No C runs here: the writer below is a second, independent rendering of the header comment in gbp_awr.h, so a
drift between the module and the reader shows up as a disagreement between this writer and the C serializer's
own unit test (tests/unit/test_gbp_awr.c pins the same offsets against the module's bytes). The reader must
accept a well-formed file and REFUSE, with a clear message, every corruption tried: a wrong magic, a wrong
version, a wrong block size, a header CRC that does not match, a reserved byte, a short file, a body that is not
a whole number of blocks, a footer magic, a total CRC that does not match, and counts that contradict each other.
The parsed blocks must be consumable by tools/u012slices.py's decode() as they come.
"""
import os
import struct
import sys
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import awrparse  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frozen  # noqa: E402
import u012slices  # noqa: E402

BLOCK = 4096
TB_HZ = 40500000


def header(fields, reserved=b"\0" * 24, crc=None):
    """The 0x80-byte header from the documented layout; `crc` overrides the computed one."""
    f = dict(version=1, block_size=BLOCK, blocks_stored=0, blocks_cap=640, tb_hz=TB_HZ, state=3,
             t_arm=0, t_first=0, t_last=0, copy_min=0, copy_max=0, copy_sum=0, copy_n=0,
             faults=0, ignored=0, seen=0, seq_first=0, seq_last=0, arm_refused=0)
    f.update(fields)
    h = b"OGBPAWR1"
    h += struct.pack(">IIIIII", f["version"], f["block_size"], f["blocks_stored"], f["blocks_cap"],
                     f["tb_hz"], f["state"])
    h += struct.pack(">QQQ", f["t_arm"], f["t_first"], f["t_last"])
    h += struct.pack(">IIQI", f["copy_min"], f["copy_max"], f["copy_sum"], f["copy_n"])
    h += struct.pack(">IIIIII", f["faults"], f["ignored"], f["seen"], f["seq_first"], f["seq_last"],
                     f["arm_refused"])
    assert len(h) == 0x64, len(h)
    h += reserved
    assert len(h) == 0x7C, len(h)
    if crc is None:
        crc = zlib.crc32(h) & 0xFFFFFFFF
    return h + struct.pack(">I", crc)


def build(blocks, fields=None, reserved=b"\0" * 24, header_crc=None, footer_magic=b"OGBPAWRE", total_crc=None):
    """A whole file: header, the blocks, footer. Counts default to what the blocks imply."""
    f = dict(blocks_stored=len(blocks), seen=len(blocks))
    if blocks:
        f.update(t_arm=1000, t_first=2000, t_last=2000 + 9889 * (len(blocks) - 1), seq_first=70,
                 seq_last=70 + len(blocks) - 1, copy_min=1309, copy_max=1437, copy_n=len(blocks),
                 copy_sum=1380 * len(blocks))
    f.update(fields or {})
    body = header(f, reserved, header_crc) + b"".join(blocks)
    if total_crc is None:
        total_crc = zlib.crc32(body) & 0xFFFFFFFF
    return body + footer_magic + struct.pack(">I", total_crc)


def synthetic_block(seed):
    """4 096 bytes whose sixteen slices carry distinct one-bit counts."""
    out = bytearray()
    for s in range(16):
        v = (seed * 16 + s) & 0xFF
        out += bytes([v]) * 256
    return bytes(out)


class Wellformed(unittest.TestCase):
    def test_three_blocks_come_back_whole_and_in_order(self):
        blocks = [synthetic_block(1), synthetic_block(2), synthetic_block(3)]
        data = build(blocks, dict(blocks_cap=3, state=3))
        h, got = awrparse.parse(data)
        self.assertEqual(got, blocks)
        self.assertEqual(h["blocks_stored"], 3)
        self.assertEqual(h["blocks_cap"], 3)
        self.assertEqual(h["state_name"], "done")
        self.assertEqual(h["tb_hz"], TB_HZ)
        self.assertEqual(h["t_arm"], 1000)
        self.assertEqual(h["t_first"], 2000)
        self.assertEqual(h["t_last"], 2000 + 2 * 9889)
        self.assertEqual((h["seq_first"], h["seq_last"]), (70, 72))
        self.assertEqual((h["copy_min"], h["copy_max"], h["copy_n"], h["copy_sum"]), (1309, 1437, 3, 4140))
        self.assertEqual(h["total_size"], 0x80 + 3 * BLOCK + 12)
        self.assertEqual(h["off_footer"], 0x80 + 3 * BLOCK)
        self.assertEqual(h["header_crc32"], zlib.crc32(data[:0x7C]) & 0xFFFFFFFF)
        self.assertEqual(h["total_crc32"], zlib.crc32(data[:h["off_footer"]]) & 0xFFFFFFFF)
        self.assertIn("blocks 3 of 3", awrparse.describe(h))

    def test_an_empty_capture_is_a_header_and_a_footer(self):
        data = build([], dict(blocks_cap=640, state=3, t_arm=5))
        h, got = awrparse.parse(data)
        self.assertEqual(got, [])
        self.assertEqual(len(data), 0x80 + 12)
        self.assertEqual(h["state_name"], "done")

    def test_an_incomplete_capture_says_so(self):
        data = build([synthetic_block(9)], dict(blocks_cap=640, state=3))
        h, got = awrparse.parse(data)
        self.assertEqual((h["blocks_stored"], h["blocks_cap"]), (1, 640))
        self.assertEqual(len(got), 1)

    def test_a_still_filling_header_is_readable(self):
        data = build([synthetic_block(4), synthetic_block(5)], dict(blocks_cap=3, state=2))
        h, _ = awrparse.parse(data)
        self.assertEqual(h["state_name"], "filling")

    def test_ignored_and_faults_are_read(self):
        data = build([synthetic_block(4)], dict(blocks_cap=3, state=3, seen=7, ignored=4, faults=2, arm_refused=1))
        h, _ = awrparse.parse(data)
        self.assertEqual((h["seen"], h["ignored"], h["faults"], h["arm_refused"]), (7, 4, 2, 1))

    def test_load_reads_a_file_once(self):
        import tempfile
        blocks = [synthetic_block(6)]
        data = build(blocks, dict(blocks_cap=1, state=3))
        with tempfile.NamedTemporaryFile(suffix=".awr", delete=False) as f:
            f.write(data)
            path = f.name
        try:
            h, got = awrparse.load(path)
        finally:
            os.unlink(path)
        self.assertEqual(got, blocks)
        self.assertEqual(h["blocks_stored"], 1)

    def test_the_blocks_feed_u012slices_decode(self):
        blocks = [synthetic_block(1), synthetic_block(2)]
        data = build(blocks, dict(blocks_cap=2, state=3))
        _, got = awrparse.parse(data)
        x = u012slices.decode(got, 8)
        self.assertEqual(len(x), 16)                 # 8 values per block, 2 blocks
        # each pair of slices contributes the one-bit count of its 512 bytes
        expect = []
        for b in blocks:
            for i in range(8):
                expect.append(float(sum(bin(c).count("1") for c in b[i * 512:(i + 1) * 512])))
        self.assertEqual(x, expect)


class Refusals(unittest.TestCase):
    def refuse(self, data, fragment):
        with self.assertRaises(awrparse.AwrError) as cm:
            awrparse.parse(data)
        self.assertIn(fragment, str(cm.exception))

    def good(self):
        return [synthetic_block(1), synthetic_block(2)]

    def test_short_file(self):
        self.refuse(b"OGBPAWR1" + b"\0" * 50, "shorter than a header and a footer")
        self.refuse(b"", "shorter")

    def test_wrong_magic(self):
        data = build(self.good(), dict(blocks_cap=2))
        self.refuse(b"OGBPAW1\0" + data[8:], "magic")

    def test_wrong_version(self):
        self.refuse(build(self.good(), dict(blocks_cap=2, version=2)), "version 2, not 1")

    def test_wrong_block_size(self):
        self.refuse(build(self.good(), dict(blocks_cap=2, block_size=4000)), "block size 4000")

    def test_header_crc(self):
        self.refuse(build(self.good(), dict(blocks_cap=2), header_crc=0x12345678), "header CRC")
        # one flipped byte inside the header, CRC left as written
        data = bytearray(build(self.good(), dict(blocks_cap=2)))
        data[0x18] ^= 0x01
        self.refuse(bytes(data), "header CRC")

    def test_reserved_byte(self):
        self.refuse(build(self.good(), dict(blocks_cap=2), reserved=b"\0" * 23 + b"\x01"), "reserved")

    def test_unknown_state(self):
        self.refuse(build(self.good(), dict(blocks_cap=2, state=4)), "state 4")

    def test_stored_above_cap(self):
        self.refuse(build(self.good(), dict(blocks_cap=1)), "exceeds blocks_cap")

    def test_cap_zero(self):
        self.refuse(build([], dict(blocks_cap=0)), "blocks_cap is 0")

    def test_state_contradicts_counts(self):
        self.refuse(build(self.good(), dict(blocks_cap=2, state=0)), "idle with blocks")
        self.refuse(build(self.good(), dict(blocks_cap=3, state=1)), "armed (never filling)")
        self.refuse(build([], dict(blocks_cap=3, state=2)), "filling with no block")
        self.refuse(build(self.good(), dict(blocks_cap=2, state=2)), "filling with a full store")

    def test_instants_contradict(self):
        self.refuse(build([], dict(blocks_cap=3, state=3, t_first=5)), "no block stored but")
        self.refuse(build(self.good(), dict(blocks_cap=2, t_first=50, t_last=40)), "t_last 40 before t_first 50")

    def test_seen_does_not_add_up(self):
        self.refuse(build(self.good(), dict(blocks_cap=2, seen=5)), "!= seen 5")

    def test_copy_statistics(self):
        self.refuse(build(self.good(), dict(blocks_cap=2, copy_n=0, copy_min=1)), "copy_n 0")
        self.refuse(build(self.good(), dict(blocks_cap=2, copy_min=2000, copy_max=1000)), "copy_min")
        self.refuse(build(self.good(), dict(blocks_cap=2, copy_sum=1)), "copy_sum")

    def test_body_is_not_whole_blocks(self):
        data = build(self.good(), dict(blocks_cap=2))
        # drop one byte from the body and reseal nothing: the size check fires first
        self.refuse(data[:0x80 + BLOCK] + data[0x80 + BLOCK + 1:], "bytes between header and footer")

    def test_blocks_stored_disagrees_with_the_bytes(self):
        self.refuse(build(self.good(), dict(blocks_cap=3, blocks_stored=1, seen=1)), "bytes between header and footer")
        self.refuse(build(self.good(), dict(blocks_cap=3, blocks_stored=3, seen=3)), "bytes between header and footer")

    def test_footer_magic(self):
        self.refuse(build(self.good(), dict(blocks_cap=2), footer_magic=b"OGBPAWND"), "footer magic")

    def test_total_crc(self):
        self.refuse(build(self.good(), dict(blocks_cap=2), total_crc=0), "total CRC")
        # one flipped byte inside a block, footer left as written
        data = bytearray(build(self.good(), dict(blocks_cap=2)))
        data[0x80 + BLOCK + 100] ^= 0x80
        self.refuse(bytes(data), "total CRC")

    def test_truncated_file(self):
        data = build(self.good(), dict(blocks_cap=2))
        self.refuse(data[:-1], "bytes between header and footer")
        self.refuse(data[:0x80 + BLOCK], "bytes between header and footer")

    def test_not_bytes(self):
        self.refuse("OGBPAWR1", "not bytes")


class Constants(unittest.TestCase):
    def test_the_reader_pins_the_contract(self):
        self.assertEqual(awrparse.MAGIC, b"OGBPAWR1")
        self.assertEqual(awrparse.END, b"OGBPAWRE")
        self.assertEqual(awrparse.HEADER_SIZE, 0x80)
        self.assertEqual(awrparse.FOOTER_SIZE, 12)
        self.assertEqual(awrparse.BLOCK_SIZE, 4096)
        self.assertEqual(awrparse.VERSION, 1)
        self.assertEqual(awrparse.crc32(b"123456789"), 0xCBF43926)   # gbp_crc32's own vector

    def test_the_header_comment_of_the_c_module_names_the_same_offsets(self):
        src = open(os.path.join(ROOT, "src", "gbp", "gbp_awr.h")).read()
        for name, off, _ in awrparse.FIELDS:
            if name == "header_crc32":
                continue
            self.assertRegex(src, r"0x%02X\s+%s\b" % (off, name), name)
        self.assertIn('#define GBP_AWR_HEADER_SIZE   0x80u', src)
        self.assertIn('#define GBP_AWR_FOOTER_SIZE   12u', src)
        self.assertIn('#define GBP_AWR_MAGIC         "OGBPAWR1"', src)
        self.assertIn('#define GBP_AWR_END           "OGBPAWRE"', src)



class TheParserIsNotEditedAfterTheImage(unittest.TestCase):
    """Frozen with the image, before any run: the container's parser is byte-identical to its commit."""
    KEY = "Issue #117 -- gbp_awr, the raw AUDIO blocks ridden along"

    def test_the_tool_is_byte_identical_to_its_freeze(self):
        then = frozen.source(self.KEY, "tools/awrparse.py")
        then = then.decode("utf-8") if isinstance(then, bytes) else then
        with open(os.path.join(ROOT, "tools", "awrparse.py"), encoding="utf-8") as f:
            self.assertEqual(then, f.read())

if __name__ == "__main__":
    unittest.main()
