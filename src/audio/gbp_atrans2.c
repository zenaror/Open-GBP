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
    t->disc_n = t->rot_post = t->fill_short = t->calls_prev = 0u;
    t->disc_rel = 0;
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

static void rotated2(struct gbp_atrans2 *t, struct gbp_aplay2 *p, int32_t b, int *to_queue)
{
    t->rotating = 0u;
    if (gbp_aplay2_drop_front(p) >= 0) t->rotations++;
    else { t->late = 1u; t->lates++; }
    *to_queue = b;
}

/* ---- 1. ROTATE ------------------------------------------------------------------------ */

/* Issue #136: the ring's level is set INSIDE the mute, once, and every chunk that will be heard is
 * built after it. See gbp_atrans2.h ("THE ROTATE LEVEL IS SET IN SILENCE"). */
static void adjust2(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint32_t handed, uint64_t now)
{
    /* how far into the current hand-off period we are, in samples of inflow already gone: from the hand-off
     * instants when the chain has two of them (the callback's own clock, so a late pump call is measured,
     * not guessed), else from the call counts */
    const uint32_t h_before = p->handed;
    const uint64_t tl = p->t_ho_last, tp = p->t_ho_prev;
    uint32_t frac_done;
    uint32_t inflow, want;
    if (tp != 0u && tl > tp && now >= tl) {
        const uint64_t f = (uint64_t)GBP_APLAY2_PUSHES * (now - tl) / (tl - tp);
        frac_done = f < GBP_APLAY2_PUSHES ? (uint32_t)f : GBP_APLAY2_PUSHES;
    } else if (t->calls_in_period > 1u && t->calls_prev > 0u) {
        const uint64_t f = (uint64_t)(t->calls_in_period - 1u) * GBP_APLAY2_PUSHES / t->calls_prev;
        frac_done = f < GBP_APLAY2_PUSHES ? (uint32_t)f : GBP_APLAY2_PUSHES;
    } else {
        frac_done = 0u;
    }
    if (p->handed != h_before) return;         /* a hand-off landed while reading: try again next call */
    /* the ring the sequence must start from so that, after `ahead` whole-chunk rotations and the inflow
     * until the landing call, it lands on target (the landing call's own recovery is left to the band) */
    inflow = (t->mute + 1u - handed) * GBP_APLAY2_PUSHES - frac_done;
    {
        /* signed: at AHEAD 1 and a low target the ring the sequence needs at the cut is below zero (the inflow of
         * the two tail periods alone exceeds target + one chunk), i.e. cut the ring empty */
        const int64_t w = (int64_t)t->target + (int64_t)p->ahead * GBP_APLAY2_PUSHES - (int64_t)inflow
                        - (int64_t)GBP_ATRANS2_LAND_BIAS;
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
         * 16 calls at the expected rate, starting one call later than a
         * steady rebuild ever does). Recovering that one call here -- an ordinary, CORRECTED
         * production attempt, the exact call the caller's own dispatch would have made one tick
         * later -- lands this call's own slot back on the steady phase, not one behind it. */
        if (*to_queue < 0) *to_queue = gbp_aplay2_produce(p, d);
        /* NOTHING is cut here: the landing runs after the first audible hand-off, so any discard now would
         * be heard, `ahead` chunks later (Issue #136). The level was set in silence; what is measured
         * below is what that left. */
        if (t->disc_n > 0u && t->rot_post < p->ahead) { t->unmasked = 1u; t->unmaskeds++; }
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
        if (b >= 0) { rotated2(t, p, b, to_queue); if (t->adjusted) t->rot_post++; }
        return 0;
    }
    if (gbp_aplay2_ready(p) < p->ahead) {
        const int32_t b = gbp_aplay2_produce_uncorrected(p, d);
        if (b >= 0) { *to_queue = b; t->topped++; }
        return 0;
    }
    if (!t->reached && d->count >= t->target) { t->reached = 1u; t->t_reached = now; }
    /* Before the last two hand-off periods nothing is consumed: the ring only fills, which is silent and
     * never a discontinuity. In the second-to-last period, with nothing in flight and the queue whole,
     * the level is set (one discard, in silence) and then `ahead` rotations follow, each building a chunk
     * from the already-correct ring and dropping the oldest queued one, so that every chunk that will be
     * heard is built after the cut. */
    if (!t->adjusted) {
        if (handed + 1u >= t->mute && p->cur < 0) adjust2(t, p, d, handed, now);
        return 0;
    }
    if (t->rot_post < p->ahead) {
        const int32_t b = gbp_aplay2_produce_uncorrected(p, d);
        t->rotating = 1u;
        if (b >= 0) { rotated2(t, p, b, to_queue); t->rot_post++; }
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
