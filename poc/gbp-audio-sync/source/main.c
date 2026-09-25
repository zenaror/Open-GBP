/*
 * gbp-audio-sync -- sync-0001 (GBP-AUDIO-012): THE LATENCY ROUND, HARDWARE_TESTS §V27
 * (GitHub Issue #117). game-0002's image (the real-cartridge chain, the A press as the
 * origin, the picture handed to the VI from the press) with:
 *
 *   - NO L2 keep: gbp_aplay_arm_l2 is never called and no keep store is bound (§V27.1);
 *   - the ring's cushion TARGET as a RUNTIME level (src/audio/gbp_aplay `target`), moved
 *     only inside a MUTE TRANSITION of fixed length, identical in both directions and on a
 *     null switch (§V27.11 §1, §V27.13): the READY queue is HELD, the callback hands the
 *     silence buffer for MUTE chunks (its own counter, never an underrun), the producer
 *     pauses for ceil(delta / 128) hand-offs when deepening and otherwise produces and
 *     DISCARDS one chunk per hand-off, and the level is landed exactly by discarding from
 *     the ring's head. The skipped content is 0.125 s deepening, 0.500 s null, 0.875 s
 *     shallowing: the asymmetry is INTRINSIC to changing an output latency, MASKED by the
 *     same 0.5 s of silence, MEASURED by the null switches;
 *   - the §V27 session machine, src/audio/gbp_async: a seeded schedule of 12 REAL + 6 NULL
 *     switches judged three ways after each (Phase 1), a nulling by 128-sample steps from
 *     seeded starts (Phase 2), an automatic descent with a bisection to the depth where the
 *     correction stops working (Phase 3), and the per-second accounting of the whole 720 s;
 *   - the C-stick as the only control the cartridge does not receive: DOWN switches, LEFT /
 *     RIGHT answer LESS / MORE and step, UP answers SAME and confirms; Z still ends the session;
 *   - a 640-block RAW WINDOW of the game's AUDIO blocks (src/gbp/gbp_awr) captured right after
 *     the origin and before the first switch, its copy cost measured, saved as OGBPAWR1 (§V27.11);
 *   - BLINDING (§V27.9 O6 widened, §V27.10): the screen and the live channel carry NOTHING
 *     derived from the arm, the target, the fill, the corrections or his answers -- no figure,
 *     no score, no label. The SD log carries everything, and is read only after his words.
 *
 * The session's bound is gbp_async's 720 s cap, a SUCCESS (teardown and save); the safety
 * bound above it is the frame store's own limit. The verdicts are tools/v27accept.py's,
 * frozen before this file existed; tools/v27report.py turns the log into what it reads.
 */
/*
 * Open-GBP GBP-AUDIO-010, build game-0001 — PHASE 6's ACCEPTANCE ON A REAL CARTRIDGE: the
 * Operator plays a game he knows and is the instrument (GitHub Issue #110; HARDWARE_TESTS §V25,
 * with §V25.7's decisions and §V25.8's confirmed readings). IMPLEMENTED AND HOST-VALIDATED; NOT
 * PHYSICALLY EXECUTED; staging and the run belong to a separate Hardware Issue.
 *
 * WHAT THIS IS (§V25.7 5, (r8)). live-0001 -- RUN 38's image, poc/gbp-audio-live at feaf380,
 * whose own header is below this one -- with the three things that stood on the stimulus ROM's
 * tone replaced, two counters and the video's location added, and nothing else. No §V23
 * recorder and no §V24 split: the chain produces in gbp_aplay's adopted 8-push calls (Issue
 * #109). Every changed or added line sits in a block marked GAME, or carries the mark itself;
 * tests/host/test_game_image.py shows it by diffing.
 *
 *   GAME 1  THE ORIGIN (§V25.7 2(a), (r1)): gbp_alive's press origin -- the first A press plus
 *           1.000 s, and no positive control. A game emits no programmed period.
 *   GAME 2  THE SCREEN (§V25.7 2(c), (r5)): play-0001's two hand-over writes, per presented
 *           frame, only from the press until C's window closes. The console before the press,
 *           the game during, the console for the report.
 *   GAME 3  THE PROMPT (§V25.7 2(d), (r6)): it invites presses; do NOT hold Z; X does nothing
 *           until the end.
 *   GAME 4  THE RECORDS: LIVEGAME (the origin and the screen as configured); LIVECAL, the
 *           calibration span's spread (§V25.7 2(b), (r3)); `clipped` in LIVEC (§V25.7 3(b),
 *           (r4)); and after the session, off the drain path, the frame store walked into
 *           LIVEVINC and LIVEVSEC (§V25.7 4, (r7)).
 *   GAME 5  THE SCREEN REPORT: the origin, the decoder's clips and spread, the video's
 *           location -- figures, never a verdict -- and two inherited lines that would be
 *           wrong here: the verdicts are tools/v25accept.py's, and the AUDIO is played.
 *
 * The verdicts are not computed here: tools/v25report.py turns the log into the report
 * tools/v25accept.py reads, and that tool was frozen (54383e6) before this image existed.
 */
/*
 * Open-GBP GBP-AUDIO-007, build live-0001 — PHASE 6's ACCEPTANCE IMAGE: drain live,
 * decode, and play the cartridge's own tone through the GameCube (GitHub Issue #92;
 * HARDWARE_TESTS §V22 with §V22.8's readings and §V22.9 AMENDMENT 1).
 * IMPLEMENTED AND HOST-VALIDATED; NOT PHYSICALLY EXECUTED; the run is staged by a
 * separate Hardware Issue and is not authorised here.
 *
 * WHAT THIS IS. `play-0001` (poc/gbp-play-session @ 2e48ca7) as RUN 37's image took
 * it -- the transport and the 003B one-shot handler, the service path draining AUDIO
 * AND VIDEO in whole 0x1000 blocks, the presentation path, the input path and the Z
 * session end, all with their behaviour unchanged -- PLUS the composition §V22
 * accepts, and nothing else:
 *
 *   1. THE AUDIO TAP (cfg.audio_tap): one call per AUDIO drain, inside the service
 *      transaction. src/audio/gbp_alive decides what the block is for: the silent
 *      calibration span, the positive control (src/audio/gbp_aperiod, §V19.11 A4.7,
 *      unchanged), or C's window, where the block is DECODED into the ring
 *      (src/audio/gbp_adec, unchanged) and L reads the sample as it leaves the
 *      decoder, before any clock correction (§V22.8 (e)).
 *   2. THE CHAIN, in the pump slot (src/audio/gbp_aplay): the ring -> one counted
 *      DUP / DROP at most per chunk (§V22.4's decision) -> gbp_aresamp (unchanged)
 *      -> 1000-frame AI chunks -> the READY queue. The AI starts once the ring holds
 *      0.5 s and stops when C's window closes. L2's record is kept inside the window.
 *   3. THE AI DMA CALLBACK: hands the next READY chunk, or silence and an UNDERRUN,
 *      and timestamps itself (MEASUREMENT M).
 *   4. THE PRESS RECORD (§V22.8 (r), §V22.9 A3): every GameCube button's rising
 *      edge, from the controller sample input_step() already took. X does NOTHING
 *      until the session has ended, which is after C's window has closed; a press
 *      inside the window is recorded, never acted on.
 *   5. THE SCREEN: the VI stays on the text console for the whole run, as in
 *      drain-0001. It is written before C's window (the prompt, and the line at the
 *      press) and after the run, never inside it: a print there would be a stall of
 *      our own making.
 *
 * NO SD WRITE ON THE DRAIN'S PATH (§V22.0, D2). The card is not touched until the
 * session has ended; the log and L2's sidecar are saved on X, after the teardown.
 *
 * WHAT IS BOUNDED, AND NONE OF IT IS A HARDWARE PROPERTY: the safety budget is 120 s;
 * the positive control cannot pass before capture start + 5 s (A4.5) and gives up
 * 10 s after the A press (A4.7); C's window is 64 s.
 *
 * THE VERDICTS ARE NOT COMPUTED HERE. This image writes its figures into its log and
 * L2's record into its sidecar; tools/v22report.py turns the log into the report
 * tools/v22accept.py reads, and that tool -- frozen before this image existed --
 * decides. The screen shows the figures, never a verdict.
 *
 * SD save on X -- the text log and L2's sidecar -- START to exit. Every run ends with
 * "POWER CYCLE REQUIRED".
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
#include "gbp_vpix.h"
#include "gbp_vqueue.h"
#include "gbp_vpresent.h"
#include "gbp_startup.h"
#include "hsp_backend.h"
#include "hsp_backend_irq.h"
#include "sdlog.h"
#include "gbp_input.h"
#include "gbp_session.h"
#include "gbp_aperiod.h"
#include "gbp_adec.h"
#include "gbp_aresamp.h"
#include "gbp_alive.h"
#include "gbp_aplay.h"
#include "gbp_async.h"
#include "gbp_atrans.h"
#include "gbp_awr.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-audio-sync"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
/* The image's embedded id: the next of the family (GBP-AUDIO-012, HARDWARE_TESTS §V27). */
#define TEST_ID "GBP-AUDIO-012"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT " OPENGBP_APP_NAME " " OPENGBP_BUILD_ID " " OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1

/* ---- the ringlog (Issue #39 sizing) ---------------------------------------
 *
 * The ringlog DROPS a line once it is full (src/log/ringlog.c: `dropped++`,
 * nothing is overwritten), and everything after the run -- the state machine's
 * own report (EV, CYC, READDISAGREE, SEM...) and this file's records -- is
 * written LAST. RUN 17 wrote 462 lines after its last KEY line. So the KEY
 * lines admitted during the run must leave that many free, and the bound that
 * does it is KEYLOG_TAIL_RESERVE below: 640 here (stream-0015's 64 covers only
 * main's own post-run records and would let a KEY-heavy run drop the state
 * machine's report -- a finding about stream-0015, recorded, not acted on
 * there). 8192 lines x 256 B = 2 MiB; the KEY headroom that leaves is
 * 8192 - 640 - the pre-run records (~240) = ~7 300 lines = ~3 650 presses. */
#define LOG_LINES 8192
#define LOG_LINE_LEN 256
#define DMA_TIMEOUT_MS 200

/* ---- the session's bounds (Issue #39) ---------------------------------------
 *
 * None of these is a property of the Game Boy Player; each is a bound of THIS
 * image, stated so a pre-registration can state it too.
 *
 * PLAY_SAFETY_SECONDS   the hard wall-clock budget, counted from the CONTROL
 *                       transform (the AGB's boot included). It stops a run the
 *                       operator did not end -- a run that has gone wrong -- and
 *                       it is never a success. 720 s: at least five minutes of
 *                       play after a boot and a menu of up to seven.
 * PLAY_MAX_DELIVERIES   the u32 delivery guard, above the budget: RUN 17 ran at
 *                       6 314 deliveries/s, so 720 s is ~4.55 M and 6 M sits
 *                       1.32x above it (a factor, as the design's guard always
 *                       was). It binds only if the physical rate exceeds
 *                       ~8 300/s, and then the run ends as `delivery_cap`.
 * PLAY_FRAME_RECORDS    the frame store, sized to OUTLAST the budget: 45056
 *                       records / 59.727 Hz = 754 s > 720 s, so in a nominal
 *                       stream (one closed frame per 40 VIDEO blocks) the
 *                       safety budget always fires first. A pathological
 *                       stream that closes frames faster fills it earlier and
 *                       the run ends as `frame_store_cap` -- visible, never
 *                       silent. Cost over the contract's 16384: +28672 x 192 B
 *                       = +5 505 024 B.
 * PLAY_EVENT_RECORDS    the event store: episodes, anomalies, disagreements.
 *                       A moving game opens and closes episodes continuously
 *                       (EPISODE_MAX_FRAMES = 60: one close per second of
 *                       change, at most), so ~4 events/s is the ceiling
 *                       assumed: 16384 records = 68 min at that rate. Cost over
 *                       the contract's 4096: +12288 x 64 B = +786 432 B.
 * PLAY_SESSION_END_HOLD_MS  how long Z must be held, continuously, to end the
 *                       session. A tap does nothing; a quarter of a second is
 *                       deliberate. Measured on the transport's 64-bit clock. */
/* 785 s (Issue #117, §V27.10): the session's own hard cap is 720 s from the ORIGIN,
 * enforced by src/audio/gbp_async and ended as a SUCCESS (teardown and save); this
 * bound, counted from the CONTROL transform, sits above the latest origin a press in
 * time can give and ends a run that has gone wrong -- a phase that never ended. The
 * origin is the press + 1 s, the press is admitted for SYNC_PROMPT_BOUND_S after the
 * prompt, the prompt comes 5.11 s after the control transform (RUN 41 / RUN 42):
 * origin <= 0.11 + 5 + 45 + 1 = 51.11 s, the session's end <= 771.11 s, 13.9 s under
 * this wall. The frame store is sized to outlast it (47 104 / 60 = 785.07 s; the
 * static assert below holds it; 788.7 s at the measured 59.727 Hz). Review before the
 * commit: at 750 s with an unbounded prompt, a press 24 s after the prompt let the
 * wall pre-empt the session's own cap. */
#define PLAY_SAFETY_SECONDS      785u
#define PLAY_MAX_DELIVERIES      6000000u
#define PLAY_FRAME_RECORDS       47104u
#define PLAY_EVENT_RECORDS       16384u
#define PLAY_SESSION_END_HOLD_MS 250u

/* One tile row per pump call: 3840 bytes read, 1920 written (stream-0002's
 * conservative bounded quantum, measured on every physical stream run). */
#define PLAY_SLICE_TILE_ROWS     1u

static char log_storage[LOG_LINES * LOG_LINE_LEN];
static uint8_t dma_buffer[GBP_BLOCK_SIZE] ATTRIBUTE_ALIGN(32);

/* ---- the state model's stores -------------------------------------------
 *
 * THE FULL GBP-VIDEO-002 STORE SET, as stream-0003 onwards carries it (§V5.29:
 * `stream-0002` shipped a reduced set and aborted at the first gate before
 * touching the device, GBP-HW-136), with TWO of the stores LARGER than the
 * contract's minimum, for the session length above. The gate honours a larger
 * set (`>=`); the model caps at the ACTUAL capacity (gbp_vstate.c:
 * frames_cap / events_cap), which the ENVSTORE record prints beside the
 * contract's constants. The raw ring keeps FOUR slots, the generation guard's
 * margin (§V3.24, §V5.7). */
static struct gbp_vstate_frame frame_store[PLAY_FRAME_RECORDS];                    /* 47104 x 192 B = 8.63 MiB */
static struct gbp_vstate_event event_store[PLAY_EVENT_RECORDS];                    /* 16384 x 64 B = 1.00 MiB */
static uint8_t raw_ring[GBP_VSTATE_RAW_RING_BYTES_4] ATTRIBUTE_ALIGN(32);          /* 0.70 MiB, DMA target */
static uint8_t episode_raw[GBP_VSTATE_EPISODE_RAW_BYTES] ATTRIBUTE_ALIGN(32);      /* 2.81 MiB */
static uint8_t audio_raw[GBP_VSTATE_AUDIO_RAW_BYTES] ATTRIBUTE_ALIGN(32);          /* 12 KiB, DMA target */

_Static_assert(sizeof frame_store / sizeof frame_store[0] >= GBP_VSTATE_MAX_FRAMES,
               "gbp_vstate requires at least GBP_VSTATE_MAX_FRAMES frame records");
_Static_assert(sizeof event_store / sizeof event_store[0] >= GBP_VSTATE_MAX_EVENTS,
               "gbp_vstate requires at least GBP_VSTATE_MAX_EVENTS event records");
_Static_assert(sizeof raw_ring >= GBP_VSTATE_RAW_RING_BYTES,
               "the raw ring must hold at least the minimum three slots");
_Static_assert(sizeof raw_ring % GBP_VSTATE_RAW_FRAME_BYTES == 0,
               "the raw ring must be a whole number of frame slots");
_Static_assert(sizeof episode_raw >= GBP_VSTATE_EPISODE_RAW_BYTES,
               "the episode raw store is NOT optional: gbp_vstate writes through it");
_Static_assert(sizeof audio_raw >= GBP_VSTATE_AUDIO_RAW_BYTES,
               "the AUDIO raw store must hold GBP_VSTATE_AUDIO_RAW_BYTES");
/* Issue #39: the frame store must outlast the safety budget at the nominal
 * 59.727 Hz (60 here, conservative), or the session would end as a cap. */
_Static_assert(PLAY_FRAME_RECORDS >= PLAY_SAFETY_SECONDS * 60u,
               "the frame store must outlast the safety budget at 60 frames per second");
_Static_assert(PLAY_EVENT_RECORDS >= PLAY_SAFETY_SECONDS * 4u,
               "the event store must outlast the safety budget at four events per second");
_Static_assert(PLAY_MAX_DELIVERIES >= PLAY_SAFETY_SECONDS * 6314u,
               "the delivery guard must sit above the budget at RUN 17's delivery rate");
static struct gbp_vstate_cycle cyc_first[GBP_VSTATE_CYC_FIRST];
static struct gbp_vstate_cycle cyc_last[GBP_VSTATE_CYC_LAST];
static struct gbp_vstate_cycle cyc_anomaly[GBP_VSTATE_CYC_ANOMALY];
static struct gbp_vstate_cycle cyc_episode[GBP_VSTATE_CYC_EPISODE];
static struct gbp_vstate vstate;
static struct gbp_vstate_diag diag_store[GBP_VSTATE_MAX_DISAGREEMENTS];
static struct gbp_vqueue vq;
static const struct gbp_vstate_result *pump_res;   /* read-only: the ARAM base, the CONTROL epoch */

/* ---- the texture buffers; the OWNERSHIP lives in src/gbp/gbp_vpresent ---- */
#define PLAY_TEX_BUFFERS GBP_VPRESENT_TEX_BUFFERS
static uint16_t tex_buf[PLAY_TEX_BUFFERS][GBP_VPIX_TEX_BYTES / 2u] ATTRIBUTE_ALIGN(32);  /* 2 x 75 KiB */
static struct gbp_vpresent present;
static GXTexObj tex_obj;

_Static_assert(GBP_VPIX_TEX_BYTES % 32u == 0u, "texture size must be cache-line aligned");
_Static_assert(GBP_VPIX_TEX_BYTES == 240u * 160u * 2u, "texture is 240x160 16-bit");
_Static_assert(GBP_VPIX_FRAME_BYTES == 40u * 0xF00u, "a frame is 40 blocks of 0xF00");
_Static_assert(PLAY_TEX_BUFFERS >= 2u, "GX may still be reading one buffer while the CPU fills the other");
_Static_assert(GBP_VPRESENT_XFB_BUFFERS == 2u, "the stream needs two framebuffers so the VI is never written under");
_Static_assert(GBP_VQUEUE_MAX_UNDISPOSITIONED == GBP_VPRESENT_TEX_BUFFERS,
               "the balance residual bound must equal the texture buffer count");

