/*
 * tests/unit/test_v28_latency_tag.c -- GitHub Issue #139 (U-GBP-049): the latency formula against EVERY SAMPLE's own latency.
 *
 * tests/unit/test_v28_stock.c proves the STOCK is conserved; this test measures the quantity the formula is for, sample by sample, without going through the
 * stock: every input-domain sample entering the ring is tagged with its arrival time; the producer's pushes are followed from the ring into their chunk (a sample
 * at position p of a chunk, resampled by the real gbp_aplay2 over gbp_adec2), the chunk plays from the hand-off AFTER the one that took it (the DMA semantics the
 * harness ASSUMES: the callback programs the chunk it takes, which starts at the next callback), sample p at p x (period / 2048), plus the resampler's 8 samples.
 * The latency of a sample is that play time minus its arrival time.
 *
 * WHAT IT SHOWS (found by the adversarial review of the derivation): the stock over the playout rate is not the whole latency. While a sample waits in the ring the
 * corrector inserts DUPs ahead of it (a DUP pushes a sample without taking one from the ring), (playout - feed) x t_ring of them, so the sample waits
 * (playout - feed) / playout x t_ring longer: +0.23 ms at T256 / A1, +0.71 ms at T704 / A4. The formula tools/v28latency.py prints,
 *     L = (c + 2048 (A + 1) - 2048 phi) / playout + 0.122 ms + (c - (2048 - feed x tau) / 2) x delta / playout,
 * is checked here against the tagged mean at six (T, A, loss) points, and the per-sample spread is bounded.
 *
 * WHAT IT CANNOT SHOW: the DMA semantics themselves. The harness assumes them (that is the (A + 1)); a wrong assumption is a wrong test. Only a physical read of the AI's
 * registers at a callback's entry can tell (HARDWARE_TESTS.md V28.22).
 */
#include <stdio.h>
#include <stdlib.h>
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

#define AI_HZ       32028.483
#define PERIOD_US   (1000.0 * 1e6 / AI_HZ)
#define CALLS       122.8
#define MAXN        1200000u
#define MAXCH       4000u
#define RESAMPLER_US (8.0 * 1e6 / 65536.0)

static double *arr_t;
static uint64_t given_total;
static double play_start[MAXCH];
static int have_play[MAXCH];

struct rec { uint32_t seq, pb, pa; uint64_t cb, ca; };
static struct rec *recs;
static uint32_t nrec;

static uint32_t give(uint32_t n, double t)
{
    uint32_t k, put = 0;
    for (k = 0; k < n && adec.count < adec.cap && given_total < MAXN; k++, put++) {
        adec.ring[(adec.head + adec.count) % adec.cap] = 100;
        adec.count++;
        arr_t[given_total++] = t;
    }
    return put;
}

struct out { double mean, min, max, c_mean, phi_mean; uint64_t n; uint32_t chunks; };

