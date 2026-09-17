/*
 * test_gbp_vcolor.c — GBP-VIDEO-003's capture state machine and its OGBPCOL1
 * sidecar. Every scenario here is SYNTHETIC and none of it is evidence about
 * the device.
 *
 * THREE properties matter most, and all three are negative:
 *
 *   1. the runtime must NOT be able to recognise the stimulus;
 *   2. a frame the R3 policy excluded must NOT be able to become evidence;
 *   3. the capture must NOT touch a frame's bytes inside the service window.
 *
 * (3) is what the microaudit of 2026-09-17 blocked the first implementation
 * over, and it is pinned here two ways: gbp_vcolor_frame() no longer has a
 * parameter through which bytes could reach it, and a ring-lifecycle test drives
 * the real assembler to prove the three certified frames are still intact -
 * uncopied, where the DMA left them - at the moment the run stops.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gbp_vcolor.h"
#include "gbp_vcoldump.h"
#include "gbp_vstate.h"
#include "gbp_crc32.h"

static int failures, checks;
#define CHECK(cond) do { checks++; if (!(cond)) { failures++; \
    printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); } } while (0)

static struct gbp_vcolor_frame frames[GBP_VCOLOR_MAX_FRAMES];
static uint8_t scratch[GBP_VCOLOR_FRAME_BYTES];
static uint8_t file[1u << 21];
static uint8_t chunk[GBP_VCOLDUMP_CHUNK];

/* The state model's storage, at the FOUR slots GBP-VIDEO-003 supplies. */
static uint8_t ring[GBP_VSTATE_RAW_RING_BYTES_4];
static uint8_t ep_raw[GBP_VSTATE_EPISODE_RAW_BYTES];
static uint8_t au_raw[GBP_VSTATE_AUDIO_RAW_BYTES];
static struct gbp_vstate_frame vframes[GBP_VSTATE_MAX_FRAMES];
static struct gbp_vstate_event vevents[GBP_VSTATE_MAX_EVENTS];

/* A synthetic frame record. The colour module reads ONLY this record; since the
 * timing fix it has no parameter through which a frame's bytes could reach it. */
static void mkframe(struct gbp_vstate_frame *f, uint32_t index, uint16_t flags, uint16_t completeness,
                    uint16_t blocks, uint64_t t)
{
    memset(f, 0, sizeof *f);
    f->index = index;
    f->blocks = blocks;
    f->flags = flags;
    f->completeness = completeness;
    f->t_first_block = t;
    f->t_last_block = t + 100u;
}

/* The 40 per-block signatures. `pic` is which picture the frame shows: two
 * frames with the same `pic` carry the same vector, which is exactly what the
 * runtime now compares. */
static void mksig(struct gbp_vstate_frame *f, uint32_t pic)
{
    unsigned i;
    for (i = 0; i < GBP_VSTATE_FRAME_SIGS; i++) f->sig[i] = pic * 0x01000193u + i * 2654435761u;
}

static void mkframe_pic(struct gbp_vstate_frame *f, uint32_t index, uint16_t flags, uint32_t pic, uint64_t t)
{
    mkframe(f, index, flags, GBP_VSTATE_FRAME_COMPLETE_40, 40u, t);
    mksig(f, pic);
}

/* Fills a synthetic frame body. `seed` changes the bytes; nothing about the
 * content means anything to the module under test. */
static void mkraw(uint8_t *dst, uint32_t seed)
{
    uint32_t i;
    for (i = 0; i < GBP_VCOLOR_FRAME_BYTES; i++)
        dst[i] = (uint8_t)((i * 31u + seed * 17u) >> 3);
}

static const uint16_t OK_FLAGS = GBP_VSTATE_F_COMPLETE;

static void test_eligibility_is_one_predicate(void)
{
    struct gbp_vstate_frame f;
    printf("-- one predicate decides what may become colour evidence, and it names the first fault\n");
    mkframe(&f, 1u, OK_FLAGS, GBP_VSTATE_FRAME_COMPLETE_40, 40u, 1000u);
    CHECK(gbp_vcolor_eligible(&f) == GBP_VCOLOR_OK);
    /* every exclusion of §V3.10, one at a time, in the order the predicate tests them */
    mkframe(&f, 2u, OK_FLAGS, GBP_VSTATE_FRAME_INCOMPLETE_SHORT, 40u, 1000u);
    CHECK(gbp_vcolor_eligible(&f) == GBP_VCOLOR_NOT_COMPLETE);
    mkframe(&f, 3u, OK_FLAGS, GBP_VSTATE_FRAME_COMPLETE_40, 39u, 1000u);
    CHECK(gbp_vcolor_eligible(&f) == GBP_VCOLOR_WRONG_BLOCKS);
    mkframe(&f, 4u, (uint16_t)(OK_FLAGS | GBP_VSTATE_F_ANOMALY), GBP_VSTATE_FRAME_COMPLETE_40, 40u, 1000u);
    CHECK(gbp_vcolor_eligible(&f) == GBP_VCOLOR_ANOMALY);
    mkframe(&f, 5u, (uint16_t)(OK_FLAGS | GBP_VSTATE_F_RESYNC), GBP_VSTATE_FRAME_COMPLETE_40, 40u, 1000u);
    CHECK(gbp_vcolor_eligible(&f) == GBP_VCOLOR_RESYNC);
    /* THE TWO R3 EXCLUSIONS. A quarantined frame may never be colour evidence,
     * whatever else is true of it (§R3.12, §V3.9). */
    mkframe(&f, 6u, (uint16_t)(OK_FLAGS | GBP_VSTATE_F_MAJORITY_EXTRA), GBP_VSTATE_FRAME_COMPLETE_40, 40u, 1000u);
    CHECK(gbp_vcolor_eligible(&f) == GBP_VCOLOR_MAJORITY_EXTRA);
    mkframe(&f, 7u, (uint16_t)(OK_FLAGS | GBP_VSTATE_F_SOURCE_DEFERRED), GBP_VSTATE_FRAME_COMPLETE_40, 40u, 1000u);
    CHECK(gbp_vcolor_eligible(&f) == GBP_VCOLOR_SOURCE_DEFERRED);
    /* F_PRE_BASELINE is NOT an exclusion any more: the vstate baseline answers a
     * different question and says nothing about this frame (§V3.25). */
    mkframe(&f, 8u, (uint16_t)(OK_FLAGS | GBP_VSTATE_F_PRE_BASELINE), GBP_VSTATE_FRAME_COMPLETE_40, 40u, 1000u);
    CHECK(gbp_vcolor_eligible(&f) == GBP_VCOLOR_OK);
    /* a quarantined frame that is ALSO incomplete reports the first fault, not the last */
    mkframe(&f, 9u, (uint16_t)(OK_FLAGS | GBP_VSTATE_F_MAJORITY_EXTRA), GBP_VSTATE_FRAME_RESYNC, 40u, 1000u);
    CHECK(gbp_vcolor_eligible(&f) == GBP_VCOLOR_NOT_COMPLETE);
    /* the retired code is never returned by the predicate, for any input */
    CHECK(gbp_vcolor_eligible(0) == GBP_VCOLOR_NOT_COMPLETE);
    printf("   6 exclusions, each named, in the design's order; PRE_BASELINE retired\n");
}

/* ---- §V3.23: what the capture costs, and the sequences it accepts -------- */

