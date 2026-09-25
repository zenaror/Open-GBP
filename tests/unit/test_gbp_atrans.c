/*
 * tests/unit/test_gbp_atrans.c — the latency round's transition executor against the
 * REAL gbp_aplay / gbp_adec, with a simulated AI (GitHub Issue #117, §V27.13-§V27.15).
 *
 * The model: one AI hand-off per period (gbp_aplay_irq_handoff), PUMPS pump calls per
 * period, and the cartridge delivering 128 decoded samples per period spread evenly
 * over the pump calls -- the drain's 4096/s against the AI's 4096/s, no deficit, so
 * that what the executor does is the only thing that moves the fill. A plan is begun
 * at a chosen PHASE: pump call k of a period, for k = 0 (right after a hand-off, the
 * refill still under way), a quarter, a half, and the last call (right before the
 * next hand-off). Every mechanism is checked at every phase:
 *   ROTATE   (Phase 1's switches, Phase 2's STARTs) MASKED: every chunk in READY at
 *            the landing was started after the plan, and nothing leaves the ring's
 *            head after the begin's discard -- so all that is skipped lies between the
 *            pause and READY's first sample, inside the silence; the residue within
 *            the aim, the band settling it, no fault, no late rotation;
 *   HELD     (Phase 2's STEPs) the ring lands EXACTLY at the level on the first
 *            audible hand-off, no correction afterwards, the trim bounded;
 *   UNMUTED  (Phase 3's depths) the target set, the discard done at begin, done at
 *            once, no silence.
 * The reviews before the commit found the executor ending one discard short (the ring
 * 128 above the level, ~113 DROPs); the phase sweep found a chunk left over (discards
 * counted per hand-off), the held queue's refill discarded (a chunk low after the
 * mute) and a late refill DROPping; and §V27.15 found the held queue's splice audible
 * 125 ms after the silence. All are pinned here.
 *
 * On hardware the feed is bursty (whole AUDIO blocks per service cycle) and runs
 * 10.9 samples/s under the AI's consumption, so the landing is exact to the feed's
 * burst, not to the sample; this harness's smooth feed isolates the executor.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_atrans.h"
#include "gbp_async.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

static uint8_t pool[GBP_APLAY_POOL * GBP_APLAY_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY_CHUNK_BYTES];
static int16_t ring[GBP_APLAY_RING];
static struct gbp_aplay ap;
static struct gbp_adec adec;
static struct gbp_atrans tr;

#define PUMPS 110u                      /* pump calls per AI period, as gbp_aplay.h states (>= 110) */
#define MUTE  18u                       /* §V27.15 */

static void give(struct gbp_adec *d, uint32_t n, int16_t v)
{
    uint32_t k;
    for (k = 0; k < n && d->count < d->cap; k++) {
        d->ring[(d->head + d->count) % d->cap] = v;
        d->count++;
    }
}

static uint32_t slice(uint32_t k)
{
    return (k + 1u) * 128u / PUMPS - k * 128u / PUMPS;
}

/* the feed during a plan: smooth (slices), or -- as on hardware, whole AUDIO blocks per service cycle -- one
 * burst of 128 at pump call `burst_at` of every period (review round 3: the smooth, phase-locked feed can
 * never make a rotation late) */
static int burst_at = -1;
static int feed_off = 0;                /* no feed at all during the plan: a drain that stopped */
static uint32_t feed_at(uint32_t k)
{
    if (feed_off) return 0u;
    return burst_at < 0 ? slice(k) : ((int)k == burst_at ? 128u : 0u);
}

/* the POC's shape: one produce site, one queue site; the executor hands back what it produced */
static void pump(uint64_t now)
{
    int b;
    if (tr.active) (void)gbp_atrans_step(&tr, &ap, &adec, now, &b);
    else b = gbp_aplay_produce(&ap, &adec);
    if (b >= 0) gbp_aplay_queue(&ap, b);
    gbp_aplay_process(&ap);
}

/* a period with no hand-off: the feed arrives and the producer adds ONE chunk to the queue from it
 * (a second chunk would start low in the ring and take a DUP) */
static void prime_period(uint64_t *now)
{
    uint32_t k;
    int done = 0;
    for (k = 0; k < PUMPS; k++) {
        give(&adec, slice(k), 100);
        if (!done) {
            int b = gbp_aplay_produce(&ap, &adec);
            if (b >= 0) { gbp_aplay_queue(&ap, b); done = 1; }
        }
        gbp_aplay_process(&ap);
        (*now)++;
    }
}

