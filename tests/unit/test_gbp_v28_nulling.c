/*
 * tests/unit/test_gbp_v28_nulling.c — GitHub Issue #129/#130, rebuilt on the PERCEPTUAL LADDER in Issue #139 / #141: gbp_v28_nulling
 * against the REAL gbp_atrans2/gbp_aplay2/gbp_adec2 chain -- same two-layer shape as test_gbp_v28_3a.c/test_gbp_v28_3b.c (the module
 * calls gbp_atrans2_begin() directly). One rung per step; a START (GBP_V28_START_MUTE) to a seeded rung; a press against an end of the
 * ladder is a same-level ROTATE with the step mute, counted per end.
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

/* the seeded values for SEED=12345, computed independently (Python, the same xorshift32 algorithm, rung = draw % 8) and hardcoded here -- not re-derived from the module under test:
 * setting 0: rung 2 (T448 A4), LEFT shallower; setting 1: rung 0 (T704 A4), LEFT deeper; setting 2: rung 3 (T320 A4), LEFT deeper. */
#define SEED   12345u
#define S0_RUNG    2u
#define S0_DIR     GBP_V28_NULLING_LEFT_SHALLOWER
#define S1_RUNG    0u
#define S1_DIR     GBP_V28_NULLING_LEFT_DEEPER

static void check_at_rung(uint32_t rung, const char *what)
{
    char w[160];
    snprintf(w, sizeof w, "%s: target is rung %u's T", what, rung);
    eqi(ap.target, GBP_V28_RUNG[rung].target, w);
    snprintf(w, sizeof w, "%s: AHEAD is rung %u's A", what, rung);
    eqi(ap.ahead, GBP_V28_RUNG[rung].ahead, w);
}

/* Issue #131 (RUN 48): gbp_v28_nulling_start() was never called anywhere in main.c. Unlike 3a and sweep this one does not freeze or skip visibly -- a perceptual run would
 * complete and look clean. Proven directly: without start(), n->rng never leaves 0 -- xorshift32's own fixed point -- so every setting confirm()'s own lazy seeding draws is the SAME
 * degenerate (rung, direction) pair, never a real one. */
static void test_a_never_started_nulling_draws_the_same_degenerate_setting_forever(void)
{
    uint64_t now = steady();
    memset(&nl, 0, sizeof nl);   /* the exact bug: gbp_v28_nulling_start() is never called */
    eqi((long long)nl.rng, 0, "test setup: rng at its raw zero-init value");

    check(gbp_v28_nulling_confirm(&nl, &tr, &ap, &adec, now) == 1, "confirm() itself does not refuse");
    eqi((long long)nl.rng, 0, "xorshift32's own fixed point: 0 in, 0 out -- rng never leaves 0");
    eqi((long long)nl.settings[0].start, 0, "setting 0 was never seeded at all (only start() seeds index 0)");
    eqi((long long)nl.settings[0].direction, 0, "-- recorded as raw zero-init, not a real draw");
    eqi(nl.p2_start[1], 0, "index 1's own lazy seed IS drawn, but from rng==0: always rung 0");
    eqi(nl.p2_dir[1], GBP_V28_NULLING_LEFT_DEEPER, "-- and always the same direction, never the other one");
    settle(&now, 40u);
    check(gbp_v28_nulling_confirm(&nl, &tr, &ap, &adec, now) == 1, "the second confirm() also does not refuse");
    eqi(nl.p2_start[2], 0, "index 2 draws the SAME rung again -- not a different one, forever");
    eqi(nl.p2_dir[2], GBP_V28_NULLING_LEFT_DEEPER, "-- and the same direction again too");
}

static void test_the_rungs_are_the_frozen_eight_deepest_first(void)
{
    static const uint32_t T[8] = { GBP_V28_T704, GBP_V28_T576, GBP_V28_T448, GBP_V28_T320, GBP_V28_T256, GBP_V28_T256, GBP_V28_T256, GBP_V28_T256 };
    static const uint32_t A[8] = { 4u, 4u, 4u, 4u, 4u, 3u, 2u, 1u };
    uint32_t k;
    eqi(GBP_V28_RUNGS, 8, "eight rungs");
    for (k = 0; k < 8u; k++) {
        eqi(GBP_V28_RUNG[k].target, T[k], "rung T");
        eqi(GBP_V28_RUNG[k].ahead, A[k], "rung A");
    }
    for (k = 1; k < 8u; k++) check(GBP_V28_RUNG[k].target < GBP_V28_RUNG[k - 1u].target || GBP_V28_RUNG[k].ahead < GBP_V28_RUNG[k - 1u].ahead, "each rung is shallower than the one before");
}

