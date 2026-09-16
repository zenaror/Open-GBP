/*
 * gbp_avsvc_probe.h — GBP-AV-SERVICE-001: the first drained service of the
 * Game Boy Player HSP interrupt — read the pending AUDIO / VIDEO blocks,
 * acknowledge, re-arm, observe the next cause (Phase 4 entry).
 *
 * Normative description: docs/research/HARDWARE_TESTS.md "Planned tests —
 * GBP-AV-SERVICE-001", docs/research/DEVLOG.md 2026-09-16 ("next step after
 * GBP-INIT-004 decided"), docs/protocol/INITIALIZATION.md §4 / §13. Not a
 * runtime: no framebuffer, no video conversion, no frame sync, no audio
 * playback, no KEYPAD, no SIO, no Link Port, no BBA, no Mobile Adapter, no
 * Game Pak logic, no callbacks, no unbounded loop. AUDIO and VIDEO are raw
 * blocks drained to RAM, summarized after the timed region, never
 * interpreted.
 *
 * Question: after one validated delivery of an HSP cause (GBP-INIT-003B /
 * 004, FACT), does ONE reference-style service pass — read IRQ (pending),
 * drain every pending AV block with one whole-block DMA each (AUDIO 0x1000
 * at index 0x8, then VIDEO 0xF00 at index 0x1: the order of both
 * references), ACK `pending | 0x8000`, re-arm `IRQ := 0x0000` — lead to a
 * NEW PI HSP cause with a valid AV source within a bound, with the CPU
 * masked throughout and no second delivery? Secondary: the raw content of
 * the blocks (length, DMA duration, CRC-32, byte windows; whole bytes in
 * the sidecar of gbp_avdump.h).
 *
 * Reuse (no fourth copy of the initialization): the 003A stage runs
 * verbatim (gbp_initirqa_run_cause) up to the first latched cause; the
 * handler is the 003B extended one-shot (hsp_backend_oneshot_isr_ext,
 * physically executed 2026-09-15; a second delivery is forbidden here, so
 * no generation wrapper); the delivery, the ACK/POSTACK/main-W1C step and
 * the teardown hook are gbp_irq_service.{h,c}; the block reads are
 * gbp_avblock.{h,c}; the teardown is the 003A one.
 *
 * Sequence:
 *   003A stage (PI masked, no handler) → CAUSE → IRQ_Request(26, ext) once →
 *   PREUNMASK (003B checks + AV rule) → one __UnmaskIrq → delivery → main
 *   __MaskIrq verified → PRESVC (PI ×2, CONTROL, IRQ: the AUTHORITATIVE
 *   snapshot; pending_irq := its semantic value; the block set and the ACK
 *   value derive from it and never from a later read) → AUDIOREAD (if
 *   pending & 0x0400) → VIDEOREAD (if pending & 0x0100) → SVCEND →
 *   POSTDRAIN (observation only) → ACK `pending_irq | 0x8000` → POSTACK
 *   (no source requirement: the AV bits are data) → PICLEAN (≤ 1 main W1C)
 *   → REARM `IRQ := 0x0000` → REARMPOST (A/B/C/D/E/F) → NEXTCAUSE ≤ 500 ms
 *   (INTSR polled while masked, never delivered) → teardown with the CPU
 *   masked (CONTROL restore, stop word `read | 0x8AAA`, ≤ 1 PI W1C,
 *   handler restore, mask check, AR_INFO, FINAL). Power cycle mandatory.
 *
 * W1C budget by construction: handler 1, main ≤ 1 (POSTACK), NEXTCAUSE 0,
 * teardown ≤ 1 — three at most. INTMR: one __UnmaskIrq, the handler's
 * mask, the main re-mask; never a second unmask, never a direct store.
 * The second cause, if it arrives, stays latched: INTMR bit 13 = 0, no
 * second ISR, no second service; the teardown's stop word and single W1C
 * close it.
 */
#ifndef OPENGBP_GBP_AVSVC_PROBE_H
#define OPENGBP_GBP_AVSVC_PROBE_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_initirqa_probe.h"
#include "gbp_irq_service.h"
#include "gbp_avblock.h"
#include "gbp_avdump.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_AVSVC_REASON_LEN 48

