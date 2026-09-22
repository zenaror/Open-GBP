/*
 * test_gbp_awindump.c — Issue #59: the OGBPAW1 sidecar (src/gbp/gbp_awindump),
 * written and read back on the host. Synthetic windows only; no image has run
 * and nothing here is physical evidence.
 *
 * THE PARSER IS THE TEST. A writer nobody can check writes whatever it likes,
 * so every case below writes a file, parses it strictly, and then MUTATES one
 * byte or one field and requires the parser to refuse with the stated code. A
 * format whose parser accepts a corrupted file is a format that will one day
 * be read as evidence after a bad SD write.
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "gbp_awindump.h"
#include "gbp_crc32.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static uint8_t *store;
static uint8_t *out;
static uint32_t out_n, out_cap;

static int sink(void *ctx, const uint8_t *data, uint32_t len)
{
    (void)ctx;
    if (out_n + len > out_cap) return -1;
    memcpy(out + out_n, data, len);
    out_n += len;
    return 0;
}

static int sink_short(void *ctx, const uint8_t *data, uint32_t len)
{
    /* refuses once past a small budget: the truncation path */
    (void)ctx;
    if (out_n + len > 4096u) return -1;
    memcpy(out + out_n, data, len);
    out_n += len;
    return 0;
}

static uint8_t block[GBP_AWIN_BLOCK_SIZE];

static void feed(struct gbp_awin *w, uint32_t n, uint32_t cyc, uint8_t base)
{
    uint32_t i;
    for (i = 0; i < n; i++) {
        memset(block, (int)(uint8_t)(base + i), sizeof block);
        gbp_awin_block(w, block, GBP_AWIN_BLOCK_SIZE, cyc + i, 1);
    }
}

/* A window model with `presses` full press windows and an optional control.
 * SMALL on purpose: the sizes come from the module's constants, and a test that
 * writes 5 MB per case is a test nobody runs. */
static void build(struct gbp_awin *w, int control, unsigned presses, unsigned partial)
{
    unsigned i;
    memset(store, 0, GBP_AWIN_STORE_BYTES);
    gbp_awin_init(w, store, GBP_AWIN_STORE_BYTES);
    if (control) {
        gbp_awin_arm_control(w, 1234u);
        feed(w, GBP_AWIN_BLOCKS, 10u, 0xC0u);
    }
    for (i = 1u; i <= presses; i++) {
        struct gbp_awin_press p;
        memset(&p, 0, sizeof p);
        p.event_n = i; p.word = (uint16_t)(1u << i); p.keys = p.word;
        p.t_poll = 1000u * i; p.t_attempt = p.t_poll + 5u; p.t_done = p.t_poll + 9u; p.t_arm = p.t_done;
        gbp_awin_arm_press(w, &p);
        feed(w, GBP_AWIN_BLOCKS, 100u * i, (uint8_t)i);
    }
    if (partial) {
        struct gbp_awin_press p;
        memset(&p, 0, sizeof p);
        p.event_n = 90u; p.word = 0x0080u; p.keys = p.word;
        gbp_awin_arm_press(w, &p);
        feed(w, partial, 9000u, 0x70u);
        gbp_awin_finish(w);
    }
}

static long write_it(struct gbp_awin *w, struct gbp_awindump_info *info, gbp_awindump_sink s)
{
    uint8_t chunk[GBP_AWINDUMP_CHUNK];
    uint64_t written = 0;
    memset(info, 0, sizeof *info);
    info->tb_hz = 40500000u;
    CHECK(gbp_awindump_set_identity(info, "GBP-AUDIO-001", "stream-0016",
                                    "gbp-audio-window-probe", "abcdef1") == 0);
    out_n = 0;
    return gbp_awindump_stream(info, w, chunk, sizeof chunk, s, 0, &written);
}

static void test_a_full_capture_round_trips(void)
{
    struct gbp_awin w;
    struct gbp_awindump_info info, back;
    const uint8_t *recs = 0, *blocks = 0;
    long n;
    build(&w, 1, GBP_AWIN_PRESS_WINDOWS, 0u);
    n = write_it(&w, &info, sink);
    CHECK(n > 0);
    CHECK((uint64_t)n == info.total_size);
    CHECK(info.windows_n == GBP_AWIN_WINDOWS);
    CHECK(info.blocks_stored == GBP_AWIN_WINDOWS * GBP_AWIN_BLOCKS);
    CHECK(info.flags == 0u);
    CHECK((uint64_t)n == (uint64_t)GBP_AWINDUMP_HEADER_SIZE
                        + (uint64_t)GBP_AWIN_WINDOWS * GBP_AWINDUMP_RECORD_SIZE
                        + (uint64_t)GBP_AWIN_WINDOWS * GBP_AWIN_BLOCKS * GBP_AWIN_BLOCK_SIZE
                        + GBP_AWINDUMP_FOOTER_SIZE);
    CHECK(gbp_awindump_parse(out, out_n, &back, &recs, &blocks) == 0);
    CHECK(back.windows_n == GBP_AWIN_WINDOWS && back.blocks_stored == info.blocks_stored);
    CHECK(strcmp(back.test_id, "GBP-AUDIO-001") == 0);
    CHECK(strcmp(back.build_id, "stream-0016") == 0);
    CHECK(strcmp(back.app, "gbp-audio-window-probe") == 0);
    CHECK(strcmp(back.commit, "abcdef1") == 0);
    CHECK(back.tb_hz == 40500000u);
    CHECK(recs != 0 && blocks != 0);
    /* the anchor a reader needs: press 2's event and its three instants */
    CHECK(recs[2u * GBP_AWINDUMP_RECORD_SIZE + 0x13u] == 2u);     /* event_n, last byte of the u32 */
    /* and the bytes are the window's own, in drain order */
    CHECK(blocks[0] == 0xC0u);                                     /* the control first */
    CHECK(blocks[(size_t)GBP_AWIN_BLOCKS * GBP_AWIN_BLOCK_SIZE] == 1u);   /* then press 1 */
}

