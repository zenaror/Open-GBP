"""
tools/avseq.py — the OGBPSEQ1 sequence sidecar of GBP-VIDEO-001 on the host: the parser against
the C serializer, the frame-start predicates, the boundary lists, the reference transform and
GBI's per-block checksum, and the offline content oracle.

The sidecar under test is produced by the C code itself (tests/unit/test_gbp_video.c --dump-log),
so the Python parser is checked against the real writer, not against a Python re-implementation.

The oracle's own algorithm is anchored to PHYSICAL data: the VIDEO block of GBP-AV-SERVICE-001
(2026-09-16, avsvc-0001) has GBI checksum 0x7F0FFF10, which VIDEO_PATH.md §6 records as entry 0
of both of GBI's reference tables. That anchor needs no private input. The comparison against the
references' embedded frame runs only when the private inputs are present under input/extracted/;
without them the verdict is `reference_content=unavailable`, which is never a failure of a run.
"""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import avdump  # noqa: E402
import avseq  # noqa: E402

BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_video")
OUTDIR = os.path.join(ROOT, "build", "tests", "unit")
PHYSICAL_AVSVC_BLOCKS = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-16-avsvc-0001-blocks.bin")


def outdir():
    return OUTDIR if os.path.isdir(OUTDIR) else tempfile.mkdtemp()


def make_sidecar():
    """One synthetic run written by the C code: the log and the sequence sidecar."""
    d = outdir()
    log, seq = os.path.join(d, "avseq-host.log"), os.path.join(d, "avseq-host-seq.bin")
    subprocess.run([BIN, "--dump-log", log, seq], check=True, capture_output=True)
    with open(seq, "rb") as f:
        return f.read(), log, seq


class Predicates(unittest.TestCase):
    """Both frame-start predicates, identical to the C ones; byte 0 alone never decides."""

    def test_predicates(self):
        self.assertEqual((avseq.flag_gbi([0xFF, 0xFF, 0xFF, 0xFF]), avseq.flag_disc([0xFF, 0xFF, 0xFF, 0xFF])), (1, 1))
        self.assertEqual((avseq.flag_gbi([0x7F, 0xFF, 0xFF, 0xFF]), avseq.flag_disc([0x7F, 0xFF, 0xFF, 0xFF])), (0, 1))
        self.assertEqual((avseq.flag_gbi([0xFF, 0x7F, 0xFF, 0xFF]), avseq.flag_disc([0xFF, 0x7F, 0xFF, 0xFF])), (0, 0))
        self.assertEqual((avseq.flag_gbi([0x7F, 0x7F, 0xFF, 0xFF]), avseq.flag_disc([0x7F, 0x7F, 0xFF, 0xFF])), (0, 0))

    def test_gbi_implies_disc(self):
        for a in range(256):
            for b in range(256):
                f4 = [a, b, a ^ b, 0xFF - a]
                if avseq.flag_gbi(f4):
                    self.assertTrue(avseq.flag_disc(f4), (a, b))


@unittest.skipUnless(os.path.isfile(PHYSICAL_AVSVC_BLOCKS), "the physical AVSVC block sidecar is required")
class ChecksumAnchor(unittest.TestCase):
    """GBI's per-block checksum, anchored to the physical block of GBP-AV-SERVICE-001."""

    def setUp(self):
        with open(PHYSICAL_AVSVC_BLOCKS, "rb") as f:
            self.block = avdump.parse(f.read())["video"]

    def test_physical_block_checksum(self):
        # VIDEO_PATH.md §6: the physical block's GBI checksum equals entry 0 of both reference tables
        self.assertEqual(avseq.gbi_block_checksum(self.block), 0x7F0FFF10)

    def test_transform_is_byte1_byte3(self):
        words = avseq.transform_block(self.block, force_bit15=False)
        self.assertEqual(len(words), 960)
        for i in range(8):
            self.assertEqual(words[i], (self.block[i * 4 + 1] << 8) | self.block[i * 4 + 3])
        forced = avseq.transform_block(self.block)
        self.assertTrue(all(w & 0x8000 for w in forced))

    def test_physical_block_predicates(self):
        f4 = list(self.block[:4])
        self.assertEqual((avseq.flag_gbi(f4), avseq.flag_disc(f4)), (1, 1))   # the physical block is a frame start for both


