/*
 * tests/unit/test_gbp_v28_3b.c — GitHub Issue #129/#130: gbp_v28_3b, §V28's AHEAD hold (#128 §2),
 * against the REAL gbp_atrans2/gbp_aplay2/gbp_adec2 chain -- same two-layer shape as
 * test_gbp_v28_3a.c (the algorithm's own logic, and the Orchestrator's begin-while-active
 * requirement, both provable only against the real chain since the module calls
 * gbp_atrans2_begin() directly).
 */
#include <stdio.h>
#include <string.h>
#include "gbp_v28_3b.h"
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

/* ---- the real chain, verbatim from test_gbp_v28_3a.c's own harness. ---- */
static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t ring[GBP_APLAY2_RING];
static int16_t keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events[GBP_APLAY2_EVENTS_CAP];
static struct gbp_aplay2 ap;
static struct gbp_adec2 adec;
static struct gbp_atrans2 tr;

#define CALLS_PER_PERIOD 16u
#define TB_HZ CALLS_PER_PERIOD

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

/* the chain steady at AHEAD 4 (3a's own fixed value throughout, so 3b always starts from there) */
static uint64_t steady_at_ahead4(uint32_t from)
{
    uint64_t now = 0;
    uint32_t i, k;
    memset(&ap, 0, sizeof ap);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    gbp_atrans2_init(&tr);
    ap.ahead = GBP_V28_A4;
    gbp_aplay2_set_target(&ap, from);
    give2(&adec, from * GBP_V28_A4, 100);
    for (i = 0; i < GBP_V28_A4; i++) prime_period2(&now);
    ap.playing = 1u;
    for (i = 0; i < 6u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(now); now++; }
    }
    return now;
}

static int drive(struct gbp_v28_3b *s, uint64_t *now, uint32_t periods)
{
    uint32_t i, k;
    int flags = 0;
    for (i = 0; i < periods; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, *now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) {
            give2(&adec, slice2(k), 100);
            flags = gbp_v28_3b_tick(s, &tr, &ap, &adec, *now);
            pump2(*now);
            (*now)++;
        }
    }
    return flags;
}

/* ================================================================================================
 * Layer 1: the algorithm, against the real chain.
 * ================================================================================================ */

static void test_start_begins_the_entry_step_once_applied(void)
{
    struct gbp_v28_3b s;
    uint64_t now = steady_at_ahead4(GBP_V28_P3_MIN);
    gbp_v28_3b_start(&s, GBP_V28_P3_MIN, TB_HZ, now);
    check(s.begin_pending == 1u, "start() only decides the entry step -- begin_pending, not yet holding");
    eqi(ap.ahead, GBP_V28_A4, "ahead is still 4 until the entry step actually applies");
    (void)drive(&s, &now, 10u);
    check(s.begin_pending == 0u, "ten periods is enough for a same-level ROTATE step to apply");
    check(s.hold_active == 1u, "holding once the entry step actually began");
    eqi(ap.ahead, GBP_V28_A1, "ahead is 1 once the entry step has applied");
    eqi(tr.target, (long long)GBP_V28_P3_MIN, "the anchor target is unchanged");
}

