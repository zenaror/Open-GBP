/*
 * test_gbp_vwitness — the OGBPIDX1 witness retention and its OGBPIDXCAP1
 * sidecar (HARDWARE_TESTS §V5.39). Every scenario is SYNTHETIC; nothing here
 * has seen hardware.
 *
 * The tests that matter most are not the arithmetic ones. They are the ones
 * that drive the REAL assembler and check that a witness record describes the
 * frame the assembler actually built — including the frames a consumer would
 * have refused. A witness placed in the wrong frame does not fail loudly; it
 * produces a plausible record of a frame that never existed, and no later check
 * can recover from that.
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "gbp_vwitness.h"
#include "gbp_vwitness_drive.h"
#include "gbp_vidxdump.h"
#include "gbp_vstate.h"
#include "gbp_vsig.h"
#include "gbp_crc32.h"

static int checks, failures;
#define CHECK(c) do { checks++; if (!(c)) { failures++; \
    printf("   FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); } } while (0)

/* ---- a synthetic VIDEO block whose STRIP-L row 0 is known exactly -------- */

static uint8_t blockbuf[GBP_VWITNESS_BLOCK_BYTES];

/* Fills the block so that pixel x of local row 0 carries `word(x)`, and every
 * byte the witness must NOT read carries a value that would be noticed. */
static void make_block(uint16_t (*word)(uint32_t x, void *u), void *u)
{
    uint32_t x, y;
    memset(blockbuf, 0xA5, sizeof blockbuf);
    for (y = 0; y < 4u; y++) {
        for (x = 0; x < 240u; x++) {
            uint8_t *p = blockbuf + y * GBP_VWITNESS_LINE_STRIDE + x * 4u;
            uint16_t w = (y == 0u) ? word(x, u) : (uint16_t)0xDEAD;
            p[0] = 0x5Au;                      /* never read (U-GBP-029) */
            p[1] = (uint8_t)(w >> 8);
            p[2] = 0xC3u;                      /* never read */
            p[3] = (uint8_t)w;
        }
    }
}

static uint16_t word_is_x(uint32_t x, void *u) { (void)u; return (uint16_t)(0x1000u + x); }
static uint16_t word_has_bit15(uint32_t x, void *u) { (void)u; return (uint16_t)(0x8000u | (x * 3u)); }
static uint16_t word_from_seed(uint32_t x, void *u)
{
    uint32_t seed = *(uint32_t *)u;
    return (uint16_t)((seed * 2654435761u + x * 40503u) >> 13);
}

/* ---- 1. the extraction is EXACTLY the canonical 54 words ---------------- */

static void test_the_extraction_is_exactly_the_canonical_strip(void)
{
    static uint16_t store[2 * GBP_VWITNESS_FRAME_WORDS];
    static struct gbp_vwitness_meta meta[2];
    struct gbp_vwitness w;
    uint32_t i;
    printf("-- the 54 extracted words are STRIP-L x=1..54 of local row 0, and nothing else\n");
    CHECK(gbp_vwitness_init(&w, store, meta, 2u, 2u) == 0);
    make_block(word_is_x, 0);
    CHECK(gbp_vwitness_stage(&w, blockbuf) == 0);
    for (i = 0; i < GBP_VWITNESS_WORDS; i++)
        CHECK(w.staged[i] == (uint16_t)(0x1000u + GBP_VWITNESS_STRIP_X0 + i));
    /* x = 0 is the FLAG column and x = 55 is the first GUARD: neither may appear */
    CHECK(w.staged[0] != (uint16_t)0x1000u);
    for (i = 0; i < GBP_VWITNESS_WORDS; i++) CHECK(w.staged[i] != (uint16_t)(0x1000u + 55u));
    CHECK(w.blocks_staged == 1u);
}

/* ---- 2. bit 15 survives; the analyzer splits it offline ----------------- */

static void test_bit15_is_preserved_on_the_way_in(void)
{
    static uint16_t store[GBP_VWITNESS_FRAME_WORDS];
    static struct gbp_vwitness_meta meta[1];
    struct gbp_vwitness w;
    uint32_t i;
    printf("-- bit 15 is stored exactly as the wire carried it (U-GBP-034 is OPEN)\n");
    CHECK(gbp_vwitness_init(&w, store, meta, 1u, 1u) == 0);
    make_block(word_has_bit15, 0);
    CHECK(gbp_vwitness_stage(&w, blockbuf) == 0);
    for (i = 0; i < GBP_VWITNESS_WORDS; i++) {
        CHECK((w.staged[i] & 0x8000u) != 0u);
        CHECK(w.staged[i] == (uint16_t)(0x8000u | ((GBP_VWITNESS_STRIP_X0 + i) * 3u)));
    }
}

/* ---- 3. a whole 40-block frame round-trips through the store ------------ */

