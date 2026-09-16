/*
 * Open-GBP GBP-INIT-004 — bounded repeated service of the GBP HSP interrupt:
 * the GBP-INIT-003A sequence verbatim (PI masked, no handler) until INTSR
 * bit 13 = 1, then ONE handler install and three service cycles — unmask,
 * delivery, main re-mask, device ACK `read | 0x8000`, clean boundary, re-arm
 * `IRQ := 0x0000` (cycles 0 and 1 only), next cause — and the 003A teardown
 * extended by the handler restore and the mask check.
 *
 * See src/gbp/gbp_initirq4_probe.h for the experiment and its rules, and
 * poc/gbp-init-irq-service-probe/README.md for the procedure. This file is
 * only the GameCube glue: console, identity, the base HSP backend (DMA, PI
 * reads, INTSR W1C, time base — src/platform/hsp_backend.c) plus the
 * multi-cycle interrupt-path object hsp_backend_irq_multi.c
 * (hsp_backend_irq_transport_multi: IRQ_Request install/restore, __MaskIrq,
 * __UnmaskIrq, the generation publication, the slot copies; the handler
 * registered is hsp_backend_oneshot_isr_multi). hsp_backend_irq.c (the
 * 002/003B handlers) and hsp_backend_intmr.c (a direct INTMR store) are NOT
 * linked: INTMR changes only through libogc2's mask API. USB Gecko dump, SD
 * save on X, START to exit. Nothing is read from the controller before the
 * probe has returned from its teardown; SD I/O happens only in the X/START
 * loop afterwards. Every run that attempted an experimental CONTROL or IRQ
 * write ends with "POWER CYCLE REQUIRED" on screen — a completed run too.
 *
 * DIRTY BUILD — NOT A PHYSICAL CANDIDATE until a clean commit is rebuilt,
 * release-audited and explicitly authorized (docs/research/HARDWARE_TESTS.md).
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
#include "gbp_initirq4_probe.h"
#include "hsp_backend.h"
#include "hsp_backend_irq_multi.h"
#include "sdlog.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-init-irq-service-probe"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-INIT-004"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT app=" OPENGBP_APP_NAME " build=" OPENGBP_BUILD_ID " commit=" OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1
#define LOG_LINES 320
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

static const char *wr(const struct gbp_regwrite_result *w)
{
    return w->completed ? "ok" : w->attempted ? "FAIL" : "-";
}

/* one line per cycle: cause, delivery, ACK, boundary, re-arm, next cause */
static void print_cycle(const struct gbp_initirq4_cycle *c)
{
    if (!c->started) { printf("  cycle %u: not started\n", c->index); return; }
    printf("  cycle %u: cause=%04x%s fired=%d n=%lu lat=%lu ack=%04x(%s) post=%04x w1c=%d bnd=%d rearm=%s post=%s next=%s\n",
           c->index, c->cause_irq, c->cause_immediate ? "!" : "", c->d.fired, (unsigned long)c->d.rec.count,
           (unsigned long)c->d.latency_ticks, c->k.ack_value, wr(&c->k.w_ack), c->k.postack.irq_gbi, c->k.main_pi_w1c,
           c->boundary_ok, c->rearm_attempted ? wr(&c->w_rearm) : "-", gbp_initirq4_rearmpost_name(c->rearmpost_outcome),
           c->cause_timed_out ? "timeout" : c->dt_rearm_to_next_cause ? "found" : "-");
}

