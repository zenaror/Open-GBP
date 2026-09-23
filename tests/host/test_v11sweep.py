"""§V11 (GitHub Issue #69) — the pre-registration, and its constructions.

Two jobs. First, `tools/v11sweep.py` must BEHAVE as §V11's text says, on
synthetic vectors only: the verdicts, the refusals, the intercept, the model
separation. Second, §V11 must remain a PRE-REGISTRATION — it authorises
nothing, it answers nothing, and it may not acquire a run, a hash for a ROM
that does not exist, or an evidence id.

The separation between the two competing models is asserted rather than
printed: §V11.4 claims ≥5 bytes at every non-anchor point and >9 at two, and an
edit that narrowed it would weaken the experiment silently. Here it fails.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")

import v11sweep as v  # noqa: E402


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _bounded(t, start):
    i = t.index(start)
    j = t.find("\n## V", i + 1)
    return t[i:j] if j >= 0 else t[i:]


def part():
    return _bounded(read(HW), "\n## V11 — GBP-AUDIO-003").lstrip("\n")


def prereg():
    """§V11.1 – §V11.14: the PRE-REGISTRATION PROPER, which is what the freeze
    guards below are about. §V11.15 is Issue #70's build appendix, appended
    after it and recording an artifact rather than a gate -- the same split
    §V9.14 made, and the reason the ROM's hash may appear there and only there."""
    s = part()
    i = s.find("\n### V11.15 ")
    return s[:i] if i >= 0 else s


def flat(s):
    return re.sub(r" +", " ", s.replace("\n", " "))


# ---------------------------------------------------------- synthetic vectors

def block(d, lo=0x03, hi=0xFC):
    """A 4096-byte block whose duty() is d, built from two levels as every
    window observed so far has been."""
    n = int(round(d * 4096))
    return [hi] * n + [lo] * (4096 - n)


def window(dev, period, onset=v.ONSET_SLICE_BLOCKS, lo=0x03, hi=0xFC,
           blocks=v.BLOCKS_PER_WINDOW):
    """A press window: `onset` flat blocks (the AGB has not reacted yet), then a
    square in the per-block duty of the given half-amplitude and period."""
    out = []
    for i in range(blocks):
        if i < onset:
            d = v.RESTING_DUTY
        else:
            phase = ((i - onset) % period) / float(period)
            d = v.RESTING_DUTY + (dev if phase < 0.5 else -dev)
        out.append(block(d, lo, hi))
    return out


def flat_window():
    """U-GBP-038's signature, as RUN 31's presses 1 and 2 actually looked: a
    two-level cell at exactly half duty, in every block."""
    return [block(v.RESTING_DUTY) for _ in range(v.BLOCKS_PER_WINDOW)]


def degenerate_window():
    return [[0x80] * 4096 for _ in range(v.BLOCKS_PER_WINDOW)]


def b_run(devs):
    return [window(d, 32) for d in devs], [v.KEY_B] * len(devs)


# ----------------------------------------------------------------- the models

class TheTwoModelsAreSeparableAndThatIsAProperty(unittest.TestCase):

    def test_both_models_agree_exactly_at_the_anchor(self):
        self.assertAlmostEqual(v.deviation_linear(v.ANCHOR_VOLUME),
                               v.ANCHOR_DEVIATION, places=12)
        self.assertAlmostEqual(v.deviation_compressive(v.ANCHOR_VOLUME),
                               v.ANCHOR_DEVIATION, places=12)

    def test_the_separation_is_at_least_five_bytes_everywhere_and_over_nine_twice(self):
        """§V11.4's claim, asserted so a narrowing edit FAILS instead of quietly
        weakening the experiment."""
        sep = v.model_separation_bytes()
        self.assertEqual(sorted(sep), [3, 7, 11])
        for volume, bytes_apart in sep.items():
            self.assertGreaterEqual(bytes_apart, 5.0,
                                    "V=%d separates by only %.2f bytes" % (volume, bytes_apart))
        self.assertGreaterEqual(sum(1 for x in sep.values() if x > 9.0), 2)
        self.assertAlmostEqual(sep[11], 5.2, places=1)
        self.assertAlmostEqual(sep[7], 9.1, places=1)
        self.assertAlmostEqual(sep[3], 9.6, places=1)

    def test_the_linear_predictions_are_the_ones_on_the_page(self):
        want = {15: 32.0, 11: 23.5, 7: 14.9, 3: 6.4}
        for volume, b in want.items():
            self.assertAlmostEqual(v.deviation_linear(volume) / v.BYTE, b, places=1)
        s = part()
        for row in (" 15      32.0 B", " 11      23.5 B", "  7      14.9 B", "  3       6.4 B"):
            self.assertIn(row, s)

    def test_the_intercept_is_the_null_and_it_finds_the_origin(self):
        devs = [v.deviation_linear(x) for x in v.AMPLITUDES]
        slope, intercept = v.fit_intercept(list(v.AMPLITUDES), devs)
        self.assertAlmostEqual(intercept / v.BYTE, 0.0, places=6)
        self.assertGreater(slope, 0.0)
        # the compressive data does NOT pass through the origin, which is the point
        devs = [v.deviation_compressive(x) for x in v.AMPLITUDES]
        _, intercept = v.fit_intercept(list(v.AMPLITUDES), devs)
        self.assertGreater(intercept / v.BYTE, 5.0)

    def test_the_four_frequencies_are_exact_and_give_the_stated_periods(self):
        self.assertEqual([v.frequency_hz(n) for n in v.FREQUENCY_N],
                         [128.0, 512.0, 256.0, 1024.0])
        self.assertEqual([v.blocks_per_period(n) for n in v.FREQUENCY_N],
                         [32.0, 8.0, 16.0, 4.0])


