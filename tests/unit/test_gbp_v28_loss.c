/*
 * tests/unit/test_gbp_v28_loss.c -- GitHub Issue #137 (U-GBP-050): gbp_v28_loss, the loss diagnostic's phase handler, against the
 * REAL gbp_atrans2/gbp_aplay2/gbp_adec2 chain (the handler calls gbp_atrans2_begin() itself, so its entries can only be proven
 * against it) -- the harness shape of test_gbp_v28_3b.c: one tick per pump call, 125 calls a hand-off period, TB_HZ = 125 so a
 * "second" of the plan is one period.
 *
 * What is proven: the Gray code (every consecutive pair of holds, wrap included, differs in exactly ONE factor; all four cells; the
 * baseline outside a CELL), the histograms' bins, the whole sequence (14 holds, their kinds, arms, durations, counter deltas, the
 * late snapshot, a fresh histogram per hold), the AHEAD-1 hold's own entry, the underrun path (counted, never ends a hold), a
 * cut (partial; the arms restored), and the refusals (an entry refused while a transition runs; hold_done() with nothing pending).
 */
#include <stdio.h>
#include <string.h>
#include "gbp_v28_loss.h"
#include "gbp_v28_ladder.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) { failures++; printf("  FAIL: %s: got %lld, want %lld\n", what, got, want); }
}

static void check(int cond, const char *what)
{
    checks++;
    if (!cond) { failures++; printf("  FAIL: %s\n", what); }
}

static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t ring[GBP_APLAY2_RING];
static int16_t keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events[GBP_APLAY2_EVENTS_CAP];
static struct gbp_aplay2 ap;
static struct gbp_adec2 adec;
static struct gbp_atrans2 tr;
static struct gbp_v28_hist hist[GBP_V28_NHIST];
static struct gbp_v28_loss_ctr ctr;

#define CALLS_PER_PERIOD 125u
#define TB_HZ CALLS_PER_PERIOD

static void give2(struct gbp_adec2 *d, uint32_t n, int16_t v)
{
    uint32_t k;
    for (k = 0; k < n && d->count < d->cap; k++) {
        d->ring[(d->head + d->count) % d->cap] = v;
        d->count++;
    }
}

static uint32_t slice2(uint32_t k)
{
    return (k + 1u) * GBP_APLAY2_PUSHES / CALLS_PER_PERIOD - k * GBP_APLAY2_PUSHES / CALLS_PER_PERIOD;
}

static void pump2(uint64_t now)
{
    int b;
    if (tr.active) (void)gbp_atrans2_step(&tr, &ap, &adec, now, &b);
    else b = gbp_aplay2_produce(&ap, &adec);
    if (b >= 0) gbp_aplay2_queue(&ap, b);
    gbp_aplay2_process(&ap);
}

static void prime_period2(uint64_t *now)
{
    uint32_t k;
    int done = 0;
    for (k = 0; k < CALLS_PER_PERIOD; k++) {
        give2(&adec, slice2(k), 100);
        if (!done) {
            int b = gbp_aplay2_produce(&ap, &adec);
            if (b >= 0) { gbp_aplay2_queue(&ap, b); done = 1; }
        }
        gbp_aplay2_process(&ap);
        (*now)++;
    }
}

/* the chain steady at AHEAD 4 and `from`, what navigate leaves */
static uint64_t steady(uint32_t from)
{
    uint64_t now = 0;
    uint32_t i, k;
    memset(&ap, 0, sizeof ap);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    gbp_atrans2_init(&tr);
    ap.ahead = GBP_V28_A4;
    gbp_aplay2_set_target(&ap, from);
    give2(&adec, from * GBP_V28_A4, 100);
    for (i = 0; i < GBP_V28_A4; i++) prime_period2(&now);
    ap.playing = 1u;
    for (i = 0; i < 6u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(now); now++; }
    }
    return now;
}

static void snap(void)
{
    ctr.blocks_in++;
    ctr.taps++;
    ctr.underruns = ap.underruns;
    ctr.dup = ap.dup;
    ctr.drop = ap.drop;
    ctr.produced = ap.produced;
    ctr.handed = ap.handed;
    ctr.ring = adec.count;
}