int main(void)
{
    struct ringlog rl;
    struct hsp_backend hsp;
    struct gbp_transport t;
    struct gbp_initirq4_config cfg;
    struct gbp_initirq4_result res;
    char summary[1600];
    char line[sizeof summary + 64];   /* holds a gecko-prefixed log line or the summary */
    char status[160] = "not saved (press X)";
    char ident_text[OPENGBP_IDENT_MAX];
    const struct opengbp_ident ident = { OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT };
    const struct gbp_initirqa_result *a;
    size_t i;
    unsigned n;
    int saved = 0;

    video_setup();
    PAD_Init();
    gecko_present = usb_isgeckoalive(GECKO_CHANNEL);
    opengbp_ident_format(ident_text, sizeof ident_text, &ident);

    printf("\n  Open-GBP " TEST_ID "  (DIRTY BUILD until release-audited: NOT A PHYSICAL CANDIDATE)\n");
    printf("  Build : %s   Commit: %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("  libogc: %s   Gecko: %s\n", _V_STRING, gecko_present ? "yes" : "no");
    printf("  %s\n\n", opengbp_ident_marker);

    snprintf(line, sizeof line, "OPENGBP-INITIRQ4 READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    gbp_initirq4_config_default(&cfg);
    gbp_initirq4_config_timebase(&cfg, (uint32_t)TB_TIMER_CLOCK * 1000u);

    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s app=%s build=%s commit=%s libogc=%s", TEST_ID,
                   OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, _V_STRING);
    ringlog_printf(&rl, "ENV bus_hz=%lu tb_hz=%lu dma_timeout_ms=%u t_max_ms=%lu t_delivery_ms=%lu t_next_cause_ms=%lu max_cycles=%u max_rearms=%u a2_obs_us=%lu,%lu,%lu,%lu,%lu,%lu csr=%04x",
                   (unsigned long)*(vu32 *)0x800000F8, (unsigned long)cfg.a.tb_hz, (unsigned)DMA_TIMEOUT_MS,
                   (unsigned long)cfg.a.t_max_ms, (unsigned long)cfg.t_delivery_ms, (unsigned long)cfg.t_next_cause_ms,
                   cfg.max_cycles, cfg.max_rearms,
                   (unsigned long)cfg.a.a2_obs_us[0], (unsigned long)cfg.a.a2_obs_us[1], (unsigned long)cfg.a.a2_obs_us[2],
                   (unsigned long)cfg.a.a2_obs_us[3], (unsigned long)cfg.a.a2_obs_us[4], (unsigned long)cfg.a.a2_obs_us[5],
                   (unsigned)hsp_backend_read_csr());

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);            /* base operations: DMA, PI reads, INTSR W1C, time base */
    hsp_backend_irq_transport_multi(&hsp, &t);  /* IRQ_Request install/restore, __MaskIrq, __UnmaskIrq, generation, slot copies */

    printf("  Sequence: the 003A programming sequence verbatim, PI masked (AR_INFO exp=3 -> gate -> PI -> BASE -> CONTROL -> P0 -> A1 -> A2)\n");
    printf("            -> INTSR bit 13 = 1 -> IRQ_Request(26) once -> per cycle: PREPARE gen -> PREUNMASK -> __UnmaskIrq x1 -> handler\n");
    printf("            -> __MaskIrq -> PREACK -> IRQ := read|%04x -> POSTACK clean -> [cycles 0,1] IRQ := 0000 -> REARMPOST -> next cause\n", cfg.ack_or);
    printf("            -> after cycle %u: restore CONTROL -> stop -> PI -> handler restore -> AR_INFO   (bounds %lu ms / %lu ms)\n",
           cfg.max_cycles - 1u, (unsigned long)cfg.t_delivery_ms, (unsigned long)cfg.t_next_cause_ms);
    printf("  Running, do not press anything ...\n");

    gbp_initirq4_probe_run(&t, &rl, &cfg, &res);     /* returns only after the teardown */
    a = &res.a;

    ringlog_printf(&rl, "STATS transfers=%lu timeouts=%lu busy=%lu", (unsigned long)hsp.transfers,
                   (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals);
    gbp_initirq4_summary(&res, summary, sizeof summary);

    printf("\n  status=%s reason=%s restore=%s (%s) teardown=%s\n", res.status_name,
           res.reason ? res.reason : "-", res.restore_ok ? "ok" : "ERROR", res.restore_reason ? res.restore_reason : "-",
           res.teardown_variant ? res.teardown_variant : "-");
    printf("  presence=%s (vote %u/%u)  AR_INFO %04x->%04x->%04x restored=%s  PI pre %08lx/%08lx  CONTROL %02x->%02x written=%d restored=%s\n",
           gbp_verdict_name(a->det.verdict), a->det.vote_ok, a->det.run, a->arinfo_orig, a->arinfo_exp, a->arinfo_final,
           a->arinfo_restore_ok == 1 ? "yes" : a->arinfo_restore_ok == 0 ? "NO" : "n/a",
           (unsigned long)a->intsr_pre, (unsigned long)a->intmr_pre, a->control_orig, a->control_exp, a->control_written,
           a->control_restore_ok == -1 ? "n/a" : a->control_restore_ok ? "yes" : "NO");
    printf("  IRQ a1pre=%04x A1=%04x(%s) A2=0000(%s) stop_pre=%04x STOP=%04x(%s) post=%04x  cause: seen=%d t_first=%lu since_a2=%lu\n",
           a->irq_a1pre.gbi, a->ack_value, wr(&a->w_a1), wr(&a->w_a2), a->irq_stop_pre.gbi, a->stop_value, wr(&a->w_stop),
           a->irq_stop_post.gbi, a->intsr13_seen, (unsigned long)a->t_first_intsr13, (unsigned long)(uint32_t)(a->t_first_intsr13 - a->t_a2));
    printf("  cycles %u/%u completed=%u deliveries=%u acks=%u rearms=%u/%u next_causes=%u unexpected=%u reentry=%u timeouts=%u gen_err=%u\n",
           res.cycles_started, res.cycles_requested, res.completed_cycles, res.deliveries, res.acks, res.rearms_completed,
           res.rearms_attempted, res.next_causes, res.unexpected_sources, res.reentries, res.timeouts, res.generation_errors);
    for (n = 0; n < GBP_INITIRQ4_MAX_CYCLES; n++) print_cycle(&res.cycles[n]);
    printf("  W1C isr=%u main=%u teardown=%u  handler: installed=%d old=%s restored=%d mask_ok=%d intmr_final=%08lx  control_ok=%d pi_sticky=%d\n",
           res.isr_w1c, res.main_w1c, res.teardown_w1c, res.h.handler_was_installed,
           res.h.old_handler_null == 1 ? "null" : res.h.old_handler_null == 0 ? "nonnull" : "?",
           res.h.handler_restored, res.h.mask_ok, (unsigned long)res.h.intmr_final, res.control_ok, res.pi_sticky_final);
    printf("  writes attempted/completed: CONTROL %d/%d  A1 %d/%d  A2 %d/%d  ACK %u  REARM %u/%u  STOP %d/%d  restore %d/%d  uncertain=%u%s\n",
           a->w_ctl_exp.attempted, a->w_ctl_exp.completed, a->w_a1.attempted, a->w_a1.completed,
           a->w_a2.attempted, a->w_a2.completed, res.acks, res.rearms_attempted, res.rearms_completed,
           a->w_stop.attempted, a->w_stop.completed, a->w_ctl_restore.attempted, a->w_ctl_restore.completed,
           res.uncertain_writes, res.uncertain_writes ? "  DEVICE STATE UNCERTAIN" : "");
    printf("  restore: control=%d stop=%d cleanup performed=%d sticky=%d arinfo=%d  errors=%u transfers=%lu timeouts=%lu busy=%lu log=%u dropped=%u trunc=%u\n",
           a->control_restore_ok, a->irq_stop_write_ok, a->pi_cleanup_performed, res.pi_sticky_final, a->arinfo_restore_ok,
           res.errors, (unsigned long)hsp.transfers, (unsigned long)hsp.timeouts,
           (unsigned long)hsp.busy_refusals, (unsigned)rl.count, (unsigned)rl.dropped, (unsigned)rl.truncated);
    if (res.power_cycle_required || res.completed_cycles) {
        printf("\n  ******************************************************************\n");
        printf("  *  POWER CYCLE REQUIRED after this run (experimental write made)  *\n");
        printf("  *  save with X, START to exit, then switch the console OFF.       *\n");
        printf("  ******************************************************************\n");
    } else {
        printf("\n  No experimental write was attempted (power cycle still recommended).\n");
    }
    printf("  X = save log to SD2SP2      START = exit\n");

    for (i = 0; i < rl.count; i++) {
        snprintf(line, sizeof line, "OPENGBP-INITIRQ4 LOG %s\n", ringlog_line(&rl, i));
        gecko_puts(line);
    }
    snprintf(line, sizeof line, "OPENGBP-INITIRQ4 %s\n", summary);
    gecko_puts(line);

    for (;;) {
        u32 down;
        VIDEO_WaitVSync();
        PAD_ScanPads();
        down = PAD_ButtonsDown(0);
        if (down & PAD_BUTTON_START) {
            gecko_puts("OPENGBP-INITIRQ4 EXIT reason=start\n");
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
            snprintf(line, sizeof line, "OPENGBP-INITIRQ4 SAVE rc=%d %s\n", rc, status);
            gecko_puts(line);
        }
    }
    printf("\n  Exiting.%s\n", res.power_cycle_required ? " POWER CYCLE REQUIRED." : "");
    VIDEO_WaitVSync();
    exit(0);
}
