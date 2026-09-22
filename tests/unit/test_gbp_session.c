/*
 * test_gbp_session.c — Issue #39: the operator's session end (src/gbp/gbp_session).
 * Pure state machine, synthetic instants. Nothing here is physical evidence.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_session.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static void test_init(void)
{
    struct gbp_session s;
    memset(&s, 0xA5, sizeof s);
    gbp_session_init(&s, 1000u);
    CHECK(s.hold_ticks == 1000u);
    CHECK(s.end_requested == 0 && s.holding == 0);
    CHECK(s.samples == 0u && s.samples_held == 0u && s.holds_begun == 0u && s.holds_released == 0u && s.samples_after == 0u);
    CHECK(s.t_hold_begin == 0u && s.t_requested == 0u);
}

static void test_released_samples_do_nothing(void)
{
    struct gbp_session s;
    uint64_t now;
    gbp_session_init(&s, 1000u);
    for (now = 0; now < 5000u; now += 100u) CHECK(gbp_session_sample(&s, 0, now) == 0);
    CHECK(s.samples == 50u && s.samples_held == 0u && s.holds_begun == 0u && s.end_requested == 0);
}

static void test_a_tap_is_released_before_the_bound(void)
{
    struct gbp_session s;
    gbp_session_init(&s, 1000u);
    CHECK(gbp_session_sample(&s, 1, 100u) == 0);      /* the hold begins */
    CHECK(s.holding == 1 && s.holds_begun == 1u && s.t_hold_begin == 100u);
    CHECK(gbp_session_sample(&s, 1, 600u) == 0);      /* 500 < 1000 */
    CHECK(gbp_session_sample(&s, 1, 1099u) == 0);     /* 999 < 1000 */
    CHECK(gbp_session_sample(&s, 0, 1100u) == 0);     /* released: a tap */
    CHECK(s.holding == 0 && s.holds_released == 1u && s.end_requested == 0);
    CHECK(s.samples == 4u && s.samples_held == 3u);
    /* a second hold starts from its own instant, not from the first one's */
    CHECK(gbp_session_sample(&s, 1, 1200u) == 0);
    CHECK(s.holds_begun == 2u && s.t_hold_begin == 1200u);
    CHECK(gbp_session_sample(&s, 1, 2100u) == 0);     /* 900 since 1200: not yet */
    CHECK(s.end_requested == 0);
}

static void test_a_hold_reaching_the_bound_requests_once(void)
{
    struct gbp_session s;
    gbp_session_init(&s, 1000u);
    CHECK(gbp_session_sample(&s, 1, 5000u) == 0);
    CHECK(gbp_session_sample(&s, 1, 5999u) == 0);
    CHECK(gbp_session_sample(&s, 1, 6000u) == 1);     /* exactly the bound: >= */
    CHECK(s.end_requested == 1 && s.t_requested == 6000u);
    /* latched: later samples, held or not, return 0 and are counted apart */
    CHECK(gbp_session_sample(&s, 1, 6100u) == 0);
    CHECK(gbp_session_sample(&s, 0, 6200u) == 0);
    CHECK(gbp_session_sample(&s, 1, 9000u) == 0);
    CHECK(s.end_requested == 1 && s.t_requested == 6000u);
    CHECK(s.samples_after == 3u && s.samples == 6u && s.samples_held == 3u);
    CHECK(s.holds_released == 0u && s.holds_begun == 1u);
}

static void test_zero_bound_requests_on_the_first_held_sample(void)
{
    struct gbp_session s;
    gbp_session_init(&s, 0u);
    CHECK(gbp_session_sample(&s, 0, 10u) == 0);
    CHECK(gbp_session_sample(&s, 1, 20u) == 1);
    CHECK(s.end_requested == 1 && s.t_requested == 20u && s.holds_begun == 1u);
}

static void test_the_clock_may_sit_high(void)
{
    /* the caller's instants are absolute 64-bit ticks; only differences matter */
    struct gbp_session s;
    const uint64_t base = 0xFFFFFFFF00000000ull;
    gbp_session_init(&s, (40500000ull * 250ull) / 1000ull);   /* 250 ms at 40.5 MHz = 10 125 000 ticks; 64-bit, as the POC computes it */
    CHECK(gbp_session_sample(&s, 1, base) == 0);
    CHECK(gbp_session_sample(&s, 1, base + 10124999u) == 0);
    CHECK(gbp_session_sample(&s, 1, base + 10125000u) == 1);
}

int main(void)
{
    printf("== test_gbp_session (Issue #39: the operator's session end; synthetic)\n");
    test_init();
    test_released_samples_do_nothing();
    test_a_tap_is_released_before_the_bound();
    test_a_hold_reaching_the_bound_requests_once();
    test_zero_bound_requests_on_the_first_held_sample();
    test_the_clock_may_sit_high();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
