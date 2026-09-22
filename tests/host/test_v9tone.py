"""
tests/host/test_v9tone.py — GitHub Issue #64: §V9's constructions on SYNTHETIC
vectors only, written before the ROM exists.

NO ROM. NO RUN. At the time this file was written `stimulus/agb-tone` did not
exist, no image had been rebuilt and RUN 31 was a reserved name with no files.
Every vector here is built in this file by someone who cannot know what the run
will say — which is the whole reason §V9's verdicts can be trusted afterwards.

THE CASE THAT MATTERS MOST is the ~2 one. §V9.3.2 chose a factor of FOUR
precisely so that a half-period miscount — which produces exactly 2 — is
DISTINGUISHABLE instead of looking like a clean answer at the wrong frequency.
A test that only showed the happy path would not be testing the decision that
was actually made.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v9tone as v9  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def _bounded(t, start):
    """From `start`'s heading to the NEXT top-level V heading, never to EOF.
    §V8's slices ran to the end of the document and had silently been reading
    §V9 for a whole checkpoint; §V10 is what made it visible. The fix is to
    BOUND the slice, not to move a pin -- the lesson of Issue #50."""
    i = t.index(start)
    j = t.find("\n## V", i + 1)
    return t[i:j] if j >= 0 else t[i:]


def v9_part():
    return _bounded(read(HW), "\n## V9 — GBP-AUDIO-002")


def square(n_bytes, period, mark=0.5, hi=255, lo=0, phase=0):
    """A two-level square in per-BYTE levels — §V9 reads the period inside one
    block, which is what RUN 30 showed the bytes actually do."""
    return [hi if ((i + phase) % period) / float(period) < mark else lo for i in range(n_bytes)]


def window(period, note, press, n=v9.BLOCK_BYTES):
    return {"press": press, "note": note, "levels": square(n, period)}


class TheChannelsArithmeticIsGbateksAndIsRecomputed(unittest.TestCase):

    def test_the_formula_and_the_floor(self):
        self.assertAlmostEqual(v9.freq_hz(0), 64.0, places=9)
        self.assertAlmostEqual(v9.freq_hz(1024), 128.0, places=9)
        self.assertAlmostEqual(v9.freq_hz(1792), 512.0, places=9)
        self.assertAlmostEqual(v9.F_MIN_HZ, 64.0, places=9)
        # n = 0 is the lowest note the channel has; there is nothing below it
        self.assertEqual(min(v9.freq_hz(n) for n in (0, 1, 2, 1024, 2047)), v9.freq_hz(0))

    def test_an_n_the_channel_does_not_have_is_refused(self):
        for bad in (-1, 2048, 5000):
            with self.assertRaises(ValueError):
                v9.freq_hz(bad)

    def test_the_two_notes_are_the_records(self):
        a, b = v9.notes()
        self.assertEqual((a["n"], b["n"]), (1024, 1792))
        self.assertEqual((a["divisor"], b["divisor"]), (1024, 256))
        self.assertEqual((a["hz"], b["hz"]), (128.0, 512.0))
        self.assertEqual((a["predicted_period_bytes"], b["predicted_period_bytes"]), (128.0, 32.0))
        self.assertEqual((a["cycles_per_block"], b["cycles_per_block"]), (32.0, 128.0))

    def test_the_choice_satisfies_every_constraint_it_claims(self):
        c = v9.choice_is_sound()
        self.assertTrue(c["both_exact_hz"])
        self.assertTrue(c["ratio_exact"])
        self.assertTrue(c["both_resolvable"])
        self.assertTrue(c["both_clear_of_rest"])
        self.assertEqual(c["short_period_over_transition_scale"], 4.0)

    def test_the_rate_range_the_record_states(self):
        r = v9.rate_range_that_still_works()
        self.assertAlmostEqual(r["bytes_per_second_low"], 12288.0, places=0)
        self.assertAlmostEqual(r["bytes_per_second_high"], 174720.0, places=0)
        self.assertGreater(r["factor"], 14.0)
        s = plain(v9_part())
        self.assertIn("ANY RATE BETWEEN 12 288 AND 175 000 BYTES/S", s)
        self.assertIn("a factor of 14", s)

    def test_the_sizing_assumption_is_used_for_nothing_but_sizing(self):
        """The verdict must not read it: question_R takes only levels."""
        src = read(os.path.join(ROOT, "tools", "v9tone.py"))
        body = src[src.index("def question_R("):src.index("def question_C(")]
        self.assertNotIn("SIZING_BYTES_PER_SECOND", body)
        self.assertNotIn("predicted_period_bytes", body)


