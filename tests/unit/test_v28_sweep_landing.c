/*
 * tests/unit/test_v28_sweep_landing.c — GitHub Issue #136 (RUN 52): the step mechanism's landing
 * under the two things the hardware has and every earlier host test lacked.
 *
 * WHAT RUN 52 MEASURED. Three GATE moves of the sweep (n=5, 7, 10: 867, 875, 826 short) and four INFO
 * ones (n=0, 21, 26, 27: 393, 829, 792, 324 short) landed with the ring below target by more than
 * GBP_APLAY2_BAND, the sweep's own band.
 * The passing moves landed at exactly target, after the landing trim cut a surplus. Nothing in the
 * landing can add samples, so a ring left short stayed short.
 *
 * WHY THE HOST NEVER SAW IT. test_v28_sweep_residue.c and test_gbp_v28_sweep.c feed the ring EXACTLY
 * the rate the DMA consumes, 16 pump calls per hand-off period. Then the ring's level at the landing
 * call equals its level at the start of the transition (the rotate loop subtracts one chunk per
 * period and the period's inflow refills it), and that level is target. The hardware differs in two
 * measured ways:
 *   - the pump runs ~125 times per period, not 16: RUN 52's 3b hold took 239 630 samples in its 60.0 s,
 *     239 630 / (60.0 s / 31.25 ms) = 124.8;
 *   - the feed is slower than the consumption: V28CORR mean_x100 = 1117 of a cap of 16 corrections per
 *     chunk, and dup 99 619 against drop 256 (RUN 52), the corrector saturated on the DUP side.
 * Either one, alone, lands the ring short on the current source; both are reproduced here.
 *
 * WHAT IS ASSERTED, per landing, for every move the sweep's GATE walks:
 *   the ring never sits above target after the trim, and never more than GBP_APLAY2_BAND below it;
 *   READY is ahead-1 (ordinary) or ahead (a landing mid produce+rotate cycle);
 *   the trim's own cut stays within two chunks (measured here at most about 2400; the bound is 4096).
 *
 * WHAT IT DOES NOT ASSERT: that the trim is inaudible. It is not masked (see gbp_atrans2.h).
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "gbp_atrans2.h"
#include "gbp_v28_ladder.h"

static int checks, failures;

static void check(int cond, const char *what)
{
    checks++;
    if (!cond) {
        failures++;
        printf("  FAIL: %s\n", what);
    }
}

static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t ring[GBP_APLAY2_RING];
static int16_t keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events[GBP_APLAY2_EVENTS_CAP];
static struct gbp_aplay2 ap;
static struct gbp_adec2 adec;
static struct gbp_atrans2 tr;

#define PERIOD_US       31250u    /* one hand-off period */
#define HW_CALLS        125u      /* pump calls per period on the hardware, see the header */
#define PHASES          25u       /* begin offsets across one period */
#define SETTLE_PERIODS  24u       /* the corrector reaches its equilibrium before a move begins */

/* the time-driven model: a call every PERIOD_US/HW_CALLS on average, scaled by `jitter` (a factor in
 * [1 - spread, 1 + spread], deterministic), the feed a smooth `rate` x the nominal, the hand-off IRQ
 * whenever a period boundary is crossed. */
static double clock_us, next_handoff_us, feed_acc;
static double rate = 1.0, spread = 0.0, stall_p = 0.0, late_first_us = 0.0;
static uint32_t lcg = 12345u;

static uint32_t rnd(void)
{
    lcg = lcg * 1664525u + 1013904223u;
    return lcg >> 8;
}

static void give2(uint32_t n)
{
    uint32_t k;
    for (k = 0; k < n && adec.count < adec.cap; k++) {
        adec.ring[(adec.head + adec.count) % adec.cap] = 100;
        adec.count++;
    }
}

static void pump2(uint64_t now)
{
    int b;
    if (tr.active) (void)gbp_atrans2_step(&tr, &ap, &adec, now, &b);
    else b = gbp_aplay2_produce(&ap, &adec);
    if (b >= 0) gbp_aplay2_queue(&ap, b);
    gbp_aplay2_process(&ap);
}

