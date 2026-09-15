/*
 * Open-GBP GBP-PROBE-001 — read-only Game Boy Player presence probe.
 *
 * What it does (docs/research/HARDWARE_TESTS.md, GBP-PROBE-001):
 *   1. shows Test ID / Build ID / commit;
 *   2. reads AR_INFO (0xCC005012) and logs it;
 *   3. MODE A (AR_INFO untouched): raw 32-byte reads of blocks 0x0 (TEST),
 *      0x4 (CONTROL), 0xD (IRQ); TEST handshake with C3/3C/FF/00; raw reads again;
 *   4. MODE B: AR_INFO bits 3-5 := 3, everything else preserved; same procedure;
 *   5. restores AR_INFO; shows a summary; emits every log line over USB Gecko
 *      (slot B) if one is present;
 *   6. X saves the log to SD2SP2 (sd:/open-gbp/GBP-PROBE-001_<build>.log),
 *      START exits to the loader.
 *
 * Presence policy (build probe-0002+): gbp_detect.h — a mode is "present"
 * only if every handshake completed and passed both the Start-up Disc
 * criterion (byte 1 == ~pattern) and the GBI majority-vote criterion.
 * DMA completion by itself is never treated as presence (both physical
 * runs of 2026-09-14 completed all transfers, with and without the GBP).
 *
 * GBP-side writes: only the TEST block (index 0). No CONTROL, KEYPAD, SIO,
 * video or audio access. GameCube-side writes: AR_INFO bits 3-5 only,
 * restored before exit. Nothing here is timing-critical; every wait has a
 * timeout.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <gccore.h>
#include <ogc/libversion.h>
#include <ogc/lwp_watchdog.h>

#include "opengbp_ident.h"
#include "ringlog.h"
#include "gbp_transport.h"
#include "gbp_probe.h"
#include "hsp_backend.h"
#include "sdlog.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-probe"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-PROBE-001"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT app=" OPENGBP_APP_NAME " build=" OPENGBP_BUILD_ID " commit=" OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1
#define LOG_LINES 160
#define LOG_LINE_LEN 256
/* DMA completion timeout: 200 ms in time-base ticks (TB = bus clock / 4). */
#define DMA_TIMEOUT_MS 200

static char log_storage[LOG_LINES * LOG_LINE_LEN];
static uint8_t dma_buffer[GBP_BLOCK_SIZE] ATTRIBUTE_ALIGN(32);

static void *xfb;
static GXRModeObj *rmode;
static int gecko_present;

static void gecko_puts(const char *line)
{
    if (gecko_present) usb_sendbuffer_safe(GECKO_CHANNEL, line, (int)strlen(line));
}

static void video_setup(void)
{
    VIDEO_Init();
    rmode = VIDEO_GetPreferredMode(NULL);
    xfb = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
    CON_Init(xfb, 20, 20, rmode->fbWidth, rmode->xfbHeight, rmode->fbWidth * VI_DISPLAY_PIX_SZ);
    VIDEO_Configure(rmode);
    VIDEO_SetNextFramebuffer(xfb);
    VIDEO_SetBlack(false);
    VIDEO_Flush();
    VIDEO_WaitVSync();
    if (rmode->viTVMode & VI_NON_INTERLACE) VIDEO_WaitVSync();
}

static void print_raw(const char *name, const uint8_t *raw, gbp_status rc)
{
    char hex[GBP_BLOCK_SIZE * 2 + 1];
    ringlog_hex(hex, sizeof hex, raw, GBP_BLOCK_SIZE);
    printf("  %-4s rc=%-7s %.32s\n              %.32s\n", name, gbp_status_name(rc), hex, hex + 32);
}

