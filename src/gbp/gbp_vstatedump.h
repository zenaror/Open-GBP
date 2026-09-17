/*
 * gbp_vstatedump.h — the GBP-VIDEO-002 sidecar: the frame-signature store,
 * the event store, the episode descriptors, the bounded cycle records and
 * the preserved raw frames of one long run, serialized DETERMINISTICALLY
 * and STREAMED to the SD card after the hardware teardown.
 *
 * Format: the OGBPSEQ1 family, **version 2**. The design (§17) asks for the
 * family to be extended rather than replaced, and that is what this is: same
 * magic, same "OGBPEND1" footer, same identity rule (32-byte fields, an
 * identity that does not fit is an error and never a truncation), same
 * big-endian field-by-field encoding with no struct copy, no pointer, no RAM
 * address, no compiler padding and no uninitialized byte. What changes is
 * the content, because the evidence changed: GBP-VIDEO-002 has no
 * per-delivery table to carry — it has ~16 000 frame signatures instead.
 * Version 1 (src/gbp/gbp_avseqdump.h, GBP-VIDEO-001) is untouched, still
 * written by that probe and still parsed by that parser; the two versions
 * are distinguished by the `version` and `header_size` fields, which every
 * parser checks before anything else.
 *
 * STREAMED, NEVER STAGED. The file is about 5 to 6 MB — larger than any
 * staging buffer that would be reasonable next to 7 MiB of resident stores.
 * The layout is computed first (pure, checked arithmetic, every offset
 * proven before a byte is written), then the header, the tables and the raw
 * sections are pushed through a caller-provided sink in chunks of about
 * 64 KiB, with a running CRC-32 across everything written, and finally the
 * footer carrying that CRC. No second integral copy of the sidecar exists in
 * memory at any point.
 *
 * Filesystem access happens ONLY after the teardown has completed, on the
 * user's keypress, exactly as in GBP-VIDEO-001.
 *
 *   header (0x200 bytes, big-endian; see gbp_vstatedump.c for every offset)
 *   frame table        frame_count x 192
 *   event table        event_count x 64
 *   episode table      episode_count x 512
 *   cycle table        cycle_count x 128   (first / last / anomaly / episode records, in that order)
 *   raw VIDEO frames   the preserved episode frames, blocks x 0xF00 each, in descriptor order
 *   raw AUDIO blocks   audio_raw_count x 0x1000 (the first successful drain, then the last valid one)
 *   footer             "OGBPEND1" + u32 CRC-32 of everything before it
 *
 * NOTHING PRIVATE IS EVER WRITTEN HERE. The file carries our captured bytes
 * and our own signatures. No reference table, checksum, pixel or block range
 * of the Start-up Disc or of GBI appears in it, in the runtime, or in any
 * fixture derived from it.
 */
#ifndef OPENGBP_GBP_VSTATEDUMP_H
#define OPENGBP_GBP_VSTATEDUMP_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_vstate.h"
#include "gbp_vstate_probe.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_VSTATEDUMP_MAGIC "OGBPSEQ1"
#define GBP_VSTATEDUMP_END "OGBPEND1"
/*
 * VERSIONS OF THE FAMILY, and why this is version 3 rather than a new magic.
 *   v1  GBP-VIDEO-001 (src/gbp/gbp_avseqdump.h): per-delivery cycle/VIDEO/AUDIO
 *       tables plus raw blocks. Header 0x100. Untouched.
 *   v2  GBP-VIDEO-002 build vstate-0001, the FIRST PHYSICAL RUN. Header 0x200:
 *       frame signatures, events, episodes, sampled cycles, preserved raw.
 *       **FROZEN.** The physical sidecar of 2026-09-16 must keep parsing exactly
 *       as it did the day it was consolidated, so not one byte of the v2
 *       contract moves: same offsets, same CRC coverage, same reserved meaning.
 *   v3  GBP-VIDEO-002 build vstate-0002, this instrumented build. Everything v2
 *       has, at the same offsets, plus ONE new section carrying the semantic
 *       disagreement diagnostic (U-GBP-032), and three header fields that
 *       describe it taken from v2's reserved area.
 * It is a version and not a new magic because v3 is v2 plus a section: the
 * header, every table, the identity rule, the CRC scheme and the footer are
 * unchanged, and a reader that understands v2 understands all of v3 except that
 * one section. A new magic would claim a break that does not exist. Both
 * versions are dispatched explicitly and each is strict; neither can read the
 * other's file by accident, because the version is checked before anything.
 */
