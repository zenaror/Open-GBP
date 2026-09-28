/*
 * gbp_v28_sweep -- see gbp_v28_sweep.h.
 */
#include <string.h>
#include "gbp_v28_sweep.h"
#include "gbp_v28_ladder.h"

struct sweep_entry {
    uint8_t  klass, mechanism;
    uint32_t from_target, from_ahead, to_target, to_ahead, mute;
};

/* The frozen sequence, exactly as gbp_v28_sweep.h's own header comment states it (Issue #129, both
 * comments). Do not reorder, add or remove an entry here without the same authority that froze the
 * sequence in the first place. */
static const struct sweep_entry TABLE[GBP_V28_SWEEP_N] = {
    /* INFO -- PRELUDE (Issue #135): 3b's own end state (the anchor T256 at AHEAD 1) to the (T704, A4)
     * the 27 frozen entries below assume. The same START as GATE row 18's own T256A1 -> T704A4. */
    { GBP_V28_SWEEP_INFO, GBP_V28_SWEEP_START, GBP_V28_T256, GBP_V28_A1, GBP_V28_T704, GBP_V28_A4,
      GBP_V28_START_MUTE },
    /* GATE -- descend, 7 adjacent down-steps */
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T704, GBP_V28_A4, GBP_V28_T576, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T576, GBP_V28_A4, GBP_V28_T448, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T448, GBP_V28_A4, GBP_V28_T320, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T320, GBP_V28_A4, GBP_V28_T256, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T256, GBP_V28_A4, GBP_V28_T256, GBP_V28_A3, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T256, GBP_V28_A3, GBP_V28_T256, GBP_V28_A2, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T256, GBP_V28_A2, GBP_V28_T256, GBP_V28_A1, GBP_V28_STEP_MUTE },
    /* GATE -- one refused step at the bottom (same-level ROTATE, the grid-end case §7) */
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_REFUSED, GBP_V28_T256, GBP_V28_A1, GBP_V28_T256, GBP_V28_A1,
      GBP_V28_STEP_MUTE },
    /* GATE -- ascend, the same 7 adjacent up-steps */
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T256, GBP_V28_A1, GBP_V28_T256, GBP_V28_A2, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T256, GBP_V28_A2, GBP_V28_T256, GBP_V28_A3, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T256, GBP_V28_A3, GBP_V28_T256, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T256, GBP_V28_A4, GBP_V28_T320, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T320, GBP_V28_A4, GBP_V28_T448, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T448, GBP_V28_A4, GBP_V28_T576, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_STEP, GBP_V28_T576, GBP_V28_A4, GBP_V28_T704, GBP_V28_A4, GBP_V28_STEP_MUTE },
    /* GATE -- one refused step at the top */
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_REFUSED, GBP_V28_T704, GBP_V28_A4, GBP_V28_T704, GBP_V28_A4,
      GBP_V28_STEP_MUTE },
    /* GATE -- the largest START, both ways */
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_START, GBP_V28_T704, GBP_V28_A4, GBP_V28_T256, GBP_V28_A1,
      GBP_V28_START_MUTE },
    { GBP_V28_SWEEP_GATE, GBP_V28_SWEEP_START, GBP_V28_T256, GBP_V28_A1, GBP_V28_T704, GBP_V28_A4,
      GBP_V28_START_MUTE },
    /* INFO -- the repositioning move that opens the T192 branch (Issue #129's own second comment:
     * the main 8 rungs' own walk, and the two STARTs, both net to zero -- this is the one interior
     * move that actually gets the chain from T704A4 to T256A4) */
    { GBP_V28_SWEEP_INFO, GBP_V28_SWEEP_START, GBP_V28_T704, GBP_V28_A4, GBP_V28_T256, GBP_V28_A4,
      GBP_V28_START_MUTE },
    /* INFO -- T192, run last (D2-class splice risk, Item 4) */
    { GBP_V28_SWEEP_INFO, GBP_V28_SWEEP_STEP, GBP_V28_T256, GBP_V28_A4, GBP_V28_T192, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_INFO, GBP_V28_SWEEP_STEP, GBP_V28_T192, GBP_V28_A4, GBP_V28_T192, GBP_V28_A3, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_INFO, GBP_V28_SWEEP_STEP, GBP_V28_T192, GBP_V28_A3, GBP_V28_T192, GBP_V28_A2, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_INFO, GBP_V28_SWEEP_STEP, GBP_V28_T192, GBP_V28_A2, GBP_V28_T192, GBP_V28_A1, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_INFO, GBP_V28_SWEEP_STEP, GBP_V28_T192, GBP_V28_A1, GBP_V28_T192, GBP_V28_A2, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_INFO, GBP_V28_SWEEP_STEP, GBP_V28_T192, GBP_V28_A2, GBP_V28_T192, GBP_V28_A3, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_INFO, GBP_V28_SWEEP_STEP, GBP_V28_T192, GBP_V28_A3, GBP_V28_T192, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { GBP_V28_SWEEP_INFO, GBP_V28_SWEEP_STEP, GBP_V28_T192, GBP_V28_A4, GBP_V28_T256, GBP_V28_A4, GBP_V28_STEP_MUTE },
};