int main(void)
{
    struct ringlog rl;
    struct hsp_backend hsp;
    struct gbp_transport t;
    struct gbp_probe_config cfg;
    struct gbp_probe_result res;
    char line[LOG_LINE_LEN + 320];
    char summary[256];
    char status[160] = "not saved (press X)";
    char ident_text[OPENGBP_IDENT_MAX];
    const struct opengbp_ident ident = { OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT };
    unsigned m;
    size_t i;
    int saved = 0;

    video_setup();
    PAD_Init();
    gecko_present = usb_isgeckoalive(GECKO_CHANNEL);
    opengbp_ident_format(ident_text, sizeof ident_text, &ident);

    printf("\n  Open-GBP " TEST_ID "\n");
    printf("  Build : %s   Commit: %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("  libogc: %s   Gecko: %s\n", _V_STRING, gecko_present ? "yes" : "no");
    printf("  %s\n\n", opengbp_ident_marker);

    snprintf(line, sizeof line, "OPENGBP-PROBE READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s app=%s build=%s commit=%s libogc=%s", TEST_ID,
                   OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, _V_STRING);
    ringlog_printf(&rl, "ENV bus_hz=%lu tb_hz=%lu dma_timeout_ms=%u csr=%04x",
                   (unsigned long)*(vu32 *)0x800000F8, (unsigned long)TB_TIMER_CLOCK * 1000ul,
                   (unsigned)DMA_TIMEOUT_MS, (unsigned)hsp_backend_read_csr());

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);
    gbp_probe_config_default(&cfg);

    printf("  Running MODE A (AR_INFO as found) and MODE B (bits 3-5 := 3) ...\n");
    gbp_probe_run(&t, &rl, &cfg, &res);
    ringlog_printf(&rl, "STATS transfers=%lu timeouts=%lu busy=%lu", (unsigned long)hsp.transfers,
                   (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals);

    gbp_probe_summary(&res, summary, sizeof summary);

    /* ---- screen summary ------------------------------------------- */
    printf("\n  AR_INFO orig=%04x  modeA=%04x  modeB=%04x  final=%04x  restored=%s\n",
           res.arinfo_orig, res.mode[0].arinfo_before, res.mode[1].arinfo_before, res.arinfo_final,
           res.arinfo_restored ? "yes" : "NO");
    for (m = 0; m < res.modes_run; m++) {
        const struct gbp_probe_mode_result *mr = &res.mode[m];
        printf("  MODE %c base=%08lx reads %u/%u vote %u/%u b1 %u/%u all32 %u/%u -> %s\n",
               m == 0 ? 'A' : 'B', (unsigned long)mr->base, mr->reads_ok,
               mr->reads_ok + mr->reads_failed, mr->tests_match_vote, mr->tests_run,
               mr->tests_match_b1, mr->tests_run, mr->tests_match_all, mr->tests_run,
               gbp_verdict_name(mr->verdict));
        print_raw("TEST", mr->raw[0], mr->raw_rc[0]);
        print_raw("CTRL", mr->raw[1], mr->raw_rc[1]);
        print_raw("IRQ", mr->raw[2], mr->raw_rc[2]);
    }
    printf("  errors=%u transfers=%lu timeouts=%lu busy=%lu log=%u lines dropped=%u\n",
           res.errors, (unsigned long)hsp.transfers, (unsigned long)hsp.timeouts,
           (unsigned long)hsp.busy_refusals, (unsigned)rl.count, (unsigned)rl.dropped);
    printf("\n  X = save log to SD2SP2      START = exit\n\n");

    /* ---- gecko: every record, then the summary ---------------------- */
    for (i = 0; i < rl.count; i++) {
        snprintf(line, sizeof line, "OPENGBP-PROBE LOG %s\n", ringlog_line(&rl, i));
        gecko_puts(line);
    }
    snprintf(line, sizeof line, "OPENGBP-PROBE %s\n", summary);
    gecko_puts(line);

    for (;;) {
        u32 down;
        VIDEO_WaitVSync();
        PAD_ScanPads();
        down = PAD_ButtonsDown(0);
        if (down & PAD_BUTTON_START) {
            gecko_puts("OPENGBP-PROBE EXIT reason=start\n");
            break;
        }
        if ((down & PAD_BUTTON_X) && !saved) {
            char path[128] = "";
            char extra[96];
            int rc;
            snprintf(extra, sizeof extra, "libogc=%s gecko=%d", _V_STRING, gecko_present);
            rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl,
                            status, sizeof status, path, sizeof path);
            saved = (rc == 0);
            printf("\x1b[24;1H  SD: %s\n", status);
            snprintf(line, sizeof line, "OPENGBP-PROBE SAVE rc=%d %s\n", rc, status);
            gecko_puts(line);
        }
    }
    printf("\n  Exiting.\n");
    VIDEO_WaitVSync();
    exit(0);
}
