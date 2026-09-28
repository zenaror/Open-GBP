/*
 * tests/unit/test_gbp_v28_sweep.c — GitHub Issue #129/#130: gbp_v28_sweep, §V28's step sweep
 * (#128 §3, the sequence frozen on #129), against the REAL gbp_atrans2/gbp_aplay2/gbp_adec2 chain
 * -- same two-layer shape as test_gbp_v28_3a.c/test_gbp_v28_3b.c (the algorithm's own logic, and
 * the Orchestrator's begin-while-active requirement, both provable only against the real chain
 * since the module calls gbp_atrans2_begin() directly). The per-transition landing correctness
 * (residue, TARGET/AHEAD structural bounds, under bursty feed and every phase) is
 * tests/unit/test_v28_sweep_residue.c's own scope -- this file tests the HANDLER: sequencing,
 * classification, recording, verdict computation, and the cut/busy-gate discipline every §V28
 * handler shares.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_v28_sweep.h"
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

#define CALLS_PER_PERIOD 16u
#define TB_HZ CALLS_PER_PERIOD   /* 1 second == 1 period, this harness's own convention */

static int starve = 0;   /* 0: feed normally; 1: give2() a no-op, for the forced-underrun test */

static void give2(struct gbp_adec2 *d, uint32_t n, int16_t v)
{
    uint32_t k;
    if (starve) return;
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

/* the chain steady at (from, ahead) -- the sweep always begins at (T704, A4) */
static uint64_t steady2(uint32_t from, uint32_t ahead)
{
    uint64_t now = 0;
    uint32_t i, k;
    memset(&ap, 0, sizeof ap);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    gbp_atrans2_init(&tr);
    ap.ahead = ahead;
    gbp_aplay2_set_target(&ap, from);
    give2(&adec, from, 100);
    for (i = 0; i < ahead; i++) prime_period2(&now);
    ap.playing = 1u;
    for (i = 0; i < 6u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(now); now++; }
    }
    return now;
}

static int drive(struct gbp_v28_sweep *s, uint64_t *now, uint32_t periods)
{
    uint32_t i, k;
    int flags = 0;
    for (i = 0; i < periods && !(flags & GBP_V28_SWEEP_TICK_PHASE_COMPLETE); i++) {
        (void)gbp_aplay2_irq_handoff(&ap, *now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) {
            give2(&adec, slice2(k), 100);
            pump2(*now);
            flags |= gbp_v28_sweep_tick(s, &tr, &ap, &adec, *now);
            (*now)++;
        }
    }
    return flags;
}

/* ================================================================================================
 * Layer 1: the algorithm, against the real chain.
 * ================================================================================================ */

/* Issue #131 (RUN 48): gbp_v28_sweep_start() was never called anywhere in poc/gbp-audio-v28/
 * source/main.c either -- the same gap as 3a's, but sweep_tick()'s own "not dwelling yet" branch
 * (`if (!s->dwelling) { if (t->active) return 0; ...dwelling=1... }`) does not require
 * begin_pending to have ever been true, so a never-started sweep silently SKIPS move 0's own
 * gbp_atrans2_begin() call and dwells on whatever chain state already existed -- RUN 48's own
 * n=0 record (`outcome=2 fail=1 residue=0`) is that artifact, void as a domain result. Proven
 * directly: move 0 finalizes a record without gbp_atrans2_begin() ever being called
 * (tr.begun stays 0), and move 1 recovers because finalize_record() sets begin_pending=1 at the
 * end of move 0's own processing regardless of how move 0 itself got there. */