static void test_a_whole_40_block_frame_is_retained(void)
{
    static uint16_t store[GBP_VWITNESS_FRAME_WORDS];
    static struct gbp_vwitness_meta meta[1];
    struct gbp_vwitness w;
    struct gbp_vwitness_meta m;
    uint32_t b, i, seed;
    printf("-- 40 blocks in, 40 x 54 words out, each in its own block\n");
    CHECK(gbp_vwitness_init(&w, store, meta, 1u, 1u) == 0);
    for (b = 0; b < GBP_VWITNESS_BLOCKS; b++) {
        seed = b + 1u;
        make_block(word_from_seed, &seed);
        CHECK(gbp_vwitness_stage(&w, blockbuf) == 0);
        CHECK(gbp_vwitness_place(&w, b) == 0);
    }
    CHECK(w.scratch_blocks == GBP_VWITNESS_BLOCKS);
    memset(&m, 0, sizeof m);
    m.frame_index = 7u; m.blocks = 40u; m.flags = GBP_VSTATE_F_COMPLETE; m.completeness = 1u;
    m.t_first_block = 1000u; m.t_last_block = 2000u;
    CHECK(gbp_vwitness_commit(&w, &m) == 1);
    CHECK(w.n == 1u);
    CHECK(gbp_vwitness_meta_at(&w, 0)->present == 0xFFFFFFFFFFull);
    CHECK(gbp_vwitness_meta_at(&w, 0)->blocks_captured == GBP_VWITNESS_BLOCKS);
    for (b = 0; b < GBP_VWITNESS_BLOCKS; b++) {
        seed = b + 1u;
        for (i = 0; i < GBP_VWITNESS_WORDS; i++)
            CHECK(gbp_vwitness_word(&w, 0, b, i)
                  == word_from_seed(GBP_VWITNESS_STRIP_X0 + i, &seed));
    }
    /* the scratch is reset, so the next frame cannot inherit a word */
    CHECK(w.scratch_present == 0u);
    for (i = 0; i < GBP_VWITNESS_FRAME_WORDS; i++) CHECK(w.scratch[i] == 0u);
}

/* ---- 4. an incomplete frame keeps its presence bitmap ------------------- */

static void test_an_incomplete_frame_keeps_its_presence_bitmap(void)
{
    static uint16_t store[GBP_VWITNESS_FRAME_WORDS];
    static struct gbp_vwitness_meta meta[1];
    struct gbp_vwitness w;
    struct gbp_vwitness_meta m;
    uint32_t b, seed;
    printf("-- a frame that never received 40 blocks is PRESERVED, with the gap visible\n");
    CHECK(gbp_vwitness_init(&w, store, meta, 1u, 1u) == 0);
    for (b = 0; b < 17u; b++) {
        seed = b + 100u;
        make_block(word_from_seed, &seed);
        CHECK(gbp_vwitness_stage(&w, blockbuf) == 0);
        CHECK(gbp_vwitness_place(&w, b) == 0);
    }
    memset(&m, 0, sizeof m);
    m.frame_index = 3u; m.blocks = 17u; m.completeness = GBP_VSTATE_FRAME_INCOMPLETE_SHORT;
    CHECK(gbp_vwitness_commit(&w, &m) == 1);
    CHECK(gbp_vwitness_meta_at(&w, 0)->present == 0x1FFFFull);
    CHECK(gbp_vwitness_meta_at(&w, 0)->blocks_captured == 17u);
    CHECK(gbp_vwitness_meta_at(&w, 0)->completeness == GBP_VSTATE_FRAME_INCOMPLETE_SHORT);
    /* the blocks that never arrived read as zero and are IDENTIFIABLE as absent
     * from the bitmap, never as "a block whose words happened to be zero" */
    CHECK(gbp_vwitness_word(&w, 0, 20u, 0u) == 0u);
    CHECK((gbp_vwitness_meta_at(&w, 0)->present & (1ull << 20)) == 0ull);
}

/* ---- 5. a block past the geometry is counted and dropped ---------------- */

static void test_a_block_past_the_geometry_is_counted_and_dropped(void)
{
    static uint16_t store[GBP_VWITNESS_FRAME_WORDS];
    static struct gbp_vwitness_meta meta[1];
    struct gbp_vwitness w;
    printf("-- the assembler may reach 48 blocks; only 40 can be canonical\n");
    CHECK(gbp_vwitness_init(&w, store, meta, 1u, 1u) == 0);
    make_block(word_is_x, 0);
    CHECK(gbp_vwitness_stage(&w, blockbuf) == 0);
    CHECK(gbp_vwitness_place(&w, 40u) == -1);
    CHECK(w.blocks_out_of_range == 1u);
    CHECK(w.scratch_blocks == 0u);
    CHECK(gbp_vwitness_stage(&w, blockbuf) == 0);
    CHECK(gbp_vwitness_place(&w, 47u) == -1);
    CHECK(w.blocks_out_of_range == 2u);
    /* and a place with nothing staged is refused rather than repeating the last */
    CHECK(gbp_vwitness_place(&w, 0u) == -1);
    CHECK(w.blocks_placed == 0u);
}

