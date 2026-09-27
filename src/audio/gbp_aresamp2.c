/*
 * gbp_aresamp2 — see gbp_aresamp2.h. Identical engine to gbp_aresamp.c; only the ratio and the
 * table differ.
 */
#include "gbp_aresamp2.h"

#include "gbp_aresamp2_coef.h"

void gbp_aresamp2_init(struct gbp_aresamp2 *r)
{
    uint32_t i;
    for (i = 0; i < GBP_ARESAMP2_TAPS; i++)
        r->hist[i] = 0;
    r->hpos = 0u;
    r->acc = 0u;
    r->in_count = 0u;
    r->out_count = 0u;
}

/* Q15 -> integer, halves away from zero, clipped to int16. Same as gbp_aresamp.c's. */
static int16_t q15_round2(int64_t v)
{
    int64_t q = (v >= 0) ? ((v + 16384) >> 15) : -(((-v) + 16384) >> 15);
    if (q > 32767) q = 32767;
    if (q < -32767) q = -32767;
    return (int16_t)q;
}

uint32_t gbp_aresamp2_push(struct gbp_aresamp2 *r, int16_t in, int16_t *out)
{
    uint32_t n = 0u;
    r->hist[r->hpos] = in;
    r->hpos = (r->hpos + 1u) % GBP_ARESAMP2_TAPS;   /* hpos is now the OLDEST sample */
    r->in_count++;
    while (r->acc < GBP_ARESAMP2_L) {
        const int32_t *h = GBP_ARESAMP2_COEF[r->acc];
        int64_t sum = 0;
        uint32_t m;
        for (m = 0; m < GBP_ARESAMP2_TAPS; m++)
            sum += (int64_t)h[m] * (int64_t)r->hist[(r->hpos + m) % GBP_ARESAMP2_TAPS];
        out[n++] = q15_round2(sum);
        r->acc += GBP_ARESAMP2_M;
    }
    r->acc -= GBP_ARESAMP2_L;
    r->out_count += n;
    return n;
}
