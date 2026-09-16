/*
 * gbp_avseqdump.h — the sequence sidecar of GBP-VIDEO-001 ("OGBPSEQ1"): the
 * cycle table, the VIDEO and AUDIO tables and the raw blocks of one bounded
 * capture, serialized deterministically for the SD card
 * (`<TestID>_<BuildID>-seq.bin`) and parsed back on the host.
 *
 * A NEW format: the GBP-AV-SERVICE-001 sidecar (gbp_avdump.h, "OGBPBLK1",
 * format 2) is untouched. Every integer big-endian, fixed offsets, field by
 * field — no struct copy, no pointer, no RAM address, no compiler padding,
 * no uninitialized byte; reserved bytes zero; an identity that does not fit
 * is an error, never a truncation.
 *
 *   header (0x100 bytes)
 *   0x00  magic      "OGBPSEQ1"
 *   0x08  u16        format version (1)
 *   0x0A  u16        header size (0x100)
 *   0x0C  u32        flags: bit 0 service_ok, bit 1 restore_ok, bit 2 next_cause_at_end,
 *                           bit 3 partial (the loop ended by a failure), bit 4 stage_a_aborted
 *   0x10  u32        tb_hz
 *   0x14  u32        cycle_count (admitted deliveries = cycle records)
 *   0x18  u32        video_count (VIDEO records = VIDEO DMAs started)
 *   0x1C  u32        audio_count (AUDIO records = AUDIO DMAs started)
 *   0x20  u32        audio_raw_count (raw AUDIO blocks stored)
 *   0x24  u32        video_block_size (0xF00), 0x28 u32 audio_block_size (0x1000)
 *   0x2C  u16        cycle_rec_size (96), 0x2E u16 video_rec_size (48)
 *   0x30  u16        audio_rec_size (32), 0x32 u16 capture_result (enum gbp_avseq_end)
 *   0x34  u16        status_code (the probe's status enum), 0x36 u16 end_reason (of the last cycle)
 *   0x38  u32        off_cycles, 0x3C u32 off_video_table
 *   0x40  id[32]     test_id, 0x60 id[32] build_id, 0x80 id[32] app, 0xA0 id[32] commit (rule of gbp_avdump.h)
 *   0xC0  u32        off_audio_table, 0xC4 u32 off_video_raw, 0xC8 u32 off_audio_raw, 0xCC u32 off_footer
 *   0xD0  u32        target_video_blocks, 0xD4 u32 max_deliveries, 0xD8 u32 admission_budget_ticks, 0xDC u32 t0 (first unmask)
 *   0xE0  u32        admission_deadline, 0xE4 u32 boundaries_gbi, 0xE8 u32 boundaries_disc, 0xEC u32 video_raw_stored
 *   0xF0  u8[12]     reserved, zero
 *   0xFC  u32        header_crc32 (bytes 0x00..0xFB)
 *   tables: cycle records (96 bytes each), VIDEO records (48), AUDIO records (32), see gbp_avseqdump.c for the field offsets
 *   raw VIDEO blocks: video_raw_stored × 0xF00 bytes, the completed blocks in sequence order (a VIDEO record's raw_offset
 *   is the file offset of its block; raw_len 0 when the DMA did not complete)
 *   raw AUDIO blocks: audio_raw_count × 0x1000 bytes (the first successful drains, then the last valid one when it lives
 *   in a ping-pong buffer; an AUDIO record's raw_index names its block, 0xFFFF when not kept)
 *   end   "OGBPEND1" + u32 crc32 of everything before this footer
 *
 * Bounds: the maximum file is computed at compile time from the design
 * constants (GBP_AVSEQDUMP_MAX_SIZE); the serializer proves offsets and
 * lengths before writing and never emits beyond `cap`. Written only after
 * the experiment and its teardown; never inside the loop.
 */
