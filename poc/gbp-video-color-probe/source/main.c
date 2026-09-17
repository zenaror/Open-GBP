/*
 * Open-GBP GBP-VIDEO-003, build color-0001 — the controlled colour experiment
 * (HARDWARE_TESTS §V3). It answers ONE question that four physical runs could
 * not touch: which five of the fifteen colour bits the Game Boy Player presents
 * are which channel, and whether the path transforms them on the way out.
 *
 * WHAT THIS PROGRAM DOES NOT KNOW. It holds no stimulus value, no channel name
 * and no hypothesis. It cannot recognise the colour bars, and that is the point:
 * a runtime that looked for 0x001F on the wire would be deciding the
 * experiment's question with the experiment's own answer. It preserves THREE
 * IDENTICAL ELIGIBLE FRAMES, whatever they show, and tools/vcolor.py decides
 * offline whether those bytes are the stimulus and what transformation they
 * imply (§V3.11, §V3.14).
 *
 * The capture: the service path of GBP-VIDEO-002 verbatim - the 003A stage, the
 * 003B extended one-shot handler, mask/unmask through libogc2 only, READ, AUDIO
 * 0x1000, VIDEO 0xF00, ACK `pending | 0x8000`, PI clean, the per-block signature
 * and frame assembly, re-arm `IRQ := 0x0000`, WAIT_NEXT - with the semantic
 * disagreement policy that vstate-0004 validated on hardware, unchanged: a
 * disagreement confined to the two serviced source bits is survivable, the
 * majority is authoritative inside SRC_MASK, a frame holding a majority-extra
 * VIDEO block is quarantined and may never become colour evidence, and every
 * other disagreement is still fatal (§V3.9).
 *
 * What is new is only the capture state machine and the sidecar: three
 * consecutive eligible frames carrying the SAME 40 block signatures certify a
 * window and the run stops there. Search window 10 s, hard wall-clock 30 s,
 * delivery cap 250 000 - none of them inherited from the vstate probe (§V3.12).
 *
 * THE CAPTURE DOES NO FULL-FRAME WORK (§V3.23). The first implementation of this
 * probe compared and copied 153 600 bytes between the ACK and the RE-ARM, at
 * every eligible frame close, and the microaudit refused it. The frame-close
 * hook now costs an eligibility test, at most 40 word comparisons and a bounded
 * record write; it never forms a pointer into the ring. The certified frames
 * stay where the DMA put them, in the state model's FOUR-slot ring, and the
 * sidecar streams them from there after the hardware is down (§V3.24).
 *
 * The stimulus is a separate program: stimulus/agb-color-bars, an AGB Mode 3
 * image of eight 30-pixel bars whose values are known by construction and which
 * never sets bit 15. HOW IT REACHES THE INTERNAL AGB IS UNRESOLVED: this
 * repository documents no flash cart, no multiboot cable and no loader, and the
 * design refuses to invent one (§V3.7, PHYSICAL EXECUTION DEPENDENCY).
 *
 * SD save on X - the text log, then the OGBPCOL1 sidecar STREAMED in 64 KiB
 * chunks - START to exit. Nothing is read from the controller before the probe
 * has returned from its teardown, and no filesystem call exists anywhere
 * between the first experimental write and the completed teardown. Every run
 * ends with "POWER CYCLE REQUIRED".
 *
 * hardware_result and save_result are separate: a card failure after a
 * successful teardown cannot invalidate the hardware result held in RAM, and
 * there is never an automatic re-run.
 *
 * Not a runtime: no framebuffer conversion, no rendering, no GX, no audio
 * output, no KEYPAD, no SIO, no Link Port, no BBA, no Game Pak logic, no
 * callbacks, no unbounded loop, no malloc. Nothing captured is ever compared
 * with anything on the console.
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
#include "gbp_vstate_probe.h"
#include "gbp_vcolor.h"
#include "gbp_vcoldump.h"
#include "hsp_backend.h"
#include "hsp_backend_irq.h"
#include "sdlog.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-video-state-probe"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-VIDEO-003"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT app=" OPENGBP_APP_NAME " build=" OPENGBP_BUILD_ID " commit=" OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1
/* The ring must hold the worst reachable run without dropping a line. There is NO per-delivery
 * record here — that is the whole point of the design — so the demand does not grow with the
 * ~639 000 expected cycles. Worst case:
 *     identity, environment, policy, stores                    ~14
 *     the 003A stage records                                    ~40
 *     4 verify cycles, full AVSVC records                4 x ~70 = 280
 *     bounded cycle records, two lines each:
 *         first 8 + last 8 + anomalies 8 + episode 64 = 88 -> 176
 *     events shown (first 128 + last 64 + two markers)          194
 *     episode descriptors                                         4
 *     clocks, frames, predicates, intervals, baseline,
 *     structured, audio, signature cost, counters, matrix, restore ~20
 *                                                             ------
 *                                                               ~728
 * 1024 lines leaves about 40 % of margin. A dropped line would break the log -> analysis chain. */
