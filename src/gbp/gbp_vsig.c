#include "gbp_vsig.h"

#include <string.h>

uint32_t gbp_vsig_block(const uint8_t *raw, uint32_t len)
{
    uint64_t total = 0;
    uint32_t it;
    if (!raw || len != GBP_VSIG_BLOCK_SIZE) return 0u;
    for (it = 0; it < GBP_VSIG_GROUPS; it++) {
        const uint8_t *p = raw + (size_t)it * 16u;
        /* Two 32-bit words per group, each packing two pixels as byte 1 : byte 3.
         * Bytes 0 and 2 of every source word are never read — that is the whole
         * reason a byte-0 deviation cannot change this value. */
        uint32_t d0 = ((uint32_t)p[1] << 24) | ((uint32_t)p[3] << 16) | ((uint32_t)p[5] << 8) | (uint32_t)p[7];
        uint32_t d1 = ((uint32_t)p[9] << 24) | ((uint32_t)p[11] << 16) | ((uint32_t)p[13] << 8) | (uint32_t)p[15];
        total += (uint64_t)d0 + (uint64_t)d1;
    }
    /* stored = low 32 bits + carry count, exactly as GBI stores its table entries */
    return (uint32_t)((total & 0xFFFFFFFFu) + (total >> 32));
}

int gbp_vsig_flag_gbi(const uint8_t first4[4])
{
    uint32_t w;
    if (!first4) return 0;
    w = ((uint32_t)first4[0] << 24) | ((uint32_t)first4[1] << 16) | ((uint32_t)first4[2] << 8) | (uint32_t)first4[3];
    return (w & GBP_VSIG_GBI_MASK) == GBP_VSIG_GBI_MASK ? 1 : 0;
}

int gbp_vsig_flag_disc(const uint8_t first4[4])
{
    uint32_t hw;
    if (!first4) return 0;
    hw = ((uint32_t)first4[0] << 8) | (uint32_t)first4[1];
    return ((hw >> 7) & 1u) ? 1 : 0;
}

/* ---- cost histogram ---------------------------------------------------
 * Buckets 0..GBP_VSIG_HIST_LINEAR-1 cover exactly one tick each. Above that
 * the width doubles every 8 buckets, which keeps 64 more buckets enough to
 * reach far beyond any plausible per-block cost while the resolution near
 * the expected range stays fine. The boundaries are computed by the same
 * function the lookup uses, so a bucket's range and its membership test can
 * never disagree. */
static uint32_t geom_width(unsigned g)
{
    unsigned shift = g / 8u;
    if (shift > 20u) shift = 20u;                 /* bounded: no overflow of a u32 width */
    return 1u << shift;
}

void gbp_vsig_cost_bucket_range(unsigned i, uint32_t *lo, uint32_t *hi)
{
    uint32_t base = GBP_VSIG_HIST_LINEAR;
    unsigned g;
    if (lo) *lo = 0u;
    if (hi) *hi = 0u;
    if (i >= GBP_VSIG_HIST_BUCKETS) return;
    if (i < GBP_VSIG_HIST_LINEAR) {
        if (lo) *lo = i;
        if (hi) *hi = i;
        return;
    }
    for (g = 0; g < i - GBP_VSIG_HIST_LINEAR; g++) base += geom_width(g);
    if (lo) *lo = base;
    if (hi) *hi = base + geom_width(i - GBP_VSIG_HIST_LINEAR) - 1u;
}

unsigned gbp_vsig_cost_bucket_of(uint32_t ticks)
{
    uint32_t base = GBP_VSIG_HIST_LINEAR;
    unsigned g;
    if (ticks < GBP_VSIG_HIST_LINEAR) return (unsigned)ticks;
    for (g = 0; g < GBP_VSIG_HIST_GEOM; g++) {
        uint32_t w = geom_width(g);
        if (ticks < base + w) return GBP_VSIG_HIST_LINEAR + g;
        base += w;
    }
    return GBP_VSIG_HIST_BUCKETS;                 /* overflow */
}

void gbp_vsig_cost_init(struct gbp_vsig_cost *c)
{
    if (!c) return;
    memset(c, 0, sizeof *c);
    c->min = 0xFFFFFFFFu;
}

void gbp_vsig_cost_add(struct gbp_vsig_cost *c, uint32_t ticks)
{
    unsigned b;
    if (!c) return;
    if (c->count == 0u || ticks < c->min) c->min = ticks;
    if (ticks > c->max) c->max = ticks;
    c->count++;
    c->sum += (uint64_t)ticks;
    b = gbp_vsig_cost_bucket_of(ticks);
    if (b >= GBP_VSIG_HIST_BUCKETS) { c->overflow++; return; }
    if (c->buckets[b] != 0xFFFFFFFFu) c->buckets[b]++;   /* saturating: never wraps silently */
}

uint32_t gbp_vsig_cost_quantile(const struct gbp_vsig_cost *c, unsigned permille, int *exact, uint32_t *width)
{
    uint64_t target, seen = 0;
    unsigned i;
    if (exact) *exact = 0;
    if (width) *width = 0;
    if (!c || c->count == 0u) return 0u;
    if (permille > 1000u) permille = 1000u;
    /* the sample at position ceil(count * permille / 1000), 1-based */
    target = (c->count * (uint64_t)permille + 999u) / 1000u;
    if (target == 0u) target = 1u;
    for (i = 0; i < GBP_VSIG_HIST_BUCKETS; i++) {
        seen += (uint64_t)c->buckets[i];
        if (seen >= target) {
            uint32_t lo = 0, hi = 0;
            gbp_vsig_cost_bucket_range(i, &lo, &hi);
            if (exact) *exact = (hi == lo) ? 1 : 0;
            if (width) *width = hi - lo + 1u;
            return hi;
        }
    }
    /* the quantile lies in the overflow: the only honest answer is the observed maximum */
    if (exact) *exact = 0;
    if (width) *width = 0;
    return c->max;
}

uint32_t gbp_vsig_cost_mean(const struct gbp_vsig_cost *c)
{
    if (!c || c->count == 0u) return 0u;
    return (uint32_t)(c->sum / c->count);
}