/* the chain playing steadily at `from`: the ring at the level and READY whole (4 chunks), every
 * chunk started with the ring AT the level so no correction ever fired */
static uint64_t steady(uint32_t from)
{
    uint64_t now = 0;
    uint32_t i, k;
    memset(&ap, 0, sizeof ap);
    gbp_adec_init(&adec, ring, GBP_APLAY_RING);
    gbp_aplay_init(&ap, pool, silence, NULL, NULL);
    gbp_atrans_init(&tr);
    gbp_aplay_set_target(&ap, from);
    give(&adec, from, 100);
    for (i = 0; i < GBP_APLAY_AHEAD; i++) prime_period(&now);
    ap.playing = 1u;
    for (i = 0; i < 40; i++) {
        (void)gbp_aplay_irq_handoff(&ap, now);
        for (k = 0; k < PUMPS; k++) { give(&adec, slice(k), 100); pump(now); now++; }
    }
    return now;
}

struct landing {
    uint32_t count_after;       /* the level the landing left: the ring plus a chunk under way's taken pushes */
    uint32_t ready_after;
    uint32_t fresh_after;       /* ROTATE: READY chunks at the landing that were STARTED after the plan began */
    uint32_t drops, dups;       /* corrections from the landing to 160 periods on */
    uint32_t mute_handed, dropped, discarded, begin_discard_extra;
    uint32_t count_end, ready_end;
    /* CONSERVATION, from the plan's begin to its landing: fed = played + skipped + (stock after - stock
     * before), stock = the ring + READY x 128 + a chunk under way's taken pushes */
    int32_t fed, played, skipped, stock0, stock1;
    uint32_t count_2s;          /* the ring 64 periods (2 s, the settling window) after the landing, at a chunk start */
    uint32_t count_45s;         /* ... and 144 periods (4.5 s) after it */
    int32_t effective;          /* the ring + a chunk under way + READY beyond AHEAD - 1, minus the target, at the landing */
};

static void check_conservation(const char *name, struct landing L);

static int32_t stock(void)
{
    return (int32_t)(adec.count + 128u * gbp_aplay_ready(&ap) + (ap.cur >= 0 ? ap.cur_pushes : 0u));
}

static uint32_t landed(void)
{
    return adec.count + (ap.cur >= 0 ? ap.cur_pushes : 0u);
}

/* chunks in READY started after the plan began: seq[] is the produced count at a chunk's START, so a
 * chunk started after begin has seq >= produced_at_begin, plus one when a chunk was under way then */
static uint32_t fresh_in_ready(uint32_t first_fresh_seq)
{
    uint32_t h, n = 0u;
    for (h = ap.rq_head; h != ap.rq_tail; h++)
        if (ap.seq[ap.rq[h % GBP_APLAY_POOL]] >= first_fresh_seq) n++;
    return n;
}

/* begin the plan at pump call `phase` of a period (0 = right after the hand-off), then 160 periods */
static struct landing run(uint8_t mode, uint32_t from, uint32_t to, uint32_t mute, uint32_t pause, uint32_t discard,
                          uint32_t phase)
{
    struct landing L;
    uint64_t now = steady(from);
    uint32_t i, k, drop0 = 0u, dup0 = 0u, muted0, dropped0, disc0, first_fresh = 0u, i_end = 0u;
    uint32_t handed0 = 0u, silent0 = 0u, discchunks0 = 0u;
    int seen_end = 0, begun = 0;
    memset(&L, 0, sizeof L);
    eqi(adec.count, from, "steady at the level before the plan");
    eqi(gbp_aplay_ready(&ap), GBP_APLAY_AHEAD, "READY whole before the plan");
    muted0 = ap.mute_handed; dropped0 = ap.dropped_front; disc0 = adec.discarded;
    for (i = 0; i <= 200u; i++) {
        (void)gbp_aplay_irq_handoff(&ap, now);
        for (k = 0; k < PUMPS; k++) {
            if (begun && !seen_end) L.fed += (int32_t)feed_at(k);
            give(&adec, feed_at(k), 100);
            if (i == 0u && k == phase) {
                first_fresh = ap.produced + (ap.cur >= 0 ? 1u : 0u);
                L.stock0 = stock();
                handed0 = ap.handed; silent0 = ap.mute_handed; discchunks0 = ap.discarded_chunks;
                gbp_atrans_begin(&tr, &ap, &adec, now, mode, mute, pause, discard, to);
                L.begin_discard_extra = adec.discarded - disc0;       /* the begin's own discard */
                begun = 1;
            }
            pump(now);
            if ((i > 0u || k >= phase) && !seen_end && !tr.active) {
                seen_end = 1;
                i_end = i;
                L.count_after = landed();
                L.ready_after = gbp_aplay_ready(&ap);
                L.fresh_after = fresh_in_ready(first_fresh);
                L.dropped = ap.dropped_front - dropped0;
                L.discarded = adec.discarded - disc0;
                L.stock1 = stock();
                L.effective = (int32_t)landed() + 128 * ((int32_t)gbp_aplay_ready(&ap) - (int32_t)(GBP_APLAY_AHEAD - 1u))
                            - (int32_t)to;
                L.played = (int32_t)(128u * ((ap.handed - handed0) - (ap.mute_handed - silent0)));
                L.skipped = (int32_t)((adec.discarded - disc0) + 128u * ((ap.dropped_front - dropped0) +
                                                                          (ap.discarded_chunks - discchunks0)));
                drop0 = ap.drop; dup0 = ap.dup;
            }
            if (seen_end && i == i_end + 64u && k == 1u) L.count_2s = adec.count;   /* a chunk starts here */
            if (seen_end && i == i_end + 144u && k == 1u) L.count_45s = adec.count;
            now++;
        }
    }
    L.drops = ap.drop - drop0; L.dups = ap.dup - dup0;
    L.mute_handed = ap.mute_handed - muted0;
    L.count_end = adec.count; L.ready_end = gbp_aplay_ready(&ap);
    return L;
}

