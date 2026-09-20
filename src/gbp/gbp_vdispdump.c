/*
 * gbp_vdispdump.c — see gbp_vdispdump.h. Everything here runs AFTER the
 * teardown; there is no capture path in this file.
 */
#include "gbp_vdispdump.h"
#include "gbp_crc32.h"

#define ID_MAX (GBP_VDISPDUMP_ID_FIELD - 1u)

static void put_u16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static void put_u32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
}
static void put_u64(uint8_t *p, uint64_t v) { put_u32(p, (uint32_t)(v >> 32)); put_u32(p + 4, (uint32_t)v); }
static uint16_t get_u16(const uint8_t *p) { return (uint16_t)(((uint16_t)p[0] << 8) | p[1]); }
static uint32_t get_u32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}
static uint64_t get_u64(const uint8_t *p) { return ((uint64_t)get_u32(p) << 32) | get_u32(p + 4); }
static void zero(uint8_t *p, size_t n) { size_t i; for (i = 0; i < n; i++) p[i] = 0u; }

static int id_copy(char *dst, const char *src)
{
    size_t i;
    for (i = 0; i < GBP_VDISPDUMP_ID_FIELD; i++) dst[i] = 0;
    if (!src) return 0;
    for (i = 0; src[i]; i++) {
        if (i >= ID_MAX) return -1;            /* never truncated: an error */
        dst[i] = src[i];
    }
    return 0;
}

static int id_ok(const uint8_t *p)
{
    unsigned i, end = 0;
    for (i = 0; i < GBP_VDISPDUMP_ID_FIELD; i++) {
        if (p[i] == 0u) end = 1;
        else if (end) return 0;                /* no bytes after the terminator */
    }
    return p[GBP_VDISPDUMP_ID_FIELD - 1u] == 0u;
}

static void id_read(char *dst, const uint8_t *p)
{
    unsigned i;
    for (i = 0; i < GBP_VDISPDUMP_ID_FIELD; i++) dst[i] = (char)p[i];
    dst[GBP_VDISPDUMP_ID_FIELD - 1u] = 0;
}

