"""tests/host/test_v28budget.py -- GitHub Issue #122: tools/v28budget.py, the next sync session's budget in events and
in the seconds they buy, beside the phase budget and the memory that pays for both. DESCRIPTIVE arithmetic; it sets no
size.

On constructions: a record count is rounded UP; the free arena is arena1_hi less bss_end + the framebuffers rounded up
to a page, and reproduces RUN 43's own ENVMEM exactly; a store option spends the arena down to the heap floor and no
further; a wall's ceiling keeps the floor with both stores at their guards' rates. From the RECORDS: the floor is
GBP-HW-262's, the caps and the wall are the image's. Then RUN 43's figures are pinned: the rate, the spans, the records
they need, the phases, the session plans each with its own session cap, the wall ceilings, and what each store
option buys.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v28budget  # noqa: E402


def read(p):
    with open(os.path.join(ROOT, p), encoding="utf-8", errors="replace") as f:
        return f.read()


def section(text, heading):
    i = text.index(heading)
    j = text.find("\n### ", i + 1)
    return text[i:j if j >= 0 else len(text)]


class OnConstructions(unittest.TestCase):
    F = {"arena1_hi": 0x100000, "bss_end": 0x10000, "xfb_bytes": 0x1000, "event_record": 64, "event_bytes": 6400,
         "frame_record": 192, "frame_bytes": 19200, "awr_bytes": 8192, "rate": 60.0}

    def test_a_count_is_rounded_up(self):
        self.assertEqual(v28budget.need(10.0, 6.0), 60)
        self.assertEqual(v28budget.need(10.0, 6.01), 61)

    def test_the_arena_is_page_rounded(self):
        f = self.F
        self.assertEqual(v28budget.free_arena(f, 100, 100, True), 0x100000 - 0x11000)
        self.assertEqual(v28budget.free_arena(f, 101, 100, True), 0x100000 - 0x12000)     # 64 B more: a page less
        self.assertEqual(v28budget.free_arena(f, 100, 100, False), 0x100000 - 0x11000 + 8192)

    def test_an_option_stops_at_the_floor(self):
        f = dict(self.F, arena1_hi=0x11000 + v28budget.HEAP_FLOOR + 40000)
        n = v28budget.largest_events(f, 100, True)
        self.assertGreaterEqual(v28budget.free_arena(f, n, 100, True), v28budget.HEAP_FLOOR)
        self.assertLess(v28budget.free_arena(f, n + 1, 100, True), v28budget.HEAP_FLOOR)
        self.assertTrue(v28budget.option(f, n, 100, True)["floor_kept"])

    def test_the_largest_store_is_found_when_the_first_estimate_undershoots(self):
        # bss_end not page-aligned and arena1_hi - floor page-aligned: an empty store wastes most of a page that a
        # larger one uses again, so the estimate from the empty store is short (RUN 43's case: 13 records)
        f = dict(self.F, bss_end=0x10CB8, arena1_hi=0x20000 + v28budget.HEAP_FLOOR // 4096 * 4096 + 4096)
        n = v28budget.largest_events(f, 100, True)
        self.assertGreater(n, (v28budget.free_arena(f, 0, 100, True) - v28budget.HEAP_FLOOR) // 64)
        self.assertGreaterEqual(v28budget.free_arena(f, n, 100, True), v28budget.HEAP_FLOOR)
        self.assertLess(v28budget.free_arena(f, n + 1, 100, True), v28budget.HEAP_FLOOR)


class TheRecords(unittest.TestCase):
    def test_the_floor_is_gbp_hw_262_s(self):
        self.assertIn("`ENVFULL arena1_free=1650688`", section(read("docs/research/EVIDENCE.md"), "### GBP-HW-262 "))
        self.assertEqual(v28budget.HEAP_FLOOR, 1650688)

    def test_the_wall_the_latest_origin_and_the_frame_guard_are_the_image_s(self):
        m = read("poc/gbp-audio-sync/source/main.c")
        self.assertIn("#define PLAY_SAFETY_SECONDS      785u", m)
        self.assertIn("origin <= 0.11 + 5 + 45 + 1 = 51.11 s", m)
        self.assertIn("_Static_assert(PLAY_FRAME_RECORDS >= PLAY_SAFETY_SECONDS * 60u,", m)
        self.assertEqual((v28budget.WALL_S, v28budget.GUARD_FRAMES_PER_S), (785, 60))


class Run43(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = v28budget.analyse(read(os.path.relpath(v28budget.RUN43, ROOT)))

    def test_the_facts(self):
        f = self.r["facts"]
        self.assertAlmostEqual(self.r["rates"]["measured"], 16384 / 249.734, places=9)
        self.assertEqual((f["arena1_free"], f["event_bytes"], f["event_record"], f["frame_bytes"], f["frame_record"],
                          f["awr_bytes"], f["xfb_bytes"]), (2269184, 1048576, 64, 9043968, 192, 2621440, 1843200))
        self.assertEqual(f["caps"], {"p1": 300, "p2": 240, "p3": 180, "session": 720})
        self.assertEqual((round(f["capture_after_control_s"], 3), round(f["origin_s"], 2)), (0.108, 7.56))
        self.assertEqual(self.r["guard_events_per_s"], 79)

    def test_the_page_rounded_arena_is_run43_s_own(self):
        o = self.r["options"]["today"]
        self.assertEqual(o["arena1_left"], self.r["facts"]["arena1_free"])
        self.assertEqual(self.r["facts"]["arena1_hi"] - self.r["facts"]["arena1_lo"], 2269184)

    def test_the_spans_and_what_they_need(self):
        s = dict((k, round(v, 2)) for k, v in self.r["spans_s"].items())
        self.assertEqual(s, {"capture_start_to_origin": 7.56, "run43_origin_plus_session": 727.56,
                             "latest_origin_plus_session": 771.0, "wall": 784.89})
        n = self.r["needed"]
        self.assertEqual([n[k]["measured"] for k in ("capture_start_to_origin", "run43_origin_plus_session",
                                                     "latest_origin_plus_session", "wall")], [497, 47733, 50583, 51494])
        self.assertEqual((n["wall"]["margin"], n["wall"]["one_per_frame"], n["wall"]["episode_ceiling"]),
                         (61793, 46880, 78133))

    def test_the_phases(self):
        p = dict((x["phase"], x) for x in self.r["phases"])
        self.assertEqual([round(p[k]["run43_s"], 2) for k in ("p0", "p1", "p2")], [38.47, 149.18, 54.52])
        self.assertEqual([p[k]["records_at_cap"]["measured"] for k in ("p1", "p2", "p3", "p3b")],
                         [19682, 15746, 11810, 3937])
        self.assertEqual(p["p3b"]["records_at_cap"]["margin"], 4724)
        self.assertIsNone(p["p0"]["cap_s"])

    def test_the_plans(self):
        pl = self.r["plans"]
        got = dict((k, (round(v["sum_s"], 2), v["cap_s"], round(v["slack_s"], 2), v["wall_s"], v["records"]["measured"],
                        v["records"]["margin"])) for k, v in pl.items())
        self.assertEqual(got, {"v27_as_frozen": (758.47, 720, -38.47, 785, 50583, 60699),
                               "v27_with_3b": (776.47, 720, -56.47, 785, 50583, 60699),
                               "validation_run": (378, 438, 60, 503, 32082, 38498),
                               "perceptual_no_phase1": (300, 360, 60, 425, 26965, 32357),
                               "perceptual_phase1": (520, 580, 60, 645, 41398, 49677),
                               "one_session_descent_first": (618, 678, 60, 743, 47827, 57393)})
        # the stores at each wall, against the floor, with and without the ride-along's raw store
        floor = dict((k, (v["awr_kept"]["floor_kept"], v["awr_dropped"]["floor_kept"])) for k, v in pl.items())
        self.assertEqual(floor, {"v27_as_frozen": (False, True), "v27_with_3b": (False, True),
                                 "validation_run": (True, True), "perceptual_no_phase1": (True, True),
                                 "perceptual_phase1": (True, True), "one_session_descent_first": (False, True)})
        self.assertEqual(pl["perceptual_phase1"]["awr_kept"]["above_floor"], 16384)       # one wall-second from the edge
        self.assertEqual((pl["v27_as_frozen"]["events"], pl["v27_as_frozen"]["frames"]), (62015, 47100))

    def test_the_wall_ceilings(self):
        self.assertEqual(self.r["wall_ceiling_s"], {"awr_kept": 646, "awr_dropped": 804})

    def test_the_options(self):
        o = self.r["options"]
        self.assertEqual([o[k]["events"] for k in ("today", "largest_awr_kept", "largest_awr_dropped",
                                                   "wall785_awr_dropped")], [16384, 26061, 67021, 62015])
        self.assertEqual(o["wall785_awr_dropped"]["arena1_left"], 1970176)
        self.assertEqual([(o[k]["units"], o[k]["units_with_label"]) for k in ("today", "wall785_awr_dropped")],
                         [(8, 7), (4, 3)])
        self.assertTrue(all(x["floor_kept"] for x in o.values()))
        # the largest stores sit exactly on the floor, and one record more breaks it
        f = self.r["facts"]
        for k, kept in (("largest_awr_kept", True), ("largest_awr_dropped", False)):
            self.assertEqual(o[k]["arena1_left"], v28budget.HEAP_FLOOR)
            self.assertLess(v28budget.free_arena(f, o[k]["events"] + 1, 47104, kept), v28budget.HEAP_FLOOR)
        # with the ride-along kept, no event store that fits reaches the session at the measured rate
        self.assertLess(o["largest_awr_kept"]["events"], self.r["needed"]["run43_origin_plus_session"]["measured"])
        # the 785 s store outlasts its wall at the guard's margin, and not at the episode path's ceiling
        self.assertGreater(o["wall785_awr_dropped"]["seconds"]["margin"], self.r["spans_s"]["wall"])
        self.assertLess(o["wall785_awr_dropped"]["seconds"]["episode_ceiling"], self.r["spans_s"]["wall"])
        self.assertEqual(round(o["wall785_awr_dropped"]["seconds"]["measured"], 1), 945.3)


if __name__ == "__main__":
    unittest.main()
