/*
 * gbp_aplay2 — Round B's drift-correction and hand-off layer at the native rate (GitHub Issue #126,
 * ported into the runtime path by Issue #127): gbp_adec2's ring -> counted clock correction ->
 * gbp_aresamp2 -> the AI chunk pool and READY queue, exactly as gbp_aplay.[ch] does for the frozen
 * 4096 Hz path. A NEW PATH, NOT A MOVED DEFAULT: the frozen path is untouched.
 *
 * Issue #126 built this module NARROWER on purpose (no pool, no queue, no L2, no mute -- an output
 * RING only, sufficient for a host-only decode+resample+drift validation) and said so explicitly:
 * "When that later Issue opens, THIS is the layer to fold the pool/queue/L2/mute machinery back
 * onto, the same way gbp_aplay.c already has it." This is that Issue. The correction/sub-block
 * decision logic (produce_impl's gate, per-sub-block decision, corr_forgone accounting) is
 * unchanged from #126 -- ONLY the destination changes: chunk-formatted AI DMA bytes in a caller
 * pool, handed off through a READY queue, instead of a bare int16 ring.
 *
 * THE CHUNK: 2048 input pushes (128 x 16, GBP-HW-349's k = rate / 4096) resample to EXACTLY 1000
 * output frames (2048 x 125 / 256 = 1000) -- IDENTICAL chunk duration to the frozen path's own 1000
 * frames at 32 000 Hz (31.25 ms). GBP_APLAY2_CHUNK_BYTES, _POOL, _LOG and _L2_CHUNKS therefore carry
 * over from gbp_aplay.h UNCHANGED: the real-time window they describe (a chunk's duration, an L2
 * window's 10 s) does not depend on the INPUT decode rate, only on the OUTPUT frame rate, which is
 * the same 32 000 Hz on both paths. GBP_APLAY2_KEEP_CAP and _EVENTS_CAP are scaled instead, for
 * K_DEFAULT = 16 corrections a chunk against the frozen path's 1 (gbp_aplay.h's own rule: "an image
 * that arms L2 with k > 1 sizes both for PUSHES + k and its k"), keeping the SAME headroom ratio
 * (EVENTS_CAP / (L2_CHUNKS x k)) the frozen path's own sizing has.
 *
 * GBP_APLAY2_AHEAD = 1 is THE QUESTION ISSUE #127 MEASURES, not an established value: GBP-HW-350
 * modelled (INFERENCE, never measured) a mono/16-tap AHEAD-1 margin around 21.0 ms in the worst
 * case, against the frozen path's AHEAD = 4 (117.9 ms of buffering, established by its own §V27
 * validation ladder). This module ships with AHEAD 1 so the ported chain can be driven and measured
 * directly (host replay, Dolphin), per #127's own text ("is AHEAD 1 safe? ... measure it").
 *
 * GBP_APLAY2_STEP_PUSHES = 128 preserves the frozen path's PER-CALL TIME GRANULARITY, not its raw
 * push count: 8 pushes at 4096 Hz is 1.953 ms of decode time a call; 128 pushes at 65536 Hz is the
 * same 1.953 ms. PROVISIONAL, exactly as gbp_aplay.h's own 8 was until RUN 40 measured it (#109):
 * no hardware run exists for this path (#127's own scope is host/Dolphin only), so this is the best
 * host-derived starting point, not a result.
 *
 * No floating point, no allocation, no blocking call, no device.
 */
#ifndef OPENGBP_GBP_APLAY2_H
#define OPENGBP_GBP_APLAY2_H

#include <stddef.h>
#include <stdint.h>

