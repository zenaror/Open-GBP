/*
 * Open-GBP GBP-AUDIO-002 — `agb-tone`, the two-frequency stimulus of
 * HARDWARE_TESTS §V9 (GitHub Issue #65). IMPLEMENTED, NOT PHYSICALLY EXECUTED.
 *
 * WHAT IT IS FOR. §V9 asks one question — does the byte-period of the AUDIO
 * window follow the note? — and answers it by a RATIO between two windows of
 * the SAME run, so the region's unknown sample rate cancels. This ROM supplies
 * the two notes:
 *
 *     press 1 -> F1 (n = 1024, 128.0 Hz)      press 2 -> F2 (n = 1792, 512.0 Hz)
 *     press 3 -> F1                            press 4 -> F2
 *
 * THE ALTERNATION IS A DECISION AGAINST U-GBP-038, not a pattern chosen for
 * neatness: RUN 30's first press changed nothing at all, and a sequence that
 * spent press 1 on F1 and never returned to it would lose F1 entirely if that
 * repeats. Alternating, presses 2-4 alone still carry both notes.
 *
 * THREE REQUIREMENTS THAT ARE EASY TO GET WRONG, and each has its own reason:
 *
 * 1. SILENT UNTIL THE FIRST PRESS. §V9 arms the capture's CONTROL window
 *    before any press, and RUN 30 showed the AUDIO window is NOT silent at
 *    rest (GBP-HW-288). If this ROM emitted from reset, that control would
 *    stop being a resting-state observation and the free comparison against
 *    RUN 30's control would be lost. So the master enable (SOUNDCNT_X bit 7)
 *    is written for the FIRST TIME on the first press, and nothing before it
 *    touches the APU except to make sure it is OFF.
 *
 * 2. A PRESS IS A KEY GOING DOWN, NOT A CHANGE. One press produces TWO events
 *    in the capture's KEY record -- down and up -- and the capture arms on the
 *    RISING edge (the word gaining a bit, Issue #59). The AGB sees the mirror
 *    of that: KEYINPUT is active-LOW, so the same instant is a KEYINPUT bit
 *    going 1 -> 0. This ROM advances on exactly that edge and on no other. If
 *    it counted the other edge, the Operator's count and the log's would
 *    disagree for a reason that has nothing to do with the input path, and
 *    §V9.6's cross-check would fire falsely the first time it is ever used.
 *
 * 3. THE COUNTER IS A DELIVERABLE. It is the Operator's half of §V9.6's two
 *    independent counts of the same number, and it has to survive a cheap
 *    RCA->HDMI converter at the Game Boy's native resolution. So it is FOUR
 *    40x48 boxes on a 240x160 screen -- a fifth of the width each -- plus a
 *    whole-screen background colour that changes with the count. Two readings
 *    of the same number, and a fifth press turns the background MAGENTA, which
 *    says "more than four" at a glance.
 *
 * WHAT IS DELIBERATELY DIFFERENT FROM THE CHECKER (§V8.6, PHASE6_ENTRY §2):
 *   - the envelope STEP TIME is 0, so the volume never decays. A level that
 *     fell during a window would change the very bytes the period is read from.
 *   - the LENGTH FLAG is never set, so nothing stops the tone but the next
 *     press. The checker's stop cleared that flag and left the channel running
 *     at 64 Hz; here there is nothing to clear.
 *   - SOUNDCNT_H IS WRITTEN. The checker never touched it, which is why §V8.6
 *     had to name the PSG-to-output ratio an UNKNOWN. This ROM sets it to
 *     100 %, so that unknown does not ride along into §V9's run.
 *
 * The rendering and the state machine are host-testable: AGB_IO_BASE and
 * AGB_VRAM_BASE are overridable, exactly as agb-indexed does it, so
 * tests/unit/test_agb_tone.c drives the real code against real buffers.
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
#define REG_DISPSTAT   AGB_IO16(0x004)
#define REG_VCOUNT     AGB_IO16(0x006)
#define REG_BLDCNT     AGB_IO16(0x050)
#define REG_BLDALPHA   AGB_IO16(0x052)
#define REG_BLDY       AGB_IO16(0x054)
#define REG_MOSAIC     AGB_IO16(0x04C)
#define REG_KEYINPUT   AGB_IO16(0x130)
#define REG_IE         AGB_IO16(0x200)
#define REG_IF         AGB_IO16(0x202)
#define REG_IME        AGB_IO16(0x208)
/* the APU, all six registers this ROM touches and no others */
#define REG_SOUND1CNT_L AGB_IO16(0x060)
#define REG_SOUND1CNT_H AGB_IO16(0x062)
#define REG_SOUND1CNT_X AGB_IO16(0x064)
#define REG_SOUNDCNT_L  AGB_IO16(0x080)
#define REG_SOUNDCNT_H  AGB_IO16(0x082)
#define REG_SOUNDCNT_X  AGB_IO16(0x084)

