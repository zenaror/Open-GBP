"""§V10 (GitHub Issue #68) — the amplitude sweep's DESIGN, pinned.

Nothing here is evidence and nothing here runs hardware. What these tests
defend is that the design SAYS what it must say before anything exists: the
four amplitudes and their arithmetic, the six failure forms told apart from one
another, the one-ROM recommendation resting on a capability the capture
already has, the rider's deferral, the wait in the steps — and, above all, that
§V10 remains a DESIGN. A design that quietly acquires a frozen construction, an
evidence id or a status is a pre-registration wearing the wrong name, and Issue
#68's scope forbids one.
"""
import math
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def flat(s):
    return re.sub(r" +", " ", s.replace("\n", " "))


def part():
    """§V10, from its heading to the end of the document."""
    t = read(HW)
    i = t.index("\n## V10 ")
    j = t.find("\n## V", i + 1)
    return (t[i:j] if j >= 0 else t[i:]).lstrip("\n")


# --------------------------------------------------------------- the arithmetic

class TheNumbersAreWhatTheyClaimToBe(unittest.TestCase):
    """Every figure in §V10 recomputed from its own stated premises. A design
    whose arithmetic does not close is worse than no design: it would be
    adopted by the pre-registration that follows it."""

    def test_the_four_predicted_duties_follow_from_the_linear_model(self):
        s = flat(part())
        for V, lo, hi in ((15, 0.3750, 0.6250), (11, 0.4083, 0.5917),
                          (7, 0.4417, 0.5583), (3, 0.4750, 0.5250)):
            dev = 0.125 * V / 15.0
            self.assertAlmostEqual(0.5 - dev, lo, places=4)
            self.assertAlmostEqual(0.5 + dev, hi, places=4)
            self.assertIn("%.4f    %.4f" % (lo, hi), part().replace("\n", "\n"),
                          "V=%d's pair is not on the page as computed" % V)
        self.assertIn("deviation = 0.125 x (V / 15)", s)

    def test_the_steps_are_evenly_spaced_and_clear_of_the_quantisation_floor(self):
        devs = [0.125 * V / 15.0 for V in (15, 11, 7, 3)]
        gaps = [256 * (devs[i] - devs[i + 1]) for i in range(3)]
        for g in gaps:
            self.assertAlmostEqual(g, 8.5, places=1)
        self.assertAlmostEqual(256 * devs[-1], 6.4, places=1)
        s = flat(part())
        self.assertIn("8.5 bytes of 256 apart", s)
        self.assertIn("6.4 bytes", s)

    def test_the_compressive_model_separates_by_at_least_five_bytes(self):
        """The reason four levels are worth more than two, checked rather than
        asserted: the two models must be distinguishable at every point that is
        not the anchor, or the sweep only says 'it moved'."""
        worst = None
        for V in (11, 7, 3):
            lin = 0.125 * V / 15.0
            comp = 0.125 * math.log2(1.0 + V) / math.log2(16.0)
            d = 256 * abs(lin - comp)
            worst = d if worst is None or d < worst else worst
        self.assertGreaterEqual(worst, 5.0)
        self.assertAlmostEqual(worst, 5.2, places=1)
        s = flat(part())
        self.assertIn("at least 5 bytes at every point that is not the anchor", s)

    def test_the_four_frequencies_are_exact_and_their_block_counts_are_right(self):
        for n, f, blocks in ((1024, 128.0, 32), (1792, 512.0, 8),
                             (1536, 256.0, 16), (1920, 1024.0, 4)):
            self.assertEqual(2048 - n, 2 ** int(math.log2(2048 - n)))  # exact frequency
            self.assertAlmostEqual(131072.0 / (2048 - n), f, places=6)
            self.assertAlmostEqual(4096.0 / f, blocks, places=6)
        s = flat(part())
        self.assertIn("32 / 8 / 16 / 4 blocks per period", s)

    def test_the_envelope_staircase_table_is_arithmetic_not_assertion(self):
        window_s = 256 / 4096.0
        self.assertAlmostEqual(window_s * 1000.0, 62.5, places=6)
        for step, per_window in ((1, 4.0), (2, 2.0), (4, 1.0)):
            self.assertAlmostEqual(window_s / (step / 64.0), per_window, places=6)
        s = flat(part())
        self.assertIn("256 blocks at 4 096.0 blocks/s =", s)
        self.assertIn("62.5 ms", s)

    def test_the_onset_slice_is_fixed_here_with_its_margin_shown(self):
        self.assertAlmostEqual(96 * 1000 / 4096.0, 23.4375, places=4)
        self.assertAlmostEqual(18.32 * 4096 / 1000.0, 75.0, delta=0.1)
        self.assertAlmostEqual((96 - 75) / 75.0 * 100.0, 28.0, places=1)
        self.assertAlmostEqual(160 / 32.0, 5.0)
        s = flat(part())
        self.assertIn("discard the first 96 blocks of every press window", s)
        self.assertIn("so the margin is 28 %", s)

    def test_the_wait_carries_its_margin_and_its_budget(self):
        self.assertAlmostEqual(20.0 - 12.547, 7.453, places=3)
        self.assertAlmostEqual((20.0 - 12.547) / 12.547 * 100.0, 59.4, places=1)
        s = flat(part())
        self.assertIn("20 s from the picture being up", s)
        self.assertIn("59 % over the upper edge", s)
        self.assertIn("20 + 9 = 29 s", s)


