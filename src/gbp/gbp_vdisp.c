/*
 * gbp_vdisp.c — see gbp_vdisp.h for what is recorded and why a refusal at the
 * token gate is a counter rather than an event.
 */
#include "gbp_vdisp.h"

static void zero(void *p, size_t n)
{
    uint8_t *b = (uint8_t *)p;
    size_t i;
    for (i = 0; i < n; i++) b[i] = 0u;
}

int gbp_vdisp_init(struct gbp_vdisp *d, struct gbp_vdisp_life *life, uint32_t life_cap,
                   struct gbp_vdisp_event *ev, uint32_t ev_cap)
{
    uint32_t i;
    if (!d) return -1;
    zero(d, sizeof *d);
    if (!life || !ev || life_cap == 0u || ev_cap == 0u) return -1;
    zero(life, (size_t)life_cap * sizeof *life);
    zero(ev, (size_t)ev_cap * sizeof *ev);
    d->life = life; d->ev = ev;
    d->life_cap = life_cap; d->ev_cap = ev_cap;
    for (i = 0; i < GBP_VDISP_TEX_SLOTS; i++) d->life_of_tex[i] = -1;
    d->prev_selected = GBP_VDISP_KEY_NONE;
    return 0;
}

static struct gbp_vdisp_life *at(struct gbp_vdisp *d, int life)
{
    if (!d || !d->life || life < 0 || (uint32_t)life >= d->life_n) return 0;
    return &d->life[life];
}

int gbp_vdisp_take(struct gbp_vdisp *d, uint32_t frame_index, uint32_t seq,
                   uint16_t slot, uint32_t src_flags, uint64_t t_close,
                   uint64_t t_take, uint32_t retrace,
                   uint16_t tex, int in_window, int selftest)
{
    struct gbp_vdisp_life *r;
    if (!d || !d->life) return -1;
    if (d->life_n >= d->life_cap) {
        /* FAIL CLOSED. Nothing wraps, nothing is overwritten: a trace is either
         * complete or visibly incomplete. */
        d->life_overflow++;
        return -1;
    }
    r = &d->life[d->life_n];
    zero(r, sizeof *r);
    r->frame_index = frame_index;
    r->seq = seq;
    r->slot = slot;
    r->tex = tex;
    r->src_flags = src_flags;
    r->t_close = t_close;
    r->t_take = t_take;
    r->retrace_take = retrace;
    r->disposition = (uint16_t)GBP_VDISP_D_OPEN;
    r->reason = (uint16_t)GBP_VDISP_R_NONE;
    if (in_window) r->life_flags |= GBP_VDISP_F_IN_WINDOW;
    if (selftest) r->life_flags |= GBP_VDISP_F_SELFTEST;
    return (int)d->life_n++;
}

void gbp_vdisp_convert_first(struct gbp_vdisp *d, int life, uint64_t t)
{
    struct gbp_vdisp_life *r = at(d, life);
    if (r && r->t_convert_first == 0u) r->t_convert_first = t;
}

void gbp_vdisp_convert_done(struct gbp_vdisp *d, int life, uint64_t t, uint32_t ticks)
{
    struct gbp_vdisp_life *r = at(d, life);
    if (!r) return;
    r->t_convert_done = t;
    r->convert_ticks = ticks;
    r->life_flags |= GBP_VDISP_F_CONVERTED;
}

void gbp_vdisp_abandon(struct gbp_vdisp *d, int life, uint16_t disposition)
{
    struct gbp_vdisp_life *r = at(d, life);
    if (!r) return;
    r->disposition = disposition;
}

void gbp_vdisp_submit_refused(struct gbp_vdisp *d, int life)
{
    struct gbp_vdisp_life *r = at(d, life);
    if (r) r->submit_refusals++;
}

