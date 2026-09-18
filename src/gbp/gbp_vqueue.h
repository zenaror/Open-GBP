/*
 * gbp_vqueue.h — the producer/consumer boundary of GBP-VIDEO-004
 * (HARDWARE_TESTS §V5.7, §V5.8, §V5.9, §V5.14). Pure, hardware-free,
 * host-tested. No allocation, no clock, no device, no blocking.
 *
 * ---- WHY THIS EXISTS AT ALL ----------------------------------------------
 *
 * The first GBP-VIDEO-003 implementation did a 153 600-byte `memcmp` and
 * `memcpy` between the ACK and the RE-ARM, and the microaudit refused it
 * (§V3.23). What replaced it — pass a SLOT INDEX, never bytes — is what made
 * `color-0001` and `color-0002` possible, and §V5.7 carries the same rule into
 * streaming. This module is that rule, made explicit:
 *
 *     producer  gbp_vqueue_publish()   writes one small descriptor. No copy.
 *     consumer  gbp_vqueue_take()      reads it, outside the critical path.
 *
 * `gbp_vqueue_publish()` is the ONLY function here the service path calls, it
 * touches a handful of words, and it can never block: a consumer that has
 * fallen behind loses a frame, it does not stall the device (§V5.14).
 *
 * ---- THE MAILBOX IS DEPTH ONE, ON PURPOSE --------------------------------
 *
 * §V5.14's policy is "newest-complete-frame wins". A deeper descriptor queue
 * would mean showing OLDER frames when the consumer is behind, which is the
 * opposite of that policy, so the mailbox holds exactly one descriptor: a
 * second publish before the consumer takes the first drops the first and counts
 * it as `dropped_before_convert`. The TEXTURE buffers are a separate question
 * and are double-buffered in the POC (§V5.8); that is about GX ownership, not
 * about queue policy.
 *
 * ---- THE GENERATION GUARD ------------------------------------------------
 *
 * The descriptor names a raw ring slot the producer still owns. The ring is
 * round-robin over `slots` entries, so the slot that held frame N is overwritten
 * when frame N + slots begins. The consumer therefore:
 *
 *     1. takes a descriptor, recording the publish sequence it was published at
 *     2. converts out of the ring slot
 *     3. asks gbp_vqueue_still_valid() whether the producer has since advanced
 *        far enough to have reused that slot
 *     4. if it has: DISCARD the conversion, count `consumer_slot_overrun`, and
 *        present nothing
 *
 * §V5.7 chose this deliberately over hoping four slots are enough: the margin is
 * about 50 ms at 59.7 Hz, but nothing in this repository has measured conversion
 * cost, so the race is DETECTED rather than assumed away. An overrun is a
 * CONSUMER fault and is counted separately from anything the device did — it is
 * never reported as source frame loss (§V5.5).
 */
#ifndef OPENGBP_GBP_VQUEUE_H
#define OPENGBP_GBP_VQUEUE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Why a published frame was refused, so "not presented" is never silent. */
enum gbp_vqueue_reject {
    GBP_VQUEUE_ACCEPT = 0,
    GBP_VQUEUE_REJECT_INCOMPLETE,     /* not COMPLETE_40, or the wrong block count */
    GBP_VQUEUE_REJECT_QUARANTINED,    /* F_MAJORITY_EXTRA: may never reach the screen */
    GBP_VQUEUE_REJECT_ANOMALY,        /* F_ANOMALY / F_RESYNC */
    GBP_VQUEUE_REJECT_NO_SLOT,        /* the frame's raw did not survive in the ring */
    GBP_VQUEUE_REJECT_COUNT
};

/* One published complete frame. This is the WHOLE handoff: no pixels cross. */
struct gbp_vqueue_desc {
    uint32_t frame_index;    /* the assembler's index */
    uint32_t seq;            /* publish sequence at which it was published */
    uint64_t t_first;        /* first block of the frame */
    uint64_t t_last;         /* last block; t_last - t_first is the frame's span */
    uint16_t slot;           /* raw ring slot holding it */
    uint16_t blocks;         /* 40 for anything that is published */
    uint32_t flags;          /* the assembler's frame flags, carried verbatim */
};

struct gbp_vqueue {
    /* ---- configuration ---- */
    uint32_t slots;          /* raw ring slots; the generation guard's modulus */
    /* ---- the consumer's CPU time, and where it comes from ----
     * The probe is single-threaded and `gbp_vstate_probe_run()` owns the loop,
     * so "the consumer runs outside the critical path" needs a concrete place to
     * execute. §V5 specified the boundary and the policy but not that place;
     * this is it, and the choice is deliberately the most conservative one
     * available.
     *
     * `pump` is called ONCE PER SERVICE CYCLE, immediately after the RE-ARM —
     * which is where the pass's device work has ended: the re-arm is "the last
     * device access of the pass" and the next cause has already been invited.
     * It is never called between the ACK and the RE-ARM.
     *
     * The callback MUST do a BOUNDED SLICE, not a frame. The size that is
     * defensible is measured, not guessed: `gbp_vsig_block()` already reads
     * 3840 bytes inside this same path and cost 777-799 ticks (19.2-19.7 us at
     * 40.5 MHz) in the physical color-0002 run, against 164 us of slack between
     * deliveries. One tile row reads the same 3840 bytes and writes 1920, so it
     * is the same order of work as something already physically proven to fit.
     *
     * NOTHING here makes that a timing claim. The POC measures the slice and
     * reports the distribution; §V5.22 forbids presenting an estimate as a
     * property, and this comment is an argument for the slice SIZE, not a
     * guarantee about it. */
    void (*pump)(void *user);
    void *pump_user;

