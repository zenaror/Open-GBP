#include "gbp_avseq.h"

#include <stdio.h>
#include <string.h>
#include "gbp_crc32.h"
#include "gbp_rawlog.h"

void gbp_avseq_store_init(struct gbp_avseq_store *s, uint8_t *video_raw, uint32_t video_raw_cap,
                          uint8_t *audio_raw, uint32_t audio_raw_cap)
{
    memset(s, 0, sizeof *s);
    s->video_raw = video_raw;
    s->video_raw_cap = video_raw_cap;
    s->audio_raw = audio_raw;
    s->audio_raw_cap = audio_raw_cap;
    s->audio_last_valid = -1;
    s->audio_last_next = GBP_AVSEQ_AUDIO_FIRST_KEPT;
}

void gbp_avseq_cycle_init(struct gbp_avseq_cycle *c, unsigned idx)
{
    memset(c, 0, sizeof *c);
    c->idx = (uint16_t)idx;
    c->audio_slot = GBP_AVSEQ_SLOT_NONE;
    c->video_seq = GBP_AVSEQ_VIDEO_SEQ_NONE;
    c->irq_rc = GBP_OK;
}

int gbp_avseq_flag_gbi(const uint8_t first4[4])
{
    uint32_t w = ((uint32_t)first4[0] << 24) | ((uint32_t)first4[1] << 16) | ((uint32_t)first4[2] << 8) | (uint32_t)first4[3];
    return ((w & GBP_AVSEQ_GBI_FRAME_START_MASK) == GBP_AVSEQ_GBI_FRAME_START_MASK) ? 1 : 0;
}

int gbp_avseq_flag_disc(const uint8_t first4[4])
{
    uint16_t hw = (uint16_t)(((uint16_t)first4[0] << 8) | first4[1]);
    return (((hw >> 7) & 1u) != 0u) ? 1 : 0;
}

uint8_t *gbp_avseq_video_target(struct gbp_avseq_store *s)
{
    uint32_t off;
    if (!s->video_raw || s->vblocks_n >= GBP_AVSEQ_MAX_VIDEO_BLOCKS) return 0;
    off = s->vblocks_n * GBP_AVSEQ_VIDEO_BLOCK_SIZE;
    if (off + GBP_AVSEQ_VIDEO_BLOCK_SIZE > s->video_raw_cap) return 0;
    return s->video_raw + off;
}

struct gbp_avseq_vblock *gbp_avseq_video_commit(struct gbp_avseq_store *s, unsigned cycle, uint16_t pending,
                                                gbp_status rc, const struct gbp_xfer_info *info,
                                                uint32_t t_start, uint32_t t_end)
{
    struct gbp_avseq_vblock *v;
    if (s->vblocks_n >= GBP_AVSEQ_MAX_VIDEO_BLOCKS) return 0;
    v = &s->vblocks[s->vblocks_n];
    memset(v, 0, sizeof *v);
    v->seq = (uint16_t)s->vblocks_n;
    v->cycle = (uint16_t)cycle;
    v->pending = pending;
    v->rc = (uint8_t)rc;
    v->completed = (rc == GBP_OK) ? 1u : 0u;
    v->t_start = t_start;
    v->t_end = t_end;
    if (info) { v->wait_ticks = info->ticks; v->polls = info->polls; v->csr_before = info->dma_status_before; v->csr_after = info->dma_status; }
    s->vblocks_n++;                       /* the slot is consumed whether or not the DMA completed: a failed read ends the loop */
    return v;
}

uint8_t *gbp_avseq_audio_target(struct gbp_avseq_store *s, unsigned *raw_slot)
{
    unsigned slot;
    if (!s->audio_raw) return 0;
    slot = (s->audio_first_kept < GBP_AVSEQ_AUDIO_FIRST_KEPT) ? s->audio_first_kept : s->audio_last_next;
    if ((uint32_t)(slot + 1u) * GBP_AVSEQ_AUDIO_BLOCK_SIZE > s->audio_raw_cap) return 0;
    if (raw_slot) *raw_slot = slot;
    return s->audio_raw + (uint32_t)slot * GBP_AVSEQ_AUDIO_BLOCK_SIZE;
}

