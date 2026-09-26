/*
 * Open-GBP GBP-AUDIO-013 — `agb-route`, `agb-sweep`'s stimulus with its LEFT/RIGHT routing as a BUILD MODE and
 * SOUNDBIAS read three times (GitHub Issue #124, Round C). IMPLEMENTED, NOT PHYSICALLY EXECUTED.
 *
 * WHAT IT IS FOR. Two open questions, one ROM:
 *
 *   U-GBP-047  are streams A and B of an AUDIO slice the AGB's two output sides? The tone ROMs route channel 1 to
 *              BOTH sides (SOUNDCNT_L 0x1177), and A == B in every tone slice. Routed to ONE side, a stereo reading
 *              predicts one stream falls to rest; a one-channel-at-131 072-Hz reading predicts both keep carrying it.
 *   U-GBP-048  why every tone slice holds one pulse per 256 cycles when nothing we wrote set SOUNDBIAS. Three reads
 *              of the register discriminate who set it.
 *
 * THE MODE IS THE BUILD, not a key: a held key at boot would arm a capture window (the capture arms on ANY rising
 * key bit) and would spoil this state machine's run. One source, three images, ROUTE_MIX set by the Makefile:
 *
 *     route-both   0x1177  channel 1 on both sides -- `agb-sweep` BYTE FOR BYTE in every APU write (the default)
 *     route-left   0x1077  channel 1 on the LEFT only  (SOUNDCNT_L bit 12, GBATEK)
 *     route-right  0x0177  channel 1 on the RIGHT only (bit 8)
 *
 * route-both reproduces the archived stimulus exactly: everything that writes the APU -- the schedules, the state
 * machine, apu_silence, apu_apply, apu_play -- is `agb-sweep`'s text, and tests/host/test_agb_route.py requires it,
 * and requires the APU registers to hold the same words as `agb-sweep`'s after every press of the same sequences.
 *
 * THE THREE READS OF SOUNDBIAS (0x04000088):
 *
 *   E  at the ROM's ENTRY, before devkitARM's crt0: source/entry.s, which tools/gbaentry.py makes the header's entry
 *      branch land on. It stores the value and a marker in OBJ palette RAM -- crt0 clears EWRAM and IWRAM's bss but
 *      never palette RAM, and mode 3 never reads it -- then branches to crt0's start_vector.
 *   M  at main's first line, after crt0.
 *   I  after this ROM's own init (the APU silenced, the display set).
 *
 *   E != M  crt0 changed it (its disassembly shows no store to 0x088: that is a check of that reading) -- except in
 *           route-bias0200, where the stub itself writes 0x0200 between E and M: there M and I must read 0x0200,
 *           and E against M says nothing about crt0
 *   M != I  our init changed it
 *   E is what the AGB had before any code of ours ran: the BIOS, the Game Boy Player, AND the flash cart's menu,
 *           which runs before this ROM on the delivery route (HARDWARE_TESTS §V3.7) -- not separable by this ROM.
 *
 * THE READOUT is the screen before the first press: three rows, E, M and I from the top, each the value as four
 * large hex digits and its sixteen bits as cells (a lit cell is a 1, bit 15 at the left) for a frame capture. E shows
 * four dashes if the marker is absent (the stub did not run). An ORANGE vertical bar on the LEFT edge, the RIGHT edge
 * or BOTH names the build's route on every screen but the spoiled one, beside the boxes and below U-GBP-040's
 * read-back marks, in a colour no mark, box, rail or background uses. After the first press the picture is `agb-sweep`'s,
 * with the route bars.
 *
 * Everything below the readout is `agb-sweep`'s, and its reasons are written out in that ROM's source: silent until
 * the first press, a press is a key going down, no decay and no length, the two schedules and their hold, the axis on
 * screen, a spoiled run loud and sticky, and U-GBP-040's twice-applied register set with its read-back marks.
 *
 * The state machine and the picture are host-testable: AGB_IO_BASE, AGB_VRAM_BASE and AGB_PAL_BASE are overridable,
 * so tests/host/test_agb_route.py drives the real code against real buffers.
 */
typedef unsigned char  u8;
typedef unsigned short u16;
typedef unsigned int   u32;