static const uint32_t PHASES[4] = { 0u, PUMPS / 4u, PUMPS / 2u, PUMPS - 1u };

static void check_rotate(const char *name, struct landing L, uint32_t to, uint32_t mute, uint32_t discard)
{
    char w[220];
    const int32_t res = (int32_t)L.count_after - (int32_t)to;
    snprintf(w, sizeof w, "%s: MASKED -- every READY chunk at the landing started after the plan", name);
    eqi(L.fresh_after, L.ready_after, w);
    snprintf(w, sizeof w, "%s: nothing left the ring's head after the begin's discard", name);
    eqi(L.discarded, discard, w);
    snprintf(w, sizeof w, "%s: not flagged unmasked, no fault", name);
    eqi(!tr.unmasked && tr.faults == 0u, 1, w);
    if (discard) {
        snprintf(w, sizeof w, "%s: a shallowing rotated AHEAD fronts out (its pre-splice chunks gone)", name);
        eqi(tr.rotations >= GBP_APLAY_AHEAD, 1, w);
    }
    snprintf(w, sizeof w, "%s: the executor's residue is the effective level", name);   eqi(tr.residue, L.effective, w);
    if (!tr.late) {
        snprintf(w, sizeof w, "%s: the residue within the aim (and a feed slice)", name);
        eqi(res >= -(int32_t)GBP_ATRANS_AIM - 2 && res <= (int32_t)GBP_ATRANS_AIM + 2, 1, w);
        if (!(res >= -(int32_t)GBP_ATRANS_AIM - 2 && res <= (int32_t)GBP_ATRANS_AIM + 2)) printf("    (residue %d)\n", (int)res);
        snprintf(w, sizeof w, "%s: the effective level is the ring's", name);   eqi(L.effective, res, w);
        snprintf(w, sizeof w, "%s: on the first audible hand-off (queue AHEAD - 1)", name);
        eqi(L.ready_after, GBP_APLAY_AHEAD - 1u, w);
    } else {
        /* a late rotation: queued undropped, READY one chunk long, the level one chunk up */
        snprintf(w, sizeof w, "%s: LATE -- READY one chunk long at the landing", name);  eqi(L.ready_after, GBP_APLAY_AHEAD, w);
        snprintf(w, sizeof w, "%s: LATE -- the effective level one chunk over the ring's", name);
        eqi(L.effective - res, (int32_t)GBP_APLAY_PUSHES, w);
    }
    snprintf(w, sizeof w, "%s: the band corrects only what lies outside it", name);
    eqi(L.drops + L.dups <= (uint32_t)(L.effective < 0 ? -L.effective : L.effective), 1, w);
    snprintf(w, sizeof w, "%s: settled inside the band 160 periods on", name);
    eqi(L.count_end + 17u >= to && L.count_end <= to + 16u, 1, w);
    snprintf(w, sizeof w, "%s: READY whole 160 periods on", name);            eqi(L.ready_end, GBP_APLAY_AHEAD, w);
    snprintf(w, sizeof w, "%s: silence handed for the mute", name);           eqi(L.mute_handed, mute, w);
    snprintf(w, sizeof w, "%s: the dropped fronts are the rotations", name);  eqi(L.dropped, tr.rotations, w);
    check_conservation(name, L);
    /* M1 reads settled seconds only: none overlapping the mute or the 2 s after it. The landing is at most
     * one hand-off after the module's mute end, and the band corrects what the residue leaves outside it
     * (at most 64 - 16 = 48 samples) at one sample a chunk, 32 a second: inside the band within 1.5 s */
    if (!tr.late) {
        snprintf(w, sizeof w, "%s: inside the band 2 s after the landing, before M1's first settled second", name);
        eqi(L.count_2s + 17u >= to && L.count_2s <= to + 17u, 1, w);
    } else {
        /* a late landing's extra chunk is DROPped at one sample a chunk: past the 2 s settling, inside 4.5 s */
        snprintf(w, sizeof w, "%s: LATE -- inside the band 4.5 s after the landing", name);
        eqi(L.count_45s + 17u >= to && L.count_45s <= to + 17u, 1, w);
    }
}

