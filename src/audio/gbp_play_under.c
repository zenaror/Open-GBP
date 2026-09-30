#include "gbp_play_under.h"

#include <stdio.h>

void gbp_play_under_summarize(struct gbp_play_under_sum *out, uint32_t total, const volatile uint32_t *handed,
                              const volatile uint64_t *t, uint32_t cap, uint32_t k, uint64_t t_feed_end)
{
    uint32_t i;
    int last_post = 0;
    if (!out) return;
    out->total = total;
    out->recorded = total < cap ? total : cap;
    out->unrecorded = total - out->recorded;
    out->startup = 0u;
    out->post_feed = 0u;
    out->first_after_handed = 0u;
    for (i = 0u; handed && i < out->recorded; i++) {
        const uint32_t h = handed[i];
        last_post = 0;
        if (h <= k) {
            out->startup++;
        } else if (t && t[i] > t_feed_end) {
            out->post_feed++;
            last_post = 1;
        } else if (out->first_after_handed == 0u) {
            out->first_after_handed = h;
        }
    }
    if (last_post) {                      /* the instants rise: everything after a post-feed record is post-feed too */
        out->post_feed += out->unrecorded;
        out->unrecorded = 0u;
    }
    out->after_startup = total - out->startup - out->post_feed;
}

int gbp_play_under_fmt_startup(char *out, size_t cap, uint64_t t_dma, uint32_t k, uint32_t ring_at_dma,
                               uint32_t ready_at_dma)
{
    return snprintf(out, cap, "PLAYSTARTUP t_dma=%llx k=%lu ring_at_dma=%lu ready_at_dma=%lu",
                    (unsigned long long)t_dma, (unsigned long)k, (unsigned long)ring_at_dma,
                    (unsigned long)ready_at_dma);
}

int gbp_play_under_fmt_und(char *out, size_t cap, uint32_t n, uint32_t handed, uint64_t t, uint64_t t_dma,
                           uint32_t tb_hz, int post_feed)
{
    const uint64_t dt = (t >= t_dma) ? t - t_dma : 0u;
    const uint64_t ms = tb_hz ? (dt * 1000u) / tb_hz : 0u;
    return snprintf(out, cap, "PLAYUND n=%lu handed=%lu since_dma_ms=%lu post_feed=%d", (unsigned long)n,
                    (unsigned long)handed, (unsigned long)ms, post_feed ? 1 : 0);
}

int gbp_play_under_fmt_sum(char *out, size_t cap, const struct gbp_play_under_sum *s, uint32_t k)
{
    char first[16];
    if (s->first_after_handed) snprintf(first, sizeof first, "%lu", (unsigned long)s->first_after_handed);
    else snprintf(first, sizeof first, "-");
    return snprintf(out, cap, "PLAYUNDER startup=%lu after_startup=%lu post_feed=%lu first_after_handed=%s unrecorded=%lu total=%lu k=%lu",
                    (unsigned long)s->startup, (unsigned long)s->after_startup, (unsigned long)s->post_feed, first,
                    (unsigned long)s->unrecorded, (unsigned long)s->total, (unsigned long)k);
}
