/*
 * gbp_vstate_probe.h — GBP-VIDEO-002: a long-duration VIDEO state scan under
 * the repeated drained service of the Game Boy Player HSP interrupt.
 *
 * Normative description: docs/research/HARDWARE_TESTS.md "GBP-VIDEO-002"
 * (designed and hardened four times on 2026-09-16), docs/research/VIDEO_PATH.md
 * §9, docs/protocol/INITIALIZATION.md §14, U-GBP-030 / U-GBP-031.
 *
 * Question: over an observation at least as long as the nominal interval the
 * Start-up Disc's own detector spans, in a session WITHOUT a Game Pak, does
 * the VIDEO stream ever carry a frame other than the uniform one — and if so
 * when, for how long and with what content?
 *
 * WHAT IS REUSED, UNCHANGED, FROM GBP-VIDEO-001 (physically executed
 * 2026-09-16): the 003A programming sequence verbatim
 * (gbp_initirqa_run_cause), the 003B extended one-shot handler installed
 * ONCE (hsp_backend_oneshot_isr_ext, byte-identical body), the memory-only
 * record reset between deliveries (irq_record_reset), the quiet delivery
 * (gbp_irq_service_deliver_quiet), the whole-block drains (gbp_avblock),
 * the ACK `pending | 0x8000`, the PI cleanup budget, the re-arm `IRQ := 0`,
 * the masked WAIT_NEXT and the 003A teardown with the handler-restore hook.
 * The repeated IRQ service is NOT redesigned. Every property that run
 * validated stays a requirement.
 *
 * WHAT IS NEW: the observation is long. That forces four changes and no
 * others.
 *   1. A 64-BIT TIME BASE. 2^32 ticks = 106.049 s at 40.5 MHz, shorter than
 *      the 120 s target, so every persistent timestamp comes from the
 *      transport's ticks64 operation. The bounded per-operation waits keep
 *      the 32-bit one, where a wrap-safe difference is exact.
 *   2. PER-FRAME EVIDENCE INSTEAD OF PER-DELIVERY RECORDS. About 639 000
 *      deliveries are expected; a record each is impossible. The evidence is
 *      one 40-signature vector per observed frame, plus a bounded event
 *      store, plus detailed cycle records only for the first eight cycles,
 *      the last eight, anomalies and the cycles inside a preserved episode.
 *   3. STATE DETECTION WITHOUT AN ORACLE. A learned baseline, then an
 *      episode state machine over signature changes. The runtime holds no
 *      reference table, checksum, pixel or block range; every comparison
 *      with the Start-up Disc's frame and GBI's tables is offline.
 *   4. THE TEARDOWN RUNS FIRST. GBP-VIDEO-001 summarised before tearing
 *      down and put 64.99 ms between the last observation and the CONTROL
 *      restore. Here: stop condition -> minimal RAM snapshot -> HARDWARE
 *      TEARDOWN -> only then summaries, checksums, formatting and the save.
 *
 * STOP CONDITION, in strict precedence, evaluated once per admitted cycle at
 * the admission point and never inside an accepted transaction:
 *   1 fatal service error            -> failure
 *   2 HARD_WALLCLOCK_LIMIT expired   -> safety_budget  (wins over an open
 *                                       episode and over the tail; a cap that
 *                                       could be extended would not be hard)
 *   3 frame store full / event store full -> frame_store_cap / event_store_cap
 *   4 baseline_valid and valid_observation_elapsed >= MIN_VALID_OBSERVATION
 *        no episode open -> nominal_negative
 *        episode open    -> the bounded finalisation tail, then nominal_negative
 *   5 no next cause within T_NEXT_CAUSE   -> no_next_cause
 *   6 delivery guard reached              -> delivery_cap
 * There is NO early positive stop: the runtime cannot know which stable
 * changed state is the one the experiment was built for, so it observes the
 * whole window and records every episode for offline classification.
 *
 * THE EPISODE RAW STORE FILLING IS NOT A STOP. It sets episode_store_full,
 * counts episodes_not_preserved and keeps the signature monitor running.
 *
 * Not a runtime: no framebuffer, no conversion, no rendering, no GX, no
 * audio output, no KEYPAD, no SIO, no Link Port, no BBA, no Mobile Adapter,
 * no Game Pak logic, no callbacks, no unbounded loop, no malloc, and no
 * filesystem access anywhere between the first experimental write and the
 * completed teardown.
 */