static void test_the_capture_never_receives_frame_bytes(void)
{
    struct gbp_vcolor c;
    struct gbp_vstate_frame f;
    printf("-- the capture has no way to touch a frame: A,A,A certifies from sig[40] alone\n");
    gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
    /* Slot indices only. There is no pointer parameter and no length parameter:
     * the type system now enforces what the microaudit had to measure. */
    mkframe_pic(&f, 0u, OK_FLAGS, 7u, 1000u);
    CHECK(gbp_vcolor_frame(&c, &f, 0, 1000u) == 0);
    CHECK(c.run_len == 1u && c.cert_n == 1u && c.cert[0].ring_slot == 0u && c.cert[0].order == 0u);
    mkframe_pic(&f, 1u, OK_FLAGS, 7u, 2000u);
    CHECK(gbp_vcolor_frame(&c, &f, 1, 2000u) == 0);
    CHECK(c.run_len == 2u && c.cert_n == 2u && c.cert[1].ring_slot == 1u && c.cert[1].order == 1u);
    mkframe_pic(&f, 2u, OK_FLAGS, 7u, 3000u);
    CHECK(gbp_vcolor_frame(&c, &f, 2, 3000u) == 1);   /* the transition, exactly once */
    CHECK(c.certified == 1 && c.run_len == 3u && c.cert_n == 3u);
    CHECK(c.cert[2].ring_slot == 2u && c.cert[2].order == 2u);
    CHECK(c.t_certified == 3000u);
    CHECK(c.cert[0].sig0 == f.sig[0] && c.cert[0].sig39 == f.sig[GBP_VSTATE_FRAME_SIGS - 1u]);
    /* certification IS the end: there is no hold window to wait for */
    CHECK(gbp_vcolor_done(&c) == 1);
    /* and nothing is examined afterwards - the run has stopped */
    mkframe_pic(&f, 3u, OK_FLAGS, 7u, 4000u);
    CHECK(gbp_vcolor_frame(&c, &f, 3, 4000u) == 0);
    CHECK(c.frames_total == 3u);
    printf("   certified at the third frame, slots 0/1/2, zero bytes read\n");
}

/* §20 of the fix contract: the four sequences, spelled out. */
static void test_the_run_sequences(void)
{
    struct gbp_vcolor c;
    struct gbp_vstate_frame f;
    printf("-- A,A,A certifies; A,A,B resets; A,B,B,B certifies on the last three\n");

    gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
    mkframe_pic(&f, 0u, OK_FLAGS, 1u, 10u); CHECK(gbp_vcolor_frame(&c, &f, 0, 10u) == 0);
    mkframe_pic(&f, 1u, OK_FLAGS, 1u, 20u); CHECK(gbp_vcolor_frame(&c, &f, 1, 20u) == 0);
    mkframe_pic(&f, 2u, OK_FLAGS, 2u, 30u); CHECK(gbp_vcolor_frame(&c, &f, 2, 30u) == 0);
    CHECK(c.certified == 0);
    CHECK(c.run_len == 1u);                   /* the differing frame STARTS a new run */
    CHECK(c.run_first_index == 2u);
    CHECK(c.resets == 1u && c.sig_mismatches == 1u);

    gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
    mkframe_pic(&f, 0u, OK_FLAGS, 1u, 10u); CHECK(gbp_vcolor_frame(&c, &f, 0, 10u) == 0);
    mkframe_pic(&f, 1u, OK_FLAGS, 2u, 20u); CHECK(gbp_vcolor_frame(&c, &f, 1, 20u) == 0);
    mkframe_pic(&f, 2u, OK_FLAGS, 2u, 30u); CHECK(gbp_vcolor_frame(&c, &f, 2, 30u) == 0);
    mkframe_pic(&f, 3u, OK_FLAGS, 2u, 40u); CHECK(gbp_vcolor_frame(&c, &f, 3, 40u) == 1);
    CHECK(c.certified == 1);
    CHECK(c.cert[0].frame_index == 1u && c.cert[1].frame_index == 2u && c.cert[2].frame_index == 3u);
    CHECK(c.run_first_index == 1u);
    printf("   run restarts at the frame that differs, not at the one after it\n");
}

/* An ineligible frame between two identical ones breaks the sequence, whatever
 * the reason: the design asks for three CONSECUTIVE eligible frames. */
static void test_what_breaks_a_sequence(void)
{
    static const struct { uint16_t flags; uint16_t completeness; uint16_t blocks; unsigned reason;
                          const char *what; } BREAK[] = {
        { GBP_VSTATE_F_COMPLETE, GBP_VSTATE_FRAME_UNKNOWN, 40u, GBP_VCOLOR_NOT_COMPLETE, "incomplete" },
        { GBP_VSTATE_F_COMPLETE, GBP_VSTATE_FRAME_COMPLETE_40, 39u, GBP_VCOLOR_WRONG_BLOCKS, "39 blocks" },
        { (uint16_t)(GBP_VSTATE_F_COMPLETE | GBP_VSTATE_F_ANOMALY), GBP_VSTATE_FRAME_COMPLETE_40, 40u,
          GBP_VCOLOR_ANOMALY, "anomaly" },
        { (uint16_t)(GBP_VSTATE_F_COMPLETE | GBP_VSTATE_F_RESYNC), GBP_VSTATE_FRAME_COMPLETE_40, 40u,
          GBP_VCOLOR_RESYNC, "resync" },
        { (uint16_t)(GBP_VSTATE_F_COMPLETE | GBP_VSTATE_F_MAJORITY_EXTRA), GBP_VSTATE_FRAME_COMPLETE_40,
          40u, GBP_VCOLOR_MAJORITY_EXTRA, "majority-extra quarantine" },
        { (uint16_t)(GBP_VSTATE_F_COMPLETE | GBP_VSTATE_F_SOURCE_DEFERRED), GBP_VSTATE_FRAME_COMPLETE_40,
          40u, GBP_VCOLOR_SOURCE_DEFERRED, "deferred VIDEO drain" }
    };
    unsigned k;
    printf("-- six ways to break a sequence, each one named and each one fatal to the run\n");
    for (k = 0; k < sizeof BREAK / sizeof BREAK[0]; k++) {
        struct gbp_vcolor c;
        struct gbp_vstate_frame f;
        gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
        mkframe_pic(&f, 0u, OK_FLAGS, 5u, 10u);  CHECK(gbp_vcolor_frame(&c, &f, 0, 10u) == 0);
        mkframe_pic(&f, 1u, OK_FLAGS, 5u, 20u);  CHECK(gbp_vcolor_frame(&c, &f, 1, 20u) == 0);
        /* the interloper carries the SAME picture: only its status differs */
        mkframe(&f, 2u, BREAK[k].flags, BREAK[k].completeness, BREAK[k].blocks, 30u);
        mksig(&f, 5u);
        CHECK(gbp_vcolor_frame(&c, &f, 2, 30u) == 0);
        CHECK(c.run_len == 0u);
        CHECK(c.frames_refused[BREAK[k].reason] == 1u);
        /* and a third identical frame afterwards is only the FIRST of a new run */
        mkframe_pic(&f, 3u, OK_FLAGS, 5u, 40u);  CHECK(gbp_vcolor_frame(&c, &f, 3, 40u) == 0);
        CHECK(c.certified == 0);
        CHECK(c.run_len == 1u);
    }
    /* A frame with no ring slot is refused for that alone, even when eligible. */
    {
        struct gbp_vcolor c;
        struct gbp_vstate_frame f;
        gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
        mkframe_pic(&f, 0u, OK_FLAGS, 5u, 10u);
        CHECK(gbp_vcolor_frame(&c, &f, -1, 10u) == 0);
        CHECK(c.frames_refused[GBP_VCOLOR_NO_SLOT] == 1u);
        CHECK(c.run_len == 0u);
    }
    printf("   %u breakers plus the missing slot, none of them repairable\n",
           (unsigned)(sizeof BREAK / sizeof BREAK[0]));
}

static void test_a_quarantined_frame_can_never_certify(void)
{
    struct gbp_vcolor c;
    struct gbp_vstate_frame f;
    uint32_t i;
    printf("-- identical quarantined frames, forever: never certified, never preserved\n");
    gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
    for (i = 0; i < 50u; i++) {
        mkframe(&f, i, (uint16_t)(OK_FLAGS | GBP_VSTATE_F_MAJORITY_EXTRA),
                GBP_VSTATE_FRAME_COMPLETE_40, 40u, 10u * i);
        mksig(&f, 3u);
        CHECK(gbp_vcolor_frame(&c, &f, (int)(i % 4u), 10u * i) == 0);
    }
    CHECK(c.certified == 0);
    CHECK(c.frames_eligible == 0u);
    CHECK(c.frames_refused[GBP_VCOLOR_MAJORITY_EXTRA] == 50u);
    printf("   50 identical frames, 0 eligible: the R3 quarantine is not negotiable\n");
}

/* The retired PRE_BASELINE gate: a pre-baseline frame is now eligible, because
 * the OTHER experiment's baseline says nothing about this one (§V3.25). */
