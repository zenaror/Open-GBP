/*
 * gbp-play-gba2 -- GitHub Issue #158: the GBA play image vehicle-0002 (TEST_ID GBP-PLAY-002, the same test as vehicle-0001; the build id discriminates).
 * A COPY of poc/gbp-play-gba (vehicle-0001, an executed image whose sources are frozen and which reproduces at its own commit) that ALSO writes, at
 * teardown, the startup profile and the Policy A invariants to its SD log (layer A of HARDWARE_TESTS.md V31.12's recommendation): STARTUP, STARTUPT,
 * STARTUPV, STREAMINV and STREAMSELFTEST, in the ten inline copies' format, through src/gbp/gbp_startrec (ONE block in main(), after the probe has
 * returned and the draw-done callback is restored, outside `if (sync_started)` so an aborted session writes them too). Nothing is added to the pump,
 * the tap, the DMA callback or the draw-done handler (tools/hotpath_cmp.py, the hot-path identity gate). Everything below is vehicle-0001's text.
 *
 * gbp-play-gba -- GitHub Issue #153 (the BUILD half; the design is HARDWARE_TESTS.md V31): Phase 7's E5 vehicle, the GBA PLAY image.
 * A physical GBA cartridge in the Game Boy Player, played normally for up to six minutes, with the native audio chain at ONE setting for the whole
 * session and a log that says what the session did. Not a research instrument: no phase of it asks the Operator to judge anything.
 *
 * WHERE IT COMES FROM. poc/gbp-audio-v28's chassis (video, vstate, vqueue, vpresent, GX, input, session, keylog, SD save/teardown, startup
 * profile, the tap and the pump), COPIED and not edited: poc/gbp-audio-v28 is an EXECUTED image whose sources are frozen and which reproduces at its
 * own commit. What is NOT here: the research handlers (3a, 3b, sweep, nulling, loss), the transition machine (gbp_atrans2), the marked DMA block and
 * the hand-off reads (gbp_v28_dma), the C-stick, and the GX label. What is here that V28 never had: a PLAY phase without a handler, the hand-off
 * ordinals of the first underruns (gbp_play_under, V31.3), a cartridge declaration made at the console after the session (gbp_cartdecl, V31.4) and
 * an ENVMEM record (V31.2).
 *
 * THE PLAN (src/audio/gbp_v28_plans.h, GBP_V28_PLAY_GBA; tools/v28budget.py "play_gba"): `navigate` is a timed phase of 60 s and `play` follows it by
 * itself for 300 s. Nothing the Operator presses moves from one to the other; the phases exist for the plan table and the store sizing. The session
 * ends at the Operator's Z (held a quarter of a second) or at the plan's cap (420 s, the wall 485 s).
 *
 * THE AUDIO. The chain is configured ONCE, in main(), by gbp_aplay2_set_target(T256 = 4096 samples) at AHEAD 1 (one chunk queued ahead of the DMA:
 * L = 121.0 ms as tabulated, label M1). The transition machine is NOT the cold-start route (V31.1). The library default in gbp_aplay2.h
 * (GBP_APLAY2_TARGET 8192) is untouched: this image passes an explicit value and records it (PLAYCFG). The production step is RUN 55-58's (64 pushes).
 * A COLD START at 4096 from an empty ring has never run before this image: the start-up is what PLAYSTARTUP / PLAYUND / PLAYUNDER time.
 *
 * WHAT THE LOG ADDS (SD only, printed at teardown, the record names of the V28 chassis kept where the readers apply): PLAYCFG, ENVMEM, PLAYSTARTUP,
 * PLAYUND (one per recorded underrun: its hand-off ordinal and the milliseconds since the DMA start), PLAYUNDER (start-up apart from after-start-up:
 * the fallback rule of Issue #142 reads `after_startup` and only that), and CARTDECL (the Operator's declaration, appended before the save).
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
#include "gbp_adec2.h"
#include "gbp_aresamp2.h"
#include "gbp_alive.h"
#include "gbp_aplay2.h"
#include "gbp_walker.h"
#include "gbp_v28_ladder.h"
#include "gbp_v28_plans.h"
#include "gbp_v28_step.h"
#include "gbp_play_under.h"
#include "gbp_cartdecl.h"
#include "gbp_startrec.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-play-gba2"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-PLAY-002"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT " OPENGBP_APP_NAME " " OPENGBP_BUILD_ID " " OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1

/* ---- the ringlog (Issue #39 sizing, unchanged discipline from sync-0001) -------------------- */
#define LOG_LINES 8192
#define LOG_LINE_LEN 256
#define DMA_TIMEOUT_MS 200
#define KEYLOG_TAIL_RESERVE 1280u

/* ---- the plan's own wall (tools/v28budget.py "play_gba": wall_s = session_cap_s + WALL_ABOVE_SESSION_S(65)), and the stores sized at its own guard
 * rates (HARDWARE_TESTS.md V31.2 table, the 300 s row): 485 s x 79 events, x 60 frames, x 39 chunk corrections. The stores are ALLOCATED, as static
 * arrays, and every one of them is smaller than RUN 57's (wall 533 s), the largest V28-chassis allocation that has booted and saved. */
#define PLAY_BOUND_S        GBP_V28_PLAY_BOUND_S               /* 300 */
#define V28_SESSION_CAP_S   GBP_V28_PLAY_GBA_CAP_S             /* 420 */
#define V28_WALL_S          485u
#define PLAY_EVENT_RECORDS  38315u
#define PLAY_FRAME_RECORDS  29100u
#define CORR_CAP            18915u
_Static_assert(V28_WALL_S == V28_SESSION_CAP_S + 65u, "the wall is the session cap plus 65 s (tools/v28budget.py WALL_ABOVE_SESSION_S)");
#define PLAY_SAFETY_SECONDS      V28_WALL_S
#define PLAY_MAX_DELIVERIES      6000000u
#define PLAY_SESSION_END_HOLD_MS 250u
#define PLAY_SLICE_TILE_ROWS     1u

_Static_assert(PLAY_FRAME_RECORDS >= (uint64_t)PLAY_SAFETY_SECONDS * 60u,
               "the frame store must outlast the wall at 60 frames per second (tools/v28budget.py)");
_Static_assert((uint64_t)PLAY_EVENT_RECORDS >= (uint64_t)PLAY_SAFETY_SECONDS * 79u,
               "the misc-events store must outlast the wall at the x1.2 guard rate (79/s)");
_Static_assert((uint64_t)CORR_CAP >= (uint64_t)PLAY_SAFETY_SECONDS * 39u,
               "the chunk_corrections store must outlast the wall at its own x1.2 guard rate (39/s), "
               "kept SEPARATE from the misc-events store (Issue #128 section 6's own trap)");
_Static_assert(PLAY_MAX_DELIVERIES >= (uint64_t)PLAY_SAFETY_SECONDS * 6314u,
               "the delivery guard must sit above the wall at RUN 17's delivery rate");

static char log_storage[LOG_LINES * LOG_LINE_LEN];
static uint8_t dma_buffer[GBP_BLOCK_SIZE] ATTRIBUTE_ALIGN(32);

/* ---- state model stores (GBP-VIDEO-002, unchanged shape from sync-0001, sized per plan above) */
static struct gbp_vstate_frame frame_store[PLAY_FRAME_RECORDS];
static struct gbp_vstate_event event_store[PLAY_EVENT_RECORDS];
static uint8_t raw_ring[GBP_VSTATE_RAW_RING_BYTES_4] ATTRIBUTE_ALIGN(32);
static uint8_t episode_raw[GBP_VSTATE_EPISODE_RAW_BYTES] ATTRIBUTE_ALIGN(32);
static uint8_t audio_raw[GBP_VSTATE_AUDIO_RAW_BYTES] ATTRIBUTE_ALIGN(32);

