/*
 * tests/unit/test_gbp_aperiod.c — the tone's period, decoded one AUDIO block at a
 * time, with no device (GitHub Issue #84, §V19.4, §V19.11 A4.7).
 *
 * Every block here is SYNTHETIC: a two-level H-PWM-like square wave whose
 * transitions fall INSIDE a block at a chosen slice, as §V18 found the real
 * ones do. The cases that matter are the wrong ones: silence, noise at rest, a
 * dropped block, a period spanning a reset, and a read too short to see a step.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_aperiod.h"
#include "gbp_adrain.h"

static int checks, failures;

static void ok(int cond, const char *what)
{
    checks++;
    if (!cond) {
        failures++;
        printf("  FAIL: %s\n", what);
    }
}

static void eqi(long got, long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %ld, want %ld\n", what, got, want);
    }
}

#define HI 0x1Fu     /* 5 bits per byte: sample 20480 */
#define LO 0x07u     /* 3 bits per byte: sample 12288 */

static uint8_t blk[4096];

/* One AUDIO block of the square wave: `from` for slices [0, k), `to` after. */
static void make_block(uint8_t from, uint8_t to, unsigned k)
{
    memset(blk, to, sizeof blk);
    memset(blk, from, (size_t)k * 256u);
}

/* Block i of a period-P square wave with both transitions at slice k. */
static void wave_block(unsigned i, unsigned period, unsigned k)
{
    const unsigned half = period / 2u, ph = i % period;
    if (ph == half - 1u) make_block(HI, LO, k);          /* high -> low inside this block */
    else if (ph == period - 1u) make_block(LO, HI, k);   /* low -> high inside this block */
    else if (ph < half) make_block(HI, HI, 0u);
    else make_block(LO, LO, 0u);
}

static void feed_wave(struct gbp_aperiod *p, unsigned first, unsigned count, unsigned period,
                      unsigned k, uint32_t n)
{
    unsigned i;
    for (i = first; i < first + count; i++) {
        wave_block(i, period, k);
        (void)gbp_aperiod_feed(p, blk, n);
    }
}

static void test_full_reads_give_the_exact_period(void)
{
    struct gbp_aperiod p;
    gbp_aperiod_reset(&p, 32u);
    feed_wave(&p, 0u, 32u * 10u, 32u, 8u, 4096u);
    ok(p.periods >= 8u, "ten periods of blocks give at least eight whole periods");
    eqi(p.pmin, 32, "every period is 32 AUDIO blocks (min)");
    eqi(p.pmax, 32, "every period is 32 AUDIO blocks (max)");
    eqi(p.off, 0, "none off");
    eqi(gbp_aperiod_exact(&p, 8u), 1, "the gate's rule passes");
    eqi(gbp_aperiod_exact(&p, p.periods + 1u), 0, "but not with more periods than were counted");
    ok(p.crossings >= 18u, "two rest crossings per period");
    eqi(p.steps_visible, 20, "every transition block shows its step at a full read");
}

static void test_short_reads_keep_the_period_and_lose_the_steps(void)
{
    /* A4.7 / A7: the SEQUENCE survives a short read; the within-block step does not. */
    static const uint32_t ns[3] = { 0x20u, 0x100u, 0x400u };
    unsigned j;
    for (j = 0u; j < 3u; j++) {
        struct gbp_aperiod p;
        gbp_aperiod_reset(&p, 32u);
        feed_wave(&p, 0u, 32u * 10u, 32u, 8u, ns[j]);
        eqi(gbp_aperiod_exact(&p, 8u), 1, "a short read keeps the exact period");
        eqi(p.steps_visible, 0, "a step at slice 8 is invisible in the first four slices or less");
        ok(p.crossings >= 18u, "while the crossings are still counted");
    }
    {
        /* a step at slice 2 IS inside four slices, and inside nothing shorter than two */
        struct gbp_aperiod p;
        gbp_aperiod_reset(&p, 32u);
        feed_wave(&p, 0u, 32u * 10u, 32u, 2u, 0x400u);
        eqi(p.steps_visible, 20, "a step at slice 2 is visible in a 0x400 read");
        gbp_aperiod_reset(&p, 32u);
        feed_wave(&p, 0u, 32u * 10u, 32u, 2u, 0x100u);
        eqi(p.steps_visible, 0, "one slice can show no within-block step at all");
    }
}

