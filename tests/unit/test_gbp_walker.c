/*
 * tests/unit/test_gbp_walker.c — GitHub Issue #129: gbp_walker, the pure sequencing engine over an
 * ordered list of phase kinds that replaces gbp_async's own single P0..P3 sequence for #128's
 * two-run design.
 *
 * Two layers, deliberately kept apart:
 *
 *   1. THE SKELETON'S OWN LOGIC, against a SYNTHETIC `transition_active` flag: caps (including
 *      navigate/p0, closing §V27.9's O4), cut-vs-complete accounting, session-cap precedence, stop
 *      semantics, the phase_record/current_kind accessors. This proves the module is correct in
 *      isolation, not that anything real is wired to it.
 *
 *   2. THE WIRING, against a REAL gbp_atrans2 transition, driven in actual pump-call order
 *      (give -> produce/step -> queue -> process), exactly Issue #117 entry 21's own test shape
 *      (tests/unit/test_gbp_atrans.c's test_the_module_waits_for_the_executor): a plan applied
 *      over a running one is deterministic in this build too when the busy flag is (deliberately,
 *      here, to reproduce the historical defect) not actually read from tr.active, and does not
 *      happen at all when it is. A synthetic flag alone would only prove layer 1; this is the
 *      layer the Orchestrator asked for after the correction on which Issue owns this defect.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_walker.h"
#include "gbp_atrans2.h"

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

/* ================================================================================================
 * Layer 1: the skeleton's own logic, synthetic busy flag.
 * ================================================================================================ */

static const struct gbp_walker_phase_def FOUR[4] = {
    { GBP_WALKER_NAVIGATE, 10u },
    { GBP_WALKER_DESCENT_3A, 20u },
    { GBP_WALKER_HOLD_3B, 5u },
    { GBP_WALKER_SWEEP, 7u },
};
static const struct gbp_walker_plan PLAN_FOUR = { FOUR, 4u, 100u };

static void test_start_begins_phase_zero(void)
{
    struct gbp_walker w;
    gbp_walker_start(&w, &PLAN_FOUR, 1u, 1000u);
    eqi(w.cfg_faults, 0, "a valid plan raises no cfg_faults");
    eqi(gbp_walker_finished(&w), 0, "not finished at the origin");
    check(gbp_walker_current_kind(&w) == GBP_WALKER_NAVIGATE, "phase 0 is NAVIGATE, same as any other kind");
    check(gbp_walker_phase_record(&w, 0)->started == 1u, "phase 0 started at t_origin");
    eqi((long long)gbp_walker_phase_record(&w, 0)->t_start, 1000, "phase 0's t_start is t_origin");
    check(gbp_walker_phase_record(&w, 1)->started == 0u, "phase 1 has not started yet");
}

static void test_navigate_p0_gets_its_own_cap_like_any_phase(void)
{
    /* §V27.9's O4: the old design's cap_p1_s/cap_p2_s/cap_p3_s/cap_session_s left Phase 0
     * uncapped. Here navigate/p0 is FOUR[0], cap_s = 10, with no special case at all. */
    struct gbp_walker w;
    int flags;
    gbp_walker_start(&w, &PLAN_FOUR, 1u, 0u);
    flags = gbp_walker_tick(&w, 9u, 0);
    eqi(flags, 0, "p0's cap has not elapsed yet at t=9 (< 10)");
    flags = gbp_walker_tick(&w, 10u, 0);
    check((flags & GBP_WALKER_TICK_PHASE_END) != 0, "p0's OWN cap ends it at t=10");
    check((flags & GBP_WALKER_TICK_PHASE_START) != 0, "phase 1 begins the same tick");
    check(gbp_walker_phase_record(&w, 0)->cut == 1u, "a phase cap is a CUT, never COMPLETE");
    check(gbp_walker_phase_record(&w, 0)->reason == GBP_WALKER_END_PHASE_CAP, "the reason is recorded as PHASE_CAP");
    check(gbp_walker_current_kind(&w) == GBP_WALKER_DESCENT_3A, "the walker advanced to phase 1's kind");
}

