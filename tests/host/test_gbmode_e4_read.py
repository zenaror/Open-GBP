"""tests/host/test_gbmode_e4_read.py -- GitHub Issue #151 (PHASE 7's E4, the L / R stretch in GB mode): the reader can say every one of its tokens, and cannot say a yes without a press.

Synthetic strips and KEY lines drive tools/gbmode_e4_read.py through each rival reading (a change while a key is held, a latched change, a toggle that toggles back, nothing, a change
that follows one key only), the by-construction limits (no legible frame, an unsent word, a failed write, another key, an insufficient cell, a partial leak, a refused gate) and a
transition margin. RUN 59's archived sidecars (captures/local, ignored by Git; those tests skip, with the registered reason, on a host without the archive) are the NEGATIVE control -- no
press, no verdict -- and the source of a POSITIVE control on real content: a nearest-neighbour stretch of RUN 59's own sample, applied in memory to its real strips (nothing is stored).
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import gbmode_e4_read as e  # noqa: E402
from test_gbmode_read import make_log  # noqa: E402

HZ = 40500000
P = int(HZ / e.FRAME_HZ)                       # ticks per AGB frame
LOCAL = os.path.join(ROOT, "captures", "local")
COMMIT = "4d6fe06"
SKY = 0x6189


def strip(stretched, lit=True):
    """One frame's 40 blocks x 54 words: the picture inside the rectangle is SKY; outside it the border is black, or SKY when the picture reaches it."""
    w = []
    for b in range(40):
        row = []
        for i in range(54):
            x = 1 + i
            inside = x >= 40 and b not in (0, 1, 38, 39)
            row.append(SKY if lit and (inside or stretched) else 0)
        w.append(row)
    return w


def frames(n, stretched_at, lit_at=lambda i: True, base=10 ** 12):
    out = []
    for i in range(n):
        out.append({"frame_index": 355 + i, "t_first_block": base + i * P, "t_last_block": base + i * P + 1000, "witness": strip(stretched_at(i), lit_at(i))})
    return out


def idx(fr):
    return {"tb_hz": HZ, "records": fr}


def key_line(n, word, i, base=10 ** 12, rc="ok", act="change"):
    t = base + i * P
    return "%06d KEY n=%d act=%s keys=%04x word=%04x t_poll=%x t_attempt=%x t_done=%x xfer=30 rc=%s" % (700 + n, n, act, word >> 8 & 0xFF, word, t - 400, t - 300, t, rc)


def run(fr, events, **kw):
    """events: [(frame offset, word)]; the log carries the idle first record and these."""
    lines = [key_line(1, 0, -5, act="first")] + [key_line(2 + k, w, i) for k, (i, w) in enumerate(events)]
    log = make_log(commit=COMMIT, inp="selftest=1 steps=1 invalid=0 no_base=0 key_changes=%d attempts=7800 completed=7800 failed=0 first=1 change=%d refresh=7799 retry=0 last_word=0000 last_rc=ok" % (len(events), len(events)),
                   extra="\n".join(lines))
    return e.read(log, idx(fr), "gbmode-0001", COMMIT, None) if not kw else e.read(make_log(commit=COMMIT, **kw), idx(fr), "gbmode-0001", COMMIT, None)


L, R = e.L_BIT, e.R_BIT