#ifndef AGB_IO_BASE
#define AGB_IO_BASE   0x04000000u
#endif
#ifndef AGB_VRAM_BASE
#define AGB_VRAM_BASE 0x06000000u
#endif
#ifndef AGB_PAL_BASE
#define AGB_PAL_BASE  0x05000000u
#endif

#define AGB_IO16(off) (*(volatile u16 *)((unsigned long)AGB_IO_BASE + (off)))

#define REG_DISPCNT    AGB_IO16(0x000)
#define REG_VCOUNT     AGB_IO16(0x006)
#define REG_BLDCNT     AGB_IO16(0x050)
#define REG_BLDALPHA   AGB_IO16(0x052)
#define REG_BLDY       AGB_IO16(0x054)
#define REG_MOSAIC     AGB_IO16(0x04C)
#define REG_KEYINPUT   AGB_IO16(0x130)
#define REG_IE         AGB_IO16(0x200)
#define REG_IF         AGB_IO16(0x202)
#define REG_IME        AGB_IO16(0x208)
/* the APU, the same six registers agb-tone touches and no others */
#define REG_SOUND1CNT_L AGB_IO16(0x060)
#define REG_SOUND1CNT_H AGB_IO16(0x062)
#define REG_SOUND1CNT_X AGB_IO16(0x064)
#define REG_SOUNDCNT_L  AGB_IO16(0x080)
#define REG_SOUNDCNT_H  AGB_IO16(0x082)
#define REG_SOUNDCNT_X  AGB_IO16(0x084)
/* read, NEVER written: this ROM measures SOUNDBIAS, it does not set it */
#define REG_SOUNDBIAS   AGB_IO16(0x088)

#define VRAM ((volatile u16 *)(unsigned long)AGB_VRAM_BASE)

#define SCREEN_W 240u
#define SCREEN_H 160u

/* ---- §V11.3's two schedules, and NOTHING else sets a note or a level ------
 * GBATEK: f = 131072 / (2048 - n). All four (2048 - n) are powers of two, which
 * is the condition for an exact integer frequency: 1024, 256, 512, 128 ->
 * 128.0, 512.0, 256.0, 1024.0 Hz, i.e. 32, 8, 16 and 4 drained blocks per
 * period at 4 096.0 blocks/s. */
#define SWEEP_STEPS 4u
static const u16 SWEEP_FREQ_N[SWEEP_STEPS] = { 1024u, 1792u, 1536u, 1920u };
/* SOUND1CNT_H's envelope INITIAL VOLUME (bits 12-15). Step time 0, so the level
 * is set at the restart and never moves. */
static const u8 SWEEP_VOLUME[SWEEP_STEPS] = { 15u, 11u, 7u, 3u };

/* SOUND1CNT_H = volume<<12 | direction 0 | STEP TIME 0 | duty 2 (50 %) | length 0.
 * At volume 15 this is 0xF080 -- byte for byte what agb-tone wrote, so a
 * four-press A run reproduces RUN 31's register state exactly. */
#define SWEEP_CNT_H(v) ((u16)(((u16)(v) << 12) | 0x0080u))
/* SOUND1CNT_X: restart (bit 15) | n. BIT 14, THE LENGTH FLAG, IS NEVER SET. */
#define SWEEP_RESTART 0x8000u
/* SOUNDCNT_L: channel 1 on both sides, PSG master volume 7/7 -- route-both, `agb-sweep`'s word. The one-side builds
 * clear one of the two enable bits and nothing else (GBATEK: bit 8 right, bit 12 left; bits 0-2 and 4-6 the volumes) */
#ifndef ROUTE_MIX
#define ROUTE_MIX 0x1177u
#endif
#if ROUTE_MIX != 0x1177u && ROUTE_MIX != 0x1077u && ROUTE_MIX != 0x0177u
#error "ROUTE_MIX must be 0x1177 (both), 0x1077 (left) or 0x0177 (right)"
#endif
#define SWEEP_CNT_MIX ROUTE_MIX
/* SOUNDCNT_H: PSG-to-output ratio 100 % (bits 0-1 = 2); no DMA sound */
#define SWEEP_CNT_RATIO 0x0002u
/* SOUNDCNT_X: bit 7, the master enable. Written for the first time on press 1. */
#define SWEEP_MASTER_ON 0x0080u

