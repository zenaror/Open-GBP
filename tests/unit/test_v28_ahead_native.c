/*
 * tests/unit/test_v28_ahead_native.c — GitHub Issue #129/#130: the native-path port of
 * test_v28_ahead_steps.c's own remaining scope (named a pre-staging item since #129's own step
 * mechanism landed) -- what that file proved on the OLD 4096 Hz path (gbp_aplay/gbp_atrans) that
 * this session's own native-path work (test_gbp_atrans2.c's AHEAD-lowering tests,
 * test_v28_sweep_residue.c's exhaustive burst/phase residue-and-safety matrix over all 16 of the
 * sweep's own transitions, the dedicated gbp_aplay2_drop_front() safety-property test) does NOT yet
 * cover: THE RULE (a step's own audible signature is identical across every kind, for the same feed
 * and phase -- #122's own §1(c), "nothing audible in a step depends on the TARGET or AHEAD in
 * force, on which moved, or on the step's direction"); D2-CLASS LOSSES (a drain that dropped
 * decoded blocks, in the plan's own first periods); and THE MASKING BOUND under a feed STALLED
 * inside the mute.
 *
 * Deliberately NOT re-proven here, already covered by this session's own native-path work:
 * the defect itself (an AHEAD-lowering step with no surplus drop) and its own fix -- test_gbp_atrans2.c's
 * own test_ahead_lower_drops_the_surplus_fronts(); the candidate's own full landing checks across
 * every rung, burst and phase -- test_v28_sweep_residue.c's own exhaustive matrix (16 transitions x
 * 5 bursts x 4 phases, all structural, all exact residue) and gbp_v28_sweep's own real cascade;
 * STARTs along the ladder -- test_v28_sweep_residue.c's own two START entries, at GBP_V28_START_MUTE
 * (this file's own "the need at a tight mute" section 6 is likewise already this: gbp_atrans2_min_mute()
 * is exercised directly by every call in the matrix above); the AHEAD-1 landing-margin question
 * this whole round's own DEVLOG entries settled (three fixes, each proven by a direct 60 s hold and
 * the residue matrix, not repeated here).
 *
 * Native units throughout (gbp_v28_ladder.h's own T/A constants, GBP_V28_STEP_MUTE), the SAME
 * bursty-feed methodology test_v28_sweep_residue.c already established (CALLS_PER_PERIOD = 16,
 * slice2()/feed_at()), extended here with the three feed kinds this file's own OLD-path ancestor
 * used that the residue matrix does not: MEASURED (a seeded bursty regime, RUN 43's own class, not
 * its own exact numbers -- this path's own decode rate differs), LOSS (samples missing from a
 * chosen period on), and STALL (nothing arrives for n periods).
 */
#include <stdio.h>
#include <string.h>
#include "gbp_atrans2.h"
#include "gbp_v28_ladder.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
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

#define CALLS_PER_PERIOD 16u

/* ---- the three feed kinds this file's own ancestor used that the residue matrix does not ------ */
enum feed_kind { FEED_SMOOTH = 0, FEED_BURST = 1, FEED_MEASURED = 2 };
struct feed { int kind; int burst_at; uint32_t seed; uint32_t loss; uint32_t loss_period; uint32_t stall; };
static struct feed FEED;
static uint32_t amounts[CALLS_PER_PERIOD];
static uint32_t rng, def_acc, loss_left;

static uint32_t xs(void)
{
    rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
    return rng;
}

static void feed_start(void)
{
    rng = FEED.seed ? FEED.seed : 0x9E3779B9u;
    def_acc = 0u;
    loss_left = FEED.loss;
}

static uint32_t slice2(uint32_t k)
{
    return (k + 1u) * GBP_APLAY2_PUSHES / CALLS_PER_PERIOD - k * GBP_APLAY2_PUSHES / CALLS_PER_PERIOD;
}

/* one period's own feed, into `amounts[0..CALLS_PER_PERIOD)`: SMOOTH/BURST match
 * test_v28_sweep_residue.c's own slice2()/feed_at(); MEASURED is a seeded bursty regime of the SAME
 * CLASS RUN 43 measured (a fractional deficit accumulated a period, 1-6 bursts placed by a seeded
 * xorshift32) -- this path's own rate, not the old path's own 10.47 samples/s figure, which does not
 * apply at 65536 Hz. LOSS removes samples from a chosen period on, STALL withholds every period
 * before a chosen one -- both exactly as the ancestor file's own period_feed(). */
