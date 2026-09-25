/*
 * tests/unit/test_gbp_aplay.c — Phase 6's playback chain with no device (GitHub
 * Issue #92, §V22.2-§V22.5).
 *
 * The callback is simulated by calling gbp_aplay_irq_handoff() from here, at the
 * cadence a test chooses. What is checked: a chunk is 128 pushes and 1000 frames
 * written big-endian; a correction is at most one per chunk and in the direction
 * the fill asks for; an empty queue hands silence and counts an underrun only while
 * playing; a handed chunk comes back to the pool two hand-offs later; the CRC is
 * zlib's; and L2 keeps exactly what its window consumed.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_aplay.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

static uint8_t pool[GBP_APLAY_POOL * GBP_APLAY_CHUNK_BYTES];
static uint8_t silence[GBP_APLAY_CHUNK_BYTES];
static int16_t keep[GBP_APLAY_KEEP_CAP];
static struct gbp_aplay_event events[GBP_APLAY_EVENTS_CAP];
static int16_t ring[GBP_APLAY_RING];

/* fill the decoder's ring with decoded samples directly, as gbp_adec_push_block would */
static void give(struct gbp_adec *d, uint32_t n, int16_t v)
{
    uint32_t k;
    for (k = 0; k < n && d->count < d->cap; k++) {
        d->ring[(d->head + d->count) % d->cap] = v;
        d->count++;
    }
}

static int produce_all(struct gbp_aplay *p, struct gbp_adec *d)
{
    int k, b = -1;
    for (k = 0; k < 64 && b < 0; k++) b = gbp_aplay_produce(p, d);
    return b;
}

static void test_crc_is_zlibs(void)
{
    static const uint8_t s[] = "123456789";
    eqi((long long)(gbp_aplay_crc_update(0xFFFFFFFFu, s, 9u) ^ 0xFFFFFFFFu), 0xCBF43926ll, "CRC-32 check value");
}

static void test_a_chunk(void)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    int b;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    give(&d, 100u, 1000);
    eqi(gbp_aplay_produce(&p, &d), -1, "too few samples: nothing is started");
    give(&d, GBP_APLAY_TARGET - 100u, 1000);                 /* exactly the target: inside the band */
    b = produce_all(&p, &d);
    eqi(b >= 0, 1, "a chunk completes");
    eqi(p.cur_frames, 1000, "1000 frames");
    eqi(p.rs.acc, 0, "and the accumulator is back at 0");
    eqi(p.dup + p.drop, 0, "inside the band: no correction");
    {
        const uint8_t *c = pool + (size_t)b * GBP_APLAY_CHUNK_BYTES + 4u * 999u;   /* settled: 1000 */
        eqi(c[0], 0x03, "big-endian high byte (1000 = 0x03E8)");
        eqi(c[1], 0xE8, "big-endian low byte");
        eqi(c[2], 0x03, "R is the same sample");
    }
}

static void test_corrections_follow_the_fill(void)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    uint32_t popped;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    give(&d, GBP_APLAY_TARGET - GBP_APLAY_BAND - 10u, 7);    /* under the band: one DUP */
    popped = d.count;
    (void)produce_all(&p, &d);
    popped -= d.count;
    eqi(p.dup, 1, "a DUP under the band");
    eqi(popped, 127, "a DUP chunk pops 127 samples for 128 pushes");
    gbp_aplay_init(&p, pool, silence, keep, events);
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    give(&d, GBP_APLAY_TARGET + GBP_APLAY_BAND + 10u, 7);    /* over it: one DROP */
    popped = d.count;
    (void)produce_all(&p, &d);
    popped -= d.count;
    eqi(p.drop, 1, "a DROP over the band");
    eqi(popped, 129, "a DROP chunk pops 129 samples for 128 pushes");
}

