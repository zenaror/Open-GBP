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

/* ---- Issue #110 (§V25.7 2(a), (r1)): the press origin, no positive control ---- */

static void calibrate_press_origin(struct gbp_alive *a, uint64_t *t, uint32_t delay_ms)
{
    uint64_t k;
    gbp_alive_init(a, (uint32_t)TB);
    gbp_alive_use_press_origin(a, delay_ms);
    gbp_alive_start(a, 1000u);
    *t = 1000u;
    gbp_alive_buttons(a, *t, 0u);
    for (k = 0; k < 4096u * 3u; k++) { *t += TB / 4096u; (void)gbp_alive_block(a, *t, 0u); }
}

static void test_the_press_origin(void)
{
    struct gbp_alive a;
    uint64_t t, t_press, k, first_decoded = 0;
    int r;
    calibrate_press_origin(&a, &t, 1000u);
    eqi(a.phase, GBP_ALIVE_PROMPT, "press origin: calibration still ends at the prompt");
    t += TB * 3u;
    t_press = t;
    gbp_alive_buttons(&a, t, GBP_ALIVE_PAD_A);
    gbp_alive_buttons(&a, t + 1000u, 0u);
    eqi(a.phase, GBP_ALIVE_DELAY, "the A starts the delay, not the control");
    eqi((long long)a.t_delay_end, (long long)(t_press + TB), "the delay is 1.000 s from the press");
    /* blocks every 1/4096 s from the press: none is decoded before press + 1 s */
    for (k = 1; ; k++) {
        const uint64_t tk = t_press + k * (TB / 4096u);
        r = gbp_alive_block(&a, tk, 7u);
        if (r == GBP_ALIVE_DO_CONTROL) { eqi(r, GBP_ALIVE_DO_NOTHING, "no control block, ever"); break; }
        if (r == GBP_ALIVE_DO_DECODE) { first_decoded = tk; break; }
        if (tk >= t_press + TB) { eqi(r, GBP_ALIVE_DO_DECODE, "the first block past the delay decodes"); break; }
    }
    eqi(first_decoded >= t_press + TB, 1, "the first decoded block is at or after press + 1 s");
    eqi(first_decoded < t_press + TB + TB / 4096u + 1u, 1, "and it is the FIRST such block");
    eqi((long long)a.t_origin, (long long)first_decoded, "the ORIGIN is that block's own tick");
    eqi(a.phase, GBP_ALIVE_WINDOW, "the window is open");
    eqi(a.sec[0], 1, "and the origin block is the window's first");
    eqi(a.fill[0], 7, "its fill opens the series");
    eqi((long long)a.t_end, (long long)(first_decoded + 64u * TB), "the window is 64 s");
    eqi(a.control_windows, 0, "no control window ran");
    for (k = 1; ; k++) {
        r = gbp_alive_block(&a, first_decoded + k * (TB / 4096u), 2048u);
        if (gbp_alive_finished(&a)) break;
    }
    eqi(a.phase, GBP_ALIVE_DONE, "the window closes");
    eqi(a.secs_used, 64, "64 whole windows");
}

static void test_the_press_origin_counts_every_press(void)
{
    struct gbp_alive a;
    uint64_t t;
    calibrate_press_origin(&a, &t, 1000u);
    t += TB * 3u;
    gbp_alive_buttons(&a, t, GBP_ALIVE_PAD_A);
    gbp_alive_buttons(&a, t + 10u, 0u);
    gbp_alive_buttons(&a, t + TB / 4u, GBP_ALIVE_PAD_A);      /* a second A, inside the delay */
    gbp_alive_buttons(&a, t + TB / 4u + 10u, 0x0200u);         /* then B */
    eqi(a.phase, GBP_ALIVE_DELAY, "a second A does not restart anything");
    eqi((long long)a.t_delay_end, (long long)(t + TB), "the delay runs from the FIRST A");
    eqi(a.presses_a, 2, "both As counted"); eqi(a.presses_other, 1, "B counted");
}

static void test_the_press_origin_after_an_early_A(void)
{
    struct gbp_alive a;
    uint64_t t, k, t_span_end;
    int r = GBP_ALIVE_DO_NOTHING;
    gbp_alive_init(&a, (uint32_t)TB);
    gbp_alive_use_press_origin(&a, 1000u);
    gbp_alive_start(&a, 1000u);
    t = 1000u;
    gbp_alive_buttons(&a, t + TB, GBP_ALIVE_PAD_A);          /* at 1 s: before the span (2 s .. 3 s) */
    for (k = 0; k < 4096u * 3u; k++) { t += TB / 4096u; r = gbp_alive_block(&a, t, 0u); }
    t_span_end = t;
    eqi(r, GBP_ALIVE_DO_CALIBRATE, "the span is calibrated whatever the press");
    eqi(a.calib_blocks, 4096, "the whole span");
    eqi(a.phase, GBP_ALIVE_DELAY, "then straight into the delay");
    eqi(a.press_before_prompt, 1, "and it says the A came before the prompt");
    /* press + 1 s (= 2 s) is long past: the first block after the span opens the window */
    r = gbp_alive_block(&a, t_span_end + TB / 4096u, 5u);
    eqi(r, GBP_ALIVE_DO_DECODE, "the first block after the span is the window's first");
    eqi((long long)a.t_origin, (long long)(t_span_end + TB / 4096u), "the later of press + D and the span's end");
}

static void test_the_call_is_ignored_once_the_run_has_started(void)
{
    struct gbp_alive a;
    gbp_alive_init(&a, (uint32_t)TB);
    gbp_alive_start(&a, 1000u);
    gbp_alive_use_press_origin(&a, 1000u);
    eqi(a.press_origin, 0, "after start: no effect, the control path stands");
    eqi(strcmp(gbp_alive_phase_name(GBP_ALIVE_DELAY), "delay") == 0, 1, "the phase's name");
    eqi(GBP_ALIVE_GAVE_UP, 5, "no earlier phase value moved");
}

int main(void)
{
    test_the_press_origin();
    test_the_press_origin_counts_every_press();
    test_the_press_origin_after_an_early_A();
    test_the_call_is_ignored_once_the_run_has_started();
    test_period_reader();
    test_the_happy_run();
    test_a_press_inside_the_window_is_recorded();
    test_the_control_bounds();
    test_an_A_before_the_prompt();
    test_a_second_with_no_blocks();
    printf("test_gbp_alive: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
