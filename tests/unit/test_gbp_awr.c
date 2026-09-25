/*
 * test_gbp_awr.c — Issue #117: the raw-block ride-along store (src/gbp/gbp_awr)
 * and its OGBPAWR1 serializer. Synthetic blocks only: NOTHING HERE IS PHYSICAL
 * EVIDENCE, and nothing here can be — no image has run this module.
 *
 * WHAT IS WORTH TESTING. The fill is the easy half. The half that decides
 * whether the file is readable is the edge: the block that arrives after the
 * store is full (ignored and counted, never overwriting), the block of the
 * wrong length (a fault, never a hole), the second arm (refused), the
 * teardown inside a fill (DONE with fewer blocks than the cap, never a
 * closed-looking header), and the bytes of the header — recomputed here with
 * gbp_crc32, not trusted from the module.
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "gbp_awr.h"
#include "gbp_crc32.h"

static int failures, checks;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

#define CAP 3u
static uint8_t store[CAP * GBP_AWR_BLOCK_SIZE];
static uint8_t block[GBP_AWR_BLOCK_SIZE];

static uint32_t get_u32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}
static uint64_t get_u64(const uint8_t *p) { return ((uint64_t)get_u32(p) << 32) | (uint64_t)get_u32(p + 4); }

/* Every test starts from a ZEROED store, so "nothing was written here" is
 * read against zero and not against another test's residue. */
static void reset(struct gbp_awr *w)
{
    memset(store, 0, sizeof store);
    CHECK(gbp_awr_init(w, store, CAP, 40500000u) == 0);
}

static void fill_block(uint8_t v) { memset(block, v, sizeof block); }

static int store_is(uint32_t index, uint8_t v)
{
    size_t i;
    const uint8_t *p = store + (size_t)index * GBP_AWR_BLOCK_SIZE;
    for (i = 0; i < GBP_AWR_BLOCK_SIZE; i++) if (p[i] != v) return 0;
    return 1;
}

static void test_init_refuses_what_it_cannot_use(void)
{
    struct gbp_awr w;
    CHECK(gbp_awr_init(&w, 0, CAP, 1u) != 0);
    CHECK(strcmp(gbp_awr_fault(&w), "store_null") == 0);
    CHECK(gbp_awr_init(&w, store, 0u, 1u) != 0);
    CHECK(strcmp(gbp_awr_fault(&w), "cap_zero") == 0);
    CHECK(gbp_awr_init(&w, store, 1u, 1u) == 0);          /* any N >= 1 */
    CHECK(strcmp(gbp_awr_fault(&w), "-") == 0);
    CHECK(w.state == GBP_AWR_IDLE && w.blocks_cap == 1u && w.tb_hz == 1u);
    CHECK(gbp_awr_done(&w) == 0);
    /* a block before the arm is ignored, never stored */
    fill_block(0x11u);
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 5u, 1u) == 0);
    CHECK(w.seen == 1u && w.ignored == 1u && w.blocks_stored == 0u && w.faults == 0u);
    CHECK(GBP_AWR_HEADER_SIZE == 0x80u && GBP_AWR_FOOTER_SIZE == 12u && GBP_AWR_BLOCK_SIZE == 4096u);
}

static void test_arm_fill_done_and_the_fourth_block(void)
{
    struct gbp_awr w;
    reset(&w);
    CHECK(gbp_awr_arm(&w, 1000u) == 0);
    CHECK(w.state == GBP_AWR_ARMED && w.t_arm == 1000u);
    CHECK(gbp_awr_arm(&w, 1001u) == -1);                   /* armed once, ever */
    CHECK(w.arm_refused == 1u && w.t_arm == 1000u);

    fill_block(0xA1u);
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 2000u, 70u) == 1);
    CHECK(w.state == GBP_AWR_FILLING && w.blocks_stored == 1u);
    CHECK(w.t_first == 2000u && w.t_last == 2000u && w.seq_first == 70u && w.seq_last == 70u);
    fill_block(0xA2u);
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 2244u, 71u) == 1);
    CHECK(w.state == GBP_AWR_FILLING && gbp_awr_done(&w) == 0);
    fill_block(0xA3u);
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 2488u, 72u) == 1);
    CHECK(w.state == GBP_AWR_DONE && gbp_awr_done(&w) == 1);
    CHECK(w.blocks_stored == 3u);
    CHECK(w.t_first == 2000u && w.t_last == 2488u && w.seq_first == 70u && w.seq_last == 72u);
    CHECK(store_is(0u, 0xA1u) && store_is(1u, 0xA2u) && store_is(2u, 0xA3u));

    /* the fourth block: refused, counted, and the store untouched */
    fill_block(0xA4u);
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 2732u, 73u) == 0);
    CHECK(w.seen == 4u && w.ignored == 1u && w.blocks_stored == 3u && w.faults == 0u);
    CHECK(w.t_last == 2488u && w.seq_last == 72u);
    CHECK(store_is(0u, 0xA1u) && store_is(1u, 0xA2u) && store_is(2u, 0xA3u));
    CHECK(gbp_awr_arm(&w, 3000u) == -1 && w.arm_refused == 2u);   /* not re-armable after done */

    CHECK(gbp_awr_block_bytes(&w, 0u) == store);
    CHECK(gbp_awr_block_bytes(&w, 2u) == store + 2u * GBP_AWR_BLOCK_SIZE);
    CHECK(gbp_awr_block_bytes(&w, 3u) == 0);
    CHECK(gbp_awr_total(&w) == 0x80u + 3u * 4096u + 12u);
}

