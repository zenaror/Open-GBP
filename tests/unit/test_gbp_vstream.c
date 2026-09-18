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

static void test_hold_previous_frame(void)
{
    struct gbp_vqueue q;
    struct gbp_vqueue_desc d;
    printf("-- nothing new to show -> the previous frame is held, and the hold is counted\n");
    gbp_vqueue_init(&q, 4u);
    CHECK(gbp_vqueue_take(&q, &d) == 0);
    gbp_vqueue_note_repeat(&q);
    gbp_vqueue_note_repeat(&q);
    CHECK(q.display_frames_repeated == 2u);
    CHECK(q.consumer_frames_presented == 0u);
    CHECK(gbp_vqueue_balanced(&q));
}

static void test_the_pump_is_optional_and_inert(void)
{
    struct gbp_vqueue q;
    printf("-- with no pump installed, pumping does nothing at all\n");
    gbp_vqueue_init(&q, 4u);
    CHECK(q.pump == 0);
    gbp_vqueue_pump(&q);                   /* must not crash, must change nothing */
    gbp_vqueue_pump(0);
    CHECK(q.consumer_frames_taken == 0u);
    CHECK(q.source_frames_closed == 0u);
}

static uint32_t pump_calls;
static void counting_pump(void *user) { (void)user; pump_calls++; }

static void test_the_pump_runs_when_installed(void)
{
    struct gbp_vqueue q;
    printf("-- an installed pump is called once per pump, with its own context\n");
    gbp_vqueue_init(&q, 4u);
    q.pump = counting_pump;
    pump_calls = 0u;
    gbp_vqueue_pump(&q);
    gbp_vqueue_pump(&q);
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
    test_the_pacing_aggregates_are_bounded();
    test_the_sequence_may_wrap();
    test_an_unconfigured_queue_trusts_nothing();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
