/*
 * tests/unit/test_gbp_play_under.c -- GitHub Issue #153, HARDWARE_TESTS.md V31.3: the instrument of the fallback rule.
 *
 * Two layers. (1) The pure summary and the record formats, on hand-made ordinals. (2) The REAL chain (gbp_adec2 / gbp_aplay2) driven as the vehicle's
 * pump drives it, at T256 A1, through a COLD START from an empty ring and then a steady state: the delimiter (the first K hand-offs) ends in both, an
 * underrun injected at hand-off 1-2 is START-UP, one at hand-off 500 is AFTER-START-UP, and two underruns in one pump interval are two records.
 * The driver feeds exactly what a chunk consumes each hand-off period (GBP_APLAY2_PUSHES native samples), in 64-sample slices with a produce call after each
 * (the vehicle's steady production step), so a healthy run has no underrun at all -- the test says so first, or an injected one would prove nothing.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_play_under.h"
#include "gbp_adec2.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

static void eqs(const char *got, const char *want, const char *what)
{
    checks++;
    if (strcmp(got, want) != 0) {
        failures++;
        printf("  FAIL: %s:\n    got  %s\n    want %s\n", what, got, want);
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

/* ---- layer 1: the summary ------------------------------------------------------------------------------------------------------------------------------ */
static void test_summary_splits_at_k(void)
{
    struct gbp_play_under_sum s;
    volatile uint32_t h[GBP_APLAY2_UNDER_CAP];
    volatile uint64_t tt[GBP_APLAY2_UNDER_CAP];
    memset((void *)h, 0, sizeof h);
    memset((void *)tt, 0, sizeof tt);
    h[0] = 1u; h[1] = 64u; h[2] = 65u; h[3] = 500u;
    gbp_play_under_summarize(&s, 4u, h, tt, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, UINT64_MAX);
    eqi(s.startup, 2, "ordinals 1 and 64 are start-up (<= K)");
    eqi(s.after_startup, 2, "65 and 500 are after start-up: an underrun beyond K is never reclassified");
    eqi(s.first_after_handed, 65, "the first after-start-up ordinal is reported");
    eqi(s.unrecorded, 0, "nothing unrecorded");
    gbp_play_under_summarize(&s, 0u, h, tt, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, UINT64_MAX);
    eqi(s.startup + s.after_startup + s.first_after_handed, 0, "no underrun: everything zero");
}

static void test_summary_past_the_cap_counts_the_rest_as_after_startup(void)
{
    struct gbp_play_under_sum s;
    volatile uint32_t h[GBP_APLAY2_UNDER_CAP];
    volatile uint64_t tt[GBP_APLAY2_UNDER_CAP];
    uint32_t i;
    for (i = 0u; i < GBP_APLAY2_UNDER_CAP; i++) { h[i] = i + 1u; tt[i] = i; }     /* every one of the first 64 hand-offs underran: all start-up */
    gbp_play_under_summarize(&s, GBP_APLAY2_UNDER_CAP + 10u, h, tt, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, UINT64_MAX);
    eqi(s.recorded, GBP_APLAY2_UNDER_CAP, "64 recorded");
    eqi(s.unrecorded, 10, "ten more were counted, not recorded");
    eqi(s.startup, 64, "the recorded ones are start-up");
    eqi(s.after_startup, 10, "the ten unrecorded came after ordinal 64: after start-up");
    eqi(s.first_after_handed, 0, "no recorded after-start-up ordinal: 0, and `unrecorded` says why");
}

static void test_the_record_formats(void)
{
    char b[256];
    struct gbp_play_under_sum s = { 5u, 5u, 0u, 3u, 0u, 2u, 1234u };   /* total, recorded, unrecorded, startup, post_feed, after_startup, first_after */
    gbp_play_under_fmt_startup(b, sizeof b, 0x123456789abcull, 64u, 4200u, 1u);
    eqs(b, "PLAYSTARTUP t_dma=123456789abc k=64 ring_at_dma=4200 ready_at_dma=1", "PLAYSTARTUP");
    gbp_play_under_fmt_und(b, sizeof b, 2u, 77u, 40500000u * 3u + 100u, 100u, 40500000u, 0);
    eqs(b, "PLAYUND n=2 handed=77 since_dma_ms=3000 post_feed=0", "PLAYUND (ms from the time base)");
    gbp_play_under_fmt_und(b, sizeof b, 0u, 1u, 5u, 100u, 40500000u, 1);
    eqs(b, "PLAYUND n=0 handed=1 since_dma_ms=0 post_feed=1", "an instant before the DMA stamp reads 0, never a wrapped figure");
    gbp_play_under_fmt_sum(b, sizeof b, &s, 64u);
    eqs(b, "PLAYUNDER startup=3 after_startup=2 post_feed=0 first_after_handed=1234 unrecorded=0 total=5 k=64", "PLAYUNDER");
    s.first_after_handed = 0u;
    gbp_play_under_fmt_sum(b, sizeof b, &s, 64u);
    eqs(b, "PLAYUNDER startup=3 after_startup=2 post_feed=0 first_after_handed=- unrecorded=0 total=5 k=64", "PLAYUNDER with no recorded after-start-up ordinal");
    check(strlen(b) < 248u, "every record fits the log line (LOG_LINE_LEN 256)");
}

