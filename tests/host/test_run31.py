"""
tests/host/test_run31.py — GitHub Issue #67: RUN 31 ingested, every figure
RECOMPUTED from the archived bytes rather than quoted from §V9.15.

THE TEST THAT MATTERS MOST is that `tools/v9tone.py` is byte-identical to the
commit that introduced it. This is the run where the frozen construction
**decided against us** — `RATIO DOES NOT HOLD` — and a construction that can be
edited after a disappointing result was never a construction at all.

THE SECOND MOST IMPORTANT is the separation of two things that are easy to
merge: §V9's VERDICT (the within-block period, which did not follow the note)
and the MEASUREMENT reported beside it (the across-block modulation, which did).
The first is a gate; the second is not, and one of its two windows needed a
slice chosen after seeing the data. The tests keep them apart.

captures/local and logs/ are ignored by design, so a clone has neither and the
recomputations skip; the source-level pins do not.
"""
import hashlib
import os
import re
import subprocess
import sys
import unittest

import frozen  # noqa: E402  (tests/host is on the path)
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

LOCAL = os.path.join(ROOT, "captures", "local")
LOG = os.path.join(LOCAL, "GBP-AUDIO-002_stream-0016-run31.log")
BIN = os.path.join(LOCAL, "GBP-AUDIO-002_stream-0016-run31-audio.bin")
RAW = os.path.join(ROOT, "logs", "run31")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")

LOG_SHA = "487c0c4935cbb33483f47eb76aa899c7b17ada6b819e557673ac0add57975bc7"
BIN_SHA = "8ff09d34006a485d2adaf96d5e008d25a9b27735c717b964940c2c2133cd2e07"
BLOCK_MS = 1000.0 / 4094.4


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def part():
    t = read(HW)
    return t[t.index("### V9.15 RUN 31"):]


def capture():
    import awinparse
    return awinparse.load(BIN)


def duty(b):
    lo, hi = min(b), max(b)
    mid = (lo + hi) / 2.0
    return sum(1 for x in b if x > mid) / len(b)


class TheConstructionDecidedAgainstUsAndWasNotEdited(unittest.TestCase):

    def test_v9tone_is_byte_identical_to_the_commit_that_wrote_it(self):
        then = frozen.source("Issue #64 -- agb-tone designed and pre-registered", "tools/v9tone.py")   # Issue #83 (F): pinned by HASH; the phrase is checked, not searched
        self.assertEqual(read(os.path.join(ROOT, "tools", "v9tone.py")), then,
                         "tools/v9tone.py was edited after its prediction failed")

    def test_the_record_says_which_outing_this_is(self):
        s = plain(part())
        self.assertIn("the first where it decides against us", s)


class TheRawsAndTheNamingDefect(unittest.TestCase):

    def test_the_hashes(self):
        if not (os.path.exists(LOG) and os.path.exists(BIN)):
            self.skipTest("RUN 31 is not archived in this checkout (captures/local is ignored)")
        with open(LOG, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), LOG_SHA)
        with open(BIN, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), BIN_SHA)
        self.assertEqual(os.path.getsize(BIN), 5243788)

    def test_the_console_wrote_RUN_30s_filenames_and_the_archive_does_not(self):
        """The defect itself, checked rather than described."""
        if not os.path.isdir(RAW):
            self.skipTest("the raw drop is not in this checkout (logs/ is ignored)")
        names = sorted(os.listdir(RAW))
        self.assertEqual(names, ["GBP-AUDIO-001_stream-0016-audio.bin",
                                 "GBP-AUDIO-001_stream-0016.log"],
                         "the console names the run after the IMAGE's TEST_ID")
        run30 = sorted(n for n in os.listdir(os.path.join(ROOT, "logs", "run30"))) \
            if os.path.isdir(os.path.join(ROOT, "logs", "run30")) else names
        self.assertEqual(names, run30, "RUN 31 wrote the same filenames RUN 30 wrote")
        # and the archived copies DO distinguish them
        self.assertTrue(os.path.exists(BIN))
        self.assertTrue(os.path.exists(os.path.join(LOCAL, "GBP-AUDIO-001_stream-0016-run30-audio.bin")))

    def test_the_archive_name_and_the_files_own_test_id_disagree_and_that_is_recorded(self):
        if not os.path.exists(LOG):
            self.skipTest("RUN 31 is not archived in this checkout")
        self.assertIn("test_id=GBP-AUDIO-001", read(LOG))
        self.assertIn("GBP-AUDIO-002", os.path.basename(LOG))
        s = plain(part())
        self.assertIn("THE CONSOLE WROTE GBP-AUDIO-001, NOT GBP-AUDIO-002", s)
        self.assertIn("that is correct rather than an error", s)
        self.assertIn("reusing an image across experiments means THE CONSOLE'S FILENAMES NO LONGER "
                      "IDENTIFY THE EXPERIMENT", s)


