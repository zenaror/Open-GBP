/*
 * gbp_atrans — the transition executor of the latency round (GitHub Issue #117,
 * HARDWARE_TESTS §V27.13-§V27.15, sync-0001): a gbp_async TRANSITION PLAN applied
 * to the chain (gbp_aplay) and the decoder's ring (gbp_adec), one pump call at a
 * time. THREE MECHANISMS, by the plan's kind -- recorded apart, so that an
 * artefact of one is never attributed to another (§V27.15):
 *
 * 1. ROTATE -- Phase 1's switches (REAL and NULL alike) and Phase 2's STARTs
 *    (§V27.15's (A)). The splice falls INSIDE the silence: no artefact.
 *      at begin    the target is set; `mute` chunks of silence are asked for
 *                  (gbp_aplay_mute: silent hand-offs never dequeue READY); a
 *                  shallowing's `discard` leaves the ring's head at once;
 *      the queue   a plan begun between a hand-off and its refill finds READY at
 *                  AHEAD - 1: the refill is finished into it first, uncorrected (a
 *                  correction decided against the NEW level would put a spurious
 *                  sample into the held content);
 *      the climb   while the ring is under the aim the producer is idle and the
 *                  feed raises it (never a slew);
 *      rotation    under silence, whenever the ring holds the aim or more, ONE
 *                  fresh chunk is produced from the ring's head (uncorrected:
 *                  exactly 128) and joins the BACK of READY while the FRONT
 *                  chunk is dropped unplayed (gbp_aplay_drop_front, only while
 *                  the callback's next hand-off is silent). After AHEAD
 *                  rotations every chunk held before the plan -- and whatever
 *                  the begin's discard spliced behind them -- has left from the
 *                  front: READY is contiguous with the ring, and everything
 *                  skipped lies between the pause and READY's first sample,
 *                  i.e. inside the silence. With no begin discard (a deepening,
 *                  a null) READY and the ring are one contiguous run whatever the
 *                  rotations -- the skip is the dropped fronts, right after the
 *                  pause -- so only a shallowing with fewer than AHEAD rotations
 *                  at the landing is NOT masked, counted (unmasked);
 *      the aim     target + 64 while two or more silent hand-offs remain; target
 *                  - 64 while one remains, because the final silent period's
 *                  chunk of feed arrives after the last rotation can be made --
 *                  the ring meets the first audible hand-off within about
 *                  +/- 64 of the level;
 *      the landing on the first pump call after the first AUDIBLE hand-off: no
 *                  trim (it would splice after READY, audibly); the residue
 *                  (signed) is left to gbp_aplay's band, whose corrections are
 *                  one sample a chunk -- the chain's normal operation. A
 *                  rotation still under way then (late) is queued undropped: it
 *                  joins READY's back contiguously (still masked) and READY is one
 *                  chunk long, which the residue -- the EFFECTIVE level: the ring,
 *                  a chunk under way, READY beyond AHEAD - 1 -- includes. On
 *                  hardware (bursty feed, pump gaps) about 5-19 % of landings are
 *                  late (review round 3's simulation); the band DROPs the chunk.
 *      THE MUTE: the climb (pause chunks) and AHEAD rotations must fit in the
 *      feed before the last silent hand-off -- at least mute - 1 chunks at the
 *      worst phase -- less the chunk the aim leaves to the last period plus the
 *      one it takes back: mute >= pause + 4. Phase 1 at MUTE 18: 12 + 4 = 16,
 *      two chunks of margin (§V27.15); a START: max(MUTE, pause + 4), at most 29.
 *
 * 2. HELD -- Phase 2's STEPs (mute 4 cannot flush: +128 and a 4-chunk refill need
 *    640 of feed in 512). §V27.13's mechanism: READY held, the music resumes where
 *    it paused, and the skipped content is spliced out 4 x 128 samples = 125 ms
 *    after the silence, AUDIBLY (§V27.15: Phase 2 is not the blinded A/B).
 *      under silence one chunk is DISCARDED (uncorrected) whenever the ring holds
 *      a whole chunk above the level; on the first audible hand-off a discard
 *      under way is CONVERTED into the refill that hand-off calls for, the level
 *      is what that refill sees at its start (the ring plus what it has taken),
 *      and the excess over the target is dropped from the ring's head -- joining
 *      the splice there. mute >= pause + 1.
 *
 * 3. UNMUTED -- Phase 3's depths: the target is set and any shallowing discard
 *    done at begin; the plan completes at once and the producer runs on. Where
 *    the ring settles at the new target is gbp_aplay's band, which is what the
 *    dwell measures. No chase, no trim, no idle producer.
 *
 * WHY A DEEPENING OR A NULL IS CONTIGUOUS WHATEVER ITS ROTATIONS (checkable by reading,
 * not only by the sweep). Under ROTATE, content leaves the ring's head in exactly two
 * ways: into the BACK of READY (a rotation's chunk, the queue's top-up, a late chunk --
 * all produced in stream order, uncorrected) or, once, by the begin's discard (a
 * shallowing only: discard > 0). READY loses chunks only at its FRONT (the front drop,
 * the callback). A queue fed only at its back from the stream's head and drained only
 * at its front holds a contiguous run of the stream that continues into the ring: no
 * count of rotations can break that. So with no begin discard the only discontinuity is
 * between the last chunk played before the pause and READY's front after it -- the
 * dropped fronts, the earliest content after the pause -- which lies inside the silence.
 * A begin discard makes the one exception: the ring's head jumps while READY still holds
 * the chunks produced before it (at most AHEAD: the AHEAD - 1 queued and the refill that
 * may be under way, which then carries the jump inside it), so READY + ring has one
 * discontinuity behind those chunks until all of them have left from the front: exactly
 * AHEAD drops. Hence `unmasked` <=> discard > 0 AND rotations < AHEAD, and nothing else.
 *
 * THE BOUNDARY. READY's head (rq_head) belongs to the AI callback, which dequeues it
 * at every hand-off that is not silent. ROTATE touches it -- the front drop -- ONLY
 * while the callback's next hand-off is silent (gbp_aplay_drop_front refuses when
 * mute == 0): that hand-off leaves rq_head alone, and the one after it is a whole
 * chunk (31 ms) away. A rotation completing after the silence ended is queued with
 * no drop (late) rather than risk the race.
 *
 * CONSERVATION, asserted by the host test at every phase: from a plan's begin to its
 * landing, fed = played + skipped + (stock after - stock before), stock = the ring +
 * READY x 128 + a chunk under way's taken pushes. Hence, under the same silence, the
 * skips of two plans differ by exactly the latency they change (less the residues'
 * difference): null - deepen = shallow - null = 1 536. A transition that ever broke
 * it would be a defect.
 *
 * The caller flushes and queues any chunk handed back through *to_queue (the
 * executor never queues itself, so the POC keeps one flush-then-queue site).
 * On hardware the feed is bursty (whole AUDIO blocks per service cycle) and runs
 * 10.9 samples/s under the AI's consumption, so every landing is exact to the
 * feed's burst, not to the sample. tests/unit/test_gbp_atrans.c drives every
 * plan against the real gbp_aplay / gbp_adec at four hand-off phases.
 *
 * Pure over its two collaborators: no device, no printing, no allocation.
 */
