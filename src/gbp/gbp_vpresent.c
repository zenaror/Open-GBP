/*
 * gbp_vpresent.c — see gbp_vpresent.h for the rule this module exists to make
 * provable: at most one draw-done token in flight, and the callback releases
 * exactly one buffer by index.
 */
#include "gbp_vpresent.h"

void gbp_vpresent_init(struct gbp_vpresent *p)
{
    uint32_t i;
    uint8_t *b = (uint8_t *)p;
    if (!p) return;
    for (i = 0; i < sizeof *p; i++) b[i] = 0u;
    for (i = 0; i < GBP_VPRESENT_TEX_BUFFERS; i++) p->tex[i] = GBP_VPRESENT_FREE;
    p->submitted = -1;
    p->xfb_pending = -1;
}

void gbp_vpresent_shutdown(struct gbp_vpresent *p)
{
    if (p) p->shutting_down = 1;
}

int gbp_vpresent_inflight(const struct gbp_vpresent *p)
{
    return (p && p->submitted >= 0) ? 1 : 0;
}

int gbp_vpresent_acquire(struct gbp_vpresent *p)
{
    uint32_t i;
    if (!p) return -1;
    p->acquire_attempts++;
    if (p->shutting_down) { p->acquire_no_free_texture++; return -1; }
    for (i = 0; i < GBP_VPRESENT_TEX_BUFFERS; i++) {
        if (p->tex[i] == GBP_VPRESENT_FREE) {
            p->tex[i] = GBP_VPRESENT_CPU_FILLING;
            p->fills_started++;
            return (int)i;
        }
    }
    /* Nothing to write into. This is a THROUGHPUT fact, not a safety one: it
     * says the CPU had no buffer, never that the GP was not raced. */
    p->acquire_no_free_texture++;
    return -1;
}

int gbp_vpresent_fill_done(struct gbp_vpresent *p, int idx)
{
    if (!p || idx < 0 || (uint32_t)idx >= GBP_VPRESENT_TEX_BUFFERS) return -1;
    if (p->tex[idx] != GBP_VPRESENT_CPU_FILLING) return -1;
    p->tex[idx] = GBP_VPRESENT_READY;
    p->fills_completed++;
    return 0;
}

int gbp_vpresent_abandon(struct gbp_vpresent *p, int idx)
{
    if (!p || idx < 0 || (uint32_t)idx >= GBP_VPRESENT_TEX_BUFFERS) return -1;
    /* A SUBMITTED buffer belongs to the GP and may never be taken back here;
     * only the callback releases it. Abandoning one would be the `stream-0001`
     * defect in a different shape. */
    if (p->tex[idx] == GBP_VPRESENT_SUBMITTED) return -1;
    p->tex[idx] = GBP_VPRESENT_FREE;
    p->fills_abandoned++;
    return 0;
}

int gbp_vpresent_submit(struct gbp_vpresent *p, int idx)
{
    if (!p || idx < 0 || (uint32_t)idx >= GBP_VPRESENT_TEX_BUFFERS) return 0;
    p->submit_attempts++;
    if (p->shutting_down) { p->submit_blocked_shutdown++; return 0; }
    if (p->tex[idx] != GBP_VPRESENT_READY) return 0;
    /* ONE token in flight. Reading `submitted` once is enough: the callback only
     * ever moves it from >= 0 to -1, so a value of -1 read here cannot become
     * >= 0 behind our back — nothing else arms a token. */
    if (p->submitted >= 0) { p->submit_blocked_inflight++; return 0; }
    /* Mark first, arm second. The caller issues GX_SetDrawDone() only after this
     * returns 1, so the callback can never observe a half-built submission. */
    p->tex[idx] = GBP_VPRESENT_SUBMITTED;
    p->submitted = idx;
    p->submit_success++;
    return 1;
}

int gbp_vpresent_draw_done(struct gbp_vpresent *p)
{
    int idx;
    if (!p) return -1;
    p->drawdone_callbacks++;
    idx = p->submitted;
    if (idx < 0) {
        /* Nothing was submitted. `stream-0001` would have freed every buffer in
         * SUBMITTED here; this releases nothing and records the event. */
        p->drawdone_spurious++;
        return -1;
    }
    p->submitted = -1;
    p->tex[idx] = GBP_VPRESENT_FREE;
    p->texture_releases++;
    return idx;
}

int gbp_vpresent_xfb_target(struct gbp_vpresent *p, int current)
{
    uint32_t i;
    if (!p) return -1;
    if (p->shutting_down) { p->xfb_skipped_busy++; return -1; }
    gbp_vpresent_xfb_observe(p, current);
    for (i = 0; i < GBP_VPRESENT_XFB_BUFFERS; i++) {
        if ((int)i == current) continue;          /* the VI is scanning it out */
        if ((int)i == p->xfb_pending) continue;   /* already handed over, not yet current */
        return (int)i;
    }
    /* Both are spoken for: skip this present. Never wait for a retrace. */
    p->xfb_skipped_busy++;
    return -1;
}

void gbp_vpresent_xfb_handed(struct gbp_vpresent *p, int idx)
{
    if (!p || idx < 0 || (uint32_t)idx >= GBP_VPRESENT_XFB_BUFFERS) return;
    p->xfb_pending = idx;
    p->xfb_presents++;
}

void gbp_vpresent_xfb_observe(struct gbp_vpresent *p, int current)
{
    if (!p) return;
    /* The VI picked up what we handed it, so the hand-over is retired and the
     * OTHER buffer becomes writable. This is the whole of the retrace tracking:
     * one comparison, no callback, no wait. */
    if (p->xfb_pending >= 0 && p->xfb_pending == current) p->xfb_pending = -1;
}

int gbp_vpresent_consistent(const struct gbp_vpresent *p)
{
    uint32_t i, n_submitted = 0;
    if (!p) return 0;
    for (i = 0; i < GBP_VPRESENT_TEX_BUFFERS; i++) {
        if (p->tex[i] > GBP_VPRESENT_SUBMITTED) return 0;
        if (p->tex[i] == GBP_VPRESENT_SUBMITTED) n_submitted++;
    }
    if (n_submitted > 1u) return 0;                          /* the whole rule */
    if (p->submitted >= 0) {
        if ((uint32_t)p->submitted >= GBP_VPRESENT_TEX_BUFFERS) return 0;
        if (p->tex[p->submitted] != GBP_VPRESENT_SUBMITTED) return 0;
        if (n_submitted != 1u) return 0;
    } else if (n_submitted != 0u) {
        return 0;
    }
    if (p->xfb_pending >= 0 && (uint32_t)p->xfb_pending >= GBP_VPRESENT_XFB_BUFFERS) return 0;
    return 1;
}