/* one pump call: feed, the handler's own tick, the slot's produce/step, a histogram note; HOLD_DONE is acknowledged like main.c */
static int step_one(struct gbp_v28_loss *s, uint64_t now)
{
    int f;
    give2(&adec, slice2((uint32_t)(now % CALLS_PER_PERIOD)), 100);
    snap();
    f = gbp_v28_loss_tick(s, &tr, &ap, &adec, now, &ctr, hist);
    pump2(now);
    gbp_v28_hist_note(&hist[GBP_V28_H_TAP], 500u);
    if (f & GBP_V28_LOSS_TICK_HOLD_DONE) gbp_v28_loss_hold_done(s);
    return f;
}

static int run_periods(struct gbp_v28_loss *s, uint64_t *now, uint32_t periods)
{
    uint32_t i, k;
    int f = 0;
    for (i = 0; i < periods; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, *now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { f = step_one(s, *now); (*now)++; }
    }
    return f;
}

static void reset_counters(void)
{
    memset(&ctr, 0, sizeof ctr);
    gbp_v28_hists_init(hist);
}

/* ---- the cells ---------------------------------------------------------------------------------- */
static void test_the_cells_are_a_single_flip_walk_balanced_against_drift(void)
{
    const uint32_t n = GBP_V28_LOSS_CYCLES * GBP_V28_LOSS_CELLS;
    uint32_t k, seen[4] = {0, 0, 0, 0};
    long lsum1 = 0, lsum0 = 0, ssum1 = 0, ssum0 = 0;
    uint8_t l0, s0, l1, s1;
    for (k = 0; k < n; k++) {
        check(gbp_v28_loss_cell(k, &l0, &s0) == 1, "every cell index below CYCLES x CELLS resolves");
        if (k + 1u < n) {
            (void)gbp_v28_loss_cell(k + 1u, &l1, &s1);
            eqi((l0 != l1) + (s0 != s1), 1, "consecutive cells differ in exactly ONE factor");
        }
        seen[(l0 << 1) | s0]++;
        if (l0) lsum1 += (long)k; else lsum0 += (long)k;
        if (s0) ssum1 += (long)k; else ssum0 += (long)k;
    }
    for (k = 0; k < 4u; k++) eqi(seen[k], GBP_V28_LOSS_CYCLES, "every one of the four cells is visited three times");
    (void)gbp_v28_loss_cell(0u, &l0, &s0);
    check(l0 == 1u && s0 == 1u, "the sequence starts at the baseline (L,S)");
    /* against a linear drift of d points a hold, a factor's effect is biased by d x (mean position of its high level minus its low level) */
    eqi(lsum1 - lsum0, 0, "the label is exactly balanced against a linear drift (the plain cycle's offset was -12)");
    eqi(ssum1 - ssum0, -4, "the step is balanced to 4 hold-positions (a bias of 2d/3 points, against the label's 2d in the plain cycle)");
    check(gbp_v28_loss_cell(n, &l0, &s0) == 0, "past the sequence: refused");
}

/* ---- the histograms ------------------------------------------------------------------------------- */
static void test_a_zeroed_handler_is_the_baseline(void)
{
    struct gbp_v28_loss z;
    memset(&z, 0, sizeof z);
    eqi(z.label_off, 0, "before start() the label is ON (the production image)");
    eqi(z.step_half, 0, "before start() the step is the production 128");
}

