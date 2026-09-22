"""
tests/host/test_v8audio.py — GitHub Issue #58: §V8's pre-registration, and its
predictions exercised on SYNTHETIC vectors only.

NO LOG EXISTS. At the time this file was written no build had been made, no run
was authorised and no capture of a GBP AUDIO window with a cartridge present
existed anywhere. That is the point: §V8's whole value is that the three
candidate models predict DIFFERENT BYTES FOR THE SAME WINDOW, and that value
survives only if the constructions are fixed before the bytes are seen. Every
vector here is built in this file, adversarially, by someone who cannot know
what the run will say.

THE DOCUMENT AND THE CODE MAY NOT DRIFT. §V8.3.2's arithmetic is not quoted
from the document into the test; it is recomputed by tools/v8audio.window_plan()
from the cadence and the frequencies, and the DOCUMENT is then checked against
it. A window that changes size in one place and not the other fails here.

AND THE PRE-REGISTRATION MUST STILL SAY IT AUTHORISES NOTHING. The negative
guards below are units of a paragraph or a table row, never a clause split on
punctuation — the split-on-";" defect of Issue #33 let an injected offender
through, and the fix was to make the unit big enough to contain the offence.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v8audio as v8  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
# RUN 30's raws, hashed at the ingestion (Issue #62)
LOG_SHA = "3d1830eb62939807756778c33e5f6bedac0dc609bb7ce1fa4900c662dbbc2c77"
BIN_SHA = "b3597b72adeae0cb8627e5c1b00584ca8a30bb2ff592c4b645e98cd9428ac564"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


# §V8 may not claim a run, a capture or a result: none exists. The unit the
# guard is applied to is a PARAGRAPH, never a clause split on punctuation —
# Issue #33's defect was a guard whose unit was small enough to step over the
# offence. The subject is restricted to THIS run's nouns so that a true
# statement about the EXISTING archive ("every archived block was captured with
# no Game Pak") is not mistaken for a claim about a run that has not happened.
CLAIMS = re.compile(
    r"\b(RUN 30|this run|the run|the window|the windows|the capture)\b[^.]{0,40}?"
    r"\b(was|were)\s+(executed|run|captured|observed|measured)\b"
    r"|\bthe run showed\b|\bwe (observed|measured)\b", re.I)


def section_v8():
    t = read(HW)
    i = t.index("\n## V8 — GBP-AUDIO-001")
    return t[i:]


# --------------------------------------------------------------- the vectors

def square(n_blocks, period, mark, high, low, phase=0):
    """A two-level square in per-block LEVELS: `period` blocks per cycle, the
    first `mark` fraction of each cycle high."""
    out = []
    for i in range(n_blocks):
        pos = ((i + phase) % period) / float(period)
        out.append(high if pos < mark else low)
    return out


def pwm_byte(level):
    """A byte whose 1 bits are contiguous and leading, carrying `level` (0-8)."""
    return (0xFF << (8 - level)) & 0xFF if level else 0x00


def pwm_block(level):
    """0x400 bytes repeated four times, as §V8.5 says PWM predicts."""
    quarter = bytes([pwm_byte(level)] * 1024)
    return quarter * 4


def pcm_block(level):
    """4096 distinct sample bytes — no mirroring. A ramp whose period divides
    1024 would mirror by accident and quietly pass PWM's mirroring check, so
    each 0x400 quarter is offset from the previous one."""
    return bytes([(level + (i // 1024) * 7 + (i & 0x03)) & 0xFF for i in range(4096)])


def byte0_block(value=0x01):
    """U-GBP-021's pattern: only byte 0 of each 32-byte line non-zero."""
    b = bytearray(4096)
    for i in range(0, 4096, 32):
        b[i] = value
    return bytes(b)


def blocks_from_levels(levels, model):
    if model == "PWM":
        return [pwm_block(int(round(lv))) for lv in levels]
    if model == "PCM":
        return [pcm_block(int(round(lv))) for lv in levels]
    raise ValueError(model)


