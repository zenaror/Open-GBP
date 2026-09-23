"""tests/host/test_v17pred.py — §V17's predictions, frozen before the decoder.

Synthetic checks only: the predictions must follow from the ROM's own tables and
GBATEK, one axis at a time, and the module must be byte-identical to the commit
that froze it."""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v11sweep  # noqa: E402
import v17pred as p  # noqa: E402

HW = os.path.join(ROOT, "docs", "research", "HARDWARE_TESTS.md")


def read(f):
    with open(f, encoding="utf-8") as fh:
        return fh.read()


def part():
    t = read(HW)
    i = t.index("\n## V17 ")
    j = t.find("\n## V", i + 1)
    return (t[i:j] if j >= 0 else t[i:]).lstrip("\n")


class ThePredictionsComeFromTheROM(unittest.TestCase):

    def test_the_tables_parsed_from_the_rom_are_v11sweeps_frozen_ones(self):
        self.assertEqual(p.freq_n(), v11sweep.FREQUENCY_N)
        self.assertEqual(p.volumes(), v11sweep.AMPLITUDES)

    def test_axis_F_walks_frequency_at_the_first_volume(self):
        rows = p.predict("F")
        self.assertEqual([r["frequency_hz"] for r in rows], [128.0, 512.0, 256.0, 1024.0])
        self.assertEqual([r["period"] for r in rows], [32.0, 8.0, 16.0, 4.0])
        self.assertEqual({r["volume"] for r in rows}, {15})

    def test_axis_V_walks_volume_at_128_hz(self):
        rows = p.predict("V")
        self.assertEqual({r["frequency_hz"] for r in rows}, {128.0})
        self.assertEqual([r["volume"] for r in rows], [15, 11, 7, 3])

    def test_the_module_refuses_to_predict_both_axes_at_once(self):
        """Issue #80's original conflation, made impossible through the module."""
        for bad in ("FV", "both", None, ""):
            with self.assertRaises(ValueError):
                p.predict(bad)

    def test_every_period_is_exact(self):
        for n in p.freq_n():
            self.assertEqual((2048 - n) % 32, 0)
            self.assertEqual(p.period_samples(n), (2048 - n) / 32)

    def test_the_band_and_its_cost_in_hertz(self):
        lo, hi = p.period_band(32.0)
        self.assertAlmostEqual(4096 / hi, 124.1, places=1)
        self.assertAlmostEqual(4096 / lo, 132.1, places=1)
        lo, hi = p.period_band(4.0)
        self.assertAlmostEqual(4096 / hi, 819.2, places=1)
        self.assertAlmostEqual(4096 / lo, 1365.3, places=1)
        self.assertIn("819–1365 Hz at 1024 Hz", part())


class TheRecordIsHonestAboutWhatWasSeen(unittest.TestCase):

    def test_the_fixture_correction_is_stated(self):
        s = part()
        self.assertIn("That is not\nwhat the ROM does.", s)
        self.assertIn("RUN 34 (B x4)   128.0 Hz in every window", s)

    def test_the_disclosure_and_the_exclusion_it_justifies(self):
        s = re.sub(r"\s+", " ", part())
        self.assertIn("Amplitude against FREQUENCY is NOT in the gate", s)
        self.assertIn("RUN 33's 1024 Hz window was seen to read lower than its 128 Hz window", s)
        src = read(os.path.join(ROOT, "tools", "v17pred.py"))
        self.assertIn("A DISCLOSURE", src)

    def test_the_layout_is_stated_in_one_paragraph(self):
        s = re.sub(r"\s+", " ", part())
        for phrase in ("one sample", "fraction of one-bits in the block",
                       "4096 per second", "Discarded:", "The resting level is subtracted"):
            self.assertIn(phrase, s)

    def test_this_commit_carries_no_decoder_and_no_output(self):
        self.assertIn("No decoder, no decoded output, no audio file and no verdict", part())

    def test_the_module_is_not_edited_after_its_commit(self):
        base = subprocess.run(["git", "-C", ROOT, "log", "--format=%H", "-1", "--grep",
                               "Issue #80 -- predictions frozen"], capture_output=True,
                              text=True).stdout.strip()
        if not base:
            self.skipTest("the commit that introduced tools/v17pred.py is not in this checkout")
        then = subprocess.run(["git", "-C", ROOT, "show", "%s:tools/v17pred.py" % base],
                              capture_output=True, text=True).stdout
        self.assertEqual(then, read(os.path.join(ROOT, "tools", "v17pred.py")))


if __name__ == "__main__":
    unittest.main()
