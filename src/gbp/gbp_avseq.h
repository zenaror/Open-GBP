/*
 * gbp_avseq.h — bounded AUDIO/VIDEO block-sequence capture: the records,
 * buffers and bookkeeping of GBP-VIDEO-001's repeated drained service.
 *
 * Normative description: docs/research/HARDWARE_TESTS.md "Planned tests —
 * GBP-VIDEO-001" (designed and reviewed 2026-09-16), docs/research/VIDEO_PATH.md,
 * docs/protocol/INITIALIZATION.md §14. Not a runtime: no framebuffer, no
 * conversion, no frame sync, no audio playback, no KEYPAD, no SIO, no Link
 * Port, no BBA, no Game Pak logic, no malloc, no unbounded loop.
 *
 * What this module owns (policy-free, tested on the host):
 *   - the compact per-cycle / per-VIDEO-block / per-AUDIO-drain records
 *     (struct gbp_avseq_cycle / _vblock / _ablock) in bounded arrays;
 *   - the static block buffers the caller provides: `video_blocks[88][0xF00]`
 *     contiguous in sequence order (one slot per VIDEO DMA, chosen after the
 *     bounds check, marked valid only after completion, never overwritten)
 *     and the AUDIO raw slots (the first 8 successful drains + a ping-pong
 *     pair for the last successful one: a failed drain lands in the other
 *     buffer and never overwrites the last valid capture);
 *   - the two frame-start predicates computed separately from the raw first
 *     four bytes of a VIDEO block (GBI: bit 7 of bytes 0 AND 1; Start-up
 *     Disc: bit 7 of byte 1), their agreement, and the boundary lists per
 *     predicate (positions, intervals, "complete interval" = two consecutive
 *     true predicates); the constant 40 is never a gate;
 *   - the post-loop summaries (CRC-32, byte-0 exceptions, undoubled words,
 *     AUDIO statistics) — computed only after the timed region, read-only;
 *   - the compact log lines formatted from the records, after the loop.
 * Nothing here touches the transport; the probe (gbp_video_probe.c) runs the
 * state machine and fills the records.
 */
#ifndef OPENGBP_GBP_AVSEQ_H
#define OPENGBP_GBP_AVSEQ_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_transport.h"
#include "../log/ringlog.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ---- the design constants (operational bounds; none is a GBP property except the sizes/indices) ---- */
#define GBP_AVSEQ_VIDEO_BLOCK_SIZE    0x0F00u
#define GBP_AVSEQ_AUDIO_BLOCK_SIZE    0x1000u
#define GBP_AVSEQ_VIDEO_INDEX         1u
#define GBP_AVSEQ_AUDIO_INDEX         8u
#define GBP_AVSEQ_VIDEO_SRC           0x0100u
#define GBP_AVSEQ_AUDIO_SRC           0x0400u
#define GBP_AVSEQ_TARGET_VIDEO_BLOCKS 88u
#define GBP_AVSEQ_MAX_VIDEO_BLOCKS    88u
#define GBP_AVSEQ_MAX_DELIVERIES      320u
#define GBP_AVSEQ_MAX_AUDIO_BLOCKS    GBP_AVSEQ_MAX_DELIVERIES   /* one drain per delivery at most: no separate cap */
#define GBP_AVSEQ_AUDIO_FIRST_KEPT    8u
#define GBP_AVSEQ_AUDIO_LAST_BUFFERS  2u
#define GBP_AVSEQ_AUDIO_RAW_SLOTS     (GBP_AVSEQ_AUDIO_FIRST_KEPT + GBP_AVSEQ_AUDIO_LAST_BUFFERS)
#define GBP_AVSEQ_VERIFY_CYCLES       4u
#define GBP_AVSEQ_ADMISSION_BUDGET_MS 1000u
#define GBP_AVSEQ_T_DELIVERY_MS       100u
#define GBP_AVSEQ_T_NEXT_CAUSE_MS     100u
#define GBP_AVSEQ_VIDEO_RAW_BYTES     (GBP_AVSEQ_MAX_VIDEO_BLOCKS * GBP_AVSEQ_VIDEO_BLOCK_SIZE)
#define GBP_AVSEQ_AUDIO_RAW_BYTES     (GBP_AVSEQ_AUDIO_RAW_SLOTS * GBP_AVSEQ_AUDIO_BLOCK_SIZE)
/* GBI's frame-start test on the first 32-bit word (0x8000bf30): bit 7 of byte 0 AND of byte 1. */
#define GBP_AVSEQ_GBI_FRAME_START_MASK 0x80800000u

