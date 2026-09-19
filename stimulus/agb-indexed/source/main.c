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

/* ---- the self-validation verdict, extracted so it can be DRIVEN -----------
 *
 * The validator is the authority on whether this stimulus is usable, so it must
 * be adversarially testable rather than buried in main(). Extracting it changes
 * no behaviour: main() is still the only caller, nothing here reads a clock,
 * and the predicate is character for character the one indexed-0001 shipped.
 *
 * FAULT is STICKY for the rest of the boot. VMARGIN is a MONOTONE MINIMUM of
 * the observed margins, and its initial 0x7F is a SENTINEL: it means "nothing
 * measured yet", and because 0x7F is also the largest representable margin the
 * first real measurement can only lower it. */
struct agb_status { u8 fault; u8 vmargin; };

static void status_measure(struct agb_status *s, u16 vc0, u16 vc1, unsigned elapsed)
{
    if (vc1 < vc0 || vc1 > VCOUNT_LAST || elapsed > VBLANK_TICKS) {
        s->fault = 1;                        /* sticky for the rest of this boot */
        s->vmargin = 0;
    } else {
        unsigned margin = (unsigned)(VCOUNT_LAST - vc1);
        if (margin > STATUS_MARGIN_MASK) margin = STATUS_MARGIN_MASK;
        if ((u8)margin < s->vmargin) s->vmargin = (u8)margin;   /* monotone minimum */
    }
}

static u8 status_byte(const struct agb_status *s)
{
    return (u8)((s->fault ? STATUS_FAULT_MASK : 0u) | (s->vmargin & STATUS_MARGIN_MASK));
}

/* ---- PREPARE / PUBLISH: the correction of indexed-0001 (§V5.41) -----------
 *
 * indexed-0001 wrote the whole 240x160 picture straight into VRAM inside what
 * was supposed to be one VBlank. The first physical run measured what that
 * really costs: the write front advanced 9 blocks per captured GBP frame, so a
 * full image took 4.44 AGB frames ~ 1 248 000 cycles -- **14.9x the 83 776-cycle
 * VBlank** -- and roughly 63 cycles per VRAM store, because the loop was
 * executing from CARTRIDGE ROM at the reset wait states and instruction FETCH,
 * not the store, dominated. FAULT was set on the very first update and stayed
 * sticky, and the GBP saw a progressive top-down wipe: 83.3 % of captured
 * frames carried two FRAME_IDs (GBP-HW-153...159).
 *
 * The wire format is UNCHANGED. What changed is WHEN each word is written:
 *
 *   PREPARE   during the VISIBLE period, into IWRAM. CRC, bit packing, symbol
 *             selection and the bar arithmetic all happen here, where taking a
 *             whole frame costs nothing and no VRAM byte is touched.
 *   PUBLISH   during VBlank only, from IWRAM, by DMA. No computation, no
 *             function call, no division: a copy of an image that already
 *             exists.
 *
 * The published spans are widened to x = 0..55 and x = 184..239 so both are
 * 4-byte aligned and can go as 32-bit DMA. That adds the FLAG column and the
 * three GUARD columns to every frame's publication -- all constants, so not one
 * wire value changes -- and it removes the odd-alignment that would have forced
 * 16-bit transfers.
 *
 * STATUS is still snapshotted BEFORE the frame it travels with, so it certifies
 * updates through f-1 and never f itself, and the snapshot is immutable for all
 * 40 blocks and both diagnostic copies of that frame (§V5.33.8). */
#define PUB_L_X0   0u                    /* FLAG + STRIP-L + GUARD_A */
#define PUB_L_W    56u
#define PUB_R_X0   184u                  /* GUARD_B + STRIP-R + GUARD_C */
#define PUB_R_W    56u
#define BAR_W      (CELL * BAR_CELLS)

/* In IWRAM by construction: .bss is at 0x03000000 on this target. */
static u16 pub_l[BLOCKS][2][PUB_L_W];
static u16 pub_r[BLOCKS][2][PUB_R_W];
static u16 pub_erase[BLOCKS][BAR_W];
static u8  pub_x0_old[BLOCKS];
static u8  pub_x0_new[BLOCKS];

/* ---- the per-frame update, split in two ---------------------------------- */
/* barpos(f,b) = (f + 8*b) mod 31, kept DIVISION-FREE: the phase for block 0 is
 * carried in a counter that is incremented and conditionally reduced, and each
 * block adds 8 with the same compare-and-subtract. */
static unsigned bar_phase_base;      /* (frame_id mod 31) */