static void test_an_incomplete_window_is_carried_and_flagged(void)
{
    struct gbp_awin w;
    struct gbp_awindump_info info, back;
    long n;
    build(&w, 1, 2u, 33u);
    n = write_it(&w, &info, sink);
    CHECK(n > 0);
    CHECK(info.flags & GBP_AWINDUMP_FLAG_INCOMPLETE);
    CHECK(info.blocks_stored == 3u * GBP_AWIN_BLOCKS + 33u);
    CHECK(gbp_awindump_parse(out, out_n, &back, 0, 0) == 0);
    CHECK(back.flags & GBP_AWINDUMP_FLAG_INCOMPLETE);
}

static void test_a_refused_press_is_carried(void)
{
    struct gbp_awin w;
    struct gbp_awindump_info info, back;
    struct gbp_awin_press p;
    build(&w, 0, GBP_AWIN_PRESS_WINDOWS, 0u);
    memset(&p, 0, sizeof p);
    p.event_n = 99u; p.word = 0x0200u;
    CHECK(gbp_awin_arm_press(&w, &p) == -1);
    CHECK(write_it(&w, &info, sink) > 0);
    CHECK(info.flags & GBP_AWINDUMP_FLAG_REFUSED);
    CHECK(info.arm_refused_full == 1u);
    CHECK(gbp_awindump_parse(out, out_n, &back, 0, 0) == 0);
    CHECK(back.arm_refused_full == 1u);
}

static void test_a_gap_is_carried(void)
{
    struct gbp_awin w;
    struct gbp_awindump_info info, back;
    struct gbp_awin_press p;
    memset(store, 0, GBP_AWIN_STORE_BYTES);
    gbp_awin_init(&w, store, GBP_AWIN_STORE_BYTES);
    memset(&p, 0, sizeof p);
    p.event_n = 1u; p.word = 0x0002u;
    gbp_awin_arm_press(&w, &p);
    feed(&w, 5u, 1u, 0x10u);
    gbp_awin_block(&w, block, GBP_AWIN_BLOCK_SIZE, 6u, 0);
    feed(&w, GBP_AWIN_BLOCKS - 5u, 7u, 0x20u);
    CHECK(write_it(&w, &info, sink) > 0);
    CHECK(info.flags & GBP_AWINDUMP_FLAG_GAP);
    CHECK(info.blocks_failed == 1u);
    CHECK(gbp_awindump_parse(out, out_n, &back, 0, 0) == 0);
    CHECK(back.flags & GBP_AWINDUMP_FLAG_GAP);
    CHECK(back.blocks_failed == 1u);
}

static void test_a_sink_that_gives_up_is_a_truncation_not_a_lie(void)
{
    struct gbp_awin w;
    struct gbp_awindump_info info;
    build(&w, 1, 1u, 0u);
    CHECK(write_it(&w, &info, sink_short) == -4);
    CHECK(info.flags & GBP_AWINDUMP_FLAG_TRUNCATED);
    /* and what came out is NOT a valid file */
    {
        struct gbp_awindump_info back;
        CHECK(gbp_awindump_parse(out, out_n, &back, 0, 0) != 0);
    }
}

static void test_an_identity_that_does_not_fit_is_refused_before_writing(void)
{
    struct gbp_awin w;
    struct gbp_awindump_info info;
    uint8_t chunk[GBP_AWINDUMP_CHUNK];
    uint64_t written = 1u;
    build(&w, 0, 1u, 0u);
    memset(&info, 0, sizeof info);
    CHECK(gbp_awindump_set_identity(&info, "GBP-AUDIO-001",
                                    "a-build-id-that-is-far-too-long-to-fit-in-the-field",
                                    "app", "commit") != 0);
    CHECK(info.identity_error == 1);
    out_n = 0;
    CHECK(gbp_awindump_stream(&info, &w, chunk, sizeof chunk, sink, 0, &written) == -2);
    CHECK(written == 0u && out_n == 0u);
}

