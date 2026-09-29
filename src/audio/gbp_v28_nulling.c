/*
 * gbp_v28_nulling — see gbp_v28_nulling.h.
 */
#include <string.h>
#include "gbp_v28_nulling.h"
#include "gbp_v28_ladder.h"

/* Same algorithm as gbp_async_xorshift32() (gbp_async.c) -- ported, not shared: the native §V28
 * modules never depend on the old 4096 Hz path's own build (gbp_v28_ladder.h, gbp_v28_3a/3b/sweep
 * all stand on their own). */
static uint32_t xorshift32(uint32_t x)
{
    x ^= (uint32_t)(x << 13);
    x ^= (uint32_t)(x >> 17);
    x ^= (uint32_t)(x << 5);
    return x;
}

/* draw_p2()'s own native port (gbp_async.c), on the eight rungs: a uniform START rung, a 50/50 direction. */
static void seed(struct gbp_v28_nulling *n, uint32_t k)
{
    if (k >= GBP_V28_NULLING_CAP) return;
    n->rng = xorshift32(n->rng);
    n->p2_start[k] = n->rng % GBP_V28_RUNGS;
    n->rng = xorshift32(n->rng);
    n->p2_dir[k] = (uint8_t)((n->rng & 1u) ? GBP_V28_NULLING_LEFT_SHALLOWER : GBP_V28_NULLING_LEFT_DEEPER);
}

/* a transition to a rung under a mute: ROTATE, no pause, no discard (gbp_atrans2.h: the ROTATE level is set in silence) */
static int go(struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d, uint64_t now, uint32_t rung, uint32_t mute)
{
    return gbp_atrans2_begin(t, p, d, now, GBP_ATRANS2_ROTATE, mute, 0u, 0u, GBP_V28_RUNG[rung].target, GBP_V28_RUNG[rung].ahead);
}

int gbp_v28_nulling_start(struct gbp_v28_nulling *n, struct gbp_atrans2 *t, struct gbp_aplay2 *p,
                          struct gbp_adec2 *d, uint64_t now, uint32_t seed_in)
{
    memset(n, 0, sizeof *n);
    /* gbp_async_start()'s own guard (gbp_async.c): a seed of 0 is xorshift32's fixed point (it
     * would draw the same "random" value forever) -- substituted here exactly as there. */
    n->rng = seed_in ? seed_in : 1u;
    seed(n, 0u);
    n->p2_seeded = 1u;
    if (!go(t, p, d, now, n->p2_start[0], GBP_V28_START_MUTE)) return 0;
    n->rung = n->p2_start[0];
    n->u0 = p->underruns; n->o0 = d->overflow;
    return 1;
}

int gbp_v28_nulling_step(struct gbp_v28_nulling *n, struct gbp_atrans2 *t, struct gbp_aplay2 *p,
                         struct gbp_adec2 *d, uint64_t now, uint8_t stick)
{
    int deeper;
    uint32_t to;
    if (stick != GBP_V28_NULLING_LEFT && stick != GBP_V28_NULLING_RIGHT) { n->refused_step_value++; return 0; }
    if (t->active) { n->refused_step_busy++; return 0; }
    deeper = (stick == GBP_V28_NULLING_LEFT) == (n->p2_dir[n->p2_index] == GBP_V28_NULLING_LEFT_DEEPER);
    to = n->rung;
    if (deeper && n->rung > 0u) to = n->rung - 1u;
    else if (!deeper && n->rung + 1u < GBP_V28_RUNGS) to = n->rung + 1u;
    /* t->active was just checked false above and nothing between there and here can begin a transition: this begin() cannot be refused. */
    if (!go(t, p, d, now, to, GBP_V28_STEP_MUTE)) {
        n->refused_step_busy++;
        return 0;
    }
    if (to == n->rung) {
        /* an end of the ladder: the SAME plan and mute as a step, to the same level (the end is not audible), counted apart per end */
        n->refused_step_end++;
        if (deeper) n->cur_refused_top++; else n->cur_refused_floor++;
        return 1;
    }
    if (deeper) { n->steps_deeper++; } else { n->steps_shallower++; }
    n->steps++;
    n->rung = to;
    return 1;
}

int gbp_v28_nulling_confirm(struct gbp_v28_nulling *n, struct gbp_atrans2 *t, struct gbp_aplay2 *p,
                            struct gbp_adec2 *d, uint64_t now)
{
    struct gbp_v28_nulling_setting *s;
    if (n->finished) { n->refused_confirm_over++; return 0; }
    if (t->active) { n->refused_confirm_busy++; return 0; }
    s = &n->settings[n->settings_n];
    s->seq = n->settings_n + 1u;
    s->start = n->p2_start[n->p2_index];
    s->direction = n->p2_dir[n->p2_index];
    s->steps = n->steps; s->steps_deeper = n->steps_deeper; s->steps_shallower = n->steps_shallower;
    s->refused_floor = n->cur_refused_floor; s->refused_top = n->cur_refused_top;
    s->rung = n->rung;
    s->target = GBP_V28_RUNG[n->rung].target;
    s->ahead = GBP_V28_RUNG[n->rung].ahead;
    s->ring = d->count;
    s->ready = gbp_aplay2_ready(p);
    s->underruns = p->underruns - n->u0;
    s->overflow = d->overflow - n->o0;
    s->t = now;
    n->settings_n++;
    if (n->settings_n >= GBP_V28_NULLING_CAP) { n->finished = 1u; return 1; }
    n->p2_index = n->settings_n;
    if (n->p2_index >= n->p2_seeded) { seed(n, n->p2_index); n->p2_seeded = n->p2_index + 1u; }
    n->steps = n->steps_deeper = n->steps_shallower = 0u;
    n->cur_refused_floor = n->cur_refused_top = 0u;
    /* see gbp_v28_nulling_step()'s own comment: t->active was just checked false above; this cannot be refused either. */
    if (!go(t, p, d, now, n->p2_start[n->p2_index], GBP_V28_START_MUTE)) {
        n->refused_confirm_busy++;
        return 0;
    }
    n->rung = n->p2_start[n->p2_index];
    n->u0 = p->underruns; n->o0 = d->overflow;
    return 1;
}

int gbp_v28_nulling_finished(const struct gbp_v28_nulling *n)
{
    return n && n->finished;
}

const struct gbp_v28_nulling_setting *gbp_v28_nulling_record(const struct gbp_v28_nulling *n, uint32_t index)
{
    if (!n || index >= n->settings_n) return NULL;
    return &n->settings[index];
}
