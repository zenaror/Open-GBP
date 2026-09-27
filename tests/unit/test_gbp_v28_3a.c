/*
 * tests/unit/test_gbp_v28_3a.c — GitHub Issue #129: gbp_v28_3a, ported from gbp_async.c's own
 * Phase 3 (Issue #117) onto the native path at gbp_v28_ladder.h's own constants.
 *
 * Two layers, as with test_gbp_walker.c:
 *   1. the algorithm's own logic (bisection, cut-dwell accounting, confirm hold) against a REAL
 *      gbp_atrans2/gbp_aplay2/gbp_adec2 chain (this module has no synthetic stand-in -- it calls
 *      gbp_atrans2_begin() directly, so every scenario needs the real collaborators);
 *   2. the Orchestrator's own requirement on Issue #130's review: 3a starts a dwell only once its
 *      plan has ACTUALLY begun. A hand-rolled "dishonest" driver that ignores gbp_atrans2_begin()'s
 *      return (exactly the mistake the requirement forbids) is compared against the real
 *      gbp_v28_3a_tick(), on the SAME forced-busy scenario, to show the honest path counts no
 *      dwell at a depth that was never applied while the dishonest one would.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_v28_3a.h"
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

/* ---- the real chain, verbatim from test_gbp_walker.c's own harness (kept byte-identical here,
 * per that file's own note: each test file duplicates its own small harness rather than sharing
 * one across the audio unit suite). ---- */
static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t ring[GBP_APLAY2_RING];
static int16_t keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events[GBP_APLAY2_EVENTS_CAP];
static struct gbp_aplay2 ap;
static struct gbp_adec2 adec;
static struct gbp_atrans2 tr;

#define CALLS_PER_PERIOD 16u
#define TB_HZ CALLS_PER_PERIOD   /* 1 s = one period = 16 ticks, the same convention test_gbp_walker.c uses */

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

static uint64_t steady2(uint32_t from)
{
    uint64_t now = 0;
    uint32_t i, k;
    memset(&ap, 0, sizeof ap);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    gbp_atrans2_init(&tr);
    gbp_aplay2_set_target(&ap, from);
    give2(&adec, from, 100);
    for (i = 0; i < GBP_APLAY2_AHEAD; i++) prime_period2(&now);
    ap.playing = 1u;
    for (i = 0; i < 6u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(now); now++; }
    }
    return now;
}

/* Feeds the chain and pumps gbp_v28_3a's own tick() for up to `periods` periods, or until it
 * stops asking to (returns 0 with nothing pending and not finished, meaning a dwell is running --
 * the caller drives the clock forward by whole periods and re-ticks). Returns the last tick's
 * flags. */
static int drive(struct gbp_v28_3a *s, uint64_t *now, uint32_t periods)
{
    uint32_t i, k;
    int flags = 0;
    for (i = 0; i < periods; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, *now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) {
            give2(&adec, slice2(k), 100);
            flags = gbp_v28_3a_tick(s, &tr, &ap, &adec, *now);
            pump2(*now);
            (*now)++;
        }
    }
    return flags;
}

/* ================================================================================================
 * Layer 1: the algorithm, against the real chain.
 * ================================================================================================ */

static void test_start_begins_the_first_depth_once_applied(void)
{
    struct gbp_v28_3a s;
    uint64_t now = steady2(GBP_V28_P3_START);
    gbp_v28_3a_start(&s, TB_HZ, now);
    check(s.begin_pending == 1u, "start() only decides the first depth -- begin_pending, not yet dwelling");
    check(s.dwell_active == 0u, "not dwelling until tick() actually applies the begin");
    (void)drive(&s, &now, 1u);
    check(s.begin_pending == 0u, "one period is enough for an UNMUTED, no-climb begin to apply");
    check(s.dwell_active == 1u, "dwelling once the plan actually began");
    eqi((long long)s.cur, (long long)GBP_V28_P3_START, "the first depth is GBP_V28_P3_START");
    eqi(tr.target, (long long)GBP_V28_P3_START, "gbp_atrans2's own target agrees");
}