static void test_post_feed_is_teardown_silence_and_never_after_startup(void)
{
    struct gbp_play_under_sum s;
    volatile uint32_t h[GBP_APLAY2_UNDER_CAP];
    volatile uint64_t tt[GBP_APLAY2_UNDER_CAP];
    uint32_t i;
    memset((void *)h, 0, sizeof h);
    memset((void *)tt, 0, sizeof tt);
    /* a genuine underrun at ordinal 300 (t=1000), a start-up one (ordinal 2, t=50), then three silences after the feed ended at t=2000 */
    h[0] = 2u;   tt[0] = 50u;
    h[1] = 300u; tt[1] = 1000u;
    h[2] = 900u; tt[2] = 2500u;
    h[3] = 901u; tt[3] = 2600u;
    h[4] = 902u; tt[4] = 2700u;
    gbp_play_under_summarize(&s, 5u, h, tt, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, 2000u);
    eqi(s.startup, 1, "the start-up underrun stays start-up");
    eqi(s.after_startup, 1, "only the genuine underrun (t <= the feed's end) is after start-up");
    eqi(s.post_feed, 3, "the three later silences are post-feed");
    eqi(s.first_after_handed, 300, "first_after_handed is the genuine one, not the first silence");
    /* a start-up underrun later than the feed's end is still start-up: the classification by ordinal comes first */
    gbp_play_under_summarize(&s, 1u, h, tt, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, 10u);
    eqi(s.startup, 1, "ordinal <= K is start-up whatever its instant");
    eqi(s.post_feed, 0, "and never post-feed");
    /* a long teardown past the cap: the unrecorded silences after a post-feed record are post-feed too */
    for (i = 0u; i < GBP_APLAY2_UNDER_CAP; i++) { h[i] = 100u + i; tt[i] = (i < 10u) ? 100u + i : 5000u + i; }
    gbp_play_under_summarize(&s, GBP_APLAY2_UNDER_CAP + 30u, h, tt, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, 1000u);
    eqi(s.after_startup, 10, "ten genuine underruns before the feed ended");
    eqi(s.post_feed, (long long)GBP_APLAY2_UNDER_CAP - 10 + 30, "54 recorded silences plus the 30 unrecorded ones that follow them");
    eqi(s.unrecorded, 0, "nothing is left unclassified");
    /* ... but a recorded GENUINE last record leaves the unrecorded ones after start-up, as before */
    for (i = 0u; i < GBP_APLAY2_UNDER_CAP; i++) { h[i] = 100u + i; tt[i] = 100u + i; }
    gbp_play_under_summarize(&s, GBP_APLAY2_UNDER_CAP + 30u, h, tt, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, 100000u);
    eqi(s.after_startup, (long long)GBP_APLAY2_UNDER_CAP + 30, "no post-feed: all after start-up");
    eqi(s.post_feed, 0, "none post-feed");
}

/* ---- layer 2: the real chain ------------------------------------------------------------------------------------------------------------------------ */
static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t ring[GBP_APLAY2_RING];

struct rig { struct gbp_aplay2 p; struct gbp_adec2 d; uint64_t t; int started; uint32_t fed_total; uint32_t count_at_start; };

static uint32_t steady_step(void *user, uint32_t seq)
{
    (void)user; (void)seq;
    return 64u;
}

static void rig_init(struct rig *r)
{
    memset(r, 0, sizeof *r);
    gbp_aplay2_init(&r->p, pool, silence, NULL, NULL);
    gbp_adec2_init(&r->d, ring, GBP_APLAY2_RING);
    gbp_aplay2_set_target(&r->p, 4096u);          /* T256 */
    r->p.ahead = 1u;                              /* A1 */
    r->p.step_pushes = steady_step;
}

