/*
 * tests/host/harness_v126.c -- GitHub Issue #126: decode one archived window through BOTH the
 * frozen 4096 Hz path (gbp_adec.c + gbp_aresamp.c, untouched) and Round B's native path
 * (gbp_adec2.c + gbp_aplay2.c + gbp_aresamp2.c), both calibrated on window 0, both resampled to
 * 32 000 Hz -- so the two int16 PCM streams this writes are directly comparable, on the SAME
 * bytes, with tools/v124taps.py's own band_power(). Built and run by tests/host/test_v126_chain.py
 * via tests/host/hostcc.py; not part of any image.
 *
 * chain_uncorrected (review round, #126) decodes ONLY the native path, with the drift corrector
 * disabled (gbp_aplay2_produce_ex's `uncorrected` flag) -- the decoder and resampler tested
 * without the separate, already-settled (#123) drift-correction algorithm's cold-start behavior.
 *
 * Issue #127 ported gbp_aplay2 onto the real pool/queue/hand-off layer (no more bare output ring):
 * this harness now drains every completed chunk itself -- queue, one simulated hand-off
 * (gbp_aplay2_irq_handoff), the hand-off's big-endian L/R-duplicated bytes decoded back to plain
 * int16 PCM (L == R always, in this format), then process() -- exactly what a real callback site
 * would do, immediately after each chunk (GBP_APLAY2_AHEAD == 1 on this path: a corrected produce()
 * refuses to start a second chunk while one is still queued, so draining cannot be deferred).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_adec.h"
#include "gbp_aresamp.h"
#include "gbp_adec2.h"
#include "gbp_aplay2.h"
#include "gbp_asrc.h"

static void put16(FILE *f, int16_t s)
{
    uint16_t v = (uint16_t)s;
    fputc((int)(v & 0xFFu), f); fputc((int)(v >> 8), f);
}
static uint8_t *slurp(const char *p, size_t *n)
{
    FILE *f = fopen(p, "rb"); long sz; uint8_t *b;
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); sz = ftell(f); fseek(f, 0, SEEK_SET);
    b = (uint8_t *)malloc((size_t)sz ? (size_t)sz : 1u);
    if (fread(b, 1, (size_t)sz, f) != (size_t)sz) { fclose(f); free(b); return NULL; }
    fclose(f); *n = (size_t)sz; return b;
}

static int16_t ring1[16];
static int16_t ring2[GBP_APLAY2_RING];
static uint8_t pool2[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence2[GBP_APLAY2_CHUNK_BYTES];
static int16_t keep2[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events2[GBP_APLAY2_EVENTS_CAP];

/* Make every bit of progress this block's new data allows: gbp_aplay2_produce() advances at most
 * GBP_APLAY2_STEP_PUSHES (128) pushes a CALL, matching a real pump call's own bounded step (a real
 * system calls it far more often than once a block; this harness must too, or a chunk starves on
 * step granularity alone despite the ring holding plenty). -1 does not mean "stop": it also covers a
 * chunk mid-progress that needs another call. Stops only once NOTHING can happen this block: no
 * chunk in progress (cur < 0) and too few samples to start one -- the exact condition
 * gbp_aplay2_produce_ex() itself would count as starved, so this harness never inflates that
 * counter by polling past it. On every completed chunk: queue it, hand it off (one simulated
 * callback), write its PCM to `o2` (big-endian L channel, L == R always here) and process(). */
static void drain_step(struct gbp_aplay2 *p2, struct gbp_adec2 *d2, int uncorrected, uint32_t *y2n, FILE *o2)
{
    for (;;) {
        int b;
        if (p2->cur < 0 && d2->count < GBP_APLAY2_PUSHES + 1u) return;   /* genuinely nothing to do */
        b = gbp_aplay2_produce_ex(p2, d2, uncorrected);
        if (b < 0) {
            /* a corrected call can also be gated by AHEAD (not "starved"): stop for this block */
            if (p2->cur < 0) return;
            continue;                                     /* mid-chunk: call again */
        }
        {
            const uint8_t *bytes;
            uint32_t k;
            gbp_aplay2_queue(p2, b);
            bytes = gbp_aplay2_irq_handoff(p2, 0u);
            for (k = 0; k < GBP_APLAY2_FRAMES; k++) {
                const int16_t v = (int16_t)((uint16_t)((uint32_t)bytes[4u * k] << 8) | bytes[4u * k + 1u]);
                put16(o2, v);
                (*y2n)++;
            }
            gbp_aplay2_process(p2);
        }
    }
}

