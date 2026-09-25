"""tests/host/test_vevents.py -- GitHub Issue #120: tools/vevents.py, how fast the video state model's event store
fills, what fills it and what session a store permits. DESCRIPTIVE; a capacity fact, never a gate.

On constructions: a log whose events come one per frame reads one per frame and 59.727 Hz worth of seconds per
record; a log without its records is refused, not guessed. From the SOURCE: the episode path emits one event per
frame while an episode is open (the claim the tool's docstring makes of src/gbp/gbp_vstate.c is checked against the
file). Then the versioned runs are pinned: RUN 43 (sync-0001, the run the store stopped), RUN 42 and RUN 41 (the same
cartridge, 64 s windows); RUN 21 and RUN 22 (play-0001, GBP-HW-282) from the local archive when it is present.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import vevents  # noqa: E402

FXD = os.path.join(ROOT, "captures", "fixtures")
LOCAL = os.path.join(ROOT, "captures", "local")
RUNS = {43: os.path.join(FXD, "hw-gamecube-gbp-2026-09-25-sync-0001-run43.log"),
        42: os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-game-0002-run42.log"),
        41: os.path.join(FXD, "hw-gamecube-gbp-2026-09-24-game-0001-run41.log"),
        21: os.path.join(LOCAL, "GBP-PLAY-001_play-0001-run21.log"),
        22: os.path.join(LOCAL, "GBP-PLAY-001_play-0001-run22.log")}


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def synthetic(n_frames, tb=40500000):
    """A log of n_frames events, one episode_stabilising per frame at 59.727 Hz, all printed."""
    lines = ["000001 CLOCKS tb_hz=%d epoch=0 capture_start=%x stop=0" % (tb, 1000),
             "000002 CLOCKSEC capture_s=%.3f" % (n_frames / 59.727),
             "000003 FRAMECAP frames=%d complete=%d incomplete=0 resync=0" % (n_frames, n_frames),
             "000004 STRUCTURED status=observed episodes=1 stable=0 unstable=1",
             "000005 PREDICATES boundaries_disc=0 boundaries_gbi=0 disagreements=0"]
    for i in range(n_frames):
        t = 1000 + int(round(i * tb / 59.727))
        lines.append("%06d EV seq=%d t=%x type=episode_stabilising f=%d ep=00000001 a=1 b=%d c=0 d=0"
                     % (10 + i, i + 1, t, i, i))
    lines.append("%06d EVENTS n=%d shown=%d dropped=0 store_full=0 seq_last=%d" % (10 + n_frames, n_frames, n_frames,
                                                                                    n_frames))
    return "\n".join(lines) + "\n"


class OnConstructions(unittest.TestCase):
    def test_one_per_frame(self):
        r = vevents.analyse(synthetic(120))
        self.assertAlmostEqual(r["per_frame"], 1.0, places=9)
        self.assertAlmostEqual(r["per_s"], 59.727, delta=0.01)
        self.assertAlmostEqual(r["head"]["per_frame"], 1.0, places=9)
        self.assertAlmostEqual(r["permits_s"]["one_per_frame"], 16384 / 59.727, places=6)
        self.assertAlmostEqual(r["permits_s"]["episode_ceiling"], 16384 / (5.0 / 3.0 * 59.727), places=6)
        self.assertEqual(r["permits_s"]["design_assumed"], 4096.0)

    def test_a_log_without_its_records_is_refused(self):
        text = "\n".join(l for l in synthetic(10).splitlines() if " FRAMECAP " not in l)
        with self.assertRaises(vevents.VeventsError):
            vevents.analyse(text)


class TheSourceSaysWhatTheToolSays(unittest.TestCase):
    def test_an_unclean_frame_inside_an_episode_appends_no_episode_event(self):
        """Issue #120's review: close_frame's branch for a frame that is NOT clean while an episode is open lengthens
        the episode and appends nothing but a cap close -- so the store counts clean frames, not frames."""
        src = read(os.path.join(ROOT, "src", "gbp", "gbp_vstate.c"))
        i = src.index("    } else if (s->episode_open) {")
        branch = src[i:src.index("\n    }\n", i)]
        self.assertIn("ep->frames++;", branch)
        self.assertNotIn("GBP_VSTATE_EV_EPISODE_STABILISING", branch)
        self.assertEqual(branch.count("gbp_vstate_event("), 1)
        self.assertIn("GBP_VSTATE_EV_EPISODE_CLOSE", branch)
        self.assertIn("if (clean) {", src[src.index("    if (clean) {") - 1:i])

    def test_one_stabilising_event_per_clean_frame_while_an_episode_is_open(self):
        src = read(os.path.join(ROOT, "src", "gbp", "gbp_vstate.c"))
        m = re.search(r"static void run_episodes\([^;{]*\)\s*\{", src)          # the definition, not a prototype
        body = src[m.start():]
        body = body[:body.index("\n}\n")]
        self.assertEqual(body.count("GBP_VSTATE_EV_EPISODE_STABILISING"), 2)     # the repeat and the change: each frame
        self.assertIn("ep->frames++;", body)
        self.assertIn("#define GBP_VSTATE_N_STABLE           3u", read(os.path.join(ROOT, "src", "gbp", "gbp_vstate.h")))

    def test_the_carried_design_comment_is_what_it_is(self):
        m = read(os.path.join(ROOT, "poc", "gbp-audio-sync", "source", "main.c"))
        self.assertIn("so ~4 events/s is the ceiling", m)
        self.assertIn("#define PLAY_EVENT_RECORDS       16384u", m)
        self.assertIn("_Static_assert(PLAY_EVENT_RECORDS >= PLAY_SAFETY_SECONDS * 4u,", m)
        self.assertIn("#define PLAY_SAFETY_SECONDS      785u", m)


class TheRuns(unittest.TestCase):
    def run_of(self, n):
        """RUN 41-43 are VERSIONED fixtures and are opened unconditionally: a missing one fails. Only RUN 21 and
        RUN 22, which live in the ignored captures/local/, may skip."""
        p = RUNS[n]
        if p.startswith(LOCAL + os.sep) and not os.path.isfile(p):
            self.skipTest("RUN %d is not archived in this checkout (captures/local is ignored)" % n)
        return vevents.analyse(read(p))

    def test_run43_the_store_that_stopped_the_run(self):
        r = self.run_of(43)
        self.assertEqual((r["n"], r["dropped"], r["store_full"]), (16384, 5, 1))
        self.assertEqual((r["frames"], r["episodes"], r["stable"], r["unstable"]), (14912, 1311, 1210, 101))
        self.assertEqual(r["capture_s"], 249.734)
        self.assertEqual(round(r["per_s"], 2), 65.61)
        self.assertEqual(round(r["per_frame"], 4), 1.0987)
        self.assertEqual(round(r["omitted"]["per_s"], 2), 65.67)
        self.assertEqual(r["head"]["types"]["episode_stabilising"], 97)
        self.assertEqual(r["tail"]["types"], {"episode_close": 5, "episode_open": 5, "episode_stabilising": 50,
                                              "episode_stable": 4})
        self.assertEqual(r["disagreements"], 0)
        self.assertEqual(round(r["permits_s"]["measured"], 1), 249.7)
        self.assertEqual(round(r["permits_s"]["one_per_frame"], 1), 274.3)
        self.assertEqual(round(r["permits_s"]["episode_ceiling"], 1), 164.6)
        self.assertEqual(r["episode_frames_at_least"], {"records": 13794, "other_at_most": 69})

    def test_run43_frames_inside_an_episode_without_a_record(self):
        """The printed head shows it: episode 1 ran 18 frames and holds 12 open/stabilising records, episode 2 ran 60
        and holds 54 -- the missing frames are the unclean ones the branch above lets through silently."""
        text = read(RUNS[43])
        frames = dict((int(m.group(1)), int(m.group(2)))
                      for m in re.finditer(r"^\d{6} EPISODE i=(\d+) idx=[0-9a-f]+ state=\w+ flags=[0-9a-f]+ frames=(\d+)",
                                           text, re.M))
        recs = {}
        for m in re.finditer(r"^\d{6} EV seq=(\d+) t=[0-9a-f]+ type=(episode_open|episode_stabilising) f=\d+ "
                             r"ep=([0-9a-f]+)", text, re.M):
            if int(m.group(1)) <= 128:
                recs[int(m.group(3), 16)] = recs.get(int(m.group(3), 16), 0) + 1
        self.assertEqual((frames[0], recs[1]), (18, 12))
        self.assertEqual((frames[1], recs[2]), (60, 54))

    def test_run42_and_run41_the_same_cartridge(self):
        r42, r41 = self.run_of(42), self.run_of(41)
        self.assertEqual((r42["n"], r42["store_full"], round(r42["per_s"], 2), round(r42["per_frame"], 4)),
                         (4240, 0, 59.99, 1.005))
        self.assertEqual((r41["n"], r41["store_full"], round(r41["per_s"], 2), round(r41["omitted"]["per_s"], 2)),
                         (2177, 0, 28.93, 61.33))

    def test_run21_and_run22_gbp_hw_282(self):
        r21, r22 = self.run_of(21), self.run_of(22)
        self.assertEqual((r21["n"], r21["dropped"], r21["store_full"], round(r21["per_s"], 2)), (16384, 3, 1, 59.84))
        self.assertEqual((r22["n"], r22["store_full"], round(r22["per_s"], 2)), (11894, 0, 58.88))


if __name__ == "__main__":
    unittest.main()
