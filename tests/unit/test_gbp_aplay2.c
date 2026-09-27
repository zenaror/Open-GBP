/*
 * tests/unit/test_gbp_aplay2.c — GitHub Issue #126, Round B: the drift-correction layer at
 * 65 536 Hz, k = 16 fixed for this round (GBP-HW-349). The chunk/sub-block decision logic is
 * gbp_aplay.c's, ported (Issue #123's three review rounds settled it there); what is checked
 * here is that the port holds at the new PUSHES/BAND/k and that its OWN new properties hold: a
 * chunk always resamples to exactly 1000 output frames regardless of correction activity, the
 * resampler's accumulator is back at 0 at every chunk boundary, and the conservation and
 * reproducibility invariants Issue #126 asks for.
 *
 * ISSUE #127 replaced the output RING #126 built (host-only, no image, no pool) with the SAME
 * pool/queue/L2/mute layer gbp_aplay.c has: gbp_aplay2_produce() now returns a completed BUFFER
 * INDEX (or -1), which the caller flushes and queues, exactly as gbp_aplay_produce() does. Tests
 * below read the completed chunk's bytes from `p.pool` directly (public, caller storage) instead
 * of popping a ring, and queue every completed chunk so the pool does not run out of FREE buffers
 * (GBP_APLAY2_POOL = 16) over a test's chunk count.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_aplay2.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

static void check(int cond, const char *what)
{
    checks++;
    if (!cond) {
        failures++;
        printf("  FAIL: %s\n", what);
    }
}

static uint8_t pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event events[GBP_APLAY2_EVENTS_CAP];
static int16_t decoder_ring[GBP_APLAY2_RING];

/* fill the decoder's ring with decoded samples directly, as gbp_adec2_push_block would --
 * tests/unit/test_gbp_aplay.c's own pattern, generalised. */
static void give(struct gbp_adec2 *d, uint32_t n, int16_t v)
{
    uint32_t k;
    for (k = 0; k < n && d->count < d->cap; k++) {
        d->ring[(d->head + d->count) % d->cap] = v;
        d->count++;
    }
}

static void reset(struct gbp_aplay2 *p, struct gbp_adec2 *d)
{
    gbp_aplay2_init(p, pool, silence, keep, events);
    gbp_adec2_init(d, decoder_ring, GBP_APLAY2_RING);
    p->playing = 1;
}

/* one chunk in as few calls as this test wants: `step` overrides GBP_APLAY2_STEP_PUSHES via the
 * Issue #105-style hook, 0 meaning "the default (128)". Queues every completed chunk (the real
 * caller's job) so the pool never runs dry over a test's chunk count. */
static uint32_t forced_step;
static uint32_t force_step_pushes(void *user, uint32_t seq)
{
    (void)user; (void)seq;
    return forced_step;
}

static int last_driven_buf = -1;

static int drive(struct gbp_aplay2 *p, struct gbp_adec2 *d, uint32_t step)
{
    uint32_t i;
    int b;
    forced_step = step;
    p->step_pushes = step ? force_step_pushes : NULL;
    for (i = 0; i < GBP_APLAY2_PUSHES + 4u; i++) {
        b = gbp_aplay2_produce(p, d);
        if (b >= 0) { last_driven_buf = b; gbp_aplay2_queue(p, b); return 1; }
    }
    return 0;
}

static void test_defaults(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    eqi((long long)p.corr_per_chunk, GBP_APLAY2_K_DEFAULT, "the default is k = 16 (GBP-HW-349)");
    eqi((long long)p.target, GBP_APLAY2_TARGET, "the default target is the 0.125 s cushion");
    eqi((long long)GBP_APLAY2_TARGET, 8192, "0.125 s at 65 536 Hz is 8192 samples exactly");
    eqi((long long)GBP_APLAY2_PUSHES, 2048, "128 x 16 (GBP-HW-349)");
    eqi((long long)GBP_APLAY2_BAND, 256, "16 x gbp_aplay's BAND, the same time width");
}

