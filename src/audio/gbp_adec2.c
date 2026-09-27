/*
 * gbp_adec2 — see gbp_adec2.h. Integer arithmetic only; nothing here allocates, blocks or
 * touches a device.
 */
#include "gbp_adec2.h"

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

uint32_t gbp_adec2_slice_sum(const uint8_t *block, uint32_t slice)
{
    const uint8_t *sl = block + (size_t)slice * GBP_ADEC2_SLICE_BYTES;
    uint32_t g, wa = 0u, wb = 0u;
    for (g = 0; g < GBP_ADEC2_SLICE_BYTES / GBP_ADEC2_GROUP_BYTES; g++) {
        wa += POPCOUNT8[sl[g * GBP_ADEC2_GROUP_BYTES + GBP_ADEC2_STREAM_A]];
        wb += POPCOUNT8[sl[g * GBP_ADEC2_GROUP_BYTES + GBP_ADEC2_STREAM_B]];
    }
    return wa + wb;
}

void gbp_adec2_init(struct gbp_adec2 *d, int16_t *ring, uint32_t cap)
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

void gbp_adec2_calibrate(struct gbp_adec2 *d, const uint8_t *block)
{
    uint32_t s;
    for (s = 0; s < GBP_ADEC2_SLICES_PER_BLOCK; s++) {
        const uint32_t p = gbp_adec2_slice_sum(block, s);
        if (d->rest_n == 0u || p < d->rest_min) d->rest_min = p;
        if (d->rest_n == 0u || p > d->rest_max) d->rest_max = p;
        d->rest_sum += (int64_t)p;
        d->rest_n++;
    }
}

/* round( num / den ) for den > 0, halves to EVEN, same rule gbp_adec.c uses. */
static int64_t div_round_half_even2(int64_t num, int64_t den)
{
    int64_t q = num / den, r = num % den;       /* C truncates toward zero */
    if (r < 0) { q -= 1; r += den; }            /* now floor division, 0 <= r < den */
    if (2 * r > den || (2 * r == den && (q & 1)))
        q += 1;
    return q;
}

/* The formula before its clip; 0 when the decoder is not calibrated. */
static int64_t sample2_unclipped(const struct gbp_adec2 *d, uint32_t p)
{
    int64_t n, num;
    if (d->rest_n == 0u)
        return 0;
    n = (int64_t)d->rest_n;
    num = (n * (int64_t)p - d->rest_sum) * (int64_t)GBP_ADEC2_FULL;
    return div_round_half_even2(num, (int64_t)GBP_ADEC2_GAIN_DENOM * n);
}

static int16_t clip2(int64_t v)
{
    if (v > GBP_ADEC2_FULL) v = GBP_ADEC2_FULL;
    if (v < -GBP_ADEC2_FULL) v = -GBP_ADEC2_FULL;
    return (int16_t)v;
}

int16_t gbp_adec2_sample(const struct gbp_adec2 *d, uint32_t p)
{
    return clip2(sample2_unclipped(d, p));
}

static int ring_put2(struct gbp_adec2 *d, int16_t s)
{
    if (d->count >= d->cap) {
        d->overflow++;
        return -1;
    }
    d->ring[(d->head + d->count) % d->cap] = s;
    d->count++;
    return 0;
}

uint32_t gbp_adec2_push_block(struct gbp_adec2 *d, const uint8_t *block)
{
    uint32_t s, pushed = 0u;
    d->blocks_in++;
    for (s = 0; s < GBP_ADEC2_SLICES_PER_BLOCK; s++) {
        const int64_t v = sample2_unclipped(d, gbp_adec2_slice_sum(block, s));
        const int16_t x = clip2(v);
        if (v > GBP_ADEC2_FULL || v < -GBP_ADEC2_FULL) d->clipped++;
        d->last = x;
        if (ring_put2(d, x) == 0) pushed++;
    }
    return pushed;
}

uint32_t gbp_adec2_push_lost(struct gbp_adec2 *d)
{
    uint32_t s, pushed = 0u;
    d->lost++;
    for (s = 0; s < GBP_ADEC2_SLICES_PER_BLOCK; s++)
        if (ring_put2(d, d->last) == 0) pushed++;
    return pushed;
}

int gbp_adec2_pop(struct gbp_adec2 *d, int16_t *out)
{
    if (d->count == 0u)
        return 0;
    *out = d->ring[d->head];
    d->head = (d->head + 1u) % d->cap;
    d->count--;
    return 1;
}

uint32_t gbp_adec2_discard(struct gbp_adec2 *d, uint32_t n)
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