struct gbp_avseq_ablock *gbp_avseq_audio_commit(struct gbp_avseq_store *s, unsigned cycle, unsigned raw_slot,
                                                gbp_status rc, const struct gbp_xfer_info *info,
                                                uint32_t t_start, uint32_t t_end)
{
    struct gbp_avseq_ablock *a;
    if (s->ablocks_n >= GBP_AVSEQ_MAX_AUDIO_BLOCKS) return 0;
    a = &s->ablocks[s->ablocks_n++];
    memset(a, 0, sizeof *a);
    a->cycle = (uint16_t)cycle;
    a->selected = 1;
    a->attempted = 1;
    a->completed = (rc == GBP_OK) ? 1u : 0u;
    a->rc = (uint8_t)rc;
    a->slot = GBP_AVSEQ_SLOT_NONE;
    a->raw_index = 0xFFFFu;
    a->t_start = t_start;
    a->t_end = t_end;
    if (info) a->wait_ticks = info->ticks;
    if (!a->completed) return a;          /* nothing valid changes: the previous last-valid buffer stays untouched */
    s->audio_drains_completed++;
    if (raw_slot < GBP_AVSEQ_AUDIO_FIRST_KEPT) {
        a->slot = (uint8_t)raw_slot;
        a->raw_kept = 1;
        a->raw_index = (uint16_t)raw_slot;
        s->audio_first_kept++;
    } else {
        a->slot = (uint8_t)(GBP_AVSEQ_SLOT_LAST | (raw_slot - GBP_AVSEQ_AUDIO_FIRST_KEPT));
        a->raw_kept = 1;                  /* kept until a later drain completes into the other buffer */
        a->raw_index = (uint16_t)raw_slot;
        s->audio_last_valid = (int)raw_slot;
        s->audio_last_next = (raw_slot == GBP_AVSEQ_AUDIO_FIRST_KEPT) ? GBP_AVSEQ_AUDIO_FIRST_KEPT + 1u : GBP_AVSEQ_AUDIO_FIRST_KEPT;
    }
    return a;
}

unsigned gbp_avseq_audio_raw_count(const struct gbp_avseq_store *s)
{
    return s->audio_first_kept + ((s->audio_last_valid >= (int)GBP_AVSEQ_AUDIO_FIRST_KEPT) ? 1u : 0u);
}

const uint8_t *gbp_avseq_video_bytes(const struct gbp_avseq_store *s, unsigned seq)
{
    if (!s->video_raw || seq >= s->vblocks_n) return 0;
    return s->video_raw + (uint32_t)seq * GBP_AVSEQ_VIDEO_BLOCK_SIZE;
}

const uint8_t *gbp_avseq_audio_bytes(const struct gbp_avseq_store *s, unsigned raw_slot)
{
    if (!s->audio_raw || raw_slot >= GBP_AVSEQ_AUDIO_RAW_SLOTS) return 0;
    return s->audio_raw + (uint32_t)raw_slot * GBP_AVSEQ_AUDIO_BLOCK_SIZE;
}

void gbp_avseq_summarize(struct gbp_avseq_store *s)
{
    unsigned i;
    for (i = 0; i < s->vblocks_n; i++) {
        struct gbp_avseq_vblock *v = &s->vblocks[i];
        const uint8_t *b = gbp_avseq_video_bytes(s, i);
        uint32_t k;
        if (!v->completed || !b) continue;
        memcpy(v->raw_first4, b, 4);
        v->flag_gbi = (uint8_t)gbp_avseq_flag_gbi(v->raw_first4);
        v->flag_disc = (uint8_t)gbp_avseq_flag_disc(v->raw_first4);
        v->flags_agree = (v->flag_gbi == v->flag_disc) ? 1u : 0u;
        v->crc32 = gbp_crc32(b, GBP_AVSEQ_VIDEO_BLOCK_SIZE);
        v->byte0_exceptions = 0;
        v->undoubled_words = 0;
        for (k = 0; k + 4u <= GBP_AVSEQ_VIDEO_BLOCK_SIZE; k += 4u) {
            int b01 = (b[k] != b[k + 1u]);
            int b23 = (b[k + 2u] != b[k + 3u]);
            if (b01) v->byte0_exceptions++;
            if (b01 || b23) v->undoubled_words++;
        }
        v->summarized = 1;
    }
    for (i = 0; i < s->ablocks_n; i++) {
        struct gbp_avseq_ablock *a = &s->ablocks[i];
        const uint8_t *b;
        uint32_t k;
        if (!a->completed || a->raw_index == 0xFFFFu) continue;
        b = gbp_avseq_audio_bytes(s, a->raw_index);
        if (!b) continue;
        /* a ping-pong slot holds the LAST completed drain that targeted it: earlier drains of the same slot were overwritten */
        if (a->raw_index >= GBP_AVSEQ_AUDIO_FIRST_KEPT && (int)a->raw_index != s->audio_last_valid) {
            a->raw_kept = 0;
            continue;
        }
        if (a->raw_index >= GBP_AVSEQ_AUDIO_FIRST_KEPT) {
            /* the last valid buffer: only the most recent drain that completed into it still owns the bytes */
            unsigned j;
            int newer = 0;
            for (j = i + 1u; j < s->ablocks_n; j++) if (s->ablocks[j].completed && s->ablocks[j].raw_index == a->raw_index) newer = 1;
            if (newer) { a->raw_kept = 0; continue; }
        }
        a->crc32 = gbp_crc32(b, GBP_AVSEQ_AUDIO_BLOCK_SIZE);
        a->first_word = ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16) | ((uint32_t)b[2] << 8) | (uint32_t)b[3];
        a->nonzero = 0;
        a->unit0_nonzero = 0;
        for (k = 0; k < GBP_AVSEQ_AUDIO_BLOCK_SIZE; k++) {
            if (b[k]) { a->nonzero++; if ((k & 31u) == 0u) a->unit0_nonzero++; }
        }
        a->summarized = 1;
    }
}

