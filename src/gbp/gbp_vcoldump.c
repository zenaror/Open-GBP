#include "gbp_vcoldump.h"

#include <string.h>
#include "gbp_crc32.h"
#include "gbp_vstatedump.h"

/* ---- primitives: every field written by hand, big-endian ---- */
static void put_u16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}
static void put_u64(uint8_t *p, uint64_t v) { put_u32(p, (uint32_t)(v >> 32)); put_u32(p + 4, (uint32_t)v); }
static uint16_t get_u16(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }
static uint32_t get_u32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}
static uint64_t get_u64(const uint8_t *p) { return ((uint64_t)get_u32(p) << 32) | get_u32(p + 4); }

static int reserved_zero(const uint8_t *p, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) if (p[i]) return 0;
    return 1;
}

/* The identity rule of this family: 32 bytes, NUL-terminated, nothing after the
 * terminator. A name that does not fit is an error - never a silent truncation. */
static int put_id(uint8_t *p, const char *s)
{
    size_t n = 0;
    memset(p, 0, GBP_VCOLDUMP_ID_FIELD);
    if (!s) return 0;
    while (s[n]) n++;
    if (n > GBP_VCOLDUMP_ID_MAX) return -1;
    memcpy(p, s, n);
    return 0;
}

static int id_ok(const uint8_t *p)
{
    unsigned i;
    int term = 0;
    for (i = 0; i < GBP_VCOLDUMP_ID_FIELD; i++) {
        if (!term) { if (!p[i]) term = 1; }
        else if (p[i]) return 0;                 /* bytes after the terminator */
    }
    return term;
}

int gbp_vcoldump_set_identity(struct gbp_vcoldump_info *info, const char *test_id,
                              const char *build_id, const char *app, const char *commit)
{
    uint8_t tmp[GBP_VCOLDUMP_ID_FIELD];
    int bad = 0;
    if (!info) return -1;
    memset(info->test_id, 0, sizeof info->test_id);
    memset(info->build_id, 0, sizeof info->build_id);
    memset(info->app, 0, sizeof info->app);
    memset(info->commit, 0, sizeof info->commit);
    if (put_id(tmp, test_id) != 0) bad = 1; else memcpy(info->test_id, tmp, sizeof tmp);
    if (put_id(tmp, build_id) != 0) bad = 1; else memcpy(info->build_id, tmp, sizeof tmp);
    if (put_id(tmp, app) != 0) bad = 1; else memcpy(info->app, tmp, sizeof tmp);
    if (put_id(tmp, commit) != 0) bad = 1; else memcpy(info->commit, tmp, sizeof tmp);
    info->identity_error = bad;
    return bad ? -1 : 0;
}

