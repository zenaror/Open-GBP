/*
 * test_gbp_adec — the AUDIO decoder and the 125/16 resampler, on SYNTHETIC
 * blocks (Issue #81). No hardware, no emulator, no capture: every expected value
 * here is derived by hand from the formula in gbp_adec.h. Bit-identity against
 * #80's validated WAVs is tests/host/test_audio_runtime.py's job.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_adec.h"
#include "gbp_aresamp.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static uint8_t blk[GBP_ADEC_BLOCK_BYTES];

/* a block holding exactly `ones` one-bits, as whole 0xFF bytes plus one partial */
static void make_block(uint32_t ones)
{
    uint32_t full = ones / 8u, rem = ones % 8u;
    memset(blk, 0, sizeof blk);
    memset(blk, 0xFF, full);
    if (rem) blk[full] = (uint8_t)(0xFFu << (8u - rem));
}

static void test_popcount(void)
{
    make_block(0);      CHECK(gbp_adec_popcount(blk) == 0u);
    make_block(16384);  CHECK(gbp_adec_popcount(blk) == 16384u);
    make_block(32768);  CHECK(gbp_adec_popcount(blk) == 32768u);
    make_block(12345);  CHECK(gbp_adec_popcount(blk) == 12345u);
    /* byte ORDER does not matter under the layout: the same bits, spread out */
    memset(blk, 0, sizeof blk);
    { uint32_t i; for (i = 0; i < 4096u; i += 2u) blk[i] = 0x80; }
    CHECK(gbp_adec_popcount(blk) == 2048u);
}

static void test_sample_formula(void)
{
    struct gbp_adec d;
    int16_t ring[4];
    gbp_adec_init(&d, ring, 4);
    CHECK(gbp_adec_sample(&d, 20000u) == 0);            /* not calibrated: silence */
    make_block(16384);
    gbp_adec_calibrate(&d, blk);                         /* rest = exactly half */
    CHECK(d.rest_n == 1u && d.rest_sum == 16384);
    CHECK(gbp_adec_sample(&d, 16384u) == 0);             /* silence decodes to zero */
    /* a deviation of 0.125 of the block (4096 bits) -> 80 % of full scale:
     * 4096 * 32767 / 5120 = 26213.6 -> 26214 */
    CHECK(gbp_adec_sample(&d, 16384u + 4096u) == 26214);
    CHECK(gbp_adec_sample(&d, 16384u - 4096u) == -26214);
    /* clipping: the whole block on */
    CHECK(gbp_adec_sample(&d, 32768u) == 32767);
    CHECK(gbp_adec_sample(&d, 0u) == -32767);
}

static void test_half_to_even(void)
{
    /* With n = 1 and S = 0 the value is p * 32767 / 5120. Find a p where that is
     * exactly k + 1/2 and check the even neighbour is chosen: 32767 * p / 5120 has
     * remainder 2560 when p = 2560 * inv(32767) mod 5120. Search instead of
     * solving, so the test states what it checks. */
    struct gbp_adec d;
    int16_t ring[1];
    uint32_t p;
    int found = 0;
    gbp_adec_init(&d, ring, 1);
    d.rest_sum = 0;
    d.rest_n = 1u;
    for (p = 1u; p <= 32768u && !found; p++) {
        long long num = (long long)p * 32767LL;
        if (num % 5120LL == 2560LL) {
            long long q = num / 5120LL;
            int16_t s = gbp_adec_sample(&d, p);
            CHECK(s == (int16_t)((q % 2LL == 0LL) ? q : q + 1LL));
            found = 1;
        }
    }
    CHECK(found);
}

static void test_ring_overflow_and_lost(void)
{
    struct gbp_adec d;
    int16_t ring[2], s;
    gbp_adec_init(&d, ring, 2);
    make_block(16384);
    gbp_adec_calibrate(&d, blk);
    make_block(16384 + 4096);
    CHECK(gbp_adec_push_block(&d, blk) == 0);
    CHECK(gbp_adec_push_lost(&d) == 0);                  /* a HOLD of the previous sample */
    CHECK(gbp_adec_push_block(&d, blk) == -1);           /* full: dropped and COUNTED */
    CHECK(d.overflow == 1u && d.lost == 1u && d.blocks_in == 2u);
    CHECK(gbp_adec_pop(&d, &s) == 1 && s == 26214);
    CHECK(gbp_adec_pop(&d, &s) == 1 && s == 26214);      /* the held value */
    CHECK(gbp_adec_pop(&d, &s) == 0);
}

static void test_resampler_is_exact(void)
{
    struct gbp_aresamp r;
    int16_t out[GBP_ARESAMP_MAX_OUT];
    uint32_t i, total = 0u;
    gbp_aresamp_init(&r);
    for (i = 0; i < 16u * 100u; i++)
        total += gbp_aresamp_push(&r, 0, out);
    /* 16 inputs -> exactly 125 outputs, and the phase returns to where it began */
    CHECK(total == 12500u);
    CHECK(r.acc == 0u);
    CHECK(r.in_count == 1600u && r.out_count == 12500u);
}