static void test_pre_baseline_no_longer_refuses(void)
{
    struct gbp_vcolor c;
    struct gbp_vstate_frame f;
    uint32_t i;
    printf("-- F_PRE_BASELINE no longer excludes: this experiment has its own stability rule\n");
    gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
    for (i = 0; i < 3u; i++) {
        mkframe(&f, i, (uint16_t)(OK_FLAGS | GBP_VSTATE_F_PRE_BASELINE),
                GBP_VSTATE_FRAME_COMPLETE_40, 40u, 10u * i);
        mksig(&f, 11u);
        CHECK(gbp_vcolor_frame(&c, &f, (int)i, 10u * i) == (i == 2u));
    }
    CHECK(c.certified == 1);
    CHECK(c.frames_refused[GBP_VCOLOR_RETIRED_PRE_BASELINE] == 0u);   /* never produced */
    printf("   certified before the vstate baseline existed, and the retired counter stays 0\n");
}

static void test_the_frame_table_caps_without_losing_the_capture(void)
{
    struct gbp_vcolor c;
    struct gbp_vstate_frame f;
    static struct gbp_vcolor_frame small[4];
    uint32_t i;
    printf("-- the frame table caps, is counted, and certification still works\n");
    gbp_vcolor_init(&c, small, 4u);
    for (i = 0; i < 10u; i++) {
        mkframe(&f, i, (uint16_t)(OK_FLAGS | GBP_VSTATE_F_ANOMALY), GBP_VSTATE_FRAME_COMPLETE_40, 40u, 10u * i);
        mksig(&f, 1u);
        gbp_vcolor_frame(&c, &f, 0, 10u * i);
    }
    CHECK(c.frames_n == 4u);
    CHECK(c.frames_dropped == 6u);
    for (i = 0; i < 3u; i++) {
        mkframe_pic(&f, 100u + i, OK_FLAGS, 9u, 1000u + 10u * i);
        gbp_vcolor_frame(&c, &f, (int)i, 1000u + 10u * i);
    }
    CHECK(c.certified == 1);                  /* the history caps; the evidence does not */
    CHECK(c.cert_n == 3u);
    printf("   table 4/10, dropped %u, still certified\n", (unsigned)c.frames_dropped);
}

/* ---- §V3.24: the ring lifecycle, driven through the REAL assembler ------- */

static uint64_t ring_clock;

/* Feeds one 0xF00 VIDEO block into the real state model. `boundary` sets the
 * frame-start bit for BOTH predicates - byte 1 bit 7 for the Start-up Disc
 * reading, byte 0 bit 7 as well for GBI's. Setting only one would make every
 * frame a predicate disagreement, which is an anomaly and therefore not
 * eligible; that is the R3 machinery working, not a fault, but it is not what
 * this test is about. */
static void feed_block(struct gbp_vstate *st, uint32_t pic, int boundary, struct gbp_vstate_step *step)
{
    uint8_t *tgt = gbp_vstate_video_target(st);
    uint8_t first4[4];
    uint32_t k;
    if (!tgt) { CHECK(tgt != 0); return; }
    for (k = 0; k < GBP_VSTATE_VIDEO_BLOCK_SIZE; k += 4u) {
        tgt[k] = 0x7F; tgt[k + 1] = 0x7F;
        tgt[k + 2] = (uint8_t)(0xFFu - (unsigned)pic);
        tgt[k + 3] = (uint8_t)(0xFFu - (unsigned)pic);
    }
    if (boundary) { tgt[0] = 0xFF; tgt[1] = 0xFF; }
    first4[0] = tgt[0]; first4[1] = tgt[1]; first4[2] = tgt[2]; first4[3] = tgt[3];
    ring_clock += 1000u;
    gbp_vstate_block(st, tgt, GBP_VSTATE_VIDEO_BLOCK_SIZE, first4,
                     ring_clock, gbp_vsig_block(tgt, GBP_VSTATE_VIDEO_BLOCK_SIZE), 800u, step);
}

/* Drives the assembler exactly the way the probe does, and STOPS THE WAY THE
 * PROBE STOPS: the moment the capture certifies, no further VIDEO block is
 * drained. That is the whole stop argument of §V3.24 - certification happens in
 * the frame-close hook, the current transaction finishes normally, and the next
 * CHECK_ADMISSION ends the run before another delivery is admitted - so the ring
 * is frozen where certification left it. A test that kept feeding would be
 * modelling a probe that does not exist. Returns the blocks fed. */
static uint32_t feed_until_certified(struct gbp_vstate *st, struct gbp_vcolor *c, uint32_t pic,
                                     uint32_t max_frames)
{
    struct gbp_vstate_step step;
    uint32_t b, fed = 0u;
    for (b = 0; b < max_frames * GBP_VCOLOR_BLOCKS; b++) {
        feed_block(st, pic, (b % GBP_VCOLOR_BLOCKS) == 0u, &step);
        fed++;
        if (step.frame_closed && st->frames_n > 0u && c) {
            uint32_t blocks = 0u;
            int slot = gbp_vstate_closed_frame_slot(st, &blocks);
            if (blocks != GBP_VCOLOR_BLOCKS) slot = -1;
            if (gbp_vcolor_frame(c, &st->frames[st->frames_n - 1u], slot, ring_clock)) return fed;
        }
    }
    return fed;
}

/* §3 of the second microaudit: the slot count is DERIVED, and a buffer the model
 * cannot describe is refused rather than quietly reinterpreted. */
static void test_the_ring_size_contract(void)
{
    static struct gbp_vstate st;
    static uint8_t big[5u * GBP_VSTATE_RAW_FRAME_BYTES];
    static const struct { uint32_t slots; uint32_t want; const char *what; } CASE[] = {
        { 0u, 0u, "no whole frame" },
        { 1u, 0u, "one slot" },
        { 2u, 0u, "two slots" },
        { 3u, 3u, "three slots: GBP-VIDEO-002" },
        { 4u, 4u, "four slots: GBP-VIDEO-003" },
        { 5u, 0u, "five slots: refused, never clamped to four" }
    };
    unsigned k;
    printf("-- the ring size is derived from the buffer, and only 3 or 4 are describable\n");
    for (k = 0; k < sizeof CASE / sizeof CASE[0]; k++) {
        gbp_vstate_init(&st, vframes, GBP_VSTATE_MAX_FRAMES, vevents, GBP_VSTATE_MAX_EVENTS,
                        big, CASE[k].slots * GBP_VSTATE_RAW_FRAME_BYTES,
                        ep_raw, sizeof ep_raw, au_raw, sizeof au_raw);
        CHECK(gbp_vstate_ring_slots(&st) == CASE[k].want);
        CHECK(gbp_vstate_storage_ok(&st) == (CASE[k].want != 0u ? 1 : 0));
    }
    /* a size BETWEEN two whole frames is not three frames either */
    gbp_vstate_init(&st, vframes, GBP_VSTATE_MAX_FRAMES, vevents, GBP_VSTATE_MAX_EVENTS,
                    big, 3u * GBP_VSTATE_RAW_FRAME_BYTES - 1u, ep_raw, sizeof ep_raw, au_raw, sizeof au_raw);
    CHECK(gbp_vstate_ring_slots(&st) == 0u);
    CHECK(gbp_vstate_storage_ok(&st) == 0);
    /* a NULL ring is not a ring */
    gbp_vstate_init(&st, vframes, GBP_VSTATE_MAX_FRAMES, vevents, GBP_VSTATE_MAX_EVENTS,
                    0, GBP_VSTATE_RAW_RING_BYTES, ep_raw, sizeof ep_raw, au_raw, sizeof au_raw);
    CHECK(gbp_vstate_ring_slots(&st) == 0u);
    /* and the budget helper follows the same contract */
    CHECK(gbp_vstate_static_bytes_for(3u) == gbp_vstate_static_bytes());
    CHECK(gbp_vstate_static_bytes_for(4u) == gbp_vstate_static_bytes() + GBP_VSTATE_RAW_FRAME_BYTES);
    CHECK(gbp_vstate_static_bytes_for(2u) == 0u);
    CHECK(gbp_vstate_static_bytes_for(5u) == 0u);
    printf("   0/1/2/5 slots and a partial frame refused; 3 and 4 accepted\n");
}