#define LOG_LINES 1024
#define LOG_LINE_LEN 256
#define DMA_TIMEOUT_MS 200

static char log_storage[LOG_LINES * LOG_LINE_LEN];
static uint8_t dma_buffer[GBP_BLOCK_SIZE] ATTRIBUTE_ALIGN(32);

/* The resident stores. All static, all 32-byte aligned where a DMA targets them, none allocated.
 * Sizes are the design's (§21) and gbp_vstate_static_bytes() re-derives the total for the log. */
/* The frame table is sized by THIS experiment, not by the vstate scan: the
 * capture ends within seconds, so 1024 frame records (~17 s at 59.7 Hz) is the
 * cap, and the state model's own frame_store_full then stops the run exactly
 * where FRAME_CAP says it should (§V3.12). */
/* The shared state model keeps its own contract: gbp_vstate_storage_ok() demands
 * the full stores, and a model running with less than it was designed for is a
 * different model. The colour experiment's own FRAME_CAP is a stop condition
 * (§V3.12), not a smaller buffer. */
static struct gbp_vstate_frame frame_store[GBP_VSTATE_MAX_FRAMES];                 /* 3.00 MiB */
static struct gbp_vstate_event event_store[GBP_VSTATE_MAX_EVENTS];                 /* 0.25 MiB */
/* FOUR slots, not three, and the extra one is the whole reason the capture can
 * be free of copies (§V3.24): when the third consecutive frame closes, the
 * assembler has already written the next frame's first block into slot cur+1,
 * so with three slots the first of the three is destroyed at exactly the
 * instant it becomes evidence. With four, A, B and C are all intact, the run
 * stops there, and the writer reads them after the teardown. */
static uint8_t raw_ring[GBP_VSTATE_RAW_RING_BYTES_4] ATTRIBUTE_ALIGN(32);          /* 0.70 MiB, DMA target */
static uint8_t episode_raw[GBP_VSTATE_EPISODE_RAW_BYTES] ATTRIBUTE_ALIGN(32);      /* 2.81 MiB */
static uint8_t audio_raw[GBP_VSTATE_AUDIO_RAW_BYTES] ATTRIBUTE_ALIGN(32);          /* 12 KiB, DMA target */
static struct gbp_vstate_cycle cyc_first[GBP_VSTATE_CYC_FIRST];
static struct gbp_vstate_cycle cyc_last[GBP_VSTATE_CYC_LAST];
static struct gbp_vstate_cycle cyc_anomaly[GBP_VSTATE_CYC_ANOMALY];
static struct gbp_vstate_cycle cyc_episode[GBP_VSTATE_CYC_EPISODE];
/* The ONLY transient buffer of the save, and it exists only after the teardown. */
static uint8_t dump_chunk[GBP_VCOLDUMP_CHUNK] ATTRIBUTE_ALIGN(32);

/* ---- what GBP-VIDEO-003 adds, and nothing else ----
 * A frame table, and that is all. There is NO staging buffer for the certified
 * raw any more: the three frames the mapping will be decided from stay in the
 * state model's ring, which grew from three slots to four so that A, B and C are
 * still intact at the instant the third one closes (§V3.24). The table beside it
 * is bounded history: one small record per assembled frame, so the sequence that
 * led to certification can be read offline instead of taken on trust. */