/* ---- layout: checked arithmetic, nothing written until every offset fits ---- */
int gbp_vcoldump_layout(struct gbp_vcoldump_info *info, const struct gbp_vcolor *c,
                        const struct gbp_vstate *st, const struct gbp_vstate_result *res,
                        const struct gbp_vstate_config *cfg)
{
    uint64_t off;
    unsigned i;
    int slots_usable;
    if (!info || !c || !st || !res || !cfg) return -1;

    info->version = (uint16_t)GBP_VCOLDUMP_VERSION;
    info->header_size = (uint16_t)GBP_VCOLDUMP_HEADER_SIZE;
    info->tb_hz = res->tb_hz ? res->tb_hz : cfg->a.tb_hz;
    info->video_block_size = GBP_VSTATE_VIDEO_BLOCK_SIZE;
    info->audio_block_size = GBP_VSTATE_AUDIO_BLOCK_SIZE;
    info->blocks_per_frame = GBP_VCOLOR_BLOCKS;
    info->frame_rec_size = (uint16_t)GBP_VCOLDUMP_FRAME_REC;
    info->cert_rec_size = (uint16_t)GBP_VCOLDUMP_CERT_REC;
    info->diag_rec_size = (uint16_t)GBP_VCOLDUMP_DIAG_REC;
    info->n_stable = (uint16_t)GBP_VCOLOR_N_STABLE;
    info->cert_budget = (uint16_t)GBP_VCOLOR_CERT_FRAMES;
    info->hold_frames_cfg = 0u;              /* RETIRED: there is no hold window (§V3.24) */

    /* The certified raw is serialized ONLY if the slots that hold it are still
     * provably the right ones. A file may not carry 460 800 bytes under three
     * identities it cannot justify, so when the check fails the raw section is
     * empty and the header says exactly that. */
    slots_usable = gbp_vcolor_slots_ok(c, st) ? 1 : 0;
    info->frame_count = c->frames_n;
    info->cert_count = (c->certified && slots_usable) ? c->cert_n : 0u;
    info->diag_count = st->diags_n;
    info->audio_raw_count = 0u;              /* §V3.13: AUDIO is drained and summarised, not stored */
    if (info->frame_count > GBP_VCOLDUMP_MAX_FRAMES) return -1;
    if (info->cert_count > GBP_VCOLDUMP_MAX_CERT) return -1;
    if (info->diag_count > GBP_VCOLDUMP_MAX_DIAGS) return -1;

    info->flags = 0;
    if (res->service_ok) info->flags |= GBP_VCOLDUMP_FLAG_SERVICE_OK;
    if (res->restore_ok) info->flags |= GBP_VCOLDUMP_FLAG_RESTORE_OK;
    if (c->certified) info->flags |= GBP_VCOLDUMP_FLAG_CERTIFIED;
    if (c->certified && !slots_usable) info->flags |= GBP_VCOLDUMP_FLAG_RAW_UNRECOVERABLE;
    if (!res->service_ok) info->flags |= GBP_VCOLDUMP_FLAG_PARTIAL;
    if (res->stage_a_aborted) info->flags |= GBP_VCOLDUMP_FLAG_STAGE_A_ABORTED;
    if (c->frames_dropped) info->flags |= GBP_VCOLDUMP_FLAG_FRAME_TABLE_CAP;

    info->status_code = (uint16_t)res->status;
    info->stop_reason = (uint16_t)res->stop;
    info->t_control_transform = res->t_control_transform;
    info->t_capture_start = res->t_capture_start;
    info->t_stop = res->t_stop;
    info->t_certified = c->certified ? c->t_certified : 0u;
    info->t_teardown_begin = res->t_teardown_begin;
    info->t_teardown_end = res->t_teardown_end;
    info->capture_elapsed = (res->t_stop > res->t_capture_start) ? res->t_stop - res->t_capture_start : 0u;
    info->safety_elapsed = (res->t_stop > res->t_control_transform) ? res->t_stop - res->t_control_transform : 0u;
    info->search_window_ticks = cfg->color_search_ticks;
    info->hard_wallclock_ticks = cfg->hard_wallclock_ticks;
    info->max_deliveries = cfg->max_deliveries;
    info->frame_table_cap = c->frames_cap;
    info->deliveries = res->deliveries;
    info->video_completed = res->video_completed;
    info->audio_drains = res->audio_drains;
    info->isr_w1c = res->isr_w1c;
    info->main_w1c = res->main_w1c;
    info->frames_total = c->frames_total;
    info->frames_eligible = c->frames_eligible;
    info->frames_dropped = c->frames_dropped;
    info->runs_reset = c->resets;
    info->hold_frames = 0u;                  /* RETIRED, and the parser refuses a non-zero value */
    info->hold_seen = 0u;
    info->sig_mismatches = c->sig_mismatches;
    info->run_len = c->run_len;
    info->run_first_index = c->run_first_index;
    for (i = 0; i < GBP_VCOLOR_REASONS; i++) info->frames_refused[i] = c->frames_refused[i];
    info->disagreements_total = st->sem.disagreements_total;
    info->source_serviced = st->sem.source_serviced;
    info->source_other = st->sem.source_other;
    info->non_source = st->sem.non_source;
    info->diagnostics_preserved = st->sem.diagnostics_preserved;
    info->diagnostics_not_preserved = st->sem.diagnostics_not_preserved;
    info->frames_quarantined = st->sem.frames_quarantined;
    info->frames_source_deferred = st->sem.frames_source_deferred;
    info->errors = res->a.errors;
    info->control_orig = res->a.control_orig;
    info->control_exp = res->a.control_exp;
    info->restore_flags = 0;
    if (res->restore_ok) info->restore_flags |= GBP_VCOLDUMP_RF_RESTORE_OK;
    if (res->h.handler_restored == 1) info->restore_flags |= GBP_VCOLDUMP_RF_HANDLER_RESTORED;
    if (res->h.mask_ok == 1) info->restore_flags |= GBP_VCOLDUMP_RF_MASK_OK;
    if (res->control_ok) info->restore_flags |= GBP_VCOLDUMP_RF_CONTROL_OK;
    if (res->pi_sticky_final) info->restore_flags |= GBP_VCOLDUMP_RF_PI_STICKY_FINAL;
    if (res->a.arinfo_restore_ok) info->restore_flags |= GBP_VCOLDUMP_RF_ARINFO_RESTORE_OK;
    if (res->a.power_cycle_required) info->restore_flags |= GBP_VCOLDUMP_RF_POWER_CYCLE_REQ;
    info->intmr_final = res->h.intmr_final;

    off = GBP_VCOLDUMP_HEADER_SIZE;
    info->off_frames = (uint32_t)off;
    off += (uint64_t)info->frame_count * GBP_VCOLDUMP_FRAME_REC;
    if (off > 0xFFFFFFFFu) return -1;
    info->off_cert = (uint32_t)off;
    off += (uint64_t)info->cert_count * GBP_VCOLDUMP_CERT_REC;
    if (off > 0xFFFFFFFFu) return -1;
    info->off_diag = (uint32_t)off;
    off += (uint64_t)info->diag_count * GBP_VCOLDUMP_DIAG_REC;
    if (off > 0xFFFFFFFFu) return -1;
    info->off_video_raw = (uint32_t)off;
    off += (uint64_t)info->cert_count * GBP_VCOLOR_FRAME_BYTES;
    if (off > 0xFFFFFFFFu) return -1;
    info->off_audio_raw = (uint32_t)off;
    off += (uint64_t)info->audio_raw_count * info->audio_block_size;
    if (off > 0xFFFFFFFFu) return -1;
    info->off_footer = (uint32_t)off;
    off += GBP_VCOLDUMP_FOOTER_SIZE;
    if (off > 0xFFFFFFFFu) return -1;
    info->total_size = off;
    return 0;
}