static void test_handoff_underrun_and_freeing(void)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    int b0, b1, i, free_before, free_after;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    eqi(gbp_aplay_irq_handoff(&p, 1u) == silence, 1, "an empty queue hands silence");
    eqi(p.underruns, 0, "not an underrun before playback started");
    p.playing = 1u;
    (void)gbp_aplay_irq_handoff(&p, 2u);
    eqi(p.underruns, 1, "an underrun while playing");
    give(&d, GBP_APLAY_TARGET, 5);
    b0 = produce_all(&p, &d); gbp_aplay_queue(&p, b0);
    b1 = produce_all(&p, &d); gbp_aplay_queue(&p, b1);
    eqi(gbp_aplay_ready(&p), 2, "two READY");
    eqi(gbp_aplay_irq_handoff(&p, 3u) == pool + (size_t)b0 * GBP_APLAY_CHUNK_BYTES, 1, "the OLDEST is handed first");
    gbp_aplay_process(&p);
    eqi(p.state[b0], GBP_APLAY_HANDED, "handed");
    (void)gbp_aplay_irq_handoff(&p, 4u);
    gbp_aplay_process(&p);
    eqi(p.state[b0], GBP_APLAY_HANDED, "still in use while the next one plays");
    free_before = 0;
    for (i = 0; i < (int)GBP_APLAY_POOL; i++) free_before += p.state[i] == GBP_APLAY_FREE;
    (void)gbp_aplay_irq_handoff(&p, 5u);                     /* a third hand-off: b0 has finished */
    gbp_aplay_process(&p);
    eqi(p.state[b0], GBP_APLAY_FREE, "freed two hand-offs later");
    free_after = 0;
    for (i = 0; i < (int)GBP_APLAY_POOL; i++) free_after += p.state[i] == GBP_APLAY_FREE;
    eqi(free_after, free_before + 1, "exactly one buffer came back");
}

static void test_measuring(void)
{
    static struct gbp_aplay p;
    gbp_aplay_init(&p, pool, silence, keep, events);
    (void)gbp_aplay_irq_handoff(&p, 10u);
    eqi(p.cb_count, 0, "not measuring: not counted");
    p.measuring = 1u;
    (void)gbp_aplay_irq_handoff(&p, 20u);
    (void)gbp_aplay_irq_handoff(&p, 30u);
    eqi(p.cb_count, 2, "two callbacks measured");
    eqi((long long)p.cb_t_first, 20, "first"); eqi((long long)p.cb_t_last, 30, "last");
}

static void test_l2_keeps_what_its_window_consumed(void)
{
    static struct gbp_aplay p;
    static uint8_t side[0x48 + 8 * GBP_APLAY_EVENTS_CAP + 2 * GBP_APLAY_KEEP_CAP + 4];
    struct gbp_adec d;
    uint32_t k, handed = 0u;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    p.playing = 1u;
    gbp_aplay_arm_l2(&p);
    /* produce and hand, one to one, with the fill low enough to DUP now and then */
    for (k = 0; k < 400u && !p.l2.done; k++) {
        int b;
        give(&d, 128u, (int16_t)(k & 1u ? 3000 : -3000));
        b = produce_all(&p, &d);
        if (b >= 0) gbp_aplay_queue(&p, b);
        (void)gbp_aplay_irq_handoff(&p, 100u + k);
        if (k == 50u) (void)gbp_aplay_irq_handoff(&p, 100u + k);   /* an empty queue: SILENCE inside the window */
        handed++;
        gbp_aplay_process(&p);
    }
    eqi(p.l2.done, 1, "the L2 window closes");
    eqi(p.l2.kept_chunks, 320, "320 kept chunks");
    eqi(p.l2.window_chunks, 320 + p.l2.silence_chunks, "the window is the kept chunks plus its silence");
    eqi(p.l2.silence_chunks >= 1u, 1, "the silence inside the window is recorded");
    eqi(p.l2.n_keep, 320u * 128u - p.dup + p.drop, "kept = 128 per chunk, less DUPs, plus DROPs");
    eqi(p.l2.acc, 0, "the kept state is a chunk boundary");
    eqi(p.l2.overflowed, 0, "nothing overflowed");
    eqi(gbp_aplay_sidecar(&p, side, sizeof side) == gbp_aplay_sidecar_size(&p), 1, "the sidecar serializes");
    eqi(memcmp(side, "OGBPL2S1", 8) == 0, 1, "its magic");
    (void)handed;
}

/* Issue #105 (Run B, §V24): the step size is the ONLY thing the hook changes. Two producers are fed the
 * same decoded stream, with DUPs and DROPs; one takes the default (16 pushes a call), one takes 8 for
 * every odd chunk. Every chunk must come out byte for byte the same, with the same corrections, and the
 * half-step chunks must take exactly twice as many working calls. */
