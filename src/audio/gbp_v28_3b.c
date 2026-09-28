/*
 * gbp_v28_3b — see gbp_v28_3b.h.
 */
#include <string.h>
#include "gbp_v28_3b.h"
#include "gbp_v28_ladder.h"

static void begin_ahead(struct gbp_v28_3b *s, uint32_t ahead)
{
    s->pending_ahead = ahead;
    s->begin_pending = 1u;
    s->cur_ahead = ahead;
    s->underrun_seen = 0u;
}

void gbp_v28_3b_start(struct gbp_v28_3b *s, uint32_t anchor_target, uint32_t tb_hz, uint64_t now)
{
    memset(s, 0, sizeof *s);
    s->tb_hz = tb_hz;
    s->anchor_target = anchor_target;
    (void)now;
    begin_ahead(s, GBP_V28_A1);     /* the entry step: AHEAD 4 -> 1 at the anchor, #128 §2 */
}

void gbp_v28_3b_underrun_observed(struct gbp_v28_3b *s, uint64_t now)
{
    if (s->hold_active && !s->underrun_seen && now < s->t_hold_end) {
        s->underrun_seen = 1u;
        s->t_hold_end = now;        /* the hold ends at its own first underrun -- #128 §2 */
    }
}

int gbp_v28_3b_tick(struct gbp_v28_3b *s, struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d,
                    uint64_t now)
{
    if (s->finished) return GBP_V28_3B_TICK_PHASE_COMPLETE;

    /* set on EVERY tick until gbp_v28_3b_hold_done() is called -- mirrors gbp_v28_3a's own
     * persistent-flag contract. */
    if (s->hold_pending) return GBP_V28_3B_TICK_HOLD_DONE;

    if (s->begin_pending) {
        /* THE SAME REQUIREMENT AS 3A: a hold starts only once its own plan has actually begun.
         * ROTATE, the step mechanism's own fixed mute (#128 §3) -- never UNMUTED, unlike 3a's own
         * descent: this is precisely the mechanism the perceptual run will use. */
        if (!gbp_atrans2_begin(t, p, d, now, GBP_ATRANS2_ROTATE, GBP_V28_STEP_MUTE, 0u, 0u,
                               s->anchor_target, s->pending_ahead))
            return 0;
        s->begin_pending = 0u;
        s->hold_active = 1u;
        s->t_set = now;
        s->t_hold_end = now + (uint64_t)GBP_V28_3B_HOLD_S * s->tb_hz;
        s->cur_min_ready = UINT32_MAX;
        s->cur_min_ring = UINT32_MAX;
        s->cur_samples = 0u;
        return 0;
    }

    if (s->hold_active && !t->active) {      /* the margin, once the entry transition itself has landed */
        const uint32_t ready = gbp_aplay2_ready(p);
        if (ready < s->cur_min_ready) s->cur_min_ready = ready;
        if (d->count < s->cur_min_ring) s->cur_min_ring = d->count;
        s->cur_samples++;
    }

    if (s->hold_active && now >= s->t_hold_end) {
        s->hold_active = 0u;
        s->hold_pending = 1u;
        return GBP_V28_3B_TICK_HOLD_DONE;
    }
    return 0;
}

void gbp_v28_3b_cut(struct gbp_v28_3b *s, uint64_t t_end)
{
    if (s->hold_active) {                    /* the hold is cut before its own end: still reportable, partial */
        s->hold_cut = 1u;
        s->hold_active = 0u;
        s->hold_pending = 1u;
        s->t_hold_end = t_end;
    }                                          /* a hold already pending/done stays exactly as it was */
    s->begin_pending = 0u;                    /* an AHEAD change decided but never begun: abandoned, nothing
                                                * to report -- see gbp_v28_3a.c's own identical reasoning */
    s->finished = 1u;
}

static void record_hold(struct gbp_v28_3b *s, uint8_t partial, uint64_t t_set, uint64_t t_done)
{
    if (s->holds_n < 2u) {
        struct gbp_v28_3b_hold *rec = &s->holds[s->holds_n++];
        rec->ahead = s->cur_ahead;
        rec->underrun_seen = s->underrun_seen;
        rec->partial = partial;
        rec->t_set = t_set;
        rec->t_done = t_done;
        rec->samples = s->cur_samples;
        rec->min_ready = s->cur_samples ? s->cur_min_ready : 0u;
        rec->min_ring = s->cur_samples ? s->cur_min_ring : 0u;
    }
    /* holds_n cannot exceed 2 by construction (AHEAD 1 then, at most, AHEAD 2) -- no overflow
     * counter needed the way gbp_v28_3a's own depths array has one. */
}

void gbp_v28_3b_hold_done(struct gbp_v28_3b *s)
{
    const int over = s->finished;    /* cut() already set this before this call: nothing follows it */
    uint8_t partial;

    if (!s->hold_pending) { s->refused_hold_done++; return; }
    s->hold_pending = 0u;

    partial = s->hold_cut;
    s->hold_cut = 0u;
    record_hold(s, partial, s->t_set, s->t_hold_end);
    if (over) return;                 /* recorded; the phase is already gone (a cut), nothing more to decide */

    if (s->cur_ahead == GBP_V28_A1 && s->underrun_seen) {
        begin_ahead(s, GBP_V28_A2);    /* the escalation: a FULL, separate 60 s hold, #128 §2 */
        return;
    }
    s->finished = 1u;                 /* AHEAD 1 held clean, or AHEAD 2's own hold just ended either way --
                                        * 3b never escalates past AHEAD 2 */
}

int gbp_v28_3b_finished(const struct gbp_v28_3b *s)
{
    return s && s->finished;
}

const struct gbp_v28_3b_hold *gbp_v28_3b_hold_record(const struct gbp_v28_3b *s, uint32_t index)
{
    if (!s || index >= s->holds_n) return NULL;
    return &s->holds[index];
}