#ifndef OPENGBP_GBP_VSTATE_PROBE_H
#define OPENGBP_GBP_VSTATE_PROBE_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_initirqa_probe.h"
#include "gbp_irq_service.h"
#include "gbp_avblock.h"
#include "gbp_vstate.h"
#include "gbp_vcolor.h"
#include "gbp_vqueue.h"
#include "gbp_vwitness.h"
#include "gbp_time64.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_VSTATE_REASON_LEN 64

/* ---- the design's own constants (§19); none is a property of the device ---- */
#define GBP_VSTATE_MIN_VALID_OBSERVATION_SECONDS 120u
#define GBP_VSTATE_HARD_WALLCLOCK_LIMIT_SECONDS  180u
/* 180 x 40 500 000. It does NOT fit in 32 bits — an independent confirmation
 * that the u64 time base is mandatory rather than tidy. */
#define GBP_VSTATE_HARD_WALLCLOCK_LIMIT_TICKS_U64 UINT64_C(7290000000)
/* §V5.59 (F5). A caller whose experiment has a DIFFERENT scientific stop -- the
 * indexed stream stops on the witness target -- disarms the generic
 * baseline/valid-observation success (`S5_target`, STOP_NOMINAL_NEGATIVE) by
 * installing these two values with gbp_vstate_config_disable_time_target(). No
 * 64-bit tick count reaches DISABLED_TICKS, so that stop can never fire; the
 * seconds value 0 is what the VSTATE/CLOCKSEC lines then report as target_s,
 * which reads as "no time target". The safety cap (hard_wallclock_*) is a
 * different thing and is untouched: it remains the run's only time-based stop,
 * and it is a SAFETY stop, never a success. Install them AFTER
 * gbp_vstate_config_timebase(), which recomputes the ticks from the seconds. */
#define GBP_VSTATE_MIN_VALID_OBSERVATION_DISABLED_S     0u
#define GBP_VSTATE_MIN_VALID_OBSERVATION_DISABLED_TICKS UINT64_MAX
/* The delivery guard of the design (section 19). It is a GUARD, not a scientific bound, and the
 * real margin is a factor, not orders of magnitude: GBP-VIDEO-001 measured 5 327 deliveries/s, so
 * the 120 s target implies ~639 000 and the 180 s hard safety envelope ~959 000 — this guard sits
 * 3.13x and 2.08x above those. It binds only if the physical delivery rate turns out above
 * ~11 111/s, and when it binds the run ends normally as `delivery_cap` with every capture kept,
 * never as a failure. (What DOES have three orders of magnitude of margin is the u32 type itself:
 * 4.29e9 / 639 000 = 6 721x. That is the design's sentence about widths, not about this cap.) */
#define GBP_VSTATE_MAX_DELIVERIES   2000000u
#define GBP_VSTATE_T_DELIVERY_MS    100u
#define GBP_VSTATE_T_NEXT_CAUSE_MS  100u
#define GBP_VSTATE_T_DMA_MS         200u
#define GBP_VSTATE_VERIFY_CYCLES    4u
#define GBP_VSTATE_VIDEO_SRC        0x0100u
#define GBP_VSTATE_AUDIO_SRC        0x0400u
/* The pre-handler wait can never be unbounded: the loop exits on the time base
 * OR on this many iterations, whichever comes first. A transport whose 64-bit
 * clock never advances therefore cannot hang the probe. */
