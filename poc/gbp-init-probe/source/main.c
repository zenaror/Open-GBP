/*
 * Open-GBP GBP-INIT-001 — GBI CONTROL transform under a masked PI HSP interrupt.
 *
 * See src/gbp/gbp_init_probe.h for the experiment and its provenance, and
 * poc/gbp-init-probe/README.md for the procedure. This file is only the
 * GameCube glue: console, identity, real HSP backend, USB Gecko dump, SD
 * save on X, START to exit. Nothing here is timing-critical.
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
#include "gbp_init_probe.h"
#include "hsp_backend.h"
#include "hsp_backend_intmr.h"
#include "sdlog.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-init-probe"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-INIT-001"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT app=" OPENGBP_APP_NAME " build=" OPENGBP_BUILD_ID " commit=" OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1
#define LOG_LINES 160
#define LOG_LINE_LEN 256
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

static void print_snap(const struct gbp_init_snapshot *s)
{
    char hex[GBP_BLOCK_SIZE * 2 + 1];
    if (!s->taken) return;
    ringlog_hex(hex, sizeof hex, s->irq, GBP_BLOCK_SIZE);
    printf("  %s +%-6lu intsr=%08lx(13:%u) ctl=%02x/%02x irq=%04x %.16s..\n", s->id,
           (unsigned long)s->ticks_since_write, (unsigned long)s->intsr,
           (s->intsr & GBP_PI_HSP_BIT) ? 1u : 0u, s->control_vote, s->control_b1f, s->irq_disc, hex);
}

int main(void)
{
    struct ringlog rl;
    struct hsp_backend hsp;
    struct gbp_transport t;
    struct gbp_init_config cfg;
    struct gbp_init_result res;
    char line[LOG_LINE_LEN + 320];
    char summary[400];
    char status[160] = "not saved (press X)";
    char ident_text[OPENGBP_IDENT_MAX];
    const struct opengbp_ident ident = { OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT };
    size_t i;
    unsigned n;
    int saved = 0;

    video_setup();
    PAD_Init();
    gecko_present = usb_isgeckoalive(GECKO_CHANNEL);
    opengbp_ident_format(ident_text, sizeof ident_text, &ident);

    printf("\n  Open-GBP " TEST_ID "\n");
    printf("  Build : %s   Commit: %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("  libogc: %s   Gecko: %s\n", _V_STRING, gecko_present ? "yes" : "no");
    printf("  %s\n\n", opengbp_ident_marker);

    snprintf(line, sizeof line, "OPENGBP-INIT READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s app=%s build=%s commit=%s libogc=%s", TEST_ID,
                   OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, _V_STRING);
    ringlog_printf(&rl, "ENV bus_hz=%lu tb_hz=%lu dma_timeout_ms=%u csr=%04x",
                   (unsigned long)*(vu32 *)0x800000F8, (unsigned long)TB_TIMER_CLOCK * 1000ul,
                   (unsigned)DMA_TIMEOUT_MS, (unsigned)hsp_backend_read_csr());

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);
    hsp_backend_intmr_transport(&hsp, &t); /* GBP-INIT-001 writes INTMR directly (its own object) */
    gbp_init_config_default(&cfg);

    printf("  Detecting GBP, then GBI CONTROL transform (v&~%02x)|%02x with PI HSP masked ...\n",
           cfg.clear_mask, cfg.set_mask);
    gbp_init_probe_run(&t, &rl, &cfg, &res);
    ringlog_printf(&rl, "STATS transfers=%lu timeouts=%lu busy=%lu", (unsigned long)hsp.transfers,
                   (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals);
    gbp_init_summary(&res, summary, sizeof summary);

    printf("\n  status=%s reason=%s  presence=%s (vote %u/%u b1 %u/%u)\n", gbp_init_status_name(res.status),
           res.abort_reason ? res.abort_reason : "-", gbp_verdict_name(res.det.verdict),
           res.det.vote_ok, res.det.run, res.det.b1_ok, res.det.run);
    printf("  AR_INFO orig=%04x exp=%04x final=%04x restored=%s   INTMR orig=%08lx restored=%s\n",
           res.arinfo_orig, res.arinfo_exp, res.arinfo_final, res.arinfo_restored ? "yes" : "NO",
           (unsigned long)res.intmr_orig,
           res.intmr_restored == -1 ? "unchanged" : res.intmr_restored ? "yes" : "NO");
    printf("  CONTROL orig=%02x exp=%02x written=%d restored=%s transition(S1,S2)=%d\n",
           res.control_orig, res.control_exp, res.control_written,
           res.control_restored == -1 ? "n/a" : res.control_restored ? "yes" : "NO", res.transition_s1_s2);
    for (n = 0; n < GBP_INIT_SNAPSHOTS; n++) print_snap(&res.snap[n]);
    printf("  errors=%u transfers=%lu timeouts=%lu busy=%lu log=%u dropped=%u truncated=%u\n",
           res.errors, (unsigned long)hsp.transfers, (unsigned long)hsp.timeouts,
           (unsigned long)hsp.busy_refusals, (unsigned)rl.count, (unsigned)rl.dropped, (unsigned)rl.truncated);
    printf("\n  X = save log to SD2SP2      START = exit\n\n");

    for (i = 0; i < rl.count; i++) {
        snprintf(line, sizeof line, "OPENGBP-INIT LOG %s\n", ringlog_line(&rl, i));
        gecko_puts(line);
    }
    snprintf(line, sizeof line, "OPENGBP-INIT %s\n", summary);
    gecko_puts(line);

    for (;;) {
        u32 down;
        VIDEO_WaitVSync();
        PAD_ScanPads();
        down = PAD_ButtonsDown(0);
        if (down & PAD_BUTTON_START) {
            gecko_puts("OPENGBP-INIT EXIT reason=start\n");
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
            printf("\x1b[26;1H  SD: %s\n", status);
            snprintf(line, sizeof line, "OPENGBP-INIT SAVE rc=%d %s\n", rc, status);
            gecko_puts(line);
        }
    }
    printf("\n  Exiting.\n");
    VIDEO_WaitVSync();
    exit(0);
}