/* the fed samples are played, skipped, or still in stock: nothing is created or lost by a transition */
static void check_conservation(const char *name, struct landing L)
{
    char w[220];
    snprintf(w, sizeof w, "%s: CONSERVED -- fed %d = played %d + skipped %d + stock %d -> %d", name, (int)L.fed,
             (int)L.played, (int)L.skipped, (int)L.stock0, (int)L.stock1);
    eqi(L.fed, L.played + L.skipped + (L.stock1 - L.stock0), w);
}

static void check_held(const char *name, struct landing L, uint32_t to, uint32_t mute)
{
    char w[220];
    check_conservation(name, L);
    snprintf(w, sizeof w, "%s: the ring lands at the level", name);          eqi(L.count_after, to, w);
    snprintf(w, sizeof w, "%s: on the first audible hand-off (queue AHEAD - 1)", name); eqi(L.ready_after, GBP_APLAY_AHEAD - 1u, w);
    snprintf(w, sizeof w, "%s: no DROP after the landing", name);             eqi(L.drops, 0, w);
    snprintf(w, sizeof w, "%s: no DUP after the landing", name);              eqi(L.dups, 0, w);
    /* the level is where a chunk STARTS (gbp_aplay decides there); at a period's end the ring sits one
     * feed slice under it, since the landing drops the slice that came with the audible hand-off */
    snprintf(w, sizeof w, "%s: at the level 160 periods on (to a feed slice)", name);
    eqi(L.count_end + 1u >= to && L.count_end <= to, 1, w);
    snprintf(w, sizeof w, "%s: READY whole 160 periods on", name);            eqi(L.ready_end, GBP_APLAY_AHEAD, w);
    snprintf(w, sizeof w, "%s: silence handed for the mute", name);           eqi(L.mute_handed, mute, w);
    snprintf(w, sizeof w, "%s: no front dropped (HELD keeps its queue)", name); eqi(L.dropped, 0, w);
    /* the trim: under a chunk and a feed slice, or one chunk more when the landing converted a discard
     * under way (it began only at a whole chunk above the level, and its taken samples are now played) */
    snprintf(w, sizeof w, "%s: the trim is bounded (a chunk more if a discard was converted)", name);
    eqi(tr.converted ? (tr.trimmed >= GBP_APLAY_PUSHES && tr.trimmed < 2u * GBP_APLAY_PUSHES)
                     : (tr.trimmed < GBP_APLAY_PUSHES + 2u), 1, w);
    snprintf(w, sizeof w, "%s: never short, no fault", name);                 eqi(tr.shorts + tr.faults, 0, w);
}

static void test_rotate_masks_at_every_phase(void)
{
    struct landing L;
    char name[120];
    uint32_t i;
    for (i = 0; i < 4u; i++) {
        const uint32_t ph = PHASES[i];
#define R(label, from, to, mute, pause, discard) \
        do { snprintf(name, sizeof name, "ROTATE %s at phase %u/%u", label, ph, PUMPS); \
             L = run(GBP_ATRANS_ROTATE, from, to, mute, pause, discard, ph); check_rotate(name, L, to, mute, discard); } while (0)
        /* Phase 1, MUTE 18 */
        R("512 -> 2048", 512, 2048, MUTE, 12, 0);
        R("2048 -> 512", 2048, 512, MUTE, 0, 1536);
        R("NULL at 2048", 2048, 2048, MUTE, 0, 0);
        R("NULL at 512", 512, 512, MUTE, 0, 0);
        /* the bound itself: 512 -> 2048 at mute = pause + 4 = 16, §V27.15's zero margin, still masked here */
        R("512 -> 2048 at the bound (mute 16)", 512, 2048, 16, 12, 0);
        /* Phase 2's STARTs: max(MUTE, pause + 4) */
        R("START 512 -> 3584 (mute 28)", 512, 3584, 28, 24, 0);
        R("START 384 -> 3584 (mute 29)", 384, 3584, 29, 25, 0);
        R("START 512 -> 2560 (mute 20)", 512, 2560, 20, 16, 0);
        R("START 2048 -> 2560", 2048, 2560, MUTE, 4, 0);
        R("START 3584 -> 384", 3584, 384, MUTE, 0, 3200);
#undef R
    }
}

