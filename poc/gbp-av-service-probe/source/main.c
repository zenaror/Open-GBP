/*
 * Open-GBP GBP-AV-SERVICE-001 — the first drained service of the GBP HSP
 * interrupt: the GBP-INIT-003A sequence verbatim (PI masked, no handler)
 * until INTSR bit 13 = 1, then ONE handler install (the 003B extended
 * one-shot), one unmask, one delivery, the main re-mask, the PRESVC snapshot,
 * the whole-block reads of the pending AUDIO (0x1000) and VIDEO (0xF00)
 * blocks into static RAM buffers, the device ACK `pending | 0x8000` from the
 * PRESVC value, POSTACK, the single main W1C if needed, the re-arm `IRQ :=
 * 0x0000`, REARMPOST, the next cause observed while masked (never delivered),
 * and the 003A teardown extended by the handler restore and the mask check.
 *
 * See src/gbp/gbp_avsvc_probe.h for the experiment and its rules, and
 * poc/gbp-av-service-probe/README.md for the procedure. This file is only the
 * GameCube glue: console, identity, the base HSP backend (32-byte DMAs, the
 * whole-block read, PI reads, INTSR W1C, time base — src/platform/hsp_backend.c)
 * plus the 002/003B interrupt-path object hsp_backend_irq.c
 * (hsp_backend_irq_transport_ext: IRQ_Request install/restore, __MaskIrq,
 * __UnmaskIrq; the handler registered is hsp_backend_oneshot_isr_ext).
 * hsp_backend_irq_multi.c (GBP-INIT-004) and hsp_backend_intmr.c (a direct
 * INTMR store) are NOT linked: INTMR changes only through libogc2's mask API.
 * USB Gecko dump, SD save on X (the text log, then the block sidecar), START
 * to exit. Nothing is read from the controller before the probe has returned
 * from its teardown; SD I/O happens only in the X/START loop afterwards; the
 * raw block buffers are kept untouched until then. Every run that attempted an
 * experimental CONTROL or IRQ write ends with "POWER CYCLE REQUIRED" on
 * screen — a completed run too.
 *
 * Not a runtime: no framebuffer, no video conversion, no frame sync, no audio
 * playback, no KEYPAD, no SIO, no Link Port, no BBA, no Mobile Adapter, no
 * Game Pak logic, no callbacks, no unbounded loop.
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
#include "gbp_avsvc_probe.h"
#include "hsp_backend.h"
#include "hsp_backend_irq.h"
#include "sdlog.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-av-service-probe"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-AV-SERVICE-001"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT app=" OPENGBP_APP_NAME " build=" OPENGBP_BUILD_ID " commit=" OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1
#define LOG_LINES 320
#define LOG_LINE_LEN 256
#define DMA_TIMEOUT_MS 200

static char log_storage[LOG_LINES * LOG_LINE_LEN];
static uint8_t dma_buffer[GBP_BLOCK_SIZE] ATTRIBUTE_ALIGN(32);
/* the raw blocks: static, 32-byte aligned, full length; written only by the DMA engine, read only after the run */
static uint8_t audio_raw[GBP_AVBLOCK_AUDIO_LEN] ATTRIBUTE_ALIGN(32);
static uint8_t video_raw[GBP_AVBLOCK_VIDEO_LEN] ATTRIBUTE_ALIGN(32);
static uint8_t dump_buffer[GBP_AVDUMP_MAX_SIZE];

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

static const char *blk(const struct gbp_avblock *b)
{
    return !b->selected ? "not-selected" : !b->attempted ? "not-started" : b->completed ? "ok" : gbp_status_name(b->rc);
}