class ThePeriodReaderRefusesWhatIsNotASquare(unittest.TestCase):

    def test_a_clean_square_gives_its_period(self):
        r = v9.window_period(square(4096, 128))
        self.assertEqual(r["period"], 128)
        self.assertEqual(r["uniformity"], 1.0)

    def test_two_edges_are_not_enough(self):
        r = v9.window_period(square(300, 128))
        self.assertEqual(r["period"], v9.PERIOD_ABSENT)
        self.assertIn("three rising edges", r["why"])

    def test_a_constant_window_has_no_period(self):
        r = v9.window_period([7] * 4096)
        self.assertEqual(r["period"], v9.PERIOD_ABSENT)

    def test_a_jittery_alternation_is_refused_rather_than_averaged(self):
        levels = []
        for k, p in enumerate((100, 140, 90, 150, 110, 130, 95, 145)):
            levels += square(p, p)
        r = v9.window_period(levels)
        self.assertEqual(r["period"], v9.PERIOD_ABSENT)
        self.assertIn("of the intervals equal the median", r["why"])


class QuestionR(unittest.TestCase):

    def test_the_ratio_holds_on_the_predicted_pair(self):
        w = [window(128, "F1", 1), window(32, "F2", 2), window(128, "F1", 3), window(32, "F2", 4)]
        r = v9.question_R(w)
        self.assertEqual(r["verdict"], "RATIO HOLDS")
        self.assertAlmostEqual(r["ratio"], 4.0)
        # and the rate follows from EITHER window, both reported
        self.assertAlmostEqual(r["bytes_per_second"]["from_F1"], 16384.0)
        self.assertAlmostEqual(r["bytes_per_second"]["from_F2"], 16384.0)

    def test_the_ratio_holds_at_any_rate_because_the_rate_cancels(self):
        """The property that makes the experiment possible: scale both periods
        by the same unknown k and the verdict is unchanged."""
        for k in (0.75, 2, 3, 10):
            w = [window(int(128 * k), "F1", 1), window(int(32 * k), "F2", 2)]
            r = v9.question_R(w)
            self.assertEqual(r["verdict"], "RATIO HOLDS", k)
            self.assertAlmostEqual(r["ratio"], 4.0, places=1)
            # the recovered rate scales with k, which is the point of recovering it
            self.assertAlmostEqual(r["bytes_per_second"]["from_F1"] / 16384.0, k, places=1)

    def test_a_half_period_miscount_is_CAUGHT_and_named(self):
        """§V9.3.2's whole argument: a factor-2 result must not look clean."""
        w = [window(128, "F1", 1), window(64, "F2", 2)]
        r = v9.question_R(w)
        self.assertEqual(r["verdict"], "RATIO DOES NOT HOLD")
        self.assertAlmostEqual(r["ratio"], 2.0)
        self.assertIn("half-period miscount", r["note"])

    def test_a_period_that_does_not_follow_the_note_is_a_real_result(self):
        w = [window(128, "F1", 1), window(128, "F2", 2)]
        r = v9.question_R(w)
        self.assertEqual(r["verdict"], "RATIO DOES NOT HOLD")
        self.assertAlmostEqual(r["ratio"], 1.0)
        self.assertIn("A REAL RESULT, not a failed run", r["why"])

    def test_windows_with_no_alternation_are_PERIOD_ABSENT(self):
        w = [{"press": 1, "note": "F1", "levels": [3] * 4096},
             {"press": 2, "note": "F2", "levels": [3] * 4096}]
        r = v9.question_R(w)
        self.assertEqual(r["verdict"], "PERIOD ABSENT")

    def test_one_frequency_only_is_inconclusive(self):
        w = [window(128, "F1", 1), window(128, "F1", 3)]
        r = v9.question_R(w)
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertIn("DIFFERENT frequencies", r["why"])

    def test_the_run_survives_U_GBP_038_losing_press_1(self):
        """The reason the frequency ALTERNATES: presses 2-4 alone still carry
        both notes."""
        w = [None, window(32, "F2", 2), window(128, "F1", 3), window(32, "F2", 4)]
        r = v9.question_R(w)
        self.assertEqual(r["verdict"], "RATIO HOLDS")
        self.assertAlmostEqual(r["ratio"], 4.0)