static uint8_t pool_b[GBP_APLAY_POOL * GBP_APLAY_CHUNK_BYTES];
static int16_t keep_b[GBP_APLAY_KEEP_CAP];
static struct gbp_aplay_event events_b[GBP_APLAY_EVENTS_CAP];
static int16_t ring_b[GBP_APLAY_RING];

static uint32_t half_on_odd(void *user, uint32_t seq)
{
    (void)user;
    return (seq & 1u) ? 8u : 16u;
}

static uint32_t always_16(void *user, uint32_t seq)
{
    (void)user;
    (void)seq;
    return 16u;
}

static void give_wave(struct gbp_adec *d, uint32_t n, uint32_t *phase)
{
    uint32_t k;
    for (k = 0; k < n && d->count < d->cap; k++, (*phase)++) {
        d->ring[(d->head + d->count) % d->cap] = (int16_t)((int32_t)((*phase * 2654435761u) >> 20) - 2048);
        d->count++;
    }
}

static void test_half_steps_change_nothing_but_the_partition(void)
{
    static struct gbp_aplay a, b;
    struct gbp_adec da, db;
    uint32_t pa = 0u, pb = 0u, chunk, calls_a, calls_b, total_a = 0u, total_b = 0u, same = 1u;
    /* fills that walk under, inside and over the band, so DUP, nothing and DROP all occur */
    static const uint32_t fill[] = { GBP_APLAY_TARGET - 40u, GBP_APLAY_TARGET, GBP_APLAY_TARGET + 40u,
                                     GBP_APLAY_TARGET - 30u, GBP_APLAY_TARGET + 30u, GBP_APLAY_TARGET };
    printf("-- Issue #105: half steps change the partition of the pushes and nothing else\n");
    gbp_adec_init(&da, ring, GBP_APLAY_RING);
    gbp_adec_init(&db, ring_b, GBP_APLAY_RING);
    gbp_aplay_init(&a, pool, silence, keep, events);
    gbp_aplay_init(&b, pool_b, silence, keep_b, events_b);
    eqi(a.step_pushes == 0, 1, "the hook is NULL after init: every build without one takes the default");
    a.step_pushes = always_16;                   /* the pre-#109 size, explicitly */
    b.step_pushes = half_on_odd;
    for (chunk = 0; chunk < 12u; chunk++) {
        int ra = -1, rb = -1;
        const uint32_t want = fill[chunk % 6u];
        if (da.count < want) give_wave(&da, want - da.count, &pa);
        if (db.count < want) give_wave(&db, want - db.count, &pb);
        calls_a = calls_b = 0u;
        while (ra < 0) { ra = gbp_aplay_produce(&a, &da); calls_a++; }
        while (rb < 0) { rb = gbp_aplay_produce(&b, &db); calls_b++; }
        total_a += calls_a;
        total_b += calls_b;
        if (memcmp(pool + (size_t)ra * GBP_APLAY_CHUNK_BYTES, pool_b + (size_t)rb * GBP_APLAY_CHUNK_BYTES,
                   GBP_APLAY_CHUNK_BYTES) != 0)
            same = 0u;
        eqi(calls_b, (chunk & 1u) ? 2u * calls_a : calls_a, "a half-step chunk takes exactly twice the calls");
        eqi(b.cur_step, (chunk & 1u) ? 8u : 16u, "the chunk's step size is the one the hook gave");
        gbp_aplay_queue(&a, ra);
        gbp_aplay_queue(&b, rb);
        (void)gbp_aplay_irq_handoff(&a, 0u);
        (void)gbp_aplay_irq_handoff(&b, 0u);
        gbp_aplay_process(&a);
        gbp_aplay_process(&b);
    }
    eqi(same, 1u, "every chunk is byte for byte the same");
    eqi(a.dup, b.dup, "the same DUPs");
    eqi(a.drop, b.drop, "the same DROPs");
    eqi(a.dup > 0u && a.drop > 0u, 1, "and both corrections occurred");
    eqi(a.produced, b.produced, "the same chunks");
    eqi(total_b, total_a + total_a / 2u, "six of twelve chunks at half steps: 1.5 x the calls");
}

