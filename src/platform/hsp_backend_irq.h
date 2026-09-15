/*
 * hsp_backend_irq.h — the PI HSP interrupt path of the real backend
 * (libogc2 build only), kept in its own object on purpose.
 *
 * A POC links this file only when its experiment needs to change INTMR
 * bit 13 or install the one-shot handler (GBP-INIT-002 and GBP-INIT-003B:
 * handler + __MaskIrq/__UnmaskIrq). The direct INTMR write of GBP-INIT-001
 * is hsp_backend_intmr.c, so this object contains no INTMR store. A POC
 * that must keep PI HSP masked for its whole run (GBP-INIT-003A) links
 * neither, so the static audit of its objects can prove that no code path
 * references __UnmaskIrq, __MaskIrq, IRQ_Request, IRQ_Free or an INTMR
 * store (tools/poc_audit.py).
 */
#ifndef OPENGBP_HSP_BACKEND_IRQ_H
#define OPENGBP_HSP_BACKEND_IRQ_H

#include "hsp_backend.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Adds the irq_install / irq_restore / irq_mask / irq_unmask / irq_record
 * operations to a transport already filled by hsp_backend_transport()
 * (irq_install registers hsp_backend_oneshot_isr, the GBP-INIT-002 body). */
void hsp_backend_irq_transport(struct hsp_backend *b, struct gbp_transport *t);
/* Same operations, but irq_install registers hsp_backend_oneshot_isr_ext
 * (the extended one-shot of GBP-INIT-003B: entry state, mask, INTMR,
 * INTSR, one W1C, INTSR, bounded wait, INTSR/INTMR again). */
void hsp_backend_irq_transport_ext(struct hsp_backend *b, struct gbp_transport *t);
void hsp_backend_oneshot_isr_ext(u32 irq, frame_context *ctx);

/* The one-shot IRQ-26 handler this file installs (gbp_irq_oneshot.h body
 * with real PI primitives). Exposed so the link map / disassembly audit
 * can find it by name; never call it. */
void hsp_backend_oneshot_isr(u32 irq, frame_context *ctx);

#ifdef __cplusplus
}
#endif
#endif
