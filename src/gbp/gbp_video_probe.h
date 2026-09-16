/*
 * gbp_video_probe.h — GBP-VIDEO-001: bounded VIDEO block-sequence capture
 * under repeated drained service of the Game Boy Player HSP interrupt (the
 * first dedicated Phase 4 experiment).
 *
 * Normative description: docs/research/HARDWARE_TESTS.md "Planned tests —
 * GBP-VIDEO-001" (designed 2026-09-16, specification reviewed twice the same
 * day), docs/research/VIDEO_PATH.md, docs/protocol/INITIALIZATION.md §14.
 * Not a runtime: no framebuffer, no video conversion, no frame sync, no
 * audio playback, no KEYPAD, no SIO, no Link Port, no BBA, no Mobile
 * Adapter, no Game Pak logic, no callbacks, no unbounded loop, no malloc.
 *
 * Question: over a bounded sequence of delivered HSP causes serviced the
 * reference way (read IRQ → drain AUDIO if 0x0400 → drain VIDEO if 0x0100 →
 * ACK `pending | 0x8000` → PI clean → `IRQ := 0` → next cause), what is the
 * physical VIDEO block stream — on which blocks each frame-start predicate
 * (GBI's, the Disc's) is true, how many blocks lie between two consecutive
 * true predicates, in which order the blocks arrive, at what intervals the
 * sources appear — and does the repeated service stay stable? The content
 * is never compared with anything on the console (tools/avseq.py does that
 * offline); the probe's status derives from SERVICE, CAPTURE and RESTORE only.
 *
 * Reuse (no new initialization, no new ISR): the 003A stage runs verbatim
 * (gbp_initirqa_run_cause) up to the first latched cause; the handler is
 * the 003B extended one-shot installed ONCE and its record is reset between
 * deliveries through the transport's irq_record_reset (memory only, under
 * mask); the delivery is gbp_irq_service_deliver_quiet (the AVSVC / 003B
 * operation sequence, formatted only in the verify cycles); the drains are
 * gbp_avblock; the records, buffers, predicates and boundaries are
 * gbp_avseq; the teardown is the 003A one with the 003B hook.
 *
 * State machine (CPU masked everywhere except inside the unmask call):
 *   INIT_ENTRY (003A stage → first cause → install → PREUNMASK) →
 *   [CHECK_ADMISSION → PREPARE → UNMASK → CONFIRM → READ → AUDIO → VIDEO →
 *    ACK → PICLEAN → REARM → WAIT_NEXT]* → TEARDOWN
 * CHECK_ADMISSION (before every cycle but the first): admission budget not
 * expired, deliveries < MAX_DELIVERIES, video blocks < TARGET, a cause
 * latched. Refused → the loop ends normally (runtime_cap / delivery_cap /
 * target_reached), the latched cause is left for the teardown, no unmask.
 * A cycle whose CONFIRM held is TRANSACTIONAL: READ … REARM complete whatever
 * the clock says (each step under its own bound, no retry); the admission
 * deadline never interrupts it. WAIT_NEXT is a masked read-only poll of
 * INTSR bit 13 bounded by min(T_NEXT_CAUSE, remaining budget), a single read
 * when no budget is left; nothing is written to the PI between the next
 * cause and the next unmask. W1C budget per cycle: handler 1, main <= 1
 * (PICLEAN), teardown <= 1.
 */
#ifndef OPENGBP_GBP_VIDEO_PROBE_H
#define OPENGBP_GBP_VIDEO_PROBE_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_initirqa_probe.h"
#include "gbp_irq_service.h"
#include "gbp_avblock.h"
#include "gbp_avseq.h"
#include "gbp_avseqdump.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_VIDEO_REASON_LEN 64

