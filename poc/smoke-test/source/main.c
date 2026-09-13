/*
 * Open-GBP Smoke Test
 *
 * Purpose: prove the autonomous development loop
 *
 *     source -> Docker -> devkitPPC + libogc2 -> ELF -> DOL -> Dolphin
 *
 * This program deliberately touches only generic GameCube facilities
 * (video framebuffer console, controller pad, optional USB Gecko console
 * in memory-card slot B). It never accesses Game Boy Player / HSP
 * hardware.
 *
 * Observable behavior
 *   Screen : identity block, then a heartbeat counter updated once per
 *            second (60 VSyncs on NTSC, 50 on PAL).
 *   Gecko  : if a USB Gecko is detected on EXI channel 1 (slot B) the
 *            same information is emitted as machine-readable lines:
 *
 *              OPENGBP-SMOKE READY app=... build=... commit=... con=<cols>x<rows> font_h=<px> hb_row=<row> hash_rows=<px>
 *              OPENGBP-SMOKE HEARTBEAT n=<seconds> frames=<vsyncs> xfb_lit=<pixels> xfb_hash=<hex>
 *
 *            xfb_lit is the number of framebuffer pixels brighter than
 *            a threshold (proves the console text was rendered) and
 *            xfb_hash is an FNV-1a hash of the static identity rows
 *            (proves the rendered content is stable and deterministic).
 *
 *            Dolphin can emulate this device (Core.SlotB=7) and forwards
 *            the text to a TCP socket, which tools/dolphin_smoke.py uses
 *            as the smoke-test success criterion. On physical hardware
 *            the Gecko path is optional and silently skipped.
 *   Input  : X saves a short report to SD2SP2 (sd:/open-gbp/SMOKE-HW-001_<build>.log)
 *            through the same ring-buffer → flush path the GBP probe uses;
 *            START exits to the loader (Swiss) via exit().
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <gccore.h>
#include <ogc/libversion.h>

#include "opengbp_ident.h"
#include "ringlog.h"
#include "sdlog.h"

#define TEST_ID "SMOKE-HW-001"
#define LOG_LINES 64
#define LOG_LINE_LEN 120
static char log_storage[LOG_LINES * LOG_LINE_LEN];

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "smoke-test"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif

/* Literal marker that host tests locate inside the DOL image. */
static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT app=" OPENGBP_APP_NAME
    " build=" OPENGBP_BUILD_ID
    " commit=" OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1

/* Console origin and geometry used both for CON_Init and for the
 * framebuffer statistics below. */
#define CON_X0 20
#define CON_Y0 20
/* Luma threshold: the console draws white-ish text on black. */
#define XFB_LIT_LUMA 0x30u

static void *xfb;
static GXRModeObj *rmode;
static int gecko_present;

static void gecko_puts(const char *line)
{
    if (gecko_present) {
        usb_sendbuffer_safe(GECKO_CHANNEL, line, (int)strlen(line));
    }
}

struct xfb_stats {
    u32 lit;   /* pixels with luma > XFB_LIT_LUMA over the whole frame */
    u32 hash;  /* FNV-1a 32 over rows [0, hash_rows): the static identity block */
};

/* XFB is YUY2: each 32-bit word packs Y0 U Y1 V for two pixels. */
static void xfb_measure(const void *fb, const GXRModeObj *mode, u32 hash_rows,
                        struct xfb_stats *out)
{
    const u32 *p = (const u32 *)fb;
    u32 words_per_row = (u32)mode->fbWidth / 2u;
    u32 rows = mode->xfbHeight;
    u32 lit = 0;
    u32 hash = 2166136261u;
    u32 y, x;

    for (y = 0; y < rows; y++) {
        for (x = 0; x < words_per_row; x++) {
            u32 w = p[y * words_per_row + x];
            if (((w >> 24) & 0xFFu) > XFB_LIT_LUMA) lit++;
            if (((w >> 8) & 0xFFu) > XFB_LIT_LUMA) lit++;
            if (y < hash_rows) {
                hash ^= w;
                hash *= 16777619u;
            }
        }
    }
    out->lit = lit;
    out->hash = hash;
}

static void video_setup(void)
{
    VIDEO_Init();
    rmode = VIDEO_GetPreferredMode(NULL);
    xfb = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
    CON_Init(xfb, CON_X0, CON_Y0, rmode->fbWidth, rmode->xfbHeight,
             rmode->fbWidth * VI_DISPLAY_PIX_SZ);
    VIDEO_Configure(rmode);
    VIDEO_SetNextFramebuffer(xfb);
    VIDEO_SetBlack(false);
    VIDEO_Flush();
    VIDEO_WaitVSync();
    if (rmode->viTVMode & VI_NON_INTERLACE) {
        VIDEO_WaitVSync();
    }
}

