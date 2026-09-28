/*
 * tests/unit/test_gbp_atrans2.c — GitHub Issue #127: gbp_atrans2 (the SAME transition-executor
 * algorithm gbp_atrans.c already has, three review rounds settled it there, #117) against the REAL
 * gbp_aplay2 / gbp_adec2, at this path's own PUSHES (2048) and AHEAD (see gbp_aplay2.h).
 *
 * DELIBERATELY NARROWER than tests/unit/test_gbp_atrans.c's own validation: one representative
 * scenario per mechanism (not the original's 4-phase x bursty-feed sweep), because what changed here
 * is the CONSTANTS and the WIRING to the native decoder, not the transition algorithm itself, which
 * is already proven. Each mechanism's completion, its own bookkeeping and the conservation identity
 * (fed = played + skipped + delta stock) are checked, matching gbp_atrans.c's own invariants in
 * kind. Reference this file's scope explicitly in review: the phase/burst sweep is not reproduced.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_atrans2.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

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

#define CALLS_PER_PERIOD 16u             /* GBP_APLAY2_PUSHES / GBP_APLAY2_STEP_PUSHES: exactly one chunk a period */

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

/* the chain playing steadily at `from`: the ring at the level and READY whole (AHEAD chunks) */
static uint64_t steady2(uint32_t from)
{
    uint64_t now = 0;
    uint32_t i, k;
    memset(&ap, 0, sizeof ap);
    gbp_adec2_init(&adec, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap, pool, silence, keep, events);
    gbp_atrans2_init(&tr);
    gbp_aplay2_set_target(&ap, from);
    give2(&adec, from, 100);
    for (i = 0; i < GBP_APLAY2_AHEAD; i++) prime_period2(&now);
    ap.playing = 1u;
    for (i = 0; i < 6u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(now); now++; }
    }
    return now;
}

static int32_t stock2(void)
{
    /* the in-flight chunk counts what it has TAKEN from the ring (cur_taken), not what it has pushed: a
     * DROP pushes one sample fewer than it takes, a DUP one more. Since Issue #136 the landing's recovery
     * call can see a ring well above target and start its chunk with a DROP, which cur_pushes misses. */
    return (int32_t)(adec.count + GBP_APLAY2_PUSHES * gbp_aplay2_ready(&ap)
                     + (ap.cur >= 0 ? ap.cur_taken : 0u));
}

static uint32_t landed2(void)
{
    return adec.count + (ap.cur >= 0 ? ap.cur_pushes : 0u);
}

struct landing2 {
    int32_t fed, played, skipped, stock0, stock1;
    uint32_t count_after, ready_after, dropped, discarded, mute_handed;
    uint32_t count_end, ready_end;
};

/* begin the plan right after a hand-off (phase 0), feed it smoothly, and land it */
static struct landing2 run2(uint8_t mode, uint32_t from, uint32_t to, uint32_t mute, uint32_t pause,
                           uint32_t discard)
{
    struct landing2 L;
    uint64_t now = steady2(from);
    uint32_t i, k, muted0, dropped0, disc0, handed0, silent0;
    int seen_end = 0, begun = 0;
    memset(&L, 0, sizeof L);
    muted0 = ap.mute_handed; dropped0 = ap.dropped_front; disc0 = adec.discarded;
    for (i = 0; i <= 40u && !seen_end; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) {
            if (begun && !seen_end) L.fed += (int32_t)slice2(k);
            give2(&adec, slice2(k), 100);
            if (i == 0u && k == 0u) {
                L.stock0 = stock2();
                handed0 = ap.handed; silent0 = ap.mute_handed;
                gbp_atrans2_begin(&tr, &ap, &adec, now, mode, mute, pause, discard, to, GBP_APLAY2_AHEAD);
                begun = 1;
            }
            pump2(now);
            if (begun && !seen_end && !tr.active) {
                seen_end = 1;
                L.count_after = landed2();
                L.ready_after = gbp_aplay2_ready(&ap);
                L.dropped = ap.dropped_front - dropped0;
                L.discarded = adec.discarded - disc0;
                L.stock1 = stock2();
                L.played = (int32_t)(GBP_APLAY2_PUSHES * ((ap.handed - handed0) - (ap.mute_handed - silent0)));
                L.skipped = (int32_t)((adec.discarded - disc0)
                                     + GBP_APLAY2_PUSHES * ((ap.dropped_front - dropped0) + ap.discarded_chunks));
            }
            now++;
        }
    }
    L.mute_handed = ap.mute_handed - muted0;
    /* settle for 40 more periods so the band can be observed at rest */
    for (i = 0; i < 40u; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(now); now++; }
    }
    L.count_end = adec.count;
    L.ready_end = gbp_aplay2_ready(&ap);
    return L;
}