struct gbp_video_config {
    struct gbp_initirqa_config a;     /* the 003A stage (sequence, deadlines, shapes) */
    uint32_t t_delivery_ms, t_delivery_ticks;        /* handler-entry bound after an unmask (100 ms) */
    uint32_t t_next_cause_ms, t_next_cause_ticks;    /* masked poll after a re-arm (100 ms) */
    uint32_t admission_budget_ms, admission_budget_ticks;   /* service-loop admission budget (1000 ms) */
    unsigned target_video_blocks;     /* 88 (<= GBP_AVSEQ_MAX_VIDEO_BLOCKS) */
    unsigned max_deliveries;          /* 320 (<= GBP_AVSEQ_MAX_DELIVERIES) */
    unsigned verify_cycles;           /* 4: the first cycles take the AVSVC snapshots */
    uint16_t ack_or, src_mask, av_mask, audio_src, video_src, odd_mask, bit15_mask, high_mask;
    unsigned audio_index, video_index;
    uint32_t audio_len, video_len;
    struct gbp_avseq_store *store;    /* caller's records and buffers */
};

void gbp_video_config_default(struct gbp_video_config *cfg);
void gbp_video_config_timebase(struct gbp_video_config *cfg, uint32_t tb_hz);

typedef enum {
    GBP_VIDEO_OK_SEQUENCE_CAPTURE = 0,           /* target reached, service ok, restore ok */
    GBP_VIDEO_OK_TARGET_NOT_REACHED_DELIVERY_CAP,
    GBP_VIDEO_OK_TARGET_NOT_REACHED_RUNTIME_CAP,
    GBP_VIDEO_OBSERVATION_NO_NEXT_CAUSE,         /* T_NEXT_CAUSE expired with budget left */
    GBP_VIDEO_CAPTURE_COMPLETED_WITH_ERRORS,     /* the loop ended normally but restore / transport / uncertainty not clean */
    GBP_VIDEO_NO_INITIAL_CAUSE,
    GBP_VIDEO_FIRST_DELIVERY_TIMEOUT,
    GBP_VIDEO_ABORT_STAGE_A,
    GBP_VIDEO_ABORT_HANDLER_INSTALL,
    GBP_VIDEO_ABORT_PRE_UNMASK_STATE,
    GBP_VIDEO_ABORT_UNMASK,
    GBP_VIDEO_ABORT_BULK_UNAVAILABLE,
    GBP_VIDEO_ABORT_RESET_UNAVAILABLE,           /* the transport cannot reset the handler record (host only) */
    GBP_VIDEO_ABORT_STORE_UNAVAILABLE,           /* no records / buffers given */
    GBP_VIDEO_ABORT_PRESVC_STATE,
    GBP_VIDEO_ABORT_READ_INCONSISTENT,
    GBP_VIDEO_ABORT_TRANSPORT,
    GBP_VIDEO_ABORT_CAPACITY,                    /* a table or buffer is full before a cap (defensive) */
    GBP_VIDEO_ACK_WRITE_FAILED,
    GBP_VIDEO_REARM_WRITE_FAILED,
    GBP_VIDEO_AUDIO_DMA_BUSY,
    GBP_VIDEO_AUDIO_DMA_TIMEOUT,
    GBP_VIDEO_AUDIO_DMA_ERROR,
    GBP_VIDEO_VIDEO_DMA_BUSY,
    GBP_VIDEO_VIDEO_DMA_TIMEOUT,
    GBP_VIDEO_VIDEO_DMA_ERROR,
    GBP_VIDEO_ANOMALY_REENTRY,
    GBP_VIDEO_ANOMALY_MISSED_ENTRY,
    GBP_VIDEO_ANOMALY_ISR_STATE,
    GBP_VIDEO_ANOMALY_RECORD_NOT_CLEAR,
    GBP_VIDEO_ANOMALY_MASK_FAILURE,
    GBP_VIDEO_ANOMALY_UNEXPECTED_SOURCE,
    GBP_VIDEO_ANOMALY_CAUSE_WITHOUT_SOURCE,
    GBP_VIDEO_ANOMALY_CONTROL_CHANGED,
    GBP_VIDEO_ANOMALY_POSTACK_SHAPE,
    GBP_VIDEO_ANOMALY_PI_STICKY,
    GBP_VIDEO_ANOMALY_REARM_STATE
} gbp_video_status;

