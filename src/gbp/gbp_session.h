/*
 * gbp_session.h — Issue #39: the operator's session end, as a pure state
 * machine (the playable image's SUCCESS).
 *
 * A game session has no scientific target: it ends when the operator ends it.
 * The one input the input policy never sends to the AGB is Z (INPUT.md §4;
 * GBP-KEY-006 / GBP-KEY-007), so a Z hold cannot be a game action, and the
 * Start-up Disc reserves the same button for its own menu. This module turns
 * "Z held continuously for at least `hold_ticks`" into ONE latched flag,
 * `end_requested`, which the caller installs as `gbp_vstate_config.session_end`
 * and CHECK_ADMISSION reads once per admitted cycle (gbp_vstate_probe.h).
 *
 * The hold is a design bound of the image, not a property of the device: a
 * tap does nothing, a deliberate hold ends the session, and the request is
 * latched for good (a release afterwards changes nothing). Every sample is
 * counted so the SESSION record can say how the end came about.
 *
 * Pure: no clock, no controller, no transport, no allocation, no logging. The
 * caller samples the pad and the clock in the pump slot (the input path's
 * PAD_ScanPads and the transport's ticks64) and feeds both in. The `play`
 * audit profile enumerates this object's outward edges: there are none.
 */
#ifndef OPENGBP_GBP_SESSION_H
#define OPENGBP_GBP_SESSION_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct gbp_session {
    uint64_t hold_ticks;       /* the bound: a hold at least this long requests the end (0 = the first held sample does) */
    uint64_t t_hold_begin;     /* the instant the hold in progress began; valid while `holding` */
    uint64_t t_requested;      /* the instant the end was requested; valid when `end_requested` */
    int holding;               /* the button was held at the last sample */
    int end_requested;         /* THE FLAG: latched by the sample that completes the hold, never cleared */
    uint32_t samples;          /* every sample fed in */
    uint32_t samples_held;     /* samples with the button held */
    uint32_t holds_begun;      /* rising edges: holds that started */
    uint32_t holds_released;   /* holds released before the bound (a tap) */
    uint32_t samples_after;    /* samples fed in after the request: counted, ignored */
};

void gbp_session_init(struct gbp_session *s, uint64_t hold_ticks);

/* One sample: `held` is whether the end button is held right now, `now` the
 * caller's monotonic 64-bit instant. Returns 1 on the ONE sample that latches
 * the request, 0 on every other. */
int gbp_session_sample(struct gbp_session *s, int held, uint64_t now);

#ifdef __cplusplus
}
#endif
#endif
