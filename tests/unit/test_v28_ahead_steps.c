/*
 * tests/unit/test_v28_ahead_steps.c — GitHub Issue #122: a PROBE of the nulling steps §V28 proposes, run against
 * the REAL chain (gbp_aplay, gbp_atrans, gbp_adec) with GBP_APLAY_AHEAD made a runtime value, before the freeze.
 *
 * WHAT IS PROBED. Every nulling step and every refused step a ROTATE plan with one fixed step mute; a step LOWERING
 * AHEAD by k also drops k READY fronts without replacement right after the begin, under the silence (inside
 * gbp_aplay_drop_front's own boundary, mute >= 1). The Orchestrator asked for this to be executed against the chain
 * before the freeze (§V27.13: a frozen mechanism carries its arithmetic).
 *
 * HOW. The Makefile builds copies of src/audio/gbp_aplay.c and gbp_atrans.c in which every use of the
 * GBP_APLAY_AHEAD macro (2 + 5, counted by the rule) reads `gbp_v28_ahead`, defined here; the plan sets it to the
 * AHEAD it lands at before gbp_atrans_begin, so the masking bound (gbp_atrans.c:86) is the AHEAD in force AFTER the
 * surplus drop: the pre-plan chunks left in READY are then exactly that many. The header's default, 4, and src/
 * are unchanged. The model is test_gbp_atrans.c's: one AI hand-off per period, PUMPS pump calls per period, the
 * plan begun at four phases of a period. THE FEEDS during a plan: smooth; one burst of 128 at a chosen pump call
 * (every one of the 110 in the identity sweep); the MEASURED regime (10.47 samples/s under the AI, RUN 43's
 * deficit, in 1-6 bursts a period at pump calls a seeded xorshift32 draws); a feed STALL (nothing for n periods);
 * and a LOSS of n samples from a chosen period on (a drain that dropped blocks, D2's class).
 *
 * WHAT IS ASSERTED.
 *   1. THE DEFECT, EXECUTED: with no surplus drop, lowering AHEAD fails the landing check at every begin with READY
 *      whole (READY one chunk long per chunk lowered, the effective level +128 a chunk, DROPs after) while
 *      conservation HOLDS: conservation alone cannot be the proof.
 *   2. THE CANDIDATE, at mutes 5 and 6, on every single-rung step of the proposed ladder (TARGET at AHEAD 4 between
 *      704 and 192, AHEAD at TARGET 192 between 4 and 1, both directions), the refused step at every rung and
 *      TARGET steps at AHEAD 1-3, at four phases, under the smooth feed and bursts at pump calls 3, 55 and 108:
 *      the steady state before it; no fault; the silence exactly the mute; MASKED -- every READY chunk at the
 *      landing, and the chunk the first audible hand-off plays, started after the plan; the executor's residue
 *      (gbp_atrans.c:77) equal to the effective level; READY == AHEAD - 1 and the residue within the aim at a
 *      non-late landing, one chunk long at a late one; the fronts dropped = rotations + the surplus; the ring
 *      discard = the plan's; no underrun; the band correcting only what lies outside it and settling within 2 s
 *      (4.5 s late); READY whole 160 periods on; conservation.
 *   3. THE RULE -- nothing audible in a step depends on the TARGET or AHEAD in force, on which moved, or on the
 *      direction: across 13 plans of every kind, the step's signature (late, unmasked, the first audible chunk
 *      pre-plan, the effective level at the landing, the silence) is IDENTICAL for the same feed and phase, at
 *      mutes 5 and 6, under the smooth feed, a burst at every one of the 110 pump calls and 16 measured-regime
 *      seeds; and under drain losses of 16 and 32 samples.
 *   4. D2-CLASS LOSSES (64-128 samples in the first periods of a plan): at mute 5 a TARGET-down step can land
 *      UNMASKED (a splice heard after the silence) where no other kind does; at mute 6 none does. At mute 6 the
 *      ladder anchored at TARGET 192 still lands a 64-sample loss one chunk late on some rungs and not others
 *      (192 sits 46 samples above the 129-sample gate); anchored at TARGET 256 every loss up to 128 lands alike.
 *      Pinned as measured, for the freeze to weigh. RUN 43 had no such loss in its session (its largest gap
 *      between decoded blocks, 0.526 ms: INFERENCE that none of this class occurred).
 *   5. THE MASKING BOUND: shallowings with the feed stalled inside the mute, so that some land with fewer
 *      rotations than AHEAD. A splice heard (the first audible chunk pre-plan) is always flagged unmasked; a flag
 *      with none heard happens only where a begin before the refill started held one pre-plan chunk fewer than
 *      AHEAD (the bound at gbp_atrans.c:86 is cautious there, with the macro as with the runtime value).
 *   6. THE NEED at a tight mute (pause + AHEAD, AHEAD < 4): no fault and exactly that silence (gbp_atrans.c:17).
 *   7. STARTs along the ladder at mutes 11 (the largest need) and 18, both directions: section 2's checks.
 * Not exercised: HELD (gbp_atrans.c:153; the proposal retires it for steps) and ring_gated (gbp_aplay.c:141; the
 * TARGET descent stays at AHEAD 4). A probe, not the implementation: the build carries the runtime AHEAD into src/
 * after the freeze; these are the assertions that implementation must meet.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_atrans.h"
#include "v28_ahead.h"

uint32_t gbp_v28_ahead = GBP_APLAY_AHEAD;

static uint8_t pool[GBP_APLAY_POOL * GBP_APLAY_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY_CHUNK_BYTES];
static int16_t ring[GBP_APLAY_RING];
static struct gbp_aplay ap;
static struct gbp_adec adec;
static struct gbp_atrans tr;

#define PUMPS 110u

static void give(uint32_t n)
{
    uint32_t k;
    for (k = 0; k < n && adec.count < adec.cap; k++) {
        adec.ring[(adec.head + adec.count) % adec.cap] = 100;
        adec.count++;
    }
}

static uint32_t slice(uint32_t k)
{
    return (k + 1u) * 128u / PUMPS - k * 128u / PUMPS;
}

/* THE FEED during a plan, period by period (period 0 is the begin's):
 *   SMOOTH    128 a period in slices;
 *   BURST     128 at pump call `burst_at` of every period;
 *   MEASURED  the regime RUN 43 measured: 10.47 samples/s under the AI (one sample fewer every ~3 periods) in
 *             1-6 bursts a period at pump calls a xorshift32 seeded per run draws;
 * and on any of them, LOSS samples missing from period `loss_period` on (a drain that dropped blocks). */
