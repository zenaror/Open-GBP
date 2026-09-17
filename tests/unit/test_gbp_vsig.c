/*
 * test_gbp_vsig.c — the GBP-VIDEO-002 semantic signature, the two frame-start
 * predicates, the bounded cost instrumentation and the 64-bit time base.
 *
 * Every scenario here is SYNTHETIC. The one physical anchor is the checksum
 * value 0x7F0FFF10, which GBP-AV-SERVICE-001's real block produces and which
 * docs/research/VIDEO_PATH.md §6 records; it is reproduced here from bytes we
 * construct, not from any reference data.
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>

#include "gbp_vsig.h"
#include "gbp_time64.h"

static unsigned checks, failures;

static void ok(int cond, const char *what)
{
    checks++;
    if (!cond) { failures++; printf("  FAIL %s\n", what); }
}

static void eq_u32(uint32_t got, uint32_t want, const char *what)
{
    checks++;
    if (got != want) { failures++; printf("  FAIL %s: got %08x want %08x\n", what, got, want); }
}

static void eq_u64(uint64_t got, uint64_t want, const char *what)
{
    checks++;
    if (got != want) { failures++; printf("  FAIL %s: got %016llx want %016llx\n", what,
                                          (unsigned long long)got, (unsigned long long)want); }
}

/* ---- a synthetic VIDEO block in the shape the physical ones had ------- */
static uint8_t blk[GBP_VSIG_BLOCK_SIZE];

/* `hh hh ll ll` per pixel word: the doubled layout both references read as byte 1 : byte 3. */
static void fill_uniform(uint8_t *b, uint8_t hi, uint8_t lo, int flag)
{
    uint32_t k;
    for (k = 0; k < GBP_VSIG_BLOCK_SIZE; k += 4u) {
        b[k] = hi; b[k + 1] = hi; b[k + 2] = lo; b[k + 3] = lo;
    }
    if (flag) { b[0] = 0xFF; b[1] = 0xFF; }     /* bit 7 of bytes 0 and 1: both predicates true */
}

static void test_signature_physical_anchor(void)
{
    uint32_t with_flag, without;
    printf("-- signature: the physically anchored all-white values\n");
    fill_uniform(blk, 0x7F, 0xFF, 0);
    without = gbp_vsig_block(blk, sizeof blk);
    fill_uniform(blk, 0x7F, 0xFF, 1);
    with_flag = gbp_vsig_block(blk, sizeof blk);
    /* The two values GBP-VIDEO-001 reproduced from its physical blocks and which
     * VIDEO_PATH.md §6 records as entries 1 and 0 of both reference tables. */
    eq_u32(without, 0xFF0FFF0Fu, "all-white block without the frame flag");
    eq_u32(with_flag, 0x7F0FFF10u, "all-white block with the frame flag (the physical anchor)");
    ok(with_flag != without, "the frame-start bit is inside the checksum by construction");
    eq_u32(gbp_vsig_block(blk, 16u), 0u, "a short block signs to 0 and is never padded");
    eq_u32(gbp_vsig_block(0, sizeof blk), 0u, "a null block signs to 0");
}

static void test_byte0_cannot_forge_a_change(void)
{
    uint32_t base, altered;
    uint32_t k, touched = 0;
    printf("-- signature: byte 0 is never read, byte 2 never substitutes byte 3\n");
    fill_uniform(blk, 0x7F, 0xFF, 1);
    base = gbp_vsig_block(blk, sizeof blk);
    /* every byte 0 of every pixel word gets the extra bit GBP-HW-070 measured */
    for (k = 0; k < GBP_VSIG_BLOCK_SIZE; k += 4u) { blk[k] ^= 0x80u; touched++; }
    altered = gbp_vsig_block(blk, sizeof blk);
    eq_u32(altered, base, "960 byte-0 changes leave the signature identical");
    ok(touched == 960u, "all 960 pixel words were touched");
    /* byte 2 likewise */
    fill_uniform(blk, 0x7F, 0xFF, 1);
    for (k = 2; k < GBP_VSIG_BLOCK_SIZE; k += 4u) blk[k] ^= 0x5Au;
    eq_u32(gbp_vsig_block(blk, sizeof blk), base, "byte-2 changes leave the signature identical");
    /* byte 1 and byte 3 DO change it — otherwise the signature would detect nothing */
    fill_uniform(blk, 0x7F, 0xFF, 1);
    blk[5] ^= 0x01u;
    ok(gbp_vsig_block(blk, sizeof blk) != base, "a single byte-1 change alters the signature");
    fill_uniform(blk, 0x7F, 0xFF, 1);
    blk[7] ^= 0x01u;
    ok(gbp_vsig_block(blk, sizeof blk) != base, "a single byte-3 change alters the signature");
    /* the carry fold is real: an all-0xFF payload overflows 32 bits many times */
    fill_uniform(blk, 0xFF, 0xFF, 0);
    ok(gbp_vsig_block(blk, sizeof blk) != 0u, "a saturated block folds its carries rather than wrapping to 0");
}

