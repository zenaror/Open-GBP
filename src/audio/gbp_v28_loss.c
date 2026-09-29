/*
 * gbp_v28_loss -- see gbp_v28_loss.h.
 */
#include <string.h>
#include "gbp_v28_loss.h"
#include "gbp_v28_ladder.h"

#define GBP_V28_LOSS_TARGET GBP_V28_T256      /* 4096: the anchor's own default, 62.5 ms */

static const uint32_t EDGES_COST[GBP_V28_HIST_BINS - 1u] = {1000u, 2000u, 4000u, 8000u};
static const uint32_t EDGES_PUMP[GBP_V28_HIST_BINS - 1u] = {2000u, 4000u, 8000u, 16000u};
/* the tap gap: half-way between whole block periods (9 887.45 ticks at 40.5 MHz / 4096), 1.5, 2.5, 3.5 and 4.5 periods, so a gap that
 * skipped k blocks falls in its own bin and read-latency jitter of a few hundred ticks cannot move it across an edge */
static const uint32_t EDGES_GAP[GBP_V28_HIST_BINS - 1u]  = {14831u, 24719u, 34606u, 44494u};

void gbp_v28_hist_init(struct gbp_v28_hist *h, const uint32_t edge[GBP_V28_HIST_BINS - 1u])
{
    uint32_t i;
    memset(h, 0, sizeof *h);
    for (i = 0; i < GBP_V28_HIST_BINS - 1u; i++) h->edge[i] = edge[i];
}

void gbp_v28_hist_note(struct gbp_v28_hist *h, uint32_t ticks)
{
    uint32_t i = 0u;
    while (i < GBP_V28_HIST_BINS - 1u && ticks > h->edge[i]) i++;
    h->bin[i]++;
    h->count++;
    h->sum += ticks;
    if (ticks > h->max) h->max = ticks;
}

void gbp_v28_hists_init(struct gbp_v28_hist h[GBP_V28_NHIST])
{
    gbp_v28_hist_init(&h[GBP_V28_H_TAP], EDGES_COST);
    gbp_v28_hist_init(&h[GBP_V28_H_DECODE], EDGES_COST);
    gbp_v28_hist_init(&h[GBP_V28_H_PROD], EDGES_COST);
    gbp_v28_hist_init(&h[GBP_V28_H_PUMP], EDGES_PUMP);
    gbp_v28_hist_init(&h[GBP_V28_H_LABEL], EDGES_COST);
    gbp_v28_hist_init(&h[GBP_V28_H_GAP], EDGES_GAP);
}

void gbp_v28_hists_clear(struct gbp_v28_hist h[GBP_V28_NHIST])
{
    uint32_t i;
    for (i = 0; i < GBP_V28_NHIST; i++) {
        uint32_t e[GBP_V28_HIST_BINS - 1u], k;
        for (k = 0; k < GBP_V28_HIST_BINS - 1u; k++) e[k] = h[i].edge[k];
        gbp_v28_hist_init(&h[i], e);
    }
}

int gbp_v28_loss_cell(uint32_t k, uint8_t *label_on, uint8_t *step_full)
{
    /* The twelve cells, (L,S): each step flips exactly ONE factor, each of the four cells is visited three times, it starts at the
     * baseline, and the label-on holds' positions sum to 33 like the label-off holds' (see the header for why it is not the plain
     * cycle). tests/unit/test_gbp_v28_loss.c checks every one of these properties from this table. */
    static const uint8_t L[GBP_V28_LOSS_CYCLES * GBP_V28_LOSS_CELLS] = {1u, 0u, 0u, 1u, 1u, 0u, 0u, 1u, 0u, 1u, 1u, 0u};
    static const uint8_t S[GBP_V28_LOSS_CYCLES * GBP_V28_LOSS_CELLS] = {1u, 1u, 0u, 0u, 1u, 1u, 0u, 0u, 0u, 0u, 1u, 1u};
    if (k >= GBP_V28_LOSS_CYCLES * GBP_V28_LOSS_CELLS) return 0;
    *label_on = L[k];
    *step_full = S[k];
    return 1;
}

void gbp_v28_loss_start(struct gbp_v28_loss *s, uint32_t tb_hz, uint64_t now)
{
    memset(s, 0, sizeof *s);
    s->tb_hz = tb_hz;
    s->begin_pending = 1u;
    (void)now;
}

void gbp_v28_loss_underrun_observed(struct gbp_v28_loss *s, uint64_t now)
{
    (void)now;
    if (s->hold_active) s->cur_hooks++;
}

static void start_hold(struct gbp_v28_loss *s, uint64_t now, const struct gbp_v28_loss_ctr *c,
                       struct gbp_v28_hist hist[GBP_V28_NHIST])
{
    const uint32_t idx = s->next_index++;
    struct gbp_v28_loss_hold *h = &s->cur;
    uint32_t dur_s;
    memset(h, 0, sizeof *h);
    h->label_on = 1u;
    h->step_full = 1u;
    h->ahead = (uint8_t)GBP_V28_A4;
    if (idx == 0u) {
        h->kind = GBP_V28_LOSS_WARM;
        dur_s = GBP_V28_LOSS_WARM_S;
    } else if (idx <= GBP_V28_LOSS_CYCLES * GBP_V28_LOSS_CELLS) {
        const uint32_t k = idx - 1u;
        h->kind = GBP_V28_LOSS_CELL;
        h->cyc = (uint8_t)(k / GBP_V28_LOSS_CELLS);
        (void)gbp_v28_loss_cell(k, &h->label_on, &h->step_full);
        dur_s = GBP_V28_LOSS_HOLD_S;
    } else {
        h->kind = GBP_V28_LOSS_FINAL;
        h->ahead = (uint8_t)GBP_V28_A1;
        dur_s = GBP_V28_LOSS_FINAL_S;
    }
    h->target = GBP_V28_LOSS_TARGET;       /* the INTENT; the observed operating point is in c_start/c_late/c_end (target, ahead) */
    h->t_start = now;
    h->c_start = *c;
    s->label_off = (uint8_t)(h->label_on ? 0u : 1u);
    s->step_half = (uint8_t)(h->step_full ? 0u : 1u);
    s->late_taken = 0u;
    s->cur_hooks = 0u;
    s->t_late_at = now + (uint64_t)GBP_V28_LOSS_LATE_S * s->tb_hz;
    s->t_hold_end = now + (uint64_t)dur_s * s->tb_hz;
    s->hold_active = 1u;
    gbp_v28_hists_clear(hist);
}

