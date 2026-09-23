/*
 * gbp_adec — the Game Boy Player's AUDIO window, decoded to PCM (Issue #81).
 *
 * THE LAYOUT (HARDWARE_TESTS §V17.2, GBP-HW-313): each 4096-byte AUDIO block
 * drained from the window is ONE sample, whose value is the number of one-bits
 * in the block. Samples arrive at 4096 per second. The resting level is the mean
 * one-bit count of a silent calibration span, subtracted so silence decodes to 0.
 *
 * THE OUTPUT is signed 16-bit PCM with ONE FIXED GAIN — a deviation of 0.125 of
 * the block (4096 one-bits) maps to 80 % of full scale — so this module and
 * tools/v17decode.py produce the SAME numbers. In integers, with p the block's
 * one-bit count, S the calibration span's summed count and n its length:
 *
 *     sample = round_half_even( (n*p - S) * 32767 / (5 * 1024 * n) ),  clipped to +-32767
 *
 * which is v17decode's  round((p/32768 - S/(32768 n)) * 6.4 * 32767)  with the
 * float removed. tests/host/test_audio_runtime.py checks bit-identity against
 * #80's WAVs on all eight windows of RUN 33 and RUN 34.
 *
 * RULES FOR CODE THAT WILL ONE DAY SIT IN A DRAIN PATH (CLAUDE.md §13, §22):
 * fixed-width integers only, NO FLOATING POINT, NO ALLOCATION — the output ring
 * is caller-provided storage — and no call that can block. A full ring DROPS the
 * newest sample and counts it (`overflow`); a block the drain lost is replaced by
 * a HOLD of the previous sample and counted (`lost`), so the 4096 Hz timebase is
 * kept. Whether the runtime can drain continuously at 4096 blocks/s is NOT
 * settled here (Issue #81, out of scope); these counters are how it will report.
 *
 * WHAT IS NOT DECIDED HERE: where a runtime gets its calibration span. The replay
 * backend uses the capture's own CONTROL window, as #80 did.
 */
#ifndef OPENGBP_GBP_ADEC_H
#define OPENGBP_GBP_ADEC_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_ADEC_BLOCK_BYTES 4096u
#define GBP_ADEC_BLOCK_BITS  (GBP_ADEC_BLOCK_BYTES * 8u)
#define GBP_ADEC_RATE        4096u        /* samples per second, GBP-HW-301 */
#define GBP_ADEC_FULL        32767

struct gbp_adec {
    /* the calibration span: summed one-bit count and how many blocks it covers */
    int64_t  rest_sum;
    uint32_t rest_n;
    /* the output ring: caller-provided storage, never allocated here */
    int16_t *ring;
    uint32_t cap, head, count;
    int16_t  last;                /* the previous sample, held for a lost block */
    /* what happened, never silent */
    uint32_t blocks_in;           /* blocks decoded */
    uint32_t lost;                /* blocks the drain lost, replaced by a hold */
    uint32_t overflow;            /* samples dropped because the ring was full */
};

/* Pure: the number of one-bits in one 4096-byte block, 0 .. 32768. */
uint32_t gbp_adec_popcount(const uint8_t *block);

void gbp_adec_init(struct gbp_adec *d, int16_t *ring, uint32_t cap);

/* Calibration: add one silent block to the resting level. */
void gbp_adec_calibrate(struct gbp_adec *d, const uint8_t *block);

/* Pure: the PCM sample for a one-bit count, given the calibration. 0 when the
 * decoder is not calibrated. */
int16_t gbp_adec_sample(const struct gbp_adec *d, uint32_t popcount);

/* Decode one drained block into the ring. 0, or -1 when the ring was full and
 * the sample was dropped (counted). */
int gbp_adec_push_block(struct gbp_adec *d, const uint8_t *block);

/* The drain lost a block: hold the previous sample so the timebase is kept. */
int gbp_adec_push_lost(struct gbp_adec *d);

/* Take the oldest sample. 1, or 0 when the ring is empty. */
int gbp_adec_pop(struct gbp_adec *d, int16_t *out);

#ifdef __cplusplus
}
#endif
#endif
