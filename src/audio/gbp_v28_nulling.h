/*
 * gbp_v28_nulling -- §V28's operator-driven nulling exercise on the PERCEPTUAL LADDER (GitHub Issue #128 section 3 / #129 / #130; rebuilt on the ladder in Issue #139 / #141).
 *
 * WHAT IT IS. The Operator moves the audio latency one rung at a time until audio and picture look synchronised, and confirms. The rungs are the eight the validation run held and
 * stepped between (gbp_v28_ladder.h GBP_V28_RUNG: T704A4 ... T256A4, T256A3, T256A2, T256A1, deepest first). Each setting starts at a SEEDED rung (uniform over the eight) with a
 * seeded direction (which stick edge counts as "deeper"): a START, GBP_V28_START_MUTE, the mute built from the ladder's largest climb. A LEFT / RIGHT press is one rung, the step
 * mechanism (ROTATE, GBP_V28_STEP_MUTE). A press against an END of the ladder is a same-level ROTATE plan with the SAME mute (#128 section 7: "a refused step at a grid end becomes a
 * same-level ROTATE plan, so the scale's end is not audible") and is counted apart, per end. gbp_v28_nulling_confirm() records the rung the Operator settled on and starts the next
 * setting; after GBP_V28_NULLING_CAP settings the exercise is finished.
 *
 * WHY THE LADDER AND NOT A TARGET GRID (the defect this replaces). The first version was a port of gbp_async's Phase 2: TARGET only, on a 6144..57344 grid, at whatever AHEAD was
 * in force (1), every start under the STEP mute. Its floor (T384 at AHEAD 1, about 153 ms) sat one grid step ABOVE the validated floor rung (T256 A1, 121 ms), so a null in between
 * would have read "censored at the floor" 31 ms too high; and a seeded start could climb 51 000 samples under a 7-period mute that a 7 168-sample climb already needs 10 for, landing
 * short, so the level a setting logged would not have been the level the ring had. The ladder's own rungs are the ones the sweep validated (GATE rows 1-18, 18 of 18 in RUN 55 and 56).
 *
 * WHAT IT IS NOT. It knows nothing of a pad, a stick, a controller, or gbp_walker; `stick` is whatever the caller already decided a button edge means (GBP_V28_NULLING_LEFT/RIGHT),
 * refused and counted apart if it is neither -- never silently mapped, mirroring gbp_async_step()'s own documented order (the value check precedes the busy check). It never calls
 * gbp_atrans2_step() (the caller's own pump slot does, exactly as for 3a/3b/sweep).
 *
 * WHY NO tick()/begin_pending, UNLIKE 3a/3b. 3a and 3b redecide their OWN next target from an INTERNAL timer, so their previous transition can still be `t->active` at the instant
 * they try to begin the next one -- hence their tick()-based begin_pending retry. Nulling's only decision points, step() and confirm(), are each an EXTERNAL, single, synchronous
 * call (a stick edge, an Operator's confirm); busy is checked once, refused and counted (never queued).
 *
 * WHAT IS RECORDED (SD log only, never shown: the leak rules): per setting the START rung, the direction, the steps in each direction, the presses refused at each end
 * (`refused_floor`: against the shallowest rung; `refused_top`: against the deepest), the rung confirmed and its (T, A). "CENSORED" (#128 section 4) is read from these by the
 * post-run tool: a setting confirmed at the floor rung after at least one refused press against the floor.
 */
#ifndef OPENGBP_GBP_V28_NULLING_H
#define OPENGBP_GBP_V28_NULLING_H

#include <stdint.h>
#include "gbp_atrans2.h"
#include "gbp_v28_ladder.h"

