/*
 * tests/unit/test_gbp_adrain.c — GBP-AUDIO-005's phase machine, with no device
 * and no console (GitHub Issue #84, HARDWARE_TESTS §V19).
 *
 * Every tick here is invented, so the whole of §V19's order, its coverage
 * counter and its two positive controls are checked before the POC exists. The
 * cases that matter most are the ones only a WRONG run reaches: a silent tone,
 * a sweep that never recovers, and a block arriving past the counter's end.
 */
#include <stdio.h>
#include <string.h>
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

#define TB 40500000u

/* Drive the machine to the start of PHASE B, the way a correct run does. */
static void to_phase_b(struct gbp_adrain *d, uint64_t *now)
{
    gbp_adrain_init(d, TB);
    gbp_adrain_tone_started(d, *now);
    gbp_adrain_step(d, *now, 1);                 /* CONTROL1 passes */
}

static void test_the_frozen_sweep(void)
{
    eqi(gbp_adrain_n_for_step(0), 0x20, "N step 0");
    eqi(gbp_adrain_n_for_step(1), 0x100, "N step 1");
    eqi(gbp_adrain_n_for_step(2), 0x400, "N step 2");
    /* every N the sweep uses is a legal multiple of the DMA granule */
    ok(gbp_adrain_legal_n(0x20) && gbp_adrain_legal_n(0x100) && gbp_adrain_legal_n(0x400),
       "the swept N are legal");
    ok(!gbp_adrain_legal_n(0), "zero is not a legal N");
    ok(!gbp_adrain_legal_n(100), "100 is not a multiple of the DMA granule");
    ok(!gbp_adrain_legal_n(4128), "larger than one AUDIO block is not legal");
    ok(gbp_adrain_legal_n(4096), "one whole AUDIO block is legal");
    eqi(gbp_adrain_budget_seconds(), 60 + 10 + 9, "the budget the Operator commits to");
}

static void test_the_short_read_sample(void)
{
    static uint8_t buf[4096];
    memset(buf, 0xFF, sizeof buf);
    eqi(gbp_adrain_sample_from_short_read(buf, 256), 32768, "all ones, N=256");
    eqi(gbp_adrain_sample_from_short_read(buf, 4096), 32768, "all ones, whole AUDIO block");
    memset(buf, 0x00, sizeof buf);
    eqi(gbp_adrain_sample_from_short_read(buf, 32), 0, "all zeros");
    /* a FLAT AUDIO block reads the same at every N -- §V18.5's "exact on flat" */
    memset(buf, 0xAA, sizeof buf);
    eqi(gbp_adrain_sample_from_short_read(buf, 32), 16384, "flat at N=32");
    eqi(gbp_adrain_sample_from_short_read(buf, 256), 16384, "flat at N=256");
    eqi(gbp_adrain_sample_from_short_read(buf, 4096), 16384, "flat whole");
    /* an EDGE block does NOT, which is why QUESTION A reads sequence not fidelity */
    memset(buf, 0xFF, 2048);
    memset(buf + 2048, 0x00, 2048);
    ok(gbp_adrain_sample_from_short_read(buf, 256) != gbp_adrain_sample_from_short_read(buf, 4096),
       "an edge AUDIO block reads differently at different N");
    eqi(gbp_adrain_sample_from_short_read(buf, 100), -1, "an illegal N is refused");
    eqi(gbp_adrain_sample_from_short_read(0, 256), -1, "a null buffer is refused");
}

static void test_the_phase_order(void)
{
    struct gbp_adrain d;
    uint64_t now = 1000u * TB;                   /* an arbitrary epoch */
    gbp_adrain_init(&d, TB);
    eqi(d.phase, GBP_ADRAIN_PROMPT, "a run begins at the prompt");
    eqi(gbp_adrain_read_len(&d), 4096, "the prompt reads whole AUDIO blocks");

    /* the prompt waits for the Operator and for nothing else */
    gbp_adrain_step(&d, now + 3600ull * TB, 1);
    eqi(d.phase, GBP_ADRAIN_PROMPT, "the prompt does not time out into the run");

    gbp_adrain_tone_started(&d, now);
    eqi(d.phase, GBP_ADRAIN_CONTROL1, "A at the prompt starts the first control");
    gbp_adrain_step(&d, now, 1);
    eqi(d.phase, GBP_ADRAIN_B, "the first control passing enters PHASE B");
    ok(d.t_b == now, "D1's windows count from PHASE B's start");

    gbp_adrain_step(&d, now + 59ull * TB, 1);
    eqi(d.phase, GBP_ADRAIN_B, "PHASE B does not end early");
    gbp_adrain_step(&d, now + 60ull * TB, 1);
    eqi(d.phase, GBP_ADRAIN_C, "PHASE B is 60 s exactly");

    now += 60ull * TB;
    gbp_adrain_step(&d, now + 10ull * TB, 1);
    eqi(d.phase, GBP_ADRAIN_CONTROL2, "PHASE C is 10 s");

    now += 10ull * TB;
    eqi(gbp_adrain_read_len(&d), 4096, "the second control is anchored on a full read");
    gbp_adrain_step(&d, now, 1);
    eqi(d.phase, GBP_ADRAIN_A, "the second control passing enters PHASE A");
    eqi(gbp_adrain_read_len(&d), 0x20, "PHASE A starts at the lowest N");

    gbp_adrain_step(&d, now + 3ull * TB, 1);
    eqi(gbp_adrain_read_len(&d), 0x100, "the sweep moves low to high");
    gbp_adrain_step(&d, now + 6ull * TB, 1);
    eqi(gbp_adrain_read_len(&d), 0x400, "and on to the highest");
    gbp_adrain_step(&d, now + 9ull * TB, 1);
    eqi(d.phase, GBP_ADRAIN_DONE, "the run ends after the third step");
}

