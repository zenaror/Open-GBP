/*
 * Open-GBP GBP-VIDEO-007 / GBP-VIDEO-008 — the CONTROLLED COORDINATE video
 * stimulus, OGBPCOORD1, second implementation: coord-0002 (HARDWARE_TESTS
 * §V6.23, GitHub Issue #13). coord-0001 (stimulus/agb-coord) is the RUN 12
 * artifact and stays exactly as it ran; this is a NEW stimulus identity that
 * publishes the SAME picture.
 *
 * WHAT CHANGED, AND WHY (GBP-VID-034, §V6.22)
 *   coord-0001 built the 80 x 50 digit table INSIDE the entry frame's PREPARE:
 *   per glyph pixel a reload of the digit, a GamePak ROM byte read and up to
 *   seven tests, plus an EWRAM read for every unlit pixel. For the sparse
 *   digits 1 and 4 that PREPARE cost more than an AGB frame, the two-loop
 *   VCOUNT wait skipped a VBlank, and the GBP captured the previous FRAME_ID
 *   twice (RUN 12: 479, 479, 480 and 1919, 1919, 1920). The FAULT latch cannot
 *   see a PREPARE-side miss, because it brackets PUBLISH only.
 *   coord-0002 builds ALL TEN digit tables ONCE at boot, before the display is
 *   enabled and before the scientific loop starts (glyph_tables_init, 80 000 B
 *   of EWRAM, NOLOAD: no ROM payload). The entry PREPARE only SELECTS the
 *   table of the digit; PUBLISH DMAs the selected rows exactly as before, from
 *   EWRAM, so the published words and the PUBLISH timing are unchanged. The
 *   entry PREPARE has ZERO per-pixel work and zero GamePak ROM reads.
 *
 * THIS PROGRAM IS A MEASURING INSTRUMENT. Every pixel it writes is known by
 * construction to an offline model (tools/icoord.py, UNCHANGED for coord-0002),
 * and nothing here may be "improved" without changing that contract first.
 *
 * WHAT IT IS FOR
 *   GBP-VIDEO-008 needs a frame whose EVERY pixel names its own position, so a
 *   row shift, a column shift, an axis swap, a tile permutation or a block
 *   displacement anywhere in the 240x160 picture is falsifiable offline.
 *   GBP-VIDEO-007 needs a large, unmistakable, cartridge-painted glyph the
 *   operator can see and the model can bind to a set of frame ids.
 *
 * THE PICTURE (Mode 3, 240x160, BGR555, bit 15 NEVER written)
 *   x = 0          FLAG     0x03E0        BYTE-IDENTICAL to OGBPIDX1
 *   x = 1..54      STRIP-L  the 54-bit payload, rows 0/2 plain, rows 1/3
 *                           complemented                BYTE-IDENTICAL to OGBPIDX1
 *   x = 55         GUARD    0x0000        BYTE-IDENTICAL to OGBPIDX1
 *   x = 56..238    FIELD    y*183 + (x-56): 0..29279, injective, bit 15 clear,
 *                           painted ONCE at boot
 *   x = 239        GUARD    0x0000
 *   glyph          for frame_id in R_k = [k*480, k*480+40), k >= 1: the seven-
 *                  segment digit (k mod 10), 48x80 at (123, 40), and six 8x8
 *                  squares at (123.., 128) showing frame_id - k*480 in binary,
 *                  MSB left; both painted INTO the field, in 0x7FFF
 *   REMOVED        STRIP-R and the moving bar of OGBPIDX1: their columns belong
 *                  to the field
 *
 * THE PAYLOAD, 54 bits, MSB first — exactly OGBPIDX1's
 *   SYNC 8 (0xB2) | FRAME_ID 24 | BLOCK_INDEX 6 | STATUS 8 | CRC8 8
 *   CRC-8 poly 0x07, init 0xFF, no reflection, no augmentation, xorout 0,
 *   over the 38 bits FRAME_ID || BLOCK_INDEX || STATUS.
 *
 * WHY THE WITNESS BYTES ARE IDENTICAL
 *   gbp_vwitness, the not-before gate, OGBPIDXCAP1 and the frozen
 *   tools/vindex.py verdict read STRIP-L, local row 0, x = 1..54, and nothing
 *   else. Keeping those bytes identical means every established regression
 *   gate applies to a coord-0001 run unchanged (§V6.6).
 *
 * SELF-VALIDATION — unchanged from OGBPIDX1
 *   VCOUNT and Timer 0 at F/64 bracket every PUBLISH, and a STICKY fault latch
 *   rides in the payload. A run whose FAULT bit is ever set is inadmissible
 *   (§V6.12). The glyph's paint and erase are the ONLY per-frame work beyond the
 *   strips, and they happen on the entry and exit frames of an appearance;
 *   whether they fit is decided by this latch, never assumed (§V6.17 item 4).
 *
 * BUDGET: PUBLISH is the same DMA work as coord-0001 (RUN 12 measured its
 *   three classes end at VMARGIN 54 / 39 / 38-39, §V6.22.5). PREPARE is the
 *   part coord-0001 never bounded: here the entry frame prepares the strips and
 *   the squares and selects a table -- the cycle model of the exact image
 *   (tools/coordtime.py, profile coord-0002; §V6.23) bounds every class of
 *   PREPARE against the VBlank-to-VBlank budget. The estimate is not evidence;
 *   the model is a model; STATUS still decides PUBLISH on hardware.
 *
 * NO heap, NO filesystem, NO link cable, NO serial, NO GameCube dependency, NO
 * logging, NO division anywhere, NO interrupt: the VBlank edge is polled.
 */

