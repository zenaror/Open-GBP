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

/* GBP_V28_STEP_MUTE (gbp_v28_ladder.h): the mute a step really runs with. The plan's own minimum
 * (gbp_atrans2_min_mute, 1 at AHEAD 1) is a floor for the queue, not for the RING: the level is set in the last two
 * periods and the ring can only have filled for as long as the mute lasted (Issue #136). */
#define STEP_MUTE_6 GBP_V28_STEP_MUTE

static void test_rotate_no_climb(void)
{
    struct landing2 L = run2(GBP_ATRANS2_ROTATE, GBP_APLAY2_TARGET, GBP_APLAY2_TARGET, STEP_MUTE_6, 0u, 0u);
    eqi(tr.completed, 1, "rotate: completed");
    eqi(tr.faults, 0, "rotate: the mute the plan asked for was enough (no fault)");
    check(!tr.unmasked, "rotate: every cut was followed by AHEAD rotations, so nothing is left to unmask");
    check(L.ready_after == GBP_APLAY2_AHEAD - 1u || tr.late, "rotate: queue AHEAD - 1 at the landing, or a late rotation");
    check(tr.disc_rel < 0, "rotate: the level was set BEFORE the first audible hand-off");
    check(tr.rot_post >= GBP_APLAY2_AHEAD, "rotate: at least AHEAD rotations followed the cut");
    check(L.count_after + GBP_APLAY2_BAND >= GBP_APLAY2_TARGET && L.count_after <= GBP_APLAY2_TARGET + GBP_APLAY2_STEP_PUSHES,
          "rotate: the ring lands within the band below target (plus the landing recovery's in-flight sub-block)");
    check_conservation2("rotate (no climb)", L);
}

static void test_rotate_with_discard(void)
{
    /* a shallowing: the level drops by one chunk's worth, discarded at begin */
    struct landing2 L = run2(GBP_ATRANS2_ROTATE, GBP_APLAY2_TARGET, GBP_APLAY2_TARGET - GBP_APLAY2_PUSHES, STEP_MUTE_6,
                            0u, GBP_APLAY2_PUSHES);
    eqi(tr.completed, 1, "rotate+discard: completed");
    /* the begin's own discard, plus the one cut that sets the level inside the mute (Issue #136); nothing is cut
     * at the landing any more */
    eqi(L.discarded, GBP_APLAY2_PUSHES + tr.disc_n,
        "rotate+discard: the begin's own discard, plus the level-setting cut, landed on the ring");
    eqi(tr.trimmed, 0, "rotate+discard: nothing is trimmed at the landing");
    check(L.count_after + GBP_APLAY2_BAND >= GBP_APLAY2_TARGET - GBP_APLAY2_PUSHES &&
          L.count_after <= GBP_APLAY2_TARGET - GBP_APLAY2_PUSHES + GBP_APLAY2_STEP_PUSHES,
          "rotate+discard: the ring lands within the band below target (plus the landing recovery's in-flight sub-block)");
    check(!tr.unmasked, "rotate+discard: AHEAD rotations followed every cut");
    check_conservation2("rotate+discard", L);
}

/* Issue #136: a mute too short to FILL the ring is reported, never hidden, and never turned into a cut: the
 * ring lands short, `fill_short` says by how much, and nothing was discarded (so no splice either). */
static void test_a_mute_too_short_to_fill_the_ring_is_reported_and_cuts_nothing(void)
{
    struct landing2 L = run2(GBP_ATRANS2_ROTATE, GBP_APLAY2_TARGET, GBP_APLAY2_TARGET + 6u * GBP_APLAY2_PUSHES, 3u, 0u, 0u);
    eqi(tr.completed, 1, "short mute: completed");
    check(tr.fill_short > 0u, "short mute: the samples the ring lacked at the level-setting point are reported");
    eqi(tr.fill_shorts, 1, "short mute: counted once");
    eqi(tr.disc_n, 0, "short mute: nothing was cut");
    eqi(tr.trimmed, 0, "short mute: nothing was trimmed either");
    check(L.count_after + GBP_APLAY2_BAND < GBP_APLAY2_TARGET + 6u * GBP_APLAY2_PUSHES,
          "short mute: the ring lands short of target -- the honest result the sweep gate then shows");
}

/* Issue #136: `unmasked` means a cut was made AND a chunk built before it is still queued at the landing. The landing
 * branch is driven directly with that state (a real run cannot leave an old chunk: it is freed by the builds), once with a
 * cut and once without. */
static void land_with(uint32_t cut, uint32_t old_left)
{
    int b;
    uint64_t now = steady2(GBP_APLAY2_TARGET);
    gbp_atrans2_begin(&tr, &ap, &adec, now, GBP_ATRANS2_ROTATE, STEP_MUTE_6, 0u, 0u, GBP_APLAY2_TARGET, GBP_APLAY2_AHEAD);
    tr.adjusted = 1u;
    tr.disc_n = cut;
    tr.old_chunks = old_left;
    tr.to_build = 0u;
    ap.handed = tr.handed_at_start + tr.mute + 1u;          /* past the first audible hand-off: the landing */
    (void)gbp_atrans2_step(&tr, &ap, &adec, now, &b);
}

static void test_unmasked_means_a_cut_with_an_old_chunk_still_queued(void)
{
    land_with(100u, 1u);
    eqi(tr.completed, 1, "unmasked: the landing branch ran");
    eqi(tr.unmasked, 1, "a cut and an old chunk still queued: unmasked");
    land_with(100u, 0u);
    eqi(tr.unmasked, 0, "a cut and every old chunk replaced: not unmasked");
    land_with(0u, 1u);
    eqi(tr.unmasked, 0, "no cut, so no discontinuity to hear: not unmasked");
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
    test_a_mute_too_short_to_fill_the_ring_is_reported_and_cuts_nothing();
    test_unmasked_means_a_cut_with_an_old_chunk_still_queued();
    test_held_no_climb();
    test_held_with_climb();
    test_begin_refuses_a_plan_over_a_running_one();
    test_ahead_raise_tops_up_the_ready_queue();
    test_ahead_lower_drops_the_surplus_fronts();
    test_ahead_out_of_bounds_is_clamped_and_counted();
    printf("test_gbp_atrans2: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
