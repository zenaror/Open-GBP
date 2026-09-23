/*
 * aout_order.h -- THE SEALED PLAY ORDER of aout-0002 (GitHub Issue #86,
 * HARDWARE_TESTS §V21.6). Drawn 2026-09-23T19:44:07-03:00 by a random draw, BEFORE this image
 * existed. It is NEVER shown on screen, which says only "TONE k of 4" by play
 * position. The log records it, and the log is read after the run.
 */
#ifndef OPENGBP_AOUT_ORDER_H
#define OPENGBP_AOUT_ORDER_H
/* play position -> the tone gbp_alisten built from press window index + 1 */
static const unsigned char AOUT_PLAY_ORDER[4] = { 3, 2, 1, 0 };
#endif
