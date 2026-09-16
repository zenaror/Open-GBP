/*
 * gbp_initirq4_probe.h — GBP-INIT-004: repeated service of the GBP HSP
 * interrupt (delivery → acknowledge → re-arm → next cause) with one
 * installed handler, three cycles, two re-arms.
 *
 * Normative description: docs/research/HARDWARE_TESTS.md (GBP-INIT-004),
 * docs/research/DEVLOG.md 2026-09-15 ("GBP-INIT-004 design"),
 * docs/protocol/INITIALIZATION.md §11. Not a runtime: no VIDEO/AUDIO DMA,
 * no KEYPAD, no SIO, no Link Port, no BBA, no Mobile Adapter, no Game Pak,
 * no callbacks, no unbounded loop — every wait has an operational bound.
 *
 * Question: after the first serviced cycle (GBP-INIT-003B, physically
 * executed 2026-09-15: latched cause → IRQ 26 delivered → one W1C → device
 * ACK `read | 0x8000`), does GBI's end-of-pass write `IRQ := 0x0000` (the
 * re-arm, GBP-IRQ-004) let the device raise the next cause, and does the
 * same handler service it again — three times, with the bookkeeping of
 * every boundary observed and no acknowledge that was not derived from a
 * read? The first cycle is semantically the 003B run up to its POSTACK.
 *
 * Reuse (no third copy of the sequence): the 003A stage runs verbatim
 * (gbp_initirqa_run_cause) up to the first latched cause; the per-cycle
 * service is gbp_irq_service.{h,c} (extracted from 003B); the teardown is
 * the 003A one with the 003B handler-restore hook; the handler body is the
 * 003B extended one-shot behind the generation wrapper
 * gbp_irq_multicycle_service (gbp_irq_oneshot.h) — installed ONCE, its
 * record slots write-once, the slot index published by this loop only while
 * INTMR bit 13 = 0.
 *
 * Per cycle n (0..2): CAUSE (EVENT for n = 0, NEXTCAUSE for n > 0) →
 * PREPARE (expected_gen := n, masked) → PREUNMASK-n (two PI samples latched
 * and masked, CONTROL 0x8C in both readings, Disc == GBI, an AV source
 * (0x0100 | 0x0400) pending, no source outside AV, odd/bit15/high bits 0,
 * slot n clean, generation n, cause after the previous re-arm) → one
 * __UnmaskIrq → delivery ≤ T_DELIVERY (100 ms) → main __MaskIrq (verified)
 * → PREACK-n → ACK `read | 0x8000` (exactly one per cycle, only with a
 * source pending, never for a source outside AV) → POSTACK-n (sources clear,
 * PI clean after at most the cycle's single main W1C) → [n < 2] REARM-n
 * `IRQ := 0x0000` → REARMPOST-n (A quiet / B latched / C source before the
 * PI latch / D unexpected source / E invalid shape / F PI without source) →
 * NEXTCAUSE-n: poll INTSR ≤ T_NEXT_CAUSE (500 ms), validate the source →
 * cycle n + 1. After cycle 2: no re-arm; the teardown (CONTROL restore, stop
 * word `read | 0x8AAA`, at most one PI W1C, handler restore, mask verified,
 * AR_INFO, FINAL) with the CPU masked. CONTROL is written once (the 003A
 * transform) and never per cycle — an intentional difference from GBI's
 * per-pass CONTROL write; a spontaneous change is an anomaly.
 *
 * Sources outside AV (0x0001 / 0x0004 / 0x0010 / 0x0040) are observed, never
 * acknowledged, never a transport failure: status anomaly_unexpected_source
 * with the raw block preserved. A generation out of range never indexes the
 * slot array (the handler counts it and services a poisoned slot without a
 * W1C). W1C budget by construction: one per delivery in the handler, at
 * most one per cycle in the main loop (POSTACK), none at REARMPOST, at most
 * one in the teardown — seven at most.
 *
 * Statuses: ok_cycles_completed only when 3 cycles completed, 3 deliveries,
 * 3 acknowledges, 2 re-arms, 2 next causes, no unexpected source, no
 * reentry, no sticky PI, no uncertain write, transport ok, CONTROL stable and
 * the restore ok; cycles_completed_with_errors when the cycles completed but
 * the restore/transport did not; the other statuses name the first
 * deviation and carry its cycle in the reason ("…_cycle_N"). Every path
 * runs the teardown; power_cycle_required is never cleared.
 */
#ifndef OPENGBP_GBP_INITIRQ4_PROBE_H
#define OPENGBP_GBP_INITIRQ4_PROBE_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_initirqa_probe.h"
#include "gbp_irq_service.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_INITIRQ4_MAX_CYCLES GBP_IRQ_MULTI_SLOTS   /* 3 */
#define GBP_INITIRQ4_MAX_REARMS 2u
#define GBP_INITIRQ4_REASON_LEN 48
#define GBP_INITIRQ4_TAG_LEN 16