static void test_silence_and_noise_never_pass(void)
{
    struct gbp_aperiod p;
    unsigned i;
    gbp_aperiod_reset(&p, 32u);
    memset(blk, 0x0F, sizeof blk);                 /* exactly rest: 16384 */
    for (i = 0u; i < 2048u; i++) (void)gbp_aperiod_feed(&p, blk, 4096u);
    eqi(p.edges, 0, "a resting signal has no rising edge: prev <= rest < cur never holds");
    eqi(gbp_aperiod_exact(&p, 48u), 0, "silence cannot pass");

    gbp_aperiod_reset(&p, 32u);
    for (i = 0u; i < 2048u; i++) {                 /* a single bit either side of rest */
        memset(blk, 0x0F, sizeof blk);
        if (i & 1u) blk[0] = 0x1F;
        (void)gbp_aperiod_feed(&p, blk, 4096u);
    }
    ok(p.periods > 48u, "noise at rest makes many periods");
    eqi(p.pmax, 2, "all of them two blocks long");
    eqi(gbp_aperiod_exact(&p, 48u), 0, "and noise cannot pass");
}

static void test_a_dropped_block_fails_the_rule(void)
{
    struct gbp_aperiod p;
    unsigned i;
    gbp_aperiod_reset(&p, 32u);
    for (i = 0u; i < 32u * 10u; i++) {
        if (i == 150u) continue;                   /* the service lost one AUDIO block */
        wave_block(i, 32u, 8u);
        (void)gbp_aperiod_feed(&p, blk, 4096u);
    }
    eqi(p.pmin, 31, "one period is a block short");
    eqi(p.off, 1, "and only one");
    eqi(gbp_aperiod_exact(&p, 8u), 0, "so the stretch is NOT exact");
}

static void test_a_period_across_a_reset_counts_nowhere(void)
{
    /* A4.7: both edges inside the stretch. The first edge after a reset opens. */
    struct gbp_aperiod p;
    gbp_aperiod_reset(&p, 32u);
    feed_wave(&p, 0u, 40u, 32u, 8u, 4096u);        /* one rising edge at block 32 */
    eqi(p.edges, 1, "one edge in the first stretch");
    eqi(p.periods, 0, "one edge closes no period");
    gbp_aperiod_reset(&p, 32u);
    feed_wave(&p, 40u, 32u * 3u, 32u, 8u, 0x20u);  /* the new length begins mid-period */
    eqi(p.edges, 3, "three edges after the reset");
    eqi(p.periods, 2, "two periods, the interval spanning the reset belonging to neither stretch");
    eqi(gbp_aperiod_exact(&p, 2u), 1, "and both are exact");
}

static void test_the_sample_is_b4s_formula(void)
{
    /* The same arithmetic as the frozen gbp_adrain_sample_from_short_read(). */
    static const uint32_t ns[5] = { 0x20u, 0x60u, 0x100u, 0x400u, 0x1000u };
    struct gbp_aperiod p;
    unsigned i, j, x = 12345u;
    for (i = 0u; i < sizeof blk; i++) { x = x * 1103515245u + 12345u; blk[i] = (uint8_t)(x >> 16); }
    for (j = 0u; j < 5u; j++) {
        gbp_aperiod_reset(&p, 32u);
        eqi(gbp_aperiod_feed(&p, blk, ns[j]), gbp_adrain_sample_from_short_read(blk, ns[j]),
            "gbp_aperiod's sample is gbp_adrain's");
    }
}

static void test_refusals_are_counted(void)
{
    struct gbp_aperiod p;
    gbp_aperiod_reset(&p, 32u);
    eqi(gbp_aperiod_feed(&p, 0, 4096u), -1, "no data");
    eqi(gbp_aperiod_feed(&p, blk, 100u), -1, "not a multiple of the DMA granule");
    eqi(gbp_aperiod_feed(&p, blk, 0u), -1, "zero bytes");
    eqi(gbp_aperiod_feed(&p, blk, 4128u), -1, "more than one AUDIO block");
    eqi(p.refused, 4, "every refusal counted");
    eqi(p.blocks, 0, "and none of them fed");
}

int main(void)
{
    test_full_reads_give_the_exact_period();
    test_short_reads_keep_the_period_and_lose_the_steps();
    test_silence_and_noise_never_pass();
    test_a_dropped_block_fails_the_rule();
    test_a_period_across_a_reset_counts_nowhere();
    test_the_sample_is_b4s_formula();
    test_refusals_are_counted();
    printf("test_gbp_aperiod: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