static void test_the_ring_keeps_A_B_C_until_the_teardown(void)
{
    static struct gbp_vstate st;
    struct gbp_vcolor c;
    int certified = 0;
    uint32_t slot_a, slot_b, slot_c;
    printf("-- the ring lifecycle, through the real assembler: A, B and C survive certification\n");
    gbp_vstate_init(&st, vframes, GBP_VSTATE_MAX_FRAMES, vevents, GBP_VSTATE_MAX_EVENTS,
                    ring, sizeof ring, ep_raw, sizeof ep_raw, au_raw, sizeof au_raw);
    CHECK(gbp_vstate_ring_slots(&st) == 4u);
    CHECK(gbp_vstate_storage_ok(&st) == 1);
    gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
    ring_clock = 0u;
    /* the assembler needs one boundary before any frame exists, so the first
     * interval is the anchor and the first CLOSED frame is the one after it */
    certified = (feed_until_certified(&st, &c, 5u, 8u) < 8u * GBP_VCOLOR_BLOCKS) ? 1 : 0;
    CHECK(certified == 1);
    CHECK(c.certified == 1 && c.cert_n == 3u);
    /* THE CHECK THIS TEST EXISTS FOR: the three certified slots are distinct, in
     * range, and none of them is the slot the assembler is filling. */
    CHECK(gbp_vcolor_slots_ok(&c, &st) == 1);
    slot_a = c.cert[0].ring_slot; slot_b = c.cert[1].ring_slot; slot_c = c.cert[2].ring_slot;
    CHECK(slot_a != slot_b && slot_b != slot_c && slot_a != slot_c);
    CHECK(slot_a != gbp_vstate_current_slot(&st));
    CHECK(slot_b != gbp_vstate_current_slot(&st));
    CHECK(slot_c != gbp_vstate_current_slot(&st));
    /* consecutive frames occupy consecutive slots, which is what makes four
     * enough and three not enough */
    CHECK(slot_b == (slot_a + 1u) % 4u);
    CHECK(slot_c == (slot_b + 1u) % 4u);
    /* the slot being filled is the FOURTH one: the boundary block that closed C
     * went there, which is precisely why three slots are not enough */
    CHECK(gbp_vstate_current_slot(&st) == (slot_c + 1u) % 4u);
    /* and the bytes really are three whole frames, equal to each other */
    {
        const uint8_t *ra = gbp_vstate_ring_frame(&st, slot_a);
        const uint8_t *rb = gbp_vstate_ring_frame(&st, slot_b);
        const uint8_t *rc = gbp_vstate_ring_frame(&st, slot_c);
        CHECK(ra && rb && rc);
        CHECK(memcmp(ra, rb, GBP_VCOLOR_FRAME_BYTES) == 0);
        CHECK(memcmp(ra, rc, GBP_VCOLOR_FRAME_BYTES) == 0);
    }
    printf("   slots A=%u B=%u C=%u, filling=%u, all intact and byte-equal\n",
           (unsigned)slot_a, (unsigned)slot_b, (unsigned)slot_c,
           (unsigned)gbp_vstate_current_slot(&st));
}

/* §4/§5/§16: the RELATION, not one example. The run is made to certify at every
 * possible rotation of the ring by varying the picture for k frames first, and
 * at each one the same three facts must hold: consecutive frames occupy
 * consecutive slots, the slot being filled is the one after C, and A, B and C
 * are byte-equal whole frames. The boundary block that closes C belongs to D. */
static void test_the_lifecycle_holds_at_every_rotation(void)
{
    unsigned k;
    printf("-- the same lifecycle at every rotation of the four-slot ring\n");
    for (k = 0; k < 6u; k++) {
        static struct gbp_vstate st;
        struct gbp_vcolor c;
        struct gbp_vstate_step step;
        uint32_t b, a_slot, b_slot, c_slot, cur, slots;
        int done = 0;
        gbp_vstate_init(&st, vframes, GBP_VSTATE_MAX_FRAMES, vevents, GBP_VSTATE_MAX_EVENTS,
                        ring, sizeof ring, ep_raw, sizeof ep_raw, au_raw, sizeof au_raw);
        gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
        ring_clock = 0u;
        /* k frames of a CHANGING picture push the rotation forward and break
         * every run; then the picture holds still and the run certifies. */
        for (b = 0; b < (k + 8u) * GBP_VCOLOR_BLOCKS && !done; b++) {
            uint32_t frame_no = b / GBP_VCOLOR_BLOCKS;
            feed_block(&st, (frame_no < k + 1u) ? (5u + frame_no) : 200u,
                       (b % GBP_VCOLOR_BLOCKS) == 0u, &step);
            if (step.frame_closed && st.frames_n > 0u) {
                uint32_t nb = 0u;
                int slot = gbp_vstate_closed_frame_slot(&st, &nb);
                if (nb != GBP_VCOLOR_BLOCKS) slot = -1;
                if (gbp_vcolor_frame(&c, &st.frames[st.frames_n - 1u], slot, ring_clock)) done = 1;
            }
        }
        CHECK(done == 1);
        CHECK(c.certified == 1 && c.cert_n == 3u);
        slots = gbp_vstate_ring_slots(&st);
        a_slot = c.cert[0].ring_slot; b_slot = c.cert[1].ring_slot; c_slot = c.cert[2].ring_slot;
        cur = gbp_vstate_current_slot(&st);
        /* THE RELATION, not the index */
        CHECK(b_slot == (a_slot + 1u) % slots);
        CHECK(c_slot == (b_slot + 1u) % slots);
        CHECK(cur == (c_slot + 1u) % slots);
        CHECK(cur != a_slot && cur != b_slot && cur != c_slot);
        CHECK(gbp_vcolor_slots_ok(&c, &st) == 1);
        {
            const uint8_t *ra = gbp_vstate_ring_frame(&st, a_slot);
            const uint8_t *rb = gbp_vstate_ring_frame(&st, b_slot);
            const uint8_t *rc = gbp_vstate_ring_frame(&st, c_slot);
            CHECK(ra && rb && rc);
            CHECK(memcmp(ra, rb, GBP_VCOLOR_FRAME_BYTES) == 0);
            CHECK(memcmp(ra, rc, GBP_VCOLOR_FRAME_BYTES) == 0);
            /* §5, BOUNDARY BLOCK OWNERSHIP, stated exactly. Every frame's own
             * block 0 IS a boundary block - the one that closed its predecessor
             * and was moved into its slot. What must not happen is the boundary
             * that closes C being counted as part of C: C holds exactly 40
             * blocks, its LAST block is not a boundary, and the boundary that
             * ended it is block 0 of D, in the slot now being filled. */
            CHECK(st.frames[c.cert[2].frame_index].blocks == GBP_VCOLOR_BLOCKS);
            CHECK(rc[1] == 0xFFu);                                        /* C block 0: the boundary that closed B */
            CHECK(rc[(GBP_VCOLOR_BLOCKS - 1u) * GBP_VSTATE_VIDEO_BLOCK_SIZE + 1u] != 0xFFu);  /* C block 39: not */
            CHECK(gbp_vstate_ring_frame(&st, cur)[1] == 0xFFu);           /* D block 0: the boundary that closed C */
        }
    }
    printf("   6 rotations, relation holds at each, boundary block owned by D\n");
}

/* §23/§24: the R3 exclusions through the REAL assembler at FOUR slots. A
 * majority-extra VIDEO block that arrives ON a boundary must contaminate the
 * frame that ACCUMULATES it - the new one - and leave the frame it closed
 * clean; the colour capture must then refuse the new one and keep the old one
 * eligible. Four slots must not change any of that. */