class TheReaderSaysWhichRivalReadingMatches(unittest.TestCase):
    def test_a_change_only_while_L_is_held(self):
        # L down at frame offset 100, up at 300; the delivered frames carry the change from 103 to 303 (a lag of 3 frames)
        o = run(frames(500, lambda i: 103 <= i < 303), [(100, L), (300, 0)])
        self.assertEqual(o["verdict"], "CHANGED")
        self.assertEqual(o["cells"]["L|after:"]["verdict"], "STRETCHED")
        self.assertEqual(o["cells"]["-|after:L"]["verdict"], "NOT_STRETCHED")
        self.assertEqual(o["cells"]["-|after:"]["verdict"], "NOT_STRETCHED")
        self.assertEqual(o["consistent_models"], ["L_MOMENTARY"], "only L was sent: no reading about R is listed")

    def test_a_change_that_stays_after_release(self):
        o = run(frames(500, lambda i: i >= 103), [(100, L), (300, 0)])
        self.assertEqual(o["verdict"], "CHANGED")
        self.assertEqual((o["cells"]["L|after:"]["verdict"], o["cells"]["-|after:L"]["verdict"]), ("STRETCHED", "STRETCHED"))
        self.assertEqual(o["consistent_models"], ["L_LATCH", "L_TOGGLE"])

    def test_a_toggle_that_toggles_back_on_the_second_press_is_told_from_a_latch(self):
        ev = [(100, L), (200, 0), (300, L), (400, 0)]
        toggle = frames(600, lambda i: 103 <= i < 303)                       # on with the first press, off with the second
        o = run(toggle, ev)
        self.assertEqual(o["cells"]["L|after:"]["verdict"], "STRETCHED")
        self.assertEqual(o["cells"]["L|after:L"]["verdict"], "NOT_STRETCHED")
        self.assertIn("L_TOGGLE", o["consistent_models"])
        self.assertNotIn("L_LATCH", o["consistent_models"])
        self.assertNotIn("L_MOMENTARY", o["consistent_models"])

    def test_the_change_follows_only_R(self):
        ev = [(100, L), (200, 0), (300, R), (400, 0)]
        o = run(frames(600, lambda i: i >= 303), ev)
        self.assertEqual(o["cells"]["L|after:"]["verdict"], "NOT_STRETCHED")
        self.assertEqual(o["cells"]["R|after:L"]["verdict"], "STRETCHED")
        self.assertEqual(o["consistent_models"], ["R_LATCH", "R_TOGGLE"])

    def test_nothing_changes_and_the_verdict_says_what_it_cannot_say(self):
        ev = [(100, L), (200, 0), (300, R), (400, 0)]
        o = run(frames(600, lambda i: False), ev)
        self.assertEqual(o["verdict"], "NOT_CHANGED_REACH_NOT_SHOWN")
        self.assertEqual(o["consistent_models"], ["NOTHING"])
        self.assertIn("the word never reached the AGB", e.render(o))

    def test_a_press_with_no_legible_frame_is_inconclusive_not_a_no(self):
        o = run(frames(500, lambda i: False, lit_at=lambda i: False), [(100, L), (300, 0)])
        self.assertEqual(o["verdict"], "INCONCLUSIVE_NOT_LEGIBLE")
        self.assertEqual(o["legible"], 0)

    def test_frames_that_are_legible_only_before_the_press_cannot_say_no(self):
        o = run(frames(500, lambda i: False, lit_at=lambda i: i < 90), [(100, L), (300, 0)])
        self.assertEqual(o["verdict"], "INCONCLUSIVE_NOT_LEGIBLE")

    def test_no_L_R_word_is_no_verdict(self):
        o = run(frames(500, lambda i: True), [])
        self.assertEqual(o["verdict"], "NO_LR_WORD_SENT")
        self.assertEqual(o["presses"], [])

    def test_a_failed_write_is_not_a_press(self):
        lines = [key_line(1, 0, -5, act="first"), key_line(2, L, 100, rc="timeout"), key_line(3, 0, 300, rc="timeout")]
        log = make_log(commit=COMMIT, extra="\n".join(lines))
        o = e.read(log, idx(frames(500, lambda i: True)), "gbmode-0001", COMMIT, None)
        self.assertEqual((o["verdict"], o["keys_failed"], o["presses"]), ("NO_LR_WORD_SENT", 2, []))

    def test_any_other_key_is_a_recorded_deviation(self):
        o = run(frames(500, lambda i: False), [(100, L | 0x0001), (150, L), (300, 0)])
        self.assertEqual(o["other_keys"], [0x0001])
        self.assertIn("other KEYPAD bits written: 0x0001", e.render(o))

    def test_a_cell_of_too_few_frames_is_insufficient_and_the_verdict_is_partial(self):
        o = run(frames(420, lambda i: False, lit_at=lambda i: 90 <= i < 170 or 240 <= i < 420), [(100, L), (110, 0), (200, R), (340, 0)])
        self.assertEqual(o["cells"]["-|after:L"]["verdict"], "INSUFFICIENT")          # 30 legible frames between the margins
        self.assertEqual(o["cells"]["R|after:L"]["verdict"], "NOT_STRETCHED")
        self.assertNotIn("L|after:", o["cells"], "L's own held frames are all transition frames")
        self.assertEqual(o["verdict"], "PARTIAL", "L was sent but no held-L cell was evaluable: never a clean NOT_CHANGED")

    def test_a_partial_leak_is_counted_and_never_classified_as_a_stretch(self):
        fr = frames(500, lambda i: False)
        for i in range(120, 260):                                            # 3 outside words lit: a 0.2 % leak, below the partial line
            fr[i]["witness"][5][0] = SKY
        o = run(fr, [(100, L), (300, 0)])
        self.assertEqual(o["leak_frames"], 0)
        fr2 = frames(500, lambda i: False)
        for i in range(120, 260):                                            # ~10 % leak
            for b in range(4, 20):
                for x in range(0, 10):
                    fr2[i]["witness"][b][x] = SKY
        o2 = run(fr2, [(100, L), (300, 0)])
        self.assertGreater(o2["partial_leak_frames"], 100)
        self.assertEqual(o2["leak_frames"], 0)
        self.assertNotEqual(o2["cells"]["L|after:"]["verdict"], "STRETCHED")
        self.assertEqual(o2["cells"]["L|after:"]["verdict"], "MIXED")

    def test_frames_within_the_margin_of_a_change_are_excluded(self):
        o = run(frames(400, lambda i: 103 <= i < 203), [(100, L), (200, 0)])
        self.assertGreater(o["transition_frames"], 50)
        self.assertLessEqual(o["cells"]["L|after:"]["n"], 100 - e.MARGIN_FRAMES)
        self.assertGreaterEqual(o["cells"]["L|after:"]["n"], 100 - 2 * e.MARGIN_FRAMES - 2)

    def test_a_refused_gate_makes_the_run_inadmissible_whatever_the_frames_show(self):
        lines = [key_line(1, 0, -5, act="first"), key_line(2, L, 100), key_line(3, 0, 300)]
        log = make_log(commit="deadbee", extra="\n".join(lines))
        o = e.read(log, idx(frames(500, lambda i: 103 <= i < 303)), "gbmode-0001", COMMIT, None)
        self.assertEqual(o["verdict"], "INADMISSIBLE")