void gbp_vdisp_submit(struct gbp_vdisp *d, int life, uint64_t t)
{
    struct gbp_vdisp_life *r = at(d, life);
    if (!r) return;
    r->t_submit = t;
    r->life_flags |= GBP_VDISP_F_SUBMITTED;
    /* The ISR resolves a texture index to a frame through this array, so it is
     * written HERE -- at the moment the token is armed -- and never earlier. A
     * mapping that named a frame before the GP was working on it would let a
     * draw-done be credited to the wrong generation. */
    if (r->tex < GBP_VDISP_TEX_SLOTS) d->life_of_tex[r->tex] = life;
}

void gbp_vdisp_defer(struct gbp_vdisp *d, int life, uint64_t t, uint32_t retrace,
                     int xfb_current, int xfb_pending, uint16_t reason,
                     const uint8_t *tex_state, uint32_t depth)
{
    struct gbp_vdisp_life *r = at(d, life);
    struct gbp_vdisp_event *e;
    int first;
    if (!d || !r) return;
    if (r->t_first_attempt == 0u) r->t_first_attempt = t;
    first = (r->defer_attempts == 0u);
    r->defer_attempts++;
    d->source_defer_attempts++;
    if (first) {
        r->t_first_defer = t;
        r->life_flags |= GBP_VDISP_F_EVER_DEFERRED;
        d->source_deferred_frames++;
    }
    r->t_last_defer = t;
    r->disposition = (uint16_t)GBP_VDISP_D_DEFERRED;
    r->reason = reason;
    if (depth > d->max_deferred_depth) d->max_deferred_depth = depth;
    /* ONE event per frame, on the transition. pump() retries about every
     * 158 us; an event per attempt would be unbounded and would perturb the
     * thing it is measuring. */
    if (!first) return;
    if (d->ev_n >= d->ev_cap) { d->ev_overflow++; return; }
    e = &d->ev[d->ev_n];
    zero(e, sizeof *e);
    e->t = t;
    e->ordinal = d->ev_n;
    e->retrace = retrace;
    e->frame_index = r->frame_index;
    e->prev_index = d->prev_selected;
    e->xfb_current = (int16_t)xfb_current;
    e->xfb_pending = (int16_t)xfb_pending;
    e->xfb_target = -1;
    e->tex = (uint8_t)r->tex;
    e->decision = (uint8_t)GBP_VDISP_D_DEFERRED;
    e->reason = (uint8_t)reason;
    if (tex_state) { e->tex_state[0] = tex_state[0]; e->tex_state[1] = tex_state[1]; }
    e->newest_source = GBP_VDISP_KEY_NONE;
    d->ev_n++;
}

void gbp_vdisp_finish(struct gbp_vdisp *d)
{
    uint32_t i;
    if (!d || !d->life) return;
    for (i = 0; i < d->life_n; i++) {
        struct gbp_vdisp_life *r = &d->life[i];
        if (r->disposition == GBP_VDISP_D_SELECTED_NEW ||
            r->disposition == GBP_VDISP_D_SLOT_OVERRUN ||
            r->disposition == GBP_VDISP_D_ABANDONED_NO_RAW ||
            r->disposition == GBP_VDISP_D_HOLD_PREVIOUS) continue;
        /* OPEN or DEFERRED at the end of the run. It was never lost and it was
         * never presented: an EDGE state, counted as itself. Teardown does not
         * invent a hand-off to make a column add up. */
        r->disposition = (uint16_t)GBP_VDISP_D_TERMINAL_PENDING;
        d->terminal_pending++;
    }
}

void gbp_vdisp_drawdone(struct gbp_vdisp *d, int tex, uint64_t t)
{
    int life;
    struct gbp_vdisp_life *r;
    if (!d || !d->life) return;
    if (tex < 0 || (uint32_t)tex >= GBP_VDISP_TEX_SLOTS) { d->drawdone_unmatched++; return; }
    life = (int)d->life_of_tex[tex];
    d->life_of_tex[tex] = -1;                 /* one token, one release */
    r = at(d, life);
    if (!r) { d->drawdone_unmatched++; return; }
    r->t_drawdone = t;
    r->life_flags |= GBP_VDISP_F_DRAWDONE;
}