void gbp_avseq_boundaries(const struct gbp_avseq_store *s, int use_disc, struct gbp_avseq_boundaries *out)
{
    unsigned i;
    memset(out, 0, sizeof *out);
    for (i = 0; i < s->vblocks_n; i++) {
        const struct gbp_avseq_vblock *v = &s->vblocks[i];
        int flag = use_disc ? v->flag_disc : v->flag_gbi;
        if (!v->completed || !v->summarized || !flag) continue;
        if (out->count) out->intervals[out->intervals_n++] = i - out->positions[out->count - 1u];
        out->positions[out->count++] = i;
    }
    out->complete_interval = (out->count >= 2u) ? 1 : 0;
}

const char *gbp_avseq_end_name(int e)
{
    switch (e) {
    case GBP_AVSEQ_END_TARGET_REACHED: return "target_reached";
    case GBP_AVSEQ_END_DELIVERY_CAP: return "delivery_cap";
    case GBP_AVSEQ_END_RUNTIME_CAP: return "runtime_cap";
    case GBP_AVSEQ_END_NO_NEXT_CAUSE: return "no_next_cause";
    case GBP_AVSEQ_END_EARLY_FAILURE: return "early_failure";
    default: return "-";
    }
}

const char *gbp_avseq_next_end_name(int e)
{
    switch (e) {
    case GBP_AVSEQ_NEXT_CAUSE: return "cause";
    case GBP_AVSEQ_NEXT_TIMEOUT: return "t_next_cause";
    case GBP_AVSEQ_NEXT_DEADLINE: return "admission_deadline";
    case GBP_AVSEQ_NEXT_SINGLE_READ: return "single_read";
    default: return "-";
    }
}

/* the register-window base behind a block address (base + index << 20) */
static uint32_t irq_base_of(uint32_t video_addr)
{
    return video_addr - ((uint32_t)GBP_AVSEQ_VIDEO_INDEX << 20);
}

static const char *slot_name(uint8_t slot, char *buf)
{
    if (slot == GBP_AVSEQ_SLOT_NONE) return "-";
    if (slot & GBP_AVSEQ_SLOT_LAST) { buf[0] = 'L'; buf[1] = (char)('0' + (slot & 1u)); buf[2] = '\0'; return buf; }
    buf[0] = (char)('0' + (slot & 0xFu)); buf[1] = '\0';
    return buf;
}