# ------------------------------------------------------- what the design says

class TheDesignSaysWhatIssue68AskedFor(unittest.TestCase):

    def test_the_failure_forms_are_enumerated_and_distinguishable(self):
        s = part()
        for tag in ("F1  THE DUTIES DO NOT MOVE", "F2  THEY MOVE, NOT MONOTONICALLY",
                    "F3  MONOTONE, NOT PROPORTIONAL", "F4  AMPLITUDE IS IN THE VALUES",
                    "F5  THE DUTY IS NOT TWO-VALUED", "F6  A WINDOW CARRIES NOTHING"):
            self.assertIn(tag, s, "failure form missing: %s" % tag)

    def test_the_null_is_the_intercept_and_the_reason_is_the_confound(self):
        """The design decision that matters most: no window may predict the
        signature that a carriage failure also produces."""
        s = flat(part())
        self.assertIn("The null is the INTERCEPT, not a fifth window", s)
        self.assertIn("look **identical**", s)
        self.assertIn("any flat window in this run is unambiguously a carriage failure", s)

    def test_the_second_candidate_encoding_rides_for_free(self):
        s = flat(part())
        self.assertIn("BYTE ALPHABET changes with", s)
        self.assertIn("AT NO EXTRA COST", s)
        self.assertIn("{00,01,FE,FF}", s)
        self.assertIn("{03,07,FC}", s)

    def test_the_step_per_press_is_argued_against_the_envelope_staircase(self):
        s = flat(part())
        self.assertIn("why a step-per-press is cleaner", s)
        self.assertIn("The estimator assumes stationarity", s)
        self.assertIn("one amplitude per window", s)