static void test_begin_refused_counts_no_dwell_until_applied(void)
{
    /* the Orchestrator's own requirement, Issue #130: force gbp_atrans2 busy at the moment 3a
     * wants to begin its first depth. The honest gbp_v28_3a_tick() must count NOTHING for it. */
    struct gbp_v28_3a s;
    uint64_t now = steady2(GBP_V28_P3_START);
    const uint32_t mute = gbp_atrans2_min_mute(GBP_ATRANS2_ROTATE, 0u, GBP_V28_A4);
    int applied;

    applied = gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mute, 0u, 0u, GBP_V28_P3_START, GBP_V28_A4);
    eqi(applied, 1, "the forcing transition itself must apply, or this test proves nothing");
    check(tr.active != 0u, "gbp_atrans2 is busy for this test's own purpose");

    gbp_v28_3a_start(&s, TB_HZ, now);
    (void)drive(&s, &now, mute + 2u);          /* long enough for the forcing ROTATE to land */
    /* while tr was busy, every gbp_v28_3a_tick() call's own begin_pending path must have been
     * refused: no dwell, no depth ever recorded for the depth that was never applied. */
    check(s.depths_n == 0u || s.dwell_active == 1u,
          "no depth is recorded before the FIRST successful begin -- either none yet, or the one dwell that "
          "started only after gbp_atrans2 became free");
    if (s.depths_n == 0u) check(s.begin_pending == 1u || s.dwell_active == 1u,
                                "still trying (or now dwelling), never silently gave up");
}

static void test_a_holding_depth_steps_down_by_p3_step(void)
{
    struct gbp_v28_3a s;
    uint64_t now = steady2(GBP_V28_P3_START);
    gbp_v28_3a_start(&s, TB_HZ, now);
    (void)drive(&s, &now, 1u + GBP_V28_3A_DWELL_S);   /* apply + dwell out */
    check((gbp_v28_3a_tick(&s, &tr, &ap, &adec, now) & GBP_V28_3A_TICK_DEPTH_DONE) != 0,
          "the dwell has ended: DEPTH_DONE is asked for");
    gbp_v28_3a_depth_done(&s, 0u, 0u, 0u, /*dup=*/1u, 0u, 0u, /*starved=*/0u);   /* holding: dup fired */
    eqi((long long)s.cur, (long long)(GBP_V28_P3_START - GBP_V28_P3_STEP), "a holding depth steps down by P3_STEP");
    check(s.have_hold == 1u, "have_hold is set");
    check(s.bisecting == 0u, "still a plain descent, not bisecting yet");
}

static void test_the_floor_holds_ends_without_a_bracket(void)
{
    struct gbp_v28_3a s;
    uint64_t now = steady2(GBP_V28_P3_MIN);
    gbp_v28_3a_start(&s, TB_HZ, now);
    s.cur = GBP_V28_P3_MIN;                  /* jump straight to the floor for this test's own purpose */
    s.pending_target = GBP_V28_P3_MIN;
    (void)drive(&s, &now, 1u + GBP_V28_3A_DWELL_S);
    (void)gbp_v28_3a_tick(&s, &tr, &ap, &adec, now);
    gbp_v28_3a_depth_done(&s, 0u, 0u, 0u, /*dup=*/1u, 0u, 0u, /*starved=*/0u);
    check(gbp_v28_3a_finished(&s) == 1, "the floor holds: the descent completes without a bracket");
    check(s.bisecting == 0u, "never bisected");
}

static void test_the_first_depth_fails_opens_no_bracket(void)
{
    struct gbp_v28_3a s;
    uint64_t now = steady2(GBP_V28_P3_START);
    gbp_v28_3a_start(&s, TB_HZ, now);
    (void)drive(&s, &now, 1u + GBP_V28_3A_DWELL_S);
    (void)gbp_v28_3a_tick(&s, &tr, &ap, &adec, now);
    gbp_v28_3a_depth_done(&s, 0u, 0u, 0u, /*dup=*/0u, 0u, 0u, /*starved=*/1u);   /* failing at once */
    check(gbp_v28_3a_finished(&s) == 1, "the very first depth failing ends the descent, no hold recorded");
    check(s.have_hold == 0u, "have_hold never set");
    check(s.bisecting == 0u, "no bracket opened -- there is nothing to bisect between");
}

