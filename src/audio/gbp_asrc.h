/*
 * gbp_asrc — where AUDIO blocks come from, behind one boundary (CLAUDE.md §10).
 *
 * The decoder takes blocks and does not care whether they came from the drain,
 * from a mock, or from a capture. This file defines the boundary and the REPLAY
 * backend: an OGBPAW1 sidecar, parsed by the existing strict parser
 * (gbp_awindump_parse), served one window at a time. It is how the decoder is
 * exercised with no hardware and no emulator (Issue #81).
 *
 * The replay backend reads a buffer the caller owns; it allocates nothing and
 * copies no block.
 */
#ifndef OPENGBP_GBP_ASRC_H
#define OPENGBP_GBP_ASRC_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* One source of blocks: returns 1 and a pointer to the next 4096-byte block,
 * or 0 when the source is exhausted. */
struct gbp_asrc {
    int (*next)(void *ctx, const uint8_t **block);
    void *ctx;
};

#define GBP_ASRC_MAX_WINDOWS 8u

struct gbp_asrc_window {
    uint32_t kind;                /* 0 = control, 1 = press (gbp_awin.h) */
    uint32_t keys;                /* the logical key set that armed it */
    uint32_t blocks;
    const uint8_t *first;         /* the window's first block, inside the caller's buffer */
};

struct gbp_asrc_replay {
    struct gbp_asrc_window win[GBP_ASRC_MAX_WINDOWS];
    uint32_t windows;
    uint32_t cur_win, cur_block;  /* the window being served and the next block in it */
};

/* Parse an OGBPAW1 sidecar in `in` (n bytes, the caller's buffer). 0, or the
 * parser's negative code, or -20 when there are more windows than supported. */
int gbp_asrc_replay_open(struct gbp_asrc_replay *r, const uint8_t *in, size_t n);

/* Serve window `w` from its first block. -1 when w is out of range. */
int gbp_asrc_replay_select(struct gbp_asrc_replay *r, uint32_t w);

/* The source interface over the selected window. */
void gbp_asrc_replay_source(struct gbp_asrc_replay *r, struct gbp_asrc *src);

#ifdef __cplusplus
}
#endif
#endif