typedef unsigned char      u8;
typedef unsigned short     u16;
typedef unsigned int       u32;

/* The three hardware bases are the ONLY thing a host test may relocate (the
 * indexed ROM's rule, §V5.33): tests/host/test_agb_coord.py compares this
 * program's VRAM word for word against tools/icoord.py. */
#ifndef AGB_IO_BASE
#define AGB_IO_BASE   0x04000000u
#endif
#ifndef AGB_VRAM_BASE
#define AGB_VRAM_BASE 0x06000000u
#endif
#ifndef AGB_OAM_BASE
#define AGB_OAM_BASE  0x07000000u
#endif

#define AGB_IO16(off) (*(volatile u16 *)((unsigned long)AGB_IO_BASE + (off)))

#define REG_DISPCNT  AGB_IO16(0x000)
#define REG_DISPSTAT AGB_IO16(0x004)
#define REG_VCOUNT   AGB_IO16(0x006)
#define REG_BLDCNT   AGB_IO16(0x050)
#define REG_BLDALPHA AGB_IO16(0x052)
#define REG_BLDY     AGB_IO16(0x054)
#define REG_MOSAIC   AGB_IO16(0x04C)
#define REG_WAITCNT  AGB_IO16(0x204)
#define REG_DMA3SAD  (*(volatile u32 *)(unsigned long)(AGB_IO_BASE + 0x0D4))
#define REG_DMA3DAD  (*(volatile u32 *)(unsigned long)(AGB_IO_BASE + 0x0D8))
#define REG_DMA3CNT  (*(volatile u32 *)(unsigned long)(AGB_IO_BASE + 0x0DC))
#define REG_TM0CNT_L AGB_IO16(0x100)
#define REG_TM0CNT_H AGB_IO16(0x102)
#define REG_IE       AGB_IO16(0x200)
#define REG_IF       AGB_IO16(0x202)
#define REG_IME      AGB_IO16(0x208)

#define VRAM ((volatile u16 *)(unsigned long)AGB_VRAM_BASE)
#define OAM  ((volatile u16 *)(unsigned long)AGB_OAM_BASE)

/* ---- the geometry (OGBPCOORD1; the witness part is OGBPIDX1's) ---- */
#define SCREEN_W 240u
#define SCREEN_H 160u
#define BLOCKS   40u
#define LINES_PER_BLOCK 4u

#define X_FLAG     0u
#define STRIP_L_X0 1u
#define X_GUARD_A  55u
#define FIELD_X0   56u
#define FIELD_W    183u
#define X_GUARD_C  239u

#define STRIP_BITS   54u
#define PAYLOAD_BITS 38u
#define SYNC_BYTE    0xB2u

/* ---- the frozen symbols (OGBPIDX1) ---- */
#define SYM_ZERO  0x0000u
#define SYM_ONE   0x7FFFu
#define SYM_FLAG  0x03E0u
#define SYM_GUARD 0x0000u