static void period_feed(uint32_t i)
{
    uint32_t k, total = GBP_APLAY2_PUSHES, n, b;
    memset(amounts, 0, sizeof amounts);
    if (FEED.stall && i < FEED.stall) return;
    if (FEED.kind == FEED_SMOOTH) {
        for (k = 0; k < CALLS_PER_PERIOD; k++) amounts[k] = slice2(k);
    } else if (FEED.kind == FEED_BURST) {
        amounts[(uint32_t)FEED.burst_at] = GBP_APLAY2_PUSHES;
    } else {
        def_acc += 327u;                                  /* an arbitrary, small, deterministic deficit */
        if (def_acc >= 1000u) { def_acc -= 1000u; total -= CALLS_PER_PERIOD; }
        n = 1u + xs() % 6u;
        for (b = 0; b < n; b++) {
            const uint32_t part = b + 1u == n ? total : (total * (1u + xs() % 3u)) / (2u * n + 2u);
            amounts[xs() % CALLS_PER_PERIOD] += part;
            total -= part;
        }
    }
    if (loss_left && i >= FEED.loss_period) {
        for (k = 0; k < CALLS_PER_PERIOD && loss_left; k++) {
            const uint32_t take = amounts[k] < loss_left ? amounts[k] : loss_left;
            amounts[k] -= take;
            loss_left -= take;
        }
    }
}

static void set_feed(int kind, int burst_at, uint32_t seed, uint32_t loss, uint32_t loss_period, uint32_t stall)
{
    FEED.kind = kind; FEED.burst_at = burst_at; FEED.seed = seed;
    FEED.loss = loss; FEED.loss_period = loss_period; FEED.stall = stall;
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

static uint64_t steady2(uint32_t target, uint32_t ahead)
{
    uint64_t now = 0;
    uint32_t i, k;
    memset(&ap, 0, sizeof ap);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    gbp_atrans2_init(&tr);
    ap.ahead = ahead;
    gbp_aplay2_set_target(&ap, target);
    give2(&adec, target, 100);
    for (i = 0; i < ahead; i++) prime_period2(&now);
    ap.playing = 1u;
    for (i = 0; i < 16u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(now); now++; }
    }
    return now;
}

struct landing {
    int32_t effective;       /* the effective level at the landing: gbp_atrans2's own residue */
    uint32_t mute_handed;     /* the silence actually handed */
    uint8_t  late, unmasked;  /* gbp_atrans2's own flags */
    uint8_t  first_audible_pre;   /* the first AUDIBLE hand-off plays a chunk queued before the plan */
    uint32_t ready_begin, rotations;
    uint8_t  under_way_begin;
};

/* one plan from (t0, a0) to (t1, a1), begun at pump call `phase`; `periods` after it (bounded).
 * `discard` is the begin's own shallowing discard (0 for every real native caller today --
 * gbp_v28_sweep/3a/3b always pass 0u, converging on a downward step through the landing's own ring
 * trim instead of an eager begin-time discard -- so every OTHER section here passes 0u to match
 * actual production usage exactly). It exists as a parameter, not a hardcoded 0, because THE
 * MASKING BOUND below needs to drive gbp_atrans2's own EXISTING discard>0 code path (already
 * unit-tested once, at a single scenario, by test_gbp_atrans2.c's own test_rotate_with_discard())
 * across the fuller phase/AHEAD/stall sweep this file's own OLD-path ancestor ran it through. */