static void test_the_histograms(void)
{
    struct gbp_v28_hist h[GBP_V28_NHIST];
    gbp_v28_hists_init(h);
    eqi(h[GBP_V28_H_TAP].edge[0], 1000, "tap edges start at 1k");
    eqi(h[GBP_V28_H_TAP].edge[3], 8000, "tap edges end at 8k");
    eqi(h[GBP_V28_H_GAP].edge[0], 14831, "the tap gap sits half-way between block periods (9 887.45 ticks): 1.5 periods");
    eqi(h[GBP_V28_H_GAP].edge[3], 44494, "...up to 4.5 periods");
    gbp_v28_hist_note(&h[GBP_V28_H_TAP], 1000u);      /* on the edge: the LOWER bin */
    gbp_v28_hist_note(&h[GBP_V28_H_TAP], 1001u);
    gbp_v28_hist_note(&h[GBP_V28_H_TAP], 8000u);
    gbp_v28_hist_note(&h[GBP_V28_H_TAP], 8001u);
    gbp_v28_hist_note(&h[GBP_V28_H_TAP], 0xFFFFFFFFu);
    eqi(h[GBP_V28_H_TAP].bin[0], 1, "1000 is <= 1k");
    eqi(h[GBP_V28_H_TAP].bin[1], 1, "1001 is <= 2k");
    eqi(h[GBP_V28_H_TAP].bin[3], 1, "8000 is <= 8k");
    eqi(h[GBP_V28_H_TAP].bin[4], 2, "8001 and beyond are > 8k");
    eqi(h[GBP_V28_H_TAP].count, 5, "count");
    eqi(h[GBP_V28_H_TAP].max, (long long)0xFFFFFFFFu, "max");
    check(h[GBP_V28_H_TAP].sum == 1000ull + 1001ull + 8000ull + 8001ull + 0xFFFFFFFFull, "the sum is 64-bit");
    gbp_v28_hists_clear(h);
    eqi(h[GBP_V28_H_TAP].count, 0, "clear zeroes the count");
    eqi(h[GBP_V28_H_TAP].edge[2], 4000, "clear KEEPS the edges");
    eqi(h[GBP_V28_H_PUMP].edge[3], 16000, "the pump call's edges survive a clear");
}

/* ---- the whole sequence ------------------------------------------------------------------------------ */
static void test_the_whole_sequence(void)
{
    struct gbp_v28_loss s;
    uint64_t now = steady(GBP_V28_T704);
    uint32_t i, guard = 0;
    int f = 0;
    reset_counters();
    gbp_v28_loss_start(&s, TB_HZ, now);
    check(s.begin_pending == 1u, "start() only decides the entry");
    eqi(s.label_off, 0, "baseline label on");
    eqi(s.step_half, 0, "baseline step full");
    while (!(f & GBP_V28_LOSS_TICK_PHASE_COMPLETE) && guard++ < 400u) f = run_periods(&s, &now, 1u);
    check(f & GBP_V28_LOSS_TICK_PHASE_COMPLETE, "the phase completes");
    check(gbp_v28_loss_finished(&s), "finished");
    eqi(s.holds_n, GBP_V28_LOSS_HOLDS_MAX, "warm + 12 cells + final = 14 holds");
    eqi(s.refused_hold_done, 0, "no hold_done() was refused");
    for (i = 0; i < s.holds_n; i++) {
        const struct gbp_v28_loss_hold *h = gbp_v28_loss_hold_record(&s, i);
        const uint64_t dur = h->t_end - h->t_start;
        uint64_t want;
        uint8_t l, sf;
        eqi(h->partial, 0, "no hold is partial in a whole run");
        eqi(h->target, GBP_V28_T256, "every hold is at the one fixed TARGET");
        if (i == 0u) {
            eqi(h->kind, GBP_V28_LOSS_WARM, "hold 0 is the warm-up");
            want = GBP_V28_LOSS_WARM_S;
            check(h->label_on == 1u && h->step_full == 1u, "the warm-up is at the baseline");
            eqi(h->ahead, GBP_V28_A4, "the warm-up is at AHEAD 4");
        } else if (i < GBP_V28_LOSS_HOLDS_MAX - 1u) {
            eqi(h->kind, GBP_V28_LOSS_CELL, "holds 1..12 are cells");
            want = GBP_V28_LOSS_HOLD_S;
            (void)gbp_v28_loss_cell(i - 1u, &l, &sf);
            check(h->label_on == l && h->step_full == sf, "a cell hold carries the Gray code's own cell");
            eqi(h->cyc, (i - 1u) / GBP_V28_LOSS_CELLS, "the cycle index");
            eqi(h->ahead, GBP_V28_A4, "the cells are at AHEAD 4");
        } else {
            eqi(h->kind, GBP_V28_LOSS_FINAL, "the last hold is the final one");
            want = GBP_V28_LOSS_FINAL_S;
            check(h->label_on == 1u && h->step_full == 1u, "the final hold is at the baseline (both arms at baseline)");
            eqi(h->ahead, GBP_V28_A1, "the final hold is at AHEAD 1");
        }
        check(dur >= want * TB_HZ && dur < want * TB_HZ + CALLS_PER_PERIOD, "a hold lasts its own seconds");
        check(h->has_late == 1u, "the late snapshot was taken");
        check(h->t_late >= h->t_start + (uint64_t)GBP_V28_LOSS_LATE_S * TB_HZ &&
              h->t_late < h->t_start + (uint64_t)GBP_V28_LOSS_LATE_S * TB_HZ + 2u, "the late snapshot sits LATE_S after the start");
        eqi(h->c_end.blocks_in - h->c_start.blocks_in, (long long)dur, "the counters' deltas are the hold's own span");
        check(h->c_late.blocks_in >= h->c_start.blocks_in && h->c_late.blocks_in <= h->c_end.blocks_in, "late is between start and end");
        /* a fresh histogram: one note a tick since THIS hold's start, never cumulative */
        check(h->hist[GBP_V28_H_TAP].count >= dur - 1u && h->hist[GBP_V28_H_TAP].count <= dur + 1u,
              "the hold's histogram counts ITS OWN ticks only (cleared at the hold's start)");
        eqi(h->hist[GBP_V28_H_TAP].edge[1], 2000, "the copied histogram carries its edges");
        if (i > 0u) {
            const struct gbp_v28_loss_hold *pv = gbp_v28_loss_hold_record(&s, i - 1u);
            check(h->t_start >= pv->t_end, "holds never overlap");
            check(h->t_start - pv->t_end <= 2u || h->kind == GBP_V28_LOSS_FINAL, "consecutive cells are contiguous (a tick apart)");
            if (h->kind == GBP_V28_LOSS_CELL && pv->kind == GBP_V28_LOSS_CELL)
                eqi((h->label_on != pv->label_on) + (h->step_full != pv->step_full), 1, "consecutive HOLDS differ in exactly one factor");
        }
    }
    eqi(ap.ahead, GBP_V28_A1, "the chain ends at AHEAD 1");
    eqi(s.label_off, 0, "the arms end at the baseline");
    eqi(s.step_half, 0, "...both of them");
}