#define VRAM ((volatile u16 *)(unsigned long)AGB_VRAM_BASE)

#define SCREEN_W 240u
#define SCREEN_H 160u

/* ---- §V9.3.2's two notes, and NOTHING else may set the frequency ---------
 * GBATEK: f = 131072 / (2048 - n). Both (2048 - n) are powers of two, which is
 * the condition for an exact integer frequency, and both differ from the
 * resting 256-byte wave RUN 30 measured. */
#define TONE_N1 1024u          /* 2048-1024 = 1024 -> 128.0 Hz exactly */
#define TONE_N2 1792u          /* 2048-1792 =  256 -> 512.0 Hz exactly */

/* SOUND1CNT_H: initial volume 15, direction 0, STEP TIME 0 (no decay at all),
 * duty 2 = 50 %, length data 0. Written once per press and never varied. */
#define TONE_CNT_H 0xF080u
/* SOUND1CNT_X: restart (bit 15) | n. BIT 14, THE LENGTH FLAG, IS NEVER SET. */
#define TONE_RESTART 0x8000u
/* SOUNDCNT_L: channel 1 on both sides, PSG master volume 7/7 */
#define TONE_CNT_MIX 0x1177u
/* SOUNDCNT_H: PSG-to-output ratio 100 % (bits 0-1 = 2); no DMA sound */
#define TONE_CNT_RATIO 0x0002u
/* SOUNDCNT_X: bit 7, the master enable. Written for the first time on press 1. */
#define TONE_MASTER_ON 0x0080u

/* ---- the counter's colours (BGR555) -------------------------------------
 * Consecutive values must be unmistakable on a cheap RCA->HDMI chain, so the
 * sequence walks the primaries rather than shades of one hue. */
#define COL_BLACK   0x0000u
#define COL_RED     0x001Fu
#define COL_GREEN   0x03E0u
#define COL_BLUE    0x7C00u
#define COL_YELLOW  0x03FFu
#define COL_MAGENTA 0x7C1Fu        /* MORE THAN FOUR: he pressed too many times */
#define COL_BOX_ON  0x7FFFu        /* white */
#define COL_BOX_OFF 0x2108u        /* dark grey */

#define BOX_N      4u
#define BOX_W      40u
#define BOX_H      48u
#define BOX_Y      56u
#define BOX_GAP    16u
#define BOX_X0     12u             /* 12 + 4*40 + 3*16 = 220, centred-ish in 240 */

/* Every key the keypad carries. A press is ANY of them going down, because the
 * capture arms on ANY bit rising and the two counts must not be able to
 * disagree about what a press is. */
#define KEY_MASK 0x03FFu

/* ---- the pure state machine: what a press does --------------------------
 * Separated from the hardware so tests/unit/test_agb_tone.c can drive it. */
struct tone_state {
    u32 presses;          /* how many key-down edges have been seen */
    u16 held;             /* the previous ACTIVE-HIGH key set */
    u16 freq_n;           /* the n currently sounding, or 0xFFFF before the first press */
    u8  sounding;         /* 0 until the first press, 1 after */
};

#define TONE_N_NONE 0xFFFFu

void tone_init(struct tone_state *s)
{
    s->presses = 0u;
    s->held = 0u;
    s->freq_n = TONE_N_NONE;
    s->sounding = 0u;
}

/* §V9.3.2's alternation, as a function of the press ordinal (1-based):
 * odd presses take F1, even presses take F2. */
u16 tone_note_for_press(u32 press_ordinal)
{
    return (press_ordinal & 1u) ? (u16)TONE_N1 : (u16)TONE_N2;
}