#define GBP_VSTATE_PREHANDLER_WAIT_MAX_ITERS  200000000u
#define GBP_VSTATE_VIDEO_INDEX      1u
#define GBP_VSTATE_AUDIO_INDEX      8u

/* Bounded detailed cycle records (§15): never one per delivery. */
#define GBP_VSTATE_CYC_FIRST    8u
#define GBP_VSTATE_CYC_LAST     8u
#define GBP_VSTATE_CYC_ANOMALY  8u
#define GBP_VSTATE_CYC_EPISODE  64u
#define GBP_VSTATE_CYC_REC      128u   /* bytes of one cycle record, in RAM and in the sidecar */

enum gbp_vstate_cycle_kind {
    GBP_VSTATE_CYC_KIND_FIRST = 0,
    GBP_VSTATE_CYC_KIND_LAST = 1,
    GBP_VSTATE_CYC_KIND_ANOMALY = 2,
    GBP_VSTATE_CYC_KIND_EPISODE = 3
};

/* Exactly 128 bytes, checked at compile time. */
struct gbp_vstate_cycle {
    uint64_t t_cause;        /* 0x00 */
    uint64_t t_unmask;       /* 0x08 */
    uint64_t t_entry;        /* 0x10 */
    uint64_t t_read;         /* 0x18 */
    uint64_t t_ack;          /* 0x20 */
    uint64_t t_rearm;        /* 0x28 */
    uint64_t t_next;         /* 0x30 */
    uint32_t index;          /* 0x38 delivery ordinal */
    uint32_t frame_index;    /* 0x3C frame being assembled when the cycle ran */
    uint16_t pending;        /* 0x40 */
    uint16_t ack_value;      /* 0x42 */
    uint16_t kind;           /* 0x44 enum gbp_vstate_cycle_kind */
    uint16_t flags;          /* 0x46 */
    uint8_t audio_selected, audio_completed, video_selected, video_completed;   /* 0x48 */
    uint8_t main_w1c, isr_count, isr_reentry, next_observed;                    /* 0x4C */
    uint32_t latency_ticks;  /* 0x50 */
    uint32_t audio_wait;     /* 0x54 */
    uint32_t video_wait;     /* 0x58 */
    uint32_t sig_ticks;      /* 0x5C the signature cost measured for this cycle's VIDEO block */
    uint32_t intsr_entry;    /* 0x60 */
    uint32_t intsr_after_w1c;/* 0x64 */
    uint32_t intsr_postack;  /* 0x68 */
    uint32_t intsr_next;     /* 0x6C */
    uint32_t block_in_frame; /* 0x70 */
    uint32_t rc;             /* 0x74 packed statuses: audio | video << 8 | ack << 16 | rearm << 24 */
    uint32_t reserved[2];    /* 0x78 zero */
};

/* ---- stop reasons and statuses (§19/§20) ---- */
enum gbp_vstate_stop {
    GBP_VSTATE_STOP_NONE = 0,
    GBP_VSTATE_STOP_NOMINAL_NEGATIVE,
    GBP_VSTATE_STOP_FRAME_STORE_CAP,
    GBP_VSTATE_STOP_EVENT_STORE_CAP,
    GBP_VSTATE_STOP_SAFETY_BUDGET,
    GBP_VSTATE_STOP_DELIVERY_CAP,
    GBP_VSTATE_STOP_NO_NEXT_CAUSE,
    GBP_VSTATE_STOP_FAILURE,
    /* GBP-VIDEO-003 only. Never reachable with cfg->color == NULL. */
    GBP_VSTATE_STOP_COLOR_CERTIFIED,     /* three signature-identical eligible frames */
    GBP_VSTATE_STOP_COLOR_SEARCH_WINDOW, /* the search window expired with nothing certified */
    GBP_VSTATE_STOP_COLOR_FRAME_CAP,     /* the capture's frame table filled first */
    /* ---- GBP-VIDEO-004 indexed retention (§V5.39.3) ----
     * The indexed run is bounded by a COUNT, not by a clock: `stream-0004`
     * physically disproved the sizing premise the experiment was designed
     * around (GBP-HW-151). These two are NOT interchangeable and never get
     * folded into one reason:
     *   WITNESS_TARGET      the target record was committed. NORMAL.
     *   WITNESS_STORE_FULL  a commit was refused for lack of room. The run was
     *                       not supposed to reach this, so the analyzer refuses
     *                       a decisive verdict. Overflow is never a normal stop. */
    GBP_VSTATE_STOP_WITNESS_TARGET,
    GBP_VSTATE_STOP_WITNESS_STORE_FULL
};

