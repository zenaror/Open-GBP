#include "gbp_vstatedump.h"

#include <string.h>
#include "gbp_crc32.h"
/* The v5 cross-field invariants recompute both readings from the preserved raw
 * bytes with the SAME functions the runtime used, never with a second copy of
 * the rule (§R4.8). */
#include "gbp_rawlog.h"

/*
 * Header offsets (big-endian throughout). Everything not listed is reserved
 * and MUST be zero; the parser refuses a file whose reserved bytes are not.
 *
 *  0x000 magic "OGBPSEQ1"            0x008 u16 version (2)        0x00A u16 header_size (0x200)
 *  0x00C u32 flags                   0x010 u32 tb_hz
 *  0x014 u32 frame_count             0x018 u32 event_count        0x01C u32 episode_count
 *  0x020 u32 cycle_count             0x024 u32 video_raw_frames   0x028 u32 audio_raw_count
 *  0x02C u16 frame_rec               0x02E u16 event_rec
 *  0x030 u16 episode_rec             0x032 u16 cycle_rec
 *  0x034 u16 status_code             0x036 u16 stop_reason
 *  0x038 u32 off_frames              0x03C u32 off_events
 *  0x040 id test_id   0x060 id build_id   0x080 id app   0x0A0 id commit
 *  0x0C0 u32 off_episodes            0x0C4 u32 off_cycles
 *  0x0C8 u32 off_video_raw           0x0CC u32 off_audio_raw      0x0D0 u32 off_footer
 *  0x0D4 u32 video_block_size        0x0D8 u32 audio_block_size   0x0DC u32 frame_max_blocks
 *  0x0E0 u64 t_control_transform     0x0E8 u64 t_capture_start    0x0F0 u64 t_stop
 *  0x0F8 u64 capture_elapsed         0x100 u64 baseline_elapsed
 *  0x108 u64 valid_observation       0x110 u64 valid_at_target    0x118 u64 safety_elapsed
 *  0x120 u64 min_valid_ticks         0x128 u64 hard_wallclock_ticks
 *  0x130 u64 t_teardown_begin        0x138 u64 t_teardown_end
 *  0x140 u32 deliveries              0x144 u32 video_completed    0x148 u32 audio_drains
 *  0x14C u32 frames_complete         0x150 u32 frames_incomplete  0x154 u32 resync_frames
 *  0x158 u32 anomalies_frame         0x15C u32 anomalies_region
 *  0x160 u32 boundaries_disc         0x164 u32 boundaries_gbi     0x168 u32 disagreements
 *  0x16C u32 episodes_opened         0x170 u32 stable_episodes    0x174 u32 unstable_episodes
 *  0x178 u32 episodes_not_preserved  0x17C u32 events_dropped
 *  0x180 u32 event_seq_last          0x184 u32 baseline_frame_index
 *  0x188 u64 t_baseline_valid        0x190 u64 sig_samples        0x198 u64 sig_sum
 *  0x1A0 u32 sig_min   0x1A4 u32 sig_max   0x1A8 u32 sig_median   0x1AC u32 sig_p95
 *  0x1B0 u32 sig_overflow            0x1B4 u32 tail_frames        0x1B8 u64 tail_ticks
 *  0x1C0 u32 cyc_first_n  0x1C4 u32 cyc_last_n  0x1C8 u32 cyc_anomaly_n  0x1CC u32 cyc_episode_n
 *  0x1D0 u32 baseline_sig0           0x1D4 u32 baseline_sig39
 *  0x1D8 u32 main_w1c                0x1DC u32 isr_w1c
 *  0x1E0 u8[28] reserved (zero)      0x1FC u32 header_crc32 (bytes 0x000..0x1FB)
 *
 * Episode record (512 bytes):
 *  0x00 u32 index   0x04 u32 state   0x08 u32 flags   0x0C u32 open_frame
 *  0x10 u32 close_frame  0x14 u32 frames  0x18 u32 stable_count  0x1C u32 raw_frames
 *  0x20 u64 t_open  0x28 u64 t_close
 *  0x30 u32 raw_frame_index[4]   0x40 u32 raw_frame_blocks[4]   0x50 u32 raw_offset[4]
 *  0x60 u32 candidate[40]        0x100 u32 final_sig[40]        0x1A0 u8[0x60] reserved (zero)
 */

static void put_u16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static void put_u32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static void put_u64(uint8_t *p, uint64_t v) { put_u32(p, (uint32_t)(v >> 32)); put_u32(p + 4, (uint32_t)v); }
static uint16_t get_u16(const uint8_t *p) { return (uint16_t)(((uint16_t)p[0] << 8) | p[1]); }
static uint32_t get_u32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }
static uint64_t get_u64(const uint8_t *p) { return ((uint64_t)get_u32(p) << 32) | get_u32(p + 4); }

static int id_store(char dst[GBP_VSTATEDUMP_ID_FIELD], const char *src)
{
    size_t n = src ? strlen(src) : 0u;
    memset(dst, 0, GBP_VSTATEDUMP_ID_FIELD);
    if (n > GBP_VSTATEDUMP_ID_MAX) return -1;      /* never truncated: an identity that does not fit is an error */
    if (n) memcpy(dst, src, n);
    return 0;
}

int gbp_vstatedump_set_identity(struct gbp_vstatedump_info *info, const char *test_id, const char *build_id,
                                const char *app, const char *commit)
{
    int rc = 0;
    if (!info) return -1;
    if (id_store(info->test_id, test_id)) rc = -1;
    if (id_store(info->build_id, build_id)) rc = -1;
    if (id_store(info->app, app)) rc = -1;
    if (id_store(info->commit, commit)) rc = -1;
    info->identity_error = rc ? 1 : 0;
    return rc;
}

/* Bytes the preserved raw frames of one episode occupy. */
static uint64_t episode_raw_bytes(const struct gbp_vstate_episode *ep, uint32_t block_size)
{
    uint64_t n = 0;
    uint32_t k;
    for (k = 0; k < ep->raw_frames && k < GBP_VSTATE_EPISODE_RAW_SLOTS; k++)
        n += (uint64_t)ep->raw_frame_blocks[k] * block_size;
    return n;
}

