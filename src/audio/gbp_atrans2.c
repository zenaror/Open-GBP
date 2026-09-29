/* gbp_atrans2 — the transition executor, ported onto the native path (see gbp_atrans2.h / gbp_atrans.h). */
#include <string.h>
#include "gbp_atrans2.h"

void gbp_atrans2_init(struct gbp_atrans2 *t)
{
    memset(t, 0, sizeof *t);
}

uint32_t gbp_atrans2_handoffs(const struct gbp_atrans2 *t, const struct gbp_aplay2 *p)
{
    return p->handed - t->handed_at_start;
}

uint32_t gbp_atrans2_min_mute(uint8_t mode, uint32_t pause, uint32_t ahead)
{
    return mode == GBP_ATRANS2_ROTATE ? pause + ahead : mode == GBP_ATRANS2_HELD ? pause + 1u : 0u;
}

int gbp_atrans2_begin(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint64_t now, uint8_t mode,
                      uint32_t mute, uint32_t pause, uint32_t discard, uint32_t target, uint32_t ahead)
{
    uint32_t need, old_ahead, k;
    if (t->active) { t->begin_refused_active++; return 0; }   /* #117 entry 21, one level down (#129/#130) */
    if (ahead < 1u || ahead > GBP_APLAY2_POOL) {               /* corrected, never a hard refusal (like mute below) */
        t->faults++;
        if (ahead < 1u) ahead = 1u;
        if (ahead > GBP_APLAY2_POOL) ahead = GBP_APLAY2_POOL;
    }
    need = gbp_atrans2_min_mute(mode, pause, ahead);
    if (mode == GBP_ATRANS2_UNMUTED) mute = 0u;
    else if (mute < need) { t->faults++; mute = need; }
    t->active = 1u;
    t->mode = mode;
    t->reached = t->discarding = t->rotating = 0u;
    t->mute = mute;
    t->pause = pause;
    t->discard = discard;
    t->discard_pending = (uint8_t)((mode == GBP_ATRANS2_HELD && discard) ? 1u : 0u);
    t->target = target;
    t->handed_at_start = p->handed;
    t->discards = t->rotations = t->topped = t->trimmed = t->short_by = t->handed_seen = t->ahead_drops = 0u;
    t->handed_last = 0u;
    t->calls_in_period = 0u;
    t->residue = 0;
    t->late = t->unmasked = 0u;
    t->adjusted = 0u;
    t->disc_n = t->rot_post = t->fill_short = t->calls_prev = t->to_build = t->dropped_pre = t->old_chunks = 0u;
    t->disc_rel = GBP_ATRANS2_NO_CUT;
    t->t_start = now;
    t->t_reached = t->t_end = 0u;
    t->begun++;
    gbp_aplay2_set_target(p, target);
    if (mute) gbp_aplay2_mute(p, mute);
    if (discard && mode != GBP_ATRANS2_HELD) (void)gbp_adec2_discard(d, discard);
    old_ahead = p->ahead;
    p->ahead = ahead;
    /* §V28's own step mechanism: a step LOWERING ahead drops the surplus READY fronts, without
     * replacement, right here, under the mute -- gbp_atrans2.h's own invariant, applied inside the
     * one place ahead ever changes. Never for HELD (retired for steps, #128's own review). */
    if (ahead < old_ahead && mode != GBP_ATRANS2_HELD)
        for (k = ahead; k < old_ahead; k++)
            if (gbp_aplay2_drop_front(p) >= 0) t->ahead_drops++;
    return 1;
}

static int finish2(struct gbp_atrans2 *t, uint64_t now)
{
    t->active = 0u;
    t->t_end = now;
    t->completed++;
    return 1;
}

/* ---- 1. ROTATE ------------------------------------------------------------------------ */

/* Issue #136: the ring's level is set INSIDE the mute, once, and every chunk that will be heard is
 * built after it. See gbp_atrans2.h ("THE ROTATE LEVEL IS SET IN SILENCE"). */

/* Issue #138: the bias that puts the LANDING at GBP_ATRANS2_LAND_POINT below target whatever the production step: the landing call's own recovery
 * is one production call, `step` pushes, and the bias is the rest of the point. The step is the one gbp_aplay2 will take for the next chunk (the
 * hook's answer, or its default), clamped exactly as gbp_aplay2.c clamps it. With the default 128 this is 32, the value RUN 53 validated. */
static uint32_t land_bias(const struct gbp_aplay2 *p)
{
    uint32_t step = p->step_pushes ? p->step_pushes(p->step_pushes_user, p->produced) : GBP_APLAY2_STEP_PUSHES;
    if (step == 0u || step > GBP_APLAY2_PUSHES) step = GBP_APLAY2_STEP_PUSHES;
    return GBP_ATRANS2_LAND_POINT > step ? GBP_ATRANS2_LAND_POINT - step : 0u;
}

