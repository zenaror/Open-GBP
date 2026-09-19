/*
 * Open-GBP GBP-VIDEO-004 — the CONTROLLED INDEXED video stimulus, OGBPIDX1.
 *
 * THIS PROGRAM IS A MEASURING INSTRUMENT. Every pixel it writes is known by
 * construction to an offline model (tools/istim.py), and the contract it
 * implements is frozen in HARDWARE_TESTS §V5.33. Nothing here may be "improved"
 * without changing that contract first: the analyzer decodes what this paints,
 * and a silent divergence would make every result meaningless.
 *
 * WHAT IT IS FOR
 *   Every AGB frame carries its own 24-bit frame number, in every one of the 40
 *   VIDEO blocks the Game Boy Player will later deliver, so an offline analyzer
 *   can state which frames arrived, in order, with every block belonging to the
 *   same frame. That is the ground truth §V5.18 requires and that no commercial
 *   cartridge can provide.
 *
 * THE PICTURE (Mode 3, 240x160, BGR555, bit 15 NEVER written)
 *   x = 0          FLAG     0x03E0   the bit-15 observation pixel (U-GBP-034)
 *   x = 1..54      STRIP-L  the 54-bit payload
 *   x = 55         GUARD    0x0000
 *   x = 56..183    CONTENT  32 cells of 4 px: a static ramp plus a moving bar
 *   x = 184        GUARD
 *   x = 185..238   STRIP-R  the same payload, reversed and/or complemented
 *   x = 239        GUARD
 *   block b = rows 4b..4b+3, b = 0..39
 *
 * THE PAYLOAD, 54 bits, MSB first
 *   SYNC 8 (0xB2) | FRAME_ID 24 | BLOCK_INDEX 6 | STATUS 8 | CRC8 8
 *   CRC-8 poly 0x07, init 0xFF, no reflection, no augmentation, xorout 0,
 *   over the 38 bits FRAME_ID || BLOCK_INDEX || STATUS.
 *
 * WHY ZERO IS 0x0000 AND ONE IS 0x7FFF
 *   Both are fixed points of the outer-group exchange the Game Boy Player
 *   performs (GBP-HW-131), so the frame id decodes correctly even if that
 *   mapping were ever revised. The symbols are chosen for maximum distance, not
 *   for looks.
 *
 * SELF-VALIDATION — THE PART THAT MAKES THE RUN TRUSTWORTHY
 *   Mode 3 has ONE framebuffer, so a write outside VBlank tears at the source.
 *   This program therefore measures itself: VCOUNT and a free-running Timer 0 at
 *   F/64 bracket every update, and a STICKY fault latch rides in the payload. A
 *   run whose FAULT bit is ever set cannot support a source-integrity claim, and
 *   the analyzer is required to refuse it.
 *
 * NO heap, NO filesystem, NO link cable, NO serial, NO GameCube dependency, NO
 * logging, and NO division anywhere in the VBlank path: ARM7TDMI has no divide
 * instruction, so every modulo here is a compare-and-subtract on a counter.
 */

typedef unsigned char      u8;
typedef unsigned short     u16;
typedef unsigned int       u32;

/* The two hardware bases are the ONLY thing a host test may relocate. Their
 * defaults are the real GBA addresses and nothing else about the program
 * changes; this exists so the pure rendering logic can be compared word for
 * word against tools/istim.py on the host (HARDWARE_TESTS §V5.33 requires that
 * equivalence, and a ROM that cannot be compared to its model is not a
 * measuring instrument). */
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
#define REG_TM0CNT_L AGB_IO16(0x100)
#define REG_TM0CNT_H AGB_IO16(0x102)
#define REG_IE       AGB_IO16(0x200)
#define REG_IF       AGB_IO16(0x202)
#define REG_IME      AGB_IO16(0x208)

#define VRAM ((volatile u16 *)(unsigned long)AGB_VRAM_BASE)
#define OAM  ((volatile u16 *)(unsigned long)AGB_OAM_BASE)

/* ---- the frozen geometry (OGBPIDX1) ---- */
#define SCREEN_W 240u
#define SCREEN_H 160u
#define BLOCKS   40u
#define LINES_PER_BLOCK 4u

#define X_FLAG     0u
#define STRIP_L_X0 1u
#define X_GUARD_A  55u
#define CONTENT_X0 56u
#define CONTENT_W  128u
#define X_GUARD_B  184u
#define STRIP_R_X0 185u
#define X_GUARD_C  239u

#define STRIP_BITS   54u
#define PAYLOAD_BITS 38u
#define SYNC_BYTE    0xB2u

/* ---- the frozen symbols ---- */
#define SYM_ZERO 0x0000u
#define SYM_ONE  0x7FFFu
#define SYM_FLAG 0x03E0u
#define SYM_GUARD 0x0000u

/* ---- content ---- */
#define CELL        4u
#define BAR_CELLS   2u
#define BAR_PERIOD  31u
#define BAR_PHASE_MUL 8u
#define BAR_COLOUR  0x7C00u