static void end_hold(struct gbp_v28_loss *s, uint64_t now, const struct gbp_v28_loss_ctr *c,
                     const struct gbp_v28_hist hist[GBP_V28_NHIST], uint8_t partial)
{
    struct gbp_v28_loss_hold *h = &s->cur;
    h->t_end = now;
    h->c_end = *c;
    h->partial = partial;
    h->underrun_hooks = s->cur_hooks;
    memcpy(h->hist, hist, sizeof h->hist);
    s->hold_active = 0u;
    s->hold_pending = 1u;
}

int gbp_v28_loss_tick(struct gbp_v28_loss *s, struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d,
                      uint64_t now, const struct gbp_v28_loss_ctr *c, struct gbp_v28_hist hist[GBP_V28_NHIST])
{
    if (s->finished) return GBP_V28_LOSS_TICK_PHASE_COMPLETE;
    if (s->hold_pending) return GBP_V28_LOSS_TICK_HOLD_DONE;

    if (s->begin_pending) {
        int ok;
        if (!s->entry_final) {
            /* 3a's own first begin: UNMUTED, the ring's level moved by one discard (or a pause), AHEAD 4 stated */
            const uint32_t from = t->target, to = GBP_V28_LOSS_TARGET;
            const uint32_t pause = (to > from) ? (to - from + GBP_APLAY2_PUSHES - 1u) / GBP_APLAY2_PUSHES : 0u;
            const uint32_t discard = (to < from) ? from - to : 0u;
            ok = gbp_atrans2_begin(t, p, d, now, GBP_ATRANS2_UNMUTED, 0u, pause, discard, to, GBP_V28_A4);
        } else {
            /* 3b's own entry: ROTATE at the step mute, AHEAD 4 -> 1 at the same target */
            ok = gbp_atrans2_begin(t, p, d, now, GBP_ATRANS2_ROTATE, GBP_V28_STEP_MUTE, 0u, 0u,
                                   GBP_V28_LOSS_TARGET, GBP_V28_A1);
        }
        if (!ok) {
            s->begin_pending_ticks++;
            return 0;
        }
        s->begin_pending = 0u;
        s->landing = 1u;
        return 0;
    }
    if (s->landing) {
        if (t->active) return 0;
        s->landing = 0u;
        start_hold(s, now, c, hist);
        return 0;
    }
    if (s->starting) {
        s->starting = 0u;
        start_hold(s, now, c, hist);
        return 0;
    }
    if (s->hold_active) {
        if (!s->late_taken && now >= s->t_late_at) {
            s->cur.t_late = now;
            s->cur.c_late = *c;
            s->cur.has_late = 1u;
            s->late_taken = 1u;
        }
        if (now >= s->t_hold_end) {
            end_hold(s, now, c, hist, 0u);
            return GBP_V28_LOSS_TICK_HOLD_DONE;
        }
    }
    return 0;
}

void gbp_v28_loss_hold_done(struct gbp_v28_loss *s)
{
    if (!s->hold_pending) {
        s->refused_hold_done++;
        return;
    }
    s->hold_pending = 0u;
    if (s->holds_n < GBP_V28_LOSS_HOLDS_MAX) s->holds[s->holds_n++] = s->cur;
    if (s->finished) return;                     /* cut: nothing follows */
    if (s->cur.kind == GBP_V28_LOSS_FINAL) {
        s->finished = 1u;
    } else if (s->next_index <= GBP_V28_LOSS_CYCLES * GBP_V28_LOSS_CELLS) {
        s->starting = 1u;                        /* the next cell starts on the next tick, the arms change there */
    } else {
        /* the cells are done: the final entry runs at the baseline cell, never on an arm */
        s->label_off = 0u;
        s->step_half = 0u;
        s->entry_final = 1u;
        s->begin_pending = 1u;
    }
}

void gbp_v28_loss_cut(struct gbp_v28_loss *s, uint64_t t_end, const struct gbp_v28_loss_ctr *c,
                      const struct gbp_v28_hist hist[GBP_V28_NHIST])
{
    if (s->hold_active) end_hold(s, t_end, c, hist, 1u);   /* still reportable, partial */
    s->begin_pending = 0u;                                 /* an entry decided but never begun: abandoned */
    s->landing = 0u;
    s->starting = 0u;
    s->label_off = 0u;
    s->step_half = 0u;                                     /* the arms never outlive the phase */
    s->finished = 1u;
}

int gbp_v28_loss_finished(const struct gbp_v28_loss *s)
{
    return s->finished;
}

const struct gbp_v28_loss_hold *gbp_v28_loss_hold_record(const struct gbp_v28_loss *s, uint32_t index)
{
    return index < s->holds_n ? &s->holds[index] : (const struct gbp_v28_loss_hold *)0;
}
