/*
 * gbp_v28_plans -- the two runs §V28 freezes (GitHub Issue #128 §2: "the two runs, with their
 * figures"), as gbp_walker.h's own ordered-list-of-phase-kinds shape (GitHub Issue #129).
 *
 * ONE SOURCE FOR THE PLANS, SHARED WITH tools/v28budget.py (the Orchestrator's own review of
 * #129's architecture, point 3): the phase names, their seconds and the session cap below are
 * the SAME table `tools/v28budget.py`'s own `PLANS["validation_run"]` /
 * `PLANS["perceptual_no_phase1"]` hold, and tests/host/test_v28_plans.py imports that module
 * directly and compares every field against this header's own text, so the two cannot drift
 * apart silently.
 *
 * validation_run        navigate(60, "allowance") -> 3a(138, "§V27 budget")
 *                        -> 3b(120, "AHEAD holds: 1, then 2 on an underrun") -> sweep(60, "ROTATE steps")
 *                        session cap 438 (60+138+120+60 = 378, + GBP_V28_SLACK_S 60)
 * perceptual_no_phase1  navigate(60, "allowance") -> nulling(240, "cap")
 *                        session cap 360 (60+240 = 300, + GBP_V28_SLACK_S 60)
 *
 * Phase 1 is in NEITHER list (#128 §2 point 3: dropped from both runs). GBP_V28_P0_ALLOWANCE_S and
 * GBP_V28_SLACK_S are tools/v28budget.py's own P0_ALLOWANCE_S/SLACK_S (§V27.9's O4: navigate/p0
 * gets an explicit allowance like every other phase, not a special case; the session cap sits
 * above the phases' own sum by the slack, the seconds p0 may overrun before the last phase is cut).
 *
 * The phase-kind HANDLERS (3a's bisection, 3b's hold, sweep's steps, nulling) are not this file's
 * scope -- these are only the two plans a caller hands to gbp_walker_start().
 */
#ifndef OPENGBP_GBP_V28_PLANS_H
#define OPENGBP_GBP_V28_PLANS_H

#include "gbp_walker.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_V28_P0_ALLOWANCE_S   60u     /* tools/v28budget.py's P0_ALLOWANCE_S */
#define GBP_V28_SLACK_S          60u     /* tools/v28budget.py's SLACK_S */

/* ---- validation_run: navigate -> 3a -> 3b -> sweep --------------------------------------- */
static const struct gbp_walker_phase_def GBP_V28_VALIDATION_RUN_PHASES[4] = {
    { GBP_WALKER_NAVIGATE,   GBP_V28_P0_ALLOWANCE_S },   /* p0, "allowance" */
    { GBP_WALKER_DESCENT_3A, 138u },                      /* 3a, "§V27 budget" */
    { GBP_WALKER_HOLD_3B,    120u },                      /* 3b, "AHEAD holds: 1, then 2 on an underrun" */
    { GBP_WALKER_SWEEP,       60u },                      /* sweep, "ROTATE steps" */
};
#define GBP_V28_VALIDATION_RUN_SUM_S (GBP_V28_P0_ALLOWANCE_S + 138u + 120u + 60u)
#define GBP_V28_VALIDATION_RUN_CAP_S (GBP_V28_VALIDATION_RUN_SUM_S + GBP_V28_SLACK_S)
_Static_assert(GBP_V28_VALIDATION_RUN_CAP_S == 438u,
    "gbp_v28_plans: validation_run's session cap no longer matches tools/v28budget.py's own 438");

static const struct gbp_walker_plan GBP_V28_VALIDATION_RUN = {
    GBP_V28_VALIDATION_RUN_PHASES, 4u, GBP_V28_VALIDATION_RUN_CAP_S
};

/* ---- perceptual_no_phase1: navigate -> nulling ------------------------------------------- */
static const struct gbp_walker_phase_def GBP_V28_PERCEPTUAL_NO_PHASE1_PHASES[2] = {
    { GBP_WALKER_NAVIGATE, GBP_V28_P0_ALLOWANCE_S },      /* p0, "allowance" */
    { GBP_WALKER_NULLING,  240u },                         /* nulling, "cap" */
};
#define GBP_V28_PERCEPTUAL_NO_PHASE1_SUM_S (GBP_V28_P0_ALLOWANCE_S + 240u)
#define GBP_V28_PERCEPTUAL_NO_PHASE1_CAP_S (GBP_V28_PERCEPTUAL_NO_PHASE1_SUM_S + GBP_V28_SLACK_S)
_Static_assert(GBP_V28_PERCEPTUAL_NO_PHASE1_CAP_S == 360u,
    "gbp_v28_plans: perceptual_no_phase1's session cap no longer matches tools/v28budget.py's own 360");

static const struct gbp_walker_plan GBP_V28_PERCEPTUAL_NO_PHASE1 = {
    GBP_V28_PERCEPTUAL_NO_PHASE1_PHASES, 2u, GBP_V28_PERCEPTUAL_NO_PHASE1_CAP_S
};

/* ---- diag_3a_stall: navigate -> 3a, short -- Issue #131 (RUN 48's own diagnostic build) -------
 *
 * RUN 48's own phase 1 (3a) ran its full 138 s budget without recording a single depth. This plan
 * exists only to catch that same stall in about two minutes of Operator time instead of six: 3a's
 * own dwell (GBP_V28_3A_DWELL_S = 6 s) needs far less than 60 s to record at least one depth if the
 * hand-off is healthy, and a still-empty depths_n at this phase's own cap is itself the finding.
 * validation_run stays the thing that gets re-run once this is understood -- this plan never
 * replaces it, only isolates the one phase RUN 48 could not get past. */
static const struct gbp_walker_phase_def GBP_V28_DIAG_3A_STALL_PHASES[2] = {
    { GBP_WALKER_NAVIGATE,   GBP_V28_P0_ALLOWANCE_S },   /* p0, "allowance" */
    { GBP_WALKER_DESCENT_3A, 60u },                       /* 3a, short -- RUN 48's own stall, caught faster */
};
#define GBP_V28_DIAG_3A_STALL_SUM_S (GBP_V28_P0_ALLOWANCE_S + 60u)
#define GBP_V28_DIAG_3A_STALL_CAP_S (GBP_V28_DIAG_3A_STALL_SUM_S + GBP_V28_SLACK_S)
_Static_assert(GBP_V28_DIAG_3A_STALL_CAP_S == 180u,
    "gbp_v28_plans: diag_3a_stall's session cap no longer matches tools/v28budget.py's own 180");

static const struct gbp_walker_plan GBP_V28_DIAG_3A_STALL = {
    GBP_V28_DIAG_3A_STALL_PHASES, 2u, GBP_V28_DIAG_3A_STALL_CAP_S
};

#ifdef __cplusplus
}
#endif
#endif
