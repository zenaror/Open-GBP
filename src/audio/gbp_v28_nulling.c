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

static uint32_t p2_nvals(void)
{
    return (GBP_V28_P2_HI - GBP_V28_P2_LO) / GBP_V28_P2_STEP + 1u;
}

/* draw_p2()'s own native port (gbp_async.c): a uniform start on the grid, a 50/50 direction. */
static void seed(struct gbp_v28_nulling *n, uint32_t k)
{
    if (k >= GBP_V28_NULLING_CAP) return;
    n->rng = xorshift32(n->rng);
    n->p2_start[k] = GBP_V28_P2_LO + (n->rng % p2_nvals()) * GBP_V28_P2_STEP;
    n->rng = xorshift32(n->rng);
    n->p2_dir[k] = (uint8_t)((n->rng & 1u) ? GBP_V28_NULLING_LEFT_SHALLOWER : GBP_V28_NULLING_LEFT_DEEPER);
}

int gbp_v28_nulling_start(struct gbp_v28_nulling *n, struct gbp_atrans2 *t, struct gbp_aplay2 *p,
                          struct gbp_adec2 *d, uint64_t now, uint32_t seed_in)
{
    memset(n, 0, sizeof *n);
    /* gbp_async_start()'s own guard (gbp_async.c): a seed of 0 is xorshift32's fixed point (it
     * would draw the same "random" value forever) -- substituted here exactly as there. */
    n->rng = seed_in ? seed_in : 1u;
    n->ahead = p->ahead;
    seed(n, 0u);
    n->p2_seeded = 1u;
    if (!gbp_atrans2_begin(t, p, d, now, GBP_ATRANS2_ROTATE, GBP_V28_STEP_MUTE, 0u, 0u, n->p2_start[0], n->ahead))
        return 0;
    n->target = n->p2_start[0];
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
    if (deeper) {
        if (n->target >= GBP_V28_P2_HI) { n->refused_step_end++; return 0; }
        to = n->target + GBP_V28_P2_STEP;
    } else {
        if (n->target <= GBP_V28_P2_LO) { n->refused_step_end++; return 0; }
        to = n->target - GBP_V28_P2_STEP;
    }
    /* t->active was just checked false above, and nothing between there and here can begin a
     * transition -- this begin() cannot be refused (gbp_atrans2_begin()'s only hard refusal). */
    if (!gbp_atrans2_begin(t, p, d, now, GBP_ATRANS2_ROTATE, GBP_V28_STEP_MUTE, 0u, 0u, to, n->ahead)) {
        n->refused_step_busy++;
        return 0;
    }
    if (deeper) { n->steps_deeper++; } else { n->steps_shallower++; }
    n->steps++;
    n->target = to;
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
    s->target = n->target;
    s->t = now;
    n->settings_n++;
    if (n->settings_n >= GBP_V28_NULLING_CAP) { n->finished = 1u; return 1; }
    n->p2_index = n->settings_n;
    if (n->p2_index >= n->p2_seeded) { seed(n, n->p2_index); n->p2_seeded = n->p2_index + 1u; }
    n->steps = n->steps_deeper = n->steps_shallower = 0u;
    /* see gbp_v28_nulling_step()'s own comment: t->active was just checked false above, and nothing
     * between there and here can begin a transition -- this cannot be refused either. */
    if (!gbp_atrans2_begin(t, p, d, now, GBP_ATRANS2_ROTATE, GBP_V28_STEP_MUTE, 0u, 0u, n->p2_start[n->p2_index],
                           n->ahead)) {
        n->refused_confirm_busy++;
        return 0;
    }
    n->target = n->p2_start[n->p2_index];
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
