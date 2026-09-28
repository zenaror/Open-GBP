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
 * GBP_ATRANS2_AIM = GBP_APLAY2_PUSHES / 2 (half a chunk, exactly gbp_atrans.h's own derivation of
 * its AIM = 64 = 128 / 2) -- expressed as a formula so it never drifts from PUSHES again. Since a
 * chunk's DURATION is identical on both paths (31.25 ms), half a chunk in DECODE SAMPLES is also
 * half a chunk in TIME on both paths: 1024 samples at 65 536 Hz is the same 15.625 ms as 64 samples
 * at 4 096 Hz -- not a coincidence, the same margin the frozen path's aim gives, at this path's rate.
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
 * ROTATE TRIMS THE RING TO TARGET AT THE LANDING (GitHub Issue #129/#130, the Orchestrator's
 * decision): a ROTATE landing can fall mid-cycle (the continuous produce+rotate loop pinned at
 * `aim` runs for the whole mute, ending on a wall-clock hand-off count, not on the cycle's own
 * phase), leaving the ring's own level (`d->count`) above target by up to about a chunk. HELD
 * already trims its own landing this way (step_held2); ROTATE's own residue on this path measures
 * about 4x the old path's own (#117's 15.6 ms vs this path's ~62.5 ms worst-case among the sweep's
 * transitions), and the ring component alone drains only through the slow DUP/DROP corrector --
 * seconds, not the one chunk period the READY component clears in -- long enough to inflate what a
 * nulling judgment sees. `gbp_atrans2_step()` discards the ring's excess down to target at the
 * landing, never below it (a shortfall is worse than the excess it fixes), before reporting
 * `residue` -- masked (still inside the same landing step) and cheap (a ring-pointer advance).
 *
 * ROTATE ONLY STARTS A NEW ROTATION WITH ENOUGH CALLS LEFT TO FINISH IT (GitHub Issue #129/#130,
 * the Orchestrator's decision, closing a gap the ROTATE-trim and READY-floor work above exposed
 * rather than caused): `gbp_aplay2_irq_handoff()`'s own `mute_carry` field gives every reader ONE
 * consistent definition of "still muted" -- through the LAST silent hand-off, not one early (see
 * gbp_aplay2.h) -- which is what gbp_v28_sweep's own entry 6 (an AHEAD-lowering STEP landing AT
 * AHEAD 1, floor 0, no slack) needed to land with its queue warm instead of empty. But a NEW
 * rotation STARTED without enough of its own hand-off period left has no guarantee of finishing;
 * landing while it is still mid-flight would lose whatever ring content it already consumed (the
 * landing branch above only resets `rotating`, it never completes or drops an abandoned one) --
 * found on two climbing transitions at one specific burst timing, a real ring shortfall, not a
 * disagreement and not a `gbp_aplay2_drop_front()` safety violation (proven separately, 320 driven
 * transitions, 0 violations, with and without this fix).
 *
 * A coarser gate (refuse any new start once `handed == t->mute`, the LAST muted hand-off) also
 * closes the shortfall, but it is NOT exact: measured directly (a real cascade, not a synthetic
 * one), entry 6's own last natural rotation start lands at EXACTLY `GBP_ATRANS2_CALLS_PER_HANDOFF`
 * calls of window left -- margin 0, sufficient -- and a period-level gate refuses that start too,
 * reopening entry 6's own underrun to close the climbs' shortfall. The exact condition instead
 * compares CALLS, not periods: `calls_in_period`/`handed_last` (this module's own bookkeeping, reset
 * on every hand-off boundary gbp_atrans2_step() observes) give the calls left before the landing
 * check, at exactly this call; a new rotation starts only if that is at least
 * `GBP_ATRANS2_CALLS_PER_HANDOFF` (a fresh rotation's own need, under the default per-call cadence).
 * Arithmetic over this module's own accounting, not a tuned threshold against `p->mute`'s own
 * timing, and not conditional on AHEAD or direction (#122 section 1(c), quoted in #128 section 3).
 * An ALREADY-rotating chunk (`t->rotating`, checked first, always ungated) is unaffected -- this
 * only decides whether a NEW one may start.
 *
 * THE LAST PERIOD'S ROTATION IS TAKEN ONLY FROM A RING AT TARGET + GBP_ATRANS2_LAST_MARGIN (GitHub Issue
 * #136, RUN 52's own measurement): a rotation subtracts a whole chunk, and in the last period the
 * period's own inflow refills it to where the ring stood when the period began -- so the ring at the
 * landing IS the ring at the start of that last period (less the landing recovery's 128 and whatever a
 * late first call costs), whatever level that happens to be. The landing trim only cuts; nothing in this
 * module can add a sample. Four GATE-and-INFO moves of RUN 52's sweep landed 792-875 samples short of
 * target for that reason and stayed short (three GATE, two INFO in that range; two more INFO, 324 and
 * 393). Before this change the last period's aim was target - GBP_ATRANS2_AIM (rotate from almost any
 * ring). Now, from a ring below target + LAST_MARGIN the rotation is skipped, the period's inflow lifts
 * the ring past target, and the trim cuts it back to exactly target.
 *
 * WHAT THIS COSTS, AND WHAT IT DOES NOT FIX (measured by review, Issue #136): the trim is larger. On the
 * model at the hardware's 125 calls a period, the landing trim's mean is about 1300-1650 samples (was
 * 40-250; 88 % of old landings trimmed nothing), at most about 2400. And it is NOT masked: the landing
 * runs after the first audible hand-off (handed == mute + 1, p->mute == 0), READY holds ahead-1 chunks
 * built before the cut, so the splice it makes falls about `ahead` chunks (31.25 ms each) after the mute
 * ends and skips 20-30 ms of content. The claims elsewhere in this file that the trim is masked were
 * never checked against the hardware, whose trim size was not logged before RUN 53 (`trim=` in
 * V28_SWEEPM). The sweep's own gate cannot see a splice (UNMASKED needs a begin discard, the sweep passes
 * none). Removing it needs the level set in silence at least `ahead` rotations before the landing, a
 * redesign, not this change. Not visible to any host test before Issue #136: they feed the ring exactly
 * the DMA's rate at 16 calls per period, where the ring at every period start is target
 * (tests/unit/test_v28_sweep_landing.c is the hardware's cadence and feed).
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

#define GBP_ATRANS2_AIM (GBP_APLAY2_PUSHES / 2u)

/* Issue #136: the last period's rotation starts only from target + this; see the paragraph above. */
#define GBP_ATRANS2_LAST_MARGIN (GBP_APLAY2_BAND * 2u)

/* gbp_atrans2_step() calls a full hand-off period holds under the default per-call cadence
 * (GBP_APLAY2_STEP_PUSHES, unhooked -- see gbp_aplay2.h's own step_pushes hook, not used by any
 * #128/#129 handler): the SAME quantity a fresh ROTATE production needs to complete one chunk, so
 * comparing the two is exact arithmetic on this module's own accounting, not a tuned constant. */
#define GBP_ATRANS2_CALLS_PER_HANDOFF (GBP_APLAY2_PUSHES / GBP_APLAY2_STEP_PUSHES)

struct gbp_atrans2 {
    uint8_t  active;
    uint8_t  mode;                    /* enum gbp_atrans2_mode */
    uint8_t  reached;                 /* the ring reached the level once (informational) */
    uint8_t  discarding;              /* HELD: a discard chunk of the executor's own is under way */
    uint8_t  rotating;                /* ROTATE: a rotation chunk is under way */
    uint8_t  discard_pending;         /* HELD: the shallowing discard, deferred until the queue is whole */
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
