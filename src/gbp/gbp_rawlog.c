#include "gbp_rawlog.h"

#include <string.h>
#include "gbp_detect.h"

uint16_t gbp_irq_value_disc(const uint8_t block[GBP_BLOCK_SIZE])
{
    return (uint16_t)((block[0x1D] << 8) | block[0x1F]);
}

uint16_t gbp_irq_value_gbi(const uint8_t block[GBP_BLOCK_SIZE])
{
    uint8_t hi[8], lo[8];
    unsigned k;
    for (k = 0; k < 8; k++) { hi[k] = block[4 * k + 1]; lo[k] = block[4 * k + 3]; }
    return (uint16_t)((gbp_majority_vote_byte_n(hi, 8) << 8) | gbp_majority_vote_byte_n(lo, 8));
}

gbp_status gbp_rawlog_read_block(const struct gbp_transport *t, struct ringlog *log, const char *tag,
                                 uint32_t base, unsigned idx, uint8_t out[GBP_BLOCK_SIZE], unsigned *errors)
{
    struct gbp_xfer_info info;
    char hex[GBP_BLOCK_SIZE * 2 + 1];
    uint32_t addr = gbp_block_addr(base, idx, 0);
    gbp_status rc;

    memset(&info, 0, sizeof info);
    memset(out, 0, GBP_BLOCK_SIZE);
    rc = t->read_block(t->ctx, addr, out, &info);
    if (rc != GBP_OK && errors) (*errors)++;
    ringlog_hex(hex, sizeof hex, out, GBP_BLOCK_SIZE);
    if (idx == GBP_IDX_CONTROL) {
        ringlog_printf(log, "RAW %s idx=%x addr=%08lx rc=%s ticks=%lu polls=%u dspcr=%04x sem_vote=%02x sem_b1f=%02x data=%s",
                       tag, idx, (unsigned long)addr, gbp_status_name(rc), (unsigned long)info.ticks,
                       (unsigned)info.polls, (unsigned)info.dma_status,
                       (unsigned)gbp_majority_vote_byte(out), (unsigned)out[GBP_BLOCK_SIZE - 1u],
                       rc == GBP_OK ? hex : "-");
    } else if (idx == GBP_IDX_IRQ) {
        ringlog_printf(log, "RAW %s idx=%x addr=%08lx rc=%s ticks=%lu polls=%u dspcr=%04x sem_disc=%04x sem_gbi=%04x data=%s",
                       tag, idx, (unsigned long)addr, gbp_status_name(rc), (unsigned long)info.ticks,
                       (unsigned)info.polls, (unsigned)info.dma_status,
                       (unsigned)gbp_irq_value_disc(out), (unsigned)gbp_irq_value_gbi(out),
                       rc == GBP_OK ? hex : "-");
    } else {
        ringlog_printf(log, "RAW %s idx=%x addr=%08lx rc=%s ticks=%lu polls=%u dspcr=%04x data=%s",
                       tag, idx, (unsigned long)addr, gbp_status_name(rc), (unsigned long)info.ticks,
                       (unsigned)info.polls, (unsigned)info.dma_status, rc == GBP_OK ? hex : "-");
    }
    return rc;
}

int gbp_rawlog_read_pi(const struct gbp_transport *t, struct ringlog *log, const char *tag,
                       uint32_t *intsr, uint32_t *intmr)
{
    gbp_status rc;
    if (!t->read_pi) {
        ringlog_printf(log, "PI %s rc=unavailable", tag);
        return 0;
    }
    rc = t->read_pi(t->ctx, intsr, intmr);
    if (rc != GBP_OK) {
        ringlog_printf(log, "PI %s rc=%s", tag, gbp_status_name(rc));
        return 0;
    }
    ringlog_printf(log, "PI %s intsr=%08lx intmr=%08lx intsr13=%u intmr13=%u", tag,
                   (unsigned long)*intsr, (unsigned long)*intmr,
                   (*intsr & GBP_PI_HSP_BIT) ? 1u : 0u, (*intmr & GBP_PI_HSP_BIT) ? 1u : 0u);
    return 1;
}
