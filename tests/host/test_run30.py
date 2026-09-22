"""
tests/host/test_run30.py — GitHub Issue #62: RUN 30 ingested, with every figure
RECOMPUTED from the archived bytes rather than quoted from §V8.13.

WHAT THIS FILE IS FOR. A record that says "the control window carries a square
of 256-byte period" is worth what its derivation is worth, so the derivation
lives here and runs on every suite. The document is then checked against THIS,
not the other way round.

THE ONE TEST THAT MATTERS MOST is that `tools/v8audio.py` is byte-identical to
the commit that introduced it, before this image existed and before any log did
(Issue #50). Everything else in this file could be rewritten after seeing the
data; that file could not, and the guard says so loudly.

captures/local is ignored by git, so a clone legitimately has neither the raws
nor the sidecar and the recomputations skip. The source-level pins do not.
"""
import hashlib
import os
import re
import subprocess
import sys
import unittest
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

LOCAL = os.path.join(ROOT, "captures", "local")
LOG = os.path.join(LOCAL, "GBP-AUDIO-001_stream-0016-run30.log")
BIN = os.path.join(LOCAL, "GBP-AUDIO-001_stream-0016-run30-audio.bin")
RAW_LOG = os.path.join(ROOT, "logs", "run30", "GBP-AUDIO-001_stream-0016.log")
RAW_BIN = os.path.join(ROOT, "logs", "run30", "GBP-AUDIO-001_stream-0016-audio.bin")
REF17 = os.path.join(LOCAL, "GBP-VIDEO-004_stream-0015-run17.log")
HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EVIDENCE = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")

LOG_SHA = "3d1830eb62939807756778c33e5f6bedac0dc609bb7ce1fa4900c662dbbc2c77"
BIN_SHA = "b3597b72adeae0cb8627e5c1b00584ca8a30bb2ff592c4b645e98cd9428ac564"
HEADER_CRC = 0x7491C1E7
TOTAL_CRC = 0x73A74A49


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def v8_part():
    t = read(HW)
    return t[t.index("### V8.13 "):]


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def capture():
    import awinparse
    return awinparse.load(BIN)


def edges(b):
    lo, hi = min(b), max(b)
    if hi - lo < 8:
        return []
    mid = (lo + hi) / 2.0
    h = [x > mid for x in b]
    return [i for i in range(1, len(h)) if h[i] and not h[i - 1]]


class TheConstructionsWereNotAdjustedToTheData(unittest.TestCase):
    """Issue #50's whole purpose, and the moment it was built for."""

    def test_v8audio_is_byte_identical_to_the_commit_that_wrote_it(self):
        base = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "-1", "--grep",
                               "Issue #58 -- the three models in code before the build exists"],
                              capture_output=True, text=True).stdout.strip()
        if not base:
            self.skipTest("the commit that introduced tools/v8audio.py is not in this checkout")
        then = subprocess.run(["git", "-C", ROOT, "show", "%s:tools/v8audio.py" % base],
                              capture_output=True, text=True, check=True).stdout
        self.assertEqual(read(os.path.join(ROOT, "tools", "v8audio.py")), then,
                         "tools/v8audio.py was edited after the data existed")

    def test_the_record_says_so_where_the_verdict_is(self):
        s = plain(v8_part())
        self.assertIn("Not one line of tools/v8audio.py was edited for this run", s)


