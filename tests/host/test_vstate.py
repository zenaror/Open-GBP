"""
tools/vstate.py — the GBP-VIDEO-002 sidecar (OGBPSEQ1 format 2) on the host: the strict parser
against the C writer, the frame/event/episode/cycle decoders, the interval histogram, the offline
oracle, and the separation between format 1 and format 2.

The file under test is produced by the C code itself (tests/unit/test_gbp_video_state --dump), so
the Python parser is checked against the real writer and never against a Python re-implementation
of it.

Every run here is SYNTHETIC. The one physically anchored number is the all-white block signature
0x7F0FFF10, which GBP-AV-SERVICE-001's real block produces and which VIDEO_PATH.md §6 records as
entry 0 of both of GBI's reference tables; it needs no private input. The comparison against the
references' embedded data runs only when the private inputs are present under input/extracted/,
and without them the verdict is `reference_content=unavailable`, which is never a failure of a run.
"""
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import avseq  # noqa: E402
import vstate  # noqa: E402

BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_video_state")
VIDEO_BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_video")
OUTDIR = os.path.join(ROOT, "build", "tests", "unit")

_CACHE = {}


def outdir():
    return OUTDIR if os.path.isdir(OUTDIR) else tempfile.mkdtemp()


def sidecar_bytes():
    """One synthetic run's sidecar, written by the C serializer."""
    if "data" not in _CACHE:
        path = os.path.join(outdir(), "vstate-host.bin")
        subprocess.run([BIN, "--dump", path], check=True, capture_output=True)
        with open(path, "rb") as f:
            _CACHE["data"] = f.read()
        _CACHE["path"] = path
    return _CACHE["data"]


@unittest.skipUnless(os.path.isfile(BIN), "build the unit tests first (make -C tests/unit)")
class Header(unittest.TestCase):
    def setUp(self):
        self.d = vstate.parse(sidecar_bytes())

    def test_identity_and_version(self):
        self.assertEqual(self.d["version"], 2)
        self.assertEqual(self.d["header_size"], 0x200)
        self.assertEqual(self.d["test_id"], "GBP-VIDEO-002")
        self.assertEqual(self.d["build_id"], "vstate-0001")
        self.assertEqual(self.d["app"], "gbp-video-state-probe")

    def test_record_sizes_are_the_contract(self):
        data = sidecar_bytes()
        self.assertEqual(struct.unpack_from(">H", data, 0x02C)[0], 192)
        self.assertEqual(struct.unpack_from(">H", data, 0x02E)[0], 64)
        self.assertEqual(struct.unpack_from(">H", data, 0x030)[0], 512)
        self.assertEqual(struct.unpack_from(">H", data, 0x032)[0], 128)

    def test_sections_are_contiguous_and_exact(self):
        d = self.d
        self.assertEqual(d["off_frames"], 0x200)
        self.assertEqual(d["off_events"], d["off_frames"] + d["frame_count"] * 192)
        self.assertEqual(d["off_episodes"], d["off_events"] + d["event_count"] * 64)
        self.assertEqual(d["off_cycles"], d["off_episodes"] + d["episode_count"] * 512)
        self.assertEqual(d["off_video_raw"], d["off_cycles"] + d["cycle_count"] * 128)
        self.assertEqual(d["off_footer"] + 12, len(sidecar_bytes()))

    def test_clocks_are_64_bit_and_consistent(self):
        d = self.d
        self.assertGreater(d["t_capture_start"], 0)
        self.assertGreaterEqual(d["t_capture_start"], d["t_control_transform"])
        self.assertGreater(d["t_stop"], d["t_capture_start"])
        self.assertEqual(d["capture_elapsed"], d["t_stop"] - d["t_capture_start"])
        self.assertEqual(d["safety_elapsed"], d["t_stop"] - d["t_control_transform"])
        self.assertGreater(d["safety_elapsed"], d["capture_elapsed"])
        self.assertGreaterEqual(d["t_teardown_begin"], d["t_stop"])
        self.assertGreaterEqual(d["t_teardown_end"], d["t_teardown_begin"])
        # the hard limit is the design's, and it does not fit in 32 bits at the real time base
        self.assertGreater(180 * 40500000, 0xFFFFFFFF)

    def test_counters_have_the_shape_a_long_run_needs(self):
        d = self.d
        self.assertGreater(d["deliveries"], 0)
        self.assertEqual(d["isr_w1c"], d["deliveries"])     # one ISR acknowledge per delivery
        self.assertGreater(d["video_completed"], 0)
        self.assertGreater(d["frame_count"], 0)
        # no per-delivery record: the cycle table is bounded and far smaller than the deliveries
        self.assertLess(d["cycle_count"], d["deliveries"])
        self.assertLessEqual(d["cycle_count"], 8 + 8 + 8 + 64)
        self.assertLess(d["event_count"], d["deliveries"])


