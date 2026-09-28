/*
 * tests/unit/test_v28_sweep_landing.c — GitHub Issue #136: the step mechanism's landing on a host
 * calibrated to the console, and the property #122 section 1(c) requires of it.
 *
 * CALIBRATION, FROM THE RUN 52 LOG AND NOT ASSUMED:
 *   - the pump runs ~125 times per hand-off period: the 3b hold took 239 630 samples in its 60.0 s,
 *     239 630 / (60.0 s / 31.25 ms) = 124.8. Every earlier host test ran it 16 times;
 *   - the feed is slower than the consumption: V28CORR mean_x100 = 1117 of a cap of 16 corrections per
 *     chunk, dup 99 619 against drop 256; the sweep alone shows 0.47 %, the run 0.545 %. Every earlier
 *     host test fed the ring exactly what the DMA consumes.
 * With those two, the previous mechanism lands the ring 700-940 samples short (RUN 52: 826-875) EVEN WITH
 * EXACT FEED, and its landing trim runs after the first audible hand-off.
 *
 * WHAT IS ASSERTED, per landing, for every move the sweep's GATE walks (and, separately, for every
 * begin phase and the same case list):
 *   the ring lands in [target - GBP_APLAY2_BAND, target] with NO cut after the level was set;
 *   READY is ahead-1 (ordinary) or ahead (a landing mid produce+rotate cycle);
 *   1(c): NOTHING IS CUT AFTER THE FIRST AUDIBLE HAND-OFF, and every chunk handed from then on was built
 *   AFTER the last cut (its production sequence number is not below the number produced when the cut
 *   ran) -- so the moment of any audible splice cannot depend on the AHEAD in force, because there is none.
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
#define STALL_MAX_US    2300.0    /* RUN 52's longest audio delivery gap (SEMGAP max 92 147 ticks at 40.5 MHz) */
#define HW_CALLS        125u      /* pump calls per period on the hardware, see the header */
#define PHASES          25u       /* begin offsets across one period */
#define SETTLE_PERIODS  24u       /* the corrector reaches its equilibrium before a move begins */

/* the time-driven model: a call every PERIOD_US/HW_CALLS on average, scaled by `jitter` (a factor in
 * [1 - spread, 1 + spread], deterministic), the feed a smooth `rate` x the nominal, the hand-off IRQ
 * whenever a period boundary is crossed. */
static double clock_us, next_handoff_us, feed_acc;
static double rate = 1.0, spread = 0.0, stall_p = 0.0, late_first_us = 0.0;
static int late_at;               /* which hand-off's first call is late: -1 the one that opens the period the level is set in,
                                   * +1 the one just past the first audible hand-off (the landing call) */
static uint32_t lcg = 12345u;

/* the property monitor: every cut (gbp_adec2_discard, the ONLY thing that makes a discontinuity in the
 * stream; a corrector DROP takes one extra sample and is not one) and every chunk handed after unmute */
static uint32_t mon_base;         /* p->handed value that makes the NEXT hand-off the first audible one, minus 1 */
static uint32_t mon_disc, mon_prod_at_cut, mon_cut_seen;
static uint32_t mon_cut_after_unmute, mon_stale_heard, mon_heard;

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
    if (stall_p > 0.0 && (double)(rnd() & 0xFFFFu) / 65535.0 < stall_p) dt += STALL_MAX_US * ((double)(rnd() & 0xFFFFu) / 65535.0);
    uint32_t n;
    /* the first pump call after one chosen hand-off runs late_first_us late */
    if (late_first_us > 0.0 && tr.active && clock_us + dt >= next_handoff_us &&
        gbp_atrans2_handoffs(&tr, &ap) + 1u == (uint32_t)((int32_t)tr.mute + late_at))
        dt = next_handoff_us + late_first_us - clock_us;
    clock_us += dt;
    feed_acc += (double)GBP_APLAY2_PUSHES * rate * dt / (double)PERIOD_US;
    n = (uint32_t)feed_acc;
    feed_acc -= (double)n;
    give2(n);
    while (clock_us >= next_handoff_us) {
        const uint8_t *h = gbp_aplay2_irq_handoff(&ap, (uint64_t)next_handoff_us);
        next_handoff_us += (double)PERIOD_US;
        if (h != silence && ap.handed > mon_base) {           /* a chunk that is HEARD */
            const uint32_t idx = (uint32_t)((h - pool) / GBP_APLAY2_CHUNK_BYTES);
            mon_heard++;
            if (mon_cut_seen && ap.seq[idx] < mon_prod_at_cut) mon_stale_heard++;   /* built before the last cut */
        }
    }
    pump2((uint64_t)clock_us);
    if (adec.discarded != mon_disc) {
        if (ap.handed > mon_base) mon_cut_after_unmute++;
        mon_prod_at_cut = ap.produced;
        mon_cut_seen = 1u;
        mon_disc = adec.discarded;
    }
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

