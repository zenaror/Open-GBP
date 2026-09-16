/*
 * gbp_avseq / gbp_avseqdump: the records, buffers, predicates, boundaries
 * and the OGBPSEQ1 sidecar of GBP-VIDEO-001, on the host, with synthetic
 * data only (nothing here is physical evidence).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_avseq.h"
#include "gbp_avseqdump.h"
#include "gbp_crc32.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static uint8_t video_raw[GBP_AVSEQ_VIDEO_RAW_BYTES] __attribute__((aligned(32)));
static uint8_t audio_raw[GBP_AVSEQ_AUDIO_RAW_BYTES] __attribute__((aligned(32)));
static struct gbp_avseq_store store;
static uint8_t dump[GBP_AVSEQDUMP_MAX_SIZE];
static uint8_t dump2[GBP_AVSEQDUMP_MAX_SIZE];
#define LINES 64
#define LINE_LEN 256
static char storage[LINES * LINE_LEN];
#define L(i) (ringlog_line(&rl, (i)) + 7)   /* past the "NNNNNN " record-number prefix */

static void put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static uint32_t get32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }

static void fill_video_slot(unsigned seq, uint8_t b0, uint8_t b1)
{
    uint8_t *b = video_raw + seq * GBP_AVSEQ_VIDEO_BLOCK_SIZE;
    uint32_t k;
    for (k = 0; k < GBP_AVSEQ_VIDEO_BLOCK_SIZE; k += 4u) { b[k] = 0x7f; b[k + 1u] = 0x7f; b[k + 2u] = (uint8_t)(0xf0 | (seq & 0xf)); b[k + 3u] = b[k + 2u]; }
    b[0] = b0; b[1] = b1; b[2] = 0xff; b[3] = 0xff;
}

static struct gbp_xfer_info info_ok(void)
{
    struct gbp_xfer_info i; memset(&i, 0, sizeof i); i.ticks = 2400; i.polls = 120; i.dma_status_before = 0x0000; i.dma_status = 0x0020; return i;
}

static void test_predicates(void)
{
    unsigned a, b;
    uint8_t f4[4] = { 0xff, 0xff, 0xff, 0xff };
    CHECK(gbp_avseq_flag_gbi(f4) == 1 && gbp_avseq_flag_disc(f4) == 1);
    f4[0] = 0x7f; CHECK(gbp_avseq_flag_gbi(f4) == 0 && gbp_avseq_flag_disc(f4) == 1);   /* byte 1 only: Disc sees a frame start, GBI does not */
    f4[0] = 0xff; f4[1] = 0x7f; CHECK(gbp_avseq_flag_gbi(f4) == 0 && gbp_avseq_flag_disc(f4) == 0);   /* byte 0 alone never decides */
    f4[0] = 0x7f; CHECK(gbp_avseq_flag_gbi(f4) == 0 && gbp_avseq_flag_disc(f4) == 0);
    f4[0] = 0x80; f4[1] = 0x80; CHECK(gbp_avseq_flag_gbi(f4) == 1 && gbp_avseq_flag_disc(f4) == 1);   /* only bit 7 matters */
    /* GBI = 1 implies Disc = 1 for every byte pair (bytes 2/3 irrelevant) */
    for (a = 0; a < 256; a++) for (b = 0; b < 256; b++) {
        uint8_t g[4]; g[0] = (uint8_t)a; g[1] = (uint8_t)b; g[2] = (uint8_t)(a ^ b); g[3] = (uint8_t)~a;
        if (gbp_avseq_flag_gbi(g) && !gbp_avseq_flag_disc(g)) { CHECK(0); return; }
        if (gbp_avseq_flag_gbi(g) != (((a & 0x80) && (b & 0x80)) ? 1 : 0)) { CHECK(0); return; }
        if (gbp_avseq_flag_disc(g) != ((b & 0x80) ? 1 : 0)) { CHECK(0); return; }
    }
    CHECK(1);
}

static void test_video_slots(void)
{
    unsigned i;
    struct gbp_xfer_info inf = info_ok();
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    CHECK(store.cycles_n == 0 && store.vblocks_n == 0 && store.ablocks_n == 0 && store.audio_last_valid == -1 && store.audio_last_next == 8u);
    for (i = 0; i < GBP_AVSEQ_MAX_VIDEO_BLOCKS; i++) {
        uint8_t *buf = gbp_avseq_video_target(&store);
        struct gbp_avseq_vblock *v;
        CHECK(buf == video_raw + i * GBP_AVSEQ_VIDEO_BLOCK_SIZE);          /* contiguous, in sequence order */
        v = gbp_avseq_video_commit(&store, i * 2u, 0x0100, GBP_OK, &inf, 1000u + i, 1500u + i);
        CHECK(v && v->seq == i && v->cycle == i * 2u && v->completed == 1 && v->rc == 0 && v->wait_ticks == 2400u && v->polls == 120u && v->csr_after == 0x0020);
        CHECK(store.vblocks_n == i + 1u);
    }
    CHECK(gbp_avseq_video_target(&store) == 0);                             /* the 89th DMA has no slot: never started */
    CHECK(gbp_avseq_video_commit(&store, 200, 0x0100, GBP_OK, &inf, 1, 2) == 0);
    CHECK(gbp_avseq_video_bytes(&store, 87) == video_raw + 87u * GBP_AVSEQ_VIDEO_BLOCK_SIZE && gbp_avseq_video_bytes(&store, 88) == 0);
    /* a failed DMA consumes its slot with completed = 0 (the loop stops; the slot is never reused) */
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    CHECK(gbp_avseq_video_target(&store) == video_raw);
    {
        struct gbp_avseq_vblock *v = gbp_avseq_video_commit(&store, 3, 0x0500, GBP_ERR_TIMEOUT, &inf, 10, 20);
        CHECK(v && v->completed == 0 && v->rc == (uint8_t)GBP_ERR_TIMEOUT && store.vblocks_n == 1u);
    }
    /* a store with a too-small buffer refuses the DMA before it starts */
    gbp_avseq_store_init(&store, video_raw, GBP_AVSEQ_VIDEO_BLOCK_SIZE * 2u, audio_raw, sizeof audio_raw);
    CHECK(gbp_avseq_video_target(&store) != 0);
    gbp_avseq_video_commit(&store, 0, 0x0100, GBP_OK, &inf, 1, 2);
    gbp_avseq_video_commit(&store, 1, 0x0100, GBP_OK, &inf, 3, 4);
    CHECK(gbp_avseq_video_target(&store) == 0);
}

