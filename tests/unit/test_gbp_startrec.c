/*
 * tests/unit/test_gbp_startrec.c -- GitHub Issue #158: src/gbp/gbp_startrec, the five records vehicle-0002 writes at teardown (STARTUP, STARTUPT,
 * STARTUPV, STREAMINV, STREAMSELFTEST) in the ten inline copies' format.
 *
 * THE EXPECTED LINES BELOW ARE ALSO THE READER'S INPUT: tests/host/test_playread.py reads the five `EXPECT_*` literals out of THIS file and feeds
 * them to tools/playread.py as a vehicle-0002 log, so the writer and the reader are held to one source of truth. Keep each on one line.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "gbp_startrec.h"

/* a clean normal-profile session: realistic values (RUN 17's first-handoff ticks, HARDWARE_TESTS.md:23470; RUN 17's STREAMINV totals, :24706) */
static const char *const EXPECT_STARTUP = "STARTUP mode=normal selftest_run=1 selftest_visible=0 prehandler_wait_ms=0 clear_fb=1 normal_clean=1 presented_synthetic=0 headless_submits=1";
static const char *const EXPECT_STARTUPT = "STARTUPT tb_hz=40500000 t_program=1a2b3c t_video=2b3c4d t_selftest_begin=3c4d5e t_selftest_end=4d5e6f t_probe_enter=5e6f70 t_control=6f7081 t_capture_start=708192";
static const char *const EXPECT_STARTUPV = "STARTUPV have_first=1 first_frame_index=3 t_take=c8a1b2 t_convert_done=c9b2c3 t_decision=cac3d4 ticks_control_to_first_handoff=6696114";
static const char *const EXPECT_STREAMINV = "STREAMINV checks=189258 failures=0 main=0/186880 isr=0/2378 consistent_at_end=1";
static const char *const EXPECT_STREAMSELFTEST = "STREAMSELFTEST ok=1 converted=1 released=1 own_presents=0 own_repeats=0 sci_clean=1 note=synthetic_frame_before_capture_no_device_counters_isolated";

#define LINE_PAYLOAD_MAX 248u      /* LOG_LINE_LEN 256 less the "%06u " prefix and the NUL (src/log/ringlog.c) */

static int checks, failures;

static void eqs(const char *got, const char *want, const char *what)
{
    checks++;
    if (strcmp(got, want) != 0) { failures++; printf("  FAIL: %s:\n    got  %s\n    want %s\n", what, got, want); }
}

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) { failures++; printf("  FAIL: %s: got %lld, want %lld\n", what, got, want); }
}

static void check(int cond, const char *what)
{
    checks++;
    if (!cond) { failures++; printf("  FAIL: %s\n", what); }
}

static void test_the_clean_session(void)
{
    char b[256];
    const uint64_t t_control = 0x6f7081u;
    int n;
    n = gbp_startrec_startup(b, sizeof b, "normal", 1, 0, 0u, 1, 1, 0u, 1u);
    eqs(b, EXPECT_STARTUP, "STARTUP");
    eqi(n, (long long)strlen(EXPECT_STARTUP), "the snprintf count");
    gbp_startrec_startupt(b, sizeof b, 40500000u, 0x1a2b3cu, 0x2b3c4du, 0x3c4d5eu, 0x4d5e6fu, 0x5e6f70u, t_control, 0x708192u);
    eqs(b, EXPECT_STARTUPT, "STARTUPT");
    gbp_startrec_startupv(b, sizeof b, 1, 3u, 0xc8a1b2u, 0xc9b2c3u, 0xcac3d4u, 0xcac3d4u - 6696114u);
    eqs(b, EXPECT_STARTUPV, "STARTUPV: ticks = t_decision - t_control");
    gbp_startrec_streaminv(b, sizeof b, 189258u, 0u, 0u, 186880u, 0u, 2378u, 1);
    eqs(b, EXPECT_STREAMINV, "STREAMINV: main= and isr= are failures/checks");
    gbp_startrec_streamselftest(b, sizeof b, 1, 1, 1, 0u, 0u, 1);
    eqs(b, EXPECT_STREAMSELFTEST, "STREAMSELFTEST");
}

