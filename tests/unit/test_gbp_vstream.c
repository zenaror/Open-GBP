/*
 * test_gbp_vstream.c — gbp_vpix and gbp_vqueue, the two pure modules of
 * GBP-VIDEO-004 (HARDWARE_TESTS §V5). Every scenario here is SYNTHETIC; nothing
 * in this file touches hardware or claims anything about timing.
 *
 * What it is really checking is that the rules the previous rounds paid for
 * still hold when they are expressed in code: the conversion reads only the two
 * bytes both references read, the source word is never modified, an incomplete
 * or quarantined frame can never reach a screen, and a conversion that loses its
 * race is discarded whole rather than half-shown.
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "gbp_vpix.h"
#include "gbp_vqueue.h"
#include "gbp_vstate.h"
#include "gbp_vpresent.h"

static int checks, failures;
#define CHECK(x) do { checks++; if (!(x)) { failures++; \
    printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

/* ---- helpers ---------------------------------------------------------- */

/* One synthetic raw frame: 40 blocks of 4 raster lines of 240 four-byte groups.
 * `word(x,y)` decides the consumed value; bytes 0 and 2 are filled with a
 * DIFFERENT, deliberately noisy pattern so that any test which accidentally
 * reads them fails loudly. */
static uint8_t *make_frame(uint16_t (*word)(uint32_t, uint32_t), uint8_t noise)
{
    uint8_t *f = (uint8_t *)malloc(GBP_VPIX_FRAME_BYTES);
    uint32_t x, y;
    if (!f) return 0;
    memset(f, 0, GBP_VPIX_FRAME_BYTES);
    for (y = 0; y < GBP_VPIX_HEIGHT; y++) {
        for (x = 0; x < GBP_VPIX_WIDTH; x++) {
            const uint16_t w = word(x, y);
            const size_t o = gbp_vpix_raw_offset(x, y);
            f[o + 0] = (uint8_t)(noise ^ (uint8_t)(x + y));    /* never read */
            f[o + 1] = (uint8_t)(w >> 8);
            f[o + 2] = (uint8_t)(noise ^ (uint8_t)(x * 3u));   /* never read */
            f[o + 3] = (uint8_t)(w & 0xFFu);
        }
    }
    return f;
}

static uint16_t w_position(uint32_t x, uint32_t y)
{
    /* Unique per pixel in the low 15 bits, and bit 15 clear: 240*160 = 38400
     * fits in 15 bits (32768)? No — so mix, but keep it injective enough to
     * catch a permutation error, and verify injectivity separately. */
    return (uint16_t)(((x << 7) ^ (y * 613u)) & 0x7FFFu);
}

static uint16_t w_flagged(uint32_t x, uint32_t y)
{
    /* Exactly one flagged word, at the origin, as every physical frame shows. */
    return (x == 0u && y == 0u) ? 0x8000u : (uint16_t)0x1234u;
}

static uint16_t w_const(uint32_t x, uint32_t y) { (void)x; (void)y; return 0x2A55u; }

/* ---- gbp_vpix: the tile permutation ----------------------------------- */

static void test_geometry_constants(void)
{
    printf("-- the geometry is the physically established one, and it is exact\n");
    CHECK(GBP_VPIX_FRAME_BYTES == 40u * 0xF00u);
    CHECK(GBP_VPIX_FRAME_BYTES == 153600u);
    CHECK(GBP_VPIX_TEX_BYTES == 240u * 160u * 2u);
    CHECK(GBP_VPIX_TEX_BYTES == 0x12C00u);
    CHECK(GBP_VPIX_BLOCK_TEX_BYTES == 0x780u);       /* what the Disc's converter emits per block */
    CHECK(GBP_VPIX_TILES_X * GBP_VPIX_TILES_Y * GBP_VPIX_TILE_BYTES == GBP_VPIX_TEX_BYTES);
    CHECK(GBP_VPIX_LINE_STRIDE == 960u);
    printf("   frame %u B -> texture %u B, %u x %u tiles of %u B\n",
           (unsigned)GBP_VPIX_FRAME_BYTES, (unsigned)GBP_VPIX_TEX_BYTES,
           (unsigned)GBP_VPIX_TILES_X, (unsigned)GBP_VPIX_TILES_Y, (unsigned)GBP_VPIX_TILE_BYTES);
}

static void test_tile_index_landmarks(void)
{
    printf("-- the tile permutation at the landmarks a wrong one gets wrong\n");
    /* first tile, in order */
    CHECK(gbp_vpix_tile_index(0, 0) == 0u);
    CHECK(gbp_vpix_tile_index(1, 0) == 1u);
    CHECK(gbp_vpix_tile_index(3, 0) == 3u);
    CHECK(gbp_vpix_tile_index(0, 1) == 4u);          /* next row INSIDE the tile */
    CHECK(gbp_vpix_tile_index(3, 3) == 15u);         /* last texel of tile 0 */
    /* x = 3 -> 4 leaves the tile horizontally */
    CHECK(gbp_vpix_tile_index(4, 0) == 16u);         /* first texel of tile 1 */
    CHECK(gbp_vpix_tile_index(4, 0) - gbp_vpix_tile_index(3, 0) == 13u);
    /* y = 3 -> 4 leaves the tile vertically, i.e. a whole tile ROW later */
    CHECK(gbp_vpix_tile_index(0, 4) == GBP_VPIX_TILES_X * 16u);
    CHECK(gbp_vpix_tile_index(0, 4) == 960u);
    /* the last texel of the image is the last texel of the last tile */
    CHECK(gbp_vpix_tile_index(239, 159) == (GBP_VPIX_TEX_BYTES / 2u) - 1u);
    printf("   (0,0)=0 (3,0)=3 (0,1)=4 (3,3)=15 (4,0)=16 (0,4)=960 (239,159)=%u\n",
           (unsigned)gbp_vpix_tile_index(239, 159));
}

static void test_every_pixel_lands_exactly_once(void)
{
    uint8_t *seen = (uint8_t *)calloc(GBP_VPIX_TEX_BYTES / 2u, 1);
    uint32_t x, y, dup = 0, miss = 0, i;
    printf("-- all 38400 pixels map to distinct texels, and cover the texture\n");
    for (y = 0; y < GBP_VPIX_HEIGHT; y++)
        for (x = 0; x < GBP_VPIX_WIDTH; x++) {
            size_t i2 = gbp_vpix_tile_index(x, y);
            CHECK(i2 < GBP_VPIX_TEX_BYTES / 2u);
            if (seen[i2]) dup++;
            seen[i2] = 1u;
        }
    for (i = 0; i < GBP_VPIX_TEX_BYTES / 2u; i++) if (!seen[i]) miss++;
    CHECK(dup == 0u);
    CHECK(miss == 0u);
    printf("   %u texels, %u duplicates, %u never written\n",
           (unsigned)(GBP_VPIX_TEX_BYTES / 2u), (unsigned)dup, (unsigned)miss);
    free(seen);
}

static void test_raw_offsets_stay_inside_the_frame(void)
{
    uint32_t x, y, bad = 0;
    printf("-- every raw offset is inside the 153600-byte frame, group-aligned\n");
    for (y = 0; y < GBP_VPIX_HEIGHT; y++)
        for (x = 0; x < GBP_VPIX_WIDTH; x++) {
            size_t o = gbp_vpix_raw_offset(x, y);
            if (o + 3u >= GBP_VPIX_FRAME_BYTES || (o % 4u) != 0u) bad++;
        }
    CHECK(bad == 0u);
    /* the first pixel of block b is at b * 0xF00 */
    CHECK(gbp_vpix_raw_offset(0, 0) == 0u);
    CHECK(gbp_vpix_raw_offset(0, 4) == 0xF00u);
    CHECK(gbp_vpix_raw_offset(0, 1) == 960u);
    CHECK(gbp_vpix_raw_offset(239, 159) == 39u * 0xF00u + 3u * 960u + 239u * 4u);
}

static void test_conversion_round_trips(void)
{
    uint8_t *f = make_frame(w_position, 0xA5);
    uint16_t *tex = (uint16_t *)malloc(GBP_VPIX_TEX_BYTES);
    struct gbp_vpix_stats st;
    uint32_t x, y, wrong = 0;
    printf("-- every converted texel is the source word of ITS OWN pixel, plus bit 15\n");
    CHECK(f && tex);
    CHECK(gbp_vpix_frame(f, GBP_VPIX_FRAME_BYTES, tex, GBP_VPIX_TEX_BYTES / 2u, &st) == 0);
    CHECK(st.pixels == 38400u);
    for (y = 0; y < GBP_VPIX_HEIGHT; y++)
        for (x = 0; x < GBP_VPIX_WIDTH; x++) {
            const uint16_t src = w_position(x, y);
            const uint16_t got = tex[gbp_vpix_tile_index(x, y)];
            if (got != (uint16_t)(src | 0x8000u)) wrong++;
        }
    CHECK(wrong == 0u);
    printf("   %u texels checked, %u wrong\n", 38400u, (unsigned)wrong);
    free(f); free(tex);
}