def tone_window(model, press_index, n=None, period=None, high=8, low=0, phase=0):
    """One window of the 64 Hz phase at the press's predicted duty."""
    n = n or v8.BLOCKS_PER_WINDOW
    period = period or int(round(v8.period_blocks(v8.F_PHASE2_HZ)))
    mark = v8.expected_mark_fraction(press_index)
    hi = high if model == "PWM" else 200
    lo = low
    return blocks_from_levels(square(n, period, mark, hi, lo, phase), model)


def silence(model, n=64):
    if model == "PWM":
        return [pwm_block(4)] * n
    return [pcm_block(100)] * n


# ------------------------------------------------------------ the arithmetic

class TheArithmeticIsRecomputedAndTheDocumentAgreesWithIt(unittest.TestCase):

    def test_the_two_predicted_periods(self):
        self.assertAlmostEqual(v8.F_PHASE1_HZ, 154.5660, places=3)
        self.assertAlmostEqual(v8.F_PHASE2_HZ, 64.0, places=6)
        self.assertAlmostEqual(v8.period_blocks(v8.F_PHASE1_HZ), 26.49, places=2)
        self.assertAlmostEqual(v8.period_blocks(v8.F_PHASE2_HZ), 63.975, places=3)

    def test_the_envelope_and_the_decay(self):
        self.assertAlmostEqual(v8.ENVELOPE_STEP_S * 1000.0, 109.375, places=3)
        p = v8.window_plan()
        self.assertAlmostEqual(p["decay_blocks_per_press"], 6717.4, places=1)

    def test_the_window_the_document_states(self):
        p = v8.window_plan()
        self.assertEqual(p["blocks_per_window"], 256)
        self.assertEqual(p["windows_per_run"], 4)
        self.assertEqual(p["total_blocks"], 1024)
        self.assertEqual(p["total_bytes"], 4194304)
        self.assertAlmostEqual(p["window_ms"], 62.52, places=2)
        self.assertAlmostEqual(p["periods_phase2_per_window"], 4.00, places=2)
        self.assertAlmostEqual(p["worst_case_ms"], 45.78, places=2)
        self.assertAlmostEqual(p["worst_case_periods"], 2.93, places=2)
        self.assertAlmostEqual(p["envelope_steps_per_window"], 0.57, places=2)
        self.assertLess(p["kept_fraction"], 0.04)

    def test_the_document_carries_those_same_numbers(self):
        s = plain(section_v8())
        for wanted in ("256 = 62.52 ms = 4.00 full periods",
                       "62.52 - 16.74 = 45.78 ms = 2.93 periods",
                       "total blocks 1 024",
                       "total bytes 4 194 304 = 4.00 MB",
                       "0.57 of one envelope step",
                       "6 717 blocks of decay per press"):
            self.assertIn(wanted, s, "§V8 lost the arithmetic: %r" % wanted)

    def test_128_would_not_have_covered_a_whole_period(self):
        """The reason the assessment's 128 was corrected upward, recomputed."""
        covered = 128 * v8.BLOCK_MS - v8.GBA_FRAME_MS
        self.assertLess(covered / (1000.0 / v8.F_PHASE2_HZ), 1.0)
        self.assertIn("0.93 of a period", plain(section_v8()))


# ------------------------------------------------------- the model reductions

class EachModelRefusesTheOtherModelsBytes(unittest.TestCase):
    """A model that can absorb any block is not a model (§V3.19)."""

    def test_pwm_refuses_pcm_bytes(self):
        self.assertIsNone(v8.block_level(pcm_block(37), "PWM"))

    def test_byte0_refuses_a_dense_block(self):
        self.assertIsNone(v8.block_level(pwm_block(4), "BYTE0"))

    def test_pwm_accepts_its_own_and_reports_the_level(self):
        self.assertAlmostEqual(v8.block_level(pwm_block(6), "PWM"), 6.0)

    def test_mirroring_separates_pwm_from_pcm(self):
        self.assertTrue(v8.mirrored_x4(pwm_block(3)))
        self.assertFalse(v8.mirrored_x4(pcm_block(3)))

    def test_the_archives_sparse_pattern_is_the_byte0_model(self):
        self.assertTrue(v8.byte0_sparse(byte0_block()))
        self.assertIsNotNone(v8.block_level(byte0_block(), "BYTE0"))

    def test_an_unknown_model_name_raises(self):
        with self.assertRaises(ValueError):
            v8.block_level(pwm_block(1), "FM")