/* chain <sidecar> <window> <out1.s16le> <out2.s16le> <counters.txt>: calibrate BOTH decoders on
 * window 0, decode window `window` through each full chain, write both 32000 Hz PCM streams and a
 * counters report Python can parse (one "key=value" line, space-separated). */
static int chain(const char *in, uint32_t window, const char *out1p, const char *out2p, const char *ctrp)
{
    struct gbp_asrc_replay r;
    struct gbp_asrc src;
    const uint8_t *blk;
    size_t n;
    uint8_t *buf;
    FILE *o1, *o2, *ct;
    int rc;
    uint32_t blocks = 0u, y1n = 0u, y2n = 0u;

    struct gbp_adec d1;
    struct gbp_aresamp rs1;
    struct gbp_adec2 d2;
    struct gbp_aplay2 p2;

    buf = slurp(in, &n);
    if (!buf) return 2;
    rc = gbp_asrc_replay_open(&r, buf, n);
    if (rc != 0) { fprintf(stderr, "open %d\n", rc); return 3; }
    if (window >= r.windows) { fprintf(stderr, "window %u out of range (%u)\n", window, r.windows); return 4; }

    gbp_adec_init(&d1, ring1, 16u);
    gbp_aresamp_init(&rs1);
    gbp_adec2_init(&d2, ring2, GBP_APLAY2_RING);
    gbp_aplay2_init(&p2, pool2, silence2, keep2, events2);
    p2.playing = 1;

    gbp_asrc_replay_select(&r, 0u);
    gbp_asrc_replay_source(&r, &src);
    while (src.next(src.ctx, &blk)) {
        gbp_adec_calibrate(&d1, blk);
        gbp_adec2_calibrate(&d2, blk);
    }

    o1 = fopen(out1p, "wb");
    o2 = fopen(out2p, "wb");
    if (!o1 || !o2) return 7;

    gbp_asrc_replay_select(&r, window);
    gbp_asrc_replay_source(&r, &src);
    while (src.next(src.ctx, &blk)) {
        int16_t s1;
        if (gbp_adec_push_block(&d1, blk) != 0) { fprintf(stderr, "gbp_adec ring overflow\n"); return 5; }
        if (gbp_adec2_push_block(&d2, blk) != 16u) { fprintf(stderr, "gbp_adec2 ring overflow\n"); return 6; }
        blocks++;
        while (gbp_adec_pop(&d1, &s1)) {
            int16_t y[GBP_ARESAMP_MAX_OUT];
            uint32_t k, kn = gbp_aresamp_push(&rs1, s1, y);
            for (k = 0; k < kn; k++) { put16(o1, y[k]); y1n++; }
        }
        /* the new path resamples inside gbp_aplay2_produce, one call (GBP_APLAY2_STEP_PUSHES pushes,
         * or a chunk's remainder) at a time; drain every chunk it completes at once (AHEAD == 1) */
        drain_step(&p2, &d2, 0, &y2n, o2);
    }
    fclose(o1);
    fclose(o2);

    ct = fopen(ctrp, "w");
    if (!ct) return 8;
    fprintf(ct, "blocks=%u y1n=%u y2n=%u produced2=%u dup2=%u drop2=%u forgone2=%u starved2=%u "
                "overflow1=%u clipped1=%u overflow2=%u clipped2=%u lost1=%u lost2=%u taken1=%u leftover2=%u\n",
            blocks, y1n, y2n, p2.produced, p2.dup, p2.drop, p2.corr_forgone, p2.starved_steps,
            d1.overflow, d1.clipped, d2.overflow, d2.clipped, d1.lost, d2.lost, d1.blocks_in, d2.count);
    fclose(ct);
    free(buf);
    return 0;
}

