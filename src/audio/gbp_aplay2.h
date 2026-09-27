/*
 * gbp_aplay2 — Round B's drift-correction layer (GitHub Issue #126): gbp_adec2's ring -> counted
 * clock correction -> gbp_aresamp2 -> an output ring of int16 PCM at 32 000 Hz.
 *
 * A NEW PATH, NOT A MOVED DEFAULT, AND DELIBERATELY NARROWER THAN gbp_aplay.[ch]. This module
 * ports gbp_aplay's PRODUCER-SIDE correction algorithm byte-for-byte (the chunk/sub-block decision
 * logic Round A's three review rounds settled, GBP-HW-349) at the new rate and k. It does NOT
 * port the AI-chunk pool, the READY hand-off queue, the IRQ callback, L2's CRC sidecar or the
 * mute/discard primitives: those are DEVICE-INTEGRATION concerns (the AI DMA hand-off, an actual
 * embedded image) that Issue #126 explicitly puts out of scope ("No image, no staging, no
 * hardware... image build and staging... gets its own Issue once this validates"). What is ported
 * is exactly what a HOST validation of the decode + resample + drift chain needs: a stream of
 * output samples, with the same counted-DUP/DROP bookkeeping, that a host test can check for
 * conservation and reproducibility. When that later Issue opens, THIS is the layer to fold the
 * pool/queue/L2/mute machinery back onto, the same way gbp_aplay.c already has it.
 *
 * THE CHUNK: 2048 input pushes (128 x 16, GBP-HW-349's k = rate / 4096) resample to EXACTLY 1000
 * output frames (2048 x 125 / 256 = 1000), and 2048 is a multiple of gbp_aresamp2's 256-push
 * period, so the resampler's accumulator is back at 0 at every chunk boundary — the same
 * precondition gbp_aplay.c's L2 relies on, ported here as a property a host test can check
 * directly on `rs.acc`.
 *
 * THE CORRECTION: counted DUP/DROP, at most k = GBP_APLAY2_K_DEFAULT (16) a chunk by default,
 * spread one per sub-block of PUSHES / k = 128 pushes — the SAME 128-sample sub-block gbp_aplay's
 * k = 1 default corrects a whole chunk at, since both scale together (GBP-HW-349: the same total
 * per-chunk envelope, 244.1 us, spread over sixteen 15.259 us corrections instead of one).
 * `gbp_aplay_set_corrections`'s constraints carry over unchanged (k divides PUSHES, at most half of
 * it). THE ARCHITECTURE QUESTION (counted corrections vs a resampling ratio steered from the fill
 * or from measured clocks) STAYS OPEN (`GBP-HW-349`/`GBP-HW-350` on top, #125): this module keeps
 * counted corrections, as fixed for this round, and decides nothing about the alternative.
 *
 * THE CUSHION: 0.125 s in TIME (GBP_APLAY2_CUSHION_US, the same value gbp_aplay.h holds),
 * recomputed in THIS path's sample rate — 8192 samples at 65 536 Hz. PROVISIONAL, same as
 * gbp_aplay.h's: re-validated on this path only once a hardware run exists (§V28, out of scope
 * here).
 *
 * No floating point, no allocation, no blocking call, no device.
 */
#ifndef OPENGBP_GBP_APLAY2_H
#define OPENGBP_GBP_APLAY2_H

#include <stdint.h>

