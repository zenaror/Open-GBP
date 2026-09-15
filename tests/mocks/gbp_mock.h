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
 *   - a full operation trace for assertions (what was written where);
 *   - a SYNTHETIC PI HSP interrupt path (GBP-INIT-002): mask/unmask
 *     state, cause assertion (never / at unmask / N ticks after the
 *     unmask), delivery of the one-shot handler (the same body the real
 *     backend runs, gbp_irq_oneshot.h), write-1-to-clear that does or
 *     does not clear the cause, a second delivery despite the mask, and
 *     an order/invariant checker that flags every violation instead of
 *     hiding it. None of the IRQ behavior is physical data.
 */
#ifndef OPENGBP_GBP_MOCK_H
#define OPENGBP_GBP_MOCK_H

#include <stdint.h>
#include "../../src/gbp/gbp_transport.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_MOCK_MAX_OPS 512

enum gbp_mock_op_kind {
    MOCK_AR_R, MOCK_AR_W, MOCK_RD, MOCK_WR,
    /* PI HSP interrupt path (main-loop operations) */
    MOCK_INTSR_W, MOCK_IRQ_INSTALL, MOCK_IRQ_RESTORE, MOCK_IRQ_MASK, MOCK_IRQ_UNMASK,
    /* events generated inside a delivered handler entry */
    MOCK_ISR_ENTRY, MOCK_ISR_MASK, MOCK_ISR_W1C, MOCK_ISR_EXIT
};

struct gbp_mock_op {
    enum gbp_mock_op_kind kind;
    uint32_t addr;
    uint16_t value;             /* AR_INFO value for AR ops */
    uint8_t data[GBP_BLOCK_SIZE];
    gbp_status rc;
    uint32_t intsr, intmr;      /* PI view when the op was recorded (IRQ-path ops) */
};

enum gbp_mock_irq_mode {
    MOCK_IRQ_NONE = 0,          /* the cause never asserts by itself */
    MOCK_IRQ_ON_UNMASK = 1,     /* the cause asserts at the moment of the unmask */
    MOCK_IRQ_AFTER_TICKS = 2    /* the cause asserts irq_after_ticks after the unmask */
};

/* Invariant violations the mock detects (bit mask in `violation_mask`). */
#define GBP_MOCK_VIOL_UNMASK_NO_HANDLER        0x01u  /* unmask with no handler installed */
#define GBP_MOCK_VIOL_UNMASK_BEFORE_CONTROL    0x02u  /* unmask before any CONTROL write (this experiment) */
#define GBP_MOCK_VIOL_RESTORE_WHILE_UNMASKED   0x04u  /* handler removed while INTMR bit 13 is enabled */
#define GBP_MOCK_VIOL_ARINFO_BEFORE_IRQ_DOWN   0x08u  /* AR_INFO written back while handler installed / unmasked */
#define GBP_MOCK_VIOL_ISR_W1C_BEFORE_MASK      0x10u  /* handler acknowledged before masking */
#define GBP_MOCK_VIOL_STORM                    0x20u  /* deliveries exceeded max_deliveries */
#define GBP_MOCK_VIOL_DMA_WHILE_UNMASKED       0x40u  /* block transfer while INTMR bit 13 is enabled */
#define GBP_MOCK_VIOL_INSTALL_TWICE            0x80u  /* irq_install while already installed */

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
    /* ---- PI HSP interrupt path (SYNTHETIC; GBP-INIT-002) ---- */
    int irq_ops_available;          /* 0: transport exposes no IRQ ops (like the replay backend); default 1 */
    int old_handler_nonnull;        /* irq_install reports a non-NULL previous handler */
    int install_fails;              /* irq_install returns GBP_ERR_BACKEND (nothing installed) */
    int restore_fails;              /* irq_restore returns GBP_ERR_BACKEND (handler stays installed) */
    int mask_ignored;               /* __MaskIrq has no effect on INTMR bit 13 (gating-failure model) */
    int unmask_ignored;             /* __UnmaskIrq has no effect */
    int irq_mode;                   /* enum gbp_mock_irq_mode */
    uint32_t irq_after_ticks;       /* MOCK_IRQ_AFTER_TICKS: delay after the unmask */
    int intsr_sticky_after_w1c;     /* a W1C leaves bit 13 set while the cause is asserted */
    int control_mask_clears_cause;  /* a CONTROL write with bit 0x10 set deasserts the cause */
    int second_delivery;            /* one more handler entry after the first returns, despite the mask */
    unsigned max_deliveries;        /* storm cap (default 8) */
    /* state */
    uint8_t test_store[GBP_BLOCK_SIZE];
    unsigned transfers;         /* block transfers so far */
    int stuck;
    struct gbp_mock_op ops[GBP_MOCK_MAX_OPS];
    unsigned nops;
    unsigned ops_dropped;
    unsigned control_writes;    /* CONTROL block writes seen */
    unsigned intmr_writes;
    unsigned intsr_writes;      /* write_intsr calls (main-loop acknowledges) */
    uint32_t last_intsr_write;
    uint16_t arinfo_initial;    /* AR_INFO at init (for the restore-order check) */
    int handler_installed;
    int cause_asserted;
    int in_isr;
    int isr_masked_this_entry;
    int unmasked_once;
    uint32_t unmask_tick;
    unsigned deliveries;        /* handler entries delivered */
    unsigned deliveries_without_handler;
    int second_delivered;
    unsigned violations;        /* count */
    unsigned violation_mask;    /* GBP_MOCK_VIOL_* bits */
    volatile struct gbp_irq_record rec;
};

void gbp_mock_init(struct gbp_mock *m);
void gbp_mock_transport(struct gbp_mock *m, struct gbp_transport *t);

/* Counts of block writes outside index 'allowed' (relative to base). */
unsigned gbp_mock_writes_outside(const struct gbp_mock *m, uint32_t base, unsigned allowed_index);

/* Index in ops[] of the first op of `kind` (and, for RD/WR, of block
 * index `block` relative to `base`; pass 16 for any); -1 if none. */
int gbp_mock_first_op(const struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t base, unsigned block);
/* Same, last occurrence. */
int gbp_mock_last_op(const struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t base, unsigned block);
/* Number of block reads or writes (kind MOCK_RD / MOCK_WR) of block index `block`. */
unsigned gbp_mock_count_block_ops(const struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t base, unsigned block);

#ifdef __cplusplus
}
#endif
#endif