#ifndef OPENGBP_GBP_ATRANS_H
#define OPENGBP_GBP_ATRANS_H

#include <stdint.h>
#include "gbp_aplay.h"
#include "gbp_adec.h"

#ifdef __cplusplus
extern "C" {
#endif

enum gbp_atrans_mode { GBP_ATRANS_UNMUTED = 0, GBP_ATRANS_HELD = 1, GBP_ATRANS_ROTATE = 2 };

#define GBP_ATRANS_AIM 64u                      /* the rotation's aim, +/- around the level (half a chunk) */

struct gbp_atrans {
    uint8_t  active;
    uint8_t  mode;                    /* enum gbp_atrans_mode */
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
    uint32_t trim_max, trim_sum;      /* HELD */
    uint32_t shorts, short_max;       /* HELD: landings below the level */
    uint32_t converted;               /* HELD: landings that turned a discard under way into the refill */
    uint32_t rotate_landings, lates, unmaskeds;   /* ROTATE */
    int32_t  residue_min, residue_max;            /* ROTATE, over its landings */
};

void gbp_atrans_init(struct gbp_atrans *t);

/* the mute a mechanism needs for a climb of `pause` chunks: ROTATE pause + 4, HELD pause + 1, UNMUTED 0 */
uint32_t gbp_atrans_min_mute(uint8_t mode, uint32_t pause);

/* Apply a plan now. */
void gbp_atrans_begin(struct gbp_atrans *t, struct gbp_aplay *p, struct gbp_adec *d, uint64_t now, uint8_t mode,
                      uint32_t mute, uint32_t pause, uint32_t discard, uint32_t target);

/* One pump call while active. Returns 1 on the call that completes the plan, else 0. `*to_queue` is
 * set to a produced chunk the CALLER must flush and queue, else -1. */
int gbp_atrans_step(struct gbp_atrans *t, struct gbp_aplay *p, struct gbp_adec *d, uint64_t now, int *to_queue);

/* hand-offs since the plan began (silence or audio alike) */
uint32_t gbp_atrans_handoffs(const struct gbp_atrans *t, const struct gbp_aplay *p);

#ifdef __cplusplus
}
#endif

#endif
