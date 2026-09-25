/*
 * gbp_awr.c — the raw-block ride-along store and its OGBPAWR1 serializer.
 * See the header for the file layout and for where each half runs.
 */
#include "gbp_awr.h"
#include "gbp_crc32.h"
#include <string.h>

static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}
static void put_u64(uint8_t *p, uint64_t v) { put_u32(p, (uint32_t)(v >> 32)); put_u32(p + 4, (uint32_t)v); }

int gbp_awr_init(struct gbp_awr *w, uint8_t *store, uint32_t blocks_cap, uint32_t tb_hz)
{
    if (!w) return -1;
    memset(w, 0, sizeof *w);
    w->tb_hz = tb_hz;
    w->state = (uint32_t)GBP_AWR_IDLE;
    if (!store) { w->fault = 1; return -1; }
    if (blocks_cap == 0u) { w->fault = 2; return -1; }
    w->store = store;
    w->blocks_cap = blocks_cap;
    return 0;
}

const char *gbp_awr_fault(const struct gbp_awr *w)
{
    if (!w) return "null";
    switch (w->fault) {
    case 0: return "-";
    case 1: return "store_null";
    case 2: return "cap_zero";
    default: return "unknown";
    }
}

int gbp_awr_arm(struct gbp_awr *w, uint64_t t_now)
{
    if (!w) return -1;
    if (!w->store || w->state != (uint32_t)GBP_AWR_IDLE) { w->arm_refused++; return -1; }
    w->t_arm = t_now;
    w->state = (uint32_t)GBP_AWR_ARMED;
    return 0;
}

int gbp_awr_block(struct gbp_awr *w, const uint8_t *block, uint32_t len, uint64_t t_done, uint32_t seq)
{
    uint8_t *dst;
    if (!w) return 0;
    w->seen++;
    if (w->state != (uint32_t)GBP_AWR_ARMED && w->state != (uint32_t)GBP_AWR_FILLING) {
        w->ignored++;
        return 0;
    }
    if (!block || len != GBP_AWR_BLOCK_SIZE) {
        /* Counted and NOT stored: a block of the wrong length is not a block
         * of the run, and a hole in the store would read as one. */
        w->faults++;
        return 0;
    }
    /* memcpy, not a byte loop: it runs in the tap at the block cadence and
     * the caller measures it either way. */
    dst = w->store + (size_t)w->blocks_stored * GBP_AWR_BLOCK_SIZE;
    memcpy(dst, block, GBP_AWR_BLOCK_SIZE);
    if (w->blocks_stored == 0u) {
        w->t_first = t_done;
        w->seq_first = seq;
        w->state = (uint32_t)GBP_AWR_FILLING;
    }
    w->t_last = t_done;
    w->seq_last = seq;
    w->blocks_stored++;
    if (w->blocks_stored >= w->blocks_cap) w->state = (uint32_t)GBP_AWR_DONE;
    return 1;
}

void gbp_awr_note_cost(struct gbp_awr *w, uint32_t ticks)
{
    if (!w) return;
    if (w->copy_n == 0u || ticks < w->copy_min) w->copy_min = ticks;
    if (ticks > w->copy_max) w->copy_max = ticks;
    w->copy_n++;
    w->copy_sum += (uint64_t)ticks;
}

void gbp_awr_finish(struct gbp_awr *w)
{
    if (!w) return;
    if (w->state == (uint32_t)GBP_AWR_ARMED || w->state == (uint32_t)GBP_AWR_FILLING)
        w->state = (uint32_t)GBP_AWR_DONE;
}

int gbp_awr_done(const struct gbp_awr *w)
{
    return (w && w->state == (uint32_t)GBP_AWR_DONE) ? 1 : 0;
}

unsigned gbp_awr_copy_mean(const struct gbp_awr *w)
{
    if (!w || w->copy_n == 0u) return 0u;
    return (unsigned)(w->copy_sum / (uint64_t)w->copy_n);
}

const uint8_t *gbp_awr_block_bytes(const struct gbp_awr *w, uint32_t index)
{
    if (!w || !w->store || index >= w->blocks_stored) return 0;
    return w->store + (size_t)index * GBP_AWR_BLOCK_SIZE;
}

