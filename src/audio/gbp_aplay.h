/*
 * gbp_aplay — Phase 6's playback chain: decoded ring -> counted clock correction ->
 * gbp_aresamp -> AI chunks, and everything QUESTION L2, C and MEASUREMENT M read
 * (GitHub Issue #92; HARDWARE_TESTS §V22.2-§V22.5, §V22.8 (p)(u), §V22.9 A1/A2).
 *
 * THE RING is src/audio/gbp_adec's own output ring, holding DECODED int16 samples,
 * one per AUDIO block (§V22.0). It is sized at 4096 (1 s, 8 KiB) because the cost is
 * nothing. That size DEFERS an underrun from the clock drift -- about 1 108 s against
 * a 200-block ring's 54 s at the drift §V22.4 predicts -- and it DOES NOT FIX drift.
 * What fixes drift is the correction below. Nobody should read the size as the
 * solution.
 *
 * THE CLOCKS (§V22.4, the decision made before the run). The drain delivers ~4096
 * samples per GameCube second; the AI consumes 32 000 x 16/125 of them per ITS
 * second, and its second is not proven to be the timebase's. The chain keeps the
 * ring's fill near GBP_APLAY_TARGET with COUNTED DROP / DUPLICATE of whole decoded
 * samples, at most one per chunk, applied BETWEEN the ring and the resampler -- never
 * a ratio servo, which would break 125/16 and L2 with it. Every correction is one
 * discrete event at a recorded index. L (gbp_alive) reads the samples BEFORE this.
 * The band is +-16 samples, NARROW ON PURPOSE: the drift moves the fill by only
 * ~3.7 samples a second, so a +-256 band would first be crossed ~69 s in -- after
 * C's whole window -- and the observed correction rate, which §V22.4 FREEZES as the
 * reading of the clock model, would say nothing. Simulated on two clocks
 * (tests/host/test_alive_chain.py): 222 DUPs in 64 s at Dolphin's 32 028.5 Hz, the
 * figure §V22.4 predicts; a handful at 32 000 Hz (the start-up transient only); and
 * DROPs, not DUPs, when the AI is the slower clock.
 *
 * THE CHUNKS. 1000 frames = 128 inputs = 8 whole 16-input phase cycles, so every
 * chunk begins with the resampler's accumulator at 0 (a precondition L2 relies on:
 * the kept state is a chunk boundary). 4000 bytes = 125 AI DMA units of 32. Frames
 * are written as explicit BIG-ENDIAN bytes, L and R the same sample: on the console
 * that is the AI's native layout, and on a host it is the same bytes, so the CRC of
 * what is handed is the same number everywhere.
 *
 * TWO CONTEXTS. The producer (gbp_aplay_produce, gbp_aplay_queue, gbp_aplay_process)
 * runs in the pump slot. The consumer (gbp_aplay_irq_handoff) runs in the AI DMA
 * callback: it takes the oldest READY chunk or, when there is none, hands SILENCE and
 * counts an UNDERRUN; it logs what it handed for the producer. Two single-producer
 * single-consumer queues, volatile indices, nothing shared besides.
 *
 * A HANDED CHUNK IS FREED TWO HAND-OFFS LATER: the callback programs block k while
 * k-1 plays, so k-2 has finished (aout-0002's queue, RUN 36).
 *
 * L2 (§V22.2 with its preconditions). Armed by the POC inside C's window. From the
 * next chunk boundary it KEEPS: the resampler's state (history, position,
 * accumulator), every decoded sample it pops (pre-correction), every DUP / DROP at
 * its kept index, and -- in hand-off order, from the first kept chunk's hand-off to
 * the last one's -- every SILENCE chunk at its window index (§V22.8 (u)) and the
 * CRC-32 of every byte handed. gbp_aplay_sidecar() serializes it as OGBPL2S1,
 * byte for byte the format tools/v22accept.py froze.
 *
 * M (§V22.5). The callback's instants, first and last, and how many, while measuring.
 *
 * No floating point, no allocation, no blocking call, no device.
 */
#ifndef OPENGBP_GBP_APLAY_H
#define OPENGBP_GBP_APLAY_H