static void test_majority_extra_at_a_boundary_with_four_slots(void)
{
    static struct gbp_vstate st;
    struct gbp_vcolor c;
    struct gbp_vstate_step step;
    uint32_t b, closed = 0u;
    int marked = 0;
    printf("-- majority-extra on a boundary block, four slots: it contaminates D, never C\n");
    gbp_vstate_init(&st, vframes, GBP_VSTATE_MAX_FRAMES, vevents, GBP_VSTATE_MAX_EVENTS,
                    ring, sizeof ring, ep_raw, sizeof ep_raw, au_raw, sizeof au_raw);
    CHECK(gbp_vstate_ring_slots(&st) == 4u);
    gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
    ring_clock = 0u;
    for (b = 0; b < 5u * GBP_VCOLOR_BLOCKS; b++) {
        int boundary = (b % GBP_VCOLOR_BLOCKS) == 0u;
        /* The suspect block is the boundary that closes the FIRST frame. It has
         * to land before three clean frames could certify, or the run would end
         * before the quarantine was ever reached and the test would prove
         * nothing. */
        if (boundary && b == GBP_VCOLOR_BLOCKS && !marked) {
            gbp_vstate_block_majority_extra(&st);
            marked = 1;
        }
        feed_block(&st, 5u, boundary, &step);
        if (step.frame_closed && st.frames_n > 0u) {
            uint32_t nb = 0u;
            int slot = gbp_vstate_closed_frame_slot(&st, &nb);
            const struct gbp_vstate_frame *fr = &st.frames[st.frames_n - 1u];
            if (nb != GBP_VCOLOR_BLOCKS) slot = -1;
            closed++;
            if (closed == 1u) {
                /* the frame the suspect block CLOSED: untouched */
                CHECK((fr->flags & GBP_VSTATE_F_MAJORITY_EXTRA) == 0u);
                CHECK(gbp_vcolor_eligible(fr) == GBP_VCOLOR_OK);
            }
            if (closed == 2u) {
                /* The frame that ACCUMULATED it: quarantined, and refused. The
                 * REASON it is refused under is ANOMALY, not MAJORITY_EXTRA, and
                 * that is not a bug - gbp_vstate_block() sets F_MAJORITY_EXTRA
                 * and F_ANOMALY together, and the predicate reports the FIRST
                 * fault. GBP_VCOLOR_MAJORITY_EXTRA is therefore a label the real
                 * state model never produces; the authoritative count of
                 * quarantined frames is st->sem.frames_quarantined, which the
                 * sidecar carries at 0x1AC. This test pins that, so nobody later
                 * reads frames_refused[MAJORITY_EXTRA] == 0 as "none were
                 * quarantined". */
                CHECK((fr->flags & GBP_VSTATE_F_MAJORITY_EXTRA) != 0u);
                CHECK((fr->flags & GBP_VSTATE_F_ANOMALY) != 0u);
                CHECK(gbp_vcolor_eligible(fr) == GBP_VCOLOR_ANOMALY);
            }
            (void)gbp_vcolor_frame(&c, fr, slot, ring_clock);
        }
    }
    CHECK(closed >= 3u);
    CHECK(c.frames_refused[GBP_VCOLOR_MAJORITY_EXTRA] == 0u);   /* shadowed, by construction */
    CHECK(c.frames_refused[GBP_VCOLOR_ANOMALY] == 1u);
    CHECK(st.sem.frames_quarantined == 1u);                     /* the authoritative counter */
    CHECK(c.certified == 0);                 /* the quarantine broke the only possible run */
    CHECK(c.resets >= 1u);
    printf("   %lu frames closed, 1 quarantined (counted as anomaly), nothing certified\n",
           (unsigned long)closed);
}

/* The counter-proof, and the reason the ring grew: with THREE slots the frame
 * that opened the run is destroyed at the instant the third one closes. */
static void test_three_slots_would_destroy_the_first_frame(void)
{
    static struct gbp_vstate st;
    struct gbp_vcolor c;
    static uint8_t ring3[GBP_VSTATE_RAW_RING_BYTES];
    int certified = 0;
    uint32_t slot_a;
    printf("-- why four slots: with three, frame A is overwritten as frame C closes\n");
    gbp_vstate_init(&st, vframes, GBP_VSTATE_MAX_FRAMES, vevents, GBP_VSTATE_MAX_EVENTS,
                    ring3, sizeof ring3, ep_raw, sizeof ep_raw, au_raw, sizeof au_raw);
    CHECK(gbp_vstate_ring_slots(&st) == 3u);
    gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
    ring_clock = 0u;
    certified = (feed_until_certified(&st, &c, 5u, 8u) < 8u * GBP_VCOLOR_BLOCKS) ? 1 : 0;
    CHECK(certified == 1);
    CHECK(c.certified == 1);
    slot_a = c.cert[0].ring_slot;
    /* the slot that held A is the very slot the assembler is now filling */
    CHECK(slot_a == gbp_vstate_current_slot(&st));
    /* so the guard refuses to call these bytes evidence */
    CHECK(gbp_vcolor_slots_ok(&c, &st) == 0);
    printf("   A was in slot %u, which is the slot being filled: refused, as it must be\n",
           (unsigned)slot_a);
}

/* ---- the OGBPCOL1 sidecar --------------------------------------------- */
struct memsink { uint8_t *buf; uint32_t cap, n, fail_after; int failed; };

static int sink_mem(void *ctx, const uint8_t *data, uint32_t len)
{
    struct memsink *s = (struct memsink *)ctx;
    if (s->fail_after && s->n + len > s->fail_after) { s->failed = 1; return -1; }
    if (s->n + len > s->cap) { s->failed = 1; return -1; }
    memcpy(s->buf + s->n, data, len);
    s->n += len;
    return 0;
}

static void put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v;
}
static void put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static uint16_t get16_at(const uint8_t *p) { return (uint16_t)(((uint16_t)p[0] << 8) | p[1]); }

/* A capture with three certified frames, one preserved disagreement and a
 * teardown, built through the real modules and serialized by the real writer. */
static long build_file(struct gbp_vcolor *c, struct gbp_vstate *st, struct gbp_vstate_result *res,
                       struct gbp_vstate_config *cfg, struct gbp_vcoldump_info *info,
                       struct gbp_vcolor_frame *ftab, uint32_t ftab_cap,
                       uint32_t seed, int with_diag)
{
    struct gbp_vstate_frame f;
    struct memsink sink;
    uint32_t i;
    gbp_vcolor_init(c, ftab, ftab_cap);
    /* A REAL state model with a REAL four-slot ring: the writer streams the raw
     * out of the ring now, so a zeroed stand-in would not exercise the path the
     * probe actually uses. */
    gbp_vstate_init(st, vframes, GBP_VSTATE_MAX_FRAMES, vevents, GBP_VSTATE_MAX_EVENTS,
                    ring, sizeof ring, ep_raw, sizeof ep_raw, au_raw, sizeof au_raw);
    memset(res, 0, sizeof *res);
    memset(cfg, 0, sizeof *cfg);
    cfg->a.tb_hz = 40500000u;
    cfg->hard_wallclock_ticks = (uint64_t)40500000u * GBP_VCOLOR_HARD_WALLCLOCK_SECONDS;
    cfg->color_search_ticks = (uint64_t)40500000u * GBP_VCOLOR_SEARCH_SECONDS;
    cfg->max_deliveries = GBP_VCOLOR_MAX_DELIVERIES;
    res->tb_hz = 40500000u;
    res->service_ok = 1;
    res->restore_ok = 1;
    res->deliveries = 1234u;
    res->video_completed = 200u;
    res->audio_drains = 300u;
    res->isr_w1c = 1234u;
    res->t_control_transform = 1000u;
    res->t_capture_start = 2000u;
    res->t_stop = 900000u;
    res->h.handler_restored = 1;
    res->h.mask_ok = 1;
    res->h.intmr_final = 0x1FAu;
    res->control_ok = 1;
    res->a.control_orig = 0x90u;
    res->a.control_exp = 0x8Cu;
    res->a.arinfo_restore_ok = 1;
    res->a.power_cycle_required = 1;

    /* Three identical pictures in slots 0, 1 and 2; slot 3 is left as the one
     * the assembler would be filling, which is what the real run leaves behind. */
    mkraw(scratch, seed);
    for (i = 0; i < 3u; i++) {
        memcpy(ring + (size_t)i * GBP_VSTATE_RAW_FRAME_BYTES, scratch, GBP_VCOLOR_FRAME_BYTES);
        mkframe_pic(&f, i, OK_FLAGS, seed, 10u * i);
        gbp_vcolor_frame(c, &f, (int)i, 10u * i);
    }
    st->cur_slot = 3u;
    if (with_diag) {
        /* the SHARED R3 record, produced by the real state module so the sidecar
         * carries exactly what the vstate sidecar would carry */
        static struct gbp_vstate_diag diags[4];
        uint8_t w[GBP_BLOCK_SIZE];
        gbp_vstate_diag_handle h;
        unsigned k;
        gbp_vstate_diag_store(st, diags, 4u);
        for (k = 0; k < 8u; k++) {
            uint16_t v = (k == 7u) ? 0x0500u : 0x0100u;
            w[4u * k + 0] = 0x00u; w[4u * k + 1] = (uint8_t)(v >> 8);
            w[4u * k + 2] = 0x00u; w[4u * k + 3] = (uint8_t)v;
        }
        h = gbp_vstate_diag_open(st, 42u, 5000u, w, 0x0500u, 0x0100u, GBP_VSTATE_DIAG_READ_LEAN,
                                 GBP_VSTATE_DIS_SOURCE_SERVICED);
        gbp_vstate_diag_service(st, h, 0x0100u, 0x0100u, 0u);
        gbp_vstate_diag_ack(st, h, 0x8100u, 5100u);
        gbp_vstate_diag_rearm(st, h, 5200u);
        (void)gbp_vstate_diag_arm_followup(st, h);
        (void)gbp_vstate_diag_followup(st, 5300u, 0x0400u, 0x0400u);
        gbp_vstate_diag_close(st, 0u);
    }
    memset(info, 0, sizeof *info);
    if (gbp_vcoldump_set_identity(info, "GBP-VIDEO-003", "color-0001",
                                  "gbp-video-color-probe", "synthetic") != 0) return -99;
    sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    return gbp_vcoldump_stream(info, c, st, res, cfg, chunk, sizeof chunk, sink_mem, &sink, 0);
}

