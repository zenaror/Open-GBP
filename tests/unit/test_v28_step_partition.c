/*
 * tests/unit/test_v28_step_partition.c -- GitHub Issue #138 (RUN 54): the steady production step of 64 pushes a call (gbp_v28_step.h) changes
 * ONLY how a chunk's 2048 pushes are partitioned into pump calls; the output is byte-identical.
 *
 * Proven on the REAL chain (gbp_aplay2 over gbp_adec2), for steps 128, 64, 32, 16 and an irregular per-chunk mix (a chunk-by-chunk mix of the two): the same ring content, the same target, k = 16 -- every completed chunk's bytes (CRC),
 * its correction count, the totals dup/drop/forgone, and the ring left behind are compared with the 128-push run. Three regimes exercise the
 * corrector: the fill above target and then drifting, DUP (target well above), DROP (well below). The feed is a function of the CHUNK, never of
 * the number of calls, so a step cannot change what the ring holds at a chunk start: that is exactly the claim (the corrector decides from the
 * fill latched at the chunk's start, gbp_aplay2.c cur_s0/cur_target), and a time-driven feed would be a different experiment.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_v28_step.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) { failures++; printf("  FAIL: %s: got %lld, want %lld\n", what, got, want); }
}

static void check(int cond, const char *what)
{
    checks++;
    if (!cond) { failures++; printf("  FAIL: %s\n", what); }
}

static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events[GBP_APLAY2_EVENTS_CAP];
static int16_t ring[GBP_APLAY2_RING];
static struct gbp_aplay2 p;
static struct gbp_adec2 d;

#define CHUNKS 24u

static uint32_t pattern_step;         /* 0: an irregular mix per chunk; else a fixed step */
static uint32_t hook(void *user, uint32_t seq)
{
    (void)user;
    if (pattern_step) return pattern_step;
    /* an arbitrary per-chunk mix of the two steps (the library default and the steady one): any partition of the same pushes is the same output */
    return ((seq * 7u + (seq >> 2)) & 1u) ? GBP_APLAY2_STEP_PUSHES : gbp_v28_step_hook(user, seq);
}

static uint32_t lcg = 1u;
static int16_t next_sample(void)
{
    lcg = lcg * 1664525u + 1013904223u;
    return (int16_t)((lcg >> 12) & 0x7FFFu) - 16384;      /* not constant: the resampler's state shows in the bytes */
}

static uint32_t crc32_of(const uint8_t *b, uint32_t n)
{
    uint32_t c = 0xFFFFFFFFu, i, k;
    for (i = 0; i < n; i++) {
        c ^= b[i];
        for (k = 0; k < 8u; k++) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
    }
    return ~c;
}

struct trace {
    uint32_t crc[CHUNKS];
    uint32_t corr[CHUNKS];
    uint32_t dup, drop, forgone, ring_after, produced, calls;
    uint32_t max_call_pushes;
};

/* one run: `chunks` chunks from the same ring content, the ring topped up by a fixed number of samples before each chunk */
static void run(uint32_t step, int32_t target_offset, struct trace *t)
{
    uint32_t c, seq_calls = 0u;
    memset(t, 0, sizeof *t);
    lcg = 1u;
    memset(&p, 0, sizeof p);
    gbp_adec2_init(&d, ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&p, pool, silence, keep, events);
    p.playing = 1u;
    p.ahead = GBP_APLAY2_POOL - 2u;                /* the READY queue never gates a chunk in this test */
    pattern_step = step;
    p.step_pushes = hook;
    p.step_pushes_user = 0;
    {
        uint32_t k;
        for (k = 0; k < 6000u; k++) { d.ring[(d.head + d.count) % d.cap] = next_sample(); d.count++; }
    }
    gbp_aplay2_set_target(&p, (uint32_t)((int32_t)d.count + target_offset));
    for (c = 0; c < CHUNKS; c++) {
        int b = -1;
        uint32_t guard = 0u, k;
        /* the chain's feed: 2000 samples a chunk, decided by the chunk index alone */
        for (k = 0; k < 2000u; k++) { d.ring[(d.head + d.count) % d.cap] = next_sample(); d.count++; }
        while (b < 0 && guard++ < 4096u) {
            const uint32_t pushed0 = p.cur >= 0 ? p.cur_pushes : 0u;
            b = gbp_aplay2_produce(&p, &d);
            seq_calls++;
            if (b >= 0 || p.cur >= 0) {
                const uint32_t now_pushes = b >= 0 ? GBP_APLAY2_PUSHES : p.cur_pushes;
                if (now_pushes - pushed0 > t->max_call_pushes) t->max_call_pushes = now_pushes - pushed0;
            }
        }
        check(b >= 0, "every chunk completes");
        if (b < 0) return;
        t->crc[c] = crc32_of(pool + (size_t)b * GBP_APLAY2_CHUNK_BYTES, GBP_APLAY2_CHUNK_BYTES);
        t->corr[c] = p.chunk_corrections;
        gbp_aplay2_queue(&p, b);
        (void)gbp_aplay2_irq_handoff(&p, c);           /* hand it off: the buffer is FREE again after process() */
        gbp_aplay2_process(&p);
    }
    t->dup = p.dup;
    t->drop = p.drop;
    t->forgone = p.corr_forgone;
    t->ring_after = d.count;
    t->produced = p.produced;
    t->calls = seq_calls;
}