/* PAL16[k] = 0x0842 * k, a 16-step grey ramp, bit 15 never set. */
static const u16 pal16[16] = {
    0x0000u, 0x0842u, 0x1084u, 0x18C6u, 0x2108u, 0x294Au, 0x318Cu, 0x39CEu,
    0x4210u, 0x4A52u, 0x5294u, 0x5AD6u, 0x6318u, 0x6B5Au, 0x739Cu, 0x7BDEu
};

/* ---- STATUS ---- */
#define STATUS_FAULT_MASK  0x80u
#define STATUS_MARGIN_MASK 0x7Fu
#define STATUS_MARGIN_INIT 0x7Fu

/* ---- the self-validation facts (GBATEK) ---- */
#define VCOUNT_VBLANK_FIRST 160u
#define VCOUNT_LAST         227u
/* VBlank is 83 776 cycles; the F/64 timer ticks every 64 cycles. */
#define VBLANK_TICKS        1309u

/* ---- CRC-8, bit-exact with tools/istim.py ---------------------------------
 * A 256-entry table is built once at boot, outside VBlank. In the VBlank path
 * the whole 38-bit payload costs five table lookups, because the payload is a
 * whole number of bytes only after FRAME_ID(24) || BLOCK_INDEX(6) || STATUS(8)
 * is viewed as 38 bits — so the last 6 bits are folded bitwise. That is 6
 * iterations per block, not 38. */
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

/* CRC over FRAME_ID[23..0] || BLOCK_INDEX[5..0] || STATUS[7..0], MSB first.
 * `crc_id` is the register after the 24 FRAME_ID bits, folded once per frame. */
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
    /* the 6 BLOCK_INDEX bits, MSB first, bitwise */
    for (i = 6u; i-- > 0u;) {
        u8 fb = (u8)(((c >> 7) & 1u) ^ ((block_index >> i) & 1u));
        c = (u8)(c << 1);
        if (fb) c = (u8)(c ^ 0x07u);
    }
    /* then the whole STATUS byte in one lookup */
    return crc_tab[c ^ status];
}

/* ---- the 54-bit strip word, expanded MSB-first into `bits` ---------------- */
static void strip_word(u8 *bits, u32 frame_id, unsigned block_index, u8 status, u8 crc)
{
    unsigned i, k = 0;
    for (i = 8u; i-- > 0u;) bits[k++] = (u8)((SYNC_BYTE >> i) & 1u);
    for (i = 24u; i-- > 0u;) bits[k++] = (u8)((frame_id >> i) & 1u);
    for (i = 6u; i-- > 0u;)  bits[k++] = (u8)((block_index >> i) & 1u);
    for (i = 8u; i-- > 0u;)  bits[k++] = (u8)((status >> i) & 1u);
    for (i = 8u; i-- > 0u;)  bits[k++] = (u8)((crc >> i) & 1u);
}

/* ---- the static background, written ONCE at boot -------------------------- */
static u16 background_at(unsigned x, unsigned y)
{
    return pal16[(((x - CONTENT_X0) >> 2) + (y >> 2)) & 15u];
}

static void paint_background(void)
{
    unsigned x, y;
    for (y = 0; y < SCREEN_H; y++) {
        volatile u16 *row = VRAM + y * SCREEN_W;
        row[X_FLAG] = SYM_FLAG;
        row[X_GUARD_A] = SYM_GUARD;
        row[X_GUARD_B] = SYM_GUARD;
        row[X_GUARD_C] = SYM_GUARD;
        for (x = CONTENT_X0; x < CONTENT_X0 + CONTENT_W; x++)
            row[x] = background_at(x, y);
        /* the strips are written every frame; fill them with ZERO so no frame
         * is ever displayed with uninitialised VRAM under them */
        for (x = STRIP_L_X0; x < STRIP_L_X0 + STRIP_BITS; x++) row[x] = SYM_ZERO;
        for (x = STRIP_R_X0; x < STRIP_R_X0 + STRIP_BITS; x++) row[x] = SYM_ZERO;
    }
}

/* ---- the per-frame update, the whole of the VBlank path ------------------- */
/* barpos(f,b) = (f + 8*b) mod 31, kept DIVISION-FREE: the phase for block 0 is
 * carried in a counter that is incremented and conditionally reduced, and each
 * block adds 8 with the same compare-and-subtract. */
static unsigned bar_phase_base;      /* (frame_id mod 31) */

