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
PHYSICAL_V2 = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-16-vstate-0001-vstate.bin")
PHYSICAL_V3 = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-17-vstate-0002-vstate.bin")
VIDEO_BIN = os.path.join(ROOT, "build", "tests", "unit", "test_gbp_video")
OUTDIR = os.path.join(ROOT, "build", "tests", "unit")

_CACHE = {}


def outdir():
    return OUTDIR if os.path.isdir(OUTDIR) else tempfile.mkdtemp()


def diag_bytes():
    """A SYNTHETIC v3 file carrying a disagreement, written by the C serializer."""
    if "diag" not in _CACHE:
        path = os.path.join(outdir(), "vstate-host-diag.bin")
        subprocess.run([BIN, "--dump-diag", path], check=True, capture_output=True)
        with open(path, "rb") as f:
            _CACHE["diag"] = f.read()
        _CACHE["diag_path"] = path
    return _CACHE["diag"]


def distinct_bytes():
    """A SYNTHETIC v3 file whose diagnostic holds 32 DISTINCT bytes, written by the C serializer:
    any transposition, truncation or normalisation on the way here would show."""
    if "distinct" not in _CACHE:
        path = os.path.join(outdir(), "vstate-host-diag-distinct.bin")
        subprocess.run([BIN, "--dump-diag-distinct", path], check=True, capture_output=True)
        with open(path, "rb") as f:
            _CACHE["distinct"] = f.read()
        _CACHE["distinct_path"] = path
    return _CACHE["distinct"]


def _refix(b, off_footer):
    """Recomputes both CRCs so that ONLY the structural rules can reject the tampered file."""
    b[0x1FC:0x200] = struct.pack(">I", vstate.crc32(bytes(b[:0x1FC])))
    b[off_footer + 8:off_footer + 12] = struct.pack(">I", vstate.crc32(bytes(b[:off_footer])))
    return bytes(b)


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
        """vstate-0003 writes format 4; the physical vstate-0001 and vstate-0002 files stay 2 and 3."""
        self.assertEqual(self.d["version"], 4)
        self.assertEqual(self.d["header_size"], 0x200)
        self.assertEqual(self.d["test_id"], "GBP-VIDEO-002")
        self.assertEqual(self.d["build_id"], "vstate-0003")
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
        self.assertEqual(d["off_semantic"], d["off_cycles"] + d["cycle_count"] * 128)
        self.assertEqual(d["off_diag"], d["off_semantic"] + 1024)
        self.assertEqual(d["off_video_raw"], d["off_diag"] + d["diag_count"] * 160)
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

    def test_the_formats_never_misread_each_other(self):
        """A GBP-VIDEO-001 sidecar is format 1 with a 0x100 header; this parser must refuse it, and
        avseq must refuse a format 2 or 3 file. Every parser checks version and header size first."""
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
        self.assertIn("OGBPSEQ1 v4", self.run_cmd("info"))
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


