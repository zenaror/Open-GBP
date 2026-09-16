#include "gbp_avseqdump.h"

#include <string.h>
#include "gbp_crc32.h"

#define OFF_TEST_ID 0x40u
#define OFF_BUILD_ID 0x60u
#define OFF_APP 0x80u
#define OFF_COMMIT 0xA0u
#define OFF_HEADER_CRC 0xFCu
#define OFF_RESERVED 0xF0u
#define RESERVED_LEN 12u

/* cycle record (96 bytes) */
#define CR_IDX 0x00u
#define CR_PENDING 0x02u
#define CR_B0 0x04u
#define CR_O2 0x05u
#define CR_FLAGS1 0x06u
#define CR_FLAGS2 0x07u
#define CR_AUDIO_RC 0x08u
#define CR_VIDEO_RC 0x09u
#define CR_AUDIO_SLOT 0x0Au
#define CR_END 0x0Bu
#define CR_VIDEO_SEQ 0x0Cu
#define CR_ACK_VALUE 0x0Eu
#define CR_ISR_FIRED 0x10u
#define CR_ISR_COUNT 0x11u
#define CR_ISR_REENTRY 0x12u
#define CR_NEXT_END 0x13u
#define CR_T_CAUSE 0x14u
#define CR_T_UNMASK 0x18u
#define CR_T_ENTRY 0x1Cu
#define CR_LATENCY 0x20u
#define CR_T_READ 0x24u
#define CR_T_AUDIO_START 0x28u
#define CR_T_AUDIO_END 0x2Cu
#define CR_T_VIDEO_START 0x30u
#define CR_T_VIDEO_END 0x34u
#define CR_T_ACK_AFTER 0x38u
#define CR_T_REARM 0x3Cu
#define CR_T_REARM_AFTER 0x40u
#define CR_T_NEXT 0x44u
#define CR_INTSR_ENTRY 0x48u
#define CR_INTMR_ENTRY 0x4Cu
#define CR_INTSR_AFTER_W1C 0x50u
#define CR_INTSR_POSTACK 0x54u
#define CR_INTSR_NEXT 0x58u
#define CR_AUDIO_CRC 0x5Cu

/* VIDEO record (48 bytes) */
#define VR_SEQ 0x00u
#define VR_CYCLE 0x02u
#define VR_PENDING 0x04u
#define VR_RC 0x06u
#define VR_FLAGS 0x07u
#define VR_FIRST4 0x08u
#define VR_T_START 0x0Cu
#define VR_T_END 0x10u
#define VR_WAIT 0x14u
#define VR_CRC 0x18u
#define VR_RAW_OFF 0x1Cu
#define VR_RAW_LEN 0x20u
#define VR_X0 0x24u
#define VR_UND 0x26u
#define VR_POLLS 0x28u
#define VR_CSR_BEFORE 0x2Au
#define VR_CSR_AFTER 0x2Cu
#define VR_RESERVED 0x2Eu

/* AUDIO record (32 bytes) */
#define AR_CYCLE 0x00u
#define AR_FLAGS 0x02u
#define AR_RC 0x03u
#define AR_SLOT 0x04u
#define AR_RESERVED 0x05u
#define AR_RAW_INDEX 0x06u
#define AR_T_START 0x08u
#define AR_T_END 0x0Cu
#define AR_WAIT 0x10u
#define AR_CRC 0x14u
#define AR_FIRST_WORD 0x18u
#define AR_NONZERO 0x1Cu
#define AR_UNIT0 0x1Eu

static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static void put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static uint16_t get16(const uint8_t *p) { return (uint16_t)((p[0] << 8) | p[1]); }
static uint32_t get32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3]; }

/* The identity rule, identical to the one gbp_avdump.h documents for the block sidecar and
 * deliberately re-stated here: this module never links the v2 sidecar, so the two formats
 * stay independent objects. 1 to 31 printable ASCII bytes (0x21..0x7E), NUL padded; a value
 * that does not fit is an error of the serializer, never a truncation. */
static int id_byte_ok(uint8_t c)
{
    return c >= 0x21u && c <= 0x7Eu;
}

static int seq_id_ok(const char *s, int may_be_empty)
{
    size_t i;
    if (!s) return 0;
    for (i = 0; s[i]; i++) {
        if (i >= GBP_AVSEQDUMP_ID_MAX) return 0;                 /* does not fit: never truncated */
        if (!id_byte_ok((uint8_t)s[i])) return 0;
    }
    if (i == 0 && !may_be_empty) return 0;
    return 1;
}

