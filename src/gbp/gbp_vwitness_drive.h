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

/* Applies the rule for one `gbp_vstate_block()` call. Call it immediately after
 * the assembler returns and BEFORE any publication hook: what is retained must
 * not depend on what a consumer was willing to accept. */
static void gbp_vwitness_step(struct gbp_vwitness *w, const struct gbp_vstate *st,
                              const struct gbp_vstate_step *step)
{
    if (!w || !st || !step) return;
    if (step->witness_valid && step->witness_place_first)
        gbp_vwitness_place_step(w, st, step);
    if (step->frame_closed)         gbp_vwitness_commit_step(w, st, step);
    else if (step->witness_reset)   gbp_vwitness_discard(w);
    if (step->witness_valid && !step->witness_place_first)
        gbp_vwitness_place_step(w, st, step);
}

#ifdef __cplusplus
}
#endif
#endif
