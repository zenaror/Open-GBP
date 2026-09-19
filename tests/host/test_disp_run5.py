"""
tests/host/test_disp_run5.py — the FIRST physical downstream trace, preserved as
a regression fixture (HARDWARE_TESTS §V5.47).

The 287 772 B `OGBPDISP1` sidecar is versioned, so every claim in
GBP-HW-194 … GBP-HW-200 is recomputed on every run of the suite, everywhere.
The 8.9 MB witness sidecar is not versioned, so the tests that need the source
join skip where the capture is absent — and say so rather than passing quietly.

WHY THE JOIN IS BY frame_index AND NOT BY THE in_window FLAG

GBP-VID-019: the flag covers 69..2116 while the OGBPIDX scientific window is
70..2117 — the same count, shifted one frame at each end, because the flag is
`gbp_vwitness_armed()` sampled at TAKE time and the witness arms earlier in the
same service cycle. The analyzer's `scientific()` inherits that. Nothing was
changed in this ingestion round, so these tests pin BOTH: the exact join that
the evidence used, and the divergence itself, so a future fix has to update a
test that states what it is fixing.
"""
import os
import statistics
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import vdisp     # noqa: E402
import vidxcap   # noqa: E402

DISP = os.path.join(ROOT, "captures", "fixtures",
                    "hw-gamecube-gbp-2026-09-19-stream-0007-run5-disp.bin")
DISP_SHA = "8bf23585543bbd386bc1e2362f6540a2ede1b507981b6c1ec1c49e14c8ca34a2"
CAP_SHA = "853c62a3687d43d9e0f487480e8c4b599d0f05122f255df6d69bd3371dd2aa87"
TB = 40500000
VI_PERIOD = 675675.0          # ticks, established by feasibility in GBP-HW-198
KEY = vdisp.KEY_NONE
_C = {}


def disp():
    if "d" not in _C:
        _C["d"] = vdisp.load(DISP)
    return _C["d"]


def capture():
    for d in ("logs", os.path.join("captures", "local")):
        p = os.path.join(ROOT, d, "GBP-VIDEO-004_stream-0007-run5-idxcap.bin")
        if os.path.exists(p):
            return p
    raise unittest.SkipTest("the run-5 witness capture is not on this machine")


def src_frames():
    if "s" not in _C:
        _C["s"] = {r["frame_index"] for r in vidxcap.load(capture())["records"]}
    return _C["s"]


def lifemap():
    return {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}


def events():
    return sorted([e for e in disp()["events"] if e["frame_index"] != KEY],
                  key=lambda e: e["ordinal"])


class TheArtifactIsTheOneThatRan(unittest.TestCase):
    def test_the_fixture_is_the_physical_sidecar_byte_for_byte(self):
        import hashlib
        with open(DISP, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), DISP_SHA)

    def test_the_container_is_intact(self):
        i = disp()
        self.assertEqual(i["build_id"], "stream-0007")
        self.assertEqual(i["commit"], "ddf8db6")
        self.assertEqual((i["life_n"], i["event_n"], i["decisions"]), (2114, 2114, 2114))
        self.assertEqual((i["life_overflow"], i["event_overflow"], i["drawdone_unmatched"]), (0, 0, 0))
        self.assertEqual((i["tb_hz"], i["tex_slots"], i["xfb_slots"]), (TB, 2, 2))
        self.assertEqual(i["header_crc32"], 0x443DD4D6)
        self.assertEqual(i["total_crc32"], 0xB90822F4)
        self.assertEqual(i["life_crc32"], 0xC4A9FCB3)
        self.assertEqual(i["event_crc32"], 0x0F23B179)
        self.assertTrue(vdisp.usable(i)["usable_for_disposition_claim"])


