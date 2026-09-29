"""tests/host/test_v28_run57_perceptual.py -- GitHub Issue #139 / #141: the perceptual image, rebuilt on the frozen ladder (HARDWARE_TESTS.md V28.28).

  * the nulling walks the EIGHT rungs the validation sweep validated (gbp_v28_ladder.h GBP_V28_RUNG == the sweep's GATE rows 1-7, == tools/v28null.py's RUNGS), never a P2 grid;
  * the perceptual image carries NO DMA reads and NO marked block: its callback is RUN 55's, no V28DMA / V28MARK strings can be compiled in, the Makefile defines nothing extra for it;
  * the records (V28_NULL, V28CFG) and their widths; the nulling's dispatch is unchanged (start with the session seed, LEFT / RIGHT step, UP confirm);
  * tools/v28null.py: the (T, A) -> L table, CENSORED per setting and per end, the verdicts, the labels.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import test_v28_diag_loss_wiring as W  # noqa: E402
import v28latency as VL  # noqa: E402
import v28null as N  # noqa: E402

MAIN = W.MAIN
LADDER = os.path.join(ROOT, "src", "audio", "gbp_v28_ladder.h")
SWEEP = os.path.join(ROOT, "src", "audio", "gbp_v28_sweep.c")
MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-v28", "Makefile")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


NAMES = {"GBP_V28_T704": 11264, "GBP_V28_T576": 9216, "GBP_V28_T448": 7168, "GBP_V28_T320": 5120, "GBP_V28_T256": 4096, "GBP_V28_T192": 3072}


class TheLadderIsTheSweepsLadder(unittest.TestCase):
    def rungs_from_header(self):
        body = re.search(r"GBP_V28_RUNG\[GBP_V28_RUNGS\] = \{(.*?)\};", W.code(read(LADDER)), re.S).group(1)
        return [(NAMES[t], int(a[-1])) for t, a in re.findall(r"\{\s*(GBP_V28_T\d+),\s*(GBP_V28_A\d)\s*\}", body)]

    def test_eight_rungs_deepest_first(self):
        r = self.rungs_from_header()
        self.assertEqual(len(r), 8)
        self.assertEqual(re.search(r"#define GBP_V28_RUNGS (\d+)u", read(LADDER)).group(1), "8")
        self.assertEqual(r, list(N.RUNGS))

    def test_they_are_the_sweeps_own_gate_rows_1_to_7_descending(self):
        rows = re.findall(r"\{ GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_(?:STEP|REFUSED|START), (GBP_V28_T\d+), GBP_V28_A(\d), (GBP_V28_T\d+), GBP_V28_A(\d), GBP_V28_(?:STEP|START)_MUTE \}",
                          read(SWEEP))
        self.assertGreaterEqual(len(rows), 7)
        chain = [(NAMES[rows[0][0]], int(rows[0][1]))] + [(NAMES[t2], int(a2)) for (_t1, _a1, t2, a2) in rows[:7]]
        self.assertEqual(chain, list(N.RUNGS), "the descent T704A4 -> ... -> T256A1 the sweep validated (RUN 55, 56: 18 of 18) is the ladder the nulling walks")

    def test_each_rung_step_is_one_of_the_sweeps_validated_transitions(self):
        pairs = {(NAMES[a], int(b), NAMES[c], int(d)) for (a, b, c, d) in re.findall(r"GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_\w+, (GBP_V28_T\d+), GBP_V28_A(\d), (GBP_V28_T\d+), GBP_V28_A(\d)", read(SWEEP))}
        for i in range(7):
            (t1, a1), (t2, a2) = N.RUNGS[i], N.RUNGS[i + 1]
            self.assertIn((t1, a1, t2, a2), pairs, "down-step %d" % i)
            self.assertIn((t2, a2, t1, a1), pairs, "up-step %d" % i)
        self.assertIn((N.RUNGS[7][0], N.RUNGS[7][1], N.RUNGS[7][0], N.RUNGS[7][1]), pairs, "the refused press at the floor: a same-level ROTATE")
        self.assertIn((N.RUNGS[0][0], N.RUNGS[0][1], N.RUNGS[0][0], N.RUNGS[0][1]), pairs, "the refused press at the top")

    def test_the_p2_grid_is_gone_from_the_perceptual_sources(self):
        for f in (MAIN, os.path.join(ROOT, "src", "audio", "gbp_v28_nulling.c"), os.path.join(ROOT, "src", "audio", "gbp_v28_nulling.h")):
            self.assertNotRegex(W.code(read(f)), r"GBP_V28_P2_|p2_lo|p2_hi|p2_step", f)

    def test_the_l_table_of_the_rungs(self):
        self.assertEqual([round(N.rung_l(i), 1) for i in range(8)], [324.4, 293.1, 261.7, 230.4, 214.7, 183.5, 152.2, 121.0])


class ThePerceptualImageCarriesNoDmaInstrumentation(unittest.TestCase):
    def test_its_callback_is_run_55s_exactly(self):
        src = W.code(read(MAIN))
        i = re.search(r"#else\s*static void live_dma_cb\(void\)", src).start()
        j = src.index("#endif", i)
        block = src[i:j]
        self.assertIn("const uint8_t *c = gbp_aplay2_irq_handoff(&ap2, gettime());", block)
        self.assertIn("AUDIO_InitDMA((u32)(size_t)c, GBP_APLAY2_CHUNK_BYTES);", block)
        self.assertEqual(len(re.findall(r"AUDIO_\w+\(", block)), 1, "one init, no register read")
        self.assertNotIn("v28_dma", block)

    def test_every_use_of_the_dma_instrumentation_is_outside_the_perceptual_branch(self):
        src = read(MAIN)
        for m in re.finditer(r"v28_dma\b|gbp_v28_dma_\w+|dma_block_bytes|V28DMA|V28MARK", src):
            line_start = src.rfind("\n", 0, m.start()) + 1
            if src[line_start:m.start()].lstrip().startswith("#include"):
                continue                       # the pure header is included everywhere; nothing in it runs unless called
            before = src[:m.start()]
            # walk the preprocessor stack back to the file start: the token must sit under `#if !defined(GBP_V28_PLAN_PERCEPTUAL)` (or a comment)
            depth_ok = self.under_not_perceptual(before)
            self.assertTrue(depth_ok, "%r at offset %d is reachable in the perceptual image" % (m.group(0), m.start()))

    @staticmethod
    def under_not_perceptual(before):
        stack = []
        for line in before.splitlines():
            t = line.strip()
            if re.match(r"#\s*if(n?def)?\b", t):
                stack.append(t)
            elif re.match(r"#\s*else\b", t) and stack:
                stack[-1] = "!" + stack[-1]
            elif re.match(r"#\s*endif\b", t) and stack:
                stack.pop()
        # a token in the `#if !defined(PERCEPTUAL)` arm, or in the `#else` arm of `#if defined(PERCEPTUAL)`, or in a comment (the caller cannot see comments; prose mentions are in the header comment block)
        if any(s.startswith("#if !defined(GBP_V28_PLAN_PERCEPTUAL)") or s.startswith("!#if defined(GBP_V28_PLAN_PERCEPTUAL)") for s in stack):
            return True
        # comments (the explanatory blocks name these symbols in prose): a token inside an unterminated /* ... */ is fine
        return before.rfind("/*") > before.rfind("*/")

    def test_the_makefile_defines_nothing_extra_for_the_perceptual_plan(self):
        mk = read(MAKEFILE)
        b = re.search(r"else ifeq \(\$\(PLAN\),perceptual_no_phase1\)\n(.*?)\nelse", mk, re.S).group(1)
        self.assertNotIn("EXTRA_DEFINES", b)
        self.assertNotIn("GBP_V28_DMA_MARK", b)

    def test_the_two_records_and_their_widths(self):
        src = read(MAIN)
        f1 = "V28_NULL n=%lu start=%lu dir=%u steps=%lu deeper=%lu shallower=%lu floor_refused=%lu top_refused=%lu rung=%lu target=%lu ahead=%lu t=%llx"
        f2 = "V28CFG plan=%s session_cap_s=%lu wall_s=%lu step_mute=%u start_mute=%u rungs=%u"
        self.assertIn('"%s"' % f1, src)
        self.assertIn('"%s"' % f2, src)
        widths = {"lu": 10, "llx": 16, "u": 3, "s": 22}
        for f in (f1, f2):
            n = 7 + len(re.sub(r"%(?:llx|lu|u|s)", "", f)) + sum(widths[t] for t in re.findall(r"%(llx|lu|u|s)", f))
            self.assertLess(n, 250, f[:12])

    def test_the_nulling_dispatch_is_unchanged(self):
        src = W.code(read(MAIN))
        self.assertIn("(void)gbp_v28_nulling_start(&nulling, &tr, &ap2, &adec2, now, sync_seed);", src)
        self.assertIn("gbp_v28_nulling_step(&nulling, &tr, &ap2, &adec2, now, GBP_V28_NULLING_LEFT)", src)
        self.assertIn("gbp_v28_nulling_step(&nulling, &tr, &ap2, &adec2, now, GBP_V28_NULLING_RIGHT)", src)
        self.assertIn("gbp_v28_nulling_confirm(&nulling, &tr, &ap2, &adec2, now)", src)


def null_line(n, start, d, steps, deeper, shallower, fr, tr, rung, t=0x7970b55c57):
    T, A = N.RUNGS[rung]
    return "%06d V28_NULL n=%d start=%d dir=%d steps=%d deeper=%d shallower=%d floor_refused=%d top_refused=%d rung=%d target=%d ahead=%d t=%x" % (
        800 + n, n, start, d, steps, deeper, shallower, fr, tr, rung, T, A, t)


class TheReader(unittest.TestCase):
    def run_of(self, *settings):
        return "\n".join(null_line(i, *s) for i, s in enumerate(settings)) + "\n"

    def test_a_floor_censored_setting_and_the_verdict_when_all_are(self):
        text = self.run_of((3, 1, 5, 0, 5, 4, 0, 7), (0, 0, 9, 8, 1, 2, 0, 7), (5, 0, 2, 0, 2, 1, 0, 7))
        a = N.analyse(text, "bounded")
        self.assertEqual((a["k_floor"], a["k_top"], a["interior"]), (3, 0, 0))
        self.assertTrue(a["verdict"].startswith("AT THE VALIDATED FLOOR (T256, A1, L 121.0-152.2 ms)"), a["verdict"])
        self.assertIn("121.0 ms", N.analyse(text, "M1")["verdict"])
        self.assertIn("152.2 ms", N.analyse(text, "M2")["verdict"])

    def test_confirming_at_the_floor_without_pressing_against_it_is_not_censored(self):
        a = N.analyse(self.run_of((3, 1, 4, 0, 4, 0, 0, 7), (2, 0, 3, 0, 3, 0, 0, 6), (1, 1, 2, 1, 1, 0, 0, 5)), "assumed")
        self.assertEqual((a["k_floor"], a["interior"]), (0, 3))
        self.assertTrue(a["verdict"].startswith("NULL ESTIMATED from the 3 uncensored"), a["verdict"])

    def test_the_top_end_and_the_mirror_verdict(self):
        text = self.run_of((3, 1, 5, 5, 0, 0, 2, 0), (0, 0, 2, 2, 0, 0, 1, 0), (7, 0, 1, 1, 0, 0, 1, 0))
        a = N.analyse(text, "assumed")
        self.assertEqual((a["k_floor"], a["k_top"]), (0, 3))
        self.assertTrue(a["verdict"].startswith("AT THE LADDER'S TOP (T704, A4, L 324.4 ms)"), a["verdict"])
        self.assertIn("not named in #128 section 4", a["verdict"])

    def test_a_mixed_run_reports_k_of_n_and_the_bias_of_the_estimate(self):
        a = N.analyse(self.run_of((3, 1, 5, 0, 5, 4, 0, 7), (0, 0, 9, 8, 1, 2, 0, 7), (5, 0, 2, 1, 1, 0, 0, 6), (6, 1, 3, 2, 1, 0, 0, 5)), "M1")
        self.assertEqual((a["n"], a["k_floor"], a["interior"]), (4, 2, 2))
        self.assertIn("censored at the floor 2, at the top 0", a["verdict"])
        self.assertIn("biased UP", a["verdict"])
        self.assertAlmostEqual(a["null_L"], (N.rung_l(6) + N.rung_l(5)) / 2.0)

    def test_fewer_than_three_settings_is_inconclusive(self):
        a = N.analyse(self.run_of((3, 1, 5, 0, 5, 4, 0, 7), (0, 0, 9, 8, 1, 2, 0, 7)), "bounded")
        self.assertTrue(a["verdict"].startswith("INCONCLUSIVE (t4): 2 of the 3"), a["verdict"])
        self.assertTrue(N.analyse("000001 IDENT x", "bounded")["verdict"].startswith("INCONCLUSIVE (t4): 0 of the 3"))

    def test_a_record_whose_target_is_not_its_rungs_is_a_defect_not_a_finding(self):
        text = self.run_of((3, 1, 5, 0, 5, 4, 0, 7), (0, 0, 9, 8, 1, 2, 0, 7), (5, 0, 2, 0, 2, 1, 0, 7)).replace("target=4096 ahead=1", "target=4096 ahead=2", 1)
        a = N.analyse(text, "bounded")
        self.assertEqual(a["inconsistent"], 1)
        self.assertIn("DEFECT: 1 record(s)", N.render(a))

    def test_the_render_names_what_l_is_and_is_not(self):
        out = N.render(N.analyse(self.run_of((3, 1, 5, 0, 5, 4, 0, 7), (0, 0, 9, 8, 1, 2, 0, 7), (5, 0, 2, 0, 2, 1, 0, 7)), "bounded"))
        self.assertIn("NOT the audio-versus-video offset", out)
        self.assertIn("RUN 56's reading", out)

    def test_the_mechanistic_gate_reads_the_fill_ready_underruns_and_overflow(self):
        base = self.run_of((3, 1, 5, 0, 5, 4, 0, 7), (0, 0, 9, 8, 1, 2, 0, 7), (5, 0, 2, 0, 2, 1, 0, 7))
        good = "\n".join("000900 V28_NULLM n=%d ring=%d ready=%d underruns=0 overflow=0" % (i, 3100, 0) for i in range(3)) + "\n"
        a = N.analyse(base + good, "bounded")
        self.assertEqual(a["gates"], {"fill": (3, 3), "ready": (3, 3), "underruns": (3, 3), "overflow": (3, 3)})
        self.assertNotIn("(t1)", N.render(a))
        bad = good.replace("ring=3100", "ring=1200", 1).replace("underruns=0", "underruns=2", 1)     # setting 0: ring 2 896 under T256; two underruns
        a = N.analyse(base + bad, "bounded")
        self.assertEqual((a["gates"]["fill"], a["gates"]["underruns"]), ((2, 3), (2, 3)))
        out = N.render(a)
        self.assertIn("(t1) THE FILL DID NOT TRACK THE TARGET at 1 setting(s)", out)
        self.assertIn("(t2) an underrun in 1 setting(s)", out)
        self.assertEqual(N.analyse(base, "bounded")["missing_mech"], 3)
        self.assertIn("3 setting(s) with no V28_NULLM record", N.render(N.analyse(base, "bounded")))

    def test_the_mechanistic_record_and_its_format(self):
        src = read(MAIN)
        f = "V28_NULLM n=%lu ring=%lu ready=%lu underruns=%lu overflow=%lu"
        self.assertIn('"%s"' % f, src)
        self.assertNotRegex(src, r"V28_NULLM[^;]*(?:printf|gecko_puts)")

    def test_the_shift_table_matches_the_latency_tool(self):
        self.assertEqual(N.shift("bounded"), (0.0, VL.PERIOD_MS))
        self.assertEqual(N.shift("M2"), (VL.PERIOD_MS, VL.PERIOD_MS))
        self.assertEqual(N.shift("M1"), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