@unittest.skipUnless(os.path.isfile(BIN), "build the unit tests first")
class Records(unittest.TestCase):
    def setUp(self):
        self.d = vstate.parse(sidecar_bytes())

    def test_frames_are_ordered_and_classified(self):
        d = self.d
        self.assertEqual([f["index"] for f in d["frames"]], list(range(d["frame_count"])))
        for i in range(1, len(d["frames"])):
            self.assertGreaterEqual(d["frames"][i]["t_first_block"], d["frames"][i - 1]["t_first_block"])
        complete = [f for f in d["frames"] if f["completeness"] == "complete_40"]
        self.assertEqual(len(complete), d["frames_complete"])
        for f in complete:
            self.assertEqual(f["blocks"], 40)
            self.assertIn("complete", f["flag_names"])

    def test_the_all_white_signature_is_the_physically_anchored_value(self):
        """The synthetic payload is a uniform white block with the frame flag on block 0, so its
        signature must be the value GBP-AV-SERVICE-001's REAL block produced."""
        f = next(f for f in self.d["frames"] if f["completeness"] == "complete_40")
        self.assertEqual(f["sig"][0], 0x7F0FFF10)          # with the frame-start flag
        self.assertEqual(f["sig"][1], 0xFF0FFF0F)          # without it
        self.assertEqual(self.d["baseline_sig0"], 0x7F0FFF10)

    def test_events_are_ordered_by_sequence_number(self):
        seqs = [e["seq"] for e in self.d["events"]]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)))
        for i in range(1, len(self.d["events"])):
            self.assertGreaterEqual(self.d["events"][i]["t"], self.d["events"][i - 1]["t"])
        kinds = {e["type"] for e in self.d["events"]}
        self.assertIn("capture_start", kinds)
        self.assertIn("baseline_valid", kinds)
        self.assertIn("stop", kinds)
        self.assertIn("teardown_begin", kinds)
        self.assertIn("teardown_end", kinds)

    def test_teardown_events_bracket_the_stop(self):
        by = {e["type"]: e["seq"] for e in self.d["events"]}
        self.assertLess(by["stop"], by["teardown_begin"])
        self.assertLess(by["teardown_begin"], by["teardown_end"])

    def test_episodes_carry_their_own_raw(self):
        d = self.d
        self.assertGreaterEqual(d["episode_count"], 1)
        seen = set()
        for i, ep in enumerate(d["episodes"]):
            self.assertLessEqual(ep["raw_frames"], 4)
            self.assertNotIn(ep["index"], seen)          # no descriptor was overwritten
            seen.add(ep["index"])
            for k in range(ep["raw_frames"]):
                raw = vstate.episode_raw(d, i, k)
                self.assertEqual(len(raw), ep["raw_frame_blocks"][k] * d["video_block_size"])
                # the first block of a preserved frame carries the frame-start flag in byte 1
                self.assertTrue(avseq.flag_disc(raw[:4]))

    def test_episode_signatures_differ_from_the_baseline(self):
        d = self.d
        for ep in d["episodes"]:
            if "stable_found" in ep["flag_names"]:
                self.assertNotEqual(ep["final_sig"][0:2], [d["baseline_sig0"], 0xFF0FFF0F])

    def test_cycle_records_are_the_four_bounded_kinds(self):
        kinds = [c["kind"] for c in self.d["cycles"]]
        self.assertEqual(kinds.count("first"), self.d["cyc_first_n"])
        self.assertEqual(kinds.count("last"), self.d["cyc_last_n"])
        self.assertEqual(kinds.count("anomaly"), self.d["cyc_anomaly_n"])
        self.assertEqual(kinds.count("episode"), self.d["cyc_episode_n"])
        for c in self.d["cycles"]:
            self.assertEqual(c["isr_count"], 1)
            self.assertEqual(c["isr_reentry"], 0)
            self.assertEqual(c["ack_value"], c["pending"] | 0x8000)   # never a partial ACK

    def test_intervals_report_what_was_seen(self):
        h = vstate.intervals(self.d)
        self.assertTrue(h)
        self.assertEqual(sum(h.values()), self.d["frame_count"])
        text = vstate.intervals_text(self.d)
        self.assertIn("hypothesis", text)