static struct landing run(uint32_t t0, uint32_t a0, uint32_t t1, uint32_t a1, uint32_t mute, uint32_t phase,
                          uint32_t discard, uint32_t periods)
{
    struct landing L;
    uint64_t now = steady2(t0, a0);
    uint32_t i, k, first_fresh = 0u;
    int begun = 0, seen_end = 0;
    memset(&L, 0, sizeof L);
    feed_start();
    for (i = 0; i <= periods; i++) {
        const uint32_t head_idx = ap.rq[ap.rq_head % GBP_APLAY2_POOL];
        const uint8_t *played;
        period_feed(i);
        played = gbp_aplay2_irq_handoff(&ap, now);
        /* the buffer a hand-off actually plays (dequeued from rq, inside the call itself) is
         * distinguished from silence (mute OR a genuine underrun, both return p->silence) by the
         * RETURNED POINTER -- not by reading `ap.mute` from outside, which the mute_carry comment
         * (gbp_aplay2.h) warns reads one call stale for exactly this kind of external check.
         * `head_idx` is captured BEFORE the call, since the call itself advances rq_head. */
        if (begun && !L.first_audible_pre && !seen_end && played != ap.silence
            && ap.seq[head_idx] < first_fresh)
            L.first_audible_pre = 1u;
        for (k = 0; k < CALLS_PER_PERIOD; k++) {
            give2(&adec, amounts[k], 100);
            if (i == 0u && k == phase) {
                first_fresh = ap.produced + (ap.cur >= 0 ? 1u : 0u);
                L.ready_begin = gbp_aplay2_ready(&ap);
                L.under_way_begin = (uint8_t)(ap.cur >= 0 ? 1u : 0u);
                (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mute, 0u, discard, t1, a1);
                begun = 1;
            }
            pump2(now);
            if (begun && !seen_end && !tr.active) {
                seen_end = 1;
                L.effective = tr.residue;
                L.mute_handed = ap.mute_handed;
                L.late = tr.late;
                L.unmasked = tr.unmasked;
                L.rotations = tr.rotations;
            }
            now++;
        }
    }
    return L;
}

#define SHORT 30u   /* periods after a plan for a landing's own signature -- comfortably past any mute */

static const uint32_t PHASES[4] = { 0u, CALLS_PER_PERIOD / 4u, CALLS_PER_PERIOD / 2u, CALLS_PER_PERIOD - 1u };
static const int BURSTS[3] = { 3, (int)CALLS_PER_PERIOD / 2, (int)CALLS_PER_PERIOD - 2 };

/* ================================================================================================
 * Section 1: THE RULE -- a step's own audible signature is identical across every kind, for the
 * same feed and phase (#122's own §1(c), quoted in #128 §3).
 * ================================================================================================ */

struct plan { uint32_t t0, a0, t1, a1; };

/* 13 plans of every kind the sweep and 3b exercise: refused, TARGET up/down, AHEAD up/down (both
 * directions), a climb/descent off the anchor at every AHEAD, the largest START both ways, and a
 * refused START. Anchored at T256 (the perceptual anchor) and, separately, at T320, matching the
 * ancestor file's own two anchors (192/256 there; T256/T320 here, both on the frozen native ladder). */
static const struct plan PLANS_T256[13] = {
    { GBP_V28_T256, GBP_V28_A4, GBP_V28_T256, GBP_V28_A4 },
    { GBP_V28_T320, GBP_V28_A4, GBP_V28_T256, GBP_V28_A4 },
    { GBP_V28_T256, GBP_V28_A4, GBP_V28_T320, GBP_V28_A4 },
    { GBP_V28_T256, GBP_V28_A4, GBP_V28_T256, GBP_V28_A3 },
    { GBP_V28_T256, GBP_V28_A3, GBP_V28_T256, GBP_V28_A4 },
    { GBP_V28_T256, GBP_V28_A1, GBP_V28_T256, GBP_V28_A1 },
    { GBP_V28_T256, GBP_V28_A2, GBP_V28_T256, GBP_V28_A1 },
    { GBP_V28_T256, GBP_V28_A1, GBP_V28_T256, GBP_V28_A2 },
    { GBP_V28_T320, GBP_V28_A1, GBP_V28_T256, GBP_V28_A1 },
    { GBP_V28_T256, GBP_V28_A1, GBP_V28_T320, GBP_V28_A1 },
    { GBP_V28_T704, GBP_V28_A4, GBP_V28_T576, GBP_V28_A4 },
    { GBP_V28_T576, GBP_V28_A4, GBP_V28_T704, GBP_V28_A4 },
    { GBP_V28_T704, GBP_V28_A4, GBP_V28_T704, GBP_V28_A4 },
};
static const struct plan PLANS_T320[13] = {
    { GBP_V28_T320, GBP_V28_A4, GBP_V28_T320, GBP_V28_A4 },
    { GBP_V28_T448, GBP_V28_A4, GBP_V28_T320, GBP_V28_A4 },
    { GBP_V28_T320, GBP_V28_A4, GBP_V28_T448, GBP_V28_A4 },
    { GBP_V28_T320, GBP_V28_A4, GBP_V28_T320, GBP_V28_A3 },
    { GBP_V28_T320, GBP_V28_A3, GBP_V28_T320, GBP_V28_A4 },
    { GBP_V28_T320, GBP_V28_A1, GBP_V28_T320, GBP_V28_A1 },
    { GBP_V28_T320, GBP_V28_A2, GBP_V28_T320, GBP_V28_A1 },
    { GBP_V28_T320, GBP_V28_A1, GBP_V28_T320, GBP_V28_A2 },
    { GBP_V28_T448, GBP_V28_A1, GBP_V28_T320, GBP_V28_A1 },
    { GBP_V28_T320, GBP_V28_A1, GBP_V28_T448, GBP_V28_A1 },
    { GBP_V28_T704, GBP_V28_A4, GBP_V28_T576, GBP_V28_A4 },
    { GBP_V28_T576, GBP_V28_A4, GBP_V28_T704, GBP_V28_A4 },
    { GBP_V28_T704, GBP_V28_A4, GBP_V28_T704, GBP_V28_A4 },
};