static int set_one(char *dst, const char *src, int may_be_empty)
{
    memset(dst, 0, GBP_AVSEQDUMP_ID_FIELD);
    if (!seq_id_ok(src, may_be_empty)) return 0;
    memcpy(dst, src, strlen(src));
    return 1;
}

int gbp_avseqdump_set_identity(struct gbp_avseqdump_info *info, const char *test_id, const char *build_id,
                               const char *app, const char *commit)
{
    int ok = 1;
    if (!set_one(info->test_id, test_id, 0)) ok = 0;
    if (!set_one(info->build_id, build_id, 0)) ok = 0;
    if (!set_one(info->app, app, 1)) ok = 0;
    if (!set_one(info->commit, commit, 1)) ok = 0;
    info->identity_error = ok ? 0 : 1;
    return ok ? 0 : -1;
}

static void put_id(uint8_t *p, const char *s)
{
    size_t n = strlen(s);
    memset(p, 0, GBP_AVSEQDUMP_ID_FIELD);
    memcpy(p, s, n);
}

static int get_id(const uint8_t *p, char *dst, int may_be_empty)
{
    size_t i, n = 0;
    int seen_nul = 0;
    memset(dst, 0, GBP_AVSEQDUMP_ID_FIELD);
    for (i = 0; i < GBP_AVSEQDUMP_ID_FIELD; i++) {
        if (seen_nul) { if (p[i] != 0u) return 0; continue; }
        if (p[i] == 0u) { seen_nul = 1; continue; }
        if (p[i] < 0x21u || p[i] > 0x7Eu) return 0;
        n++;
    }
    if (!seen_nul || n > GBP_AVSEQDUMP_ID_MAX) return 0;
    if (n == 0 && !may_be_empty) return 0;
    memcpy(dst, p, n);
    return 1;
}

static unsigned video_raw_stored(const struct gbp_avseq_store *s)
{
    unsigned i, n = 0;
    for (i = 0; i < s->vblocks_n; i++) if (s->vblocks[i].completed) n++;
    return n;
}

size_t gbp_avseqdump_size(const struct gbp_avseq_store *s)
{
    return (size_t)GBP_AVSEQDUMP_HEADER_SIZE + (size_t)s->cycles_n * GBP_AVSEQDUMP_CYCLE_REC +
           (size_t)s->vblocks_n * GBP_AVSEQDUMP_VIDEO_REC + (size_t)s->ablocks_n * GBP_AVSEQDUMP_AUDIO_REC +
           (size_t)video_raw_stored(s) * GBP_AVSEQ_VIDEO_BLOCK_SIZE +
           (size_t)gbp_avseq_audio_raw_count(s) * GBP_AVSEQ_AUDIO_BLOCK_SIZE + GBP_AVSEQDUMP_FOOTER_SIZE;
}