enum feed_kind { FEED_SMOOTH = 0, FEED_BURST = 1, FEED_MEASURED = 2 };
struct feed { int kind; int burst_at; uint32_t seed; uint32_t loss; uint32_t loss_period; uint32_t stall; };
static struct feed FEED;
static uint32_t amounts[PUMPS];
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

static void period_feed(uint32_t i)
{
    uint32_t k, total = 128u, n, b;
    memset(amounts, 0, sizeof amounts);
    if (FEED.stall && i < FEED.stall) return;          /* a drain that stopped: nothing arrives */
    if (FEED.kind == FEED_SMOOTH) {
        for (k = 0; k < PUMPS; k++) amounts[k] = slice(k);
    } else if (FEED.kind == FEED_BURST) {
        amounts[FEED.burst_at] = 128u;
    } else {
        def_acc += 3269u;                               /* 10.47 samples/s x 31.222 ms = 0.3269 a period */
        if (def_acc >= 10000u) { def_acc -= 10000u; total = 127u; }
        n = 1u + xs() % 6u;
        for (b = 0; b < n; b++) {
            const uint32_t part = b + 1u == n ? total : (total * (1u + xs() % 3u)) / (2u * n + 2u);
            amounts[xs() % PUMPS] += part;
            total -= part;
        }
    }
    if (loss_left && i >= FEED.loss_period) {
        for (k = 0; k < PUMPS && loss_left; k++) {
            const uint32_t take = amounts[k] < loss_left ? amounts[k] : loss_left;
            amounts[k] -= take;
            loss_left -= take;
        }
    }
}

static void pump(uint64_t now)
{
    int b;
    if (tr.active) (void)gbp_atrans_step(&tr, &ap, &adec, now, &b);
    else b = gbp_aplay_produce(&ap, &adec);
    if (b >= 0) gbp_aplay_queue(&ap, b);
    gbp_aplay_process(&ap);
}

static void prime_period(uint64_t *now)
{
    uint32_t k;
    int done = 0;
    for (k = 0; k < PUMPS; k++) {
        give(slice(k));
        if (!done) {
            int b = gbp_aplay_produce(&ap, &adec);
            if (b >= 0) { gbp_aplay_queue(&ap, b); done = 1; }
        }
        gbp_aplay_process(&ap);
        (*now)++;
    }
}