static void test_a_never_started_sweep_skips_move_0_s_own_begin_then_recovers(void)
{
    struct gbp_v28_sweep s;
    uint64_t now = steady2(GBP_V28_T704, GBP_V28_A4);
    uint32_t i, k;
    long long begun_at_move_0_finalize = -1;
    memset(&s, 0, sizeof s);   /* the exact bug: gbp_v28_sweep_start() is never called */
    check(tr.active == 0u, "test setup: nothing is transitioning yet");
    /* one tick at a time, so the check lands EXACTLY when records_n first becomes 1 -- before
     * move 1's own begin_pending has had a further tick to act on it. */
    for (i = 0; i < 200u && s.records_n == 0u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD && s.records_n == 0u; k++) {
            give2(&adec, slice2(k), 100);
            pump2(now);
            (void)gbp_v28_sweep_tick(&s, &tr, &ap, &adec, now);
            if (s.records_n == 1u && begun_at_move_0_finalize < 0) begun_at_move_0_finalize = tr.begun;
            now++;
        }
    }
    eqi((long long)s.records_n, 1, "test setup: move 0's own dwell elapsed and finalized a record");
    eqi(begun_at_move_0_finalize, 0,
       "move 0's own gbp_atrans2_begin() was never called -- begin_pending was never 1 for it");
    eqi((long long)s.index, 1, "sweep moved on to move 1");
    eqi((long long)s.begin_pending, 1, "move 1's own begin_pending WAS set correctly, by finalize_record() itself");
    (void)drive(&s, &now, 100u);   /* comfortably above one move's own worst-case mute + dwell */
    check(tr.begun >= 1u, "move 1 recovers: its own gbp_atrans2_begin() DOES get called this time");
    check(s.records_n >= 2u, "and move 1 (and beyond) finalize their own, real records");
}