static void test_a_wrong_length_is_a_fault_and_not_a_hole(void)
{
    struct gbp_awr w;
    reset(&w);
    CHECK(gbp_awr_arm(&w, 10u) == 0);
    fill_block(0x5Au);
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE - 1u, 20u, 1u) == 0);
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE + 1u, 21u, 2u) == 0);
    CHECK(gbp_awr_block(&w, 0, GBP_AWR_BLOCK_SIZE, 22u, 3u) == 0);
    CHECK(w.faults == 3u && w.blocks_stored == 0u && w.state == GBP_AWR_ARMED);
    CHECK(w.t_first == 0u && w.seq_first == 0u);
    CHECK(store_is(0u, 0u));
    /* the next good block is the FIRST stored block */
    fill_block(0x5Bu);
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 23u, 4u) == 1);
    CHECK(w.blocks_stored == 1u && w.t_first == 23u && w.seq_first == 4u && store_is(0u, 0x5Bu));
    CHECK(w.seen == 4u && w.ignored == 0u);
}

static void test_finish_closes_a_fill_without_pretending(void)
{
    struct gbp_awr w;
    reset(&w);
    gbp_awr_finish(&w);                                     /* idle: nothing happens */
    CHECK(w.state == GBP_AWR_IDLE);
    CHECK(gbp_awr_arm(&w, 5u) == 0);
    fill_block(0x33u);
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 6u, 9u) == 1);
    gbp_awr_finish(&w);
    CHECK(w.state == GBP_AWR_DONE && gbp_awr_done(&w) == 1);
    CHECK(w.blocks_stored == 1u && w.blocks_cap == CAP);   /* the header will say 1 of 3 */
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 7u, 10u) == 0);
    CHECK(w.ignored == 1u && w.blocks_stored == 1u);
    /* armed and never filled, then finished: DONE with zero blocks */
    reset(&w);
    CHECK(gbp_awr_arm(&w, 5u) == 0);
    gbp_awr_finish(&w);
    CHECK(w.state == GBP_AWR_DONE && w.blocks_stored == 0u && gbp_awr_total(&w) == 0x80u + 12u);
}

static void test_the_cost_is_reported_and_never_invented(void)
{
    struct gbp_awr w;
    reset(&w);
    CHECK(gbp_awr_copy_mean(&w) == 0u && w.copy_n == 0u && w.copy_min == 0u && w.copy_max == 0u);
    gbp_awr_note_cost(&w, 1300u);
    CHECK(w.copy_min == 1300u && w.copy_max == 1300u && w.copy_n == 1u && w.copy_sum == 1300u);
    gbp_awr_note_cost(&w, 900u);
    gbp_awr_note_cost(&w, 1437u);
    CHECK(w.copy_min == 900u && w.copy_max == 1437u && w.copy_n == 3u && w.copy_sum == 3637u);
    CHECK(gbp_awr_copy_mean(&w) == 1212u);
    gbp_awr_note_cost(&w, 0u);
    CHECK(w.copy_min == 0u && w.copy_n == 4u);
}

