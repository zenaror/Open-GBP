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
 * ring's fill near its target (GBP_APLAY_TARGET by default) with COUNTED DROP / DUPLICATE of whole decoded
 * samples, at most one per chunk (k, spread one per sub-block, since Issue #123:
 * gbp_aplay_set_corrections), applied BETWEEN the ring and the resampler -- never
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
 * THE RUNTIME TARGET AND THE MUTE (GitHub Issue #117, HARDWARE_TESTS §V27). Three
 * primitives the sync POC needs, none of which changes what a default-initialized
 * chain does:
 *   - `target` is the fill the corrections hold, a FIELD defaulting to GBP_APLAY_TARGET
 *     (the macro stays; since #121 it is the cushion in time, see THE CUSHION, IN TIME);
 *     gbp_aplay_set_target() moves it, clamped so a
 *     chunk can always start and the ring can always hold TARGET + BAND. BAND stays a
 *     macro. The decision is still taken once, at the chunk's start, from the fill (with k corrections
 *     a chunk, Issue #123: every decision in the chunk's start frame, its fill and its target).
 *   - `mute`, a count of silence chunks the CALLBACK hands next, whatever the READY
 *     queue holds: a mute hand-off leaves rq untouched, counts neither a silence nor an
 *     underrun, counts `mute_handed`, and logs -2 (a plain silence logs -1). It is one
 *     32-bit store from the pump (gbp_aplay_mute) and one load-and-decrement in the
 *     callback; no lock, nothing else shared. Its duration is exact: `chunks` x 31.25 ms
 *     from the next hand-off, which is what a "fixed-duration mute, never an underrun"
 *     needs (§V27.11). gbp_aplay_process treats -2 like -1 for freeing (no buffer) and
 *     leaves it OUT of L2's record: a mute is not a playback event L2 was written for,
 *     and §V27 never arms L2.
 *   - gbp_aplay_discard_chunk() takes a chunk gbp_aplay_produce() just completed and
 *     returns its buffer to the pool WITHOUT queueing it, counted in `discarded_chunks`:
 *     production keeps consuming the ring at its normal rate while the output is muted.
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
/* THE CUSHION, IN TIME (GitHub Issue #121, 2026-09-25). The fill the corrections hold, and the fill playback starts
 * at, is a latency: every decoded sample of it is 1/GBP_ADEC_RATE s of audio played after the picture it belongs to.
 * ADOPTED: 0.125 s. It was 0.5 s -- 2048 samples -- in every build before #121; each executed image reproduces at its
 * own commit (HARDWARE_TESTS §V23.9), so none is retuned, and sync-0001, which pins its own levels (2048 / 512 / 384
 * in gbp_async.c), keeps them.
 * THE EVIDENCE (HARDWARE_TESTS §V27.20.7, §V27.20.13; GBP-HW-343). RUN 43 ran 0.125 s as an ARM, interleaved with
 * 0.5 s inside one session on a real cartridge. NO INCREASE IN AUDIO LOSS WAS DETECTED AT 0.125 s, AND A LOWER LOSS IS
 * NOT ESTABLISHED. The primary statistic is the exact permutation of the 12 dwells, one-sided p 0.068; the percentile
 * interval, 0.798-0.977, is descriptive and anti-conservative by a measured 15.75 % against 10 %
 * (tests/host/test_v27derive.py, TheIntervalsCoverage). No underrun and no overflow in 71 s, which puts the underrun
 * rate below 3/71 = 0.042 per second at 95 % only (rule of three). It REDUCES the audio-behind-video offset and does
 * not remove it: the chain still holds this cushion, the READY queue, the DMA chunk and the FIR (U-GBP-046 stays
 * open). Nothing shallower is adopted: 0.09375 s was only visited in Phase 2's exploration, and the correction's
 * floor is unmeasured (U-GBP-045).
 * The value is set in TIME: the sample count is recomputed from GBP_ADEC_RATE, which #118 may still change, and never
 * renegotiated. It must come out a whole number of samples within the clamp's bounds (asserted in gbp_aplay.c). */
#define GBP_APLAY_CUSHION_US    125000u  /* ADOPTED 2026-09-25, GitHub Issue #121; 500 000 before */
#define GBP_APLAY_TARGET        ((uint32_t)(((uint64_t)GBP_ADEC_RATE * GBP_APLAY_CUSHION_US) / 1000000u))  /* 512 */
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
 * NOT A FIX for the whole problem: the residue stands (U-GBP-045).
 * RESTATED 2026-09-24 (GitHub Issue #116), a comment only: the figures above integrate over RUN 40's 10 s L2 test
 * window, whose cost fell mostly on the 8-push arm. Outside it the ratio is 0.270 (90 % CI 0.235-0.308) and the
 * residue 0.198 gaps/cycle (GBP-HW-339): the gain is larger than argued, and the residue stands. */
#define GBP_APLAY_STEP_PUSHES      8u
#define GBP_APLAY_LOG            256u    /* the hand-off log, a power of two */
#define GBP_APLAY_L2_CHUNKS      320u    /* produced chunks in the L2 window: 320 000 frames, 10 s */
/* Issue #123, knowingly unchanged: KEEP_CAP is sized for one DROP a chunk. With k corrections a chunk
 * (gbp_aplay_set_corrections) a surplus held above one DROP a chunk over the whole window, or more than
 * EVENTS_CAP corrections in it, marks the L2 record overflowed (take(), l2_event(): the record is then
 * incomplete, and says so). An image that arms L2 with k > 1 sizes both for PUSHES + k and its k. */
#define GBP_APLAY_KEEP_CAP     (GBP_APLAY_L2_CHUNKS * (GBP_APLAY_PUSHES + 1u))
#define GBP_APLAY_EVENTS_CAP    1024u

#define GBP_APLAY_EV_DUP     1u
#define GBP_APLAY_EV_DROP    2u
#define GBP_APLAY_EV_SILENCE 3u

/* what the hand-off log holds besides a buffer index (Issue #117 added the mute) */
#define GBP_APLAY_HL_SILENCE (-1)
#define GBP_APLAY_HL_MUTE    (-2)

/* the bounds gbp_aplay_set_target() clamps to: a chunk must be able to start (PUSHES + 1
 * samples, one more for a DROP) and the ring must hold TARGET + BAND without overflowing. Issue #123:
 * k corrections a chunk need no more -- their decisions stop DROPping at the band's upper edge, so a
 * chunk started at PUSHES + 1 always finishes (gbp_aplay.c, the chunk-start gate) */
#define GBP_APLAY_TARGET_MIN (GBP_APLAY_PUSHES)      /* §V27.11's floor of 128 is realisable literally */
#define GBP_APLAY_TARGET_MAX (GBP_APLAY_RING - GBP_APLAY_BAND - 1u)

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
    uint32_t cur_corr;                         /* 0, DUP or DROP pending for this chunk's current sub-block */
    uint8_t  cur_corr_done;
    /* Issue #123: corrections per chunk. 1 after init, every build before #123: one DUP or DROP a chunk,
     * decided at its start (#92's image choice, §V22.10; §V22.4 decides that corrections are COUNTED
     * events, not how many). k > 1, a divisor of GBP_APLAY_PUSHES no larger than half of it, set by
     * gbp_aplay_set_corrections() and read once at a chunk's start, SPREADS them: k equal sub-blocks of
     * PUSHES / k pushes, at most one decision in each, at its first push when a corrected call makes it
     * (else the sub-block is forgone). Every decision is in the chunk's start frame: the chunk-start level
     * less the chunk's own net corrections so far (cur_s0 + cur_pushes - cur_taken) against the
     * chunk-start target. So a chunk corrects at most as far as the band's edge, samples arriving during
     * production are not counted as surplus, and a set_target or discard mid-chunk acts from the next
     * chunk. Before playback (playing == 0) a chunk takes at most one. A chunk started uncorrected (a
     * transition's) never corrects, and no sub-block of any chunk is decided in an uncorrected call: a
     * decision against a transition's new level would put a spurious sample into the held content
     * (gbp_atrans.c). */
    uint32_t corr_per_chunk;
    uint32_t cur_k;                            /* corr_per_chunk as this chunk started with it */
    uint32_t cur_s0;                           /* the ring's count at this chunk's start */
    uint32_t cur_target;                       /* p->target at this chunk's start */
    uint32_t cur_sub;                          /* the first sub-block not yet decided or passed */
    uint32_t cur_taken;                        /* samples this chunk has taken from the ring */
    uint8_t  cur_uncorrected;                  /* the chunk was started by an uncorrected call */
    uint32_t cur_step;                         /* this chunk's pushes per call, chosen at its start */
    /* Issue #105 (Run B, HARDWARE_TESTS §V24): each chunk's step size, asked once at the chunk's
     * start with its production sequence number. NULL -- every build but Run B's -- means every
     * chunk takes GBP_APLAY_STEP_PUSHES (8 since Issue #109, 16 before; an executed image reproduces
     * at its own commit). Only the partition of the pushes into calls changes: the
     * same samples, the same arithmetic, the same DUP/DROP decision (taken at the chunk's start). */
    uint32_t (*step_pushes)(void *user, uint32_t seq);
    void    *step_pushes_user;
    /* Issue #117 (§V27): the fill the corrections hold. GBP_APLAY_TARGET after init; moved
     * only by gbp_aplay_set_target(), from the pump slot. Read once per chunk, at its start (latched
     * there for every decision of the chunk since Issue #123). */
    uint32_t target;
    /* READY queue, producer -> callback */
    volatile uint8_t  rq[GBP_APLAY_POOL];
    volatile uint32_t rq_head, rq_tail;        /* head: the callback's, tail: the producer's */
    /* hand-off log, callback -> producer: a buffer index, GBP_APLAY_HL_SILENCE or GBP_APLAY_HL_MUTE */
    volatile int8_t   hl[GBP_APLAY_LOG];
    volatile uint32_t hl_head, hl_tail;        /* head: the producer's, tail: the callback's */
    int      last_handed[2];                   /* the two most recent hand-offs, main side */
    /* Issue #117: the mute. `mute` is the number of silence chunks the callback still hands
     * before it takes the READY queue again: written whole by gbp_aplay_mute() (pump), read
     * and decremented by the callback, one 32-bit access each way. `mute_handed` counts them. */
    volatile uint32_t mute;
    volatile uint32_t mute_handed;
    /* what happened, never silent */
    uint32_t produced, dup, drop, starved_steps, log_overflow;
    uint32_t ring_gated;                       /* Issue #117: steps that WANTED a chunk and found the ring under 129 */
    uint32_t discarded_chunks;                 /* Issue #117: completed chunks returned unqueued */
    uint32_t dropped_front;                    /* Issue #117: READY chunks freed unplayed from the front */
    /* Issue #124: the sub-blocks of chunks STARTED corrected that were never decided -- an uncorrected call made their
     * first push, so their correction is forgone (gbp_aplay_set_corrections). 0 at k = 1 by construction: the one
     * sub-block is decided by the call that starts the chunk. What would bring back a persistence rule, counted. */
    uint32_t corr_forgone;
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

/* Issue #117. Producer side, all three.
 * set_target: the fill the next chunks' DUP/DROP decision holds, clamped to
 *   [GBP_APLAY_TARGET_MIN, GBP_APLAY_TARGET_MAX]. The chunk being produced keeps its decision -- all
 *   of them, with k corrections a chunk (Issue #123).
 * mute: the callback hands `chunks` chunks of silence next (0 cancels), see THE RUNTIME TARGET
 *   AND THE MUTE. A store, nothing else.
 * discard_chunk: a chunk gbp_aplay_produce() just returned, NOT to be queued: its buffer is FREE
 *   again and `discarded_chunks` counts it. 1 when discarded; 0 when `buf` is not a completed,
 *   unqueued chunk (out of range, still filling, READY, HANDED or already FREE), and nothing changes. */
void gbp_aplay_set_target(struct gbp_aplay *p, uint32_t target);
/* Issue #123: up to k corrections a chunk, at most one per sub-block of GBP_APLAY_PUSHES / k pushes.
 * k must divide GBP_APLAY_PUSHES and be at most half of it (a DUP is two pushes). It takes effect
 * from the next chunk that starts, and only while playing. 0 on success, -1 (and nothing changed) for
 * any other k. The default, 1, is every earlier build's. */
int gbp_aplay_set_corrections(struct gbp_aplay *p, uint32_t k);
void gbp_aplay_mute(struct gbp_aplay *p, uint32_t chunks);
int  gbp_aplay_discard_chunk(struct gbp_aplay *p, int buf);
/* produce_discard: gbp_aplay_produce() with the READY-queue limit IGNORED (the queue is HELD full
 * during a mute) and the completed chunk returned unqueued through gbp_aplay_discard_chunk(): the
 * ring is consumed at production's normal rate while the callback hands silence. A chunk it STARTS
 * takes no correction: it is never played, so it takes exactly 128 samples and counts no DUP or DROP
 * (a correction there would change the discard's size and pollute the counters). Returns the
 * discarded buffer's index, or -1 when nothing completed (ring short, pool full, or a chunk still
 * in progress -- the same chunk continues on the next call, whichever producer makes it).
 * PRECONDITION for both discards: never while L2 keeps (the kept stream would hold a chunk that
 * is never handed); §V27's image never arms L2. */
int  gbp_aplay_produce_discard(struct gbp_aplay *p, struct gbp_adec *d);

/* produce_uncorrected: produce_discard's production (the READY-queue limit ignored, no correction:
 * exactly 128 samples) but the completed chunk is RETURNED, not freed -- the caller flushes and queues
 * it. The latency round's rotation (Issue #117, §V27.15): under silence a fresh chunk joins the back
 * of the held queue while gbp_aplay_drop_front() frees its front. */
int  gbp_aplay_produce_uncorrected(struct gbp_aplay *p, struct gbp_adec *d);

/* drop_front: free the READY queue's front chunk unplayed (its content is skipped) and return its
 * index, or -1 when the queue is empty or the callback's next hand-off is NOT silent (mute == 0):
 * rq_head is the callback's and is touched here only while its next hand-off leaves it alone. */
int  gbp_aplay_drop_front(struct gbp_aplay *p);

/* Process what the callback handed: the L2 CRC and silence record, and freeing. */
void gbp_aplay_process(struct gbp_aplay *p);

/* Arm L2: the next chunk boundary starts keeping. */
void gbp_aplay_arm_l2(struct gbp_aplay *p);

/* The callback's side. Returns the bytes to hand to AUDIO_InitDMA. `t` is its instant.
 * While `mute` > 0 it hands silence, decrements it and counts `mute_handed` -- the queue,
 * `silences` and `underruns` untouched; M and `handed` still count the callback. */
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
