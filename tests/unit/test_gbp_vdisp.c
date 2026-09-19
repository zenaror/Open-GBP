/*
 * test_gbp_vdisp — the downstream disposition trace and its OGBPDISP1 sidecar
 * (HARDWARE_TESTS §V5.46). Every scenario is SYNTHETIC.
 *
 * WHAT IS DELIBERATELY NOT TESTED, AND WHY
 *
 * §V5.46 asked for a case where "a display opportunity finds no new source
 * frame" and one where "a frame exists but conversion has not finished at the
 * opportunity". Neither is written here, because neither EXISTS in this
 * runtime. There is no VI-driven display loop: `VIDEO_WaitVSync()` is never
 * called in the capture path, no retrace callback is installed, and a
 * presentation opportunity is one `submit_ready()` call, which happens because
 * a conversion finished. An opportunity cannot precede its own frame.
 *
 * Writing those tests would have meant inventing branches to satisfy them. What
 * the architecture does have is tested instead: a token-gate refusal (a frame
 * whose GX predecessor had not released), and an XFB-busy hold (a frame that
 * was converted, submitted and drawn and still reached no framebuffer).
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "gbp_vdisp.h"
#include "gbp_vdispdump.h"
#include "gbp_crc32.h"

static int checks, failures;
#define CHECK(c) do { checks++; if (!(c)) { failures++; \
    printf("   FAIL %s:%d  %s\n", __FILE__, __LINE__, #c); } } while (0)

static struct gbp_vdisp_life  life[64];
static struct gbp_vdisp_event ev[64];
static struct gbp_vdisp d;

static void reset(void)
{
    CHECK(gbp_vdisp_init(&d, life, 64u, ev, 64u) == 0);
}

/* The exact shape of one healthy frame: taken, converted, submitted, drawn,
 * and given a framebuffer. */
static int walk_ok(uint32_t key, uint64_t t, int tex, int in_window)
{
    static const uint8_t st[2] = { 3u, 0u };
    const int L = gbp_vdisp_take(&d, key, key, 1u, 0x29u, t, t + 10u, 100u + key,
                                 (uint16_t)tex, in_window, 0);
    gbp_vdisp_convert_first(&d, L, t + 20u);
    gbp_vdisp_convert_done(&d, L, t + 30u, 1400u);
    gbp_vdisp_submit(&d, L, t + 40u);
    gbp_vdisp_drawdone(&d, tex, t + 50u);
    gbp_vdisp_decision(&d, L, t + 60u, 101u + key, 0, -1, 1, GBP_VDISP_R_NONE, st, 1, GBP_VDISP_KEY_NONE);
    return L;
}

/* ---- A: the whole healthy path ----------------------------------------- */
static void test_A_a_frame_that_reaches_a_framebuffer(void)
{
    const struct gbp_vdisp_life *r;
    const struct gbp_vdisp_event *e;
    printf("-- A: take -> convert -> submit -> draw-done -> a framebuffer\n");
    reset();
    (void)walk_ok(7u, 1000u, 0, 1);
    r = gbp_vdisp_life_at(&d, 0u);
    CHECK(r != 0);
    if (!r) return;
    CHECK(r->frame_index == 7u);
    CHECK(r->disposition == GBP_VDISP_D_SELECTED_NEW);
    CHECK(r->reason == GBP_VDISP_R_NONE);
    CHECK((r->life_flags & GBP_VDISP_F_ALL) ==
          (GBP_VDISP_F_IN_WINDOW | GBP_VDISP_F_CONVERTED | GBP_VDISP_F_SUBMITTED |
           GBP_VDISP_F_DRAWDONE | GBP_VDISP_F_DECIDED));
    /* every stage has a time, and they are ordered */
    CHECK(r->t_close < r->t_take);
    CHECK(r->t_take < r->t_convert_first);
    CHECK(r->t_convert_first < r->t_convert_done);
    CHECK(r->t_convert_done < r->t_submit);
    CHECK(r->t_submit < r->t_drawdone);
    CHECK(r->t_drawdone < r->t_decision);
    e = gbp_vdisp_event_at(&d, 0u);
    CHECK(e != 0);
    if (e) {
        CHECK(e->frame_index == 7u);
        CHECK(e->prev_index == GBP_VDISP_KEY_NONE);   /* nothing was on screen yet */
        CHECK(e->decision == GBP_VDISP_D_SELECTED_NEW);
        CHECK(e->xfb_target == 1);
    }
    CHECK(gbp_vdisp_intact(&d));
}