# --------------------------------------------------------- the two observables

class ThePeriodAndTheDuty(unittest.TestCase):

    def test_a_64_block_square_measures_64(self):
        levels = square(256, 64, 0.5, 8, 0)
        self.assertAlmostEqual(v8.alternation_period(levels), 64.0)

    def test_the_four_duties_are_recovered_at_the_tolerance(self):
        for i in range(4):
            levels = square(256, 64, v8.expected_mark_fraction(i), 8, 0)
            self.assertTrue(v8.mark_matches(v8.mark_fraction(levels),
                                            v8.expected_mark_fraction(i)),
                            "press %d: %.3f" % (i, v8.mark_fraction(levels)))

    def test_no_duty_matches_its_neighbours_prediction(self):
        """±0.06 cannot let one press's prediction match the next one's."""
        for i in range(4):
            levels = square(256, 64, v8.expected_mark_fraction(i), 8, 0)
            m = v8.mark_fraction(levels)
            for j in range(4):
                if j != i:
                    self.assertFalse(v8.mark_matches(m, v8.expected_mark_fraction(j)),
                                     "press %d matched press %d's prediction" % (i, j))

    def test_silence_has_no_period_and_no_duty(self):
        levels = [4.0] * 256
        self.assertEqual(v8.alternation_period(levels), v8.NOT_ESTIMATED)
        self.assertIsNone(v8.mark_fraction(levels))

    def test_two_edges_are_not_enough_for_a_period(self):
        """§V8.5.3: three rising edges, i.e. two whole intervals."""
        levels = square(160, 64, 0.5, 8, 0)      # two rising edges in 160 blocks
        self.assertEqual(v8.alternation_period(levels), v8.NOT_ESTIMATED)


# ------------------------------------------------------------ the transition

class TheTransition(unittest.TestCase):

    def test_it_is_found_when_both_phases_are_present(self):
        p1 = int(round(v8.period_blocks(v8.F_PHASE1_HZ)))
        p2 = int(round(v8.period_blocks(v8.F_PHASE2_HZ)))
        levels = square(4 * p1, p1, 0.5, 8, 0) + square(4 * p2, p2, 0.5, 8, 0)
        tr = v8.find_transition(levels)
        self.assertIsInstance(tr, dict)
        self.assertTrue(v8.period_matches(tr["period_before"], v8.period_blocks(v8.F_PHASE1_HZ)))
        self.assertTrue(v8.period_matches(tr["period_after"], v8.period_blocks(v8.F_PHASE2_HZ)))

    def test_a_window_that_missed_phase_1_reports_NOT_OBSERVED_not_absence(self):
        """§V8.3.1: the anchor does not remove the AGB-side latency."""
        p2 = int(round(v8.period_blocks(v8.F_PHASE2_HZ)))
        levels = square(6 * p2, p2, 0.5, 8, 0)
        self.assertEqual(v8.find_transition(levels), v8.NOT_OBSERVED)
        self.assertIn("not the same as", v8.NOT_OBSERVED)

    def test_the_transition_is_not_found_in_noise_at_one_period(self):
        levels = square(256, 40, 0.5, 8, 0)
        self.assertEqual(v8.find_transition(levels), v8.NOT_OBSERVED)


# ----------------------------------------------------------------- QUESTION AU