/* PREPARE. Visible period. Produces exactly the words indexed-0001 produced,
 * into IWRAM instead of VRAM: same CRC, same bit order, same symbols, same bar
 * arithmetic, same complement rule. Not one wire value differs.
 *
 * ---- WHY THIS IS IN IWRAM TOO (indexed-0003, §V5.42) ---------------------
 *
 * indexed-0002 moved PUBLISH into IWRAM and left PREPARE in cartridge ROM. The
 * second physical run measured what that costs. The loop below waits like this:
 *
 *     while (VCOUNT >= 160) { }    wait until NOT in VBlank
 *     while (VCOUNT <  160) { }    wait until VBlank starts
 *
 * so if PREPARE returns while VCOUNT is still inside a VBlank, that VBlank is
 * skipped entirely and the publication lands in the NEXT one. Publication ends
 * at VCOUNT 203 (VMARGIN 24, measured on all 81 840 strips), leaving 185 lines
 * = 227 920 cycles before the next VBlank. From ROM, PREPARE did not fit:
 * every single FRAME_ID was published twice, 1022 of 1022, perfectly regular,
 * which bounds it at 227 920 <= T < 508 816 cycles -- never 1:1, never 3:1
 * (GBP-HW-164, GBP-HW-165).
 *
 * 195 ARM instructions over ~8 640 symbol stores at ROM wait states is ~253 000
 * cycles; the same code fetched from IWRAM is ~94 000, about 41 % of the
 * budget. The work is not reduced and not one wire value changes — only where
 * the instructions are fetched from. */
__attribute__((section(".iwram"), noinline))
static void prepare_frame(u32 frame_id, u8 status, unsigned prev_phase_base)
{
    u8 bits[STRIP_BITS];
    const u8 crc_id = crc_after_id(frame_id);
    unsigned b;
    unsigned phase = bar_phase_base;
    unsigned prev_phase = prev_phase_base;

    for (b = 0; b < BLOCKS; b++) {
        const u8 crc = crc_finish(crc_id, b, status);
        unsigned i, inv;
        unsigned x0_new = CONTENT_X0 + CELL * phase;
        unsigned x0_old = CONTENT_X0 + CELL * prev_phase;

        strip_word(bits, frame_id, b, status, crc);

        for (inv = 0; inv < 2u; inv++) {
            u16 *l = pub_l[b][inv];
            u16 *r = pub_r[b][inv];
            /* the constant columns travel with the span so the DMA stays aligned */
            l[X_FLAG - PUB_L_X0]    = SYM_FLAG;
            l[X_GUARD_A - PUB_L_X0] = SYM_GUARD;
            r[X_GUARD_B - PUB_R_X0] = SYM_GUARD;
            r[X_GUARD_C - PUB_R_X0] = SYM_GUARD;
            /* STRIP-L: plain on rows 0/2, complemented on rows 1/3 */
            for (i = 0; i < STRIP_BITS; i++) {
                const unsigned v = (unsigned)bits[i] ^ inv;
                l[STRIP_L_X0 - PUB_L_X0 + i] = v ? SYM_ONE : SYM_ZERO;
            }
            /* STRIP-R: reversed, and complemented on rows 0/2 (not 1/3) */
            for (i = 0; i < STRIP_BITS; i++) {
                const unsigned v = (unsigned)bits[STRIP_BITS - 1u - i] ^ (inv ^ 1u);
                r[STRIP_R_X0 - PUB_R_X0 + i] = v ? SYM_ONE : SYM_ZERO;
            }
        }
        /* the bar erase pattern. background_at() depends on y only through
         * (y >> 2), and every row of block b has y >> 2 == b, so ONE pattern
         * serves all four rows of the block. */
        for (i = 0; i < BAR_W; i++)
            pub_erase[b][i] = background_at(x0_old + i, b * LINES_PER_BLOCK);
        pub_x0_old[b] = (u8)x0_old;
        pub_x0_new[b] = (u8)x0_new;

        phase += BAR_PHASE_MUL;      if (phase >= BAR_PERIOD) phase -= BAR_PERIOD;
        prev_phase += BAR_PHASE_MUL; if (prev_phase >= BAR_PERIOD) prev_phase -= BAR_PERIOD;
    }
}

/* PUBLISH. VBlank only, and the whole of the VBlank path. Runs from IWRAM, so
 * instruction fetch is 0-wait rather than the cartridge wait states that made
 * indexed-0001 cost ~63 cycles per store. It computes nothing: two aligned
 * 32-bit DMA bursts per row out of IWRAM, then the 16 bar words. No division,
 * no call, no clock read, no branch on anything measured. */
/* One aligned 32-bit burst, IWRAM -> VRAM.
 *
 * The host harness has no DMA controller, so there it performs the same copy
 * directly. That is deliberate: a publication the host cannot execute would
 * make the 38 400-word model-equality gate vacuous, and that gate is the only
 * thing standing between "the wire format is unchanged" and a claim. */