# -------------------------------------------------------------- QUESTION V

class QuestionVDecidesOnTheOrder(unittest.TestCase):

    def test_a_linear_run_is_ORDERED_and_the_comparison_names_linear(self):
        w, k = b_run([v.deviation_linear(x) for x in v.AMPLITUDES])
        r = v.question_V(w, k)
        self.assertEqual(r["verdict"], "ORDERED")
        self.assertAlmostEqual(r["span_bytes"], 25.6, places=1)
        self.assertAlmostEqual(r["intercept_bytes"], 0.0, delta=0.2)
        self.assertEqual(r["models"]["closer"], "linear")

    def test_a_compressive_run_is_ALSO_ORDERED_and_the_comparison_separates_them(self):
        """The order gate must NOT refuse the competitor: that is what the
        measurement beside the verdict is for."""
        w, k = b_run([v.deviation_compressive(x) for x in v.AMPLITUDES])
        r = v.question_V(w, k)
        self.assertEqual(r["verdict"], "ORDERED")
        self.assertEqual(r["models"]["closer"], "compressive")
        self.assertGreater(r["models"]["margin_bytes"], 20.0)
        self.assertGreater(r["intercept_bytes"], 5.0)

    def test_no_movement_at_all_is_DOES_NOT_MOVE(self):
        w, k = b_run([0.125] * 4)
        self.assertEqual(v.question_V(w, k)["verdict"], "DOES NOT MOVE")

    def test_movement_out_of_order_is_MOVES_NOT_ORDERED(self):
        w, k = b_run([v.deviation_linear(x) for x in (15, 3, 11, 7)])
        self.assertEqual(v.question_V(w, k)["verdict"], "MOVES, NOT ORDERED")

    def test_one_byte_of_slack_does_not_count_as_a_violation(self):
        base = [v.deviation_linear(x) for x in v.AMPLITUDES]
        base[2] = base[1] + v.BYTE          # a one-byte rise, inside the slack
        w, k = b_run(base)
        self.assertEqual(v.question_V(w, k)["verdict"], "ORDERED")
        base[2] = base[1] + 3 * v.BYTE      # three bytes is not
        w, k = b_run(base)
        self.assertEqual(v.question_V(w, k)["verdict"], "MOVES, NOT ORDERED")


class AFlatWindowIsACarriageFailureAndNeverAReading(unittest.TestCase):
    """§V11.4.1's whole point: no schedule entry predicts flat, so flat has
    exactly one meaning."""

    def test_the_classifier_calls_it_a_carriage_failure(self):
        c = v.classify_window(flat_window())
        self.assertEqual(c["state"], "CARRIAGE FAILURE")
        self.assertIsNone(c["deviation"])

    def test_the_question_is_inconclusive_and_names_the_windows_and_the_unknown(self):
        w = [window(v.deviation_linear(15), 32), flat_window(),
             window(v.deviation_linear(7), 32), window(v.deviation_linear(3), 32)]
        r = v.question_V(w, [v.KEY_B] * 4)
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertIn("[2]", r["why"])
        self.assertIn("U-GBP-038", r["why"])
        self.assertIn("no schedule entry predicts a flat window", r["why"])

    def test_no_schedule_entry_predicts_a_flat_window(self):
        """The property the whole design rests on: every amplitude in the
        schedule predicts a deviation clear of the flat tolerance."""
        for volume in v.AMPLITUDES:
            self.assertGreater(v.deviation_linear(volume), v.FLAT_TOLERANCE)
            self.assertGreater(v.deviation_compressive(volume), v.FLAT_TOLERANCE)
        self.assertNotIn(0, v.AMPLITUDES)

    def test_a_single_valued_block_is_NO_CELL_and_not_a_carriage_failure(self):
        c = v.classify_window(degenerate_window())
        self.assertEqual(c["state"], "NO CELL")
        r = v.question_V([window(v.deviation_linear(15), 32)] + [degenerate_window()] * 3,
                         [v.KEY_B] * 4)
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertIn("no two-level cell", r["why"])
        self.assertIn("a finding", r["why"])