/* chain_uncorrected <sidecar> <window> <skip> <out2.s16le> <counters.txt>: gbp_adec2 + gbp_aresamp2
 * + gbp_aplay2, calibrated on window 0 like chain(), decoding window `window` -- but every chunk is
 * produced with gbp_aplay2_produce_ex's own `uncorrected` flag (1), the mechanism gbp_aplay.c's
 * transition chunks already use: no DUP, no DROP, exactly GBP_APLAY2_PUSHES pushes a chunk. This
 * isolates the DECODER + RESAMPLER from the DRIFT CORRECTOR (review round, #126): a short,
 * two-chunk test window's cold-start DUPs (the ring far below target) stretch the tone and phase-
 * jump it, which a per-harmonic measurement at the tone's OWN frequency cannot tell apart from a
 * real high-frequency loss. Counters include dup2/drop2, which this path must hold at exactly 0.
 * `skip` discards the window's first `skip` blocks before decoding starts -- tools/v11sweep.py's
 * ONSET_SLICE_BLOCKS (=96), a FIXED onset a press window's AGB has not yet reacted within, §V11.9,
 * the same rule GBP-HW-340 applies; never chosen from this measurement's own output. */
static int chain_uncorrected(const char *in, uint32_t window, uint32_t skip, const char *out2p, const char *ctrp)
{
    struct gbp_asrc_replay r;
    struct gbp_asrc src;
    const uint8_t *blk;
    size_t n;
    uint8_t *buf;
    FILE *o2, *ct;
    int rc;
    uint32_t blocks = 0u, skipped = 0u, y2n = 0u;

    struct gbp_adec2 d2;
    struct gbp_aplay2 p2;

    buf = slurp(in, &n);
    if (!buf) return 2;
    rc = gbp_asrc_replay_open(&r, buf, n);
    if (rc != 0) { fprintf(stderr, "open %d\n", rc); return 3; }
    if (window >= r.windows) { fprintf(stderr, "window %u out of range (%u)\n", window, r.windows); return 4; }

    gbp_adec2_init(&d2, ring2, GBP_APLAY2_RING);
    gbp_aplay2_init(&p2, pool2, silence2, keep2, events2);
    p2.playing = 1;

    gbp_asrc_replay_select(&r, 0u);
    gbp_asrc_replay_source(&r, &src);
    while (src.next(src.ctx, &blk)) gbp_adec2_calibrate(&d2, blk);

    o2 = fopen(out2p, "wb");
    if (!o2) return 7;

    gbp_asrc_replay_select(&r, window);
    gbp_asrc_replay_source(&r, &src);
    while (src.next(src.ctx, &blk)) {
        if (skipped < skip) { skipped++; continue; }
        if (gbp_adec2_push_block(&d2, blk) != 16u) { fprintf(stderr, "gbp_adec2 ring overflow\n"); return 6; }
        blocks++;
        /* uncorrected: bypasses the AHEAD gate entirely (produce_impl2's uncorrected branch), so no
         * draining is required between chunks here -- but this harness still drains every chunk to
         * read its PCM out, exactly as chain() does. */
        drain_step(&p2, &d2, 1, &y2n, o2);
    }
    fclose(o2);

    ct = fopen(ctrp, "w");
    if (!ct) return 8;
    fprintf(ct, "blocks=%u y2n=%u produced2=%u dup2=%u drop2=%u forgone2=%u starved2=%u "
                "overflow2=%u clipped2=%u lost2=%u leftover2=%u\n",
            blocks, y2n, p2.produced, p2.dup, p2.drop, p2.corr_forgone, p2.starved_steps,
            d2.overflow, d2.clipped, d2.lost, d2.count);
    fclose(ct);
    free(buf);
    return 0;
}

