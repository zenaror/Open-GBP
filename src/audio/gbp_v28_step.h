/*
 * gbp_v28_step -- the production step of the native path (GitHub Issue #138, RUN 54, U-GBP-050): how many pushes one pump call takes.
 *
 * WHY. RUN 54 (`HARDWARE_TESTS.md` section V28.18, `GBP-HW-364`) manipulated it: at 128 pushes a call (`GBP_APLAY2_STEP_PUSHES`, the value
 * gbp_aplay2.h chose to keep the frozen path's decode-TIME granularity, 1.953 ms) the drain's block loss is 0.902 percentage points higher than
 * at 64, with the label off and the tap unchanged. A 128-push call is 2k-4k ticks (486 a second), a 64-push call 1k-2k; the pump call's
 * 4k-8k stretches fall from 236 to 23 a second and the gap between consecutive taps of 1.5-2.5 block periods from 55 to 16 a second.
 *
 * WHAT IT CHANGES, AND WHAT IT DOES NOT. Only the partition of a chunk's 2048 pushes into pump calls: the same samples, the same arithmetic,
 * the same DUP/DROP decisions (taken at sub-block starts, every 128 pushes, and 64 divides 128 so no call passes one uncorrected). The output
 * is byte-identical for any step that divides 128: tests/unit/test_v28_step_partition.c proves it on the real chain.
 *
 * ONE MODE, EVERYWHERE, TRANSITIONS INCLUDED (the Orchestrator's rule on #138: every defect this front found lived at a state boundary, so no step
 * that flips on `tr.active`). What the ROTATE landing needed for that, and nothing more: the landing call finds the ring after its own recovery
 * produce, ONE production call of `step` pushes, so at 64 the landing rose from target - 160 to target - 96 and the lateness it tolerates fell
 * from 2.44 ms to 1.47 ms. gbp_atrans2 now aims the cut `GBP_ATRANS2_LAND_POINT (160) - step` below the level it wants (32 at 128, 96 at 64), which puts
 * the landing at target - 160 at both steps; the mutes (sample-flow derivations) need no change. The pump's minimum call rate doubles: a chunk is 32
 * calls, AHEAD 4 wants about 72 calls a period (about 36 at 128; jitter 42), the console's 122-125 is a 1.7x margin (3.0x at 128), and the whole
 * landing battery passes at both steps (tests/unit/test_v28_sweep_landing.c, which also pins the floor: 64 calls a period fails at 64 pushes).
 * The hook is asked once per chunk, at its start.
 *
 * WHY NOT 32. RUN 54 has no data for it, and what it has argues against the need: a working 64-push call is about 1.3k ticks (RUN 54: 1 316k ticks
 * a second over 1 021 working calls; 2.5k at 128), RUN 43's 8-push call was about 1 021 ticks, and the loss with the label off and 64 pushes (0.16-0.20 %) is RUN 43's 0.18 %: the remaining
 * floor does not look like it is set by the production call's length. Halving again would double the working calls to 64 a chunk (2 044 a second
 * against about 4 000 pump calls a second: half of them), cost about 80 ticks a call more (RUN 54: 41k ticks a second for the 511 extra calls
 * from 128 to 64, 0.10 % of the CPU; 0.20 % more at 32), and leave the 4k-8k pump stretches, which are not production's, where they are.
 */
#ifndef OPENGBP_GBP_V28_STEP_H
#define OPENGBP_GBP_V28_STEP_H

#include <stdint.h>
#include "gbp_aplay2.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_V28_STEP_STEADY 64u      /* the steady-state production step */

_Static_assert(GBP_APLAY2_STEP_PUSHES % GBP_V28_STEP_STEADY == 0u,
    "gbp_v28_step: the steady step must divide the sub-block (128): a call that passed a sub-block start uncorrected would change the output");
_Static_assert(GBP_V28_STEP_STEADY < GBP_APLAY2_STEP_PUSHES, "gbp_v28_step: the steady step is smaller than the transition step");
_Static_assert(GBP_APLAY2_PUSHES % GBP_V28_STEP_STEADY == 0u, "gbp_v28_step: a chunk is a whole number of steady calls");

/* gbp_aplay2's `step_pushes` hook: every chunk of every image that installs it takes the steady step. */
static inline uint32_t gbp_v28_step_hook(void *user, uint32_t seq)
{
    (void)user;
    (void)seq;
    return GBP_V28_STEP_STEADY;
}

#ifdef __cplusplus
}
#endif
#endif