int gbp_vstatedump_layout(struct gbp_vstatedump_info *info, const struct gbp_vstate *st,
                          const struct gbp_vstate_result *res, const struct gbp_vstate_config *cfg)
{
    uint64_t off, raw_bytes = 0;
    uint32_t i;
    if (!info || !st || !res || !cfg) return -1;

    info->version = (uint16_t)GBP_VSTATEDUMP_VERSION;
    info->header_size = (uint16_t)GBP_VSTATEDUMP_HEADER_SIZE;
    info->tb_hz = res->tb_hz ? res->tb_hz : cfg->a.tb_hz;
    info->flags = 0;
    if (res->service_ok) info->flags |= GBP_VSTATEDUMP_FLAG_SERVICE_OK;
    if (res->restore_ok) info->flags |= GBP_VSTATEDUMP_FLAG_RESTORE_OK;
    if (res->next_cause_at_end) info->flags |= GBP_VSTATEDUMP_FLAG_NEXT_CAUSE_AT_END;
    if (!res->service_ok) info->flags |= GBP_VSTATEDUMP_FLAG_PARTIAL;
    if (res->stage_a_aborted) info->flags |= GBP_VSTATEDUMP_FLAG_STAGE_A_ABORTED;
    if (st->baseline_valid) info->flags |= GBP_VSTATEDUMP_FLAG_BASELINE_VALID;
    if (st->frame_store_full) info->flags |= GBP_VSTATEDUMP_FLAG_FRAME_STORE_FULL;
    if (st->event_store_full) info->flags |= GBP_VSTATEDUMP_FLAG_EVENT_STORE_FULL;
    if (st->episode_store_full) info->flags |= GBP_VSTATEDUMP_FLAG_EPISODE_STORE_FULL;
    if (st->tail_truncated_by_cap) info->flags |= GBP_VSTATEDUMP_FLAG_TAIL_TRUNCATED;
    if (res->counter_overflow) info->flags |= GBP_VSTATEDUMP_FLAG_COUNTER_OVERFLOW;

    info->frame_count = st->frames_n;
    info->event_count = st->events_n;
    info->episode_count = st->episodes_n;
    info->cycle_count = res->cyc_first_n + res->cyc_last_n + res->cyc_anomaly_n + res->cyc_episode_n;
    info->audio_raw_count = gbp_vstate_audio_raw_count(st);
    info->video_block_size = GBP_VSTATE_VIDEO_BLOCK_SIZE;
    info->audio_block_size = GBP_VSTATE_AUDIO_BLOCK_SIZE;
    info->frame_max_blocks = GBP_VSTATE_FRAME_MAX_BLOCKS;
    info->status_code = (uint16_t)res->status;
    info->stop_reason = (uint16_t)res->stop;

    info->video_raw_frames = 0;
    for (i = 0; i < info->episode_count && i < GBP_VSTATE_MAX_EPISODES; i++) {
        const struct gbp_vstate_episode *ep = &st->episodes[i];
        uint32_t k = ep->raw_frames;
        if (k > GBP_VSTATE_EPISODE_RAW_SLOTS) return -1;
        info->video_raw_frames += k;
        raw_bytes += episode_raw_bytes(ep, info->video_block_size);
    }

    info->t_control_transform = res->t_control_transform;
    info->t_capture_start = res->t_capture_start;
    info->t_stop = res->t_stop;
    info->t_teardown_begin = res->t_teardown_begin;
    info->t_teardown_end = res->t_teardown_end;
    info->capture_elapsed = res->capture_elapsed;
    info->baseline_elapsed = res->baseline_elapsed;
    info->valid_observation_elapsed = res->valid_observation_elapsed;
    info->valid_observation_at_target = res->valid_observation_at_target;
    info->safety_elapsed = res->safety_elapsed;
    info->min_valid_observation_ticks = cfg->min_valid_observation_ticks;
    info->hard_wallclock_ticks = cfg->hard_wallclock_ticks;
    info->t_baseline_valid = st->t_baseline_valid;
    info->tail_ticks = st->tail_ticks;
    info->deliveries = res->deliveries;
    info->video_completed = res->video_completed;
    info->audio_drains = res->audio_drains;
    info->frames_complete = st->frames_complete;
    info->frames_incomplete = st->frames_incomplete;
    info->resync_frames = st->resync_frames;
    info->anomalies_frame = st->anomalies_frame;
    info->anomalies_region = st->anomalies_region;
    info->boundaries_disc = st->boundaries_disc;
    info->boundaries_gbi = st->boundaries_gbi;
    info->disagreements = st->disagreements_total;
    info->episodes_opened = st->episode_count;
    info->stable_episodes = st->stable_episodes;
    info->unstable_episodes = st->unstable_episodes;
    info->episodes_not_preserved = st->episodes_not_preserved;
    info->events_dropped = st->events_dropped;
    info->event_seq_last = st->event_seq;
    info->baseline_frame_index = st->baseline_frame_index;
    info->sig_samples = st->cost.count;
    info->sig_sum = st->cost.sum;
    info->sig_min = st->cost.count ? st->cost.min : 0u;
    info->sig_max = st->cost.max;
    info->sig_median = gbp_vsig_cost_quantile(&st->cost, 500u, 0, 0);
    info->sig_p95 = gbp_vsig_cost_quantile(&st->cost, 950u, 0, 0);
    info->sig_overflow = st->cost.overflow;
    info->tail_frames = st->tail_frames;
    info->cyc_first_n = res->cyc_first_n;
    info->cyc_last_n = res->cyc_last_n;
    info->cyc_anomaly_n = res->cyc_anomaly_n;
    info->cyc_episode_n = res->cyc_episode_n;
    info->baseline_sig0 = st->original_baseline_sig[0];
    info->baseline_sig39 = st->original_baseline_sig[GBP_VSTATE_FRAME_SIGS - 1u];
    info->main_w1c = res->main_w1c;
    info->isr_w1c = res->isr_w1c;

    /* checked arithmetic: every section is placed and proven before a byte is written */
    off = GBP_VSTATEDUMP_HEADER_SIZE;
    info->off_frames = (uint32_t)off;
    off += (uint64_t)info->frame_count * GBP_VSTATEDUMP_FRAME_REC;
    info->off_events = (uint32_t)off;
    off += (uint64_t)info->event_count * GBP_VSTATEDUMP_EVENT_REC;
    info->off_episodes = (uint32_t)off;
    off += (uint64_t)info->episode_count * GBP_VSTATEDUMP_EPISODE_REC;
    info->off_cycles = (uint32_t)off;
    off += (uint64_t)info->cycle_count * GBP_VSTATEDUMP_CYCLE_REC;
    /* v3: the one diagnostic record, if the run captured one. Its bytes are inside the total CRC
     * like every other section; nothing lives in a reserved area without a contract. */
    info->off_semantic = (uint32_t)off;
    info->semantic_size = GBP_VSTATEDUMP_SEMANTIC_SIZE;
    off += GBP_VSTATEDUMP_SEMANTIC_SIZE;
    info->diag_rec_size = GBP_VSTATEDUMP_DIAG_REC_V4;
    info->diag_count = st->diags_n;
    if (info->diag_count > GBP_VSTATEDUMP_MAX_DIAGS) return -1;
    info->diag_flags = (uint16_t)(st->sem.store_capped ? GBP_VSTATEDUMP_DIAGF_CAPPED : 0u);
    info->off_diag = (uint32_t)off;
    off += (uint64_t)info->diag_count * GBP_VSTATEDUMP_DIAG_REC_V4;
    info->off_video_raw = (uint32_t)off;
    off += raw_bytes;
    info->off_audio_raw = (uint32_t)off;
    off += (uint64_t)info->audio_raw_count * info->audio_block_size;
    info->off_footer = (uint32_t)off;
    off += GBP_VSTATEDUMP_FOOTER_SIZE;
    info->total_size = off;
    if (off > 0xFFFFFFFFu) return -1;
    if (info->off_frames > info->off_events || info->off_events > info->off_episodes ||
        info->off_episodes > info->off_cycles || info->off_cycles > info->off_semantic ||
        info->off_semantic > info->off_diag || info->off_diag > info->off_video_raw ||
        info->off_video_raw > info->off_audio_raw || info->off_audio_raw > info->off_footer) return -1;
    return 0;
}

/* ---- streaming ------------------------------------------------------- */
struct emit {
    uint8_t *chunk;
    uint32_t cap, used;
    gbp_vstatedump_sink sink;
    void *ctx;
    uint32_t crc;
    uint64_t written;
    int failed;
};

static void emit_flush(struct emit *e)
{
    if (e->failed || !e->used) return;
    if (e->sink(e->ctx, e->chunk, e->used) != 0) { e->failed = 1; return; }
    e->written += e->used;
    e->used = 0;
}

static void emit(struct emit *e, const uint8_t *data, uint32_t len)
{
    if (e->failed) return;
    e->crc = gbp_crc32_update(e->crc, data, len);
    while (len) {
        uint32_t room = e->cap - e->used;
        uint32_t n = (len < room) ? len : room;
        memcpy(e->chunk + e->used, data, n);
        e->used += n;
        data += n;
        len -= n;
        if (e->used == e->cap) { emit_flush(e); if (e->failed) return; }
    }
}

static void emit_zero(struct emit *e, uint32_t len)
{
    uint8_t z[64];
    memset(z, 0, sizeof z);
    while (len && !e->failed) {
        uint32_t n = (len < sizeof z) ? len : (uint32_t)sizeof z;
        emit(e, z, n);
        len -= n;
    }
}

static void frame_rec(uint8_t *r, const struct gbp_vstate_frame *f)
{
    unsigned i;
    memset(r, 0, GBP_VSTATEDUMP_FRAME_REC);
    put_u64(r + 0x00, f->t_first_block);
    put_u64(r + 0x08, f->t_last_block);
    put_u32(r + 0x10, f->index);
    put_u32(r + 0x14, f->episode);
    put_u16(r + 0x18, f->blocks);
    put_u16(r + 0x1A, f->flags);
    put_u16(r + 0x1C, f->disagreements);
    put_u16(r + 0x1E, f->completeness);
    for (i = 0; i < GBP_VSTATE_FRAME_SIGS; i++) put_u32(r + 0x20 + i * 4u, f->sig[i]);
}

static void event_rec(uint8_t *r, const struct gbp_vstate_event *e)
{
    memset(r, 0, GBP_VSTATEDUMP_EVENT_REC);
    put_u64(r + 0x00, e->t);
    put_u32(r + 0x08, e->seq);
    put_u16(r + 0x0C, e->type);
    put_u16(r + 0x0E, e->flags);
    put_u32(r + 0x10, e->a);
    put_u32(r + 0x14, e->b);
    put_u32(r + 0x18, e->c);
    put_u32(r + 0x1C, e->d);
    put_u32(r + 0x20, e->frame);
    put_u32(r + 0x24, e->episode);
    put_u32(r + 0x28, e->e);
    put_u32(r + 0x2C, e->f);
    put_u64(r + 0x30, e->t2);
    put_u32(r + 0x38, e->g);
    put_u32(r + 0x3C, e->h);
}

static void episode_rec(uint8_t *r, const struct gbp_vstate_episode *ep, const uint32_t raw_off[GBP_VSTATE_EPISODE_RAW_SLOTS])
{
    unsigned i;
    memset(r, 0, GBP_VSTATEDUMP_EPISODE_REC);
    put_u32(r + 0x00, ep->index);
    put_u32(r + 0x04, ep->state);
    put_u32(r + 0x08, ep->flags);
    put_u32(r + 0x0C, ep->open_frame);
    put_u32(r + 0x10, ep->close_frame);
    put_u32(r + 0x14, ep->frames);
    put_u32(r + 0x18, ep->stable_count);
    put_u32(r + 0x1C, ep->raw_frames);
    put_u64(r + 0x20, ep->t_open);
    put_u64(r + 0x28, ep->t_close);
    for (i = 0; i < GBP_VSTATE_EPISODE_RAW_SLOTS; i++) {
        put_u32(r + 0x30 + i * 4u, ep->raw_frame_index[i]);
        put_u32(r + 0x40 + i * 4u, ep->raw_frame_blocks[i]);
        put_u32(r + 0x50 + i * 4u, raw_off ? raw_off[i] : 0u);
    }
    for (i = 0; i < GBP_VSTATE_FRAME_SIGS; i++) {
        put_u32(r + 0x60 + i * 4u, ep->candidate[i]);
        put_u32(r + 0x100 + i * 4u, ep->final_sig[i]);
    }
}

