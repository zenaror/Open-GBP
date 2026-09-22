"""
tests/host/test_phase6_entry.py — GitHub Issue #45: Phase 6's entry assessed,
with the Operator's instrument read at its pinned commit.

THE TEST THAT MATTERS MOST IS THE LICENCE ONE. The Enhanced Control Checker is
CC BY-SA 4.0, so nothing from it may enter this repository — no image, no
source, no asset. A description of behaviour derived from reading it is this
project's own work; the source text is not. So this file checks that the
repository contains none of the source's distinctive text and none of its
binary, and it will keep checking it long after the reason is forgotten.

THE ARITHMETIC IS RECOMPUTED, not quoted: the two frequencies from GBATEK's own
formula, the envelope step from its own units, and the block counts from the
drain rate this project measured. A document whose numbers cannot be re-derived
is a document nobody can check.

AND THE IMAGE MATRIX IS VERIFIED AGAINST THE SOURCES. The claim that decides
the cheapest path — that the capture probe has no input path while the stream
and play probes do — is read from the tree rather than taken from the design.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC = os.path.join(ROOT, "docs", "research", "PHASE6_ENTRY.md")

# the pinned identity, from §V7.1's amendment
COMMIT = "76924c1371d7bf761f8b1ed45ab36f195cd1374f"
GBA_SHA = "53c212c73e814875fcbac16a4dc22ea5d6c752f85cdddc433db97439caef2b6e"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


class NothingFromTheShareAlikeSourceEnteredTheRepository(unittest.TestCase):
    """CC BY-SA 4.0: describe it, never carry it."""

    def test_no_source_text_and_no_binary(self):
        """THE LINE IS BETWEEN NAMING AND CARRYING, and it is worth stating because the
        first version of this test got it wrong.

        Naming a function to say what a program does -- "it prints a tally only on a press
        (`updateButtonTally` after `keysDown()`)" -- is a FACT ABOUT BEHAVIOUR, and the
        project has recorded exactly that since §V7.1's amendment in September. Carrying
        the program's STATEMENTS is expression, and that is what share-alike reaches. So
        the forbidden list is the source's own lines and its binary, not its symbol names.
        """
        forbidden = ["dutyCycleSettings[] = {",
                     "for (volatile int i = 0; i < 5000; i++)",
                     "REG_SOUND1CNT_X = 0x8400 | 1200",
                     "REG_SOUNDCNT_L = 0x1177;",
                     "void playTone() {"]
        hits = []
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "build", "external", "captures", "logs", "input")]
            for fn in files:
                p = os.path.join(base, fn)
                rel = os.path.relpath(p, ROOT)
                if rel.startswith("tests/host/test_phase6_entry.py"):
                    continue
                try:
                    t = read(p)
                except (UnicodeDecodeError, IsADirectoryError, PermissionError):
                    continue
                for tok in forbidden:
                    if tok in t:
                        hits.append((rel, tok))
        self.assertEqual(hits, [], "share-alike source text has entered the repository: %s" % hits)

    def test_no_copy_of_the_rom(self):
        for base, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in (".git", "external", "input")]
            for fn in files:
                self.assertNotIn("enhancedcontrolchecker", fn.lower(),
                                 "a copy of the third-party ROM is in the tree: %s" % fn)

    def test_the_document_states_the_terms_and_the_pinned_identity(self):
        p = plain(read(DOC))
        self.assertIn("CC BY-SA 4.0", p)
        self.assertIn("nothing from it enters the repository", p)
        self.assertIn(COMMIT, p)
        self.assertIn("53c212c73e814875", p)
        self.assertIn("a DESCRIPTION of behaviour derived from reading the program, not a reproduction", p)


class TheToneArithmeticIsRecomputable(unittest.TestCase):
    def test_the_two_frequencies_follow_gbateks_formula(self):
        """f = 131072 / (2048 - n), GBATEK's own words for SOUND1CNT_X bits 0-10."""
        self.assertAlmostEqual(131072.0 / (2048 - 1200), 154.57, places=2)
        self.assertAlmostEqual(131072.0 / (2048 - 0), 64.0, places=2)
        p = plain(read(DOC))
        self.assertIn("131072 / (2048 - 1200) = 131072 / 848 = 154.57 Hz", p)
        self.assertIn("131072 / 2048 = 64.0 Hz", p)
        # and the formula is cited to the reference rather than asserted
        gbatek = os.path.join(ROOT, "external", "gbatek", "gba.md")
        if os.path.exists(gbatek):
            self.assertIn("Frequency; 131072/(2048-n)Hz", read(gbatek))

    def test_the_envelope_and_the_block_counts(self):
        self.assertAlmostEqual(7.0 / 64.0 * 1000, 109.4, places=1)      # envelope step, ms
        self.assertAlmostEqual(15 * 7.0 / 64.0, 1.64, places=2)         # full decay, s
        block_ms = 1000.0 / 4094.4
        self.assertAlmostEqual(block_ms, 0.244, places=3)
        self.assertAlmostEqual((1000.0 / 64.0) / block_ms, 64.0, delta=1.0)    # one 64 Hz period
        self.assertAlmostEqual(109.4 / block_ms, 448.0, delta=2.0)             # one envelope step
        self.assertAlmostEqual(1640.0 / block_ms, 6715.0, delta=30.0)          # the whole decay
        p = plain(read(DOC))
        for tok in ("109.4 ms per step", "15 steps x 109.4 ms = 1.64 s", "one block is 0.244 ms",
                    "period 15.6 ms ~= 64 blocks", "~= 448 blocks per", "~ 6 700 blocks"):
            self.assertIn(tok, p, tok)

    def test_the_duty_cycles_per_press_and_not_per_button(self):
        p = plain(read(DOC))
        self.assertIn("12.5 %, 25 %, 50 %, 75 %", p)
        self.assertIn("Four presses give four different duty ratios at the same frequency", p)
        self.assertIn("It does not differ per button", p)