static void check_conservation2(const char *name, struct landing2 L)
{
    char w[200];
    snprintf(w, sizeof w, "%s: fed = played + skipped + delta stock", name);
    eqi(L.fed, L.played + L.skipped + (L.stock1 - L.stock0), w);
}

static void test_unmuted(void)
{
    struct landing2 L = run2(GBP_ATRANS2_UNMUTED, GBP_APLAY2_TARGET, GBP_APLAY2_TARGET + 512u, 0u, 0u, 0u);
    eqi(tr.begun, 1, "unmuted: begun");
    eqi(tr.completed, 1, "unmuted: completed at once");
    eqi(tr.mute, 0, "unmuted: no mute");
    eqi(ap.target, GBP_APLAY2_TARGET + 512u, "unmuted: target set at begin");
    check_conservation2("unmuted", L);
}

static void test_unmuted_with_discard(void)
{
    struct landing2 L = run2(GBP_ATRANS2_UNMUTED, GBP_APLAY2_TARGET, GBP_APLAY2_TARGET - 512u, 0u, 0u, 512u);
    eqi(tr.completed, 1, "unmuted+discard: completed at once");
    eqi(L.discarded, 512u, "unmuted+discard: the shallowing discard applied at begin");
    check_conservation2("unmuted+discard", L);
}

static void test_rotate_no_climb(void)
{
    const uint32_t mute = gbp_atrans2_min_mute(GBP_ATRANS2_ROTATE, 0u, GBP_APLAY2_AHEAD);
    struct landing2 L = run2(GBP_ATRANS2_ROTATE, GBP_APLAY2_TARGET, GBP_APLAY2_TARGET, mute, 0u, 0u);
    eqi(tr.completed, 1, "rotate: completed");
    eqi(tr.faults, 0, "rotate: the mute the plan asked for was enough (no fault)");
    check(!tr.unmasked, "rotate: no begin discard, so nothing to unmask");
    check(L.ready_after == GBP_APLAY2_AHEAD - 1u || tr.late, "rotate: queue AHEAD - 1 at the landing, or a late rotation");
    check_conservation2("rotate (no climb)", L);
}

static void test_rotate_with_discard(void)
{
    /* a shallowing: the level drops by one chunk's worth, discarded at begin, masked once AHEAD
     * rotations have happened (AHEAD == 1 on this path, so the very first rotation masks it) */
    const uint32_t mute = gbp_atrans2_min_mute(GBP_ATRANS2_ROTATE, 0u, GBP_APLAY2_AHEAD);
    struct landing2 L = run2(GBP_ATRANS2_ROTATE, GBP_APLAY2_TARGET, GBP_APLAY2_TARGET - GBP_APLAY2_PUSHES, mute, 0u,
                            GBP_APLAY2_PUSHES);
    eqi(tr.completed, 1, "rotate+discard: completed");
    /* the begin's own discard (a shallowing), plus the landing's own ring trim down to target --
     * two separate corrections, both counted in adec.discarded (Issue #129/#130's ROTATE trim) */
    eqi(L.discarded, GBP_APLAY2_PUSHES + tr.trimmed,
        "rotate+discard: the begin's own discard, plus the landing's own ring trim, landed on the ring");
    /* the ring lands exactly at target -- PLUS one sub-block's worth (GBP_APLAY2_STEP_PUSHES) the
     * landing call's own production recovery (Issue #129/#130) already produced towards the NEXT
     * chunk before returning. This is deterministic here, not a range: the recovery runs BEFORE the
     * trim (this round's own fix) against the ring's full, still-untrimmed surplus, which this
     * scenario's own synthetic feed always leaves comfortably above GBP_APLAY2_PUSHES + 1 -- the
     * recovery is a SINGLE gbp_aplay2_produce() call, which advances at most one sub-block
     * (cur_step, GBP_APLAY2_STEP_PUSHES by default) regardless of how much surplus is available, so
     * it always succeeds here and never produces more than exactly one. landed2()'s own count_after
     * already folds in cur_pushes when a chunk is left in flight. */
    eqi(L.count_after, GBP_APLAY2_TARGET - GBP_APLAY2_PUSHES + GBP_APLAY2_STEP_PUSHES,
        "rotate+discard: the ring lands exactly at target, plus the landing recovery's own exactly-one "
        "in-flight sub-block");
    if (tr.rotations >= GBP_APLAY2_AHEAD) check(!tr.unmasked, "rotate+discard: AHEAD rotations mask the splice");
    check_conservation2("rotate+discard", L);
}

