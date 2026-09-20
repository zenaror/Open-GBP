/*
 * gbp_vvi.c — the VI hand-over / latch trace. See the header.
 */
#include <string.h>
#include "gbp_vvi.h"

void gbp_vvi_init(struct gbp_vvi *v, struct gbp_vvi_rec *recs, uint32_t cap)
{
    if (!v) return;
    memset(v, 0, sizeof *v);
    v->rec = recs;
    v->cap = recs ? cap : 0u;
    v->awaiting = -1;
}

int gbp_vvi_handed(struct gbp_vvi *v, uint32_t frame_index, uint32_t life, int16_t xfb,
                   uint32_t phys, uint64_t t, uint32_t retrace)
{
    struct gbp_vvi_rec *r;
    if (!v) return -1;
    v->handed++;
    if (v->awaiting >= 0) {
        v->rec[v->awaiting].flags |= GBP_VVI_F_SUPERSEDED;
        v->superseded++;
        v->awaiting = -1;
    }
    if (!v->rec || v->n >= v->cap) { v->overflow++; return -1; }
    r = &v->rec[v->n];
    memset(r, 0, sizeof *r);
    r->frame_index = frame_index;
    r->life = life;
    r->xfb = xfb;
    r->phys = phys;
    r->t_handed = t;
    r->retrace_handed = retrace;
    v->awaiting = (int32_t)v->n;
    v->n++;
    return v->awaiting;
}

int gbp_vvi_awaiting(const struct gbp_vvi *v)
{
    if (!v || v->awaiting < 0) return -1;
    return v->rec[v->awaiting].xfb;
}

int gbp_vvi_latch(struct gbp_vvi *v, uint64_t t, uint32_t retrace,
                  uint16_t vi14, uint16_t vi15, uint16_t vi18, uint16_t vi19)
{
    struct gbp_vvi_rec *r;
    if (!v) return 0;
    v->observe_calls++;
    if (v->awaiting < 0) return 0;
    r = &v->rec[v->awaiting];
    r->t_latch = t;
    r->retrace_latch = retrace;
    r->vi14 = vi14; r->vi15 = vi15; r->vi18 = vi18; r->vi19 = vi19;
    r->flags |= GBP_VVI_F_LATCHED;
    v->latched++;
    v->awaiting = -1;
    return 1;
}
