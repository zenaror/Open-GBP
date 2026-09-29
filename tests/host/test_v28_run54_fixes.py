"""tests/host/test_v28_run54_fixes.py -- GitHub Issue #138: the two fixes RUN 54 derived (a steady production step of 64 pushes a call; a label that
changes once a second) and the per-phase loss records that measure them, as WRITTEN in poc/gbp-audio-v28/source/main.c (which cannot be compiled or
driven on the host: the source text is what can be checked, the shape test_v28_diag_loss_wiring.py established).
"""
import os
import re
import sys
import unittest
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import test_v28_diag_loss_wiring as W  # noqa: E402
import v28verdict  # noqa: E402

MAIN = W.MAIN


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class TheStepIsInstalledEverywhereButTheDiagnostic(unittest.TestCase):
    def test_exactly_two_assignments_one_per_branch(self):
        src = W.code(read(MAIN))
        self.assertEqual(len(re.findall(r"\.step_pushes\s*=", src)), 2)
        for n, line, active in W.diag_regions(src):
            if "ap2.step_pushes = gbp_v28_step_hook;" in line:
                self.assertFalse(active, "the production hook sits in the branch the diag_loss image does NOT compile")
            if "ap2.step_pushes = loss_step_pushes;" in line:
                self.assertTrue(active, "the diagnostic's own step arm sits in the diag_loss-only branch")

    def test_it_is_installed_before_the_first_tap_can_produce(self):
        src = read(MAIN)
        self.assertLess(src.index("ap2.step_pushes = gbp_v28_step_hook;"), src.index("cfg.audio_tap = live_tap;"))

    def test_the_header_pins_the_step_and_its_constraints(self):
        h = read(os.path.join(ROOT, "src", "audio", "gbp_v28_step.h"))
        self.assertIn("#define GBP_V28_STEP_STEADY 64u", h)
        for assertion in ("GBP_APLAY2_STEP_PUSHES % GBP_V28_STEP_STEADY == 0u", "GBP_APLAY2_PUSHES % GBP_V28_STEP_STEADY == 0u"):
            self.assertIn(assertion, h)


class TheLandingFollowsTheStep(unittest.TestCase):
    def test_the_bias_is_the_landing_point_less_the_recoverys_step_and_clamped_like_the_producer(self):
        src = read(os.path.join(ROOT, "src", "audio", "gbp_atrans2.c"))
        m = re.search(r"static uint32_t land_bias\(const struct gbp_aplay2 \*p\)\n\{(.*?)\n\}", src, re.S)
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("p->step_pushes ? p->step_pushes(p->step_pushes_user, p->produced) : GBP_APLAY2_STEP_PUSHES", body)
        self.assertIn("if (step == 0u || step > GBP_APLAY2_PUSHES) step = GBP_APLAY2_STEP_PUSHES;", body)
        self.assertIn("GBP_ATRANS2_LAND_POINT > step ? GBP_ATRANS2_LAND_POINT - step : 0u", body)
        # the same clamp the producer applies (gbp_aplay2.c), so the two cannot disagree about the step
        ap = read(os.path.join(ROOT, "src", "audio", "gbp_aplay2.c"))
        self.assertIn("if (p->cur_step == 0u || p->cur_step > GBP_APLAY2_PUSHES) p->cur_step = GBP_APLAY2_STEP_PUSHES;", ap)

    def test_the_old_constant_is_gone_everywhere(self):
        for base in ("src", "tests", "poc", "tools"):
            for dp, _dn, fn in os.walk(os.path.join(ROOT, base)):
                for f in fn:
                    if f.endswith((".c", ".h", ".py")) and f != "test_v28_run54_fixes.py":
                        self.assertNotIn("GBP_ATRANS2_LAND_BIAS", read(os.path.join(dp, f)) if os.path.getsize(os.path.join(dp, f)) < 5_000_000 else "",
                                         "%s still names GBP_ATRANS2_LAND_BIAS" % os.path.join(dp, f))