/* ---- E: converted, submitted, DRAWN — and still no framebuffer --------- */
static void test_E_a_drawn_frame_that_reaches_no_framebuffer(void)
{
    static const uint8_t st[2] = { 3u, 0u };
    const struct gbp_vdisp_life *r;
    const struct gbp_vdisp_event *e;
    int L;
    printf("-- E: the HOLD branch — both framebuffers spoken for\n");
    reset();
    (void)walk_ok(1u, 1000u, 0, 1);              /* frame 1 reaches XFB 1 */
    L = gbp_vdisp_take(&d, 2u, 2u, 1u, 0x29u, 2000u, 2010u, 200u, 1u, 1, 0);
    gbp_vdisp_convert_done(&d, L, 2030u, 1400u);
    gbp_vdisp_submit(&d, L, 2040u);
    gbp_vdisp_drawdone(&d, 1, 2050u);
    /* the VI is scanning 0 and 1 was handed over but not yet latched */
    /* nothing newer was waiting: the mailbox was empty */
    gbp_vdisp_decision(&d, L, 2060u, 201u, 0, 1, -1, GBP_VDISP_R_XFB_BUSY, st, 1,
                       GBP_VDISP_KEY_NONE);
    r = gbp_vdisp_life_at(&d, 1u);
    CHECK(r != 0);
    if (r) {
        CHECK(r->disposition == GBP_VDISP_D_HOLD_PREVIOUS);
        CHECK(r->reason == GBP_VDISP_R_XFB_BUSY);
        /* IT WAS DRAWN. A hold is not a conversion or a GX failure, and the
         * record must make that impossible to misread. */
        CHECK(r->life_flags & GBP_VDISP_F_CONVERTED);
        CHECK(r->life_flags & GBP_VDISP_F_SUBMITTED);
        CHECK(r->life_flags & GBP_VDISP_F_DRAWDONE);
    }
    e = gbp_vdisp_event_at(&d, 1u);
    CHECK(e != 0);
    if (e) {
        CHECK(e->decision == GBP_VDISP_D_HOLD_PREVIOUS);
        CHECK(e->reason == GBP_VDISP_R_XFB_BUSY);
        CHECK(e->xfb_current == 0 && e->xfb_pending == 1 && e->xfb_target == -1);
        /* §V5.46.25: nothing newer was waiting, so this hold cost no frame */
        CHECK(e->newest_source == GBP_VDISP_KEY_NONE);
        /* the screen still shows frame 1, so THAT is what prev names */
        CHECK(e->prev_index == 1u);
    }
    /* and a hold never becomes "previous" */
    (void)walk_ok(3u, 3000u, 0, 1);
    e = gbp_vdisp_event_at(&d, 2u);
    if (e) CHECK(e->prev_index == 1u);
}

/* ---- D: the token gate refuses, and it is a count, not an event -------- */
static void test_D_a_token_gate_refusal_is_counted_not_evented(void)
{
    const struct gbp_vdisp_life *r;
    int L;
    printf("-- D: a refusal costs a counter, never an event (pump runs 224k times)\n");
    reset();
    L = gbp_vdisp_take(&d, 5u, 5u, 1u, 0x29u, 1000u, 1010u, 100u, 0u, 1, 0);
    gbp_vdisp_convert_done(&d, L, 1030u, 1400u);
    gbp_vdisp_submit_refused(&d, L);
    gbp_vdisp_submit_refused(&d, L);
    gbp_vdisp_submit_refused(&d, L);
    CHECK(d.ev_n == 0u);                       /* THE POINT: no events */
    r = gbp_vdisp_life_at(&d, 0u);
    CHECK(r != 0);
    if (r) {
        CHECK(r->submit_refusals == 3u);
        CHECK(!(r->life_flags & GBP_VDISP_F_SUBMITTED));
        CHECK(r->disposition == GBP_VDISP_D_OPEN);
    }
}

