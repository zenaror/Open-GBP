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

    (void)gbp_walker_tick(&w, 60u + 138u, 0);
    check(gbp_walker_current_kind(&w) == GBP_WALKER_HOLD_3B, "3a's own 138 s cap moves to 3b");

    (void)gbp_walker_tick(&w, 60u + 138u + 120u, 0);
    check(gbp_walker_current_kind(&w) == GBP_WALKER_SWEEP, "3b's own 120 s cap moves to sweep");

    (void)gbp_walker_tick(&w, 60u + 138u + 120u + 60u, 0);
    check(gbp_walker_finished(&w) == 1, "sweep's own 60 s cap finishes the run (378 s < the 438 s session cap)");
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
    test_the_busy_gate_holds_for_the_real_plans_too();
    printf("test_gbp_v28_plans: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