/* the final entry runs at the baseline cell, never on an arm, even though the last CELL hold is (l,S) */
static void test_the_final_entry_is_at_the_baseline(void)
{
    struct gbp_v28_loss s;
    uint64_t now = steady(GBP_V28_T704);
    uint32_t guard = 0;
    int in_entry_seen = 0;
    reset_counters();
    gbp_v28_loss_start(&s, TB_HZ, now);
    while (!gbp_v28_loss_finished(&s) && guard++ < 40000u) {
        (void)step_one(&s, now);
        if (guard % CALLS_PER_PERIOD == 0u) (void)gbp_aplay2_irq_handoff(&ap, now);
        now++;
        if ((s.begin_pending || s.landing) && s.entry_final) {
            in_entry_seen = 1;
            eqi(s.label_off, 0, "during the final entry the label is at the baseline");
            eqi(s.step_half, 0, "during the final entry the step is at the baseline");
        }
    }
    check(in_entry_seen, "the final entry was observed");
}

/* ---- the underrun path ----------------------------------------------------------------------------- */
static void test_the_underrun_path_counts_and_never_ends_a_hold(void)
{
    struct gbp_v28_loss s;
    uint64_t now = steady(GBP_V28_T704);
    uint32_t i;
    reset_counters();
    gbp_v28_loss_start(&s, TB_HZ, now);
    gbp_v28_loss_underrun_observed(&s, now);
    eqi(s.cur_hooks, 0, "before any hold: a no-op");
    while (!s.hold_active) { (void)step_one(&s, now); now++; }
    for (i = 0; i < 5u; i++) gbp_v28_loss_underrun_observed(&s, now);
    eqi(s.cur_hooks, 5, "counted into the hold in progress");
    check(s.hold_active == 1u, "and the hold is NOT ended by it (the final hold's count is the measurement)");
    (void)run_periods(&s, &now, GBP_V28_LOSS_WARM_S + 1u);
    eqi(gbp_v28_loss_hold_record(&s, 0u)->underrun_hooks, 5, "the record carries the count");
    eqi(s.cur_hooks, 0, "the next hold starts at zero");
}

