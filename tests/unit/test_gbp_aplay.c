/*
 * tests/unit/test_gbp_aplay.c — Phase 6's playback chain with no device (GitHub
 * Issue #92, §V22.2-§V22.5).
 *
 * The callback is simulated by calling gbp_aplay_irq_handoff() from here, at the
 * cadence a test chooses. What is checked: a chunk is 128 pushes and 1000 frames
 * written big-endian; a correction is at most one per chunk by default (k, spread one per
 * sub-block, with gbp_aplay_set_corrections since Issue #123) and in the direction
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
    /* the same fills at the default target are all DUPs: the field is what the decision reads
     * AMENDED 2026-09-25 (GitHub Issue #121), on top: the default was 2048 when this was written and is 512 (0.125 s)
     * since, so the comparison target is set to that 2048 explicitly; the assertion is unchanged. */
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    gbp_aplay_set_target(&p, 2048u);                         /* Issue #121: the default until then */
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
    /* AMENDED 2026-09-25 (GitHub Issue #121), on top: the message below describes the 2048 default (four DUPs, 104
     * left). At 512 the four chunks take three DUPs and one DROP and leave 102, still under 129: the assertion holds. */
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

/* Issue #121 (2026-09-25): the adopted cushion, 0.125 s, set in TIME. The default target is the decoder's rate times
 * the cushion, a whole number of samples, and a fresh init holds it. The correction tests written relative to
 * GBP_APLAY_TARGET (test_a_chunk, test_corrections_follow_the_fill, the mute, discard and rotation tests) now run at 512
 * unchanged. Two were not relative to it: test_set_target_moves_the_decision's #117 comparison used an absolute 2048
 * and is amended to set it explicitly; test_ring_gated_counts_only_a_wanted_chunk's absolute fill, 612, now takes one
 * DROP and three DUPs instead of four DUPs and still leaves the ring under 129, so its assertion holds as written. The
 * default was 2048 (0.5 s) in every build before #121; each executed image reproduces at its own commit
 * (HARDWARE_TESTS §V23.9). */
static void test_the_default_cushion_is_0_125_s(void)
{
    static struct gbp_aplay p;
    printf("-- Issue #121: the default cushion is 0.125 s, 512 samples at 4 096 per second\n");
    eqi(GBP_APLAY_CUSHION_US, 125000, "0.125 s, in microseconds");
    eqi(GBP_ADEC_RATE, 4096, "today's decoded rate");
    eqi(GBP_APLAY_TARGET, 512, "512 decoded samples");
    eqi((long long)GBP_APLAY_TARGET * 1000000ll, (long long)GBP_APLAY_CUSHION_US * GBP_ADEC_RATE,
        "exactly the time: no rounding");
    eqi(GBP_APLAY_TARGET >= GBP_APLAY_TARGET_MIN && GBP_APLAY_TARGET <= GBP_APLAY_TARGET_MAX, 1,
        "a target the clamp accepts as it is");
    gbp_aplay_init(&p, pool, silence, keep, events);
    eqi(p.target, 512, "a fresh init holds it");
}


/* ---- Issue #123: k corrections a chunk, spread one per sub-block ------------------------------------ */
static void test_one_correction_a_chunk_is_the_default(void)
{
    static struct gbp_aplay p;
    static const uint32_t bad[] = { 0u, 3u, 5u, 96u, 128u, 129u, 256u };   /* 128: a DUP is two pushes */
    uint32_t k, i;
    gbp_aplay_init(&p, pool, silence, keep, events);
    eqi(p.corr_per_chunk, 1, "one correction a chunk after init: every earlier build's");
    for (i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        eqi(gbp_aplay_set_corrections(&p, bad[i]), -1, "a k that does not divide 128, or above 64, is refused");
        eqi(p.corr_per_chunk, 1, "and nothing changed");
    }
    for (k = 1u; k <= GBP_APLAY_PUSHES / 2u; k *= 2u) {
        eqi(gbp_aplay_set_corrections(&p, k), 0, "a divisor of 128 up to 64 is accepted");
        eqi(p.corr_per_chunk, k, "and held");
    }
}

