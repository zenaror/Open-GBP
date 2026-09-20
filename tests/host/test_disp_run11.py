"""
tests/host/test_disp_run11.py — GBP-VIDEO-006 / RUN 11: the stream-0011
reporting repair (GBP-VID-033) on run 10's topology — Broadband Adapter
physically PRESENT, Ethernet DISCONNECTED (HARDWARE_TESTS §V5.58.7, result
§V5.58.9). Preserved as a fixture.

The topology facts come from the operator's declaration, recorded in the
fixture metadata as such; nothing here derives them from files. The frozen
analyzer's verdict is kept WITH its composition. The PRIMARY new gate is the
log-reporting one: `dropped=0 truncated=0`, exactly one complete `WITELIG` and
one complete `WITELIG2`, and `qual_streak_at_eligible=0` read DIRECTLY from the
saved record, with the counter relation agreeing as a cross-check. Every other
gate is the run-9/run-10 gate reused: none added, none narrowed. The display
repeat count is recorded as the observation it is, never as a gate. Run-9 and
run-10 fixtures and tests are not touched; run 10 keeps its `truncated=1`.
"""
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import vdisp  # noqa: E402
import vqual  # noqa: E402

FX = os.path.join(ROOT, "captures", "fixtures")
DISP = os.path.join(FX, "hw-gamecube-gbp-2026-09-20-stream-0011-run11-disp.bin")
QUAL = os.path.join(FX, "hw-gamecube-gbp-2026-09-20-idxcap-run11-qual.bin")
STRUCT = os.path.join(FX, "hw-gamecube-gbp-2026-09-20-idxcap-run11-struct.json")
RUN10 = os.path.join(FX, "hw-gamecube-gbp-2026-09-20-idxcap-run10-struct.json")
DISP_SHA = "04feeca965f9b68479dc654aa31b25e1bf16798c79365b0f938911adfa72b3e7"
QUAL_SHA = "d73f6c982337842e39bfc0e7932ca5cb2615b045f0310954e8b4684a3371a3e6"
IDXCAP_SHA = "9b62415b869a07c27440f6c481f1971e4244de4b1efc0ff453eed349e3e74b51"
LOG_SHA = "c1987d2f5499b037d7912e5664178d0c38bb68afba270001f3968537ded4228b"
DOL_SHA = "df2873ee61caa75c885215b54e29e8d5357b233b9bcc0f10d5c0b1af75453e25"
STIM_SHA = "9f04916b88308e7045f207136f5fc681e5bab33ac9b22d2e19be12c16b8d9cc2"
TB = 40500000
KEY = vdisp.KEY_NONE
D = {v: k for k, v in vdisp.DISPOSITION.items()}
LF = {v: k for k, v in vdisp.LF}
LO, HI = 356, 2403
CONTRACT_FIELDS = {"policy", "origin", "not_before_ms", "gated_at_init", "released", "still_gated", "t_eligible",
                   "ticks_control_to_eligible", "frames_seen_before_eligible", "disqualified_before_eligible",
                   "qual_streak_at_eligible"}
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


def run10():
    if "r10" not in _C:
        with open(RUN10) as f:
            _C["r10"] = json.load(f)
    return _C["r10"]


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def pct(s, q):
    n = len(s)
    return s[min(n - 1, int(n * q))] if n else None


class TheArtifactAndTopology(unittest.TestCase):
    def test_the_disp_fixture_is_the_physical_sidecar(self):
        self.assertEqual(sha(DISP), DISP_SHA)
        self.assertEqual(os.path.getsize(DISP), 401956)

    def test_the_qual_projection_names_the_physical_witness_it_came_from(self):
        self.assertEqual(sha(QUAL), QUAL_SHA)
        q = vqual.load(QUAL)
        self.assertEqual((q["records_n"], q["src_size"], q["src_sha256"]), (2048, 8946060, IDXCAP_SHA))

    def test_it_is_the_stream_0011_binary_and_the_run_10_stimulus(self):
        i, s = disp(), struct()
        self.assertEqual((i["build_id"], i["commit"]), ("stream-0011", "97c78c2"))
        self.assertEqual((s["dol"]["size"], s["dol"]["sha256"]), (495104, DOL_SHA))
        self.assertEqual(s["stimulus"]["sha256"], STIM_SHA)
        self.assertEqual(run10()["stimulus"]["sha256"], STIM_SHA, "the stimulus is run 10's, not re-flashed")
        self.assertNotEqual(run10()["dol"]["sha256"], DOL_SHA, "the reporting build is the intentional variable")

    def test_the_raw_identities_are_the_ones_hashed_on_receipt(self):
        raw = struct()["raw"]
        self.assertEqual((raw["log"]["size"], raw["log"]["sha256"]), (86338, LOG_SHA))
        self.assertEqual((raw["idxcap"]["size"], raw["idxcap"]["sha256"]), (8946060, IDXCAP_SHA))
        self.assertEqual((raw["disp"]["size"], raw["disp"]["sha256"]), (401956, DISP_SHA))
        for k in ("log", "idxcap", "disp"):
            self.assertIn("-run11", raw[k]["archived_as"])
            self.assertNotIn("run11", raw[k]["supplied_name"], "the console names carry no run number")

    def test_the_topology_is_the_operators_declaration(self):
        t = struct()["topology_declared_by_operator"]
        self.assertEqual((t["bba_present"], t["ethernet"], t["same_gamecube_as_run10"], t["same_gbp_as_run10"]),
                         ("YES", "DISCONNECTED", "YES", "YES"))
        self.assertIn("OPERATOR", t["source"])


