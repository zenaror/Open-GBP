/*
 * gbp_vsig.h — the per-block VIDEO signature of GBP-VIDEO-002, the two
 * frame-start predicates, and the bounded cost instrumentation of the
 * signature itself.
 *
 * Normative description: docs/research/HARDWARE_TESTS.md "GBP-VIDEO-002"
 * §6 (the signature), §8 (the cost measurement), §13 (segmentation).
 *
 * THE SIGNATURE IS OURS, COMPUTED FROM OUR BYTES. It is the per-block
 * checksum GBI's video service thread computes (`FUN_8000BF30`), applied to
 * the blocks WE captured: for each group of four raw bytes it consumes
 * **byte 1 and byte 3** and nothing else, packs two consecutive pixels into
 * one 32-bit word, accumulates 240 such pairs in 64 bits and stores the low
 * 32 bits PLUS the carry count. No reference table, no reference checksum
 * and no reference pixel is embedded here or anywhere in the runtime; the
 * comparison against the Start-up Disc's embedded frame and GBI's tables
 * happens OFFLINE, in tools/avseq.py, from the private inputs.
 *
 * Why byte 0 cannot forge a change: bytes 0 and 2 are never read, so the
 * byte-0 exceptions GBP-HW-070 measured (688 words in 84 480) cannot produce
 * a structured-change false positive. That is a property of the algorithm,
 * not a tuning choice, and tests/unit/test_gbp_vsig.c pins it.
 *
 * The frame-start bit lives in byte 1 of the block's first word, so it is
 * inside the checksum by construction (0xFFFF versus 0x7FFF took block 0
 * from 0xFF0FFF0F to 0x7F0FFF10 in the physical run). Within a frame block 0
 * always carries it, so a frame-to-frame comparison at the same block
 * position sees it consistently on both sides and it can never by itself
 * mark a frame as changed.
 *
 * Nothing here touches the transport, allocates, logs or blocks.
 */
#ifndef OPENGBP_GBP_VSIG_H
#define OPENGBP_GBP_VSIG_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* One VIDEO block: 0xF00 bytes = 240 groups of four 32-bit pixel words. */
#define GBP_VSIG_BLOCK_SIZE 0x0F00u
#define GBP_VSIG_GROUPS 240u
/* GBI's frame-start test on the first 32-bit word: bit 7 of byte 0 AND byte 1. */
#define GBP_VSIG_GBI_MASK 0x80800000u

/* The per-block signature over the semantic payload only (bytes 1 and 3).
 * `len` must be GBP_VSIG_BLOCK_SIZE; a shorter block returns 0 and is never
 * silently padded. */
uint32_t gbp_vsig_block(const uint8_t *raw, uint32_t len);

/* The two frame-start predicates, from the raw first four bytes, never
 * corrected (docs/research/VIDEO_PATH.md §5):
 *   GBI  : (u32_be(first4) & 0x80800000) == 0x80800000   — bit 7 of bytes 0 AND 1
 *   Disc : ((u16_be(first4[0..1]) >> 7) & 1) != 0        — bit 7 of byte 1
 * GBI implies Disc by construction, so the only informative disagreement is
 * Disc = 1 with GBI = 0: byte 1 carries the bit and byte 0 does not. */
int gbp_vsig_flag_gbi(const uint8_t first4[4]);
int gbp_vsig_flag_disc(const uint8_t first4[4]);

/*
 * Cost instrumentation (§8): the measurement is mandatory, the threshold is
 * not — a previous revision required "p95 below 25 % of the median lean
 * cycle" and that number was withdrawn for having no physical basis. What is
 * required is min, median, p95 and max over at least 10 000 blocks, with no
 * per-block record: 269 000 samples must never become 269 000 stored values.
 *
 * Median and p95 are NEVER derived from the mean. They come from a bounded
 * histogram with exact linear buckets below `GBP_VSIG_HIST_LINEAR` ticks
 * (one bucket per tick, so any quantile inside that range is exact to one
 * tick) and geometric buckets above it, plus an explicit overflow bucket.
 * The reported quantile carries its own resolution, so a reader can see
 * whether it is exact (`q_exact = 1`) or the width of the bucket it fell in.
 * Memory: GBP_VSIG_HIST_BUCKETS u32 counters = 1 KiB, fixed.
 */
#define GBP_VSIG_HIST_LINEAR 192u     /* ticks 0..191 get one exact bucket each */
#define GBP_VSIG_HIST_GEOM 64u        /* buckets above that, each twice as wide as a step allows */
#define GBP_VSIG_HIST_BUCKETS (GBP_VSIG_HIST_LINEAR + GBP_VSIG_HIST_GEOM)

struct gbp_vsig_cost {
    uint64_t count;        /* samples taken */
    uint64_t sum;          /* total ticks (for the mean, which is reported but never used for a quantile) */
    uint32_t min, max;
    uint32_t overflow;     /* samples beyond the last bucket's upper bound (still counted in count/sum/max) */
    uint32_t buckets[GBP_VSIG_HIST_BUCKETS];
};

void gbp_vsig_cost_init(struct gbp_vsig_cost *c);
void gbp_vsig_cost_add(struct gbp_vsig_cost *c, uint32_t ticks);
/* Lower and upper tick bound (inclusive) of bucket `i`; 0/0 when i is out of range. */
void gbp_vsig_cost_bucket_range(unsigned i, uint32_t *lo, uint32_t *hi);
/* Which bucket a sample falls in (GBP_VSIG_HIST_BUCKETS when it overflows). */
unsigned gbp_vsig_cost_bucket_of(uint32_t ticks);
/* The quantile at permille `q` (500 = median, 950 = p95), as the upper bound of the bucket that
 * contains it. `*exact` (optional) is 1 when that bucket is one tick wide, else 0, and `*width`
 * (optional) receives the bucket's width in ticks. Returns 0 with *exact = 0 when count == 0. */
uint32_t gbp_vsig_cost_quantile(const struct gbp_vsig_cost *c, unsigned permille, int *exact, uint32_t *width);
/* Mean in ticks (integer), reported alongside the quantiles and never substituted for them. */
uint32_t gbp_vsig_cost_mean(const struct gbp_vsig_cost *c);

#ifdef __cplusplus
}
#endif
#endif