static void cycle_rec(uint8_t *r, const struct gbp_vstate_cycle *c)
{
    memset(r, 0, GBP_VSTATEDUMP_CYCLE_REC);
    put_u64(r + 0x00, c->t_cause);
    put_u64(r + 0x08, c->t_unmask);
    put_u64(r + 0x10, c->t_entry);
    put_u64(r + 0x18, c->t_read);
    put_u64(r + 0x20, c->t_ack);
    put_u64(r + 0x28, c->t_rearm);
    put_u64(r + 0x30, c->t_next);
    put_u32(r + 0x38, c->index);
    put_u32(r + 0x3C, c->frame_index);
    put_u16(r + 0x40, c->pending);
    put_u16(r + 0x42, c->ack_value);
    put_u16(r + 0x44, c->kind);
    put_u16(r + 0x46, c->flags);
    r[0x48] = c->audio_selected; r[0x49] = c->audio_completed; r[0x4A] = c->video_selected; r[0x4B] = c->video_completed;
    r[0x4C] = c->main_w1c; r[0x4D] = c->isr_count; r[0x4E] = c->isr_reentry; r[0x4F] = c->next_observed;
    put_u32(r + 0x50, c->latency_ticks);
    put_u32(r + 0x54, c->audio_wait);
    put_u32(r + 0x58, c->video_wait);
    put_u32(r + 0x5C, c->sig_ticks);
    put_u32(r + 0x60, c->intsr_entry);
    put_u32(r + 0x64, c->intsr_after_w1c);
    put_u32(r + 0x68, c->intsr_postack);
    put_u32(r + 0x6C, c->intsr_next);
    put_u32(r + 0x70, c->block_in_frame);
    put_u32(r + 0x74, c->rc);
}


static void diag_rec(uint8_t *r, const struct gbp_vstate_diag *d);

void gbp_vstatedump_encode_diag(uint8_t *rec, const struct gbp_vstate_diag *d)
{
    if (rec && d) diag_rec(rec, d);
}

static void diag_rec(uint8_t *r, const struct gbp_vstate_diag *d)
{
    unsigned i;
    memset(r, 0, GBP_VSTATEDUMP_DIAG_REC_V4);
    put_u64(r + 0x00, d->t);
    put_u32(r + 0x08, d->cycle);
    put_u32(r + 0x0C, d->valid);
    put_u16(r + 0x10, d->disc_value);
    put_u16(r + 0x12, d->gbi_value);
    put_u16(r + 0x14, d->read_kind);
    put_u16(r + 0x16, d->attempts);
    for (i = 0; i < GBP_BLOCK_SIZE; i++) r[0x18 + i] = d->raw[i];   /* verbatim */
    put_u32(r + 0x38, d->intsr_entry);
    put_u32(r + 0x3C, d->intsr_after_w1c);
    put_u32(r + 0x40, d->intmr_entry);
    put_u32(r + 0x44, d->latency_ticks);
    put_u32(r + 0x48, d->xfer_ticks);
    put_u16(r + 0x4C, d->xfer_polls);
    put_u16(r + 0x4E, d->dma_status);
    put_u16(r + 0x50, d->dma_status_before);
    put_u16(r + 0x52, d->control_exp);
    put_u32(r + 0x54, d->frame_index);
    put_u32(r + 0x58, d->block_in_frame);
    /* 0x5C reserved0 stays zero */
    /* ---- the v4 extension (§R3.24), field by field, big-endian ---- */
    put_u16(r + 0x60, d->delta);
    put_u16(r + 0x62, d->disc_extra_sources);
    put_u16(r + 0x64, d->majority_extra_sources);
    put_u16(r + 0x66, d->classification);
    put_u16(r + 0x68, d->authoritative_value);
    put_u16(r + 0x6A, d->ack_value);
    put_u16(r + 0x6C, d->service_selected);
    put_u16(r + 0x6E, d->record_flags);
    put_u64(r + 0x70, d->t_ack);
    put_u64(r + 0x78, d->t_rearm);
    put_u64(r + 0x80, d->t_next_cause);
    put_u16(r + 0x88, d->next_pending_gbi);
    put_u16(r + 0x8A, d->next_pending_disc);
    r[0x8C] = d->followup_state;
    r[0x8D] = d->followup_reason;
    put_u16(r + 0x8E, d->payload_source);
    put_u32(r + 0x90, d->payload_crc32);
    put_u32(r + 0x94, d->payload_first_word);
    put_u32(r + 0x98, d->gap_min_before_ticks);
    put_u16(r + 0x9C, d->gap_count_before);
    /* 0x9E reserved1 stays zero */
}

/* The fixed 1024-byte semantic block (§R3.27). */
static void semantic_block(uint8_t *b, const struct gbp_vstate_semantic *m)
{
    const uint32_t c[21] = {
        m->disagreements_total, m->source_serviced, m->source_other, m->non_source,
        m->disc_extra_events, m->majority_extra_events, m->both_direction_events,
        m->majority_extra_video_services, m->majority_extra_audio_services,
        m->frames_quarantined, m->frames_source_deferred, m->diagnostics_preserved,
        m->diagnostics_not_preserved, m->followup_present, m->followup_absent,
        m->followup_no_next, m->followup_unknown, m->observational_disagreements,
        m->service_selecting_disagreements, m->payload_diagnostics_captured,
        m->service_incomplete_events
    };
    unsigned i;
    memset(b, 0, GBP_VSTATEDUMP_SEMANTIC_SIZE);
    put_u32(b + 0x000, GBP_VSTATEDUMP_SEMANTIC_TAG);
    put_u16(b + 0x004, (uint16_t)GBP_VSTATEDUMP_SEMANTIC_VERSION);
    put_u16(b + 0x006, (uint16_t)(m->store_capped ? GBP_VSTATEDUMP_DIAGF_CAPPED : 0u));
    for (i = 0; i < 21u; i++) put_u32(b + 0x008 + 4u * i, c[i]);
    /* 0x05C..0x06F reserved, already zero */
    for (i = 0; i < GBP_VSTATE_GAP_SLOTS; i++) {
        uint8_t *g = b + 0x070 + 24u * i;
        put_u16(g + 0x00, gbp_vstate_gap_slot_bit(i));
        put_u32(g + 0x04, m->gap[i].count);
        put_u32(g + 0x08, m->gap[i].min_ticks);
        put_u32(g + 0x0C, m->gap[i].max_ticks);
        put_u32(g + 0x10, m->gap[i].last_ticks);
    }
    for (i = 0; i < GBP_VSTATE_HIST_ENTRIES; i++) {
        put_u32(b + 0x100 + 4u * i, m->delta_hist[i]);
        put_u32(b + 0x200 + 4u * i, m->disc_extra_hist[i]);
        put_u32(b + 0x300 + 4u * i, m->majority_extra_hist[i]);
    }
}

int gbp_vstatedump_decode_diag_v4(const uint8_t *rec, struct gbp_vstate_diag *out)
{
    if (!gbp_vstatedump_decode_diag(rec, out)) return 0;
    out->delta = get_u16(rec + 0x60);
    out->disc_extra_sources = get_u16(rec + 0x62);
    out->majority_extra_sources = get_u16(rec + 0x64);
    out->classification = get_u16(rec + 0x66);
    out->authoritative_value = get_u16(rec + 0x68);
    out->ack_value = get_u16(rec + 0x6A);
    out->service_selected = get_u16(rec + 0x6C);
    out->record_flags = get_u16(rec + 0x6E);
    out->t_ack = get_u64(rec + 0x70);
    out->t_rearm = get_u64(rec + 0x78);
    out->t_next_cause = get_u64(rec + 0x80);
    out->next_pending_gbi = get_u16(rec + 0x88);
    out->next_pending_disc = get_u16(rec + 0x8A);
    out->followup_state = rec[0x8C];
    out->followup_reason = rec[0x8D];
    out->payload_source = get_u16(rec + 0x8E);
    out->payload_crc32 = get_u32(rec + 0x90);
    out->payload_first_word = get_u32(rec + 0x94);
    out->gap_min_before_ticks = get_u32(rec + 0x98);
    out->gap_count_before = get_u16(rec + 0x9C);
    return 1;
}

