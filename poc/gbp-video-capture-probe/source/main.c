/*
 * Open-GBP GBP-VIDEO-001 — bounded VIDEO block-sequence capture under the
 * repeated drained service of the GBP HSP interrupt: the GBP-INIT-003A
 * sequence verbatim (PI masked, no handler) until INTSR bit 13 = 1, then ONE
 * handler install (the 003B extended one-shot) and a bounded loop of
 * admitted cycles — CHECK_ADMISSION → PREPARE (record reset, memory only) →
 * UNMASK → CONFIRM → READ → AUDIO 0x1000 → VIDEO 0xF00 → ACK `pending |
 * 0x8000` → PI clean → re-arm `IRQ := 0x0000` → WAIT_NEXT (masked, read-only)
 * — until the capture target (88 VIDEO blocks), the delivery cap (320), the
 * service-loop admission budget (1000 ms) or an absent next cause ends it;
 * then the 003A teardown extended by the handler restore and the mask check.
 *
 * See src/gbp/gbp_video_probe.h for the experiment and its rules,
 * src/gbp/gbp_avseq.h for the records and buffers, and
 * poc/gbp-video-capture-probe/README.md for the procedure. This file is only
 * the GameCube glue: console, identity, the base HSP backend (32-byte DMAs,
 * the whole-block read, PI reads, INTSR W1C, time base —
 * src/platform/hsp_backend.c) plus the 002/003B interrupt-path object
 * hsp_backend_irq.c (hsp_backend_irq_transport_ext: IRQ_Request
 * install/restore, __MaskIrq, __UnmaskIrq, the memory-only record reset; the
 * handler registered is hsp_backend_oneshot_isr_ext). hsp_backend_irq_multi.c
 * (GBP-INIT-004) and hsp_backend_intmr.c (a direct INTMR store) are NOT
 * linked: INTMR changes only through libogc2's mask API.
 *
 * USB Gecko dump, SD save on X (the text log, then the sequence sidecar
 * `OGBPSEQ1`), START to exit. Nothing is read from the controller before the
 * probe has returned from its teardown; SD I/O happens only in the X/START
 * loop afterwards; the raw block buffers are kept untouched until then. Every
 * run that attempted an experimental CONTROL or IRQ write ends with "POWER
 * CYCLE REQUIRED" on screen — a completed run too.
 *
 * Not a runtime: no framebuffer, no video conversion, no frame sync, no audio
 * playback, no KEYPAD, no SIO, no Link Port, no BBA, no Mobile Adapter, no
 * Game Pak logic, no callbacks, no unbounded loop, no malloc. The content of
 * the captured blocks is never compared with anything on the console: the
 * offline tool tools/avseq.py is the only oracle.
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
#include "gbp_video_probe.h"
#include "hsp_backend.h"
#include "hsp_backend_irq.h"
#include "sdlog.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-video-capture-probe"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-VIDEO-001"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT app=" OPENGBP_APP_NAME " build=" OPENGBP_BUILD_ID " commit=" OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1
/* The ring must hold the WORST reachable run without dropping a line, because a dropped line
 * would break the log -> fixture -> replay chain of a physical run. Worst case, derived from the
 * design bounds and confirmed by tests/unit/test_gbp_video.c:
 *     stage and identity                              ~45
 *     4 verify cycles, full AVSVC records          4 x ~70 = 280
 *     316 lean cycles x 6 records (CYCU CYCW CYCH RAW CYCD CYCR) = 1896
 *     VBLK (<= 88) + ABLK (<= 320)                    408
 *     boundaries (chunked when long) and summaries     ~29
 *                                                   ------
 *                                                    ~2658
 * The measured maximum over the reachable source patterns is 2614 lines (320 deliveries with
 * VIDEO on roughly one cycle in four). 3000 lines leaves ~13% margin. */
#define LOG_LINES 3000
#define LOG_LINE_LEN 256
#define DMA_TIMEOUT_MS 200

static char log_storage[LOG_LINES * LOG_LINE_LEN];
static uint8_t dma_buffer[GBP_BLOCK_SIZE] ATTRIBUTE_ALIGN(32);
/* the raw blocks: static, 32-byte aligned, full length, one slot per captured VIDEO block and
 * the AUDIO ping-pong set; written only by the DMA engine, read only after the run */
