/*
 * gbp_vcoldump.h — "OGBPCOL1", the sidecar of GBP-VIDEO-003 (HARDWARE_TESTS
 * §V3.20): the frame history, the certified window and the WHOLE raw bytes of
 * the frames the colour mapping will be decided from, serialized
 * deterministically and streamed to the SD card after the hardware teardown.
 *
 * A NEW FORMAT, AND DELIBERATELY NOT OGBPSEQ1. The OGBPSEQ1 family (versions 2
 * to 5) is the vstate probe's contract: frame signatures, a learned baseline,
 * episodes, a structured change, a semantic block about disagreement policy.
 * None of that describes this capture, and stretching a versioned contract to
 * fit a different experiment is how formats stop meaning anything. What IS
 * shared is the 160-byte disagreement record, because the R3 policy is shared
 * and was physically validated (GBP-HW-111) - a record is shared, a container
 * is not.
 *
 * Every integer big-endian, fixed offsets, field by field: no struct copy, no
 * pointer, no RAM address, no compiler padding, no uninitialized byte. Reserved
 * areas are zero and a parser refuses them otherwise. An identity that does not
 * fit is an error, never a truncation. Sections are contiguous, in this order,
 * with no gap and no overlap:
 *
 *   header            0x200 bytes
 *   frame table       frame_count x 48
 *   certified table   cert_count  x 32       (cert_count <= 3)
 *   diagnostics       diag_count  x 160      (the shared R3 record, v5 contract)
 *   raw VIDEO         cert_count x 40 x 0xF00
 *   raw AUDIO         audio_raw_count x 0x1000   (0 in this experiment)
 *   footer            "OGBPCEND" + u32 CRC-32 of everything before it
 *
 * There is no cycle table. The colour analysis (§V3.14) reads raw bytes, the
 * certified table and the diagnostics; per-cycle timing belongs to the vstate
 * experiment, and the diagnostic record already carries the full cycle context
 * of every disagreement. A section nothing reads is a section that rots.
 *
 * THE FILE HOLDS NO CONCLUSION. It carries no hypothesis, no channel name, no
 * "observed vector" and no winning mapping: those are produced offline by
 * tools/vcolor.py from the raw bytes, so the decision can be redone and
 * disputed without the console (§V3.13, §V3.21).
 *
 * ---- header layout, byte by byte ------------------------------------------
 *   0x000  char[8]  magic "OGBPCOL1"
 *   0x008  u16      format version (1)
 *   0x00A  u16      header size (0x200)
 *   0x00C  u32      flags: bit0 service_ok, bit1 restore_ok, bit2 certified,
 *                          bit3 hold_complete (RETIRED, 0), bit4 partial (loop
 *                          ended by a failure), bit5 stage_a_aborted,
 *                          bit6 frame_table_capped, bit7 raw_unrecoverable
 *   0x010  u32      tb_hz
 *   0x014  u32      frame_count      0x018 u32 cert_count
 *   0x01C  u32      diag_count       0x020 u32 audio_raw_count
 *   0x024  u32      video_block_size (0xF00)
 *   0x028  u32      audio_block_size (0x1000)
 *   0x02C  u32      blocks_per_frame (40)
 *   0x030  u16      frame_rec_size (48)   0x032 u16 cert_rec_size (32)
 *   0x034  u16      diag_rec_size (160)   0x036 u16 status_code
 *   0x038  u16      stop_reason           0x03A u16 n_stable (3)
 *   0x03C  u16      cert_budget (3)       0x03E u16 hold_frames_cfg (RETIRED, 0)
 *   0x040  id[32]   test_id    0x060 id[32] build_id
 *   0x080  id[32]   app        0x0A0 id[32] commit
 *   0x0C0  u32      off_frames     0x0C4 u32 off_cert
 *   0x0C8  u32      off_diag       0x0CC u32 off_video_raw
 *   0x0D0  u32      off_audio_raw  0x0D4 u32 off_footer
 *   0x0D8  u32      reserved (0)   0x0DC u32 reserved (0)
 *   0x0E0  u64      t_control_transform (the safety epoch)
 *   0x0E8  u64      t_capture_start
 *   0x0F0  u64      t_stop
 *   0x0F8  u64      t_certified (0 when nothing certified)
 *   0x100  u64      t_teardown_begin   0x108 u64 t_teardown_end
 *   0x110  u64      capture_elapsed    0x118 u64 safety_elapsed
 *   0x120  u64      search_window_ticks
 *   0x128  u64      hard_wallclock_ticks
 *   0x130  u32      max_deliveries     0x134 u32 frame_table_cap
 *   0x138  u32      deliveries         0x13C u32 video_completed
 *   0x140  u32      audio_drains       0x144 u32 isr_w1c
 *   0x148  u32      main_w1c           0x14C u32 frames_total
 *   0x150  u32      frames_eligible    0x154 u32 frames_dropped
 *   0x158  u32      runs_reset         0x15C u32 hold_frames (RETIRED, 0)
 *   0x160  u32      hold_seen (RETIRED, 0)   0x164 u32 sig_mismatches
 *   0x168  u32      run_len            0x16C u32 run_first_index
 *   0x170  u32[9]   frames_refused[GBP_VCOLOR_REASONS]     (0x170..0x193)
 *   0x194  u32      disagreements_total
 *   0x198  u32      source_serviced    0x19C u32 source_other
 *   0x1A0  u32      non_source         0x1A4 u32 diagnostics_preserved
 *   0x1A8  u32      diagnostics_not_preserved
 *   0x1AC  u32      frames_quarantined 0x1B0 u32 frames_source_deferred
 *   0x1B4  u32      errors
 *   0x1B8  u32      control_orig       0x1BC u32 control_exp
 *   0x1C0  u32      restore_flags: bit0 restore_ok, bit1 handler_restored,
 *                   bit2 mask_ok, bit3 control_ok, bit4 pi_sticky_final,
 *                   bit5 arinfo_restore_ok, bit6 power_cycle_required
 *   0x1C4  u32      intmr_final
 *   0x1C8..0x1FB    reserved, zero
 *   0x1FC  u32      CRC-32 of 0x000..0x1FB
 *
 * ---- frame record, 48 bytes ------------------------------------------------
 *   0x00 u64 t_first_block   0x08 u64 t_last_block
 *   0x10 u32 index           0x14 u32 blocks
 *   0x18 u16 flags (GBP_VSTATE_F_*)   0x1A u16 reason (GBP_VCOLOR_*)
 *   0x1C u32 run_len_after   0x20 u32 sig0   0x24 u32 sig39
 *   0x28 u32 reserved (0)    0x2C u32 reserved (0)
 *
 * ---- certified record, 40 bytes -------------------------------------------
 *   0x00 u64 t_first_block   0x08 u64 t_last_block
 *   0x10 u32 frame_index     0x14 u32 blocks
 *   0x18 u32 raw_offset (into the raw VIDEO section)
 *   0x1C u16 ring_slot (the state model's slot the bytes were read from)
 *   0x1E u16 order (0 = A, 1 = B, 2 = C: the order they arrived in)
 *   0x20 u32 sig0            0x24 u32 sig39
 *
 * The record identifies its bytes four independent ways - frame index, raw
 * offset, ring slot and the two signatures - so a certified frame can be tied
 * to the capture without the frame table, which is capped and can drop records.
 * It still carries NO conclusion: no channel, no hypothesis, no colour.
 *
 * ---- RETIRED FIELDS, which both parsers REFUSE when non-zero ---------------
 * The first implementation held the certified image for 60 further frames and
 * compared each one. That hold could only be served by 153 600-byte comparisons
 * inside the service window, and holding at all would have rotated the ring over
 * the very frames it was protecting (§V3.24). It is gone. Its header fields stay
 * at their offsets so nothing else moves, and they must be zero:
 *
 *   0x03E hold_frames_cfg    0x15C hold_frames    0x160 hold_seen
 *   flags bit 3 (HOLD_COMPLETE)
 *   frames_refused[7] (the retired PRE_BASELINE reason)
 *
 * 0x164 is REPURPOSED and named `sig_mismatches`: eligible frames whose
 * signature vector broke a run. It is a property of the search, not of a hold.
 */