static void test_bytes_0_and_2_cannot_change_the_texture(void)
{
    uint8_t *a = make_frame(w_position, 0x00);
    uint8_t *b = make_frame(w_position, 0xFF);   /* every discarded byte differs */
    uint16_t *ta = (uint16_t *)malloc(GBP_VPIX_TEX_BYTES);
    uint16_t *tb = (uint16_t *)malloc(GBP_VPIX_TEX_BYTES);
    size_t i, differ = 0;
    printf("-- bytes 0 and 2 are invisible to the conversion (U-GBP-029 stays out of it)\n");
    CHECK(a && b && ta && tb);
    /* the two raw frames really do differ, and only in the discarded bytes */
    for (i = 0; i < GBP_VPIX_FRAME_BYTES; i++) if (a[i] != b[i]) { differ++; CHECK((i % 4u) == 0u || (i % 4u) == 2u); }
    CHECK(differ > 0u);
    CHECK(gbp_vpix_frame(a, GBP_VPIX_FRAME_BYTES, ta, GBP_VPIX_TEX_BYTES / 2u, 0) == 0);
    CHECK(gbp_vpix_frame(b, GBP_VPIX_FRAME_BYTES, tb, GBP_VPIX_TEX_BYTES / 2u, 0) == 0);
    CHECK(memcmp(ta, tb, GBP_VPIX_TEX_BYTES) == 0);
    printf("   %u raw bytes differ, 0 texture bytes differ\n", (unsigned)differ);
    free(a); free(b); free(ta); free(tb);
}

static void test_the_source_word_is_never_modified(void)
{
    uint8_t *f = make_frame(w_flagged, 0x5A);
    uint8_t *copy = (uint8_t *)malloc(GBP_VPIX_FRAME_BYTES);
    uint16_t *tex = (uint16_t *)malloc(GBP_VPIX_TEX_BYTES);
    printf("-- the OR is PRESENTATION: the raw frame comes back byte-identical\n");
    CHECK(f && copy && tex);
    memcpy(copy, f, GBP_VPIX_FRAME_BYTES);
    CHECK(gbp_vpix_frame(f, GBP_VPIX_FRAME_BYTES, tex, GBP_VPIX_TEX_BYTES / 2u, 0) == 0);
    CHECK(memcmp(f, copy, GBP_VPIX_FRAME_BYTES) == 0);
    /* and the texel really does differ from the word exactly by bit 15 */
    {
        const uint16_t src = w_flagged(5, 5);
        const uint16_t got = tex[gbp_vpix_tile_index(5, 5)];
        CHECK((got & 0x8000u) != 0u);
        CHECK((got & 0x7FFFu) == (src & 0x7FFFu));      /* lower 15 bits byte-for-byte */
        CHECK(gbp_vpix_color15(src) == (uint16_t)(src & 0x7FFFu));
    }
    free(f); free(copy); free(tex);
}

static void test_flag15_is_counted_separately(void)
{
    uint8_t *f = make_frame(w_flagged, 0x11);
    uint16_t *tex = (uint16_t *)malloc(GBP_VPIX_TEX_BYTES);
    struct gbp_vpix_stats st;
    printf("-- flag15 is counted and located, and it is NOT what the texel's bit 15 is\n");
    CHECK(f && tex);
    CHECK(gbp_vpix_frame(f, GBP_VPIX_FRAME_BYTES, tex, GBP_VPIX_TEX_BYTES / 2u, &st) == 0);
    CHECK(st.flag15_count == 1u);                 /* one on the WIRE */
    CHECK(st.flag15_coords == 1u);
    CHECK(st.flag15_x[0] == 0u && st.flag15_y[0] == 0u);
    /* but EVERY texel has bit 15, because RGB5A3 requires it */
    {
        uint32_t i, without = 0;
        for (i = 0; i < GBP_VPIX_TEX_BYTES / 2u; i++) if (!(tex[i] & 0x8000u)) without++;
        CHECK(without == 0u);
    }
    printf("   1 flagged word on the wire at (0,0); all %u texels opaque by presentation rule\n",
           (unsigned)(GBP_VPIX_TEX_BYTES / 2u));
    free(f); free(tex);
}

static void test_the_coordinate_list_is_bounded(void)
{
    uint8_t *f = make_frame(w_const, 0x33);
    uint16_t *tex = (uint16_t *)malloc(GBP_VPIX_TEX_BYTES);
    struct gbp_vpix_stats st;
    uint32_t x, y;
    printf("-- a frame with bit 15 set EVERYWHERE records a bounded coordinate list\n");
    CHECK(f && tex);
    for (y = 0; y < GBP_VPIX_HEIGHT; y++)
        for (x = 0; x < GBP_VPIX_WIDTH; x++) f[gbp_vpix_raw_offset(x, y) + 1u] |= 0x80u;
    CHECK(gbp_vpix_frame(f, GBP_VPIX_FRAME_BYTES, tex, GBP_VPIX_TEX_BYTES / 2u, &st) == 0);
    CHECK(st.flag15_count == 38400u);
    CHECK(st.flag15_coords == GBP_VPIX_MAX_FLAG_COORDS);   /* the LIST is capped, the count is not */
    free(f); free(tex);
}

static void test_bad_arguments_write_nothing(void)
{
    uint8_t blk[GBP_VPIX_BLOCK_BYTES];
    uint16_t tex[16];
    printf("-- a bad argument is refused, and nothing is written outside the buffer\n");
    memset(blk, 0, sizeof blk);
    CHECK(gbp_vpix_block(0, 0, tex, 16u, 0) == -1);
    CHECK(gbp_vpix_block(blk, GBP_VPIX_BLOCKS, tex, GBP_VPIX_TEX_BYTES / 2u, 0) == -1);
    CHECK(gbp_vpix_block(blk, 0, tex, 16u, 0) == -1);        /* texture far too small */
    CHECK(gbp_vpix_frame(0, GBP_VPIX_FRAME_BYTES, tex, 16u, 0) == -1);
    CHECK(gbp_vpix_frame(blk, 16u, tex, 16u, 0) == -1);      /* raw too small */
}

static void test_block_conversion_fills_exactly_one_tile_row(void)
{
    uint8_t *f = make_frame(w_position, 0x77);
    uint16_t *tex = (uint16_t *)calloc(GBP_VPIX_TEX_BYTES / 2u, 2);
    uint32_t i, written = 0;
    printf("-- one block converts one tile row and touches nothing else\n");
    CHECK(f && tex);
    CHECK(gbp_vpix_block(f + 7u * GBP_VPIX_BLOCK_BYTES, 7u, tex, GBP_VPIX_TEX_BYTES / 2u, 0) == 0);
    for (i = 0; i < GBP_VPIX_TEX_BYTES / 2u; i++) if (tex[i]) written++;
    CHECK(written == GBP_VPIX_BLOCK_TEX_BYTES / 2u);         /* 960 texels */
    /* and they are the ones belonging to rows 28..31 */
    for (i = 0; i < 960u; i++) CHECK(tex[7u * 960u + i] != 0u);
    printf("   block 7 wrote %u texels, at tile-row offset %u\n", (unsigned)written, 7u * 960u);
    free(f); free(tex);
}

/* ---- gbp_vqueue: policy, handoff, generation guard -------------------- */

#define F_OK (GBP_VSTATE_F_COMPLETE)

static void test_classification_matches_the_assembler(void)
{
    printf("-- what may be displayed, decided from the assembler's own flags\n");
    CHECK(gbp_vqueue_classify(40u, F_OK, 0) == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_classify(39u, F_OK, 0) == GBP_VQUEUE_REJECT_INCOMPLETE);
    CHECK(gbp_vqueue_classify(40u, 0u, 0) == GBP_VQUEUE_REJECT_INCOMPLETE);      /* no F_COMPLETE */
    CHECK(gbp_vqueue_classify(40u, F_OK | GBP_VSTATE_F_ANOMALY, 0) == GBP_VQUEUE_REJECT_ANOMALY);
    CHECK(gbp_vqueue_classify(40u, F_OK | GBP_VSTATE_F_RESYNC, 0) == GBP_VQUEUE_REJECT_ANOMALY);
    CHECK(gbp_vqueue_classify(40u, F_OK, -1) == GBP_VQUEUE_REJECT_NO_SLOT);
    /* a quarantined frame is refused UNDER ITS OWN NAME even though the
     * assembler also sets F_ANOMALY on it: the two failures are different */
    CHECK(gbp_vqueue_classify(40u, F_OK | GBP_VSTATE_F_MAJORITY_EXTRA | GBP_VSTATE_F_ANOMALY, 0)
          == GBP_VQUEUE_REJECT_QUARANTINED);
}

static void test_only_complete_frames_are_published(void)
{
    struct gbp_vqueue q;
    struct gbp_vqueue_desc d;
    printf("-- an incomplete, anomalous or quarantined frame NEVER becomes visible\n");
    gbp_vqueue_init(&q, 4u);
    CHECK(gbp_vqueue_publish(&q, 1u, 39u, F_OK, 0, 10u, 20u) == GBP_VQUEUE_REJECT_INCOMPLETE);
    CHECK(gbp_vqueue_publish(&q, 2u, 40u, F_OK | GBP_VSTATE_F_MAJORITY_EXTRA, 0, 10u, 20u)
          == GBP_VQUEUE_REJECT_QUARANTINED);
    CHECK(gbp_vqueue_publish(&q, 3u, 40u, F_OK | GBP_VSTATE_F_RESYNC, 0, 10u, 20u) == GBP_VQUEUE_REJECT_ANOMALY);
    CHECK(gbp_vqueue_publish(&q, 4u, 40u, F_OK, -1, 10u, 20u) == GBP_VQUEUE_REJECT_NO_SLOT);
    CHECK(gbp_vqueue_take(&q, &d) == 0);                 /* nothing to show */
    CHECK(q.frames_published == 0u);
    CHECK(q.source_frames_closed == 4u);
    CHECK(q.source_frames_quarantined == 1u);
    CHECK(q.source_frames_anomaly == 1u);
    CHECK(q.source_frames_incomplete == 2u);
    CHECK(gbp_vqueue_balanced(&q));
    /* a good one does get through */
    CHECK(gbp_vqueue_publish(&q, 5u, 40u, F_OK, 2, 100u, 200u) == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_take(&q, &d) == 1);
    CHECK(d.frame_index == 5u && d.slot == 2u && d.blocks == 40u);
    CHECK(gbp_vqueue_balanced(&q));
}