@unittest.skipUnless(os.path.isfile(BIN), "build the unit tests first")
class DiagnosticV4(unittest.TestCase):
    """Format 4 carries every preserved disagreement and the aggregate block. Every file here is
    SYNTHETIC. The frozen physical v2 and v3 files are covered by their own classes below."""

    def setUp(self):
        self.d = vstate.parse(diag_bytes())

    def test_it_is_version_4_with_the_block_and_the_array(self):
        self.assertEqual(self.d["version"], 4)
        self.assertEqual(self.d["diag_count"], 1)
        self.assertEqual(self.d["diag_rec_size"], 160)
        self.assertEqual(self.d["semantic_size"], 1024)
        self.assertIsNotNone(self.d["diag"])
        self.assertIsNotNone(self.d["semantic"])
        self.assertEqual(self.d["off_semantic"], self.d["off_cycles"] + self.d["cycle_count"] * 128)
        self.assertEqual(self.d["off_diag"], self.d["off_semantic"] + 1024)
        self.assertEqual(self.d["off_video_raw"], self.d["off_diag"] + 160)

    def test_the_record_carries_the_policy_fields(self):
        g = self.d["diags"][0]
        self.assertIn(g["classification"], ("source_serviced", "source_other", "non_source"))
        self.assertEqual(g["delta"], g["disc_value"] ^ g["gbi_value"])
        self.assertEqual(g["disc_extra_sources"],
                         (g["disc_value"] & 0x0555) & ~(g["gbi_value"] & 0x0555))
        self.assertEqual(g["majority_extra_sources"],
                         (g["gbi_value"] & 0x0555) & ~(g["disc_value"] & 0x0555))
        self.assertNotEqual(g["followup_state"], "pending")   # never serialized

    def test_the_aggregate_block(self):
        m = self.d["semantic"]
        self.assertEqual(m["disagreements_total"], 1)
        self.assertEqual(m["diagnostics_preserved"], 1)
        self.assertFalse(m["store_capped"])
        self.assertEqual(len(m["gaps"]), 6)
        self.assertEqual([g["source"] for g in m["gaps"]], [1, 4, 16, 64, 256, 1024])
        self.assertEqual(len(m["delta_hist"]), 64)
        self.assertEqual(m["delta_hist"][vstate.hist_index(self.d["diags"][0]["delta"])], 1)

    def test_the_histogram_index_is_the_documented_one(self):
        self.assertEqual([vstate.hist_index(v) for v in (0, 1, 4, 16, 64, 0x100, 0x400, 0x500)],
                         [0, 1, 2, 4, 8, 16, 32, 48])
        self.assertEqual(sorted(vstate.hist_index(sum((1 << (2 * k)) for k in range(6) if i >> k & 1))
                                for i in range(64)), list(range(64)))

    def test_the_raw_window_is_thirty_two_bytes(self):
        self.assertEqual(len(self.d["diag"]["raw"]), 32)

    def test_the_stored_values_are_what_the_bytes_recompute_to(self):
        """The whole point: the serializer must agree with the decision the runtime took."""
        e = vstate.explain_diag(self.d["diag"])
        self.assertTrue(e["consistent"], e)
        self.assertEqual(e["recomputed_disc"], self.d["diag"]["disc_value"])
        self.assertEqual(e["recomputed_gbi"], self.d["diag"]["gbi_value"])
        self.assertNotEqual(e["recomputed_disc"], e["recomputed_gbi"])

    def test_the_explanation_names_the_offending_replica(self):
        e = vstate.explain_diag(self.d["diag"])
        self.assertEqual(e["replicas_differing_low"] + e["replicas_differing_high"], [7])
        self.assertTrue(e["disc_low_differs"] or e["disc_high_differs"])
        self.assertEqual(len(e["replicas"]), 8)
        self.assertEqual(e["discarded_bytes_differing"], [])

    def test_the_two_readings_are_the_runtime_ones(self):
        """Pinned against the C implementation's own behaviour, not re-derived."""
        raw = [0x05, 0x05, 0x00, 0x00] * 8
        self.assertEqual(vstate.read_disc(raw), 0x0500)
        self.assertEqual(vstate.read_gbi(raw), 0x0500)
        bad = list(raw)
        bad[0x1F] ^= 0x01
        self.assertEqual(vstate.read_disc(bad), 0x0501)
        self.assertEqual(vstate.read_gbi(bad), 0x0500)
        # the historical case: only the discarded bytes move
        hist = list(raw)
        for k in range(8):
            hist[4 * k] ^= 0x80
            hist[4 * k + 2] ^= 0x5A
        self.assertEqual(vstate.read_disc(hist), vstate.read_gbi(hist))
        # the vote is bitwise, and a tie resolves to 0
        tie = [0] * 32
        for k in range(4):
            tie[4 * k + 3] = 0x0F
        self.assertEqual(vstate.read_gbi(tie), 0x0000)
        five = [0] * 32
        for k in range(5):
            five[4 * k + 3] = 0x0F
        self.assertEqual(vstate.read_gbi(five), 0x000F)

    def test_corruption_of_the_diagnostic_is_detected(self):
        data = bytearray(diag_bytes())
        off = self.d["off_diag"]
        undetected = 0
        for k in range(96):
            bad = bytearray(data)
            bad[off + k] ^= 0x01
            try:
                vstate.parse(bytes(bad))
                undetected += 1
            except ValueError:
                pass
        self.assertEqual(undetected, 0)

    def test_the_cli_explains_it(self):
        diag_bytes()
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vstate.py"), "diag",
                            _CACHE["diag_path"]], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("semantic coherence:", r.stdout)
        self.assertIn("record 0:", r.stdout)
        self.assertIn("raw 32 bytes:", r.stdout)
        self.assertIn("asserts no physical cause", r.stdout)
        self.assertNotIn("too fast", r.stdout.lower())