static void test_the_sidecar_round_trips(void)
{
    struct gbp_vcolor c;
    static struct gbp_vstate st;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vcoldump_info info, parsed;
    const uint8_t *ftab = 0, *ctab = 0, *dtab = 0, *vraw = 0, *araw = 0;
    struct gbp_vcolor_cert cert;
    long n;
    printf("-- the OGBPCOL1 sidecar: written, parsed strictly, and the raw is byte-identical\n");
    n = build_file(&c, &st, &res, &cfg, &info, frames, GBP_VCOLOR_MAX_FRAMES, 21u, 1);
    CHECK(n > 0);
    CHECK(info.version == GBP_VCOLDUMP_VERSION);
    CHECK(info.cert_count == 3u);
    CHECK(info.diag_count == 1u);
    CHECK(info.frame_count == 3u);
    CHECK((uint64_t)n == info.total_size);
    /* the layout is exactly the sum of its sections */
    CHECK(info.off_frames == GBP_VCOLDUMP_HEADER_SIZE);
    CHECK(info.off_cert == info.off_frames + 3u * GBP_VCOLDUMP_FRAME_REC);
    CHECK(info.off_diag == info.off_cert + 3u * GBP_VCOLDUMP_CERT_REC);
    CHECK(info.off_video_raw == info.off_diag + GBP_VCOLDUMP_DIAG_REC);
    CHECK(info.off_audio_raw == info.off_video_raw + 3u * GBP_VCOLOR_FRAME_BYTES);
    CHECK(info.off_footer == info.off_audio_raw);

    CHECK(gbp_vcoldump_parse(file, (size_t)n, &parsed, &ftab, &ctab, &dtab, &vraw, &araw) == 0);
    CHECK(parsed.cert_count == 3u && parsed.diag_count == 1u && parsed.frame_count == 3u);
    CHECK(parsed.total_crc32 == info.total_crc32);
    CHECK(ftab && ctab && dtab && vraw);
    CHECK(araw == 0);                                   /* no AUDIO raw in this experiment */
    gbp_vcoldump_decode_cert(ctab, &cert);
    CHECK(cert.blocks == 40u && cert.raw_offset == 0u);
    /* THE POINT OF THE WHOLE FILE: the raw bytes came back unchanged */
    mkraw(scratch, 21u);
    CHECK(memcmp(vraw, scratch, GBP_VCOLOR_FRAME_BYTES) == 0);
    CHECK(memcmp(vraw + GBP_VCOLOR_FRAME_BYTES, scratch, GBP_VCOLOR_FRAME_BYTES) == 0);
    CHECK(memcmp(vraw + 2u * GBP_VCOLOR_FRAME_BYTES, scratch, GBP_VCOLOR_FRAME_BYTES) == 0);
    printf("   %ld bytes, 3 certified frames, raw identical on the way back\n", n);
}

/* §16/§17: the raw section is ordered by CERTIFICATION ORDER, never by slot
 * number, so a replay never has to know what a slot is. Built from a state whose
 * slots are deliberately not 0,1,2. */
static void test_the_writer_orders_raw_by_certification_not_by_slot(void)
{
    struct gbp_vcolor c;
    static struct gbp_vstate st;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vcoldump_info info, parsed;
    struct gbp_vstate_frame f;
    struct gbp_vcolor_cert cert;
    struct memsink sink;
    const uint8_t *ctab = 0, *vraw = 0;
    static const uint32_t SLOT[3] = { 2u, 3u, 0u };        /* a real rotation */
    static uint8_t body[3][GBP_VCOLOR_FRAME_BYTES];
    unsigned i;
    long n;
    printf("-- the raw section follows A,B,C even when the slots are 2,3,0\n");
    gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
    gbp_vstate_init(&st, vframes, GBP_VSTATE_MAX_FRAMES, vevents, GBP_VSTATE_MAX_EVENTS,
                    ring, sizeof ring, ep_raw, sizeof ep_raw, au_raw, sizeof au_raw);
    memset(&res, 0, sizeof res); memset(&cfg, 0, sizeof cfg);
    cfg.a.tb_hz = 40500000u; res.tb_hz = 40500000u; res.service_ok = 1; res.restore_ok = 1;
    /* each slot gets DISTINGUISHABLE bytes, so an order mistake cannot hide */
    for (i = 0; i < 3u; i++) {
        mkraw(body[i], 100u + SLOT[i]);
        memcpy(ring + (size_t)SLOT[i] * GBP_VSTATE_RAW_FRAME_BYTES, body[i], GBP_VCOLOR_FRAME_BYTES);
        mkframe_pic(&f, 50u + i, OK_FLAGS, 77u, 10u * i);
        gbp_vcolor_frame(&c, &f, (int)SLOT[i], 10u * i);
    }
    CHECK(c.certified == 1);
    st.cur_slot = 1u;                                       /* the only slot left */
    CHECK(gbp_vcolor_slots_ok(&c, &st) == 1);
    memset(&info, 0, sizeof info);
    CHECK(gbp_vcoldump_set_identity(&info, "GBP-VIDEO-003", "color-0001",
                                    "gbp-video-color-probe", "synthetic") == 0);
    sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    n = gbp_vcoldump_stream(&info, &c, &st, &res, &cfg, chunk, sizeof chunk, sink_mem, &sink, 0);
    CHECK(n > 0);
    CHECK(gbp_vcoldump_parse(file, (size_t)n, &parsed, 0, &ctab, 0, &vraw, 0) == 0);
    CHECK(parsed.cert_count == 3u);
    for (i = 0; i < 3u; i++) {
        gbp_vcoldump_decode_cert(ctab + i * GBP_VCOLDUMP_CERT_REC, &cert);
        CHECK(cert.order == i);
        CHECK(cert.ring_slot == SLOT[i]);
        CHECK(cert.raw_offset == i * GBP_VCOLOR_FRAME_BYTES);
        /* the bytes at position i of the raw section are the bytes of the frame
         * that certified i-th - not the bytes of slot i */
        CHECK(memcmp(vraw + i * GBP_VCOLOR_FRAME_BYTES, body[i], GBP_VCOLOR_FRAME_BYTES) == 0);
    }
    /* and slot order would have given a different file: the test is not vacuous */
    CHECK(memcmp(body[0], body[2], GBP_VCOLOR_FRAME_BYTES) != 0);
    printf("   slots 2,3,0 serialized as A,B,C; the raw section never mentions a slot\n");
}