static void test_resampler_dc_and_identity(void)
{
    struct gbp_aresamp r;
    int16_t out[GBP_ARESAMP_MAX_OUT];
    uint32_t i, n, k;
    int ok_dc = 1;
    gbp_aresamp_init(&r);
    /* after the history fills, a constant comes out EXACTLY constant at every phase */
    for (i = 0; i < 64u; i++) {
        n = gbp_aresamp_push(&r, 1000, out);
        if (i >= 16u)
            for (k = 0; k < n; k++)
                if (out[k] != 1000) ok_dc = 0;
    }
    CHECK(ok_dc);
    /* Phase 0 lands ON an input sample, 8 back, and must reproduce it exactly --
     * with the SIGN it had, which an int16 coefficient table would have flipped.
     * The accumulator is at phase 0 only after a multiple of 16 inputs, so the
     * first output of input 16 is input 8. */
    gbp_aresamp_init(&r);
    for (i = 0; i <= 16u; i++) {
        n = gbp_aresamp_push(&r, (int16_t)(i == 8u ? -12345 : 0), out);
        if (i == 16u) CHECK(n >= 1u && out[0] == -12345);
    }
}

/* Issue #110: the formula exactly as it stood before the clip counter (dca5bb8),
 * restated here so the counter is shown to change NO output value. */
static int16_t ref_sample(long long rest_sum, long long n, uint32_t p, long long *unclipped)
{
    long long num, den, q, r;
    if (n == 0) { *unclipped = 0; return 0; }
    num = (n * (long long)p - rest_sum) * 32767LL;
    den = 5LL * 1024LL * n;
    q = num / den; r = num % den;
    if (r < 0) { q -= 1; r += den; }
    if (2 * r > den || (2 * r == den && (q & 1))) q += 1;
    *unclipped = q;
    if (q > 32767) q = 32767;
    if (q < -32767) q = -32767;
    return (int16_t)q;
}

static void test_clip_counter_changes_no_output(void)
{
    /* several calibrations: the silent half, an odd multi-block sum, and both extremes */
    static const long long SUMS[4] = { 16384LL, 4096LL * 16383LL + 7LL, 0LL, 32768LL };
    static const uint32_t NS[4] = { 1u, 4096u, 1u, 1u };
    int16_t ring[1], s;
    unsigned c;
    for (c = 0; c < 4u; c++) {
        struct gbp_adec d;
        uint32_t p, want_clips = 0u;
        int same_sample = 1, same_push = 1;
        gbp_adec_init(&d, ring, 1);
        d.rest_sum = SUMS[c];
        d.rest_n = NS[c];
        for (p = 0u; p <= 32768u; p++) {
            long long u;
            const int16_t want = ref_sample(SUMS[c], NS[c], p, &u);
            if (u > 32767 || u < -32767) want_clips++;
            if (gbp_adec_sample(&d, p) != want) same_sample = 0;
            make_block(p);
            if (gbp_adec_push_block(&d, blk) != 0 || gbp_adec_pop(&d, &s) != 1 || s != want) same_push = 0;
        }
        CHECK(same_sample);
        CHECK(same_push);
        CHECK(d.clipped == want_clips);
        CHECK(d.blocks_in == 32769u);
    }
}

static void test_clip_counter_edges(void)
{
    struct gbp_adec d;
    int16_t ring[8], s;
    gbp_adec_init(&d, ring, 8);
    CHECK(d.clipped == 0u);
    make_block(16384);
    gbp_adec_calibrate(&d, blk);
    make_block(16384u + 5120u);                          /* exactly full scale: 32767, NOT clipped */
    CHECK(gbp_adec_push_block(&d, blk) == 0 && d.clipped == 0u);
    make_block(16384u + 5121u);                          /* 32773.4 -> 32767, clipped and counted */
    CHECK(gbp_adec_push_block(&d, blk) == 0 && d.clipped == 1u);
    make_block(16384u - 5121u);
    CHECK(gbp_adec_push_block(&d, blk) == 0 && d.clipped == 2u);
    CHECK(gbp_adec_push_lost(&d) == 0 && d.clipped == 2u);   /* a hold is not a clip */
    CHECK(gbp_adec_pop(&d, &s) == 1 && s == 32767);
    CHECK(gbp_adec_pop(&d, &s) == 1 && s == 32767);
    CHECK(gbp_adec_pop(&d, &s) == 1 && s == -32767);
    CHECK(gbp_adec_pop(&d, &s) == 1 && s == -32767);
}

static void test_calibration_spread(void)
{
    struct gbp_adec d;
    int16_t ring[1];
    gbp_adec_init(&d, ring, 1);
    CHECK(d.rest_min == 0u && d.rest_max == 0u);
    make_block(16385); gbp_adec_calibrate(&d, blk);
    CHECK(d.rest_min == 16385u && d.rest_max == 16385u);
    make_block(16380); gbp_adec_calibrate(&d, blk);
    make_block(16390); gbp_adec_calibrate(&d, blk);
    make_block(16384); gbp_adec_calibrate(&d, blk);
    CHECK(d.rest_min == 16380u && d.rest_max == 16390u);
    CHECK(d.rest_n == 4u && d.rest_sum == 16385LL + 16380LL + 16390LL + 16384LL);
}

int main(void)
{
    test_clip_counter_changes_no_output();
    test_clip_counter_edges();
    test_calibration_spread();
    test_popcount();
    test_sample_formula();
    test_half_to_even();
    test_ring_overflow_and_lost();
    test_resampler_is_exact();
    test_resampler_dc_and_identity();
    printf("test_gbp_adec: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