/* ---- the glyph schedule (§V6.4, §V6.6; Issue #7 decision 4) ---- */
#define GLYPH_P      480u                 /* appearance period, frames */
#define GLYPH_W      40u                  /* appearance width, frames */
#define GLYPH_X0     123u                 /* 56 + (183 - 48) / 2 */
#define GLYPH_Y0     40u                  /* (160 - 80) / 2 */
#define GLYPH_COLS   48u
#define GLYPH_ROWS   80u
#define SEG_T        8u                   /* segment thickness */
#define SQ_X0        123u
#define SQ_Y0        128u
#define SQ_N         6u
#define SQ_SIZE      8u
#define SQ_COLS      (SQ_N * SQ_SIZE)     /* 48 */
#define GLYPH_COLOUR 0x7FFFu

/* ---- STATUS ---- */
#define STATUS_FAULT_MASK  0x80u
#define STATUS_MARGIN_MASK 0x7Fu
#define STATUS_MARGIN_INIT 0x7Fu

/* ---- the self-validation facts (GBATEK) ---- */
#define VCOUNT_VBLANK_FIRST 160u
#define VCOUNT_LAST         227u
#define VBLANK_TICKS        1309u

/* ---- CRC-8, bit-exact with tools/istim.py (and therefore tools/icoord.py) --- */
static u8 crc_tab[256];

static void crc_table_init(void)
{
    unsigned i, b;
    for (i = 0; i < 256u; i++) {
        u8 c = (u8)i;
        for (b = 0; b < 8u; b++)
            c = (u8)((c & 0x80u) ? (u8)((u8)(c << 1) ^ 0x07u) : (u8)(c << 1));
        crc_tab[i] = c;
    }
}

static u8 crc_after_id(u32 frame_id)
{
    u8 c = 0xFFu;
    c = crc_tab[c ^ (u8)((frame_id >> 16) & 0xFFu)];
    c = crc_tab[c ^ (u8)((frame_id >> 8) & 0xFFu)];
    c = crc_tab[c ^ (u8)(frame_id & 0xFFu)];
    return c;
}

static u8 crc_finish(u8 crc_id, unsigned block_index, u8 status)
{
    u8 c = crc_id;
    unsigned i;
    for (i = 6u; i-- > 0u;) {
        u8 fb = (u8)(((c >> 7) & 1u) ^ ((block_index >> i) & 1u));
        c = (u8)(c << 1);
        if (fb) c = (u8)(c ^ 0x07u);
    }
    return crc_tab[c ^ status];
}

static void strip_word(u8 *bits, u32 frame_id, unsigned block_index, u8 status, u8 crc)
{
    unsigned i, k = 0;
    for (i = 8u; i-- > 0u;) bits[k++] = (u8)((SYNC_BYTE >> i) & 1u);
    for (i = 24u; i-- > 0u;) bits[k++] = (u8)((frame_id >> i) & 1u);
    for (i = 6u; i-- > 0u;)  bits[k++] = (u8)((block_index >> i) & 1u);
    for (i = 8u; i-- > 0u;)  bits[k++] = (u8)((status >> i) & 1u);
    for (i = 8u; i-- > 0u;)  bits[k++] = (u8)((crc >> i) & 1u);
}

/* ---- the coordinate field: every pixel names its own position ------------ */
static u16 field_at(unsigned x, unsigned y)
{
    return (u16)(y * FIELD_W + (x - FIELD_X0));      /* 0 .. 29279 */
}

/* ---- the seven-segment digit, as a pure pixel predicate --------------------
 * bit 0 a top, 1 b top-right, 2 c bottom-right, 3 d bottom, 4 e bottom-left,
 * 5 f top-left, 6 g middle. */
static const u8 seg_of_digit[10] = { 0x3Fu, 0x06u, 0x5Bu, 0x4Fu, 0x66u, 0x6Du, 0x7Du, 0x07u, 0x7Fu, 0x6Fu };

static unsigned glyph_lit(unsigned digit, unsigned gx, unsigned gy)
{
    const unsigned s = seg_of_digit[digit];
    const unsigned top = gy < 44u, bottom = gy >= 36u;
    if ((s & 0x01u) && gy < SEG_T) return 1u;                                   /* a */
    if ((s & 0x08u) && gy >= GLYPH_ROWS - SEG_T) return 1u;                     /* d */
    if ((s & 0x40u) && gy >= 36u && gy < 44u) return 1u;                         /* g */
    if ((s & 0x02u) && gx >= GLYPH_COLS - SEG_T && top) return 1u;              /* b */
    if ((s & 0x04u) && gx >= GLYPH_COLS - SEG_T && bottom) return 1u;           /* c */
    if ((s & 0x20u) && gx < SEG_T && top) return 1u;                            /* f */
    if ((s & 0x10u) && gx < SEG_T && bottom) return 1u;                         /* e */
    return 0u;
}

