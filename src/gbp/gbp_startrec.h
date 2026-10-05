/*
 * gbp_startrec -- the startup-profile and Policy A records of the GBA play image vehicle-0002 (GitHub Issue #158; HARDWARE_TESTS.md V31.12's
 * recommendation (a) and (b)): STARTUP, STARTUPT, STARTUPV, STREAMINV and STREAMSELFTEST, in the format the ten POCs that write them inline
 * already use (eight gbp-audio-* images, gbp-play-session, gbp-video-stream-probe; nearest source poc/gbp-audio-game2/source/main.c), so every
 * existing reading of those records applies unchanged.
 *
 * THE LITERALS AND THE CASTS ARE THE TEN COPIES' (tests/host/test_play_gba2_image.py extracts them from each main.c and compares). STARTUPV
 * takes the NINE-copy shape (no `t_drawdone`): a first-draw-done instant would need an instruction in the draw-done handler, which the vehicle's
 * hot path must not gain. `ticks_control_to_first_handoff` is computed as the copies do: `(have && t_decision > t_control) ? t_decision -
 * t_control : 0`, and every instant of the record is 0 when `have` is 0.
 *
 * Pure: plain values in, no struct, no device, no clock; each function writes ONE record into the caller's buffer and returns the snprintf
 * count. The object references nothing but snprintf (tools/poc_audit.py profile vehicle2 pins it). The vehicle writes them at TEARDOWN only,
 * from main(), after the probe has returned and the draw-done callback is restored.
 */
#ifndef OPENGBP_GBP_STARTREC_H
#define OPENGBP_GBP_STARTREC_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* STARTUP mode=<name> selftest_run=<d> selftest_visible=<d> prehandler_wait_ms=<lu> clear_fb=<d> normal_clean=<d> presented_synthetic=<lu> headless_submits=<lu> */
int gbp_startrec_startup(char *out, size_t cap, const char *mode, int selftest_run, int selftest_visible, uint32_t prehandler_wait_ms,
                         int clear_fb, int normal_clean, uint32_t presented_synthetic, uint32_t headless_submits);

/* STARTUPT tb_hz=<lu> t_program=<llx> t_video=<llx> t_selftest_begin=<llx> t_selftest_end=<llx> t_probe_enter=<llx> t_control=<llx> t_capture_start=<llx> */
int gbp_startrec_startupt(char *out, size_t cap, uint32_t tb_hz, uint64_t t_program, uint64_t t_video, uint64_t t_selftest_begin,
                          uint64_t t_selftest_end, uint64_t t_probe_enter, uint64_t t_control, uint64_t t_capture_start);

/* STARTUPV have_first=<d> first_frame_index=<lu> t_take=<llx> t_convert_done=<llx> t_decision=<llx> ticks_control_to_first_handoff=<llu> */
int gbp_startrec_startupv(char *out, size_t cap, int have, uint32_t frame_index, uint64_t t_take, uint64_t t_convert_done,
                          uint64_t t_decision, uint64_t t_control);

/* STREAMINV checks=<lu> failures=<lu> main=<failures>/<checks> isr=<failures>/<checks> consistent_at_end=<d> */
int gbp_startrec_streaminv(char *out, size_t cap, uint32_t checks, uint32_t failures, uint32_t main_failures, uint32_t main_checks,
                           uint32_t isr_failures, uint32_t isr_checks, int consistent_at_end);

/* STREAMSELFTEST ok=<d> converted=<d> released=<d> own_presents=<lu> own_repeats=<lu> sci_clean=<d> note=... */
int gbp_startrec_streamselftest(char *out, size_t cap, int ok, int converted, int released, uint32_t own_presents, uint32_t own_repeats,
                                int sci_clean);

#ifdef __cplusplus
}
#endif
#endif