class TheRunIsAdmissibleAndTheCrossCheckAgreed(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(BIN):
            self.skipTest("RUN 31's sidecar is not in this checkout")
        self.data, self.h, self.anchors, self.wins = capture()

    def test_the_capture(self):
        self.assertEqual((self.h["windows_n"], self.h["windows_closed"], self.h["blocks_stored"]), (5, 5, 1280))
        self.assertEqual((self.h["blocks_failed"], self.h["arm_refused_busy"], self.h["arm_refused_full"]), (0, 0, 0))
        for a in self.anchors:
            self.assertEqual((a["blocks"], a["skipped"], a["flags"]), (256, 0, 1))

    def test_four_presses_four_windows(self):
        t = read(LOG)
        m = re.search(r"AWIN .*presses=(\d+) releases=(\d+)", t)
        self.assertEqual((int(m.group(1)), int(m.group(2))), (4, 4))
        self.assertEqual([a["event_n"] for a in self.anchors], [0, 2, 4, 6, 8])

    def test_the_operators_count_and_the_machines_agree(self):
        s = plain(part())
        self.assertIn("four by his count and four by the machine's", s.lower())
        self.assertIn("apareceu as cores Vermelho, verde, azul e saiu no quarto aperto", s)
        self.assertIn("RAN AND AGREED", s)


class QuestionCWithTheApuProvablyOff(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(BIN):
            self.skipTest("RUN 31's sidecar is not in this checkout")
        _, _, _, self.wins = capture()

    def test_the_control_is_the_same_256_byte_square_on_a_different_cartridge(self):
        import v9tone as v9
        c = self.wins[0]
        vals = set()
        for b in c:
            vals.update(b)
        self.assertEqual(sorted(vals), [0x00, 0x03, 0x07, 0xFC, 0xFF])
        for b in c:
            r = v9.window_period(list(b))
            self.assertEqual(r["period"], 256)
            self.assertEqual(r["uniformity"], 1.0)
            self.assertAlmostEqual(duty(b), 0.5)
        self.assertEqual(v9.question_C([x for b in c for x in b])["verdict"], "SAME SHAPE")

    def test_the_transition_bytes_differ_from_run30s_and_that_is_recorded(self):
        run30 = os.path.join(LOCAL, "GBP-AUDIO-001_stream-0016-run30-audio.bin")
        if not os.path.exists(run30):
            self.skipTest("RUN 30 is not archived in this checkout")
        import awinparse
        _, _, _, w30 = awinparse.load(run30)
        v30 = set()
        for b in w30[0]:
            v30.update(b)
        self.assertEqual(sorted(v30), [0x00, 0x01, 0xFE, 0xFF])
        s = plain(part())
        self.assertIn("{01, FE} in RUN 30, {03, 07, FC} here", s)

    def test_the_rom_guarantees_the_silence(self):
        rom = read(os.path.join(ROOT, "stimulus", "agb-tone", "source", "main.c"))
        self.assertIn("apu_silence", rom)
        self.assertIn("SILENT UNTIL THE FIRST PRESS", rom)
        s = plain(part())
        self.assertIn("the APU is PROVABLY OFF", s)


class QuestionRIsTheVerdictAndTheOtherThingIsNot(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(BIN):
            self.skipTest("RUN 31's sidecar is not in this checkout")
        _, _, _, self.wins = capture()

    def test_the_within_block_period_is_256_everywhere(self):
        import v9tone as v9
        n = 0
        for w in self.wins:
            for b in w:
                r = v9.window_period(list(b))
                self.assertEqual(r["period"], 256)
                n += 1
        self.assertEqual(n, 1280)

    def test_the_frozen_question_returns_RATIO_DOES_NOT_HOLD(self):
        import v9tone as v9
        w = [{"press": i, "note": "F1" if i % 2 else "F2",
              "levels": [x for b in self.wins[i] for x in b]} for i in (1, 2, 3, 4)]
        r = v9.question_R(w)
        self.assertEqual(r["verdict"], "RATIO DOES NOT HOLD")
        self.assertAlmostEqual(r["ratio"], 1.0)
        self.assertIn("A REAL RESULT, not a failed run", r["why"])
        self.assertIn("RATIO DOES NOT HOLD", plain(part()))

    def test_the_across_block_modulation_carries_the_notes(self):
        """The MEASUREMENT beside the verdict — and the slice that was chosen
        after the fact is made explicit here too."""
        import v9tone as v9
        s3 = [duty(b) for b in self.wins[3]]
        s4 = [duty(b) for b in self.wins[4]]
        onset = next(i for i, x in enumerate(s3) if abs(x - 0.5) > 0.01)
        self.assertEqual(onset, 44)
        r3 = v9.window_period(s3[onset:])
        r4 = v9.window_period(s4)
        self.assertEqual(r3["period"], 32)
        self.assertEqual(r3["uniformity"], 1.0)
        self.assertEqual(r4["period"], 8)
        self.assertGreaterEqual(r4["uniformity"], 0.9)
        self.assertAlmostEqual(r3["period"] / r4["period"], 4.0)
        # as frequencies, against what the ROM asked for
        self.assertAlmostEqual(1000.0 / (r3["period"] * BLOCK_MS), 128.0, delta=0.2)
        self.assertAlmostEqual(1000.0 / (r4["period"] * BLOCK_MS), 512.0, delta=0.5)
        # and each window recovers the same drain rate independently
        self.assertAlmostEqual(128.0 * r3["period"], 4096.0, places=1)
        self.assertAlmostEqual(512.0 * r4["period"], 4096.0, places=1)
        # w1 and w2 carry no modulation at all
        for i in (1, 2):
            self.assertEqual(v9.window_period([duty(b) for b in self.wins[i]])["period"], v9.PERIOD_ABSENT)

    def test_the_record_keeps_the_measurement_and_the_verdict_apart(self):
        s = plain(part())
        self.assertIn("This is a MEASUREMENT reported beside the verdict, NOT a gate that was passed", s)
        self.assertIn("That slice was chosen after seeing the data", s)
        self.assertIn("is why this is a measurement and not a verdict", s)


class TheDelayIsBoundedByTwoRuns(unittest.TestCase):

    def _run(self, path, logname):
        import awinparse
        if not os.path.exists(path):
            return None
        data, h, anchors, wins = awinparse.load(path)
        t = read(logname)
        tc = int(re.search(r"t_control=([0-9a-f]+)", t).group(1), 16)
        ctrl = set()
        for b in wins[0]:
            ctrl.update(b)
        out = []
        for a in anchors:
            w = wins[a["index"]]
            k = next((j for j, b in enumerate(w) if not set(b) <= ctrl), None)
            out.append(((a["t_arm"] - tc) / h["tb_hz"], k))
        return out

    def test_the_bound_the_record_states_is_the_bound_the_logs_give(self):
        r31 = self._run(BIN, LOG)
        r30 = self._run(os.path.join(LOCAL, "GBP-AUDIO-001_stream-0016-run30-audio.bin"),
                        os.path.join(LOCAL, "GBP-AUDIO-001_stream-0016-run30.log"))
        if not (r31 and r30):
            self.skipTest("both runs are needed and are not both archived here")
        silent = [t for t, k in r30[1:] + r31[1:] if k is None]
        carried = [t for t, k in r30[1:] + r31[1:] if k is not None]
        self.assertTrue(silent and carried)
        self.assertLess(max(silent), min(carried), "the two classes must not interleave")
        self.assertAlmostEqual(max(silent), 10.045, places=2)
        self.assertAlmostEqual(min(carried), 12.547, places=2)
        # the record states the same bound in its own words
        s = plain(part())
        self.assertIn("BETWEEN 10.045 s AND 12.547 s AFTER THE CONTROL TRANSFORM", s)

    def test_u_gbp_038_is_answered_and_039_opened(self):
        u = read(UNK)
        h38 = [l for l in u.splitlines() if l.startswith("## U-GBP-038")][0]
        self.assertIn("ANSWERED AND CLOSED", h38)
        self.assertIn("it was EARLY", h38)
        self.assertIn("## U-GBP-039 (P2", u)
        u39 = u[u.index("## U-GBP-039"):]
        self.assertIn("CANDIDATES, none measured", u39)
        self.assertIn("WHAT WOULD NARROW IT CHEAPLY", u39)

    def test_u_gbp_037_moved_rather_than_closed(self):
        u = read(UNK)
        h37 = [l for l in u.splitlines() if l.startswith("## U-GBP-037")][0]
        self.assertIn("P1 → P3", h37)
        self.assertIn("stays OPEN", h37)
        body = u[u.index("## U-GBP-037"):u.index("## U-GBP-038")]
        self.assertIn("Why it does not CLOSE", body)
        self.assertIn("a THIRD frequency", body)


if __name__ == "__main__":
    unittest.main()


class TheRateIsDolphinsAndTheLayoutIsNot(unittest.TestCase):
    """Issue #67's validation: the model has two parts and they got different
    answers. "Dolphin was wrong" is the reading this class exists to prevent."""

    def test_the_rate_the_two_windows_give_is_dolphins_own_number(self):
        if not os.path.exists(BIN):
            self.skipTest("RUN 31's sidecar is not in this checkout")
        import v9tone as v9
        _, _, _, wins = capture()
        s3 = [duty(b) for b in wins[3]]
        onset = next(i for i, x in enumerate(s3) if abs(x - 0.5) > 0.01)
        p3 = v9.window_period(s3[onset:])["period"]
        p4 = v9.window_period([duty(b) for b in wins[4]])["period"]
        # one block = one sample: the rate follows from f x period, from each window alone
        self.assertAlmostEqual(128.0 * p3, 4096.0, places=1)
        self.assertAlmostEqual(512.0 * p4, 4096.0, places=1)
        # and that is the number GBP-AUD-001 records for Dolphin's model
        self.assertIn("produced at 4096 Hz", read(EVIDENCE))

    def test_the_amendment_splits_the_rate_from_the_layout(self):
        ev = read(EVIDENCE)
        i = ev.index("## GBP-AUD-001")
        entry = plain(ev[i:ev.index("## GBP-SIO-001")])
        self.assertIn("the model has TWO parts and RUN 31 answers them DIFFERENTLY", entry)
        self.assertIn('Do not read "Dolphin was wrong"', entry)
        self.assertIn("CORROBORATED BY HARDWARE TO FOUR FIGURES", entry)
        self.assertIn("REFUSED, and that is the half U-GBP-012 still carries", entry)

    def test_u_gbp_012_carries_the_open_half_and_labels_the_hypothesis(self):
        u = read(UNK)
        body = u[u.index("## U-GBP-012"):u.index("## U-GBP-013")]
        self.assertIn("THE RATE -- ANSWERED", body)
        self.assertIn("THE BYTE LAYOUT -- STILL OPEN", body)
        self.assertIn("A HYPOTHESIS, labelled as one and NOT promoted by this run", body)
        self.assertIn("sweeps AMPLITUDE rather than frequency", body)
        self.assertIn("three values are not a curve", body)


class TheCheapestProbeWasRunAndIsNegative(unittest.TestCase):

    def test_the_four_epochs_are_confounded_in_these_logs(self):
        """GBP-HW-302, recomputed: the probe's own result."""
        import awinparse
        out = {}
        for tag, b, l in (("run30", os.path.join(LOCAL, "GBP-AUDIO-001_stream-0016-run30-audio.bin"),
                           os.path.join(LOCAL, "GBP-AUDIO-001_stream-0016-run30.log")),
                          ("run31", BIN, LOG)):
            if not (os.path.exists(b) and os.path.exists(l)):
                self.skipTest("both runs are needed and are not both archived here")
            data, h, anchors, wins = awinparse.load(b)
            txt = read(l)
            ep = {k: int(re.search(r"%s=([0-9a-f]+)" % k, txt).group(1), 16)
                  for k in ("t_program", "t_probe_enter", "t_control", "t_capture_start")}
            out[tag] = (h["tb_hz"], ep, anchors, wins)
        for tag, (tb, ep, anchors, wins) in out.items():
            spread = (max(ep.values()) - min(ep.values())) / tb
            self.assertLess(spread, 0.163 + 1e-3, "%s: the epochs must be within 163 ms" % tag)
        # the bound against each epoch, and every one of them is ~2.5 s wide
        for epoch in ("t_program", "t_probe_enter", "t_control", "t_capture_start"):
            silent, carried = [], []
            for tag, (tb, ep, anchors, wins) in out.items():
                ctrl = set()
                for x in wins[0]:
                    ctrl.update(x)
                for a in anchors[1:]:
                    w = wins[a["index"]]
                    k = next((j for j, x in enumerate(w) if not set(x) <= ctrl), None)
                    (carried if k is not None else silent).append((a["t_arm"] - ep[epoch]) / tb)
            self.assertLess(max(silent), min(carried), epoch)
            self.assertGreater(min(carried) - max(silent), 2.0, epoch)

    def test_the_record_says_the_probe_is_exhausted_and_what_separates_them(self):
        u = read(UNK)
        body = plain(u[u.index("## U-GBP-039"):])
        self.assertIn("THE CHEAPEST PROBE HAS BEEN RUN, and it is a NEGATIVE result", body)
        self.assertIn("All four epochs are within 163 ms of each other", body)
        self.assertIn("The cheap probe is exhausted", body)
        self.assertIn("prehandler_wait_ms", body)
        self.assertIn("It costs a rebuild with an existing option and no new code", body)
        # and that option really exists, checked against the source rather than the prose
        self.assertIn("prehandler_wait_ms", read(os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.h")))
