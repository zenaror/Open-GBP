"""tests/host/test_v28loss.py -- GitHub Issue #137: tools/v28loss.py applies the rule the Orchestrator registered before the build
(loss = 1 - blocks_in / nominal; a factor's effect is the mean level difference in percentage points; > 0.2 coupled, < 0.05 not,
between unresolved), on synthetic logs whose answer is known, and the format strings the tool reads are the ones main.c writes.

The boundaries are tested in EXACT arithmetic: the synthetic windows are 125 s at a 1 Hz timebase, where one percentage point of
loss is 4096 x 125 / 100 = 5120 blocks, so 0.2 pp is exactly 1024 blocks and 0.05 pp exactly 256 -- a value ON a threshold is
UNRESOLVED (the rule's words: 'exceeds' and 'below'), one block either side of it is not.
"""
import os
import re
import sys
import unittest
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import v28loss  # noqa: E402

MAIN = os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")
SECS = 125                   # the synthetic hold's window (seconds at tb_hz = 1)
NOMINAL = 4096 * SECS        # 512 000 blocks
PP = NOMINAL // 100          # one percentage point of loss, in blocks: 5120


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def hold_lines(n, kind, cyc, L, S, ahead, blocks, partial=0, late=1, hooks=0, underruns=0, taps=None, failed=0, wrong=0, t0=0,
               hist=None, obs_t=(4096, 4096, 4096), obs_a=None, underruns_late=None):
    """The lines main.c's v28_loss_report writes for one hold; full window = late window + LATE_S, both ending at t_end."""
    late_s = 3
    ts, tl, te = t0, t0 + late_s, t0 + late_s + SECS
    full_blocks = blocks + 4096 * late_s
    taps_full = full_blocks if taps is None else taps
    lines = ["%06d V28_LOSS n=%d kind=%d cyc=%d L=%d S=%d ahead=%d target=4096 partial=%d late=%d hooks=%d t_start=%x t_late=%x t_end=%x "
             "ring=100,200,300" % (n, n, kind, cyc, L, S, ahead, partial, late, hooks, ts, tl if late else 0, te),
             "%06d V28_LOSSO n=%d obs_t=%d,%d,%d obs_a=%d,%d,%d" % ((n, n) + tuple(obs_t) + tuple(obs_a or (ahead, ahead, ahead)))]
    lines.append("%06d V28_LOSSC n=%d win=full blocks_in=%d taps=%d failed=%d wrong=%d underruns=%d dup=1 drop=0 starved=2 "
                 "produced=3 handed=4 gated=5" % (n, n, full_blocks, taps_full, failed, wrong, underruns))
    if late:
        lines.append("%06d V28_LOSSC n=%d win=late blocks_in=%d taps=%d failed=%d wrong=%d underruns=%d dup=1 drop=0 starved=2 "
                     "produced=3 handed=4 gated=5" % (n, n, blocks, blocks if taps is None else taps - 4096 * late_s,
                                                      failed, wrong,
                                                      underruns if underruns_late is None else underruns_late))
    for name in v28loss.HIST_NAMES:
        h = (hist or {}).get(name, (10, 10000, 2000, [4, 3, 2, 1, 0]))
        edges = "1000,2000,4000,8000" if name != "gap" else "12000,20000,40000,80000"
        lines.append("%06d V28_LOSSH n=%d h=%s count=%d sum=%d max=%d edges=%s bins=%s" % (
            n, n, name, h[0], h[1], h[2], edges, ",".join(str(b) for b in h[3])))
    return lines


def log(holds, cfg_holds=None):
    cfg = ("000001 V28LOSSCFG target=4096 ahead=4 ahead_final=1 warm_s=10 hold_s=20 late_s=3 final_s=60 cycles=3 cells=4 "
           "step_full=128 step_half=64 tb_hz=1 holds=%d refused_done=0 entry_refused_ticks=0" % (len(holds) if cfg_holds is None else cfg_holds))
    lines = ["000000 IDENT test=GBP-AUDIO-V28", cfg,
             "000002 V28TAPS taps=100 taps_failed=0 wrong_len=0 blocks_in=100 gap_max=5 gap_at=0"]
    for h in holds:
        lines += h
    return "\n".join(lines) + "\n"