static void same_output(const struct trace *a, const struct trace *b, const char *what)
{
    uint32_t c;
    int all = 1;
    for (c = 0; c < CHUNKS; c++) all = all && a->crc[c] == b->crc[c] && a->corr[c] == b->corr[c];
    check(all, what);
    eqi(a->dup, b->dup, "same dup total");
    eqi(a->drop, b->drop, "same drop total");
    eqi(a->forgone, b->forgone, "same forgone total");
    eqi(a->ring_after, b->ring_after, "same ring left behind");
    eqi(a->produced, b->produced, "same chunks produced");
}

static void test_regime(int32_t offset, const char *name, int expect_dup, int expect_drop)
{
    static struct trace ref, t;
    static const uint32_t steps[] = {64u, 32u, 16u, 37u, 0u};
    uint32_t i;
    char msg[160];
    run(GBP_APLAY2_STEP_PUSHES, offset, &ref);
    if (expect_dup) check(ref.dup > 0u, "the regime really DUPs (the test can see the corrector)");
    if (expect_drop) check(ref.drop > 0u, "the regime really DROPs");
    /* (a regime with neither flag is whatever the drift makes of it: what is compared is that every step gives the same) */
    for (i = 0; i < sizeof steps / sizeof steps[0]; i++) {
        run(steps[i], offset, &t);
        snprintf(msg, sizeof msg, "%s: step %u (0 = the per-chunk mix) gives the 128-push run's bytes and corrections", name, (unsigned)steps[i]);
        same_output(&ref, &t, msg);
        if (steps[i] == 64u) {
            check(t.calls > ref.calls, "and takes more calls (the whole point: shorter stretches)");
            check(t.max_call_pushes <= 64u + 1u, "no call exceeds the step by more than the one push a DUP adds");
        }
    }
}

static void test_the_step_function(void)
{
    eqi(gbp_v28_step_hook(0, 0u), 64, "the hook answers the steady 64, for every chunk");
    eqi(gbp_v28_step_hook(0, 12345u), 64, "whatever the sequence number");
    eqi(GBP_V28_STEP_STEADY * 2u, GBP_APLAY2_STEP_PUSHES, "the steady step is half the transition step");
}

static void test_forgone_is_zero_at_a_step_that_divides_the_sub_block(void)
{
    static struct trace t;
    run(64u, 0, &t);
    eqi(t.forgone, 0, "no sub-block decision is forgone at 64 (a call never passes a decision point)");
    run(37u, 0, &t);
    check(1, "an odd step still completes (the comparison above proves it identical)");
}

int main(void)
{
    printf("test_v28_step_partition\n");
    test_the_step_function();
    test_regime(0, "ring above target, then drifting", 0, 0);
    test_regime(1500, "DUP regime", 1, 0);
    test_regime(-1500, "DROP regime", 0, 1);
    test_forgone_is_zero_at_a_step_that_divides_the_sub_block();
    printf("  %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
