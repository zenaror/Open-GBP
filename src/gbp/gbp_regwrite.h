/*
 * gbp_regwrite.h — register writes with the layouts the references use,
 * captured first and logged later (docs/protocol/REGISTERS.md §2, DEVLOG
 * 2026-09-15 "GBI write layouts, from the binary").
 *
 *   CONTROL (index 0x4): GBI writes the byte replicated over the 32 bytes
 *                        (0x80015d9c / 0x80015dd4).
 *   IRQ     (index 0xD): GBI writes the 16-bit value replicated 16 times,
 *                        `hi lo hi lo …` (0x80015da4 fills 8 words of
 *                        value << 16 | value; `IRQ := 0` is 0x80015da0 =
 *                        32 × 00). Bytes 0x1E/0x1F therefore carry hi/lo,
 *                        the positions the Start-up Disc writes.
 *
 * The write functions perform one 32-byte transfer and record everything
 * about it (raw buffer, rc, DMA status, time base afterwards) without
 * formatting anything; gbp_regwrite_log() turns a result into its log
 * record afterwards, so a probe can keep its experimental region free of
 * printf-class work. Nothing here decides what a value means. The IRQ
 * write is the primitive GBP-INIT-003A uses for A1 (`read | 0x8000`), A2
 * (`0`) and the Start-up-Disc-style stop word; every call site is
 * counted by tools/poc_audit.py.
 */
#ifndef OPENGBP_GBP_REGWRITE_H
#define OPENGBP_GBP_REGWRITE_H

#include <stdint.h>
#include "gbp_transport.h"
#include "../log/ringlog.h"

#ifdef __cplusplus
extern "C" {
#endif

/* GBI 16-bit layout: value replicated 16 times, hi byte first. */
void gbp_regwrite_u16_layout(uint16_t value, uint8_t out[GBP_BLOCK_SIZE]);
/* GBI 8-bit layout: byte replicated 32 times. */
void gbp_regwrite_byte_layout(uint8_t value, uint8_t out[GBP_BLOCK_SIZE]);

enum gbp_regwrite_kind {
    GBP_REGWRITE_NONE = 0,
    GBP_REGWRITE_IRQ_U16 = 1,        /* record "IRQW <tag> …" */
    GBP_REGWRITE_CONTROL_BYTE = 2    /* record "CTLW <tag> …" */
};

/*
 * attempted / completed semantics (safety state, not statistics):
 *   attempted = 1 is stored BEFORE the transport's write_block is invoked;
 *   completed = 1 only after it returned GBP_OK. Whenever attempted && !completed
 *   the caller must assume the device may have taken the data: a timeout means
 *   the DMA was started and its completion was not seen, and even a busy
 *   refusal (GBP_ERR_BUSY, returned before the DMA is programmed by
 *   src/platform/hsp_backend.c) is treated conservatively the same way. The
 *   replay backend answers an unscripted write with GBP_ERR_BACKEND — for the
 *   caller that is an attempted, uncompleted write like any other.
 */
struct gbp_regwrite_result {
    int kind;                    /* enum gbp_regwrite_kind */
    const char *tag;             /* e.g. "tag=A1" (literal, kept for the log) */
    uint16_t before;             /* IRQ: 16-bit value read just before (log only) */
    uint16_t value;              /* the semantic value written */
    int attempted;               /* the transfer was issued */
    int completed;               /* rc == GBP_OK: the transfer reported completion */
    gbp_status rc;
    struct gbp_xfer_info info;
    uint32_t addr;
    uint32_t t_after;            /* transport ticks right after the transfer (0 if no time base) */
    uint8_t raw[GBP_BLOCK_SIZE]; /* exactly what was sent */
};

/* IRQ register write (index 0xD, offset 0), GBI u16 layout. No logging. */
void gbp_regwrite_irq_u16(const struct gbp_transport *t, const char *tag, uint32_t base,
                          uint16_t before, uint16_t value, struct gbp_regwrite_result *out, unsigned *errors);

/* CONTROL register write (index 0x4, offset 0), GBI byte layout. No logging. */
void gbp_regwrite_control_byte(const struct gbp_transport *t, const char *tag, uint32_t base,
                               uint8_t value, struct gbp_regwrite_result *out, unsigned *errors);

/* Log record of a completed call:
 *   IRQW <tag> addr= before=%04x write=%04x layout=gbi-u16-replicated rc= ticks= polls= dspcr= t_after= data=<64 hex>
 *   CTLW <tag> addr= semantic=%02x rc= ticks= polls= dspcr= t_after= layout=gbi-replicated data=<64 hex> */
void gbp_regwrite_log(struct ringlog *log, const struct gbp_regwrite_result *r);

#ifdef __cplusplus
}
#endif
#endif
