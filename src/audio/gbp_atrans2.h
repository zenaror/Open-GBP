/*
 * gbp_atrans2 — gbp_atrans.h's transition executor (GitHub Issue #117), PORTED onto the native
 * path by Issue #127: the SAME three mechanisms (ROTATE, HELD, UNMUTED), the SAME algorithm, at
 * this path's own PUSHES (2048, not 128) and AHEAD (GBP_APLAY2_AHEAD, under test -- see
 * gbp_aplay2.h). Applies a gbp_async TRANSITION PLAN to gbp_aplay2 and gbp_adec2's ring, one pump
 * call at a time. A NEW PATH, NOT A MOVED DEFAULT: gbp_atrans.c is untouched.
 *
 * Every mechanism, every invariant and every conservation argument gbp_atrans.h documents in full
 * carries over unchanged in KIND -- only the numbers (PUSHES, AHEAD, the aim) scale with this
 * path's own chunk. Read gbp_atrans.h first; this header records only what differs.
 *
 * Pure over its two collaborators: no device, no printing, no allocation.
 *
 * GBP_ATRANS2_BEGIN REFUSES A PLAN OVER A RUNNING ONE (GitHub Issue #129/#130, Orchestrator
 * review): Issue #117's entry 21 ("a plan was applied over a running one", deterministic in 63
 * of 64 phases without a guard) is a defect at the SESSION layer (gbp_async/gbp_walker skipping
 * a phase transition while busy); this is the SAME defect one level down, inside a single phase,
 * whenever a handler (§V28's 3a bisection, the step sweep) issues more than one plan of its own.
 * gbp_walker's own busy-gate does not reach here -- it only refuses to ADVANCE BETWEEN phases; it
 * has no view of a handler calling gbp_atrans2_begin() a second time inside one phase. So the
 * gate is here, in the ONE place every handler shares, not duplicated in each one:
 * gbp_atrans2_begin() itself refuses (returns 0, counts `begin_refused_active`, touches nothing)
 * when `active` is already 1, rather than clobbering the running transition's state.
 *
 * THE PLAN CARRIES THE TARGET AHEAD (GitHub Issue #129/#130, the Orchestrator's review, on top of
 * the same requirement): `gbp_aplay2`'s own `ahead` field (see gbp_aplay2.h) never changes except
 * through `gbp_atrans2_begin()`, which applies it inside the mute together with the surplus drop
 * -- never through a bare setter callable mid-transition, which would leave the mute-length and
 * surplus-drop accounting computed against the wrong value. A step that LOWERS ahead drops the
 * surplus READY fronts, without replacement, right at begin (counted in `ahead_drops`); one that
 * raises it only tops up, unchanged from today. `ahead` is clamped to [1, GBP_APLAY2_POOL] --
 * counted as a fault, like an insufficient mute, never a hard refusal.
 *
 * THE ROTATE LEVEL IS SET IN SILENCE (GitHub Issue #136, the Orchestrator's decision on RUN 52; it
 * REPLACES the landing trim and the aim/call-window gating of Issues #129/#130, which are gone).
 *
 * WHAT WAS WRONG. The previous ROTATE ran a produce+rotate loop for the whole mute, then at the landing
 * discarded the ring's excess down to target. The landing runs AFTER the first audible hand-off
 * (`handed == mute + 1`), so that cut spliced the stream `ahead` chunks after unmute (about 33 ms at AHEAD 1,
 * 64 at AHEAD 2, 127 at AHEAD 4): the moment of an audible splice depended on the AHEAD in force, which #122
 * section 1(c) forbids, and it could only cut, so a ring below target at the landing stayed below it. On the
 * console (124.8 pump calls per period, a feed 0.5 % slow: both from the RUN 52 log) three GATE moves landed
 * 826-875 samples short. Every host test before Issue #136 ran 16 calls a period with an exact feed, where
 * the ring at every period start is target; the comments that called the trim "masked" were never tested.
 *
 * WHAT IT DOES NOW. Nothing is consumed until the second-to-last hand-off period: the ring only fills, which
 * is silent and never a discontinuity. There, with nothing in flight and the queue whole, the level is set
 * with ONE discard (gbp_adec2_discard): the ring is cut to
 *     target + ahead x PUSHES - (the feed until the landing call) - GBP_ATRANS2_LAND_BIAS,
 * the feed measured from the callback's own hand-off instants (so a late pump call is compensated, not
 * guessed), then exactly `ahead` rotations follow, each building one chunk from the already-cut ring and
 * dropping the oldest queued one, so that every chunk that will be HEARD is built after the cut. The landing
 * cuts nothing. The ring lands at target - 160 on an exact feed (the recovery's 128 and the bias 32), 20 lower
 * per 0.5 % of feed deficit, inside the sweep's band [target - BAND, target].
 *
 * WHAT IT NEEDS. The ring must hold that level at the cut, and the only source of samples is the feed, one
 * PUSHES per period, so a mute has a FLOOR of about ceil(target / PUSHES) + ahead - 1 periods, whatever the
 * mechanism: gbp_v28_ladder.h derives GBP_V28_STEP_MUTE (6) and GBP_V28_START_MUTE (12) from it, measured on
 * the calibrated host. A mute too short to fill the ring is REPORTED (`fill_short`, `fill_shorts`), never
 * hidden and never turned into a cut: the ring lands short and the sweep gate shows it.
 *
 * WHAT IS CHECKED. `disc_rel` is the period the cut ran in relative to the first audible hand-off (negative:
 * inside the mute), `rot_post` the rotations after it (`unmasked` if fewer than ahead, i.e. a pre-cut chunk
 * would be heard), and the sweep fails a GATE row as SPLICE for any cut at `disc_rel >= 0` or anywhere in the
 * dwell that follows (tests/unit/test_v28_sweep_landing.c asserts both on the console-calibrated host, and
 * that every chunk heard was built after the last cut: RED on the source before Issue #136 and on its first
 * fix).
 *
 * HELD is unchanged (a mute of pause + 1, its own landing trim). UNMUTED has no mute.
 */
