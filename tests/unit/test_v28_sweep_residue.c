/*
 * tests/unit/test_v28_sweep_residue.c — GitHub Issue #129/#130: two STRUCTURAL invariants at every
 * landing of EXACTLY the transitions the step sweep walks, at GBP_V28_STEP_MUTE (6), on the REAL
 * native chain, under the SAME bursty feed and phase sweep tests/unit/test_gbp_atrans.c's own
 * test_rotate_under_a_bursty_feed() uses (the old path's own review round 3 finding: "the smooth,
 * phase-locked feed can never make a rotation late").
 *
 * NARROWER THAN THE FULL test_v28_ahead_steps.c MATRIX, DELIBERATELY (Orchestrator review, Issue
 * #130): this measures only what the sweep's own OUT_OF_BAND check needs -- the realistic worst
 * case for a NORMAL landing on the sweep's own 16 transitions (the 7 adjacent ladder steps each
 * way, plus the 2 largest STARTs), under a bursty feed and every phase. Mutes 5-vs-6, D2-class
 * losses and the masking bound stay the full matrix's own scope, a named pre-staging item, not
 * measured here.
 *
 * STRUCTURAL, NOT FITTED (the Orchestrator's own correction, Issue #129/#130, after gbp_atrans2's
 * ROTATE landing trim -- see gbp_atrans2.c's step_rotate2()): a fitted ceiling on the raw `residue`
 * would just enshrine whatever the mechanism happened to produce. With the trim in place, both
 * halves of a landing are EXACT claims instead:
 *   TARGET  -- the ring after the trim never sits above target (any excess there is the trim
 *              failing to fire, a genuine fault); it may sit up to GBP_APLAY2_BAND below target
 *              (a natural undershoot the trim never manufactures a fix for, since it only ever
 *              cuts downward) -- not observed in this sweep, but not asserted away either.
 *   AHEAD   -- READY at landing is exactly `to_ahead - 1` (the ordinary case) or `to_ahead` (a
 *              landing mid produce+rotate cycle, the same LATE class test_gbp_atrans.c's own
 *              check_rotate() already tolerates for the old path).
 * The residue itself is still measured and printed (informational): with the trim, its only
 * remaining content is the benign READY-side term, a structural one-chunk-period figure, not a
 * tuned one.
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "gbp_atrans2.h"
#include "gbp_v28_ladder.h"

static int checks, failures;

static void check(int cond, const char *what)
{
    checks++;
    if (!cond) {
        failures++;
        printf("  FAIL: %s\n", what);
    }
}

static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t ring[GBP_APLAY2_RING];
static int16_t keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events[GBP_APLAY2_EVENTS_CAP];
static struct gbp_aplay2 ap;
static struct gbp_adec2 adec;
static struct gbp_atrans2 tr;

#define CALLS_PER_PERIOD 125u   /* the console's own: 124.8 pump calls per hand-off period (RUN 52 log, Issue #136); not 16 */

static int burst_at = -1;      /* -1: smooth (even slices); >= 0: one burst of a whole period's pushes here */

static uint32_t slice2(uint32_t k)
{
    return (k + 1u) * GBP_APLAY2_PUSHES / CALLS_PER_PERIOD - k * GBP_APLAY2_PUSHES / CALLS_PER_PERIOD;
}

static uint32_t feed_at(uint32_t k)
{
    if (burst_at < 0) return slice2(k);
    return (int)k == burst_at ? GBP_APLAY2_PUSHES : 0u;
}

static void give2(struct gbp_adec2 *d, uint32_t n, int16_t v)
{
    uint32_t k;
    for (k = 0; k < n && d->count < d->cap; k++) {
        d->ring[(d->head + d->count) % d->cap] = v;
        d->count++;
    }
}

static void pump2(uint64_t now)
{
    int b;
    (void)now;
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

/* the chain steady at (from, ahead): the ring at the level, READY whole at `ahead` */
static uint64_t steady2(uint32_t from, uint32_t ahead)
{
    uint64_t now = 0;
    uint32_t i, k;
    memset(&ap, 0, sizeof ap);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    gbp_atrans2_init(&tr);
    ap.ahead = ahead;
    gbp_aplay2_set_target(&ap, from);
    give2(&adec, from, 100);
    for (i = 0; i < ahead; i++) prime_period2(&now);
    ap.playing = 1u;
    for (i = 0; i < 6u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(now); now++; }
    }
    return now;
}