/* ---- the conversion in progress (consumer state) ----------------------- */
static struct {
    struct gbp_vqueue_desc desc;
    uint32_t next_row;             /* tile rows converted so far, 0..40 */
    uint8_t  buf;                  /* which texture buffer is CPU_FILLING */
    uint8_t  active;
    uint32_t ticks;                /* accumulated slice cost for this frame */
    struct gbp_vpix_stats stats;
} conv;

/* ---- what a texture holds, by index (Issue #39) ------------------------
 *
 * stream-0015 ordered its offers by the disposition trace's lifecycle index
 * and timestamped the first real hand-off from the same trace. The trace is
 * OUT (a partial trace of a long session would be no evidence: Issue #39), so
 * the two facts the runtime itself needs are kept here, per texture:
 *   tex_seq     the take ordinal (assigned in take order, exactly as the
 *               lifecycle index was), which is what keeps §V5.49 I2 -- the
 *               OLDEST READY texture is offered first -- true by construction;
 *               0 = holds no source frame;
 *   tex_frame / tex_t_take / tex_t_done   the frame index and the two consumer
 *               instants, so the STARTUPV record can still say when the
 *               operator first saw real video. Bookkeeping, never a decision. */
static uint32_t tex_seq[PLAY_TEX_BUFFERS];
static uint32_t tex_frame[PLAY_TEX_BUFFERS];
static uint64_t tex_t_take[PLAY_TEX_BUFFERS], tex_t_done[PLAY_TEX_BUFFERS];
static uint32_t take_seq;
static struct {
    int have;
    uint32_t frame_index;
    uint64_t t_take, t_convert_done, t_decision;
} first_real;

static uint32_t conv_abandoned_no_raw;
static int gx_drained_at_teardown, gx_callback_restored;
static uint32_t flag15_last_count;
static uint32_t flag15_last_x, flag15_last_y;
static const struct gbp_vstate *pump_state;

/* ---- the startup profile (§V5.52): NORMAL unless the build says otherwise ---- */
#ifndef GBP_STARTUP_MODE
#define GBP_STARTUP_MODE GBP_STARTUP_NORMAL
#endif
static struct gbp_startup startup;

/* ---- the two stream framebuffers, plus the console's own ---------------- */
static void *xfb_stream_buf[GBP_VPRESENT_XFB_BUFFERS];

static int xfb_current_index(void)
{
    void *cur = VIDEO_GetCurrentFramebuffer();
    uint32_t i;
    for (i = 0; i < GBP_VPRESENT_XFB_BUFFERS; i++)
        if (cur == xfb_stream_buf[i]) return (int)i;
    return -1;
}

static void *xfb_stream;      /* GX copies the AGB image here */
static void *xfb_text;        /* the console report lives here, so they never fight */
static GXRModeObj *rmode;
static int gecko_present;

#define GX_FIFO_BYTES (256 * 1024)
static uint8_t gx_fifo[GX_FIFO_BYTES] ATTRIBUTE_ALIGN(32);

static void gecko_puts(const char *line)
{
    if (gecko_present) usb_sendbuffer_safe(GECKO_CHANNEL, line, (int)strlen(line));
}

/* The GP finished the commands up to the pending token, so the ONE submitted
 * texture is free. Interrupt time; exactly one thing: the ownership module
 * releases exactly one buffer by index (§V5.26.2). No clock is read here any
 * more: the timestamp the disposition trace took is gone with the trace. */
static void on_draw_done(void)
{
    (void)gbp_vpresent_draw_done(&present);
}

static void video_setup(void)
{
    VIDEO_Init();
    rmode = VIDEO_GetPreferredMode(NULL);
    xfb_stream_buf[0] = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
    xfb_stream_buf[1] = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
    xfb_stream = xfb_stream_buf[0];
    xfb_text   = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
    CON_Init(xfb_text, 20, 20, rmode->fbWidth, rmode->xfbHeight, rmode->fbWidth * VI_DISPLAY_PIX_SZ);
    if (startup.clear_framebuffers) {
        VIDEO_ClearFrameBuffer(rmode, xfb_stream_buf[0], COLOR_BLACK);
        VIDEO_ClearFrameBuffer(rmode, xfb_stream_buf[1], COLOR_BLACK);
    }
    VIDEO_Configure(rmode);
    VIDEO_SetNextFramebuffer(xfb_text);
    VIDEO_SetBlack(false);
    VIDEO_Flush();
    VIDEO_WaitVSync();
    if (rmode->viTVMode & VI_NON_INTERLACE) VIDEO_WaitVSync();
}

/* Minimal GX: one RGB5A3 texture drawn as one quad, orthographic, no lighting,
 * no filter, no effect (§V5.12, §V5.16). Unchanged from stream-0015. */
static GXDrawDoneCallback gx_prev_drawdone_cb;

static void gx_setup(void)
{
    GXColor background = { 0, 0, 0, 0xFF };
    Mtx44 proj;
    Mtx mv;

    memset(gx_fifo, 0, sizeof gx_fifo);
    GX_Init(gx_fifo, sizeof gx_fifo);
    GX_SetCopyClear(background, 0x00FFFFFF);
    GX_SetViewport(0, 0, rmode->fbWidth, rmode->efbHeight, 0, 1);
    GX_SetDispCopyYScale((f32)rmode->xfbHeight / (f32)rmode->efbHeight);
    GX_SetScissor(0, 0, rmode->fbWidth, rmode->efbHeight);
    GX_SetDispCopySrc(0, 0, rmode->fbWidth, rmode->efbHeight);
    GX_SetDispCopyDst(rmode->fbWidth, rmode->xfbHeight);
    GX_SetCopyFilter(rmode->aa, rmode->sample_pattern, GX_TRUE, rmode->vfilter);
    GX_SetFieldMode(rmode->field_rendering,
                    ((rmode->viHeight == 2 * rmode->xfbHeight) ? GX_ENABLE : GX_DISABLE));
    GX_SetPixelFmt(rmode->aa ? GX_PF_RGB565_Z16 : GX_PF_RGB8_Z24, GX_ZC_LINEAR);
    GX_SetCullMode(GX_CULL_NONE);
    GX_SetZMode(GX_FALSE, GX_ALWAYS, GX_FALSE);
    GX_SetColorUpdate(GX_TRUE);
    GX_CopyDisp(xfb_stream_buf[0], GX_TRUE);
    GX_SetDispCopyGamma(GX_GM_1_0);

    GX_ClearVtxDesc();
    GX_SetVtxDesc(GX_VA_POS, GX_DIRECT);
    GX_SetVtxDesc(GX_VA_TEX0, GX_DIRECT);
    GX_SetVtxAttrFmt(GX_VTXFMT0, GX_VA_POS, GX_POS_XY, GX_F32, 0);
    GX_SetVtxAttrFmt(GX_VTXFMT0, GX_VA_TEX0, GX_TEX_ST, GX_F32, 0);
    GX_SetNumChans(0);
    GX_SetNumTexGens(1);
    GX_SetTexCoordGen(GX_TEXCOORD0, GX_TG_MTX2x4, GX_TG_TEX0, GX_IDENTITY);
    GX_SetTevOp(GX_TEVSTAGE0, GX_REPLACE);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORD0, GX_TEXMAP0, GX_COLORNULL);
    GX_SetNumTevStages(1);

    guOrtho(proj, 0.0f, (f32)rmode->efbHeight, 0.0f, (f32)rmode->fbWidth, 0.0f, 300.0f);
    GX_LoadProjectionMtx(proj, GX_ORTHOGRAPHIC);
    guMtxIdentity(mv);
    GX_LoadPosMtxImm(mv, GX_PNMTX0);

    gx_prev_drawdone_cb = GX_SetDrawDoneCallback(on_draw_done);
}

/* Native 240x160, centred, unscaled. Scaling and aspect are Phase 9 policy. */
static void draw_quad(void)
{
    const f32 w = (f32)GBP_VPIX_WIDTH, h = (f32)GBP_VPIX_HEIGHT;
    const f32 x0 = ((f32)rmode->fbWidth - w) * 0.5f;
    const f32 y0 = ((f32)rmode->efbHeight - h) * 0.5f;

    GX_Begin(GX_QUADS, GX_VTXFMT0, 4);
        GX_Position2f32(x0,     y0);     GX_TexCoord2f32(0.0f, 0.0f);
        GX_Position2f32(x0 + w, y0);     GX_TexCoord2f32(1.0f, 0.0f);
        GX_Position2f32(x0 + w, y0 + h); GX_TexCoord2f32(1.0f, 1.0f);
        GX_Position2f32(x0,     y0 + h); GX_TexCoord2f32(0.0f, 1.0f);
    GX_End();
}

static void submit_ready(int buf, struct gbp_vqueue *account);
static void offer_oldest_ready(void);

/* ---- the display self-test (§V5.26.4, §V5.52) ----------------------------
 * Walks the display path once from a SYNTHETIC coordinate gradient, before any
 * device is touched, so the path is not dead code. Under the NORMAL profile
 * the submit is headless (no framebuffer is claimed, nothing synthetic is
 * shown). It proves the code runs and the ownership machine ends where it
 * started; it proves nothing about the Game Boy Player. */
static uint32_t selftest_headless;

static void selftest_submit_headless(int buf)
{
    if (!gbp_vpresent_submit(&present, buf)) return;
    GX_InvalidateTexAll();
    GX_InitTexObj(&tex_obj, tex_buf[buf], GBP_VPIX_WIDTH, GBP_VPIX_HEIGHT,
                  GX_TF_RGB5A3, GX_CLAMP, GX_CLAMP, GX_FALSE);
    GX_InitTexObjFilterMode(&tex_obj, GX_NEAR, GX_NEAR);
    GX_LoadTexObj(&tex_obj, GX_TEXMAP0);
    draw_quad();
    GX_SetDrawDone();                 /* the callback releases the texture */
    GX_Flush();
    selftest_headless++;
}

static uint8_t selftest_raw[GBP_VPIX_FRAME_BYTES] ATTRIBUTE_ALIGN(32);
static int selftest_ok, selftest_released, selftest_converted, selftest_sci_clean;
static uint32_t selftest_presents, selftest_repeats;

static void display_selftest(void)
{
    struct gbp_vpix_stats st;
    uint32_t x, y, spins;
    int buf;

    for (y = 0; y < GBP_VPIX_HEIGHT; y++) {
        for (x = 0; x < GBP_VPIX_WIDTH; x++) {
            const uint16_t w = (uint16_t)(((x >> 3) << 10) | ((y >> 3) << 5) | ((x ^ y) & 0x1Fu));
            const size_t o = gbp_vpix_raw_offset(x, y);
            selftest_raw[o + 0] = 0x5Au;
            selftest_raw[o + 1] = (uint8_t)(w >> 8);
            selftest_raw[o + 2] = 0xA5u;
            selftest_raw[o + 3] = (uint8_t)(w & 0xFFu);
        }
    }

    buf = gbp_vpresent_acquire(&present);
    if (buf < 0) return;
    if (gbp_vpix_frame(selftest_raw, sizeof selftest_raw, tex_buf[buf],
                       GBP_VPIX_TEX_BYTES / 2u, &st) != 0) {
        (void)gbp_vpresent_abandon(&present, buf);
        return;
    }
    selftest_converted = (st.pixels == GBP_VPIX_WIDTH * GBP_VPIX_HEIGHT) ? 1 : 0;
    DCFlushRange(tex_buf[buf], GBP_VPIX_TEX_BYTES);
    (void)gbp_vpresent_fill_done(&present, buf);
    tex_seq[buf] = 0u;                /* no source frame: never ordered ahead of one */
    if (startup.selftest_visible) {
        unsigned k;
        for (k = 0; k < 8u; k++) {
            submit_ready(buf, 0);
            if (present.tex[buf] != GBP_VPRESENT_READY) break;
            VIDEO_WaitVSync();
        }
    } else {
        selftest_submit_headless(buf);
    }
    for (spins = 0; spins < 600u && gbp_vpresent_inflight(&present); spins++) VIDEO_WaitVSync();
    selftest_released = gbp_vpresent_inflight(&present) ? 0 : 1;
    selftest_sci_clean = gbp_vqueue_pristine(&vq);
    selftest_ok = (selftest_converted && selftest_released && selftest_sci_clean &&
                   (startup.selftest_visible ? (selftest_presents >= 1u)
                                             : (selftest_headless >= 1u)) &&
                   gbp_vpresent_consistent(&present) &&
                   gbp_vpresent_invariant_failures(&present) == 0u) ? 1 : 0;
}

/* ---- Issue #19 (Phase 5): the input path in the pump slot ----------------------
 *
 * GameCube pad 1 -> gbp_input_map (POLICY) -> gbp_keypad_encode (the ONE
 * descriptor in src/gbp/gbp_input.c) -> one 32-byte write at KEYPAD (index
 * 0xC) through the SAME transport the RE-ARM uses -- written on change and as
 * a periodic refresh every GBP_INPUT_REFRESH_MS (INPUT_PATH.md §7).
 *
 * WHERE: the first statement of pump(), i.e. inside the slot gbp_vqueue_pump()
 * admits after the RE-ARM only when no cause is pending -- so the poll and the
 * write obey the same yield rule as the consumer slice, run from the main loop,
 * never in the ISR, never inside the service transaction, never overlapping a
 * service DMA (the transport's write is synchronous and completion-polled).
 * It runs BEFORE the slice's early returns so it is unconditional within the
 * slot; the slice's own measurement (t0..t1 below) starts after it, so the
 * STREAMPUMPT aggregate still measures the conversion alone.
 *
 * CLOCKS: every instant here comes from the transport's `ticks` / `ticks64`
 * operations (h_ticks / h_ticks64), never from a direct gettime()/gettick():
 * the stream audit pins the gettime call sites of pump() and main(), and the
 * input path adds none. `t_poll` is taken right after PAD_ScanPads() returns;
 * libogc2's PAD_ScanPads() copies the SI hardware's last poll response (pad.c,
 * PAD_Read: no transfer is issued synchronously), and at the library's default
 * sampling rate 0 the SI polls the pads twice per video frame (si.c, the xy
 * table), so the sample precedes t_poll by at most one SI polling period.
 * `t_write` is the transport's instant after the DMA completed. Both are
 * FIELDS of `in_state`; nothing emits them (INPUT_PATH.md §8, Issue #19).
 *
 * The device's state is unknown before the first write, so the first admitted
 * step always writes the current word -- with nothing held, that is the
 * `KEYPAD := 0` both references start from. No release is written at the
 * teardown: the validated stop sequence is untouched, and what the device
 * keeps after it is a question for the first physical input run. */
static struct gbp_input in_state;
static const struct gbp_transport *in_transport;   /* the probe's transport; set before the run */
static int in_selftest_ok;
_Static_assert(GBP_PAD_BUTTON_LEFT == PAD_BUTTON_LEFT && GBP_PAD_BUTTON_RIGHT == PAD_BUTTON_RIGHT &&
               GBP_PAD_BUTTON_DOWN == PAD_BUTTON_DOWN && GBP_PAD_BUTTON_UP == PAD_BUTTON_UP &&
               GBP_PAD_BUTTON_Z == PAD_BUTTON_Z && GBP_PAD_BUTTON_R == PAD_BUTTON_R &&
               GBP_PAD_BUTTON_L == PAD_BUTTON_L && GBP_PAD_BUTTON_A == PAD_BUTTON_A &&
               GBP_PAD_BUTTON_B == PAD_BUTTON_B && GBP_PAD_BUTTON_X == PAD_BUTTON_X &&
               GBP_PAD_BUTTON_Y == PAD_BUTTON_Y && GBP_PAD_BUTTON_START == PAD_BUTTON_START,
               "the input module's controller bits must be libogc2's");
_Static_assert(GBP_PAD_ERR_NONE == PAD_ERR_NONE && GBP_PAD_ERR_NO_CONTROLLER == PAD_ERR_NO_CONTROLLER,
               "the input module's pad error codes must be libogc2's");

/* ---- Issue #92: PHASE 6's ACCEPTANCE (§V22) ----------------------------------
 *
 * Everything below is §V22 with §V22.8's readings and §V22.9 AMENDMENT 1. The
 * accounting is src/audio/gbp_alive and the chain src/audio/gbp_aplay; the decoder,
 * the resampler and the positive control's period decoder are linked UNCHANGED. */
#define LIVE_SEC_PER_LINE 16u
/* §V27.1: NO L2 keep runs in this image -- gbp_aplay_arm_l2 is never called, no keep or
 * event store is bound, and no L2 sidecar exists. Bit-exactness was established by RUN 42. */
_Static_assert(GBP_ALIVE_PAD_A == PAD_BUTTON_A, "gbp_alive's A must be libogc2's");
_Static_assert(GBP_ALIVE_PAD_BUTTONS == PAD_BUTTON_ALL, "the press record reads every button and no stick");
_Static_assert(GBP_APLAY_RING >= 2u * 100u, "D2's x2 rule: the ring holds at least 200 decoded samples");
_Static_assert(GBP_APLAY_CHUNK_BYTES % 32u == 0u, "an AI DMA block is a whole number of 32-byte units");
/* GAME 1 (Issue #110, §V25.7 2(a), (r1)): the press origin's delay. CHOSEN, not derived:
 * RUN 40's press-to-origin, through two control windows, was 1.0002 s. */
#define GAME_ORIGIN_DELAY_MS 1000u
/* GAME 6 (Issue #113, (s6)): the before-AI frames listed, at most; more is counted, and v26accept declines */
#define GAME_BEFORE_LIST_CAP 64u
/* GAME 4 (§V25.7 4, (r7)): the video's location, filled after the session and read by the
 * screen report (GAME 5) */
static uint32_t game_vsec[GBP_ALIVE_MAX_SECONDS];
static uint32_t game_v_before, game_v_inside, game_v_after, game_v_stored, game_v_sec_overflow;

