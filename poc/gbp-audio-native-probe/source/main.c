/*
 * Open-GBP Audio Native Probe (GitHub Issue #127)
 *
 * Purpose: prove build+link+run of the native decoder path
 * (gbp_adec2/gbp_aresamp2/gbp_aplay2/gbp_atrans2, GitHub Issues #126/#127) on the real Gekko/
 * Broadway target and under Dolphin -- EXECUTION ONLY. It never touches Game Boy Player / HSP
 * hardware, real or emulated: the self-test below feeds a SYNTHETIC decoded stream (no cartridge,
 * no drain), exactly mirroring what tests/unit/test_gbp_aplay2.c and test_gbp_atrans2.c already
 * prove on the host, just compiled for the real target this time. Correctness is the host suite's
 * job; this POC only answers "does the ported code run here without crashing" (CLAUDE.md §6.4,
 * §9, §17).
 *
 * Everything else (video framebuffer console, controller pad, optional USB Gecko console, SD2SP2
 * report) is poc/smoke-test's own proven mechanism, unchanged, so tools/dolphin_smoke.py's generic
 * READY/HEARTBEAT detection works identically here.
 *
 * Observable behavior
 *   Screen : identity block, the audio self-test's PASS/FAIL line, then the same heartbeat counter
 *            poc/smoke-test uses.
 *   Gecko  : the same OPENGBP-SMOKE-style lines, plus one
 *              OPENGBP-AUDIO2 SELFTEST result=PASS|FAIL produced=<n> dup=<n> drop=<n> atrans=<n>
 *            line, emitted once before READY.
 *   Input  : X saves a short report to SD2SP2; START exits to the loader (Swiss) via exit().
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <gccore.h>
#include <ogc/libversion.h>

#include "opengbp_ident.h"
#include "ringlog.h"
#include "sdlog.h"

#include "gbp_adec2.h"
#include "gbp_aplay2.h"
#include "gbp_atrans2.h"

#define TEST_ID "AUDIO2-PROBE-001"
#define LOG_LINES 64
#define LOG_LINE_LEN 120
static char log_storage[LOG_LINES * LOG_LINE_LEN];

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-audio-native-probe"
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

#define CON_X0 20
#define CON_Y0 20
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

/* ---- the native audio chain's caller storage (a NEW path, not a moved default) ---------------- */
static int16_t decoder_ring[GBP_APLAY2_RING];
static uint8_t audio_pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES];
static uint8_t audio_silence[GBP_APLAY2_CHUNK_BYTES];
static int16_t audio_keep[GBP_APLAY2_KEEP_CAP];
static struct gbp_aplay2_event audio_events[GBP_APLAY2_EVENTS_CAP];

struct audio_selftest_result {
    int pass;
    uint32_t produced, dup, drop, atrans_completed;
};

/* Feed `n` synthetic decoded samples directly into the decoder's ring (no cartridge, no drain --
 * exactly tests/unit/test_gbp_aplay2.c's own give()). */
static void selftest_give(struct gbp_adec2 *d, uint32_t n, int16_t v)
{
    uint32_t k;
    for (k = 0; k < n && d->count < d->cap; k++) {
        d->ring[(d->head + d->count) % d->cap] = v;
        d->count++;
    }
}

/* Drive one chunk to completion (a generous, bounded loop -- gbp_aplay2's own gate arithmetic
 * guarantees a started chunk always finishes; a real defect would show as this returning 0). */
static int selftest_drive(struct gbp_aplay2 *p, struct gbp_adec2 *d)
{
    uint32_t i;
    for (i = 0; i < GBP_APLAY2_PUSHES + 4u; i++) {
        const int b = gbp_aplay2_produce(p, d);
        if (b >= 0) {
            gbp_aplay2_queue(p, b);
            (void)gbp_aplay2_irq_handoff(p, 0u);
            gbp_aplay2_process(p);
            return 1;
        }
    }
    return 0;
}

/* Runs the SAME chunk/queue/hand-off/L2/mute sequence tests/unit/test_gbp_aplay2.c proves on the
 * host, then one gbp_atrans2 UNMUTED transition -- on the real target this time. No cartridge, no
 * GBP/HSP register is read or written anywhere in this file. */
