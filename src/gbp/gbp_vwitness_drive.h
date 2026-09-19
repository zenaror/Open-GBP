/*
 * gbp_vwitness_drive.h — the ONE rule that binds a witness scratch to the
 * assembler's own frame boundaries, in one place that both the probe and the
 * unit tests execute (HARDWARE_TESTS §V5.39.4).
 *
 * WHY THIS IS A FILE AND NOT SIX LINES IN THE SERVICE LOOP
 *
 * The association is the whole experiment. A witness placed in the wrong frame
 * does not fail loudly — it produces a *plausible* record of a frame that never
 * existed, and there is no later check that can recover from it. The rule
 * therefore lives where a test can drive it against the real assembler, rather
 * than being a transcription inside a function that needs a transport, an HSP
 * backend and a Game Boy Player to call.
 *
 * THE RULE, and every case it covers:
 *
 *   The assembler reports where the block it just accumulated landed, and
 *   whether that block belongs to the frame that closed in the SAME call.
 *
 *     boundary block      the previous frame closed FIRST and this block is
 *                         index 0 of the one now opening
 *                         -> commit, then place
 *     48-block give-up    this block is already the 48th of the interval that
 *                         is ending
 *                         -> place, then commit
 *     ordinary block      nothing closed; the order is immaterial
 *     no anchor / store full
 *                         no frame record exists, so no witness record may
 *                         -> drop the scratch
 *
 * Nothing here reads a clock, touches a device, allocates or blocks. It reads
 * 54 words out of the ring slot THE ASSEMBLER NAMED — never one this code
 * computed — and takes its metadata from the frame record the assembler just
 * wrote, so a witness can never describe a frame the frame store does not.
 */
#ifndef OPENGBP_GBP_VWITNESS_DRIVE_H
#define OPENGBP_GBP_VWITNESS_DRIVE_H

#include "gbp_vstate.h"
#include "gbp_vwitness.h"