static void adjust2(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint32_t handed, uint64_t now)
{
    /* how far into the current hand-off period we are, in samples of inflow already gone: from the hand-off
     * instants when the chain has two of them (the callback's own clock, so a late pump call is measured,
     * not guessed), else from the call counts */
    const uint32_t h_expected = t->handed_at_start + handed;   /* the hand-off count `handed` was taken at */
    const uint64_t tl = p->t_ho_last, tp = p->t_ho_prev;
    uint32_t frac_done;
    uint32_t want;
    uint64_t inflow;
    if (tp != 0u && tl > tp && now >= tl) {
        const uint64_t f = (uint64_t)GBP_APLAY2_PUSHES * (now - tl) / (tl - tp);
        frac_done = f < GBP_APLAY2_PUSHES ? (uint32_t)f : GBP_APLAY2_PUSHES;
    } else if (t->calls_in_period > 1u && t->calls_prev > 0u) {
        const uint64_t f = (uint64_t)(t->calls_in_period - 1u) * GBP_APLAY2_PUSHES / t->calls_prev;
        frac_done = f < GBP_APLAY2_PUSHES ? (uint32_t)f : GBP_APLAY2_PUSHES;
    } else {
        frac_done = 0u;
    }
    if (p->handed != h_expected) return;        /* a hand-off landed since `handed` was read: try again next call */
    /* the ring the sequence must start from so that, after `ahead` whole-chunk builds and the inflow until the
     * landing call, it lands on target (the landing call's own recovery is left to the band) */
    inflow = (uint64_t)(t->mute + 1u - handed) * GBP_APLAY2_PUSHES - frac_done;   /* nominal: one PUSHES a period */
    {
        /* signed: at AHEAD 1 and a low target the ring the sequence needs at the cut is below zero (the inflow of
         * the two tail periods alone exceeds target + one chunk), i.e. cut the ring empty */
        const int64_t w = (int64_t)t->target + (int64_t)p->ahead * GBP_APLAY2_PUSHES - (int64_t)inflow
                        - (int64_t)land_bias(p);
        want = w > 0 ? (uint32_t)w : 0u;
    }
    t->adjusted = 1u;
    t->disc_rel = (int32_t)handed - (int32_t)t->mute - 1;
    if (d->count > want) {
        t->disc_n = gbp_adec2_discard(d, d->count - want);
    } else if (d->count < want) {
        t->fill_short = want - d->count;       /* the mute was too short to fill the ring: counted, never hidden */
        t->fill_shorts++;
    }
    /* `ahead` chunks are built from the ring, cut or not, each REPLACING the oldest queued one (the oldest is freed
     * unplayed, silent: the callback is still handing silence, then the caller queues the new one), exactly the old
     * rotation, so the queue is not left empty for the unmute by a build that is merely late. After a cut every chunk queued now was built
     * BEFORE it and none may be heard: they are all gone once `ahead` builds are done. With no cut the level accounting
     * above still assumes `ahead` builds, so a ring that lacked the material lands short by exactly what it lacked,
     * never above target. */
    t->old_chunks = gbp_aplay2_ready(p);
    t->to_build = p->ahead;
}

/* one build finished (a chunk the caller must queue): it replaces the oldest chunk queued before the level was set */
static void built2(struct gbp_atrans2 *t, struct gbp_aplay2 *p, int32_t b, int *to_queue)
{
    t->rotating = 0u;
    t->rot_post++;
    t->rotations++;
    if (t->old_chunks > 0u && gbp_aplay2_drop_front(p) >= 0) { t->old_chunks--; t->dropped_pre++; }
    *to_queue = b;
}