static struct gbp_alive live;
static struct gbp_aperiod live_per;          /* the positive control's window (§V19.11 A4.7) */
static struct gbp_adec adec;
static int16_t adec_ring[GBP_APLAY_RING] ATTRIBUTE_ALIGN(32);
static struct gbp_aplay ap;
static uint8_t ap_pool[GBP_APLAY_POOL * GBP_APLAY_CHUNK_BYTES] ATTRIBUTE_ALIGN(32);
static uint8_t ap_silence[GBP_APLAY_CHUNK_BYTES] ATTRIBUTE_ALIGN(32);
/* ---- §V27: the session machine, the raw window, the transition's plan --------------------- */
#define SYNC_AWR_BLOCKS 640u
/* the A press is admitted this long after the prompt; then the run ends as `prompt_expired` (no
 * origin, nothing to judge) instead of running on to the safety wall */
#define SYNC_PROMPT_BOUND_S 45u                  /* §V27.11: 1 280 do not fit game-0002's arena (94 KB short); 640 do */
static struct gbp_async sync;
static struct gbp_awr awr;
static uint8_t awr_store[SYNC_AWR_BLOCKS * GBP_AWR_BLOCK_SIZE] ATTRIBUTE_ALIGN(32);   /* 2.5 MiB */
static uint32_t sync_seed;
static int sync_started;
/* Phase 3: the dwell's counters are deltas against these, taken when its plan is applied */
static uint32_t dwell_underruns0, dwell_overflow0, dwell_dup0, dwell_drop0, dwell_blocks0;
static uint64_t dwell_t0;
static uint32_t sync_cs_events, sync_cs_acted, sync_plans, sync_p2_lines, sync_z_skips;
/* a plan-making C-stick edge while the executor still lands the last plan: refused, counted (review round 3) */
static uint32_t sync_cs_busy;
/* a plan applied over a running one: never, with the tick held while the executor runs; counted if it were */
static uint32_t sync_preempts;
static uint64_t sync_last_now;                  /* the last live_step's tick: a pending depth's report at the end */
static uint32_t sync_p3_drained;                /* pending depths reported after the session (the backstop) */
static uint8_t sync_prompt_expired;             /* no A within SYNC_PROMPT_BOUND_S of the prompt */
/* per Phase 3 depth, beside gbp_async's own row: the drain readable from the log whatever the
 * failure criterion reads (the objection on #117: at 128 the queue drains, the underrun comes ~44 s
 * later, the dwell is 6 s) */
struct sync_depth_extra { uint32_t starved, ready_in, ready_out, fill_in, fill_out, fill_n; };
static struct sync_depth_extra sync_dx[GBP_ASYNC_DEPTH_CAP];
static uint32_t dwell_starved0, dwell_ready0, dwell_fill0;
static int z_can_act = 1;                     /* one skip per Z hold: re-armed when Z is released */
static int live_end;                          /* cfg.session_end: the session's end (gbp_async), or Z */
static uint32_t live_taps, live_taps_failed, live_wrong_len;
static uint64_t live_gap_max, live_gap_at, live_last_t;
static int ai_started, ai_stopped;
static uint64_t t_ai_start, t_ai_stop;
static int live_drawn_prompt, live_drawn_press;

/* THE AUDIO TAP. Inside the service transaction, once per AUDIO drain, after the
 * drain and its commit: bounded, no device, no allocation, no filesystem, no print.
 * What the block is for is gbp_alive's decision. */
static void live_tap(void *user, const uint8_t *bytes, uint32_t len, uint64_t t_done, int completed)
{
    int act;
    (void)user;
    live_taps++;
    if (!live.t0)
        gbp_alive_start(&live, (pump_res && pump_res->t_capture_start) ? pump_res->t_capture_start : t_done);
    if (!completed) { live_taps_failed++; return; }        /* not coverage; the service ends the run anyway */
    if (len != GBP_ADEC_BLOCK_BYTES) { live_wrong_len++; return; }
    {
        const uint32_t fill_before = adec.count;
        act = gbp_alive_block(&live, t_done, fill_before);
        /* §V27: the session starts at gbp_alive's origin (the A press + the delay, its first window
         * block) with the seed the press's own tick gave; the raw window is armed at the same block */
        if (!sync_started && live.phase == GBP_ALIVE_WINDOW && live.t_origin) {
            sync_started = 1;
            sync_seed = (uint32_t)live.t_press;
            gbp_async_start(&sync, live.t_origin, sync_seed);
            /* the seeded initial level is the chain's target from the origin on: the AI starts at it
             * (live_step's `adec.count >= ap.target`) and the corrections hold it. A field write with
             * a clamp, no device. Without it half the seeds ran Phase 0 at 2048 while the rows said 512
             * and the first REAL switch was a null (caught by review before the commit). */
            gbp_aplay_set_target(&ap, sync.target);
            (void)gbp_awr_arm(&awr, live.t_origin);
        }
        /* the chain keeps decoding through gbp_alive's own 64 s window end: the session's bound is
         * gbp_async's (720 s), and every block of it is binned there */
        if (act == GBP_ALIVE_DO_DECODE || (sync_started && !sync.finished && live.phase == GBP_ALIVE_DONE)) {
            if (live_last_t && t_done - live_last_t > live_gap_max) { live_gap_max = t_done - live_last_t; live_gap_at = t_done; }
            live_last_t = t_done;
            if (sync_started) gbp_async_block(&sync, t_done, fill_before);
            /* the ride-along: right after the origin, before any switch can happen (§V27.11); the copy's
             * cost measured around the whole call and reported, never inferred */
            if (awr.state == GBP_AWR_ARMED || awr.state == GBP_AWR_FILLING) {
                const uint32_t c0 = in_transport ? in_transport->ticks(in_transport->ctx) : 0u;
                if (gbp_awr_block(&awr, bytes, len, t_done, live_taps) && in_transport)
                    gbp_awr_note_cost(&awr, in_transport->ticks(in_transport->ctx) - c0);
            }
            /* L reads the sample AS IT LEAVES THE DECODER, before any correction (§V22.8 (e)) */
            if (gbp_adec_push_block(&adec, bytes) == 0)
                gbp_alive_decoded(&live, adec.ring[(adec.head + adec.count - 1u) % adec.cap]);
            act = GBP_ALIVE_DO_DECODE;
        }
    }
    if (act == GBP_ALIVE_DO_DECODE) {
        /* handled above */
    } else if (act == GBP_ALIVE_DO_CONTROL) {
        (void)gbp_aperiod_feed(&live_per, bytes, len);
        if (live_per.blocks >= GBP_ALIVE_CONTROL_BLOCKS) {
            gbp_alive_control_window(&live, t_done, gbp_aperiod_exact(&live_per, GBP_ALIVE_CONTROL_MIN),
                                     live_per.periods, live_per.pmin, live_per.pmax, live_per.blocks);
            gbp_aperiod_reset(&live_per, GBP_ALIVE_PERIOD);
        }
    } else if (act == GBP_ALIVE_DO_CALIBRATE) {
        gbp_adec_calibrate(&adec, bytes);
    }
    /* §V27: gbp_alive's window end does NOT end the session; gbp_async's does (or Z, in the pump) */
    if (sync_started && gbp_async_finished(&sync)) live_end = 1;
    else if (!sync_started && gbp_alive_finished(&live)) live_end = 1;   /* the origin never came: as game-0002 */
}

/* THE AI DMA CALLBACK. Interrupt context: the block programmed last time has just
 * started; hand the next READY chunk, or silence (an UNDERRUN while playing), and
 * timestamp it (M). No print, no allocation, no file, nothing that can wait. */
static void live_dma_cb(void)
{
    const uint8_t *c = gbp_aplay_irq_handoff(&ap, gettime());
    AUDIO_InitDMA((u32)(size_t)c, GBP_APLAY_CHUNK_BYTES);
}
/* ---- Issue #27 (GBP-KEY-009): the per-change record ----------------------------
 *
 * ONE ringlog line ("KEY …", GBP_INPUT_EVENT_FMT of gbp_input.h) per write that
 * was NOT a refresh -- first / change / retry -- emitted here, from the pump
 * slot, right after the write it describes: never from the ISR, never inside
 * the service transaction (the slot is after the RE-ARM, under the
 * cause-pending yield rule). RUN 14 wrote 7 849 refreshes against 42 changes:
 * a refresh is never recorded, only counted (INPUT refresh=).
 *
 * BOUND (CLAUDE.md §13). The store is the ringlog itself -- preallocated,
 * LOG_LINES lines, never grown -- and a line is admitted only while
 * KEYLOG_TAIL_RESERVE lines stay free for the post-run summary records
 * (tests/host/test_input_keylog.py counts them against this constant). A run
 * with more changes than the headroom holds keeps every summary, keeps
 * `dropped=0`, and counts the surplus in keylog_lost (the KEYLOG record):
 * bounded, never blocking, never silent. The cost is one vsnprintf of at most
 * GBP_INPUT_EVENT_RENDER_MAX characters, measured with the transport's ticks
 * and reported as KEYLOG emit_ticks -- outside the INPUTT step aggregate, so
 * RUN 14 / RUN 15's step figures stay comparable.
 *
 * The instants are the transport's ticks64: the gbp_time64 base of
 * OGBPIDXCAP1, OGBPDISP2 and OGBPVI1, so a join to the frame records needs no
 * conversion. INPUT_PATH.md §8's observability guarantee is spent here. */
/* Issue #39: 640, not stream-0015's 64 -- the reserve must cover the WHOLE
 * post-run report (the state machine's EV / CYC / READDISAGREE lines and this
 * file's records: 462 lines in RUN 17), because the ringlog drops, it does not
 * overwrite. The functions below are byte-identical to stream-0015's. */
#define KEYLOG_TAIL_RESERVE 1280u      /* §V27: RUN 42's tail (about 490 records) plus the SYNC records (about 500) */
static struct ringlog *keylog_rl;            /* armed with the run, like in_transport */
static uint32_t keylog_emitted, keylog_lost, keylog_truncated;
static uint32_t keylog_ticks_min, keylog_ticks_max, keylog_ticks_n;
static uint64_t keylog_ticks_sum;

static void keylog_emit(const struct gbp_transport *t)
{
    struct gbp_input_event e;
    uint32_t t0, dt;
    int r;

    if (!gbp_input_take_event(&in_state, &e)) return;
    if (!keylog_rl || !gbp_input_keylog_admit((uint32_t)keylog_rl->count, (uint32_t)keylog_rl->capacity, KEYLOG_TAIL_RESERVE)) {
        keylog_lost++;
        return;
    }
    t0 = t->ticks(t->ctx);
    r = ringlog_printf(keylog_rl, GBP_INPUT_EVENT_FMT, GBP_INPUT_EVENT_ARGS(&e));
    dt = t->ticks(t->ctx) - t0;
    if (r < 0) { keylog_lost++; return; }        /* cannot happen under the admit rule; counted, never silent */
    if (r > 0) keylog_truncated++;               /* cannot happen at GBP_INPUT_EVENT_RENDER_MAX < 248; counted */
    keylog_emitted++;
    if (keylog_ticks_n == 0u || dt < keylog_ticks_min) keylog_ticks_min = dt;
    if (dt > keylog_ticks_max) keylog_ticks_max = dt;
    keylog_ticks_n++;
    keylog_ticks_sum += dt;
}

static void input_step(void)
{
    const struct gbp_transport *t = in_transport;
    struct gbp_pad_sample s;
    uint32_t t0, connected;
    uint64_t t_poll;
    enum gbp_input_action act;

    if (!t) return;
    if (!in_state.base) {
        /* the ARAM base is the 003A stage's; until it is known nothing is polled or written */
        if (!pump_res || !pump_res->a.base) { in_state.skipped_no_base++; return; }
        gbp_input_set_base(&in_state, pump_res->a.base);
    }
    t0 = t->ticks(t->ctx);
    connected = PAD_ScanPads();
    t_poll = t->ticks64(t->ctx);
    s.buttons = (uint16_t)(PAD_ButtonsHeld(PAD_CHAN0) & 0xFFFFu);
    s.stick_x = PAD_StickX(PAD_CHAN0);
    s.stick_y = PAD_StickY(PAD_CHAN0);
    s.substick_x = PAD_SubStickX(PAD_CHAN0);
    s.substick_y = PAD_SubStickY(PAD_CHAN0);
    s.trigger_l = PAD_TriggerL(PAD_CHAN0);
    s.trigger_r = PAD_TriggerR(PAD_CHAN0);
    s.analog_a = PAD_AnalogA(PAD_CHAN0);
    s.analog_b = PAD_AnalogB(PAD_CHAN0);
    s.err = (connected & 1u) ? GBP_PAD_ERR_NONE : GBP_PAD_ERR_NO_CONTROLLER;
    act = gbp_input_step(&in_state, t, &s, t_poll);
    gbp_input_note_step_ticks(&in_state, t->ticks(t->ctx) - t0);
    /* Issue #27: the record of a first / change / retry write, after the step's own measurement */
    if (act == GBP_INPUT_WRITE_FIRST || act == GBP_INPUT_WRITE_CHANGE || act == GBP_INPUT_WRITE_RETRY)
        keylog_emit(t);
}

/* Issue #39: the ringlog's headroom, checked where it cannot be argued with. */
_Static_assert(KEYLOG_TAIL_RESERVE >= 600u, "the post-run reserve must cover the state machine's report (462 lines in RUN 17)");
_Static_assert(LOG_LINES - KEYLOG_TAIL_RESERVE >= 6900u, "the KEY headroom of a long session (about 3 450 presses)");

/* ---- Issue #39: the session end, in the pump slot ------------------------
 *
 * Reads the sample input_step() just took -- PAD_ButtonsHeld() returns the
 * state of the last PAD_ScanPads(); no second scan, no SI transfer -- takes
 * the transport's 64-bit instant, and feeds the pure state machine. Z is the
 * one input the policy never sends to the AGB, so a hold cannot be a game
 * action. The flag the service-path module reads is `session.end_requested`,
 * installed once as cfg.session_end; nothing here touches the device, formats
 * anything or waits. The same admission as input_step(): nothing before the
 * ARAM base is known, which input_step() records as `in_state.base`. */
static struct gbp_session session;
static uint64_t session_hold_ticks;

static void session_step(void)
{
    const struct gbp_transport *t = in_transport;
    if (!t || !in_state.base) return;
    (void)gbp_session_sample(&session, (PAD_ButtonsHeld(PAD_CHAN0) & PAD_BUTTON_Z) ? 1 : 0,
                             t->ticks64(t->ctx));
}

/* ---- Issue #92: the chain's pump-slot half ----------------------------------
 * The press record from the sample input_step() just took, the chain's bounded
 * step, the AI's start once the ring holds 0.5 s and its stop when the window
 * closes, and the two screen lines the run is allowed -- both before C's window.
 * No SD, no device. */
static void live_screen(uint64_t now)
{
    if (!live_drawn_prompt && live.t_accept && now >= live.t_accept && live.phase == GBP_ALIVE_PROMPT) {
        live_drawn_prompt = 1;
        printf("\x1b[8;0H");
        printf("  >>> PRESS A within 45 s: the game appears. Then follow the checklist (C-stick). <<<  ");
    }
    if (!live_drawn_press && live.phase == GBP_ALIVE_DELAY) {       /* GAME 3: the press starts the delay */
        /* drawn at the press, BEFORE C's window: never a print inside it */
        live_drawn_press = 1;
        printf("\x1b[10;0H");
        printf("  A RECEIVED. The game appears now. C-stick DOWN switches; LEFT/RIGHT/UP answer.     ");
        printf("\x1b[11;0H");
        printf("  Hold Z 1/4 s to move to the next phase. The report appears when the game disappears.");
    }
}

/* ---- §V27: the transition executor (pump slot) --------------------------------------
 * src/audio/gbp_atrans applies gbp_async's plans to the chain and the ring, ONE at a time,
 * and is tested on the host against the real gbp_aplay / gbp_adec with a simulated AI
 * (tests/unit/test_gbp_atrans.c: every plan lands the ring exactly at its level). Here:
 * the one instance, begun from the plan application and stepped once per pump call. */
static struct gbp_atrans trans;
/* per Phase 1 switch, the executor's own account (§V27.15: masking is audited per switch on the SD);
 * done: 0 never begun, 1 landed, 2 cut by a plan applied over it (never: sync_preempts), 3 begun and not
 * landed (the session stopped under it) */
struct sync_tx { uint8_t done, mech, late, unmasked; uint32_t mute, rotations, topped; int32_t residue; };
static struct sync_tx sync_tx[GBP_ASYNC_SWITCH_CAP];
static int32_t trans_sw = -1;                    /* the switch the running plan belongs to, else -1 */

static void sync_trans_done(void)
{
    if (trans_sw >= 0 && trans_sw < (int32_t)GBP_ASYNC_SWITCH_CAP) {
        struct sync_tx *x = &sync_tx[trans_sw];
        x->done = 1u; x->mech = trans.mode; x->late = trans.late; x->unmasked = trans.unmasked;
        x->mute = trans.mute; x->rotations = trans.rotations; x->topped = trans.topped; x->residue = trans.residue;
    }
    trans_sw = -1;
}

/* ---- §V27: the C-stick, the only control the cartridge never receives ------------------
 * An EDGE: the stick leaves the centre (past +-CS_THRESHOLD on its larger axis) after having
 * been at the centre, with CS_DEAD_MS of dead time after each edge. The main stick's threshold
 * is reused so the two sticks agree on what "pressed" means. */
#define CS_THRESHOLD GBP_INPUT_POLICY_STICK_THRESHOLD
#define CS_DEAD_MS   250u
enum cs_dir { CS_NONE = 0, CS_UP, CS_DOWN, CS_LEFT, CS_RIGHT };
static enum cs_dir cs_last;
static uint64_t cs_dead_until;
static uint32_t cs_edges, cs_ignored_dead;

static enum cs_dir cs_read(int8_t x, int8_t y)
{
    int ax = x < 0 ? -x : x, ay = y < 0 ? -y : y;
    if (ax >= ay) {
        if (ax >= CS_THRESHOLD) return x > 0 ? CS_RIGHT : CS_LEFT;
        return CS_NONE;
    }
    if (ay >= CS_THRESHOLD) return y > 0 ? CS_UP : CS_DOWN;
    return CS_NONE;
}

/* the edge, or CS_NONE; called once per pump call with the sample input_step() took */
static enum cs_dir cs_edge(uint64_t now)
{
    enum cs_dir d = cs_read(PAD_SubStickX(PAD_CHAN0), PAD_SubStickY(PAD_CHAN0));
    enum cs_dir out = CS_NONE;
    if (d != CS_NONE && cs_last == CS_NONE) {
        if (now >= cs_dead_until) {
            out = d;
            cs_edges++;
            cs_dead_until = now + ((uint64_t)live.tb_hz * CS_DEAD_MS) / 1000u;
        } else {
            cs_ignored_dead++;
        }
    }
    cs_last = d;
    return out;
}