int gbp_vdispdump_set_identity(struct gbp_vdispdump_info *info, const char *test_id,
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

int gbp_vdispdump_layout(struct gbp_vdispdump_info *info, const struct gbp_vdisp *d,
                         uint32_t tb_hz, uint32_t xfb_slots)
{
    uint64_t body;
    uint32_t i;
    if (!info || !d) return -1;
    info->version = (uint16_t)GBP_VDISPDUMP_VERSION;
    info->header_size = (uint16_t)GBP_VDISPDUMP_HEADER_SIZE;
    info->life_record_size = GBP_VDISPDUMP_LIFE_SIZE;
    info->event_record_size = GBP_VDISPDUMP_EVENT_SIZE;
    info->life_cap = d->life_cap;  info->life_n = d->life_n;
    info->event_cap = d->ev_cap;   info->event_n = d->ev_n;
    info->life_overflow = d->life_overflow;
    info->event_overflow = d->ev_overflow;
    info->drawdone_unmatched = d->drawdone_unmatched;
    info->decisions = d->decisions;
    info->tb_hz = tb_hz;
    info->tex_slots = GBP_VDISP_TEX_SLOTS;
    info->xfb_slots = xfb_slots;

    info->window_first_frame = 0xFFFFFFFFu;
    for (i = 0; i < d->life_n; i++)
        if (d->life[i].life_flags & GBP_VDISP_F_IN_WINDOW) { info->window_first_frame = d->life[i].frame_index; break; }

    info->source_handoffs = d->source_handoffs;
    info->source_deferred_frames = d->source_deferred_frames;
    info->source_defer_attempts = d->source_defer_attempts;
    info->source_dropped_interior = d->source_dropped_interior;
    info->terminal_pending = d->terminal_pending;
    info->max_deferred_depth = d->max_deferred_depth;
    info->order_violations = d->order_violations;

    info->flags = 0u;
    if (gbp_vdisp_intact(d))          info->flags |= GBP_VDISPDUMP_F_INTACT;
    if (d->order_violations)          info->flags |= GBP_VDISPDUMP_F_ORDER_VIOLATION;
    if (d->source_dropped_interior)   info->flags |= GBP_VDISPDUMP_F_INTERIOR_LOSS;
    if (d->life_overflow)             info->flags |= GBP_VDISPDUMP_F_LIFE_OVERFLOW;
    if (d->ev_overflow)               info->flags |= GBP_VDISPDUMP_F_EVENT_OVERFLOW;
    if (d->drawdone_unmatched)        info->flags |= GBP_VDISPDUMP_F_DRAWDONE_UNMATCHED;
    if (info->window_first_frame != 0xFFFFFFFFu) info->flags |= GBP_VDISPDUMP_F_WINDOW_OPENED;

    body = (uint64_t)info->life_n * GBP_VDISPDUMP_LIFE_SIZE
         + (uint64_t)info->event_n * GBP_VDISPDUMP_EVENT_SIZE;
    if (body > 0x7FFFFFFFu) return -1;
    info->off_life = GBP_VDISPDUMP_HEADER_SIZE;
    info->off_events = (uint32_t)(info->off_life + (uint64_t)info->life_n * GBP_VDISPDUMP_LIFE_SIZE);
    info->off_footer = (uint32_t)(GBP_VDISPDUMP_HEADER_SIZE + body);
    info->total_size = (uint64_t)info->off_footer + GBP_VDISPDUMP_FOOTER_SIZE;
    return 0;
}

static void build_life(const struct gbp_vdisp_life *r, uint8_t *o)
{
    zero(o, GBP_VDISPDUMP_LIFE_SIZE);
    put_u32(o + 0x00, r->frame_index);      put_u32(o + 0x04, r->seq);
    put_u64(o + 0x08, r->t_close);          put_u64(o + 0x10, r->t_take);
    put_u64(o + 0x18, r->t_convert_first);  put_u64(o + 0x20, r->t_convert_done);
    put_u64(o + 0x28, r->t_first_attempt);  put_u64(o + 0x30, r->t_first_defer);
    put_u64(o + 0x38, r->t_last_defer);     put_u64(o + 0x40, r->t_submit);
    put_u64(o + 0x48, r->t_drawdone);       put_u64(o + 0x50, r->t_decision);
    put_u32(o + 0x58, r->retrace_take);     put_u32(o + 0x5C, r->retrace_decision);
    put_u32(o + 0x60, r->convert_ticks);    put_u32(o + 0x64, r->submit_refusals);
    put_u32(o + 0x68, r->defer_attempts);
    put_u16(o + 0x6C, r->slot);             put_u16(o + 0x6E, r->tex);
    put_u16(o + 0x70, r->disposition);      put_u16(o + 0x72, r->reason);
    put_u32(o + 0x74, r->src_flags);        put_u32(o + 0x78, r->life_flags);
}

static void build_event(const struct gbp_vdisp_event *e, uint8_t *o)
{
    zero(o, GBP_VDISPDUMP_EVENT_SIZE);
    put_u64(o + 0x00, e->t);
    put_u32(o + 0x08, e->ordinal);          put_u32(o + 0x0C, e->retrace);
    put_u32(o + 0x10, e->frame_index);      put_u32(o + 0x14, e->prev_index);
    put_u16(o + 0x18, (uint16_t)e->xfb_current);
    put_u16(o + 0x1A, (uint16_t)e->xfb_pending);
    put_u16(o + 0x1C, (uint16_t)e->xfb_target);
    o[0x1E] = e->tex;  o[0x1F] = e->decision;  o[0x20] = e->reason;
    o[0x21] = e->tex_state[0];  o[0x22] = e->tex_state[1];  o[0x23] = e->inflight;
    put_u32(o + 0x24, e->newest_source);
}

static void build_header(const struct gbp_vdispdump_info *i, uint8_t *h)
{
    unsigned k;
    zero(h, GBP_VDISPDUMP_HEADER_SIZE);
    for (k = 0; k < 8u; k++) h[k] = (uint8_t)GBP_VDISPDUMP_MAGIC[k];
    put_u16(h + 0x08, i->version);          put_u16(h + 0x0A, i->header_size);
    put_u32(h + 0x0C, i->flags);
    put_u32(h + 0x10, i->life_record_size); put_u32(h + 0x14, i->event_record_size);
    put_u32(h + 0x18, i->life_cap);         put_u32(h + 0x1C, i->life_n);
    put_u32(h + 0x20, i->event_cap);        put_u32(h + 0x24, i->event_n);
    put_u32(h + 0x28, i->life_overflow);    put_u32(h + 0x2C, i->event_overflow);
    put_u32(h + 0x30, i->drawdone_unmatched); put_u32(h + 0x34, i->decisions);
    put_u32(h + 0x38, i->tb_hz);            put_u32(h + 0x3C, i->tex_slots);
    put_u32(h + 0x40, i->xfb_slots);        put_u32(h + 0x44, i->window_first_frame);
    put_u32(h + 0x48, i->off_life);         put_u32(h + 0x4C, i->off_events);
    put_u32(h + 0x50, i->off_footer);       put_u32(h + 0x54, i->life_crc32);
    put_u32(h + 0x58, i->event_crc32);
    put_u64(h + 0x60, i->total_size);
    put_u32(h + 0x68, i->source_handoffs);
    put_u32(h + 0x6C, i->source_deferred_frames);
    put_u32(h + 0x70, i->source_defer_attempts);
    put_u32(h + 0x74, i->source_dropped_interior);
    put_u32(h + 0x78, i->terminal_pending);
    put_u32(h + 0x7C, i->max_deferred_depth);
    put_u32(h + 0x80, i->order_violations);
    for (k = 0; k < GBP_VDISPDUMP_ID_FIELD; k++) {
        h[0x88 + k] = (uint8_t)i->test_id[k];
        h[0xA8 + k] = (uint8_t)i->build_id[k];
        h[0xC8 + k] = (uint8_t)i->app[k];
        h[0xE8 + k] = (uint8_t)i->commit[k];
    }
    /* 0x108 .. 0x13B stay zero: reserved, and a parser rejects them non-zero. */
    put_u32(h + GBP_VDISPDUMP_HEADER_SIZE - 4u,
            gbp_crc32(h, GBP_VDISPDUMP_HEADER_SIZE - 4u));
}

long gbp_vdispdump_stream(struct gbp_vdispdump_info *info, const struct gbp_vdisp *d,
                          uint8_t *chunk, uint32_t chunk_cap,
                          gbp_vdispdump_sink sink, void *sink_ctx, uint64_t *written)
{
    uint32_t i, state;
    uint64_t out = 0;
    uint8_t footer[GBP_VDISPDUMP_FOOTER_SIZE];
    if (written) *written = 0;
    if (!info || !d || !chunk || !sink) return -1;
    if (chunk_cap < GBP_VDISPDUMP_HEADER_SIZE) return -1;
    if (info->identity_error) return -2;
    if (gbp_vdispdump_layout(info, d, info->tb_hz, info->xfb_slots)) return -3;

    /* Section CRCs FIRST, so the header can carry them. Both passes read RAM
     * that nothing is writing any more: the capture has ended. */
    state = gbp_crc32_init();
    for (i = 0; i < info->life_n; i++) { build_life(&d->life[i], chunk); state = gbp_crc32_update(state, chunk, GBP_VDISPDUMP_LIFE_SIZE); }
    info->life_crc32 = gbp_crc32_final(state);
    state = gbp_crc32_init();
    for (i = 0; i < info->event_n; i++) { build_event(&d->ev[i], chunk); state = gbp_crc32_update(state, chunk, GBP_VDISPDUMP_EVENT_SIZE); }
    info->event_crc32 = gbp_crc32_final(state);

    state = gbp_crc32_init();
    build_header(info, chunk);
    info->header_crc32 = get_u32(chunk + GBP_VDISPDUMP_HEADER_SIZE - 4u);
    state = gbp_crc32_update(state, chunk, GBP_VDISPDUMP_HEADER_SIZE);
    if (sink(sink_ctx, chunk, GBP_VDISPDUMP_HEADER_SIZE)) { if (written) *written = out; return -4; }
    out += GBP_VDISPDUMP_HEADER_SIZE;

    for (i = 0; i < info->life_n; i++) {
        build_life(&d->life[i], chunk);
        state = gbp_crc32_update(state, chunk, GBP_VDISPDUMP_LIFE_SIZE);
        if (sink(sink_ctx, chunk, GBP_VDISPDUMP_LIFE_SIZE)) { if (written) *written = out; return -4; }
        out += GBP_VDISPDUMP_LIFE_SIZE;
    }
    for (i = 0; i < info->event_n; i++) {
        build_event(&d->ev[i], chunk);
        state = gbp_crc32_update(state, chunk, GBP_VDISPDUMP_EVENT_SIZE);
        if (sink(sink_ctx, chunk, GBP_VDISPDUMP_EVENT_SIZE)) { if (written) *written = out; return -4; }
        out += GBP_VDISPDUMP_EVENT_SIZE;
    }
    for (i = 0; i < 8u; i++) footer[i] = (uint8_t)GBP_VDISPDUMP_END[i];
    info->total_crc32 = gbp_crc32_final(state);
    put_u32(footer + 8, info->total_crc32);
    if (sink(sink_ctx, footer, GBP_VDISPDUMP_FOOTER_SIZE)) { if (written) *written = out; return -4; }
    out += GBP_VDISPDUMP_FOOTER_SIZE;
    if (written) *written = out;
    return (long)out;
}

int gbp_vdispdump_parse(const uint8_t *in, size_t n, struct gbp_vdispdump_info *info,
                        const uint8_t **life, const uint8_t **events)
{
    uint64_t body;
    uint32_t i, state;
    if (life) *life = 0;
    if (events) *events = 0;
    if (!in || !info) return -1;
    if (n < GBP_VDISPDUMP_HEADER_SIZE + GBP_VDISPDUMP_FOOTER_SIZE) return -1;
    for (i = 0; i < 8u; i++) if (in[i] != (uint8_t)GBP_VDISPDUMP_MAGIC[i]) return -1;

    info->version = get_u16(in + 0x08);
    info->header_size = get_u16(in + 0x0A);
    if (info->version != GBP_VDISPDUMP_VERSION) return -2;
    if (info->header_size != GBP_VDISPDUMP_HEADER_SIZE) return -2;
    info->header_crc32 = get_u32(in + GBP_VDISPDUMP_HEADER_SIZE - 4u);
    if (info->header_crc32 != gbp_crc32(in, GBP_VDISPDUMP_HEADER_SIZE - 4u)) return -3;

    info->flags = get_u32(in + 0x0C);
    info->life_record_size = get_u32(in + 0x10);
    info->event_record_size = get_u32(in + 0x14);
    if (info->life_record_size != GBP_VDISPDUMP_LIFE_SIZE) return -2;
    if (info->event_record_size != GBP_VDISPDUMP_EVENT_SIZE) return -2;
    info->life_cap = get_u32(in + 0x18);   info->life_n = get_u32(in + 0x1C);
    info->event_cap = get_u32(in + 0x20);  info->event_n = get_u32(in + 0x24);
    info->life_overflow = get_u32(in + 0x28);
    info->event_overflow = get_u32(in + 0x2C);
    info->drawdone_unmatched = get_u32(in + 0x30);
    info->decisions = get_u32(in + 0x34);
    info->tb_hz = get_u32(in + 0x38);
    info->tex_slots = get_u32(in + 0x3C);
    info->xfb_slots = get_u32(in + 0x40);
    info->window_first_frame = get_u32(in + 0x44);
    info->off_life = get_u32(in + 0x48);   info->off_events = get_u32(in + 0x4C);
    info->off_footer = get_u32(in + 0x50); info->life_crc32 = get_u32(in + 0x54);
    info->event_crc32 = get_u32(in + 0x58);
    info->total_size = get_u64(in + 0x60);
    info->source_handoffs = get_u32(in + 0x68);
    info->source_deferred_frames = get_u32(in + 0x6C);
    info->source_defer_attempts = get_u32(in + 0x70);
    info->source_dropped_interior = get_u32(in + 0x74);
    info->terminal_pending = get_u32(in + 0x78);
    info->max_deferred_depth = get_u32(in + 0x7C);
    info->order_violations = get_u32(in + 0x80);

    if (info->flags & ~GBP_VDISPDUMP_F_ALL) return -10;
    if (info->life_n > info->life_cap || info->event_n > info->event_cap) return -10;
    /* The flags must agree with the counters they summarise. */
    if (((info->flags & GBP_VDISPDUMP_F_LIFE_OVERFLOW) != 0u) != (info->life_overflow != 0u)) return -10;
    if (((info->flags & GBP_VDISPDUMP_F_EVENT_OVERFLOW) != 0u) != (info->event_overflow != 0u)) return -10;
    if (((info->flags & GBP_VDISPDUMP_F_DRAWDONE_UNMATCHED) != 0u) != (info->drawdone_unmatched != 0u)) return -10;
    if (((info->flags & GBP_VDISPDUMP_F_WINDOW_OPENED) != 0u) != (info->window_first_frame != 0xFFFFFFFFu)) return -10;
    if (((info->flags & GBP_VDISPDUMP_F_ORDER_VIOLATION) != 0u) != (info->order_violations != 0u)) return -10;
    if (((info->flags & GBP_VDISPDUMP_F_INTERIOR_LOSS) != 0u) != (info->source_dropped_interior != 0u)) return -10;
    if ((info->flags & GBP_VDISPDUMP_F_INTACT) &&
        (info->life_overflow || info->event_overflow || info->drawdone_unmatched ||
         info->order_violations ||
         info->decisions + info->source_deferred_frames != info->event_n)) return -10;

    body = (uint64_t)info->life_n * GBP_VDISPDUMP_LIFE_SIZE
         + (uint64_t)info->event_n * GBP_VDISPDUMP_EVENT_SIZE;
    if (info->off_life != GBP_VDISPDUMP_HEADER_SIZE) return -4;
    if ((uint64_t)info->off_events != info->off_life + (uint64_t)info->life_n * GBP_VDISPDUMP_LIFE_SIZE) return -4;
    if ((uint64_t)info->off_footer != GBP_VDISPDUMP_HEADER_SIZE + body) return -4;
    if (info->total_size != (uint64_t)info->off_footer + GBP_VDISPDUMP_FOOTER_SIZE) return -4;
    if ((uint64_t)n != info->total_size) return -4;

    for (i = 0x108u; i < GBP_VDISPDUMP_HEADER_SIZE - 4u; i++) if (in[i] != 0u) return -8;
    if (!id_ok(in + 0x88) || !id_ok(in + 0xA8) || !id_ok(in + 0xC8) || !id_ok(in + 0xE8)) return -7;
    id_read(info->test_id, in + 0x88);   id_read(info->build_id, in + 0xA8);
    id_read(info->app, in + 0xC8);       id_read(info->commit, in + 0xE8);

    for (i = 0; i < 8u; i++)
        if (in[info->off_footer + i] != (uint8_t)GBP_VDISPDUMP_END[i]) return -5;
    info->total_crc32 = get_u32(in + info->off_footer + 8u);
    if (info->total_crc32 != gbp_crc32(in, info->off_footer)) return -6;

    state = gbp_crc32_final(gbp_crc32_update(gbp_crc32_init(), in + info->off_life,
                                             (size_t)info->life_n * GBP_VDISPDUMP_LIFE_SIZE));
    if (state != info->life_crc32) return -9;
    state = gbp_crc32_final(gbp_crc32_update(gbp_crc32_init(), in + info->off_events,
                                             (size_t)info->event_n * GBP_VDISPDUMP_EVENT_SIZE));
    if (state != info->event_crc32) return -9;

    if (life) *life = in + info->off_life;
    if (events) *events = in + info->off_events;
    return 0;
}