class TheRawsAreTheOperatorsAndTheArchiveMatchesThem(unittest.TestCase):

    def test_the_hashes(self):
        if not (os.path.exists(LOG) and os.path.exists(BIN)):
            self.skipTest("RUN 30 is not archived in this checkout (captures/local is ignored)")
        self.assertEqual(sha(LOG), LOG_SHA)
        self.assertEqual(sha(BIN), BIN_SHA)
        self.assertEqual(os.path.getsize(LOG), 88929)
        self.assertEqual(os.path.getsize(BIN), 5243788)

    def test_the_raw_drop_is_untouched(self):
        if not (os.path.exists(RAW_LOG) and os.path.exists(RAW_BIN)):
            self.skipTest("the raw drop is not in this checkout (logs/ is ignored)")
        self.assertEqual(sha(RAW_LOG), LOG_SHA)
        self.assertEqual(sha(RAW_BIN), BIN_SHA)

    def test_the_document_carries_both_hashes(self):
        s = v8_part()
        self.assertIn(LOG_SHA, s)
        self.assertIn(BIN_SHA, s)


class TheSidecarIsVerifiedBeforeItIsRead(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(BIN):
            self.skipTest("RUN 30's sidecar is not in this checkout")
        self.data, self.h, self.anchors, self.wins = capture()

    def test_the_contract_and_the_crcs(self):
        self.assertEqual(self.h["header_crc32"], HEADER_CRC)
        self.assertEqual(self.h["total_crc32"], TOTAL_CRC)
        self.assertEqual(self.h["total_size"], 5243788)
        self.assertEqual(self.h["total_size"], 0x100 + 5 * 128 + 1280 * 4096 + 12)
        self.assertEqual((self.h["test_id"], self.h["build_id"], self.h["commit"]),
                         ("GBP-AUDIO-001", "stream-0016", "04121fe"))

    def test_the_runs_own_log_recorded_the_same_figures(self):
        """Recomputed first, compared second: that order is what makes the
        agreement mean anything."""
        t = read(LOG)
        m = re.search(r"AWINSAVE rc=(\d+) n=(\d+) written=(\d+) flags=(\w+) header_crc=(\w+) total_crc=(\w+)", t)
        self.assertTrue(m, "the log carries no AWINSAVE record")
        self.assertEqual(int(m.group(3)), self.h["total_size"])
        self.assertEqual(int(m.group(5), 16), self.h["header_crc32"])
        self.assertEqual(int(m.group(6), 16), self.h["total_crc32"])
        self.assertEqual(int(m.group(4), 16), 0)

    def test_the_capture_is_complete_and_nothing_was_refused(self):
        self.assertEqual((self.h["windows_n"], self.h["windows_closed"], self.h["blocks_stored"]), (5, 5, 1280))
        self.assertEqual((self.h["blocks_failed"], self.h["arm_refused_busy"], self.h["arm_refused_full"]), (0, 0, 0))
        self.assertEqual(self.h["arms"], 5)
        for a in self.anchors:
            self.assertEqual(a["blocks"], 256)
            self.assertEqual(a["skipped"], 0)
            self.assertEqual(a["flags"], 1)          # CLOSED, and neither INCOMPLETE nor GAP

    def test_four_presses_produced_four_windows_not_eight(self):
        """The rising-edge anchor, confirmed on hardware."""
        t = read(LOG)
        m = re.search(r"AWIN .*presses=(\d+) releases=(\d+)", t)
        self.assertEqual((int(m.group(1)), int(m.group(2))), (4, 4))
        self.assertEqual(sum(1 for a in self.anchors if a["kind"] == 1), 4)
        self.assertEqual([a["event_n"] for a in self.anchors], [0, 2, 4, 6, 8])
        self.assertTrue(all(a["word"] == 0x0001 for a in self.anchors if a["kind"] == 1))


class TheControlWindowIsReadFirst(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(BIN):
            self.skipTest("RUN 30's sidecar is not in this checkout")
        _, _, _, self.wins = capture()

    def test_it_is_not_silence_shaped(self):
        c = self.wins[0]
        vals = set()
        for b in c:
            vals.update(b)
        self.assertEqual(sorted(vals), [0x00, 0x01, 0xFE, 0xFF])
        self.assertEqual(len({bytes(b) for b in c}), 9)
        self.assertEqual(sum(1 for b in c if bytes(b) == bytes(c[0])), 245)

    def test_the_period_is_exactly_256_bytes_and_the_duty_is_a_half(self):
        c = self.wins[0]
        for b in c:
            e = edges(b)
            self.assertGreaterEqual(len(e), 3)
            self.assertTrue(all(e[i + 1] - e[i] == 256 for i in range(len(e) - 1)))
            lo, hi = min(b), max(b)
            mid = (lo + hi) / 2.0
            self.assertEqual(sum(1 for x in b if x > mid), 2048)   # 128/256

    def test_it_is_not_the_cartridge_less_byte_0_pattern(self):
        b = self.wins[0][0]
        self.assertFalse(all(x == 0 for i, x in enumerate(b) if i % 32))


class ThePressesChangeTheWindowOneGbaFrameLater(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(BIN):
            self.skipTest("RUN 30's sidecar is not in this checkout")
        _, _, _, self.wins = capture()
        self.ctrl = set()
        for b in self.wins[0]:
            self.ctrl.update(b)

    def test_the_period_never_changes_anywhere_in_the_capture(self):
        bad = 0
        for w in self.wins:
            for b in w:
                e = edges(b)
                if len(e) >= 3 and any(e[i + 1] - e[i] != 256 for i in range(len(e) - 1)):
                    bad += 1
        self.assertEqual(bad, 0, "the 256-byte period is not universal")

    def test_new_levels_appear_only_in_presses_2_3_and_4(self):
        counts = []
        for w in self.wins:
            c = Counter()
            for b in w:
                c.update(b)
            counts.append(c[0x80])
        self.assertEqual(counts, [0, 0, 5564, 10749, 19309])
        for i in (0, 1):
            vals = set()
            for b in self.wins[i]:
                vals.update(b)
            self.assertEqual(sorted(vals), [0x00, 0x01, 0xFE, 0xFF])
        for i in (2, 3, 4):
            vals = set()
            for b in self.wins[i]:
                vals.update(b)
            self.assertEqual(sorted(vals), [0x00, 0x01, 0x80, 0x81, 0xF8, 0xFA, 0xFE, 0xFF])

    def test_the_onset_brackets_one_gba_frame(self):
        BLOCK_MS = 1000.0 / 4094.4
        onsets = []
        for w in self.wins:
            k = next((j for j, b in enumerate(w) if not set(b) <= self.ctrl), None)
            onsets.append(k)
        self.assertEqual(onsets[:2], [None, None])
        ms = [k * BLOCK_MS for k in onsets[2:]]
        self.assertEqual(onsets[2:], [75, 65, 50])
        for x in ms:
            self.assertLess(x, 2 * 16.74)
        self.assertAlmostEqual(ms[0], 18.32, places=1)
        self.assertAlmostEqual(ms[1], 15.88, places=1)
        self.assertAlmostEqual(ms[2], 12.21, places=1)


class TheVerdictsAreTheFrozenConstructionsOwn(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(BIN):
            self.skipTest("RUN 30's sidecar is not in this checkout")
        _, _, _, self.wins = capture()

    def test_AU_is_carries_other_shape(self):
        import v8audio as v8
        au = v8.question_AU(self.wins[1:], self.wins[0])
        self.assertEqual(au["verdict"], "CARRIES / OTHER SHAPE")
        self.assertIn("CARRIES / OTHER SHAPE", v8_part())

    def test_SP_is_not_observed(self):
        import v8audio as v8
        sp = v8.question_SP(self.wins[1:])
        self.assertEqual(sp["verdict"], v8.NOT_OBSERVED)
        self.assertIn("SP = NOT OBSERVED", plain(v8_part()) or "")

    def test_every_model_but_PCM_refuses_these_bytes(self):
        import v8audio as v8
        for w in self.wins:
            self.assertIsNone(v8.level_series(w, "PWM"))
            self.assertIsNone(v8.level_series(w, "BYTE0"))
            self.assertIsNotNone(v8.level_series(w, "PCM"))


class TPrimeIsNominalAndRecomputed(unittest.TestCase):

    def test_the_verdict_and_the_figures(self):
        if not (os.path.exists(LOG) and os.path.exists(REF17)):
            self.skipTest("RUN 30 or its reference is not in this checkout")
        import tprime
        r = tprime.question_tprime(read(LOG), read(REF17), "run30", "run17")
        self.assertEqual(r["verdict"], "NOMINAL")
        self.assertEqual(r["fault_why"], [])
        self.assertTrue(r["control_unchanged"])
        self.assertEqual(r["medians"]["new_audio"], r["medians"]["ref_audio"])
        self.assertLessEqual(r["medians"]["new_video"], r["medians"]["ref_video"])
        self.assertTrue(all(r["checks"].values()))
        # the population is §V7.9.2's: CYCF/CYCFT and CYCL/CYCLT only, nothing excluded
        self.assertEqual(r["classes"]["new"]["n"], 16)
        self.assertEqual(r["classes"]["new"]["excluded"], 0)
        self.assertGreaterEqual(len(r["classes"]["new"]["video"]), 5)
        self.assertGreaterEqual(len(r["classes"]["new"]["audio_only"]), 5)

    def test_the_record_states_the_same_verdict(self):
        s = plain(v8_part())
        self.assertIn("QUESTION T' NOMINAL", s.replace("′", "'"))
        self.assertIn("T' is not applied to RUN 17, 21, 22, 25 or 26 as a verdict".replace("'", "'"),
                      plain(read(EVIDENCE)).replace("′", "'"))


class TheRecordSaysWhatWasFoundAndWhatWasNot(unittest.TestCase):

    def test_the_prose_correction_keeps_the_wrong_sentence(self):
        t = read(HW)
        self.assertIn("It is\nevidence about the instrument — it bears on SP", t)
        self.assertIn("##### V8.10.1 CORRECTED 2026-09-22", t)
        s = plain(t[t.index("##### V8.10.1"):t.index("### V8.11 ")])
        self.assertIn("is false", s)
        self.assertIn("links -lfat -logc and no audio library", s)
        # and the claim is checked against the Makefile itself, not against the prose
        mk = read(os.path.join(ROOT, "poc", "gbp-audio-window-probe", "Makefile"))
        self.assertIn("LIBS     := -lfat -logc", mk)
        for audio in ("-lasnd", "-laesnd", "ASND", "AESND", "AUDIO_Init"):
            self.assertNotIn(audio, mk, audio)
        self.assertIn("The Operator was briefed without this", s)
        self.assertIn("NEGATIVE CONTROL", s)
        self.assertIn("is NOT a post-hoc reinterpretation of a gate", s)

    def test_u_gbp_012_is_not_closed(self):
        t = read(UNK)
        head = [l for l in t.splitlines() if l.startswith("## U-GBP-012")][0]
        self.assertIn("STILL OPEN", head)
        self.assertIn("STAYS OPEN", head)
        body = t[t.index("## U-GBP-012"):t.index("## U-GBP-013")]
        self.assertIn("STILL UNKNOWN, and this is why the item does not close", body)

    def test_the_two_new_unknowns_exist_and_say_what_would_close_them(self):
        t = read(UNK)
        self.assertIn("## U-GBP-037 (P1", t)
        self.assertIn("## U-GBP-038 (P3", t)
        u37 = t[t.index("## U-GBP-037"):t.index("## U-GBP-038")]
        self.assertIn("stimulus/agb-tone", u37)
        self.assertIn("What would close it", u37)

    def test_the_part_claims_no_frequency(self):
        s = plain(v8_part())
        self.assertIn("NO FREQUENCY IS CLAIMED", plain(read(EVIDENCE)))
        self.assertIn("No frequency. No sample rate.", s)


if __name__ == "__main__":
    unittest.main()