/* a SYNC line during the run takes the KEY lines' admission rule, so the reserve stays whole for the
 * post-run records the builder needs; a refusal is counted (SYNCC2 lines_lost), never silent */
static uint32_t sync_lines_lost;
static int sync_line_admit(void)
{
    if (keylog_rl && gbp_input_keylog_admit((uint32_t)keylog_rl->count, (uint32_t)keylog_rl->capacity, KEYLOG_TAIL_RESERVE))
        return 1;
    sync_lines_lost++;
    return 0;
}

static void sync_apply_plan(uint64_t now)
{
    const struct gbp_async_plan *pl = &sync.plan;
    sync_plans++;
    if (pl->kind == GBP_ASYNC_KIND_DEPTH) {
        /* Phase 3: the dwell's baselines, then the level with no silence */
        dwell_underruns0 = ap.underruns; dwell_overflow0 = adec.overflow;
        dwell_dup0 = ap.dup; dwell_drop0 = ap.drop; dwell_blocks0 = adec.blocks_in; dwell_t0 = now;
        /* §V27.14's `starved` is gbp_aplay's ring_gated -- a chunk WANTED, the ring short -- not starved_steps,
         * which also counts the benign wait after every chunk with READY full (review round 3) */
        dwell_starved0 = ap.ring_gated; dwell_ready0 = gbp_aplay_ready(&ap); dwell_fill0 = adec.count;
    } else if (pl->kind == GBP_ASYNC_KIND_START || pl->kind == GBP_ASYNC_KIND_STEP) {
        /* Phase 2's transitions are not kept by the module: recorded here, SD only, bounded */
        if (sync_p2_lines < 200u && sync_line_admit()) {
            sync_p2_lines++;
            ringlog_printf(keylog_rl, "SYNCP2 seq=%lu kind=%s from=%lu to=%lu t=%llx", (unsigned long)pl->seq,
                           gbp_async_kind_name(pl->kind), (unsigned long)pl->from, (unsigned long)pl->to,
                           (unsigned long long)pl->t);
        }
    }
    if (trans.active) {                            /* never, with the tick held and busy edges refused */
        const int32_t cut = trans_sw;
        sync_preempts++;
        sync_trans_done();                         /* the running switch's record as it stands ... */
        if (cut >= 0 && cut < (int32_t)GBP_ASYNC_SWITCH_CAP) sync_tx[cut].done = 2u;   /* ... marked cut, not landed */
    }
    /* a switch's plan: the module has recorded it already, so it is the last one */
    trans_sw = (pl->kind == GBP_ASYNC_KIND_REAL || pl->kind == GBP_ASYNC_KIND_NULL) ? (int32_t)sync.switches - 1 : -1;
    if (trans_sw >= 0 && trans_sw < (int32_t)GBP_ASYNC_SWITCH_CAP) {   /* begun: landed (1) or cut (2) overwrite it */
        sync_tx[trans_sw].done = 3u; sync_tx[trans_sw].mech = pl->mech; sync_tx[trans_sw].mute = pl->mute_chunks;
    }
    gbp_atrans_begin(&trans, &ap, &adec, now, pl->mech, pl->mute_chunks, pl->pause_chunks, pl->discard, pl->to);
}

/* returns 1 when the next depth's plan is in sync.plan */
static int sync_dwell_done(uint64_t now)
{
    /* the settled fill: the mean over the dwell's last three whole seconds, from the module's own bins.
     * A dwell cut before its end (cap, session cap, Z) is read to its actual end, and never before its
     * own set second (review before the commit: the planned end's window was empty for a cut 3 s early) */
    const uint64_t t_end = sync.p3_dwell_cut ? sync.ph[GBP_ASYNC_P3].t_end : sync.t_dwell_end;
    const uint32_t s_set = (uint32_t)((sync.plan.t - sync.t_origin) / (uint64_t)live.tb_hz);
    uint32_t s_end = (uint32_t)((t_end - sync.t_origin) / (uint64_t)live.tb_hz);
    uint32_t k0 = s_end >= 3u ? s_end - 3u : 0u;
    uint32_t n = 0u, k, bins = 0u;
    uint64_t sum = 0u;
    if (k0 < s_set) k0 = s_set;
    for (k = k0; k < s_end && k < GBP_ASYNC_SECONDS; k++) {
        if (sync.sec_count[k]) { sum += sync.sec_fill_sum[k]; n += sync.sec_count[k]; bins++; }
    }
    if (sync.depths_n < GBP_ASYNC_DEPTH_CAP) {
        struct sync_depth_extra *x = &sync_dx[sync.depths_n];
        x->starved = ap.ring_gated - dwell_starved0; x->ready_in = dwell_ready0; x->ready_out = gbp_aplay_ready(&ap);
        x->fill_in = dwell_fill0; x->fill_out = adec.count; x->fill_n = bins;
    }
    {
        /* expected over the SAME window `got` spans -- from the apply tick to this tick, in ticks, never
         * truncated seconds (a truncated 5 s against 6 s of blocks hid every loss under 4 096) */
        const uint32_t expected = dwell_t0
            ? (uint32_t)(((now - dwell_t0) * (uint64_t)GBP_ASYNC_RATE) / (uint64_t)live.tb_hz) : 0u;
        const uint32_t got = adec.blocks_in - dwell_blocks0;
        return gbp_async_depth_done(&sync, n ? (uint32_t)(sum * 16u / n) : 0u,
                                    ap.underruns - dwell_underruns0, adec.overflow - dwell_overflow0,
                                    ap.dup - dwell_dup0, ap.drop - dwell_drop0, expected > got ? expected - got : 0u,
                                    ap.ring_gated - dwell_starved0);
    }
}

static void sync_control(uint64_t now)
{
    const enum cs_dir d = cs_edge(now);
    int acted = 0, busy;
    if (d == CS_NONE) return;
    sync_cs_events++;
    /* an edge that would make a plan while the executor still lands the last one is refused and counted:
     * the module's own mute refusal ends up to one hand-off before the executor lands */
    busy = trans.active && ((sync.phase <= GBP_ASYNC_P1 && d == CS_DOWN) ||
                            (sync.phase == GBP_ASYNC_P2 && (d == CS_LEFT || d == CS_RIGHT || d == CS_UP)));
    if (busy) sync_cs_busy++;
    else switch (sync.phase) {
    case GBP_ASYNC_P0:
    case GBP_ASYNC_P1:
        if (d == CS_DOWN) acted = gbp_async_switch(&sync, now);
        else if (d == CS_LEFT) acted = gbp_async_answer(&sync, now, GBP_ASYNC_LESS);
        else if (d == CS_RIGHT) acted = gbp_async_answer(&sync, now, GBP_ASYNC_MORE);
        else acted = gbp_async_answer(&sync, now, GBP_ASYNC_SAME);
        break;
    case GBP_ASYNC_P2:
        if (d == CS_LEFT) acted = gbp_async_step(&sync, now, GBP_ASYNC_LEFT);
        else if (d == CS_RIGHT) acted = gbp_async_step(&sync, now, GBP_ASYNC_RIGHT);
        else if (d == CS_UP) acted = gbp_async_confirm(&sync, now);
        break;
    default:
        break;
    }
    if (acted) sync_cs_acted++;
    /* SD only, bounded: the run's control events (the KEY reserve covers the tail) */
    if (sync_cs_events <= 400u && sync_line_admit())
        ringlog_printf(keylog_rl, "SYNCCS dir=%c phase=%u acted=%d busy=%d t=%llx", "?UDLR"[d], (unsigned)sync.phase,
                       acted, busy, (unsigned long long)now);
    if (acted && (d == CS_DOWN || (sync.phase == GBP_ASYNC_P2 && d != CS_NONE))) sync_apply_plan(now);
}

static void live_step(void)
{
    const struct gbp_transport *t = in_transport;
    uint64_t now;
    int b;
    if (!t || !in_state.base) return;                /* the same admission as input_step() */
    now = t->ticks64(t->ctx);
    /* §V22.9 A3: every button, X included, is recorded -- and none is acted on here */
    gbp_alive_buttons(&live, now, (uint16_t)(PAD_ButtonsHeld(PAD_CHAN0) & 0xFFFFu));
    sync_last_now = now;
    /* ... and while a Phase 3 depth is still to be reported: the tap usually reaches the module first when a
     * cap cuts a dwell (it runs inside the service transaction, before the pump), so `finished` is set with the
     * cut dwell still pending, and its row was lost (review of round 3's fixes). After `finished` the module's
     * switch/step/confirm/skip are no-ops, so entering here only delivers the pending row. */
    if (sync_started && (!sync.finished || sync.p3_depth_pending)) {
        int r;
        /* Z: the next phase (§V27: Phase 2 may end before its cap once three settings are in; a Z in
         * Phase 3 ends the session). The hold is gbp_session's 250 ms, latched once per hold. */
        if (session.end_requested && z_can_act) {
            /* counted only when it ended a phase: a hold re-latched under the running mute, between a
             * phase's end and the next one's begin, is a no-op in the module (review before the commit) */
            const uint8_t phase0 = sync.phase;
            const uint8_t ended0 = sync.phase <= GBP_ASYNC_P3 ? sync.ph[sync.phase].ended : 0u;
            gbp_async_skip(&sync, now);
            if (sync.phase != phase0 || (sync.phase <= GBP_ASYNC_P3 && sync.ph[sync.phase].ended != ended0)) sync_z_skips++;
            z_can_act = 0;
        }
        if (!(PAD_ButtonsHeld(PAD_CHAN0) & PAD_BUTTON_Z)) { z_can_act = 1; session.end_requested = 0; }
        gbp_async_second_counters(&sync, now, ap.underruns, adec.overflow);
        /* the module makes a plan only once the executor has landed the last one: its mute ends at the plan's
         * instant + mute chunks, the executor's at the first audible hand-off, up to one period later -- a phase
         * ended inside a mute (Z, a cap, the 18th answer) otherwise began the next plan over the running one and
         * lost its record (review round 3). The caps, the rows and `finished` still advance (second_counters) */
        r = trans.active ? 0 : gbp_async_tick(&sync, now);
        if (r & GBP_ASYNC_TICK_DEPTH_DONE) {
            if (sync_dwell_done(now)) sync_apply_plan(now);
        } else if (r & GBP_ASYNC_TICK_PLAN) {
            sync_apply_plan(now);
        }
        sync_control(now);
        if (gbp_async_finished(&sync)) live_end = 1;
    } else if (session.end_requested) {
        live_end = 1;                                 /* before the origin: Z ends the session, as game-0002 */
    } else if (!sync_started && live.phase == GBP_ALIVE_PROMPT && live.t_accept &&
               now >= live.t_accept + (uint64_t)live.tb_hz * SYNC_PROMPT_BOUND_S) {
        /* no A within the bound: the run ends here, with the whole 720 s still under the safety wall
         * for a press that comes in time (the wait for A was unbounded before) */
        sync_prompt_expired = 1;
        live_end = 1;
    }
    if (live.phase == GBP_ALIVE_WINDOW || (sync_started && !sync.finished && live.phase == GBP_ALIVE_DONE)) {
        /* one produce site and one flush-then-queue site: the executor, while a plan runs, hands back
         * the READY top-up chunk it produced under silence (gbp_atrans_step's *to_queue) */
        if (trans.active) { if (gbp_atrans_step(&trans, &ap, &adec, now, &b)) sync_trans_done(); }
        else b = gbp_aplay_produce(&ap, &adec);
        if (b >= 0) {
            /* the CPU wrote the chunk; the AI DMA reads memory: flush, then queue */
            DCFlushRange(ap_pool + (size_t)b * GBP_APLAY_CHUNK_BYTES, GBP_APLAY_CHUNK_BYTES);
            gbp_aplay_queue(&ap, b);
        }
        gbp_aplay_process(&ap);
        if (!ai_started && adec.count >= ap.target && gbp_aplay_ready(&ap) >= 2u) {
            const uint8_t *first;
            ai_started = 1;
            t_ai_start = now;
            ap.playing = 1u;
            first = gbp_aplay_irq_handoff(&ap, now);   /* not a callback: M starts at the first one */
            ap.measuring = 1u;
            AUDIO_InitDMA((u32)(size_t)first, GBP_APLAY_CHUNK_BYTES);
            AUDIO_StartDMA();
        }
    } else if (ai_started && !ai_stopped && (live_end || (sync_started && sync.finished))) {
        AUDIO_StopDMA();
        ap.measuring = 0u;
        ap.playing = 0u;
        ai_stopped = 1;
        t_ai_stop = now;
        gbp_aplay_process(&ap);
    }
    live_screen(now);
}
/* THE CONSUMER SLICE. Called once per service cycle, after the RE-ARM, under
 * the cause-pending yield; a bounded amount of work, then it returns. It never
 * blocks, never waits for the GP or the VI, and never touches the device. */
static void pump(void *user)
{
    uint32_t t0, t1, row, n;
    (void)user;

    /* Issue #19: the input step, FIRST in the slot. Nothing below it changed. */
    input_step();
    /* Issue #39: the session end, right after it, from the same sample. */
    session_step();
    /* Issue #92: the chain's slot half -- the press record, the chain, the AI, the screen */
    live_step();

    /* A READY buffer whose submit was refused because a token was still pending
     * gets another chance here, before any new work is started. */
    offer_oldest_ready();

    if (!conv.active) {
        int buf;
        buf = gbp_vpresent_acquire(&present);
        if (buf < 0) return;          /* counted inside as acquire_no_free_texture */
        if (!gbp_vqueue_take(&vq, &conv.desc)) {
            (void)gbp_vpresent_abandon(&present, buf);   /* give the buffer straight back */
            return;
        }
        conv.buf = (uint8_t)buf;
        conv.next_row = 0u;
        conv.ticks = 0u;
        conv.active = 1u;
        memset(&conv.stats, 0, sizeof conv.stats);
        /* the take ordinal: what orders the offers (never 0 for a source frame;
         * a wrap would need 2^32 takes, 2.3 years at 60 Hz) */
        tex_seq[buf] = ++take_seq;
        tex_frame[buf] = conv.desc.frame_index;
        tex_t_take[buf] = gettime();
        tex_t_done[buf] = 0u;
    }

    t0 = (uint32_t)gettick();
    for (n = 0; n < PLAY_SLICE_TILE_ROWS && conv.next_row < GBP_VPIX_BLOCKS; n++) {
        const uint8_t *blk;
        row = conv.next_row;
        blk = gbp_vstate_ring_block(pump_state, conv.desc.slot, row);
        if (!blk) {
            /* unreachable for a published descriptor (the ring's own bounds
             * check); rejected HERE if it ever happens (§V5.26 F5) */
            (void)gbp_vpresent_abandon(&present, (int)conv.buf);
            tex_seq[conv.buf] = 0u;
            conv.active = 0u;
            conv_abandoned_no_raw++;
            return;
        }
        (void)gbp_vpix_block(blk, row, tex_buf[conv.buf],
                             GBP_VPIX_TEX_BYTES / 2u, &conv.stats);
        conv.next_row++;
    }
    t1 = (uint32_t)gettick();
    {
        const uint32_t d = t1 - t0;
        conv.ticks += d;
        gbp_vqueue_pump_slice(&vq, d, conv.next_row >= GBP_VPIX_BLOCKS);
    }

    if (conv.next_row < GBP_VPIX_BLOCKS) return;      /* more slices to come */

    /* The frame is converted. Steps 3 and 4 of the generation guard (§V5.7):
     * only now do we ask whether the producer reused the slot underneath us. */
    if (!gbp_vqueue_commit(&vq, gbp_vqueue_still_valid(&vq, &conv.desc), conv.ticks)) {
        /* Consumer overrun: the half-and-half image is discarded WHOLE and the
         * screen keeps the previous frame; two generations never mix. */
        (void)gbp_vpresent_abandon(&present, (int)conv.buf);
        tex_seq[conv.buf] = 0u;
        conv.active = 0u;
        return;
    }

    flag15_last_count = conv.stats.flag15_count;
    if (conv.stats.flag15_coords) {
        flag15_last_x = conv.stats.flag15_x[0];
        flag15_last_y = conv.stats.flag15_y[0];
    }

    /* Cache coherency, in the one order that is correct: the CPU has finished
     * writing, so flush EXACTLY this buffer, and only then may the GP be told. */
    DCFlushRange(tex_buf[conv.buf], GBP_VPIX_TEX_BYTES);
    tex_t_done[conv.buf] = gettime();
    (void)gbp_vpresent_fill_done(&present, (int)conv.buf);   /* CPU_FILLING -> READY */
    conv.active = 0u;
    /* NOT submit_ready(conv.buf): if an older frame is still deferred, this one
     * must wait behind it. The offer is by age, never by slot. */
    offer_oldest_ready();
}

/* Hand a READY texture to the GP and put the result on screen -- or decline,
 * without waiting for anything. POLICY A (§V5.49), unchanged from stream-0015:
 * the framebuffer question first, one token in flight, the GX call ORDER
 * (draw, arm the token, copy) is the ownership argument. What is gone is the
 * disposition trace's bookkeeping around each decision; not one decision, not
 * one call, not one order changed. */
