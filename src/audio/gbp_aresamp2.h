/*
 * gbp_aresamp2 — 65 536 Hz -> 32 000 Hz, Round B's native decode rate (GitHub Issue #126).
 *
 * A NEW PATH, NOT A MOVED DEFAULT: gbp_aresamp.[ch] (4096 -> 32 000 Hz) is untouched, and every
 * frozen image still uses it. This module is the same ENGINE (the push-driven integer phase
 * accumulator of gbp_aresamp.c, unchanged in structure) run at a different ratio and against a
 * different, independently settled coefficient table.
 *
 * EXACT, BY CONSTRUCTION, the same way: 32000 * 256 == 65536 * 125 (both 8 192 000). L = 125,
 * M = 256. Unlike the 4096 Hz path, THIS IS A NET DOWNSAMPLE (L < M): the same accumulator loop
 * (`while (acc < L) { emit; acc += M; } acc -= L;`) then emits AT MOST ONE output per push, since
 * M >= L means a single `acc += M` already exceeds L. Over a full 256-push period (256 and 125 are
 * coprime) the accumulator visits all 125 phases exactly once and returns to 0, so pushing a
 * multiple of 256 samples always leaves `acc` back at 0 — the same "acc == 0 at a chunk boundary"
 * property gbp_aplay2 relies on, generalised from gbp_aresamp's own 16-push period.
 *
 * THE FILTER: 16 taps a phase, Kaiser beta 4.0, cutoff at the OUTPUT'S Nyquist (16 000 Hz, the
 * lower of the two rates) — GBP-HW-351's registered choice, settled against both 32-tap candidates
 * on RUN 33, RUN 34 and RUN 43. `tools/gen_aresamp2.py` builds the table from
 * `tools/v124taps.py`'s own `kernel()`, the exact construction #124 measured, not a rederivation.
 * Q15, every phase summing to exactly 32768 (tests/host/test_resampler_tables.py).
 *
 * LATENCY: 8 input samples at 65 536 Hz (122.1 us) — a sixteenth of the 4096 Hz path's 1.95 ms,
 * since the kernel spans the same 16 taps at 16x the rate. History starts at zero (silence).
 *
 * Integer only, no allocation, no blocking call.
 */
#ifndef OPENGBP_GBP_ARESAMP2_H
#define OPENGBP_GBP_ARESAMP2_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_ARESAMP2_MAX_OUT 1u          /* L < M: at most one output per push (a net downsample) */

struct gbp_aresamp2 {
    int16_t  hist[16];                  /* the last 16 inputs, a ring (GBP_ARESAMP2_TAPS == 16) */
    uint32_t hpos;                      /* where the NEXT input goes */
    uint32_t acc;                       /* next output's phase, in 1/125 of an input sample */
    uint32_t in_count, out_count;
};

void gbp_aresamp2_init(struct gbp_aresamp2 *r);

/* Push one 65 536 Hz sample; writes 0 or 1 32 kHz samples to out (room for
 * GBP_ARESAMP2_MAX_OUT) and returns how many. */
uint32_t gbp_aresamp2_push(struct gbp_aresamp2 *r, int16_t in, int16_t *out);

#ifdef __cplusplus
}
#endif
#endif
