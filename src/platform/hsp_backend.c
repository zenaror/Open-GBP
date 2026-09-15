#include "hsp_backend.h"

#include <string.h>
#include <gccore.h>
#include <ogc/lwp_watchdog.h>
#include <ogc/machine/processor.h>

/*
 * DSP interface registers (YAGCD 5.9 / libogc aram.c / Start-up Disc).
 * All 16-bit. Offsets from 0xCC005000.
 */
#define DSP_BASE        0xCC005000u
#define DSP_CSR         (*(vu16 *)(DSP_BASE + 0x0A))
#define DSP_AR_INFO     (*(vu16 *)(DSP_BASE + 0x12))
#define DSP_AR_MMADDR_H (*(vu16 *)(DSP_BASE + 0x20))
#define DSP_AR_MMADDR_L (*(vu16 *)(DSP_BASE + 0x22))
#define DSP_AR_ARADDR_H (*(vu16 *)(DSP_BASE + 0x24))
#define DSP_AR_ARADDR_L (*(vu16 *)(DSP_BASE + 0x26))
#define DSP_AR_CNT_H    (*(vu16 *)(DSP_BASE + 0x28))
#define DSP_AR_CNT_L    (*(vu16 *)(DSP_BASE + 0x2A))

/* DSP CSR bits used here (libogc DSPCR_*): */
#define CSR_AIINT   0x0008u   /* AI DMA interrupt flag (write 1 clears)   */
#define CSR_ARINT   0x0020u   /* ARAM DMA interrupt flag (write 1 clears) */
#define CSR_DSPINT  0x0080u   /* DSP interrupt flag (write 1 clears)      */
#define CSR_DSPDMA  0x0200u   /* ARAM DMA in progress                     */

/* Processor Interface. This file only READS INTMR (0xCC003004); the only
 * PI write it contains is the INTSR write-1-to-clear (h_write_intsr).
 * Everything that changes INTMR or installs a handler lives in
 * hsp_backend_irq.c, which a POC links only when it needs it. */
#define PI_INTSR (*(vu32 *)0xCC003000u)
#define PI_INTMR (*(vu32 *)0xCC003004u)

#define DIR_MRAM_TO_ARAM 0u
#define DIR_ARAM_TO_MRAM 1u

uint16_t hsp_backend_read_csr(void)
{
    return DSP_CSR;
}

static gbp_status dma(struct hsp_backend *b, unsigned dir, uint32_t aram_addr,
                      struct gbp_xfer_info *info)
{
    uint32_t level;
    uint32_t mem = MEM_VIRTUAL_TO_PHYSICAL(b->buffer);
    uint32_t t0, now;
    uint16_t csr;
    unsigned polls = 0;
    gbp_status rc = GBP_OK;

    if (info) memset(info, 0, sizeof *info);
    b->transfers++;

    _CPU_ISR_Disable(level);
    csr = DSP_CSR;
    b->last_csr_before = csr;
    if (csr & (CSR_DSPDMA | CSR_ARINT)) {
        /* Engine busy or a stale completion flag: refuse, like the disc. */
        _CPU_ISR_Restore(level);
        b->busy_refusals++;
        if (info) { info->dma_status = csr; }
        return GBP_ERR_BUSY;
    }
    DSP_AR_MMADDR_H = (u16)((mem >> 16) & 0x03FFu);
    DSP_AR_MMADDR_L = (u16)(mem & 0xFFE0u);
    DSP_AR_ARADDR_H = (u16)((aram_addr >> 16) & 0x03FFu);
    DSP_AR_ARADDR_L = (u16)(aram_addr & 0xFFE0u);
    DSP_AR_CNT_H    = (u16)(((dir & 1u) << 15) | ((GBP_BLOCK_SIZE >> 16) & 0x03FFu));
    DSP_AR_CNT_L    = (u16)(GBP_BLOCK_SIZE & 0xFFE0u);   /* writing CNT_L starts the DMA */

    t0 = gettick();
    for (;;) {
        csr = DSP_CSR;
        polls++;
        if (csr & CSR_ARINT) break;
        now = gettick();
        if ((uint32_t)(now - t0) > b->timeout_ticks) {
            rc = GBP_ERR_TIMEOUT;
            b->timeouts++;
            break;
        }
    }
    now = gettick();
    if (rc == GBP_OK) {
        /* Acknowledge only the ARAM flag: keep AI/DSP flags untouched
         * (they are write-1-to-clear too). */
        DSP_CSR = (u16)((csr & (u16)~(CSR_AIINT | CSR_DSPINT)) | CSR_ARINT);
    }
    b->last_csr_after = DSP_CSR;
    _CPU_ISR_Restore(level);

