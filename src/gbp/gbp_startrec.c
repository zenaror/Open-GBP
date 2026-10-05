#include "gbp_startrec.h"

#include <stdio.h>

int gbp_startrec_startup(char *out, size_t cap, const char *mode, int selftest_run, int selftest_visible, uint32_t prehandler_wait_ms,
                         int clear_fb, int normal_clean, uint32_t presented_synthetic, uint32_t headless_submits)
{
    return snprintf(out, cap, "STARTUP mode=%s selftest_run=%d selftest_visible=%d "
                              "prehandler_wait_ms=%lu clear_fb=%d normal_clean=%d "
                              "presented_synthetic=%lu headless_submits=%lu",
                    mode ? mode : "?", selftest_run, selftest_visible, (unsigned long)prehandler_wait_ms,
                    clear_fb, normal_clean, (unsigned long)presented_synthetic, (unsigned long)headless_submits);
}

int gbp_startrec_startupt(char *out, size_t cap, uint32_t tb_hz, uint64_t t_program, uint64_t t_video, uint64_t t_selftest_begin,
                          uint64_t t_selftest_end, uint64_t t_probe_enter, uint64_t t_control, uint64_t t_capture_start)
{
    return snprintf(out, cap, "STARTUPT tb_hz=%lu t_program=%llx t_video=%llx "
                              "t_selftest_begin=%llx t_selftest_end=%llx t_probe_enter=%llx "
                              "t_control=%llx t_capture_start=%llx",
                    (unsigned long)tb_hz, (unsigned long long)t_program, (unsigned long long)t_video,
                    (unsigned long long)t_selftest_begin, (unsigned long long)t_selftest_end,
                    (unsigned long long)t_probe_enter, (unsigned long long)t_control,
                    (unsigned long long)t_capture_start);
}

int gbp_startrec_startupv(char *out, size_t cap, int have, uint32_t frame_index, uint64_t t_take, uint64_t t_convert_done,
                          uint64_t t_decision, uint64_t t_control)
{
    /* ONE tag, ONE shape, always emitted; `have_first` is what a parser tests before reading the rest (the copies' own rule) */
    const uint64_t t_ho = have ? t_decision : 0u;
    return snprintf(out, cap, "STARTUPV have_first=%d first_frame_index=%lu t_take=%llx "
                              "t_convert_done=%llx t_decision=%llx "
                              "ticks_control_to_first_handoff=%llu",
                    have, (unsigned long)(have ? frame_index : 0u), (unsigned long long)(have ? t_take : 0u),
                    (unsigned long long)(have ? t_convert_done : 0u), (unsigned long long)t_ho,
                    (unsigned long long)((have && t_ho > t_control) ? t_ho - t_control : 0u));
}

int gbp_startrec_streaminv(char *out, size_t cap, uint32_t checks, uint32_t failures, uint32_t main_failures, uint32_t main_checks,
                           uint32_t isr_failures, uint32_t isr_checks, int consistent_at_end)
{
    return snprintf(out, cap, "STREAMINV checks=%lu failures=%lu main=%lu/%lu isr=%lu/%lu consistent_at_end=%d",
                    (unsigned long)checks, (unsigned long)failures, (unsigned long)main_failures, (unsigned long)main_checks,
                    (unsigned long)isr_failures, (unsigned long)isr_checks, consistent_at_end);
}

int gbp_startrec_streamselftest(char *out, size_t cap, int ok, int converted, int released, uint32_t own_presents, uint32_t own_repeats,
                                int sci_clean)
{
    return snprintf(out, cap, "STREAMSELFTEST ok=%d converted=%d released=%d own_presents=%lu own_repeats=%lu sci_clean=%d note=synthetic_frame_before_capture_no_device_counters_isolated",
                    ok, converted, released, (unsigned long)own_presents, (unsigned long)own_repeats, sci_clean);
}
