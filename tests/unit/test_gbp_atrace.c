/*
 * test_gbp_atrace.c — Run A's read-only timing records (GitHub Issue #101, §V23), with no hardware.
 *
 * Pinned: every AUDIO sample and its completion delta are kept in order, and a delta that does not
 * fit goes to the side ring with its full tick; VIDEO records flag frame starts and every vblank
 * saturates; a callback keeps its entry and its ISR duration; a flush_queue step is always kept and
 * a produce or process only above the floor, while EVERY call lands in the histogram and the write
 * of one not kept is a cost; the recorder's other writes accumulate per AI callback cycle, cycle 0
 * being before the first callback; full buffers are counted, never overrun; and the emitted file has
 * the documented layout, is identical whatever the staging size, and ends in the CRC-32 of everything
 * before it.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "gbp_atrace.h"
#include "gbp_crc32.h"

static int failures, checks;
#define CHECK(c) do { checks++; if (!(c)) { failures++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

static int16_t a_dec[GBP_ATRACE_A_MAX];
static uint16_t a_del[GBP_ATRACE_A_MAX];
static struct gbp_atrace_sat a_sat[GBP_ATRACE_A_SAT_MAX];
static uint16_t v_rec[GBP_ATRACE_V_MAX];
static struct gbp_atrace_sat v_sat[GBP_ATRACE_V_SAT_MAX];
static struct gbp_atrace_cb cbs[GBP_ATRACE_CB_MAX];
static struct gbp_atrace_step steps[GBP_ATRACE_STEP_MAX];
static uint32_t cycles[GBP_ATRACE_CYCLES_MAX];

static void storage(struct gbp_atrace_storage *s)
{
    memset(cycles, 0, sizeof cycles);
    s->a_decoded = a_dec; s->a_delta = a_del; s->a_sat = a_sat; s->v_rec = v_rec; s->v_sat = v_sat;
    s->cb = cbs; s->step = steps; s->cycles = cycles;
}

static uint32_t rd32(const uint8_t *b) { return ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16) | ((uint32_t)b[2] << 8) | b[3]; }
static uint16_t rd16(const uint8_t *b) { return (uint16_t)(((uint32_t)b[0] << 8) | b[1]); }
static uint64_t rd64(const uint8_t *b) { return ((uint64_t)rd32(b) << 32) | rd32(b + 4); }

static uint8_t out[4u << 20];
static uint32_t out_n;
static int put_mem(void *ctx, const uint8_t *bytes, uint32_t n)
{
    (void)ctx;
    if (out_n + n > sizeof out) return -1;
    memcpy(out + out_n, bytes, n);
    out_n += n;
    return 0;
}
static int put_fail(void *ctx, const uint8_t *bytes, uint32_t n) { (void)ctx; (void)bytes; (void)n; return -1; }

static void test_audio(void)
{
    struct gbp_atrace tr;
    struct gbp_atrace_storage s;
    printf("-- AUDIO: samples, deltas, and a gap too long for a u16\n");
    storage(&s);
    gbp_atrace_init(&tr, &s, 40500000u);
    gbp_atrace_audio(&tr, 100, 1000000u);
    gbp_atrace_audio(&tr, -200, 1009888u);
    gbp_atrace_audio(&tr, 300, 1009888u + 70000u);      /* 70 000 ticks: does not fit */
    gbp_atrace_audio(&tr, 400, 1009888u + 70000u + 9888u);
    CHECK(tr.a_n == 4u && tr.a_first == 1000000u);
    CHECK(a_dec[1] == -200 && a_del[0] == 0u && a_del[1] == 9888u);
    CHECK(a_del[2] == GBP_ATRACE_A_SAT && tr.a_sat_n == 1u && a_sat[0].index == 2u && a_sat[0].t == 1079888u);
    CHECK(a_del[3] == 9888u);
}

static void test_video(void)
{
    struct gbp_atrace tr;
    struct gbp_atrace_storage s;
    printf("-- VIDEO: frame starts flagged, every vblank saturates into the side ring\n");
    storage(&s);
    gbp_atrace_init(&tr, &s, 40500000u);
    gbp_atrace_video(&tr, 1, 5000000u);
    gbp_atrace_video(&tr, 0, 5000000u + 11890u);
    gbp_atrace_video(&tr, 1, 5000000u + 11890u + 216000u);   /* the vblank before a frame start */
    CHECK(tr.v_n == 3u && tr.v_first == 5000000u);
    CHECK(v_rec[0] == GBP_ATRACE_V_START);
    CHECK(v_rec[1] == 11890u);
    CHECK(v_rec[2] == (GBP_ATRACE_V_START | GBP_ATRACE_V_SAT));
    CHECK(tr.v_sat_n == 1u && v_sat[0].index == 2u && v_sat[0].t == 5227890u);
}