/* ---- record encoders ---- */
static void frame_rec(uint8_t *r, const struct gbp_vcolor_frame *f)
{
    memset(r, 0, GBP_VCOLDUMP_FRAME_REC);
    put_u64(r + 0x00, f->t_first);
    put_u64(r + 0x08, f->t_last);
    put_u32(r + 0x10, f->index);
    put_u32(r + 0x14, f->blocks);
    put_u16(r + 0x18, f->flags);
    put_u16(r + 0x1A, f->reason);
    put_u32(r + 0x1C, f->run_len_after);
    put_u32(r + 0x20, f->sig0);
    put_u32(r + 0x24, f->sig39);
    /* 0x28 and 0x2C stay zero: reserved, and the parser refuses anything else */
}

static void cert_rec(uint8_t *r, const struct gbp_vcolor_cert *c)
{
    memset(r, 0, GBP_VCOLDUMP_CERT_REC);
    put_u64(r + 0x00, c->t_first);
    put_u64(r + 0x08, c->t_last);
    put_u32(r + 0x10, c->frame_index);
    put_u32(r + 0x14, c->blocks);
    put_u32(r + 0x18, c->raw_offset);
    put_u16(r + 0x1C, c->ring_slot);
    put_u16(r + 0x1E, c->order);
    put_u32(r + 0x20, c->sig0);
    put_u32(r + 0x24, c->sig39);
    /* 0x28..0x27 none: the record is exactly 40 bytes and every one is defined */
}

