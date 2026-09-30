/*
 * gbp_walker -- a pure sequencing engine over an ORDERED LIST OF PHASE KINDS (GitHub Issue #129,
 * restructuring gbp_async's single P0->P1->P2->P3 session into #128's two-run design:
 * validation_run (navigate -> 3a descent -> 3b hold -> sweep) and perceptual_no_phase1
 * (navigate -> nulling), Phase 1 dropped from both).
 *
 * WHAT IT IS. A pure state machine, same discipline as gbp_async.h: no device, no audio, no pad.
 * It owns only the plan's own timing and cut/complete accounting. It knows nothing about what a
 * phase KIND actually does (3a's bisection, 3b's hold, sweep's steps, nulling's scan) -- that
 * domain logic lives in a handler above this module, which reads gbp_walker_current_kind() and
 * calls gbp_walker_phase_complete() when its own logic decides the phase is naturally done. This
 * module never dispatches to a handler itself; it only sequences.
 *
 * WHY IT REPLACES gbp_async'S OWN SEQUENCE, NOT JUST ITS NAME. #128's two runs are not a rename of
 * P0..P3: Phase 1 is dropped from BOTH; "3a"/"3b"/"sweep" are new phase kinds with no P0..P3
 * equivalent; the two runs share no single ordered sequence. An ordered LIST that a plan supplies
 * is what lets validation_run and perceptual_no_phase1 be two different lists over the same
 * walker, instead of two copies of a hand-written phase switch.
 *
 * THE BINDING ORDERING CONSTRAINT (the one this module exists to hold, not a caller's discipline):
 * every advance -- a phase starting, ending, or completing -- is refused while the caller's own
 * `transition_active` flag is true, structurally, inside gbp_walker_tick()/_phase_complete()/_stop()
 * themselves. This is Issue #117's entry 21, "a plan was applied over a running one": the original
 * fix was the CALLER remembering to gate a call to gbp_async_tick() (main.c's
 * `r = trans.active ? 0 : gbp_async_tick(&sync, now)`), which is exactly the kind of caller
 * discipline this module removes the need for -- gbp_walker itself refuses to advance, so no
 * caller can forget the gate. tests/unit/test_gbp_atrans.c's test_the_module_waits_for_the_executor
 * found this deterministic in 63 of 64 phases without the gate; this module's own tests reproduce
 * that shape against gbp_walker directly.
 *
 * A CUT PHASE IS NEVER COUNTED COMPLETE (Issue #117's "cut dwell" defects, entries 8/11/20/24/25):
 * `gbp_walker_phase_rec.reason` distinguishes GBP_WALKER_END_COMPLETE (the handler's own decision)
 * from every cut reason (a phase cap, the session cap, an external stop) -- a report builder reads
 * `reason`, never infers completeness from `ended` alone.
 *
 * EVERY PHASE HAS ITS OWN EXPLICIT CAP, INCLUDING NAVIGATE/P0 (§V27.9's O4: the old design's
 * cap_p1_s/cap_p2_s/cap_p3_s/cap_session_s left Phase 0 with no cap of its own, so it could
 * silently eat the budget later phases assumed was theirs). Here every `gbp_walker_phase_def` in
 * the plan carries its own `cap_s`, navigate included -- no special case, closed by construction.
 *
 * EDGES, for the SD log's SYNCPE tag (Issue #128 §7: "an edge detector ... emitted once per pump
 * call, OUTSIDE the module block"): gbp_walker_tick() returns GBP_WALKER_TICK_PHASE_START and/or
 * GBP_WALKER_TICK_PHASE_END bits the SAME tick a phase starts or ends, so the caller's own edge
 * detector needs nothing beyond reading these bits and gbp_walker_phase_record() -- it does not
 * need to poll `started`/`ended` itself.
 */
#ifndef OPENGBP_GBP_WALKER_H
#define OPENGBP_GBP_WALKER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_WALKER_MAX_PHASES   8u

enum gbp_walker_kind {
    GBP_WALKER_NAVIGATE = 0,     /* p0: origin -> the phase's own handler decides it is done */
    GBP_WALKER_DESCENT_3A,
    GBP_WALKER_HOLD_3B,
    GBP_WALKER_SWEEP,
    GBP_WALKER_NULLING,
    GBP_WALKER_LOSS,             /* Issue #137's diagnostic: steady holds, measured against two manipulated factors */
    GBP_WALKER_PLAY              /* Issue #153's play phase: free-running, NO handler -- only the Operator's Z or the cap ends it */
};