# -------------------------------------------------------------- QUESTION F

class QuestionFDecidesOnTheRatios(unittest.TestCase):

    def test_the_ladder_holds_and_gives_six_pairs(self):
        w = [window(0.125, int(v.blocks_per_period(n))) for n in v.FREQUENCY_N]
        r = v.question_F(w, [v.KEY_A] * 4)
        self.assertEqual(r["verdict"], "RATIOS HOLD")
        self.assertEqual(len(r["pairs"]), 6)
        self.assertEqual(r["periods"], [32, 8.0, 16.0, 4.0])
        self.assertEqual(r["absent"], [])

    def test_one_wrong_note_breaks_it(self):
        periods = [32, 8, 16, 4]
        periods[2] = 24                      # 384 Hz where 256 was asked for
        w = [window(0.125, p) for p in periods]
        r = v.question_F(w, [v.KEY_A] * 4)
        self.assertEqual(r["verdict"], "RATIOS DO NOT HOLD")
        self.assertTrue(r["failed_pairs"])

    def test_the_tolerance_is_the_inherited_ten_percent(self):
        self.assertEqual(v.RATIO_TOLERANCE, 0.10)
        self.assertEqual(v.MIN_RISING_EDGES, 3)
        self.assertEqual(v.UNIFORMITY_MIN, 0.90)


# ------------------------------------------------ QUESTION E, on its own

class QuestionEReadsTheLevelsAndNotTheDuty(unittest.TestCase):

    def test_levels_that_close_in_with_the_schedule_are_LEVELS_MOVE(self):
        w = [window(0.0, 32, lo=0x80 - s, hi=0x80 + s) for s in (60, 44, 28, 12)]
        r = v.question_E(w, [v.KEY_B] * 4, "V")
        self.assertEqual(r["verdict"], "LEVELS MOVE")
        self.assertEqual(r["spans"], [120, 88, 56, 24])

    def test_a_normal_duty_sweep_leaves_the_levels_alone(self):
        w, k = b_run([v.deviation_linear(x) for x in v.AMPLITUDES])
        self.assertEqual(v.question_E(w, k, "V")["verdict"], "LEVELS STABLE")

    def test_the_two_questions_do_not_consult_each_other(self):
        """§V6.13's rule, and the reason the alphabet-shift is a DIRECTION and
        not a null: V says DOES NOT MOVE while E says LEVELS MOVE, on the same
        four windows."""
        w = [window(0.0, 32, lo=0x80 - s, hi=0x80 + s) for s in (60, 44, 28, 12)]
        k = [v.KEY_B] * 4
        self.assertEqual(v.question_V(w, k)["verdict"], "INCONCLUSIVE")
        self.assertEqual(v.question_E(w, k, "V")["verdict"], "LEVELS MOVE")
        import inspect
        src = inspect.getsource(v.question_E)
        self.assertNotIn("question_V", src)
        self.assertNotIn("question_V", inspect.getsource(v.question_F))


# --------------------------------------------- the schedule is DERIVED