static void header_rec(uint8_t *h, const struct gbp_vcoldump_info *in)
{
    unsigned i;
    memset(h, 0, GBP_VCOLDUMP_HEADER_SIZE);
    memcpy(h, GBP_VCOLDUMP_MAGIC, 8);
    put_u16(h + 0x008, in->version);
    put_u16(h + 0x00A, in->header_size);
    put_u32(h + 0x00C, in->flags);
    put_u32(h + 0x010, in->tb_hz);
    put_u32(h + 0x014, in->frame_count);
    put_u32(h + 0x018, in->cert_count);
    put_u32(h + 0x01C, in->diag_count);
    put_u32(h + 0x020, in->audio_raw_count);
    put_u32(h + 0x024, in->video_block_size);
    put_u32(h + 0x028, in->audio_block_size);
    put_u32(h + 0x02C, in->blocks_per_frame);
    put_u16(h + 0x030, in->frame_rec_size);
    put_u16(h + 0x032, in->cert_rec_size);
    put_u16(h + 0x034, in->diag_rec_size);
    put_u16(h + 0x036, in->status_code);
    put_u16(h + 0x038, in->stop_reason);
    put_u16(h + 0x03A, in->n_stable);
    put_u16(h + 0x03C, in->cert_budget);
    put_u16(h + 0x03E, in->hold_frames_cfg);
    memcpy(h + 0x040, in->test_id, GBP_VCOLDUMP_ID_FIELD);
    memcpy(h + 0x060, in->build_id, GBP_VCOLDUMP_ID_FIELD);
    memcpy(h + 0x080, in->app, GBP_VCOLDUMP_ID_FIELD);
    memcpy(h + 0x0A0, in->commit, GBP_VCOLDUMP_ID_FIELD);
    put_u32(h + 0x0C0, in->off_frames);
    put_u32(h + 0x0C4, in->off_cert);
    put_u32(h + 0x0C8, in->off_diag);
    put_u32(h + 0x0CC, in->off_video_raw);
    put_u32(h + 0x0D0, in->off_audio_raw);
    put_u32(h + 0x0D4, in->off_footer);
    put_u64(h + 0x0E0, in->t_control_transform);
    put_u64(h + 0x0E8, in->t_capture_start);
    put_u64(h + 0x0F0, in->t_stop);
    put_u64(h + 0x0F8, in->t_certified);
    put_u64(h + 0x100, in->t_teardown_begin);
    put_u64(h + 0x108, in->t_teardown_end);
    put_u64(h + 0x110, in->capture_elapsed);
    put_u64(h + 0x118, in->safety_elapsed);
    put_u64(h + 0x120, in->search_window_ticks);
    put_u64(h + 0x128, in->hard_wallclock_ticks);
    put_u32(h + 0x130, in->max_deliveries);
    put_u32(h + 0x134, in->frame_table_cap);
    put_u32(h + 0x138, in->deliveries);
    put_u32(h + 0x13C, in->video_completed);
    put_u32(h + 0x140, in->audio_drains);
    put_u32(h + 0x144, in->isr_w1c);
    put_u32(h + 0x148, in->main_w1c);
    put_u32(h + 0x14C, in->frames_total);
    put_u32(h + 0x150, in->frames_eligible);
    put_u32(h + 0x154, in->frames_dropped);
    put_u32(h + 0x158, in->runs_reset);
    put_u32(h + 0x15C, in->hold_frames);
    put_u32(h + 0x160, in->hold_seen);
    put_u32(h + 0x164, in->sig_mismatches);
    put_u32(h + 0x168, in->run_len);
    put_u32(h + 0x16C, in->run_first_index);
    for (i = 0; i < GBP_VCOLOR_REASONS; i++) put_u32(h + 0x170 + 4u * i, in->frames_refused[i]);
    put_u32(h + 0x194, in->disagreements_total);
    put_u32(h + 0x198, in->source_serviced);
    put_u32(h + 0x19C, in->source_other);
    put_u32(h + 0x1A0, in->non_source);
    put_u32(h + 0x1A4, in->diagnostics_preserved);
    put_u32(h + 0x1A8, in->diagnostics_not_preserved);
    put_u32(h + 0x1AC, in->frames_quarantined);
    put_u32(h + 0x1B0, in->frames_source_deferred);
    put_u32(h + 0x1B4, in->errors);
    put_u32(h + 0x1B8, in->control_orig);
    put_u32(h + 0x1BC, in->control_exp);
    put_u32(h + 0x1C0, in->restore_flags);
    put_u32(h + 0x1C4, in->intmr_final);
    put_u32(h + 0x1FC, gbp_crc32(h, GBP_VCOLDUMP_HEADER_SIZE - 4u));
}

/* ---- the streaming emitter: one transient buffer, a running CRC ---- */
struct emit {
    uint8_t *buf;
    uint32_t cap, used;
    gbp_vcoldump_sink sink;
    void *ctx;
    uint64_t written;
    uint32_t crc;
    int failed;
};

static void flush(struct emit *e)
{
    if (e->failed || !e->used) return;
    if (e->sink(e->ctx, e->buf, e->used) != 0) { e->failed = 1; return; }
    e->written += e->used;
    e->used = 0;
}

static void emit(struct emit *e, const uint8_t *data, uint32_t len)
{
    while (len && !e->failed) {
        uint32_t room = e->cap - e->used;
        uint32_t take = (len < room) ? len : room;
        memcpy(e->buf + e->used, data, take);
        e->crc = gbp_crc32_update(e->crc, data, take);
        e->used += take;
        data += take;
        len -= take;
        if (e->used == e->cap) flush(e);
    }
}