static void test_audio_pingpong(void)
{
    unsigned i, slot = 99;
    struct gbp_xfer_info inf = info_ok();
    struct gbp_avseq_ablock *a;
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    for (i = 0; i < GBP_AVSEQ_AUDIO_FIRST_KEPT; i++) {
        uint8_t *buf = gbp_avseq_audio_target(&store, &slot);
        CHECK(buf == audio_raw + i * GBP_AVSEQ_AUDIO_BLOCK_SIZE && slot == i);
        memset(buf, (int)(0x10 + i), GBP_AVSEQ_AUDIO_BLOCK_SIZE);
        a = gbp_avseq_audio_commit(&store, i, slot, GBP_OK, &inf, 100u * i, 100u * i + 50u);
        CHECK(a && a->completed && a->slot == i && a->raw_kept == 1 && a->raw_index == i);
    }
    CHECK(store.audio_first_kept == 8u && gbp_avseq_audio_raw_count(&store) == 8u && store.audio_last_valid == -1);
    /* 9th: ping-pong slot 8 */
    CHECK(gbp_avseq_audio_target(&store, &slot) == audio_raw + 8u * GBP_AVSEQ_AUDIO_BLOCK_SIZE && slot == 8u);
    memset(audio_raw + 8u * GBP_AVSEQ_AUDIO_BLOCK_SIZE, 0xA8, GBP_AVSEQ_AUDIO_BLOCK_SIZE);
    a = gbp_avseq_audio_commit(&store, 8, slot, GBP_OK, &inf, 800, 850);
    CHECK(a && a->completed && a->slot == (GBP_AVSEQ_SLOT_LAST | 0u) && a->raw_index == 8u && a->raw_kept == 1);
    CHECK(store.audio_last_valid == 8 && store.audio_last_next == 9u && gbp_avseq_audio_raw_count(&store) == 9u);
    /* 10th: slot 9; last valid moves */
    CHECK(gbp_avseq_audio_target(&store, &slot) == audio_raw + 9u * GBP_AVSEQ_AUDIO_BLOCK_SIZE && slot == 9u);
    memset(audio_raw + 9u * GBP_AVSEQ_AUDIO_BLOCK_SIZE, 0xA9, GBP_AVSEQ_AUDIO_BLOCK_SIZE);
    a = gbp_avseq_audio_commit(&store, 9, slot, GBP_OK, &inf, 900, 950);
    CHECK(a && a->slot == (GBP_AVSEQ_SLOT_LAST | 1u) && a->raw_index == 9u && store.audio_last_valid == 9 && store.audio_last_next == 8u);
    /* 11th FAILS into slot 8: the last valid capture (slot 9) is untouched and stays the last valid one; the next target is still 8 */
    CHECK(gbp_avseq_audio_target(&store, &slot) == audio_raw + 8u * GBP_AVSEQ_AUDIO_BLOCK_SIZE && slot == 8u);
    a = gbp_avseq_audio_commit(&store, 10, slot, GBP_ERR_TIMEOUT, &inf, 1000, 1010);
    CHECK(a && a->completed == 0 && a->slot == GBP_AVSEQ_SLOT_NONE && a->raw_index == 0xFFFFu && a->raw_kept == 0);
    CHECK(store.audio_last_valid == 9 && store.audio_last_next == 8u && audio_raw[9u * GBP_AVSEQ_AUDIO_BLOCK_SIZE] == 0xA9);
    CHECK(gbp_avseq_audio_raw_count(&store) == 9u && store.audio_drains_completed == 10u);
    /* 12th succeeds into slot 8: last valid = 8 */
    CHECK(gbp_avseq_audio_target(&store, &slot) != 0 && slot == 8u);
    memset(audio_raw + 8u * GBP_AVSEQ_AUDIO_BLOCK_SIZE, 0xB8, GBP_AVSEQ_AUDIO_BLOCK_SIZE);
    a = gbp_avseq_audio_commit(&store, 11, slot, GBP_OK, &inf, 1100, 1150);
    CHECK(a && a->raw_index == 8u && store.audio_last_valid == 8 && store.audio_last_next == 9u);
    /* summaries: the first 8 kept; the 9th (slot 8) was overwritten by the 12th → raw_kept 0; the 10th (slot 9) is not the last valid → raw_kept 0 */
    gbp_avseq_summarize(&store);
    CHECK(store.ablocks[0].summarized && store.ablocks[0].crc32 == gbp_crc32(audio_raw, GBP_AVSEQ_AUDIO_BLOCK_SIZE) && store.ablocks[0].first_word == 0x10101010u);
    CHECK(store.ablocks[7].summarized && store.ablocks[7].nonzero == GBP_AVSEQ_AUDIO_BLOCK_SIZE && store.ablocks[7].unit0_nonzero == GBP_AVSEQ_AUDIO_BLOCK_SIZE / 32u);
    CHECK(store.ablocks[8].raw_kept == 0 && store.ablocks[8].summarized == 0);
    CHECK(store.ablocks[9].raw_kept == 0 && store.ablocks[9].summarized == 0);
    CHECK(store.ablocks[10].raw_kept == 0 && store.ablocks[10].completed == 0);
    CHECK(store.ablocks[11].raw_kept == 1 && store.ablocks[11].summarized == 1 && store.ablocks[11].first_word == 0xB8B8B8B8u);
    CHECK(store.ablocks_n == 12u);
}