static void test_callbacks_steps_and_cost(void)
{
    struct gbp_atrace tr;
    struct gbp_atrace_storage s;
    struct gbp_atrace_step *st;
    struct gbp_atrace_cb *c;
    printf("-- callbacks, steps above the floor, every call in the histogram, the cost per cycle\n");
    storage(&s);
    gbp_atrace_init(&tr, &s, 40500000u);
    gbp_atrace_cost(&tr, 40u);                              /* before the first callback: cycle 0 */
    c = gbp_atrace_callback(&tr, 2000000u, 2000800u);
    CHECK(c && c->entry == 2000000u && c->dur == 800u && tr.cb_n == 1u);
    gbp_atrace_cost(&tr, 30u);
    gbp_atrace_cost(&tr, 50u);
    CHECK(cycles[0] == 40u && cycles[1] == 80u && tr.cycles_n == 2u && tr.cost_max == 50u);

    st = gbp_atrace_step(&tr, GBP_ATRACE_PRODUCE, 3000000u, 3000000u + 100u);   /* under the floor */
    CHECK(st == 0 && tr.step_n == 0u && tr.calls[GBP_ATRACE_PRODUCE] == 1u);
    st = gbp_atrace_step(&tr, GBP_ATRACE_PRODUCE, 3001000u, 3001000u + 4000u);
    CHECK(st && tr.step_n == 1u && tr.step_base == 3001000u && st->start_rel == 0u && st->dur == 4000u);
    gbp_atrace_step_rec(&tr, st, 3005000u, 3005040u);
    CHECK(st->rec == 40u);
    st = gbp_atrace_step(&tr, GBP_ATRACE_FLUSH_QUEUE, 3006000u, 3006000u + 50u);   /* always kept */
    CHECK(st && st->kind == GBP_ATRACE_FLUSH_QUEUE && st->start_rel == 5000u);
    st = gbp_atrace_step(&tr, GBP_ATRACE_PROCESS, 3007000u, 3007000u + 20u);
    CHECK(st == 0 && tr.calls[GBP_ATRACE_PROCESS] == 1u);
    gbp_atrace_step_rec(&tr, st, 3007020u, 3007020u + 25u);     /* not kept: its write is a cost */
    CHECK(cycles[1] == 105u && tr.cost_max == 50u);
    CHECK(tr.hist[GBP_ATRACE_PRODUCE][6] == 1u);      /* 100 ticks: log2 bin 6 */
    CHECK(tr.hist[GBP_ATRACE_PRODUCE][11] == 1u);     /* 4000 ticks: bin 11 */
}

static void test_full_buffers_are_counted(void)
{
    struct gbp_atrace tr;
    struct gbp_atrace_storage s;
    uint32_t i;
    printf("-- a full buffer is counted, never overrun\n");
    storage(&s);
    gbp_atrace_init(&tr, &s, 40500000u);
    for (i = 0; i < GBP_ATRACE_CB_MAX + 3u; i++) (void)gbp_atrace_callback(&tr, i * 1000u, i * 1000u + 10u);
    CHECK(tr.cb_n == GBP_ATRACE_CB_MAX && tr.cb_dropped == 3u);
    for (i = 0; i < GBP_ATRACE_A_MAX + 5u; i++) gbp_atrace_audio(&tr, 1, (uint64_t)i * 9888u);
    CHECK(tr.a_n == GBP_ATRACE_A_MAX && tr.a_dropped == 5u);
}

static void test_the_file(void)
{
    struct gbp_atrace tr;
    struct gbp_atrace_storage s;
    static uint8_t stage[4096], first[1u << 16];
    uint32_t n, n2, i, o;
    printf("-- the emitted file: the layout, the CRC, and the same bytes whatever the staging size\n");
    storage(&s);
    gbp_atrace_init(&tr, &s, 40500000u);
    for (i = 0; i < 100u; i++) gbp_atrace_audio(&tr, (int16_t)(i * 7), 1000000u + (uint64_t)i * 9888u);
    for (i = 0; i < 50u; i++) gbp_atrace_video(&tr, i % 40u == 0u, 900000u + (uint64_t)i * 11890u);
    (void)gbp_atrace_callback(&tr, 1500000u, 1500900u);
    gbp_atrace_step_rec(&tr, gbp_atrace_step(&tr, GBP_ATRACE_PRODUCE, 1510000u, 1514000u), 1514000u, 1514033u);
    gbp_atrace_cost(&tr, 12u);
    out_n = 0u;
    n = gbp_atrace_emit(&tr, put_mem, 0, stage, sizeof stage);
    CHECK(n == out_n && n > 0u);
    CHECK(memcmp(out, "OGBPTRC1", 8) == 0 && rd32(out + 8) == 1u && rd32(out + 12) == 40500000u);
    CHECK(rd32(out + 0x10) == 100u && rd32(out + 0x18) == 50u && rd32(out + 0x20) == 1u && rd32(out + 0x24) == 1u);
    CHECK(rd64(out + 0x44) == 1000000u && rd64(out + 0x4C) == 900000u && rd64(out + 0x54) == 1510000u);
    CHECK(rd32(out + 0x5C) == GBP_ATRACE_STEP_FLOOR);
    o = 0x64u + 4u * 4u + 4u * 4u * GBP_ATRACE_HIST_BINS;
    CHECK((int16_t)rd16(out + o + 2u * 3u) == 21);                     /* a_decoded[3] */
    CHECK(rd16(out + o + 2u * 100u + 2u * 1u) == 9888u);               /* a_delta[1] */
    CHECK(rd32(out + n - 4u) == gbp_crc32(out, n - 4u));
    memcpy(first, out, n < sizeof first ? n : sizeof first);
    out_n = 0u;
    n2 = gbp_atrace_emit(&tr, put_mem, 0, stage, 7u);                  /* a tiny stage: the same file */
    CHECK(n2 == n && memcmp(first, out, n) == 0);
    CHECK(gbp_atrace_emit(&tr, put_fail, 0, stage, sizeof stage) == 0u);
}

int main(void)
{
    test_audio();
    test_video();
    test_callbacks_steps_and_cost();
    test_full_buffers_are_counted();
    test_the_file();
    printf("test_gbp_atrace: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