/* The RISING edge, and only it. `keyinput` is the raw register: ACTIVE LOW.
 * Returns 1 when this sample contains at least one key going DOWN. */
int tone_step(struct tone_state *s, u16 keyinput)
{
    u16 now = (u16)(~keyinput & KEY_MASK);       /* active-high set */
    u16 went_down = (u16)(now & ~s->held);
    s->held = now;
    if (!went_down) return 0;
    s->presses++;
    s->freq_n = tone_note_for_press(s->presses);
    s->sounding = 1u;
    return 1;
}

u16 tone_background(const struct tone_state *s)
{
    switch (s->presses) {
    case 0u: return COL_BLACK;
    case 1u: return COL_RED;
    case 2u: return COL_GREEN;
    case 3u: return COL_BLUE;
    case 4u: return COL_YELLOW;
    default: return COL_MAGENTA;                 /* more than four */
    }
}

unsigned tone_boxes_filled(const struct tone_state *s)
{
    return (s->presses > BOX_N) ? BOX_N : (unsigned)s->presses;
}

/* ---- the picture --------------------------------------------------------- */
static void fill_rect(unsigned x0, unsigned y0, unsigned w, unsigned h, u16 c)
{
    unsigned x, y;
    for (y = y0; y < y0 + h && y < SCREEN_H; y++)
        for (x = x0; x < x0 + w && x < SCREEN_W; x++)
            VRAM[y * SCREEN_W + x] = c;
}

void tone_paint(const struct tone_state *s)
{
    unsigned i, filled = tone_boxes_filled(s);
    fill_rect(0u, 0u, SCREEN_W, SCREEN_H, tone_background(s));
    for (i = 0; i < BOX_N; i++) {
        unsigned x = BOX_X0 + i * (BOX_W + BOX_GAP);
        fill_rect(x, BOX_Y, BOX_W, BOX_H, (i < filled) ? COL_BOX_ON : COL_BOX_OFF);
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

static void apu_play(u16 n)
{
    /* The master enable must be set before any channel register is written:
     * with SOUNDCNT_X bit 7 clear the APU ignores writes (GBATEK). */
    REG_SOUNDCNT_X = TONE_MASTER_ON;
    REG_SOUNDCNT_H = TONE_CNT_RATIO;
    REG_SOUNDCNT_L = TONE_CNT_MIX;
    REG_SOUND1CNT_L = 0u;                        /* no sweep: the note must not glide */
    REG_SOUND1CNT_H = TONE_CNT_H;
    REG_SOUND1CNT_X = (u16)(TONE_RESTART | n);   /* restart, length flag CLEAR */
}

static void wait_vblank(void)
{
    while (REG_VCOUNT >= SCREEN_H) { }
    while (REG_VCOUNT < SCREEN_H) { }
}

int main(void)
{
    struct tone_state st;

    /* nothing composites, tints, blends or mosaics the bitmap */
    REG_BLDCNT = 0; REG_BLDALPHA = 0; REG_BLDY = 0; REG_MOSAIC = 0;
    /* no interrupt runs: the frame edge is POLLED, so nothing preempts a write */
    REG_IME = 0; REG_IE = 0; REG_IF = 0xFFFFu;

    tone_init(&st);
    apu_silence();                               /* REQUIREMENT 1: silent until the first press */

    REG_DISPCNT = 0x0403u;                       /* mode 3, BG2 on */
    tone_paint(&st);                             /* count 0: black, four empty boxes */

    /* The picture is repainted ONLY on a press -- four or five frames out of a
     * session's thousand -- so nothing competes with the capture for the rest
     * of the run. A full repaint does not fit in one VBlank and will overrun
     * into the visible period of that one frame; that is accepted and named
     * rather than discovered: a single torn frame is invisible to a person and
     * the AUDIO window this run measures does not read VRAM at all. */
    for (;;) {
        wait_vblank();
        if (tone_step(&st, REG_KEYINPUT)) {      /* REQUIREMENT 2: the key-DOWN edge only */
            apu_play(st.freq_n);                 /* the sound FIRST: it is what is measured */
            tone_paint(&st);                     /* REQUIREMENT 3: and he can see it */
        }
    }
}