    /* ---- the depth-one mailbox ---- */
    struct gbp_vqueue_desc pending;
    int      has_pending;

    /* ---- the publish sequence: one per ACCEPTED publish ---- */
    uint32_t seq;

    /* ---- source-side counters (what the DEVICE and the assembler did) ---- */
    uint32_t source_frames_closed;
    uint32_t source_frames_complete;
    uint32_t source_frames_incomplete;
    uint32_t source_frames_quarantined;
    uint32_t source_frames_anomaly;

    /* ---- publication ---- */
    uint32_t frames_published;
    uint32_t dropped_before_convert;   /* superseded in the mailbox: newest wins */

    /* ---- consumer-side counters (what WE did, never what the device did) ---- */
    uint32_t consumer_frames_taken;
    uint32_t consumer_frames_converted;
    uint32_t consumer_frames_presented;
    uint32_t consumer_slot_overrun;    /* the generation guard fired */

    /* ---- display-side counters ---- */
    uint32_t display_frames_repeated;  /* HOLD_PREVIOUS_FRAME: nothing new to show */

    /* ---- bounded pacing aggregates (§V5.19): no per-frame storage ---- */
    uint32_t publish_interval_min;     /* in the caller's tick unit */
    uint32_t publish_interval_max;
    uint32_t publish_interval_n;
    uint64_t publish_interval_sum;
    uint64_t t_last_publish;
    int      have_last_publish;   /* a frame published AT tick 0 is legitimate */

    uint32_t convert_ticks_min;
    uint32_t convert_ticks_max;
    uint32_t convert_ticks_n;
    uint64_t convert_ticks_sum;
};

/* `slots` is the raw ring's slot count, from gbp_vstate_ring_slots(). */
void gbp_vqueue_init(struct gbp_vqueue *q, uint32_t slots);

/* Classifies a closed frame WITHOUT publishing it. Pure; the POC's audit and
 * the host tests use it to prove the policy independently of the publish path. */
enum gbp_vqueue_reject gbp_vqueue_classify(uint32_t blocks, uint32_t flags, int slot);

/* PRODUCER, in the service path, after the ACK and before the RE-ARM.
 *
 * Counts the closed frame, and publishes it only if it is COMPLETE_40, clean,
 * not quarantined and its raw survived in the ring. Returns GBP_VQUEUE_ACCEPT
 * when it was published. NEVER blocks and never copies a pixel: a pending
 * descriptor the consumer has not taken is simply replaced, because §V5.14's
 * policy is newest-complete-frame-wins. */
enum gbp_vqueue_reject gbp_vqueue_publish(struct gbp_vqueue *q, uint32_t frame_index,
                                          uint32_t blocks, uint32_t flags, int slot,
                                          uint64_t t_first, uint64_t t_last);

/* CONSUMER, outside the critical path. Returns 1 and fills `out` when a frame
 * was waiting, 0 when there was none (which is the HOLD_PREVIOUS_FRAME case —
 * the caller reports it through gbp_vqueue_note_repeat()). */
int gbp_vqueue_take(struct gbp_vqueue *q, struct gbp_vqueue_desc *out);

/* Step 3 of the generation guard: may the frame taken at `desc->seq` still be
 * trusted, now that the producer has reached `q->seq`? The ring is round-robin,
 * so the slot survives until `slots` further frames have been published.
 * Returns 1 if the conversion is valid, 0 if the slot was reused. */
int gbp_vqueue_still_valid(const struct gbp_vqueue *q, const struct gbp_vqueue_desc *desc);

/* Step 4. Call exactly once per converted frame, with the result of
 * gbp_vqueue_still_valid(). Returns 1 when the frame may be presented, 0 when
 * it must be discarded (and the overrun has been counted).
 * `convert_ticks` feeds the bounded aggregate; pass 0 if not measured. */
int gbp_vqueue_commit(struct gbp_vqueue *q, int still_valid, uint32_t convert_ticks);

/* Called by the service loop once per cycle, after the RE-ARM. Invokes `pump`
 * when one is installed, and does nothing at all otherwise — every earlier
 * build behaves exactly as it did. */
void gbp_vqueue_pump(struct gbp_vqueue *q);

/* The frame reached the screen. */
void gbp_vqueue_note_presented(struct gbp_vqueue *q);

/* HOLD_PREVIOUS_FRAME: a display opportunity passed with no new valid frame. */
void gbp_vqueue_note_repeat(struct gbp_vqueue *q);

/* Every accounted frame must land in exactly one bucket. Returns 1 when the
 * counters balance, 0 when they do not — a run whose counters do not balance
 * cannot support a claim about loss. */
int gbp_vqueue_balanced(const struct gbp_vqueue *q);

/* Mean publish interval and mean convert cost, or 0 when nothing was sampled.
 * Integer only: this code runs on a target where a float in a report is noise. */
uint32_t gbp_vqueue_publish_interval_mean(const struct gbp_vqueue *q);
uint32_t gbp_vqueue_convert_ticks_mean(const struct gbp_vqueue *q);

#ifdef __cplusplus
}
#endif
#endif