struct sig { int32_t eff; uint32_t mute; uint8_t late, unmasked, pre; };

/* 1 when every plan's own signature equals the first's; counts landings with a splice heard */
static int alike(const struct plan *P, uint32_t mute, uint32_t phase, uint32_t *heard)
{
    uint32_t p;
    struct sig s0, s;
    int same = 1;
    memset(&s0, 0, sizeof s0);
    for (p = 0; p < 13u; p++) {
        const struct landing L = run(P[p].t0, P[p].a0, P[p].t1, P[p].a1, mute, phase, 0u, SHORT);
        memset(&s, 0, sizeof s);
        s.eff = L.effective; s.mute = L.mute_handed; s.late = L.late; s.unmasked = L.unmasked;
        s.pre = (uint8_t)(P[p].t0 > P[p].t1 ? L.first_audible_pre : 0u);
        if (s.pre) (*heard)++;
        if (p == 0u) s0 = s;
        else if (memcmp(&s, &s0, sizeof s) != 0) same = 0;
    }
    return same;
}

static void test_the_rule(void)
{
    uint32_t b, sd, ph, groups, differ, heard;
    char w[200];
    printf("-- 1. the rule: one signature for every kind of step, loss-free feeds\n");
    groups = differ = heard = 0u;
    for (ph = 0; ph < 4; ph++) {
        set_feed(FEED_SMOOTH, 0, 0u, 0u, 0u, 0u);
        groups++; differ += (uint32_t)!alike(PLANS_T256, GBP_V28_STEP_MUTE, PHASES[ph], &heard);
        groups++; differ += (uint32_t)!alike(PLANS_T320, GBP_V28_STEP_MUTE, PHASES[ph], &heard);
        for (b = 0; b < CALLS_PER_PERIOD; b++) {
            set_feed(FEED_BURST, (int)b, 0u, 0u, 0u, 0u);
            groups++; differ += (uint32_t)!alike(PLANS_T256, GBP_V28_STEP_MUTE, PHASES[ph], &heard);
        }
        for (sd = 1; sd <= 8u; sd++) {
            set_feed(FEED_MEASURED, 0, sd * 2654435761u, 0u, 0u, 0u);
            groups++; differ += (uint32_t)!alike(PLANS_T256, GBP_V28_STEP_MUTE, PHASES[ph], &heard);
        }
    }
    printf("   %u of %u loss-free groups differ, %u splices heard\n", differ, groups, heard);
    snprintf(w, sizeof w, "every loss-free group alike (%u groups)", groups);
    eqi(differ, 0, w);
    snprintf(w, sizeof w, "no splice heard, loss-free");
    eqi(heard, 0, w);
}

/* ================================================================================================
 * Section 2: D2-CLASS LOSSES -- a drain that dropped decoded blocks, in the plan's own first
 * periods.
 * ================================================================================================ */