int gbp_vstatedump_decode_semantic(const uint8_t *blk, struct gbp_vstate_semantic *out)
{
    uint32_t *c;
    unsigned i;
    if (!blk || !out) return -1;
    if (get_u32(blk + 0x000) != GBP_VSTATEDUMP_SEMANTIC_TAG) return -1;
    if (get_u16(blk + 0x004) != GBP_VSTATEDUMP_SEMANTIC_VERSION) return -1;
    memset(out, 0, sizeof *out);
    out->store_capped = (get_u16(blk + 0x006) & GBP_VSTATEDUMP_DIAGF_CAPPED) ? 1u : 0u;
    /* the 21 counters, in the normative order, read straight into the struct's
     * first 21 u32 members - which are declared in exactly that order */
    c = &out->disagreements_total;
    for (i = 0; i < 21u; i++) c[i] = get_u32(blk + 0x008 + 4u * i);
    for (i = 0; i < GBP_VSTATE_GAP_SLOTS; i++) {
        const uint8_t *g = blk + 0x070 + 24u * i;
        out->gap[i].count = get_u32(g + 0x04);
        out->gap[i].min_ticks = get_u32(g + 0x08);
        out->gap[i].max_ticks = get_u32(g + 0x0C);
        out->gap[i].last_ticks = get_u32(g + 0x10);
    }
    for (i = 0; i < GBP_VSTATE_HIST_ENTRIES; i++) {
        out->delta_hist[i] = get_u32(blk + 0x100 + 4u * i);
        out->disc_extra_hist[i] = get_u32(blk + 0x200 + 4u * i);
        out->majority_extra_hist[i] = get_u32(blk + 0x300 + 4u * i);
    }
    return 0;
}

int gbp_vstatedump_decode_diag(const uint8_t *rec, struct gbp_vstate_diag *out)
{
    unsigned i;
    if (!rec || !out) return 0;
    memset(out, 0, sizeof *out);
    out->t = get_u64(rec + 0x00);
    out->cycle = get_u32(rec + 0x08);
    out->valid = get_u32(rec + 0x0C);
    out->disc_value = get_u16(rec + 0x10);
    out->gbi_value = get_u16(rec + 0x12);
    out->read_kind = get_u16(rec + 0x14);
    out->attempts = get_u16(rec + 0x16);
    for (i = 0; i < GBP_BLOCK_SIZE; i++) out->raw[i] = rec[0x18 + i];
    out->intsr_entry = get_u32(rec + 0x38);
    out->intsr_after_w1c = get_u32(rec + 0x3C);
    out->intmr_entry = get_u32(rec + 0x40);
    out->latency_ticks = get_u32(rec + 0x44);
    out->xfer_ticks = get_u32(rec + 0x48);
    out->xfer_polls = get_u16(rec + 0x4C);
    out->dma_status = get_u16(rec + 0x4E);
    out->dma_status_before = get_u16(rec + 0x50);
    out->control_exp = get_u16(rec + 0x52);
    out->frame_index = get_u32(rec + 0x54);
    out->block_in_frame = get_u32(rec + 0x58);
    return out->valid ? 1 : 0;
}

static void header_bytes(uint8_t *h, const struct gbp_vstatedump_info *in)
{
    memset(h, 0, GBP_VSTATEDUMP_HEADER_SIZE);
    memcpy(h + 0x000, GBP_VSTATEDUMP_MAGIC, 8);
    put_u16(h + 0x008, in->version);
    put_u16(h + 0x00A, in->header_size);
    put_u32(h + 0x00C, in->flags);
    put_u32(h + 0x010, in->tb_hz);
    put_u32(h + 0x014, in->frame_count);
    put_u32(h + 0x018, in->event_count);
    put_u32(h + 0x01C, in->episode_count);
    put_u32(h + 0x020, in->cycle_count);
    put_u32(h + 0x024, in->video_raw_frames);
    put_u32(h + 0x028, in->audio_raw_count);
    put_u16(h + 0x02C, (uint16_t)GBP_VSTATEDUMP_FRAME_REC);
    put_u16(h + 0x02E, (uint16_t)GBP_VSTATEDUMP_EVENT_REC);
    put_u16(h + 0x030, (uint16_t)GBP_VSTATEDUMP_EPISODE_REC);
    put_u16(h + 0x032, (uint16_t)GBP_VSTATEDUMP_CYCLE_REC);
    put_u16(h + 0x034, in->status_code);
    put_u16(h + 0x036, in->stop_reason);
    put_u32(h + 0x038, in->off_frames);
    put_u32(h + 0x03C, in->off_events);
    memcpy(h + 0x040, in->test_id, GBP_VSTATEDUMP_ID_FIELD);
    memcpy(h + 0x060, in->build_id, GBP_VSTATEDUMP_ID_FIELD);
    memcpy(h + 0x080, in->app, GBP_VSTATEDUMP_ID_FIELD);
    memcpy(h + 0x0A0, in->commit, GBP_VSTATEDUMP_ID_FIELD);
    put_u32(h + 0x0C0, in->off_episodes);
    put_u32(h + 0x0C4, in->off_cycles);
    put_u32(h + 0x0C8, in->off_video_raw);
    put_u32(h + 0x0CC, in->off_audio_raw);
    put_u32(h + 0x0D0, in->off_footer);
    put_u32(h + 0x0D4, in->video_block_size);
    put_u32(h + 0x0D8, in->audio_block_size);
    put_u32(h + 0x0DC, in->frame_max_blocks);
    put_u64(h + 0x0E0, in->t_control_transform);
    put_u64(h + 0x0E8, in->t_capture_start);
    put_u64(h + 0x0F0, in->t_stop);
    put_u64(h + 0x0F8, in->capture_elapsed);
    put_u64(h + 0x100, in->baseline_elapsed);
    put_u64(h + 0x108, in->valid_observation_elapsed);
    put_u64(h + 0x110, in->valid_observation_at_target);
    put_u64(h + 0x118, in->safety_elapsed);
    put_u64(h + 0x120, in->min_valid_observation_ticks);
    put_u64(h + 0x128, in->hard_wallclock_ticks);
    put_u64(h + 0x130, in->t_teardown_begin);
    put_u64(h + 0x138, in->t_teardown_end);
    put_u32(h + 0x140, in->deliveries);
    put_u32(h + 0x144, in->video_completed);
    put_u32(h + 0x148, in->audio_drains);
    put_u32(h + 0x14C, in->frames_complete);
    put_u32(h + 0x150, in->frames_incomplete);
    put_u32(h + 0x154, in->resync_frames);
    put_u32(h + 0x158, in->anomalies_frame);
    put_u32(h + 0x15C, in->anomalies_region);
    put_u32(h + 0x160, in->boundaries_disc);
    put_u32(h + 0x164, in->boundaries_gbi);
    put_u32(h + 0x168, in->disagreements);
    put_u32(h + 0x16C, in->episodes_opened);
    put_u32(h + 0x170, in->stable_episodes);
    put_u32(h + 0x174, in->unstable_episodes);
    put_u32(h + 0x178, in->episodes_not_preserved);
    put_u32(h + 0x17C, in->events_dropped);
    put_u32(h + 0x180, in->event_seq_last);
    put_u32(h + 0x184, in->baseline_frame_index);
    put_u64(h + 0x188, in->t_baseline_valid);
    put_u64(h + 0x190, in->sig_samples);
    put_u64(h + 0x198, in->sig_sum);
    put_u32(h + 0x1A0, in->sig_min);
    put_u32(h + 0x1A4, in->sig_max);
    put_u32(h + 0x1A8, in->sig_median);
    put_u32(h + 0x1AC, in->sig_p95);
    put_u32(h + 0x1B0, in->sig_overflow);
    put_u32(h + 0x1B4, in->tail_frames);
    put_u64(h + 0x1B8, in->tail_ticks);
    put_u32(h + 0x1C0, in->cyc_first_n);
    put_u32(h + 0x1C4, in->cyc_last_n);
    put_u32(h + 0x1C8, in->cyc_anomaly_n);
    put_u32(h + 0x1CC, in->cyc_episode_n);
    put_u32(h + 0x1D0, in->baseline_sig0);
    put_u32(h + 0x1D4, in->baseline_sig39);
    put_u32(h + 0x1D8, in->main_w1c);
    put_u32(h + 0x1DC, in->isr_w1c);
    /* v3 fields, taken from v2's reserved area and given an explicit contract */
    put_u32(h + 0x1E0, in->off_diag);
    put_u32(h + 0x1E4, in->diag_count);
    put_u16(h + 0x1E8, (uint16_t)in->diag_rec_size);
    put_u16(h + 0x1EA, in->diag_flags);
    put_u32(h + 0x1EC, in->off_semantic);
    put_u32(h + 0x1F0, in->semantic_size);
    /* 0x1F4..0x1FB reserved, already zero */
    put_u32(h + 0x1FC, gbp_crc32(h, GBP_VSTATEDUMP_HEADER_SIZE - 4u));
}

