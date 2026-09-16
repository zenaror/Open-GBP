/*
 * gbp_initirqa_probe.h — GBP-INIT-003A: GBP IRQ-register programming with
 * the PI HSP interrupt masked throughout.
 *
 * Normative description: docs/research/HARDWARE_TESTS.md (planned tests,
 * GBP-INIT-003A), docs/research/DEVLOG.md 2026-09-15 ("GBP-INIT-003A
 * design consolidated"), docs/protocol/INITIALIZATION.md §9–§10.
 *
 * Questions: A1 — with PI HSP masked, what does `IRQ := irq_read | 0x8000`
 * (GBI's acknowledge, the u16 replicated 16×) change in the read-back?
 * A2 — after that acknowledge, what does `IRQ := 0` (GBI's end-of-pass
 * write, 32 × 00) change, and does a source that becomes visible
 * afterwards raise INTSR bit 13 while delivery to the CPU stays masked?
 * The two experimental writes are literally the values of GBI's first
 * loop pass (GBP-IRQ-004), an independent mature implementation; the
 * stop word is the Nintendo Start-up Disc's (GBP-IRQ-002/006), the
 * official reference. Neither reference reads the register back between
 * its writes, which is why this has to be observed on hardware.
 *
 * Protection: PI HSP (interrupt 26) is never unmasked — no handler is
 * installed, no __UnmaskIrq/__MaskIrq is called, INTMR is only read.
 * INTMR bit 13 == 1 or INTSR bit 13 == 1 at the start aborts (never
 * adjusted). An INTSR bit 13 that rises inside the window is observed
 * only (no write-1-to-clear there); the teardown performs at most one.
 *
 * Sequence (order checked by the host mock and by the log tests):
 *   AR_INFO[5:3] := 3 → presence gate (PRESENT only) → PI precondition
 *   (INTSR13 == 0, INTMR13 == 0) → BASE (PI, CONTROL, IRQ, TEST) →
 *   CONTROL shape ((v & 0x10) != 0, (v & 0x0C) == 0, vote == byte 0x1F)
 *   → IRQ shape ((v & 0x0AAA) == 0x0AAA, (v & 0x8000) != 0, (v & 0x7000)
 *   == 0, Disc reading == GBI reading; even source bits may vary) →
 *   CONTROL := (v & ~0x10) | 0x0C (GBI layout) → P0 (INTMR13 re-check)
 *   → A1PRE: IRQ read (shape re-check) → A1: IRQ := read | 0x8000 →
 *   A1-0, A1-50US, A1-500US → A2PRE: IRQ read + PI (INTMR13 re-check) →
 *   A2: IRQ := 0 → A2-0, A2-50US … A2-2000MS with INTSR polling, EVENT
 *   snapshot at the first INTSR13 == 1 (window may end early) →
 *   teardown: CONTROL := v → IRQ read → IRQ := read | 0x8AAA (Start-up
 *   Disc stop shadow: bit 15 + the odd mask bits of the six serviced
 *   slots) → IRQ read → PI → one INTSR := 0x2000 only if bit 13 is set
 *   → AR_INFO back → FINAL. Writing the BASE raw block back is NOT a
 *   restore and is never done (DEVLOG 2026-09-15).
 *
 * Experimental region (A1PRE read … end of the A2 window): reads and
 * writes are captured into structures; nothing is formatted or logged
 * until the window has ended (log_count_window_start == _end proves it).
 * Deadlines are time-base distances (operational bounds, not properties
 * of the Game Boy Player); every outcome is a valid observation.
 *
 * Writes (complete list): AR_INFO bits 3–5 (restored), TEST (handshake),
 * CONTROL (transform, restore), IRQ register (A1, A2, stop — the only
 * three call sites of gbp_regwrite_irq_u16 in this object), PI INTSR
 * W1C 0x2000 at most once in the teardown. Never: INTMR, KEYPAD, VIDEO,
 * AUDIO, SIOCTL, SIODATA, BBA. Byte 0 of any block never feeds a
 * decision. A console power cycle is mandatory after any run that
 * attempted a CONTROL or IRQ write (power_cycle_required).
 */
