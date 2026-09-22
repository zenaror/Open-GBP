"""
tests/host/test_question_t_inconclusive.py — GitHub Issue #53: Question T is
INCONCLUSIVE, the lesson that produced it, and T′ pre-registered so the same
question can be answered next time.

THE VERDICT IS ABOUT THE PRE-REGISTRATION, NOT THE DEVICE, and the two are easy
to confuse a year from now. So this file pins the distinction in three places:
the record says "the gate as frozen cannot be applied"; the measurements are
marked as measurements and the table carries its own warning; and T′ carries an
explicit bar against being applied to the runs that have already happened.

THE DECISIVE DEFECT IS CHECKED AGAINST THE FILES, not asserted. `CYCLT i=6` is
AUDIO-only in RUN 17 and carries a VIDEO block in both new runs, which is what
makes the positional reference a category error — and it is wrong independently
of the answer it produces, which is what made it safe to decide after the data.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
METHOD = os.path.join(ROOT, "docs", "RESEARCH_METHOD.md")
LOCAL = os.path.join(ROOT, "captures", "local")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def part(name):
    t = read(HW)
    i = t.index(name)
    nxt = [j for j in (t.find("\n#### V7.", i + 1), t.find("\n### V7.", i + 1)) if j != -1]
    return t[i:min(nxt)] if nxt else t[i:]


class TheVerdictIsAboutThePreRegistration(unittest.TestCase):
    def test_T_is_inconclusive_for_all_four_runs_and_says_why(self):
        p = plain(part("#### V7.8.10"))
        self.assertIn("Question T = INCONCLUSIVE for RUN 21, RUN 22, RUN 25 and RUN 26", p)
        self.assertIn("A verdict about the PRE-REGISTRATION, not about the device", p)
        self.assertIn("the gate as frozen cannot be applied", p)
        self.assertIn("It says nothing about the device", p)

    def test_both_defects_are_named_and_only_one_is_decisive(self):
        p = plain(part("#### V7.8.10"))
        self.assertIn("DECISIVE -- a CATEGORY ERROR", p)
        self.assertIn("IT IS WRONG INDEPENDENTLY OF THE ANSWER IT PRODUCES", p)
        self.assertIn("a defect that could only be recognised by disliking its output would not be", p)
        self.assertIn("SECOND, AND SEPARATE -- an UNNAMED STATISTIC", p)
        # and the three verdicts are each excluded for their own reason
        for tok in ("would resolve an ambiguity AFTER the data",
                    "would elevate an artefact of one unstated statistic",
                    "excluded on its own terms"):
            self.assertIn(tok, p, tok)

    def test_the_category_error_is_true_of_the_files(self):
        """Checked, not asserted: i=6 denotes different kinds of cycle in different runs."""
        need = ["GBP-VIDEO-004_stream-0015-run17.log", "GBP-PLAY-001_play-0001-run21.log",
                "GBP-PLAY-001_play-0001-run22.log"]
        if not all(os.path.exists(os.path.join(LOCAL, f)) for f in need):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        def kind(f, i):
            m = re.search(r"^\d+ CYCL i=%d [^\n]*? v=(\d)/" % i, read(os.path.join(LOCAL, f)), re.M)
            return int(m.group(1)) if m else None
        self.assertEqual(kind(need[0], 6), 0, "CYCLT i=6 should be AUDIO-only in RUN 17")
        self.assertEqual(kind(need[1], 6), 1, "CYCLT i=6 should carry VIDEO in RUN 21")
        self.assertEqual(kind(need[2], 6), 1, "CYCLT i=6 should carry VIDEO in RUN 22")

    def test_the_measurements_cannot_be_mistaken_for_a_verdict(self):
        s = part("#### V7.8.10")
        p = plain(s)
        self.assertIn("THE MEASUREMENTS STAND, AND THEY ARE NOT A VERDICT", p)
        self.assertIn("This table is a MEASUREMENT. It is not T = NOMINAL and must never be read, cited or "
                      "summarised as one", p)
        self.assertIn("Question T has no verdict for these runs", p)
        self.assertIn("split by WHAT THE CYCLE CARRIED (not by index)", p)
        self.assertIn("THE READING, AS AN OBSERVATION AND NOTHING MORE", p)
        self.assertIn("still not a gate outcome", p)
        self.assertIn("A LATER RUN UNDER §V7.9's T' CAN TURN THIS INTO A VERDICT. These four runs cannot", p)

    def test_the_frozen_words_were_appended_to_and_not_edited(self):
        t = read(HW)
        # §V7.6.3's positional table is still there, verbatim: the defect is recorded, not erased
        self.assertIn("ACK -> RE-ARM, AUDIO-only cycles    CYCLT i=6,7: 12 ticks (0.30 us)", t)
        self.assertIn("CYCFT i=0,1,2: 1 197 / 895 / 886 ticks", t)
        self.assertIn("Written on top. §V7.6.3, §V7.6.11 and every part of §V7.8 above keep their", t)
        # and §V7.8's heading points at the amendment (the convention of Issue #49)
        head = t[t.index("### V7.8 RUN 21"):].splitlines()[0]
        self.assertIn("AMENDED 2026-09-22 (Issue #53, §V7.8.10)", head)
        self.assertIn("are NOT a verdict", head)


class ThePortableLessonIsRecorded(unittest.TestCase):
    def test_it_is_in_the_method_with_the_case_that_produced_it(self):
        m = plain(read(METHOD))
        self.assertIn("A reference figure is defined by what the element CONTAINS, never by its position", m)
        self.assertIn("2026-09-22, GitHub Issue #53", m)
        self.assertIn("\"The AUDIO-only cycles\" is a reference; \"CYCLT i=6,7\" is not", m)
        self.assertIn("what that position holds depends on what the device was doing", m)
        self.assertIn("A defect that can only be recognised by disliking its output is not safe to act on "
                      "after the data", m)
        self.assertIn("A reference table may still print index labels as provenance; it may not use them as "
                      "the matching key", m)


class TPrimeIsPreRegisteredAndBarredFromTheOldRuns(unittest.TestCase):
    def test_the_retrospective_bar_is_the_first_thing_it_says(self):
        s = read(HW)
        v79 = s[s.index("### V7.9 "):]
        first = v79[:v79.index("#### V7.9.2")]
        p = plain(first)
        self.assertIn("THE BAR THAT MATTERS MOST, stated first", p)
        self.assertIn("T′ MAY NOT BE APPLIED RETROSPECTIVELY TO RUN 17, RUN 21, RUN 22, RUN 25 OR RUN 26 AS "
                      "A VERDICT", p)
        self.assertIn("A construction written after seeing those logs can never be a gate over them", p)
        self.assertIn("A labelled retrospective computation is allowed and is NOT a verdict", p)
        self.assertIn("RETROSPECTIVE — NOT A VERDICT", plain(first))

    def test_it_matches_by_content_and_names_its_statistic(self):
        p = plain(part("#### V7.9.2") + part("#### V7.9.3"))
        self.assertIn("The INDEX IS PROVENANCE ONLY and is never a matching key", p)
        self.assertIn("The predicate is applied to BOTH sides", p)
        self.assertIn("the statistic the MEDIAN of each class", p)
        self.assertIn("a mean is dragged by it", p)
        # every deciding word of §V7.6.11 that was unnamed now has a rule
        for tok in ('"unchanged"', '"not longer"', '"not lower"', '"far from"'):
            self.assertIn(tok.replace('"', ''), p, tok)
        self.assertIn("RECOMPUTED by this same content-matching rule from its own log -- never quoted from "
                      "§V7.6.3's table", p)

    def test_the_within_run_control_gates_the_treatment(self):
        p = plain(part("#### V7.9.4"))
        self.assertIn("The control is read FIRST", p)
        self.assertIn("T' = INCONCLUSIVE for the removal", p)
        self.assertIn("the VIDEO reading cannot be attributed to it", p)

    def test_it_schedules_no_hardware_and_reopens_nothing(self):
        p = plain(part("#### V7.9.6"))
        self.assertIn("It does not schedule a run, authorise a build, or change any image", p)
        self.assertIn("they stay INCONCLUSIVE", p)
        self.assertIn("it has answered nothing", p)
        head = read(HW)[read(HW).index("### V7.9 "):].splitlines()[0]
        self.assertIn("NO HARDWARE IS SCHEDULED, NO RUN IS AUTHORISED", head)


if __name__ == "__main__":
    unittest.main()
