/*
 * gbp_alive — Phase 6's acceptance run, the accounting half (GitHub Issue #92;
 * HARDWARE_TESTS §V22 with §V22.8's readings and §V22.9 AMENDMENT 1).
 *
 * WHAT IT DECIDES. Which phase the run is in, which 1.000 s window of QUESTION C
 * an AUDIO block belongs to, what L reads, and what the press record says. The POC
 * hands it ticks, verdicts of the positive-control windows (src/audio/gbp_aperiod,
 * §V19.11 A4.7, unchanged), decoded samples and controller samples; it never
 * touches a device and never allocates. tests/unit/test_gbp_alive.c drives it with
 * no hardware at all.
 *
 * THE PHASES
 *   CALIBRATE  capture start + GBP_ALIVE_CALIB_FROM_S, GBP_ALIVE_CALIB_BLOCKS blocks
 *              of the silent cartridge calibrate the decoder's resting level
 *              (src/audio/gbp_adec). Where a runtime gets that span was left open
 *              by #81; this image takes it before the prompt, while nothing plays.
 *   PROMPT     waits for the ONE A press.
 *   CONTROL    rolling 2048-block windows of gbp_aperiod, as §V19.11 A4.7 defines
 *              them. A pass before capture start + GBP_ALIVE_ACCEPT_S does not
 *              count (A4.5); no pass within GBP_ALIVE_CONTROL_BOUND_S of the press
 *              gives up (A4.7) and the run is INCONCLUSIVE, never a FAIL.
 *   WINDOW     QUESTION C's window, from the ORIGIN (the end of the passing control
 *              window, §V22.1) for GBP_ALIVE_WINDOW_S, in 40.5 MHz ticks.
 *   DONE / GAVE_UP
 *
 * THE PRESS ORIGIN (GitHub Issue #110, §V25.7 2(a), reading (r1)). A game emits no
 * programmed period, so a control can never pass on one. After
 * gbp_alive_use_press_origin() the first A press moves PROMPT to DELAY instead of
 * CONTROL, and the ORIGIN is the completion tick of the first block at or after the
 * press + the delay; that block is the window's first. No control window runs. An A
 * during the calibration span still counts: the delay starts at the press, and the
 * origin is the first block after the span that is also past it. Without the call
 * nothing changes: CONTROL is the path, as every earlier build took it.
 *
 * L (§V22.1, §V22.8 (c) and (e)). The period of the decoder's OWN output, read
 * as each sample leaves the decoder -- BEFORE any clock correction -- over C's
 * window. A rising edge is prev <= 0 < cur: the decoder subtracts the calibrated
 * resting level, so 0 is GBP-HW-313's resting duty. A period counts only between
 * two edges inside the window.
 *
 * THE PRESS RECORD (§V22.8 (r), §V22.9 A3). Every rising edge of the GameCube pad's
 * buttons, A counted apart from all the others, is counted from the first sample
 * until C's window closes; what comes after (the X that saves the log) is counted
 * separately. The image does not act on X until the window has closed.
 *
 * No floating point, no allocation, no blocking call.
 */
#ifndef OPENGBP_GBP_ALIVE_H
#define OPENGBP_GBP_ALIVE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_ALIVE_RATE              4096u   /* AUDIO blocks per second, GBP-HW-301 */
#define GBP_ALIVE_PERIOD              32u   /* one A press: sweep-0002's 128 Hz */
#define GBP_ALIVE_CONTROL_BLOCKS    2048u   /* §V19.11 A4.7 */
#define GBP_ALIVE_CONTROL_MIN         48u   /* §V19.11 A4.7 */
#define GBP_ALIVE_ACCEPT_S             5u   /* §V19.11 A4.5, unchanged */
#define GBP_ALIVE_CONTROL_BOUND_S     10u   /* §V19.11 A4.7, from the A press */
#define GBP_ALIVE_CALIB_FROM_S         2u   /* the calibration span starts here ... */
#define GBP_ALIVE_CALIB_BLOCKS      4096u   /* ... and is one second of silent blocks */
/* C's window: at least 60 s (§V22.3). 64 leaves four whole seconds of margin, so the
 * report always carries 60 whole windows whatever the drain's phase at the origin. */
#define GBP_ALIVE_WINDOW_S            64u
#define GBP_ALIVE_MAX_SECONDS         64u

/* the pad bits this module reads (libogc2's; the POC asserts they match) */
#define GBP_ALIVE_PAD_A           0x0100u
#define GBP_ALIVE_PAD_BUTTONS     0x1F7Fu   /* every button and trigger click, no stick */