class ThePrimaryReportingGate(unittest.TestCase):
    """GBP-VID-033: the gate that is NEW in run 11 (§V5.58.7)."""

    def test_nothing_dropped_nothing_truncated(self):
        h = struct()["log_header"]
        self.assertEqual((h["dropped"], h["truncated"]), (0, 0))
        self.assertIsNone(h["truncated_line"])
        self.assertLess(h["longest_payload"]["chars"], h["longest_payload"]["limit"])
        self.assertEqual(h["longest_payload"]["limit"], 248)

    def test_exactly_one_witelig_and_one_witelig2_both_complete(self):
        h, r = struct()["log_header"], struct()["reporting_records"]
        self.assertEqual(h["tag_counts"], {"WITELIG": 1, "WITELIG2": 1})
        self.assertEqual(set(r["WITELIG"]["fields"]), {"policy", "origin", "not_before_ms", "gated_at_init", "released",
                                                       "still_gated", "t_eligible", "ticks_control_to_eligible"})
        self.assertEqual(set(r["WITELIG2"]["fields"]), {"frames_seen_before_eligible", "disqualified_before_eligible",
                                                        "qual_streak_at_eligible"})
        self.assertEqual(set(r["WITELIG"]["fields"]) | set(r["WITELIG2"]["fields"]), CONTRACT_FIELDS)
        self.assertEqual(set(r["stream_0010_contract_fields"]), CONTRACT_FIELDS)
        self.assertTrue(r["WITELIG"]["complete"] and r["WITELIG2"]["complete"])
        self.assertLessEqual(r["WITELIG"]["payload_chars"], 248)
        self.assertLessEqual(r["WITELIG2"]["payload_chars"], 248)
        self.assertEqual(r["WITELIG2"]["seq"], r["WITELIG"]["seq"] + 1)

    def test_the_zero_is_read_directly_and_the_counters_agree(self):
        w, q = struct()["witelig"], struct()["witqual"]
        z = w["qual_streak_at_eligible"]
        self.assertEqual(z["direct_value"], 0)
        self.assertIn("PRESENT", z["direct_field"])
        self.assertTrue(z["agrees"])
        # the cross-check the pre-registration asked for, recomputed here from the recorded counters
        self.assertEqual(q["warmup_frames"] - w["frames_seen_before_eligible"], q["required"])
        self.assertEqual(q["qualify_frame"], w["frames_seen_before_eligible"] + q["required"] - 1)
        self.assertEqual(q["resets"], 0)
        self.assertEqual(q["warmup_disqualified"], w["disqualified_before_eligible"])

    def test_run_10_keeps_its_truncation_and_run_11_does_not(self):
        h10, h11 = run10()["log_header"], struct()["log_header"]
        self.assertEqual((h10["truncated"], h11["truncated"]), (1, 0))
        self.assertIn("WITELIG", h10["truncated_line"])
        self.assertEqual(struct()["comparison_vs_run10"]["log_truncated"], [1, 0])


class SourceGate(unittest.TestCase):
    def test_observed_contiguous_with_2048_intact_and_zero_invalid(self):
        v = struct()["official_vindex"]
        self.assertEqual(v["verdict"], "OBSERVED_CONTIGUOUS")
        self.assertEqual((v["observed"], v["intact"], v["invalid_canonical_strip"]), (2048, 2048, 0))
        self.assertEqual(v["observed_id_contiguous"], 2046)
        self.assertEqual(v["first_last_observed"], [73, 2120])

    def test_every_canonical_record_is_valid_and_contiguous(self):
        recs = struct()["records"]
        self.assertEqual(len(recs), 2048)
        self.assertTrue(all(r["valid_blocks"] == 40 and r["index_ok"] == 40 and r["invalid_by_reason"] == {} for r in recs))
        ids = [r["frame_id"] for r in recs]
        self.assertEqual((ids[0], ids[-1]), (73, 2120))
        self.assertTrue(all(b - a == 1 for a, b in zip(ids, ids[1:])))
        self.assertTrue(all(r["status"] == 0x18 for r in recs))
        self.assertEqual([r["frame_index"] for r in recs], list(range(LO, HI + 1)))

    def test_the_qual_projection_agrees_with_the_records(self):
        q = vqual.load(QUAL)
        self.assertEqual([r["frame_index"] for r in q["records"]], list(range(LO, HI + 1)))