class TheExactScientificJoin(unittest.TestCase):
    """GBP-HW-195. By frame_index, never by the flag."""

    def test_the_disposition_identity_closes(self):
        src, life = src_frames(), lifemap()
        self.assertEqual(len(src), 2048)
        self.assertEqual((min(src), max(src)), (70, 2117))
        joined = [life[k] for k in src if k in life]
        missing = [k for k in src if k not in life]
        sel = sum(1 for r in joined if r["disposition"] == 1)
        hold = sum(1 for r in joined if r["disposition"] == 2)
        self.assertEqual((sel, hold, len(missing)), (2030, 17, 1))
        self.assertEqual(sel + hold + len(missing), len(src))

    def test_the_only_unjoined_frame_is_the_capture_edge(self):
        src, life = src_frames(), lifemap()
        missing = [k for k in src if k not in life]
        self.assertEqual(missing, [2117])
        self.assertEqual(missing[0], max(src), "it must be the LAST source record")

    def test_the_in_window_flag_is_one_frame_early_and_that_is_recorded(self):
        """GBP-VID-019. Pinned deliberately: this asserts the DEFECT, so a
        future fix cannot land without updating a test that names it."""
        inw = sorted(r["frame_index"] for r in disp()["life"] if r["life_flags"] & 0x01)
        self.assertEqual(len(inw), 2048)
        self.assertEqual((inw[0], inw[-1]), (69, 2116))
        self.assertEqual(disp()["window_first_frame"], 69)
        self.assertEqual(sorted(src_frames())[0], 70, "the source window starts one later")

    def test_the_analyzer_no_longer_substitutes_the_flag(self):
        """The correction. The flag set still contains 2031 SELECTED_NEW -- the
        sidecar is a correct file and is not rewritten -- but it is now exposed
        as WITNESS_ARMED_AT_TAKE, and the scientific population comes from the
        exact join, which is 2030."""
        flag = vdisp.witness_armed_at_take(disp())
        self.assertEqual(sum(1 for r in flag if r["disposition"] == 1), 2031)
        sci = vdisp.scientific(disp(), src_frames())
        self.assertEqual(sum(1 for r in sci if r["disposition"] == 1), 2030)
        with self.assertRaises(vdisp.DispError):
            vdisp.scientific(disp())          # no witness, no authority

    def test_the_report_states_both_and_confuses_neither(self):
        r = vdisp.format_report(disp(), capture())
        self.assertIn("WITNESS_ARMED_AT_TAKE", r)
        self.assertIn("NOT a population", r)
        self.assertIn("SCIENTIFIC WINDOW (exact OGBPIDXCAP1 frame_index join)", r)
        self.assertIn("SELECTED_NEW       2030", r)
        self.assertIn("no lifecycle       1", r)
        self.assertNotIn("SELECTED_NEW       2031", r)


class TheHolds(unittest.TestCase):
    """GBP-HW-196. One state, no exception."""

    SCI = [334, 336, 345, 609, 620, 891, 893, 904, 1175, 1177, 1188,
           1457, 1460, 1471, 1744, 2017, 2028]

    def holds(self):
        return [e for e in events() if e["decision"] == 2]

    def test_nineteen_holds_seventeen_of_them_scientific(self):
        h = [e["frame_index"] for e in self.holds()]
        self.assertEqual(h, [61, 63] + self.SCI)
        self.assertEqual([k for k in h if k in src_frames()], self.SCI)

    def test_every_hold_has_the_same_machine_state(self):
        life = lifemap()
        for e in self.holds():
            fi = e["frame_index"]
            self.assertEqual(vdisp.REASON[e["reason"]], "XFB_BUSY", fi)
            self.assertLess(e["xfb_target"], 0, fi)
            self.assertEqual({e["xfb_current"], e["xfb_pending"]}, {0, 1}, fi)
            self.assertEqual(e["newest_source"], KEY, fi)
            r = life[fi]
            self.assertTrue(r["life_flags"] & 0x04, "converted")
            self.assertTrue(r["life_flags"] & 0x08, "submitted")
            self.assertGreater(r["t_drawdone"], 0, "a DrawDone did arrive")

    def test_nothing_was_ever_queued_at_any_decision(self):
        """GBP-HW-196. Not only at the holds: at EVERY decision in the run."""
        self.assertEqual({e["newest_source"] for e in events()}, {KEY})


class TheStageOrder(unittest.TestCase):
    """GBP-HW-197, and the correction it forces on §V5.46.6."""

    def test_drawdone_always_follows_the_decision(self):
        rows = [r for r in lifemap().values() if r["t_drawdone"] and r["t_decision"]]
        self.assertEqual(len(rows), 2113)
        self.assertTrue(all(r["t_drawdone"] > r["t_decision"] for r in rows),
                        "a held frame was NOT 'already drawn' at the decision")

    def test_conversion_cost_does_not_distinguish_holds(self):
        life, src = lifemap(), src_frames()
        joined = [life[k] for k in src if k in life]
        sel = [r["convert_ticks"] for r in joined if r["disposition"] == 1]
        hold = [r["convert_ticks"] for r in joined if r["disposition"] == 2]
        self.assertEqual((len(sel), len(hold)), (2030, 17))
        # within 1 % of each other: H2 is not supported for these holds
        self.assertLess(abs(statistics.mean(sel) - statistics.mean(hold))
                        / statistics.mean(sel), 0.01)

    def test_no_frame_was_ever_refused_at_the_token_gate(self):
        self.assertEqual(sum(r["submit_refusals"] for r in lifemap().values()), 0)