static void one_call(uint64_t *now)
{
    const double base = (double)PERIOD_US / (double)HW_CALLS;
    double dt = spread == 0.0 ? base : base * (1.0 - spread + 2.0 * spread * ((double)(rnd() & 0xFFFFu) / 65535.0));
    if (stall_p > 0.0 && (double)(rnd() & 0xFFFFu) / 65535.0 < stall_p) dt += 8000.0 * ((double)(rnd() & 0xFFFFu) / 65535.0);
    uint32_t n;
    /* the first call after the hand-off that opens the transition's LAST period runs late_first_us late:
     * the decision to rotate is taken there, and every 250 us it slips costs ~16 samples at the landing */
    if (late_first_us > 0.0 && tr.active && clock_us + dt >= next_handoff_us &&
        gbp_atrans2_handoffs(&tr, &ap) + 1u == tr.mute)
        dt = next_handoff_us + late_first_us - clock_us;
    clock_us += dt;
    feed_acc += (double)GBP_APLAY2_PUSHES * rate * dt / (double)PERIOD_US;
    n = (uint32_t)feed_acc;
    feed_acc -= (double)n;
    give2(n);
    while (clock_us >= next_handoff_us) {
        (void)gbp_aplay2_irq_handoff(&ap, *now);
        next_handoff_us += (double)PERIOD_US;
    }
    pump2(*now);
    (*now)++;
}

/* the chain playing at (from, ahead) with the ring at the level, then SETTLE_PERIODS at the case's
 * own rate so the corrector sits where it would sit on the hardware */
static uint64_t steady(uint32_t from, uint32_t ahead)
{
    uint64_t now = 0;
    uint32_t i, k;
    memset(&ap, 0, sizeof ap);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    gbp_atrans2_init(&tr);
    ap.ahead = ahead;
    gbp_aplay2_set_target(&ap, from);
    give2(from);
    for (i = 0; i < ahead; i++)
        for (k = 0; k < HW_CALLS; k++) {
            int b;
            give2(GBP_APLAY2_PUSHES / HW_CALLS);
            b = gbp_aplay2_produce(&ap, &adec);
            if (b >= 0) gbp_aplay2_queue(&ap, b);
            gbp_aplay2_process(&ap);
            now++;
        }
    ap.playing = 1u;
    clock_us = 0.0;
    next_handoff_us = (double)PERIOD_US;
    feed_acc = 0.0;
    for (i = 0; i < SETTLE_PERIODS * HW_CALLS; i++) one_call(&now);
    return now;
}

struct move {
    const char *name;
    uint32_t from_t, from_a, to_t, to_a, mute;
};

/* exactly the sweep's own GATE moves (#129's frozen sequence): the 14 adjacent steps, the 2 refused
 * same-level steps and the 2 largest STARTs */
#define S GBP_V28_STEP_MUTE
#define ST GBP_V28_START_MUTE
static const struct move MOVES[18] = {
    { "T704A4->T576A4", GBP_V28_T704, GBP_V28_A4, GBP_V28_T576, GBP_V28_A4, S },
    { "T576A4->T448A4", GBP_V28_T576, GBP_V28_A4, GBP_V28_T448, GBP_V28_A4, S },
    { "T448A4->T320A4", GBP_V28_T448, GBP_V28_A4, GBP_V28_T320, GBP_V28_A4, S },
    { "T320A4->T256A4", GBP_V28_T320, GBP_V28_A4, GBP_V28_T256, GBP_V28_A4, S },
    { "T256A4->T256A3", GBP_V28_T256, GBP_V28_A4, GBP_V28_T256, GBP_V28_A3, S },
    { "T256A3->T256A2", GBP_V28_T256, GBP_V28_A3, GBP_V28_T256, GBP_V28_A2, S },
    { "T256A2->T256A1", GBP_V28_T256, GBP_V28_A2, GBP_V28_T256, GBP_V28_A1, S },
    { "T256A1->T256A1", GBP_V28_T256, GBP_V28_A1, GBP_V28_T256, GBP_V28_A1, S },
    { "T256A1->T256A2", GBP_V28_T256, GBP_V28_A1, GBP_V28_T256, GBP_V28_A2, S },
    { "T256A2->T256A3", GBP_V28_T256, GBP_V28_A2, GBP_V28_T256, GBP_V28_A3, S },
    { "T256A3->T256A4", GBP_V28_T256, GBP_V28_A3, GBP_V28_T256, GBP_V28_A4, S },
    { "T256A4->T320A4", GBP_V28_T256, GBP_V28_A4, GBP_V28_T320, GBP_V28_A4, S },
    { "T320A4->T448A4", GBP_V28_T320, GBP_V28_A4, GBP_V28_T448, GBP_V28_A4, S },
    { "T448A4->T576A4", GBP_V28_T448, GBP_V28_A4, GBP_V28_T576, GBP_V28_A4, S },
    { "T576A4->T704A4", GBP_V28_T576, GBP_V28_A4, GBP_V28_T704, GBP_V28_A4, S },
    { "T704A4->T704A4", GBP_V28_T704, GBP_V28_A4, GBP_V28_T704, GBP_V28_A4, S },
    { "START T704A4->T256A1", GBP_V28_T704, GBP_V28_A4, GBP_V28_T256, GBP_V28_A1, ST },
    { "START T256A1->T704A4", GBP_V28_T256, GBP_V28_A1, GBP_V28_T704, GBP_V28_A4, ST },
};