typedef enum {
    /* the three outcomes of a run whose service stayed ok */
    GBP_VSTATE_OK_STRUCTURED_CHANGE_OBSERVED = 0,
    GBP_VSTATE_OK_NO_CHANGE_NOMINAL_INTERVAL,
    GBP_VSTATE_OK_NO_CHANGE_INCONCLUSIVE,
    GBP_VSTATE_OBSERVATION_NO_NEXT_CAUSE,
    GBP_VSTATE_CAPTURE_COMPLETED_WITH_ERRORS,
    /* the GBP-VIDEO-001 failure statuses, unchanged in meaning */
    GBP_VSTATE_NO_INITIAL_CAUSE,
    GBP_VSTATE_FIRST_DELIVERY_TIMEOUT,
    GBP_VSTATE_ABORT_STAGE_A,
    GBP_VSTATE_ABORT_HANDLER_INSTALL,
    GBP_VSTATE_ABORT_PRE_UNMASK_STATE,
    GBP_VSTATE_ABORT_UNMASK,
    GBP_VSTATE_ABORT_BULK_UNAVAILABLE,
    GBP_VSTATE_ABORT_RESET_UNAVAILABLE,
    GBP_VSTATE_ABORT_TIME64_UNAVAILABLE,
    GBP_VSTATE_ABORT_STORE_UNAVAILABLE,
    GBP_VSTATE_ABORT_PRESVC_STATE,
    GBP_VSTATE_ABORT_READ_INCONSISTENT,
    GBP_VSTATE_ABORT_TRANSPORT,
    GBP_VSTATE_ABORT_CAPACITY,
    GBP_VSTATE_ACK_WRITE_FAILED,
    GBP_VSTATE_REARM_WRITE_FAILED,
    GBP_VSTATE_AUDIO_DMA_BUSY,
    GBP_VSTATE_AUDIO_DMA_TIMEOUT,
    GBP_VSTATE_AUDIO_DMA_ERROR,
    GBP_VSTATE_VIDEO_DMA_BUSY,
    GBP_VSTATE_VIDEO_DMA_TIMEOUT,
    GBP_VSTATE_VIDEO_DMA_ERROR,
    GBP_VSTATE_ANOMALY_REENTRY,
    GBP_VSTATE_ANOMALY_MISSED_ENTRY,
    GBP_VSTATE_ANOMALY_ISR_STATE,
    GBP_VSTATE_ANOMALY_RECORD_NOT_CLEAR,
    GBP_VSTATE_ANOMALY_MASK_FAILURE,
    GBP_VSTATE_ANOMALY_UNEXPECTED_SOURCE,
    GBP_VSTATE_ANOMALY_CAUSE_WITHOUT_SOURCE,
    GBP_VSTATE_ANOMALY_CONTROL_CHANGED,
    GBP_VSTATE_ANOMALY_POSTACK_SHAPE,
    GBP_VSTATE_ANOMALY_PI_STICKY,
    GBP_VSTATE_ANOMALY_REARM_STATE
} gbp_vstate_status;

