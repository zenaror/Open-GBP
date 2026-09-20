/*
 * gbp_startup.h — the ONE place that decides what the operator sees before the
 * Game Boy Player's own video reaches the screen (HARDWARE_TESTS §V5.52).
 *
 * WHY THIS IS A FILE AND NOT THREE `#ifdef`s IN main()
 *
 * Three independent switches decide the startup experience: whether the
 * synthetic self-test is HANDED to the video interface, whether the
 * pre-handler masked wait runs, and whether the framebuffers are cleared before
 * the interface is pointed at them. Scattered, they drift: a build can end up
 * diagnostic in one respect and normal in another, and nothing detects it. Here
 * they are ONE function of ONE enum, so "which startup is this build" has
 * exactly one answer and a test can ask it.
 *
 * WHAT THE PHYSICAL EVIDENCE SAYS, and why the normal profile looks like this
 *
 *   - The rainbow/checkerboard the operator sees is `display_selftest()`'s
 *     coordinate gradient, handed to the VI by the self-test's own present
 *     (GBP-VID-027). It is diagnostic GameCube output and never Game Boy video.
 *   - It holds the framebuffers for 5.1777 s in `stream-0008`, of which
 *     5.000 s is `prehandler_wait_ms` — a DIAGNOSTIC that the base API already
 *     defaults to OFF (`gbp_vstate_probe.c`, `cfg->prehandler_wait_ms = 0`).
 *   - The AGB is RUNNING throughout that wait: stage A has already put CONTROL
 *     in the running shape.
 *   - `vstate-0001`, with no wait, captured the animated GAME BOY logotype
 *     0.5014 s after capture start; `vstate-prewait-5000`, with the same 5 s
 *     wait, reported `STRUCTURED not_observed`. The boot happens inside the
 *     wait.
 *
 * So the wait is not a protocol requirement, and removing it from the normal
 * path is not a protocol change. It stays available, because the experiments
 * that needed it must remain reproducible (GBP-HW-120).
 *
 * WHAT THIS HEADER DOES NOT TOUCH
 *
 * Policy A, the source assembler, the qualification, the transport, the IRQ
 * ACK/REARM order, the XFB count and the texture count are all outside it. It
 * schedules the startup; it does not change the pipeline.
 */
#ifndef OPENGBP_GBP_STARTUP_H
#define OPENGBP_GBP_STARTUP_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum gbp_startup_mode {
    /* What a user gets. Nothing synthetic is ever handed to the video
     * interface, nothing waits for seconds, and the screen is black — not
     * uninitialised memory — until the Game Boy Player's own first frame. */
    GBP_STARTUP_NORMAL = 0,
    /* What an experiment gets. The visible self-test and the pre-handler masked
     * wait are both available, so every historical run remains reproducible. */
    GBP_STARTUP_DIAGNOSTIC = 1
};

struct gbp_startup {
    uint8_t  mode;
    /* Execute the display self-test at all. TRUE in BOTH profiles: the path it
     * validates -- convert, texture upload, GX submit, draw-done, release --
     * is exactly the path `stream-0001` shipped without ever executing. */
    uint8_t  selftest_run;
    /* May the self-test's output reach VIDEO_SetNextFramebuffer? Only in the
     * diagnostic profile. In the normal profile the self-test runs HEADLESS:
     * it claims no framebuffer, so it cannot be seen and cannot perturb the
     * two-framebuffer state machine Policy A reasons about. */
    uint8_t  selftest_visible;
    /* Clear both stream framebuffers to black before the video interface is
     * ever pointed at one. SYS_AllocateFramebuffer does not clear, so without
     * this the normal path would scan out uninitialised memory. */
    uint8_t  clear_framebuffers;
    /* The pre-handler masked wait, in milliseconds. ZERO in the normal
     * profile. Non-zero only for the diagnostic that measured it. */
    uint32_t prehandler_wait_ms;
};

#define GBP_STARTUP_DIAGNOSTIC_WAIT_MS 5000u

/* Pure, total, and the only place a profile is decided. An unknown mode is
 * resolved to NORMAL rather than left undefined: the failure mode of a typo
 * must be "the user sees no diagnostic output", never "the user sees a test
 * pattern and a five-second pause". */
static void gbp_startup_profile(struct gbp_startup *s, int mode)
{
    if (!s) return;
    s->selftest_run = 1u;                 /* both profiles validate the path */
    if (mode == (int)GBP_STARTUP_DIAGNOSTIC) {
        s->mode = (uint8_t)GBP_STARTUP_DIAGNOSTIC;
        s->selftest_visible = 1u;
        s->clear_framebuffers = 1u;
        s->prehandler_wait_ms = GBP_STARTUP_DIAGNOSTIC_WAIT_MS;
    } else {
        s->mode = (uint8_t)GBP_STARTUP_NORMAL;
        s->selftest_visible = 0u;
        s->clear_framebuffers = 1u;
        s->prehandler_wait_ms = 0u;
    }
}

static const char *gbp_startup_mode_name(const struct gbp_startup *s)
{
    if (!s) return "?";
    return (s->mode == (uint8_t)GBP_STARTUP_DIAGNOSTIC) ? "diagnostic" : "normal";
}

/* The two properties the normal path is REQUIRED to have, as one predicate a
 * test and the runtime can both call. It is deliberately a statement about the
 * profile and not about the code that reads it: the wiring is pinned
 * separately, by source, in tests/host/test_vdisp.py. */
static int gbp_startup_is_normal_clean(const struct gbp_startup *s)
{
    if (!s) return 0;
    if (s->mode != (uint8_t)GBP_STARTUP_NORMAL) return 0;
    return (s->selftest_visible == 0u && s->prehandler_wait_ms == 0u &&
            s->clear_framebuffers == 1u) ? 1 : 0;
}

#ifdef __cplusplus
}
#endif
#endif