/* one chunk from a ring holding `fill` samples and nothing more fed; its L2 event indices into `idx` */
static uint32_t one_chunk(uint32_t k, uint32_t fill, uint32_t *idx, uint32_t *popped, struct gbp_aplay *p)
{
    struct gbp_adec d;
    uint32_t i, n;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(p, pool, silence, keep, events);
    eqi(gbp_aplay_set_corrections(p, k), 0, "k set");
    p->playing = 1u;                                      /* k applies only while playing */
    gbp_aplay_arm_l2(p);                                  /* keeps from the first chunk's start: the event indices */
    give(&d, fill, 11);
    *popped = d.count;
    eqi(produce_all(p, &d) >= 0, 1, "the chunk completes");
    *popped -= d.count;
    eqi(p->cur_frames, 1000, "1000 frames, whatever the corrections");
    eqi(p->rs.acc, 0, "the accumulator back at 0 at the boundary");
    n = p->l2.n_events;
    for (i = 0; i < n && i < 64u; i++) idx[i] = events[i].index;
    return n;
}

static void test_k_corrections_are_spread_one_per_sub_block(void)
{
    static struct gbp_aplay p;
    static const uint32_t K[] = { 1u, 2u, 4u, 8u, 16u, 32u, 64u };
    uint32_t idx[64], popped, n, i, j;
    char w[160];
    for (i = 0; i < sizeof K / sizeof K[0]; i++) {
        const uint32_t k = K[i], sub = GBP_APLAY_PUSHES / k;
        /* under the band all the way: every sub-block DUPs */
        n = one_chunk(k, GBP_APLAY_TARGET - GBP_APLAY_BAND - 200u, idx, &popped, &p);
        snprintf(w, sizeof w, "k %u: one DUP per sub-block", k);                     eqi(p.dup, k, w);
        snprintf(w, sizeof w, "k %u: DUPs pop 128 - k samples for 128 pushes", k);  eqi(popped, 128u - k, w);
        snprintf(w, sizeof w, "k %u: each DUP an L2 event", k);                      eqi(n, k, w);
        for (j = 1; j < n; j++) {
            snprintf(w, sizeof w, "k %u: DUP %u a whole sub-block after the one before (%u samples)", k, j,
                     idx[j] - idx[j - 1]);
            eqi(idx[j] - idx[j - 1], sub - 1u, w);          /* a sub-block of pushes, one of them the DUP's */
        }
        /* over the band all the way: every sub-block DROPs */
        n = one_chunk(k, GBP_APLAY_TARGET + GBP_APLAY_BAND + 200u, idx, &popped, &p);
        snprintf(w, sizeof w, "k %u: one DROP per sub-block", k);                    eqi(p.drop, k, w);
        snprintf(w, sizeof w, "k %u: DROPs pop 128 + k samples for 128 pushes", k); eqi(popped, 128u + k, w);
        for (j = 1; j < n; j++) {
            snprintf(w, sizeof w, "k %u: DROP %u a whole sub-block after the one before", k, j);
            eqi(idx[j] - idx[j - 1], sub + 1u, w);          /* a sub-block of pushes, plus the dropped sample */
        }
    }
}

static void test_a_decision_holds_the_effective_fill(void)
{
    /* the ring AT the level and nothing fed: the raw count falls by 128 across the chunk, the level a decision
     * compares (the chunk-start count less the chunk's own net corrections) does not move. A decision against
     * the raw count would DUP every late sub-block. */
    static struct gbp_aplay p;
    uint32_t idx[64], popped;
    (void)one_chunk(8u, GBP_APLAY_TARGET, idx, &popped, &p);
    eqi(p.dup + p.drop, 0, "at the level: no correction in any sub-block");
    eqi(popped, 128, "exactly 128 samples");
}

/* a sustained deficit of `short_by` samples a chunk period; the fill at the START of the last period's chunk (the
 * level a decision compares: in this model the feed comes before production, so it is also every sub-block's) */
static uint32_t deficit_run(uint32_t k, uint32_t short_by, uint32_t periods, uint32_t *dups)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    uint32_t i, start = 0u;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    eqi(gbp_aplay_set_corrections(&p, k), 0, "k set");
    give(&d, GBP_APLAY_TARGET, 9);
    p.playing = 1u;
    for (i = 0; i < periods; i++) {
        int b;
        give(&d, 128u - short_by, 9);
        start = d.count;
        b = produce_all(&p, &d);
        if (b >= 0) gbp_aplay_queue(&p, b);
        (void)gbp_aplay_irq_handoff(&p, 1000u + i);
        gbp_aplay_process(&p);
    }
    *dups = p.dup;
    return start;
}