class TheLabelChangesOnceASecond(unittest.TestCase):
    def branches(self):
        body = W.function_body(W.code(read(MAIN)), "v28_label_text")
        m = re.search(r"#if\s+defined\(GBP_V28_PLAN_PERCEPTUAL\)\n(.*?)#else\n(.*?)#endif\n", body, re.S)
        return m.group(1), m.group(2)

    @staticmethod
    def snprintf_args(branch):
        """The argument expressions of every snprintf in the branch after the format string."""
        out = []
        for m in re.finditer(r"snprintf\(out, cap, (\"(?:[^\"\\]|\\.)*\"),(.*?)\);", branch, re.S):
            args = re.sub(r"\(unsigned long\)", "", m.group(2))
            out.append([a.strip() for a in re.split(r",(?![^(]*\))", args) if a.strip()])
        return out

    def test_the_validation_text_depends_only_on_the_clock_the_sampled_count_and_the_phase(self):
        _, validation = self.branches()
        allowed = {"shown < count ? shown : count", "count", "label_handed_once_a_second(elapsed_s)", "elapsed_s"}
        args = self.snprintf_args(validation)
        self.assertTrue(args)
        for a in args:
            for x in a:
                self.assertIn(x, allowed, "the validation label reads %r: not a once-a-second input" % x)

    def test_the_perceptual_text_is_the_clock_only_plus_its_own_setting_count(self):
        perceptual, _ = self.branches()
        allowed = {"nulling.settings_n", "elapsed_s"}
        for a in self.snprintf_args(perceptual):
            for x in a:
                self.assertIn(x, allowed)
        self.assertNotIn("ap2.", perceptual)

    def test_the_helper_samples_once_a_second_and_only_outside_the_perceptual_build(self):
        src = W.code(read(MAIN))
        body = W.function_body(src, "label_handed_once_a_second")
        self.assertIn("if (elapsed_s != label_h_second) {", body)
        self.assertIn("label_h_value = (uint32_t)ap2.handed;", body)
        for n, line, active in W.diag_regions(src):
            pass
        i = src.index("static uint32_t label_h_second")
        pre = src[:i].rsplit("#if", 1)[-1]
        self.assertTrue(pre.lstrip().startswith("!defined(GBP_V28_PLAN_PERCEPTUAL)"), "the helper is compiled only where the label may read ap2")

    def test_a_model_of_the_helper_gives_one_text_change_a_second(self):
        """The helper's logic in Python: over 10 s of 32 hand-offs a second, the (clock, H) pair changes once a second, not 32 times."""
        state = {"sec": None, "val": None}

        def helper(sec, handed):
            if sec != state["sec"]:
                state["sec"], state["val"] = sec, handed
            return state["val"]
        texts, prev = 0, None
        for k in range(320):                       # 10 s, one look at the label per hand-off (a video frame sees a new count each time)
            sec, handed = k // 32, k
            t = (sec, helper(sec, handed))
            texts += t != prev
            prev = t
        self.assertEqual(texts, 10)
        # and a stall still shows: the count is the same across two seconds when hand-offs stop
        state.update(sec=None, val=None)
        seen = [helper(s, 500) for s in range(5)]
        self.assertEqual(seen, [500] * 5)