struct gbp_initirq4_config {
    struct gbp_initirqa_config a;     /* the 003A stage (sequence, deadlines, shapes) */
    uint32_t t_delivery_ms;           /* delivery bound per cycle (100 ms; operational, not a device property) */
    uint32_t t_delivery_ticks;
    uint32_t t_next_cause_ms;         /* next-cause bound after a re-arm (500 ms; operational) */
    uint32_t t_next_cause_ticks;
    uint16_t ack_or;                  /* 0x8000: ACK = read | ack_or (GBI form, 003B validated) */
    uint16_t src_mask;                /* 0x0555: the even source bits */
    uint16_t av_mask;                 /* 0x0500: the sources this experiment services (VIDEO 0x0100, AUDIO 0x0400) */
    uint16_t odd_mask, bit15_mask, high_mask;   /* 0x0AAA / 0x8000 / 0x7000: must read 0 while armed */
    unsigned max_cycles;              /* 3 */
    unsigned max_rearms;              /* 2 */
};

void gbp_initirq4_config_default(struct gbp_initirq4_config *cfg);
void gbp_initirq4_config_timebase(struct gbp_initirq4_config *cfg, uint32_t tb_hz);

typedef enum {
    GBP_INITIRQ4_OK_CYCLES_COMPLETED = 0,
    GBP_INITIRQ4_CYCLES_COMPLETED_WITH_ERRORS, /* every cycle completed, but restore/transport/uncertain not clean */
    GBP_INITIRQ4_NO_INITIAL_CAUSE,
    GBP_INITIRQ4_NO_NEXT_CAUSE,
    GBP_INITIRQ4_DELIVERY_TIMEOUT,             /* reason delivery_timeout_cycle_N */
    GBP_INITIRQ4_ABORT_STAGE_A,                /* status_name = the 003A status name */
    GBP_INITIRQ4_ABORT_HANDLER_INSTALL,
    GBP_INITIRQ4_ABORT_PRE_UNMASK_STATE,
    GBP_INITIRQ4_ABORT_UNMASK,
    GBP_INITIRQ4_ABORT_READ_INCONSISTENT,      /* Disc reading != GBI reading at a per-cycle read */
    GBP_INITIRQ4_ABORT_TRANSPORT,              /* ack_write_failed_cycle_N, rearm_write_failed_cycle_N, *_read_failed_cycle_N */
    GBP_INITIRQ4_ANOMALY_REENTRY,
    GBP_INITIRQ4_ANOMALY_GENERATION,
    GBP_INITIRQ4_ANOMALY_MASK_FAILURE,
    GBP_INITIRQ4_ANOMALY_UNEXPECTED_SOURCE,
    GBP_INITIRQ4_ANOMALY_SOURCE_LOST_BEFORE_ACK,
    GBP_INITIRQ4_ANOMALY_SOURCE_NOT_CLEARED,
    GBP_INITIRQ4_ANOMALY_PI_STICKY_AFTER_ACK,
    GBP_INITIRQ4_ANOMALY_REARM_STATE,
    GBP_INITIRQ4_ANOMALY_CONTROL_CHANGED
} gbp_initirq4_status;

/* REARMPOST classification (see the header comment). */
enum {
    GBP_INITIRQ4_REARMPOST_NONE = 0,
    GBP_INITIRQ4_REARMPOST_A_QUIET,            /* no source, INTSR13 = 0: wait for the next cause */
    GBP_INITIRQ4_REARMPOST_B_LATCHED,          /* AV source pending and INTSR13 = 1: the next cause is already there */
    GBP_INITIRQ4_REARMPOST_C_SOURCE_BEFORE_PI, /* AV source pending, INTSR13 = 0: keep observing within the bound */
    GBP_INITIRQ4_REARMPOST_D_UNEXPECTED,       /* a source outside AV pending */
    GBP_INITIRQ4_REARMPOST_E_INVALID,          /* odd / bit 15 / high bits set after IRQ := 0 */
    GBP_INITIRQ4_REARMPOST_F_INCONSISTENT      /* INTSR13 = 1 with no source visible (or the two PI samples disagree downwards) */
};