/* Issue #109: the ADOPTED default is 8 pushes a call. With no hook, every chunk takes 8-push calls -- exactly
 * sixteen working calls -- and comes out byte for byte the same as 16-push production, with the same
 * corrections: the runtime change moves the partition and nothing else. */
static void test_the_adopted_default_is_8_and_changes_only_the_partition(void)
{
    static struct gbp_aplay a, b;
    struct gbp_adec da, db;
    uint32_t pa = 0u, pb = 0u, chunk, calls_a, calls_b, same = 1u;
    static const uint32_t fill[] = { GBP_APLAY_TARGET - 40u, GBP_APLAY_TARGET, GBP_APLAY_TARGET + 40u };
    printf("-- Issue #109: the adopted default, 8 pushes a call, changes the partition and nothing else\n");
    eqi(GBP_APLAY_STEP_PUSHES, 8, "the adopted default");
    gbp_adec_init(&da, ring, GBP_APLAY_RING);
    gbp_adec_init(&db, ring_b, GBP_APLAY_RING);
    gbp_aplay_init(&a, pool, silence, keep, events);
    gbp_aplay_init(&b, pool_b, silence, keep_b, events_b);
    a.step_pushes = always_16;                   /* b: no hook, the default */
    for (chunk = 0; chunk < 9u; chunk++) {
        int ra = -1, rb = -1;
        const uint32_t want = fill[chunk % 3u];
        if (da.count < want) give_wave(&da, want - da.count, &pa);
        if (db.count < want) give_wave(&db, want - db.count, &pb);
        calls_a = calls_b = 0u;
        while (ra < 0) { ra = gbp_aplay_produce(&a, &da); calls_a++; }
        while (rb < 0) { rb = gbp_aplay_produce(&b, &db); calls_b++; }
        if (memcmp(pool + (size_t)ra * GBP_APLAY_CHUNK_BYTES, pool_b + (size_t)rb * GBP_APLAY_CHUNK_BYTES,
                   GBP_APLAY_CHUNK_BYTES) != 0)
            same = 0u;
        eqi(calls_b, 2u * calls_a, "twice the calls of 16-push production");
        eqi(b.cur_step, 8u, "no hook: the chunk takes the default");
        gbp_aplay_queue(&a, ra);
        gbp_aplay_queue(&b, rb);
        (void)gbp_aplay_irq_handoff(&a, 0u);
        (void)gbp_aplay_irq_handoff(&b, 0u);
        gbp_aplay_process(&a);
        gbp_aplay_process(&b);
    }
    eqi(same, 1u, "every chunk is byte for byte the same");
    eqi(a.dup == b.dup && a.drop == b.drop && a.produced == b.produced, 1, "the same corrections and chunks");
    eqi(a.dup > 0u && a.drop > 0u, 1, "and both corrections occurred");
}

/* Issue #117 (§V27): the runtime target, the mute and the discard. The two-producer harnesses
 * above already prove that a default-initialized chain produces byte for byte what it did. */
static int count_free(const struct gbp_aplay *p)
{
    int i, n = 0;
    for (i = 0; i < (int)GBP_APLAY_POOL; i++) n += p->state[i] == GBP_APLAY_FREE;
    return n;
}

static void test_fresh_init_defaults(void)
{
    static struct gbp_aplay p;
    printf("-- Issue #117: the runtime target, the mute and the discard\n");
    gbp_aplay_init(&p, pool, silence, keep, events);
    eqi(p.target, GBP_APLAY_TARGET, "a fresh init holds the macro's target");
    eqi(p.mute, 0, "no mute");
    eqi(p.mute_handed, 0, "no mute handed");
    eqi(p.discarded_chunks, 0, "nothing discarded");
    eqi(GBP_APLAY_TARGET_MIN, 128, "the clamp's floor: §V27.11's 128 is realisable literally");
    eqi(GBP_APLAY_TARGET_MAX, 4079, "the clamp's ceiling: the ring holds TARGET + BAND");
}

