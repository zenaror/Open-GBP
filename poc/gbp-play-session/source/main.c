/*
 * Open-GBP GBP-PLAY-001, build play-0001 — THE PLAYABLE RUNTIME IMAGE (GitHub
 * Issue #39). IMPLEMENTED AND HOST-VALIDATED; it has never touched hardware,
 * nothing here claims that a game plays, and no run is pre-registered for it.
 *
 * WHAT THIS IS. `stream-0015` (poc/gbp-video-stream-probe) minus its research
 * instrumentation, plus the one thing Issue #38 found missing: a SUCCESS STOP
 * the operator controls. Everything a game needs is the stream probe's, reused
 * with its BEHAVIOUR unchanged:
 *
 *   - the transport and the 003B extended one-shot handler (audited byte for
 *     byte against the physically validated GBP-VIDEO-001 build's);
 *   - the service path, `gbp_vstate_probe_run()`: the 003A stage, READ ->
 *     AUDIO -> VIDEO -> ACK -> PI clean -> signature + assembly -> RE-ARM ->
 *     next cause, with Policy R3, and the state model's stores the storage
 *     contract requires (HARDWARE_TESTS §V5.29: a LARGER set is honoured, a
 *     smaller one is refused at the first gate);
 *   - the presentation path: gbp_vqueue -> pump() (one tile row per slice,
 *     after the RE-ARM, under the cause-pending yield) -> gbp_vpix -> GX (one
 *     RGB5A3 quad) -> two stream framebuffers, with Policy A in submit_ready()
 *     (the framebuffer question first; one draw-done token in flight; the
 *     oldest READY texture offered first) and gbp_vpresent's ownership machine;
 *   - THE INPUT PATH AND THE KEY RECORD, BYTE-IDENTICAL: keylog_emit() and
 *     input_step() below are the text of stream-0015's, and tests/host/
 *     test_play_image.py diffs them against it; the descriptor and the policy
 *     are the src/gbp data the routing FACT of HARDWARE_TESTS §V7.4 was
 *     established with; the KEYPAD write is the same 32-byte write through the
 *     same transport, on change and every 5 ms, FIRST in the pump slot.
 *
 * WHAT IS OUT (Issue #38, INPUT_PATH.md §12.2; Issue #39): the OGBPIDX1
 * witness (never bound -- cfg.witness stays NULL, so the witness step never
 * runs inside the service transaction and the two witness stops do not exist),
 * the full-frame sampler, the VI latch trace, the disposition trace, and their
 * four sidecars. The witness MODULE is still linked, because the service-path
 * module references its predicates; no store exists for it, and main.o names
 * no gbp_vwitness_ symbol (the `play` audit profile proves both).
 *
 * WHAT IS NEW (Issue #39):
 *
 *   1. THE SESSION END. Z -- the one input the policy deliberately never sends
 *      to the AGB (INPUT.md §4) -- held for PLAY_SESSION_END_HOLD_MS raises a
 *      caller-owned flag from the pump slot (src/gbp/gbp_session, a pure state
 *      machine with no outward edge). CHECK_ADMISSION reads the flag once per
 *      admitted cycle, after the safety budget and the two store caps, and ends
 *      the run as `stop=session_end status=ok_session_ended
 *      teardown=S5_session_end`: a SUCCESS, the run's normal end, with the
 *      same teardown every other stop gets. The transaction in flight always
 *      completes whole; the cause stays latched for the teardown.
 *
 *   2. THE SIZING, for a session of PLAY_SAFETY_SECONDS: a frame store of
 *      PLAY_FRAME_RECORDS records (the contract's 16384 would end the run as
 *      `frame_store_cap` after 274 s), an event store of PLAY_EVENT_RECORDS,
 *      the delivery guard above the budget, and a ringlog whose KEY headroom
 *      and post-run reserve are sized for a long session. What each costs is
 *      in the ENVMEM record and in docs/research/INPUT_PATH.md §13.
 *
 * WHAT THIS DOES NOT CLAIM. The service pass is SHORTER than stream-0015's by
 * the witness step it no longer runs -- RUN 17 measured that step at
 * 5..1547 ticks, mean 70, per VIDEO block (STREAMWITT). That shape has
 * physical precedent (the pre-witness builds stream-0003 and stream-0004 ran
 * it, with this presentation path), but this image has not run, and its
 * first run is the measurement: the cycle records, the delivery rate and the
 * anomaly counters, read against RUN 17's. Nothing here says the timing is
 * fine.
 *
 * SD save on X -- the text log, and nothing else -- START to exit. Nothing is
 * read from the controller for the save before the probe has returned from its
 * teardown. Every run ends with "POWER CYCLE REQUIRED".
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

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-play-session"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
/* The image's embedded id. No run is pre-registered under it; a pre-registration
 * may rename it (one line, one rebuild, one new hash). */