#ifdef __cplusplus
extern "C" {
#endif

/* GBP_ASYNC_P2_CAP's own value (gbp_async.h), unconverted -- a record-array size, not a sample count. */
#define GBP_V28_NULLING_CAP   16u

enum gbp_v28_nulling_dir   { GBP_V28_NULLING_LEFT_DEEPER = 0, GBP_V28_NULLING_LEFT_SHALLOWER = 1 };
enum gbp_v28_nulling_stick { GBP_V28_NULLING_LEFT = 0, GBP_V28_NULLING_RIGHT = 1 };

struct gbp_v28_nulling_setting {
    uint32_t seq;
    uint32_t start;               /* this setting's own seeded START rung (an index into GBP_V28_RUNG) */
    uint8_t  direction;           /* enum gbp_v28_nulling_dir */
    uint32_t steps, steps_deeper, steps_shallower;
    uint32_t refused_floor, refused_top;    /* presses against the shallowest / the deepest rung in this setting */
    uint32_t rung;                /* the rung the Operator confirmed */
    uint32_t target, ahead;       /* its (T, A) */
    uint32_t ring, ready;         /* the decoder ring's level and the READY chunks at the confirm (the mechanistic gate: the fill tracks the target) */
    uint32_t underruns, overflow; /* the AI underruns and the ring's dropped samples DURING this setting (from its START's begin to its confirm) */
    uint64_t t;
};

struct gbp_v28_nulling {
    uint32_t rng;
    uint32_t p2_index, p2_seeded;
    uint32_t p2_start[GBP_V28_NULLING_CAP];      /* the seeded START rung of each setting */
    uint8_t  p2_dir[GBP_V28_NULLING_CAP];        /* enum gbp_v28_nulling_dir */
    uint32_t rung;                               /* the CURRENT setting's own rung */
    uint32_t steps, steps_deeper, steps_shallower;
    uint32_t cur_refused_floor, cur_refused_top;
    uint32_t u0, o0;                             /* the AI underruns / ring overflow counters at the current setting's begin */
    struct gbp_v28_nulling_setting settings[GBP_V28_NULLING_CAP];
    uint32_t settings_n;
    uint8_t  finished;                           /* GBP_V28_NULLING_CAP settings recorded */
    uint32_t refused_step_value;   /* stick was neither LEFT nor RIGHT: never mapped */
    uint32_t refused_step_busy;    /* a transition (this setting's own previous step) is still active */
    uint32_t refused_step_end;     /* presses against an end of the ladder (each ran as a same-level ROTATE), both ends */
    uint32_t refused_confirm_busy;
    uint32_t refused_confirm_over; /* confirm() called after the exercise already finished */
};

/* Seeds setting 0 and begins its START (ROTATE, GBP_V28_START_MUTE, to the seeded rung's (T, A)). `seed_in` is the xorshift32 state to draw from (caller-chosen, e.g. a session
 * seed); 0 is substituted with 1, exactly as gbp_async_start() does (0 is xorshift32's own fixed point). Returns 1 applied, 0 refused (gbp_atrans2_begin() was busy -- cannot happen at
 * a true start under gbp_walker's own phase-gating, but never assumed: the caller retries). */
int gbp_v28_nulling_start(struct gbp_v28_nulling *n, struct gbp_atrans2 *t, struct gbp_aplay2 *p,
                          struct gbp_adec2 *d, uint64_t now, uint32_t seed_in);

/* One rung, `stick` at a time. Refusal order mirrors gbp_async_step() exactly: an invalid stick value first (refused_step_value, never mapped), then busy (refused_step_busy).
 * A press against an END of the ladder is NOT refused: it begins a same-level ROTATE (the same mute and mechanism as any step, so the end is not audible), counted in
 * refused_step_end and the current setting's refused_floor / refused_top. Returns 1 when a transition began (a step or an end press), 0 when refused (value or busy). */
int gbp_v28_nulling_step(struct gbp_v28_nulling *n, struct gbp_atrans2 *t, struct gbp_aplay2 *p,
                         struct gbp_adec2 *d, uint64_t now, uint8_t stick);

/* Records the current setting and, unless this was the last of GBP_V28_NULLING_CAP (n->finished set instead), seeds and begins (a START) the next one. Returns 1 applied
 * (recorded, whether or not a next setting followed), 0 refused (busy, or already finished). */
int gbp_v28_nulling_confirm(struct gbp_v28_nulling *n, struct gbp_atrans2 *t, struct gbp_aplay2 *p,
                            struct gbp_adec2 *d, uint64_t now);

int gbp_v28_nulling_finished(const struct gbp_v28_nulling *n);

/* NULL if `index` is out of range (>= settings_n). */
const struct gbp_v28_nulling_setting *gbp_v28_nulling_record(const struct gbp_v28_nulling *n, uint32_t index);

#ifdef __cplusplus
}
#endif
#endif
