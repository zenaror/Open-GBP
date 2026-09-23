"""tests/host/test_v19drain.py — §V19's three gates on SYNTHETIC vectors only (Issue #84).

`tools/v19drain.py` is frozen before GBP-AUDIO-005 runs, so everything here is
constructed: no capture is read, and the module has never seen data. Two things
are checked.

  THE VERDICTS, on vectors built to hit each arm — including the arms that only
  a wrong run would reach (a short PHASE B, a counter disagreeing with the
  timebase, a silent PHASE A, a sweep that never recovers).

  THE AGREEMENT WITH THE PART, because a gate that drifts from the text it was
  frozen as is no longer a pre-registration: every constant the module holds is
  quoted in §V19 or its amendments, and the two are compared here.

Two properties get their own tests because they are the ones a later reading
could talk itself out of:

  * AMENDMENT 2 B5's BLIND SPOT — 68 AUDIO blocks spread uniformly over 28 s is
    2.44 per window and PASSES 0.999, which is exactly the steady-state loss D1
    exists to detect. The Orchestrator stated it rather than tightening the
    threshold; this file proves the gate really does behave that way, so the
    limitation is demonstrated and not merely claimed.
  * the A6 / B5 AMBIGUITY — "misses by one block IS A FAIL" against a 4.096-block
    margin. §V19.9 records the adopted reading; this file pins it, so a future
    reader cannot quietly adopt the other one.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v19drain as v  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def part():
    t = read(HW)
    i = t.index("\n## V19 — GBP-AUDIO-005")
    j = t.find("\n## V20 ", i)
    return t[i:] if j < 0 else t[i:j]


def full(n=None):
    """A PHASE B that loses nothing: 60 whole seconds at the nominal rate."""
    return [v.D1_EXPECTED] * (60 if n is None else n)


class TheConstantsAreThePartsConstants(unittest.TestCase):

    def test_the_numbers_the_module_holds_are_quoted_in_the_part(self):
        p = part()
        for token in ("40 500 000", "4096", "0.999", "60 s exactly", "3.000 s",
                      "0x20", "0x100", "0x400", "4.096"):
            self.assertIn(token, p, token)
        self.assertEqual(v.TB_HZ, 40500000)
        self.assertEqual((v.AUDIO_BLOCK, v.DMA_GRANULE), (4096, 32))
        self.assertEqual(v.D1_THRESHOLD, 0.999)
        self.assertEqual(v.D1_START_S, 3.0)
        self.assertEqual(v.D1_WINDOW_TICKS, v.TB_HZ)
        self.assertEqual(v.D1_EXPECTED, 4096)
        self.assertEqual(v.D1_MIN_PHASE_S, 60.0)
        self.assertEqual(v.N_SWEEP, (0x20, 0x100, 0x400))

    def test_the_part_carries_both_amendments_and_says_which_prevails(self):
        p = part()
        for token in ("AMENDMENT 1", "AMENDMENT 2", "prevail", "NOT RUN",
                      "4093.6 and 4094.2 blocks/s", "NOT per second"):
            self.assertIn(token, p, token)
        # the superseded figures are still there, unedited, as the convention requires
        self.assertIn("~4028 blocks/s", p, "the original's wrong rate must stay, marked superseded")
        self.assertIn("10 s each", p, "the original's PHASE A duration must stay")
        self.assertIn("floor(elapsed_ms * 4096 / 1000)", p, "the original's expected() must stay")

    def test_the_terminology_rule_is_stated(self):
        p = part()
        self.assertIn("DMA granule", p)
        self.assertIn("AUDIO block", p)
        # and the module obeys it: no bare "block" in its own prose
        doc = v.__doc__
        self.assertIn("DMA GRANULE", doc)
        self.assertIn("AUDIO BLOCK", doc)


class D1(unittest.TestCase):

    def test_a_clean_phase_passes(self):
        r = v.question_D1(full(), 60.0)
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(len(r["windows"]), 57)          # 60 s minus the first 3
        self.assertEqual(r["windows"][0]["t_start_s"], 3.0)

    def test_one_window_five_blocks_short_fails(self):
        """0.999 x 4096 = 4092.1, so five short is the first failing window."""
        c = full()
        c[20] = v.D1_EXPECTED - 5
        r = v.question_D1(c, 60.0)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("worst window 17", r["why"])       # index 20 minus the 3 skipped

    def test_four_blocks_short_still_passes_and_that_is_the_stated_margin(self):
        c = full()
        c[20] = v.D1_EXPECTED - 4
        self.assertEqual(v.question_D1(c, 60.0)["verdict"], "PASS")

    def test_the_first_three_seconds_are_excluded_however_bad_they_are(self):
        """§V18's 13 stalls all fall there; D1 is a steady-state question by construction."""
        c = full()
        c[0] = c[1] = c[2] = 0
        self.assertEqual(v.question_D1(c, 60.0)["verdict"], "PASS")

    def test_a_short_phase_is_inconclusive_not_a_pass(self):
        r = v.question_D1(full(30), 30.0)
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertIn("under the frozen 60.0 s", r["why"])

    def test_disagreeing_counters_are_inconclusive_not_a_pass(self):
        r = v.question_D1(full(), 60.0, counter_total=245760, timebase_total=245762)
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertIn("disagree by 2", r["why"])
        # one block of disagreement is within the frozen tolerance
        self.assertEqual(v.question_D1(full(), 60.0, counter_total=245760,
                                       timebase_total=245761)["verdict"], "PASS")

    def test_the_series_is_returned_whatever_the_verdict(self):
        """§V19 AMENDMENT 2 B5: reported IN FULL beside the verdict, PASS or FAIL."""
        for c, want in ((full(), "PASS"), ([v.D1_EXPECTED - 9] * 60, "FAIL")):
            r = v.question_D1(c, 60.0)
            self.assertEqual(r["verdict"], want)
            self.assertEqual(len(r["windows"]), 57)
            self.assertIsNotNone(r["worst"])

    def test_a_pass_is_never_worded_as_no_loss(self):
        r = v.question_D1(full(), 60.0)
        self.assertIn("does NOT mean no loss", r["why"])
        self.assertIn("4.096", r["why"])