long gbp_vcoldump_stream(struct gbp_vcoldump_info *info, const struct gbp_vcolor *c,
                         const struct gbp_vstate *st, const struct gbp_vstate_result *res,
                         const struct gbp_vstate_config *cfg,
                         uint8_t *chunk, uint32_t chunk_cap,
                         gbp_vcoldump_sink sink, void *sink_ctx, uint64_t *written)
{
    struct emit e;
    uint8_t rec[GBP_VCOLDUMP_DIAG_REC];
    uint8_t header[GBP_VCOLDUMP_HEADER_SIZE];
    uint8_t foot[GBP_VCOLDUMP_FOOTER_SIZE];
    uint32_t i;
    if (written) *written = 0;
    if (!info || !c || !st || !res || !cfg || !chunk || chunk_cap < 1024u || !sink) return -1;
    if (info->identity_error) return -2;
    if (gbp_vcoldump_layout(info, c, st, res, cfg) != 0) return -3;

    memset(&e, 0, sizeof e);
    e.buf = chunk; e.cap = chunk_cap; e.sink = sink; e.ctx = sink_ctx;
    e.crc = gbp_crc32_init();

    header_rec(header, info);
    emit(&e, header, GBP_VCOLDUMP_HEADER_SIZE);

    for (i = 0; i < info->frame_count && !e.failed; i++) {
        frame_rec(rec, &c->frames[i]);
        emit(&e, rec, GBP_VCOLDUMP_FRAME_REC);
    }
    for (i = 0; i < info->cert_count && !e.failed; i++) {
        cert_rec(rec, &c->cert[i]);
        emit(&e, rec, GBP_VCOLDUMP_CERT_REC);
    }
    for (i = 0; i < info->diag_count && !e.failed; i++) {
        /* the SHARED record, through the SHARED encoder (§21) */
        gbp_vstatedump_encode_diag(rec, &st->diags[i]);
        emit(&e, rec, GBP_VCOLDUMP_DIAG_REC);
    }
    /* The raw frames, verbatim: every byte of every block, in block order, with
     * bytes 0 and 2 of each group included. Nothing is repaired, normalised or
     * reduced to the two bytes the references consume (§V3.13).
     *
     * STRAIGHT OUT OF THE STATE MODEL'S RING (§V3.24). These bytes have not been
     * copied since the DMA wrote them: the capture never staged them, and this
     * loop runs after the hardware teardown, where a multi-megabyte read costs
     * the experiment nothing. gbp_vcolor_slots_ok() has already established that
     * the three slots are in range, distinct, and none of them the slot the
     * assembler was filling. */
    for (i = 0; i < info->cert_count && !e.failed; i++) {
        const uint8_t *src = gbp_vstate_ring_frame(st, c->cert[i].ring_slot);
        if (!src) { e.failed = 1; break; }
        emit(&e, src, GBP_VCOLOR_FRAME_BYTES);
    }

    if (!e.failed) {
        /* The footer carries the CRC of everything BEFORE it, so the value is
         * taken here and the footer bytes are then written outside the running
         * CRC - a footer that covered itself could never be checked. */
        info->total_crc32 = gbp_crc32_final(e.crc);
        memcpy(foot, GBP_VCOLDUMP_END, 8);
        put_u32(foot + 8, info->total_crc32);
        if (e.used + GBP_VCOLDUMP_FOOTER_SIZE > e.cap) flush(&e);
        if (!e.failed) {
            memcpy(e.buf + e.used, foot, GBP_VCOLDUMP_FOOTER_SIZE);
            e.used += GBP_VCOLDUMP_FOOTER_SIZE;
        }
    }
    flush(&e);
    info->header_crc32 = get_u32(header + 0x1FC);
    if (written) *written = e.written;
    if (e.failed) return -4;
    return (long)e.written;
}

/* ---- the strict parser ---- */
void gbp_vcoldump_decode_frame(const uint8_t *rec, struct gbp_vcolor_frame *out)
{
    memset(out, 0, sizeof *out);
    out->t_first = get_u64(rec + 0x00);
    out->t_last = get_u64(rec + 0x08);
    out->index = get_u32(rec + 0x10);
    out->blocks = get_u32(rec + 0x14);
    out->flags = get_u16(rec + 0x18);
    out->reason = get_u16(rec + 0x1A);
    out->run_len_after = get_u32(rec + 0x1C);
    out->sig0 = get_u32(rec + 0x20);
    out->sig39 = get_u32(rec + 0x24);
}

