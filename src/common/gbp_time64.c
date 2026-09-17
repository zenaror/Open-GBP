#include "gbp_time64.h"

int gbp_time64_compose(uint32_t tbu1, uint32_t tbl, uint32_t tbu2, uint64_t *out)
{
    if (tbu1 != tbu2) return 0;
    if (out) *out = ((uint64_t)tbu1 << 32) | (uint64_t)tbl;
    return 1;
}

uint64_t gbp_time64_read(gbp_time64_spr_fn f, void *ctx, unsigned *retries)
{
    uint64_t v = 0;
    unsigned n = 0;
    if (retries) *retries = 0;
    if (!f) return 0;
    for (;;) {
        uint32_t tbu1 = f(ctx, GBP_TIME64_TBU);
        uint32_t tbl = f(ctx, GBP_TIME64_TBL);
        uint32_t tbu2 = f(ctx, GBP_TIME64_TBU);
        if (gbp_time64_compose(tbu1, tbl, tbu2, &v)) break;
        n++;
        if (n >= GBP_TIME64_MAX_RETRIES) {
            /* A reader whose high word never settles is broken, not wrapping:
             * take the last sample's high word with its own low word so the
             * result stays a real reading, and report the retries. */
            v = ((uint64_t)tbu2 << 32) | (uint64_t)tbl;
            break;
        }
    }
    if (retries) *retries = n;
    return v;
}

uint64_t gbp_time64_make(uint32_t hi, uint32_t lo)
{
    return ((uint64_t)hi << 32) | (uint64_t)lo;
}

uint32_t gbp_time64_hi(uint64_t v)
{
    return (uint32_t)(v >> 32);
}

uint32_t gbp_time64_lo(uint64_t v)
{
    return (uint32_t)(v & 0xFFFFFFFFu);
}

uint64_t gbp_time64_delta(uint64_t earlier, uint64_t later)
{
    if (later <= earlier) return 0u;
    return later - earlier;
}

int gbp_time64_reached(uint64_t start, uint64_t span, uint64_t now)
{
    if (now < start) return 0;
    return (now - start) >= span;
}

uint64_t gbp_time64_from_seconds(uint32_t tb_hz, uint32_t seconds)
{
    return (uint64_t)tb_hz * (uint64_t)seconds;
}

uint64_t gbp_time64_from_ms(uint32_t tb_hz, uint32_t ms)
{
    return ((uint64_t)tb_hz * (uint64_t)ms) / 1000u;
}

uint32_t gbp_time64_to_ms(uint32_t tb_hz, uint64_t ticks)
{
    uint64_t ms;
    if (!tb_hz) return 0u;
    ms = (ticks / (uint64_t)tb_hz) * 1000u + ((ticks % (uint64_t)tb_hz) * 1000u) / (uint64_t)tb_hz;
    if (ms > 0xFFFFFFFFu) return 0xFFFFFFFFu;
    return (uint32_t)ms;
}

uint32_t gbp_time64_seconds(uint32_t tb_hz, uint64_t ticks)
{
    uint64_t s;
    if (!tb_hz) return 0u;
    s = ticks / (uint64_t)tb_hz;
    if (s > 0xFFFFFFFFu) return 0xFFFFFFFFu;
    return (uint32_t)s;
}

uint32_t gbp_time64_millis_part(uint32_t tb_hz, uint64_t ticks)
{
    if (!tb_hz) return 0u;
    return (uint32_t)(((ticks % (uint64_t)tb_hz) * 1000u) / (uint64_t)tb_hz);
}