static void test_summaries_and_boundaries(void)
{
    unsigned i;
    struct gbp_xfer_info inf = info_ok();
    struct gbp_avseq_boundaries bg, bd;
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    /* 88 blocks: GBI+Disc flag at 0, 40, 80; Disc-only at 20; byte-0-only at 60 (both 0); a failed DMA at seq 30 (not counted) */
    for (i = 0; i < GBP_AVSEQ_MAX_VIDEO_BLOCKS; i++) {
        uint8_t b0 = 0x7f, b1 = 0x7f;
        gbp_status rc = (i == 30u) ? GBP_ERR_BUSY : GBP_OK;
        if (i == 0u || i == 40u || i == 80u) { b0 = 0xff; b1 = 0xff; }
        if (i == 20u) { b1 = 0xff; }
        if (i == 60u) { b0 = 0xff; }
        fill_video_slot(i, b0, b1);
        gbp_avseq_video_target(&store);
        gbp_avseq_video_commit(&store, i, 0x0100, rc, &inf, 10u * i, 10u * i + 5u);
    }
    gbp_avseq_summarize(&store);
    CHECK(store.vblocks[0].summarized && store.vblocks[0].flag_gbi == 1 && store.vblocks[0].flag_disc == 1 && store.vblocks[0].flags_agree == 1);
    CHECK(store.vblocks[1].flag_gbi == 0 && store.vblocks[1].flag_disc == 0 && store.vblocks[1].flags_agree == 1);
    CHECK(store.vblocks[20].flag_gbi == 0 && store.vblocks[20].flag_disc == 1 && store.vblocks[20].flags_agree == 0);
    CHECK(store.vblocks[60].flag_gbi == 0 && store.vblocks[60].flag_disc == 0 && store.vblocks[60].flags_agree == 1);   /* byte 0 never decides */
    CHECK(store.vblocks[30].summarized == 0 && store.vblocks[30].completed == 0 && store.vblocks[30].crc32 == 0);
    CHECK(store.vblocks[0].raw_first4[0] == 0xff && store.vblocks[0].raw_first4[1] == 0xff && store.vblocks[0].raw_first4[2] == 0xff && store.vblocks[0].raw_first4[3] == 0xff);
    CHECK(store.vblocks[1].byte0_exceptions == 0 && store.vblocks[1].undoubled_words == 0);
    CHECK(store.vblocks[20].byte0_exceptions == 1 && store.vblocks[20].undoubled_words == 1);   /* only its first word differs */
    CHECK(store.vblocks[5].crc32 == gbp_crc32(video_raw + 5u * GBP_AVSEQ_VIDEO_BLOCK_SIZE, GBP_AVSEQ_VIDEO_BLOCK_SIZE));
    for (i = 0; i < GBP_AVSEQ_MAX_VIDEO_BLOCKS; i++) if (store.vblocks[i].flag_gbi && !store.vblocks[i].flag_disc) { CHECK(0); break; }
    gbp_avseq_boundaries(&store, 0, &bg);
    gbp_avseq_boundaries(&store, 1, &bd);
    CHECK(bg.count == 3 && bg.positions[0] == 0 && bg.positions[1] == 40 && bg.positions[2] == 80 && bg.intervals_n == 2 && bg.intervals[0] == 40 && bg.intervals[1] == 40 && bg.complete_interval == 1);
    CHECK(bd.count == 4 && bd.positions[0] == 0 && bd.positions[1] == 20 && bd.positions[2] == 40 && bd.positions[3] == 80 && bd.intervals_n == 3);
    CHECK(bd.intervals[0] == 20 && bd.intervals[1] == 20 && bd.intervals[2] == 40 && bd.complete_interval == 1);
    /* one boundary only: no complete interval; none: count 0 */
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    for (i = 0; i < 10; i++) { fill_video_slot(i, i == 3u ? 0xff : 0x7f, i == 3u ? 0xff : 0x7f); gbp_avseq_video_target(&store); gbp_avseq_video_commit(&store, i, 0x0100, GBP_OK, &inf, 0, 1); }
    gbp_avseq_summarize(&store);
    gbp_avseq_boundaries(&store, 0, &bg);
    CHECK(bg.count == 1 && bg.positions[0] == 3 && bg.intervals_n == 0 && bg.complete_interval == 0);
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    gbp_avseq_boundaries(&store, 1, &bd);
    CHECK(bd.count == 0 && bd.intervals_n == 0 && bd.complete_interval == 0);
}

static struct gbp_avseq_cycle cycle_sample(unsigned n)
{
    struct gbp_avseq_cycle c;
    gbp_avseq_cycle_init(&c, n);
    c.pending = (uint16_t)((n & 1u) ? 0x0100 : 0x0500);
    c.irq_byte0 = (uint8_t)(0x05 + n); c.irq_off2_g0 = 0xaa;
    c.verify = (uint8_t)(n < 4u); c.end_reason = (uint8_t)((n == 9u) ? GBP_AVSEQ_END_TARGET_REACHED : 0);
    c.audio_selected = (uint8_t)((n & 1u) ? 0 : 1); c.audio_attempted = c.audio_selected; c.audio_completed = c.audio_selected; c.audio_rc = 0;
    c.audio_slot = (uint8_t)(c.audio_selected ? (n / 2u) : GBP_AVSEQ_SLOT_NONE);
    c.video_selected = 1; c.video_attempted = 1; c.video_completed = 1; c.video_rc = 0; c.video_seq = (uint16_t)n;
    c.ack_attempted = 1; c.ack_completed = 1; c.rearm_attempted = 1; c.rearm_completed = 1;
    c.main_w1c = (uint8_t)(n == 2u); c.pi_sticky = 0; c.relatch_postack = (uint8_t)(n == 2u); c.relatch_postdrain = 0;
    c.next_observed = 1; c.next_ended_by = GBP_AVSEQ_NEXT_CAUSE;
    c.isr_fired = 1; c.isr_count = 1; c.isr_reentry = 0; c.admitted = 1;
    c.ack_value = (uint16_t)(c.pending | 0x8000); c.next_pending = 0x0400;
    c.t_adm = 0xF0000000u + n; c.t_cause = 0xF0000010u + n; c.t_unmask = 0xF0000020u + n; c.t_post_unmask = 0xF0000021u + n;
    c.t_entry = 0xF0000030u + n; c.latency = 16u + n; c.t_read = 0xF0000040u + n;
    c.t_audio_start = 0xF0000050u + n; c.t_audio_end = 0xF0000060u + n; c.t_video_start = 0xF0000070u + n; c.t_video_end = 0xF0000080u + n;
    c.t_ack_after = 0xF0000090u + n; c.t_rearm = 0xF00000A0u + n; c.t_rearm_after = 0xF00000A1u + n; c.t_next = 0xF00000B0u + n;
    c.intsr_entry = 0x00012000u; c.intmr_entry = 0x000021fau; c.intsr_after_w1c = 0x00010000u;
    c.intsr_prep = 0x00012000u; c.intmr_prep = 0x000001fau;
    c.intsr_postack = 0x00010000u; c.intmr_postack = 0x000001fau; c.intsr_after_main_w1c = 0x00010000u; c.intsr_next = 0x00012000u;
    c.audio_crc32 = c.audio_selected ? 0xC0DE0000u + n : 0u; c.audio_wait = 2475; c.video_wait = 2319; c.audio_polls = 128; c.video_polls = 120;
    memset(c.irq_raw, (int)(0x30 + n), sizeof c.irq_raw);
    c.irq_rc = GBP_OK; c.irq_disc = c.pending; c.irq_gbi = c.pending;
    return c;
}