/* the other users of the step mechanism: 3b's entry from every 3a floor the bracket can return (T2048 to T4096,
 * AHEAD 4 -> 1 and -> 2), the sweep's T192 INFO rungs, and the perceptual plan's nulling steps (+-2048 at
 * AHEAD 1 and 4, across the whole target range, GBP_V28_STEP_MUTE) */
static struct move OTHER[80];
static uint32_t n_other;
static void add_other(const char *n, uint32_t ft, uint32_t fa, uint32_t tt, uint32_t ta, uint32_t mute)
{
    OTHER[n_other].name = n; OTHER[n_other].from_t = ft; OTHER[n_other].from_a = fa;
    OTHER[n_other].to_t = tt; OTHER[n_other].to_a = ta; OTHER[n_other].mute = mute; n_other++;
}

static void build_other(void)
{
    static const uint32_t FLOORS[6] = { 2048, 2304, 2336, 2432, 3072, 4096 };
    uint32_t i, tg, a;
    n_other = 0;
    for (i = 0; i < 6u; i++) {
        add_other("3b entry ->A1", FLOORS[i], GBP_V28_A4, GBP_V28_T256, GBP_V28_A1, S);
        add_other("3b entry ->A2", FLOORS[i], GBP_V28_A4, GBP_V28_T256, GBP_V28_A2, S);
    }
    add_other("T256A4->T192A4", GBP_V28_T256, GBP_V28_A4, GBP_V28_T192, GBP_V28_A4, S);
    add_other("T192A4->T256A4", GBP_V28_T192, GBP_V28_A4, GBP_V28_T256, GBP_V28_A4, S);
    add_other("T192A1->A2", GBP_V28_T192, GBP_V28_A1, GBP_V28_T192, GBP_V28_A2, S);
    add_other("T192A2->A1", GBP_V28_T192, GBP_V28_A2, GBP_V28_T192, GBP_V28_A1, S);
    add_other("T192A4->A3", GBP_V28_T192, GBP_V28_A4, GBP_V28_T192, GBP_V28_A3, S);
    add_other("T192A3->A4", GBP_V28_T192, GBP_V28_A3, GBP_V28_T192, GBP_V28_A4, S);
    add_other("START T704A4->T256A4", GBP_V28_T704, GBP_V28_A4, GBP_V28_T256, GBP_V28_A4, ST);
    for (tg = 6144u; tg <= 57344u; tg += 2048u * 5u)
        for (a = 1u; a <= 4u; a += 3u) {
            add_other("nulling up", tg, a, tg + 2048u, a, S);
            add_other("nulling down", tg + 2048u, a, tg, a, S);
        }
}

static const struct move *cur_moves = MOVES;
static uint32_t cur_n = 18u;

struct case_result {
    uint32_t runs, short_out, above, ready_bad, late_cut, stale_heard, late_rot, unadj, fill_short, heard;
    uint32_t worst_short, disc_max;
};

/* `mute_add`: periods added to every move's own mute, to find the smallest that works */
static uint32_t mute_add;

static void run_case(double r, double sp, double st, double late, int at, uint32_t seed, struct case_result *out)
{
    uint32_t m, p;
    memset(out, 0, sizeof *out);
    for (m = 0; m < cur_n; m++) {
        for (p = 0; p < PHASES; p++) {
            const struct move *mv = &cur_moves[m];
            uint64_t now;
            uint32_t i, guard = 0;
            rate = r;
            spread = sp;
            stall_p = st;
            late_first_us = late;
            late_at = at;
            lcg = seed + m * 131u + p * 17u;
            now = steady(mv->from_t, mv->from_a);
            for (i = 0; i < p * HW_CALLS / PHASES; i++) one_call(&now);
            if (late > 0.0) {   /* the ring's level when the sequence opens is what its plan reads: sweep it */
                const int32_t off = ((int32_t)(p % 9u) - 4) * 256;
                if (off > 0) give2((uint32_t)off);
                else if (off < 0) (void)gbp_adec2_discard(&adec, (uint32_t)-off);
            }
            mon_disc = adec.discarded;
            mon_cut_seen = mon_cut_after_unmute = mon_stale_heard = mon_heard = 0u;
            (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mv->mute + mute_add, 0u, 0u, mv->to_t,
                                    mv->to_a);
            mon_base = tr.handed_at_start + tr.mute;
            while (tr.active && guard++ < 100000u) one_call(&now);
            out->runs++;
            if (tr.active) { out->short_out++; continue; }
            if (adec.count > mv->to_t) out->above++;
            if (adec.count + GBP_APLAY2_BAND < mv->to_t) {
                out->short_out++;
                if (mv->to_t - adec.count > out->worst_short) out->worst_short = mv->to_t - adec.count;
            }
            if (gbp_aplay2_ready(&ap) != mv->to_a - 1u && gbp_aplay2_ready(&ap) != mv->to_a) out->ready_bad++;
            if (tr.late) out->late_rot++;
            if (tr.unadjusted != 0u) out->unadj++;
            if (tr.fill_short != 0u) out->fill_short++;
            if (tr.disc_n > out->disc_max) out->disc_max = tr.disc_n;
            /* the chunks heard from the first audible hand-off on: observe long enough for `ahead` of them */
            for (i = 0; i < 6u * HW_CALLS; i++) one_call(&now);
            out->late_cut += mon_cut_after_unmute != 0u;
            out->stale_heard += mon_stale_heard != 0u;
            out->heard += mon_heard;
        }
    }
}