size_t gbp_awr_header(const struct gbp_awr *w, uint8_t *out, size_t cap)
{
    unsigned i;
    if (!w || !out || cap < GBP_AWR_HEADER_SIZE) return 0u;
    memset(out, 0, GBP_AWR_HEADER_SIZE);
    for (i = 0; i < 8u; i++) out[i] = (uint8_t)GBP_AWR_MAGIC[i];
    put_u32(out + 0x08, GBP_AWR_VERSION);
    put_u32(out + 0x0C, GBP_AWR_BLOCK_SIZE);
    put_u32(out + 0x10, w->blocks_stored);
    put_u32(out + 0x14, w->blocks_cap);
    put_u32(out + 0x18, w->tb_hz);
    put_u32(out + 0x1C, w->state);
    put_u64(out + 0x20, w->t_arm);
    put_u64(out + 0x28, w->t_first);
    put_u64(out + 0x30, w->t_last);
    put_u32(out + 0x38, w->copy_min);
    put_u32(out + 0x3C, w->copy_max);
    put_u64(out + 0x40, w->copy_sum);
    put_u32(out + 0x48, w->copy_n);
    put_u32(out + 0x4C, w->faults);
    put_u32(out + 0x50, w->ignored);
    put_u32(out + 0x54, w->seen);
    put_u32(out + 0x58, w->seq_first);
    put_u32(out + 0x5C, w->seq_last);
    put_u32(out + 0x60, w->arm_refused);
    /* 0x64 .. 0x7B reserved zero */
    put_u32(out + GBP_AWR_CRC_OFFSET, gbp_crc32(out, GBP_AWR_CRC_OFFSET));
    return GBP_AWR_HEADER_SIZE;
}

size_t gbp_awr_footer(uint32_t crc_state, uint8_t *out, size_t cap)
{
    unsigned i;
    if (!out || cap < GBP_AWR_FOOTER_SIZE) return 0u;
    for (i = 0; i < 8u; i++) out[i] = (uint8_t)GBP_AWR_END[i];
    put_u32(out + 8, gbp_crc32_final(crc_state));
    return GBP_AWR_FOOTER_SIZE;
}

uint64_t gbp_awr_total(const struct gbp_awr *w)
{
    if (!w) return 0u;
    return (uint64_t)GBP_AWR_HEADER_SIZE + (uint64_t)w->blocks_stored * GBP_AWR_BLOCK_SIZE + GBP_AWR_FOOTER_SIZE;
}

long gbp_awr_stream(const struct gbp_awr *w, gbp_awr_sink sink, void *sink_ctx, uint64_t *written)
{
    uint8_t head[GBP_AWR_HEADER_SIZE];
    uint8_t foot[GBP_AWR_FOOTER_SIZE];
    uint64_t total = 0u;
    uint32_t state, k;
    if (written) *written = 0u;
    if (!w || !sink) return -1;
    if (w->blocks_stored && !w->store) return -1;
    if (gbp_awr_header(w, head, sizeof head) != GBP_AWR_HEADER_SIZE) return -1;
    state = gbp_crc32_init();
    state = gbp_crc32_update(state, head, GBP_AWR_HEADER_SIZE);
    if (sink(sink_ctx, head, GBP_AWR_HEADER_SIZE)) goto trunc;
    total += GBP_AWR_HEADER_SIZE;
    for (k = 0; k < w->blocks_stored; k++) {
        const uint8_t *blk = w->store + (size_t)k * GBP_AWR_BLOCK_SIZE;
        state = gbp_crc32_update(state, blk, GBP_AWR_BLOCK_SIZE);
        if (sink(sink_ctx, blk, GBP_AWR_BLOCK_SIZE)) goto trunc;
        total += GBP_AWR_BLOCK_SIZE;
    }
    if (gbp_awr_footer(state, foot, sizeof foot) != GBP_AWR_FOOTER_SIZE) return -1;
    if (sink(sink_ctx, foot, GBP_AWR_FOOTER_SIZE)) goto trunc;
    total += GBP_AWR_FOOTER_SIZE;
    if (written) *written = total;
    return (long)total;
trunc:
    if (written) *written = total;
    return -2;
}
