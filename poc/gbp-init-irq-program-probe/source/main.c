/*
 * Open-GBP GBP-INIT-003A — GBP IRQ-register programming (A1 = read | 0x8000,
 * A2 = 0) with the PI HSP interrupt masked for the whole run.
 *
 * See src/gbp/gbp_initirqa_probe.h for the experiment and its rules, and
 * poc/gbp-init-irq-program-probe/README.md for the procedure. This file is
 * only the GameCube glue: console, identity, the base HSP backend (DMA, PI
 * reads, INTSR W1C, time base — src/platform/hsp_backend.c; the interrupt
 * path object hsp_backend_irq.c is deliberately NOT linked), USB Gecko
 * dump, SD save on X, START to exit. Nothing is read from the controller
 * before the probe has returned from its teardown; SD I/O happens only in
 * the X/START loop afterwards. Any run that attempted an experimental
 * CONTROL or IRQ write ends with "POWER CYCLE REQUIRED" on screen.
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
#include "gbp_initirqa_probe.h"
#include "hsp_backend.h"
#include "sdlog.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-init-irq-program-probe"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-INIT-003A"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT app=" OPENGBP_APP_NAME " build=" OPENGBP_BUILD_ID " commit=" OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1
#define LOG_LINES 192
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

static void print_snap(const struct gbp_initirqa_snapshot *s)
{
    if (!s->taken) return;
    printf("  %-9s +c%-9lu +a1 %-9lu +a2 %-9lu i13=%u m13=%u ctl=%02x/%02x irq=%04x/%04x b0=%02x/%02x%s\n", s->id,
           (unsigned long)s->since_control, (unsigned long)s->since_a1, (unsigned long)s->since_a2,
           (s->intsr & GBP_PI_HSP_BIT) ? 1u : 0u, (s->intmr & GBP_PI_HSP_BIT) ? 1u : 0u,
           s->control_vote, s->control_b1f, s->irq_gbi, s->irq_disc, s->control[0], s->irq[0],
           s->is_event ? " EVENT" : "");
}

int main(void)
{
    struct ringlog rl;
    struct hsp_backend hsp;
    struct gbp_transport t;
    struct gbp_initirqa_config cfg;
    struct gbp_initirqa_result res;
    char summary[900];
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

    snprintf(line, sizeof line, "OPENGBP-INITIRQA READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    gbp_initirqa_config_default(&cfg);
    gbp_initirqa_config_timebase(&cfg, (uint32_t)TB_TIMER_CLOCK * 1000u);

    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s app=%s build=%s commit=%s libogc=%s", TEST_ID,
                   OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, _V_STRING);
    ringlog_printf(&rl, "ENV bus_hz=%lu tb_hz=%lu dma_timeout_ms=%u t_max_ms=%lu a1_obs_us=%lu,%lu a2_obs_us=%lu,%lu,%lu,%lu,%lu,%lu csr=%04x",
                   (unsigned long)*(vu32 *)0x800000F8, (unsigned long)cfg.tb_hz, (unsigned)DMA_TIMEOUT_MS,
                   (unsigned long)cfg.t_max_ms, (unsigned long)cfg.a1_obs_us[0], (unsigned long)cfg.a1_obs_us[1],
                   (unsigned long)cfg.a2_obs_us[0], (unsigned long)cfg.a2_obs_us[1], (unsigned long)cfg.a2_obs_us[2],
                   (unsigned long)cfg.a2_obs_us[3], (unsigned long)cfg.a2_obs_us[4], (unsigned long)cfg.a2_obs_us[5],
                   (unsigned)hsp_backend_read_csr());

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);   /* base operations only: no INTMR write, no handler, no unmask exists in this binary */

    printf("  Sequence: AR_INFO exp=3 -> presence gate -> PI preconditions -> BASE (CONTROL/IRQ shape)\n");
    printf("            -> CONTROL (v&~%02x)|%02x -> P0 -> A1: IRQ := read|%04x -> A1-0, +50us, +500us\n",
           cfg.clear_mask, cfg.set_mask, cfg.ack_or);
    printf("            -> A2PRE -> A2: IRQ := 0000 -> A2-0, +50us .. +%lu ms (INTSR polled, PI masked)\n",
           (unsigned long)cfg.t_max_ms);
    printf("            -> restore CONTROL -> IRQ := read|%04x (Start-up Disc stop) -> PI cleanup -> AR_INFO -> FINAL\n",
           cfg.stop_or);
    printf("  PI HSP interrupt stays masked: no handler, no unmask, INTMR never written.\n");
    printf("  Running, do not press anything ...\n");

    gbp_initirqa_probe_run(&t, &rl, &cfg, &res);     /* returns only after the teardown */

    ringlog_printf(&rl, "STATS transfers=%lu timeouts=%lu busy=%lu", (unsigned long)hsp.transfers,
                   (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals);
    gbp_initirqa_summary(&res, summary, sizeof summary);

    printf("\n  status=%s reason=%s restore=%s (%s)\n", gbp_initirqa_status_name(res.status),
           res.reason ? res.reason : "-", res.restore_ok ? "ok" : "ERROR", res.restore_reason ? res.restore_reason : "-");
    printf("  presence=%s (vote %u/%u b1 %u/%u)  AR_INFO %04x->%04x->%04x restored=%s\n",
           gbp_verdict_name(res.det.verdict), res.det.vote_ok, res.det.run, res.det.b1_ok, res.det.run,
           res.arinfo_orig, res.arinfo_exp, res.arinfo_final,
           res.arinfo_restore_ok == 1 ? "yes" : res.arinfo_restore_ok == 0 ? "NO" : "n/a");
    printf("  PI pre intsr=%08lx intmr=%08lx  CONTROL orig=%02x exp=%02x written=%d restored=%s\n",
           (unsigned long)res.intsr_pre, (unsigned long)res.intmr_pre, res.control_orig, res.control_exp,
           res.control_written, res.control_restore_ok == -1 ? "n/a" : res.control_restore_ok ? "yes" : "NO");
    printf("  IRQ a1pre=%04x A1=%04x(%s) a2pre=%04x A2=0000(%s) stop_pre=%04x STOP=%04x(%s) post=%04x masks=%d b15=%d\n",
           res.irq_a1pre.gbi, res.ack_value, res.w_a1.completed ? "ok" : res.w_a1.attempted ? "FAIL" : "-",
           res.irq_a2pre.gbi, res.w_a2.completed ? "ok" : res.w_a2.attempted ? "FAIL" : "-",
           res.irq_stop_pre.gbi, res.stop_value, res.w_stop.completed ? "ok" : res.w_stop.attempted ? "FAIL" : "-",
           res.irq_stop_post.gbi, res.stop_masks_readback, res.stop_bit15_readback);
    printf("  intsr13_seen=%d first=%s t_first=%lu event=%d ended_early=%d polls a1=%u a2=%u obs a1=%u/%u a2=%u/%u\n",
           res.intsr13_seen, res.first_intsr13_phase ? res.first_intsr13_phase : "-", (unsigned long)res.t_first_intsr13,
           res.event_taken, res.window_ended_early, res.a1_polls, res.a2_polls, res.a1_obs_taken, cfg.n_a1_obs,
           res.a2_obs_taken, cfg.n_a2_obs);
    printf("  writes attempted/completed: CONTROL %d/%d  A1 %d/%d  A2 %d/%d  STOP %d/%d  restore %d/%d  uncertain=%u%s\n",
           res.w_ctl_exp.attempted, res.w_ctl_exp.completed, res.w_a1.attempted, res.w_a1.completed,
           res.w_a2.attempted, res.w_a2.completed, res.w_stop.attempted, res.w_stop.completed,
           res.w_ctl_restore.attempted, res.w_ctl_restore.completed, res.uncertain_writes,
           res.uncertain_writes ? "  DEVICE STATE UNCERTAIN" : "");
    printf("  cleanup performed=%d ok=%d sticky=%d (intsr %08lx -> %08lx)  region formatted_inside=%lu\n",
           res.pi_cleanup_performed, res.pi_cleanup_ok, res.pi_cleanup_sticky,
           (unsigned long)res.cleanup_intsr_before, (unsigned long)res.cleanup_intsr_after,
           (unsigned long)(res.log_count_window_end - res.log_count_window_start));
    for (n = 0; n < GBP_INITIRQA_SNAPSHOTS; n++) print_snap(&res.snap[n]);
    printf("  errors=%u transfers=%lu timeouts=%lu busy=%lu log=%u dropped=%u truncated=%u\n",
           res.errors, (unsigned long)hsp.transfers, (unsigned long)hsp.timeouts,
           (unsigned long)hsp.busy_refusals, (unsigned)rl.count, (unsigned)rl.dropped, (unsigned)rl.truncated);
    if (res.power_cycle_required) {
        printf("\n  ******************************************************************\n");
        printf("  *  POWER CYCLE REQUIRED after this run (experimental write made)  *\n");
        printf("  *  save with X, START to exit, then switch the console OFF.       *\n");
        printf("  ******************************************************************\n");
    } else {
        printf("\n  No experimental write was attempted (power cycle still recommended).\n");
    }
    printf("\n  X = save log to SD2SP2      START = exit\n\n");

    for (i = 0; i < rl.count; i++) {
        snprintf(line, sizeof line, "OPENGBP-INITIRQA LOG %s\n", ringlog_line(&rl, i));
        gecko_puts(line);
    }
    snprintf(line, sizeof line, "OPENGBP-INITIRQA %s\n", summary);
    gecko_puts(line);

    for (;;) {
        u32 down;
        VIDEO_WaitVSync();
        PAD_ScanPads();
        down = PAD_ButtonsDown(0);
        if (down & PAD_BUTTON_START) {
            gecko_puts("OPENGBP-INITIRQA EXIT reason=start\n");
            break;
        }
        if ((down & PAD_BUTTON_X) && !saved) {
            char path[128] = "";
            char extra[128];
            int rc;
            snprintf(extra, sizeof extra, "libogc=%s gecko=%d power_cycle_required=%d", _V_STRING, gecko_present,
                     res.power_cycle_required);
            rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl,
                            status, sizeof status, path, sizeof path);
            saved = (rc == 0);
            printf("\x1b[27;1H  SD: %s\n", status);
            snprintf(line, sizeof line, "OPENGBP-INITIRQA SAVE rc=%d %s\n", rc, status);
            gecko_puts(line);
        }
    }
    printf("\n  Exiting.%s\n", res.power_cycle_required ? " POWER CYCLE REQUIRED." : "");
    VIDEO_WaitVSync();
    exit(0);
}
