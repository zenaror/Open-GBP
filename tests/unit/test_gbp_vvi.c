/* test_gbp_vvi.c — the VI hand-over / latch trace and the OGBPVI1 writer /
 * parser (HARDWARE_TESTS §V6.8, Issue #7). Every scenario SYNTHETIC; nothing
 * here says anything about a screen. */
#include <stdio.h>
#include <string.h>
#include "gbp_vvi.h"
#include "gbp_vvidump.h"

static int checks, failures;
#define CHECK(c) do { checks++; if (!(c)) { failures++; printf("   FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

static struct gbp_vvi_rec recs[16];
static uint8_t chunk[GBP_VVIDUMP_CHUNK];
static uint8_t file[GBP_VVIDUMP_HEADER_SIZE + 16u * GBP_VVIDUMP_RECORD_SIZE + GBP_VVIDUMP_FOOTER_SIZE];
static size_t file_n;

static int sink(void *ctx, const uint8_t *d, uint32_t n)
{
    (void)ctx;
    if (file_n + n > sizeof file) return 1;
    memcpy(file + file_n, d, n);
    file_n += n;
    return 0;
}

static void test_handoff_latch_supersede(void)
{
    struct gbp_vvi v;
    printf("-- hand-over -> observed current binds one record; a second hand-over first supersedes\n");
    gbp_vvi_init(&v, recs, 16u);
    CHECK(gbp_vvi_awaiting(&v) == -1);
    CHECK(gbp_vvi_latch(&v, 1u, 1u, 0, 0, 0, 0) == 0);          /* nothing awaited */
    CHECK(gbp_vvi_handed(&v, 356u, 7u, 1, 0x00A60000u, 1000u, 50u) == 0);
    CHECK(gbp_vvi_awaiting(&v) == 1);
    CHECK(gbp_vvi_latch(&v, 1100u, 51u, 0x0000u, 0x5300u, 0x0000u, 0x5E80u) == 1);
    CHECK(gbp_vvi_awaiting(&v) == -1);
    CHECK(recs[0].flags == GBP_VVI_F_LATCHED && recs[0].t_latch == 1100u && recs[0].retrace_latch == 51u);
    CHECK(recs[0].vi15 == 0x5300u && recs[0].vi19 == 0x5E80u && recs[0].phys == 0x00A60000u);
    CHECK(gbp_vvi_handed(&v, 357u, 8u, 0, 0x00B00000u, 2000u, 52u) == 1);
    CHECK(gbp_vvi_handed(&v, 358u, 9u, 1, 0x00A60000u, 3000u, 53u) == 2);   /* before 357 was observed */
    CHECK(recs[1].flags == GBP_VVI_F_SUPERSEDED && recs[1].t_latch == 0u);
    CHECK(gbp_vvi_awaiting(&v) == 1);
    CHECK(gbp_vvi_latch(&v, 3100u, 54u, 0, 0, 0, 0) == 1);
    CHECK(v.handed == 3u && v.latched == 2u && v.superseded == 1u && v.observe_calls == 3u && v.n == 3u);
}

static void test_overflow_is_counted_never_overwritten(void)
{
    struct gbp_vvi v;
    uint32_t i;
    printf("-- capacity: hand-overs beyond it are counted, records are never overwritten\n");
    gbp_vvi_init(&v, recs, 4u);
    for (i = 0; i < 6u; i++) (void)gbp_vvi_handed(&v, i, i, (int16_t)(i & 1u), 0u, i, i);
    CHECK(v.n == 4u && v.overflow == 2u && v.handed == 6u);
    CHECK(recs[3].frame_index == 3u);
}

static void test_serializer_round_trip_and_strictness(void)
{
    struct gbp_vvi v;
    struct gbp_vvidump_info info, back;
    const uint8_t *r = 0;
    long n;
    uint64_t written = 0;
    size_t i;
    printf("-- OGBPVI1: written, parsed strictly, every byte flip refused\n");
    gbp_vvi_init(&v, recs, 16u);
    (void)gbp_vvi_handed(&v, 356u, 7u, 1, 0x00A60000u, 1000u, 50u);
    (void)gbp_vvi_latch(&v, 1100u, 51u, 0x0000u, 0x5300u, 0x0000u, 0x5E80u);
    (void)gbp_vvi_handed(&v, 357u, 8u, 0, 0x00B00000u, 2000u, 52u);
    memset(&info, 0, sizeof info);
    info.tb_hz = 40500000u;
    info.xfb_slots = 2u;
    CHECK(gbp_vvidump_set_identity(&info, "GBP-VIDEO-004", "stream-0013", "gbp-video-stream-probe", "abc1234") == 0);
    file_n = 0;
    n = gbp_vvidump_stream(&info, &v, chunk, sizeof chunk, sink, 0, &written);
    CHECK(n == (long)(GBP_VVIDUMP_HEADER_SIZE + 2u * GBP_VVIDUMP_RECORD_SIZE + GBP_VVIDUMP_FOOTER_SIZE));
    CHECK(gbp_vvidump_parse(file, file_n, &back, &r) == 0);
    CHECK(back.records_n == 2u && back.handed == 2u && back.latched == 1u && back.awaiting_at_end == 1);
    CHECK(strcmp(back.build_id, "stream-0013") == 0 && back.xfb_slots == 2u);
    for (i = 0; i < file_n; i++) {
        file[i] ^= 0x01u;
        CHECK(gbp_vvidump_parse(file, file_n, &back, &r) != 0);
        file[i] ^= 0x01u;
    }
    CHECK(gbp_vvidump_parse(file, file_n, &back, &r) == 0);
    CHECK(gbp_vvidump_parse(file, file_n - 1u, &back, &r) == -4);
}

int main(void)
{
    printf("== test_gbp_vvi (GBP-VIDEO-007 hand-over / latch trace + OGBPVI1; every scenario SYNTHETIC)\n");
    test_handoff_latch_supersede();
    test_overflow_is_counted_never_overwritten();
    test_serializer_round_trip_and_strictness();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
