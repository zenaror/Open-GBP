/*
 * gbp_atrace.c — Run A's read-only timing records (GitHub Issue #101, §V23). See gbp_atrace.h.
 */
#include "gbp_atrace.h"

#include <string.h>

#include "gbp_crc32.h"

void gbp_atrace_init(struct gbp_atrace *tr, const struct gbp_atrace_storage *s, uint32_t tb_hz)
{
    memset(tr, 0, sizeof *tr);
    tr->s = *s;
    tr->tb_hz = tb_hz;
}

static uint32_t log2_bin(uint64_t v)
{
    uint32_t b = 0u;
    while (v > 1u && b < GBP_ATRACE_HIST_BINS - 1u) {
        v >>= 1;
        b++;
    }
    return b;
}

void gbp_atrace_audio(struct gbp_atrace *tr, int16_t decoded, uint64_t t_done)
{
    uint64_t d;
    if (tr->a_n >= GBP_ATRACE_A_MAX) { tr->a_dropped++; return; }
    if (tr->a_n == 0u) {
        tr->a_first = t_done;
        d = 0u;
    } else {
        d = t_done - tr->a_last;
    }
    tr->s.a_decoded[tr->a_n] = decoded;
    if (d >= GBP_ATRACE_A_SAT) {
        tr->s.a_delta[tr->a_n] = (uint16_t)GBP_ATRACE_A_SAT;
        if (tr->a_sat_n < GBP_ATRACE_A_SAT_MAX) {
            tr->s.a_sat[tr->a_sat_n].index = tr->a_n;
            tr->s.a_sat[tr->a_sat_n].t = t_done;
            tr->a_sat_n++;
        } else {
            tr->a_sat_dropped++;
        }
    } else {
        tr->s.a_delta[tr->a_n] = (uint16_t)d;
    }
    tr->a_last = t_done;
    tr->a_n++;
}

void gbp_atrace_video(struct gbp_atrace *tr, int frame_start, uint64_t t_done)
{
    uint64_t d;
    uint16_t rec;
    if (tr->v_n >= GBP_ATRACE_V_MAX) { tr->v_dropped++; return; }
    if (tr->v_n == 0u) {
        tr->v_first = t_done;
        d = 0u;
    } else {
        d = t_done - tr->v_last;
    }
    if (d >= GBP_ATRACE_V_SAT) {
        rec = (uint16_t)GBP_ATRACE_V_SAT;
        if (tr->v_sat_n < GBP_ATRACE_V_SAT_MAX) {
            tr->s.v_sat[tr->v_sat_n].index = tr->v_n;
            tr->s.v_sat[tr->v_sat_n].t = t_done;
            tr->v_sat_n++;
        } else {
            tr->v_sat_dropped++;
        }
    } else {
        rec = (uint16_t)d;
    }
    if (frame_start) rec = (uint16_t)(rec | GBP_ATRACE_V_START);
    tr->s.v_rec[tr->v_n] = rec;
    tr->v_last = t_done;
    tr->v_n++;
}

struct gbp_atrace_cb *gbp_atrace_callback(struct gbp_atrace *tr, uint64_t entry, uint64_t exit_)
{
    struct gbp_atrace_cb *c;
    uint32_t n = tr->cb_n;
    if (n >= GBP_ATRACE_CB_MAX) { tr->cb_dropped++; return 0; }
    c = &tr->s.cb[n];
    c->entry = entry;
    c->dur = (uint32_t)(exit_ - entry);
    c->rec = 0u;
    tr->cb_n = n + 1u;
    return c;
}

struct gbp_atrace_step *gbp_atrace_step(struct gbp_atrace *tr, enum gbp_atrace_kind kind, uint64_t start, uint64_t end)
{
    return gbp_atrace_step_tagged(tr, kind, start, end, 0u);
}

