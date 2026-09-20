/*
 * test_gbp_startup.c — the startup PROFILE, which decides what a user sees
 * before the Game Boy Player's own video does (HARDWARE_TESTS §V5.52).
 *
 * The profile is one pure function, so it can be tested exhaustively rather
 * than argued about. What it must guarantee:
 *
 *   NORMAL      nothing synthetic reaches the video interface, nothing waits
 *               for seconds, and the framebuffers are cleared first
 *   DIAGNOSTIC  both of those are available, so GBP-HW-120's 5000 ms run and
 *               every visible-self-test experiment stay reproducible
 *   EITHER WAY  the display path is still exercised -- the reason the
 *               self-test exists is that `stream-0001` shipped a display path
 *               that had never once run
 *
 * The failure mode this file exists to prevent is a build that is diagnostic in
 * one respect and normal in another, with nothing detecting it.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_startup.h"

static int checks, failures;
#define CHECK(c) do { checks++; if (!(c)) { failures++; \
    printf("  FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static void test_A_the_normal_profile(void)
{
    struct gbp_startup s;
    printf("-- A: NORMAL shows the user nothing synthetic and waits for nothing\n");
    memset(&s, 0xAA, sizeof s);
    gbp_startup_profile(&s, GBP_STARTUP_NORMAL);
    CHECK(s.mode == (uint8_t)GBP_STARTUP_NORMAL);
    CHECK(s.selftest_visible == 0u);       /* the whole point */
    CHECK(s.prehandler_wait_ms == 0u);     /* the other whole point */
    CHECK(s.clear_framebuffers == 1u);     /* black, never uninitialised memory */
    CHECK(s.selftest_run == 1u);           /* the path is still validated */
    CHECK(gbp_startup_is_normal_clean(&s) == 1);
    CHECK(strcmp(gbp_startup_mode_name(&s), "normal") == 0);
}

static void test_B_the_diagnostic_profile(void)
{
    struct gbp_startup s;
    printf("-- B: DIAGNOSTIC keeps every historical experiment reproducible\n");
    memset(&s, 0x55, sizeof s);
    gbp_startup_profile(&s, GBP_STARTUP_DIAGNOSTIC);
    CHECK(s.mode == (uint8_t)GBP_STARTUP_DIAGNOSTIC);
    CHECK(s.selftest_visible == 1u);
    CHECK(s.prehandler_wait_ms == GBP_STARTUP_DIAGNOSTIC_WAIT_MS);
    CHECK(s.prehandler_wait_ms == 5000u);  /* the value GBP-HW-120 validated */
    CHECK(s.clear_framebuffers == 1u);     /* garbage helps no one */
    CHECK(s.selftest_run == 1u);
    CHECK(gbp_startup_is_normal_clean(&s) == 0);
    CHECK(strcmp(gbp_startup_mode_name(&s), "diagnostic") == 0);
}

static void test_C_the_two_profiles_are_distinguishable(void)
{
    struct gbp_startup n, d;
    printf("-- C: the profiles differ in exactly the two things they should\n");
    gbp_startup_profile(&n, GBP_STARTUP_NORMAL);
    gbp_startup_profile(&d, GBP_STARTUP_DIAGNOSTIC);
    CHECK(memcmp(&n, &d, sizeof n) != 0);
    CHECK(n.selftest_visible != d.selftest_visible);
    CHECK(n.prehandler_wait_ms != d.prehandler_wait_ms);
    /* and in NOTHING else: a future field that silently differs would make the
     * normal path diverge from the diagnostic one without anyone deciding to */
    CHECK(n.selftest_run == d.selftest_run);
    CHECK(n.clear_framebuffers == d.clear_framebuffers);
}

static void test_D_an_unknown_mode_fails_towards_the_user(void)
{
    struct gbp_startup s;
    int m;
    printf("-- D: a typo shows no test pattern and causes no five-second pause\n");
    for (m = -3; m < 8; m++) {
        if (m == (int)GBP_STARTUP_DIAGNOSTIC) continue;
        gbp_startup_profile(&s, m);
        CHECK(s.mode == (uint8_t)GBP_STARTUP_NORMAL);
        CHECK(s.selftest_visible == 0u);
        CHECK(s.prehandler_wait_ms == 0u);
        CHECK(gbp_startup_is_normal_clean(&s) == 1);
    }
}

static void test_E_the_predicate_refuses_a_hand_edited_profile(void)
{
    struct gbp_startup s;
    printf("-- E: normal_clean is a TEST, not a restatement of the mode field\n");
    gbp_startup_profile(&s, GBP_STARTUP_NORMAL);
    CHECK(gbp_startup_is_normal_clean(&s) == 1);
    s.selftest_visible = 1u;
    CHECK(gbp_startup_is_normal_clean(&s) == 0);

    gbp_startup_profile(&s, GBP_STARTUP_NORMAL);
    s.prehandler_wait_ms = 1u;             /* ONE millisecond is already wrong */
    CHECK(gbp_startup_is_normal_clean(&s) == 0);

    gbp_startup_profile(&s, GBP_STARTUP_NORMAL);
    s.clear_framebuffers = 0u;
    CHECK(gbp_startup_is_normal_clean(&s) == 0);

    gbp_startup_profile(&s, GBP_STARTUP_NORMAL);
    s.mode = (uint8_t)GBP_STARTUP_DIAGNOSTIC;
    CHECK(gbp_startup_is_normal_clean(&s) == 0);
}

static void test_F_null_is_survivable(void)
{
    printf("-- F: no call here may fault on a null profile\n");
    gbp_startup_profile(0, GBP_STARTUP_NORMAL);
    CHECK(gbp_startup_is_normal_clean(0) == 0);
    CHECK(strcmp(gbp_startup_mode_name(0), "?") == 0);
}

int main(void)
{
    printf("== test_gbp_startup (the startup profile; every case SYNTHETIC)\n");
    test_A_the_normal_profile();
    test_B_the_diagnostic_profile();
    test_C_the_two_profiles_are_distinguishable();
    test_D_an_unknown_mode_fails_towards_the_user();
    test_E_the_predicate_refuses_a_hand_edited_profile();
    test_F_null_is_survivable();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
