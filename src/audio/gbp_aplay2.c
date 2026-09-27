/*
 * gbp_aplay2 — see gbp_aplay2.h. The correction/sub-block decision logic below is #126's own
 * produce_impl, unchanged (same gate, same per-sub-block decision, same corr_forgone accounting,
 * GBP-HW-349). Ported in by Issue #127: the destination is now the AI chunk pool + READY queue,
 * exactly as gbp_aplay.c's own produce_impl, put_frames, queue, drop_front, process, irq_handoff,
 * arm_l2 and sidecar routines -- read here at this path's own PUSHES/AHEAD/K_DEFAULT/constants.
 */
#include "gbp_aplay2.h"

#include <string.h>

#include "gbp_aresamp2_coef.h"       /* GBP_ARESAMP2_M, for the chunk-alignment static assert below */

/* ---- CRC-32 (IEEE 802.3 / zlib) -- the SAME table gbp_aplay.c builds, kept local since the two
 * modules never link together in one image (a NEW path, not a moved default) ------------------- */
static uint32_t crc_table[256];
static int32_t crc_ready;

static void crc_build(void)
{
    uint32_t i, k, c;
    for (i = 0u; i < 256u; i++) {
        c = i;
        for (k = 0u; k < 8u; k++) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
        crc_table[i] = c;
    }
    crc_ready = 1;
}

uint32_t gbp_aplay2_crc_update(uint32_t state, const uint8_t *data, size_t n)
{
    size_t i;
    if (!crc_ready) crc_build();
    for (i = 0; i < n; i++) state = crc_table[(state ^ data[i]) & 0xFFu] ^ (state >> 8);
    return state;
}

/* ---- the buffers ------------------------------------------------------------- */
static uint8_t *chunk2(struct gbp_aplay2 *p, int buf)
{
    return p->pool + (size_t)buf * GBP_APLAY2_CHUNK_BYTES;
}

