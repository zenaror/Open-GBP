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

static int step_rotate2(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint64_t now,
                        uint32_t handed, int *to_queue)
{
    if (handed > t->mute) {
        uint32_t ring_excess;
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
         * GBP_ATRANS2_CALLS_PER_HANDOFF calls at the expected rate, starting one call later than a
         * steady rebuild ever does). Recovering that one call here -- an ordinary, CORRECTED
         * production attempt, the exact call the caller's own dispatch would have made one tick
         * later -- lands this call's own slot back on the steady phase, not one behind it.
         *
         * BEFORE the trim below, not after (Orchestrator, #129/#130, a second call traced the same
         * way): the trim discards the ring's own excess down to EXACTLY target, and a landing whose
         * own TARGET equals GBP_APLAY2_PUSHES exactly (gbp_v28_3b's own anchor can be
         * GBP_V28_P3_MIN) would then present the recovery with `d->count == PUSHES`, one sample
         * short of the `PUSHES + 1` a fresh chunk needs to start at all -- not a timing gap, the
         * trim's own surplus erased before the recovery ever saw it, at every landing whose target
         * happens to sit at that exact floor. Recovering first, from whatever surplus the mute
         * itself accumulated (steady state never needs this surplus and never has it artificially
         * removed first), then trimming whatever the recovery's own consumption left behind, gives
         * the recovery the SAME chance at every legal TARGET, including the floor. */
        if (*to_queue < 0) *to_queue = gbp_aplay2_produce(p, d);
        /* Orchestrator direction, Issue #129/#130: the ring's own excess over target, trimmed at
         * the landing, never below target (a shortfall would be worse than the excess it fixes).
         * HELD already trims this way at its own landing (step_held2, above); ROTATE's landing can
         * fire mid-cycle (the continuous produce+rotate loop pinned at `aim`, ending on a wall-clock
         * hand-off count, not on the cycle's own phase) and this path's residue measures 4x the old
         * path's own (#117's 15.6 ms vs this path's ~62.5 ms worst-case), with the ring component
         * alone draining over seconds through the slow DUP/DROP corrector if left untrimmed -- long
         * enough to inflate what a nulling judgment sees. The trim is masked (inside this same
         * landing step, before the transition is reported complete) and cheap (a ring-pointer
         * advance, no resample). */
        ring_excess = d->count > t->target ? d->count - t->target : 0u;
        if (ring_excess) {
            t->trimmed = gbp_adec2_discard(d, ring_excess);
            t->trim_sum += t->trimmed;
            if (t->trimmed > t->trim_max) t->trim_max = t->trimmed;
        }
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
        if (b >= 0) rotated2(t, p, b, to_queue);
        return 0;
    }
    if (gbp_aplay2_ready(p) < p->ahead) {
        const int32_t b = gbp_aplay2_produce_uncorrected(p, d);
        if (b >= 0) { *to_queue = b; t->topped++; }
        return 0;
    }
    if (!t->reached && d->count >= t->target) { t->reached = 1u; t->t_reached = now; }
    /* a NEW rotation may only START if the calls left before the landing check are at least the
     * calls one needs to finish (Orchestrator, #129/#130) -- exact arithmetic over this module's
     * own accounting (`calls_in_period`/`handed`/`t->mute`), not a tuned bound and not `p->mute`'s
     * own timing: measured first (a real cascade drove entry 6's own last natural rotation start to
     * EXACTLY `GBP_ATRANS2_CALLS_PER_HANDOFF` calls of window left, margin 0 -- a coarser
     * `handed < t->mute` gate would have refused that exact, sufficient start, which is why this is
     * counted in calls, not periods). Starting one anyway and having it still mid-flight at landing
     * would lose whatever it already consumed -- the landing branch above only resets `rotating`,
     * it never completes or drops an abandoned one. An ALREADY-rotating chunk (`t->rotating`,
     * above) is UNGATED and unaffected -- this only decides whether a NEW one may start. */
    {
        const uint32_t calls_left_this_period = t->calls_in_period <= GBP_ATRANS2_CALLS_PER_HANDOFF
                                               ? GBP_ATRANS2_CALLS_PER_HANDOFF - t->calls_in_period + 1u : 0u;
        const uint32_t window_left = calls_left_this_period
                                    + GBP_ATRANS2_CALLS_PER_HANDOFF * (t->mute - handed);
        if (window_left >= GBP_ATRANS2_CALLS_PER_HANDOFF) {
            const uint32_t aim = p->mute >= 2u ? t->target + GBP_ATRANS2_AIM
                                               : (t->target > GBP_ATRANS2_AIM ? t->target - GBP_ATRANS2_AIM : 0u);
            if (d->count >= aim) {
                const int32_t b = gbp_aplay2_produce_uncorrected(p, d);
                t->rotating = 1u;
                if (b >= 0) rotated2(t, p, b, to_queue);
            }
        }
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
    if (handed != t->handed_last) { t->calls_in_period = 0u; t->handed_last = handed; }
    t->calls_in_period++;
    if (t->mode == GBP_ATRANS2_ROTATE) return step_rotate2(t, p, d, now, handed, to_queue);
    if (t->mode == GBP_ATRANS2_HELD) return step_held2(t, p, d, now, handed, to_queue);
    /* 3. UNMUTED: target and discard at begin; the band decides the rest. Done at once. */
    t->reached = 1u;
    t->t_reached = now;
    return finish2(t, now);
}