static void test_a_chunk_resamples_to_exactly_1000_frames_at_rest(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    int b;
    reset(&p, &d);
    give(&d, GBP_APLAY2_TARGET, 0);                /* fill exactly at target */
    b = drive(&p, &d, 0u);
    eqi(b, 1, "a whole chunk completes");
    eqi((long long)p.produced, 1, "one chunk produced");
    eqi((long long)p.cur_frames, GBP_APLAY2_FRAMES, "exactly 1000 output frames, regardless of corrections");
    eqi((long long)p.rs.acc, 0, "the resampler's accumulator is back at 0 at the chunk boundary");
    eqi((long long)(p.dup + p.drop), 0, "at a fill exactly at target, no correction is due");
}

static void test_the_gate_is_pushes_plus_one(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    give(&d, GBP_APLAY2_PUSHES, 0);                /* one short */
    eqi(gbp_aplay2_produce(&p, &d), -1, "not enough to start a chunk");
    eqi((long long)p.starved_steps, 1, "counted");
    give(&d, 1u, 0);                                /* now exactly the gate */
    eqi(drive(&p, &d, 0u), 1, "starts and finishes");
}

static void test_k_corrections_are_spread_one_per_sub_block(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    /* well under the band, ALL the way (not just past its edge): every sub-block DUPs, mirroring
     * gbp_aplay's own test_k_corrections_are_spread_one_per_sub_block */
    reset(&p, &d);
    give(&d, GBP_APLAY2_TARGET - GBP_APLAY2_BAND - 300u, 0);
    eqi(drive(&p, &d, 0u), 1, "the chunk still finishes");
    eqi((long long)p.dup, GBP_APLAY2_K_DEFAULT, "sixteen DUPs, one per sub-block");
    eqi((long long)p.drop, 0, "no DROPs");
    eqi((long long)p.corr_forgone, 0, "every sub-block was decided");
    eqi((long long)p.cur_taken, GBP_APLAY2_PUSHES - GBP_APLAY2_K_DEFAULT,
        "each DUP takes one sample from the ring for two resampler pushes: 2048 - 16");
    eqi((long long)p.chunk_corrections, GBP_APLAY2_K_DEFAULT,
        "review round (#127, §V28): this chunk's own dup+drop count, the per-chunk rate a session-length "
        "log samples instead of one L2 event a correction");
}

/* review round (#127, §V28): chunk_corrections is a PER-CHUNK delta, not a running total -- it must reset to
 * what THIS chunk alone did, not accumulate across chunks. */
static void test_chunk_corrections_is_a_per_chunk_delta(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    /* first chunk: far under the band, every sub-block DUPs */
    give(&d, GBP_APLAY2_TARGET - GBP_APLAY2_BAND - 300u, 0);
    eqi(drive(&p, &d, 0u), 1, "first chunk finishes");
    eqi((long long)p.chunk_corrections, GBP_APLAY2_K_DEFAULT, "first chunk: sixteen corrections");
    (void)gbp_aplay2_irq_handoff(&p, 1000u);   /* AHEAD == 1: drain so a second chunk can start */
    gbp_aplay2_process(&p);
    /* second chunk: topped up to exactly the gate (cur_s0 == PUSHES + 1, inside the band around TARGET is not
     * required -- the band check is against cur_target, and TARGET_MIN == PUSHES, so feeding to land near
     * TARGET keeps this chunk's own fill inside the band regardless of the ring's leftover from the first */
    eqi(GBP_APLAY2_TARGET > d.count, 1, "sanity: the first chunk did not overshoot the target on its own");
    give(&d, GBP_APLAY2_TARGET - d.count, 0);   /* top up to exactly TARGET: inside the band, no correction due */
    eqi(drive(&p, &d, 0u), 1, "second chunk finishes");
    eqi((long long)p.chunk_corrections, 0, "second chunk: fed exactly to the target, no correction due");
    eqi((long long)p.dup + (long long)p.drop, (long long)GBP_APLAY2_K_DEFAULT,
        "the running totals still hold only the first chunk's corrections");
}