static void test_the_busy_gate_defers_every_kind_of_advance(void)
{
    /* Layer 1's own version of "never advances while busy": a SYNTHETIC flag held true across the
     * cap's own instant defers the cut; the SAME elapsed time still cuts it the next idle tick. */
    struct gbp_walker w;
    int flags;
    gbp_walker_start(&w, &PLAN_FOUR, 1u, 0u);
    flags = gbp_walker_tick(&w, 50u, 1 /* busy, well past the cap of 10 */);
    eqi(flags, 0, "busy: nothing happens even though the cap elapsed long ago");
    check(gbp_walker_phase_record(&w, 0)->ended == 0u, "phase 0 is still open while busy");
    flags = gbp_walker_tick(&w, 51u, 0 /* idle now */);
    check((flags & GBP_WALKER_TICK_PHASE_END) != 0, "the deferred cap cuts it as soon as it is idle");
    eqi((long long)gbp_walker_phase_record(&w, 0)->t_end, 10, "the cut's own t_end is the cap's instant, not when it was noticed");
}

static void test_phase_complete_is_the_only_path_to_the_complete_reason(void)
{
    struct gbp_walker w;
    int flags;
    gbp_walker_start(&w, &PLAN_FOUR, 1u, 0u);
    flags = gbp_walker_phase_complete(&w, 3u, 0);
    check((flags & GBP_WALKER_TICK_PHASE_END) != 0, "the handler's own completion ends the phase");
    check(gbp_walker_phase_record(&w, 0)->cut == 0u, "a handler-completed phase is NOT a cut");
    check(gbp_walker_phase_record(&w, 0)->reason == GBP_WALKER_END_COMPLETE, "its reason is COMPLETE");
}

static void test_phase_complete_is_busy_gated_too(void)
{
    struct gbp_walker w;
    int flags;
    gbp_walker_start(&w, &PLAN_FOUR, 1u, 0u);
    flags = gbp_walker_phase_complete(&w, 3u, 1 /* busy */);
    eqi(flags, 0, "a handler's own completion is refused while busy");
    check(gbp_walker_phase_record(&w, 0)->ended == 0u, "the phase is still open");
}

static void test_a_cut_phase_is_never_counted_complete_across_every_reason(void)
{
    struct gbp_walker w;
    gbp_walker_start(&w, &PLAN_FOUR, 1u, 0u);
    (void)gbp_walker_tick(&w, 10u, 0);                                     /* phase 0: PHASE_CAP */
    (void)gbp_walker_phase_complete(&w, 11u, 0);                          /* phase 1: COMPLETE */
    (void)gbp_walker_stop(&w, 12u, 0);                                    /* phase 2: STOP */
    check(gbp_walker_phase_record(&w, 0)->cut == 1u, "PHASE_CAP is a cut");
    check(gbp_walker_phase_record(&w, 1)->cut == 0u, "COMPLETE is not a cut");
    check(gbp_walker_phase_record(&w, 2)->cut == 1u, "STOP is a cut");
}

static void test_session_cap_ends_the_whole_walk_not_just_the_phase(void)
{
    /* every phase cap (1000) is far later than the session cap (100), so the ONLY thing that can
     * end phase 0 at t=100 is the session cap -- unlike PLAN_FOUR, where phase 0's own cap (10)
     * would legitimately fire first on a continuously-ticked walker (see the precedence test
     * right below, which exercises exactly that ordering at PLAN_FOUR's own numbers). */
    static const struct gbp_walker_phase_def UNCAPPED[4] = {
        { GBP_WALKER_NAVIGATE, 1000u }, { GBP_WALKER_DESCENT_3A, 1000u },
        { GBP_WALKER_HOLD_3B, 1000u }, { GBP_WALKER_SWEEP, 1000u },
    };
    static const struct gbp_walker_plan PLAN_UNCAPPED = { UNCAPPED, 4u, 100u };
    struct gbp_walker w;
    int flags;
    gbp_walker_start(&w, &PLAN_UNCAPPED, 1u, 0u);
    flags = gbp_walker_tick(&w, 100u, 0);
    check((flags & GBP_WALKER_TICK_FINISHED) != 0, "the session cap finishes the walk");
    check(gbp_walker_finished(&w) == 1, "finished() agrees");
    check(gbp_walker_phase_record(&w, 0)->reason == GBP_WALKER_END_SESSION_CAP, "phase 0's own reason is SESSION_CAP");
    check(gbp_walker_phase_record(&w, 1)->started == 0u, "no later phase was started -- the session cap does not advance");
}

