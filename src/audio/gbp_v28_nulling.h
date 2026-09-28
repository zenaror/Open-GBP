/*
 * gbp_v28_nulling -- §V28's operator-driven nulling exercise, the native port of gbp_async's own
 * Phase 2 (GitHub Issue #117, §V27.2's "2 nulling: a seeded start on the p2 grid, 128-sample steps
 * under a short mute, a confirm records the setting and jumps to the next seeded start"),
 * GitHub Issue #129/#130 (the Orchestrator's own direction: option (a), the same interface shape
 * gbp_async_step() already has -- a pure step function taking the stick as a plain argument, no
 * idea a pad exists anywhere).
 *
 * WHAT IT IS. A seeded search: GBP_V28_NULLING_CAP settings, each a random start on the p2 grid
 * (GBP_V28_P2_LO..HI by GBP_V28_P2_STEP, gbp_v28_ladder.h) and a random direction (which stick edge
 * counts as "deeper"). gbp_v28_nulling_step() moves the CURRENT setting's target by one grid step,
 * under the SAME step mechanism every other §V28 handler uses (ROTATE, GBP_V28_STEP_MUTE -- #128
 * §3's own fixed mute, not gbp_async's own step_mute_chunks, which it supersedes: gbp_v28_ladder.h's
 * own comment on GBP_V28_STEP_MUTE names nulling explicitly). gbp_v28_nulling_confirm() records the
 * setting the Operator settled on and seeds/starts the next one; after GBP_V28_NULLING_CAP settings
 * the exercise is finished.
 *
 * WHAT IT IS NOT. It knows nothing of a pad, a stick, a controller, or gbp_walker; `stick` is
 * whatever the caller already decided a button edge means (GBP_V28_NULLING_LEFT/RIGHT), refused
 * and counted apart if it is neither -- never silently mapped, mirroring gbp_async_step()'s own
 * documented order (the value check precedes the busy check). It never calls gbp_atrans2_step()
 * (the caller's own pump slot does, exactly as for 3a/3b/sweep). AHEAD is read ONCE at start() from
 * whatever the caller already set it to and held fixed for the whole exercise -- nulling varies
 * TARGET only, the same as gbp_async's own Phase 2, which has no AHEAD concept at all.
 *
 * WHY NO tick()/begin_pending, UNLIKE 3a/3b. 3a and 3b redecide their OWN next target from an
 * INTERNAL timer (a dwell/hold ending), so their own previous transition (still landing, possibly
 * more than one pump call for a climb) can still be `t->active` at the exact instant they try to
 * begin the next one -- hence their tick()-based begin_pending retry. Nulling's only two decision
 * points, step() and confirm(), are each an EXTERNAL, single, synchronous call (a stick edge, an
 * Operator's confirm) with no internal timer of its own driving a redecision; by the time either is
 * called, gbp_atrans2's own busy state is exactly what it is, checked once, refused and counted
 * (never queued) if busy -- the same shape gbp_async_step()/gbp_async_confirm() already have, which
 * is what the Orchestrator asked this module to keep.
 */
#ifndef OPENGBP_GBP_V28_NULLING_H
#define OPENGBP_GBP_V28_NULLING_H

#include <stdint.h>
#include "gbp_atrans2.h"

#ifdef __cplusplus
extern "C" {
#endif

/* GBP_ASYNC_P2_CAP's own value (gbp_async.h), unconverted -- a record-array size, not a sample
 * count (gbp_v28_ladder.h's own enumeration, the "NOT TARGET-domain at all" list). */
#define GBP_V28_NULLING_CAP   16u

enum gbp_v28_nulling_dir   { GBP_V28_NULLING_LEFT_DEEPER = 0, GBP_V28_NULLING_LEFT_SHALLOWER = 1 };
enum gbp_v28_nulling_stick { GBP_V28_NULLING_LEFT = 0, GBP_V28_NULLING_RIGHT = 1 };

struct gbp_v28_nulling_setting {
    uint32_t seq;
    uint32_t start;               /* this setting's own seeded start */
    uint8_t  direction;           /* enum gbp_v28_nulling_dir */
    uint32_t steps, steps_deeper, steps_shallower;
    uint32_t target;              /* the level the Operator confirmed */
    uint64_t t;
};

struct gbp_v28_nulling {
    uint32_t rng;
    uint32_t ahead;                              /* fixed for the whole exercise, read at start() */
    uint32_t p2_index, p2_seeded;
    uint32_t p2_start[GBP_V28_NULLING_CAP];
    uint8_t  p2_dir[GBP_V28_NULLING_CAP];        /* enum gbp_v28_nulling_dir */
    uint32_t target;                             /* the CURRENT setting's own target */
    uint32_t steps, steps_deeper, steps_shallower;
    struct gbp_v28_nulling_setting settings[GBP_V28_NULLING_CAP];
    uint32_t settings_n;
    uint8_t  finished;                           /* GBP_V28_NULLING_CAP settings recorded */
    uint32_t refused_step_value;   /* stick was neither LEFT nor RIGHT: never mapped */
    uint32_t refused_step_busy;    /* a transition (this setting's own previous step) is still active */
    uint32_t refused_step_end;     /* the grid's own p2_lo/p2_hi edge in that direction */
    uint32_t refused_confirm_busy;
    uint32_t refused_confirm_over; /* confirm() called after the exercise already finished */
};

/* Seeds setting 0 and attempts its own START (ROTATE, GBP_V28_STEP_MUTE, to p2_start[0], at
 * whatever AHEAD `p` already carries). `seed_in` is the xorshift32 state to draw from
 * (caller-chosen, e.g. a session seed); 0 is substituted with 1, exactly as gbp_async_start() does
 * (0 is xorshift32's own fixed point). Returns 1 applied, 0 refused (gbp_atrans2_begin() was busy --
 * cannot happen at a true start under gbp_walker's own phase-gating, but never assumed: the caller
 * retries exactly as it would for a refused gbp_v28_3a_tick()/gbp_v28_3b_tick() begin). */
int gbp_v28_nulling_start(struct gbp_v28_nulling *n, struct gbp_atrans2 *t, struct gbp_aplay2 *p,
                          struct gbp_adec2 *d, uint64_t now, uint32_t seed_in);

/* One grid step, `stick` at a time. Refusal order mirrors gbp_async_step() exactly: an invalid
 * stick value first (refused_step_value, never mapped), then busy (refused_step_busy), then the
 * grid's own edge (refused_step_end). Returns 1 applied, 0 refused. */
int gbp_v28_nulling_step(struct gbp_v28_nulling *n, struct gbp_atrans2 *t, struct gbp_aplay2 *p,
                         struct gbp_adec2 *d, uint64_t now, uint8_t stick);

/* Records the current setting and, unless this was the last of GBP_V28_NULLING_CAP (n->finished
 * set instead), seeds/starts the next one. Returns 1 applied (recorded, whether or not a next
 * setting followed), 0 refused (busy, or already finished). */
int gbp_v28_nulling_confirm(struct gbp_v28_nulling *n, struct gbp_atrans2 *t, struct gbp_aplay2 *p,
                            struct gbp_adec2 *d, uint64_t now);

int gbp_v28_nulling_finished(const struct gbp_v28_nulling *n);

/* NULL if `index` is out of range (>= settings_n). */
const struct gbp_v28_nulling_setting *gbp_v28_nulling_record(const struct gbp_v28_nulling *n, uint32_t index);

#ifdef __cplusplus
}
#endif
#endif