static void test_set_target_moves_the_decision(void)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    /* 480 -> DUP, 540 -> DROP, 512 -> nothing, each from a fresh chain at target 512 */
    static const struct { uint32_t fill, dup, drop; } cases[] = { { 480u, 1u, 0u }, { 540u, 0u, 1u }, { 512u, 0u, 0u } };
    uint32_t k;
    for (k = 0; k < 3u; k++) {
        gbp_adec_init(&d, ring, GBP_APLAY_RING);
        gbp_aplay_init(&p, pool, silence, keep, events);
        gbp_aplay_set_target(&p, 512u);
        eqi(p.target, 512, "the target is 512");
        give(&d, cases[k].fill, 7);
        eqi(produce_all(&p, &d) >= 0, 1, "a chunk completes");
        eqi(p.dup, cases[k].dup, "DUP follows 512 - BAND");
        eqi(p.drop, cases[k].drop, "DROP follows 512 + BAND");
    }
    /* the same fills at the default target are all DUPs: the field is what the decision reads */
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    give(&d, 540u, 7);
    eqi(produce_all(&p, &d) >= 0, 1, "a chunk completes at the default");
    eqi(p.dup, 1, "540 is far under 2048: a DUP");
    /* the clamp */
    gbp_aplay_set_target(&p, 0u);
    eqi(p.target, GBP_APLAY_TARGET_MIN, "0 clamps to the floor");
    gbp_aplay_set_target(&p, GBP_APLAY_TARGET_MIN - 1u);
    eqi(p.target, GBP_APLAY_TARGET_MIN, "127 clamps to the floor");
    gbp_aplay_set_target(&p, GBP_APLAY_TARGET_MIN);
    eqi(p.target, GBP_APLAY_TARGET_MIN, "128 stands");
    gbp_aplay_set_target(&p, 0xFFFFFFFFu);
    eqi(p.target, GBP_APLAY_TARGET_MAX, "huge clamps to the ceiling");
    gbp_aplay_set_target(&p, GBP_APLAY_TARGET_MAX + 1u);
    eqi(p.target, GBP_APLAY_TARGET_MAX, "4080 clamps to the ceiling");
    gbp_aplay_set_target(&p, GBP_APLAY_TARGET_MAX);
    eqi(p.target, GBP_APLAY_TARGET_MAX, "4079 stands");
    gbp_aplay_set_target(&p, 3584u);
    eqi(p.target, 3584, "3584 stands");
    /* the floor still produces: a chunk starts at 129 samples and the decision is inside the band */
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    gbp_aplay_set_target(&p, GBP_APLAY_TARGET_MIN);
    give(&d, GBP_APLAY_TARGET_MIN + 1u, 7);
    eqi(produce_all(&p, &d) >= 0, 1, "a chunk completes at the floor");
    eqi(p.dup + p.drop, 0, "inside the band at the floor");
}

