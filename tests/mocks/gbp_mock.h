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
 *     state, cause assertion, delivery of the one-shot handler, etc.;
 *   - a SYNTHETIC "SOURCE_MASK" model of the GBP IRQ register
 *     (GBP-INIT-003A): even bits 0..10 = sources, write-1-to-clear; odd
 *     bits 1..11 = masks, level-written; bit 15 level-written or a W1C
 *     pending summary, per scenario; a source may (re)assert some ticks
 *     after the Nth IRQ write; PI INTSR bit 13 is raised when a source is
 *     pending and its local mask (and bit 15, in the level reading) are
 *     open, whether or not INTMR enables delivery.
 *   - a SYNTHETIC whole-block read model (GBP-AV-SERVICE-001): read_bulk
 *     answers a deterministic byte pattern per block index, with per-index
 *     failure injection (busy / timeout / backend), an optional "the drain
 *     clears the source bit" rule, a source that (re)asserts while the Nth
 *     bulk read is in progress, and a phantom PI cause after the Nth
 *     IRQ-register write.
 *   None of the IRQ behavior is physical data: it only exercises control
 *   flow (docs/protocol/INITIALIZATION.md §10 keeps the classification).
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
    MOCK_ISR_ENTRY, MOCK_ISR_MASK, MOCK_ISR_W1C, MOCK_ISR_EXIT,
    /* multi-cycle path (GBP-INIT-004): the generation published by the main loop (value = gen) */
    MOCK_IRQ_PREPARE,
    /* whole-block read (GBP-AV-SERVICE-001): addr, len, rc, data = the first 32 bytes delivered */
    MOCK_RD_BULK
};