static void pub_copy32(volatile u16 *dst, const u16 *src, unsigned words)
{
#ifdef AGB_HOST_TEST
    unsigned i;
    for (i = 0; i < words; i++) dst[i] = src[i];
#else
    REG_DMA3SAD = (u32)(unsigned long)src;
    REG_DMA3DAD = (u32)(unsigned long)dst;
    /* >> 1, never / 2: ARM7TDMI has no divide instruction and the no-division
     * rule is enforced textually, so the VBlank path states the shift it means. */
    REG_DMA3CNT = 0x84000000u | (words >> 1);      /* enable | 32-bit */
#endif
}

__attribute__((section(".iwram"), noinline))
static void publish_frame(void)
{
    unsigned b;
    for (b = 0; b < BLOCKS; b++) {
        const unsigned xo = pub_x0_old[b], xn = pub_x0_new[b];
        const u16 *er = pub_erase[b];
        unsigned row;
        for (row = 0; row < LINES_PER_BLOCK; row++) {
            volatile u16 *v = VRAM + (b * LINES_PER_BLOCK + row) * SCREEN_W;
            const unsigned inv = (row & 1u);
            unsigned i;
            pub_copy32(v + PUB_L_X0, pub_l[b][inv], PUB_L_W);
            pub_copy32(v + PUB_R_X0, pub_r[b][inv], PUB_R_W);
            for (i = 0; i < BAR_W; i++) v[xo + i] = er[i];
            for (i = 0; i < BAR_W; i++) v[xn + i] = BAR_COLOUR;
        }
    }
}

int main(void)
{
    u32 frame_id = 0;
    u8 status = STATUS_MARGIN_INIT;          /* the sentinel: nothing measured yet */
    struct agb_status st = { 0u, STATUS_MARGIN_INIT };
    unsigned prev_phase_base;
    unsigned i;

    /* 1. nothing may composite, tint, blend or mosaic the bitmap */
    REG_BLDCNT = 0; REG_BLDALPHA = 0; REG_BLDY = 0; REG_MOSAIC = 0;

    /* 2. no interrupt runs: the VBlank edge is POLLED, so nothing can preempt
     *    an update and nothing else can ever write VRAM */
    REG_IME = 0; REG_IE = 0; REG_IF = 0xFFFFu;

    /* 3. every object disabled, from whatever state a loader left behind */
    for (i = 0; i < 512u; i++) OAM[i] = 0x0200u;

    /* 3b. game-pak wait states and prefetch. indexed-0001 never touched this,
     *     so the PREPARE work ran at the reset values (4/2, no prefetch). It is
     *     set here for the visible-period path only; the VBlank path now runs
     *     from IWRAM and does not depend on it. */
    REG_WAITCNT = 0x4317u;

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
    prepare_frame(0, status, prev_phase_base);
    publish_frame();
    REG_DISPCNT = 0x0403u;                   /* mode 3 | BG2; everything else off */

    for (;;) {
        u16 t0, t1, vc0, vc1;
        unsigned elapsed;

        prev_phase_base = bar_phase_base;
        frame_id = (frame_id + 1u) & 0x00FFFFFFu;        /* 24-bit modular wrap */
        bar_phase_base += 1u; if (bar_phase_base >= BAR_PERIOD) bar_phase_base = 0;

        /* STATUS(f) is snapshotted BEFORE frame f is prepared, so it certifies
         * publications 0..f-1 and never f itself (§V5.33.8), and it is immutable
         * for all 40 blocks and both diagnostic copies of this frame. */
        status = status_byte(&st);

        /* PREPARE, in the VISIBLE period. It writes no VRAM byte, so it can
         * never tear the picture — but it must still FINISH before the next
         * VBlank begins, or the wait below skips that VBlank and the same
         * FRAME_ID is published for two source refreshes (GBP-HW-165). */
        prepare_frame(frame_id, status, prev_phase_base);

        /* wait for the END of the visible area, then for VBlank to begin */
        while (REG_VCOUNT >= VCOUNT_VBLANK_FIRST) { }
        while (REG_VCOUNT <  VCOUNT_VBLANK_FIRST) { }

        /* PUBLISH. This, and only this, is what the budget is measured over. */
        vc0 = REG_VCOUNT;
        t0 = REG_TM0CNT_L;
        publish_frame();
        t1 = REG_TM0CNT_L;
        vc1 = REG_VCOUNT;

        elapsed = (unsigned)((u16)(t1 - t0));
        status_measure(&st, vc0, vc1, elapsed);
    }
}