static void build_store(unsigned cycles, unsigned videos, unsigned audios)
{
    unsigned i;
    struct gbp_xfer_info inf = info_ok();
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    for (i = 0; i < cycles; i++) { store.cycles[i] = cycle_sample(i); }
    store.cycles_n = cycles;
    for (i = 0; i < videos; i++) {
        fill_video_slot(i, (i % 40u) == 0u ? 0xff : 0x7f, (i % 40u) == 0u ? 0xff : 0x7f);
        gbp_avseq_video_target(&store);
        gbp_avseq_video_commit(&store, i, 0x0100, (i == 30u && videos > 31u) ? GBP_ERR_TIMEOUT : GBP_OK, &inf, 100u * i, 100u * i + 40u);
    }
    for (i = 0; i < audios; i++) {
        unsigned slot;
        uint8_t *buf = gbp_avseq_audio_target(&store, &slot);
        memset(buf, (int)(0x40 + i), GBP_AVSEQ_AUDIO_BLOCK_SIZE);
        gbp_avseq_audio_commit(&store, i * 2u, slot, (i == 10u && audios > 11u) ? GBP_ERR_BUSY : GBP_OK, &inf, 7u * i, 7u * i + 3u);
    }
    gbp_avseq_summarize(&store);
}

static void check_cycle_eq(const struct gbp_avseq_cycle *a, const struct gbp_avseq_cycle *b)
{
    CHECK(a->idx == b->idx && a->pending == b->pending && a->irq_byte0 == b->irq_byte0 && a->irq_off2_g0 == b->irq_off2_g0 && a->verify == b->verify && a->end_reason == b->end_reason);
    CHECK(a->audio_selected == b->audio_selected && a->audio_attempted == b->audio_attempted && a->audio_completed == b->audio_completed && a->audio_rc == b->audio_rc && a->audio_slot == b->audio_slot);
    CHECK(a->video_selected == b->video_selected && a->video_attempted == b->video_attempted && a->video_completed == b->video_completed && a->video_rc == b->video_rc && a->video_seq == b->video_seq);
    CHECK(a->ack_attempted == b->ack_attempted && a->ack_completed == b->ack_completed && a->rearm_attempted == b->rearm_attempted && a->rearm_completed == b->rearm_completed);
    CHECK(a->main_w1c == b->main_w1c && a->pi_sticky == b->pi_sticky && a->relatch_postack == b->relatch_postack && a->next_observed == b->next_observed && a->next_ended_by == b->next_ended_by);
    CHECK(a->isr_fired == b->isr_fired && a->isr_count == b->isr_count && a->isr_reentry == b->isr_reentry && a->admitted == b->admitted && a->ack_value == b->ack_value);
    CHECK(a->t_cause == b->t_cause && a->t_unmask == b->t_unmask && a->t_entry == b->t_entry && a->latency == b->latency && a->t_read == b->t_read);
    CHECK(a->t_audio_start == b->t_audio_start && a->t_audio_end == b->t_audio_end && a->t_video_start == b->t_video_start && a->t_video_end == b->t_video_end);
    CHECK(a->t_ack_after == b->t_ack_after && a->t_rearm == b->t_rearm && a->t_rearm_after == b->t_rearm_after && a->t_next == b->t_next);
    CHECK(a->intsr_entry == b->intsr_entry && a->intmr_entry == b->intmr_entry && a->intsr_after_w1c == b->intsr_after_w1c && a->intsr_postack == b->intsr_postack && a->intsr_next == b->intsr_next);
    CHECK(a->audio_crc32 == b->audio_crc32);
}

