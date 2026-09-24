"""tests/host/test_run32.py — GitHub Issue #72: RUN 32 ingested.

Every figure §V11.16 states is RECOMPUTED here from the archived raws with the
frozen constructions, never quoted from the page. What cannot be recomputed —
the Operator's own report — is pinned as a quotation with its stated limit, so
the limit cannot be dropped later while the quote survives.

The archive lives under captures/local/, which Git ignores, so the recomputations
skip in a clone; everything that reads only the DOCUMENTS runs everywhere.
"""
import collections
import os
import re
import subprocess
import sys
import unittest

import frozen  # noqa: E402  (tests/host is on the path)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v11sweep as v  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")
LOCAL = os.path.join(ROOT, "captures", "local")
BIN = os.path.join(LOCAL, "GBP-AUDIO-003_stream-0016-run32-audio.bin")
LOG = os.path.join(LOCAL, "GBP-AUDIO-003_stream-0016-run32.log")
RAW = os.path.join(ROOT, "logs", "run32")
REF31 = os.path.join(LOCAL, "GBP-AUDIO-002_stream-0016-run31-audio.bin")

POP = bytes(bin(i).count("1") for i in range(256))


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def part():
    t = read(HW)
    i = t.index("\n### V11.16 RUN 32")
    j = t.find("\n### V", i + 1)
    return (t[i:j] if j >= 0 else t[i:]).lstrip("\n")


def sidecar():
    if not os.path.exists(BIN):
        raise unittest.SkipTest("RUN 32's sidecar is not in this checkout")
    import awinparse
    return awinparse.load(BIN)


def bitduty(b):
    return sum(POP[x] for x in b) / float(len(b) * 8)


def levels(blocks):
    s = [bitduty(x) for x in blocks[v.ONSET_SLICE_BLOCKS:]]
    lo = [x for x in s if x < 0.5 - 1e-6]
    hi = [x for x in s if x > 0.5 + 1e-6]
    if not lo or not hi:
        return None
    ml = collections.Counter(lo).most_common(1)[0][0]
    mh = collections.Counter(hi).most_common(1)[0][0]
    return (mh - ml) / 2.0


# ------------------------------------------------------- the archive itself