class TheStopThatDoesNotStop(unittest.TestCase):
    def test_it_is_derived_from_the_reference_and_flagged_as_a_prediction(self):
        p = plain(read(DOC))
        self.assertIn("The stop does not stop it", p)
        self.assertIn("removes the only stop that was armed", p)
        self.assertIn("This is an a-priori prediction, not an observation", p)
        self.assertIn("the capture checks the reading of the code at the same time as it answers the real "
                      "question", p)
        # GBATEK's wording is the authority for the length flag
        gbatek = os.path.join(ROOT, "external", "gbatek", "gba.md")
        if os.path.exists(gbatek):
            self.assertIn("Length Flag  (1=Stop output when length in NR11 expires)", read(gbatek))

    def test_the_unwritten_register_is_declared(self):
        p = plain(read(DOC))
        self.assertIn("SOUNDCNT_H", p)
        self.assertIn("never written", p)
        self.assertIn("a declared assumption, not a derived fact", p)


class TheImageMatrixIsReadFromTheTree(unittest.TestCase):
    def test_the_capture_probe_has_no_input_path_and_the_others_do(self):
        def uses_input(poc):
            # the POC directories are versioned, so a missing one is a FAILURE and not a
            # reason to go quiet -- there is no partial-clone case here to be honest about
            d = os.path.join(ROOT, "poc", poc)
            self.assertTrue(os.path.isdir(d), "%s is missing from the checkout" % poc)
            for base, _, files in os.walk(d):
                for fn in files:
                    if "gbp_input" in read(os.path.join(base, fn)):
                        return True
            return False
        self.assertFalse(uses_input("gbp-video-capture-probe"))
        self.assertTrue(uses_input("gbp-video-stream-probe"))
        self.assertTrue(uses_input("gbp-play-session"))
        p = plain(read(DOC))
        self.assertIn("NO -- it does not reference gbp_input at all", p)
        self.assertIn("no image has input AND retention AND emission", p)

    def test_the_slot_counts_are_the_headers(self):
        h = read(os.path.join(ROOT, "src", "gbp", "gbp_avseq.h"))
        self.assertIn("#define GBP_AVSEQ_AUDIO_FIRST_KEPT    8u", h)
        self.assertIn("#define GBP_AVSEQ_AUDIO_LAST_BUFFERS  2u", h)
        p = plain(read(DOC))
        self.assertIn("10 slots (8 first + 2 last)", p)
        self.assertIn("3 slots, 2 kept", p)

    def test_the_cheapest_path_is_argued_not_asserted(self):
        p = plain(read(DOC))
        self.assertIn("extend the STREAM probe, not the capture probe", p)
        self.assertIn("WHY NOT THE CAPTURE PROBE", p)
        self.assertIn("DERIVED, not chosen", p)
        self.assertIn("the capture must be a WINDOW", p)


class TheComparisonIsHonestAndTheDocumentAuthorisesNothing(unittest.TestCase):
    def test_the_stages_collapse_and_the_build_becomes_a_fallback(self):
        p = plain(read(DOC))
        self.assertIn("Stage A and Stage B collapse into one experiment", p)
        self.assertIn("stimulus/agb-tone becomes a FALLBACK rather than a prerequisite", p)
        self.assertIn("He has removed a build from the phase", p)
        self.assertIn("the discriminator is not \"changed\" but \"changed INTO THE PREDICTED SHAPE\"", p)

    def test_the_caveat_against_his_instrument_is_stated_not_softened(self):
        p = plain(read(DOC))
        self.assertIn("a side effect of a button press in a program written for another purpose", p)
        self.assertIn("The reason to prefer the checker anyway is not that it is better", p)
        self.assertIn("WHAT WOULD MAKE THE FALLBACK NEEDED", p)

    def test_the_negative_answer_is_a_real_result(self):
        p = plain(read(DOC))
        self.assertIn("A NEGATIVE ANSWER", p)
        self.assertIn("THAT IS A REAL RESULT", p)

    def test_it_authorises_nothing_and_carries_the_gates(self):
        p = plain(read(DOC))
        self.assertIn("DESIGN AND ASSESSMENT ONLY. It authorises nothing", p)
        self.assertIn("IDENTITY IS A GATE AND IS RE-DECLARED", p)
        self.assertIn("DO NOT RUN", p)
        self.assertIn("R4 RIDES ALONG", p)
        self.assertIn("the pre-registration is the NEXT checkpoint, not this one", p)
        self.assertIn("a match with it would be CORROBORATED, never FACT", p)


if __name__ == "__main__":
    unittest.main()