struct gbp_vstate_config {
    struct gbp_initirqa_config a;        /* the 003A stage, verbatim */
    uint32_t t_delivery_ms, t_delivery_ticks;
    uint32_t t_next_cause_ms, t_next_cause_ticks;
    uint32_t max_deliveries;             /* the u32 guard, not a scientific bound */
    uint32_t verify_cycles;
    uint32_t min_valid_observation_s;    /* 120 */
    uint32_t hard_wallclock_s;           /* 180 */
    uint64_t min_valid_observation_ticks;
    uint64_t hard_wallclock_ticks;
    uint16_t ack_or, src_mask, av_mask, audio_src, video_src, odd_mask, bit15_mask, high_mask;
    uint32_t audio_index, video_index, audio_len, video_len;
    struct gbp_vstate *st;               /* caller's state model and storage */
    /* ---- GBP-VIDEO-003 capture mode (HARDWARE_TESTS §V3) ----
     * NULL in every GBP-VIDEO-002 build, and then this probe behaves exactly as
     * it did when vstate-0004 was physically validated: the device operations,
     * their order, the policy and the stop conditions are untouched. When the
     * colour POC supplies a state here, ONE extra thing happens per closed frame
     * (a RAM-only eligibility test and, at most, a memcpy of the frame's own
     * bytes) and TWO extra stop conditions are evaluated in CHECK_ADMISSION,
     * after the safety budget. No hardware access is added anywhere (§V3.13). */
    struct gbp_vcolor *color;
    uint64_t color_search_ticks;         /* SEARCH_WINDOW: certification must start by then */
    /* ---- GBP-VIDEO-004 streaming mode (HARDWARE_TESTS §V5) ----
     * NULL in every earlier build, and then this field does not exist as far as
     * the device is concerned. When the streaming POC supplies a queue here, ONE
     * extra thing happens per CLOSED frame, and it is the same shape the colour
     * capture was reduced to by the §V3.23 microaudit: a classification of
     * integers and a small descriptor write. No frame byte is read, no pointer
     * into the ring is formed, no clock is read, no device is touched, and the
     * call can never block — a consumer that has fallen behind loses a frame,
     * it does not stall the service (§V5.7, §V5.14). */
    struct gbp_vqueue *stream;
    /* ---- GBP-VIDEO-004 OGBPIDX1 witness retention (HARDWARE_TESTS §V5.39) ----
     * NULL in every earlier build, and then this field does not exist as far as
     * the device is concerned. When the indexed POC supplies a store here, ONE
     * extra thing happens per received VIDEO block — 54 consumed-word
     * extractions and a 108-byte placement, both in RAM, both measured — and
     * ONE extra thing per closed frame: the scratch becomes a record. It runs
     * in the SOURCE-CAPTURE layer, ahead of the publish, so a frame the
     * consumer never sees is preserved anyway; retaining only published frames
     * would make the population a function of consumer eligibility, which is
     * exactly the bias that would make a source-continuity claim worthless
     * (§V5.39.4). No device access, no filesystem, no allocation is added. */
    struct gbp_vwitness *witness;
    /* ---- PRE-HANDLER MASKED WAIT: a DIAGNOSTIC, and nothing else ----
     * 0 in every ordinary build, and then this field does not exist as far as
     * the device is concerned: no wait, no extra read, no log line, the same
     * operation stream vstate-0004 executed.
     *
     * Non-zero inserts a bounded wait in ONE place - after stage A has put
     * CONTROL in the running shape and BEFORE the 003B handler is installed -
     * to answer one question and no other (HARDWARE_TESTS, the pre-handler wait
     * diagnostic): does the Game Boy Player tolerate several seconds there, with
     * PI still masked, and then service normally?
     *
     * That position is not arbitrary: it is exactly where a future operator
     * ARMING step would have to sit, because it is the only point at which the
     * AGB is already running and no service transaction is in flight. Nothing
     * here reads the controller, and nothing here belongs to GBP-VIDEO-003. */
    uint32_t prehandler_wait_ms;
    struct gbp_vstate_cycle *cyc_first, *cyc_last, *cyc_anomaly, *cyc_episode;   /* caller's bounded records */
    /* BENCHMARK ONLY. Section 8 of the design requires the same synthetic scenario to be run WITH
     * and WITHOUT the per-block signature so the cadence can be compared. This flag is how the
     * "without" half is produced; it exists for that measurement and nothing else. The POC never
     * sets it (gbp_vstate_config_default leaves it 0), the audit profile checks that main.o does
     * not reference it, and a run with it set produces NO signatures, NO frames and therefore no
     * scientific result at all. */
    int bench_skip_signature;
};

