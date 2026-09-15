/*
 * Open-GBP GBP-INIT-003B — delivery of a latched HSP cause to the CPU as
 * IRQ 26: the GBP-INIT-003A sequence verbatim (PI masked, no handler)
 * until INTSR bit 13 = 1 is observed, then one handler install, one
 * __UnmaskIrq, the extended one-shot handler, the device acknowledge and
 * the 003A teardown extended by the handler restore and the mask check.
 *
 * See src/gbp/gbp_initirqb_probe.h for the experiment and its rules, and
 * poc/gbp-init-irq-deliver-probe/README.md for the procedure. This file is
 * only the GameCube glue: console, identity, the base HSP backend (DMA, PI
 * reads, INTSR W1C, time base — src/platform/hsp_backend.c) plus the
 * interrupt-path object hsp_backend_irq.c in its extended form
 * (hsp_backend_irq_transport_ext: IRQ_Request install/restore, __MaskIrq,
 * __UnmaskIrq, the record copy; the one-shot body registered is
 * hsp_backend_oneshot_isr_ext). hsp_backend_intmr.c (a direct INTMR
 * store) is NOT linked: INTMR changes only through libogc2's mask API.
 * USB Gecko dump, SD save on X, START to exit. Nothing is read from the
 * controller before the probe has returned from its teardown; SD I/O
 * happens only in the X/START loop afterwards. Any run that attempted an
 * experimental CONTROL or IRQ write ends with "POWER CYCLE REQUIRED" on
 * screen.
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
#include "gbp_initirqb_probe.h"
#include "hsp_backend.h"
#include "hsp_backend_irq.h"
#include "sdlog.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-init-irq-deliver-probe"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-INIT-003B"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT app=" OPENGBP_APP_NAME " build=" OPENGBP_BUILD_ID " commit=" OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1
#define LOG_LINES 224
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

static unsigned b13(uint32_t v)
{
    return (v & GBP_PI_HSP_BIT) ? 1u : 0u;
}

static const char *wr(const struct gbp_regwrite_result *w)
{
    return w->completed ? "ok" : w->attempted ? "FAIL" : "-";
}

/* two snapshots on one line: PI bit 13 (both samples), CONTROL vote, IRQ (GBI reading / Disc reading) */
static void print_snap2(const struct gbp_initirqa_snapshot *a, const struct gbp_initirqa_snapshot *b)
{
    const struct gbp_initirqa_snapshot *s[2] = { a, b };
    unsigned i;
    printf(" ");
    for (i = 0; i < 2; i++) {
        if (!s[i] || !s[i]->taken) { printf("  %-9s -", s[i] ? s[i]->id : "-"); continue; }
        printf("  %-9s i13=%u%s m13=%u ctl=%02x irq=%04x/%04x", s[i]->id, b13(s[i]->intsr),
               s[i]->pi2_ok ? (b13(s[i]->intsr2) ? "/1" : "/0") : "", b13(s[i]->intmr),
               s[i]->control_vote, s[i]->irq_gbi, s[i]->irq_disc);
    }
    printf("\n");
}

