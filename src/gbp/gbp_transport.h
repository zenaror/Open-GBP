/*
 * gbp_transport.h — the boundary between GBP logic and the hardware.
 *
 *     probe / driver logic
 *            │
 *     struct gbp_transport  (this file)
 *            ├── src/platform/hsp_backend.c   real GameCube (ARAM DMA)
 *            ├── tests/mocks/gbp_mock.c       scripted device model (host)
 *            └── src/gbp/gbp_replay.c         replays recorded blocks (host)
 *
 * Terminology (docs/protocol/REGISTERS.md): a GBP "block" is 32 bytes at
 * ARAM address  base + (index << 20) + offset,  base = internal ARAM size.
 * Nothing in this header assumes the hardware semantics beyond that.
 */
#ifndef OPENGBP_GBP_TRANSPORT_H
#define OPENGBP_GBP_TRANSPORT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_BLOCK_SIZE 32u

typedef enum {
    GBP_OK = 0,
    GBP_ERR_TIMEOUT = 1,   /* DMA did not complete within the backend's timeout */
    GBP_ERR_BUSY = 2,      /* DMA engine busy / stale completion flag before start */
    GBP_ERR_PARAM = 3,     /* bad argument (alignment, size) */
    GBP_ERR_BACKEND = 4    /* backend-specific failure (mock script, replay exhausted) */
} gbp_status;

/* Status snapshot a backend can report for logging; fields it cannot
 * provide are 0. */
struct gbp_xfer_info {
    uint32_t ticks;        /* time spent waiting for completion (backend units) */
    uint16_t dma_status;   /* raw DSP CSR (0xCC00500A) after the transfer, if applicable */
    uint16_t polls;        /* completion polls performed */
};

/*
 * Fields the one-shot PI HSP interrupt handler (gbp_irq_oneshot.h) shares
 * with the main loop. All 32-bit so that no store is torn between the
 * handler and the main loop; the main loop copies them only while the
 * interrupt is masked again. Names follow the order of the handler's
 * statements (docs/protocol/INITIALIZATION.md §9 R3/R8).
 */
struct gbp_irq_record {
    uint32_t count;             /* handler entries so far (1 expected) */
    uint32_t fired;             /* 1 once the first entry has stored every field below */
    uint32_t t_entry;           /* ticks at the first entry, read before anything else */
    uint32_t intsr_before_ack;  /* INTSR read at the first entry, before the mask and the W1C */
    uint32_t intmr_at_entry;    /* INTMR read at the first entry, before the mask */
    uint32_t intsr_after_ack;   /* INTSR re-read after __MaskIrq + W1C (first entry) */
    uint32_t intmr_after_mask;  /* INTMR re-read after __MaskIrq + W1C (first entry) */
    uint32_t reentry_intsr;     /* INTSR seen at a second entry, if one ever happens (anomaly) */
    uint32_t reentry_intmr;     /* INTMR seen at that second entry */
    /* Extended handler (gbp_irq_oneshot_service_ext, GBP-INIT-003B) only;
     * zero when the base handler ran. In the extended handler
     * intmr_after_mask is read between the mask and the W1C and
     * intsr_after_ack is the read immediately after the W1C. */
    uint32_t intsr_before_w1c;  /* INTSR read after the mask, before the W1C */
    uint32_t t_second;          /* ticks of the second read, ≈100 ticks after the W1C */
    uint32_t intsr_second;      /* INTSR at the second read */
    uint32_t intmr_second;      /* INTMR at the second read */
    uint32_t reentry_t;         /* ticks at a second entry (anomaly) */
};

/* The multi-cycle handler's bookkeeping (GBP-INIT-004; the handler body is
 * gbp_irq_multicycle_service in gbp_irq_oneshot.h). One static instance in
 * the real backend and in the mock; written by the handler, read by the
 * main loop through the transport operations below. */
#define GBP_IRQ_MULTI_SLOTS 3u          /* write-once record slots: one per service cycle */
struct gbp_irq_multi {
    uint32_t expected_gen;                          /* slot index of the next valid entry (published while masked) */
    uint32_t entries_total;                         /* every entry (reporting only) */
    uint32_t generation_errors;                     /* entries with expected_gen >= GBP_IRQ_MULTI_SLOTS */
    struct gbp_irq_record slots[GBP_IRQ_MULTI_SLOTS];
    struct gbp_irq_record anomaly;                  /* count = 1 after the install: never acknowledges */
};

/* Generation bookkeeping as copied out for the main loop. */
struct gbp_irq_multi_status {
    uint32_t expected_gen;         /* slot index the next entry uses */
    uint32_t entries_total;        /* every handler entry (reporting only) */
    uint32_t generation_errors;    /* entries that found expected_gen out of range */
    struct gbp_irq_record anomaly; /* the slot those entries used (never acknowledges) */
};