_Static_assert(sizeof frame_store / sizeof frame_store[0] >= GBP_VSTATE_MAX_FRAMES,
               "gbp_vstate requires at least GBP_VSTATE_MAX_FRAMES frame records");
_Static_assert(sizeof event_store / sizeof event_store[0] >= GBP_VSTATE_MAX_EVENTS,
               "gbp_vstate requires at least GBP_VSTATE_MAX_EVENTS event records");
_Static_assert(sizeof raw_ring >= GBP_VSTATE_RAW_RING_BYTES, "the raw ring must hold at least the minimum three slots");
_Static_assert(sizeof raw_ring % GBP_VSTATE_RAW_FRAME_BYTES == 0, "the raw ring must be a whole number of frame slots");
_Static_assert(sizeof episode_raw >= GBP_VSTATE_EPISODE_RAW_BYTES, "the episode raw store is NOT optional");
_Static_assert(sizeof audio_raw >= GBP_VSTATE_AUDIO_RAW_BYTES, "the AUDIO raw store must hold GBP_VSTATE_AUDIO_RAW_BYTES");

static struct gbp_vstate_cycle cyc_first[GBP_VSTATE_CYC_FIRST];
static struct gbp_vstate_cycle cyc_last[GBP_VSTATE_CYC_LAST];
static struct gbp_vstate_cycle cyc_anomaly[GBP_VSTATE_CYC_ANOMALY];
static struct gbp_vstate_cycle cyc_episode[GBP_VSTATE_CYC_EPISODE];
static struct gbp_vstate vstate;
static struct gbp_vstate_diag diag_store[GBP_VSTATE_MAX_DISAGREEMENTS];
static struct gbp_vqueue vq;
static const struct gbp_vstate_result *pump_res;

/* ---- texture buffers -- unchanged from sync-0001 (gbp_vpresent owns the ownership rule) ------ */
#define PLAY_TEX_BUFFERS GBP_VPRESENT_TEX_BUFFERS
static uint16_t tex_buf[PLAY_TEX_BUFFERS][GBP_VPIX_TEX_BYTES / 2u] ATTRIBUTE_ALIGN(32);
static struct gbp_vpresent present;
static GXTexObj tex_obj;
_Static_assert(GBP_VPIX_TEX_BYTES % 32u == 0u, "texture size must be cache-line aligned");
_Static_assert(GBP_VPIX_TEX_BYTES == 240u * 160u * 2u, "texture is 240x160 16-bit");
_Static_assert(GBP_VPIX_FRAME_BYTES == 40u * 0xF00u, "a frame is 40 blocks of 0xF00");
_Static_assert(PLAY_TEX_BUFFERS >= 2u, "GX may still be reading one buffer while the CPU fills the other");
_Static_assert(GBP_VPRESENT_XFB_BUFFERS == 2u, "the stream needs two framebuffers so the VI is never written under");
_Static_assert(GBP_VQUEUE_MAX_UNDISPOSITIONED == GBP_VPRESENT_TEX_BUFFERS,
               "the balance residual bound must equal the texture buffer count");

static struct {
    struct gbp_vqueue_desc desc;
    uint32_t next_row;
    uint8_t  buf;
    uint8_t  active;
    uint32_t ticks;
    struct gbp_vpix_stats stats;
} conv;

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

#ifndef GBP_STARTUP_MODE
#define GBP_STARTUP_MODE GBP_STARTUP_NORMAL
#endif
static struct gbp_startup startup;

static void *xfb_stream_buf[GBP_VPRESENT_XFB_BUFFERS];

static int xfb_current_index(void)
{
    void *cur = VIDEO_GetCurrentFramebuffer();
    uint32_t i;
    for (i = 0; i < GBP_VPRESENT_XFB_BUFFERS; i++)
        if (cur == xfb_stream_buf[i]) return (int)i;
    return -1;
}

static void *xfb_stream;
static void *xfb_text;
static GXRModeObj *rmode;
static int gecko_present;

#define GX_FIFO_BYTES (256 * 1024)
static uint8_t gx_fifo[GX_FIFO_BYTES] ATTRIBUTE_ALIGN(32);

static void gecko_puts(const char *line)
{
    if (gecko_present) usb_sendbuffer_safe(GECKO_CHANNEL, line, (int)strlen(line));
}

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
    GX_SetDrawDone();
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
    tex_seq[buf] = 0u;
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

/* ---- Issue #19: the input path (unchanged domain -- pad, KEYPAD, the descriptor) ------------- */
static struct gbp_input in_state;
static const struct gbp_transport *in_transport;
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

/* ---- §V28: the origin (gbp_alive, UNCHANGED domain), the native audio chain, the walker ------ */
#define GAME_ORIGIN_DELAY_MS 1000u
_Static_assert(GBP_ALIVE_PAD_A == PAD_BUTTON_A, "gbp_alive's A must be libogc2's");
_Static_assert(GBP_ALIVE_PAD_BUTTONS == PAD_BUTTON_ALL, "the press record reads every button and no stick");
_Static_assert(GBP_APLAY2_CHUNK_BYTES % 32u == 0u, "an AI DMA block is a whole number of 32-byte units");

static struct gbp_alive live;
static struct gbp_aperiod live_per;         /* the positive control's window; unused under press-origin (kept,
                                              * unchanged domain, exactly as sync-0001 keeps it) */
static struct gbp_adec2 adec2;
static int16_t adec2_ring[GBP_APLAY2_RING] ATTRIBUTE_ALIGN(32);
static struct gbp_aplay2 ap2;
static uint8_t ap2_pool[GBP_APLAY2_POOL * GBP_APLAY2_CHUNK_BYTES] ATTRIBUTE_ALIGN(32);
static uint8_t ap2_silence[GBP_APLAY2_CHUNK_BYTES] ATTRIBUTE_ALIGN(32);


static struct gbp_walker walker;

/* THE CONFIGURATION, stated once (HARDWARE_TESTS.md V31.1): T256 at AHEAD 1, passed to the chain as an explicit value. */
#define PLAY_TARGET  GBP_V28_T256
#define PLAY_AHEAD   GBP_V28_A1
_Static_assert(PLAY_TARGET == 4096u && PLAY_AHEAD == 1u, "the vehicle's setting is T256 A1 (Issue #142's shipping decision)");
_Static_assert(GBP_APLAY2_AHEAD == PLAY_AHEAD, "gbp_aplay2_init() already gives the one-chunk depth; the vehicle asserts it instead of assuming it");

static const struct gbp_walker_plan *const V28_PLAN = &GBP_V28_PLAY_GBA;

static uint32_t sync_seed;
static int sync_started;
static uint32_t sync_lines_lost;             /* SYNCCS/SYNCPE admission refusals, together (mirrors sync-0001's
                                               * own single counter for this class of SD-only line) */
static uint32_t syncpe_lines_lost;
static uint8_t syncpe_started_seen[GBP_WALKER_MAX_PHASES], syncpe_ended_seen[GBP_WALKER_MAX_PHASES];
static int z_can_act = 1;
static int live_end;
static uint32_t live_taps, live_taps_failed, live_wrong_len;
static uint64_t live_gap_max, live_gap_at, live_last_t;
static int ai_started, ai_stopped;