    if (info) {
        info->ticks = (uint32_t)(now - t0);
        info->polls = (uint16_t)(polls > 0xFFFFu ? 0xFFFFu : polls);
        info->dma_status = b->last_csr_after;
    }
    return rc;
}

static gbp_status h_read_arinfo(void *ctx, uint16_t *value)
{
    (void)ctx;
    *value = DSP_AR_INFO;
    return GBP_OK;
}

static gbp_status h_write_arinfo(void *ctx, uint16_t value)
{
    (void)ctx;
    DSP_AR_INFO = value;
    return GBP_OK;
}

static gbp_status h_read_block(void *ctx, uint32_t aram_addr, uint8_t out[GBP_BLOCK_SIZE],
                               struct gbp_xfer_info *info)
{
    struct hsp_backend *b = (struct hsp_backend *)ctx;
    gbp_status rc;
    if ((aram_addr & (GBP_BLOCK_SIZE - 1u)) != 0u) return GBP_ERR_PARAM;
    memset(b->buffer, 0, GBP_BLOCK_SIZE);
    DCFlushRange(b->buffer, GBP_BLOCK_SIZE);      /* push the zero fill out, then drop the line */
    DCInvalidateRange(b->buffer, GBP_BLOCK_SIZE);
    rc = dma(b, DIR_ARAM_TO_MRAM, aram_addr, info);
    DCInvalidateRange(b->buffer, GBP_BLOCK_SIZE); /* make sure we read what the DMA wrote */
    memcpy(out, b->buffer, GBP_BLOCK_SIZE);
    return rc;
}

static gbp_status h_write_block(void *ctx, uint32_t aram_addr, const uint8_t in[GBP_BLOCK_SIZE],
                                struct gbp_xfer_info *info)
{
    struct hsp_backend *b = (struct hsp_backend *)ctx;
    if ((aram_addr & (GBP_BLOCK_SIZE - 1u)) != 0u) return GBP_ERR_PARAM;
    memcpy(b->buffer, in, GBP_BLOCK_SIZE);
    DCFlushRange(b->buffer, GBP_BLOCK_SIZE);
    return dma(b, DIR_MRAM_TO_ARAM, aram_addr, info);
}

static gbp_status h_read_pi(void *ctx, uint32_t *intsr, uint32_t *intmr)
{
    (void)ctx;
    *intsr = PI_INTSR;
    *intmr = PI_INTMR;
    return GBP_OK;
}

static gbp_status h_poll_intsr(void *ctx, uint32_t *intsr)
{
    (void)ctx;
    *intsr = PI_INTSR;                            /* one MMIO read, nothing else */
    return GBP_OK;
}

static gbp_status h_write_intsr(void *ctx, uint32_t value)
{
    (void)ctx;
    /* The same write the Start-up Disc (0x8008af08, 0x8008be04) and GBI
     * (0x8000b400) perform: write-1-to-clear (GBP-PI-002). */
    PI_INTSR = value;
    return GBP_OK;
}

static uint32_t h_ticks(void *ctx)
{
    (void)ctx;
    return gettick();
}

void hsp_backend_init(struct hsp_backend *b, uint8_t *buffer, uint32_t timeout_ticks)
{
    memset(b, 0, sizeof *b);
    b->buffer = buffer;
    b->timeout_ticks = timeout_ticks;
}

void hsp_backend_transport(struct hsp_backend *b, struct gbp_transport *t)
{
    memset(t, 0, sizeof *t);
    t->read_arinfo = h_read_arinfo;
    t->write_arinfo = h_write_arinfo;
    t->read_block = h_read_block;
    t->write_block = h_write_block;
    t->read_pi = h_read_pi;
    t->poll_intsr = h_poll_intsr;
    t->write_intsr = h_write_intsr;
    /* write_intmr and the irq_* operations stay NULL unless the POC also
     * links hsp_backend_irq.c and calls hsp_backend_irq_transport(). */
    t->ticks = h_ticks;
    t->ctx = b;
}
