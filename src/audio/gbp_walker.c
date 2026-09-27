/*
 * gbp_walker — see gbp_walker.h.
 */
#include "gbp_walker.h"

#include <string.h>

static int plan_is_valid(const struct gbp_walker_plan *plan)
{
    uint32_t i;
    if (!plan || !plan->phases || plan->count == 0u || plan->count > GBP_WALKER_MAX_PHASES) return 0;
    if (plan->session_cap_s == 0u) return 0;
    for (i = 0; i < plan->count; i++)
        if (plan->phases[i].cap_s == 0u) return 0;
    return 1;
}

static void begin_phase(struct gbp_walker *w, uint32_t index, uint64_t t)
{
    w->index = index;
    w->rec[index].started = 1u;
    w->rec[index].t_start = t;
}

/* Ends the current phase with `reason` at `t_end`. Never decides what happens next -- the two
 * callers below do that explicitly, because a phase cap/complete advances to the next phase (or
 * finishes if there is none), while the session cap and an external stop end the WHOLE walk
 * regardless of how many phases remain, and must never start one more. */
static void end_current(struct gbp_walker *w, enum gbp_walker_end_reason reason, uint64_t t_end)
{
    struct gbp_walker_phase_rec *r = &w->rec[w->index];
    r->ended = 1u;
    r->cut = (uint8_t)(reason != GBP_WALKER_END_COMPLETE);
    r->reason = reason;
    r->t_end = t_end;
}

/* Ends the current phase with `reason`, then either begins the next phase (SAME call, so a phase
 * never sits "ended" for a whole tick with nothing current) or finishes the walk. For a phase cap
 * or a handler's own completion ONLY -- never for the session cap or a stop, which end the whole
 * walk instead (see end_current_and_finish below). */
static int end_current_and_advance(struct gbp_walker *w, enum gbp_walker_end_reason reason, uint64_t t_end)
{
    int flags = GBP_WALKER_TICK_PHASE_END;
    end_current(w, reason, t_end);
    if (w->index + 1u < w->plan->count) {
        begin_phase(w, w->index + 1u, t_end);
        flags |= GBP_WALKER_TICK_PHASE_START;
    } else {
        w->finished = 1u;
        flags |= GBP_WALKER_TICK_FINISHED;
    }
    return flags;
}

/* Ends the current phase with `reason` and finishes the WHOLE walk, regardless of how many phases
 * remain -- the session cap and an external stop both work this way. */
static int end_current_and_finish(struct gbp_walker *w, enum gbp_walker_end_reason reason, uint64_t t_end)
{
    end_current(w, reason, t_end);
    w->finished = 1u;
    return GBP_WALKER_TICK_PHASE_END | GBP_WALKER_TICK_FINISHED;
}

void gbp_walker_start(struct gbp_walker *w, const struct gbp_walker_plan *plan, uint32_t tb_hz, uint64_t t_origin)
{
    if (!w) return;
    memset(w, 0, sizeof *w);
    if (!plan_is_valid(plan) || tb_hz == 0u) { w->cfg_faults++; return; }
    w->plan = plan;
    w->tb_hz = tb_hz;
    w->t_origin = t_origin;
    w->t_session_end = t_origin + (uint64_t)plan->session_cap_s * tb_hz;
    w->started = 1u;
    begin_phase(w, 0u, t_origin);
}

int gbp_walker_tick(struct gbp_walker *w, uint64_t now, int transition_active)
{
    uint64_t t_cap;
    if (!w || !w->started) return 0;
    if (w->finished) return GBP_WALKER_TICK_FINISHED;
    if (transition_active) return 0;                    /* structural: never evaluate a cap while busy */
    /* the running phase's own cap, then the session's: whichever instant came first (mirrors
     * gbp_async's own advance(), so a `now` that jumps past both at once is not misattributed). */
    t_cap = w->rec[w->index].t_start + (uint64_t)w->plan->phases[w->index].cap_s * w->tb_hz;
    if (now >= t_cap && t_cap <= w->t_session_end)
        return end_current_and_advance(w, GBP_WALKER_END_PHASE_CAP, t_cap);
    if (now >= w->t_session_end)
        return end_current_and_finish(w, GBP_WALKER_END_SESSION_CAP, w->t_session_end);
    return 0;
}

int gbp_walker_phase_complete(struct gbp_walker *w, uint64_t now, int transition_active)
{
    if (!w || !w->started || w->finished || transition_active) return 0;
    if (!w->rec[w->index].started || w->rec[w->index].ended) return 0;
    return end_current_and_advance(w, GBP_WALKER_END_COMPLETE, now);
}

int gbp_walker_stop(struct gbp_walker *w, uint64_t now, int transition_active)
{
    if (!w || !w->started || w->finished || transition_active) return 0;
    if (!w->rec[w->index].started || w->rec[w->index].ended) return 0;
    return end_current_and_finish(w, GBP_WALKER_END_STOP, now);   /* ends the WHOLE walk, not just this phase */
}

enum gbp_walker_kind gbp_walker_current_kind(const struct gbp_walker *w)
{
    if (!w || !w->started || w->finished || w->index >= w->plan->count) return GBP_WALKER_NAVIGATE;
    return w->plan->phases[w->index].kind;
}

int gbp_walker_finished(const struct gbp_walker *w)
{
    return w && w->finished;
}

const struct gbp_walker_phase_rec *gbp_walker_phase_record(const struct gbp_walker *w, uint32_t index)
{
    if (!w || !w->plan || index >= w->plan->count) return NULL;
    return &w->rec[index];
}
