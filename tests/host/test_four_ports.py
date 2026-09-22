"""
tests/host/test_four_ports.py — GitHub Issue #63: four ports, one controller.

A RECORD AND A SCOPE CORRECTION, so the tests are about the record and about
the claim underneath it. The claim is the one that can rot: "Open-GBP reads
port 1 only" is true today and becomes false the moment the implementation
checkpoint lands, so it is checked against the SOURCES on every run rather
than trusted as prose.

The other half is discipline: an inference must stay labelled as one. §15.4
reads the merge rule as an OR from the Operator's sentence, and the tests
require the label to still be there — a project that lets "almost certainly"
quietly become "is" has lost the thing that makes its records worth keeping.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
INPUT_PATH = os.path.join(ROOT, "docs", "research", "INPUT_PATH.md")
PHASE5 = os.path.join(ROOT, "docs", "research", "PHASE5_ASSESSMENT.md")
POCS = ("gbp-video-stream-probe", "gbp-play-session", "gbp-audio-window-probe")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def part(doc, name):
    t = read(doc)
    i = t.index(name)
    j = t.find("\n## ", i + 1)
    return t[i:j] if j != -1 else t[i:]


class ThePortOneClaimIsCheckedAgainstTheSources(unittest.TestCase):
    """The one statement in §15 that a later checkpoint will make false."""

    def _channels(self):
        found = {}
        for d in POCS:
            p = os.path.join(ROOT, "poc", d, "source", "main.c")
            if not os.path.exists(p):
                continue
            found[d] = re.findall(r"PAD_CHAN(\d)", read(p))
        return found

    def test_every_controller_read_is_channel_0(self):
        found = self._channels()
        self.assertEqual(sorted(found), sorted(POCS), "an image with an input path is missing")
        for d, chans in found.items():
            self.assertTrue(chans, "%s reads no controller at all" % d)
            self.assertEqual(set(chans), {"0"}, "%s reads a channel other than 0: %s" % (d, set(chans)))

    def test_the_count_the_record_states_is_the_count_in_the_tree(self):
        n = sum(len(v) for v in self._channels().values())
        # src/ holds no channel of its own: the policy module is fed a sample, it does not poll
        for root, _dirs, files in os.walk(os.path.join(ROOT, "src")):
            for f in files:
                if f.endswith((".c", ".h")):
                    self.assertNotIn("PAD_CHAN", read(os.path.join(root, f)), os.path.join(root, f))
        self.assertIn("29 occurrences in all", read(INPUT_PATH))
        self.assertEqual(n, 29, "the tree has %d PAD_CHAN0 reads and §15.2 states 29" % n)

    def test_no_other_channel_appears_anywhere(self):
        for base in ("poc", "src"):
            for root, _dirs, files in os.walk(os.path.join(ROOT, base)):
                for f in files:
                    if f.endswith((".c", ".h")):
                        body = read(os.path.join(root, f))
                        for ch in ("PAD_CHAN1", "PAD_CHAN2", "PAD_CHAN3"):
                            self.assertNotIn(ch, body, os.path.join(root, f))


class TheRecordKeepsTheObservationAndItsStatus(unittest.TestCase):

    def test_the_operators_words_are_verbatim_and_labelled(self):
        s = part(INPUT_PATH, "## 15. FOUR PORTS, ONE CONTROLLER")
        self.assertIn("o gamecube tem 4 portas, todas no GB Player funcionam", s)
        self.assertIn("independente se for um GBA via multiboot ROM ou controle", s)
        self.assertIn("que é o que acontece hoje", s)
        self.assertIn("OPERATOR OBSERVATION", s)
        self.assertIn("not a measurement\nthis project performed", s)

    def test_the_merge_is_answered_only_as_to_whether(self):
        s = plain(part(INPUT_PATH, "## 15. FOUR PORTS, ONE CONTROLLER"))
        self.assertIn("ANSWERED (as an OPERATOR OBSERVATION of the references) THAT they merge", s)
        self.assertIn("STILL OPEN, and it is POLICY HOW they merge", s)
        self.assertIn("ONE rule and not two", s)

    def test_the_or_reading_is_labelled_an_inference(self):
        """The discipline this file exists for."""
        s = plain(part(INPUT_PATH, "## 15. FOUR PORTS, ONE CONTROLLER"))
        self.assertIn("almost certainly an OR", s)
        self.assertIn("That is a reading of the Operator's sentence, not a measurement", s)
        self.assertIn("labelled as one here", s)
        # and the alternatives are named, so the choice is visible as a choice
        for cand in ("OR", "LAST-WRITER-WINS", "FIRST-SEEN"):
            self.assertIn(cand, s)

    def test_the_opposite_direction_question_is_named_and_not_resolved(self):
        s = plain(part(INPUT_PATH, "## 15. FOUR PORTS, ONE CONTROLLER"))
        self.assertIn("filter-then-merge", s)
        self.assertIn("merge-then-filter", s)
        self.assertIn("neither is obviously right, and the references' answer is unknown", s)
        self.assertIn("This is not resolved here", s)
        # the filter it interacts with is a real thing in the tree
        self.assertIn("GBP_INPUT_POLICY_DEFAULT", read(INPUT_PATH))
        self.assertIn("GBP_INPUT_POLICY_DEFAULT", read(os.path.join(ROOT, "src", "gbp", "gbp_input.h")))

    def test_the_section_mints_nothing_and_writes_no_code(self):
        s = plain(part(INPUT_PATH, "## 15. FOUR PORTS, ONE CONTROLLER"))
        self.assertIn("RECORD AND SCOPE ONLY", s)
        self.assertIn("No code, no evidence id, no status change, no hardware", s)
        self.assertNotRegex(s, r"GBP-HW-\d{3}")
        self.assertNotRegex(s, r"GBP-KEY-\d{3}")


class R6IsRepricedOnTopAndPhase5IsNotReopened(unittest.TestCase):

    def test_the_original_words_of_r6_are_still_there(self):
        t = read(PHASE5)
        self.assertIn("R6  THE ANALOGUE TRIGGER, PORTS 2-4, OTHER PADS", t)
        self.assertIn("what is missing   everything: the FACT covers the digital click on two pads in port 1.", t)
        self.assertIn("what retires it   a run designed for it, with its own pre-registration.", t)

    def test_the_repricing_is_dated_and_says_what_changed(self):
        s = plain(part(PHASE5, "### 6b. R6 RE-PRICED"))
        self.assertIn("2026-09-22 (GitHub Issue #63)", s)
        self.assertIn("its words above stay", s)
        self.assertIn("R6 WAS ports 2-4 and other pads are UNTESTED", s)
        self.assertIn("BEHAVIOURAL GAP AGAINST THE REFERENCES", s)
        self.assertIn("AN IMPLEMENTATION GAP SITS IN FRONT OF IT", s)
        self.assertIn("the run is the cheapest part", s)

    def test_phase_5_is_not_reopened(self):
        s = plain(part(PHASE5, "### 6b. R6 RE-PRICED"))
        self.assertIn("This does NOT reopen Phase 5", s)
        self.assertIn("A residual becoming better understood is the system working", s)
        # the verdict itself is untouched
        self.assertIn("SATISFIED WITH NAMED RESIDUALS", read(PHASE5))

    def test_the_phase_table_carries_the_correction(self):
        t = read(PHASE5)
        i = t.index("the analogue trigger, ports 2-4, other pads")
        self.assertIn("IMPLEMENTATION gap in front of the run", t[i:i + 400])
        self.assertIn("PAD_CHAN0 only", t[i:i + 500])


if __name__ == "__main__":
    unittest.main()
