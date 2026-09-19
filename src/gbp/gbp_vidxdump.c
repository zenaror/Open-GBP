/*
 * gbp_vidxdump.c — the OGBPIDXCAP1 writer and its strict parser. See the header
 * for the layout and for why this is a new magic rather than an OGBPSEQ1
 * version.
 *
 * Every field is written byte by byte, big-endian. No struct is ever copied
 * into the file, so compiler padding, member order and host endianness cannot
 * reach the format.
 */
#include "gbp_vidxdump.h"
#include "gbp_crc32.h"

/* ---- primitive encoders / decoders -------------------------------------- */

static void put_u16(uint8_t *p, uint16_t v)
{
    p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v;
}

static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
}

static void put_u64(uint8_t *p, uint64_t v)
{
    put_u32(p, (uint32_t)(v >> 32));
    put_u32(p + 4, (uint32_t)v);
}

static uint16_t get_u16(const uint8_t *p)
{
    return (uint16_t)(((uint16_t)p[0] << 8) | (uint16_t)p[1]);
}

static uint32_t get_u32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8)  | (uint32_t)p[3];
}

static uint64_t get_u64(const uint8_t *p)
{
    return ((uint64_t)get_u32(p) << 32) | (uint64_t)get_u32(p + 4);
}

static void zero(uint8_t *p, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) p[i] = 0u;
}

static int id_copy(char *dst, const char *src)
{
    size_t i = 0;
    for (i = 0; i < GBP_VIDXDUMP_ID_FIELD; i++) dst[i] = 0;
    if (!src) return 0;
    for (i = 0; src[i]; i++) {
        if (i >= GBP_VIDXDUMP_ID_MAX) return -1;   /* never truncated: an error */
        dst[i] = src[i];
    }
    return 0;
}