static void run(uint32_t ahead, uint32_t target, double loss, struct out *o)
{
    const double feedhz = 65536.0 * (1.0 - loss), dt = PERIOD_US / CALLS, settle = 300.0, periods = 120.0;
    double clock_us = 0.0, next_ho = PERIOD_US, feed_acc = 0.0, last_ho = 0.0, csum = 0.0, phisum = 0.0, t_meas0 = settle * PERIOD_US;
    uint32_t i, k, cs_n = 0;
    double sum = 0.0, mn = 1e18, mx = -1e18;
    uint64_t n = 0;
    uint32_t j;
    given_total = 0u;
    nrec = 0u;
    memset(have_play, 0, sizeof have_play);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    memset(&ap, 0, sizeof ap);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    ap.step_pushes = gbp_v28_step_hook;
    ap.ahead = ahead;
    gbp_aplay2_set_target(&ap, target);
    (void)give(target, 0.0);
    for (i = 0; i < ahead; i++)
        for (k = 0; k < 123u; k++) {
            int b;
            (void)give(GBP_APLAY2_PUSHES / 123u, 0.0);
            b = gbp_aplay2_produce(&ap, &adec);
            if (b >= 0) gbp_aplay2_queue(&ap, b);
            gbp_aplay2_process(&ap);
        }
    ap.playing = 1u;
    for (i = 0; (double)i < (settle + periods) * CALLS; i++) {
        int b;
        int32_t curpre;
        uint32_t producedpre, pb;
        uint64_t cb, ca;
        clock_us += dt;
        feed_acc += feedhz * dt * 1e-6;
        k = (uint32_t)feed_acc;
        feed_acc -= (double)k;
        (void)give(k, clock_us);
        while (clock_us >= next_ho) {
            const uint8_t *h = gbp_aplay2_irq_handoff(&ap, (uint64_t)next_ho);
            if (h != silence) {
                const uint32_t s = ap.seq[(int)((h - pool) / GBP_APLAY2_CHUNK_BYTES)];
                if (s < MAXCH) { play_start[s] = next_ho + PERIOD_US; have_play[s] = 1; }   /* the chunk taken now plays from the NEXT callback */
            }
            last_ho = next_ho;
            next_ho += PERIOD_US;
        }
        pb = ap.cur >= 0 ? ap.cur_pushes : 0u;
        cb = given_total - adec.count;
        curpre = ap.cur;
        producedpre = ap.produced;
        b = gbp_aplay2_produce(&ap, &adec);
        if (b >= 0) gbp_aplay2_queue(&ap, b);
        gbp_aplay2_process(&ap);
        ca = given_total - adec.count;
        if (curpre < 0 && ap.cur >= 0 && (double)i >= settle * CALLS) {
            csum += (double)ap.cur_s0;
            phisum += (clock_us - last_ho) / PERIOD_US;
            cs_n++;
        }
        if (ca > cb && nrec < 400000u) {
            struct rec *r = &recs[nrec++];
            r->seq = curpre >= 0 ? ap.seq[curpre] : (b >= 0 ? producedpre : ap.seq[ap.cur >= 0 ? ap.cur : 0]);
            r->pb = pb;
            r->pa = b >= 0 ? GBP_APLAY2_PUSHES : ap.cur_pushes;
            r->cb = cb;
            r->ca = ca;
        }
    }
    for (j = 0; j < nrec; j++) {
        const struct rec *r = &recs[j];
        uint64_t s;
        if (r->seq >= MAXCH || !have_play[r->seq]) continue;
        for (s = r->cb; s < r->ca; s++) {
            const double frac = (double)(s - r->cb) / (double)(r->ca - r->cb);
            const double pos = (double)r->pb + frac * ((double)r->pa - (double)r->pb);
            const double tplay = play_start[r->seq] + pos * (PERIOD_US / 2048.0) + RESAMPLER_US;
            const double L = (tplay - arr_t[s]) / 1000.0;
            if (arr_t[s] < t_meas0 || arr_t[s] == 0.0) continue;
            sum += L; n++;
            if (L < mn) mn = L;
            if (L > mx) mx = L;
        }
    }
    o->mean = n ? sum / (double)n : 0.0; o->min = mn; o->max = mx; o->n = n;
    o->c_mean = cs_n ? csum / cs_n : 0.0; o->phi_mean = cs_n ? phisum / cs_n : 0.0; o->chunks = cs_n;
}

int main(void)
{
    static const struct { uint32_t a, t; double loss; } CASES[] = {
        {1u, 4096u, 0.00355}, {1u, 4096u, 0.0018}, {1u, 3072u, 0.00355}, {2u, 7168u, 0.00355}, {4u, 11264u, 0.00355}, {4u, 11264u, 0.0065},
    };
    const double rate = 2048.0 / (PERIOD_US * 1e-6);
    uint32_t i;
    arr_t = malloc(sizeof(double) * MAXN);
    recs = malloc(sizeof(struct rec) * 400000u);
    printf("test_v28_latency_tag\n");
    for (i = 0; i < sizeof CASES / sizeof CASES[0]; i++) {
        struct out o;
        const double delta = (rate - 65536.0 * (1.0 - CASES[i].loss)) / rate;
        double stock_only, full;
        char w[160];
        run(CASES[i].a, CASES[i].t, CASES[i].loss, &o);
        stock_only = (o.c_mean + 2048.0 * (CASES[i].a + 1u) - 2048.0 * o.phi_mean) / rate * 1000.0 + RESAMPLER_US / 1000.0;
        full = stock_only + (o.c_mean - (2048.0 - 65536.0 * (1.0 - CASES[i].loss) * (32.0 / CALLS * PERIOD_US * 1e-6)) / 2.0) * delta / rate * 1000.0;
        printf("    A%u T%u loss %.3f%%: tagged L mean %.3f ms (%.3f .. %.3f) over %llu samples; c %.0f phi %.4f; stock only %.3f, + DUP delay %.3f\n",
               CASES[i].a, CASES[i].t, CASES[i].loss * 100.0, o.mean, o.min, o.max, (unsigned long long)o.n, o.c_mean, o.phi_mean, stock_only, full);
        snprintf(w, sizeof w, "A%u T%u: enough samples were tagged", CASES[i].a, CASES[i].t);
        check(o.n > 100000u && o.chunks > 100u, w);
        snprintf(w, sizeof w, "A%u T%u: the tagged mean is within 0.1 ms of the formula with the DUP delay", CASES[i].a, CASES[i].t);
        check(fabs(o.mean - full) < 0.1, w);
        snprintf(w, sizeof w, "A%u T%u: the stock alone UNDERSTATES it (the DUP delay is real, over 0.03 ms)", CASES[i].a, CASES[i].t);
        check(o.mean - stock_only > 0.03, w);
        snprintf(w, sizeof w, "A%u T%u: the per-sample spread is under 0.6 ms", CASES[i].a, CASES[i].t);
        check(o.max - o.min < 0.6, w);
    }
    printf("  %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
