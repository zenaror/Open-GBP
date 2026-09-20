/*
 * gbp_vvidump.c — the OGBPVI1 writer and its strict parser. See the header.
 */
#include "gbp_vvidump.h"
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
    for (i = 0; i < GBP_VVIDUMP_ID_FIELD; i++) dst[i] = 0;
    if (!src) return 0;
    for (i = 0; src[i]; i++) {
        if (i >= GBP_VVIDUMP_ID_MAX) return -1;
        dst[i] = src[i];
    }
    return 0;
}

int gbp_vvidump_set_identity(struct gbp_vvidump_info *info, const char *test_id,
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

int gbp_vvidump_layout(struct gbp_vvidump_info *info, const struct gbp_vvi *v)
{
    uint64_t body;
    if (!info || !v) return -1;
    info->version = GBP_VVIDUMP_VERSION;
    info->header_size = GBP_VVIDUMP_HEADER_SIZE;
    info->record_size = GBP_VVIDUMP_RECORD_SIZE;
    info->records_cap = v->cap;
    info->records_n = v->n;
    info->handed = v->handed;
    info->latched = v->latched;
    info->superseded = v->superseded;
    info->overflow = v->overflow;
    info->observe_calls = v->observe_calls;
    info->awaiting_at_end = v->awaiting;
    info->flags &= (uint32_t)GBP_VVIDUMP_FLAG_TRUNCATED;
    if (v->overflow) info->flags |= GBP_VVIDUMP_FLAG_OVERFLOW;
    if (info->records_n > info->records_cap) return -1;
    body = (uint64_t)info->records_n * GBP_VVIDUMP_RECORD_SIZE;
    if (body > 0xFFFFFFFFull - GBP_VVIDUMP_HEADER_SIZE - GBP_VVIDUMP_FOOTER_SIZE) return -1;
    info->off_records = GBP_VVIDUMP_HEADER_SIZE;
    info->off_footer = (uint32_t)(GBP_VVIDUMP_HEADER_SIZE + body);
    info->total_size = (uint64_t)info->off_footer + GBP_VVIDUMP_FOOTER_SIZE;
    return 0;
}

static void build_header(const struct gbp_vvidump_info *info, uint8_t *h)
{
    unsigned i;
    zero(h, GBP_VVIDUMP_HEADER_SIZE);
    for (i = 0; i < 8; i++) h[i] = (uint8_t)GBP_VVIDUMP_MAGIC[i];
    put_u16(h + 0x08, info->version);
    put_u16(h + 0x0A, info->header_size);
    put_u32(h + 0x0C, info->flags);
    put_u32(h + 0x10, info->record_size);
    put_u32(h + 0x14, info->records_cap);
    put_u32(h + 0x18, info->records_n);
    put_u32(h + 0x1C, info->tb_hz);
    put_u32(h + 0x20, info->xfb_slots);
    put_u32(h + 0x24, info->handed);
    put_u32(h + 0x28, info->latched);
    put_u32(h + 0x2C, info->superseded);
    put_u32(h + 0x30, info->overflow);
    put_u32(h + 0x34, info->observe_calls);
    put_u32(h + 0x38, (uint32_t)info->awaiting_at_end);
    put_u32(h + 0x3C, info->off_records);
    put_u32(h + 0x40, info->off_footer);
    put_u64(h + 0x48, info->total_size);
    for (i = 0; i < GBP_VVIDUMP_ID_FIELD; i++) {
        h[0x50 + i] = (uint8_t)info->test_id[i];
        h[0x70 + i] = (uint8_t)info->build_id[i];
        h[0x90 + i] = (uint8_t)info->app[i];
        h[0xB0 + i] = (uint8_t)info->commit[i];
    }
    /* 0xD0 .. 0xFB reserved zero; CRC at 0xFC */
    put_u32(h + GBP_VVIDUMP_HEADER_SIZE - 4u, gbp_crc32(h, GBP_VVIDUMP_HEADER_SIZE - 4u));
}

static void build_record(const struct gbp_vvi_rec *r, uint8_t *b)
{
    zero(b, GBP_VVIDUMP_RECORD_SIZE);
    put_u32(b + 0x00, r->frame_index);
    put_u32(b + 0x04, r->life);
    put_u16(b + 0x08, (uint16_t)r->xfb);
    put_u16(b + 0x0A, r->flags);
    put_u32(b + 0x0C, r->phys);
    put_u64(b + 0x10, r->t_handed);
    put_u32(b + 0x18, r->retrace_handed);
    put_u32(b + 0x1C, r->retrace_latch);
    put_u64(b + 0x20, r->t_latch);
    put_u16(b + 0x28, r->vi14);
    put_u16(b + 0x2A, r->vi15);
    put_u16(b + 0x2C, r->vi18);
    put_u16(b + 0x2E, r->vi19);
    /* 0x30 .. 0x3B reserved zero; 0x3C record CRC over 0x00 .. 0x3C */
    put_u32(b + 0x3C, gbp_crc32(b, 0x3Cu));
}

long gbp_vvidump_stream(struct gbp_vvidump_info *info, const struct gbp_vvi *v,
                        uint8_t *chunk, uint32_t chunk_cap,
                        gbp_vvidump_sink sink, void *sink_ctx, uint64_t *written)
{
    uint64_t total = 0;
    uint32_t state, i;
    uint8_t footer[GBP_VVIDUMP_FOOTER_SIZE];
    if (written) *written = 0;
    if (!info || !v || !chunk || !sink) return -1;
    if (chunk_cap < GBP_VVIDUMP_HEADER_SIZE || chunk_cap < GBP_VVIDUMP_RECORD_SIZE) return -1;
    if (info->identity_error) return -2;
    if (gbp_vvidump_layout(info, v)) return -3;
    state = gbp_crc32_init();
    build_header(info, chunk);
    info->header_crc32 = get_u32(chunk + GBP_VVIDUMP_HEADER_SIZE - 4u);
    state = gbp_crc32_update(state, chunk, GBP_VVIDUMP_HEADER_SIZE);
    if (sink(sink_ctx, chunk, GBP_VVIDUMP_HEADER_SIZE)) goto trunc;
    total += GBP_VVIDUMP_HEADER_SIZE;
    for (i = 0; i < info->records_n; i++) {
        build_record(&v->rec[i], chunk);
        state = gbp_crc32_update(state, chunk, GBP_VVIDUMP_RECORD_SIZE);
        if (sink(sink_ctx, chunk, GBP_VVIDUMP_RECORD_SIZE)) goto trunc;
        total += GBP_VVIDUMP_RECORD_SIZE;
    }
    for (i = 0; i < 8u; i++) footer[i] = (uint8_t)GBP_VVIDUMP_END[i];
    info->total_crc32 = gbp_crc32_final(state);
    put_u32(footer + 8, info->total_crc32);
    if (sink(sink_ctx, footer, GBP_VVIDUMP_FOOTER_SIZE)) goto trunc;
    total += GBP_VVIDUMP_FOOTER_SIZE;
    if (written) *written = total;
    return (long)total;
trunc:
    info->flags |= GBP_VVIDUMP_FLAG_TRUNCATED;
    if (written) *written = total;
    return -4;
}

static int id_ok(const uint8_t *p)
{
    unsigned i, end = 0;
    for (i = 0; i < GBP_VVIDUMP_ID_FIELD; i++) {
        if (p[i] == 0u) { end = 1; continue; }
        if (end) return 0;
    }
    return p[GBP_VVIDUMP_ID_FIELD - 1u] == 0u;
}

static void id_read(char *dst, const uint8_t *p)
{
    unsigned i;
    for (i = 0; i < GBP_VVIDUMP_ID_FIELD; i++) dst[i] = (char)p[i];
}

int gbp_vvidump_parse(const uint8_t *in, size_t n, struct gbp_vvidump_info *info,
                      const uint8_t **records)
{
    uint32_t i;
    uint64_t body;
    if (records) *records = 0;
    if (!in || !info) return -1;
    if (n < GBP_VVIDUMP_HEADER_SIZE + GBP_VVIDUMP_FOOTER_SIZE) return -1;
    for (i = 0; i < 8u; i++) if (in[i] != (uint8_t)GBP_VVIDUMP_MAGIC[i]) return -1;
    zero((uint8_t *)info, sizeof *info);
    info->version = get_u16(in + 0x08);
    info->header_size = get_u16(in + 0x0A);
    if (info->version != GBP_VVIDUMP_VERSION || info->header_size != GBP_VVIDUMP_HEADER_SIZE) return -2;
    info->record_size = get_u32(in + 0x10);
    if (info->record_size != GBP_VVIDUMP_RECORD_SIZE) return -2;
    info->header_crc32 = get_u32(in + GBP_VVIDUMP_HEADER_SIZE - 4u);
    if (info->header_crc32 != gbp_crc32(in, GBP_VVIDUMP_HEADER_SIZE - 4u)) return -3;
    info->flags = get_u32(in + 0x0C);
    info->records_cap = get_u32(in + 0x14);
    info->records_n = get_u32(in + 0x18);
    info->tb_hz = get_u32(in + 0x1C);
    info->xfb_slots = get_u32(in + 0x20);
    info->handed = get_u32(in + 0x24);
    info->latched = get_u32(in + 0x28);
    info->superseded = get_u32(in + 0x2C);
    info->overflow = get_u32(in + 0x30);
    info->observe_calls = get_u32(in + 0x34);
    info->awaiting_at_end = (int32_t)get_u32(in + 0x38);
    info->off_records = get_u32(in + 0x3C);
    info->off_footer = get_u32(in + 0x40);
    info->total_size = get_u64(in + 0x48);
    if (info->flags & ~(uint32_t)GBP_VVIDUMP_FLAG_ALL) return -8;
    if (info->records_n > info->records_cap) return -4;
    if (info->off_records != GBP_VVIDUMP_HEADER_SIZE) return -4;
    body = (uint64_t)info->records_n * GBP_VVIDUMP_RECORD_SIZE;
    if ((uint64_t)info->off_footer != GBP_VVIDUMP_HEADER_SIZE + body) return -4;
    if (info->total_size != (uint64_t)info->off_footer + GBP_VVIDUMP_FOOTER_SIZE) return -4;
    if ((uint64_t)n != info->total_size) return -4;
    for (i = 0xD0u; i < GBP_VVIDUMP_HEADER_SIZE - 4u; i++) if (in[i] != 0u) return -8;
    if (!id_ok(in + 0x50) || !id_ok(in + 0x70) || !id_ok(in + 0x90) || !id_ok(in + 0xB0)) return -7;
    id_read(info->test_id, in + 0x50);
    id_read(info->build_id, in + 0x70);
    id_read(info->app, in + 0x90);
    id_read(info->commit, in + 0xB0);
    for (i = 0; i < 8u; i++) if (in[info->off_footer + i] != (uint8_t)GBP_VVIDUMP_END[i]) return -5;
    info->total_crc32 = get_u32(in + info->off_footer + 8u);
    if (info->total_crc32 != gbp_crc32(in, info->off_footer)) return -6;
    for (i = 0; i < info->records_n; i++) {
        const uint8_t *r = in + info->off_records + (size_t)i * GBP_VVIDUMP_RECORD_SIZE;
        uint32_t k;
        uint16_t fl = get_u16(r + 0x0A);
        for (k = 0x30u; k < 0x3Cu; k++) if (r[k] != 0u) return -8;
        if (fl & ~(uint16_t)(GBP_VVI_F_LATCHED | GBP_VVI_F_SUPERSEDED)) return -8;
        if ((fl & GBP_VVI_F_LATCHED) && (fl & GBP_VVI_F_SUPERSEDED)) return -9;
        if (!(fl & GBP_VVI_F_LATCHED) && (get_u64(r + 0x20) != 0u || get_u32(r + 0x1C) != 0u)) return -9;
        if (gbp_crc32(r, 0x3Cu) != get_u32(r + 0x3C)) return -9;
    }
    if (records) *records = in + info->off_records;
    return 0;
}
