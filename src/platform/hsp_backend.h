/*
 * hsp_backend.h — real GameCube backend for gbp_transport (libogc2 build only).
 *
 * Implements the ARAM-DMA transfer exactly as the Start-up Disc does
 * (docs/hardware/HSP.md §1): program 0xCC005020/24/28 in 16-bit halves,
 * poll DSP CSR bit 5, clear it, with interrupts disabled and a bounded
 * timeout. libogc's AR/ARQ subsystem is NOT used and must not be
 * initialized by the application (its ARAM interrupt handler would race
 * this polling).
 *
 * This object contains no INTMR write and no interrupt-handler code: the
 * PI HSP interrupt path (write_intmr, irq_install/restore/mask/unmask/
 * record, the one-shot handler) is hsp_backend_irq.c, linked only by the
 * POCs whose experiment needs it.
 */
#ifndef OPENGBP_HSP_BACKEND_H
#define OPENGBP_HSP_BACKEND_H

#include <stdint.h>
#include <gctypes.h>
#include <ogc/irq.h>
#include "../gbp/gbp_transport.h"

#ifdef __cplusplus
extern "C" {
#endif

struct hsp_backend {
    uint32_t timeout_ticks;    /* completion timeout in time-base ticks */
    uint8_t *buffer;           /* 32-byte aligned, 32 bytes, caller-provided */
    uint32_t transfers;        /* statistics */
    uint32_t timeouts;
    uint32_t busy_refusals;
    uint16_t last_csr_before;  /* DSP CSR seen before the last transfer */
    uint16_t last_csr_after;
    /* PI HSP interrupt path (gbp_transport irq_* operations):
     * the previous IRQ-26 handler as returned by IRQ_Request, kept
     * verbatim (NULL or not) and put back by irq_restore. */
    irq_handler_t old_handler;
    int handler_installed;
    int use_ext_isr;           /* 1: irq_install registers the extended one-shot (GBP-INIT-003B) */
};

/* buffer: 32 bytes, 32-byte aligned (e.g. static u8 b[32] ATTRIBUTE_ALIGN(32)). */
void hsp_backend_init(struct hsp_backend *b, uint8_t *buffer, uint32_t timeout_ticks);
void hsp_backend_transport(struct hsp_backend *b, struct gbp_transport *t);

/* Raw DSP CSR (0xCC00500A) read, for diagnostics. */
uint16_t hsp_backend_read_csr(void);

/* The one-shot IRQ-26 handler and the INTMR/handler operations are
 * declared in hsp_backend_irq.h (separate object). */

#ifdef __cplusplus
}
#endif
#endif
