/*
 * gbp_vidxdump.h — the OGBPIDXCAP1 sidecar: the retained OGBPIDX1 canonical
 * witness of one indexed run, serialized DETERMINISTICALLY and STREAMED to the
 * SD card after the hardware teardown.
 *
 * ---- WHY A NEW MAGIC AND NOT AN OGBPSEQ1 VERSION -------------------------
 *
 * OGBPSEQ1 v2…v5 are FROZEN and physically produced: their header, tables,
 * identity rule, CRC scheme and footer describe frame SIGNATURES and preserved
 * episode frames. This file carries something categorically different — a
 * fixed 4 320-byte slice of PIXELS per frame, for every closed frame, with no
 * episode logic — and it is written by a different experiment. Extending
 * OGBPSEQ1 would force every existing parser to learn a section that has
 * nothing to do with what it was built to read, and would put a physically
 * produced format at risk for a convenience. So: a new magic, a version field
 * from the start, and the SAME conventions the family already proved —
 * 8-byte magic, big-endian field by field, no struct copy, no pointer, no RAM
 * address, no compiler padding, no uninitialized byte, an "OGBPEND1"-shaped
 * footer carrying a CRC-32 over everything before it, and identity fields that
 * are an error when they do not fit rather than a truncation.
 *
 * ---- THE RUNTIME NEVER INTERPRETS OGBPIDX1 -------------------------------
 *
 * Not one field here decodes SYNC, FRAME_ID, BLOCK_INDEX, STATUS or the CRC-8.
 * The runtime stores the words it observed and says how it observed them; the
 * meaning is recovered by `tools/vindex.py`, offline, where being wrong is free
 * and being checked is possible (§V5.35, §V5.39.10).
 *
 * ---- LAYOUT --------------------------------------------------------------
 *
 *   header   0x180 bytes, big-endian
 *   records  records_n x 4368 bytes
 *   footer   "OGBPEND1" + u32 CRC-32 of everything before it
 *
 * One record is 48 bytes of metadata followed by 40 x 54 big-endian uint16.
 * Filesystem access happens ONLY after the teardown has completed, on the
 * user's keypress, exactly as in GBP-VIDEO-001/002 (§V5.39.8).
 */
#ifndef OPENGBP_GBP_VIDXDUMP_H
#define OPENGBP_GBP_VIDXDUMP_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_vwitness.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_VIDXDUMP_MAGIC        "OGBPIDXC"
#define GBP_VIDXDUMP_END          "OGBPEND1"
#define GBP_VIDXDUMP_VERSION      1u
#define GBP_VIDXDUMP_HEADER_SIZE  0x180u
#define GBP_VIDXDUMP_FOOTER_SIZE  12u
#define GBP_VIDXDUMP_META_SIZE    0x30u        /* 48 bytes before the witness */
#define GBP_VIDXDUMP_RECORD_SIZE  (GBP_VIDXDUMP_META_SIZE + GBP_VWITNESS_FRAME_BYTES)  /* 4368 */
#define GBP_VIDXDUMP_ID_FIELD     32u
#define GBP_VIDXDUMP_ID_MAX       31u
/* The streaming chunk. It must hold at least one whole record, so the writer
 * never has to split a record's CRC across two calls. */
#define GBP_VIDXDUMP_CHUNK        0x10000u

#define GBP_VIDXDUMP_FLAG_STORE_FULL      0x0001u  /* a commit was refused: INCONCLUSIVE */
#define GBP_VIDXDUMP_FLAG_TARGET_REACHED  0x0002u  /* the target record was committed: NORMAL */
#define GBP_VIDXDUMP_FLAG_TRUNCATED       0x0004u  /* the writer did not finish */
#define GBP_VIDXDUMP_FLAG_SERVICE_OK      0x0008u
#define GBP_VIDXDUMP_FLAG_STOP_IS_TARGET  0x0010u  /* the run stopped BECAUSE of the target */
#define GBP_VIDXDUMP_FLAG_ALL             0x001Fu

struct gbp_vidxdump_info {
    uint16_t version, header_size;
    uint32_t flags;
    uint32_t record_size, records_cap, records_n, target_frames;
    uint32_t witness_words, witness_blocks, strip_x0, strip_row, block_bytes, line_stride;
    uint16_t stop_reason, status_code;
    uint32_t tb_hz;
    uint32_t frames_seen, frames_discarded, blocks_staged, blocks_placed, blocks_out_of_range;
    uint32_t copy_ticks_min, copy_ticks_max, copy_ticks_n;
    uint64_t copy_ticks_sum, t_first_record, t_last_record;
    uint32_t off_records, off_footer;
    uint64_t total_size;
    char test_id[GBP_VIDXDUMP_ID_FIELD];
    char build_id[GBP_VIDXDUMP_ID_FIELD];
    char app[GBP_VIDXDUMP_ID_FIELD];
    char commit[GBP_VIDXDUMP_ID_FIELD];
    int identity_error;
    uint32_t header_crc32, total_crc32;
};

/* Stores the four identities without truncation; returns 0 when all fit. */
int gbp_vidxdump_set_identity(struct gbp_vidxdump_info *info, const char *test_id,
                              const char *build_id, const char *app, const char *commit);

/* Fills the counts, sizes and offsets from the witness store with checked
 * arithmetic. Returns 0, or -1 when something does not fit. */
int gbp_vidxdump_layout(struct gbp_vidxdump_info *info, const struct gbp_vwitness *w);

/* The streaming sink: 0 on success, non-zero to abort. */
typedef int (*gbp_vidxdump_sink)(void *ctx, const uint8_t *data, uint32_t len);

/* Streams the whole file through `sink`, using `chunk` (>= one record plus the
 * header) as the ONLY transient buffer. Returns bytes written, or a negative
 * code: -1 bad argument, -2 identity does not fit, -3 layout overflow,
 * -4 the sink refused (bytes written so far land in *written). */
long gbp_vidxdump_stream(struct gbp_vidxdump_info *info, const struct gbp_vwitness *w,
                         uint8_t *chunk, uint32_t chunk_cap,
                         gbp_vidxdump_sink sink, void *sink_ctx, uint64_t *written);

/* Strict parser. Negative codes: -1 too short or bad magic, -2 unsupported
 * version / header size / record size, -3 header CRC mismatch, -4 the record
 * section falls outside the file, -5 footer magic missing, -6 total CRC
 * mismatch, -7 an identity field breaks the rule, -8 reserved bytes not zero,
 * -9 a record's internal bounds or its own CRC are inconsistent,
 * -10 a declared flag combination is impossible. */
int gbp_vidxdump_parse(const uint8_t *in, size_t n, struct gbp_vidxdump_info *info,
                       const uint8_t **records);

/* Field accessors for one parsed record (`rec` points at its first byte). */
uint32_t gbp_vidxdump_rec_frame_index(const uint8_t *rec);
uint16_t gbp_vidxdump_rec_blocks(const uint8_t *rec);
uint16_t gbp_vidxdump_rec_flags(const uint8_t *rec);
uint16_t gbp_vidxdump_rec_completeness(const uint8_t *rec);
uint64_t gbp_vidxdump_rec_present(const uint8_t *rec);
uint16_t gbp_vidxdump_rec_word(const uint8_t *rec, uint32_t block, uint32_t word);

#ifdef __cplusplus
}
#endif
#endif