static void encode_cycle(uint8_t *p, const struct gbp_avseq_cycle *c)
{
    memset(p, 0, GBP_AVSEQDUMP_CYCLE_REC);
    put16(p + CR_IDX, c->idx);
    put16(p + CR_PENDING, c->pending);
    p[CR_B0] = c->irq_byte0;
    p[CR_O2] = c->irq_off2_g0;
    p[CR_FLAGS1] = (uint8_t)((c->verify ? 1u : 0u) | (c->audio_selected ? 2u : 0u) | (c->audio_attempted ? 4u : 0u) | (c->audio_completed ? 8u : 0u) |
                             (c->video_selected ? 16u : 0u) | (c->video_attempted ? 32u : 0u) | (c->video_completed ? 64u : 0u) | (c->next_observed ? 128u : 0u));
    p[CR_FLAGS2] = (uint8_t)((c->ack_attempted ? 1u : 0u) | (c->ack_completed ? 2u : 0u) | (c->rearm_attempted ? 4u : 0u) | (c->rearm_completed ? 8u : 0u) |
                             (c->main_w1c ? 16u : 0u) | (c->pi_sticky ? 32u : 0u) | (c->relatch_postack ? 64u : 0u) | (c->admitted ? 128u : 0u));
    p[CR_AUDIO_RC] = c->audio_rc;
    p[CR_VIDEO_RC] = c->video_rc;
    p[CR_AUDIO_SLOT] = c->audio_slot;
    p[CR_END] = c->end_reason;
    put16(p + CR_VIDEO_SEQ, c->video_seq);
    put16(p + CR_ACK_VALUE, c->ack_value);
    p[CR_ISR_FIRED] = c->isr_fired;
    p[CR_ISR_COUNT] = c->isr_count;
    p[CR_ISR_REENTRY] = c->isr_reentry;
    p[CR_NEXT_END] = c->next_ended_by;
    put32(p + CR_T_CAUSE, c->t_cause);
    put32(p + CR_T_UNMASK, c->t_unmask);
    put32(p + CR_T_ENTRY, c->t_entry);
    put32(p + CR_LATENCY, c->latency);
    put32(p + CR_T_READ, c->t_read);
    put32(p + CR_T_AUDIO_START, c->t_audio_start);
    put32(p + CR_T_AUDIO_END, c->t_audio_end);
    put32(p + CR_T_VIDEO_START, c->t_video_start);
    put32(p + CR_T_VIDEO_END, c->t_video_end);
    put32(p + CR_T_ACK_AFTER, c->t_ack_after);
    put32(p + CR_T_REARM, c->t_rearm);
    put32(p + CR_T_REARM_AFTER, c->t_rearm_after);
    put32(p + CR_T_NEXT, c->t_next);
    put32(p + CR_INTSR_ENTRY, c->intsr_entry);
    put32(p + CR_INTMR_ENTRY, c->intmr_entry);
    put32(p + CR_INTSR_AFTER_W1C, c->intsr_after_w1c);
    put32(p + CR_INTSR_POSTACK, c->intsr_postack);
    put32(p + CR_INTSR_NEXT, c->intsr_next);
    put32(p + CR_AUDIO_CRC, c->audio_crc32);
}

void gbp_avseqdump_decode_cycle(const uint8_t *p, struct gbp_avseq_cycle *c)
{
    uint8_t f1 = p[CR_FLAGS1], f2 = p[CR_FLAGS2];
    memset(c, 0, sizeof *c);
    c->idx = get16(p + CR_IDX);
    c->pending = get16(p + CR_PENDING);
    c->irq_byte0 = p[CR_B0];
    c->irq_off2_g0 = p[CR_O2];
    c->verify = (f1 & 1u) ? 1u : 0u;
    c->audio_selected = (f1 & 2u) ? 1u : 0u;
    c->audio_attempted = (f1 & 4u) ? 1u : 0u;
    c->audio_completed = (f1 & 8u) ? 1u : 0u;
    c->video_selected = (f1 & 16u) ? 1u : 0u;
    c->video_attempted = (f1 & 32u) ? 1u : 0u;
    c->video_completed = (f1 & 64u) ? 1u : 0u;
    c->next_observed = (f1 & 128u) ? 1u : 0u;
    c->ack_attempted = (f2 & 1u) ? 1u : 0u;
    c->ack_completed = (f2 & 2u) ? 1u : 0u;
    c->rearm_attempted = (f2 & 4u) ? 1u : 0u;
    c->rearm_completed = (f2 & 8u) ? 1u : 0u;
    c->main_w1c = (f2 & 16u) ? 1u : 0u;
    c->pi_sticky = (f2 & 32u) ? 1u : 0u;
    c->relatch_postack = (f2 & 64u) ? 1u : 0u;
    c->admitted = (f2 & 128u) ? 1u : 0u;
    c->audio_rc = p[CR_AUDIO_RC];
    c->video_rc = p[CR_VIDEO_RC];
    c->audio_slot = p[CR_AUDIO_SLOT];
    c->end_reason = p[CR_END];
    c->video_seq = get16(p + CR_VIDEO_SEQ);
    c->ack_value = get16(p + CR_ACK_VALUE);
    c->isr_fired = p[CR_ISR_FIRED];
    c->isr_count = p[CR_ISR_COUNT];
    c->isr_reentry = p[CR_ISR_REENTRY];
    c->next_ended_by = p[CR_NEXT_END];
    c->t_cause = get32(p + CR_T_CAUSE);
    c->t_unmask = get32(p + CR_T_UNMASK);
    c->t_entry = get32(p + CR_T_ENTRY);
    c->latency = get32(p + CR_LATENCY);
    c->t_read = get32(p + CR_T_READ);
    c->t_audio_start = get32(p + CR_T_AUDIO_START);
    c->t_audio_end = get32(p + CR_T_AUDIO_END);
    c->t_video_start = get32(p + CR_T_VIDEO_START);
    c->t_video_end = get32(p + CR_T_VIDEO_END);
    c->t_ack_after = get32(p + CR_T_ACK_AFTER);
    c->t_rearm = get32(p + CR_T_REARM);
    c->t_rearm_after = get32(p + CR_T_REARM_AFTER);
    c->t_next = get32(p + CR_T_NEXT);
    c->intsr_entry = get32(p + CR_INTSR_ENTRY);
    c->intmr_entry = get32(p + CR_INTMR_ENTRY);
    c->intsr_after_w1c = get32(p + CR_INTSR_AFTER_W1C);
    c->intsr_postack = get32(p + CR_INTSR_POSTACK);
    c->intsr_next = get32(p + CR_INTSR_NEXT);
    c->audio_crc32 = get32(p + CR_AUDIO_CRC);
}

