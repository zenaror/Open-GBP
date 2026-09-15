#include "hsp_backend_irq.h"

#include <gccore.h>
#include <ogc/lwp_watchdog.h>

#define PI_INTSR (*(vu32 *)0xCC003000u)
#define PI_INTMR (*(vu32 *)0xCC003004u)

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

static gbp_status h_write_intmr(void *ctx, uint32_t intmr)
{
    (void)ctx;
    /* Same register write libogc2's __SetInterrupts performs (_piReg[1] = imask).
     * Used by GBP-INIT-001 only; later probes go through __MaskIrq/__UnmaskIrq. */
    PI_INTMR = intmr;
    return GBP_OK;
}

void hsp_backend_irq_transport(struct hsp_backend *b, struct gbp_transport *t)
{
    (void)b;
    t->write_intmr = h_write_intmr;
    t->irq_install = h_irq_install;
    t->irq_restore = h_irq_restore;
    t->irq_mask = h_irq_mask;
    t->irq_unmask = h_irq_unmask;
    t->irq_record = h_irq_record;
}
