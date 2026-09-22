/*
 * test_gbp_awin.c — Issue #59: the AUDIO window store (src/gbp/gbp_awin).
 * Synthetic blocks only. NOTHING HERE IS PHYSICAL EVIDENCE, and nothing here
 * can be: no image has run, and the window this module fills has never held a
 * byte the Game Boy Player produced.
 *
 * WHAT IS WORTH TESTING IS THE REFUSALS. Filling a window is the easy half.
 * The half that decides whether §V8's run is readable is what happens when the
 * Operator presses twice too quickly, presses a fifth time, releases a key,
 * or when a drain does not complete inside a window -- because each of those
 * has to be VISIBLE in the sidecar rather than silently absorbed.
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "gbp_awin.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static uint8_t *store;
static uint8_t block[GBP_AWIN_BLOCK_SIZE];

static void fill_block(uint8_t v) { memset(block, v, sizeof block); }

/* Every test starts from a ZEROED store. Without this, "nothing was written
 * here" would be read against another test's residue -- which is how a test
 * passes while the code under it does not work. */
static void reset(struct gbp_awin *w)
{
    memset(store, 0, GBP_AWIN_STORE_BYTES);
    gbp_awin_init(w, store, GBP_AWIN_STORE_BYTES);
}

static struct gbp_awin_press press_at(uint32_t n, uint16_t word, uint64_t t)
{
    struct gbp_awin_press p;
    memset(&p, 0, sizeof p);
    p.event_n = n; p.word = word; p.keys = word;
    p.t_poll = t; p.t_attempt = t + 10u; p.t_done = t + 20u; p.t_arm = t + 20u;
    return p;
}

/* feed `n` completed blocks, numbering them so the store can be checked */
static void feed(struct gbp_awin *w, uint32_t n, uint32_t first_cycle, uint8_t base)
{
    uint32_t i;
    for (i = 0; i < n; i++) {
        fill_block((uint8_t)(base + i));
        gbp_awin_block(w, block, GBP_AWIN_BLOCK_SIZE, first_cycle + i, 1);
    }
}

static void test_init_refuses_a_store_it_cannot_use(void)
{
    struct gbp_awin w;
    CHECK(gbp_awin_init(&w, 0, GBP_AWIN_STORE_BYTES) != 0);
    CHECK(strcmp(gbp_awin_fault(&w), "store_null") == 0);
    CHECK(gbp_awin_init(&w, store, GBP_AWIN_STORE_BYTES - 1u) != 0);
    CHECK(strcmp(gbp_awin_fault(&w), "store_too_small") == 0);
    CHECK(gbp_awin_init(&w, store + 1, GBP_AWIN_STORE_BYTES) != 0);
    CHECK(strcmp(gbp_awin_fault(&w), "store_misaligned") == 0);
    CHECK(gbp_awin_init(&w, store, GBP_AWIN_STORE_BYTES) == 0);
    CHECK(strcmp(gbp_awin_fault(&w), "-") == 0);
    CHECK(w.active == -1 && w.arms == 0u && w.next_press == 1u);
    /* §V8.3.2's numbers, from the module, not from a comment */
    CHECK(w.blocks_per_window == 256u && w.windows == 5u && w.block_size == 0x1000u);
    CHECK(GBP_AWIN_STORE_BYTES == 5u * 256u * 0x1000u);
    CHECK(GBP_AWIN_STORE_BYTES == 5242880u);
}

static void test_blocks_with_no_window_are_ignored_not_lost(void)
{
    struct gbp_awin w;
    reset(&w);
    feed(&w, 1000u, 1u, 0u);
    CHECK(w.blocks_seen == 1000u);
    CHECK(w.blocks_ignored == 1000u);
    CHECK(w.blocks_stored == 0u);
    CHECK(gbp_awin_stored_total(&w) == 0u);
    /* the expected majority of a run: ~4094 drains a second, 1280 kept */
    CHECK(gbp_awin_complete(&w) == 0);
}

static void test_a_window_fills_closes_and_disarms(void)
{
    struct gbp_awin w;
    struct gbp_awin_press p = press_at(7u, 0x0001u, 5000u);
    const uint8_t *bytes;
    reset(&w);
    CHECK(gbp_awin_arm_press(&w, &p) == 1);
    CHECK(w.active == 1);
    feed(&w, GBP_AWIN_BLOCKS, 100u, 0u);
    CHECK(w.active == -1);                       /* closed itself */
    CHECK(w.windows_closed == 1u);
    CHECK(w.anchor[1].flags == GBP_AWIN_F_CLOSED);
    CHECK(w.anchor[1].blocks == GBP_AWIN_BLOCKS);
    CHECK(w.anchor[1].first_cycle == 100u);
    CHECK(w.anchor[1].last_cycle == 100u + GBP_AWIN_BLOCKS - 1u);
    CHECK(w.anchor[1].event_n == 7u && w.anchor[1].word == 0x0001u);
    CHECK(w.anchor[1].t_poll == 5000u && w.anchor[1].t_attempt == 5010u && w.anchor[1].t_done == 5020u);
    /* the bytes are where the anchor says, in drain order */
    bytes = gbp_awin_window_bytes(&w, 1u);
    CHECK(bytes != 0);
    CHECK(bytes[0] == 0u);
    CHECK(bytes[GBP_AWIN_BLOCK_SIZE] == 1u);
    CHECK(bytes[(size_t)(GBP_AWIN_BLOCKS - 1u) * GBP_AWIN_BLOCK_SIZE] == (uint8_t)(GBP_AWIN_BLOCKS - 1u));
    /* and nothing was written into a neighbour */
    CHECK(gbp_awin_window_bytes(&w, 2u)[0] == 0u);
}