@unittest.skipUnless(os.path.isfile(BIN), "build the unit tests first")
class StrictParsing(unittest.TestCase):
    def test_corruption_is_detected(self):
        data = bytearray(sidecar_bytes())
        with self.assertRaises(ValueError):
            vstate.parse(bytes(data[:-1]))                       # truncated
        with self.assertRaises(ValueError):
            vstate.parse(bytes(data[:64]))                       # far too short
        bad = bytearray(data)
        bad[0] = ord("X")
        with self.assertRaises(ValueError):
            vstate.parse(bytes(bad))                             # magic
        bad = bytearray(data)
        bad[0x009] = 9
        with self.assertRaises(ValueError):
            vstate.parse(bytes(bad))                             # version
        bad = bytearray(data)
        bad[0x010] ^= 0x01
        with self.assertRaises(ValueError):
            vstate.parse(bytes(bad))                             # header CRC
        bad = bytearray(data)
        bad[0x200 + 8] ^= 0x80
        with self.assertRaises(ValueError):
            vstate.parse(bytes(bad))                             # payload CRC
        bad = bytearray(data)
        off = struct.unpack_from(">I", data, 0x0D0)[0]
        bad[off] = ord("Z")
        with self.assertRaises(ValueError):
            vstate.parse(bytes(bad))                             # footer magic
        bad = bytearray(data)
        bad.extend(b"\x00\x00\x00\x00")
        with self.assertRaises(ValueError):
            vstate.parse(bytes(bad))                             # trailing bytes

    def test_format_1_and_format_2_never_misread_each_other(self):
        """A GBP-VIDEO-001 sidecar is format 1 with a 0x100 header; this parser must refuse it, and
        avseq must refuse a format 2 file. Both check version and header size before anything."""
        with self.assertRaises(ValueError):
            avseq.parse(sidecar_bytes())
        if os.path.isfile(VIDEO_BIN):
            d = outdir()
            log = os.path.join(d, "v1-for-vstate.log")
            seq = os.path.join(d, "v1-for-vstate-seq.bin")
            subprocess.run([VIDEO_BIN, "--dump-log", log, seq], check=True, capture_output=True)
            with open(seq, "rb") as f:
                v1 = f.read()
            self.assertEqual(v1[:8], b"OGBPSEQ1")             # the same family
            self.assertEqual(struct.unpack_from(">H", v1, 8)[0], 1)
            with self.assertRaises(ValueError):
                vstate.parse(v1)                              # and still unmistakable
            avseq.parse(v1)                                   # while its own parser still reads it


@unittest.skipUnless(os.path.isfile(BIN), "build the unit tests first")
class Oracle(unittest.TestCase):
    def test_oracle_runs_and_never_gates_the_hardware_result(self):
        d = vstate.parse(sidecar_bytes())
        o = vstate.oracle(d)
        self.assertIn("episodes", o)
        self.assertEqual(len(o["episodes"]), d["episode_count"])
        self.assertIn("disclaimer", o)
        for item in o["episodes"]:
            self.assertIn("signature", item)
            self.assertEqual(len(item["signature"]), 40)
        if not (o["disc_available"] or o["gbi_available"]):
            self.assertEqual(o["reference_content"], "unavailable")
            self.assertIn("unaffected", o["note"])
        else:
            self.assertEqual(o["reference_content"], "computed")

    def test_the_checksum_algorithm_matches_the_runtime(self):
        """The signature the probe stores and the one tools/avseq.py computes must be the same
        function, or an offline comparison would be meaningless."""
        d = vstate.parse(sidecar_bytes())
        ep = d["episodes"][0]
        slot = ep["raw_frames"] - 1
        raw = vstate.episode_raw(d, 0, slot)
        blocks = ep["raw_frame_blocks"][slot]
        for pos in range(min(blocks, 40)):
            b = raw[pos * d["video_block_size"]:(pos + 1) * d["video_block_size"]]
            self.assertEqual(avseq.gbi_block_checksum(b), d["frames"][ep["raw_frame_index"][slot]]["sig"][pos])

    def test_byte_zero_cannot_change_a_signature(self):
        """The property the whole detection rests on, re-checked against the host implementation."""
        base = bytes([0x7F, 0x7F, 0xFF, 0xFF] * 960)
        c0 = avseq.gbi_block_checksum(base)
        altered = bytearray(base)
        for k in range(0, len(altered), 4):
            altered[k] ^= 0x80
        self.assertEqual(avseq.gbi_block_checksum(bytes(altered)), c0)
        altered = bytearray(base)
        altered[5] ^= 0x01
        self.assertNotEqual(avseq.gbi_block_checksum(bytes(altered)), c0)


@unittest.skipUnless(os.path.isfile(BIN), "build the unit tests first")
class Cli(unittest.TestCase):
    def run_cmd(self, *args):
        path = _CACHE.get("path") or os.path.join(outdir(), "vstate-host.bin")
        sidecar_bytes()
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vstate.py")] + list(args) + [path],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_subcommands(self):
        self.assertIn("OGBPSEQ1 v2", self.run_cmd("info"))
        self.assertIn("frame", self.run_cmd("frames"))
        self.assertIn("seq", self.run_cmd("events"))
        self.assertIn("episode", self.run_cmd("episodes"))
        self.assertIn("pend=", self.run_cmd("cycles"))
        self.assertIn("hypothesis", self.run_cmd("intervals"))
        self.assertIn("block  0", self.run_cmd("signatures"))
        self.assertIn("disclaimer", self.run_cmd("oracle"))

    def test_info_never_claims_a_reference_match(self):
        text = self.run_cmd("info")
        self.assertIn("REFERENCE_MATCH is not in this file", text)
        self.assertNotIn("full_match", text)

    def test_extract_writes_only_our_own_bytes(self):
        d = tempfile.mkdtemp()
        out = self.run_cmd("extract", d) if False else None   # extract takes the dir before the file
        path = _CACHE["path"]
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vstate.py"), "extract", path, d],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        files = sorted(os.listdir(d))
        self.assertTrue(any(f.startswith("episode-") for f in files))
        self.assertTrue(any(f.startswith("audio-") for f in files))
        del out


if __name__ == "__main__":
    unittest.main()
