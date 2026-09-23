/*
 * gbp_alisten — see gbp_alisten.h.
 */
#include "gbp_alisten.h"

#include <string.h>

#include "gbp_adec.h"
#include "gbp_aresamp.h"
#include "gbp_asrc.h"
#include "gbp_awindump.h"

#define KIND_CONTROL 0u
#define KIND_PRESS   1u

struct emitter {
    struct gbp_aresamp rs;
    int16_t *out;
    uint32_t cap, frames, in_samples;
    int full;
};

/* One 4096 Hz input sample through the ONE resampler; every output lands in
 * both channels. A full buffer is an error, never a truncation. */
static void emit(struct emitter *e, int16_t s)
{
    int16_t y[GBP_ARESAMP_MAX_OUT];
    uint32_t k, n = gbp_aresamp_push(&e->rs, s, y);
    e->in_samples++;
    for (k = 0u; k < n; k++) {
        if (e->frames >= e->cap) {
            e->full = 1;
            return;
        }
        e->out[2u * e->frames] = y[k];
        e->out[2u * e->frames + 1u] = y[k];
        e->frames++;
    }
}

int gbp_alisten_build(const uint8_t *sidecar, size_t n, int16_t *out, uint32_t cap_frames,
                      struct gbp_alisten_info *info)
{
    struct gbp_awindump_info ai;
    const uint8_t *records = 0, *blocks = 0;
    struct gbp_asrc_replay rep;
    struct gbp_adec d;
    int16_t ring[4];
    int16_t pcm[GBP_ALISTEN_MAX_SLICED];
    struct emitter e;
    uint32_t w, b, i, r, control = 0xFFFFFFFFu;

    if (!info)
        return GBP_ALISTEN_ERR_ARG;
    memset(info, 0, sizeof *info);
    if (!sidecar || !out || cap_frames == 0u) {
        info->rc = GBP_ALISTEN_ERR_ARG;
        return info->rc;
    }
    /* 1. the strict parser, for the identity it checked; then the replay backend */
    if (gbp_awindump_parse(sidecar, n, &ai, &records, &blocks) < 0 || gbp_asrc_replay_open(&rep, sidecar, n) < 0) {
        info->rc = GBP_ALISTEN_ERR_PARSE;
        return info->rc;
    }
    info->total_crc32 = ai.total_crc32;
    info->windows = rep.windows;

    /* 2. calibrate on the CONTROL window, as #80 and #81 did */
    gbp_adec_init(&d, ring, (uint32_t)(sizeof ring / sizeof ring[0]));
    for (w = 0u; w < rep.windows; w++) {
        if (rep.win[w].kind != KIND_CONTROL)
            continue;
        info->controls++;
        if (control == 0xFFFFFFFFu)
            control = w;
    }
    if (control == 0xFFFFFFFFu) {
        info->rc = GBP_ALISTEN_ERR_CONTROL;
        return info->rc;
    }
    for (b = 0u; b < rep.win[control].blocks; b++)
        gbp_adec_calibrate(&d, rep.win[control].first + (size_t)b * GBP_ADEC_BLOCK_BYTES);

    memset(&e, 0, sizeof e);
    gbp_aresamp_init(&e.rs);
    e.out = out;
    e.cap = cap_frames;

    for (w = 0u; w < rep.windows && info->tones < GBP_ALISTEN_MAX_TONES; w++) {
        const uint32_t t = info->tones;
        uint32_t len, first;
        if (rep.win[w].kind != KIND_PRESS)
            continue;
        if (rep.win[w].blocks <= GBP_ALISTEN_ONSET) {
            info->rc = GBP_ALISTEN_ERR_TONES;
            return info->rc;
        }
        /* 3. the SLICED region, one sample per AUDIO block */
        len = rep.win[w].blocks - GBP_ALISTEN_ONSET;
        if (len > GBP_ALISTEN_MAX_SLICED)
            len = GBP_ALISTEN_MAX_SLICED;
        for (i = 0u; i < len; i++) {
            (void)gbp_adec_push_block(&d, rep.win[w].first + (size_t)(GBP_ALISTEN_ONSET + i) * GBP_ADEC_BLOCK_BYTES);
            if (!gbp_adec_pop(&d, &pcm[i]))
                pcm[i] = 0;                        /* cannot happen: one push, one pop */
        }
        info->keys[t] = rep.win[w].keys;
        info->sliced[t] = len;
        /* 4. repeated to about one second: v17decode's max(1, round(4096 / len)) */
        info->repeats[t] = (GBP_ALISTEN_IN_RATE + len / 2u) / len;
        if (info->repeats[t] == 0u)
            info->repeats[t] = 1u;
        first = e.frames;
        for (r = 0u; r < info->repeats[t]; r++)
            for (i = 0u; i < len; i++)
                emit(&e, pcm[i]);
        info->seg_first[2u * t] = first;
        info->seg_frames[2u * t] = e.frames - first;
        /* 5. the gap: silence, not data */
        first = e.frames;
        for (i = 0u; i < GBP_ALISTEN_GAP_IN; i++)
            emit(&e, 0);
        info->seg_first[2u * t + 1u] = first;
        info->seg_frames[2u * t + 1u] = e.frames - first;
        info->tones++;
        if (e.full) {
            info->rc = GBP_ALISTEN_ERR_CAPACITY;
            return info->rc;
        }
    }
    if (info->tones == 0u) {
        info->rc = GBP_ALISTEN_ERR_TONES;
        return info->rc;
    }
    info->segs = 2u * info->tones;
    info->in_samples = e.in_samples;
    info->out_frames = e.frames;
    info->dec_blocks = d.blocks_in;
    info->dec_lost = d.lost;
    info->dec_overflow = d.overflow;
    return 0;
}

int gbp_alisten_segment(const struct gbp_alisten_info *info, uint32_t frame)
{
    uint32_t s;
    if (!info)
        return -1;
    for (s = 0u; s < info->segs; s++)
        if (frame >= info->seg_first[s] && frame - info->seg_first[s] < info->seg_frames[s])
            return (int)s;
    return -1;
}