/* §V5.59 (F5): see GBP_VSTATE_MIN_VALID_OBSERVATION_DISABLED_TICKS. */
static inline void gbp_vstate_config_disable_time_target(struct gbp_vstate_config *cfg)
{
    cfg->min_valid_observation_s = GBP_VSTATE_MIN_VALID_OBSERVATION_DISABLED_S;
    cfg->min_valid_observation_ticks = GBP_VSTATE_MIN_VALID_OBSERVATION_DISABLED_TICKS;
}

static inline int gbp_vstate_config_time_target_disabled(const struct gbp_vstate_config *cfg)
{
    return cfg->min_valid_observation_ticks == GBP_VSTATE_MIN_VALID_OBSERVATION_DISABLED_TICKS;
}

void gbp_vstate_config_default(struct gbp_vstate_config *cfg);
void gbp_vstate_config_timebase(struct gbp_vstate_config *cfg, uint32_t tb_hz);

struct gbp_vstate_result {
    struct gbp_initirqa_result a;
    gbp_vstate_status status;
    const char *status_name, *status_class, *reason;
    char reason_buf[GBP_VSTATE_REASON_LEN];
    int stage_a_aborted;
    int restore_ok;
    const char *restore_reason, *teardown_variant;
    struct gbp_irq_handler_state h;
    struct gbp_vstate *st;

    /* ---- the result matrix (§20) ---- */
    int service_ok;
    const char *service_reason;
    /* The caps this run actually used. The summary printed them from the build's
     * constants until GBP-VIDEO-003 arrived with different ones; a report that
     * names a limit the run did not use is a report that cannot be checked. */
    uint32_t target_s, limit_s;
    int stop;                            /* enum gbp_vstate_stop */
    const char *stop_name;
    int next_cause_at_end;

    /* ---- the three clocks, all u64 (§6b) ---- */
    uint64_t t_control_transform;        /* the safety epoch: the CONTROL 0x90 -> 0x8C write */
    /* How that epoch was obtained. The stage records the CONTROL write on the 32-bit time base, so
     * the u64 value is reconstructed and then CHECKED against a bracket of two real u64 reads taken
     * around the stage — it is never simply trusted.
     *    1  reconstructed and inside the bracket
     *    0  the reconstruction fell outside the bracket, so the epoch was clamped to the earlier
     *       bracket end: EARLIER than the true write, which makes safety_elapsed larger and the
     *       hard cap fire sooner. Conservative by construction, never a time in the future.
     *   -1  no experimental CONTROL write was made at all (the stage aborted before it): there is
     *       no experiment epoch, and none is invented. */
    int epoch_ok;
    uint64_t t_capture_start;            /* the first admitted unmask */
    uint64_t t_stop, t_teardown_begin, t_teardown_end;
    uint64_t capture_elapsed;            /* capture_start -> stop */
    uint64_t baseline_elapsed;           /* capture_start -> baseline_valid */
    uint64_t valid_observation_elapsed;  /* the ONLY quantity the negative result uses */
    uint64_t valid_observation_at_target;/* its value when the target fired */
    uint64_t safety_elapsed;             /* t_control_transform -> stop */
    uint32_t tb_hz;

