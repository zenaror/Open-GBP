"""tests/host/test_v28verdict.py -- tools/v28verdict.py against synthetic gbp-audio-v28 logs built
with the POC's own tag grammar (never a real capture). The Hardware Issue's own §4 is the authority;
this proves the tool implements it, gate by gate, on both the clean case and each named admissibility/
domain failure mode.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v28verdict  # noqa: E402


def syncpe_pair(p, why="complete"):
    return "SYNCPE p=%d edge=start t=%x why=none\nSYNCPE p=%d edge=end t=%x why=%s" % (p, p * 10 + 1, p, p * 10 + 9, why)


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


def b3_hold(ahead, underrun_seen=0, partial=0):
    return "V28_3B n=0 ahead=%d underrun_seen=%d partial=%d t_set=0 t_done=100" % (ahead, underrun_seen, partial)


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
        b3_hold(1, underrun_seen=0, partial=0),
        "\n".join(sweep_gate_row(n) for n in range(18)),
        sweep_verdict(1),
        label(),
    ])


class Admissibility(unittest.TestCase):
    def test_clean_log_passes(self):
        out = v28verdict.admissibility(CLEAN_ADMISSIBILITY)
        self.assertTrue(out["pass"], out["problems"])
        self.assertEqual(out["problems"], [])
        self.assertEqual(out["cut_reasons"], [])

    def test_a_missing_syncpe_edge_is_caught(self):
        # phase 2's own end edge dropped
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


class Hold3B(unittest.TestCase):
    def test_ahead1_clean_fires_the_reversal(self):
        out = v28verdict.hold_3b(b3_hold(1, underrun_seen=0))
        self.assertTrue(out["ahead1_clean"])
        self.assertTrue(out["reversal_fired"])
        self.assertFalse(out["have_ahead2"])

    def test_ahead1_underrun_does_not_fire_the_reversal_and_ahead2_appears(self):
        text = "\n".join([b3_hold(1, underrun_seen=1), b3_hold(2, underrun_seen=0)])
        out = v28verdict.hold_3b(text)
        self.assertFalse(out["ahead1_clean"])
        self.assertFalse(out["reversal_fired"])
        self.assertTrue(out["have_ahead2"])
        self.assertTrue(out["ahead2_clean"])


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


class FullRender(unittest.TestCase):
    def test_a_clean_full_log_renders_without_any_fail_marker(self):
        text = v28verdict.render(v28verdict.analyse(full_clean_log()))
        self.assertIn("ADMISSIBILITY: PASS", text)
        self.assertIn("verdict=PASS", text)
        self.assertNotIn("FAIL", text)

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