#ifndef OPENGBP_GBP_INITIRQA_PROBE_H
#define OPENGBP_GBP_INITIRQA_PROBE_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_transport.h"
#include "gbp_detect.h"
#include "gbp_regwrite.h"
#include "../log/ringlog.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_INITIRQA_MAX_A1_OBS 2
#define GBP_INITIRQA_MAX_A2_OBS 6
#define GBP_INITIRQA_ID_LEN 16   /* "A1-4294967295US" + NUL */

/* Snapshot slots (fixed); the A2 window is logged in temporal order via a2_order[]. */
enum {
    GBP_INITIRQA_SNAP_BASE = 0,
    GBP_INITIRQA_SNAP_P0,
    GBP_INITIRQA_SNAP_A1_0,
    GBP_INITIRQA_SNAP_A1_OBS,                                                     /* + k */
    GBP_INITIRQA_SNAP_A2_0 = GBP_INITIRQA_SNAP_A1_OBS + GBP_INITIRQA_MAX_A1_OBS,
    GBP_INITIRQA_SNAP_A2_OBS,                                                     /* + k */
    GBP_INITIRQA_SNAP_EVENT = GBP_INITIRQA_SNAP_A2_OBS + GBP_INITIRQA_MAX_A2_OBS,
    GBP_INITIRQA_SNAP_FINAL,
    GBP_INITIRQA_SNAPSHOTS
};

struct gbp_initirqa_config {
    uint8_t patterns[4];
    unsigned npatterns;
    unsigned expansion_code;      /* AR_INFO bits 3-5 during the experiment (3) */
    uint8_t clear_mask;           /* 0x10 */
    uint8_t set_mask;             /* 0x0C */
    int require_idle_shape;       /* CONTROL precondition (always 1 for this experiment) */
    uint16_t irq_req_masks;       /* 0x0AAA: odd mask bits that must read 1 */
    uint16_t irq_req_set;         /* 0x8000: must read 1 */
    uint16_t irq_req_clear;       /* 0x7000: must read 0 */
    uint16_t ack_or;              /* 0x8000: A1 = read | ack_or */
    uint16_t stop_or;             /* 0x8AAA: stop = read | stop_or */
    uint32_t tb_hz;               /* ticks per second (µs conversion; 0 = unknown) */
    uint32_t a1_obs_us[GBP_INITIRQA_MAX_A1_OBS];
    uint32_t a1_obs_ticks[GBP_INITIRQA_MAX_A1_OBS];
    char a1_obs_id[GBP_INITIRQA_MAX_A1_OBS][GBP_INITIRQA_ID_LEN];
    unsigned n_a1_obs;
    uint32_t a2_obs_us[GBP_INITIRQA_MAX_A2_OBS];
    uint32_t a2_obs_ticks[GBP_INITIRQA_MAX_A2_OBS];
    char a2_obs_id[GBP_INITIRQA_MAX_A2_OBS][GBP_INITIRQA_ID_LEN];
    unsigned n_a2_obs;
    uint32_t t_max_ms;            /* the last A2 deadline in ms (log only) */
    int poll_between;             /* 1: poll INTSR inside the deadline loops (counter only) */
    int end_window_on_event;      /* 1: after the EVENT snapshot the A2 window ends early */
};

/* Defaults: patterns C3/3C/FF/00, code 3, transform (v & ~0x10) | 0x0C,
 * IRQ shape 0x0AAA/0x8000/0x7000, ack 0x8000, stop 0x8AAA, A1 samples at
 * 50 µs and 500 µs, A2 samples at 50 µs, 500 µs, 5 ms, 50 ms, 500 ms and
 * 2000 ms, 40.5 MHz time base, polling on, early end on. */
void gbp_initirqa_config_default(struct gbp_initirqa_config *cfg);
/* Recomputes every *_ticks deadline (and the snapshot ids) from the µs tables for tb_hz. */
void gbp_initirqa_config_timebase(struct gbp_initirqa_config *cfg, uint32_t tb_hz);

