"""tests/host/test_v14repeat.py — §V14, RUN 34: §V11's amplitude sweep repeated.

Three jobs. `tools/v14repeat.py` must reproduce §V11.16.7's published figures on
RUN 32 exactly, so that the method frozen for RUN 34 is the one already used and
not a new one. §V14's two findings must hold against the code rather than only
in prose. And §V14 must stay a pre-registration that adds no gate.
"""
import math
import os
import re
import subprocess
import sys
import unittest

import frozen  # noqa: E402  (tests/host is on the path)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v11sweep  # noqa: E402
import v13sep  # noqa: E402
import v14repeat as r  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
LOCAL = os.path.join(ROOT, "captures", "local")
RUN31 = os.path.join(LOCAL, "GBP-AUDIO-002_stream-0016-run31-audio.bin")
RUN32 = os.path.join(LOCAL, "GBP-AUDIO-003_stream-0016-run32-audio.bin")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s.replace("\n> ", " ")).replace("`", "").replace("**", "").replace("*", "")


def part():
    t = read(HW)
    i = t.index("\n## V14 ")
    j = t.find("\n## V", i + 1)
    return (t[i:j] if j >= 0 else t[i:]).lstrip("\n")


class TheMethodIsTheOneAlreadyUsed(unittest.TestCase):
    """If the frozen method did not reproduce §V11.16.7 exactly, RUN 34 would be
    measured with a different ruler from RUN 32 and the repeat would mean
    nothing."""

    def load(self):
        if not (os.path.exists(RUN31) and os.path.exists(RUN32)):
            self.skipTest("both runs are needed and are not both archived here")
        import awinparse
        return awinparse.load(RUN31)[3], awinparse.load(RUN32)[3]

    def test_it_reproduces_the_three_published_deviations(self):
        w31, w32 = self.load()
        self.assertAlmostEqual(r.deviation(w31[3]) * 256, 30.0625, places=4)
        self.assertAlmostEqual(r.deviation(w32[3]) * 256, 14.0547, places=4)
        self.assertAlmostEqual(r.deviation(w32[4]) * 256, 6.0547, places=4)
        self.assertIsNone(r.deviation(w32[1]))
        self.assertIsNone(r.deviation(w32[2]))

    def test_it_reproduces_the_fit_and_the_model_ratio(self):
        w31, w32 = self.load()
        pts = [(15, r.deviation(w31[3]) * 256), (7, r.deviation(w32[3]) * 256),
               (3, r.deviation(w32[4]) * 256)]
        slope, icpt = r.fit(pts)
        self.assertAlmostEqual(slope, 2.0007, places=4)
        self.assertAlmostEqual(icpt, 0.0515, places=4)
        e = r.model_errors([(15, r.deviation(w31[3])), (7, r.deviation(w32[3])),
                            (3, r.deviation(w32[4]))])
        self.assertAlmostEqual(e["compressive"] / e["linear"], 258, delta=1)

    def test_the_anchor_constant_is_the_measured_value(self):
        self.assertAlmostEqual(r.ANCHOR_V15 * 256, 30.0625, places=6)

    def test_the_module_contains_no_gate(self):
        src = read(os.path.join(ROOT, "tools", "v14repeat.py"))
        self.assertNotIn("verdict", src.split('"""', 2)[2])     # not in the code
        self.assertNotIn("def question", src)
        self.assertIn("THIS MODULE CONTAINS NO GATE", src)

    def test_the_module_is_not_edited_after_its_commit(self):
        then = frozen.source("RUN 34 pre-registered", "tools/v14repeat.py")   # Issue #83 (F): pinned by HASH; the phrase is checked, not searched
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v14repeat.py")))


class FindingOneWindowOneIsAlwaysDead(unittest.TestCase):

    def test_the_emitting_window_is_dead_under_BOTH_readings(self):
        # ORDINAL: the emitting window is dead by definition
        self.assertFalse(v13sep.predict_ordinal(4)[0])
        # ELAPSED: dead for every T the bound still allows, because T > one window
        self.assertGreater(v13sep.T_LOWER, 0.0)
        for t in (v13sep.T_LOWER + 1e-9, 1.0, v13sep.T_UPPER):
            self.assertFalse(v13sep.predict_elapsed([0.0], t)[0])

    def test_so_question_V_cannot_pass_on_a_four_press_run(self):
        """question_V needs four carrying windows; with window 1 dead it must say
        INCONCLUSIVE. Demonstrated on synthetic windows rather than argued."""
        def block(d):
            n = int(round(d * 4096)); return [0xFC] * n + [0x03] * (4096 - n)

        def window(dev, carry=True):
            out = []
            for i in range(256):
                if not carry or i < v11sweep.ONSET_SLICE_BLOCKS:
                    out.append(block(0.5))
                else:
                    ph = ((i - v11sweep.ONSET_SLICE_BLOCKS) % 32) / 32.0
                    out.append(block(0.5 + (dev if ph < 0.5 else -dev)))
            return out
        wins = [window(0.0, carry=False)] + [window(v11sweep.deviation_linear(v))
                                              for v in v11sweep.AMPLITUDES[1:]]
        res = v11sweep.question_V(wins, [v11sweep.KEY_B] * 4)
        self.assertEqual(res["verdict"], "INCONCLUSIVE")
        self.assertIn("[1]", res["why"])

    def test_the_lost_window_is_the_one_already_measured(self):
        self.assertEqual(v11sweep.AMPLITUDES[0], 15)
        self.assertEqual(v11sweep.ANCHOR_VOLUME, 15)
        s = plain(part())
        self.assertIn("the window RUN 34 loses is envelope volume 15, which RUN 31 has already measured twice", s)
        self.assertIn("It is not a defect in the gate", s.replace("That is not a defect in the gate", "It is not a defect in the gate"))

    def test_the_mixed_axis_trick_is_closed_by_the_ROMs_own_guard(self):
        rom = read(os.path.join(ROOT, "stimulus", "agb-sweep", "source", "main.c"))
        self.assertIn("if (s->axis == (u8)SWEEP_AXIS_F) { s->spoiled = 1u; return 1; }", rom)
        self.assertIn("The guard that makes the display trustworthy is the same guard that forbids the trick",
                      plain(part()))

    def test_the_fifth_window_that_would_fix_it_is_named_and_not_proposed(self):
        h = read(os.path.join(ROOT, "src", "gbp", "gbp_awin.h"))
        self.assertIn("#define GBP_AWIN_PRESS_WINDOWS  4u", h)
        s = plain(part())
        self.assertIn("a capture with a fifth press window", s)
        self.assertIn("Not proposed here", s)