@unittest.skipUnless(os.path.isfile(BIN), "build the unit tests first (make -C tests/unit)")
class DiagnosticIsStrict(unittest.TestCase):
    """What the parser must refuse, and what the tool must notice. Every tampered file here has
    BOTH CRCs recomputed, so a rejection can only come from a structural or semantic rule."""

    def setUp(self):
        self.data = diag_bytes()
        self.d = vstate.parse(self.data)
        self.foot = self.d["off_footer"]

    def _tampered(self, off, packed):
        b = bytearray(self.data)
        b[off:off + len(packed)] = packed
        return _refix(b, self.foot)

    def test_off_diag_may_not_move(self):
        for value in (0, self.d["off_diag"] + 160, self.d["off_diag"] - 160, 0xFFFFFF00):
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(0x1E0, struct.pack(">I", value)))

    def test_the_record_count_is_bounded(self):
        with self.assertRaises(ValueError):
            vstate.parse(self._tampered(0x1E4, struct.pack(">I", 257)))
        with self.assertRaises(ValueError):    # denying the record leaves 160 orphan bytes
            vstate.parse(self._tampered(0x1E4, struct.pack(">I", 0)))

    def test_the_record_size_is_one_hundred_and_sixty(self):
        for value in (0, 96, 159, 161, 12345):
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(0x1E8, struct.pack(">H", value)))

    def test_the_semantic_block_is_exactly_one_kilobyte(self):
        for value in (0, 512, 1023, 1025, 65536):
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(0x1F0, struct.pack(">I", value)))

    def test_the_semantic_block_must_be_where_the_header_says(self):
        for value in (0, self.d["off_semantic"] + 16, 0xFFFFFF00):
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(0x1EC, struct.pack(">I", value)))

    def test_unknown_flag_bits_are_refused(self):
        for bit in (0x0002, 0x8000):
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(0x1EA, struct.pack(">H", bit)))
        for bit in (0x0100, 0x8000):     # record_flags
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(self.d["off_diag"] + 0x6E, struct.pack(">H", bit)))
        for bit in (0x0002, 0x8000):     # the block's own flags
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(self.d["off_semantic"] + 6, struct.pack(">H", bit)))

    def test_invalid_enums_are_refused(self):
        off = self.d["off_diag"]
        for value in (0, 4, 0xFFFF):     # classification
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(off + 0x66, struct.pack(">H", value)))
        for value in (0, 5, 255):        # followup_state, 0 = FU_PENDING
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(off + 0x8C, bytes([value])))
        for value in (5, 255):           # followup_reason
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(off + 0x8D, bytes([value])))
        for value in (0x0010, 0x0001):   # payload_source
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(off + 0x8E, struct.pack(">H", value)))

    def test_the_semantic_block_structure(self):
        off = self.d["off_semantic"]
        with self.assertRaises(ValueError):
            vstate.parse(self._tampered(off, struct.pack(">I", 0)))            # tag
        with self.assertRaises(ValueError):
            vstate.parse(self._tampered(off + 4, struct.pack(">H", 2)))        # block version
        with self.assertRaises(ValueError):
            vstate.parse(self._tampered(off + 0x05C, b"\x01"))                 # reserved
        with self.assertRaises(ValueError):
            vstate.parse(self._tampered(off + 0x070, struct.pack(">H", 2)))    # gap slot bit

    def test_the_records_reserved_words_must_be_zero(self):
        for off in (self.d["off_diag"] + 0x9E, self.d["off_diag"] + 0x9F):
            b = bytearray(self.data)
            b[off] = 0xAB
            with self.assertRaises(ValueError):
                vstate.parse(_refix(b, self.foot))
        off = self.d["off_diag"] + 0x5C
        for k in range(4):
            b = bytearray(self.data)
            b[off + k] = 0xAB
            with self.assertRaises(ValueError):
                vstate.parse(_refix(b, self.foot))

    def test_a_version_nobody_defined_is_refused(self):
        for value in (0, 1, 5, 0xFFFF):
            with self.assertRaises(ValueError):
                vstate.parse(self._tampered(0x008, struct.pack(">H", value)))