@unittest.skipUnless(os.path.isfile(BIN), "run `make -C tests/unit` to build the unit tests")
class SidecarRoundTrip(unittest.TestCase):
    """The Python parser against the C serializer, on a real synthetic run."""

    @classmethod
    def setUpClass(cls):
        cls.data, cls.log, cls.seq = make_sidecar()
        cls.d = avseq.parse(cls.data)

    def test_header(self):
        d = self.d
        self.assertEqual((d["version"], d["header_size"]), (1, 0x100))
        self.assertEqual((d["test_id"], d["build_id"]), ("GBP-VIDEO-001", "synthetic"))
        self.assertEqual(d["app"], "gbp-video-capture-probe")
        self.assertEqual((d["video_block_size"], d["audio_block_size"]), (0x0F00, 0x1000))
        self.assertEqual((d["cycle_rec"], d["video_rec"], d["audio_rec"]), (96, 48, 32))
        self.assertTrue(d["service_ok"] and d["restore_ok"])
        self.assertEqual(d["capture"], "delivery_cap")
        self.assertEqual(d["target_video_blocks"], 88)
        self.assertEqual(d["max_deliveries"], 320)

    def test_tables_are_contiguous_and_counted(self):
        d = self.d
        self.assertEqual(len(d["cycles"]), d["cycle_count"])
        self.assertEqual(len(d["video"]), d["video_count"])
        self.assertEqual(len(d["audio"]), d["audio_count"])
        self.assertEqual(d["off_cycles"], 0x100)
        self.assertEqual(d["off_footer"] + 12, len(self.data))

    def test_every_cycle_delivered_once(self):
        for c in self.d["cycles"]:
            self.assertTrue(c["admitted"])
            self.assertEqual((c["isr_fired"], c["isr_count"], c["isr_reentry"]), (1, 1, 0))
            self.assertTrue(c["ack_completed"] and c["rearm_completed"])
            self.assertEqual(c["ack_value"], c["pending"] | 0x8000)   # never a partial ACK

    def test_video_blocks_and_predicates(self):
        d = self.d
        for v in d["video"]:
            self.assertTrue(v["completed"])
            self.assertEqual(v["raw_len"], 0x0F00)
            raw = avseq.video_bytes(d, v["seq"])
            self.assertEqual(len(raw), 0x0F00)
            self.assertEqual(avseq.crc32(raw), v["crc32"])
            self.assertEqual(v["flag_gbi"], avseq.flag_gbi(v["raw_first4"]))
            self.assertEqual(v["flag_disc"], avseq.flag_disc(v["raw_first4"]))
            self.assertEqual(list(raw[:4]), v["raw_first4"])

    def test_boundaries_match_the_probe_counts(self):
        d = self.d
        bg, bd = avseq.boundaries(d, "gbi"), avseq.boundaries(d, "disc")
        self.assertEqual(bg["count"], d["boundaries_gbi"])
        self.assertEqual(bd["count"], d["boundaries_disc"])
        self.assertEqual(bg["complete_interval"], bg["count"] >= 2)
        self.assertEqual(bg["intervals"], [bg["positions"][i + 1] - bg["positions"][i] for i in range(bg["count"] - 1)])

    def test_audio_raw_blocks(self):
        d = self.d
        for a in d["audio"]:
            if a["raw_index"] == 0xFFFF:
                self.assertFalse(a["raw_kept"])
                continue
            raw = avseq.audio_bytes(d, a["raw_index"])
            self.assertEqual(len(raw), 0x1000)
            if a["summarized"]:
                self.assertEqual(avseq.crc32(raw), a["crc32"])

    def test_corrupted_files_are_refused(self):
        for mutate, code in (
            (lambda b: b"X" + b[1:], "-1"),
            (lambda b: b[:0x09] + bytes([2]) + b[0x0A:], "-2"),          # the version is checked before the header CRC, as in C
            (lambda b: b[:0x2D] + bytes([95]) + b[0x2E:], "-2"),         # a record size the reader does not know
            (lambda b: b[:0x10] + bytes([b[0x10] ^ 1]) + b[0x11:], "-3"),   # a header byte outside the checked prefix fields
            (lambda b: b[:0xF3] + bytes([1]) + b[0xF4:], "-3"),          # reserved byte set: the header CRC catches it first

            (lambda b: b[:-1], "-4"),
            (lambda b: b[:len(b) - 12] + b"XXXXXXXX" + b[-4:], "-5"),
        ):
            with self.assertRaises(ValueError) as cm:
                avseq.parse(mutate(self.data))
            self.assertTrue(str(cm.exception).startswith(code), (code, str(cm.exception)))

    def test_cli(self):
        for cmd in ("info", "cycles", "video", "audio", "boundaries", "json", "frames"):
            r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "avseq.py"), cmd, self.seq],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, (cmd, r.stderr))
            self.assertTrue(r.stdout.strip(), cmd)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "avseq.py"), "info", self.seq],
                           capture_output=True, text=True)
        self.assertIn("reference_content=unavailable unless", r.stdout)

    def test_extract(self):
        d = tempfile.mkdtemp()
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "avseq.py"), "extract", self.seq, d],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        names = sorted(os.listdir(d))
        self.assertTrue(any(n.startswith("video-") for n in names))
        self.assertTrue(any(n.startswith("audio-") for n in names))
        for n in names:
            size = os.path.getsize(os.path.join(d, n))
            self.assertEqual(size, 0x0F00 if n.startswith("video-") else 0x1000, n)