struct gbp_initirqa_snapshot {
    const char *id;               /* "BASE", "P0", "A1-0", "A1-50US", …, "EVENT", "FINAL" */
    int taken;
    uint32_t ticks;
    uint32_t since_control;       /* ticks since the experimental CONTROL write (0 if before) */
    uint32_t since_a1;            /* ticks since the A1 write (0 if before) */
    uint32_t since_a2;            /* ticks since the A2 write (0 if before) */
    int pi_ok;
    gbp_status pi_rc;
    uint32_t intsr, intmr;
    int pi2_ok;                   /* second PI sample (only when requested) */
    uint32_t intsr2, intmr2;
    gbp_status control_rc, irq_rc, test_rc;
    struct gbp_xfer_info control_info, irq_info, test_info;
    int has_test;
    uint8_t control[GBP_BLOCK_SIZE];
    uint8_t irq[GBP_BLOCK_SIZE];
    uint8_t test[GBP_BLOCK_SIZE];
    uint8_t control_vote;         /* GBI semantic value */
    uint8_t control_b1f;          /* Start-up Disc semantic value (byte 0x1F) */
    uint16_t irq_disc;            /* bytes 0x1D/0x1F (Start-up Disc reading) */
    uint16_t irq_gbi;             /* GBI vote reading */
    unsigned polls_before;        /* INTSR polls of the phase performed before this snapshot */
    int is_event;                 /* EVENT: taken because a poll saw INTSR bit 13 */
    uint32_t poll_intsr;          /* EVENT: the polled value that triggered it */
};

/* One quiet IRQ-register read (raw kept, both readings). */
struct gbp_initirqa_irqread {
    int taken;
    gbp_status rc;
    struct gbp_xfer_info info;
    uint8_t raw[GBP_BLOCK_SIZE];
    uint16_t disc, gbi;
};

typedef enum {
    GBP_INITIRQA_OK_NO_PI_CAUSE_OBSERVED = 0, /* A1, A2 and the window ran; INTSR bit 13 stayed 0 */
    GBP_INITIRQA_OK_PI_CAUSE_OBSERVED,        /* A1, A2 and the window ran; INTSR bit 13 was seen set */
    GBP_INITIRQA_ABORT_ARINFO,                /* AR_INFO unreadable / not settable */
    GBP_INITIRQA_ABORT_NOT_PRESENT,           /* verdict ABSENT */
    GBP_INITIRQA_ABORT_INCONSISTENT,          /* verdict INCONSISTENT / NO_DATA */
    GBP_INITIRQA_ABORT_PI_PRECONDITION,       /* PI unreadable, INTMR bit 13 enabled (start, P0, A2PRE), INTSR bit 13 set at start */
    GBP_INITIRQA_ABORT_CONTROL_READ,          /* BASE unreadable or CONTROL ambiguous */
    GBP_INITIRQA_ABORT_CONTROL_SHAPE,         /* CONTROL not in the required idle shape */
    GBP_INITIRQA_ABORT_IRQ_SHAPE,             /* IRQ register not in the required shape (BASE or A1PRE) */
    GBP_INITIRQA_ABORT_TRANSPORT              /* a required transfer failed (CONTROL write, A1PRE, A1, A2PRE, A2, P0) */
} gbp_initirqa_status;