void gbp_avseq_log_cycle(struct ringlog *log, const struct gbp_avseq_cycle *c, uint32_t audio_addr, uint32_t video_addr)
{
    char sb[4];
    /* CYCU: admission, PREPARE, the delivery — every value a replay needs, in the order the transport was used */
    ringlog_printf(log, "CYCU n=%u verify=%u t_adm=%lu prep=%08lx/%08lx/%s pre=%08lx/%08lx t_unmask=%lu t_post=%lu post=%08lx/%08lx rec0=%lu",
                   (unsigned)c->idx, (unsigned)c->verify, (unsigned long)c->t_adm, (unsigned long)c->intsr_prep, (unsigned long)c->intmr_prep,
                   gbp_status_name((gbp_status)c->prep_rc), (unsigned long)c->intsr_pre, (unsigned long)c->intmr_pre, (unsigned long)c->t_unmask,
                   (unsigned long)c->t_post_unmask, (unsigned long)c->intsr_post, (unsigned long)c->intmr_post, (unsigned long)c->rec0_fired);
    /* CYCW: the bounded wait for the handler and the main re-mask */
    ringlog_printf(log, "CYCW n=%u polls=%lu timed_out=%u t_wait_end=%lu remask=%08lx/%08lx retry=%u mask_ok=%u",
                   (unsigned)c->idx, (unsigned long)c->wait_polls, (unsigned)c->timed_out, (unsigned long)c->t_wait_end, (unsigned long)c->intsr_remask,
                   (unsigned long)c->intmr_remask, (unsigned)c->remask_retry, (unsigned)c->mask_ok);
    /* CYCH: the handler record in the order of a replay "I u" line (count fired t_entry intsr_at_entry intmr_at_entry
     * intsr_after_w1c intmr_after_mask reentry_intsr reentry_intmr intsr_before_w1c t_second intsr_second intmr_second reentry_t) */
    ringlog_printf(log, "CYCH n=%u rec=%u,%u,%lu,%08lx,%08lx,%08lx,%08lx,%08lx,%08lx,%08lx,%lu,%08lx,%08lx,%lu lat=%lu reentry=%u",
                   (unsigned)c->idx, (unsigned)c->isr_count, (unsigned)c->isr_fired, (unsigned long)c->t_entry,
                   (unsigned long)c->intsr_entry, (unsigned long)c->intmr_entry, (unsigned long)c->intsr_after_w1c, (unsigned long)c->intmr_after_mask,
                   (unsigned long)c->reentry_intsr, (unsigned long)c->reentry_intmr, (unsigned long)c->intsr_before_w1c, (unsigned long)c->t_second,
                   (unsigned long)c->intsr_second, (unsigned long)c->intmr_second, (unsigned long)c->reentry_t, (unsigned long)c->latency,
                   (unsigned)c->isr_reentry);
    /* RAW READ-n: the pending read verbatim, in the standard block format, so a physical log
     * regenerates a replay fixture (tools/probelog.py turns it into an "R" line). Lean cycles
     * only: a verify cycle's PRESVC snapshot already logged the same read. */
    if (!c->verify) {
        char tag[16];
        snprintf(tag, sizeof tag, "READ-%u", (unsigned)c->idx);
        gbp_rawlog_log_block(log, tag, gbp_block_addr(irq_base_of(video_addr), GBP_IDX_IRQ, 0), GBP_IDX_IRQ, c->irq_rc, &c->irq_info, c->irq_raw);
    }
    /* CYCD: the pending read, the drains, the ACK */
    ringlog_printf(log, "CYCD n=%u pend=%04x disc=%04x gbi=%04x b0=%02x o2=%02x t_read=%lu a=%u/%u/%u/%s/%s/%lu/%lu/%lu/%08lx/%08lx v=%u/%u/%u/%s/%u/%lu/%lu/%lu/%08lx ack=%u/%u/%04x/%lu",
                   (unsigned)c->idx, (unsigned)c->pending, (unsigned)c->irq_disc, (unsigned)c->irq_gbi, (unsigned)c->irq_byte0, (unsigned)c->irq_off2_g0,
                   (unsigned long)c->t_read,
                   (unsigned)c->audio_selected, (unsigned)c->audio_attempted, (unsigned)c->audio_completed,
                   c->audio_attempted ? gbp_status_name((gbp_status)c->audio_rc) : "-", slot_name(c->audio_slot, sb),
                   (unsigned long)c->t_audio_start, (unsigned long)c->t_audio_end, (unsigned long)c->audio_wait, (unsigned long)c->audio_crc32,
                   (unsigned long)audio_addr,
                   (unsigned)c->video_selected, (unsigned)c->video_attempted, (unsigned)c->video_completed,
                   c->video_attempted ? gbp_status_name((gbp_status)c->video_rc) : "-", (unsigned)c->video_seq,
                   (unsigned long)c->t_video_start, (unsigned long)c->t_video_end, (unsigned long)c->video_wait, (unsigned long)video_addr,
                   (unsigned)c->ack_attempted, (unsigned)c->ack_completed, (unsigned)c->ack_value, (unsigned long)c->t_ack_after);
    /* CYCR: PI clean, the re-arm, WAIT_NEXT */
    ringlog_printf(log, "CYCR n=%u pi=%08lx/%08lx w1c=%u after=%08lx sticky=%u relatch=%u/%u rearm=%u/%u/%lu/%lu next=%u/%s/%lu/%08lx/%lu end=%s",
                   (unsigned)c->idx, (unsigned long)c->intsr_postack, (unsigned long)c->intmr_postack, (unsigned)c->main_w1c,
                   (unsigned long)c->intsr_after_main_w1c, (unsigned)c->pi_sticky, (unsigned)c->relatch_postdrain, (unsigned)c->relatch_postack,
                   (unsigned)c->rearm_attempted, (unsigned)c->rearm_completed, (unsigned long)c->t_rearm, (unsigned long)c->t_rearm_after,
                   (unsigned)c->next_observed, gbp_avseq_next_end_name(c->next_ended_by), (unsigned long)c->t_next, (unsigned long)c->intsr_next,
                   (unsigned long)c->next_polls, gbp_avseq_end_name(c->end_reason));
}

