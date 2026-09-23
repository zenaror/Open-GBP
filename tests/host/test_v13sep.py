"""tests/host/test_v13sep.py — GitHub Issue #75: §V13, `U-GBP-038`'s separator.

Two jobs. `tools/v13sep.py` must behave as §V13 says on synthetic vectors, and
§V13 must stay a pre-registration — it authorises no run, no flash and no
staging, and it answers nothing.

The load-bearing test is the one that shows a LONG gap does not separate the two
readings and a SHORT one does, because that is the correction this checkpoint
exists for: §V11.16.9 named the wrong separator and it is corrected on top
rather than deleted.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v13sep as v  # noqa: E402
import v11sweep  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def part():
    t = read(HW)
    i = t.index("\n## V13 ")
    j = t.find("\n## V", i + 1)
    return (t[i:j] if j >= 0 else t[i:]).lstrip("\n")


class ALongGapDoesNotSeparateAndAShortOneDoes(unittest.TestCase):
    """The correction this whole checkpoint rests on, demonstrated on the two
    predicates rather than argued in prose."""

    def test_at_a_long_gap_the_two_readings_AGREE(self):
        offsets = [0.0, 10.0]
        ordinal = v.predict_ordinal(2)
        for t in (0.5, 1.0, 3.33):          # every T still credible
            elapsed = v.predict_elapsed(offsets, t)
            self.assertEqual(ordinal, elapsed,
                             "a long gap separates them at T=%s, which would make §V13 wrong" % t)

    def test_at_a_short_gap_the_two_readings_DISAGREE(self):
        offsets = [0.0, 0.3]
        ordinal = v.predict_ordinal(2)
        elapsed = v.predict_elapsed(offsets, 3.33)
        self.assertNotEqual(ordinal, elapsed)
        self.assertEqual(ordinal[1], True)      # ORDINAL: the next window carries
        self.assertEqual(elapsed[1], False)     # ELAPSED: 0.3 s has not reached T

    def test_the_document_carries_the_correction_and_does_not_delete_the_error(self):
        s = plain(part())
        self.assertIn("§V11.16.9 said the separator was a LONG gap. It is not", s)
        self.assertIn("reasoning as if ORDINAL meant", s)
        # and the original text is still there, with its correction appended
        hw = read(HW)
        self.assertIn("The separator is a run with a LONG gap after the first", hw)
        self.assertIn("THE SENTENCE ABOVE NAMES THE WRONG SEPARATOR", hw)
        for doc in (EV, UNK):
            self.assertIn("Issue #75", read(doc))


class TheGateIsMechanicalAndNeedsNoAssumedDelay(unittest.TestCase):

    def setUp(self):
        self.offs = list(v.OFFSET_TARGETS)

    def test_only_the_emitting_window_dead_is_NOT_SEPARATED_but_bounds_T(self):
        r = v.question_S(self.offs, [False, True, True, True])
        self.assertEqual(r["verdict"], "NOT SEPARATED")
        lo, hi = r["bound"]
        self.assertAlmostEqual(lo, 0.0625, places=4)
        self.assertAlmostEqual(hi, 0.3625, places=4)
        # and that is about nine times tighter than the interval it starts from
        self.assertGreater((v.T_UPPER - v.T_LOWER) / (hi - lo), 8.0)

    def test_a_second_dead_window_REFUTES_ORDINAL(self):
        for carried, want in (([False, False, True, True], (0.3625, 1.2625)),
                              ([False, False, False, True], (1.2625, 4.0625))):
            r = v.question_S(self.offs, carried)
            self.assertEqual(r["verdict"], "ORDINAL REFUTED")
            self.assertAlmostEqual(r["bound"][0], want[0], places=4)
            self.assertAlmostEqual(r["bound"][1], want[1], places=4)

    def test_a_non_monotone_pattern_refutes_BOTH(self):
        r = v.question_S(self.offs, [False, True, False, True])
        self.assertEqual(r["verdict"], "BOTH REFUTED")
        self.assertIsNone(r["bound"])
        self.assertIn("no single", r["why"])

    def test_the_positive_control_failing_is_INADMISSIBLE_not_evidence(self):
        r = v.question_S(self.offs, [False, False, False, False])
        self.assertEqual(r["verdict"], "INADMISSIBLE")
        self.assertIn("positive control", r["why"])

    def test_the_emitting_window_carrying_is_INADMISSIBLE(self):
        r = v.question_S(self.offs, [True, True, True, True])
        self.assertEqual(r["verdict"], "INADMISSIBLE")
        self.assertIn("neither reading predicts", r["why"])

    def test_the_verdict_does_not_depend_on_the_order_they_are_passed_in(self):
        a = v.question_S([0.0, 0.3, 1.2, 4.0], [False, False, True, True])
        b = v.question_S([4.0, 1.2, 0.3, 0.0], [True, True, False, False])
        self.assertEqual(a["verdict"], b["verdict"])
        self.assertEqual(a["bound"], b["bound"])

    def test_the_floor_is_derived_from_the_window_fill_not_chosen(self):
        self.assertAlmostEqual(v.WINDOW_SECONDS, 0.0625, places=6)
        self.assertGreater(v.GAP_FLOOR, v.WINDOW_SECONDS)   # a window must finish filling
        self.assertEqual(v.gaps_are_admissible([0.0, 0.05]), [0.05])
        self.assertEqual(v.gaps_are_admissible(list(v.OFFSET_TARGETS)), [])

    def test_the_bound_this_run_starts_from_is_the_one_the_runs_measured(self):
        self.assertAlmostEqual(v.T_LOWER, 0.0625, places=6)
        self.assertAlmostEqual(v.T_UPPER, 3.33, places=6)
        s = part()
        self.assertIn("T ∈ (0.0625, 3.33]", s)
        self.assertIn("53×", s)
        self.assertAlmostEqual((3.33 - 0.0625) / 0.0625, 52.3, delta=1.0)

    def test_carriage_is_v11sweeps_own_classifier_and_nothing_new(self):
        s = plain(part())
        self.assertIn("Carriage is tools/v11sweep.py's own classify_window(), unedited", s)
        self.assertTrue(hasattr(v11sweep, "classify_window"))
        self.assertNotIn("def classify", read(os.path.join(ROOT, "tools", "v13sep.py")))

    def test_the_construction_is_not_edited_after_its_commit(self):
        base = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "-1", "--grep",
                               "Issue #75 -- U-GBP-038's separator pre-registered"],
                              capture_output=True, text=True).stdout.strip()
        if not base:
            self.skipTest("the commit that introduced tools/v13sep.py is not in this checkout")
        then = subprocess.run(["git", "-C", ROOT, "show", "%s:tools/v13sep.py" % base],
                              capture_output=True, text=True).stdout
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v13sep.py")))


class TheFifthPressAlarmIsDecidedAndDeferredWithItsReason(unittest.TestCase):

    def test_the_property_is_written_down_in_general_terms(self):
        s = part()
        self.assertIn("AN ALARM MUST NOT BE REACHABLE BY ANY VALID STATE", s)
        f = plain(s)
        self.assertIn("a sixth colour in a sequence of colours is a continuation", f)

    def test_the_machine_record_really_does_catch_a_fifth_press_twice(self):
        """The claim that lets the fix wait, checked in the SOURCE rather than
        taken from the page."""
        poc = read(os.path.join(ROOT, "poc", "gbp-audio-window-probe", "source", "main.c"))
        awin = read(os.path.join(ROOT, "src", "gbp", "gbp_awin.c"))
        self.assertIn("awin_presses_seen++", poc)
        self.assertLess(poc.index("awin_presses_seen++"), poc.index("gbp_awin_arm_press(&awin"))
        self.assertIn("w->arm_refused_full++", awin)
        self.assertIn("refused_full=%lu presses=%lu", poc)
        unit = read(os.path.join(ROOT, "tests", "unit", "test_gbp_awin.c"))
        self.assertIn("arm_refused_full == 1u", unit)

    def test_the_photographs_are_recorded_and_the_defect_is_demonstrated(self):
        s = part()
        self.assertIn("PRESSES 4 AND 5 DIFFER IN EXACTLY ONE THING: THE BACKGROUND HUE", s)
        f = plain(s.replace("\n> ", " "))
        self.assertIn("the box channel has run out of boxes", f)
        self.assertIn("neither channel distinguishes the fifth press", f)
        # the count sequence is named, since nothing else in the record names it
        self.assertIn("black (0) → red → green → blue → yellow → MAGENTA", s)

    def test_the_sequence_on_the_page_is_the_sequence_in_the_ROM(self):
        src = read(os.path.join(ROOT, "stimulus", "agb-sweep", "source", "main.c"))
        body = src[src.index("u16 sweep_background"):]
        body = body[:body.index("\n}")]
        order = re.findall(r"return (COL_\w+);", body)
        self.assertEqual(order, ["COL_BLACK", "COL_RED", "COL_GREEN", "COL_BLUE",
                                 "COL_YELLOW", "COL_MAGENTA"])

    def test_the_fifth_press_really_is_harmless_in_the_code(self):
        """What makes "a conversation, not a run" a statement about the code."""
        rom = read(os.path.join(ROOT, "stimulus", "agb-sweep", "source", "main.c"))
        self.assertIn("(count >= SWEEP_STEPS) ? (SWEEP_STEPS - 1u)", rom)
        awin = read(os.path.join(ROOT, "src", "gbp", "gbp_awin.c"))
        arm = awin[awin.index("int gbp_awin_arm_press"):]
        arm = arm[:arm.index("\n}")]
        # the busy check returns BEFORE anything is written, so a filling window is untouched
        self.assertLess(arm.index("arm_refused_busy++"), arm.index("w->next_press++"))
        self.assertIn("return -1;", arm.split("arm_refused_busy++")[1].split("\n")[0])
        s = plain(part())
        self.assertIn("LEAVES WINDOW 4 UNDISTURBED", part())
        self.assertIn("a statement about the code rather than a hope", s)

    def test_the_absence_of_an_at_the_time_signal_is_recorded_as_a_limitation(self):
        s = plain(part())
        self.assertIn("no at-the-time signal at all", s)
        self.assertIn("recorded here as a known limitation", s)
        self.assertIn("a future ROM that breaks either must ship the alarm fix with it", s)

    def test_U_GBP_040_is_confirmed_fixed_and_unexplained_by_the_photographs(self):
        s = plain(part())
        self.assertIn("no cyan mark anywhere, on any press", s)
        self.assertIn("U-GBP-040 is FIXED AND UNEXPLAINED", s)
        u = read(UNK)
        i = u.index("## U-GBP-040")
        j = u.find("\n## ", i + 10)
        self.assertNotIn("CLOSED", u[i:j if j > 0 else len(u)])

    def test_the_fix_is_specified_and_explicitly_NOT_built(self):
        s = plain(part())
        self.assertIn("make >4 a pattern rather than a sixth colour", s.lower())
        self.assertIn("IT DOES NOT SHIP ON ITS OWN", s)
        self.assertIn("costs a conversation", s)
        # and the ROM really was not touched
        src = read(os.path.join(ROOT, "stimulus", "agb-sweep", "source", "main.c"))
        self.assertIn("default: return COL_MAGENTA;", src)


class ItAuthorisesNothing(unittest.TestCase):

    def test_the_heading_says_not_run_not_authorised(self):
        h = part().split("\n", 1)[0]
        self.assertIn("NOT RUN, NOT AUTHORISED HERE", h)
        self.assertIn("PRE-REGISTERED", h)

    def test_no_flash_and_no_staging_because_both_already_exist(self):
        s = plain(part())
        self.assertIn("ALREADY FLASHED", s)
        self.assertIn("NO NEW FLASH", s)
        self.assertIn("REUSED UNCHANGED. NO NEW STAGING", s)
        self.assertIn("9596ddee9d3f969b21264384391656df91ab23cb91042f5162b1f696a80195f2", part())

    def test_the_varied_spacing_is_explicit_in_the_action_list(self):
        s = part()
        self.assertIn("THIS RUN DELIBERATELY BREAKS THAT", s)
        self.assertIn("THE SPACING IS NOT THE USUAL ONE", s)
        self.assertRegex(s, r"\bA  × 1\b")
        self.assertIsNone(re.search(r"\b[A-Z]{1,6}\s?x\s?\d", s))

    def test_the_kept_wait_says_it_no_longer_has_the_job_it_had(self):
        s = plain(part())
        self.assertIn("this wait has no known job left", s)
        self.assertIn("IT IS HELD CONSTANT ANYWAY, as a control", s)

    def test_the_names_come_from_the_image_and_the_clash_is_stated(self):
        s = part()
        self.assertIn("sd:/open-gbp/GBP-AUDIO-001_stream-0016.log", s)
        self.assertIn("GBP-AUDIO-004_stream-0016-run33.log", s)
        self.assertIn("They disagree by design", plain(s))
        self.assertIn("RUN 33 is the next free number", plain(s))

    def test_it_mints_no_id_and_closes_nothing(self):
        self.assertIsNone(re.search(r"^#{2,4} +GBP-[A-Z]+-\d{3}\b", part(), re.M))
        ev = read(EV)
        self.assertEqual(max(int(n) for n in re.findall(
            r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 307)
        s = plain(part())
        self.assertIn("U-GBP-038 stays open", s)
        self.assertIn("whose mechanism is unexplained", s)

    def test_nothing_beyond_run_32_is_claimed_to_have_happened(self):
        s = part()
        self.assertNotIn("RUN 34", s)
        self.assertIn("the files do not exist", s)


if __name__ == "__main__":
    unittest.main()