static void test_newest_wins_and_the_producer_never_waits(void)
{
    struct gbp_vqueue q;
    struct gbp_vqueue_desc d;
    uint32_t i;
    printf("-- the producer publishes 100 frames with no consumer and never stalls\n");
    gbp_vqueue_init(&q, 4u);
    for (i = 0; i < 100u; i++)
        CHECK(gbp_vqueue_publish(&q, i, 40u, F_OK, (int)(i % 4u), i * 1000u, i * 1000u + 500u)
              == GBP_VQUEUE_ACCEPT);
    CHECK(q.frames_published == 100u);
    CHECK(q.dropped_before_convert == 99u);        /* 99 superseded, 1 pending */
    CHECK(gbp_vqueue_take(&q, &d) == 1);
    CHECK(d.frame_index == 99u);                   /* the NEWEST, not the oldest */
    CHECK(gbp_vqueue_balanced(&q));
    printf("   100 published, 99 superseded, the consumer got frame %u\n", (unsigned)d.frame_index);
}

static void test_generation_guard_accepts_an_untouched_slot(void)
{
    struct gbp_vqueue q;
    struct gbp_vqueue_desc d;
    printf("-- generation unchanged -> the frame is accepted and presented\n");
    gbp_vqueue_init(&q, 4u);
    CHECK(gbp_vqueue_publish(&q, 1u, 40u, F_OK, 0, 10u, 20u) == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_take(&q, &d) == 1);
    CHECK(gbp_vqueue_still_valid(&q, &d) == 1);
    CHECK(gbp_vqueue_commit(&q, 1, 500u) == 1);
    gbp_vqueue_note_presented(&q);
    CHECK(q.consumer_slot_overrun == 0u);
    CHECK(q.consumer_frames_presented == 1u);
    CHECK(gbp_vqueue_balanced(&q));
    /* three more publishes still leave the slot alone: the ring is 4 deep */
    CHECK(gbp_vqueue_publish(&q, 2u, 40u, F_OK, 1, 30u, 40u) == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_still_valid(&q, &d) == 1);
    CHECK(gbp_vqueue_publish(&q, 3u, 40u, F_OK, 2, 50u, 60u) == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_still_valid(&q, &d) == 1);
}

static void test_generation_guard_rejects_a_reused_slot(void)
{
    struct gbp_vqueue q;
    struct gbp_vqueue_desc d;
    uint32_t i;
    printf("-- generation changed MID-CONVERSION -> discarded, counted, never shown\n");
    gbp_vqueue_init(&q, 4u);
    CHECK(gbp_vqueue_publish(&q, 1u, 40u, F_OK, 0, 10u, 20u) == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_take(&q, &d) == 1);
    /* the "conversion" is in progress here; the producer runs ahead by exactly
     * `slots` frames, which is the moment slot 0 is written again */
    for (i = 0; i < 4u; i++)
        CHECK(gbp_vqueue_publish(&q, 10u + i, 40u, F_OK, (int)(i % 4u), 100u + i, 110u + i)
              == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_still_valid(&q, &d) == 0);
    CHECK(gbp_vqueue_commit(&q, 0, 700u) == 0);          /* the caller must NOT present */
    CHECK(q.consumer_slot_overrun == 1u);                /* exactly once */
    CHECK(q.consumer_frames_presented == 0u);            /* nothing reached the screen */
    CHECK(q.consumer_frames_converted == 1u);
    CHECK(gbp_vqueue_balanced(&q));
    printf("   overrun counted once, 0 presented, counters balance\n");
}

static void test_an_overrun_is_not_source_loss(void)
{
    struct gbp_vqueue q;
    struct gbp_vqueue_desc d;
    uint32_t i;
    printf("-- an overrun is OUR fault and is never counted as a device fault\n");
    gbp_vqueue_init(&q, 3u);
    CHECK(gbp_vqueue_publish(&q, 1u, 40u, F_OK, 0, 10u, 20u) == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_take(&q, &d) == 1);
    for (i = 0; i < 3u; i++) (void)gbp_vqueue_publish(&q, 20u + i, 40u, F_OK, (int)(i % 3u), 200u, 210u);
    (void)gbp_vqueue_commit(&q, gbp_vqueue_still_valid(&q, &d), 0u);
    CHECK(q.consumer_slot_overrun == 1u);
    CHECK(q.source_frames_incomplete == 0u);
    CHECK(q.source_frames_quarantined == 0u);
    CHECK(q.source_frames_anomaly == 0u);
    CHECK(q.source_frames_complete == 4u);      /* the device delivered all four perfectly */
}

/* HOLD_PREVIOUS_FRAME. P1 sharpened what this counter means: the ONLY caller of
 * gbp_vqueue_note_repeat() with a real queue is submit_ready(), AFTER a
 * successful submit of a CONVERTED frame, when both framebuffers are spoken
 * for. So a repeat always has exactly one converted frame behind it — which the
 * physical run showed too (repeats=12 == xfb_skipped=12, both from that branch).
 * A bare repeat with nothing converted is therefore an inconsistency, and after
 * P1 `balanced()` says so. */
static void test_hold_previous_frame(void)
{
    struct gbp_vqueue q;
    struct gbp_vqueue_desc d;
    printf("-- a held frame is counted, and every hold has a converted frame behind it\n");
    gbp_vqueue_init(&q, 4u);
    CHECK(gbp_vqueue_take(&q, &d) == 0);
    /* two converted frames whose XFB was busy */
    q.source_frames_closed = q.source_frames_complete = 2u;
    q.frames_published = q.consumer_frames_taken = q.consumer_frames_converted = 2u;
    gbp_vqueue_note_repeat(&q);
    gbp_vqueue_note_repeat(&q);
    CHECK(q.display_frames_repeated == 2u);
    CHECK(q.consumer_frames_presented == 0u);
    CHECK(gbp_vqueue_balanced(&q));
    /* and a repeat with nothing converted behind it is NOT balanced */
    gbp_vqueue_init(&q, 4u);
    gbp_vqueue_note_repeat(&q);
    CHECK(gbp_vqueue_balanced(&q) == 0);
}

static uint32_t pump_calls;
static void counting_pump(void *user) { (void)user; pump_calls++; }

static void test_the_pump_is_optional_and_inert(void)
{
    struct gbp_vqueue q;
    printf("-- with no pump installed, pumping does nothing at all\n");
    gbp_vqueue_init(&q, 4u);
    CHECK(q.pump == 0);
    gbp_vqueue_pump(&q, 0);                /* must not crash, must change nothing */
    gbp_vqueue_pump(0, 0);
    CHECK(q.consumer_frames_taken == 0u);
    CHECK(q.source_frames_closed == 0u);
}

static void test_a_latched_cause_skips_the_slice(void)
{
    struct gbp_vqueue q;
    printf("-- §V5.26/§11: a cause already pending means NO slice runs at all\n");
    gbp_vqueue_init(&q, 4u);
    q.pump = counting_pump;
    pump_calls = 0u;
    gbp_vqueue_pump(&q, 1);                /* the GBP is already waiting */
    CHECK(pump_calls == 0u);               /* the consumer got out of the way */
    CHECK(q.pump_skipped_cause_pending == 1u);
    CHECK(q.cause_pending_before_pump == 1u);
    gbp_vqueue_pump(&q, 0);                /* nothing pending: the slice runs */
    CHECK(pump_calls == 1u);
    CHECK(q.pump_skipped_cause_pending == 1u);
    CHECK(q.pump_calls == 2u);
}

static void test_the_slice_cost_is_a_bounded_aggregate(void)
{
    struct gbp_vqueue q;
    uint32_t i;
    printf("-- 10000 slices cost constant memory, and completion is counted apart\n");
    gbp_vqueue_init(&q, 4u);
    for (i = 0; i < 10000u; i++) gbp_vqueue_pump_slice(&q, 100u + (i % 7u), (i % 40u) == 39u);
    CHECK(q.pump_slices_started == 10000u);
    CHECK(q.pump_slices_completed == 250u);
    CHECK(q.pump_ticks_min == 100u);
    CHECK(q.pump_ticks_max == 106u);
    CHECK(q.pump_ticks_n == 10000u);
    CHECK(gbp_vqueue_pump_ticks_mean(&q) == 102u);   /* integer mean of 100..106 over 10000 */
}

static void test_the_pump_runs_when_installed(void)
{
    struct gbp_vqueue q;
    printf("-- an installed pump is called once per pump, with its own context\n");
    gbp_vqueue_init(&q, 4u);
    q.pump = counting_pump;
    pump_calls = 0u;
    gbp_vqueue_pump(&q, 0);
    gbp_vqueue_pump(&q, 0);
    CHECK(pump_calls == 2u);
}