static void test_held_no_climb(void)
{
    const uint32_t mute = gbp_atrans2_min_mute(GBP_ATRANS2_HELD, 0u, GBP_APLAY2_AHEAD);
    struct landing2 L = run2(GBP_ATRANS2_HELD, GBP_APLAY2_TARGET, GBP_APLAY2_TARGET, mute, 0u, 0u);
    eqi(tr.completed, 1, "held: completed");
    eqi(tr.faults, 0, "held: the mute the plan asked for was enough");
    check(L.count_after + 1u >= GBP_APLAY2_TARGET && L.count_after <= GBP_APLAY2_TARGET + GBP_APLAY2_PUSHES,
          "held: the ring lands at or above the target (a whole chunk's slack, the level check's own window)");
    check_conservation2("held (no climb)", L);
}

static void test_held_with_climb(void)
{
    const uint32_t pause = 3u;
    const uint32_t mute = gbp_atrans2_min_mute(GBP_ATRANS2_HELD, pause, GBP_APLAY2_AHEAD);
    struct landing2 L = run2(GBP_ATRANS2_HELD, GBP_APLAY2_TARGET, GBP_APLAY2_TARGET + GBP_APLAY2_PUSHES, mute, pause,
                            0u);
    eqi(tr.completed, 1, "held+climb: completed");
    eqi(tr.faults, 0, "held+climb: the mute fit the climb");
    check_conservation2("held+climb", L);
}

/* GitHub Issue #129/#130, Orchestrator review: #117 entry 21 ("a plan applied over a running
 * one") one level down, inside a single phase, for whichever future handler (§V28's 3a
 * bisection, the step sweep) issues more than one plan per phase. The gate lives HERE, in the
 * one place every handler shares, so it need not be duplicated in each one. */
static void test_begin_refuses_a_plan_over_a_running_one(void)
{
    uint64_t now = steady2(GBP_APLAY2_TARGET);
    const uint32_t mute = gbp_atrans2_min_mute(GBP_ATRANS2_ROTATE, 0u, GBP_APLAY2_AHEAD);
    int applied1, applied2;
    uint32_t target0, mute0;
    uint8_t mode0;

    applied1 = gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mute, 0u, 0u, GBP_APLAY2_TARGET + 512u, GBP_APLAY2_AHEAD);
    eqi(applied1, 1, "begin while idle: applied");
    check(tr.active != 0u, "begin while idle: active");
    target0 = tr.target;
    mode0 = tr.mode;
    mute0 = tr.mute;

    applied2 = gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_HELD, mute, 0u, 0u, GBP_APLAY2_TARGET - 512u, GBP_APLAY2_AHEAD);
    eqi(applied2, 0, "begin while active: refused");
    eqi(tr.begin_refused_active, 1, "begin while active: counted");
    eqi(tr.target, target0, "begin while active: the running transition's target is untouched");
    eqi(tr.mode, mode0, "begin while active: the running transition's mode is untouched");
    eqi(tr.mute, mute0, "begin while active: the running transition's mute is untouched");
    check(tr.active != 0u, "begin while active: still active -- the running transition was not cancelled");
}

/* GitHub Issue #129/#130, Orchestrator review: AHEAD is now a runtime field (p->ahead), changed
 * only through gbp_atrans2_begin(), applied inside the mute together with the surplus drop --
 * never a bare setter. These are the mechanism's own direct tests; test_v28_ahead_steps.c's own
 * exhaustive matrix (mutes 5/6, four phases, bursts, D2-class losses, the masking bound) stays
 * the OLD path's probe for now -- porting it onto the native path is its own follow-up, not done
 * here. */