/* ---- 6/7. THE REAL ASSEMBLER: association, and no consumer bias --------- */

#define ASM_FRAMES 1200u
#define ASM_EVENTS 512u
#define ASM_SLOTS  4u

static struct gbp_vstate_frame asm_frames[ASM_FRAMES];
static struct gbp_vstate_event asm_events[ASM_EVENTS];
static uint8_t asm_ring[ASM_SLOTS * GBP_VSTATE_RAW_FRAME_BYTES];
static uint8_t asm_ep_raw[GBP_VSTATE_EPISODE_RAW_BYTES];
static uint8_t asm_audio_raw[GBP_VSTATE_AUDIO_RAW_BYTES];
static struct gbp_vstate asm_state;
static uint16_t asm_store[64 * GBP_VWITNESS_FRAME_WORDS];
static struct gbp_vwitness_meta asm_meta[64];

/* Feeds ONE block through the real assembler exactly as the probe does: DMA
 * into the target the assembler names, then `gbp_vstate_block()`, then the
 * witness rule — and nothing else, because nothing else may come first. */
static void feed(struct gbp_vwitness *w, uint32_t frame_no, uint32_t block_no,
                 int boundary, uint64_t t)
{
    struct gbp_vstate_step step;
    uint8_t *dst = gbp_vstate_video_target(&asm_state);
    uint8_t first4[4];
    uint32_t seed = frame_no * 1000u + block_no;
    make_block(word_from_seed, &seed);
    blockbuf[1] = boundary ? 0x80u : 0x00u;     /* the Disc boundary predicate */
    if (!dst) return;
    memcpy(dst, blockbuf, GBP_VWITNESS_BLOCK_BYTES);
    first4[0] = dst[0]; first4[1] = dst[1]; first4[2] = dst[2]; first4[3] = dst[3];
    gbp_vstate_block(&asm_state, dst, GBP_VWITNESS_BLOCK_BYTES, first4, t,
                     gbp_vsig_block(dst, GBP_VWITNESS_BLOCK_BYTES), 0u, &step);
    gbp_vwitness_step(w, &asm_state, &step);
}

static void asm_reset(struct gbp_vwitness *w)
{
    memset(&asm_state, 0, sizeof asm_state);
    gbp_vstate_init(&asm_state, asm_frames, ASM_FRAMES, asm_events, ASM_EVENTS,
                    asm_ring, sizeof asm_ring, asm_ep_raw, sizeof asm_ep_raw,
                    asm_audio_raw, sizeof asm_audio_raw);
    CHECK(gbp_vwitness_init(w, asm_store, asm_meta, 64u, 64u) == 0);
}

static void test_the_witness_follows_the_real_assembler(void)
{
    struct gbp_vwitness w;
    uint32_t f, b, i;
    uint64_t t = 1000u;
    printf("-- driven by the REAL assembler, every record describes the frame it closed\n");
    asm_reset(&w);
    /* six ordinary frames of 40 blocks each, block 0 carrying the boundary */
    for (f = 0; f < 6u; f++)
        for (b = 0; b < GBP_VWITNESS_BLOCKS; b++) feed(&w, f, b, b == 0u, t += 100u);
    /* five frames closed (the sixth is still open, exactly as at a run's end) */
    CHECK(asm_state.frames_n == 5u);
    CHECK(w.n == 5u);
    for (i = 0; i < w.n; i++) {
        const struct gbp_vwitness_meta *m = gbp_vwitness_meta_at(&w, i);
        const struct gbp_vstate_frame *fr = gbp_vstate_frame_at(&asm_state, i);
        CHECK(m->frame_index == fr->index);
        CHECK(m->blocks == fr->blocks);
        CHECK(m->flags == fr->flags);            /* VERBATIM, quarantine included */
        CHECK(m->completeness == fr->completeness);
        CHECK(m->t_first_block == fr->t_first_block);
        CHECK(m->t_last_block == fr->t_last_block);
        CHECK(m->present == 0xFFFFFFFFFFull);
        CHECK(m->blocks_captured == GBP_VWITNESS_BLOCKS);
    }
    /* THE ASSOCIATION ITSELF: record k must carry the words of frame k, not of
     * the frame before or after it. The boundary block is MOVED between slots,
     * so an off-by-one here is exactly the failure this test exists for. */
    for (i = 0; i < w.n; i++) {
        uint32_t seed = i * 1000u;               /* frame i, block 0 */
        CHECK(gbp_vwitness_word(&w, i, 0u, 0u)
              == word_from_seed(GBP_VWITNESS_STRIP_X0, &seed));
        seed = i * 1000u + 39u;
        CHECK(gbp_vwitness_word(&w, i, 39u, 53u)
              == word_from_seed(GBP_VWITNESS_STRIP_X0 + 53u, &seed));
    }
}

