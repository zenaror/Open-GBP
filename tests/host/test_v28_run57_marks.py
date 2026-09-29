"""tests/host/test_v28_run57_marks.py -- GitHub Issue #139 / #140 (the marked-block discriminator, HARDWARE_TESTS.md V28.26).

RUN 56 read the AI DMA's start-address register as a write-through latch, so it cannot tell AHEAD + 1 (a block programmed at callback k starts at k + 1) from AHEAD + 2
(k + 2). A block of a different LENGTH can: validation_run programs a block 256 bytes shorter at the FIRST silent hand-off of each mute, and the callback at which the bytes-left
register reads the shorter block (and the interval to the next callback is 2 ms short) is the one its start is at. This file pins, without hardware:

  * the module (src/audio/gbp_v28_dma.c) against a MODEL of the hardware at each depth (AHEAD + 1, AHEAD + 2), of a length that takes effect on the block already playing, and of a
    length the AI ignores: the records the model produces, read by tools/v28latency.py dma_marks(), give M1, M2, M3 and M4 respectively;
  * the rule's thresholds, the marks' scope (a mute's FIRST silent hand-off only, never an underrun's, at most one in flight, at most GBP_V28_DMA_MARKS);
  * the wiring in main.c: the mark exists in validation_run and in no other plan, the callback has no conditional, the format strings.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import hostcc  # noqa: E402
import test_v28_diag_loss_wiring as W  # noqa: E402
import v28latency as V  # noqa: E402
import v28verdict  # noqa: E402

MAIN = W.MAIN
MAKEFILE = os.path.join(ROOT, "poc", "gbp-audio-v28", "Makefile")
AUDIO = os.path.join(ROOT, "src", "audio")

DRIVER = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_v28_dma.h"

/* the model: depth D >= 1 -- the block that STARTS at callback m is the one programmed at callback m - D; D = 0 -- the length programmed at callback m is applied to the block
 * that started at m (already playing); D = 9 -- the AI ignores the length. Time: a block of `len` bytes lasts len / 4 frames at 32 028.483 Hz, on a 40.5 MHz timebase. */
#define N 400
static uint32_t prog[N + 8];
static uint32_t lcg = 7u;
static uint32_t rnd(void) { lcg = lcg * 1664525u + 1013904223u; return lcg >> 16; }

int main(int argc, char **argv)
{
    static struct gbp_v28_dma d;
    static uint8_t buf[4];
    const int depth = atoi(argv[1]);
    const int mode = atoi(argv[2]);          /* 0 mutes of 7 every 20 callbacks; 1 underrun silences (not mutes) only; 2 mutes 1 long every 3 callbacks; 3 mutes 7 long every 8 callbacks */
    const int jitter = atoi(argv[3]);
    uint64_t t = 1000000u;
    uint32_t blk[N + 8];
    int m, q;
    gbp_v28_dma_init(&d);
    gbp_v28_dma_marks_enable(&d);
    for (m = 0; m < N + 8; m++) { blk[m] = 4000u; prog[m] = 4000u; }
    for (m = 0; m < N; m++) {
        int silent = 0, mute = 0;
        uint32_t left, len;
        if (mode == 0) { mute = (m % 20) >= 10 && (m % 20) < 17; silent = mute; }
        if (mode == 1) { silent = (m % 20) >= 10 && (m % 20) < 17; mute = 0; }
        if (mode == 2) { mute = (m % 3) == 0; silent = mute; }
        if (mode == 3) { mute = (m % 8) >= 1 && (m % 8) < 8 && (m / 8) % 2 == 0; silent = mute; }
        (void)silent;
        if (depth == 0) blk[m] = prog[m];    /* filled below, once programmed */
        else if (depth != 9) blk[m] = m - depth >= 0 ? prog[m - depth] : 4000u;
        else blk[m] = 4000u;
        left = blk[m] - 32u - ((jitter && rnd() % 20u == 0u) ? 32u : 0u);
        if (m > 0) {
            const uint64_t ticks = (uint64_t)blk[m - 1] / 4u * 40500000ull / 32028u;
            t += ticks + (jitter ? (rnd() % 6000u) : 0u);
        }
        len = gbp_v28_dma_len(&d, mute, 4000u);
        prog[m] = len;
        if (depth == 0) blk[m] = len;
        gbp_v28_dma_note(&d, 0u, left, t, buf, 0u);
        /* the depth-0 model changes an already-measured entry: the timing of the NEXT callback uses blk[m] */
    }
    printf("000700 V28MARKS n=%lu short=%lu chunk=%lu\n", (unsigned long)d.marks_n, (unsigned long)GBP_V28_DMA_MARK_SHORT, 4000ul);
    for (q = 0; q < (int)d.marks_n; q++)
        printf("000701 V28MARK i=%lu j=%lu left=%lu,%lu,%lu dur=%lu,%lu,%lu,%lu done=%lu\n", (unsigned long)q, (unsigned long)d.mark[q].j,
               (unsigned long)d.mark[q].left[0], (unsigned long)d.mark[q].left[1], (unsigned long)d.mark[q].left[2],
               (unsigned long)d.mark[q].dur[0], (unsigned long)d.mark[q].dur[1], (unsigned long)d.mark[q].dur[2],
               (unsigned long)d.mark[q].dur[3], (unsigned long)d.mark[q].done);
    (void)argc;
    return 0;
}
"""


