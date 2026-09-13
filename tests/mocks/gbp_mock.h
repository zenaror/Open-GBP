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
    /* state */
    uint8_t test_store[GBP_BLOCK_SIZE];
    unsigned transfers;         /* block transfers so far */
    int stuck;
    struct gbp_mock_op ops[GBP_MOCK_MAX_OPS];
    unsigned nops;
    unsigned ops_dropped;
};

void gbp_mock_init(struct gbp_mock *m);
void gbp_mock_transport(struct gbp_mock *m, struct gbp_transport *t);

/* Counts of block writes outside index 'allowed' (relative to base). */
unsigned gbp_mock_writes_outside(const struct gbp_mock *m, uint32_t base, unsigned allowed_index);

#ifdef __cplusplus
}
#endif
#endif
