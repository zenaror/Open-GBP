#include "gbp_avblock.h"

#include <string.h>
#include "gbp_crc32.h"

void gbp_avblock_init(struct gbp_avblock *b, const char *kind, unsigned index, uint16_t source_bit,
                      uint8_t *buf, uint32_t cap, uint32_t len)
{
    memset(b, 0, sizeof *b);
    b->kind = kind;
    b->index = index;
    b->source_bit = source_bit;
    b->buf = buf;
    b->cap = cap;
    b->len = len;
    b->rc = GBP_OK;
}

static uint32_t now(const struct gbp_transport *t)
{
    return t->ticks ? t->ticks(t->ctx) : 0u;
}

gbp_status gbp_avblock_read(const struct gbp_transport *t, uint32_t base, struct gbp_avblock *b, unsigned *errors)
{
    b->addr = gbp_block_addr(base, b->index, 0);
    if (!t->read_bulk || !b->buf || b->cap < b->len || b->addr == 0u) {
        b->rc = GBP_ERR_BACKEND;                 /* nothing was started: attempted stays 0 */
        if (errors) (*errors)++;
        return b->rc;
    }
    memset(&b->info, 0, sizeof b->info);
    b->attempted = 1;                            /* before the transport call: the device may take the transfer whatever rc says */
    b->t_start = now(t);
    b->rc = t->read_bulk(t->ctx, b->addr, b->buf, b->len, &b->info);
    b->t_end = now(t);
    b->completed = (b->rc == GBP_OK) ? 1 : 0;
    if (b->rc != GBP_OK && errors) (*errors)++;
    return b->rc;
}

void gbp_avblock_window_offsets(uint32_t len, uint32_t out[GBP_AVBLOCK_WINDOWS])
{
    out[0] = 0;
    out[1] = (len / 3u) & ~(GBP_BLOCK_SIZE - 1u);
    out[2] = ((2u * len) / 3u) & ~(GBP_BLOCK_SIZE - 1u);
    out[3] = (len >= GBP_BLOCK_SIZE) ? len - GBP_BLOCK_SIZE : 0u;
}

void gbp_avblock_summarize(struct gbp_avblock *b)
{
    uint8_t seen[256];
    uint32_t i;
    if (!b->completed || !b->buf) return;
    memset(seen, 0, sizeof seen);
    b->crc32 = gbp_crc32(b->buf, b->len);
    b->zeros = 0;
    for (i = 0; i < b->len; i++) {
        if (b->buf[i] == 0u) b->zeros++;
        seen[b->buf[i]] = 1;
    }
    b->distinct = 0;
    for (i = 0; i < 256u; i++) if (seen[i]) b->distinct++;
    gbp_avblock_window_offsets(b->len, b->w_off);
    b->first_word = (b->len >= 4u) ? ((uint32_t)b->buf[0] << 24) | ((uint32_t)b->buf[1] << 16) | ((uint32_t)b->buf[2] << 8) | (uint32_t)b->buf[3] : 0u;
    b->gbi_frame_start = ((b->first_word & GBP_AVBLOCK_GBI_FRAME_START_MASK) == GBP_AVBLOCK_GBI_FRAME_START_MASK) ? 1 : 0;
    b->summarized = 1;
}

void gbp_avblock_log_read(struct ringlog *log, const char *tag, const struct gbp_avblock *b)
{
    if (!b->attempted) {
        ringlog_printf(log, "%s idx=%x addr=%08lx len=%04lx selected=%d attempted=0 rc=-", tag, b->index, (unsigned long)b->addr,
                       (unsigned long)b->len, b->selected);
        return;
    }
    ringlog_printf(log, "%s idx=%x addr=%08lx len=%04lx selected=%d attempted=1 completed=%d rc=%s t_start=%lu t_end=%lu dt=%lu wait_ticks=%lu polls=%u csr_before=%04x csr_after=%04x",
                   tag, b->index, (unsigned long)b->addr, (unsigned long)b->len, b->selected, b->completed, gbp_status_name(b->rc),
                   (unsigned long)b->t_start, (unsigned long)b->t_end, (unsigned long)(uint32_t)(b->t_end - b->t_start),
                   (unsigned long)b->info.ticks, (unsigned)b->info.polls, (unsigned)b->info.dma_status_before, (unsigned)b->info.dma_status);
}

void gbp_avblock_log_summary(struct ringlog *log, const struct gbp_avblock *b)
{
    char hex[GBP_BLOCK_SIZE * 2 + 1];
    unsigned k;
    if (!b->attempted) {
        ringlog_printf(log, "BLOCK kind=%s idx=%x len=%04lx present=0 valid=0", b->kind, b->index, (unsigned long)b->len);
        return;
    }
    if (!b->summarized) {
        ringlog_printf(log, "BLOCK kind=%s idx=%x len=%04lx present=1 valid=0 rc=%s summary=-", b->kind, b->index,
                       (unsigned long)b->len, gbp_status_name(b->rc));
        return;
    }
    ringlog_printf(log, "BLOCK kind=%s idx=%x len=%04lx present=1 valid=1 crc32=%08lx zeros=%lu distinct=%lu w_off=%04lx,%04lx,%04lx,%04lx first_word=%08lx gbi_frame_start=%d",
                   b->kind, b->index, (unsigned long)b->len, (unsigned long)b->crc32, (unsigned long)b->zeros, (unsigned long)b->distinct,
                   (unsigned long)b->w_off[0], (unsigned long)b->w_off[1], (unsigned long)b->w_off[2], (unsigned long)b->w_off[3],
                   (unsigned long)b->first_word, b->gbi_frame_start);
    for (k = 0; k < GBP_AVBLOCK_WINDOWS; k++) {
        if (b->w_off[k] + GBP_BLOCK_SIZE > b->len) continue;
        ringlog_hex(hex, sizeof hex, b->buf + b->w_off[k], GBP_BLOCK_SIZE);
        ringlog_printf(log, "BLOCKW kind=%s off=%04lx data=%s", b->kind, (unsigned long)b->w_off[k], hex);
    }
}
