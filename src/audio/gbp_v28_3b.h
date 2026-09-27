/*
 * gbp_v28_3b -- §V28's AHEAD hold (GitHub Issue #128 §2: "3b: AHEAD 1 at the anchor for 60 s. Ends
 * at first underrun; if underrun, AHEAD 2 held for the remaining 60 s. A clean hold bounds the
 * rate below 0.05/s at 95 %"), driven by gbp_walker like gbp_v28_3a.
 *
 * THE ANCHOR is 3a's own confirmed floor (its lowest holding TARGET, `s.lo` after
 * gbp_v28_3a's own bracket closes) -- passed in at gbp_v28_3b_start(), TARGET never changes again
 * in 3b: only AHEAD does, from 4 (3a's own fixed value) down to 1, and up to 2 if the AHEAD-1 hold
 * sees an underrun.
 *
 * THE ENTRY STEP (AHEAD 4 -> 1) AND ANY ESCALATION (AHEAD 1 -> 2) USE THE STEP MECHANISM
 * (#128 §3): mode ROTATE, mute GBP_V28_STEP_MUTE (6) -- NOT 3a's own UNMUTED transitions. This is
 * precisely the mechanism/margin the perceptual run will use, which is the whole point of 3b: it
 * is the observation #128 §5 names as settling the 32-tap reversal condition (`GBP-HW-351`).
 *
 * THE HOLD, EXACTLY TWO LEVELS, NEVER A THIRD: AHEAD 1 for up to GBP_V28_3B_HOLD_S (60 s),
 * ending EARLY at the first observed underrun (gbp_v28_3b_underrun_observed(), the SAME
 * early-exit idiom gbp_v28_3a's own confirm hold uses). If (and only if) that underrun happened,
 * AHEAD 2 is held for a FULL, SEPARATE GBP_V28_3B_HOLD_S (not the remaining time from AHEAD 1's
 * own budget: #128 §2's own 120 s phase figure is 60 + 60, not 60 total) -- and 3b finishes
 * there regardless of what AHEAD 2's own hold sees. If AHEAD 1's hold runs its own full 60 s with
 * no underrun, 3b finishes there instead, using only half its own phase budget.
 *
 * Shares gbp_v28_3a's own construction discipline: a decided AHEAD change is held PENDING and
 * retried every tick via gbp_atrans2_begin()'s own busy-gate (never assumed to have taken effect);
 * a cut dwell is recorded PARTIAL, never whole; depth_done() (here, hold_done()) fires on every
 * tick until acknowledged, even after a cut sets `finished`.
 *
 * What this module does NOT do: it never calls gbp_atrans2_step() (the caller's own pump slot
 * does, exactly as for 3a); it knows nothing of gbp_walker, phases or the session; it never reads
 * a device or a clock beyond the `now` it is handed; it never decides the 32-tap reversal itself
 * -- it only produces the (T, A, clean-or-not) record #128 §5 asks the validation run for.
 */
#ifndef OPENGBP_GBP_V28_3B_H
#define OPENGBP_GBP_V28_3B_H

#include <stdint.h>
#include "gbp_atrans2.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_V28_3B_HOLD_S   60u   /* #128 §2's own figure, per level */

struct gbp_v28_3b_hold {
    uint32_t ahead;              /* 1 or 2 */
    uint8_t  underrun_seen;      /* an underrun was observed during THIS hold */
    uint8_t  partial;            /* cut before its own end -- never counted complete */
    uint64_t t_set, t_done;
};

struct gbp_v28_3b {
    uint32_t tb_hz;
    uint32_t anchor_target;      /* 3a's own confirmed floor; never changes again in 3b */
    uint32_t cur_ahead;          /* the AHEAD level under hold/pending now: 1 (entry) or 2 (escalation) */
    uint8_t  hold_active;
    uint8_t  hold_pending;       /* the hold ended (naturally or cut): hold_done() has not yet been called */
    uint8_t  hold_cut;           /* the pending hold was cut before its own end: recorded partial */
    uint8_t  underrun_seen;      /* an underrun observed during the CURRENT hold, not yet recorded */
    uint8_t  finished;           /* 3b is over; tick()/hold_done() are inert from here */
    uint8_t  begin_pending;      /* an AHEAD change is decided; tick() retries the begin() every call */
    uint32_t pending_ahead;
    uint64_t t_set;              /* when the CURRENT hold's plan actually began */
    uint64_t t_hold_end;
    struct gbp_v28_3b_hold holds[2];     /* at most AHEAD 1, then AHEAD 2 -- never a third level */
    uint32_t holds_n;
    uint32_t refused_hold_done;  /* hold_done() called with nothing pending: counted, never silent */
};

/* Begins the entry step, AHEAD 4 -> 1 at `anchor_target` (3a's own floor). `tb_hz` is the SAME
 * hardware timebase gbp_walker/gbp_v28_3a use. */
void gbp_v28_3b_start(struct gbp_v28_3b *s, uint32_t anchor_target, uint32_t tb_hz, uint64_t now);

/* §128 §2's own early exit: call whenever the caller observes underruns_total increase. Ends an
 * ACTIVE hold immediately (t_hold_end pulled back to `now`) and marks it; a no-op if no hold is
 * active or it has already seen one. */
void gbp_v28_3b_underrun_observed(struct gbp_v28_3b *s, uint64_t now);

/* GBP_V28_3B_TICK_* bits, returned by gbp_v28_3b_tick() -- mirrors gbp_v28_3a's own contract. */
#define GBP_V28_3B_TICK_HOLD_DONE      1   /* a hold ended: call gbp_v28_3b_hold_done() */
#define GBP_V28_3B_TICK_PHASE_COMPLETE 2   /* 3b is over: call gbp_walker_phase_complete() */

/* Call every pump slot while 3b is the walker's current phase. Retries a deferred begin();
 * notices a hold's own end. Returns GBP_V28_3B_TICK_* bits, or 0. */
int gbp_v28_3b_tick(struct gbp_v28_3b *s, struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d,
                    uint64_t now);

/* The hold ended (GBP_V28_3B_TICK_HOLD_DONE was seen): records it and, only for AHEAD 1 with an
 * observed underrun, decides the AHEAD 2 escalation (gbp_v28_3b_tick() applies it). A no-op,
 * counted, if nothing was pending. */
void gbp_v28_3b_hold_done(struct gbp_v28_3b *s);

/* The phase is being cut (a cap, the session cap, or a stop) -- call BEFORE the caller advances
 * past 3b. Marks an in-progress hold `partial` (one that had already ended stays whole). */
void gbp_v28_3b_cut(struct gbp_v28_3b *s, uint64_t t_end);

int gbp_v28_3b_finished(const struct gbp_v28_3b *s);

/* NULL if `index` is out of range (>= holds_n, at most 2). */
const struct gbp_v28_3b_hold *gbp_v28_3b_hold_record(const struct gbp_v28_3b *s, uint32_t index);

#ifdef __cplusplus
}
#endif
#endif
