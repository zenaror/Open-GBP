/*
 * tests/unit/test_v28_3a_dma_stall_integration.c — GitHub Issue #131 (RUN 48): does a DMA hand-off
 * rate throttled to the run's own measured ratio, with the decode FEED running at full speed,
 * reproduce zero V28_3A records over a simulated phase-1 budget? The Orchestrator's own hypothesis
 * on #131, reproduced here call-for-call against the real chain, exactly as
 * tests/unit/test_v28_zero_feed_integration.c already does for 3b's own entry step.
 *
 * THE ARITHMETIC THIS MODELS (Issue #131). RUN 48: handed=188 over 315.8 s (measured), against the
 * path's own expected ~16 Hz -- about one hand-off per 1.7 s instead of one per ~0.0625 s. produced
 * (207) - handed (188) = 19, close to GBP_APLAY2_POOL (16): production stalls once the pool runs
 * out of free buffers, and only a hand-off frees one. Feed itself is not the bottleneck
 * (blocks_in=1291230 against overflow=20214785 -- the decoder ring has plenty to give and nowhere
 * to put it).
 *
 * main.c's own wiring, reproduced verbatim (poc/gbp-audio-v28/source/main.c, the
 * GBP_WALKER_DESCENT_3A case, live_step()/live_dma_cb()):
 *   1. once per hand-off period, unconditionally: gbp_aplay2_irq_handoff() -- live_dma_cb();
 *   2. once per pump call, unconditionally: gbp_v28_3a_tick(); on GBP_V28_3A_TICK_DEPTH_DONE,
 *      gbp_v28_3a_depth_done() fed from ap/adec's own DELTA counters -- underruns, overflow, dup,
 *      drop, and `ring_gated` (not `starved_steps`) for the `starved` parameter, exactly as
 *      main.c:951-952 calls it;
 *   3. produce-or-step, then gbp_aplay2_process() -- the same pump2() every other test_gbp_v28_*.c
 *      file in this suite already uses.
 *
 * The feed (give2()) is called on EVERY tick, at full rate -- never starved from the outside. The
 * only throttled thing is the hand-off's own calling frequency.
 *
 * THE RESULT (run against this file, before this comment was written): REFUTED. With the feed at
 * full rate, the throttled hand-off alone does NOT stall 3a -- it completes 9 depths and finishes
 * entirely within the simulated 138 s budget (a mix of holds and DUP/DROP corrections keeping the
 * ring in check, ending well short of the budget). RUN 48's own correction counts are far smaller
 * (dup=16, drop=29 over the WHOLE 315.8 s run) than this scenario's own (drop climbs into the
 * hundreds by the time 3a finishes here), which is itself a second, independent signal that the
 * throttled-hand-off-alone model is not what RUN 48 actually did. The hand-off rate is still the
 * one unexplained quantity in the run (§ above), but it is not, by itself, why zero depths
 * completed -- something else held the first depth, and this test's own negative result is kept as
 * the record of that, not discarded, per this project's own discipline on negative findings.
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

/* ---- the real chain, the same harness shape every test_gbp_v28_*.c file in this suite uses. ---- */
static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t ring[GBP_APLAY2_RING];
static int16_t keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events[GBP_APLAY2_EVENTS_CAP];
static struct gbp_aplay2 ap;
static struct gbp_adec2 adec;
static struct gbp_atrans2 tr;

#define CALLS_PER_PERIOD 16u
#define TB_HZ CALLS_PER_PERIOD   /* 1 s = one period = 16 ticks, the same convention this suite uses */

/* RUN 48's own measured ratio: one hand-off per ~1.7 real seconds against an expected ~1 per
 * period (1 real second, this suite's own convention) -- HANDOFF_PERIOD_TICKS scales CALLS_PER_PERIOD
 * by that same ratio, 1.7x fewer hand-offs per real second than the steady rate every other test in
 * this suite assumes. */
#define HANDOFF_PERIOD_TICKS  27u   /* ~1.7 * CALLS_PER_PERIOD, RUN 48's own handed/expected ratio */

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

/* main.c's own live_step() shape (its pump-slot block): tr.active ? step() : produce(); process(). */
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

/* Feeds one full period's worth of decoded samples per HANDOFF_PERIOD_TICKS ticks -- full-rate
 * feed, same slice2() cadence every other test in this suite uses, just repeated to keep the ring
 * from ever running dry over the throttled hand-off's own longer period. */