#define GATE_N   18u   /* TABLE[1..18]; TABLE[0] is the INFO prelude, TABLE[19..27] the 9-entry INFO tail */

void gbp_v28_sweep_start(struct gbp_v28_sweep *s, uint32_t tb_hz, uint64_t now)
{
    memset(s, 0, sizeof *s);
    s->tb_hz = tb_hz;
    s->begin_pending = 1u;
    (void)now;
}

static int out_of_band(uint32_t ring, uint32_t ready, uint32_t to_target, uint32_t to_ahead)
{
    if (ring > to_target) return 1;                        /* the level is aimed below target; above it is a fault */
    if (ring + GBP_APLAY2_BAND < to_target) return 1;       /* an undershoot beyond the allowed band */
    if (ready != to_ahead - 1u && ready != to_ahead) return 1;
    return 0;
}

/* Priority among co-occurring faults, most audible/severe first: an actual dropout (UNDERRUN) over
 * a splice that might be heard (UNMASKED) over a level/bookkeeping fault that may not be audible at
 * all (OUT_OF_BAND). Only one fail_reason is recorded; this is the order a co-occurrence picks. */
static void finalize_record(struct gbp_v28_sweep *s, const struct sweep_entry *e, struct gbp_aplay2 *p,
                            const struct gbp_adec2 *d, uint64_t now)
{
    struct gbp_v28_sweep_record *r = &s->records[s->records_n++];
    const uint32_t underrun_delta = p->underruns - s->underruns0;
    /* Issue #136: a cut after the first audible hand-off, from any source: the level-setting one landed late, or
     * the ring was cut at all during the dwell that follows the landing */
    const int splice = (s->cut_at_land > 0u && s->cut_rel_at_land >= 0) || d->discarded != s->disc_at_land;

    r->klass = e->klass;
    r->mechanism = e->mechanism;
    r->from_target = e->from_target;
    r->from_ahead = e->from_ahead;
    r->to_target = e->to_target;
    r->to_ahead = e->to_ahead;
    r->t_begin = s->t_begin;
    r->t_land = s->t_land;
    r->t_done = now;
    r->residue = s->residue_at_land;
    r->dup = p->dup - s->dup0;
    r->drop = p->drop - s->drop0;
    r->ahead_drops = s->ahead_drops_at_land;
    r->unmasked = s->unmasked_at_land;
    r->meas_target = s->meas_target0;
    r->meas_ahead = s->meas_ahead0;
    r->meas_ring = s->meas_ring0;
    r->meas_ready = s->meas_ready0;
    r->ring = s->ring_at_land;
    r->ready = s->ready_at_land;
    r->cut = s->cut_at_land;
    r->cut_rel = s->cut_rel_at_land;
    r->rot_post = s->rot_post_at_land;
    r->fill_short = s->fill_short_at_land;
    r->late = s->late_at_land;

    if (underrun_delta > 0u) {
        r->outcome = GBP_V28_SWEEP_FAIL;
        r->fail_reason = GBP_V28_SWEEP_FAIL_UNDERRUN;
    } else if (splice) {
        r->outcome = GBP_V28_SWEEP_FAIL;
        r->fail_reason = GBP_V28_SWEEP_FAIL_SPLICE;
    } else if (s->unmasked_at_land) {
        r->outcome = GBP_V28_SWEEP_FAIL;
        r->fail_reason = GBP_V28_SWEEP_FAIL_UNMASKED;
    } else if (out_of_band(s->ring_at_land, s->ready_at_land, e->to_target, e->to_ahead)) {
        r->outcome = GBP_V28_SWEEP_FAIL;
        r->fail_reason = GBP_V28_SWEEP_FAIL_OUT_OF_BAND;
    } else {
        r->outcome = GBP_V28_SWEEP_PASS;
        r->fail_reason = GBP_V28_SWEEP_FAIL_NONE;
    }
}