#define GBP_VSTATEDUMP_VERSION 3u          /* what this build WRITES */
#define GBP_VSTATEDUMP_VERSION_V2 2u       /* the frozen physical format, still read */
#define GBP_VSTATEDUMP_DIAG_REC GBP_VSTATE_DIAG_REC   /* 96 */
#define GBP_VSTATEDUMP_HEADER_SIZE 0x200u
#define GBP_VSTATEDUMP_FOOTER_SIZE 12u
#define GBP_VSTATEDUMP_FRAME_REC GBP_VSTATE_FRAME_REC      /* 192 */
#define GBP_VSTATEDUMP_EVENT_REC GBP_VSTATE_EVENT_REC      /* 64 */
#define GBP_VSTATEDUMP_EPISODE_REC 512u
#define GBP_VSTATEDUMP_CYCLE_REC GBP_VSTATE_CYC_REC        /* 128 */
#define GBP_VSTATEDUMP_ID_FIELD 32u
#define GBP_VSTATEDUMP_ID_MAX 31u
/* The streaming chunk. 64 KiB is the design's figure; it is the ONLY transient
 * buffer the save uses, and it holds no section in full. */
#define GBP_VSTATEDUMP_CHUNK 0x10000u

#define GBP_VSTATEDUMP_FLAG_SERVICE_OK         0x0001u
#define GBP_VSTATEDUMP_FLAG_RESTORE_OK         0x0002u
#define GBP_VSTATEDUMP_FLAG_NEXT_CAUSE_AT_END  0x0004u
#define GBP_VSTATEDUMP_FLAG_PARTIAL            0x0008u
#define GBP_VSTATEDUMP_FLAG_STAGE_A_ABORTED    0x0010u
#define GBP_VSTATEDUMP_FLAG_BASELINE_VALID     0x0020u
#define GBP_VSTATEDUMP_FLAG_FRAME_STORE_FULL   0x0040u
#define GBP_VSTATEDUMP_FLAG_EVENT_STORE_FULL   0x0080u
#define GBP_VSTATEDUMP_FLAG_EPISODE_STORE_FULL 0x0100u
#define GBP_VSTATEDUMP_FLAG_TAIL_TRUNCATED     0x0200u
#define GBP_VSTATEDUMP_FLAG_COUNTER_OVERFLOW   0x0400u

struct gbp_vstatedump_info {
    uint16_t version, header_size;
    uint32_t flags, tb_hz;
    uint32_t frame_count, event_count, episode_count, cycle_count, video_raw_frames, audio_raw_count;
    uint32_t video_block_size, audio_block_size, frame_max_blocks;
    uint16_t status_code, stop_reason;
    uint32_t off_frames, off_events, off_episodes, off_cycles, off_video_raw, off_audio_raw, off_footer;
    /* v3 only; zero and absent in v2 */
    uint32_t off_diag, diag_count, diag_rec_size;
    uint64_t total_size;
    char test_id[GBP_VSTATEDUMP_ID_FIELD];
    char build_id[GBP_VSTATEDUMP_ID_FIELD];
    char app[GBP_VSTATEDUMP_ID_FIELD];
    char commit[GBP_VSTATEDUMP_ID_FIELD];
    int identity_error;
    /* clocks and counters mirrored into the header so the file stands alone */
    uint64_t t_control_transform, t_capture_start, t_stop, t_teardown_begin, t_teardown_end;
    uint64_t capture_elapsed, baseline_elapsed, valid_observation_elapsed, valid_observation_at_target, safety_elapsed;
    uint64_t min_valid_observation_ticks, hard_wallclock_ticks, t_baseline_valid, tail_ticks;
    uint64_t sig_samples, sig_sum;
    uint32_t deliveries, video_completed, audio_drains;
    uint32_t frames_complete, frames_incomplete, resync_frames, anomalies_frame, anomalies_region;
    uint32_t boundaries_disc, boundaries_gbi, disagreements;
    uint32_t episodes_opened, stable_episodes, unstable_episodes, episodes_not_preserved;
    uint32_t events_dropped, event_seq_last, baseline_frame_index;
    uint32_t sig_min, sig_max, sig_median, sig_p95, sig_overflow;
    uint32_t tail_frames, cyc_first_n, cyc_last_n, cyc_anomaly_n, cyc_episode_n;
    uint32_t baseline_sig0, baseline_sig39, main_w1c, isr_w1c;
    uint32_t header_crc32, total_crc32;
};