static void test_the_pacing_aggregates_are_bounded(void)
{
    struct gbp_vqueue q;
    uint32_t i;
    printf("-- 10000 frames cost constant memory: min, max, count and sum only\n");
    gbp_vqueue_init(&q, 4u);
    for (i = 0; i < 10000u; i++)
        (void)gbp_vqueue_publish(&q, i, 40u, F_OK, (int)(i % 4u),
                                 (uint64_t)i * 16743u, (uint64_t)i * 16743u + 11000u);
    /* 10000 publishes give 9999 intervals, and the FIRST is measurable because
     * `have_last_publish` distinguishes "no previous frame" from "a previous
     * frame published at tick 0". */
    CHECK(q.publish_interval_n == 9999u);
    CHECK(q.publish_interval_min == 16743u);
    CHECK(q.publish_interval_max == 16743u);
    CHECK(gbp_vqueue_publish_interval_mean(&q) == 16743u);
    CHECK(gbp_vqueue_convert_ticks_mean(&q) == 0u);      /* nothing converted */
    printf("   publish interval min==max==mean==%u ticks over %u samples\n",
           (unsigned)q.publish_interval_min, (unsigned)q.publish_interval_n);
}

static void test_the_sequence_may_wrap(void)
{
    struct gbp_vqueue q;
    struct gbp_vqueue_desc d;
    printf("-- the publish counter wrapping does not break the generation guard\n");
    gbp_vqueue_init(&q, 4u);
    q.seq = 0xFFFFFFFEu;
    CHECK(gbp_vqueue_publish(&q, 1u, 40u, F_OK, 0, 10u, 20u) == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_take(&q, &d) == 1);
    CHECK(d.seq == 0xFFFFFFFFu);
    CHECK(gbp_vqueue_still_valid(&q, &d) == 1);
    /* wrap past zero */
    (void)gbp_vqueue_publish(&q, 2u, 40u, F_OK, 1, 30u, 40u);
    CHECK(q.seq == 0u);                               /* the counter really wrapped */
    CHECK(gbp_vqueue_still_valid(&q, &d) == 1);       /* 1 frame later */
    (void)gbp_vqueue_publish(&q, 3u, 40u, F_OK, 2, 50u, 60u);
    CHECK(gbp_vqueue_still_valid(&q, &d) == 1);       /* 2 later */
    (void)gbp_vqueue_publish(&q, 4u, 40u, F_OK, 3, 70u, 80u);
    CHECK(gbp_vqueue_still_valid(&q, &d) == 1);       /* 3 later: the slot is still ours */
    (void)gbp_vqueue_publish(&q, 5u, 40u, F_OK, 0, 90u, 100u);
    CHECK(gbp_vqueue_still_valid(&q, &d) == 0);       /* 4 later: slot 0 was written again */
}

static void test_an_unconfigured_queue_trusts_nothing(void)
{
    struct gbp_vqueue q;
    struct gbp_vqueue_desc d;
    printf("-- slots == 0 is not a licence to present: the guard refuses everything\n");
    gbp_vqueue_init(&q, 0u);
    CHECK(gbp_vqueue_publish(&q, 1u, 40u, F_OK, 0, 10u, 20u) == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_take(&q, &d) == 1);
    CHECK(gbp_vqueue_still_valid(&q, &d) == 0);
    CHECK(gbp_vqueue_commit(&q, gbp_vqueue_still_valid(&q, &d), 0u) == 0);
    CHECK(q.consumer_slot_overrun == 1u);
}


/* ---- gbp_vpresent: the ownership machine stream-0001 got wrong ---------- */

#define S_FREE  GBP_VPRESENT_FREE
#define S_FILL  GBP_VPRESENT_CPU_FILLING
#define S_READY GBP_VPRESENT_READY
#define S_SUB   GBP_VPRESENT_SUBMITTED

/* Drive one buffer FREE -> CPU_FILLING -> READY -> SUBMITTED. */
static int take_and_submit(struct gbp_vpresent *p)
{
    int b = gbp_vpresent_acquire(p);
    if (b < 0) return -1;
    if (gbp_vpresent_fill_done(p, b) != 0) return -1;
    return gbp_vpresent_submit(p, b) ? b : -1;
}

static void test_the_stream0001_bug_cannot_recur(void)
{
    struct gbp_vpresent p;
    int b0, b1;
    printf("-- THE stream-0001 BUG: submit buf0, prepare buf1, drawdone(buf0) frees ONLY buf0\n");
    gbp_vpresent_init(&p);
    b0 = take_and_submit(&p);
    CHECK(b0 == 0);
    CHECK(p.tex[0] == S_SUB);
    CHECK(p.submitted == 0);

    /* buffer 1 is filled and READY while the token for buffer 0 is still out */
    b1 = gbp_vpresent_acquire(&p);
    CHECK(b1 == 1);
    CHECK(gbp_vpresent_fill_done(&p, b1) == 0);
    CHECK(p.tex[1] == S_READY);
    /* and it MUST NOT be submittable: one token in flight, always */
    CHECK(gbp_vpresent_submit(&p, b1) == 0);
    CHECK(p.submit_blocked_inflight == 1u);
    CHECK(p.tex[1] == S_READY);          /* still ours, NOT submitted */
    CHECK(gbp_vpresent_consistent(&p));

    /* the token for buffer 0 fires: it must free EXACTLY buffer 0 */
    CHECK(gbp_vpresent_draw_done(&p) == 0);
    CHECK(p.tex[0] == S_FREE);
    CHECK(p.tex[1] == S_READY);          /* <-- stream-0001 freed this one too */
    CHECK(p.submitted == -1);
    CHECK(p.texture_releases == 1u);
    CHECK(p.drawdone_spurious == 0u);
    CHECK(gbp_vpresent_consistent(&p));

    /* and only NOW may buffer 1 go */
    CHECK(gbp_vpresent_submit(&p, b1) == 1);
    CHECK(p.tex[1] == S_SUB);
    CHECK(p.submitted == 1);
    printf("   buf0 released, buf1 untouched, one token at a time\n");
}

static void test_the_callback_releases_only_the_indexed_buffer(void)
{
    struct gbp_vpresent p;
    printf("-- WHITE BOX: even if two buffers somehow read SUBMITTED, the callback\n");
    printf("   releases only the one `submitted` names\n");
    /* An adversarial mutation restoring stream-0001's "free every SUBMITTED
     * buffer" callback was NOT caught by the behavioural tests, because the
     * one-token rule means two buffers can never both be SUBMITTED in a
     * legitimate sequence — the defect is neutralised by the architecture rather
     * than detected. That is one rule carrying everything, so the callback's own
     * contract is asserted here directly: the state is built by hand, which no
     * legitimate call sequence can produce, and the callback must still touch
     * exactly one buffer. */
    gbp_vpresent_init(&p);
    p.tex[0] = S_SUB;
    p.tex[1] = S_SUB;          /* impossible through the API; constructed on purpose */
    p.submitted = 0;
    CHECK(gbp_vpresent_consistent(&p) == 0);     /* and it is detected as impossible */

    CHECK(gbp_vpresent_draw_done(&p) == 0);
    CHECK(p.tex[0] == S_FREE);
    CHECK(p.tex[1] == S_SUB);  /* <-- stream-0001 freed this one; this must not */
    CHECK(p.submitted == -1);
    CHECK(p.texture_releases == 1u);

    /* the same, with the roles reversed, so the test cannot pass by index luck */
    gbp_vpresent_init(&p);
    p.tex[0] = S_SUB;
    p.tex[1] = S_SUB;
    p.submitted = 1;
    CHECK(gbp_vpresent_draw_done(&p) == 1);
    CHECK(p.tex[1] == S_FREE);
    CHECK(p.tex[0] == S_SUB);
    printf("   exactly one buffer released, both directions\n");
}

static void test_never_two_submitted(void)
{
    struct gbp_vpresent p;
    uint32_t i, n;
    printf("-- across 1000 attempts, at most ONE buffer is ever SUBMITTED\n");
    gbp_vpresent_init(&p);
    for (i = 0; i < 1000u; i++) {
        int b = gbp_vpresent_acquire(&p);
        if (b >= 0) { (void)gbp_vpresent_fill_done(&p, b); (void)gbp_vpresent_submit(&p, b); }
        /* the invariant, after every single step */
        n = 0;
        if (p.tex[0] == S_SUB) n++;
        if (p.tex[1] == S_SUB) n++;
        CHECK(n <= 1u);
        CHECK(gbp_vpresent_consistent(&p));
        if ((i % 3u) == 0u) (void)gbp_vpresent_draw_done(&p);
    }
    CHECK(p.submit_blocked_inflight > 0u);   /* the rule really bit */
}

static void test_a_spurious_callback_frees_nothing(void)
{
    struct gbp_vpresent p;
    printf("-- a callback with nothing submitted releases NOTHING and is counted\n");
    gbp_vpresent_init(&p);
    CHECK(gbp_vpresent_draw_done(&p) == -1);
    CHECK(p.drawdone_spurious == 1u);
    CHECK(p.texture_releases == 0u);
    CHECK(p.tex[0] == S_FREE && p.tex[1] == S_FREE);
    /* and a repeated callback after a genuine one is also spurious */
    CHECK(take_and_submit(&p) == 0);
    CHECK(gbp_vpresent_draw_done(&p) == 0);
    CHECK(gbp_vpresent_draw_done(&p) == -1);
    CHECK(p.drawdone_spurious == 2u);
    CHECK(p.texture_releases == 1u);
    CHECK(gbp_vpresent_consistent(&p));
}