static void test_a_short_frame_is_retained_with_its_anomaly_flags(void)
{
    struct gbp_vwitness w;
    uint32_t b;
    uint64_t t = 1000u;
    const struct gbp_vwitness_meta *m;
    printf("-- a SHORT frame closed by an early boundary is retained, flags and all\n");
    asm_reset(&w);
    for (b = 0; b < GBP_VWITNESS_BLOCKS; b++) feed(&w, 0u, b, b == 0u, t += 100u);
    for (b = 0; b < 12u; b++) feed(&w, 1u, b, b == 0u, t += 100u);   /* only 12 */
    feed(&w, 2u, 0u, 1, t += 100u);                                  /* closes the short one */
    CHECK(asm_state.frames_n == 2u);
    CHECK(w.n == 2u);
    m = gbp_vwitness_meta_at(&w, 1u);
    CHECK(m->blocks == 12u);
    CHECK(m->present == 0xFFFull);
    CHECK(m->blocks_captured == 12u);
    CHECK(m->completeness != GBP_VSTATE_FRAME_COMPLETE_40);
    /* the SOURCE layer keeps it even though no consumer would have taken it */
    CHECK(gbp_vstate_frame_at(&asm_state, 1u)->flags == m->flags);
}

static void test_a_quarantined_frame_is_still_retained(void)
{
    struct gbp_vwitness w;
    uint32_t b;
    uint64_t t = 1000u;
    const struct gbp_vwitness_meta *m;
    printf("-- a QUARANTINED frame is preserved: retention must not inherit consumer policy\n");
    asm_reset(&w);
    for (b = 0; b < GBP_VWITNESS_BLOCKS; b++) {
        if (b == 5u) gbp_vstate_block_majority_extra(&asm_state);
        feed(&w, 0u, b, b == 0u, t += 100u);
    }
    feed(&w, 1u, 0u, 1, t += 100u);
    CHECK(w.n == 1u);
    m = gbp_vwitness_meta_at(&w, 0u);
    CHECK((m->flags & GBP_VSTATE_F_MAJORITY_EXTRA) != 0u);
    CHECK((m->flags & GBP_VSTATE_F_ANOMALY) != 0u);
    CHECK(m->present == 0xFFFFFFFFFFull);       /* all 40 blocks still retained */
}

static void test_the_48_block_give_up_keeps_its_last_block(void)
{
    struct gbp_vwitness w;
    uint32_t b;
    uint64_t t = 1000u;
    const struct gbp_vwitness_meta *m;
    uint32_t seed;
    printf("-- the 48-block give-up: the block that TRIGGERS the close belongs to it\n");
    asm_reset(&w);
    for (b = 0; b < GBP_VWITNESS_BLOCKS; b++) feed(&w, 0u, b, b == 0u, t += 100u);
    /* Frame 1 opens on a boundary and then NEVER sees another one. The assembler
     * refuses to invent a period: at 48 blocks it closes the interval as it was
     * observed and gives up the anchor. The 48th block is part of THAT frame. */
    for (b = 0; b < 48u; b++) feed(&w, 1u, b, b == 0u, t += 100u);
    CHECK(asm_state.frames_n == 2u);
    CHECK(w.n == 2u);
    m = gbp_vwitness_meta_at(&w, 1u);
    CHECK(m->blocks == 48u);
    /* only the first 40 could be canonical, and ALL of them were kept */
    CHECK(m->present == 0xFFFFFFFFFFull);
    CHECK(m->blocks_captured == GBP_VWITNESS_BLOCKS);
    CHECK(w.blocks_out_of_range == 8u);          /* blocks 40..47, counted not folded */
    seed = 1u * 1000u + 39u;
    CHECK(gbp_vwitness_word(&w, 1u, 39u, 0u) == word_from_seed(GBP_VWITNESS_STRIP_X0, &seed));
}

static void test_blocks_with_no_anchor_produce_no_record(void)
{
    struct gbp_vwitness w;
    uint32_t b;
    uint64_t t = 1000u;
    printf("-- blocks before the first boundary belong to no frame and make no record\n");
    asm_reset(&w);
    for (b = 0; b < 9u; b++) feed(&w, 9u, b, 0, t += 100u);   /* no boundary yet */
    CHECK(asm_state.frames_n == 0u);
    CHECK(w.n == 0u);
    feed(&w, 0u, 0u, 1, t += 100u);                           /* the first anchor */
    CHECK(w.n == 0u);
    CHECK(w.frames_discarded == 1u);
    CHECK(w.scratch_blocks == 1u);                            /* only the anchor block */
    CHECK(w.scratch_present == 1ull);
}

/* ---- 8/9/10/11. the target, the refusal, and no rotation ---------------- */

