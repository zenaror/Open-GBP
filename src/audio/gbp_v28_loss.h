/*
 * gbp_v28_loss -- the LOSS diagnostic's phase handler (GitHub Issue #137, U-GBP-050): steady holds at ONE fixed TARGET and
 * AHEAD, so the AUDIO blocks the drain fails to deliver (about 1.6 % in RUN 51-53, 0.18 % in RUN 43, the last build before the
 * native path) are measured AWAY from transitions, against a two-factor manipulation, then one separately labelled AHEAD-1
 * hold with both underrun paths wired.
 *
 * WHAT IT IS. A pure state machine over the same collaborators gbp_v28_3b uses (gbp_atrans2 for the two entry transitions,
 * gbp_aplay2, gbp_adec2), with no device, no printing and no allocation. It reads no counter itself: the caller hands it a
 * snapshot of its own counters every tick (struct gbp_v28_loss_ctr) and the histograms it keeps (struct gbp_v28_hist).
 *
 * THE DESIGN (the Orchestrator's decision on #137, `docs/research/HARDWARE_TESTS.md` §V28.16):
 *   ENTRY   one UNMUTED plan to (GBP_V28_LOSS_TARGET, AHEAD 4), 3a's own first begin; the holds start once it has landed.
 *   WARM    10 s at the baseline cell, RECORDED BUT NEVER COUNTED (the ring and the corrector settle after the entry).
 *   CELLS   twelve holds of 20 s, three visits to each of the four cells. L is the GX label (on = production image, l = off: the
 *           label block of submit_ready is skipped); S is the production step (S = 128 pushes a call, the production value; s = 64,
 *           RUN 40's half-size step: the SAME pushes, partitioned into twice the calls). Every consecutive pair of holds differs in
 *           exactly ONE factor (CLAUDE.md section 18), all four cells are covered three times.
 *           THE ORDER IS NOT THE PLAIN CYCLE (L,S) -> (L,s) -> (l,s) -> (l,S) -> ..., which the decision comment names, and why: in
 *           that cycle the label-on holds sit at positions {0,1,4,5,8,9} and the label-off holds at {2,3,6,7,10,11}, two holds later
 *           on average, so a monotone drift of d points a hold biases the label effect by -2d (a review found it; the step is
 *           balanced by it). A walk that flips one factor a step alternates L xor S, so BOTH factors cannot be balanced against a
 *           linear drift (searched exhaustively: 800 walks); this one balances L exactly (label-on positions sum 33, as do
 *           label-off) and S to a sum difference of 4 holds (a bias of 2d/3, a third of the plain cycle's worst). tools/v28loss.py
 *           also prints a trend-adjusted estimate and holds a verdict the trend moves.
 *   FINAL   ROTATE (GBP_V28_STEP_MUTE) to AHEAD 1 at the same TARGET, then 60 s at the baseline cell, counting the
 *           underruns: the calibrated host predicts 14-15 in 60 s at the ~1.6 % deficit (#137).
 *
 * WHY THE ARMS ARE NOT APPLIED HERE. The handler decides which cell a hold is in (`label_off`, `step_half`); the caller applies
 * them (main.c: the label block of submit_ready, ap2.step_pushes). During every transition the cell is the baseline, so an
 * entry never runs on an arm.
 *
 * WHAT A HOLD RECORDS. Absolute counter snapshots at the hold's start, at t_start + GBP_V28_LOSS_LATE_S (the PRIMARY window
 * starts there: the first seconds after an arm changes are settling) and at its end, the timestamps of the three, the hold's
 * histograms (reset at its start), and the number of times the underrun path fired. The loss itself is computed by the reader
 * (tools/v28loss.py): 1 - blocks_in / (4096 x seconds); nothing here decides it.
 *
 * A CUT HOLD IS PARTIAL, never whole (gbp_walker.h's rule); a hold cut before its late mark has no late snapshot and says so.
 */
#ifndef OPENGBP_GBP_V28_LOSS_H
#define OPENGBP_GBP_V28_LOSS_H

#include <stdint.h>
#include "gbp_atrans2.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_V28_LOSS_WARM_S      10u
#define GBP_V28_LOSS_HOLD_S      20u     /* a cell hold */
#define GBP_V28_LOSS_LATE_S       3u     /* the primary window starts this long after the hold's start */
#define GBP_V28_LOSS_FINAL_S     60u
#define GBP_V28_LOSS_CYCLES       3u
#define GBP_V28_LOSS_CELLS        4u     /* the four cells (L,S) (L,s) (l,s) (l,S) */
#define GBP_V28_LOSS_STEP_FULL  128u     /* S: the production step (GBP_APLAY2_STEP_PUSHES) */
#define GBP_V28_LOSS_STEP_HALF   64u     /* s: RUN 40's half-size step */
_Static_assert(GBP_V28_LOSS_STEP_FULL == GBP_APLAY2_STEP_PUSHES,
    "gbp_v28_loss: the S arm is no longer the production step -- the baseline cell would not be the production image");