static void test_a_submitted_buffer_can_never_be_taken_back(void)
{
    struct gbp_vpresent p;
    printf("-- the CPU may not abandon, refill or re-acquire a buffer the GP owns\n");
    gbp_vpresent_init(&p);
    CHECK(take_and_submit(&p) == 0);
    CHECK(gbp_vpresent_abandon(&p, 0) == -1);        /* refused */
    CHECK(p.tex[0] == S_SUB);
    CHECK(gbp_vpresent_fill_done(&p, 0) == -1);      /* not CPU_FILLING */
    CHECK(p.tex[0] == S_SUB);
    /* acquire may only ever hand out the OTHER one */
    CHECK(gbp_vpresent_acquire(&p) == 1);
    CHECK(gbp_vpresent_acquire(&p) == -1);
    CHECK(p.acquire_no_free_texture == 1u);
    CHECK(gbp_vpresent_consistent(&p));
}

static void test_the_full_lifecycle(void)
{
    struct gbp_vpresent p;
    printf("-- FREE -> CPU_FILLING -> READY -> SUBMITTED -> FREE, one buffer\n");
    gbp_vpresent_init(&p);
    CHECK(p.tex[0] == S_FREE);
    CHECK(gbp_vpresent_acquire(&p) == 0);
    CHECK(p.tex[0] == S_FILL);
    CHECK(gbp_vpresent_submit(&p, 0) == 0);          /* not READY yet */
    CHECK(gbp_vpresent_fill_done(&p, 0) == 0);
    CHECK(p.tex[0] == S_READY);
    CHECK(gbp_vpresent_submit(&p, 0) == 1);
    CHECK(p.tex[0] == S_SUB);
    CHECK(gbp_vpresent_draw_done(&p) == 0);
    CHECK(p.tex[0] == S_FREE);
    CHECK(p.fills_started == 1u && p.fills_completed == 1u && p.submit_success == 1u);
}

static void test_abandon_returns_a_buffer_unshown(void)
{
    struct gbp_vpresent p;
    printf("-- an abandoned conversion returns its buffer and is never shown\n");
    gbp_vpresent_init(&p);
    CHECK(gbp_vpresent_acquire(&p) == 0);
    CHECK(gbp_vpresent_abandon(&p, 0) == 0);
    CHECK(p.tex[0] == S_FREE);
    CHECK(p.fills_abandoned == 1u);
    CHECK(p.submit_success == 0u);
    CHECK(gbp_vpresent_acquire(&p) == 0);            /* immediately reusable */
}

static void test_shutdown_stops_new_work_but_not_the_gp(void)
{
    struct gbp_vpresent p;
    printf("-- shutdown refuses new fills and submits, and never steals an in-flight buffer\n");
    gbp_vpresent_init(&p);
    CHECK(take_and_submit(&p) == 0);
    CHECK(gbp_vpresent_inflight(&p) == 1);
    {
        int b = gbp_vpresent_acquire(&p);
        CHECK(b == 1);
        CHECK(gbp_vpresent_fill_done(&p, b) == 0);
        gbp_vpresent_shutdown(&p);
        CHECK(gbp_vpresent_submit(&p, b) == 0);
        CHECK(p.submit_blocked_shutdown == 1u);
    }
    CHECK(gbp_vpresent_acquire(&p) == -1);
    CHECK(p.tex[0] == S_SUB);                        /* the GP still owns it */
    CHECK(gbp_vpresent_inflight(&p) == 1);
    /* the callback still works during shutdown: that is how the drain completes */
    CHECK(gbp_vpresent_draw_done(&p) == 0);
    CHECK(gbp_vpresent_inflight(&p) == 0);
    CHECK(gbp_vpresent_consistent(&p));
}

static void test_the_inconsistent_states_are_detected(void)
{
    struct gbp_vpresent p;
    printf("-- gbp_vpresent_consistent() actually rejects the states it must\n");
    gbp_vpresent_init(&p);
    CHECK(gbp_vpresent_consistent(&p));
    p.tex[0] = S_SUB; p.tex[1] = S_SUB; p.submitted = 0;   /* the stream-0001 shape */
    CHECK(gbp_vpresent_consistent(&p) == 0);
    gbp_vpresent_init(&p);
    p.tex[0] = S_SUB;                                       /* submitted index lost */
    CHECK(gbp_vpresent_consistent(&p) == 0);
    gbp_vpresent_init(&p);
    p.submitted = 1;                                        /* index without a state */
    CHECK(gbp_vpresent_consistent(&p) == 0);
}

/* ---- gbp_vpresent: the XFB machine, kept apart from the texture one ----- */

static void test_xfb_never_targets_the_buffer_being_scanned(void)
{
    struct gbp_vpresent p;
    printf("-- the copy target is never what the VI is scanning out\n");
    gbp_vpresent_init(&p);
    CHECK(gbp_vpresent_xfb_target(&p, 0) == 1);
    CHECK(gbp_vpresent_xfb_target(&p, 1) == 0);
    CHECK(gbp_vpresent_xfb_target(&p, -1) == 0);   /* VI on neither: either is fine */
}

static void test_xfb_never_targets_a_pending_handover(void)
{
    struct gbp_vpresent p;
    printf("-- nor the one already handed over and not yet picked up\n");
    gbp_vpresent_init(&p);
    /* VI shows 0; we copy into 1 and hand it over */
    CHECK(gbp_vpresent_xfb_target(&p, 0) == 1);
    gbp_vpresent_xfb_handed(&p, 1);
    /* VI is STILL on 0: 1 is pending, 0 is being scanned -> nothing is safe */
    CHECK(gbp_vpresent_xfb_target(&p, 0) == -1);
    CHECK(p.xfb_skipped_busy == 1u);
    /* the VI switches to 1: the hand-over retires and 0 becomes writable */
    CHECK(gbp_vpresent_xfb_target(&p, 1) == 0);
    CHECK(p.xfb_pending == -1);
    CHECK(p.xfb_presents == 1u);
}

static void test_xfb_alternates_and_never_blocks(void)
{
    struct gbp_vpresent p;
    int vi = 0, i, skipped = 0, shown = 0;
    printf("-- a long alternating run: every present is either shown or SKIPPED, never waited on\n");
    gbp_vpresent_init(&p);
    for (i = 0; i < 200; i++) {
        int t = gbp_vpresent_xfb_target(&p, vi);
        if (t < 0) { skipped++; vi ^= 1; continue; }   /* a retrace happens meanwhile */
        CHECK(t != vi);
        gbp_vpresent_xfb_handed(&p, t);
        shown++;
        vi = t;                                        /* the VI picks it up */
    }
    CHECK(shown > 0);
    CHECK(shown + skipped == 200);
    CHECK(p.xfb_presents == (uint32_t)shown);
    printf("   %d shown, %d skipped, 0 waits\n", shown, skipped);
}

/* ---- R1: the self-test must not touch the scientific counters ---------- */

/* `stream-0002` routed its pre-probe display self-test through
 * gbp_vqueue_note_presented(), which put consumer_frames_presented one ahead of
 * consumer_frames_converted for the whole run — confirmed physically as
 * converted=0 presented=1 before the capture opened (GBP-HW-135).
 *
 * `stream-0003` passes NULL as the accounting queue for that frame. This models
 * the POC's two call shapes and checks what the POC checks: that the queue is
 * PRISTINE when the probe is entered. */
static void test_a_self_test_presentation_leaves_the_queue_pristine(void)
{
    struct gbp_vqueue q;
    printf("-- R1: a presentation accounted to NULL leaves every scientific counter at zero\n");
    gbp_vqueue_init(&q, 4u);
    CHECK(gbp_vqueue_pristine(&q) == 1);

    /* the self-test's shape: submit_ready(buf, NULL) */
    gbp_vqueue_note_presented(0);
    gbp_vqueue_note_repeat(0);
    CHECK(gbp_vqueue_pristine(&q) == 1);
    CHECK(q.consumer_frames_presented == 0u);
    CHECK(q.display_frames_repeated == 0u);
    CHECK(gbp_vqueue_balanced(&q) == 1);

    /* THE MUTATION THIS TEST EXISTS FOR: the stream-0002 shape, which routed the
     * self-test into the real queue. One call is enough to break both. */
    gbp_vqueue_note_presented(&q);
    CHECK(gbp_vqueue_pristine(&q) == 0);
    CHECK(gbp_vqueue_balanced(&q) == 0);
    CHECK(q.consumer_frames_presented == 1u);
    CHECK(q.consumer_frames_converted == 0u);
}

/* pristine() and balanced() answer different questions, and after P1 they both
 * catch a repeat with nothing converted behind it. pristine() is still the
 * stricter one: it also refuses a queue that merely PUBLISHED something. */