static void test_predicates(void)
{
    uint8_t f[4];
    printf("-- the two frame-start predicates, from the raw first four bytes\n");
    f[0] = 0x7F; f[1] = 0x7F; f[2] = 0xFF; f[3] = 0xFF;
    ok(!gbp_vsig_flag_gbi(f) && !gbp_vsig_flag_disc(f), "no flag: both predicates false");
    f[0] = 0xFF; f[1] = 0xFF;
    ok(gbp_vsig_flag_gbi(f) && gbp_vsig_flag_disc(f), "both bytes set: both predicates true");
    f[0] = 0x7F; f[1] = 0xFF;
    ok(!gbp_vsig_flag_gbi(f) && gbp_vsig_flag_disc(f), "byte 1 only: Disc true, GBI false (the informative case)");
    f[0] = 0xFF; f[1] = 0x7F;
    ok(!gbp_vsig_flag_gbi(f) && !gbp_vsig_flag_disc(f), "byte 0 only: BOTH false — byte 0 never decides");
    /* GBI implies Disc, exhaustively over the two bytes that matter */
    {
        unsigned a, b, violations = 0;
        for (a = 0; a < 256u; a++) {
            for (b = 0; b < 256u; b++) {
                uint8_t g[4];
                g[0] = (uint8_t)a; g[1] = (uint8_t)b; g[2] = 0; g[3] = 0;
                if (gbp_vsig_flag_gbi(g) && !gbp_vsig_flag_disc(g)) violations++;
            }
        }
        eq_u32(violations, 0u, "GBI implies Disc over all 65536 byte pairs");
    }
}

static void test_cost_histogram(void)
{
    struct gbp_vsig_cost c;
    unsigned i;
    int exact = 0;
    uint32_t width = 0, q;
    printf("-- cost instrumentation: bounded, exact where it matters, no invented threshold\n");
    gbp_vsig_cost_init(&c);
    eq_u32(gbp_vsig_cost_quantile(&c, 500u, &exact, &width), 0u, "an empty histogram reports 0");
    ok(exact == 0, "and says so rather than claiming exactness");
    /* 10 001 samples: 10 000 at 40 ticks and one at 5000 — median must be 40, p95 must be 40,
     * max 5000. A mean would be 40.5; the point is that the quantiles come from the histogram. */
    for (i = 0; i < 10000u; i++) gbp_vsig_cost_add(&c, 40u);
    gbp_vsig_cost_add(&c, 5000u);
    eq_u64(c.count, 10001u, "every sample counted");
    eq_u32(c.min, 40u, "min");
    eq_u32(c.max, 5000u, "max");
    q = gbp_vsig_cost_quantile(&c, 500u, &exact, &width);
    eq_u32(q, 40u, "median from the histogram, not from the mean");
    ok(exact == 1 && width == 1u, "the median is exact to one tick in the linear range");
    q = gbp_vsig_cost_quantile(&c, 950u, &exact, &width);
    eq_u32(q, 40u, "p95 likewise");
    ok(gbp_vsig_cost_mean(&c) == 40u, "the mean is reported separately and is not a quantile");
    /* a spread that straddles the linear/geometric boundary */
    gbp_vsig_cost_init(&c);
    for (i = 0; i < 1000u; i++) gbp_vsig_cost_add(&c, i);
    q = gbp_vsig_cost_quantile(&c, 500u, &exact, &width);
    ok(q >= 499u && q <= 512u, "median of 0..999 lands in the right bucket");
    ok(width >= 1u, "and reports its own resolution");
    q = gbp_vsig_cost_quantile(&c, 1000u, &exact, &width);
    ok(q >= 999u, "the 100th percentile is at or above the largest sample");
    /* bucket ranges are consistent with membership */
    {
        unsigned bad = 0;
        for (i = 0; i < GBP_VSIG_HIST_BUCKETS; i++) {
            uint32_t lo = 0, hi = 0;
            gbp_vsig_cost_bucket_range(i, &lo, &hi);
            if (gbp_vsig_cost_bucket_of(lo) != i || gbp_vsig_cost_bucket_of(hi) != i) bad++;
            if (hi < lo) bad++;
        }
        eq_u32(bad, 0u, "every bucket's range agrees with the membership test");
    }
    ok(sizeof c.buckets == GBP_VSIG_HIST_BUCKETS * sizeof(uint32_t), "the histogram is a fixed 1 KiB, never a sample list");
    /* an overflow sample is counted and named, never silently dropped */
    gbp_vsig_cost_init(&c);
    gbp_vsig_cost_add(&c, 0xFFFFFFFFu);
    eq_u64(c.count, 1u, "an overflow sample still counts");
    eq_u32(c.overflow, 1u, "and is named as an overflow");
    eq_u32(c.max, 0xFFFFFFFFu, "max keeps the real value");
}