class QuestionCIsReadFirstAndDecidesNothingElse(unittest.TestCase):

    def test_the_same_shape_as_run30(self):
        c = v9.question_C(square(4096, 256))
        self.assertEqual(c["verdict"], "SAME SHAPE")
        self.assertIn("property of the PATH", c["why"])

    def test_a_different_period_at_rest(self):
        c = v9.question_C(square(4096, 100))
        self.assertEqual(c["verdict"], "DIFFERENT SHAPE")
        self.assertEqual(c["period"], 100)

    def test_silence_at_rest_is_its_own_verdict(self):
        c = v9.question_C([0] * 4096)
        self.assertEqual(c["verdict"], "SILENCE")
        self.assertIn("odd one out", c["why"])

    def test_no_control_is_inconclusive(self):
        self.assertEqual(v9.question_C([])["verdict"], "INCONCLUSIVE")


class ThePreRegistrationSaysItsPart(unittest.TestCase):

    def test_the_parts_the_issue_requires_are_present(self):
        s = plain(v9_part())
        for wanted in ("QUESTION R", "QUESTION C", "f = 131072 / (2048 − n)",
                       "n 2048 − n", "128.0 Hz", "512.0 Hz",
                       "128 bytes", "32 bytes", "the ratio 4.000000",
                       "IT MUST SHOW THE PRESS COUNT ON SCREEN",
                       "captures/local/GBP-AUDIO-002_stream-0016-run31",
                       "RUN 31 is the next free number", "DO NOT RUN",
                       "the pad's A", "stream-0016 is reused UNCHANGED"):
            self.assertIn(wanted, s, wanted)

    def test_the_factor_of_four_is_argued_not_assumed(self):
        s = plain(v9_part())
        self.assertIn("a half-period miscount produces EXACTLY a factor of 2", s)
        self.assertIn("a factor of 4 cannot be produced by that error", s)
        self.assertIn("the smallest factor that cannot", s)

    def test_the_sizing_assumption_is_labelled_and_fenced(self):
        s = plain(v9_part())
        self.assertIn("THE ASSUMPTION", s)
        self.assertIn("It is U-GBP-037's own INFERENCE and it is NOT established", s)
        self.assertIn("WHAT IT IS NOT USED FOR the verdict", s)
        self.assertIn("a ratio of two periods is independent of the sample rate", s)

    def test_the_operators_cost_is_stated_plainly(self):
        s = plain(v9_part())
        self.assertIn("flashing agb-tone to the NOR REPLACES the Enhanced Control Checker", s)
        self.assertIn("re-flashing the checker is the way back", s)
        self.assertIn("he should not have to rediscover it", s)

    def test_the_press_counter_requirement_says_why(self):
        s = plain(v9_part())
        self.assertIn("he pressed four times into a void", s)
        self.assertIn("Every run so far has asked him to act blind", s)
        self.assertIn("he reports the count he SAW at the time, and the machine reports the count it RECORDED", s)
        self.assertIn("Two independent counts of the same thing", s)
        self.assertIn("what he saw is an OPERATOR OBSERVATION and stays one", s)
        # and the counter is asked for in the action list, not only required of the ROM
        self.assertIn("the counter after it", s)

    def test_the_checklist_notation_rule_is_kept(self):
        rows = [l for l in v9_part().split("\n") if "the pad's" in l]
        self.assertTrue(rows)
        for row in rows:
            self.assertRegex(row, r"[A-Z]+\s+×\s+\d")
            self.assertIsNone(re.search(r"\b[A-Z]{1,6}\s?x\s?\d", row), row)

    def test_it_authorises_nothing(self):
        s = plain(v9_part())
        self.assertIn("NOT RUN, NOT AUTHORISED HERE", s)
        self.assertIn("It authorises no ROM, no build, no hardware", s)
        self.assertIn("U-GBP-037 and U-GBP-012 stay open", s)

    def test_no_paragraph_claims_a_run_or_a_rom(self):
        claims = re.compile(r"\b(RUN 31|the ROM|the run)\b[^.]{0,40}?\b(was|were)\s+"
                            r"(built|executed|run|captured|flashed|measured)\b"
                            r"|\bthe run showed\b|\bwe (observed|measured)\b", re.I)
        for para in re.split(r"\n\s*\n", v9_part()):
            self.assertIsNone(claims.search(plain(para)), "§V9 claims something it cannot have:\n%s" % para[:200])
        # the guard bites
        for offender in ("RUN 31 was executed on 2026-09-30.",
                         "The ROM was built and the run showed the predicted ratio."):
            self.assertIsNotNone(claims.search(plain(offender)), offender)


if __name__ == "__main__":
    unittest.main()