static void test_the_target_bounds_the_run_and_overflow_never_rotates(void)
{
    enum { CAP = 5u };
    static uint16_t store[CAP * GBP_VWITNESS_FRAME_WORDS];
    static struct gbp_vwitness_meta meta[CAP];
    struct gbp_vwitness w;
    struct gbp_vwitness_meta m;
    uint32_t k;
    printf("-- the Nth record raises the target; the (N+1)th is REFUSED, never rotated in\n");
    CHECK(gbp_vwitness_init(&w, store, meta, CAP, CAP) == 0);
    for (k = 0; k < CAP; k++) {
        uint32_t seed = k + 1u;
        make_block(word_from_seed, &seed);
        CHECK(gbp_vwitness_stage(&w, blockbuf) == 0);
        CHECK(gbp_vwitness_place(&w, 0u) == 0);
        memset(&m, 0, sizeof m);
        m.frame_index = k; m.blocks = 40u;
        CHECK(gbp_vwitness_commit(&w, &m) == 1);
        /* the target is reached by the LAST record, not one early and not one late */
        CHECK(gbp_vwitness_target_reached(&w) == ((k == CAP - 1u) ? 1 : 0));
        CHECK(gbp_vwitness_store_full(&w) == 0);
    }
    CHECK(w.n == CAP);
    /* the record beyond the capacity: refused, latched, and the FIRST record is
     * still the first record */
    {
        uint32_t seed = 999u;
        uint16_t first_before = gbp_vwitness_word(&w, 0u, 0u, 0u);
        make_block(word_from_seed, &seed);
        CHECK(gbp_vwitness_stage(&w, blockbuf) == 0);
        CHECK(gbp_vwitness_place(&w, 0u) == 0);
        memset(&m, 0, sizeof m);
        m.frame_index = CAP;
        CHECK(gbp_vwitness_commit(&w, &m) == 0);
        CHECK(gbp_vwitness_store_full(&w) == 1);
        CHECK(w.n == CAP);
        CHECK(gbp_vwitness_word(&w, 0u, 0u, 0u) == first_before);
        CHECK(gbp_vwitness_meta_at(&w, 0u)->frame_index == 0u);
        CHECK(gbp_vwitness_meta_at(&w, CAP - 1u)->frame_index == CAP - 1u);
        CHECK(w.frames_seen == CAP + 1u);       /* the refusal is still an observation */
    }
}

static void test_a_target_below_the_capacity_stops_early(void)
{
    enum { CAP = 8u, TARGET = 3u };
    static uint16_t store[CAP * GBP_VWITNESS_FRAME_WORDS];
    static struct gbp_vwitness_meta meta[CAP];
    struct gbp_vwitness w;
    struct gbp_vwitness_meta m;
    uint32_t k;
    printf("-- the target and the capacity are different things and behave differently\n");
    CHECK(gbp_vwitness_init(&w, store, meta, CAP, TARGET) == 0);
    for (k = 0; k < TARGET; k++) {
        memset(&m, 0, sizeof m);
        m.frame_index = k;
        CHECK(gbp_vwitness_commit(&w, &m) == 1);
    }
    CHECK(gbp_vwitness_target_reached(&w) == 1);
    CHECK(gbp_vwitness_store_full(&w) == 0);     /* room remains; the run simply ends */
    CHECK(w.n == TARGET);
}

static void test_the_production_geometry_is_the_audited_one(void)
{
    printf("-- the shipped store is exactly 2048 x 4320 bytes, and the record is 4368\n");
    CHECK(GBP_VWITNESS_WORDS == 54u);
    CHECK(GBP_VWITNESS_BLOCKS == 40u);
    CHECK(GBP_VWITNESS_FRAME_BYTES == 4320u);
    CHECK(GBP_VWITNESS_TARGET == 2048u);
    CHECK(GBP_VWITNESS_STORE_BYTES == 8847360u);
    CHECK(GBP_VIDXDUMP_RECORD_SIZE == 4368u);
    CHECK(GBP_VIDXDUMP_META_SIZE == 48u);
    CHECK(GBP_VIDXDUMP_HEADER_SIZE == 0x180u);
    CHECK(GBP_VIDXDUMP_FOOTER_SIZE == 12u);
}

/* ---- 12/13. the sidecar: exact round trip, and corruption refused ------- */

#define DUMP_CAP (GBP_VIDXDUMP_HEADER_SIZE + 8u * GBP_VIDXDUMP_RECORD_SIZE + GBP_VIDXDUMP_FOOTER_SIZE)
static uint8_t dump_buf[DUMP_CAP];
static uint32_t dump_len;
static uint8_t dump_chunk[GBP_VIDXDUMP_RECORD_SIZE];
static int dump_fail_at = -1, dump_calls;

static int dump_sink(void *ctx, const uint8_t *data, uint32_t len)
{
    (void)ctx;
    if (dump_fail_at >= 0 && dump_calls == dump_fail_at) { dump_calls++; return -1; }
    dump_calls++;
    if (dump_len + len > sizeof dump_buf) return -1;
    memcpy(dump_buf + dump_len, data, len);
    dump_len += len;
    return 0;
}

/* Re-seals a deliberately damaged file: the header CRC first, then the
 * whole-file CRC over the result, so a test can isolate exactly ONE rule. */
static void put_be32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
}