class TheBlindSpotB5StatedRatherThanDiscovered(unittest.TestCase):
    """AMENDMENT 2 B5. The Orchestrator found this in his own gate after correcting
    the rate, and chose to state it rather than tighten the threshold. Demonstrated
    here so the limitation is a property of the code and not a claim about it."""

    def test_the_whole_capture_shortfall_would_pass_every_window(self):
        b = v.d1_uniform_shortfall_blind_spot(68.06, 27.932144)
        self.assertAlmostEqual(b["per_window"], 2.436, places=2)
        self.assertAlmostEqual(b["coverage"], 0.99941, places=5)
        self.assertTrue(b["passes"], "this is the blind spot; if it ever fails, B5 has been edited")
        self.assertAlmostEqual(b["margin_blocks"], 4.096, places=3)

    def test_and_the_gate_really_does_pass_it(self):
        c = [v.D1_EXPECTED - 2] * 60          # ~2.4 blocks/window, rounded to whole blocks
        r = v.question_D1(c, 60.0)
        self.assertEqual(r["verdict"], "PASS")
        # but every window is visibly under 1.0 in the series the verdict travels with
        self.assertTrue(all(w["coverage"] < 1.0 for w in r["windows"]))

    def test_what_a_real_incapacity_looks_like_by_contrast(self):
        """4028/4096 = 0.9834 — the rate §V19.0 first stated. It fails every window,
        which is why freezing it would have made the pre-registration contradict itself."""
        c = [4028] * 60
        r = v.question_D1(c, 60.0)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("57 of 57 windows below", r["why"])


class TheA6AmbiguityIsPinnedToTheAdoptedReading(unittest.TestCase):
    """§V19.9. "A window that misses by one AUDIO block IS A FAIL" against a
    4.096-block margin admits two readings 3.096 blocks apart; B5 settles it."""

    def test_one_block_short_passes_under_the_adopted_reading(self):
        c = full()
        c[10] = v.D1_EXPECTED - 1
        self.assertEqual(v.question_D1(c, 60.0)["verdict"], "PASS")

    def test_the_part_records_the_ambiguity_and_names_the_reading(self):
        p = part()
        self.assertIn("ONE AMBIGUITY RESOLVED AT TRANSCRIPTION", p)
        self.assertIn("LITERAL", p)
        self.assertIn("ADOPTED", p)
        self.assertIn("3.096", p)

    def test_the_module_says_which_reading_it_implements(self):
        self.assertIn("rescue", v.__doc__)
        self.assertIn("0.99976", v.__doc__)


class D2(unittest.TestCase):

    def test_it_measures_and_does_not_judge(self):
        r = v.question_D2(1.0, 0.994, 5243788, 26)
        self.assertEqual(r["verdict"], "MEASURED")
        self.assertNotIn("PASS", r["verdict"])
        self.assertEqual(r["blocks_lost"], 26)
        self.assertAlmostEqual(r["wall_ms"], 26 * 1000.0 / 4096, places=6)

    def test_the_ring_rule_is_twice_the_largest_stall(self):
        self.assertEqual(v.question_D2(1.0, 0.9, 4096, 40)["ring_minimum_blocks"], 80)
        self.assertIn("at least TWICE", v.question_D2(1.0, 0.9, 4096, 40)["rule"])