static void submit_ready(int buf, struct gbp_vqueue *account)
{
    int xfb, cur;
    uint64_t t_dec;

    cur = xfb_current_index();
    t_dec = gettime();
    xfb = gbp_vpresent_xfb_target(&present, cur);
    if (xfb < 0) {
        /* DEFER. Non-terminal: no counter of loss moves, no token is consumed,
         * and the texture is left READY for the next offer. */
        if (!account) selftest_repeats++;
        return;
    }

    /* ONE token in flight. A refusal here is normal back-pressure: the buffer
     * stays READY and is offered again on the next slice boundary. */
    if (!gbp_vpresent_submit(&present, buf)) return;

    GX_InvalidateTexAll();
    GX_InitTexObj(&tex_obj, tex_buf[buf], GBP_VPIX_WIDTH, GBP_VPIX_HEIGHT,
                  GX_TF_RGB5A3, GX_CLAMP, GX_CLAMP, GX_FALSE);
    GX_InitTexObjFilterMode(&tex_obj, GX_NEAR, GX_NEAR);   /* no filtering: Phase 9 */
    GX_LoadTexObj(&tex_obj, GX_TEXMAP0);
    draw_quad();
    GX_SetDrawDone();                 /* NON-blocking: on_draw_done() releases it */

    GX_CopyDisp(xfb_stream_buf[xfb], GX_TRUE);
    GX_Flush();
    /* Issue #92, as drain-0001: the VI stays on the text console for the whole run,
     * so the prompt can be read. The two hand-over register writes are the ONLY
     * thing gone; the frame is still converted, drawn and copied. */
    /* GAME 2 (Issue #110, §V25.7 2(c), (r5)): play-0001's two hand-over writes return, but only
     * from the press until C's window closes: he must see the game to play it and to judge it. */
    /* §V27: and on through gbp_alive's 64 s window end, until the session's own end, as the audio
     * path does (live_tap, live_step): the picture he judges the sound against must stay live. */
    if (live.phase == GBP_ALIVE_DELAY || live.phase == GBP_ALIVE_WINDOW ||
        (sync_started && !sync.finished && live.phase == GBP_ALIVE_DONE)) {
        VIDEO_SetNextFramebuffer(xfb_stream_buf[xfb]);
        VIDEO_Flush();                    /* register write only; NEVER VIDEO_WaitVSync here */
    }
    gbp_vpresent_xfb_handed(&present, xfb);
    /* R1: only a frame that came OUT of the queue goes back INTO its counters.
     * The self-test passes NULL and is counted separately. */
    if (account) {
        gbp_vqueue_note_presented(account);
        if (!first_real.have) {
            first_real.have = 1;
            first_real.frame_index = tex_frame[buf];
            first_real.t_take = tex_t_take[buf];
            first_real.t_convert_done = tex_t_done[buf];
            first_real.t_decision = t_dec;
        }
    } else {
        selftest_presents++;
    }
    tex_seq[buf] = 0u;                /* the frame is handed off; the slot is free to be re-keyed */
}

/* THE ORDERING GUARANTEE (§V5.49 I2): the OLDEST READY texture is offered
 * first, oldest by take ordinal, which is assigned in take order. */
static void offer_oldest_ready(void)
{
    uint32_t i;
    int best = -1;
    uint32_t best_seq = 0u;
    for (i = 0; i < GBP_VPRESENT_TEX_BUFFERS; i++) {
        if (present.tex[i] != GBP_VPRESENT_READY) continue;
        if (best < 0 || (tex_seq[i] != 0u && (best_seq == 0u || tex_seq[i] < best_seq))) {
            best = (int)i;
            best_seq = tex_seq[i];
        }
    }
    if (best >= 0) submit_ready(best, &vq);
}

/* ---- Issue #92: the figures ON SCREEN, last, so they are what the Operator reads
 * when the run ends -- and so an SD failure does not waste the run (CLAUDE.md §13).
 * Figures, never verdicts: those are tools/v22accept.py's. */
/* the schedule's PROGRESS, figure-free: counts that are the same whatever the levels (§V27.9 O6) */
static const char *sync_progress_text(void)
{
    static char buf[160];
    snprintf(buf, sizeof buf, "phase %u ended; %lu of %lu switches answered, %lu settings, %lu depths, %lu plans, "
             "%lu C-stick events (%lu acted), %lu Z skips, raw window %lu blocks",
             (unsigned)sync.phase, (unsigned long)sync.answered, (unsigned long)sync.switches,
             (unsigned long)sync.settings_n, (unsigned long)sync.depths_n, (unsigned long)sync_plans,
             (unsigned long)sync_cs_events, (unsigned long)sync_cs_acted, (unsigned long)sync_z_skips,
             (unsigned long)awr.blocks_stored);
    return buf;
}

static const char *sync_progress_kv(void)
{
    static char buf[200];
    snprintf(buf, sizeof buf, "phase=%u switches=%lu answered=%lu settings=%lu depths=%lu plans=%lu cs=%lu acted=%lu "
             "z=%lu awr=%lu finished=%u cs_dead=%lu",
             (unsigned)sync.phase, (unsigned long)sync.switches, (unsigned long)sync.answered,
             (unsigned long)sync.settings_n, (unsigned long)sync.depths_n, (unsigned long)sync_plans,
             (unsigned long)sync_cs_events, (unsigned long)sync_cs_acted, (unsigned long)sync_z_skips,
             (unsigned long)awr.blocks_stored, (unsigned)sync.finished, (unsigned long)cs_ignored_dead);
    return buf;
}

static int awr_sink(void *ctx, const uint8_t *data, uint32_t len)
{
    return sdlog_stream_write((struct sdlog_stream *)ctx, data, len);
}

/* the raw window's sidecar: OGBPAWR1 streamed straight from the store (§V27.11); the status says why not */
static size_t sync_save_awr(int *open_rc, int *write_rc, int *close_rc, char *status, size_t status_cap)
{
    struct sdlog_stream st;
    uint64_t written = 0u;
    long r;
    if (awr.blocks_stored == 0u) return 0u;
    *open_rc = sdlog_stream_open(&st, TEST_ID, OPENGBP_BUILD_ID, "-awr.bin", status, status_cap);
    if (*open_rc != 0) return 0u;
    r = gbp_awr_stream(&awr, awr_sink, &st, &written);
    *write_rc = r < 0 ? (int)r : 0;
    *close_rc = sdlog_stream_close(&st, status, status_cap);
    return (size_t)written;
}