struct gbp_atrace_step *gbp_atrace_step_tagged(struct gbp_atrace *tr, enum gbp_atrace_kind kind, uint64_t start,
                                               uint64_t end, uint8_t tag)
{
    struct gbp_atrace_step *st;
    uint64_t dur = end - start;
    if ((unsigned)kind < 4u) {
        tr->calls[kind]++;
        tr->hist[kind][log2_bin(dur)]++;
    }
    /* Issue #105 (§V24.4): in a sampled cycle, every step, with no floor */
    if (tr->sample_every && tr->s.sample && tr->cb_n % tr->sample_every == 1u) {
        if (!tr->sample_armed) {
            tr->sample_armed = 1;
            tr->sample_base = start;
        }
        if (tr->sample_n < GBP_ATRACE_SAMPLE_MAX) {
            struct gbp_atrace_step *sp = &tr->s.sample[tr->sample_n++];
            sp->start_rel = (uint32_t)(start - tr->sample_base);
            sp->dur = (uint32_t)dur;
            sp->rec = 0u;
            sp->kind = (uint8_t)kind;
            sp->tag = tag;
        } else {
            tr->sample_dropped++;
        }
    }
    if (kind != GBP_ATRACE_FLUSH_QUEUE && dur < GBP_ATRACE_STEP_FLOOR) return 0;
    if (!tr->step_armed) {
        tr->step_armed = 1;
        tr->step_base = start;
    }
    if (tr->step_n >= GBP_ATRACE_STEP_MAX) { tr->step_dropped++; return 0; }
    st = &tr->s.step[tr->step_n++];
    st->start_rel = (uint32_t)(start - tr->step_base);
    st->dur = (uint32_t)dur;
    st->rec = 0u;
    st->kind = (uint8_t)kind;
    st->tag = tag;
    return st;
}

void gbp_atrace_step_rec(struct gbp_atrace *tr, struct gbp_atrace_step *st, uint64_t end, uint64_t rec_end)
{
    const uint64_t r = rec_end - end;
    if (!st) {                                     /* not kept: its histogram write is a recorder cost */
        gbp_atrace_cost(tr, (uint32_t)(r > 0xFFFFFFFFu ? 0xFFFFFFFFu : r));
        return;
    }
    st->rec = (uint16_t)(r > 0xFFFFu ? 0xFFFFu : r);
}

void gbp_atrace_cost(struct gbp_atrace *tr, uint32_t ticks)
{
    uint32_t c = tr->cb_n;                         /* 0: before the first callback */
    if (c >= GBP_ATRACE_CYCLES_MAX) c = GBP_ATRACE_CYCLES_MAX - 1u;
    tr->s.cycles[c] += ticks;
    if (c + 1u > tr->cycles_n) tr->cycles_n = c + 1u;
    if (ticks > tr->cost_max) tr->cost_max = ticks;
}

/* ---- the sidecar ------------------------------------------------------------ */

struct emitter {
    gbp_atrace_put put;
    void *ctx;
    uint8_t *stage;
    uint32_t cap, fill, total;
    uint32_t crc;
    int failed;
};

static void flush(struct emitter *e)
{
    if (e->fill && !e->failed) {
        if (e->put(e->ctx, e->stage, e->fill) != 0) e->failed = 1;
    }
    e->fill = 0u;
}

static void put_bytes(struct emitter *e, const uint8_t *b, uint32_t n)
{
    uint32_t i;
    e->crc = gbp_crc32_update(e->crc, b, n);
    for (i = 0; i < n; i++) {
        if (e->fill == e->cap) flush(e);
        e->stage[e->fill++] = b[i];
    }
    e->total += n;
}

static void be16(struct emitter *e, uint16_t v)
{
    uint8_t b[2];
    b[0] = (uint8_t)(v >> 8);
    b[1] = (uint8_t)v;
    put_bytes(e, b, 2u);
}

static void be32(struct emitter *e, uint32_t v)
{
    uint8_t b[4];
    b[0] = (uint8_t)(v >> 24);
    b[1] = (uint8_t)(v >> 16);
    b[2] = (uint8_t)(v >> 8);
    b[3] = (uint8_t)v;
    put_bytes(e, b, 4u);
}

static void be64(struct emitter *e, uint64_t v)
{
    be32(e, (uint32_t)(v >> 32));
    be32(e, (uint32_t)v);
}

/*
 * THE FILE (big-endian):
 *   0x00  8    magic "OGBPTRC1"
 *   0x08  u32  version = 1
 *   0x0C  u32  tb_hz
 *   0x10  u32  a_n, a_sat_n, v_n, v_sat_n, cb_n, step_n, cycles_n      (7 words)
 *   0x2C  u32  a_dropped, a_sat_dropped, v_dropped, v_sat_dropped, cb_dropped, step_dropped (6)
 *   0x44  u64  a_first, v_first, step_base
 *   0x5C  u32  step_floor, cost_max
 *   0x64  u32  calls[4], then hist[4][32]                              (132 words)
 *   ....  s16 x a_n              a_decoded
 *   ....  u16 x a_n              a_delta
 *   ....  (u32 index, u64 t) x a_sat_n
 *   ....  u16 x v_n              v_rec
 *   ....  (u32 index, u64 t) x v_sat_n
 *   ....  (u64 entry, u32 dur, u32 rec) x cb_n
 *   ....  (u32 start_rel, u32 dur, u16 rec, u8 kind, u8 0) x step_n
 *   ....  u32 x cycles_n         the recorder's other writes, per AI callback cycle
 *   VERSION 2 ONLY (sample_every != 0; Issue #105): each step's spare byte is its tag, and
 *   ....  u32  sample_every, sample_n, sample_dropped; u64 sample_base
 *   ....  (u32 start_rel, u32 dur, u16 0, u8 kind, u8 tag) x sample_n
 *   ....  u32                    CRC-32 of every byte before it
 */