#include "gbp_adec2.h"
#include "gbp_aresamp2.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_APLAY2_FRAMES        1000u    /* per chunk, output domain (32 000 Hz), unchanged */
#define GBP_APLAY2_PUSHES        2048u    /* per chunk, input domain: 128 x 16 (GBP-HW-349) */
#define GBP_APLAY2_K_DEFAULT       16u    /* k = rate / 4096 = 65536 / 4096 (GBP-HW-349), this path's default */
#define GBP_APLAY2_CUSHION_US   125000u   /* the same adopted cushion, in time (gbp_aplay.h, GBP-HW-343); PROVISIONAL
                                            * on this path until re-validated by a hardware run (out of scope, #126) */
#define GBP_APLAY2_TARGET       ((uint32_t)(((uint64_t)GBP_ADEC2_RATE * GBP_APLAY2_CUSHION_US) / 1000000u))  /* 8192 */
#define GBP_APLAY2_BAND           256u    /* 16 x gbp_aplay's BAND: the same 3.906 ms width, at the new rate */
/* documented convention for gbp_adec2's ring, mirroring gbp_aplay.h's GBP_APLAY_RING: 1 s of
 * decoded samples at this rate. 16x the memory of the 4096 Hz path's ring; the budget for an
 * actual image is a question for the hardware-integration Issue, not this one. */
#define GBP_APLAY2_RING         65536u
#define GBP_APLAY2_TARGET_MIN   GBP_APLAY2_PUSHES        /* a chunk must be able to start */
#define GBP_APLAY2_TARGET_MAX   (GBP_APLAY2_RING - GBP_APLAY2_BAND - 1u)

#define GBP_APLAY2_EV_DUP     1u
#define GBP_APLAY2_EV_DROP    2u

struct gbp_aplay2 {
    struct gbp_aresamp2 rs;
    uint32_t corr_per_chunk;                   /* k, read once at each chunk's start */
    uint32_t target;                           /* the fill the corrections hold; GBP_APLAY2_TARGET after init */
    uint8_t  playing;                          /* the caller's: before playback a chunk takes at most one
                                                 * correction, the same rule gbp_aplay.c applies */
    /* the chunk being produced */
    uint8_t  started;                          /* 1 while a chunk is in progress */
    uint32_t cur_pushes;
    uint32_t cur_corr;
    uint8_t  cur_corr_done;
    uint32_t cur_k;
    uint32_t cur_s0;
    uint32_t cur_target;
    uint32_t cur_sub;
    uint32_t cur_taken;
    uint8_t  cur_uncorrected;
    /* the output ring: caller-provided storage, never allocated here */
    int16_t *ring;
    uint32_t cap, head, count;
    /* what happened, never silent */
    uint32_t produced, dup, drop, starved_steps;
    uint32_t corr_forgone;                     /* Issue #124's counter, ported unchanged (GBP-HW-349) */
    uint32_t out_overflow;                     /* the caller's output ring was full: a host-harness sizing error,
                                                 * counted rather than silently dropped (mirrors gbp_adec2's own
                                                 * ring_put2 overflow counter, review round, #126) */
};

void gbp_aplay2_init(struct gbp_aplay2 *p, int16_t *out_ring, uint32_t out_cap);

/* k must divide GBP_APLAY2_PUSHES and be at most half of it (a DUP is two pushes). 0 on success,
 * -1 (nothing changed) otherwise. Takes effect from the next chunk that starts. */
int gbp_aplay2_set_corrections(struct gbp_aplay2 *p, uint32_t k);

/* Clamped to [GBP_APLAY2_TARGET_MIN, GBP_APLAY2_TARGET_MAX]. A chunk being produced keeps its
 * already-latched decision. */
void gbp_aplay2_set_target(struct gbp_aplay2 *p, uint32_t target);

/* Producer: pops from `d`'s ring, corrects, resamples, and pushes output frames into `p`'s ring.
 * At most `max_pushes` resampler pushes this call (0 means "the whole chunk in one call" — no
 * upper bound). Returns 1 when a chunk completed this call, 0 otherwise: either nothing was
 * popped because the ring was too short to start a chunk (GBP_APLAY2_PUSHES + 1 samples, one more
 * for a DROP; `starved_steps` counted) or a chunk is still in progress after `max_pushes`.
 * `uncorrected` mirrors gbp_aplay_produce_uncorrected: a transition's chunk takes no correction, at
 * exactly GBP_APLAY2_PUSHES pushes, and corrects nothing. */
int gbp_aplay2_produce_ex(struct gbp_aplay2 *p, struct gbp_adec2 *d, uint32_t max_pushes, int uncorrected);
int gbp_aplay2_produce(struct gbp_aplay2 *p, struct gbp_adec2 *d, uint32_t max_pushes);

/* Take the oldest output sample. 1, or 0 when the ring is empty. */
int gbp_aplay2_pop(struct gbp_aplay2 *p, int16_t *out);

#ifdef __cplusplus
}
#endif
#endif
