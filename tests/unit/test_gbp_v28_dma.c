/*
 * tests/unit/test_gbp_v28_dma.c -- GitHub Issue #139: gbp_v28_dma, the AI DMA's hand-off semantics as READ at a callback's entry, against simulated callback sequences
 * of each pre-registered reading (HARDWARE_TESTS.md V28.23): the register holds the chunk returned at the PREVIOUS callback with the block just started (AHEAD + 1), the
 * chunk returned TWO callbacks ago (AHEAD + 2), or the previous chunk with the block just finished (AHEAD); plus silences, the seed, the raw store and the physical mask.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_v28_dma.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) { failures++; printf("  FAIL: %s: got %lld, want %lld\n", what, got, want); }
}

static uint8_t pool[16][4000] __attribute__((aligned(32)));
static uint8_t silence[4000] __attribute__((aligned(32)));

/* the reading a semantic gives at callback k: `lag` chunks back (1 = the previous callback's) with `left` bytes left */
static void run(struct gbp_v28_dma *d, uint32_t callbacks, uint32_t lag, uint32_t left0, int silent_every)
{
    uint32_t k;
    const void *hist[3] = { pool[0], 0, 0 };          /* hist[0] = the chunk returned last callback (the seed) */
    gbp_v28_dma_init(d);
    gbp_v28_dma_seed(d, pool[0]);
    for (k = 1; k <= callbacks; k++) {
        const void *ret = (silent_every && k % (uint32_t)silent_every == 0u) ? (const void *)silence : (const void *)pool[k % 16u];
        const void *seen = lag == 0u ? (const void *)(pool[15] + 64) : (lag == 1u ? hist[0] : hist[1] ? hist[1] : hist[0]);
        gbp_v28_dma_note(d, gbp_v28_dma_phys(seen), left0 - (k % 5u) * 8u, (uint64_t)k * 1264u, ret);
        hist[2] = hist[1]; hist[1] = hist[0]; hist[0] = ret;
    }
}

static void test_the_assumed_semantics(void)
{
    struct gbp_v28_dma d;
    run(&d, 500, 1u, 3990u, 0);
    eqi(d.n, 500, "every callback counted");
    eqi(d.prev1, 500, "R1: the register holds the chunk the PREVIOUS callback returned, at every callback (the seed makes the first one count)");
    eqi(d.prev2 + d.none, 0, "and nothing else");
    eqi(d.bins[4] + d.bins[5], 500, "bytes left near 4 000 (3 950-3 990)");
    eqi(d.left_max, 3990, "max");
    eqi(d.left_min, 3958, "min");
    eqi((long long)(d.left_sum / d.n), 3974, "mean");
    eqi(d.raw_n, GBP_V28_DMA_RAW, "the first callbacks are kept raw");
    eqi(d.raw[1].dt, 1264, "the raw store carries the time since the last callback");
    eqi(d.raw[0].dt, 0, "the first has none");
    eqi(d.raw[0].ret1, gbp_v28_dma_phys(pool[0]), "the raw store carries what the seed said the register should hold");
}

static void test_ahead_plus_two(void)
{
    struct gbp_v28_dma d;
    run(&d, 500, 2u, 3990u, 0);
    eqi(d.prev2, 499, "R2: the register holds the chunk returned TWO callbacks ago (all but the first, which has no such chunk yet)");
    eqi(d.prev1, 1, "(the first callback falls back to the seed, the previous chunk)");
    eqi(d.none, 0, "no unexplained register");
}

static void test_a_finished_block(void)
{
    struct gbp_v28_dma d;
    run(&d, 500, 1u, 40u, 0);
    eqi(d.prev1, 500, "R3: the previous chunk again");
    eqi(d.bins[0], 500, "but with under 1 000 bytes left: the block has just FINISHED");
}

static void test_an_unexplained_register(void)
{
    struct gbp_v28_dma d;
    run(&d, 300, 0u, 3990u, 0);
    eqi(d.none, 300, "R4: a register that is none of the chunks the last two callbacks returned");
    eqi(d.prev1 + d.prev2, 0, "");
}

static void test_silences_are_counted_apart(void)
{
    struct gbp_v28_dma d;
    uint32_t k;
    gbp_v28_dma_init(&d);
    gbp_v28_dma_seed(&d, silence);
    for (k = 0; k < 10u; k++) gbp_v28_dma_note(&d, gbp_v28_dma_phys(silence), 3990u, (uint64_t)k, silence);
    eqi(d.same12, 9, "two consecutive silences cannot be told apart by their pointers: counted, never classified (the seed is the silence too, so the first is not a pair)");
    eqi(d.prev1 + d.prev2 + d.none, 1, "only the call before the second silence had two DIFFERENT last chunks... the seeded silence and no earlier one");
}

static void test_the_physical_mask(void)
{
    eqi(gbp_v28_dma_phys((const void *)(uintptr_t)0x80123460u), 0x123460, "cached virtual -> physical, 32-byte aligned");
    eqi(gbp_v28_dma_phys((const void *)(uintptr_t)0xC0123460u), 0x123460, "uncached virtual -> the same physical");
    eqi(gbp_v28_dma_phys((const void *)(uintptr_t)0x8012347Fu), 0x123460, "the low five bits are dropped as the register does");
}

static void test_no_seed_no_classification(void)
{
    struct gbp_v28_dma d;
    gbp_v28_dma_init(&d);
    gbp_v28_dma_note(&d, 0x1000u, 3000u, 5u, pool[1]);
    eqi(d.prev1 + d.prev2 + d.none + d.same12, 0, "before the seed nothing is classified");
    eqi(d.n, 1, "but the read is counted");
    eqi(d.bins[3], 1, "and binned (3 000-3 499)");
}

int main(void)
{
    printf("test_gbp_v28_dma\n");
    test_the_assumed_semantics();
    test_ahead_plus_two();
    test_a_finished_block();
    test_an_unexplained_register();
    test_silences_are_counted_apart();
    test_the_physical_mask();
    test_no_seed_no_classification();
    printf("  %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
