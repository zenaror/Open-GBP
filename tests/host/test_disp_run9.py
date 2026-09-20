"""
tests/host/test_disp_run9.py — RUN 9, the first hardware of the research
not-before gate (HARDWARE_TESTS §V5.56), preserved as a regression fixture.

Two versioned projections carry the claims without the 8.9 MB witness or the
private log: the 401 796 B OGBPDISP2 and a structural projection of the witness
with per-record canonical validity, FRAME_ID, STATUS, the frozen analyzer's
verdict WITH ITS COMPOSITION, the WITELIG/WITQUAL/STARTUP fields, and the
text-truncation finding. Nothing here weakens the run-7 or run-8 fixtures.
"""
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import vdisp  # noqa: E402

FX = os.path.join(ROOT, "captures", "fixtures")
DISP = os.path.join(FX, "hw-gamecube-gbp-2026-09-20-stream-0010-run9-disp.bin")
STRUCT = os.path.join(FX, "hw-gamecube-gbp-2026-09-20-idxcap-run9-struct.json")
DISP_SHA = "7a4b032aecfc9af5787d6c099967dcffc2942e0b798b2b81d25c4be445994c67"
TB = 40500000
KEY = vdisp.KEY_NONE
D = {v: k for k, v in vdisp.DISPOSITION.items()}
LF = {v: k for k, v in vdisp.LF}
LO, HI = 356, 2403
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


def pct(s, q):
    n = len(s)
    return s[min(n - 1, int(n * q))] if n else None


class TheArtifactIsTheOneThatRan(unittest.TestCase):
    def test_the_disp_fixture_is_the_physical_sidecar(self):
        with open(DISP, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), DISP_SHA)

    def test_identity_and_metadata(self):
        i, s = disp(), struct()
        self.assertEqual((i["build_id"], i["commit"]), ("stream-0010", "fbaea00"))
        self.assertEqual(s["dol"]["sha256"], "6b57d6696cf718baaac83cd0b9631c672bbe756f842e42bfd12d7a0ee3736180")
        self.assertEqual(s["stimulus"]["sha256"], "9f04916b88308e7045f207136f5fc681e5bab33ac9b22d2e19be12c16b8d9cc2")
        self.assertEqual(s["topology"]["bba"], "DISCONNECTED")
        self.assertEqual(s["raw"]["idxcap"]["sha256"], "247bae664896d0005877d8236e56ef3ac19936426cec7c41fcc85978e8eac7d1")
        self.assertEqual(len(s["records"]), 2048)


class TheFrozenAnalyzerCompositionIsTheResult(unittest.TestCase):
    """Gate H: the label alone is insufficient."""

    def test_observed_contiguous_with_2048_intact_and_zero_invalid(self):
        v = struct()["official_vindex"]
        self.assertEqual(v["verdict"], "OBSERVED_CONTIGUOUS")
        self.assertEqual((v["observed"], v["intact"], v["invalid_canonical_strip"]), (2048, 2048, 0))
        self.assertEqual(v["observed_id_contiguous"], 2046)
        self.assertEqual(v["first_last_observed"], [73, 2120])

    def test_every_retained_strip_is_valid_under_the_frozen_rules(self):
        """Gate I, from the projection: 40/40 valid, index ok, one FRAME_ID and
        STATUS 0x18 per record, IDs 73..2120 with every delta +1."""
        recs = struct()["records"]
        self.assertTrue(all(r["valid_blocks"] == 40 and r["index_ok"] == 40 for r in recs))
        self.assertTrue(all(r["invalid_by_reason"] == {} for r in recs))
        ids = [r["frame_id"] for r in recs]
        self.assertEqual((ids[0], ids[-1]), (73, 2120))
        self.assertTrue(all(b - a == 1 for a, b in zip(ids, ids[1:])))
        self.assertTrue(all(r["status"] == 0x18 for r in recs))
        self.assertEqual([r["frame_index"] for r in recs], list(range(LO, HI + 1)))

    def test_unlike_run_7_there_is_no_pre_stimulus_content(self):
        self.assertEqual(sum(1 for r in struct()["records"] if r["valid_blocks"] < 40), 0)