int main(void)
{
    struct ringlog rl;
    struct hsp_backend hsp;
    struct gbp_transport t;
    struct gbp_initirqb_config cfg;
    struct gbp_initirqb_result res;
    char summary[1400];
    char line[sizeof summary + 64];   /* holds a gecko-prefixed log line or the summary */
    char status[160] = "not saved (press X)";
    char ident_text[OPENGBP_IDENT_MAX];
    const struct opengbp_ident ident = { OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT };
    const struct gbp_initirqa_result *a;
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

    snprintf(line, sizeof line, "OPENGBP-INITIRQB READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    gbp_initirqb_config_default(&cfg);
    gbp_initirqb_config_timebase(&cfg, (uint32_t)TB_TIMER_CLOCK * 1000u);

    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s app=%s build=%s commit=%s libogc=%s", TEST_ID,
                   OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, _V_STRING);
    ringlog_printf(&rl, "ENV bus_hz=%lu tb_hz=%lu dma_timeout_ms=%u t_max_ms=%lu t_delivery_ms=%lu t_delivery_ticks=%lu a1_obs_us=%lu,%lu a2_obs_us=%lu,%lu,%lu,%lu,%lu,%lu csr=%04x",
                   (unsigned long)*(vu32 *)0x800000F8, (unsigned long)cfg.a.tb_hz, (unsigned)DMA_TIMEOUT_MS,
                   (unsigned long)cfg.a.t_max_ms, (unsigned long)cfg.t_delivery_ms, (unsigned long)cfg.t_delivery_ticks,
                   (unsigned long)cfg.a.a1_obs_us[0], (unsigned long)cfg.a.a1_obs_us[1],
                   (unsigned long)cfg.a.a2_obs_us[0], (unsigned long)cfg.a.a2_obs_us[1], (unsigned long)cfg.a.a2_obs_us[2],
                   (unsigned long)cfg.a.a2_obs_us[3], (unsigned long)cfg.a.a2_obs_us[4], (unsigned long)cfg.a.a2_obs_us[5],
                   (unsigned)hsp_backend_read_csr());

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);          /* base operations: DMA, PI reads, INTSR W1C, time base */
    hsp_backend_irq_transport_ext(&hsp, &t);  /* IRQ_Request install/restore, __MaskIrq, __UnmaskIrq, record copy; extended one-shot body */

    printf("  Sequence: the 003A programming sequence verbatim, PI masked (AR_INFO exp=3 -> gate -> PI -> BASE -> CONTROL -> P0 -> A1 -> A2)\n");
    printf("            -> INTSR bit 13 = 1 (EVENT) -> IRQ_Request(26) -> PREUNMASK -> __UnmaskIrq x1 -> one-shot handler (mask, W1C x1)\n");
    printf("            -> __MaskIrq -> PREACK -> IRQ := read|%04x -> POSTACK -> restore CONTROL -> stop -> PI -> handler restore -> AR_INFO\n",
           cfg.ack_or);
    printf("  Running, do not press anything ...\n");

    gbp_initirqb_probe_run(&t, &rl, &cfg, &res);     /* returns only after the teardown */
    a = &res.a;

    ringlog_printf(&rl, "STATS transfers=%lu timeouts=%lu busy=%lu", (unsigned long)hsp.transfers,
                   (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals);
    gbp_initirqb_summary(&res, summary, sizeof summary);

    printf("\n  status=%s reason=%s restore=%s (%s)\n", res.status_name,
           res.reason ? res.reason : "-", res.restore_ok ? "ok" : "ERROR", res.restore_reason ? res.restore_reason : "-");
    printf("  presence=%s (vote %u/%u)  AR_INFO %04x->%04x->%04x restored=%s  PI pre %08lx/%08lx  CONTROL %02x->%02x written=%d restored=%s\n",
           gbp_verdict_name(a->det.verdict), a->det.vote_ok, a->det.run, a->arinfo_orig, a->arinfo_exp, a->arinfo_final,
           a->arinfo_restore_ok == 1 ? "yes" : a->arinfo_restore_ok == 0 ? "NO" : "n/a",
           (unsigned long)a->intsr_pre, (unsigned long)a->intmr_pre, a->control_orig, a->control_exp, a->control_written,
           a->control_restore_ok == -1 ? "n/a" : a->control_restore_ok ? "yes" : "NO");
    printf("  IRQ a1pre=%04x A1=%04x(%s) a2pre=%04x A2=0000(%s) stop_pre=%04x STOP=%04x(%s) post=%04x masks=%d b15=%d\n",
           a->irq_a1pre.gbi, a->ack_value, wr(&a->w_a1), a->irq_a2pre.gbi, wr(&a->w_a2),
           a->irq_stop_pre.gbi, a->stop_value, wr(&a->w_stop), a->irq_stop_post.gbi, a->stop_masks_readback, a->stop_bit15_readback);
    printf("  cause: intsr13_seen=%d first=%s t_first=%lu event=%d since_a2=%lu ticks  polls a1=%u a2=%u\n",
           a->intsr13_seen, a->first_intsr13_phase ? a->first_intsr13_phase : "-", (unsigned long)a->t_first_intsr13,
           a->event_taken, (unsigned long)(uint32_t)(a->t_first_intsr13 - a->t_a2), a->a1_polls, a->a2_polls);
    printf("  handler: installed=%d old=%s preunmask=%d/%s unmasked=%d t_unmask=%lu fired=%d count=%lu latency=%lu ticks (%lu us) timeout=%d\n",
           res.handler_was_installed, res.old_handler_null == 1 ? "null" : res.old_handler_null == 0 ? "nonnull" : "?",
           res.preunmask_ok, res.preunmask_reason ? res.preunmask_reason : "-", res.irq_unmasked, (unsigned long)res.t_unmask,
           res.fired, (unsigned long)res.rec.count, (unsigned long)res.latency_ticks, (unsigned long)res.latency_us, res.timed_out);
    printf("  ISR: intsr13 entry=%u before_w1c=%u after_w1c=%u second=%u  intmr13 entry=%u after_mask=%u second=%u  dt_second=%lu reentry=%d\n",
           b13(res.rec.intsr_before_ack), b13(res.rec.intsr_before_w1c), b13(res.rec.intsr_after_ack), b13(res.rec.intsr_second),
           b13(res.rec.intmr_at_entry), b13(res.rec.intmr_after_mask), b13(res.rec.intmr_second),
           (unsigned long)(uint32_t)(res.rec.t_second - res.rec.t_entry), res.reentry);
    printf("  main: remask ok=%d retry=%d  ACK=%04x(%s) skipped=%d(%s)  main_w1c=%d site=%s sticky=%d\n",
           res.main_mask_ok, res.remask_retry, res.ack_value, wr(&res.w_ack), res.ack_skipped,
           res.ack_skip_reason ? res.ack_skip_reason : "-", res.main_pi_w1c, res.main_pi_w1c_site ? res.main_pi_w1c_site : "-",
           res.main_w1c_sticky);
    print_snap2(&a->snap[GBP_INITIRQA_SNAP_EVENT], &res.preunmask);
    print_snap2(&res.preack, &res.postack);
    printf("  writes attempted/completed: CONTROL %d/%d  A1 %d/%d  A2 %d/%d  ACK %d/%d  STOP %d/%d  restore %d/%d  uncertain=%u%s\n",
           a->w_ctl_exp.attempted, a->w_ctl_exp.completed, a->w_a1.attempted, a->w_a1.completed,
           a->w_a2.attempted, a->w_a2.completed, res.w_ack.attempted, res.w_ack.completed,
           a->w_stop.attempted, a->w_stop.completed, a->w_ctl_restore.attempted, a->w_ctl_restore.completed,
           res.uncertain_writes, res.uncertain_writes ? "  DEVICE STATE UNCERTAIN" : "");
    printf("  restore: control=%d stop=%d cleanup performed=%d sticky=%d handler_restored=%d mask_ok=%d intmr_final=%08lx arinfo=%d\n",
           a->control_restore_ok, a->irq_stop_write_ok, a->pi_cleanup_performed, res.pi_sticky_final,
           res.handler_restored, res.mask_ok, (unsigned long)res.intmr_final, a->arinfo_restore_ok);
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
    printf("  X = save log to SD2SP2      START = exit\n");

    for (i = 0; i < rl.count; i++) {
        snprintf(line, sizeof line, "OPENGBP-INITIRQB LOG %s\n", ringlog_line(&rl, i));
        gecko_puts(line);
    }
    snprintf(line, sizeof line, "OPENGBP-INITIRQB %s\n", summary);
    gecko_puts(line);

    for (;;) {
        u32 down;
        VIDEO_WaitVSync();
        PAD_ScanPads();
        down = PAD_ButtonsDown(0);
        if (down & PAD_BUTTON_START) {
            gecko_puts("OPENGBP-INITIRQB EXIT reason=start\n");
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
            snprintf(line, sizeof line, "OPENGBP-INITIRQB SAVE rc=%d %s\n", rc, status);
            gecko_puts(line);
        }
    }
    printf("\n  Exiting.%s\n", res.power_cycle_required ? " POWER CYCLE REQUIRED." : "");
    VIDEO_WaitVSync();
    exit(0);
}
