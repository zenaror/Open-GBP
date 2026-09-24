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
    printf("test_gbp_aplay: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