#include "gbp_adec2.h"
#include "gbp_aresamp2.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_APLAY2_FRAMES        1000u    /* per chunk, output domain (32 000 Hz); identical to gbp_aplay.h's */
#define GBP_APLAY2_PUSHES        2048u    /* per chunk, input domain: 128 x 16 (GBP-HW-349) */
#define GBP_APLAY2_K_DEFAULT       16u    /* k = rate / 4096 = 65536 / 4096 (GBP-HW-349), this path's default */
#define GBP_APLAY2_CUSHION_US   125000u   /* the same adopted cushion, in time (gbp_aplay.h, GBP-HW-343); PROVISIONAL
                                            * on this path until re-validated by a hardware run (#126, still open) */
#define GBP_APLAY2_TARGET       ((uint32_t)(((uint64_t)GBP_ADEC2_RATE * GBP_APLAY2_CUSHION_US) / 1000000u))  /* 8192 */
#define GBP_APLAY2_BAND           256u    /* 16 x gbp_aplay's BAND: the same 3.906 ms width, at the new rate */
#define GBP_APLAY2_RING         65536u    /* the input decoder's (gbp_adec2) ring: caller-sized, passed to
                                            * gbp_adec2_init, not to gbp_aplay2_init (which has no ring of its own
                                            * any more -- #127 replaced it with the pool below) */
#define GBP_APLAY2_TARGET_MIN   GBP_APLAY2_PUSHES        /* a chunk must be able to start */
#define GBP_APLAY2_TARGET_MAX   (GBP_APLAY2_RING - GBP_APLAY2_BAND - 1u)

#define GBP_APLAY2_EV_DUP     1u
#define GBP_APLAY2_EV_DROP    2u
#define GBP_APLAY2_EV_SILENCE 3u

/* ---- ported unchanged from gbp_aplay.h (the output chunk/pool/queue/L2/mute layer) ------------- */
#define GBP_APLAY2_CHUNK_BYTES  4000u    /* 125 AI DMA units of 32; SAME as gbp_aplay.h's (identical chunk duration) */
#define GBP_APLAY2_POOL           16u
#define GBP_APLAY2_AHEAD           1u    /* READY chunks kept ahead of the DMA -- THE QUESTION #127 MEASURES, see
                                          * the header comment; not yet an established safe value */
#define GBP_APLAY2_STEP_PUSHES   128u    /* one pump call's pushes: 1.953 ms, matching gbp_aplay's 8-push/4096 Hz
                                          * granularity exactly (see the header comment); PROVISIONAL */
#define GBP_APLAY2_LOG           256u    /* the hand-off log, a power of two; SAME as gbp_aplay.h's */
#define GBP_APLAY2_L2_CHUNKS     320u    /* produced chunks in the L2 window: 320 000 frames, 10 s; SAME real-time
                                          * window as gbp_aplay.h's (chunk duration is identical on both paths) */
/* scaled for K_DEFAULT corrections a chunk (gbp_aplay.h's own rule for k > 1: "sizes both for PUSHES + k and its
 * k"), keeping the frozen path's own headroom ratio (EVENTS_CAP / (L2_CHUNKS x k) = 1024 / (320 x 1) = 3.2). */
#define GBP_APLAY2_KEEP_CAP     (GBP_APLAY2_L2_CHUNKS * (GBP_APLAY2_PUSHES + GBP_APLAY2_K_DEFAULT))
#define GBP_APLAY2_EVENTS_CAP   16384u    /* 320 x 16 x 3.2, the same headroom ratio as gbp_aplay.h's 1024 */

/* what the hand-off log holds besides a buffer index (gbp_aplay.h's own convention) */
#define GBP_APLAY2_HL_SILENCE (-1)
#define GBP_APLAY2_HL_MUTE    (-2)

enum gbp_aplay2_buf { GBP_APLAY2_FREE = 0, GBP_APLAY2_FILLING, GBP_APLAY2_READY, GBP_APLAY2_HANDED };

struct gbp_aplay2_event { uint32_t kind, index; };

struct gbp_aplay2_l2 {
    uint8_t  armed, keeping, handing, done, overflowed;
    uint32_t first_seq;                        /* production sequence number of the first kept chunk */
    uint32_t kept_chunks;                      /* produced while keeping */
    uint32_t window_chunks;                    /* handed inside the window, silence included */
    uint32_t silence_chunks;
    int16_t  hist[16];                         /* GBP_ARESAMP2_TAPS taps, same width as the frozen path's */
    uint32_t hpos, acc;
    uint32_t n_keep, n_events;
    uint32_t crc;                              /* running CRC-32 state (pre-final) */
};

struct gbp_aplay2 {
    struct gbp_aresamp2 rs;
    uint8_t *pool;                             /* GBP_APLAY2_POOL x GBP_APLAY2_CHUNK_BYTES, caller storage */
    const uint8_t *silence;                    /* one chunk of zeros, caller storage */
    uint8_t  state[GBP_APLAY2_POOL];
    uint32_t seq[GBP_APLAY2_POOL];              /* production sequence number of what the buffer holds */
    /* the chunk being produced */
    int32_t  cur;                               /* buffer index, or -1 */
    uint32_t cur_frames, cur_pushes;
    uint32_t cur_corr;                          /* 0, DUP or DROP pending for this chunk's current sub-block */
    uint8_t  cur_corr_done;
    uint32_t corr_per_chunk;                    /* k, read once at each chunk's start */
    uint32_t cur_k;                             /* corr_per_chunk as this chunk started with it */
    uint32_t cur_s0;                            /* the ring's count at this chunk's start */
    uint32_t cur_target;                        /* p->target at this chunk's start */
    uint32_t cur_sub;                           /* the first sub-block not yet decided or passed */
    uint32_t cur_taken;                         /* samples this chunk has taken from the ring */
    uint8_t  cur_uncorrected;                   /* the chunk was started by an uncorrected call */
    uint32_t cur_step;                          /* this chunk's pushes per call, chosen at its start */
    /* mirrors gbp_aplay.h's Run B step_pushes hook: NULL means every chunk takes
     * GBP_APLAY2_STEP_PUSHES. Only the partition of the pushes into calls changes. */
    uint32_t (*step_pushes)(void *user, uint32_t seq);
    void    *step_pushes_user;
    uint32_t target;                            /* the fill the corrections hold; GBP_APLAY2_TARGET after init */
    uint8_t  playing;                           /* before playback a chunk takes at most one correction */
    /* READY queue, producer -> callback */
    volatile uint8_t  rq[GBP_APLAY2_POOL];
    volatile uint32_t rq_head, rq_tail;         /* head: the callback's, tail: the producer's */
    /* hand-off log, callback -> producer: a buffer index, GBP_APLAY2_HL_SILENCE or GBP_APLAY2_HL_MUTE */
    volatile int8_t   hl[GBP_APLAY2_LOG];
    volatile uint32_t hl_head, hl_tail;         /* head: the producer's, tail: the callback's */
    int32_t  last_handed[2];                    /* the two most recent hand-offs, main side */
    /* the mute: `mute` is the number of silence chunks the callback still hands before it takes the
     * READY queue again: written whole by gbp_aplay2_mute() (pump), read and decremented by the
     * callback, one 32-bit access each way. `mute_handed` counts them. */
    volatile uint32_t mute;
    volatile uint32_t mute_handed;
    /* what happened, never silent */
    uint32_t produced, dup, drop, starved_steps, log_overflow;
    uint32_t ring_gated;                        /* steps that WANTED a chunk and found the ring under target+1 */
    uint32_t discarded_chunks;                  /* completed chunks returned unqueued */
    uint32_t dropped_front;                     /* READY chunks freed unplayed from the front */
    uint32_t corr_forgone;                      /* Issue #124's counter, ported unchanged (GBP-HW-349) */
    uint32_t out_overflow;                      /* kept for compatibility with #126's own counter name; always 0
                                                  * on this path (the pool is fixed-size, never overflows a chunk:
                                                  * cur_frames caps at GBP_APLAY2_FRAMES by construction) */
    volatile uint32_t handed, underruns, silences;
    /* M: the callback's instants */
    volatile uint8_t  measuring;
    volatile uint32_t cb_count;
    volatile uint64_t cb_t_first, cb_t_last;
    /* L2 */
    struct gbp_aplay2_l2 l2;
    int16_t *keep;                              /* GBP_APLAY2_KEEP_CAP samples, caller storage */
    struct gbp_aplay2_event *events;            /* GBP_APLAY2_EVENTS_CAP, caller storage */
};

void gbp_aplay2_init(struct gbp_aplay2 *p, uint8_t *pool, const uint8_t *silence, int16_t *keep,
                     struct gbp_aplay2_event *events);

/* k must divide GBP_APLAY2_PUSHES and be at most half of it (a DUP is two pushes). 0 on success,
 * -1 (nothing changed) otherwise. Takes effect from the next chunk that starts. */
int gbp_aplay2_set_corrections(struct gbp_aplay2 *p, uint32_t k);

/* Clamped to [GBP_APLAY2_TARGET_MIN, GBP_APLAY2_TARGET_MAX]. A chunk being produced keeps its
 * already-latched decision. */
void gbp_aplay2_set_target(struct gbp_aplay2 *p, uint32_t target);

/* Producer side (the pump slot). One bounded step: at most the chunk's step size in pushes
 * (GBP_APLAY2_STEP_PUSHES unless p->step_pushes says otherwise).
 * Returns the index of a chunk it has just COMPLETED (flush it, then gbp_aplay2_queue it), or -1.
 * It does nothing while the ring holds too few samples to finish a chunk. */
int gbp_aplay2_produce(struct gbp_aplay2 *p, struct gbp_adec2 *d);
int gbp_aplay2_produce_ex(struct gbp_aplay2 *p, struct gbp_adec2 *d, int uncorrected);
void gbp_aplay2_queue(struct gbp_aplay2 *p, int buf);
uint32_t gbp_aplay2_ready(const struct gbp_aplay2 *p);

void gbp_aplay2_mute(struct gbp_aplay2 *p, uint32_t chunks);
int  gbp_aplay2_discard_chunk(struct gbp_aplay2 *p, int buf);

/* produce_discard: gbp_aplay2_produce() with the READY-queue limit IGNORED (the queue is HELD full
 * during a mute) and the completed chunk returned unqueued through gbp_aplay2_discard_chunk(). A
 * chunk it STARTS takes no correction: it is never played. */
int  gbp_aplay2_produce_discard(struct gbp_aplay2 *p, struct gbp_adec2 *d);

/* produce_uncorrected: produce_discard's production (the READY-queue limit ignored, no correction:
 * exactly GBP_APLAY2_PUSHES samples) but the completed chunk is RETURNED, not freed. */
int  gbp_aplay2_produce_uncorrected(struct gbp_aplay2 *p, struct gbp_adec2 *d);

/* drop_front: free the READY queue's front chunk unplayed, or -1 when the queue is empty or the
 * callback's next hand-off is NOT silent (mute == 0). */
int  gbp_aplay2_drop_front(struct gbp_aplay2 *p);

/* Process what the callback handed: the L2 CRC and silence record, and freeing. */
void gbp_aplay2_process(struct gbp_aplay2 *p);

/* Arm L2: the next chunk boundary starts keeping. */
void gbp_aplay2_arm_l2(struct gbp_aplay2 *p);

/* The callback's side. Returns the bytes to hand to AUDIO_InitDMA. `t` is its instant. */
const uint8_t *gbp_aplay2_irq_handoff(struct gbp_aplay2 *p, uint64_t t);

/* The OGBPL2S1 sidecar (tools/v22accept.py's frozen format, the SAME layout gbp_aplay.c's sidecar
 * writes -- only the field values, at this path's own rate/constants, differ). */
size_t gbp_aplay2_sidecar_size(const struct gbp_aplay2 *p);
size_t gbp_aplay2_sidecar(const struct gbp_aplay2 *p, uint8_t *out, size_t cap);

/* CRC-32 (IEEE, zlib's), table-driven: the running state and its final value. */
uint32_t gbp_aplay2_crc_update(uint32_t state, const uint8_t *data, size_t n);

#ifdef __cplusplus
}
#endif
#endif