static int steady_ok;
static uint64_t steady(uint32_t target, uint32_t ahead)
{
    uint64_t now = 0;
    uint32_t i, k;
    memset(&ap, 0, sizeof ap);
    gbp_adec_init(&adec, ring, GBP_APLAY_RING);
    gbp_aplay_init(&ap, pool, silence, NULL, NULL);
    gbp_atrans_init(&tr);
    gbp_v28_ahead = ahead;
    gbp_aplay_set_target(&ap, target);
    give(target);
    for (i = 0; i < ahead; i++) prime_period(&now);
    ap.playing = 1u;
    for (i = 0; i < 16; i++) {
        (void)gbp_aplay_irq_handoff(&ap, now);
        for (k = 0; k < PUMPS; k++) { give(slice(k)); pump(now); now++; }
    }
    steady_ok = adec.count == target && gbp_aplay_ready(&ap) == ahead && ap.dup == 0u && ap.drop == 0u;
    return now;
}

struct landing {
    uint32_t count_after, ready_after, fresh_after, ready_begin, under_way_begin;
    uint32_t drops, dups, mute_handed, dropped, begin_drops, discarded, rotations;
    uint32_t count_end, ready_end, count_2s, count_45s, underruns;
    int32_t fed, played, skipped, stock0, stock1, effective, residue_exec;
    uint8_t late, unmasked, faults, first_audible_pre, first_audible_seen, steady;
};

static int32_t stock(void)
{
    return (int32_t)(adec.count + 128u * gbp_aplay_ready(&ap) + (ap.cur >= 0 ? ap.cur_pushes : 0u));
}

static uint32_t landed(void)
{
    return adec.count + (ap.cur >= 0 ? ap.cur_pushes : 0u);
}

static uint32_t fresh_in_ready(uint32_t first_fresh_seq)
{
    uint32_t h, n = 0u;
    for (h = ap.rq_head; h != ap.rq_tail; h++)
        if (ap.seq[ap.rq[h % GBP_APLAY_POOL]] >= first_fresh_seq) n++;
    return n;
}

enum variant { ROTATE_ONLY = 0, CANDIDATE = 1 };

/* one plan from (t0, a0) to (t1, a1), begun at pump call `phase` of a period; `periods` after it */
static struct landing run(uint32_t t0, uint32_t a0, uint32_t t1, uint32_t a1, uint32_t mute, uint32_t phase,
                          enum variant v, uint32_t periods)
{
    struct landing L;
    const int32_t s0 = (int32_t)(t0 + 128u * a0), s1 = (int32_t)(t1 + 128u * a1);
    const uint32_t discard = t0 > t1 ? t0 - t1 : 0u;
    const uint32_t pause = s1 > s0 ? (uint32_t)((s1 - s0 + 127) / 128) : 0u;
    uint64_t now = steady(t0, a0);
    uint32_t i, k, drop0 = 0u, dup0 = 0u, muted0, dropped0, disc0, first_fresh = 0u, i_end = 0u, under0;
    uint32_t handed0 = 0u, silent0 = 0u, discchunks0 = 0u;
    int seen_end = 0, begun = 0;
    memset(&L, 0, sizeof L);
    L.steady = (uint8_t)steady_ok;
    muted0 = ap.mute_handed; dropped0 = ap.dropped_front; disc0 = adec.discarded; under0 = ap.underruns;
    feed_start();
    for (i = 0; i <= periods; i++) {
        period_feed(i);
        /* the chunk the first AUDIBLE hand-off plays: a pre-plan chunk there is a splice heard after the silence */
        if (begun && !L.first_audible_seen && ap.mute == 0u) {
            L.first_audible_seen = 1u;
            if (ap.rq_head != ap.rq_tail) L.first_audible_pre = (uint8_t)(ap.seq[ap.rq[ap.rq_head % GBP_APLAY_POOL]] < first_fresh);
        }
        (void)gbp_aplay_irq_handoff(&ap, now);
        for (k = 0; k < PUMPS; k++) {
            if (begun && !seen_end) L.fed += (int32_t)amounts[k];
            give(amounts[k]);
            if (i == 0u && k == phase) {
                first_fresh = ap.produced + (ap.cur >= 0 ? 1u : 0u);
                L.stock0 = stock();
                handed0 = ap.handed; silent0 = ap.mute_handed; discchunks0 = ap.discarded_chunks;
                L.ready_begin = gbp_aplay_ready(&ap);
                L.under_way_begin = ap.cur >= 0 ? 1u : 0u;
                gbp_v28_ahead = a1;
                gbp_atrans_begin(&tr, &ap, &adec, now, GBP_ATRANS_ROTATE, mute, pause, discard, t1);
                if (v == CANDIDATE)
                    for (; a1 + L.begin_drops < a0 && gbp_aplay_drop_front(&ap) >= 0; L.begin_drops++) { }
                begun = 1;
            }
            pump(now);
            if ((i > 0u || k >= phase) && begun && !seen_end && !tr.active) {
                seen_end = 1;
                i_end = i;
                L.count_after = landed();
                L.ready_after = gbp_aplay_ready(&ap);
                L.fresh_after = fresh_in_ready(first_fresh);
                L.dropped = ap.dropped_front - dropped0;
                L.discarded = adec.discarded - disc0;
                L.stock1 = stock();
                L.effective = (int32_t)landed() + 128 * ((int32_t)gbp_aplay_ready(&ap) - (int32_t)(a1 - 1u))
                            - (int32_t)t1;
                L.residue_exec = tr.residue;
                L.rotations = tr.rotations;
                L.played = (int32_t)(128u * ((ap.handed - handed0) - (ap.mute_handed - silent0)));
                L.skipped = (int32_t)((adec.discarded - disc0) + 128u * ((ap.dropped_front - dropped0) +
                                                                          (ap.discarded_chunks - discchunks0)));
                L.late = tr.late; L.unmasked = tr.unmasked; L.faults = (uint8_t)tr.faults;
                drop0 = ap.drop; dup0 = ap.dup;
            }
            if (seen_end && i == i_end + 64u && k == 1u) L.count_2s = adec.count;
            if (seen_end && i == i_end + 144u && k == 1u) L.count_45s = adec.count;
            now++;
        }
    }
    L.drops = ap.drop - drop0; L.dups = ap.dup - dup0;
    L.mute_handed = ap.mute_handed - muted0;
    L.count_end = adec.count; L.ready_end = gbp_aplay_ready(&ap);
    L.underruns = ap.underruns - under0;
    return L;
}

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