static void test_the_entry_step_lands_without_a_real_underrun(void)
{
    /* the REAL landing, not s.hold_active (which gbp_v28_3b sets the instant begin() applies, well
     * before the underlying ROTATE transition's own mute elapses -- found the hard way building
     * this exact test, Issue #129/#130): drive until tr.active itself returns to 0, a clean period
     * boundary, then settle a few periods under ordinary smooth feed and check the real chain's
     * own ap.underruns never moves. This is what a fitted READY-only check at the landing instant
     * would miss: 3b's own entry step used to land with `ready`/`cur` matching steady state's own
     * tuple exactly, and still underran one hand-off later, because gbp_v28_3b's own anchor
     * (GBP_V28_P3_MIN) sits at GBP_APLAY2_PUSHES exactly, where the ROTATE landing's own ring trim
     * left nothing for the landing call's own production recovery to work with. */
    struct gbp_v28_3b s;
    uint64_t now = steady_at_ahead4(GBP_V28_P3_MIN);
    uint32_t i, k, u0;
    gbp_v28_3b_start(&s, GBP_V28_P3_MIN, TB_HZ, now);
    /* wait for the REAL landing (tr.active back to 0), not just s.begin_pending clearing -- begin()
     * applying and the underlying ROTATE transition actually finishing are different instants (the
     * cause this test exists to catch). */
    for (i = 0; i < 40u && (s.begin_pending || tr.active); i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) {
            give2(&adec, slice2(k), 100);
            (void)gbp_v28_3b_tick(&s, &tr, &ap, &adec, now);
            pump2(now);
            now++;
        }
    }
    check(tr.active == 0u, "this test's own setup: the entry step's own transition actually landed");
    u0 = ap.underruns;
    for (i = 0; i < 8u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) {
            give2(&adec, slice2(k), 100);
            (void)gbp_v28_3b_tick(&s, &tr, &ap, &adec, now);
            pump2(now);
            now++;
        }
    }
    eqi((long long)ap.underruns, (long long)u0,
        "no real underrun in the periods right after the entry step's own landing");
}

static void test_begin_refused_counts_no_hold_until_applied(void)
{
    struct gbp_v28_3b s;
    uint64_t now = steady_at_ahead4(GBP_V28_P3_MIN);
    const uint32_t mute = gbp_atrans2_min_mute(GBP_ATRANS2_ROTATE, 0u, GBP_V28_A4);
    int applied;

    applied = gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mute, 0u, 0u, GBP_V28_P3_MIN, GBP_V28_A4);
    eqi(applied, 1, "the forcing transition itself must apply, or this test proves nothing");
    check(tr.active != 0u, "gbp_atrans2 is busy for this test's own purpose");

    gbp_v28_3b_start(&s, GBP_V28_P3_MIN, TB_HZ, now);
    (void)drive(&s, &now, GBP_V28_STEP_MUTE + 4u);   /* long enough for the forcing ROTATE to land */
    check(s.holds_n == 0u, "no hold is recorded before the entry step's own begin actually applies");
}

static void test_clean_hold_at_ahead_1_finishes_3b(void)
{
    struct gbp_v28_3b s;
    uint64_t now = steady_at_ahead4(GBP_V28_P3_MIN);
    gbp_v28_3b_start(&s, GBP_V28_P3_MIN, TB_HZ, now);
    (void)drive(&s, &now, 10u);
    check(s.hold_active == 1u, "the entry step applied; the AHEAD-1 hold is running");
    (void)drive(&s, &now, GBP_V28_3B_HOLD_S);        /* no underrun_observed() call: a clean hold */
    check((gbp_v28_3b_tick(&s, &tr, &ap, &adec, now) & GBP_V28_3B_TICK_HOLD_DONE) != 0,
          "the hold's own 60 s have elapsed");
    gbp_v28_3b_hold_done(&s);
    check(gbp_v28_3b_finished(&s) == 1, "a clean AHEAD-1 hold finishes 3b -- no escalation");
    eqi(s.holds_n, 1, "only one hold recorded");
    check(gbp_v28_3b_hold_record(&s, 0)->underrun_seen == 0u, "recorded clean");
    check(gbp_v28_3b_hold_record(&s, 0)->ahead == GBP_V28_A1, "at AHEAD 1");
}