class TheReviewsHolesAreClosed(unittest.TestCase):
    """Issue #151's adversarial review: each case below was a false reading before it was fixed."""

    def test_a_change_of_the_height_alone_shows_only_in_the_border_rows_and_is_found(self):
        fr = frames(500, lambda i: False)
        for i in range(103, 500):
            for b in (0, 1, 38, 39):
                for x in range(39, 54):
                    fr[i]["witness"][b][x] = SKY                             # the picture reaches the border ROWS: 60 words, 3.7 % of the 1 620
        o = run(fr, [(100, L), (400, 0)])
        self.assertEqual(o["cells"]["L|after:"]["verdict"], "STRETCHED")
        self.assertEqual(o["verdict"], "CHANGED")

    def test_border_rows_below_half_are_partial_not_a_stretch(self):
        fr = frames(500, lambda i: False)
        for i in range(103, 500):
            for b in (0, 1):
                for x in range(39, 54):
                    fr[i]["witness"][b][x] = SKY                             # 30 of 60 -> exactly the line: a stretch; 29 would be partial
        o1 = run(fr, [(100, L), (400, 0)])
        self.assertEqual(o1["verdict"], "CHANGED")
        fr2 = frames(500, lambda i: False)
        for i in range(103, 500):
            for b in (0, 1):
                for x in range(39, 53):
                    fr2[i]["witness"][b][x] = SKY                            # 28 of 60
        o2 = run(fr2, [(100, L), (400, 0)])
        self.assertEqual(o2["leak_frames"], 0)
        self.assertGreater(o2["partial_leak_frames"], 100)
        self.assertNotEqual(o2["verdict"], "CHANGED")

    def test_the_edge_blocks_are_0_1_38_39_and_the_flag_bit_alone_is_black(self):
        for blocks in ((38, 39), (1, 38), (0, 39)):
            fr = frames(500, lambda i: False)
            for i in range(103, 500):
                for b in blocks:
                    for x in range(39, 54):
                        fr[i]["witness"][b][x] = SKY
            self.assertEqual(run(fr, [(100, L), (400, 0)])["verdict"], "CHANGED", blocks)
        fr = frames(500, lambda i: False)
        for i in range(103, 500):
            for b in range(40):
                for x in range(0, 39):
                    fr[i]["witness"][b][x] = 0x8000                          # the flag bit alone: black in the 15-bit reading
        o = run(fr, [(100, L), (400, 0)])
        self.assertEqual((o["leak_frames"], o["partial_leak_frames"]), (0, 0))
        self.assertEqual(e.frame_stats(strip(False))[1:], (0, 0))
        self.assertEqual(e.frame_stats(strip(True))[1:], (1560, 60))

    def test_a_press_that_ends_exactly_at_a_frame_time_belongs_to_the_press_it_completes(self):
        ps = e.presses([(100, 1, 0), (200, 0, 0)])
        self.assertEqual(e.cell_of(200, [(100, 1, 0), (200, 0, 0)], ps), "-|after:L")
        self.assertEqual(e.cell_of(199, [(100, 1, 0), (200, 0, 0)], ps), "L|after:")

    def test_a_transient_change_inside_the_margins_blocks_a_not_changed(self):
        fr = frames(600, lambda i: False)
        for i in range(101, 121):                                            # 20 frames after the press, all inside the 30-frame margin
            fr[i]["witness"] = strip(True)
        o = run(fr, [(100, L), (300, 0)])
        self.assertGreater(o["stray_leak_frames"], 0)
        self.assertEqual(o["verdict"], "PARTIAL")
        self.assertNotEqual(o["verdict"], "NOT_CHANGED_REACH_NOT_SHOWN")

    def test_a_change_present_before_any_press_is_not_attributed_to_a_press(self):
        fr = frames(500, lambda i: True)                                     # stretched from the first frame, the press changes nothing
        o = run(fr, [(100, L), (300, 0)])
        self.assertGreater(o["pre_press_leak_frames"], 0)
        self.assertEqual(o["verdict"], "BASELINE_NOT_CLEAN")

    def test_a_key_held_together_with_the_other_evaluates_neither_alone(self):
        o = run(frames(600, lambda i: False), [(100, L), (150, L | R), (400, L), (450, 0)])
        self.assertIn("LR|after:", o["cells"])
        self.assertNotEqual(o["verdict"], "NOT_CHANGED_REACH_NOT_SHOWN" if "R|after:" not in o["cells"] else "x")

    def test_only_the_readings_about_the_keys_sent_are_listed(self):
        o = run(frames(500, lambda i: False), [(100, L), (300, 0)])
        self.assertEqual(o["consistent_models"], ["NOTHING"])
        self.assertEqual(e.models_for(["R"]), ["NOTHING", "R_MOMENTARY", "R_LATCH", "R_TOGGLE"])
        self.assertEqual(e.models_for(["L", "R"]), list(e.MODELS))

    def test_a_mixed_cell_beside_a_not_stretched_one_is_partial(self):
        fr = frames(700, lambda i: False)
        for i in range(140, 190):                                            # inside the L hold: half of its frames leak
            fr[i]["witness"] = strip(True)
        o = run(fr, [(100, L), (300, 0), (400, R), (600, 0)])
        self.assertEqual(o["cells"]["L|after:"]["verdict"], "MIXED")
        self.assertEqual(o["cells"]["R|after:L"]["verdict"], "NOT_STRETCHED")
        self.assertEqual(o["verdict"], "PARTIAL")

    def test_the_cell_thresholds_are_the_registered_ones(self):
        self.assertEqual((e.CELL_STRETCHED, e.CELL_NOT, e.LEAK_X_STRETCHED, e.LEAK_Y_STRETCHED, e.LEAK_X_PARTIAL, e.LEAK_Y_PARTIAL), (0.90, 0.02, 0.25, 0.50, 0.01, 0.10))
        # a cell at exactly 90 % leak frames is STRETCHED, at 89 % it is MIXED; at exactly 2 % it is NOT_STRETCHED, above it MIXED
        cf = [{"legible": True, "transition": False, "cell": "L|after:", "strong": i < 90, "partial": False} for i in range(100)]
        self.assertEqual(e.cells_of(cf)["L|after:"]["verdict"], "STRETCHED")
        cf = [{"legible": True, "transition": False, "cell": "L|after:", "strong": i < 89, "partial": False} for i in range(100)]
        self.assertEqual(e.cells_of(cf)["L|after:"]["verdict"], "MIXED")
        cf = [{"legible": True, "transition": False, "cell": "L|after:", "strong": i < 2, "partial": False} for i in range(100)]
        self.assertEqual(e.cells_of(cf)["L|after:"]["verdict"], "NOT_STRETCHED")
        cf = [{"legible": True, "transition": False, "cell": "L|after:", "strong": i < 3, "partial": False} for i in range(100)]
        self.assertEqual(e.cells_of(cf)["L|after:"]["verdict"], "MIXED")
        cf = [{"legible": True, "transition": False, "cell": "L|after:", "strong": False, "partial": i < 3} for i in range(100)]
        self.assertEqual(e.cells_of(cf)["L|after:"]["verdict"], "MIXED", "more than 2 % partial frames keep a cell from NOT_STRETCHED")

    def test_the_border_columns_alone_are_a_stretch_when_a_quarter_of_them_light_up(self):
        fr = frames(500, lambda i: False)
        for i in range(103, 500):
            for b in range(40):
                for x in range(0, 10):                                       # 400 of the 1 560 border-column words = 25.6 %
                    fr[i]["witness"][b][x] = SKY
        self.assertEqual(run(fr, [(100, L), (400, 0)])["verdict"], "CHANGED")
        fr2 = frames(500, lambda i: False)
        for i in range(103, 500):
            for b in range(40):
                for x in range(0, 9):                                        # 360 = 23 %: partial
                    fr2[i]["witness"][b][x] = SKY
        o = run(fr2, [(100, L), (400, 0)])
        self.assertEqual(o["leak_frames"], 0)
        self.assertNotEqual(o["verdict"], "CHANGED")

    def test_frames_of_the_expected_windows_that_go_dark_after_the_first_press_are_reported(self):
        fr = frames(2100, lambda i: False, lit_at=lambda i: False)
        o = run(fr, [(100, L), (300, 0)])
        self.assertEqual(o["verdict"], "INCONCLUSIVE_NOT_LEGIBLE")
        self.assertEqual(o["expected_window_frames_dark"], o["expected_window_frames_after_first_press"])
        self.assertGreater(o["expected_window_frames_dark"], 500)
        self.assertIn("NOT separable", e.render(o))