/* ---- colours (BGR555) --------------------------------------------------- */
#define COL_BLACK   0x0000u
#define COL_RED     0x001Fu
#define COL_GREEN   0x03E0u
#define COL_BLUE    0x7C00u
#define COL_YELLOW  0x03FFu
#define COL_MAGENTA 0x7C1Fu        /* MORE THAN FOUR: agb-tone's meaning, kept */
#define COL_WHITE   0x7FFFu
#define COL_GREY    0x2108u        /* the unfilled half, and an unpressed box */
#define COL_CYAN    0x7FE0u        /* U-GBP-040's read-back marks, and nothing else */
#define COL_ORANGE  0x021Fu        /* Issue #124: the route bars, and nothing else */

/* ---- the picture's geometry --------------------------------------------
 * Four 40x96 boxes: a filled HALF is 40x48, which is the same block agb-tone
 * used for a whole box, so the half is as legible on his chain as the box was.
 * 4*40 + 3*16 = 208, centred in 240. */
#define BOX_N      4u
#define BOX_W      40u
#define BOX_H      96u
#define BOX_HALF   (BOX_H / 2u)
#define BOX_Y      32u
#define BOX_GAP    16u
#define BOX_X0     16u
#define RAIL_H     16u
#define RAIL_Y_F   0u                         /* the A / frequency rail, at the TOP */
#define RAIL_Y_V   (SCREEN_H - RAIL_H)        /* the B / amplitude rail, at the BOTTOM */
#define BAND_H     16u                        /* the spoiled-run bands */
/* U-GBP-040's read-back marks: the free band between the top rail and the boxes */
#define MARK_W     12u
#define MARK_GAP    4u
#define MARK_X0     4u
#define MARK_Y     18u

/* The GBA key bits §V11.8 reads out of the anchor: A is logical key 0 and B is
 * key 1 (gbp_input.h's descriptor, and GBP_INPUT_POLICY_DEFAULT maps the pad's
 * A and B to them). KEY_MASK is every key the keypad carries, because the
 * capture arms on ANY rising bit and this ROM must see exactly what it does. */
#define KEY_A    0x0001u
#define KEY_B    0x0002u
#define KEY_MASK 0x03FFu

enum sweep_axis { SWEEP_AXIS_NONE = 0, SWEEP_AXIS_F = 1, SWEEP_AXIS_V = 2 };

struct sweep_state {
    u32 presses;            /* key-down edges seen, whatever the key */
    u16 held;               /* the previous ACTIVE-HIGH key set */
    u8  axis;               /* enum sweep_axis: the axis this run is on */
    u8  spoiled;            /* sticky: a press that was not this run's button */
    u8  f_step;             /* 0..SWEEP_STEPS-1, HELD at the last */
    u8  v_step;
    u8  f_count;            /* presses on each axis, before the hold is applied */
    u8  v_count;
    u8  sounding;           /* 0 until the first press */
    u8  box_axis[BOX_N];    /* per press 1..4: which axis filled that box */
};

void sweep_init(struct sweep_state *s)
{
    unsigned i;
    s->presses = 0u;
    s->held = 0u;
    s->axis = (u8)SWEEP_AXIS_NONE;
    s->spoiled = 0u;
    s->f_step = 0u;
    s->v_step = 0u;
    s->f_count = 0u;
    s->v_count = 0u;
    s->sounding = 0u;
    for (i = 0; i < BOX_N; i++) s->box_axis[i] = (u8)SWEEP_AXIS_NONE;
}

/* §V11.3's hold: the index is the press ordinal on that axis minus one, and it
 * stops at the last entry. A fifth press changes nothing that is sounding. */
static u8 step_for_count(u8 count)
{
    return (u8)((count >= SWEEP_STEPS) ? (SWEEP_STEPS - 1u) : (count - 1u));
}

u16 sweep_freq_n(const struct sweep_state *s) { return SWEEP_FREQ_N[s->f_step]; }
u8  sweep_volume(const struct sweep_state *s) { return SWEEP_VOLUME[s->v_step]; }