enum gbp_alive_phase {
    GBP_ALIVE_CALIBRATE = 0,
    GBP_ALIVE_PROMPT,
    GBP_ALIVE_CONTROL,
    GBP_ALIVE_WINDOW,
    GBP_ALIVE_DONE,
    GBP_ALIVE_GAVE_UP,
    GBP_ALIVE_DELAY            /* Issue #110: the press origin's wait; LAST, so no value above moves */
};

struct gbp_alive_period {
    uint32_t expected;
    uint32_t samples;
    int32_t  prev;             /* INT32_MIN right after a reset */
    uint32_t last_edge;
    uint8_t  have_edge;
    uint32_t edges, periods, pmin, pmax, off;
};

struct gbp_alive {
    enum gbp_alive_phase phase;
    uint32_t tb_hz;
    uint64_t t0, t_calib, t_accept, t_press, t_origin, t_end;
    uint32_t calib_blocks;
    /* the positive control */
    uint32_t control_windows, control_passes, control_early;
    uint32_t control_periods, control_pmin, control_pmax, control_blocks;
    uint8_t  control_ok, control_gave_up;
    /* QUESTION C's window */
    uint32_t sec[GBP_ALIVE_MAX_SECONDS];      /* AUDIO blocks drained per 1.000 s window */
    uint32_t fill[GBP_ALIVE_MAX_SECONDS];     /* the ring's fill as each window begins */
    uint32_t secs_used, sec_overflow;
    uint64_t blocks_in, window_blocks;
    /* L, on the decoder's output */
    struct gbp_alive_period l;
    uint32_t l_samples;
    /* the press record */
    uint16_t prev_buttons;
    uint8_t  have_buttons;
    uint32_t presses_a, presses_other;        /* first sample .. C's window closed */
    uint32_t presses_after;                   /* after it (the X that saves the log) */
    uint64_t t_first_a;
    uint8_t  press_before_prompt;             /* the A came during the calibration span: reported */
    /* Issue #110: the press origin, off unless gbp_alive_use_press_origin() was called */
    uint8_t  press_origin;
    uint32_t origin_delay_ms;
    uint64_t t_delay_end;                     /* t_press + the delay */
};

void gbp_alive_init(struct gbp_alive *a, uint32_t tb_hz);

/* Issue #110: after init, before the first block. The first A press then starts a
 * delay of `delay_ms` instead of the positive control, and C's window opens on the
 * first block at or after its end. */
void gbp_alive_use_press_origin(struct gbp_alive *a, uint32_t delay_ms);

/* The service's capture start, as the tap first sees it. Fixes the calibration
 * span and the accept instant. */
void gbp_alive_start(struct gbp_alive *a, uint64_t t0);

/* Every completed AUDIO block goes through here first. Returns what the POC must
 * do with the block's bytes: */
#define GBP_ALIVE_DO_NOTHING    0
#define GBP_ALIVE_DO_CALIBRATE  1       /* gbp_adec_calibrate() it */
#define GBP_ALIVE_DO_CONTROL    2       /* gbp_aperiod_feed() it */
#define GBP_ALIVE_DO_DECODE     3       /* gbp_adec_push_block() it, then gbp_alive_decoded() */
int gbp_alive_block(struct gbp_alive *a, uint64_t t_done, uint32_t ring_fill);

/* A control window of GBP_ALIVE_CONTROL_BLOCKS has been decoded. `pass` is
 * gbp_aperiod_exact(.., GBP_ALIVE_CONTROL_MIN); the other fields are its figures. */
void gbp_alive_control_window(struct gbp_alive *a, uint64_t t_done, int pass, uint32_t periods,
                              uint32_t pmin, uint32_t pmax, uint32_t blocks);

/* One decoded sample as it left the decoder, before any correction (L). */
void gbp_alive_decoded(struct gbp_alive *a, int16_t sample);

/* One controller sample (the pump slot's PAD_ButtonsHeld), with its instant. The
 * first A press moves PROMPT to CONTROL. */
void gbp_alive_buttons(struct gbp_alive *a, uint64_t t, uint16_t buttons);

/* 1 once the window has closed (the session may end), 0 before. */
int gbp_alive_finished(const struct gbp_alive *a);

/* Pure period reader, exposed for the tests. */
void gbp_alive_period_reset(struct gbp_alive_period *p, uint32_t expected);
void gbp_alive_period_feed(struct gbp_alive_period *p, int16_t s);

const char *gbp_alive_phase_name(enum gbp_alive_phase p);

#ifdef __cplusplus
}
#endif
#endif
