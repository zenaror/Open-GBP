/*
 * gbp_aplay — see gbp_aplay.h.
 */
#include "gbp_aplay.h"

#include <string.h>

/* ---- CRC-32 (IEEE 802.3 / zlib), one table built from the polynomial ---------- */
static uint32_t crc_table[256];
static int crc_ready;

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

uint32_t gbp_aplay_crc_update(uint32_t state, const uint8_t *data, size_t n)
{
    size_t i;
    if (!crc_ready) crc_build();
    for (i = 0; i < n; i++) state = crc_table[(state ^ data[i]) & 0xFFu] ^ (state >> 8);
    return state;
}

/* ---- the buffers ------------------------------------------------------------- */
static uint8_t *chunk(struct gbp_aplay *p, int buf)
{
    return p->pool + (size_t)buf * GBP_APLAY_CHUNK_BYTES;
}

void gbp_aplay_init(struct gbp_aplay *p, uint8_t *pool, const uint8_t *silence, int16_t *keep,
                    struct gbp_aplay_event *events)
{
    if (!p) return;
    memset(p, 0, sizeof *p);
    gbp_aresamp_init(&p->rs);
    p->pool = pool;
    p->silence = silence;
    p->keep = keep;
    p->events = events;
    p->cur = -1;
    p->last_handed[0] = p->last_handed[1] = -1;
    p->target = GBP_APLAY_TARGET;                       /* Issue #117: the field's default is the macro */
    p->corr_per_chunk = 1u;                             /* Issue #123: one a chunk, every earlier build's */
    if (!crc_ready) crc_build();
}

/* ---- Issue #123: corrections per chunk --------------------------------------------- */
int gbp_aplay_set_corrections(struct gbp_aplay *p, uint32_t k)
{
    /* a DUP is two pushes, so a sub-block must hold two: k <= PUSHES / 2 */
    if (!p || k == 0u || k > GBP_APLAY_PUSHES / 2u || GBP_APLAY_PUSHES % k != 0u) return -1;
    p->corr_per_chunk = k;                              /* read at each chunk's start */
    return 0;
}

/* ---- Issue #121: the cushion in time, checked where it is compiled ------------------ */
_Static_assert(((uint64_t)GBP_ADEC_RATE * GBP_APLAY_CUSHION_US) % 1000000u == 0u,
               "the cushion must be a whole number of decoded samples at the decoder's rate");
_Static_assert(GBP_APLAY_TARGET >= GBP_APLAY_TARGET_MIN && GBP_APLAY_TARGET <= GBP_APLAY_TARGET_MAX,
               "the default cushion must be a target gbp_aplay_set_target() would accept unclamped");

/* ---- Issue #117: the runtime target, the mute, the discard (pump slot) ---------- */
void gbp_aplay_set_target(struct gbp_aplay *p, uint32_t target)
{
    if (!p) return;
    if (target < GBP_APLAY_TARGET_MIN) target = GBP_APLAY_TARGET_MIN;
    if (target > GBP_APLAY_TARGET_MAX) target = GBP_APLAY_TARGET_MAX;
    p->target = target;
}

void gbp_aplay_mute(struct gbp_aplay *p, uint32_t chunks)
{
    if (!p) return;
    p->mute = chunks;                                   /* one 32-bit store; the callback decrements */
}

int gbp_aplay_discard_chunk(struct gbp_aplay *p, int buf)
{
    if (!p || buf < 0 || buf >= (int)GBP_APLAY_POOL) return 0;
    /* a completed chunk is FILLING and no longer current; anything else is not ours to free */
    if (p->state[buf] != GBP_APLAY_FILLING || buf == p->cur) return 0;
    p->state[buf] = GBP_APLAY_FREE;
    p->discarded_chunks++;
    return 1;
}

static void l2_event(struct gbp_aplay *p, uint32_t kind, uint32_t index)
{
    if (p->l2.n_events >= GBP_APLAY_EVENTS_CAP) {
        p->l2.overflowed = 1u;                      /* the record is then incomplete, and says so */
        return;
    }
    p->events[p->l2.n_events].kind = kind;
    p->events[p->l2.n_events].index = index;
    p->l2.n_events++;
}

