/*
 * hsp_backend_intmr.h — the direct PI INTMR write of the real backend
 * (libogc2 build only), in its own object on purpose.
 *
 * Only GBP-INIT-001 (gbp_init_probe.c) writes INTMR directly. Every
 * later experiment changes INTMR bit 13 through libogc2's __MaskIrq /
 * __UnmaskIrq (hsp_backend_irq.c) or never at all, and their static
 * audits (tools/poc_audit.py) require zero INTMR stores in every linked
 * object — so this write is kept out of hsp_backend_irq.c.
 */
#ifndef OPENGBP_HSP_BACKEND_INTMR_H
#define OPENGBP_HSP_BACKEND_INTMR_H

#include "hsp_backend.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Adds write_intmr to a transport already filled by hsp_backend_transport(). */
void hsp_backend_intmr_transport(struct hsp_backend *b, struct gbp_transport *t);

#ifdef __cplusplus
}
#endif
#endif