static void rig_feed(struct rig *r, uint32_t n)
{
    while (n && r->d.count < r->d.cap) {
        r->d.ring[(r->d.head + r->d.count) % r->d.cap] = 100;
        r->d.count++;
        n--;
        r->fed_total++;
    }
}

/* the pump's own production call (live_step's audio block): produce, queue, process; and the DMA start the moment start_ready() holds */
static void rig_pump(struct rig *r)
{
    int b = gbp_aplay2_produce(&r->p, &r->d);
    if (b >= 0) gbp_aplay2_queue(&r->p, b);
    gbp_aplay2_process(&r->p);
    if (!r->started && gbp_aplay2_start_ready(&r->p, r->d.count)) {
        r->started = 1;
        r->count_at_start = r->d.count;                 /* the fill AT the DMA start, as PLAYSTARTUP reads it */
        r->p.playing = 1u;
        (void)gbp_aplay2_irq_handoff(&r->p, r->t);          /* hand-off ordinal 1 */
    }
}

/* one hand-off period: `feed` native samples arrive in 64-sample slices, the pump runs after each (and a few more times, as it does between taps),
 * then the DMA callback fires (once, or `callbacks` times when a test injects two in one pump interval) */
static void rig_period(struct rig *r, uint32_t feed, uint32_t callbacks)
{
    uint32_t left = feed, k;
    r->t += 1265625u;                                       /* 31.25 ms at the 40.5 MHz time base */
    while (left) {
        const uint32_t n = left < 64u ? left : 64u;
        rig_feed(r, n);
        left -= n;
        rig_pump(r);
    }
    for (k = 0u; k < 40u; k++) rig_pump(r);
    if (r->started)
        for (k = 0u; k < callbacks; k++) (void)gbp_aplay2_irq_handoff(&r->p, r->t + k);
}

static void stall(struct rig *r, uint32_t periods)
{
    while (periods--) rig_period(r, 0u, 1u);            /* the feed stops: the ring's stock and the queue drain, then the DMA finds nothing */
}

static void cold_start(struct rig *r)
{
    uint32_t guard = 0u;
    rig_init(r);
    while (!r->started && guard++ < 1000u) rig_period(r, GBP_APLAY2_PUSHES, 0u);
    check(r->started, "the cold start at T256 A1 from an EMPTY ring reaches start_ready (no deadlock at AHEAD 1)");
    check(r->count_at_start >= r->p.target, "and the ring held the target fill at the DMA start (start_ready's own requirement)");
    eqi((long long)r->p.handed, 1, "the start's own first hand-off is ordinal 1");
    eqi((long long)r->p.underruns, 0, "no underrun at the start itself");
}

static void test_a_healthy_cold_start_and_steady_state_have_no_underrun(void)
{
    struct rig r;
    struct gbp_play_under_sum s;
    uint32_t i;
    cold_start(&r);
    for (i = 0u; i < 600u; i++) rig_period(&r, GBP_APLAY2_PUSHES, 1u);
    gbp_play_under_summarize(&s, (uint32_t)r.p.underruns, r.p.under_handed, r.p.under_t, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, UINT64_MAX);
    eqi(s.total, 0, "600 hand-off periods of a matched feed: no underrun at all (the baseline the injections are read against)");
    check(r.p.handed > GBP_PLAY_STARTUP_K + 500u, "the delimiter (the first K hand-offs) ends in the steady state too: handed passed K by far");
}

static void test_a_callback_right_after_the_dma_start_is_an_underrun_at_ordinal_2_and_is_startup(void)
{
    /* GBP-HW-372: the callback fires as a block starts. At AHEAD 1 the start's own hand-off consumed the one ready chunk, so a callback BEFORE the pump refills finds the queue empty
     * (RUN 55-58 each show one underrun in navigate). The rig's other cases give the pump a full period first; this one does not. */
    struct rig r;
    struct gbp_play_under_sum s;
    uint32_t guard = 0u;
    rig_init(&r);
    while (!r.started && guard++ < 100000u) { rig_feed(&r, 64u); rig_pump(&r); }   /* slice by slice: the DMA starts inside the pump call that completes the first chunk */
    check(r.started, "test setup: the DMA started");
    eqi((long long)r.p.handed, 1, "test setup: only the start's own hand-off so far");
    (void)gbp_aplay2_irq_handoff(&r.p, r.t + 1u);             /* the very next callback, before the pump ran again */
    gbp_play_under_summarize(&s, (uint32_t)r.p.underruns, r.p.under_handed, r.p.under_t, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, UINT64_MAX);
    eqi(s.total, 1, "an immediate callback finds nothing ready");
    eqi((long long)r.p.under_handed[0], 2, "it is hand-off ordinal 2");
    eqi(s.startup, 1, "and it is start-up, not after start-up");
}