/* AUDIO raw slot codes (struct gbp_avseq_cycle / _ablock .audio_slot / .slot). */
#define GBP_AVSEQ_SLOT_NONE 0xFFu      /* nothing preserved (drain not attempted / raw not kept) */
#define GBP_AVSEQ_SLOT_LAST 0x80u      /* | k: the ping-pong buffer k (0/1), i.e. raw slot 8 + k */
#define GBP_AVSEQ_VIDEO_SEQ_NONE 0xFFFFu

/* How the capture loop ended (the CAPTURE dimension of the result matrix). */
enum gbp_avseq_end {
    GBP_AVSEQ_END_NONE = 0,
    GBP_AVSEQ_END_TARGET_REACHED,     /* TARGET_VIDEO_BLOCKS captured */
    GBP_AVSEQ_END_DELIVERY_CAP,       /* MAX_DELIVERIES admitted */
    GBP_AVSEQ_END_RUNTIME_CAP,        /* the admission budget expired before a new cycle could be admitted */
    GBP_AVSEQ_END_NO_NEXT_CAUSE,      /* T_NEXT_CAUSE expired with budget left: the device produced no cause */
    GBP_AVSEQ_END_EARLY_FAILURE       /* a service failure stopped the loop */
};

/* How WAIT_NEXT ended in a cycle. */
enum gbp_avseq_next_end {
    GBP_AVSEQ_NEXT_NONE = 0,
    GBP_AVSEQ_NEXT_CAUSE,             /* INTSR bit 13 seen (the cause stays latched) */
    GBP_AVSEQ_NEXT_TIMEOUT,           /* T_NEXT_CAUSE expired, budget left */
    GBP_AVSEQ_NEXT_DEADLINE,          /* the admission deadline arrived during the wait, no cause */
    GBP_AVSEQ_NEXT_SINGLE_READ        /* no budget left when the wait would start: one read only, no cause */
};

/* One admitted delivery (compact; formatted only after the loop). */
struct gbp_avseq_cycle {
    uint16_t idx;                     /* 0-based cycle / delivery index */
    uint16_t pending;                 /* the READ value (Disc == GBI) the transaction acted on */
    uint8_t irq_byte0, irq_off2_g0;   /* raw byte 0 and the group-0 offset-2 byte of that read (never a decision) */
    uint8_t verify;                   /* 1: a verify cycle (AVSVC snapshots taken and logged) */
    uint8_t end_reason;               /* enum gbp_avseq_end when the loop ended in this cycle, else 0 */
    uint8_t audio_selected, audio_attempted, audio_completed, audio_rc, audio_slot;
    uint8_t video_selected, video_attempted, video_completed, video_rc;
    uint16_t video_seq;               /* sequence index of the VIDEO block of this cycle (GBP_AVSEQ_VIDEO_SEQ_NONE) */
    uint8_t ack_attempted, ack_completed, rearm_attempted, rearm_completed;
    uint8_t main_w1c, pi_sticky, relatch_postack, relatch_postdrain;
    uint8_t next_observed, next_ended_by;      /* WAIT_NEXT */
    uint8_t isr_fired, isr_count, isr_reentry;
    uint8_t admitted;                 /* 1 once CONFIRM held (the cycle became transactional) */
    uint16_t ack_value;
    uint16_t next_pending;            /* pending value read at the next cause, verify cycles only (REARMPOST) */
    uint32_t t_adm;                   /* the admission time-base read */
    uint32_t t_cause;                 /* the poll / EVENT that saw INTSR bit 13 for this delivery */
    uint32_t t_unmask, t_post_unmask, t_entry, latency;
    uint32_t t_read;                  /* the pending read (READ / PRESVC) */
    uint32_t t_audio_start, t_audio_end, t_video_start, t_video_end;
    uint32_t t_ack_after, t_rearm, t_rearm_after, t_next;
    uint32_t intsr_entry, intmr_entry, intsr_after_w1c;      /* the handler record */
    uint32_t intsr_prep, intmr_prep;                          /* PREPARE read */
    uint32_t intsr_postack, intmr_postack, intsr_after_main_w1c;
    uint32_t intsr_next;              /* the polled INTSR that ended WAIT_NEXT (or the single read) */
    uint32_t audio_crc32;             /* of the completed drain (0 otherwise) */
    uint32_t audio_wait, video_wait;  /* backend completion waits (ticks) */
    uint16_t audio_polls, video_polls;
    uint8_t irq_raw[GBP_BLOCK_SIZE];  /* the pending read, verbatim (lean cycles; verify cycles keep it in their snapshot too) */
    struct gbp_xfer_info irq_info;    /* transport info of that read */
    gbp_status irq_rc;
    uint16_t irq_disc, irq_gbi;
    /* the delivery / remask values needed to regenerate a replay fixture from the log */
    uint32_t intsr_pre, intmr_pre, intsr_post, intmr_post, intsr_remask, intmr_remask;
    uint32_t t_wait_end, wait_polls;
    uint8_t timed_out, remask_retry, mask_ok, prep_rc;
    uint32_t intsr_before_w1c, intmr_after_mask, t_second, intsr_second, intmr_second, reentry_t, reentry_intsr, reentry_intmr;
    uint32_t rec0_fired;
    uint32_t next_polls;
};

