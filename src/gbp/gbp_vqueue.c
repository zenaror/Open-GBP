/*
 * gbp_vqueue.c — the producer/consumer boundary. See gbp_vqueue.h for the rule
 * this module exists to enforce and for why the mailbox is depth one.
 *
 * It includes gbp_vstate.h for the assembler's FRAME FLAG VALUES ONLY. The
 * classification itself is not reimplemented here: `gbp_vstate` decides what a
 * frame is, and this module decides only what the DISPLAY does about it
 * (§V5.9). Copying a divergent classifier would be the exact failure the
 * regression tests guard against.
 */
#include "gbp_vqueue.h"
#include "gbp_vstate.h"
#include "gbp_vpix.h"

void gbp_vqueue_init(struct gbp_vqueue *q, uint32_t slots)
{
    uint32_t i;
    uint8_t *p = (uint8_t *)q;
    if (!q) return;
    for (i = 0; i < sizeof *q; i++) p[i] = 0u;
    q->slots = slots;
    q->publish_interval_min = 0xFFFFFFFFu;
    q->convert_ticks_min = 0xFFFFFFFFu;
}

enum gbp_vqueue_reject gbp_vqueue_classify(uint32_t blocks, uint32_t flags, int slot)
{
    /* Order matters, and it is the order a reader would want reported: the
     * strongest reason to refuse a frame is named first. A quarantined frame is
     * refused for its own reason even though it also carries F_ANOMALY, because
     * "a majority-extra block reached the screen" is a different failure from
     * "an anomalous frame reached the screen" (§R3.12). */
    if (flags & GBP_VSTATE_F_MAJORITY_EXTRA) return GBP_VQUEUE_REJECT_QUARANTINED;
    if (flags & (GBP_VSTATE_F_ANOMALY | GBP_VSTATE_F_RESYNC)) return GBP_VQUEUE_REJECT_ANOMALY;
    if (!(flags & GBP_VSTATE_F_COMPLETE) || blocks != GBP_VPIX_BLOCKS)
        return GBP_VQUEUE_REJECT_INCOMPLETE;
    if (slot < 0) return GBP_VQUEUE_REJECT_NO_SLOT;
    return GBP_VQUEUE_ACCEPT;
}

enum gbp_vqueue_reject gbp_vqueue_publish(struct gbp_vqueue *q, uint32_t frame_index,
                                          uint32_t blocks, uint32_t flags, int slot,
                                          uint64_t t_first, uint64_t t_last)
{
    enum gbp_vqueue_reject r;

    if (!q) return GBP_VQUEUE_REJECT_NO_SLOT;
    q->source_frames_closed++;

    r = gbp_vqueue_classify(blocks, flags, slot);
    switch (r) {
    case GBP_VQUEUE_REJECT_QUARANTINED: q->source_frames_quarantined++; return r;
    case GBP_VQUEUE_REJECT_ANOMALY:     q->source_frames_anomaly++;     return r;
    case GBP_VQUEUE_REJECT_INCOMPLETE:  q->source_frames_incomplete++;  return r;
    case GBP_VQUEUE_REJECT_NO_SLOT:     q->source_frames_incomplete++;  return r;
    default: break;
    }
    q->source_frames_complete++;

    /* Newest wins. A descriptor the consumer never took is replaced, and the
     * loss is counted HERE, as a consumer-side drop — the device delivered that
     * frame perfectly well (§V5.14). The producer does not wait. */
    if (q->has_pending) q->dropped_before_convert++;

    q->seq++;
    q->pending.frame_index = frame_index;
    q->pending.seq         = q->seq;
    q->pending.t_first     = t_first;
    q->pending.t_last      = t_last;
    q->pending.slot        = (uint16_t)slot;
    q->pending.blocks      = (uint16_t)blocks;
    q->pending.flags       = flags;
    q->has_pending = 1;
    q->frames_published++;

    /* Bounded pacing aggregate: min, max, count and sum. No per-frame array,
     * so a long run costs constant memory (§V5.19). */
    if (q->have_last_publish && t_first > q->t_last_publish) {
        uint64_t d = t_first - q->t_last_publish;
        uint32_t d32 = (d > 0xFFFFFFFFull) ? 0xFFFFFFFFu : (uint32_t)d;
        if (d32 < q->publish_interval_min) q->publish_interval_min = d32;
        if (d32 > q->publish_interval_max) q->publish_interval_max = d32;
        q->publish_interval_sum += d32;
        q->publish_interval_n++;
    }
    q->t_last_publish = t_first;
    q->have_last_publish = 1;
    return GBP_VQUEUE_ACCEPT;
}