#define STEP_MUTE  5u                   /* the proposed step mute: a one-chunk step up needs 1 + 4 */
#define POST       160u                 /* periods after a plan for the full checks */
#define SHORT      24u                  /* periods after a plan for a landing's signature */

static const uint32_t PHASES[4] = { 0u, PUMPS / 4u, PUMPS / 2u, PUMPS - 1u };
static const int BURSTS[3] = { 3, PUMPS / 2, PUMPS - 2 };

static int conserved(const struct landing *L)
{
    return L->fed == L->played + L->skipped + (L->stock1 - L->stock0);
}

static void set_feed(int kind, int burst_at, uint32_t seed, uint32_t loss, uint32_t loss_period, uint32_t stall)
{
    FEED.kind = kind; FEED.burst_at = burst_at; FEED.seed = seed;
    FEED.loss = loss; FEED.loss_period = loss_period; FEED.stall = stall;
}

/* the landing the proposal needs, whichever variable moved and in whichever direction */
static int landing_ok(const struct landing *L, uint32_t t1, uint32_t a1)
{
    const int32_t res = (int32_t)L->count_after - (int32_t)t1;
    const int32_t eff = L->effective < 0 ? -L->effective : L->effective;
    if (L->late) {
        if (L->ready_after != a1) return 0;             /* the late chunk queued undropped: one chunk long */
        if (res < -(int32_t)GBP_ATRANS_AIM - 2 || res > (int32_t)GBP_ATRANS_AIM + 2) return 0;
    } else {
        if (L->ready_after != a1 - 1u) return 0;
        if (res < -(int32_t)GBP_ATRANS_AIM - 2 || res > (int32_t)GBP_ATRANS_AIM + 2) return 0;
        if (L->effective != res) return 0;
    }
    if (L->drops + L->dups > (uint32_t)eff) return 0;                 /* the band corrects only what is outside it */
    if (L->ready_end != a1 || L->count_end + 17u < t1 || L->count_end > t1 + 16u) return 0;
    return 1;
}