def build():
    d = tempfile.mkdtemp(prefix="run57marks")
    src = os.path.join(d, "driver.c")
    exe = os.path.join(d, "driver")
    with open(src, "w") as f:
        f.write(DRIVER)
    have, ok, err = hostcc.compile_c(["-std=gnu11", "-Wall", "-Wextra", "-I", AUDIO, "-o", exe, src, os.path.join(AUDIO, "gbp_v28_dma.c")])
    return have, ok, err, exe


_BUILT = None


def run_model(depth, mode=0, jitter=0):
    global _BUILT
    if _BUILT is None:
        _BUILT = build()
    have, ok, err, exe = _BUILT
    hostcc.require_here(have, ok, err, what="the marked-block model driver")
    return subprocess.run([exe, str(depth), str(mode), str(jitter)], capture_output=True, text=True, check=True).stdout


class TheModelsReadAsRegistered(unittest.TestCase):
    def test_ahead_plus_one_reads_m1_and_every_mark_is_seen_one_callback_after_it(self):
        text = run_model(1)
        r = V.dma_marks(text)
        self.assertEqual(r["reading"], "M1", r["why"])
        self.assertEqual(r["offset_ms"], 0.0)
        self.assertEqual(r["complete"], 20)
        self.assertEqual(list(r["arms"].items()), [("1/1", 20)])

    def test_ahead_plus_two_reads_m2_and_shifts_every_row_up_a_chunk(self):
        r = V.dma_marks(run_model(2))
        self.assertEqual(r["reading"], "M2", r["why"])
        self.assertAlmostEqual(r["offset_ms"], V.PERIOD_MS)
        self.assertEqual(list(r["arms"].items()), [("2/2", 20)])

    def test_a_length_that_takes_effect_on_the_block_already_playing_reads_m3(self):
        r = V.dma_marks(run_model(0))
        self.assertEqual(r["reading"], "M3", r["why"])
        self.assertIsNone(r["offset_ms"])

    def test_a_length_the_ai_ignores_reads_m4_and_says_no_mark_was_seen(self):
        r = V.dma_marks(run_model(9))
        self.assertEqual(r["reading"], "M4", r["why"])
        self.assertIn("None/None", r["why"])

    def test_the_readings_survive_jitter_in_the_entry_and_the_interval(self):
        for depth, want in ((1, "M1"), (2, "M2")):
            r = V.dma_marks(run_model(depth, 0, 1))
            self.assertEqual(r["reading"], want, (depth, r["why"], r["arms"]))

    def test_the_combined_reading_moves_the_row_shift_only_when_resolved(self):
        dma = "000715 V28DMA n=1000 prev1=999 prev2=0 none=0 same12=0 left_min=3968 left_max=3968 left_mean=3968 bins=0,0,0,0,1000,0\n000716 V28DMAP new=999 kept=0 amb=1 other=0\n"
        m1 = V.dma_semantics(dma + run_model(1))
        self.assertEqual((m1["offset_ms"], m1["offset_max_ms"]), (0.0, 0.0), "resolved: the bound closes")
        self.assertIn("MARKED BLOCK M1", m1["why"])
        m2 = V.dma_semantics(dma + run_model(2))
        self.assertEqual((m2["offset_ms"], m2["offset_max_ms"]), (V.PERIOD_MS, V.PERIOD_MS))
        m4 = V.dma_semantics(dma + run_model(9))
        self.assertEqual((m4["offset_ms"], m4["offset_max_ms"]), (0.0, V.PERIOD_MS), "unresolved: the address arm's bound stands")
        none = V.dma_semantics(dma)
        self.assertIsNone(none["mark"])

    def test_the_verdict_prints_the_marked_block_line(self):
        out = v28verdict.render(v28verdict.analyse(run_model(2) + "000715 V28DMA n=1000 prev1=999 prev2=0 none=0 same12=0 left_min=3968 left_max=3968 left_mean=3968 bins=0,0,0,0,1000,0\n"))
        self.assertIn("DMA MARKED BLOCK (V28MARK, 20 marks, 20 complete", out)
        self.assertIn("M2", out)


