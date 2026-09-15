/*
 * gbp_transport.h — the boundary between GBP logic and the hardware.
 *
 *     probe / driver logic
 *            │
 *     struct gbp_transport  (this file)
 *            ├── src/platform/hsp_backend.c   real GameCube (ARAM DMA)
 *            ├── tests/mocks/gbp_mock.c       scripted device model (host)
 *            └── src/gbp/gbp_replay.c         replays recorded blocks (host)
 *
 * Terminology (docs/protocol/REGISTERS.md): a GBP "block" is 32 bytes at
 * ARAM address  base + (index << 20) + offset,  base = internal ARAM size.
 * Nothing in this header assumes the hardware semantics beyond that.
 */
#ifndef OPENGBP_GBP_TRANSPORT_H
#define OPENGBP_GBP_TRANSPORT_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_BLOCK_SIZE 32u

typedef enum {
    GBP_OK = 0,
    GBP_ERR_TIMEOUT = 1,   /* DMA did not complete within the backend's timeout */
    GBP_ERR_BUSY = 2,      /* DMA engine busy / stale completion flag before start */
    GBP_ERR_PARAM = 3,     /* bad argument (alignment, size) */
    GBP_ERR_BACKEND = 4    /* backend-specific failure (mock script, replay exhausted) */
} gbp_status;

/* Status snapshot a backend can report for logging; fields it cannot
 * provide are 0. */
struct gbp_xfer_info {
    uint32_t ticks;        /* time spent waiting for completion (backend units) */
    uint16_t dma_status;   /* raw DSP CSR (0xCC00500A) after the transfer, if applicable */
    uint16_t polls;        /* completion polls performed */
};

struct gbp_transport {
    /* ARAM-info register 0xCC005012 (16-bit). */
    gbp_status (*read_arinfo)(void *ctx, uint16_t *value);
    gbp_status (*write_arinfo)(void *ctx, uint16_t value);
    /* One 32-byte transfer. aram_addr is the absolute ARAM address. */
    gbp_status (*read_block)(void *ctx, uint32_t aram_addr, uint8_t out[GBP_BLOCK_SIZE],
                             struct gbp_xfer_info *info);
    gbp_status (*write_block)(void *ctx, uint32_t aram_addr, const uint8_t in[GBP_BLOCK_SIZE],
                              struct gbp_xfer_info *info);
    /* Optional (may be NULL): Processor Interface INTSR (0xCC003000) and
     * INTMR (0xCC003004), raw 32-bit values. write_intmr writes the whole
     * register; callers preserve every bit they do not intend to change. */
    gbp_status (*read_pi)(void *ctx, uint32_t *intsr, uint32_t *intmr);
    gbp_status (*write_intmr)(void *ctx, uint32_t intmr);
    /* Optional (may be NULL): monotonic tick counter (time base on GC). */
    uint32_t (*ticks)(void *ctx);
    void *ctx;
};

/* PI bit for the High Speed Port interrupt (YAGCD 6.1.5.2, libogc2 irq.c:
 * INTMR bit set = interrupt enabled; INTSR bit set = pending). */
#define GBP_PI_HSP_BIT 0x00002000u

/* ---- address helpers (pure, tested on host) --------------------------- */

/* Internal ARAM size from AR_INFO bits 0-2, as decoded by the Start-up
 * Disc (0x80089aac): 0→2 MB, 1→4 MB, 2→8 MB, 3→16 MB, 4→32 MB, else 0. */
uint32_t gbp_internal_size_from_arinfo(uint16_t arinfo);

/* AR_INFO with bits 3-5 replaced by 'code' (0..7), all other bits kept. */
uint16_t gbp_arinfo_with_expansion(uint16_t arinfo, unsigned code);

/* ARAM address of a block: base + (index << 20) + offset. offset must be a
 * multiple of 32 and < 1 MB; index 0..15. Returns 0 on bad input. */
uint32_t gbp_block_addr(uint32_t base, unsigned index, uint32_t offset);

const char *gbp_status_name(gbp_status s);

#ifdef __cplusplus
}
#endif
#endif
