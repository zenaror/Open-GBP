#include "hsp_backend_irq_multi.h"

#include <gccore.h>
#include <ogc/lwp_watchdog.h>

#define PI_INTSR (*(vu32 *)0xCC003000u)
#define PI_INTMR (*(vu32 *)0xCC003004u)

/*
 * ---- multi-cycle PI HSP interrupt path (GBP-INIT-004) -----------------
 *
 * One handler for OS interrupt 26 (libogc2 IRQ_PI_HSP), installed once per
 * run, whose body is gbp_irq_multicycle_service() (src/gbp/gbp_irq_oneshot.h,
 * shared with the host mock): it reads the published generation once,
 * bounds-checks it before any pointer arithmetic, and services the selected
 * write-once slot with the unchanged GBP-INIT-003B body (entry state, mask,
 * INTMR, INTSR, one W1C, INTSR, bounded wait, INTSR/INTMR again). The
 * primitives below are the only things it can call: the time base, the two
 * PI registers and libogc2's __MaskIrq. No DMA, no allocation, no logging,
 * no GBP access, no INTMR store in this object.
 *
 * The bookkeeping is a single static instance (a libogc2 handler receives
 * no context pointer). The main loop touches it only through the transport
 * operations below, and only while INTMR bit 13 = 0 (the probe's rule); the
 * handler is the only writer of a slot once the generation is published.
 */
static volatile struct gbp_irq_multi hsp_irq_multi;

#define GBP_IRQ_PRIM_TICKS()        gettick()
#define GBP_IRQ_PRIM_READ_INTSR()   PI_INTSR
#define GBP_IRQ_PRIM_READ_INTMR()   PI_INTMR
#define GBP_IRQ_PRIM_MASK()         __MaskIrq(IM_PI_HSP)
#define GBP_IRQ_PRIM_WRITE_INTSR(v) (PI_INTSR = (v))
#include "../gbp/gbp_irq_oneshot.h"

void hsp_backend_oneshot_isr_multi(u32 irq, frame_context *ctx)
{
    (void)irq;
    (void)ctx;
    gbp_irq_multicycle_service(&hsp_irq_multi);
}

static void rec_clear(volatile struct gbp_irq_record *r)
{
    r->count = 0;
    r->fired = 0;
    r->t_entry = 0;
    r->intsr_before_ack = 0;
    r->intmr_at_entry = 0;
    r->intsr_after_ack = 0;
    r->intmr_after_mask = 0;
    r->reentry_intsr = 0;
    r->reentry_intmr = 0;
    r->intsr_before_w1c = 0;
    r->t_second = 0;
    r->intsr_second = 0;
    r->intmr_second = 0;
    r->reentry_t = 0;
}

static void rec_copy(const volatile struct gbp_irq_record *r, struct gbp_irq_record *out)
{
    out->count = r->count;
    out->fired = r->fired;
    out->t_entry = r->t_entry;
    out->intsr_before_ack = r->intsr_before_ack;
    out->intmr_at_entry = r->intmr_at_entry;
    out->intsr_after_ack = r->intsr_after_ack;
    out->intmr_after_mask = r->intmr_after_mask;
    out->reentry_intsr = r->reentry_intsr;
    out->reentry_intmr = r->reentry_intmr;
    out->intsr_before_w1c = r->intsr_before_w1c;
    out->t_second = r->t_second;
    out->intsr_second = r->intsr_second;
    out->intmr_second = r->intmr_second;
    out->reentry_t = r->reentry_t;
}

static void multi_clear(void)
{
    uint32_t i;
    hsp_irq_multi.expected_gen = 0;
    hsp_irq_multi.entries_total = 0;
    hsp_irq_multi.generation_errors = 0;
    for (i = 0; i < GBP_IRQ_MAX_CYCLES; i++) rec_clear(&hsp_irq_multi.slots[i]);
    rec_clear(&hsp_irq_multi.anomaly);
    hsp_irq_multi.anomaly.count = 1;     /* poisoned: an out-of-range generation takes the no-W1C reentry branch */
}