class ThePerPhaseRecords(unittest.TestCase):
    def test_the_snapshots_are_taken_at_the_edges_before_the_line_admission_gate(self):
        body = W.function_body(W.code(read(MAIN)), "syncpe_edges")
        a = body.index("v28_phase_snap_take(&ph_start[i]);")
        b = body.index("v28_phase_snap_take(&ph_end[i]);")
        self.assertLess(a, body.index("if (sync_line_admit())"), "a full ring log must not lose the snapshot")
        self.assertLess(b, body.index("if (sync_line_admit())", body.index("syncpe_ended_seen[i] = 1u;")))
        self.assertIn("if (r->started && !syncpe_started_seen[i]) {", body[:a + 200])
        self.assertIn("if (r->ended && !syncpe_ended_seen[i]) {", body[:b + 200])

    def test_a_snapshot_never_depends_on_the_transport_teardown_clears(self):
        body = W.function_body(W.code(read(MAIN)), "v28_phase_snap_take")
        self.assertIn("s->t = (uint64_t)gettime();", body)
        self.assertNotIn("in_transport", body, "teardown sets in_transport = 0 before v28_phase_report(): an unended phase would print t1 = 0")

    def test_every_plan_prints_them(self):
        src = W.code(read(MAIN))
        for n, line, active in W.diag_regions(src):
            if "v28_phase_report(&rl);" in line:
                self.assertFalse(active, "the per-phase report is in every plan, not only diag_loss")
        self.assertIn("v28_phase_report(&rl);", src)

    def test_the_formats_are_the_readers_and_fit_a_ring_line(self):
        src = read(MAIN)
        i = src.index("static void v28_phase_report")
        body = src[i:src.index("static uint64_t t_video_ready", i)]
        fmts = ["".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))
                for m in re.finditer(r'ringlog_printf\(rl, ((?:"(?:[^"\\]|\\.)*"\s*)+),', body)]
        self.assertEqual(len(fmts), 2)
        both = " ".join(fmts)
        for field in ("V28PHC p=", "V28PHD p=", "ended=", "t0=", "t1=", "blocks_in=", "taps=", "failed=", "wrong=", "underruns=", "dup=", "drop=",
                      "starved=", "produced=", "handed=", "gated=", "ring="):
            self.assertIn(field, both)
        widths = {"lu": 10, "llu": 20, "llx": 16, "u": 3, "s": 7}
        for fmt in fmts:
            n = 7 + len(re.sub(r"%(?:llu|llx|lu|u|s)", "", fmt)) + sum(widths[t] for t in re.findall(r"%(llu|llx|lu|u|s)", fmt))
            self.assertLess(n, 250, "%s can reach %d bytes" % (fmt[:12], n))


def phc(p, secs, blocks, ended=1, underruns=0, tb=40_500_000, t0=1000, drop_detail=False):
    lines = ["%06d V28PHC p=%d ended=%d t0=%x t1=%x blocks_in=%d taps=%d failed=0 wrong=0 underruns=%d"
             % (p, p, ended, t0, t0 + int(secs * tb), blocks, blocks, underruns)]
    if not drop_detail:
        lines.append("%06d V28PHD p=%d dup=5 drop=1 starved=2 produced=3 handed=4 gated=6 ring=100,200" % (p, p))
    return "\n".join(lines)


class TheReader(unittest.TestCase):
    def test_the_loss_per_phase_is_exact(self):
        text = "\n".join([phc(0, 10, 40960), phc(1, 20, int(4096 * 20 * 0.998)), phc(2, 60, 4096 * 60 - 3686, underruns=2, ended=0)])
        rows = v28verdict.phase_loss(text)["rows"]
        self.assertEqual([r["p"] for r in rows], [0, 1, 2])
        self.assertEqual(rows[0]["loss"], Fraction(0))
        self.assertEqual(rows[1]["loss"], 1 - Fraction(int(4096 * 20 * 0.998), 4096 * 20))
        self.assertEqual(rows[2]["loss"], Fraction(3686, 4096 * 60))
        self.assertFalse(rows[2]["ended"])

    def test_a_log_without_the_records_says_so(self):
        self.assertFalse(v28verdict.phase_loss("000001 IDENT x")["have"])
        self.assertEqual(v28verdict.phase_loss("000001 IDENT x"), {"have": False, "rows": []})

    def test_a_phase_with_only_its_first_record_is_not_half_reported(self):
        text = "\n".join([phc(0, 10, 40960, drop_detail=True), phc(1, 20, 80000)])
        self.assertEqual([r["p"] for r in v28verdict.phase_loss(text)["rows"]], [1])

    def test_render_prints_every_phase(self):
        text = "\n".join([phc(0, 10, 40960), phc(1, 20, 80000, underruns=3)])
        a = v28verdict.analyse(text)
        self.assertEqual(len(a["phase_loss"]["rows"]), 2)
        out = v28verdict.render(a)
        self.assertIn("PHASE LOSS", out)
        self.assertIn("p1 3a", out)
        self.assertIn("underruns 3", out)


if __name__ == "__main__":
    unittest.main()
