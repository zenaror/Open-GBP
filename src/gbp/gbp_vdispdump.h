/*
 * gbp_vdispdump.h — OGBPDISP1, the downstream disposition sidecar
 * (HARDWARE_TESTS §V5.46). A NEW magic and a NEW file, never a version of
 * OGBPIDXCAP1: the source witness contract is frozen and this is a different
 * layer with a different population.
 *
 * A future physical run therefore delivers THREE artifacts, and all three are
 * needed for different reasons:
 *
 *   .log            WITQUAL and the aggregate counters; OGBPIDXCAP1 v1 does not
 *                   encode the qualification, so the log is still required
 *   OGBPIDXCAP1     the SOURCE scientific witness — what was preserved
 *   OGBPDISP1       the DOWNSTREAM trace — what happened to it afterwards
 *
 * The join is offline and by the generic key: `life.frame_index` here against
 * `record.frame_index` there. Nothing in this file decodes OGBPIDX1, and this
 * format carries no pixels — it duplicates none of the witness payload.
 *
 * ---- WHY VERSION 2 ---------------------------------------------------------
 *
 * v1 was designed around ONE downstream decision per source lifecycle. Policy A
 * introduces a NON-TERMINAL event -- a frame is deferred and handed off later --
 * and v1 cannot represent that without overloading `HOLD_PREVIOUS_FRAME` to
 * mean "temporarily deferred". That word already has a physical meaning in
 * run 5 (17 frames that were discarded), and reusing it would silently
 * reinterpret an existing capture. So the version is bumped instead.
 *
 * v2 adds: the defer aggregate on each lifecycle (first, last, count), a first
 * presentation-attempt timestamp, the DEFERRED and TERMINAL_PENDING
 * dispositions, and a header block of source-disposition counters whose
 * meanings do not overlap.
 *
 * It does NOT add a scientific-membership field. The population is the exact
 * `frame_index` join with OGBPIDXCAP1, and duplicating it here is what produced
 * the v1 off-by-one (GBP-VID-019/023).
 *
 * ---- INTEGRITY, AND WHERE IT IS NOT COMPUTED ------------------------------
 *
 * The lesson of OGBPIDXCAP1 is kept: NOTHING here runs in the capture path. The
 * whole file is serialized after the teardown, from fixed RAM, through a sink,
 * with one record as the only transient buffer. No CRC is computed while the
 * Game Boy Player is being serviced and no filesystem call exists in this
 * module's hot path, because this module has no hot path.
 *
 * Three CRC-32s, each answering a different question:
 *   header  is the geometry trustworthy at all
 *   section one per array, so damage is localised to lifecycles or to events
 *   global  everything before the footer magic, so nothing is missed
 */
#ifndef OPENGBP_GBP_VDISPDUMP_H
#define OPENGBP_GBP_VDISPDUMP_H

#include "gbp_vdisp.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_VDISPDUMP_MAGIC        "OGBPDISP"
#define GBP_VDISPDUMP_END          "OGBPDEND"
#define GBP_VDISPDUMP_VERSION      2u
#define GBP_VDISPDUMP_HEADER_SIZE  0x140u
#define GBP_VDISPDUMP_FOOTER_SIZE  12u
#define GBP_VDISPDUMP_LIFE_SIZE    128u
#define GBP_VDISPDUMP_EVENT_SIZE   40u
#define GBP_VDISPDUMP_ID_FIELD     32u

#define GBP_VDISPDUMP_F_INTACT             0x0001u
#define GBP_VDISPDUMP_F_LIFE_OVERFLOW      0x0002u
#define GBP_VDISPDUMP_F_EVENT_OVERFLOW     0x0004u
#define GBP_VDISPDUMP_F_DRAWDONE_UNMATCHED 0x0008u
#define GBP_VDISPDUMP_F_WINDOW_OPENED      0x0010u
#define GBP_VDISPDUMP_F_ORDER_VIOLATION    0x0020u
#define GBP_VDISPDUMP_F_INTERIOR_LOSS      0x0040u
#define GBP_VDISPDUMP_F_ALL                0x007Fu

struct gbp_vdispdump_info {
    uint16_t version, header_size;
    uint32_t flags;
    uint32_t life_record_size, event_record_size;
    uint32_t life_cap, life_n, event_cap, event_n;
    uint32_t life_overflow, event_overflow, drawdone_unmatched, decisions;
    uint32_t tb_hz, tex_slots, xfb_slots, window_first_frame;
    uint32_t off_life, off_events, off_footer, life_crc32, event_crc32;
    uint64_t total_size;
    /* §V5.49.6: source DISPOSITION, with non-overlapping meanings. None of
     * these is a display-cadence quantity and none may be read as one. */
    uint32_t source_handoffs, source_deferred_frames, source_defer_attempts;
    uint32_t source_dropped_interior, terminal_pending, max_deferred_depth;
    uint32_t order_violations;
    char test_id[GBP_VDISPDUMP_ID_FIELD];
    char build_id[GBP_VDISPDUMP_ID_FIELD];
    char app[GBP_VDISPDUMP_ID_FIELD];
    char commit[GBP_VDISPDUMP_ID_FIELD];
    int  identity_error;
    uint32_t header_crc32, total_crc32;
};

/* Stores the four identities without truncation; returns 0 when all fit. */
int gbp_vdispdump_set_identity(struct gbp_vdispdump_info *info, const char *test_id,
                               const char *build_id, const char *app, const char *commit);

/* Fills counts, sizes and offsets from the trace. Returns 0, or -1 on overflow. */
int gbp_vdispdump_layout(struct gbp_vdispdump_info *info, const struct gbp_vdisp *d,
                         uint32_t tb_hz, uint32_t xfb_slots);

typedef int (*gbp_vdispdump_sink)(void *ctx, const uint8_t *data, uint32_t len);

/* Streams the whole file through `sink` using `chunk` (>= the header size) as
 * the ONLY transient buffer. Returns bytes written, or a negative code:
 * -1 bad argument, -2 identity does not fit, -3 layout overflow, -4 the sink
 * refused (bytes written so far land in *written). */
long gbp_vdispdump_stream(struct gbp_vdispdump_info *info, const struct gbp_vdisp *d,
                          uint8_t *chunk, uint32_t chunk_cap,
                          gbp_vdispdump_sink sink, void *sink_ctx, uint64_t *written);

/* Strict parser. Negative codes: -1 too short or bad magic, -2 unsupported
 * version / header size / record size, -3 header CRC mismatch, -4 a section
 * falls outside the file, -5 footer magic missing, -6 global CRC mismatch,
 * -7 an identity field breaks the rule, -8 reserved bytes not zero,
 * -9 a section CRC mismatch, -10 an impossible count or flag combination. */
int gbp_vdispdump_parse(const uint8_t *in, size_t n, struct gbp_vdispdump_info *info,
                        const uint8_t **life, const uint8_t **events);

#ifdef __cplusplus
}
#endif
#endif