static void test_pristine_is_stricter_than_balanced(void)
{
    struct gbp_vqueue q;
    printf("-- pristine() is stricter than balanced(), and P1 made balanced() see a repeat\n");
    gbp_vqueue_init(&q, 4u);
    gbp_vqueue_note_repeat(&q);
    /* P1: a repeat with zero converted frames is now a REAL inconsistency */
    CHECK(gbp_vqueue_balanced(&q) == 0);
    CHECK(gbp_vqueue_pristine(&q) == 0);
    /* and the thing only pristine() catches: a published frame, nothing else */
    gbp_vqueue_init(&q, 4u);
    CHECK(gbp_vqueue_publish(&q, 0u, GBP_VPIX_BLOCKS, GBP_VSTATE_F_COMPLETE, 0, 1u, 2u)
          == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_balanced(&q) == 1);
    CHECK(gbp_vqueue_pristine(&q) == 0);
}

/* A whole legitimate frame moves both, and the identity still holds — so the
 * checks above are not vacuous. */
static void test_a_real_frame_still_balances(void)
{
    struct gbp_vqueue q;
    struct gbp_vqueue_desc d;
    printf("-- and a real queue frame balances exactly, with no correction of any kind\n");
    gbp_vqueue_init(&q, 4u);
    CHECK(gbp_vqueue_publish(&q, 0u, GBP_VPIX_BLOCKS, GBP_VSTATE_F_COMPLETE, 0, 1000u, 2000u)
          == GBP_VQUEUE_ACCEPT);
    CHECK(gbp_vqueue_take(&q, &d) == 1);
    CHECK(gbp_vqueue_commit(&q, gbp_vqueue_still_valid(&q, &d), 10u) == 1);
    gbp_vqueue_note_presented(&q);
    CHECK(q.consumer_frames_converted == 1u);
    CHECK(q.consumer_frames_presented == 1u);
    CHECK(gbp_vqueue_balanced(&q) == 1);
    CHECK(gbp_vqueue_pristine(&q) == 0);      /* it is no longer clean, correctly */
}

/* ---- R8: the invariants, latched during the run ------------------------ */

static void test_valid_transitions_latch_no_invariant_failure(void)
{
    struct gbp_vpresent p;
    int b;
    printf("-- R8: a full legitimate lifecycle latches ZERO invariant failures\n");
    gbp_vpresent_init(&p);
    CHECK(gbp_vpresent_invariant_failures(&p) == 0u);
    CHECK(gbp_vpresent_invariant_checks(&p) == 0u);

    b = gbp_vpresent_acquire(&p);          CHECK(b == 0);
    CHECK(gbp_vpresent_fill_done(&p, b) == 0);
    CHECK(gbp_vpresent_submit(&p, b) == 1);
    CHECK(gbp_vpresent_draw_done(&p) == 0);
    b = gbp_vpresent_acquire(&p);          CHECK(b >= 0);
    CHECK(gbp_vpresent_abandon(&p, b) == 0);
    /* a spurious callback is legitimate and must not be read as a violation */
    CHECK(gbp_vpresent_draw_done(&p) == -1);

    CHECK(gbp_vpresent_invariant_failures(&p) == 0u);
    CHECK(gbp_vpresent_invariant_checks(&p) >= 6u);     /* it really did look */
    CHECK(p.invariant_checks > 0u && p.invariant_checks_isr > 0u);
    CHECK(gbp_vpresent_consistent(&p) == 1);
}

/* The one that the end-of-run check could never make: a state that is impossible
 * for a moment and consistent again afterwards. */
static void test_a_transient_impossible_state_is_latched_even_after_it_heals(void)
{
    struct gbp_vpresent p;
    printf("-- R8: a violation that HEALS is still counted, which is the whole point\n");
    gbp_vpresent_init(&p);

    /* Inject the stream-0001 shape by hand: two buffers SUBMITTED at once. No
     * legitimate sequence can produce it, which is exactly why it is injected. */
    p.tex[0] = GBP_VPRESENT_SUBMITTED;
    p.tex[1] = GBP_VPRESENT_SUBMITTED;
    p.submitted = 0;
    CHECK(gbp_vpresent_consistent(&p) == 0);

    /* the next transition through the module observes it */
    (void)gbp_vpresent_draw_done(&p);                 /* ISR side */
    CHECK(gbp_vpresent_invariant_failures(&p) >= 1u);

    /* now heal it completely */
    p.tex[0] = GBP_VPRESENT_FREE;
    p.tex[1] = GBP_VPRESENT_FREE;
    p.submitted = -1;
    CHECK(gbp_vpresent_consistent(&p) == 1);          /* consistent AT END */

    /* and drive a whole clean lifecycle over the top of it */
    {
        int b = gbp_vpresent_acquire(&p);
        CHECK(gbp_vpresent_fill_done(&p, b) == 0);
        CHECK(gbp_vpresent_submit(&p, b) == 1);
        CHECK(gbp_vpresent_draw_done(&p) == b);
    }
    CHECK(gbp_vpresent_consistent(&p) == 1);

    /* THE CLAIM: the end says "consistent" and the run says "it was not".
     * stream-0002 could only ever have reported the first of those. */
    CHECK(gbp_vpresent_invariant_failures(&p) >= 1u);
}

/* Main side and interrupt side count separately, so neither can lose the
 * other's increment through a read-modify-write. */
static void test_the_two_invariant_counters_stay_apart(void)
{
    struct gbp_vpresent p;
    printf("-- R8: main-side and interrupt-side failures are counted in separate fields\n");
    gbp_vpresent_init(&p);

    p.tex[0] = GBP_VPRESENT_SUBMITTED;
    p.tex[1] = GBP_VPRESENT_SUBMITTED;
    p.submitted = 0;
    (void)gbp_vpresent_acquire(&p);                   /* main side, refuses, then audits */
    CHECK(p.invariant_failures >= 1u);
    CHECK(p.invariant_failures_isr == 0u);

    (void)gbp_vpresent_draw_done(&p);                 /* ISR side */
    CHECK(p.invariant_failures_isr >= 1u);
    CHECK(gbp_vpresent_invariant_failures(&p) == p.invariant_failures + p.invariant_failures_isr);
}

/* The audit must not have changed the state machine: the same sequences produce
 * the same states and the same counters as `stream-0002`. */
static void test_the_audit_changed_no_state_transition(void)
{
    struct gbp_vpresent p;
    int b;
    printf("-- R8: the latch observes and never writes a state bit\n");
    gbp_vpresent_init(&p);
    b = gbp_vpresent_acquire(&p);
    CHECK(b == 0 && p.tex[0] == GBP_VPRESENT_CPU_FILLING && p.submitted == -1);
    CHECK(gbp_vpresent_fill_done(&p, b) == 0 && p.tex[0] == GBP_VPRESENT_READY);
    CHECK(gbp_vpresent_submit(&p, b) == 1 && p.tex[0] == GBP_VPRESENT_SUBMITTED && p.submitted == 0);
    /* the one-token rule, unchanged */
    {
        int c = gbp_vpresent_acquire(&p);
        CHECK(c == 1);
        CHECK(gbp_vpresent_fill_done(&p, c) == 0);
        CHECK(gbp_vpresent_submit(&p, c) == 0);
        CHECK(p.submit_blocked_inflight == 1u);
    }
    /* abandon still refuses a SUBMITTED buffer, unchanged */
    CHECK(gbp_vpresent_abandon(&p, 0) == -1);
    CHECK(gbp_vpresent_draw_done(&p) == 0 && p.tex[0] == GBP_VPRESENT_FREE && p.submitted == -1);
    CHECK(gbp_vpresent_invariant_failures(&p) == 0u);
}

static void test_texture_and_xfb_are_independent(void)
{
    struct gbp_vpresent p;
    printf("-- a draw-done never touches XFB state, and an XFB hand-over never frees a texture\n");
    gbp_vpresent_init(&p);
    CHECK(take_and_submit(&p) == 0);
    gbp_vpresent_xfb_handed(&p, 1);
    CHECK(gbp_vpresent_draw_done(&p) == 0);
    CHECK(p.xfb_pending == 1);                 /* the VI was not consulted by that */
    CHECK(p.tex[0] == S_FREE);
    gbp_vpresent_xfb_observe(&p, 1);
    CHECK(p.xfb_pending == -1);
    CHECK(p.submitted == -1);                  /* and that did not touch the texture */
}

/* ---- what the FIRST PHYSICAL RUN of stream-0003 taught, locked as tests ---
 *
 * These reproduce two findings from GBP-VIDEO-004 / stream-0003 (HARDWARE_TESTS
 * §V5.34). Neither is fixed here — this round is not authorised to change
 * src/gbp — and both tests therefore assert the CURRENT behaviour together with
 * the arithmetic that shows why it is wrong. A future fix must change these
 * tests deliberately, not by accident. */

/* P1, FIXED. The physical stream-0003 counters conserve, and gbp_vqueue_balanced()
 * now says so. The old predicate knew only `presented + overrun` and called a
 * legitimate display repeat a conservation failure (GBP-HW-145). */
