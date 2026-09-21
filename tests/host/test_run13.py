"""
tests/host/test_run13.py — RUN 13: GBP-VIDEO-007 (physical scanout) and
GBP-VIDEO-008 (full-frame fidelity) on stream-0013 + coord-0002, pre-registered
in HARDWARE_TESTS §V6.24 (Issue #14), executed under Hardware Issue #15,
ingested under Issue #16 (result §V6.25). Preserved as fixtures.

Both formal verdicts are PASS, classified by the Orchestrator against the
prospectively frozen §V6.24 gates before the ingestion: the SHARED source-window
gate -- the one RUN 12 failed -- reads OBSERVED_CONTIGUOUS over 2048 intact
records with every one of the 2046 decisive transitions +1; the K = 8 full-frame
samples match the unchanged oracle in all 38 400 words each (CLAIM-A / CLAIM-B
for the eight sampled frames only); the corrected tools/vvi.py (GBP-VID-035
repaired, §V6.21, used PROSPECTIVELY here) derives L = 40 / 40 / 39 / 40 and the
operator saw 1, 2, 3, 4 in order through the declared chain (CLAIM-D only, no
exact-frame binding, no pixel claim). The one R_3 record not in L_3 is
SUPERSEDED in the raw file: instrumentation semantics, never evidence of
physical non-scanout. Every inherited gate is the run-9..12 gate reused; none
added, none narrowed. RUN 12 stays INCONCLUSIVE / INCONCLUSIVE and its fixtures
are pinned untouched here. Nothing derives a topology from a file, and no test
consults the operator's report to decide a machine fact.
"""
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import vdisp  # noqa: E402
import vfull  # noqa: E402
import vqual  # noqa: E402
import vvi  # noqa: E402

FX = os.path.join(ROOT, "captures", "fixtures")
P = "hw-gamecube-gbp-2026-09-21-"
DISP = os.path.join(FX, P + "stream-0013-run13-disp.bin")
FULL = os.path.join(FX, P + "stream-0013-run13-full.bin")
VI = os.path.join(FX, P + "stream-0013-run13-vi.bin")
QUAL = os.path.join(FX, P + "idxcap-run13-qual.bin")
STRUCT = os.path.join(FX, P + "idxcap-run13-struct.json")
RUN12 = os.path.join(FX, "hw-gamecube-gbp-2026-09-20-idxcap-run12-struct.json")
DISP_SHA = "c75e986a320837e6f096e155ff21fe34b0eac3bd4c3e97a5a007c761894c8131"
FULL_SHA = "cb884e272c122a8b8fe1376c2b77ec3162abba96175ce1d8033441d857ae304b"
VI_SHA = "2a772ae07e058bbcd9532d6a4a824eb231d8e9f371ce29380c67a04701bef1b4"
QUAL_SHA = "9b76d3f9ee8508db89292ff580f714419feeb3b0e1c4ab728fdfda7cf09985da"
IDXCAP_SHA = "dcbcfd3e3e1440a3fd4da008286eac03dfe88723e0221aa311ebb88ef18c2280"
LOG_SHA = "4d86ef32562a839dc46f363011f0d4eca1e5bcf4c67e2af5da2fd01af550b49a"
DOL_SHA = "5391c3fe962dc4b2f4e493f3846ac7407ded064c58f5d4bb583a51e5a725dd79"
STIM_SHA = "276ad987c4cd0cefc7d7c532b86a7f5c336cf6603a32509f80f17aac9a56f700"
CANON_SHA = "319dacb759dd2f78b420691a896387b727accf5d9483f152a6a096865c95093f"
TB = 40500000
KEY = vdisp.KEY_NONE
D = {v: k for k, v in vdisp.DISPOSITION.items()}
LF = {v: k for k, v in vdisp.LF}
LO, HI = 356, 2403
SAMPLE_FI = [356 + 256 * i for i in range(8)]
SAMPLE_FID = [52, 308, 564, 820, 1076, 1332, 1588, 1844]
_C = {}