static void live_screen_report(const struct gbp_vstate_result *res)
{
    /* §V27.9 O6 (widened) and §V27.10: NOTHING here is derived from the arm, the target, the fill,
     * the corrections or his answers -- no figure, no score, no phase label that differs between
     * the arms. The counts below are the schedule's own progress, identical whatever the levels. */
    printf("\n  == sync: HARDWARE %s stop=%s restore=%s\n", res->status_name,
           gbp_vstate_stop_name(res->stop), res->restore_ok ? "ok" : "ERROR");
    printf("  RUN     origin phase %s; A presses %lu, other presses %lu (inside), %lu after\n",
           gbp_alive_phase_name(live.phase), (unsigned long)live.presses_a, (unsigned long)live.presses_other,
           (unsigned long)live.presses_after);
    printf("  SYNC    %s. Every figure is on the SD log; the verdicts are tools/v27accept.py's.\n", sync_progress_text());
}
/* §V5.52 STARTUP TIMESTAMPS: plain 64-bit reads at points main() passes through. */
static uint64_t t_video_ready, t_selftest_begin, t_selftest_end, t_probe_enter;

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
    char ident_text[OPENGBP_IDENT_MAX];
    const struct opengbp_ident ident = { OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT };
    const struct gbp_initirqa_result *a;
    uint32_t tb_hz = (uint32_t)TB_TIMER_CLOCK * 1000u;
    size_t i;
    int saved = 0;
    const uint64_t t_program = gettime();

    gbp_startup_profile(&startup, GBP_STARTUP_MODE);

    video_setup();
    t_video_ready = gettime();
    gx_setup();
    PAD_Init();
    gecko_present = usb_isgeckoalive(GECKO_CHANNEL);
    opengbp_ident_format(ident_text, sizeof ident_text, &ident);

    printf("\n  Open-GBP " TEST_ID "  PHASE 6's ACCEPTANCE, SECOND ATTEMPT (HARDWARE_TESTS V26; NOT PHYSICALLY VALIDATED)\n");
    printf("  Build : %s   Commit: %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("  libogc: %s   Gecko: %s\n", _V_STRING, gecko_present ? "yes" : "no");
    printf("  %s\n\n", opengbp_ident_marker);

    snprintf(line, sizeof line, "OPENGBP-LIVE READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    gbp_vstate_config_default(&cfg);
    gbp_vstate_config_timebase(&cfg, tb_hz);
    /* Issue #19: the default policy and THE descriptor; the base comes later, from the probe */
    gbp_input_init(&in_state, &GBP_INPUT_POLICY_DEFAULT, &GBP_KEYPAD_DESCRIPTOR, tb_hz);
    gbp_vstate_init(&vstate, frame_store, (uint32_t)(sizeof frame_store / sizeof frame_store[0]),
                    event_store, (uint32_t)(sizeof event_store / sizeof event_store[0]),
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw,
                    audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&vstate, diag_store, GBP_VSTATE_MAX_DISAGREEMENTS);
    cfg.st = &vstate;

    gbp_vqueue_init(&vq, gbp_vstate_ring_slots(&vstate));
    gbp_vpresent_init(&present);
    {
        unsigned k;
        for (k = 0; k < PLAY_TEX_BUFFERS; k++) { tex_seq[k] = 0u; tex_frame[k] = 0u; tex_t_take[k] = 0u; tex_t_done[k] = 0u; }
    }
    pump_state = &vstate;
    vq.pump = pump;
    vq.pump_user = 0;
    cfg.stream = &vq;
    /* Issue #39: NO witness. cfg.witness stays NULL (gbp_vstate_config_default
     * zeroes it): the witness step never runs inside the service transaction,
     * the two witness stops do not exist, and no store is bound. */
    /* Issue #39: THE SESSION END. The hold on the transport's 64-bit clock; the
     * flag installed once; read by CHECK_ADMISSION, written by the pump slot. */
    session_hold_ticks = ((uint64_t)tb_hz * PLAY_SESSION_END_HOLD_MS) / 1000u;
    gbp_session_init(&session, session_hold_ticks);
    /* Issue #92: the window's end OR Z -- the pump folds Z in -- and ONE hook, the
     * tap. cfg.audio_len_live stays NULL: every AUDIO read is a whole 0x1000
     * (§V22.0; QUESTION A found no lever there). */
    cfg.session_end = &live_end;
    gbp_alive_init(&live, tb_hz);
    /* GAME 1 (§V25.7 2(a), (r1)): the origin is the A press + 1.000 s; no positive control runs */
    gbp_alive_use_press_origin(&live, GAME_ORIGIN_DELAY_MS);
    gbp_aperiod_reset(&live_per, GBP_ALIVE_PERIOD);
    gbp_adec_init(&adec, adec_ring, GBP_APLAY_RING);
    gbp_aplay_init(&ap, ap_pool, ap_silence, NULL, NULL);       /* §V27.1: no L2 keep, no store */
    gbp_async_init(&sync, NULL);
    gbp_atrans_init(&trans);                                 /* §V27's defaults, frozen (gbp_async_cfg_default) */
    (void)gbp_awr_init(&awr, awr_store, SYNC_AWR_BLOCKS, tb_hz);
    DCFlushRange(ap_silence, sizeof ap_silence);
    cfg.audio_tap = live_tap;
    cfg.audio_tap_user = 0;

    t_selftest_begin = gettime();
    display_selftest();
    t_selftest_end = gettime();
    snprintf(line, sizeof line,
             "OPENGBP-LIVE SELFTEST ok=%d converted=%d released=%d submits=%lu drawdone=%lu releases=%lu xfb=%lu sci_clean=%d inv_fail=%lu\n",
             selftest_ok, selftest_converted, selftest_released,
             (unsigned long)present.submit_success, (unsigned long)present.drawdone_callbacks,
             (unsigned long)present.texture_releases, (unsigned long)selftest_presents,
             selftest_sci_clean, (unsigned long)gbp_vpresent_invariant_failures(&present));
    gecko_puts(line);
    printf("  SELF-TEST display path: %s (converted=%d, texture released by the GP=%d)\n",
           selftest_ok ? "ok" : "NOT OK", selftest_converted, selftest_released);
    printf("  SELF-TEST accounting: %lu present / %lu repeat of its OWN, scientific counters %s\n",
           (unsigned long)selftest_presents, (unsigned long)selftest_repeats,
           selftest_sci_clean ? "CLEAN" : "CONTAMINATED");
    in_selftest_ok = gbp_input_selftest();
    snprintf(line, sizeof line,
             "OPENGBP-LIVE INPUTSELFTEST ok=%d refresh_ms=%u stick_threshold=%d layout=gbi-u16-replicated device_touched=0\n",
             in_selftest_ok, (unsigned)GBP_INPUT_REFRESH_MS, (int)GBP_INPUT_POLICY_DEFAULT.stick_threshold);
    gecko_puts(line);
    printf("  SELF-TEST input path: %s (pure: descriptor, encode/decode identity, default policy; no device access)\n",
           in_selftest_ok ? "ok" : "NOT OK");

    cfg.prehandler_wait_ms = startup.prehandler_wait_ms;
    cfg.hard_wallclock_s = PLAY_SAFETY_SECONDS;
    cfg.hard_wallclock_ticks = (uint64_t)tb_hz * PLAY_SAFETY_SECONDS;
    cfg.max_deliveries = PLAY_MAX_DELIVERIES;
    /* §V5.59 (F5): the generic time target is NOT a stop condition of a game
     * session either -- the session end is the only success. Installed after
     * gbp_vstate_config_timebase() above, as the header requires. */
    gbp_vstate_config_disable_time_target(&cfg);
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
    /* Issue #39: the session's bounds and the stop precedence of THIS image, as data */
    ringlog_printf(&rl, "ENVPLAY time_target=disabled safety_s=%lu max_deliveries=%lu session_end=Z hold_ms=%lu hold_ticks=%llu "
                        "precedence=fatal,safety,stores,session_end,no_next_cause,delivery witness=none",
                   (unsigned long)PLAY_SAFETY_SECONDS, (unsigned long)PLAY_MAX_DELIVERIES,
                   (unsigned long)PLAY_SESSION_END_HOLD_MS, (unsigned long long)session_hold_ticks);
    ringlog_printf(&rl, "ENVSTREAM time_target=disabled safety_s=%lu slice_tile_rows=%u tex_buffers=%u tex_bytes=%u ring_slots=%lu",
                   (unsigned long)PLAY_SAFETY_SECONDS,
                   (unsigned)PLAY_SLICE_TILE_ROWS, (unsigned)PLAY_TEX_BUFFERS,
                   (unsigned)GBP_VPIX_TEX_BYTES, (unsigned long)gbp_vstate_ring_slots(&vstate));
    ringlog_printf(&rl, "ENVINPUT port=1 policy=default stick_threshold=%d trigger_threshold=%u analog_ab_threshold=%u filter_opposites=%u refresh_ms=%u refresh_ticks=%llu layout=gbi-u16-replicated",
                   (int)GBP_INPUT_POLICY_DEFAULT.stick_threshold, (unsigned)GBP_INPUT_POLICY_DEFAULT.trigger_threshold,
                   (unsigned)GBP_INPUT_POLICY_DEFAULT.analog_ab_threshold, (unsigned)GBP_INPUT_POLICY_DEFAULT.filter_opposites,
                   (unsigned)GBP_INPUT_REFRESH_MS, (unsigned long long)in_state.refresh_ticks);
    ringlog_printf(&rl, "ENVINPUT2 index=%u desc=%u,%u,%u,%u,%u,%u,%u,%u,%u,%u pressed_is_one=%u desc_status=FACT_hw_run_scoped selftest=%d",
                   (unsigned)GBP_KEYPAD_INDEX,
                   (unsigned)GBP_KEYPAD_DESCRIPTOR.bit[0], (unsigned)GBP_KEYPAD_DESCRIPTOR.bit[1], (unsigned)GBP_KEYPAD_DESCRIPTOR.bit[2],
                   (unsigned)GBP_KEYPAD_DESCRIPTOR.bit[3], (unsigned)GBP_KEYPAD_DESCRIPTOR.bit[4], (unsigned)GBP_KEYPAD_DESCRIPTOR.bit[5],
                   (unsigned)GBP_KEYPAD_DESCRIPTOR.bit[6], (unsigned)GBP_KEYPAD_DESCRIPTOR.bit[7], (unsigned)GBP_KEYPAD_DESCRIPTOR.bit[8],
                   (unsigned)GBP_KEYPAD_DESCRIPTOR.bit[9], (unsigned)GBP_KEYPAD_DESCRIPTOR.pressed_is_one, in_selftest_ok);
    /* THE STORES AS CONFIGURED, beside what the contract requires, and with the
     * first unmet field by name (§V5.29.6). Here two of them are LARGER. */
    {
        const char *fault = gbp_vstate_storage_fault(&vstate);
        ringlog_printf(&rl, "ENVSTORE frames=%lu/%lu events=%lu/%lu raw_ring=%lu/%lu slots=%lu/%lu episode_raw=%lu/%lu audio_raw=%lu/%lu configured_bytes=%llu required_bytes=%llu fault=%s ok=%d",
                       (unsigned long)vstate.frames_cap, (unsigned long)GBP_VSTATE_MAX_FRAMES,
                       (unsigned long)vstate.events_cap, (unsigned long)GBP_VSTATE_MAX_EVENTS,
                       (unsigned long)vstate.raw_ring_cap, (unsigned long)GBP_VSTATE_RAW_RING_BYTES,
                       (unsigned long)vstate.raw_ring_slots, (unsigned long)GBP_VSTATE_RAW_RING_SLOTS_MIN,
                       (unsigned long)vstate.episode_raw_cap, (unsigned long)GBP_VSTATE_EPISODE_RAW_BYTES,
                       (unsigned long)vstate.audio_raw_cap, (unsigned long)GBP_VSTATE_AUDIO_RAW_BYTES,
                       (unsigned long long)gbp_vstate_configured_bytes(&vstate),
                       (unsigned long long)gbp_vstate_required_capacity_bytes(),
                       fault ? fault : "-", gbp_vstate_storage_ok(&vstate));
        if (fault) {
            printf("\n  FATAL: the state model's storage contract is not met: field=%s\n", fault);
            printf("  configured %llu B, required %llu B. The probe was NOT entered.\n",
                   (unsigned long long)gbp_vstate_configured_bytes(&vstate),
                   (unsigned long long)gbp_vstate_required_capacity_bytes());
            gecko_puts("OPENGBP-LIVE STORAGE FATAL field=");
            gecko_puts(fault);
            gecko_puts("\n");
        }
    }
    ringlog_printf(&rl, "ENVBUF frames=%08lx events=%08lx raw_ring=%08lx episode_raw=%08lx audio_raw=%08lx texA=%08lx texB=%08lx fifo=%08lx log_lines=%u",
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(frame_store), (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(event_store),
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(raw_ring), (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(episode_raw),
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(audio_raw),
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(tex_buf[0]), (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(tex_buf[1]),
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(gx_fifo), (unsigned)LOG_LINES);
    /* §V5.39.11: the memory audit, MEASURED at run time. What the enlarged
     * stores and the ringlog cost, and the arena that survives them, in the
     * log AND on the gecko so a Dolphin run reports it too. */
    {
        extern char __bss_end[];
        uint32_t lo = (uint32_t)(size_t)SYS_GetArena1Lo();
        uint32_t hi = (uint32_t)(size_t)SYS_GetArena1Hi();
        ringlog_printf(&rl, "ENVMEM bss_end=%08lx arena1_lo=%08lx arena1_hi=%08lx arena1_free=%lu "
                            "frames_bytes=%lu events_bytes=%lu log_bytes=%lu witness=0 xfb=3x%lu",
                       (unsigned long)(size_t)__bss_end, (unsigned long)lo, (unsigned long)hi,
                       (unsigned long)(hi > lo ? hi - lo : 0u),
                       (unsigned long)sizeof frame_store, (unsigned long)sizeof event_store,
                       (unsigned long)sizeof log_storage, (unsigned long)VIDEO_GetFrameBufferSize(rmode));
        snprintf(line, sizeof line,
                 "OPENGBP-LIVE ENVMEM frames=%lu events=%lu log_lines=%u frames_bytes=%lu events_bytes=%lu log_bytes=%lu "
                 "bss_end=%08lx arena1_lo=%08lx arena1_hi=%08lx arena1_free=%lu\n",
                 (unsigned long)PLAY_FRAME_RECORDS, (unsigned long)PLAY_EVENT_RECORDS, (unsigned)LOG_LINES,
                 (unsigned long)sizeof frame_store, (unsigned long)sizeof event_store, (unsigned long)sizeof log_storage,
                 (unsigned long)(size_t)__bss_end, (unsigned long)lo, (unsigned long)hi,
                 (unsigned long)(hi > lo ? hi - lo : 0u));
        gecko_puts(line);
    }

    /* Issue #92: the card is NOT touched here, nor during the run (§V22.0, D2). Every
     * LIVE record is kept under the ringlog's 248 characters even with every number
     * at its type's maximum (tests/host/test_live_image.py). */
    ringlog_printf(&rl, "LIVECFG accept_s=%u control_bound_s=%u control_blocks=%u control_min_periods=%u period=%u "
                        "calib_from_s=%u calib_blocks=%u window_s=%u safety_s=%u",
                   (unsigned)GBP_ALIVE_ACCEPT_S, (unsigned)GBP_ALIVE_CONTROL_BOUND_S, (unsigned)GBP_ALIVE_CONTROL_BLOCKS,
                   (unsigned)GBP_ALIVE_CONTROL_MIN, (unsigned)GBP_ALIVE_PERIOD, (unsigned)GBP_ALIVE_CALIB_FROM_S,
                   (unsigned)GBP_ALIVE_CALIB_BLOCKS, (unsigned)GBP_ALIVE_WINDOW_S, (unsigned)PLAY_SAFETY_SECONDS);
    ringlog_printf(&rl, "LIVECFG2 ring=%u target=%u band=%u chunk_frames=%u chunk_bytes=%u pool=%u ahead=%u l2=never "
                        "ai_hz=32000",
                   (unsigned)GBP_APLAY_RING, (unsigned)GBP_APLAY_TARGET, (unsigned)GBP_APLAY_BAND,
                   (unsigned)GBP_APLAY_FRAMES, (unsigned)GBP_APLAY_CHUNK_BYTES, (unsigned)GBP_APLAY_POOL,
                   (unsigned)GBP_APLAY_AHEAD);
    /* GAME 4 (§V25.7 2(a), 2(c)): the origin and the screen, as configured */
    ringlog_printf(&rl, "LIVEGAME origin=press delay_ms=%u control=none picture=press_to_window_end clip_counter=1 "
                        "cal_spread=1 video_location=frame_store",
                   (unsigned)GAME_ORIGIN_DELAY_MS);
    /* §V27: the session's configuration, as gbp_async holds it (the frozen seconds' realisation in samples) */
    /* Two records: one line would be 257 characters with these values, and the ringlog cuts at 248. */
    ringlog_printf(&rl, "SYNCCFG deep=%lu shallow=%lu floor=%lu mute=%lu step_mute=%lu p2_lo=%lu p2_hi=%lu p2_step=%lu "
                        "p3_start=%lu p3_step=%lu p3_dwell_s=%lu p3_bisect=%lu",
                   (unsigned long)sync.cfg.deep, (unsigned long)sync.cfg.shallow, (unsigned long)sync.cfg.floor,
                   (unsigned long)sync.cfg.mute_chunks, (unsigned long)sync.cfg.step_mute_chunks,
                   (unsigned long)sync.cfg.p2_lo, (unsigned long)sync.cfg.p2_hi, (unsigned long)sync.cfg.p2_step,
                   (unsigned long)sync.cfg.p3_start, (unsigned long)sync.cfg.p3_step, (unsigned long)sync.cfg.p3_dwell_s,
                   (unsigned long)sync.cfg.p3_bisect_width);
    ringlog_printf(&rl, "SYNCCFG2 p3_min=%lu cap_p1=%lu cap_p2=%lu cap_p3=%lu cap_session=%lu real=%lu null=%lu settling_s=%lu "
                        "awr_blocks=%u cfg_faults=%lu",
                   (unsigned long)sync.cfg.p3_min, (unsigned long)sync.cfg.cap_p1_s, (unsigned long)sync.cfg.cap_p2_s, (unsigned long)sync.cfg.cap_p3_s,
                   (unsigned long)sync.cfg.cap_session_s, (unsigned long)sync.cfg.real, (unsigned long)sync.cfg.null,
                   (unsigned long)sync.cfg.settling_s, (unsigned)SYNC_AWR_BLOCKS, (unsigned long)sync.cfg_faults);
    ringlog_printf(&rl, "SYNCCFG3 p3_confirm_s=%lu prompt_bound_s=%u",
                   (unsigned long)sync.cfg.p3_confirm_s, (unsigned)SYNC_PROMPT_BOUND_S);
    /* the AI, at its native 32 kHz, with its callback; it is STARTED from the pump slot, not here */
    AUDIO_Init(NULL);
    AUDIO_SetDSPSampleRate(AI_SAMPLERATE_32KHZ);
    AUDIO_RegisterDMACallback(live_dma_cb);

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);
    hsp_backend_irq_transport_ext(&hsp, &t);

    printf("  Sequence: the vstate-0004 service path VERBATIM -- 003A, one-shot handler, READ -> AUDIO\n");
    printf("            -> VIDEO -> ACK -> PI clean -> signature + assembly -> IRQ := 0000 -> next cause.\n");
    printf("  Screen:   after the RE-ARM, ONE bounded conversion slice (%u tile row); a converted frame only.\n",
           (unsigned)PLAY_SLICE_TILE_ROWS);
    printf("  Input:    pad 1 -> KEYPAD (index 0xC) in the same slot: written on change and every %u ms.\n",
           (unsigned)GBP_INPUT_REFRESH_MS);
    printf("  Session:  HOLD Z for %lu ms to END THE SESSION (the only success). Safety cap %lu s (never a success).\n",
           (unsigned long)PLAY_SESSION_END_HOLD_MS, (unsigned long)PLAY_SAFETY_SECONDS);
    printf("  Stores:   %lu frame records (%lu s at 60 Hz), %lu event records, log %u lines.\n\n",
           (unsigned long)PLAY_FRAME_RECORDS, (unsigned long)(PLAY_FRAME_RECORDS / 60u),
           (unsigned long)PLAY_EVENT_RECORDS, (unsigned)LOG_LINES);
    if (!gbp_transport_has_bulk_read(&t) || !gbp_transport_has_irq_reset(&t) || !gbp_transport_has_time64(&t)) {
        printf("\n  FATAL: the transport lacks the whole-block read, the record reset or the 64-bit time base.\n");
        printf("  Nothing was run. START = exit\n");
        for (;;) { VIDEO_WaitVSync(); PAD_ScanPads(); if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break; }
        exit(1);
    }
    /* Issue #84: the console STAYS on screen. It is cleared once, here, before
     * the service, so nothing written during the run can make it scroll (a
     * scroll copies the whole framebuffer: a stall of our own making). */
    printf("\x1b[2J\x1b[1;0H");
    printf("  Open-GBP " TEST_ID "  %s  %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    /* GAME 3 (§V25.7 2(d), (r6)): the console before the press says what the run needs */
    printf("  Cartridge: a GBA game the Operator knows. Link Port: nothing. BBA: absent.\n");
    printf("  WAIT for the prompt below (about 5 s). Then press A within 45 s: the game appears.\n");
    printf("  C-stick DOWN = switch. After each: LEFT = lags less, RIGHT = lags more, UP = the same.\n");
    printf("  Phase 2: LEFT/RIGHT step, UP confirm. Hold Z 1/4 s = next phase. X only at the end.\n");

    pump_res = &res;
    in_transport = &t;                       /* Issue #19: the slot writes through the probe's transport */
    keylog_rl = &rl;                         /* Issue #27: and records its non-refresh writes in the ringlog */
    t_probe_enter = gettime();
    gbp_vstate_probe_run(&t, &rl, &cfg, &res);     /* returns only after the teardown */
    a = &res.a;

    /* ---- display shutdown, in the one order that is safe (§V5.26 F6) ---- */
    gbp_vpresent_shutdown(&present);
    cfg.stream = 0;                     /* no further publish can reach the queue */
    vq.pump = 0;                        /* and no further slice can be pumped     */
    in_transport = 0;                   /* Issue #19: and no further KEYPAD write   */
    keylog_rl = 0;                      /* Issue #27: and no further KEY line       */
    if (gbp_vpresent_inflight(&present)) {
        GX_DrawDone();                  /* BLOCKING, and deliberately so: the GBP is already down */
        gx_drained_at_teardown = 1;
    }
    GX_SetDrawDoneCallback(gx_prev_drawdone_cb);
    gx_callback_restored = 1;

    /* Issue #92: the AI stops here if the window did not close it (Z, a stop, the
     * safety bound), and its callback is released before anything else runs. */
    if (ai_started && !ai_stopped) {
        AUDIO_StopDMA();
        ap.measuring = 0u;
        ap.playing = 0u;
        ai_stopped = 1;
        t_ai_stop = gettime();
    }
    AUDIO_RegisterDMACallback(NULL);
    gbp_aplay_process(&ap);
    gbp_awr_finish(&awr);                    /* §V27.11: a capture cut short says so in its own header */

    /* Back to the console for the report: the framebuffers never fight. */
    VIDEO_SetNextFramebuffer(xfb_text);
    VIDEO_Flush();
    VIDEO_WaitVSync();

    ringlog_printf(&rl, "STATS transfers=%lu timeouts=%lu busy=%lu bulk_transfers=%lu bulk_bytes=%lu",
                   (unsigned long)hsp.transfers, (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals,
                   (unsigned long)hsp.bulk_transfers, (unsigned long)hsp.bulk_bytes);
    ringlog_printf(&rl, "STREAMSRC closed=%lu complete=%lu incomplete=%lu quarantined=%lu anomaly=%lu published=%lu",
                   (unsigned long)vq.source_frames_closed, (unsigned long)vq.source_frames_complete,
                   (unsigned long)vq.source_frames_incomplete, (unsigned long)vq.source_frames_quarantined,
                   (unsigned long)vq.source_frames_anomaly, (unsigned long)vq.frames_published);
    ringlog_printf(&rl, "STREAMCONS taken=%lu converted=%lu presented=%lu overrun=%lu dropped_before_convert=%lu repeats=%lu no_cpu_texture=%lu abandoned_no_raw=%lu balanced=%d",
                   (unsigned long)vq.consumer_frames_taken, (unsigned long)vq.consumer_frames_converted,
                   (unsigned long)vq.consumer_frames_presented, (unsigned long)vq.consumer_slot_overrun,
                   (unsigned long)vq.dropped_before_convert, (unsigned long)vq.display_frames_repeated,
                   (unsigned long)present.acquire_no_free_texture, (unsigned long)conv_abandoned_no_raw,
                   gbp_vqueue_balanced(&vq));
    ringlog_printf(&rl, "STREAMDISP converted=%lu presented=%lu overrun=%lu repeated=%lu undispositioned=%lu identity=converted==presented+overrun+repeated(+residual<=%u)",
                   (unsigned long)vq.consumer_frames_converted,
                   (unsigned long)vq.consumer_frames_presented,
                   (unsigned long)vq.consumer_slot_overrun,
                   (unsigned long)vq.display_frames_repeated,
                   (unsigned long)gbp_vqueue_undispositioned(&vq),
                   (unsigned)GBP_VQUEUE_MAX_UNDISPOSITIONED);
    ringlog_printf(&rl, "STREAMPUMP calls=%lu slices=%lu completed=%lu skipped_cause_pending=%lu pending_before=%lu pending_after=%lu arrived_during=%lu",
                   (unsigned long)vq.pump_calls, (unsigned long)vq.pump_slices_started,
                   (unsigned long)vq.pump_slices_completed, (unsigned long)vq.pump_skipped_cause_pending,
                   (unsigned long)vq.cause_pending_before_pump, (unsigned long)vq.cause_pending_after_pump,
                   (unsigned long)vq.cause_arrived_during_pump);
    ringlog_printf(&rl, "STREAMPUMPT ticks_min=%lu ticks_max=%lu ticks_mean=%lu n=%lu tile_rows_per_slice=%u",
                   (unsigned long)(vq.pump_ticks_n ? vq.pump_ticks_min : 0u), (unsigned long)vq.pump_ticks_max,
                   (unsigned long)gbp_vqueue_pump_ticks_mean(&vq), (unsigned long)vq.pump_ticks_n,
                   (unsigned)PLAY_SLICE_TILE_ROWS);
    ringlog_printf(&rl, "INPUT selftest=%d steps=%lu invalid=%lu no_base=%lu key_changes=%lu attempts=%lu completed=%lu failed=%lu first=%lu change=%lu refresh=%lu retry=%lu last_word=%04x last_rc=%s",
                   in_selftest_ok, (unsigned long)in_state.steps, (unsigned long)in_state.samples_invalid,
                   (unsigned long)in_state.skipped_no_base, (unsigned long)in_state.keys_changes,
                   (unsigned long)in_state.attempts, (unsigned long)in_state.writes_completed,
                   (unsigned long)in_state.writes_failed, (unsigned long)in_state.writes_first,
                   (unsigned long)in_state.writes_change, (unsigned long)in_state.writes_refresh,
                   (unsigned long)in_state.writes_retry, (unsigned)in_state.word_written,
                   in_state.attempts ? gbp_status_name(in_state.last_rc) : "-");
    ringlog_printf(&rl, "INPUTT write_ticks=%lu/%lu/%lu n=%lu step_ticks=%lu/%lu/%lu n=%lu units=min/mean/max",
                   (unsigned long)(in_state.write_ticks_n ? in_state.write_ticks_min : 0u),
                   (unsigned long)gbp_input_write_ticks_mean(&in_state), (unsigned long)in_state.write_ticks_max,
                   (unsigned long)in_state.write_ticks_n,
                   (unsigned long)(in_state.step_ticks_n ? in_state.step_ticks_min : 0u),
                   (unsigned long)gbp_input_step_ticks_mean(&in_state), (unsigned long)in_state.step_ticks_max,
                   (unsigned long)in_state.step_ticks_n);
    ringlog_printf(&rl, "KEYLOG events=%lu emitted=%lu lost=%lu truncated=%lu overwritten=%lu reserve=%u emit_ticks=%lu/%lu/%lu n=%lu units=min/mean/max",
                   (unsigned long)in_state.events_recorded, (unsigned long)keylog_emitted, (unsigned long)keylog_lost,
                   (unsigned long)keylog_truncated, (unsigned long)in_state.events_overwritten, (unsigned)KEYLOG_TAIL_RESERVE,
                   (unsigned long)(keylog_ticks_n ? keylog_ticks_min : 0u),
                   (unsigned long)(keylog_ticks_n ? (uint32_t)(keylog_ticks_sum / keylog_ticks_n) : 0u),
                   (unsigned long)keylog_ticks_max, (unsigned long)keylog_ticks_n);
    /* Issue #39: how the session ended, as data */
    ringlog_printf(&rl, "SESSION end=Z hold_ms=%lu hold_ticks=%llu requested=%d t_hold_begin=%llx t_requested=%llx samples=%lu held=%lu holds=%lu released=%lu after=%lu stop=%s teardown=%s",
                   (unsigned long)PLAY_SESSION_END_HOLD_MS, (unsigned long long)session_hold_ticks,
                   session.end_requested, (unsigned long long)session.t_hold_begin, (unsigned long long)session.t_requested,
                   (unsigned long)session.samples, (unsigned long)session.samples_held, (unsigned long)session.holds_begun,
                   (unsigned long)session.holds_released, (unsigned long)session.samples_after,
                   gbp_vstate_stop_name(res.stop), res.teardown_variant ? res.teardown_variant : "-");
    ringlog_printf(&rl, "STREAMOWN acquire=%lu no_texture=%lu fills=%lu/%lu abandoned=%lu submit=%lu/%lu blocked_inflight=%lu blocked_shutdown=%lu",
                   (unsigned long)present.acquire_attempts, (unsigned long)present.acquire_no_free_texture,
                   (unsigned long)present.fills_completed, (unsigned long)present.fills_started,
                   (unsigned long)present.fills_abandoned, (unsigned long)present.submit_success,
                   (unsigned long)present.submit_attempts, (unsigned long)present.submit_blocked_inflight,
                   (unsigned long)present.submit_blocked_shutdown);
    ringlog_printf(&rl, "STREAMGX drawdone=%lu spurious=%lu releases=%lu xfb_presents=%lu xfb_skipped=%lu consistent_at_end=%d inflight_at_end=%d drained=%d cb_restored=%d",
                   (unsigned long)present.drawdone_callbacks, (unsigned long)present.drawdone_spurious,
                   (unsigned long)present.texture_releases, (unsigned long)present.xfb_presents,
                   (unsigned long)present.xfb_skipped_busy, gbp_vpresent_consistent(&present),
                   gbp_vpresent_inflight(&present), gx_drained_at_teardown, gx_callback_restored);
    ringlog_printf(&rl, "STREAMINV checks=%lu failures=%lu main=%lu/%lu isr=%lu/%lu consistent_at_end=%d",
                   (unsigned long)gbp_vpresent_invariant_checks(&present),
                   (unsigned long)gbp_vpresent_invariant_failures(&present),
                   (unsigned long)present.invariant_failures, (unsigned long)present.invariant_checks,
                   (unsigned long)present.invariant_failures_isr, (unsigned long)present.invariant_checks_isr,
                   gbp_vpresent_consistent(&present));
    ringlog_printf(&rl, "STREAMSELFTEST ok=%d converted=%d released=%d own_presents=%lu own_repeats=%lu sci_clean=%d note=synthetic_frame_before_capture_no_device_counters_isolated",
                   selftest_ok, selftest_converted, selftest_released,
                   (unsigned long)selftest_presents, (unsigned long)selftest_repeats,
                   selftest_sci_clean);
    ringlog_printf(&rl, "STARTUP mode=%s selftest_run=%d selftest_visible=%d "
                        "prehandler_wait_ms=%lu clear_fb=%d normal_clean=%d "
                        "presented_synthetic=%lu headless_submits=%lu",
                   gbp_startup_mode_name(&startup), startup.selftest_run,
                   startup.selftest_visible, (unsigned long)startup.prehandler_wait_ms,
                   startup.clear_framebuffers, gbp_startup_is_normal_clean(&startup),
                   (unsigned long)selftest_presents, (unsigned long)selftest_headless);
    ringlog_printf(&rl, "STARTUPT tb_hz=%lu t_program=%llx t_video=%llx "
                        "t_selftest_begin=%llx t_selftest_end=%llx t_probe_enter=%llx "
                        "t_control=%llx t_capture_start=%llx",
                   (unsigned long)tb_hz, (unsigned long long)t_program,
                   (unsigned long long)t_video_ready,
                   (unsigned long long)t_selftest_begin,
                   (unsigned long long)t_selftest_end,
                   (unsigned long long)t_probe_enter,
                   (unsigned long long)res.t_control_transform,
                   (unsigned long long)res.t_capture_start);
    {
        /* ONE tag, ONE shape, always emitted; `have_first` is what a parser
         * tests before reading the rest. The instants come from this file's
         * own per-texture bookkeeping, not from a trace. */
        const uint64_t c = res.t_control_transform;
        const uint64_t t_ho = first_real.have ? first_real.t_decision : 0u;
        ringlog_printf(&rl, "STARTUPV have_first=%d first_frame_index=%lu t_take=%llx "
                            "t_convert_done=%llx t_decision=%llx "
                            "ticks_control_to_first_handoff=%llu",
                       first_real.have,
                       (unsigned long)(first_real.have ? first_real.frame_index : 0u),
                       (unsigned long long)(first_real.have ? first_real.t_take : 0u),
                       (unsigned long long)(first_real.have ? first_real.t_convert_done : 0u),
                       (unsigned long long)t_ho,
                       (unsigned long long)((first_real.have && t_ho > c) ? t_ho - c : 0u));
    }
    ringlog_printf(&rl, "STREAMPACE publish_min=%lu publish_max=%lu publish_mean=%lu n=%lu convert_min=%lu convert_max=%lu convert_mean=%lu n=%lu",
                   (unsigned long)(vq.publish_interval_n ? vq.publish_interval_min : 0u),
                   (unsigned long)vq.publish_interval_max, (unsigned long)gbp_vqueue_publish_interval_mean(&vq),
                   (unsigned long)vq.publish_interval_n,
                   (unsigned long)(vq.convert_ticks_n ? vq.convert_ticks_min : 0u),
                   (unsigned long)vq.convert_ticks_max, (unsigned long)gbp_vqueue_convert_ticks_mean(&vq),
                   (unsigned long)vq.convert_ticks_n);
    ringlog_printf(&rl, "STREAMFLAG15 last_count=%lu first_x=%lu first_y=%lu note=reported_not_interpreted",
                   (unsigned long)flag15_last_count, (unsigned long)flag15_last_x, (unsigned long)flag15_last_y);

    /* ---- Issue #92: the run's records. tools/v22report.py reads these and nothing
     * else; the verdicts are tools/v22accept.py's. ---- */
    {
        uint32_t k;
        char buf[200];
        ringlog_printf(&rl, "LIVE phase=%s control_ok=%u gave_up=%u early=%lu windows=%lu press_before_prompt=%u "
                            "presses_a=%lu presses_other=%lu presses_after=%lu",
                       gbp_alive_phase_name(live.phase), (unsigned)live.control_ok, (unsigned)live.control_gave_up,
                       (unsigned long)live.control_early, (unsigned long)live.control_windows,
                       (unsigned)live.press_before_prompt, (unsigned long)live.presses_a,
                       (unsigned long)live.presses_other, (unsigned long)live.presses_after);
        ringlog_printf(&rl, "LIVECTL periods=%lu pmin=%lu pmax=%lu blocks=%lu calib_blocks=%lu rest_n=%lu",
                       (unsigned long)live.control_periods, (unsigned long)live.control_pmin,
                       (unsigned long)live.control_pmax, (unsigned long)live.control_blocks,
                       (unsigned long)live.calib_blocks, (unsigned long)adec.rest_n);
        /* GAME 4 (§V25.7 2(b), (r3)): the calibration span's spread -- reported, never used */
        ringlog_printf(&rl, "LIVECAL rest_sum=%llu rest_n=%lu pmin=%lu pmax=%lu",
                       (unsigned long long)adec.rest_sum, (unsigned long)adec.rest_n,
                       (unsigned long)adec.rest_min, (unsigned long)adec.rest_max);
        ringlog_printf(&rl, "LIVET tb_hz=%lu t0=%llx t_accept=%llx t_press=%llx t_origin=%llx t_end=%llx",
                       (unsigned long)live.tb_hz, (unsigned long long)live.t0, (unsigned long long)live.t_accept,
                       (unsigned long long)live.t_press, (unsigned long long)live.t_origin,
                       (unsigned long long)live.t_end);
        ringlog_printf(&rl, "LIVET2 t_ai_start=%llx t_ai_stop=%llx t_last_block=%llx gap_max=%llu gap_at=%llx",
                       (unsigned long long)t_ai_start, (unsigned long long)t_ai_stop,
                       (unsigned long long)live_last_t, (unsigned long long)live_gap_max,
                       (unsigned long long)live_gap_at);
        ringlog_printf(&rl, "LIVEN blocks_in=%llu window_blocks=%llu taps=%lu taps_failed=%lu wrong_len=%lu secs_used=%lu "
                            "sec_overflow=%lu",
                       (unsigned long long)live.blocks_in, (unsigned long long)live.window_blocks,
                       (unsigned long)live_taps, (unsigned long)live_taps_failed, (unsigned long)live_wrong_len,
                       (unsigned long)live.secs_used, (unsigned long)live.sec_overflow);
        for (k = 0u; k < live.secs_used && k < GBP_ALIVE_MAX_SECONDS; k += LIVE_SEC_PER_LINE) {
            uint32_t j2;
            size_t o = 0u;
            buf[0] = '\0';
            for (j2 = k; j2 < k + LIVE_SEC_PER_LINE && j2 < live.secs_used && o < sizeof buf; j2++)
                o += (size_t)snprintf(buf + o, sizeof buf - o, "%s%lu", j2 == k ? "" : ",", (unsigned long)live.sec[j2]);
            ringlog_printf(&rl, "LIVESEC from=%lu counts=%s", (unsigned long)k, buf);
        }
        for (k = 0u; k < live.secs_used && k < GBP_ALIVE_MAX_SECONDS; k += LIVE_SEC_PER_LINE) {
            uint32_t j2;
            size_t o = 0u;
            buf[0] = '\0';
            for (j2 = k; j2 < k + LIVE_SEC_PER_LINE && j2 < live.secs_used && o < sizeof buf; j2++)
                o += (size_t)snprintf(buf + o, sizeof buf - o, "%s%lu", j2 == k ? "" : ",", (unsigned long)live.fill[j2]);
            ringlog_printf(&rl, "LIVEFILL from=%lu fill=%s", (unsigned long)k, buf);
        }
        ringlog_printf(&rl, "LIVEL periods=%lu pmin=%lu pmax=%lu off=%lu edges=%lu samples=%lu",
                       (unsigned long)live.l.periods, (unsigned long)live.l.pmin, (unsigned long)live.l.pmax,
                       (unsigned long)live.l.off, (unsigned long)live.l.edges, (unsigned long)live.l_samples);
        ringlog_printf(&rl, "LIVEC overflow=%lu lost=%lu underruns=%lu silences=%lu dup=%lu drop=%lu produced=%lu "
                            "handed=%lu starved=%lu log_overflow=%lu clipped=%lu",   /* GAME 4: (r4) */
                       (unsigned long)adec.overflow, (unsigned long)adec.lost, (unsigned long)ap.underruns,
                       (unsigned long)ap.silences, (unsigned long)ap.dup, (unsigned long)ap.drop,
                       (unsigned long)ap.produced, (unsigned long)ap.handed, (unsigned long)ap.starved_steps,
                       (unsigned long)ap.log_overflow, (unsigned long)adec.clipped);      /* GAME 4: (r4) */
        ringlog_printf(&rl, "LIVEM callbacks=%lu t_first=%llx t_last=%llx frames_per_callback=%u",
                       (unsigned long)ap.cb_count, (unsigned long long)ap.cb_t_first,
                       (unsigned long long)ap.cb_t_last, (unsigned)GBP_APLAY_FRAMES);
        /* ---- §V27: the session's records. tools/v27report.py reads these; the verdicts are
         * tools/v27accept.py's. Every one is SD-only: nothing here reaches the screen or the gecko. ---- */
        if (sync_started) {
            char sbuf[248];
            uint32_t j;
            /* the backstop: a depth still pending (a cap in the last pump-less cycle) is reported now */
            if (sync.p3_depth_pending) { (void)sync_dwell_done(sync_last_now); sync_p3_drained++; }
            ringlog_printf(&rl, "SYNCP3 pending=%u drained=%lu refused_depth_done=%lu depths=%lu overflow=%lu",
                           (unsigned)sync.p3_depth_pending, (unsigned long)sync_p3_drained,
                           (unsigned long)sync.refused_depth_done, (unsigned long)sync.depths_n,
                           (unsigned long)sync.depths_overflow);
            ringlog_printf(&rl, "SYNCSEED seed=%08lx initial=%s", (unsigned long)sync.seed,
                           gbp_async_level_name(sync.initial));
            {
                size_t o = 0u;
                sbuf[0] = '\0';
                for (j = 0u; j < sync.n_sched && j < GBP_ASYNC_SWITCH_CAP && o < sizeof sbuf - 2u; j++)
                    o += (size_t)snprintf(sbuf + o, sizeof sbuf - o, "%s%c", j ? "," : "",
                                          sync.schedule[j] == GBP_ASYNC_KIND_REAL ? 'R' : 'N');
                ringlog_printf(&rl, "SYNCSCHED n=%lu kinds=%s", (unsigned long)sync.n_sched, sbuf);
            }
            {
                char dbuf[64];
                size_t o = 0u, od = 0u;
                sbuf[0] = '\0'; dbuf[0] = '\0';
                for (j = 0u; j < sync.p2_seeded && j < GBP_ASYNC_P2_CAP && o < sizeof sbuf - 8u; j++) {
                    o += (size_t)snprintf(sbuf + o, sizeof sbuf - o, "%s%lu", j ? "," : "", (unsigned long)sync.p2_start[j]);
                    od += (size_t)snprintf(dbuf + od, sizeof dbuf - od, "%s%c", j ? "," : "",
                                           sync.p2_dir[j] == GBP_ASYNC_LEFT_DEEPER ? 'D' : 'S');
                }
                ringlog_printf(&rl, "SYNCP2CFG starts=%s dirs=%s", sbuf, dbuf);
            }
            for (j = 0u; j < sync.switches && j < GBP_ASYNC_SWITCH_CAP; j++) {
                const struct gbp_async_switch *w = &sync.sw[j];
                ringlog_printf(&rl, "SYNCSW seq=%lu kind=%s from=%lu to=%lu t=%llx discard=%lu pause=%lu", (unsigned long)j,
                               gbp_async_kind_name(w->kind), (unsigned long)w->from, (unsigned long)w->to,
                               (unsigned long long)w->t, (unsigned long)w->discard,
                               (unsigned long)(w->to > w->from ? (w->to - w->from + 127u) / 128u : 0u));
            }
            for (j = 0u; j < sync.switches && j < GBP_ASYNC_SWITCH_CAP; j++) {
                const struct gbp_async_switch *w = &sync.sw[j];
                if (w->answer != GBP_ASYNC_ANSWER_NONE)
                    ringlog_printf(&rl, "SYNCANS seq=%lu answer=%s t=%llx", (unsigned long)j,
                                   gbp_async_answer_name(w->answer), (unsigned long long)w->t_answer);
            }
            /* §V27.15: each switch's transition as the executor carried it out. Masked (by content) when it
             * ROTATEd, landed, and is not `unmasked` -- a shallowing with fewer than AHEAD fronts dropped; a late
             * rotation and a deepening or null with few rotations are contiguous (gbp_atrans.h) */
            for (j = 0u; j < sync.switches && j < GBP_ASYNC_SWITCH_CAP; j++) {
                const struct sync_tx *x = &sync_tx[j];
                ringlog_printf(&rl, "SYNCTX seq=%lu done=%u mech=%s mute=%lu rot=%lu res=%ld late=%u unmasked=%u topped=%lu",
                               (unsigned long)j, (unsigned)x->done,
                               x->mech == GBP_ATRANS_ROTATE ? "ROTATE" : x->mech == GBP_ATRANS_HELD ? "HELD" : "UNMUTED",
                               (unsigned long)x->mute, (unsigned long)x->rotations, (long)x->residue,
                               (unsigned)x->late, (unsigned)x->unmasked, (unsigned long)x->topped);
            }
            ringlog_printf(&rl, "SYNCTXA begun=%lu completed=%lu faults=%lu rotate=%lu lates=%lu unmasked=%lu res=%ld..%ld "
                                "converted=%lu shorts=%lu short_max=%lu trim_max=%lu trim_sum=%lu",
                           (unsigned long)trans.begun, (unsigned long)trans.completed, (unsigned long)trans.faults,
                           (unsigned long)trans.rotate_landings, (unsigned long)trans.lates, (unsigned long)trans.unmaskeds,
                           (long)trans.residue_min, (long)trans.residue_max, (unsigned long)trans.converted,
                           (unsigned long)trans.shorts, (unsigned long)trans.short_max, (unsigned long)trans.trim_max,
                           (unsigned long)trans.trim_sum);
            for (j = 0u; j < sync.settings_n && j < GBP_ASYNC_P2_CAP; j++) {
                const struct gbp_async_setting *x = &sync.settings[j];
                ringlog_printf(&rl, "SYNCSET seq=%lu start=%lu dir=%c steps=%lu target=%lu t=%llx", (unsigned long)j,
                               (unsigned long)x->start, x->direction == GBP_ASYNC_LEFT_DEEPER ? 'D' : 'S',
                               (unsigned long)x->steps, (unsigned long)x->target, (unsigned long long)x->t);
            }
            for (j = 0u; j < sync.depths_n && j < GBP_ASYNC_DEPTH_CAP; j++) {
                const struct gbp_async_depth *d = &sync.depths[j];
                ringlog_printf(&rl, "SYNCDEPTH n=%lu kind=%s target=%lu fill16=%lu underruns=%lu overflow=%lu dup=%lu drop=%lu "
                                    "lost=%lu starved=%lu t_start=%llx t_end=%llx partial=%u", (unsigned long)j,
                               gbp_async_depth_kind_name(d->kind), (unsigned long)d->target,
                               (unsigned long)d->fill_mean_x16, (unsigned long)d->underruns, (unsigned long)d->overflow,
                               (unsigned long)d->dup, (unsigned long)d->drop, (unsigned long)d->lost, (unsigned long)d->starved,
                               (unsigned long long)d->t_set, (unsigned long long)d->t_done, (unsigned)d->partial);
                ringlog_printf(&rl, "SYNCDEPTH2 n=%lu starved=%lu ready_in=%lu ready_out=%lu fill_in=%lu fill_out=%lu fill_n=%lu",
                               (unsigned long)j, (unsigned long)sync_dx[j].starved, (unsigned long)sync_dx[j].ready_in,
                               (unsigned long)sync_dx[j].ready_out, (unsigned long)sync_dx[j].fill_in,
                               (unsigned long)sync_dx[j].fill_out, (unsigned long)sync_dx[j].fill_n);
            }
            for (j = 1u; j <= 3u; j++) {
                const struct gbp_async_phase_rec *ph = &sync.ph[j];
                if (ph->started)
                    ringlog_printf(&rl, "SYNCPH phase=%lu t_start=%llx t_end=%llx ended=%s", (unsigned long)j,
                                   (unsigned long long)ph->t_start, (unsigned long long)ph->t_end,
                                   gbp_async_end_name(ph->ended));
            }
            {
                /* the eight per-second series, 16 a line, one value per whole second since the origin */
                static const char *tags[8] = { "SYNCSECC", "SYNCSECF", "SYNCSECT", "SYNCSECP", "SYNCSECM", "SYNCSECS",
                                               "SYNCSECU", "SYNCSECO" };
                static const char *names[8] = { "counts", "fill16", "target", "phase", "mute", "settling", "underruns",
                                                "overflow" };
                uint32_t f, k2;
                const uint32_t n = sync.secs_used < GBP_ASYNC_SECONDS ? sync.secs_used : GBP_ASYNC_SECONDS;
                for (f = 0u; f < 8u; f++) {
                    for (k2 = 0u; k2 < n; k2 += LIVE_SEC_PER_LINE) {
                        uint32_t j2;
                        size_t o = 0u;
                        sbuf[0] = '\0';
                        for (j2 = k2; j2 < k2 + LIVE_SEC_PER_LINE && j2 < n && o < sizeof sbuf - 12u; j2++) {
                            unsigned long v = 0u;
                            switch (f) {
                            case 0: v = sync.sec_count[j2]; break;
                            case 1: v = sync.sec_count[j2] ? (unsigned long)(((uint64_t)sync.sec_fill_sum[j2] * 16u) / sync.sec_count[j2]) : 0u; break;
                            case 2: v = sync.sec_target[j2]; break;
                            case 3: v = sync.sec_phase[j2]; break;
                            case 4: v = sync.sec_mute[j2]; break;
                            case 5: v = sync.sec_settling[j2]; break;
                            case 6: v = sync.sec_underruns[j2]; break;
                            default: v = sync.sec_overflow_ev[j2]; break;
                            }
                            o += (size_t)snprintf(sbuf + o, sizeof sbuf - o, "%s%lu", j2 == k2 ? "" : ",", v);
                        }
                        ringlog_printf(&rl, "%s from=%lu %s=%s", tags[f], (unsigned long)k2, names[f], sbuf);
                    }
                }
            }
            /* Three records (the ringlog cuts at 248 characters): the chain's counters, the decoder's and the
             * session's faults, the session's refusals -- every field named, every value at its type's maximum
             * still fits (tests/host/test_sync_image.py). */
            ringlog_printf(&rl, "SYNCC underruns=%lu overflow=%lu silences=%lu mute_handed=%lu dup=%lu drop=%lu produced=%lu "
                                "handed=%lu ring_gated=%lu",
                           (unsigned long)ap.underruns, (unsigned long)adec.overflow, (unsigned long)ap.silences,
                           (unsigned long)ap.mute_handed, (unsigned long)ap.dup, (unsigned long)ap.drop,
                           (unsigned long)ap.produced, (unsigned long)ap.handed, (unsigned long)ap.ring_gated);
            ringlog_printf(&rl, "SYNCC2 discarded=%lu starved_steps=%lu lost=%lu blocks_in=%lu ring_discarded=%lu counter_faults=%lu "
                                "sec_overflow=%lu lines_lost=%lu trans_faults=%lu dropped_front=%lu",
                           (unsigned long)ap.discarded_chunks, (unsigned long)ap.starved_steps, (unsigned long)adec.lost,
                           (unsigned long)adec.blocks_in, (unsigned long)adec.discarded, (unsigned long)sync.counter_faults,
                           (unsigned long)sync.sec_overflow, (unsigned long)sync_lines_lost, (unsigned long)trans.faults,
                           (unsigned long)ap.dropped_front);
            ringlog_printf(&rl, "SYNCREF switch_unanswered=%lu switch_mute=%lu switch_exhausted=%lu switch_phase=%lu answer=%lu "
                                "step_mute=%lu step_end=%lu step_phase=%lu step_value=%lu confirm=%lu",
                           (unsigned long)sync.refused_switch_unanswered, (unsigned long)sync.refused_switch_mute,
                           (unsigned long)sync.refused_switch_exhausted, (unsigned long)sync.refused_switch_phase,
                           (unsigned long)sync.refused_answer, (unsigned long)sync.refused_step_mute,
                           (unsigned long)sync.refused_step_end, (unsigned long)sync.refused_step_phase,
                           (unsigned long)sync.refused_step_value, (unsigned long)sync.refused_confirm);
            ringlog_printf(&rl, "SYNCAWR blocks=%lu cap=%lu t_arm=%llx t_first=%llx t_last=%llx faults=%lu ignored=%lu "
                                "seen=%lu state=%u",
                           (unsigned long)awr.blocks_stored, (unsigned long)awr.blocks_cap, (unsigned long long)awr.t_arm,
                           (unsigned long long)awr.t_first, (unsigned long long)awr.t_last, (unsigned long)awr.faults,
                           (unsigned long)awr.ignored, (unsigned long)awr.seen, (unsigned)awr.state);
            ringlog_printf(&rl, "SYNCAWRC copy_min=%lu copy_max=%lu copy_sum=%llu copy_n=%lu",
                           (unsigned long)awr.copy_min, (unsigned long)awr.copy_max, (unsigned long long)awr.copy_sum,
                           (unsigned long)awr.copy_n);
            ringlog_printf(&rl, "SYNCEND reason=%s t=%llx secs=%lu phase=%u plans=%lu cs=%lu acted=%lu z=%lu cs_dead=%lu "
                                "cs_busy=%lu preempts=%lu stop=%s",
                           sync.finished ? (res.stop == GBP_VSTATE_STOP_SESSION_END ? "session" : gbp_vstate_stop_name(res.stop))
                                         : "not_finished",
                           (unsigned long long)live_last_t, (unsigned long)(sync.secs_used < GBP_ASYNC_SECONDS ? sync.secs_used : GBP_ASYNC_SECONDS),
                           (unsigned)sync.phase, (unsigned long)sync_plans, (unsigned long)sync_cs_events,
                           (unsigned long)sync_cs_acted, (unsigned long)sync_z_skips, (unsigned long)cs_ignored_dead,
                           (unsigned long)sync_cs_busy, (unsigned long)sync_preempts, gbp_vstate_stop_name(res.stop));
        } else {
            ringlog_printf(&rl, "SYNCEND reason=%s t=%llx secs=0 phase=0 plans=0 cs=0 acted=0 z=0 cs_dead=%lu stop=%s",
                           sync_prompt_expired ? "prompt_expired" : "no_origin", (unsigned long long)live_last_t,
                           (unsigned long)cs_ignored_dead, gbp_vstate_stop_name(res.stop));
        }
        /* GAME 4 (§V25.7 4, (r7)): the frame store, walked HERE -- after the session, off the drain
         * path. An incomplete frame is a stored frame that is not COMPLETE_40, the predicate FRAMECAP
         * counts; it is INSIDE the AI span iff t_ai_start <= t_last_block <= t_ai_stop, and each
         * inside frame is counted in the 1.000 s of the span its t_last_block falls in. */
        {
            uint32_t f, nsec = 0u;
            for (k = 0u; k < GBP_ALIVE_MAX_SECONDS; k++) game_vsec[k] = 0u;
            for (f = 0u; f < vstate.frames_n; f++) {
                const struct gbp_vstate_frame *fr = &vstate.frames[f];
                if (fr->completeness == GBP_VSTATE_FRAME_COMPLETE_40) continue;
                game_v_stored++;
                if (!ai_started || fr->t_last_block < t_ai_start) {
                    game_v_before++;
                } else if (fr->t_last_block > t_ai_stop) {
                    game_v_after++;
                } else {
                    const uint64_t s = (fr->t_last_block - t_ai_start) / (uint64_t)tb_hz;
                    game_v_inside++;
                    if (s < (uint64_t)GBP_ALIVE_MAX_SECONDS) game_vsec[s]++; else game_v_sec_overflow++;
                }
            }
            if (ai_started && t_ai_stop > t_ai_start) {
                const uint64_t span = t_ai_stop - t_ai_start;
                const uint64_t n = (span + (uint64_t)tb_hz - 1u) / (uint64_t)tb_hz;
                nsec = n < (uint64_t)GBP_ALIVE_MAX_SECONDS ? (uint32_t)n : GBP_ALIVE_MAX_SECONDS;
            }
            ringlog_printf(&rl, "LIVEVINC ai=%d before=%lu inside=%lu after=%lu stored=%lu framecap=%lu store_full=%d "
                                "secs=%lu sec_overflow=%lu",
                           ai_started, (unsigned long)game_v_before, (unsigned long)game_v_inside,
                           (unsigned long)game_v_after, (unsigned long)game_v_stored,
                           (unsigned long)vstate.frames_incomplete, vstate.frame_store_full,
                           (unsigned long)nsec, (unsigned long)game_v_sec_overflow);
            for (k = 0u; k < nsec; k += LIVE_SEC_PER_LINE) {
                uint32_t j2;
                size_t o = 0u;
                buf[0] = '\0';
                for (j2 = k; j2 < k + LIVE_SEC_PER_LINE && j2 < nsec && o < sizeof buf; j2++)
                    o += (size_t)snprintf(buf + o, sizeof buf - o, "%s%lu", j2 == k ? "" : ",", (unsigned long)game_vsec[j2]);
                ringlog_printf(&rl, "LIVEVSEC from=%lu counts=%s", (unsigned long)k, buf);
            }
        }
        /* GAME 6 (Issue #113, §V26.7 1 & 2, (s2) (s5) (s6)): each before-AI incomplete frame, located. The
         * predicate is LIVEVINC's `before`; the next stored frame's t_first_block is what places the press
         * frame structurally (t_first_block <= t_press < next). After the session, off the drain path. */
        {
            uint32_t f, n_before = 0u, n_listed = 0u;
            for (f = 0u; f < vstate.frames_n; f++) {
                const struct gbp_vstate_frame *fr = &vstate.frames[f];
                if (fr->completeness == GBP_VSTATE_FRAME_COMPLETE_40) continue;
                if (ai_started && fr->t_last_block >= t_ai_start) continue;
                n_before++;
                if (n_listed >= GAME_BEFORE_LIST_CAP) continue;
                ringlog_printf(&rl, "LIVEVBEF i=%lu idx=%lu t_first=%llx t_last=%llx t_next=%llx",
                               (unsigned long)n_listed, (unsigned long)fr->index,
                               (unsigned long long)fr->t_first_block, (unsigned long long)fr->t_last_block,
                               (unsigned long long)(f + 1u < vstate.frames_n ? vstate.frames[f + 1u].t_first_block : 0u));
                n_listed++;
            }
            ringlog_printf(&rl, "LIVEVBEFN before=%lu listed=%lu capped=%d cap=%u", (unsigned long)n_before,
                           (unsigned long)n_listed, n_before > n_listed ? 1 : 0, (unsigned)GAME_BEFORE_LIST_CAP);
        }
    }

    gbp_vstate_summary(&res, summary, sizeof summary);

    printf("\n  HARDWARE status=%s (%s) reason=%s stop=%s restore=%s teardown=%s\n", res.status_name, res.status_class,
           res.reason ? res.reason : "-", gbp_vstate_stop_name(res.stop), res.restore_ok ? "ok" : "ERROR",
           res.teardown_variant ? res.teardown_variant : "-");
    printf("  SESSION %s: Z held %lu of %lu samples, %lu hold(s), %lu released before %lu ms; requested=%d\n",
           res.stop == GBP_VSTATE_STOP_SESSION_END ? "ENDED BY THE OPERATOR (success)" : "NOT ended by the operator",
           (unsigned long)session.samples_held, (unsigned long)session.samples, (unsigned long)session.holds_begun,
           (unsigned long)session.holds_released, (unsigned long)PLAY_SESSION_END_HOLD_MS, session.end_requested);
    printf("  SERVICE %s  deliveries=%lu  VIDEO %lu  AUDIO %lu (drained; played in C's window)  errors=%lu uncertain=%lu\n", /* GAME 5 */
           res.service_ok ? "ok" : "FAILED", (unsigned long)res.deliveries, (unsigned long)res.video_completed,
           (unsigned long)res.audio_drains, (unsigned long)res.errors, (unsigned long)res.uncertain_writes);
    printf("  SOURCE  closed=%lu complete=%lu incomplete=%lu quarantined=%lu anomaly=%lu -> published=%lu\n",
           (unsigned long)vq.source_frames_closed, (unsigned long)vq.source_frames_complete,
           (unsigned long)vq.source_frames_incomplete, (unsigned long)vq.source_frames_quarantined,
           (unsigned long)vq.source_frames_anomaly, (unsigned long)vq.frames_published);
    printf("  CONSUMER taken=%lu converted=%lu presented=%lu  overrun=%lu superseded=%lu repeats=%lu  counters %s\n",
           (unsigned long)vq.consumer_frames_taken, (unsigned long)vq.consumer_frames_converted,
           (unsigned long)vq.consumer_frames_presented, (unsigned long)vq.consumer_slot_overrun,
           (unsigned long)vq.dropped_before_convert, (unsigned long)vq.display_frames_repeated,
           gbp_vqueue_balanced(&vq) ? "BALANCE" : "DO NOT BALANCE");
    printf("  PUMP    %lu calls, %lu slices (%lu..%lu ticks, mean %lu); SKIPPED %lu because a cause was already latched\n",
           (unsigned long)vq.pump_calls, (unsigned long)vq.pump_slices_started,
           (unsigned long)(vq.pump_ticks_n ? vq.pump_ticks_min : 0u), (unsigned long)vq.pump_ticks_max,
           (unsigned long)gbp_vqueue_pump_ticks_mean(&vq), (unsigned long)vq.pump_skipped_cause_pending);
    printf("  INPUT   %lu steps, %lu writes (%lu first, %lu change, %lu refresh, %lu retry), %lu failed, last word %04x, self-test %s\n",
           (unsigned long)in_state.steps, (unsigned long)in_state.writes_completed, (unsigned long)in_state.writes_first,
           (unsigned long)in_state.writes_change, (unsigned long)in_state.writes_refresh, (unsigned long)in_state.writes_retry,
           (unsigned long)in_state.writes_failed, (unsigned)in_state.word_written, in_selftest_ok ? "ok" : "NOT OK");
    printf("  KEYLOG  %lu events (first/change/retry), %lu KEY lines emitted, %lu lost to the bound (reserve %u lines), %lu truncated\n",
           (unsigned long)in_state.events_recorded, (unsigned long)keylog_emitted, (unsigned long)keylog_lost,
           (unsigned)KEYLOG_TAIL_RESERVE, (unsigned long)keylog_truncated);
    printf("  GX      submit %lu/%lu (blocked in-flight %lu)  drawdone %lu (spurious %lu)  releases %lu  xfb %lu shown / %lu skipped\n",
           (unsigned long)present.submit_success, (unsigned long)present.submit_attempts,
           (unsigned long)present.submit_blocked_inflight, (unsigned long)present.drawdone_callbacks,
           (unsigned long)present.drawdone_spurious, (unsigned long)present.texture_releases,
           (unsigned long)present.xfb_presents, (unsigned long)present.xfb_skipped_busy);
    printf("  OWNER   at end %s   DURING the run %lu failure(s) in %lu checks   in flight %d   drained %d   cb restored %d\n",
           gbp_vpresent_consistent(&present) ? "HOLD" : "VIOLATED",
           (unsigned long)gbp_vpresent_invariant_failures(&present),
           (unsigned long)gbp_vpresent_invariant_checks(&present),
           gbp_vpresent_inflight(&present), gx_drained_at_teardown, gx_callback_restored);
    printf("  SELFTEST %s, its own presents %lu / repeats %lu, scientific counters %s\n",
           selftest_ok ? "ok" : "NOT OK", (unsigned long)selftest_presents,
           (unsigned long)selftest_repeats, selftest_sci_clean ? "CLEAN" : "CONTAMINATED");
    printf("  FLAG15  last frame carried %lu set word(s), first at (%lu,%lu) -- REPORTED, NOT INTERPRETED (U-GBP-034)\n",
           (unsigned long)flag15_last_count, (unsigned long)flag15_last_x, (unsigned long)flag15_last_y);
    printf("  RESTORE control=%d stop=%d cleanup=%d arinfo=%d handler=%d mask_ok=%d\n",
           a->control_restore_ok, a->irq_stop_write_ok, a->pi_cleanup_performed, a->arinfo_restore_ok,
           res.h.handler_restored, res.h.mask_ok);
    /* Issue #92: the run's figures, LAST, where the Operator reads them */
    live_screen_report(&res);

    snprintf(line, sizeof line,
             "OPENGBP-LIVE COUNTERS balanced=%d sci_clean_at_probe=%d inv_fail=%lu inv_checks=%lu consistent_at_end=%d storage_fault=%s\n",
             gbp_vqueue_balanced(&vq), selftest_sci_clean,
             (unsigned long)gbp_vpresent_invariant_failures(&present),
             (unsigned long)gbp_vpresent_invariant_checks(&present),
             gbp_vpresent_consistent(&present),
             gbp_vstate_storage_fault(&vstate) ? gbp_vstate_storage_fault(&vstate) : "-");
    gecko_puts(line);
    snprintf(line, sizeof line,
             "OPENGBP-LIVE INPUT selftest=%d steps=%lu attempts=%lu completed=%lu failed=%lu last_word=%04x events=%lu emitted=%lu lost=%lu\n",
             in_selftest_ok, (unsigned long)in_state.steps, (unsigned long)in_state.attempts,
             (unsigned long)in_state.writes_completed, (unsigned long)in_state.writes_failed,
             (unsigned)in_state.word_written, (unsigned long)in_state.events_recorded,
             (unsigned long)keylog_emitted, (unsigned long)keylog_lost);
    gecko_puts(line);
    snprintf(line, sizeof line,
             "OPENGBP-LIVE SESSION requested=%d samples=%lu held=%lu holds=%lu released=%lu hold_ms=%lu\n",
             session.end_requested, (unsigned long)session.samples, (unsigned long)session.samples_held,
             (unsigned long)session.holds_begun, (unsigned long)session.holds_released,
             (unsigned long)PLAY_SESSION_END_HOLD_MS);
    gecko_puts(line);
    snprintf(line, sizeof line,
             "OPENGBP-LIVE RESULT status=%s class=%s reason=%s stop=%s teardown=%s service=%d deliveries=%lu restore=%d\n",
             res.status_name, res.status_class, res.reason ? res.reason : "-", gbp_vstate_stop_name(res.stop),
             res.teardown_variant ? res.teardown_variant : "-", res.service_ok, (unsigned long)res.deliveries, res.restore_ok);
    gecko_puts(line);

    /* §V27.9 O6 (widened): the live channel carries the schedule's progress and NOTHING derived from
     * the arm, the target, the fill, the corrections or his answers. The Orchestrator reads this channel
     * while the Operator plays. */
    snprintf(line, sizeof line, "OPENGBP-LIVE SYNCEND %s\n", sync_progress_kv());
    gecko_puts(line);

    /* §V22.9 A3: X is read only HERE, after the session */
    printf("\n  X = save log and raw window to SD    START = exit    POWER CYCLE REQUIRED\n");
    for (;;) {
        VIDEO_WaitVSync();
        PAD_ScanPads();
        if (!saved && (PAD_ButtonsDown(0) & PAD_BUTTON_X)) {
            char path[128] = "";
            char extra[240];
            char awr_status[160] = "not written: nothing was captured";
            int rc, awr_open = 1, awr_write = 1, awr_close = 1;
            size_t n = 0u;
            /* The raw window FIRST, so the log can say whether it saved (§V27.11: the ride-along) */
            n = sync_save_awr(&awr_open, &awr_write, &awr_close, awr_status, sizeof awr_status);
            ringlog_printf(&rl, "SYNCAWRSAVE open=%d write=%d close=%d bytes=%lu status=%s", awr_open, awr_write,
                           awr_close, (unsigned long)n, awr_status);
            snprintf(line, sizeof line, "OPENGBP-LIVE AWRSAVE open=%d write=%d close=%d bytes=%lu\n", awr_open,
                     awr_write, awr_close, (unsigned long)n);
            gecko_puts(line);
            printf("  SAVE raw window  %s\n", awr_status);
            /* The log names what it is and what it is not: the one sidecar, and the
             * one success by name. */
            snprintf(extra, sizeof extra,
                     "libogc=%s gecko=%d power_cycle_required=%d sidecar=awr time_target=disabled safety_s=%lu "
                     "session_end=sync_or_Z hold_ms=%lu stop=%s status=%s witness=none",
                     _V_STRING, gecko_present, res.power_cycle_required,
                     (unsigned long)PLAY_SAFETY_SECONDS, (unsigned long)PLAY_SESSION_END_HOLD_MS,
                     gbp_vstate_stop_name(res.stop), res.status_name);
            rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl,
                            status, sizeof status, path, sizeof path);
            saved = (rc == 0);
            printf("  SAVE log     %s\n", status);
            snprintf(line, sizeof line, "OPENGBP-LIVE SAVELOG rc=%d path=%s\n", rc, path);
            gecko_puts(line);
        }
        if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break;
    }
    for (i = 0; i < 1; i++) gecko_puts("OPENGBP-LIVE DONE\n");
    return 0;
}