static void test_the_physical_stream0003_counters_conserve(void)
{
    struct gbp_vqueue q;
    uint32_t i;
    printf("-- the stream-0003 physical counters conserve, and balanced() agrees after P1\n");
    gbp_vqueue_init(&q, 4u);
    for (i = 0; i < 2286u; i++) gbp_vqueue_note_presented(&q);
    for (i = 0; i < 12u; i++)   gbp_vqueue_note_repeat(&q);
    q.consumer_frames_converted = 2298u;
    q.consumer_slot_overrun = 0u;
    q.source_frames_closed = 2648u;
    q.source_frames_complete = 2298u;
    q.source_frames_incomplete = 13u;
    q.source_frames_quarantined = 324u;
    q.source_frames_anomaly = 13u;
    q.frames_published = 2298u;
    q.consumer_frames_taken = 2298u;
    q.dropped_before_convert = 0u;
    q.has_pending = 0;

    CHECK(q.consumer_frames_presented == 2286u);
    CHECK(q.display_frames_repeated == 12u);
    CHECK(q.source_frames_closed == q.source_frames_complete + q.source_frames_incomplete
                                 + q.source_frames_quarantined + q.source_frames_anomaly);
    CHECK(q.source_frames_complete == q.frames_published);
    CHECK(q.frames_published == q.consumer_frames_taken + q.dropped_before_convert);
    CHECK(q.consumer_frames_converted <= q.consumer_frames_taken);
    /* the identity the state machine actually proves */
    CHECK(q.consumer_frames_converted == q.consumer_frames_presented
                                       + q.consumer_slot_overrun
                                       + q.display_frames_repeated);
    CHECK(gbp_vqueue_undispositioned(&q) == 0u);
    CHECK(gbp_vqueue_balanced(&q) == 1);           /* was 0 before P1 */
}

/* P2, FIXED. The two flags no longer share a bit, and neither meaning leaked. */
static void test_the_episode_stable_bit_no_longer_aliases(void)
{
    printf("-- F_EPISODE_STABLE and F_MAJORITY_EXTRA are distinct bits after P2\n");
    CHECK(GBP_VSTATE_F_EPISODE_STABLE == 0x1000u);   /* UNMOVED: it is what every
                                                      * historical sidecar carries */
    CHECK(GBP_VSTATE_F_MAJORITY_EXTRA == 0x4000u);   /* MOVED: never set in any
                                                      * physical run, so moving it
                                                      * re-interprets nothing */
    CHECK(GBP_VSTATE_F_MAJORITY_EXTRA != GBP_VSTATE_F_EPISODE_STABLE);
    CHECK((GBP_VSTATE_F_MAJORITY_EXTRA & GBP_VSTATE_F_EPISODE_STABLE) == 0u);
}

/* §7. The behavioural reproduction: a frame carrying ONLY episode-stable
 * semantics must be ELIGIBLE. Before P2 it was QUARANTINED. */
static void test_a_stable_frame_is_eligible(void)
{
    struct gbp_vqueue q;
    printf("-- a frame that merely closed an episode as stable is ELIGIBLE\n");
    CHECK(gbp_vqueue_classify(GBP_VPIX_BLOCKS,
                              GBP_VSTATE_F_COMPLETE | GBP_VSTATE_F_EPISODE_STABLE, 0)
          == GBP_VQUEUE_ACCEPT);
    /* and it really publishes */
    gbp_vqueue_init(&q, 4u);
    CHECK(gbp_vqueue_publish(&q, 0u, GBP_VPIX_BLOCKS,
                             GBP_VSTATE_F_COMPLETE | GBP_VSTATE_F_EPISODE_STABLE,
                             0, 10u, 20u) == GBP_VQUEUE_ACCEPT);
    CHECK(q.frames_published == 1u);
    CHECK(q.source_frames_quarantined == 0u);
    /* the whole combination the 324 stream-0003 frames carried */
    CHECK(gbp_vqueue_classify(GBP_VPIX_BLOCKS,
                              GBP_VSTATE_F_COMPLETE | GBP_VSTATE_F_COUNTED
                              | GBP_VSTATE_F_EPISODE_STABLE, 0) == GBP_VQUEUE_ACCEPT);
}

/* §8. The real policy must NOT be weakened: a true majority-extra frame is
 * still quarantined, and still ahead of the anomaly it always carries. */
static void test_a_true_majority_extra_frame_is_still_quarantined(void)
{
    struct gbp_vqueue q;
    printf("-- a TRUE majority-extra frame is still QUARANTINED, per R3.12\n");
    CHECK(gbp_vqueue_classify(GBP_VPIX_BLOCKS,
                              GBP_VSTATE_F_COMPLETE | GBP_VSTATE_F_MAJORITY_EXTRA, 0)
          == GBP_VQUEUE_REJECT_QUARANTINED);
    /* as it is emitted in practice: always together with F_ANOMALY */
    CHECK(gbp_vqueue_classify(GBP_VPIX_BLOCKS,
                              GBP_VSTATE_F_COMPLETE | GBP_VSTATE_F_MAJORITY_EXTRA
                              | GBP_VSTATE_F_ANOMALY, 0) == GBP_VQUEUE_REJECT_QUARANTINED);
    /* and even together with EPISODE_STABLE, quarantine still wins */
    CHECK(gbp_vqueue_classify(GBP_VPIX_BLOCKS,
                              GBP_VSTATE_F_COMPLETE | GBP_VSTATE_F_MAJORITY_EXTRA
                              | GBP_VSTATE_F_EPISODE_STABLE, 0)
          == GBP_VQUEUE_REJECT_QUARANTINED);
    gbp_vqueue_init(&q, 4u);
    CHECK(gbp_vqueue_publish(&q, 0u, GBP_VPIX_BLOCKS,
                             GBP_VSTATE_F_COMPLETE | GBP_VSTATE_F_MAJORITY_EXTRA,
                             0, 10u, 20u) == GBP_VQUEUE_REJECT_QUARANTINED);
    CHECK(q.source_frames_quarantined == 1u);
    CHECK(q.frames_published == 0u);
}

/* §6. The uniqueness rule itself, at test time as well as at build time. */
static void test_every_frame_flag_is_a_distinct_power_of_two(void)
{
    static const uint16_t flags[] = {
        GBP_VSTATE_F_COMPLETE, GBP_VSTATE_F_DISAGREEMENT, GBP_VSTATE_F_ANOMALY,
        GBP_VSTATE_F_PRE_BASELINE, GBP_VSTATE_F_RESYNC, GBP_VSTATE_F_EARLY_CANDIDATE,
        GBP_VSTATE_F_OVERLONG, GBP_VSTATE_F_RAW_PRESERVED, GBP_VSTATE_F_BASELINE,
        GBP_VSTATE_F_COUNTED, GBP_VSTATE_F_TAIL, GBP_VSTATE_F_EPISODE_CHANGE,
        GBP_VSTATE_F_EPISODE_STABLE, GBP_VSTATE_F_SOURCE_DEFERRED,
        GBP_VSTATE_F_MAJORITY_EXTRA
    };
    unsigned i, j;
    uint16_t seen = 0;
    printf("-- every frame flag is a distinct power of two, and GBP_VSTATE_F_ALL is complete\n");
    CHECK(sizeof flags / sizeof flags[0] == GBP_VSTATE_F_COUNT);
    for (i = 0; i < sizeof flags / sizeof flags[0]; i++) {
        CHECK(flags[i] != 0u);
        CHECK((flags[i] & (uint16_t)(flags[i] - 1u)) == 0u);    /* a power of two */
        for (j = 0; j < i; j++) CHECK(flags[i] != flags[j]);    /* pairwise distinct */
        seen = (uint16_t)(seen | flags[i]);
    }
    CHECK(seen == (uint16_t)GBP_VSTATE_F_ALL);
}

/* §14. Every terminal a converted frame can reach, and the identity at each. */
static void test_every_converted_frame_terminal_balances(void)
{
    struct gbp_vqueue q;
    printf("-- each terminal of a converted frame, and a mixture, all balance\n");
    /* A: converted -> presented */
    gbp_vqueue_init(&q, 4u);
    q.consumer_frames_taken = q.consumer_frames_converted = 1u;
    q.frames_published = 1u; q.source_frames_closed = q.source_frames_complete = 1u;
    gbp_vqueue_note_presented(&q);
    CHECK(gbp_vqueue_balanced(&q) == 1);
    /* B: converted -> generation overrun */
    gbp_vqueue_init(&q, 4u);
    q.consumer_frames_taken = q.consumer_frames_converted = 1u;
    q.frames_published = 1u; q.source_frames_closed = q.source_frames_complete = 1u;
    q.consumer_slot_overrun = 1u;
    CHECK(gbp_vqueue_balanced(&q) == 1);
    /* C: converted -> XFB busy -> display repeat */
    gbp_vqueue_init(&q, 4u);
    q.consumer_frames_taken = q.consumer_frames_converted = 1u;
    q.frames_published = 1u; q.source_frames_closed = q.source_frames_complete = 1u;
    gbp_vqueue_note_repeat(&q);
    CHECK(gbp_vqueue_balanced(&q) == 1);
    /* D: a mixture of all three */
    gbp_vqueue_init(&q, 4u);
    q.consumer_frames_taken = q.consumer_frames_converted = 10u;
    q.frames_published = 10u; q.source_frames_closed = q.source_frames_complete = 10u;
    q.consumer_frames_presented = 7u; q.consumer_slot_overrun = 2u;
    q.display_frames_repeated = 1u;
    CHECK(gbp_vqueue_balanced(&q) == 1);
    /* E: a terminal missing -> FAIL, but only beyond the bounded residual */
    gbp_vqueue_init(&q, 4u);
    q.consumer_frames_taken = q.consumer_frames_converted = 10u;
    q.frames_published = 10u; q.source_frames_closed = q.source_frames_complete = 10u;
    q.consumer_frames_presented = 7u;            /* 3 unaccounted, bound is 2 */
    CHECK(gbp_vqueue_balanced(&q) == 0);
    CHECK(gbp_vqueue_undispositioned(&q) == 3u);
    /* F: a frame counted twice -> FAIL */
    gbp_vqueue_init(&q, 4u);
    q.consumer_frames_taken = q.consumer_frames_converted = 1u;
    q.frames_published = 1u; q.source_frames_closed = q.source_frames_complete = 1u;
    gbp_vqueue_note_presented(&q);
    gbp_vqueue_note_repeat(&q);                  /* the same frame, twice */
    CHECK(gbp_vqueue_balanced(&q) == 0);
}