class QuestionAU(unittest.TestCase):

    def test_the_predicted_shape_on_four_presses(self):
        windows = [tone_window("PWM", i) for i in range(4)]
        r = v8.question_AU(windows, silence("PWM"))
        self.assertEqual(r["verdict"], "CARRIES / PREDICTED SHAPE")
        self.assertIn("PWM", r["models"])

    def test_pcm_is_distinguished_from_pwm_by_the_same_windows(self):
        windows = [tone_window("PCM", i) for i in range(4)]
        r = v8.question_AU(windows, silence("PCM"))
        self.assertEqual(r["verdict"], "CARRIES / PREDICTED SHAPE")
        self.assertEqual(r["models"], ["PCM"])
        self.assertFalse(any(w["models"]["PCM"]["mirrored_x4"] for w in r["per_window"]))

    def test_two_presses_are_enough_and_one_is_not(self):
        two = [tone_window("PWM", 0), tone_window("PWM", 1)]
        self.assertEqual(v8.question_AU(two, silence("PWM"))["verdict"],
                         "CARRIES / PREDICTED SHAPE")
        one = [tone_window("PWM", 0), None, None, None]
        self.assertEqual(v8.question_AU(one, silence("PWM"))["verdict"], "INCONCLUSIVE")

    def test_the_archives_sparse_pattern_is_DOES_NOT_CARRY(self):
        windows = [[byte0_block()] * v8.BLOCKS_PER_WINDOW for _ in range(4)]
        r = v8.question_AU(windows, [byte0_block()] * 64)
        self.assertEqual(r["verdict"], "DOES NOT CARRY")
        self.assertIn("REAL RESULT", r["why"])

    def test_something_that_is_not_the_prediction_is_a_real_result(self):
        """Windows that move with the press but at the wrong period: CARRIES /
        OTHER SHAPE, which is what would send the project to stimulus/agb-tone."""
        windows = [blocks_from_levels(square(256, 40, 0.5, 8, 0), "PWM") for _ in range(4)]
        r = v8.question_AU(windows, silence("PWM"))
        self.assertEqual(r["verdict"], "CARRIES / OTHER SHAPE")

    def test_one_window_differing_is_a_difference_and_not_a_repetition(self):
        """§V8.5.2 says the windows must REPEAT with the press. One that moves
        while the others do not is INCONCLUSIVE, never CARRIES."""
        flat = [pwm_block(4)] * v8.BLOCKS_PER_WINDOW
        windows = [blocks_from_levels(square(256, 40, 0.5, 8, 0), "PWM"), flat, flat, flat]
        r = v8.question_AU(windows, silence("PWM"))
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertIn("not a repetition", r["why"])

    def test_no_control_makes_the_positive_verdict_unavailable(self):
        """§V8.5.1 stated as a BUILD requirement, so it cannot be discovered
        after the run."""
        windows = [tone_window("PWM", i) for i in range(4)]
        r = v8.question_AU(windows, None)
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertIn("silent control", r["why"])

    def test_the_right_duty_at_the_wrong_press_does_not_match(self):
        """The duty is checked against THAT press's prediction, in press order."""
        windows = [tone_window("PWM", 3), tone_window("PWM", 2),
                   tone_window("PWM", 1), tone_window("PWM", 0)]
        r = v8.question_AU(windows, silence("PWM"))
        self.assertNotEqual(r["verdict"], "CARRIES / PREDICTED SHAPE")


# ----------------------------------------------------------------- QUESTION SP

class QuestionSPHasItsOwnGate(unittest.TestCase):

    def test_sp_wrong_does_not_touch_au(self):
        """§V8.4: separate gates. Windows with no phase 1 at all still answer AU."""
        windows = [tone_window("PWM", i) for i in range(4)]
        self.assertEqual(v8.question_SP(windows)["verdict"], v8.NOT_OBSERVED)
        self.assertEqual(v8.question_AU(windows, silence("PWM"))["verdict"],
                         "CARRIES / PREDICTED SHAPE")

    def test_sp_as_predicted_when_the_transition_is_in_the_window(self):
        p1 = int(round(v8.period_blocks(v8.F_PHASE1_HZ)))
        p2 = int(round(v8.period_blocks(v8.F_PHASE2_HZ)))
        levels = square(4 * p1, p1, 0.5, 8, 0) + square(4 * p2, p2, 0.5, 8, 0)
        windows = [blocks_from_levels(levels, "PWM"), None, None, None]
        self.assertEqual(v8.question_SP(windows)["verdict"], "AS PREDICTED")

    def test_sp_never_claims_the_stop_worked(self):
        r = v8.question_SP([tone_window("PWM", 0)])
        self.assertIn("NOT a finding that the stop worked", r["why"])