/* Issue #138: the counters the diagnostic snapshots per hold, and every plan snapshots per PHASE (SD only): the chain's own cumulative counters, read
 * in one place. Reads only; nothing here decides anything. */
static void v28_snapshot(struct gbp_v28_loss_ctr *c)
{
    c->blocks_in = (uint32_t)adec2.blocks_in;
    c->taps = live_taps;
    c->taps_failed = live_taps_failed;
    c->wrong_len = live_wrong_len;
    c->underruns = (uint32_t)ap2.underruns;
    c->dup = (uint32_t)ap2.dup;
    c->drop = (uint32_t)ap2.drop;
    c->starved = (uint32_t)ap2.starved_steps;
    c->produced = (uint32_t)ap2.produced;
    c->handed = (uint32_t)ap2.handed;
    c->ring_gated = (uint32_t)ap2.ring_gated;
    c->ring = (uint32_t)adec2.count;
    c->target = (uint32_t)ap2.target;
    c->ahead = (uint32_t)ap2.ahead;
}


/* the no-op instruments of the V28 chassis' loss diagnostic: this image measures none of them */
#define V28_TICKS(var)
#define V28_NOTE(id, t0)
#define loss_gap_note(d)        ((void)0)
static uint64_t t_ai_start, t_ai_stop;
static uint64_t play_t_last_step;                          /* the instant of the pump's LAST production slot: what separates teardown silence (POST-FEED) from an underrun */
static uint32_t play_ring_at_dma, play_ready_at_dma;      /* read ONCE, at the DMA start (PLAYSTARTUP) */
static int live_drawn_prompt, live_drawn_press;

/* ---- chunk_corrections: the DEDICATED store (Issue #128 section 6) --------------------------- */
struct v28_corr_record { uint8_t corr; uint8_t reserved; };
_Static_assert(sizeof(struct v28_corr_record) == 2u, "CORR_RECORD_BYTES is 2, tools/v28budget.py");
static struct v28_corr_record corr_store[CORR_CAP];
static uint32_t corr_n, corr_overflow;
static uint32_t corr_min = 0xFFFFFFFFu, corr_max;
static uint64_t corr_sum;

static void corr_note(uint32_t value)
{
    if (corr_n < CORR_CAP) {
        corr_store[corr_n].corr = (uint8_t)value;
        corr_store[corr_n].reserved = 0u;
        corr_n++;
    } else {
        corr_overflow++;
    }
    if (value < corr_min) corr_min = value;
    if (value > corr_max) corr_max = value;
    corr_sum += value;
}

/* THE AUDIO TAP -- gbp_alive's own origin/window detection is UNCHANGED; only the decode call and
 * what happens AT the origin (gbp_walker_start() instead of gbp_async_start(), no AWR arm) differ
 * from sync-0001. */
static void live_tap_body(void *user, const uint8_t *bytes, uint32_t len, uint64_t t_done, int completed)
{
    int act;
    (void)user;
    live_taps++;
    if (!live.t0)
        gbp_alive_start(&live, (pump_res && pump_res->t_capture_start) ? pump_res->t_capture_start : t_done);
    if (!completed) { live_taps_failed++; return; }
    if (len != GBP_ADEC2_BLOCK_BYTES) { live_wrong_len++; return; }
    {
        act = gbp_alive_block(&live, t_done, adec2.count);
        if (!sync_started && live.phase == GBP_ALIVE_WINDOW && live.t_origin) {
            sync_started = 1;
            sync_seed = (uint32_t)live.t_press;
            gbp_walker_start(&walker, V28_PLAN, live.tb_hz, live.t_origin);
        }
        if (act == GBP_ALIVE_DO_DECODE || (sync_started && !gbp_walker_finished(&walker) && live.phase == GBP_ALIVE_DONE)) {
            if (live_last_t) loss_gap_note(t_done - live_last_t);
            if (live_last_t && t_done - live_last_t > live_gap_max) { live_gap_max = t_done - live_last_t; live_gap_at = t_done; }
            live_last_t = t_done;
            {
                V28_TICKS(dec_t0);
                const uint32_t pushed = gbp_adec2_push_block(&adec2, bytes);
                V28_NOTE(GBP_V28_H_DECODE, dec_t0);
                if (pushed == 0)
                    gbp_alive_decoded(&live, adec2.ring[(adec2.head + adec2.count - 1u) % adec2.cap]);
            }
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
        gbp_adec2_calibrate(&adec2, bytes);
    }
    if (sync_started && gbp_walker_finished(&walker)) live_end = 1;
    else if (!sync_started && gbp_alive_finished(&live)) live_end = 1;
}

static void live_tap(void *user, const uint8_t *bytes, uint32_t len, uint64_t t_done, int completed)
{
    V28_TICKS(tap_t0);
    live_tap_body(user, bytes, len, t_done, completed);
    V28_NOTE(GBP_V28_H_TAP, tap_t0);
}


/* THE AI DMA CALLBACK -- interrupt context, native hand-off, and nothing else: the perceptual image's (RUN 55), with no register reads and no marked
 * block. The hand-off ordinal of an underrun is stored by gbp_aplay2_irq_handoff() itself. */
static void live_dma_cb(void)
{
    const uint8_t *c = gbp_aplay2_irq_handoff(&ap2, gettime());
    AUDIO_InitDMA((u32)(size_t)c, GBP_APLAY2_CHUNK_BYTES);
}

/* ---- Issue #27: the per-change KEY record (unchanged domain) --------------------------------- */
static struct ringlog *keylog_rl;
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
    if (r < 0) { keylog_lost++; return; }
    if (r > 0) keylog_truncated++;
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
    if (act == GBP_INPUT_WRITE_FIRST || act == GBP_INPUT_WRITE_CHANGE || act == GBP_INPUT_WRITE_RETRY)
        keylog_emit(t);
}

_Static_assert(KEYLOG_TAIL_RESERVE >= 600u, "the post-run reserve must cover the state machine's report");
_Static_assert(LOG_LINES - KEYLOG_TAIL_RESERVE >= 6900u, "the KEY headroom of a long session");

/* ---- Issue #39: the session end (unchanged domain) -------------------------------------------- */
static struct gbp_session session;
static uint64_t session_hold_ticks;

static void session_step(void)
{
    const struct gbp_transport *t = in_transport;
    if (!t || !in_state.base) return;
    (void)gbp_session_sample(&session, (PAD_ButtonsHeld(PAD_CHAN0) & PAD_BUTTON_Z) ? 1 : 0,
                             t->ticks64(t->ctx));
}


/* ---- the screen, before the session: the prompt, and what the Operator does ---------------------------------------------------------------------- */
static void live_screen(uint64_t now)
{
    if (!live_drawn_prompt && live.t_accept && now >= live.t_accept && live.phase == GBP_ALIVE_PROMPT) {
        live_drawn_prompt = 1;
        printf("\x1b[8;0H");
        printf("  >>> PRESS A within 45 s: the game appears. Then play normally. <<<                   ");
    }
    if (!live_drawn_press && live.phase == GBP_ALIVE_DELAY) {
        live_drawn_press = 1;
        printf("\x1b[10;0H");
        printf("  A RECEIVED. The game appears now. Play normally; do NOT save in the game.            ");
        printf("\x1b[11;0H");
        printf("  The test ends by itself (up to 6 min). Hold Z 1/4 s = end early. X only at the end.  ");
    }
}

static int sync_line_admit(void)
{
    if (keylog_rl && gbp_input_keylog_admit((uint32_t)keylog_rl->count, (uint32_t)keylog_rl->capacity, KEYLOG_TAIL_RESERVE))
        return 1;
    sync_lines_lost++;
    return 0;
}