class WitnessAndStartup(unittest.TestCase):
    def test_eligibility_and_window(self):
        w, q, t = struct()["witelig"], struct()["witqual"], struct()["timing_after_control_s"]
        self.assertEqual((w["policy"], w["origin"], w["not_before_ms"], w["gated_at_init"]), ("time_not_before", "control", 5000, 1))
        self.assertEqual((w["released"], w["still_gated"], w["ticks_control_to_eligible"]), (1, 0, 202505829))
        self.assertAlmostEqual(w["ticks_control_to_eligible"] / float(TB), 5.000143926, places=8)
        self.assertEqual((q["required"], q["resets"], q["first_record_frame"], q["window_first_block"]), (64, 0, 356, 0))
        self.assertAlmostEqual(t["first_retained_record"], 6.067192864, places=8)
        self.assertGreaterEqual(t["first_retained_record"] - t["eligibility"], 63 / 59.727)

    def test_startup_normal_under_400_ms_with_the_delta_vs_run_10_recorded(self):
        s = struct()["startup"]
        self.assertEqual((s["mode"], s["selftest_visible"], s["prehandler_wait_ms"], s["presented_synthetic"]), ("normal", 0, 0, 0))
        self.assertEqual(s["ticks_control_to_first_handoff"], 6688927)
        self.assertLess(s["ticks_control_to_first_handoff"] * 1000.0 / TB, 400.0)
        self.assertEqual(struct()["comparison_vs_run10"]["first_handoff_ticks"], [run10()["startup"]["ticks_control_to_first_handoff"], 6688927])
        self.assertEqual(6688927 - 6688750, 177)  # recorded, not a tolerance

    def test_transport_is_clean(self):
        t = struct()["transport"]
        self.assertEqual((t["errors"], t["transport_ok"], t["timeouts"], t["busy"], t["overflow"], t["uncertain"]), (0, 1, 0, 0, 0, 0))
        self.assertEqual(t["unmasks"], t["deliveries"])
        self.assertEqual(t["acks"], t["rearms"])
        self.assertEqual(t["stop"], "witness_target_reached")


class PolicyAOnTheRepairedBuild(unittest.TestCase):
    def test_container_and_identity(self):
        i = disp()
        self.assertEqual((i["life_overflow"], i["event_overflow"], i["drawdone_unmatched"], i["order_violations"]), (0, 0, 0, 0))
        self.assertEqual((i["decisions"], i["source_deferred_frames"], i["event_n"]), (2377, 54, 2431))
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

    def test_deferrals_depth_and_frozen_latency_gates(self):
        i = disp()
        m = {r["frame_index"]: r for r in i["life"] if r["frame_index"] != KEY}
        J = [m[k] for k in range(LO, HI)]
        dd = [r for r in J if r["life_flags"] & LF["EVER_DEFERRED"]]
        self.assertEqual((len(dd), sum(r["defer_attempts"] for r in dd), i["max_deferred_depth"]), (50, 128, 1))
        lat = sorted(r["t_decision"] - r["t_convert_done"] for r in J)
        p99, mx = pct(lat, 0.99) * 1000.0 / TB, lat[-1] * 1000.0 / TB
        self.assertLessEqual(p99, 1.0)
        self.assertLessEqual(mx, 2.5)
        self.assertAlmostEqual(p99, 0.486790, places=5)
        self.assertAlmostEqual(mx, 1.000914, places=5)

    def test_display_repeats_recorded_as_the_observation_they_are(self):
        # the count is recorded, never gated (§V5.58.7 CADENCE); this reproduces the fixture's own record
        m = {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}
        rt = [m[k]["retrace_decision"] for k in range(LO, HI)]
        d = [b - a for a, b in zip(rt, rt[1:])]
        hist = {k: d.count(k) for k in set(d)}
        self.assertEqual(hist, {int(k): v for k, v in struct()["policy_a"]["retrace_delta_hist"].items()})
        self.assertEqual(sum(x - 1 for x in d), struct()["policy_a"]["display_repeat_intervals"])
        self.assertIn("never a gate", struct()["policy_a"]["display_repeat_note"])


class TheComparisonWithRun10(unittest.TestCase):
    def test_the_comparison_records_both_runs_and_claims_no_mechanism(self):
        c = struct()["comparison_vs_run10"]
        self.assertEqual(c["build"], ["stream-0010", "stream-0011"])
        self.assertEqual(c["bba"], ["PRESENT", "PRESENT"])
        self.assertEqual(c["ethernet"], ["DISCONNECTED", "DISCONNECTED"])
        self.assertEqual(c["intact_invalid"], [[2048, 0], [2048, 0]])
        self.assertEqual(c["interior_drops"], [0, 0])
        self.assertEqual(c["reorder"], [0, 0])
        self.assertEqual(c["max_depth"], [1, 1])
        self.assertEqual(c["frozen_p99_max_ms"][0], run10()["comparison_vs_run9"]["frozen_p99_max_ms"][1])
        self.assertIn("not proof", c["note"])


if __name__ == "__main__":
    unittest.main()