# ------------------------------------------------------- the refusals and gate

class TheRefusalsAreExecutableRatherThanRemembered(unittest.TestCase):

    def test_the_envelope_is_not_a_question_this_run_answers(self):
        r = v8.envelope_staircase([])
        self.assertEqual(r["verdict"], v8.NOT_READABLE)

    def test_identity_differing_on_the_day_means_do_not_run(self):
        d = {"sha256": "53c212c7", "size": "69348"}
        self.assertEqual(v8.identity_gate(d, d)["verdict"], "RE-DECLARED")
        self.assertEqual(v8.identity_gate(d, {"sha256": "other", "size": "69348"})["verdict"],
                         "DO NOT RUN")

    def test_an_unchecked_identity_is_not_a_failed_gate(self):
        r = v8.identity_gate({"sha256": "53c212c7"}, {})
        self.assertEqual(r["verdict"], "DECLARED, NOT CHECKED")


# ------------------------------------------ the pre-registration says its part

class ThePreRegistrationIsComplete(unittest.TestCase):

    def test_the_parts_the_issue_requires_are_present(self):
        s = plain(section_v8())
        for wanted in ("QUESTION AU", "QUESTION SP", "QUESTION T'",
                       "SEPARATE GATES", "PWM (Dolphin's model)", "BYTE-0 ONLY",
                       "THE ANCHOR", "THE LATENCY", "the budget",
                       "SOUNDCNT_H (0x04000082)", "captures/local/GBP-AUDIO-001",
                       "RUN 30 is the next free number", "DO NOT RUN",
                       "the pad's A", "stream-0016"):
            self.assertIn(wanted, s, "§V8 is missing %r" % wanted)

    def test_it_authorises_nothing_and_says_so(self):
        s = plain(section_v8())
        self.assertIn("NOT RUN, NOT AUTHORISED HERE", s)
        self.assertIn("It authorises no hardware and no build", s)

    def test_no_paragraph_claims_a_run_or_a_result(self):
        """A unit is a paragraph or a table row — never a clause split on
        punctuation (the Issue #33 defect)."""
        claims = CLAIMS
        for para in re.split(r"\n\s*\n", section_v8()):
            self.assertIsNone(claims.search(plain(para)),
                              "§V8 claims a result it cannot have:\n%s" % para[:200])

    def test_the_guard_bites(self):
        """The guard is worth nothing unless an offender is shown to trip it —
        and the offender must be the kind §V8 could plausibly grow."""
        for offender in ("RUN 30 was executed on 2026-09-30.",
                         "The windows were captured and the run showed the predicted shape.",
                         "We measured the mark fraction at 0.50."):
            self.assertIsNotNone(CLAIMS.search(plain(offender)), offender)
        self.assertIsNone(CLAIMS.search(plain(
            "Every AUDIO block this project has archived was captured with no Game Pak.")),
            "the guard must not fire on a statement about the EXISTING archive")

    def test_the_operator_checklist_separates_the_count_from_the_button(self):
        """The Operator's own correction: a count glued to a button name reads
        as a PlayStation button. Applied from this checklist onward."""
        rows = [l for l in section_v8().split("\n") if re.search(r"the pad's", l)]
        self.assertTrue(rows)
        for row in rows:
            self.assertIsNone(re.search(r"\b[A-Z]{1,6}\s?x\s?\d", row), row)
            self.assertIn("×", row)
            self.assertRegex(row, r"[A-Z]+\s+×\s+\d")

    def test_nothing_from_the_share_alike_source_is_carried(self):
        """CC BY-SA 4.0: §V8 describes behaviour and names registers; it must
        not carry the source's own lines."""
        s = section_v8()
        self.assertIn("nothing carried", plain(s))
        self.assertNotIn("#include", s)
        self.assertNotIn("REG_", s)