static void test_corr_forgone_when_a_sub_block_is_passed_uncorrected(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    give(&d, GBP_APLAY2_TARGET - GBP_APLAY2_BAND - 300u, 0);
    /* a first, small-step call still catches sub-block 0's decision (it fires at cur_pushes == 0,
     * the call's very first push): nothing is forgone here, this just exercises multi-call driving */
    forced_step = 300u; p.step_pushes = force_step_pushes;
    eqi(gbp_aplay2_produce(&p, &d), -1, "not finished yet");
    eqi(drive(&p, &d, 0u), 1, "finishes over further calls");
    eqi((long long)p.dup, GBP_APLAY2_K_DEFAULT, "every sub-block still decides eventually in this test");
    eqi((long long)p.corr_forgone, 0, "and none is forgone when every call lands on a sub-block start");
}

static void test_no_correction_below_playback(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    p.playing = 0;                                  /* prefill: at most one correction whatever k is */
    give(&d, GBP_APLAY2_TARGET - GBP_APLAY2_BAND - 300u, 0);
    eqi(drive(&p, &d, 0u), 1, "prefill chunk finishes");
    eqi((long long)(p.dup + p.drop), 1, "at most one correction before playback, not k = 16");
}

static void test_uncorrected_chunk_takes_none(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    uint32_t i;
    int b = -1;
    reset(&p, &d);
    give(&d, GBP_APLAY2_TARGET - GBP_APLAY2_BAND - 300u, 0);    /* would DUP under a corrected call */
    for (i = 0; i < GBP_APLAY2_PUSHES + 4u && b < 0; i++) b = gbp_aplay2_produce_uncorrected(&p, &d);
    check(b >= 0, "an uncorrected (transition) chunk finishes");
    eqi((long long)(p.dup + p.drop), 0, "and takes no correction");
    eqi((long long)p.cur_taken, GBP_APLAY2_PUSHES, "exactly PUSHES samples taken, none extra or forgone");
}

static void test_set_corrections_bounds(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    eqi(gbp_aplay2_set_corrections(&p, 0u), -1, "k = 0 rejected");
    eqi(gbp_aplay2_set_corrections(&p, GBP_APLAY2_PUSHES / 2u + 1u), -1, "k > PUSHES/2 rejected");
    eqi(gbp_aplay2_set_corrections(&p, 100u), -1, "k must divide PUSHES (2048 %% 100 != 0)");
    eqi(gbp_aplay2_set_corrections(&p, 32u), 0, "a legal k is accepted");
    eqi((long long)p.corr_per_chunk, 32, "and takes effect");
}

static void test_set_target_clamps(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    gbp_aplay2_set_target(&p, 0u);
    eqi((long long)p.target, GBP_APLAY2_TARGET_MIN, "clamped to the floor");
    gbp_aplay2_set_target(&p, 999999999u);
    eqi((long long)p.target, GBP_APLAY2_TARGET_MAX, "clamped to the ceiling");
}

/* Conservation: over N chunks, every sample the decoder's ring gave up (cur_taken, summed) equals
 * PUSHES x chunks - dup + drop exactly, and every chunk's output is exactly FRAMES samples.
 * GBP_APLAY2_AHEAD == 1 on this path (#127; under test, see gbp_aplay2.h): a CORRECTED produce()
 * refuses to start a new chunk while READY already holds AHEAD chunks, exactly as gbp_aplay.c's
 * own gate does -- so each chunk here is drained by a simulated hand-off before the next is fed,
 * matching how a real callback would consume it. */
static void test_conservation(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    uint32_t i, chunks = 5u;
    long long fed = 0;
    reset(&p, &d);
    for (i = 0; i < chunks; i++) {
        give(&d, GBP_APLAY2_PUSHES + 1u, (int16_t)((i % 3u) * 100 - 100));   /* a varying, bursty feed */
        fed += GBP_APLAY2_PUSHES + 1u;
        /* drive it in small, uneven steps -- several hand-off phases, not one whole-chunk call */
        eqi(drive(&p, &d, 37u), 1, "each chunk completes over several small-step calls");
        (void)gbp_aplay2_irq_handoff(&p, 1000u + i);   /* drain READY so the next chunk can start */
        gbp_aplay2_process(&p);
    }
    eqi((long long)p.produced, chunks, "every chunk completed under a bursty feed");
    eqi((long long)p.handed, chunks, "every completed chunk was handed off");
    /* fed = consumed (popped) + still in the decoder's ring (delta stock); nothing overflowed or was lost
     * upstream in this test, so d->count is the only "still fed, not yet taken" term */
    eqi(fed - (long long)d.count, (long long)chunks * GBP_APLAY2_PUSHES - (long long)p.dup + (long long)p.drop,
        "fed = taken + delta stock, and taken = chunks x PUSHES - dup + drop (GBP-HW-349's k arithmetic)");
}

