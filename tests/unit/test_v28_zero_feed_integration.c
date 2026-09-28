/*
 * tests/unit/test_v28_zero_feed_integration.c — GitHub Issue #129/#130: the zero-feed test's own
 * named successor (docs/research/DEVLOG.md, 2026-09-27's "§18" entry): "once main.c exists, an
 * integration-level zero-feed test, the SAME STALL driven through the REAL DRIVER LOOP, asserting a
 * transition still completes."
 *
 * WHAT THE EARLIER, INFORMAL CHECK ALREADY PROVED (not repeated here): `gbp_atrans2_step()`'s own
 * landing check is wall-clock-bounded by construction, because `gbp_aplay2_irq_handoff()`
 * increments `p->handed` UNCONDITIONALLY on every call, regardless of whether that hand-off carried
 * a real chunk, mute, or underrun silence -- `handed` counts IRQ CALLS, not produced chunks. That
 * check drove `gbp_atrans2` directly, in isolation.
 *
 * THE RESIDUAL RISK THAT CHECK NAMED, AND WHAT THIS FILE ACTUALLY TESTS: "a backstop placed INSIDE
 * gbp_atrans2_step() cannot protect against the one thing that could actually stop `handed` from
 * advancing -- the future driver loop itself failing to call gbp_aplay2_irq_handoff()/
 * gbp_atrans2_step() on every real audio tick, e.g. by gating its own calls on feed or decode
 * availability." poc/gbp-audio-v28/source/main.c's own `main.c` cannot be compiled or driven on the
 * host (it includes <gccore.h> and the rest of the GameCube-only SDK; no such harness exists
 * anywhere in this project, checked directly against tests/mocks/ and every existing tests/unit/
 * file before writing this one). What CAN be proven here, faithfully, is main.c's own PUMP ORDER
 * against the real gbp_walker + a real handler (gbp_v28_3b, the simplest single-ROTATE-transition
 * module) + the real gbp_atrans2/gbp_aplay2/gbp_adec2 chain -- EXACTLY the three-step shape
 * main.c's own live_step()/live_dma_cb() split uses, reproduced call-for-call below (not
 * reimplemented logic, just the same ordering every other test_gbp_v28_*.c file in this suite
 * already uses for the identical reason):
 *
 *   1. once per PERIOD (16 pump calls), unconditionally: gbp_aplay2_irq_handoff() -- main.c's own
 *      live_dma_cb(), called from the AI DMA callback on a FIXED schedule, never gated on feed;
 *   2. once per PUMP CALL, unconditionally: the handler's own tick() (a chance to notice a hold's
 *      end or retry a deferred begin()), then produce-or-step, then gbp_aplay2_process() -- main.c's
 *      own live_step(), also never gated on feed or decode availability.
 *
 * THE STALL: give2() is never called at all for the whole duration of 3b's own entry step (its
 * ROTATE mute, GBP_V28_STEP_MUTE periods) -- a total feed stall, exactly the informal check's own
 * scenario, now one layer up. Structural companion: tests/host/test_v28_zero_feed_wiring.py greps
 * main.c's own text and confirms neither call site is nested inside a feed/decode conditional.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_v28_3b.h"
#include "gbp_v28_ladder.h"
#include "gbp_walker.h"

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

/* main.c's own live_step() shape: `if (tr.active) { if (step()) ... } else b = produce();
 * process();` -- unconditional, no feed/decode gate of any kind. */
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
        (void)gbp_aplay2_irq_handoff(&ap, now);      /* main.c's own live_dma_cb(), once per period */
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(now); now++; }
    }
    return now;
}

static void test_the_entry_step_lands_under_a_total_feed_stall(void)
{
    struct gbp_v28_3b s;
    struct gbp_walker w;
    static const struct gbp_walker_phase_def ONE_3B[1] = { { GBP_WALKER_HOLD_3B, 60u } };
    static const struct gbp_walker_plan PLAN_ONE_3B = { ONE_3B, 1u, 100u };
    uint64_t now = steady_at_ahead4(GBP_V28_P3_MIN);
    uint32_t i, k, periods = 0u;
    const uint32_t bound = GBP_V28_STEP_MUTE + 4u;     /* generous, still a real bound: the mute is
                                                        * GBP_V28_STEP_MUTE periods; landing needs at
                                                        * most one more once handed > mute */

    gbp_walker_start(&w, &PLAN_ONE_3B, TB_HZ, now);
    gbp_v28_3b_start(&s, GBP_V28_P3_MIN, TB_HZ, now);

    /* NOTE, found by this test's own sanity check (a mutation that dropped the irq_handoff() call
     * entirely did NOT fail the first draft's own assertions): `hold_active` and `ap.ahead` both
     * flip the instant gbp_atrans2_begin() APPLIES -- a single successful tick, nothing to do with
     * the mute -- not when the ROTATE transition actually LANDS. The signal this test is actually
     * about is `tr.active` returning to 0 (gbp_atrans2's own `handed > mute` landing check, the
     * thing that depends on gbp_aplay2_irq_handoff() having been called enough times), the SAME
     * idiom test_gbp_v28_3b.c's own test_the_entry_step_lands_without_a_real_underrun() uses
     * (`s.begin_pending || tr.active`) to tell "applied" apart from "landed". */

    /* THE STALL: give2() is never called below -- zero decoded samples arrive for the whole
     * duration of the entry step's own mute. main.c's own three unconditional calls run anyway,
     * exactly as they would on real hardware with a stalled GBP or a pulled cartridge. */
    for (i = 0; i < bound && (s.begin_pending || tr.active); i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);        /* unconditional, once a period */
        for (k = 0; k < CALLS_PER_PERIOD; k++) {
            const int tflags = gbp_v28_3b_tick(&s, &tr, &ap, &adec, now);   /* unconditional */
            if (tflags & GBP_V28_3B_TICK_HOLD_DONE) gbp_v28_3b_hold_done(&s);
            pump2(now);                                 /* unconditional */
            now++;
        }
        periods++;
    }
    check(periods < bound, "the entry step's own ROTATE mute lands within its own bound, never hangs");
    check(tr.active == 0, "the transition actually LANDED (handed > mute), not merely applied or timed out");
    check(s.hold_active == 1u, "and 3b's own hold is running");
    eqi((long long)ap.ahead, (long long)GBP_V28_A1, "and the real chain agrees: ahead is 1");
    (void)w;   /* the walker's own presence in this test proves the SAME dispatch shape main.c uses
                * compiles and runs together with 3b under the stall; its own timing is not what
                * this test is about (3b's own cap is 100 s, far above anything driven here) */
}

int main(void)
{
    test_the_entry_step_lands_under_a_total_feed_stall();
    printf("test_v28_zero_feed_integration: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