static const char *syncpe_why(enum gbp_walker_end_reason r)
{
    switch (r) {
    case GBP_WALKER_END_COMPLETE:    return "complete";
    case GBP_WALKER_END_PHASE_CAP:   return "cap";
    case GBP_WALKER_END_SESSION_CAP: return "session";
    case GBP_WALKER_END_STOP:        return "z";
    default:                         return "none";
    }
}

/* Issue #138: the chain's counters at every phase's start and end, every plan, SD only (printed at teardown as V28PHC). The loss the next run must
 * show near 0.18 % is measured PER PHASE, not only over the whole session; the snapshot is taken in the slot that sees the edge (a few ms late at most:
 * its own timestamp is printed, and the reader divides by it). */
struct v28_phase_snap { uint8_t have; uint64_t t; struct gbp_v28_loss_ctr c; };
static struct v28_phase_snap ph_start[GBP_WALKER_MAX_PHASES], ph_end[GBP_WALKER_MAX_PHASES];

static void v28_phase_snap_take(struct v28_phase_snap *s)
{
    /* gettime(), not the transport: teardown clears in_transport before the report runs, and a snapshot taken there (a phase that never ended) must
     * still carry a real time base -- the transport's ticks64 is gettime() on the console (hsp_backend.c h_ticks64) */
    s->t = (uint64_t)gettime();
    v28_snapshot(&s->c);
    s->have = 1u;
}

static void syncpe_edges(void)
{
    uint32_t i;
    if (!sync_started) return;
    for (i = 0; i < V28_PLAN->count; i++) {
        const struct gbp_walker_phase_rec *r = gbp_walker_phase_record(&walker, i);
        if (!r) continue;
        if (r->started && !syncpe_started_seen[i]) {
            syncpe_started_seen[i] = 1u;
            v28_phase_snap_take(&ph_start[i]);
            if (sync_line_admit())
                ringlog_printf(keylog_rl, "SYNCPE p=%lu edge=start t=%llx why=none", (unsigned long)i,
                               (unsigned long long)r->t_start);
            else
                syncpe_lines_lost++;
        }
        if (r->ended && !syncpe_ended_seen[i]) {
            syncpe_ended_seen[i] = 1u;
            v28_phase_snap_take(&ph_end[i]);
            if (sync_line_admit())
                ringlog_printf(keylog_rl, "SYNCPE p=%lu edge=end t=%llx why=%s", (unsigned long)i,
                               (unsigned long long)r->t_end, syncpe_why(r->reason));
            else
                syncpe_lines_lost++;
        }
    }
}

/* THE SESSION STEP. No handler is started, ticked or completed: the walker only sequences (navigate's cap starts `play`; the play cap, the session cap
 * or the Operator's Z ends the walk). What the chain does here is produce, queue and start the DMA -- at ONE setting, configured in main(). */
static void live_step(void)
{
    const struct gbp_transport *t = in_transport;
    uint64_t now;
    int b, ending;
    if (!t || !in_state.base) return;
    now = t->ticks64(t->ctx);
    gbp_alive_buttons(&live, now, (uint16_t)(PAD_ButtonsHeld(PAD_CHAN0) & 0xFFFFu));

    if (sync_started && !gbp_walker_finished(&walker)) {
        int wflags = 0;
        if (session.end_requested && z_can_act) {
            wflags = gbp_walker_stop(&walker, now, 0);   /* Z: end the WHOLE walk (gbp_walker's own semantics) */
            z_can_act = 0;
        }
        if (!(PAD_ButtonsHeld(PAD_CHAN0) & PAD_BUTTON_Z)) { z_can_act = 1; session.end_requested = 0; }
        if (!(wflags & GBP_WALKER_TICK_FINISHED)) (void)gbp_walker_tick(&walker, now, 0);
        syncpe_edges();
        if (gbp_walker_finished(&walker)) live_end = 1;
    } else if (session.end_requested) {
        live_end = 1;
    }

    /* The end is tested BEFORE the production branch: a session that is ending (the walker finished, or Z inside the alive window) stops the DMA in this very slot instead of letting the
     * feed stop while the DMA keeps handing out silence (review of the build half: those silences were counted as underruns) */
    ending = live_end || (sync_started && gbp_walker_finished(&walker));
    if (!ending && (live.phase == GBP_ALIVE_WINDOW || (sync_started && !gbp_walker_finished(&walker) && live.phase == GBP_ALIVE_DONE))) {
        play_t_last_step = now;
        b = gbp_aplay2_produce(&ap2, &adec2);
        if (b >= 0) {
            DCFlushRange(ap2_pool + (size_t)b * GBP_APLAY2_CHUNK_BYTES, GBP_APLAY2_CHUNK_BYTES);
            gbp_aplay2_queue(&ap2, b);
            corr_note(ap2.chunk_corrections);
        }
        gbp_aplay2_process(&ap2);
        /* gbp_aplay2_start_ready(): never a literal >= 2u, which is unreachable at AHEAD 1 by construction (gbp_aplay2.h) */
        if (!ai_started && gbp_aplay2_start_ready(&ap2, adec2.count)) {
            const uint8_t *first;
            ai_started = 1;
            t_ai_start = now;
            play_ring_at_dma = (uint32_t)adec2.count;       /* PLAYSTARTUP: the fill AT the start, read once */
            play_ready_at_dma = gbp_aplay2_ready(&ap2);
            ap2.playing = 1u;
            first = gbp_aplay2_irq_handoff(&ap2, now);      /* hand-off ordinal 1 */
            ap2.measuring = 1u;
            AUDIO_InitDMA((u32)(size_t)first, GBP_APLAY2_CHUNK_BYTES);
            AUDIO_StartDMA();
        }
    } else if (ai_started && !ai_stopped && ending) {
        AUDIO_StopDMA();
        ap2.measuring = 0u;
        ap2.playing = 0u;
        ai_stopped = 1;
        t_ai_stop = now;
        gbp_aplay2_process(&ap2);
    }
    live_screen(now);
}

/* THE CONSUMER SLICE -- unchanged from sync-0001 (video/vqueue/vpresent domain). */
static void pump_body(void *user)
{
    uint32_t t0, t1, row, n;
    (void)user;

    input_step();
    session_step();
    live_step();

    offer_oldest_ready();

    if (!conv.active) {
        int buf;
        buf = gbp_vpresent_acquire(&present);
        if (buf < 0) return;
        if (!gbp_vqueue_take(&vq, &conv.desc)) {
            (void)gbp_vpresent_abandon(&present, buf);
            return;
        }
        conv.buf = (uint8_t)buf;
        conv.next_row = 0u;
        conv.ticks = 0u;
        conv.active = 1u;
        memset(&conv.stats, 0, sizeof conv.stats);
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
            (void)gbp_vpresent_abandon(&present, (int)conv.buf);
            tex_seq[conv.buf] = 0u;
            conv.active = 0u;
            conv_abandoned_no_raw++;
            return;
        }
        (void)gbp_vpix_block(blk, row, tex_buf[conv.buf], GBP_VPIX_TEX_BYTES / 2u, &conv.stats);
        conv.next_row++;
    }
    t1 = (uint32_t)gettick();
    {
        const uint32_t d = t1 - t0;
        conv.ticks += d;
        gbp_vqueue_pump_slice(&vq, d, conv.next_row >= GBP_VPIX_BLOCKS);
    }

    if (conv.next_row < GBP_VPIX_BLOCKS) return;

    if (!gbp_vqueue_commit(&vq, gbp_vqueue_still_valid(&vq, &conv.desc), conv.ticks)) {
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

    DCFlushRange(tex_buf[conv.buf], GBP_VPIX_TEX_BYTES);
    tex_t_done[conv.buf] = gettime();
    (void)gbp_vpresent_fill_done(&present, (int)conv.buf);
    conv.active = 0u;
    offer_oldest_ready();
}

