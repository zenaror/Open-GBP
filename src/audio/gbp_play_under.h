/*
 * gbp_play_under -- the instrument of the fallback rule in HARDWARE_TESTS.md V31.3 (GitHub Issue #153, the build half of Phase 7's E5 vehicle):
 * underruns AFTER the start-up, and the start-up apart, from the hand-off ordinals gbp_aplay2_irq_handoff() stores at the increment.
 *
 * START-UP IS A HAND-OFF COUNT: the first GBP_PLAY_STARTUP_K = 64 hand-offs after the DMA start (about 2.0 s at the 31.2 ms period), registered
 * before any data. The delimiter is the counter the callback already increments (`handed`), needs no ring level and cannot fail to fire. An
 * underrun is START-UP when its 1-based hand-off ordinal is <= K and AFTER-START-UP otherwise; an underrun beyond K is never reclassified, and
 * its ordinal is in the record. The fallback rule reads `after_startup`, and only that.
 *
 * POST-FEED. The vehicle's pump stops producing when the session ends; on a probe-side stop (a store cap, the safety wall, the delivery cap) no pump call runs at all while the teardown
 * goes on, and the DMA keeps handing out silence until main stops it: every one of those silences is an "underrun" of the chain and NOT a finding about the setting. The caller passes the
 * instant of the pump's LAST production slot plus a margin (`t_feed_end`); a recorded underrun whose instant is later is POST-FEED, counted apart and never in `after_startup`. Because the
 * instants rise, every unrecorded underrun after a post-feed recorded one is post-feed too. A start-up underrun is never post-feed.
 *
 * Pure: no device, no clock. The callback's arrays are read by the pump side after the session; the formatters return the snprintf count.
 * Only the first GBP_APLAY2_UNDER_CAP (64) underruns keep an ordinal; the count of the rest is `unrecorded`, and because the ordinals rise,
 * every unrecorded underrun came after the last recorded one (which is at least ordinal 64), so with K <= the cap it is AFTER-START-UP.
 */
#ifndef OPENGBP_GBP_PLAY_UNDER_H
#define OPENGBP_GBP_PLAY_UNDER_H

#include <stddef.h>
#include <stdint.h>

#include "gbp_aplay2.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_PLAY_STARTUP_K 64u
_Static_assert(GBP_PLAY_STARTUP_K <= GBP_APLAY2_UNDER_CAP,
               "start-up must lie inside the recorded ordinals, or an unrecorded underrun could not be classified");

struct gbp_play_under_sum {
    uint32_t total;               /* every underrun the chain counted */
    uint32_t recorded;            /* those that kept an ordinal: min(total, cap) */
    uint32_t unrecorded;          /* total - recorded: all of them AFTER the last recorded ordinal, so after start-up */
    uint32_t startup;             /* ordinal <= K */
    uint32_t post_feed;           /* after the pump's last production slot (teardown silence): NOT a finding about the setting */
    uint32_t after_startup;       /* everything else (total - startup - post_feed), unrecorded ones included unless they follow a post-feed one */
    uint32_t first_after_handed;  /* the ordinal of the first recorded after-start-up underrun; 0 when none is recorded */
};

/* `handed` / `t` are the callback's arrays of ordinals and instants (volatile: written in interrupt context), `cap` their length; `t_feed_end` the instant after which an underrun is post-feed
 * (pass UINT64_MAX for "none"). */
void gbp_play_under_summarize(struct gbp_play_under_sum *out, uint32_t total, const volatile uint32_t *handed,
                              const volatile uint64_t *t, uint32_t cap, uint32_t k, uint64_t t_feed_end);

/* PLAYSTARTUP t_dma=<hex> k=<K> ring_at_dma=<n> ready_at_dma=<n> -- read ONCE, at the DMA start. */
int gbp_play_under_fmt_startup(char *out, size_t cap, uint64_t t_dma, uint32_t k, uint32_t ring_at_dma,
                               uint32_t ready_at_dma);
/* PLAYUND n=<i> handed=<ordinal> since_dma_ms=<ms> post_feed=<0|1> -- one per recorded underrun. */
int gbp_play_under_fmt_und(char *out, size_t cap, uint32_t n, uint32_t handed, uint64_t t, uint64_t t_dma,
                           uint32_t tb_hz, int post_feed);
/* PLAYUNDER startup=<n> after_startup=<n> post_feed=<n> first_after_handed=<ordinal or -> unrecorded=<n> total=<n> k=<K> */
int gbp_play_under_fmt_sum(char *out, size_t cap, const struct gbp_play_under_sum *s, uint32_t k);

#ifdef __cplusplus
}
#endif
#endif