/* §V27.15's INVARIANT, asserted rather than observed: at the same phase the feed under the same silence is
 * the same, so the skips differ by exactly the latency they change, less the residues' difference.
 * (skip + residue) of the null minus that of the deepening = 1 536 = (shallow) minus (null): conservation --
 * content that stops being delayed by 0.375 s has to go somewhere. A transition that ever broke it would be
 * a defect, and this is the cheapest place to catch one. */
static void test_the_skip_difference_is_the_latency_difference(void)
{
    uint32_t i;
    for (i = 0; i < 4u; i++) {
        struct landing D, N, S;
        int32_t d, n, sh;
        char w[160];
        D = run(GBP_ATRANS_ROTATE, 512, 2048, MUTE, 12, 0, PHASES[i]);    d = D.skipped + ((int32_t)D.count_after - 2048);
        N = run(GBP_ATRANS_ROTATE, 2048, 2048, MUTE, 0, 0, PHASES[i]);    n = N.skipped + ((int32_t)N.count_after - 2048);
        S = run(GBP_ATRANS_ROTATE, 2048, 512, MUTE, 0, 1536, PHASES[i]);  sh = S.skipped + ((int32_t)S.count_after - 512);
        snprintf(w, sizeof w, "phase %u: null - deepen = 1536 (skip + residue), got %d", PHASES[i], (int)(n - d));
        eqi(n - d, 1536, w);
        snprintf(w, sizeof w, "phase %u: shallow - null = 1536 (skip + residue), got %d", PHASES[i], (int)(sh - n));
        eqi(sh - n, 1536, w);
    }
}

/* §V27.13's arithmetic at MUTE 18 (§V27.15): the skip -- the begin's discard plus the dropped fronts --
 * is mute x 128 - delta for a deepening, mute x 128 for a null, mute x 128 + delta for a shallowing, each
 * to within the residue; the null sits at the midpoint of the two real sizes */
static void test_the_skip_sizes(void)
{
    struct landing L;
    int32_t deepen, null, shallow;
    L = run(GBP_ATRANS_ROTATE, 512, 2048, MUTE, 12, 0, PUMPS / 2u);
    deepen = (int32_t)(L.begin_discard_extra + L.dropped * GBP_APLAY_PUSHES);
    L = run(GBP_ATRANS_ROTATE, 2048, 2048, MUTE, 0, 0, PUMPS / 2u);
    null = (int32_t)(L.begin_discard_extra + L.dropped * GBP_APLAY_PUSHES);
    L = run(GBP_ATRANS_ROTATE, 2048, 512, MUTE, 0, 1536, PUMPS / 2u);
    shallow = (int32_t)(L.begin_discard_extra + L.dropped * GBP_APLAY_PUSHES);
    printf("    skips at MUTE 18: deepen %d, null %d, shallow %d samples\n", (int)deepen, (int)null, (int)shallow);
    eqi(deepen >= 768 - 128 && deepen <= 768 + 128, 1, "deepen ~ 18 x 128 - 1536 = 768 (0.1875 s)");
    eqi(null >= 2304 - 128 && null <= 2304 + 128, 1, "null ~ 18 x 128 = 2304 (0.5625 s)");
    eqi(shallow >= 3840 - 128 && shallow <= 3840 + 128, 1, "shallow ~ 18 x 128 + 1536 = 3840 (0.9375 s)");
    eqi(2 * null - deepen - shallow >= -128 && 2 * null - deepen - shallow <= 128, 1, "the null at the midpoint");
}

/* the hardware's feed: one burst per period at an offset; the offsets near a period's end make the last
 * rotation of the one-silent-hand-off window late (review round 3 measured 5-19 % late on hardware) */
