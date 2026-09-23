/*
 * gbp_aresamp — see gbp_aresamp.h.
 */
#include "gbp_aresamp.h"

#include "gbp_aresamp_coef.h"

void gbp_aresamp_init(struct gbp_aresamp *r)
{
    uint32_t i;
    for (i = 0; i < GBP_ARESAMP_TAPS; i++)
        r->hist[i] = 0;
    r->hpos = 0u;
    r->acc = 0u;
    r->in_count = 0u;
    r->out_count = 0u;
}

/* Q15 -> integer, halves away from zero, clipped to int16. Written out rather
 * than left to a right shift of a negative number, whose meaning C leaves to
 * the implementation. */
static int16_t q15_round(int64_t v)
{
    int64_t q = (v >= 0) ? ((v + 16384) >> 15) : -(((-v) + 16384) >> 15);
    if (q > 32767) q = 32767;
    if (q < -32767) q = -32767;
    return (int16_t)q;
}

uint32_t gbp_aresamp_push(struct gbp_aresamp *r, int16_t in, int16_t *out)
{
    uint32_t n = 0u;
    r->hist[r->hpos] = in;
    r->hpos = (r->hpos + 1u) % GBP_ARESAMP_TAPS;   /* hpos is now the OLDEST sample */
    r->in_count++;
    while (r->acc < GBP_ARESAMP_L) {
        const int32_t *h = GBP_ARESAMP_COEF[r->acc];
        int64_t sum = 0;
        uint32_t m;
        /* tap m multiplies the input 15 - m samples back, i.e. hist[hpos + m] */
        for (m = 0; m < GBP_ARESAMP_TAPS; m++)
            sum += (int64_t)h[m] * (int64_t)r->hist[(r->hpos + m) % GBP_ARESAMP_TAPS];
        out[n++] = q15_round(sum);
        r->acc += GBP_ARESAMP_M;
    }
    r->acc -= GBP_ARESAMP_L;
    r->out_count += n;
    return n;
}