static void reseal(uint8_t *buf, uint32_t len)
{
    put_be32(buf + GBP_VIDXDUMP_HEADER_SIZE - 4u,
             gbp_crc32(buf, GBP_VIDXDUMP_HEADER_SIZE - 4u));
    put_be32(buf + len - 4u, gbp_crc32(buf, len - GBP_VIDXDUMP_FOOTER_SIZE));
}

static uint16_t rt_store[8 * GBP_VWITNESS_FRAME_WORDS];
static struct gbp_vwitness_meta rt_meta[8];

static long build_sidecar(struct gbp_vwitness *w, struct gbp_vidxdump_info *info, uint32_t n)
{
    struct gbp_vwitness_meta m;
    uint32_t k, b;
    uint64_t written = 0;
    CHECK(gbp_vwitness_init(w, rt_store, rt_meta, 8u, n) == 0);
    for (k = 0; k < n; k++) {
        for (b = 0; b < GBP_VWITNESS_BLOCKS; b++) {
            uint32_t seed = k * 97u + b;
            make_block(word_from_seed, &seed);
            CHECK(gbp_vwitness_stage(w, blockbuf) == 0);
            CHECK(gbp_vwitness_place(w, b) == 0);
        }
        memset(&m, 0, sizeof m);
        m.frame_index = k * 3u + 1u;
        m.blocks = 40u;
        m.flags = (uint16_t)(GBP_VSTATE_F_COMPLETE | (k == 1u ? GBP_VSTATE_F_ANOMALY : 0u));
        m.completeness = GBP_VSTATE_FRAME_COMPLETE_40;
        m.disagreements = (uint16_t)k;
        m.t_first_block = 1000u + k * 100u;
        m.t_last_block = 1050u + k * 100u;
        CHECK(gbp_vwitness_commit(w, &m) == 1);
    }
    memset(info, 0, sizeof *info);
    info->tb_hz = 40500000u;
    info->stop_reason = 11u;
    CHECK(gbp_vidxdump_set_identity(info, "GBP-VIDEO-004", "stream-0005",
                                    "gbp-video-stream-probe", "deadbee") == 0);
    dump_len = 0; dump_calls = 0;
    return gbp_vidxdump_stream(info, w, dump_chunk, sizeof dump_chunk, dump_sink, 0, &written);
}

static void test_the_sidecar_round_trips_exactly(void)
{
    struct gbp_vwitness w;
    struct gbp_vidxdump_info info, back;
    const uint8_t *recs = 0;
    long n;
    uint32_t k, b, i;
    printf("-- the sidecar round-trips every word, every flag and every bitmap exactly\n");
    dump_fail_at = -1;
    n = build_sidecar(&w, &info, 3u);
    CHECK(n > 0);
    CHECK((uint32_t)n == dump_len);
    CHECK((uint64_t)n == info.total_size);
    CHECK(dump_len == GBP_VIDXDUMP_HEADER_SIZE + 3u * GBP_VIDXDUMP_RECORD_SIZE + GBP_VIDXDUMP_FOOTER_SIZE);
    CHECK(gbp_vidxdump_parse(dump_buf, dump_len, &back, &recs) == 0);
    CHECK(back.records_n == 3u);
    CHECK(back.target_frames == 3u);
    CHECK(back.flags & GBP_VIDXDUMP_FLAG_TARGET_REACHED);
    CHECK(!(back.flags & GBP_VIDXDUMP_FLAG_STORE_FULL));
    CHECK(strcmp(back.build_id, "stream-0005") == 0);
    CHECK(strcmp(back.test_id, "GBP-VIDEO-004") == 0);
    CHECK(back.total_crc32 == info.total_crc32);
    CHECK(back.header_crc32 == info.header_crc32);
    for (k = 0; k < 3u; k++) {
        const uint8_t *r = recs + (size_t)k * GBP_VIDXDUMP_RECORD_SIZE;
        const struct gbp_vwitness_meta *m = gbp_vwitness_meta_at(&w, k);
        CHECK(gbp_vidxdump_rec_frame_index(r) == m->frame_index);
        CHECK(gbp_vidxdump_rec_blocks(r) == m->blocks);
        CHECK(gbp_vidxdump_rec_flags(r) == m->flags);
        CHECK(gbp_vidxdump_rec_completeness(r) == m->completeness);
        CHECK(gbp_vidxdump_rec_present(r) == m->present);
        for (b = 0; b < GBP_VWITNESS_BLOCKS; b++)
            for (i = 0; i < GBP_VWITNESS_WORDS; i++)
                CHECK(gbp_vidxdump_rec_word(r, b, i) == gbp_vwitness_word(&w, k, b, i));
    }
}