static void test_a_press_while_a_window_fills_is_refused_not_queued(void)
{
    struct gbp_awin w;
    struct gbp_awin_press a = press_at(1u, 0x0001u, 1000u), b = press_at(2u, 0x0002u, 1100u);
    reset(&w);
    CHECK(gbp_awin_arm_press(&w, &a) == 1);
    feed(&w, 10u, 1u, 0u);
    CHECK(gbp_awin_arm_press(&w, &b) == -1);     /* §V8.10 wants three seconds between presses */
    CHECK(w.arm_refused_busy == 1u);
    CHECK(w.next_press == 2u);                   /* the refused press did NOT consume a window */
    CHECK(w.anchor[1].event_n == 1u);            /* and did not overwrite the anchor */
    CHECK(w.anchor[2].blocks == 0u);
    feed(&w, GBP_AWIN_BLOCKS - 10u, 11u, 0u);
    CHECK(gbp_awin_arm_press(&w, &b) == 2);      /* once it closed, the next press is taken */
    CHECK(w.anchor[2].event_n == 2u);
}

static void test_a_fifth_press_cannot_overwrite_the_first(void)
{
    struct gbp_awin w;
    unsigned i;
    reset(&w);
    for (i = 1u; i <= GBP_AWIN_PRESS_WINDOWS; i++) {
        struct gbp_awin_press p = press_at(i, (uint16_t)(1u << i), 1000u * i);
        CHECK(gbp_awin_arm_press(&w, &p) == (int)i);
        feed(&w, GBP_AWIN_BLOCKS, 1000u * i, (uint8_t)i);
    }
    CHECK(gbp_awin_complete(&w) == 1);
    {
        struct gbp_awin_press fifth = press_at(99u, 0x0100u, 90000u);
        CHECK(gbp_awin_arm_press(&w, &fifth) == -1);
        CHECK(w.arm_refused_full == 1u);
        CHECK(w.anchor[1].event_n == 1u);        /* the first window is intact */
        CHECK(gbp_awin_window_bytes(&w, 1u)[0] == 1u);
    }
    /* and blocks after the last window are ignored, not appended anywhere */
    feed(&w, 50u, 99999u, 0xEEu);
    CHECK(w.blocks_ignored == 50u);
    CHECK(gbp_awin_stored_total(&w) == GBP_AWIN_PRESS_WINDOWS * GBP_AWIN_BLOCKS);
}

static void test_a_failed_drain_is_a_flagged_gap_and_not_a_stored_block(void)
{
    struct gbp_awin w;
    struct gbp_awin_press p = press_at(3u, 0x0004u, 2000u);
    reset(&w);
    gbp_awin_arm_press(&w, &p);
    feed(&w, 4u, 10u, 0x10u);
    fill_block(0xFF);
    gbp_awin_block(&w, block, GBP_AWIN_BLOCK_SIZE, 14u, 0);        /* did not complete */
    CHECK(w.blocks_failed == 1u);
    CHECK(w.anchor[1].skipped == 1u);
    CHECK(w.anchor[1].flags & GBP_AWIN_F_GAP);
    CHECK(w.anchor[1].blocks == 4u);                               /* the window did NOT advance */
    CHECK(gbp_awin_window_bytes(&w, 1u)[(size_t)4u * GBP_AWIN_BLOCK_SIZE] == 0u);   /* nothing written */
    /* a short or null block is refused the same way */
    gbp_awin_block(&w, block, GBP_AWIN_BLOCK_SIZE - 1u, 15u, 1);
    gbp_awin_block(&w, 0, GBP_AWIN_BLOCK_SIZE, 16u, 1);
    CHECK(w.blocks_failed == 3u && w.anchor[1].blocks == 4u);
}

