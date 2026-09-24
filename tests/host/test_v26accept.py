"""
tests/host/test_v26accept.py — §V26's gates (tools/v26accept.py, GitHub Issue #113), on synthetic vectors only,
before the image exists.

Pinned: v26accept is v25accept with ONE function replaced -- V's start-up clause -- and restores it after every
call; the rebuilt clause admits RUN 40's case (13, no press frame) and RUN 39's (13 + the frame in flight at the
press) and nothing else: not a frame one later, not 12 + press + one elsewhere, not 12 + press, not a thirteenth
beyond the start-up span, not a frame after the AI; P's boundaries are structural (t_first <= t_press < t_next);
an early press, a missing bound, an incomplete list are INCONCLUSIVE; the rate half is §V25.10's integers.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import v22accept  # noqa: E402
import v25accept  # noqa: E402
import v26accept as v  # noqa: E402

TB = 40500000
FRAME = 678000                    # ~16.74 ms in ticks
T0 = 10 ** 9
SIG = [1, 10, 13, 16, 32, 35, 38, 92, 95, 98, 152, 155, 158]      # GBP-HW-331's positions, store indices
PRESS_IDX = 612
AI0 = T0 + 700 * FRAME


def frame(idx, blocks_lost_at_end=False):
    """[store index, t_first_block, t_last_block, t_first_block of the next frame]"""
    first = T0 + idx * FRAME
    last = first + (FRAME * 30 // 40 if blocks_lost_at_end else FRAME * 39 // 40)
    return [idx, first, last, first + FRAME]


def t_press_in(idx, offset=FRAME // 4):
    return T0 + idx * FRAME + offset


def report(before_idx=SIG, press_idx=None, t_press=None, after=0, inside=12, bound=197, capped=False,
           listed=None, ai_ticks=2566709992, **over):
    frames = [frame(i) for i in sorted(set(before_idx) | ({press_idx} if press_idx is not None else set()))]
    if listed is not None:
        frames = frames[:listed]
    n = len(set(before_idx) | ({press_idx} if press_idx is not None else set()))
    r = {"test_id": "GBP-AUDIO-011", "build_id": "synthetic", "commit": "0000000",
         "window_opened": True, "phase_reached": "done",
         "presses": {"a": 5, "other": 30}, "presses_after": 0, "press_before_prompt": False,
         "t_press": t_press if t_press is not None else t_press_in(PRESS_IDX),
         "window": {"ticks": 64 * TB, "coverage": [4088] * 64, "l": {"periods": 1, "pmin": 1, "pmax": 1},
                    "not_drained": 8 * 64, "overflow": 0, "underrun": 0, "fill": [2000] * 64,
                    "corrections": {"dup": 1500, "drop": 0}},
         "m": {"callbacks": 2031, "t_first": AI0, "t_last": AI0 + 2030 * 1264500, "frames_per_callback": 1000},
         "calibration": {"rest_sum": 4096 * 16384, "rest_n": 4096, "pmin": 16380, "pmax": 16388},
         "clipped": 0,
         "video": {"framecap_incomplete": n + inside + after, "stored": n + inside + after, "store_full": 0,
                   "before": n, "inside": inside, "after": after, "per_second": [0] * 64,
                   "t_ai_start": AI0, "t_ai_stop": AI0 + ai_ticks,
                   "before_frames": frames, "before_listed": len(frames), "before_capped": capped,
                   "episodes_close_max": bound},
         "l2_sidecar": "present"}
    for k, val in over.items():
        sect, _, key = k.partition("__")
        if key:
            r[sect][key] = val
        else:
            r[sect] = val
    return r


def verdict(r):
    return v.video_clause(r)["verdict"]


class TheModuleIsV25WithOneFunctionReplaced(unittest.TestCase):
    def test_it_redefines_only_the_video_clause(self):
        own = {n for n, o in vars(v).items() if callable(o) and getattr(o, "__module__", None) == "v26accept"}
        self.assertEqual(own, {"video_clause", "evaluate", "main", "_Replaced"})
        with open(os.path.join(ROOT, "tools", "v26accept.py"), encoding="utf-8") as f:
            src = f.read()
        for name in ("question_L2", "question_C", "question_A", "question_R", "question_V", "check_declaration"):
            self.assertNotIn("def %s" % name, src, name)
        self.assertIn("import v25accept", src)
        self.assertNotIn("captures/", src.split('"""', 2)[2])

    def test_v25accept_is_restored_after_every_call_even_on_error(self):
        orig = v25accept.video_clause
        v.evaluate(report(), None, None)
        self.assertIs(v25accept.video_clause, orig)
        with self.assertRaises(ValueError):
            v.evaluate(report(), None, {"a_stability": "OK"})
        self.assertIs(v25accept.video_clause, orig)