/* ---- F: a frame that ended the run mid-flight stays OPEN --------------- */
static void test_F_a_frame_still_in_flight_at_the_end_is_open(void)
{
    const struct gbp_vdisp_life *r;
    int L;
    printf("-- F: the terminal residual is OPEN, and is not a loss\n");
    reset();
    (void)walk_ok(1u, 1000u, 0, 1);
    L = gbp_vdisp_take(&d, 2u, 2u, 1u, 0x29u, 2000u, 2010u, 200u, 1u, 1, 0);
    gbp_vdisp_convert_done(&d, L, 2030u, 1400u);
    /* the run stops here */
    r = gbp_vdisp_life_at(&d, 1u);
    CHECK(r != 0);
    if (r) {
        CHECK(r->disposition == GBP_VDISP_D_OPEN);
        CHECK(r->t_decision == 0u);           /* never invented */
        CHECK(r->t_drawdone == 0u);
    }
    CHECK(gbp_vdisp_intact(&d));              /* an open frame is not damage */
}

/* ---- the two abandon branches ------------------------------------------ */
static void test_the_two_abandon_branches(void)
{
    const struct gbp_vdisp_life *r;
    int L;
    printf("-- the generation guard and the unreadable ring block\n");
    reset();
    L = gbp_vdisp_take(&d, 4u, 4u, 2u, 0x29u, 1000u, 1010u, 100u, 0u, 1, 0);
    gbp_vdisp_convert_done(&d, L, 1030u, 1400u);
    gbp_vdisp_abandon(&d, L, (uint16_t)GBP_VDISP_D_SLOT_OVERRUN);
    r = gbp_vdisp_life_at(&d, 0u);
    if (r) CHECK(r->disposition == GBP_VDISP_D_SLOT_OVERRUN);
    L = gbp_vdisp_take(&d, 5u, 5u, 3u, 0x29u, 2000u, 2010u, 200u, 1u, 1, 0);
    gbp_vdisp_abandon(&d, L, (uint16_t)GBP_VDISP_D_ABANDONED_NO_RAW);
    r = gbp_vdisp_life_at(&d, 1u);
    if (r) {
        CHECK(r->disposition == GBP_VDISP_D_ABANDONED_NO_RAW);
        CHECK(!(r->life_flags & GBP_VDISP_F_CONVERTED));
    }
}

/* ---- H: the self-test can never be mistaken for a source frame --------- */
static void test_H_the_selftest_is_isolated(void)
{
    const struct gbp_vdisp_life *r;
    uint32_t i;
    printf("-- H: the synthetic frame carries no source key and is flagged\n");
    reset();
    {
        static const uint8_t st[2] = { 3u, 0u };
        const int L = gbp_vdisp_take(&d, GBP_VDISP_KEY_NONE, 0u, 0u, 0u, 0u, 10u, 1u, 0u, 0, 1);
        gbp_vdisp_convert_done(&d, L, 20u, 0u);
        gbp_vdisp_submit(&d, L, 30u);
        gbp_vdisp_drawdone(&d, 0, 40u);
        gbp_vdisp_decision(&d, L, 50u, 2u, 0, -1, 1, GBP_VDISP_R_NONE, st, 1, GBP_VDISP_KEY_NONE);
    }
    (void)walk_ok(70u, 1000u, 1, 1);
    r = gbp_vdisp_life_at(&d, 0u);
    CHECK(r != 0);
    if (r) {
        CHECK(r->life_flags & GBP_VDISP_F_SELFTEST);
        CHECK(!(r->life_flags & GBP_VDISP_F_IN_WINDOW));
        CHECK(r->frame_index == GBP_VDISP_KEY_NONE);
    }
    /* and exactly one record is synthetic, whatever else the run did */
    for (i = 0; i < d.life_n; i++) {
        const struct gbp_vdisp_life *x = gbp_vdisp_life_at(&d, i);
        if (x && (x->life_flags & GBP_VDISP_F_SELFTEST))
            CHECK(x->frame_index == GBP_VDISP_KEY_NONE);
    }
}

/* ---- I: a texture is reused, and a token may not cross generations ----- */
static void test_I_texture_reuse_never_crosses_generations(void)
{
    const struct gbp_vdisp_life *a, *b;
    printf("-- I: the same texture, two frames, one draw-done each\n");
    reset();
    (void)walk_ok(1u, 1000u, 0, 1);      /* texture 0, frame 1 */
    (void)walk_ok(2u, 2000u, 0, 1);      /* texture 0 AGAIN, frame 2 */
    a = gbp_vdisp_life_at(&d, 0u);
    b = gbp_vdisp_life_at(&d, 1u);
    CHECK(a && b);
    if (a && b) {
        CHECK(a->frame_index == 1u && b->frame_index == 2u);
        CHECK(a->t_drawdone == 1050u);   /* each got its OWN token */
        CHECK(b->t_drawdone == 2050u);
    }
    CHECK(d.drawdone_unmatched == 0u);

    /* A SECOND token on a slot that was already released belongs to nobody, and
     * must be reported rather than credited to whatever is in the slot now. */
    gbp_vdisp_drawdone(&d, 0, 9999u);
    CHECK(d.drawdone_unmatched == 1u);
    if (b) CHECK(b->t_drawdone == 2050u);      /* unchanged */
    CHECK(!gbp_vdisp_intact(&d));
}