class TheScheduleIsReadFromTheKeyRecordAndAMismatchIsRefused(unittest.TestCase):

    def test_the_axis_comes_from_the_gba_key_bits(self):
        self.assertEqual(v.axis_of_window(0x0001), "F")
        self.assertEqual(v.axis_of_window(0x0002), "V")
        for other in (0x0000, 0x0003, 0x0004, 0x0008, 0x0200):
            self.assertIsNone(v.axis_of_window(other))

    def test_a_uniform_run_derives_its_axis_and_a_mixed_one_says_so(self):
        self.assertEqual(v.derive_schedule([v.KEY_B] * 4), "V")
        self.assertEqual(v.derive_schedule([v.KEY_A] * 4), "F")
        self.assertEqual(v.derive_schedule([v.KEY_A, v.KEY_B, v.KEY_A, v.KEY_A]), "MIXED")
        self.assertEqual(v.derive_schedule([0x0004] * 4), "UNKNOWN")

    def test_a_question_refuses_rather_than_reading_the_other_experiment(self):
        w, _ = b_run([v.deviation_linear(x) for x in v.AMPLITUDES])
        r = v.question_V(w, [v.KEY_B, v.KEY_A, v.KEY_B, v.KEY_B])
        self.assertEqual(r["verdict"], "REFUSED")
        self.assertIn("[2]", r["why"])
        self.assertEqual(r["refused"], [(2, v.KEY_A)])
        # and it does NOT fall through to a reading
        self.assertNotIn("deviations", r)
        r = v.question_F(w, [v.KEY_B] * 4)
        self.assertEqual(r["verdict"], "REFUSED")

    def test_the_anchor_really_carries_keys_so_this_needs_no_firmware_change(self):
        h = read(os.path.join(ROOT, "src", "gbp", "gbp_awin.h"))
        self.assertIn("uint32_t keys;", h)
        self.assertIn('"keys": _u32(r, 0x18)', read(os.path.join(ROOT, "tools", "awinparse.py")))


# ------------------------------------------------- the frozen constants

class TheConstantsAreTheOnesOnThePage(unittest.TestCase):

    def test_the_schedules_and_the_slice(self):
        self.assertEqual(v.AMPLITUDES, (15, 11, 7, 3))
        self.assertEqual(v.FREQUENCY_N, (1024, 1792, 1536, 1920))
        self.assertEqual(v.ONSET_SLICE_BLOCKS, 96)
        self.assertEqual(v.DRAIN_BLOCKS_PER_S, 4096.0)
        s = part()
        self.assertIn("ONSET_SLICE_BLOCKS = 96", s)
        self.assertIn("n = 1024 -> 1792 -> 1536 -> 1920", s)
        self.assertIn("initial volume 15 -> 11 -> 7 -> 3", s)

    def test_the_onset_slice_derivation_closes(self):
        self.assertAlmostEqual(96 * 1000.0 / v.DRAIN_BLOCKS_PER_S, 23.4375, places=4)
        self.assertAlmostEqual(18.32 * v.DRAIN_BLOCKS_PER_S / 1000.0, 75.0, delta=0.1)
        self.assertAlmostEqual(96 / 75.0, 1.28, places=2)
        left = v.BLOCKS_PER_WINDOW - v.ONSET_SLICE_BLOCKS
        self.assertEqual(left, 160)
        self.assertAlmostEqual(left / v.blocks_per_period(v.FREQUENCY_N[0]), 5.0)

    def test_the_move_threshold_sits_below_both_predicted_spans(self):
        lin = v.deviation_linear(15) - v.deviation_linear(3)
        comp = v.deviation_compressive(15) - v.deviation_compressive(3)
        self.assertAlmostEqual(lin / v.BYTE, 25.6, places=1)
        self.assertAlmostEqual(comp / v.BYTE, 16.0, places=1)
        self.assertLess(v.MOVE_SPAN_MIN, comp)
        self.assertIn("The linear model predicts a span", flat(part()))

    def test_the_construction_is_not_edited_after_its_commit(self):
        base = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "-1", "--grep",
                               "Issue #69 -- the sweep pre-registered"],
                              capture_output=True, text=True).stdout.strip()
        if not base:
            self.skipTest("the commit that introduced tools/v11sweep.py is not in this checkout")
        then = subprocess.run(["git", "-C", ROOT, "show", "%s:tools/v11sweep.py" % base],
                              capture_output=True, text=True).stdout
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v11sweep.py")),
                         "tools/v11sweep.py changed after the commit that froze it")


# ------------------------------------------ and it stays a PRE-REGISTRATION