@unittest.skipUnless(os.path.isfile(BIN), "build the unit tests first (make -C tests/unit)")
class DiagnosticIsRecomputed(unittest.TestCase):
    """Section 24: the tool must read the BYTES, not the conclusion. A file whose persisted values
    were altered - with both CRCs made valid again - must still be caught."""

    def setUp(self):
        self.data = diag_bytes()
        self.d = vstate.parse(self.data)
        self.foot = self.d["off_footer"]
        self.off = self.d["off_diag"]

    def _altered(self, field_off, value):
        b = bytearray(self.data)
        b[self.off + field_off:self.off + field_off + 2] = struct.pack(">H", value)
        return vstate.parse(_refix(b, self.foot))

    def test_a_tampered_disc_value_is_caught(self):
        d = self._altered(0x10, 0x0500)          # claim the two readings agreed after all
        e = vstate.explain_diag(d["diag"])
        self.assertFalse(e["consistent"])
        self.assertEqual(e["stored_disc"], 0x0500)
        self.assertEqual(e["recomputed_disc"], 0x0501)
        text = vstate.diag_text(d)
        self.assertIn("INCONSISTENT", text)
        self.assertIn("do not use this record", text.lower())

    def test_a_tampered_gbi_value_is_caught(self):
        d = self._altered(0x12, 0x0501)
        e = vstate.explain_diag(d["diag"])
        self.assertFalse(e["consistent"])
        self.assertEqual(e["recomputed_gbi"], 0x0500)

    def test_the_explanation_follows_the_bytes(self):
        """Change a raw byte and the recomputation must move with it, not with the stored value."""
        b = bytearray(self.data)
        b[self.off + 0x18 + 0x1F] ^= 0x01
        d = vstate.parse(_refix(b, self.foot))
        e = vstate.explain_diag(d["diag"])
        self.assertEqual(e["recomputed_disc"], 0x0500)
        self.assertEqual(e["stored_disc"], 0x0501)
        self.assertFalse(e["consistent"])


@unittest.skipUnless(os.path.isfile(BIN), "build the unit tests first (make -C tests/unit)")
class ThirtyTwoDistinctBytes(unittest.TestCase):
    """Section 3: the last leg of the chain. The C side proved transport buffer -> RAM -> sidecar
    -> C parser with 32 distinct bytes; this is the same file arriving in the Python tool."""

    def setUp(self):
        self.d = vstate.parse(distinct_bytes())
        self.expected = [(0x11 + 7 * i) & 0xFF for i in range(32)]

    def test_every_byte_is_where_it_was(self):
        self.assertEqual(len(set(self.expected)), 32)
        self.assertEqual(self.d["diag"]["raw"], self.expected)

    def test_the_readings_are_recomputed_from_those_bytes(self):
        e = vstate.explain_diag(self.d["diag"])
        self.assertTrue(e["consistent"])
        self.assertEqual(e["recomputed_disc"], (self.expected[0x1D] << 8) | self.expected[0x1F])
        # eight replicas all different: the bitwise majority need not be any of them, and is not
        self.assertNotIn("%04x" % e["recomputed_gbi"],
                         [r["consumed"] for r in e["replicas"]])

    def test_the_wide_timestamp_survives(self):
        self.assertEqual(self.d["diag"]["t"], 0x1FFFFFFFF)     # past the 32-bit wrap
        self.assertEqual(self.d["diag"]["read_kind"], "POSTDRAIN")


class MajorityRule(unittest.TestCase):
    """Section 7: the vote, exhaustively. Not a re-implementation check - the same 2048 cases are
    pinned on the C side, and both must give the textbook answer."""

    def test_every_subset_of_the_eight_replicas(self):
        mismatches = 0
        for bit in range(8):
            for subset in range(256):
                values = [(1 << bit) if (subset >> k) & 1 else 0 for k in range(8)]
                popcount = bin(subset).count("1")
                expect = (1 << bit) if popcount > 4 else 0
                if vstate.majority_byte(values) != expect:
                    mismatches += 1
        self.assertEqual(mismatches, 0)

    def test_a_tie_at_four_is_not_a_majority(self):
        self.assertEqual(vstate.majority_byte([0xFF] * 4 + [0x00] * 4), 0x00)
        self.assertEqual(vstate.majority_byte([0xFF] * 5 + [0x00] * 3), 0xFF)

    def test_the_result_need_not_be_any_sample(self):
        samples = [0b011] * 3 + [0b101] * 3 + [0b110] * 2
        self.assertEqual(vstate.majority_byte(samples), 0b111)
        self.assertNotIn(0b111, samples)