static void pump_until_landed2(uint64_t *now, uint32_t max_periods)
{
    uint32_t i, k;
    for (i = 0; i < max_periods && tr.active; i++) {
        (void)gbp_aplay2_irq_handoff(&ap, *now);
        for (k = 0; k < CALLS_PER_PERIOD; k++) { give2(&adec, slice2(k), 100); pump2(*now); (*now)++; }
    }
}

static void test_ahead_raise_tops_up_the_ready_queue(void)
{
    uint64_t now = steady2(GBP_APLAY2_TARGET);
    const uint32_t new_ahead = 4u;
    const uint32_t mute = gbp_atrans2_min_mute(GBP_ATRANS2_ROTATE, 0u, new_ahead);
    eqi(ap.ahead, 1, "steady2's own chain starts at the compiled-in default (GBP_APLAY2_AHEAD)");
    (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, mute, 0u, 0u, GBP_APLAY2_TARGET, new_ahead);
    eqi(ap.ahead, new_ahead, "ahead changes at begin, immediately -- before the transition even lands");
    pump_until_landed2(&now, 40u);
    check(tr.active == 0u, "the raise lands within the bound");
    eqi(tr.ahead_drops, 0, "a raise never drops anything");
    check(gbp_aplay2_ready(&ap) + 1u >= new_ahead, "ready has topped up toward the new, higher ahead");
}

static void test_ahead_lower_drops_the_surplus_fronts(void)
{
    uint64_t now = steady2(GBP_APLAY2_TARGET);
    const uint32_t raise_mute = gbp_atrans2_min_mute(GBP_ATRANS2_ROTATE, 0u, 4u);
    const uint32_t lower_mute = gbp_atrans2_min_mute(GBP_ATRANS2_ROTATE, 0u, 1u);
    uint32_t dropped0;
    (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, raise_mute, 0u, 0u, GBP_APLAY2_TARGET, 4u);
    pump_until_landed2(&now, 40u);
    check(tr.active == 0u, "the raise lands first, so there is a surplus to drop");
    dropped0 = ap.dropped_front;
    (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, lower_mute, 0u, 0u, GBP_APLAY2_TARGET, 1u);
    eqi(ap.ahead, 1, "ahead changes at begin, immediately, even before the plan lands");
    check(tr.ahead_drops >= 1u, "a lowering step drops at least one surplus front at begin, without replacement");
    eqi((long long)(ap.dropped_front - dropped0), (long long)tr.ahead_drops,
        "gbp_aplay2's own dropped_front agrees with gbp_atrans2's own count");
    pump_until_landed2(&now, 40u);
    check(tr.active == 0u, "the lowering step lands too");
}

static void test_ahead_out_of_bounds_is_clamped_and_counted(void)
{
    uint64_t now = steady2(GBP_APLAY2_TARGET);
    uint32_t faults0 = tr.faults;
    (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_UNMUTED, 0u, 0u, 0u, GBP_APLAY2_TARGET, 0u);
    eqi(ap.ahead, 1, "an ahead of 0 clamps to the floor, 1");
    check(tr.faults > faults0, "counted as a fault, not accepted silently");

    now = steady2(GBP_APLAY2_TARGET);
    faults0 = tr.faults;
    (void)gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_UNMUTED, 0u, 0u, 0u, GBP_APLAY2_TARGET,
                            GBP_APLAY2_POOL + 1u);
    eqi(ap.ahead, GBP_APLAY2_POOL, "an ahead above GBP_APLAY2_POOL clamps to POOL");
    check(tr.faults > faults0, "counted as a fault too");
}

int main(void)
{
    test_unmuted();
    test_unmuted_with_discard();
    test_rotate_no_climb();
    test_rotate_with_discard();
    test_held_no_climb();
    test_held_with_climb();
    test_begin_refuses_a_plan_over_a_running_one();
    test_ahead_raise_tops_up_the_ready_queue();
    test_ahead_lower_drops_the_surplus_fronts();
    test_ahead_out_of_bounds_is_clamped_and_counted();
    printf("test_gbp_atrans2: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