struct gbp_avsvc_config {
    struct gbp_initirqa_config a;     /* the 003A stage (sequence, deadlines, shapes) */
    uint32_t t_delivery_ms;           /* delivery bound (100 ms; operational, not a device property) */
    uint32_t t_delivery_ticks;
    uint32_t t_next_cause_ms;         /* next-cause bound after the re-arm (500 ms; operational) */
    uint32_t t_next_cause_ticks;
    uint16_t ack_or;                  /* 0x8000: ACK = pending | ack_or (GBI form, 003B/004 validated) */
    uint16_t src_mask;                /* 0x0555: the even source bits */
    uint16_t av_mask;                 /* 0x0500: the sources this experiment services */
    uint16_t audio_src, video_src;    /* 0x0400 / 0x0100 */
    unsigned audio_index, video_index;/* 0x8 / 0x1 */
    uint32_t audio_len, video_len;    /* 0x1000 / 0xF00 */
    uint16_t odd_mask, bit15_mask, high_mask;   /* 0x0AAA / 0x8000 / 0x7000 */
    /* caller's buffers: static, 32-byte aligned, at least the lengths above */
    uint8_t *audio_buf;
    uint32_t audio_cap;
    uint8_t *video_buf;
    uint32_t video_cap;
};

void gbp_avsvc_config_default(struct gbp_avsvc_config *cfg);
void gbp_avsvc_config_timebase(struct gbp_avsvc_config *cfg, uint32_t tb_hz);

typedef enum {
    GBP_AVSVC_OK_SERVICE_REARM_CAUSE_OBSERVED = 0,
    GBP_AVSVC_NO_NEXT_CAUSE_AFTER_SERVICE,      /* re-arm completed, no cause within the bound: a valid physical result */
    GBP_AVSVC_SERVICE_COMPLETED_WITH_ERRORS,    /* the chain completed but restore / transport / uncertainty not clean */
    GBP_AVSVC_NO_INITIAL_CAUSE,
    GBP_AVSVC_FIRST_DELIVERY_TIMEOUT,
    GBP_AVSVC_ABORT_STAGE_A,                    /* status_name = the 003A status name */
    GBP_AVSVC_ABORT_HANDLER_INSTALL,
    GBP_AVSVC_ABORT_PRE_UNMASK_STATE,
    GBP_AVSVC_ABORT_UNMASK,
    GBP_AVSVC_ABORT_BULK_UNAVAILABLE,           /* the transport has no whole-block read (host only) */
    GBP_AVSVC_ABORT_PRESVC_STATE,               /* PRESVC: no AV source / odd, bit 15 or high bits set */
    GBP_AVSVC_ABORT_READ_INCONSISTENT,          /* Disc reading != GBI reading at a service read */
    GBP_AVSVC_ABORT_TRANSPORT,                  /* a snapshot read failed */
    GBP_AVSVC_ACK_WRITE_FAILED,
    GBP_AVSVC_REARM_WRITE_FAILED,
    GBP_AVSVC_AUDIO_DMA_BUSY,
    GBP_AVSVC_AUDIO_DMA_TIMEOUT,
    GBP_AVSVC_AUDIO_DMA_ERROR,
    GBP_AVSVC_VIDEO_DMA_BUSY,
    GBP_AVSVC_VIDEO_DMA_TIMEOUT,
    GBP_AVSVC_VIDEO_DMA_ERROR,
    GBP_AVSVC_ANOMALY_REENTRY,
    GBP_AVSVC_ANOMALY_MASK_FAILURE,
    GBP_AVSVC_ANOMALY_UNEXPECTED_SOURCE,
    GBP_AVSVC_ANOMALY_CONTROL_CHANGED,
    GBP_AVSVC_ANOMALY_POSTACK_SHAPE,
    GBP_AVSVC_ANOMALY_PI_STICKY_AFTER_SERVICE,
    GBP_AVSVC_ANOMALY_REARM_STATE
} gbp_avsvc_status;

/* REARMPOST classification (as GBP-INIT-004, after a real drain). */
enum {
    GBP_AVSVC_REARMPOST_NONE = 0,
    GBP_AVSVC_REARMPOST_A_QUIET,            /* source 0, INTSR13 = 0: wait for the next cause */
    GBP_AVSVC_REARMPOST_B_LATCHED,          /* AV source != 0 and INTSR13 = 1: the next cause is already there */
    GBP_AVSVC_REARMPOST_C_SOURCE_BEFORE_PI, /* AV source != 0, INTSR13 = 0: keep observing within the bound */
    GBP_AVSVC_REARMPOST_D_UNEXPECTED,       /* a source outside AV */
    GBP_AVSVC_REARMPOST_E_INVALID,          /* odd / bit 15 / high bits set after IRQ := 0 */
    GBP_AVSVC_REARMPOST_F_INCONSISTENT      /* INTSR13 = 1 with no AV source visible */
};