#define TEST_ID "GBP-PLAY-001"

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
#define PLAY_SAFETY_SECONDS      720u
#define PLAY_MAX_DELIVERIES      6000000u
#define PLAY_FRAME_RECORDS       45056u
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
static struct gbp_vstate_frame frame_store[PLAY_FRAME_RECORDS];                    /* 45056 x 192 B = 8.25 MiB */
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
#define KEYLOG_TAIL_RESERVE 640u
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
_Static_assert(LOG_LINES - KEYLOG_TAIL_RESERVE >= 7000u, "the KEY headroom of a long session");

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
    VIDEO_SetNextFramebuffer(xfb_stream_buf[xfb]);
    VIDEO_Flush();                    /* register write only; NEVER VIDEO_WaitVSync here */
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

    printf("\n  Open-GBP " TEST_ID "  THE PLAYABLE IMAGE (NOT PHYSICALLY VALIDATED; no run pre-registered)\n");
    printf("  Build : %s   Commit: %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("  libogc: %s   Gecko: %s\n", _V_STRING, gecko_present ? "yes" : "no");
    printf("  %s\n\n", opengbp_ident_marker);

    snprintf(line, sizeof line, "OPENGBP-PLAY READY %s test=%s\n", ident_text, TEST_ID);
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
    cfg.session_end = &session.end_requested;

    t_selftest_begin = gettime();
    display_selftest();
    t_selftest_end = gettime();
    snprintf(line, sizeof line,
             "OPENGBP-PLAY SELFTEST ok=%d converted=%d released=%d submits=%lu drawdone=%lu releases=%lu xfb=%lu sci_clean=%d inv_fail=%lu\n",
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
             "OPENGBP-PLAY INPUTSELFTEST ok=%d refresh_ms=%u stick_threshold=%d layout=gbi-u16-replicated device_touched=0\n",
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
            gecko_puts("OPENGBP-PLAY STORAGE FATAL field=");
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
                 "OPENGBP-PLAY ENVMEM frames=%lu events=%lu log_lines=%u frames_bytes=%lu events_bytes=%lu log_bytes=%lu "
                 "bss_end=%08lx arena1_lo=%08lx arena1_hi=%08lx arena1_free=%lu\n",
                 (unsigned long)PLAY_FRAME_RECORDS, (unsigned long)PLAY_EVENT_RECORDS, (unsigned)LOG_LINES,
                 (unsigned long)sizeof frame_store, (unsigned long)sizeof event_store, (unsigned long)sizeof log_storage,
                 (unsigned long)(size_t)__bss_end, (unsigned long)lo, (unsigned long)hi,
                 (unsigned long)(hi > lo ? hi - lo : 0u));
        gecko_puts(line);
    }

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
    printf("  Running ...\n");

    /* The AGB image is what the operator should see while this runs. */
    VIDEO_SetNextFramebuffer(xfb_stream);
    VIDEO_Flush();

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

    gbp_vstate_summary(&res, summary, sizeof summary);

    printf("\n  HARDWARE status=%s (%s) reason=%s stop=%s restore=%s teardown=%s\n", res.status_name, res.status_class,
           res.reason ? res.reason : "-", gbp_vstate_stop_name(res.stop), res.restore_ok ? "ok" : "ERROR",
           res.teardown_variant ? res.teardown_variant : "-");
    printf("  SESSION %s: Z held %lu of %lu samples, %lu hold(s), %lu released before %lu ms; requested=%d\n",
           res.stop == GBP_VSTATE_STOP_SESSION_END ? "ENDED BY THE OPERATOR (success)" : "NOT ended by the operator",
           (unsigned long)session.samples_held, (unsigned long)session.samples, (unsigned long)session.holds_begun,
           (unsigned long)session.holds_released, (unsigned long)PLAY_SESSION_END_HOLD_MS, session.end_requested);
    printf("  SERVICE %s  deliveries=%lu  VIDEO %lu  AUDIO %lu (drained, NOT reproduced)  errors=%lu uncertain=%lu\n",
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
    printf("\n  stop=session_end IS THE ONLY SUCCESS. A session that ended any other way has gone wrong,\n");
    printf("  however well the game played. The verdict of a play session is the operator's report AND this log.\n");

    snprintf(line, sizeof line,
             "OPENGBP-PLAY COUNTERS balanced=%d sci_clean_at_probe=%d inv_fail=%lu inv_checks=%lu consistent_at_end=%d storage_fault=%s\n",
             gbp_vqueue_balanced(&vq), selftest_sci_clean,
             (unsigned long)gbp_vpresent_invariant_failures(&present),
             (unsigned long)gbp_vpresent_invariant_checks(&present),
             gbp_vpresent_consistent(&present),
             gbp_vstate_storage_fault(&vstate) ? gbp_vstate_storage_fault(&vstate) : "-");
    gecko_puts(line);
    snprintf(line, sizeof line,
             "OPENGBP-PLAY INPUT selftest=%d steps=%lu attempts=%lu completed=%lu failed=%lu last_word=%04x events=%lu emitted=%lu lost=%lu\n",
             in_selftest_ok, (unsigned long)in_state.steps, (unsigned long)in_state.attempts,
             (unsigned long)in_state.writes_completed, (unsigned long)in_state.writes_failed,
             (unsigned)in_state.word_written, (unsigned long)in_state.events_recorded,
             (unsigned long)keylog_emitted, (unsigned long)keylog_lost);
    gecko_puts(line);
    snprintf(line, sizeof line,
             "OPENGBP-PLAY SESSION requested=%d samples=%lu held=%lu holds=%lu released=%lu hold_ms=%lu\n",
             session.end_requested, (unsigned long)session.samples, (unsigned long)session.samples_held,
             (unsigned long)session.holds_begun, (unsigned long)session.holds_released,
             (unsigned long)PLAY_SESSION_END_HOLD_MS);
    gecko_puts(line);
    snprintf(line, sizeof line,
             "OPENGBP-PLAY RESULT status=%s class=%s reason=%s stop=%s teardown=%s service=%d deliveries=%lu restore=%d\n",
             res.status_name, res.status_class, res.reason ? res.reason : "-", gbp_vstate_stop_name(res.stop),
             res.teardown_variant ? res.teardown_variant : "-", res.service_ok, (unsigned long)res.deliveries, res.restore_ok);
    gecko_puts(line);

    printf("\n  X = save log to SD    START = exit    POWER CYCLE REQUIRED\n");
    for (;;) {
        VIDEO_WaitVSync();
        PAD_ScanPads();
        if (!saved && (PAD_ButtonsDown(0) & PAD_BUTTON_X)) {
            char path[128] = "";
            char extra[240];
            int rc;
            /* The log names what it is and what it is not: no sidecar, and the
             * one success by name. */
            snprintf(extra, sizeof extra,
                     "libogc=%s gecko=%d power_cycle_required=%d sidecar=none time_target=disabled safety_s=%lu "
                     "session_end=Z hold_ms=%lu stop=%s status=%s witness=none",
                     _V_STRING, gecko_present, res.power_cycle_required,
                     (unsigned long)PLAY_SAFETY_SECONDS, (unsigned long)PLAY_SESSION_END_HOLD_MS,
                     gbp_vstate_stop_name(res.stop), res.status_name);
            rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl,
                            status, sizeof status, path, sizeof path);
            saved = (rc == 0);
            printf("  SAVE log     %s\n", status);
            snprintf(line, sizeof line, "OPENGBP-PLAY SAVELOG rc=%d path=%s\n", rc, path);
            gecko_puts(line);
        }
        if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break;
    }
    for (i = 0; i < 1; i++) gecko_puts("OPENGBP-PLAY DONE\n");
    return 0;
}
