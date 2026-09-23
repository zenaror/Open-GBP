/*
 * gbp_aperiod — the programmed tone's PERIOD, decoded one AUDIO block at a time
 * (GitHub Issue #84; `HARDWARE_TESTS.md` §V19.4, AMENDMENT 2 B4 and §V19.11
 * AMENDMENT 4 A4.7).
 *
 * TERMINOLOGY (§V19 AMENDMENT 1 A1): DMA GRANULE = 32 bytes, AUDIO BLOCK = 4096
 * bytes, a SLICE = 256 bytes (§V18). "block" unqualified is never used here.
 *
 * WHAT IT DOES. Each AUDIO block -- or the N bytes of it that were read -- is
 * reduced to ONE sample by the frozen formula of B4:
 *
 *     sample(N) = popcount(the N bytes read) * 4096 / N          (0 .. 32768)
 *
 * and the sample series is read by the SAME rule as the instrument
 * `GBP-HW-313` established the layout with (tools/v11sweep.py rising_edges):
 * a RISING EDGE is `prev <= 16384 < cur`, 16384 being RESTING_DUTY 0.5 of the
 * 32 768-bit full scale. A PERIOD is the number of AUDIO blocks between two
 * consecutive rising edges. Nothing is adaptive, so nothing can be tuned to a
 * run: silence has no swing, gives edges only by noise, and cannot produce a
 * run of identical periods of the programmed length.
 *
 * THE GATE'S RULE, AND ONLY IT (§V19.4): a stretch is exact when it counted at
 * least the caller's minimum of periods and every one equals the programmed
 * period (min == max == programmed). A4.7: a period counts only if BOTH its
 * edges fall inside the stretch, which is what a reset between stretches gives:
 * the first edge after a reset opens a period, it does not close one.
 *
 * BESIDE THE GATE, NEVER IN IT (AMENDMENT 1 A7): how many blocks show a step
 * WITHIN the bytes read -- two whole slices whose popcounts differ by more than
 * GBP_APERIOD_STEP_BITS -- against how many times the series crossed rest.
 * That ratio is `edge_recoverable`. A read shorter than two slices can show no
 * within-block step at all, and that is reported, not hidden.
 *
 * Pure: no device, no clock, no allocation, no floating point. It runs in the
 * drain image's audio tap, inside the service transaction, on the controls and
 * PHASE A only; its cost is one pass over the bytes read.
 */
#ifndef OPENGBP_GBP_APERIOD_H
#define OPENGBP_GBP_APERIOD_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_APERIOD_BLOCK       4096u
#define GBP_APERIOD_SLICE        256u
#define GBP_APERIOD_FULL       32768u    /* sample of an all-ones AUDIO block */
#define GBP_APERIOD_REST       16384u    /* RESTING_DUTY 0.5, v11sweep's, unchanged */
#define GBP_APERIOD_STEP_BITS     32u    /* A4.7: a within-block step, not a flat block's 1-3 bits */

struct gbp_aperiod {
    uint32_t expected;         /* the programmed period, in AUDIO blocks */
    uint32_t blocks;           /* blocks fed since the reset */
    int32_t  prev;             /* the previous sample, or -1 right after a reset */
    uint32_t last_edge;        /* index of the last rising edge (valid when have_edge) */
    uint8_t  have_edge;
    uint32_t edges;            /* rising edges */
    uint32_t periods;          /* intervals between two rising edges, both inside the stretch */
    uint32_t pmin, pmax;       /* valid when periods > 0 */
    uint32_t off;              /* periods that were NOT the programmed one */
    uint32_t crossings;        /* rest crossings, either direction */
    uint32_t steps_visible;    /* blocks whose read portion shows a within-block step */
    uint32_t refused;          /* blocks refused: no data or an illegal length */
    int32_t  last_sample;
};

/* Start a stretch: every counter to zero, and no edge carried over. */
void gbp_aperiod_reset(struct gbp_aperiod *p, uint32_t expected);

/* Feed the `n` bytes read of one AUDIO block. Returns the sample, or -1 when
 * the block is refused (NULL data, or `n` not a positive multiple of the DMA
 * granule no larger than one AUDIO block). */
int32_t gbp_aperiod_feed(struct gbp_aperiod *p, const uint8_t *data, uint32_t n);

/* §V19.4's rule: at least `min_periods` periods, and every one exactly the
 * programmed period. */
int gbp_aperiod_exact(const struct gbp_aperiod *p, uint32_t min_periods);

#ifdef __cplusplus
}
#endif
#endif