class TheStartUpClauseAdmitsTheFamilysTwoCasesAndNothingElse(unittest.TestCase):
    def test_RUN_40s_case_thirteen_no_press_frame(self):
        vid = v.video_clause(report())
        self.assertEqual((vid["verdict"], vid["P"]), ("HOLDS", None))
        self.assertEqual(vid["Q_indices"], SIG)

    def test_RUN_39s_case_thirteen_plus_the_frame_in_flight_at_the_press(self):
        vid = v.video_clause(report(press_idx=PRESS_IDX))
        self.assertEqual(vid["verdict"], "HOLDS")
        self.assertEqual(vid["P"]["index"], PRESS_IDX)
        self.assertLessEqual(vid["P"]["first_ms"], 0)
        self.assertGreater(vid["P"]["next_ms"], 0)
        self.assertEqual(vid["E_outside"], 1)                      # §V25's count, reported, deciding nothing

    def test_a_frame_one_later_is_new_behaviour_and_fails(self):
        """The hand-over frame one frame after the press (§V26.7 3): it is in Q, beyond the bound."""
        r = report(before_idx=SIG + [PRESS_IDX + 1])
        self.assertEqual(verdict(r), "DOES NOT HOLD")
        self.assertIn("|Q| = 14", v.video_clause(r)["why"])

    def test_the_masking_cases_the_count_alone_would_pass(self):
        # 12 signature + press + 1 elsewhere: |Q| = 13, one beyond the span
        r = report(before_idx=SIG[:-1] + [400], press_idx=PRESS_IDX)
        self.assertEqual(verdict(r), "DOES NOT HOLD")
        self.assertIn("beyond the start-up span", v.video_clause(r)["why"])
        # 12 + press: |Q| = 12
        self.assertEqual(verdict(report(before_idx=SIG[:-1], press_idx=PRESS_IDX)), "DOES NOT HOLD")

    def test_a_thirteenth_beyond_the_span_fails_without_a_press_frame_too(self):
        self.assertEqual(verdict(report(before_idx=SIG[:-1] + [250])), "DOES NOT HOLD")

    def test_fourteen_and_twelve_fail(self):
        self.assertEqual(verdict(report(before_idx=SIG + [170])), "DOES NOT HOLD")
        self.assertEqual(verdict(report(before_idx=SIG[:-1])), "DOES NOT HOLD")

    def test_a_frame_after_the_ai_fails(self):
        r = report(press_idx=PRESS_IDX, after=1)
        self.assertEqual(verdict(r), "DOES NOT HOLD")
        self.assertIn("AFTER the AI span (s1)", v.video_clause(r)["why"])

    def test_the_bound_is_the_logs_own_and_inclusive(self):
        self.assertEqual(verdict(report(before_idx=SIG[:-1] + [197])), "HOLDS")
        self.assertEqual(verdict(report(before_idx=SIG[:-1] + [198])), "DOES NOT HOLD")
        self.assertEqual(verdict(report(before_idx=SIG[:-1] + [198], bound=200)), "HOLDS")