void gbp_aplay2_init(struct gbp_aplay2 *p, uint8_t *pool, const uint8_t *silence, int16_t *keep,
                     struct gbp_aplay2_event *events)
{
    if (!p) return;
    memset(p, 0, sizeof *p);
    gbp_aresamp2_init(&p->rs);
    p->pool = pool;
    p->silence = silence;
    p->keep = keep;
    p->events = events;
    p->cur = -1;
    p->last_handed[0] = p->last_handed[1] = -1;
    p->target = GBP_APLAY2_TARGET;
    p->corr_per_chunk = GBP_APLAY2_K_DEFAULT;          /* this path's fixed default (GBP-HW-349) */
    if (!crc_ready) crc_build();
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
_Static_assert(GBP_APLAY2_STEP_PUSHES > 0u && GBP_APLAY2_STEP_PUSHES <= GBP_APLAY2_PUSHES,
               "the default step must itself be a legal chunk step");

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

void gbp_aplay2_mute(struct gbp_aplay2 *p, uint32_t chunks)
{
    if (!p) return;
    p->mute = chunks;                                   /* one 32-bit store; the callback decrements */
}

int gbp_aplay2_discard_chunk(struct gbp_aplay2 *p, int buf)
{
    if (!p || buf < 0 || buf >= (int)GBP_APLAY2_POOL) return 0;
    if (p->state[buf] != GBP_APLAY2_FILLING || buf == p->cur) return 0;
    p->state[buf] = GBP_APLAY2_FREE;
    p->discarded_chunks++;
    return 1;
}

static void l2_event2(struct gbp_aplay2 *p, uint32_t kind, uint32_t index)
{
    if (p->l2.n_events >= GBP_APLAY2_EVENTS_CAP) {
        p->l2.overflowed = 1u;
        return;
    }
    p->events[p->l2.n_events].kind = kind;
    p->events[p->l2.n_events].index = index;
    p->l2.n_events++;
}

static void put_frames2(struct gbp_aplay2 *p, const int16_t *y, uint32_t n)
{
    uint8_t *o = chunk2(p, p->cur) + (size_t)p->cur_frames * 4u;
    uint32_t k;
    for (k = 0; k < n; k++) {
        const uint16_t v = (uint16_t)y[k];
        o[4u * k + 0u] = (uint8_t)(v >> 8);
        o[4u * k + 1u] = (uint8_t)(v & 0xFFu);
        o[4u * k + 2u] = (uint8_t)(v >> 8);
        o[4u * k + 3u] = (uint8_t)(v & 0xFFu);
    }
    p->cur_frames += n;
}

static void push_one2(struct gbp_aplay2 *p, int16_t x)
{
    int16_t y[GBP_ARESAMP2_MAX_OUT];
    const uint32_t n = gbp_aresamp2_push(&p->rs, x, y);
    put_frames2(p, y, n);
    p->cur_pushes++;
}

static int take2(struct gbp_adec2 *d, struct gbp_aplay2 *p, int16_t *x)
{
    if (!gbp_adec2_pop(d, x)) return 0;
    if (p->l2.keeping) {
        if (p->l2.n_keep < GBP_APLAY2_KEEP_CAP) p->keep[p->l2.n_keep] = *x;
        else p->l2.overflowed = 1u;
        p->l2.n_keep++;
    }
    return 1;
}

static int produce_impl2(struct gbp_aplay2 *p, struct gbp_adec2 *d, int uncorrected)
{
    uint32_t step = 0u;
    if (!p || !d) return -1;
    if (p->cur < 0) {
        int32_t i, found = -1;
        /* a chunk is only started when the ring can finish it: PUSHES pushes, one more for a
         * DROP (gbp_aplay.c's third review; GBP-HW-349 confirms the argument holds at this
         * path's k = 16 too, #126). */
        if (d->count < GBP_APLAY2_PUSHES + 1u) {
            p->starved_steps++;
            if (uncorrected || gbp_aplay2_ready(p) < GBP_APLAY2_AHEAD) {
                for (i = 0; i < (int)GBP_APLAY2_POOL; i++)
                    if (p->state[i] == GBP_APLAY2_FREE) { p->ring_gated++; break; }
            }
            return -1;
        }
        if (!uncorrected && gbp_aplay2_ready(p) >= GBP_APLAY2_AHEAD) return -1;
        for (i = 0; i < (int)GBP_APLAY2_POOL; i++)
            if (p->state[i] == GBP_APLAY2_FREE) { found = i; break; }
        if (found < 0) return -1;
        p->cur = found;
        p->state[found] = GBP_APLAY2_FILLING;
        p->seq[found] = p->produced;
        p->cur_frames = 0u;
        p->cur_pushes = 0u;
        p->cur_step = p->step_pushes ? p->step_pushes(p->step_pushes_user, p->produced) : GBP_APLAY2_STEP_PUSHES;
        if (p->cur_step == 0u || p->cur_step > GBP_APLAY2_PUSHES) p->cur_step = GBP_APLAY2_STEP_PUSHES;
        p->cur_corr = 0u;
        p->cur_corr_done = 1u;
        /* before playback a chunk takes at most one correction: the ring filling up is not drift */
        p->cur_k = p->playing ? p->corr_per_chunk : 1u;
        p->cur_s0 = d->count;
        p->cur_target = p->target;
        p->cur_sub = 0u;
        p->cur_taken = 0u;
        p->cur_uncorrected = (uint8_t)(uncorrected ? 1u : 0u);
        /* L2: a chunk boundary, acc 0 -- the kept state is the resampler's here */
        if (p->l2.armed && !p->l2.keeping && !p->l2.done) {
            p->l2.keeping = 1u;
            p->l2.first_seq = p->produced;
            memcpy(p->l2.hist, p->rs.hist, sizeof p->l2.hist);
            p->l2.hpos = p->rs.hpos;
            p->l2.acc = p->rs.acc;
        }
    }
    while (p->cur_pushes < GBP_APLAY2_PUSHES && step < p->cur_step) {
        int16_t x;
        /* a sub-block's decision, at its FIRST push, made by a corrected call -- #126's logic,
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
        if (!take2(d, p, &x)) { p->starved_steps++; return -1; }   /* cannot happen: checked at the start */
        p->cur_taken++;
        if (p->cur_corr == GBP_APLAY2_EV_DROP && !p->cur_corr_done) {
            p->cur_corr_done = 1u;
            p->drop++;
            if (p->l2.keeping) l2_event2(p, GBP_APLAY2_EV_DROP, p->l2.n_keep - 1u);
            continue;                                          /* the sample is not pushed */
        }
        push_one2(p, x);
        step++;
        if (p->cur_corr == GBP_APLAY2_EV_DUP && !p->cur_corr_done && p->cur_pushes < GBP_APLAY2_PUSHES) {
            p->cur_corr_done = 1u;
            p->dup++;
            if (p->l2.keeping) l2_event2(p, GBP_APLAY2_EV_DUP, p->l2.n_keep - 1u);
            push_one2(p, x);                                    /* pushed twice */
            step++;
        }
    }
    if (p->cur_pushes < GBP_APLAY2_PUSHES) return -1;
    {
        const int32_t done = p->cur;
        if (!p->cur_uncorrected) p->corr_forgone += p->cur_k - p->cur_sub;   /* the rest, undecided */
        p->cur = -1;
        p->produced++;
        if (p->l2.keeping) {
            p->l2.kept_chunks++;
            if (p->l2.kept_chunks >= GBP_APLAY2_L2_CHUNKS) {
                p->l2.keeping = 0u;
                p->l2.armed = 0u;
            }
        }
        return done;
    }
}

int gbp_aplay2_produce(struct gbp_aplay2 *p, struct gbp_adec2 *d)
{
    return produce_impl2(p, d, 0);
}

int gbp_aplay2_produce_ex(struct gbp_aplay2 *p, struct gbp_adec2 *d, int uncorrected)
{
    return produce_impl2(p, d, uncorrected);
}

int gbp_aplay2_produce_uncorrected(struct gbp_aplay2 *p, struct gbp_adec2 *d)
{
    return produce_impl2(p, d, 1);
}

int gbp_aplay2_produce_discard(struct gbp_aplay2 *p, struct gbp_adec2 *d)
{
    int32_t b = produce_impl2(p, d, 1);
    if (b >= 0 && !gbp_aplay2_discard_chunk(p, b)) return -1;   /* cannot happen: just completed, not current */
    return b;
}

int gbp_aplay2_drop_front(struct gbp_aplay2 *p)
{
    uint32_t h;
    int32_t b;
    if (!p || p->mute == 0u || p->rq_head == p->rq_tail) return -1;
    h = p->rq_head;
    b = (int)p->rq[h % GBP_APLAY2_POOL];
    p->state[b] = GBP_APLAY2_FREE;
    p->rq_head = h + 1u;
    p->dropped_front++;
    return b;
}

uint32_t gbp_aplay2_ready(const struct gbp_aplay2 *p)
{
    return p ? (uint32_t)(p->rq_tail - p->rq_head) : 0u;
}

void gbp_aplay2_queue(struct gbp_aplay2 *p, int buf)
{
    if (!p || buf < 0 || buf >= (int)GBP_APLAY2_POOL) return;
    p->state[buf] = GBP_APLAY2_READY;
    p->rq[p->rq_tail % GBP_APLAY2_POOL] = (uint8_t)buf;
    p->rq_tail = p->rq_tail + 1u;                       /* published after the entry */
}

void gbp_aplay2_arm_l2(struct gbp_aplay2 *p)
{
    if (p && !p->l2.done && !p->l2.keeping) p->l2.armed = 1u;
}

/* The callback: interrupt context (on the frozen path). Host tests call it directly. */
const uint8_t *gbp_aplay2_irq_handoff(struct gbp_aplay2 *p, uint64_t t)
{
    int32_t buf = GBP_APLAY2_HL_SILENCE;
    if (p->measuring) {
        if (p->cb_count == 0u) p->cb_t_first = t;
        p->cb_t_last = t;
        p->cb_count = p->cb_count + 1u;
    }
    if (p->mute > 0u) {
        p->mute = p->mute - 1u;
        p->mute_handed = p->mute_handed + 1u;
        buf = GBP_APLAY2_HL_MUTE;
    } else if (p->rq_head != p->rq_tail) {
        buf = (int)p->rq[p->rq_head % GBP_APLAY2_POOL];
        p->rq_head = p->rq_head + 1u;
    } else {
        p->silences = p->silences + 1u;
        if (p->playing) p->underruns = p->underruns + 1u;
    }
    if (p->hl_tail - p->hl_head < GBP_APLAY2_LOG) {
        p->hl[p->hl_tail % GBP_APLAY2_LOG] = (int8_t)buf;
        p->hl_tail = p->hl_tail + 1u;
    } else {
        p->log_overflow++;
    }
    p->handed = p->handed + 1u;
    return buf >= 0 ? p->pool + (size_t)buf * GBP_APLAY2_CHUNK_BYTES : p->silence;
}

void gbp_aplay2_process(struct gbp_aplay2 *p)
{
    if (!p) return;
    while (p->hl_head != p->hl_tail) {
        const int32_t buf = (int32_t)p->hl[p->hl_head % GBP_APLAY2_LOG];
        p->hl_head = p->hl_head + 1u;
        if (buf >= 0 && !p->l2.handing && !p->l2.done && (p->l2.keeping || p->l2.kept_chunks) &&
            p->seq[buf] == p->l2.first_seq && p->l2.kept_chunks > 0u) {
            p->l2.handing = 1u;
            p->l2.crc = 0xFFFFFFFFu;
        }
        if (p->l2.handing && buf != GBP_APLAY2_HL_MUTE) {
            if (buf < 0) {
                l2_event2(p, GBP_APLAY2_EV_SILENCE, p->l2.window_chunks);
                p->l2.silence_chunks++;
                p->l2.crc = gbp_aplay2_crc_update(p->l2.crc, p->silence, GBP_APLAY2_CHUNK_BYTES);
            } else {
                p->l2.crc = gbp_aplay2_crc_update(p->l2.crc, chunk2(p, buf), GBP_APLAY2_CHUNK_BYTES);
            }
            p->l2.window_chunks++;
            if (buf >= 0 && p->seq[buf] == p->l2.first_seq + GBP_APLAY2_L2_CHUNKS - 1u) {
                p->l2.handing = 0u;
                p->l2.done = 1u;
            }
        }
        if (buf >= 0) p->state[buf] = GBP_APLAY2_HANDED;
        if (p->last_handed[0] >= 0) p->state[p->last_handed[0]] = GBP_APLAY2_FREE;
        p->last_handed[0] = p->last_handed[1];
        p->last_handed[1] = buf;
    }
}

/* ---- the OGBPL2S1 sidecar (tools/v22accept.py's frozen format) ------------------------------- */
static uint8_t *be32_2(uint8_t *o, uint32_t v)
{
    o[0] = (uint8_t)(v >> 24); o[1] = (uint8_t)(v >> 16); o[2] = (uint8_t)(v >> 8); o[3] = (uint8_t)v;
    return o + 4;
}

static uint8_t *be16_2(uint8_t *o, int16_t s)
{
    const uint16_t v = (uint16_t)s;
    o[0] = (uint8_t)(v >> 8); o[1] = (uint8_t)(v & 0xFFu);
    return o + 2;
}

size_t gbp_aplay2_sidecar_size(const struct gbp_aplay2 *p)
{
    uint32_t keep;
    if (!p) return 0u;
    keep = p->l2.n_keep < GBP_APLAY2_KEEP_CAP ? p->l2.n_keep : GBP_APLAY2_KEEP_CAP;
    return 0x48u + 8u * (size_t)p->l2.n_events + 2u * (size_t)keep + 4u;
}

size_t gbp_aplay2_sidecar(const struct gbp_aplay2 *p, uint8_t *out, size_t cap)
{
    static const uint8_t magic[8] = { 'O', 'G', 'B', 'P', 'L', '2', 'S', '1' };
    const size_t need = gbp_aplay2_sidecar_size(p);
    uint8_t *o = out;
    uint32_t k, keep;
    if (!p || !out || cap < need) return 0u;
    keep = p->l2.n_keep < GBP_APLAY2_KEEP_CAP ? p->l2.n_keep : GBP_APLAY2_KEEP_CAP;
    memcpy(o, magic, 8u); o += 8;
    o = be32_2(o, 1u);
    o = be32_2(o, GBP_APLAY2_FRAMES);
    o = be32_2(o, p->l2.window_chunks);
    o = be32_2(o, p->l2.crc ^ 0xFFFFFFFFu);
    o = be32_2(o, p->l2.acc);
    o = be32_2(o, p->l2.hpos);
    for (k = 0; k < 16u; k++) o = be16_2(o, p->l2.hist[k]);
    o = be32_2(o, keep);
    o = be32_2(o, p->l2.n_events);
    for (k = 0; k < p->l2.n_events; k++) {
        o = be32_2(o, p->events[k].kind);
        o = be32_2(o, p->events[k].index);
    }
    for (k = 0; k < keep; k++) o = be16_2(o, p->keep[k]);
    o = be32_2(o, gbp_aplay2_crc_update(0xFFFFFFFFu, out, (size_t)(o - out)) ^ 0xFFFFFFFFu);
    return (size_t)(o - out);
}
