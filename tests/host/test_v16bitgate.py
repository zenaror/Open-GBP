"""tests/host/test_v16bitgate.py — Issue #79: GBP-HW-305 decided, duty()'s
defect named, and the gate repaired forward only.

The repaired gates are exercised on SYNTHETIC vectors that reproduce the defect,
so the repair is shown to fix the exact failure rather than merely to agree with
RUN 34. The non-retroactivity clause is checked in the document, and the
repaired gates' output on RUN 32 and RUN 34 is asserted only as the labelled
measurement the record says it is.
"""
import os
import re
import subprocess
import sys
import unittest

import frozen  # noqa: E402  (tests/host is on the path)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v11sweep as v  # noqa: E402
import v16bitgate as g  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
LOCAL = os.path.join(ROOT, "captures", "local")
B32 = os.path.join(LOCAL, "GBP-AUDIO-003_stream-0016-run32-audio.bin")
B34 = os.path.join(LOCAL, "GBP-AUDIO-003_stream-0016-run34-audio.bin")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s.replace("\n> ", " ")).replace("`", "").replace("**", "").replace("*", "")


def part():
    t = read(HW)
    i = t.index("\n## V16 ")
    j = t.find("\n## V", i + 1)
    return (t[i:j] if j >= 0 else t[i:]).lstrip("\n")


def cell(ones_ff, n80, total=256):
    """A 256-byte cell: `ones_ff` bytes of 0xFF, `n80` bytes of 0x80 (ONE bit each),
    the rest 0x00. Blocks span 0x00..0xFF, so duty()'s midpoint is 127.5."""
    return [0xFF] * ones_ff + [0x80] * n80 + [0x00] * (total - ones_ff - n80)


def block(ones_ff, n80):
    return cell(ones_ff, n80) * 16


def window(hi, lo, onset=v.ONSET_SLICE_BLOCKS):
    """Rest for the onset, then a 32-block square between two block shapes."""
    rest = block(128, 0)
    out = [rest] * onset
    for i in range(256 - onset):
        out.append(hi if (i % 32) < 16 else lo)
    return out


class TheDefectIsReproducedAndTheRepairFixesIt(unittest.TestCase):
    """Built to have exactly RUN 34's V=3 shape: a low level carrying eight 0x80
    bytes per cell."""

    def setUp(self):
        self.high = block(136, 0)          # 136 bytes of 0xFF: byte duty 136
        self.low_clean = block(120, 0)     # RUN 32's low: 120 bytes of 0xFF
        self.low_80 = block(120, 8)        # RUN 34's low: + eight 0x80 bytes

    def test_the_old_duty_counts_eight_one_bit_bytes_as_eight_whole_bytes(self):
        self.assertEqual(round(v.duty(self.low_clean) * 256), 120)
        self.assertEqual(round(v.duty(self.low_80) * 256), 128)     # the REST value
        self.assertEqual(min(self.low_80), 0x00)
        self.assertEqual(max(self.low_80), 0xFF)                    # midpoint 127.5

    def test_the_old_gate_loses_the_low_level_and_the_new_one_keeps_it(self):
        w = window(self.high, self.low_80)
        self.assertIsNone(v.classify_window(w)["deviation"])        # the defect
        self.assertIsNotNone(g.classify_window_bits(w)["deviation"])  # the repair

    def test_at_bit_level_the_eight_bytes_count_as_eight_BITS(self):
        import v14repeat
        d_clean = v14repeat.bitduty(self.low_clean)
        d_80 = v14repeat.bitduty(self.low_80)
        self.assertAlmostEqual((d_80 - d_clean) * 2048, 8.0, places=6)

    def test_the_repair_is_one_substitution_and_imports_the_rest(self):
        src = read(os.path.join(ROOT, "tools", "v16bitgate.py"))
        self.assertIn("v14repeat.bitduty(b)", src)
        for name in ("sliced", "is_flat", "is_degenerate", "observed_deviation",
                     "refusals", "ORDER_SLACK", "MOVE_SPAN_MIN", "compare_models"):
            self.assertIn("v11sweep." + name, src)
        self.assertNotIn("def duty(", src)
        self.assertNotIn("def modal_levels(", src)

    def test_v11sweep_is_not_edited(self):
        then = frozen.source("Issue #69 -- the sweep pre-registered", "tools/v11sweep.py")   # Issue #83 (F): pinned by HASH; the phrase is checked, not searched
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v11sweep.py")))

    def test_the_module_is_not_edited_after_its_commit(self):
        then = frozen.source("Issue #79 -- GBP-HW-305 decided", "tools/v16bitgate.py")   # Issue #83 (F): pinned by HASH; the phrase is checked, not searched
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v16bitgate.py")))