struct gbp_initirqa_result {
    gbp_initirqa_status status;
    const char *reason;
    int restore_ok;               /* 1 if every attempted restore step succeeded */
    const char *restore_reason;   /* first restore failure, or "-" */
    int power_cycle_required;     /* 1 once any experimental CONTROL or IRQ write was attempted */
    /* AR_INFO */
    int arinfo_changed;
    uint16_t arinfo_orig, arinfo_exp, arinfo_final;
    int arinfo_restore_ok;        /* 1 ok, 0 failed, -1 not attempted */
    /* detection */
    struct gbp_handshake_result det;
    uint32_t base;
    /* PI precondition */
    int pi_pre_ok;
    uint32_t intsr_pre, intmr_pre;
    /* CONTROL */
    uint8_t control_orig, control_exp;
    int control_written;          /* the experimental CONTROL write was attempted */
    struct gbp_regwrite_result w_ctl_exp, w_ctl_restore;
    gbp_status control_restore_read_rc;
    uint8_t control_restore_raw[GBP_BLOCK_SIZE];
    uint8_t control_restore_vote, control_restore_b1f;
    int control_restore_ok;       /* -1 not attempted, 1 write ok + readback vote == orig, 0 otherwise */
    /* IRQ shape */
    int irq_shape_base_ok, irq_shape_a1pre_ok;   /* -1 not evaluated */
    const char *irq_shape_reason;
    /* IRQ reads outside snapshots */
    struct gbp_initirqa_irqread irq_a1pre, irq_a2pre, irq_stop_pre, irq_stop_post;
    int a2pre_pi_ok;
    uint32_t a2pre_intsr, a2pre_intmr;
    /* IRQ writes */
    uint16_t ack_value, stop_value;
    struct gbp_regwrite_result w_a1, w_a2, w_stop;
    /* Probe-side safety counters (not the mock's device-side counters):
     * incremented BEFORE the transport is invoked / after rc == ok. */
    unsigned irq_writes_attempted, irq_writes_completed;
    unsigned uncertain_writes;    /* writes attempted whose completion was not reported (device state uncertain) */
    /* timing */
    uint32_t t_control, t_a1, t_a2, t_window_end;
    int no_timebase;              /* transport has no ticks(): deadline loops skipped */
    unsigned a1_polls, a2_polls, poll_errors;
    unsigned a1_obs_taken, a2_obs_taken;
    int intsr13_seen;             /* INTSR bit 13 observed set at any point after the CONTROL write (global, first sighting kept) */
    int a1_intsr13_seen;          /* INTSR bit 13 observed set during the A1 phase only (A1-0, its samples, its polls) */
    int a2_intsr13_seen;          /* INTSR bit 13 observed set during the A2 phase only (A2-0, samples, polls, EVENT) */
    uint32_t t_first_intsr13;
    const char *first_intsr13_phase;   /* "P0", "A1", "A1-0", "A2PRE", "A2", "A2-0", … or "-" */
    uint32_t first_intsr13_value;
    unsigned polls_at_first_intsr13;
    int event_taken;
    uint32_t t_event;
    int window_ended_early;
    /* teardown, best-effort fields kept separate */
    int irq_stop_write_ok;        /* -1 not attempted, 1 rc ok, 0 failed */
    int irq_stop_readback_ok;     /* -1 not attempted, 1 re-read rc ok, 0 failed */
    int stop_masks_readback;      /* -1 n/a, 1 the odd mask bits of stop_or read back set, 0 not (observation) */
    int stop_bit15_readback;      /* -1 n/a, else bit 15 of the re-read (observation) */
    int pi_cleanup_performed;     /* exactly one INTSR := 0x2000, only if bit 13 was set while masked */
    int pi_cleanup_ok;            /* -1 not performed, 1 W1C rc ok and bit 13 clear afterwards, 0 otherwise */
    int pi_cleanup_sticky;        /* 1 if bit 13 was still set after the single W1C */
    const char *pi_cleanup_skip_reason;
    uint32_t cleanup_intsr_before, cleanup_intmr_before, cleanup_intsr_after;
    gbp_status cleanup_rc;
    /* snapshots */
    struct gbp_initirqa_snapshot snap[GBP_INITIRQA_SNAPSHOTS];
    unsigned a2_order[GBP_INITIRQA_MAX_A2_OBS + 1];
    unsigned n_a2_order;
    /* proof that the experimental region logged nothing */
    size_t log_count_window_start, log_count_window_end;
    int window_entered;
    int window_flushed;           /* the window records were formatted (once) */
    unsigned errors;              /* transport failures */
    int transport_ok;
};

/* Runs the experiment; always returns after the teardown. Returns 0 if
 * it completed (aborted or not), -1 only if AR_INFO could not be read. */
int gbp_initirqa_probe_run(const struct gbp_transport *t, struct ringlog *log,
                           const struct gbp_initirqa_config *cfg, struct gbp_initirqa_result *res);