static void test_k_corrections_hold_a_deficit_one_cannot(void)
{
    uint32_t dups1, dups4, f1, f4;
    /* 3 samples short a period: one correction a chunk repays 1, four repay up to 4 */
    f1 = deficit_run(1u, 3u, 300u, &dups1);
    f4 = deficit_run(4u, 3u, 300u, &dups4);
    printf("   a deficit of 3 a period over 300: one a chunk leaves the chunk-start fill at %u (%u DUPs); "
           "four a chunk at %u (%u DUPs)\n", f1, dups1, f4, dups4);
    eqi(f1 + 100u < GBP_APLAY_TARGET - GBP_APLAY_BAND, 1, "one a chunk cannot hold it: far under the band");
    eqi(f4 + 4u >= GBP_APLAY_TARGET - GBP_APLAY_BAND && f4 <= GBP_APLAY_TARGET + GBP_APLAY_BAND, 1,
        "four a chunk hold it at the band's lower edge");
    eqi(dups4 >= 750u && dups4 <= 904u, 1, "four a chunk: about the deficit's 3 DUPs a period");
}

static void test_only_corrected_calls_decide(void)
{
    /* a chunk started by a corrected call and finished by a transition's uncorrected calls: only the sub-block
     * decided in the corrected call corrects; a chunk started uncorrected never does */
    static struct gbp_aplay p;
    struct gbp_adec d;
    int b = -1, k;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    eqi(gbp_aplay_set_corrections(&p, 8u), 0, "k 8");
    p.playing = 1u;
    give(&d, GBP_APLAY_TARGET - GBP_APLAY_BAND - 200u, 5);
    eqi(gbp_aplay_produce(&p, &d), -1, "one corrected call: a sub-block of 16 pushes, 8 of them done");
    for (k = 0; k < 64 && b < 0; k++) b = gbp_aplay_produce_uncorrected(&p, &d);
    eqi(b >= 0, 1, "finished by uncorrected calls");
    eqi(p.dup, 1, "only the corrected call's sub-block corrected");
    gbp_aplay_init(&p, pool, silence, keep, events);
    eqi(gbp_aplay_set_corrections(&p, 8u), 0, "k 8");
    b = -1;
    for (k = 0; k < 64 && b < 0; k++) b = gbp_aplay_produce_uncorrected(&p, &d);
    eqi(b >= 0 && p.dup + p.drop == 0u, 1, "a chunk started uncorrected never corrects");
}

static void test_k_takes_effect_from_the_next_chunk(void)
{
    /* the gate that started a chunk was checked against its k: a k moved mid-chunk must not add decisions the gate
     * never paid for. The chunk in progress keeps the k it started with; the next chunk takes the new one. */
    static struct gbp_aplay p;
    struct gbp_adec d;
    uint32_t popped;
    int b = -1, i;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    p.playing = 1u;
    give(&d, GBP_APLAY_TARGET + GBP_APLAY_BAND + 600u, 7);   /* over the band for both chunks */
    popped = d.count;
    eqi(gbp_aplay_produce(&p, &d), -1, "one call of a chunk started with k 1");
    eqi(gbp_aplay_set_corrections(&p, 16u), 0, "k moved to 16 mid-chunk");
    for (i = 0; i < 64 && b < 0; i++) b = gbp_aplay_produce(&p, &d);
    popped -= d.count;
    eqi(b >= 0, 1, "the chunk completes");
    eqi(p.drop, 1, "the chunk in progress keeps k 1: one DROP");
    eqi(popped, 129, "129 samples for it");
    b = produce_all(&p, &d);
    eqi(b >= 0, 1, "the next chunk completes");
    eqi(p.drop, 1u + 16u, "the next chunk takes k 16: sixteen DROPs");
}

/* Issue #123, review: the three failures of the first rule (a decision against the ring plus what the chunk had
 * taken), each reproduced on it before it was replaced. */
static uint32_t step_of(void *user, uint32_t seq) { (void)seq; return *(const uint32_t *)user; }

