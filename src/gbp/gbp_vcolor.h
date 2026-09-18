/*
 * gbp_vcolor.h — the capture state machine of GBP-VIDEO-003, the controlled
 * colour experiment (HARDWARE_TESTS §V3.10 to §V3.13, §V3.23 to §V3.25).
 *
 * WHAT THIS MODULE KNOWS, AND WHAT IT MUST NEVER KNOW
 *
 * It knows: whether a frame is eligible, whether the frame just closed carries
 * the same 40 block signatures as the one before it, how many such frames have
 * arrived in a row, which ring slot each of them occupies, and when to stop.
 * That is all the runtime needs in order to preserve the right bytes.
 *
 * It does NOT know the eight stimulus values, it does not reconstruct a pixel,
 * it does not separate bit 15, it does not name a channel and it does not hold
 * any hypothesis. A runtime that recognised `0x001F` on the wire would be
 * deciding the experiment's question with the experiment's own answer; the
 * values live in the stimulus ROM and in the offline analyser, and the audit
 * profile checks that none of them appears in this object (§V3.11).
 *
 * The consequence is a pleasant one: a flash-cart menu, a BIOS screen or a
 * half-drawn framebuffer can certify here just as well as the stimulus, and
 * nothing is lost by that - the analyser is what decides whether the preserved
 * bytes are the pattern. The probe's job is only to identify THREE CONSECUTIVE
 * ELIGIBLE FRAMES THE DEVICE PRESENTED AS THE SAME PICTURE, whatever they show.
 *
 * ---- THE TIMING CONTRACT, which is why this file was rewritten -------------
 *
 * The first implementation compared whole frames here: `memcmp` over 153 600
 * bytes, and a `memcpy` of the same size, at every eligible frame close. That
 * runs between the ACK and the RE-ARM, and the microaudit of 2026-09-17 refused
 * it: it is ~81x the bytes and ~700x the frequency of the only full-frame work
 * that window has ever physically survived, in the window whose next cause the
 * hardware asserts 1.90..2.32 us later (vstate-0004, 29/29 SOURCE_SERVICED).
 *
 * THE RULE NOW, and every test in tests/unit/test_gbp_vcolor.c pins it:
 *
 *     NOTHING IN THIS MODULE TOUCHES A FRAME'S BYTES. EVER.
 *
 * gbp_vcolor_frame() receives a frame RECORD and a SLOT INDEX. Its whole cost
 * is one eligibility test on fields already in a cache line, at most 40 word
 * comparisons (160 bytes) against the run's reference signature vector, and a
 * bounded record write. No memcmp, no memcpy, no CRC, no hash, no scan, no
 * pointer into the ring is even formed.
 *
 * ---- WHAT THE SIGNATURE IS, AND WHAT IT IS NOT ----------------------------
 *
 * `sig[40]` is the per-block checksum the state model ALREADY computes in that
 * same window. Reusing it introduces no new computation of the signature itself.
 *
 * ONE THING THIS FILE WILL NOT CLAIM. The physical figure "median 823 ticks over
 * 420 073 samples" belongs to `gbp_vsig_block()` - the EXISTING per-VIDEO-BLOCK
 * signature - and to nothing else. The new work here is the per-FRAME-CLOSE
 * comparison of 40 words, and it has NOT been measured on hardware. What can be
 * said is what is true by construction: it is bounded at 40 word comparisons and
 * at most 160 bytes copied, it adds no device operation, and it replaces paths
 * that moved 153 600 and 307 200 bytes. It must NOT be described as
 * timing-neutral, timing-equivalent, or as costing less than one tick: no such
 * measurement exists, and inventing one would be the same class of error the
 * first implementation was refused for.
 *
 * WHAT THE SIGNATURE DECIDES. One thing: that the candidate window is stable
 * enough to be worth preserving. It is NOT the scientific claim. The runtime's statement is
 *
 *     "three signature-identical eligible frames"
 *
 * and the offline analyser's, from the raw bytes, is
 *
 *     "the three certified raw frames are byte-for-byte equal"
 *
 * Those are different sentences and this file never writes the second one. A
 * signature collision would be caught offline, where the bytes are; that is
 * exactly why the raw is still preserved and still the authority (§V3.16).
 *
 * ---- WHY NO RAW BUFFER EXISTS HERE ANY MORE -------------------------------
 *
 * The certified frames stay where the DMA put them, in the state model's ring.
 * Four slots are enough for A, B and C to be intact at the moment C closes, the
 * run stops at that moment without admitting another scientific delivery, and
 * the OGBPCOL1 writer streams the three slots straight to the card after the
 * hardware is down. The 460 800-byte staging buffer the first implementation
 * needed is gone, and with it every copy inside the capture (§V3.24).
 */
#ifndef OPENGBP_GBP_VCOLOR_H
#define OPENGBP_GBP_VCOLOR_H