/* The RISING edge, and only it. `keyinput` is the raw register: ACTIVE LOW.
 * Returns 1 when this sample contains at least one key going DOWN -- and the
 * caller may only touch the APU when it ALSO returns with `spoiled` clear. */
int sweep_step(struct sweep_state *s, u16 keyinput)
{
    u16 now = (u16)(~keyinput & KEY_MASK);
    u16 went_down = (u16)(now & ~s->held);
    s->held = now;
    if (!went_down) return 0;
    s->presses++;
    if (s->spoiled) return 1;                 /* already spent; nothing more changes */

    if (went_down == KEY_A) {
        if (s->axis == (u8)SWEEP_AXIS_V) { s->spoiled = 1u; return 1; }
        s->axis = (u8)SWEEP_AXIS_F;
        if (s->f_count < 0xFFu) s->f_count++;
        s->f_step = step_for_count(s->f_count);
    } else if (went_down == KEY_B) {
        if (s->axis == (u8)SWEEP_AXIS_F) { s->spoiled = 1u; return 1; }
        s->axis = (u8)SWEEP_AXIS_V;
        if (s->v_count < 0xFFu) s->v_count++;
        s->v_step = step_for_count(s->v_count);
    } else {
        /* A and B together, or any other key: the capture arms a window the
         * ingestion cannot give an axis to (§V11.8), so the run is spent. */
        s->spoiled = 1u;
        return 1;
    }
    if (s->presses <= BOX_N) s->box_axis[s->presses - 1u] = s->axis;
    s->sounding = 1u;
    return 1;
}

u16 sweep_background(const struct sweep_state *s)
{
    switch (s->presses) {
    case 0u: return COL_BLACK;
    case 1u: return COL_RED;
    case 2u: return COL_GREEN;
    case 3u: return COL_BLUE;
    case 4u: return COL_YELLOW;
    default: return COL_MAGENTA;              /* more than four, as in agb-tone */
    }
}

unsigned sweep_boxes_filled(const struct sweep_state *s)
{
    return (s->presses > BOX_N) ? BOX_N : (unsigned)s->presses;
}

#define APU_BAD_CNT_X   0x01u    /* SOUNDCNT_X   master enable did not stick */
#define APU_BAD_CNT_H   0x02u    /* SOUNDCNT_H   PSG-to-output ratio */
#define APU_BAD_CNT_L   0x04u    /* SOUNDCNT_L   the LEFT/RIGHT routing -- the hypothesis */
#define APU_BAD_1CNT_H  0x08u    /* SOUND1CNT_H  duty and envelope */

static u16 apu_marks;            /* every bit that failed on any press, kept for the screen */

static void route_bars(void);                    /* Issue #124: the build's route, drawn by sweep_paint too */

/* ---- the picture --------------------------------------------------------- */
static void fill_rect(unsigned x0, unsigned y0, unsigned w, unsigned h, u16 c)
{
    unsigned x, y;
    for (y = y0; y < y0 + h && y < SCREEN_H; y++)
        for (x = x0; x < x0 + w && x < SCREEN_W; x++)
            VRAM[y * SCREEN_W + x] = c;
}