static void test_an_underrun_at_the_start_is_startup(void)
{
    struct rig r;
    struct gbp_play_under_sum s;
    uint32_t i;
    cold_start(&r);
    stall(&r, 4u);                                          /* the feed stops for four periods right after the DMA start */
    for (i = 0u; i < 200u; i++) rig_period(&r, GBP_APLAY2_PUSHES, 1u);
    gbp_play_under_summarize(&s, (uint32_t)r.p.underruns, r.p.under_handed, r.p.under_t, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, UINT64_MAX);
    check(s.total >= 1u, "test setup: the stalled feed produced an underrun");
    eqi(s.startup, (long long)s.total, "every underrun of the stalled first period is START-UP");
    eqi(s.after_startup, 0, "and none is after start-up");
    check(r.p.under_handed[0] >= 1u && r.p.under_handed[0] <= GBP_PLAY_STARTUP_K, "its ordinal is inside the first K hand-offs");
}

static void test_an_underrun_at_hand_off_500_is_after_startup(void)
{
    struct rig r;
    struct gbp_play_under_sum s;
    uint32_t i;
    cold_start(&r);
    for (i = 0u; i < 498u; i++) rig_period(&r, GBP_APLAY2_PUSHES, 1u);
    eqi((long long)r.p.underruns, 0, "test setup: clean up to hand-off 499");
    stall(&r, 4u);                                          /* the feed stops for four periods: hand-offs 500-503 or so */
    for (i = 0u; i < 50u; i++) rig_period(&r, GBP_APLAY2_PUSHES, 1u);
    gbp_play_under_summarize(&s, (uint32_t)r.p.underruns, r.p.under_handed, r.p.under_t, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, UINT64_MAX);
    check(s.total >= 1u, "test setup: the stalled feed produced an underrun");
    eqi(s.startup, 0, "none is start-up");
    eqi(s.after_startup, (long long)s.total, "all after start-up");
    check(s.first_after_handed >= 495u && s.first_after_handed <= 505u, "its ordinal is about 500: the record says where");
}

static void test_two_underruns_in_one_pump_interval_are_two_records(void)
{
    struct rig r;
    struct gbp_play_under_sum s;
    uint32_t i;
    cold_start(&r);
    for (i = 0u; i < 100u; i++) rig_period(&r, GBP_APLAY2_PUSHES, 1u);
    eqi((long long)r.p.underruns, 0, "test setup: clean at hand-off 101");
    { uint32_t k; for (k = 0u; k < 40u; k++) rig_pump(&r); }   /* the pump refills the queue (one chunk at AHEAD 1) */
    eqi((long long)gbp_aplay2_ready(&r.p), 1, "test setup: one chunk ready");
    (void)gbp_aplay2_irq_handoff(&r.p, r.t + 1u);           /* consumes the ready chunk ... */
    (void)gbp_aplay2_irq_handoff(&r.p, r.t + 2u);           /* ... and two empty ones, with no pump call between */
    (void)gbp_aplay2_irq_handoff(&r.p, r.t + 3u);
    gbp_play_under_summarize(&s, (uint32_t)r.p.underruns, r.p.under_handed, r.p.under_t, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, UINT64_MAX);
    eqi(s.total, 2, "two empty hand-offs between two pump calls are two underruns");
    eqi(s.after_startup, 2, "both after start-up");
    eqi((long long)r.p.under_handed[1] - (long long)r.p.under_handed[0], 1, "with consecutive ordinals: two records, not one");
    eqi((long long)r.p.handed, 104, "test setup: hand-off 1 at the start, one per period for 100 periods, then three more calls");
    eqi((long long)r.p.under_handed[0], 103, "the first underrun is the third of those calls: EXACTLY ordinal 103 (the ordinal counts the call that found the queue empty)");
    eqi((long long)r.p.under_handed[1], 104, "the second is ordinal 104");
}

int main(void)
{
    test_summary_splits_at_k();
    test_summary_past_the_cap_counts_the_rest_as_after_startup();
    test_the_record_formats();
    test_post_feed_is_teardown_silence_and_never_after_startup();
    test_a_callback_right_after_the_dma_start_is_an_underrun_at_ordinal_2_and_is_startup();
    test_a_healthy_cold_start_and_steady_state_have_no_underrun();
    test_an_underrun_at_the_start_is_startup();
    test_an_underrun_at_hand_off_500_is_after_startup();
    test_two_underruns_in_one_pump_interval_are_two_records();
    printf("test_gbp_play_under: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