static void test_underrun_during_ahead_1_escalates_to_ahead_2(void)
{
    struct gbp_v28_3b s;
    uint64_t now = steady_at_ahead4(GBP_V28_P3_MIN);
    uint64_t underrun_at;
    gbp_v28_3b_start(&s, GBP_V28_P3_MIN, TB_HZ, now);
    (void)drive(&s, &now, 10u);
    check(s.hold_active == 1u, "the AHEAD-1 hold is running");
    (void)drive(&s, &now, 5u);
    underrun_at = now;
    gbp_v28_3b_underrun_observed(&s, now);
    check(s.hold_active == 1u, "still active -- the tick that notices the shortened end has not run yet");
    check((gbp_v28_3b_tick(&s, &tr, &ap, &adec, now) & GBP_V28_3B_TICK_HOLD_DONE) != 0,
          "the hold ends immediately at the observed underrun, long before its own 60 s");
    gbp_v28_3b_hold_done(&s);
    check(gbp_v28_3b_finished(&s) == 0, "not finished yet -- AHEAD 1 saw an underrun, so AHEAD 2 follows");
    eqi(s.holds_n, 1, "one hold recorded so far");
    check(gbp_v28_3b_hold_record(&s, 0)->underrun_seen == 1u, "recorded WITH the underrun");
    eqi((long long)gbp_v28_3b_hold_record(&s, 0)->t_done, (long long)underrun_at,
        "the recorded end is the underrun's own instant, not the full 60 s");
    check(s.begin_pending == 1u, "the AHEAD-2 escalation is decided");
    eqi(s.pending_ahead, GBP_V28_A2, "escalating to AHEAD 2");

    (void)drive(&s, &now, 10u);
    check(s.hold_active == 1u, "the AHEAD-2 hold is now running");
    eqi(ap.ahead, GBP_V28_A2, "ahead is 2");
    (void)drive(&s, &now, GBP_V28_3B_HOLD_S);        /* AHEAD 2's own FULL 60 s, not "the remaining time" */
    check((gbp_v28_3b_tick(&s, &tr, &ap, &adec, now) & GBP_V28_3B_TICK_HOLD_DONE) != 0, "AHEAD 2's hold ends too");
    gbp_v28_3b_hold_done(&s);
    check(gbp_v28_3b_finished(&s) == 1, "3b finishes after AHEAD 2 -- never a third level");
    eqi(s.holds_n, 2, "both holds recorded");
    check(gbp_v28_3b_hold_record(&s, 1)->ahead == GBP_V28_A2, "the second hold is at AHEAD 2");
}

static void test_ahead_2_hold_finishes_regardless_of_its_own_underrun(void)
{
    struct gbp_v28_3b s;
    uint64_t now = steady_at_ahead4(GBP_V28_P3_MIN);
    gbp_v28_3b_start(&s, GBP_V28_P3_MIN, TB_HZ, now);
    (void)drive(&s, &now, 10u);
    gbp_v28_3b_underrun_observed(&s, now);
    (void)gbp_v28_3b_tick(&s, &tr, &ap, &adec, now);
    gbp_v28_3b_hold_done(&s);                        /* escalate to AHEAD 2 */
    (void)drive(&s, &now, 10u);
    check(s.hold_active == 1u, "AHEAD 2's own hold is running");
    gbp_v28_3b_underrun_observed(&s, now);            /* AHEAD 2 ALSO sees an underrun */
    (void)gbp_v28_3b_tick(&s, &tr, &ap, &adec, now);
    gbp_v28_3b_hold_done(&s);
    check(gbp_v28_3b_finished(&s) == 1, "3b still finishes -- AHEAD 2's own underrun does not escalate further");
    eqi(s.holds_n, 2, "still exactly two holds, never three");
    check(gbp_v28_3b_hold_record(&s, 1)->underrun_seen == 1u, "the second hold's own underrun is recorded too");
}

static void test_a_cut_hold_is_partial(void)
{
    struct gbp_v28_3b s;
    uint64_t now = steady_at_ahead4(GBP_V28_P3_MIN);
    gbp_v28_3b_start(&s, GBP_V28_P3_MIN, TB_HZ, now);
    (void)drive(&s, &now, 10u);
    check(s.hold_active == 1u, "the hold is running (cut before its own end)");
    gbp_v28_3b_cut(&s, now);
    check(gbp_v28_3b_finished(&s) == 1, "a cut always finishes 3b");
    check(s.hold_pending == 1u, "the cut hold is still owed its hold_done() call");
    gbp_v28_3b_hold_done(&s);
    check(gbp_v28_3b_hold_record(&s, 0)->partial == 1u, "a hold cut before its own end is recorded PARTIAL");
}