static void test_start_seeds_and_begins_a_start_to_the_seeded_rung(void)
{
    uint64_t now = steady();
    check(gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED) == 1, "start applies at once (nothing else active)");
    eqi(nl.p2_start[0], S0_RUNG, "setting 0's own seeded rung (SEED=12345)");
    eqi(nl.p2_dir[0], S0_DIR, "setting 0's own seeded direction");
    eqi(nl.rung, S0_RUNG, "the module's own rung tracks the seeded start");
    check(tr.active != 0, "a real transition began");
    eqi((long long)tr.mode, GBP_ATRANS2_ROTATE, "ROTATE, the step mechanism, not UNMUTED");
    eqi((long long)tr.mute, GBP_V28_START_MUTE, "a START: the mute built from the ladder's largest climb, not the step mute");
    eqi((long long)tr.target, GBP_V28_RUNG[S0_RUNG].target, "the plan's own target is the seeded rung's T");
    settle(&now, 40u);
    check(!tr.active, "test setup: settled before the next call");
    check_at_rung(S0_RUNG, "after the landing");
}

/* Defect 2's own native mirror (test_gbp_async.c): a stick value that is neither LEFT nor RIGHT is refused and counted apart, checked BEFORE the busy check. */
static void test_step_value_that_is_not_a_stick_is_refused(void)
{
    uint64_t now = steady();
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);

    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, 2u), 0, "a value of 2 is refused, idle");
    eqi((long long)nl.refused_step_value, 1, "counted as a value");
    eqi((long long)nl.refused_step_busy, 0, "not as busy");
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, 255u), 0, "a value of 255 is refused, idle");
    eqi((long long)nl.refused_step_value, 2, "counted");
    eqi(nl.rung, S0_RUNG, "the rung is untouched"); eqi((long long)nl.steps, 0, "no step taken");
    check(!tr.active, "idle throughout: no plan began");

    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_RIGHT), 1, "RIGHT steps");
    check(tr.active != 0, "the step's own mute is running");
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, 9u), 0, "a bad value while busy is STILL refused as a value");
    eqi((long long)nl.refused_step_value, 3, "counted as a value, not as busy");
    eqi((long long)nl.refused_step_busy, 0, "the value check precedes the busy check -- not counted here");
}

static void test_step_deeper_and_shallower_move_by_one_rung(void)
{
    uint64_t now = steady();
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    /* setting 0's own direction is SHALLOWER-for-LEFT (S0_DIR), so RIGHT is deeper here: rung 2 -> rung 1 (T576 A4). */
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_RIGHT), 1, "deeper steps");
    eqi(nl.rung, S0_RUNG - 1u, "one rung deeper");
    eqi((long long)tr.target, GBP_V28_RUNG[S0_RUNG - 1u].target, "the real plan's own target matches the rung");
    eqi((long long)tr.mute, GBP_V28_STEP_MUTE, "a step: the ordinary step mute");
    eqi((long long)nl.steps, 1, "one step"); eqi((long long)nl.steps_deeper, 1, "one deeper"); eqi((long long)nl.steps_shallower, 0, "none shallower");
    settle(&now, 40u);
    check_at_rung(S0_RUNG - 1u, "after the deeper step");

    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_LEFT), 1, "shallower steps");
    eqi(nl.rung, S0_RUNG, "back one rung");
    eqi((long long)nl.steps, 2, "two steps total"); eqi((long long)nl.steps_deeper, 1, "still one deeper"); eqi((long long)nl.steps_shallower, 1, "one shallower");
    settle(&now, 40u);
    check_at_rung(S0_RUNG, "after the shallower step");
}

static void test_a_step_across_the_A_boundary_changes_AHEAD_not_only_the_target(void)
{
    uint64_t now = steady();
    uint32_t k;
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    /* shallow-ward from rung 2: rungs 3 (T320 A4), 4 (T256 A4), 5 (T256 A3), 6 (T256 A2), 7 (T256 A1) */
    for (k = S0_RUNG + 1u; k < GBP_V28_RUNGS; k++) {
        eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_LEFT), 1, "a shallower step");
        settle(&now, 40u);
        check(!tr.active, "landed");
        check_at_rung(k, "after each shallower step");
    }
    eqi(nl.rung, GBP_V28_RUNGS - 1u, "the floor rung, T256 A1");
}

static void test_step_is_refused_while_busy(void)
{
    uint64_t now = steady();
    uint32_t rung_at_step;
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_RIGHT), 1, "the first step applies");
    rung_at_step = nl.rung;
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_RIGHT), 0, "a second step, still muted, is refused");
    eqi((long long)nl.refused_step_busy, 1, "counted as busy");
    eqi(nl.rung, rung_at_step, "the rung is untouched by the refused attempt");
    eqi((long long)nl.steps, 1, "still one step");
}

