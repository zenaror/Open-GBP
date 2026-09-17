#include "gbp_vstatedump.h"

#include <string.h>
#include "gbp_crc32.h"

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
    info->off_video_raw = (uint32_t)off;
    off += raw_bytes;
    info->off_audio_raw = (uint32_t)off;
    off += (uint64_t)info->audio_raw_count * info->audio_block_size;
    info->off_footer = (uint32_t)off;
    off += GBP_VSTATEDUMP_FOOTER_SIZE;
    info->total_size = off;
    if (off > 0xFFFFFFFFu) return -1;
    if (info->off_frames > info->off_events || info->off_events > info->off_episodes ||
        info->off_episodes > info->off_cycles || info->off_cycles > info->off_video_raw ||
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
    /* 0x1E0..0x1FB reserved, already zero */
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
    struct gbp_vstatedump_info d;
    uint64_t need;
    uint32_t i;
    if (!in || n < GBP_VSTATEDUMP_HEADER_SIZE + GBP_VSTATEDUMP_FOOTER_SIZE) return -1;
    if (memcmp(in, GBP_VSTATEDUMP_MAGIC, 8) != 0) return -1;
    memset(&d, 0, sizeof d);
    d.version = get_u16(in + 0x008);
    d.header_size = get_u16(in + 0x00A);
    if (d.version != GBP_VSTATEDUMP_VERSION || d.header_size != GBP_VSTATEDUMP_HEADER_SIZE) return -2;
    if (get_u16(in + 0x02C) != GBP_VSTATEDUMP_FRAME_REC || get_u16(in + 0x02E) != GBP_VSTATEDUMP_EVENT_REC ||
        get_u16(in + 0x030) != GBP_VSTATEDUMP_EPISODE_REC || get_u16(in + 0x032) != GBP_VSTATEDUMP_CYCLE_REC) return -2;
    if (gbp_crc32(in, GBP_VSTATEDUMP_HEADER_SIZE - 4u) != get_u32(in + 0x1FC)) return -3;
    if (!reserved_zero(in + 0x1E0, 0x1FCu - 0x1E0u)) return -8;

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
    if (video_raw) *video_raw = in + d.off_video_raw;
    if (audio_raw) *audio_raw = in + d.off_audio_raw;
    return 0;
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
