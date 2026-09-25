/* gbp_atrans — the latency round's transition executor (see gbp_atrans.h). */
#include <string.h>
#include "gbp_atrans.h"

void gbp_atrans_init(struct gbp_atrans *t)
{
    memset(t, 0, sizeof *t);
}

uint32_t gbp_atrans_handoffs(const struct gbp_atrans *t, const struct gbp_aplay *p)
{
    return p->handed - t->handed_at_start;
}

uint32_t gbp_atrans_min_mute(uint8_t mode, uint32_t pause)
{
    return mode == GBP_ATRANS_ROTATE ? pause + GBP_APLAY_AHEAD : mode == GBP_ATRANS_HELD ? pause + 1u : 0u;
}

void gbp_atrans_begin(struct gbp_atrans *t, struct gbp_aplay *p, struct gbp_adec *d, uint64_t now, uint8_t mode,
                      uint32_t mute, uint32_t pause, uint32_t discard, uint32_t target)
{
    const uint32_t need = gbp_atrans_min_mute(mode, pause);
    if (mode == GBP_ATRANS_UNMUTED) mute = 0u;
    else if (mute < need) { t->faults++; mute = need; }   /* gbp_async's make_plan holds it: never */
    t->active = 1u;
    t->mode = mode;
    t->reached = t->discarding = t->rotating = 0u;
    t->mute = mute;
    t->pause = pause;
    t->discard = discard;
    t->discard_pending = (uint8_t)((mode == GBP_ATRANS_HELD && discard) ? 1u : 0u);
    t->target = target;
    t->handed_at_start = p->handed;
    t->discards = t->rotations = t->topped = t->trimmed = t->short_by = t->handed_seen = 0u;
    t->residue = 0;
    t->late = t->unmasked = 0u;
    t->t_start = now;
    t->t_reached = t->t_end = 0u;
    t->begun++;
    gbp_aplay_set_target(p, target);
    if (mute) gbp_aplay_mute(p, mute);
    /* ROTATE and UNMUTED: the shallowing discard at once (ROTATE's rotations then carry the splice to the
     * front, inside the silence); HELD defers it until its queue is whole */
    if (discard && mode != GBP_ATRANS_HELD) (void)gbp_adec_discard(d, discard);
}

static int finish(struct gbp_atrans *t, uint64_t now)
{
    t->active = 0u;
    t->t_end = now;
    t->completed++;
    return 1;
}

/* a rotation's chunk is complete: the front leaves if the next hand-off is still silent */
static void rotated(struct gbp_atrans *t, struct gbp_aplay *p, int b, int *to_queue)
{
    t->rotating = 0u;
    if (gbp_aplay_drop_front(p) >= 0) t->rotations++;
    else { t->late = 1u; t->lates++; }                    /* the silence ended under it: queued undropped */
    *to_queue = b;
}

/* ---- 1. ROTATE ------------------------------------------------------------------------ */

static int step_rotate(struct gbp_atrans *t, struct gbp_aplay *p, struct gbp_adec *d, uint64_t now, uint32_t handed,
                       int *to_queue)
{
    /* THE LANDING: the first audible hand-off has come. No trim: the residue is the band's. */
    if (handed > t->mute) {
        if (t->rotating) { t->rotating = 0u; t->late = 1u; t->lates++; }   /* the producer finishes and queues it */
        /* the residue is the EFFECTIVE level -- the ring, a chunk under way's taken pushes, and READY beyond
         * the AHEAD - 1 an audible hand-off leaves -- minus the target: a late rotation queued undropped
         * leaves READY one chunk long, which the ring alone does not show (review round 3) */
        t->residue = (int32_t)d->count + (p->cur >= 0 ? (int32_t)p->cur_pushes : 0)
                   + (int32_t)GBP_APLAY_PUSHES * ((int32_t)gbp_aplay_ready(p) - (int32_t)(GBP_APLAY_AHEAD - 1u))
                   - (int32_t)t->target;
        if (t->rotate_landings == 0u || t->residue < t->residue_min) t->residue_min = t->residue;
        if (t->rotate_landings == 0u || t->residue > t->residue_max) t->residue_max = t->residue;
        t->rotate_landings++;
        /* NOT MASKED only when a pre-splice chunk can still be in READY: a begin discard (a shallowing) put a
         * splice behind the held chunks, and fewer than AHEAD fronts have left since. With no discard, READY
         * and the ring are one contiguous run whatever the rotations: the skip is the dropped fronts, right
         * after the pause. A late rotation joins READY's back contiguously: it unmasks nothing. */
        if (t->discard > 0u && t->rotations < GBP_APLAY_AHEAD) { t->unmasked = 1u; t->unmaskeds++; }
        return finish(t, now);
    }
    if (t->rotating) {                                   /* a rotation under way: continue it */
        const int b = gbp_aplay_produce_uncorrected(p, d);
        if (b >= 0) rotated(t, p, b, to_queue);
        return 0;
    }
    /* the held queue first: a refill under way at begin is finished into it -- uncorrected: a chunk
     * started now would decide its DUP/DROP against the NEW level and put a spurious sample into (or out
     * of) the held content (conservation, below, caught it at phase 0); one already under way keeps the
     * correction it decided before the plan, against the old level */
    if (gbp_aplay_ready(p) < GBP_APLAY_AHEAD) {
        const int b = gbp_aplay_produce_uncorrected(p, d);
        if (b >= 0) { *to_queue = b; t->topped++; }
        return 0;
    }
    if (!t->reached && d->count >= t->target) { t->reached = 1u; t->t_reached = now; }
    /* THE AIM: +64 while two or more silent hand-offs remain; -64 while one remains (the last period's
     * chunk of feed arrives after the last rotation can be made); none once the next hand-off is audible.
     * Below the aim the producer is idle: the climb. */
    if (p->mute >= 1u) {
        const uint32_t aim = p->mute >= 2u ? t->target + GBP_ATRANS_AIM
                                           : (t->target > GBP_ATRANS_AIM ? t->target - GBP_ATRANS_AIM : 0u);
        if (d->count >= aim) {
            const int b = gbp_aplay_produce_uncorrected(p, d);
            t->rotating = 1u;
            if (b >= 0) rotated(t, p, b, to_queue);
        }
    }
    return 0;
}

