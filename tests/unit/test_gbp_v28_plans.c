/*
 * tests/unit/test_gbp_v28_plans.c — GitHub Issue #129: gbp_v28_plans.h's two real plans, walked
 * by the REAL gbp_walker (not a synthetic stand-in plan, as tests/unit/test_gbp_walker.c uses for
 * its own skeleton-only checks) — proves the plans are walker-compatible (no cfg_faults, the
 * right phase kind in force at each point), not only numerically self-consistent with
 * tools/v28budget.py (tests/host/test_v28_plans.py's own scope).
 */
#include <stdio.h>
#include "gbp_v28_plans.h"

static int checks, failures;

static void check(int cond, const char *what)
{
    checks++;
    if (!cond) {
        failures++;
        printf("  FAIL: %s\n", what);
    }
}

static void test_validation_run(void)
{
    struct gbp_walker w;
    gbp_walker_start(&w, &GBP_V28_VALIDATION_RUN, 1u, 0u);
    check(w.cfg_faults == 0u, "validation_run raises no cfg_faults");
    check(gbp_walker_current_kind(&w) == GBP_WALKER_NAVIGATE, "starts at navigate/p0");

    (void)gbp_walker_tick(&w, 60u, 0);
    check(gbp_walker_current_kind(&w) == GBP_WALKER_DESCENT_3A, "p0's own 60 s cap moves to 3a");

    /* Issue #131/#133 (RUN 50, Defect B): 138 -> 168 -- 138 was the EXACT worst-case sum of 3a's
     * own dwells (gbp_v28_plans.h's own header comment has the full derivation), leaving zero
     * margin for the confirm's own natural end to ever beat the walker's own cap race. */
    (void)gbp_walker_tick(&w, 60u + 168u, 0);
    check(gbp_walker_current_kind(&w) == GBP_WALKER_HOLD_3B, "3a's own 168 s cap moves to 3b");

    (void)gbp_walker_tick(&w, 60u + 168u + 120u, 0);
    check(gbp_walker_current_kind(&w) == GBP_WALKER_SWEEP, "3b's own 120 s cap moves to sweep");

    (void)gbp_walker_tick(&w, 60u + 168u + 120u + 60u, 0);
    check(gbp_walker_finished(&w) == 1, "sweep's own 60 s cap finishes the run (408 s < the 468 s session cap)");
}

static void test_perceptual_no_phase1(void)
{
    struct gbp_walker w;
    gbp_walker_start(&w, &GBP_V28_PERCEPTUAL_NO_PHASE1, 1u, 0u);
    check(w.cfg_faults == 0u, "perceptual_no_phase1 raises no cfg_faults");
    check(gbp_walker_current_kind(&w) == GBP_WALKER_NAVIGATE, "starts at navigate/p0");

    (void)gbp_walker_tick(&w, 60u, 0);
    check(gbp_walker_current_kind(&w) == GBP_WALKER_NULLING, "p0's own 60 s cap moves to nulling");

    (void)gbp_walker_tick(&w, 60u + 240u, 0);
    check(gbp_walker_finished(&w) == 1, "nulling's own 240 s cap finishes the run (300 s < the 360 s session cap)");
}

/* Issue #153 (HARDWARE_TESTS.md V31.1): navigate -> play, a free-running phase with no handler. The play cap ends it; so does the Operator's Z (the walker's stop),
 * and a cut play phase is never counted complete. */
static void test_play_gba(void)
{
    struct gbp_walker w;
    const struct gbp_walker_phase_rec *r;
    gbp_walker_start(&w, &GBP_V28_PLAY_GBA, 1u, 0u);
    check(w.cfg_faults == 0u, "play_gba raises no cfg_faults");
    check(gbp_walker_current_kind(&w) == GBP_WALKER_NAVIGATE, "starts at navigate/p0");
    check(GBP_V28_PLAY_GBA.session_cap_s == 420u, "the session cap is 60 + 300 + 60");
    (void)gbp_walker_tick(&w, 59u, 0);
    check(gbp_walker_current_kind(&w) == GBP_WALKER_NAVIGATE, "navigate holds until its own 60 s cap");
    (void)gbp_walker_tick(&w, 60u, 0);
    check(gbp_walker_current_kind(&w) == GBP_WALKER_PLAY, "navigate's cap starts play BY ITSELF: nothing the Operator presses is needed");
    (void)gbp_walker_tick(&w, 60u + 299u, 0);
    check(gbp_walker_finished(&w) == 0, "play is still running one second before its cap");
    (void)gbp_walker_tick(&w, 60u + 300u, 0);
    check(gbp_walker_finished(&w) == 1, "play's own 300 s cap finishes the run (360 s < the 420 s session cap)");
    r = gbp_walker_phase_record(&w, 1u);
    check(r && r->ended && r->cut && r->reason == GBP_WALKER_END_PHASE_CAP, "the play phase ended by its cap, and a cap is a cut (never complete)");

    gbp_walker_start(&w, &GBP_V28_PLAY_GBA, 1u, 0u);
    (void)gbp_walker_tick(&w, 100u, 0);
    check(gbp_walker_current_kind(&w) == GBP_WALKER_PLAY, "test setup: in play at t=100");
    check((gbp_walker_stop(&w, 100u, 0) & GBP_WALKER_TICK_FINISHED) != 0, "Z ends the whole walk from play");
    r = gbp_walker_phase_record(&w, 1u);
    check(r && r->reason == GBP_WALKER_END_STOP, "and the record says STOP");

    /* a late origin does not shorten the play bound: the caps run from the walker's own origin */
    gbp_walker_start(&w, &GBP_V28_PLAY_GBA, 1u, 1000u);
    (void)gbp_walker_tick(&w, 1000u + 60u, 0);
    check(gbp_walker_current_kind(&w) == GBP_WALKER_PLAY, "the caps are relative to the origin");
}

static void test_the_busy_gate_holds_for_the_real_plans_too(void)
{
    struct gbp_walker w;
    gbp_walker_start(&w, &GBP_V28_VALIDATION_RUN, 1u, 0u);
    (void)gbp_walker_tick(&w, 1000u, 1 /* busy: well past every cap */);
    check(gbp_walker_current_kind(&w) == GBP_WALKER_NAVIGATE, "busy defers even a long-overdue cap on a real plan");
}

int main(void)
{
    test_validation_run();
    test_perceptual_no_phase1();
    test_play_gba();
    test_the_busy_gate_holds_for_the_real_plans_too();
    printf("test_gbp_v28_plans: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