class TheArchivedRunIsTheNegativeControlAndTheSourceOfAPositiveOne(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = os.path.join(LOCAL, "GBP-VIDEO-004_gbmode-0001-run59.log")
        cls.idx = os.path.join(LOCAL, "GBP-VIDEO-004_gbmode-0001-run59-idxcap.bin")
        cls.full = os.path.join(LOCAL, "GBP-VIDEO-004_gbmode-0001-run59-full.bin")
        if not all(os.path.isfile(p) for p in (cls.log, cls.idx, cls.full)):
            raise unittest.SkipTest("no local archive on this host (captures/local is ignored)")
        import vidxcap
        with open(cls.log, encoding="utf-8", errors="replace") as f:
            cls.text = f.read()
        cls.info = vidxcap.load(cls.idx)

    def test_run_59_has_no_press_no_leak_and_no_verdict(self):
        o = e.read(self.text, self.info, "gbmode-0001", COMMIT, None)
        self.assertEqual(o["verdict"], "NO_LR_WORD_SENT")
        self.assertEqual((o["frames"], o["legible"], o["leak_frames"], o["partial_leak_frames"]), (2048, 577, 0, 0))
        self.assertEqual(o["consistent_models"], ["NOTHING"], "no key was sent: only the reading that needs no press is listed")
        self.assertEqual(o["cells"]["-|after:"], {"n": 577, "leak": 0, "partial": 0, "verdict": "NOT_STRETCHED"})

    def test_the_legible_windows_of_run_59(self):
        import gbmode_e4_read as g
        legible = []
        for rec in self.info["records"]:
            inbox, _lx, _ly = g.frame_stats(rec["witness"])
            legible.append(inbox / float(g.INBOX_WORDS) >= g.LEGIBLE_MIN)
        wins, cur = [], None
        for i, ok in enumerate(legible):
            if ok and cur is None:
                cur = [355 + i, 355 + i]
            elif ok:
                cur[1] = 355 + i
            elif cur:
                wins.append(tuple(cur))
                cur = None
        if cur:
            wins.append(tuple(cur))
        self.assertEqual(wins, [(355, 373), (1192, 1321), (1622, 1918), (2245, 2375)])

    def test_a_stretch_of_the_real_sample_is_found_in_the_real_strips_in_memory(self):
        """POSITIVE control on real content: samples 5's own 160 x 144 picture, nearest-neighbour stretched to 240 x 160, gives the strips a stretched window would carry."""
        import copy
        import gbmode_picture
        import vfull
        px = gbmode_picture.pixels(vfull.load(self.full)["records"][5]["raw"])
        pic = [row[40:200] for row in px[8:152]]
        big = [[pic[min(143, (y * 144) // 160)][min(159, (x * 160) // 240)] for x in range(240)] for y in range(160)]
        stretched = [[big[4 * b][x] for x in range(1, 55)] for b in range(40)]
        recs = copy.deepcopy(self.info["records"])
        first = next(r for r in recs if 1622 <= r["frame_index"] <= 1918)
        t_down = recs[1750 - 355]["t_first_block"]
        t_up = recs[1900 - 355]["t_first_block"]
        for r in recs:
            if 1750 <= r["frame_index"] < 1900:
                r["witness"] = copy.deepcopy(stretched)
        lines = ["000700 KEY n=1 act=first keys=0000 word=0000 t_poll=%x t_attempt=%x t_done=%x xfer=30 rc=ok" % (first["t_first_block"] - 9, first["t_first_block"] - 8, first["t_first_block"] - 7),
                 "000701 KEY n=2 act=change keys=0000 word=%04x t_poll=%x t_attempt=%x t_done=%x xfer=30 rc=ok" % (e.L_BIT, t_down - 9, t_down - 8, t_down),
                 "000702 KEY n=3 act=change keys=0000 word=0000 t_poll=%x t_attempt=%x t_done=%x xfer=30 rc=ok" % (t_up - 9, t_up - 8, t_up)]
        text = self.text + "\n".join(lines) + "\n"
        info = dict(self.info)
        info["records"] = recs
        o = e.read(text, info, "gbmode-0001", COMMIT, None)
        self.assertEqual(o["cells"]["L|after:"]["verdict"], "STRETCHED")
        self.assertEqual(o["verdict"], "CHANGED")
        self.assertGreater(o["cells"]["L|after:"]["leak"], 80)
        self.assertIn("L_MOMENTARY", o["consistent_models"])

    def test_the_samples_are_placed_in_their_cells_by_time(self):
        import vfull
        o = e.read(self.text, self.info, "gbmode-0001", COMMIT, vfull.load(self.full))
        self.assertEqual([s["cell"] for s in o["samples"]], ["-|after:"] * 8)
        self.assertEqual([s["bbox"] for s in o["samples"]][0], (40, 8, 199, 151))


if __name__ == "__main__":
    unittest.main()