static uint32_t loss_sweep(const struct plan *P, uint32_t mute, uint32_t loss, uint32_t *heard)
{
    uint32_t lp, ph, b, sd, differ = 0u;
    for (lp = 0; lp <= 4u; lp += 2u) {
        for (ph = 0; ph < 4; ph++) {
            set_feed(FEED_SMOOTH, 0, 0u, loss, lp, 0u);
            differ += (uint32_t)!alike(P, mute, PHASES[ph], heard);
            for (b = 0; b < 3; b++) {
                set_feed(FEED_BURST, BURSTS[b], 0u, loss, lp, 0u);
                differ += (uint32_t)!alike(P, mute, PHASES[ph], heard);
            }
            for (sd = 1; sd <= 2u; sd++) {
                set_feed(FEED_MEASURED, 0, sd * 2654435761u, loss, lp, 0u);
                differ += (uint32_t)!alike(P, mute, PHASES[ph], heard);
            }
        }
    }
    return differ;   /* of 3 x 4 x 6 = 72 groups */
}

static void test_losses(void)
{
    static const uint32_t LOSS[5] = { 16u, 32u, 64u, 100u, 128u };
    uint32_t l, d256, h256;
    char w[200];
    printf("-- 2. D2-class losses in the plan's own first periods (72 groups each)\n");
    for (l = 0; l < 5; l++) {
        h256 = 0u;
        d256 = loss_sweep(PLANS_T256, GBP_V28_STEP_MUTE, LOSS[l], &h256);
        printf("   anchor T256, mute %u, loss %3u: %2u groups differ, %2u splices heard\n", GBP_V28_STEP_MUTE,
               LOSS[l], d256, h256);
        snprintf(w, sizeof w, "anchor T256, loss %u: every group alike, no splice heard", LOSS[l]);
        eqi((long long)(d256 + h256), 0, w);
    }
}

/* ================================================================================================
 * Section 3: THE MASKING BOUND -- shallowings with the feed stalled inside the mute, so that some
 * land with fewer rotations than AHEAD.
 * ================================================================================================ */

static void test_the_masking_bound(void)
{
    uint32_t a, st, ph, n = 0u, heard = 0u, cautious = 0u;
    char w[240];
    printf("-- 3. the masking bound: shallowings with the feed stalled inside the mute\n");
    for (a = 1; a <= 4; a++) {
        for (st = 1; st <= GBP_V28_STEP_MUTE; st++) {
            for (ph = 0; ph < 4; ph++) {
                struct landing L;
                set_feed(FEED_SMOOTH, 0, 0u, 0u, 0u, st);
                L = run(GBP_V28_T320, a, GBP_V28_T256, a, GBP_V28_STEP_MUTE, PHASES[ph],
                        GBP_V28_T320 - GBP_V28_T256, SHORT);
                n++; heard += L.first_audible_pre;
                if (L.first_audible_pre) {
                    snprintf(w, sizeof w, "A%u stall %u phase %u: a splice heard is flagged unmasked (%u rotations)",
                             a, st, PHASES[ph], L.rotations);
                    eqi(L.unmasked, 1, w);
                } else if (L.unmasked) {
                    cautious++;
                    snprintf(w, sizeof w, "A%u stall %u phase %u: a flag with no splice heard only when fewer than "
                             "AHEAD pre-plan chunks were held (READY %u, under way %u)", a, st, PHASES[ph],
                             L.ready_begin, L.under_way_begin);
                    eqi((long long)(L.ready_begin + L.under_way_begin < a), 1, w);
                    snprintf(w, sizeof w, "A%u stall %u phase %u: ... and it missed by the one chunk", a, st,
                             PHASES[ph]);
                    eqi((long long)(L.rotations + 1u >= L.ready_begin + L.under_way_begin), 1, w);
                }
            }
        }
    }
    printf("   %u shallowings: %u splices heard, all flagged; %u flagged with none heard (cautious)\n", n, heard,
           cautious);
    snprintf(w, sizeof w, "the stalls produced splices heard to check (%u)", heard);
    eqi((long long)(heard > 0u), 1, w);
}

int main(void)
{
    test_the_rule();
    test_losses();
    test_the_masking_bound();
    printf("test_v28_ahead_native: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