int gbp_vqueue_take(struct gbp_vqueue *q, struct gbp_vqueue_desc *out)
{
    if (!q || !out) return 0;
    if (!q->has_pending) return 0;
    *out = q->pending;
    q->has_pending = 0;
    q->consumer_frames_taken++;
    return 1;
}

int gbp_vqueue_still_valid(const struct gbp_vqueue *q, const struct gbp_vqueue_desc *desc)
{
    uint32_t advanced;
    if (!q || !desc) return 0;
    if (q->slots == 0u) return 0;          /* an unconfigured queue trusts nothing */
    /* The ring is round-robin over `slots`. The slot that held the frame
     * published at `desc->seq` is reused once `slots` further frames have been
     * published. Unsigned wrap is intentional and correct: only the DIFFERENCE
     * matters, and a u32 publish counter wrapping after 4.29e9 frames still
     * yields the right distance. */
    advanced = q->seq - desc->seq;
    return (advanced < q->slots) ? 1 : 0;
}

int gbp_vqueue_commit(struct gbp_vqueue *q, int still_valid, uint32_t convert_ticks)
{
    if (!q) return 0;
    q->consumer_frames_converted++;
    if (convert_ticks != 0u) {
        if (convert_ticks < q->convert_ticks_min) q->convert_ticks_min = convert_ticks;
        if (convert_ticks > q->convert_ticks_max) q->convert_ticks_max = convert_ticks;
        q->convert_ticks_sum += convert_ticks;
        q->convert_ticks_n++;
    }
    if (!still_valid) {
        /* The producer reused the slot while we were reading it. This is a
         * CONSUMER overrun: the device lost nothing. The partially converted
         * texture is never presented (§V5.9: never mix pixels from two
         * generations). */
        q->consumer_slot_overrun++;
        return 0;
    }
    return 1;
}

void gbp_vqueue_pump(struct gbp_vqueue *q)
{
    if (q && q->pump) q->pump(q->pump_user);
}

void gbp_vqueue_note_presented(struct gbp_vqueue *q)
{
    if (q) q->consumer_frames_presented++;
}

void gbp_vqueue_note_repeat(struct gbp_vqueue *q)
{
    if (q) q->display_frames_repeated++;
}

int gbp_vqueue_balanced(const struct gbp_vqueue *q)
{
    if (!q) return 0;
    /* Every closed frame is complete, incomplete, quarantined or anomalous. */
    if (q->source_frames_closed != q->source_frames_complete + q->source_frames_incomplete
                                + q->source_frames_quarantined + q->source_frames_anomaly)
        return 0;
    /* Every complete frame was published. */
    if (q->source_frames_complete != q->frames_published) return 0;
    /* A published frame is taken, still pending, or was superseded. */
    if (q->frames_published != q->consumer_frames_taken + q->dropped_before_convert
                             + (uint32_t)(q->has_pending ? 1u : 0u))
        return 0;
    /* A converted frame was presented or overran; a taken frame may still be
     * mid-conversion, so converted <= taken rather than equal. */
    if (q->consumer_frames_converted > q->consumer_frames_taken) return 0;
    if (q->consumer_frames_converted != q->consumer_frames_presented + q->consumer_slot_overrun)
        return 0;
    return 1;
}

uint32_t gbp_vqueue_publish_interval_mean(const struct gbp_vqueue *q)
{
    if (!q || q->publish_interval_n == 0u) return 0u;
    return (uint32_t)(q->publish_interval_sum / q->publish_interval_n);
}

uint32_t gbp_vqueue_convert_ticks_mean(const struct gbp_vqueue *q)
{
    if (!q || q->convert_ticks_n == 0u) return 0u;
    return (uint32_t)(q->convert_ticks_sum / q->convert_ticks_n);
}
