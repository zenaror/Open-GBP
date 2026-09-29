/*
 * tests/unit/test_v28_stock.c -- GitHub Issue #139 (U-GBP-049): the latency of the native chain is a STOCK, and the stock is conserved.
 *
 * THE DEFINITION (written once; tools/v28latency.py and HARDWARE_TESTS.md section V28.22 quote it): the latency of a sample is the time from its
 * entering the decoder's ring to its being PLAYED at the AI. The AI plays continuously, one chunk (2048 input-domain samples, 1000 frames) a hand-off
 * period, so the time is the number of input-domain samples AHEAD of it -- the STOCK -- divided by the playout rate:
 *
 *     S = ring + (pushes already in the chunk being filled) + 2048 x READY + 2048 (the chunk PROGRAMMED at the last hand-off) + 2048 x (1 - phi)
 *
 * phi being the fraction of the hand-off period elapsed since the last hand-off, the last term the UNPLAYED part of the chunk that hand-off started.
 * gbp_aplay2's producer only MOVES samples ring -> filling chunk -> READY; the hand-off moves a chunk READY -> programmed -> playing; the AI plays the
 * playing chunk out. So S changes ONLY by the feed (+), the playout (-) and the corrector's one sample per DUP (+) or DROP (-): the SAWTOOTH the ring
 * shows is in how the stock is SPLIT, not in its total. At a chunk start READY = AHEAD - 1, so S = c + 2048 (AHEAD + 1) - 2048 phi (c = the ring at the
 * chunk's start, gbp_aplay2's cur_s0): the structure of #122's 4096 Hz formula, c + 128 (A + 1).
 *
 * WHAT THIS SHOWS (it does NOT show the DMA semantics: the harness's `playing = programmed; programmed = <the chunk just taken>` IS the assumption; a wrong assumption
 * is a wrong test, and a mutation that drops the programmed chunk fails only the formula check, not the flatness: the review of the derivation found this; the physical check is
 * HARDWARE_TESTS.md V28.22a), on the REAL chain (gbp_aplay2 over gbp_adec2), time-driven at the console's cadence (122.8 pump calls a hand-off period, the AI's
 * 32 028.483 Hz period, RUN 55's feed deficits): (1) READY is AHEAD - 1 at every chunk start; (2) S is FLAT over the whole run to within a few tens of
 * samples (well under a millisecond) at AHEAD 1, 2 and 4, while the ring alone swings by about 1.5 chunks; (3) S at every chunk start equals
 * c + 2048 (AHEAD + 1) - 2048 phi to within one push (the formula IS the definition at that instant); (4) the ring's mean and minimum follow from c and the
 * production time: mean = c - (2048 - feed x tau) / 2, min = c - 2048 + feed x tau, with tau the 32 calls a 64-push chunk takes.
 */
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "gbp_v28_step.h"

static int checks, failures;

static void check(int cond, const char *what)
{
    checks++;
    if (!cond) { failures++; printf("  FAIL: %s\n", what); }
}

static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events[GBP_APLAY2_EVENTS_CAP];
static int16_t ring[GBP_APLAY2_RING];
static struct gbp_aplay2 ap;
static struct gbp_adec2 adec;

#define AI_HZ           32028.483           /* GBP-HW-325 */
#define PERIOD_US       (1000.0 * 1e6 / AI_HZ)   /* one chunk of 1000 frames: 31 222 us */
#define CALLS_PER_PERIOD 122.8              /* RUN 55, p2: 236 074 pump calls in 60.0 s at that period */
#define FEED_HZ         65536.0             /* the game's own sample rate, times (1 - loss) */

struct result {
    uint32_t start_ready_bad, chunks, dup_total;
    double s_min, s_max, s_start_min, s_start_max, formula_err_max, ring_min, ring_sum, ring_n, cs_sum, cs_min, cs_max;
    double tau_us_sum;
};

static uint32_t give(uint32_t n)
{
    uint32_t k, put = 0;
    for (k = 0; k < n && adec.count < adec.cap; k++, put++) {
        adec.ring[(adec.head + adec.count) % adec.cap] = 100;
        adec.count++;
    }
    return put;
}

