"""tools/avdump.py: the block sidecar parser against the C serializer (tests/unit/test_gbp_avsvc.c
--dump-log) and against synthetic files built with the Python inverse (never evidence)."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import avdump  # noqa: E402

BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_avsvc")
OUTDIR = os.path.join(ROOT, "build", "tests", "unit")


class AvdumpSynthetic(unittest.TestCase):
    def test_round_trip_and_layout(self):
        audio = bytes((i * 3 + 1) & 0xFF for i in range(0x1000))
        video = bytes((i * 5 + 2) & 0xFF for i in range(0xF00))
        info = {"flags": 0xF, "pending_irq": 0x0500, "drain_mask": 0x0500, "audio_wait_ticks": 384, "video_wait_ticks": 360,
                "audio_dt_ticks": 400, "video_dt_ticks": 380, "tb_hz": 40500000, "test_id": "GBP-AV-SERVICE-001", "build_id": "avsvc-0001",
                "commit": "abc1234-dirty"}
        info["app"] = "gbp-av-service-probe"
        data = avdump.serialize(info, audio, video)
        self.assertEqual(len(data), 0x100 + 0x1000 + 0xF00 + 12)
        self.assertEqual(data[:8], b"OGBPBLK1")
        self.assertEqual(data[-12:-4], b"OGBPEND1")
        self.assertEqual(data[0x08:0x0C], bytes([0, 2, 1, 0]))
        self.assertEqual(data[0x40:0x60], b"GBP-AV-SERVICE-001" + bytes(14))          # the exact identity, zero padded, never truncated
        self.assertEqual(data[0x60:0x80], b"avsvc-0001" + bytes(22))
        self.assertEqual(data[0x80:0xA0], b"gbp-av-service-probe" + bytes(12))
        self.assertEqual(data[0xA0:0xC0], b"abc1234-dirty" + bytes(19))
        self.assertEqual(data[0xC8:0xFC], bytes(52))                                       # reserved, zero
        d = avdump.parse(data)
        self.assertEqual((d["audio"], d["video"]), (audio, video))
        self.assertEqual((d["test_id"], d["build_id"], d["app"], d["commit"]),
                         ("GBP-AV-SERVICE-001", "avsvc-0001", "gbp-av-service-probe", "abc1234-dirty"))
        self.assertEqual(d["version"], 2)
        self.assertEqual((d["pending_irq"], d["drain_mask"], d["audio_len"], d["video_len"], d["tb_hz"]), (0x0500, 0x0500, 0x1000, 0xF00, 40500000))
        self.assertEqual((d["audio_rc"], d["video_rc"], d["audio_index"], d["video_index"]), ("ok", "ok", 8, 1))
        self.assertTrue(d["audio_present"] and d["audio_valid"] and d["video_present"] and d["video_valid"])
        self.assertEqual(d["audio_crc32"], avdump.crc32(audio))
        self.assertEqual(d["trailing_bytes"], 0)
        # audio only / video only / none
        d = avdump.parse(avdump.serialize({"flags": 3, "pending_irq": 0x0400, "drain_mask": 0x0400, "test_id": "T", "build_id": "B"}, audio, b""))
        self.assertEqual((d["audio_len"], d["video_len"], d["video"]), (0x1000, 0, None))
        d = avdump.parse(avdump.serialize({"flags": 12, "test_id": "T", "build_id": "B"}, b"", video))
        self.assertEqual((d["audio"], d["video_len"]), (None, 0xF00))
        d = avdump.parse(avdump.serialize({"test_id": "T", "build_id": "B"}, b"", b""))
        self.assertEqual((d["audio"], d["video"], d["size"], d["app"], d["commit"]), (None, None, 0x100 + 12, "", ""))
        # the identity rule: 31 fits, 32 is an error (never a truncation), required fields non-empty, printable ASCII without spaces
        d = avdump.parse(avdump.serialize({"test_id": "x" * 31, "build_id": "y" * 31, "app": "z" * 31, "commit": "w" * 31}, b"", b""))
        self.assertEqual((d["test_id"], len(d["commit"])), ("x" * 31, 31))
        for bad in ({"test_id": "x" * 32, "build_id": "B"}, {"test_id": "", "build_id": "B"}, {"test_id": "T", "build_id": ""},
                    {"test_id": "with space", "build_id": "B"}, {"test_id": "T", "build_id": "B", "app": "a" * 32}, {"test_id": "caf\u00e9", "build_id": "B"}):
            with self.assertRaises(ValueError):
                avdump.serialize(bad, b"", b"")
        self.assertIn("test_id", str(next(iter([e for e in [self._err({"test_id": "x" * 32, "build_id": "B"})]]))))
        # a failed read stored as left in memory: present, not valid, rc named
        d = avdump.parse(avdump.serialize({"flags": 1, "audio_rc": 1, "test_id": "T", "build_id": "B"}, audio, b""))
        self.assertEqual((d["audio_present"], d["audio_valid"], d["audio_rc"]), (True, False, "timeout"))

    def _err(self, info):
        try:
            avdump.serialize(info, b"", b"")
        except ValueError as e:
            return e
        return None

    def _reseal(self, buf):
        import struct
        struct.pack_into(">I", buf, 0xFC, avdump.crc32(bytes(buf[:0xFC])))
        struct.pack_into(">I", buf, len(buf) - 4, avdump.crc32(bytes(buf[:-12])))
        return buf

    def test_identity_fields_in_files(self):
        base = avdump.serialize({"test_id": "GBP-AV-SERVICE-001", "build_id": "avsvc-0001", "app": "gbp-av-service-probe", "commit": "5ed9d93"}, b"", b"")
        self.assertEqual(avdump.parse(base)["test_id"], "GBP-AV-SERVICE-001")
        bad = bytearray(base); bad[0x40:0x60] = b"A" * 32                          # no terminator
        with self.assertRaisesRegex(ValueError, "^-8"):
            avdump.parse(self._reseal(bad))
        bad = bytearray(base); bad[0x40 + 25] = ord("Z")                            # non-zero padding after the NUL
        with self.assertRaisesRegex(ValueError, "^-8"):
            avdump.parse(self._reseal(bad))
        bad = bytearray(base); bad[0x62] = ord(" ")                                 # a space inside build_id
        with self.assertRaisesRegex(ValueError, "^-8"):
            avdump.parse(self._reseal(bad))
        bad = bytearray(base); bad[0x60:0x80] = bytes(32)                           # required field empty
        with self.assertRaisesRegex(ValueError, "^-8"):
            avdump.parse(self._reseal(bad))
        bad = bytearray(base); bad[0xA0:0xC0] = bytes(32)                           # optional field empty: fine
        self.assertEqual(avdump.parse(self._reseal(bad))["commit"], "")
        bad = bytearray(base); bad[0xD0] = 1                                        # reserved bytes must be zero
        with self.assertRaisesRegex(ValueError, "^-8"):
            avdump.parse(self._reseal(bad))
        bad = bytearray(base); bad[9] = 1                                           # the pre-release layout is refused
        with self.assertRaisesRegex(ValueError, "^-2"):
            avdump.parse(self._reseal(bad))

    def test_error_codes(self):
        audio = bytes(range(256)) * 16
        data = bytearray(avdump.serialize({"flags": 3, "test_id": "T", "build_id": "B"}, audio, b""))
        with self.assertRaisesRegex(ValueError, "^-1"):
            avdump.parse(data[:20])
        bad = bytearray(data); bad[0] ^= 1
        with self.assertRaisesRegex(ValueError, "^-1"):
            avdump.parse(bad)
        bad = bytearray(data); bad[9] = 3
        with self.assertRaisesRegex(ValueError, "^-2"):
            avdump.parse(bad)
        bad = bytearray(data); bad[0x12] ^= 0x40
        with self.assertRaisesRegex(ValueError, "^-3"):
            avdump.parse(bad)
        with self.assertRaisesRegex(ValueError, "^-4"):
            avdump.parse(data[:-1])
        bad = bytearray(data); bad[-12] ^= 1
        with self.assertRaisesRegex(ValueError, "^-5"):
            avdump.parse(bad)
        bad = bytearray(data); bad[-1] ^= 1
        with self.assertRaisesRegex(ValueError, "^-6"):
            avdump.parse(bad)
        bad = bytearray(data); bad[0x100 + 3] ^= 0xFF
        import struct
        struct.pack_into(">I", bad, len(bad) - 4, avdump.crc32(bytes(bad[:-12])))
        with self.assertRaisesRegex(ValueError, "^-7"):
            avdump.parse(bad)

    def test_cli(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x-blocks.bin")
        with open(p, "wb") as f:
            f.write(avdump.serialize({"flags": 0xF, "pending_irq": 0x0500, "test_id": "GBP-AV-SERVICE-001", "build_id": "avsvc-0001", "app": "gbp-av-service-probe"},
                                     b"\x80\x80\x00\x00" + bytes(0x1000 - 4), bytes(0xF00)))
        self.assertEqual(avdump.main(["info", p]), 0)
        self.assertEqual(avdump.main(["json", p]), 0)
        self.assertEqual(avdump.main(["extract", p, os.path.join(d, "out")]), 0)
        self.assertEqual(os.path.getsize(os.path.join(d, "out", "audio.bin")), 0x1000)
        self.assertEqual(os.path.getsize(os.path.join(d, "out", "video.bin")), 0xF00)
        with open(p, "r+b") as f:
            f.seek(0x100); f.write(b"\x01")
        self.assertEqual(avdump.main(["info", p]), 1)


@unittest.skipUnless(os.path.isfile(BIN), "run `make -C tests/unit` to build the test binary")
class AvdumpAgainstTheCSerializer(unittest.TestCase):
    def test_c_sidecar_parses_and_matches_the_log(self):
        d = OUTDIR if os.path.isdir(OUTDIR) else tempfile.mkdtemp()
        log = os.path.join(d, "avdump-check.log")
        blocks = os.path.join(d, "avdump-check-blocks.bin")
        run = subprocess.run([BIN, "--dump-log", log, blocks], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        line = [l for l in run.stdout.splitlines() if l.startswith("BLOCKS ")][0]
        with open(blocks, "rb") as f:
            raw = f.read()
        info = avdump.parse(raw)
        self.assertIn("audio_crc32=%08x video_crc32=%08x bytes=%d" % (info["audio_crc32"], info["video_crc32"], len(raw)), line)
        self.assertEqual((info["audio_len"], info["video_len"], info["audio_index"], info["video_index"]), (0x1000, 0xF00, 8, 1))
        self.assertEqual((info["test_id"], info["build_id"], info["app"], info["commit"]), ("GBP-AV-SERVICE-001", "synthetic", "gbp-av-service-probe", "none"))
        self.assertEqual(info["tb_hz"], 40500000)
        # the log's BLOCK records carry the same CRCs and windows as the bytes
        import probelog
        _, records = probelog.parse_file(log)
        blk = {r["fields"]["kind"]: r["fields"] for r in records if r["kind"] == "BLOCK"}
        self.assertEqual(blk["audio"]["crc32"], "%08x" % info["audio_crc32"])
        self.assertEqual(blk["video"]["crc32"], "%08x" % info["video_crc32"])
        self.assertEqual(int(blk["audio"]["zeros"]), info["audio"].count(0))
        windows = {(r["fields"]["kind"], int(r["fields"]["off"], 16)): r["fields"]["data"] for r in records if r["kind"] == "BLOCKW"}
        for (kind, off), hx in windows.items():
            self.assertEqual(info[kind][off:off + 32].hex(), hx)
        self.assertEqual(int(blk["video"]["first_word"], 16), int.from_bytes(info["video"][:4], "big"))


PHYSICAL_BLOCKS = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-16-avsvc-0001-blocks.bin")
PHYSICAL_FIXTURE = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-16-avsvc-0001.gbpreplay")


@unittest.skipUnless(os.path.isfile(PHYSICAL_BLOCKS), "physical GBP-AV-SERVICE-001 sidecar missing")
class AvdumpPhysicalSidecar(unittest.TestCase):
    """The block sidecar written by the console on 2026-09-16 (GBP-AV-SERVICE-001, build
    avsvc-0001, commit d3a6d23): a byte-identical copy of GBP-AV-SERVICE-001_avsvc-0001-blocks.bin,
    format version 2, both blocks present and valid, every CRC intact."""

    def setUp(self):
        with open(PHYSICAL_BLOCKS, "rb") as f:
            self.raw = f.read()
        self.info = avdump.parse(self.raw)

    def test_identity_and_hash(self):
        import hashlib
        self.assertEqual(len(self.raw), 8204)
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), "1c17a2d77fa60b4446863032ced62cc3d2390625de2a42b120a195eb074edc1e")
        self.assertEqual(self.raw[:8], b"OGBPBLK1")
        self.assertEqual(self.raw[0x100 + 0x1000 + 0xF00:0x100 + 0x1000 + 0xF00 + 8], b"OGBPEND1")
        i = self.info
        self.assertEqual((i["version"], i["size"], i["trailing_bytes"]), (2, 8204, 0))
        self.assertEqual((i["test_id"], i["build_id"], i["app"], i["commit"]), ("GBP-AV-SERVICE-001", "avsvc-0001", "gbp-av-service-probe", "d3a6d23"))
        self.assertEqual(self.raw[0x40:0x40 + 18], b"GBP-AV-SERVICE-001")       # the 18-character Test ID, whole (format 2)
        self.assertEqual(self.raw[0x40 + 18:0x60], bytes(14))
        with open(PHYSICAL_FIXTURE, encoding="utf-8") as f:
            head = f.read(4096)
        self.assertIn("# BLOCKS=hw-gamecube-gbp-2026-09-16-avsvc-0001-blocks.bin\n", head)
        self.assertIn("# BLOCKS_SHA256=1c17a2d77fa60b4446863032ced62cc3d2390625de2a42b120a195eb074edc1e\n", head)
        self.assertIn("# BLOCKS_SIZE=8204\n", head)

    def test_blocks_and_crcs(self):
        i = self.info
        self.assertEqual((i["flags"], i["pending_irq"], i["drain_mask"]), (0xF, 0x0500, 0x0500))
        self.assertTrue(i["audio_present"] and i["audio_valid"] and i["video_present"] and i["video_valid"])
        self.assertEqual((i["audio_index"], i["audio_len"], i["audio_rc"], i["audio_wait_ticks"], i["audio_dt_ticks"]), (8, 0x1000, "ok", 2475, 2692))
        self.assertEqual((i["video_index"], i["video_len"], i["video_rc"], i["video_wait_ticks"], i["video_dt_ticks"]), (1, 0xF00, "ok", 2319, 2485))
        self.assertEqual(i["tb_hz"], 40500000)
        self.assertEqual((i["audio_crc32"], i["video_crc32"]), (0xFEC5E4E7, 0xFE45FF08))
        self.assertEqual(avdump.crc32(i["audio"]), 0xFEC5E4E7)
        self.assertEqual(avdump.crc32(i["video"]), 0xFE45FF08)
        self.assertEqual((i["header_crc32"], i["total_crc32"]), (0x6174E52D, 0x18E966CF))
        self.assertEqual(avdump.crc32(self.raw[:0xFC]), 0x6174E52D)
        self.assertEqual(avdump.crc32(self.raw[:0x100 + 0x1000 + 0xF00]), 0x18E966CF)     # everything before the footer
        # the fixture's "B" lines carry the same CRCs
        with open(PHYSICAL_FIXTURE, encoding="utf-8") as f:
            b_lines = [l.rstrip("\n") for l in f if l.startswith("B ")]
        self.assertEqual(b_lines, ["B 01800000 00001000 ok fec5e4e7", "B 01100000 00000f00 ok fe45ff08"])

    def test_raw_content_is_recorded_not_interpreted(self):
        audio, video = self.info["audio"], self.info["video"]
        # AUDIO: 3969 zero bytes, three distinct values; the 127 non-zero bytes sit at offset 0 of 123 of the 128
        # 32-byte lines (0x01 in 121, 0x11 in lines 31 and 61; lines 3, 22, 33, 41, 74 all zero) plus four isolated
        # 0x01 at in-line offsets 12, 30, 8, 26 — positions, not a format
        self.assertEqual((audio.count(0), len(set(audio)), sorted(set(audio))), (3969, 3, [0x00, 0x01, 0x11]))
        self.assertEqual(audio[:4], b"\x01\x00\x00\x00")
        line0 = [audio[l * 32] for l in range(128)]
        self.assertEqual((line0.count(0x01), line0.count(0x11), line0.count(0x00)), (121, 2, 5))
        self.assertEqual([l for l in range(128) if line0[l] == 0x11], [31, 61])
        self.assertEqual([l for l in range(128) if line0[l] == 0x00], [3, 22, 33, 41, 74])
        strays = [(i, audio[i]) for i in range(len(audio)) if audio[i] and i % 32]
        self.assertEqual(strays, [(0x8C, 1), (0x49E, 1), (0x8A8, 1), (0xCBA, 1)])
        # VIDEO: no zero byte, two distinct values; 960 four-byte groups: the first ff ff ff ff (GBI frame-start
        # predicate true), 954 × 7f 7f ff ff, five × ff 7f ff ff (groups 41, 165, 186, 426, 578)
        self.assertEqual((video.count(0), sorted(set(video))), (0, [0x7F, 0xFF]))
        groups = [video[i:i + 4] for i in range(0, len(video), 4)]
        self.assertEqual(len(groups), 960)
        self.assertEqual(groups[0], b"\xff\xff\xff\xff")
        self.assertEqual((int.from_bytes(groups[0], "big") & 0x80800000), 0x80800000)
        self.assertEqual(groups.count(b"\x7f\x7f\xff\xff"), 954)
        self.assertEqual([g for g in range(960) if groups[g] == b"\xff\x7f\xff\xff"], [41, 165, 186, 426, 578])
        self.assertEqual(sum(1 for g in groups if g[0] != g[1] or g[2] != g[3]), 5)

    def test_cli_info_on_the_physical_file(self):
        import io
        import contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = avdump.main(["info", PHYSICAL_BLOCKS])
        self.assertEqual(rc, 0)
        text = out.getvalue()
        for needle in ("GBP-AV-SERVICE-001", "avsvc-0001", "d3a6d23", "fec5e4e7", "fe45ff08"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
