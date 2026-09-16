/*
 * gbp_initirqb_probe.h — GBP-INIT-003B: delivery of a latched HSP cause
 * to the CPU as IRQ 26.
 *
 * Normative description: docs/research/HARDWARE_TESTS.md "Planned tests —
 * GBP-INIT-003B", docs/research/DEVLOG.md 2026-09-15 "GBP-INIT-003B
 * designed", docs/protocol/INITIALIZATION.md §9 (R1–R8) and §11.
 *
 * Question: with a real HSP cause already latched at the PI (INTSR bit
 * 13 = 1) while IRQ 26 is masked (INTMR bit 13 = 0) — the state
 * GBP-INIT-003A produced ≈105 ms after its write A2 — does
 * __UnmaskIrq(IM_PI_HSP) deliver it to the CPU handler at once? And what
 * does INTSR do after the handler's write-1-to-clear while the GBS-DOL
 * source has not been acknowledged (level/pulse discriminator, U-GBP-022)?
 *
 * The 003A sequence (AR_INFO 3 → gate → PI preconditions → BASE → CONTROL
 * transform → P0 → A1 → A2 → masked window) is executed verbatim through
 * gbp_initirqa_run_cause(); nothing of the executed experiment is copied.
 * Only after INTSR bit 13 has been observed (EVENT) does this module act:
 *   IRQ_Request(26, one-shot ext) → PREUNMASK snapshot + preconditions →
 *   t_unmask, one __UnmaskIrq → wait for the handler up to T_DELIVERY →
 *   __MaskIrq (idempotent) → INTMR bit 13 must read 0 → record copied →
 *   PREACK snapshot → device ACK `IRQ := read | 0x8000` (GBI's form, A1's
 *   physically validated write) → POSTACK snapshot → at most one main-loop
 *   INTSR W1C → the 003A teardown (CONTROL restore, Disc stop word, PI
 *   check with the W1C budget, handler restore + mask check, AR_INFO,
 *   FINAL). Every path after the CONTROL write ends in that teardown.
 *
 * PI INTSR write-1-to-clear budget: exactly one in the handler (after the
 * mask), at most one in the main loop (POSTACK, else CLEANUPCHK), never
 * repeated: two per run maximum. INTMR is changed only through
 * __UnmaskIrq (once) and __MaskIrq; never stored directly.
 *
 * Writes (complete): the 003A set (AR_INFO bits 3–5, TEST handshake,
 * CONTROL transform/restore, IRQ A1 / A2 / stop) plus the device ACK —
 * four IRQ-register write sites in the linked objects. Never: KEYPAD,
 * VIDEO, AUDIO, SIOCTL, SIODATA, BBA. A console power cycle is mandatory
 * after any run that attempted an experimental write.
 */
#ifndef OPENGBP_GBP_INITIRQB_PROBE_H
#define OPENGBP_GBP_INITIRQB_PROBE_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_initirqa_probe.h"
#include "gbp_irq_service.h"

#ifdef __cplusplus
extern "C" {
#endif

struct gbp_initirqb_config {
    struct gbp_initirqa_config a;   /* the 003A stage, unchanged defaults */
    uint32_t t_delivery_ms;         /* operational bound for the delivery after the unmask (100 ms) */
    uint32_t t_delivery_ticks;
    uint16_t ack_or;                /* 0x8000: device ACK = read | ack_or */
    uint16_t src_mask;              /* 0x0555: at least one of these must read 1 before the unmask */
    uint16_t odd_mask;              /* 0x0AAA: must read 0 before the unmask (as A2 wrote them) */
    uint16_t bit15_mask;            /* 0x8000: must read 0 before the unmask */
    uint16_t high_mask;             /* 0x7000: must read 0 before the unmask */
};

void gbp_initirqb_config_default(struct gbp_initirqb_config *cfg);
void gbp_initirqb_config_timebase(struct gbp_initirqb_config *cfg, uint32_t tb_hz);

typedef enum {
    GBP_INITIRQB_OK_DELIVERY_OBSERVED = 0, /* handler fired once after the unmask */
    GBP_INITIRQB_DELIVERY_TIMEOUT,         /* INTMR bit 13 opened, nothing fired within T_DELIVERY (not a transport error) */
    GBP_INITIRQB_NO_CAUSE_WITHIN_TMAX,     /* the 003A window ended without INTSR bit 13 (not a transport error) */
    GBP_INITIRQB_ABORT_STAGE_A,            /* the 003A stage aborted: status_name/reason carry its status */
    GBP_INITIRQB_ABORT_HANDLER_INSTALL,    /* no IRQ path in the transport, or install failed */
    GBP_INITIRQB_ABORT_PRE_UNMASK_STATE,   /* PREUNMASK preconditions failed (reason names which) */
    GBP_INITIRQB_ABORT_UNMASK,             /* unmask failed or INTMR bit 13 never became 1 and nothing fired */
    GBP_INITIRQB_ANOMALY_REENTRY,          /* handler entered more than once */
    GBP_INITIRQB_ANOMALY_MASK_FAILURE      /* INTMR bit 13 still 1 after the handler and the main re-mask */
} gbp_initirqb_status;

struct gbp_initirqb_result {
    struct gbp_initirqa_result a;  /* the 003A stage: snapshots, writes, teardown flags, restore fields */
    gbp_initirqb_status status;
    const char *status_name;       /* 003A's status name when the stage aborted, else gbp_initirqb_status_name() */
    const char *reason;
    int stage_a_aborted;
    int restore_ok;                /* a.restore_ok and handler restored and mask ok */
    const char *restore_reason;
    struct gbp_irq_handler_state h;    /* install / restore / final mask (gbp_irq_service.h) */
    /* pre-unmask */
    struct gbp_initirqa_snapshot preunmask;
    int preunmask_ok;
    const char *preunmask_reason;
    struct gbp_irq_delivery d;         /* one unmask → delivery → re-mask → record (gbp_irq_service.h) */
    struct gbp_irq_ack k;              /* PREACK → device ACK → POSTACK → main W1C budget (gbp_irq_service.h) */
    int pi_sticky_final;           /* INTSR bit 13 still 1 at the end of the PI step (no W1C left in the budget) */
    /* totals */
    unsigned uncertain_writes;
    unsigned errors;
    int transport_ok;
    int power_cycle_required;
};

/* The cycle service (unmask/deliver/re-mask/record, PREACK/ACK/POSTACK/main
 * W1C, teardown hook) lives in gbp_irq_service.{h,c} since GBP-INIT-004: the
 * functions were extracted from this module verbatim; the physical fixture of
 * the 2026-09-15 run pins the behavior and every log line of this probe.
 * Runs the experiment; always returns after the teardown. */
int gbp_initirqb_probe_run(const struct gbp_transport *t, struct ringlog *log,
                           const struct gbp_initirqb_config *cfg, struct gbp_initirqb_result *res);

int gbp_initirqb_summary(const struct gbp_initirqb_result *res, char *dst, size_t cap);
const char *gbp_initirqb_status_name(gbp_initirqb_status s);

#ifdef __cplusplus
}
#endif
#endif
