/*
 * gbp_vfulldump.c — the OGBPFULL1 writer and its strict parser. See the header.
 */
#include "gbp_vfulldump.h"
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
    for (i = 0; i < GBP_VFULLDUMP_ID_FIELD; i++) dst[i] = 0;
    if (!src) return 0;
    for (i = 0; src[i]; i++) {
        if (i >= GBP_VFULLDUMP_ID_MAX) return -1;
        dst[i] = src[i];
    }
    return 0;
}

int gbp_vfulldump_set_identity(struct gbp_vfulldump_info *info, const char *test_id,
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

int gbp_vfulldump_layout(struct gbp_vfulldump_info *info, const struct gbp_vfull *f)
{
    uint64_t body;
    if (!info || !f) return -1;
    info->version = GBP_VFULLDUMP_VERSION;
    info->header_size = GBP_VFULLDUMP_HEADER_SIZE;
    info->record_size = GBP_VFULLDUMP_RECORD_SIZE;
    info->meta_size = GBP_VFULLDUMP_META_SIZE;
    info->records_n = gbp_vfull_records(f);
    info->k_cap = GBP_VFULL_K;
    info->spacing = f->spacing;
    info->origin = f->origin;
    info->raw_bytes = GBP_VFULL_RAW_BYTES;
    info->tex_bytes = GBP_VFULLDUMP_TEX_BYTES;
    info->blocks = GBP_VFULL_BLOCKS;
    info->block_bytes = GBP_VFULL_BLOCK_RAW;
    info->tex_row_bytes = GBP_VFULL_BLOCK_TEX * 2u;
    info->width = GBP_VPIX_WIDTH;
    info->height = GBP_VPIX_HEIGHT;
    info->want_calls = f->want_calls;
    info->wanted = f->wanted;
    info->opened = f->opened;
    info->completed = f->completed;
    info->refused = f->refused;
    info->skipped_capacity = f->skipped_capacity;
    info->blocks_copied = f->blocks_copied;
    info->flags &= (uint32_t)GBP_VFULLDUMP_FLAG_TRUNCATED;
    if (f->origin_set) info->flags |= GBP_VFULLDUMP_FLAG_ORIGIN_SET;
    if (f->skipped_capacity) info->flags |= GBP_VFULLDUMP_FLAG_CAPACITY_SKIPPED;
    body = (uint64_t)info->records_n * (uint64_t)GBP_VFULLDUMP_RECORD_SIZE;
    if (body > 0xFFFFFFFFull - GBP_VFULLDUMP_HEADER_SIZE - GBP_VFULLDUMP_FOOTER_SIZE) return -1;
    info->off_records = GBP_VFULLDUMP_HEADER_SIZE;
    info->off_footer = (uint32_t)(GBP_VFULLDUMP_HEADER_SIZE + body);
    info->total_size = (uint64_t)info->off_footer + GBP_VFULLDUMP_FOOTER_SIZE;
    return 0;
}

static void build_header(const struct gbp_vfulldump_info *info, uint8_t *h)
{
    unsigned i;
    zero(h, GBP_VFULLDUMP_HEADER_SIZE);
    for (i = 0; i < 8; i++) h[i] = (uint8_t)GBP_VFULLDUMP_MAGIC[i];
    put_u16(h + 0x08, info->version);
    put_u16(h + 0x0A, info->header_size);
    put_u32(h + 0x0C, info->flags);
    put_u32(h + 0x10, info->record_size);
    put_u32(h + 0x14, info->meta_size);
    put_u32(h + 0x18, info->records_n);
    put_u32(h + 0x1C, info->k_cap);
    put_u32(h + 0x20, info->spacing);
    put_u32(h + 0x24, info->origin);
    put_u32(h + 0x28, info->raw_bytes);
    put_u32(h + 0x2C, info->tex_bytes);
    put_u32(h + 0x30, info->blocks);
    put_u32(h + 0x34, info->block_bytes);
    put_u32(h + 0x38, info->tex_row_bytes);
    put_u32(h + 0x3C, info->width);
    put_u32(h + 0x40, info->height);
    put_u32(h + 0x44, info->tb_hz);
    put_u32(h + 0x48, info->want_calls);
    put_u32(h + 0x4C, info->wanted);
    put_u32(h + 0x50, info->opened);
    put_u32(h + 0x54, info->completed);
    put_u32(h + 0x58, info->refused);
    put_u32(h + 0x5C, info->skipped_capacity);
    put_u32(h + 0x60, info->blocks_copied);
    put_u32(h + 0x64, info->off_records);
    put_u32(h + 0x68, info->off_footer);
    put_u64(h + 0x70, info->total_size);
    for (i = 0; i < GBP_VFULLDUMP_ID_FIELD; i++) {
        h[0x78 + i] = (uint8_t)info->test_id[i];
        h[0x98 + i] = (uint8_t)info->build_id[i];
        h[0xB8 + i] = (uint8_t)info->app[i];
        h[0xD8 + i] = (uint8_t)info->commit[i];
    }
    /* 0xF8 .. 0xFB reserved zero; CRC at 0xFC */
    put_u32(h + GBP_VFULLDUMP_HEADER_SIZE - 4u, gbp_crc32(h, GBP_VFULLDUMP_HEADER_SIZE - 4u));
}

static void build_meta(const struct gbp_vfull_sample *s, uint8_t *m)
{
    zero(m, GBP_VFULLDUMP_META_SIZE);
    put_u32(m + 0x00, s->sample_index);
    put_u32(m + 0x04, s->frame_index);
    put_u32(m + 0x08, s->seq);
    put_u32(m + 0x0C, s->life);
    put_u16(m + 0x10, s->slot);
    put_u16(m + 0x12, s->tex);
    put_u16(m + 0x14, s->state);
    put_u16(m + 0x16, s->reason);
    put_u16(m + 0x18, s->blocks_raw);
    put_u16(m + 0x1A, s->blocks_tex);
    put_u32(m + 0x1C, s->retrace_decision);
    put_u64(m + 0x20, s->present);
    put_u64(m + 0x28, s->t_take);
    put_u64(m + 0x30, s->t_convert_done);
    put_u64(m + 0x38, s->t_decision);
    put_u16(m + 0x40, (uint16_t)s->xfb_target);
    put_u16(m + 0x42, s->disposition);
    /* 0x44 .. 0x77 reserved zero; 0x78 record CRC; 0x7C reserved */
}

long gbp_vfulldump_stream(struct gbp_vfulldump_info *info, const struct gbp_vfull *f,
                          uint8_t *chunk, uint32_t chunk_cap,
                          gbp_vfulldump_sink sink, void *sink_ctx, uint64_t *written)
{
    uint64_t total = 0;
    uint32_t state, i, k;
    uint8_t footer[GBP_VFULLDUMP_FOOTER_SIZE];

    if (written) *written = 0;
    if (!info || !f || !chunk || !sink) return -1;
    if (chunk_cap < GBP_VFULLDUMP_CHUNK) return -1;
    if (info->identity_error) return -2;
    if (gbp_vfulldump_layout(info, f)) return -3;

    state = gbp_crc32_init();
    build_header(info, chunk);
    info->header_crc32 = get_u32(chunk + GBP_VFULLDUMP_HEADER_SIZE - 4u);
    state = gbp_crc32_update(state, chunk, GBP_VFULLDUMP_HEADER_SIZE);
    if (sink(sink_ctx, chunk, GBP_VFULLDUMP_HEADER_SIZE)) goto trunc;
    total += GBP_VFULLDUMP_HEADER_SIZE;

    for (i = 0; i < GBP_VFULL_K; i++) {
        const struct gbp_vfull_sample *s = &f->s[i];
        const uint8_t *raw = gbp_vfull_raw(f, (int)i);
        const uint16_t *tex = gbp_vfull_tex(f, (int)i);
        uint32_t rstate, t;
        if (s->state == GBP_VFULL_EMPTY) continue;
        if (!raw || !tex) return -3;
        /* the record CRC: meta before the CRC field, then raw, then texture bytes */
        build_meta(s, chunk);
        rstate = gbp_crc32_init();
        rstate = gbp_crc32_update(rstate, chunk, 0x78u);
        rstate = gbp_crc32_update(rstate, raw, GBP_VFULL_RAW_BYTES);
        {
            /* the texture bytes, serialized big-endian in pieces behind the meta,
             * which stays in chunk[0 .. 0x80) until its CRC field is filled */
            uint8_t *tb = chunk + GBP_VFULLDUMP_META_SIZE;
            const uint32_t cap = (chunk_cap - GBP_VFULLDUMP_META_SIZE) / 2u;
            t = 0;
            while (t < GBP_VFULL_TEX_TEXELS) {
                uint32_t n = GBP_VFULL_TEX_TEXELS - t, j;
                if (n > cap) n = cap;
                for (j = 0; j < n; j++) put_u16(tb + j * 2u, tex[t + j]);
                rstate = gbp_crc32_update(rstate, tb, n * 2u);
                t += n;
            }
        }
        put_u32(chunk + 0x78, gbp_crc32_final(rstate));
        /* emit: meta, raw (from the store), texture (re-serialized in pieces) */
        state = gbp_crc32_update(state, chunk, GBP_VFULLDUMP_META_SIZE);
        if (sink(sink_ctx, chunk, GBP_VFULLDUMP_META_SIZE)) goto trunc;
        total += GBP_VFULLDUMP_META_SIZE;
        state = gbp_crc32_update(state, raw, GBP_VFULL_RAW_BYTES);
        if (sink(sink_ctx, raw, GBP_VFULL_RAW_BYTES)) goto trunc;
        total += GBP_VFULL_RAW_BYTES;
        for (t = 0; t < GBP_VFULL_TEX_TEXELS;) {
            uint32_t n = GBP_VFULL_TEX_TEXELS - t, j;
            if (n > chunk_cap / 2u) n = chunk_cap / 2u;
            for (j = 0; j < n; j++) put_u16(chunk + j * 2u, tex[t + j]);
            state = gbp_crc32_update(state, chunk, n * 2u);
            if (sink(sink_ctx, chunk, n * 2u)) goto trunc;
            total += n * 2u;
            t += n;
        }
    }
    for (k = 0; k < 8u; k++) footer[k] = (uint8_t)GBP_VFULLDUMP_END[k];
    info->total_crc32 = gbp_crc32_final(state);
    put_u32(footer + 8, info->total_crc32);
    if (sink(sink_ctx, footer, GBP_VFULLDUMP_FOOTER_SIZE)) goto trunc;
    total += GBP_VFULLDUMP_FOOTER_SIZE;
    if (written) *written = total;
    return (long)total;
trunc:
    info->flags |= GBP_VFULLDUMP_FLAG_TRUNCATED;
    if (written) *written = total;
    return -4;
}

static int id_ok(const uint8_t *p)
{
    unsigned i, end = 0;
    for (i = 0; i < GBP_VFULLDUMP_ID_FIELD; i++) {
        if (p[i] == 0u) { end = 1; continue; }
        if (end) return 0;
    }
    return p[GBP_VFULLDUMP_ID_FIELD - 1u] == 0u;
}

static void id_read(char *dst, const uint8_t *p)
{
    unsigned i;
    for (i = 0; i < GBP_VFULLDUMP_ID_FIELD; i++) dst[i] = (char)p[i];
}

int gbp_vfulldump_parse(const uint8_t *in, size_t n, struct gbp_vfulldump_info *info,
                        const uint8_t **records)
{
    uint32_t i, state;
    uint64_t body;
    if (records) *records = 0;
    if (!in || !info) return -1;
    if (n < GBP_VFULLDUMP_HEADER_SIZE + GBP_VFULLDUMP_FOOTER_SIZE) return -1;
    for (i = 0; i < 8u; i++) if (in[i] != (uint8_t)GBP_VFULLDUMP_MAGIC[i]) return -1;
    zero((uint8_t *)info, sizeof *info);
    info->version = get_u16(in + 0x08);
    info->header_size = get_u16(in + 0x0A);
    if (info->version != GBP_VFULLDUMP_VERSION || info->header_size != GBP_VFULLDUMP_HEADER_SIZE) return -2;
    info->record_size = get_u32(in + 0x10);
    info->meta_size = get_u32(in + 0x14);
    if (info->record_size != GBP_VFULLDUMP_RECORD_SIZE || info->meta_size != GBP_VFULLDUMP_META_SIZE) return -2;
    info->header_crc32 = get_u32(in + GBP_VFULLDUMP_HEADER_SIZE - 4u);
    if (info->header_crc32 != gbp_crc32(in, GBP_VFULLDUMP_HEADER_SIZE - 4u)) return -3;
    info->flags = get_u32(in + 0x0C);
    info->records_n = get_u32(in + 0x18);
    info->k_cap = get_u32(in + 0x1C);
    info->spacing = get_u32(in + 0x20);
    info->origin = get_u32(in + 0x24);
    info->raw_bytes = get_u32(in + 0x28);
    info->tex_bytes = get_u32(in + 0x2C);
    info->blocks = get_u32(in + 0x30);
    info->block_bytes = get_u32(in + 0x34);
    info->tex_row_bytes = get_u32(in + 0x38);
    info->width = get_u32(in + 0x3C);
    info->height = get_u32(in + 0x40);
    info->tb_hz = get_u32(in + 0x44);
    info->want_calls = get_u32(in + 0x48);
    info->wanted = get_u32(in + 0x4C);
    info->opened = get_u32(in + 0x50);
    info->completed = get_u32(in + 0x54);
    info->refused = get_u32(in + 0x58);
    info->skipped_capacity = get_u32(in + 0x5C);
    info->blocks_copied = get_u32(in + 0x60);
    info->off_records = get_u32(in + 0x64);
    info->off_footer = get_u32(in + 0x68);
    info->total_size = get_u64(in + 0x70);
    if (info->flags & ~(uint32_t)GBP_VFULLDUMP_FLAG_ALL) return -8;
    if (info->k_cap != GBP_VFULL_K || info->records_n > info->k_cap) return -2;
    if (info->raw_bytes != GBP_VFULL_RAW_BYTES || info->tex_bytes != GBP_VFULLDUMP_TEX_BYTES) return -2;
    if (info->blocks != GBP_VFULL_BLOCKS || info->block_bytes != GBP_VFULL_BLOCK_RAW) return -2;
    if (info->tex_row_bytes != GBP_VFULL_BLOCK_TEX * 2u) return -2;
    if (info->width != GBP_VPIX_WIDTH || info->height != GBP_VPIX_HEIGHT) return -2;
    if (info->off_records != GBP_VFULLDUMP_HEADER_SIZE) return -4;
    body = (uint64_t)info->records_n * (uint64_t)GBP_VFULLDUMP_RECORD_SIZE;
    if ((uint64_t)info->off_footer != GBP_VFULLDUMP_HEADER_SIZE + body) return -4;
    if (info->total_size != (uint64_t)info->off_footer + GBP_VFULLDUMP_FOOTER_SIZE) return -4;
    if ((uint64_t)n != info->total_size) return -4;
    for (i = 0xF8u; i < GBP_VFULLDUMP_HEADER_SIZE - 4u; i++) if (in[i] != 0u) return -8;
    if (!id_ok(in + 0x78) || !id_ok(in + 0x98) || !id_ok(in + 0xB8) || !id_ok(in + 0xD8)) return -7;
    id_read(info->test_id, in + 0x78);
    id_read(info->build_id, in + 0x98);
    id_read(info->app, in + 0xB8);
    id_read(info->commit, in + 0xD8);
    for (i = 0; i < 8u; i++) if (in[info->off_footer + i] != (uint8_t)GBP_VFULLDUMP_END[i]) return -5;
    info->total_crc32 = get_u32(in + info->off_footer + 8u);
    if (info->total_crc32 != gbp_crc32(in, info->off_footer)) return -6;
    for (i = 0; i < info->records_n; i++) {
        const uint8_t *r = in + info->off_records + (size_t)i * GBP_VFULLDUMP_RECORD_SIZE;
        uint64_t present = get_u64(r + 0x20);
        uint32_t pop = 0, k;
        uint16_t st = get_u16(r + 0x14);
        if (get_u32(r + 0x00) >= GBP_VFULL_K) return -9;
        if (st == GBP_VFULL_EMPTY || st > GBP_VFULL_REFUSED) return -9;
        for (k = 0x44u; k < 0x78u; k++) if (r[k] != 0u) return -8;
        if (get_u32(r + 0x7C) != 0u) return -8;
        for (k = 0; k < 64u; k++) if (present & ((uint64_t)1u << k)) pop++;
        if (present >> GBP_VFULL_BLOCKS) return -9;
        if (pop != get_u16(r + 0x18) || pop != get_u16(r + 0x1A)) return -9;
        if (st == GBP_VFULL_COMPLETE && pop != GBP_VFULL_BLOCKS) return -9;
        state = gbp_crc32_init();
        state = gbp_crc32_update(state, r, 0x78u);
        state = gbp_crc32_update(state, r + GBP_VFULLDUMP_META_SIZE, GBP_VFULL_RAW_BYTES + GBP_VFULLDUMP_TEX_BYTES);
        if (gbp_crc32_final(state) != get_u32(r + 0x78)) return -9;
    }
    if (records) *records = in + info->off_records;
    return 0;
}

uint32_t gbp_vfulldump_rec_sample_index(const uint8_t *rec) { return rec ? get_u32(rec + 0x00) : 0u; }
uint32_t gbp_vfulldump_rec_frame_index(const uint8_t *rec) { return rec ? get_u32(rec + 0x04) : 0u; }
uint32_t gbp_vfulldump_rec_seq(const uint8_t *rec) { return rec ? get_u32(rec + 0x08) : 0u; }
uint16_t gbp_vfulldump_rec_state(const uint8_t *rec) { return rec ? get_u16(rec + 0x14) : 0u; }
uint64_t gbp_vfulldump_rec_present(const uint8_t *rec) { return rec ? get_u64(rec + 0x20) : 0u; }
const uint8_t *gbp_vfulldump_rec_raw(const uint8_t *rec) { return rec ? rec + GBP_VFULLDUMP_META_SIZE : 0; }
uint16_t gbp_vfulldump_rec_texel(const uint8_t *rec, uint32_t i)
{
    if (!rec || i >= GBP_VFULL_TEX_TEXELS) return 0u;
    return get_u16(rec + GBP_VFULLDUMP_META_SIZE + GBP_VFULL_RAW_BYTES + (size_t)i * 2u);
}
