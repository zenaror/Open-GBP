/*
 * tests/unit/test_gbp_v28_nulling.c — GitHub Issue #129/#130: gbp_v28_nulling, the native port of
 * gbp_async's own Phase 2, against the REAL gbp_atrans2/gbp_aplay2/gbp_adec2 chain -- same two-layer
 * shape as test_gbp_v28_3a.c/test_gbp_v28_3b.c (the module calls gbp_atrans2_begin() directly).
 *
 * Mirrors test_gbp_async.c's own "a step value that is not a stick is refused" test (Defect 2
 * there): the value check precedes the busy check, never mapped, counted apart.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_v28_nulling.h"
#include "gbp_v28_ladder.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

static void check(int cond, const char *what)
{
    checks++;
    if (!cond) {
        failures++;
        printf("  FAIL: %s\n", what);
    }
}

/* ---- the real chain, verbatim from test_gbp_v28_3b.c's own harness. ---- */
static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t ring[GBP_APLAY2_RING];
static int16_t keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events[GBP_APLAY2_EVENTS_CAP];
static struct gbp_aplay2 ap;
static struct gbp_adec2 adec;
static struct gbp_atrans2 tr;
static struct gbp_v28_nulling nl;

#define CALLS_PER_PERIOD 125u   /* the console's own: 124.8 pump calls per hand-off period (RUN 52 log, Issue #136); not 16 */

static void give2(struct gbp_adec2 *d, uint32_t n, int16_t v)
{
    uint32_t k;
    for (k = 0; k < n && d->count < d->cap; k++) {
        d->ring[(d->head + d->count) % d->cap] = v;
        d->count++;
    }
}

static uint32_t slice2(uint32_t k)
{
    return (k + 1u) * GBP_APLAY2_PUSHES / CALLS_PER_PERIOD - k * GBP_APLAY2_PUSHES / CALLS_PER_PERIOD;
}

static void pump2(uint64_t now)
{
    int b;
    (void)now;
    if (tr.active) (void)gbp_atrans2_step(&tr, &ap, &adec, now, &b);
    else b = gbp_aplay2_produce(&ap, &adec);
    if (b >= 0) gbp_aplay2_queue(&ap, b);
    gbp_aplay2_process(&ap);
}

static void prime_period2(uint64_t *now)
{
    uint32_t k;
    int done = 0;
    for (k = 0; k < CALLS_PER_PERIOD; k++) {
        give2(&adec, slice2(k), 100);
        if (!done) {
            int b = gbp_aplay2_produce(&ap, &adec);
            if (b >= 0) { gbp_aplay2_queue(&ap, b); done = 1; }
        }
        gbp_aplay2_process(&ap);
        (*now)++;
    }
}

/* the chain steady at T256, AHEAD 2 -- deliberately not 4, so a test that finds AHEAD unchanged
 * throughout is not vacuously true at some module-internal default. */
static uint64_t steady(void)
{
    uint64_t now = 0;
    uint32_t i, k;
    memset(&ap, 0, sizeof ap);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    gbp_atrans2_init(&tr);
    ap.ahead = GBP_V28_A2;
    gbp_aplay2_set_target(&ap, GBP_V28_T256);
    give2(&adec, GBP_V28_T256 * GBP_V28_A2, 100);
    for (i = 0; i < GBP_V28_A2; i++) prime_period2(&now);
    ap.playing = 1u;
    for (i = 0; i < 6u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(now); now++; }
    }
    return now;
}

/* pumps the chain until the current transition lands (tr.active back to 0), bounded. */
static void settle(uint64_t *now, uint32_t max_periods)
{
    uint32_t i, k;
    for (i = 0; i < max_periods && tr.active; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, *now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(*now); (*now)++; }
    }
}

/* setting 0 and setting 1's own seeded values for SEED=12345, computed independently (Python, the
 * same xorshift32 algorithm) and hardcoded here -- not re-derived from the module under test. */
#define SEED   12345u
#define S0_START   26624u
#define S0_DIR     GBP_V28_NULLING_LEFT_SHALLOWER
#define S1_START   55296u
#define S1_DIR     GBP_V28_NULLING_LEFT_DEEPER