/* ---- J: full means full, never wrapped --------------------------------- */
static void test_J_overflow_fails_closed(void)
{
    static struct gbp_vdisp_life  l2[4];
    static struct gbp_vdisp_event e2[2];
    static const uint8_t st[2] = { 3u, 0u };
    struct gbp_vdisp small;
    uint32_t i;
    printf("-- J: a full trace stops recording and says so; nothing rotates\n");
    CHECK(gbp_vdisp_init(&small, l2, 4u, e2, 2u) == 0);
    for (i = 0; i < 6u; i++) {
        const int L = gbp_vdisp_take(&small, i, i, 0u, 0u, i * 10u, i * 10u + 1u, i, 0u, 1, 0);
        if (i < 4u) CHECK(L == (int)i); else CHECK(L == -1);
        gbp_vdisp_decision(&small, L, i * 10u + 5u, i, 0, -1, 1, GBP_VDISP_R_NONE, st, 0, GBP_VDISP_KEY_NONE);
    }
    CHECK(small.life_n == 4u);
    CHECK(small.life_overflow == 2u);
    CHECK(small.ev_n == 2u);
    CHECK(small.ev_overflow == 4u);
    CHECK(small.decisions == 6u);            /* counted even when not stored */
    CHECK(!gbp_vdisp_intact(&small));
    /* the FIRST records survive: nothing was overwritten by later ones */
    CHECK(l2[0].frame_index == 0u);
    CHECK(l2[3].frame_index == 3u);
    CHECK(e2[0].frame_index == 0u);
    CHECK(e2[1].frame_index == 1u);
}

static void test_bad_arguments_store_nothing(void)
{
    static const uint8_t st[2] = { 0u, 0u };
    printf("-- every entry point refuses a bad argument instead of writing somewhere\n");
    CHECK(gbp_vdisp_init(0, life, 64u, ev, 64u) == -1);
    CHECK(gbp_vdisp_init(&d, 0, 64u, ev, 64u) == -1);
    CHECK(gbp_vdisp_init(&d, life, 0u, ev, 64u) == -1);
    CHECK(gbp_vdisp_init(&d, life, 64u, 0, 64u) == -1);
    reset();
    CHECK(gbp_vdisp_take(0, 1u, 1u, 0u, 0u, 0u, 0u, 0u, 0u, 0, 0) == -1);
    gbp_vdisp_convert_first(&d, -1, 1u);
    gbp_vdisp_convert_done(&d, 99, 1u, 1u);
    gbp_vdisp_abandon(&d, -1, 1u);
    gbp_vdisp_submit_refused(&d, -1);
    gbp_vdisp_submit(&d, 99, 1u);
    gbp_vdisp_drawdone(&d, -1, 1u);
    CHECK(d.drawdone_unmatched == 1u);
    gbp_vdisp_drawdone(&d, 99, 1u);
    CHECK(d.drawdone_unmatched == 2u);
    gbp_vdisp_decision(&d, -1, 1u, 1u, 0, -1, 1, GBP_VDISP_R_NONE, st, 0, GBP_VDISP_KEY_NONE);
    CHECK(d.ev_n == 1u);                      /* the decision happened; the frame did not */
    CHECK(gbp_vdisp_event_at(&d, 0u)->frame_index == GBP_VDISP_KEY_NONE);
    CHECK(gbp_vdisp_life_at(&d, 0u) == 0);
    CHECK(gbp_vdisp_event_at(&d, 9u) == 0);
    CHECK(gbp_vdisp_intact(0) == 0);
}

/* ---- the sidecar -------------------------------------------------------- */
static uint8_t filebuf[1 << 20];
static uint32_t filelen;

static int sink_mem(void *ctx, const uint8_t *data, uint32_t len)
{
    (void)ctx;
    if (filelen + len > sizeof filebuf) return -1;
    memcpy(filebuf + filelen, data, len);
    filelen += len;
    return 0;
}

