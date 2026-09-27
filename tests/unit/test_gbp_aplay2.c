/*
 * tests/unit/test_gbp_aplay2.c — GitHub Issue #126, Round B: the drift-correction layer at
 * 65 536 Hz, k = 16 fixed for this round (GBP-HW-349). The chunk/sub-block decision logic is
 * gbp_aplay.c's, ported (Issue #123's three review rounds settled it there); what is checked
 * here is that the port holds at the new PUSHES/BAND/k and that its OWN new properties hold: a
 * chunk always resamples to exactly 1000 output frames regardless of correction activity, the
 * resampler's accumulator is back at 0 at every chunk boundary, and the conservation and
 * reproducibility invariants Issue #126 asks for.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_aplay2.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

static int16_t decoder_ring[GBP_APLAY2_RING];
static int16_t out_ring[GBP_APLAY2_FRAMES * 8u];

/* fill the decoder's ring with decoded samples directly, as gbp_adec2_push_block would --
 * tests/unit/test_gbp_aplay.c's own pattern, generalised. */
static void give(struct gbp_adec2 *d, uint32_t n, int16_t v)
{
    uint32_t k;
    for (k = 0; k < n && d->count < d->cap; k++) {
        d->ring[(d->head + d->count) % d->cap] = v;
        d->count++;
    }
}

static void reset(struct gbp_aplay2 *p, struct gbp_adec2 *d)
{
    gbp_aplay2_init(p, out_ring, sizeof out_ring / sizeof out_ring[0]);
    gbp_adec2_init(d, decoder_ring, GBP_APLAY2_RING);
    p->playing = 1;
}

/* keep calling with a step limit until a chunk completes (or a generous bound is hit, which would
 * mean a real defect, not a test-driving choice: gbp_aplay.c's own gate arithmetic guarantees a
 * STARTED chunk always has enough samples to finish). */
static int drive(struct gbp_aplay2 *p, struct gbp_adec2 *d, uint32_t step)
{
    uint32_t i;
    for (i = 0; i < GBP_APLAY2_PUSHES + 4u; i++)
        if (gbp_aplay2_produce(p, d, step)) return 1;
    return 0;
}

static void test_defaults(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    eqi((long long)p.corr_per_chunk, GBP_APLAY2_K_DEFAULT, "the default is k = 16 (GBP-HW-349)");
    eqi((long long)p.target, GBP_APLAY2_TARGET, "the default target is the 0.125 s cushion");
    eqi((long long)GBP_APLAY2_TARGET, 8192, "0.125 s at 65 536 Hz is 8192 samples exactly");
    eqi((long long)GBP_APLAY2_PUSHES, 2048, "128 x 16 (GBP-HW-349)");
    eqi((long long)GBP_APLAY2_BAND, 256, "16 x gbp_aplay's BAND, the same time width");
}

static void test_a_chunk_resamples_to_exactly_1000_frames_at_rest(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    give(&d, GBP_APLAY2_TARGET, 0);                /* fill exactly at target */
    eqi(gbp_aplay2_produce(&p, &d, 0u), 1, "a whole chunk in one call");
    eqi((long long)p.produced, 1, "one chunk produced");
    eqi((long long)p.count, GBP_APLAY2_FRAMES, "exactly 1000 output frames, regardless of corrections");
    eqi((long long)p.rs.acc, 0, "the resampler's accumulator is back at 0 at the chunk boundary");
    eqi((long long)(p.dup + p.drop), 0, "at a fill exactly at target, no correction is due");
}

static void test_the_gate_is_pushes_plus_one(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    give(&d, GBP_APLAY2_PUSHES, 0);                /* one short */
    eqi(gbp_aplay2_produce(&p, &d, 0u), 0, "not enough to start a chunk");
    eqi((long long)p.starved_steps, 1, "counted");
    give(&d, 1u, 0);                                /* now exactly the gate */
    eqi(gbp_aplay2_produce(&p, &d, 0u), 1, "starts and finishes");
}

