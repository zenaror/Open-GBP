/*
 * gbp_v28_sweep -- §V28's step sweep (GitHub Issue #128 §3/#129/#130), the validation run's own
 * FOURTH phase (navigate -> 3a -> 3b -> sweep), driven by gbp_walker like 3a/3b.
 *
 * THE SEQUENCE IS FROZEN, NOT THIS MODULE'S TO DESIGN (Issue #129, "The sweep's sequence:
 * Orchestrator's decision", and its own follow-up correcting the sequence's own closure gap):
 * 27 transitions, in this exact deterministic order --
 *
 *   GATE (18, carries a verdict, runs FIRST on a clean chain):
 *     1-7   descend  T704A4 -> T576A4 -> T448A4 -> T320A4 -> T256A4 -> T256A3 -> T256A2 -> T256A1
 *                     (7 adjacent down-steps)
 *     8     one refused step at the bottom   (same-level ROTATE, T256A1 -> T256A1)
 *     9-15  ascend   T256A1 -> ... -> T704A4                       (7 adjacent up-steps)
 *     16    one refused step at the top      (same-level ROTATE, T704A4 -> T704A4)
 *     17-18 the largest START both ways:  T704A4 -> T256A1  and  T256A1 -> T704A4
 *
 *   INFORMATIONAL (9, never gates, runs LAST -- T192 carries the D2-class splice risk found in
 *   Item 4, so it never contaminates the gating measurement; the repositioning move that opens it
 *   is the SAME class of large jump the two STARTs above already cover, verified again here rather
 *   than assumed):
 *     19    repositioning: T704A4 -> T256A4    (the walk along the main 8 rungs' own line always
 *                                                returns to its own start -- Issue #129's own second
 *                                                comment: descending 7 down-steps then climbing the
 *                                                same 7 up nets to zero, and the two STARTs, one each
 *                                                way, also net to zero; ONE interior move is what
 *                                                actually gets the chain from T704A4 to T256A4)
 *     20-27 T256A4 -> T192A4, then T192 A4->A3->A2->A1, then A1->A2->A3->A4, then T192A4 -> T256A4
 *
 * MECHANISM, per entry: STEP (GBP_V28_STEP_MUTE, an ordinary rung), REFUSED (the same STEP mute, a
 * same-level ROTATE -- test_v28_ahead_steps.c's own "refused" idiom, the grid-end case §7: not a
 * gbp_atrans2_begin() refusal, a plan with nothing to move away from), START (GBP_V28_START_MUTE,
 * the ladder's own largest climb, both the two gating STARTs and the repositioning move -- #7's own
 * build-time need, verified again at the repositioning, not assumed from the gating STARTs' own
 * pass).
 *
 * VERDICTS, KEPT APART (Issue #129, both comments): a GATE entry PASSes when it lands with no
 * OUT_OF_BAND fault (gbp_atrans2's own ROTATE landing trim makes this a STRUCTURAL check now, not a
 * fitted one -- see tests/unit/test_v28_sweep_residue.c), no UNDERRUN observed during its own mute
 * or dwell, and is masked by content (`tr.unmasked` clear -- #117's rule). ANY gate failure is
 * reported by fail_reason, never silently folded into a generic FAIL. An INFORMATIONAL entry is
 * recorded in full, with the SAME fields, but never contributes to gbp_v28_sweep_verdict() -- only
 * the 18 GATE rows do. A dwell CUT before its own end is recorded PARTIAL, never PASS (Issue #117's
 * cut-dwell defects; the same discipline gbp_v28_3a/3b already apply) -- and PARTIAL fails the
 * verdict exactly like FAIL: an unobserved GATE entry is never certified safe by omission.
 *
 * BUDGET (Issue #129's own second comment, recomputed there): 27 moves, not 26; the STARTs and the
 * repositioning use GBP_V28_START_MUTE (8), not GBP_V28_STEP_MUTE (6); with the ROTATE trim, the
 * ring lands at target immediately, so the settle dwell is a SHORT OBSERVATION window
 * (GBP_V28_SWEEP_DWELL_S), not a wait for the ring to drift back -- see the sum check below.
 *
 * Shares gbp_v28_3a/3b's own construction discipline exactly: a decided plan is held PENDING and
 * retried every tick through gbp_atrans2_begin()'s own busy-gate; nothing is assumed to have taken
 * effect until begin() actually reports 1; a plan decided but never begun (cut first) is abandoned,
 * nothing to report -- the SAME reasoning gbp_v28_3a.c/gbp_v28_3b.c already state for their own
 * pending changes. gbp_walker's own busy-gate (transition_active) means a phase cut can never land
 * mid-mute -- the only cuttable states here are "decided, not yet begun" (abandoned) and "landed,
 * dwelling" (recorded PARTIAL).
 *
 * What this module does NOT do: it never calls gbp_atrans2_step() itself (the caller's own pump
 * slot does, exactly as for 3a/3b); it knows nothing of gbp_walker, phases or the session; it never
 * reads a device or a clock beyond the `now` it is handed; it never decides what happens to a GATE
 * failure (removing a rung from the perceptual ladder, blocking the perceptual run) -- it only
 * produces the verdict and the 27 records #129 asks the validation run for.
 */
