/*
 * Open-GBP GBP-VIDEO-003 controlled colour stimulus — AGB Mode 3 colour bars.
 *
 * THIS PROGRAM IS A MEASURING INSTRUMENT, NOT A DEMO. Everything it does is
 * chosen so that the value of every pixel on the AGB screen is known by
 * construction, and so that nothing it writes can be confused with the thing
 * GBP-VIDEO-003 is trying to measure (HARDWARE_TESTS §V3.3, §V3.4, §V3.6).
 *
 * The image: 240 x 160, video mode 3 (16-bit direct colour framebuffer, no
 * palette, no tiles, no scaling), eight vertical bars of exactly 30 pixels,
 * all 160 lines identical:
 *
 *     x 000..029  0x0000     popcount 0    zero reference
 *     x 030..059  0x001F     popcount 5    one whole 5-bit group
 *     x 060..089  0x03E0     popcount 5    the next whole group
 *     x 090..119  0x7C00     popcount 5    the last whole group
 *     x 120..149  0x7FFF     popcount 15   all-bits reference
 *     x 150..179  0x0001     popcount 1    the LOW bit of the first group
 *     x 180..209  0x0020     popcount 1    the LOW bit of the second group
 *     x 210..239  0x0400     popcount 1    the LOW bit of the third group
 *
 * In the AGB's own documented framebuffer layout (BGR555: bits 0-4 R, 5-9 G,
 * 10-14 B) those are black, red, green, blue, white and the least significant
 * bit of red, of green and of blue. That sentence describes WHAT THIS ROM
 * WRITES. It says nothing about which bits the Game Boy Player then presents to
 * the GameCube, which is the open question (U-GBP-011): this source must never
 * be read as naming a GBP bit.
 *
 * Why the low-bit bars exist: an intra-group bit reversal maps 0x001F to
 * 0x001F, so full-scale primaries alone cannot falsify it. 0x0001 becomes
 * 0x0010 under that transformation, and becomes 0x0400 under a group exchange.
 * Why 0x0000 and 0x7FFF exist: they are fixed points of every PERMUTATION of
 * the 15 colour bits, so they cannot single out one of those - which is exactly
 * what makes them the controls for the failures a permutation cannot explain
 * (complement, stuck bits, fill). A byte swap is NOT such a permutation: the
 * high byte of the 16-bit word holds only seven colour bits, so 0x7FFF becomes
 * 0x7F7F and one bit is lost. The white bar therefore also discriminates the
 * byte-swap family, which is a property of the word, not of the colour bits.
 *
 * BIT 15 IS NEVER SET. Every value above has bit 15 = 0, so any bit 15 that
 * appears in the GBP's VIDEO window demonstrably did not come from the colour
 * this ROM wrote (§V3.4).
 *
 * No interrupts, no sprites, no blending, no mosaic, no palette, no input, no
 * animation, no library: the framebuffer is written once and the CPU then spins
 * forever. A second write would make "the screen is static" an assumption
 * instead of a property of the program.
 */

#define REG_DISPCNT (*(volatile unsigned short *)0x04000000)
#define REG_BLDCNT  (*(volatile unsigned short *)0x04000050)
#define REG_BLDALPHA (*(volatile unsigned short *)0x04000052)
#define REG_BLDY    (*(volatile unsigned short *)0x04000054)
#define REG_MOSAIC  (*(volatile unsigned short *)0x0400004C)
#define REG_IE      (*(volatile unsigned short *)0x04000200)
#define REG_IF      (*(volatile unsigned short *)0x04000202)
#define REG_IME     (*(volatile unsigned short *)0x04000208)

#define VRAM        ((volatile unsigned short *)0x06000000)
#define OAM         ((volatile unsigned short *)0x07000000)

#define SCREEN_W 240
#define SCREEN_H 160
#define BAR_W    30
#define BARS     8

/* The eight stimulus values, in bar order, left to right. The analyser holds
 * the same eight; the GameCube probe holds NONE of them (§V3.11, §26 of the
 * implementation contract): a runtime that recognised these values would be
 * deciding the experiment's question with the experiment's answer. */
static const unsigned short bar_value[BARS] = {
    0x0000u, 0x001Fu, 0x03E0u, 0x7C00u, 0x7FFFu, 0x0001u, 0x0020u, 0x0400u
};

int main(void)
{
    int x, y, i;

    /* 1. Nothing may composite, tint, blend or mosaic the bitmap. These are
     *    the registers that could, and they are cleared before the mode is
     *    selected so that no frame is ever displayed under a stale setting. */
    REG_BLDCNT = 0x0000u;
    REG_BLDALPHA = 0x0000u;
    REG_BLDY = 0x0000u;
    REG_MOSAIC = 0x0000u;

    /* 2. No interrupt may run: nothing else in this program writes VRAM, and a
     *    handler that did would break the one property the experiment needs. */
    REG_IME = 0x0000u;
    REG_IE = 0x0000u;
    REG_IF = 0xFFFFu;                 /* acknowledge anything already latched */

    /* 3. Every OAM halfword is written with 0x0200, not with zero. In attribute
     *    0 of an object that is rotation/scaling flag = 0 and OBJ-disable = 1,
     *    which is the documented "this object is hidden" encoding; the same
     *    value lands in attributes 1 and 2 and in the affine parameters, where
     *    it is harmless precisely because every object is disabled and OBJ is
     *    off in DISPCNT. 512 halfwords is the whole 1 KiB of OAM. The point is
     *    that no sprite can be drawn over the bars from whatever state a loader
     *    left behind. */
    for (i = 0; i < 512; i++) OAM[i] = 0x0200u;   /* attr0: OBJ disabled */

    /* 4. The framebuffer, written exactly once. Row by row so the write order
     *    is the raster order the GBP will later stream. */
    for (y = 0; y < SCREEN_H; y++) {
        volatile unsigned short *row = VRAM + (unsigned)y * SCREEN_W;
        for (x = 0; x < SCREEN_W; x++) row[x] = bar_value[x / BAR_W];
    }

    /* 5. Mode 3, BG2 only. Selected AFTER the framebuffer is complete, so the
     *    first frame the AGB presents is already the final image and no partial
     *    fill can ever reach the GBP. 0x0403 = mode 3 (bits 0-2) | BG2 (bit 10);
     *    every other bit - OBJ, BG0/1/3, windows, forced blank - stays 0. */
    REG_DISPCNT = 0x0403u;

    /* 6. Stop. No VBlank wait is needed because nothing changes from here, and
     *    nothing after this line touches VRAM, a register or an interrupt. */
    for (;;) {
        /* deliberately empty */
    }
}