void sweep_paint(const struct sweep_state *s)
{
    unsigned i, filled;

    if (s->spoiled) {
        /* Nothing but the bands: the run is spent and the only thing worth
         * saying is that it is. RED against WHITE because the background takes
         * red at count 1 and a single red pixel must not be able to stand for
         * this -- what identifies it is that ADJACENT BANDS DIFFER, which no
         * valid state of this ROM or of agb-tone ever produces, and white is a
         * colour the background never takes. */
        unsigned y;
        for (y = 0; y < SCREEN_H; y += BAND_H)
            fill_rect(0u, y, SCREEN_W, BAND_H, ((y / BAND_H) & 1u) ? COL_WHITE : COL_RED);
        return;
    }

    fill_rect(0u, 0u, SCREEN_W, SCREEN_H, sweep_background(s));

    /* the rail: the same UP/DOWN answer as the box halves, 240 px wide */
    if (s->axis == (u8)SWEEP_AXIS_F)
        fill_rect(0u, RAIL_Y_F, SCREEN_W, RAIL_H, COL_WHITE);
    else if (s->axis == (u8)SWEEP_AXIS_V)
        fill_rect(0u, RAIL_Y_V, SCREEN_W, RAIL_H, COL_WHITE);

    /* U-GBP-040's read-back mask, and NOTHING is drawn when it is zero: the
     * picture §V11.15.3 describes is unchanged on a healthy ROM. Four 12x12
     * marks in the free band under the top rail, one per register, lit for a
     * register that did not hold the value just written to it. */
    if (apu_marks) {
        unsigned k;
        for (k = 0; k < 4u; k++)
            if (apu_marks & (1u << k))
                fill_rect(MARK_X0 + k * (MARK_W + MARK_GAP), MARK_Y, MARK_W, MARK_W, COL_CYAN);
    }

    filled = sweep_boxes_filled(s);
    for (i = 0; i < BOX_N; i++) {
        unsigned x = BOX_X0 + i * (BOX_W + BOX_GAP);
        u8 a = (i < filled) ? s->box_axis[i] : (u8)SWEEP_AXIS_NONE;
        fill_rect(x, BOX_Y, BOX_W, BOX_HALF,
                  (a == (u8)SWEEP_AXIS_F) ? COL_WHITE : COL_GREY);
        fill_rect(x, BOX_Y + BOX_HALF, BOX_W, BOX_HALF,
                  (a == (u8)SWEEP_AXIS_V) ? COL_WHITE : COL_GREY);
    }
    route_bars();                                     /* Issue #124: the build's route, on every valid screen */
}

/* ---- Issue #124: the three reads of SOUNDBIAS, and the readout ---------------
 * entry.s stores the entry read at BIAS_STASH[0] and BIAS_MARK at BIAS_STASH[1]: OBJ palette 15, its last two
 * colours, which crt0 does not clear and mode 3 does not display. */
#define BIAS_STASH ((volatile u16 *)((unsigned long)AGB_PAL_BASE + 0x3FCu))
#define BIAS_MARK  0xB1A5u

struct bias_reads {
    u16 entry, main_, init;
    u8  entry_ok;             /* the stub ran: BIAS_STASH[1] held the marker */
};
static struct bias_reads bias;

void bias_read_entry_and_main(void)
{
    bias.main_ = REG_SOUNDBIAS;                       /* M: main's first read, before anything else of ours */
    bias.entry = BIAS_STASH[0];
    bias.entry_ok = (u8)(BIAS_STASH[1] == BIAS_MARK);
}

void bias_read_init(void) { bias.init = REG_SOUNDBIAS; }

/* A 3x5 font for 0-9, A-F and '-': row r of glyph g is bits 2..0 of GLYPH[g][r], bit 2 the left column. B and D
 * keep their right corners open, so neither reads as 8 or 0. */
#define GLYPH_DASH 16u
static const u8 GLYPH[17][5] = {
    {7, 5, 5, 5, 7}, {2, 6, 2, 2, 7}, {7, 1, 7, 4, 7}, {7, 1, 7, 1, 7}, {5, 5, 7, 1, 1}, {7, 4, 7, 1, 7},
    {7, 4, 7, 5, 7}, {7, 1, 1, 1, 1}, {7, 5, 7, 5, 7}, {7, 5, 7, 1, 7}, {7, 5, 7, 5, 5}, {6, 5, 6, 5, 6},
    {7, 4, 4, 4, 7}, {6, 5, 5, 5, 6}, {7, 4, 7, 4, 7}, {7, 4, 7, 4, 4}, {0, 0, 7, 0, 0}};

/* the readout's geometry: a digit is 3x5 cells of SCALE px; four digits a row; under them sixteen bit cells */
#define RD_SCALE   5u
#define RD_DIGIT_W (3u * RD_SCALE)
#define RD_DIGIT_H (5u * RD_SCALE)
#define RD_GAP     RD_SCALE
#define RD_X0      24u
#define RD_Y0      8u
#define RD_ROW_H   50u
#define RD_CELL_Y  (RD_DIGIT_H + 5u)
#define RD_CELL_W  11u
#define RD_CELL_H  8u
#define RD_CELL_GAP 1u
#define ROUTE_BAR_W 8u