static void test_rotate_under_a_bursty_feed(void)
{
    static const int bursts[5] = { 3, 30, 60, 100, (int)PUMPS - 4 };
    struct landing L;
    char name[140];
    uint32_t i, b, lates = 0u;
    for (b = 0; b < 5u; b++) {
        burst_at = bursts[b];
        for (i = 0; i < 4u; i++) {
            const uint32_t ph = PHASES[i];
#define RB(label, from, to, mute, pause, discard)             do { snprintf(name, sizeof name, "ROTATE %s, burst at %d, phase %u", label, burst_at, ph);                  L = run(GBP_ATRANS_ROTATE, from, to, mute, pause, discard, ph); check_rotate(name, L, to, mute, discard);                  lates += tr.late; } while (0)
            RB("512 -> 2048", 512, 2048, MUTE, 12, 0);
            RB("2048 -> 512", 2048, 512, MUTE, 0, 1536);
            RB("NULL at 2048", 2048, 2048, MUTE, 0, 0);
            RB("START 384 -> 3584 (mute 29)", 384, 3584, 29, 25, 0);
#undef RB
        }
    }
    burst_at = -1;
    printf("    bursty sweep: %u late landings of 80, each masked and conserved\n", (unsigned)lates);
    eqi(lates > 0u, 1, "the sweep reaches the late case (a burst near the period's end)");
}

/* `unmasked` means a shallowing's pre-splice chunk may still be in READY: fewer than AHEAD fronts gone since
 * its begin discard. A deepening or a null is contiguous whatever the rotations */
static void test_unmasked_only_where_a_splice_can_remain(void)
{
    struct landing L;
    /* no feed under the silence (a real plan always rotates enough; the guard is what is tested): nothing can
     * rotate, so the held chunks all stay in READY */
    feed_off = 1;
    L = run(GBP_ATRANS_ROTATE, 2048, 1920, 4, 0, 128, PUMPS / 2u);    /* a shallowing */
    eqi(tr.rotations < GBP_APLAY_AHEAD, 1, "a shallowing with fewer than AHEAD rotations");
    eqi(tr.unmasked, 1, "is flagged unmasked: its splice is behind the held chunks");
    eqi(L.fresh_after < L.ready_after, 1, "and a pre-plan chunk is indeed still in READY");
    check_conservation("the unfed shallowing", L);
    L = run(GBP_ATRANS_ROTATE, 2048, 2048, 4, 0, 0, PUMPS / 2u);      /* a null: the same, with no discard */
    eqi(tr.rotations < GBP_APLAY_AHEAD, 1, "a null with fewer than AHEAD rotations");
    eqi(tr.unmasked, 0, "is not flagged: READY and the ring are contiguous");
    eqi(L.skipped, (int32_t)(128u * tr.rotations), "its skip is the dropped fronts, right after the pause");
    check_conservation("the unfed null", L);
    feed_off = 0;
}

/* Review round 3: gbp_async's mute ends at the plan's instant + mute chunks, the executor lands on the first
 * AUDIBLE hand-off, up to one period later. A phase ended inside a switch's mute (Z, a cap, the 18th answer)
 * made the module's next tick begin Phase 2's START over the running switch, and the switch's record was lost.
 * main.c holds the tick while the executor runs; this drives the real gbp_async and gbp_atrans in main.c's
 * order (tick -> apply -> step), with and without that hold, at every phase of the switch against the
 * hand-offs. The module's time is the pump call: tb_hz 3 520 makes a chunk one period of PUMPS calls. */
static uint32_t drive_z_in_the_mute(uint32_t phase, int hold, uint32_t *completed_at_start)
{
    struct gbp_async a;
    struct gbp_async_cfg c = gbp_async_cfg_default;
    uint64_t now = steady(2048);
    uint32_t i, k, preempts = 0u;
    int switched = 0, zed = 0;
    c.tb_hz = 3520u;
    gbp_async_init(&a, &c);
    gbp_async_start(&a, now, 0x1234u);
    a.target = 2048u; ap.target = 2048u;
    *completed_at_start = 0xFFFFFFFFu;
    for (i = 0; i < 60u; i++) {
        (void)gbp_aplay_irq_handoff(&ap, now);
        for (k = 0; k < PUMPS; k++) {
            int r, b;
            give(&adec, slice(k), 100);
            if (!switched && i == 2u && k == phase) {       /* the first switch: a REAL, rotated */
                switched = 1;
                if (gbp_async_switch(&a, now))
                    gbp_atrans_begin(&tr, &ap, &adec, now, a.plan.mech, a.plan.mute_chunks, a.plan.pause_chunks,
                                     a.plan.discard, a.plan.to);
            }
            if (switched && !zed && i == 12u) { zed = 1; gbp_async_skip(&a, now); }   /* Z inside the 18-chunk mute */
            r = (hold && tr.active) ? 0 : gbp_async_tick(&a, now);
            if (r & GBP_ASYNC_TICK_PLAN) {
                if (tr.active) preempts++;
                if (a.plan.kind == GBP_ASYNC_KIND_START && *completed_at_start == 0xFFFFFFFFu) *completed_at_start = tr.completed;
                gbp_atrans_begin(&tr, &ap, &adec, now, a.plan.mech, a.plan.mute_chunks, a.plan.pause_chunks,
                                 a.plan.discard, a.plan.to);
            }
            if (tr.active) (void)gbp_atrans_step(&tr, &ap, &adec, now, &b);
            else b = gbp_aplay_produce(&ap, &adec);
            if (b >= 0) gbp_aplay_queue(&ap, b);
            gbp_aplay_process(&ap);
            now++;
        }
    }
    return preempts;
}