/* Issue #127: the pool/queue/L2/mute layer, ported from gbp_aplay.c. */

/* GBP_APLAY2_AHEAD == 1 on this path (#127; under test): a CORRECTED produce() refuses to start a
 * SECOND chunk while READY already holds one, so FIFO order here is checked across a drained
 * queue -- each chunk handed off before the next is produced -- rather than two queued at once. */
static void test_queue_and_handoff_fifo(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    int b0, b1;
    const uint8_t *bytes;
    reset(&p, &d);
    give(&d, 2u * (GBP_APLAY2_PUSHES + 1u), 100);
    eqi(drive(&p, &d, 0u), 1, "first chunk completes");
    eqi((long long)gbp_aplay2_ready(&p), 1, "one chunk READY");
    b0 = (int)p.rq[p.rq_head % GBP_APLAY2_POOL];
    bytes = gbp_aplay2_irq_handoff(&p, 1000u);
    eqi((long long)bytes[0], (long long)pool[(size_t)b0 * GBP_APLAY2_CHUNK_BYTES], "the FRONT chunk is handed first");
    eqi((long long)p.handed, 1, "one hand-off counted");
    eqi((long long)p.underruns, 0, "not an underrun: a real chunk was handed");
    gbp_aplay2_process(&p);
    eqi(drive(&p, &d, 0u), 1, "second chunk completes once the queue drained");
    b1 = (int)p.rq[p.rq_head % GBP_APLAY2_POOL];
    check(b1 != b0, "the second chunk is a different buffer");
}

static void test_underrun_when_ready_is_empty(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    const uint8_t *bytes;
    reset(&p, &d);
    p.playing = 1;
    bytes = gbp_aplay2_irq_handoff(&p, 1000u);
    eqi((long long)p.underruns, 1, "an empty READY queue while playing counts an underrun");
    eqi((long long)p.silences, 1, "and a silence");
    check(bytes == p.silence, "the silence buffer is handed");
}

/* AHEAD == 1 forces one chunk produced, handed and processed at a time; "two hand-offs later" is
 * checked across three such cycles: A's buffer is freed only once a THIRD chunk (C) has been
 * handed, not after B's hand-off alone. */
static void test_process_frees_two_handoffs_later(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    int a, bbuf, c;
    reset(&p, &d);
    give(&d, GBP_APLAY2_PUSHES + 1u, 100);
    eqi(drive(&p, &d, 0u), 1, "chunk A completes");
    a = (int)p.rq[p.rq_head % GBP_APLAY2_POOL];
    (void)gbp_aplay2_irq_handoff(&p, 1000u);         /* A handed */
    gbp_aplay2_process(&p);
    eqi((long long)p.state[a], GBP_APLAY2_HANDED, "A is HANDED, not yet freed");

    give(&d, GBP_APLAY2_PUSHES + 1u, 100);
    eqi(drive(&p, &d, 0u), 1, "chunk B completes");
    bbuf = (int)p.rq[p.rq_head % GBP_APLAY2_POOL];
    (void)gbp_aplay2_irq_handoff(&p, 1001u);         /* B handed */
    gbp_aplay2_process(&p);
    eqi((long long)p.state[a], GBP_APLAY2_HANDED, "A still not freed after B's hand-off alone");
    eqi((long long)p.state[bbuf], GBP_APLAY2_HANDED, "B is HANDED");

    give(&d, GBP_APLAY2_PUSHES + 1u, 100);
    eqi(drive(&p, &d, 0u), 1, "chunk C completes");
    c = (int)p.rq[p.rq_head % GBP_APLAY2_POOL];
    (void)gbp_aplay2_irq_handoff(&p, 1002u);         /* C handed: A is now two hand-offs behind */
    gbp_aplay2_process(&p);
    eqi((long long)p.state[a], GBP_APLAY2_FREE, "A freed once C (two hand-offs later) is handed");
    eqi((long long)p.state[bbuf], GBP_APLAY2_HANDED, "B still HANDED (only one hand-off later)");
    eqi((long long)p.state[c], GBP_APLAY2_HANDED, "C is HANDED");
}