static void test_a_matched_feed_during_production_corrects_nothing(void)
{
    /* the feed arrives BETWEEN production calls, exactly as fast as the chunk consumes it, over a chunk spread across
     * many calls (the native decode's longer production): nothing is surplus and nothing is short, at any k. The
     * first rule counted every sample that arrived during the chunk as surplus, and DROPped from the second
     * sub-block on, then DUPped back: 1 201 corrections in 200 chunks at k = 8 with 2-push calls. */
    static const uint32_t K[] = { 1u, 8u, 16u, 64u };
    static struct gbp_aplay p;
    uint32_t i, per, step = 2u;
    char w[120];
    for (i = 0; i < sizeof K / sizeof K[0]; i++) {
        struct gbp_adec d;
        gbp_adec_init(&d, ring, GBP_APLAY_RING);
        gbp_aplay_init(&p, pool, silence, keep, events);
        eqi(gbp_aplay_set_corrections(&p, K[i]), 0, "k set");
        p.step_pushes = step_of;
        p.step_pushes_user = &step;
        give(&d, GBP_APLAY_TARGET, 3);
        p.playing = 1u;
        for (per = 0; per < 200u; per++) {
            int b = -1, c;
            for (c = 0; c < 64 && b < 0; c++) {          /* 64 calls of 2 pushes: one chunk, fed as it goes */
                give(&d, step, 3);
                b = gbp_aplay_produce(&p, &d);
            }
            if (b >= 0) gbp_aplay_queue(&p, b);
            (void)gbp_aplay_irq_handoff(&p, 1000u + per);
            gbp_aplay_process(&p);
        }
        snprintf(w, sizeof w, "k %u, a matched feed during production: no correction in 200 chunks", K[i]);
        eqi(p.dup + p.drop, 0, w);
        snprintf(w, sizeof w, "k %u: 200 chunks produced", K[i]);
        eqi(p.produced, 200, w);
    }
}

static void test_a_chunk_at_the_band_edge_corrects_once(void)
{
    /* one sample above the band and a balanced feed: one DROP brings it to the edge, and it stays. The first rule
     * never saw the chunk's own corrections, so every sub-block DROPped: k = 64 went 529 -> 465 -> 529, 64
     * corrections a chunk for ever. */
    static const uint32_t K[] = { 1u, 8u, 64u };
    static struct gbp_aplay p;
    uint32_t i, per, start = 0u;
    char w[120];
    for (i = 0; i < sizeof K / sizeof K[0]; i++) {
        struct gbp_adec d;
        gbp_adec_init(&d, ring, GBP_APLAY_RING);
        gbp_aplay_init(&p, pool, silence, keep, events);
        eqi(gbp_aplay_set_corrections(&p, K[i]), 0, "k set");
        give(&d, GBP_APLAY_TARGET + GBP_APLAY_BAND + 1u - 128u, 3);
        p.playing = 1u;
        for (per = 0; per < 40u; per++) {
            int b;
            give(&d, 128u, 3);                           /* balanced: 128 a chunk, before production */
            start = d.count;
            b = produce_all(&p, &d);
            if (b >= 0) gbp_aplay_queue(&p, b);
            (void)gbp_aplay_irq_handoff(&p, 1000u + per);
            gbp_aplay_process(&p);
        }
        snprintf(w, sizeof w, "k %u, one above the band: exactly one DROP in 40 chunks", K[i]);
        eqi(p.drop == 1u && p.dup == 0u, 1, w);
        snprintf(w, sizeof w, "k %u: the level held at the band's edge", K[i]);
        eqi(start, GBP_APLAY_TARGET + GBP_APLAY_BAND, w);   /* each chunk-start count after the first */
    }
}

/* one chunk under the band at k: a first corrected call, uncorrected calls until `resume` pushes, then corrected calls
 * to the end, `step` pushes a call. Returns the DUP count; the DUP event indices go to idx. */
static uint32_t resumed_chunk(uint32_t k, uint32_t step, uint32_t resume, uint32_t *idx, uint32_t *n)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    uint32_t i;
    int b = -1, c;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    eqi(gbp_aplay_set_corrections(&p, k), 0, "k set");
    p.playing = 1u;
    p.step_pushes = step_of;
    p.step_pushes_user = &step;
    gbp_aplay_arm_l2(&p);
    give(&d, GBP_APLAY_TARGET - GBP_APLAY_BAND - 200u, 5);
    eqi(gbp_aplay_produce(&p, &d), -1, "one corrected call");
    for (c = 0; c < 128 && p.cur_pushes < resume; c++) (void)gbp_aplay_produce_uncorrected(&p, &d);
    eqi(p.cur_pushes, resume, "the uncorrected calls stop where the case says");
    for (c = 0; c < 128 && b < 0; c++) b = gbp_aplay_produce(&p, &d);
    eqi(b >= 0, 1, "the chunk completes");
    *n = p.l2.n_events;
    for (i = 0; i < *n && i < 64u; i++) idx[i] = events[i].index;
    return p.dup;
}