static void test_sidecar_roundtrip(void)
{
    struct gbp_avseqdump_info info, pinfo;
    const uint8_t *cyc, *vt, *at, *vr, *ar;
    long n;
    unsigned i, stored;
    build_store(12, 12, 6);
    memset(&info, 0, sizeof info);
    CHECK(gbp_avseqdump_set_identity(&info, "GBP-VIDEO-001", "video-0001", "gbp-video-capture-probe", "abcdef0") == 0);
    info.flags = GBP_AVSEQDUMP_FLAG_SERVICE_OK | GBP_AVSEQDUMP_FLAG_RESTORE_OK | GBP_AVSEQDUMP_FLAG_NEXT_CAUSE_AT_END;
    info.tb_hz = 40500000u; info.capture_result = GBP_AVSEQ_END_TARGET_REACHED; info.status_code = 0; info.end_reason = GBP_AVSEQ_END_TARGET_REACHED;
    info.target_video_blocks = 88; info.max_deliveries = 320; info.admission_budget_ticks = 40500000u; info.t0 = 0xFFFFFF00u; info.admission_deadline = 0xFFFFFF00u + 40500000u;
    info.boundaries_gbi = 1; info.boundaries_disc = 1;
    CHECK(gbp_avseqdump_size(&store) == GBP_AVSEQDUMP_HEADER_SIZE + 12u * GBP_AVSEQDUMP_CYCLE_REC + 12u * GBP_AVSEQDUMP_VIDEO_REC + 6u * GBP_AVSEQDUMP_AUDIO_REC +
                                        12u * GBP_AVSEQ_VIDEO_BLOCK_SIZE + 6u * GBP_AVSEQ_AUDIO_BLOCK_SIZE + GBP_AVSEQDUMP_FOOTER_SIZE);
    n = gbp_avseqdump_serialize(&info, &store, dump, sizeof dump);
    CHECK(n == (long)gbp_avseqdump_size(&store));
    CHECK(memcmp(dump, "OGBPSEQ1", 8) == 0 && memcmp(dump + info.off_footer, "OGBPEND1", 8) == 0);
    CHECK(info.cycle_count == 12 && info.video_count == 12 && info.audio_count == 6 && info.audio_raw_count == 6 && info.video_raw_stored == 12);
    CHECK(info.header_crc32 == gbp_crc32(dump, 0xFCu) && info.total_crc32 == gbp_crc32(dump, info.off_footer) && get32(dump + info.off_footer + 8) == info.total_crc32);
    for (i = 0; i < 12; i++) CHECK(dump[0xF0 + i] == 0);                    /* reserved zero */
    /* parse back */
    CHECK(gbp_avseqdump_parse(dump, (size_t)n, &pinfo, &cyc, &vt, &at, &vr, &ar) == 0);
    CHECK(pinfo.version == 1 && pinfo.flags == info.flags && pinfo.tb_hz == 40500000u && pinfo.cycle_count == 12 && pinfo.video_count == 12 && pinfo.audio_count == 6);
    CHECK(pinfo.audio_raw_count == 6 && pinfo.video_raw_stored == 12 && pinfo.capture_result == GBP_AVSEQ_END_TARGET_REACHED && pinfo.end_reason == GBP_AVSEQ_END_TARGET_REACHED);
    CHECK(pinfo.target_video_blocks == 88 && pinfo.max_deliveries == 320 && pinfo.admission_budget_ticks == 40500000u && pinfo.t0 == 0xFFFFFF00u && pinfo.admission_deadline == 0xFFFFFF00u + 40500000u);
    CHECK(pinfo.boundaries_gbi == 1 && pinfo.boundaries_disc == 1 && pinfo.video_block_size == 0xF00u && pinfo.audio_block_size == 0x1000u);
    CHECK(strcmp(pinfo.test_id, "GBP-VIDEO-001") == 0 && strcmp(pinfo.build_id, "video-0001") == 0 && strcmp(pinfo.app, "gbp-video-capture-probe") == 0 && strcmp(pinfo.commit, "abcdef0") == 0);
    CHECK(pinfo.off_cycles == 0x100 && pinfo.off_video_table == info.off_video_table && pinfo.off_audio_table == info.off_audio_table && pinfo.off_video_raw == info.off_video_raw && pinfo.off_audio_raw == info.off_audio_raw && pinfo.off_footer == info.off_footer);
    CHECK(cyc == dump + 0x100 && vt == dump + info.off_video_table && at == dump + info.off_audio_table && vr == dump + info.off_video_raw && ar == dump + info.off_audio_raw);
    for (i = 0; i < 12; i++) { struct gbp_avseq_cycle c; gbp_avseqdump_decode_cycle(cyc + i * GBP_AVSEQDUMP_CYCLE_REC, &c); check_cycle_eq(&c, &store.cycles[i]); }
    stored = 0;
    for (i = 0; i < 12; i++) {
        struct gbp_avseq_vblock v; uint32_t roff = 0, rlen = 0;
        gbp_avseqdump_decode_vblock(vt + i * GBP_AVSEQDUMP_VIDEO_REC, &v, &roff, &rlen);
        CHECK(v.seq == store.vblocks[i].seq && v.cycle == store.vblocks[i].cycle && v.pending == 0x0100 && v.completed == 1 && v.rc == 0 && v.summarized == 1);
        CHECK(v.flag_gbi == store.vblocks[i].flag_gbi && v.flag_disc == store.vblocks[i].flag_disc && v.flags_agree == 1 && memcmp(v.raw_first4, store.vblocks[i].raw_first4, 4) == 0);
        CHECK(v.t_start == 100u * i && v.t_end == 100u * i + 40u && v.wait_ticks == 2400u && v.crc32 == store.vblocks[i].crc32 && v.polls == 120 && v.csr_after == 0x0020);
        CHECK(v.byte0_exceptions == store.vblocks[i].byte0_exceptions && v.undoubled_words == store.vblocks[i].undoubled_words);
        CHECK(rlen == GBP_AVSEQ_VIDEO_BLOCK_SIZE && roff == info.off_video_raw + stored * GBP_AVSEQ_VIDEO_BLOCK_SIZE);
        CHECK(memcmp(dump + roff, video_raw + i * GBP_AVSEQ_VIDEO_BLOCK_SIZE, GBP_AVSEQ_VIDEO_BLOCK_SIZE) == 0);
        stored++;
    }
    for (i = 0; i < 6; i++) {
        struct gbp_avseq_ablock a;
        gbp_avseqdump_decode_ablock(at + i * GBP_AVSEQDUMP_AUDIO_REC, &a);
        CHECK(a.cycle == i * 2u && a.selected && a.attempted && a.completed && a.rc == 0 && a.slot == i && a.raw_kept == 1 && a.raw_index == i && a.summarized == 1);
        CHECK(a.t_start == 7u * i && a.t_end == 7u * i + 3u && a.wait_ticks == 2400u && a.crc32 == store.ablocks[i].crc32 && a.first_word == store.ablocks[i].first_word);
        CHECK(a.nonzero == GBP_AVSEQ_AUDIO_BLOCK_SIZE && a.unit0_nonzero == 128);
        CHECK(memcmp(dump + info.off_audio_raw + i * GBP_AVSEQ_AUDIO_BLOCK_SIZE, audio_raw + i * GBP_AVSEQ_AUDIO_BLOCK_SIZE, GBP_AVSEQ_AUDIO_BLOCK_SIZE) == 0);
    }
    /* deterministic: a second serialization is byte-identical */
    {
        struct gbp_avseqdump_info info2 = info;
        long n2 = gbp_avseqdump_serialize(&info2, &store, dump2, sizeof dump2);
        CHECK(n2 == n && memcmp(dump, dump2, (size_t)n) == 0);
    }
}

