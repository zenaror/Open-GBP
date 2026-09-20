"""
tests/host/test_run12.py — RUN 12: GBP-VIDEO-007 (physical scanout) and
GBP-VIDEO-008 (full-frame fidelity) on stream-0013 + coord-0001, pre-registered
in HARDWARE_TESTS §V6.19 (Issue #8), executed under Hardware Issue #9, ingested
under Issue #10 (result §V6.20). Preserved as fixtures.

Both formal verdicts are INCONCLUSIVE because the SHARED source-window gate
failed: the frozen analyzer reads OBSERVED_DISCONTINUITY (two duplicate FRAME_ID
transitions) over 2048 structurally intact records. The subordinate full-frame
dependent-variable analysis is PASS 8/8 and is kept as exactly that — positive
subordinate evidence, never a GBP-VIDEO-008 experiment PASS. The operator's
visual report (digits 1, 2, 3, 4 in order) is preserved as an observation beside
the machine chain, never inside it. GBP-VID-034 (the duplicates; mechanism open)
(OPEN) and GBP-VID-035 (the vvi.py address-domain defect, since REPAIRED in
software by Issue #11) are pinned: the fixture keeps the analyzer's
frozen-at-run output (0/2370, L_k = 0) as the historical record, and the
executable assertions read the CORRECTED tool -- a post-run software replay
that changes no verdict. Every inherited gate is the run-9/10/11 gate reused;
none added, none narrowed. Nothing here derives a topology from a file, and no
test consults the operator's report to decide a machine fact.
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
P = "hw-gamecube-gbp-2026-09-20-"
DISP = os.path.join(FX, P + "stream-0013-run12-disp.bin")
FULL = os.path.join(FX, P + "stream-0013-run12-full.bin")
VI = os.path.join(FX, P + "stream-0013-run12-vi.bin")
QUAL = os.path.join(FX, P + "idxcap-run12-qual.bin")
STRUCT = os.path.join(FX, P + "idxcap-run12-struct.json")
RUN11 = os.path.join(FX, P + "idxcap-run11-struct.json")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
DISP_SHA = "91c2f80549845ac4598a8e7f60825f33c2256dabdfd5f878e4cb0abd4c4c23a4"
FULL_SHA = "fb09a777893b91b582d6b33b16136a4aacdc1528011d625e350a916ddeb9433c"
VI_SHA = "d301e96e6865669d8d91acad669c7b89612191619013757fd1656508b42addb0"
QUAL_SHA = "f010af4afaff3d1c0698b1cd5be6763c064b3eee868930d50dc1064a6f2e7ce0"
IDXCAP_SHA = "fe1c1c0ad00ba7bf1392da045c7a8086e08b65043596d39d0e0d04a5c2b3afd8"
LOG_SHA = "0b64b677d7f1496d34353f816dec926b09b62b271a19fac62ce0c464c439882b"
DOL_SHA = "5391c3fe962dc4b2f4e493f3846ac7407ded064c58f5d4bb583a51e5a725dd79"
STIM_SHA = "a769cc11afcb93cfc1cf89bf9bb59554533662c051e25b475f3943e7bdbb994f"
TB = 40500000
KEY = vdisp.KEY_NONE
D = {v: k for k, v in vdisp.DISPOSITION.items()}
LF = {v: k for k, v in vdisp.LF}
LO, HI = 356, 2403
SAMPLE_FI = [356 + 256 * i for i in range(8)]
SAMPLE_FID = [74, 330, 585, 841, 1097, 1353, 1609, 1865]
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


def run11():
    if "r11" not in _C:
        with open(RUN11) as f:
            _C["r11"] = json.load(f)
    return _C["r11"]


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
        self.assertEqual((sha(DISP), os.path.getsize(DISP)), (DISP_SHA, 401356))
        self.assertEqual((sha(FULL), os.path.getsize(FULL)), (FULL_SHA, 1844492))
        self.assertEqual((sha(VI), os.path.getsize(VI)), (VI_SHA, 152396))

    def test_the_qual_projection_names_the_physical_witness_it_came_from(self):
        self.assertEqual(sha(QUAL), QUAL_SHA)
        q = vqual.load(QUAL)
        self.assertEqual((q["records_n"], q["src_size"], q["src_sha256"]), (2048, 8946060, IDXCAP_SHA))
        self.assertEqual([r["frame_index"] for r in q["records"]], list(range(LO, HI + 1)))

    def test_it_is_stream_0013_at_7d7a6d8_and_the_coord_0001_delivery_image(self):
        s = struct()
        for i in (disp(), vi(), vfull.load(FULL)):
            self.assertEqual((i["build_id"], i["commit"], i["test_id"]), ("stream-0013", "7d7a6d8", "GBP-VIDEO-004"))
        self.assertEqual((s["dol"]["size"], s["dol"]["sha256"], s["dol"]["commit_full"]),
                         (506496, DOL_SHA, "7d7a6d8acf4e3985034f9ad4f5041fec751181d0"))
        self.assertEqual((s["stimulus"]["size"], s["stimulus"]["sha256"]), (3496, STIM_SHA))
        self.assertIn("re-flashed", s["stimulus"]["note"])
        self.assertNotEqual(run11()["dol"]["sha256"], DOL_SHA)
        self.assertNotEqual(run11()["stimulus"]["sha256"], STIM_SHA)

    def test_the_raw_identities_are_the_ones_hashed_on_receipt(self):
        raw = struct()["raw"]
        exp = {"log": (89514, LOG_SHA), "idxcap": (8946060, IDXCAP_SHA), "disp": (401356, DISP_SHA),
               "full": (1844492, FULL_SHA), "vi": (152396, VI_SHA)}
        for k, (sz, h) in exp.items():
            self.assertEqual((raw[k]["size"], raw[k]["sha256"]), (sz, h), k)
            self.assertIn("-run12", raw[k]["archived_as"])
            self.assertNotIn("run12", raw[k]["supplied_name"], "the console names carry no run number")
        self.assertEqual(struct()["fixtures"]["qual"]["sha256"], QUAL_SHA)

    def test_the_topology_and_the_display_chain_are_the_operators_declaration(self):
        t = struct()["topology_declared_by_operator"]
        self.assertEqual((t["bba_present"], t["ethernet"], t["same_gamecube_as_run10_run11"], t["same_gbp_as_run10_run11"]),
                         ("YES", "DISCONNECTED", "YES", "YES"))
        self.assertIn("OPERATOR", t["source"])
        chain = " ".join(t["display_chain"])
        for item in ("composite / RCA", "RCA-to-HDMI converter", "1080p", "HYDIS HV150UX2", "M.NT68676.2A"):
            self.assertIn(item, chain)
        self.assertIn("topology declaration only", t["display_chain_note"])
        self.assertIn("OUTSIDE RUN 12", t["future_morph_2k_paths"])

    def test_the_visual_report_is_literal_and_never_frame_accurate(self):
        v = struct()["operator_visual_report"]
        self.assertEqual((v["digits_seen"], v["order"]), ([1, 2, 3, 4], [1, 2, 3, 4]))
        self.assertEqual((v["missing_digit"], v["repeated_digit"], v["unexpected_digit"], v["visual_anomaly"]), ("no", "no", "no", "no"))
        self.assertIn("OPERATOR OBSERVATION", v["source"])
        self.assertIn("never a frame-accurate claim", v["source"])


class TheSharedSourceGateFailed(unittest.TestCase):
    """§V6.19.7 WITNESS / SOURCE: the frozen analyzer must read OBSERVED_CONTIGUOUS. It did not."""

    def test_the_frozen_verdict_is_observed_discontinuity_over_2048_intact_records(self):
        v = struct()["official_vindex"]
        self.assertEqual(v["verdict"], "OBSERVED_DISCONTINUITY")
        self.assertEqual((v["observed"], v["intact"], v["invalid_canonical_strip"]), (2048, 2048, 0))
        self.assertEqual((v["decisive_transitions"], v["observed_id_contiguous"], v["observed_duplicate_id"]), (2046, 2044, 2))
        self.assertEqual((v["first_last_observed"], v["first_last_decisive"]), ([74, 2119], [74, 2118]))
        self.assertEqual((v["misplaced_block_indices"], v["mixed_block_ids"], v["fault_seen"]), (0, 0, False))

    def test_the_two_duplicates_at_their_exact_positions_and_nowhere_else(self):
        recs = struct()["records"]
        self.assertEqual(len(recs), 2048)
        self.assertTrue(all(r["valid_blocks"] == 40 and r["index_ok"] == 40 and r["invalid_by_reason"] == {} for r in recs))
        self.assertEqual([r["frame_index"] for r in recs], list(range(LO, HI + 1)))
        ids = [r["frame_id"] for r in recs]
        self.assertEqual((ids[0], ids[-1], len(set(ids))), (74, 2119, 2046))
        dup = [(recs[k]["frame_index"], recs[k + 1]["frame_index"], ids[k]) for k in range(2047) if ids[k + 1] == ids[k]]
        self.assertEqual(dup, [(761, 762, 479), (2202, 2203, 1919)])
        self.assertTrue(all(b - a in (0, 1) for a, b in zip(ids, ids[1:])), "no gap, no reorder: duplicates only")
        self.assertEqual([d["status"] for d in struct()["official_vindex"]["duplicates"]], ["0x36", "0x26"])

    def test_fault_never_set_and_status_is_one_of_three_values(self):
        recs = struct()["records"]
        self.assertTrue(all((r["status"] & 0x80) == 0 for r in recs), "STATUS.FAULT = 0 throughout")
        self.assertEqual(sorted({r["status"] for r in recs}), [0x26, 0x27, 0x36])
        self.assertEqual(struct()["independent_decode"]["status_counts"], {"0x26": 1120, "0x27": 520, "0x36": 408})

    def test_the_duplicates_sit_outside_every_appearance_set(self):
        """Each R_k = [480k, 480k+40) keeps 40 distinct FRAME_IDs; the duplicated ids 479 and
        1919 are the frames BEFORE R_1 and R_4 -- recorded as an observation, no mechanism."""
        ids = [r["frame_id"] for r in struct()["records"]]
        for k in (1, 2, 3, 4):
            inside = [f for f in ids if 480 * k <= f < 480 * k + 40]
            self.assertEqual((len(inside), len(set(inside))), (40, 40), k)
        self.assertEqual([479 + 1, 1919 + 1], [480 * 1, 480 * 4])
        self.assertIn("NOT inferred", struct()["official_vindex"]["note"])

    def test_both_formal_verdicts_are_inconclusive_for_the_shared_reason(self):
        v = struct()["verdicts"]
        self.assertEqual((v["GBP-VIDEO-007"]["verdict"], v["GBP-VIDEO-008"]["verdict"]), ("INCONCLUSIVE", "INCONCLUSIVE"))
        self.assertIn("OBSERVED_DISCONTINUITY, not OBSERVED_CONTIGUOUS", v["common_formal_reason"])
        self.assertTrue(v["no_rerun_preregistered"])


class TheSubordinateFullFrameResult(unittest.TestCase):
    """GBP-VIDEO-008's dependent variable, recomputed from the versioned OGBPFULL1 with the frozen
    tools/vfull.py (Python, host-built gbp_vpix.c and the tiled oracle). PASS 8/8 here is SUBORDINATE
    evidence; the experiment verdict stays INCONCLUSIVE and this file never says otherwise."""

    def test_the_container_is_the_k8_content_blind_store_it_was_pre_registered_to_be(self):
        i = vfull.load(FULL)
        self.assertEqual((i["records_n"], i["k_cap"], i["spacing"], i["origin"]), (8, 8, 256, 356))
        self.assertEqual((i["want_calls"], i["wanted"], i["opened"], i["completed"], i["refused"], i["skipped_capacity"], i["blocks_copied"]),
                         (2377, 8, 8, 8, 0, 0, 320))
        self.assertEqual(i["origin"], struct()["witqual"]["first_record_frame"], "origin = the first retained witness frame_index, mechanically")

    def test_all_eight_samples_pass_every_frozen_check_with_zero_mismatches(self):
        a = full_analysis()
        self.assertEqual(a["verdict"], "PASS")
        self.assertEqual(len(a["samples"]), 8)
        self.assertEqual([s["frame_index"] for s in a["samples"]], SAMPLE_FI)
        self.assertEqual([s["frame_id"] for s in a["samples"]], SAMPLE_FID)
        self.assertEqual([s["status"] for s in a["samples"]], [0x36, 0x36, 0x27, 0x27, 0x26, 0x26, 0x26, 0x26])
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

    def test_it_is_recorded_as_subordinate_and_never_as_an_experiment_pass(self):
        v = struct()["verdicts"]["GBP-VIDEO-008"]
        self.assertEqual(v["verdict"], "INCONCLUSIVE")
        self.assertIn("PASS 8/8", v["subordinate_full_frame_analysis"])
        self.assertIn("Positive subordinate evidence", v["required_wording"])
        self.assertIn("nevertheless INCONCLUSIVE", v["required_wording"])
        forbidden = "GBP-VIDEO-008" + " PASS"      # the literal must not exist anywhere, this file included
        for path, enc in ((STRUCT, None), (HW, "utf-8"), (os.path.join(ROOT, "docs", "HANDOFF.md"), "utf-8"),
                          (os.path.join(ROOT, "docs", "research", "EVIDENCE.md"), "utf-8")):
            with open(path, encoding=enc) as f:
                self.assertNotIn(forbidden, f.read(), path)


class PolicyATransportAndStartup(unittest.TestCase):
    def test_container_and_identity(self):
        i = disp()
        self.assertEqual((i["life_overflow"], i["event_overflow"], i["drawdone_unmatched"], i["order_violations"]), (0, 0, 0, 0))
        self.assertEqual((i["decisions"], i["source_deferred_frames"], i["event_n"], i["max_deferred_depth"]), (2377, 39, 2416, 1))
        self.assertTrue(vdisp.usable(i)["usable_for_disposition_claim"])
        self.assertEqual([r["frame_index"] for r in i["life"] if r["disposition"] == D["TERMINAL_PENDING"]], [KEY])

    def test_exact_join_no_interior_drop_no_reorder(self):
        m = {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}
        joined = [k for k in range(LO, HI + 1) if k in m]
        self.assertEqual(len(joined), 2047)
        self.assertEqual([k for k in range(LO, HI + 1) if k not in m], [HI])
        self.assertTrue(all(m[k]["disposition"] == D["SELECTED_NEW"] for k in joined))
        seq = [r["frame_index"] for r in sorted((m[k] for k in joined), key=lambda r: r["t_decision"])]
        self.assertEqual(seq, list(range(LO, HI)))

    def test_deferrals_depth_and_the_frozen_latency_gates(self):
        i = disp()
        m = {r["frame_index"]: r for r in i["life"] if r["frame_index"] != KEY}
        J = [m[k] for k in range(LO, HI)]
        dd = [r for r in J if r["life_flags"] & LF["EVER_DEFERRED"]]
        self.assertEqual((len(dd), sum(r["defer_attempts"] for r in dd), i["max_deferred_depth"]), (36, 79, 1))
        lat = sorted(r["t_decision"] - r["t_convert_done"] for r in J)
        p99, mx = pct(lat, 0.99) * 1000.0 / TB, lat[-1] * 1000.0 / TB
        self.assertLessEqual(p99, 1.0)
        self.assertLessEqual(mx, 2.5)
        self.assertAlmostEqual(p99, 0.308642, places=5)
        self.assertAlmostEqual(mx, 1.004667, places=5)

    def test_display_repeats_recorded_as_the_observation_they_are(self):
        m = {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}
        rt = [m[k]["retrace_decision"] for k in range(LO, HI)]
        d = [b - a for a, b in zip(rt, rt[1:])]
        self.assertEqual({k: d.count(k) for k in set(d)}, {1: 2039, 2: 7})
        self.assertEqual(sum(x - 1 for x in d), 7)
        self.assertEqual(struct()["policy_a"]["display_repeat_intervals"], 7)
        self.assertIn("never a gate", struct()["policy_a"]["display_repeat_note"])

    def test_log_transport_and_startup_gates(self):
        s = struct()
        h, t, st = s["log_header"], s["transport"], s["startup"]
        self.assertEqual((h["lines"], h["dropped"], h["truncated"]), (674, 0, 0))
        self.assertEqual(h["tag_counts"]["WITELIG"], 1)
        self.assertEqual(h["tag_counts"]["WITELIG2"], 1)
        self.assertLess(h["longest_payload"]["chars"], 248)
        self.assertEqual((t["errors"], t["transport_ok"], t["timeouts"], t["busy"], t["overflow"], t["uncertain"]), (0, 1, 0, 0, 0, 0))
        self.assertEqual(t["unmasks"], t["deliveries"])
        self.assertEqual(t["acks"], t["rearms"])
        self.assertEqual(t["stop"], "witness_target_reached")
        self.assertEqual((st["mode"], st["ticks_control_to_first_handoff"]), ("normal", 6688663))
        self.assertLess(st["ticks_control_to_first_handoff"] * 1000.0 / TB, 400.0)
        self.assertAlmostEqual(st["ms_control_to_first_handoff"], 165.152173, places=5)

    def test_witness_window_and_the_direct_zero(self):
        s = struct()
        w, q = s["witelig"], s["witqual"]
        self.assertEqual((w["released"], w["still_gated"], w["ticks_control_to_eligible"], w["not_before_ms"]), (1, 0, 202506231, 5000))
        self.assertEqual((q["required"], q["resets"], q["warmup_frames"], q["qualify_frame"], q["first_record_frame"], q["window_first_block"]),
                         (64, 0, 356, 355, 356, 0))
        self.assertEqual(w["qual_streak_at_eligible"]["direct_value"], 0)
        self.assertEqual(q["warmup_frames"] - w["frames_seen_before_eligible"], q["required"])
        self.assertEqual(s["runtime_summaries"]["STREAMWIT"]["records"], "2048/2048")
        self.assertEqual(s["runtime_summaries"]["ENVFULL"]["arena1_free"], 1658880)


class TheVIChainAndFinding035(unittest.TestCase):
    def test_container_counts(self):
        v = vi()
        self.assertEqual((v["records_n"], v["records_cap"], v["handed"], v["latched"], v["superseded"], v["overflow"], v["observe_calls"], v["awaiting_at_end"]),
                         (2377, 4096, 2377, 2370, 6, 0, 2370, 2376))
        self.assertEqual([r["frame_index"] for r in v["records"] if r["superseded"]], [86, 631, 1754, 1757, 2041, 2315])
        self.assertEqual([r["frame_index"] for r in v["records"] if not r["latched"] and not r["superseded"]], [2402])

    def test_the_frozen_at_run_result_is_kept_as_history_in_the_fixture(self):
        """What the analyzer frozen at RUN 12 returned -- 0/2370 and L_k = 0 -- is a historical fact
        (§V6.20.7, GBP-HW-255) recorded in the fixture's metadata; it is not recomputed, because the
        tool has since been repaired (GBP-VID-035, Issue #11) and no longer returns it."""
        o = struct()["official_vvi"]
        self.assertEqual((o["regs_consistent_top_matches"], o["regs_consistent_bottom_plausible"]), ("0/2370", "0/2370"))
        self.assertEqual([(r["k"], r["retained"], r["H"], r["L"]) for r in o["rows"]], [(k, 40, 40, 0) for k in (1, 2, 3, 4)])
        self.assertTrue(all(r["first_latch_t"] is None for r in o["rows"]))
        x = struct()["vi_raw_crosscheck"]
        self.assertEqual((x["finding"], x["top_vs_unmasked_phys"], x["top_vs_masked_phys_24bit"], x["bottom_vs_phys_or_phys_plus_1280"]),
                         ("GBP-VID-035", "2370/2370", "0/2370", "2370/2370"))
        self.assertIn("software analyzer/model defect", x["interpretation"])
        self.assertIn("does not retrospectively change", x["interpretation"])

    def test_the_corrected_tool_reads_every_latched_register_as_naming_its_handed_buffer(self):
        """GBP-VID-035 REPAIRED (Issue #11): a post-run software replay of the versioned OGBPVI1 with
        the corrected regs_consistent(); it changes no RUN 12 verdict."""
        v = vi()
        latched = [r for r in v["records"] if r["latched"]]
        self.assertEqual(len(latched), 2370)
        rc = [vvi.regs_consistent(r) for r in latched]
        self.assertEqual((sum(1 for t, _, _ in rc if t), sum(1 for _, b, _ in rc if b)), (2370, 2370))
        self.assertTrue(all(t == r["phys"] for (_, _, t), r in zip(rc, latched)))
        # the raw halves are exactly libogc2's encoding of the handed address (flag 1: MEM1 above 16 MiB, stored >> 5)
        for r in latched:
            self.assertEqual(r["phys"] & 0x1F, 0)
            self.assertGreaterEqual(r["phys"], 0x01000000)
            t, b = r["phys"] >> 5, (r["phys"] + 1280) >> 5
            self.assertEqual((r["vi14"], r["vi15"], r["vi18"], r["vi19"]),
                             ((1 << 12) | ((t >> 16) & 0xFF), t & 0xFFFF, (b >> 16) & 0xFF, b & 0xFFFF))
        self.assertEqual(sorted({r["phys"] for r in latched}), [0x013a8420, 0x0143e440])

    def test_the_corrected_chain_derives_l_k_40_40_38_40_from_latched_records_only(self):
        """The two R_3 hand-overs at frame_index 1754 (FRAME_ID 1471) and 1757 (FRAME_ID 1474) are
        SUPERSEDED in the raw OGBPVI1 -- the next hand-over came before the pump observed them
        current -- so they have no latch record and are not members of L_3 by the frozen definition.
        That is instrumentation semantics only: nothing here says whether either frame was or was
        not physically scanned out."""
        v = vi()
        rows = vvi.chain(fi_to_fid(), disp(), v)
        self.assertEqual([(r["k"], r["digit"], len(r["R"]), r["retained"], r["H"], r["L"]) for r in rows],
                         [(1, 1, 40, 40, 40, 40), (2, 2, 40, 40, 40, 40), (3, 3, 40, 40, 40, 38), (4, 4, 40, 40, 40, 40)])
        self.assertTrue(all(r["first_latch_t"] is not None and r["first_latch_t"] > r["first_handed_t"] for r in rows))
        by_fi = {r["frame_index"]: r for r in v["records"]}
        m = fi_to_fid()
        r3 = [fi for fi, fid in m.items() if 1440 <= fid < 1480]
        self.assertEqual(len(r3), 40)
        missing = sorted(fi for fi in r3 if not by_fi[fi]["latched"])
        self.assertEqual(missing, [1754, 1757])
        self.assertEqual([m[fi] for fi in missing], [1471, 1474])
        for fi in missing:
            self.assertTrue(by_fi[fi]["superseded"])
            self.assertEqual((by_fi[fi]["t_latch"], by_fi[fi]["retrace_latch"], by_fi[fi]["vi14"]), (0, 0, 0))
            self.assertEqual(by_fi[fi + 1]["retrace_handed"], by_fi[fi]["retrace_handed"] + 1, "superseded by the next hand-over, one retrace later")
        # the §V6.19.9 gate asked for at least one latched frame per qualifying appearance; all four sets are non-empty
        self.assertTrue(all(r["L"] >= 1 for r in rows))

    def test_every_latch_is_the_next_retrace_after_its_hand_over(self):
        latched = [r for r in vi()["records"] if r["latched"]]
        self.assertTrue(all(r["retrace_latch"] - r["retrace_handed"] == 1 for r in latched))
        self.assertTrue(all(r["t_latch"] > r["t_handed"] for r in latched))


class TheComparisonWithRun11AndTheFindings(unittest.TestCase):
    def test_the_comparison_records_both_runs_and_claims_no_mechanism(self):
        c = struct()["comparison_vs_run11"]
        self.assertEqual(c["build"], ["stream-0011", "stream-0013"])
        self.assertEqual(c["source_verdict"], ["OBSERVED_CONTIGUOUS", "OBSERVED_DISCONTINUITY"])
        self.assertEqual(c["intact_invalid"], [[2048, 0], [2048, 0]])
        self.assertEqual(c["first_handoff_ticks"], [run11()["startup"]["ticks_control_to_first_handoff"], 6688663])
        self.assertEqual(c["interior_drops"], [0, 0])
        self.assertEqual(c["max_depth"], [1, 1])
        self.assertEqual(c["display_repeats"], [7, 7])
        self.assertEqual(c["frozen_p99_max_ms"][1], [0.308642, 1.004667])
        self.assertIn("not proof", c["note"])

    def test_the_findings_as_recorded_at_ingestion_and_their_current_status(self):
        f = struct()["findings"]                      # the fixture is the ingestion-time record and is never edited
        self.assertIn("OPEN", f["GBP-VID-034"])
        self.assertIn("479->479", f["GBP-VID-034"])
        self.assertIn("OPEN", f["GBP-VID-035"])
        self.assertIn("not fixed here", f["GBP-VID-035"])
        self.assertEqual(struct()["evidence_ids"], ["GBP-HW-%d" % n for n in range(250, 256)])
        with open(os.path.join(ROOT, "docs", "research", "EVIDENCE.md"), encoding="utf-8") as fh:
            ev = fh.read()
        h34 = [l for l in ev.splitlines() if l.startswith("### GBP-VID-034 ")][0]
        h35 = [l for l in ev.splitlines() if l.startswith("### GBP-VID-035 ")][0]
        self.assertIn("OPEN", h34)                     # GBP-VID-034 is outside Issue #11 and stays open
        self.assertIn("REPAIRED (software)", h35)      # GBP-VID-035 repaired by Issue #11
        self.assertNotIn("OPEN", h35.split("REPAIRED")[-1])


if __name__ == "__main__":
    unittest.main()