struct gbp_video_result {
    struct gbp_initirqa_result a;     /* the 003A stage: snapshots, writes, teardown flags, restore fields */
    gbp_video_status status;
    const char *status_name;
    const char *status_class;         /* "ok", "observation", "errors", "abort", "transport", "dma", "anomaly" */
    const char *reason;
    char reason_buf[GBP_VIDEO_REASON_LEN];
    int stage_a_aborted;
    int restore_ok;
    const char *restore_reason;
    const char *teardown_variant;
    struct gbp_irq_handler_state h;
    struct gbp_avseq_store *store;
    /* ---- result matrix ---- */
    int service_ok;                   /* SERVICE: 1 until a service failure */
    const char *service_reason;
    int capture;                      /* CAPTURE: enum gbp_avseq_end */
    int next_cause_at_end;            /* a cause was latched when the loop ended (never delivered; the teardown acknowledges it) */
    struct gbp_avseq_boundaries b_gbi, b_disc;   /* BOUNDARIES_GBI / _DISC (+ COMPLETE_INTERVAL each) */
    /* REFERENCE_CONTENT is never computed here (offline only); RESTORE = restore_ok */
    /* ---- first cause and the install ---- */
    uint32_t t_cause;
    uint16_t cause_irq;
    struct gbp_initirqa_snapshot preunmask;
    int preunmask_ok;
    const char *preunmask_reason;
    /* ---- admission ---- */
    uint32_t t0;                      /* the first admitted unmask */
    uint32_t admission_deadline;      /* t0 + budget (wrap-safe arithmetic everywhere) */
    int deadline_armed;
    unsigned admissions, refusals;
    const char *refusal;              /* "-", "runtime_cap", "delivery_cap", "target_reached" */
    /* ---- per-cycle scratch (the values of the last cycle) ---- */
    struct gbp_irq_delivery d;
    struct gbp_irq_ack k;
    struct gbp_avblock audio, video;
    struct gbp_initirqa_snapshot presvc, postdrain, rearmpost;   /* verify cycles */
    struct gbp_regwrite_result w_ack, w_rearm;
    char id_presvc[20], id_postdrain[20], id_postack[20], id_rearmpost[20], tag_ack[20], tag_rearm[20], nfield[12], sfx[8];
    /* ---- counters ---- */
    unsigned deliveries, unmasks, acks, rearms, isr_w1c, main_w1c, teardown_w1c;
    unsigned lean_cycles, verify_cycles_done;
    unsigned audio_drains, audio_completed, video_blocks, video_completed;
    unsigned unexpected_cycle;
    uint16_t unexpected;
    const char *unexpected_site;
    int control_ok;
    int pi_sticky_final;
    unsigned uncertain_writes;
    unsigned errors;
    int transport_ok;
    int power_cycle_required;
    uint32_t dt_cause_to_isr_first;   /* the first cycle's cause → handler entry */
};

/* Runs the experiment; always returns after the teardown. Returns 0 if it
 * completed (aborted or not), -1 only if AR_INFO could not be read. */
int gbp_video_probe_run(const struct gbp_transport *t, struct ringlog *log,
                        const struct gbp_video_config *cfg, struct gbp_video_result *res);

int gbp_video_summary(const struct gbp_video_result *res, char *dst, size_t cap);
const char *gbp_video_status_name(gbp_video_status s);
const char *gbp_video_status_class(gbp_video_status s);

/* Fills the sequence-sidecar description from a result (counts, flags, identities). Returns 0
 * when every identity fits the format (never truncated). */
int gbp_video_dump_info(const struct gbp_video_result *res, uint32_t tb_hz, const char *test_id,
                        const char *build_id, const char *app, const char *commit, struct gbp_avseqdump_info *info);

#ifdef __cplusplus
}
#endif
#endif
