"""tests/host/test_v17decode.py — §V17.6: the H-PWM decode, its verdict, and the audio.

The decoder is exercised on SYNTHETIC blocks first — a known square wave in, the
known period and amplitude out — so a pass on the captures is not the only thing
standing between the code and the claim. Then the verdict is recomputed on the
archive, and the correction to §V17.4's disclosure is pinned against the bytes.
"""
import math
import os
import re
import subprocess
import sys
import tempfile
import unittest

import frozen  # noqa: E402  (tests/host is on the path)
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v11sweep as v  # noqa: E402
import v17decode as d  # noqa: E402
import v17pred  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
LOCAL = os.path.join(ROOT, "captures", "local")
B33 = os.path.join(LOCAL, "GBP-AUDIO-004_stream-0016-run33-audio.bin")
B34 = os.path.join(LOCAL, "GBP-AUDIO-003_stream-0016-run34-audio.bin")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s.replace("\n> ", " ")).replace("`", "").replace("**", "").replace("*", "")


def part():
    t = read(HW)
    i = t.index("\n### V17.6 ")
    j = t.find("\n## V", i + 1)
    return (t[i:j] if j >= 0 else t[i:]).lstrip("\n")


def block_with_bits(ones):
    """A 4096-byte block holding exactly `ones` one-bits, laid as whole 0xFF bytes
    and one partial byte, spanning 0x00..0xFF."""
    full, rem = divmod(ones, 8)
    b = [0xFF] * full + ([(0xFF << (8 - rem)) & 0xFF] if rem else [])
    return b + [0x00] * (4096 - len(b))