static void test_mute_hands_silence_and_touches_nothing_else(void)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    int b[3], k, free_before;
    uint32_t head_before, tail_before;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    give(&d, GBP_APLAY_TARGET, 5);
    for (k = 0; k < 3; k++) { b[k] = produce_all(&p, &d); gbp_aplay_queue(&p, b[k]); }
    eqi(gbp_aplay_ready(&p), 3, "three READY");
    p.playing = 1u;
    p.measuring = 1u;
    head_before = p.rq_head; tail_before = p.rq_tail;
    free_before = count_free(&p);
    gbp_aplay_mute(&p, 2u);
    eqi(p.mute, 2, "two chunks of mute pending");
    eqi(gbp_aplay_irq_handoff(&p, 10u) == silence, 1, "the first mute hand-off is the silence buffer");
    eqi(p.mute, 1, "one left");
    eqi(gbp_aplay_irq_handoff(&p, 20u) == silence, 1, "the second too");
    eqi(p.mute, 0, "the mute is spent");
    eqi(p.mute_handed, 2, "mute_handed counts them");
    eqi(p.silences, 0, "no silence counted");
    eqi(p.underruns, 0, "no underrun counted");
    eqi(p.rq_head, head_before, "rq_head untouched");
    eqi(p.rq_tail, tail_before, "rq_tail untouched");
    eqi(gbp_aplay_ready(&p), 3, "the three READY chunks are still there");
    eqi(p.handed, 2, "the callback ran twice");
    eqi(p.cb_count, 2, "M counts the callbacks");
    gbp_aplay_process(&p);
    eqi(count_free(&p), free_before, "process frees nothing for the mute hand-offs");
    for (k = 0; k < 3; k++) eqi(p.state[b[k]], GBP_APLAY_READY, "every queued chunk is still READY");
    eqi(p.l2.window_chunks, 0, "nothing reached L2");
    /* the third hand-off is the first READY chunk, as if the mute had never been */
    eqi(gbp_aplay_irq_handoff(&p, 30u) == pool + (size_t)b[0] * GBP_APLAY_CHUNK_BYTES, 1,
        "the third hand-off is the oldest READY chunk");
    gbp_aplay_process(&p);
    eqi(p.state[b[0]], GBP_APLAY_HANDED, "handed");
    eqi(gbp_aplay_ready(&p), 2, "two READY left");
    eqi(p.silences + p.underruns, 0, "still no silence, no underrun");
    /* a mute with an EMPTY queue is not an underrun either, and the mute can be cancelled */
    (void)gbp_aplay_irq_handoff(&p, 40u);
    (void)gbp_aplay_irq_handoff(&p, 50u);
    eqi(gbp_aplay_ready(&p), 0, "the queue is empty");
    gbp_aplay_mute(&p, 5u);
    eqi(gbp_aplay_irq_handoff(&p, 60u) == silence, 1, "muted on an empty queue: silence");
    eqi(p.underruns, 0, "and no underrun");
    gbp_aplay_mute(&p, 0u);
    eqi(gbp_aplay_irq_handoff(&p, 70u) == silence, 1, "the mute cancelled: an ordinary empty-queue silence");
    eqi(p.silences, 1, "counted as a silence");
    eqi(p.underruns, 1, "and, while playing, an underrun");
    eqi(p.mute_handed, 3, "three mute hand-offs in all");
    gbp_aplay_process(&p);
    eqi(count_free(&p), (int)GBP_APLAY_POOL, "every chunk came back after the timeline moved on");
}

static void test_discard_chunk_frees_and_counts(void)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    int b0, b1;
    uint32_t before;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    give(&d, GBP_APLAY_TARGET, 5);
    before = d.count;
    b0 = produce_all(&p, &d);
    eqi(b0 >= 0, 1, "a chunk completes");
    eqi(before - d.count, GBP_APLAY_PUSHES, "production consumed the ring at its normal rate");
    eqi(p.state[b0], GBP_APLAY_FILLING, "completed, not yet queued");
    eqi(gbp_aplay_discard_chunk(&p, b0), 1, "discarded");
    eqi(p.state[b0], GBP_APLAY_FREE, "its buffer is FREE");
    eqi(p.discarded_chunks, 1, "counted");
    eqi(gbp_aplay_ready(&p), 0, "nothing was queued");
    eqi(p.produced, 1, "it was still produced");
    /* refusals: out of range, already FREE, a READY chunk, the chunk being filled */
    eqi(gbp_aplay_discard_chunk(&p, -1), 0, "-1 refused");
    eqi(gbp_aplay_discard_chunk(&p, (int)GBP_APLAY_POOL), 0, "POOL refused");
    eqi(gbp_aplay_discard_chunk(&p, b0), 0, "a FREE buffer refused");
    b1 = produce_all(&p, &d);
    eqi(b1, b0, "the freed buffer is reused by the next chunk");
    gbp_aplay_queue(&p, b1);
    eqi(gbp_aplay_discard_chunk(&p, b1), 0, "a READY chunk refused");
    eqi(p.state[b1], GBP_APLAY_READY, "and left READY");
    eqi(gbp_aplay_produce(&p, &d), -1, "one step: a second chunk is started, not completed");
    eqi(p.cur >= 0 && p.state[p.cur] == GBP_APLAY_FILLING, 1, "it is being filled");
    eqi(gbp_aplay_discard_chunk(&p, p.cur), 0, "the chunk being filled refused");
    eqi(p.state[p.cur], GBP_APLAY_FILLING, "and left FILLING");
    eqi(p.discarded_chunks, 1, "the count is unchanged by refusals");
}

