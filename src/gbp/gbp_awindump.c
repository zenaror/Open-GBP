/*
 * gbp_awindump.c — the OGBPAW1 writer and its strict parser. See the header.
 */
#include "gbp_awindump.h"
#include "gbp_crc32.h"

static void put_u16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}
static void put_u64(uint8_t *p, uint64_t v) { put_u32(p, (uint32_t)(v >> 32)); put_u32(p + 4, (uint32_t)v); }
static uint16_t get_u16(const uint8_t *p) { return (uint16_t)(((uint16_t)p[0] << 8) | (uint16_t)p[1]); }
static uint32_t get_u32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}
static uint64_t get_u64(const uint8_t *p) { return ((uint64_t)get_u32(p) << 32) | (uint64_t)get_u32(p + 4); }
static void zero(uint8_t *p, size_t n) { size_t i; for (i = 0; i < n; i++) p[i] = 0u; }

static int id_copy(char *dst, const char *src)
{
    size_t i;
    for (i = 0; i < GBP_AWINDUMP_ID_FIELD; i++) dst[i] = 0;
    if (!src) return 0;
    for (i = 0; src[i]; i++) {
        if (i >= GBP_AWINDUMP_ID_MAX) return -1;
        dst[i] = src[i];
    }
    return 0;
}

int gbp_awindump_set_identity(struct gbp_awindump_info *info, const char *test_id,
                              const char *build_id, const char *app, const char *commit)
{
    int rc = 0;
    if (!info) return -1;
    if (id_copy(info->test_id, test_id)) rc = -1;
    if (id_copy(info->build_id, build_id)) rc = -1;
    if (id_copy(info->app, app)) rc = -1;
    if (id_copy(info->commit, commit)) rc = -1;
    info->identity_error = rc ? 1 : 0;
    return rc;
}

int gbp_awindump_layout(struct gbp_awindump_info *info, const struct gbp_awin *w)
{
    uint64_t records, blocks;
    unsigned i;
    if (!info || !w) return -1;
    if (w->windows == 0u || w->windows > GBP_AWIN_WINDOWS) return -1;
    if (w->block_size != GBP_AWIN_BLOCK_SIZE) return -1;
    info->version = GBP_AWINDUMP_VERSION;
    info->header_size = GBP_AWINDUMP_HEADER_SIZE;
    info->record_size = GBP_AWINDUMP_RECORD_SIZE;
    info->block_size = w->block_size;
    info->blocks_per_window = w->blocks_per_window;
    info->windows_n = w->windows;
    info->blocks_seen = w->blocks_seen;
    info->blocks_ignored = w->blocks_ignored;
    info->blocks_failed = w->blocks_failed;
    info->arms = w->arms;
    info->arm_refused_busy = w->arm_refused_busy;
    info->arm_refused_full = w->arm_refused_full;
    info->windows_closed = w->windows_closed;
    info->ticks_min = w->ticks_min;
    info->ticks_max = w->ticks_max;
    info->ticks_n = w->ticks_n;
    info->ticks_sum = w->ticks_sum;
    info->flags &= (uint32_t)GBP_AWINDUMP_FLAG_TRUNCATED;
    info->blocks_stored = 0u;
    for (i = 0; i < info->windows_n; i++) {
        const struct gbp_awin_anchor *a = &w->anchor[i];
        if (a->blocks > w->blocks_per_window) return -1;
        if (a->flags & ~(uint32_t)GBP_AWIN_F_ALL) return -1;
        if (a->flags & GBP_AWIN_F_INCOMPLETE) info->flags |= GBP_AWINDUMP_FLAG_INCOMPLETE;
        if (a->flags & GBP_AWIN_F_GAP) info->flags |= GBP_AWINDUMP_FLAG_GAP;
        info->blocks_stored += a->blocks;
    }
    if (w->arm_refused_busy || w->arm_refused_full) info->flags |= GBP_AWINDUMP_FLAG_REFUSED;
    records = (uint64_t)info->windows_n * GBP_AWINDUMP_RECORD_SIZE;
    blocks = (uint64_t)info->blocks_stored * (uint64_t)info->block_size;
    if (records + blocks > 0xFFFFFFFFull - GBP_AWINDUMP_HEADER_SIZE - GBP_AWINDUMP_FOOTER_SIZE) return -1;
    info->off_records = GBP_AWINDUMP_HEADER_SIZE;
    info->off_blocks = (uint32_t)(GBP_AWINDUMP_HEADER_SIZE + records);
    info->off_footer = (uint32_t)((uint64_t)info->off_blocks + blocks);
    info->total_size = (uint64_t)info->off_footer + GBP_AWINDUMP_FOOTER_SIZE;
    return 0;
}

