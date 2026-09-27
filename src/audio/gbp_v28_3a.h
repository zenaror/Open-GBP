/*
 * gbp_v28_3a -- §V28's automatic bisection descent (GitHub Issue #128 §2/§3: "TARGET 384 -> 128
 * by 32 per 6 s dwell, bisected to width 2, 60 s confirm hold. Stays at AHEAD 4"), ported from
 * gbp_async.c's own Phase 3 (Issue #117, three review rounds settled the algorithm there) onto
 * the native path (gbp_atrans2/gbp_aplay2/gbp_adec2) at gbp_v28_ladder.h's own constants, and
 * driven by gbp_walker instead of gbp_async's own P0..P3 sequence.
 *
 * THE ALGORITHM CARRIES OVER UNCHANGED IN KIND (only the numbers scale, per gbp_atrans2.h's own
 * precedent): the descent steps GBP_V28_P3_START down by GBP_V28_P3_STEP per GBP_V28_3A_DWELL_S,
 * each depth set WITHOUT a mute (mode UNMUTED -- this is NOT #128 §3's new ROTATE/fixed-mute step
 * mechanism, which applies only to "every nulling step and every refused step", never to 3a's own
 * automatic depths). A depth FAILS when, over its dwell, dup == 0 AND starved > 0 (the correction
 * stopped holding the level; the POC supplies these as its own gbp_aplay2 counter deltas -- this
 * module reads no device). On the first failing depth, bisect between the last holding depth
 * (hi) and the failing one (lo): next = (lo + hi) / 2, until hi - lo <= GBP_V28_P3_BISECT_WIDTH
 * or the bracket cannot shrink further. The bracket closed, a CONFIRM dwell holds the highest
 * failing depth (lo) for up to GBP_V28_3A_CONFIRM_S, watching for a real underrun. The phase then
 * completes; it also completes at GBP_V28_P3_MIN without a failure, or when the very first depth
 * already fails (open bracket, no hold).
 *
 * A CUT DWELL IS NEVER COUNTED WHOLE (gbp_async's own "cut dwell" defect class, entries 8/11/20/
 * 24/25): gbp_v28_3a_cut() marks a dwell in progress `partial`, mirroring gbp_async's own
 * end_phase()'s Phase-3-specific branch; a dwell that had already ended when the phase is cut
 * stays whole (`partial` untouched).
 *
 * THE BEGIN-WHILE-BUSY GATE IS NOT THIS MODULE'S OWN JOB (GitHub Issue #129/#130, Orchestrator
 * review): gbp_atrans2_begin() itself refuses a plan over a running one, in the one place every
 * handler shares. gbp_v28_3a's own tick() only RETRIES a decided-but-not-yet-applied depth change
 * every call, exactly as gbp_walker's own tick() retries a deferred cap -- the retry is automatic
 * and idempotent, so the caller need not remember anything beyond calling tick() every pump slot.
 *
 * WHAT THIS MODULE DOES NOT DO: it never calls gbp_atrans2_step() (the caller's own pump slot
 * does that, exactly as today, for whichever mechanism is active); it knows nothing of
 * gbp_walker, phases or the session (the caller reads gbp_v28_3a_tick()'s own return to decide
 * when to call gbp_walker_phase_complete()); it never reads a device or a clock beyond the `now`
 * it is handed. Pure, bounded, no allocation, no printing, no floating point.
 *
 * DELIBERATELY NARROWER than gbp_async_second_counters() for the confirm hold's own early exit
 * (mirrors gbp_atrans2.h's own "DELIBERATELY NARROWER" precedent, #127): gbp_async's version does
 * per-second underrun/overflow binning for the whole session's report AND ends a confirm hold
 * early on the first underrun. gbp_v28_3a_underrun_observed() does only the second part -- the
 * per-second report, if #128 still wants one, is the session-wide accounting's own job, not this
 * handler's.
 */
#ifndef OPENGBP_GBP_V28_3A_H
#define OPENGBP_GBP_V28_3A_H

#include <stdint.h>
#include "gbp_atrans2.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_V28_3A_DEPTH_CAP     64u    /* mirrors GBP_ASYNC_DEPTH_CAP */
#define GBP_V28_3A_DWELL_S        6u    /* gbp_async_cfg_default's own p3_dwell_s, unconverted (time) */
#define GBP_V28_3A_CONFIRM_S     60u    /* gbp_async_cfg_default's own p3_confirm_s, unconverted (time) */

enum gbp_v28_3a_kind { GBP_V28_3A_STEP = 0, GBP_V28_3A_BISECT = 1, GBP_V28_3A_CONFIRM = 2 };

/* GBP_V28_3A_TICK_* bits, returned by gbp_v28_3a_tick() -- mirrors GBP_ASYNC_TICK_DEPTH_DONE's
 * own "set on every tick until acknowledged" contract. */
