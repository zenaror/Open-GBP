/*
 * gbp_vstate.h — the state model of GBP-VIDEO-002: the stateful frame
 * assembler, the bounded frame-signature store, the learned baseline, the
 * episode state machine, the bounded event store and the raw preservation
 * policy.
 *
 * Normative description: docs/research/HARDWARE_TESTS.md "GBP-VIDEO-002"
 * §5 (frame store), §6b (the three clocks and the three anomaly classes),
 * §9 (baseline), §10 (episodes), §11 (raw preservation), §12 (AUDIO),
 * §13 (segmentation), §14 (widths), §15 (events), §19 (caps), §20 (matrix),
 * §21 (memory budget).
 *
 * Policy-free with respect to the hardware: nothing here touches the
 * transport, allocates, logs, blocks or formats. The probe
 * (gbp_vstate_probe.c) runs the service loop and feeds this module one
 * VIDEO block at a time; this module decides what a frame is, whether the
 * stream is interpretable, what the baseline is and when a structured state
 * differs from the reference of the moment.
 *
 * THERE IS NO ORACLE HERE. An episode means "this frame's signature differs
 * from the reference signature of the moment" and nothing more. It never
 * means "the screen we came for was found": only the offline tool, reading
 * the private inputs, can say that. No reference table, checksum, pixel or
 * block range is embedded in this module or anywhere else in the runtime.
 *
 * WHAT IS DELIBERATELY NOT COLLAPSED (prompt §4, design §10): the frame
 * store and the event store filling END the run; the episode RAW store
 * filling does NOT. They are different conditions with different names,
 * different counters and different code paths.
 */
#ifndef OPENGBP_GBP_VSTATE_H
#define OPENGBP_GBP_VSTATE_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_vsig.h"
#include "gbp_transport.h"   /* GBP_BLOCK_SIZE: the diagnostic keeps one whole register window */