void gbp_vdisp_decision(struct gbp_vdisp *d, int life, uint64_t t, uint32_t retrace,
                        int xfb_current, int xfb_pending, int xfb_target,
                        uint16_t reason, const uint8_t *tex_state, int inflight,
                        uint32_t newest_source)
{
    struct gbp_vdisp_life *r = at(d, life);
    struct gbp_vdisp_event *e;
    const uint16_t disp = (uint16_t)((xfb_target >= 0) ? GBP_VDISP_D_SELECTED_NEW
                                                       : GBP_VDISP_D_HOLD_PREVIOUS);
    if (!d) return;
    d->decisions++;
    if (r) {
        if (r->t_first_attempt == 0u) r->t_first_attempt = t;
        r->t_decision = t;
        r->retrace_decision = retrace;
        r->disposition = disp;
        r->reason = (xfb_target >= 0) ? (uint16_t)GBP_VDISP_R_NONE : reason;
        r->life_flags |= GBP_VDISP_F_DECIDED;
        if (xfb_target >= 0) {
            d->source_handoffs++;
            /* I2: a newer frame must never hand off before an older one that is
             * still waiting. Counted rather than asserted, so a violation is
             * visible in the evidence instead of stopping the run. */
            if (d->have_last_handoff && r->frame_index != GBP_VDISP_KEY_NONE &&
                d->last_handoff_index != GBP_VDISP_KEY_NONE &&
                r->frame_index <= d->last_handoff_index) d->order_violations++;
            if (r->frame_index != GBP_VDISP_KEY_NONE) {
                d->last_handoff_index = r->frame_index;
                d->have_last_handoff = 1;
            }
        } else {
            d->source_dropped_interior++;
        }
    }
    if (d->ev_n >= d->ev_cap) { d->ev_overflow++; return; }
    e = &d->ev[d->ev_n];
    zero(e, sizeof *e);
    e->t = t;
    e->ordinal = d->ev_n;
    e->retrace = retrace;
    e->frame_index = r ? r->frame_index : GBP_VDISP_KEY_NONE;
    e->prev_index = d->prev_selected;
    e->xfb_current = (int16_t)xfb_current;
    e->xfb_pending = (int16_t)xfb_pending;
    e->xfb_target = (int16_t)xfb_target;
    e->tex = r ? (uint8_t)r->tex : 0xFFu;
    e->decision = (uint8_t)disp;
    e->reason = (uint8_t)((xfb_target >= 0) ? GBP_VDISP_R_NONE : reason);
    if (tex_state) { e->tex_state[0] = tex_state[0]; e->tex_state[1] = tex_state[1]; }
    e->inflight = (uint8_t)(inflight ? 1 : 0);
    e->newest_source = newest_source;
    d->ev_n++;
    /* Only a frame that actually reached a framebuffer becomes "previous": a
     * HOLD leaves the screen showing whatever was there, so the next event's
     * prev_index must still name THAT frame and not the one that was held. */
    if (xfb_target >= 0 && r) d->prev_selected = r->frame_index;
}

const struct gbp_vdisp_life *gbp_vdisp_life_at(const struct gbp_vdisp *d, uint32_t i)
{
    if (!d || !d->life || i >= d->life_n) return 0;
    return &d->life[i];
}

const struct gbp_vdisp_event *gbp_vdisp_event_at(const struct gbp_vdisp *d, uint32_t i)
{
    if (!d || !d->ev || i >= d->ev_n) return 0;
    return &d->ev[i];
}

int gbp_vdisp_intact(const struct gbp_vdisp *d)
{
    if (!d) return 0;
    /* `decisions` counts terminal decisions only; `ev_n` also holds one event
     * per DEFERRED frame, so the identity is decisions + deferred == ev_n. */
    return (d->life_overflow == 0u && d->ev_overflow == 0u &&
            d->drawdone_unmatched == 0u && d->order_violations == 0u &&
            d->decisions + d->source_deferred_frames == d->ev_n) ? 1 : 0;
}