_Static_assert(GBP_V28_LOSS_STEP_HALF * 2u == GBP_V28_LOSS_STEP_FULL, "gbp_v28_loss: the s arm is exactly half the S arm (RUN 40's manipulation)");
/* warm + cells + final */
#define GBP_V28_LOSS_HOLDS_MAX  (1u + GBP_V28_LOSS_CYCLES * GBP_V28_LOSS_CELLS + 1u)
/* the seconds of holds alone; the entries (a few seconds each) come on top, and the phase cap has the margin */
#define GBP_V28_LOSS_HOLDS_S    (GBP_V28_LOSS_WARM_S + GBP_V28_LOSS_CYCLES * GBP_V28_LOSS_CELLS * GBP_V28_LOSS_HOLD_S + \
                                 GBP_V28_LOSS_FINAL_S)

/* the histograms: how long each thing took (ticks) or how far apart the taps arrived */
enum gbp_v28_hist_id {
    GBP_V28_H_TAP = 0,      /* the whole tap callback, in the drain slot */
    GBP_V28_H_DECODE,       /* the tap's decode alone (gbp_adec2_push_block) */
    GBP_V28_H_PROD,         /* one production call in the pump slot (gbp_aplay2_produce) */
    GBP_V28_H_PUMP,         /* the whole pump call: the stretch the drain cannot run in */
    GBP_V28_H_LABEL,        /* the label block of submit_ready (only while the label is on) */
    GBP_V28_H_GAP,          /* the interval between two consecutive taps */
    GBP_V28_NHIST
};

#define GBP_V28_HIST_BINS 5u

struct gbp_v28_hist {
    uint32_t count;
    uint32_t max;
    uint64_t sum;
    uint32_t bin[GBP_V28_HIST_BINS];     /* <= edge[0], <= edge[1], <= edge[2], <= edge[3], > edge[3] */
    uint32_t edge[GBP_V28_HIST_BINS - 1u];
};

/* the edges of each histogram: ticks at 40.5 MHz. The three the Orchestrator named (tap, production, label) use
 * <=1k <=2k <=4k <=8k >8k; the pump call and the tap gap need their own scale (a block period is 9 888 ticks). */
void gbp_v28_hist_init(struct gbp_v28_hist *h, const uint32_t edge[GBP_V28_HIST_BINS - 1u]);
void gbp_v28_hist_note(struct gbp_v28_hist *h, uint32_t ticks);
/* all six with their standard edges; used at start-up and reset at every hold's start (edges kept) */
void gbp_v28_hists_init(struct gbp_v28_hist h[GBP_V28_NHIST]);
void gbp_v28_hists_clear(struct gbp_v28_hist h[GBP_V28_NHIST]);

/* the caller's own counters, all cumulative: the handler snapshots and never reads a device */
struct gbp_v28_loss_ctr {
    uint32_t blocks_in;      /* gbp_adec2.blocks_in: AUDIO blocks decoded into the ring */
    uint32_t taps;           /* every tap call, refused or short ones included */
    uint32_t taps_failed;
    uint32_t wrong_len;
    uint32_t underruns;      /* gbp_aplay2.underruns */
    uint32_t dup, drop;
    uint32_t starved;        /* gbp_aplay2.starved_steps */
    uint32_t produced, handed;
    uint32_t ring_gated;
    uint32_t ring;           /* gbp_adec2.count, at the snapshot */
    uint32_t target, ahead;  /* gbp_aplay2's OBSERVED target and ahead: the log verifies the fixed operating point, not the intent */
};

enum gbp_v28_loss_kind { GBP_V28_LOSS_WARM = 0, GBP_V28_LOSS_CELL = 1, GBP_V28_LOSS_FINAL = 2 };

struct gbp_v28_loss_hold {
    uint8_t  kind;                   /* enum gbp_v28_loss_kind */
    uint8_t  cyc;                    /* the cycle of a CELL hold, 0-based; 0 for the others */
    uint8_t  label_on;               /* L (1) or l (0) */
    uint8_t  step_full;              /* S (1) or s (0) */
    uint8_t  ahead;
    uint8_t  partial;                /* cut before its own end */
    uint8_t  has_late;               /* the late snapshot was taken */
    uint8_t  reserved;
    uint32_t target;
    uint32_t underrun_hooks;         /* times the underrun path fired during the hold */
    uint64_t t_start, t_late, t_end;
    struct gbp_v28_loss_ctr c_start, c_late, c_end;
    struct gbp_v28_hist hist[GBP_V28_NHIST];
};

