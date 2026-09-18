/*
 * gbp_vpix.h — the raster-to-texture conversion of GBP-VIDEO-004
 * (HARDWARE_TESTS §V5.10, §V5.11). Pure, hardware-free, host-tested.
 *
 * WHAT IT CONVERTS, AND HOW LITTLE WORK THAT IS
 *
 * The VIDEO window delivers 40 blocks of 0xF00 bytes. Each block is 4 raster
 * lines of 240 pixels of 4 bytes, line stride 960; the pixel is bytes 1 and 3,
 * `word16 = (b1 << 8) | b3` (GBP-VID-003, physically confirmed by GBP-HW-123
 * and GBP-HW-128). Bytes 0 and 2 are read by neither reference decoder, vary
 * physically between frames of the same picture, and mean nothing established
 * (U-GBP-029) — this module never reads them.
 *
 * `color-0002` established that the device already exchanges the two outer
 * 5-bit groups relative to the AGB framebuffer (GBP-HW-131). The word that
 * arrives therefore already has R in bits 14-10, which IS `GX_TF_RGB5A3` order.
 * So there is no channel arithmetic here at all:
 *
 *     texel = word16 | 0x8000
 *
 * and the only real work is the raster -> 4x4 tile permutation, which is the
 * same transformation the Start-up Disc's own converter performs (`FUN_8008EFB4`,
 * VIDEO_PATH.md §2.3): 0xF00 raw bytes in, 0x780 tiled bytes out, per block.
 *
 * ---- WHAT THE `| 0x8000` IS, AND WHAT IT IS NOT --------------------------
 *
 * It is a PRESENTATION transformation, required because `GX_TF_RGB5A3` reads a
 * texel with bit 15 set as opaque 5-5-5 RGB. It is what both references do when
 * they draw (the Disc ORs FILL = 0x8000 into every pixel; GBI ORs 0x80008000
 * into its tiles).
 *
 * It is **NOT** a statement that bit 15 means alpha, or opacity, or anything
 * else in the GBP protocol. What sets that bit on the wire is **U-GBP-034,
 * OPEN**. This module therefore never modifies a source word: `gbp_vpix_word()`
 * returns the word as it arrived, `gbp_vpix_flag15()` reports the bit
 * separately, and the OR happens only on the way into a texture.
 *
 * ---- WHERE IT MAY RUN ----------------------------------------------------
 *
 * CONSUMER ONLY. Never between the ACK and the RE-ARM. §V3.23 refused exactly
 * this class of work in the service path once already, and §V5.7 carries the
 * rule forward: what crosses into the service path is an integer, never bytes.
 * Nothing in this file reads a clock, touches a device, allocates or blocks.
 */
#ifndef OPENGBP_GBP_VPIX_H
#define OPENGBP_GBP_VPIX_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Geometry, all of it physically established (GBP-HW-074…087). */
#define GBP_VPIX_WIDTH        240u
#define GBP_VPIX_HEIGHT       160u
#define GBP_VPIX_BLOCKS       40u
#define GBP_VPIX_BLOCK_BYTES  0xF00u                     /* one VIDEO delivery */
#define GBP_VPIX_LINES_PER_BLOCK 4u
#define GBP_VPIX_LINE_STRIDE  (GBP_VPIX_WIDTH * 4u)      /* 960 */
#define GBP_VPIX_FRAME_BYTES  (GBP_VPIX_BLOCKS * GBP_VPIX_BLOCK_BYTES)   /* 153600 */

/* GX_TF_RGB5A3: 4x4 tiles, 16 texels of 2 bytes = 32 bytes per tile. */
#define GBP_VPIX_TILE_W       4u
#define GBP_VPIX_TILE_H       4u
#define GBP_VPIX_TILE_BYTES   (GBP_VPIX_TILE_W * GBP_VPIX_TILE_H * 2u)   /* 32 */
#define GBP_VPIX_TILES_X      (GBP_VPIX_WIDTH / GBP_VPIX_TILE_W)         /* 60 */
#define GBP_VPIX_TILES_Y      (GBP_VPIX_HEIGHT / GBP_VPIX_TILE_H)        /* 40 */
#define GBP_VPIX_TEX_BYTES    (GBP_VPIX_TILES_X * GBP_VPIX_TILES_Y * GBP_VPIX_TILE_BYTES) /* 76800 */
/* One block is 4 raster lines, which is exactly one tile row: 60 tiles, 0x780
 * bytes. The Disc's converter produces the same 0x780 per block. */
#define GBP_VPIX_BLOCK_TEX_BYTES (GBP_VPIX_TILES_X * GBP_VPIX_TILE_BYTES)  /* 1920 = 0x780 */

/* The presentation bit RGB5A3 needs. NOT a claim about the protocol (U-GBP-034). */
#define GBP_VPIX_RGB5A3_OPAQUE 0x8000u

/* What a conversion observed, so the flag stays science and the texel stays
 * presentation. Bounded: no coordinate list grows without limit. */
#define GBP_VPIX_MAX_FLAG_COORDS 8u

struct gbp_vpix_stats {
    uint32_t pixels;                 /* texels written; must equal 38400 */
    uint32_t flag15_count;           /* words whose bit 15 was set ON THE WIRE */
    uint16_t flag15_x[GBP_VPIX_MAX_FLAG_COORDS];
    uint16_t flag15_y[GBP_VPIX_MAX_FLAG_COORDS];
    uint32_t flag15_coords;          /* coordinates actually recorded (<= MAX) */
};

/* The source word, exactly as the wire carried it. Bytes 0 and 2 are not read. */
static inline uint16_t gbp_vpix_word(uint8_t b1, uint8_t b3)
{
    return (uint16_t)(((uint16_t)b1 << 8) | (uint16_t)b3);
}

/* Bit 15 of a source word, reported and never consumed. */
static inline unsigned gbp_vpix_flag15(uint16_t word)
{
    return (unsigned)((word >> 15) & 1u);
}

/* The 15 colour bits, with the flag split off (§V5.11). */
static inline uint16_t gbp_vpix_color15(uint16_t word)
{
    return (uint16_t)(word & 0x7FFFu);
}

/* PRESENTATION ONLY. The source word is not modified; this returns a new value. */
static inline uint16_t gbp_vpix_texel(uint16_t word)
{
    return (uint16_t)(word | GBP_VPIX_RGB5A3_OPAQUE);
}

/* Byte offset of pixel (x, y) inside the raw 40-block frame. */
size_t gbp_vpix_raw_offset(uint32_t x, uint32_t y);

/* Texel index (not byte offset) of pixel (x, y) inside the tiled texture. */
size_t gbp_vpix_tile_index(uint32_t x, uint32_t y);

/* Converts ONE 0xF00 block into ONE tile row (0x780 bytes).
 * `block` is the raw delivery; `tex` is the whole texture; `block_index` says
 * which tile row to fill. Returns 0, or -1 on a bad argument — it never writes
 * outside `tex[0 .. GBP_VPIX_TEX_BYTES)`.
 * `stats` may be NULL; when given, it is ACCUMULATED into (never reset here). */
int gbp_vpix_block(const uint8_t *block, uint32_t block_index,
                   uint16_t *tex, size_t tex_len, struct gbp_vpix_stats *stats);

/* Converts a whole 153 600-byte frame into a 76 800-byte tiled texture.
 * Resets `stats` first. Returns 0, or -1 on a bad argument. */
int gbp_vpix_frame(const uint8_t *raw, size_t raw_len,
                   uint16_t *tex, size_t tex_len, struct gbp_vpix_stats *stats);

#ifdef __cplusplus
}
#endif
#endif