class TheGateDidWhatItWasBuiltFor(unittest.TestCase):
    def test_eligibility_at_five_seconds_after_control(self):
        w = struct()["witelig"]
        self.assertEqual((w["policy"], w["origin"], w["not_before_ms"], w["released"], w["still_gated"]),
                         ("time_not_before", "control", 5000, 1, 0))
        self.assertEqual(w["ticks_control_to_eligible"], 202506346)
        s = w["ticks_control_to_eligible"] / float(TB)
        self.assertAlmostEqual(s, 5.000156691, places=8)
        self.assertGreaterEqual(s, 5.0)
        self.assertLess(s - 5.0, 0.001, "overshoot must be within the pump cadence")

    def test_streak_zero_is_exactly_derivable_from_the_counters(self):
        """Gate D. The DIRECT field was lost to the ringlog line limit; the
        SEMANTIC value is exact: 356 - 292 = 64 = required, resets 0, and the
        26 disqualified frames all precede eligibility."""
        w, q = struct()["witelig"], struct()["witqual"]
        self.assertEqual(w["qual_streak_at_eligible"]["semantic_value"], 0)
        self.assertEqual(q["warmup_frames"] - w["frames_seen_before_eligible"], q["required"])
        self.assertEqual(q["qualify_frame"], w["frames_seen_before_eligible"] + q["required"] - 1)
        self.assertEqual(q["resets"], 0)
        self.assertEqual(q["warmup_disqualified"], w["disqualified_before_eligible"])
        self.assertIn("LOST", w["qual_streak_at_eligible"]["direct_field"])

    def test_the_window_opened_after_eligibility_plus_64_at_block_0(self):
        q, t = struct()["witqual"], struct()["timing_after_control_s"]
        self.assertEqual((q["qualify_frame"], q["first_record_frame"], q["window_first_block"]), (355, 356, 0))
        self.assertAlmostEqual(t["first_retained_record"], 6.067209383, places=8)
        # 64 CLOSES after eligibility span at least 63 frame periods (the first
        # close may be a frame already in progress), never fewer.
        self.assertGreaterEqual(t["first_retained_record"] - t["eligibility"], 63 / 59.727)
        self.assertAlmostEqual(t["eligibility_to_first_record"], 1.067052692, places=8)
        self.assertEqual(struct()["records"][0]["frame_index"], 356)

    def test_the_transient_was_still_recorded_and_the_log_says_truncated_once(self):
        h = struct()["log_header"]
        self.assertEqual((h["dropped"], h["truncated"]), (0, 1))
        self.assertIn("WITELIG", h["truncated_line"])
        self.assertEqual(struct()["witelig"]["disqualified_before_eligible"], 26)


class StartupAndPolicyAWereUntouchedByTheGate(unittest.TestCase):
    def test_startup_within_18_ticks_of_run_7(self):
        s = struct()["startup"]
        self.assertEqual((s["mode"], s["selftest_visible"], s["prehandler_wait_ms"], s["presented_synthetic"], s["headless_submits"]),
                         ("normal", 0, 0, 0, 1))
        self.assertEqual(s["ticks_control_to_first_handoff"], 6688767)
        self.assertLess(s["ticks_control_to_first_handoff"] * 1000.0 / TB, 400.0)
        self.assertLessEqual(abs(6688767 - 6688749), 18)

    def test_container_and_identity(self):
        i = disp()
        self.assertEqual((i["life_overflow"], i["event_overflow"], i["drawdone_unmatched"], i["order_violations"]), (0, 0, 0, 0))
        self.assertEqual((i["decisions"], i["source_deferred_frames"], i["event_n"]), (2377, 50, 2427))
        self.assertEqual(i["decisions"] + i["source_deferred_frames"], i["event_n"])
        self.assertTrue(vdisp.usable(i)["usable_for_disposition_claim"])
        tp = [r["frame_index"] for r in i["life"] if r["disposition"] == D["TERMINAL_PENDING"]]
        self.assertEqual(tp, [KEY], "only the headless self-test is terminal-pending")

    def test_exact_join_2047_selected_new_and_one_capture_edge(self):
        m = {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}
        joined = [k for k in range(LO, HI + 1) if k in m]
        missing = [k for k in range(LO, HI + 1) if k not in m]
        self.assertEqual(len(joined), 2047)
        self.assertEqual(missing, [HI])
        self.assertTrue(all(m[k]["disposition"] == D["SELECTED_NEW"] for k in joined))
        seq = [r["frame_index"] for r in sorted((m[k] for k in joined), key=lambda r: r["t_decision"])]
        self.assertEqual(seq, list(range(LO, HI)))

    def test_deferrals_depth_and_latency_gates(self):
        i = disp()
        m = {r["frame_index"]: r for r in i["life"] if r["frame_index"] != KEY}
        J = [m[k] for k in range(LO, HI) ]
        dd = [r for r in J if r["life_flags"] & LF["EVER_DEFERRED"]]
        self.assertEqual((len(dd), sum(r["defer_attempts"] for r in dd)), (46, 112))
        self.assertEqual((i["source_deferred_frames"], i["source_defer_attempts"], i["max_deferred_depth"]), (50, 124, 1))
        ev = {e["frame_index"]: e for e in i["events"] if e["decision"] == D["DEFERRED"]}
        self.assertTrue(all(r["retrace_decision"] == ev[r["frame_index"]]["retrace"] + 1 for r in dd))
        lat = sorted(r["t_decision"] - r["t_convert_done"] for r in J)
        self.assertLessEqual(pct(lat, 0.99) * 1000.0 / TB, 1.0)
        self.assertLessEqual(lat[-1] * 1000.0 / TB, 2.5)
        self.assertAlmostEqual(pct(lat, 0.99) * 1000.0 / TB, 0.472000, places=5)

    def test_seven_display_repeats_fourth_run_running(self):
        m = {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}
        rt = [m[k]["retrace_decision"] for k in range(LO, HI)]
        d = [b - a for a, b in zip(rt, rt[1:])]
        self.assertEqual({k: d.count(k) for k in set(d)}, {1: 2039, 2: 7})
        self.assertEqual(disp()["source_dropped_interior"], 0)


if __name__ == "__main__":
    unittest.main()