#ifndef OPENGBP_GBP_AVSEQDUMP_H
#define OPENGBP_GBP_AVSEQDUMP_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_avseq.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_AVSEQDUMP_MAGIC "OGBPSEQ1"
#define GBP_AVSEQDUMP_END "OGBPEND1"
#define GBP_AVSEQDUMP_VERSION 1u
#define GBP_AVSEQDUMP_HEADER_SIZE 0x100u
#define GBP_AVSEQDUMP_FOOTER_SIZE 12u
#define GBP_AVSEQDUMP_CYCLE_REC 96u
#define GBP_AVSEQDUMP_VIDEO_REC 48u
#define GBP_AVSEQDUMP_AUDIO_REC 32u
#define GBP_AVSEQDUMP_ID_FIELD 32u
#define GBP_AVSEQDUMP_ID_MAX 31u
#define GBP_AVSEQDUMP_FLAG_SERVICE_OK        0x01u
#define GBP_AVSEQDUMP_FLAG_RESTORE_OK        0x02u
#define GBP_AVSEQDUMP_FLAG_NEXT_CAUSE_AT_END 0x04u
#define GBP_AVSEQDUMP_FLAG_PARTIAL           0x08u
#define GBP_AVSEQDUMP_FLAG_STAGE_A_ABORTED   0x10u
#define GBP_AVSEQDUMP_MAX_SIZE (GBP_AVSEQDUMP_HEADER_SIZE + \
                                GBP_AVSEQ_MAX_DELIVERIES * GBP_AVSEQDUMP_CYCLE_REC + \
                                GBP_AVSEQ_MAX_VIDEO_BLOCKS * GBP_AVSEQDUMP_VIDEO_REC + \
                                GBP_AVSEQ_MAX_AUDIO_BLOCKS * GBP_AVSEQDUMP_AUDIO_REC + \
                                GBP_AVSEQ_VIDEO_RAW_BYTES + GBP_AVSEQ_AUDIO_RAW_BYTES + GBP_AVSEQDUMP_FOOTER_SIZE)

struct gbp_avseqdump_info {
    uint16_t version;
    uint32_t flags;
    uint32_t tb_hz;
    uint32_t cycle_count, video_count, audio_count, audio_raw_count, video_raw_stored;
    uint32_t video_block_size, audio_block_size;
    uint16_t capture_result, status_code, end_reason;
    uint32_t target_video_blocks, max_deliveries, admission_budget_ticks, t0, admission_deadline;
    uint32_t boundaries_gbi, boundaries_disc;
    char test_id[GBP_AVSEQDUMP_ID_FIELD];
    char build_id[GBP_AVSEQDUMP_ID_FIELD];
    char app[GBP_AVSEQDUMP_ID_FIELD];
    char commit[GBP_AVSEQDUMP_ID_FIELD];
    int identity_error;
    uint32_t off_cycles, off_video_table, off_audio_table, off_video_raw, off_audio_raw, off_footer;
    uint32_t header_crc32, total_crc32;
};

/* Stores the four identities without truncation (rule of gbp_avdump.h); returns 0 when all fit. */
int gbp_avseqdump_set_identity(struct gbp_avseqdump_info *info, const char *test_id, const char *build_id,
                               const char *app, const char *commit);

/* Bytes the serialization of `store` needs. */
size_t gbp_avseqdump_size(const struct gbp_avseq_store *s);

/* Serializes the store into out (cap bytes); the info's counts / offsets / CRCs are filled here.
 * Returns the bytes written; -1 when out is too small or an argument is inconsistent (the
 * offsets are proven before any byte is written); -2 when an identity breaks the rule. */
long gbp_avseqdump_serialize(struct gbp_avseqdump_info *info, const struct gbp_avseq_store *s, uint8_t *out, size_t cap);

/* Parses `in` (n bytes): header, table bounds, footer, CRCs. Fills info and, when non-NULL, the
 * pointers to the tables and the raw sections inside `in`. Negative codes: -1 too short / bad
 * magic, -2 unsupported version / header size / record size, -3 header CRC mismatch, -4 a
 * table or raw section falls outside the file or overlaps, -5 footer magic missing, -6 total
 * CRC mismatch, -7 a VIDEO record's stored CRC does not match its bytes, -8 an identity field
 * breaks the rule, -9 reserved bytes not zero. */
int gbp_avseqdump_parse(const uint8_t *in, size_t n, struct gbp_avseqdump_info *info,
                        const uint8_t **cycles, const uint8_t **vtable, const uint8_t **atable,
                        const uint8_t **video_raw, const uint8_t **audio_raw);

/* Decodes one serialized record into the C structure (fields the format carries; the rest zero). */
void gbp_avseqdump_decode_cycle(const uint8_t *rec, struct gbp_avseq_cycle *out);
void gbp_avseqdump_decode_vblock(const uint8_t *rec, struct gbp_avseq_vblock *out, uint32_t *raw_offset, uint32_t *raw_len);
void gbp_avseqdump_decode_ablock(const uint8_t *rec, struct gbp_avseq_ablock *out);

#ifdef __cplusplus
}
#endif
#endif