struct gbp_transport {
    /* ARAM-info register 0xCC005012 (16-bit). */
    gbp_status (*read_arinfo)(void *ctx, uint16_t *value);
    gbp_status (*write_arinfo)(void *ctx, uint16_t value);
    /* One 32-byte transfer. aram_addr is the absolute ARAM address. */
    gbp_status (*read_block)(void *ctx, uint32_t aram_addr, uint8_t out[GBP_BLOCK_SIZE],
                             struct gbp_xfer_info *info);
    gbp_status (*write_block)(void *ctx, uint32_t aram_addr, const uint8_t in[GBP_BLOCK_SIZE],
                              struct gbp_xfer_info *info);
    /* Optional (may be NULL): Processor Interface INTSR (0xCC003000) and
     * INTMR (0xCC003004), raw 32-bit values. write_intmr writes the whole
     * register; callers preserve every bit they do not intend to change.
     * Under libogc2 a direct INTMR write can be undone by the library's
     * shadow-mask rebuild (EVIDENCE ENV-IRQ-002): code that needs the HSP
     * interrupt masked/unmasked must use irq_mask/irq_unmask below. */
    gbp_status (*read_pi)(void *ctx, uint32_t *intsr, uint32_t *intmr);
    gbp_status (*write_intmr)(void *ctx, uint32_t intmr);
    /* Optional (may be NULL): PI INTSR write — write-1-to-clear
     * acknowledge of the bits set in `value` (GBP-PI-002, CORROBORATED).
     * Main-loop cleanup only; the handler acknowledges by itself. */
    gbp_status (*write_intsr)(void *ctx, uint32_t value);
    /* Optional (may be NULL): one cheap INTSR read for polling loops that
     * must not log or transfer anything (a replay answers it from the
     * last recorded PI read; the real backend reads the register). */
    gbp_status (*poll_intsr)(void *ctx, uint32_t *intsr);
    /* Optional (may be NULL as a group): the PI HSP interrupt path.
     *   irq_install  installs the backend's one-shot handler for interrupt
     *                26 (libogc2: IRQ_Request(IRQ_PI_HSP, …)), clears the
     *                backend's gbp_irq_record, and reports whether the
     *                previous handler was NULL. The previous handler is kept.
     *   irq_restore  puts the previous handler back (IRQ_Request(26, old)).
     *   irq_mask     __MaskIrq(IM_PI_HSP)   — through libogc2's shadow masks.
     *   irq_unmask   __UnmaskIrq(IM_PI_HSP) — idem. Never before irq_install.
     *   irq_record   copies the shared record (call only while masked). */
    gbp_status (*irq_install)(void *ctx, int *old_was_null);
    gbp_status (*irq_restore)(void *ctx);
    gbp_status (*irq_mask)(void *ctx);
    gbp_status (*irq_unmask)(void *ctx);
    gbp_status (*irq_record)(void *ctx, struct gbp_irq_record *out);
    /* Optional multi-cycle interrupt path (GBP-INIT-004; NULL elsewhere):
     *   irq_prepare      publishes the generation (slot index) the next handler
     *                    entry must use — the caller calls it only while INTMR
     *                    bit 13 = 0 and never while an entry could happen;
     *   irq_record_slot  copies one write-once slot record (call only while masked);
     *   irq_multi_status copies the generation bookkeeping and the anomaly slot. */
    gbp_status (*irq_prepare)(void *ctx, uint32_t gen);
    gbp_status (*irq_record_slot)(void *ctx, uint32_t slot, struct gbp_irq_record *out);
    gbp_status (*irq_multi_status)(void *ctx, struct gbp_irq_multi_status *out);
    /* Optional (may be NULL): monotonic tick counter (time base on GC). */
    uint32_t (*ticks)(void *ctx);
    void *ctx;
};

/* 1 if every operation of the PI HSP interrupt path is available. */
int gbp_transport_has_irq_path(const struct gbp_transport *t);
/* 1 if the interrupt path and the three multi-cycle operations are available. */
int gbp_transport_has_irq_multi_path(const struct gbp_transport *t);

/* PI bit for the High Speed Port interrupt (YAGCD 6.1.5.2, libogc2 irq.c:
 * INTMR bit set = interrupt enabled; INTSR bit set = pending). */
#define GBP_PI_HSP_BIT 0x00002000u

/* ---- address helpers (pure, tested on host) --------------------------- */

/* Internal ARAM size from AR_INFO bits 0-2, as decoded by the Start-up
 * Disc (0x80089aac): 0→2 MB, 1→4 MB, 2→8 MB, 3→16 MB, 4→32 MB, else 0. */
uint32_t gbp_internal_size_from_arinfo(uint16_t arinfo);

/* AR_INFO with bits 3-5 replaced by 'code' (0..7), all other bits kept. */
uint16_t gbp_arinfo_with_expansion(uint16_t arinfo, unsigned code);

/* ARAM address of a block: base + (index << 20) + offset. offset must be a
 * multiple of 32 and < 1 MB; index 0..15. Returns 0 on bad input. */
uint32_t gbp_block_addr(uint32_t base, unsigned index, uint32_t offset);

const char *gbp_status_name(gbp_status s);

#ifdef __cplusplus
}
#endif
#endif