static void test_case(const char *name, double r, double sp, double st, double late, int at, uint32_t seed)
{
    struct case_result c;
    char w[200];
    run_case(r, sp, st, late, at, seed, &c);
    printf("    %-38s %u landings: short %u (worst %u), above %u, READY off %u, cut after unmute %u, stale heard %u, "
           "late rot %u, fill short %u, cut max %u\n",
           name, c.runs, c.short_out, c.worst_short, c.above, c.ready_bad, c.late_cut, c.stale_heard, c.late_rot,
           c.fill_short, c.disc_max);
    snprintf(w, sizeof w, "%s: every landing is in [target - BAND, target]", name);
    check(c.short_out == 0u && c.above == 0u, w);
    snprintf(w, sizeof w, "%s: READY is ahead-1 or ahead at every landing", name);
    check(c.ready_bad == 0u, w);
    snprintf(w, sizeof w, "%s: 1(c): nothing is cut after the first audible hand-off", name);
    check(c.late_cut == 0u, w);
    snprintf(w, sizeof w, "%s: 1(c): every chunk heard was built after the last cut", name);
    check(c.stale_heard == 0u && c.heard > 0u, w);
    snprintf(w, sizeof w, "%s: the sequence always finished in silence (no rotation left in flight)", name);
    check(c.late_rot == 0u, w);
    snprintf(w, sizeof w, "%s: the mute always held enough to fill the ring", name);
    check(c.fill_short == 0u, w);
}

int main(int argc, char **argv)
{
    if (argc > 1) mute_add = (uint32_t)atoi(argv[1]);
    build_other();
    test_case("hardware cadence, exact feed", 1.0, 0.0, 0.0, 0.0, 0, 1u);
    test_case("hardware cadence, feed 0.5% slow", 0.995, 0.0, 0.0, 0.0, 0, 2u);
    test_case("hardware cadence, feed 1% slow", 0.99, 0.0, 0.0, 0.0, 0, 3u);
    test_case("hardware cadence, feed 0.5% fast", 1.005, 0.0, 0.0, 0.0, 0, 6u);
    test_case("irregular calls, exact feed", 1.0, 0.7, 0.0, 0.0, 0, 4u);
    test_case("irregular calls, feed 0.5% slow", 0.995, 0.7, 0.0, 0.0, 0, 5u);
    test_case("irregular calls, 1% stalls to 2.3 ms", 0.995, 0.7, 0.01, 0.0, 0, 9u);
    /* the two calls the sequence is exposed at. The call after the hand-off that opens the period the level is
     * set in is MEASURED against the callback's own instant, so any lateness is compensated; the landing call
     * reads the ring after whatever the feed added since the hand-off, 65.5 samples a ms, and the sweep's band
     * tolerates 2.4 ms of it (GBP_ATRANS2_LAND_BIAS) */
    test_case("level-setting call 6 ms late", 1.0, 0.0, 0.0, 6000.0, -1, 10u);
    test_case("landing call 2 ms late", 1.0, 0.0, 0.0, 2000.0, 1, 11u);
    /* the other users, same properties, the two cases that bracket the console */
    cur_moves = OTHER;
    cur_n = n_other;
    test_case("3b/T192/nulling: exact feed", 1.0, 0.0, 0.0, 0.0, 0, 21u);
    test_case("3b/T192/nulling: 0.5% slow, jitter", 0.995, 0.7, 0.0, 0.0, 0, 22u);
    test_case("3b/T192/nulling: 1% slow", 0.99, 0.0, 0.0, 0.0, 0, 23u);
    printf("test_v28_sweep_landing: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