/* §29: a certified run whose slots did not survive writes NO raw and says so. */
static void test_a_certified_run_with_unusable_slots(void)
{
    struct gbp_vcolor c;
    static struct gbp_vstate st;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vcoldump_info info, parsed;
    struct gbp_vstate_frame f;
    struct memsink sink;
    unsigned i;
    long n;
    printf("-- certified, but the slots were lost: no raw, and the file says which\n");
    gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
    gbp_vstate_init(&st, vframes, GBP_VSTATE_MAX_FRAMES, vevents, GBP_VSTATE_MAX_EVENTS,
                    ring, sizeof ring, ep_raw, sizeof ep_raw, au_raw, sizeof au_raw);
    memset(&res, 0, sizeof res); memset(&cfg, 0, sizeof cfg);
    cfg.a.tb_hz = 40500000u; res.tb_hz = 40500000u; res.service_ok = 1; res.restore_ok = 1;
    for (i = 0; i < 3u; i++) {
        mkframe_pic(&f, i, OK_FLAGS, 88u, 10u * i);
        gbp_vcolor_frame(&c, &f, (int)i, 10u * i);
    }
    CHECK(c.certified == 1);
    st.cur_slot = 1u;                      /* the assembler is filling B's slot */
    CHECK(gbp_vcolor_slots_ok(&c, &st) == 0);
    memset(&info, 0, sizeof info);
    CHECK(gbp_vcoldump_set_identity(&info, "GBP-VIDEO-003", "color-0001",
                                    "gbp-video-color-probe", "synthetic") == 0);
    sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    n = gbp_vcoldump_stream(&info, &c, &st, &res, &cfg, chunk, sizeof chunk, sink_mem, &sink, 0);
    CHECK(n > 0);
    CHECK(info.cert_count == 0u);
    CHECK((info.flags & GBP_VCOLDUMP_FLAG_CERTIFIED) != 0u);
    CHECK((info.flags & GBP_VCOLDUMP_FLAG_RAW_UNRECOVERABLE) != 0u);
    CHECK(gbp_vcoldump_parse(file, (size_t)n, &parsed, 0, 0, 0, 0, 0) == 0);
    CHECK(parsed.cert_count == 0u);
    CHECK((parsed.flags & GBP_VCOLDUMP_FLAG_RAW_UNRECOVERABLE) != 0u);
    printf("   %ld bytes, certified with 0 raw frames, flagged raw_unrecoverable\n", n);
}

static void test_the_parser_is_strict(void)
{
    struct gbp_vcolor c;
    static struct gbp_vstate st;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vcoldump_info info;
    static uint8_t bad[sizeof file];
    long n;
    printf("-- every structural rule, with both CRCs recomputed after each tamper\n");
    n = build_file(&c, &st, &res, &cfg, &info, frames, GBP_VCOLOR_MAX_FRAMES, 33u, 1);
    CHECK(n > 0);
    CHECK(gbp_vcoldump_parse(file, (size_t)n, 0, 0, 0, 0, 0, 0) == 0);

#define REFIX(b) do { put32((b) + 0x1FC, gbp_crc32((b), 0x1FCu)); \
                      put32((b) + info.off_footer + 8u, gbp_crc32((b), info.off_footer)); } while (0)
#define TAMPER(stmt, want, label) do { \
        int rc_; memcpy(bad, file, (size_t)n); { stmt; } REFIX(bad); \
        rc_ = gbp_vcoldump_parse(bad, (size_t)n, 0, 0, 0, 0, 0, 0); \
        CHECK(rc_ == (want)); if (rc_ != (want)) printf("   %s: rc=%d, wanted %d\n", label, rc_, want); \
    } while (0)

    TAMPER(bad[0] = 'X', -1, "magic");
    TAMPER(put16(bad + 0x008, 2u), -2, "version 2");
    TAMPER(put16(bad + 0x00A, 0x100u), -2, "header size");
    TAMPER(put16(bad + 0x030, 47u), -2, "frame record size");
    TAMPER(put16(bad + 0x032, 31u), -2, "certified record size");
    TAMPER(put16(bad + 0x034, 96u), -2, "diagnostic record size");
    TAMPER(put32(bad + 0x00C, 0x0100u), -8, "unknown header flag");
    TAMPER(put32(bad + 0x00C, info.flags | GBP_VCOLDUMP_FLAG_HOLD_COMPLETE), -9, "the retired hold flag");
    TAMPER(put32(bad + 0x00C, info.flags | GBP_VCOLDUMP_FLAG_RAW_UNRECOVERABLE), -9,
           "raw_unrecoverable next to raw");
    TAMPER(put16(bad + 0x03E, 60u), -9, "the retired hold_frames_cfg");
    TAMPER(put32(bad + 0x15C, 1u), -9, "the retired hold_frames counter");
    TAMPER(put32(bad + 0x160, 1u), -9, "the retired hold_seen counter");
    TAMPER(put32(bad + 0x170 + 4u * GBP_VCOLOR_RETIRED_PRE_BASELINE, 1u), -9,
           "the retired refusal reason");
    TAMPER(put32(bad + 0x020, GBP_VCOLDUMP_MAX_AUDIO_RAW + 1u), -9, "audio_raw_count over the cap");
    TAMPER(put32(bad + 0x014, GBP_VCOLDUMP_MAX_FRAMES + 1u), -9, "frame_count over the cap");
    TAMPER(put32(bad + 0x018, 4u), -9, "cert_count over the raw budget");
    TAMPER(put32(bad + 0x01C, 257u), -9, "diag_count over the store");
    TAMPER(put32(bad + 0x024, 0xF01u), -9, "video block size");
    TAMPER(put32(bad + 0x02C, 41u), -9, "blocks per frame");
    TAMPER(put16(bad + 0x03A, 2u), -9, "n_stable 2");
    TAMPER(put32(bad + 0x00C, info.flags & ~(uint32_t)GBP_VCOLDUMP_FLAG_CERTIFIED), -9,
           "certified frames without the flag");
    TAMPER(bad[0x0D8] = 1u, -8, "header reserved not zero");
    TAMPER(bad[0x1C8] = 1u, -8, "header reserved tail not zero");
    TAMPER(put32(bad + 0x1C0, 0x0080u), -8, "unknown restore flag");
    TAMPER(bad[0x040 + 31u] = 'x', -7, "identity not terminated");
    TAMPER(bad[0x060 + 12u] = 'x', -7, "bytes after the identity terminator");
    TAMPER(put32(bad + 0x0C4, info.off_cert + 16u), -4, "certified table moved");
    TAMPER(put32(bad + 0x0C8, info.off_diag + 16u), -4, "diagnostics moved");
    TAMPER(put32(bad + 0x0CC, info.off_video_raw + 16u), -4, "raw VIDEO moved");
    TAMPER(memcpy(bad + info.off_footer, "XXXXXXXX", 8), -5, "footer magic");
    TAMPER(bad[info.off_frames + 0x28] = 1u, -8, "frame record reserved not zero");
    TAMPER(put16(bad + info.off_frames + 0x1A, 9u), -9, "unknown refusal reason");
    TAMPER(put16(bad + info.off_cert + 0x1C, GBP_VSTATE_RAW_RING_SLOTS_MAX), -9,
           "a certified frame naming a ring slot that cannot exist");
    TAMPER(put16(bad + info.off_cert + 0x1E, 2u), -9, "a certified frame with the wrong order");
    TAMPER(put16(bad + info.off_cert + GBP_VCOLDUMP_CERT_REC + 0x1C,
                 get16_at(bad + info.off_cert + 0x1C)), -9, "two certified frames on one ring slot");
    TAMPER(put32(bad + info.off_cert + 0x14, 39u), -9, "a certified frame with 39 blocks");
    TAMPER(put32(bad + info.off_cert + 0x18, 16u), -9, "a certified frame pointing elsewhere");
    TAMPER(bad[info.off_diag + 0x5C] = 1u, -8, "diagnostic reserved not zero");
    TAMPER(put16(bad + info.off_diag + 0x66, 0u), -9, "classification 0");
    TAMPER(bad[info.off_diag + 0x8C] = 0u, -9, "FU_PENDING in a saved file");
    TAMPER(put16(bad + info.off_diag + 0x6E, 0x0200u), -8, "unknown diagnostic flag");