static double stock(int programmed, int playing, double phi)
{
    uint32_t filling = ap.cur >= 0 ? ap.cur_pushes : 0u;
    return (double)adec.count + (double)filling + (double)GBP_APLAY2_PUSHES * (double)gbp_aplay2_ready(&ap) +
           (double)GBP_APLAY2_PUSHES * (double)programmed + (double)GBP_APLAY2_PUSHES * (double)playing * (1.0 - phi);
}

static void run(uint32_t ahead, uint32_t target, double loss, double periods, struct result *r)
{
    double clock_us = 0.0, next_ho = PERIOD_US, last_ho = 0.0, feed_acc = 0.0, dt = PERIOD_US / CALLS_PER_PERIOD;
    int programmed = 0, playing = 0;
    uint32_t i, k;
    const double settle = 300.0;                 /* the ring above the band drains at the deficit (9 a chunk) until the corrector engages */
    double chunk_t0 = 0.0;
    memset(r, 0, sizeof *r);
    r->s_min = r->s_start_min = r->ring_min = r->cs_min = 1e18;
    memset(&ap, 0, sizeof ap);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    ap.step_pushes = gbp_v28_step_hook;
    ap.ahead = ahead;
    gbp_aplay2_set_target(&ap, target);
    (void)give(target);        /* the prefill periods feed the AHEAD builds' material; the ring leaves them at target, within one band of where the corrector holds it */
    for (i = 0; i < ahead; i++)
        for (k = 0; k < 123u; k++) {
            int b;
            (void)give(GBP_APLAY2_PUSHES / 123u);
            b = gbp_aplay2_produce(&ap, &adec);
            if (b >= 0) gbp_aplay2_queue(&ap, b);
            gbp_aplay2_process(&ap);
        }
    ap.playing = 1u;
    programmed = playing = 0;
    for (i = 0; (double)i < (settle + periods) * CALLS_PER_PERIOD; i++) {
        const int measuring = (double)i >= settle * CALLS_PER_PERIOD;
        int b;
        int32_t cur_pre;
        double s_pre, phi;
        uint32_t ready_pre, s0;
        clock_us += dt;
        feed_acc += FEED_HZ * (1.0 - loss) * dt * 1e-6;
        k = (uint32_t)feed_acc;
        feed_acc -= (double)k;
        (void)give(k);
        while (clock_us >= next_ho) {
            const uint8_t *h = gbp_aplay2_irq_handoff(&ap, (uint64_t)next_ho);
            playing = programmed;                                    /* the chunk programmed last time has just started */
            programmed = (h != silence) ? 1 : 0;                     /* the callback programs the chunk it took (a mute or a silence is not stock) */
            last_ho = next_ho;
            next_ho += PERIOD_US;
        }
        phi = (clock_us - last_ho) / PERIOD_US;
        cur_pre = ap.cur;
        s_pre = stock(programmed, playing, phi);
        ready_pre = gbp_aplay2_ready(&ap);
        s0 = (uint32_t)adec.count;
        if (cur_pre < 0) chunk_t0 = clock_us;
        b = gbp_aplay2_produce(&ap, &adec);
        if (b >= 0) gbp_aplay2_queue(&ap, b);
        gbp_aplay2_process(&ap);
        if (!measuring) continue;
        {
            const double s = stock(programmed, playing, phi);
            if (s < r->s_min) r->s_min = s;
            if (s > r->s_max) r->s_max = s;
            r->ring_sum += (double)adec.count; r->ring_n += 1.0;
            if ((double)adec.count < r->ring_min) r->ring_min = (double)adec.count;
        }
        if (cur_pre < 0 && ap.cur >= 0) {                            /* a chunk started in this call */
            const double formula = (double)s0 + (double)GBP_APLAY2_PUSHES * (double)(ahead + 1u) - (double)GBP_APLAY2_PUSHES * phi;
            double err = s_pre - formula;
            if (err < 0) err = -err;
            if (ready_pre != ahead - 1u) r->start_ready_bad++;
            if (err > r->formula_err_max) r->formula_err_max = err;
            if (s_pre < r->s_start_min) r->s_start_min = s_pre;
            if (s_pre > r->s_start_max) r->s_start_max = s_pre;
            r->cs_sum += (double)s0; r->chunks++;
            if ((double)s0 < r->cs_min) r->cs_min = (double)s0;
            if ((double)s0 > r->cs_max) r->cs_max = (double)s0;
        }
        if (cur_pre >= 0 && b >= 0 && chunk_t0 > 0.0) r->tau_us_sum += clock_us - chunk_t0;
    }
    r->dup_total = ap.dup;
}

