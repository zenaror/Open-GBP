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
        if (t->rotating) { t->rotating = 0u; t->late = 1u; t->lates++; }
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
    if (p->mute >= 1u) {
        const uint32_t aim = p->mute >= 2u ? t->target + GBP_ATRANS2_AIM
                                           : (t->target > GBP_ATRANS2_AIM ? t->target - GBP_ATRANS2_AIM : 0u);
        if (d->count >= aim) {
            const int32_t b = gbp_aplay2_produce_uncorrected(p, d);
            t->rotating = 1u;
            if (b >= 0) rotated2(t, p, b, to_queue);
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
    if (t->mode == GBP_ATRANS2_ROTATE) return step_rotate2(t, p, d, now, handed, to_queue);
    if (t->mode == GBP_ATRANS2_HELD) return step_held2(t, p, d, now, handed, to_queue);
    /* 3. UNMUTED: target and discard at begin; the band decides the rest. Done at once. */
    t->reached = 1u;
    t->t_reached = now;
    return finish2(t, now);
}