/* ---- the 64-bit time base -------------------------------------------- */
struct tb_script { uint32_t tbu[8]; uint32_t tbl[8]; unsigned i_u, i_l; };

static uint32_t tb_read(void *ctx, int which)
{
    struct tb_script *s = (struct tb_script *)ctx;
    if (which == GBP_TIME64_TBU) return s->tbu[s->i_u++ & 7u];
    return s->tbl[s->i_l++ & 7u];
}

static void test_time64(void)
{
    struct tb_script s;
    unsigned retries = 0;
    uint64_t v;
    printf("-- the 64-bit time base: composition, the low-word wrap, and the retry\n");
    ok(gbp_time64_compose(5u, 7u, 5u, &v) == 1, "a stable pair composes");
    eq_u64(v, ((uint64_t)5 << 32) | 7u, "and gives (tbu << 32) | tbl");
    ok(gbp_time64_compose(5u, 7u, 6u, 0) == 0, "a differing pair of TBU reads demands a retry");

    /* the carry: TBL wraps 0xFFFFFFFF -> 0x00000000 while TBU goes 3 -> 4.
     * The first attempt reads TBU=3, TBL=0 (already past the carry), TBU=4: rejected.
     * The retry reads 4, 0, 4: accepted, and the value is on the correct side. */
    memset(&s, 0, sizeof s);
    s.tbu[0] = 3u; s.tbu[1] = 4u; s.tbu[2] = 4u; s.tbu[3] = 4u;
    s.tbl[0] = 0x00000000u; s.tbl[1] = 0x00000000u;
    v = gbp_time64_read(tb_read, &s, &retries);
    eq_u64(v, ((uint64_t)4 << 32), "the carry is detected and the retry lands past it");
    ok(retries == 1u, "exactly one retry was needed");

    /* monotonicity and ordering across the wrap, which a u32 counter would destroy */
    {
        uint64_t before = gbp_time64_make(3u, 0xFFFFFFFFu);
        uint64_t after = gbp_time64_make(4u, 0x00000000u);
        ok(after > before, "0x3FFFFFFFF -> 0x400000000 is an increase in 64 bits");
        eq_u64(gbp_time64_delta(before, after), 1u, "the difference across the wrap is exactly one tick");
        eq_u32(gbp_time64_lo(before), 0xFFFFFFFFu, "low word before the wrap");
        eq_u32(gbp_time64_lo(after), 0x00000000u, "low word after the wrap");
        /* the truncated path, which the design forbids, really does regress */
        ok((uint32_t)gbp_time64_lo(after) < (uint32_t)gbp_time64_lo(before),
           "a truncated u32 path would see time go BACKWARDS across the same wrap");
        eq_u64(gbp_time64_delta(after, before), 0u, "a backwards difference reports 0, never a huge unsigned");
    }

    /* a reader that never settles is bounded, not an infinite loop */
    memset(&s, 0, sizeof s);
    s.tbu[0] = 1u; s.tbu[1] = 2u; s.tbu[2] = 3u; s.tbu[3] = 4u;
    s.tbu[4] = 5u; s.tbu[5] = 6u; s.tbu[6] = 7u; s.tbu[7] = 8u;
    v = gbp_time64_read(tb_read, &s, &retries);
    ok(retries == GBP_TIME64_MAX_RETRIES, "a broken reader stops at the retry bound");
    ok(v != 0u, "and still returns a real reading");

    /* the design's constants, in 64 bits */
    printf("-- the design's tick constants\n");
    eq_u64(gbp_time64_from_seconds(GBP_TIME64_NOMINAL_HZ, 180u), 7290000000ull,
           "180 s at 40.5 MHz = 7 290 000 000 ticks");
    ok(7290000000ull > 0xFFFFFFFFull, "the hard safety budget does NOT fit in 32 bits");
    eq_u64(gbp_time64_from_seconds(GBP_TIME64_NOMINAL_HZ, 120u), 4860000000ull,
           "120 s at 40.5 MHz = 4 860 000 000 ticks");
    ok(4860000000ull > 0xFFFFFFFFull, "the scientific target does not fit in 32 bits either");
    eq_u32(0xFFFFFFFFu / GBP_TIME64_NOMINAL_HZ, 106u, "a u32 tick counter wraps after 106 s");
    eq_u32(gbp_time64_seconds(GBP_TIME64_NOMINAL_HZ, 4860000000ull), 120u, "seconds conversion");
    eq_u32(gbp_time64_millis_part(GBP_TIME64_NOMINAL_HZ, 4860000000ull + 20250000ull), 500u, "milliseconds part");
    eq_u32(gbp_time64_to_ms(GBP_TIME64_NOMINAL_HZ, 4860000000ull), 120000u, "milliseconds conversion");
    ok(gbp_time64_reached(100u, 50u, 150u) == 1, "reached() at exactly the deadline");
    ok(gbp_time64_reached(100u, 50u, 149u) == 0, "reached() one tick before");
    ok(gbp_time64_reached(gbp_time64_make(3u, 0xFFFFFFF0u), 0x20u, gbp_time64_make(4u, 0x10u)) == 1,
       "reached() works across the low-word wrap");
}