class ItAuthorisesNothingAndAnswersNothing(unittest.TestCase):

    def test_the_heading_says_not_run_not_authorised(self):
        h = part().split("\n", 1)[0]
        self.assertIn("NOT RUN, NOT AUTHORISED HERE", h)
        self.assertIn("PRE-REGISTERED", h)

    def test_the_rom_hash_is_refused_rather_than_left_blank(self):
        s = flat(prereg())
        self.assertIn("IT DOES NOT EXIST", s)
        self.assertIn("THIS PART CANNOT STATE THEM AND DOES NOT LEAVE A BLANK FOR THEM", s)
        # no 64-hex string may appear in the PRE-REGISTRATION except the image's,
        # which did exist. Issue #70's appendix (§V11.15) carries the ROM's.
        hashes = set(re.findall(r"\b[0-9a-f]{64}\b", prereg()))
        self.assertEqual(hashes, {"c3281a8c1382a1136a881c5548ef8238d69fa"
                                  "7862861d66741310b3d1f5f9c54"})

    def test_the_reserved_names_come_from_the_image_and_the_clash_is_stated(self):
        s = part()
        self.assertIn("sd:/open-gbp/GBP-AUDIO-001_stream-0016.log", s)
        self.assertIn("captures/local/GBP-AUDIO-003_stream-0016-run32.log", s)
        self.assertIn("THE TWO DISAGREE, AND THAT IS CORRECT", flat(s))
        self.assertIn("GBP-HW-300", s)
        # and the image really does embed that TEST_ID
        self.assertIn('#define TEST_ID "GBP-AUDIO-001"',
                      read(os.path.join(ROOT, "poc", "gbp-audio-window-probe", "source", "main.c")))
        self.assertIn('"sd:/open-gbp/%s_%s.log", test_id, build_id',
                      read(os.path.join(ROOT, "src", "platform", "sdlog.c")))

    def test_the_action_list_carries_the_wait_its_reason_and_the_button_warning(self):
        s = prereg()
        self.assertIn("WAIT 20 SECONDS", s)
        self.assertIn("---- WHY:", s)
        self.assertIn("NOT a hardware property", s)
        self.assertIn("USE THE SAME BUTTON ALL FOUR TIMES", s)
        self.assertIn("a DIFFERENT", s)
        self.assertRegex(s, r"\bB  × 1\b")
        self.assertIsNone(re.search(r"\b[A-Z]{1,6}\s?x\s?\d", s))
        self.assertIn("REPLACES `agb-tone`", s)

    def test_no_paragraph_claims_a_run_or_a_rom(self):
        claims = re.compile(r"\b(RUN 32|the ROM|agb-sweep)\b[^.]{0,40}?\b(was|were)\s+"
                            r"(built|executed|run|captured|flashed|measured)\b"
                            r"|\bthe run showed\b|\bwe (observed|measured)\b", re.I)
        # the PRE-REGISTRATION may claim nothing; §V11.15 records a BUILD and §V11.16 a RUN,
        # both appended after it and both entitled to say what happened (§V9.14 / §V9.15's split)
        for para in re.split(r"\n\s*\n", prereg()):
            self.assertIsNone(claims.search(flat(para)),
                              "§V11's pre-registration claims something it cannot have:\n%s" % para[:200])

    def test_it_mints_no_evidence_id_and_moves_no_status(self):
        self.assertNotRegex(part(), r"^#{2,4} +GBP-[A-Z]+-\d{3}\b")
        ev = read(EV)
        self.assertEqual(max(int(n) for n in re.findall(
            r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 311)
        self.assertNotIn("Issue #69", ev)

    def test_the_earlier_parts_keep_their_words(self):
        for name in ("v8audio.py", "v9tone.py"):
            base = subprocess.run(
                ["git", "-C", ROOT, "log", "--format=%H", "-1", "--", "tools/" + name],
                capture_output=True, text=True).stdout.strip()
            if not base:
                continue
            d = subprocess.run(["git", "-C", ROOT, "diff", "--stat", base, "--",
                                "tools/" + name], capture_output=True, text=True).stdout
            self.assertEqual(d.strip(), "", "tools/%s changed" % name)
        self.assertIn("§V9.2.1 keeps its words; it is not edited", flat(part()))
        # Issue #70 (2026-09-22) BUILT stimulus/agb-sweep, which §V11 authorised
        # separately. What still has to hold is that §V11.1 – §V11.14 did not move
        # to accommodate it: the ROM met the specification, not the other way round.
        self.assertIn("§V11.1 – §V11.14 ARE UNTOUCHED", part())
        # Issue #72 (2026-09-23) appended §V11.16, RUN 32's ingestion. What still has to hold is
        # that the PRE-REGISTRATION did not move to accommodate the result.
        self.assertIn("### V11.16 RUN 32", part())
        # Issue #73 (2026-09-23) appended §V11.17, U-GBP-040's fix. Same rule: the
        # PRE-REGISTRATION did not move to accommodate a build or a result.
        self.assertIn("### V11.17 `U-GBP-040`", part())
        self.assertIn("§V11.1 – §V11.16 ARE UNTOUCHED", part())
        self.assertNotIn("### V11.18", part())

    def test_nothing_beyond_run_31_is_claimed_to_have_happened(self):
        self.assertNotIn("RUN 33", part())
        s = prereg()
        self.assertIn("RUN 32 is the next free number", flat(s))
        self.assertIn("the files do not exist", s)


if __name__ == "__main__":
    unittest.main()