static void test_a_sub_block_an_uncorrected_call_started_is_forgone(void)
{
    /* k = 8 under the band, 8-push calls: one corrected call (sub-block 0), six uncorrected calls (pushes 8..55, the
     * first pushes of sub-blocks 1..3), then corrected calls to the end. Sub-blocks 1..3 are forgone and 4..7 decided
     * at their first pushes: five DUPs. The first rule caught up one passed sub-block a push (DUPs on samples 55, 56
     * and 57); a rule deciding late, once, still put a late DUP beside the next sub-block's (the second review). So in
     * every case -- the review's step and resume points included -- every DUP falls on a sub-block's first push, and
     * none is nearer the one before than a sub-block (forgone sub-blocks leave wider gaps). */
    static const uint32_t C[][3] = { { 8u, 8u, 56u }, { 8u, 2u, 30u }, { 8u, 5u, 95u }, { 16u, 3u, 15u },
                                     { 4u, 7u, 63u } };
    uint32_t idx[64], n, i, c;
    char w[140];
    eqi(resumed_chunk(8u, 8u, 56u, idx, &n), 5, "k 8, resumed at push 56: five DUPs, sub-blocks 0 and 4..7");
    for (c = 0; c < sizeof C / sizeof C[0]; c++) {
        const uint32_t k = C[c][0], sub = GBP_APLAY_PUSHES / k;
        (void)resumed_chunk(k, C[c][1], C[c][2], idx, &n);
        for (i = 0; i < n; i++) {
            /* a DUP's push is its sample's index plus the DUPs before it (each pushed one sample twice) */
            snprintf(w, sizeof w, "k %u, step %u, resumed at %u: DUP %u at a sub-block's first push", k, C[c][1],
                     C[c][2], i);
            eqi((idx[i] + i) % sub, 0, w);
            if (i == 0) continue;
            snprintf(w, sizeof w, "k %u, step %u, resumed at %u: DUP %u no nearer the one before than a sub-block",
                     k, C[c][1], C[c][2], i);
            eqi(idx[i] - idx[i - 1] >= sub - 1u, 1, w);
        }
    }
}

static void test_a_chunk_keeps_its_frame(void)
{
    /* a corrected chunk under way when the level is moved down -- set_target and a discard, as gbp_atrans's UNMUTED
     * shallowing does -- takes no correction: its decisions are in its start frame. The next chunk starts at the new
     * level and has nothing to correct. The first two rules DROPped in every remaining sub-block (k = 64: 60 DROPs,
     * the next chunk 44 under the band, then 44 DUPs back). */
    static const uint32_t K[] = { 1u, 8u, 64u };
    static struct gbp_aplay p;
    uint32_t i, per;
    char w[120];
    for (i = 0; i < sizeof K / sizeof K[0]; i++) {
        struct gbp_adec d;
        int b = -1, c;
        gbp_adec_init(&d, ring, GBP_APLAY_RING);
        gbp_aplay_init(&p, pool, silence, keep, events);
        gbp_aplay_set_target(&p, 1024u);
        eqi(gbp_aplay_set_corrections(&p, K[i]), 0, "k set");
        p.playing = 1u;
        give(&d, 1024u, 3);
        eqi(gbp_aplay_produce(&p, &d), -1, "one corrected call of a chunk at the old level");
        gbp_aplay_set_target(&p, GBP_APLAY_TARGET);
        (void)gbp_adec_discard(&d, 1024u - GBP_APLAY_TARGET);
        for (c = 0; c < 64 && b < 0; c++) b = gbp_aplay_produce(&p, &d);
        snprintf(w, sizeof w, "k %u: the chunk under way takes no correction", K[i]);
        eqi(b >= 0 && p.dup + p.drop == 0u, 1, w);
        gbp_aplay_queue(&p, b);
        for (per = 0; per < 20u; per++) {
            give(&d, 128u, 3);
            b = produce_all(&p, &d);
            if (b >= 0) gbp_aplay_queue(&p, b);
            (void)gbp_aplay_irq_handoff(&p, 1000u + per);
            gbp_aplay_process(&p);
        }
        snprintf(w, sizeof w, "k %u: nothing to correct at the new level in 20 chunks", K[i]);
        eqi(p.dup + p.drop, 0, w);
    }
}

/* a matched feed, 128 samples a period, delivered in batches every `every` of a period's 110 pump calls; the chunk
 * produced as the pump allows, one hand-off a period once READY holds two. The corrections and underruns of periods
 * 200..600 (after the start). */