class TheMarksScope(unittest.TestCase):
    def test_marks_only_a_mutes_first_silent_hand_off_never_an_underruns(self):
        r = V.dma_marks(run_model(1, mode=1))
        self.assertEqual(r["marks"], 0, "underrun silences (silence without a mute) are never shortened")
        self.assertEqual(r["reading"], "M4")

    def test_one_in_flight_at_most_and_a_mute_with_no_room_is_skipped(self):
        marks = V.read_marks(run_model(1, mode=2))
        js = [m["j"] for m in marks]
        self.assertTrue(all(b - a >= 4 for a, b in zip(js, js[1:])), "a mark waits until the previous one has been read (four callbacks): %s" % js[:8])
        self.assertTrue(all(m["done"] for m in marks[:-1]))

    def test_the_marks_are_at_most_the_records_capacity(self):
        text = run_model(1, mode=3)
        n = int(re.search(r"V28MARKS n=(\d+)", text).group(1))
        self.assertLessEqual(n, 48)
        self.assertEqual(n, len(V.read_marks(text)))

    def test_only_the_first_silent_hand_off_of_a_run_is_marked(self):
        marks = V.read_marks(run_model(1, mode=0))
        # mode 0: mutes of 7 starting at callbacks 10, 30, 50, ...: the mark's j is the FIRST of each run
        self.assertEqual([m["j"] for m in marks][:5], [10, 30, 50, 70, 90])

    def test_the_landing_measurements_interval_is_far_from_the_marks(self):
        """gbp_atrans2 measures the fraction of the period gone from the LAST TWO hand-off instants at the level-setting call, in the mute's second-to-last period
        (handed + 1 >= mute, the shortest mute being GBP_V28_STEP_MUTE): the interval a mark shortens is the one that STARTS at j + 1 or j + 2 and ENDS at j + 2 or j + 3."""
        step_mute = 7      # gbp_v28_ladder.h's own _Static_assert(GBP_V28_STEP_MUTE == 7u && GBP_V28_START_MUTE == 10u): a change there breaks the build first
        self.assertIn("GBP_V28_STEP_MUTE == 7u", open(os.path.join(AUDIO, "gbp_v28_ladder.h")).read())
        last_interval_starts_at = step_mute - 2          # the interval of the last two hand-offs before the cut, counting from the mute's first hand-off as 1
        marked_interval_ends_at = 1 + 3
        self.assertGreater(last_interval_starts_at, marked_interval_ends_at, "the level-setting interval must not overlap a marked one, even at lag 3")


class TheRuleThresholds(unittest.TestCase):
    def mark(self, left, dur, done=1, i=0):
        return "000701 V28MARK i=%d j=%d left=%s dur=%s done=%d" % (i, 10 + 20 * i, ",".join(map(str, left)), ",".join(map(str, dur)), done)

    def text(self, marks, short=256):
        return "000700 V28MARKS n=%d short=%d chunk=4000\n" % (len(marks), short) + "\n".join(marks) + "\n"

    N = 1264503
    S = 1183640

    def test_the_split_points_lie_between_the_ordinary_and_the_marked_readings(self):
        self.assertTrue(3712 < V.MARK_LEFT_SPLIT < 3936)
        self.assertTrue(self.S < V.MARK_DUR_SPLIT < self.N - 3000 * 3)
        self.assertEqual(3744 % 32, 0)

    def test_ten_complete_marks_at_lag_one_is_m1_and_nine_is_too_few(self):
        ok = [self.mark((3712, 3968, 3968), (self.N, self.S, self.N, self.N), i=i) for i in range(10)]
        self.assertEqual(V.dma_marks(self.text(ok))["reading"], "M1")
        self.assertEqual(V.dma_marks(self.text(ok[:9]))["reading"], "M4")

    def test_a_partial_mark_is_not_counted(self):
        ok = [self.mark((3712, 3968, 3968), (self.N, self.S, self.N, self.N), i=i) for i in range(9)]
        ok.append(self.mark((3712, 0, 0), (self.N, 0, 0, 0), done=0, i=9))
        r = V.dma_marks(self.text(ok))
        self.assertEqual((r["marks"], r["complete"], r["reading"]), (10, 9, "M4"))

    def test_ninety_percent_and_no_opposite_lag(self):
        good = self.mark((3712, 3968, 3968), (self.N, self.S, self.N, self.N))
        odd = self.mark((3968, 3968, 3968), (self.N, self.N, self.N, self.N))          # seen in neither arm
        r = V.dma_marks(self.text([good] * 9 + [odd]))
        self.assertEqual(r["reading"], "M1")                                            # 9 of 10 = 90 %
        r = V.dma_marks(self.text([good] * 8 + [odd] * 2))
        self.assertEqual(r["reading"], "M4")                                            # 80 %
        opposite = self.mark((3968, 3712, 3968), (self.N, self.N, self.S, self.N))
        r = V.dma_marks(self.text([good] * 9 + [opposite]))
        self.assertEqual(r["reading"], "M4", "one mark at lag two in either arm forbids M1 whatever the fraction")

    def test_the_two_arms_must_agree_for_a_mark_to_count(self):
        bytes_only = self.mark((3712, 3968, 3968), (self.N, self.N, self.S, self.N))    # bytes say 1, timing says 2
        r = V.dma_marks(self.text([bytes_only] * 12))
        self.assertEqual(r["reading"], "M4")
        self.assertIn("1/2: 12", r["why"])

    def test_a_wrong_mark_length_voids_the_thresholds(self):
        ok = [self.mark((3712, 3968, 3968), (self.N, self.S, self.N, self.N), i=i) for i in range(12)]
        r = V.dma_marks(self.text(ok, short=512))
        self.assertEqual(r["reading"], "M4")
        self.assertIn("not the registered", r["why"])

    def test_a_log_without_marks_reads_none(self):
        self.assertIsNone(V.dma_marks("000001 IDENT x"))