static void test_the_control_is_armed_once_and_is_window_zero(void)
{
    struct gbp_awin w;
    struct gbp_awin_press p = press_at(1u, 0x0001u, 1000u);
    reset(&w);
    CHECK(gbp_awin_arm_control(&w, 4242u) == 0);
    CHECK(w.anchor[0].kind == (uint32_t)GBP_AWIN_CONTROL);
    CHECK(w.anchor[0].ordinal == 0u && w.anchor[0].event_n == 0u && w.anchor[0].word == 0u);
    CHECK(w.anchor[0].t_arm == 4242u);
    CHECK(gbp_awin_arm_control(&w, 5000u) == -1);   /* busy */
    CHECK(gbp_awin_arm_press(&w, &p) == -1);        /* and a press during the control is refused too */
    CHECK(w.arm_refused_busy == 2u);
    feed(&w, GBP_AWIN_BLOCKS, 1u, 0x20u);
    CHECK(w.anchor[0].flags & GBP_AWIN_F_CLOSED);
    CHECK(gbp_awin_arm_control(&w, 9000u) == -1);   /* never re-armed */
    CHECK(w.arm_refused_full == 1u);
    CHECK(gbp_awin_arm_press(&w, &p) == 1);         /* the presses still have their four */
}

static void test_the_capture_is_complete_without_the_control(void)
{
    /* §V8.5.2 reads a missing control as INCONCLUSIVE, not as a reason to keep
     * the run going: completion is the four PRESS windows. */
    struct gbp_awin w;
    unsigned i;
    reset(&w);
    for (i = 1u; i <= GBP_AWIN_PRESS_WINDOWS; i++) {
        struct gbp_awin_press p = press_at(i, (uint16_t)(1u << i), 1000u * i);
        gbp_awin_arm_press(&w, &p);
        CHECK(gbp_awin_complete(&w) == 0);
        feed(&w, GBP_AWIN_BLOCKS, 1000u * i, (uint8_t)i);
    }
    CHECK(gbp_awin_complete(&w) == 1);
    CHECK(w.anchor[0].blocks == 0u && w.anchor[0].flags == 0u);
}

static void test_finish_marks_a_window_that_was_still_filling(void)
{
    struct gbp_awin w;
    struct gbp_awin_press p = press_at(5u, 0x0008u, 3000u);
    reset(&w);
    gbp_awin_arm_press(&w, &p);
    feed(&w, 17u, 1u, 0x30u);
    gbp_awin_finish(&w);
    CHECK(w.active == -1);
    CHECK(w.anchor[1].flags & GBP_AWIN_F_INCOMPLETE);
    CHECK(!(w.anchor[1].flags & GBP_AWIN_F_CLOSED));
    CHECK(w.anchor[1].blocks == 17u);
    gbp_awin_finish(&w);                     /* idempotent */
    CHECK(w.active == -1);
    feed(&w, 5u, 99u, 0x40u);                /* and nothing is kept after it */
    CHECK(w.anchor[1].blocks == 17u);
}

static void test_the_ticks_are_reported_and_never_invented(void)
{
    struct gbp_awin w;
    reset(&w);
    CHECK(gbp_awin_ticks_mean(&w) == 0u && w.ticks_n == 0u);
    gbp_awin_note_ticks(&w, 40u);
    gbp_awin_note_ticks(&w, 10u);
    gbp_awin_note_ticks(&w, 70u);
    CHECK(w.ticks_min == 10u && w.ticks_max == 70u && w.ticks_n == 3u);
    CHECK(gbp_awin_ticks_mean(&w) == 40u);
}

static void test_null_is_survivable_everywhere(void)
{
    CHECK(gbp_awin_init(0, store, GBP_AWIN_STORE_BYTES) != 0);
    CHECK(strcmp(gbp_awin_fault(0), "null") == 0);
    gbp_awin_block(0, block, GBP_AWIN_BLOCK_SIZE, 1u, 1);
    gbp_awin_note_ticks(0, 1u);
    gbp_awin_finish(0);
    CHECK(gbp_awin_complete(0) == 0);
    CHECK(gbp_awin_window_bytes(0, 0u) == 0);
    CHECK(gbp_awin_stored_total(0) == 0u);
    CHECK(gbp_awin_ticks_mean(0) == 0u);
    CHECK(gbp_awin_arm_control(0, 0u) == -1);
    CHECK(gbp_awin_arm_press(0, 0) == -1);
}

int main(void)
{
    void *p = 0;
    if (posix_memalign(&p, 32u, GBP_AWIN_STORE_BYTES + 64u) != 0 || !p) {
        fprintf(stderr, "cannot allocate the window store\n");
        return 2;
    }
    store = (uint8_t *)p;
    memset(store, 0, GBP_AWIN_STORE_BYTES + 64u);

    test_init_refuses_a_store_it_cannot_use();
    test_blocks_with_no_window_are_ignored_not_lost();
    test_a_window_fills_closes_and_disarms();
    test_a_press_while_a_window_fills_is_refused_not_queued();
    test_a_fifth_press_cannot_overwrite_the_first();
    test_a_failed_drain_is_a_flagged_gap_and_not_a_stored_block();
    test_the_control_is_armed_once_and_is_window_zero();
    test_the_capture_is_complete_without_the_control();
    test_finish_marks_a_window_that_was_still_filling();
    test_the_ticks_are_reported_and_never_invented();
    test_null_is_survivable_everywhere();

    free(p);
    printf("test_gbp_awin: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
