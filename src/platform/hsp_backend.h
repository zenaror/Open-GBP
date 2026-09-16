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
 * Whole-block reads (read_bulk, GBP-AV-SERVICE-001): the same register
 * programming and the same polled completion with the caller's 32-byte
 * aligned buffer and a length that is a multiple of 32 — one DMA of the
 * whole length, as both references issue for the AUDIO (0x1000) and VIDEO
 * (0xF00) blocks. Cache maintenance for a device -> main-memory transfer:
 * DCFlushRange (dcbf: write back + invalidate every line of the range, so
 * no dirty line can be written back over the DMA data later and no stale
 * line can serve a CPU read; the caller's pre-fill reaches memory) BEFORE
 * the DMA, DCInvalidateRange (dcbi) AFTER completion — the Start-up Disc
 * invalidates (dcbi, 0x800687dc) before its block DMA and again in the
 * DMA-done callback, libogc2 invalidates before every EXI/ARAM read DMA
 * (exi.c, aram.c). The buffer must not be touched while the DMA runs.
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
    uint32_t transfers;        /* statistics (every DMA: 32-byte and bulk) */
    uint32_t timeouts;
    uint32_t busy_refusals;
    uint32_t bulk_transfers;   /* whole-block reads started */
    uint32_t bulk_bytes;       /* bytes requested by them */
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
