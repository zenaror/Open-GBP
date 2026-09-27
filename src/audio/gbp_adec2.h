/*
 * gbp_adec2 — the Game Boy Player's AUDIO window, decoded PER SLICE, PER STREAM, at 65 536 Hz
 * nominal (GitHub Issue #126, Round B). A NEW PATH, NOT A MOVED DEFAULT: gbp_adec.[ch] (one
 * value per 4096-byte BLOCK, 4096 Hz) is untouched, and every frozen image still uses it.
 *
 * THE LAYOUT (GBP-HW-347, `tools/v123frame.py`). A 4096-byte AUDIO block is sixteen 256-byte
 * SLICES; a slice is 32 groups of 8 bytes. Stream j of a slice is byte j of every group. Streams
 * 1 and 3 carry the SAME bits (called A here, read at byte offset 3); streams 5 and 7 carry the
 * same bits too (B, byte offset 7) -- `GBP-AUD-002`/`GBP-AUD-003`'s reading of both reference
 * implementations agrees on exactly these two streams and no others. wA and wB are each stream's
 * one-bit COUNT over its slice's 32 bytes, 0..256; both rest near 128 at silence (independently
 * corroborated by GBI's centred popcount, `GBP-AUD-004`).
 *
 * THE DECODE (Round A Decision 1, `GBP-HW-351`, kept unchanged by #125/#126): per slice,
 * p = wA + wB, SUMMED BEFORE THE RESAMPLER -- mono, one combined value a slice, 0..512, resting
 * near 256. `GBP_ADEC2_RATE` = 65 536, sixteen values a block, matching gbp_aresamp2's input rate
 * exactly. Stereo (A and B kept apart) is a later parameter, OFF this round (U-GBP-047 unsettled;
 * out of scope, GitHub Issue #126).
 *
 * THE GAIN (a Round B design decision, not fixed by the Issue, so recorded here). It PRESERVES
 * gbp_adec's own sensitivity ratio exactly -- "a deviation of 0.125 of the full range maps to 80 %
 * of full scale", 6.4 -- so a listening comparison changes the DECODE RATE only, never the
 * loudness. gbp_adec's full range is 32768 (one whole 4096-byte block's bits); this decoder's is
 * 512 (wA + wB's maximum). 32768 / 6.4 = 5120 (gbp_adec's own denominator, per calibration
 * sample); 512 / 6.4 = 80 exactly, so:
 *
 *     sample = round_half_even( (n*p - S) * 32767 / (80 * n) ),  clipped to +-32767
 *
 * with n the calibration span's SLICE count and S its summed p. Silence (p == rest mean)
 * decodes to 0, exactly as gbp_adec's formula does at its own rest mean.
 *
 * RULES FOR CODE THAT WILL ONE DAY SIT IN A DRAIN PATH (CLAUDE.md §13, §22): fixed-width integers
 * only, NO FLOATING POINT, NO ALLOCATION -- the output ring is caller-provided storage -- and no
 * call that can block. A full ring DROPS the newest sample and counts it (`overflow`, per SAMPLE,
 * not per block); a block the drain lost is replaced by sixteen HOLDs of the previous sample and
 * counted (`lost`), so the 65 536 Hz timebase is kept, the same design gbp_adec.c uses at 4096 Hz.
 */
#ifndef OPENGBP_GBP_ADEC2_H
#define OPENGBP_GBP_ADEC2_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_ADEC2_BLOCK_BYTES 4096u
#define GBP_ADEC2_SLICE_BYTES 256u
#define GBP_ADEC2_SLICES_PER_BLOCK (GBP_ADEC2_BLOCK_BYTES / GBP_ADEC2_SLICE_BYTES)   /* 16 */
#define GBP_ADEC2_GROUP_BYTES  8u
#define GBP_ADEC2_STREAM_A     3u        /* byte offset of stream A within an 8-byte group */
#define GBP_ADEC2_STREAM_B     7u        /* byte offset of stream B within an 8-byte group */
#define GBP_ADEC2_P_MAX        512u      /* wA + wB, each 0..256 */
#define GBP_ADEC2_GAIN_DENOM    80u      /* P_MAX / 6.4, gbp_adec's own sensitivity ratio preserved */
#define GBP_ADEC2_RATE      65536u       /* decoded samples per second, nominal (U-GBP-041) */
#define GBP_ADEC2_FULL      32767

struct gbp_adec2 {
    /* the calibration span: summed p and how many SLICES it covers */
    int64_t  rest_sum;
    uint32_t rest_n;
    uint32_t rest_min, rest_max;         /* per-slice, reported and never used, as gbp_adec's are */
    /* the output ring: caller-provided storage, never allocated here */
    int16_t *ring;
    uint32_t cap, head, count;
    int16_t  last;                       /* the previous sample, held for a lost block's 16 slices */
    /* what happened, never silent */
    uint32_t blocks_in;                  /* blocks decoded (16 slices each) */
    uint32_t lost;                       /* blocks the drain lost (16 holds each) */
    uint32_t overflow;                   /* SAMPLES dropped because the ring was full */
    uint32_t clipped;                    /* decoded samples whose value before the clip lay outside +-FULL */
    uint32_t discarded;                  /* samples the consumer dropped from the ring's head on purpose */
};

/* Pure: wA + wB for slice `slice` (0..15) of a 4096-byte block, 0..512. */
uint32_t gbp_adec2_slice_sum(const uint8_t *block, uint32_t slice);

void gbp_adec2_init(struct gbp_adec2 *d, int16_t *ring, uint32_t cap);

/* Calibration: add all sixteen slices of one silent block to the resting level. */
void gbp_adec2_calibrate(struct gbp_adec2 *d, const uint8_t *block);

/* Pure: the PCM sample for a slice sum p, given the calibration. 0 when not calibrated. */
int16_t gbp_adec2_sample(const struct gbp_adec2 *d, uint32_t p);

/* Decode one drained block's sixteen slices into the ring, oldest slice first. Returns how many of
 * the sixteen were pushed (0..16); fewer than 16 means the ring filled partway through, each miss
 * counted in `overflow`. A sample the formula took past full scale is clipped and counted in
 * `clipped`, exactly as gbp_adec2_sample() clips it. */
uint32_t gbp_adec2_push_block(struct gbp_adec2 *d, const uint8_t *block);

/* The drain lost a block: hold the previous sample sixteen times so the timebase is kept. Same
 * return convention as push_block. */
uint32_t gbp_adec2_push_lost(struct gbp_adec2 *d);

/* Take the oldest sample. 1, or 0 when the ring is empty. */
int gbp_adec2_pop(struct gbp_adec2 *d, int16_t *out);

/* Drop the oldest min(n, count) samples without reading them; `discarded` counts them. */
uint32_t gbp_adec2_discard(struct gbp_adec2 *d, uint32_t n);

#ifdef __cplusplus
}
#endif
#endif
