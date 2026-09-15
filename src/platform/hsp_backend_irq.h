/*
 * hsp_backend_irq.h — the PI HSP interrupt path of the real backend
 * (libogc2 build only), kept in its own object on purpose.
 *
 * A POC links this file only when its experiment needs to change INTMR
 * bit 13, install the one-shot handler or write INTMR directly (GBP-INIT-001
 * used write_intmr, GBP-INIT-002 the handler + __MaskIrq/__UnmaskIrq). A
 * POC that must keep PI HSP masked for its whole run (GBP-INIT-003A) does
 * not link it, so the static audit of its objects can prove that no code
 * path references __UnmaskIrq, __MaskIrq, IRQ_Request, IRQ_Free or an
 * INTMR store (tools/poc_audit.py).
 */
#ifndef OPENGBP_HSP_BACKEND_IRQ_H
#define OPENGBP_HSP_BACKEND_IRQ_H

#include "hsp_backend.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Adds write_intmr and the irq_install / irq_restore / irq_mask /
 * irq_unmask / irq_record operations to a transport already filled by
 * hsp_backend_transport(). */
void hsp_backend_irq_transport(struct hsp_backend *b, struct gbp_transport *t);

/* The one-shot IRQ-26 handler this file installs (gbp_irq_oneshot.h body
 * with real PI primitives). Exposed so the link map / disassembly audit
 * can find it by name; never call it. */
void hsp_backend_oneshot_isr(u32 irq, frame_context *ctx);

#ifdef __cplusplus
}
#endif
#endif