enum gbp_walker_end_reason {
    GBP_WALKER_END_NONE = 0,
    GBP_WALKER_END_COMPLETE,     /* the phase's own handler decided it was done -- the ONLY reason that is not a cut */
    GBP_WALKER_END_PHASE_CAP,    /* cut: this phase's own cap_s elapsed */
    GBP_WALKER_END_SESSION_CAP,  /* cut: the whole session's cap elapsed */
    GBP_WALKER_END_STOP          /* cut: an external stop (Z) */
};

struct gbp_walker_phase_def {
    enum gbp_walker_kind kind;
    uint32_t cap_s;               /* this phase's OWN explicit budget -- every phase gets one */
};

struct gbp_walker_plan {
    const struct gbp_walker_phase_def *phases;
    uint32_t count;                /* 1 .. GBP_WALKER_MAX_PHASES */
    uint32_t session_cap_s;
};

struct gbp_walker_phase_rec {
    uint8_t started;
    uint8_t ended;
    uint8_t cut;                   /* (reason != GBP_WALKER_END_COMPLETE); redundant with reason, kept for a cheap read */
    enum gbp_walker_end_reason reason;
    uint64_t t_start;
    uint64_t t_end;
};

struct gbp_walker {
    const struct gbp_walker_plan *plan;
    uint32_t tb_hz;
    uint64_t t_origin;
    uint64_t t_session_end;
    uint32_t index;                 /* the current phase's index into plan->phases */
    int started;
    int finished;
    struct gbp_walker_phase_rec rec[GBP_WALKER_MAX_PHASES];
    uint32_t cfg_faults;            /* an invalid plan (NULL, empty, oversized, a zero cap): counted, never guessed at */
};

/* GBP_WALKER_TICK_* bits, returned by gbp_walker_tick()/_phase_complete()/_stop() -- mirrors
 * gbp_async's own bitmask tick contract (GBP_ASYNC_TICK_*). */
#define GBP_WALKER_TICK_PHASE_START   1
#define GBP_WALKER_TICK_PHASE_END     2
#define GBP_WALKER_TICK_FINISHED      4

/* Rejects a NULL/empty/oversized plan, or one with a zero cap_s anywhere (including
 * session_cap_s), by counting cfg_faults and never starting -- gbp_walker_tick() then always
 * returns 0. Otherwise begins the first phase at t_origin. */
void gbp_walker_start(struct gbp_walker *w, const struct gbp_walker_plan *plan, uint32_t tb_hz, uint64_t t_origin);

/* Advances timing/cap bookkeeping and starts the next phase when due. NEVER evaluates or advances
 * anything while `transition_active` is true (see the header comment above) -- returns 0
 * immediately in that case, even if a cap has already elapsed; the cap is evaluated again next
 * tick, against the same elapsed time, so nothing is lost, only deferred. Returns
 * GBP_WALKER_TICK_* bits, or 0 if nothing happened this tick. */
int gbp_walker_tick(struct gbp_walker *w, uint64_t now, int transition_active);

/* The CURRENT phase's own handler calls this when ITS OWN domain logic (3a's bisection converged,
 * sweep exhausted its steps, nulling recorded its settings, ...) decides the phase is naturally
 * done -- distinct from a cap cutting it, and the only path that ever records
 * GBP_WALKER_END_COMPLETE. Busy-gated like every other advance: returns 0 (not applied; call again
 * once idle) while transition_active, or if there is no started, unended current phase. Returns
 * GBP_WALKER_TICK_* bits on success. */
int gbp_walker_phase_complete(struct gbp_walker *w, uint64_t now, int transition_active);

/* An external stop (Z): cuts the current phase (GBP_WALKER_END_STOP, never COMPLETE) and ends the
 * WHOLE walk, not just this phase -- the session cap's own semantics, requested early. Busy-gated
 * like every other advance. Returns GBP_WALKER_TICK_* bits on success, 0 if refused or already
 * finished. */
int gbp_walker_stop(struct gbp_walker *w, uint64_t now, int transition_active);

/* Only meaningful while !gbp_walker_finished(). */
enum gbp_walker_kind gbp_walker_current_kind(const struct gbp_walker *w);

int gbp_walker_finished(const struct gbp_walker *w);

/* NULL if `index` is out of the plan's own range. */
const struct gbp_walker_phase_rec *gbp_walker_phase_record(const struct gbp_walker *w, uint32_t index);

#ifdef __cplusplus
}
#endif
#endif