static void test_session_cap_takes_precedence_over_a_phase_cap_at_the_same_instant(void)
{
    /* mirrors gbp_async's own advance(): "whichever instant came first". A plan whose LAST
     * phase's own cap would fire only after the session cap must report SESSION_CAP, not
     * PHASE_CAP, for that last phase. */
    static const struct gbp_walker_phase_def ONE[1] = { { GBP_WALKER_NAVIGATE, 1000u } };
    static const struct gbp_walker_plan PLAN_ONE = { ONE, 1u, 50u };
    struct gbp_walker w;
    int flags;
    gbp_walker_start(&w, &PLAN_ONE, 1u, 0u);
    flags = gbp_walker_tick(&w, 50u, 0);
    check((flags & GBP_WALKER_TICK_FINISHED) != 0, "the session cap (50) fires well before the phase cap (1000)");
    check(gbp_walker_phase_record(&w, 0)->reason == GBP_WALKER_END_SESSION_CAP, "the reason is SESSION_CAP, not PHASE_CAP");
}

static void test_stop_ends_the_whole_walk_even_with_phases_left(void)
{
    struct gbp_walker w;
    int flags;
    gbp_walker_start(&w, &PLAN_FOUR, 1u, 0u);
    flags = gbp_walker_stop(&w, 3u, 0);
    check((flags & GBP_WALKER_TICK_FINISHED) != 0, "a stop finishes the walk");
    check(gbp_walker_phase_record(&w, 1)->started == 0u, "phase 1 never started -- a stop does not begin one more phase");
}

static void test_an_invalid_plan_raises_a_fault_and_never_starts(void)
{
    struct gbp_walker w;
    static const struct gbp_walker_phase_def ZERO_CAP[1] = { { GBP_WALKER_NAVIGATE, 0u } };
    static const struct gbp_walker_plan BAD1 = { ZERO_CAP, 1u, 10u };
    static const struct gbp_walker_plan BAD2 = { FOUR, 0u, 10u };
    gbp_walker_start(&w, &BAD1, 1u, 0u);
    eqi(w.cfg_faults, 1, "a zero cap_s is a fault");
    eqi(gbp_walker_tick(&w, 1000u, 0), 0, "an unstarted walker never ticks");
    gbp_walker_start(&w, &BAD2, 1u, 0u);
    eqi(w.cfg_faults, 1, "a zero-count plan is a fault");
    gbp_walker_start(&w, NULL, 1u, 0u);
    eqi(w.cfg_faults, 1, "a NULL plan is a fault, not a crash");
}

static void test_finished_reports_before_and_after(void)
{
    struct gbp_walker w;
    gbp_walker_start(&w, &PLAN_FOUR, 1u, 0u);
    eqi(gbp_walker_finished(&w), 0, "not finished right after start");
    (void)gbp_walker_stop(&w, 1u, 0);
    eqi(gbp_walker_finished(&w), 1, "finished after a stop");
    eqi(gbp_walker_tick(&w, 999999u, 0), GBP_WALKER_TICK_FINISHED, "a finished walker keeps reporting FINISHED, never crashes");
}

/* ================================================================================================
 * Layer 2: the wiring, against a REAL gbp_atrans2 transition (Issue #117 entry 21's own shape).
 * ================================================================================================ */

static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t ring[GBP_APLAY2_RING];
static int16_t keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events[GBP_APLAY2_EVENTS_CAP];
static struct gbp_aplay2 ap;
static struct gbp_adec2 adec;
static struct gbp_atrans2 tr;