/* ---- a cut ------------------------------------------------------------------------------------------ */
static void test_a_cut_hold_is_partial_and_the_arms_are_restored(void)
{
    struct gbp_v28_loss s;
    uint64_t now = steady(GBP_V28_T704);
    reset_counters();
    gbp_v28_loss_start(&s, TB_HZ, now);
    /* run into the second CELL hold, the label arm (l,S) */
    while (s.next_index < 3u || !s.hold_active) { (void)step_one(&s, now); now++; }
    check(s.label_off == 1u && s.step_half == 0u, "in CELL 1 the label arm is on (l,S)");
    (void)run_periods(&s, &now, 1u);              /* < LATE_S: no late snapshot yet */
    snap();
    gbp_v28_loss_cut(&s, now, &ctr, hist);
    check(gbp_v28_loss_finished(&s), "a cut finishes the phase");
    check(s.hold_pending == 1u, "the hold is pending its acknowledgement");
    eqi(s.label_off, 0, "the arms are back at the baseline after a cut");
    eqi(s.step_half, 0, "...both of them");
    gbp_v28_loss_hold_done(&s);
    eqi(s.holds_n, 3, "warm, one whole cell, the cut cell");
    check(gbp_v28_loss_hold_record(&s, 2u)->partial == 1u, "the cut hold is partial");
    check(gbp_v28_loss_hold_record(&s, 2u)->has_late == 0u, "cut before its late mark: no late snapshot, and it says so");
    check(gbp_v28_loss_hold_record(&s, 1u)->partial == 0u, "the earlier hold stays whole");
    eqi(gbp_v28_loss_tick(&s, &tr, &ap, &adec, now, &ctr, hist), GBP_V28_LOSS_TICK_PHASE_COMPLETE, "tick() reports the phase over");
    eqi(s.starting, 0, "nothing follows a cut");
}

static void test_a_cut_during_the_entry_records_nothing(void)
{
    struct gbp_v28_loss s;
    uint64_t now = steady(GBP_V28_T704);
    reset_counters();
    gbp_v28_loss_start(&s, TB_HZ, now);
    gbp_v28_loss_cut(&s, now, &ctr, hist);
    eqi(s.hold_pending, 0, "no hold was running: nothing pending");
    eqi(s.holds_n, 0, "and nothing recorded");
    check(gbp_v28_loss_finished(&s), "finished");
    gbp_v28_loss_hold_done(&s);
    eqi(s.refused_hold_done, 1, "hold_done() with nothing pending is counted, never silent");
}

/* ---- an entry refused while a transition runs ----------------------------------------------------------- */
static void test_the_entry_waits_for_a_running_transition(void)
{
    struct gbp_v28_loss s;
    uint64_t now = steady(GBP_V28_T704);
    int b;
    uint32_t n = 0;
    reset_counters();
    check(gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_UNMUTED, 0u, 0u, 2048u, GBP_V28_T704 - 2048u, GBP_V28_A4) == 1,
          "a foreign plan is running");
    gbp_v28_loss_start(&s, TB_HZ, now);
    (void)gbp_v28_loss_tick(&s, &tr, &ap, &adec, now, &ctr, hist);
    check(s.begin_pending == 1u, "the entry is refused while a transition runs");
    check(s.begin_pending_ticks >= 1u, "and counts its refusals");
    check(s.hold_active == 0u, "no hold starts on a refused entry");
    while (tr.active && n++ < 100000u) { (void)gbp_atrans2_step(&tr, &ap, &adec, now, &b); if (b >= 0) gbp_aplay2_queue(&ap, b); now++; }
    (void)run_periods(&s, &now, 3u);
    check(s.hold_active == 1u || s.holds_n > 0u, "once the foreign plan lands the entry begins and the warm-up starts");
    eqi(ap.ahead, GBP_V28_A4, "AHEAD 4 stated by the entry");
    eqi(tr.target, GBP_V28_T256, "at the loss TARGET");
}

int main(void)
{
    printf("test_gbp_v28_loss\n");
    test_the_cells_are_a_single_flip_walk_balanced_against_drift();
    test_a_zeroed_handler_is_the_baseline();
    test_the_histograms();
    test_the_whole_sequence();
    test_the_final_entry_is_at_the_baseline();
    test_the_underrun_path_counts_and_never_ends_a_hold();
    test_a_cut_hold_is_partial_and_the_arms_are_restored();
    test_a_cut_during_the_entry_records_nothing();
    test_the_entry_waits_for_a_running_transition();
    printf("  %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
