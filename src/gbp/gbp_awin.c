/*
 * gbp_awin.c — the AUDIO WINDOW store. See the header for the concurrency
 * argument and for why the window size is not this module's to choose.
 */
#include "gbp_awin.h"
#include <string.h>

/* memcpy, not a byte loop. The copy runs in the service path at the drain
 * cadence while a window is open, and a hand-written loop would cost several
 * times what the platform's copy does for no gain whatever. It is measured by
 * the caller either way. */

int gbp_awin_init(struct gbp_awin *w, uint8_t *store, uint32_t bytes)
{
    unsigned i;
    if (!w) return -1;
    memset(w, 0, sizeof *w);
    w->active = -1;
    w->block_size = GBP_AWIN_BLOCK_SIZE;
    w->blocks_per_window = GBP_AWIN_BLOCKS;
    w->windows = GBP_AWIN_WINDOWS;
    w->next_press = 1u;
    if (!store) { w->fault = 1; return -1; }
    if (bytes < GBP_AWIN_STORE_BYTES) { w->fault = 2; return -1; }
    if (((size_t)store & 31u) != 0u) { w->fault = 3; return -1; }
    w->store = store;
    w->store_bytes = bytes;
    for (i = 0; i < GBP_AWIN_WINDOWS; i++) {
        w->anchor[i].kind = (i == 0u) ? (uint32_t)GBP_AWIN_CONTROL : (uint32_t)GBP_AWIN_PRESS;
        w->anchor[i].ordinal = (i == 0u) ? 0u : i;
    }
    return 0;
}

const char *gbp_awin_fault(const struct gbp_awin *w)
{
    if (!w) return "null";
    switch (w->fault) {
    case 0: return "-";
    case 1: return "store_null";
    case 2: return "store_too_small";
    case 3: return "store_misaligned";
    default: return "unknown";
    }
}

/* Open window `index`. The caller has established that nothing is filling. */
static int open_window(struct gbp_awin *w, unsigned index, uint32_t kind, uint32_t ordinal,
                       const struct gbp_awin_press *p, uint64_t t_arm)
{
    struct gbp_awin_anchor *a = &w->anchor[index];
    a->kind = kind;
    a->ordinal = ordinal;
    a->flags = 0u;
    a->blocks = 0u;
    a->skipped = 0u;
    a->first_cycle = 0u;
    a->last_cycle = 0u;
    if (p) {
        a->event_n = p->event_n; a->word = p->word; a->keys = p->keys;
        a->t_poll = p->t_poll; a->t_attempt = p->t_attempt; a->t_done = p->t_done;
        a->t_arm = p->t_arm;
    } else {
        a->event_n = 0u; a->word = 0u; a->keys = 0u;
        a->t_poll = 0u; a->t_attempt = 0u; a->t_done = 0u;
        a->t_arm = t_arm;
    }
    w->filled = 0u;
    w->arms++;
    /* LAST, and after everything the fill will read: the service path takes
     * `active` as the permission to touch the store. */
    w->active = (int)index;
    return (int)index;
}

int gbp_awin_arm_control(struct gbp_awin *w, uint64_t t_arm)
{
    if (!w || !w->store) { if (w) w->arm_refused_no_store++; return -1; }
    if (w->active >= 0) { w->arm_refused_busy++; return -1; }
    if (w->anchor[0].flags & (GBP_AWIN_F_CLOSED | GBP_AWIN_F_INCOMPLETE)) {
        w->arm_refused_full++;          /* the control is armed once and never re-armed */
        return -1;
    }
    return open_window(w, 0u, (uint32_t)GBP_AWIN_CONTROL, 0u, 0, t_arm);
}

int gbp_awin_arm_press(struct gbp_awin *w, const struct gbp_awin_press *p)
{
    unsigned index;
    if (!w || !w->store) { if (w) w->arm_refused_no_store++; return -1; }
    if (!p) return -1;
    /* §V8.10 asks for three seconds between presses. A press that arrives while
     * a window is still filling is REFUSED, not queued and not allowed to
     * overwrite: the run reports it and the analysis knows one press has no
     * window rather than believing a window it never had. */
    if (w->active >= 0) { w->arm_refused_busy++; return -1; }
    if (w->next_press > GBP_AWIN_PRESS_WINDOWS) { w->arm_refused_full++; return -1; }
    index = w->next_press;
    w->next_press++;
    return open_window(w, index, (uint32_t)GBP_AWIN_PRESS, index, p, p->t_arm);
}

void gbp_awin_block(struct gbp_awin *w, const uint8_t *bytes, uint32_t len,
                    uint64_t cycle, int completed)
{
    int idx;
    struct gbp_awin_anchor *a;
    uint8_t *dst;

    if (!w) return;
    w->blocks_seen++;
    idx = w->active;
    if (idx < 0 || !w->store) { w->blocks_ignored++; return; }
    a = &w->anchor[idx];
    if (!completed || !bytes || len != w->block_size) {
        /* A drain that did not complete carries no bytes worth keeping. It is
         * counted, the window is flagged, and the window does NOT advance: the
         * blocks that follow are still consecutive drains, and the flag is what
         * tells the analysis they are no longer consecutive in time. */
        w->blocks_failed++;
        a->skipped++;
        a->flags |= GBP_AWIN_F_GAP;
        return;
    }
    dst = w->store + (size_t)idx * GBP_AWIN_WINDOW_BYTES + (size_t)w->filled * w->block_size;
    memcpy(dst, bytes, len);
    if (w->filled == 0u) a->first_cycle = cycle;
    a->last_cycle = cycle;
    w->filled++;
    a->blocks = w->filled;
    w->blocks_stored++;
    if (w->filled >= w->blocks_per_window) {
        a->flags |= GBP_AWIN_F_CLOSED;
        w->windows_closed++;
        w->active = -1;          /* CLEARED here and nowhere else */
    }
}

void gbp_awin_note_ticks(struct gbp_awin *w, uint32_t dt)
{
    if (!w) return;
    if (w->ticks_n == 0u || dt < w->ticks_min) w->ticks_min = dt;
    if (dt > w->ticks_max) w->ticks_max = dt;
    w->ticks_n++;
    w->ticks_sum += (uint64_t)dt;
}

void gbp_awin_finish(struct gbp_awin *w)
{
    int idx;
    if (!w) return;
    idx = w->active;
    if (idx < 0) return;
    w->anchor[idx].flags |= GBP_AWIN_F_INCOMPLETE;
    w->active = -1;
}

int gbp_awin_complete(const struct gbp_awin *w)
{
    unsigned i;
    if (!w || !w->store) return 0;
    for (i = 1u; i <= GBP_AWIN_PRESS_WINDOWS; i++)
        if (!(w->anchor[i].flags & GBP_AWIN_F_CLOSED)) return 0;
    return 1;
}

unsigned gbp_awin_ticks_mean(const struct gbp_awin *w)
{
    if (!w || w->ticks_n == 0u) return 0u;
    return (unsigned)(w->ticks_sum / (uint64_t)w->ticks_n);
}

const uint8_t *gbp_awin_window_bytes(const struct gbp_awin *w, unsigned index)
{
    if (!w || !w->store || index >= w->windows) return 0;
    return w->store + (size_t)index * GBP_AWIN_WINDOW_BYTES;
}

uint32_t gbp_awin_stored_total(const struct gbp_awin *w)
{
    uint32_t n = 0u;
    unsigned i;
    if (!w) return 0u;
    for (i = 0; i < w->windows; i++) n += w->anchor[i].blocks;
    return n;
}