static void audio_selftest(struct audio_selftest_result *out)
{
    struct gbp_adec2 d;
    struct gbp_aplay2 p;
    struct gbp_atrans2 t;
    uint32_t i;
    int ok = 1;

    gbp_adec2_init(&d, decoder_ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&p, audio_pool, audio_silence, audio_keep, audio_events);
    gbp_atrans2_init(&t);
    p.playing = 1;
    gbp_aplay2_set_target(&p, GBP_APLAY2_PUSHES);   /* a cold chunk should not immediately correct */

    for (i = 0; i < 2u; i++) {
        selftest_give(&d, GBP_APLAY2_PUSHES + 1u, 100);
        if (!selftest_drive(&p, &d)) ok = 0;
    }

    {
        int to_queue;
        selftest_give(&d, GBP_APLAY2_PUSHES + 1u, 100);
        gbp_atrans2_begin(&t, &p, &d, 0u, GBP_ATRANS2_UNMUTED, 0u, 0u, 0u, GBP_APLAY2_TARGET);
        if (gbp_atrans2_step(&t, &p, &d, 1u, &to_queue) != 1) ok = 0;
    }

    out->pass = ok && p.produced >= 2u;
    out->produced = p.produced;
    out->dup = p.dup;
    out->drop = p.drop;
    out->atrans_completed = t.completed;
}

struct xfb_stats { u32 lit; u32 hash; };

static void xfb_measure(const void *fb, const GXRModeObj *mode, u32 hash_rows, struct xfb_stats *out)
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
    char line[OPENGBP_IDENT_MAX + 128];
    u32 frames = 0;
    u32 seconds = 0;
    u32 frames_per_second;
    struct xfb_stats stats;
    struct ringlog rl;
    struct audio_selftest_result at;
    int saved = 0;
    u32 buttons_seen = 0;
    int con_cols, con_rows, cur_col, cur_row;
    u32 font_h, hb_row, hash_rows;

    video_setup();
    PAD_Init();

    gecko_present = usb_isgeckoalive(GECKO_CHANNEL);
    opengbp_ident_format(ident_text, sizeof ident_text, &ident);

    audio_selftest(&at);

    printf("\n\n");
    printf("  Open-GBP Audio Native Probe\n");
    printf("  Build : %s\n", OPENGBP_BUILD_ID);
    printf("  Commit: %s\n", OPENGBP_GIT_COMMIT);
    printf("  libogc: %s\n", _V_STRING);
    printf("  Video : %ux%u %s\n", rmode->fbWidth, rmode->xfbHeight,
           (rmode->viTVMode >> 2) == VI_PAL ? "PAL" : "NTSC/other");
    printf("  Gecko : %s\n", gecko_present ? "detected (slot B)" : "absent");
    printf("  Audio selftest: %s (produced=%u dup=%u drop=%u atrans=%u)\n",
           at.pass ? "PASS" : "FAIL", (unsigned)at.produced, (unsigned)at.dup, (unsigned)at.drop,
           (unsigned)at.atrans_completed);
    printf("  %s\n", opengbp_ident_marker);
    printf("\n  X = save report to SD2SP2   START = exit to loader\n\n");
    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s %s libogc=%s", TEST_ID, ident_text, _V_STRING);
    ringlog_printf(&rl, "VIDEO %ux%u tvmode=%u gecko=%d", rmode->fbWidth, rmode->xfbHeight,
                   (unsigned)rmode->viTVMode, gecko_present);
    ringlog_printf(&rl, "AUDIO2 result=%s produced=%u dup=%u drop=%u atrans=%u",
                   at.pass ? "PASS" : "FAIL", (unsigned)at.produced, (unsigned)at.dup,
                   (unsigned)at.drop, (unsigned)at.atrans_completed);

    snprintf(line, sizeof line, "OPENGBP-AUDIO2 SELFTEST result=%s produced=%u dup=%u drop=%u atrans=%u\n",
             at.pass ? "PASS" : "FAIL", (unsigned)at.produced, (unsigned)at.dup, (unsigned)at.drop,
             (unsigned)at.atrans_completed);
    gecko_puts(line);

    CON_GetMetrics(&con_cols, &con_rows);
    CON_GetPosition(&cur_col, &cur_row);
    font_h = con_rows > 0 ? ((u32)rmode->xfbHeight - CON_Y0) / (u32)con_rows : 16u;
    hb_row = (u32)cur_row;
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