/* Issue #131 (RUN 48): gbp_v28_nulling_start() was never called anywhere in poc/gbp-audio-v28/
 * source/main.c either. Unlike 3a and sweep, this one does not freeze or skip visibly -- a
 * perceptual run would complete and look clean, which is why it is the worst of the three, not
 * the least. Proven directly: without start(), n->rng never leaves 0 -- xorshift32's own fixed
 * point (0 in, 0 out, forever) -- so every setting confirm()'s own lazy seeding draws is the SAME
 * degenerate (start, direction) pair, never a real one. Setting 0 itself is worse still: only
 * gbp_v28_nulling_start() ever seeds index 0 (confirm()'s own lazy path seeds the NEXT index,
 * after recording the current one), so a never-started setting 0 is recorded with p2_start==0,
 * p2_dir==0 -- raw zero-init, not even a valid grid point (GBP_V28_P2_LO is 6144). */
static void test_a_never_started_nulling_draws_the_same_degenerate_setting_forever(void)
{
    uint64_t now = steady();
    memset(&nl, 0, sizeof nl);   /* the exact bug: gbp_v28_nulling_start() is never called */
    eqi((long long)nl.rng, 0, "test setup: rng at its raw zero-init value");

    check(gbp_v28_nulling_confirm(&nl, &tr, &ap, &adec, now) == 1, "confirm() itself does not refuse");
    eqi((long long)nl.rng, 0, "xorshift32's own fixed point: 0 in, 0 out -- rng never leaves 0");
    eqi((long long)nl.settings[0].start, 0, "setting 0 was never seeded at all (only start() seeds index 0)");
    eqi((long long)nl.settings[0].direction, 0, "-- recorded as raw zero-init, not a real draw");
    eqi(nl.p2_start[1], GBP_V28_P2_LO, "index 1's own lazy seed IS drawn, but from rng==0: always P2_LO");
    eqi(nl.p2_dir[1], GBP_V28_NULLING_LEFT_DEEPER, "-- and always the same direction, never the other one");

    settle(&now, 40u);   /* land the transition confirm() just began, so a second confirm() is not refused-busy */
    check(gbp_v28_nulling_confirm(&nl, &tr, &ap, &adec, now) == 1, "the second confirm() also does not refuse");
    eqi((long long)nl.settings[1].start, GBP_V28_P2_LO, "setting 1 recorded the same degenerate value index 1 drew");
    eqi(nl.p2_start[2], GBP_V28_P2_LO, "index 2 draws the SAME value again -- not a different one, forever");
    eqi(nl.p2_dir[2], GBP_V28_NULLING_LEFT_DEEPER, "-- and the same direction again too");
}

static void test_start_seeds_and_begins(void)
{
    uint64_t now = steady();
    const uint32_t ahead0 = ap.ahead;
    check(gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED) == 1, "start applies at once (nothing else active)");
    eqi(nl.p2_start[0], S0_START, "setting 0's own seeded start (SEED=12345)");
    eqi(nl.p2_dir[0], S0_DIR, "setting 0's own seeded direction");
    eqi(nl.target, S0_START, "the module's own target tracks the seeded start");
    eqi(nl.ahead, ahead0, "AHEAD read once from the chain, held fixed");
    check(tr.active != 0, "a real transition began");
    eqi((long long)tr.mode, GBP_ATRANS2_ROTATE, "ROTATE, the step mechanism, not UNMUTED");
    eqi((long long)tr.mute, GBP_V28_STEP_MUTE, "the fixed step mute, not gbp_async's own step_mute_chunks");
    eqi((long long)tr.target, S0_START, "the plan's own target is the seeded start");
    settle(&now, 40u);
    check(!tr.active, "test setup: settled before the next call");
    eqi((long long)ap.ahead, (long long)ahead0, "AHEAD unchanged by the landing");
}

/* Defect 2's own native mirror (test_gbp_async.c): a stick value that is neither LEFT nor RIGHT is
 * refused and counted apart, checked BEFORE the busy check -- both while idle and while busy. */