/* chain_raw <blocks.bin> <n> <out1.s16le> <out2.s16le> <counters.txt>: `blocks.bin` is N
 * consecutive 4096-byte blocks, no sidecar wrapper (a Python-extracted gap-free run, e.g. RUN 43's
 * game window, which carries no separate silent control span). SELF-CALIBRATED: both decoders'
 * rest is the MEAN of the very blocks being decoded, since no other reference exists here -- a
 * methodological choice this round makes explicitly, not a frozen one. */
static int chain_raw(const char *in, uint32_t nblocks, const char *out1p, const char *out2p, const char *ctrp)
{
    size_t n;
    uint8_t *buf = slurp(in, &n);
    FILE *o1, *o2, *ct;
    uint32_t i, y1n = 0u, y2n = 0u;

    struct gbp_adec d1;
    struct gbp_aresamp rs1;
    struct gbp_adec2 d2;
    struct gbp_aplay2 p2;

    if (!buf) return 2;
    if (n != (size_t)nblocks * GBP_ADEC2_BLOCK_BYTES) { fprintf(stderr, "size mismatch\n"); return 3; }

    gbp_adec_init(&d1, ring1, 16u);
    gbp_aresamp_init(&rs1);
    gbp_adec2_init(&d2, ring2, GBP_APLAY2_RING);
    gbp_aplay2_init(&p2, pool2, silence2, keep2, events2);
    p2.playing = 1;

    for (i = 0; i < nblocks; i++) {
        gbp_adec_calibrate(&d1, buf + (size_t)i * GBP_ADEC2_BLOCK_BYTES);
        gbp_adec2_calibrate(&d2, buf + (size_t)i * GBP_ADEC2_BLOCK_BYTES);
    }

    o1 = fopen(out1p, "wb");
    o2 = fopen(out2p, "wb");
    if (!o1 || !o2) return 7;
    for (i = 0; i < nblocks; i++) {
        const uint8_t *blk = buf + (size_t)i * GBP_ADEC2_BLOCK_BYTES;
        int16_t s1;
        if (gbp_adec_push_block(&d1, blk) != 0) { fprintf(stderr, "gbp_adec ring overflow\n"); return 5; }
        if (gbp_adec2_push_block(&d2, blk) != 16u) { fprintf(stderr, "gbp_adec2 ring overflow\n"); return 6; }
        while (gbp_adec_pop(&d1, &s1)) {
            int16_t y[GBP_ARESAMP_MAX_OUT];
            uint32_t k, kn = gbp_aresamp_push(&rs1, s1, y);
            for (k = 0; k < kn; k++) { put16(o1, y[k]); y1n++; }
        }
        drain_step(&p2, &d2, 0, &y2n, o2);
    }
    fclose(o1);
    fclose(o2);

    ct = fopen(ctrp, "w");
    if (!ct) return 8;
    fprintf(ct, "blocks=%u y1n=%u y2n=%u produced2=%u dup2=%u drop2=%u forgone2=%u starved2=%u "
                "overflow1=%u clipped1=%u overflow2=%u clipped2=%u lost1=%u lost2=%u taken1=%u leftover2=%u\n",
            nblocks, y1n, y2n, p2.produced, p2.dup, p2.drop, p2.corr_forgone, p2.starved_steps,
            d1.overflow, d1.clipped, d2.overflow, d2.clipped, d1.lost, d2.lost, d1.blocks_in, d2.count);
    fclose(ct);
    free(buf);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 7 && strcmp(argv[1], "chain") == 0)
        return chain(argv[2], (uint32_t)strtoul(argv[3], NULL, 10), argv[4], argv[5], argv[6]);
    if (argc == 7 && strcmp(argv[1], "chain_raw") == 0)
        return chain_raw(argv[2], (uint32_t)strtoul(argv[3], NULL, 10), argv[4], argv[5], argv[6]);
    if (argc == 7 && strcmp(argv[1], "chain_uncorrected") == 0)
        return chain_uncorrected(argv[2], (uint32_t)strtoul(argv[3], NULL, 10),
                                  (uint32_t)strtoul(argv[4], NULL, 10), argv[5], argv[6]);
    return 1;
}