struct landing {
    int32_t residue;   /* informational: after the trim, the benign READY-side term alone */
    uint32_t ring;      /* d->count at the landing, AFTER gbp_atrans2's own trim */
    uint32_t ready;     /* gbp_aplay2_ready(&ap) at the landing */
};

/* begins the plan at pump call `phase` of a period, drives it to landing (bounded). Returns 1 and
 * fills `out` at the landing, or 0 if it never lands within the bound (a fault, never silently
 * ignored by the caller). `mute` is the plan's own mute -- GBP_V28_STEP_MUTE for an ordinary rung,
 * GBP_V28_START_MUTE for the ladder's own largest climb (its own frozen need, #128 §7). */
static int land(uint32_t from_target, uint32_t from_ahead, uint32_t to_target, uint32_t to_ahead, uint32_t mute,
                uint32_t phase, uint32_t max_periods, struct landing *out)
{
    uint64_t now = steady2(from_target, from_ahead);
    uint32_t i, k;
    int begun = 0;
    for (i = 0; i <= max_periods; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) {
            give2(&adec, feed_at(k), 100);
            if (i == 0u && k == phase) {
                (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mute, 0u, 0u, to_target, to_ahead);
                begun = 1;
            }
            pump2(now);
            if (begun && !tr.active) {
                out->residue = tr.residue;
                out->ring = adec.count;
                out->ready = gbp_aplay2_ready(&ap);
                return 1;
            }
            now++;
        }
    }
    return 0;
}

struct transition {
    const char *name;
    uint32_t from_target, from_ahead, to_target, to_ahead, mute;
};

/* exactly the sweep's own 16 transitions (#129's own frozen sequence): the 7 adjacent ladder
 * steps each way, and the 2 largest STARTs both ways. Refused (same-level) steps are not here --
 * a same-level ROTATE has no new target to land away from, so it carries no OUT_OF_BAND risk of
 * its own kind. The two STARTs use GBP_V28_START_MUTE, not GBP_V28_STEP_MUTE -- the perceptual
 * run's own STARTs never use the ordinary rung's fixed mute either (#128 §7). */