#ifndef OPENGBP_GBP_V28_SWEEP_H
#define OPENGBP_GBP_V28_SWEEP_H

#include <stdint.h>
#include "gbp_atrans2.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_V28_SWEEP_N          27u
#define GBP_V28_SWEEP_DWELL_S     1u   /* a short post-landing observation, not a settle wait -- the
                                        * ROTATE trim already lands the ring at target (see
                                        * gbp_atrans2.c's own step_rotate2()) */

enum gbp_v28_sweep_class { GBP_V28_SWEEP_GATE = 0, GBP_V28_SWEEP_INFO = 1 };
enum gbp_v28_sweep_mechanism { GBP_V28_SWEEP_STEP = 0, GBP_V28_SWEEP_REFUSED = 1, GBP_V28_SWEEP_START = 2 };
enum gbp_v28_sweep_outcome { GBP_V28_SWEEP_PENDING = 0, GBP_V28_SWEEP_PASS = 1, GBP_V28_SWEEP_FAIL = 2,
                            GBP_V28_SWEEP_PARTIAL = 3 };
enum gbp_v28_sweep_fail_reason { GBP_V28_SWEEP_FAIL_NONE = 0, GBP_V28_SWEEP_FAIL_OUT_OF_BAND = 1,
                                 GBP_V28_SWEEP_FAIL_UNDERRUN = 2, GBP_V28_SWEEP_FAIL_UNMASKED = 3 };
enum gbp_v28_sweep_verdict { GBP_V28_SWEEP_VERDICT_PENDING = 0, GBP_V28_SWEEP_VERDICT_PASS = 1,
                            GBP_V28_SWEEP_VERDICT_FAIL = 2 };

struct gbp_v28_sweep_record {
    uint8_t  klass;                             /* enum gbp_v28_sweep_class */
    uint8_t  mechanism;                         /* enum gbp_v28_sweep_mechanism */
    uint32_t from_target, from_ahead, to_target, to_ahead;
    uint8_t  outcome;                           /* enum gbp_v28_sweep_outcome */
    uint8_t  fail_reason;                       /* enum gbp_v28_sweep_fail_reason, meaningful iff FAIL */
    uint64_t t_begin, t_land, t_done;           /* plan applied, transition landed, dwell ended (or cut) */
    int32_t  residue;                           /* gbp_atrans2's own tr.residue at the landing (informational) */
    uint32_t dup, drop;                         /* THIS entry's own deltas (gbp_aplay2's cumulative counters) */
    uint32_t ahead_drops;                       /* gbp_atrans2's own tr.ahead_drops for this entry */
    uint8_t  unmasked;                          /* gbp_atrans2's own tr.unmasked for this entry */
};

struct gbp_v28_sweep {
    uint32_t tb_hz;
    uint32_t index;                              /* the entry now pending/active/dwelling */
    uint8_t  begin_pending;                      /* this entry's plan decided, not yet applied */
    uint8_t  dwelling;                           /* landed; observing until t_dwell_end or a cut */
    uint8_t  finished;
    uint64_t t_begin;                            /* when THIS entry's plan actually began */
    uint64_t t_land;                             /* when THIS entry's transition landed */
    uint64_t t_dwell_end;
    uint32_t dup0, drop0;                        /* gbp_aplay2's own dup/drop, snapshotted at begin */
    uint32_t underruns0;                         /* gbp_aplay2's own underruns, snapshotted at begin */
    uint32_t ring_at_land, ready_at_land;         /* d->count/gbp_aplay2_ready(), snapshotted at the landing */
    int32_t  residue_at_land;                    /* gbp_atrans2's own tr.residue, snapshotted at the landing */
    uint32_t ahead_drops_at_land;                /* gbp_atrans2's own tr.ahead_drops, snapshotted at the landing */
    uint8_t  unmasked_at_land;                   /* gbp_atrans2's own tr.unmasked, snapshotted at the landing */
    struct gbp_v28_sweep_record records[GBP_V28_SWEEP_N];
    uint32_t records_n;
};

/* Begins the sequence's first entry (index 0). `tb_hz` is the same hardware timebase
 * gbp_walker/gbp_v28_3a/3b use. */
void gbp_v28_sweep_start(struct gbp_v28_sweep *s, uint32_t tb_hz, uint64_t now);

/* GBP_V28_SWEEP_TICK_* bits, returned by gbp_v28_sweep_tick() -- mirrors gbp_v28_3a/3b's own
 * contract. */
#define GBP_V28_SWEEP_TICK_PHASE_COMPLETE   1   /* the whole sequence is over: call gbp_walker_phase_complete() */

/* Call every pump slot while sweep is the walker's current phase, AFTER the caller's own pump slot
 * for this same `now` has already run (its `gbp_atrans2_step()`/`gbp_aplay2_produce()` call) --
 * NOT before, unlike gbp_v28_3a/3b's own convention. 3a/3b only ever read wall-clock time, so
 * calling them before or after the pump slot makes no difference; this module reads the RING and
 * READY level at the exact landing instant (the TARGET/AHEAD check), and gbp_atrans2's own landing
 * (`t->active` flipping to 0, inside `gbp_atrans2_step()`) happens INSIDE that same pump slot --
 * calling this module before it would observe a stale `t->active` and, once it does notice landing
 * next tick, a ring/READY level already drifted by one extra period's worth of ordinary production
 * (found and fixed empirically while building this module's own test: the mismeasurement was
 * exactly one slice's worth, `GBP_APLAY2_PUSHES / 16`, matching the lag precisely).
 *
 * Retries a deferred begin(); lands, observes, records, and advances to the next entry; `p`/`d` are
 * read for dup/drop/underrun/ring/READY snapshots but never mutated except through
 * `t`/gbp_atrans2_begin(). Returns GBP_V28_SWEEP_TICK_* bits, or 0. */
int gbp_v28_sweep_tick(struct gbp_v28_sweep *s, struct gbp_atrans2 *t, struct gbp_aplay2 *p, struct gbp_adec2 *d,
                       uint64_t now);

/* The phase is being cut (a cap, the session cap, or a stop) -- call BEFORE the caller advances
 * past sweep. A plan decided but not yet begun is abandoned (nothing to report, gbp_v28_3a/3b's own
 * reasoning); a landed entry still dwelling is recorded PARTIAL, never PASS. */
void gbp_v28_sweep_cut(struct gbp_v28_sweep *s, uint64_t t_end);

int gbp_v28_sweep_finished(const struct gbp_v28_sweep *s);

/* NULL if `index` is out of range (>= records_n). */
const struct gbp_v28_sweep_record *gbp_v28_sweep_record_at(const struct gbp_v28_sweep *s, uint32_t index);

/* PENDING while fewer than the 18 GATE entries have been recorded yet; otherwise PASS iff every
 * GATE record's own outcome is PASS (a FAIL or a PARTIAL -- an unobserved GATE entry is never
 * certified safe by omission -- both fail it); INFO records never fold in. */
enum gbp_v28_sweep_verdict gbp_v28_sweep_verdict(const struct gbp_v28_sweep *s);

#ifdef __cplusplus
}
#endif
#endif
