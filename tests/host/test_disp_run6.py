"""
tests/host/test_disp_run6.py — the FIRST physical Policy-A run, preserved as a
regression fixture (HARDWARE_TESTS §V5.50).

`stream-0008` is the run that answers the question `stream-0007` raised. The
357 524 B `OGBPDISP2` sidecar is versioned, so every number GBP-HW-202 …
GBP-HW-211 rests on is recomputed wherever the suite runs. The 8.9 MB witness
capture is not versioned, so the tests that need the exact source join skip
where it is absent — loudly, never quietly.

WHAT THIS FILE IS FOR

Run 5 lost 17 interior source frames downstream and needed 24 repeated VI
intervals. Run 6, same stimulus and same VI, lost none and needed 7 — and
24 − 7 = 17 is not a coincidence, it is the whole causal claim. These tests pin
that arithmetic, the ordering reconstruction, the pre-registered latency gates
and the counter semantics, so a future change to the analyzer has to edit a
test that says what it is changing.

THE JOIN IS BY frame_index, NEVER BY THE ARMED BIT (GBP-VID-019), and the
percentile convention is the pre-registered one from tools/vpace.py.
"""
import hashlib
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import vdisp     # noqa: E402
import vidxcap   # noqa: E402
import vpace     # noqa: E402

DISP = os.path.join(ROOT, "captures", "fixtures",
                    "hw-gamecube-gbp-2026-09-19-stream-0008-run6-disp.bin")
DISP_SHA = "36b684610b32219d9585126fba8abc4ee58e31de0a6d8044ccca4fb75803a44e"
CAP_SHA = "311a26a78a19d8573b54fadb463dc50fd411984b97d8679287066e5de45a8d54"
DOL_SHA = "a9efe181d46928d11a20623276a77f352db45b9795681173185e9a60d4e81282"
TB = 40500000
VI_PERIOD = 675675.0            # re-derived from THIS run, GBP-HW-209
KEY = vdisp.KEY_NONE
SCI_LO, SCI_HI = 70, 2117       # source scientific population, inclusive
OVERLAP_HI = 2116               # last frame the consumer was offered
# Derived from the analyzer's own tables, so the NAME->code mapping is pinned
# here too: a silent renumbering of a disposition would fail these tests.
D = {v: k for k, v in vdisp.DISPOSITION.items()}
R = {v: k for k, v in vdisp.REASON.items()}
LF = {v: k for k, v in vdisp.LF}
F_EVER_DEFERRED = LF["EVER_DEFERRED"]
_C = {}


def disp():
    if "d" not in _C:
        _C["d"] = vdisp.load(DISP)
    return _C["d"]


def capture():
    for d in ("logs", os.path.join("captures", "local")):
        for n in ("GBP-VIDEO-004_stream-0008-run6-idxcap.bin",
                  "GBP-VIDEO-004_stream-0008-idxcap.bin"):
            p = os.path.join(ROOT, d, n)
            if os.path.exists(p):
                return p
    raise unittest.SkipTest("the run-6 witness capture is not on this machine")


def src_frames():
    if "s" not in _C:
        _C["s"] = {r["frame_index"] for r in vidxcap.load(capture())["records"]}
    return _C["s"]


def lifemap():
    return {r["frame_index"]: r for r in disp()["life"] if r["frame_index"] != KEY}


def overlap():
    """The consumer-reached scientific frames, by exact frame_index."""
    m = lifemap()
    return [m[k] for k in range(SCI_LO, OVERLAP_HI + 1)]


def handed():
    return sorted([r for r in overlap() if r["disposition"] == D["SELECTED_NEW"]],
                  key=lambda r: r["t_decision"])


def pct(s, q):
    """The PRE-REGISTERED convention, copied from tools/vpace.py."""
    n = len(s)
    return s[min(n - 1, int(n * q))] if n else None


