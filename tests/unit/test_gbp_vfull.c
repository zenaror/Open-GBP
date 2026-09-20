/* test_gbp_vfull.c — the full-frame sample store and the OGBPFULL1 writer /
 * parser (HARDWARE_TESTS §V6.8, Issue #7). Every scenario SYNTHETIC. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gbp_vfull.h"
#include "gbp_vfulldump.h"

static int checks, failures;
#define CHECK(c) do { checks++; if (!(c)) { failures++; printf("   FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

static uint8_t  raw_store[GBP_VFULL_RAW_STORE];
static uint16_t tex_store[GBP_VFULL_TEX_STORE];
static uint8_t  blk[GBP_VFULL_BLOCK_RAW];
static uint16_t row[GBP_VFULL_BLOCK_TEX];
static uint8_t  chunk[GBP_VFULLDUMP_CHUNK];
static uint8_t  file[GBP_VFULLDUMP_HEADER_SIZE + 8u * GBP_VFULLDUMP_RECORD_SIZE + GBP_VFULLDUMP_FOOTER_SIZE];
static size_t   file_n;

static int sink(void *ctx, const uint8_t *d, uint32_t n)
{
    (void)ctx;
    if (file_n + n > sizeof file) return 1;
    memcpy(file + file_n, d, n);
    file_n += n;
    return 0;
}

static void fill_block(uint32_t fi, uint32_t b)
{
    uint32_t i;
    for (i = 0; i < GBP_VFULL_BLOCK_RAW; i++) blk[i] = (uint8_t)(fi * 7u + b * 13u + i);
    for (i = 0; i < GBP_VFULL_BLOCK_TEX; i++) row[i] = (uint16_t)(0x8000u | ((fi + b + i) & 0x7FFFu));
}

static void copy_frame(struct gbp_vfull *f, int i, uint32_t fi)
{
    uint32_t b;
    for (b = 0; b < GBP_VFULL_BLOCKS; b++) { fill_block(fi, b); CHECK(gbp_vfull_block(f, i, b, blk, row) == 0); }
}

static void test_content_blind_grid(void)
{
    struct gbp_vfull f;
    uint32_t fi;
    int got = 0;
    printf("-- the grid: origin + 256*i, i < 8, decided from frame_index alone\n");
    gbp_vfull_init(&f, raw_store, tex_store, 0u);
    CHECK(f.spacing == 256u);
    CHECK(gbp_vfull_want(&f, 356u) == -1);                 /* no origin yet */
    gbp_vfull_set_origin(&f, 356u);
    gbp_vfull_set_origin(&f, 9999u);                        /* ignored: set once */
    CHECK(f.origin == 356u && f.origin_set == 1u);
    for (fi = 0; fi < 356u + 256u * 12u; fi++) {
        int w = gbp_vfull_want(&f, fi);
        if (w >= 0) {
            CHECK((fi - 356u) % 256u == 0u && (uint32_t)w == (fi - 356u) / 256u);
            CHECK(gbp_vfull_open(&f, w, fi, fi + 1000u, (uint16_t)(fi & 3u), (uint16_t)(fi & 1u), fi + 5u, 100u + fi) == 0);
            got++;
        }
    }
    CHECK(got == 8);
    CHECK(f.skipped_capacity == 4u);                        /* i = 8..11 fell beyond K */
    CHECK(gbp_vfull_want(&f, 356u) == -1);                  /* never overwritten */
    CHECK(f.wanted == 8u && f.opened == 8u);
}

static void test_complete_incomplete_refused(void)
{
    struct gbp_vfull f;
    printf("-- COMPLETE needs 40 blocks; INCOMPLETE and REFUSED are never a frame\n");
    gbp_vfull_init(&f, raw_store, tex_store, 256u);
    gbp_vfull_set_origin(&f, 0u);
    CHECK(gbp_vfull_want(&f, 0u) == 0);
    CHECK(gbp_vfull_open(&f, 0, 0u, 1u, 2u, 1u, 3u, 4u) == 0);
    copy_frame(&f, 0, 0u);
    fill_block(0u, 3u);
    CHECK(gbp_vfull_block(&f, 0, 3u, blk, row) == -1);     /* a block is copied once */
    CHECK(gbp_vfull_convert_done(&f, 0, 77u) == 1);
    CHECK(f.s[0].state == GBP_VFULL_COMPLETE && f.s[0].t_convert_done == 77u && f.s[0].present == 0xFFFFFFFFFFull);
    CHECK(memcmp(gbp_vfull_raw(&f, 0) + 3u * GBP_VFULL_BLOCK_RAW, blk, GBP_VFULL_BLOCK_RAW) == 0);
    CHECK(gbp_vfull_tex(&f, 0)[3u * GBP_VFULL_BLOCK_TEX + 5u] == row[5]);
    CHECK(gbp_vfull_want(&f, 256u) == 1);
    CHECK(gbp_vfull_open(&f, 1, 256u, 2u, 0u, 0u, 9u, 5u) == 0);
    fill_block(256u, 0u);
    CHECK(gbp_vfull_block(&f, 1, 0u, blk, row) == 0);
    CHECK(gbp_vfull_convert_done(&f, 1, 88u) == 0);        /* 39 blocks missing */
    CHECK(f.s[1].state == GBP_VFULL_REFUSED && f.s[1].reason == GBP_VFULL_R_INCOMPLETE);
    CHECK(gbp_vfull_want(&f, 512u) == 2);
    CHECK(gbp_vfull_open(&f, 2, 512u, 3u, 1u, 1u, 10u, 6u) == 0);
    copy_frame(&f, 2, 512u);
    CHECK(gbp_vfull_refuse(&f, 2, GBP_VFULL_R_GENERATION) == 0);   /* the guard spoke after the copy */
    CHECK(f.s[2].state == GBP_VFULL_REFUSED && f.s[2].reason == GBP_VFULL_R_GENERATION);
    CHECK(gbp_vfull_block(&f, 2, 0u, blk, row) == -1);     /* nothing is added to a refused sample */
    CHECK(gbp_vfull_decision(&f, 0, 99u, 1234u, 1, 1u) == 0);
    CHECK(f.s[0].xfb_target == 1 && f.s[0].retrace_decision == 1234u && f.s[0].disposition == 1u);
    CHECK(gbp_vfull_decision(&f, 5, 1u, 1u, 0, 1u) == -1); /* EMPTY */
    CHECK(f.completed == 1u && f.refused == 2u && gbp_vfull_records(&f) == 3u);
}