long gbp_vstatedump_stream(struct gbp_vstatedump_info *info, const struct gbp_vstate *st,
                           const struct gbp_vstate_result *res, const struct gbp_vstate_config *cfg,
                           uint8_t *chunk, uint32_t chunk_cap,
                           gbp_vstatedump_sink sink, void *sink_ctx, uint64_t *written)
{
    static uint8_t hdr[GBP_VSTATEDUMP_HEADER_SIZE];
    uint8_t rec[GBP_VSTATEDUMP_EPISODE_REC];
    uint32_t raw_off[GBP_VSTATE_EPISODE_RAW_SLOTS];
    struct emit e;
    uint32_t i, k, cursor;
    if (written) *written = 0;
    if (!info || !st || !res || !cfg || !chunk || chunk_cap < 1024u || !sink) return -1;
    if (info->identity_error) return -2;
    if (gbp_vstatedump_layout(info, st, res, cfg) != 0) return -3;

    memset(&e, 0, sizeof e);
    e.chunk = chunk; e.cap = chunk_cap; e.sink = sink; e.ctx = sink_ctx;
    e.crc = gbp_crc32_init();

    header_bytes(hdr, info);
    info->header_crc32 = get_u32(hdr + 0x1FC);
    emit(&e, hdr, GBP_VSTATEDUMP_HEADER_SIZE);

    for (i = 0; i < info->frame_count && !e.failed; i++) {
        uint8_t fr[GBP_VSTATEDUMP_FRAME_REC];
        frame_rec(fr, &st->frames[i]);
        emit(&e, fr, GBP_VSTATEDUMP_FRAME_REC);
    }
    for (i = 0; i < info->event_count && !e.failed; i++) {
        uint8_t ev[GBP_VSTATEDUMP_EVENT_REC];
        event_rec(ev, &st->events[i]);
        emit(&e, ev, GBP_VSTATEDUMP_EVENT_REC);
    }
    cursor = info->off_video_raw;
    for (i = 0; i < info->episode_count && !e.failed; i++) {
        const struct gbp_vstate_episode *ep = &st->episodes[i];
        memset(raw_off, 0, sizeof raw_off);
        for (k = 0; k < ep->raw_frames && k < GBP_VSTATE_EPISODE_RAW_SLOTS; k++) {
            raw_off[k] = cursor;
            cursor += ep->raw_frame_blocks[k] * info->video_block_size;
        }
        episode_rec(rec, ep, raw_off);
        emit(&e, rec, GBP_VSTATEDUMP_EPISODE_REC);
    }
    {
        const struct gbp_vstate_cycle *tabs[4];
        uint32_t ns[4];
        unsigned s;
        tabs[0] = cfg->cyc_first;   ns[0] = res->cyc_first_n;
        tabs[1] = cfg->cyc_last;    ns[1] = res->cyc_last_n;
        tabs[2] = cfg->cyc_anomaly; ns[2] = res->cyc_anomaly_n;
        tabs[3] = cfg->cyc_episode; ns[3] = res->cyc_episode_n;
        for (s = 0; s < 4u && !e.failed; s++) {
            for (i = 0; i < ns[s] && !e.failed; i++) {
                uint8_t cy[GBP_VSTATEDUMP_CYCLE_REC];
                if (!tabs[s]) { emit_zero(&e, GBP_VSTATEDUMP_CYCLE_REC); continue; }
                cycle_rec(cy, &tabs[s][i]);
                emit(&e, cy, GBP_VSTATEDUMP_CYCLE_REC);
            }
        }
    }
    if (!e.failed) {
        /* The one staging buffer this section needs, 1 KiB, static rather than on
         * the stack because this file's whole contract is "no large stack frames
         * in a probe that also owns a 7 MiB resident set". It is WRITE-ONLY and
         * derived: `semantic_block()` fills it from `st->sem` immediately before
         * the emit, so it is never a second source of truth for any counter, and
         * it is touched only here - after the teardown, on the user's keypress,
         * never during capture. Its 1 024 bytes are accounted for in
         * HARDWARE_TESTS §R3.15 as the symbol `sb.0`. */
        static uint8_t sb[GBP_VSTATEDUMP_SEMANTIC_SIZE];
        semantic_block(sb, &st->sem);
        emit(&e, sb, GBP_VSTATEDUMP_SEMANTIC_SIZE);
    }
    for (i = 0; i < info->diag_count && !e.failed; i++) {
        uint8_t dr[GBP_VSTATEDUMP_DIAG_REC_V4];
        diag_rec(dr, &st->diags[i]);
        emit(&e, dr, GBP_VSTATEDUMP_DIAG_REC_V4);
    }
    /* the preserved raw frames, streamed block by block straight out of the episode store */
    for (i = 0; i < info->episode_count && !e.failed; i++) {
        const struct gbp_vstate_episode *ep = &st->episodes[i];
        for (k = 0; k < ep->raw_frames && k < GBP_VSTATE_EPISODE_RAW_SLOTS && !e.failed; k++) {
            uint32_t b;
            for (b = 0; b < ep->raw_frame_blocks[k] && !e.failed; b++) {
                const uint8_t *p = gbp_vstate_episode_block(st, ep->raw_slot + k, b);
                if (!p) { e.failed = 1; break; }
                emit(&e, p, info->video_block_size);
            }
        }
    }
    if (!e.failed && st->audio.first_valid) emit(&e, gbp_vstate_audio_bytes(st, 0u), info->audio_block_size);
    if (!e.failed && st->audio.last_valid >= 0) emit(&e, gbp_vstate_audio_bytes(st, (unsigned)st->audio.last_valid), info->audio_block_size);

    if (!e.failed) {
        uint8_t foot[GBP_VSTATEDUMP_FOOTER_SIZE];
        memcpy(foot, GBP_VSTATEDUMP_END, 8);
        info->total_crc32 = gbp_crc32_final(e.crc);
        put_u32(foot + 8, info->total_crc32);
        /* the footer is not part of the CRC it carries */
        if (e.used + GBP_VSTATEDUMP_FOOTER_SIZE > e.cap) emit_flush(&e);
        if (!e.failed) {
            memcpy(e.chunk + e.used, foot, GBP_VSTATEDUMP_FOOTER_SIZE);
            e.used += GBP_VSTATEDUMP_FOOTER_SIZE;
        }
    }
    emit_flush(&e);
    if (written) *written = e.written;
    if (e.failed) return -4;
    return (long)e.written;
}

/* ---- parser ---------------------------------------------------------- */
static int reserved_zero(const uint8_t *p, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) if (p[i]) return 0;
    return 1;
}

static int id_load(char dst[GBP_VSTATEDUMP_ID_FIELD], const uint8_t *src)
{
    size_t i;
    int seen_nul = 0;
    for (i = 0; i < GBP_VSTATEDUMP_ID_FIELD; i++) {
        if (src[i] == 0) seen_nul = 1;
        else if (seen_nul) return -1;              /* bytes after the terminator: not a valid identity */
    }
    if (!seen_nul) return -1;                       /* never truncated: the field always ends in a NUL */
    memcpy(dst, src, GBP_VSTATEDUMP_ID_FIELD);
    return 0;
}

int gbp_vstatedump_parse(const uint8_t *in, size_t n, struct gbp_vstatedump_info *info,
                         const uint8_t **frames, const uint8_t **events, const uint8_t **episodes,
                         const uint8_t **cycles, const uint8_t **video_raw, const uint8_t **audio_raw)
{
    return gbp_vstatedump_parse_v3(in, n, info, frames, events, episodes, cycles, 0, video_raw, audio_raw);
}

int gbp_vstatedump_parse_v3(const uint8_t *in, size_t n, struct gbp_vstatedump_info *info,
                            const uint8_t **frames, const uint8_t **events, const uint8_t **episodes,
                            const uint8_t **cycles, const uint8_t **diag,
                            const uint8_t **video_raw, const uint8_t **audio_raw)
{
    return gbp_vstatedump_parse_v4(in, n, info, frames, events, episodes, cycles, 0, diag,
                                   video_raw, audio_raw);
}

/* v4 and v5 share one layout exactly; only the producer contract differs, so the
 * structural rules below are written once and asked this question instead of the
 * version number. */
static int has_semantic_block(uint16_t version)
{
    return version == GBP_VSTATEDUMP_VERSION_V4 || version == GBP_VSTATEDUMP_VERSION_V5;
}

/*
 * The one parser. THE FILE'S OWN VERSION DECIDES THE RULES - always, whichever
 * entry point was called: a v2 file is checked as v2, a v5 file as v5, and no
 * file is ever read under another version's contract. The four public entries
 * differ only in which sections they hand back.
 */
