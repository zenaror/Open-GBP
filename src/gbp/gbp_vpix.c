/*
 * gbp_vpix.c — raster -> GX_TF_RGB5A3 tile. See gbp_vpix.h for why this is the
 * whole of the colour work, and why it may never run in the service path.
 */
#include "gbp_vpix.h"

size_t gbp_vpix_raw_offset(uint32_t x, uint32_t y)
{
    /* Block b holds raster lines 4b..4b+3; inside a block a line is 960 bytes
     * and a pixel is 4 bytes. */
    const uint32_t block = y / GBP_VPIX_LINES_PER_BLOCK;
    const uint32_t line  = y % GBP_VPIX_LINES_PER_BLOCK;
    return (size_t)block * GBP_VPIX_BLOCK_BYTES
         + (size_t)line  * GBP_VPIX_LINE_STRIDE
         + (size_t)x * 4u;
}

size_t gbp_vpix_tile_index(uint32_t x, uint32_t y)
{
    /* Tiles run left to right, then top to bottom; inside a tile the four rows
     * of four texels are consecutive. */
    const uint32_t tx = x / GBP_VPIX_TILE_W, ty = y / GBP_VPIX_TILE_H;
    const uint32_t ix = x % GBP_VPIX_TILE_W, iy = y % GBP_VPIX_TILE_H;
    const size_t tile = (size_t)ty * GBP_VPIX_TILES_X + tx;
    return tile * (GBP_VPIX_TILE_W * GBP_VPIX_TILE_H) + (size_t)iy * GBP_VPIX_TILE_W + ix;
}

static void note_flag(struct gbp_vpix_stats *st, uint32_t x, uint32_t y)
{
    st->flag15_count++;
    if (st->flag15_coords < GBP_VPIX_MAX_FLAG_COORDS) {
        st->flag15_x[st->flag15_coords] = (uint16_t)x;
        st->flag15_y[st->flag15_coords] = (uint16_t)y;
        st->flag15_coords++;
    }
}

int gbp_vpix_block(const uint8_t *block, uint32_t block_index,
                   uint16_t *tex, size_t tex_len, struct gbp_vpix_stats *stats)
{
    uint32_t line, x;

    if (!block || !tex) return -1;
    if (block_index >= GBP_VPIX_BLOCKS) return -1;
    if (tex_len < GBP_VPIX_TEX_BYTES / 2u) return -1;   /* tex_len counts TEXELS */

    for (line = 0; line < GBP_VPIX_LINES_PER_BLOCK; line++) {
        const uint8_t *src = block + (size_t)line * GBP_VPIX_LINE_STRIDE;
        const uint32_t y = block_index * GBP_VPIX_LINES_PER_BLOCK + line;
        for (x = 0; x < GBP_VPIX_WIDTH; x++) {
            /* bytes 1 and 3 only; bytes 0 and 2 are never read (U-GBP-029) */
            const uint16_t word = gbp_vpix_word(src[x * 4u + 1u], src[x * 4u + 3u]);
            const size_t i = gbp_vpix_tile_index(x, y);
            /* The source word is never modified. The OR produces a NEW value
             * for the texture, because RGB5A3 needs bit 15 set to read the
             * texel as opaque 5-5-5 — a presentation rule, not a protocol
             * claim (U-GBP-034 stays OPEN). */
            tex[i] = gbp_vpix_texel(word);
            if (stats) {
                stats->pixels++;
                if (gbp_vpix_flag15(word)) note_flag(stats, x, y);
            }
        }
    }
    return 0;
}

int gbp_vpix_frame(const uint8_t *raw, size_t raw_len,
                   uint16_t *tex, size_t tex_len, struct gbp_vpix_stats *stats)
{
    uint32_t b;

    if (!raw || !tex) return -1;
    if (raw_len < GBP_VPIX_FRAME_BYTES) return -1;
    if (tex_len < GBP_VPIX_TEX_BYTES / 2u) return -1;

    if (stats) {
        uint32_t i;
        stats->pixels = 0u;
        stats->flag15_count = 0u;
        stats->flag15_coords = 0u;
        for (i = 0; i < GBP_VPIX_MAX_FLAG_COORDS; i++) { stats->flag15_x[i] = 0u; stats->flag15_y[i] = 0u; }
    }
    for (b = 0; b < GBP_VPIX_BLOCKS; b++) {
        if (gbp_vpix_block(raw + (size_t)b * GBP_VPIX_BLOCK_BYTES, b, tex, tex_len, stats) != 0)
            return -1;
    }
    return 0;
}
