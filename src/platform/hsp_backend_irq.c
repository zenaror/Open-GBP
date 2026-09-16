#include "hsp_backend_irq.h"

#include <gccore.h>
#include <ogc/lwp_watchdog.h>

#define PI_INTSR (*(vu32 *)0xCC003000u)
#define PI_INTMR (*(vu32 *)0xCC003004u)

/*
 * ---- PI HSP interrupt path -------------------------------------------
 *
 * The record can be reset between deliveries (irq_record_reset, GBP-VIDEO-001):
 * a memory-only clear, legal only while INTMR bit 13 = 0, so the same handler
 * serves every delivery of a repeated service with its unchanged body.
 *
 * Two one-shot handlers for OS interrupt 26 (libogc2 IRQ_PI_HSP), both
 * with bodies shared with the host mock (src/gbp/gbp_irq_oneshot.h):
 *   hsp_backend_oneshot_isr      GBP-INIT-002 body (audited, executed)
 *   hsp_backend_oneshot_isr_ext  GBP-INIT-003B body (entry state, mask,
 *                                INTMR, INTSR, one W1C, INTSR, bounded
 *                                wait, INTSR/INTMR again)
 * The primitives below are the only things they can call: the time base,
 * the two PI registers, and libogc2's __MaskIrq (shadow-mask update +
 * INTMR rebuild, ENV-IRQ-002). No DMA, no allocation, no logging, no GBP
 * access. The record is a single static instance because a libogc2
 * handler receives no context pointer. This object contains NO INTMR
 * store: the direct INTMR write of GBP-INIT-001 lives in
 * hsp_backend_intmr.c.
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

void hsp_backend_oneshot_isr_ext(u32 irq, frame_context *ctx)
{
    (void)irq;
    (void)ctx;
    gbp_irq_oneshot_service_ext(&hsp_irq_rec);
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
    hsp_irq_rec.intsr_before_w1c = 0;
    hsp_irq_rec.t_second = 0;
    hsp_irq_rec.intsr_second = 0;
    hsp_irq_rec.intmr_second = 0;
    hsp_irq_rec.reentry_t = 0;
}

static irq_handler_t selected_isr(const struct hsp_backend *b)
{
    return b->use_ext_isr ? hsp_backend_oneshot_isr_ext : hsp_backend_oneshot_isr;
}

static gbp_status h_irq_install(void *ctx, int *old_was_null)
{
    struct hsp_backend *b = (struct hsp_backend *)ctx;
    if (b->handler_installed) return GBP_ERR_PARAM;
    irq_rec_clear();
    /* IRQ_Request returns the previous handler (binary-verified in
     * r2442.094b250, ENV-IRQ-002). Kept verbatim, NULL or not. */
    b->old_handler = IRQ_Request(IRQ_PI_HSP, selected_isr(b));
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
    return (current == selected_isr(b)) ? GBP_OK : GBP_ERR_BACKEND;
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
    out->intsr_before_w1c = hsp_irq_rec.intsr_before_w1c;
    out->t_second = hsp_irq_rec.t_second;
    out->intsr_second = hsp_irq_rec.intsr_second;
    out->intmr_second = hsp_irq_rec.intmr_second;
    out->reentry_t = hsp_irq_rec.reentry_t;
    return GBP_OK;
}

/* GBP-VIDEO-001 (repeated service with the one installed handler): the
 * record back to the state the install left it in — memory only. Refused
 * while IRQ 26 is enabled (INTMR bit 13 read 1: the record belongs to the
 * handler then) and when no handler is installed. This function READS
 * INTMR and never stores to it. */
static gbp_status h_irq_record_reset(void *ctx)
{
    struct hsp_backend *b = (struct hsp_backend *)ctx;
    if (!b->handler_installed) return GBP_ERR_PARAM;
    if (PI_INTMR & GBP_PI_HSP_BIT) return GBP_ERR_BUSY;
    irq_rec_clear();
    return GBP_OK;
}

void hsp_backend_irq_transport(struct hsp_backend *b, struct gbp_transport *t)
{
    b->use_ext_isr = 0;
    t->irq_install = h_irq_install;
    t->irq_restore = h_irq_restore;
    t->irq_mask = h_irq_mask;
    t->irq_unmask = h_irq_unmask;
    t->irq_record = h_irq_record;
    t->irq_record_reset = h_irq_record_reset;
}

void hsp_backend_irq_transport_ext(struct hsp_backend *b, struct gbp_transport *t)
{
    hsp_backend_irq_transport(b, t);
    b->use_ext_isr = 1;
}
