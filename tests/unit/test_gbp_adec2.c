/*
 * test_gbp_adec2 — GitHub Issue #126, Round B: the per-slice, two-stream decoder, on SYNTHETIC
 * blocks. No hardware, no capture: every expected value is derived by hand from gbp_adec2.h's
 * formula. The energy-gain comparison against gbp_adec.c on archived bytes is
 * tests/host/test_v126_chain.py's job.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_adec2.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static uint8_t blk[GBP_ADEC2_BLOCK_BYTES];

/* every group's byte at offset A gets bit pattern `abits` (MSB first), offset B gets `bbits`, so
 * every one of the 16 slices' wA = popcount(abits) x 32 / 8... actually one BYTE per group, so
 * wA per slice = 32 x popcount(abits), same for every slice: a flat, DC-only block. */
static void make_flat(uint8_t abyte, uint8_t bbyte)
{
    uint32_t i;
    memset(blk, 0, sizeof blk);
    for (i = 0; i < GBP_ADEC2_BLOCK_BYTES; i += GBP_ADEC2_GROUP_BYTES) {
        blk[i + GBP_ADEC2_STREAM_A] = abyte;
        blk[i + GBP_ADEC2_STREAM_B] = bbyte;
    }
}

static int popcount8(uint8_t b)
{
    int n = 0;
    while (b) { n += b & 1; b >>= 1; }
    return n;
}

static void test_slice_sum(void)
{
    uint32_t s;
    make_flat(0x00, 0x00);
    for (s = 0; s < GBP_ADEC2_SLICES_PER_BLOCK; s++) CHECK(gbp_adec2_slice_sum(blk, s) == 0u);
    make_flat(0xFF, 0xFF);
    for (s = 0; s < GBP_ADEC2_SLICES_PER_BLOCK; s++) CHECK(gbp_adec2_slice_sum(blk, s) == 512u);
    /* rest: a byte whose popcount is 4 on each stream -> wA = wB = 32*4 = 128, p = 256 */
    make_flat(0x0F, 0xF0);
    CHECK(popcount8(0x0F) == 4 && popcount8(0xF0) == 4);
    for (s = 0; s < GBP_ADEC2_SLICES_PER_BLOCK; s++) CHECK(gbp_adec2_slice_sum(blk, s) == 256u);
    /* only stream A's byte matters, not its neighbours in the group */
    memset(blk, 0, sizeof blk);
    blk[GBP_ADEC2_STREAM_A] = 0xFF;                 /* slice 0, group 0 only */
    CHECK(gbp_adec2_slice_sum(blk, 0) == 8u);
    CHECK(gbp_adec2_slice_sum(blk, 1) == 0u);
}

static void test_sample_formula(void)
{
    struct gbp_adec2 d;
    int16_t ring[16];
    gbp_adec2_init(&d, ring, 16);
    CHECK(gbp_adec2_sample(&d, 300u) == 0);              /* not calibrated: silence */
    make_flat(0x0F, 0xF0);                                /* p = 256 on every slice, sixteen of them */
    gbp_adec2_calibrate(&d, blk);
    CHECK(d.rest_n == 16u && d.rest_sum == 16 * 256);
    CHECK(d.rest_min == 256u && d.rest_max == 256u);
    CHECK(gbp_adec2_sample(&d, 256u) == 0);               /* silence decodes to zero */
    /* the same 0.125-of-range -> 80 %-of-full-scale ratio as gbp_adec's, at P_MAX = 512:
     * a deviation of 64 (0.125 * 512) -> 32767 * 64 / 80 = 26213.6 -> 26214 */
    CHECK(gbp_adec2_sample(&d, 256u + 64u) == 26214);
    CHECK(gbp_adec2_sample(&d, 256u - 64u) == -26214);
    /* clipping: the whole slice on both streams */
    CHECK(gbp_adec2_sample(&d, 512u) == 32767);
    CHECK(gbp_adec2_sample(&d, 0u) == -32767);
}

static void test_push_block_and_pop(void)
{
    struct gbp_adec2 d;
    int16_t ring[32];
    uint32_t i;
    gbp_adec2_init(&d, ring, 32);
    make_flat(0x0F, 0xF0);
    gbp_adec2_calibrate(&d, blk);
    CHECK(gbp_adec2_push_block(&d, blk) == 16u);          /* all sixteen slices at rest */
    CHECK(d.blocks_in == 1u && d.count == 16u);
    for (i = 0; i < 16u; i++) {
        int16_t s;
        CHECK(gbp_adec2_pop(&d, &s) == 1 && s == 0);
    }
    CHECK(d.count == 0u);
    CHECK(gbp_adec2_pop(&d, &ring[0]) == 0);              /* empty */
}

static void test_overflow_is_counted_per_sample(void)
{
    struct gbp_adec2 d;
    int16_t ring[10];                                     /* smaller than one block's 16 samples */
    gbp_adec2_init(&d, ring, 10);
    make_flat(0x0F, 0xF0);
    gbp_adec2_calibrate(&d, blk);
    CHECK(gbp_adec2_push_block(&d, blk) == 10u);           /* only 10 of the 16 fit */
    CHECK(d.overflow == 6u && d.count == 10u);
}

static void test_lost_holds_the_previous_sample_sixteen_times(void)
{
    struct gbp_adec2 d;
    int16_t ring[64];
    uint32_t i;
    gbp_adec2_init(&d, ring, 64);
    make_flat(0x0F, 0xF0);
    gbp_adec2_calibrate(&d, blk);
    make_flat(0xFF, 0xFF);                                 /* full scale */
    CHECK(gbp_adec2_push_block(&d, blk) == 16u);
    CHECK(gbp_adec2_push_lost(&d) == 16u);
    CHECK(d.lost == 1u && d.count == 32u);
    for (i = 0; i < 32u; i++) {
        int16_t s;
        CHECK(gbp_adec2_pop(&d, &s) == 1 && s == 32767);   /* the held sample, sixteen extra times */
    }
}

static void test_discard(void)
{
    struct gbp_adec2 d;
    int16_t ring[32];
    gbp_adec2_init(&d, ring, 32);
    make_flat(0x0F, 0xF0);
    gbp_adec2_calibrate(&d, blk);
    gbp_adec2_push_block(&d, blk);
    CHECK(gbp_adec2_discard(&d, 5u) == 5u && d.count == 11u && d.discarded == 5u);
    CHECK(gbp_adec2_discard(&d, 100u) == 11u && d.count == 0u && d.discarded == 16u);
}

int main(void)
{
    test_slice_sum();
    test_sample_formula();
    test_push_block_and_pop();
    test_overflow_is_counted_per_sample();
    test_lost_holds_the_previous_sample_sixteen_times();
    test_discard();
    fprintf(stderr, "%d checks, %d failures\n", checks, failures);
    return failures != 0;
}