static void test_sidecar_failed_blocks_and_pingpong(void)
{
    struct gbp_avseqdump_info info, pinfo;
    const uint8_t *cyc, *vt, *at, *vr, *ar;
    long n;
    unsigned i;
    /* 40 VIDEO DMAs with seq 30 failed (raw_len 0, no raw block), 14 AUDIO drains with the 11th failed: raw = 8 first + last valid */
    build_store(40, 40, 14);
    memset(&info, 0, sizeof info);
    gbp_avseqdump_set_identity(&info, "GBP-VIDEO-001", "synthetic", "test", "");
    n = gbp_avseqdump_serialize(&info, &store, dump, sizeof dump);
    CHECK(n > 0 && info.video_count == 40 && info.video_raw_stored == 39 && info.audio_count == 14 && info.audio_raw_count == 9);
    CHECK(gbp_avseqdump_parse(dump, (size_t)n, &pinfo, &cyc, &vt, &at, &vr, &ar) == 0);
    {
        struct gbp_avseq_vblock v; uint32_t roff = 1, rlen = 1;
        gbp_avseqdump_decode_vblock(vt + 30u * GBP_AVSEQDUMP_VIDEO_REC, &v, &roff, &rlen);
        CHECK(v.completed == 0 && v.rc == (uint8_t)GBP_ERR_TIMEOUT && rlen == 0 && roff == 0 && v.summarized == 0 && v.crc32 == 0);
        gbp_avseqdump_decode_vblock(vt + 31u * GBP_AVSEQDUMP_VIDEO_REC, &v, &roff, &rlen);
        CHECK(v.completed == 1 && rlen == GBP_AVSEQ_VIDEO_BLOCK_SIZE && roff == info.off_video_raw + 30u * GBP_AVSEQ_VIDEO_BLOCK_SIZE);   /* stored blocks are packed */
        CHECK(memcmp(dump + roff, video_raw + 31u * GBP_AVSEQ_VIDEO_BLOCK_SIZE, GBP_AVSEQ_VIDEO_BLOCK_SIZE) == 0);
    }
    for (i = 0; i < 14; i++) {
        struct gbp_avseq_ablock a;
        gbp_avseqdump_decode_ablock(at + i * GBP_AVSEQDUMP_AUDIO_REC, &a);
        if (i < 8) CHECK(a.completed && a.raw_kept && a.raw_index == i);
        else if (i == 10) CHECK(!a.completed && a.raw_index == 0xFFFFu && a.slot == GBP_AVSEQ_SLOT_NONE && a.rc == (uint8_t)GBP_ERR_BUSY);
        else if (i == 13) CHECK(a.completed && a.raw_kept && a.raw_index == 8u);      /* the last valid: raw slot 8 (drains 9..: 8,9,fail(8),8?,...) */
        else CHECK(a.completed && a.raw_kept == 0 && a.raw_index == 0xFFFFu);   /* overwritten ping-pong bytes: no raw block in the file */
    }
    CHECK(memcmp(dump + info.off_audio_raw + 8u * GBP_AVSEQ_AUDIO_BLOCK_SIZE, audio_raw + (unsigned)store.audio_last_valid * GBP_AVSEQ_AUDIO_BLOCK_SIZE, GBP_AVSEQ_AUDIO_BLOCK_SIZE) == 0);
    CHECK(gbp_crc32(dump + info.off_audio_raw + 8u * GBP_AVSEQ_AUDIO_BLOCK_SIZE, GBP_AVSEQ_AUDIO_BLOCK_SIZE) == store.ablocks[13].crc32);
}