@unittest.skipUnless(os.path.isfile(PHYSICAL_V2), "the physical v2 sidecar is not present")
class PhysicalV2IsFrozen(unittest.TestCase):
    """The first physical run's sidecar must keep parsing byte for byte as it did the day it was
    consolidated. Adding format 3 may not move one field of format 2."""

    def setUp(self):
        with open(PHYSICAL_V2, "rb") as f:
            self.data = f.read()
        self.d = vstate.parse(self.data)

    def test_identity_and_version(self):
        self.assertEqual(self.d["version"], 2)
        self.assertEqual(self.d["header_size"], 0x200)
        self.assertEqual(self.d["test_id"], "GBP-VIDEO-002")
        self.assertEqual(self.d["build_id"], "vstate-0001")
        self.assertEqual(self.d["commit"], "e8f3a69")

    def test_the_counts_and_crcs_are_unchanged(self):
        self.assertEqual(self.d["frame_count"], 489)
        self.assertEqual(self.d["event_count"], 209)
        self.assertEqual(self.d["episode_count"], 4)
        self.assertEqual(self.d["cycle_count"], 81)
        self.assertEqual(self.d["video_raw_frames"], 15)
        self.assertEqual(self.d["audio_raw_count"], 2)
        self.assertEqual(self.d["header_crc32"], 0x947083C4)
        self.assertEqual(self.d["total_crc32"], 0x9BEF714B)
        self.assertEqual(len(self.data), 2432396)

    def test_v2_has_no_diagnostic_and_says_so(self):
        self.assertEqual(self.d["diag_count"], 0)
        self.assertIsNone(self.d["diag"])
        text = vstate.diag_text(self.d)
        self.assertIn("format 2", text)
        self.assertIn("did NOT preserve the bytes", text)
        self.assertIn("U-GBP-032", text)

    def test_v2_reserved_area_must_stay_zero(self):
        bad = bytearray(self.data)
        bad[0x1E0] = 1
        with self.assertRaises(ValueError):
            vstate.parse(bytes(bad))          # caught by the header CRC first, and by the rule after

    def test_an_unknown_version_is_refused(self):
        for v in (0, 1, 4, 99):
            bad = bytearray(self.data)
            struct.pack_into(">H", bad, 0x008, v)
            with self.assertRaises(ValueError):
                vstate.parse(bytes(bad))