static void encode_vblock(uint8_t *p, const struct gbp_avseq_vblock *v, uint32_t raw_offset, uint32_t raw_len)
{
    memset(p, 0, GBP_AVSEQDUMP_VIDEO_REC);
    put16(p + VR_SEQ, v->seq);
    put16(p + VR_CYCLE, v->cycle);
    put16(p + VR_PENDING, v->pending);
    p[VR_RC] = v->rc;
    p[VR_FLAGS] = (uint8_t)((v->completed ? 1u : 0u) | (v->flag_gbi ? 2u : 0u) | (v->flag_disc ? 4u : 0u) | (v->flags_agree ? 8u : 0u) | (v->summarized ? 16u : 0u));
    memcpy(p + VR_FIRST4, v->raw_first4, 4);
    put32(p + VR_T_START, v->t_start);
    put32(p + VR_T_END, v->t_end);
    put32(p + VR_WAIT, v->wait_ticks);
    put32(p + VR_CRC, v->crc32);
    put32(p + VR_RAW_OFF, raw_offset);
    put32(p + VR_RAW_LEN, raw_len);
    put16(p + VR_X0, v->byte0_exceptions);
    put16(p + VR_UND, v->undoubled_words);
    put16(p + VR_POLLS, v->polls);
    put16(p + VR_CSR_BEFORE, v->csr_before);
    put16(p + VR_CSR_AFTER, v->csr_after);
}

void gbp_avseqdump_decode_vblock(const uint8_t *p, struct gbp_avseq_vblock *v, uint32_t *raw_offset, uint32_t *raw_len)
{
    uint8_t f = p[VR_FLAGS];
    memset(v, 0, sizeof *v);
    v->seq = get16(p + VR_SEQ);
    v->cycle = get16(p + VR_CYCLE);
    v->pending = get16(p + VR_PENDING);
    v->rc = p[VR_RC];
    v->completed = (f & 1u) ? 1u : 0u;
    v->flag_gbi = (f & 2u) ? 1u : 0u;
    v->flag_disc = (f & 4u) ? 1u : 0u;
    v->flags_agree = (f & 8u) ? 1u : 0u;
    v->summarized = (f & 16u) ? 1u : 0u;
    memcpy(v->raw_first4, p + VR_FIRST4, 4);
    v->t_start = get32(p + VR_T_START);
    v->t_end = get32(p + VR_T_END);
    v->wait_ticks = get32(p + VR_WAIT);
    v->crc32 = get32(p + VR_CRC);
    if (raw_offset) *raw_offset = get32(p + VR_RAW_OFF);
    if (raw_len) *raw_len = get32(p + VR_RAW_LEN);
    v->byte0_exceptions = get16(p + VR_X0);
    v->undoubled_words = get16(p + VR_UND);
    v->polls = get16(p + VR_POLLS);
    v->csr_before = get16(p + VR_CSR_BEFORE);
    v->csr_after = get16(p + VR_CSR_AFTER);
}