static void test_mute_hands_silence_and_leaves_ready_untouched(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    uint32_t ready0;
    reset(&p, &d);
    give(&d, GBP_APLAY2_PUSHES + 1u, 100);
    eqi(drive(&p, &d, 0u), 1, "one chunk queued");
    ready0 = gbp_aplay2_ready(&p);
    gbp_aplay2_mute(&p, 2u);
    (void)gbp_aplay2_irq_handoff(&p, 1000u);
    eqi((long long)gbp_aplay2_ready(&p), (long long)ready0, "a mute hand-off leaves READY untouched");
    eqi((long long)p.mute_handed, 1, "counted as mute_handed, not a silence or an underrun");
    eqi((long long)p.silences, 0, "not a silence");
    eqi((long long)p.underruns, 0, "not an underrun");
}

static void test_discard_chunk_frees_without_queueing(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    int b;
    reset(&p, &d);
    give(&d, GBP_APLAY2_PUSHES + 1u, 100);
    forced_step = 0u; p.step_pushes = NULL;
    do { b = gbp_aplay2_produce(&p, &d); } while (b < 0);
    eqi(gbp_aplay2_discard_chunk(&p, b), 1, "a just-completed chunk can be discarded");
    eqi((long long)p.state[b], GBP_APLAY2_FREE, "its buffer is free again");
    eqi((long long)gbp_aplay2_ready(&p), 0, "and never queued");
    eqi((long long)p.discarded_chunks, 1, "counted");
}

static void test_arm_l2_keeps_and_hands_off_a_window(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    uint32_t i;
    reset(&p, &d);
    gbp_aplay2_arm_l2(&p);
    eqi((long long)p.l2.armed, 1, "armed");
    for (i = 0; i < 2u; i++) {
        give(&d, GBP_APLAY2_PUSHES + 1u, 100);
        eqi(drive(&p, &d, 0u), 1, "chunk completes");
        (void)gbp_aplay2_irq_handoff(&p, 1000u + i);   /* AHEAD == 1: drain before the next chunk */
        gbp_aplay2_process(&p);
    }
    eqi((long long)p.l2.keeping, 1, "arming took effect at the first chunk boundary and is still keeping");
    eqi((long long)p.l2.kept_chunks, 2, "two chunks kept so far");
    check(p.l2.n_keep > 0u, "samples were kept");
    eqi((long long)p.l2.handing, 1, "the hand-off window opened at the first kept chunk's hand-off");
    check(p.l2.window_chunks > 0u, "the window is counting handed chunks");
}

/* A deliberately undersized output ring is no longer applicable (#127 replaced the ring with a
 * fixed-size pool: a chunk's bytes are written into its own GBP_APLAY2_CHUNK_BYTES buffer, which
 * cannot overflow by construction -- cur_frames stops at GBP_APLAY2_FRAMES exactly, the loop's own
 * gate). out_overflow is kept as a permanently-zero counter for API stability; this test pins that. */
static void test_out_overflow_stays_zero_on_this_path(void)
{
    struct gbp_aplay2 p;
    struct gbp_adec2 d;
    reset(&p, &d);
    give(&d, GBP_APLAY2_PUSHES + 1u, 100);
    eqi(drive(&p, &d, 0u), 1, "a chunk completes normally");
    eqi((long long)p.out_overflow, 0, "the pool never overflows a chunk buffer");
}