static void test_a_silent_run_never_reaches_phase_a(void)
{
    /* AMENDMENT 2 B3: the false refutation this exists to prevent. */
    struct gbp_adrain d;
    uint64_t now = 0u;
    to_phase_b(&d, &now);
    gbp_adrain_step(&d, 60ull * TB, 1);
    gbp_adrain_step(&d, 70ull * TB, 1);
    eqi(d.phase, GBP_ADRAIN_CONTROL2, "at the second control");
    gbp_adrain_step(&d, 70ull * TB, 0);          /* the tone is NOT there */
    eqi(d.phase, GBP_ADRAIN_DONE, "a failed second control ends the run");
    ok(d.phase != GBP_ADRAIN_A, "PHASE A is never entered without the tone");
    eqi(d.control2_ok, 0, "and the report says which control failed");
    eqi(d.control1_ok, 1, "while the first one had passed");
}

static void test_the_first_control_does_not_void_the_run(void)
{
    struct gbp_adrain d;
    gbp_adrain_init(&d, TB);
    gbp_adrain_tone_started(&d, 0u);
    gbp_adrain_step(&d, 0u, 0);                  /* no tone yet */
    eqi(d.phase, GBP_ADRAIN_CONTROL1, "it waits rather than failing the run");
    gbp_adrain_step(&d, TB, 1);                  /* he presses again; now it sounds */
    eqi(d.phase, GBP_ADRAIN_B, "and proceeds once the tone is established");
}

static void test_the_coverage_counter(void)
{
    struct gbp_adrain d;
    uint64_t now = 5000ull * TB;
    uint32_t i;
    to_phase_b(&d, &now);

    /* one second's worth of AUDIO blocks, spread across that second */
    for (i = 0u; i < 4096u; i++)
        gbp_adrain_block(&d, now + (uint64_t)i * (TB / 4096u));
    eqi(d.sec[0], 4096, "the first second counted every AUDIO block");
    eqi(d.secs_used, 1, "and only the first second was touched");
    eqi((long)d.blocks_in, 4096, "the total agrees");

    /* the second second, one block short */
    for (i = 0u; i < 4095u; i++)
        gbp_adrain_block(&d, now + TB + (uint64_t)i * (TB / 4096u));
    eqi(d.sec[1], 4095, "a short second is short in the counter");
    eqi(d.secs_used, 2, "two seconds touched");

    /* failures are a DIFFERENT field and never touch coverage (§V19.2) */
    gbp_adrain_failure(&d);
    gbp_adrain_failure(&d);
    eqi(d.failures, 2, "failures counted");
    eqi(d.sec[0], 4096, "and coverage is untouched by them");
    eqi((long)d.blocks_in, 4096 + 4095, "as is the block total");
}

static void test_a_block_past_the_array_is_counted_not_dropped(void)
{
    struct gbp_adrain d;
    uint64_t now = 0u;
    to_phase_b(&d, &now);
    gbp_adrain_block(&d, (uint64_t)GBP_ADRAIN_MAX_SECONDS * TB);
    eqi(d.sec_overflow, 1, "a block past the counter's end is counted as overflow");
    eqi((long)d.blocks_in, 1, "and still counted in the total");
    gbp_adrain_block(&d, TB);
    eqi(d.sec[1], 1, "while a block inside the array lands in its second");
}

static void test_blocks_before_phase_b_are_not_in_the_windows(void)
{
    struct gbp_adrain d;
    gbp_adrain_init(&d, TB);
    gbp_adrain_block(&d, 0u);                    /* at the prompt */
    eqi((long)d.blocks_in, 1, "counted in the total");
    eqi(d.secs_used, 0, "but in no window: D1 is a PHASE B question");
}

static void test_no_recovery_voids_the_run(void)
{
    struct gbp_adrain d;
    uint64_t now = 0u;
    to_phase_b(&d, &now);
    gbp_adrain_sync_lost(&d, 0);
    eqi(d.phase, GBP_ADRAIN_VOID, "no recovery voids the remaining phases");
    eqi(d.sync_lost, 1, "and it is recorded");
    gbp_adrain_step(&d, 999ull * TB, 1);
    eqi(d.phase, GBP_ADRAIN_VOID, "a void run does not step on");

    to_phase_b(&d, &now);
    gbp_adrain_sync_lost(&d, 1);
    eqi(d.phase, GBP_ADRAIN_DONE, "recovery ends the run normally");
    eqi(d.recovered, 1, "and says so");
}

int main(void)
{
    test_the_frozen_sweep();
    test_the_short_read_sample();
    test_the_phase_order();
    test_a_silent_run_never_reaches_phase_a();
    test_the_first_control_does_not_void_the_run();
    test_the_coverage_counter();
    test_a_block_past_the_array_is_counted_not_dropped();
    test_blocks_before_phase_b_are_not_in_the_windows();
    test_no_recovery_voids_the_run();
    printf("test_gbp_adrain: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