/* THE ENDS (#128 section 7): a press against an end is a same-level ROTATE with the SAME mute as any step, counted per end; nothing about the plan differs from a real step. */
static void test_a_press_against_an_end_is_a_same_level_rotate_counted_per_end(void)
{
    uint64_t now = steady();
    uint32_t k;
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    for (k = 0; k < S0_RUNG; k++) { eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_RIGHT), 1, "deeper"); settle(&now, 40u); }
    eqi(nl.rung, 0, "the deepest rung, T704 A4");
    eqi((long long)nl.steps, (long long)S0_RUNG, "test setup: the steps so far");

    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_RIGHT), 1, "a press deeper than the deepest rung still begins a plan (the end is not audible)");
    check(tr.active != 0, "a real transition began");
    eqi((long long)tr.mode, GBP_ATRANS2_ROTATE, "ROTATE");
    eqi((long long)tr.mute, GBP_V28_STEP_MUTE, "the SAME mute as any step");
    eqi((long long)tr.target, GBP_V28_T704, "to the same level");
    eqi((long long)nl.refused_step_end, 1, "counted as an end press");
    eqi((long long)nl.cur_refused_top, 1, "against the top (the deepest)");
    eqi((long long)nl.cur_refused_floor, 0, "not the floor");
    eqi(nl.rung, 0, "the rung did not move");
    eqi((long long)nl.steps, (long long)S0_RUNG, "and no step was counted");
    eqi((long long)nl.refused_step_busy, 0, "not busy, not a value");
    settle(&now, 40u);
    check_at_rung(0, "after the same-level landing");

    for (k = 0; k < GBP_V28_RUNGS - 1u; k++) { eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_LEFT), 1, "shallower"); settle(&now, 40u); }
    eqi(nl.rung, GBP_V28_RUNGS - 1u, "the floor rung");
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_LEFT), 1, "a press shallower than the floor begins a plan too");
    eqi((long long)tr.mute, GBP_V28_STEP_MUTE, "the same mute");
    eqi((long long)tr.target, GBP_V28_T256, "the floor's T");
    eqi((long long)nl.cur_refused_floor, 1, "counted against the floor");
    eqi((long long)nl.cur_refused_top, 1, "the top's own count is untouched");
    eqi((long long)nl.refused_step_end, 2, "both ends, total");
    settle(&now, 40u);
    check_at_rung(GBP_V28_RUNGS - 1u, "after the floor's same-level landing");
}

static void test_confirm_records_and_starts_the_next_setting(void)
{
    uint64_t now = steady();
    const struct gbp_v28_nulling_setting *rec;
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    eqi(gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_RIGHT), 1, "one deeper step (rung 2 -> 1)");
    settle(&now, 40u);
    ap.underruns += 3u;          /* three AI underruns during the setting */
    adec.overflow += 5u;         /* five dropped samples */
    {
        const uint32_t ring_at_confirm = adec.count, ready_at_confirm = gbp_aplay2_ready(&ap);
        eqi(gbp_v28_nulling_confirm(&nl, &tr, &ap, &adec, now), 1, "confirm applies");
        rec = gbp_v28_nulling_record(&nl, 0u);
        eqi(rec->ring, ring_at_confirm, "the ring's level at the confirm");
        eqi(rec->ready, ready_at_confirm, "the READY chunks at the confirm");
    }
    eqi(rec->underruns, 3u, "the AI underruns DURING the setting");
    eqi(rec->overflow, 5u, "the ring's dropped samples DURING the setting");
    eqi((long long)nl.settings_n, 1, "one setting recorded");
    rec = gbp_v28_nulling_record(&nl, 0u);
    check(rec != NULL, "record 0 exists");
    eqi(rec->seq, 1u, "sequence 1"); eqi(rec->start, S0_RUNG, "records setting 0's own seeded start rung");
    eqi(rec->direction, S0_DIR, "records setting 0's own seeded direction");
    eqi(rec->steps, 1u, "one step"); eqi(rec->steps_deeper, 1u, "one deeper"); eqi(rec->steps_shallower, 0u, "none shallower");
    eqi(rec->refused_floor, 0u, "no floor press"); eqi(rec->refused_top, 0u, "no top press");
    eqi(rec->rung, S0_RUNG - 1u, "the confirmed rung");
    eqi(rec->target, GBP_V28_T576, "its T"); eqi(rec->ahead, 4u, "its A");
    check(gbp_v28_nulling_record(&nl, 1u) == NULL, "record 1 does not exist yet");

    eqi((long long)nl.p2_index, 1, "moved to setting 1");
    eqi(nl.p2_start[1], S1_RUNG, "setting 1's own seeded rung");
    eqi(nl.p2_dir[1], S1_DIR, "setting 1's own seeded direction");
    eqi(nl.rung, S1_RUNG, "the module's own rung follows setting 1's start");
    eqi((long long)nl.steps, 0, "the per-setting step counters reset");
    eqi((long long)nl.cur_refused_floor + (long long)nl.cur_refused_top, 0, "and the per-end counters");
    eqi((long long)nl.u0, (long long)ap.underruns, "the underrun baseline is re-taken at the next setting's begin");
    eqi((long long)nl.o0, (long long)adec.overflow, "and the overflow baseline");
    check(tr.active != 0, "the next setting's own START began");
    eqi((long long)tr.mute, GBP_V28_START_MUTE, "under the START mute");
    eqi((long long)tr.target, GBP_V28_RUNG[S1_RUNG].target, "to setting 1's own seeded rung");
}