static void update_frame(u32 frame_id, u8 status, unsigned prev_phase_base)
{
    u8 bits[STRIP_BITS];
    const u8 crc_id = crc_after_id(frame_id);
    unsigned b;
    unsigned phase = bar_phase_base;
    unsigned prev_phase = prev_phase_base;

    for (b = 0; b < BLOCKS; b++) {
        const u8 crc = crc_finish(crc_id, b, status);
        unsigned i, row;
        unsigned x0_new = CONTENT_X0 + CELL * phase;
        unsigned x0_old = CONTENT_X0 + CELL * prev_phase;

        strip_word(bits, frame_id, b, status, crc);

        for (row = 0; row < LINES_PER_BLOCK; row++) {
            const unsigned y = b * LINES_PER_BLOCK + row;
            volatile u16 *r = VRAM + y * SCREEN_W;
            const unsigned inv = (row & 1u);          /* rows 1 and 3 are complemented */

            /* STRIP-L: plain on rows 0/2, complemented on rows 1/3 */
            for (i = 0; i < STRIP_BITS; i++) {
                const unsigned v = (unsigned)bits[i] ^ inv;
                r[STRIP_L_X0 + i] = v ? SYM_ONE : SYM_ZERO;
            }
            /* STRIP-R: reversed, and complemented on rows 0/2 (not 1/3) */
            for (i = 0; i < STRIP_BITS; i++) {
                const unsigned v = (unsigned)bits[STRIP_BITS - 1u - i] ^ (inv ^ 1u);
                r[STRIP_R_X0 + i] = v ? SYM_ONE : SYM_ZERO;
            }
            /* erase the previous bar, then draw the new one */
            for (i = 0; i < CELL * BAR_CELLS; i++)
                r[x0_old + i] = background_at(x0_old + i, y);
            for (i = 0; i < CELL * BAR_CELLS; i++)
                r[x0_new + i] = BAR_COLOUR;
        }

        phase += BAR_PHASE_MUL;      if (phase >= BAR_PERIOD) phase -= BAR_PERIOD;
        prev_phase += BAR_PHASE_MUL; if (prev_phase >= BAR_PERIOD) prev_phase -= BAR_PERIOD;
    }
}

int main(void)
{
    u32 frame_id = 0;
    u8 status = STATUS_MARGIN_INIT;          /* the sentinel: nothing measured yet */
    u8 fault = 0;
    u8 vmargin = STATUS_MARGIN_INIT;
    unsigned prev_phase_base;
    unsigned i;

    /* 1. nothing may composite, tint, blend or mosaic the bitmap */
    REG_BLDCNT = 0; REG_BLDALPHA = 0; REG_BLDY = 0; REG_MOSAIC = 0;

    /* 2. no interrupt runs: the VBlank edge is POLLED, so nothing can preempt
     *    an update and nothing else can ever write VRAM */
    REG_IME = 0; REG_IE = 0; REG_IF = 0xFFFFu;

    /* 3. every object disabled, from whatever state a loader left behind */
    for (i = 0; i < 512u; i++) OAM[i] = 0x0200u;

    /* 4. Timer 0, free running, prescaler 1 = F/64 (GBATEK): 262 144 Hz */
    REG_TM0CNT_H = 0;
    REG_TM0CNT_L = 0;
    REG_TM0CNT_H = 0x0081u;                  /* enable | prescaler F/64 */

    crc_table_init();
    paint_background();

    /* 5. frame 0 is COMPLETE before the mode is selected, so no partially
     *    initialised picture is ever displayed */
    bar_phase_base = 0;
    prev_phase_base = 0;
    update_frame(0, status, prev_phase_base);
    REG_DISPCNT = 0x0403u;                   /* mode 3 | BG2; everything else off */

    for (;;) {
        u16 t0, t1, vc0, vc1;
        unsigned elapsed, margin;

        /* wait for the END of the visible area, then for VBlank to begin */
        while (REG_VCOUNT >= VCOUNT_VBLANK_FIRST) { }
        while (REG_VCOUNT <  VCOUNT_VBLANK_FIRST) { }

        prev_phase_base = bar_phase_base;
        frame_id = (frame_id + 1u) & 0x00FFFFFFu;        /* 24-bit modular wrap */
        bar_phase_base += 1u; if (bar_phase_base >= BAR_PERIOD) bar_phase_base = 0;

        /* STATUS(f) is snapshotted BEFORE update f, so it certifies updates
         * 0..f-1 and never f itself (§V5.33.8). */
        status = (u8)((fault ? STATUS_FAULT_MASK : 0u) | (vmargin & STATUS_MARGIN_MASK));

        vc0 = REG_VCOUNT;
        t0 = REG_TM0CNT_L;
        update_frame(frame_id, status, prev_phase_base);
        t1 = REG_TM0CNT_L;
        vc1 = REG_VCOUNT;

        elapsed = (unsigned)((u16)(t1 - t0));
        if (vc1 < vc0 || vc1 > VCOUNT_LAST || elapsed > VBLANK_TICKS) {
            fault = 1;                       /* sticky for the rest of this boot */
            vmargin = 0;
        } else {
            margin = (unsigned)(VCOUNT_LAST - vc1);
            if (margin > STATUS_MARGIN_MASK) margin = STATUS_MARGIN_MASK;
            if ((u8)margin < vmargin) vmargin = (u8)margin;   /* monotone minimum */
        }
    }
}