def square_window(period, dev_bits, rest_bits=16384, onset=v.ONSET_SLICE_BLOCKS):
    out = [block_with_bits(rest_bits)] * onset
    for i in range(256 - onset):
        out.append(block_with_bits(rest_bits + (dev_bits if (i % period) < period // 2 else -dev_bits)))
    return out


class TheDecoderOnSyntheticSquares(unittest.TestCase):

    def test_a_block_is_one_sample_and_its_value_is_the_bit_fraction(self):
        rest = 16384 / 32768.0
        self.assertAlmostEqual(d.decode([block_with_bits(16384)], rest)[0], 0.0)
        self.assertAlmostEqual(d.decode([block_with_bits(16384 + 2048)], rest)[0], 2048 / 32768.0)

    def test_the_byte_order_inside_a_block_does_not_matter(self):
        b = block_with_bits(20000)
        self.assertEqual(d.decode([b], 0.5), d.decode([list(reversed(b))], 0.5))

    def test_each_scheduled_period_is_recovered_exactly(self):
        for per in (32, 8, 16, 4):
            m = d.measure_window(square_window(per, 4000))
            self.assertEqual(m["period"], per)
            self.assertEqual(m["uniformity"], 1.0)

    def test_a_V_ladder_holds_and_a_flat_one_is_refuted(self):
        wins = [square_window(32, b) for b in (3840, 2816, 1792, 768)]
        self.assertEqual(d.question_D(wins, [v.KEY_B] * 4)["verdict"], "LAYOUT HOLDS")
        wins = [square_window(32, 3840)] * 4
        self.assertEqual(d.question_D(wins, [v.KEY_B] * 4)["verdict"], "LAYOUT REFUTED")

    def test_a_wrong_timebase_is_refuted(self):
        wins = [square_window(p, 3840) for p in (32, 8, 24, 4)]      # 24 where 16 is predicted
        r = d.question_D(wins, [v.KEY_A] * 4)
        self.assertEqual(r["verdict"], "LAYOUT REFUTED")
        self.assertIn("[3]", r["why"])

    def test_the_axis_is_derived_not_assumed(self):
        wins = [square_window(32, 3840)] * 4
        self.assertEqual(d.question_D(wins, [v.KEY_A, v.KEY_B, v.KEY_A, v.KEY_A])["verdict"],
                         "INCONCLUSIVE")

    def test_the_resampler_keeps_a_tone_at_its_frequency(self):
        tone = [math.sin(2 * math.pi * 128.0 * n / 4096.0) for n in range(512)]
        up = d.resample(tone)
        self.assertEqual(len(up), 512 * 48000 // 4096)
        # zero crossings per second of the middle half, where the kernel is fully inside
        mid = up[len(up) // 4: 3 * len(up) // 4]
        rises = sum(1 for i in range(1, len(mid)) if mid[i - 1] <= 0 < mid[i])
        self.assertAlmostEqual(rises / (len(mid) / 48000.0), 128.0, delta=4.0)

    def test_the_wav_writer_uses_one_fixed_gain(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "x.wav")
            d.write_wav(p, [0.125, -0.125], 4096)
            with wave.open(p) as w:
                import struct
                a, b = struct.unpack("<2h", w.readframes(2))
        self.assertAlmostEqual(a / 32767.0, 0.80, places=3)
        self.assertAlmostEqual(b / 32767.0, -0.80, places=3)
        self.assertAlmostEqual(d.GAIN, 0.80 / 0.125)

    def test_the_decoder_does_not_edit_the_frozen_predictions(self):
        then = frozen.source("Issue #80 -- predictions frozen", "tools/v17pred.py")   # Issue #83 (F): pinned by HASH; the phrase is checked, not searched
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v17pred.py")))
        # and the decoder did not exist in that commit
        base = frozen.base("Issue #80 -- predictions frozen")
        exists = subprocess.run(["git", "-C", ROOT, "cat-file", "-e", "%s:tools/v17decode.py" % base],
                                capture_output=True).returncode
        self.assertNotEqual(exists, 0, "the decoder existed when the predictions were frozen")


class TheVerdictOnTheArchive(unittest.TestCase):

    def load(self, p):
        if not os.path.exists(p):
            self.skipTest("RUN 33 or RUN 34 is not archived in this checkout")
        import awinparse
        return awinparse.load(p)

    def test_both_runs_LAYOUT_HOLDS_with_every_period_exact(self):
        for p, axis, periods in ((B33, "F", [32, 8, 16, 4]), (B34, "V", [32, 32, 32, 32])):
            _, _, anc, wins = self.load(p)
            r = d.question_D(wins[1:], [a["keys"] for a in anc if a["kind"] == 1])
            self.assertEqual(r["axis"], axis)
            self.assertEqual(r["verdict"], "LAYOUT HOLDS")
            self.assertEqual([row["period"] for row in r["rows"]], periods)
            self.assertTrue(all(row["uniformity"] == 1.0 for row in r["rows"]))

    def test_the_1024_hz_window_has_four_levels_with_the_128_hz_extremes(self):
        import collections
        import v14repeat
        _, _, _, wins = self.load(B33)
        c1 = collections.Counter(round(v14repeat.bitduty(b) * 2048) for b in v.sliced(wins[1]))
        c4 = collections.Counter(round(v14repeat.bitduty(b) * 2048) for b in v.sliced(wins[4]))
        self.assertEqual(sorted(k for k, n in c4.items() if n >= 40), [785, 845, 1206, 1266])
        top1 = sorted(k for k, _ in c1.most_common(2))
        self.assertEqual(top1, [785, 1266])                      # the SAME extremes
        self.assertEqual((1266 + 785) / 2.0, (1206 + 845) / 2.0)  # symmetric about the rest
        # with the levels rounded to 1/2048 of a cell the pair gives 26.3125; deviation() works at
        # block resolution and gives 26.3047 -- the same pair, and the page says both
        self.assertAlmostEqual((1266 - 845) / 2.0 / 2048 * 256, 26.3125, places=4)
        self.assertAlmostEqual(v14repeat.deviation(wins[4]) * 256, 26.3047, places=3)


class TheRecord(unittest.TestCase):

    def test_the_correction_to_the_disclosure_is_made_here_not_in_V17_4(self):
        s = plain(part())
        self.assertIn("Keeping it out was right. The reading behind the disclosure was wrong", s)
        self.assertIn("The near-exact 7/8 ratio that made it look like a filter is a symptom of the tie", s)
        t = read(HW)
        v174 = t[t.index("### V17.4 "):t.index("### V17.5 ")]
        self.assertIn("was\nseen to read lower", v174)     # §V17.4 keeps its words

    def test_the_audio_is_described_and_the_evidence_is_the_4096_file(self):
        s = plain(part())
        self.assertIn("<- THE EVIDENCE", part())
        self.assertIn("It adds no information", s)
        self.assertIn("It is for listening, not evidence, and says so in its name", s)
        self.assertIn("exactly 375/32", s)

    def test_the_evidence_is_CORROBORATED_and_not_FACT(self):
        h = [l for l in read(EV).split("\n") if l.startswith("### GBP-HW-313")][0]
        self.assertIn("CORROBORATED for the layout, not FACT", h)

    def test_the_integrating_sampler_is_only_a_hypothesis(self):
        s = plain(part())
        self.assertIn("labelled as a HYPOTHESIS", s)
        self.assertIn("one window is not enough to promote it", s)


if __name__ == "__main__":
    unittest.main()