/* One VIDEO block (one slot of the contiguous buffer). */
struct gbp_avseq_vblock {
    uint16_t seq, cycle, pending;
    uint8_t rc, completed;
    uint8_t flag_gbi, flag_disc, flags_agree;
    uint8_t raw_first4[4];            /* bytes 0..3 verbatim */
    uint32_t t_start, t_end, wait_ticks, crc32;
    uint16_t byte0_exceptions;        /* words whose byte 0 != byte 1 (computed after the loop) */
    uint16_t undoubled_words;         /* words whose byte 0 != byte 1 or byte 2 != byte 3 */
    uint16_t polls, csr_before, csr_after;
    uint8_t summarized;
};

/* One AUDIO drain (one per cycle at most). */
struct gbp_avseq_ablock {
    uint16_t cycle;
    uint8_t selected, attempted, completed, rc;
    uint8_t slot;                     /* GBP_AVSEQ_SLOT_* / 0..7 */
    uint8_t raw_kept;                 /* 1: the bytes of this drain are preserved (first 8 or the last valid) */
    uint16_t raw_index;               /* index into the raw AUDIO slots (0..9) or 0xFFFF */
    uint32_t t_start, t_end, wait_ticks, crc32, first_word;
    uint16_t nonzero, unit0_nonzero;  /* bytes != 0; 32-byte units whose byte 0 != 0 */
    uint8_t summarized;
};

struct gbp_avseq_boundaries {
    unsigned count;
    unsigned positions[GBP_AVSEQ_MAX_VIDEO_BLOCKS];
    unsigned intervals_n;
    unsigned intervals[GBP_AVSEQ_MAX_VIDEO_BLOCKS];
    int complete_interval;            /* 1 iff count >= 2 */
};

struct gbp_avseq_store {
    struct gbp_avseq_cycle cycles[GBP_AVSEQ_MAX_DELIVERIES];
    struct gbp_avseq_vblock vblocks[GBP_AVSEQ_MAX_VIDEO_BLOCKS];
    struct gbp_avseq_ablock ablocks[GBP_AVSEQ_MAX_AUDIO_BLOCKS];
    unsigned cycles_n, vblocks_n, ablocks_n;
    uint8_t *video_raw;               /* caller's: >= GBP_AVSEQ_VIDEO_RAW_BYTES, 32-byte aligned; slot i at i * 0xF00 */
    uint32_t video_raw_cap;
    uint8_t *audio_raw;               /* caller's: >= GBP_AVSEQ_AUDIO_RAW_BYTES, 32-byte aligned; slots 0..7 first, 8..9 ping-pong */
    uint32_t audio_raw_cap;
    unsigned audio_first_kept;        /* successful drains stored in slots 0..7 */
    int audio_last_valid;             /* -1 none; else the raw slot (8 or 9) of the last completed drain beyond the first 8 */
    unsigned audio_last_next;         /* the ping-pong slot the next drain beyond the first 8 targets (8 or 9) */
    unsigned audio_drains_completed;  /* every completed drain (raw kept or not) */
};