static void test_the_header_bytes(void)
{
    struct gbp_awr w;
    uint8_t h[GBP_AWR_HEADER_SIZE + 4u];
    unsigned i;
    reset(&w);
    memset(h, 0xEE, sizeof h);
    CHECK(gbp_awr_header(&w, h, GBP_AWR_HEADER_SIZE - 1u) == 0u);   /* too small: nothing */
    CHECK(h[0] == 0xEEu);
    CHECK(gbp_awr_header(0, h, sizeof h) == 0u);
    CHECK(gbp_awr_header(&w, 0, sizeof h) == 0u);

    CHECK(gbp_awr_arm(&w, 0x0000000100000002ull) == 0);
    gbp_awr_arm(&w, 1u);                                    /* refused: 1 */
    fill_block(0x01u);
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 0x0000000200000003ull, 40u) == 1);
    CHECK(gbp_awr_block(&w, block, 17u, 0u, 41u) == 0);   /* fault: 1 */
    fill_block(0x02u);
    CHECK(gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 0x0000000300000004ull, 42u) == 1);
    gbp_awr_note_cost(&w, 1000u);
    gbp_awr_note_cost(&w, 1500u);

    CHECK(gbp_awr_header(&w, h, sizeof h) == GBP_AWR_HEADER_SIZE);
    CHECK(h[GBP_AWR_HEADER_SIZE] == 0xEEu);                /* wrote exactly 0x80 */
    CHECK(memcmp(h, "OGBPAWR1", 8) == 0);
    CHECK(get_u32(h + 0x08) == 1u);                         /* version */
    CHECK(get_u32(h + 0x0C) == 4096u);                      /* block size */
    CHECK(get_u32(h + 0x10) == 2u);                         /* blocks stored */
    CHECK(get_u32(h + 0x14) == CAP);                        /* blocks cap */
    CHECK(get_u32(h + 0x18) == 40500000u);                  /* tb_hz */
    CHECK(get_u32(h + 0x1C) == (uint32_t)GBP_AWR_FILLING);  /* state */
    CHECK(get_u64(h + 0x20) == 0x0000000100000002ull);      /* t_arm */
    CHECK(get_u64(h + 0x28) == 0x0000000200000003ull);      /* t_first */
    CHECK(get_u64(h + 0x30) == 0x0000000300000004ull);      /* t_last */
    CHECK(get_u32(h + 0x38) == 1000u);                      /* copy min */
    CHECK(get_u32(h + 0x3C) == 1500u);                      /* copy max */
    CHECK(get_u64(h + 0x40) == 2500u);                      /* copy sum */
    CHECK(get_u32(h + 0x48) == 2u);                         /* copy n */
    CHECK(get_u32(h + 0x4C) == 1u);                         /* faults */
    CHECK(get_u32(h + 0x50) == 0u);                         /* ignored */
    CHECK(get_u32(h + 0x54) == 3u);                         /* seen */
    CHECK(get_u32(h + 0x58) == 40u);                        /* seq first */
    CHECK(get_u32(h + 0x5C) == 42u);                        /* seq last */
    CHECK(get_u32(h + 0x60) == 1u);                         /* arm refused */
    for (i = 0x64u; i < 0x7Cu; i++) CHECK(h[i] == 0u);      /* reserved */
    CHECK(get_u32(h + 0x7C) == gbp_crc32(h, 0x7Cu));        /* the CRC, recomputed here */
    /* big-endian, byte by byte: the version's bytes */
    CHECK(h[0x08] == 0u && h[0x09] == 0u && h[0x0A] == 0u && h[0x0B] == 1u);
    CHECK(h[0x0C] == 0u && h[0x0D] == 0u && h[0x0E] == 0x10u && h[0x0F] == 0u);
}

static void test_the_footer_seals_the_running_crc(void)
{
    uint8_t f[GBP_AWR_FOOTER_SIZE + 1u];
    uint8_t data[16];
    uint32_t st;
    size_t i;
    for (i = 0; i < sizeof data; i++) data[i] = (uint8_t)(i * 7u + 3u);
    st = gbp_crc32_update(gbp_crc32_init(), data, sizeof data);
    memset(f, 0xEE, sizeof f);
    CHECK(gbp_awr_footer(st, f, GBP_AWR_FOOTER_SIZE - 1u) == 0u);
    CHECK(f[0] == 0xEEu);
    CHECK(gbp_awr_footer(st, 0, sizeof f) == 0u);
    CHECK(gbp_awr_footer(st, f, sizeof f) == GBP_AWR_FOOTER_SIZE);
    CHECK(f[GBP_AWR_FOOTER_SIZE] == 0xEEu);
    CHECK(memcmp(f, "OGBPAWRE", 8) == 0);
    CHECK(get_u32(f + 8) == gbp_crc32(data, sizeof data));
}

/* a sink into a flat buffer, refusing after `limit` bytes */
struct sinkbuf { uint8_t *buf; size_t cap, len, limit; unsigned calls; };
static int sink_cb(void *ctx, const uint8_t *d, uint32_t n)
{
    struct sinkbuf *s = (struct sinkbuf *)ctx;
    s->calls++;
    if (s->len + n > s->limit || s->len + n > s->cap) return -1;
    memcpy(s->buf + s->len, d, n);
    s->len += n;
    return 0;
}