class TheMarkExistsInValidationRunAndNowhereElse(unittest.TestCase):
    def test_the_makefile_defines_the_macro_in_the_validation_branch_alone(self):
        mk = open(MAKEFILE, encoding="utf-8").read()
        self.assertEqual(mk.count("GBP_V28_DMA_MARK"), 1, "the one define")
        branch = re.search(r"ifeq \(\$\(PLAN\),validation_run\)\n(.*?)\nelse ifeq", mk, re.S).group(1)
        self.assertIn("-DGBP_V28_DMA_MARK=1", branch)
        for other in ("perceptual_no_phase1", "diag_3a_stall", "diag_loss"):
            b = re.search(r"else ifeq \(\$\(PLAN\),%s\)\n(.*?)\n(?:else|endif)" % other, mk, re.S).group(1)
            self.assertNotIn("GBP_V28_DMA_MARK", b, other)
        self.assertIn("$(EXTRA_DEFINES)", mk)

    def test_the_source_refuses_the_macro_in_any_other_plan(self):
        src = open(MAIN, encoding="utf-8").read()
        self.assertIn("#if defined(GBP_V28_DMA_MARK) && !defined(GBP_V28_PLAN_VALIDATION)\n#error", src)

    def test_the_only_uses_of_the_mark_are_under_the_macro(self):
        code = W.code(open(MAIN, encoding="utf-8").read())
        for token in ("gbp_v28_dma_len(", "gbp_v28_dma_marks_enable(", "V28MARK"):
            for m in re.finditer(re.escape(token), open(MAIN, encoding="utf-8").read()):
                before = open(MAIN, encoding="utf-8").read()[:m.start()]
                opens = len(re.findall(r"^#\s*ifdef GBP_V28_DMA_MARK", before, re.M))
                closes = len(re.findall(r"^#\s*(?:endif|else)\b", before[before.rfind("#ifdef GBP_V28_DMA_MARK"):], re.M)) if opens else 0
                self.assertTrue(opens and closes == 0, "%s at offset %d is not inside #ifdef GBP_V28_DMA_MARK ... (no #else/#endif yet)" % (token, m.start()))
        self.assertTrue(code)

    def test_the_callback_has_no_conditional_and_takes_its_length_from_the_helper(self):
        body = W.function_body(W.code(open(MAIN, encoding="utf-8").read()), "live_dma_cb")
        self.assertNotIn("if (", body)
        self.assertIn("AUDIO_InitDMA((u32)(size_t)c, dma_block_bytes(c));", body)
        helper = W.function_body(open(MAIN, encoding="utf-8").read(), "dma_block_bytes")
        self.assertIn("gbp_v28_dma_len(&v28_dma, ap2.mute_carry != 0u && c == ap2.silence, GBP_APLAY2_CHUNK_BYTES)", helper)
        self.assertIn("return GBP_APLAY2_CHUNK_BYTES;", helper)

    def test_the_teardown_lines_and_their_widths(self):
        src = open(MAIN, encoding="utf-8").read()
        f1 = "V28MARKS n=%lu short=%lu chunk=%lu"
        f2 = "V28MARK i=%lu j=%lu left=%lu,%lu,%lu dur=%lu,%lu,%lu,%lu done=%lu"
        self.assertIn('"%s"' % f1, src)
        self.assertIn('"%s"' % f2, src)
        self.assertLess(7 + len(f2) + 10 * 10, 250)
        # the marks are enabled before the callback is registered, and the lines are printed after the DMA has stopped
        self.assertLess(src.index("gbp_v28_dma_marks_enable(&v28_dma);"), src.index("AUDIO_RegisterDMACallback(live_dma_cb);"))


if __name__ == "__main__":
    unittest.main()