#ifndef OPENGBP_GBP_VCOLDUMP_H
#define OPENGBP_GBP_VCOLDUMP_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_vcolor.h"
#include "gbp_vstate_probe.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ---- VERSION 1, AND WHEN IT FREEZES ---------------------------------------
 * The certified record grew from 32 to 40 bytes during implementation and the
 * version stayed 1. That was legitimate exactly once, and the reason is factual
 * rather than a preference: no OGBPCOL1 file had ever been checkpointed, none
 * had ever been produced by hardware, and nothing outside this tree had been
 * promised the old shape - so there was no v1 in the world to be incompatible
 * with.
 *
 * THAT ENDS AT THE IMPLEMENTATION CHECKPOINT. From the commit that introduces
 * this file, the v1 layout is FROZEN: every offset, every record size, every
 * retired field and every reserved byte below is the contract. A later change to
 * any of them is a NEW VERSION, never a silent edit of v1 - the OGBPSEQ1 family
 * (v2 to v5) exists precisely because that rule was kept there.
 */
#define GBP_VCOLDUMP_MAGIC        "OGBPCOL1"
#define GBP_VCOLDUMP_END          "OGBPCEND"
#define GBP_VCOLDUMP_VERSION      1u
#define GBP_VCOLDUMP_HEADER_SIZE  0x200u
#define GBP_VCOLDUMP_FOOTER_SIZE  12u
#define GBP_VCOLDUMP_FRAME_REC    48u
#define GBP_VCOLDUMP_CERT_REC     40u
#define GBP_VCOLDUMP_DIAG_REC     GBP_VSTATE_DIAG_REC_V4    /* 160, the shared R3 record */
#define GBP_VCOLDUMP_MAX_FRAMES   GBP_VCOLOR_MAX_FRAMES     /* 1024 */
#define GBP_VCOLDUMP_MAX_CERT     GBP_VCOLOR_CERT_FRAMES    /* 3 */
#define GBP_VCOLDUMP_MAX_DIAGS    GBP_VSTATE_MAX_DISAGREEMENTS  /* 256 */
/* Every count in the header is capped, including the one this experiment never
 * uses. An uncapped counter that happens to be safe because of an unrelated
 * offset check is a counter nobody is checking (microaudit §28). */