static void encode_ablock(uint8_t *p, const struct gbp_avseq_ablock *a, uint16_t raw_index)
{
    memset(p, 0, GBP_AVSEQDUMP_AUDIO_REC);
    put16(p + AR_CYCLE, a->cycle);
    p[AR_FLAGS] = (uint8_t)((a->selected ? 1u : 0u) | (a->attempted ? 2u : 0u) | (a->completed ? 4u : 0u) | (a->raw_kept ? 8u : 0u) | (a->summarized ? 16u : 0u));
    p[AR_RC] = a->rc;
    p[AR_SLOT] = a->slot;
    put16(p + AR_RAW_INDEX, raw_index);
    put32(p + AR_T_START, a->t_start);
    put32(p + AR_T_END, a->t_end);
    put32(p + AR_WAIT, a->wait_ticks);
    put32(p + AR_CRC, a->crc32);
    put32(p + AR_FIRST_WORD, a->first_word);
    put16(p + AR_NONZERO, a->nonzero);
    put16(p + AR_UNIT0, a->unit0_nonzero);
}

void gbp_avseqdump_decode_ablock(const uint8_t *p, struct gbp_avseq_ablock *a)
{
    uint8_t f = p[AR_FLAGS];
    memset(a, 0, sizeof *a);
    a->cycle = get16(p + AR_CYCLE);
    a->selected = (f & 1u) ? 1u : 0u;
    a->attempted = (f & 2u) ? 1u : 0u;
    a->completed = (f & 4u) ? 1u : 0u;
    a->raw_kept = (f & 8u) ? 1u : 0u;
    a->summarized = (f & 16u) ? 1u : 0u;
    a->rc = p[AR_RC];
    a->slot = p[AR_SLOT];
    a->raw_index = get16(p + AR_RAW_INDEX);
    a->t_start = get32(p + AR_T_START);
    a->t_end = get32(p + AR_T_END);
    a->wait_ticks = get32(p + AR_WAIT);
    a->crc32 = get32(p + AR_CRC);
    a->first_word = get32(p + AR_FIRST_WORD);
    a->nonzero = get16(p + AR_NONZERO);
    a->unit0_nonzero = get16(p + AR_UNIT0);
}

/* File index of a raw AUDIO slot: slots 0..first_kept-1 keep their index; the last valid ping-pong slot follows them. */
static uint16_t audio_file_index(const struct gbp_avseq_store *s, uint16_t raw_index, int kept)
{
    if (!kept || raw_index == 0xFFFFu) return 0xFFFFu;
    if (raw_index < GBP_AVSEQ_AUDIO_FIRST_KEPT) return (raw_index < s->audio_first_kept) ? raw_index : 0xFFFFu;
    if ((int)raw_index == s->audio_last_valid) return (uint16_t)s->audio_first_kept;
    return 0xFFFFu;
}