static void test_confirm_records_the_end_presses_of_its_own_setting(void)
{
    uint64_t now = steady();
    const struct gbp_v28_nulling_setting *rec;
    uint32_t k;
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    settle(&now, 40u);
    for (k = 0; k < 6u; k++) { (void)gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_LEFT); settle(&now, 40u); }     /* to the floor and past it: 5 steps, 1 press */
    eqi(nl.rung, GBP_V28_RUNGS - 1u, "at the floor");
    (void)gbp_v28_nulling_step(&nl, &tr, &ap, &adec, now, GBP_V28_NULLING_LEFT); settle(&now, 40u);                                     /* a second press against it */
    eqi(gbp_v28_nulling_confirm(&nl, &tr, &ap, &adec, now), 1, "confirm at the floor");
    rec = gbp_v28_nulling_record(&nl, 0u);
    eqi(rec->rung, GBP_V28_RUNGS - 1u, "confirmed at the floor rung");
    eqi(rec->refused_floor, 2u, "two presses against the floor: the CENSORED operand (#128 section 4)");
    eqi(rec->refused_top, 0u, "none against the top");
    eqi(rec->steps, 5u, "five real steps");
    eqi(rec->target, GBP_V28_T256, "T256"); eqi(rec->ahead, 1u, "A1");
    eqi((long long)nl.cur_refused_floor, 0, "the next setting starts its own count");
    eqi((long long)nl.refused_step_end, 2, "the session total keeps both");
}

static void test_confirm_is_refused_while_busy(void)
{
    uint64_t now = steady();
    (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, SEED);
    eqi(gbp_v28_nulling_confirm(&nl, &tr, &ap, &adec, now), 0, "confirm refused while the START's own mute runs");
    eqi((long long)nl.refused_confirm_busy, 1, "counted as busy");
    eqi((long long)nl.settings_n, 0, "nothing recorded");
}

static void test_every_rung_is_a_reachable_start(void)
{
    uint32_t seen[8] = { 0 }, seed, k;
    for (seed = 1u; seed <= 160u; seed++) {
        uint64_t now = steady();
        (void)gbp_v28_nulling_start(&nl, &tr, &ap, &adec, now, seed);
        check(nl.p2_start[0] < GBP_V28_RUNGS, "a start is always one of the eight rungs");
        seen[nl.p2_start[0] % 8u]++;
    }
    for (k = 0; k < 8u; k++) check(seen[k] >= 8u && seen[k] <= 40u, "each rung is drawn about a eighth of the time (160 seeds: 8..40)");
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
            check(!tr.active, "and landed within the START's own mute");
            check_at_rung(nl.rung, "each start lands on its own rung (T and A)");
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
    test_the_rungs_are_the_frozen_eight_deepest_first();
    test_start_seeds_and_begins_a_start_to_the_seeded_rung();
    test_step_value_that_is_not_a_stick_is_refused();
    test_step_deeper_and_shallower_move_by_one_rung();
    test_a_step_across_the_A_boundary_changes_AHEAD_not_only_the_target();
    test_step_is_refused_while_busy();
    test_a_press_against_an_end_is_a_same_level_rotate_counted_per_end();
    test_confirm_records_and_starts_the_next_setting();
    test_confirm_records_the_end_presses_of_its_own_setting();
    test_confirm_is_refused_while_busy();
    test_every_rung_is_a_reachable_start();
    test_the_whole_cap_finishes_and_further_confirms_are_refused();
    printf("test_gbp_v28_nulling: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