static void test_step_value_that_is_not_a_stick_is_refused(void)
{
    uint64_t now = steady();
    uint32_t before_target;
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    before_target = nl.target;

    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, 2u), 0, "a value of 2 is refused, idle");
    eqi((long long)nl.refused_step_value, 1, "counted as a value");
    eqi((long long)nl.refused_step_busy, 0, "not as busy");
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, 255u), 0, "a value of 255 is refused, idle");
    eqi((long long)nl.refused_step_value, 2, "counted");
    eqi(nl.target, before_target, "the target is untouched"); eqi((long long)nl.steps, 0, "no step taken");
    check(!tr.active, "idle throughout: no plan began");

    /* now busy: begin a real (valid) step, then probe an invalid value mid-mute. */
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_RIGHT), 1, "RIGHT steps");
    check(tr.active != 0, "the step's own mute is running");
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, 9u), 0, "a bad value while busy is STILL refused as a value");
    eqi((long long)nl.refused_step_value, 3, "counted as a value, not as busy");
    eqi((long long)nl.refused_step_busy, 0, "the value check precedes the busy check -- not counted here");
}

static void test_step_deeper_and_shallower_move_by_one_grid_step(void)
{
    uint64_t now = steady();
    uint32_t deeper_stick, shallower_stick, to_deeper, to_shallower;
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    /* setting 0's own direction is SHALLOWER-for-LEFT (S0_DIR), so RIGHT is deeper here. */
    deeper_stick = GBP_V28_NULLING_RIGHT;
    shallower_stick = GBP_V28_NULLING_LEFT;

    to_deeper = nl.target + GBP_V28_P2_STEP;
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, (uint8_t)deeper_stick), 1, "deeper steps");
    eqi(nl.target, to_deeper, "target moved up by exactly one grid step");
    eqi((long long)tr.target, to_deeper, "the real plan's own target matches");
    eqi((long long)nl.steps, 1, "one step"); eqi((long long)nl.steps_deeper, 1, "one deeper");
    eqi((long long)nl.steps_shallower, 0, "none shallower");
    settle(&now, 40u);
    check(!tr.active, "test setup: settled");

    to_shallower = nl.target - GBP_V28_P2_STEP;
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, (uint8_t)shallower_stick), 1, "shallower steps");
    eqi(nl.target, to_shallower, "target moved down by exactly one grid step");
    eqi((long long)nl.steps, 2, "two steps total"); eqi((long long)nl.steps_deeper, 1, "still one deeper");
    eqi((long long)nl.steps_shallower, 1, "one shallower");
}

static void test_step_is_refused_while_busy(void)
{
    uint64_t now = steady();
    uint32_t target_at_step;
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_RIGHT), 1, "the first step applies");
    target_at_step = nl.target;
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_RIGHT), 0, "a second step, still muted, is refused");
    eqi((long long)nl.refused_step_busy, 1, "counted as busy");
    eqi(nl.target, target_at_step, "the target is untouched by the refused attempt");
    eqi((long long)nl.steps, 1, "still one step");
}

static void test_step_refuses_past_the_grid_edge(void)
{
    uint64_t now = steady();
    uint32_t stick_toward_hi, n_steps = 0u;
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    stick_toward_hi = GBP_V28_NULLING_RIGHT;   /* deeper, for setting 0's own seeded direction */
    while (nl.target < GBP_V28_P2_HI && n_steps < 64u) {
        check(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, (uint8_t)stick_toward_hi) == 1, "climbs to the edge");
        settle(&now, 40u);
        n_steps++;
    }
    eqi(nl.target, GBP_V28_P2_HI, "landed exactly on the grid's own ceiling");
    check(n_steps < 64u, "test setup: reached the ceiling within a bounded number of steps");
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, (uint8_t)stick_toward_hi), 0, "one more deeper step is refused");
    eqi((long long)nl.refused_step_end, 1, "counted as the grid's own end, not as busy or a value");
    eqi((long long)nl.refused_step_busy, 0, "not busy"); eqi((long long)nl.refused_step_value, 0, "not a value");
    check(!tr.active, "the refused attempt began no plan");
}