static void build_header(const struct gbp_awindump_info *info, uint8_t *h)
{
    unsigned i;
    zero(h, GBP_AWINDUMP_HEADER_SIZE);
    for (i = 0; i < 8u; i++) h[i] = (uint8_t)GBP_AWINDUMP_MAGIC[i];
    put_u16(h + 0x08, info->version);
    put_u16(h + 0x0A, info->header_size);
    put_u32(h + 0x0C, info->flags);
    put_u32(h + 0x10, info->block_size);
    put_u32(h + 0x14, info->blocks_per_window);
    put_u32(h + 0x18, info->windows_n);
    put_u32(h + 0x1C, info->record_size);
    put_u32(h + 0x20, info->blocks_stored);
    put_u32(h + 0x24, info->blocks_seen);
    put_u32(h + 0x28, info->blocks_ignored);
    put_u32(h + 0x2C, info->blocks_failed);
    put_u32(h + 0x30, info->arms);
    put_u32(h + 0x34, info->arm_refused_busy);
    put_u32(h + 0x38, info->arm_refused_full);
    put_u32(h + 0x3C, info->windows_closed);
    put_u32(h + 0x40, info->tb_hz);
    put_u32(h + 0x44, info->ticks_min);
    put_u32(h + 0x48, info->ticks_max);
    put_u32(h + 0x4C, info->ticks_n);
    put_u64(h + 0x50, info->ticks_sum);
    put_u32(h + 0x58, info->off_records);
    put_u32(h + 0x5C, info->off_blocks);
    put_u32(h + 0x60, info->off_footer);
    put_u64(h + 0x68, info->total_size);
    for (i = 0; i < GBP_AWINDUMP_ID_FIELD; i++) {
        h[0x70 + i] = (uint8_t)info->test_id[i];
        h[0x90 + i] = (uint8_t)info->build_id[i];
        h[0xB0 + i] = (uint8_t)info->app[i];
        h[0xD0 + i] = (uint8_t)info->commit[i];
    }
    /* 0xF0 .. 0xFB reserved zero; CRC at 0xFC */
    put_u32(h + GBP_AWINDUMP_HEADER_SIZE - 4u, gbp_crc32(h, GBP_AWINDUMP_HEADER_SIZE - 4u));
}

static void build_record(const struct gbp_awin_anchor *a, uint32_t index, uint32_t off, uint8_t *b)
{
    zero(b, GBP_AWINDUMP_RECORD_SIZE);
    put_u32(b + 0x00, index);
    put_u32(b + 0x04, a->kind);
    put_u32(b + 0x08, a->ordinal);
    put_u32(b + 0x0C, a->flags);
    put_u32(b + 0x10, a->event_n);
    put_u32(b + 0x14, a->word);
    put_u32(b + 0x18, a->keys);
    put_u32(b + 0x1C, a->blocks);
    put_u64(b + 0x20, a->t_poll);
    put_u64(b + 0x28, a->t_attempt);
    put_u64(b + 0x30, a->t_done);
    put_u64(b + 0x38, a->t_arm);
    put_u64(b + 0x40, a->first_cycle);
    put_u64(b + 0x48, a->last_cycle);
    put_u32(b + 0x50, a->skipped);
    put_u32(b + 0x54, off);      /* this window's blocks, from off_blocks */
    /* 0x58 .. 0x7B reserved zero; 0x7C record CRC over 0x00 .. 0x7C */
    put_u32(b + 0x7C, gbp_crc32(b, 0x7Cu));
}

