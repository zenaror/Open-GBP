/*
 * gbp_awindump.h — "OGBPAW1", the AUDIO WINDOW sidecar of GBP-AUDIO-001
 * (HARDWARE_TESTS §V8; GitHub Issue #59). A NEW magic, because no existing
 * contract carries a window anchor and a frozen contract is never extended in
 * place. Family conventions, unchanged: 8-byte magic, big-endian field by
 * field, no struct copy, identities that are an error when they do not fit, a
 * per-record CRC-32 and a footer CRC-32 over everything before it. Written
 * only after the teardown.
 *
 *   header    0x100 bytes
 *   anchors   windows_n x 128 bytes          -- one per window, INCLUDING the control
 *   blocks    sum(anchor.blocks) x 0x1000    -- in window order, in drain order
 *   footer    "OGBPAWND" + u32 CRC-32
 *
 * THE ANCHOR IS THE POINT. §V8.3.1 anchors each window at "the block being
 * drained when the KEY record's t_attempt is taken", and a reader who cannot
 * align a block to the press that caused it has 5 MB of bytes and no
 * experiment. So every window carries the KEY event's number, the word, the
 * three instants in the transport's ticks64 base -- the same base OGBPIDXCAP1,
 * OGBPDISP2 and OGBPVI1 use, so a join needs no conversion -- and the service
 * delivery index of its first and last stored block.
 *
 * THE BLOCKS ARE NOT COPIED THROUGH THE CHUNK. They are handed to the sink
 * straight out of the window store: 5 MB moved once instead of twice, and the
 * CRC is computed over exactly the bytes that were written.
 */
#ifndef OPENGBP_GBP_AWINDUMP_H
#define OPENGBP_GBP_AWINDUMP_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_awin.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_AWINDUMP_MAGIC        "OGBPAW1\0"
#define GBP_AWINDUMP_END          "OGBPAWND"
#define GBP_AWINDUMP_VERSION      1u
#define GBP_AWINDUMP_HEADER_SIZE  0x100u
#define GBP_AWINDUMP_RECORD_SIZE  128u
#define GBP_AWINDUMP_FOOTER_SIZE  12u
#define GBP_AWINDUMP_ID_FIELD     32u
#define GBP_AWINDUMP_ID_MAX       31u
#define GBP_AWINDUMP_CHUNK        0x100u

#define GBP_AWINDUMP_FLAG_TRUNCATED   0x0001u
#define GBP_AWINDUMP_FLAG_INCOMPLETE  0x0002u   /* a window was still filling at the teardown */
#define GBP_AWINDUMP_FLAG_GAP         0x0004u   /* a drain that did not complete fell inside a window */
#define GBP_AWINDUMP_FLAG_REFUSED     0x0008u   /* a press was refused: busy, or every window used */
#define GBP_AWINDUMP_FLAG_ALL         0x000Fu

struct gbp_awindump_info {
    uint16_t version, header_size;
    uint32_t flags;
    uint32_t block_size, blocks_per_window, windows_n, record_size;
    uint32_t blocks_stored, blocks_seen, blocks_ignored, blocks_failed;
    uint32_t arms, arm_refused_busy, arm_refused_full, windows_closed;
    uint32_t tb_hz;
    uint32_t ticks_min, ticks_max, ticks_n;
    uint64_t ticks_sum;
    uint32_t off_records, off_blocks, off_footer;
    uint64_t total_size;
    char test_id[GBP_AWINDUMP_ID_FIELD];
    char build_id[GBP_AWINDUMP_ID_FIELD];
    char app[GBP_AWINDUMP_ID_FIELD];
    char commit[GBP_AWINDUMP_ID_FIELD];
    int identity_error;
    uint32_t header_crc32, total_crc32;
};

int gbp_awindump_set_identity(struct gbp_awindump_info *info, const char *test_id,
                              const char *build_id, const char *app, const char *commit);
int gbp_awindump_layout(struct gbp_awindump_info *info, const struct gbp_awin *w);

typedef int (*gbp_awindump_sink)(void *ctx, const uint8_t *data, uint32_t len);

long gbp_awindump_stream(struct gbp_awindump_info *info, const struct gbp_awin *w,
                         uint8_t *chunk, uint32_t chunk_cap,
                         gbp_awindump_sink sink, void *sink_ctx, uint64_t *written);

/* Strict parser: -1 short/magic, -2 version/sizes, -3 header CRC, -4 bounds,
 * -5 footer magic, -6 total CRC, -7 identity, -8 reserved/flags, -9 record. */
int gbp_awindump_parse(const uint8_t *in, size_t n, struct gbp_awindump_info *info,
                       const uint8_t **records, const uint8_t **blocks);

#ifdef __cplusplus
}
#endif
#endif