static void put_frames(struct gbp_aplay *p, const int16_t *y, uint32_t n)
{
    uint8_t *o = chunk(p, p->cur) + (size_t)p->cur_frames * 4u;
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

static void push_one(struct gbp_aplay *p, int16_t x)
{
    int16_t y[GBP_ARESAMP_MAX_OUT];
    const uint32_t n = gbp_aresamp_push(&p->rs, x, y);
    put_frames(p, y, n);
    p->cur_pushes++;
}

static int take(struct gbp_aplay *p, struct gbp_adec *d, int16_t *x)
{
    if (!gbp_adec_pop(d, x)) return 0;
    if (p->l2.keeping) {
        if (p->l2.n_keep < GBP_APLAY_KEEP_CAP) p->keep[p->l2.n_keep] = *x;
        else p->l2.overflowed = 1u;
        p->l2.n_keep++;
    }
    return 1;
}

static int produce_impl(struct gbp_aplay *p, struct gbp_adec *d, int uncorrected)
{
    uint32_t step = 0u;
    if (!p || !d) return -1;
    if (p->cur < 0) {
        int i, found = -1;
        /* a chunk is only started when the ring can finish it: 128 pushes, one more for a DROP. Issue #123: k
         * corrections a chunk need no more. Its decisions stop DROPping at the band's upper edge, so a chunk
         * started at s0 takes at most 128 + (s0 - target - BAND) samples, which s0 holds because target + BAND
         * >= 128; below the edge it takes at most 128. A gate of PUSHES + k sat at or above the band for large k
         * and, under a batched feed, made every chunk start over the edge and DROP (the third review) */
        if (d->count < GBP_APLAY_PUSHES + 1u) {
            p->starved_steps++;                         /* every such step, the wait after a chunk included */
            /* Issue #117 (§V27.14): the steps where a chunk was WANTED -- the queue short of AHEAD (or an
             * uncorrected transition chunk) and a free buffer to put it in -- and the ring could not give
             * it. starved_steps also counts the benign wait after every chunk while READY is full, which
             * made it large at every depth <= 224 whether the correction held or not (review round 3) */
            if (uncorrected || gbp_aplay_ready(p) < GBP_APLAY_AHEAD) {
                for (i = 0; i < (int)GBP_APLAY_POOL; i++)
                    if (p->state[i] == GBP_APLAY_FREE) { p->ring_gated++; break; }
            }
            return -1;
        }
        if (!uncorrected && gbp_aplay_ready(p) >= GBP_APLAY_AHEAD) return -1;
        for (i = 0; i < (int)GBP_APLAY_POOL; i++)
            if (p->state[i] == GBP_APLAY_FREE) { found = i; break; }
        if (found < 0) return -1;
        p->cur = found;
        p->state[found] = GBP_APLAY_FILLING;
        p->seq[found] = p->produced;
        p->cur_frames = 0u;
        p->cur_pushes = 0u;
        /* Issue #105: the chunk's step size, asked once, here; anything out of range is the default */
        p->cur_step = p->step_pushes ? p->step_pushes(p->step_pushes_user, p->produced) : GBP_APLAY_STEP_PUSHES;
        if (p->cur_step == 0u || p->cur_step > GBP_APLAY_PUSHES) p->cur_step = GBP_APLAY_STEP_PUSHES;
        /* §V22.4 makes a correction a COUNTED event (a DUP or a DROP), not a ratio servo; how many a
         * chunk may take is corr_per_chunk (1, #92's image choice, §V22.10, until Issue #123). Each is
         * decided at the start of its sub-block, below. A transition's chunk (Issue #117) takes none:
         * exactly 128 samples out and no correction counted -- the executor holds the level, not the
         * band. */
        p->cur_corr = 0u;
        p->cur_corr_done = 1u;
        /* latched: the gate above was checked against it. Before playback starts a chunk takes at most one
         * correction: the ring filling up is not drift, and k DUPs a prefill chunk would only repeat samples */
        p->cur_k = p->playing ? p->corr_per_chunk : 1u;
        /* the chunk's frame, which every one of its decisions uses: the ring's count and the target at its start.
         * A set_target or a discard made while it is produced takes effect from the next chunk */
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
    while (p->cur_pushes < GBP_APLAY_PUSHES && step < p->cur_step) {
        int16_t x;
        /* Issue #123: a sub-block's decision, at its FIRST push, made by a corrected call -- a sub-block whose
         * first push an uncorrected call made is forgone, never decided late (a late DUP could land beside the
         * next sub-block's). It compares the chunk's frame: the chunk-start level less the chunk's own net
         * corrections so far (a DROP takes one sample more than it pushes, a DUP one fewer),
         * cur_s0 + cur_pushes - cur_taken, against the chunk-start target. Samples that arrive while the chunk
         * is produced are not in it -- a matched feed would read as surplus -- and neither is the ring's fall,
         * so the level holds at the band's edge instead of cycling past it (the review of Issue #123). With one
         * correction a chunk this is the chunk's first push, where cur_s0 is the ring's count and cur_target
         * the target: every earlier build's decision, unchanged. */
        if (!uncorrected && !p->cur_uncorrected && p->cur_sub < p->cur_k &&
            p->cur_pushes % (GBP_APLAY_PUSHES / p->cur_k) == 0u &&
            p->cur_pushes / (GBP_APLAY_PUSHES / p->cur_k) >= p->cur_sub) {
            const uint32_t fill = p->cur_s0 + p->cur_pushes - p->cur_taken;
            p->cur_corr = (fill < p->cur_target - GBP_APLAY_BAND) ? GBP_APLAY_EV_DUP :
                          (fill > p->cur_target + GBP_APLAY_BAND) ? GBP_APLAY_EV_DROP : 0u;
            p->cur_corr_done = 0u;
            p->corr_forgone += p->cur_pushes / (GBP_APLAY_PUSHES / p->cur_k) - p->cur_sub;  /* passed, undecided */
            p->cur_sub = p->cur_pushes / (GBP_APLAY_PUSHES / p->cur_k) + 1u;
        }
        if (!take(p, d, &x)) { p->starved_steps++; return -1; }   /* cannot happen: checked at the start */
        p->cur_taken++;
        if (p->cur_corr == GBP_APLAY_EV_DROP && !p->cur_corr_done) {
            p->cur_corr_done = 1u;
            p->drop++;
            if (p->l2.keeping) l2_event(p, GBP_APLAY_EV_DROP, p->l2.n_keep - 1u);
            continue;                                   /* the sample is not pushed */
        }
        push_one(p, x);
        step++;
        if (p->cur_corr == GBP_APLAY_EV_DUP && !p->cur_corr_done && p->cur_pushes < GBP_APLAY_PUSHES) {
            p->cur_corr_done = 1u;
            p->dup++;
            if (p->l2.keeping) l2_event(p, GBP_APLAY_EV_DUP, p->l2.n_keep - 1u);
            push_one(p, x);                             /* pushed twice */
            step++;
        }
    }
    if (p->cur_pushes < GBP_APLAY_PUSHES) return -1;
    {
        const int done = p->cur;
        if (!p->cur_uncorrected) p->corr_forgone += p->cur_k - p->cur_sub;   /* Issue #124: the rest, undecided */
        p->cur = -1;
        p->produced++;
        if (p->l2.keeping) {
            p->l2.kept_chunks++;
            if (p->l2.kept_chunks >= GBP_APLAY_L2_CHUNKS) {
                p->l2.keeping = 0u;                     /* the kept stream ends on this chunk's last push */
                p->l2.armed = 0u;
            }
        }
        return done;
    }
}

int gbp_aplay_produce(struct gbp_aplay *p, struct gbp_adec *d)
{
    return produce_impl(p, d, 0);
}

int gbp_aplay_produce_uncorrected(struct gbp_aplay *p, struct gbp_adec *d)
{
    return produce_impl(p, d, 1);
}

int gbp_aplay_produce_discard(struct gbp_aplay *p, struct gbp_adec *d)
{
    int b = produce_impl(p, d, 1);
    if (b >= 0 && !gbp_aplay_discard_chunk(p, b)) return -1;   /* cannot happen: just completed, not current */
    return b;
}

int gbp_aplay_drop_front(struct gbp_aplay *p)
{
    uint32_t h;
    int b;
    /* rq_head is the callback's. It is written here only while the callback's NEXT hand-off is silent
     * (mute >= 1): that hand-off leaves rq_head alone, and the one after it is a whole chunk (31 ms)
     * away -- this store is long done by then. */
    if (!p || p->mute == 0u || p->rq_head == p->rq_tail) return -1;
    h = p->rq_head;
    b = (int)p->rq[h % GBP_APLAY_POOL];
    p->state[b] = GBP_APLAY_FREE;
    p->rq_head = h + 1u;
    p->dropped_front++;
    return b;
}

uint32_t gbp_aplay_ready(const struct gbp_aplay *p)
{
    return p ? (uint32_t)(p->rq_tail - p->rq_head) : 0u;
}

void gbp_aplay_queue(struct gbp_aplay *p, int buf)
{
    if (!p || buf < 0 || buf >= (int)GBP_APLAY_POOL) return;
    p->state[buf] = GBP_APLAY_READY;
    p->rq[p->rq_tail % GBP_APLAY_POOL] = (uint8_t)buf;
    p->rq_tail = p->rq_tail + 1u;                       /* published after the entry */
}

void gbp_aplay_arm_l2(struct gbp_aplay *p)
{
    if (p && !p->l2.done && !p->l2.keeping) p->l2.armed = 1u;
}

/* The callback: interrupt context. Takes the oldest READY chunk, or hands silence -- or,
 * while a mute runs (Issue #117), silence regardless, with the queue left as it is. */
const uint8_t *gbp_aplay_irq_handoff(struct gbp_aplay *p, uint64_t t)
{
    int buf = GBP_APLAY_HL_SILENCE;
    if (p->measuring) {
        if (p->cb_count == 0u) p->cb_t_first = t;
        p->cb_t_last = t;
        p->cb_count = p->cb_count + 1u;
    }
    if (p->mute > 0u) {
        p->mute = p->mute - 1u;                         /* the callback's only write to it */
        p->mute_handed = p->mute_handed + 1u;
        buf = GBP_APLAY_HL_MUTE;                        /* not a silence, not an underrun: asked for */
    } else if (p->rq_head != p->rq_tail) {
        buf = (int)p->rq[p->rq_head % GBP_APLAY_POOL];
        p->rq_head = p->rq_head + 1u;
    } else {
        p->silences = p->silences + 1u;
        if (p->playing) p->underruns = p->underruns + 1u;
    }
    if (p->hl_tail - p->hl_head < GBP_APLAY_LOG) {
        p->hl[p->hl_tail % GBP_APLAY_LOG] = (int8_t)buf;
        p->hl_tail = p->hl_tail + 1u;
    } else {
        p->log_overflow++;                              /* the producer fell 256 hand-offs behind: counted */
    }
    p->handed = p->handed + 1u;
    return buf >= 0 ? p->pool + (size_t)buf * GBP_APLAY_CHUNK_BYTES : p->silence;
}

void gbp_aplay_process(struct gbp_aplay *p)
{
    if (!p) return;
    while (p->hl_head != p->hl_tail) {
        const int buf = (int)p->hl[p->hl_head % GBP_APLAY_LOG];
        p->hl_head = p->hl_head + 1u;
        /* L2's hand-off window: from the first kept chunk's hand-off to the last one's */
        if (buf >= 0 && !p->l2.handing && !p->l2.done && (p->l2.keeping || p->l2.kept_chunks) &&
            p->seq[buf] == p->l2.first_seq && p->l2.kept_chunks > 0u) {
            p->l2.handing = 1u;
            p->l2.crc = 0xFFFFFFFFu;
        }
        /* a mute hand-off (Issue #117) is outside L2's record; it still advances the freeing below */
        if (p->l2.handing && buf != GBP_APLAY_HL_MUTE) {
            if (buf < 0) {
                l2_event(p, GBP_APLAY_EV_SILENCE, p->l2.window_chunks);
                p->l2.silence_chunks++;
                p->l2.crc = gbp_aplay_crc_update(p->l2.crc, p->silence, GBP_APLAY_CHUNK_BYTES);
            } else {
                p->l2.crc = gbp_aplay_crc_update(p->l2.crc, chunk(p, buf), GBP_APLAY_CHUNK_BYTES);
            }
            p->l2.window_chunks++;
            if (buf >= 0 && p->seq[buf] == p->l2.first_seq + GBP_APLAY_L2_CHUNKS - 1u) {
                p->l2.handing = 0u;
                p->l2.done = 1u;
            }
        }
        if (buf >= 0) p->state[buf] = GBP_APLAY_HANDED;
        /* the chunk handed two hand-offs ago has finished playing */
        if (p->last_handed[0] >= 0) p->state[p->last_handed[0]] = GBP_APLAY_FREE;
        p->last_handed[0] = p->last_handed[1];
        p->last_handed[1] = buf;
    }
}

/* ---- the OGBPL2S1 sidecar ------------------------------------------------------ */
static uint8_t *be32(uint8_t *o, uint32_t v)
{
    o[0] = (uint8_t)(v >> 24); o[1] = (uint8_t)(v >> 16); o[2] = (uint8_t)(v >> 8); o[3] = (uint8_t)v;
    return o + 4;
}

static uint8_t *be16(uint8_t *o, int16_t s)
{
    const uint16_t v = (uint16_t)s;
    o[0] = (uint8_t)(v >> 8); o[1] = (uint8_t)(v & 0xFFu);
    return o + 2;
}

size_t gbp_aplay_sidecar_size(const struct gbp_aplay *p)
{
    uint32_t keep;
    if (!p) return 0u;
    keep = p->l2.n_keep < GBP_APLAY_KEEP_CAP ? p->l2.n_keep : GBP_APLAY_KEEP_CAP;
    return 0x48u + 8u * (size_t)p->l2.n_events + 2u * (size_t)keep + 4u;
}

size_t gbp_aplay_sidecar(const struct gbp_aplay *p, uint8_t *out, size_t cap)
{
    static const uint8_t magic[8] = { 'O', 'G', 'B', 'P', 'L', '2', 'S', '1' };
    const size_t need = gbp_aplay_sidecar_size(p);
    uint8_t *o = out;
    uint32_t k, keep;
    if (!p || !out || cap < need) return 0u;
    keep = p->l2.n_keep < GBP_APLAY_KEEP_CAP ? p->l2.n_keep : GBP_APLAY_KEEP_CAP;
    memcpy(o, magic, 8u); o += 8;
    o = be32(o, 1u);
    o = be32(o, GBP_APLAY_FRAMES);
    o = be32(o, p->l2.window_chunks);
    o = be32(o, p->l2.crc ^ 0xFFFFFFFFu);
    o = be32(o, p->l2.acc);
    o = be32(o, p->l2.hpos);
    for (k = 0; k < 16u; k++) o = be16(o, p->l2.hist[k]);
    o = be32(o, keep);
    o = be32(o, p->l2.n_events);
    for (k = 0; k < p->l2.n_events; k++) {
        o = be32(o, p->events[k].kind);
        o = be32(o, p->events[k].index);
    }
    for (k = 0; k < keep; k++) o = be16(o, p->keep[k]);
    o = be32(o, gbp_aplay_crc_update(0xFFFFFFFFu, out, (size_t)(o - out)) ^ 0xFFFFFFFFu);
    return (size_t)(o - out);
}