@unittest.skipUnless(os.path.isfile(BIN), "run `make -C tests/unit` to build the unit tests")
class Oracle(unittest.TestCase):
    """The offline content oracle: never a gate, and explicit when the private inputs are absent."""

    @classmethod
    def setUpClass(cls):
        cls.data, cls.log, cls.seq = make_sidecar()
        cls.d = avseq.parse(cls.data)

    def test_without_private_inputs_the_verdict_is_unavailable(self):
        o = avseq.oracle(self.d, refdir=tempfile.mkdtemp())
        self.assertEqual(o["reference_content"], "unavailable")
        self.assertEqual(o["verdict"], "insufficient_data")
        self.assertFalse(o["disc_available"] or o["gbi_available"])
        self.assertIn("unaffected", o["note"])
        # our own measurement is still reported: it needs no reference
        self.assertEqual(len(o["checksums"]), self.d["video_count"])
        for c in o["checksums"]:
            self.assertRegex(c["gbi_checksum"], r"^[0-9a-f]{8}$")

    def test_boundaries_are_always_reported(self):
        o = avseq.oracle(self.d, refdir=tempfile.mkdtemp())
        for p in ("gbi", "disc"):
            self.assertEqual(o["boundaries_" + p], avseq.boundaries(self.d, p))

    def test_synthetic_blocks_do_not_match_the_references(self):
        # with the private inputs present the comparison runs and reports a mismatch for mock data;
        # a mismatch is evidence, never a failure — and the run's own result is untouched
        ref = avseq._find_reference(None)
        if not ref["available"]:
            self.skipTest("the private reference inputs are not present on this host")
        o = avseq.oracle(self.d)
        self.assertIn(o["reference_content"], ("mismatch", "partial_match", "full_match", "insufficient_data"))
        self.assertEqual(o["blocks_compared"], len([v for v in self.d["video"] if v["completed"]]))

    def test_reference_tables_have_the_documented_shape(self):
        ref = avseq._find_reference(None)
        if not ref["gbi_image"]:
            self.skipTest("the private GBI image is not present on this host")
        ta = avseq._raw_image_read(ref["gbi_image"], avseq.GBI_IMAGE_BASE, avseq.GBI_TABLE_A, 40 * 4)
        tb = avseq._raw_image_read(ref["gbi_image"], avseq.GBI_IMAGE_BASE, avseq.GBI_TABLE_B, 40 * 4)
        self.assertIsNotNone(ta)
        self.assertIsNotNone(tb)
        a = struct.unpack(">40I", ta)
        b = struct.unpack(">40I", tb)
        # VIDEO_PATH.md §3.3: entry 0 of both is the all-white flagged block; table A has content in
        # blocks 14..25 and table B in 12..19. Only the SHAPE is asserted; no table value is stored here.
        self.assertEqual(a[0], 0x7F0FFF10)
        self.assertEqual(b[0], 0x7F0FFF10)
        self.assertEqual([i for i in range(1, 40) if a[i] != a[1]], list(range(14, 26)))
        self.assertEqual([i for i in range(1, 40) if b[i] != b[1]], list(range(12, 20)))


if __name__ == "__main__":
    unittest.main()