/*
 * The measurement section 8 of the design requires: the per-block signature cost over at least
 * 10 000 blocks, reported as min, median, p95 and max, from the bounded histogram and NEVER from
 * the mean. There is no threshold, because the design withdrew the arbitrary 25 % gate: what is
 * required is the number, a with/without cadence comparison, and a reviewer.
 *
 * This is the HOST half, in host nanoseconds. The DOL half needs the real 40.5 MHz time base and
 * therefore real hardware; Dolphin's timing is not physical and is never presented as such. The
 * probe already records sig_ticks per cycle and min/median/p95/max in the sidecar header, so the
 * physical measurement needs no new code — only a run.
 */
static void bench_signature(void)
{
    static uint8_t blocks[8][GBP_VSIG_BLOCK_SIZE];
    struct gbp_vsig_cost c;
    unsigned i, k;
    uint32_t sink = 0;
    const unsigned N = 20000u;
    printf("-- benchmark: the per-block signature cost (HOST, nanoseconds; not a hardware figure)\n");
    for (i = 0; i < 8u; i++) fill_uniform(blocks[i], (uint8_t)(0x70u + i), (uint8_t)(0xF0u + i), (int)(i & 1u));
    gbp_vsig_cost_init(&c);
    for (i = 0; i < N; i++) {
        struct timespec a, b;
        uint32_t dt;
        clock_gettime(CLOCK_MONOTONIC, &a);
        sink ^= gbp_vsig_block(blocks[i & 7u], GBP_VSIG_BLOCK_SIZE);
        clock_gettime(CLOCK_MONOTONIC, &b);
        dt = (uint32_t)((b.tv_sec - a.tv_sec) * 1000000000ll + (b.tv_nsec - a.tv_nsec));
        gbp_vsig_cost_add(&c, dt);
    }
    {
        int em = 0, ep = 0;
        uint32_t wm = 0, wp = 0;
        uint32_t med = gbp_vsig_cost_quantile(&c, 500u, &em, &wm);
        uint32_t p95 = gbp_vsig_cost_quantile(&c, 950u, &ep, &wp);
        printf("   blocks=%u  min=%u  median=%u(exact=%d,w=%u)  p95=%u(exact=%d,w=%u)  max=%u  mean=%u  overflow=%u\n",
               N, c.min, med, em, wm, p95, ep, wp, c.max, gbp_vsig_cost_mean(&c), c.overflow);
        printf("   (nanoseconds on this host; 0xF00 bytes read as 240 groups of four words, bytes 1 and 3 only)\n");
        ok(c.count == N, "every sample was recorded");
        ok(c.min > 0u, "the measurement resolved a non-zero cost");
        ok(med > 0u, "the median comes from the histogram");
        ok(p95 >= med, "p95 is at or above the median");
        ok(c.max >= p95, "max is at or above p95");
        ok(sink != 0xFFFFFFFFu, "the results were consumed so the loop is not optimised away");
        /* the report is complete: that is the gate, not a number */
        ok(1, "NO THRESHOLD IS APPLIED: the 25 % gate was withdrawn for having no physical basis");
    }
    /* the histogram itself stays 1 KiB whatever the sample count */
    for (k = 0; k < 8u; k++) (void)blocks[k][0];
    eq_u32((uint32_t)sizeof c.buckets, GBP_VSIG_HIST_BUCKETS * 4u, "20 000 samples, still a fixed 1 KiB histogram");
}

int main(void)
{
    printf("== test_gbp_vsig (GBP-VIDEO-002 signature, predicates, cost, 64-bit time base)\n");
    test_signature_physical_anchor();
    test_byte0_cannot_forge_a_change();
    test_predicates();
    test_cost_histogram();
    test_time64();
    bench_signature();
    printf("%u checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
