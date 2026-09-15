/*
 * gbp_irq_oneshot.h — body of the one-shot PI HSP interrupt handler.
 *
 * Included by the real backend (src/platform/hsp_backend.c, inside the
 * libogc2 handler installed with IRQ_Request(IRQ_PI_HSP, …)) and by the
 * host mock (tests/mocks/gbp_mock.c), so both execute exactly the same
 * statements in the same order. The includer defines the primitives
 * BEFORE including this header:
 *
 *   GBP_IRQ_PRIM_TICKS()          uint32_t   time-base low word (gettick)
 *   GBP_IRQ_PRIM_READ_INTSR()     uint32_t   PI INTSR 0xCC003000
 *   GBP_IRQ_PRIM_READ_INTMR()     uint32_t   PI INTMR 0xCC003004
 *   GBP_IRQ_PRIM_MASK()           void       __MaskIrq(IM_PI_HSP): through
 *                                            libogc2's shadow masks, never a
 *                                            direct INTMR write (ENV-IRQ-002)
 *   GBP_IRQ_PRIM_WRITE_INTSR(v)   void       PI INTSR := v (write-1-to-clear)
 *
 * Binding rules (docs/protocol/INITIALIZATION.md §9, R3 and R8; UNKNOWNS
 * U-GBP-022 safety note):
 *   - the mask comes BEFORE the acknowledge, so that an interrupt cause
 *     that the W1C does not clear cannot re-enter the handler after rfi;
 *   - nothing here allocates, blocks, formats, logs, performs DMA or
 *     touches any GBP register; only PI MMIO and 32-bit stores;
 *   - the W1C is written once per entry, never in a loop; what INTSR reads
 *     afterwards is an observation for the main loop, not an exit condition;
 *   - a second entry (count > 1) is an anomaly: it re-masks and
 *     re-acknowledges once more, keeps the view it saw, and returns.
 */
#ifndef OPENGBP_GBP_IRQ_ONESHOT_H
#define OPENGBP_GBP_IRQ_ONESHOT_H

#include <stdint.h>
#include "gbp_transport.h"

#if !defined(GBP_IRQ_PRIM_TICKS) || !defined(GBP_IRQ_PRIM_READ_INTSR) || \
    !defined(GBP_IRQ_PRIM_READ_INTMR) || !defined(GBP_IRQ_PRIM_MASK) || \
    !defined(GBP_IRQ_PRIM_WRITE_INTSR)
#error "define the GBP_IRQ_PRIM_* primitives before including gbp_irq_oneshot.h"
#endif

static inline void gbp_irq_oneshot_service(volatile struct gbp_irq_record *r)
{
    uint32_t t = GBP_IRQ_PRIM_TICKS();                  /* 1. entry timestamp                 */
    uint32_t sr = GBP_IRQ_PRIM_READ_INTSR();            /* 2. INTSR as found at entry         */
    uint32_t mr = GBP_IRQ_PRIM_READ_INTMR();            /* 3. INTMR as found at entry         */
    uint32_t n = r->count + 1u;                         /* 4. count this entry                */
    r->count = n;
    GBP_IRQ_PRIM_MASK();                                /* 5. MASK IRQ 26 — before the W1C    */
    GBP_IRQ_PRIM_WRITE_INTSR(GBP_PI_HSP_BIT);           /* 6. acknowledge PI: W1C bit 13 only */
    if (n == 1u) {
        r->t_entry = t;                                 /* 9. keep the first entry's data     */
        r->intsr_before_ack = sr;
        r->intmr_at_entry = mr;
        r->intsr_after_ack = GBP_IRQ_PRIM_READ_INTSR(); /* 7. INTSR after mask + ack          */
        r->intmr_after_mask = GBP_IRQ_PRIM_READ_INTMR();/* 8. INTMR after mask + ack          */
        r->fired = 1u;                                  /* 10. published last                 */
    } else if (n == 2u) {
        r->reentry_intsr = sr;                          /* anomaly: second entry's view       */
        r->reentry_intmr = mr;
    }
    /* 11. return — no loop, no wait, no further access */
}

#endif