void gbp_avseq_store_init(struct gbp_avseq_store *s, uint8_t *video_raw, uint32_t video_raw_cap,
                          uint8_t *audio_raw, uint32_t audio_raw_cap);
void gbp_avseq_cycle_init(struct gbp_avseq_cycle *c, unsigned idx);

/* The two predicates, from the raw first four bytes (pure). */
int gbp_avseq_flag_gbi(const uint8_t first4[4]);
int gbp_avseq_flag_disc(const uint8_t first4[4]);

/* VIDEO slot for the next DMA: the buffer of slot vblocks_n after the bounds check, or NULL
 * when the array is full (the caller must never start a DMA then). */
uint8_t *gbp_avseq_video_target(struct gbp_avseq_store *s);
/* Registers the VIDEO DMA of `cycle` into the slot returned above (completed or not); a
 * completed read consumes the slot (vblocks_n + 1); a failed one keeps the slot's record with
 * completed = 0 and raw_len 0 — the loop stops after a failure, so no later DMA reuses it. */
struct gbp_avseq_vblock *gbp_avseq_video_commit(struct gbp_avseq_store *s, unsigned cycle, uint16_t pending,
                                                gbp_status rc, const struct gbp_xfer_info *info,
                                                uint32_t t_start, uint32_t t_end);

/* AUDIO destination for the next drain: raw slot 0..7 while first_kept < 8, else the ping-pong
 * slot audio_last_next. Returns the buffer and the raw slot index. */
uint8_t *gbp_avseq_audio_target(struct gbp_avseq_store *s, unsigned *raw_slot);
/* Registers the AUDIO DMA of `cycle`: on completion the slot becomes valid (first_kept advances,
 * or last_valid := raw_slot and the ping-pong flips); on failure nothing valid changes. */
struct gbp_avseq_ablock *gbp_avseq_audio_commit(struct gbp_avseq_store *s, unsigned cycle, unsigned raw_slot,
                                                gbp_status rc, const struct gbp_xfer_info *info,
                                                uint32_t t_start, uint32_t t_end);
/* Raw AUDIO blocks to store: the first_kept slots, plus the last valid one when it is a ping-pong slot. */
unsigned gbp_avseq_audio_raw_count(const struct gbp_avseq_store *s);
/* Byte address of a raw slot. */
const uint8_t *gbp_avseq_video_bytes(const struct gbp_avseq_store *s, unsigned seq);
const uint8_t *gbp_avseq_audio_bytes(const struct gbp_avseq_store *s, unsigned raw_slot);

/* Post-loop summaries (read-only on the buffers): CRC-32s, the predicates and the exception
 * counts of every completed VIDEO block; CRC-32 / first word / statistics of every completed
 * AUDIO drain whose bytes are still in a raw slot. Never inside the loop. */
void gbp_avseq_summarize(struct gbp_avseq_store *s);
/* Boundary list under one predicate (use_disc = 0: GBI; 1: Disc), over the completed blocks in sequence order. */
void gbp_avseq_boundaries(const struct gbp_avseq_store *s, int use_disc, struct gbp_avseq_boundaries *out);

/* Compact log lines (formatting only):
 *   CYCU n= …   the admission read, PREPARE PI read, the unmask; CYCW n= … the bounded wait and the re-mask;
 *   CYCH n= …   the handler record (in the order of a replay "I u" line)
 *   CYCD n= …   the pending read summary, the AUDIO and VIDEO DMAs, the ACK
 *   CYCR n= …   PI clean, the re-arm, WAIT_NEXT
 *   VBLK seq= … one VIDEO block; ABLK n= … one AUDIO drain */
void gbp_avseq_log_cycle(struct ringlog *log, const struct gbp_avseq_cycle *c, uint32_t audio_addr, uint32_t video_addr);
void gbp_avseq_log_vblock(struct ringlog *log, const struct gbp_avseq_vblock *v);
void gbp_avseq_log_ablock(struct ringlog *log, const struct gbp_avseq_ablock *a);
void gbp_avseq_log_boundaries(struct ringlog *log, const char *predicate, const struct gbp_avseq_boundaries *b);
const char *gbp_avseq_end_name(int e);
const char *gbp_avseq_next_end_name(int e);

#ifdef __cplusplus
}
#endif
#endif