static long write_sidecar(void)
{
    struct gbp_vdispdump_info info;
    uint8_t chunk[GBP_VDISPDUMP_HEADER_SIZE];
    uint64_t w = 0;
    memset(&info, 0, sizeof info);
    info.tb_hz = 40500000u;
    info.xfb_slots = 2u;
    filelen = 0;
    if (gbp_vdispdump_set_identity(&info, "GBP-VIDEO-004", "stream-0007",
                                   "gbp-video-stream-probe", "abcdef0") != 0) return -100;
    return gbp_vdispdump_stream(&info, &d, chunk, sizeof chunk, sink_mem, 0, &w);
}

static void test_the_sidecar_round_trips_exactly(void)
{
    struct gbp_vdispdump_info info;
    const uint8_t *lf = 0, *evs = 0;
    long n;
    uint32_t i;
    printf("-- OGBPDISP1: what the writer wrote is what the parser reads back\n");
    reset();
    (void)walk_ok(70u, 1000u, 0, 1);
    (void)walk_ok(71u, 2000u, 1, 1);
    n = write_sidecar();
    CHECK(n > 0);
    CHECK((uint32_t)n == filelen);
    CHECK(gbp_vdispdump_parse(filebuf, filelen, &info, &lf, &evs) == 0);
    CHECK(info.version == GBP_VDISPDUMP_VERSION);
    CHECK(info.life_n == 2u && info.event_n == 2u);
    CHECK(info.life_record_size == 96u && info.event_record_size == 40u);
    CHECK(info.decisions == 2u);
    CHECK(info.flags & GBP_VDISPDUMP_F_INTACT);
    CHECK(info.flags & GBP_VDISPDUMP_F_WINDOW_OPENED);
    CHECK(info.window_first_frame == 70u);
    CHECK(info.tb_hz == 40500000u);
    CHECK(strcmp(info.build_id, "stream-0007") == 0);
    CHECK(strcmp(info.test_id, "GBP-VIDEO-004") == 0);
    CHECK(info.total_size == filelen);
    /* the first life record, field by field, big-endian */
    CHECK(lf != 0);
    if (lf) {
        CHECK(((uint32_t)lf[0] << 24 | (uint32_t)lf[1] << 16 |
               (uint32_t)lf[2] << 8 | lf[3]) == 70u);
    }
    /* and every byte of the body is accounted for */
    CHECK(filelen == GBP_VDISPDUMP_HEADER_SIZE + 2u * 96u + 2u * 40u + 12u);
    for (i = 0xE8u; i < GBP_VDISPDUMP_HEADER_SIZE - 4u; i++) CHECK(filebuf[i] == 0u);
}

/* Recomputes the header CRC-32 after an edit, so a check that sits BEHIND the
 * CRC can be reached and shown to exist. The global and section CRCs are left
 * broken on purpose where the expected verdict comes first. */
static void put_be32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
}

static void reseal(uint8_t *f)
{
    /* The header CRC first, because the GLOBAL CRC covers the header and would
     * otherwise report the repair as damage. Both have to be honest for the
     * check under test to be the one that fires. */
    const uint32_t off = ((uint32_t)f[0x50] << 24) | ((uint32_t)f[0x51] << 16) |
                         ((uint32_t)f[0x52] << 8) | f[0x53];
    put_be32(f + GBP_VDISPDUMP_HEADER_SIZE - 4u,
             gbp_crc32(f, GBP_VDISPDUMP_HEADER_SIZE - 4u));
    put_be32(f + off + 8u, gbp_crc32(f, off));
}