static gbp_status hm_irq_install(void *ctx, int *old_was_null)
{
    struct hsp_backend *b = (struct hsp_backend *)ctx;
    if (b->handler_installed) return GBP_ERR_PARAM;
    multi_clear();
    /* IRQ_Request returns the previous handler (binary-verified in
     * r2442.094b250, ENV-IRQ-002). Kept verbatim, NULL or not. */
    b->old_handler = IRQ_Request(IRQ_PI_HSP, hsp_backend_oneshot_isr_multi);
    b->handler_installed = 1;
    if (old_was_null) *old_was_null = (b->old_handler == 0) ? 1 : 0;
    return GBP_OK;
}

static gbp_status hm_irq_restore(void *ctx)
{
    struct hsp_backend *b = (struct hsp_backend *)ctx;
    irq_handler_t current;
    if (!b->handler_installed) return GBP_OK;
    /* Putting a NULL previous handler back has the same effect as IRQ_Free. */
    current = IRQ_Request(IRQ_PI_HSP, b->old_handler);
    b->handler_installed = 0;
    return (current == hsp_backend_oneshot_isr_multi) ? GBP_OK : GBP_ERR_BACKEND;
}

static gbp_status hm_irq_mask(void *ctx)
{
    (void)ctx;
    __MaskIrq(IM_PI_HSP);
    return GBP_OK;
}

static gbp_status hm_irq_unmask(void *ctx)
{
    (void)ctx;
    __UnmaskIrq(IM_PI_HSP);
    return GBP_OK;
}

/* The generation the next entry must use. The caller guarantees INTMR bit 13
 * = 0 (the handler cannot run); the slot is expected clean (write-once) and
 * is not cleared here: a dirty slot must be visible to the caller's check. */
static gbp_status hm_irq_prepare(void *ctx, uint32_t gen)
{
    (void)ctx;
    if (gen >= GBP_IRQ_MAX_CYCLES) return GBP_ERR_PARAM;
    hsp_irq_multi.expected_gen = gen;
    return GBP_OK;
}

static gbp_status hm_irq_record_slot(void *ctx, uint32_t slot, struct gbp_irq_record *out)
{
    (void)ctx;
    if (slot >= GBP_IRQ_MAX_CYCLES) return GBP_ERR_PARAM;
    rec_copy(&hsp_irq_multi.slots[slot], out);
    return GBP_OK;
}

/* irq_record: the slot of the published generation (kept for callers of the
 * single-record operation; the probe uses irq_record_slot). */
static gbp_status hm_irq_record(void *ctx, struct gbp_irq_record *out)
{
    uint32_t gen = hsp_irq_multi.expected_gen;
    if (gen >= GBP_IRQ_MAX_CYCLES) { rec_copy(&hsp_irq_multi.anomaly, out); return GBP_OK; }
    return hm_irq_record_slot(ctx, gen, out);
}

static gbp_status hm_irq_multi_status(void *ctx, struct gbp_irq_multi_status *out)
{
    (void)ctx;
    out->expected_gen = hsp_irq_multi.expected_gen;
    out->entries_total = hsp_irq_multi.entries_total;
    out->generation_errors = hsp_irq_multi.generation_errors;
    rec_copy(&hsp_irq_multi.anomaly, &out->anomaly);
    return GBP_OK;
}

void hsp_backend_irq_transport_multi(struct hsp_backend *b, struct gbp_transport *t)
{
    b->use_ext_isr = 0;
    t->irq_install = hm_irq_install;
    t->irq_restore = hm_irq_restore;
    t->irq_mask = hm_irq_mask;
    t->irq_unmask = hm_irq_unmask;
    t->irq_record = hm_irq_record;
    t->irq_prepare = hm_irq_prepare;
    t->irq_record_slot = hm_irq_record_slot;
    t->irq_multi_status = hm_irq_multi_status;
}