struct case_result {
    uint32_t runs, short_out, above, ready_bad, trim_over;
    uint32_t worst_short, trim_max;
};

static void run_case(double r, double sp, double st, double late, uint32_t seed, struct case_result *out)
{
    uint32_t m, p;
    memset(out, 0, sizeof *out);
    for (m = 0; m < 18u; m++) {
        for (p = 0; p < PHASES; p++) {
            const struct move *mv = &MOVES[m];
            uint64_t now;
            uint32_t i, guard = 0;
            rate = r;
            spread = sp;
            stall_p = st;
            late_first_us = late;
            lcg = seed + m * 131u + p * 17u;
            now = steady(mv->from_t, mv->from_a);
            for (i = 0; i < p * HW_CALLS / PHASES; i++) one_call(&now);
            if (late > 0.0) {   /* the ring's level at the last period's start is what the decision reads: sweep it */
                const int32_t off = ((int32_t)(p % 9u) - 4) * 256;
                if (off > 0) give2((uint32_t)off);
                else if (off < 0) (void)gbp_adec2_discard(&adec, (uint32_t)-off);
            }
            (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mv->mute, 0u, 0u, mv->to_t, mv->to_a);
            while (tr.active && guard++ < 100000u) one_call(&now);
            out->runs++;
            if (tr.active) { out->short_out++; continue; }
            if (adec.count > mv->to_t) out->above++;
            if (adec.count + GBP_APLAY2_BAND < mv->to_t) {
                out->short_out++;
                if (mv->to_t - adec.count > out->worst_short) out->worst_short = mv->to_t - adec.count;
            }
            if (gbp_aplay2_ready(&ap) != mv->to_a - 1u && gbp_aplay2_ready(&ap) != mv->to_a) out->ready_bad++;
            if (tr.trimmed > out->trim_max) out->trim_max = tr.trimmed;
            if (tr.trimmed > 2u * GBP_APLAY2_PUSHES) out->trim_over++;
        }
    }
}

static void test_case(const char *name, double r, double sp, double st, double late, uint32_t seed)
{
    struct case_result c;
    char w[200];
    run_case(r, sp, st, late, seed, &c);
    printf("    %-34s %u landings: %u out of band (worst short %u), %u above target, %u READY off, trim max %u\n",
           name, c.runs, c.short_out, c.worst_short, c.above, c.ready_bad, c.trim_max);
    snprintf(w, sizeof w, "%s: no landing is more than BAND below target", name);
    check(c.short_out == 0u, w);
    snprintf(w, sizeof w, "%s: no landing is above target after the trim", name);
    check(c.above == 0u, w);
    snprintf(w, sizeof w, "%s: READY is ahead-1 or ahead at every landing", name);
    check(c.ready_bad == 0u, w);
    snprintf(w, sizeof w, "%s: the trim never cuts more than two chunks", name);
    check(c.trim_over == 0u, w);
}

int main(void)
{
    test_case("hardware cadence, exact feed", 1.0, 0.0, 0.0, 0.0, 1u);
    test_case("hardware cadence, feed 0.5% slow", 0.995, 0.0, 0.0, 0.0, 2u);
    test_case("hardware cadence, feed 1% slow", 0.99, 0.0, 0.0, 0.0, 3u);
    test_case("hardware cadence, feed 0.5% fast", 1.005, 0.0, 0.0, 0.0, 6u);
    test_case("irregular calls, exact feed", 1.0, 0.7, 0.0, 0.0, 4u);
    test_case("irregular calls, feed 0.5% slow", 0.995, 0.7, 0.0, 0.0, 5u);
    /* a late first call of the last period, the one place the fix is exposed: a stall of up to 8 ms on 2 % of
     * the calls (RUN 52's own audio delivery gaps reach 2.3 ms and its video ones 5.5 ms) */
    test_case("irregular calls, 2% stalls to 8 ms", 0.995, 0.7, 0.02, 0.0, 9u);
    test_case("first call of the last period 3.5 ms late", 1.0, 0.0, 0.0, 3500.0, 10u);
    printf("test_v28_sweep_landing: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