long gbp_avseqdump_serialize(struct gbp_avseqdump_info *info, const struct gbp_avseq_store *s, uint8_t *out, size_t cap)
{
    size_t need = gbp_avseqdump_size(s);
    uint8_t *p = out;
    uint32_t off, raw_video_n = video_raw_stored(s), raw_audio_n = gbp_avseq_audio_raw_count(s);
    unsigned i, stored = 0;

    if (!out || !s || cap < need || need > GBP_AVSEQDUMP_MAX_SIZE) return -1;
    if (s->cycles_n > GBP_AVSEQ_MAX_DELIVERIES || s->vblocks_n > GBP_AVSEQ_MAX_VIDEO_BLOCKS || s->ablocks_n > GBP_AVSEQ_MAX_AUDIO_BLOCKS) return -1;
    if ((raw_video_n && !s->video_raw) || (raw_audio_n && !s->audio_raw)) return -1;
    if (info->identity_error || !seq_id_ok(info->test_id, 0) || !seq_id_ok(info->build_id, 0) ||
        !seq_id_ok(info->app, 1) || !seq_id_ok(info->commit, 1)) return -2;

    /* the offsets, proven before anything is written */
    off = GBP_AVSEQDUMP_HEADER_SIZE;
    info->off_cycles = off;       off += (uint32_t)s->cycles_n * GBP_AVSEQDUMP_CYCLE_REC;
    info->off_video_table = off;  off += (uint32_t)s->vblocks_n * GBP_AVSEQDUMP_VIDEO_REC;
    info->off_audio_table = off;  off += (uint32_t)s->ablocks_n * GBP_AVSEQDUMP_AUDIO_REC;
    info->off_video_raw = off;    off += raw_video_n * GBP_AVSEQ_VIDEO_BLOCK_SIZE;
    info->off_audio_raw = off;    off += raw_audio_n * GBP_AVSEQ_AUDIO_BLOCK_SIZE;
    info->off_footer = off;
    if ((size_t)off + GBP_AVSEQDUMP_FOOTER_SIZE != need) return -1;
    info->version = (uint16_t)GBP_AVSEQDUMP_VERSION;
    info->cycle_count = s->cycles_n;
    info->video_count = s->vblocks_n;
    info->audio_count = s->ablocks_n;
    info->audio_raw_count = raw_audio_n;
    info->video_raw_stored = raw_video_n;
    info->video_block_size = GBP_AVSEQ_VIDEO_BLOCK_SIZE;
    info->audio_block_size = GBP_AVSEQ_AUDIO_BLOCK_SIZE;

    memset(p, 0, GBP_AVSEQDUMP_HEADER_SIZE);
    memcpy(p + 0x00, GBP_AVSEQDUMP_MAGIC, 8);
    put16(p + 0x08, info->version);
    put16(p + 0x0A, (uint16_t)GBP_AVSEQDUMP_HEADER_SIZE);
    put32(p + 0x0C, info->flags);
    put32(p + 0x10, info->tb_hz);
    put32(p + 0x14, info->cycle_count);
    put32(p + 0x18, info->video_count);
    put32(p + 0x1C, info->audio_count);
    put32(p + 0x20, info->audio_raw_count);
    put32(p + 0x24, info->video_block_size);
    put32(p + 0x28, info->audio_block_size);
    put16(p + 0x2C, (uint16_t)GBP_AVSEQDUMP_CYCLE_REC);
    put16(p + 0x2E, (uint16_t)GBP_AVSEQDUMP_VIDEO_REC);
    put16(p + 0x30, (uint16_t)GBP_AVSEQDUMP_AUDIO_REC);
    put16(p + 0x32, info->capture_result);
    put16(p + 0x34, info->status_code);
    put16(p + 0x36, info->end_reason);
    put32(p + 0x38, info->off_cycles);
    put32(p + 0x3C, info->off_video_table);
    put_id(p + OFF_TEST_ID, info->test_id);
    put_id(p + OFF_BUILD_ID, info->build_id);
    put_id(p + OFF_APP, info->app);
    put_id(p + OFF_COMMIT, info->commit);
    put32(p + 0xC0, info->off_audio_table);
    put32(p + 0xC4, info->off_video_raw);
    put32(p + 0xC8, info->off_audio_raw);
    put32(p + 0xCC, info->off_footer);
    put32(p + 0xD0, info->target_video_blocks);
    put32(p + 0xD4, info->max_deliveries);
    put32(p + 0xD8, info->admission_budget_ticks);
    put32(p + 0xDC, info->t0);
    put32(p + 0xE0, info->admission_deadline);
    put32(p + 0xE4, info->boundaries_gbi);
    put32(p + 0xE8, info->boundaries_disc);
    put32(p + 0xEC, info->video_raw_stored);
    info->header_crc32 = gbp_crc32(p, OFF_HEADER_CRC);
    put32(p + OFF_HEADER_CRC, info->header_crc32);

    /* tables */
    p = out + info->off_cycles;
    for (i = 0; i < s->cycles_n; i++, p += GBP_AVSEQDUMP_CYCLE_REC) encode_cycle(p, &s->cycles[i]);
    p = out + info->off_video_table;
    for (i = 0; i < s->vblocks_n; i++, p += GBP_AVSEQDUMP_VIDEO_REC) {
        const struct gbp_avseq_vblock *v = &s->vblocks[i];
        if (v->completed) { encode_vblock(p, v, info->off_video_raw + stored * GBP_AVSEQ_VIDEO_BLOCK_SIZE, GBP_AVSEQ_VIDEO_BLOCK_SIZE); stored++; }
        else encode_vblock(p, v, 0u, 0u);
    }
    p = out + info->off_audio_table;
    for (i = 0; i < s->ablocks_n; i++, p += GBP_AVSEQDUMP_AUDIO_REC) {
        const struct gbp_avseq_ablock *a = &s->ablocks[i];
        encode_ablock(p, a, audio_file_index(s, a->raw_index, a->raw_kept && a->completed));
    }
    /* raw VIDEO blocks, completed ones in sequence order */
    p = out + info->off_video_raw;
    for (i = 0; i < s->vblocks_n; i++) {
        if (!s->vblocks[i].completed) continue;
        memcpy(p, gbp_avseq_video_bytes(s, i), GBP_AVSEQ_VIDEO_BLOCK_SIZE);
        p += GBP_AVSEQ_VIDEO_BLOCK_SIZE;
    }
    /* raw AUDIO blocks: the first kept slots, then the last valid ping-pong slot */
    p = out + info->off_audio_raw;
    for (i = 0; i < s->audio_first_kept; i++) { memcpy(p, gbp_avseq_audio_bytes(s, i), GBP_AVSEQ_AUDIO_BLOCK_SIZE); p += GBP_AVSEQ_AUDIO_BLOCK_SIZE; }
    if (s->audio_last_valid >= (int)GBP_AVSEQ_AUDIO_FIRST_KEPT) { memcpy(p, gbp_avseq_audio_bytes(s, (unsigned)s->audio_last_valid), GBP_AVSEQ_AUDIO_BLOCK_SIZE); p += GBP_AVSEQ_AUDIO_BLOCK_SIZE; }
    if ((uint32_t)(p - out) != info->off_footer) return -1;
    info->total_crc32 = gbp_crc32(out, (size_t)info->off_footer);
    memcpy(p, GBP_AVSEQDUMP_END, 8);
    put32(p + 8, info->total_crc32);
    p += GBP_AVSEQDUMP_FOOTER_SIZE;
    return (long)(p - out);
}