/* Issue #137: the whole pump call is the stretch the drain cannot run in (GBP-HW-332); measured in the diag_loss image only. */
static void pump(void *user)
{
    V28_TICKS(pump_t0);
    pump_body(user);
    V28_NOTE(GBP_V28_H_PUMP, pump_t0);
}

/* ---- the display submit: the main quad alone, in one GX batch released by one draw-done token (gbp_vpresent.c's one-token rule). No label. */
static void submit_ready(int buf, struct gbp_vqueue *account)
{
    int xfb, cur;
    uint64_t t_dec;

    cur = xfb_current_index();
    t_dec = gettime();
    xfb = gbp_vpresent_xfb_target(&present, cur);
    if (xfb < 0) {
        if (!account) selftest_repeats++;
        return;
    }

    if (!gbp_vpresent_submit(&present, buf)) return;

    GX_InvalidateTexAll();
    GX_InitTexObj(&tex_obj, tex_buf[buf], GBP_VPIX_WIDTH, GBP_VPIX_HEIGHT,
                  GX_TF_RGB5A3, GX_CLAMP, GX_CLAMP, GX_FALSE);
    GX_InitTexObjFilterMode(&tex_obj, GX_NEAR, GX_NEAR);
    GX_LoadTexObj(&tex_obj, GX_TEXMAP0);
    draw_quad();

    GX_SetDrawDone();
    GX_CopyDisp(xfb_stream_buf[xfb], GX_TRUE);
    GX_Flush();
    if (live.phase == GBP_ALIVE_DELAY || live.phase == GBP_ALIVE_WINDOW ||
        (sync_started && !gbp_walker_finished(&walker) && live.phase == GBP_ALIVE_DONE)) {
        VIDEO_SetNextFramebuffer(xfb_stream_buf[xfb]);
        VIDEO_Flush();
    }
    gbp_vpresent_xfb_handed(&present, xfb);
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
    tex_seq[buf] = 0u;
}

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

/* ---- the screen/live report: no plan conditional (one plan), no leak rule (nothing is blinded); the phase number and "done" only ---------------- */
static void play_screen_report(void)
{
    if (!sync_started) {
        printf("  PLAY    not started (no origin)\n");
        return;
    }
    if (gbp_walker_finished(&walker)) {
        printf("  PLAY    done\n");
        return;
    }
    printf("  PLAY    phase %lu of %lu, running\n", (unsigned long)walker.index + 1u, (unsigned long)V28_PLAN->count);
}

static void play_live_report(void)
{
    char line[160];
    if (gbp_walker_finished(&walker)) {
        gecko_puts("OPENGBP-PLAY done\n");
        return;
    }
    snprintf(line, sizeof line, "OPENGBP-PLAY phase=%lu of %lu finished=0\n", (unsigned long)walker.index + 1u,
             (unsigned long)V28_PLAN->count);
    gecko_puts(line);
}

static void v28_phase_report(struct ringlog *rl)
{
    uint32_t i;
    struct v28_phase_snap now_snap;
    v28_phase_snap_take(&now_snap);
    for (i = 0u; i < V28_PLAN->count; i++) {
        const struct v28_phase_snap *a = &ph_start[i];
        const struct v28_phase_snap *b = ph_end[i].have ? &ph_end[i] : &now_snap;
        if (!a->have) continue;
        ringlog_printf(rl, "V28PHC p=%lu ended=%u t0=%llx t1=%llx blocks_in=%lu taps=%lu failed=%lu wrong=%lu underruns=%lu",
                       (unsigned long)i, (unsigned)ph_end[i].have, (unsigned long long)a->t, (unsigned long long)b->t,
                       (unsigned long)(b->c.blocks_in - a->c.blocks_in), (unsigned long)(b->c.taps - a->c.taps),
                       (unsigned long)(b->c.taps_failed - a->c.taps_failed), (unsigned long)(b->c.wrong_len - a->c.wrong_len),
                       (unsigned long)(b->c.underruns - a->c.underruns));
        ringlog_printf(rl, "V28PHD p=%lu dup=%lu drop=%lu starved=%lu produced=%lu handed=%lu gated=%lu ring=%lu,%lu",
                       (unsigned long)i, (unsigned long)(b->c.dup - a->c.dup), (unsigned long)(b->c.drop - a->c.drop),
                       (unsigned long)(b->c.starved - a->c.starved), (unsigned long)(b->c.produced - a->c.produced),
                       (unsigned long)(b->c.handed - a->c.handed), (unsigned long)(b->c.ring_gated - a->c.ring_gated),
                       (unsigned long)a->c.ring, (unsigned long)b->c.ring);
    }
}

static uint64_t t_video_ready, t_selftest_begin, t_selftest_end, t_probe_enter;

/* ---- the final screen's title selection (HARDWARE_TESTS.md V31.4): AFTER the session, the transport is torn down and nothing is forwarded to the
 * cartridge. D-pad LEFT / RIGHT steps, A confirms. Drawn at fixed rows of a cleared screen, so it never depends on what was printed before. */