int gbp_initirqa_summary(const struct gbp_initirqa_result *res, char *dst, size_t cap);
const char *gbp_initirqa_status_name(gbp_initirqa_status s);

/* ---- stage API, for experiments built on this sequence (GBP-INIT-003B) ----
 * gbp_initirqa_probe_run() == gbp_initirqa_run_cause() followed, when the
 * window ran, by the standard finish (teardown + end records). */
typedef enum {
    GBP_INITIRQA_CAUSE_ABORTED = 0,    /* an abort path ran: teardown and end records already written (res->status) */
    GBP_INITIRQA_CAUSE_NOT_OBSERVED,   /* the A2 window ended without INTSR bit 13; window records flushed; no teardown yet */
    GBP_INITIRQA_CAUSE_OBSERVED        /* INTSR bit 13 observed (EVENT); window records flushed; no teardown yet */
} gbp_initirqa_cause_rc;

gbp_initirqa_cause_rc gbp_initirqa_run_cause(const struct gbp_transport *t, struct ringlog *log,
                                             const struct gbp_initirqa_config *cfg, struct gbp_initirqa_result *res);

struct gbp_initirqa_teardown_opts {
    int pi_cleanup_allowed;                 /* 0: CLEANUPCHK observes only (reason=budget_spent) */
    void (*pre_arinfo_hook)(void *ctx);     /* runs after the PI step, before the AR_INFO restore (NULL: none) */
    void *hook_ctx;
    const char *pi_policy;                  /* label of "TEARDOWN start … pi_policy="; NULL = "never_unmasked" (this
                                             * probe's own policy). A caller that unmasked PI HSP passes its real
                                             * policy: build initirqb-0001 printed "never_unmasked" in a run that had
                                             * unmasked once (physical log of 2026-09-15, label defect; DEVLOG). */
};

/* The teardown of §9 R7 as run by the probe (opts NULL = the probe's own
 * behavior: cleanup allowed, no hook). Never writes end records. */
void gbp_initirqa_teardown(const struct gbp_transport *t, struct ringlog *log, const struct gbp_initirqa_config *cfg,
                           struct gbp_initirqa_result *res, const struct gbp_initirqa_teardown_opts *opts);

/* One snapshot into `s` (any storage): PI (twice if two_pi), CONTROL raw,
 * IRQ raw (+ TEST raw); note_intsr13 bookkeeping as for the fixed slots.
 * Logged by gbp_initirqa_snapshot_log (SNAP/PI/RAW records). */
struct gbp_initirqa_snapshot *gbp_initirqa_snapshot_take(const struct gbp_transport *t, struct gbp_initirqa_result *res,
                                                         struct gbp_initirqa_snapshot *s, const char *id, int with_test, int two_pi);
void gbp_initirqa_snapshot_log(struct ringlog *log, const struct gbp_initirqa_result *res, const struct gbp_initirqa_snapshot *s);
/* Same, but stamped with a time base the caller already read (the poll that
 * saw INTSR bit 13) and logged as an event snapshot (poll_intsr= field), as
 * the 003A EVENT is: no second time-base read, so a replay stays exact. */
struct gbp_initirqa_snapshot *gbp_initirqa_snapshot_take_at(const struct gbp_transport *t, struct gbp_initirqa_result *res,
                                                            struct gbp_initirqa_snapshot *s, const char *id, int with_test, int two_pi,
                                                            uint32_t tnow, uint32_t poll_intsr, unsigned polls_before);

/* WRITES / OBSERVED / RESTORE records (the probe's finish writes them after its own end line). */
void gbp_initirqa_log_summary_records(struct ringlog *log, struct gbp_initirqa_result *res);

/* The IRQ-register shape rule (pure; tested on host). Returns 1 if ok,
 * else 0 and *reason names the first failed condition. */
int gbp_initirqa_irq_shape(const struct gbp_initirqa_config *cfg, uint16_t disc, uint16_t gbi, const char **reason);

#ifdef __cplusplus
}
#endif
#endif