static void test_a_full_run_completes_all_27_in_order(void)
{
    struct gbp_v28_sweep s;
    uint64_t now = steady2(GBP_V28_T704, GBP_V28_A4);
    int flags;
    uint32_t i;

    gbp_v28_sweep_start(&s, TB_HZ, now);
    check(s.begin_pending == 1u, "start() only decides the first entry -- begin_pending, not yet begun");

    flags = drive(&s, &now, 800u);   /* comfortably above the ~600-period worst case (mutes + 27 dwells) */
    check((flags & GBP_V28_SWEEP_TICK_PHASE_COMPLETE) != 0, "the whole sequence completes within the bound");
    check(gbp_v28_sweep_finished(&s) == 1, "finished once every entry has landed and dwelt");
    eqi(s.records_n, GBP_V28_SWEEP_N, "all 27 entries recorded, none abandoned or skipped");

    /* A REAL FINDING, once fixed at its own source (Issue #129/#130, the Orchestrator's own
     * diagnosis chain): entry 6 (T256A2 -> T256A1, an AHEAD-lowering STEP landing AT AHEAD 1) used
     * to underrun here, one period after landing -- traced, not guessed, to the landing call itself
     * wasting its own pump-call slot (the call that finishes a transition never reaches the
     * caller's own `gbp_aplay2_produce()`, unlike every ordinary steady-state call), so a fresh
     * chunk's own rebuild always starts one call later than steady state's own rhythm. AHEAD >= 2
     * absorbs that one-call delay with its own spare queued chunks; AHEAD 1's own floor is 0, no
     * chunk to spare, so the SAME one-call-late rebuild finishes one call short exactly when the
     * next hand-off needs it. `gbp_atrans2_step()`'s own landing branch now recovers that slot (an
     * ordinary, corrected production attempt, the exact call the caller's own dispatch would have
     * made one tick later) -- proven first against a real 60 s hold (0 underruns), and here again,
     * against the real cascade this test drives: every one of the 27 entries now passes. */
    for (i = 0; i < s.records_n; i++) {
        const struct gbp_v28_sweep_record *r = gbp_v28_sweep_record_at(&s, i);
        check(r != NULL, "every recorded index is readable");
        if (!r) continue;
        check(r->outcome == GBP_V28_SWEEP_PASS, "a clean run under smooth feed passes every entry, entry 6 included");
    }

    /* spot-check the frozen sequence's own shape, not just its count */
    check(gbp_v28_sweep_record_at(&s, 0)->klass == GBP_V28_SWEEP_GATE, "entry 0: GATE");
    check(gbp_v28_sweep_record_at(&s, 0)->mechanism == GBP_V28_SWEEP_STEP, "entry 0: STEP");
    eqi((long long)gbp_v28_sweep_record_at(&s, 0)->from_target, (long long)GBP_V28_T704, "entry 0: from T704");
    eqi((long long)gbp_v28_sweep_record_at(&s, 0)->to_target, (long long)GBP_V28_T576, "entry 0: to T576");

    check(gbp_v28_sweep_record_at(&s, 7)->mechanism == GBP_V28_SWEEP_REFUSED, "entry 7: the refused step at the "
          "bottom");
    eqi((long long)gbp_v28_sweep_record_at(&s, 7)->from_target, (long long)GBP_V28_T256, "entry 7: at T256");
    eqi((long long)gbp_v28_sweep_record_at(&s, 7)->from_ahead, (long long)GBP_V28_A1, "entry 7: at A1");
    eqi((long long)gbp_v28_sweep_record_at(&s, 7)->to_target, (long long)GBP_V28_T256, "entry 7: same-level, T256");
    eqi((long long)gbp_v28_sweep_record_at(&s, 7)->to_ahead, (long long)GBP_V28_A1, "entry 7: same-level, A1");

    check(gbp_v28_sweep_record_at(&s, 15)->mechanism == GBP_V28_SWEEP_REFUSED, "entry 15: the refused step at the "
          "top");

    check(gbp_v28_sweep_record_at(&s, 16)->mechanism == GBP_V28_SWEEP_START, "entry 16: the first largest START");
    check(gbp_v28_sweep_record_at(&s, 16)->klass == GBP_V28_SWEEP_GATE, "entry 16: still GATE");
    check(gbp_v28_sweep_record_at(&s, 17)->mechanism == GBP_V28_SWEEP_START, "entry 17: the second largest START");
    check(gbp_v28_sweep_record_at(&s, 17)->klass == GBP_V28_SWEEP_GATE, "entry 17: still GATE, the last one");

    check(gbp_v28_sweep_record_at(&s, 18)->klass == GBP_V28_SWEEP_INFO, "entry 18: INFO -- the repositioning move");
    check(gbp_v28_sweep_record_at(&s, 18)->mechanism == GBP_V28_SWEEP_START, "entry 18: repositioning is a START");
    eqi((long long)gbp_v28_sweep_record_at(&s, 18)->from_target, (long long)GBP_V28_T704, "entry 18: from T704");
    eqi((long long)gbp_v28_sweep_record_at(&s, 18)->to_target, (long long)GBP_V28_T256, "entry 18: to T256");

    for (i = 19; i < 27u; i++)
        check(gbp_v28_sweep_record_at(&s, i)->klass == GBP_V28_SWEEP_INFO, "entries 19..26: the T192 branch is INFO");
    eqi((long long)gbp_v28_sweep_record_at(&s, 19)->to_target, (long long)GBP_V28_T192, "entry 19: T256 -> T192");
    eqi((long long)gbp_v28_sweep_record_at(&s, 26)->to_target, (long long)GBP_V28_T256, "entry 26: T192 -> T256, "
          "back to the anchor");

    check(gbp_v28_sweep_verdict(&s) == GBP_V28_SWEEP_VERDICT_PASS,
          "18/18 GATE entries pass under this smooth-feed cascade: the verdict is PASS");
}

static void test_verdict_is_pending_until_all_18_gate_entries_are_in(void)
{
    struct gbp_v28_sweep s;
    uint64_t now = steady2(GBP_V28_T704, GBP_V28_A4);
    gbp_v28_sweep_start(&s, TB_HZ, now);
    check(gbp_v28_sweep_verdict(&s) == GBP_V28_SWEEP_VERDICT_PENDING, "nothing recorded yet: PENDING");
    (void)drive(&s, &now, 40u);   /* enough for a handful of GATE entries, not all 18 */
    check(s.records_n > 0u && s.records_n < 18u, "this test's own setup: partway through GATE");
    check(gbp_v28_sweep_verdict(&s) == GBP_V28_SWEEP_VERDICT_PENDING,
          "still PENDING with fewer than 18 GATE entries recorded");
}