static void test_the_parser_refuses_every_shape_of_damage(void)
{
    struct gbp_vdispdump_info info;
    static uint8_t good[1 << 20];
    uint32_t goodlen, i;
    printf("-- OGBPDISP1: the parser names the damage instead of guessing\n");
    reset();
    (void)walk_ok(70u, 1000u, 0, 1);
    (void)walk_ok(71u, 2000u, 1, 1);
    CHECK(write_sidecar() > 0);
    memcpy(good, filebuf, filelen);
    goodlen = filelen;

    CHECK(gbp_vdispdump_parse(good, goodlen, &info, 0, 0) == 0);
    CHECK(gbp_vdispdump_parse(good, 8u, &info, 0, 0) == -1);          /* too short */
    memcpy(filebuf, good, goodlen); filebuf[0] ^= 1u;
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -1);  /* magic */
    memcpy(filebuf, good, goodlen); filebuf[0x09] = 9u;
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -2);  /* version */
    memcpy(filebuf, good, goodlen); filebuf[0x0B] = 0x80u;
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -2);  /* header size */
    /* The header CRC is the FIRST line of defence, so a check that lives behind
     * it can only be tested by repairing the CRC after the edit. Doing that
     * proves the later check exists rather than assuming the CRC covers for it. */
    memcpy(filebuf, good, goodlen); filebuf[0x13] = 99u; reseal(filebuf);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -2);  /* life rec size */
    memcpy(filebuf, good, goodlen); filebuf[0x17] = 99u; reseal(filebuf);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -2);  /* event rec size */
    /* life_n within the cap but inconsistent with the offsets: the geometry
     * check fires. */
    memcpy(filebuf, good, goodlen); filebuf[0x1F] = 1u; reseal(filebuf);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -4);
    /* life_n beyond the cap: the count check fires FIRST, before geometry. */
    memcpy(filebuf, good, goodlen); filebuf[0x1F] = 99u; reseal(filebuf);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -10);
    memcpy(filebuf, good, goodlen); filebuf[0x0F] |= 0x20u; reseal(filebuf);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -10); /* unknown flag */
    memcpy(filebuf, good, goodlen); filebuf[0x0F] &= (uint8_t)~GBP_VDISPDUMP_F_INTACT; reseal(filebuf);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == 0);   /* honest downgrade */
    memcpy(filebuf, good, goodlen); filebuf[0x33] = 1u; reseal(filebuf);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -10); /* unmatched, flag clear */
    memcpy(filebuf, good, goodlen); filebuf[0x57] ^= 1u; reseal(filebuf);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -9);  /* life section CRC */
    memcpy(filebuf, good, goodlen); filebuf[0x5B] ^= 1u; reseal(filebuf);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -9);  /* event section CRC */
    memcpy(filebuf, good, goodlen); filebuf[0xE8] = 1u; reseal(filebuf);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -8);  /* reserved not zero */
    memcpy(filebuf, good, goodlen);
    for (i = 0; i < 4u; i++) filebuf[0x68 + 20u + i] = 0x41u;
    reseal(filebuf);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -7);  /* identity rule */
    memcpy(filebuf, good, goodlen); filebuf[0x38] ^= 1u;
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -3);  /* header CRC */
    memcpy(filebuf, good, goodlen);
    CHECK(gbp_vdispdump_parse(filebuf, goodlen - 1u, &info, 0, 0) == -4); /* truncation */
    memcpy(filebuf, good, goodlen); filebuf[GBP_VDISPDUMP_HEADER_SIZE] ^= 1u;
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -6);  /* a life byte */
    memcpy(filebuf, good, goodlen);
    filebuf[GBP_VDISPDUMP_HEADER_SIZE + 2u * 96u] ^= 1u;
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -6);  /* an event byte */
    memcpy(filebuf, good, goodlen); filebuf[goodlen - 13u] ^= 1u;     /* last event byte */
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -6);
    memcpy(filebuf, good, goodlen); filebuf[goodlen - 12u] ^= 1u;
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -5);  /* footer magic */
    memcpy(filebuf, good, goodlen); filebuf[goodlen - 1u] ^= 1u;
    CHECK(gbp_vdispdump_parse(filebuf, goodlen, &info, 0, 0) == -6);  /* global CRC */
}

static void test_an_identity_that_does_not_fit_is_an_error(void)
{
    struct gbp_vdispdump_info info;
    static char toolong[64];
    unsigned i;
    printf("-- an identity is never truncated: it is refused\n");
    for (i = 0; i < 40u; i++) toolong[i] = 'x';
    toolong[40] = 0;
    memset(&info, 0, sizeof info);
    CHECK(gbp_vdispdump_set_identity(&info, "ok", toolong, "ok", "ok") == -1);
    CHECK(info.identity_error == 1);
    CHECK(gbp_vdispdump_set_identity(&info, "ok", "ok", "ok", "ok") == 0);
    CHECK(info.identity_error == 0);
}