static void test_sidecar_bounds_and_errors(void)
{
    struct gbp_avseqdump_info info, pinfo;
    long n;
    size_t sz;
    /* the maximal store fits the compile-time bound exactly */
    build_store(GBP_AVSEQ_MAX_DELIVERIES, GBP_AVSEQ_MAX_VIDEO_BLOCKS, GBP_AVSEQ_MAX_AUDIO_BLOCKS);
    sz = gbp_avseqdump_size(&store);
    CHECK(sz <= GBP_AVSEQDUMP_MAX_SIZE && sz == GBP_AVSEQDUMP_MAX_SIZE - GBP_AVSEQ_VIDEO_BLOCK_SIZE - GBP_AVSEQ_AUDIO_BLOCK_SIZE);   /* one failed VIDEO, 9 of 10 audio slots */
    memset(&info, 0, sizeof info);
    gbp_avseqdump_set_identity(&info, "GBP-VIDEO-001", "video-0001", "gbp-video-capture-probe", "0123456789abcdef0123456789abcde");
    n = gbp_avseqdump_serialize(&info, &store, dump, sizeof dump);
    CHECK(n == (long)sz);
    CHECK(gbp_avseqdump_parse(dump, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == 0 && pinfo.cycle_count == 320 && pinfo.video_count == 88 && pinfo.audio_count == 320 && pinfo.audio_raw_count == 9);
    CHECK(gbp_avseqdump_serialize(&info, &store, dump, sz - 1u) == -1);   /* too small: nothing written beyond cap */
    CHECK(gbp_avseqdump_serialize(&info, &store, 0, sz) == -1);
    /* identities: too long, empty test id, non-printable → refused, never truncated */
    CHECK(gbp_avseqdump_set_identity(&info, "GBP-VIDEO-001", "video-0001", "gbp-video-capture-probe", "0123456789abcdef0123456789abcdef") != 0 && info.identity_error == 1);
    CHECK(gbp_avseqdump_serialize(&info, &store, dump, sizeof dump) == -2);
    CHECK(gbp_avseqdump_set_identity(&info, "", "video-0001", "x", "") != 0);
    CHECK(gbp_avseqdump_set_identity(&info, "GBP VIDEO", "video-0001", "x", "") != 0);
    CHECK(gbp_avseqdump_set_identity(&info, "GBP-VIDEO-001", "video-0001", "", "") == 0);   /* app and commit may be empty */
    /* parse errors on a small file */
    build_store(3, 2, 1);
    memset(&info, 0, sizeof info);
    gbp_avseqdump_set_identity(&info, "GBP-VIDEO-001", "synthetic", "test", "none");
    n = gbp_avseqdump_serialize(&info, &store, dump, sizeof dump);
    CHECK(n > 0 && gbp_avseqdump_parse(dump, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == 0);
    CHECK(gbp_avseqdump_parse(dump, (size_t)n - 1u, &pinfo, 0, 0, 0, 0, 0) == -4);          /* truncated: the footer falls outside */
    CHECK(gbp_avseqdump_parse(dump, 100, &pinfo, 0, 0, 0, 0, 0) == -1);                      /* shorter than a header */
    memcpy(dump2, dump, (size_t)n); dump2[0] = 'X';
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -1);              /* bad magic */
    memcpy(dump2, dump, (size_t)n); dump2[0x09] = 2; put32(dump2 + 0xFC, gbp_crc32(dump2, 0xFCu));
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -2);              /* unsupported version */
    memcpy(dump2, dump, (size_t)n); dump2[0x2D] = 95; put32(dump2 + 0xFC, gbp_crc32(dump2, 0xFCu));
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -2);              /* record size mismatch */
    memcpy(dump2, dump, (size_t)n); dump2[0x10] ^= 0x01;
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -3);              /* header CRC */
    memcpy(dump2, dump, (size_t)n); dump2[0xF3] = 1; put32(dump2 + 0xFC, gbp_crc32(dump2, 0xFCu));
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -9);              /* reserved not zero */
    memcpy(dump2, dump, (size_t)n); put32(dump2 + 0x3C, get32(dump2 + 0x3C) + 4u); put32(dump2 + 0xFC, gbp_crc32(dump2, 0xFCu));
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -4);              /* tables not contiguous */
    memcpy(dump2, dump, (size_t)n); put32(dump2 + 0x14, 321u); put32(dump2 + 0xFC, gbp_crc32(dump2, 0xFCu));
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -4);              /* a count beyond the design bound */
    memcpy(dump2, dump, (size_t)n); dump2[info.off_footer] = 'X';
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -5);              /* footer magic */
    memcpy(dump2, dump, (size_t)n); dump2[info.off_cycles + 5] ^= 0xFF;
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -6);              /* total CRC (a table byte changed) */
    memcpy(dump2, dump, (size_t)n); dump2[info.off_video_raw + 100] ^= 0x55; put32(dump2 + info.off_footer + 8, gbp_crc32(dump2, info.off_footer));
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -7);              /* a VIDEO block's CRC (total CRC "repaired") */
    memcpy(dump2, dump, (size_t)n); dump2[info.off_audio_raw + 7] ^= 0x55; put32(dump2 + info.off_footer + 8, gbp_crc32(dump2, info.off_footer));
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -7);              /* an AUDIO block's CRC */
    memcpy(dump2, dump, (size_t)n); dump2[0x40] = ' '; put32(dump2 + 0xFC, gbp_crc32(dump2, 0xFCu));
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -8);              /* identity with a space */
    memcpy(dump2, dump, (size_t)n); memset(dump2 + 0x60, 'b', 32); put32(dump2 + 0xFC, gbp_crc32(dump2, 0xFCu));
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -8);              /* identity without terminator (overflow) */
    memcpy(dump2, dump, (size_t)n); dump2[0x60 + 3] = 0; put32(dump2 + 0xFC, gbp_crc32(dump2, 0xFCu));
    CHECK(gbp_avseqdump_parse(dump2, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == -8);              /* bytes after the terminator */
    /* an empty store (a run that never delivered) still round-trips */
    gbp_avseq_store_init(&store, video_raw, sizeof video_raw, audio_raw, sizeof audio_raw);
    n = gbp_avseqdump_serialize(&info, &store, dump, sizeof dump);
    CHECK(n == (long)(GBP_AVSEQDUMP_HEADER_SIZE + GBP_AVSEQDUMP_FOOTER_SIZE) && gbp_avseqdump_parse(dump, (size_t)n, &pinfo, 0, 0, 0, 0, 0) == 0 && pinfo.cycle_count == 0);
}

