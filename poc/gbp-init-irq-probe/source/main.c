/*
 * Open-GBP GBP-INIT-002 — first unmask of the PI HSP interrupt, after the
 * validated CONTROL transform, with a one-shot self-masking handler.
 *
 * See src/gbp/gbp_init_irq_probe.h for the experiment and its rules, and
 * poc/gbp-init-irq-probe/README.md for the procedure. This file is only
 * the GameCube glue: console, identity, real HSP backend (which owns the
 * handler, src/platform/hsp_backend.c), USB Gecko dump, SD save on X,
 * START to exit. The X/START loop — and therefore any SD I/O — is only
 * reached after the probe has completed its teardown.
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
#include "gbp_init_irq_probe.h"
#include "hsp_backend.h"
#include "hsp_backend_irq.h"
#include "sdlog.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-init-irq-probe"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-INIT-002"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT app=" OPENGBP_APP_NAME " build=" OPENGBP_BUILD_ID " commit=" OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1
#define LOG_LINES 160
#define LOG_LINE_LEN 256
#define DMA_TIMEOUT_MS 200
#define T_MAX_MS 2000          /* operational bound of the wait after the unmask; not a GBP property */

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

static void print_snap(const struct gbp_initirq_snapshot *s)
{
    if (!s->taken) return;
    printf("  %s +w%-7lu +u%-7lu intsr=%08lx(13:%u) intmr13=%u ctl=%02x/%02x irq=%04x/%04x b0=%02x/%02x\n", s->id,
           (unsigned long)s->since_write, (unsigned long)s->since_unmask, (unsigned long)s->intsr,
           (s->intsr & GBP_PI_HSP_BIT) ? 1u : 0u, (s->intmr & GBP_PI_HSP_BIT) ? 1u : 0u,
           s->control_vote, s->control_b1f, s->irq_disc, s->irq_gbi, s->control[0], s->irq[0]);
    if (s->pi2_ok)
        printf("      second sample intsr=%08lx(13:%u)\n", (unsigned long)s->intsr2, (s->intsr2 & GBP_PI_HSP_BIT) ? 1u : 0u);
}

