/*
 * gbp_adec — see gbp_adec.h. Integer arithmetic only; nothing here allocates,
 * blocks or touches a device.
 */
#include "gbp_adec.h"

#include <stddef.h>

static const uint8_t POPCOUNT8[256] = {
#define B2(n) n, n + 1, n + 1, n + 2
#define B4(n) B2(n), B2(n + 1), B2(n + 1), B2(n + 2)
#define B6(n) B4(n), B4(n + 1), B4(n + 1), B4(n + 2)
    B6(0), B6(1), B6(1), B6(2)
#undef B6
#undef B4
#undef B2
};

uint32_t gbp_adec_popcount(const uint8_t *block)
{
    uint32_t i, n = 0u;
    for (i = 0; i < GBP_ADEC_BLOCK_BYTES; i++)
        n += POPCOUNT8[block[i]];
    return n;
}

void gbp_adec_init(struct gbp_adec *d, int16_t *ring, uint32_t cap)
{
    d->rest_sum = 0;
    d->rest_n = 0u;
    d->rest_min = 0u;
    d->rest_max = 0u;
    d->ring = ring;
    d->cap = cap;
    d->head = 0u;
    d->count = 0u;
    d->last = 0;
    d->blocks_in = 0u;
    d->lost = 0u;
    d->overflow = 0u;
    d->clipped = 0u;
    d->discarded = 0u;
}

void gbp_adec_calibrate(struct gbp_adec *d, const uint8_t *block)
{
    const uint32_t p = gbp_adec_popcount(block);
    if (d->rest_n == 0u || p < d->rest_min) d->rest_min = p;
    if (d->rest_n == 0u || p > d->rest_max) d->rest_max = p;
    d->rest_sum += (int64_t)p;
    d->rest_n++;
}

/* round( num / den ) for den > 0, halves to EVEN -- the rule Python's round()
 * applies, which is what makes the result identical to tools/v17decode.py. */
static int64_t div_round_half_even(int64_t num, int64_t den)
{
    int64_t q = num / den, r = num % den;       /* C truncates toward zero */
    if (r < 0) { q -= 1; r += den; }            /* now floor division, 0 <= r < den */
    if (2 * r > den || (2 * r == den && (q & 1)))
        q += 1;
    return q;
}

/* The formula before its clip; 0 when the decoder is not calibrated. */
static int64_t sample_unclipped(const struct gbp_adec *d, uint32_t popcount)
{
    int64_t n, num;
    if (d->rest_n == 0u)
        return 0;
    n = (int64_t)d->rest_n;
    num = (n * (int64_t)popcount - d->rest_sum) * (int64_t)GBP_ADEC_FULL;
    return div_round_half_even(num, 5 * 1024 * n);
}

static int16_t clip(int64_t v)
{
    if (v > GBP_ADEC_FULL) v = GBP_ADEC_FULL;
    if (v < -GBP_ADEC_FULL) v = -GBP_ADEC_FULL;
    return (int16_t)v;
}

int16_t gbp_adec_sample(const struct gbp_adec *d, uint32_t popcount)
{
    return clip(sample_unclipped(d, popcount));
}

static int ring_put(struct gbp_adec *d, int16_t s)
{
    if (d->count >= d->cap) {
        d->overflow++;
        return -1;
    }
    d->ring[(d->head + d->count) % d->cap] = s;
    d->count++;
    return 0;
}

int gbp_adec_push_block(struct gbp_adec *d, const uint8_t *block)
{
    const int64_t v = sample_unclipped(d, gbp_adec_popcount(block));
    const int16_t s = clip(v);
    if (v > GBP_ADEC_FULL || v < -GBP_ADEC_FULL) d->clipped++;     /* Issue #110: counted, not changed */
    d->blocks_in++;
    d->last = s;
    return ring_put(d, s);
}

int gbp_adec_push_lost(struct gbp_adec *d)
{
    d->lost++;
    return ring_put(d, d->last);
}

int gbp_adec_pop(struct gbp_adec *d, int16_t *out)
{
    if (d->count == 0u)
        return 0;
    *out = d->ring[d->head];
    d->head = (d->head + 1u) % d->cap;
    d->count--;
    return 1;
}

uint32_t gbp_adec_discard(struct gbp_adec *d, uint32_t n)
{
    if (n > d->count)
        n = d->count;
    if (n == 0u)
        return 0u;
    d->head = (d->head + n) % d->cap;
    d->count -= n;
    d->discarded += n;
    return n;
}