class FindingTwoThreeSecondsIsNoLongerSafe(unittest.TestCase):

    def test_three_seconds_is_inside_the_bound_and_five_clears_it(self):
        w = v13sep.WINDOW_SECONDS
        self.assertLess(3.0 + w, v13sep.T_UPPER)          # 3 s: window 2 may still be dead
        self.assertGreater(5.0 + w, v13sep.T_UPPER)       # 5 s: safe under either reading
        self.assertAlmostEqual(5.0 + w - v13sep.T_UPPER, 1.7325, places=3)
        s = part()
        self.assertIn("RUN 34 spaces its presses at least FIVE seconds apart", s)
        self.assertIn("AT LEAST FIVE SECONDS BETWEEN THEM", s)

    def test_it_does_not_depend_on_RUN_33(self):
        self.assertIn("It does not depend on RUN 33's outcome", plain(part()))

    def test_the_budget_holds(self):
        self.assertLessEqual(20 + 3 * 5, 120)
        self.assertIn("35 s, inside the 120 s safety budget", plain(part()))


class ThePredictionsAndTheHonestShortfall(unittest.TestCase):

    def test_V11_separates_by_4_90_on_the_measured_anchor(self):
        a = r.ANCHOR_V15
        lin = v11sweep.deviation_linear(11, anchor=a) * 256
        comp = v11sweep.deviation_compressive(11, anchor=a) * 256
        self.assertAlmostEqual(lin, 22.05, places=2)
        self.assertAlmostEqual(comp, 26.94, places=2)
        self.assertAlmostEqual(comp - lin, 4.90, places=2)
        self.assertLess(comp - lin, 5.0)          # the §V11.4 claim does NOT hold here
        s = plain(part())
        self.assertIn("Re-anchored on the measured value, V=11 separates by 4.90", s)
        self.assertIn("§V11.4 keeps its words", s)

    def test_the_scaling_is_the_anchor_ratio(self):
        self.assertAlmostEqual(30.0625 / 32.0, 0.939, places=3)
        self.assertAlmostEqual(5.21 * 30.0625 / 32.0, 4.90, delta=0.01)

    def test_no_tolerance_is_invented_for_the_repeat(self):
        s = plain(part())
        self.assertIn("No tolerance is set on the repeat", s)
        self.assertAlmostEqual(r.repeat_delta(14.0 / 256, 14.5 / 256), 0.5, places=9)


class ItIsAPreRegistrationThatAddsNoGate(unittest.TestCase):

    def test_the_heading_says_not_run_not_authorised(self):
        h = part().split("\n", 1)[0]
        self.assertIn("NOT RUN, NOT AUTHORISED HERE", h)
        self.assertIn("PRE-REGISTERED", h)
        self.assertIn("under §V11's existing gates", h)

    def test_the_names_come_from_the_image_and_33_34_share_a_card(self):
        s = part()
        self.assertIn("sd:/open-gbp/GBP-AUDIO-001_stream-0016.log", s)
        self.assertIn("captures/local/GBP-AUDIO-003_stream-0016-run34.log", s)
        self.assertIn("RUN 33's TWO FILES MUST COME OFF", s)
        self.assertIn("THE CARD BEFORE THE SECOND BOOT", s)
        self.assertIn('"sd:/open-gbp/%s_%s.log", test_id, build_id',
                      read(os.path.join(ROOT, "src", "platform", "sdlog.c")))

    def test_no_flash_no_staging(self):
        s = plain(part())
        self.assertIn("ALREADY FLASHED. NO NEW FLASH", s)
        self.assertIn("REUSED UNCHANGED. NO NEW STAGING", s)

    def test_the_action_list_uses_the_notation(self):
        s = part()
        self.assertRegex(s, r"\bB  × 1\b")
        self.assertIsNone(re.search(r"\b[A-Z]{1,6}\s?x\s?\d", s))

    def test_it_mints_no_id_and_promotes_nothing(self):
        self.assertIsNone(re.search(r"^#{2,4} +GBP-[A-Z]+-\d{3}\b", part(), re.M))
        ev = read(EV)
        self.assertEqual(max(int(n) for n in re.findall(
            r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 321)   # 318: Issue #90 (RUN 36 ingested, the output path heard: §V21.9)   # 319…321: Issue #91 (RUN 37 ingested: D1, D2, QUESTION A; §V19.14)
        s = plain(part())
        self.assertIn("H-PWM stays a hypothesis whatever RUN 34 shows", s)

    def test_nothing_beyond_the_reservation_is_claimed(self):
        s = part()
        self.assertNotIn("RUN 35", s)
        self.assertIn("RUN 34 is reserved and the files do not exist", plain(s))


if __name__ == "__main__":
    unittest.main()
