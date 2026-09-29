/*
 * gbp_v28_dma -- the AI DMA's HAND-OFF SEMANTICS, read at every callback's entry (GitHub Issue #139, U-GBP-049).
 *
 * WHY. tools/v28latency.py's L(T, A) counts AHEAD + 1 chunks in flight: AHEAD - 1 READY, the chunk PROGRAMMED at the last hand-off, the chunk that hand-off STARTED. That rests on
 * one assumption no run has measured: the DMA callback fires when the block programmed LAST time has just STARTED, and programs the next. If it were wrong every L would be a whole
 * chunk (31.2 ms) off. The callback reads the AI's start-address register and bytes-left counter at its ENTRY (before the hand-off, before AUDIO_InitDMA), and this module keeps what
 * those reads say against the chunks the previous two callbacks returned. NOTHING IS WRITTEN TO THE DEVICE and nothing here touches one: a callback hands it the two numbers.
 *
 * THE READINGS, pre-registered in HARDWARE_TESTS.md V28.23 (tools/v28latency.py dma_semantics() applies them):
 *   register == the chunk returned at the PREVIOUS callback, bytes left near 4 000   -> the block has just started: AHEAD + 1 (the table stands)
 *   register == the chunk returned TWO callbacks ago                                 -> AHEAD + 2 (every L +31.2 ms)
 *   register == the previous chunk, bytes left near 0                                -> the block has just FINISHED: AHEAD (every L -31.2 ms)
 * Two consecutive silences return the same buffer, so the pointers cannot tell those callbacks apart: they are counted apart (`same12`), never classified.
 *
 * Pure, bounded, no allocation, no printing, no floating point. Addresses are compared as the register holds them: the PHYSICAL address, 32-byte aligned (libogc's
 * AUDIO_GetDMAStartAddr: (reg24 & 0x1FFF) << 16 | (reg25 & 0xFFE0)); a chunk is 4 000 = 125 x 32 bytes and 32-byte aligned.
 */
#ifndef OPENGBP_GBP_V28_DMA_H
#define OPENGBP_GBP_V28_DMA_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_V28_DMA_RAW   32u        /* the first callbacks, kept raw */
#define GBP_V28_DMA_BINS   6u        /* bytes left: <1000, <2000, <3000, <3500, <4000, >= 4000 */

struct gbp_v28_dma_raw { uint32_t addr, left, ret1, ret2, dt; };

struct gbp_v28_dma {
    uint32_t n, prev1, prev2, none, same12;
    uint32_t left_min, left_max;
    uint32_t bins[GBP_V28_DMA_BINS];
    uint32_t raw_n;
    uint32_t ret1, ret2;         /* the physical addresses the last two callbacks returned (ret1 the last) */
    uint32_t seeded;
    uint64_t left_sum, t_last;
    struct gbp_v28_dma_raw raw[GBP_V28_DMA_RAW];
};

void gbp_v28_dma_init(struct gbp_v28_dma *d);

/* The AI's register form of a buffer's address. */
uint32_t gbp_v28_dma_phys(const void *p);

/* The first chunk, programmed by the pump slot's own hand-off before the DMA is started: what the FIRST callback should find in the register. */
void gbp_v28_dma_seed(struct gbp_v28_dma *d, const void *first);

/* One callback: `addr` and `left` are the two register reads at its ENTRY, `t` its time (ticks), `returned` the chunk the hand-off returned (to be programmed next). */
void gbp_v28_dma_note(struct gbp_v28_dma *d, uint32_t addr, uint32_t left, uint64_t t, const void *returned);

#ifdef __cplusplus
}
#endif
#endif
