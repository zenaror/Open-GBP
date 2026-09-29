/*
 * gbp_v28_dma -- see gbp_v28_dma.h.
 */
#include <string.h>
#include "gbp_v28_dma.h"

void gbp_v28_dma_init(struct gbp_v28_dma *d)
{
    memset(d, 0, sizeof *d);
    d->left_min = 0xFFFFFFFFu;
}

uint32_t gbp_v28_dma_phys(const void *p)
{
    return (uint32_t)(uintptr_t)p & 0x1FFFFFE0u;
}

void gbp_v28_dma_seed(struct gbp_v28_dma *d, const void *first)
{
    d->ret1 = gbp_v28_dma_phys(first);
    d->ret2 = 0u;
    d->seeded = 1u;
}

void gbp_v28_dma_note(struct gbp_v28_dma *d, uint32_t addr, uint32_t left, uint64_t t, const void *returned)
{
    uint32_t bin;
    if (d->seeded) {
        if (d->ret1 == d->ret2) d->same12++;
        else if (addr == d->ret1) d->prev1++;
        else if (addr == d->ret2) d->prev2++;
        else d->none++;
    }
    if (left < d->left_min) d->left_min = left;
    if (left > d->left_max) d->left_max = left;
    d->left_sum += left;
    bin = left >= 4000u ? 5u : left >= 3500u ? 4u : left >= 3000u ? 3u : left >= 2000u ? 2u : left >= 1000u ? 1u : 0u;
    d->bins[bin]++;
    if (d->raw_n < GBP_V28_DMA_RAW) {
        struct gbp_v28_dma_raw *r = &d->raw[d->raw_n++];
        r->addr = addr;
        r->left = left;
        r->ret1 = d->ret1;
        r->ret2 = d->ret2;
        r->dt = d->t_last ? (uint32_t)(t - d->t_last) : 0u;
    }
    d->t_last = t;
    d->n++;
    d->ret2 = d->ret1;
    d->ret1 = gbp_v28_dma_phys(returned);
}