static void test_log_lines(void)
{
    struct ringlog rl;
    struct gbp_avseq_cycle c = cycle_sample(319);
    struct gbp_avseq_boundaries b;
    size_t i, m = 0;
    unsigned k;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    /* extreme values in every field: no line may exceed the ring's line width */
    c.t_adm = 0xFFFFFFFFu; c.t_cause = 0xFFFFFFFFu; c.t_unmask = 0xFFFFFFFFu; c.t_post_unmask = 0xFFFFFFFFu; c.t_entry = 0xFFFFFFFFu; c.latency = 0xFFFFFFFFu;
    c.t_read = 0xFFFFFFFFu; c.t_audio_start = c.t_audio_end = c.t_video_start = c.t_video_end = 0xFFFFFFFFu; c.t_ack_after = c.t_rearm = c.t_rearm_after = c.t_next = 0xFFFFFFFFu;
    c.intsr_pre = c.intmr_pre = c.intsr_post = c.intmr_post = c.intsr_remask = c.intmr_remask = 0xFFFFFFFFu; c.t_wait_end = c.wait_polls = 0xFFFFFFFFu;
    c.intsr_before_w1c = c.intmr_after_mask = c.t_second = c.intsr_second = c.intmr_second = c.reentry_t = c.reentry_intsr = c.reentry_intmr = 0xFFFFFFFFu;
    c.rec0_fired = 0xFFFFFFFFu; c.next_polls = 0xFFFFFFFFu; c.audio_wait = c.video_wait = 0xFFFFFFFFu; c.audio_crc32 = 0xFFFFFFFFu; c.audio_slot = GBP_AVSEQ_SLOT_LAST | 1u;
    c.video_seq = 0xFFFF; c.pending = 0xFFFF; c.ack_value = 0xFFFF; c.audio_rc = (uint8_t)GBP_ERR_TIMEOUT; c.video_rc = (uint8_t)GBP_ERR_BACKEND; c.prep_rc = (uint8_t)GBP_ERR_BUSY;
    c.isr_count = 255; c.isr_reentry = 1; c.timed_out = 1; c.remask_retry = 1; c.next_ended_by = GBP_AVSEQ_NEXT_SINGLE_READ; c.end_reason = GBP_AVSEQ_END_RUNTIME_CAP;
    c.intsr_prep = c.intmr_prep = 0xFFFFFFFFu; c.mask_ok = 1; c.irq_disc = c.irq_gbi = 0xFFFF; c.irq_byte0 = 0xff;
    memset(c.irq_raw, 0xff, sizeof c.irq_raw); c.irq_rc = GBP_OK; memset(&c.irq_info, 0, sizeof c.irq_info);
    gbp_avseq_log_cycle(&rl, &c, 0x01800000u, 0x01100000u);
    /* a LEAN cycle: five compact records plus the raw pending read, so a physical log regenerates a fixture */
    CHECK(rl.count == 6 && rl.truncated == 0);
    CHECK(strncmp(L(0), "CYCU n=319 verify=0 t_adm=4294967295 prep=ffffffff/ffffffff/busy pre=ffffffff/ffffffff t_unmask=4294967295", 105) == 0);
    CHECK(strcmp(L(1), "CYCW n=319 polls=4294967295 timed_out=1 t_wait_end=4294967295 remask=ffffffff/ffffffff retry=1 mask_ok=1") == 0);
    CHECK(strncmp(L(2), "CYCH n=319 rec=255,1,4294967295,", 32) == 0);
    CHECK(strncmp(L(3), "RAW READ-319 idx=d addr=01d00000 rc=ok", 38) == 0);          /* the standard block format */
    CHECK(strstr(L(3), "sem_disc=ffff sem_gbi=ffff data=") != 0);
    CHECK(strstr(L(4), "CYCD n=319 pend=ffff disc=ffff gbi=ffff b0=") != 0 && strstr(L(4), "/L1/") != 0);
    CHECK(strstr(L(5), "next=1/single_read/4294967295/00012000/4294967295 end=runtime_cap") != 0);
    /* a VERIFY cycle logs no raw line: its PRESVC snapshot already carried the same read */
    {
        struct gbp_avseq_cycle vc = c;
        struct ringlog r2;
        vc.verify = 1;
        ringlog_init(&r2, storage, LINE_LEN, LINES);
        gbp_avseq_log_cycle(&r2, &vc, 0x01800000u, 0x01100000u);
        CHECK(r2.count == 5 && r2.truncated == 0);
        CHECK(strstr(ringlog_line(&r2, 3), "CYCD n=319") != 0);
    }
    for (i = 0; i < rl.count; i++) if (strlen(ringlog_line(&rl, i)) > m) m = strlen(ringlog_line(&rl, i));
    CHECK(m < LINE_LEN - 1u);
    /* boundaries with 88 positions and 87 intervals: too long for one line → summary + chunked BPOS / BINT lines, nothing truncated */
    b.count = GBP_AVSEQ_MAX_VIDEO_BLOCKS; b.intervals_n = GBP_AVSEQ_MAX_VIDEO_BLOCKS - 1u; b.complete_interval = 1;
    for (k = 0; k < GBP_AVSEQ_MAX_VIDEO_BLOCKS; k++) { b.positions[k] = k; b.intervals[k] = 1; }
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_avseq_log_boundaries(&rl, "gbi", &b);
    CHECK(rl.count == 7 && rl.truncated == 0 && strcmp(L(0), "BOUNDARIES gbi=88 positions=BPOS intervals=BINT complete_interval=1") == 0);
    CHECK(strncmp(L(1), "BPOS gbi i=0 v=0,1,2,3,", 23) == 0 && strncmp(L(3), "BPOS gbi i=64 v=64,65,", 22) == 0);
    CHECK(strncmp(L(4), "BINT gbi i=0 v=1,1,1,", 21) == 0 && strcmp(L(6), "BINT gbi i=64 v=1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1") == 0);
    for (i = 0; i < rl.count; i++) CHECK(strlen(ringlog_line(&rl, i)) < LINE_LEN - 1u);
    b.count = 3; b.positions[0] = 0; b.positions[1] = 40; b.positions[2] = 80; b.intervals_n = 2; b.intervals[0] = 40; b.intervals[1] = 40;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_avseq_log_boundaries(&rl, "disc", &b);
    CHECK(strcmp(L(0), "BOUNDARIES disc=3 positions=0,40,80 intervals=40,40 complete_interval=1") == 0);
    b.count = 0; b.intervals_n = 0; b.complete_interval = 0;
    ringlog_init(&rl, storage, LINE_LEN, LINES);
    gbp_avseq_log_boundaries(&rl, "gbi", &b);
    CHECK(strcmp(L(0), "BOUNDARIES gbi=0 positions=- intervals=- complete_interval=0") == 0);
    CHECK(strcmp(gbp_avseq_end_name(GBP_AVSEQ_END_TARGET_REACHED), "target_reached") == 0 && strcmp(gbp_avseq_end_name(GBP_AVSEQ_END_DELIVERY_CAP), "delivery_cap") == 0);
    CHECK(strcmp(gbp_avseq_end_name(GBP_AVSEQ_END_NO_NEXT_CAUSE), "no_next_cause") == 0 && strcmp(gbp_avseq_end_name(GBP_AVSEQ_END_EARLY_FAILURE), "early_failure") == 0);
    CHECK(strcmp(gbp_avseq_next_end_name(GBP_AVSEQ_NEXT_CAUSE), "cause") == 0 && strcmp(gbp_avseq_next_end_name(GBP_AVSEQ_NEXT_DEADLINE), "admission_deadline") == 0 && strcmp(gbp_avseq_next_end_name(GBP_AVSEQ_NEXT_TIMEOUT), "t_next_cause") == 0);
}

int main(void)
{
    test_predicates();
    test_video_slots();
    test_audio_pingpong();
    test_summaries_and_boundaries();
    test_sidecar_roundtrip();
    test_sidecar_failed_blocks_and_pingpong();
    test_sidecar_bounds_and_errors();
    test_log_lines();
    printf("test_gbp_avseq: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