static void test_the_module_waits_for_the_executor(void)
{
    uint32_t i, done, pre_old = 0u;
    char w[140];
    for (i = 0; i < 4u; i++) {
        pre_old += drive_z_in_the_mute(PHASES[i], 0, &done);
        snprintf(w, sizeof w, "phase %u: held, the START is applied over nothing", PHASES[i]);
        eqi(drive_z_in_the_mute(PHASES[i], 1, &done), 0, w);
        snprintf(w, sizeof w, "phase %u: held, the switch had landed when the START began", PHASES[i]);
        eqi(done, 1, w);
    }
    printf("    without the hold: %u of 4 phases preempted the running switch\n", (unsigned)pre_old);
    eqi(pre_old >= 3u, 1, "without the hold the START is applied over the running switch (the finding)");
}

static void test_held_lands_exactly_at_every_phase(void)
{
    struct landing L;
    char name[120];
    uint32_t i;
    for (i = 0; i < 4u; i++) {
        const uint32_t ph = PHASES[i];
#define H(label, from, to, mute, pause, discard) \
        do { snprintf(name, sizeof name, "HELD %s at phase %u/%u", label, ph, PUMPS); \
             L = run(GBP_ATRANS_HELD, from, to, mute, pause, discard, ph); check_held(name, L, to, mute); } while (0)
        H("STEP +128", 1024, 1152, 4, 1, 0);
        H("STEP -128", 1152, 1024, 4, 0, 128);
        H("STEP +128 from 3584 (under the cap)", 3584, 3712, 4, 1, 0);
        H("STEP -128 to 384", 512, 384, 4, 0, 128);
#undef H
    }
}

/* Phase 3 depths (mute 0): the executor's whole contract is to set the target, apply a shallowing
 * discard at begin, hand NO silence, and complete AT ONCE without pausing the producer -- where the
 * ring then settles is gbp_aplay's band, which is what the dwell measures and NOT the executor's to
 * force (near the floor the ring oscillates, by design) */
static void test_unmuted_sets_the_target_and_does_not_chase(void)
{
    uint32_t i, c, k;
    static const struct { const char *name; uint32_t from, to, pause, discard; } cases[] = {
        {"384 -> 352 (shallow)", 384, 352, 0, 32}, {"160 -> 128 (shallow)", 160, 128, 0, 32},
        {"128 -> 144 (deepen 16)", 128, 144, 1, 0}, {"144 -> 152 (deepen 8)", 144, 152, 1, 0},
    };
    for (i = 0; i < 4u; i++) {
        for (c = 0; c < 4u; c++) {
            uint32_t disc0;
            uint64_t now = steady(cases[c].from);
            char w[160];
            disc0 = adec.discarded;
            gbp_atrans_begin(&tr, &ap, &adec, now, GBP_ATRANS_UNMUTED, 16u, cases[c].pause, cases[c].discard, cases[c].to);
            snprintf(w, sizeof w, "UNMUTED %s: the discard is done at begin", cases[c].name);
            eqi(adec.discarded - disc0, cases[c].discard, w);
            snprintf(w, sizeof w, "UNMUTED %s: a mute asked for is ignored", cases[c].name); eqi(tr.mute, 0, w);
            (void)gbp_aplay_irq_handoff(&ap, now);
            for (k = 0; k < PUMPS; k++) { give(&adec, slice(k), 100); pump(now); now++; }
            snprintf(w, sizeof w, "UNMUTED %s: the target is set", cases[c].name);   eqi(ap.target, cases[c].to, w);
            snprintf(w, sizeof w, "UNMUTED %s: completed at once", cases[c].name);   eqi(tr.active, 0, w);
            snprintf(w, sizeof w, "UNMUTED %s: no silence handed", cases[c].name);   eqi(ap.mute_handed, 0, w);
            snprintf(w, sizeof w, "UNMUTED %s: no discard past begin", cases[c].name); eqi(adec.discarded - disc0, cases[c].discard, w);
        }
    }
}