/* ---- 2. HELD -------------------------------------------------------------------------- */

static int step_held(struct gbp_atrans *t, struct gbp_aplay *p, struct gbp_adec *d, uint64_t now, uint32_t handed,
                     int *to_queue)
{
    /* THE LANDING, on the first pump call after the first AUDIBLE hand-off: a discard under way is
     * CONVERTED into the refill that hand-off calls for (waiting for it started the refill ~15 pump calls
     * late, on ~16 samples of feed, and the band DROPped: the phase sweep); the level is what the refill
     * sees at its start -- the ring plus what the chunk has taken; the excess over the target is dropped
     * from the ring's head, joining the splice the discards made there (after READY: HELD's splice). */
    if (handed > t->mute) {
        const uint32_t taken = t->discarding ? p->cur_pushes : 0u;
        uint32_t base;
        if (t->discard_pending) { (void)gbp_adec_discard(d, t->discard); t->discard_pending = 0u; }
        if (t->discarding) { t->discarding = 0u; t->converted++; }
        base = d->count + taken;
        if (base > t->target) {
            t->trimmed = gbp_adec_discard(d, base - t->target);
        } else if (base < t->target) {
            t->short_by = t->target - base;              /* the climb did not finish: the band takes it */
            t->shorts++;
            if (t->short_by > t->short_max) t->short_max = t->short_by;
        }
        t->trim_sum += t->trimmed;
        if (t->trimmed > t->trim_max) t->trim_max = t->trimmed;
        return finish(t, now);
    }
    if (t->discarding) {                                 /* a discard chunk under way: continue it */
        if (gbp_aplay_produce_discard(p, d) < 0) return 0;
        t->discarding = 0u;
        t->discards++;
    }
    /* the held queue first: a refill under way at begin is finished into it (contiguous held content),
     * uncorrected, as ROTATE's */
    if (gbp_aplay_ready(p) < GBP_APLAY_AHEAD) {
        const int b = gbp_aplay_produce_uncorrected(p, d);
        if (b >= 0) { *to_queue = b; t->topped++; }
        return 0;
    }
    if (t->discard_pending) {                            /* the shallowing discard, once the queue is whole */
        (void)gbp_adec_discard(d, t->discard);
        t->discard_pending = 0u;
    }
    if (!t->reached) {
        if (d->count < t->target) return 0;             /* THE CLIMB */
        t->reached = 1u;
        t->t_reached = now;
    }
    /* THE LEVEL, under silence: one chunk out whenever the ring holds a whole chunk above the level (counting
     * discards per hand-off missed the period the level was reached in and left a whole chunk: the sweep) */
    if (d->count >= t->target + GBP_APLAY_PUSHES) {
        t->discarding = 1u;
        if (gbp_aplay_produce_discard(p, d) >= 0) { t->discarding = 0u; t->discards++; }
    }
    return 0;
}

int gbp_atrans_step(struct gbp_atrans *t, struct gbp_aplay *p, struct gbp_adec *d, uint64_t now, int *to_queue)
{
    uint32_t handed;
    *to_queue = -1;
    if (!t->active) return 0;
    handed = gbp_atrans_handoffs(t, p);
    t->handed_seen = handed;
    if (t->mode == GBP_ATRANS_ROTATE) return step_rotate(t, p, d, now, handed, to_queue);
    if (t->mode == GBP_ATRANS_HELD) return step_held(t, p, d, now, handed, to_queue);
    /* 3. UNMUTED (Phase 3): target and discard at begin; the band decides the rest. Done at once. */
    t->reached = 1u;
    t->t_reached = now;
    return finish(t, now);
}