/* Reproducibility: the same feed sequence, replayed on a fresh state, gives an identical trace. */
static void test_reproducibility(void)
{
    struct gbp_aplay2 p1, p2;
    struct gbp_adec2 d1, d2;
    static uint8_t pool2[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
    static uint8_t silence2[GBP_APLAY2_CHUNK_BYTES];
    static int16_t keep2[GBP_APLAY2_KEEP_CAP];
    static struct gbp_aplay2_event events2[GBP_APLAY2_EVENTS_CAP];
    static int16_t decoder_ring2[GBP_APLAY2_RING];
    static uint8_t snap1[4u * GBP_APLAY2_CHUNK_BYTES], snap2[4u * GBP_APLAY2_CHUNK_BYTES];
    uint32_t i;
    gbp_aplay2_init(&p1, pool, silence, keep, events);
    gbp_adec2_init(&d1, decoder_ring, GBP_APLAY2_RING);
    p1.playing = 1;
    gbp_aplay2_init(&p2, pool2, silence2, keep2, events2);
    gbp_adec2_init(&d2, decoder_ring2, GBP_APLAY2_RING);
    p2.playing = 1;
    for (i = 0; i < 4u; i++) {
        give(&d1, GBP_APLAY2_PUSHES + 1u, (int16_t)(i * 37 - 60));
        give(&d2, GBP_APLAY2_PUSHES + 1u, (int16_t)(i * 37 - 60));
        drive(&p1, &d1, 61u);
        memcpy(&snap1[i * GBP_APLAY2_CHUNK_BYTES], pool + (size_t)last_driven_buf * GBP_APLAY2_CHUNK_BYTES,
               GBP_APLAY2_CHUNK_BYTES);
        drive(&p2, &d2, 61u);
        memcpy(&snap2[i * GBP_APLAY2_CHUNK_BYTES], pool2 + (size_t)last_driven_buf * GBP_APLAY2_CHUNK_BYTES,
               GBP_APLAY2_CHUNK_BYTES);
        /* GBP_APLAY2_AHEAD == 1: drain the queue so the next chunk can start, identically on both --
         * and only AFTER the snapshot above, since draining is what frees a buffer for reuse */
        (void)gbp_aplay2_irq_handoff(&p1, 1000u + i); gbp_aplay2_process(&p1);
        (void)gbp_aplay2_irq_handoff(&p2, 1000u + i); gbp_aplay2_process(&p2);
    }
    eqi((long long)p1.produced, (long long)p2.produced, "same chunk count");
    eqi((long long)p1.dup, (long long)p2.dup, "same DUPs");
    eqi((long long)p1.drop, (long long)p2.drop, "same DROPs");
    eqi((long long)p1.corr_forgone, (long long)p2.corr_forgone, "same forgone count");
    eqi((long long)gbp_aplay2_ready(&p1), (long long)gbp_aplay2_ready(&p2), "same queue depth");
    eqi(memcmp(snap1, snap2, 4u * GBP_APLAY2_CHUNK_BYTES) == 0, 1, "the same output bytes, chunk for chunk");
}

int main(void)
{
    test_defaults();
    test_a_chunk_resamples_to_exactly_1000_frames_at_rest();
    test_the_gate_is_pushes_plus_one();
    test_k_corrections_are_spread_one_per_sub_block();
    test_chunk_corrections_is_a_per_chunk_delta();
    test_corr_forgone_when_a_sub_block_is_passed_uncorrected();
    test_no_correction_below_playback();
    test_uncorrected_chunk_takes_none();
    test_set_corrections_bounds();
    test_set_target_clamps();
    test_conservation();
    test_queue_and_handoff_fifo();
    test_underrun_when_ready_is_empty();
    test_process_frees_two_handoffs_later();
    test_mute_hands_silence_and_leaves_ready_untouched();
    test_discard_chunk_frees_without_queueing();
    test_arm_l2_keeps_and_hands_off_a_window();
    test_out_overflow_stays_zero_on_this_path();
    test_reproducibility();
    fprintf(stderr, "%d checks, %d failures\n", checks, failures);
    return failures != 0;
}
