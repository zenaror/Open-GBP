/*
 * gbp_v28_3a — see gbp_v28_3a.h.
 */
#include <string.h>
#include "gbp_v28_3a.h"
#include "gbp_v28_ladder.h"

static void begin_depth(struct gbp_v28_3a *s, uint32_t target, uint8_t kind)
{
    s->pending_target = target;
    s->cur_kind = kind;
    s->begin_pending = 1u;
    s->cur = target;
}

void gbp_v28_3a_start(struct gbp_v28_3a *s, uint32_t tb_hz, uint64_t now)
{
    memset(s, 0, sizeof *s);
    s->tb_hz = tb_hz;
    (void)now;
    begin_depth(s, GBP_V28_P3_START, (uint8_t)GBP_V28_3A_STEP);
}

void gbp_v28_3a_underrun_observed(struct gbp_v28_3a *s, uint64_t now)
{
    /* §V27.14 §4: the confirmation hold ends at its first underrun -- the inevitability OBSERVED. */
    if (s->dwell_active && s->cur_kind == GBP_V28_3A_CONFIRM && now < s->t_dwell_end) s->t_dwell_end = now;
}

int gbp_v28_3a_tick(struct gbp_v28_3a *s, struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d,
                    uint64_t now)
{
    int flags = 0;

    if (s->finished) return GBP_V28_3A_TICK_PHASE_COMPLETE;

    /* set on EVERY tick until gbp_v28_3a_depth_done() is called -- mirrors
     * GBP_ASYNC_TICK_DEPTH_DONE's own persistent-flag contract exactly. */
    if (s->depth_pending) return GBP_V28_3A_TICK_DEPTH_DONE;

    if (s->begin_pending) {
        const uint32_t from = t->target;
        const uint32_t to = s->pending_target;
        const uint32_t pause = (to > from) ? (to - from + GBP_APLAY2_PUSHES - 1u) / GBP_APLAY2_PUSHES : 0u;
        const uint32_t discard = (to < from) ? from - to : 0u;
        /* THE REQUIREMENT (Orchestrator review): 3a starts its dwell only once its OWN plan has
         * actually begun. gbp_atrans2_begin() refuses (0) while a transition is still running --
         * this can only be the previous depth's own climb, not yet landed (a bisection step may
         * DEEPEN, which takes more than one pump call) -- and 3a must NOT believe the new target
         * is in force, or it would count a dwell at a depth the ring never reached. */
        /* #128 §2: 3a stays at AHEAD 4 throughout -- passed explicitly here, never left to whatever
         * gbp_aplay2_init()'s own default (GBP_APLAY2_AHEAD, currently 1) happens to be. */
        if (!gbp_atrans2_begin(t, p, d, now, GBP_ATRANS2_UNMUTED, 0u, pause, discard, to, GBP_V28_A4)) return 0;
        s->begin_pending = 0u;
        s->dwell_active = 1u;
        s->t_set = now;
        s->t_dwell_end = now + (uint64_t)(s->cur_kind == GBP_V28_3A_CONFIRM ? GBP_V28_3A_CONFIRM_S
                                                                             : GBP_V28_3A_DWELL_S) * s->tb_hz;
        return 0;
    }

    if (s->dwell_active && now >= s->t_dwell_end) {
        s->dwell_active = 0u;
        s->depth_pending = 1u;
        flags |= GBP_V28_3A_TICK_DEPTH_DONE;
    }
    return flags;
}

void gbp_v28_3a_cut(struct gbp_v28_3a *s, uint64_t t_end)
{
    if (s->dwell_active) {                   /* the dwell is cut before its own end: still reportable, partial */
        s->dwell_cut = 1u;
        s->dwell_active = 0u;
        s->depth_pending = 1u;
        s->t_dwell_end = t_end;
    }                                         /* a dwell already pending/done stays exactly as it was: whole if
                                                * it had already ended, still pending either way -- depth_done()
                                                * is still owed its call after a cut (gbp_async's own contract:
                                                * DEPTH_DONE fires on every tick until acknowledged) */
    if (s->begin_pending) {                   /* a depth decided but never begun: abandoned, nothing to report --
                                                * gbp_async's own design has no equivalent (its begin() could not
                                                * be refused), so there is no dwell of zero duration to record */
        s->begin_pending = 0u;
    }
    s->finished = 1u;                         /* the phase is over: tick() reports PHASE_COMPLETE from here,
                                                * but a depth_done() already owed for a cut/ended dwell above is
                                                * still honoured -- finished only stops the ALGORITHM from
                                                * deciding a next depth, not the last acknowledgement */
}

