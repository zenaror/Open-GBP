/*
 * gbp_avdump.h — the block sidecar of GBP-AV-SERVICE-001: the raw AUDIO and
 * VIDEO blocks of one run, serialized deterministically for the SD card
 * (`<TestID>_<BuildID>-blocks.bin`) and parsed back on the host.
 *
 * The text log carries the summaries (CRC-32, byte windows); this file
 * carries the bytes. Format version 2 (all integers big-endian, fixed
 * offsets, serialized field by field — no struct copy, no pointer, no RAM
 * address, no uninitialized byte; version 1, a pre-release layout with
 * 16-byte identity fields that truncated the Test ID, was never produced
 * on hardware and is rejected):
 *
 *   0x00  magic      "OGBPBLK1"
 *   0x08  u16        version (2)
 *   0x0A  u16        header size (0x100)
 *   0x0C  u32        flags: bit 0 audio present (read attempted), bit 1 audio valid (read completed),
 *                           bit 2 video present, bit 3 video valid
 *   0x10  u16        pending_irq (the PRESVC value the service acted on)
 *   0x12  u16        drain_mask (pending_irq & AV mask)
 *   0x14  u32        audio_len   (bytes stored; 0 when not present)
 *   0x18  u32        video_len
 *   0x1C  u32        audio_crc32 (of the stored bytes; 0 when none)
 *   0x20  u32        video_crc32
 *   0x24  u32        audio_rc, 0x28 u32 video_rc (gbp_status; 0 = ok)
 *   0x2C  u32        audio_wait_ticks, 0x30 u32 video_wait_ticks (backend completion wait)
 *   0x34  u32        audio_dt_ticks, 0x38 u32 video_dt_ticks (t_end - t_start around the call)
 *   0x3C  u32        tb_hz (time-base frequency the ticks refer to)
 *   0x40  id[32]     test_id   (e.g. "GBP-AV-SERVICE-001")
 *   0x60  id[32]     build_id  (e.g. "avsvc-0001")
 *   0x80  id[32]     app       (e.g. "gbp-av-service-probe")
 *   0xA0  id[32]     commit    (e.g. "5ed9d93-dirty")
 *   0xC0  u32        audio_index, 0xC4 u32 video_index (register indices)
 *   0xC8  u8[52]     reserved, zero
 *   0xFC  u32        header_crc32 (CRC-32 of bytes 0x00..0xFB)
 *   0x100 audio bytes (audio_len), then video bytes (video_len)
 *   end   "OGBPEND1" + u32 crc32 of everything before this footer
 *
 * Identity field rule (id[32]): 1 to 31 characters of printable ASCII
 * without spaces (0x21..0x7E) for test_id and build_id, 0 to 31 for app and
 * commit; the characters are followed by NUL bytes up to byte 31 (a NUL is
 * therefore always present, and every byte after the first NUL is zero).
 * A string that does not fit, an empty required field or a byte outside
 * the range is an ERROR of the serializer (-2) and of the parser (-8) —
 * never a truncation. The official identities ("GBP-AV-SERVICE-001",
 * "avsvc-0001", "gbp-av-service-probe", a 7-hex commit + "-dirty") fit
 * with room.
 *
 * A block that was not read is absent (len 0): nothing uninitialized is
 * ever stored. A block whose read failed is stored as it was left in
 * memory (present, not valid) so the failure keeps its raw evidence.
 * tools/avdump.py parses the same layout on the host.
 */
#ifndef OPENGBP_GBP_AVDUMP_H
#define OPENGBP_GBP_AVDUMP_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_AVDUMP_MAGIC "OGBPBLK1"
#define GBP_AVDUMP_END "OGBPEND1"
#define GBP_AVDUMP_VERSION 2u
#define GBP_AVDUMP_HEADER_SIZE 0x100u
#define GBP_AVDUMP_FOOTER_SIZE 12u
#define GBP_AVDUMP_ID_FIELD 32u      /* bytes of one identity field in the file */
#define GBP_AVDUMP_ID_MAX 31u        /* characters an identity may hold (a NUL always follows) */
#define GBP_AVDUMP_FLAG_AUDIO_PRESENT 0x1u
#define GBP_AVDUMP_FLAG_AUDIO_VALID   0x2u
#define GBP_AVDUMP_FLAG_VIDEO_PRESENT 0x4u
#define GBP_AVDUMP_FLAG_VIDEO_VALID   0x8u
/* largest file for the two GBP blocks (0x1000 + 0xF00) */
#define GBP_AVDUMP_MAX_SIZE (GBP_AVDUMP_HEADER_SIZE + 0x1000u + 0x0F00u + GBP_AVDUMP_FOOTER_SIZE)

struct gbp_avdump_info {
    uint16_t version;
    uint32_t flags;
    uint16_t pending_irq, drain_mask;
    uint32_t audio_len, video_len;
    uint32_t audio_crc32, video_crc32;
    uint32_t audio_rc, video_rc;
    uint32_t audio_wait_ticks, video_wait_ticks;
    uint32_t audio_dt_ticks, video_dt_ticks;
    uint32_t tb_hz;
    char test_id[GBP_AVDUMP_ID_FIELD];   /* NUL-terminated, at most GBP_AVDUMP_ID_MAX characters */
    char build_id[GBP_AVDUMP_ID_FIELD];
    char app[GBP_AVDUMP_ID_FIELD];
    char commit[GBP_AVDUMP_ID_FIELD];
    int identity_error;        /* set by gbp_avdump_set_identity when a string did not fit: the serializer refuses */
    uint32_t audio_index, video_index;
    uint32_t header_crc32;     /* parse: as read; serialize: computed */
    uint32_t total_crc32;      /* parse: as read; serialize: computed */
};

/* 1 when `s` obeys the identity rule (length 1..31 or, with `may_be_empty`, 0..31; bytes 0x21..0x7E). */
int gbp_avdump_id_ok(const char *s, int may_be_empty);

/* Stores the four identities into `info` without truncation: a string that
 * does not fit (or breaks the rule) is stored empty and identity_error is
 * set, so the serializer refuses the file. Returns 0 when all four fit. */
int gbp_avdump_set_identity(struct gbp_avdump_info *info, const char *test_id, const char *build_id,
                            const char *app, const char *commit);

/* Bytes the serialization of `info` needs (header + payload + footer). */
size_t gbp_avdump_size(const struct gbp_avdump_info *info);

/* Serializes into out (cap bytes). audio / video point to audio_len / video_len
 * bytes (may be NULL when the length is 0). The CRCs of the payload are
 * computed here from the bytes given (info->audio_crc32 / video_crc32 are
 * overwritten). Returns the number of bytes written; -1 when out is too
 * small or an argument is inconsistent; -2 when an identity breaks the
 * rule (too long, required and empty, bad byte, or identity_error set). */
long gbp_avdump_serialize(struct gbp_avdump_info *info, const uint8_t *audio, const uint8_t *video,
                          uint8_t *out, size_t cap);

/* Parses `in` (n bytes). On success fills info, points *audio / *video into
 * `in` (NULL when absent) and returns 0. Negative codes: -1 too short / bad
 * magic, -2 unsupported version or header size, -3 header CRC mismatch,
 * -4 truncated payload, -5 footer magic missing, -6 total CRC mismatch,
 * -7 a stored payload CRC does not match its bytes, -8 an identity field
 * breaks the rule (no NUL, non-zero padding, bad byte, required empty). */
int gbp_avdump_parse(const uint8_t *in, size_t n, struct gbp_avdump_info *info,
                     const uint8_t **audio, const uint8_t **video);

#ifdef __cplusplus
}
#endif
#endif
