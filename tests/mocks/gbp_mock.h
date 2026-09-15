/*
 * gbp_mock.h — scripted device model behind gbp_transport, host only.
 *
 * Models just enough of what Phase 2 documented to exercise the probe
 * logic and every failure path:
 *   - AR_INFO register with read/write;
 *   - a GBP that is present or absent;
 *   - optional rule "the GBP only answers when AR_INFO bits 3-5 != 0"
 *     (the U-GBP-004 hypothesis);
 *   - TEST block storing ~data; CONTROL/IRQ blocks returning canned bytes;
 *   - read layout: byte-doubled ("dd") like the Start-up Disc's parsing,
 *     or plain;
 *   - fault injection: timeout/busy/backend error on the Nth transfer,
 *     stuck-busy after a timeout;
 *   - a full operation trace for assertions (what was written where).
 */
#ifndef OPENGBP_GBP_MOCK_H
#define OPENGBP_GBP_MOCK_H

#include <stdint.h>
#include "../../src/gbp/gbp_transport.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_MOCK_MAX_OPS 256

enum gbp_mock_op_kind { MOCK_AR_R, MOCK_AR_W, MOCK_RD, MOCK_WR };

struct gbp_mock_op {
    enum gbp_mock_op_kind kind;
    uint32_t addr;
    uint16_t value;             /* AR_INFO value for AR ops */
    uint8_t data[GBP_BLOCK_SIZE];
    gbp_status rc;
};

struct gbp_mock {
    /* configuration */
    int present;
    int require_expansion;      /* only answer when AR_INFO bits 3-5 != 0 */
    int byte_doubled;           /* 1: reads return each byte twice (b0 b0 b1 b1 ...) */
    uint16_t arinfo;
    uint8_t control_byte;       /* value presented by the CONTROL block */
    uint16_t irq_value;         /* value presented by the IRQ block */
    uint8_t absent_fill;        /* what a read returns when no GBP answers */
    unsigned fail_at_op;        /* 1-based transfer number that fails (0 = never) */
    gbp_status fail_rc;         /* which failure */
    int stuck_after_timeout;    /* subsequent transfers report busy */
    int silent_reads;           /* 1: read DMA "completes" but never writes the buffer */
    const uint8_t *canned;      /* if set: every read returns exactly these 32 bytes */
    /* CONTROL/IRQ/TEST block models for the init probe (used when set) */
    const uint8_t *control_block;   /* exact 32 bytes returned for CONTROL reads (else control_byte fill) */
    const uint8_t *irq_block;       /* exact 32 bytes returned for IRQ reads (else irq_value doubled) */
    int test_byte0_anomaly;         /* TEST read-back: byte 0 gets extra bit 0x40 */
    int control_writes_stick;       /* 1: a CONTROL write updates control_byte (readback follows) */
    unsigned control_write_fail_at; /* Nth CONTROL write (1-based) is ignored (readback unchanged) */
    uint8_t irq_after_write;        /* if nonzero: IRQ block becomes this byte after a CONTROL write */
    /* PI model */
    uint32_t intsr, intmr;
    int pi_unavailable;             /* read_pi fails */
    int intmr_write_ignored;        /* write_intmr "succeeds" but the value does not change */
    int intsr_bit13_follows_control;/* bit 13 set while control bit 0x10 is clear */
    uint32_t tick;
    /* state */
    uint8_t test_store[GBP_BLOCK_SIZE];
    unsigned transfers;         /* block transfers so far */
    int stuck;
    struct gbp_mock_op ops[GBP_MOCK_MAX_OPS];
    unsigned nops;
    unsigned ops_dropped;
    unsigned control_writes;    /* CONTROL block writes seen */
    unsigned intmr_writes;
};

void gbp_mock_init(struct gbp_mock *m);
void gbp_mock_transport(struct gbp_mock *m, struct gbp_transport *t);

/* Counts of block writes outside index 'allowed' (relative to base). */
unsigned gbp_mock_writes_outside(const struct gbp_mock *m, uint32_t base, unsigned allowed_index);

#ifdef __cplusplus
}
#endif
#endif
