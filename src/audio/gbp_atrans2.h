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
    uint32_t trimmed;                 /* HELD: samples dropped at the landing */
    int32_t  residue;                 /* ROTATE: the effective level minus the target at the landing, left to the band */
    uint8_t  late;                    /* ROTATE: a rotation under way when the silence ended, queued undropped */
    uint8_t  unmasked;                /* ROTATE: a shallowing's pre-splice chunk still in READY (discard, < AHEAD rotations) */
    uint32_t short_by;                /* HELD: samples the ring lay below the level at the landing */
    uint32_t handed_seen;
    uint64_t t_start, t_reached, t_end;
    /* since init */
    uint32_t begun, completed;
    uint32_t faults;                  /* plans whose mute could not fit their mechanism (never; counted, raised) */
    uint32_t begin_refused_active;    /* a begin() while already active: refused, counted, nothing touched */
    uint32_t trim_max, trim_sum;      /* HELD */
    uint32_t shorts, short_max;       /* HELD: landings below the level */
    uint32_t converted;               /* HELD: landings that turned a discard under way into the refill */
    uint32_t rotate_landings, lates, unmaskeds;   /* ROTATE */
    int32_t  residue_min, residue_max;            /* ROTATE, over its landings */
};

void gbp_atrans2_init(struct gbp_atrans2 *t);

/* the mute a mechanism needs for a climb of `pause` chunks: ROTATE pause + GBP_APLAY2_AHEAD,
 * HELD pause + 1, UNMUTED 0 */
uint32_t gbp_atrans2_min_mute(uint8_t mode, uint32_t pause);

/* Apply a plan now. Returns 1 when applied, or 0 when refused because a transition is already
 * active (begin_refused_active counts it; nothing about the running transition is touched). */
int gbp_atrans2_begin(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint64_t now, uint8_t mode,
                      uint32_t mute, uint32_t pause, uint32_t discard, uint32_t target);

/* One pump call while active. Returns 1 on the call that completes the plan, else 0. `*to_queue` is
 * set to a produced chunk the CALLER must flush and queue, else -1. */
int gbp_atrans2_step(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint64_t now, int *to_queue);

/* hand-offs since the plan began (silence or audio alike) */
uint32_t gbp_atrans2_handoffs(const struct gbp_atrans2 *t, const struct gbp_aplay2 *p);

#ifdef __cplusplus
}
#endif

#endif