class PIsStructural(unittest.TestCase):
    def test_the_boundaries(self):
        f = frame(PRESS_IDX)
        self.assertEqual(v.video_clause(report(press_idx=PRESS_IDX, t_press=f[1]))["P"]["index"], PRESS_IDX)
        # t_press exactly at the next frame's first block belongs to the next frame: not P
        r = report(press_idx=PRESS_IDX, t_press=f[3])
        self.assertIsNone(v.video_clause(r)["P"])
        self.assertEqual(verdict(r), "DOES NOT HOLD")

    def test_a_tail_lost_to_the_stall_does_not_move_P_outside_itself(self):
        """The objection that replaced the time window: a stall that drops a frame's tail puts its t_last_block
        BEFORE t_press; P is defined by t_first and the next frame, so it still holds."""
        r = report(press_idx=PRESS_IDX, t_press=t_press_in(PRESS_IDX, offset=FRAME * 35 // 40))
        r["video"]["before_frames"] = [x if x[0] != PRESS_IDX else frame(PRESS_IDX, blocks_lost_at_end=True)
                                       for x in r["video"]["before_frames"]]
        pf = [x for x in r["video"]["before_frames"] if x[0] == PRESS_IDX][0]
        self.assertLess(pf[2], r["t_press"])                       # t_last_block before the press
        self.assertEqual(verdict(r), "HOLDS")


class Inconclusive(unittest.TestCase):
    def test_an_early_press_inside_the_start_up_span(self):
        r = report(before_idx=SIG[:-1], press_idx=158, t_press=t_press_in(158))
        vid = v.video_clause(r)
        self.assertEqual(vid["verdict"], "INCONCLUSIVE")
        self.assertIn("(s4)", vid["why"])

    def test_no_bound_a_capped_list_or_a_short_list(self):
        self.assertEqual(verdict(report(bound=None)), "INCONCLUSIVE")
        self.assertEqual(verdict(report(capped=True)), "INCONCLUSIVE")
        self.assertEqual(verdict(report(listed=12)), "INCONCLUSIVE")
        r = report()
        del r["video"]["before_frames"]
        self.assertEqual(verdict(r), "INCONCLUSIVE")

    def test_the_store_and_the_window_as_in_V25(self):
        self.assertEqual(verdict(report(video__store_full=1)), "INCONCLUSIVE")
        self.assertEqual(verdict(report(video__stored=99)), "INCONCLUSIVE")
        self.assertEqual(verdict(report(window_opened=False)), "INCONCLUSIVE")


class TheRateHalfIsV25s(unittest.TestCase):
    def test_integers_inclusive(self):
        self.assertEqual(verdict(report(inside=44, ai_ticks=2567047476)), "HOLDS")
        self.assertEqual(verdict(report(inside=45, ai_ticks=2567047476)), "DOES NOT HOLD")


class PhaseSix(unittest.TestCase):
    def setUp(self):
        saved = v22accept.question_L2
        v22accept.question_L2 = lambda b: {"verdict": "PASS", "why": "spy", "silence_fraction": 0.0}
        self.addCleanup(setattr, v22accept, "question_L2", saved)
        self.decl = {"a_stability": "PASS", "defects": {k: "no" for k in v25accept.DEFECTS}, "a_words": "",
                     "a_fidelity": "", "picture": "normal", "picture_words": "", "controls": "responded",
                     "controls_words": ""}

    def test_closes_on_RUN_39s_case(self):
        r = v.evaluate(report(press_idx=PRESS_IDX), b"s", self.decl)
        self.assertEqual((r["V"]["verdict"], r["phase6"]["verdict"]), ("PASS", "CLOSES"))

    def test_stays_open_on_a_frame_one_later(self):
        r = v.evaluate(report(before_idx=SIG + [PRESS_IDX + 1]), b"s", self.decl)
        self.assertEqual(r["phase6"]["verdict"], "STAYS OPEN")
        self.assertEqual([c["clause"] for c in r["phase6"]["clauses_not_pass"]], ["V"])

    def test_the_command_line_prints_the_clause_and_the_confound(self):
        with tempfile.TemporaryDirectory() as d:
            rp, dp = os.path.join(d, "r.json"), os.path.join(d, "d.json")
            for p, o in ((rp, report(press_idx=PRESS_IDX)), (dp, self.decl)):
                with open(p, "w") as f:
                    json.dump(o, f)
            side = os.path.join(d, "s.bin")
            with open(side, "wb") as f:
                f.write(b"s")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = v.main(["v26accept.py", rp, "--sidecar", side, "--declaration", dp,
                             "--json", os.path.join(d, "o.json")])
            self.assertEqual(rc, 0)
            out = buf.getvalue()
            for tok in ("  V   PASS", "PHASE 6  CLOSES", "V's start-up clause (§V26.7): P {'index': 612",
                        "cannot be attributed between the console prints and the first VI hand-over"):
                self.assertIn(tok, out, tok)
            with open(os.path.join(d, "o.json")) as f:
                self.assertEqual(json.load(f)["V"]["video"]["P"]["index"], PRESS_IDX)
        self.assertIs(v25accept.video_clause.__module__, "v25accept")


if __name__ == "__main__":
    unittest.main()