int main(void)
{
    const struct opengbp_ident ident = {
        OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT
    };
    char ident_text[OPENGBP_IDENT_MAX];
    char line[OPENGBP_IDENT_MAX + 96];
    u32 frames = 0;
    u32 seconds = 0;
    u32 frames_per_second;
    struct xfb_stats stats;
    struct ringlog rl;
    int saved = 0;
    u32 buttons_seen = 0;
    int con_cols, con_rows, cur_col, cur_row;
    u32 font_h, hb_row, hash_rows;

    video_setup();
    PAD_Init();

    gecko_present = usb_isgeckoalive(GECKO_CHANNEL);
    opengbp_ident_format(ident_text, sizeof ident_text, &ident);

    printf("\n\n");
    printf("  Open-GBP Smoke Test\n");
    printf("  Build : %s\n", OPENGBP_BUILD_ID);
    printf("  Commit: %s\n", OPENGBP_GIT_COMMIT);
    printf("  libogc: %s\n", _V_STRING);
    printf("  Video : %ux%u %s\n", rmode->fbWidth, rmode->xfbHeight,
           (rmode->viTVMode >> 2) == VI_PAL ? "PAL" : "NTSC/other");
    printf("  Gecko : %s\n", gecko_present ? "detected (slot B)" : "absent");
    printf("  %s\n", opengbp_ident_marker);
    printf("\n  X = save report to SD2SP2   START = exit to loader\n\n");
    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s %s libogc=%s", TEST_ID, ident_text, _V_STRING);
    ringlog_printf(&rl, "VIDEO %ux%u tvmode=%u gecko=%d", rmode->fbWidth, rmode->xfbHeight,
                   (unsigned)rmode->viTVMode, gecko_present);

    /* Everything printed so far is static. The heartbeat is rewritten in
     * place on the current console row, so the framebuffer rows above it
     * must hash to the same value on every heartbeat. Derive the font
     * height from the console metrics instead of assuming it. */
    CON_GetMetrics(&con_cols, &con_rows);
    CON_GetPosition(&cur_col, &cur_row);
    /* The console area is (xfbHeight - CON_Y0) pixels tall and holds
     * con_rows rows; integer division yields the cell height (16). */
    font_h = con_rows > 0 ? ((u32)rmode->xfbHeight - CON_Y0) / (u32)con_rows : 16u;
    hb_row = (u32)cur_row;
    /* Hash everything above the row *before* the heartbeat row: one blank
     * row of margin so a small font-height error cannot leak the changing
     * heartbeat text into the "static" region. */
    hash_rows = CON_Y0 + (hb_row > 0 ? hb_row - 1u : 0u) * font_h;
    if (hash_rows > (u32)rmode->xfbHeight) {
        hash_rows = rmode->xfbHeight;
    }

    snprintf(line, sizeof line,
             "OPENGBP-SMOKE READY %s con=%dx%d font_h=%u hb_row=%u hash_rows=%u\n",
             ident_text, con_cols, con_rows, (unsigned)font_h, (unsigned)hb_row,
             (unsigned)hash_rows);
    gecko_puts(line);

    frames_per_second = ((rmode->viTVMode >> 2) == VI_PAL) ? 50 : 60;

    for (;;) {
        VIDEO_WaitVSync();
        frames++;
        PAD_ScanPads();

        buttons_seen |= PAD_ButtonsHeld(0);
        if (PAD_ButtonsDown(0) & PAD_BUTTON_START) {
            gecko_puts("OPENGBP-SMOKE EXIT reason=start\n");
            break;
        }
        if ((PAD_ButtonsDown(0) & PAD_BUTTON_X) && !saved) {
            char status[160];
            int rc;
            xfb_measure(xfb, rmode, hash_rows, &stats);
            ringlog_printf(&rl, "STATE seconds=%u frames=%u lit=%u hash=%08x buttons_seen=%04x",
                           (unsigned)seconds, (unsigned)frames, (unsigned)stats.lit,
                           (unsigned)stats.hash, (unsigned)buttons_seen);
            rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, "", &rl,
                            status, sizeof status, NULL, 0);
            saved = (rc == 0);
            printf("\x1b[%u;1H  SD: %s", (unsigned)(hb_row + 3u), status);
            snprintf(line, sizeof line, "OPENGBP-SMOKE SAVE rc=%d %s\n", rc, status);
            gecko_puts(line);
        }

        if (frames % frames_per_second == 0) {
            seconds++;
            xfb_measure(xfb, rmode, hash_rows, &stats);
            /* ESC[row;colH is 1-based; CON_GetPosition is 0-based. */
            printf("\x1b[%u;1H  Heartbeat: %u s, %u frames, lit %u, hash %08x",
                   (unsigned)(hb_row + 1u), (unsigned)seconds, (unsigned)frames,
                   (unsigned)stats.lit, (unsigned)stats.hash);
            snprintf(line, sizeof line,
                     "OPENGBP-SMOKE HEARTBEAT n=%u frames=%u xfb_lit=%u xfb_hash=%08x\n",
                     (unsigned)seconds, (unsigned)frames,
                     (unsigned)stats.lit, (unsigned)stats.hash);
            gecko_puts(line);
        }
    }

    printf("\n  Exiting.\n");
    VIDEO_WaitVSync();
    exit(0);
}