static void check_candidate(const char *name, const struct landing *L, uint32_t t1, uint32_t a1, uint32_t mute,
                            uint32_t discard, uint32_t surplus)
{
    char w[480];
    snprintf(w, sizeof w, "%s: steady at the level before the plan", name);          eqi(L->steady, 1, w);
    snprintf(w, sizeof w, "%s: no fault", name);                                   eqi(L->faults, 0, w);
    snprintf(w, sizeof w, "%s: the silence is the mute", name);                    eqi(L->mute_handed, mute, w);
    snprintf(w, sizeof w, "%s: MASKED -- every READY chunk at the landing started after the plan", name);
    eqi(L->fresh_after, L->ready_after, w);
    snprintf(w, sizeof w, "%s: MASKED -- the first audible hand-off plays a chunk started after the plan", name);
    eqi(discard ? L->first_audible_pre : 0, 0, w);
    snprintf(w, sizeof w, "%s: not flagged unmasked", name);                        eqi(L->unmasked, 0, w);
    snprintf(w, sizeof w, "%s: the executor's residue is the effective level", name);
    eqi(L->residue_exec, L->effective, w);
    snprintf(w, sizeof w, "%s: the landing (READY %u, residue %d, effective %d, late %u, drops %u, dups %u)", name,
             L->ready_after, (int)((int32_t)L->count_after - (int32_t)t1), (int)L->effective, L->late, L->drops,
             L->dups);
    eqi(landing_ok(L, t1, a1), 1, w);
    snprintf(w, sizeof w, "%s: the fronts dropped are the rotations and the surplus", name);
    eqi(L->dropped, L->rotations + surplus, w);
    snprintf(w, sizeof w, "%s: the surplus dropped", name);                         eqi(L->begin_drops, surplus, w);
    snprintf(w, sizeof w, "%s: nothing left the ring's head but the plan's discard", name);  eqi(L->discarded, discard, w);
    snprintf(w, sizeof w, "%s: no underrun", name);                                 eqi(L->underruns, 0, w);
    if (!L->late) {
        snprintf(w, sizeof w, "%s: inside the band 2 s after the landing", name);
        eqi(L->count_2s + 17u >= t1 && L->count_2s <= t1 + 17u, 1, w);
    } else {
        snprintf(w, sizeof w, "%s: LATE -- inside the band 4.5 s after the landing", name);
        eqi(L->count_45s + 17u >= t1 && L->count_45s <= t1 + 17u, 1, w);
    }
    snprintf(w, sizeof w, "%s: CONSERVED -- fed %d = played %d + skipped %d + stock %d -> %d", name, (int)L->fed,
             (int)L->played, (int)L->skipped, (int)L->stock0, (int)L->stock1);
    eqi(conserved(L), 1, w);
}

struct rung { uint32_t t, a; };
static const struct rung LADDER[8] = { {704, 4}, {576, 4}, {448, 4}, {320, 4}, {192, 4}, {192, 3}, {192, 2}, {192, 1} };

static void full(const char *what, uint32_t t0, uint32_t a0, uint32_t t1, uint32_t a1, uint32_t mute, uint32_t phase)
{
    char name[160];
    const struct landing L = run(t0, a0, t1, a1, mute, phase, CANDIDATE, 200u);
    snprintf(name, sizeof name, "mute %u: %s T%u A%u -> T%u A%u, phase %u, feed %d/%d", mute, what, t0, a0, t1, a1, phase,
             FEED.kind, FEED.burst_at);
    check_candidate(name, &L, t1, a1, mute, t0 > t1 ? t0 - t1 : 0u, a0 > a1 ? a0 - a1 : 0u);
}