static void test_an_overflowed_trace_says_so_in_the_file(void)
{
    static struct gbp_vdisp_life  l2[2];
    static struct gbp_vdisp_event e2[1];
    static const uint8_t st[2] = { 0u, 0u };
    struct gbp_vdispdump_info info;
    uint8_t chunk[GBP_VDISPDUMP_HEADER_SIZE];
    uint64_t w = 0;
    uint32_t i;
    printf("-- an incomplete trace is VISIBLY incomplete, in the header\n");
    CHECK(gbp_vdisp_init(&d, l2, 2u, e2, 1u) == 0);
    for (i = 0; i < 4u; i++) {
        const int L = gbp_vdisp_take(&d, i, i, 0u, 0u, i, i, i, 0u, 0, 0);
        gbp_vdisp_decision(&d, L, i, i, 0, -1, -1, GBP_VDISP_R_XFB_BUSY, st, 0, GBP_VDISP_KEY_NONE);
    }
    memset(&info, 0, sizeof info);
    info.tb_hz = 40500000u; info.xfb_slots = 2u;
    CHECK(gbp_vdispdump_set_identity(&info, "T", "B", "A", "C") == 0);
    filelen = 0;
    CHECK(gbp_vdispdump_stream(&info, &d, chunk, sizeof chunk, sink_mem, 0, &w) > 0);
    CHECK(gbp_vdispdump_parse(filebuf, filelen, &info, 0, 0) == 0);
    CHECK(!(info.flags & GBP_VDISPDUMP_F_INTACT));
    CHECK(info.flags & GBP_VDISPDUMP_F_LIFE_OVERFLOW);
    CHECK(info.flags & GBP_VDISPDUMP_F_EVENT_OVERFLOW);
    CHECK(info.life_overflow == 2u && info.event_overflow == 3u);
    CHECK(info.decisions == 4u && info.event_n == 1u);
    /* a file claiming INTACT while carrying overflow is impossible */
    filebuf[0x0F] |= (uint8_t)GBP_VDISPDUMP_F_INTACT;
    CHECK(gbp_vdispdump_parse(filebuf, filelen, &info, 0, 0) == -3);   /* CRC catches it first */
}

static void test_a_refused_sink_is_reported_and_never_silent(void)
{
    struct gbp_vdispdump_info info;
    uint8_t chunk[GBP_VDISPDUMP_HEADER_SIZE];
    uint64_t w = 123u;
    printf("-- a sink that refuses stops the write and reports what got out\n");
    reset();
    (void)walk_ok(1u, 1000u, 0, 1);
    memset(&info, 0, sizeof info);
    info.tb_hz = 40500000u; info.xfb_slots = 2u;
    CHECK(gbp_vdispdump_set_identity(&info, "T", "B", "A", "C") == 0);
    filelen = sizeof filebuf - 4u;             /* the very first write will not fit */
    CHECK(gbp_vdispdump_stream(&info, &d, chunk, sizeof chunk, sink_mem, 0, &w) == -4);
    CHECK(w == 0u);
    CHECK(gbp_vdispdump_stream(&info, &d, chunk, 4u, sink_mem, 0, &w) == -1);
    CHECK(gbp_vdispdump_stream(0, &d, chunk, sizeof chunk, sink_mem, 0, &w) == -1);
    CHECK(gbp_vdispdump_stream(&info, &d, chunk, sizeof chunk, 0, 0, &w) == -1);
}

static void test_the_production_geometry_is_the_audited_one(void)
{
    printf("-- the constants the audit and the analyzer both depend on\n");
    CHECK(GBP_VDISP_LIFE_CAP == 4096u);
    CHECK(GBP_VDISP_EVENT_CAP == 4096u);
    CHECK(GBP_VDISP_TEX_SLOTS == 2u);
    CHECK(GBP_VDISPDUMP_LIFE_SIZE == 96u);
    CHECK(GBP_VDISPDUMP_EVENT_SIZE == 40u);
    /* the discriminator fits the reserved word, so the record did not grow */
    CHECK(sizeof(struct gbp_vdisp_event) >= 40u);
    CHECK(GBP_VDISPDUMP_HEADER_SIZE == 0x100u);
    CHECK(sizeof(struct gbp_vdisp_life) >= 96u);
    CHECK(sizeof(struct gbp_vdisp_event) >= 40u);
    /* Capacity must clear the largest population a run of this shape produced:
     * run 4 closed 2 118 source frames and took 2 113. */
    CHECK(GBP_VDISP_LIFE_CAP > 2118u * 3u / 2u);
    /* and the whole file must stay small next to the witness store */
    CHECK((uint32_t)(GBP_VDISPDUMP_HEADER_SIZE + GBP_VDISP_LIFE_CAP * 96u
                     + GBP_VDISP_EVENT_CAP * 40u + 12u) < 1u << 20);
}

