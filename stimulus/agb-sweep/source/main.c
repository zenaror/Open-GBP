/*
 * Open-GBP GBP-AUDIO-003 — `agb-sweep`, the TWO-AXIS stimulus of
 * HARDWARE_TESTS §V11 (GitHub Issue #70). IMPLEMENTED, NOT PHYSICALLY EXECUTED.
 *
 * WHAT IT IS FOR. §V11 asks three questions and decides which one a run is
 * asking from the button that was pressed, not from a declaration:
 *
 *     the pad's A -> the FREQUENCY schedule   128.0 -> 512.0 -> 256.0 -> 1024.0 Hz
 *     the pad's B -> the AMPLITUDE schedule   volume 15 -> 11 -> 7 -> 3
 *
 * Both HOLD at their last entry, and each starts where the other run needs it
 * held: a run of four B presses never leaves 128.0 Hz, a run of four A presses
 * never leaves volume 15. So ONE ROM serves both experiments and the Operator's
 * button decides which — no mode, no configuration, no second flash.
 *
 * WHY THE SCREEN CARRIES THE AXIS AND NOT ONLY THE COUNT. §V11.8's ingestion
 * REFUSES a window whose key does not match the schedule it is read under —
 * correctly, loudly, and AFTER THE TRIP. A and B are adjacent on the pad and
 * the consequence is silent at the time, so the Operator has to be able to see
 * at the FIRST press that he is running the experiment he was asked to run.
 * A count cannot tell him that; a filled half can.
 *
 *     the background       the press COUNT, as agb-tone did it (§V11.2)
 *     a box's filled half  WHICH AXIS that press advanced -- UPPER for A, LOWER for B
 *     the rail             the same up/down answer, 240 px wide, for across the room
 *
 * He is told "press B, the boxes must fill on the LOWER half". He does not have
 * to know what upper and lower MEAN: he has to see that what happened matches
 * what he was told, which is a check he can perform without interpreting
 * anything.
 *
 * THE TWO WAYS A RUN IS SPOILED, AND THEY GET DIFFERENT SIGNALS.
 *
 *   MORE THAN FOUR PRESSES -> the background turns MAGENTA, which is exactly
 *     what it meant in `agb-tone`. The fifth window is refused by the capture
 *     (arm_refused_full) and both schedules HOLD, so nothing that is sounding
 *     changes: he over-pressed, and the four captured windows are still good.
 *     Reusing the colour he has already seen is worth more than a fresh one.
 *
 *   A PRESS THAT IS NOT THE RUN'S BUTTON -> RED AND WHITE BANDS across the
 *     whole screen, and they STICK. This is worse than a fifth press: the
 *     capture arms a window for ANY rising bit, so a stray press consumes one
 *     of the four AND makes §V11.8's derive_schedule return MIXED or UNKNOWN,
 *     which refuses the whole run. A striped screen is not a colour this ROM
 *     or `agb-tone` produces in any valid state, so it cannot be misread as
 *     one, and nothing else is drawn over it: at that point the run is spent
 *     and the only thing worth communicating is THAT it is spent.
 *
 *   ANY key that is not exactly A or exactly B counts as such a press --
 *     START, the D-pad, L, R, or A and B together -- because every one of them
 *     arms a window the ingestion will refuse (§V11.8: keys that are not
 *     0x0001 or 0x0002 give no axis at all).
 *
 * THE THREE REQUIREMENTS INHERITED FROM `agb-tone`, unchanged and for the same
 * reasons, which are written out in that ROM's source:
 *
 *   1. SILENT UNTIL THE FIRST PRESS. §V11's control window is armed before any
 *      press and must stay a resting-state observation, so the master enable
 *      (SOUNDCNT_X bit 7) is written for the FIRST TIME on the first press and
 *      every APU register is explicitly cleared before it.
 *   2. A PRESS IS A KEY GOING DOWN. The capture arms on the RISING edge of the
 *      word; KEYINPUT is active LOW, so the same instant is a bit going 1 -> 0.
 *      Counting the other edge would make his count and the log's disagree for
 *      a reason with nothing to do with the input path.
 *   3. NO DECAY, NO LENGTH. Envelope step time 0 and the length flag never set:
 *      a level that fell inside a window would change the very bytes §V11.4
 *      reads the duty from.
 *
 * ONCE SPOILED, THE AUDIO FREEZES. After a stray press the ROM stops touching
 * the APU: the run is refused at ingestion whatever happens next, and the
 * quietest possible behaviour is the one that adds nothing further to explain.
 *
 * The state machine and the picture are host-testable: AGB_IO_BASE and
 * AGB_VRAM_BASE are overridable exactly as `agb-tone` and `agb-indexed` do it,
 * so tests/host/test_agb_sweep.py drives the real code against real buffers.
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
/* SOUNDCNT_L: channel 1 on both sides, PSG master volume 7/7 */
#define SWEEP_CNT_MIX 0x1177u
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

int main(void)
{
    struct sweep_state st;

    /* nothing composites, tints, blends or mosaics the bitmap */
    REG_BLDCNT = 0; REG_BLDALPHA = 0; REG_BLDY = 0; REG_MOSAIC = 0;
    /* no interrupt runs: the frame edge is POLLED, so nothing preempts a write */
    REG_IME = 0; REG_IE = 0; REG_IF = 0xFFFFu;

    sweep_init(&st);
    apu_silence();                               /* REQUIREMENT 1 */

    REG_DISPCNT = 0x0403u;                       /* mode 3, BG2 on */
    sweep_paint(&st);                            /* count 0: black, four grey boxes */

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