static void batched_run(uint32_t k, uint32_t target, uint32_t every, uint32_t *corr, uint32_t *under)
{
    static struct gbp_aplay p;
    struct gbp_adec d;
    uint32_t per, c, fed = 0u, c0 = 0u, u0 = 0u;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    gbp_aplay_set_target(&p, target);
    eqi(gbp_aplay_set_corrections(&p, k), 0, "k set");
    for (per = 0; per < 600u; per++) {
        for (c = 0; c < 110u; c++) {
            const uint32_t call = per * 110u + c;
            int b;
            if (call % every == 0u) {                       /* the batch due until the next delivery */
                const uint32_t due = (uint32_t)(((uint64_t)(call + every) * 128u) / 110u);
                give(&d, due - fed, 3);
                fed = due;
            }
            b = gbp_aplay_produce(&p, &d);
            if (b >= 0) gbp_aplay_queue(&p, b);
        }
        if (!p.playing && gbp_aplay_ready(&p) >= 2u) p.playing = 1u;
        if (p.playing) {
            (void)gbp_aplay_irq_handoff(&p, 1000u + per);
            gbp_aplay_process(&p);
        }
        if (per == 199u) { c0 = p.dup + p.drop; u0 = p.underruns; }
    }
    *corr = p.dup + p.drop - c0;
    *under = p.underruns - u0;
}

static void test_a_chunk_finishes_from_the_gate_at_any_k(void)
{
    /* the gate stays PUSHES + 1 at every k: the decisions stop DROPping at the band's upper edge, so a chunk started
     * at s0 takes at most 128 + (s0 - target - BAND) <= s0 samples. At the lowest target, 128, and k up to 64, a
     * matched feed in batches of ~8 and ~15 samples takes no correction and the AI never underruns. A gate of
     * PUSHES + k (the second rule) sat at the band's upper edge for k = 16 at target 128: every batch that crossed it
     * started a chunk over the edge, which DROPped, and the AI underran (the third review). */
    static const uint32_t K[] = { 1u, 16u, 64u }, E[] = { 7u, 13u };
    uint32_t i, e, corr, under;
    char w[140];
    for (i = 0; i < sizeof K / sizeof K[0]; i++)
        for (e = 0; e < sizeof E / sizeof E[0]; e++) {
            batched_run(K[i], GBP_APLAY_TARGET_MIN, E[e], &corr, &under);
            snprintf(w, sizeof w, "k %u at target 128, batches every %u calls: no correction, no underrun", K[i],
                     E[e]);
            eqi(corr == 0u && under == 0u, 1, w);
        }
}

static void test_before_playback_a_chunk_corrects_at_most_once(void)
{
    /* the prefill: chunks produced from a ring at the gate, before the AI starts, far under the band. The ring filling
     * up is not drift: one DUP a chunk, every earlier build's start-up transient, not k (k = 64 would double every
     * sample of the first chunks). Once playing, k applies. */
    static struct gbp_aplay p;
    struct gbp_adec d;
    gbp_adec_init(&d, ring, GBP_APLAY_RING);
    gbp_aplay_init(&p, pool, silence, keep, events);
    eqi(gbp_aplay_set_corrections(&p, 8u), 0, "k 8");
    give(&d, GBP_APLAY_PUSHES + 8u, 3);
    eqi(produce_all(&p, &d) >= 0 && p.dup == 1u, 1, "not playing: one DUP");
    p.playing = 1u;
    give(&d, GBP_APLAY_PUSHES + 8u, 3);
    eqi(produce_all(&p, &d) >= 0 && p.dup == 1u + 8u, 1, "playing: eight");
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
    test_the_default_cushion_is_0_125_s();
    test_one_correction_a_chunk_is_the_default();
    test_k_corrections_are_spread_one_per_sub_block();
    test_a_decision_holds_the_effective_fill();
    test_k_corrections_hold_a_deficit_one_cannot();
    test_only_corrected_calls_decide();
    test_k_takes_effect_from_the_next_chunk();
    test_a_matched_feed_during_production_corrects_nothing();
    test_a_chunk_at_the_band_edge_corrects_once();
    test_a_sub_block_an_uncorrected_call_started_is_forgone();
    test_a_chunk_keeps_its_frame();
    test_a_chunk_finishes_from_the_gate_at_any_k();
    test_before_playback_a_chunk_corrects_at_most_once();
    printf("test_gbp_aplay: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
