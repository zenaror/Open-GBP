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

/*
 * Extended one-shot body for GBP-INIT-003B (delivery of a cause that is
 * already latched at the PI). Same primitives, same rules; the entry
 * state is captured before the mask because the experiment needs
 * INTSR/INTMR "as delivered" — MSR[EE] is 0 from the exception entry to
 * the end of c_irqdispatcher (libogc2 irq_handler.S sets only MSR_RI;
 * ENV-IRQ-001), so nothing can pre-empt these three reads. Nothing is
 * written before the mask. After the mask: INTMR, INTSR, ONE W1C, INTSR
 * again, a bounded time-base wait of about GBP_IRQ_SECOND_READ_TICKS
 * ticks (2.5 µs at 40.5 MHz; capped by GBP_IRQ_SECOND_READ_GUARD
 * iterations so it cannot hang), then INTSR/INTMR once more. A second
 * entry re-masks, keeps its view and does NOT write INTSR.
 */
#ifndef GBP_IRQ_SECOND_READ_TICKS
#define GBP_IRQ_SECOND_READ_TICKS 100u
#endif
#ifndef GBP_IRQ_SECOND_READ_GUARD
#define GBP_IRQ_SECOND_READ_GUARD 4096u
#endif

static inline void gbp_irq_oneshot_service_ext(volatile struct gbp_irq_record *r)
{
    uint32_t t = GBP_IRQ_PRIM_TICKS();                  /* 1. entry timestamp                       */
    uint32_t sr = GBP_IRQ_PRIM_READ_INTSR();            /* 2. INTSR at entry (as delivered)         */
    uint32_t mr = GBP_IRQ_PRIM_READ_INTMR();            /* 3. INTMR at entry                        */
    uint32_t n = r->count + 1u;                         /* 4. count this entry                      */
    r->count = n;
    GBP_IRQ_PRIM_MASK();                                /* 5. MASK IRQ 26 — before any write        */
    if (n == 1u) {
        uint32_t t0, guard = 0u;
        r->t_entry = t;
        r->intsr_before_ack = sr;                       /*    intsr_at_entry                        */
        r->intmr_at_entry = mr;
        r->intmr_after_mask = GBP_IRQ_PRIM_READ_INTMR();/* 6. INTMR after the mask                  */
        r->intsr_before_w1c = GBP_IRQ_PRIM_READ_INTSR();/* 7. INTSR before the W1C                  */
        GBP_IRQ_PRIM_WRITE_INTSR(GBP_PI_HSP_BIT);       /* 8. the ONLY W1C of the run               */
        r->intsr_after_ack = GBP_IRQ_PRIM_READ_INTSR(); /* 9. INTSR immediately after the W1C       */
        t0 = GBP_IRQ_PRIM_TICKS();                      /* 10. bounded wait on the time base        */
        while ((uint32_t)(GBP_IRQ_PRIM_TICKS() - t0) < GBP_IRQ_SECOND_READ_TICKS &&
               ++guard < GBP_IRQ_SECOND_READ_GUARD) { }
        r->t_second = GBP_IRQ_PRIM_TICKS();             /* 11. */
        r->intsr_second = GBP_IRQ_PRIM_READ_INTSR();    /* 12. INTSR at the second read             */
        r->intmr_second = GBP_IRQ_PRIM_READ_INTMR();    /* 13. INTMR at the second read             */
        r->fired = 1u;                                  /* 14. published last                       */
    } else {
        r->reentry_t = t;                               /* anomaly: second entry — no W1C           */
        r->reentry_intsr = sr;
        r->reentry_intmr = mr;
        r->fired = 1u;
    }
    /* 15. return — no loop beyond the bounded wait, no further access */
}

/*
 * Multi-cycle wrapper (GBP-INIT-004). The main loop publishes the slot
 * index the next entry must use (`expected_gen`) only while INTMR bit 13 =
 * 0; the handler reads it exactly once at entry and services that slot
 * with the unchanged extended body above (first entry of a slot: the 003B
 * sequence with its single W1C; a second entry of the same slot: the
 * body's reentry branch, no W1C). Slots are write-once: zeroed at the
 * install, never cleared afterwards. A generation out of range never
 * indexes the array: it is counted and serviced through `anomaly`, a slot
 * the install "poisons" with count = 1 so that the body always takes its
 * no-W1C reentry branch there. Exactly one call of the body (one inlined
 * W1C store) so tools/isr_audit.py can prove "one INTSR store".
 */
#define GBP_IRQ_MAX_CYCLES GBP_IRQ_MULTI_SLOTS   /* struct gbp_irq_multi: gbp_transport.h */

static inline void gbp_irq_multicycle_service(volatile struct gbp_irq_multi *m)
{
    uint32_t gen = m->expected_gen;                 /* read once */
    volatile struct gbp_irq_record *slot;
    m->entries_total = m->entries_total + 1u;
    if (gen < GBP_IRQ_MAX_CYCLES) {
        slot = &m->slots[gen];                      /* bounds checked before the pointer arithmetic */
    } else {
        m->generation_errors = m->generation_errors + 1u;
        slot = &m->anomaly;
    }
    gbp_irq_oneshot_service_ext(slot);
}

#endif
