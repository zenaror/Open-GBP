"""tests/host/test_v28verdict.py -- tools/v28verdict.py against synthetic gbp-audio-v28 logs built
with the POC's own tag grammar (never a real capture). The Hardware Issue's own §4 is the authority;
this proves the tool implements it, gate by gate, on both the clean case and each named admissibility/
domain failure mode, including Issue #131's own Amendment 1 (the anchor), Amendment 4 (native
units), and Amendment 5 (Z / partial runs).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v28verdict  # noqa: E402

T256 = 4096  # gbp_v28_ladder.h's own GBP_V28_T256, native samples


def syncpe_pair(p, why="complete"):
    return "SYNCPE p=%d edge=start t=%x why=none\nSYNCPE p=%d edge=end t=%x why=%s" % (p, p * 10 + 1, p, p * 10 + 9, why)


def syncpe_start_only(p):
    return "SYNCPE p=%d edge=start t=%x why=none" % (p, p * 10 + 1)


def syncph(p, reason="complete"):
    return "SYNCPH phase=%d t_start=%x t_end=%x ended=1 reason=%s" % (p, p * 10 + 1, p * 10 + 9, reason)


CLEAN_ADMISSIBILITY = "\n".join(
    [syncpe_pair(p) for p in range(4)] + [syncph(p) for p in range(4)] +
    ["V28C2 discarded=0 starved_steps=0 lost=0 blocks_in=100 ring_discarded=0 trans_faults=0 "
     "dropped_front=0 cs=0 acted=0 syncpe_lost=0 lines_lost=0",
     "V28CORR n=100 overflow=0 min=0 max=5 mean_x100=250 cap=19617"])


def a3_confirm(target, partial=0, underruns=0):
    return ("V28_3A n=0 target=%d kind=2 partial=%d underruns=%d overflow=0 dup=0 drop=0 starved=0 "
            "t_set=0 t_done=100" % (target, partial, underruns))


def anchor_line(target=T256, source="rule"):
    return "V28ANCHOR target=%d source=%s" % (target, source)


def b3_hold(ahead, underrun_seen=0, partial=0, anchor=T256, source="rule"):
    return ("V28_3B n=0 ahead=%d anchor=%d source=%s underrun_seen=%d partial=%d t_set=0 t_done=100"
            % (ahead, anchor, source, underrun_seen, partial))


def sweep_gate_row(n, outcome=1, fail=0):
    return ("V28_SWEEP n=%d klass=0 mech=0 from_t=4096 from_a=4 to_t=4096 to_a=3 outcome=%d fail=%d "
            "residue=0 unmasked=0" % (n, outcome, fail))


def sweep_info_row(n):
    return ("V28_SWEEP n=%d klass=1 mech=0 from_t=3072 from_a=4 to_t=3072 to_a=3 outcome=1 fail=0 "
            "residue=0 unmasked=0" % n)


def sweep_verdict(v):
    return "V28_SWEEP_VERDICT v=%d" % v


def label(renders=5, ticks_last=3, ticks_max=7):
    return "V28LABEL renders=%d ticks_last=%d ticks_max=%d" % (renders, ticks_last, ticks_max)


def full_clean_log():
    return "\n".join([
        CLEAN_ADMISSIBILITY,
        a3_confirm(3072, partial=0, underruns=0),
        anchor_line(T256, "rule"),
        b3_hold(1, underrun_seen=0, partial=0, anchor=T256, source="rule"),
        "\n".join(sweep_gate_row(n) for n in range(18)),
        sweep_verdict(1),
        label(),
    ])


class FmtTarget(unittest.TestCase):
    def test_native_old_and_ms_all_appear(self):
        s = v28verdict.fmt_target(4096)
        self.assertIn("4096 native", s)
        self.assertIn("256.0 old", s)          # 4096 / 16
        self.assertIn("62.50 ms", s)           # 4096 / 65536 * 1000

    def test_never_bare_old_unit_arithmetic_leaks_as_the_native_value(self):
        # a reader must never be able to mistake the native figure for an old-path one
        s = v28verdict.fmt_target(2048)        # P3_MIN
        self.assertIn("2048 native", s)
        self.assertIn("128.0 old", s)
        self.assertIn("31.25 ms", s)


class Admissibility(unittest.TestCase):
    def test_clean_log_passes(self):
        out = v28verdict.admissibility(CLEAN_ADMISSIBILITY)
        self.assertTrue(out["pass"], out["problems"])
        self.assertEqual(out["problems"], [])
        self.assertEqual(out["cut_reasons"], [])
        self.assertEqual(out["not_reached"], [])
        self.assertEqual(out["last_reached"], 3)
        self.assertFalse(out["used_z"])

    def test_a_missing_syncpe_edge_on_a_reached_phase_is_caught(self):
        # phase 2's own end edge dropped, but phase 3 still ran -- phase 2 was clearly reached
        lines = CLEAN_ADMISSIBILITY.splitlines()
        lines = [l for l in lines if not (l.startswith("SYNCPE p=2 edge=end"))]
        out = v28verdict.admissibility("\n".join(lines))
        self.assertFalse(out["pass"])
        self.assertTrue(any("phase 2" in p and "no SYNCPE end" in p for p in out["problems"]), out["problems"])

    def test_a_v28corr_overflow_is_caught(self):
        text = CLEAN_ADMISSIBILITY.replace("V28CORR n=100 overflow=0", "V28CORR n=100 overflow=3")
        out = v28verdict.admissibility(text)
        self.assertFalse(out["pass"])
        self.assertTrue(any("V28CORR overflow=3" in p for p in out["problems"]), out["problems"])

    def test_a_v28c2_nonzero_field_is_caught(self):
        text = CLEAN_ADMISSIBILITY.replace("lost=0", "lost=7", 1)
        out = v28verdict.admissibility(text)
        self.assertFalse(out["pass"])
        self.assertTrue(any("lost=7" in p for p in out["problems"]), out["problems"])

    def test_ring_discarded_alone_never_fails_admissibility(self):
        """RUN 51 (Issue #131/#133/#135): ring_discarded (adec2.discarded) is documented as
        "samples the consumer dropped from the ring's head ON PURPOSE" (gbp_adec2.h) -- every
        downward TARGET transition drives it, so it is structurally guaranteed nonzero for any
        validation_run informative enough to matter (3a's whole descent, sweep's own ladder walk
        both ways). Issue #131 sec4's own text: "V28C2's own overflow/lost/ring_discarded fields
        at 0 WHERE THE DESIGN SAYS THEY SHOULD BE" -- conditional, and the design does not say so
        here. RED-verified against the historical blanket check (ring_discarded folded into the
        same loop as the genuine loss counters) before this fix."""
        text = CLEAN_ADMISSIBILITY.replace("ring_discarded=0", "ring_discarded=15695", 1)
        out = v28verdict.admissibility(text)
        self.assertTrue(out["pass"], out["problems"])
        self.assertEqual(out["problems"], [])

    def test_the_genuine_loss_counters_still_fail_admissibility_each(self):
        """lost/syncpe_lost/lines_lost are real capture-integrity counters with no domain
        mechanism that spends them (unlike ring_discarded) -- the design DOES guarantee 0."""
        for field in ("lost", "syncpe_lost", "lines_lost"):
            text = CLEAN_ADMISSIBILITY.replace("%s=0" % field, "%s=3" % field, 1)
            out = v28verdict.admissibility(text)
            self.assertFalse(out["pass"], field)
            self.assertTrue(any("%s=3" % field in p for p in out["problems"]), (field, out["problems"]))

    def test_a_phase_cut_by_cap_is_recorded_not_a_hard_failure(self):
        text = CLEAN_ADMISSIBILITY.replace(syncph(1), syncph(1, reason="cap"))
        out = v28verdict.admissibility(text)
        self.assertTrue(out["pass"], out["problems"])  # a cap cut is a note, not an admissibility FAIL
        self.assertEqual(out["cut_reasons"], [(1, "cap")])

    def test_missing_v28c2_or_v28corr_is_caught(self):
        text = "\n".join(l for l in CLEAN_ADMISSIBILITY.splitlines() if not l.startswith("V28C2"))
        out = v28verdict.admissibility(text)
        self.assertFalse(out["pass"])
        self.assertIn("no V28C2 record", out["problems"])

    def test_amendment_5_unreached_phases_are_not_flagged_as_problems(self):
        """A Z cut mid-phase-1 (3a): phases 2 and 3 (3b, sweep) never started at all -- not a
        problem, not evaluated, distinct from a phase that started but never got its own end."""
        text = "\n".join([
            syncpe_pair(0), syncph(0, "complete"),
            syncpe_start_only(1), syncph(1, "z"),   # phase 1 reached and cut by Z -- its own end IS present via SYNCPH's backstop, but no SYNCPE end line here on purpose
            "V28C2 discarded=0 starved_steps=0 lost=0 blocks_in=100 ring_discarded=0 trans_faults=0 "
            "dropped_front=0 cs=0 acted=0 syncpe_lost=0 lines_lost=0",
            "V28CORR n=100 overflow=0 min=0 max=5 mean_x100=250 cap=19617",
        ])
        out = v28verdict.admissibility(text)
        self.assertEqual(out["not_reached"], [2, 3])
        self.assertTrue(out["used_z"])
        # phase 1 was reached (a start exists) but never got a SYNCPE end -- that IS a real problem,
        # distinct from "not reached"
        self.assertTrue(any("phase 1" in p and "no SYNCPE end" in p for p in out["problems"]), out["problems"])
        self.assertFalse(any("phase 2" in p or "phase 3" in p for p in out["problems"]), out["problems"])

    def test_last_reached_with_nothing_at_all_is_minus_one(self):
        out = v28verdict.admissibility("V28C2 discarded=0 starved_steps=0 lost=0 blocks_in=0 "
                                       "ring_discarded=0 trans_faults=0 dropped_front=0 cs=0 acted=0 "
                                       "syncpe_lost=0 lines_lost=0\nV28CORR n=0 overflow=0 min=0 max=0 "
                                       "mean_x100=0 cap=19617")
        self.assertEqual(out["last_reached"], -1)
        self.assertEqual(out["not_reached"], [0, 1, 2, 3])


class Descent3A(unittest.TestCase):
    def test_the_last_confirm_is_the_measurement(self):
        text = "\n".join([a3_confirm(4096, partial=0, underruns=1), a3_confirm(3072, partial=0, underruns=0)])
        out = v28verdict.descent_3a(text)
        self.assertTrue(out["have"])
        self.assertEqual(out["target"], 3072)  # the LAST confirm, not the first
        self.assertTrue(out["clean"])
        self.assertFalse(out["partial"])

    def test_a_partial_confirm_is_reported_as_such(self):
        out = v28verdict.descent_3a(a3_confirm(3072, partial=1, underruns=0))
        self.assertTrue(out["partial"])

    def test_no_confirm_record_is_reported(self):
        out = v28verdict.descent_3a("V28_3A n=0 target=4096 kind=0 partial=0 underruns=0 overflow=0 "
                                     "dup=0 drop=0 starved=0 t_set=0 t_done=0")
        self.assertFalse(out["have"])


class AnchorInfo(unittest.TestCase):
    def test_reads_the_dedicated_record(self):
        out = v28verdict.anchor_info(anchor_line(4096, "rule"))
        self.assertTrue(out["have"])
        self.assertEqual(out["target"], 4096)
        self.assertEqual(out["source"], "rule")

    def test_none_source_is_read_as_such(self):
        out = v28verdict.anchor_info(anchor_line(0, "none"))
        self.assertEqual(out["source"], "none")

    def test_no_record_at_all(self):
        out = v28verdict.anchor_info("")
        self.assertFalse(out["have"])


class Hold3B(unittest.TestCase):
    def test_ahead1_clean_at_t256_fires_the_reversal(self):
        text = "\n".join([anchor_line(T256, "rule"), b3_hold(1, underrun_seen=0, anchor=T256, source="rule")])
        out = v28verdict.hold_3b(text)
        self.assertTrue(out["ahead1_clean"])
        self.assertTrue(out["reversal_evaluable"])
        self.assertTrue(out["reversal_fired"])
        self.assertFalse(out["have_ahead2"])

    def test_ahead1_underrun_does_not_fire_the_reversal_and_ahead2_appears(self):
        text = "\n".join([anchor_line(T256, "rule"),
                          b3_hold(1, underrun_seen=1, anchor=T256, source="rule"),
                          b3_hold(2, underrun_seen=0, anchor=T256, source="rule")])
        out = v28verdict.hold_3b(text)
        self.assertFalse(out["ahead1_clean"])
        self.assertFalse(out["reversal_fired"])
        self.assertTrue(out["have_ahead2"])
        self.assertTrue(out["ahead2_clean"])

    def test_amendment_1_a_clean_hold_at_a_non_t256_anchor_never_fires_the_reversal(self):
        """The exact scenario Amendment 1 exists to prevent silently misreading: a clean AHEAD-1
        hold at, say, T320 (a non-anchor rung 3a's own floor happened to land on) must NOT be read
        as the reversal firing -- the condition is specifically about the T256 anchor."""
        text = "\n".join([anchor_line(5120, "rule"), b3_hold(1, underrun_seen=0, anchor=5120, source="rule")])
        out = v28verdict.hold_3b(text)
        self.assertTrue(out["ahead1_clean"])
        self.assertFalse(out["reversal_evaluable"])
        self.assertFalse(out["reversal_fired"])

    def test_anchor_default_still_evaluates_the_reversal(self):
        """#128's own freeze (§5): "the anchor used is T256" -- no source qualifier. A clean hold
        at T256 is the observation named whether T256 came from the rule or from the frozen
        default (no confirmed floor at all). An earlier draft of this tool required source=="rule"
        too, which the freeze never asked for -- caught at the Orchestrator's own review."""
        text = "\n".join([anchor_line(T256, "default"), b3_hold(1, underrun_seen=0, anchor=T256, source="default")])
        out = v28verdict.hold_3b(text)
        self.assertEqual(out["anchor"]["source"], "default")
        self.assertTrue(out["reversal_evaluable"])
        self.assertTrue(out["reversal_fired"])  # clean, at T256 -- FIRED, regardless of source

    def test_anchor_none_has_no_hold_at_all(self):
        out = v28verdict.hold_3b(anchor_line(0, "none"))
        self.assertEqual(out["anchor"]["source"], "none")
        self.assertFalse(out["have_ahead1"])


class Sweep(unittest.TestCase):
    def test_18_clean_gates_pass(self):
        text = "\n".join(sweep_gate_row(n) for n in range(18)) + "\n" + sweep_verdict(1)
        out = v28verdict.sweep(text)
        self.assertEqual(out["n_gate"], 18)
        self.assertEqual(out["failing_gates"], [])
        self.assertEqual(out["verdict_name"], "PASS")

    def test_fewer_than_18_is_pending(self):
        text = "\n".join(sweep_gate_row(n) for n in range(10)) + "\n" + sweep_verdict(0)
        out = v28verdict.sweep(text)
        self.assertEqual(out["verdict_name"], "PENDING")

    def test_one_failing_gate_fails_the_verdict(self):
        rows = [sweep_gate_row(n) for n in range(18)]
        rows[5] = sweep_gate_row(5, outcome=2, fail=2)  # FAIL_UNDERRUN
        text = "\n".join(rows) + "\n" + sweep_verdict(2)
        out = v28verdict.sweep(text)
        self.assertEqual(len(out["failing_gates"]), 1)
        self.assertEqual(out["failing_gates"][0]["n"], "5")
        self.assertEqual(out["verdict_name"], "FAIL")

    def test_info_rows_never_counted_as_gates(self):
        rows = [sweep_gate_row(n) for n in range(18)] + [sweep_info_row(n) for n in range(18, 27)]
        text = "\n".join(rows) + "\n" + sweep_verdict(1)
        out = v28verdict.sweep(text)
        self.assertEqual(out["n_gate"], 18)
        self.assertEqual(out["n_info"], 9)
        self.assertEqual(out["n_records"], 27)


class LabelCost(unittest.TestCase):
    def test_the_last_v28label_record_is_read(self):
        text = "\n".join([label(renders=1, ticks_max=3), label(renders=5, ticks_max=9)])
        out = v28verdict.label_cost(text)
        self.assertTrue(out["have"])
        self.assertEqual(out["renders"], 5)
        self.assertEqual(out["ticks_max"], 9)

    def test_no_record_is_reported(self):
        out = v28verdict.label_cost("")
        self.assertFalse(out["have"])


class Issue135Diagnostics(unittest.TestCase):
    """RUN 52's own additions: the INFO prelude that opens the sweep, the measured from-state on every
    V28_SWEEP line, and 3b's own margin minima. Logs without them (RUN 51's) must read as before."""

    MAIN = os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")

    def test_the_prelude_is_one_more_info_row_and_never_a_gate(self):
        prelude = ("V28_SWEEP n=0 klass=1 mech=2 from_t=4096 from_a=1 to_t=11264 to_a=4 outcome=2 fail=1 "
                   "residue=-895 unmasked=0")
        rows = [prelude] + [sweep_gate_row(n) for n in range(1, 19)] + [sweep_info_row(n) for n in range(19, 28)]
        out = v28verdict.sweep("\n".join(rows) + "\n" + sweep_verdict(1))
        self.assertEqual(out["n_gate"], 18)
        self.assertEqual(out["n_info"], 10)
        self.assertEqual(out["n_records"], 28)
        self.assertEqual(out["failing_gates"], [])    # a failing prelude is not a failing GATE
        self.assertEqual(out["verdict_name"], "PASS")

    def test_measured_fields_are_rendered_for_a_failing_gate_and_optional_otherwise(self):
        row = (sweep_gate_row(3, outcome=2, fail=1) + "\n"
               "V28_SWEEPM n=3 meas_t=4096 meas_a=1 meas_ring=4100 meas_ready=1 ring=3000 ready=0 dup=2 drop=0 "
               "t_land=abc")
        log = full_clean_log().replace(sweep_gate_row(3), row)
        text = v28verdict.render(v28verdict.analyse(log))
        self.assertIn("measured from-state: target 4096 ahead 1 ring 4100 ready 1; landed ring 3000 ready 0", text)
        plain = v28verdict.render(v28verdict.analyse(full_clean_log()))
        self.assertNotIn("measured from-state", plain)

    def test_the_prelude_start_state_is_rendered_although_it_is_info_and_passes_or_fails(self):
        prelude = ("V28_SWEEP n=0 klass=1 mech=2 from_t=4096 from_a=1 to_t=11264 to_a=4 outcome=2 fail=1 "
                   "residue=-204 unmasked=0\n"
                   "V28_SWEEPM n=0 meas_t=4096 meas_a=1 meas_ring=5000 meas_ready=2 ring=3100 ready=1 dup=0 "
                   "drop=0 t_land=abc")
        rows = [prelude] + [sweep_gate_row(n) for n in range(1, 19)] + [sweep_info_row(n) for n in range(19, 28)]
        log = full_clean_log().split("V28_SWEEP ")[0] + "\n".join(rows) + "\n" + sweep_verdict(1) + "\n"
        text = v28verdict.render(v28verdict.analyse(log))
        self.assertIn("INFO n=0: from", text)
        self.assertIn("measured from-state: target 4096 ahead 1 ring 5000 ready 2; landed ring 3100 ready 1", text)
        self.assertNotIn("FAIL gate", text)

    def test_3b_margin_is_read_and_rendered_when_present_and_absent_otherwise(self):
        row = b3_hold(1) + " min_ready=0 min_ring=2048 samples=1919"
        log = full_clean_log().replace(b3_hold(1), row)
        out = v28verdict.hold_3b(log)
        self.assertEqual(out["margin_ahead1"], {"min_ready": 0, "min_ring": 2048, "samples": 1919})
        self.assertIn("min READY 0, min ring 2048", v28verdict.render(v28verdict.analyse(log)))
        self.assertNotIn("margin_ahead1", v28verdict.hold_3b(full_clean_log()))

    def test_3b_settled_margin_is_read_and_rendered_when_present_and_absent_otherwise(self):
        """Issue #136: RUN 52's min_ring = 256 could not say a landing transient from a steady margin."""
        row = b3_hold(1) + " min_ready=0 min_ring=256 samples=1919"
        extra = "V28_3BM n=0 ring0=2304 min_ring_late=2110 samples_late=1500 mean_ring=2925 mean_cs=3830 chunk_starts=1800"
        log = full_clean_log().replace(b3_hold(1), row + "\n" + extra)
        out = v28verdict.hold_3b(log)
        self.assertEqual(out["margin_ahead1"]["ring0"], 2304)
        self.assertEqual(out["margin_ahead1"]["min_ring_late"], 2110)
        self.assertEqual(out["margin_ahead1"]["samples_late"], 1500)
        rendered = v28verdict.render(v28verdict.analyse(log))
        self.assertIn("ring at the first sample 2304; min ring over the 1500 samples taken 10 s or more after it 2110", rendered)
        self.assertIn("steady level: mean ring 2925 (-1171 vs target 4096), mean ring at chunk start 3830 (-266 vs target) over 1800 chunks", rendered)
        none = b3_hold(1) + " min_ready=0 min_ring=256 samples=1919\nV28_3BM n=0 ring0=2304 min_ring_late=0 samples_late=0 mean_ring=0 mean_cs=0 chunk_starts=0"
        self.assertIn("(none)", v28verdict.render(v28verdict.analyse(full_clean_log().replace(b3_hold(1), none))))
        self.assertNotIn("ring0", v28verdict.hold_3b(full_clean_log().replace(b3_hold(1), row))["margin_ahead1"])

    def test_the_cut_fields_are_rendered_when_present(self):
        row = (sweep_gate_row(3, outcome=2, fail=1) + "\n"
               "V28_SWEEPM n=3 meas_t=4096 meas_a=1 meas_ring=4100 meas_ready=1 ring=3000 ready=0 dup=2 drop=0 "
               "t_land=abc\nV28_SWEEPC n=3 cut=1500 cut_rel=-2 rot_post=4 fill_short=0 dwell_cut=0 late=0")
        text = v28verdict.render(v28verdict.analyse(full_clean_log().replace(sweep_gate_row(3), row)))
        self.assertIn("dup 2 drop 0 cut 1500 (period -2 vs unmute) rot_post 4 fill_short 0 dwell_cut 0 late 0", text)
        self.assertIn("fail_reason=1 (OUT_OF_BAND)", text)

    def _log_with_cut(self, n, cut, rel, dwell=0):
        rows = ["V28_SWEEPC n=%d cut=%d cut_rel=%d rot_post=4 fill_short=0 dwell_cut=0 late=0" % (k, 1800, -2)
                for k in range(1, 19)]
        rows[n - 1] = "V28_SWEEPC n=%d cut=%d cut_rel=%d rot_post=4 fill_short=0 dwell_cut=%d late=0" % (n, cut, rel, dwell)
        log = full_clean_log()
        return log.replace("V28_SWEEP_VERDICT", "\n".join(rows) + "\nV28_SWEEP_VERDICT", 1)

    def test_a_cut_after_unmute_in_a_gate_row_fails_the_pre_registered_gate_line(self):
        """#122 section 1(c), registered on Issue #136 before RUN 53: read from the log's own records, whatever the module said."""
        text = v28verdict.render(v28verdict.analyse(self._log_with_cut(5, 1400, 1)))
        self.assertIn("no cut after unmute (Issue #136 GATE condition) -- FAIL at GATE n=5 (1400 samples cut after the landing or at period 1)", text)

    def test_a_cut_in_the_dwell_after_the_landing_fails_it_too(self):
        """the only path the firmware can actually reach: the module's own cut is always before unmute, a stray discard is not"""
        text = v28verdict.render(v28verdict.analyse(self._log_with_cut(5, 1800, -2, dwell=96)))
        self.assertIn("-- FAIL at GATE n=5 (96 samples cut after the landing or at period 0)", text)

    def test_cuts_inside_the_mute_pass_the_gate_line_and_an_old_log_says_not_recorded(self):
        text = v28verdict.render(v28verdict.analyse(self._log_with_cut(5, 1400, -2)))
        self.assertIn("no cut after unmute (Issue #136 GATE condition) -- PASS in every GATE row", text)
        old = v28verdict.render(v28verdict.analyse(full_clean_log()))
        self.assertIn("NOT RECORDED (this log predates it)", old)

    def test_a_row_with_no_cut_at_all_is_no_cut(self):
        text = v28verdict.render(v28verdict.analyse(self._log_with_cut(5, 0, -100)))
        self.assertIn("-- PASS in every GATE row", text)

    def test_the_underrun_accounting_leaves_the_unattributed_remainder_and_says_the_3b_flag_is_unobserved(self):
        """Issue #137: 3b's underrun_seen is set by a hook main.c never calls; the log's own total less 3a's rows is what is left."""
        log = ("V28C underruns=41 overflow=0 silences=41 mute_handed=215 dup=79047 drop=0 produced=5427 handed=5595 ring_gated=1\n"
               "V28_3A n=0 target=6144 kind=0 partial=0 underruns=7 overflow=0 dup=1 drop=0 starved=1 t_set=1 t_done=2\n"
               "V28_3A n=1 target=5632 kind=0 partial=0 underruns=2 overflow=0 dup=1 drop=0 starved=1 t_set=1 t_done=2\n")
        self.assertEqual(v28verdict.underrun_accounting(log), {"have": True, "total": 41, "s3a": 9, "rest": 32})
        self.assertEqual(v28verdict.underrun_accounting("no V28C here"), {"have": False})
        text = v28verdict.render(v28verdict.analyse(full_clean_log() + "\n" + log))
        self.assertIn("'clean' means UNOBSERVED. Session underruns 41, 3a's rows carry", text)

    def test_the_worst_case_print_lines_fit_the_console_log_line(self):
        """LOG_LINE_LEN 256, less the 7-character `%06u ` prefix and the terminator: a longer line
        would be silently truncated (ringlog's own snprintf), losing the tail fields first."""
        import re
        with open(self.MAIN, encoding="utf-8") as f:
            src = f.read()
        limit = int(re.search(r"#define LOG_LINE_LEN (\d+)", src).group(1)) - 8
        for tag in ("V28_SWEEP n=", "V28_SWEEPM n=", "V28_SWEEPC n=", "V28_3B n=", "V28_3BM n="):
            i = src.index('"' + tag)
            call = src[i:src.index(");", i)]
            fmt = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', call.split("\n", 1)[0] + "\n" +
                                     call.split("\n", 1)[1].split(",\n")[0]))
            # widest values a run can plausibly reach: counters below a million, tick timestamps of
            # 12 hex digits (a 2.8e14-tick run, 5 orders past the 468 s cap), residues of 7 characters
            widths = {"%lu": "999999", "%llx": "f" * 12, "%ld": "-999999", "%u": "255", "%s": "default"}
            for spec, w in widths.items():
                fmt = fmt.replace(spec, w)
            self.assertLessEqual(len(fmt), limit, "%s line would be truncated: %d > %d" % (tag, len(fmt), limit))


class FullRender(unittest.TestCase):
    def test_a_clean_full_log_renders_without_any_fail_marker(self):
        text = v28verdict.render(v28verdict.analyse(full_clean_log()))
        self.assertIn("ADMISSIBILITY: PASS", text)
        self.assertIn("verdict=PASS", text)
        self.assertIn("FIRED", text)  # the reversal condition, at the T256 anchor, clean
        self.assertNotIn("FAIL", text)

    def test_targets_are_never_printed_as_a_bare_number(self):
        text = v28verdict.render(v28verdict.analyse(full_clean_log()))
        self.assertIn("native", text)
        self.assertIn("old", text)
        self.assertIn("ms", text)

    def test_main_reads_a_file_and_prints(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False) as f:
            f.write(full_clean_log())
            path = f.name
        try:
            rc = v28verdict.main(["v28verdict.py", path])
            self.assertEqual(rc, 0)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
