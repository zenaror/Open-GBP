/*
 * hsp_backend_irq_multi.h — the multi-cycle PI HSP interrupt path of the
 * real backend (libogc2 build only), in its own object (GBP-INIT-004).
 *
 * hsp_backend_irq.c (GBP-INIT-002/003B) stays untouched: its object, its
 * audit profile and the physically executed builds keep their identity. A
 * POC links THIS file when its experiment services several cycles with one
 * installed handler: the handler body is gbp_irq_multicycle_service()
 * (src/gbp/gbp_irq_oneshot.h) — the generation index published by the
 * main loop selects a write-once record slot, the unchanged 003B body
 * services it. The object contains no INTMR store (mask changes only
 * through __MaskIrq/__UnmaskIrq) and never references hsp_backend_intmr.c.
 */
#ifndef OPENGBP_HSP_BACKEND_IRQ_MULTI_H
#define OPENGBP_HSP_BACKEND_IRQ_MULTI_H

#include "hsp_backend.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Adds irq_install / irq_restore / irq_mask / irq_unmask / irq_record and the
 * multi-cycle operations irq_prepare / irq_record_slot / irq_multi_status to a
 * transport already filled by hsp_backend_transport(). irq_install registers
 * hsp_backend_oneshot_isr_multi and clears every slot (the anomaly slot is
 * poisoned with count = 1 so that an out-of-range generation never
 * acknowledges anything). */
void hsp_backend_irq_transport_multi(struct hsp_backend *b, struct gbp_transport *t);

/* The IRQ-26 handler this file installs (gbp_irq_multicycle_service with the
 * real PI primitives). Exposed so the link map / disassembly audit can find
 * it by name (tools/isr_audit.py --symbol hsp_backend_oneshot_isr_multi);
 * never call it. */
void hsp_backend_oneshot_isr_multi(u32 irq, frame_context *ctx);

#ifdef __cplusplus
}
#endif
#endif
