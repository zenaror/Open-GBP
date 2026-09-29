/*
 * gbp_v28_dma -- the AI DMA's HAND-OFF SEMANTICS, read at every callback's entry (GitHub Issue #139, U-GBP-049).
 *
 * WHY. tools/v28latency.py's L(T, A) counts AHEAD + 1 chunks in flight: AHEAD - 1 READY, the chunk PROGRAMMED at the last hand-off, the chunk that hand-off STARTED. That rests on
 * one assumption no run has measured: the DMA callback fires when the block programmed LAST time has just STARTED, and programs the next. If it were wrong every L would be a whole
 * chunk (31.2 ms) off. The callback reads the AI's start-address register and bytes-left counter at its ENTRY (before the hand-off, before AUDIO_InitDMA), and this module keeps what
 * those reads say against the chunks the previous two callbacks returned. The READS write nothing to the device and nothing here touches one: a callback hands it the numbers. (The one thing the callback writes differently is the LENGTH of a marked block, gbp_v28_dma_len() below, under GBP_V28_DMA_MARK in validation_run only.)
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
#define GBP_V28_DMA_MARKS 48u        /* the marked blocks a run records */
#define GBP_V28_DMA_MARK_SHORT 256u  /* a marked block is this many bytes shorter than a chunk: 8 units, 2.0 ms of silence */
#define GBP_V28_DMA_BINS   6u        /* bytes left: <1000, <2000, <3000, <3500, <4000, >= 4000 */

struct gbp_v28_dma_raw { uint32_t addr, left, ret1, ret2, dt; };

/* One MARKED block (Issue #139, the discriminator between AHEAD + 1 and AHEAD + 2): programmed at callback `j` with a length the others do not have, and what the
 * next callbacks read. left[i] is the bytes-left read at ENTRY of callback j + i + 1; dur[k] is the duration in ticks of the block that STARTED at callback j + k
 * (the interval between callback j + k and j + k + 1). A block that is shorter than the rest shows in `left` as a lower reading and in `dur` as a shorter interval,
 * at the callback its start is at: j + 1 if what a callback programs starts at the NEXT callback (AHEAD + 1), j + 2 if one callback later (AHEAD + 2). */
struct gbp_v28_dma_mark { uint32_t j, left[3], dur[4], done; };

struct gbp_v28_dma {
    uint32_t n, prev1, prev2, none, same12;
    uint32_t post_new, post_kept, post_amb, post_other;   /* the register read again right AFTER the init: what the callback just programmed, the entry value, indistinguishable, or neither */
    uint32_t left_min, left_max;
    uint32_t bins[GBP_V28_DMA_BINS];
    uint32_t raw_n;
    uint32_t ret1, ret2;         /* the physical addresses the last two callbacks returned (ret1 the last) */
    uint32_t seeded;
    uint64_t left_sum, t_last;
    struct gbp_v28_dma_raw raw[GBP_V28_DMA_RAW];
    uint32_t marks_on, marks_n, mark_pending, mute_run;   /* the marked-block discriminator: enabled, taken, one in flight (index + 1), consecutive mute hand-offs so far */
    struct gbp_v28_dma_mark mark[GBP_V28_DMA_MARKS];
};

void gbp_v28_dma_init(struct gbp_v28_dma *d);

/* The AI's register form of a buffer's address. */
uint32_t gbp_v28_dma_phys(const void *p);

/* The first chunk, programmed by the pump slot's own hand-off before the DMA is started: what the FIRST callback should find in the register. */
void gbp_v28_dma_seed(struct gbp_v28_dma *d, const void *first);

/* One callback: `addr` and `left` are the two register reads at its ENTRY, `t` its time (ticks), `returned` the chunk the hand-off returned (programmed next), `post` the address
 * register read again right after that programming. `post` tells a write-through latch (it reads back what was just written: `addr` then only echoes the previous write and cannot
 * separate AHEAD + 1 from AHEAD + 2) from a register that keeps the ACTIVE block's address until the block ends (`post` keeps the entry value: the address arm is informative). */
void gbp_v28_dma_note(struct gbp_v28_dma *d, uint32_t addr, uint32_t left, uint64_t t, const void *returned, uint32_t post);

/* THE MARKED BLOCK. Off by default; the plan that carries it turns it on once, before the DMA starts.
 * gbp_v28_dma_len() is called by the callback for EVERY hand-off, after the hand-off and before the block is programmed, with `silence` true exactly when the chunk the
 * hand-off returned is the silence buffer of a MUTE (never an underrun's). It returns the length to program: `chunk_bytes`, except for the FIRST silent hand-off of each
 * mute (a run of consecutive mute hand-offs), which is `chunk_bytes - GBP_V28_DMA_MARK_SHORT`, up to GBP_V28_DMA_MARKS times and never while an earlier mark is still being
 * read. Only silence is ever shortened, and only at the run's first hand-off: the interval the sweep's landing measures from the last two hand-offs of its mute is seven or ten
 * hand-offs away. */
void gbp_v28_dma_marks_enable(struct gbp_v28_dma *d);
uint32_t gbp_v28_dma_len(struct gbp_v28_dma *d, int silence, uint32_t chunk_bytes);

#ifdef __cplusplus
}
#endif
#endif