@unittest.skipUnless(os.path.isfile(PHYSICAL_V3), "the physical v3 sidecar is not present")
class PhysicalV3(unittest.TestCase):
    """The second physical GBP-VIDEO-002 run (build vstate-0002, 2026-09-17). This is the FIRST
    physical file of the family that carries a semantic-disagreement diagnostic, and the first
    physical evidence of what the eight replicas held when the two readings disagreed. Everything
    asserted here is recomputed from the bytes on disk; nothing is taken from the run's own
    summary."""

    def setUp(self):
        with open(PHYSICAL_V3, "rb") as f:
            self.data = f.read()
        self.d = vstate.parse(self.data)

    def test_identity_and_integrity(self):
        self.assertEqual(len(self.data), 12588)
        self.assertEqual(self.d["version"], 3)
        self.assertEqual(self.d["header_size"], 0x200)
        self.assertEqual(self.d["test_id"], "GBP-VIDEO-002")
        self.assertEqual(self.d["build_id"], "vstate-0002")
        self.assertEqual(self.d["commit"], "8cbb28d")
        self.assertEqual(self.d["header_crc32"], 0xBD2A5F27)
        self.assertEqual(self.d["total_crc32"], 0x08514BAA)

    def test_the_sections_are_where_the_header_says(self):
        d = self.d
        self.assertEqual(d["off_frames"], 512)
        self.assertEqual(d["off_events"], d["off_frames"] + d["frame_count"] * 192)
        self.assertEqual(d["off_episodes"], d["off_events"] + d["event_count"] * 64)
        self.assertEqual(d["off_cycles"], d["off_episodes"] + d["episode_count"] * 512)
        self.assertEqual(d["off_diag"], d["off_cycles"] + d["cycle_count"] * 128)
        self.assertEqual(d["off_diag"], 0x10C0)
        self.assertEqual(d["off_video_raw"], d["off_diag"] + 96)
        self.assertEqual(d["off_footer"] + 12, len(self.data))
        self.assertEqual((d["frame_count"], d["event_count"], d["episode_count"], d["cycle_count"]),
                         (5, 10, 0, 17))

    def test_the_diagnostic_is_the_one_the_run_reported(self):
        g = self.d["diag"]
        self.assertEqual(self.d["diag_count"], 1)
        self.assertEqual(g["cycle"], 517)
        self.assertEqual(g["valid"], 1)
        self.assertEqual(g["attempts"], 1)
        self.assertEqual(g["read_kind"], "READ")
        self.assertEqual(g["disc_value"], 0x0500)
        self.assertEqual(g["gbi_value"], 0x0100)
        self.assertEqual(g["frame_index"], 5)
        self.assertEqual(g["block_in_frame"], 5)
        self.assertEqual(g["latency_ticks"], 35)
        self.assertEqual((g["xfer_ticks"], g["xfer_polls"]), (34, 9))
        self.assertEqual((g["dma_status_before"], g["dma_status"]), (0x0804, 0x0804))
        self.assertEqual(g["intsr_entry"], 0x00012000)
        self.assertEqual(g["intsr_after_w1c"], 0x00010000)
        self.assertEqual(g["intmr_entry"], 0x000021FA)
        self.assertEqual(g["control_exp"], 0x8C)

    def test_the_thirty_two_bytes(self):
        raw = self.d["diag"]["raw"]
        self.assertEqual(bytes(raw).hex(),
                         "0101010001010100010101000101010001010100010101000101010005050500")

    def test_seven_replicas_say_video_and_the_eighth_says_video_plus_audio(self):
        raw = self.d["diag"]["raw"]
        semantic = [(raw[4 * k + 1] << 8) | raw[4 * k + 3] for k in range(8)]
        self.assertEqual(semantic, [0x0100] * 7 + [0x0500])
        # and the eighth group is internally coherent, not a mangled copy: its first three bytes
        # move together, exactly as the first three of every other group do
        self.assertEqual(list(raw[28:32]), [0x05, 0x05, 0x05, 0x00])
        for k in range(7):
            self.assertEqual(list(raw[4 * k:4 * k + 4]), [0x01, 0x01, 0x01, 0x00])

    def test_both_readings_recompute_to_what_the_runtime_stored(self):
        e = vstate.explain_diag(self.d["diag"])
        self.assertTrue(e["consistent"], e)
        self.assertEqual(e["recomputed_disc"], 0x0500)
        self.assertEqual(e["recomputed_gbi"], 0x0100)
        self.assertEqual(e["differing_bits"], 0x0400)      # exactly the AUDIO source bit
        self.assertEqual(e["replicas_differing_high"], [7])
        self.assertEqual(e["replicas_differing_low"], [])
        self.assertTrue(e["disc_high_differs"])

    def test_the_tool_explains_it_without_asserting_a_cause(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "vstate.py"), "diag",
                            PHYSICAL_V3], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("semantic disagreement at cycle 517", r.stdout)
        self.assertIn("CONSUMED byte", r.stdout)
        self.assertIn("asserts no physical cause", r.stdout)

    def test_this_run_observed_no_structured_state_and_claims_none(self):
        """The abort came at 0.084 s; vstate-0001's screen first appeared at 0.5014 s. This file
        must not be read as contradicting that run - it stopped before the interesting window."""
        self.assertEqual(self.d["episode_count"], 0)
        self.assertEqual(self.d["frame_count"], 5)
        self.assertLess(self.d["capture_elapsed"] / self.d["tb_hz"], 0.2)

if __name__ == "__main__":
    unittest.main()
