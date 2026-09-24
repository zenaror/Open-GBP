/*
 * tests/unit/test_gbp_alive.c — Phase 6's acceptance run, the accounting half, with
 * no device (GitHub Issue #92, §V22, §V22.8, §V22.9 A3).
 *
 * The cases that matter are the ones a run can actually take: a pass before the
 * accept instant, a control that never passes, an A before the prompt, a second
 * button inside the window, X after it, a second with no blocks at all, and L on a
 * tone whose samples sit exactly at rest.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_alive.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

#define TB 40500000ull

static void test_period_reader(void)
{
    struct gbp_alive_period p;
    uint32_t k;
    gbp_alive_period_reset(&p, 32u);
    for (k = 0; k < 32u * 10u; k++) gbp_alive_period_feed(&p, (int16_t)((k % 32u) >= 16u ? 8000 : -8000));
    eqi(p.edges, 10, "a 32-period square: one rising edge per period");
    eqi(p.periods, 9, "periods are counted between two edges");
    eqi(p.pmin, 32, "pmin"); eqi(p.pmax, 32, "pmax"); eqi(p.off, 0, "off");
    /* a sample exactly at rest is NOT above it: prev <= 0 < cur */
    gbp_alive_period_reset(&p, 32u);
    gbp_alive_period_feed(&p, 0); gbp_alive_period_feed(&p, 0); gbp_alive_period_feed(&p, 1);
    eqi(p.edges, 1, "0 -> 0 -> 1: one edge, at the 1");
    /* the first sample after a reset opens nothing */
    gbp_alive_period_reset(&p, 32u);
    gbp_alive_period_feed(&p, 5);
    eqi(p.edges, 0, "no edge on the first sample");
    /* one duplicate makes one period 33 -- why L reads before the corrections (§V22.8 (e)) */
    gbp_alive_period_reset(&p, 32u);
    for (k = 0; k < 32u * 4u; k++) {
        const int16_t s = (int16_t)((k % 32u) >= 16u ? 8000 : -8000);
        gbp_alive_period_feed(&p, s);
        if (k == 40u) gbp_alive_period_feed(&p, s);
    }
    eqi(p.pmax, 33, "a duplicated sample inside a period makes it 33");
}

static void run_to_window(struct gbp_alive *a, uint64_t *t)
{
    uint64_t k;
    gbp_alive_init(a, (uint32_t)TB);
    gbp_alive_start(a, 1000u);
    *t = 1000u;
    gbp_alive_buttons(a, *t, 0u);
    /* 2 s of nothing, then the calibration second */
    for (k = 0; k < 4096u * 3u; k++) { *t += TB / 4096u; (void)gbp_alive_block(a, *t, 0u); }
    eqi(a->phase, GBP_ALIVE_PROMPT, "the calibration second ends at the prompt");
    eqi(a->calib_blocks, 4096, "one second of calibration blocks");
    *t += TB * 3u;                                           /* past the accept instant */
    gbp_alive_buttons(a, *t, GBP_ALIVE_PAD_A);
    gbp_alive_buttons(a, *t + 1000u, 0u);
    eqi(a->phase, GBP_ALIVE_CONTROL, "the A press starts the control");
    *t += TB / 2u;
    gbp_alive_control_window(a, *t, 1, 63u, 32u, 32u, 2048u);
    eqi(a->phase, GBP_ALIVE_WINDOW, "a passing control opens C's window");
}

static void test_the_happy_run(void)
{
    struct gbp_alive a;
    uint64_t t, origin, k;
    uint32_t s;
    run_to_window(&a, &t);
    origin = a.t_origin;
    eqi((long long)a.t_end, (long long)(origin + 64u * TB), "the window is 64 s from the origin");
    for (k = 1; ; k++) {
        const uint64_t tk = origin + k * (TB / 4096u);
        int r = gbp_alive_block(&a, tk, 2048u);
        if (r == GBP_ALIVE_DO_DECODE) gbp_alive_decoded(&a, (int16_t)((k % 32u) >= 16u ? 7000 : -7000));
        if (gbp_alive_finished(&a)) break;
    }
    eqi(a.phase, GBP_ALIVE_DONE, "the window closes");
    eqi(a.secs_used, 64, "64 whole windows");
    for (s = 0; s < 64u; s++) {
        if (a.sec[s] < 4095u || a.sec[s] > 4097u) { eqi(a.sec[s], 4096, "a window's count"); break; }
    }
    eqi(a.fill[10], 2048, "the fill series is recorded as each window begins");
    eqi(a.l.pmin, 32, "L pmin"); eqi(a.l.pmax, 32, "L pmax");
    eqi(a.presses_a, 1, "one A"); eqi(a.presses_other, 0, "nothing else");
    gbp_alive_buttons(&a, t + 100u * TB, 0x0400u);           /* X, after the window */
    eqi(a.presses_after, 1, "X after the window is counted apart");
    eqi(a.presses_other, 0, "and does not spoil the run");
}

