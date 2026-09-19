/*
 * gbp_vwitness.h — LOSSLESS retention of the OGBPIDX1 canonical witness
 * (HARDWARE_TESTS §V5.33, §V5.39). Pure, hardware-free, host-tested: no
 * allocation, no clock, no device, no filesystem, no blocking.
 *
 * ---- WHAT IS RETAINED, AND WHY SO LITTLE OF IT ---------------------------
 *
 * `stream-0003` and `stream-0004` both proved that frames arrive, that they are
 * conserved and that they reach the screen. Neither can say whether the SOURCE
 * frames are continuous, because nothing in the picture identifies a frame.
 * `OGBPIDX1` (§V5.33) fixes that by making the cartridge draw its own frame ID,
 * and its **canonical witness** is the smallest region that carries the whole
 * encoded word:
 *
 *     STRIP-L, local row 0 of each block, x = 1 .. 54
 *     -> 54 word16 per block, 40 blocks per frame
 *     -> 108 bytes per block, 4320 bytes per frame
 *
 * That is 2.8 % of the 153 600-byte frame, and it is *lossless* for the thing
 * being measured: the analyzer recovers SYNC, FRAME_ID, BLOCK_INDEX, STATUS and
 * CRC-8 from exactly these words, offline (§V5.35).
 *
 * ---- THE WORD IS STORED EXACTLY AS THE WIRE CARRIED IT --------------------
 *
 *     word16 = (b1 << 8) | b3           GBP-VID-003, GBP-HW-123, GBP-HW-128
 *
 * **Bit 15 is NOT masked here.** What sets it is U-GBP-034, OPEN; masking on
 * the way in would destroy the only evidence this run can gather about it. The
 * analyzer separates bit 15 from `colour15` offline, where a mistake costs
 * nothing. Bytes 0 and 2 are read by neither reference decoder and are not read
 * here either (U-GBP-029).
 *
 * ---- WHERE IT RUNS, AND WHERE IT MUST NOT --------------------------------
 *
 * SOURCE-CAPTURE LAYER, before publication. The witness is captured when the
 * VIDEO block is received — ahead of `gbp_vqueue_publish()`, the mailbox, the
 * consumer and the display — so that a frame the CONSUMER never sees is still
 * preserved. Retaining only published frames would make the witness population
 * a function of consumer eligibility, which is precisely the bias that would
 * make a source-continuity claim worthless.
 *
 * It is therefore also NEVER run between the ACK and the RE-ARM (§V5.7), it
 * never touches a device or a clock, and it never writes a file: the sidecar is
 * serialized after the hardware is down, exactly as OGBPSEQ1 is (§V3.13).
 *
 * ---- THE STOP IS A COUNT, NOT A CLOCK ------------------------------------
 *
 * `stream-0004` disproved the sizing premise this experiment was designed
 * around (GBP-HW-151): 30 *valid* seconds were 44.3 WALL seconds and 2 648
 * closed frames, not the ~1 792 a wall-clock reading of `valid_s` predicts. The
 * valid clock sums frame spans, not the time between frames. So the indexed run
 * stops on a WITNESS COUNT:
 *
 *     the record that fills GBP_VWITNESS_TARGET is the last one, and the run
 *     asks to stop immediately    ->  stop = witness_target_reached  NORMAL
 *     an attempt to store beyond the capacity                        ->
 *                                     store_full                     INCONCLUSIVE
 *
 * Overflow is never the normal stop. If `store_full` is ever set, the analyzer
 * refuses to produce a decisive verdict (§V5.39.7).
 */
#ifndef OPENGBP_GBP_VWITNESS_H
#define OPENGBP_GBP_VWITNESS_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---- the geometry, all of it fixed by the frozen OGBPIDX1 contract ------- */
#define GBP_VWITNESS_WORDS       54u    /* STRIP-L, x = 1 .. 54                */
#define GBP_VWITNESS_STRIP_X0    1u     /* the first STRIP-L column            */
#define GBP_VWITNESS_ROW         0u     /* local row 0 of the block            */
#define GBP_VWITNESS_BLOCKS      40u    /* blocks per frame                    */
#define GBP_VWITNESS_MAX_BLOCKS  48u    /* what the assembler may accumulate   */
#define GBP_VWITNESS_LINE_STRIDE 960u   /* 240 px x 4 bytes                    */
#define GBP_VWITNESS_BLOCK_BYTES 0xF00u /* one VIDEO delivery                  */

/* 54 x 40 x 2 = 4320 bytes of witness per frame. */
#define GBP_VWITNESS_FRAME_WORDS (GBP_VWITNESS_WORDS * GBP_VWITNESS_BLOCKS)
#define GBP_VWITNESS_FRAME_BYTES (GBP_VWITNESS_FRAME_WORDS * 2u)

/* The audited budget: 2048 frames x 4320 bytes = 8 847 360 bytes = 8.4375 MiB
 * of witness. The per-frame metadata (§V5.39.6) is counted separately and
 * reported separately; it is NOT taken out of this figure. */
#define GBP_VWITNESS_TARGET      2048u
#define GBP_VWITNESS_STORE_BYTES ((size_t)GBP_VWITNESS_TARGET * GBP_VWITNESS_FRAME_BYTES)

/* Metadata that travels with each retained frame. It is what makes the record
 * interpretable WITHOUT the OGBPSEQ1 sidecar and without the runtime having
 * understood one bit of OGBPIDX1 (§V5.39.5). */