static void test_stream_writes_the_whole_file_once(void)
{
    struct gbp_awr w;
    static uint8_t out[GBP_AWR_HEADER_SIZE + CAP * GBP_AWR_BLOCK_SIZE + GBP_AWR_FOOTER_SIZE + 64u];
    struct sinkbuf s;
    uint64_t written = 99u;
    uint8_t h[GBP_AWR_HEADER_SIZE];
    long rc;
    size_t body;
    reset(&w);
    CHECK(gbp_awr_arm(&w, 1u) == 0);
    fill_block(0x10u); gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 2u, 1u);
    fill_block(0x20u); gbp_awr_block(&w, block, GBP_AWR_BLOCK_SIZE, 3u, 2u);
    gbp_awr_finish(&w);                                     /* 2 of 3: DONE, incomplete */

    memset(&s, 0, sizeof s);
    s.buf = out; s.cap = sizeof out; s.limit = sizeof out;
    rc = gbp_awr_stream(&w, sink_cb, &s, &written);
    body = GBP_AWR_HEADER_SIZE + 2u * GBP_AWR_BLOCK_SIZE;
    CHECK(rc == (long)(body + GBP_AWR_FOOTER_SIZE));
    CHECK(written == (uint64_t)rc && s.len == (size_t)rc);
    CHECK(gbp_awr_total(&w) == (uint64_t)rc);
    CHECK(s.calls == 4u);                                   /* header, 2 blocks, footer: moved once */
    CHECK(gbp_awr_header(&w, h, sizeof h) == GBP_AWR_HEADER_SIZE);
    CHECK(memcmp(out, h, GBP_AWR_HEADER_SIZE) == 0);
    CHECK(get_u32(out + 0x10) == 2u && get_u32(out + 0x1C) == (uint32_t)GBP_AWR_DONE);
    CHECK(out[GBP_AWR_HEADER_SIZE] == 0x10u && out[GBP_AWR_HEADER_SIZE + GBP_AWR_BLOCK_SIZE - 1u] == 0x10u);
    CHECK(out[GBP_AWR_HEADER_SIZE + GBP_AWR_BLOCK_SIZE] == 0x20u);
    CHECK(memcmp(out + body, "OGBPAWRE", 8) == 0);
    CHECK(get_u32(out + body + 8u) == gbp_crc32(out, body));

    /* the sink refusing mid-way: -2, and `written` says how far it got */
    memset(&s, 0, sizeof s);
    s.buf = out; s.cap = sizeof out; s.limit = GBP_AWR_HEADER_SIZE + GBP_AWR_BLOCK_SIZE;
    rc = gbp_awr_stream(&w, sink_cb, &s, &written);
    CHECK(rc == -2 && written == GBP_AWR_HEADER_SIZE + GBP_AWR_BLOCK_SIZE);

    /* zero blocks: header and footer only */
    reset(&w);
    memset(&s, 0, sizeof s);
    s.buf = out; s.cap = sizeof out; s.limit = sizeof out;
    rc = gbp_awr_stream(&w, sink_cb, &s, &written);
    CHECK(rc == (long)(GBP_AWR_HEADER_SIZE + GBP_AWR_FOOTER_SIZE) && s.calls == 2u);
    CHECK(get_u32(out + GBP_AWR_HEADER_SIZE + 8u) == gbp_crc32(out, GBP_AWR_HEADER_SIZE));

    CHECK(gbp_awr_stream(0, sink_cb, &s, &written) == -1 && written == 0u);
    CHECK(gbp_awr_stream(&w, 0, &s, &written) == -1);
    CHECK(gbp_awr_stream(&w, sink_cb, &s, 0) > 0);          /* `written` is optional */
}

static void test_null_is_survivable_everywhere(void)
{
    uint8_t h[GBP_AWR_HEADER_SIZE];
    CHECK(gbp_awr_init(0, store, CAP, 1u) != 0);
    CHECK(strcmp(gbp_awr_fault(0), "null") == 0);
    CHECK(gbp_awr_arm(0, 1u) == -1);
    CHECK(gbp_awr_block(0, block, GBP_AWR_BLOCK_SIZE, 1u, 1u) == 0);
    gbp_awr_note_cost(0, 1u);
    gbp_awr_finish(0);
    CHECK(gbp_awr_done(0) == 0);
    CHECK(gbp_awr_copy_mean(0) == 0u);
    CHECK(gbp_awr_block_bytes(0, 0u) == 0);
    CHECK(gbp_awr_header(0, h, sizeof h) == 0u);
    CHECK(gbp_awr_total(0) == 0u);
}

int main(void)
{
    test_init_refuses_what_it_cannot_use();
    test_arm_fill_done_and_the_fourth_block();
    test_a_wrong_length_is_a_fault_and_not_a_hole();
    test_finish_closes_a_fill_without_pretending();
    test_the_cost_is_reported_and_never_invented();
    test_the_header_bytes();
    test_the_footer_seals_the_running_crc();
    test_stream_writes_the_whole_file_once();
    test_null_is_survivable_everywhere();
    printf("test_gbp_awr: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