/* ---- the static picture, written ONCE at boot ------------------------------ */
static void paint_background(void)
{
    unsigned x, y;
    for (y = 0; y < SCREEN_H; y++) {
        volatile u16 *row = VRAM + y * SCREEN_W;
        row[X_FLAG] = SYM_FLAG;
        row[X_GUARD_A] = SYM_GUARD;
        row[X_GUARD_C] = SYM_GUARD;
        for (x = FIELD_X0; x < FIELD_X0 + FIELD_W; x++) row[x] = field_at(x, y);
        for (x = STRIP_L_X0; x < STRIP_L_X0 + STRIP_BITS; x++) row[x] = SYM_ZERO;
    }
}

/* ---- the self-validation verdict (identical to OGBPIDX1's) ---------------- */
struct agb_status { u8 fault; u8 vmargin; };

static void status_measure(struct agb_status *s, u16 vc0, u16 vc1, unsigned elapsed)
{
    if (vc1 < vc0 || vc1 > VCOUNT_LAST || elapsed > VBLANK_TICKS) {
        s->fault = 1;
        s->vmargin = 0;
    } else {
        unsigned margin = (unsigned)(VCOUNT_LAST - vc1);
        if (margin > STATUS_MARGIN_MASK) margin = STATUS_MARGIN_MASK;
        if ((u8)margin < s->vmargin) s->vmargin = (u8)margin;
    }
}

static u8 status_byte(const struct agb_status *s)
{
    return (u8)((s->fault ? STATUS_FAULT_MASK : 0u) | (s->vmargin & STATUS_MARGIN_MASK));
}

/* ---- PREPARE / PUBLISH ------------------------------------------------------
 * PREPARE runs in the visible period, touches no VRAM and, on an entry
 * frame, builds nothing (it selects a boot-built table); PUBLISH runs in
 * VBlank only, from IWRAM, and only copies. The strip span x = 0..55 is the
 * OGBPIDX1 left span, DMA'd as 28 aligned 32-bit units per row. The glyph rows
 * are 48 words = 24 units, at an even column (123 is odd: the span starts at
 * x = 122 so the DMA stays 4-byte aligned, and column 122 carries its own
 * field value in every row, which keeps the wire identical to the model). */
#define PUB_L_X0   0u
#define PUB_L_W    56u
#define GLYPH_SPAN_X0 (GLYPH_X0 - 1u)                /* 122, even */
#define GLYPH_SPAN_W  (GLYPH_COLS + 2u)              /* 50: 122 .. 171 */
#define SQ_SPAN_X0    (SQ_X0 - 1u)                   /* 122, even */
#define SQ_SPAN_W     (SQ_COLS + 2u)                 /* 50: 122 .. 171 */

/* In IWRAM by construction: .bss is at 0x03000000 on this target. */
static u16 pub_l[BLOCKS][2][PUB_L_W];
static u16 pub_sq[SQ_SIZE][SQ_SPAN_W];

/* Large tables live in EWRAM (.sbss: NOLOAD, so they cost no ROM bytes; the
 * crt0 clears EWRAM and this program fills them at boot). glyph_tables holds
 * the complete published rows of every digit 0..9 -- 10 x 80 x 50 words =
 * 80 000 B -- built ONCE by glyph_tables_init() before the display is enabled;
 * glyph_erase and sq_erase hold the field words the glyph and the squares
 * cover. Nothing writes any of them after boot. */
#ifdef AGB_HOST_TEST
#define EWRAM_SECTION
#else
#define EWRAM_SECTION __attribute__((section(".sbss")))
#endif
#define DIGITS 10u
static u16 glyph_tables[DIGITS][GLYPH_ROWS][GLYPH_SPAN_W] EWRAM_SECTION;
static u16 glyph_erase[GLYPH_ROWS][GLYPH_SPAN_W] EWRAM_SECTION;
static u16 sq_erase[SQ_SIZE][SQ_SPAN_W] EWRAM_SECTION;

