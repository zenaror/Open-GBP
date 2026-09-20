/*
 * gbp_vfulldump.h — "OGBPFULL1", the full-frame sample sidecar of GBP-VIDEO-008
 * (HARDWARE_TESTS §V6.8; GitHub Issue #7). A NEW magic: OGBPIDXCAP1 holds the
 * 4 320-byte witness of every frame and OGBPDISP2 holds lifecycles and
 * decisions; neither can carry a raw frame and its texture, and a frozen
 * contract is never extended in place.
 *
 * Same conventions as the family: 8-byte magic, big-endian field by field, no
 * struct copy, no pointer, no RAM address, no padding, no uninitialized byte,
 * identities that are an error when they do not fit, a footer with a CRC-32
 * over everything before it, and each record sealing its own bytes.
 *
 * ---- LAYOUT --------------------------------------------------------------
 *
 *   header   0x100 bytes
 *   records  records_n x (0x80 meta + 153 600 raw + 76 800 texture) = 230 528 each
 *            (only slots that are not EMPTY are written; sample_index is in the meta)
 *   footer   "OGBPFEND" + u32 CRC-32 of everything before it
 *
 * The raw bytes are the DMA's bytes, all four per pixel word, untouched; the
 * texture is the converter's output for the SAME lifecycle, serialized as
 * big-endian uint16 in tile order. The record CRC seals meta[0x00..0x78),
 * then the raw, then the texture bytes as written.
 *
 * Written ONLY after the hardware teardown, on the operator's keypress, from
 * fixed RAM, through the same streaming sink as the other sidecars.
 */
#ifndef OPENGBP_GBP_VFULLDUMP_H
#define OPENGBP_GBP_VFULLDUMP_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_vfull.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_VFULLDUMP_MAGIC        "OGBPFULL"
#define GBP_VFULLDUMP_END          "OGBPFEND"
#define GBP_VFULLDUMP_VERSION      1u
#define GBP_VFULLDUMP_HEADER_SIZE  0x100u
#define GBP_VFULLDUMP_META_SIZE    0x80u
#define GBP_VFULLDUMP_FOOTER_SIZE  12u
#define GBP_VFULLDUMP_TEX_BYTES    (GBP_VFULL_TEX_TEXELS * 2u)                       /* 76800 */
#define GBP_VFULLDUMP_RECORD_SIZE  (GBP_VFULLDUMP_META_SIZE + GBP_VFULL_RAW_BYTES + GBP_VFULLDUMP_TEX_BYTES)  /* 230528 */
#define GBP_VFULLDUMP_ID_FIELD     32u
#define GBP_VFULLDUMP_ID_MAX       31u
/* The streaming chunk carries the header, one meta block and texture pieces;
 * the raw bytes go straight from the store. */
#define GBP_VFULLDUMP_CHUNK        0x1000u

#define GBP_VFULLDUMP_FLAG_TRUNCATED        0x0001u
#define GBP_VFULLDUMP_FLAG_ORIGIN_SET       0x0002u
#define GBP_VFULLDUMP_FLAG_CAPACITY_SKIPPED 0x0004u   /* a grid frame fell beyond K */
#define GBP_VFULLDUMP_FLAG_ALL              0x0007u

struct gbp_vfulldump_info {
    uint16_t version, header_size;
    uint32_t flags;
    uint32_t record_size, meta_size, records_n, k_cap, spacing, origin;
    uint32_t raw_bytes, tex_bytes, blocks, block_bytes, tex_row_bytes, width, height;
    uint32_t tb_hz;
    uint32_t want_calls, wanted, opened, completed, refused, skipped_capacity, blocks_copied;
    uint32_t off_records, off_footer;
    uint64_t total_size;
    char test_id[GBP_VFULLDUMP_ID_FIELD];
    char build_id[GBP_VFULLDUMP_ID_FIELD];
    char app[GBP_VFULLDUMP_ID_FIELD];
    char commit[GBP_VFULLDUMP_ID_FIELD];
    int identity_error;
    uint32_t header_crc32, total_crc32;
};

int gbp_vfulldump_set_identity(struct gbp_vfulldump_info *info, const char *test_id,
                               const char *build_id, const char *app, const char *commit);
int gbp_vfulldump_layout(struct gbp_vfulldump_info *info, const struct gbp_vfull *f);

typedef int (*gbp_vfulldump_sink)(void *ctx, const uint8_t *data, uint32_t len);

/* Streams the whole file. `chunk` (>= GBP_VFULLDUMP_CHUNK) is the only
 * transient buffer; the raw bytes are handed to the sink from the store.
 * Returns bytes written or -1 bad argument, -2 identity, -3 layout, -4 sink. */
long gbp_vfulldump_stream(struct gbp_vfulldump_info *info, const struct gbp_vfull *f,
                          uint8_t *chunk, uint32_t chunk_cap,
                          gbp_vfulldump_sink sink, void *sink_ctx, uint64_t *written);

/* Strict parser: -1 short/magic, -2 version/sizes, -3 header CRC, -4 bounds,
 * -5 footer magic, -6 total CRC, -7 identity, -8 reserved/flags, -9 record. */
int gbp_vfulldump_parse(const uint8_t *in, size_t n, struct gbp_vfulldump_info *info,
                        const uint8_t **records);

/* Record accessors (`rec` points at the record's first byte). */
uint32_t gbp_vfulldump_rec_sample_index(const uint8_t *rec);
uint32_t gbp_vfulldump_rec_frame_index(const uint8_t *rec);
uint32_t gbp_vfulldump_rec_seq(const uint8_t *rec);
uint16_t gbp_vfulldump_rec_state(const uint8_t *rec);
uint64_t gbp_vfulldump_rec_present(const uint8_t *rec);
const uint8_t *gbp_vfulldump_rec_raw(const uint8_t *rec);
uint16_t gbp_vfulldump_rec_texel(const uint8_t *rec, uint32_t i);

#ifdef __cplusplus
}
#endif
#endif