def image_cells():
    """The twelve cells (L, S) exactly as src/audio/gbp_v28_loss.c's own table lists them."""
    with open(os.path.join(ROOT, "src", "audio", "gbp_v28_loss.c"), encoding="utf-8") as f:
        src = f.read()
    ls = [int(x) for x in re.search(r"static const uint8_t L\[[^\]]*\] = \{([^}]*)\}", src).group(1).replace("u", "").split(",")]
    ss = [int(x) for x in re.search(r"static const uint8_t S\[[^\]]*\] = \{([^}]*)\}", src).group(1).replace("u", "").split(",")]
    return list(zip(ls, ss))


CELLS = image_cells()


def sequence(loss_of_cell, drift=0, cells=None):
    """warm, the twelve cells in the image's own order, final. `loss_of_cell(L, S, k)` is the loss of hold k in BLOCKS per 125 s window;
    `drift` adds that many blocks per hold of position (a linear drift)."""
    hs = [hold_lines(0, 0, 0, 1, 1, 4, NOMINAL - 100 * PP // 100)]
    n = 1
    for k, (L, S) in enumerate(cells or CELLS):
        hs.append(hold_lines(n, 1, k // 4, L, S, 4, NOMINAL - loss_of_cell(L, S, k) - drift * k))
        n += 1
    hs.append(hold_lines(n, 2, 0, 1, 1, 1, NOMINAL - 8 * PP, underruns=14, hooks=13))
    return hs


class Rule(unittest.TestCase):
    def test_classify_at_the_registered_thresholds(self):
        c = v28loss.classify
        self.assertEqual(c(Fraction(1, 5)), "UNRESOLVED")                     # exactly 0.2: 'exceeds' is strict
        self.assertEqual(c(Fraction(1, 5) + Fraction(1, 10**6)), "COUPLED")
        self.assertEqual(c(-Fraction(1, 5) - Fraction(1, 10**6)), "COUPLED")   # the sign does not matter
        self.assertEqual(c(Fraction(1, 20)), "UNRESOLVED")                     # exactly 0.05: 'below' is strict
        self.assertEqual(c(Fraction(1, 20) - Fraction(1, 10**6)), "NOT COUPLED")
        self.assertEqual(c(Fraction(0)), "NOT COUPLED")
        self.assertEqual(c(None), "NOT EVALUABLE")

    def effects(self, lab_blocks, step_blocks):
        """Both effects from a log where the label costs `lab_blocks` per hold with the label ON and the long step `step_blocks`."""
        res = v28loss.analyse(log(sequence(lambda L, S, c: 16 * PP // 10 + (lab_blocks if L else 0) + (step_blocks if S else 0))))
        return res["effects"]["label"], res["effects"]["step"], res

    def test_the_effect_is_the_mean_level_difference_in_points(self):
        lab, stp, res = self.effects(2 * PP, 0)           # the label costs 2 pp with it ON; the step nothing
        self.assertEqual(lab["effect_pp"], Fraction(2))
        self.assertEqual(lab["verdict"], "COUPLED")
        self.assertEqual(stp["effect_pp"], Fraction(0))
        self.assertEqual(stp["verdict"], "NOT COUPLED")
        self.assertEqual((lab["n_a"], lab["n_b"], stp["n_a"], stp["n_b"]), (6, 6, 6, 6))
        self.assertEqual(res["counted"], 12)

    def test_a_step_effect_alone_and_the_sign(self):
        lab, stp, _ = self.effects(0, 3 * PP // 2)         # the long step costs 1.5 pp
        self.assertEqual(stp["effect_pp"], Fraction(3, 2))
        self.assertEqual(stp["verdict"], "COUPLED")
        self.assertEqual(lab["verdict"], "NOT COUPLED")
        lab, stp, _ = self.effects(0, -3 * PP // 2)        # a long step that HELPS is negative and still coupled
        self.assertEqual(stp["effect_pp"], Fraction(-3, 2))
        self.assertEqual(stp["verdict"], "COUPLED")

    def test_exact_boundaries_in_blocks(self):
        for blocks, want in ((1024, "UNRESOLVED"), (1025, "COUPLED"), (1023, "UNRESOLVED"),
                             (256, "UNRESOLVED"), (257, "UNRESOLVED"), (255, "NOT COUPLED"), (0, "NOT COUPLED")):
            lab, _, _ = self.effects(blocks, 0)
            self.assertEqual(lab["verdict"], want, "%d blocks (%s pp)" % (blocks, lab["effect_pp"]))
        lab, _, _ = self.effects(1024, 0)
        self.assertEqual(lab["effect_pp"], Fraction(1, 5), "1024 blocks of 512000 is exactly 0.2 points, not a rounded decimal")

    def test_only_whole_cell_holds_with_a_late_snapshot_count(self):
        hs = sequence(lambda L, S, c: 2 * PP)
        hs[3] = hold_lines(3, 1, 0, 0, 0, 4, NOMINAL - 90 * PP, partial=1)          # a cut cell: excluded
        hs[5] = hold_lines(5, 1, 1, 1, 0, 4, NOMINAL - 90 * PP, late=0)              # no late snapshot: excluded
        res = v28loss.analyse(log(hs))
        self.assertEqual(res["counted"], 10)
        self.assertEqual(res["effects"]["label"]["effect_pp"], Fraction(0), "the excluded holds' 90 % never enter a mean")
        self.assertTrue(any("not counted" in n for n in res["notes"]))

    def test_warm_and_final_are_never_counted(self):
        res = v28loss.analyse(log(sequence(lambda L, S, c: 2 * PP)))
        self.assertEqual([h["kind"] for h in res["holds"]].count("warm"), 1)
        self.assertEqual(res["counted"], 12)
        self.assertEqual(res["mean_loss"], Fraction(2, 100))

    def test_a_log_that_breaks_the_one_flip_walk_says_so(self):
        hs = sequence(lambda L, S, c: 2 * PP)
        hs[2] = hold_lines(2, 1, 0, 0, 0, 4, NOMINAL - 2 * PP)     # (L,S) -> (l,s): two factors at once
        res = v28loss.analyse(log(hs))
        self.assertTrue(any("one-flip" in n for n in res["notes"]))

    def test_the_final_hold(self):
        for u, key in ((14, "matches"), (15, "matches"), (0, "ZERO"), (13, "consistent"), (16, "consistent"), (7, "consistent"),
                       (22, "consistent"), (6, "differs"), (23, "differs"), (30, "differs")):
            hs = sequence(lambda L, S, c: 2 * PP)
            hs[-1] = hold_lines(13, 2, 0, 1, 1, 1, NOMINAL - 8 * PP, underruns=u, hooks=u)
            txt = v28loss.render(v28loss.analyse(log(hs)))
            self.assertIn(key, [l for l in txt.splitlines() if l.startswith("FINAL")][0], "%d underruns" % u)
        hs = sequence(lambda L, S, c: 2 * PP)
        hs[-1] = hold_lines(13, 2, 0, 1, 1, 1, NOMINAL - 8 * PP, underruns=14, partial=1)
        self.assertIn("PARTIAL", v28loss.render(v28loss.analyse(log(hs))))

    def test_a_refused_or_short_tap_is_flagged(self):
        hs = sequence(lambda L, S, c: 2 * PP)
        hs[2] = hold_lines(2, 1, 0, 1, 0, 4, NOMINAL - 2 * PP, failed=3)
        res = v28loss.analyse(log(hs))
        self.assertTrue(any("failed" in x for h in res["holds"] for x in h["flags"]))
        hs[2] = hold_lines(2, 1, 0, 1, 0, 4, NOMINAL - 2 * PP, taps=NOMINAL - 5)
        res = v28loss.analyse(log(hs))
        self.assertTrue(any("taps" in x and "!=" in x for h in res["holds"] for x in h["flags"]))

    def test_the_count_of_holds_is_checked_against_the_config(self):
        res = v28loss.analyse(log(sequence(lambda L, S, c: 2 * PP), cfg_holds=15))
        self.assertTrue(any("15 holds" in n for n in res["notes"]))

    def test_a_log_without_the_config_is_refused(self):
        with self.assertRaises(ValueError):
            v28loss.analyse("000000 IDENT test=x\n")

    def test_the_render_carries_the_loss_and_the_histograms(self):
        txt = v28loss.render(v28loss.analyse(log(sequence(lambda L, S, c: 2 * PP))))
        self.assertIn("FACTOR EFFECTS", txt)
        self.assertIn("WHERE THE TIME GOES", txt)
        self.assertIn("HOW OFTEN EACH STRETCH IS LONG", txt)
        self.assertIn("2.000", txt)


class AfterTheReview(unittest.TestCase):
    """What an adversarial review of the first reader found, each pinned: drift, dispersion, balance, robustness, the point."""

    def test_the_image_s_own_order_balances_the_label_against_a_linear_drift(self):
        pos = dict(((L, S), []) for L, S in CELLS)
        for k, c in enumerate(CELLS):
            pos[c].append(k)
        self.assertEqual(sum(k for k, (L, S) in enumerate(CELLS) if L == 1), sum(k for k, (L, S) in enumerate(CELLS) if L == 0),
                         "label-on and label-off positions sum alike: no linear drift leaks into the label effect")
        self.assertEqual(sum(k for k, (L, S) in enumerate(CELLS) if S == 1) - sum(k for k, (L, S) in enumerate(CELLS) if S == 0), -4)
        self.assertTrue(all(len(v) == 3 for v in pos.values()))
        self.assertTrue(all((a[0] != b[0]) + (a[1] != b[1]) == 1 for a, b in zip(CELLS, CELLS[1:])))

    def test_a_linear_drift_biases_the_marginal_step_effect_and_the_adjusted_estimate_removes_it(self):
        res = v28loss.analyse(log(sequence(lambda L, S, c: 2 * PP, drift=PP // 10)))      # 0.1 pp per hold, NO real effect
        lab, stp = res["effects"]["label"], res["effects"]["step"]
        self.assertEqual(lab["effect_pp"], Fraction(0), "the label is balanced: a linear drift does not leak into it")
        self.assertEqual(stp["effect_pp"], Fraction(-1, 15), "the step's marginal effect carries 0.1 x (-4/6) pp of the drift")
        self.assertEqual(res["adjusted"]["S"], Fraction(0))
        self.assertEqual(res["adjusted"]["L"], Fraction(0))
        self.assertEqual(res["adjusted"]["trend"], Fraction(1, 10))
        self.assertEqual(stp["verdict"], "UNRESOLVED")
        self.assertEqual(stp["adjusted_verdict"], "NOT COUPLED")
        self.assertEqual(stp["held"], "UNRESOLVED", "the registered class and the trend-adjusted class disagree: held")

    def test_a_real_effect_survives_drift_in_the_held_verdict(self):
        res = v28loss.analyse(log(sequence(lambda L, S, c: 2 * PP + (2 * PP if L else 0), drift=PP // 100)))
        lab = res["effects"]["label"]
        self.assertEqual(lab["verdict"], "COUPLED")
        self.assertEqual(lab["adjusted_verdict"], "COUPLED")
        self.assertEqual(lab["held"], "COUPLED")
        self.assertTrue(lab["stable"])

    def test_the_standard_error_and_a_class_the_noise_can_move(self):
        # effect 0.1 pp ( UNRESOLVED ) with scatter: the pooled SD comes from the repeats of the same cell
        base = lambda L, S, c: 2 * PP + (PP // 10 if L else 0) + [0, 300, -300][(c // 4) % 3] * 2
        res = v28loss.analyse(log(sequence(base)))
        self.assertEqual(res["sd_df"], 8)
        self.assertGreater(res["sd_pp"], 0)
        e = res["effects"]["label"]
        self.assertIsNotNone(e["se_pp"])
        # near a threshold with scatter the class is not stable and the held verdict says UNRESOLVED
        near = lambda L, S, c: 2 * PP + (1000 if L else 0) + [0, 900, -900][(c // 4) % 3]
        e = v28loss.analyse(log(sequence(near)))["effects"]["label"]
        self.assertEqual(e["verdict"], "UNRESOLVED")
        self.assertEqual(e["held"], "UNRESOLVED")

    def test_zero_scatter_is_stable_and_held_equals_registered(self):
        res = v28loss.analyse(log(sequence(lambda L, S, c: 2 * PP + (2 * PP if L else 0))))
        e = res["effects"]["label"]
        self.assertEqual(e["se_pp"], 0.0)
        self.assertTrue(e["stable"])
        self.assertEqual(e["held"], e["verdict"])
        self.assertEqual(res["effects"]["step"]["held"], "NOT COUPLED")

    def test_an_unbalanced_design_holds_every_verdict(self):
        hs = sequence(lambda L, S, c: 2 * PP + (2 * PP if L else 0))
        hs[-2] = hold_lines(12, 1, 2, 0, 1, 4, NOMINAL - 2 * PP, partial=1)          # the last cell is cut
        res = v28loss.analyse(log(hs))
        self.assertFalse(res["balanced"])
        self.assertTrue(any("UNBALANCED" in n for n in res["notes"]))
        for e in res["effects"].values():
            self.assertEqual(e["held"], "UNRESOLVED")
            self.assertIn("unbalanced", e["held_why"])

    def test_a_hold_off_the_intended_point_is_not_counted(self):
        hs = sequence(lambda L, S, c: 2 * PP)
        hs[4] = hold_lines(4, 1, 0, 1, 0, 4, NOMINAL - 2 * PP, obs_t=(4096, 4096, 3000))      # the target moved during the hold
        hs[6] = hold_lines(6, 1, 1, 0, 0, 4, NOMINAL - 2 * PP, obs_a=(4, 3, 4))                # AHEAD moved
        res = v28loss.analyse(log(hs))
        self.assertEqual(res["counted"], 10)
        self.assertTrue(any("OFF POINT" in x for h in res["holds"] for x in h["flags"]))

    def test_a_truncated_log_degrades_with_notes_instead_of_crashing(self):
        text = log(sequence(lambda L, S, c: 2 * PP))
        lines = text.splitlines()
        # 1. a whole V28_LOSS record missing
        cut = "\n".join(l for l in lines if not l.startswith("000000".replace("000000", "%06d" % 0)) or True)
        no_loss = "\n".join(l for l in lines if " V28_LOSS n=3 " not in l) + "\n"
        res = v28loss.analyse(no_loss)
        self.assertTrue(any("no V28_LOSS record" in n for n in res["notes"]))
        # 2. the late window's V28_LOSSC record missing while late=1
        no_late = "\n".join(l for l in lines if not (" V28_LOSSC n=5 win=late" in l)) + "\n"
        res = v28loss.analyse(no_late)
        self.assertEqual(res["counted"], 11)
        self.assertTrue(any("late window's record is missing" in x for h in res["holds"] for x in h["flags"]))
        # 3. a V28_LOSSC line cut off mid-record (a full ring drops or truncates)
        trunc = "\n".join(l if " V28_LOSSC n=7 win=full" not in l else l[:l.index("failed=")] for l in lines) + "\n"
        res = v28loss.analyse(trunc)
        self.assertTrue(any("truncated or malformed V28_LOSSC" in n for n in res["notes"]))
        # 4. the operating-point record missing
        no_obs = "\n".join(l for l in lines if " V28_LOSSO n=8 " not in l) + "\n"
        res = v28loss.analyse(no_obs)
        self.assertEqual(res["counted"], 11)
        # the tool still renders every one of them
        for t in (no_loss, no_late, trunc, no_obs):
            self.assertIn("FACTOR EFFECTS", v28loss.render(v28loss.analyse(t)))

    def test_the_final_hold_reports_the_late_window_and_a_partial_or_off_point_one_is_not_evaluable(self):
        hs = sequence(lambda L, S, c: 2 * PP)
        hs[-1] = hold_lines(13, 2, 0, 1, 1, 1, NOMINAL - 8 * PP, underruns=14, underruns_late=11, hooks=14)
        txt = v28loss.render(v28loss.analyse(log(hs)))
        self.assertIn("14 underruns whole hold, 11 in the late window", txt)
        hs[-1] = hold_lines(13, 2, 0, 1, 1, 1, NOMINAL - 8 * PP, underruns=14, obs_a=(1, 1, 2))
        self.assertIn("OFF THE INTENDED POINT", v28loss.render(v28loss.analyse(log(hs))))


class TheEdgesAreTheImagesOwn(unittest.TestCase):
    def test_the_gap_histogram_edges_sit_half_way_between_whole_block_periods(self):
        """A gap that skipped k blocks must fall in its own bin, and read-latency jitter must not move it across an edge: the edges are
        the block period (40.5 MHz / 4096 blocks/s = 9 887.45 ticks) x 1.5, 2.5, 3.5, 4.5, rounded down."""
        src = read(os.path.join(ROOT, "src", "audio", "gbp_v28_loss.c"))
        m = re.search(r"EDGES_GAP\[[^\]]*\]\s*=\s*\{([^}]*)\}", src)
        edges = [int(x) for x in m.group(1).replace("u", "").split(",")]
        period = 40_500_000 / 4096
        self.assertEqual(edges, [int((k + 0.5) * period) for k in (1, 2, 3, 4)])


class TheFormatsAreTheImagesOwn(unittest.TestCase):
    """The format strings the tool reads are the ones v28_loss_report() writes, and none can be truncated by the ring log."""
    FORMATS = ("V28LOSSCFG target=", "V28_LOSS n=", "V28_LOSSC n=", "V28_LOSSH n=", "V28_LOSSO n=")

    def formats(self, src):
        i = src.index("static void v28_loss_report_ctr")
        j = src.index("#endif /* GBP_V28_PLAN_DIAG_LOSS */", i)
        body = src[i:j]
        out = []
        for m in re.finditer(r'ringlog_printf\(rl,\s*((?:"(?:[^"\\]|\\.)*"\s*)+),', body):
            out.append("".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1))))
        return out

    def test_every_record_the_tool_reads_is_written_by_main(self):
        fm = self.formats(read(MAIN))
        for prefix in self.FORMATS:
            self.assertTrue(any(f.startswith(prefix) for f in fm), prefix)
        self.assertIn('"V28TAPS taps=%lu taps_failed=%lu wrong_len=%lu blocks_in=%lu gap_max=%llu gap_at=%llx"', read(MAIN))

    def test_the_tool_reads_the_fields_main_writes(self):
        fm = "\n".join(self.formats(read(MAIN)))
        for field in ("kind=", "cyc=", "L=", "S=", "ahead=", "target=", "partial=", "late=", "hooks=", "t_start=", "t_late=", "t_end=",
                      "ring=", "win=", "blocks_in=", "taps=", "failed=", "wrong=", "underruns=", "dup=", "drop=", "starved=",
                      "produced=", "handed=", "gated=", "h=", "count=", "sum=", "max=", "edges=", "bins=", "tb_hz=", "holds=",
                      "hold_s=", "late_s=", "cells=", "cycles=", "obs_t=", "obs_a="):
            self.assertIn(field, fm, "%s is read by tools/v28loss.py and is not written by main.c" % field)

    def test_no_record_can_be_truncated_by_the_ring_log(self):
        """Worst case: every %lu ten digits, every %llu twenty, every %llx sixteen, %u three, %s the longest name (7), and the
        ringlog's own 7-character prefix; the ring's line is 256 bytes."""
        widths = {"lu": 10, "llu": 20, "llx": 16, "u": 3, "s": 7}
        for f in self.formats(read(MAIN)):
            n = 7 + len(re.sub(r"%(?:llu|llx|lu|u|s)", "", f)) + sum(widths[t] for t in re.findall(r"%(llu|llx|lu|u|s)", f))
            self.assertLess(n, 250, "%r can reach %d bytes: a truncated record is a silently missing measurement" % (f[:40], n))


if __name__ == "__main__":
    unittest.main()