class TheRawsAreArchivedUnderTheReservedNames(unittest.TestCase):

    def test_the_hashes_on_the_page_are_the_files_hashes(self):
        import hashlib
        want = {"GBP-AUDIO-001_stream-0016.log":
                "d0f1f980dfcd6d1ad087448eb2722290cf674a9c8be546bce0a7f45447eb522a",
                "GBP-AUDIO-001_stream-0016-audio.bin":
                "ab370d0ac4f578e65b10a0aa420e4c89d10a90c9b2fd5823c9b1a84e4721d989"}
        seen = 0
        for name, h in want.items():
            p = os.path.join(RAW, name)
            if not os.path.exists(p):
                continue
            with open(p, "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), h, p)
            seen += 1
            self.assertIn(h, part())
        if not seen:
            self.skipTest("the raw drop is not in this checkout (logs/ is ignored)")

    def test_the_archive_copy_is_byte_identical_to_the_raw(self):
        raw = os.path.join(RAW, "GBP-AUDIO-001_stream-0016.log")
        if not (os.path.exists(raw) and os.path.exists(LOG)):
            self.skipTest("RUN 30 or its reference is not in this checkout")
        with open(raw, "rb") as a, open(LOG, "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_the_console_name_and_the_archive_name_disagree_by_design(self):
        if not os.path.exists(LOG):
            self.skipTest("RUN 32 is not archived in this checkout (captures/local is ignored)")
        self.assertIn("test_id=GBP-AUDIO-001", read(LOG))
        self.assertIn("GBP-AUDIO-003", os.path.basename(LOG))
        s = plain(part())
        self.assertIn("which is correct by design", s)
        self.assertIn("GBP-HW-300", part())


# ------------------------------------------------- admissibility and the axis

class TheRunIsAdmissibleAndTheScheduleIsDerived(unittest.TestCase):

    def test_every_press_window_was_armed_by_the_pads_B(self):
        _, _, anc, _ = sidecar()
        press = [a for a in anc if a["kind"] == 1]
        self.assertEqual(len(press), 4)
        self.assertEqual([a["keys"] for a in press], [v.KEY_B] * 4)
        self.assertEqual(v.derive_schedule([a["keys"] for a in press]), "V")
        self.assertEqual(v.refusals([a["keys"] for a in press], "V"), [])

    def test_the_capture_completed_and_nothing_was_refused(self):
        if not os.path.exists(LOG):
            self.skipTest("RUN 32 is not archived in this checkout")
        s = re.sub(r" +", " ", read(LOG))
        self.assertIn("complete=1 windows=5 closed=5 stored=1280", s)
        self.assertIn("refused_busy=0 refused_full=0 presses=4 releases=4", s)
        self.assertIn("events=8 emitted=8 lost=0 truncated=0", s)

    def test_the_operators_report_is_quoted_WITH_its_limit(self):
        s = part()
        self.assertIn("a metade de baixo ficava branca", s)
        self.assertIn("E o fundo mudava de cor", s)
        self.assertIn("OPERATOR OBSERVATION", s)
        f = plain(s)
        self.assertIn("It does not show the volume value", f)
        self.assertIn("His channel narrows the question; it does not close the loop", f)


# --------------------------------------------- the frozen verdicts

class TheFrozenConstructionsDecidedThisRun(unittest.TestCase):

    def test_v11sweep_is_byte_identical_to_the_commit_that_froze_it(self):
        then = frozen.source("Issue #69 -- the sweep pre-registered", "tools/v11sweep.py")   # Issue #83 (F): pinned by HASH; the phrase is checked, not searched
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v11sweep.py")))

    def test_QUESTION_V_is_INCONCLUSIVE_and_the_two_flat_windows_are_FAILURES(self):
        _, _, anc, wins = sidecar()
        keys = [a["keys"] for a in anc if a["kind"] == 1]
        r = v.question_V(wins[1:], keys)
        self.assertEqual(r["verdict"], "INCONCLUSIVE")
        self.assertEqual([c["state"] for c in r["windows"]],
                         ["CARRIAGE FAILURE", "CARRIAGE FAILURE", "CARRIES", "CARRIES"])
        self.assertIn("U-GBP-038", r["why"])
        self.assertIn("no schedule entry predicts a flat window", r["why"])
        self.assertIn("INCONCLUSIVE", part())

    def test_the_flat_windows_are_NOT_read_as_a_volume_result(self):
        """§V11.4.1's whole purpose, and this is the run it was built for."""
        s = plain(part())
        self.assertIn("never as \"volume 15 encodes nothing\"", s.replace("“", '"').replace("”", '"'))
        self.assertNotIn("volume 15 encodes nothing.", s.replace("never as \"volume 15 encodes nothing\"", ""))

    def test_QUESTION_E_verdict_and_its_named_limitation(self):
        _, _, anc, wins = sidecar()
        keys = [a["keys"] for a in anc if a["kind"] == 1]
        r = v.question_E(wins[1:], keys, "V")
        self.assertEqual(r["verdict"], "LEVELS DIFFER, NOT ORDERED")
        self.assertEqual(r["spans"], [255, 255, 255, 255])
        s = plain(part())
        self.assertIn("E's gate reads the level SPAN, and the span is saturated", s)
        self.assertIn("recorded and not repaired", s)

    def test_T_prime_is_NOMINAL_against_both_references_named(self):
        import tprime
        if not os.path.exists(LOG):
            self.skipTest("RUN 32 is not archived in this checkout")
        refs = [f for f in os.listdir(LOCAL) if "run17" in f and f.endswith(".log")]
        if not (refs and os.path.exists(os.path.join(LOCAL, "GBP-AUDIO-002_stream-0016-run31.log"))):
            self.skipTest("both references are needed and are not both archived here")
        for ref in (os.path.join(LOCAL, refs[0]),
                    os.path.join(LOCAL, "GBP-AUDIO-002_stream-0016-run31.log")):
            r = tprime.question_tprime(read(LOG), read(ref), "RUN 32", "ref")
            self.assertEqual(r["verdict"], "NOMINAL", ref)
            self.assertTrue(r["control_unchanged"])
        self.assertIn("NOMINAL", part())
        self.assertIn("The reference choice is named because it is ours", plain(part()))


# ------------------------------- the measurement beside the verdict

class TheMeasurementBesideTheVerdict(unittest.TestCase):

    def test_the_block_is_a_one_bit_pulse_and_every_byte_is_contiguous_ones(self):
        _, _, _, wins = sidecar()
        seen = set()
        for w in wins:
            seen |= set(v.alphabet(w))
        shapes = {(0xFF << (8 - n)) & 0xFF for n in range(9)}
        shapes |= {(0xFF >> (8 - n)) & 0xFF for n in range(1, 9)}
        for b in seen:
            self.assertIn(b, shapes | {0x83, 0xF1},
                          "0x%02x is not a run of contiguous one-bits" % b)
        self.assertIn("1-bit PWM pulse", part())

    def test_the_LEVELS_quantise_to_multiples_of_eight_and_transitions_do_not(self):
        """The claim the page makes, and it is the narrower one: the level each
        window SETTLES at is a multiple of 8 from rest. Blocks in transition
        between the two levels are not, and the page says so."""
        _, _, _, wins = sidecar()
        for i, want in ((3, {112, 144}), (4, {120, 136})):
            c = collections.Counter(round(v.duty(b) * 256) for b in wins[i][v.ONSET_SLICE_BLOCKS:])
            top = {d for d, n in c.most_common(2)}
            self.assertEqual(top, want)
            for d in top:
                self.assertEqual((d - 128) % 8, 0)
        odd = [round(v.duty(b) * 256) for w in wins for b in w
               if (round(v.duty(b) * 256) - 128) % 8]
        self.assertEqual(len(odd), 18)
        s = plain(part())
        self.assertIn("quantises the sample to 8 bits", s)
        self.assertIn("blocks in transition between them take intermediate values", s)

    def test_the_three_points_and_the_linear_fit_are_recomputed(self):
        import math
        if not os.path.exists(REF31):
            self.skipTest("both runs are needed and are not both archived here")
        import awinparse
        _, _, _, w31 = awinparse.load(REF31)
        _, _, _, w32 = sidecar()
        d15 = [levels(w) for w in w31[1:] if levels(w)]
        self.assertEqual(len(d15), 2)
        self.assertAlmostEqual(d15[0] * 256, 30.0625, places=3)
        self.assertAlmostEqual(d15[0], d15[1], places=6)
        d7, d3 = levels(w32[3]), levels(w32[4])
        self.assertAlmostEqual(d7 * 256, 14.0547, places=3)
        self.assertAlmostEqual(d3 * 256, 6.0547, places=3)
        pts = [(15, d15[0] * 256), (7, d7 * 256), (3, d3 * 256)]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / sum((x - mx) ** 2 for x in xs)
        icpt = my - slope * mx
        self.assertAlmostEqual(slope, 2.0007, places=3)
        self.assertAlmostEqual(icpt, 0.0515, places=3)
        # and the two models, re-anchored on the window that measured V=15
        a = d15[0] * 256
        el = sum(abs(y - a * x / 15.0) for x, y in pts[1:])
        ec = sum(abs(y - a * math.log2(1.0 + x) / math.log2(16.0)) for x, y in pts[1:])
        self.assertLess(el, 0.1)
        self.assertAlmostEqual(ec / el, 258, delta=1)
        s = part()
        self.assertIn("+0.0515 /256", s)
        self.assertIn("factor of 258", s)

    def test_it_is_named_a_measurement_and_not_a_verdict(self):
        s = plain(part())
        self.assertIn("This is a MEASUREMENT reported beside the verdict, NOT a gate that was passed", s)
        self.assertIn("a cross-run anchor the pre-registration did not authorise", s)
        self.assertIn("U-GBP-012 is not closed and H-PWM is not promoted", s)


# ------------------------------------- the instrument defect and U-GBP-038

class TheInstrumentDefectIsSeparatedFromThePath(unittest.TestCase):

    def test_the_operators_second_report_is_quoted_and_labelled(self):
        s = part()
        self.assertIn("no primeiro toque nada é reproduzido",
                      plain(s.replace("\n> ", " ")))
        self.assertIn("OPERATOR OBSERVATION, 2026-09-23", s)
        f = plain(s)
        self.assertIn("That is our ROM's defect", f.replace("**", ""))
        self.assertIn("It does not explain window 2", f)

    def test_the_write_order_is_ruled_out_against_the_vendored_gbatek(self):
        s = plain(part())
        self.assertIn("The ordering is right and is not the bug", s)
        g = os.path.join(ROOT, "external", "gbatek", "gba.md")
        if not os.path.exists(g):
            self.skipTest("external/gbatek is not in this checkout")
        self.assertIn("must be re-initialized\nafter re-enabling sound", read(g))
        # Issue #73 split the writes into apu_apply(); the ORDER is what this pins,
        # and it is the same order sweep-0001 had when the defect was found.
        src = read(os.path.join(ROOT, "stimulus", "agb-sweep", "source", "main.c"))
        body = src[src.index("static u16 apu_apply"):]
        self.assertLess(body.index("REG_SOUNDCNT_X"), body.index("REG_SOUND1CNT_H"))

    def test_the_mechanism_is_not_guessed_and_an_unknown_carries_it(self):
        self.assertIn("THE MECHANISM IS NOT DETERMINED and is not guessed here", part())
        u = read(UNK)
        self.assertIn("## U-GBP-040", u)
        self.assertIn("NOT GUESSED HERE", u)

    def test_mGBA_would_not_have_caught_it_and_that_is_said(self):
        s = plain(part())
        self.assertIn("mGBA would NOT have caught this", s)
        self.assertIn("an mGBA rung would have returned a false pass", s)

    def test_U_GBP_038_is_reopened_and_299_keeps_its_words(self):
        u = read(UNK)
        h = [l for l in u.split("\n") if l.startswith("## U-GBP-038")][0]
        self.assertIn("REOPENED 2026-09-23", h)
        ev = read(EV)
        h299 = [l for l in ev.split("\n") if l.startswith("### GBP-HW-299")][0]
        self.assertIn("REFUTED AS A FIXED PROPERTY", h299)
        self.assertIn("stay TRUE OF RUN 30 AND RUN 31", h299)

    def test_the_two_readings_are_named_and_said_to_be_confounded(self):
        s = plain(part())
        self.assertIn("READING A ELAPSED TIME", s)
        self.assertIn("READING B WINDOW ORDINAL", s)
        self.assertIn("this run does not separate them", s.lower())
        self.assertIn("no new ROM and no new image", s)

    def test_the_arming_times_reproduce_the_two_intervals(self):
        if not os.path.exists(REF31):
            self.skipTest("both runs are needed and are not both archived here")
        import awinparse
        TB = 40500000.0
        got = {}
        for name, p in (("31", REF31), ("32", BIN)):
            _, _, anc, wins = awinparse.load(p)
            ctrl = [a for a in anc if a["kind"] == 0][0]
            press = [a for a in anc if a["kind"] == 1]
            t0 = ctrl["t_arm"] - 5.0 * TB
            alive = [i for i, w in enumerate(wins[1:]) if levels(w)]
            got[name] = ((press[min(alive) - 1]["t_arm"] - t0) / TB,
                         (press[min(alive)]["t_arm"] - t0) / TB)
        self.assertAlmostEqual(got["31"][0], 9.227, places=2)
        self.assertAlmostEqual(got["31"][1], 12.547, places=2)
        self.assertAlmostEqual(got["32"][0], 29.264, places=2)
        self.assertAlmostEqual(got["32"][1], 32.634, places=2)
        # DISJOINT, which is the finding
        self.assertGreater(got["32"][0], got["31"][1])
        self.assertIn("DISJOINT", part())


class NothingWasPromotedAndTheIdsAreWhereTheyShouldBe(unittest.TestCase):

    def test_the_ids_minted_are_303_to_307(self):
        ev = read(EV)
        self.assertEqual(max(int(n) for n in re.findall(
            r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 321)   # 318: Issue #90 (RUN 36 ingested, the output path heard: §V21.9)   # 319…321: Issue #91 (RUN 37 ingested: D1, D2, QUESTION A; §V19.14)
        for i in range(303, 308):
            self.assertIn("### GBP-HW-%d" % i, ev)

    def test_U_GBP_012_is_not_closed(self):
        u = read(UNK)
        i = u.index("## U-GBP-012")
        j = u.index("\n## U-GBP-013")
        self.assertNotIn("CLOSED", u[i:j])

    def test_the_part_claims_nothing_beyond_this_run(self):
        s = part()
        self.assertNotIn("RUN 33", s)
        self.assertIn("What this part does NOT claim", s)


if __name__ == "__main__":
    unittest.main()