/* The table PUBLISH reads on an entry frame: selected by PREPARE (one pointer
 * store, IWRAM), never built there. */
static const u16 (*glyph_sel)[GLYPH_SPAN_W];

/* The schedule, DIVISION-FREE: a phase counter inside the period, the
 * appearance ordinal and its digit, all advanced by compare-and-subtract. */
struct sched { u32 phase; u32 k; u32 digit; };

static void sched_init(struct sched *s) { s->phase = 0u; s->k = 0u; s->digit = 0u; }

static void sched_advance(struct sched *s)
{
    s->phase += 1u;
    if (s->phase >= GLYPH_P) {
        s->phase = 0u;
        s->k += 1u;
        s->digit += 1u;
        if (s->digit >= 10u) s->digit = 0u;
    }
}

enum glyph_op { OP_NONE = 0, OP_PAINT = 1, OP_ERASE = 2 };
static u8 op_digit, op_sq;

static void erase_tables_init(void)
{
    unsigned r, c;
    for (r = 0; r < GLYPH_ROWS; r++)
        for (c = 0; c < GLYPH_SPAN_W; c++)
            glyph_erase[r][c] = field_at(GLYPH_SPAN_X0 + c, GLYPH_Y0 + r);
    for (r = 0; r < SQ_SIZE; r++)
        for (c = 0; c < SQ_SPAN_W; c++)
            sq_erase[r][c] = field_at(SQ_SPAN_X0 + c, SQ_Y0 + r);
}

/* BOOT ONLY, after erase_tables_init() and before REG_DISPCNT is written: the
 * complete published rows of every digit, exactly the words coord-0001 built
 * per entry (the lit predicate and the erase values are the same). Runs once;
 * its cost is spent before the scientific loop exists. */
static void glyph_tables_init(void)
{
    unsigned d, r, c;
    for (d = 0; d < DIGITS; d++)
        for (r = 0; r < GLYPH_ROWS; r++)
            for (c = 0; c < GLYPH_SPAN_W; c++)
                glyph_tables[d][r][c] = (c >= 1u && c <= GLYPH_COLS && glyph_lit(d, c - 1u, r))
                                        ? (u16)GLYPH_COLOUR : glyph_erase[r][c];
}

__attribute__((section(".iwram"), noinline))
static void prepare_frame(u32 frame_id, u8 status, const struct sched *sc)
{
    u8 bits[STRIP_BITS];
    const u8 crc_id = crc_after_id(frame_id);
    unsigned b, r, c;
    const unsigned shown = (sc->k >= 1u) && (sc->phase < GLYPH_W);

    for (b = 0; b < BLOCKS; b++) {
        const u8 crc = crc_finish(crc_id, b, status);
        unsigned i, inv;
        strip_word(bits, frame_id, b, status, crc);
        for (inv = 0; inv < 2u; inv++) {
            u16 *l = pub_l[b][inv];
            l[X_FLAG - PUB_L_X0]    = SYM_FLAG;
            l[X_GUARD_A - PUB_L_X0] = SYM_GUARD;
            for (i = 0; i < STRIP_BITS; i++) {
                const unsigned v = (unsigned)bits[i] ^ inv;
                l[STRIP_L_X0 - PUB_L_X0 + i] = v ? SYM_ONE : SYM_ZERO;
            }
        }
    }

    /* the digit: painted on the entry frame, erased on the exit frame. The
     * entry frame SELECTS the digit's precomputed table (one load, one store,
     * IWRAM): no pixel is computed, no ROM byte is read, here (GBP-VID-034). */
    op_digit = OP_NONE;
    if (sc->k >= 1u && sc->phase == 0u) {
        op_digit = OP_PAINT;
        glyph_sel = glyph_tables[sc->digit];
    } else if (sc->k >= 1u && sc->phase == GLYPH_W) {
        op_digit = OP_ERASE;
    }

    /* the counter squares: repainted every shown frame, erased on the exit frame */
    op_sq = OP_NONE;
    if (shown) {
        op_sq = OP_PAINT;
        for (r = 0; r < SQ_SIZE; r++) {
            for (c = 0; c < SQ_SPAN_W; c++) {
                unsigned lit = 0u;
                if (c >= 1u && c <= SQ_COLS) {
                    const unsigned i = (c - 1u) >> 3;                 /* square 0..5, MSB left */
                    lit = (sc->phase >> (SQ_N - 1u - i)) & 1u;
                }
                pub_sq[r][c] = lit ? (u16)GLYPH_COLOUR : sq_erase[r][c];
            }
        }
    } else if (sc->k >= 1u && sc->phase == GLYPH_W) {
        op_sq = OP_ERASE;
    }
}