#ifdef __cplusplus
extern "C" {
#endif

/* ---- design constants (operational bounds; none is a GBP property) ---- */
#define GBP_VSTATE_VIDEO_BLOCK_SIZE   GBP_VSIG_BLOCK_SIZE     /* 0xF00 */
#define GBP_VSTATE_AUDIO_BLOCK_SIZE   0x1000u
#define GBP_VSTATE_FRAME_SIGS         40u    /* checksums kept per frame (the references' block count) */
#define GBP_VSTATE_FRAME_MAX_BLOCKS   48u    /* a raw ring slot: 48 so an over-long interval is still captured whole */
#define GBP_VSTATE_MAX_FRAMES         16384u /* 16384 x 192 B = 3.00 MiB */
#define GBP_VSTATE_FRAME_REC          192u   /* bytes of one frame record, in RAM and in the sidecar */
#define GBP_VSTATE_MAX_EVENTS         4096u  /* 4096 x 64 B = 0.25 MiB */
#define GBP_VSTATE_EVENT_REC          64u
#define GBP_VSTATE_MAX_EPISODES       4u
#define GBP_VSTATE_EPISODE_MAX_FRAMES 60u
#define GBP_VSTATE_N_STABLE           3u     /* the same evidence threshold the baseline uses */
#define GBP_VSTATE_BASELINE_FRAMES    3u
#define GBP_VSTATE_RAW_RING_SLOTS     3u     /* previous closed frame, frame just closed, frame filling */
#define GBP_VSTATE_EPISODE_RAW_SLOTS  4u     /* per episode: reference, first changed, context, stable */
#define GBP_VSTATE_RAW_FRAME_BYTES    (GBP_VSTATE_FRAME_MAX_BLOCKS * GBP_VSTATE_VIDEO_BLOCK_SIZE)   /* 184320 */
#define GBP_VSTATE_RAW_RING_BYTES     (GBP_VSTATE_RAW_RING_SLOTS * GBP_VSTATE_RAW_FRAME_BYTES)      /* 552960 = 0.53 MiB */
#define GBP_VSTATE_EPISODE_RAW_BYTES  (GBP_VSTATE_MAX_EPISODES * GBP_VSTATE_EPISODE_RAW_SLOTS * GBP_VSTATE_RAW_FRAME_BYTES)
                                                                                                     /* 2949120 = 2.81 MiB */
/* AUDIO raw: the first successful drain, then a ping-pong pair for the last successful one.
 * The design's budget line says "first + last, 2 x 0x1000"; two buffers cannot satisfy its own
 * rule that a failed drain never overwrites a valid capture, because a drain writes before its
 * status is known. Three buffers do, at 12 KiB, which still rounds to the same 0.01 MiB. */
#define GBP_VSTATE_AUDIO_RAW_SLOTS    3u
#define GBP_VSTATE_AUDIO_RAW_BYTES    (GBP_VSTATE_AUDIO_RAW_SLOTS * GBP_VSTATE_AUDIO_BLOCK_SIZE)

/* ---- frame classification ------------------------------------------- */
enum gbp_vstate_completeness {
    GBP_VSTATE_FRAME_UNKNOWN = 0,       /* still open, or closed with no usable origin (resync region) */
    GBP_VSTATE_FRAME_COMPLETE_40,       /* exactly 40 blocks between two OBSERVED boundaries */
    GBP_VSTATE_FRAME_INCOMPLETE_SHORT,  /* a boundary arrived before the 40th block */
    GBP_VSTATE_FRAME_INCOMPLETE_LONG,   /* more than 40 blocks, or 48 with no boundary at all */
    GBP_VSTATE_FRAME_PREDICATE_ANOMALY, /* a disagreement coincided with an interval that is not 40 */
    GBP_VSTATE_FRAME_RESYNC             /* discarded while the assembler had no anchor */
};

/* Frame flags. COMPLETE is never set because 40 was assumed: it is set only when two observed
 * boundaries really delimited 40 VIDEO blocks. */
#define GBP_VSTATE_F_COMPLETE        0x0001u
#define GBP_VSTATE_F_DISAGREEMENT    0x0002u   /* Disc = 1, GBI = 0 on some block of this frame */
#define GBP_VSTATE_F_ANOMALY         0x0004u   /* class (a): frame-invalidating */
#define GBP_VSTATE_F_PRE_BASELINE    0x0008u   /* observed before baseline_valid */
#define GBP_VSTATE_F_RESYNC          0x0010u   /* class (b): region-invalidating, the clock is paused */
#define GBP_VSTATE_F_EARLY_CANDIDATE 0x0020u
#define GBP_VSTATE_F_OVERLONG        0x0040u   /* more than 40 blocks: the first 40 signatures are stored */
#define GBP_VSTATE_F_RAW_PRESERVED   0x0080u
#define GBP_VSTATE_F_BASELINE        0x0100u   /* one of the frames that formed the baseline */
#define GBP_VSTATE_F_COUNTED         0x0200u   /* its duration was added to valid_observation_elapsed */
#define GBP_VSTATE_F_TAIL            0x0400u   /* observed during the bounded finalisation tail */
#define GBP_VSTATE_F_EPISODE_CHANGE  0x0800u   /* the frame that opened an episode */
#define GBP_VSTATE_F_MAJORITY_EXTRA  0x1000u   /* §R3.12: contains a VIDEO block drained ONLY
                                                * because the majority carried a source the Disc
                                                * reading did not. Always set together with
                                                * F_ANOMALY: quarantined from every scientific use */
/* Per-block provenance (§R3.11). The store carries no per-block flag word, so
 * the marker is a one-shot on the state consumed by the next block and then
 * recorded on the frame that consumed it and in the diagnostic record. */
#define GBP_VSTATE_B_MAJORITY_EXTRA  0x0001u
#define GBP_VSTATE_F_SOURCE_DEFERRED 0x2000u   /* §R3.13/§R3.29: a disagreement inside this frame
                                                * deferred a VIDEO drain. DESCRIPTIVE ONLY - it does
                                                * not change completeness, fabricate a block, claim
                                                * recovery, or feed any stop rule */
#define GBP_VSTATE_F_EPISODE_STABLE  0x1000u   /* the frame that closed an episode as stable */

/* Exactly 192 bytes, by construction and by a compile-time check in the .c. */
struct gbp_vstate_frame {
    uint64_t t_first_block;      /* 0x00 time base at the first block of the interval */
    uint64_t t_last_block;       /* 0x08 time base at the last block of the interval */
    uint32_t index;              /* 0x10 0-based frame index, monotonic */
    uint32_t episode;            /* 0x14 1-based episode this frame belongs to, 0 = none */
    uint16_t blocks;             /* 0x18 VIDEO blocks the interval carried (may exceed 40) */
    uint16_t flags;              /* 0x1A GBP_VSTATE_F_* */
    uint16_t disagreements;      /* 0x1C predicate disagreements inside this frame */
    uint16_t completeness;       /* 0x1E enum gbp_vstate_completeness */
    uint32_t sig[GBP_VSTATE_FRAME_SIGS];   /* 0x20..0xBF the 40 semantic block signatures */
};

/* ---- events ---------------------------------------------------------- */
enum gbp_vstate_event_type {
    GBP_VSTATE_EV_NONE = 0,
    GBP_VSTATE_EV_CAPTURE_START,
    GBP_VSTATE_EV_BASELINE_CANDIDATE,
    GBP_VSTATE_EV_BASELINE_VALID,
    GBP_VSTATE_EV_EARLY_CANDIDATE,
    GBP_VSTATE_EV_PREDICATE_DISAGREEMENT,
    GBP_VSTATE_EV_INCOMPLETE_INTERVAL,
    GBP_VSTATE_EV_RESYNC,
    GBP_VSTATE_EV_EPISODE_OPEN,
    GBP_VSTATE_EV_EPISODE_STABILISING,
    GBP_VSTATE_EV_EPISODE_STABLE,
    GBP_VSTATE_EV_EPISODE_CLOSE,
    GBP_VSTATE_EV_EPISODE_STORE_FULL,
    GBP_VSTATE_EV_ANOMALY,
    GBP_VSTATE_EV_CAP_REACHED,
    GBP_VSTATE_EV_SAFETY_BUDGET,
    GBP_VSTATE_EV_SCIENTIFIC_TARGET,
    GBP_VSTATE_EV_TAIL_BEGIN,
    GBP_VSTATE_EV_STOP,
    GBP_VSTATE_EV_TEARDOWN_BEGIN,
    GBP_VSTATE_EV_TEARDOWN_END
};

/* Exactly 64 bytes. `seq` is the monotonic sequence number assigned when the event is recorded
 * and it — not the timestamp — defines the order: two events can legitimately share one tick. */
struct gbp_vstate_event {
    uint64_t t;                  /* 0x00 */
    uint32_t seq;                /* 0x08 */
    uint16_t type;               /* 0x0C enum gbp_vstate_event_type */
    uint16_t flags;              /* 0x0E */
    uint32_t a, b, c, d;         /* 0x10 small fixed payload, meaning per type */
    uint32_t frame;              /* 0x20 frame index at the moment of the event */
    uint32_t episode;            /* 0x24 1-based episode, 0 = none */
    uint32_t e, f;               /* 0x28 */
    uint64_t t2;                 /* 0x30 a second timestamp when the type carries one */
    uint32_t g, h;               /* 0x38 */
};

/* ---- episodes -------------------------------------------------------- */
enum gbp_vstate_episode_state {
    GBP_VSTATE_EP_ARMED = 0,     /* the current signature equals current_reference_signature */
    GBP_VSTATE_EP_CHANGED,       /* a differing frame opened an episode (candidate = that signature) */
    GBP_VSTATE_EP_STABILISING,   /* counting repeats of the candidate */
    GBP_VSTATE_EP_CLOSED
};

#define GBP_VSTATE_EPF_STABLE_FOUND       0x0001u
#define GBP_VSTATE_EPF_CAPPED             0x0002u   /* closed at EPISODE_MAX_FRAMES, unstable */
#define GBP_VSTATE_EPF_RAW_PRESERVED      0x0004u
#define GBP_VSTATE_EPF_NOT_PRESERVED      0x0008u   /* opened after the raw store filled */
#define GBP_VSTATE_EPF_TRUNCATED_BY_SAFETY 0x0010u  /* the hard wall-clock cap closed it */
#define GBP_VSTATE_EPF_TAIL               0x0020u   /* it was still open when the scientific target arrived */
#define GBP_VSTATE_EPF_EARLY              0x0040u   /* pre-baseline EARLY_CANDIDATE, not a post-baseline episode */
/* High bit of an episode index: the episode was tracked in full but has no descriptor and no raw,
 * because the episode raw store had filled. Monitoring never stops for that reason. */
#define GBP_VSTATE_EPISODE_SHADOW 0x80000000u

struct gbp_vstate_episode {
    uint32_t index;              /* 1-based */
    uint32_t state;              /* enum gbp_vstate_episode_state */
    uint32_t flags;
    uint32_t open_frame, close_frame;
    uint64_t t_open, t_close;
    uint32_t frames;             /* frames observed while the episode was open */
    uint32_t stable_count;       /* consecutive repeats of `candidate` */
    uint32_t raw_slot;           /* first episode raw slot used, or 0xFFFFFFFF */
    uint32_t raw_frames;         /* raw frames actually preserved (<= GBP_VSTATE_EPISODE_RAW_SLOTS) */
    uint32_t raw_frame_index[GBP_VSTATE_EPISODE_RAW_SLOTS];  /* the frame index each preserved slot holds */
    uint32_t raw_frame_blocks[GBP_VSTATE_EPISODE_RAW_SLOTS]; /* blocks stored in that slot */
    uint32_t candidate[GBP_VSTATE_FRAME_SIGS];   /* the signature being counted */
    uint32_t final_sig[GBP_VSTATE_FRAME_SIGS];   /* the signature the episode settled on (stable only) */
};

/* ---- AUDIO aggregate policy (§12/§22): counters only, never a record per drain ---- */
struct gbp_vstate_audio {
    uint32_t selected, attempted, completed, failures;
    uint64_t bytes;
    int first_valid;             /* slot 0 holds a completed drain */
    int last_valid;              /* -1 none; else the ping-pong slot (1 or 2) of the last completed drain */
    unsigned last_next;          /* the ping-pong slot the next drain beyond the first targets */
    uint32_t first_crc32, last_crc32;
    uint64_t first_cycle, last_cycle;
};


/* ---- the semantic-disagreement diagnostic (U-GBP-032) ----------------
 * GBP-VIDEO-002's first physical run aborted at cycle 51750 because the two
 * readings of one 32-byte IRQ-register window disagreed, and the bytes that
 * caused it were never recorded. This record fixes that, and ONLY that: it is
 * purely observational. It changes nothing about when a disagreement happens,
 * what it means, or that it is fatal.
 *
 * The two readings, unchanged (src/gbp/gbp_rawlog.c):
 *   Disc : (block[0x1D] << 8) | block[0x1F]   - the LAST replica, two bytes.
 *   GBI  : a BITWISE majority over the eight replicas at offsets 4k+1 (high
 *          byte) and 4k+3 (low byte), k = 0..7; a bit is 1 only when strictly
 *          more than four of the eight carry it, so a tie at four resolves to
 *          0 and the result need not equal any replica that was actually read.
 * Everything else about the window - bytes at offsets 4k+0 and 4k+2 - is read
 * by neither, which is where all 220 deviations logged so far have landed.
 *
 * The bytes are copied from the buffer the transport already filled. NO extra
 * read, no re-read, no retry: the capture cannot change the number or the
 * order of hardware operations. Exactly one record is kept - the first
 * disagreement ends the run, so a second can only mean a defect, and the first
 * is never overwritten. */
#define GBP_VSTATE_DIAG_REC 96u          /* the v3 record: still the first 96 bytes of v4 */
#define GBP_VSTATE_DIAG_REC_V4 160u      /* HARDWARE_TESTS GBP-VIDEO-002-R3 §R3.24 */
#define GBP_VSTATE_MAX_DISAGREEMENTS 256u /* §R3.15: chosen from footprint, not from a rate */

/* ---- the masks, from docs/protocol/REGISTERS.md §4 (§R3.1) -------------
 * Exhaustive and disjoint: SRC|ODD|HIGH|BIT15 == 0xFFFF. Nothing here is new
 * vocabulary; the probes already configure exactly these values. */
#define GBP_VSTATE_SRC_MASK   0x0555u    /* the six even source slots */
#define GBP_VSTATE_AV_MASK    0x0500u    /* VIDEO 0x0100 + AUDIO 0x0400: the ONLY drained sources */
#define GBP_VSTATE_ODD_MASK   0x0AAAu
#define GBP_VSTATE_HIGH_MASK  0x7000u
#define GBP_VSTATE_BIT15_MASK 0x8000u
#define GBP_VSTATE_SRC_VIDEO  0x0100u
#define GBP_VSTATE_SRC_AUDIO  0x0400u

/* ---- how a disagreement is classified (§R3.2). 0 is NOT a valid stored value. */
#define GBP_VSTATE_DIS_NONE            0u
#define GBP_VSTATE_DIS_SOURCE_SERVICED 1u   /* delta confined to AV_MASK -> NONFATAL */
#define GBP_VSTATE_DIS_SOURCE_OTHER    2u   /* a source slot with no drain -> FATAL */
#define GBP_VSTATE_DIS_NON_SOURCE      3u   /* odd / bit15 / high differ    -> FATAL */

/* ---- follow-up, purely descriptive (§R3.7). No state is derived from any
 * divisor of an observed gap, and none asserts that a source could not be new. */
#define GBP_VSTATE_FU_PENDING            0u  /* never allowed in a serialized file */
#define GBP_VSTATE_FU_SOURCE_PRESENT_NEXT 1u
#define GBP_VSTATE_FU_SOURCE_ABSENT_NEXT 2u
#define GBP_VSTATE_FU_NO_NEXT_CAUSE      3u
#define GBP_VSTATE_FU_UNKNOWN            4u
#define GBP_VSTATE_FUR_NONE              0u
#define GBP_VSTATE_FUR_OBSERVATIONAL     1u
#define GBP_VSTATE_FUR_RUN_ABORTED       2u
#define GBP_VSTATE_FUR_NOT_APPLICABLE    3u  /* the majority omitted nothing */
#define GBP_VSTATE_FUR_INTERNAL          4u

/* ---- record_flags (§R3.24). Bits 8..15 are reserved and must stay zero. */
#define GBP_VSTATE_DF_FOLLOWUP_FILLED    0x0001u
#define GBP_VSTATE_DF_PAYLOAD_VALID      0x0002u
#define GBP_VSTATE_DF_PAYLOAD_SECOND     0x0004u
#define GBP_VSTATE_DF_FRAME_QUARANTINED  0x0008u
#define GBP_VSTATE_DF_SOURCE_DEFERRED    0x0010u
#define GBP_VSTATE_DF_SERVICE_INCOMPLETE 0x0020u
#define GBP_VSTATE_DF_ACK_WRITTEN        0x0040u
#define GBP_VSTATE_DF_REARM_WRITTEN      0x0080u
#define GBP_VSTATE_DF_ALL                0x00FFu   /* the v4 set: bits 8..15 reserved, zero */
/* v5 only (§R4.8). The service decision of a cycle was written to THIS record.
 * Without it `service_selected == 0` would be ambiguous between "no source was
 * selected" and "no decision was ever recorded here" - which is exactly the kind
 * of zero the v5 contract refuses to leave undecidable. A v4 file must still
 * carry zero in bits 8..15 and its parser still refuses anything else. */
#define GBP_VSTATE_DF_SERVICE_WRITTEN    0x0100u
#define GBP_VSTATE_DF_ALL_V5             0x01FFu

#define GBP_VSTATE_GAP_NONE   0xFFFFFFFFu /* sentinel: no gap has been measured */
#define GBP_VSTATE_GAP_SAT    0xFFFFFFFEu /* saturation instead of a silent wrap */
#define GBP_VSTATE_GAP_SLOTS  6u          /* one per SRC_MASK bit, ascending */
#define GBP_VSTATE_HIST_ENTRIES 64u
#define GBP_VSTATE_DIAG_LOG_MAX 8u        /* records printed in full in the ring log */       /* the six source bits compressed to six index bits */

/* which read produced the disagreement; the value is recorded, never inferred */
#define GBP_VSTATE_DIAG_READ_LEAN     0u /* the lean cycle's own IRQ read */
#define GBP_VSTATE_DIAG_READ_PRESVC   1u /* a verify cycle's PRESVC snapshot */
#define GBP_VSTATE_DIAG_READ_POSTDRAIN 2u
#define GBP_VSTATE_DIAG_READ_POSTACK  3u
#define GBP_VSTATE_DIAG_READ_OTHER    4u

struct gbp_vstate_diag {
    uint64_t t;                  /* 0x00 the u64 time base at the read */
    uint32_t cycle;              /* 0x08 delivery ordinal */
    uint32_t valid;              /* 0x0C 1 once captured; first wins, never overwritten */
    uint16_t disc_value;         /* 0x10 what the runtime computed, persisted so the */
    uint16_t gbi_value;          /* 0x12 offline tool can prove it recomputes the same */
    uint16_t read_kind;          /* 0x14 GBP_VSTATE_DIAG_READ_* */
    uint16_t attempts;           /* 0x16 disagreements seen (a second one would be a defect) */
    uint8_t raw[GBP_BLOCK_SIZE]; /* 0x18..0x37 the 32 bytes VERBATIM, before any reduction */
    uint32_t intsr_entry;        /* 0x38 from the ISR record already in RAM */
    uint32_t intsr_after_w1c;    /* 0x3C */
    uint32_t intmr_entry;        /* 0x40 */
    uint32_t latency_ticks;      /* 0x44 */
    uint32_t xfer_ticks;         /* 0x48 transport info of THAT read */
    uint16_t xfer_polls;         /* 0x4C */
    uint16_t dma_status;         /* 0x4E */
    uint16_t dma_status_before;  /* 0x50 */
    uint16_t control_exp;        /* 0x52 the CONTROL byte the stage established */
    uint32_t frame_index;        /* 0x54 frame being assembled */
    uint32_t block_in_frame;     /* 0x58 */
    uint32_t reserved;           /* 0x5C zero */
    /* ---- the v4 extension, 0x60..0x9F (§R3.24). Every field's validity is
     * governed by record_flags or followup_state, never by its own value. */
    uint16_t delta;                  /* 0x60 disc ^ gbi; always valid */
    uint16_t disc_extra_sources;     /* 0x62 disc & ~gbi & SRC_MASK */
    uint16_t majority_extra_sources; /* 0x64 gbi & ~disc & SRC_MASK */
    uint16_t classification;         /* 0x66 GBP_VSTATE_DIS_*, never 0 once stored */
    uint16_t authoritative_value;    /* 0x68 the composed u16 of §R3.3 */
    uint16_t ack_value;              /* 0x6A valid iff DF_ACK_WRITTEN */
    uint16_t service_selected;       /* 0x6C sources actually drained; 0 IS a measurement */
    uint16_t record_flags;           /* 0x6E GBP_VSTATE_DF_* */
    uint64_t t_ack;                  /* 0x70 valid iff DF_ACK_WRITTEN */
    uint64_t t_rearm;                /* 0x78 valid iff DF_REARM_WRITTEN */
    uint64_t t_next_cause;           /* 0x80 valid iff followup_state is PRESENT/ABSENT */
    uint16_t next_pending_gbi;       /* 0x88 same validity */
    uint16_t next_pending_disc;      /* 0x8A same validity */
    uint8_t followup_state;          /* 0x8C GBP_VSTATE_FU_* */
    uint8_t followup_reason;         /* 0x8D GBP_VSTATE_FUR_* */
    uint16_t payload_source;         /* 0x8E the ONE source the payload describes, or 0 */
    uint32_t payload_crc32;          /* 0x90 valid iff DF_PAYLOAD_VALID */
    uint32_t payload_first_word;     /* 0x94 valid iff DF_PAYLOAD_VALID */
    uint32_t gap_min_before_ticks;   /* 0x98 GBP_VSTATE_GAP_NONE when gap_count_before == 0 */
    uint16_t gap_count_before;       /* 0x9C 0 means "no statistic", never "a zero gap" */
    uint16_t reserved1;              /* 0x9E zero */
};

/* Per-source cause->cause statistics (§R3.28). Measurements of ONE run; nothing
 * here is a physical bound and no runtime decision reads them. */
struct gbp_vstate_gap {
    uint64_t last_cause_t;  /* RAM only; the wire carries the derived values */
    uint32_t count;         /* number of GAPS, so a source seen once has count 0 */
    uint32_t min_ticks;     /* GBP_VSTATE_GAP_NONE while count == 0 */
    uint32_t max_ticks;
    uint32_t last_ticks;
};

/* The aggregate counters of the semantic block, in the normative order of §R3.27. */
struct gbp_vstate_semantic {
    uint32_t disagreements_total;
    uint32_t source_serviced;
    uint32_t source_other;
    uint32_t non_source;
    uint32_t disc_extra_events;
    uint32_t majority_extra_events;
    uint32_t both_direction_events;
    uint32_t majority_extra_video_services;
    uint32_t majority_extra_audio_services;
    uint32_t frames_quarantined;
    uint32_t frames_source_deferred;
    uint32_t diagnostics_preserved;
    uint32_t diagnostics_not_preserved;
    uint32_t followup_present;
    uint32_t followup_absent;
    uint32_t followup_no_next;
    uint32_t followup_unknown;
    uint32_t observational_disagreements;
    uint32_t service_selecting_disagreements;
    uint32_t payload_diagnostics_captured;
    uint32_t service_incomplete_events;
    /* Not one of the 21 serialized counters: a RAM-side convenience that the
     * offline tool re-derives per record from disc_extra_sources and
     * next_pending_gbi. Kept so the on-screen summary can say it without
     * re-walking the store. */
    uint32_t followup_partial;
    /* not serialized as counters: the flag lives in the block's own flags word */
    uint32_t store_capped;
    struct gbp_vstate_gap gap[GBP_VSTATE_GAP_SLOTS];
    uint32_t delta_hist[GBP_VSTATE_HIST_ENTRIES];
    uint32_t disc_extra_hist[GBP_VSTATE_HIST_ENTRIES];
    uint32_t majority_extra_hist[GBP_VSTATE_HIST_ENTRIES];
};

/* ---- the whole state ------------------------------------------------- */
struct gbp_vstate {
    /* caller-owned storage, all static, none allocated here */
    struct gbp_vstate_frame *frames;     /* GBP_VSTATE_MAX_FRAMES entries */
    uint32_t frames_cap;
    struct gbp_vstate_event *events;     /* GBP_VSTATE_MAX_EVENTS entries */
    uint32_t events_cap;
    uint8_t *raw_ring;                   /* GBP_VSTATE_RAW_RING_BYTES, 32-byte aligned */
    uint32_t raw_ring_cap;
    uint8_t *episode_raw;                /* GBP_VSTATE_EPISODE_RAW_BYTES, 32-byte aligned */
    uint32_t episode_raw_cap;
    uint8_t *audio_raw;                  /* GBP_VSTATE_AUDIO_RAW_BYTES, 32-byte aligned */
    uint32_t audio_raw_cap;

    /* frame store */
    uint32_t frames_n;                   /* frames closed and stored */
    int frame_store_full;                /* the store filled: the run stops (never an overwrite, never a wrap) */

    /* event store */
    uint32_t events_n;
    uint32_t event_seq;                  /* monotonic, assigned at record time; defines the order */
    int event_store_full;                /* the store filled: the run stops */
    uint32_t events_dropped;             /* events refused after the store filled (never silently lost) */

    /* frame assembler.
     * `asm_state` is about the ANCHOR — whether a Disc boundary has told the assembler where a
     * frame starts — and `resync_pending` is about the CLOCK, which stays paused until a clean
     * complete frame closes. They are separate because a region anomaly can leave the assembler
     * perfectly anchored (a boundary arrived, just at an unexpected position) while the
     * observation is no longer interpretable. */
    int asm_state;                       /* 0 seeking (no anchor), 1 in-frame (anchored) */
    int resync_pending;                  /* class (b) in force: valid observation is paused */
    uint32_t cur_blocks;                 /* blocks accumulated in the frame being assembled */
    uint32_t cur_slot;                   /* raw ring slot the current frame fills */
    uint64_t cur_t_first, cur_t_last;
    uint16_t cur_disagreements;
    uint16_t cur_flags;
    uint32_t cur_sig[GBP_VSTATE_FRAME_SIGS];
    uint32_t blocks_before_first_boundary;
    uint64_t blocks_total;               /* every VIDEO block fed in */

    /* segmentation statistics */
    uint32_t boundaries_disc, boundaries_gbi;
    uint32_t disagreements_total;
    uint32_t disagreement_first_frame, disagreement_first_block;
    uint8_t disagreement_first4[4];
    int disagreement_seen;
    uint32_t interval_hist[GBP_VSTATE_FRAME_MAX_BLOCKS + 2u];   /* observed boundary-to-boundary intervals; index 49 = "no boundary in 48" */

    /* anomaly accounting, three classes, never merged */
    uint32_t anomalies_frame;            /* class (a) */
    uint32_t anomalies_region;           /* class (b) */
    uint32_t resync_frames;              /* frames discarded or skipped while resynchronising */
    uint32_t frames_complete, frames_incomplete;

    /* baseline */
    int baseline_valid;
    uint32_t baseline_frames_seen;       /* consecutive identical complete frames so far */
    uint32_t baseline_frame_index;       /* the frame that completed the baseline */
    uint64_t t_baseline_valid;
    uint32_t original_baseline_sig[GBP_VSTATE_FRAME_SIGS];   /* fixed at baseline_valid, NEVER overwritten */
    uint32_t current_reference_sig[GBP_VSTATE_FRAME_SIGS];   /* advances to each closed episode's final signature */
    uint32_t reference_updates;

    /* episodes */
    struct gbp_vstate_episode episodes[GBP_VSTATE_MAX_EPISODES];
    /* An episode opened after the descriptors ran out is still tracked in full — it must be, or
     * current_reference_signature would stop advancing and every later frame would be compared
     * against a stale state. It runs in `shadow`, is counted in episodes_not_preserved and keeps
     * no raw. This is what makes "the episode raw store filled" different from a store cap. */
    struct gbp_vstate_episode shadow;
    uint32_t episodes_n;                 /* episodes with a descriptor (<= MAX_EPISODES) */
    uint32_t episode_count;              /* episodes OPENED, including those with no descriptor left */
    uint32_t stable_episodes, unstable_episodes;
    uint32_t episodes_not_preserved;     /* opened after the raw store filled */
    int episode_store_full;              /* the episode RAW store filled: monitoring CONTINUES */
    int episode_open;                    /* an episode is open right now */
    int episode_shadow_active;           /* the open episode has no descriptor and no raw (see `shadow`) */
    uint32_t episode_cur;                /* index of the open episode, 0 = none. A descriptor episode uses
                                          * its 1-based descriptor number; an episode with no descriptor
                                          * uses GBP_VSTATE_EPISODE_SHADOW | ordinal, so the two can never
                                          * be confused in a frame record, an event or the sidecar. */
    uint32_t early_candidates;
    uint32_t episode_raw_used;           /* episode raw slots consumed */

    /* the finalisation tail (the scientific target arrived with an episode open) */
    int tail_active;
    uint32_t tail_frames;
    uint64_t tail_t_begin, tail_ticks;
    int tail_truncated_by_cap;

    /* the scientific clock (all u64) */
    uint64_t t_capture_start;
    uint64_t valid_observation_elapsed;  /* accumulated, the ONLY quantity the negative result uses */
    uint32_t frames_counted;             /* frames whose duration was added */

    /* AUDIO */
    struct gbp_vstate_audio audio;

    /* signature cost */
    struct gbp_vsig_cost cost;

    /* ---- the semantic-disagreement store (U-GBP-032 answered; §R3.15) ----
     * Caller-owned, bounded, never allocated here, never written per delivery.
     * `diag` stays as the FIRST record so every v3-era reader of this struct
     * keeps working; the array is the same type. */
    struct gbp_vstate_diag *diags;       /* GBP_VSTATE_MAX_DISAGREEMENTS entries */
    uint32_t diags_cap;
    uint32_t diags_n;                    /* records actually stored (<= cap) */
    /* The follow-up waiter: the ONE record armed after a written re-arm and
     * waiting for the next ordinary read (§R4.3). It is a SEPARATE lifetime from
     * the service handle of a transaction, it receives ONLY t_next_cause,
     * next_pending_*, followup_state/reason and DF_FOLLOWUP_FILLED, and no
     * current-cycle setter may ever resolve through it. -1 when none. */
    int32_t diag_wait;
    uint32_t next_block_majority_extra;  /* one-shot provenance for the next VIDEO block */
    struct gbp_vstate_semantic sem;      /* aggregate counters, gap stats, histograms */
    /* There is deliberately NO second copy of "the first record": the store is
     * the single source of truth, and gbp_vstate_diag_first() reads diags[0]. */

    /* the previous closed frame's ring slot and identity, for "the last reference frame" */
    int prev_slot;                       /* -1 none */
    uint32_t prev_frame_index, prev_frame_blocks;
    int prev_frame_clean;
};

/* ---- lifecycle ------------------------------------------------------- */
void gbp_vstate_init(struct gbp_vstate *s,
                     struct gbp_vstate_frame *frames, uint32_t frames_cap,
                     struct gbp_vstate_event *events, uint32_t events_cap,
                     uint8_t *raw_ring, uint32_t raw_ring_cap,
                     uint8_t *episode_raw, uint32_t episode_raw_cap,
                     uint8_t *audio_raw, uint32_t audio_raw_cap);
/* 1 when every buffer is present and large enough (the probe refuses to run otherwise). */
int gbp_vstate_storage_ok(const struct gbp_vstate *s);

/* ---- events ---------------------------------------------------------- */
/* Records one event. Returns the sequence number, or 0 when the store is full (events_dropped
 * is incremented; nothing is overwritten). */
uint32_t gbp_vstate_event(struct gbp_vstate *s, uint64_t t, enum gbp_vstate_event_type type,
                          uint32_t a, uint32_t b, uint32_t c, uint32_t d);
const char *gbp_vstate_event_name(unsigned type);

/* ---- the raw working ring -------------------------------------------- */
/* Destination of the next VIDEO DMA: the current ring slot at the current block position.
 * NULL when the frame already holds GBP_VSTATE_FRAME_MAX_BLOCKS blocks — the caller must close
 * the frame first, which gbp_vstate_block() does automatically before it returns a target. */
uint8_t *gbp_vstate_video_target(struct gbp_vstate *s);
/* Byte address of one block of one ring slot / one episode raw slot (read-only helpers). */
const uint8_t *gbp_vstate_ring_block(const struct gbp_vstate *s, uint32_t slot, uint32_t block);
const uint8_t *gbp_vstate_episode_block(const struct gbp_vstate *s, uint32_t raw_slot, uint32_t block);

/* ---- feeding the assembler ------------------------------------------- */
/* What the caller learns after feeding one block. */
struct gbp_vstate_step {
    int frame_closed;            /* a frame was closed by this block */
    uint32_t frame_index;        /* its index, when frame_closed */
    int frame_complete;          /* it closed COMPLETE_40 and clean */
    int counted;                 /* its duration was added to valid_observation_elapsed */
    int episode_opened, episode_closed, episode_stable;
    int early_candidate;
    int resync;                  /* a region anomaly was raised */
    int frame_store_full, event_store_full;   /* set when this step filled one of the two stores */
    int episode_store_full;                   /* set when this step exhausted the episode RAW store */
};

/* One VIDEO block, already in the ring slot gbp_vstate_video_target() returned.
 * `t` is the u64 time base at the end of that block's DMA; `first4` the raw first four bytes.
 * The signature is computed here, from the block in the ring, and its cost in ticks is passed
 * in by the caller (which measured it) — this function never reads a clock.
 * Returns 0, or -1 when the block could not be accepted (no target, bad state). */
int gbp_vstate_block(struct gbp_vstate *s, const uint8_t *block, uint32_t len, const uint8_t first4[4],
                     uint64_t t, uint32_t sig, uint32_t sig_cost_ticks, struct gbp_vstate_step *step);

/* Marks the NEXT block handed to gbp_vstate_block() as drained only because the
 * majority carried a source the Disc reading did not (§R3.11). One-shot: it is
 * consumed by that call. The frame that receives such a block is quarantined -
 * F_MAJORITY_EXTRA plus F_ANOMALY - so it never counts toward valid observation,
 * never forms a baseline and never validates a structured change. */
void gbp_vstate_block_majority_extra(struct gbp_vstate *s);
/* Marks the frame being assembled, if any, as having deferred a VIDEO drain
 * (§R3.13/§R3.29). Descriptive: it changes no completeness and fabricates
 * nothing. With no frame open it does nothing and creates no frame. Returns 1
 * when a frame was marked. */
int gbp_vstate_mark_source_deferred(struct gbp_vstate *s);

/* The scientific target arrived. With no episode open the caller stops; with one open this opens
 * the bounded finalisation tail (no new episode may open, the current one closes on stabilisation
 * or at EPISODE_MAX_FRAMES). Returns 1 when a tail was opened, 0 when the caller may stop now. */
int gbp_vstate_target_reached(struct gbp_vstate *s, uint64_t t);
/* The hard wall-clock cap fired: close any open episode as truncated_by_safety. Never extends. */
void gbp_vstate_safety_stop(struct gbp_vstate *s, uint64_t t);
/* A store cap fired during the tail: end the tail, set tail_truncated_by_cap. NOT a service failure. */
void gbp_vstate_tail_truncate(struct gbp_vstate *s, uint64_t t);

/* ---- AUDIO ----------------------------------------------------------- */
/* Destination of the next AUDIO drain and its slot: slot 0 until one drain completes, then the
 * ping-pong pair 1/2. A failed drain lands in the slot that is not last_valid. */
uint8_t *gbp_vstate_audio_target(struct gbp_vstate *s, unsigned *slot);
/* Registers the outcome. `completed` != 0 promotes the slot to valid; a failure never touches a
 * valid capture. `crc32` is the caller's, computed outside the timed region (0 during capture). */
void gbp_vstate_audio_commit(struct gbp_vstate *s, unsigned slot, int completed, uint32_t bytes, uint64_t cycle);
const uint8_t *gbp_vstate_audio_bytes(const struct gbp_vstate *s, unsigned slot);
/* Raw AUDIO slots worth storing: 0 (first) plus the last valid ping-pong slot when there is one. */
unsigned gbp_vstate_audio_raw_count(const struct gbp_vstate *s);

/* ---- the semantic-disagreement policy (§R3.2, §R3.3) ------------------
 * Pure functions: no I/O, no state, no formatting. `disc` and `gbi` are the two
 * readings of ONE 32-byte window, already computed by the caller from bytes the
 * transport delivered. Nothing here re-reads anything.
 *
 * gbp_vstate_classify() returns GBP_VSTATE_DIS_*: NON_SOURCE when the two
 * readings differ outside SRC_MASK, SOURCE_OTHER when they differ on a source
 * slot this probe cannot drain, SOURCE_SERVICED when every difference is inside
 * AV_MASK, NONE when they agree.
 *
 * gbp_vstate_authoritative() composes the value the runtime acts on: outside
 * SRC_MASK the two readings MUST already agree (the caller has classified), so
 * the agreed bits are used verbatim and NOTHING is voted there; inside SRC_MASK
 * the bitwise majority wins. THIS IS PROJECT POLICY, not a fact about what the
 * hardware intends (HARDWARE_TESTS §R3.3). */
unsigned gbp_vstate_classify(uint16_t disc, uint16_t gbi);
uint16_t gbp_vstate_authoritative(uint16_t disc, uint16_t gbi);
const char *gbp_vstate_class_name(unsigned c);
const char *gbp_vstate_fu_name(unsigned st);
const char *gbp_vstate_fur_name(unsigned r);
/* The six even source bits compressed to six index bits: source bit 2k -> index
 * bit k (§R3.28). Bits outside SRC_MASK are ignored. */
unsigned gbp_vstate_hist_index(uint16_t v);

/* Attaches the bounded disagreement store. Without it the probe still runs and
 * still counts, but preserves no record (diagnostics_not_preserved counts them). */
void gbp_vstate_diag_store(struct gbp_vstate *s, struct gbp_vstate_diag *store, uint32_t cap);
/* The first stored record, or NULL when none was preserved. */
const struct gbp_vstate_diag *gbp_vstate_diag_first(const struct gbp_vstate *s);

/* ---- the explicit diagnostic handle (§R4.2) ---------------------------
 * The whole point of vstate-0004. In vstate-0003 every current-cycle setter
 * resolved its target as `diags[diags_n - 1]`, "the newest record", and ran on
 * EVERY service cycle: a record kept absorbing the authoritative value, service
 * decision, ACK and re-arm of later cycles until the next disagreement opened a
 * new one (GBP-HW-104). Here the target is named by the caller and by nobody
 * else:
 *   - a handle identifies exactly ONE record; the store is append-only and no
 *     index is ever reused inside a run;
 *   - GBP_VSTATE_DIAG_INVALID never selects a record, and a setter given it is a
 *     bounded no-op over the store (aggregate counters may still move; not one
 *     byte of any record does);
 *   - no setter falls back to "the latest record", derives its target from
 *     diags_n, or reads a current-record global. There is none to read. */
typedef int gbp_vstate_diag_handle;
#define GBP_VSTATE_DIAG_INVALID (-1)

/* 1 when the handle addresses a record that exists in the store. */
int gbp_vstate_diag_handle_valid(const struct gbp_vstate *s, gbp_vstate_diag_handle h);
/* The record a handle names, or NULL. Read-only: the setters below are the only
 * writers, and each of them takes its handle explicitly. */
const struct gbp_vstate_diag *gbp_vstate_diag_at(const struct gbp_vstate *s, gbp_vstate_diag_handle h);

/* Opens a record for a disagreement, from bytes the transport already delivered.
 * Returns the HANDLE of the new record, or GBP_VSTATE_DIAG_INVALID when the
 * store is full or absent (counters still move, the flag is sticky, and no
 * waiter is created). Fills the v3 half plus delta/extra/classification and
 * leaves followup_state = FU_PENDING for a service-selecting site; an
 * observational site is closed immediately as FU_UNKNOWN/observational_site.
 * Performs no I/O and no formatting. */
gbp_vstate_diag_handle gbp_vstate_diag_open(struct gbp_vstate *s, uint32_t cycle, uint64_t t,
                                            const uint8_t *raw, uint16_t disc, uint16_t gbi,
                                            uint16_t read_kind, unsigned classification);
/* The transport and ISR context of the READ that opened the record `h` names.
 * Those values live in the probe's result, not in this state, so they arrive
 * here instead of inside gbp_vstate_diag_open() - but they arrive through the
 * same handle and the same resolver as every other write, because "the store is
 * indexed from exactly one place" is the property this revision exists to keep.
 * Written once, by the cycle that opened the record; a no-op on an invalid
 * handle. `info` may be NULL when the read carried no transport record. */
void gbp_vstate_diag_context(struct gbp_vstate *s, gbp_vstate_diag_handle h,
                             uint32_t intsr_entry, uint32_t intsr_after_w1c, uint32_t intmr_entry,
                             uint32_t latency_ticks, uint16_t control_exp,
                             const struct gbp_xfer_info *info);
/* The current-cycle setters. Each one writes the record `h` names and NOTHING
 * else; each is a no-op when `h` is invalid. They are called at most once per
 * transaction, from the cycle that owns the record. */
void gbp_vstate_diag_service(struct gbp_vstate *s, gbp_vstate_diag_handle h, uint16_t authoritative,
                             uint16_t service_selected, unsigned incomplete);
/* A selected drain that did not complete. The transaction ends here, so the flag
 * is the record's last word about its own service. */
void gbp_vstate_diag_service_incomplete(struct gbp_vstate *s, gbp_vstate_diag_handle h);
void gbp_vstate_diag_ack(struct gbp_vstate *s, gbp_vstate_diag_handle h, uint16_t ack_value, uint64_t t_ack);
void gbp_vstate_diag_rearm(struct gbp_vstate *s, gbp_vstate_diag_handle h, uint64_t t_rearm);
/* Attaches the bounded payload diagnostic of a block drained ONLY because the
 * majority carried a source the Disc reading did not (§R3.11, §R3.22, §R3.23). */
void gbp_vstate_diag_payload(struct gbp_vstate *s, gbp_vstate_diag_handle h, uint16_t source,
                             uint32_t crc32, uint32_t first_word);
/* Marks the record of the current cycle: a VIDEO block of it was quarantined, or
 * a VIDEO drain was deferred. Both are descriptive (§R3.12, §R3.13). */
void gbp_vstate_diag_quarantined(struct gbp_vstate *s, gbp_vstate_diag_handle h);
void gbp_vstate_diag_deferred(struct gbp_vstate *s, gbp_vstate_diag_handle h);
/* The source bit a gap slot describes, or 0. */
uint16_t gbp_vstate_gap_slot_bit(unsigned slot);
/* Arms the follow-up waiter on the record `h` names, at the END of its
 * transaction and only when its re-arm was actually written (§R4.6). Installing
 * it any earlier would claim that a next cause is expected after a re-arm that
 * never happened. Returns 1 when the record became the waiter. The waiter is a
 * SEPARATE lifetime from the service handle and receives only follow-up
 * fields. */
int gbp_vstate_diag_arm_followup(struct gbp_vstate *s, gbp_vstate_diag_handle h);
/* Fills the follow-up of the ONE waiting record from the NEXT cycle's ordinary
 * read. No extra hardware access exists for this. Returns 1 when a record was
 * closed. Call this BEFORE opening a record for the same read (§R3.8). */
int gbp_vstate_diag_followup(struct gbp_vstate *s, uint64_t t_cause, uint16_t next_gbi, uint16_t next_disc);
/* Closes the waiter at teardown - FU_NO_NEXT_CAUSE, or FU_UNKNOWN with a reason
 * - and then SWEEPS the store so that no record can reach the file as
 * FU_PENDING (§R3.14): a record whose transaction ended before its re-arm never
 * became the waiter, and closing it is a property of every exit rather than an
 * argument about one. */
void gbp_vstate_diag_close(struct gbp_vstate *s, unsigned aborted);
/* cause -> cause statistics per source slot (§R3.28). Called once per delivery
 * with the authoritative pending value; disagreement cycles are included. */
void gbp_vstate_gap_observe(struct gbp_vstate *s, uint16_t sources, uint64_t t_cause);

const char *gbp_vstate_diag_read_name(unsigned kind);

/* ---- reporting helpers (pure) ---------------------------------------- */
const char *gbp_vstate_completeness_name(unsigned c);
const char *gbp_vstate_episode_state_name(unsigned st);
/* Static footprint in bytes of every resident store, for the memory audit. */
uint64_t gbp_vstate_static_bytes(void);

#ifdef __cplusplus
}
#endif
#endif