class QuestionLDecidesLinearityWithAModelDerivedBand(unittest.TestCase):

    def b_run(self, devs):
        import math
        out = []
        for d in devs:
            n = int(round(d * 256 * 16))            # one-bits per cell, as whole 0xFF bytes + remainder
            hi = block(128 + int(round(d * 256)), 0)
            lo = block(128 - int(round(d * 256)), 0)
            out.append(window(hi, lo))
        return out, [v.KEY_B] * 4

    def test_a_linear_ladder_is_LINEAR(self):
        a = 30.0 / 256
        w, k = self.b_run([v.deviation_linear(x, anchor=a) for x in v.AMPLITUDES])
        self.assertEqual(g.question_L_bits(w, k)["verdict"], "LINEAR")

    def test_a_compressive_ladder_is_COMPRESSIVE(self):
        a = 30.0 / 256
        w, k = self.b_run([v.deviation_compressive(x, anchor=a) for x in v.AMPLITUDES])
        self.assertEqual(g.question_L_bits(w, k)["verdict"], "COMPRESSIVE")

    def test_the_band_is_half_the_model_gap_and_nothing_else(self):
        src = read(os.path.join(ROOT, "tools", "v16bitgate.py"))
        self.assertIn("half = abs(lin - comp) / 2.0", src)
        self.assertIn("ITS TOLERANCE IS DERIVED FROM THE MODELS, NOT FROM THE RESIDUALS", src)
        # and no number that could only have come from RUN 32 / RUN 34 is in it
        body = src[src.index("def question_L_bits"):]
        self.assertIsNone(re.search(r"0\.0[0-9]+|0\.1[0-9]+", body))

    def test_why_the_order_gate_cannot_deliver_linearity_is_stated(self):
        s = plain(part())
        self.assertIn("can never take \"the deviation is linear in the volume\" there", s)


class TheRecordSaysWhatItMust(unittest.TestCase):

    def test_GBP_HW_305_is_NOT_recorded_as_a_promotion(self):
        s = plain(part())
        self.assertIn("The label does not move, because it has read CORROBORATED since Issue #72", s)
        h = [l for l in read(EV).split("\n") if l.startswith("### GBP-HW-305")][0]
        self.assertIn("which it has been since #72", h)
        self.assertIn("THE PRE-REGISTERED GATE DECLINED", h)
        self.assertIn("FACT IS STILL OWED", h)
        self.assertIn("the intercept is +0.0515", h)

    def test_GBP_HW_312_is_a_FACT_about_the_instrument(self):
        ev = read(EV)
        h = [l for l in ev.split("\n") if l.startswith("### GBP-HW-312")][0]
        self.assertIn("FACT, a property of code and data, recomputable; not a hardware claim", h)
        self.assertEqual(max(int(n) for n in re.findall(r"^#{2,4} +GBP-HW-(\d{3})\b", ev, re.M)), 318)   # 318: Issue #90 (RUN 36 ingested, the output path heard: §V21.9)

    def test_the_mechanism_recomputes_from_the_archive(self):
        if not (os.path.exists(B32) and os.path.exists(B34)):
            self.skipTest("both runs are needed and are not both archived here")
        import awinparse
        import collections
        for p, want in ((B32, {0: None}), (B34, {8: None})):
            _, _, _, w = awinparse.load(p)
            lows = [b for b in w[4][v.ONSET_SLICE_BLOCKS:] if round(v.duty(b) * 256) in (120, 128)]
            counts = collections.Counter(b[c:c + 256].count(0x80) for b in lows for c in range(0, 4096, 256))
            self.assertEqual(counts.most_common(1)[0][0], list(want)[0])
            self.assertTrue(all((min(b) + max(b)) / 2.0 == 127.5 for b in w[4]))

    def test_the_non_retroactivity_clause(self):
        s = plain(part())
        self.assertIn("question_V_bits may not be applied to RUN 32 or RUN 34 to produce a verdict", s)
        self.assertIn("§V15.8 stands unedited", s)
        self.assertIn("MEASUREMENTS, labelled as such, and never the question having been answered", s)

    def test_the_labelled_measurements_on_the_archive(self):
        if not (os.path.exists(B32) and os.path.exists(B34)):
            self.skipTest("both runs are needed and are not both archived here")
        import awinparse
        _, _, a32, w32 = awinparse.load(B32)
        _, _, a34, w34 = awinparse.load(B34)
        k = lambda a: [x["keys"] for x in a if x["kind"] == 1]
        self.assertEqual(g.question_V_bits(w32[1:], k(a32))["verdict"], "INCONCLUSIVE")
        self.assertEqual(g.question_V_bits(w34[1:], k(a34))["verdict"], "ORDERED")
        self.assertEqual(g.question_L_bits(w34[1:], k(a34))["verdict"], "LINEAR")

    def test_RUN_35_rides_along_and_changes_only_the_analysis(self):
        s = plain(part())
        self.assertIn("IT RIDES ALONG", s)
        self.assertIn("§V14.10's action list unchanged", s)
        self.assertIn("captures/local/GBP-AUDIO-003_stream-0016-run35.log", s)
        self.assertIn("RUN 35 is reserved and the files do not exist", s)
        self.assertNotIn("RUN 36", part())


if __name__ == "__main__":
    unittest.main()