    /* ---- counters, u32 with explicit overflow guards (§14) ---- */
    uint32_t deliveries, unmasks, acks, rearms, isr_w1c, main_w1c, teardown_w1c;
    uint32_t audio_drains, video_drains, video_completed;
    uint32_t verify_cycles_done, lean_cycles;
    uint64_t bytes_video, bytes_audio;
    uint32_t counter_overflow;           /* non-zero ends the run rather than wrapping */
    uint32_t uncertain_writes, errors;
    /* semantic coherence is an INDEPENDENT dimension of the result (§R3.17): a
     * run that saw source-serviced disagreements and handled them is not a
     * service failure. */
    uint32_t semantic_disagreements;     /* every disagreement, preserved or not */
    uint16_t last_majority_extra;        /* sources the majority had and the Disc did not,
                                          * for THIS cycle; 0 in every ordinary cycle */
    uint16_t last_disc_extra;            /* the mirror: sources the majority omitted */
    int semantic_failed;                 /* a NON_SOURCE or SOURCE_OTHER ended the run */
    uint16_t unexpected;
    const char *unexpected_site;
    uint32_t unexpected_cycle;
    int control_ok, pi_sticky_final, transport_ok, power_cycle_required;

    /* bounded cycle records actually filled */
    uint32_t cyc_first_n, cyc_last_n, cyc_anomaly_n, cyc_episode_n, cyc_last_next;

    /* ---- first cause / install / preunmask ---- */
    uint32_t t_cause32;
    uint16_t cause_irq;
    struct gbp_initirqa_snapshot preunmask;
    /* The pre-handler wait diagnostic. All zero when prehandler_wait_ms is 0,
     * and the two snapshots are then never taken. These live in RAM and in the
     * text log only: OGBPSEQ1 v5 is FROZEN and carries none of them. */
    uint32_t prehandler_wait_ms;         /* what was configured */
    uint32_t prehandler_wait_iters;      /* loop iterations actually spent */
    int prehandler_wait_done;            /* 1 = the bound was reached, 0 = skipped, -1 = iteration cap hit */
    uint64_t t_prehandler_wait_begin, t_prehandler_wait_end;
    struct gbp_initirqa_snapshot waitpre, waitpost;   /* read-only state either side of the wait */
    int preunmask_ok;
    const char *preunmask_reason;

    /* ---- per-cycle scratch ---- */
    struct gbp_irq_delivery d;
    struct gbp_irq_ack k;
    struct gbp_avblock audio, video;
    struct gbp_initirqa_snapshot presvc, postdrain, rearmpost;
    struct gbp_regwrite_result w_ack, w_rearm;
    char id_presvc[32], id_postdrain[32], id_postack[32], id_rearmpost[32], tag_ack[32], tag_rearm[32], nfield[24], sfx[20];

    /* ---- save_result, kept completely apart from the hardware result (§18/§26) ---- */
    int save_attempted;
    int save_log_ok, save_sidecar_ok;
    const char *save_reason;
    uint32_t save_sections_written;
    uint64_t save_bytes;
};

/* Runs the experiment; always returns after the teardown. Returns 0 when it
 * completed (aborted or not), -1 only if AR_INFO could not be read. */
int gbp_vstate_probe_run(const struct gbp_transport *t, struct ringlog *log,
                         const struct gbp_vstate_config *cfg, struct gbp_vstate_result *res);

/* Everything that is NOT allowed before the teardown: summaries, boundary
 * lists and the textual records. The probe calls this itself, after the
 * hardware teardown has completed; it is exposed so a test can assert the
 * ordering directly. */
void gbp_vstate_report(struct ringlog *log, const struct gbp_vstate_config *cfg, struct gbp_vstate_result *res);

int gbp_vstate_summary(const struct gbp_vstate_result *res, char *dst, size_t cap);
const char *gbp_vstate_status_name(gbp_vstate_status s);
const char *gbp_vstate_status_class(gbp_vstate_status s);
const char *gbp_vstate_stop_name(int stop);
/* The main status derived from the matrix, exactly as §20 defines it. */
gbp_vstate_status gbp_vstate_main_status(const struct gbp_vstate_result *res);

#ifdef __cplusplus
}
#endif
#endif