long gbp_awindump_stream(struct gbp_awindump_info *info, const struct gbp_awin *w,
                         uint8_t *chunk, uint32_t chunk_cap,
                         gbp_awindump_sink sink, void *sink_ctx, uint64_t *written)
{
    uint64_t total = 0;
    uint32_t state, i, off;
    uint8_t footer[GBP_AWINDUMP_FOOTER_SIZE];
    if (written) *written = 0;
    if (!info || !w || !chunk || !sink) return -1;
    if (chunk_cap < GBP_AWINDUMP_HEADER_SIZE || chunk_cap < GBP_AWINDUMP_RECORD_SIZE) return -1;
    if (info->identity_error) return -2;
    if (gbp_awindump_layout(info, w)) return -3;
    state = gbp_crc32_init();
    build_header(info, chunk);
    info->header_crc32 = get_u32(chunk + GBP_AWINDUMP_HEADER_SIZE - 4u);
    state = gbp_crc32_update(state, chunk, GBP_AWINDUMP_HEADER_SIZE);
    if (sink(sink_ctx, chunk, GBP_AWINDUMP_HEADER_SIZE)) goto trunc;
    total += GBP_AWINDUMP_HEADER_SIZE;
    off = 0u;
    for (i = 0; i < info->windows_n; i++) {
        build_record(&w->anchor[i], i, off, chunk);
        state = gbp_crc32_update(state, chunk, GBP_AWINDUMP_RECORD_SIZE);
        if (sink(sink_ctx, chunk, GBP_AWINDUMP_RECORD_SIZE)) goto trunc;
        total += GBP_AWINDUMP_RECORD_SIZE;
        off += w->anchor[i].blocks * info->block_size;
    }
    for (i = 0; i < info->windows_n; i++) {
        const uint8_t *p = gbp_awin_window_bytes(w, i);
        uint32_t k;
        if (!p) { if (w->anchor[i].blocks) goto trunc; else continue; }
        for (k = 0; k < w->anchor[i].blocks; k++) {
            const uint8_t *blk = p + (size_t)k * info->block_size;
            state = gbp_crc32_update(state, blk, info->block_size);
            if (sink(sink_ctx, blk, info->block_size)) goto trunc;
            total += info->block_size;
        }
    }
    for (i = 0; i < 8u; i++) footer[i] = (uint8_t)GBP_AWINDUMP_END[i];
    info->total_crc32 = gbp_crc32_final(state);
    put_u32(footer + 8, info->total_crc32);
    if (sink(sink_ctx, footer, GBP_AWINDUMP_FOOTER_SIZE)) goto trunc;
    total += GBP_AWINDUMP_FOOTER_SIZE;
    if (written) *written = total;
    return (long)total;
trunc:
    info->flags |= GBP_AWINDUMP_FLAG_TRUNCATED;
    if (written) *written = total;
    return -4;
}

static int id_ok(const uint8_t *p)
{
    unsigned i, end = 0;
    for (i = 0; i < GBP_AWINDUMP_ID_FIELD; i++) {
        if (p[i] == 0u) { end = 1; continue; }
        if (end) return 0;
    }
    return p[GBP_AWINDUMP_ID_FIELD - 1u] == 0u;
}

static void id_read(char *dst, const uint8_t *p)
{
    unsigned i;
    for (i = 0; i < GBP_AWINDUMP_ID_FIELD; i++) dst[i] = (char)p[i];
}