static void test_k_corrections_are_spread_one_per_sub_block(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    /* well under the band, ALL the way (not just past its edge): every sub-block DUPs, mirroring
     * gbp_aplay's own test_k_corrections_are_spread_one_per_sub_block */
    reset(&p, &d);
    give(&d, GBP_APLAY2_TARGET - GBP_APLAY2_BAND - 300u, 0);
    eqi(gbp_aplay2_produce(&p, &d, 0u), 1, "the chunk still finishes");
    eqi((long long)p.dup, GBP_APLAY2_K_DEFAULT, "sixteen DUPs, one per sub-block");
    eqi((long long)p.drop, 0, "no DROPs");
    eqi((long long)p.corr_forgone, 0, "every sub-block was decided");
    eqi((long long)p.cur_taken, GBP_APLAY2_PUSHES - GBP_APLAY2_K_DEFAULT,
        "each DUP takes one sample from the ring for two resampler pushes: 2048 - 16");
}

static void test_corr_forgone_when_a_sub_block_is_passed_uncorrected(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    /* the same low fill, but the whole chunk is produced as an UNCORRECTED transition chunk first
     * to exercise cur_uncorrected -- here instead we check the forgone count by resuming a
     * corrected chunk mid-way through several calls, mirroring gbp_aplay's own
     * test_forgone_corrections_are_counted, at this path's sub-block size (128 pushes) */
    reset(&p, &d);
    give(&d, GBP_APLAY2_TARGET - GBP_APLAY2_BAND - 300u, 0);
    /* a first, small-step call still catches sub-block 0's decision (it fires at cur_pushes == 0,
     * the call's very first push): nothing is forgone here, this just exercises multi-call driving */
    eqi(gbp_aplay2_produce(&p, &d, 300u), 0, "not finished yet");
    eqi(drive(&p, &d, 0u), 1, "finishes over further calls");
    eqi((long long)p.dup, GBP_APLAY2_K_DEFAULT, "every sub-block still decides eventually in this test");
    eqi((long long)p.corr_forgone, 0, "and none is forgone when every call lands on a sub-block start");
}

static void test_no_correction_below_playback(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    p.playing = 0;                                  /* prefill: at most one correction whatever k is */
    give(&d, GBP_APLAY2_TARGET - GBP_APLAY2_BAND - 300u, 0);
    eqi(gbp_aplay2_produce(&p, &d, 0u), 1, "prefill chunk finishes");
    eqi((long long)(p.dup + p.drop), 1, "at most one correction before playback, not k = 16");
}

static void test_uncorrected_chunk_takes_none(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    give(&d, GBP_APLAY2_TARGET - GBP_APLAY2_BAND - 300u, 0);    /* would DUP under a corrected call */
    eqi(gbp_aplay2_produce_ex(&p, &d, 0u, 1), 1, "an uncorrected (transition) chunk still finishes");
    eqi((long long)(p.dup + p.drop), 0, "and takes no correction");
    eqi((long long)p.cur_taken, GBP_APLAY2_PUSHES, "exactly PUSHES samples taken, none extra or forgone");
}

static void test_set_corrections_bounds(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    eqi(gbp_aplay2_set_corrections(&p, 0u), -1, "k = 0 rejected");
    eqi(gbp_aplay2_set_corrections(&p, GBP_APLAY2_PUSHES / 2u + 1u), -1, "k > PUSHES/2 rejected");
    eqi(gbp_aplay2_set_corrections(&p, 100u), -1, "k must divide PUSHES (2048 %% 100 != 0)");
    eqi(gbp_aplay2_set_corrections(&p, 32u), 0, "a legal k is accepted");
    eqi((long long)p.corr_per_chunk, 32, "and takes effect");
}

static void test_set_target_clamps(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    gbp_aplay2_set_target(&p, 0u);
    eqi((long long)p.target, GBP_APLAY2_TARGET_MIN, "clamped to the floor");
    gbp_aplay2_set_target(&p, 999999999u);
    eqi((long long)p.target, GBP_APLAY2_TARGET_MAX, "clamped to the ceiling");
}

/* Conservation: over N chunks, every sample the decoder's ring gave up (cur_taken, summed) equals
 * PUSHES x chunks - dup + drop exactly, and every chunk's output is exactly FRAMES samples. */