class TheArtifactIsTheOneThatRan(unittest.TestCase):
    def test_the_fixture_is_the_physical_sidecar_byte_for_byte(self):
        with open(DISP, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), DISP_SHA)

    def test_the_sidecar_names_the_build_that_produced_it(self):
        i = disp()
        self.assertEqual(i["test_id"], "GBP-VIDEO-004")
        self.assertEqual(i["build_id"], "stream-0008")
        self.assertEqual(i["commit"], "5126a19")

    def test_the_witness_capture_is_the_one_that_was_analysed(self):
        with open(capture(), "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), CAP_SHA)


class TheContainerIsIntact(unittest.TestCase):
    def test_it_is_version_two(self):
        self.assertEqual(disp()["version"], 2)
        self.assertEqual(disp()["header_size"], 0x140)
        self.assertEqual(disp()["life_record_size"], 128)
        self.assertEqual(disp()["event_record_size"], 40)

    def test_nothing_overflowed_and_no_token_was_unmatched(self):
        i = disp()
        self.assertEqual(i["life_overflow"], 0)
        self.assertEqual(i["event_overflow"], 0)
        self.assertEqual(i["drawdone_unmatched"], 0)
        self.assertEqual(i["order_violations"], 0)

    def test_the_v2_event_identity_holds(self):
        """decisions + deferred_frames == event_n. The v1 rule (decisions ==
        event_n) is FALSE here, and a readiness check left at the v1 form is
        exactly what reported this structurally perfect trace as unusable."""
        i = disp()
        self.assertEqual(i["decisions"] + i["source_deferred_frames"], i["event_n"])
        self.assertEqual((i["decisions"], i["source_deferred_frames"], i["event_n"]),
                         (2114, 51, 2165))
        self.assertNotEqual(i["decisions"], i["event_n"])

    def test_the_trace_is_usable_for_a_disposition_claim(self):
        u = vdisp.usable(disp())
        self.assertTrue(u["usable_for_disposition_claim"], u["reasons"])

    def test_the_header_counters_are_what_the_run_reported(self):
        i = disp()
        self.assertEqual(i["source_handoffs"], 2114)
        self.assertEqual(i["source_deferred_frames"], 51)
        self.assertEqual(i["source_defer_attempts"], 129)
        self.assertEqual(i["source_dropped_interior"], 0)
        self.assertEqual(i["terminal_pending"], 0)
        self.assertEqual(i["max_deferred_depth"], 1)


class TheScientificJoinIsExact(unittest.TestCase):
    def test_the_source_population_is_2048_frames(self):
        s = src_frames()
        self.assertEqual(len(s), 2048)
        self.assertEqual((min(s), max(s)), (SCI_LO, SCI_HI))

    def test_2047_of_them_reached_the_consumer_and_one_is_the_stop_edge(self):
        s, m = src_frames(), lifemap()
        joined = sorted(s & set(m))
        missing = sorted(s - set(m))
        self.assertEqual(len(joined), 2047)
        self.assertEqual((joined[0], joined[-1]), (SCI_LO, OVERLAP_HI))
        self.assertEqual(missing, [SCI_HI],
                         "the only source frame without a lifecycle is the stop edge")
        self.assertEqual(len(s), len(joined) + len(missing))

    def test_the_selftest_can_never_enter_the_join(self):
        st = [r for r in disp()["life"] if r["frame_index"] == KEY]
        self.assertEqual(len(st), 1)
        self.assertTrue(st[0]["life_flags"] & LF["SELFTEST"])
        self.assertFalse(st[0]["life_flags"] & LF["WITNESS_ARMED_AT_TAKE"])
        self.assertNotIn(KEY, src_frames())


class PolicyAPreservedEveryInteriorSourceFrame(unittest.TestCase):
    def test_all_2047_were_handed_off(self):
        o = overlap()
        self.assertEqual(len(o), 2047)
        self.assertTrue(all(r["disposition"] == D["SELECTED_NEW"] for r in o))

    def test_there_is_no_hold_no_overrun_and_no_abandonment(self):
        seen = {r["disposition"] for r in overlap()}
        self.assertEqual(seen, {D["SELECTED_NEW"]})

    def test_nothing_was_left_deferred_or_open_at_the_stop(self):
        o = overlap()
        self.assertEqual(sum(1 for r in o if r["disposition"] == D["DEFERRED"]), 0)
        self.assertEqual(sum(1 for r in o if r["disposition"] == D["OPEN"]), 0)
        self.assertEqual(disp()["terminal_pending"], 0)

    def test_the_handoff_order_reconstructs_to_exactly_70_through_2116(self):
        """Not `order_violations == 0` -- the sequence itself, rebuilt from the
        decision timestamps. This was the pre-hardware risk: the offer used to
        scan from slot 0, so a newer frame could overtake a deferred older one."""
        seq = [r["frame_index"] for r in handed()]
        self.assertEqual(seq, list(range(SCI_LO, OVERLAP_HI + 1)))
        self.assertEqual(len(seq), len(set(seq)), "no frame handed off twice")

    def test_no_deferred_frame_was_overtaken(self):
        seq = [r["frame_index"] for r in handed()]
        pos = {f: i for i, f in enumerate(seq)}
        for r in overlap():
            if r["life_flags"] & F_EVER_DEFERRED:
                after = seq[pos[r["frame_index"]] + 1:]
                self.assertFalse([x for x in after if x < r["frame_index"]],
                                 "frame %d was overtaken" % r["frame_index"])


class TheDeferralPopulation(unittest.TestCase):
    def test_48_scientific_frames_deferred_over_124_attempts(self):
        d = [r for r in overlap() if r["life_flags"] & F_EVER_DEFERRED]
        self.assertEqual(len(d), 48)
        self.assertEqual(sum(r["defer_attempts"] for r in d), 124)

    def test_every_deferred_frame_was_eventually_handed_off(self):
        d = [r for r in overlap() if r["life_flags"] & F_EVER_DEFERRED]
        self.assertTrue(all(r["disposition"] == D["SELECTED_NEW"] for r in d))

    def test_the_queue_never_grew_past_one(self):
        self.assertEqual(disp()["max_deferred_depth"], 1)

    def test_every_deferral_resolved_at_the_very_next_retrace(self):
        """The mechanism, seen directly: a frame deferred because both
        framebuffers were spoken for, and the next retrace freed exactly one."""
        ev = {e["frame_index"]: e for e in disp()["events"]
              if e["decision"] == D["DEFERRED"]}
        n = 0
        for r in overlap():
            if r["life_flags"] & F_EVER_DEFERRED:
                self.assertEqual(r["retrace_decision"], ev[r["frame_index"]]["retrace"] + 1,
                                 "frame %d did not resolve on the next retrace"
                                 % r["frame_index"])
                n += 1
        self.assertEqual(n, 48)

    def test_defer_events_are_aggregated_one_per_frame(self):
        ev = [e for e in disp()["events"] if e["decision"] == D["DEFERRED"]]
        self.assertEqual(len(ev), 51)
        self.assertEqual(len(ev), len({e["frame_index"] for e in ev}))

    def test_every_defer_was_because_both_framebuffers_were_busy(self):
        ev = [e for e in disp()["events"] if e["decision"] == D["DEFERRED"]]
        self.assertTrue(all(e["reason"] == R["XFB_BUSY"] for e in ev))
        self.assertTrue(all(e["xfb_target"] == -1 for e in ev))


class ThePreRegisteredLatencyGates(unittest.TestCase):
    """ready = t_convert_done (the frame becomes READY), hand-off = t_decision,
    the population is EVERY scientific hand-off, and the percentile convention
    is tools/vpace.py's. All four were fixed in §V5.49.15, before the run."""

    def lat(self):
        return sorted(r["t_decision"] - r["t_convert_done"] for r in handed())

    def test_p99_is_within_one_millisecond(self):
        v = pct(self.lat(), 0.99) * 1000.0 / TB
        self.assertLessEqual(v, 1.0, "p99 %.4f ms" % v)

    def test_the_maximum_is_within_two_and_a_half_milliseconds(self):
        v = self.lat()[-1] * 1000.0 / TB
        self.assertLessEqual(v, 2.5, "max %.4f ms" % v)

    def test_the_gate_population_is_all_2047_handoffs_not_only_the_deferred(self):
        self.assertEqual(len(self.lat()), 2047)

    def test_the_undeferred_path_costs_almost_nothing(self):
        u = sorted(r["t_decision"] - r["t_convert_done"] for r in overlap()
                   if not (r["life_flags"] & F_EVER_DEFERRED))
        self.assertEqual(len(u), 1999)
        self.assertLess(u[-1] * 1000.0 / TB, 0.01)


class DisplayCadenceIsNotSourceDisposition(unittest.TestCase):
    def test_the_vi_period_re_derives_to_the_same_value_as_run_5(self):
        lo, hi, best = vpace.vi_period_feasible(
            [(float(r["t_decision"]), r["retrace_decision"]) for r in handed()])
        self.assertEqual(best, VI_PERIOD)
        self.assertEqual((lo, hi), (VI_PERIOD, VI_PERIOD))

    def test_there_were_exactly_seven_repeated_intervals(self):
        rt = [r["retrace_decision"] for r in handed()]
        d = [rt[i + 1] - rt[i] for i in range(len(rt) - 1)]
        self.assertEqual(len(d), 2046)
        self.assertEqual(sorted(set(d)), [1, 2])
        self.assertEqual(d.count(2), 7)
        self.assertEqual(sum(x - 1 for x in d), 7)

    def test_a_repeat_is_not_a_drop(self):
        self.assertEqual(disp()["source_dropped_interior"], 0)

    def test_seven_is_what_this_run_s_own_rates_require(self):
        h = handed()
        span = (h[-1]["t_decision"] - h[0]["t_decision"]) / float(TB)
        need = (TB / VI_PERIOD) * span - (len(h) - 1)
        self.assertLessEqual(int(need), 7)
        self.assertGreaterEqual(int(need) + 1, 7)


class TheCausalComparisonWithRun5(unittest.TestCase):
    """The experiment. Same stimulus, same VI, same span; one policy change."""

    R5 = os.path.join(ROOT, "captures", "fixtures",
                      "hw-gamecube-gbp-2026-09-19-stream-0007-run5-disp.bin")

    def r5_handed(self):
        # Issue #82: this file is VERSIONED under captures/fixtures/, so its absence is a
        # defect of the checkout and fails; it was a skip, which would have hidden it.
        self.assertTrue(os.path.exists(self.R5), "the versioned run-5 fixture is missing: " + self.R5)
        i = vdisp.load(self.R5)
        m = {r["frame_index"]: r for r in i["life"] if r["frame_index"] != KEY}
        o = [m[k] for k in range(SCI_LO, OVERLAP_HI + 1)]
        return o, sorted([r for r in o if r["disposition"] == D["SELECTED_NEW"]],
                         key=lambda r: r["t_decision"])

    def extras(self, h):
        rt = [r["retrace_decision"] for r in h]
        return sum((rt[i + 1] - rt[i]) - 1 for i in range(len(rt) - 1))

    def test_run_5_lost_seventeen_and_run_6_lost_none(self):
        o5, h5 = self.r5_handed()
        self.assertEqual(sum(1 for r in o5 if r["disposition"] == D["HOLD_PREVIOUS"]), 17)
        self.assertEqual(len(h5), 2030)
        self.assertEqual(len(handed()), 2047)

    def test_the_vi_consumed_the_same_2053_intervals_in_both_runs(self):
        _, h5 = self.r5_handed()
        span5 = sum(h5[i + 1]["retrace_decision"] - h5[i]["retrace_decision"]
                    for i in range(len(h5) - 1))
        h6 = handed()
        span6 = sum(h6[i + 1]["retrace_decision"] - h6[i]["retrace_decision"]
                    for i in range(len(h6) - 1))
        self.assertEqual(span5, 2053)
        self.assertEqual(span6, 2053)

    def test_the_repeats_fell_by_exactly_the_frames_run_5_had_thrown_away(self):
        """24 − 7 = 17. The display had to repeat once for every source frame
        that was discarded; Policy A stopped discarding them, and the repeats
        fell to what rate conversion alone requires."""
        _, h5 = self.r5_handed()
        e5, e6 = self.extras(h5), self.extras(handed())
        self.assertEqual(e5, 24)
        self.assertEqual(e6, 7)
        self.assertEqual(e5 - e6, 17)


if __name__ == "__main__":
    unittest.main()