static void test_the_defect_executed(void)
{
    static const uint32_t PAIRS[4][2] = { {4, 3}, {3, 2}, {2, 1}, {4, 1} };
    uint32_t p, ph, f;
    char w[240];
    printf("-- 1. the defect, executed: ROTATE alone lowering AHEAD at TARGET 192 (no surplus drop)\n");
    for (p = 0; p < 4; p++) {
        const uint32_t a0 = PAIRS[p][0], a1 = PAIRS[p][1];
        uint32_t failed_full = 0u, full_n = 0u;
        for (f = 0; f < 4; f++) {
            set_feed(f == 0 ? FEED_SMOOTH : FEED_BURST, f == 0 ? 0 : BURSTS[f - 1], 0u, 0u, 0u, 0u);
            for (ph = 0; ph < 4; ph++) {
                const struct landing L = run(192u, a0, 192u, a1, STEP_MUTE, PHASES[ph], ROTATE_ONLY, POST);
                snprintf(w, sizeof w, "A%u->A%u phase %u feed %u: conservation HOLDS on the defect", a0, a1, PHASES[ph], f);
                eqi(conserved(&L), 1, w);
                if (L.ready_begin == a0) {
                    full_n++;
                    if (!landing_ok(&L, 192u, a1)) failed_full++;
                    if (f == 0 && ph == 2) {
                        printf("   A%u->A%u, half a period in, smooth feed: READY %u at the landing (want %u), "
                               "effective %+d, %u DROPs after it\n", a0, a1, L.ready_after, a1 - 1u,
                               (int)L.effective, L.drops);
                        snprintf(w, sizeof w, "A%u->A%u: READY keeps its old length", a0, a1);
                        eqi(L.ready_after, a0 - 1u, w);
                        snprintf(w, sizeof w, "A%u->A%u: the effective level +128 per chunk lowered", a0, a1);
                        eqi(L.effective >= 128 * (int32_t)(a0 - a1) - (int32_t)GBP_ATRANS_AIM - 2, 1, w);
                        snprintf(w, sizeof w, "A%u->A%u: the band DROPs the surplus after the landing", a0, a1);
                        eqi(L.drops >= 64u, 1, w);
                    }
                }
            }
        }
        snprintf(w, sizeof w, "A%u->A%u: some begins had READY whole (%u)", a0, a1, full_n);
        eqi(full_n > 0u, 1, w);
        snprintf(w, sizeof w, "A%u->A%u: the landing check FAILS at every begin with READY whole (%u of %u)", a0, a1,
                 failed_full, full_n);
        eqi(failed_full, full_n, w);
    }
}

static void test_the_candidate(void)
{
    uint32_t m, r, ph, f, runs = 0u;
    printf("-- 2. the candidate: ROTATE, the surplus dropped when AHEAD falls, full checks\n");
    for (m = STEP_MUTE; m <= STEP_MUTE + 1u; m++) {
        for (f = 0; f < 4; f++) {
            set_feed(f == 0 ? FEED_SMOOTH : FEED_BURST, f == 0 ? 0 : BURSTS[f - 1], 0u, 0u, 0u, 0u);
            for (ph = 0; ph < 4; ph++) {
                for (r = 0; r < 8; r++) {
                    full("refused", LADDER[r].t, LADDER[r].a, LADDER[r].t, LADDER[r].a, m, PHASES[ph]); runs++;
                    if (r + 1u < 8u) {
                        full("down", LADDER[r].t, LADDER[r].a, LADDER[r + 1u].t, LADDER[r + 1u].a, m, PHASES[ph]);
                        full("up", LADDER[r + 1u].t, LADDER[r + 1u].a, LADDER[r].t, LADDER[r].a, m, PHASES[ph]);
                        runs += 2u;
                    }
                }
                for (r = 1; r <= 3; r++) {             /* TARGET steps below AHEAD 4, off the ladder */
                    full("down", 320u, r, 192u, r, m, PHASES[ph]);
                    full("up", 192u, r, 320u, r, m, PHASES[ph]);
                    runs += 2u;
                }
            }
        }
    }
    printf("   %u plans\n", runs);
}

/* THE RULE: the step's audible signature, compared across plans of every kind for the same feed and phase */
struct plan { uint32_t t0, a0, t1, a1; };
static const struct plan PLANS192[13] = {
    {192, 4, 192, 4}, {320, 4, 192, 4}, {192, 4, 320, 4}, {192, 4, 192, 3}, {192, 3, 192, 4}, {192, 1, 192, 1},
    {192, 2, 192, 1}, {192, 1, 192, 2}, {320, 1, 192, 1}, {192, 1, 320, 1}, {704, 4, 576, 4}, {576, 4, 704, 4},
    {704, 4, 704, 4} };
static const struct plan PLANS256[13] = {
    {256, 4, 256, 4}, {384, 4, 256, 4}, {256, 4, 384, 4}, {256, 4, 256, 3}, {256, 3, 256, 4}, {256, 1, 256, 1},
    {256, 2, 256, 1}, {256, 1, 256, 2}, {384, 1, 256, 1}, {256, 1, 384, 1}, {704, 4, 576, 4}, {576, 4, 704, 4},
    {704, 4, 704, 4} };

struct sig { int32_t eff; uint32_t mute; uint8_t late, unmasked, pre; };