static const struct transition TRANSITIONS[16] = {
    { "T704A4->T576A4", GBP_V28_T704, GBP_V28_A4, GBP_V28_T576, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { "T576A4->T704A4", GBP_V28_T576, GBP_V28_A4, GBP_V28_T704, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { "T576A4->T448A4", GBP_V28_T576, GBP_V28_A4, GBP_V28_T448, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { "T448A4->T576A4", GBP_V28_T448, GBP_V28_A4, GBP_V28_T576, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { "T448A4->T320A4", GBP_V28_T448, GBP_V28_A4, GBP_V28_T320, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { "T320A4->T448A4", GBP_V28_T320, GBP_V28_A4, GBP_V28_T448, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { "T320A4->T256A4", GBP_V28_T320, GBP_V28_A4, GBP_V28_T256, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { "T256A4->T320A4", GBP_V28_T256, GBP_V28_A4, GBP_V28_T320, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { "T256A4->T256A3", GBP_V28_T256, GBP_V28_A4, GBP_V28_T256, GBP_V28_A3, GBP_V28_STEP_MUTE },
    { "T256A3->T256A4", GBP_V28_T256, GBP_V28_A3, GBP_V28_T256, GBP_V28_A4, GBP_V28_STEP_MUTE },
    { "T256A3->T256A2", GBP_V28_T256, GBP_V28_A3, GBP_V28_T256, GBP_V28_A2, GBP_V28_STEP_MUTE },
    { "T256A2->T256A3", GBP_V28_T256, GBP_V28_A2, GBP_V28_T256, GBP_V28_A3, GBP_V28_STEP_MUTE },
    { "T256A2->T256A1", GBP_V28_T256, GBP_V28_A2, GBP_V28_T256, GBP_V28_A1, GBP_V28_STEP_MUTE },
    { "T256A1->T256A2", GBP_V28_T256, GBP_V28_A1, GBP_V28_T256, GBP_V28_A2, GBP_V28_STEP_MUTE },
    { "START T704A4->T256A1", GBP_V28_T704, GBP_V28_A4, GBP_V28_T256, GBP_V28_A1, GBP_V28_START_MUTE },
    { "START T256A1->T704A4", GBP_V28_T256, GBP_V28_A1, GBP_V28_T704, GBP_V28_A4, GBP_V28_START_MUTE },
};

static const int BURSTS[5] = { 0, 4, 8, 12, (int)CALLS_PER_PERIOD - 1 };
static const uint32_t PHASES[4] = { 0u, CALLS_PER_PERIOD / 4u, CALLS_PER_PERIOD / 2u, CALLS_PER_PERIOD - 1u };

static void test_the_sweep_s_own_transitions_under_every_burst_and_phase(void)
{
    uint32_t t, b, p, n = 0u, never = 0u;
    int32_t worst_residue = 0;
    const struct transition *worst_t = NULL;
    int worst_burst = -1;
    uint32_t worst_phase = 0u;

    for (t = 0; t < 16u; t++) {
        const struct transition *tt = &TRANSITIONS[t];
        int32_t t_worst = 0;
        int t_seen = 0;
        for (b = 0; b < 5u; b++) {
            burst_at = BURSTS[b];
            for (p = 0; p < 4u; p++) {
                struct landing l;
                char w[160];
                const int landed = land(tt->from_target, tt->from_ahead, tt->to_target, tt->to_ahead, tt->mute,
                                        PHASES[p], 40u, &l);
                n++;
                snprintf(w, sizeof w, "%s: lands within the bound (burst %d, phase %u)", tt->name, burst_at,
                        PHASES[p]);
                check(landed, w);
                if (!landed) { never++; continue; }

                /* TARGET: the ring after the trim never sits above target -- a genuine fault, not the
                 * trim's own doing, if it does; up to BAND below is a natural undershoot the trim never
                 * fixes (it only ever cuts downward). */
                snprintf(w, sizeof w, "%s: the ring never lands above target after the trim (burst %d, phase %u)",
                        tt->name, burst_at, PHASES[p]);
                check(l.ring <= tt->to_target, w);
                snprintf(w, sizeof w, "%s: the ring lands within BAND below target (burst %d, phase %u)", tt->name,
                        burst_at, PHASES[p]);
                check(l.ring + GBP_APLAY2_BAND >= tt->to_target, w);

                /* AHEAD: READY at landing is ahead-1 (ordinary) or ahead (a landing mid produce+rotate
                 * cycle -- the same LATE class the old path's own check_rotate() already tolerates). */
                snprintf(w, sizeof w, "%s: READY at landing is ahead-1 or ahead (burst %d, phase %u)", tt->name,
                        burst_at, PHASES[p]);
                check(l.ready == tt->to_ahead - 1u || l.ready == tt->to_ahead, w);

                if (!t_seen || (l.residue < 0 ? -l.residue : l.residue) > (t_worst < 0 ? -t_worst : t_worst)) {
                    t_worst = l.residue;
                    t_seen = 1;
                }
                if (worst_t == NULL ||
                    (l.residue < 0 ? -l.residue : l.residue) > (worst_residue < 0 ? -worst_residue : worst_residue)) {
                    worst_residue = l.residue;
                    worst_t = tt;
                    worst_burst = burst_at;
                    worst_phase = PHASES[p];
                }
            }
        }
        printf("    %-24s worst |residue| = %d\n", tt->name, (int)(t_worst < 0 ? -t_worst : t_worst));
    }
    burst_at = -1;
    printf("    %u runs (16 transitions x 5 bursts x 4 phases), %u never landed within the bound\n", n, never);
    if (worst_t)
        printf("    worst |residue| = %d samples (%.3f ms), transition %s, burst at %d, phase %u\n",
               (int)(worst_residue < 0 ? -worst_residue : worst_residue), (worst_residue < 0 ? -worst_residue :
               worst_residue) / 65.536, worst_t->name, worst_burst, worst_phase);
}

int main(void)
{
    test_the_sweep_s_own_transitions_under_every_burst_and_phase();
    printf("test_v28_sweep_residue: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