static void test_a_mute_too_short_for_its_mechanism_is_counted_and_raised(void)
{
    struct landing L = run(GBP_ATRANS_ROTATE, 512, 2048, 15, 12, 0, PUMPS - 1u);
    eqi(tr.faults, 1, "ROTATE: mute 15 < 12 + 4 is counted");
    eqi(L.mute_handed, 16, "and raised to pause + 4");
    eqi(L.fresh_after, L.ready_after, "and still masked");
    L = run(GBP_ATRANS_HELD, 1024, 1152, 1, 1, 0, PUMPS - 1u);
    eqi(tr.faults, 1, "HELD: mute 1 < 1 + 1 is counted");
    eqi(L.mute_handed, 2, "and raised to pause + 1");
    eqi(gbp_atrans_min_mute(GBP_ATRANS_ROTATE, 12), 16, "ROTATE needs pause + 4");
    eqi(gbp_atrans_min_mute(GBP_ATRANS_HELD, 1), 2, "HELD needs pause + 1");
    eqi(gbp_atrans_min_mute(GBP_ATRANS_UNMUTED, 9), 0, "UNMUTED needs none");
}

static void test_the_held_queue_splice_was_the_finding(void)
{
    /* §V27.15: under HELD the chunks in READY at the landing are the ones held from before the plan (the
     * music resumes where it paused) and the skip is spliced behind them -- which is why Phase 1 rotates */
    struct landing L = run(GBP_ATRANS_HELD, 2048, 2048, MUTE, 0, 0, PUMPS / 2u);
    eqi(L.fresh_after, 0, "HELD: none of the READY chunks at the landing is fresh: the old audio plays first");
    L = run(GBP_ATRANS_ROTATE, 2048, 2048, MUTE, 0, 0, PUMPS / 2u);
    eqi(L.fresh_after, L.ready_after, "ROTATE: all of them are");
}

static void test_the_hand_off_counted_pause_was_the_finding(void)
{
    /* the first version paused `pause` hand-offs and dropped a computed overshoot; begun right before
     * a hand-off, a climb of 16 (128 -> 144) then dropped 112 from a ring that had gained nothing */
    uint64_t now = steady(128);
    uint32_t k;
    (void)gbp_aplay_irq_handoff(&ap, now);
    for (k = 0; k < PUMPS - 1u; k++) { give(&adec, slice(k), 100); pump(now); now++; }
    give(&adec, slice(PUMPS - 1u), 100);
    eqi(adec.count, 128, "the ring at the level, right before a hand-off");
    (void)gbp_aplay_irq_handoff(&ap, now);                   /* the old rule: handed >= pause here */
    (void)gbp_adec_discard(&adec, 128u * 1u - 16u);          /* its overshoot drop */
    eqi(adec.count, 16, "the old rule left 16 in the ring: a chunk cannot even start");
}

static void test_init_and_counters(void)
{
    (void)run(GBP_ATRANS_ROTATE, 512, 2048, MUTE, 12, 0, 0u);
    eqi(tr.begun, 1, "one plan begun"); eqi(tr.completed, 1, "one completed"); eqi(tr.active, 0, "not active");
    eqi(tr.reached, 1, "the level was reached");
    eqi(tr.handed_seen >= MUTE + 1u, 1, "the hand-offs seen");
    eqi(tr.t_reached >= tr.t_start && tr.t_end >= tr.t_reached, 1, "t_start <= t_reached <= t_end");
    eqi(tr.rotate_landings, 1, "one ROTATE landing");
    eqi(tr.residue_min, tr.residue, "min"); eqi(tr.residue_max, tr.residue, "max");
}

int main(void)
{
    test_rotate_masks_at_every_phase();
    test_the_skip_sizes();
    test_the_skip_difference_is_the_latency_difference();
    test_rotate_under_a_bursty_feed();
    test_unmasked_only_where_a_splice_can_remain();
    test_the_module_waits_for_the_executor();
    test_held_lands_exactly_at_every_phase();
    test_unmuted_sets_the_target_and_does_not_chase();
    test_a_mute_too_short_for_its_mechanism_is_counted_and_raised();
    test_the_held_queue_splice_was_the_finding();
    test_the_hand_off_counted_pause_was_the_finding();
    test_init_and_counters();
    printf("test_gbp_atrans: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