class TheReservedNamesAreReservedAndNothingMore(unittest.TestCase):
    """§V7.6.7: a reserved name is not evidence. It is reserved once, it is not
    cited anywhere else, and the file it names DOES NOT EXIST — nothing may be
    said about a run until the Operator's raw drop is in `logs/`."""

    NAMES = ("captures/local/GBP-AUDIO-001_stream-0016-run30.log",
             "captures/local/GBP-AUDIO-001_stream-0016-run30-audio.bin")

    def test_each_name_is_reserved_once_and_now_appears_in_its_result(self):
        """§V7.6.7's shape: a name is RESERVED once, and once the run exists it
        appears a second time in the run's own record and nowhere else."""
        t = read(HW)
        for n in self.NAMES:
            self.assertEqual(t.count(n), 2,
                             "%s should appear exactly twice: its reservation (§V8.9) and its result (§V8.13)" % n)
            self.assertLess(t.index("### V8.9 "), t.index(n), n)

    def test_the_names_are_the_ones_the_run_landed_under(self):
        """EXPIRED AND MOVED 2026-09-22 (Issue #62). These two cases asserted that
        RUN 30 had not happened; it has. A guard whose condition has been
        overtaken is not deleted -- it becomes the guard for what replaced it,
        which here is that the archived copies are under §V8.9's RESERVED names
        and carry the hashes the ingestion recorded. captures/local is ignored by
        git, so a clone legitimately has neither."""
        import hashlib
        want = {self.NAMES[0]: "%s" % LOG_SHA, self.NAMES[1]: "%s" % BIN_SHA}
        present = [n for n in self.NAMES if os.path.exists(os.path.join(ROOT, n))]
        if not present:
            self.skipTest("RUN 30's archived copies are not in this checkout (captures/local is ignored)")
        self.assertEqual(sorted(present), sorted(self.NAMES), "one of the two archived copies is missing")
        for n in self.NAMES:
            with open(os.path.join(ROOT, n), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), want[n], n)

    def test_the_operators_raw_drop_is_untouched(self):
        """logs/ is the Operator's, never edited and never versioned: the archived
        copy must be byte-identical to it."""
        import hashlib
        raw = {os.path.join(ROOT, "logs", "run30", "GBP-AUDIO-001_stream-0016.log"): LOG_SHA,
               os.path.join(ROOT, "logs", "run30", "GBP-AUDIO-001_stream-0016-audio.bin"): BIN_SHA}
        if not all(os.path.exists(f) for f in raw):
            self.skipTest("the raw drop is not in this checkout (logs/ is ignored)")
        for f, want in raw.items():
            with open(f, "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), want, f)

    def test_the_handoff_carries_the_reservation_and_not_a_result(self):
        h = read(os.path.join(ROOT, "docs", "HANDOFF.md"))
        self.assertIn("captures/local/GBP-AUDIO-001_stream-0016-run30", h)
        self.assertIn("NOT RUN", h)
        self.assertIsNone(CLAIMS.search(plain(
            h[h.index("issue 58"):h.index("forbidden   frozen analyzers")])))


class UGBP012IsPointedAtAndNotAnswered(unittest.TestCase):

    def test_the_heading_points_at_V8_and_keeps_the_item_open(self):
        t = read(UNK)
        i = t.index("## U-GBP-012 ")
        head = plain(t[i:t.index("\n", i)])
        self.assertIn("STILL OPEN", head)
        self.assertIn("HARDWARE_TESTS.md §V8", head)
        self.assertIn("NOT RUN, NOT AUTHORISED", head)
        self.assertIn("a pre-registration answers nothing", head)

    def test_the_body_does_not_answer_it(self):
        t = read(UNK)
        i = t.index("## U-GBP-012 ")
        body = plain(t[i:t.index("\n## U-GBP-013", i)])
        self.assertIn("this item is not answered by the pre-registration", body)
        for forbidden in ("the AUDIO block format is", "U-GBP-012 CLOSED", "is PWM", "is PCM"):
            self.assertNotIn(forbidden, body)


if __name__ == "__main__":
    unittest.main()