class TheOneRomShapeIsArguedFromWhatAlreadyExists(unittest.TestCase):

    def test_the_anchor_really_does_carry_the_key_that_armed_the_window(self):
        """The recommendation's load-bearing claim, checked against the source
        rather than against the prose that cites it."""
        h = read(os.path.join(ROOT, "src", "gbp", "gbp_awin.h"))
        self.assertIn("uint32_t word;", h)
        self.assertIn("uint32_t keys;", h)
        parser = read(os.path.join(ROOT, "tools", "awinparse.py"))
        self.assertIn('"word": _u32(r, 0x14)', parser)
        self.assertIn('"keys": _u32(r, 0x18)', parser)
        poc = read(os.path.join(ROOT, "poc", "gbp-audio-window-probe", "source", "main.c"))
        self.assertIn("p.keys = (uint32_t)e->keys;", poc)
        self.assertIn("rising = (uint16_t)(e->word & (uint16_t)~awin_prev_word);", poc)

    def test_the_ab_mapping_is_the_default_policy_and_not_a_wish(self):
        c = read(os.path.join(ROOT, "src", "gbp", "gbp_input.c"))
        self.assertIn("{ GBP_PAD_BUTTON_A, GBP_PAD_BUTTON_B,", c)
        s = flat(part())
        self.assertIn("sends the pad's **A** to GBA **A**", s)
        self.assertIn("RUN 14 pressed A, B, SELECT, START, L", s)

    def test_each_schedule_starts_where_the_other_run_needs_it_held(self):
        s = flat(part())
        self.assertIn("a pure-B run frequency never leaves F1 = 128.0 Hz", s)
        self.assertIn("a pure-A run amplitude never leaves V = 15", s)
        self.assertIn("HOLD, not wrap", s)

    def test_the_risk_ordering_puts_the_measured_point_first(self):
        s = flat(part())
        self.assertIn("the known point first", s)
        self.assertIn("losing it costs a replication", s)

    def test_the_display_carries_the_axis_by_shape_not_colour(self):
        s = flat(part())
        self.assertIn("shape, not colour", s)
        self.assertIn("filled UPPER half that press was A", s)
        self.assertIn("filled LOWER half that press was B", s)

    def test_the_cost_of_the_flash_is_stated_and_agb_tone_is_not_edited(self):
        s = flat(part())
        self.assertIn("one more NOR write", s)
        self.assertIn("a pure-a run is a superset of run 31", s.lower())
        self.assertIn("never an edit of `stimulus/agb-tone`", s)
        # and it really is not edited
        base = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "-1", "--grep",
                               "Issue #65 -- agb-tone built"], capture_output=True,
                              text=True).stdout.strip()
        if not base:
            self.skipTest("the commit that built agb-tone is not in this checkout")
        d = subprocess.run(["git", "-C", ROOT, "diff", "--stat", base, "--",
                            "stimulus/agb-tone"], capture_output=True, text=True).stdout
        self.assertEqual(d.strip(), "", "stimulus/agb-tone changed since it was built")


class TheRiderIsPricedAndDeferredForAStatedReason(unittest.TestCase):

    def test_the_recommendation_is_wait_and_the_reason_is_the_precondition(self):
        s = flat(part())
        self.assertIn("the recommendation is **WAIT**", s)
        self.assertIn("It manipulates the precondition of the primary question", s)
        self.assertIn("one question standing on the other's manipulation", s)

    def test_the_v613_precedent_is_read_rather_than_invoked(self):
        """§V6.13's two questions shared ONE image and ONE run; this rider needs
        a second image. The design says so, and §V6.13 still reads that way."""
        s = flat(part())
        self.assertIn("not quite the precedent it looks like", s)
        self.assertIn("**one image and one run**", s)
        v6 = read(HW)
        i = v6.index("### V6.13 PASS / FAIL / INCONCLUSIVE")
        block = v6[i:i + 2000]
        self.assertIn("GBP-VIDEO-007", block)
        self.assertIn("GBP-VIDEO-008", block)
        self.assertIn("Neither verdict consults the other's evidence", block)

    def test_the_cost_to_the_operator_is_named_as_the_real_one(self):
        s = flat(part())
        self.assertIn("a SECOND BOOT and a second press run HIS, and it is the real cost", s)
        self.assertIn("TWO checklists, and crossing them loses a run", s)