class ThePhase(unittest.TestCase):
    """GBP-HW-198/199. The VI period is established by FEASIBILITY: a period is
    admissible only if every residual fits one window of its own width. A span
    ratio is biased by the phase difference between the first and last sample
    and produces residuals wider than the period."""

    def test_the_vi_period_is_admissible_and_ntsc(self):
        ev = events()
        def spread(P):
            v = [e["t"] - P * e["retrace"] for e in ev]
            return max(v) - min(v)
        self.assertLess(spread(VI_PERIOD), VI_PERIOD, "the frozen period must fit")
        self.assertGreater(spread(675531.65), 675531.65, "the span ratio must NOT fit")
        self.assertAlmostEqual(TB / VI_PERIOD, 59.94006, places=4)

    def test_every_hold_is_in_the_last_four_percent_of_the_interval(self):
        ev = events()
        origin = min(e["t"] - VI_PERIOD * e["retrace"] for e in ev)
        ph = {e["ordinal"]: e["t"] - origin - VI_PERIOD * e["retrace"] for e in ev}
        self.assertTrue(all(0 <= p < VI_PERIOD for p in ph.values()))
        hold = [ph[e["ordinal"]] / VI_PERIOD for e in ev if e["decision"] == 2]
        sel = [ph[e["ordinal"]] / VI_PERIOD for e in ev if e["decision"] == 1]
        self.assertGreater(min(hold), 0.96, "every hold is in the final 4 %")
        self.assertLess(min(sel), 0.01, "selects span the whole interval")
        band = sum(1 for x in sel if x >= min(hold))
        self.assertLess(band / len(sel), 0.05)

    def test_a_second_decision_in_one_retrace_is_always_a_hold(self):
        ev = events()
        prev = {b["ordinal"]: a for a, b in zip(ev, ev[1:])}
        same = [e for e in ev if e["ordinal"] in prev
                and prev[e["ordinal"]]["retrace"] == e["retrace"]]
        self.assertEqual(len(same), 16)
        self.assertTrue(all(e["decision"] == 2 for e in same))
        self.assertEqual(sum(1 for e in same if e["decision"] == 1), 0)


class TheBeat(unittest.TestCase):
    """GBP-HW-200 — CORROBORATED, not FACT."""

    @staticmethod
    def cluster(holds, th):
        """Consecutive holds separated by <= `th` source decisions. A fresh list
        per cluster: appending `cur` and then clearing it aliases every cluster
        to one object, which is a mistake this test made once and which made a
        broken grouping pass its own length check."""
        out, cur = [], [holds[0]]
        for a, b in zip(holds, holds[1:]):
            if b - a <= th:
                cur.append(b)
            else:
                out.append(cur)
                cur = [b]
        out.append(cur)
        return out

    def test_hold_recurrence_matches_the_source_vi_beat(self):
        recs = vidxcap.load(capture())["records"]
        f_src = (len(recs) - 1) * TB / (recs[-1]["t_first_block"] - recs[0]["t_first_block"])
        self.assertAlmostEqual(f_src, 59.727083, places=4)
        predicted = f_src / (TB / VI_PERIOD - f_src)
        self.assertAlmostEqual(predicted, 280.44, delta=0.5)
        holds = sorted(e["frame_index"] for e in events() if e["decision"] == 2)
        cl = self.cluster(holds, 20)
        self.assertEqual(len(cl), 8)
        self.assertEqual([len(c) for c in cl], [2, 3, 2, 3, 3, 3, 1, 2])
        cen = [statistics.mean(c) for c in cl]
        gaps = [b - a for a, b in zip(cen, cen[1:])]
        self.assertEqual(len(gaps), 7)
        self.assertAlmostEqual(statistics.mean(gaps), 280.07, delta=0.5)
        self.assertAlmostEqual(statistics.mean(gaps) / predicted, 1.0, delta=0.01)

    def test_the_clustering_is_stable_across_thresholds(self):
        holds = sorted(e["frame_index"] for e in events() if e["decision"] == 2)
        self.assertEqual({len(self.cluster(holds, t)) for t in (15, 20, 25, 30)}, {8},
                         "stable where it matters")
        self.assertGreater(len(self.cluster(holds, 10)), 8,
                           "and it fragments below that, which is reported")


if __name__ == "__main__":
    unittest.main()
