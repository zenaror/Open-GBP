"""
tests/host/test_disp_run7.py — the FIRST physical NORMAL-startup run, preserved
as a regression fixture (HARDWARE_TESTS §V5.53).

Two conclusions live here and they must not be merged:

  I.  NORMAL STARTUP passed every pre-registered machine gate: no synthetic
      hand-off, no wait, first real hand-off 165.154 ms after CONTROL.
  II. The STRUCTURAL scientific window opened 3.840 s after CONTROL, and the
      indexed-0003 stimulus only produced its first OGBPIDX frame at 4.845 s.
      Records 0..59 therefore hold startup content with no OGBPIDX framing.
      The frozen analyzer's verdict for the run is preserved EXACTLY as it
      printed it, composition included, and nothing here trims the window.

The 379 340 B OGBPDISP2 is versioned. The 8.9 MB witness is not; a 230 KB
structural projection of it is, carrying per-record canonical validity,
FRAME_ID and STATUS -- enough to pin every claim without a pixel.
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
DISP = os.path.join(FX, "hw-gamecube-gbp-2026-09-19-stream-0009-run7-disp.bin")
STRUCT = os.path.join(FX, "hw-gamecube-gbp-2026-09-19-idxcap-run7-struct.json")
DISP_SHA = "edf3842896e84618a1f38267015cbca284be5d1a6e0e7eff2584e574fe30ce45"
CAP_SHA = "1e502bc8cab4af28e129393acab2f5be007d0c62bbd7d76e8c06fc57232602e9"
TB = 40500000
KEY = vdisp.KEY_NONE
D = {v: k for k, v in vdisp.DISPOSITION.items()}
LF = {v: k for k, v in vdisp.LF}
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

    def test_it_names_the_normal_startup_build(self):
        i = disp()
        self.assertEqual((i["build_id"], i["commit"]), ("stream-0009", "59d2f57"))

    def test_the_struct_fixture_names_the_witness_it_projects(self):
        s = struct()
        self.assertEqual(s["source_sha256"], CAP_SHA)
        self.assertEqual(s["source_size"], 8946060)
        self.assertEqual(len(s["records"]), 2048)


class NormalStartupPassedItsMachineGates(unittest.TestCase):
    """Conclusion I. None of these depends on when the stimulus began."""

    def test_the_profile_that_ran_was_normal_and_clean(self):
        st = struct()["startup"]
        self.assertEqual(st["mode"], "normal")
        self.assertEqual(st["selftest_visible"], 0)
        self.assertEqual(st["prehandler_wait_ms"], 0)

    def test_nothing_synthetic_was_handed_to_the_vi(self):
        st = struct()["startup"]
        self.assertEqual(st["presented_synthetic"], 0)
        self.assertEqual(st["headless_submits"], 1, "but the self-test DID run")

    def test_the_selftest_ended_terminal_pending_not_selected(self):
        """Headless: taken, converted, drawn, never handed off. That is the
        literal truth and it is what the sidecar must say."""
        st = [r for r in disp()["life"] if r["frame_index"] == KEY]
        self.assertEqual(len(st), 1)
        self.assertTrue(st[0]["life_flags"] & LF["SELFTEST"])
        self.assertEqual(st[0]["disposition"], D["TERMINAL_PENDING"])

    def test_first_real_handoff_is_within_400_ms_of_control(self):
        st = struct()["startup"]
        ms = st["ticks_control_to_first_handoff"] * 1000.0 / st["tb_hz"]
        self.assertEqual(st["ticks_control_to_first_handoff"], 6688749)
        self.assertAlmostEqual(ms, 165.154296, places=5)
        self.assertLess(ms, 400.0)

    def test_the_first_real_frame_was_frame_index_2(self):
        self.assertEqual(struct()["startup"]["first_frame_index"], 2)
        m = {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}
        self.assertIn(2, m)
        self.assertEqual(m[2]["disposition"], D["SELECTED_NEW"])


class PolicyAWasCleanOverTheWholeRun(unittest.TestCase):
    """Total-run counters: diagnostic evidence, no population invented."""

    def test_the_container_is_intact_under_the_v2_identity(self):
        i = disp()
        self.assertEqual((i["life_overflow"], i["event_overflow"], i["drawdone_unmatched"],
                          i["order_violations"]), (0, 0, 0, 0))
        self.assertEqual(i["decisions"] + i["source_deferred_frames"], i["event_n"])
        self.assertEqual((i["decisions"], i["source_deferred_frames"], i["event_n"]),
                         (2244, 44, 2288))
        self.assertTrue(vdisp.usable(i)["usable_for_disposition_claim"])

    def test_terminal_pending_in_the_header_is_two_and_the_log_line_is_pre_finish(self):
        """DISPSRC prints terminal_pending=0 because it is emitted BEFORE
        gbp_vdisp_finish(); the header is written after. Both are true. The
        two are the headless self-test and frame 2270, the last frame taken."""
        i = disp()
        self.assertEqual(i["terminal_pending"], 2)
        tp = sorted(r["frame_index"] for r in i["life"] if r["disposition"] == D["TERMINAL_PENDING"])
        self.assertEqual(tp, [2270, KEY])

    def test_every_published_frame_was_handed_off_in_order(self):
        real = [r for r in disp()["life"] if r["frame_index"] != KEY]
        handed = sorted([r for r in real if r["disposition"] == D["SELECTED_NEW"]],
                        key=lambda r: r["t_decision"])
        seq = [r["frame_index"] for r in handed]
        self.assertEqual(len(seq), 2244)
        self.assertEqual(seq, sorted(seq), "strictly increasing")
        self.assertEqual(len(seq), len(set(seq)), "no duplicate hand-off")

    def test_the_gaps_in_the_total_sequence_are_unpublished_source_frames(self):
        """24 indices are absent between 2 and 2269. Every one of them has NO
        lifecycle: the source layer never published it (13 incomplete + 13
        anomaly, minus frames 0 and 1 which precede the first take). That is
        an upstream fact, not a Policy-A drop, and none falls inside the
        frozen scientific join."""
        m = {r["frame_index"] for r in disp()["life"] if r["frame_index"] != KEY}
        handed = sorted(f for f in m)
        gaps = [x for a, b in zip(handed, handed[1:]) for x in range(a + 1, b)]
        self.assertEqual(len(gaps), 24)
        self.assertFalse([g for g in gaps if g in m])
        self.assertFalse([g for g in gaps if 223 <= g <= 2270])

    def test_deferrals_all_resolved_next_retrace_depth_one(self):
        i = disp()
        dd = [r for r in i["life"] if r["life_flags"] & LF["EVER_DEFERRED"]]
        self.assertEqual(len(dd), 44)
        self.assertEqual(sum(r["defer_attempts"] for r in dd), 108)
        self.assertTrue(all(r["disposition"] == D["SELECTED_NEW"] for r in dd))
        self.assertEqual(i["max_deferred_depth"], 1)
        ev = {e["frame_index"]: e for e in i["events"] if e["decision"] == D["DEFERRED"]}
        for r in dd:
            self.assertEqual(r["retrace_decision"], ev[r["frame_index"]]["retrace"] + 1)

    def test_latency_gates_pass_over_all_handoffs(self):
        handed = [r for r in disp()["life"]
                  if r["frame_index"] != KEY and r["disposition"] == D["SELECTED_NEW"]]
        lat = sorted(r["t_decision"] - r["t_convert_done"] for r in handed)
        self.assertLessEqual(pct(lat, 0.99) * 1000.0 / TB, 1.0)
        self.assertLessEqual(lat[-1] * 1000.0 / TB, 2.5)


class TheFrozenAnalyzerVerdictIsPreservedVerbatim(unittest.TestCase):
    """Conclusion II. The label is the analyzer's, composition included."""

    def test_the_official_verdict_and_its_composition(self):
        v = struct()["official_vindex"]
        self.assertEqual(v["verdict"], "OBSERVED_CONTIGUOUS")
        self.assertEqual((v["observed"], v["intact"]), (2048, 1988))
        self.assertEqual(v["invalid_canonical_strip"], 60)
        self.assertEqual(v["observed_id_contiguous"], 1986)
        self.assertEqual(v["first_last_observed"], [0, 1987])

    def test_records_0_to_59_carry_no_ogbpidx_framing_at_all(self):
        recs = struct()["records"]
        early = recs[:60]
        self.assertTrue(all(r["valid_blocks"] == 0 for r in early))
        self.assertTrue(all(r["frame_id"] is None for r in early))
        by = {}
        for r in early:
            for k, n in r["invalid_by_reason"].items():
                by[k] = by.get(k, 0) + n
        self.assertEqual(sum(by.values()), 2400)
        self.assertEqual(set(by), {"sync", "symbol"})

    def test_the_stimulus_enters_at_record_60_with_status_7f(self):
        recs = struct()["records"]
        self.assertEqual((recs[60]["frame_index"], recs[60]["frame_id"], recs[60]["status"]), (283, 0, 0x7F))
        self.assertEqual((recs[61]["frame_index"], recs[61]["frame_id"], recs[61]["status"]), (284, 1, 0x7F))
        self.assertEqual((recs[62]["frame_index"], recs[62]["frame_id"], recs[62]["status"]), (285, 2, 0x18))

    def test_the_tail_is_a_diagnostic_and_contiguous(self):
        """62..2047: 1986 records, FRAME_ID 2..1987, every delta +1. This is
        evidence of WHY the population changed. It is NOT the run's verdict."""
        tail = struct()["records"][62:]
        self.assertEqual(len(tail), 1986)
        self.assertTrue(all(r["valid_blocks"] == 40 and r["index_ok"] == 40 for r in tail))
        ids = [r["frame_id"] for r in tail]
        self.assertEqual((ids[0], ids[-1]), (2, 1987))
        self.assertTrue(all(b - a == 1 for a, b in zip(ids, ids[1:])))
        self.assertTrue(all(r["status"] == 0x18 for r in tail))

    def test_the_window_opened_one_second_before_the_stimulus(self):
        t = struct()["timing_after_control_s"]
        self.assertAlmostEqual(t["first_retained_record"], 3.84047, places=4)
        self.assertAlmostEqual(t["stimulus_id0"], 4.84498, places=4)
        self.assertGreater(t["stimulus_id0"] - t["first_retained_record"], 1.0)

    def test_qualification_was_structural_and_recorded_the_transient(self):
        q = struct()["witqual"]
        self.assertEqual((q["required"], q["resets"], q["warmup_frames"], q["first_record_frame"]),
                         (64, 12, 223, 223))


if __name__ == "__main__":
    unittest.main()