static void test_a_gate_underrun_fails_that_entry_and_the_verdict(void)
{
    struct gbp_v28_sweep s;
    uint64_t now = steady2(GBP_V28_T704, GBP_V28_A4);
    uint32_t i;
    int any_underrun = 0;
    gbp_v28_sweep_start(&s, TB_HZ, now);

    /* stall the feed for long enough to outlast the ring's own starting surplus (~5.5 chunks) --
     * a real, driven underrun somewhere in the early GATE entries, not a faked one; which entry it
     * lands on is not fixed (the descending entries can complete on existing surplus alone, exactly
     * as the first-cut version of this test found the hard way), so this checks the OUTCOME the
     * mechanism must produce, not a specific index. */
    starve = 1;
    (void)drive(&s, &now, 300u);
    starve = 0;
    check(ap.underruns > 0u, "this test's own setup: the stall actually underran the chain");

    /* feed normally the rest of the way to completion. */
    (void)drive(&s, &now, 800u);
    check(gbp_v28_sweep_finished(&s) == 1, "the sequence still runs to completion despite the earlier stall");
    eqi(s.records_n, GBP_V28_SWEEP_N, "still all 27 recorded -- a FAIL does not stop the sweep");

    for (i = 0; i < s.records_n; i++) {
        const struct gbp_v28_sweep_record *r = gbp_v28_sweep_record_at(&s, i);
        if (r->outcome == GBP_V28_SWEEP_FAIL && r->fail_reason == GBP_V28_SWEEP_FAIL_UNDERRUN) any_underrun = 1;
    }
    check(any_underrun, "at least one entry is recorded FAIL/UNDERRUN, matching the real underrun the stall caused");
    check(gbp_v28_sweep_verdict(&s) == GBP_V28_SWEEP_VERDICT_FAIL,
          "a GATE FAIL among 18 fails the verdict, even with the rest passing and every INFO entry clean");
}

static void test_begin_refused_counts_nothing_until_applied(void)
{
    struct gbp_v28_sweep s;
    uint64_t now = steady2(GBP_V28_T704, GBP_V28_A4);
    const uint32_t mute = gbp_atrans2_min_mute(GBP_ATRANS2_ROTATE, 0u, GBP_V28_A4);
    int applied;

    applied = gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mute, 0u, 0u, GBP_V28_T704, GBP_V28_A4);
    eqi(applied, 1, "the forcing transition itself must apply, or this test proves nothing");
    check(tr.active != 0u, "gbp_atrans2 is busy for this test's own purpose");

    gbp_v28_sweep_start(&s, TB_HZ, now);
    (void)drive(&s, &now, GBP_V28_STEP_MUTE + 4u);   /* long enough for the forcing ROTATE to land */
    eqi(s.records_n, 0, "no entry is recorded before the sweep's own first begin() actually applies");
}

static void test_a_cut_before_the_first_begin_abandons_nothing_to_report(void)
{
    struct gbp_v28_sweep s;
    uint64_t now = steady2(GBP_V28_T704, GBP_V28_A4);
    gbp_v28_sweep_start(&s, TB_HZ, now);
    check(s.begin_pending == 1u, "decided, not yet begun");
    gbp_v28_sweep_cut(&s, now);
    check(gbp_v28_sweep_finished(&s) == 1, "a cut always finishes the sweep");
    eqi(s.records_n, 0, "a plan decided but never begun is abandoned, nothing to report");
}