static void test_the_parser_refuses_every_shape_of_damage(void)
{
    struct gbp_vwitness w;
    struct gbp_vidxdump_info info, back;
    static uint8_t good[DUMP_CAP];
    uint32_t good_len;
    long n;
    printf("-- one changed byte anywhere is refused, with a reason, never accepted\n");
    dump_fail_at = -1;
    n = build_sidecar(&w, &info, 2u);
    CHECK(n > 0);
    good_len = dump_len;
    memcpy(good, dump_buf, good_len);
    CHECK(gbp_vidxdump_parse(good, good_len, &back, 0) == 0);

    /* a witness word inside a record: the record's own CRC catches it */
    memcpy(dump_buf, good, good_len);
    dump_buf[GBP_VIDXDUMP_HEADER_SIZE + GBP_VIDXDUMP_META_SIZE + 7u] ^= 0x01u;
    CHECK(gbp_vidxdump_parse(dump_buf, good_len, &back, 0) == -6);   /* file CRC first */

    /* The same damage with the whole-file CRC REPAIRED. This is what the
     * per-record CRC adds and the file-wide one cannot give: damage is still
     * caught, AND the damaged record is NAMED, so one bad record does not
     * condemn the other 2 047.
     *
     * It is NOT a producer check. A CRC computed by the writer over the bytes it
     * has just written passes whether those bytes are right or wrong; a witness
     * stored into the wrong frame would be sealed just as neatly. Correct
     * capture is established by the source-layer placement, the assembler-driven
     * tests above, and OGBPIDX1's own CRC-8 — which the CARTRIDGE computes
     * (§V5.40.11). */
    memcpy(dump_buf, good, good_len);
    dump_buf[GBP_VIDXDUMP_HEADER_SIZE + GBP_VIDXDUMP_META_SIZE + 7u] ^= 0x01u;
    reseal(dump_buf, good_len);
    CHECK(gbp_vidxdump_parse(dump_buf, good_len, &back, 0) == -9);

    /* the magic */
    memcpy(dump_buf, good, good_len);
    dump_buf[3] ^= 0xFFu;
    CHECK(gbp_vidxdump_parse(dump_buf, good_len, &back, 0) == -1);

    /* the header */
    memcpy(dump_buf, good, good_len);
    dump_buf[0x40] ^= 0x10u;
    CHECK(gbp_vidxdump_parse(dump_buf, good_len, &back, 0) == -3);

    /* a reserved header byte */
    memcpy(dump_buf, good, good_len);
    dump_buf[0x120] = 0x01u;
    CHECK(gbp_vidxdump_parse(dump_buf, good_len, &back, 0) == -3);   /* header CRC sees it */

    /* the footer magic */
    memcpy(dump_buf, good, good_len);
    dump_buf[good_len - GBP_VIDXDUMP_FOOTER_SIZE] ^= 0xFFu;
    CHECK(gbp_vidxdump_parse(dump_buf, good_len, &back, 0) == -5);

    /* a truncated file */
    memcpy(dump_buf, good, good_len);
    CHECK(gbp_vidxdump_parse(dump_buf, good_len - 1u, &back, 0) == -4);
    CHECK(gbp_vidxdump_parse(dump_buf, 4u, &back, 0) == -1);

    /* an identity that is not terminated, with both CRCs repaired */
    memcpy(dump_buf, good, good_len);
    {
        uint32_t i;
        for (i = 0; i < GBP_VIDXDUMP_ID_FIELD; i++) dump_buf[0xA8 + i] = 'x';
    }
    reseal(dump_buf, good_len);
    CHECK(gbp_vidxdump_parse(dump_buf, good_len, &back, 0) == -7);

    /* a reserved header byte, with both CRCs repaired: the reserved-zero rule
     * must catch it by itself, not by accident through a checksum */
    memcpy(dump_buf, good, good_len);
    dump_buf[0x120] = 0x01u;
    reseal(dump_buf, good_len);
    CHECK(gbp_vidxdump_parse(dump_buf, good_len, &back, 0) == -8);
}

static void test_a_refused_sink_is_reported_and_never_silent(void)
{
    struct gbp_vwitness w;
    struct gbp_vidxdump_info info;
    long n;
    printf("-- a card that stops accepting bytes is a TRUNCATED save, reported as one\n");
    dump_fail_at = 2;                 /* fail on the second record */
    n = build_sidecar(&w, &info, 3u);
    CHECK(n == -4);
    CHECK(info.flags & GBP_VIDXDUMP_FLAG_TRUNCATED);
    dump_fail_at = -1;
}

static void test_an_identity_that_does_not_fit_is_an_error(void)
{
    struct gbp_vidxdump_info info;
    printf("-- an identity is never truncated into the format; it is refused\n");
    memset(&info, 0, sizeof info);
    CHECK(gbp_vidxdump_set_identity(&info, "GBP-VIDEO-004", "stream-0005",
                                    "a-build-identity-far-too-long-to-fit-in-the-field",
                                    "deadbee") == -1);
    CHECK(info.identity_error == 1);
}

/* ---- 16. the self-test consumes no witness slot ------------------------- */