/* a discarded chunk is never played: at a fill far above the band it takes exactly 128 samples and
 * counts no DROP (Issue #117: a DROP there made the discard 129 and put one DROP per discard in the
 * counters); far below the band, no DUP. The ordinary producer at the same fill still corrects. */
static void test_a_discarded_chunk_takes_no_correction(void)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    int b = -1, k;
    uint32_t before;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    give(&d, GBP_APLAY_TARGET + 1000u, 5);                  /* far above the band */
    before = d.count;
    for (k = 0; k < 64 && b < 0; k++) b = gbp_aplay_produce_discard(&p, &d);
    eqi(b >= 0, 1, "a discard completed");
    eqi(before - d.count, GBP_APLAY_PUSHES, "exactly 128 samples, no DROP");
    eqi(p.drop, 0, "no DROP counted"); eqi(p.dup, 0, "no DUP counted");
    gbp_aplay_set_target(&p, d.count + 1000u);                /* now far below the band */
    before = d.count; b = -1;
    for (k = 0; k < 64 && b < 0; k++) b = gbp_aplay_produce_discard(&p, &d);
    eqi(before - d.count, GBP_APLAY_PUSHES, "exactly 128 samples, no DUP");
    eqi(p.dup, 0, "no DUP counted");
    b = produce_all(&p, &d);
    eqi(b >= 0, 1, "the ordinary producer");
    eqi(p.dup, 1, "still corrects at the same fill");
}

/* §V27.15's rotation: produce_uncorrected returns a completed chunk (not freed) past the full queue and
 * with no correction; drop_front frees the queue's front unplayed -- but only while the callback's next
 * hand-off is silent (mute >= 1), because rq_head is the callback's. */
static void test_the_rotation_primitives(void)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    int b = -1, k, front;
    uint32_t before;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    give(&d, GBP_APLAY_TARGET + 1000u, 5);                  /* far above the band */
    for (k = 0; k < (int)GBP_APLAY_AHEAD; k++) { b = produce_all(&p, &d); gbp_aplay_queue(&p, b); }
    eqi(gbp_aplay_ready(&p), GBP_APLAY_AHEAD, "the queue full");
    front = (int)p.rq[p.rq_head % GBP_APLAY_POOL];
    eqi(gbp_aplay_drop_front(&p), -1, "no drop while the next hand-off would be audible (mute 0)");
    eqi(gbp_aplay_ready(&p), GBP_APLAY_AHEAD, "the queue untouched");
    gbp_aplay_mute(&p, 2u);
    before = d.count; b = -1;
    for (k = 0; k < 64 && b < 0; k++) b = gbp_aplay_produce_uncorrected(&p, &d);
    eqi(b >= 0, 1, "a chunk past the full queue");
    eqi(before - d.count, GBP_APLAY_PUSHES, "exactly 128 samples: no DROP far above the band");
    eqi(p.drop, 4, "only the four ordinary chunks corrected"); eqi(p.state[b], GBP_APLAY_FILLING, "returned, not freed");
    eqi(gbp_aplay_drop_front(&p), front, "the front chunk dropped");
    eqi(p.state[front], GBP_APLAY_FREE, "freed unplayed"); eqi(p.dropped_front, 1, "counted");
    gbp_aplay_queue(&p, b);
    eqi(gbp_aplay_ready(&p), GBP_APLAY_AHEAD, "the queue rotated: still four");
    eqi((int)p.rq[(p.rq_tail - 1u) % GBP_APLAY_POOL], b, "the fresh chunk at the back");
    (void)gbp_aplay_irq_handoff(&p, 1u);
    eqi(p.mute, 1, "a silent hand-off"); eqi(gbp_aplay_ready(&p), GBP_APLAY_AHEAD, "which leaves the queue alone");
    eqi(gbp_aplay_drop_front(&p) >= 0, 1, "mute 1: the next hand-off is still silent, a drop is allowed");
    (void)gbp_aplay_irq_handoff(&p, 2u);
    eqi(p.mute, 0, "the silence handed");
    eqi(gbp_aplay_drop_front(&p), -1, "mute 0: refused");
}

/* ring_gated (§V27.14's `starved`): a step counts only when a chunk was WANTED and the ring could not give it;
 * starved_steps keeps counting every step under 129, the benign wait with READY full included */