static void test_serializer_round_trip_and_strictness(void)
{
    struct gbp_vfull f;
    struct gbp_vfulldump_info info, back;
    const uint8_t *recs = 0;
    long n;
    uint64_t written = 0;
    size_t i;
    printf("-- OGBPFULL1: written from the store, parsed strictly, every byte flip refused\n");
    gbp_vfull_init(&f, raw_store, tex_store, 256u);
    gbp_vfull_set_origin(&f, 356u);
    CHECK(gbp_vfull_want(&f, 356u) == 0);
    CHECK(gbp_vfull_open(&f, 0, 356u, 1u, 2u, 1u, 3u, 4u) == 0);
    copy_frame(&f, 0, 356u);
    CHECK(gbp_vfull_convert_done(&f, 0, 77u) == 1);
    CHECK(gbp_vfull_decision(&f, 0, 99u, 1234u, 0, 1u) == 0);
    CHECK(gbp_vfull_want(&f, 612u) == 1);
    CHECK(gbp_vfull_open(&f, 1, 612u, 5u, 3u, 0u, 8u, 9u) == 0);
    fill_block(612u, 0u);
    CHECK(gbp_vfull_block(&f, 1, 0u, blk, row) == 0);
    CHECK(gbp_vfull_convert_done(&f, 1, 10u) == 0);
    memset(&info, 0, sizeof info);
    info.tb_hz = 40500000u;
    CHECK(gbp_vfulldump_set_identity(&info, "GBP-VIDEO-004", "stream-0013", "gbp-video-stream-probe", "abc1234") == 0);
    file_n = 0;
    n = gbp_vfulldump_stream(&info, &f, chunk, sizeof chunk, sink, 0, &written);
    CHECK(n > 0 && (uint64_t)n == written);
    CHECK((uint64_t)n == GBP_VFULLDUMP_HEADER_SIZE + 2u * GBP_VFULLDUMP_RECORD_SIZE + GBP_VFULLDUMP_FOOTER_SIZE);
    CHECK(gbp_vfulldump_parse(file, file_n, &back, &recs) == 0);
    CHECK(back.records_n == 2u && back.k_cap == 8u && back.spacing == 256u && back.origin == 356u);
    CHECK(back.completed == 1u && back.refused == 1u && back.tb_hz == 40500000u);
    CHECK((back.flags & GBP_VFULLDUMP_FLAG_ORIGIN_SET) != 0u && (back.flags & GBP_VFULLDUMP_FLAG_CAPACITY_SKIPPED) == 0u);
    CHECK(strcmp(back.build_id, "stream-0013") == 0 && strcmp(back.test_id, "GBP-VIDEO-004") == 0);
    CHECK(gbp_vfulldump_rec_sample_index(recs) == 0u && gbp_vfulldump_rec_frame_index(recs) == 356u);
    CHECK(gbp_vfulldump_rec_seq(recs) == 1u && gbp_vfulldump_rec_state(recs) == GBP_VFULL_COMPLETE);
    CHECK(gbp_vfulldump_rec_present(recs) == 0xFFFFFFFFFFull);
    CHECK(memcmp(gbp_vfulldump_rec_raw(recs), gbp_vfull_raw(&f, 0), GBP_VFULL_RAW_BYTES) == 0);
    CHECK(gbp_vfulldump_rec_texel(recs, 3u * GBP_VFULL_BLOCK_TEX + 5u) == gbp_vfull_tex(&f, 0)[3u * GBP_VFULL_BLOCK_TEX + 5u]);
    CHECK(gbp_vfulldump_rec_state(recs + GBP_VFULLDUMP_RECORD_SIZE) == GBP_VFULL_REFUSED);
    /* strictness: a flip anywhere is refused (sampled positions, whole file is 461 KB) */
    for (i = 0; i < file_n; i += 977u) {
        int rc;
        file[i] ^= 0x01u;
        rc = gbp_vfulldump_parse(file, file_n, &back, &recs);
        CHECK(rc != 0);
        file[i] ^= 0x01u;
    }
    CHECK(gbp_vfulldump_parse(file, file_n - 1u, &back, &recs) == -4);
    CHECK(gbp_vfulldump_parse(file, file_n, &back, &recs) == 0);
    /* an identity that does not fit is an error, never truncated */
    CHECK(gbp_vfulldump_set_identity(&info, "GBP-VIDEO-004", "a-build-id-that-is-far-too-long-for-32", "x", "y") != 0);
    file_n = 0;
    CHECK(gbp_vfulldump_stream(&info, &f, chunk, sizeof chunk, sink, 0, &written) == -2);
}

int main(void)
{
    printf("== test_gbp_vfull (GBP-VIDEO-008 sample store + OGBPFULL1; every scenario SYNTHETIC)\n");
    test_content_blind_grid();
    test_complete_incomplete_refused();
    test_serializer_round_trip_and_strictness();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