int gbp_v28_sweep_tick(struct gbp_v28_sweep *s, struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d,
                       uint64_t now)
{
    const struct sweep_entry *e;
    if (s->finished) return GBP_V28_SWEEP_TICK_PHASE_COMPLETE;
    e = &TABLE[s->index];

    if (s->begin_pending) {
        const uint32_t m_target = p->target, m_ahead = p->ahead, m_ring = d->count, m_ready = gbp_aplay2_ready(p);
        if (!gbp_atrans2_begin(t, p, d, now, GBP_ATRANS2_ROTATE, e->mute, 0u, 0u, e->to_target, e->to_ahead))
            return 0;
        s->begin_pending = 0u;
        s->t_begin = now;
        s->dup0 = p->dup;
        s->drop0 = p->drop;
        s->underruns0 = p->underruns;
        s->meas_target0 = m_target;
        s->meas_ahead0 = m_ahead;
        s->meas_ring0 = m_ring;
        s->meas_ready0 = m_ready;
        return 0;
    }

    if (!s->dwelling) {
        if (t->active) return 0;                            /* still muting/rotating */
        /* landed, this tick, for the first time -- snapshot the landing state, then dwell */
        s->ring_at_land = d->count;
        s->ready_at_land = gbp_aplay2_ready(p);
        s->residue_at_land = t->residue;
        s->ahead_drops_at_land = t->ahead_drops;
        s->unmasked_at_land = t->unmasked;
        s->cut_at_land = t->disc_n;
        s->cut_rel_at_land = t->disc_rel;
        s->rot_post_at_land = t->rot_post;
        s->fill_short_at_land = t->fill_short;
        s->disc_at_land = d->discarded;
        s->late_at_land = t->late;
        s->t_land = now;
        s->dwelling = 1u;
        s->t_dwell_end = now + (uint64_t)GBP_V28_SWEEP_DWELL_S * s->tb_hz;
        return 0;
    }

    if (now < s->t_dwell_end) return 0;                     /* still observing */

    finalize_record(s, e, p, d, now);
    s->index++;
    s->dwelling = 0u;
    if (s->index >= GBP_V28_SWEEP_N) {
        s->finished = 1u;
        return GBP_V28_SWEEP_TICK_PHASE_COMPLETE;
    }
    s->begin_pending = 1u;
    return 0;
}

void gbp_v28_sweep_cut(struct gbp_v28_sweep *s, uint64_t t_end)
{
    if (s->dwelling) {                                       /* landed, still observing: still reportable, partial */
        const struct sweep_entry *e = &TABLE[s->index];
        struct gbp_v28_sweep_record *r = &s->records[s->records_n++];
        r->klass = e->klass;
        r->mechanism = e->mechanism;
        r->from_target = e->from_target;
        r->from_ahead = e->from_ahead;
        r->to_target = e->to_target;
        r->to_ahead = e->to_ahead;
        r->t_begin = s->t_begin;
        r->t_land = s->t_land;
        r->t_done = t_end;
        r->residue = s->residue_at_land;
        r->dup = 0u;                                          /* the caller's own `p` is not handed to cut() --
                                                                * the dup/drop delta over a cut dwell is not
                                                                * knowable here; a PARTIAL record already tells
                                                                * the reader not to trust it as a full PASS */
        r->drop = 0u;
        r->ahead_drops = s->ahead_drops_at_land;
        r->unmasked = s->unmasked_at_land;
        r->meas_target = s->meas_target0;
        r->meas_ahead = s->meas_ahead0;
        r->meas_ring = s->meas_ring0;
        r->meas_ready = s->meas_ready0;
        r->ring = s->ring_at_land;
        r->ready = s->ready_at_land;
        r->cut = s->cut_at_land;
        r->cut_rel = s->cut_rel_at_land;
        r->rot_post = s->rot_post_at_land;
        r->fill_short = s->fill_short_at_land;
        r->late = s->late_at_land;
        r->outcome = GBP_V28_SWEEP_PARTIAL;
        r->fail_reason = GBP_V28_SWEEP_FAIL_NONE;
    }                                                          /* begin_pending (decided, not yet begun): abandoned,
                                                                * nothing to report -- gbp_v28_3a/3b's own reasoning */
    s->begin_pending = 0u;
    s->dwelling = 0u;
    s->finished = 1u;
}

int gbp_v28_sweep_finished(const struct gbp_v28_sweep *s)
{
    return s && s->finished;
}

const struct gbp_v28_sweep_record *gbp_v28_sweep_record_at(const struct gbp_v28_sweep *s, uint32_t index)
{
    if (!s || index >= s->records_n) return NULL;
    return &s->records[index];
}

enum gbp_v28_sweep_verdict gbp_v28_sweep_verdict(const struct gbp_v28_sweep *s)
{
    uint32_t i;
    if (!s || s->records_n < GBP_V28_SWEEP_PRELUDE_N + GATE_N) return GBP_V28_SWEEP_VERDICT_PENDING;
    for (i = 0; i < GBP_V28_SWEEP_PRELUDE_N + GATE_N; i++) {
        if (s->records[i].klass != GBP_V28_SWEEP_GATE) continue;   /* the INFO prelude never folds in */
        if (s->records[i].outcome != GBP_V28_SWEEP_PASS) return GBP_V28_SWEEP_VERDICT_FAIL;
    }
    return GBP_V28_SWEEP_VERDICT_PASS;
}