static void record_depth(struct gbp_v28_3a *s, uint32_t fill_mean_x16, uint32_t underruns, uint32_t overflow,
                         uint32_t dup, uint32_t drop, uint32_t lost, uint32_t starved, uint8_t partial,
                         uint64_t t_set, uint64_t t_done)
{
    if (s->depths_n < GBP_V28_3A_DEPTH_CAP) {
        struct gbp_v28_3a_depth *rec = &s->depths[s->depths_n++];
        rec->target = s->cur;
        rec->kind = s->cur_kind;
        rec->partial = partial;
        rec->fill_mean_x16 = fill_mean_x16;
        rec->underruns = underruns;
        rec->overflow = overflow;
        rec->dup = dup;
        rec->drop = drop;
        rec->lost = lost;
        rec->starved = starved;
        rec->t_set = t_set;
        rec->t_done = t_done;
    } else {
        s->depths_overflow++;
    }
}

void gbp_v28_3a_depth_done(struct gbp_v28_3a *s, uint32_t fill_mean_x16, uint32_t underruns, uint32_t overflow,
                          uint32_t dup, uint32_t drop, uint32_t lost, uint32_t starved)
{
    /* the same criterion gbp_async_depth_done() uses, unedited: a depth FAILS when the
     * correction stopped holding the level over its dwell (the DUP could not fire and the ring
     * could not give a wanted chunk), not when the audio actually failed. */
    const int failing = dup == 0u && starved > 0u;
    const uint32_t cur = s->cur;
    uint8_t partial;
    uint32_t next;
    const int over = s->finished;    /* cut() already set this before this call: nothing follows it */

    if (!s->depth_pending) { s->refused_depth_done++; return; }
    s->depth_pending = 0u;

    partial = s->dwell_cut;
    s->dwell_cut = 0u;
    record_depth(s, fill_mean_x16, underruns, overflow, dup, drop, lost, starved, partial, s->t_set,
                 s->t_dwell_end);
    if (over) return;                /* recorded; the phase is already gone (a cut), nothing more to decide */

    if (s->cur_kind == GBP_V28_3A_CONFIRM) {                          /* the hold is the last word */
        s->finished = 1u;
        return;
    }
    if (!s->bisecting) {
        if (failing) {
            if (!s->have_hold) {                                      /* the first depth fails: open bracket */
                s->finished = 1u;
                return;
            }
            s->lo = cur;
            s->hi = s->last_hold;
            s->bisecting = 1u;
        } else {
            s->have_hold = 1u;
            s->last_hold = cur;
            if (cur <= GBP_V28_P3_MIN) {                               /* the floor holds: nothing to bracket */
                s->finished = 1u;
                return;
            }
            next = (cur - GBP_V28_P3_MIN < GBP_V28_P3_STEP) ? GBP_V28_P3_MIN : cur - GBP_V28_P3_STEP;
            begin_depth(s, next, (uint8_t)GBP_V28_3A_STEP);
            return;
        }
    } else {
        if (failing) s->lo = cur; else s->hi = cur;
    }
    if (s->hi - s->lo <= GBP_V28_P3_BISECT_WIDTH) {
        s->bracket_closed = 1u;
        s->confirming = 1u;
        begin_depth(s, s->lo, (uint8_t)GBP_V28_3A_CONFIRM);
        return;
    }
    next = (s->lo + s->hi) / 2u;
    if (next == s->lo || next == s->hi) {                              /* the bracket cannot shrink further */
        s->bracket_closed = 1u;
        s->confirming = 1u;
        begin_depth(s, s->lo, (uint8_t)GBP_V28_3A_CONFIRM);
        return;
    }
    begin_depth(s, next, (uint8_t)GBP_V28_3A_BISECT);
}

int gbp_v28_3a_finished(const struct gbp_v28_3a *s)
{
    return s && s->finished;
}

const struct gbp_v28_3a_depth *gbp_v28_3a_depth_record(const struct gbp_v28_3a *s, uint32_t index)
{
    if (!s || index >= s->depths_n) return NULL;
    return &s->depths[index];
}

int gbp_v28_3a_confirmed_floor(const struct gbp_v28_3a *s, uint32_t *out)
{
    if (!s || !s->have_hold) return 0;
    *out = s->bisecting ? s->hi : s->last_hold;
    return 1;
}