static void give_full_rate(uint32_t tick_in_period)
{
    give2(&adec, slice2(tick_in_period % CALLS_PER_PERIOD), 100);
}

static void test_a_throttled_handoff_rate_with_full_feed(void)
{
    uint64_t now = 0;
    uint32_t i, k;
    /* main.c's own depth_done() call site keeps these as static deltas (main.c:950). */
    uint32_t d0_underruns = 0, d0_overflow = 0, d0_dup = 0, d0_drop = 0, d0_ring_gated = 0;
    struct gbp_v28_3a s;
    /* 138 s, RUN 48's own phase-1 budget, at this suite's 16-ticks-per-second convention. */
    const uint32_t budget_ticks = 138u * TB_HZ;
    uint32_t depth_done_calls = 0u;

    memset(&ap, 0, sizeof ap);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    gbp_atrans2_init(&tr);
    ap.ahead = GBP_V28_A4;
    gbp_aplay2_set_target(&ap, GBP_V28_P3_START);
    /* prime steady state at the descent's own starting depth, full rate, normal hand-off --
     * the run itself DID reach a working steady state before the throttle (handed > 0). */
    give2(&adec, GBP_V28_P3_START * GBP_V28_A4, 100);
    for (i = 0; i < GBP_V28_A4; i++) prime_period2(&now);
    ap.playing = 1u;
    for (i = 0; i < 4u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(now); now++; }
    }

    gbp_v28_3a_start(&s, TB_HZ, now);

    /* THE THROTTLE: hand-off fires once every HANDOFF_PERIOD_TICKS instead of every
     * CALLS_PER_PERIOD -- RUN 48's own measured ratio. Feed is unthrottled: give_full_rate() runs
     * on every tick, exactly as blocks_in's own count says the GBP's capture path did. */
    for (i = 0; i < budget_ticks; i++) {
        if (i % HANDOFF_PERIOD_TICKS == 0u) (void)gbp_aplay2_irq_handoff(&ap, now);
        give_full_rate(i);
        {
            /* main.c:944-954, verbatim. */
            const int f = gbp_v28_3a_tick(&s, &tr, &ap, &adec, now);
            if (f & GBP_V28_3A_TICK_DEPTH_DONE) {
                gbp_v28_3a_depth_done(&s, 0u, ap.underruns - d0_underruns, adec.overflow - d0_overflow,
                                      ap.dup - d0_dup, ap.drop - d0_drop, 0u, ap.ring_gated - d0_ring_gated);
                d0_underruns = ap.underruns; d0_overflow = adec.overflow; d0_dup = ap.dup;
                d0_drop = ap.drop; d0_ring_gated = ap.ring_gated;
                depth_done_calls++;
            }
            if (f & GBP_V28_3A_TICK_PHASE_COMPLETE) break;
        }
        pump2(now);
        now++;
    }

    printf("  [diagnostic] depth_done_calls=%u finished=%d handed=%u produced=%u dup=%u drop=%u "
          "starved_steps=%u ring_gated=%u ready=%u ahead=%u tr.active=%d s.begin_pending=%u "
          "s.dwell_active=%u\n",
          depth_done_calls, gbp_v28_3a_finished(&s), ap.handed, ap.produced, ap.dup, ap.drop,
          ap.starved_steps, ap.ring_gated, gbp_aplay2_ready(&ap), ap.ahead, tr.active,
          s.begin_pending, s.dwell_active);

    /* REFUTED (see this file's own header comment): a throttled hand-off rate, alone, with the
     * feed running at full rate, does NOT reproduce RUN 48's zero V28_3A records -- 3a completes
     * depths and finishes well inside the phase-1 budget. Pinned here so the record survives: if a
     * future edit makes this scenario stall too, that is itself worth knowing, and if it keeps
     * NOT stalling, the negative result stays proven rather than merely remembered. */
    check(depth_done_calls > 0u, "a throttled hand-off rate with a full-rate feed does NOT stall "
                                 "3a -- it still completes depths (REFUTES the hand-off-alone "
                                 "hypothesis; RUN 48's own zero records need a different cause)");
    eqi((long long)gbp_v28_3a_finished(&s), 1, "and 3a finishes well inside the phase-1 budget "
                                              "in this scenario, unlike RUN 48's own zero-record run");
}

int main(void)
{
    test_a_throttled_handoff_rate_with_full_feed();
    printf("test_v28_3a_dma_stall_integration: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