static int parse_core(const uint8_t *in, size_t n,
                      struct gbp_vstatedump_info *info,
                      const uint8_t **frames, const uint8_t **events, const uint8_t **episodes,
                      const uint8_t **cycles, const uint8_t **semantic, const uint8_t **diag,
                      const uint8_t **video_raw, const uint8_t **audio_raw)
{
    struct gbp_vstatedump_info d;
    uint64_t need;
    uint32_t i;
    if (!in || n < GBP_VSTATEDUMP_HEADER_SIZE + GBP_VSTATEDUMP_FOOTER_SIZE) return -1;
    if (memcmp(in, GBP_VSTATEDUMP_MAGIC, 8) != 0) return -1;
    memset(&d, 0, sizeof d);
    d.version = get_u16(in + 0x008);
    d.header_size = get_u16(in + 0x00A);
    /* Explicit dispatch, never a silent reinterpretation: v2 is the FROZEN physical format and v3
     * is v2 plus the diagnostic section. Any other version is refused here, before a single field
     * is read, so no file of one version can be parsed as another. */
    if ((d.version != GBP_VSTATEDUMP_VERSION_V2 && d.version != GBP_VSTATEDUMP_VERSION_V3 &&
         d.version != GBP_VSTATEDUMP_VERSION_V4 && d.version != GBP_VSTATEDUMP_VERSION_V5) ||
        d.header_size != GBP_VSTATEDUMP_HEADER_SIZE) return -2;
    if (get_u16(in + 0x02C) != GBP_VSTATEDUMP_FRAME_REC || get_u16(in + 0x02E) != GBP_VSTATEDUMP_EVENT_REC ||
        get_u16(in + 0x030) != GBP_VSTATEDUMP_EPISODE_REC || get_u16(in + 0x032) != GBP_VSTATEDUMP_CYCLE_REC) return -2;
    if (gbp_crc32(in, GBP_VSTATEDUMP_HEADER_SIZE - 4u) != get_u32(in + 0x1FC)) return -3;
    if (d.version == GBP_VSTATEDUMP_VERSION_V2) {
        /* v2: the whole 0x1E0..0x1FB area is reserved and must be zero, exactly as the physical
         * sidecar of 2026-09-16 has it. This check is what freezes the format. */
        if (!reserved_zero(in + 0x1E0, 0x1FCu - 0x1E0u)) return -8;
    } else if (d.version == GBP_VSTATEDUMP_VERSION_V3) {
        /* v3: FROZEN at one 96-byte record. Not one rule of it moves. */
        d.off_diag = get_u32(in + 0x1E0);
        d.diag_count = get_u32(in + 0x1E4);
        d.diag_rec_size = get_u16(in + 0x1E8);
        if (!reserved_zero(in + 0x1EA, 0x1FCu - 0x1EAu)) return -8;
        if (d.diag_count > 1u) return -9;                                   /* at most one record */
        if (d.diag_count && d.diag_rec_size != GBP_VSTATEDUMP_DIAG_REC) return -2;
        if (!d.diag_count && d.diag_rec_size != GBP_VSTATEDUMP_DIAG_REC && d.diag_rec_size != 0u) return -2;
    } else {
        /* v4 and v5: the same three fields with the same meanings, plus the block. */
        d.off_diag = get_u32(in + 0x1E0);
        d.diag_count = get_u32(in + 0x1E4);
        d.diag_rec_size = get_u16(in + 0x1E8);
        d.diag_flags = get_u16(in + 0x1EA);
        d.off_semantic = get_u32(in + 0x1EC);
        d.semantic_size = get_u32(in + 0x1F0);
        if (!reserved_zero(in + 0x1F4, 0x1FCu - 0x1F4u)) return -8;
        if (d.diag_count > GBP_VSTATEDUMP_MAX_DIAGS) return -9;
        if (d.diag_rec_size != GBP_VSTATEDUMP_DIAG_REC_V4) return -2;
        if (d.semantic_size != GBP_VSTATEDUMP_SEMANTIC_SIZE) return -2;
        if (d.diag_flags & (uint16_t)~GBP_VSTATEDUMP_DIAGF_ALL) return -8;  /* unknown flag bit */
    }

    d.flags = get_u32(in + 0x00C);
    d.tb_hz = get_u32(in + 0x010);
    d.frame_count = get_u32(in + 0x014);
    d.event_count = get_u32(in + 0x018);
    d.episode_count = get_u32(in + 0x01C);
    d.cycle_count = get_u32(in + 0x020);
    d.video_raw_frames = get_u32(in + 0x024);
    d.audio_raw_count = get_u32(in + 0x028);
    d.status_code = get_u16(in + 0x034);
    d.stop_reason = get_u16(in + 0x036);
    d.off_frames = get_u32(in + 0x038);
    d.off_events = get_u32(in + 0x03C);
    if (id_load(d.test_id, in + 0x040) || id_load(d.build_id, in + 0x060) ||
        id_load(d.app, in + 0x080) || id_load(d.commit, in + 0x0A0)) return -7;
    d.off_episodes = get_u32(in + 0x0C0);
    d.off_cycles = get_u32(in + 0x0C4);
    d.off_video_raw = get_u32(in + 0x0C8);
    d.off_audio_raw = get_u32(in + 0x0CC);
    d.off_footer = get_u32(in + 0x0D0);
    d.video_block_size = get_u32(in + 0x0D4);
    d.audio_block_size = get_u32(in + 0x0D8);
    d.frame_max_blocks = get_u32(in + 0x0DC);
    d.t_control_transform = get_u64(in + 0x0E0);
    d.t_capture_start = get_u64(in + 0x0E8);
    d.t_stop = get_u64(in + 0x0F0);
    d.capture_elapsed = get_u64(in + 0x0F8);
    d.baseline_elapsed = get_u64(in + 0x100);
    d.valid_observation_elapsed = get_u64(in + 0x108);
    d.valid_observation_at_target = get_u64(in + 0x110);
    d.safety_elapsed = get_u64(in + 0x118);
    d.min_valid_observation_ticks = get_u64(in + 0x120);
    d.hard_wallclock_ticks = get_u64(in + 0x128);
    d.t_teardown_begin = get_u64(in + 0x130);
    d.t_teardown_end = get_u64(in + 0x138);
    d.deliveries = get_u32(in + 0x140);
    d.video_completed = get_u32(in + 0x144);
    d.audio_drains = get_u32(in + 0x148);
    d.frames_complete = get_u32(in + 0x14C);
    d.frames_incomplete = get_u32(in + 0x150);
    d.resync_frames = get_u32(in + 0x154);
    d.anomalies_frame = get_u32(in + 0x158);
    d.anomalies_region = get_u32(in + 0x15C);
    d.boundaries_disc = get_u32(in + 0x160);
    d.boundaries_gbi = get_u32(in + 0x164);
    d.disagreements = get_u32(in + 0x168);
    d.episodes_opened = get_u32(in + 0x16C);
    d.stable_episodes = get_u32(in + 0x170);
    d.unstable_episodes = get_u32(in + 0x174);
    d.episodes_not_preserved = get_u32(in + 0x178);
    d.events_dropped = get_u32(in + 0x17C);
    d.event_seq_last = get_u32(in + 0x180);
    d.baseline_frame_index = get_u32(in + 0x184);
    d.t_baseline_valid = get_u64(in + 0x188);
    d.sig_samples = get_u64(in + 0x190);
    d.sig_sum = get_u64(in + 0x198);
    d.sig_min = get_u32(in + 0x1A0);
    d.sig_max = get_u32(in + 0x1A4);
    d.sig_median = get_u32(in + 0x1A8);
    d.sig_p95 = get_u32(in + 0x1AC);
    d.sig_overflow = get_u32(in + 0x1B0);
    d.tail_frames = get_u32(in + 0x1B4);
    d.tail_ticks = get_u64(in + 0x1B8);
    d.cyc_first_n = get_u32(in + 0x1C0);
    d.cyc_last_n = get_u32(in + 0x1C4);
    d.cyc_anomaly_n = get_u32(in + 0x1C8);
    d.cyc_episode_n = get_u32(in + 0x1CC);
    d.baseline_sig0 = get_u32(in + 0x1D0);
    d.baseline_sig39 = get_u32(in + 0x1D4);
    d.main_w1c = get_u32(in + 0x1D8);
    d.isr_w1c = get_u32(in + 0x1DC);
    d.header_crc32 = get_u32(in + 0x1FC);

    /* section bounds: monotone, inside the file, exactly the sizes the counts imply */
    if (d.off_frames != GBP_VSTATEDUMP_HEADER_SIZE) return -4;
    need = (uint64_t)d.off_frames + (uint64_t)d.frame_count * GBP_VSTATEDUMP_FRAME_REC;
    if (need != d.off_events) return -4;
    need += (uint64_t)d.event_count * GBP_VSTATEDUMP_EVENT_REC;
    if (need != d.off_episodes) return -4;
    need += (uint64_t)d.episode_count * GBP_VSTATEDUMP_EPISODE_REC;
    if (need != d.off_cycles) return -4;
    need += (uint64_t)d.cycle_count * GBP_VSTATEDUMP_CYCLE_REC;
    if (d.version == GBP_VSTATEDUMP_VERSION_V3) {
        if (need != d.off_diag) return -4;
        need += (uint64_t)d.diag_count * GBP_VSTATEDUMP_DIAG_REC;
    } else if (has_semantic_block(d.version)) {
        if (need != d.off_semantic) return -4;
        need += GBP_VSTATEDUMP_SEMANTIC_SIZE;
        if (need != d.off_diag) return -4;
        need += (uint64_t)d.diag_count * GBP_VSTATEDUMP_DIAG_REC_V4;
    }
    if (need != d.off_video_raw) return -4;
    if (d.cyc_first_n + d.cyc_last_n + d.cyc_anomaly_n + d.cyc_episode_n != d.cycle_count) return -9;
    if (d.off_video_raw > d.off_audio_raw || d.off_audio_raw > d.off_footer) return -4;
    if ((uint64_t)d.off_audio_raw + (uint64_t)d.audio_raw_count * d.audio_block_size != d.off_footer) return -4;
    if ((uint64_t)d.off_footer + GBP_VSTATEDUMP_FOOTER_SIZE != (uint64_t)n) return -1;   /* truncation / trailing bytes */
    /* the raw VIDEO section is the sum of the episodes' preserved frames */
    {
        uint64_t raw = 0;
        for (i = 0; i < d.episode_count; i++) {
            const uint8_t *r = in + d.off_episodes + (size_t)i * GBP_VSTATEDUMP_EPISODE_REC;
            uint32_t rf = get_u32(r + 0x1C);
            uint32_t k;
            if (rf > GBP_VSTATE_EPISODE_RAW_SLOTS) return -9;
            if (!reserved_zero(r + 0x1A0, GBP_VSTATEDUMP_EPISODE_REC - 0x1A0u)) return -8;
            for (k = 0; k < rf; k++) {
                uint32_t blocks = get_u32(r + 0x40 + k * 4u);
                if (blocks > d.frame_max_blocks) return -9;
                raw += (uint64_t)blocks * d.video_block_size;
            }
        }
        if ((uint64_t)d.off_video_raw + raw != (uint64_t)d.off_audio_raw) return -4;
    }
    if (memcmp(in + d.off_footer, GBP_VSTATEDUMP_END, 8) != 0) return -5;
    d.total_crc32 = get_u32(in + d.off_footer + 8);
    if (gbp_crc32(in, d.off_footer) != d.total_crc32) return -6;
    d.total_size = (uint64_t)n;

    if (info) *info = d;
    if (frames) *frames = in + d.off_frames;
    if (events) *events = in + d.off_events;
    if (episodes) *episodes = in + d.off_episodes;
    if (cycles) *cycles = in + d.off_cycles;
    /* Every record's reserved words obey the same rule as the header's reserved
     * area: zero, or the file is refused. A future field there is a new version,
     * never a silent reinterpretation. tools/vstate.py enforces exactly this, and
     * the two parsers must agree on what is valid. */
    if (d.version == GBP_VSTATEDUMP_VERSION_V3 && d.diag_count &&
        !reserved_zero(in + d.off_diag + 0x5Cu, GBP_VSTATEDUMP_DIAG_REC - 0x5Cu)) return -8;
    if (has_semantic_block(d.version)) {
        uint32_t vi;
        const uint8_t *sb = in + d.off_semantic;
        if (get_u32(sb + 0x000) != GBP_VSTATEDUMP_SEMANTIC_TAG) return -9;
        if (get_u16(sb + 0x004) != GBP_VSTATEDUMP_SEMANTIC_VERSION) return -2;
        if (get_u16(sb + 0x006) & (uint16_t)~GBP_VSTATEDUMP_DIAGF_ALL) return -8;
        if (!reserved_zero(sb + 0x05C, 0x070u - 0x05Cu)) return -8;
        for (vi = 0; vi < GBP_VSTATE_GAP_SLOTS; vi++) {
            const uint8_t *g = sb + 0x070 + 24u * vi;
            if (get_u16(g + 0x00) != gbp_vstate_gap_slot_bit(vi)) return -9;
            if (!reserved_zero(g + 0x02, 2u) || !reserved_zero(g + 0x14, 4u)) return -8;
            if (get_u32(g + 0x04) == 0u && get_u32(g + 0x08) != GBP_VSTATE_GAP_NONE) return -9;
        }
        for (vi = 0; vi < d.diag_count; vi++) {
            const uint8_t *r = in + d.off_diag + (size_t)vi * GBP_VSTATEDUMP_DIAG_REC_V4;
            uint16_t fl = get_u16(r + 0x6E);
            uint16_t cls = get_u16(r + 0x66);
            uint8_t fu = r[0x8C], fur = r[0x8D];
            if (!reserved_zero(r + 0x5C, 4u) || !reserved_zero(r + 0x9E, 2u)) return -8;
            /* DF_SERVICE_WRITTEN exists only in v5: a v4 file must still carry
             * zero in bits 8..15, exactly as the physical one does. */
            if (fl & (uint16_t)~(d.version == GBP_VSTATEDUMP_VERSION_V5 ?
                                 GBP_VSTATE_DF_ALL_V5 : GBP_VSTATE_DF_ALL)) return -8;
            if (cls < 1u || cls > 3u) return -9;
            if (fu == GBP_VSTATE_FU_PENDING || fu > GBP_VSTATE_FU_UNKNOWN) return -9;
            if (fur > GBP_VSTATE_FUR_INTERNAL) return -9;
            if (get_u16(r + 0x8E) != 0u && get_u16(r + 0x8E) != GBP_VSTATE_SRC_VIDEO &&
                get_u16(r + 0x8E) != GBP_VSTATE_SRC_AUDIO) return -9;
            if ((fl & GBP_VSTATE_DF_PAYLOAD_VALID) && get_u16(r + 0x8E) == 0u) return -9;
            if ((fl & GBP_VSTATE_DF_FOLLOWUP_FILLED) &&
                fu != GBP_VSTATE_FU_SOURCE_PRESENT_NEXT && fu != GBP_VSTATE_FU_SOURCE_ABSENT_NEXT) return -9;
            if (get_u16(r + 0x9C) == 0u && get_u32(r + 0x98) != GBP_VSTATE_GAP_NONE) return -9;
            /* ---- v5 ONLY: the cross-field invariants of §R4.8 ----
             * Everything below is RECOMPUTED from the 32 preserved bytes and
             * from the normative functions; not one of them trusts a stored
             * derived value. A v4 file never reaches here. */
            if (d.version == GBP_VSTATEDUMP_VERSION_V5) {
                const uint8_t *raw = r + 0x18;
                uint16_t disc = get_u16(r + 0x10), gbi = get_u16(r + 0x12);
                uint16_t kind = get_u16(r + 0x14);
                uint16_t auth = get_u16(r + 0x68), ack = get_u16(r + 0x6A);
                uint16_t svc = get_u16(r + 0x6C);
                uint16_t delta = get_u16(r + 0x60);
                uint16_t disc_x = get_u16(r + 0x62), maj_x = get_u16(r + 0x64);
                uint64_t t = get_u64(r + 0x00), t_ack = get_u64(r + 0x70);
                uint64_t t_rearm = get_u64(r + 0x78), t_next = get_u64(r + 0x80);
                uint16_t next_gbi = get_u16(r + 0x88);
                int selects = (kind == GBP_VSTATE_DIAG_READ_LEAN || kind == GBP_VSTATE_DIAG_READ_PRESVC);
                /* 1. both readings, from the bytes themselves */
                if (gbp_irq_value_disc(raw) != disc || gbp_irq_value_gbi(raw) != gbi) return -10;
                /* 2. every derived field, from those two */
                if (delta != (uint16_t)(disc ^ gbi)) return -10;
                if (disc_x != (uint16_t)((disc & GBP_VSTATE_SRC_MASK) & ~(gbi & GBP_VSTATE_SRC_MASK))) return -10;
                if (maj_x != (uint16_t)((gbi & GBP_VSTATE_SRC_MASK) & ~(disc & GBP_VSTATE_SRC_MASK))) return -10;
                if (cls != (uint16_t)gbp_vstate_classify(disc, gbi)) return -10;
                /* 3. the composed authoritative value: agreed outside SRC_MASK,
                 *    the majority inside it. This is the invariant the physical
                 *    v4 file fails in 22 of its 23 records. */
                if (auth != gbp_vstate_authoritative(disc, gbi)) return -10;
                /* 4. the service decision, and the zero that must not be ambiguous */
                if (fl & GBP_VSTATE_DF_SERVICE_WRITTEN) {
                    if (!selects) return -10;                       /* observational claims service */
                    if (svc != (uint16_t)(auth & GBP_VSTATE_AV_MASK)) return -10;
                } else if (svc != 0u) {
                    return -10;                                     /* a decision with no record of one */
                }
                /* 5. the ACK identity and its invalid encoding */
                if (fl & GBP_VSTATE_DF_ACK_WRITTEN) {
                    if (!(fl & GBP_VSTATE_DF_SERVICE_WRITTEN)) return -10;
                    if (ack != (uint16_t)(auth | GBP_VSTATE_BIT15_MASK)) return -10;
                    if (t_ack < t) return -10;
                } else if (ack != 0u || t_ack != 0u) {
                    return -10;             /* a plausible ACK without its flag */
                }
                /* 6. the re-arm: never before the ACK, invalid without its flag */
                if (fl & GBP_VSTATE_DF_REARM_WRITTEN) {
                    if (!(fl & GBP_VSTATE_DF_ACK_WRITTEN)) return -10;
                    if (t_rearm < t_ack) return -10;
                } else if (t_rearm != 0u) {
                    return -10;
                }
                /* 7. the follow-up, per source bit and against the majority only */
                if (fu == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT || fu == GBP_VSTATE_FU_SOURCE_ABSENT_NEXT) {
                    uint16_t absent = (uint16_t)(disc_x & ~(next_gbi & GBP_VSTATE_SRC_MASK));
                    if (!selects || disc_x == 0u) return -10;
                    if (!(fl & GBP_VSTATE_DF_REARM_WRITTEN)) return -10;  /* no re-arm, no next cause */
                    if (!(fl & GBP_VSTATE_DF_FOLLOWUP_FILLED)) return -10;
                    if (t_next < t_rearm) return -10;
                    if ((fu == GBP_VSTATE_FU_SOURCE_PRESENT_NEXT) != (absent == 0u)) return -10;
                } else {
                    /* no next cause was observed: the next fields stay at their
                     * invalid encoding, so nothing can be read out of them */
                    if (t_next != 0u || next_gbi != 0u || get_u16(r + 0x8A) != 0u) return -10;
                    if (fu == GBP_VSTATE_FU_NO_NEXT_CAUSE && !(fl & GBP_VSTATE_DF_REARM_WRITTEN)) return -10;
                }
                /* 8. the observational contract: it asserts nothing about service */
                if (!selects) {
                    if (fl & (GBP_VSTATE_DF_SERVICE_WRITTEN | GBP_VSTATE_DF_ACK_WRITTEN |
                              GBP_VSTATE_DF_REARM_WRITTEN | GBP_VSTATE_DF_PAYLOAD_VALID |
                              GBP_VSTATE_DF_PAYLOAD_SECOND | GBP_VSTATE_DF_FRAME_QUARANTINED |
                              GBP_VSTATE_DF_SOURCE_DEFERRED | GBP_VSTATE_DF_SERVICE_INCOMPLETE)) return -10;
                    if (fu != GBP_VSTATE_FU_UNKNOWN || fur != GBP_VSTATE_FUR_OBSERVATIONAL) return -10;
                }
                /* 9. the payload provenance, and the two markers */
                if (fl & GBP_VSTATE_DF_PAYLOAD_VALID) {
                    uint16_t psrc = get_u16(r + 0x8E);
                    if (!(fl & GBP_VSTATE_DF_SERVICE_WRITTEN)) return -10;
                    if ((psrc & maj_x) == 0u) return -10;           /* not a majority-extra source */
                    if ((psrc & svc) == 0u) return -10;             /* not actually serviced */
                    if ((fl & GBP_VSTATE_DF_PAYLOAD_SECOND) &&
                        (maj_x & GBP_VSTATE_AV_MASK) != GBP_VSTATE_AV_MASK) return -10;
                } else if (fl & GBP_VSTATE_DF_PAYLOAD_SECOND) {
                    return -10;
                }
                if ((fl & GBP_VSTATE_DF_FRAME_QUARANTINED) &&
                    !(maj_x & GBP_VSTATE_SRC_VIDEO)) return -10;
                if ((fl & GBP_VSTATE_DF_SOURCE_DEFERRED) &&
                    !(disc_x & GBP_VSTATE_SRC_VIDEO)) return -10;
                /* 10. a fatal class ends its transaction where it happened, so it
                 *     can never carry an ACK or a re-arm. */
                if (cls != GBP_VSTATE_DIS_SOURCE_SERVICED &&
                    (fl & (GBP_VSTATE_DF_ACK_WRITTEN | GBP_VSTATE_DF_REARM_WRITTEN))) return -10;
            }
        }
    }
    if (semantic) *semantic = has_semantic_block(d.version) ? in + d.off_semantic : 0;
    if (diag) *diag = ((d.version == GBP_VSTATEDUMP_VERSION_V3 || has_semantic_block(d.version)) &&
                       d.diag_count) ? in + d.off_diag : 0;
    if (video_raw) *video_raw = in + d.off_video_raw;
    if (audio_raw) *audio_raw = in + d.off_audio_raw;
    return 0;
}