static void draw_glyph(unsigned x0, unsigned y0, unsigned g, u16 c)
{
    unsigned r, k;
    for (r = 0; r < 5u; r++)
        for (k = 0; k < 3u; k++)
            if (GLYPH[g][r] & (4u >> k))
                fill_rect(x0 + k * RD_SCALE, y0 + r * RD_SCALE, RD_SCALE, RD_SCALE, c);
}

static void draw_value(unsigned row, u16 v, int valid)
{
    unsigned d, b, y = RD_Y0 + row * RD_ROW_H;
    for (d = 0; d < 4u; d++)
        draw_glyph(RD_X0 + d * (RD_DIGIT_W + RD_GAP), y, valid ? ((v >> (12u - 4u * d)) & 0xFu) : GLYPH_DASH,
                   COL_WHITE);
    if (!valid) return;
    for (b = 0; b < 16u; b++)                          /* bit 15 at the left, as the digits read */
        fill_rect(RD_X0 + b * (RD_CELL_W + RD_CELL_GAP), y + RD_CELL_Y, RD_CELL_W, RD_CELL_H,
                  ((v >> (15u - b)) & 1u) ? COL_WHITE : COL_GREY);
}

/* the build's route, on the edge it names: LEFT, RIGHT or both -- over the boxes' rows only, so the read-back marks
 * above them (MARK_Y .. MARK_Y + MARK_W) and the rails are never covered */
static void route_bars(void)
{
    if (ROUTE_MIX & 0x1000u) fill_rect(0u, BOX_Y, ROUTE_BAR_W, BOX_H, COL_ORANGE);
    if (ROUTE_MIX & 0x0100u) fill_rect(SCREEN_W - ROUTE_BAR_W, BOX_Y, ROUTE_BAR_W, BOX_H, COL_ORANGE);
}

void route_paint_readout(void)
{
    fill_rect(0u, 0u, SCREEN_W, SCREEN_H, COL_BLACK);
    draw_value(0u, bias.entry, bias.entry_ok);
    draw_value(1u, bias.main_, 1);
    draw_value(2u, bias.init, 1);
    route_bars();
}

/* ---- the device, which only the ROM itself touches ----------------------- */
static void apu_silence(void)
{
    /* Before the first press the APU is OFF and is SEEN to be off: the master
     * enable is cleared explicitly rather than assumed clear from reset. */
    REG_SOUNDCNT_X = 0u;
    REG_SOUND1CNT_L = 0u;
    REG_SOUND1CNT_H = 0u;
    REG_SOUND1CNT_X = 0u;
    REG_SOUNDCNT_L = 0u;
    REG_SOUNDCNT_H = 0u;
}

/* ---- U-GBP-040: THE FIRST PRESS DID NOT EMIT ----------------------------
 * sweep-0001 and agb-tone made no sound on their FIRST press and made sound on
 * every press after it -- reproduced by the Operator on his own Game Boy
 * Advance, with no GameCube involved (GBP-HW-306). The write ORDER was ruled
 * out against the vendored GBATEK: the master enable IS written first, which is
 * what it requires.
 *
 * WHAT IS DIFFERENT ABOUT THE FIRST PRESS, and it is the only thing: SOUNDCNT_X
 * bit 7 goes 0 -> 1 there and is already 1 on every later press. GBATEK: "while
 * Bit 7 is cleared ... all PSG registers at 4000060h..4000081h are reset to zero
 * (and must be re-initialized after re-enabling sound)".
 *
 * A HYPOTHESIS, LABELLED AS ONE AND NOT PROMOTED BY THIS ROM: if the APU takes
 * any time at all to come out of that reset, the writes immediately following
 * the enable land while it is still held -- and SOUNDCNT_L (0x4000080) is INSIDE
 * that range and carries the channel's LEFT/RIGHT routing. A channel that
 * triggers with SOUNDCNT_L still zero runs and reaches neither output, which is
 * exactly "the note is playing and nothing is heard".
 *
 * THE FIX AND THE MEASUREMENT ARE THE SAME TWO LINES, so one flash settles both:
 *
 *   THE FIX          every press applies the register set TWICE. Identical on
 *                    every press, so no press behaves differently from another,
 *                    and the second pass lands after any reset has been
 *                    released. Idempotent: presses 2-4 were already correct.
 *   THE MEASUREMENT  between the two passes the R/W registers are READ BACK. A
 *                    bit is set for each one that did not hold the value just
 *                    written, and that mask is shown on screen (apu_marks).
 *                    If the mask comes up with SOUNDCNT_L's bit on the first
 *                    press and clear on the others, the hypothesis above is
 *                    measured rather than argued.
 *
 * SOUND1CNT_X is NOT read back: its restart bit reads as 0 and its low bits are
 * write-only, so a mismatch there would mean nothing. SOUND1CNT_H is compared
 * only above bit 6, because bits 0-5 are the write-only length.
 */