struct gbp_v28_loss {
    uint32_t tb_hz;
    uint8_t  finished;
    uint8_t  begin_pending;          /* the current entry is decided but its plan has not begun */
    uint8_t  entry_final;            /* the pending/landing entry is the AHEAD-1 one */
    uint8_t  landing;                /* the entry plan is running: the hold starts when it lands */
    uint8_t  hold_active;
    uint8_t  hold_pending;           /* the hold ended (or was cut): hold_done() has not yet been called */
    uint8_t  late_taken;
    uint8_t  starting;               /* a hold just ended and the next CELL starts on the next tick */
    /* THE CELL IN FORCE, what the caller applies -- stored INVERTED so that the zeroed struct (before start(), or after a cut) is the
     * BASELINE: label_off = 1 is the l arm, step_half = 1 the s arm. A caller that reads them before the phase starts gets the
     * production image, never an arm. */
    uint8_t  label_off, step_half;
    uint32_t next_index;             /* the index of the NEXT hold to start, 0 .. GBP_V28_LOSS_HOLDS_MAX */
    uint32_t cur_hooks;              /* underrun-path firings in the current hold */
    uint64_t t_hold_end, t_late_at;
    struct gbp_v28_loss_hold cur;    /* the hold in progress; copied to holds[] by hold_done() */
    struct gbp_v28_loss_hold holds[GBP_V28_LOSS_HOLDS_MAX];
    uint32_t holds_n;
    uint32_t refused_hold_done;      /* hold_done() called with nothing pending: counted, never silent */
    uint32_t begin_pending_ticks;    /* ticks the entry spent refused (a transition still running) */
};

/* Decides the entry (AHEAD 4 at GBP_V28_LOSS_TARGET) and arms the baseline cell. `tb_hz` is gbp_walker's timebase. */
void gbp_v28_loss_start(struct gbp_v28_loss *s, uint32_t tb_hz, uint64_t now);

/* Call whenever the caller observes the AI underrun counter increase (the same contract as gbp_v28_3a/3b's): counted into the
 * hold in progress, never ends it -- the final hold's underrun count is the measurement. A no-op outside a hold. */
void gbp_v28_loss_underrun_observed(struct gbp_v28_loss *s, uint64_t now);

#define GBP_V28_LOSS_TICK_HOLD_DONE      1   /* a hold ended: call gbp_v28_loss_hold_done() */
#define GBP_V28_LOSS_TICK_PHASE_COMPLETE 2   /* the phase is over: call gbp_walker_phase_complete() */

/* Call every pump slot while the LOSS phase is current, BEFORE the slot's own produce/step call, as 3a's and 3b's ticks are: the
 * entry's landing is read from `t->active`, so an entry that landed in that call is seen one slot (about 0.25 ms) later.
 * `hist` is the caller's live histograms: cleared at every hold's start, copied at its end. */
int gbp_v28_loss_tick(struct gbp_v28_loss *s, struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d,
                      uint64_t now, const struct gbp_v28_loss_ctr *c, struct gbp_v28_hist hist[GBP_V28_NHIST]);

/* The hold ended (GBP_V28_LOSS_TICK_HOLD_DONE was seen): commits its record and decides the next hold, or the final entry, or
 * the end. Counted, a no-op, if nothing was pending. */
void gbp_v28_loss_hold_done(struct gbp_v28_loss *s);

/* The phase is cut (a cap, the session cap, a stop): call BEFORE the walker advances. The hold in progress is recorded PARTIAL,
 * with the counters the caller hands over as its end; one that had already ended stays whole. */
void gbp_v28_loss_cut(struct gbp_v28_loss *s, uint64_t t_end, const struct gbp_v28_loss_ctr *c,
                      const struct gbp_v28_hist hist[GBP_V28_NHIST]);

int gbp_v28_loss_finished(const struct gbp_v28_loss *s);

/* NULL if `index` >= holds_n. */
const struct gbp_v28_loss_hold *gbp_v28_loss_hold_record(const struct gbp_v28_loss *s, uint32_t index);

/* The cell of CELL hold number `k` (0-based over the twelve): its label and step level. Pure; the tests use the same table.
 * Returns 0 for k >= CYCLES x CELLS. */
int gbp_v28_loss_cell(uint32_t k, uint8_t *label_on, uint8_t *step_full);

#ifdef __cplusplus
}
#endif
#endif