static void test_a_press_inside_the_window_is_recorded(void)
{
    struct gbp_alive a;
    uint64_t t;
    run_to_window(&a, &t);
    gbp_alive_buttons(&a, t + TB, 0x0400u);                  /* X inside the window (§V22.9 A3) */
    gbp_alive_buttons(&a, t + TB + 10u, 0u);
    gbp_alive_buttons(&a, t + 2u * TB, GBP_ALIVE_PAD_A | 0x0200u);   /* A and B together */
    eqi(a.presses_other, 2, "X, then B: two other presses inside the window");
    eqi(a.presses_a, 2, "a second A is counted");
}

static void test_the_control_bounds(void)
{
    struct gbp_alive a;
    uint64_t t, k;
    gbp_alive_init(&a, (uint32_t)TB);
    gbp_alive_start(&a, 1000u);
    t = 1000u;
    for (k = 0; k < 4096u * 3u; k++) { t += TB / 4096u; (void)gbp_alive_block(&a, t, 0u); }
    gbp_alive_buttons(&a, t, GBP_ALIVE_PAD_A);                /* before the accept instant (5 s) */
    gbp_alive_control_window(&a, t + TB / 2u, 1, 63u, 32u, 32u, 2048u);
    eqi(a.control_early, 1, "A4.5: a pass before the accept instant does not count");
    eqi(a.phase, GBP_ALIVE_CONTROL, "and the control goes on");
    gbp_alive_control_window(&a, t + 9u * TB, 0, 20u, 31u, 33u, 2048u);
    eqi(a.phase, GBP_ALIVE_CONTROL, "9 s after the press: still trying");
    gbp_alive_control_window(&a, t + 10u * TB, 0, 20u, 31u, 33u, 2048u);
    eqi(a.phase, GBP_ALIVE_GAVE_UP, "A4.7: 10 s after the press it gives up");
    eqi(a.control_gave_up, 1, "gave_up");
    eqi(gbp_alive_finished(&a), 1, "and the session may end");
}

static void test_an_A_before_the_prompt(void)
{
    struct gbp_alive a;
    uint64_t t, k;
    gbp_alive_init(&a, (uint32_t)TB);
    gbp_alive_start(&a, 1000u);
    t = 1000u;
    gbp_alive_buttons(&a, t + TB, GBP_ALIVE_PAD_A);          /* during the first second */
    for (k = 0; k < 4096u * 3u; k++) { t += TB / 4096u; (void)gbp_alive_block(&a, t, 0u); }
    eqi(a.phase, GBP_ALIVE_CONTROL, "calibration ends straight into the control");
    eqi(a.press_before_prompt, 1, "and says the A came before the prompt");
}

static void test_a_second_with_no_blocks(void)
{
    struct gbp_alive a;
    uint64_t t;
    run_to_window(&a, &t);
    (void)gbp_alive_block(&a, a.t_origin + 10u, 100u);
    (void)gbp_alive_block(&a, a.t_origin + 3u * TB + 10u, 300u);     /* seconds 1 and 2 had nothing */
    eqi(a.secs_used, 4, "the windows in between exist");
    eqi(a.sec[1], 0, "an empty second is a 0, not a missing one");
    eqi(a.fill[3], 300, "and the fill is the one seen when the next block came");
}

int main(void)
{
    test_period_reader();
    test_the_happy_run();
    test_a_press_inside_the_window_is_recorded();
    test_the_control_bounds();
    test_an_A_before_the_prompt();
    test_a_second_with_no_blocks();
    printf("test_gbp_alive: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