static int step_rotate2(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint64_t now,
                        uint32_t handed, int *to_queue)
{
    if (handed > t->mute) {
        if (t->rotating) { t->rotating = 0u; t->late = 1u; t->lates++; }
        /* the landing call itself must not waste its own slot (Orchestrator, #129/#130, traced to
         * the exact call, not assumed): this call is what finishes the transition, so the
         * CALLER'S OWN dispatch (`if (t->active) step() else produce()`) never reaches
         * `gbp_aplay2_produce()` for it -- ordinary production only starts NEXT call. Steady-state
         * running never loses a call this way (every call is a produce() call); a landing does,
         * exactly once, and only here. For AHEAD >= 2 the spare chunks (`ahead - 1 >= 1`) absorb a
         * rebuild that starts one call late without consequence; AHEAD 1's own floor is 0 -- no
         * chunk to spare -- so the SAME one-call-late rebuild finishes one call short when the very
         * next hand-off needs it (proven: gbp_v28_sweep's own entry 6, its rebuild ran the expected
         * 16 calls (32 at the 64-push steady step) at the expected rate, starting one call later than a
         * steady rebuild ever does). Recovering that one call here -- an ordinary, CORRECTED
         * production attempt, the exact call the caller's own dispatch would have made one tick
         * later -- lands this call's own slot back on the steady phase, not one behind it. */
        if (*to_queue < 0) *to_queue = gbp_aplay2_produce(p, d);
        /* NOTHING is cut here: the landing runs after the first audible hand-off, so any discard now would
         * be heard, `ahead` chunks later (Issue #136). The level was set in silence; what is measured
         * below is what that left. */
        if (t->disc_n > 0u && t->old_chunks > 0u) { t->unmasked = 1u; t->unmaskeds++; }   /* a pre-cut chunk would be heard */
        if (!t->adjusted) t->unadjusted++;
        t->residue = (int32_t)d->count + (p->cur >= 0 ? (int32_t)p->cur_pushes : 0)
                   + (int32_t)GBP_APLAY2_PUSHES * ((int32_t)gbp_aplay2_ready(p) - (int32_t)(p->ahead - 1u))
                   - (int32_t)t->target;
        if (t->rotate_landings == 0u || t->residue < t->residue_min) t->residue_min = t->residue;
        if (t->rotate_landings == 0u || t->residue > t->residue_max) t->residue_max = t->residue;
        t->rotate_landings++;
        if (t->discard > 0u && t->rotations < p->ahead) { t->unmasked = 1u; t->unmaskeds++; }
        return finish2(t, now);
    }
    if (t->rotating) {
        const int32_t b = gbp_aplay2_produce_uncorrected(p, d);
        if (b >= 0) built2(t, p, b, to_queue);
        return 0;
    }
    if (!t->reached && d->count >= t->target) { t->reached = 1u; t->t_reached = now; }
    /* Until the second-to-last hand-off period nothing is consumed: the ring only fills, which is silent and
     * never a discontinuity. Then, with nothing in flight, the level is set (one discard, in silence) and the
     * chunks that will be heard are built from the cut ring. The cut also comes early if the ring is about
     * to fill (the feed's newest samples would be lost, a gap heard later, its moment depending on TARGET). */
    if (!t->adjusted) {
        if (p->cur >= 0) {
            /* a chunk the ordinary producer had started before the plan began: finish it (queued, and if a cut
             * follows it is freed with the rest) -- the cut waits for nothing in flight */
            const int32_t b = gbp_aplay2_produce_uncorrected(p, d);
            if (b >= 0) *to_queue = b;
        } else if (handed + 1u >= t->mute || d->count + 2u * GBP_APLAY2_PUSHES >= d->cap) {
            adjust2(t, p, d, handed, now);
        }
        return 0;
    }
    if (t->rot_post < t->to_build && d->count > GBP_APLAY2_PUSHES) {
        const int32_t b = gbp_aplay2_produce_uncorrected(p, d);
        t->rotating = 1u;
        if (b >= 0) built2(t, p, b, to_queue);
    }
    return 0;
}

/* ---- 2. HELD -------------------------------------------------------------------------- */

static int step_held2(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint64_t now,
                      uint32_t handed, int *to_queue)
{
    if (handed > t->mute) {
        const uint32_t taken = t->discarding ? p->cur_pushes : 0u;
        uint32_t base;
        if (t->discard_pending) { (void)gbp_adec2_discard(d, t->discard); t->discard_pending = 0u; }
        if (t->discarding) { t->discarding = 0u; t->converted++; }
        base = d->count + taken;
        if (base > t->target) {
            t->trimmed = gbp_adec2_discard(d, base - t->target);
        } else if (base < t->target) {
            t->short_by = t->target - base;
            t->shorts++;
            if (t->short_by > t->short_max) t->short_max = t->short_by;
        }
        t->trim_sum += t->trimmed;
        if (t->trimmed > t->trim_max) t->trim_max = t->trimmed;
        return finish2(t, now);
    }
    if (t->discarding) {
        if (gbp_aplay2_produce_discard(p, d) < 0) return 0;
        t->discarding = 0u;
        t->discards++;
    }
    if (gbp_aplay2_ready(p) < p->ahead) {
        const int32_t b = gbp_aplay2_produce_uncorrected(p, d);
        if (b >= 0) { *to_queue = b; t->topped++; }
        return 0;
    }
    if (t->discard_pending) {
        (void)gbp_adec2_discard(d, t->discard);
        t->discard_pending = 0u;
    }
    if (!t->reached) {
        if (d->count < t->target) return 0;
        t->reached = 1u;
        t->t_reached = now;
    }
    if (d->count >= t->target + GBP_APLAY2_PUSHES) {
        t->discarding = 1u;
        if (gbp_aplay2_produce_discard(p, d) >= 0) { t->discarding = 0u; t->discards++; }
    }
    return 0;
}

int gbp_atrans2_step(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint64_t now, int *to_queue)
{
    uint32_t handed;
    *to_queue = -1;
    if (!t->active) return 0;
    handed = gbp_atrans2_handoffs(t, p);
    t->handed_seen = handed;
    /* a hand-off boundary just passed (or this is the first call): the period's own call count
     * restarts, THIS call being its first (see gbp_atrans2.h's own calls_in_period comment) */
    if (handed != t->handed_last) { t->calls_prev = t->calls_in_period; t->calls_in_period = 0u; t->handed_last = handed; }
    t->calls_in_period++;
    if (t->mode == GBP_ATRANS2_ROTATE) return step_rotate2(t, p, d, now, handed, to_queue);
    if (t->mode == GBP_ATRANS2_HELD) return step_held2(t, p, d, now, handed, to_queue);
    /* 3. UNMUTED: target and discard at begin; the band decides the rest. Done at once. */
    t->reached = 1u;
    t->t_reached = now;
    return finish2(t, now);
}