static struct gbp_vcolor_frame color_frames[GBP_VCOLOR_MAX_FRAMES];                /* 48 KiB */
static struct gbp_vcolor color;

static struct gbp_vstate vstate;
/* The bounded semantic-disagreement store (§R3.15). 256 x 160 = 40 960 B, static,
 * never allocated, never written per delivery. */
static struct gbp_vstate_diag diag_store[GBP_VSTATE_MAX_DISAGREEMENTS];

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

/* The streaming sink: one SD write per 64 KiB chunk, after the teardown. */
static int sink_sd(void *ctx, const uint8_t *data, uint32_t len)
{
    return sdlog_stream_write((struct sdlog_stream *)ctx, data, len);
}

int main(void)
{
    struct ringlog rl;
    struct hsp_backend hsp;
    struct gbp_transport t;
    static struct gbp_vstate_config cfg;
    static struct gbp_vstate_result res;
    static char summary[2600];
    static char line[sizeof summary + 64];
    char status[160] = "not saved (press X)";
    char status2[160] = "-";
    char ident_text[OPENGBP_IDENT_MAX];
    const struct opengbp_ident ident = { OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT };
    const struct gbp_initirqa_result *a;
    uint32_t tb_hz = (uint32_t)TB_TIMER_CLOCK * 1000u;
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

    snprintf(line, sizeof line, "OPENGBP-COLOR READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    gbp_vstate_config_default(&cfg);
    gbp_vstate_config_timebase(&cfg, tb_hz);
    gbp_vstate_init(&vstate, frame_store, GBP_VSTATE_MAX_FRAMES, event_store, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&vstate, diag_store, GBP_VSTATE_MAX_DISAGREEMENTS);
    gbp_vcolor_init(&color, color_frames, GBP_VCOLOR_MAX_FRAMES);
    cfg.st = &vstate;
    /* ---- the GBP-VIDEO-003 capture, and its caps (§V3.12) ----
     * SEARCH_WINDOW 10 s: two orders of magnitude more than the ~50 ms three
     * frames need once a stable image is on screen. HARD_WALLCLOCK 30 s: search
     * plus teardown with a wide margin. DELIVERY_CAP 250 000: about
     * 40 s at the 6 336 deliveries/s measured in vstate-0004. The vstate probe's
     * 120 s and 180 s are NOT inherited - that target came from the Start-up
     * Disc's detector window and has nothing to do with this question - and the
     * target logic is pushed out of reach so that the ONLY success path is
     * certification. */
    cfg.color = &color;
    cfg.color_search_ticks = (uint64_t)tb_hz * GBP_VCOLOR_SEARCH_SECONDS;
    cfg.hard_wallclock_s = GBP_VCOLOR_HARD_WALLCLOCK_SECONDS;
    cfg.hard_wallclock_ticks = (uint64_t)tb_hz * GBP_VCOLOR_HARD_WALLCLOCK_SECONDS;
    cfg.max_deliveries = GBP_VCOLOR_MAX_DELIVERIES;
    cfg.min_valid_observation_s = 0u;
    cfg.min_valid_observation_ticks = (uint64_t)1 << 60;   /* unreachable on purpose */
    cfg.cyc_first = cyc_first;
    cfg.cyc_last = cyc_last;
    cfg.cyc_anomaly = cyc_anomaly;
    cfg.cyc_episode = cyc_episode;

    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s app=%s build=%s commit=%s libogc=%s", TEST_ID,
                   OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, _V_STRING);
    ringlog_printf(&rl, "ENV bus_hz=%lu tb_hz=%lu dma_timeout_ms=%u t_max_ms=%lu t_delivery_ms=%lu t_next_cause_ms=%lu csr=%04x",
                   (unsigned long)*(vu32 *)0x800000F8, (unsigned long)cfg.a.tb_hz, (unsigned)DMA_TIMEOUT_MS,
                   (unsigned long)cfg.a.t_max_ms, (unsigned long)cfg.t_delivery_ms, (unsigned long)cfg.t_next_cause_ms,
                   (unsigned)hsp_backend_read_csr());
    ringlog_printf(&rl, "ENVTIME target_s=%lu target_ticks=%llx limit_s=%lu limit_ticks=%llx nominal_limit_ticks=%llx u32_wrap_s=%lu",
                   (unsigned long)cfg.min_valid_observation_s, (unsigned long long)cfg.min_valid_observation_ticks,
                   (unsigned long)cfg.hard_wallclock_s, (unsigned long long)cfg.hard_wallclock_ticks,
                   (unsigned long long)GBP_VSTATE_HARD_WALLCLOCK_LIMIT_TICKS_U64,
                   (unsigned long)(0xFFFFFFFFu / (tb_hz ? tb_hz : 1u)));
    ringlog_printf(&rl, "ENVBUF frames=%08lx events=%08lx raw_ring=%08lx episode_raw=%08lx audio_raw=%08lx chunk=%08lx static_bytes=%llu log_lines=%u",
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(frame_store), (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(event_store),
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(raw_ring), (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(episode_raw),
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(audio_raw), (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(dump_chunk),
                   (unsigned long long)(gbp_vstate_static_bytes_for(gbp_vstate_ring_slots(&vstate)) +
                                        gbp_vcolor_static_bytes()), (unsigned)LOG_LINES);
    ringlog_printf(&rl, "ENVA2 a2_obs_us=%lu,%lu,%lu,%lu,%lu,%lu",
                   (unsigned long)cfg.a.a2_obs_us[0], (unsigned long)cfg.a.a2_obs_us[1], (unsigned long)cfg.a.a2_obs_us[2],
                   (unsigned long)cfg.a.a2_obs_us[3], (unsigned long)cfg.a.a2_obs_us[4], (unsigned long)cfg.a.a2_obs_us[5]);

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);
    hsp_backend_irq_transport_ext(&hsp, &t);

    printf("  Sequence: 003A verbatim, PI masked -> first cause -> IRQ_Request(26, ext) ONCE -> PREUNMASK\n");
    printf("            -> repeated: reset -> __UnmaskIrq x1 -> handler -> __MaskIrq -> READ -> AUDIO -> VIDEO\n");
    printf("               -> ACK -> PI clean -> signature + frame assembly -> IRQ := 0000 -> next cause (masked)\n");
    printf("            -> until %lu s of VALID post-baseline observation, the %lu s hard safety cap,\n",
           (unsigned long)cfg.min_valid_observation_s, (unsigned long)cfg.hard_wallclock_s);
    printf("               a store cap, no next cause, or a failure -> IMMEDIATE teardown -> then summaries.\n");
    printf("  Expect two to five minutes of unattended running. DO NOT PRESS ANYTHING.\n");
    if (!gbp_transport_has_bulk_read(&t) || !gbp_transport_has_irq_reset(&t) || !gbp_transport_has_time64(&t)) {
        printf("\n  FATAL: the transport lacks the whole-block read, the record reset or the 64-bit time base.\n");
        printf("  Nothing was run. START = exit\n");
        for (;;) { VIDEO_WaitVSync(); PAD_ScanPads(); if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break; }
        exit(1);
    }
    printf("  Running ...\n");

    gbp_vstate_probe_run(&t, &rl, &cfg, &res);     /* returns only after the teardown AND the report */
    a = &res.a;

    ringlog_printf(&rl, "STATS transfers=%lu timeouts=%lu busy=%lu bulk_transfers=%lu bulk_bytes=%lu", (unsigned long)hsp.transfers,
                   (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals, (unsigned long)hsp.bulk_transfers,
                   (unsigned long)hsp.bulk_bytes);
    gbp_vstate_summary(&res, summary, sizeof summary);

    /* ---- the compact final screen: hardware, baseline, valid seconds, frames, episodes, caps, restore, save ---- */
    printf("\n  HARDWARE status=%s (%s) reason=%s stop=%s restore=%s (%s) teardown=%s\n", res.status_name, res.status_class,
           res.reason ? res.reason : "-", gbp_vstate_stop_name(res.stop), res.restore_ok ? "ok" : "ERROR",
           res.restore_reason ? res.restore_reason : "-", res.teardown_variant ? res.teardown_variant : "-");
    printf("  SERVICE %s (%s)  deliveries=%lu  VIDEO %lu blocks  AUDIO %lu drains  W1C isr=%lu main=%lu teardown=%lu\n",
           res.service_ok ? "ok" : "FAILED", res.service_reason, (unsigned long)res.deliveries,
           (unsigned long)res.video_completed, (unsigned long)res.audio_drains,
           (unsigned long)res.isr_w1c, (unsigned long)res.main_w1c, (unsigned long)res.teardown_w1c);
    printf("  BASELINE %s after %lu frames (%lu.%03lu s)   VALID OBSERVATION %lu.%03lu s of %lu s   capture %lu.%03lu s   safety %lu.%03lu s of %lu s\n",
           vstate.baseline_valid ? "valid" : "NEVER ESTABLISHED", (unsigned long)vstate.baseline_frames_seen,
           (unsigned long)gbp_time64_seconds(tb_hz, res.baseline_elapsed), (unsigned long)gbp_time64_millis_part(tb_hz, res.baseline_elapsed),
           (unsigned long)gbp_time64_seconds(tb_hz, res.valid_observation_elapsed), (unsigned long)gbp_time64_millis_part(tb_hz, res.valid_observation_elapsed),
           (unsigned long)cfg.min_valid_observation_s,
           (unsigned long)gbp_time64_seconds(tb_hz, res.capture_elapsed), (unsigned long)gbp_time64_millis_part(tb_hz, res.capture_elapsed),
           (unsigned long)gbp_time64_seconds(tb_hz, res.safety_elapsed), (unsigned long)gbp_time64_millis_part(tb_hz, res.safety_elapsed),
           (unsigned long)cfg.hard_wallclock_s);
    printf("  FRAMES %lu observed (%lu complete, %lu incomplete, %lu resync)  boundaries disc=%lu gbi=%lu disagreements=%lu\n",
           (unsigned long)vstate.frames_n, (unsigned long)vstate.frames_complete, (unsigned long)vstate.frames_incomplete,
           (unsigned long)vstate.resync_frames, (unsigned long)vstate.boundaries_disc, (unsigned long)vstate.boundaries_gbi,
           (unsigned long)vstate.disagreements_total);
    /* ---- what this experiment is actually about ----
     * The probe reports WHETHER it preserved three identical eligible frames.
     * It does not say what they show: it holds no stimulus value, no channel
     * name and no hypothesis, and the mapping is decided offline by
     * tools/vcolor.py from the raw bytes (§V3.11, §V3.14). */
    printf("  COLOUR %s  frames=%lu eligible=%lu  run_len=%lu  resets=%lu  certified=%lu frame(s), %lu bytes of raw\n",
           color.certified ? "CERTIFIED" : "NOT CERTIFIED",
           (unsigned long)color.frames_total, (unsigned long)color.frames_eligible,
           (unsigned long)color.run_len, (unsigned long)color.resets,
           (unsigned long)(color.certified ? color.cert_n : 0u),
           (unsigned long)(color.certified ? color.cert_n * GBP_VCOLOR_FRAME_BYTES : 0u));
    /* The certified bytes were never copied: they are still in the state model's
     * ring, in the slots named here, and this line is what says so. SLOTS is the
     * check that turns the ring-lifecycle argument into a fact (§V3.24). */
    printf("  SLOTS %s  ring=%lu slots  cur=%lu  cert=[%u:%lu %u:%lu %u:%lu]  sig_mismatches=%lu\n",
           gbp_vcolor_slots_ok(&color, &vstate) ? "intact" : (color.certified ? "UNUSABLE" : "n/a"),
           (unsigned long)gbp_vstate_ring_slots(&vstate), (unsigned long)gbp_vstate_current_slot(&vstate),
           0u, (unsigned long)color.cert[0].ring_slot,
           1u, (unsigned long)color.cert[1].ring_slot,
           2u, (unsigned long)color.cert[2].ring_slot,
           (unsigned long)color.sig_mismatches);
    printf("  REFUSED not_complete=%lu wrong_blocks=%lu anomaly=%lu resync=%lu quarantine=%lu deferred=%lu retired=%lu no_slot=%lu\n",
           (unsigned long)color.frames_refused[GBP_VCOLOR_NOT_COMPLETE],
           (unsigned long)color.frames_refused[GBP_VCOLOR_WRONG_BLOCKS],
           (unsigned long)color.frames_refused[GBP_VCOLOR_ANOMALY],
           (unsigned long)color.frames_refused[GBP_VCOLOR_RESYNC],
           (unsigned long)color.frames_refused[GBP_VCOLOR_MAJORITY_EXTRA],
           (unsigned long)color.frames_refused[GBP_VCOLOR_SOURCE_DEFERRED],
           (unsigned long)color.frames_refused[GBP_VCOLOR_RETIRED_PRE_BASELINE],
           (unsigned long)color.frames_refused[GBP_VCOLOR_NO_SLOT]);
    printf("  CAPS frame_store_full=%d event_store_full=%d episode_raw_store_full=%d (monitoring continued)  tail_frames=%lu truncated=%d  anomalies a=%lu b=%lu\n",
           vstate.frame_store_full, vstate.event_store_full, vstate.episode_store_full,
           (unsigned long)vstate.tail_frames, vstate.tail_truncated_by_cap,
           (unsigned long)vstate.anomalies_frame, (unsigned long)vstate.anomalies_region);
    printf("  RESTORE control=%d stop=%d cleanup=%d arinfo=%d handler=%d mask_ok=%d  errors=%lu uncertain=%lu overflow=%lu\n",
           a->control_restore_ok, a->irq_stop_write_ok, a->pi_cleanup_performed, a->arinfo_restore_ok,
           res.h.handler_restored, res.h.mask_ok, (unsigned long)res.errors, (unsigned long)res.uncertain_writes,
           (unsigned long)res.counter_overflow);
    if (vstate.sem.disagreements_total) {
        const struct gbp_vstate_diag *d0 = gbp_vstate_diag_first(&vstate);
        /* The bytes are held; the explanation is offline (tools/vstate.py diag). */
        printf("  SEMANTIC %lu disagreement(s): %lu serviced, %lu other, %lu non-source; %lu preserved%s\n",
               (unsigned long)vstate.sem.disagreements_total, (unsigned long)vstate.sem.source_serviced,
               (unsigned long)vstate.sem.source_other, (unsigned long)vstate.sem.non_source,
               (unsigned long)vstate.sem.diagnostics_preserved,
               vstate.sem.store_capped ? " (store capped)" : "");
        if (d0)
            printf("  FIRST at cycle %lu (%s, %s): disc=%04x gbi=%04x delta=%04x, the 32 raw bytes ARE preserved\n",
                   (unsigned long)d0->cycle, gbp_vstate_diag_read_name(d0->read_kind),
                   gbp_vstate_class_name(d0->classification), d0->disc_value, d0->gbi_value, d0->delta);
        if (vstate.sem.frames_quarantined)
            printf("  QUARANTINE %lu frame(s) carried a VIDEO block served only by the majority\n",
                   (unsigned long)vstate.sem.frames_quarantined);
    }
    printf("  LOG %u lines, dropped=%u truncated=%u\n", (unsigned)rl.count, (unsigned)rl.dropped, (unsigned)rl.truncated);
    if (res.power_cycle_required) {
        printf("\n  ******************************************************************\n");
        printf("  *  POWER CYCLE REQUIRED after this run (experimental write made)  *\n");
        printf("  *  save with X, START to exit, then switch the console OFF.       *\n");
        printf("  ******************************************************************\n");
    } else {
        printf("\n  No experimental write was attempted (power cycle still recommended).\n");
    }
    printf("  X = save log + streamed sidecar to SD2SP2      START = exit\n");

    for (i = 0; i < rl.count; i++) {
        snprintf(line, sizeof line, "OPENGBP-COLOR LOG %s\n", ringlog_line(&rl, i));
        gecko_puts(line);
    }
    snprintf(line, sizeof line, "OPENGBP-COLOR %s\n", summary);
    gecko_puts(line);

    for (;;) {
        u32 down;
        VIDEO_WaitVSync();
        PAD_ScanPads();
        down = PAD_ButtonsDown(0);
        if (down & PAD_BUTTON_START) {
            gecko_puts("OPENGBP-COLOR EXIT reason=start\n");
            break;
        }
        if ((down & PAD_BUTTON_X) && !saved) {
            char path[128] = "";
            char extra[200];
            static struct gbp_vcoldump_info info;
            struct sdlog_stream stream;
            uint64_t written = 0;
            long n = -1;
            int rc, rc2 = -9;
            res.save_attempted = 1;
            /* The log names the sidecar AND its format: v4 and v5 share a layout,
             * so the version is the only thing that says which producer contract
             * the file was written under. */
            snprintf(extra, sizeof extra,
                     "libogc=%s gecko=%d power_cycle_required=%d sidecar=%s_%s-color.bin format=OGBPCOL1_v%u",
                     _V_STRING, gecko_present, res.power_cycle_required, TEST_ID, OPENGBP_BUILD_ID,
                     (unsigned)GBP_VCOLDUMP_VERSION);
            rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl,
                            status, sizeof status, path, sizeof path);
            res.save_log_ok = (rc == 0) ? 1 : 0;
            /* The sidecar, streamed: the layout is proven first, then the header, the tables and
             * the raw sections go out in 64 KiB chunks with a running CRC. No second full copy. */
            memset(&info, 0, sizeof info);
            if (gbp_vcoldump_set_identity(&info, TEST_ID, OPENGBP_BUILD_ID, OPENGBP_APP_NAME, OPENGBP_GIT_COMMIT) != 0) {
                snprintf(status2, sizeof status2, "sidecar not written: an identity does not fit the format");
                res.save_reason = "identity_does_not_fit";
            } else if (sdlog_stream_open(&stream, TEST_ID, OPENGBP_BUILD_ID, "-color.bin", status2, sizeof status2) != 0) {
                res.save_reason = "open_failed";
            } else {
                n = gbp_vcoldump_stream(&info, &color, &vstate, &res, &cfg, dump_chunk, sizeof dump_chunk,
                                        sink_sd, &stream, &written);
                rc2 = sdlog_stream_close(&stream, status2, sizeof status2);
                if (n < 0 && rc2 == 0) rc2 = -5;
                res.save_bytes = written;
                res.save_reason = (rc2 == 0 && n > 0) ? "-" : (n < 0 ? "serialize_failed" : "write_failed");
            }
            res.save_sidecar_ok = (rc2 == 0 && n > 0) ? 1 : 0;
            saved = (res.save_log_ok && res.save_sidecar_ok);
            /* hardware_result is NOT touched by any of this (§18/§26): a card failure after a
             * successful teardown cannot invalidate what is in RAM, and nothing re-runs. */
            printf("\x1b[28;1H  SD log     : %s\n", status);
            printf("  SD sidecar : %s   (OGBPCOL1 v%u)\n", status2, (unsigned)GBP_VCOLDUMP_VERSION);
            printf("  SAVE RESULT: %s   (hardware_result unchanged: %s / %s)\n",
                   saved ? "complete" : (res.save_log_ok || written) ? "PARTIAL" : "FAILED",
                   res.status_name, res.restore_ok ? "restore ok" : "restore FAILED");
            snprintf(line, sizeof line, "OPENGBP-COLOR SAVE rc=%d %s\n", rc, status);
            gecko_puts(line);
            snprintf(line, sizeof line,
                     "OPENGBP-COLOR SAVESIDECAR rc=%d %s bytes=%lu frames=%lu certified=%lu diags=%lu raw_bytes=%lu audio=%lu header_crc32=%08lx total_crc32=%08lx\n",
                     rc2, status2, (unsigned long)written, (unsigned long)info.frame_count,
                     (unsigned long)info.cert_count, (unsigned long)info.diag_count,
                     (unsigned long)(info.cert_count * GBP_VCOLOR_FRAME_BYTES),
                     (unsigned long)info.audio_raw_count, (unsigned long)info.header_crc32, (unsigned long)info.total_crc32);
            gecko_puts(line);
        }
    }
    printf("\n  Exiting.%s\n", res.power_cycle_required ? " POWER CYCLE REQUIRED." : "");
    VIDEO_WaitVSync();
    exit(0);
}
