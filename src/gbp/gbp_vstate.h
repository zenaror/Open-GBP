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

/* ---- reporting helpers (pure) ---------------------------------------- */
const char *gbp_vstate_completeness_name(unsigned c);
const char *gbp_vstate_episode_state_name(unsigned st);
/* Static footprint in bytes of every resident store, for the memory audit. */
uint64_t gbp_vstate_static_bytes(void);

#ifdef __cplusplus
}
#endif
#endif
