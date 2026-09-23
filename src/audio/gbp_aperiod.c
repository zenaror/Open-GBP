/*
 * gbp_aperiod — see gbp_aperiod.h.
 */
#include "gbp_aperiod.h"

/* popcount of a byte, built as gbp_adec.c and gbp_adrain.c build it. */
#define B2(n)  n,     (n) + 1,     (n) + 1,     (n) + 2
#define B4(n)  B2(n), B2((n) + 1), B2((n) + 1), B2((n) + 2)
#define B6(n)  B4(n), B4((n) + 1), B4((n) + 1), B4((n) + 2)
static const uint8_t POPCOUNT8[256] = { B6(0), B6(1), B6(1), B6(2) };

void gbp_aperiod_reset(struct gbp_aperiod *p, uint32_t expected)
{
    if (!p) return;
    p->expected = expected;
    p->blocks = 0u;
    p->prev = -1;
    p->last_edge = 0u;
    p->have_edge = 0u;
    p->edges = 0u;
    p->periods = 0u;
    p->pmin = 0u;
    p->pmax = 0u;
    p->off = 0u;
    p->crossings = 0u;
    p->steps_visible = 0u;
    p->refused = 0u;
    p->last_sample = -1;
}

int32_t gbp_aperiod_feed(struct gbp_aperiod *p, const uint8_t *data, uint32_t n)
{
    uint32_t off, total = 0u, smin = 0xFFFFFFFFu, smax = 0u, whole = 0u;
    int32_t sample;
    if (!p) return -1;
    if (!data || n == 0u || n > GBP_APERIOD_BLOCK || (n & 31u) != 0u) {
        p->refused++;
        return -1;
    }
    /* ONE pass: the total for the sample, and each WHOLE slice's own count for
     * the within-block step. A partial slice (n < 256) is counted in the total
     * and in no comparison. */
    for (off = 0u; off < n; off += GBP_APERIOD_SLICE) {
        const uint32_t len = (n - off < GBP_APERIOD_SLICE) ? (n - off) : GBP_APERIOD_SLICE;
        uint32_t i, c = 0u;
        for (i = 0u; i < len; i++)
            c += POPCOUNT8[data[off + i]];
        total += c;
        if (len == GBP_APERIOD_SLICE) {
            if (c < smin) smin = c;
            if (c > smax) smax = c;
            whole++;
        }
    }
    /* B4, frozen: exact for every power-of-two N, truncating for any other
     * legal N -- the same arithmetic as gbp_adrain_sample_from_short_read(). */
    sample = (int32_t)(total * (GBP_APERIOD_BLOCK / n));
    if (whole >= 2u && smax - smin > GBP_APERIOD_STEP_BITS)
        p->steps_visible++;
    if (p->prev >= 0) {
        const int was_high = p->prev > (int32_t)GBP_APERIOD_REST;
        const int is_high = sample > (int32_t)GBP_APERIOD_REST;
        if (was_high != is_high)
            p->crossings++;
        if (!was_high && is_high) {                    /* prev <= rest < cur */
            if (p->have_edge) {
                const uint32_t per = p->blocks - p->last_edge;
                if (p->periods == 0u || per < p->pmin) p->pmin = per;
                if (per > p->pmax) p->pmax = per;
                if (per != p->expected) p->off++;
                p->periods++;
            }
            p->last_edge = p->blocks;
            p->have_edge = 1u;
            p->edges++;
        }
    }
    p->prev = sample;
    p->last_sample = sample;
    p->blocks++;
    return sample;
}

int gbp_aperiod_exact(const struct gbp_aperiod *p, uint32_t min_periods)
{
    if (!p || p->periods == 0u || p->periods < min_periods)
        return 0;
    return (p->pmin == p->expected && p->pmax == p->expected) ? 1 : 0;
}
