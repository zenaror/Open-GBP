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
    /* handler */
    int irq_path_available;
    gbp_status install_rc;
    int handler_installed;         /* currently installed */
    int handler_was_installed;     /* installed at some point (teardown restores) */
    int old_handler_null;          /* 1 NULL, 0 non-NULL, -1 unknown */
    uint32_t install_count, install_fired;   /* the record right after the install: must be 0/0 before the unmask */
    gbp_status handler_restore_rc;
    int handler_restored;          /* -1 not attempted, 1 ok, 0 failed */
    /* pre-unmask */
    struct gbp_initirqa_snapshot preunmask;
    int preunmask_ok;
    const char *preunmask_reason;
    /* unmask and wait */
    int pi_pre_unmask_ok, pi_post_unmask_ok;
    uint32_t intsr_pre_unmask, intmr_pre_unmask, intsr_post_unmask, intmr_post_unmask;
    uint32_t t_unmask, t_post_unmask, t_wait_end, wait_ticks;
    gbp_status unmask_rc;
    int irq_unmasked;
    unsigned polls;
    int timed_out;
    /* main re-mask */
    gbp_status mask_rc;
    int irq_masked_again;
    int main_mask_ok;              /* -1 not checked, 1 INTMR bit 13 = 0 after the re-mask, 0 not */
    int remask_retry;
    uint32_t intsr_remask, intmr_remask;
    /* handler record (copied while masked) */
    struct gbp_irq_record rec;
    int fired, reentry;
    uint32_t latency_ticks, latency_us;
    /* pre-ack / ack / post-ack */
    struct gbp_initirqa_snapshot preack, postack;
    uint16_t irq_pending, ack_value;
    struct gbp_regwrite_result w_ack;
    int ack_skipped;
    const char *ack_skip_reason;
    /* main-loop PI W1C (budget: one per run) */
    int main_pi_w1c;
    const char *main_pi_w1c_site;  /* "POSTACK", "CLEANUP" or "-" */
    gbp_status main_w1c_rc;
    uint32_t main_w1c_intsr_before, main_w1c_intsr_after;
    int main_w1c_sticky;
    /* teardown extras */
    int mask_ok;                   /* -1 not checked, 1 INTMR bit 13 = 0 at the end, 0 not */
    uint32_t intmr_final;
    int pi_sticky_final;           /* INTSR bit 13 still 1 at the end of the PI step (no W1C left in the budget) */
    /* totals */
    unsigned uncertain_writes;
    unsigned errors;
    int transport_ok;
    int power_cycle_required;
};

/* Runs the experiment; always returns after the teardown. */
int gbp_initirqb_probe_run(const struct gbp_transport *t, struct ringlog *log,
                           const struct gbp_initirqb_config *cfg, struct gbp_initirqb_result *res);

int gbp_initirqb_summary(const struct gbp_initirqb_result *res, char *dst, size_t cap);
const char *gbp_initirqb_status_name(gbp_initirqb_status s);

#ifdef __cplusplus
}
#endif
#endif