/* 1 when every plan's signature equals the first's; counts the shallowings that landed with a splice heard */
static int alike(const struct plan *P, uint32_t mute, uint32_t phase, uint32_t *heard)
{
    uint32_t p;
    struct sig s0, s;
    int same = 1;
    memset(&s0, 0, sizeof s0);
    for (p = 0; p < 13u; p++) {
        const struct landing L = run(P[p].t0, P[p].a0, P[p].t1, P[p].a1, mute, phase, CANDIDATE, SHORT);
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
    uint32_t m, b, sd, ph, groups, differ, heard;
    char w[200];
    printf("-- 3. the rule: one signature for every kind of step, loss-free feeds and small losses\n");
    for (m = STEP_MUTE; m <= STEP_MUTE + 1u; m++) {
        groups = differ = heard = 0u;
        for (ph = 0; ph < 4; ph++) {
            set_feed(FEED_SMOOTH, 0, 0u, 0u, 0u, 0u);
            groups++; differ += (uint32_t)!alike(PLANS192, m, PHASES[ph], &heard);
            for (b = 0; b < PUMPS; b++) {
                set_feed(FEED_BURST, (int)b, 0u, 0u, 0u, 0u);
                groups++; differ += (uint32_t)!alike(PLANS192, m, PHASES[ph], &heard);
            }
            for (sd = 1; sd <= 16u; sd++) {
                set_feed(FEED_MEASURED, 0, sd * 2654435761u, 0u, 0u, 0u);
                groups++; differ += (uint32_t)!alike(PLANS192, m, PHASES[ph], &heard);
            }
        }
        printf("   mute %u: %u of %u loss-free groups differ, %u splices heard\n", m, differ, groups, heard);
        snprintf(w, sizeof w, "mute %u: every loss-free group alike (%u groups)", m, groups);  eqi(differ, 0, w);
        snprintf(w, sizeof w, "mute %u: no splice heard, loss-free", m);                         eqi(heard, 0, w);
    }
}

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
    return differ;                                      /* of 3 x 4 x 6 = 72 groups */
}

static void test_losses(void)
{
    static const uint32_t LOSS[5] = { 16u, 32u, 64u, 100u, 128u };
    uint32_t m, l, d192[2][5], h192[2][5], d256, h256;
    char w[200];
    printf("-- 4. drain losses in the plan's first periods (72 groups each)\n");
    for (m = 0; m < 2; m++) {
        for (l = 0; l < 5; l++) {
            h192[m][l] = 0u;
            d192[m][l] = loss_sweep(PLANS192, STEP_MUTE + m, LOSS[l], &h192[m][l]);
            printf("   anchor 192, mute %u, loss %3u: %2u groups differ, %2u splices heard\n", STEP_MUTE + m, LOSS[l],
                   d192[m][l], h192[m][l]);
        }
    }
    for (l = 0; l < 2; l++)
        for (m = 0; m < 2; m++) {
            snprintf(w, sizeof w, "anchor 192, mute %u, loss %u: every group alike, no splice heard", STEP_MUTE + m, LOSS[l]);
            eqi(d192[m][l] + h192[m][l], 0, w);
        }
    snprintf(w, sizeof w, "anchor 192, mute 5, a D2-class loss (100): a TARGET-down step lands with a splice heard");
    eqi(h192[0][3] > 0u, 1, w);
    for (l = 2; l < 5; l++) {
        snprintf(w, sizeof w, "anchor 192, mute 6, loss %u: no splice heard", LOSS[l]);   eqi(h192[1][l], 0, w);
    }
    snprintf(w, sizeof w, "anchor 192, mute 6, loss 64: some landings differ by rung (192 is 46 over the gate)");
    eqi(d192[1][2] > 0u, 1, w);
    for (l = 0; l < 5; l++) {
        h256 = 0u;
        d256 = loss_sweep(PLANS256, STEP_MUTE + 1u, LOSS[l], &h256);
        printf("   anchor 256, mute 6, loss %3u: %2u groups differ, %2u splices heard\n", LOSS[l], d256, h256);
        snprintf(w, sizeof w, "anchor 256, mute 6, loss %u: every group alike, no splice heard", LOSS[l]);
        eqi(d256 + h256, 0, w);
    }
}