struct gbp_avsvc_result {
    struct gbp_initirqa_result a;     /* the 003A stage: snapshots, writes, teardown flags, restore fields */
    gbp_avsvc_status status;
    const char *status_name;
    const char *status_class;         /* "ok", "observation", "errors", "abort", "transport", "dma", "anomaly" */
    const char *reason;
    char reason_buf[GBP_AVSVC_REASON_LEN];
    int stage_a_aborted;
    int restore_ok;
    const char *restore_reason;
    const char *teardown_variant;     /* "stage_a", "S2_before_unmask", "S3_service_aborted", "S3_dma_failed", "S4_ack_failed",
                                       * "S3_pi_sticky", "S4_rearm_failed", "S4C_rearmpost_invalid", "S4A_rearmed_no_next_cause",
                                       * "S4B_next_cause_latched" */
    struct gbp_irq_handler_state h;
    /* first cause and delivery */
    uint32_t t_cause;
    uint16_t cause_irq;
    struct gbp_initirqa_snapshot preunmask;
    int preunmask_ok;
    const char *preunmask_reason;
    struct gbp_irq_delivery d;
    int delivered;                    /* fired, single entry, main mask verified */
    /* service */
    struct gbp_initirqa_snapshot presvc;      /* the authoritative snapshot */
    int presvc_ok;
    const char *presvc_reason;
    uint16_t pending_irq;             /* PRESVC semantic value: block set and ACK value derive from it */
    uint16_t drain_mask;              /* pending_irq & av_mask */
    struct gbp_avblock audio, video;  /* AUDIO first, then VIDEO */
    unsigned drains_selected, drains_attempted, drains_completed;
    int drain_uncertain;              /* a block DMA was started and its completion not seen (timeout) */
    uint32_t t_service_end;           /* t_end of the last block read (0 when none) */
    struct gbp_initirqa_snapshot postdrain;   /* observation only: never changes pending_irq, the set or the ACK */
    int postdrain_ok;
    int relatch_postdrain;            /* INTSR bit 13 read 1 at POSTDRAIN (a cause latched during the drain) */
    /* acknowledge */
    struct gbp_irq_ack k;             /* ACK write, POSTACK, the single main W1C (gbp_irq_service) */
    int acked;
    int postack_ok;
    const char *postack_reason;
    uint16_t source_after_ack;        /* postack & av_mask: data, not a requirement */
    int relatch_postack;              /* INTSR bit 13 read 1 at POSTACK before the main W1C */
    int pi_clean;                     /* INTSR13 = 0 and INTMR13 = 0 confirmed before the re-arm */
    int pi_sticky;
    uint32_t pi_clean_intsr, pi_clean_intmr;
    /* re-arm */
    int rearm_attempted, rearm_completed;
    uint32_t t_rearm;
    uint16_t rearm_before;
    struct gbp_regwrite_result w_rearm;
    struct gbp_initirqa_snapshot rearmpost;
    int rearmpost_outcome;            /* GBP_AVSVC_REARMPOST_* */
    int rearmpost_ok;
    /* next cause (never delivered) */
    int next_cause_found, next_cause_immediate, next_cause_timed_out;
    unsigned next_cause_polls;
    uint32_t t_next_cause, dt_rearm_to_next_cause;
    uint16_t next_cause_irq;
    uint32_t next_cause_intsr;
    struct gbp_initirqa_snapshot nextcause;
    /* unexpected sources */
    uint16_t unexpected;
    const char *unexpected_site;      /* "PREUNMASK", "PRESVC", "POSTDRAIN", "POSTACK", "REARMPOST", "NEXTCAUSE" or "-" */
    /* counters (by control flow) */
    unsigned unmasks, deliveries, acks, isr_w1c, main_w1c, teardown_w1c;
    int control_ok;
    int pi_sticky_final;
    unsigned uncertain_writes;
    unsigned errors;
    int transport_ok;
    int power_cycle_required;
    /* timing, ticks (wrap-safe differences; 0 when not reached) */
    uint32_t dt_cause_to_isr, dt_isr_to_presvc, dt_presvc_to_ack, dt_service, dt_ack_to_postack, dt_postack_to_rearm;
};

/* Runs the experiment; always returns after the teardown. Returns 0 if it
 * completed (aborted or not), -1 only if AR_INFO could not be read. */
int gbp_avsvc_probe_run(const struct gbp_transport *t, struct ringlog *log,
                        const struct gbp_avsvc_config *cfg, struct gbp_avsvc_result *res);

int gbp_avsvc_summary(const struct gbp_avsvc_result *res, char *dst, size_t cap);
const char *gbp_avsvc_status_name(gbp_avsvc_status s);
const char *gbp_avsvc_status_class(gbp_avsvc_status s);
const char *gbp_avsvc_rearmpost_name(int outcome);

/* Fills the sidecar description from a result; the bytes are res->audio.buf /
 * res->video.buf. Absent blocks get length 0 (nothing uninitialized is
 * described). The four identities follow the sidecar rule (gbp_avdump.h):
 * a string that does not fit is never truncated — identity_error is set and
 * the serializer refuses the file. Returns 0 when every identity fits. */
int gbp_avsvc_dump_info(const struct gbp_avsvc_result *res, uint32_t tb_hz, const char *test_id,
                        const char *build_id, const char *app, const char *commit, struct gbp_avdump_info *info);

#ifdef __cplusplus
}
#endif
#endif