/* Stores the four identities without truncation; returns 0 when all fit. */
int gbp_vstatedump_set_identity(struct gbp_vstatedump_info *info, const char *test_id, const char *build_id,
                                const char *app, const char *commit);

/* Fills the info from the state and the result, then computes every count,
 * size and offset with checked arithmetic. Returns 0, or -1 when a count or
 * an offset does not fit (nothing is written in that case). */
int gbp_vstatedump_layout(struct gbp_vstatedump_info *info, const struct gbp_vstate *st,
                          const struct gbp_vstate_result *res, const struct gbp_vstate_config *cfg);

/* The streaming sink: returns 0 on success, non-zero to abort the write.
 * `len` is never larger than the chunk the caller supplied. */
typedef int (*gbp_vstatedump_sink)(void *ctx, const uint8_t *data, uint32_t len);

/* Streams the whole file through `sink`, using `chunk` (>= 1024 bytes, 64 KiB
 * expected) as the ONLY transient buffer. Returns the number of bytes written,
 * or a negative code: -1 bad argument, -2 identity does not fit, -3 layout
 * overflow, -4 the sink refused (the count of bytes written so far is in
 * *written, so a partial save can name exactly what reached the card). */
long gbp_vstatedump_stream(struct gbp_vstatedump_info *info, const struct gbp_vstate *st,
                           const struct gbp_vstate_result *res, const struct gbp_vstate_config *cfg,
                           uint8_t *chunk, uint32_t chunk_cap,
                           gbp_vstatedump_sink sink, void *sink_ctx, uint64_t *written);

/* Strict parser (host / tests: the file is in memory there). Negative codes:
 * -1 too short or bad magic, -2 unsupported version / header size / record
 * size, -3 header CRC mismatch, -4 a section falls outside the file or
 * overlaps, -5 footer magic missing, -6 total CRC mismatch, -7 an identity
 * field breaks the rule, -8 reserved bytes not zero, -9 a table's internal
 * bounds are inconsistent. */
int gbp_vstatedump_parse(const uint8_t *in, size_t n, struct gbp_vstatedump_info *info,
                         const uint8_t **frames, const uint8_t **events, const uint8_t **episodes,
                         const uint8_t **cycles, const uint8_t **video_raw, const uint8_t **audio_raw);
/* Same, plus the v3 diagnostic section (NULL in a v2 file or when no record was captured). */
int gbp_vstatedump_parse_v3(const uint8_t *in, size_t n, struct gbp_vstatedump_info *info,
                            const uint8_t **frames, const uint8_t **events, const uint8_t **episodes,
                            const uint8_t **cycles, const uint8_t **diag,
                            const uint8_t **video_raw, const uint8_t **audio_raw);

/* The v3 diagnostic record. Returns 1 when the file carried a valid one. */
int gbp_vstatedump_decode_diag(const uint8_t *rec, struct gbp_vstate_diag *out);

/* Decoders for one serialized record. */
void gbp_vstatedump_decode_frame(const uint8_t *rec, struct gbp_vstate_frame *out);
void gbp_vstatedump_decode_event(const uint8_t *rec, struct gbp_vstate_event *out);
void gbp_vstatedump_decode_episode(const uint8_t *rec, struct gbp_vstate_episode *out, uint32_t raw_offset[GBP_VSTATE_EPISODE_RAW_SLOTS]);
void gbp_vstatedump_decode_cycle(const uint8_t *rec, struct gbp_vstate_cycle *out);

#ifdef __cplusplus
}
#endif
#endif