static void test_the_masking_bound(void)
{
    uint32_t a, st, ph, n = 0u, heard = 0u, flagged = 0u, cautious = 0u;
    char w[240];
    printf("-- 5. the masking bound: shallowings with the feed stalled inside the mute\n");
    for (a = 1; a <= 4; a++) {
        for (st = 1; st <= 5; st++) {
            for (ph = 0; ph < 4; ph++) {
                struct landing L;
                set_feed(FEED_SMOOTH, 0, 0u, 0u, 0u, st);
                L = run(320u, a, 192u, a, STEP_MUTE + 1u, PHASES[ph], CANDIDATE, SHORT);
                n++; heard += L.first_audible_pre; flagged += L.unmasked;
                /* never a miss: a splice heard after the silence is always flagged */
                if (L.first_audible_pre) {
                    snprintf(w, sizeof w, "A%u stall %u phase %u: a splice heard is flagged unmasked (%u rotations)",
                             a, st, PHASES[ph], L.rotations);
                    eqi(L.unmasked, 1, w);
                } else if (L.unmasked) {
                    /* cautious: the bound counts AHEAD pre-plan chunks, but a begin before the refill started held
                     * one fewer (READY at AHEAD - 1 and nothing under way), so fewer rotations already cleared them */
                    cautious++;
                    snprintf(w, sizeof w, "A%u stall %u phase %u: a flag with no splice heard only when fewer than "
                             "AHEAD pre-plan chunks were held (READY %u, under way %u)", a, st, PHASES[ph],
                             L.ready_begin, L.under_way_begin);
                    eqi(L.ready_begin + L.under_way_begin < a, 1, w);
                    snprintf(w, sizeof w, "A%u stall %u phase %u: ... and it missed by the one chunk", a, st, PHASES[ph]);
                    eqi(L.rotations + 1u >= L.ready_begin + L.under_way_begin, 1, w);
                }
            }
        }
    }
    set_feed(FEED_SMOOTH, 0, 0u, 0u, 0u, 0u);
    printf("   %u shallowings: %u splices heard, all flagged; %u flagged with none heard (cautious)\n", n, heard, cautious);
    snprintf(w, sizeof w, "the stalls produced splices heard to check (%u)", heard);   eqi(heard > 0u, 1, w);
    (void)flagged;
}

static void test_the_need(void)
{
    uint32_t r, ph;
    char w[200];
    printf("-- 6. the need at a tight mute (pause + AHEAD, AHEAD < 4)\n");
    set_feed(FEED_SMOOTH, 0, 0u, 0u, 0u, 0u);
    for (r = 1; r <= 3; r++) {
        for (ph = 0; ph < 4; ph++) {
            struct landing L = run(192u, r, 320u, r, 1u + r, PHASES[ph], CANDIDATE, SHORT);
            snprintf(w, sizeof w, "up T192 A%u -> T320 A%u at mute %u, phase %u: no fault, that silence", r, r, 1u + r,
                     PHASES[ph]);
            eqi(L.faults == 0u && L.mute_handed == 1u + r, 1, w);
            L = run(192u, r, 192u, r + 1u, 2u + r, PHASES[ph], CANDIDATE, SHORT);
            snprintf(w, sizeof w, "up A%u -> A%u at mute %u, phase %u: no fault, that silence", r, r + 1u, 2u + r,
                     PHASES[ph]);
            eqi(L.faults == 0u && L.mute_handed == 2u + r, 1, w);
        }
    }
}

static void test_starts_along_the_ladder(void)
{
    static const uint32_t STARTS[4][4] = { {704, 4, 192, 1}, {192, 1, 704, 4}, {448, 4, 192, 2}, {192, 2, 448, 4} };
    static const uint32_t MUTES[2] = { 11u, 18u };
    uint32_t s, m, ph, f;
    char w[200];
    printf("-- 7. STARTs along the ladder at mutes 11 and 18\n");
    for (s = 0; s < 4; s++) {
        const uint32_t *x = STARTS[s];
        const uint32_t s0 = x[0] + 128u * x[1], s1 = x[2] + 128u * x[3];
        snprintf(w, sizeof w, "START T%u A%u -> T%u A%u: the need is at most 11", x[0], x[1], x[2], x[3]);
        eqi((s1 > s0 ? (s1 - s0 + 127u) / 128u : 0u) + x[3] <= 11u, 1, w);
        for (m = 0; m < 2; m++)
            for (f = 0; f < 4; f++) {
                set_feed(f == 0 ? FEED_SMOOTH : FEED_BURST, f == 0 ? 0 : BURSTS[f - 1], 0u, 0u, 0u, 0u);
                for (ph = 0; ph < 4; ph++) full("START", x[0], x[1], x[2], x[3], MUTES[m], PHASES[ph]);
            }
    }
}

int main(void)
{
    test_the_defect_executed();
    test_the_candidate();
    test_the_rule();
    test_losses();
    test_the_masking_bound();
    test_the_need();
    test_starts_along_the_ladder();
    gbp_v28_ahead = GBP_APLAY_AHEAD;
    printf("test_v28_ahead_steps: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
