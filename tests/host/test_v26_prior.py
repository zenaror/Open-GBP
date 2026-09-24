"""
tests/host/test_v26_prior.py — GitHub Issue #113: what §V26.8 records as checked before §V26's clause froze, recomputed
from the versioned fixtures.

RUN 39's press frame, from its per-block VIDEO trace (the frozen tools/v23report.py), satisfies the rebuilt clause's P:
it is the frame in flight when the press was read, t_first_block <= t_press < the next frame's t_first_block, with 39
blocks and its one missing block straddling t_press. The trace's segmentation (GBI's predicate) is the frame store's
(the Disc's): no disagreement in RUN 39 or RUN 41. The bound the clause reads from the log, the last preserved
start-up episode's close frame, is 197 in RUN 39, RUN 40 and RUN 41, and RUN 39's thirteen located signature frames
sit well inside it.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v23report  # noqa: E402

FXD = os.path.join(ROOT, "captures", "fixtures")
R39 = os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-trace-0001-run39")
LOGS = {39: R39 + ".log", 40: os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-split-0001-run40.log"),
        41: os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-game-0001-run41.log")}
TB = 40500000.0


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def kv(s):
    return dict(re.findall(r"(\w+)=(\S*)", s))


class RUN39sPressFrameIsP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        log = read(R39 + ".log")
        with open(R39 + "-trace.bin", "rb") as f:
            rep = v23report.build(log, f.read())
        lt = kv(re.search(r"^\d{6} LIVET (.*)$", log, re.M).group(1))
        l2 = kv(re.search(r"^\d{6} LIVET2 (.*)$", log, re.M).group(1))
        cls.tp, cls.ta = int(lt["t_press"], 16), int(l2["t_ai_start"], 16)
        vt, vs = rep["video"]["ticks"], rep["video"]["start"]
        starts = [i for i, s in enumerate(vs) if s]
        cls.frames = []          # (blocks, t_first, t_last, t_next, largest gap, its block, gap start, gap end)
        for j in range(len(starts) - 1):
            a, b = starts[j], starts[j + 1]
            gaps = [vt[i + 1] - vt[i] for i in range(a, b - 1)]
            k = gaps.index(max(gaps))
            cls.frames.append((b - a, vt[a], vt[b - 1], vt[b], max(gaps), k, vt[a + k], vt[a + k + 1]))

    def test_exactly_one_frame_is_in_flight_at_the_press_and_it_is_the_incomplete_one(self):
        p = [f for f in self.frames if f[1] <= self.tp < f[3]]
        self.assertEqual(len(p), 1)
        blocks, first, last, nxt, gap, at, g0, g1 = p[0]
        self.assertEqual(blocks, 39)
        ms = lambda t: round((t - self.tp) * 1e3 / TB, 3)
        self.assertEqual((ms(first), ms(last), ms(nxt)), (-3.682, 7.795, 13.163))
        # its one missing block: the largest intra-frame gap, and it straddles t_press
        self.assertEqual((round(gap * 1e3 / TB, 3), at), (0.714, 12))
        self.assertLess(g0, self.tp)
        self.assertLess(self.tp, g1)

    def test_the_neighbours_are_complete(self):
        i = [k for k, f in enumerate(self.frames) if f[1] <= self.tp < f[3]][0]
        self.assertEqual((self.frames[i - 1][0], self.frames[i + 1][0]), (40, 40))

    def test_a_time_window_of_one_chunk_period_would_admit_four(self):
        """§V26.3's superseded window: frames whose t_last_block lies within 31.222 ms of t_press. FOUR, not the
        three §V26.7's text says (j=337-339): j=336's t_last_block, at -25.688 ms, is inside it too (§V26.8)."""
        w = 31.222e-3 * TB
        near = [f for f in self.frames if abs(f[2] - self.tp) <= w]
        self.assertEqual(len(near), 4)
        self.assertEqual([round((f[2] - self.tp) * 1e3 / TB, 3) for f in near], [-25.688, -8.969, 7.795, 24.516])

    def test_the_press_was_before_the_ai(self):
        self.assertLess(self.tp, self.ta)


class TheSegmentationsAgreeAndTheBoundIsTheLogs(unittest.TestCase):
    def test_no_predicate_disagreement(self):
        for run in (39, 41):
            self.assertRegex(read(LOGS[run]), r"PREDICATES boundaries_disc=(\d+) boundaries_gbi=\1 disagreements=0 ")

    def test_the_last_preserved_start_up_episode_closes_at_197(self):
        for run, path in LOGS.items():
            eps = [kv(m) for m in re.findall(r"^\d{6} EPISODE (.*)$", read(path), re.M)]
            self.assertEqual([int(e["open_frame"]) for e in eps], [8, 30, 90, 150], run)
            self.assertEqual(max(int(e["close_frame"]) for e in eps), 197, run)


if __name__ == "__main__":
    unittest.main()