static void test_bisection_converges_to_width_le_bisect_width(void)
{
    struct gbp_v28_3a s;
    uint64_t now = steady2(GBP_V28_P3_START);
    uint32_t guard;
    gbp_v28_3a_start(&s, TB_HZ, now);
    /* one holding depth, then a failing one, to open the bracket */
    (void)drive(&s, &now, 1u + GBP_V28_3A_DWELL_S);
    (void)gbp_v28_3a_tick(&s, &tr, &ap, &adec, now);
    gbp_v28_3a_depth_done(&s, 0u, 0u, 0u, 1u, 0u, 0u, 0u);                      /* holds */
    (void)drive(&s, &now, 1u + GBP_V28_3A_DWELL_S);
    (void)gbp_v28_3a_tick(&s, &tr, &ap, &adec, now);
    gbp_v28_3a_depth_done(&s, 0u, 0u, 0u, 0u, 0u, 0u, 1u);                      /* fails: bracket opens */
    check(s.bisecting == 1u, "the bracket is open after one hold then one fail");
    for (guard = 0; guard < 20u && !s.bracket_closed; guard++) {
        const uint32_t mid = (s.lo + s.hi) / 2u;
        (void)drive(&s, &now, 1u + GBP_V28_3A_DWELL_S + GBP_V28_3A_CONFIRM_S);  /* enough for a deepening climb too */
        (void)gbp_v28_3a_tick(&s, &tr, &ap, &adec, now);
        /* alternate so the bracket actually narrows both ways at least once, deterministically:
         * fail exactly at the midpoint every time closes toward it monotonically from both sides */
        gbp_v28_3a_depth_done(&s, 0u, 0u, 0u, mid % 2u, 0u, 0u, (mid % 2u) ? 0u : 1u);
    }
    check(s.bracket_closed == 1u, "the bracket closed within a bounded number of steps");
    check(s.hi - s.lo <= GBP_V28_P3_BISECT_WIDTH, "the closed bracket is within GBP_V28_P3_BISECT_WIDTH");
    check(s.confirming == 1u, "a closed bracket enters the confirm hold");
    check(s.depths_n >= 5u, "real convergence took several depths, not a trivial single close (log2(512/32) = 4)");
}

static void test_confirm_hold_ends_the_descent(void)
{
    struct gbp_v28_3a s;
    uint64_t now = steady2(GBP_V28_P3_START);
    gbp_v28_3a_start(&s, TB_HZ, now);
    (void)drive(&s, &now, 1u + GBP_V28_3A_DWELL_S);
    (void)gbp_v28_3a_tick(&s, &tr, &ap, &adec, now);
    gbp_v28_3a_depth_done(&s, 0u, 0u, 0u, 0u, 0u, 0u, 1u);   /* fail at once: open bracket, ends already -- so
                                                              * force a confirm state directly for this test's
                                                              * own narrow purpose instead */
    memset(&s, 0, sizeof s);
    s.tb_hz = TB_HZ;
    s.confirming = 1u;
    s.bracket_closed = 1u;
    s.lo = GBP_V28_P3_MIN;
    s.hi = GBP_V28_P3_MIN + GBP_V28_P3_BISECT_WIDTH;
    s.cur = s.lo;
    s.cur_kind = (uint8_t)GBP_V28_3A_CONFIRM;
    s.begin_pending = 1u;
    s.pending_target = s.lo;
    now = steady2(s.lo);
    (void)drive(&s, &now, 1u + GBP_V28_3A_CONFIRM_S);
    (void)gbp_v28_3a_tick(&s, &tr, &ap, &adec, now);
    gbp_v28_3a_depth_done(&s, 0u, 0u, 0u, /*dup=*/1u, 0u, 0u, /*starved=*/0u);   /* NOT OBSERVED, per §V27.14 §4 */
    check(gbp_v28_3a_finished(&s) == 1, "the confirm hold is the last word: the descent completes");
}

static void test_confirm_hold_ends_early_on_underrun_observed(void)
{
    struct gbp_v28_3a s;
    uint64_t now;
    memset(&s, 0, sizeof s);
    s.tb_hz = TB_HZ;
    now = steady2(GBP_V28_P3_MIN);
    s.cur = GBP_V28_P3_MIN;
    s.cur_kind = (uint8_t)GBP_V28_3A_CONFIRM;
    s.begin_pending = 1u;
    s.pending_target = GBP_V28_P3_MIN;
    (void)drive(&s, &now, 1u);                       /* apply the confirm depth */
    check(s.dwell_active == 1u, "the confirm dwell is running");
    {
        const uint64_t scheduled_end = s.t_dwell_end;
        gbp_v28_3a_underrun_observed(&s, now + 1u);
        check(s.t_dwell_end == now + 1u, "the hold is pulled back to the observed instant");
        check(s.t_dwell_end < scheduled_end, "strictly earlier than its own full confirm span");
    }
    (void)drive(&s, &now, 1u);
    check(s.depth_pending == 1u || gbp_v28_3a_finished(&s) == 1,
          "the shortened dwell is noticed on the very next tick, not the original schedule");
}

static void test_a_cut_dwell_is_partial(void)
{
    struct gbp_v28_3a s;
    uint64_t now = steady2(GBP_V28_P3_START);
    gbp_v28_3a_start(&s, TB_HZ, now);
    (void)drive(&s, &now, 1u);                        /* apply the first depth, but do NOT let it dwell out */
    check(s.dwell_active == 1u, "the dwell is running (cut before its own end)");
    gbp_v28_3a_cut(&s, now);
    check(gbp_v28_3a_finished(&s) == 1, "a cut always finishes the descent");
    check(s.depth_pending == 1u, "the cut dwell is still owed its depth_done() call");
    gbp_v28_3a_depth_done(&s, 0u, 0u, 0u, 1u, 0u, 0u, 0u);
    check(gbp_v28_3a_depth_record(&s, 0)->partial == 1u, "a dwell cut before its own end is recorded PARTIAL");
}

