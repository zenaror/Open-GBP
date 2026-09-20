/*
 * gbp_vfull.h — the FULL-FRAME SAMPLE store of GBP-VIDEO-008 (HARDWARE_TESTS
 * §V6.5, §V6.8; GitHub Issue #7). Pure, hardware-free, host-tested: no
 * allocation, no clock, no device, no filesystem, no blocking.
 *
 * ---- WHAT IT KEEPS, AND FROM WHERE --------------------------------------
 *
 * For K = 8 lifecycles chosen CONTENT-BLINDLY -- by frame_index only, one every
 * 256 positions from the scientific window's first retained frame -- it keeps
 * the whole raw VIDEO frame (40 x 0xF00 bytes, all four bytes of every pixel
 * word, untouched) and the whole converted texture (38 400 GX_TF_RGB5A3
 * texels) so that CLAIM-A (the source frame was acquired completely) and
 * CLAIM-B (the source -> texture conversion is full-frame correct) can be
 * decided OFFLINE against an oracle that this runtime never sees.
 *
 * CONSUMER ONLY. The copy is made by the pump, in the same slices that convert
 * the frame: one block's 3 840 raw bytes and the 1 920 texture bytes it
 * produced, per slice, for a sampled lifecycle and for nothing else. Never
 * between the ACK and the RE-ARM (§V5.7), never a whole frame in one slice,
 * never a clock, never a predicate on pixel content.
 *
 * ---- GENERATIONS NEVER MIX ------------------------------------------------
 *
 * The raw bytes come from the ring slot the conversion reads, under the same
 * generation guard the consumer already enforces: when the guard rejects the
 * frame (the producer reused the slot), the sample is REFUSED and its bytes are
 * never presented as a frame. A sample is COMPLETE only when all 40 blocks were
 * copied and the conversion finished; anything else is INCOMPLETE or REFUSED,
 * with the reason, and the offline analyzer refuses it.
 *
 * ---- BOUNDED --------------------------------------------------------------
 *
 * K samples, fixed. A frame that maps beyond K is counted (skipped_capacity)
 * and not stored; nothing is ever overwritten.
 */
#ifndef OPENGBP_GBP_VFULL_H
#define OPENGBP_GBP_VFULL_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_vpix.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_VFULL_K            8u
#define GBP_VFULL_SPACING      256u
#define GBP_VFULL_BLOCKS       GBP_VPIX_BLOCKS                        /* 40 */
#define GBP_VFULL_RAW_BYTES    GBP_VPIX_FRAME_BYTES                   /* 153600 per sample */
#define GBP_VFULL_TEX_TEXELS   (GBP_VPIX_TEX_BYTES / 2u)              /* 38400 per sample */
#define GBP_VFULL_BLOCK_RAW    GBP_VPIX_BLOCK_BYTES                   /* 3840 */
#define GBP_VFULL_BLOCK_TEX    (GBP_VPIX_BLOCK_TEX_BYTES / 2u)        /* 960 texels */
#define GBP_VFULL_RAW_STORE    (GBP_VFULL_K * GBP_VFULL_RAW_BYTES)    /* 1228800 */
#define GBP_VFULL_TEX_STORE    (GBP_VFULL_K * GBP_VFULL_TEX_TEXELS)   /* 307200 texels = 614400 B */

enum gbp_vfull_state {
    GBP_VFULL_EMPTY = 0,        /* the slot's frame was never taken by the consumer */
    GBP_VFULL_OPEN = 1,         /* being copied */
    GBP_VFULL_COMPLETE = 2,     /* 40 blocks of raw and texture, conversion finished */
    GBP_VFULL_REFUSED = 3       /* the frame was abandoned; bytes are not a frame */
};

enum gbp_vfull_reason {
    GBP_VFULL_R_NONE = 0,
    GBP_VFULL_R_GENERATION = 1, /* the generation guard rejected the slot */
    GBP_VFULL_R_NO_RAW = 2,     /* the ring returned no block */
    GBP_VFULL_R_INCOMPLETE = 3, /* convert_done with blocks missing */
    GBP_VFULL_R_ABANDONED = 4   /* any other abandon path */
};

struct gbp_vfull_sample {
    uint32_t sample_index;      /* 0..K-1, == (frame_index - origin) / spacing */
    uint32_t frame_index;       /* the assembler's key */
    uint32_t seq;               /* the publish sequence: the generation identity */
    uint32_t life;              /* the OGBPDISP2 lifecycle index */
    uint16_t slot, tex;         /* raw ring slot; texture buffer index */
    uint16_t state, reason;
    uint16_t blocks_raw, blocks_tex;
    uint64_t present;           /* bit b: block b copied (raw and texture) */
    uint64_t t_take, t_convert_done, t_decision;
    uint32_t retrace_decision;
    int16_t  xfb_target;        /* -1 until a decision handed it over */
    uint16_t disposition;       /* the OGBPDISP2 disposition, or 0 */
};

struct gbp_vfull {
    uint8_t  *raw;              /* K x 153600 bytes, the caller's storage */
    uint16_t *tex;              /* K x 38400 texels, the caller's storage */
    struct gbp_vfull_sample s[GBP_VFULL_K];
    uint32_t spacing;
    uint32_t origin;            /* the first retained frame of the scientific window */
    uint32_t origin_set;
    /* counters, plain increments, never reset */
    uint32_t want_calls, wanted, opened, completed, refused, skipped_capacity, blocks_copied;
};

void gbp_vfull_init(struct gbp_vfull *f, uint8_t *raw, uint16_t *tex, uint32_t spacing);

/* The origin is set ONCE, from the witness window's first retained frame; every
 * later call is ignored. Content-blind: a frame index, nothing else. */
void gbp_vfull_set_origin(struct gbp_vfull *f, uint32_t first_frame);

/* The sample index this frame maps to (0..K-1), or -1: no origin yet, not on
 * the grid, beyond K (counted), or already used. Never reads a pixel. */
int gbp_vfull_want(struct gbp_vfull *f, uint32_t frame_index);

int gbp_vfull_open(struct gbp_vfull *f, int i, uint32_t frame_index, uint32_t seq,
                   uint16_t slot, uint16_t tex, uint32_t life, uint64_t t_take);

/* Copies ONE block: 3 840 raw bytes and 960 texels. Bounded; the only work. */
int gbp_vfull_block(struct gbp_vfull *f, int i, uint32_t block,
                    const uint8_t *raw_block, const uint16_t *tex_row);

/* COMPLETE iff all 40 blocks were copied; otherwise REFUSED (INCOMPLETE). */
int gbp_vfull_convert_done(struct gbp_vfull *f, int i, uint64_t t);

int gbp_vfull_refuse(struct gbp_vfull *f, int i, uint16_t reason);

/* The presentation decision of the sampled lifecycle, when it happens. */
int gbp_vfull_decision(struct gbp_vfull *f, int i, uint64_t t, uint32_t retrace,
                       int16_t xfb_target, uint16_t disposition);

const uint8_t  *gbp_vfull_raw(const struct gbp_vfull *f, int i);
const uint16_t *gbp_vfull_tex(const struct gbp_vfull *f, int i);
uint32_t gbp_vfull_records(const struct gbp_vfull *f);   /* slots that are not EMPTY */

#ifdef __cplusplus
}
#endif
#endif