static void test_startupv_rules(void)
{
    char b[256];
    gbp_startrec_startupv(b, sizeof b, 0, 7u, 0x10u, 0x20u, 0x30u, 0x5u);
    eqs(b, "STARTUPV have_first=0 first_frame_index=0 t_take=0 t_convert_done=0 t_decision=0 ticks_control_to_first_handoff=0",
        "no first hand-off: every instant 0, whatever the arguments");
    gbp_startrec_startupv(b, sizeof b, 1, 1u, 0x10u, 0x20u, 0x30u, 0x30u);
    eqs(b, "STARTUPV have_first=1 first_frame_index=1 t_take=10 t_convert_done=20 t_decision=30 ticks_control_to_first_handoff=0",
        "t_decision == t_control: 0, never a wrap");
    gbp_startrec_startupv(b, sizeof b, 1, 1u, 0x10u, 0x20u, 0x30u, 0x40u);
    eqs(b, "STARTUPV have_first=1 first_frame_index=1 t_take=10 t_convert_done=20 t_decision=30 ticks_control_to_first_handoff=0",
        "t_decision before t_control: 0, never a wrap");
    gbp_startrec_startupv(b, sizeof b, 1, 2u, 0u, 0u, 16200000u + 100u, 100u);
    check(strstr(b, "ticks_control_to_first_handoff=16200000") != NULL, "the 400 ms bound at 40.5 MHz, exact");
}

static void test_the_worst_case_fits_the_line(void)
{
    char b[512];
    size_t n;
    n = (size_t)gbp_startrec_startup(b, sizeof b, "diagnostic", -2147483647 - 1, -2147483647 - 1, UINT32_MAX, -2147483647 - 1,
                                     -2147483647 - 1, UINT32_MAX, UINT32_MAX);
    printf("  STARTUP worst %zu\n", n);
    eqi((long long)n, 212, "STARTUP worst case (mode=diagnostic, every %d at 11, every %lu at 10)");
    n = (size_t)gbp_startrec_startupt(b, sizeof b, UINT32_MAX, UINT64_MAX, UINT64_MAX, UINT64_MAX, UINT64_MAX, UINT64_MAX, UINT64_MAX, UINT64_MAX);
    printf("  STARTUPT worst %zu\n", n);
    eqi((long long)n, 234, "STARTUPT worst case (every %llx at 16)");
    n = (size_t)gbp_startrec_startupv(b, sizeof b, -2147483647 - 1, UINT32_MAX, UINT64_MAX, UINT64_MAX, UINT64_MAX, 0u);
    printf("  STARTUPV worst %zu\n", n);
    check(n <= 196u, "STARTUPV worst case at most 196 (its %llu cannot exceed t_decision, so 20 digits is the bound)");
    n = (size_t)gbp_startrec_streaminv(b, sizeof b, UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX, -2147483647 - 1);
    printf("  STREAMINV worst %zu\n", n);
    eqi((long long)n, 130, "STREAMINV worst case");
    n = (size_t)gbp_startrec_streamselftest(b, sizeof b, -2147483647 - 1, -2147483647 - 1, -2147483647 - 1, UINT32_MAX, UINT32_MAX, -2147483647 - 1);
    printf("  STREAMSELFTEST worst %zu\n", n);
    eqi((long long)n, 205, "STREAMSELFTEST worst case");
    check(234u < LINE_PAYLOAD_MAX, "the widest record (STARTUPT 234) is under the 248 the log line leaves");
}

static void test_truncation_is_reported_not_overrun(void)
{
    char b[16];
    int n;
    memset(b, 'X', sizeof b);
    n = gbp_startrec_streaminv(b, 10u, 1u, 0u, 0u, 1u, 0u, 0u, 1);
    check(n > 9, "the count is the full length, so a caller can see the truncation");
    eqi((long long)strlen(b), 9, "nine characters and the NUL inside the 10 given");
    check(b[10] == 'X', "nothing written past the given size");
}

int main(void)
{
    test_the_clean_session();
    test_startupv_rules();
    test_the_worst_case_fits_the_line();
    test_truncation_is_reported_not_overrun();
    printf("test_gbp_startrec: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
