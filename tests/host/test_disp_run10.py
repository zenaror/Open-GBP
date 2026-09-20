"""
tests/host/test_disp_run10.py — GBP-BBA-001 / RUN 10: the exact run-9 binary
with the Broadband Adapter physically PRESENT and Ethernet DISCONNECTED
(HARDWARE_TESTS §V5.57). A paired topology control, preserved as a fixture.

The topology facts come from the operator's declaration, recorded in the
fixture metadata as such; nothing here derives them from files. The frozen
analyzer's verdict is kept WITH its composition. The known WITELIG truncation
(GBP-VID-033) is EXPECTED in this binary and is asserted as such — not as a
regression. Run-9 tests are not touched.
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
DISP = os.path.join(FX, "hw-gamecube-gbp-2026-09-20-stream-0010-run10-disp.bin")
STRUCT = os.path.join(FX, "hw-gamecube-gbp-2026-09-20-idxcap-run10-struct.json")
RUN9 = os.path.join(FX, "hw-gamecube-gbp-2026-09-20-idxcap-run9-struct.json")
DISP_SHA = "53c675725f074a7c4fa4b874d5c0240c888dd9cb5dd1eadc15681a3c1bb89235"
DOL_SHA = "6b57d6696cf718baaac83cd0b9631c672bbe756f842e42bfd12d7a0ee3736180"
STIM_SHA = "9f04916b88308e7045f207136f5fc681e5bab33ac9b22d2e19be12c16b8d9cc2"
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


class TheArtifactAndTopology(unittest.TestCase):
    def test_the_disp_fixture_is_the_physical_sidecar(self):
        with open(DISP, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), DISP_SHA)

    def test_it_is_the_exact_run_9_binary_and_stimulus(self):
        i, s = disp(), struct()
        self.assertEqual((i["build_id"], i["commit"]), ("stream-0010", "fbaea00"))
        self.assertEqual(s["dol"]["sha256"], DOL_SHA)
        self.assertEqual(s["stimulus"]["sha256"], STIM_SHA)
        r9 = json.load(open(RUN9))
        self.assertEqual(r9["dol"]["sha256"], DOL_SHA, "the control reuses run 9's exact DOL")

    def test_the_topology_is_the_operators_declaration(self):
        t = struct()["topology_declared_by_operator"]
        self.assertEqual((t["bba_present"], t["ethernet"], t["same_gamecube_as_run9"], t["same_gbp_as_run9"]),
                         ("YES", "DISCONNECTED", "YES", "YES"))
        self.assertIn("OPERATOR", t["source"])

    def test_the_supplied_bba_names_are_kept_as_metadata(self):
        raw = struct()["raw"]
        self.assertEqual(raw["log"]["supplied_name"], "GBP-VIDEO-004_stream-0010-bba.log")
        self.assertTrue(raw["idxcap"]["archived_as"].endswith("-run10-idxcap.bin"))
        self.assertEqual(raw["idxcap"]["sha256"], "1cba0fd7096a5d43f801378cabd9eaf9a9711492abf1601ffa0f54ce0ae0e95f")


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


class WitnessAndStartup(unittest.TestCase):
    def test_eligibility_and_window(self):
        w, q, t = struct()["witelig"], struct()["witqual"], struct()["timing_after_control_s"]
        self.assertEqual((w["released"], w["still_gated"], w["ticks_control_to_eligible"]), (1, 0, 202506351))
        self.assertAlmostEqual(w["ticks_control_to_eligible"] / float(TB), 5.000156815, places=8)
        self.assertEqual(q["warmup_frames"] - w["frames_seen_before_eligible"], q["required"])
        self.assertEqual(q["qualify_frame"], w["frames_seen_before_eligible"] + q["required"] - 1)
        self.assertEqual((q["resets"], q["first_record_frame"], q["window_first_block"]), (0, 356, 0))
        self.assertAlmostEqual(t["first_retained_record"], 6.067209136, places=8)
        self.assertGreaterEqual(t["first_retained_record"] - t["eligibility"], 63 / 59.727)

    def test_the_known_witelig_truncation_recurred_and_is_not_a_regression(self):
        h, w = struct()["log_header"], struct()["witelig"]
        self.assertEqual((h["dropped"], h["truncated"]), (0, 1))
        self.assertIn("WITELIG", h["truncated_line"])
        self.assertEqual(w["qual_streak_at_eligible"]["semantic_value"], 0)
        self.assertIn("NOT a BBA regression", w["qual_streak_at_eligible"]["direct_field"])

    def test_startup_under_400_ms_and_within_17_ticks_of_run_9(self):
        s = struct()["startup"]
        self.assertEqual((s["mode"], s["selftest_visible"], s["prehandler_wait_ms"], s["presented_synthetic"]), ("normal", 0, 0, 0))
        self.assertEqual(s["ticks_control_to_first_handoff"], 6688750)
        self.assertLess(s["ticks_control_to_first_handoff"] * 1000.0 / TB, 400.0)
        self.assertEqual(6688750 - 6688767, -17)


class PolicyAOnTheBbaPresentTopology(unittest.TestCase):
    def test_container_and_identity(self):
        i = disp()
        self.assertEqual((i["life_overflow"], i["event_overflow"], i["drawdone_unmatched"], i["order_violations"]), (0, 0, 0, 0))
        self.assertEqual((i["decisions"], i["source_deferred_frames"], i["event_n"]), (2377, 50, 2427))
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
        self.assertEqual((len(dd), sum(r["defer_attempts"] for r in dd), i["max_deferred_depth"]), (46, 112, 1))
        lat = sorted(r["t_decision"] - r["t_convert_done"] for r in J)
        p99, mx = pct(lat, 0.99) * 1000.0 / TB, lat[-1] * 1000.0 / TB
        self.assertLessEqual(p99, 1.0)
        self.assertLessEqual(mx, 2.5)
        self.assertAlmostEqual(p99, 0.471778, places=5)
        self.assertAlmostEqual(mx, 1.000765, places=5)

    def test_seven_display_repeats_recorded_as_observation(self):
        m = {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}
        rt = [m[k]["retrace_decision"] for k in range(LO, HI)]
        d = [b - a for a, b in zip(rt, rt[1:])]
        self.assertEqual({k: d.count(k) for k in set(d)}, {1: 2039, 2: 7})
        self.assertEqual(struct()["comparison_vs_run9"]["display_repeats"], [7, 7])


class ThePairedControl(unittest.TestCase):
    def test_the_comparison_records_both_runs_and_claims_no_mechanism(self):
        c = struct()["comparison_vs_run9"]
        self.assertEqual(c["bba"], ["ABSENT", "PRESENT"])
        self.assertEqual(c["intact_invalid"], [[2048, 0], [2048, 0]])
        self.assertEqual(c["interior_drops"], [0, 0])
        self.assertEqual(c["reorder"], [0, 0])
        self.assertEqual(c["first_handoff_ticks"], [6688767, 6688750])
        self.assertIn("not proof", c["note"])


if __name__ == "__main__":
    unittest.main()