int main(void)
{
    struct ringlog rl;
    struct hsp_backend hsp;
    struct gbp_transport t;
    struct gbp_avsvc_config cfg;
    struct gbp_avsvc_result res;
    char summary[2000];
    char line[sizeof summary + 64];   /* holds a gecko-prefixed log line or the summary */
    char status[160] = "not saved (press X)";
    char status2[160] = "-";
    char ident_text[OPENGBP_IDENT_MAX];
    const struct opengbp_ident ident = { OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT };
    const struct gbp_initirqa_result *a;
    size_t i;
    int saved = 0;

    video_setup();
    PAD_Init();
    gecko_present = usb_isgeckoalive(GECKO_CHANNEL);
    opengbp_ident_format(ident_text, sizeof ident_text, &ident);

    printf("\n  Open-GBP " TEST_ID "  (DIRTY BUILD until release-audited: NOT A PHYSICAL CANDIDATE)\n");
    printf("  Build : %s   Commit: %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("  libogc: %s   Gecko: %s\n", _V_STRING, gecko_present ? "yes" : "no");
    printf("  %s\n\n", opengbp_ident_marker);

    snprintf(line, sizeof line, "OPENGBP-AVSVC READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    gbp_avsvc_config_default(&cfg);
    gbp_avsvc_config_timebase(&cfg, (uint32_t)TB_TIMER_CLOCK * 1000u);
    cfg.audio_buf = audio_raw; cfg.audio_cap = sizeof audio_raw;
    cfg.video_buf = video_raw; cfg.video_cap = sizeof video_raw;

    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s app=%s build=%s commit=%s libogc=%s", TEST_ID,
                   OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, _V_STRING);
    ringlog_printf(&rl, "ENV bus_hz=%lu tb_hz=%lu dma_timeout_ms=%u t_max_ms=%lu t_delivery_ms=%lu t_next_cause_ms=%lu a2_obs_us=%lu,%lu,%lu,%lu,%lu,%lu csr=%04x audio_buf=%08lx video_buf=%08lx",
                   (unsigned long)*(vu32 *)0x800000F8, (unsigned long)cfg.a.tb_hz, (unsigned)DMA_TIMEOUT_MS,
                   (unsigned long)cfg.a.t_max_ms, (unsigned long)cfg.t_delivery_ms, (unsigned long)cfg.t_next_cause_ms,
                   (unsigned long)cfg.a.a2_obs_us[0], (unsigned long)cfg.a.a2_obs_us[1], (unsigned long)cfg.a.a2_obs_us[2],
                   (unsigned long)cfg.a.a2_obs_us[3], (unsigned long)cfg.a.a2_obs_us[4], (unsigned long)cfg.a.a2_obs_us[5],
                   (unsigned)hsp_backend_read_csr(), (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(audio_raw), (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(video_raw));

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);            /* base operations: 32-byte DMA, whole-block read, PI reads, INTSR W1C, time base */
    hsp_backend_irq_transport_ext(&hsp, &t);    /* IRQ_Request install/restore, __MaskIrq, __UnmaskIrq; the 003B extended one-shot */

    printf("  Sequence: the 003A programming sequence verbatim, PI masked (AR_INFO exp=3 -> gate -> PI -> BASE -> CONTROL -> P0 -> A1 -> A2)\n");
    printf("            -> INTSR bit 13 = 1 -> IRQ_Request(26, ext) once -> PREUNMASK -> __UnmaskIrq x1 -> handler -> __MaskIrq\n");
    printf("            -> PRESVC (authoritative) -> AUDIO 0x1000 -> VIDEO 0xF00 (one DMA each) -> POSTDRAIN -> IRQ := pending|%04x\n", cfg.ack_or);
    printf("            -> POSTACK -> PI clean -> IRQ := 0000 -> REARMPOST -> next cause observed, NEVER delivered (bounds %lu ms / %lu ms)\n",
           (unsigned long)cfg.t_delivery_ms, (unsigned long)cfg.t_next_cause_ms);
    printf("            -> restore CONTROL -> stop -> PI -> handler restore -> AR_INFO\n");
    if (!gbp_transport_has_bulk_read(&t)) {
        printf("\n  FATAL: the transport has no whole-block read; nothing was run. START = exit\n");
        for (;;) { VIDEO_WaitVSync(); PAD_ScanPads(); if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break; }
        exit(1);
    }
    printf("  Running, do not press anything ...\n");

    gbp_avsvc_probe_run(&t, &rl, &cfg, &res);     /* returns only after the teardown */
    a = &res.a;

    ringlog_printf(&rl, "STATS transfers=%lu timeouts=%lu busy=%lu bulk_transfers=%lu bulk_bytes=%lu", (unsigned long)hsp.transfers,
                   (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals, (unsigned long)hsp.bulk_transfers, (unsigned long)hsp.bulk_bytes);
    gbp_avsvc_summary(&res, summary, sizeof summary);

    printf("\n  status=%s (%s) reason=%s restore=%s (%s) teardown=%s\n", res.status_name, res.status_class,
           res.reason ? res.reason : "-", res.restore_ok ? "ok" : "ERROR", res.restore_reason ? res.restore_reason : "-",
           res.teardown_variant ? res.teardown_variant : "-");
    printf("  presence=%s (vote %u/%u)  AR_INFO %04x->%04x->%04x restored=%s  PI pre %08lx/%08lx  CONTROL %02x->%02x written=%d restored=%s\n",
           gbp_verdict_name(a->det.verdict), a->det.vote_ok, a->det.run, a->arinfo_orig, a->arinfo_exp, a->arinfo_final,
           a->arinfo_restore_ok == 1 ? "yes" : a->arinfo_restore_ok == 0 ? "NO" : "n/a",
           (unsigned long)a->intsr_pre, (unsigned long)a->intmr_pre, a->control_orig, a->control_exp, a->control_written,
           a->control_restore_ok == -1 ? "n/a" : a->control_restore_ok ? "yes" : "NO");
    printf("  IRQ a1pre=%04x A1=%04x(%s) A2=0000(%s)  cause: seen=%d t_first=%lu since_a2=%lu  delivery: unmasked=%d fired=%d count=%lu latency=%lu\n",
           a->irq_a1pre.gbi, a->ack_value, wr(&a->w_a1), wr(&a->w_a2), a->intsr13_seen, (unsigned long)a->t_first_intsr13,
           (unsigned long)(uint32_t)(a->t_first_intsr13 - a->t_a2), res.d.irq_unmasked, res.d.fired, (unsigned long)res.d.rec.count,
           (unsigned long)res.d.latency_ticks);
    printf("  service: pending=%04x drain=%04x audio=%s crc32=%08lx dt=%lu  video=%s crc32=%08lx dt=%lu  postdrain=%04x relatch=%d\n",
           res.pending_irq, res.drain_mask, blk(&res.audio), (unsigned long)res.audio.crc32,
           (unsigned long)(res.audio.attempted ? (uint32_t)(res.audio.t_end - res.audio.t_start) : 0u),
           blk(&res.video), (unsigned long)res.video.crc32, (unsigned long)(res.video.attempted ? (uint32_t)(res.video.t_end - res.video.t_start) : 0u),
           res.postdrain.irq_gbi, res.relatch_postdrain);
    printf("  ack=%04x(%s) postack=%04x source_after_ack=%04x relatch=%d main_w1c=%d pi_clean=%d sticky=%d  rearm=%s rearmpost=%s %04x\n",
           res.k.ack_value, wr(&res.k.w_ack), res.k.postack.irq_gbi, res.source_after_ack, res.relatch_postack, res.k.main_pi_w1c,
           res.pi_clean, res.pi_sticky, res.rearm_attempted ? wr(&res.w_rearm) : "-", gbp_avsvc_rearmpost_name(res.rearmpost_outcome),
           res.rearmpost.irq_gbi);
    printf("  next cause: found=%d immediate=%d timed_out=%d irq=%04x dt_rearm=%lu ticks (NEVER delivered)  unexpected=%04x@%s\n",
           res.next_cause_found, res.next_cause_immediate, res.next_cause_timed_out, res.next_cause_irq,
           (unsigned long)res.dt_rearm_to_next_cause, res.unexpected, res.unexpected_site);
    printf("  W1C isr=%u main=%u teardown=%u  handler: installed=%d old=%s restored=%d mask_ok=%d intmr_final=%08lx  control_ok=%d pi_sticky=%d\n",
           res.isr_w1c, res.main_w1c, res.teardown_w1c, res.h.handler_was_installed,
           res.h.old_handler_null == 1 ? "null" : res.h.old_handler_null == 0 ? "nonnull" : "?",
           res.h.handler_restored, res.h.mask_ok, (unsigned long)res.h.intmr_final, res.control_ok, res.pi_sticky_final);
    printf("  writes attempted/completed: CONTROL %d/%d  A1 %d/%d  A2 %d/%d  ACK %d/%d  REARM %d/%d  STOP %d/%d  restore %d/%d  uncertain=%u%s\n",
           a->w_ctl_exp.attempted, a->w_ctl_exp.completed, a->w_a1.attempted, a->w_a1.completed,
           a->w_a2.attempted, a->w_a2.completed, res.k.w_ack.attempted, res.k.w_ack.completed, res.rearm_attempted, res.rearm_completed,
           a->w_stop.attempted, a->w_stop.completed, a->w_ctl_restore.attempted, a->w_ctl_restore.completed,
           res.uncertain_writes, res.uncertain_writes ? "  DEVICE STATE UNCERTAIN" : "");
    printf("  restore: control=%d stop=%d cleanup performed=%d sticky=%d arinfo=%d  errors=%u transfers=%lu bulk=%lu/%lu timeouts=%lu busy=%lu log=%u dropped=%u trunc=%u\n",
           a->control_restore_ok, a->irq_stop_write_ok, a->pi_cleanup_performed, res.pi_sticky_final, a->arinfo_restore_ok,
           res.errors, (unsigned long)hsp.transfers, (unsigned long)hsp.bulk_transfers, (unsigned long)hsp.bulk_bytes,
           (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals, (unsigned)rl.count, (unsigned)rl.dropped, (unsigned)rl.truncated);
    if (res.power_cycle_required) {
        printf("\n  ******************************************************************\n");
        printf("  *  POWER CYCLE REQUIRED after this run (experimental write made)  *\n");
        printf("  *  save with X, START to exit, then switch the console OFF.       *\n");
        printf("  ******************************************************************\n");
    } else {
        printf("\n  No experimental write was attempted (power cycle still recommended).\n");
    }
    printf("  X = save log + block sidecar to SD2SP2      START = exit\n");

    for (i = 0; i < rl.count; i++) {
        snprintf(line, sizeof line, "OPENGBP-AVSVC LOG %s\n", ringlog_line(&rl, i));
        gecko_puts(line);
    }
    snprintf(line, sizeof line, "OPENGBP-AVSVC %s\n", summary);
    gecko_puts(line);

    for (;;) {
        u32 down;
        VIDEO_WaitVSync();
        PAD_ScanPads();
        down = PAD_ButtonsDown(0);
        if (down & PAD_BUTTON_START) {
            gecko_puts("OPENGBP-AVSVC EXIT reason=start\n");
            break;
        }
        if ((down & PAD_BUTTON_X) && !saved) {
            char path[128] = "";
            char extra[160];
            struct gbp_avdump_info info;
            long n;
            int rc, rc2 = -9;
            snprintf(extra, sizeof extra, "libogc=%s gecko=%d power_cycle_required=%d sidecar=%s_%s-blocks.bin", _V_STRING, gecko_present,
                     res.power_cycle_required, TEST_ID, OPENGBP_BUILD_ID);
            rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl,
                            status, sizeof status, path, sizeof path);
            /* the sidecar: the raw blocks exactly as the DMA left them, serialized only now, outside every timed region */
            gbp_avsvc_dump_info(&res, cfg.a.tb_hz, TEST_ID, OPENGBP_BUILD_ID, OPENGBP_APP_NAME, OPENGBP_GIT_COMMIT, &info);
            n = gbp_avdump_serialize(&info, audio_raw, video_raw, dump_buffer, sizeof dump_buffer);
            if (n > 0) rc2 = sdlog_save_blob(TEST_ID, OPENGBP_BUILD_ID, "-blocks.bin", dump_buffer, (size_t)n, status2, sizeof status2, NULL, 0);
            else snprintf(status2, sizeof status2, "sidecar not serialized (rc=%ld%s)", n, n == -2 ? ": identity does not fit the format" : "");
            saved = (rc == 0 && rc2 == 0);
            printf("\x1b[26;1H  SD log   : %s\n", status);
            printf("  SD blocks: %s%s\n", status2, (rc == 0 && rc2 != 0) ? "  (PARTIAL SAVE: log only)" : "");
            snprintf(line, sizeof line, "OPENGBP-AVSVC SAVE rc=%d %s\n", rc, status);
            gecko_puts(line);
            snprintf(line, sizeof line, "OPENGBP-AVSVC SAVEBLOCKS rc=%d %s audio_crc32=%08lx video_crc32=%08lx bytes=%ld\n", rc2, status2,
                     (unsigned long)info.audio_crc32, (unsigned long)info.video_crc32, n);
            gecko_puts(line);
        }
    }
    printf("\n  Exiting.%s\n", res.power_cycle_required ? " POWER CYCLE REQUIRED." : "");
    VIDEO_WaitVSync();
    exit(0);
}