class TheBoundIsInTheShapeOfTheActionList(unittest.TestCase):

    def test_the_step_carries_the_reason_beside_it(self):
        s = part()
        self.assertIn("THE TWELVE-SECOND BOUND GOES IN THE STEPS", s)
        self.assertIn("---- WHY:", s)
        self.assertIn("The reason travels with the step", flat(s))

    def test_the_epoch_he_can_observe_is_named_with_its_offset(self):
        s = flat(part())
        self.assertIn("164.696 ms after the CONTROL transform", s)
        self.assertIn("within ~0.2 s of", s)

    def test_the_notation_follows_the_operator_checklist_convention(self):
        """Count separated by × and whitespace, as every checklist since §V7.6."""
        s = part()
        self.assertRegex(s, r"\bB  × 1\b")
        self.assertIn("wait  >= 3 s", s)

    def test_it_says_what_v912_got_wrong_without_rewriting_v912(self):
        s = flat(part())
        self.assertIn('§V9.12\'s did', s)
        self.assertIn("RUN 31 lost two of its four windows to that", s)
        # §V9.12 itself keeps its words
        v9 = read(HW)
        i = v9.index("### V9.12 The Operator's action list")
        self.assertIn("wait until the screen is up and stable", v9[i:i + 3000])


# ------------------------------------------------- and it stays a DESIGN

class NothingWasFrozenMintedOrPromoted(unittest.TestCase):

    def test_the_heading_says_it_is_not_a_pre_registration(self):
        h = part().split("\n", 1)[0]
        self.assertIn("NOT A PRE-REGISTRATION", h)
        self.assertIn("NOTHING HERE IS FROZEN", h)

    def test_the_part_mints_no_evidence_id(self):
        self.assertNotRegex(part(), r"^#{2,4} +GBP-[A-Z]+-\d{3}\b")
        # and EVIDENCE.md gained nothing
        ev = read(EV)
        self.assertEqual(max(int(n) for n in re.findall(
            r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 311)
        self.assertNotIn("Issue #68", ev)

    def test_the_unknowns_kept_their_status_and_only_gained_pointers(self):
        u = read(UNK)
        fu = flat(u)
        self.assertIn("this item stays exactly as OPEN as it was", fu)
        self.assertIn("The item is unchanged and still P2", fu)
        # U-GBP-012's heading is untouched by this checkpoint
        head = [l for l in u.split("\n") if l.startswith("## U-GBP-012")][0]
        self.assertNotIn("#68", head)
        head39 = [l for l in u.split("\n") if l.startswith("## U-GBP-039")][0]
        self.assertNotIn("#68", head39)

    def test_no_new_frozen_construction_was_added_to_tools(self):
        """§V9 froze tools/v9tone.py before RUN 31. A DESIGN freezes nothing,
        so this checkpoint must not have added a v10 analyser."""
        self.assertFalse(os.path.exists(os.path.join(ROOT, "tools", "v10sweep.py")))
        for name in ("v8audio.py", "v9tone.py"):
            base = subprocess.run(
                ["git", "-C", ROOT, "log", "--format=%H", "-1", "--", "tools/" + name],
                capture_output=True, text=True).stdout.strip()
            if not base:
                continue
            d = subprocess.run(["git", "-C", ROOT, "diff", "--stat", base, "--",
                                "tools/" + name], capture_output=True, text=True).stdout
            self.assertEqual(d.strip(), "", "tools/%s changed" % name)

    def test_the_explicit_non_claims_are_present(self):
        s = flat(part())
        self.assertIn("It authorises **no ROM, no build, no image, no staging and no hardware**", s)
        self.assertIn("a proposal adopted after data exists is worth nothing", s)
        self.assertIn("H-PWM is named so it can fail, and naming it is not evidence for it", s)

    def test_nothing_beyond_run_31_is_claimed_to_have_happened(self):
        s = part()
        self.assertNotIn("RUN 32", s)
        self.assertNotIn("EXECUTED", s.replace("RUN 30 EXECUTED", "").replace("RUN 31 EXECUTED", ""))


if __name__ == "__main__":
    unittest.main()