#define GBP_VCOLDUMP_MAX_AUDIO_RAW GBP_VSTATE_AUDIO_RAW_SLOTS    /* 3 */
#define GBP_VCOLDUMP_ID_FIELD     32u
#define GBP_VCOLDUMP_ID_MAX       31u
#define GBP_VCOLDUMP_CHUNK        0x10000u

#define GBP_VCOLDUMP_FLAG_SERVICE_OK       0x0001u
#define GBP_VCOLDUMP_FLAG_RESTORE_OK       0x0002u
#define GBP_VCOLDUMP_FLAG_CERTIFIED        0x0004u
#define GBP_VCOLDUMP_FLAG_HOLD_COMPLETE    0x0008u   /* RETIRED: must be 0 */
#define GBP_VCOLDUMP_FLAG_PARTIAL          0x0010u
#define GBP_VCOLDUMP_FLAG_STAGE_A_ABORTED  0x0020u
#define GBP_VCOLDUMP_FLAG_FRAME_TABLE_CAP  0x0040u
/* The run certified, but the ring slots holding A, B and C did not survive to
 * the teardown, so the raw could not be serialized. The file still carries the
 * frame table and the diagnostics; it carries NO raw and claims none. This
 * combination is the only way CERTIFIED and cert_count = 0 may appear together,
 * and both parsers enforce that (§V3.24). */
#define GBP_VCOLDUMP_FLAG_RAW_UNRECOVERABLE 0x0080u
#define GBP_VCOLDUMP_FLAG_ALL              0x00FFu

#define GBP_VCOLDUMP_RF_RESTORE_OK         0x0001u
#define GBP_VCOLDUMP_RF_HANDLER_RESTORED   0x0002u
#define GBP_VCOLDUMP_RF_MASK_OK            0x0004u
#define GBP_VCOLDUMP_RF_CONTROL_OK         0x0008u
#define GBP_VCOLDUMP_RF_PI_STICKY_FINAL    0x0010u
#define GBP_VCOLDUMP_RF_ARINFO_RESTORE_OK  0x0020u
#define GBP_VCOLDUMP_RF_POWER_CYCLE_REQ    0x0040u
#define GBP_VCOLDUMP_RF_ALL                0x007Fu