#ifndef OPENGBP_GBP_ATRANS2_H
#define OPENGBP_GBP_ATRANS2_H

#include <stdint.h>
#include "gbp_aplay2.h"
#include "gbp_adec2.h"

#ifdef __cplusplus
extern "C" {
#endif

enum gbp_atrans2_mode { GBP_ATRANS2_UNMUTED = 0, GBP_ATRANS2_HELD = 1, GBP_ATRANS2_ROTATE = 2 };

/* Issue #136: the level-setting cut aims this far BELOW target. The landing call finds the ring after its own
 * recovery produce (128 pushes) and after whatever the pump's first call past the hand-off let the feed add
 * (65.5 samples per ms late); the sweep's band is [target - BAND, target], so a late call can only push the
 * ring toward the upper edge. 32 leaves the landing at target - 160 on an exact feed: 96 below the upper
 * edge (a landing call up to 2.4 ms late) and, with a feed 0.5 % slow, 51 above the lower one. */
#define GBP_ATRANS2_LAND_BIAS 32u

struct gbp_atrans2 {
    uint8_t  active;
    uint8_t  mode;                    /* enum gbp_atrans2_mode */
    uint8_t  reached;                 /* the ring reached the level once (informational) */
    uint8_t  discarding;              /* HELD: a discard chunk of the executor's own is under way */
    uint8_t  rotating;                /* ROTATE: a rotation chunk is under way */
    uint8_t  discard_pending;         /* HELD: the shallowing discard, deferred until the queue is whole */
    uint8_t  adjusted;                /* ROTATE: the ring's level has been set (Issue #136) */
    uint32_t mute;                    /* chunks of silence asked for */
    uint32_t pause;                   /* the plan's climb in chunks (the record's arithmetic; counted in feed) */
    uint32_t discard;                 /* samples dropped from the ring's head (a shallower level) */
    uint32_t target;                  /* the level in force from begin on */
    uint32_t handed_at_start;         /* the chain's hand-off count at begin */
    /* this plan */
    uint32_t discards;                /* HELD: chunks discarded under silence */
    uint32_t rotations;               /* ROTATE: chunks rotated through READY (front dropped) */
    uint32_t topped;                  /* chunks handed back to finish the held queue (0 or 1) */
    uint32_t trimmed;                 /* HELD, ROTATE: samples dropped from the ring at the landing */
    int32_t  residue;                 /* ROTATE: the effective level minus the target at the landing, AFTER the
                                        * ring's own trim (the READY component, if any, is left to the band --
                                        * gbp_aplay2.h's own producer clears it in about one chunk period) */
    uint8_t  late;                    /* ROTATE: a rotation under way when the silence ended, queued undropped */
    uint8_t  unmasked;                /* ROTATE: a shallowing's pre-splice chunk still in READY (discard, < AHEAD rotations) */
    uint32_t short_by;                /* HELD: samples the ring lay below the level at the landing */
    uint32_t handed_seen;
    uint32_t handed_last;             /* ROTATE: `handed` as of the last gbp_atrans2_step() call, to detect a
                                       * hand-off boundary crossing (see calls_in_period, below) */
    uint32_t calls_in_period;          /* ROTATE: gbp_atrans2_step() calls seen so far THIS hand-off period,
                                       * 1-indexed (this call counts) -- reset to 0 whenever `handed` changes,
                                       * then incremented, so it is always this call's own 1-based position */
    /* Issue #136, ROTATE: where the level was set, and what came of it */
    uint32_t disc_n;                  /* samples cut from the ring's head by the level-setting discard */
    int32_t  disc_rel;                /* the hand-off period it ran in, relative to the first audible hand-off
                                       * (-1 = the last silent period, -2 the one before; >= 0 would be AFTER unmute) */
    uint32_t rot_post;                /* rotations completed after the discard: each rebuilds one queued chunk */
    uint32_t fill_short;              /* the samples the ring lacked at the discard point (the mute was too short) */
    uint32_t calls_prev;              /* gbp_atrans2_step() calls in the previous hand-off period */
    uint64_t t_start, t_reached, t_end;
    /* since init */
    uint32_t begun, completed;
    uint32_t faults;                  /* plans whose mute could not fit their mechanism, or whose ahead was out
                                       * of [1, GBP_APLAY2_POOL] (never; counted, corrected) */
    uint32_t begin_refused_active;    /* a begin() while already active: refused, counted, nothing touched */
    uint32_t ahead_drops;             /* surplus READY fronts dropped at begin by an ahead-lowering step */
    uint32_t trim_max, trim_sum;      /* HELD, ROTATE */
    uint32_t shorts, short_max;       /* HELD: landings below the level */
    uint32_t converted;               /* HELD: landings that turned a discard under way into the refill */
    uint32_t rotate_landings, lates, unmaskeds;   /* ROTATE */
    uint32_t unadjusted, fill_shorts;             /* ROTATE: landings whose level was never set / lacked material */
    int32_t  residue_min, residue_max;            /* ROTATE, over its landings */
};

void gbp_atrans2_init(struct gbp_atrans2 *t);

/* the mute a mechanism needs for a climb of `pause` chunks at the given `ahead`: ROTATE
 * pause + ahead, HELD pause + 1, UNMUTED 0 */
uint32_t gbp_atrans2_min_mute(uint8_t mode, uint32_t pause, uint32_t ahead);

/* Apply a plan now, at the given `ahead` (p->ahead from this call on -- see the header comment
 * above; a surplus drop happens here too, if ahead is lower than it was). Returns 1 when applied,
 * or 0 when refused because a transition is already active (begin_refused_active counts it;
 * nothing about the running transition, INCLUDING p->ahead, is touched). */
int gbp_atrans2_begin(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint64_t now, uint8_t mode,
                      uint32_t mute, uint32_t pause, uint32_t discard, uint32_t target, uint32_t ahead);

/* One pump call while active. Returns 1 on the call that completes the plan, else 0. `*to_queue` is
 * set to a produced chunk the CALLER must flush and queue, else -1. */
int gbp_atrans2_step(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint64_t now, int *to_queue);

/* hand-offs since the plan began (silence or audio alike) */
uint32_t gbp_atrans2_handoffs(const struct gbp_atrans2 *t, const struct gbp_aplay2 *p);

#ifdef __cplusplus
}
#endif

#endif