struct gbp_initirq4_cycle {
    unsigned index;
    int started;
    char tag_preunmask[GBP_INITIRQ4_TAG_LEN], tag_preack[GBP_INITIRQ4_TAG_LEN], tag_postack[GBP_INITIRQ4_TAG_LEN];
    char tag_ack[GBP_INITIRQ4_TAG_LEN], tag_rearm[GBP_INITIRQ4_TAG_LEN], tag_rearmpost[GBP_INITIRQ4_TAG_LEN];
    char tag_nextcause[GBP_INITIRQ4_TAG_LEN];
    char nfield[12], sfx[8];
    /* cause */
    int cause_ready;                  /* a validated cause is latched for this cycle (EVENT / NEXTCAUSE) */
    uint32_t t_cause;                 /* EVENT ticks (n = 0) / the poll that saw INTSR bit 13 (n > 0) */
    uint16_t cause_irq;               /* IRQ reading at the cause */
    uint32_t cause_intsr;
    int cause_immediate;              /* n > 0: already latched at REARMPOST-(n-1) (outcome B) */
    unsigned cause_polls;             /* n > 0: INTSR polls of the wait */
    int cause_timed_out;
    uint32_t since_rearm;             /* n > 0: t_cause - t_rearm(n-1), wrap-safe */
    uint32_t since_prev_cause;        /* n > 0: t_cause - t_cause(n-1) */
    struct gbp_initirqa_snapshot nextcause;   /* n > 0, non-immediate: the NEXTCAUSE-(n-1) snapshot */
    /* prepare */
    int prepared;
    gbp_status prepare_rc;
    uint32_t prepare_intmr;           /* the PI evidence (last read) the publication relied on */
    struct gbp_irq_record slot_before;         /* slot n before the unmask: must be clean */
    struct gbp_irq_multi_status multi_before;
    /* preunmask */
    struct gbp_initirqa_snapshot preunmask;
    int preunmask_ok;
    const char *preunmask_reason;
    /* delivery */
    struct gbp_irq_delivery d;
    struct gbp_irq_multi_status multi_after;
    int delivered;                    /* fired, single entry, generation consistent, main mask verified */
    /* acknowledge */
    struct gbp_irq_ack k;
    int acked;                        /* w_ack.completed */
    uint16_t unexpected;              /* sources outside AV seen at `unexpected_site` */
    const char *unexpected_site;      /* "PREUNMASK", "PREACK", "POSTACK", "REARMPOST", "NEXTCAUSE" or "-" */
    int source_lost, source_not_cleared, pi_sticky;
    int pi_clean;                     /* INTSR13 = 0 and INTMR13 = 0 confirmed before the re-arm */
    uint32_t pi_clean_intsr, pi_clean_intmr;
    int boundary_ok;                  /* the cycle completed: delivery + ACK + POSTACK clean + PI clean */
    /* re-arm */
    int rearm_attempted, rearm_completed;
    uint32_t t_rearm;
    uint16_t rearm_before;
    struct gbp_regwrite_result w_rearm;
    struct gbp_initirqa_snapshot rearmpost;
    int rearmpost_outcome;            /* GBP_INITIRQ4_REARMPOST_* */
    int rearmpost_ok;                 /* mandatory checks held (CONTROL, INTMR13, Disc == GBI, shape) */
    /* timing, ticks (wrap-safe differences; 0 when not reached) */
    uint32_t dt_cause_to_isr, dt_isr_second, dt_isr_to_preack, dt_ack_to_postack, dt_postack_to_rearm, dt_rearm_to_next_cause;
};

struct gbp_initirq4_result {
    struct gbp_initirqa_result a;     /* the 003A stage: snapshots, writes, teardown flags, restore fields */
    gbp_initirq4_status status;
    const char *status_name;
    const char *reason;
    char reason_buf[GBP_INITIRQ4_REASON_LEN];
    int stage_a_aborted;
    int restore_ok;
    const char *restore_reason;
    const char *teardown_variant;     /* "final_cycle", "S2_before_unmask", "S3_cycle_aborted", "S4_rearm_failed",
                                       * "S4A_rearmed_no_next_cause", "S4B_next_cause_latched", "S4C_rearmpost_invalid", "stage_a" */
    struct gbp_irq_handler_state h;
    struct gbp_initirq4_cycle cycles[GBP_INITIRQ4_MAX_CYCLES];
    /* counters (by control flow of this loop) */
    unsigned cycles_requested, cycles_started, completed_cycles;
    unsigned causes, next_causes, deliveries, acks, rearms_attempted, rearms_completed, unmasks;
    unsigned unexpected_sources, reentries, timeouts, generation_errors, entries_total;
    unsigned isr_w1c, main_w1c, teardown_w1c;
    int control_ok;                   /* CONTROL read 0x8C at every per-cycle check */
    int pi_sticky_final;
    struct gbp_irq_multi_status multi_final;
    unsigned uncertain_writes;
    unsigned errors;
    int transport_ok;
    int power_cycle_required;
};

/* Runs the experiment; always returns after the teardown. Returns 0 if it
 * completed (aborted or not), -1 only if AR_INFO could not be read. */
int gbp_initirq4_probe_run(const struct gbp_transport *t, struct ringlog *log,
                           const struct gbp_initirq4_config *cfg, struct gbp_initirq4_result *res);

int gbp_initirq4_summary(const struct gbp_initirq4_result *res, char *dst, size_t cap);
const char *gbp_initirq4_status_name(gbp_initirq4_status s);
const char *gbp_initirq4_rearmpost_name(int outcome);

#ifdef __cplusplus
}
#endif
#endif
