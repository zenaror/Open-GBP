/*
 * gbp_irq_service.h — the service primitives of one PI HSP interrupt cycle,
 * extracted verbatim from GBP-INIT-003B (physically executed 2026-09-15,
 * build initirqb-0001) so that GBP-INIT-004 repeats them per cycle without a
 * third copy of the sequence.
 *
 * Policy-free: the callers decide the preconditions, the statuses and the
 * teardown. Every log record is the 003B one with two optional decorations:
 * `nfield`, inserted right after the record kind (e.g. " n=0"), and `sfx`,
 * appended to the snapshot / PI / IRQW tags (e.g. "-0"). With nfield = ""
 * and sfx = "" the output is byte-identical to the executed 003B build,
 * which its physical fixture pins (tests/unit/test_gbp_initirqb.c).
 *
 *   gbp_irq_service_preunmask_check   the 003B preconditions on a snapshot
 *   gbp_irq_service_deliver           one __UnmaskIrq, the bounded wait on the
 *                                     record, the main re-mask (+ one retry),
 *                                     the record copy while masked, its records
 *   gbp_irq_service_ack               PREACK snapshot, device ACK `read | ack_or`
 *                                     through gbp_regwrite_irq_u16 (attempted
 *                                     before the call, completed on rc ok),
 *                                     POSTACK snapshot, the cycle's single
 *                                     main-loop INTSR W1C when bit 13 reads 1
 *   gbp_irq_service_teardown_hook     previous handler back, mask verified
 * Nothing here formats inside a handler or between the unmask and the
 * re-mask other than what 003B did (values first, records afterwards).
 */
#ifndef OPENGBP_GBP_IRQ_SERVICE_H
#define OPENGBP_GBP_IRQ_SERVICE_H

#include <stdint.h>
#include "gbp_transport.h"
#include "gbp_initirqa_probe.h"
#include "gbp_regwrite.h"
#include "ringlog.h"