static void test_ring_gated_counts_only_a_wanted_chunk(void)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    int b, k;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    give(&d, 4u * GBP_APLAY_PUSHES + 100u, 5);
    for (k = 0; k < (int)GBP_APLAY_AHEAD; k++) { b = produce_all(&p, &d); gbp_aplay_queue(&p, b); }
    eqi(d.count < GBP_APLAY_PUSHES + 1u, 1, "under 129 left (the DUPs of the default target took 4), READY full");
    eqi(gbp_aplay_produce(&p, &d), -1, "nothing starts");
    eqi(p.starved_steps, 1, "starved_steps counts the wait");
    eqi(p.ring_gated, 0, "ring_gated does not: no chunk was wanted (READY full)");
    (void)gbp_aplay_irq_handoff(&p, 1u);
    eqi(gbp_aplay_ready(&p), GBP_APLAY_AHEAD - 1u, "a hand-off: READY short");
    eqi(gbp_aplay_produce(&p, &d), -1, "a chunk is wanted, the ring cannot give it");
    eqi(p.starved_steps, 2, "starved_steps"); eqi(p.ring_gated, 1, "ring_gated counts it");
    eqi(gbp_aplay_produce_uncorrected(&p, &d), -1, "an uncorrected transition chunk, the ring short");
    eqi(p.ring_gated, 2, "counts it too");
    give(&d, 100u, 5);
    eqi(gbp_aplay_produce(&p, &d), -1, "one step of a chunk now under way");
    eqi(p.ring_gated, 2, "a chunk under way counts nothing");
}

static void test_produce_discard_ignores_the_held_queue(void)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    int b, k;
    uint32_t before;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    give(&d, GBP_APLAY_TARGET + 4u * GBP_APLAY_PUSHES, 5);   /* four chunks out: the fill sits at the target, no correction */
    for (k = 0; k < (int)GBP_APLAY_AHEAD; k++) {          /* the queue HELD full, as during a mute */
        b = produce_all(&p, &d);
        eqi(b >= 0, 1, "a chunk to queue");
        gbp_aplay_queue(&p, b);
    }
    eqi(gbp_aplay_ready(&p), GBP_APLAY_AHEAD, "four READY");
    eqi(gbp_aplay_produce(&p, &d), -1, "the ordinary producer refuses: the queue is full");
    before = d.count;
    for (k = 0; k < 64; k++) { b = gbp_aplay_produce_discard(&p, &d); if (b >= 0) break; }
    eqi(b >= 0, 1, "produce_discard completed a chunk with the queue full");
    eqi(before - d.count, GBP_APLAY_PUSHES, "it consumed the ring at production's normal rate");
    eqi(p.state[b], GBP_APLAY_FREE, "and the chunk went back to the pool, unqueued");
    eqi(p.discarded_chunks, 1, "counted as discarded");
    eqi(gbp_aplay_ready(&p), GBP_APLAY_AHEAD, "the queue is still the four held chunks");
    eqi(p.produced, GBP_APLAY_AHEAD + 1u, "produced counts it");
    /* the chunk in progress continues under whichever producer calls next */
    eqi(gbp_aplay_produce_discard(&p, &d), -1, "one step: a chunk started, not completed");
    eqi(p.cur >= 0, 1, "in progress");
    gbp_aplay_mute(&p, 0u);
    eqi(gbp_aplay_produce(&p, &d), -1, "the ordinary producer continues it (queue full: it may not finish)");
}

int main(void)
{
    test_crc_is_zlibs();
    test_a_chunk();
    test_corrections_follow_the_fill();
    test_handoff_underrun_and_freeing();
    test_measuring();
    test_l2_keeps_what_its_window_consumed();
    test_half_steps_change_nothing_but_the_partition();
    test_the_adopted_default_is_8_and_changes_only_the_partition();
    test_fresh_init_defaults();
    test_set_target_moves_the_decision();
    test_mute_hands_silence_and_touches_nothing_else();
    test_discard_chunk_frees_and_counts();
    test_produce_discard_ignores_the_held_queue();
    test_a_discarded_chunk_takes_no_correction();
    test_the_rotation_primitives();
    test_ring_gated_counts_only_a_wanted_chunk();
    printf("test_gbp_aplay: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