struct gbp_vcoldump_info {
    uint16_t version, header_size;
    uint32_t flags, tb_hz;
    uint32_t frame_count, cert_count, diag_count, audio_raw_count;
    uint32_t video_block_size, audio_block_size, blocks_per_frame;
    uint16_t frame_rec_size, cert_rec_size, diag_rec_size;
    uint16_t status_code, stop_reason, n_stable, cert_budget;
    uint16_t hold_frames_cfg;             /* RETIRED, always 0 */
    uint32_t off_frames, off_cert, off_diag, off_video_raw, off_audio_raw, off_footer;
    uint64_t t_control_transform, t_capture_start, t_stop, t_certified;
    uint64_t t_teardown_begin, t_teardown_end, capture_elapsed, safety_elapsed;
    uint64_t search_window_ticks, hard_wallclock_ticks;
    uint32_t max_deliveries, frame_table_cap;
    uint32_t deliveries, video_completed, audio_drains, isr_w1c, main_w1c;
    uint32_t frames_total, frames_eligible, frames_dropped, runs_reset;
    uint32_t hold_frames, hold_seen;      /* RETIRED, always 0 */
    uint32_t sig_mismatches;              /* 0x164: runs broken by a signature change */
    uint32_t run_len, run_first_index;
    uint32_t frames_refused[GBP_VCOLOR_REASONS];
    uint32_t disagreements_total, source_serviced, source_other, non_source;
    uint32_t diagnostics_preserved, diagnostics_not_preserved;
    uint32_t frames_quarantined, frames_source_deferred, errors;
    uint32_t control_orig, control_exp, restore_flags, intmr_final;
    uint64_t total_size;
    char test_id[GBP_VCOLDUMP_ID_FIELD];
    char build_id[GBP_VCOLDUMP_ID_FIELD];
    char app[GBP_VCOLDUMP_ID_FIELD];
    char commit[GBP_VCOLDUMP_ID_FIELD];
    int identity_error;
    uint32_t header_crc32, total_crc32;
};

/* Stores the four identities without truncation; returns 0 when all fit. */
int gbp_vcoldump_set_identity(struct gbp_vcoldump_info *info, const char *test_id,
                              const char *build_id, const char *app, const char *commit);

/* Fills the info from the capture state and computes every count, size and
 * offset with checked arithmetic. Returns 0, or -1 when something does not fit
 * (nothing is written in that case). */
int gbp_vcoldump_layout(struct gbp_vcoldump_info *info, const struct gbp_vcolor *c,
                        const struct gbp_vstate *st, const struct gbp_vstate_result *res,
                        const struct gbp_vstate_config *cfg);

typedef int (*gbp_vcoldump_sink)(void *ctx, const uint8_t *data, uint32_t len);

/* Streams the whole file through `sink` using `chunk` as the ONLY transient
 * buffer. Returns the bytes written, or -1 bad argument, -2 identity does not
 * fit, -3 layout overflow, -4 the sink refused (bytes written so far land in
 * *written, so a partial save can name exactly what reached the card). */
long gbp_vcoldump_stream(struct gbp_vcoldump_info *info, const struct gbp_vcolor *c,
                         const struct gbp_vstate *st, const struct gbp_vstate_result *res,
                         const struct gbp_vstate_config *cfg,
                         uint8_t *chunk, uint32_t chunk_cap,
                         gbp_vcoldump_sink sink, void *sink_ctx, uint64_t *written);

/* Strict parser. Negative codes: -1 too short / bad magic / truncation, -2
 * unsupported version, header size or record size, -3 header CRC mismatch, -4 a
 * section is misplaced, overlaps or leaves orphan bytes, -5 footer magic
 * missing, -6 total CRC mismatch, -7 an identity field breaks the rule, -8
 * reserved bytes not zero or an unknown flag, -9 a count or a field is out of
 * contract. */
int gbp_vcoldump_parse(const uint8_t *in, size_t n, struct gbp_vcoldump_info *info,
                       const uint8_t **frames, const uint8_t **cert, const uint8_t **diag,
                       const uint8_t **video_raw, const uint8_t **audio_raw);

/* Decoders for one serialized record. */
void gbp_vcoldump_decode_frame(const uint8_t *rec, struct gbp_vcolor_frame *out);
void gbp_vcoldump_decode_cert(const uint8_t *rec, struct gbp_vcolor_cert *out);

#ifdef __cplusplus
}
#endif
#endif