uint32_t gbp_atrace_emit(const struct gbp_atrace *tr, gbp_atrace_put put, void *ctx, uint8_t *stage, uint32_t cap)
{
    struct emitter e;
    uint32_t i, k, cb_n = tr->cb_n;
    static const uint8_t magic[8] = { 'O', 'G', 'B', 'P', 'T', 'R', 'C', '1' };
    if (!put || !stage || cap == 0u) return 0u;
    memset(&e, 0, sizeof e);
    e.put = put;
    e.ctx = ctx;
    e.stage = stage;
    e.cap = cap;
    e.crc = gbp_crc32_init();
    put_bytes(&e, magic, 8u);
    be32(&e, tr->sample_every ? 2u : 1u);
    be32(&e, tr->tb_hz);
    be32(&e, tr->a_n); be32(&e, tr->a_sat_n); be32(&e, tr->v_n); be32(&e, tr->v_sat_n);
    be32(&e, cb_n); be32(&e, tr->step_n); be32(&e, tr->cycles_n);
    be32(&e, tr->a_dropped); be32(&e, tr->a_sat_dropped); be32(&e, tr->v_dropped); be32(&e, tr->v_sat_dropped);
    be32(&e, tr->cb_dropped); be32(&e, tr->step_dropped);
    be64(&e, tr->a_first); be64(&e, tr->v_first); be64(&e, tr->step_base);
    be32(&e, GBP_ATRACE_STEP_FLOOR); be32(&e, tr->cost_max);
    for (k = 0; k < 4u; k++) be32(&e, tr->calls[k]);
    for (k = 0; k < 4u; k++)
        for (i = 0; i < GBP_ATRACE_HIST_BINS; i++) be32(&e, tr->hist[k][i]);
    for (i = 0; i < tr->a_n; i++) be16(&e, (uint16_t)tr->s.a_decoded[i]);
    for (i = 0; i < tr->a_n; i++) be16(&e, tr->s.a_delta[i]);
    for (i = 0; i < tr->a_sat_n; i++) { be32(&e, tr->s.a_sat[i].index); be64(&e, tr->s.a_sat[i].t); }
    for (i = 0; i < tr->v_n; i++) be16(&e, tr->s.v_rec[i]);
    for (i = 0; i < tr->v_sat_n; i++) { be32(&e, tr->s.v_sat[i].index); be64(&e, tr->s.v_sat[i].t); }
    for (i = 0; i < cb_n; i++) { be64(&e, tr->s.cb[i].entry); be32(&e, tr->s.cb[i].dur); be32(&e, tr->s.cb[i].rec); }
    for (i = 0; i < tr->step_n; i++) {
        uint8_t kz[2];
        be32(&e, tr->s.step[i].start_rel);
        be32(&e, tr->s.step[i].dur);
        be16(&e, tr->s.step[i].rec);
        kz[0] = tr->s.step[i].kind;
        kz[1] = tr->sample_every ? tr->s.step[i].tag : 0u;
        put_bytes(&e, kz, 2u);
    }
    for (i = 0; i < tr->cycles_n; i++) be32(&e, tr->s.cycles[i]);
    if (tr->sample_every) {
        be32(&e, tr->sample_every); be32(&e, tr->sample_n); be32(&e, tr->sample_dropped);
        be64(&e, tr->sample_base);
        for (i = 0; i < tr->sample_n; i++) {
            uint8_t kz[2];
            be32(&e, tr->s.sample[i].start_rel);
            be32(&e, tr->s.sample[i].dur);
            be16(&e, 0u);
            kz[0] = tr->s.sample[i].kind;
            kz[1] = tr->s.sample[i].tag;
            put_bytes(&e, kz, 2u);
        }
    }
    {
        uint32_t crc = gbp_crc32_final(e.crc);
        uint8_t b[4];
        b[0] = (uint8_t)(crc >> 24);
        b[1] = (uint8_t)(crc >> 16);
        b[2] = (uint8_t)(crc >> 8);
        b[3] = (uint8_t)crc;
        for (i = 0; i < 4u; i++) {
            if (e.fill == e.cap) flush(&e);
            e.stage[e.fill++] = b[i];
        }
        e.total += 4u;
    }
    flush(&e);
    return e.failed ? 0u : e.total;
}