int gbp_awindump_parse(const uint8_t *in, size_t n, struct gbp_awindump_info *info,
                       const uint8_t **records, const uint8_t **blocks)
{
    uint32_t i, off = 0u, sum = 0u;
    uint64_t body;
    if (records) *records = 0;
    if (blocks) *blocks = 0;
    if (!in || !info) return -1;
    if (n < GBP_AWINDUMP_HEADER_SIZE + GBP_AWINDUMP_FOOTER_SIZE) return -1;
    for (i = 0; i < 8u; i++) if (in[i] != (uint8_t)GBP_AWINDUMP_MAGIC[i]) return -1;
    zero((uint8_t *)info, sizeof *info);
    info->version = get_u16(in + 0x08);
    info->header_size = get_u16(in + 0x0A);
    if (info->version != GBP_AWINDUMP_VERSION || info->header_size != GBP_AWINDUMP_HEADER_SIZE) return -2;
    info->record_size = get_u32(in + 0x1C);
    info->block_size = get_u32(in + 0x10);
    if (info->record_size != GBP_AWINDUMP_RECORD_SIZE) return -2;
    if (info->block_size != GBP_AWIN_BLOCK_SIZE) return -2;
    info->header_crc32 = get_u32(in + GBP_AWINDUMP_HEADER_SIZE - 4u);
    if (info->header_crc32 != gbp_crc32(in, GBP_AWINDUMP_HEADER_SIZE - 4u)) return -3;
    info->flags = get_u32(in + 0x0C);
    info->blocks_per_window = get_u32(in + 0x14);
    info->windows_n = get_u32(in + 0x18);
    info->blocks_stored = get_u32(in + 0x20);
    info->blocks_seen = get_u32(in + 0x24);
    info->blocks_ignored = get_u32(in + 0x28);
    info->blocks_failed = get_u32(in + 0x2C);
    info->arms = get_u32(in + 0x30);
    info->arm_refused_busy = get_u32(in + 0x34);
    info->arm_refused_full = get_u32(in + 0x38);
    info->windows_closed = get_u32(in + 0x3C);
    info->tb_hz = get_u32(in + 0x40);
    info->ticks_min = get_u32(in + 0x44);
    info->ticks_max = get_u32(in + 0x48);
    info->ticks_n = get_u32(in + 0x4C);
    info->ticks_sum = get_u64(in + 0x50);
    info->off_records = get_u32(in + 0x58);
    info->off_blocks = get_u32(in + 0x5C);
    info->off_footer = get_u32(in + 0x60);
    info->total_size = get_u64(in + 0x68);
    if (info->flags & ~(uint32_t)GBP_AWINDUMP_FLAG_ALL) return -8;
    if (info->windows_n == 0u || info->windows_n > GBP_AWIN_WINDOWS) return -4;
    if (info->blocks_per_window != GBP_AWIN_BLOCKS) return -4;
    if (info->off_records != GBP_AWINDUMP_HEADER_SIZE) return -4;
    body = (uint64_t)info->windows_n * GBP_AWINDUMP_RECORD_SIZE;
    if ((uint64_t)info->off_blocks != GBP_AWINDUMP_HEADER_SIZE + body) return -4;
    if ((uint64_t)info->off_footer !=
        (uint64_t)info->off_blocks + (uint64_t)info->blocks_stored * info->block_size) return -4;
    if (info->total_size != (uint64_t)info->off_footer + GBP_AWINDUMP_FOOTER_SIZE) return -4;
    if ((uint64_t)n != info->total_size) return -4;
    for (i = 0xF0u; i < GBP_AWINDUMP_HEADER_SIZE - 4u; i++) if (in[i] != 0u) return -8;
    if (!id_ok(in + 0x70) || !id_ok(in + 0x90) || !id_ok(in + 0xB0) || !id_ok(in + 0xD0)) return -7;
    id_read(info->test_id, in + 0x70);
    id_read(info->build_id, in + 0x90);
    id_read(info->app, in + 0xB0);
    id_read(info->commit, in + 0xD0);
    for (i = 0; i < 8u; i++) if (in[info->off_footer + i] != (uint8_t)GBP_AWINDUMP_END[i]) return -5;
    info->total_crc32 = get_u32(in + info->off_footer + 8u);
    if (info->total_crc32 != gbp_crc32(in, info->off_footer)) return -6;
    for (i = 0; i < info->windows_n; i++) {
        const uint8_t *r = in + info->off_records + (size_t)i * GBP_AWINDUMP_RECORD_SIZE;
        uint32_t k, fl, nb, ro;
        for (k = 0x58u; k < 0x7Cu; k++) if (r[k] != 0u) return -8;
        if (gbp_crc32(r, 0x7Cu) != get_u32(r + 0x7C)) return -9;
        if (get_u32(r + 0x00) != i) return -9;
        fl = get_u32(r + 0x0C);
        if (fl & ~(uint32_t)GBP_AWIN_F_ALL) return -8;
        if ((fl & GBP_AWIN_F_CLOSED) && (fl & GBP_AWIN_F_INCOMPLETE)) return -9;
        nb = get_u32(r + 0x1C);
        if (nb > info->blocks_per_window) return -9;
        if ((fl & GBP_AWIN_F_CLOSED) && nb != info->blocks_per_window) return -9;
        ro = get_u32(r + 0x54);
        if (ro != off) return -9;
        off += nb * info->block_size;
        sum += nb;
        /* the control is window 0 and nothing else is */
        if (get_u32(r + 0x04) == (uint32_t)GBP_AWIN_CONTROL && i != 0u) return -9;
        if (i == 0u && get_u32(r + 0x04) != (uint32_t)GBP_AWIN_CONTROL) return -9;
    }
    if (sum != info->blocks_stored) return -4;
    if (records) *records = in + info->off_records;
    if (blocks) *blocks = in + info->off_blocks;
    return 0;
}