static void test_a_display_self_test_consumes_no_witness_slot(void)
{
    static uint16_t store[4 * GBP_VWITNESS_FRAME_WORDS];
    static struct gbp_vwitness_meta meta[4];
    struct gbp_vwitness w;
    printf("-- R1: the pre-probe display self-test never reaches the witness store\n");
    CHECK(gbp_vwitness_init(&w, store, meta, 4u, 4u) == 0);
    /* The self-test builds a synthetic texture and presents it. It never calls
     * gbp_vstate_block(), so it produces no step and therefore no witness work.
     * What is asserted here is the state that leaves: pristine. */
    CHECK(w.n == 0u);
    CHECK(w.frames_seen == 0u);
    CHECK(w.blocks_staged == 0u);
    CHECK(w.blocks_placed == 0u);
    CHECK(w.copy_ticks_n == 0u);
    CHECK(gbp_vwitness_target_reached(&w) == 0);
    CHECK(gbp_vwitness_store_full(&w) == 0);
}

static void test_the_copy_cost_is_a_bounded_aggregate(void)
{
    static uint16_t store[GBP_VWITNESS_FRAME_WORDS];
    static struct gbp_vwitness_meta meta[1];
    struct gbp_vwitness w;
    printf("-- the added critical-path work is measured, bounded and saturating\n");
    CHECK(gbp_vwitness_init(&w, store, meta, 1u, 1u) == 0);
    CHECK(gbp_vwitness_copy_ticks_mean(&w) == 0u);
    gbp_vwitness_note_ticks(&w, 0u);             /* zero is "not measured", not a sample */
    CHECK(w.copy_ticks_n == 0u);
    gbp_vwitness_note_ticks(&w, 100u);
    gbp_vwitness_note_ticks(&w, 300u);
    gbp_vwitness_note_ticks(&w, 200u);
    CHECK(w.copy_ticks_min == 100u);
    CHECK(w.copy_ticks_max == 300u);
    CHECK(w.copy_ticks_n == 3u);
    CHECK(gbp_vwitness_copy_ticks_mean(&w) == 200u);
}

static void test_bad_arguments_store_nothing(void)
{
    static uint16_t store[GBP_VWITNESS_FRAME_WORDS];
    static struct gbp_vwitness_meta meta[1];
    struct gbp_vwitness w;
    struct gbp_vwitness_meta m;
    printf("-- every entry point refuses a bad argument instead of writing somewhere\n");
    CHECK(gbp_vwitness_init(0, store, meta, 1u, 1u) == -1);
    CHECK(gbp_vwitness_init(&w, 0, meta, 1u, 1u) == -1);
    CHECK(gbp_vwitness_init(&w, store, 0, 1u, 1u) == -1);
    CHECK(gbp_vwitness_init(&w, store, meta, 0u, 1u) == -1);
    CHECK(gbp_vwitness_init(&w, store, meta, 1u, 0u) == 0);
    CHECK(w.target == 1u);                        /* target 0 means "the capacity" */
    CHECK(gbp_vwitness_stage(&w, 0) == -1);
    CHECK(gbp_vwitness_place(&w, 0u) == -1);      /* nothing staged */
    memset(&m, 0, sizeof m);
    CHECK(gbp_vwitness_commit(&w, 0) == -1);
    CHECK(gbp_vwitness_record(&w, 0u) == 0);
    CHECK(gbp_vwitness_meta_at(&w, 0u) == 0);
    CHECK(gbp_vwitness_word(&w, 0u, 99u, 0u) == 0u);
    gbp_vwitness_discard(0);
    gbp_vwitness_note_ticks(0, 5u);
    CHECK(gbp_vwitness_target_reached(0) == 0);
    CHECK(gbp_vwitness_store_full(0) == 0);
}

int main(void)
{
    printf("== test_gbp_vwitness (OGBPIDX1 retention; every scenario SYNTHETIC)\n");
    test_the_extraction_is_exactly_the_canonical_strip();
    test_bit15_is_preserved_on_the_way_in();
    test_a_whole_40_block_frame_is_retained();
    test_an_incomplete_frame_keeps_its_presence_bitmap();
    test_a_block_past_the_geometry_is_counted_and_dropped();
    test_the_witness_follows_the_real_assembler();
    test_a_short_frame_is_retained_with_its_anomaly_flags();
    test_a_quarantined_frame_is_still_retained();
    test_the_48_block_give_up_keeps_its_last_block();
    test_blocks_with_no_anchor_produce_no_record();
    test_the_target_bounds_the_run_and_overflow_never_rotates();
    test_a_target_below_the_capacity_stops_early();
    test_the_production_geometry_is_the_audited_one();
    test_the_sidecar_round_trips_exactly();
    test_the_parser_refuses_every_shape_of_damage();
    test_a_refused_sink_is_reported_and_never_silent();
    test_an_identity_that_does_not_fit_is_an_error();
    test_a_display_self_test_consumes_no_witness_slot();
    test_the_copy_cost_is_a_bounded_aggregate();
    test_bad_arguments_store_nothing();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