#include <stddef.h>
#include <stdint.h>

#include "gbp_adec.h"
#include "gbp_aresamp.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_APLAY_FRAMES        1000u    /* per AI chunk: 128 inputs, acc 0 at every boundary */
#define GBP_APLAY_PUSHES         128u
#define GBP_APLAY_CHUNK_BYTES   4000u    /* 125 x 32 */
#define GBP_APLAY_POOL            16u
#define GBP_APLAY_AHEAD            4u    /* READY chunks kept ahead of the DMA */
#define GBP_APLAY_RING          4096u    /* the decoder's ring: 1 s, 8 KiB (defers, never fixes, drift) */
#define GBP_APLAY_TARGET        2048u    /* the fill the corrections hold, and the fill playback starts at */
#define GBP_APLAY_BAND            16u    /* DUP below TARGET-BAND, DROP above TARGET+BAND (see THE CLOCKS) */
/* One pump call produces at most this many pushes (62.5 frames). 8, ADOPTED by GitHub Issue #109
 * from RUN 40 (HARDWARE_TESTS §V24.10); 16 in every build before it.
 *
 * The argument, from quantities measured in RUN 40:
 *   - the gain: 8-push calls lost 0.341 of the 16-push calls' loss gaps per AI cycle (GBP-HW-332);
 *     the `produce` share was 89 % in both arms, so the losses fall with the stretch's length
 *     (GBP-HW-334), and the half arm's residue overlaps the ordinary calls (228 of 257), not the
 *     chunk's first call (7).
 *   - the cost is NOT the limit: 119.6 ticks per push and 64.0 fixed per call, so even 2-push
 *     calls would add ~4 100 ticks per chunk, 0.3 % of an AI cycle.
 *   - the limit is THROUGHPUT: the pump slot ran at least 110 times per AI cycle (floorless
 *     sample, 254 cycles), and one chunk a cycle needs 128 pushes. 1-push calls (128 a chunk)
 *     cannot keep up; 2 is the smallest that can (1.7x margin); 4 gives 3.4x, 8 gives 6.9x.
 *   - 8 is where the evidence stops. Below it the effect is unmeasured -- a proportional
 *     extrapolation, not a result -- so the runtime takes the measured value, and a Phase 6
 *     run on it runs a configuration whose loss rate is known (the half arm: 0.25 gaps/cycle).
 * NOT A FIX for the whole problem: the residue stands (U-GBP-045). */
#define GBP_APLAY_STEP_PUSHES      8u
#define GBP_APLAY_LOG            256u    /* the hand-off log, a power of two */
#define GBP_APLAY_L2_CHUNKS      320u    /* produced chunks in the L2 window: 320 000 frames, 10 s */
#define GBP_APLAY_KEEP_CAP     (GBP_APLAY_L2_CHUNKS * (GBP_APLAY_PUSHES + 1u))
#define GBP_APLAY_EVENTS_CAP    1024u

#define GBP_APLAY_EV_DUP     1u
#define GBP_APLAY_EV_DROP    2u
#define GBP_APLAY_EV_SILENCE 3u

enum gbp_aplay_buf { GBP_APLAY_FREE = 0, GBP_APLAY_FILLING, GBP_APLAY_READY, GBP_APLAY_HANDED };

struct gbp_aplay_event { uint32_t kind, index; };

struct gbp_aplay_l2 {
    uint8_t  armed, keeping, handing, done, overflowed;
    uint32_t first_seq;                        /* production sequence number of the first kept chunk */
    uint32_t kept_chunks;                      /* produced while keeping */
    uint32_t window_chunks;                    /* handed inside the window, silence included */
    uint32_t silence_chunks;
    int16_t  hist[16];
    uint32_t hpos, acc;
    uint32_t n_keep, n_events;
    uint32_t crc;                              /* running CRC-32 state (pre-final) */
};