void gbp_vcoldump_decode_cert(const uint8_t *rec, struct gbp_vcolor_cert *out)
{
    memset(out, 0, sizeof *out);
    out->t_first = get_u64(rec + 0x00);
    out->t_last = get_u64(rec + 0x08);
    out->frame_index = get_u32(rec + 0x10);
    out->blocks = get_u32(rec + 0x14);
    out->raw_offset = get_u32(rec + 0x18);
    out->ring_slot = get_u16(rec + 0x1C);
    out->order = get_u16(rec + 0x1E);
    out->sig0 = get_u32(rec + 0x20);
    out->sig39 = get_u32(rec + 0x24);
}

int gbp_vcoldump_parse(const uint8_t *in, size_t n, struct gbp_vcoldump_info *info,
                       const uint8_t **frames, const uint8_t **cert, const uint8_t **diag,
                       const uint8_t **video_raw, const uint8_t **audio_raw)
{
    struct gbp_vcoldump_info d;
    uint64_t need;
    uint32_t i;
    if (!in || n < GBP_VCOLDUMP_HEADER_SIZE + GBP_VCOLDUMP_FOOTER_SIZE) return -1;
    if (memcmp(in, GBP_VCOLDUMP_MAGIC, 8) != 0) return -1;
    memset(&d, 0, sizeof d);
    d.version = get_u16(in + 0x008);
    d.header_size = get_u16(in + 0x00A);
    if (d.version != GBP_VCOLDUMP_VERSION || d.header_size != GBP_VCOLDUMP_HEADER_SIZE) return -2;
    d.frame_rec_size = get_u16(in + 0x030);
    d.cert_rec_size = get_u16(in + 0x032);
    d.diag_rec_size = get_u16(in + 0x034);
    if (d.frame_rec_size != GBP_VCOLDUMP_FRAME_REC || d.cert_rec_size != GBP_VCOLDUMP_CERT_REC ||
        d.diag_rec_size != GBP_VCOLDUMP_DIAG_REC) return -2;
    if (gbp_crc32(in, GBP_VCOLDUMP_HEADER_SIZE - 4u) != get_u32(in + 0x1FC)) return -3;
    d.header_crc32 = get_u32(in + 0x1FC);

    d.flags = get_u32(in + 0x00C);
    if (d.flags & ~(uint32_t)GBP_VCOLDUMP_FLAG_ALL) return -8;
    d.tb_hz = get_u32(in + 0x010);
    d.frame_count = get_u32(in + 0x014);
    d.cert_count = get_u32(in + 0x018);
    d.diag_count = get_u32(in + 0x01C);
    d.audio_raw_count = get_u32(in + 0x020);
    d.video_block_size = get_u32(in + 0x024);
    d.audio_block_size = get_u32(in + 0x028);
    d.blocks_per_frame = get_u32(in + 0x02C);
    if (d.frame_count > GBP_VCOLDUMP_MAX_FRAMES) return -9;
    if (d.cert_count > GBP_VCOLDUMP_MAX_CERT) return -9;
    if (d.diag_count > GBP_VCOLDUMP_MAX_DIAGS) return -9;
    if (d.video_block_size != GBP_VSTATE_VIDEO_BLOCK_SIZE) return -9;
    if (d.audio_block_size != GBP_VSTATE_AUDIO_BLOCK_SIZE) return -9;
    if (d.blocks_per_frame != GBP_VCOLOR_BLOCKS) return -9;
    d.status_code = get_u16(in + 0x036);
    d.stop_reason = get_u16(in + 0x038);
    d.n_stable = get_u16(in + 0x03A);
    d.cert_budget = get_u16(in + 0x03C);
    d.hold_frames_cfg = get_u16(in + 0x03E);
    if (d.n_stable != GBP_VCOLOR_N_STABLE || d.cert_budget != GBP_VCOLOR_CERT_FRAMES) return -9;
    if (d.audio_raw_count > GBP_VCOLDUMP_MAX_AUDIO_RAW) return -9;
    /* A certified file must carry the certified flag and at least one frame, and
     * an uncertified one may carry neither: a sidecar may not claim evidence it
     * does not hold, in either direction. */
    if ((d.flags & GBP_VCOLDUMP_FLAG_CERTIFIED) && d.cert_count == 0u &&
        !(d.flags & GBP_VCOLDUMP_FLAG_RAW_UNRECOVERABLE)) return -9;
    if (!(d.flags & GBP_VCOLDUMP_FLAG_CERTIFIED) && d.cert_count != 0u) return -9;
    /* RAW_UNRECOVERABLE describes a certified run whose bytes were lost; it is
     * meaningless without CERTIFIED, and it may never sit next to raw. */
    if ((d.flags & GBP_VCOLDUMP_FLAG_RAW_UNRECOVERABLE) &&
        (!(d.flags & GBP_VCOLDUMP_FLAG_CERTIFIED) || d.cert_count != 0u)) return -9;
    if ((d.flags & GBP_VCOLDUMP_FLAG_HOLD_COMPLETE) != 0u) return -9;   /* retired */

    for (i = 0; i < 4u; i++) if (!id_ok(in + 0x040 + 0x20u * i)) return -7;
    memcpy(d.test_id, in + 0x040, GBP_VCOLDUMP_ID_FIELD);
    memcpy(d.build_id, in + 0x060, GBP_VCOLDUMP_ID_FIELD);
    memcpy(d.app, in + 0x080, GBP_VCOLDUMP_ID_FIELD);
    memcpy(d.commit, in + 0x0A0, GBP_VCOLDUMP_ID_FIELD);

    d.off_frames = get_u32(in + 0x0C0);
    d.off_cert = get_u32(in + 0x0C4);
    d.off_diag = get_u32(in + 0x0C8);
    d.off_video_raw = get_u32(in + 0x0CC);
    d.off_audio_raw = get_u32(in + 0x0D0);
    d.off_footer = get_u32(in + 0x0D4);
    if (!reserved_zero(in + 0x0D8, 0x0E0u - 0x0D8u)) return -8;
    if (!reserved_zero(in + 0x1C8, 0x1FCu - 0x1C8u)) return -8;

    d.t_control_transform = get_u64(in + 0x0E0);
    d.t_capture_start = get_u64(in + 0x0E8);
    d.t_stop = get_u64(in + 0x0F0);
    d.t_certified = get_u64(in + 0x0F8);
    d.t_teardown_begin = get_u64(in + 0x100);
    d.t_teardown_end = get_u64(in + 0x108);
    d.capture_elapsed = get_u64(in + 0x110);
    d.safety_elapsed = get_u64(in + 0x118);
    d.search_window_ticks = get_u64(in + 0x120);
    d.hard_wallclock_ticks = get_u64(in + 0x128);
    d.max_deliveries = get_u32(in + 0x130);
    d.frame_table_cap = get_u32(in + 0x134);
    d.deliveries = get_u32(in + 0x138);
    d.video_completed = get_u32(in + 0x13C);
    d.audio_drains = get_u32(in + 0x140);
    d.isr_w1c = get_u32(in + 0x144);
    d.main_w1c = get_u32(in + 0x148);
    d.frames_total = get_u32(in + 0x14C);
    d.frames_eligible = get_u32(in + 0x150);
    d.frames_dropped = get_u32(in + 0x154);
    d.runs_reset = get_u32(in + 0x158);
    d.hold_frames = get_u32(in + 0x15C);
    d.hold_seen = get_u32(in + 0x160);
    d.sig_mismatches = get_u32(in + 0x164);
    d.run_len = get_u32(in + 0x168);
    d.run_first_index = get_u32(in + 0x16C);
    for (i = 0; i < GBP_VCOLOR_REASONS; i++) d.frames_refused[i] = get_u32(in + 0x170 + 4u * i);
    /* The retired fields, checked where their values actually exist. A file
     * that carries one was written by a producer this parser does not describe,
     * and it is refused rather than read with a field silently ignored
     * (§V3.24). The order matters: this runs AFTER the reads above, because a
     * check on a field the parser has not filled yet checks nothing. */
    if (d.hold_frames_cfg != 0u || d.hold_frames != 0u || d.hold_seen != 0u) return -9;
    if (d.frames_refused[GBP_VCOLOR_RETIRED_PRE_BASELINE] != 0u) return -9;
    d.disagreements_total = get_u32(in + 0x194);
    d.source_serviced = get_u32(in + 0x198);
    d.source_other = get_u32(in + 0x19C);
    d.non_source = get_u32(in + 0x1A0);
    d.diagnostics_preserved = get_u32(in + 0x1A4);
    d.diagnostics_not_preserved = get_u32(in + 0x1A8);
    d.frames_quarantined = get_u32(in + 0x1AC);
    d.frames_source_deferred = get_u32(in + 0x1B0);
    d.errors = get_u32(in + 0x1B4);
    d.control_orig = get_u32(in + 0x1B8);
    d.control_exp = get_u32(in + 0x1BC);
    d.restore_flags = get_u32(in + 0x1C0);
    if (d.restore_flags & ~(uint32_t)GBP_VCOLDUMP_RF_ALL) return -8;
    d.intmr_final = get_u32(in + 0x1C4);

    /* sections: contiguous, in order, exactly the size the counts imply */
    if (d.off_frames != GBP_VCOLDUMP_HEADER_SIZE) return -4;
    need = (uint64_t)d.off_frames + (uint64_t)d.frame_count * GBP_VCOLDUMP_FRAME_REC;
    if (need != d.off_cert) return -4;
    need += (uint64_t)d.cert_count * GBP_VCOLDUMP_CERT_REC;
    if (need != d.off_diag) return -4;
    need += (uint64_t)d.diag_count * GBP_VCOLDUMP_DIAG_REC;
    if (need != d.off_video_raw) return -4;
    need += (uint64_t)d.cert_count * GBP_VCOLOR_FRAME_BYTES;
    if (need != d.off_audio_raw) return -4;
    need += (uint64_t)d.audio_raw_count * d.audio_block_size;
    if (need != d.off_footer) return -4;
    if ((uint64_t)d.off_footer + GBP_VCOLDUMP_FOOTER_SIZE != (uint64_t)n) return -1;

    if (memcmp(in + d.off_footer, GBP_VCOLDUMP_END, 8) != 0) return -5;
    d.total_crc32 = get_u32(in + d.off_footer + 8);
    if (gbp_crc32(in, d.off_footer) != d.total_crc32) return -6;
    d.total_size = (uint64_t)n;

    /* per-record rules */
    for (i = 0; i < d.frame_count; i++) {
        const uint8_t *r = in + d.off_frames + (size_t)i * GBP_VCOLDUMP_FRAME_REC;
        if (!reserved_zero(r + 0x28, 8u)) return -8;
        if (get_u16(r + 0x1A) >= GBP_VCOLOR_REASONS) return -9;
        if (get_u16(r + 0x1A) == GBP_VCOLOR_RETIRED_PRE_BASELINE) return -9;
        if (get_u32(r + 0x14) > GBP_VSTATE_FRAME_MAX_BLOCKS) return -9;
    }
    for (i = 0; i < d.cert_count; i++) {
        const uint8_t *r = in + d.off_cert + (size_t)i * GBP_VCOLDUMP_CERT_REC;
        uint32_t j;
        /* a certified frame is 40 blocks, and its raw sits exactly where the
         * order of the table says it does - no frame may point anywhere else */
        if (get_u32(r + 0x14) != GBP_VCOLOR_BLOCKS) return -9;
        if (get_u32(r + 0x18) != i * GBP_VCOLOR_FRAME_BYTES) return -9;
        if (get_u16(r + 0x1E) != (uint16_t)i) return -9;              /* order is A, B, C */
        if (get_u16(r + 0x1C) >= GBP_VSTATE_RAW_RING_SLOTS_MAX) return -9;
        /* Two certified frames may never name the same ring slot: that would be
         * the same bytes serialized twice under two identities (§V3.24). */
        for (j = 0; j < i; j++) {
            const uint8_t *q = in + d.off_cert + (size_t)j * GBP_VCOLDUMP_CERT_REC;
            if (get_u16(q + 0x1C) == get_u16(r + 0x1C)) return -9;
        }
    }
    for (i = 0; i < d.diag_count; i++) {
        /* the shared record keeps the v5 structural rules: reserved words zero,
         * a classification that exists, and never FU_PENDING in a saved file */
        const uint8_t *r = in + d.off_diag + (size_t)i * GBP_VCOLDUMP_DIAG_REC;
        uint16_t cls = get_u16(r + 0x66);
        uint8_t fu = r[0x8C], fur = r[0x8D];
        if (!reserved_zero(r + 0x5C, 4u) || !reserved_zero(r + 0x9E, 2u)) return -8;
        if (get_u16(r + 0x6E) & (uint16_t)~GBP_VSTATE_DF_ALL_V5) return -8;
        if (cls < 1u || cls > 3u) return -9;
        if (fu == GBP_VSTATE_FU_PENDING || fu > GBP_VSTATE_FU_UNKNOWN) return -9;
        if (fur > GBP_VSTATE_FUR_INTERNAL) return -9;
    }

    if (info) *info = d;
    if (frames) *frames = d.frame_count ? in + d.off_frames : 0;
    if (cert) *cert = d.cert_count ? in + d.off_cert : 0;
    if (diag) *diag = d.diag_count ? in + d.off_diag : 0;
    if (video_raw) *video_raw = d.cert_count ? in + d.off_video_raw : 0;
    if (audio_raw) *audio_raw = d.audio_raw_count ? in + d.off_audio_raw : 0;
    return 0;
}