static uint8_t video_blocks[GBP_AVSEQ_MAX_VIDEO_BLOCKS][GBP_AVSEQ_VIDEO_BLOCK_SIZE] ATTRIBUTE_ALIGN(32);
static uint8_t audio_raw[GBP_AVSEQ_AUDIO_RAW_SLOTS][GBP_AVSEQ_AUDIO_BLOCK_SIZE] ATTRIBUTE_ALIGN(32);
static uint8_t dump_buffer[GBP_AVSEQDUMP_MAX_SIZE];
static struct gbp_avseq_store seq_store;

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

int main(void)
{
    struct ringlog rl;
    struct hsp_backend hsp;
    struct gbp_transport t;
    struct gbp_video_config cfg;
    static struct gbp_video_result res;      /* large (the 003A result and four snapshots): not on the stack */
    static char summary[2400];
    static char line[sizeof summary + 64];   /* holds a gecko-prefixed log line or the summary */
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

    snprintf(line, sizeof line, "OPENGBP-VIDEO READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    gbp_video_config_default(&cfg);
    gbp_video_config_timebase(&cfg, (uint32_t)TB_TIMER_CLOCK * 1000u);
    gbp_avseq_store_init(&seq_store, &video_blocks[0][0], sizeof video_blocks, &audio_raw[0][0], sizeof audio_raw);
    cfg.store = &seq_store;

    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s app=%s build=%s commit=%s libogc=%s", TEST_ID,
                   OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, _V_STRING);
    ringlog_printf(&rl, "ENV bus_hz=%lu tb_hz=%lu dma_timeout_ms=%u t_max_ms=%lu t_delivery_ms=%lu t_next_cause_ms=%lu budget_ms=%lu csr=%04x",
                   (unsigned long)*(vu32 *)0x800000F8, (unsigned long)cfg.a.tb_hz, (unsigned)DMA_TIMEOUT_MS,
                   (unsigned long)cfg.a.t_max_ms, (unsigned long)cfg.t_delivery_ms, (unsigned long)cfg.t_next_cause_ms,
                   (unsigned long)cfg.admission_budget_ms, (unsigned)hsp_backend_read_csr());
    ringlog_printf(&rl, "ENVBUF video_slots=%u video_block=%04lx video_buf=%08lx audio_slots=%u audio_block=%04lx audio_buf=%08lx seq_max=%lu log_lines=%u",
                   (unsigned)GBP_AVSEQ_MAX_VIDEO_BLOCKS, (unsigned long)GBP_AVSEQ_VIDEO_BLOCK_SIZE,
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(&video_blocks[0][0]), (unsigned)GBP_AVSEQ_AUDIO_RAW_SLOTS,
                   (unsigned long)GBP_AVSEQ_AUDIO_BLOCK_SIZE, (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(&audio_raw[0][0]),
                   (unsigned long)GBP_AVSEQDUMP_MAX_SIZE, (unsigned)LOG_LINES);
    ringlog_printf(&rl, "ENVA2 a2_obs_us=%lu,%lu,%lu,%lu,%lu,%lu",
                   (unsigned long)cfg.a.a2_obs_us[0], (unsigned long)cfg.a.a2_obs_us[1], (unsigned long)cfg.a.a2_obs_us[2],
                   (unsigned long)cfg.a.a2_obs_us[3], (unsigned long)cfg.a.a2_obs_us[4], (unsigned long)cfg.a.a2_obs_us[5]);

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);            /* base operations: 32-byte DMA, whole-block read, PI reads, INTSR W1C, time base */
    hsp_backend_irq_transport_ext(&hsp, &t);    /* IRQ_Request install/restore, __MaskIrq, __UnmaskIrq, the record reset; the 003B extended one-shot */

    printf("  Sequence: the 003A programming sequence verbatim, PI masked (AR_INFO exp=3 -> gate -> PI -> BASE -> CONTROL -> P0 -> A1 -> A2)\n");
    printf("            -> INTSR bit 13 = 1 -> IRQ_Request(26, ext) ONCE -> PREUNMASK\n");
    printf("            -> repeated: admit -> record reset -> __UnmaskIrq x1 -> handler -> __MaskIrq -> READ -> AUDIO %04lx -> VIDEO %04lx\n",
           (unsigned long)cfg.audio_len, (unsigned long)cfg.video_len);
    printf("               -> IRQ := pending|%04x -> PI clean -> IRQ := 0000 -> next cause observed while masked (never delivered)\n", cfg.ack_or);
    printf("            -> until %u VIDEO blocks / %u deliveries / %lu ms admission budget / no next cause within %lu ms\n",
           cfg.target_video_blocks, cfg.max_deliveries, (unsigned long)cfg.admission_budget_ms, (unsigned long)cfg.t_next_cause_ms);
    printf("            -> restore CONTROL -> stop -> PI -> handler restore -> AR_INFO\n");
    if (!gbp_transport_has_bulk_read(&t) || !gbp_transport_has_irq_reset(&t)) {
        printf("\n  FATAL: the transport lacks the whole-block read or the record reset; nothing was run. START = exit\n");
        for (;;) { VIDEO_WaitVSync(); PAD_ScanPads(); if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break; }
        exit(1);
    }
    printf("  Running, do not press anything ...\n");

    gbp_video_probe_run(&t, &rl, &cfg, &res);     /* returns only after the teardown */
    a = &res.a;

    ringlog_printf(&rl, "STATS transfers=%lu timeouts=%lu busy=%lu bulk_transfers=%lu bulk_bytes=%lu", (unsigned long)hsp.transfers,
                   (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals, (unsigned long)hsp.bulk_transfers, (unsigned long)hsp.bulk_bytes);
    gbp_video_summary(&res, summary, sizeof summary);

    printf("\n  status=%s (%s) reason=%s restore=%s (%s) teardown=%s\n", res.status_name, res.status_class,
           res.reason ? res.reason : "-", res.restore_ok ? "ok" : "ERROR", res.restore_reason ? res.restore_reason : "-",
           res.teardown_variant ? res.teardown_variant : "-");
    printf("  presence=%s (vote %u/%u)  AR_INFO %04x->%04x->%04x restored=%s  CONTROL %02x->%02x written=%d restored=%s\n",
           gbp_verdict_name(a->det.verdict), a->det.vote_ok, a->det.run, a->arinfo_orig, a->arinfo_exp, a->arinfo_final,
           a->arinfo_restore_ok == 1 ? "yes" : a->arinfo_restore_ok == 0 ? "NO" : "n/a",
           a->control_orig, a->control_exp, a->control_written,
           a->control_restore_ok == -1 ? "n/a" : a->control_restore_ok ? "yes" : "NO");
    printf("  IRQ a1pre=%04x A1=%04x(%s) A2=0000(%s)  first cause: seen=%d t_first=%lu since_a2=%lu  cause_to_isr=%lu ticks\n",
           a->irq_a1pre.gbi, a->ack_value, wr(&a->w_a1), wr(&a->w_a2), a->intsr13_seen, (unsigned long)a->t_first_intsr13,
           (unsigned long)(uint32_t)(a->t_first_intsr13 - a->t_a2), (unsigned long)res.dt_cause_to_isr_first);
    printf("  MATRIX  service=%s (%s)  capture=%s  next_cause_at_end=%d  restore=%s  reference_content=offline (tools/avseq.py)\n",
           res.service_ok ? "ok" : "FAILED", res.service_reason, gbp_avseq_end_name(res.capture), res.next_cause_at_end,
           res.restore_ok ? "ok" : "FAILED");
    printf("  capture: deliveries=%u  VIDEO %u/%u blocks  AUDIO %u/%u drains (raw kept %u)  verify=%u lean=%u  admissions=%u refusals=%u (%s)\n",
           res.deliveries, res.video_completed, res.video_blocks, res.audio_completed, res.audio_drains,
           gbp_avseq_audio_raw_count(&seq_store), res.verify_cycles_done, res.lean_cycles, res.admissions, res.refusals, res.refusal);
    printf("  boundaries: GBI %u (complete interval %s)   Disc %u (complete interval %s)\n",
           res.b_gbi.count, res.b_gbi.complete_interval ? "yes" : "no", res.b_disc.count, res.b_disc.complete_interval ? "yes" : "no");
    if (res.b_gbi.count >= 2) printf("              GBI  first intervals: %u %u %u\n", res.b_gbi.intervals[0],
                                     res.b_gbi.intervals_n > 1 ? res.b_gbi.intervals[1] : 0, res.b_gbi.intervals_n > 2 ? res.b_gbi.intervals[2] : 0);
    if (res.b_disc.count >= 2) printf("              Disc first intervals: %u %u %u\n", res.b_disc.intervals[0],
                                      res.b_disc.intervals_n > 1 ? res.b_disc.intervals[1] : 0, res.b_disc.intervals_n > 2 ? res.b_disc.intervals[2] : 0);
    printf("  budget: t0=%lu deadline=%lu (%lu ms)  acks=%u rearms=%u  W1C isr=%u main=%u teardown=%u  unexpected=%04x@%s\n",
           (unsigned long)res.t0, (unsigned long)res.admission_deadline, (unsigned long)cfg.admission_budget_ms,
           res.acks, res.rearms, res.isr_w1c, res.main_w1c, res.teardown_w1c, res.unexpected, res.unexpected_site);
    printf("  handler: installed=%d old=%s restored=%d mask_ok=%d intmr_final=%08lx  control_ok=%d pi_sticky=%d  uncertain=%u%s\n",
           res.h.handler_was_installed, res.h.old_handler_null == 1 ? "null" : res.h.old_handler_null == 0 ? "nonnull" : "?",
           res.h.handler_restored, res.h.mask_ok, (unsigned long)res.h.intmr_final, res.control_ok, res.pi_sticky_final,
           res.uncertain_writes, res.uncertain_writes ? "  DEVICE STATE UNCERTAIN" : "");
    printf("  restore: control=%d stop=%d cleanup performed=%d arinfo=%d  errors=%u transfers=%lu bulk=%lu/%lu timeouts=%lu busy=%lu log=%u dropped=%u trunc=%u\n",
           a->control_restore_ok, a->irq_stop_write_ok, a->pi_cleanup_performed, a->arinfo_restore_ok,
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
    printf("  X = save log + sequence sidecar to SD2SP2      START = exit\n");

    for (i = 0; i < rl.count; i++) {
        snprintf(line, sizeof line, "OPENGBP-VIDEO LOG %s\n", ringlog_line(&rl, i));
        gecko_puts(line);
    }
    snprintf(line, sizeof line, "OPENGBP-VIDEO %s\n", summary);
    gecko_puts(line);

    for (;;) {
        u32 down;
        VIDEO_WaitVSync();
        PAD_ScanPads();
        down = PAD_ButtonsDown(0);
        if (down & PAD_BUTTON_START) {
            gecko_puts("OPENGBP-VIDEO EXIT reason=start\n");
            break;
        }
        if ((down & PAD_BUTTON_X) && !saved) {
            char path[128] = "";
            char extra[176];
            struct gbp_avseqdump_info info;
            long n;
            int rc, rc2 = -9;
            snprintf(extra, sizeof extra, "libogc=%s gecko=%d power_cycle_required=%d sidecar=%s_%s-seq.bin", _V_STRING, gecko_present,
                     res.power_cycle_required, TEST_ID, OPENGBP_BUILD_ID);
            rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl,
                            status, sizeof status, path, sizeof path);
            /* the sidecar: the records and the raw blocks exactly as the DMA left them, serialized only
             * now, outside every timed region; an identity that does not fit is an error, never a truncation */
            if (gbp_video_dump_info(&res, cfg.a.tb_hz, TEST_ID, OPENGBP_BUILD_ID, OPENGBP_APP_NAME, OPENGBP_GIT_COMMIT, &info) != 0) {
                snprintf(status2, sizeof status2, "sidecar not written: an identity does not fit the format");
                n = -2;
            } else {
                n = gbp_avseqdump_serialize(&info, &seq_store, dump_buffer, sizeof dump_buffer);
                if (n > 0) rc2 = sdlog_save_blob(TEST_ID, OPENGBP_BUILD_ID, "-seq.bin", dump_buffer, (size_t)n, status2, sizeof status2, NULL, 0);
                else snprintf(status2, sizeof status2, "sidecar not serialized (rc=%ld)", n);
            }
            saved = (rc == 0 && rc2 == 0);
            printf("\x1b[26;1H  SD log: %s\n", status);
            printf("  SD seq: %s%s\n", status2, (rc == 0 && rc2 != 0) ? "  (PARTIAL SAVE: log only)" : "");
            snprintf(line, sizeof line, "OPENGBP-VIDEO SAVE rc=%d %s\n", rc, status);
            gecko_puts(line);
            snprintf(line, sizeof line, "OPENGBP-VIDEO SAVESEQ rc=%d %s cycles=%lu video=%lu audio=%lu audio_raw=%lu bytes=%ld total_crc32=%08lx\n",
                     rc2, status2, (unsigned long)info.cycle_count, (unsigned long)info.video_count, (unsigned long)info.audio_count,
                     (unsigned long)info.audio_raw_count, n, (unsigned long)info.total_crc32);
            gecko_puts(line);
        }
    }
    printf("\n  Exiting.%s\n", res.power_cycle_required ? " POWER CYCLE REQUIRED." : "");
    VIDEO_WaitVSync();
    exit(0);
}