#ifdef __cplusplus
extern "C" {
#endif

/* One unmask → delivery → re-mask → record copy (GBP-INIT-003B steps 5–8). */
struct gbp_irq_delivery {
    int pi_pre_unmask_ok, pi_post_unmask_ok;
    uint32_t intsr_pre_unmask, intmr_pre_unmask, intsr_post_unmask, intmr_post_unmask;
    uint32_t t_unmask, t_post_unmask, t_wait_end, wait_ticks;
    gbp_status unmask_rc;
    int irq_unmasked;              /* the unmask was attempted (the teardown re-masks anyway) */
    unsigned polls;
    int timed_out;
    gbp_status mask_rc;
    int irq_masked_again;
    int main_mask_ok;              /* -1 not checked, 1 INTMR bit 13 = 0 after the re-mask, 0 not */
    int remask_retry;
    uint32_t intsr_remask, intmr_remask;
    struct gbp_irq_record rec;     /* the handler record, copied while masked */
    int fired, reentry;
    uint32_t latency_ticks, latency_us;
};

/* PREACK → device ACK → POSTACK → main-loop W1C budget (GBP-INIT-003B steps 9–12). */
struct gbp_irq_ack {
    struct gbp_initirqa_snapshot preack, postack;
    uint16_t irq_pending, ack_value;
    uint16_t unexpected;           /* pending sources outside `allowed_src` at PREACK (0 when every source is allowed) */
    int source_zero;               /* no source of src_mask pending at PREACK */
    struct gbp_regwrite_result w_ack;
    int ack_skipped;
    const char *ack_skip_reason;   /* "-", "irq_read_failed", "semantic_disagree", "unexpected_source", "source_lost",
                                    * "control_changed", "intmr13_set" (the last two only with require_control) */
    int main_pi_w1c;
    const char *main_pi_w1c_site;  /* "POSTACK" or "-" */
    gbp_status main_w1c_rc;
    uint32_t main_w1c_intsr_before, main_w1c_intsr_after;
    uint32_t main_w1c_intmr_after; /* INTMR of the MAINCLEANUP re-read (GBP-INIT-004 needs both bits before a re-arm) */
    int main_w1c_sticky;
};

/* Handler install / restore / final mask state. */
struct gbp_irq_handler_state {
    int irq_path_available;
    gbp_status install_rc;
    int handler_installed;         /* currently installed */
    int handler_was_installed;     /* installed at some point (the teardown restores) */
    int old_handler_null;          /* 1 NULL, 0 non-NULL, -1 unknown */
    uint32_t install_count, install_fired;   /* the record right after the install: must be 0/0 */
    gbp_status handler_restore_rc;
    int handler_restored;          /* -1 not attempted, 1 ok, 0 failed */
    int mask_ok;                   /* -1 not checked, 1 INTMR bit 13 = 0 at the end, 0 not */
    uint32_t intmr_final;
};

void gbp_irq_service_delivery_init(struct gbp_irq_delivery *d);
void gbp_irq_service_ack_init(struct gbp_irq_ack *k);
void gbp_irq_service_handler_init(struct gbp_irq_handler_state *h);

/* The 003B PREUNMASK preconditions on a snapshot taken with two PI samples:
 * reads ok, record clean, INTSR bit 13 = 1 in both samples, INTMR bit 13 = 0
 * in both, CONTROL vote == control_exp == byte 0x1F, Disc == GBI reading,
 * at least one source of src_mask, odd/bit15/high masks clear. Returns 1 and
 * *why = "-" when everything holds, else 0 and the reason. */
int gbp_irq_service_preunmask_check(const struct gbp_initirqa_snapshot *s, uint8_t control_exp,
                                    uint16_t src_mask, uint16_t odd_mask, uint16_t bit15_mask, uint16_t high_mask,
                                    uint32_t install_count, uint32_t install_fired, const char **why);
void gbp_irq_service_log_preunmask(struct ringlog *log, const char *nfield, const struct gbp_initirqa_snapshot *s,
                                   int ok, const char *why, uint16_t src_mask, uint16_t odd_mask, uint16_t bit15_mask);

/* Steps 5–8: UNMASKPRE read, t_unmask, one irq_unmask, t_post, UNMASKPOST read,
 * wait for the record's `fired` up to t_delivery_ticks (record polled only),
 * irq_mask, WAIT/REMASKCHK (+ one RETRY), record copy, HANDLER/HANDLERPI/
 * HANDLERPI2/DELIVERY records. `slot` < 0 reads the record with irq_record;
 * `slot` >= 0 reads it with irq_record_slot when the transport has it. */
void gbp_irq_service_deliver(const struct gbp_transport *t, struct ringlog *log, uint32_t tb_hz,
                             uint32_t t_delivery_ms, uint32_t t_delivery_ticks, int slot,
                             const char *nfield, const char *sfx, struct gbp_irq_delivery *d, unsigned *errors);

/* Steps 9–12: PREACK snapshot (two PI samples), device ACK `pending | ack_or`
 * (skipped when the IRQ read failed, when the two readings disagree, when a
 * pending source lies outside `allowed_src`, when require_source is set and
 * no source of src_mask is pending, or — with require_control — when CONTROL
 * does not read control_exp in both readings or INTMR bit 13 reads 1),
 * POSTACK snapshot, and the cycle's single main-loop INTSR W1C if bit 13
 * reads 1 there while masked. The tags name the snapshots / the IRQW record
 * ("PREACK", "POSTACK", "tag=ACK" for 003B, which passes require_control = 0). */
void gbp_irq_service_ack(const struct gbp_transport *t, struct ringlog *log, struct gbp_initirqa_result *a,
                         uint16_t ack_or, uint16_t src_mask, uint16_t allowed_src, int require_source,
                         int require_control, uint8_t control_exp,
                         const char *nfield, const char *tag_preack, const char *tag_postack, const char *tag_ack,
                         const char *sfx, struct gbp_irq_ack *k, unsigned *errors);

/* Teardown step between the PI check and the AR_INFO restore: the previous
 * handler back (verbatim), then the mask state verified with one retry when
 * `engaged`. Returns the first failure reason ("handler_restore_failed",
 * "mask_not_restored") or NULL. */
const char *gbp_irq_service_teardown_hook(const struct gbp_transport *t, struct ringlog *log,
                                          struct gbp_irq_handler_state *h, int engaged, unsigned *errors);

#ifdef __cplusplus
}
#endif
#endif
