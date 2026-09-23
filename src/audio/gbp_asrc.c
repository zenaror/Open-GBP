/*
 * gbp_asrc — the replay backend. See gbp_asrc.h.
 */
#include "gbp_asrc.h"

#include "gbp_adec.h"
#include "gbp_awindump.h"

static uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

int gbp_asrc_replay_open(struct gbp_asrc_replay *r, const uint8_t *in, size_t n)
{
    struct gbp_awindump_info info;
    const uint8_t *records = 0, *blocks = 0;
    uint32_t i, off = 0u;
    int rc = gbp_awindump_parse(in, n, &info, &records, &blocks);
    if (rc < 0)
        return rc;
    if (info.windows_n > GBP_ASRC_MAX_WINDOWS)
        return -20;
    r->windows = info.windows_n;
    for (i = 0; i < info.windows_n; i++) {
        /* the anchor record, big-endian: kind @0x04, keys @0x18, blocks @0x1C (gbp_awin.h) */
        const uint8_t *rec = records + i * GBP_AWINDUMP_RECORD_SIZE;
        r->win[i].kind = be32(rec + 0x04);
        r->win[i].keys = be32(rec + 0x18);
        r->win[i].blocks = be32(rec + 0x1C);
        r->win[i].first = blocks + (size_t)off * GBP_ADEC_BLOCK_BYTES;
        off += r->win[i].blocks;
    }
    r->cur_win = 0u;
    r->cur_block = 0u;
    return 0;
}

int gbp_asrc_replay_select(struct gbp_asrc_replay *r, uint32_t w)
{
    if (w >= r->windows)
        return -1;
    r->cur_win = w;
    r->cur_block = 0u;
    return 0;
}

static int replay_next(void *ctx, const uint8_t **block)
{
    struct gbp_asrc_replay *r = (struct gbp_asrc_replay *)ctx;
    const struct gbp_asrc_window *w = &r->win[r->cur_win];
    if (r->cur_block >= w->blocks)
        return 0;
    *block = w->first + (size_t)r->cur_block * GBP_ADEC_BLOCK_BYTES;
    r->cur_block++;
    return 1;
}

void gbp_asrc_replay_source(struct gbp_asrc_replay *r, struct gbp_asrc *src)
{
    src->next = replay_next;
    src->ctx = r;
}