static void test_a_hold_already_ended_before_a_cut_stays_whole(void)
{
    struct gbp_v28_3b s;
    uint64_t now = steady_at_ahead4(GBP_V28_P3_MIN);
    gbp_v28_3b_start(&s, GBP_V28_P3_MIN, TB_HZ, now);
    (void)drive(&s, &now, 10u + GBP_V28_3B_HOLD_S);
    (void)gbp_v28_3b_tick(&s, &tr, &ap, &adec, now);
    check(s.hold_active == 0u && s.hold_pending == 1u, "the hold already ended on its own, still unacknowledged");
    gbp_v28_3b_cut(&s, now + 1u);
    gbp_v28_3b_hold_done(&s);
    check(gbp_v28_3b_hold_record(&s, 0)->partial == 0u,
          "a hold that had already ended when the phase was cut stays WHOLE, not partial");
}

static void test_hold_done_with_nothing_pending_is_refused_and_counted(void)
{
    struct gbp_v28_3b s;
    memset(&s, 0, sizeof s);
    s.tb_hz = TB_HZ;
    gbp_v28_3b_hold_done(&s);
    eqi(s.refused_hold_done, 1, "hold_done() with nothing pending is refused, counted, never silent");
    eqi(s.holds_n, 0, "and records nothing");
}

/* ================================================================================================
 * Layer 2: the Orchestrator's own requirement -- 3b must check begin()'s return, exactly as 3a
 * does. Same dishonest-vs-honest contrast as test_gbp_v28_3a.c's own Layer 2.
 * ================================================================================================ */

static uint32_t dishonest_ahead_recorded_at_the_wrong_value;

static void dishonest_drive_one_period(uint32_t ahead, uint32_t anchor, uint64_t *now)
{
    uint32_t k;
    (void)gbp_atrans2_begin(&tr, &ap, &adec, *now, GBP_ATRANS2_ROTATE, GBP_V28_STEP_MUTE, 0u, 0u, anchor, ahead);
    if (ap.ahead != ahead) dishonest_ahead_recorded_at_the_wrong_value++;
    for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(*now); (*now)++; }
}

static void test_dishonest_vs_honest_under_a_forced_busy_transition(void)
{
    struct gbp_v28_3b s;
    uint64_t now = steady_at_ahead4(GBP_V28_P3_MIN);
    const uint32_t mute = gbp_atrans2_min_mute(GBP_ATRANS2_ROTATE, 0u, GBP_V28_A4);

    dishonest_ahead_recorded_at_the_wrong_value = 0u;
    (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mute, 0u, 0u, GBP_V28_P3_MIN, GBP_V28_A4);
    dishonest_drive_one_period(GBP_V28_A1, GBP_V28_P3_MIN, &now);
    check(dishonest_ahead_recorded_at_the_wrong_value >= 1u,
          "without the check: gbp_atrans2_begin() is called again while busy and its ahead is silently ignored "
          "(begin() itself refuses and leaves ap.ahead at the OLD value -- exactly the defect)");

    now = steady_at_ahead4(GBP_V28_P3_MIN);
    (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mute, 0u, 0u, GBP_V28_P3_MIN, GBP_V28_A4);
    gbp_v28_3b_start(&s, GBP_V28_P3_MIN, TB_HZ, now);
    (void)drive(&s, &now, mute + 4u);
    check(s.hold_active == 0u || ap.ahead == (uint32_t)s.cur_ahead,
          "with the check (the real module): a hold only ever runs once gbp_atrans2's own ahead agrees");
}

int main(void)
{
    test_start_begins_the_entry_step_once_applied();
    test_the_entry_step_lands_without_a_real_underrun();
    test_begin_refused_counts_no_hold_until_applied();
    test_clean_hold_at_ahead_1_finishes_3b();
    test_underrun_during_ahead_1_escalates_to_ahead_2();
    test_ahead_2_hold_finishes_regardless_of_its_own_underrun();
    test_a_cut_hold_is_partial();
    test_a_hold_already_ended_before_a_cut_stays_whole();
    test_hold_done_with_nothing_pending_is_refused_and_counted();
    test_dishonest_vs_honest_under_a_forced_busy_transition();
    printf("test_gbp_v28_3b: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