#define CALLS_PER_PERIOD 16u             /* GBP_APLAY2_PUSHES / GBP_APLAY2_STEP_PUSHES: one chunk a period */
#define TRANSITION_MUTE_CHUNKS 5u        /* the transition stays tr.active for about 5 periods */

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

/* the chain playing steadily at `from`: the ring at the level and READY whole (AHEAD chunks) --
 * verbatim from tests/unit/test_gbp_atrans2.c's own steady2(), which this file cannot include
 * (it is `static`), so it is kept byte-identical here rather than half-shared. */
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

/* Drives 4 walker phases (cap_s = 1 second each, tb_hz = CALLS_PER_PERIOD so 1 s = one period =
 * 16 ticks) across a REAL gbp_atrans2 transition sized to stay active for ~5 periods (80 ticks) --
 * longer than the whole 4-phase walk (64 ticks) -- so every phase's own cap is due to fire while
 * the transition is still running, unless the busy gate defers it. `honest` selects what is
 * actually passed as `transition_active`: 1 reads the REAL tr.active (the fix); 0 always claims
 * idle regardless of tr.active (reproducing the historical defect: main.c calling the module's
 * tick unconditionally). Returns how many phase-ends happened while tr.active was actually 1. */
static uint32_t drive_walker_against_a_running_transition(int honest)
{
    static const struct gbp_walker_phase_def P[4] = {
        { GBP_WALKER_NAVIGATE, 1u }, { GBP_WALKER_DESCENT_3A, 1u },
        { GBP_WALKER_HOLD_3B, 1u }, { GBP_WALKER_SWEEP, 1u },
    };
    static const struct gbp_walker_plan PLAN = { P, 4u, 1000u };
    struct gbp_walker w;
    uint64_t now;
    uint32_t preempted = 0u;
    uint32_t i, k;

    now = steady2(512u);
    gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, TRANSITION_MUTE_CHUNKS, 0u, 0u, 512u);
    gbp_walker_start(&w, &PLAN, CALLS_PER_PERIOD, now);

    for (i = 0; i < 6u && !gbp_walker_finished(&w); i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) {
            give2(&adec, slice2(k), 100);
            {
                int busy_real = tr.active;
                int flags = gbp_walker_tick(&w, now, honest ? busy_real : 0);
                if ((flags & GBP_WALKER_TICK_PHASE_END) && busy_real) preempted++;
            }
            pump2(now);
            now++;
        }
    }
    return preempted;
}

static void test_without_the_hold_the_walker_advances_over_the_running_transition(void)
{
    uint32_t preempted = drive_walker_against_a_running_transition(0 /* dishonest: always claims idle */);
    printf("    without the hold: %u of 4 phases preempted the running transition\n", (unsigned)preempted);
    check(preempted >= 3u, "without the hold the walker advances over the running transition (the historical defect, #117 entry 21)");
}

static void test_with_the_hold_the_walker_never_advances_over_the_running_transition(void)
{
    uint32_t preempted = drive_walker_against_a_running_transition(1 /* honest: reads the real tr.active */);
    eqi((long long)preempted, 0, "with the hold, wired to the REAL tr.active, no phase ever ends while the transition is active");
}

int main(void)
{
    test_start_begins_phase_zero();
    test_navigate_p0_gets_its_own_cap_like_any_phase();
    test_the_busy_gate_defers_every_kind_of_advance();
    test_phase_complete_is_the_only_path_to_the_complete_reason();
    test_phase_complete_is_busy_gated_too();
    test_a_cut_phase_is_never_counted_complete_across_every_reason();
    test_session_cap_ends_the_whole_walk_not_just_the_phase();
    test_session_cap_takes_precedence_over_a_phase_cap_at_the_same_instant();
    test_stop_ends_the_whole_walk_even_with_phases_left();
    test_an_invalid_plan_raises_a_fault_and_never_starts();
    test_finished_reports_before_and_after();
    test_without_the_hold_the_walker_advances_over_the_running_transition();
    test_with_the_hold_the_walker_never_advances_over_the_running_transition();
    printf("test_gbp_walker: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