def disp():
    if "d" not in _C:
        _C["d"] = vdisp.load(DISP)
    return _C["d"]


def struct():
    if "s" not in _C:
        with open(STRUCT) as f:
            _C["s"] = json.load(f)
    return _C["s"]


def run12():
    if "r12" not in _C:
        with open(RUN12) as f:
            _C["r12"] = json.load(f)
    return _C["r12"]


def vi():
    if "v" not in _C:
        _C["v"] = vvi.load(VI)
    return _C["v"]


def full_analysis():
    if "fa" not in _C:
        _C["fa"] = vfull.analyse(vfull.load(FULL), use_c=True)
    return _C["fa"]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def pct(s, q):
    n = len(s)
    return s[min(n - 1, int(n * q))] if n else None


def fi_to_fid():
    return {r["frame_index"]: r["frame_id"] for r in struct()["records"]}


class TheArtifactsAndTheDeclarations(unittest.TestCase):
    def test_the_sidecar_fixtures_are_the_physical_files(self):
        self.assertEqual((sha(DISP), os.path.getsize(DISP)), (DISP_SHA, 401396))
        self.assertEqual((sha(FULL), os.path.getsize(FULL)), (FULL_SHA, 1844492))
        self.assertEqual((sha(VI), os.path.getsize(VI)), (VI_SHA, 152396))

    def test_the_qual_projection_names_the_physical_witness_it_came_from(self):
        self.assertEqual(sha(QUAL), QUAL_SHA)
        q = vqual.load(QUAL)
        self.assertEqual((q["records_n"], q["src_size"], q["src_sha256"]), (2048, 8946060, IDXCAP_SHA))
        self.assertEqual([r["frame_index"] for r in q["records"]], list(range(LO, HI + 1)))

    def test_it_is_the_run_12_image_at_7d7a6d8_and_the_coord_0002_delivery_image(self):
        s = struct()
        for i in (disp(), vi(), vfull.load(FULL)):
            self.assertEqual((i["build_id"], i["commit"], i["test_id"]), ("stream-0013", "7d7a6d8", "GBP-VIDEO-004"))
        self.assertEqual((s["dol"]["size"], s["dol"]["sha256"], s["dol"]["commit_full"]),
                         (506496, DOL_SHA, "7d7a6d8acf4e3985034f9ad4f5041fec751181d0"))
        self.assertEqual(s["dol"]["sha256"], run12()["dol"]["sha256"], "the SAME image as RUN 12, not rebuilt")
        self.assertEqual((s["stimulus"]["size"], s["stimulus"]["sha256"], s["stimulus"]["canonical_sha256"]), (3620, STIM_SHA, CANON_SHA))
        self.assertIn("re-flashed", s["stimulus"]["note"])
        self.assertNotEqual(run12()["stimulus"]["sha256"], STIM_SHA, "the stimulus is the designed difference")
        with open(os.path.join(FX, "stimulus-coord-0002-canonical.gba"), "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), CANON_SHA)

    def test_the_raw_identities_are_the_ones_hashed_on_receipt(self):
        raw = struct()["raw"]
        exp = {"log": (87200, LOG_SHA), "idxcap": (8946060, IDXCAP_SHA), "disp": (401396, DISP_SHA),
               "full": (1844492, FULL_SHA), "vi": (152396, VI_SHA)}
        for k, (sz, h) in exp.items():
            self.assertEqual((raw[k]["size"], raw[k]["sha256"]), (sz, h), k)
            self.assertIn("-run13", raw[k]["archived_as"])
            self.assertNotIn("run13", raw[k]["supplied_name"], "the console names carry no run number")
        self.assertEqual(struct()["fixtures"]["qual"]["sha256"], QUAL_SHA)
        r = struct()["raw_receipt"]
        self.assertIn("OVERWROTE RUN 12's raw-drop copies", r["found_at_ingestion"])
        self.assertIn("all five equal the RUN 12 identities", r["run12_preserved"])
        self.assertIn("cp --update=none", r["archived"])

    def test_the_topology_and_the_display_chain_are_the_operators_declaration(self):
        t = struct()["topology_declared_by_operator"]
        self.assertEqual((t["bba_present"], t["ethernet"], t["same_gamecube_as_run12"], t["same_gbp_as_run12"]),
                         ("YES", "DISCONNECTED", "YES", "YES"))
        self.assertIn("OPERATOR", t["source"])
        chain = " ".join(t["display_chain"])
        for item in ("composite / RCA", "RCA-to-HDMI converter", "1080p", "HYDIS HV150UX2", "M.NT68676.2A"):
            self.assertIn(item, chain)
        self.assertEqual(t["display_chain"], run12()["topology_declared_by_operator"]["display_chain"], "RUN 12's chain, held")
        self.assertIn("topology declaration only", t["display_chain_note"])
        self.assertIn("OUTSIDE RUN 13", t["future_morph_2k_paths"])

    def test_the_visual_report_is_literal_and_never_frame_accurate(self):
        v = struct()["operator_visual_report"]
        self.assertEqual((v["digits_seen"], v["order"]), ([1, 2, 3, 4], [1, 2, 3, 4]))
        self.assertEqual((v["missing_digit"], v["repeated_digit"], v["unexpected_digit"], v["visual_anomaly"]), ("no", "no", "no", "no"))
        self.assertEqual(v["approximate_interval_s"], 8)
        self.assertIn("OPERATOR OBSERVATION", v["source"])
        self.assertIn("never timing evidence", v["source"])
        self.assertIn("never a frame-accurate claim", v["source"])


class TheSharedSourceGatePassed(unittest.TestCase):
    """§V6.24.7 WITNESS / SOURCE: the frozen analyzer must read OBSERVED_CONTIGUOUS. It does."""

    def test_the_frozen_verdict_is_observed_contiguous_over_2048_intact_records(self):
        v = struct()["official_vindex"]
        self.assertEqual(v["verdict"], "OBSERVED_CONTIGUOUS")
        self.assertEqual((v["observed"], v["intact"], v["invalid_canonical_strip"]), (2048, 2048, 0))
        self.assertEqual((v["decisive_transitions"], v["observed_id_contiguous"], v["observed_duplicate_id"], v["observed_gap"], v["observed_reorder"]),
                         (2046, 2046, 0, 0, 0))
        self.assertEqual((v["first_last_observed"], v["first_last_decisive"]), ([52, 2099], [52, 2098]))
        self.assertEqual((v["misplaced_block_indices"], v["mixed_block_ids"], v["fault_seen"], v["duplicates"]), (0, 0, False, []))
        self.assertEqual((v["header_crc32"], v["total_crc32"]), ("800a1097", "781de3b8"))

    def test_every_transition_is_plus_one_and_every_record_is_intact(self):
        recs = struct()["records"]
        self.assertEqual(len(recs), 2048)
        self.assertTrue(all(r["valid_blocks"] == 40 and r["index_ok"] == 40 and r["invalid_by_reason"] == {} for r in recs))
        self.assertEqual([r["frame_index"] for r in recs], list(range(LO, HI + 1)))
        ids = [r["frame_id"] for r in recs]
        self.assertEqual((ids[0], ids[-1], len(set(ids))), (52, 2099, 2048))
        self.assertEqual(ids, list(range(52, 2100)), "strictly +1: no duplicate, no gap, no reorder")
        self.assertEqual(struct()["independent_decode"]["adjacent_deltas"], {"1": 2047})

    def test_fault_never_set_and_status_is_one_of_three_values(self):
        recs = struct()["records"]
        self.assertTrue(all((r["status"] & 0x80) == 0 for r in recs), "STATUS.FAULT = 0 throughout")
        self.assertEqual(sorted({r["status"] for r in recs}), [0x26, 0x27, 0x36])
        self.assertEqual(struct()["independent_decode"]["status_counts"], {"0x26": 1579, "0x27": 40, "0x36": 429})
        self.assertEqual(struct()["independent_decode"]["vmargin_values"], [38, 39, 54])

    def test_the_four_appearance_sets_are_retained_whole_and_entered_by_plus_one(self):
        """§V6.22's falsifiable expectation for coord-0002 -- no PREPARE-side duplicate at any
        entry -- read off the data: the frame before each R_k start is followed by the start."""
        m = fi_to_fid()
        ids = list(m.values())
        for k in (1, 2, 3, 4):
            inside = [f for f in ids if 480 * k <= f < 480 * k + 40]
            self.assertEqual((len(inside), len(set(inside))), (40, 40), k)
            before = [fi for fi, f in m.items() if f == 480 * k - 1]
            start = [fi for fi, f in m.items() if f == 480 * k]
            self.assertEqual((len(before), len(start), start[0] - before[0]), (1, 1, 1), k)
        self.assertEqual(struct()["independent_decode"]["appearance_sets_inside_retained_range"], [1, 2, 3, 4])
        self.assertEqual(struct()["independent_decode"]["duplicates_inside_any_R_k"], 0)

    def test_the_run_is_admissible_and_the_gate_is_named_as_the_one_run_12_failed(self):
        g = struct()["verdicts"]["shared_source_gate"]
        self.assertTrue(g.startswith("PASS"))
        self.assertIn("ADMISSIBLE for both experiments", g)
        self.assertIn("the gate RUN 12 failed", g)
        self.assertEqual(run12()["official_vindex"]["verdict"], "OBSERVED_DISCONTINUITY", "RUN 12's record is untouched")


class TheFullFrameResultAndTheFormalVerdict(unittest.TestCase):
    """GBP-VIDEO-008's dependent variable, recomputed from the versioned OGBPFULL1 with the unchanged
    tools/vfull.py (Python, host-built gbp_vpix.c and the tiled oracle) -- and, this time, the run is
    admissible, so the experiment verdict is what the pre-registration said it would be."""

    def test_the_container_is_the_k8_content_blind_store_it_was_pre_registered_to_be(self):
        i = vfull.load(FULL)
        self.assertEqual((i["records_n"], i["k_cap"], i["spacing"], i["origin"]), (8, 8, 256, 356))
        self.assertEqual((i["want_calls"], i["wanted"], i["opened"], i["completed"], i["refused"], i["skipped_capacity"], i["blocks_copied"]),
                         (2377, 8, 8, 8, 0, 0, 320))
        self.assertEqual(i["origin"], struct()["witqual"]["first_record_frame"], "origin = the first retained witness frame_index, mechanically")
        self.assertEqual(("%08x" % i["header_crc32"], "%08x" % i["total_crc32"]), ("b037ecc2", "3e926833"))

    def test_all_eight_samples_pass_every_frozen_check_with_zero_mismatches(self):
        a = full_analysis()
        self.assertEqual(a["verdict"], "PASS")
        self.assertEqual(len(a["samples"]), 8)
        self.assertEqual([s["frame_index"] for s in a["samples"]], SAMPLE_FI)
        self.assertEqual([s["frame_id"] for s in a["samples"]], SAMPLE_FID)
        self.assertEqual([s["status"] for s in a["samples"]], [0x36, 0x36, 0x26, 0x26, 0x26, 0x26, 0x26, 0x26])
        for s in a["samples"]:
            self.assertEqual(s["state"], "COMPLETE")
            self.assertEqual((s["colour15_mismatches"], s["tex_vs_python"], s["tex_vs_oracle"], s["tex_vs_c"]), (0, 0, 0, 0))
            self.assertEqual(s["bit15"], [(0, 0)])
            self.assertEqual(s["displacement_class"], "NONE")
            self.assertFalse(s["fault"])
            self.assertGreater(s["bytes02"]["count"], 0, "bytes 0/2 vary and are reported, never judged (U-GBP-029)")
        self.assertIn("source -> converted texture only", a["boundary"])

    def test_the_sample_ids_are_the_witness_ids_at_those_frame_indices(self):
        m = fi_to_fid()
        self.assertEqual([m[fi] for fi in SAMPLE_FI], SAMPLE_FID)
        self.assertEqual([s["frame_id"] for s in struct()["official_vfull"]["samples"]], SAMPLE_FID)

    def test_the_formal_verdict_is_pass_within_the_stated_boundary(self):
        v = struct()["verdicts"]["GBP-VIDEO-008"]
        self.assertEqual(v["verdict"], "PASS")
        self.assertIn("CLAIM-A / CLAIM-B for the eight prospectively selected K=8 frames only", v["scope"])
        self.assertIn("eight prospectively sampled frames only", v["boundary"])
        self.assertIn("no physical pixel equality", v["boundary"])
        self.assertEqual(run12()["verdicts"]["GBP-VIDEO-008"]["verdict"], "INCONCLUSIVE", "RUN 12's record is untouched")


class PolicyATransportAndStartup(unittest.TestCase):
    def test_container_and_identity(self):
        i = disp()
        self.assertEqual((i["life_overflow"], i["event_overflow"], i["drawdone_unmatched"], i["order_violations"]), (0, 0, 0, 0))
        self.assertEqual((len(i["life"]), i["decisions"], i["source_deferred_frames"], i["event_n"], i["max_deferred_depth"]), (2378, 2377, 40, 2417, 1))
        self.assertTrue(vdisp.usable(i)["usable_for_disposition_claim"])
        self.assertEqual([r["frame_index"] for r in i["life"] if r["disposition"] == D["TERMINAL_PENDING"]], [KEY])
        self.assertEqual(("%08x" % i["header_crc32"], "%08x" % i["total_crc32"]), ("98c08390", "0e88b3ff"))

    def test_exact_join_no_interior_drop_no_reorder(self):
        m = {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}
        joined = [k for k in range(LO, HI + 1) if k in m]
        self.assertEqual(len(joined), 2047)
        self.assertEqual([k for k in range(LO, HI + 1) if k not in m], [HI])
        self.assertTrue(all(m[k]["disposition"] == D["SELECTED_NEW"] for k in joined))
        seq = [r["frame_index"] for r in sorted((m[k] for k in joined), key=lambda r: r["t_decision"])]
        self.assertEqual(seq, list(range(LO, HI)))
        self.assertEqual(vdisp.interior_vs_edge(disp()), {"open": 0, "interior": [], "edge": []})

    def test_deferrals_depth_and_the_frozen_latency_gates(self):
        i = disp()
        m = {r["frame_index"]: r for r in i["life"] if r["frame_index"] != KEY}
        J = [m[k] for k in range(LO, HI)]
        dd = [r for r in J if r["life_flags"] & LF["EVER_DEFERRED"]]
        self.assertEqual((len(dd), sum(r["defer_attempts"] for r in dd), i["max_deferred_depth"]), (37, 81, 1))
        lat = sorted(r["t_decision"] - r["t_convert_done"] for r in J)
        p99, mx = pct(lat, 0.99) * 1000.0 / TB, lat[-1] * 1000.0 / TB
        self.assertLessEqual(p99, 1.0)
        self.assertLessEqual(mx, 2.5)
        self.assertAlmostEqual(p99, 0.308543, places=5)
        self.assertAlmostEqual(mx, 1.005012, places=5)
        self.assertEqual(struct()["policy_a"]["frozen_latency_ms"], {"definition": struct()["policy_a"]["frozen_latency_ms"]["definition"], "p99": 0.308543, "max": 1.005012})

    def test_display_repeats_recorded_as_the_observation_they_are(self):
        m = {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}
        rt = [m[k]["retrace_decision"] for k in range(LO, HI)]
        d = [b - a for a, b in zip(rt, rt[1:])]
        self.assertEqual({k: d.count(k) for k in set(d)}, {1: 2039, 2: 7})
        self.assertEqual(sum(x - 1 for x in d), 7)
        self.assertEqual(struct()["policy_a"]["display_repeat_intervals"], 7)
        self.assertIn("never a gate", struct()["policy_a"]["display_repeat_note"])
        self.assertEqual(vdisp.decision_intervals(disp())["retrace_delta_hist"], {0: 40, 1: 2355, 2: 9, 3: 12})

    def test_log_transport_and_startup_gates(self):
        s = struct()
        h, t, st = s["log_header"], s["transport"], s["startup"]
        self.assertEqual((h["lines"], h["dropped"], h["truncated"]), (658, 0, 0))
        self.assertTrue(all(h["tag_counts"][k] == 1 for k in ("WITELIG", "WITELIG2", "WITQUAL", "FULLSTORE", "VISTORE", "DISPSRC", "STREAMWIT")))
        self.assertLess(h["longest_payload"]["chars"], 248)
        self.assertEqual((t["errors"], t["transport_ok"], t["timeouts"], t["busy"], t["overflow"], t["uncertain"]), (0, 1, 0, 0, 0, 0))
        self.assertEqual((t["unmasks"], t["deliveries"], t["acks"], t["rearms"]), (254862, 254862, 254862, 254862))
        self.assertEqual((t["video"], t["irq_attempted"], t["irq_completed"]), ("96110/96110", 509727, 509727))
        self.assertEqual(t["stop"], "witness_target_reached")
        self.assertEqual((st["mode"], st["ticks_control_to_first_handoff"]), ("normal", 6688650))
        self.assertLess(st["ticks_control_to_first_handoff"] * 1000.0 / TB, 400.0)
        self.assertAlmostEqual(st["ms_control_to_first_handoff"], 165.151852, places=5)

    def test_witness_window_and_the_direct_zero(self):
        s = struct()
        w, q = s["witelig"], s["witqual"]
        self.assertEqual((w["released"], w["still_gated"], w["ticks_control_to_eligible"], w["not_before_ms"]), (1, 0, 202506118, 5000))
        self.assertEqual((q["required"], q["resets"], q["warmup_frames"], q["qualify_frame"], q["first_record_frame"], q["window_first_block"]),
                         (64, 0, 356, 355, 356, 0))
        self.assertEqual(w["qual_streak_at_eligible"]["direct_value"], 0)
        self.assertEqual(q["warmup_frames"] - w["frames_seen_before_eligible"], q["required"])
        self.assertEqual(s["runtime_summaries"]["STREAMWIT"]["records"], "2048/2048")
        self.assertEqual(s["runtime_summaries"]["DISPSRC"]["defer_attempts"], 88)
        self.assertEqual(s["runtime_summaries"]["ENVFULL"]["arena1_free"], 1658880)


class TheVIChainWithTheCorrectedTool(unittest.TestCase):
    def test_container_counts(self):
        v = vi()
        self.assertEqual((v["records_n"], v["records_cap"], v["handed"], v["latched"], v["superseded"], v["overflow"], v["observe_calls"], v["awaiting_at_end"]),
                         (2377, 4096, 2377, 2371, 5, 0, 2371, 2376))
        self.assertEqual([r["frame_index"] for r in v["records"] if r["superseded"]], [86, 631, 1754, 2041, 2315])
        self.assertEqual([r["frame_index"] for r in v["records"] if not r["latched"] and not r["superseded"]], [2402])
        self.assertEqual(("%08x" % v["header_crc32"], "%08x" % v["total_crc32"]), ("a11e9209", "c480f86f"))

    def test_the_corrected_tool_reads_every_latched_register_as_naming_its_handed_buffer(self):
        """The corrected regs_consistent() (GBP-VID-035 repaired, Issue #11) applied PROSPECTIVELY,
        as §V6.24.2 / §V6.24.9 pre-registered; the frozen-at-RUN-12 tool is not re-run here."""
        v = vi()
        latched = [r for r in v["records"] if r["latched"]]
        self.assertEqual(len(latched), 2371)
        rc = [vvi.regs_consistent(r) for r in latched]
        self.assertEqual((sum(1 for t, _, _ in rc if t), sum(1 for _, b, _ in rc if b)), (2371, 2371))
        self.assertTrue(all(t == r["phys"] for (_, _, t), r in zip(rc, latched)))
        for r in latched:
            self.assertEqual(r["phys"] & 0x1F, 0)
            self.assertGreaterEqual(r["phys"], 0x01000000)
            t, b = r["phys"] >> 5, (r["phys"] + 1280) >> 5
            self.assertEqual((r["vi14"], r["vi15"], r["vi18"], r["vi19"]),
                             ((1 << 12) | ((t >> 16) & 0xFF), t & 0xFFFF, (b >> 16) & 0xFF, b & 0xFFFF))
        self.assertEqual(sorted({r["phys"] for r in latched}), [0x013a8420, 0x0143e440])
        self.assertEqual(struct()["official_vvi"]["regs_consistent_top_matches"], "2371/2371")
        self.assertIn("CORRECTED", struct()["official_vvi"]["tool"])

    def test_the_chain_derives_l_40_40_39_40_from_latched_records_only(self):
        """The one R_3 hand-over at frame_index 1754 (FRAME_ID 1450) is SUPERSEDED in the raw
        OGBPVI1 -- the next hand-over came one retrace later, before the pump observed it current --
        so it has no latch record and is not a member of L_3 by the frozen definition. That is
        instrumentation semantics only: nothing here says whether the frame was or was not
        physically scanned out."""
        v = vi()
        rows = vvi.chain(fi_to_fid(), disp(), v)
        self.assertEqual([(r["k"], r["digit"], len(r["R"]), r["retained"], r["H"], r["L"]) for r in rows],
                         [(1, 1, 40, 40, 40, 40), (2, 2, 40, 40, 40, 40), (3, 3, 40, 40, 40, 39), (4, 4, 40, 40, 40, 40)])
        self.assertTrue(all(r["first_latch_t"] is not None and r["first_latch_t"] > r["first_handed_t"] for r in rows))
        by_fi = {r["frame_index"]: r for r in v["records"]}
        m = fi_to_fid()
        r3 = [fi for fi, fid in m.items() if 1440 <= fid < 1480]
        self.assertEqual(len(r3), 40)
        missing = sorted(fi for fi in r3 if not by_fi[fi]["latched"])
        self.assertEqual(missing, [1754])
        self.assertEqual(m[1754], 1450)
        self.assertTrue(by_fi[1754]["superseded"])
        self.assertEqual((by_fi[1754]["t_latch"], by_fi[1754]["retrace_latch"], by_fi[1754]["vi14"]), (0, 0, 0))
        self.assertEqual(by_fi[1755]["retrace_handed"], by_fi[1754]["retrace_handed"] + 1, "superseded by the next hand-over, one retrace later")
        self.assertTrue(all(r["L"] >= 1 for r in rows), "the §V6.24.9 population requirement: at least one latched frame per qualifying appearance")
        self.assertEqual([r["L"] for r in struct()["official_vvi"]["rows"]], [40, 40, 39, 40])
        self.assertIn("INSTRUMENTATION ONLY", struct()["official_vvi"]["R_3_member_not_in_L_3"]["semantics"])

    def test_every_latch_is_the_next_retrace_after_its_hand_over(self):
        latched = [r for r in vi()["records"] if r["latched"]]
        self.assertTrue(all(r["retrace_latch"] - r["retrace_handed"] == 1 for r in latched))
        self.assertTrue(all(r["t_latch"] > r["t_handed"] for r in latched))

    def test_the_formal_verdict_is_pass_as_claim_d_only(self):
        v = struct()["verdicts"]["GBP-VIDEO-007"]
        self.assertEqual(v["verdict"], "PASS")
        self.assertTrue(v["scope"].startswith("CLAIM-D only"))
        self.assertIn("digits 1, 2, 3, 4 in order through the declared RUN-13 display chain", v["scope"])
        self.assertFalse(v["exact_frame_binding"])
        self.assertFalse(v["pixel_claim"])
        self.assertTrue(v["operator_report_beside_not_inside"])
        self.assertIn("never evidence of physical non-scanout", v["superseded_r3_record"])
        self.assertEqual(run12()["verdicts"]["GBP-VIDEO-007"]["verdict"], "INCONCLUSIVE", "RUN 12's record is untouched")


class TheComparisonWithRun12AndTheFindings(unittest.TestCase):
    def test_the_comparison_records_both_runs_and_claims_no_mechanism(self):
        c = struct()["comparison_vs_run12"]
        self.assertEqual(c["build"], ["stream-0013", "stream-0013"])
        self.assertEqual(c["dol_sha256"], [DOL_SHA, DOL_SHA])
        self.assertEqual(c["source_verdict"], ["OBSERVED_DISCONTINUITY", "OBSERVED_CONTIGUOUS"])
        self.assertEqual(c["decisive_transitions"], [{"contiguous": 2044, "duplicate": 2}, {"contiguous": 2046, "duplicate": 0}])
        self.assertEqual(c["intact_invalid"], [[2048, 0], [2048, 0]])
        self.assertEqual(c["first_handoff_ticks"], [run12()["startup"]["ticks_control_to_first_handoff"], 6688650])
        self.assertEqual(c["frozen_p99_max_ms"], [[0.308642, 1.004667], [0.308543, 1.005012]])
        self.assertEqual((c["interior_drops"], c["max_depth"], c["display_repeats"]), ([0, 0], [1, 1], [7, 7]))
        self.assertEqual([c["verdict_007"], c["verdict_008"]], [["INCONCLUSIVE", "PASS"], ["INCONCLUSIVE", "PASS"]])
        self.assertIn("not proof", c["note"])

    def test_no_new_finding_and_the_two_histories_stay(self):
        f = struct()["findings"]
        self.assertTrue(f["new"].startswith("none"))
        self.assertIn("RESOLVED history", f["GBP-VID-034"])
        self.assertIn("REPAIRED history", f["GBP-VID-035"])
        self.assertEqual(struct()["evidence_ids"], ["GBP-HW-256", "GBP-HW-257", "GBP-HW-258", "GBP-HW-259", "GBP-HW-260"])
        self.assertTrue(struct()["verdicts"]["no_rerun_preregistered"])

    def test_the_run_12_fixtures_are_untouched(self):
        r = run12()
        for k in ("disp", "full", "vi", "qual"):
            p = os.path.join(ROOT, r["fixtures"][k]["path"])
            self.assertEqual(sha(p), r["fixtures"][k]["sha256"], k)
        self.assertEqual((r["run"], r["verdicts"]["GBP-VIDEO-007"]["verdict"], r["verdicts"]["GBP-VIDEO-008"]["verdict"]), (12, "INCONCLUSIVE", "INCONCLUSIVE"))
        self.assertEqual(r["official_vvi"]["regs_consistent_top_matches"], "0/2370", "the frozen-at-RUN-12 output stays as history")


if __name__ == "__main__":
    unittest.main()