static void report(const char *name, uint32_t ahead, uint32_t target, double loss, const struct result *r)
{
    const double rate = 2048.0 / (PERIOD_US * 1e-6);                    /* input-domain samples played a second: the AI's own clock */
    const double tau_us = r->chunks ? r->tau_us_sum / (double)r->chunks : 0.0;
    const double feed_tau = FEED_HZ * (1.0 - loss) * tau_us * 1e-6;
    const double c = r->chunks ? r->cs_sum / (double)r->chunks : 0.0;
    const double ring_mean = r->ring_n > 0.0 ? r->ring_sum / r->ring_n : 0.0;
    char w[200];
    printf("    %-34s A%u T%u loss %.2f%%: c %.0f (%.0f..%.0f)  S %.0f..%.0f (span %.1f samples = %.3f ms)  L %.2f ms  ring mean %.0f (model %.0f) min %.0f (model %.0f)  tau %.2f ms\n",
           name, ahead, target, loss * 100.0, c, r->cs_min, r->cs_max, r->s_min, r->s_max, r->s_max - r->s_min,
           (r->s_max - r->s_min) / rate * 1000.0, (r->s_start_min + r->s_start_max) / 2.0 / rate * 1000.0, ring_mean,
           c - (2048.0 - feed_tau) / 2.0, r->ring_min, r->cs_min - 2048.0 + feed_tau, tau_us / 1000.0);
    snprintf(w, sizeof w, "%s: READY is AHEAD - 1 at every chunk start", name);
    check(r->start_ready_bad == 0u && r->chunks > 100u, w);
    snprintf(w, sizeof w, "%s: the TOTAL stock is flat: span under 64 samples (0.98 ms) while the ring alone swings by over 1 000", name);
    check(r->s_max - r->s_min < 64.0, w);
    check(r->ring_n > 0.0 && (double)r->s_max - r->s_min < (ring_mean - r->ring_min) / 8.0, "the stock's span is a small fraction of the ring's own swing");
    snprintf(w, sizeof w, "%s: S at every chunk start equals c + 2048 (AHEAD + 1) - 2048 phi (the formula is the definition there)", name);
    check(r->formula_err_max < 1.0, w);
    snprintf(w, sizeof w, "%s: the ring's mean follows from c and the production time (within 40 samples)", name);
    check(fabs(ring_mean - (c - (2048.0 - feed_tau) / 2.0)) < 40.0, w);
    snprintf(w, sizeof w, "%s: and its minimum (within 40 samples)", name);
    check(fabs(r->ring_min - (r->cs_min - 2048.0 + feed_tau)) < 40.0, w);
    (void)target;
}

int main(void)
{
    static const struct { uint32_t a, t; double loss; const char *name; } CASES[] = {
        {1u, 4096u, 0.00355, "RUN 55's 3b hold (0.355 % loss)"},
        {1u, 4096u, 0.0018,  "0.18 % loss"},
        {2u, 4096u, 0.00355, "AHEAD 2"},
        {4u, 4096u, 0.00355, "AHEAD 4"},
        {1u, 3072u, 0.00355, "T192 (3072)"},
        {4u, 11264u, 0.00355, "T704 (11264), AHEAD 4"},
    };
    static struct result r;
    uint32_t i;
    printf("test_v28_stock\n");
    for (i = 0; i < sizeof CASES / sizeof CASES[0]; i++) {
        run(CASES[i].a, CASES[i].t, CASES[i].loss, 120.0, &r);
        report(CASES[i].name, CASES[i].a, CASES[i].t, CASES[i].loss, &r);
    }
    printf("  %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