#undef TAMPER
    /* a CRC-only corruption is caught by the CRC, and a truncation by the size rule */
    memcpy(bad, file, (size_t)n);
    bad[info.off_video_raw + 100u] ^= 0x01u;
    CHECK(gbp_vcoldump_parse(bad, (size_t)n, 0, 0, 0, 0, 0, 0) == -6);
    memcpy(bad, file, (size_t)n);
    CHECK(gbp_vcoldump_parse(bad, (size_t)n - 1u, 0, 0, 0, 0, 0, 0) == -1);
    memcpy(bad, file, (size_t)n);
    put32(bad + 0x1FC, 0xDEADBEEFu);
    CHECK(gbp_vcoldump_parse(bad, (size_t)n, 0, 0, 0, 0, 0, 0) == -3);
#undef REFIX
    printf("   %d structural tampers refused, plus CRC, truncation and header CRC\n", 42);
}

static void test_a_partial_save_never_touches_the_capture(void)
{
    struct gbp_vcolor c;
    static struct gbp_vstate st;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vcoldump_info info;
    struct memsink sink;
    struct gbp_vcolor snapshot;
    uint64_t written;
    uint32_t stops[8];
    unsigned k;
    long n;
    printf("-- a card that dies at each section: partial, refused, capture intact\n");
    n = build_file(&c, &st, &res, &cfg, &info, frames, GBP_VCOLOR_MAX_FRAMES, 44u, 1);
    CHECK(n > 0);
    stops[0] = 64u;                                   /* inside the header */
    stops[1] = info.off_frames + 16u;                 /* inside the frame table */
    stops[2] = info.off_cert + 8u;                    /* inside the certified table */
    stops[3] = info.off_diag + 32u;                   /* inside the diagnostics */
    /* each of the three certified frames in turn: the raw is streamed from the
     * ring now, so a card that dies partway through A, B or C must still leave
     * the capture state - and the ring - exactly as it was */
    stops[4] = info.off_video_raw + 1000u;                                  /* inside raw A */
    stops[5] = info.off_video_raw + GBP_VCOLOR_FRAME_BYTES + 1000u;         /* inside raw B */
    stops[6] = info.off_video_raw + 2u * GBP_VCOLOR_FRAME_BYTES + 1000u;    /* inside raw C */
    stops[7] = info.off_footer + 4u;                  /* inside the footer */
    for (k = 0; k < 8u; k++) {
        long rc;
        snapshot = c;
        memset(&info, 0, sizeof info);
        CHECK(gbp_vcoldump_set_identity(&info, "GBP-VIDEO-003", "color-0001",
                                        "gbp-video-color-probe", "synthetic") == 0);
        sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = stops[k]; sink.failed = 0;
        written = 0;
        rc = gbp_vcoldump_stream(&info, &c, &st, &res, &cfg, chunk, sizeof chunk,
                                 sink_mem, &sink, &written);
        CHECK(rc == -4);                              /* the sink refused */
        CHECK(written <= stops[k]);
        /* the parser refuses what reached the card, and the capture state in RAM
         * is byte-identical to what it was before the attempt */
        CHECK(gbp_vcoldump_parse(file, (size_t)sink.n, 0, 0, 0, 0, 0, 0) < 0);
        CHECK(memcmp(&snapshot, &c, sizeof c) == 0);
    }
    printf("   8 failure points (header, tables, diag, raw A/B/C, footer), every one refused\n");
}

static void test_an_uncertified_run_is_a_valid_file(void)
{
    struct gbp_vcolor c;
    static struct gbp_vstate st;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vcoldump_info info, parsed;
    struct gbp_vstate_frame f;
    struct memsink sink;
    long n;
    printf("-- a run that certified nothing still produces a strict, honest file\n");
    gbp_vcolor_init(&c, frames, GBP_VCOLOR_MAX_FRAMES);
    gbp_vstate_init(&st, vframes, GBP_VSTATE_MAX_FRAMES, vevents, GBP_VSTATE_MAX_EVENTS,
                    ring, sizeof ring, ep_raw, sizeof ep_raw, au_raw, sizeof au_raw);
    memset(&res, 0, sizeof res); memset(&cfg, 0, sizeof cfg);
    cfg.a.tb_hz = 40500000u; res.tb_hz = 40500000u; res.service_ok = 1; res.restore_ok = 1;
    mkframe(&f, 0u, (uint16_t)(OK_FLAGS | GBP_VSTATE_F_ANOMALY), GBP_VSTATE_FRAME_COMPLETE_40, 40u, 1u);
    mksig(&f, 9u);
    gbp_vcolor_frame(&c, &f, 0, 1u);
    memset(&info, 0, sizeof info);
    CHECK(gbp_vcoldump_set_identity(&info, "GBP-VIDEO-003", "color-0001",
                                    "gbp-video-color-probe", "synthetic") == 0);
    sink.buf = file; sink.cap = sizeof file; sink.n = 0; sink.fail_after = 0; sink.failed = 0;
    n = gbp_vcoldump_stream(&info, &c, &st, &res, &cfg, chunk, sizeof chunk, sink_mem, &sink, 0);
    CHECK(n > 0);
    CHECK(info.cert_count == 0u);
    CHECK((info.flags & GBP_VCOLDUMP_FLAG_CERTIFIED) == 0u);
    CHECK(gbp_vcoldump_parse(file, (size_t)n, &parsed, 0, 0, 0, 0, 0) == 0);
    CHECK(parsed.cert_count == 0u);
    CHECK(parsed.frame_count == 1u);
    CHECK(parsed.frames_refused[GBP_VCOLOR_ANOMALY] == 1u);
    CHECK((uint64_t)n == GBP_VCOLDUMP_HEADER_SIZE + GBP_VCOLDUMP_FRAME_REC + GBP_VCOLDUMP_FOOTER_SIZE);
    printf("   %ld bytes, 0 certified, 1 refused frame, and it parses\n", n);
}

static int dump_sidecar(const char *path, uint32_t seed, int with_diag)
{
    struct gbp_vcolor c;
    static struct gbp_vstate st;
    static struct gbp_vstate_result res;
    struct gbp_vstate_config cfg;
    struct gbp_vcoldump_info info;
    FILE *f;
    long n = build_file(&c, &st, &res, &cfg, &info, frames, GBP_VCOLOR_MAX_FRAMES, seed, with_diag);
    if (n <= 0) return 3;
    f = fopen(path, "wb");
    if (!f) return 4;
    if (fwrite(file, 1, (size_t)n, f) != (size_t)n) { fclose(f); return 5; }
    fclose(f);
    printf("wrote %ld bytes: OGBPCOL1 v%u certified=%lu diags=%lu\n", n, info.version,
           (unsigned long)info.cert_count, (unsigned long)info.diag_count);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc > 2 && strcmp(argv[1], "--dump") == 0) return dump_sidecar(argv[2], 21u, 1);
    printf("== test_gbp_vcolor (GBP-VIDEO-003 capture and OGBPCOL1; every scenario SYNTHETIC)\n");
    test_eligibility_is_one_predicate();
    test_the_capture_never_receives_frame_bytes();
    test_the_run_sequences();
    test_what_breaks_a_sequence();
    test_a_quarantined_frame_can_never_certify();
    test_pre_baseline_no_longer_refuses();
    test_the_frame_table_caps_without_losing_the_capture();
    test_the_ring_size_contract();
    test_the_ring_keeps_A_B_C_until_the_teardown();
    test_the_lifecycle_holds_at_every_rotation();
    test_majority_extra_at_a_boundary_with_four_slots();
    test_three_slots_would_destroy_the_first_frame();
    test_the_sidecar_round_trips();
    test_the_writer_orders_raw_by_certification_not_by_slot();
    test_a_certified_run_with_unusable_slots();
    test_the_parser_is_strict();
    test_a_partial_save_never_touches_the_capture();
    test_an_uncertified_run_is_a_valid_file();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
