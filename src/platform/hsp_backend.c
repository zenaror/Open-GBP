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

#define PI_INTSR (*(vu32 *)0xCC003000u)
#define PI_INTMR (*(vu32 *)0xCC003004u)

#define DIR_MRAM_TO_ARAM 0u
#define DIR_ARAM_TO_MRAM 1u

/*
 * ---- PI HSP interrupt path -------------------------------------------
 *
 * One-shot handler for OS interrupt 26 (libogc2 IRQ_PI_HSP). Its body is
 * shared with the host mock (src/gbp/gbp_irq_oneshot.h); the primitives
 * below are the only things it can call: the time base, the two PI
 * registers, and libogc2's __MaskIrq (shadow-mask update + INTMR rebuild,
 * ENV-IRQ-002). No DMA, no allocation, no logging, no GBP access.
 * The record is a single static instance because a libogc2 handler
 * receives no context pointer.
 */
static volatile struct gbp_irq_record hsp_irq_rec;

#define GBP_IRQ_PRIM_TICKS()        gettick()
#define GBP_IRQ_PRIM_READ_INTSR()   PI_INTSR
#define GBP_IRQ_PRIM_READ_INTMR()   PI_INTMR
#define GBP_IRQ_PRIM_MASK()         __MaskIrq(IM_PI_HSP)
#define GBP_IRQ_PRIM_WRITE_INTSR(v) (PI_INTSR = (v))
#include "../gbp/gbp_irq_oneshot.h"

void hsp_backend_oneshot_isr(u32 irq, frame_context *ctx)
{
    (void)irq;
    (void)ctx;
    gbp_irq_oneshot_service(&hsp_irq_rec);
}

static void irq_rec_clear(void)
{
    hsp_irq_rec.count = 0;
    hsp_irq_rec.fired = 0;
    hsp_irq_rec.t_entry = 0;
    hsp_irq_rec.intsr_before_ack = 0;
    hsp_irq_rec.intmr_at_entry = 0;
    hsp_irq_rec.intsr_after_ack = 0;
    hsp_irq_rec.intmr_after_mask = 0;
    hsp_irq_rec.reentry_intsr = 0;
    hsp_irq_rec.reentry_intmr = 0;
}

static gbp_status h_irq_install(void *ctx, int *old_was_null)
{
    struct hsp_backend *b = (struct hsp_backend *)ctx;
    if (b->handler_installed) return GBP_ERR_PARAM;
    irq_rec_clear();
    /* IRQ_Request returns the previous handler (binary-verified in
     * r2442.094b250, ENV-IRQ-002). Kept verbatim, NULL or not. */
    b->old_handler = IRQ_Request(IRQ_PI_HSP, hsp_backend_oneshot_isr);
    b->handler_installed = 1;
    if (old_was_null) *old_was_null = (b->old_handler == 0) ? 1 : 0;
    return GBP_OK;
}

static gbp_status h_irq_restore(void *ctx)
{
    struct hsp_backend *b = (struct hsp_backend *)ctx;
    irq_handler_t current;
    if (!b->handler_installed) return GBP_OK;
    /* Putting a NULL previous handler back has the same effect as IRQ_Free. */
    current = IRQ_Request(IRQ_PI_HSP, b->old_handler);
    b->handler_installed = 0;
    return (current == hsp_backend_oneshot_isr) ? GBP_OK : GBP_ERR_BACKEND;
}

static gbp_status h_irq_mask(void *ctx)
{
    (void)ctx;
    __MaskIrq(IM_PI_HSP);
    return GBP_OK;
}

static gbp_status h_irq_unmask(void *ctx)
{
    (void)ctx;
    __UnmaskIrq(IM_PI_HSP);
    return GBP_OK;
}

static gbp_status h_irq_record(void *ctx, struct gbp_irq_record *out)
{
    (void)ctx;
    out->count = hsp_irq_rec.count;
    out->fired = hsp_irq_rec.fired;
    out->t_entry = hsp_irq_rec.t_entry;
    out->intsr_before_ack = hsp_irq_rec.intsr_before_ack;
    out->intmr_at_entry = hsp_irq_rec.intmr_at_entry;
    out->intsr_after_ack = hsp_irq_rec.intsr_after_ack;
    out->intmr_after_mask = hsp_irq_rec.intmr_after_mask;
    out->reentry_intsr = hsp_irq_rec.reentry_intsr;
    out->reentry_intmr = hsp_irq_rec.reentry_intmr;
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

static gbp_status h_write_intmr(void *ctx, uint32_t intmr)
{
    (void)ctx;
    /* Same register write libogc2's __SetInterrupts performs (_piReg[1] = imask). */
    PI_INTMR = intmr;
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
    t->read_arinfo = h_read_arinfo;
    t->write_arinfo = h_write_arinfo;
    t->read_block = h_read_block;
    t->write_block = h_write_block;
    t->read_pi = h_read_pi;
    t->write_intmr = h_write_intmr;
    t->write_intsr = h_write_intsr;
    t->irq_install = h_irq_install;
    t->irq_restore = h_irq_restore;
    t->irq_mask = h_irq_mask;
    t->irq_unmask = h_irq_unmask;
    t->irq_record = h_irq_record;
    t->ticks = h_ticks;
    t->ctx = b;
}