#define DECL_ROW 16
/* `idx`/`confirmed` are the EFFECTIVE declaration: after the save they are what the log line says (an unconfirmed selection is UNDECLARED), never the stepped-to title */
static void decl_draw(uint32_t idx, int confirmed, int locked)
{
    const struct gbp_cartdecl_entry *e = gbp_cartdecl_entry_at(idx);
    printf("\x1b[%d;0H", DECL_ROW);
    printf("  TITLE: D-pad LEFT/RIGHT choose, A confirm                    \n");
    printf("  %lu/%lu  %-52s\n", (unsigned long)idx + 1u, (unsigned long)gbp_cartdecl_count(), e ? e->title : "?");
    printf("  form: %-22s %-12s %-22s\n", e ? e->form : "?", confirmed ? "[CONFIRMED]" : "[not confirmed]", locked ? "LOCKED: saved so" : "");
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
    char ident_text[OPENGBP_IDENT_MAX];
    const struct opengbp_ident ident = { OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT };
    const struct gbp_initirqa_result *a;
    uint32_t tb_hz = (uint32_t)TB_TIMER_CLOCK * 1000u;
    int saved = 0;
    const uint64_t t_program = gettime();
    uint32_t j;

    gbp_startup_profile(&startup, GBP_STARTUP_MODE);

    video_setup();
    t_video_ready = gettime();
    gx_setup();
    PAD_Init();
    gecko_present = usb_isgeckoalive(GECKO_CHANNEL);
    opengbp_ident_format(ident_text, sizeof ident_text, &ident);

    printf("\n  Open-GBP " TEST_ID "  Issue #158, THE GBA PLAY IMAGE vehicle-0002 (NOT PHYSICALLY VALIDATED)\n");
    printf("  Build : %s   Commit: %s   Plan: play_gba\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("  libogc: %s   Gecko: %s\n", _V_STRING, gecko_present ? "yes" : "no");
    printf("  %s\n\n", opengbp_ident_marker);

    snprintf(line, sizeof line, "OPENGBP-PLAY READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    gbp_vstate_config_default(&cfg);
    gbp_vstate_config_timebase(&cfg, tb_hz);
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
    session_hold_ticks = ((uint64_t)tb_hz * PLAY_SESSION_END_HOLD_MS) / 1000u;
    gbp_session_init(&session, session_hold_ticks);
    cfg.session_end = &live_end;
    gbp_alive_init(&live, tb_hz);
    gbp_alive_use_press_origin(&live, GAME_ORIGIN_DELAY_MS);
    gbp_aperiod_reset(&live_per, GBP_ALIVE_PERIOD);
    gbp_adec2_init(&adec2, adec2_ring, GBP_APLAY2_RING);
    gbp_aplay2_init(&ap2, ap2_pool, ap2_silence, NULL, NULL);   /* no L2 keep, no store -- same as sync-0001 */
    /* THE CONFIGURATION (V31.1): the plain setter, never the transition machine; T256 at AHEAD 1 (the library's own AHEAD, asserted equal above), recorded in PLAYCFG */
    gbp_aplay2_set_target(&ap2, PLAY_TARGET);
    /* Issue #138 (RUN 54): every image takes the steady production step, 64 pushes a call (gbp_v28_step.h) */
    ap2.step_pushes = gbp_v28_step_hook;
    ap2.step_pushes_user = 0;
    DCFlushRange(ap2_silence, sizeof ap2_silence);
    cfg.audio_tap = live_tap;
    cfg.audio_tap_user = 0;

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
    in_selftest_ok = gbp_input_selftest();
    printf("  SELF-TEST input path: %s\n", in_selftest_ok ? "ok" : "NOT OK");

    cfg.prehandler_wait_ms = startup.prehandler_wait_ms;
    cfg.hard_wallclock_s = PLAY_SAFETY_SECONDS;
    cfg.hard_wallclock_ticks = (uint64_t)tb_hz * PLAY_SAFETY_SECONDS;
    cfg.max_deliveries = PLAY_MAX_DELIVERIES;
    gbp_vstate_config_disable_time_target(&cfg);
    cfg.cyc_first = cyc_first;
    cfg.cyc_last = cyc_last;
    cfg.cyc_anomaly = cyc_anomaly;
    cfg.cyc_episode = cyc_episode;

    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);
    ringlog_printf(&rl, "IDENT test=%s app=%s build=%s commit=%s libogc=%s", TEST_ID,
                   OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, _V_STRING);
    ringlog_printf(&rl, "PLAYCFG plan=play_gba navigate_s=%lu play_bound_s=%lu session_cap_s=%lu wall_s=%lu target=%lu ahead=%lu step=%lu "
                        "startup_k=%lu cold_start=set_target mode=GBA",
                   (unsigned long)GBP_V28_P0_ALLOWANCE_S, (unsigned long)PLAY_BOUND_S, (unsigned long)V28_SESSION_CAP_S,
                   (unsigned long)V28_WALL_S, (unsigned long)ap2.target, (unsigned long)ap2.ahead,
                   (unsigned long)GBP_V28_STEP_STEADY, (unsigned long)GBP_PLAY_STARTUP_K);
    ringlog_printf(&rl, "ENVPLAY safety_s=%lu max_deliveries=%lu session_end=Z_or_walker hold_ms=%lu",
                   (unsigned long)PLAY_SAFETY_SECONDS, (unsigned long)PLAY_MAX_DELIVERIES,
                   (unsigned long)PLAY_SESSION_END_HOLD_MS);
    {
        const char *fault = gbp_vstate_storage_fault(&vstate);
        ringlog_printf(&rl, "ENVSTORE frames=%lu/%lu events=%lu/%lu corr_cap=%lu fault=%s ok=%d",
                       (unsigned long)vstate.frames_cap, (unsigned long)GBP_VSTATE_MAX_FRAMES,
                       (unsigned long)vstate.events_cap, (unsigned long)GBP_VSTATE_MAX_EVENTS,
                       (unsigned long)CORR_CAP, fault ? fault : "-", gbp_vstate_storage_ok(&vstate));
        if (fault) {
            printf("\n  FATAL: the state model's storage contract is not met: field=%s\n", fault);
            printf("  The probe was NOT entered.\n");
            gecko_puts("OPENGBP-PLAY STORAGE FATAL field=");
            gecko_puts(fault);
            gecko_puts("\n");
        }
    }
    {   /* V31.2: the store bound MEASURED on this chassis -- what the allocation left of the arena, read before the session starts */
        extern char __bss_end[];
        const uint32_t lo = (uint32_t)(size_t)SYS_GetArena1Lo();
        const uint32_t hi = (uint32_t)(size_t)SYS_GetArena1Hi();
        ringlog_printf(&rl, "ENVMEM bss_end=%08lx arena1_lo=%08lx arena1_hi=%08lx arena1_free=%lu frames_bytes=%lu events_bytes=%lu "
                            "corr_bytes=%lu log_bytes=%lu xfb=3x%lu",
                       (unsigned long)(size_t)__bss_end, (unsigned long)lo, (unsigned long)hi,
                       (unsigned long)(hi > lo ? hi - lo : 0u), (unsigned long)sizeof frame_store,
                       (unsigned long)sizeof event_store, (unsigned long)sizeof corr_store,
                       (unsigned long)sizeof log_storage, (unsigned long)VIDEO_GetFrameBufferSize(rmode));
    }

    AUDIO_Init(NULL);
    AUDIO_SetDSPSampleRate(AI_SAMPLERATE_32KHZ);
    AUDIO_RegisterDMACallback(live_dma_cb);

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);
    hsp_backend_irq_transport_ext(&hsp, &t);

    printf("  Sequence: the vstate-0004 service path VERBATIM.\n");
    printf("  Session:  it ends by itself (up to 6 min); HOLD Z for %lu ms to end it early. Wall %lu s.\n",
           (unsigned long)PLAY_SESSION_END_HOLD_MS, (unsigned long)PLAY_SAFETY_SECONDS);
    if (!gbp_transport_has_bulk_read(&t) || !gbp_transport_has_irq_reset(&t) || !gbp_transport_has_time64(&t)) {
        printf("\n  FATAL: the transport lacks the whole-block read, the record reset or the 64-bit time base.\n");
        printf("  Nothing was run. START = exit\n");
        for (;;) { VIDEO_WaitVSync(); PAD_ScanPads(); if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break; }
        exit(1);
    }
    printf("\x1b[2J\x1b[1;0H");
    printf("  Open-GBP " TEST_ID "  %s  %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("  Cartridge: the GBA game in the console. Link Port: nothing. BBA: absent.\n");
    printf("  WAIT for the prompt below (about 5 s). Then press A within 45 s: the game appears.\n");
    printf("  Play normally. Do NOT save in the game.\n");

    pump_res = &res;
    in_transport = &t;
    keylog_rl = &rl;
    t_probe_enter = gettime();
    gbp_vstate_probe_run(&t, &rl, &cfg, &res);
    a = &res.a;

    gbp_vpresent_shutdown(&present);
    cfg.stream = 0;
    vq.pump = 0;
    in_transport = 0;
    keylog_rl = 0;
    if (gbp_vpresent_inflight(&present)) {
        GX_DrawDone();
        gx_drained_at_teardown = 1;
    }
    GX_SetDrawDoneCallback(gx_prev_drawdone_cb);
    gx_callback_restored = 1;

    if (ai_started && !ai_stopped) {
        AUDIO_StopDMA();
        ap2.measuring = 0u;
        ap2.playing = 0u;
        ai_stopped = 1;
        t_ai_stop = gettime();
    }
    AUDIO_RegisterDMACallback(NULL);
    gbp_aplay2_process(&ap2);

    VIDEO_SetNextFramebuffer(xfb_text);
    VIDEO_Flush();
    VIDEO_WaitVSync();

    ringlog_printf(&rl, "STATS transfers=%lu timeouts=%lu busy=%lu bulk_transfers=%lu bulk_bytes=%lu",
                   (unsigned long)hsp.transfers, (unsigned long)hsp.timeouts, (unsigned long)hsp.busy_refusals,
                   (unsigned long)hsp.bulk_transfers, (unsigned long)hsp.bulk_bytes);
    ringlog_printf(&rl, "INPUT selftest=%d steps=%lu key_changes=%lu completed=%lu failed=%lu",
                   in_selftest_ok, (unsigned long)in_state.steps, (unsigned long)in_state.keys_changes,
                   (unsigned long)in_state.writes_completed, (unsigned long)in_state.writes_failed);
    ringlog_printf(&rl, "KEYLOG events=%lu emitted=%lu lost=%lu truncated=%lu reserve=%u",
                   (unsigned long)in_state.events_recorded, (unsigned long)keylog_emitted, (unsigned long)keylog_lost,
                   (unsigned long)keylog_truncated, (unsigned)KEYLOG_TAIL_RESERVE);
    ringlog_printf(&rl, "SESSION hold_ms=%lu requested=%d held=%lu holds=%lu stop=%s",
                   (unsigned long)PLAY_SESSION_END_HOLD_MS, session.end_requested, (unsigned long)session.samples_held,
                   (unsigned long)session.holds_begun, gbp_vstate_stop_name(res.stop));

    /* ---- Issue #158 (vehicle-0002): the startup profile and the Policy A invariants, SD only, in the ten copies' format. TEARDOWN ONLY: the probe has
     * returned, the draw-done callback is restored and the DMA callback is gone; unconditional, so an aborted session writes them too. ---- */
    {
        char srec[LOG_LINE_LEN];
        gbp_startrec_startup(srec, sizeof srec, gbp_startup_mode_name(&startup), startup.selftest_run, startup.selftest_visible,
                             startup.prehandler_wait_ms, startup.clear_framebuffers, gbp_startup_is_normal_clean(&startup),
                             selftest_presents, selftest_headless);
        ringlog_printf(&rl, "%s", srec);
        gbp_startrec_startupt(srec, sizeof srec, tb_hz, t_program, t_video_ready, t_selftest_begin, t_selftest_end, t_probe_enter,
                              res.t_control_transform, res.t_capture_start);
        ringlog_printf(&rl, "%s", srec);
        gbp_startrec_startupv(srec, sizeof srec, first_real.have, first_real.frame_index, first_real.t_take, first_real.t_convert_done,
                              first_real.t_decision, res.t_control_transform);
        ringlog_printf(&rl, "%s", srec);
        gbp_startrec_streaminv(srec, sizeof srec, gbp_vpresent_invariant_checks(&present), gbp_vpresent_invariant_failures(&present),
                               present.invariant_failures, present.invariant_checks, present.invariant_failures_isr,
                               present.invariant_checks_isr, gbp_vpresent_consistent(&present));
        ringlog_printf(&rl, "%s", srec);
        gbp_startrec_streamselftest(srec, sizeof srec, selftest_ok, selftest_converted, selftest_released, selftest_presents,
                                    selftest_repeats, selftest_sci_clean);
        ringlog_printf(&rl, "%s", srec);
    }

    /* ---- the play image's own records. EVERY one below is SD-only: nothing here reaches the screen or the live/gecko channel. ---- */
    if (sync_started) {
        struct gbp_play_under_sum us;
        uint32_t q;
        uint64_t t_feed_end;
        char rec[LOG_LINE_LEN];
        ringlog_printf(&rl, "V28SEED seed=%08lx", (unsigned long)sync_seed);
        ringlog_printf(&rl, "V28C underruns=%lu overflow=%lu silences=%lu mute_handed=%lu dup=%lu drop=%lu produced=%lu "
                            "handed=%lu ring_gated=%lu",
                       (unsigned long)ap2.underruns, (unsigned long)adec2.overflow, (unsigned long)ap2.silences,
                       (unsigned long)ap2.mute_handed, (unsigned long)ap2.dup, (unsigned long)ap2.drop,
                       (unsigned long)ap2.produced, (unsigned long)ap2.handed, (unsigned long)ap2.ring_gated);
        ringlog_printf(&rl, "V28C2 discarded=%lu starved_steps=%lu lost=%lu blocks_in=%lu ring_discarded=%lu "
                            "dropped_front=%lu cs=0 acted=0 syncpe_lost=%lu lines_lost=%lu",
                       (unsigned long)ap2.discarded_chunks, (unsigned long)ap2.starved_steps, (unsigned long)adec2.lost,
                       (unsigned long)adec2.blocks_in, (unsigned long)adec2.discarded,
                       (unsigned long)ap2.dropped_front, (unsigned long)syncpe_lines_lost, (unsigned long)sync_lines_lost);
        ringlog_printf(&rl, "V28CORR n=%lu overflow=%lu min=%lu max=%lu mean_x100=%lu cap=%lu",
                       (unsigned long)corr_n, (unsigned long)corr_overflow,
                       (unsigned long)(corr_n ? corr_min : 0u), (unsigned long)corr_max,
                       (unsigned long)(corr_n ? (unsigned long)((corr_sum * 100u) / corr_n) : 0u),
                       (unsigned long)CORR_CAP);
        ringlog_printf(&rl, "V28TAPS taps=%lu taps_failed=%lu wrong_len=%lu blocks_in=%lu gap_max=%llu gap_at=%llx",
                       (unsigned long)live_taps, (unsigned long)live_taps_failed, (unsigned long)live_wrong_len,
                       (unsigned long)adec2.blocks_in, (unsigned long long)live_gap_max, (unsigned long long)live_gap_at);
        v28_phase_report(&rl);
        /* V31.3: the start-up apart from what comes after it. The chain counts (ap2.underruns); the callback stored the hand-off ordinal and
         * the instant of the first GBP_APLAY2_UNDER_CAP of them; this reads them after the DMA has stopped. */
        if (ai_started) {
            gbp_play_under_fmt_startup(rec, sizeof rec, t_ai_start, GBP_PLAY_STARTUP_K, play_ring_at_dma, play_ready_at_dma);
            ringlog_printf(&rl, "%s", rec);
            /* POST-FEED: an underrun later than the pump's last production slot (plus 10 ms: a genuine underrun always has a production slot within a few ms after it)
             * is teardown silence -- a probe-side stop (a store cap, the wall) runs no pump call while the DMA still hands out silence */
            t_feed_end = play_t_last_step + tb_hz / 100u;
            gbp_play_under_summarize(&us, (uint32_t)ap2.underruns, ap2.under_handed, ap2.under_t, GBP_APLAY2_UNDER_CAP, GBP_PLAY_STARTUP_K, t_feed_end);
            for (q = 0u; q < us.recorded; q++) {
                gbp_play_under_fmt_und(rec, sizeof rec, q, ap2.under_handed[q], ap2.under_t[q], t_ai_start, tb_hz,
                                       ap2.under_handed[q] > GBP_PLAY_STARTUP_K && ap2.under_t[q] > t_feed_end);
                ringlog_printf(&rl, "%s", rec);
            }
            gbp_play_under_fmt_sum(rec, sizeof rec, &us, GBP_PLAY_STARTUP_K);
            ringlog_printf(&rl, "%s", rec);
        } else {
            ringlog_printf(&rl, "PLAYSTARTUP t_dma=none k=%lu reason=dma_never_started", (unsigned long)GBP_PLAY_STARTUP_K);
        }
        /* the backstop: EVERY phase index, INCLUDING 0 -- and what actually classifies why=probe vs why=z (see syncpe_why) */
        for (j = 0u; j < V28_PLAN->count; j++) {
            const struct gbp_walker_phase_rec *r = gbp_walker_phase_record(&walker, j);
            const char *why;
            if (!r || !r->started) continue;
            if (r->ended) {
                why = syncpe_why(r->reason);
            } else {
                why = (res.stop != GBP_VSTATE_STOP_SESSION_END) ? "probe" : "none";
                if (!syncpe_ended_seen[j] && sync_line_admit())
                    ringlog_printf(&rl, "SYNCPE p=%lu edge=end t=%llx why=%s", (unsigned long)j,
                                   (unsigned long long)live_last_t, why);
                syncpe_ended_seen[j] = 1u;
            }
            ringlog_printf(&rl, "SYNCPH phase=%lu t_start=%llx t_end=%llx ended=%u reason=%s",
                           (unsigned long)j, (unsigned long long)r->t_start, (unsigned long long)r->t_end,
                           (unsigned)r->ended, why);
        }
        ringlog_printf(&rl, "V28END stop=%s t=%llx", gbp_vstate_stop_name(res.stop), (unsigned long long)live_last_t);
    } else {
        ringlog_printf(&rl, "V28END stop=%s t=%llx reason=no_origin", gbp_vstate_stop_name(res.stop),
                       (unsigned long long)live_last_t);
    }

    gbp_vstate_summary(&res, summary, sizeof summary);

    printf("\x1b[2J\x1b[1;0H");
    printf("  Open-GBP " TEST_ID "  %s  %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("\n  HARDWARE status=%s (%s) reason=%s stop=%s restore=%s\n", res.status_name, res.status_class,
           res.reason ? res.reason : "-", gbp_vstate_stop_name(res.stop), res.restore_ok ? "ok" : "ERROR");
    printf("  SESSION %s: Z held %lu of %lu samples\n",
           res.stop == GBP_VSTATE_STOP_SESSION_END ? "ENDED (success)" : "NOT ended by the operator",
           (unsigned long)session.samples_held, (unsigned long)session.samples);
    printf("  RESTORE control=%d stop=%d cleanup=%d arinfo=%d handler=%d mask_ok=%d\n",
           a->control_restore_ok, a->irq_stop_write_ok, a->pi_cleanup_performed, a->arinfo_restore_ok,
           res.h.handler_restored, res.h.mask_ok);
    play_screen_report();

    snprintf(line, sizeof line, "OPENGBP-PLAY RESULT status=%s stop=%s service=%d deliveries=%lu restore=%d\n",
             res.status_name, gbp_vstate_stop_name(res.stop), res.service_ok, (unsigned long)res.deliveries,
             res.restore_ok);
    gecko_puts(line);
    play_live_report();

    {
        uint32_t decl_idx = GBP_CARTDECL_UNDECLARED;
        int decl_confirmed = 0, decl_locked = 0;
        uint32_t settle, start_held = 0u;
        /* The session usually ends by itself mid-play, with the Operator's fingers on the GAME's buttons (START pauses, A/B/D-pad/X/Y are game keys): nothing on this screen may act on
         * them. Wait (bounded, about 5 s) until no button is held, then ignore every edge for a second. */
        printf("\n  Release every button...\n");
        for (settle = 0u; settle < 300u; settle++) {
            VIDEO_WaitVSync();
            PAD_ScanPads();
            if (PAD_ButtonsHeld(0) == 0u) break;
        }
        for (settle = 0u; settle < 60u; settle++) { VIDEO_WaitVSync(); PAD_ScanPads(); }
        printf("\x1b[2J\x1b[1;0H");
        printf("  Open-GBP " TEST_ID "  %s  %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
        printf("\n  HARDWARE status=%s (%s) stop=%s restore=%s\n", res.status_name, res.status_class, gbp_vstate_stop_name(res.stop), res.restore_ok ? "ok" : "ERROR");
        printf("  SESSION %s\n", res.stop == GBP_VSTATE_STOP_SESSION_END ? "ENDED" : "NOT ended by the operator");
        printf("  RESTORE control=%d stop=%d cleanup=%d arinfo=%d handler=%d mask_ok=%d\n", a->control_restore_ok, a->irq_stop_write_ok,
               a->pi_cleanup_performed, a->arinfo_restore_ok, res.h.handler_restored, res.h.mask_ok);
        play_screen_report();
        printf("\n  D-pad LEFT/RIGHT + A = which game was in the console\n");
        printf("  X = save log to SD   START (hold 1.5 s; at once once saved) = exit\n");
        printf("  POWER CYCLE REQUIRED\n");
        decl_draw(decl_idx, decl_confirmed, decl_locked);
        for (;;) {
            u32 down;
            VIDEO_WaitVSync();
            PAD_ScanPads();
            down = PAD_ButtonsDown(0);
            if (!decl_locked) {
                const uint32_t before = decl_idx;
                const int was = decl_confirmed;
                if (down & PAD_BUTTON_RIGHT) { decl_idx = gbp_cartdecl_step(decl_idx, 1); decl_confirmed = 0; }
                if (down & PAD_BUTTON_LEFT) { decl_idx = gbp_cartdecl_step(decl_idx, -1); decl_confirmed = 0; }
                if (down & PAD_BUTTON_A) decl_confirmed = 1;
                if (decl_idx != before || decl_confirmed != was) decl_draw(decl_idx, decl_confirmed, decl_locked);
            }
            if (!saved && (down & PAD_BUTTON_X)) {
                char extra[240];
                char decl[LOG_LINE_LEN];
                int rc;
                if (!decl_locked) {
                    /* V31.4: the declaration is appended ONCE, before the first save attempt, and the selection is locked from then on, so the
                     * saved line is the one the screen shows; an unconfirmed selection is written as UNDECLARED (entered=none) */
                    decl_locked = 1;
                    if (!decl_confirmed) decl_idx = GBP_CARTDECL_UNDECLARED;
                    gbp_cartdecl_fmt(decl, sizeof decl, decl_idx, decl_confirmed);
                    ringlog_printf(&rl, "%s", decl);
                    decl_draw(decl_idx, decl_confirmed, decl_locked);
                }
                snprintf(extra, sizeof extra,
                         "libogc=%s gecko=%d power_cycle_required=%d time_target=disabled safety_s=%lu "
                         "session_end=walker_or_Z hold_ms=%lu stop=%s status=%s",
                         _V_STRING, gecko_present, res.power_cycle_required,
                         (unsigned long)PLAY_SAFETY_SECONDS, (unsigned long)PLAY_SESSION_END_HOLD_MS,
                         gbp_vstate_stop_name(res.stop), res.status_name);
                rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl, status, sizeof status, line,
                                sizeof line);
                saved = (rc == 0);
                printf("\x1b[%d;0H  SAVE log     %-60s\n", DECL_ROW + 5, status);
            }
            /* START is the pause key of nearly every GBA game and the log lives only in RAM until X: exit at once only after a successful save, else on a 1.5 s hold */
            start_held = (PAD_ButtonsHeld(0) & PAD_BUTTON_START) ? start_held + 1u : 0u;
            if ((saved && (down & PAD_BUTTON_START)) || start_held >= 90u) break;
        }
    }
    gecko_puts("OPENGBP-PLAY DONE\n");
    (void)t_program; (void)t_video_ready; (void)t_selftest_begin; (void)t_selftest_end; (void)t_probe_enter;
    return 0;
}