static u16 apu_apply(u16 n, u8 volume)
{
    u16 bad = 0u;
    /* The master enable must be set before any channel register is written:
     * with SOUNDCNT_X bit 7 clear the APU ignores writes (GBATEK). */
    REG_SOUNDCNT_X = SWEEP_MASTER_ON;
    REG_SOUNDCNT_H = SWEEP_CNT_RATIO;
    REG_SOUNDCNT_L = SWEEP_CNT_MIX;
    REG_SOUND1CNT_L = 0u;                        /* no sweep: the note must not glide */
    REG_SOUND1CNT_H = SWEEP_CNT_H(volume);
    REG_SOUND1CNT_X = (u16)(SWEEP_RESTART | n);  /* restart, length flag CLEAR */
    if ((REG_SOUNDCNT_X & SWEEP_MASTER_ON) != SWEEP_MASTER_ON) bad |= APU_BAD_CNT_X;
    if (REG_SOUNDCNT_H != SWEEP_CNT_RATIO)                     bad |= APU_BAD_CNT_H;
    if (REG_SOUNDCNT_L != SWEEP_CNT_MIX)                       bad |= APU_BAD_CNT_L;
    if ((REG_SOUND1CNT_H & 0xFFC0u) != (u16)(SWEEP_CNT_H(volume) & 0xFFC0u))
        bad |= APU_BAD_1CNT_H;
    return bad;
}

static void apu_play(u16 n, u8 volume)
{
    apu_marks = (u16)(apu_marks | apu_apply(n, volume));
    (void)apu_apply(n, volume);      /* the same writes again, unconditionally */
}

static void wait_vblank(void)
{
    while (REG_VCOUNT >= SCREEN_H) { }
    while (REG_VCOUNT < SCREEN_H) { }
}

/* the boot, host-testable: main's first read, then `agb-sweep`'s init, then the read after it and the readout */
void route_boot(struct sweep_state *st)
{
    bias_read_entry_and_main();                  /* M, and E from the stub's stash */

    /* nothing composites, tints, blends or mosaics the bitmap */
    REG_BLDCNT = 0; REG_BLDALPHA = 0; REG_BLDY = 0; REG_MOSAIC = 0;
    /* no interrupt runs: the frame edge is POLLED, so nothing preempts a write */
    REG_IME = 0; REG_IE = 0; REG_IF = 0xFFFFu;

    sweep_init(st);
    apu_silence();                               /* REQUIREMENT 1 */

    REG_DISPCNT = 0x0403u;                       /* mode 3, BG2 on */
    bias_read_init();                            /* I: after this ROM's own init */
    route_paint_readout();                       /* count 0: the three reads, and the route */
}

int main(void)
{
    struct sweep_state st;

    route_boot(&st);

    /* Repainted ONLY on a press -- four or five frames out of a session's
     * thousand -- so nothing competes with the capture for the rest of the run.
     * A full repaint does not fit in one VBlank and overruns into that one
     * frame's visible period; that is accepted and named rather than
     * discovered, as it was for agb-tone: a single torn frame is invisible to a
     * person and §V11's AUDIO window does not read VRAM at all. */
    for (;;) {
        wait_vblank();
        if (sweep_step(&st, REG_KEYINPUT)) {     /* REQUIREMENT 2: the key-DOWN edge */
            if (!st.spoiled)
                apu_play(sweep_freq_n(&st), sweep_volume(&st));
            sweep_paint(&st);                    /* and he can see WHICH AXIS */
        }
    }
}
