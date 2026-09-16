/*
 * gbp_avblock.h — one raw AUDIO / VIDEO block of the Game Boy Player read
 * whole into main memory (GBP-AV-SERVICE-001).
 *
 * The references consume the block the pending source bit names with one
 * DMA of its whole length (Start-up Disc 0x8008a764 / 0x8008a480, GBI
 * 0x8000bf30 through the ARQ hi queue): AUDIO = index 0x8, 0x1000 bytes,
 * for source 0x0400; VIDEO = index 0x1, 0xF00 bytes, for source 0x0100
 * (docs/protocol/REGISTERS.md §2, GBP-IRQ-005, GBP-VID-001, GBP-AUD-001).
 * This module performs exactly that transfer through the transport's
 * read_bulk operation and keeps the result raw:
 *   - the buffer is the caller's (static, 32-byte aligned, full length);
 *     it is never modified by this module after the transfer;
 *   - nothing is formatted or interpreted during the transfer; the read
 *     records and the summaries are produced afterwards by explicit calls;
 *   - the summary (CRC-32, byte counts, four 32-byte windows, the first
 *     32-bit word and GBI's frame-start test on it, recorded as a raw flag)
 *     is computed outside the timed region and never replaces the bytes.
 * A block that was not selected by the service snapshot is "not present":
 * attempted = 0, and nothing about its buffer is reported as evidence.
 */
#ifndef OPENGBP_GBP_AVBLOCK_H
#define OPENGBP_GBP_AVBLOCK_H

#include <stdint.h>
#include "gbp_transport.h"
#include "../log/ringlog.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_AVBLOCK_AUDIO_INDEX 0x8u
#define GBP_AVBLOCK_AUDIO_LEN   0x1000u
#define GBP_AVBLOCK_AUDIO_SRC   0x0400u
#define GBP_AVBLOCK_VIDEO_INDEX 0x1u
#define GBP_AVBLOCK_VIDEO_LEN   0x0F00u
#define GBP_AVBLOCK_VIDEO_SRC   0x0100u
#define GBP_AVBLOCK_WINDOWS 4u
/* GBI's frame-start test on the first 32-bit word of a VIDEO block
 * (0x8000bf30: `(word0 & 0x80800000) == 0x80800000`); recorded as a raw
 * flag, never as an interpretation of the frame (U-GBP-011). */
#define GBP_AVBLOCK_GBI_FRAME_START_MASK 0x80800000u

struct gbp_avblock {
    const char *kind;          /* "audio" / "video" */
    unsigned index;            /* register index (0x8 / 0x1) */
    uint16_t source_bit;       /* 0x0400 / 0x0100 */
    uint8_t *buf;              /* caller's buffer, 32-byte aligned, >= len bytes */
    uint32_t cap;
    uint32_t len;              /* transfer length (0x1000 / 0xF00) */
    uint32_t addr;             /* ARAM-side address of the block (base + index << 20) */
    int selected;              /* named by the service snapshot (pending & source_bit) */
    int attempted;             /* read_bulk was invoked (set BEFORE the call) */
    int completed;             /* rc == GBP_OK */
    gbp_status rc;
    struct gbp_xfer_info info;
    uint32_t t_start, t_end;   /* transport ticks read right before / after the call */
    /* summary, computed by gbp_avblock_summarize() outside the timed region */
    int summarized;
    uint32_t crc32;
    uint32_t zeros;            /* bytes equal to 0x00 */
    uint32_t distinct;         /* distinct byte values (1..256) */
    uint32_t w_off[GBP_AVBLOCK_WINDOWS];   /* window offsets: 0, ~1/3, ~2/3, last 32 bytes */
    uint32_t first_word;       /* bytes 0..3, big-endian */
    int gbi_frame_start;       /* (first_word & GBP_AVBLOCK_GBI_FRAME_START_MASK) == mask (raw flag) */
};

void gbp_avblock_init(struct gbp_avblock *b, const char *kind, unsigned index, uint16_t source_bit,
                      uint8_t *buf, uint32_t cap, uint32_t len);

/* One whole-block read through t->read_bulk into b->buf: b->addr computed
 * from `base`, `attempted` set before the call, `completed` on rc ok,
 * t_start / t_end from the transport time base. No formatting, no retry.
 * Returns the transport status (GBP_ERR_BACKEND when the transport has no
 * read_bulk or the buffer is too small; then attempted stays 0). *errors is
 * incremented on any failure when non-NULL. */
gbp_status gbp_avblock_read(const struct gbp_transport *t, uint32_t base, struct gbp_avblock *b, unsigned *errors);

/* Summary of a completed read (outside the timed region; the buffer is only read). */
void gbp_avblock_summarize(struct gbp_avblock *b);

/* Records (formatting only):
 *   <TAG> idx= addr= len= selected= attempted= rc= t_start= t_end= dt= wait_ticks= polls= csr_before= csr_after=
 *   BLOCK kind= idx= len= present= valid= crc32= zeros= distinct= w_off=…,…,…,… first_word= gbi_frame_start=
 *   BLOCKW kind= off= data=<64 hex>   (one per window) */
void gbp_avblock_log_read(struct ringlog *log, const char *tag, const struct gbp_avblock *b);
void gbp_avblock_log_summary(struct ringlog *log, const struct gbp_avblock *b);

/* Window offsets for a length (pure): 0, (len/3) rounded down to 32, (2*len/3) rounded down to 32, len-32. */
void gbp_avblock_window_offsets(uint32_t len, uint32_t out[GBP_AVBLOCK_WINDOWS]);

#ifdef __cplusplus
}
#endif
#endif