struct gbp_aplay {
    struct gbp_aresamp rs;
    uint8_t *pool;                             /* GBP_APLAY_POOL x GBP_APLAY_CHUNK_BYTES, caller storage */
    const uint8_t *silence;                    /* one chunk of zeros, caller storage */
    uint8_t  state[GBP_APLAY_POOL];
    uint32_t seq[GBP_APLAY_POOL];              /* production sequence number of what the buffer holds */
    /* the chunk being produced */
    int      cur;                              /* buffer index, or -1 */
    uint32_t cur_frames, cur_pushes;
    uint32_t cur_corr;                         /* 0, DUP or DROP for this chunk */
    uint8_t  cur_corr_done;
    uint32_t cur_step;                         /* this chunk's pushes per call, chosen at its start */
    /* Issue #105 (Run B, HARDWARE_TESTS §V24): each chunk's step size, asked once at the chunk's
     * start with its production sequence number. NULL -- every build but Run B's -- means every
     * chunk takes GBP_APLAY_STEP_PUSHES (8 since Issue #109, 16 before; an executed image reproduces
     * at its own commit). Only the partition of the pushes into calls changes: the
     * same samples, the same arithmetic, the same DUP/DROP decision (taken at the chunk's start). */
    uint32_t (*step_pushes)(void *user, uint32_t seq);
    void    *step_pushes_user;
    /* READY queue, producer -> callback */
    volatile uint8_t  rq[GBP_APLAY_POOL];
    volatile uint32_t rq_head, rq_tail;        /* head: the callback's, tail: the producer's */
    /* hand-off log, callback -> producer: a buffer index, or -1 for silence */
    volatile int8_t   hl[GBP_APLAY_LOG];
    volatile uint32_t hl_head, hl_tail;        /* head: the producer's, tail: the callback's */
    int      last_handed[2];                   /* the two most recent hand-offs, main side */
    /* what happened, never silent */
    uint32_t produced, dup, drop, starved_steps, log_overflow;
    volatile uint32_t handed, underruns, silences;
    volatile uint8_t  playing;
    /* M */
    volatile uint8_t  measuring;
    volatile uint32_t cb_count;
    volatile uint64_t cb_t_first, cb_t_last;
    /* L2 */
    struct gbp_aplay_l2 l2;
    int16_t *keep;                             /* GBP_APLAY_KEEP_CAP samples, caller storage */
    struct gbp_aplay_event *events;            /* GBP_APLAY_EVENTS_CAP, caller storage */
};

void gbp_aplay_init(struct gbp_aplay *p, uint8_t *pool, const uint8_t *silence, int16_t *keep,
                    struct gbp_aplay_event *events);

/* Producer side (the pump slot). One bounded step: at most the chunk's step size in pushes
 * (GBP_APLAY_STEP_PUSHES unless p->step_pushes says otherwise).
 * Returns the index of a chunk it has just COMPLETED (flush it, then gbp_aplay_queue it),
 * or -1. It does nothing while the ring holds too few samples to finish a chunk. */
int  gbp_aplay_produce(struct gbp_aplay *p, struct gbp_adec *d);
void gbp_aplay_queue(struct gbp_aplay *p, int buf);
uint32_t gbp_aplay_ready(const struct gbp_aplay *p);

/* Process what the callback handed: the L2 CRC and silence record, and freeing. */
void gbp_aplay_process(struct gbp_aplay *p);

/* Arm L2: the next chunk boundary starts keeping. */
void gbp_aplay_arm_l2(struct gbp_aplay *p);

/* The callback's side. Returns the bytes to hand to AUDIO_InitDMA. `t` is its instant. */
const uint8_t *gbp_aplay_irq_handoff(struct gbp_aplay *p, uint64_t t);

/* The OGBPL2S1 sidecar (tools/v22accept.py's frozen format). Size, and the bytes. */
size_t gbp_aplay_sidecar_size(const struct gbp_aplay *p);
size_t gbp_aplay_sidecar(const struct gbp_aplay *p, uint8_t *out, size_t cap);

/* CRC-32 (IEEE, zlib's), table-driven: the running state and its final value. */
uint32_t gbp_aplay_crc_update(uint32_t state, const uint8_t *data, size_t n);

#ifdef __cplusplus
}
#endif
#endif