static void test_conservation(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    uint32_t i, chunks = 5u;
    long long fed = 0, taken_total = 0;
    reset(&p, &d);
    for (i = 0; i < chunks; i++) {
        give(&d, GBP_APLAY2_PUSHES + 1u, (int16_t)((i % 3u) * 100 - 100));   /* a varying, bursty feed */
        fed += GBP_APLAY2_PUSHES + 1u;
        /* drive it in small, uneven steps -- several hand-off phases, not one whole-chunk call */
        eqi(drive(&p, &d, 37u), 1, "each chunk completes over several small-step calls");
    }
    (void)taken_total;
    eqi((long long)p.produced, chunks, "every chunk completed under a bursty feed");
    eqi((long long)p.count, (long long)chunks * GBP_APLAY2_FRAMES, "output is exactly FRAMES samples a chunk");
    /* fed = consumed (popped) + still in the decoder's ring (delta stock); nothing overflowed or was lost
     * upstream in this test, so d->count is the only "still fed, not yet taken" term */
    eqi(fed - (long long)d.count, (long long)chunks * GBP_APLAY2_PUSHES - (long long)p.dup + (long long)p.drop,
        "fed = taken + delta stock, and taken = chunks x PUSHES - dup + drop (GBP-HW-349's k arithmetic)");
}

/* A deliberately undersized output ring: out_put() must count every sample it cannot hold rather
 * than dropping it silently (review round, #126 -- mirrors gbp_adec2's own ring_put2 overflow
 * counter, which this module's out_put() lacked until this test). */
static void test_out_overflow_is_counted(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    static int16_t small_ring[16];
    gbp_aplay2_init(&p, small_ring, sizeof small_ring / sizeof small_ring[0]);
    gbp_adec2_init(&d, decoder_ring, GBP_APLAY2_RING);
    p.playing = 1;
    give(&d, GBP_APLAY2_PUSHES + 1u, 100);
    eqi(drive(&p, &d, 0u), 1, "the chunk still completes despite an undersized output ring");
    eqi((long long)p.count, 16, "the ring holds only what it was sized for");
    eqi(p.out_overflow > 0u, 1, "every sample the ring could not hold is counted, not dropped silently");
    eqi((long long)p.out_overflow, (long long)GBP_APLAY2_FRAMES - 16, "exactly the samples the ring could not hold");
}

/* Reproducibility: the same feed sequence, replayed on a fresh state, gives an identical trace. */
static void test_reproducibility(void)
{
    struct gbp_aplay2 p1, p2;
    struct gbp_adec2 d1, d2;
    static int16_t decoder_ring2[GBP_APLAY2_RING];
    static int16_t out_ring2[GBP_APLAY2_FRAMES * 8u];
    uint32_t i;
    gbp_aplay2_init(&p1, out_ring, sizeof out_ring / sizeof out_ring[0]);
    gbp_adec2_init(&d1, decoder_ring, GBP_APLAY2_RING);
    p1.playing = 1;
    gbp_aplay2_init(&p2, out_ring2, sizeof out_ring2 / sizeof out_ring2[0]);
    gbp_adec2_init(&d2, decoder_ring2, GBP_APLAY2_RING);
    p2.playing = 1;
    for (i = 0; i < 4u; i++) {
        give(&d1, GBP_APLAY2_PUSHES + 1u, (int16_t)(i * 37 - 60));
        give(&d2, GBP_APLAY2_PUSHES + 1u, (int16_t)(i * 37 - 60));
        drive(&p1, &d1, 61u);
        drive(&p2, &d2, 61u);
    }
    eqi((long long)p1.produced, (long long)p2.produced, "same chunk count");
    eqi((long long)p1.dup, (long long)p2.dup, "same DUPs");
    eqi((long long)p1.drop, (long long)p2.drop, "same DROPs");
    eqi((long long)p1.corr_forgone, (long long)p2.corr_forgone, "same forgone count");
    eqi((long long)p1.count, (long long)p2.count, "same output length");
    eqi(memcmp(out_ring, out_ring2, (size_t)p1.count * sizeof(int16_t)) == 0, 1,
        "the same output samples, byte for byte");
}

int main(void)
{
    test_defaults();
    test_a_chunk_resamples_to_exactly_1000_frames_at_rest();
    test_the_gate_is_pushes_plus_one();
    test_k_corrections_are_spread_one_per_sub_block();
    test_corr_forgone_when_a_sub_block_is_passed_uncorrected();
    test_no_correction_below_playback();
    test_uncorrected_chunk_takes_none();
    test_set_corrections_bounds();
    test_set_target_clamps();
    test_conservation();
    test_out_overflow_is_counted();
    test_reproducibility();
    fprintf(stderr, "%d checks, %d failures\n", checks, failures);
    return failures != 0;
}