class QuestionA(unittest.TestCase):

    def step(self, n, programmed=32, periods=None, edges=1.0):
        return {"n": n, "programmed_period": programmed,
                "periods": [programmed] * 8 if periods is None else periods,
                "edge_recoverable": edges}

    def test_the_whole_sweep_holding_is_sync_ok(self):
        r = v.question_A([self.step(n) for n in v.N_SWEEP], True, True)
        self.assertEqual(r["verdict"], "SYNC-OK")
        self.assertEqual([s["sync"] for s in r["steps"]], ["SYNC-OK"] * 3)
        self.assertEqual(r["recovery"], "RECOVERS")

    def test_a_pass_says_it_is_sequence_and_not_fidelity(self):
        r = v.question_A([self.step(n) for n in v.N_SWEEP], True, True)
        self.assertIn("SEQUENCE", r["why"])
        self.assertIn("does NOT mean the audio is intact", r["why"])

    def test_the_sweep_stops_at_the_first_sync_lost(self):
        steps = [self.step(0x20), self.step(0x100, periods=[32, 31, 33, 32]), self.step(0x400)]
        r = v.question_A(steps, True, True)
        self.assertEqual(r["verdict"], "SYNC-LOST")
        self.assertEqual(len(r["steps"]), 2, "the third step must not be evaluated")
        self.assertIn("0x100", r["why"])

    def test_no_recovery_voids_the_rest_and_says_power_cycle(self):
        steps = [self.step(0x20, periods=[32, 30])]
        r = v.question_A(steps, True, False)
        self.assertEqual((r["verdict"], r["recovery"]), ("SYNC-LOST", "NO-RECOVERY"))
        self.assertIn("power-cycle", r["why"])

    def test_a_failed_positive_control_is_inconclusive_never_sync_lost(self):
        """AMENDMENT 2 B3: the false refutation this exists to prevent. A silent PHASE A
        is not evidence about short reads."""
        r = v.question_A([self.step(n) for n in v.N_SWEEP], False, True)
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertNotEqual(r["verdict"], "SYNC-LOST")
        self.assertIn("Nothing was playing", r["why"])
        self.assertIn("PHASE B and PHASE C remain valid", r["why"])
        self.assertEqual(r["steps"], [], "no step is judged when the control failed")

    def test_edge_degradation_is_reported_and_never_folded_into_the_verdict(self):
        steps = [self.step(n, edges=0.0) for n in v.N_SWEEP]     # every edge destroyed
        r = v.question_A(steps, True, True)
        self.assertEqual(r["verdict"], "SYNC-OK", "edge degradation may not change the verdict")
        self.assertEqual([s["edge_recoverable"] for s in r["steps"]], [0.0, 0.0, 0.0])

    def test_an_illegal_n_is_an_error_not_a_verdict(self):
        with self.assertRaises(ValueError):
            v.question_A([self.step(100)], True, True)


class TheShortReadSample(unittest.TestCase):

    def test_the_frozen_formula(self):
        self.assertEqual(v.sample_from_short_read(b"\xff" * 256, 256), 32768)
        self.assertEqual(v.sample_from_short_read(b"\x00" * 256, 256), 0)
        self.assertEqual(v.sample_from_short_read(b"\xff" * 32, 32), 32768)
        # a flat AUDIO block reads the same at every N, which is §V18.5's "exact on flat"
        flat = bytes([0b10101010]) * 4096
        self.assertEqual({v.sample_from_short_read(flat, n) for n in v.N_SWEEP + (4096,)}, {16384})

    def test_an_edge_block_does_not_read_the_same_at_every_n(self):
        """§V18.5: never at an edge. The formula is frozen anyway because the PERIOD is
        carried by the sequence of levels, not by one AUDIO block's value."""
        edge = bytes([0xFF]) * 2048 + bytes([0x00]) * 2048
        self.assertNotEqual(v.sample_from_short_read(edge, 256), v.sample_from_short_read(edge, 4096))

    def test_illegal_lengths_raise(self):
        for n in (0, 100, 4128, -32):
            with self.assertRaises(ValueError):
                v.sample_from_short_read(b"\x00" * 4096, n)
        self.assertEqual([v.legal_n(n) for n in (32, 256, 1024, 4096)], [True] * 4)
        self.assertEqual([v.legal_n(n) for n in (0, 31, 100, 4097, 8192)], [False] * 5)


class TheModuleAuthorisesNothing(unittest.TestCase):

    def test_it_reads_no_capture_and_writes_nothing(self):
        src = read(os.path.join(ROOT, "tools", "v19drain.py"))
        for forbidden in ("awinparse", "captures/", "logs/", "open(", "subprocess"):
            if forbidden == "open(":
                # one open(), in main(), of the report path the caller names
                self.assertEqual(src.count("open("), 1, "only main() opens the report it is given")
                continue
            self.assertNotIn(forbidden, src, forbidden)

    def test_the_part_says_not_run_and_mints_no_evidence_id(self):
        p = part()
        self.assertIn("NOT RUN, NOT AUTHORISED HERE", p)
        self.assertNotRegex(p, r"^#{2,4} +GBP-HW-\d{3}", )


if __name__ == "__main__":
    unittest.main()