#ifdef __cplusplus
extern "C" {
#endif

static void gbp_vwitness_place_step(struct gbp_vwitness *w, const struct gbp_vstate *st,
                                    const struct gbp_vstate_step *step)
{
    const uint8_t *blk = gbp_vstate_ring_block(st, step->witness_slot, step->witness_index);
    if (!blk) return;
    if (gbp_vwitness_stage(w, blk)) return;
    (void)gbp_vwitness_place(w, step->witness_index);
}

static void gbp_vwitness_commit_step(struct gbp_vwitness *w, const struct gbp_vstate *st,
                                     const struct gbp_vstate_step *step)
{
    const struct gbp_vstate_frame *fr = gbp_vstate_frame_at(st, step->frame_index);
    struct gbp_vwitness_meta m;
    if (!fr) { gbp_vwitness_discard(w); return; }
    m.frame_index = fr->index;
    m.t_first_block = fr->t_first_block;
    m.t_last_block = fr->t_last_block;
    m.blocks = fr->blocks;
    m.flags = fr->flags;                 /* VERBATIM: quarantine and anomaly travel too */
    m.completeness = fr->completeness;
    m.disagreements = fr->disagreements;
    m.present = 0u;                      /* the commit fills it from what was placed */
    m.blocks_captured = 0u;
    (void)gbp_vwitness_commit(w, &m);
}

/* THE STRUCTURAL QUALIFICATION PREDICATE (§V5.44).
 *
 * Reads the ASSEMBLER's verdict on frame structure and nothing else. It may
 * not touch FRAME_ID, STATUS, SYNC, CRC-8, a symbol or a pixel: the runtime
 * must not consult the scientific answer in order to decide when to start
 * measuring it. Every term below is the assembler's own vocabulary.
 *
 * `resync_pending` is the assembler's existing latch for "synchronisation is
 * not re-established": raised by ANY region anomaly, cleared only by a clean
 * complete frame. F_RESYNC marks the frame that performed that clearing, so
 * excluding it means the streak begins only AFTER re-establishment. */
/* The RECORDED half of the predicate, split out so it can be replayed.
 *
 * These three quantities are the only ones a frame record preserves, so they
 * are the only ones an offline replay of a past capture can evaluate. Keeping
 * them in a function the RUNTIME also calls is the whole point: a replay that
 * re-implemented the rule would be testing the re-implementation.
 *
 * F_PRE_BASELINE is deliberately NOT in the reject mask. The baseline is a
 * CONTENT-stability notion -- it waits for a frame to repeat -- and on an
 * indexed stimulus, whose every frame differs by construction, it never
 * establishes: all three physical runs report `baseline=never_established`
 * with F_PRE_BASELINE on 2048 of 2048 records. Rejecting on it would mean the
 * window never opens, and would smuggle a content criterion into a rule that
 * must not have one. */
static int gbp_vwitness_frame_shape_qualifies(uint16_t blocks, uint16_t flags,
                                              uint16_t completeness)
{
    if (completeness != GBP_VSTATE_FRAME_COMPLETE_40) return 0;
    if (blocks != GBP_VWITNESS_BLOCKS) return 0;
    if (flags & (uint16_t)(GBP_VSTATE_F_ANOMALY | GBP_VSTATE_F_DISAGREEMENT |
                           GBP_VSTATE_F_OVERLONG | GBP_VSTATE_F_RESYNC)) return 0;
    return 1;
}

static int gbp_vwitness_frame_qualifies(const struct gbp_vstate *st,
                                        const struct gbp_vstate_step *step)
{
    const struct gbp_vstate_frame *fr;
    if (!step->frame_closed) return 0;
    if (step->resync) return 0;                 /* a region anomaly was raised here */
    if (!step->frame_complete) return 0;
    if (st->resync_pending) return 0;           /* the assembler says: not yet in sync */
    fr = gbp_vstate_frame_at(st, step->frame_index);
    if (!fr) return 0;
    /* The two tests above this line are LIVE LATCHES that no frame record
     * preserves; everything below is recorded, hence replayable. A replay is
     * therefore an EARLIEST BOUND on the window, never an equality. */
    return gbp_vwitness_frame_shape_qualifies(fr->blocks, fr->flags, fr->completeness);
}

/* Applies the rule for one `gbp_vstate_block()` call. Call it immediately after
 * the assembler returns and BEFORE any publication hook: what is retained must
 * not depend on what a consumer was willing to accept. */
static void gbp_vwitness_step(struct gbp_vwitness *w, const struct gbp_vstate *st,
                              const struct gbp_vstate_step *step)
{
    if (!w || !st || !step) return;
    if (step->witness_valid && step->witness_place_first)
        gbp_vwitness_place_step(w, st, step);
    if (step->frame_closed) {
        /* The structural verdict FIRST: a frame that closed during warm-up
         * feeds the streak and is then discarded by the commit, which refuses
         * to store anything before the window is armed. */
        gbp_vwitness_note_frame(w, gbp_vwitness_frame_qualifies(st, step));
        gbp_vwitness_commit_step(w, st, step);
    } else if (step->witness_reset) {
        /* No frame record exists at all — no anchor, or the frame store filled.
         * Structurally that is not a qualifying frame, so it breaks the streak. */
        gbp_vwitness_note_frame(w, 0);
        gbp_vwitness_discard(w);
    }
    if (step->witness_valid && !step->witness_place_first) {
        /* THE ONLY PLACE THE WINDOW MAY OPEN. This block begins a new frame, so
         * arming here — and only here — makes record 0 start at block 0 by
         * construction rather than by hope. */
        if (step->witness_index == 0u && gbp_vwitness_qualified(w))
            gbp_vwitness_arm(w);
        gbp_vwitness_place_step(w, st, step);
    }
}

#ifdef __cplusplus
}
#endif
#endif