int gbp_vstatedump_parse_v4(const uint8_t *in, size_t n, struct gbp_vstatedump_info *info,
                            const uint8_t **frames, const uint8_t **events, const uint8_t **episodes,
                            const uint8_t **cycles, const uint8_t **semantic, const uint8_t **diag,
                            const uint8_t **video_raw, const uint8_t **audio_raw)
{
    return parse_core(in, n, info, frames, events, episodes, cycles,
                      semantic, diag, video_raw, audio_raw);
}

int gbp_vstatedump_parse_v5(const uint8_t *in, size_t n, struct gbp_vstatedump_info *info,
                            const uint8_t **frames, const uint8_t **events, const uint8_t **episodes,
                            const uint8_t **cycles, const uint8_t **semantic, const uint8_t **diag,
                            const uint8_t **video_raw, const uint8_t **audio_raw)
{
    return parse_core(in, n, info, frames, events, episodes, cycles,
                      semantic, diag, video_raw, audio_raw);
}

void gbp_vstatedump_decode_frame(const uint8_t *rec, struct gbp_vstate_frame *out)
{
    unsigned i;
    memset(out, 0, sizeof *out);
    out->t_first_block = get_u64(rec + 0x00);
    out->t_last_block = get_u64(rec + 0x08);
    out->index = get_u32(rec + 0x10);
    out->episode = get_u32(rec + 0x14);
    out->blocks = get_u16(rec + 0x18);
    out->flags = get_u16(rec + 0x1A);
    out->disagreements = get_u16(rec + 0x1C);
    out->completeness = get_u16(rec + 0x1E);
    for (i = 0; i < GBP_VSTATE_FRAME_SIGS; i++) out->sig[i] = get_u32(rec + 0x20 + i * 4u);
}

