"""tests/host/test_u045_cadence.py -- GitHub Issue #100: U-GBP-045 from RUN 38's archive.

The method is proved on constructions before it is believed on data: a square wave with losses
removed at known places gives those places back, and the phase statistic reads 1 for a periodic
set and near 0 for a set with no period. Then every figure the record states is recomputed from the
versioned fixtures by tools/u045cadence.py, and the record is checked for saying what the archive
does NOT establish.
"""
import os
import random
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import u045cadence as U  # noqa: E402

FX = os.path.join(ROOT, "captures", "fixtures", "hw-gamecube-gbp-2026-09-24-live-0001-run38")
EV = os.path.join(ROOT, "docs", "research", "EVIDENCE.md")
UNK = os.path.join(ROOT, "docs", "research", "UNKNOWNS.md")


def read(p, mode="r"):
    with open(p, mode, **({} if "b" in mode else {"encoding": "utf-8", "errors": "replace"})) as f:
        return f.read()


def plain(s):
    return re.sub(r"\s+", " ", s).replace("`", "").replace("**", "").replace("*", "")


def square(n_halves, lost):
    """A 128 Hz tone as the decoder emits it (15 plateau samples and one step sample per half),
    with the samples at the absolute block indices in `lost` removed."""
    x, blk = [], 0
    for h in range(n_halves):
        level = 25900 if h % 2 == 0 else -23150
        for j in range(16):
            v = level if j < 15 else (7500 if h % 2 == 0 else -4760)
            if blk not in lost:
                x.append(v)
            blk += 1
    return x


class TheMethodOnConstructions(unittest.TestCase):
    def test_losses_at_known_blocks_come_back_in_their_half_periods(self):
        lost = {40, 41, 200, 999}                     # halves 2 (two losses), 12, 62
        losses, halves = U.audio_losses(square(80, lost))
        self.assertEqual([k for _t, k in losses], [2, 1, 1])
        for (t, _k), h in zip(losses, (2, 12, 62)):
            self.assertLessEqual(abs(t * U.BLOCKS_PER_S - 16 * h), 1.0)   # the half's start, within a sample
        self.assertEqual(sum(k for _t, k in losses), len(lost))

    def test_a_plateau_loss_is_placed_only_to_its_half(self):
        a = U.audio_losses(square(10, {33}))[0]
        b = U.audio_losses(square(10, {40}))[0]
        self.assertEqual(round(a[0][0] * U.BLOCKS_PER_S), round(b[0][0] * U.BLOCKS_PER_S))   # same half: 32..47

    def test_the_phase_statistic(self):
        per = 0.0312222
        self.assertAlmostEqual(U.rayleigh([k * per + 0.001 for k in range(200)], per)[0], 1.0, places=6)
        rng = random.Random(1)
        self.assertLess(U.rayleigh([rng.uniform(0, 10) for _ in range(200)], per)[0], 0.2)


class TheArchiveSays(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = U.analyse(read(FX + ".log"), read(FX + "-l2.bin", "rb"), trials=20000)

    def test_the_audio_losses(self):
        r = self.r
        self.assertEqual((r["samples"], r["losses"], r["loss_halves"], r["episodes"]), (40640, 296, 229, 196))
        self.assertAlmostEqual(r["span_s"], 9.994, places=3)

    def test_the_audio_losses_keep_the_ai_chunk_cadence(self):
        r = self.r
        self.assertAlmostEqual(r["ai_period_ms"], 31.2222, places=3)
        self.assertGreater(r["audio_R_ai"], 0.93)
        self.assertLess(r["audio_R_tone_grid"], r["audio_R_ai"])
        self.assertAlmostEqual(r["audio_peak"][1] * 1e3, 31.215, places=3)
        iv = r["audio_intervals_in_chunks"]
        self.assertEqual({k: iv.count(k) for k in set(iv)}, {1: 140, 2: 17, 3: 16, 4: 15, 5: 6, 8: 1})

    def test_the_video_losses_follow_the_ai_callbacks(self):
        r = self.r
        self.assertEqual((r["video_n"], r["video_tail_from_seq"]), (31, 357))
        self.assertAlmostEqual(r["video_R_ai"], 0.788, places=3)
        ph = r["video_phase_ms"]
        self.assertTrue(1.4 < min(ph) and max(ph) < 11.8, ph)
        self.assertEqual(sum(1 for p in ph if p <= 5.05), 23)
        self.assertEqual(r["video_mc_hits"], 0)

    def test_no_co_variation_second_by_second(self):
        self.assertEqual(self.r["per_second_span"], (27, 63))
        self.assertLess(abs(self.r["per_second_r"]), 0.1)


class TheRecord(unittest.TestCase):
    def entry(self):
        t = read(EV)
        i = t.index("\n### GBP-HW-327 ")
        j = t.find("\n### ", i + 1)
        return t[i:j] if j >= 0 else t[i:]

    def test_the_evidence_entry_and_its_statuses(self):
        e = plain(self.entry())
        for tok in ("FACT (statistics recomputable from the archive)",
                    "CORROBORATED that one cadence, the AI chunk cycle, orders both losses",
                    "which step of the cycle is UNKNOWN",
                    "The archive cannot say whether an individual audio loss and an individual video loss coincide",
                    "tools/u045cadence.py"):
            self.assertIn(tok, e, tok)

    def test_the_unknown_is_rescoped_on_top(self):
        h = re.search(r"^## U-GBP-045 .*$", read(UNK), re.M).group(0)
        self.assertIn("2026-09-24, Issue #100", h)
        self.assertIn("GBP-HW-327", h)
        u = read(UNK)
        body = u[u.index("## U-GBP-045 "):]
        self.assertIn("RESCOPED 2026-09-24 (GitHub Issue #100)", body)


if __name__ == "__main__":
    unittest.main()