static void test_a_cut_while_dwelling_is_partial(void)
{
    struct gbp_v28_sweep s;
    uint64_t now = steady2(GBP_V28_T704, GBP_V28_A4);
    uint32_t i, k;
    gbp_v28_sweep_start(&s, TB_HZ, now);
    /* the dwell is only GBP_V28_SWEEP_DWELL_S * TB_HZ == one period long in THIS harness's own
     * compressed time (TB_HZ periods per abstract second, same convention gbp_v28_3a/3b's own test
     * files use) -- drive() alone would overshoot straight past it into the next entry, so this
     * stops the instant dwelling starts, rather than after a fixed period count. */
    for (i = 0; i < 40u && !s.dwelling; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD && !s.dwelling; k++) {
            give2(&adec, slice2(k), 100);
            pump2(now);
            (void)gbp_v28_sweep_tick(&s, &tr, &ap, &adec, now);
            now++;
        }
    }
    check(s.dwelling == 1u, "entry 0 landed, still inside its own dwell (cut before its own end)");
    gbp_v28_sweep_cut(&s, now);
    check(gbp_v28_sweep_finished(&s) == 1, "a cut always finishes the sweep");
    eqi(s.records_n, 1, "the landed, dwelling entry is still recorded");
    check(gbp_v28_sweep_record_at(&s, 0)->outcome == GBP_V28_SWEEP_PARTIAL,
          "a dwell cut before its own end is recorded PARTIAL, never PASS");
}

/* ================================================================================================
 * Layer 2: the budget (Issue #129's own second comment: "recompute the budget ... check that the
 * total fits in the sweep's 60 s"). The frozen table's own mute counts (24 ordinary/refused STEP
 * entries at GBP_V28_STEP_MUTE, 3 START entries -- the 2 gating STARTs plus the repositioning
 * move -- at GBP_V28_START_MUTE), not re-derived from gbp_v28_sweep.c's own private TABLE.
 * ================================================================================================ */

static void test_the_frozen_sequence_fits_the_sweep_s_60_s_cap(void)
{
    const uint32_t step_entries = 24u;     /* 14 ordinary rungs (7 down + 7 up) + 2 refused + 8 T192 */
    const uint32_t start_entries = 3u;     /* the 2 gating STARTs + the 1 informational repositioning */
    const uint64_t chunk_us = (uint64_t)GBP_APLAY2_PUSHES * 1000000u / GBP_ADEC2_RATE;   /* 31250, exact */
    const uint64_t mute_us = (uint64_t)step_entries * GBP_V28_STEP_MUTE * chunk_us
                           + (uint64_t)start_entries * GBP_V28_START_MUTE * chunk_us;
    const uint64_t dwell_us = (uint64_t)GBP_V28_SWEEP_N * GBP_V28_SWEEP_DWELL_S * 1000000u;
    const uint64_t total_us = mute_us + dwell_us;

    eqi((long long)(step_entries + start_entries), (long long)GBP_V28_SWEEP_N,
        "this test's own entry-class counts still sum to all 27");
    check(chunk_us == 31250u, "one native chunk period is 31.25 ms, exactly -- or the budget below is wrong");
    printf("    mute %llu us + dwell %llu us = %llu us total (cap 60 000 000 us)\n",
           (unsigned long long)mute_us, (unsigned long long)dwell_us, (unsigned long long)total_us);
    check(total_us <= 60000000ull, "the frozen 27-entry sequence fits the sweep phase's own 60 s cap");
}

int main(void)
{
    test_a_never_started_sweep_skips_move_0_s_own_begin_then_recovers();
    test_a_full_run_completes_all_27_in_order();
    test_verdict_is_pending_until_all_18_gate_entries_are_in();
    test_a_gate_underrun_fails_that_entry_and_the_verdict();
    test_begin_refused_counts_nothing_until_applied();
    test_a_cut_before_the_first_begin_abandons_nothing_to_report();
    test_a_cut_while_dwelling_is_partial();
    test_the_frozen_sequence_fits_the_sweep_s_60_s_cap();
    printf("test_gbp_v28_sweep: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