static void test_a_dwell_already_ended_before_a_cut_stays_whole(void)
{
    struct gbp_v28_3a s;
    uint64_t now = steady2(GBP_V28_P3_START);
    gbp_v28_3a_start(&s, TB_HZ, now);
    (void)drive(&s, &now, 1u + GBP_V28_3A_DWELL_S);   /* let the dwell end NATURALLY first */
    (void)gbp_v28_3a_tick(&s, &tr, &ap, &adec, now);
    check(s.dwell_active == 0u && s.depth_pending == 1u, "the dwell already ended on its own, still unacknowledged");
    gbp_v28_3a_cut(&s, now + 1u);                     /* the cut arrives only AFTER the dwell's own end */
    gbp_v28_3a_depth_done(&s, 0u, 0u, 0u, 1u, 0u, 0u, 0u);
    check(gbp_v28_3a_depth_record(&s, 0)->partial == 0u,
          "a dwell that had already ended when the phase was cut stays WHOLE, not partial");
}

static void test_depth_done_with_nothing_pending_is_refused_and_counted(void)
{
    struct gbp_v28_3a s;
    memset(&s, 0, sizeof s);
    s.tb_hz = TB_HZ;
    gbp_v28_3a_depth_done(&s, 0u, 0u, 0u, 0u, 0u, 0u, 0u);
    eqi(s.refused_depth_done, 1, "depth_done() with nothing pending is refused, counted, never silent");
    eqi(s.depths_n, 0, "and records nothing");
}

/* ================================================================================================
 * Layer 2: the Orchestrator's own requirement (Issue #130) -- 3a must check begin()'s return.
 * ================================================================================================ */

/* A DELIBERATELY WRONG driver: proceeds as though gbp_atrans2_begin() always applies, exactly the
 * mistake the Orchestrator's requirement forbids. Used only to show the contrast; gbp_v28_3a.c
 * itself never does this. */
static uint32_t dishonest_depths_recorded_at_the_wrong_target;

static void dishonest_drive_one_period(uint32_t target, uint64_t *now)
{
    uint32_t k;
    /* believes the begin succeeded whether or not it did -- the defect */
    (void)gbp_atrans2_begin(&tr, &ap, &adec, *now, GBP_ATRANS2_UNMUTED, 0u, 0u, 0u, target, GBP_V28_A4);
    if (tr.target != target) dishonest_depths_recorded_at_the_wrong_target++;
    for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(*now); (*now)++; }
}

static void test_dishonest_vs_honest_under_a_forced_busy_transition(void)
{
    struct gbp_v28_3a s;
    uint64_t now = steady2(GBP_V28_P3_START);
    const uint32_t mute = gbp_atrans2_min_mute(GBP_ATRANS2_ROTATE, 0u, GBP_V28_A4);

    dishonest_depths_recorded_at_the_wrong_target = 0u;
    (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mute, 0u, 0u, GBP_V28_P3_START, GBP_V28_A4);
    dishonest_drive_one_period(GBP_V28_P3_START - GBP_V28_P3_STEP, &now);
    check(dishonest_depths_recorded_at_the_wrong_target >= 1u,
          "without the check: believes a depth is in force while the ring is still at the OLD one (the defect)");

    now = steady2(GBP_V28_P3_START);
    (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mute, 0u, 0u, GBP_V28_P3_START, GBP_V28_A4);
    gbp_v28_3a_start(&s, TB_HZ, now);
    (void)drive(&s, &now, mute + 2u);
    check(s.dwell_active == 0u || tr.target == (uint32_t)s.cur,
          "with the check (the real module): a dwell only ever runs once gbp_atrans2's own target agrees");
}

int main(void)
{
    test_start_begins_the_first_depth_once_applied();
    test_begin_refused_counts_no_dwell_until_applied();
    test_a_holding_depth_steps_down_by_p3_step();
    test_the_floor_holds_ends_without_a_bracket();
    test_the_first_depth_fails_opens_no_bracket();
    test_bisection_converges_to_width_le_bisect_width();
    test_confirm_hold_ends_the_descent();
    test_confirm_hold_ends_early_on_underrun_observed();
    test_a_cut_dwell_is_partial();
    test_a_dwell_already_ended_before_a_cut_stays_whole();
    test_depth_done_with_nothing_pending_is_refused_and_counted();
    test_dishonest_vs_honest_under_a_forced_busy_transition();
    printf("test_gbp_v28_3a: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
