/*
 * gbp_aplay2 — see gbp_aplay2.h. The correction/sub-block decision logic below is gbp_aplay.c's
 * produce_impl, ported: same gate (PUSHES + 1), same per-sub-block decision (the chunk-start
 * frame, cur_s0 + cur_pushes - cur_taken against cur_target), same corr_forgone accounting
 * (Issue #123/#124, GBP-HW-349). Only the destination differs: an output RING here, an AI chunk
 * buffer pool + hand-off queue there.
 */
#include "gbp_aplay2.h"

#include <string.h>

#include "gbp_aresamp2_coef.h"       /* GBP_ARESAMP2_M, for the chunk-alignment static assert below */

void gbp_aplay2_init(struct gbp_aplay2 *p, int16_t *out_ring, uint32_t out_cap)
{
    if (!p) return;
    memset(p, 0, sizeof *p);
    gbp_aresamp2_init(&p->rs);
    p->ring = out_ring;
    p->cap = out_cap;
    p->target = GBP_APLAY2_TARGET;
    p->corr_per_chunk = GBP_APLAY2_K_DEFAULT;          /* this path's fixed default (GBP-HW-349) */
}

_Static_assert(((uint64_t)GBP_ADEC2_RATE * GBP_APLAY2_CUSHION_US) % 1000000u == 0u,
               "the cushion must be a whole number of decoded samples at this path's rate");
_Static_assert(GBP_APLAY2_TARGET >= GBP_APLAY2_TARGET_MIN && GBP_APLAY2_TARGET <= GBP_APLAY2_TARGET_MAX,
               "the default cushion must be a target gbp_aplay2_set_target() would accept unclamped");
_Static_assert(GBP_APLAY2_PUSHES % GBP_APLAY2_K_DEFAULT == 0u &&
               GBP_APLAY2_K_DEFAULT <= GBP_APLAY2_PUSHES / 2u,
               "the default k must itself be a legal gbp_aplay2_set_corrections() value");
_Static_assert(GBP_APLAY2_PUSHES % GBP_ARESAMP2_M == 0u,
               "a chunk must span a whole number of the resampler's periods, so acc == 0 at every boundary");

int gbp_aplay2_set_corrections(struct gbp_aplay2 *p, uint32_t k)
{
    if (!p || k == 0u || k > GBP_APLAY2_PUSHES / 2u || GBP_APLAY2_PUSHES % k != 0u) return -1;
    p->corr_per_chunk = k;
    return 0;
}

void gbp_aplay2_set_target(struct gbp_aplay2 *p, uint32_t target)
{
    if (!p) return;
    if (target < GBP_APLAY2_TARGET_MIN) target = GBP_APLAY2_TARGET_MIN;
    if (target > GBP_APLAY2_TARGET_MAX) target = GBP_APLAY2_TARGET_MAX;
    p->target = target;
}

static int out_put(struct gbp_aplay2 *p, int16_t s)
{
    if (p->count >= p->cap) return -1;              /* the caller's ring is full: a host-harness sizing error */
    p->ring[(p->head + p->count) % p->cap] = s;
    p->count++;
    return 0;
}

static void push_one2(struct gbp_aplay2 *p, int16_t x)
{
    int16_t y[GBP_ARESAMP2_MAX_OUT];
    const uint32_t n = gbp_aresamp2_push(&p->rs, x, y);
    uint32_t i;
    for (i = 0; i < n; i++)
        if (out_put(p, y[i]) != 0) p->out_overflow++;
    p->cur_pushes++;
}

static int take2(struct gbp_adec2 *d, int16_t *x)
{
    return gbp_adec2_pop(d, x);
}

int gbp_aplay2_produce_ex(struct gbp_aplay2 *p, struct gbp_adec2 *d, uint32_t max_pushes, int uncorrected)
{
    uint32_t step = 0u;
    if (!p || !d) return 0;
    if (!p->started) {
        /* a chunk is only started when the ring can finish it: PUSHES pushes, one more for a
         * DROP. The gate is PUSHES + 1 whatever k is (gbp_aplay.c's third review; GBP-HW-349
         * confirms the same argument holds at this path's k = 16). */
        if (d->count < GBP_APLAY2_PUSHES + 1u) {
            p->starved_steps++;
            return 0;
        }
        p->started = 1;
        p->cur_pushes = 0u;
        p->cur_corr = 0u;
        p->cur_corr_done = 1u;
        /* before playback a chunk takes at most one correction: the ring filling up is not drift */
        p->cur_k = p->playing ? p->corr_per_chunk : 1u;
        p->cur_s0 = d->count;
        p->cur_target = p->target;
        p->cur_sub = 0u;
        p->cur_taken = 0u;
        p->cur_uncorrected = (uint8_t)(uncorrected ? 1u : 0u);
    }
    while (p->cur_pushes < GBP_APLAY2_PUSHES && (max_pushes == 0u || step < max_pushes)) {
        int16_t x;
        /* a sub-block's decision, at its FIRST push, made by a corrected call; the chunk's frame
         * (cur_s0 + cur_pushes - cur_taken) against cur_target -- gbp_aplay.c's Issue #123 logic,
         * unchanged. */
        if (!uncorrected && !p->cur_uncorrected && p->cur_sub < p->cur_k &&
            p->cur_pushes % (GBP_APLAY2_PUSHES / p->cur_k) == 0u &&
            p->cur_pushes / (GBP_APLAY2_PUSHES / p->cur_k) >= p->cur_sub) {
            const uint32_t fill = p->cur_s0 + p->cur_pushes - p->cur_taken;
            p->cur_corr = (fill < p->cur_target - GBP_APLAY2_BAND) ? GBP_APLAY2_EV_DUP :
                          (fill > p->cur_target + GBP_APLAY2_BAND) ? GBP_APLAY2_EV_DROP : 0u;
            p->cur_corr_done = 0u;
            p->corr_forgone += p->cur_pushes / (GBP_APLAY2_PUSHES / p->cur_k) - p->cur_sub;
            p->cur_sub = p->cur_pushes / (GBP_APLAY2_PUSHES / p->cur_k) + 1u;
        }
        if (!take2(d, &x)) { p->starved_steps++; return 0; }   /* cannot happen: checked at the start */
        p->cur_taken++;
        if (p->cur_corr == GBP_APLAY2_EV_DROP && !p->cur_corr_done) {
            p->cur_corr_done = 1u;
            p->drop++;
            continue;                                          /* the sample is not pushed */
        }
        push_one2(p, x);
        step++;
        if (p->cur_corr == GBP_APLAY2_EV_DUP && !p->cur_corr_done && p->cur_pushes < GBP_APLAY2_PUSHES) {
            p->cur_corr_done = 1u;
            p->dup++;
            push_one2(p, x);                                   /* pushed twice */
            step++;
        }
    }
    if (p->cur_pushes < GBP_APLAY2_PUSHES) return 0;
    if (!p->cur_uncorrected) p->corr_forgone += p->cur_k - p->cur_sub;   /* the rest, undecided */
    p->started = 0;
    p->produced++;
    return 1;
}

int gbp_aplay2_produce(struct gbp_aplay2 *p, struct gbp_adec2 *d, uint32_t max_pushes)
{
    return gbp_aplay2_produce_ex(p, d, max_pushes, 0);
}

int gbp_aplay2_pop(struct gbp_aplay2 *p, int16_t *out)
{
    if (p->count == 0u)
        return 0;
    *out = p->ring[p->head];
    p->head = (p->head + 1u) % p->cap;
    p->count--;
    return 1;
}