static void test_confirm_records_and_starts_the_next_setting(void)
{
    uint64_t now = steady();
    const struct gbp_v28_nulling_setting *rec;
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_RIGHT), 1, "one deeper step");
    settle(&now, 40u);
    eqi(gbp_v28_nulling_confirm(&nl, &tr, &ap, &adec, now), 1, "confirm applies");
    eqi((long long)nl.settings_n, 1, "one setting recorded");
    rec = gbp_v28_nulling_record(&nl, 0u);
    check(rec != NULL, "record 0 exists");
    eqi(rec->seq, 1u, "sequence 1"); eqi(rec->start, S0_START, "records setting 0's own seeded start");
    eqi(rec->direction, S0_DIR, "records setting 0's own seeded direction");
    eqi(rec->steps, 1u, "one step"); eqi(rec->steps_deeper, 1u, "one deeper"); eqi(rec->steps_shallower, 0u, "none shallower");
    eqi(rec->target, S0_START + GBP_V28_P2_STEP, "the confirmed target");
    check(gbp_v28_nulling_record(&nl, 1u) == NULL, "record 1 does not exist yet");

    /* the next setting is seeded (1 more draw beyond setting 0 -- matches S1_START/S1_DIR) and a
     * new plan began at once. */
    eqi((long long)nl.p2_index, 1, "moved to setting 1");
    eqi(nl.p2_start[1], S1_START, "setting 1's own seeded start");
    eqi(nl.p2_dir[1], S1_DIR, "setting 1's own seeded direction");
    eqi(nl.target, S1_START, "the module's own target follows setting 1's start");
    eqi((long long)nl.steps, 0, "the per-setting step counters reset");
    check(tr.active != 0, "the next setting's own START began");
    eqi((long long)tr.target, S1_START, "the real plan targets setting 1's own seeded start");
}

static void test_confirm_is_refused_while_busy(void)
{
    uint64_t now = steady();
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    /* still muted from start(): confirm before it lands */
    eqi(gbp_v28_nulling_confirm(&nl, &tr, &ap, &adec, now), 0, "confirm refused while the START's own mute runs");
    eqi((long long)nl.refused_confirm_busy, 1, "counted as busy");
    eqi((long long)nl.settings_n, 0, "nothing recorded");
}

static void test_the_whole_cap_finishes_and_further_confirms_are_refused(void)
{
    uint64_t now = steady();
    uint32_t i;
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    for (i = 0; i < GBP_V28_NULLING_CAP; i++) {
        check(!tr.active, "settled before this confirm");
        eqi(gbp_v28_nulling_confirm(&nl, &tr, &ap, &adec, now), 1, "confirm applies");
        if (i + 1u < GBP_V28_NULLING_CAP) {
            check(tr.active != 0, "the next setting's own START began");
            settle(&now, 40u);
        }
    }
    eqi((long long)nl.settings_n, (long long)GBP_V28_NULLING_CAP, "all settings recorded");
    check(gbp_v28_nulling_finished(&nl) != 0, "the exercise is finished");
    check(!tr.active, "no further plan began after the last confirm");
    eqi(gbp_v28_nulling_confirm(&nl, &tr, &ap, &adec, now), 0, "a confirm after the cap is refused");
    eqi((long long)nl.refused_confirm_over, 1, "counted as over, not as busy");
    eqi((long long)nl.refused_confirm_busy, 0, "not as busy");
}

int main(void)
{
    test_a_never_started_nulling_draws_the_same_degenerate_setting_forever();
    test_start_seeds_and_begins();
    test_step_value_that_is_not_a_stick_is_refused();
    test_step_deeper_and_shallower_move_by_one_grid_step();
    test_step_is_refused_while_busy();
    test_step_refuses_past_the_grid_edge();
    test_confirm_records_and_starts_the_next_setting();
    test_confirm_is_refused_while_busy();
    test_the_whole_cap_finishes_and_further_confirms_are_refused();
    printf("test_gbp_v28_nulling: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