void gbp_avseq_log_vblock(struct ringlog *log, const struct gbp_avseq_vblock *v)
{
    ringlog_printf(log, "VBLK seq=%u cyc=%u pend=%04x rc=%s completed=%u t_start=%lu t_end=%lu dt=%lu wait=%lu polls=%u csr=%04x/%04x crc32=%08lx f4=%02x%02x%02x%02x gbi=%u disc=%u agree=%u x0=%u und=%u",
                   (unsigned)v->seq, (unsigned)v->cycle, (unsigned)v->pending, gbp_status_name((gbp_status)v->rc), (unsigned)v->completed,
                   (unsigned long)v->t_start, (unsigned long)v->t_end, (unsigned long)(uint32_t)(v->t_end - v->t_start), (unsigned long)v->wait_ticks,
                   (unsigned)v->polls, (unsigned)v->csr_before, (unsigned)v->csr_after, (unsigned long)v->crc32,
                   (unsigned)v->raw_first4[0], (unsigned)v->raw_first4[1], (unsigned)v->raw_first4[2], (unsigned)v->raw_first4[3],
                   (unsigned)v->flag_gbi, (unsigned)v->flag_disc, (unsigned)v->flags_agree, (unsigned)v->byte0_exceptions, (unsigned)v->undoubled_words);
}

void gbp_avseq_log_ablock(struct ringlog *log, const struct gbp_avseq_ablock *a)
{
    char sb[4];
    ringlog_printf(log, "ABLK cyc=%u sel=%u att=%u comp=%u rc=%s slot=%s kept=%u raw=%u t_start=%lu t_end=%lu wait=%lu crc32=%08lx fw=%08lx nz=%u u0=%u",
                   (unsigned)a->cycle, (unsigned)a->selected, (unsigned)a->attempted, (unsigned)a->completed, gbp_status_name((gbp_status)a->rc),
                   slot_name(a->slot, sb), (unsigned)a->raw_kept, a->raw_index == 0xFFFFu ? 0xFFFFu : (unsigned)a->raw_index,
                   (unsigned long)a->t_start, (unsigned long)a->t_end, (unsigned long)a->wait_ticks, (unsigned long)a->crc32,
                   (unsigned long)a->first_word, (unsigned)a->nonzero, (unsigned)a->unit0_nonzero);
}

static size_t join_list(char *dst, size_t cap, const unsigned *v, unsigned n)
{
    size_t o = 0;
    unsigned i;
    dst[0] = '\0';
    for (i = 0; i < n; i++) {
        int w = snprintf(dst + o, cap - o, "%s%u", i ? "," : "", v[i]);
        if (w < 0 || (size_t)w >= cap - o) { dst[o] = '\0'; return (size_t)-1; }   /* does not fit: the caller chunks */
        o += (size_t)w;
    }
    return o;
}

/* a list too long for one line goes out in chunks of 32 values: "<kind> <predicate> i=<first index> v=<values>" */
static void log_list_chunks(struct ringlog *log, const char *kind, const char *predicate, const unsigned *v, unsigned n)
{
    char buf[200];
    unsigned i;
    for (i = 0; i < n; i += 32u) {
        unsigned m = (n - i < 32u) ? (n - i) : 32u;
        join_list(buf, sizeof buf, v + i, m);
        ringlog_printf(log, "%s %s i=%u v=%s", kind, predicate, i, buf);
    }
}

void gbp_avseq_log_boundaries(struct ringlog *log, const char *predicate, const struct gbp_avseq_boundaries *b)
{
    char pos[120], iv[120];
    size_t n = join_list(pos, sizeof pos, b->positions, b->count);
    size_t m = join_list(iv, sizeof iv, b->intervals, b->intervals_n);
    if (n != (size_t)-1 && m != (size_t)-1) {
        ringlog_printf(log, "BOUNDARIES %s=%u positions=%s intervals=%s complete_interval=%d", predicate, b->count,
                       b->count ? pos : "-", b->intervals_n ? iv : "-", b->complete_interval);
        return;
    }
    ringlog_printf(log, "BOUNDARIES %s=%u positions=BPOS intervals=BINT complete_interval=%d", predicate, b->count, b->complete_interval);
    log_list_chunks(log, "BPOS", predicate, b->positions, b->count);
    log_list_chunks(log, "BINT", predicate, b->intervals, b->intervals_n);
}