#include <stdint.h>
#include "gbp_vstate.h"

#ifdef __cplusplus
extern "C" {
#endif

/* A certified frame is exactly 40 blocks of 0xF00; anything else is not a
 * complete frame and is not eligible (§V3.10). */
#define GBP_VCOLOR_BLOCKS        40u
#define GBP_VCOLOR_FRAME_BYTES   (GBP_VCOLOR_BLOCKS * GBP_VSTATE_VIDEO_BLOCK_SIZE)   /* 153600 */
#define GBP_VCOLOR_CERT_FRAMES   3u                                                  /* A, B, C */
#define GBP_VCOLOR_RAW_BYTES     (GBP_VCOLOR_CERT_FRAMES * GBP_VCOLOR_FRAME_BYTES)   /* 460800 serialized */
#define GBP_VCOLOR_N_STABLE      3u
#define GBP_VCOLOR_MAX_FRAMES    1024u   /* the bounded frame table: ~17 s at 59.7 Hz */

/* ---- the run envelope of §V3.12, each number justified where it is used ----
 * None of them is inherited from the vstate probe: that experiment's 120 s came
 * from the Start-up Disc's detector window, and this one only has to find three
 * stable frames and stop. */
/* ---- the fixed pre-handler wait (§V3.28) --------------------------------
 * The probe itself starts the AGB: stage A writes CONTROL 0x90 -> 0x8C, and
 * capture opens 107 ms later at the first unmask. `vstate-0004` measured three
 * consecutive signature-identical clean frames 77 ms after that, so without a
 * wait this experiment would certify inside the AGB's boot animation - a run
 * spent on a picture that is not the stimulus (§V3.26).
 *
 * The operator cannot fix that by watching: nothing renders the AGB's video at
 * that point, which §V3.27 established from the source. So the capture is
 * delayed instead, in the one position where the AGB is already running and no
 * service transaction is in flight, and where 5000 ms was PHYSICALLY TOLERATED
 * by the Game Boy Player (GBP-HW-116 to GBP-HW-118).
 *
 * WHAT THIS NUMBER IS AND IS NOT. That the position tolerates 5 s is FACT. That
 * 5 s is ENOUGH for the cartridge boot to reach the static bars is UNKNOWN, and
 * the first physical run of this experiment is what establishes it. If it is
 * not enough, the analyser refuses the window rather than mapping it: a boot or
 * transition frame is not eight uniform bars, and a non-uniform bar is
 * `inconclusive_bar_not_uniform`. A wrong answer is not among the outcomes. */
#define GBP_VCOLOR_PREHANDLER_WAIT_MS   5000u

#define GBP_VCOLOR_SEARCH_SECONDS        10u      /* SEARCH_WINDOW */
#define GBP_VCOLOR_HARD_WALLCLOCK_SECONDS 30u     /* safety, and it always wins */
#define GBP_VCOLOR_MAX_DELIVERIES    250000u      /* ~40 s at the rate vstate-0004 measured */

/* Why a frame was refused as evidence. Recorded per frame so an offline reader
 * can see the whole sequence, not just the certified window. One reason per
 * frame, in the order they are tested. */
#define GBP_VCOLOR_OK                 0u
#define GBP_VCOLOR_NOT_COMPLETE       1u   /* not COMPLETE_40 */
#define GBP_VCOLOR_WRONG_BLOCKS       2u   /* blocks != 40 */
#define GBP_VCOLOR_ANOMALY            3u   /* F_ANOMALY: frame-invalidating */
#define GBP_VCOLOR_RESYNC             4u   /* F_RESYNC: the region is not interpretable */
/* SHADOWED BY CONSTRUCTION, and said here so no reader is misled. The state
 * model sets F_MAJORITY_EXTRA and F_ANOMALY on the same frame, and the predicate
 * below reports the FIRST fault, so a frame quarantined by the majority is
 * refused under GBP_VCOLOR_ANOMALY and this counter stays 0 in a real run. The
 * exclusion still happens - that is what matters - and the authoritative count
 * of quarantined frames is the state model's `sem.frames_quarantined`, which the
 * sidecar carries at 0x1AC. This code remains defined because the predicate is
 * total over the flags it is given, and a synthetic record can separate them. */
#define GBP_VCOLOR_MAJORITY_EXTRA     5u   /* quarantined: a block drained only by the majority */
#define GBP_VCOLOR_SOURCE_DEFERRED    6u   /* a VIDEO drain was deferred inside this frame */
/* Code 7 is RETIRED and is never produced. It was F_PRE_BASELINE, inherited
 * from the vstate probe's change detector. GBP-VIDEO-003 asks a different
 * question: it does not compare against a learned reference, it looks for its
 * own stable window, so whether the OTHER experiment's baseline had settled
 * says nothing about this frame's integrity, the protocol's correctness or the
 * raw lifecycle (§V3.25). The code stays reserved so the file layout does not
 * move, and both parsers REFUSE a file that uses it. */
#define GBP_VCOLOR_RETIRED_PRE_BASELINE 7u
#define GBP_VCOLOR_NO_SLOT            8u   /* the closed frame has no valid ring slot */
#define GBP_VCOLOR_REASONS            9u

/* The bounded per-frame record. No raw here, and no pointer to any. */
struct gbp_vcolor_frame {
    uint64_t t_first, t_last;    /* the frame's own block timestamps */
    uint32_t index;              /* the state model's frame index */
    uint32_t blocks;
    uint16_t flags;              /* GBP_VSTATE_F_* verbatim */
    uint16_t reason;             /* GBP_VCOLOR_* */
    uint32_t run_len_after;      /* consecutive signature-identical eligible frames after this one */
    uint32_t sig0, sig39;        /* two of the model's per-block signatures, for the log only */
};

/* One of the three certified frames. `ring_slot` is where its bytes still are;
 * `order` is 0/1/2 = A/B/C, the order they arrived in. Nothing here is a
 * conclusion: it identifies bytes, it does not describe them. */
struct gbp_vcolor_cert {
    uint32_t frame_index;
    uint32_t blocks;
    uint64_t t_first, t_last;
    uint32_t raw_offset;         /* byte offset inside the file's raw VIDEO section */
    uint16_t ring_slot;          /* the state model's ring slot holding these bytes */
    uint16_t order;              /* 0 = A, 1 = B, 2 = C */
    uint32_t sig0, sig39;        /* so a certified frame is identifiable without the frame table */
};

struct gbp_vcolor {
    /* caller-owned storage: the frame table, and nothing else. */
    struct gbp_vcolor_frame *frames;
    uint32_t frames_cap, frames_n;
    uint32_t frames_dropped;              /* frames past the table cap: counted, never overwritten */

    /* the run of consecutive signature-identical eligible frames */
    uint32_t ref_sig[GBP_VSTATE_FRAME_SIGS];   /* 40 words = 160 bytes: the whole comparison */
    uint32_t run_len;
    uint32_t run_first_index;             /* the frame index that started the current run */

    /* certification */
    int certified;                        /* 1 once run_len reached N_STABLE */
    uint64_t t_certified;
    struct gbp_vcolor_cert cert[GBP_VCOLOR_CERT_FRAMES];
    uint32_t cert_n;

    /* aggregate counters, all bounded */
    uint32_t frames_total, frames_eligible, frames_refused[GBP_VCOLOR_REASONS];
    uint32_t resets;                      /* runs broken before reaching N_STABLE */
    uint32_t sig_mismatches;              /* eligible frames whose signature broke a run */
};

/* Attaches the caller's frame table. With no table the module still counts and
 * still certifies: the table is a log, not evidence. */
void gbp_vcolor_init(struct gbp_vcolor *c, struct gbp_vcolor_frame *frames, uint32_t frames_cap);

/* THE eligibility predicate, in one place (§V3.10). Pure: it reads the frame
 * record and nothing else, so every caller and every test asks the same
 * question. Returns GBP_VCOLOR_OK or the first reason that refused it. */
unsigned gbp_vcolor_eligible(const struct gbp_vstate_frame *f);

/* One closed frame. `slot` is the ring slot the state model closed it into, or
 * negative when there is none. Returns 1 when this frame certified the window
 * (the transition, once per run).
 *
 * COST, and it is the point of this revision: one eligibility test, at most 40
 * word comparisons, one bounded record write. It reads no frame bytes, forms no
 * pointer into the ring, allocates nothing, formats nothing, reads no clock of
 * its own and touches no device. */
int gbp_vcolor_frame(struct gbp_vcolor *c, const struct gbp_vstate_frame *f, int slot, uint64_t t);

/* 1 when the capture is finished. Certification IS the end: there is no hold
 * window, because holding would mean servicing 60 more frames and the ring
 * would wrap over A, B and C long before that (§V3.24). */
int gbp_vcolor_done(const struct gbp_vcolor *c);

/* 1 when the certified slots are still usable as evidence: exactly cert_n of
 * them, each in range, all distinct, and none of them the slot the assembler is
 * currently filling. Called AFTER the teardown, before serialization - it turns
 * the ring-lifecycle argument into a check instead of an assumption (§V3.24). */
int gbp_vcolor_slots_ok(const struct gbp_vcolor *c, const struct gbp_vstate *st);

const char *gbp_vcolor_reason_name(unsigned reason);
/* Static footprint of the stores this module needs, for the memory audit. */
uint64_t gbp_vcolor_static_bytes(void);

#ifdef __cplusplus
}
#endif
#endif