int gbp_vidxdump_set_identity(struct gbp_vidxdump_info *info, const char *test_id,
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

/* ---- layout -------------------------------------------------------------- */

int gbp_vidxdump_layout(struct gbp_vidxdump_info *info, const struct gbp_vwitness *w)
{
    uint64_t body;
    if (!info || !w) return -1;
    info->version = GBP_VIDXDUMP_VERSION;
    info->header_size = GBP_VIDXDUMP_HEADER_SIZE;
    info->record_size = GBP_VIDXDUMP_RECORD_SIZE;
    info->records_cap = w->cap;
    info->records_n = w->n;
    info->target_frames = w->target;
    info->witness_words = GBP_VWITNESS_WORDS;
    info->witness_blocks = GBP_VWITNESS_BLOCKS;
    info->strip_x0 = GBP_VWITNESS_STRIP_X0;
    info->strip_row = GBP_VWITNESS_ROW;
    info->block_bytes = GBP_VWITNESS_BLOCK_BYTES;
    info->line_stride = GBP_VWITNESS_LINE_STRIDE;
    info->frames_seen = w->frames_seen;
    info->frames_discarded = w->frames_discarded;
    info->blocks_staged = w->blocks_staged;
    info->blocks_placed = w->blocks_placed;
    info->blocks_out_of_range = w->blocks_out_of_range;
    info->copy_ticks_min = (w->copy_ticks_n ? w->copy_ticks_min : 0u);
    info->copy_ticks_max = w->copy_ticks_max;
    info->copy_ticks_n = w->copy_ticks_n;
    info->copy_ticks_sum = w->copy_ticks_sum;
    info->t_first_record = w->t_first_record;
    info->t_last_record = w->t_last_record;
    if (w->store_full) info->flags |= GBP_VIDXDUMP_FLAG_STORE_FULL;
    if (w->target_reached) info->flags |= GBP_VIDXDUMP_FLAG_TARGET_REACHED;

    if (info->records_n > info->records_cap) return -1;
    body = (uint64_t)info->records_n * (uint64_t)GBP_VIDXDUMP_RECORD_SIZE;
    if (body > 0xFFFFFFFFull - GBP_VIDXDUMP_HEADER_SIZE - GBP_VIDXDUMP_FOOTER_SIZE) return -1;
    info->off_records = GBP_VIDXDUMP_HEADER_SIZE;
    info->off_footer = (uint32_t)(GBP_VIDXDUMP_HEADER_SIZE + body);
    info->total_size = (uint64_t)info->off_footer + GBP_VIDXDUMP_FOOTER_SIZE;
    return 0;
}

/* ---- the header ---------------------------------------------------------- */

static void build_header(const struct gbp_vidxdump_info *info, uint8_t *h)
{
    unsigned i;
    zero(h, GBP_VIDXDUMP_HEADER_SIZE);
    for (i = 0; i < 8; i++) h[i] = (uint8_t)GBP_VIDXDUMP_MAGIC[i];
    put_u16(h + 0x08, info->version);
    put_u16(h + 0x0A, info->header_size);
    put_u32(h + 0x0C, info->flags);
    put_u32(h + 0x10, info->record_size);
    put_u32(h + 0x14, info->records_cap);
    put_u32(h + 0x18, info->records_n);
    put_u32(h + 0x1C, info->witness_words);
    put_u32(h + 0x20, info->witness_blocks);
    put_u32(h + 0x24, info->strip_x0);
    put_u32(h + 0x28, info->strip_row);
    put_u32(h + 0x2C, info->block_bytes);
    put_u32(h + 0x30, info->line_stride);
    put_u32(h + 0x34, info->target_frames);
    put_u16(h + 0x38, info->stop_reason);
    put_u16(h + 0x3A, info->status_code);
    put_u32(h + 0x3C, info->tb_hz);
    put_u32(h + 0x40, info->frames_seen);
    put_u32(h + 0x44, info->frames_discarded);
    put_u32(h + 0x48, info->blocks_staged);
    put_u32(h + 0x4C, info->blocks_placed);
    put_u32(h + 0x50, info->blocks_out_of_range);
    put_u32(h + 0x54, info->copy_ticks_min);
    put_u32(h + 0x58, info->copy_ticks_max);
    put_u32(h + 0x5C, info->copy_ticks_n);
    put_u64(h + 0x60, info->copy_ticks_sum);
    put_u64(h + 0x68, info->t_first_record);
    put_u64(h + 0x70, info->t_last_record);
    put_u32(h + 0x78, info->off_records);
    put_u32(h + 0x7C, info->off_footer);
    put_u64(h + 0x80, info->total_size);
    for (i = 0; i < GBP_VIDXDUMP_ID_FIELD; i++) {
        h[0x88 + i] = (uint8_t)info->test_id[i];
        h[0xA8 + i] = (uint8_t)info->build_id[i];
        h[0xC8 + i] = (uint8_t)info->app[i];
        h[0xE8 + i] = (uint8_t)info->commit[i];
    }
    /* 0x108 .. 0x17B stay zero: reserved, and a parser rejects them non-zero. */
    put_u32(h + GBP_VIDXDUMP_HEADER_SIZE - 4u,
            gbp_crc32(h, GBP_VIDXDUMP_HEADER_SIZE - 4u));
}

/* ---- one record ---------------------------------------------------------- */

static void build_record(const struct gbp_vwitness *w, uint32_t i, uint8_t *r)
{
    const struct gbp_vwitness_meta *m = gbp_vwitness_meta_at(w, i);
    const uint16_t *words = gbp_vwitness_record(w, i);
    uint32_t k, state;
    zero(r, GBP_VIDXDUMP_RECORD_SIZE);
    if (!m || !words) return;
    put_u32(r + 0x00, m->frame_index);
    put_u16(r + 0x04, m->blocks);
    put_u16(r + 0x06, m->flags);
    put_u16(r + 0x08, m->completeness);
    put_u16(r + 0x0A, m->disagreements);
    put_u32(r + 0x0C, m->blocks_captured);
    put_u64(r + 0x10, m->t_first_block);
    put_u64(r + 0x18, m->t_last_block);
    put_u64(r + 0x20, m->present);
    /* 0x28 record_crc32, filled below; 0x2C reserved and zero. */
    for (k = 0; k < GBP_VWITNESS_FRAME_WORDS; k++)
        put_u16(r + GBP_VIDXDUMP_META_SIZE + k * 2u, words[k]);
    /* The record seals ITS OWN bytes: the 40 bytes before the CRC field, then
     * everything after the reserved word. A single corrupted record is then
     * identifiable, not merely "the file is bad". */
    state = gbp_crc32_init();
    state = gbp_crc32_update(state, r, 0x28u);
    state = gbp_crc32_update(state, r + GBP_VIDXDUMP_META_SIZE, GBP_VWITNESS_FRAME_BYTES);
    put_u32(r + 0x28, gbp_crc32_final(state));
}

/* ---- streaming ----------------------------------------------------------- */

long gbp_vidxdump_stream(struct gbp_vidxdump_info *info, const struct gbp_vwitness *w,
                         uint8_t *chunk, uint32_t chunk_cap,
                         gbp_vidxdump_sink sink, void *sink_ctx, uint64_t *written)
{
    uint64_t total = 0;
    uint32_t state, i;
    uint8_t footer[GBP_VIDXDUMP_FOOTER_SIZE];

    if (written) *written = 0;
    if (!info || !w || !chunk || !sink) return -1;
    if (chunk_cap < GBP_VIDXDUMP_HEADER_SIZE || chunk_cap < GBP_VIDXDUMP_RECORD_SIZE) return -1;
    if (info->identity_error) return -2;
    if (gbp_vidxdump_layout(info, w)) return -3;

    state = gbp_crc32_init();

    build_header(info, chunk);
    info->header_crc32 = get_u32(chunk + GBP_VIDXDUMP_HEADER_SIZE - 4u);
    state = gbp_crc32_update(state, chunk, GBP_VIDXDUMP_HEADER_SIZE);
    if (sink(sink_ctx, chunk, GBP_VIDXDUMP_HEADER_SIZE)) {
        info->flags |= GBP_VIDXDUMP_FLAG_TRUNCATED;
        if (written) *written = total;
        return -4;
    }
    total += GBP_VIDXDUMP_HEADER_SIZE;

    /* Records are emitted one at a time into the same chunk: the ONLY transient
     * buffer is 4 368 bytes, and no second copy of the 8.4 MiB store exists. */
    for (i = 0; i < info->records_n; i++) {
        build_record(w, i, chunk);
        state = gbp_crc32_update(state, chunk, GBP_VIDXDUMP_RECORD_SIZE);
        if (sink(sink_ctx, chunk, GBP_VIDXDUMP_RECORD_SIZE)) {
            info->flags |= GBP_VIDXDUMP_FLAG_TRUNCATED;
            if (written) *written = total;
            return -4;
        }
        total += GBP_VIDXDUMP_RECORD_SIZE;
    }

    for (i = 0; i < 8u; i++) footer[i] = (uint8_t)GBP_VIDXDUMP_END[i];
    info->total_crc32 = gbp_crc32_final(state);
    put_u32(footer + 8, info->total_crc32);
    if (sink(sink_ctx, footer, GBP_VIDXDUMP_FOOTER_SIZE)) {
        info->flags |= GBP_VIDXDUMP_FLAG_TRUNCATED;
        if (written) *written = total;
        return -4;
    }
    total += GBP_VIDXDUMP_FOOTER_SIZE;
    if (written) *written = total;
    return (long)total;
}

/* ---- the strict parser --------------------------------------------------- */

static int id_ok(const uint8_t *p)
{
    unsigned i, end = 0;
    for (i = 0; i < GBP_VIDXDUMP_ID_FIELD; i++) {
        if (p[i] == 0u) { end = 1; continue; }
        if (end) return 0;                    /* a byte after the terminator */
    }
    return p[GBP_VIDXDUMP_ID_FIELD - 1u] == 0u;   /* always terminated */
}

static void id_read(char *dst, const uint8_t *p)
{
    unsigned i;
    for (i = 0; i < GBP_VIDXDUMP_ID_FIELD; i++) dst[i] = (char)p[i];
}

int gbp_vidxdump_parse(const uint8_t *in, size_t n, struct gbp_vidxdump_info *info,
                       const uint8_t **records)
{
    uint32_t i, state;
    uint64_t body;
    if (records) *records = 0;
    if (!in || !info) return -1;
    if (n < GBP_VIDXDUMP_HEADER_SIZE + GBP_VIDXDUMP_FOOTER_SIZE) return -1;
    for (i = 0; i < 8u; i++) if (in[i] != (uint8_t)GBP_VIDXDUMP_MAGIC[i]) return -1;

    zero((uint8_t *)info, sizeof *info);
    info->version = get_u16(in + 0x08);
    info->header_size = get_u16(in + 0x0A);
    if (info->version != GBP_VIDXDUMP_VERSION) return -2;
    if (info->header_size != GBP_VIDXDUMP_HEADER_SIZE) return -2;
    info->record_size = get_u32(in + 0x10);
    if (info->record_size != GBP_VIDXDUMP_RECORD_SIZE) return -2;

    info->header_crc32 = get_u32(in + GBP_VIDXDUMP_HEADER_SIZE - 4u);
    if (info->header_crc32 != gbp_crc32(in, GBP_VIDXDUMP_HEADER_SIZE - 4u)) return -3;

    info->flags = get_u32(in + 0x0C);
    info->records_cap = get_u32(in + 0x14);
    info->records_n = get_u32(in + 0x18);
    info->witness_words = get_u32(in + 0x1C);
    info->witness_blocks = get_u32(in + 0x20);
    info->strip_x0 = get_u32(in + 0x24);
    info->strip_row = get_u32(in + 0x28);
    info->block_bytes = get_u32(in + 0x2C);
    info->line_stride = get_u32(in + 0x30);
    info->target_frames = get_u32(in + 0x34);
    info->stop_reason = get_u16(in + 0x38);
    info->status_code = get_u16(in + 0x3A);
    info->tb_hz = get_u32(in + 0x3C);
    info->frames_seen = get_u32(in + 0x40);
    info->frames_discarded = get_u32(in + 0x44);
    info->blocks_staged = get_u32(in + 0x48);
    info->blocks_placed = get_u32(in + 0x4C);
    info->blocks_out_of_range = get_u32(in + 0x50);
    info->copy_ticks_min = get_u32(in + 0x54);
    info->copy_ticks_max = get_u32(in + 0x58);
    info->copy_ticks_n = get_u32(in + 0x5C);
    info->copy_ticks_sum = get_u64(in + 0x60);
    info->t_first_record = get_u64(in + 0x68);
    info->t_last_record = get_u64(in + 0x70);
    info->off_records = get_u32(in + 0x78);
    info->off_footer = get_u32(in + 0x7C);
    info->total_size = get_u64(in + 0x80);

    if (info->flags & ~(uint32_t)GBP_VIDXDUMP_FLAG_ALL) return -8;
    if (info->witness_words != GBP_VWITNESS_WORDS) return -2;
    if (info->witness_blocks != GBP_VWITNESS_BLOCKS) return -2;
    if (info->off_records != GBP_VIDXDUMP_HEADER_SIZE) return -4;
    if (info->records_n > info->records_cap) return -4;

    body = (uint64_t)info->records_n * (uint64_t)GBP_VIDXDUMP_RECORD_SIZE;
    if ((uint64_t)info->off_footer != GBP_VIDXDUMP_HEADER_SIZE + body) return -4;
    if (info->total_size != (uint64_t)info->off_footer + GBP_VIDXDUMP_FOOTER_SIZE) return -4;
    if ((uint64_t)n != info->total_size) return -4;

    for (i = 0x108u; i < GBP_VIDXDUMP_HEADER_SIZE - 4u; i++) if (in[i] != 0u) return -8;
    if (!id_ok(in + 0x88) || !id_ok(in + 0xA8) || !id_ok(in + 0xC8) || !id_ok(in + 0xE8)) return -7;
    id_read(info->test_id, in + 0x88);
    id_read(info->build_id, in + 0xA8);
    id_read(info->app, in + 0xC8);
    id_read(info->commit, in + 0xE8);

    for (i = 0; i < 8u; i++)
        if (in[info->off_footer + i] != (uint8_t)GBP_VIDXDUMP_END[i]) return -5;
    info->total_crc32 = get_u32(in + info->off_footer + 8u);
    if (info->total_crc32 != gbp_crc32(in, info->off_footer)) return -6;

    /* Per-record integrity, after the whole-file CRC has already passed: this
     * catches a producer that built a record wrongly, which a file-wide CRC
     * cannot distinguish from a correct one. */
    for (i = 0; i < info->records_n; i++) {
        const uint8_t *r = in + info->off_records + (size_t)i * GBP_VIDXDUMP_RECORD_SIZE;
        uint64_t present = get_u64(r + 0x20);
        uint32_t captured = get_u32(r + 0x0C), pop = 0, k;
        if (get_u32(r + 0x2C) != 0u) return -8;
        for (k = 0; k < 64u; k++) if (present & ((uint64_t)1u << k)) pop++;
        if (pop != captured) return -9;
        if (present >> GBP_VWITNESS_BLOCKS) return -9;      /* a bit past the geometry */
        if (get_u16(r + 0x04) > GBP_VWITNESS_MAX_BLOCKS) return -9;
        state = gbp_crc32_init();
        state = gbp_crc32_update(state, r, 0x28u);
        state = gbp_crc32_update(state, r + GBP_VIDXDUMP_META_SIZE, GBP_VWITNESS_FRAME_BYTES);
        if (gbp_crc32_final(state) != get_u32(r + 0x28)) return -9;
    }

    /* A file cannot both have reached the target and have refused a commit for
     * lack of room: the target is at most the capacity, so one excludes the
     * other. Declaring both means the producer is not trustworthy. */
    if ((info->flags & GBP_VIDXDUMP_FLAG_STORE_FULL) &&
        (info->flags & GBP_VIDXDUMP_FLAG_TARGET_REACHED) &&
        info->target_frames == info->records_cap) return -10;
    if ((info->flags & GBP_VIDXDUMP_FLAG_TARGET_REACHED) && info->records_n < info->target_frames)
        return -10;
    if (info->target_frames > info->records_cap) return -10;

    if (records) *records = in + info->off_records;
    return 0;
}

/* ---- record accessors ---------------------------------------------------- */

uint32_t gbp_vidxdump_rec_frame_index(const uint8_t *rec) { return rec ? get_u32(rec + 0x00) : 0u; }
uint16_t gbp_vidxdump_rec_blocks(const uint8_t *rec) { return rec ? get_u16(rec + 0x04) : 0u; }
uint16_t gbp_vidxdump_rec_flags(const uint8_t *rec) { return rec ? get_u16(rec + 0x06) : 0u; }
uint16_t gbp_vidxdump_rec_completeness(const uint8_t *rec) { return rec ? get_u16(rec + 0x08) : 0u; }
uint64_t gbp_vidxdump_rec_present(const uint8_t *rec) { return rec ? get_u64(rec + 0x20) : 0u; }

uint16_t gbp_vidxdump_rec_word(const uint8_t *rec, uint32_t block, uint32_t word)
{
    if (!rec || block >= GBP_VWITNESS_BLOCKS || word >= GBP_VWITNESS_WORDS) return 0u;
    return get_u16(rec + GBP_VIDXDUMP_META_SIZE + ((size_t)block * GBP_VWITNESS_WORDS + word) * 2u);
}