#define GBP_V28_3A_TICK_DEPTH_DONE   1   /* the dwell ended: gather the POC's counters and call
                                          * gbp_v28_3a_depth_done() */
#define GBP_V28_3A_TICK_PHASE_COMPLETE 2 /* the descent is over: call gbp_walker_phase_complete() */

struct gbp_v28_3a_depth {
    uint32_t target;
    uint8_t  kind;               /* enum gbp_v28_3a_kind */
    uint8_t  partial;            /* cut before its own end -- never counted complete */
    uint32_t fill_mean_x16, underruns, overflow, dup, drop, lost, starved;
    uint64_t t_set, t_done;
};

struct gbp_v28_3a {
    uint32_t tb_hz;
    uint32_t cur;                 /* the depth under dwell/hold now */
    uint8_t  cur_kind;            /* enum gbp_v28_3a_kind */
    uint8_t  dwell_active;
    uint8_t  depth_pending;       /* the dwell ended (naturally or cut): depth_done() has not yet been called */
    uint8_t  dwell_cut;           /* the pending dwell was cut before its own end: recorded partial */
    uint8_t  bisecting;
    uint8_t  have_hold;
    uint8_t  bracket_closed;
    uint8_t  confirming;
    uint8_t  finished;            /* the descent is over; tick()/depth_done() are inert from here */
    uint8_t  begin_pending;       /* a depth change is decided; tick() retries the begin() every call */
    uint32_t pending_target;
    uint32_t lo, hi, last_hold;
    uint64_t t_set;               /* when the CURRENT depth's plan actually began (begin() succeeded) */
    uint64_t t_dwell_end;
    struct gbp_v28_3a_depth depths[GBP_V28_3A_DEPTH_CAP];
    uint32_t depths_n, depths_overflow;
    uint32_t refused_depth_done;  /* depth_done() called with nothing pending: counted, never silent */
};

/* Begins the descent at GBP_V28_P3_START, AHEAD already fixed at GBP_V28_A4 by the CALLER --
 * this module never touches AHEAD (#128 §2: "Stays at AHEAD 4"). If gbp_atrans2 happens to be
 * busy (it should not be, at a fresh phase's own start), the first depth is deferred exactly like
 * any other: gbp_v28_3a_tick() retries it. `tb_hz` is the SAME hardware timebase gbp_walker uses. */
void gbp_v28_3a_start(struct gbp_v28_3a *s, uint32_t tb_hz, uint64_t now);

/* §V27.14 §4's own early exit, ported narrower (see the header comment above): call whenever the
 * caller observes underruns_total increase. Ends an ACTIVE confirm dwell immediately (t_dwell_end
 * pulled back to `now`); a no-op otherwise (no dwell, a STEP/BISECT dwell, or already past `now`). */
void gbp_v28_3a_underrun_observed(struct gbp_v28_3a *s, uint64_t now);

/* Call every pump slot while 3a is the walker's current phase. Retries a deferred begin();
 * notices a dwell's own end. Returns GBP_V28_3A_TICK_* bits, or 0. `t`/`p`/`d` are only touched
 * for a deferred gbp_atrans2_begin() retry -- never for stepping (the caller's own pump slot
 * calls gbp_atrans2_step() while `t->active`, exactly as today). */
int gbp_v28_3a_tick(struct gbp_v28_3a *s, struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d,
                    uint64_t now);

/* The dwell ended (GBP_V28_3A_TICK_DEPTH_DONE was seen): the caller supplies the POC's own
 * gbp_aplay2/gbp_adec2 counter DELTAS over the dwell window (this module reads no device).
 * Decides the next depth (or that the descent is complete) and marks it PENDING -- gbp_v28_3a_tick()
 * applies it. Refuses (does nothing, no-op) if no dwell had ended or the descent already finished. */
void gbp_v28_3a_depth_done(struct gbp_v28_3a *s, uint32_t fill_mean_x16, uint32_t underruns,
                           uint32_t overflow, uint32_t dup, uint32_t drop, uint32_t lost, uint32_t starved);

/* The phase is being cut (a cap, the session cap, or a stop) -- call BEFORE the caller advances
 * past 3a. Marks an in-progress dwell `partial` (a dwell that had already ended stays whole). */
void gbp_v28_3a_cut(struct gbp_v28_3a *s, uint64_t t_end);

int gbp_v28_3a_finished(const struct gbp_v28_3a *s);

/* NULL if `index` is out of range (>= depths_n). */
const struct gbp_v28_3a_depth *gbp_v28_3a_depth_record(const struct gbp_v28_3a *s, uint32_t index);

#ifdef __cplusplus
}
#endif
#endif