static void test_the_parser_refuses_what_it_should(void)
{
    struct gbp_awin w;
    struct gbp_awindump_info info, back;
    uint8_t *copy;
    uint32_t n;
    build(&w, 1, 1u, 0u);
    CHECK(write_it(&w, &info, sink) > 0);
    n = out_n;
    copy = (uint8_t *)malloc(n);
    CHECK(copy != 0);
    if (!copy) return;

#define MUTATE(off, val, want) do {                                  \
        memcpy(copy, out, n);                                        \
        copy[(off)] ^= (uint8_t)(val);                               \
        CHECK(gbp_awindump_parse(copy, n, &back, 0, 0) == (want));   \
    } while (0)

    MUTATE(0u, 0xFF, -1);                                  /* the magic */
    MUTATE(0x09u, 0x01, -2);                               /* the version */
    MUTATE(0x11u, 0x01, -2);                               /* the block size */
    MUTATE(0x0Cu, 0x80, -3);                               /* a header field, header CRC */
    /* A record field: the WHOLE-FILE CRC catches it first (-6), because the
     * footer CRC is verified before the per-record loop. The per-record CRC is
     * not redundant -- it is what lets a reader seek to one window's anchor and
     * trust it without hashing 5 MB -- but the order is what it is, and the
     * test says so rather than asserting the code it wishes existed. */
    MUTATE(GBP_AWINDUMP_HEADER_SIZE + 0x11u, 0x01, -6);
    MUTATE(n - 12u, 0xFF, -5);                             /* the footer magic */
    MUTATE(n - 1u, 0x01, -6);                              /* the footer CRC */
    MUTATE(GBP_AWINDUMP_HEADER_SIZE + 2u * GBP_AWINDUMP_RECORD_SIZE + 100u, 0xFF, -6);  /* a BLOCK byte */
    /* a truncated file is refused on length, not read short */
    memcpy(copy, out, n);
    CHECK(gbp_awindump_parse(copy, n - 1u, &back, 0, 0) == -4);
    CHECK(gbp_awindump_parse(copy, 4u, &back, 0, 0) == -1);
    CHECK(gbp_awindump_parse(0, n, &back, 0, 0) == -1);
    CHECK(gbp_awindump_parse(copy, n, 0, 0, 0) == -1);
    /* and the per-record CRC IS reachable: rebuild the footer CRC over the
     * mutated body, and the record check is then the one that refuses. */
    {
        uint32_t crc;
        memcpy(copy, out, n);
        copy[GBP_AWINDUMP_HEADER_SIZE + 0x11u] ^= 0x01u;
        crc = gbp_crc32(copy, n - GBP_AWINDUMP_FOOTER_SIZE);   /* the footer CRC covers everything BEFORE the footer */
        copy[n - 4u] = (uint8_t)(crc >> 24); copy[n - 3u] = (uint8_t)(crc >> 16);
        copy[n - 2u] = (uint8_t)(crc >> 8);  copy[n - 1u] = (uint8_t)crc;
        CHECK(gbp_awindump_parse(copy, n, &back, 0, 0) == -9);
    }
#undef MUTATE
    free(copy);
}

static void test_a_reserved_byte_is_not_a_free_field(void)
{
    struct gbp_awin w;
    struct gbp_awindump_info info, back;
    uint8_t *copy;
    uint32_t n;
    build(&w, 0, 1u, 0u);
    CHECK(write_it(&w, &info, sink) > 0);
    n = out_n;
    copy = (uint8_t *)malloc(n);
    CHECK(copy != 0);
    if (!copy) return;
    memcpy(copy, out, n);
    copy[0xF4u] = 0x01u;                                   /* a reserved header byte */
    /* the header CRC covers it, so the refusal comes first on the CRC */
    CHECK(gbp_awindump_parse(copy, n, &back, 0, 0) == -3);
    free(copy);
}

int main(void)
{
    void *p = 0, *q = 0;
    out_cap = GBP_AWINDUMP_HEADER_SIZE + GBP_AWIN_WINDOWS * GBP_AWINDUMP_RECORD_SIZE
              + GBP_AWIN_STORE_BYTES + GBP_AWINDUMP_FOOTER_SIZE;
    if (posix_memalign(&p, 32u, GBP_AWIN_STORE_BYTES) != 0 || !p) return 2;
    q = malloc(out_cap);
    if (!q) return 2;
    store = (uint8_t *)p;
    out = (uint8_t *)q;

    test_a_full_capture_round_trips();
    test_an_incomplete_window_is_carried_and_flagged();
    test_a_refused_press_is_carried();
    test_a_gap_is_carried();
    test_a_sink_that_gives_up_is_a_truncation_not_a_lie();
    test_an_identity_that_does_not_fit_is_refused_before_writing();
    test_the_parser_refuses_what_it_should();
    test_a_reserved_byte_is_not_a_free_field();

    free(p); free(q);
    printf("test_gbp_awindump: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