void gbp_vstatedump_decode_event(const uint8_t *rec, struct gbp_vstate_event *out)
{
    memset(out, 0, sizeof *out);
    out->t = get_u64(rec + 0x00);
    out->seq = get_u32(rec + 0x08);
    out->type = get_u16(rec + 0x0C);
    out->flags = get_u16(rec + 0x0E);
    out->a = get_u32(rec + 0x10);
    out->b = get_u32(rec + 0x14);
    out->c = get_u32(rec + 0x18);
    out->d = get_u32(rec + 0x1C);
    out->frame = get_u32(rec + 0x20);
    out->episode = get_u32(rec + 0x24);
    out->e = get_u32(rec + 0x28);
    out->f = get_u32(rec + 0x2C);
    out->t2 = get_u64(rec + 0x30);
    out->g = get_u32(rec + 0x38);
    out->h = get_u32(rec + 0x3C);
}

void gbp_vstatedump_decode_episode(const uint8_t *rec, struct gbp_vstate_episode *out, uint32_t raw_offset[GBP_VSTATE_EPISODE_RAW_SLOTS])
{
    unsigned i;
    memset(out, 0, sizeof *out);
    out->index = get_u32(rec + 0x00);
    out->state = get_u32(rec + 0x04);
    out->flags = get_u32(rec + 0x08);
    out->open_frame = get_u32(rec + 0x0C);
    out->close_frame = get_u32(rec + 0x10);
    out->frames = get_u32(rec + 0x14);
    out->stable_count = get_u32(rec + 0x18);
    out->raw_frames = get_u32(rec + 0x1C);
    out->t_open = get_u64(rec + 0x20);
    out->t_close = get_u64(rec + 0x28);
    for (i = 0; i < GBP_VSTATE_EPISODE_RAW_SLOTS; i++) {
        out->raw_frame_index[i] = get_u32(rec + 0x30 + i * 4u);
        out->raw_frame_blocks[i] = get_u32(rec + 0x40 + i * 4u);
        if (raw_offset) raw_offset[i] = get_u32(rec + 0x50 + i * 4u);
    }
    for (i = 0; i < GBP_VSTATE_FRAME_SIGS; i++) {
        out->candidate[i] = get_u32(rec + 0x60 + i * 4u);
        out->final_sig[i] = get_u32(rec + 0x100 + i * 4u);
    }
}

void gbp_vstatedump_decode_cycle(const uint8_t *rec, struct gbp_vstate_cycle *out)
{
    memset(out, 0, sizeof *out);
    out->t_cause = get_u64(rec + 0x00);
    out->t_unmask = get_u64(rec + 0x08);
    out->t_entry = get_u64(rec + 0x10);
    out->t_read = get_u64(rec + 0x18);
    out->t_ack = get_u64(rec + 0x20);
    out->t_rearm = get_u64(rec + 0x28);
    out->t_next = get_u64(rec + 0x30);
    out->index = get_u32(rec + 0x38);
    out->frame_index = get_u32(rec + 0x3C);
    out->pending = get_u16(rec + 0x40);
    out->ack_value = get_u16(rec + 0x42);
    out->kind = get_u16(rec + 0x44);
    out->flags = get_u16(rec + 0x46);
    out->audio_selected = rec[0x48]; out->audio_completed = rec[0x49];
    out->video_selected = rec[0x4A]; out->video_completed = rec[0x4B];
    out->main_w1c = rec[0x4C]; out->isr_count = rec[0x4D];
    out->isr_reentry = rec[0x4E]; out->next_observed = rec[0x4F];
    out->latency_ticks = get_u32(rec + 0x50);
    out->audio_wait = get_u32(rec + 0x54);
    out->video_wait = get_u32(rec + 0x58);
    out->sig_ticks = get_u32(rec + 0x5C);
    out->intsr_entry = get_u32(rec + 0x60);
    out->intsr_after_w1c = get_u32(rec + 0x64);
    out->intsr_postack = get_u32(rec + 0x68);
    out->intsr_next = get_u32(rec + 0x6C);
    out->block_in_frame = get_u32(rec + 0x70);
    out->rc = get_u32(rec + 0x74);
}