/* Writes a sidecar the HOST parser is checked against, so tools/vdisp.py is
 * validated against the real C writer and never against a Python restatement
 * of it. The scenario deliberately contains one of everything the analyzer has
 * a branch for. */
static int dump_fixture(const char *path)
{
    static const uint8_t st_busy[2] = { 3u, 0u };
    FILE *f;
    long n;
    int L;
    reset();
    /* the synthetic self-test, first and flagged */
    L = gbp_vdisp_take(&d, GBP_VDISP_KEY_NONE, 0u, 0u, 0u, 0u, 10u, 1u, 0u, 0, 1);
    gbp_vdisp_convert_done(&d, L, 20u, 0u);
    gbp_vdisp_submit(&d, L, 30u);
    gbp_vdisp_drawdone(&d, 0, 40u);
    gbp_vdisp_decision(&d, L, 50u, 1u, 0, -1, 1, GBP_VDISP_R_NONE, st_busy, 1, GBP_VDISP_KEY_NONE);
    /* two warm-up frames, outside the qualified window */
    (void)walk_ok(68u, 1000u, 0, 0);
    (void)walk_ok(69u, 2000u, 1, 0);
    /* the window opens */
    (void)walk_ok(70u, 3000u, 0, 1);
    (void)walk_ok(71u, 4000u, 1, 1);
    /* one HOLD: converted, submitted, DRAWN, and no framebuffer was free */
    L = gbp_vdisp_take(&d, 72u, 72u, 1u, 0x29u, 5000u, 5010u, 272u, 0u, 1, 0);
    gbp_vdisp_convert_first(&d, L, 5020u);
    gbp_vdisp_convert_done(&d, L, 5030u, 1450u);
    gbp_vdisp_submit(&d, L, 5040u);
    gbp_vdisp_drawdone(&d, 0, 5050u);
    /* frame 73 was ALREADY waiting when 72 was held: the discriminator */
    gbp_vdisp_decision(&d, L, 5060u, 273u, 0, 1, -1, GBP_VDISP_R_XFB_BUSY, st_busy, 1, 73u);
    /* a NORMAL frame after the hold. Without it the fixture ends on the hold
     * and every "what happened next" assertion is vacuous -- which is exactly
     * what mutation M12 exposed. */
    (void)walk_ok(75u, 5500u, 1, 1);
    /* one generation-guard overrun */
    L = gbp_vdisp_take(&d, 73u, 73u, 2u, 0x29u, 6000u, 6010u, 274u, 1u, 1, 0);
    gbp_vdisp_convert_done(&d, L, 6030u, 1400u);
    gbp_vdisp_abandon(&d, L, (uint16_t)GBP_VDISP_D_SLOT_OVERRUN);
    /* and one frame still in flight when the capture ended */
    L = gbp_vdisp_take(&d, 74u, 74u, 3u, 0x29u, 7000u, 7010u, 276u, 0u, 1, 0);
    gbp_vdisp_convert_done(&d, L, 7030u, 1400u);
    gbp_vdisp_submit_refused(&d, L);

    n = write_sidecar();
    if (n <= 0) return 1;
    f = fopen(path, "wb");
    if (!f) return 1;
    if (fwrite(filebuf, 1u, filelen, f) != filelen) { fclose(f); return 1; }
    fclose(f);
    printf("wrote %s: %lu bytes, %lu life, %lu events\n", path,
           (unsigned long)filelen, (unsigned long)d.life_n, (unsigned long)d.ev_n);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 3 && strcmp(argv[1], "--dump") == 0) return dump_fixture(argv[2]);
    printf("== test_gbp_vdisp (downstream disposition trace; every scenario SYNTHETIC)\n");
    test_A_a_frame_that_reaches_a_framebuffer();
    test_E_a_drawn_frame_that_reaches_no_framebuffer();
    test_D_a_token_gate_refusal_is_counted_not_evented();
    test_F_a_frame_still_in_flight_at_the_end_is_open();
    test_the_two_abandon_branches();
    test_H_the_selftest_is_isolated();
    test_I_texture_reuse_never_crosses_generations();
    test_J_overflow_fails_closed();
    test_bad_arguments_store_nothing();
    test_the_sidecar_round_trips_exactly();
    test_the_parser_refuses_every_shape_of_damage();
    test_an_identity_that_does_not_fit_is_an_error();
    test_an_overflowed_trace_says_so_in_the_file();
    test_a_refused_sink_is_reported_and_never_silent();
    test_the_production_geometry_is_the_audited_one();
    printf("%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