struct gbp_mock_op {
    enum gbp_mock_op_kind kind;
    uint32_t addr;
    uint32_t len;               /* MOCK_RD_BULK: bytes requested */
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

/* GBP IRQ-register model (index 0xD) */
enum gbp_mock_irq_model {
    MOCK_IRQ_MODEL_STATIC = 0,      /* canned irq_value / irq_block, writes ignored (GBP-INIT-001/002 tests) */
    MOCK_IRQ_MODEL_SOURCE_MASK = 1  /* synthetic source/mask register, see above */
};
enum gbp_mock_bit15_mode {
    MOCK_BIT15_LEVEL = 0,           /* bit 15 written as a level; 1 blocks every source (global mask reading) */
    MOCK_BIT15_SUMMARY = 1          /* bit 15 = "any source pending"; W1C; never blocks (pending-summary reading) */
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
#define GBP_MOCK_VIOL_PREPARE_WHILE_UNMASKED   0x100u /* generation published while INTMR bit 13 is enabled (GBP-INIT-004) */

struct gbp_mock {
    /* configuration */
    int present;
    int require_expansion;      /* only answer when AR_INFO bits 3-5 != 0 */
    int byte_doubled;           /* 1: reads return each byte twice (b0 b0 b1 b1 ...) */
    uint16_t arinfo;
    uint8_t control_byte;       /* value presented by the CONTROL block */
    uint16_t irq_value;         /* value presented by the IRQ block (STATIC model) */
    uint8_t absent_fill;        /* what a read returns when no GBP answers */
    unsigned fail_at_op;        /* 1-based transfer number that fails (0 = never) */
    gbp_status fail_rc;         /* which failure */
    int stuck_after_timeout;    /* subsequent transfers report busy */
    int silent_reads;           /* 1: read DMA "completes" but never writes the buffer */
    const uint8_t *canned;      /* if set: every read returns exactly these 32 bytes */
    /* CONTROL/IRQ/TEST block models for the init probe (used when set) */
    const uint8_t *control_block;   /* exact 32 bytes returned for CONTROL reads (else control_byte fill) */
    const uint8_t *irq_block;       /* exact 32 bytes returned for IRQ reads (STATIC model, else irq_value doubled) */
    int test_byte0_anomaly;         /* TEST read-back: byte 0 gets extra bit 0x40 */
    int control_writes_stick;       /* 1: a CONTROL write updates control_byte (readback follows) */
    unsigned control_write_fail_at; /* Nth CONTROL write (1-based) is ignored (readback unchanged) */
    uint8_t irq_after_write;        /* if nonzero: IRQ block becomes this byte after a CONTROL write */
    unsigned arinfo_write_fail_at;  /* Nth AR_INFO write (1-based) returns GBP_ERR_BACKEND and is ignored */
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
    /* ---- GBP IRQ register model (SYNTHETIC; GBP-INIT-003A) ---- */
    int irq_model;                  /* enum gbp_mock_irq_model */
    int bit15_mode;                 /* enum gbp_mock_bit15_mode */
    uint16_t irq_reg;               /* register state (SOURCE_MASK model) */
    unsigned source_assert_after_write; /* 1-based IRQ write number after which `source_assert_bits` (re)assert; 0 = never */
    uint32_t source_assert_delay;   /* ticks after that write */
    uint16_t source_assert_bits;    /* even bits to set then (e.g. 0x0500) */
    int pi_cause_level;             /* 1: INTSR bit 13 follows the device line (clears when nothing propagates); 0: latched until W1C */
    unsigned irq_write_fail_at;     /* Nth IRQ-register write (1-based) returns GBP_ERR_TIMEOUT */
    int irq_write_fail_applies;     /* 1: the failed write still updates the register (DMA started) */
    int irq_byte0_anomaly;          /* IRQ reads (SOURCE_MASK): byte 0 carries extra bits, as the hardware does */
    int intsr_w1c_ignored;          /* a main-loop INTSR W1C leaves bit 13 set (sticky-cause model) */
    int intmr13_set_after_control_write; /* INTMR bit 13 becomes 1 right after the first CONTROL write (external unmask model) */
    int intmr13_set_after_irq_write;     /* INTMR bit 13 becomes 1 right after the first IRQ-register write */
    /* ---- delivery experiment (SYNTHETIC; GBP-INIT-003B) ---- */
    int isr_ext;                    /* 1: deliveries run gbp_irq_oneshot_service_ext (the 003B body); ticks advance by 1 per read inside it */
    uint32_t pi_relatch_after_ticks;/* after a W1C clears bit 13 while a device source is pending and its mask open, set it again after N ticks (0 = never) */
    int delivery_suppressed;        /* the cause is set and unmasked but the mock never delivers (delivery-timeout model) */
    int record_dirty_on_install;    /* synthetic: the install leaves count=1 in the record (must abort before the unmask) */
    int clear_cause_on_install;     /* INTSR bit 13 is cleared when irq_install is called (cause-lost model) */
    int intmr13_set_on_install;     /* INTMR bit 13 becomes 1 when irq_install is called */
    uint8_t control_on_install;     /* if nonzero: CONTROL byte becomes this value when irq_install is called */
    uint16_t irq_reg_on_install;    /* if nonzero: SOURCE_MASK register becomes this value when irq_install is called */
    int irq_disagree_on_install;    /* after irq_install, IRQ reads present byte 0x1F ^ 0x01 (Disc/GBI readings disagree) */
    /* ---- multi-cycle service (SYNTHETIC; GBP-INIT-004) ---- */
    int isr_multi;                  /* 1: deliveries run gbp_irq_multicycle_service on `multi` (ticks advance as with isr_ext) */
    struct gbp_mock_src_sched {     /* sources that (re)assert `delay` ticks after the Nth IRQ-register write (any number of them) */
        unsigned after_write;       /* 1-based IRQ write number; 0 = unused entry */
        uint32_t delay;
        uint16_t bits;              /* even source bits, e.g. 0x0500 */
        uint32_t at_tick;           /* armed: absolute tick of the assertion */
        int armed, done;
    } src_sched[8];
    unsigned n_src_sched;
    uint32_t source_pi_delay;       /* the PI latch follows a device source by N ticks (0 = same instant): "source visible before PI" model */
    unsigned ack_ignored_at_write;  /* the Nth IRQ write completes (rc ok) but clears no source: "ACK ineffective" model */
    uint16_t rearm_sticky_bits;     /* bits that read 1 right after an IRQ := 0x0000 write: "invalid re-arm read-back" model */
    unsigned rearm_sticky_from_write;  /* ... only for zero writes numbered >= this (1-based; 0 = every zero write, A2 included) */
    int force_gen_valid;            /* 1: at the next unmask the handler sees generation force_expected_gen (synthetic corruption) */
    uint32_t force_expected_gen;
    unsigned second_delivery_at;    /* one more handler entry after the Nth delivery returns (second_delivery = at 1) */
    unsigned control_change_after_irq_write;  /* CONTROL byte becomes control_change_value by itself after the Nth IRQ write */
    uint8_t control_change_value;
    unsigned mask_ignored_from_call;/* every mask (handler or main) from the Nth mask call on has no effect (0 = never) */
    unsigned force_gen_at_unmask;   /* force_gen_valid applies at the Nth unmask call (0 = the next one) */
    unsigned suppress_delivery_at;  /* the Nth delivery (1-based) never reaches the CPU although cause and mask are open */
    unsigned source_clear_at_delivery; /* right after the Nth delivered handler entry returns, every source drops (source-lost model) */
    unsigned irq_disagree_from_write;  /* from the Nth IRQ write on, IRQ reads present byte 0x1F ^ 0x01 (Disc != GBI) */
    /* ---- whole-block reads (SYNTHETIC; GBP-AV-SERVICE-001) ---- */
    int bulk_ops_available;         /* 0: the transport exposes no read_bulk (like a replay without "B" lines); default 1 */
    int bulk_any_offset;            /* 1: accept a bulk read at any offset of a window; default 0 = the exact block address only
                                     * (base + index << 20, as both references read the AUDIO / VIDEO blocks), else GBP_ERR_PARAM */
    unsigned bulk_bad_addr;         /* bulk reads refused because their address was not a block's exact address */
    gbp_status bulk_rc[16];         /* status returned by a bulk read of block index i (default GBP_OK) */
    int bulk_partial_on_fail;       /* a failed bulk read still delivered its first 32 bytes (DMA-started model) */
    uint32_t bulk_ticks_per_line;   /* wait ticks reported per 32 bytes (default 3) */
    uint8_t bulk_seed;              /* byte-pattern seed (gbp_mock_bulk_byte) */
    int bulk_clears_source;         /* 1: reading block 0x8 clears source 0x0400 and block 0x1 clears 0x0100 (drain-clears model) */
    unsigned bulk_assert_at_read;   /* 1-based bulk read number during which bulk_assert_bits (re)assert (0 = never) */
    uint16_t bulk_assert_bits;      /* even source bits set then, e.g. 0x0100 */
    int bulk_assert_after;          /* 1: the assertion happens after that read completed, else before it starts */
    unsigned bit15_drop_at_write;   /* 1-based IRQ-register write whose bit 15 is not retained (reads 0 afterwards; 0 = never) */
    unsigned pi_phantom_after_write;/* 1-based IRQ-register write after which INTSR bit 13 is set with no source (0 = never) */
    uint32_t pi_phantom_delay;      /* ticks after that write */
    /* state */
    uint8_t test_store[GBP_BLOCK_SIZE];
    unsigned transfers;         /* block transfers so far */
    int stuck;
    struct gbp_mock_op ops[GBP_MOCK_MAX_OPS];
    unsigned nops;
    unsigned ops_dropped;
    unsigned control_writes;    /* CONTROL block writes seen */
    unsigned irq_writes;        /* IRQ block writes seen */
    unsigned arinfo_writes;
    unsigned intmr_writes;
    unsigned intsr_writes;      /* write_intsr calls (main-loop acknowledges) */
    unsigned intsr_polls;       /* poll_intsr calls */
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
    uint32_t source_assert_at_tick; /* SOURCE_MASK: absolute tick of the pending (re)assertion, 0 = none */
    int source_asserted_done;
    int relatch_pending;            /* a W1C cleared bit 13 while the line was up: re-set it at relatch_at_tick */
    uint32_t relatch_at_tick;
    unsigned isr_w1c_count;         /* W1C writes performed from inside delivered handler entries */
    int installed_calls;            /* irq_install calls seen */
    uint16_t last_irq_write_value;  /* SOURCE_MASK: 16-bit value of the last IRQ write (bytes 0x1E/0x1F) */
    int irq_present_u16;            /* STATIC: present irq_value as hh hh ll ll (set by irq_after_write) */
    volatile struct gbp_irq_multi multi;   /* the multi-cycle handler's bookkeeping and slots (isr_multi) */
    int pi_latch_pending;           /* source_pi_delay: a latch is due at pi_latch_at_tick */
    uint32_t pi_latch_at_tick;
    unsigned prepare_calls;         /* irq_prepare calls seen */
    uint32_t last_prepare_gen;
    unsigned mask_calls;            /* mask primitive calls (handler + main), for mask_ignored_from_call */
    unsigned unmask_calls;          /* irq_unmask calls seen */
    unsigned isr_entries_multi;     /* handler entries served through the multi-cycle body */
    unsigned bulk_reads;            /* bulk reads seen (attempted) */
    uint32_t bulk_bytes;            /* bytes delivered by completed bulk reads */
    int pi_phantom_pending;
    uint32_t pi_phantom_at_tick;
    /* test hook: invoked at the entry of every write_block, before the mock
     * decides anything — lets a test observe the caller's state at the
     * moment the transport is invoked (not after it returned). */
    void (*write_hook)(struct gbp_mock *m, uint32_t addr, const uint8_t data[GBP_BLOCK_SIZE], void *user);
    void *write_hook_user;
};

void gbp_mock_init(struct gbp_mock *m);
void gbp_mock_transport(struct gbp_mock *m, struct gbp_transport *t);

/* Byte k of the synthetic pattern a bulk read of block `index` delivers (seed = m->bulk_seed). */
uint8_t gbp_mock_bulk_byte(unsigned index, uint8_t seed, uint32_t k);

/* Counts of block writes outside index 'allowed' (relative to base). */
unsigned gbp_mock_writes_outside(const struct gbp_mock *m, uint32_t base, unsigned allowed_index);

/* Index in ops[] of the first op of `kind` (and, for RD/WR, of block
 * index `block` relative to `base`; pass 16 for any); -1 if none. */
int gbp_mock_first_op(const struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t base, unsigned block);
/* Same, last occurrence. */
int gbp_mock_last_op(const struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t base, unsigned block);
/* Same, Nth occurrence (1-based); -1 if fewer. */
int gbp_mock_nth_op(const struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t base, unsigned block, unsigned n);
/* Number of block reads or writes (kind MOCK_RD / MOCK_WR) of block index `block`. */
unsigned gbp_mock_count_block_ops(const struct gbp_mock *m, enum gbp_mock_op_kind kind, uint32_t base, unsigned block);

#ifdef __cplusplus
}
#endif
#endif