struct gbp_vwitness_meta {
    uint32_t frame_index;        /* the assembler's own index; the frame_store ordering */
    uint64_t t_first_block;      /* the frame's own span, in time-base ticks */
    uint64_t t_last_block;
    uint64_t present;            /* bit b set: block b's witness was captured */
    uint16_t blocks;             /* blocks the assembler accumulated */
    uint16_t flags;              /* gbp_vstate frame flags, VERBATIM */
    uint16_t completeness;       /* gbp_vstate completeness code */
    uint16_t disagreements;
    uint32_t blocks_captured;    /* popcount(present); redundant and deliberate */
};

struct gbp_vwitness {
    /* the caller's storage; neither is ever allocated here */
    uint16_t *store;                    /* >= GBP_VWITNESS_TARGET frames of witness */
    struct gbp_vwitness_meta *meta;     /* >= `cap` entries */
    uint32_t cap;                       /* records the storage can hold */
    uint32_t target;                    /* records after which the run asks to stop */
    uint32_t n;                         /* records committed */

    /* the frame being assembled; committed or discarded, never overwritten */
    uint16_t scratch[GBP_VWITNESS_FRAME_WORDS];
    uint64_t scratch_present;
    uint32_t scratch_blocks;            /* blocks placed into the scratch */
    uint32_t staged_valid;              /* a block is staged and not yet placed */
    uint16_t staged[GBP_VWITNESS_WORDS];

    /* what happened, so nothing has to be inferred from a count */
    uint32_t frames_seen;               /* frames closed while capture was live */
    uint32_t frames_discarded;          /* scratches dropped with no frame record */
    uint32_t blocks_staged;             /* extractions performed */
    uint32_t blocks_placed;             /* placements performed */
    uint32_t blocks_out_of_range;       /* a block index >= MAX_BLOCKS was offered */
    uint32_t store_full;                /* an attempt to commit beyond `cap`: INCONCLUSIVE */
    uint32_t target_reached;            /* the target record was committed: NORMAL */
    uint64_t t_first_record, t_last_record;

    /* §V5.39.9: the added critical-path work, as a bounded aggregate. The
     * module reads no clock — the caller measures and reports here, exactly as
     * it already does for the per-block signature. */
    uint32_t copy_ticks_min, copy_ticks_max, copy_ticks_n;
    uint64_t copy_ticks_sum;
};

/* Binds caller storage. `store` must hold `cap` x GBP_VWITNESS_FRAME_WORDS
 * uint16, `meta` must hold `cap` entries. `target` is clamped to `cap`; 0 means
 * "use cap". Returns 0, or -1 on a bad argument (and the struct is left unusable). */
int gbp_vwitness_init(struct gbp_vwitness *w, uint16_t *store, struct gbp_vwitness_meta *meta,
                      uint32_t cap, uint32_t target);

/* ---- the two steps, in the order the assembler imposes ------------------- */

/* STAGE. Extracts the 54 canonical words from one received VIDEO block into the
 * staging buffer. `block` is the 0xF00 delivery. This is the only place bytes
 * are read, it is bounded and branch-free, and it does NOT need to know where
 * the block will land — which is what makes it safe to run before the assembler
 * has decided. Returns 0, or -1 on a bad argument. */
int gbp_vwitness_stage(struct gbp_vwitness *w, const uint8_t *block);

/* PLACE. Moves the staged words to block `index` of the frame being assembled.
 * The assembler reports that index, so the witness can never disagree with the
 * frame the bytes actually joined. Out of range is COUNTED and ignored, never
 * clamped into the wrong block. Returns 0, or -1 when nothing was staged or the
 * index is out of range. */
int gbp_vwitness_place(struct gbp_vwitness *w, uint32_t index);

/* COMMIT. Writes the scratch as record `n` with `meta` (the caller fills
 * `frame_index`, the times, `blocks`, `flags`, `completeness`, `disagreements`;
 * `present` and `blocks_captured` are filled here). Resets the scratch.
 * Returns 1 when the record was stored, 0 when the store was already full
 * (`store_full` is latched and nothing is overwritten), -1 on a bad argument. */
int gbp_vwitness_commit(struct gbp_vwitness *w, const struct gbp_vwitness_meta *meta);

/* DISCARD. Drops the scratch without producing a record — the assembler gave up
 * an anchor and the blocks belong to no frame. Counted, never silent. */
void gbp_vwitness_discard(struct gbp_vwitness *w);

/* The measured cost of one stage+place, in time-base ticks. Saturating. */
void gbp_vwitness_note_ticks(struct gbp_vwitness *w, uint32_t ticks);
uint32_t gbp_vwitness_copy_ticks_mean(const struct gbp_vwitness *w);

/* 1 once the target record has been committed: the run must ask to stop NOW.
 * This is a NORMAL result and never an overflow. */
int gbp_vwitness_target_reached(const struct gbp_vwitness *w);
/* 1 when a commit was refused for lack of capacity. INCONCLUSIVE by contract. */
int gbp_vwitness_store_full(const struct gbp_vwitness *w);

/* Read-only access to a stored record (NULL when `i` is out of range). */
const uint16_t *gbp_vwitness_record(const struct gbp_vwitness *w, uint32_t i);
const struct gbp_vwitness_meta *gbp_vwitness_meta_at(const struct gbp_vwitness *w, uint32_t i);

/* One canonical word of one stored record, without the caller doing arithmetic. */
uint16_t gbp_vwitness_word(const struct gbp_vwitness *w, uint32_t i, uint32_t block, uint32_t word);

#ifdef __cplusplus
}
#endif
#endif