/* The bounded residual is a real state, not a loophole: a converted frame whose
 * submit was refused is waiting, and at most one per texture buffer can wait. */
static void test_the_bounded_residual_is_accepted_and_bounded(void)
{
    struct gbp_vqueue q;
    unsigned k;
    printf("-- a converted frame still waiting for a submit is accepted, up to the buffer count\n");
    for (k = 0; k <= GBP_VQUEUE_MAX_UNDISPOSITIONED + 1u; k++) {
        gbp_vqueue_init(&q, 4u);
        q.consumer_frames_taken = q.consumer_frames_converted = 10u + k;
        q.frames_published = 10u + k;
        q.source_frames_closed = q.source_frames_complete = 10u + k;
        q.consumer_frames_presented = 10u;
        CHECK(gbp_vqueue_undispositioned(&q) == k);
        CHECK(gbp_vqueue_balanced(&q) == ((k <= GBP_VQUEUE_MAX_UNDISPOSITIONED) ? 1 : 0));
    }
}

/* §V5.37.5. The audit did not settle this by example. `F_EPISODE_STABLE` is a
 * REPORTING bit: it says an episode closed as stable, which is a statement about
 * the picture, never about the frame's fitness to be shown. So the claim under
 * test is not "the 324-frame combination is accepted" but the stronger one —
 * over EVERY flag word the classifier can be handed, setting or clearing
 * `F_EPISODE_STABLE` cannot change the answer. That is what P2's aliasing broke,
 * and enumerating it is cheap: 2^15 words, both ways. */
static void test_episode_stable_never_changes_a_classification(void)
{
    uint32_t bits;
    printf("-- EXHAUSTIVE: F_EPISODE_STABLE cannot change a classification, in any combination\n");
    for (bits = 0; bits < 0x8000u; bits++) {
        const uint32_t without = bits & (uint32_t)~GBP_VSTATE_F_EPISODE_STABLE;
        const uint32_t with    = without | GBP_VSTATE_F_EPISODE_STABLE;
        CHECK(gbp_vqueue_classify(40u, without, 0) == gbp_vqueue_classify(40u, with, 0));
        CHECK(gbp_vqueue_classify(39u, without, 0) == gbp_vqueue_classify(39u, with, 0));
        CHECK(gbp_vqueue_classify(40u, without, -1) == gbp_vqueue_classify(40u, with, -1));
    }
}

/* §V5.37.8/§V5.37.10. The residual `gbp_vqueue_balanced()` tolerates is not an
 * allowance, it is a state: the set of textures left READY when the run ended.
 * Two facts make the bound exactly GBP_VPRESENT_TEX_BUFFERS, and both are
 * checked here rather than asserted in prose:
 *
 *   1. a SUBMITTED buffer has ALREADY been dispositioned — the POC counts the
 *      terminal at submit time, so the teardown drain retires a GP token and
 *      never a frame. Only READY buffers can still be waiting.
 *   2. every texture buffer can be READY at once: one conversion finishes while
 *      a token is in flight, and the pump then fills the remaining free buffer.
 *
 * `gbp_vpresent_shutdown()` is what makes such a frame permanent: it refuses
 * every later submit, so no drain can dispose of it. */
static void test_the_residual_is_exactly_the_textures_left_ready(void)
{
    struct gbp_vpresent p;
    uint32_t i, ready;
    int first;
    printf("-- the undispositioned residual is exactly the READY textures, and the bound is the buffer count\n");

    gbp_vpresent_init(&p);
    first = gbp_vpresent_acquire(&p);
    CHECK(first >= 0);
    CHECK(gbp_vpresent_fill_done(&p, first) == 0);
    CHECK(gbp_vpresent_submit(&p, first) == 1);          /* dispositioned HERE, not at draw-done */
    CHECK(p.tex[first] == GBP_VPRESENT_SUBMITTED);

    /* Every remaining buffer can reach READY while that token is still in
     * flight, and each refused submit moves no counter at all. */
    ready = 0u;
    for (i = 1; i < GBP_VPRESENT_TEX_BUFFERS; i++) {
        const int b = gbp_vpresent_acquire(&p);
        CHECK(b >= 0);
        CHECK(gbp_vpresent_fill_done(&p, b) == 0);
        CHECK(gbp_vpresent_submit(&p, b) == 0);
        CHECK(p.tex[b] == GBP_VPRESENT_READY);
        ready++;
    }
    CHECK(p.submit_blocked_inflight == GBP_VPRESENT_TEX_BUFFERS - 1u);

    /* The drain releases the submitted buffer and nothing else, so it can free
     * one more slot but disposes of no waiting frame. */
    CHECK(gbp_vpresent_draw_done(&p) == first);
    CHECK(p.tex[first] == GBP_VPRESENT_FREE);
    for (i = 0; i < GBP_VPRESENT_TEX_BUFFERS; i++)
        if ((int)i != first) CHECK(p.tex[i] == GBP_VPRESENT_READY);

    /* And after shutdown the waiting frames can never be dispositioned: the
     * residual that survives the teardown is permanent by construction, which is
     * why the POC reports it on its own line instead of hiding it. */
    gbp_vpresent_shutdown(&p);
    for (i = 0; i < GBP_VPRESENT_TEX_BUFFERS; i++) {
        if (p.tex[i] != GBP_VPRESENT_READY) continue;
        CHECK(gbp_vpresent_submit(&p, (int)i) == 0);
        CHECK(p.tex[i] == GBP_VPRESENT_READY);
    }
    CHECK(p.submit_blocked_shutdown == ready);
    CHECK(gbp_vpresent_consistent(&p) == 1);

    /* The bound the queue enforces is exactly that maximum, no larger. */
    CHECK(GBP_VQUEUE_MAX_UNDISPOSITIONED == GBP_VPRESENT_TEX_BUFFERS);
}

int main(void)
{
    printf("== test_gbp_vstream (GBP-VIDEO-004 pure modules; every scenario SYNTHETIC)\n");
    test_geometry_constants();
    test_tile_index_landmarks();
    test_every_pixel_lands_exactly_once();
    test_raw_offsets_stay_inside_the_frame();
    test_conversion_round_trips();
    test_bytes_0_and_2_cannot_change_the_texture();
    test_the_source_word_is_never_modified();
    test_flag15_is_counted_separately();
    test_the_coordinate_list_is_bounded();
    test_bad_arguments_write_nothing();
    test_block_conversion_fills_exactly_one_tile_row();
    test_classification_matches_the_assembler();
    test_only_complete_frames_are_published();
    test_newest_wins_and_the_producer_never_waits();
    test_generation_guard_accepts_an_untouched_slot();
    test_generation_guard_rejects_a_reused_slot();
    test_an_overrun_is_not_source_loss();
    test_hold_previous_frame();
    test_the_pump_is_optional_and_inert();
    test_the_pump_runs_when_installed();
    test_a_latched_cause_skips_the_slice();
    test_the_slice_cost_is_a_bounded_aggregate();
    test_the_pacing_aggregates_are_bounded();
    test_the_sequence_may_wrap();
    test_an_unconfigured_queue_trusts_nothing();
    test_the_stream0001_bug_cannot_recur();
    test_the_callback_releases_only_the_indexed_buffer();
    test_never_two_submitted();
    test_a_spurious_callback_frees_nothing();
    test_a_submitted_buffer_can_never_be_taken_back();
    test_the_full_lifecycle();
    test_abandon_returns_a_buffer_unshown();
    test_shutdown_stops_new_work_but_not_the_gp();
    test_the_inconsistent_states_are_detected();
    test_xfb_never_targets_the_buffer_being_scanned();
    test_xfb_never_targets_a_pending_handover();
    test_xfb_alternates_and_never_blocks();
    test_texture_and_xfb_are_independent();
    test_a_self_test_presentation_leaves_the_queue_pristine();
    test_pristine_is_stricter_than_balanced();
    test_a_real_frame_still_balances();
    test_valid_transitions_latch_no_invariant_failure();
    test_a_transient_impossible_state_is_latched_even_after_it_heals();
    test_the_two_invariant_counters_stay_apart();
    test_the_audit_changed_no_state_transition();
    test_the_physical_stream0003_counters_conserve();
    test_the_episode_stable_bit_no_longer_aliases();
    test_a_stable_frame_is_eligible();
    test_a_true_majority_extra_frame_is_still_quarantined();
    test_every_frame_flag_is_a_distinct_power_of_two();
    test_every_converted_frame_terminal_balances();
    test_the_bounded_residual_is_accepted_and_bounded();
    test_episode_stable_never_changes_a_classification();
    test_the_residual_is_exactly_the_textures_left_ready();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