int main(void)
{
    struct ringlog rl;
    struct hsp_backend hsp;
    struct gbp_transport t;
    struct gbp_initirq_config cfg;
    struct gbp_initirq_result res;
    char summary[640];
    char line[sizeof summary + 64];   /* holds a gecko-prefixed log line or the summary */
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

    snprintf(line, sizeof line, "OPENGBP-INITIRQ READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s app=%s build=%s commit=%s libogc=%s", TEST_ID,
                   OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, _V_STRING);
    ringlog_printf(&rl, "ENV bus_hz=%lu tb_hz=%lu dma_timeout_ms=%u t_max_ms=%u csr=%04x",
                   (unsigned long)*(vu32 *)0x800000F8, (unsigned long)TB_TIMER_CLOCK * 1000ul,
                   (unsigned)DMA_TIMEOUT_MS, (unsigned)T_MAX_MS, (unsigned)hsp_backend_read_csr());

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);
    hsp_backend_irq_transport(&hsp, &t);   /* this POC needs INTMR / handler operations */
    gbp_initirq_config_default(&cfg);
    cfg.t_max_ms = T_MAX_MS;
    cfg.t_max_ticks = (uint32_t)millisecs_to_ticks(T_MAX_MS);
    cfg.tb_hz = (uint32_t)TB_TIMER_CLOCK * 1000u;

    printf("  Sequence: AR_INFO exp=3 -> presence gate -> PI preconditions -> S0/CONTROL shape\n");
    printf("            -> handler -> CONTROL (v&~%02x)|%02x -> S1 -> unmask IRQ26 (<= %u ms) -> mask\n",
           cfg.clear_mask, cfg.set_mask, (unsigned)T_MAX_MS);
    printf("            -> S2 -> restore CONTROL -> S3 -> PI cleanup -> handler/mask/AR_INFO restore -> S4\n");
    printf("  Running, do not press anything ...\n");

    gbp_initirq_probe_run(&t, &rl, &cfg, &res);      /* returns only after the teardown */

    ringlog_printf(&rl, "STATS transfers=%lu timeouts=%lu busy=%lu", (unsigned long)hsp.transfers,
                   (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals);
    gbp_initirq_summary(&res, summary, sizeof summary);

    printf("\n  status=%s reason=%s restore=%s (%s)\n", gbp_initirq_status_name(res.status),
           res.reason ? res.reason : "-", res.restore_ok ? "ok" : "ERROR", res.restore_reason ? res.restore_reason : "-");
    printf("  presence=%s (vote %u/%u b1 %u/%u)  AR_INFO %04x->%04x->%04x restored=%s\n",
           gbp_verdict_name(res.det.verdict), res.det.vote_ok, res.det.run, res.det.b1_ok, res.det.run,
           res.arinfo_orig, res.arinfo_exp, res.arinfo_final, res.arinfo_restored == 1 ? "yes" : res.arinfo_restored == 0 ? "NO" : "n/a");
    printf("  PI pre intsr=%08lx intmr=%08lx  CONTROL orig=%02x exp=%02x written=%d restored=%s\n",
           (unsigned long)res.intsr_pre, (unsigned long)res.intmr_pre, res.control_orig, res.control_exp,
           res.control_written, res.control_restored == -1 ? "n/a" : res.control_restored ? "yes" : "NO");
    printf("  handler installed=%d old=%s restored=%s   unmasked=%d masked_again=%d mask_ok=%s\n",
           res.handler_installed || res.handler_restored != -1,
           res.old_handler_null == 1 ? "null" : res.old_handler_null == 0 ? "nonnull" : "?",
           res.handler_restored == -1 ? "n/a" : res.handler_restored ? "yes" : "NO",
           res.irq_unmasked, res.irq_masked_again, res.mask_ok == -1 ? "n/a" : res.mask_ok ? "yes" : "NO");
    printf("  fired=%d count=%lu timed_out=%d latency=%lu ticks (%lu us) reentry=%d wait=%lu ticks\n",
           res.fired, (unsigned long)res.rec.count, res.timed_out, (unsigned long)res.latency_ticks,
           (unsigned long)res.latency_us, res.unexpected_reentry, (unsigned long)res.wait_ticks);
    printf("  ISR intsr before_ack=%08lx after_ack=%08lx  intmr at_entry=%08lx after_mask=%08lx\n",
           (unsigned long)res.rec.intsr_before_ack, (unsigned long)res.rec.intsr_after_ack,
           (unsigned long)res.rec.intmr_at_entry, (unsigned long)res.rec.intmr_after_mask);
    printf("  cleanup_ack=%d (intsr %08lx -> %08lx)\n", res.cleanup_ack_performed,
           (unsigned long)res.cleanup_intsr_before, (unsigned long)res.cleanup_intsr_after);
    for (n = 0; n < GBP_INITIRQ_SNAPSHOTS; n++) print_snap(&res.snap[n]);
    printf("  errors=%u transfers=%lu timeouts=%lu busy=%lu log=%u dropped=%u truncated=%u\n",
           res.errors, (unsigned long)hsp.transfers, (unsigned long)hsp.timeouts,
           (unsigned long)hsp.busy_refusals, (unsigned)rl.count, (unsigned)rl.dropped, (unsigned)rl.truncated);
    printf("\n  X = save log to SD2SP2      START = exit      (power-cycle the console afterwards)\n\n");

    for (i = 0; i < rl.count; i++) {
        snprintf(line, sizeof line, "OPENGBP-INITIRQ LOG %s\n", ringlog_line(&rl, i));
        gecko_puts(line);
    }
    snprintf(line, sizeof line, "OPENGBP-INITIRQ %s\n", summary);
    gecko_puts(line);

    for (;;) {
        u32 down;
        VIDEO_WaitVSync();
        PAD_ScanPads();
        down = PAD_ButtonsDown(0);
        if (down & PAD_BUTTON_START) {
            gecko_puts("OPENGBP-INITIRQ EXIT reason=start\n");
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
            printf("\x1b[27;1H  SD: %s\n", status);
            snprintf(line, sizeof line, "OPENGBP-INITIRQ SAVE rc=%d %s\n", rc, status);
            gecko_puts(line);
        }
    }
    printf("\n  Exiting.\n");
    VIDEO_WaitVSync();
    exit(0);
}