int gbp_avseqdump_parse(const uint8_t *in, size_t n, struct gbp_avseqdump_info *info,
                        const uint8_t **cycles, const uint8_t **vtable, const uint8_t **atable,
                        const uint8_t **video_raw, const uint8_t **audio_raw)
{
    size_t end_cycles, end_video, end_audio, end_vraw, end_araw;
    unsigned i;
    if (cycles) *cycles = 0;
    if (vtable) *vtable = 0;
    if (atable) *atable = 0;
    if (video_raw) *video_raw = 0;
    if (audio_raw) *audio_raw = 0;
    if (!in || n < GBP_AVSEQDUMP_HEADER_SIZE + GBP_AVSEQDUMP_FOOTER_SIZE || memcmp(in, GBP_AVSEQDUMP_MAGIC, 8) != 0) return -1;
    memset(info, 0, sizeof *info);
    info->version = get16(in + 0x08);
    if (info->version != GBP_AVSEQDUMP_VERSION || get16(in + 0x0A) != GBP_AVSEQDUMP_HEADER_SIZE) return -2;
    if (get16(in + 0x2C) != GBP_AVSEQDUMP_CYCLE_REC || get16(in + 0x2E) != GBP_AVSEQDUMP_VIDEO_REC || get16(in + 0x30) != GBP_AVSEQDUMP_AUDIO_REC) return -2;
    info->header_crc32 = get32(in + OFF_HEADER_CRC);
    if (gbp_crc32(in, OFF_HEADER_CRC) != info->header_crc32) return -3;
    for (i = 0; i < RESERVED_LEN; i++) if (in[OFF_RESERVED + i] != 0u) return -9;
    info->flags = get32(in + 0x0C);
    info->tb_hz = get32(in + 0x10);
    info->cycle_count = get32(in + 0x14);
    info->video_count = get32(in + 0x18);
    info->audio_count = get32(in + 0x1C);
    info->audio_raw_count = get32(in + 0x20);
    info->video_block_size = get32(in + 0x24);
    info->audio_block_size = get32(in + 0x28);
    info->capture_result = get16(in + 0x32);
    info->status_code = get16(in + 0x34);
    info->end_reason = get16(in + 0x36);
    info->off_cycles = get32(in + 0x38);
    info->off_video_table = get32(in + 0x3C);
    if (!get_id(in + OFF_TEST_ID, info->test_id, 0) || !get_id(in + OFF_BUILD_ID, info->build_id, 0) ||
        !get_id(in + OFF_APP, info->app, 1) || !get_id(in + OFF_COMMIT, info->commit, 1)) return -8;
    info->off_audio_table = get32(in + 0xC0);
    info->off_video_raw = get32(in + 0xC4);
    info->off_audio_raw = get32(in + 0xC8);
    info->off_footer = get32(in + 0xCC);
    info->target_video_blocks = get32(in + 0xD0);
    info->max_deliveries = get32(in + 0xD4);
    info->admission_budget_ticks = get32(in + 0xD8);
    info->t0 = get32(in + 0xDC);
    info->admission_deadline = get32(in + 0xE0);
    info->boundaries_gbi = get32(in + 0xE4);
    info->boundaries_disc = get32(in + 0xE8);
    info->video_raw_stored = get32(in + 0xEC);
    /* bounds: every table and section inside the file, contiguous, in order, no overlap */
    if (info->cycle_count > GBP_AVSEQ_MAX_DELIVERIES || info->video_count > GBP_AVSEQ_MAX_VIDEO_BLOCKS ||
        info->audio_count > GBP_AVSEQ_MAX_AUDIO_BLOCKS || info->audio_raw_count > GBP_AVSEQ_AUDIO_RAW_SLOTS ||
        info->video_raw_stored > info->video_count) return -4;
    if (info->video_block_size != GBP_AVSEQ_VIDEO_BLOCK_SIZE || info->audio_block_size != GBP_AVSEQ_AUDIO_BLOCK_SIZE) return -2;
    end_cycles = (size_t)info->off_cycles + (size_t)info->cycle_count * GBP_AVSEQDUMP_CYCLE_REC;
    end_video = (size_t)info->off_video_table + (size_t)info->video_count * GBP_AVSEQDUMP_VIDEO_REC;
    end_audio = (size_t)info->off_audio_table + (size_t)info->audio_count * GBP_AVSEQDUMP_AUDIO_REC;
    end_vraw = (size_t)info->off_video_raw + (size_t)info->video_raw_stored * GBP_AVSEQ_VIDEO_BLOCK_SIZE;
    end_araw = (size_t)info->off_audio_raw + (size_t)info->audio_raw_count * GBP_AVSEQ_AUDIO_BLOCK_SIZE;
    if (info->off_cycles != GBP_AVSEQDUMP_HEADER_SIZE || end_cycles != info->off_video_table || end_video != info->off_audio_table ||
        end_audio != info->off_video_raw || end_vraw != info->off_audio_raw || end_araw != info->off_footer) return -4;
    if ((size_t)info->off_footer + GBP_AVSEQDUMP_FOOTER_SIZE > n) return -4;
    if (memcmp(in + info->off_footer, GBP_AVSEQDUMP_END, 8) != 0) return -5;
    info->total_crc32 = get32(in + info->off_footer + 8);
    if (gbp_crc32(in, (size_t)info->off_footer) != info->total_crc32) return -6;
    /* every stored VIDEO block's CRC against its bytes; raw offsets inside the raw section */
    for (i = 0; i < info->video_count; i++) {
        const uint8_t *rec = in + info->off_video_table + (size_t)i * GBP_AVSEQDUMP_VIDEO_REC;
        uint32_t roff = get32(rec + VR_RAW_OFF), rlen = get32(rec + VR_RAW_LEN), crc = get32(rec + VR_CRC);
        uint8_t flags = rec[VR_FLAGS];
        if (!(flags & 1u)) { if (rlen != 0u) return -4; continue; }
        if (rlen != GBP_AVSEQ_VIDEO_BLOCK_SIZE || roff < info->off_video_raw || (size_t)roff + rlen > end_vraw ||
            ((roff - info->off_video_raw) % GBP_AVSEQ_VIDEO_BLOCK_SIZE) != 0u) return -4;
        if ((flags & 16u) && gbp_crc32(in + roff, rlen) != crc) return -7;
    }
    for (i = 0; i < info->audio_count; i++) {
        const uint8_t *rec = in + info->off_audio_table + (size_t)i * GBP_AVSEQDUMP_AUDIO_REC;
        uint16_t ri = get16(rec + AR_RAW_INDEX);
        uint8_t flags = rec[AR_FLAGS];
        if (ri != 0xFFFFu) {
            if (ri >= info->audio_raw_count) return -4;
            if ((flags & 16u) && gbp_crc32(in + info->off_audio_raw + (size_t)ri * GBP_AVSEQ_AUDIO_BLOCK_SIZE, GBP_AVSEQ_AUDIO_BLOCK_SIZE) != get32(rec + AR_CRC)) return -7;
        }
    }
    if (cycles) *cycles = in + info->off_cycles;
    if (vtable) *vtable = in + info->off_video_table;
    if (atable) *atable = in + info->off_audio_table;
    if (video_raw) *video_raw = in + info->off_video_raw;
    if (audio_raw) *audio_raw = in + info->off_audio_raw;
    return 0;
}