static void pub_copy32(volatile u16 *dst, const u16 *src, unsigned words)
{
#ifdef AGB_HOST_TEST
    unsigned i;
    for (i = 0; i < words; i++) dst[i] = src[i];
#else
    REG_DMA3SAD = (u32)(unsigned long)src;
    REG_DMA3DAD = (u32)(unsigned long)dst;
    REG_DMA3CNT = 0x84000000u | (words >> 1);      /* enable | 32-bit */
#endif
}

__attribute__((section(".iwram"), noinline))
static void publish_frame(void)
{
    unsigned b, row, r;
    for (b = 0; b < BLOCKS; b++) {
        for (row = 0; row < LINES_PER_BLOCK; row++) {
            volatile u16 *v = VRAM + (b * LINES_PER_BLOCK + row) * SCREEN_W;
            pub_copy32(v + PUB_L_X0, pub_l[b][row & 1u], PUB_L_W);
        }
    }
    if (op_digit == OP_PAINT) {
        for (r = 0; r < GLYPH_ROWS; r++)
            pub_copy32(VRAM + (GLYPH_Y0 + r) * SCREEN_W + GLYPH_SPAN_X0, glyph_sel[r], GLYPH_SPAN_W);
    } else if (op_digit == OP_ERASE) {
        for (r = 0; r < GLYPH_ROWS; r++)
            pub_copy32(VRAM + (GLYPH_Y0 + r) * SCREEN_W + GLYPH_SPAN_X0, glyph_erase[r], GLYPH_SPAN_W);
    }
    if (op_sq == OP_PAINT) {
        for (r = 0; r < SQ_SIZE; r++)
            pub_copy32(VRAM + (SQ_Y0 + r) * SCREEN_W + SQ_SPAN_X0, pub_sq[r], SQ_SPAN_W);
    } else if (op_sq == OP_ERASE) {
        for (r = 0; r < SQ_SIZE; r++)
            pub_copy32(VRAM + (SQ_Y0 + r) * SCREEN_W + SQ_SPAN_X0, sq_erase[r], SQ_SPAN_W);
    }
}

int main(void)
{
    u32 frame_id = 0;
    u8 status = STATUS_MARGIN_INIT;
    struct agb_status st = { 0u, STATUS_MARGIN_INIT };
    struct sched sc;
    unsigned i;

    REG_BLDCNT = 0; REG_BLDALPHA = 0; REG_BLDY = 0; REG_MOSAIC = 0;
    REG_IME = 0; REG_IE = 0; REG_IF = 0xFFFFu;
    for (i = 0; i < 512u; i++) OAM[i] = 0x0200u;
    REG_WAITCNT = 0x4317u;
    REG_TM0CNT_H = 0;
    REG_TM0CNT_L = 0;
    REG_TM0CNT_H = 0x0081u;

    crc_table_init();
    erase_tables_init();
    glyph_tables_init();               /* all ten digits, once, before anything is shown */
    paint_background();

    sched_init(&sc);
    prepare_frame(0, status, &sc);
    publish_frame();
    REG_DISPCNT = 0x0403u;

    for (;;) {
        u16 t0, t1, vc0, vc1;
        unsigned elapsed;

        sched_advance(&sc);
        frame_id = (frame_id + 1u) & 0x00FFFFFFu;
        status = status_byte(&st);

        prepare_frame(frame_id, status, &sc);

        while (REG_VCOUNT >= VCOUNT_VBLANK_FIRST) { }
        while (REG_VCOUNT <  VCOUNT_VBLANK_FIRST) { }

        vc0 = REG_VCOUNT;
        t0 = REG_TM0CNT_L;
        publish_frame();
        t1 = REG_TM0CNT_L;
        vc1 = REG_VCOUNT;

        elapsed = (unsigned)((u16)(t1 - t0));
        status_measure(&st, vc0, vc1, elapsed);
    }
}
