/*
 * gbp_vfull.c — the full-frame sample store. See the header.
 */
#include <string.h>
#include "gbp_vfull.h"

void gbp_vfull_init(struct gbp_vfull *f, uint8_t *raw, uint16_t *tex, uint32_t spacing)
{
    uint32_t i;
    if (!f) return;
    memset(f, 0, sizeof *f);
    f->raw = raw;
    f->tex = tex;
    f->spacing = spacing ? spacing : GBP_VFULL_SPACING;
    for (i = 0; i < GBP_VFULL_K; i++) {
        f->s[i].sample_index = i;
        f->s[i].xfb_target = -1;
    }
}

void gbp_vfull_set_origin(struct gbp_vfull *f, uint32_t first_frame)
{
    if (!f || f->origin_set) return;
    f->origin = first_frame;
    f->origin_set = 1u;
}

int gbp_vfull_want(struct gbp_vfull *f, uint32_t frame_index)
{
    uint32_t d, i;
    if (!f) return -1;
    f->want_calls++;
    if (!f->origin_set || !f->raw || !f->tex) return -1;
    if (frame_index < f->origin) return -1;
    d = frame_index - f->origin;
    if (d % f->spacing) return -1;
    i = d / f->spacing;
    if (i >= GBP_VFULL_K) { f->skipped_capacity++; return -1; }
    if (f->s[i].state != GBP_VFULL_EMPTY) return -1;    /* never overwritten */
    f->wanted++;
    return (int)i;
}

static int valid(const struct gbp_vfull *f, int i)
{
    return f && i >= 0 && (uint32_t)i < GBP_VFULL_K;
}

int gbp_vfull_open(struct gbp_vfull *f, int i, uint32_t frame_index, uint32_t seq,
                   uint16_t slot, uint16_t tex, uint32_t life, uint64_t t_take)
{
    struct gbp_vfull_sample *s;
    if (!valid(f, i)) return -1;
    s = &f->s[i];
    if (s->state != GBP_VFULL_EMPTY) return -1;
    s->frame_index = frame_index;
    s->seq = seq;
    s->slot = slot;
    s->tex = tex;
    s->life = life;
    s->t_take = t_take;
    s->state = GBP_VFULL_OPEN;
    s->reason = GBP_VFULL_R_NONE;
    s->present = 0u;
    s->blocks_raw = s->blocks_tex = 0u;
    f->opened++;
    return 0;
}

int gbp_vfull_block(struct gbp_vfull *f, int i, uint32_t block,
                    const uint8_t *raw_block, const uint16_t *tex_row)
{
    struct gbp_vfull_sample *s;
    if (!valid(f, i) || !raw_block || !tex_row || block >= GBP_VFULL_BLOCKS) return -1;
    s = &f->s[i];
    if (s->state != GBP_VFULL_OPEN) return -1;
    if (s->present & ((uint64_t)1u << block)) return -1;   /* a block is copied once */
    memcpy(f->raw + (size_t)i * GBP_VFULL_RAW_BYTES + (size_t)block * GBP_VFULL_BLOCK_RAW,
           raw_block, GBP_VFULL_BLOCK_RAW);
    memcpy(f->tex + (size_t)i * GBP_VFULL_TEX_TEXELS + (size_t)block * GBP_VFULL_BLOCK_TEX,
           tex_row, GBP_VFULL_BLOCK_TEX * sizeof(uint16_t));
    s->present |= (uint64_t)1u << block;
    s->blocks_raw++;
    s->blocks_tex++;
    f->blocks_copied++;
    return 0;
}

int gbp_vfull_convert_done(struct gbp_vfull *f, int i, uint64_t t)
{
    struct gbp_vfull_sample *s;
    if (!valid(f, i)) return -1;
    s = &f->s[i];
    if (s->state != GBP_VFULL_OPEN) return -1;
    s->t_convert_done = t;
    if (s->blocks_raw == GBP_VFULL_BLOCKS && s->blocks_tex == GBP_VFULL_BLOCKS &&
        s->present == (((uint64_t)1u << GBP_VFULL_BLOCKS) - 1u)) {
        s->state = GBP_VFULL_COMPLETE;
        f->completed++;
        return 1;
    }
    s->state = GBP_VFULL_REFUSED;
    s->reason = GBP_VFULL_R_INCOMPLETE;
    f->refused++;
    return 0;
}

int gbp_vfull_refuse(struct gbp_vfull *f, int i, uint16_t reason)
{
    struct gbp_vfull_sample *s;
    if (!valid(f, i)) return -1;
    s = &f->s[i];
    if (s->state == GBP_VFULL_EMPTY) return -1;
    if (s->state == GBP_VFULL_REFUSED) return 0;
    /* a COMPLETE sample whose slot the producer reused after the copy is still
     * refused: the guard speaks for the frame, and the frame is what the bytes
     * claim to be */
    s->state = GBP_VFULL_REFUSED;
    s->reason = reason;
    f->refused++;
    return 0;
}

int gbp_vfull_decision(struct gbp_vfull *f, int i, uint64_t t, uint32_t retrace,
                       int16_t xfb_target, uint16_t disposition)
{
    struct gbp_vfull_sample *s;
    if (!valid(f, i)) return -1;
    s = &f->s[i];
    if (s->state == GBP_VFULL_EMPTY) return -1;
    s->t_decision = t;
    s->retrace_decision = retrace;
    s->xfb_target = xfb_target;
    s->disposition = disposition;
    return 0;
}

const uint8_t *gbp_vfull_raw(const struct gbp_vfull *f, int i)
{
    return valid(f, i) && f->raw ? f->raw + (size_t)i * GBP_VFULL_RAW_BYTES : 0;
}

const uint16_t *gbp_vfull_tex(const struct gbp_vfull *f, int i)
{
    return valid(f, i) && f->tex ? f->tex + (size_t)i * GBP_VFULL_TEX_TEXELS : 0;
}

uint32_t gbp_vfull_records(const struct gbp_vfull *f)
{
    uint32_t i, n = 0;
    if (!f) return 0;
    for (i = 0; i < GBP_VFULL_K; i++) if (f->s[i].state != GBP_VFULL_EMPTY) n++;
    return n;
}
