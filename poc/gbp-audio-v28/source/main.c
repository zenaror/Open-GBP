/*
 * gbp-audio-v28 -- Issue #128 (frozen), #129/#130 (the follow-up execution checkpoint): §V28's
 * latency validation round, the native decoder as the audio path, the two-run ladder, the event
 * budget and the leak rules, implemented on top of poc/gbp-audio-sync's own chassis (video, vstate,
 * vqueue, vpresent, GX, input, session, keylog, SD save/teardown, startup profile -- ALL carried
 * over UNCHANGED, per the Orchestrator's own instruction) with the WHOLE audio pipeline replaced:
 *
 *   gbp_adec/gbp_aresamp/gbp_aplay/gbp_atrans  -> gbp_adec2/gbp_aresamp2/gbp_aplay2/gbp_atrans2
 *   gbp_async (P0..P3, one hand-written session) -> gbp_walker (a pure ordered-list sequencer)
 *                                                    + gbp_v28_3a/3b/sweep/nulling (the domain logic)
 *
 * ONE SOURCE, TWO IMAGES, chosen by the Makefile's PLAN variable: `validation_run`
 * (navigate -> 3a -> 3b -> sweep, automatic, "he judges nothing") and `perceptual_no_phase1`
 * (navigate -> nulling, operator-driven), both frozen in src/audio/gbp_v28_plans.h. The build
 * defines exactly one of GBP_V28_PLAN_VALIDATION / GBP_V28_PLAN_PERCEPTUAL.
 *
 * DROPPED FROM sync-0001, BY THE ORCHESTRATOR'S OWN DECISION (Issue #129/#130): the raw AUDIO
 * window (gbp_awr, the OGBPAWR1 sidecar) -- no §V28 question reads it, its own copy cost runs in
 * the SAME pump slot the validation run measures the AHEAD margin in, and dropping it raises the
 * wall ceiling by 158 s. No gbp_awr.c/.h is linked here.
 *
 * THE LEAK RULES (Issue #128 §7, Amendment C -- read in full before touching a printf/gecko_puts
 * site in this file):
 *
 *   SAFE (kind-independent instants)
 *     Phase 0            the phase name and a clock
 *     nulling            "setting k" when settings_n changes. Not at the confirm's return value
 *     validation run     anything else: he judges nothing there
 *   NEVER, in the perceptual run
 *     accepted step counts, plans, acted, C-stick event counts, refusal/busy counters
 *     any visible response to a LEFT / RIGHT press
 *     his answers, which stick direction is deeper (p2_dir)
 *     the TARGET or AHEAD in force, or anything read from gbp_atrans2/gbp_aplay2/gbp_adec2, or the
 *     target/fill rows
 *   AMENDMENT C, UNIVERSAL, NO EXEMPTION, BOTH IMAGES: depths, plans, acted come off the
 *     post-session screen and the live/gecko channel entirely. They go to the SD log ONLY. sync-0001's
 *     own `main.c:1286` comment ("counts that are the same whatever the levels") was FALSE and is not
 *     repeated here -- the rule that cannot leak is not to show them, not a reasoned exemption.
 *
 * The perceptual image compiles the leaking fields OUT (GBP_V28_PLAN_PERCEPTUAL guards the print
 * call sites themselves), rather than hiding them at runtime -- see v28_screen_report()/
 * v28_live_report() below. tests/host/test_v28_leak.py proves no NEVER field's name can appear in
 * the perceptual branch's own text.
 *
 * THE GX LABEL (§7's own paragraph) IS BUILT. The earlier checkpoint's own probe tested the WRONG
 * symbol (SYS_InitFont()/SYS_GetFontTexture(), which decode the IPL ROM's own font -- empty under
 * this project's `--exec <dol>` Dolphin boot, which never loads an IPL, and says nothing about
 * hardware). §7 names "libogc2's 8x16 font", which is `console_font_8x16` -- a plain DEFINED data
 * symbol compiled INTO libogc2 itself (confirmed by `nm` over this image's own libogc.a), no IPL
 * dependency at all, and the SAME data CON_Init's own console already renders legible text from in
 * every prior Dolphin screenshot. Its layout (`extern u8 console_font_8x16[]`, one glyph every 16
 * bytes at `console_font_8x16[c * 16]`, one byte per row, bit 0x80 the leftmost pixel) is
 * `external/libogc2`'s own `libogc/console.c:87,130` and `libogc/console.h`'s `FONT_XSIZE 8` /
 * `FONT_YSIZE 16` -- and, since this image's own libogc2 (r2442.094b250) predates that checkout
 * (ca03fb7) and cannot be diffed directly, VERIFIED ON THE BYTES: `objdump -s` on the image's own
 * compiled `console_font_8x16.o` (extracted from `$DEVKITPRO/libogc2/gamecube/lib/libogc.a`) matches
 * `external/libogc2`'s own source array byte-for-byte at glyphs 'A' (0x410), '0' (0x300) and ':'
 * (0x3a0) -- the exact three the Orchestrator asked to spot-check.
 *
 * Rendered into a private, purpose-built 256x16 RGB5A3 double buffer (`label_tex[2]`), NOT a second
 * `gbp_vpresent` instance: that module's own state machine is coupled to XFB target selection
 * (`gbp_vpresent_xfb_target()`), which has no meaning for a texture-only label, so reusing it would
 * be a mismatch, not a simplification. Both the label's own texture and the main quad's are always
 * drawn in the SAME GX command batch and released by the SAME single draw-done token
 * (`gbp_vpresent.c:103-143`'s own one-token rule) -- `label_render()` only ever writes the buffer
 * NOT currently bound (`label_cur`), so there is never a write racing the GP's own read of the one
 * currently in flight. Re-rendered only when the label's own text differs from what is already
 * shown (`label_shown`), never every call. Opaque black background (`0x8000`), opaque white glyphs
 * (`0xFFFF`) -- no blend-mode change needed, since `GX_SetTevOp(..., GX_REPLACE)` already governs
 * both quads identically. Its own cost (this checkpoint's whole label block, in the SAME pump slot
 * the validation run measures the AHEAD margin's own refill cost in) is tracked in `label_ticks_max`/
 * `label_renders`, reported the same bounded, SD-only way every other counter in this file is.
 * The label's own TEXT obeys the SAME leak rules as the rest of the screen (`v28_label_text()`,
 * right beside `v28_screen_report()`/`v28_live_report()`, the identical plan-conditional split).
 *
 * SYNCPE, THE PHASE-EDGE GRAMMAR (§7): `SYNCPE p=<n> edge=<start|end> t=<tick> why=<reason>`,
 * `why` one of `none` (a start edge; also an end edge this build could not otherwise classify),
 * `complete` (the handler's own decision), `cap` (a phase cap), `session` (the session cap),
 * `z` (an Operator Z-hold, gbp_walker_stop() -- and ONLY that), `probe` (the run ended from OUTSIDE
 * gbp_walker -- the safety wall, a store cap, the delivery cap -- while this phase was still open;
 * distinguished from `z` by `res.stop != GBP_VSTATE_STOP_SESSION_END` at teardown, see the backstop
 * below). Emitted once per pump call, by an edge detector OUTSIDE gbp_walker.c comparing each
 * phase's own started/ended bits against the previous call's snapshot (gbp_walker_tick()'s own
 * return bits are per-TICK, not a full history, and a detector inside the module misses ends found
 * by the tap rather than tick() -- §7's own words). Admission: through sync_line_admit(), the SAME
 * ringlog-headroom gate KEYLOG/SYNCCS/SYNCP2 already use, with its OWN refusal counter
 * (syncpe_lines_lost) -- at most 8 lines for validation_run's own 4 phases x 2 edges (which already
 * ARE the 3a->3b/3b->sweep sub-edges: one phase's own end and the next phase's own start are the
 * SAME pump call's two new bits, so no separate sub-edge tag is needed; stated here rather than
 * invented silently), 4 for perceptual_no_phase1's own 2 phases. Backstop: `SYNCPH phase=<n>
 * t_start=<tick> t_end=<tick> ended=<0|1> reason=<why>`, over EVERY phase index INCLUDING 0 (the
 * OLD sync-0001 bug this must not repeat, §7: its own loop started at j=1u), emitted once per phase
 * after gbp_vstate_probe_run() returns -- this is what actually classifies `why=probe` (a phase left
 * `started && !ended` when the whole run ended is, structurally, ended by something outside
 * gbp_walker; if `res.stop == GBP_VSTATE_STOP_SESSION_END`, gbp_walker itself already recorded a
 * COMPLETE/PHASE_CAP/SESSION_CAP/STOP end before the run could return, so this case can only be a
 * probe-level stop -- confirmed against gbp_vstate_probe.h's own stop-reason enum before writing
 * this). The missing live SYNCPE end-edge for that phase is also emitted here, once, so a live
 * parser and the post-run summary agree.
 *
 * `chunk_corrections` (§5/§6): a DEDICATED store, 2 B/record (struct v28_corr_record), sized per
 * plan at wall_s x GUARD_CORR_PER_S(39) records (tools/v28budget.py) -- 19617 (validation_run),
 * 16575 (perceptual_no_phase1) -- NEVER folded into the misc-events store (§6's own trap: sharing
 * it caps the wall at 167.8 s, short of both plans' walls by a wide margin). Fed once per produced
 * chunk from gbp_aplay2's own `chunk_corrections` field (a per-chunk delta, valid once
 * gbp_aplay2_produce()/gbp_atrans2_step()'s own *to_queue returns >= 0). This checkpoint keeps the
 * per-chunk values in this RAM arena (the budget's own concern: a store that does not compete with
 * the misc-events stream) and logs a bounded SD summary (SYNCCORR) at session end, not a full
 * per-record text dump -- the store's own job is the memory-budget accounting §6 asks for, not a
 * text sidecar this Issue never asked to be built.
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
#include "gbp_atrans2.h"
#include "gbp_walker.h"
#include "gbp_v28_ladder.h"
#include "gbp_v28_plans.h"
#include "gbp_v28_3a.h"
#include "gbp_v28_3b.h"
#include "gbp_v28_sweep.h"
#include "gbp_v28_nulling.h"
#include "gbp_v28_step.h"
#include "gbp_v28_dma.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-audio-v28"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-AUDIO-V28"

#if (defined(GBP_V28_PLAN_VALIDATION) + defined(GBP_V28_PLAN_PERCEPTUAL) + defined(GBP_V28_PLAN_DIAG_3A_STALL) + \
     defined(GBP_V28_PLAN_DIAG_LOSS)) > 1
#error "exactly one of GBP_V28_PLAN_VALIDATION / GBP_V28_PLAN_PERCEPTUAL / GBP_V28_PLAN_DIAG_3A_STALL / GBP_V28_PLAN_DIAG_LOSS must be defined"
#endif
#if !defined(GBP_V28_PLAN_VALIDATION) && !defined(GBP_V28_PLAN_PERCEPTUAL) && !defined(GBP_V28_PLAN_DIAG_3A_STALL) && \
    !defined(GBP_V28_PLAN_DIAG_LOSS)
#error "the Makefile must define exactly one of GBP_V28_PLAN_VALIDATION / GBP_V28_PLAN_PERCEPTUAL / GBP_V28_PLAN_DIAG_3A_STALL / GBP_V28_PLAN_DIAG_LOSS"
#endif

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT " OPENGBP_APP_NAME " " OPENGBP_BUILD_ID " " OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1

/* ---- the ringlog (Issue #39 sizing, unchanged discipline from sync-0001) -------------------- */
#define LOG_LINES 8192
#define LOG_LINE_LEN 256
#define DMA_TIMEOUT_MS 200
#define KEYLOG_TAIL_RESERVE 1280u

/* ---- the plan's own wall (tools/v28budget.py: wall_s = session_cap_s + WALL_ABOVE_SESSION_S(65)),
 * and the stores sized at its own guard rates (§6, AWR dropped in both -- the "without" figures) --
 * NOT sync-0001's own 785 s / 720 s, which were §V27's, not §V28's. */
#if defined(GBP_V28_PLAN_PERCEPTUAL)
#define V28_SESSION_CAP_S   GBP_V28_PERCEPTUAL_NO_PHASE1_CAP_S   /* 360 */
#define V28_WALL_S          425u
#define PLAY_EVENT_RECORDS  33575u
#define PLAY_FRAME_RECORDS  25500u
#define CORR_CAP            16575u
#elif defined(GBP_V28_PLAN_DIAG_LOSS)
#define V28_SESSION_CAP_S   GBP_V28_DIAG_LOSS_CAP_S              /* 468, Issue #137: the same cap as validation_run, so the
                                                                    * stores below are already sized for it */
#define V28_WALL_S          533u
#define PLAY_EVENT_RECORDS  42107u
#define PLAY_FRAME_RECORDS  31980u
#define CORR_CAP            20787u
#else
#define V28_SESSION_CAP_S   GBP_V28_VALIDATION_RUN_CAP_S         /* 468, Issue #131/#133: 3a's own budget
                                                                    * 138 -> 168 (Defect B) */
#define V28_WALL_S          533u
#define PLAY_EVENT_RECORDS  42107u
#define PLAY_FRAME_RECORDS  31980u
#define CORR_CAP            20787u
#endif
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

/* ---- the GX label (Issue #128 §7): a private double buffer, released by the SAME draw-done token
 * as the main quad -- see the file header's own comment for why this is not a second gbp_vpresent
 * instance. libogc2's own 8x16 font (libogc/console.c:87, verified on this image's own bytes,
 * see the header). */
extern u8 console_font_8x16[];
#define GBP_V28_LABEL_W       256u
#define GBP_V28_LABEL_H        16u
#define GBP_V28_LABEL_CHARS   (GBP_V28_LABEL_W / 8u)   /* 32, an 8-pixel-wide glyph each */
#define GBP_V28_LABEL_BG   0x8000u   /* opaque (bit15) RGB555 black */
#define GBP_V28_LABEL_FG   0xFFFFu   /* opaque (bit15) RGB555 white */
static uint16_t label_tex[2][GBP_V28_LABEL_W * GBP_V28_LABEL_H] ATTRIBUTE_ALIGN(32);   /* 2 x 8192 B */
static GXTexObj label_tex_obj;
static uint32_t label_cur;                        /* which of label_tex[2] is bound/submitted now */
static char label_shown[GBP_V28_LABEL_CHARS + 1];  /* the text label_tex[label_cur] actually holds */
static uint32_t label_renders;                     /* re-renders (text actually changed), not calls */
static uint32_t label_ticks_last, label_ticks_max; /* this checkpoint's own cost, in the pump slot */

_Static_assert(GBP_V28_LABEL_W * GBP_V28_LABEL_H * 2u == 8192u, "one label buffer is 8192 B (16384 B, both)");

/* GX_TF_RGB5A3 is NOT raster order: 4x4-texel tiles, left to right then top to bottom, the four
 * rows of a tile consecutive (src/gbp/gbp_vpix.c's own gbp_vpix_tile_index(), the same permutation,
 * parameterised by this label's own width instead of GBP_VPIX_WIDTH -- found the hard way, on a
 * screenshot: a flat `dst[y*W+x]` write renders as shuffled 4x4 blocks, not text). */
static size_t label_tile_index(uint32_t x, uint32_t y)
{
    const uint32_t tiles_x = GBP_V28_LABEL_W / 4u;
    const uint32_t tx = x / 4u, ty = y / 4u, ix = x % 4u, iy = y % 4u;
    const size_t tile = (size_t)ty * tiles_x + tx;
    return tile * 16u + (size_t)iy * 4u + ix;
}

/* Renders `text` (at most GBP_V28_LABEL_CHARS characters, silently truncated beyond that -- the
 * label is a bounded fixed-width strip, not a scroll) into `label_tex[buf]`. One byte per glyph row
 * (console_font_8x16[c * 16 + row]), bit 0x80 the LEFTMOST pixel (libogc/console.c:139-160's own
 * FONT_XSIZE==8 case). Opaque background first, so a shorter string does not show the PREVIOUS
 * frame's own trailing glyphs -- a flat fill needs no tile mapping, every element gets the same
 * value regardless of order. */
static void label_render(uint32_t buf, const char *text)
{
    uint32_t x, y, i;
    uint16_t *dst = label_tex[buf];
    for (i = 0; i < GBP_V28_LABEL_W * GBP_V28_LABEL_H; i++) dst[i] = GBP_V28_LABEL_BG;
    for (i = 0; text[i] != '\0' && i < GBP_V28_LABEL_CHARS; i++) {
        const uint8_t *glyph = &console_font_8x16[(uint32_t)(uint8_t)text[i] * 16u];
        for (y = 0; y < 16u; y++) {
            const uint8_t row = glyph[y];
            for (x = 0; x < 8u; x++)
                if (row & (0x80u >> x)) dst[label_tile_index(i * 8u + x, y)] = GBP_V28_LABEL_FG;
        }
    }
}

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

/* The label's own quad: top-centre of the black border, well clear of the 240x160 game quad
 * draw_quad() above centres (border height on each side is (efbHeight-160)/2, comfortably >16px
 * at every mode this project targets).
 *
 * RUN 48 (Issue #131): the Operator read "P2/4" as "F2/4" -- his TV cuts the top of the picture,
 * and y0 = 8.0f sat inside that cut. A fixed 8px offset assumes no overscan at all, which no real
 * CRT/composite/S-Video display gives. The margin assumed here is the standard 10% broadcast
 * title-safe inset (SMPTE RP 218 / the convention libogc's own examples use), applied to
 * efbHeight -- e.g. 48px at the common NTSC efbHeight of 480, comfortably clear of any ordinary
 * overscan and still well above the 240x160 game quad's own top border. */
static void draw_label_quad(void)
{
    const f32 w = (f32)GBP_V28_LABEL_W, h = (f32)GBP_V28_LABEL_H;
    const f32 x0 = ((f32)rmode->fbWidth - w) * 0.5f;
    const f32 y0 = (f32)rmode->efbHeight * 0.10f;

    GX_Begin(GX_QUADS, GX_VTXFMT0, 4);
        GX_Position2f32(x0,     y0);     GX_TexCoord2f32(0.0f, 0.0f);
        GX_Position2f32(x0 + w, y0);     GX_TexCoord2f32(1.0f, 0.0f);
        GX_Position2f32(x0 + w, y0 + h); GX_TexCoord2f32(1.0f, 1.0f);
        GX_Position2f32(x0,     y0 + h); GX_TexCoord2f32(0.0f, 1.0f);
    GX_End();
}

static void submit_ready(int buf, struct gbp_vqueue *account);
static void offer_oldest_ready(void);
static void v28_label_text(char *out, size_t cap, uint64_t now);

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

static struct gbp_atrans2 tr;
static struct gbp_walker walker;
static struct gbp_v28_3a s3a;
static struct gbp_v28_3b s3b;
static struct gbp_v28_sweep sweep;
static struct gbp_v28_nulling nulling;

/* Issue #128/#129/#130, Amendment 1 on #131's own freeze: 3b holds AHEAD at the nearest perceptual
 * ladder rung at or above 3a's own confirmed floor, never at 3a's own raw floor directly (see
 * gbp_v28_anchor()'s own header comment, gbp_v28_ladder.h). Computed once at the 3a -> 3b
 * transition (below); `v28_anchor_computed` distinguishes "not yet computed" from a genuine
 * source=RULE(0) result, since both would otherwise read as an all-zero struct. */
static struct gbp_v28_anchor v28_anchor;
static uint8_t v28_anchor_computed;

/* Issue #131/#133 (RUN 50, Defect A): the walker's own phase INDEX a handler start has already
 * been issued for -- see v28_dispatch_phase_start() below, defined once walker/v28_cut() exist. */
static uint32_t v28_started_phase_index;

static const struct gbp_walker_plan *const V28_PLAN =
#if defined(GBP_V28_PLAN_PERCEPTUAL)
    &GBP_V28_PERCEPTUAL_NO_PHASE1;
#elif defined(GBP_V28_PLAN_DIAG_3A_STALL)
    &GBP_V28_DIAG_3A_STALL;
#elif defined(GBP_V28_PLAN_DIAG_LOSS)
    &GBP_V28_DIAG_LOSS;
#else
    &GBP_V28_VALIDATION_RUN;
#endif

static uint32_t sync_seed;
static int sync_started;
static uint32_t sync_lines_lost;             /* SYNCCS/SYNCPE admission refusals, together (mirrors sync-0001's
                                               * own single counter for this class of SD-only line) */
static uint32_t syncpe_lines_lost;
static uint8_t syncpe_started_seen[GBP_WALKER_MAX_PHASES], syncpe_ended_seen[GBP_WALKER_MAX_PHASES];
static uint32_t cs_events, cs_acted;          /* SD-only counters (never printed/gecko'd) */
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

/* ---- Issue #137 (U-GBP-050): the LOSS diagnostic's instruments. ONLY in the diag_loss image: every other plan compiles none
 * of this, so validation_run and the perceptual image keep their own timing byte for byte. The handler (gbp_v28_loss.h) decides
 * the cell; this file applies it (the label block of submit_ready, ap2.step_pushes) and measures: ticks around the tap, its
 * decode, each production call, the whole pump call and the label block, and the gap between taps. */
#if defined(GBP_V28_PLAN_DIAG_LOSS)
static struct gbp_v28_loss loss;
static struct gbp_v28_hist loss_hist[GBP_V28_NHIST];
static struct gbp_v28_loss_ctr loss_ctr;
#define V28_LABEL_ON()          (loss.label_off == 0u)
#define V28_TICKS(var)          const uint32_t var = (uint32_t)gettick()
#define V28_NOTE(id, t0)        gbp_v28_hist_note(&loss_hist[(id)], (uint32_t)gettick() - (t0))
static void loss_gap_note(uint64_t d)
{
    gbp_v28_hist_note(&loss_hist[GBP_V28_H_GAP], d > 0xFFFFFFFFull ? 0xFFFFFFFFu : (uint32_t)d);
}
/* the step arm: the SAME pushes, partitioned into calls of 128 (production) or 64 (RUN 40's half-size step) */
static uint32_t loss_step_pushes(void *user, uint32_t seq)
{
    (void)user;
    (void)seq;
    return loss.step_half ? GBP_V28_LOSS_STEP_HALF : GBP_V28_LOSS_STEP_FULL;
}
#else
#define V28_LABEL_ON()          1
#define V28_TICKS(var)
#define V28_NOTE(id, t0)
#define loss_gap_note(d)        ((void)0)
#endif
static uint64_t t_ai_start, t_ai_stop;
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

/* ---- Issue #139 (U-GBP-049): THE AI DMA'S HAND-OFF SEMANTICS, READ -- NEVER WRITTEN. ------------------------------------------------------------------
 * The latency table L(T, A) counts AHEAD + 1 chunks in flight (AHEAD - 1 READY, the chunk PROGRAMMED at the last hand-off, the chunk that hand-off STARTED). That rests
 * on one assumption no run has measured: the callback fires when the block programmed LAST time has just STARTED, and programs the next. If it were wrong every L is a
 * whole chunk (31.2 ms) off, in a direction the measurement gives. At every callback's ENTRY, before the hand-off and before AUDIO_InitDMA, this reads the AI DMA's
 * start-address register and its bytes-left counter (libogc: two loads of the DSP registers) and compares the address with the chunks the previous two callbacks
 * returned. Nothing is written to the device; the callback's own behaviour is unchanged; everything else is bounded static stores, printed only at teardown
 * (V28DMA / V28DMAR, SD log only, never the screen). Pre-registered readings, HARDWARE_TESTS.md V28.23:
 *   address == the chunk returned at the PREVIOUS callback, bytes left near 4 000 (the block has just started)  -> AHEAD + 1 (the table stands);
 *   address == the chunk returned TWO callbacks ago                                                             -> AHEAD + 2 (every L +31.2 ms);
 *   address == the previous chunk but bytes left near 0 (the block has just FINISHED, nothing playing)          -> AHEAD (every L -31.2 ms). */
static struct gbp_v28_dma v28_dma;      /* zero + left_min at the maximum: gbp_v28_dma_init() in main(), before the DMA can start */

/* THE AI DMA CALLBACK -- interrupt context, native handoff. Issue #139: the two register READS come first, before anything else, and the hand-off and AUDIO_InitDMA are
 * exactly what they were. */
static void live_dma_cb(void)
{
    const uint32_t dma_addr = (uint32_t)AUDIO_GetDMAStartAddr();
    const uint32_t dma_left = (uint32_t)AUDIO_GetDMABytesLeft();
    const uint64_t t = gettime();
    const uint8_t *c = gbp_aplay2_irq_handoff(&ap2, t);
    gbp_v28_dma_note(&v28_dma, dma_addr, dma_left, t, c);
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

/* ---- the screen, before the session (SAFE: Phase 0's own name/clock, unchanged prompt text) --- */
static void live_screen(uint64_t now)
{
    if (!live_drawn_prompt && live.t_accept && now >= live.t_accept && live.phase == GBP_ALIVE_PROMPT) {
        live_drawn_prompt = 1;
        printf("\x1b[8;0H");
        printf("  >>> PRESS A within 45 s: the game appears. Then follow the checklist (C-stick). <<<  ");
    }
    if (!live_drawn_press && live.phase == GBP_ALIVE_DELAY) {
        live_drawn_press = 1;
        printf("\x1b[10;0H");
        printf("  A RECEIVED. The game appears now. C-stick DOWN = next phase.                         ");
        printf("\x1b[11;0H");
#if defined(GBP_V28_PLAN_PERCEPTUAL)
        printf("  Nulling: LEFT/RIGHT step, UP confirm. Hold Z 1/4 s = end. X only at the end.          ");
#else
        printf("  Automatic from here. Hold Z 1/4 s = end early. X only at the end.                     ");
#endif
    }
}

/* ---- §V28's C-stick: DOWN ends navigate in BOTH images; LEFT/RIGHT/UP are live ONLY while
 * nulling is the walker's current phase (Issue #128 section 7, the Orchestrator's own answer).
 * A press outside those two cases is a structural no-op (the guards below), never "acted" --
 * exactly what the perceptual image's own blinding needs: nothing here can print or gecko_puts,
 * and cs_events/cs_acted are SD-only counters, never read by v28_screen_report()/v28_live_report(). */
#define CS_THRESHOLD GBP_INPUT_POLICY_STICK_THRESHOLD
#define CS_DEAD_MS   250u
enum cs_dir { CS_NONE = 0, CS_UP, CS_DOWN, CS_LEFT, CS_RIGHT };
static enum cs_dir cs_last;
static uint64_t cs_dead_until;
static uint32_t cs_ignored_dead;

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

static enum cs_dir cs_edge(uint64_t now)
{
    enum cs_dir d = cs_read(PAD_SubStickX(PAD_CHAN0), PAD_SubStickY(PAD_CHAN0));
    enum cs_dir out = CS_NONE;
    if (d != CS_NONE && cs_last == CS_NONE) {
        if (now >= cs_dead_until) {
            out = d;
            cs_dead_until = now + ((uint64_t)live.tb_hz * CS_DEAD_MS) / 1000u;
        } else {
            cs_ignored_dead++;
        }
    }
    cs_last = d;
    return out;
}

static int sync_line_admit(void)
{
    if (keylog_rl && gbp_input_keylog_admit((uint32_t)keylog_rl->count, (uint32_t)keylog_rl->capacity, KEYLOG_TAIL_RESERVE))
        return 1;
    sync_lines_lost++;
    return 0;
}

static void v28_control(uint64_t now)
{
    const enum cs_dir d = cs_edge(now);
    int acted = 0;
    enum gbp_walker_kind kind;
    if (d == CS_NONE) return;
    cs_events++;
    kind = gbp_walker_current_kind(&walker);
    if (d == CS_DOWN) {
        if (kind == GBP_WALKER_NAVIGATE)
            /* Issue #131 (RUN 48): starting whatever phase this lands in is NOT done here any
             * more -- see v28_dispatch_phase_start()'s own header comment for why a per-caller
             * start is exactly the defect RUN 50 (Issue #133) found for 3a -> 3b: reachable on
             * only ONE of navigate's own two exit paths (a press, here; the walker's own 60 s
             * allowance cap, which never ran through this function at all). */
            acted = gbp_walker_phase_complete(&walker, now, tr.active);
    } else if (kind == GBP_WALKER_NULLING) {
        if (d == CS_LEFT) acted = gbp_v28_nulling_step(&nulling, &tr, &ap2, &adec2, now, GBP_V28_NULLING_LEFT);
        else if (d == CS_RIGHT) acted = gbp_v28_nulling_step(&nulling, &tr, &ap2, &adec2, now, GBP_V28_NULLING_RIGHT);
        else if (d == CS_UP) acted = gbp_v28_nulling_confirm(&nulling, &tr, &ap2, &adec2, now);
    }
    if (acted) cs_acted++;
    /* SD only, bounded exactly like KEYLOG: `kind`/`acted` here are the walker's own phase kind and
     * a bit, not a TARGET/AHEAD/step value -- and this line never reaches the screen or gecko_puts
     * regardless, so it is unaffected by the plan either way. */
    if (cs_events <= 400u && sync_line_admit())
        ringlog_printf(keylog_rl, "SYNCCS dir=%c kind=%u acted=%d t=%llx", "?UDLR"[d], (unsigned)kind, acted,
                       (unsigned long long)now);
}

/* Every handler that carries a dwell/hold/sweep-dwell of its own documents the SAME requirement
 * ("call BEFORE the caller advances past [3a/3b/sweep]", gbp_v28_3a.h/3b.h/sweep.h): a phase cut
 * from OUTSIDE the handler's own logic (a cap, the session cap, Z) must be reported to it before
 * the walker moves on, or an in-progress record is silently never recorded at all -- not marked
 * partial, simply absent (the adversarial review of e283aa5 found this call missing entirely).
 * Safe to call for any kind, including one with no cut()/dwell concept (navigate, nulling): the
 * default case is a no-op, and each _cut() itself is documented as inert on an already-ended
 * record. `kind` is the phase that was CURRENT before the call that may have cut it -- captured by
 * the caller, since gbp_walker_current_kind() only reads the phase in force NOW. */
static void v28_cut(enum gbp_walker_kind kind, uint64_t now)
{
    switch (kind) {
    case GBP_WALKER_DESCENT_3A:
        gbp_v28_3a_cut(&s3a, now);
        /* _cut() only MARKS the in-progress dwell (dwell_cut/depth_pending, finished=1); the actual
         * record push is _depth_done()'s own job -- a no-op here (documented, tested:
         * test_gbp_v28_3a.c's own test_a_cut_dwell_is_partial() calls both, in this order) unless
         * cut() just set depth_pending. Zeroed deltas, matching gbp_v28_sweep_cut()'s own explicit
         * precedent for a partial record: "a PARTIAL record already tells the reader not to trust
         * it as a full PASS", so the exact counters do not matter here. */
        gbp_v28_3a_depth_done(&s3a, 0u, 0u, 0u, 0u, 0u, 0u, 0u);
        break;
    case GBP_WALKER_HOLD_3B:
        gbp_v28_3b_cut(&s3b, now);
        gbp_v28_3b_hold_done(&s3b);   /* same two-step contract as 3a, see above */
        break;
    case GBP_WALKER_SWEEP:
        gbp_v28_sweep_cut(&sweep, now);   /* self-contained: writes the record itself, no follow-up call */
        break;
    case GBP_WALKER_LOSS:
#if defined(GBP_V28_PLAN_DIAG_LOSS)
        v28_snapshot(&loss_ctr);
        gbp_v28_loss_cut(&loss, now, &loss_ctr, loss_hist);
        if (loss.hold_pending) gbp_v28_loss_hold_done(&loss);   /* the same two-step contract as 3a and 3b; a cut with no hold
                                                                    * running (an entry, between holds) owes nothing */
#else
        (void)now;
#endif
        break;
    default: break;
    }
}

/* Issue #131/#133: RUN 50 (Defect A) -- 3a's own exit into 3b was cut by 3a's own phase cap, not
 * completed by 3a's own algorithm, so the anchor computation and gbp_v28_3b_start() (which sat
 * ONLY inside DESCENT_3A's own `f & GBP_V28_3A_TICK_PHASE_COMPLETE` branch) never ran: 3b sat at
 * its own zero-init state for its whole 120 s phase, the same shape as RUN 48's original "no
 * handler was ever started" defect, just one exit path narrower. "A start reachable on only one
 * of two exit paths is the same shape as a start reachable on no path" (the Orchestrator's own
 * framing) -- so every handler start in this POC is now issued from exactly ONE place, driven
 * off the WALKER's own phase index advancing, never a specific handler's own completion flag or
 * a specific caller (a button press, a TICK_PHASE_COMPLETE bit).
 *
 * gbp_walker.c's own begin_phase() is the ONLY place `walker.index` ever changes, and it always
 * runs inside end_current_and_advance() -- called for BOTH a phase cap (gbp_walker_tick()) and a
 * handler's own gbp_walker_phase_complete() -- never for the session cap or a stop
 * (end_current_and_finish(), which ends the WHOLE walk without touching `index`, correctly
 * dispatching nothing here since there is no next phase to start). So "index changed since the
 * start last issued" is exactly "a new phase needs its own start()", independent of why the
 * previous one ended.
 *
 * MUST run before ANY tick() call for the new phase, every time -- not next tick, not "close
 * enough". gbp_v28_3a_tick()/gbp_v28_3b_tick() both no-op safely on all-zero (never-started)
 * state (tested: tests/unit/test_gbp_v28_3a.c's/test_gbp_v28_3b.c's own "never started" cases),
 * so a transition landing inside live_step()'s own main switch on the SAME tick it happens (the
 * cap-cut path: gbp_walker_tick() advances `index` before that switch reads
 * gbp_walker_current_kind()) costs at most one harmless no-op call there. gbp_v28_sweep_tick()
 * does NOT have that property: on unstarted state (begin_pending==0, dwelling==0) its own "not
 * dwelling yet" branch does not require begin_pending to have been set, so it silently skips
 * move 0's own gbp_atrans2_begin() and dwells on whatever transport state already exists --
 * RUN 48's own n=0 record (outcome=2 fail=1 residue=0) is exactly that artifact. This function is
 * therefore called from live_step() AFTER every call that could advance the walker this tick
 * (gbp_walker_tick()'s own cap check, a handler's own gbp_walker_phase_complete(), v28_control()'s
 * NAVIGATE dispatch) and BEFORE the sweep-tick call below -- so sweep is ALWAYS started before
 * its own first tick(), on every exit path that leads to it, not only the one RUN 48/50 happened
 * to exercise.
 *
 * tests/host/test_v28_plans.py's TheHandlersAreStarted now checks, structurally, that each
 * KIND_START_FN has EXACTLY ONE call site in main.c and that it sits inside this function's own
 * body -- the general, durable form of today's lesson: a start conditioned on a specific exit
 * reason is the same defect shape whether it currently has zero reachable paths or one. */
/* Issue #138 (RUN 55): 3a's per-depth deltas are taken against this snapshot, and it is RE-TAKEN when 3a starts. It used to be a function-local static that
 * began at zero, so 3a's first row counted from boot and carried navigate's underrun and 13 088 `dup` (RUN 55: row n=0 `dup` 16 191 against about 3 100
 * of its own, session underruns 2 against p0 1 + rows 2). */
static uint32_t d0_underruns, d0_overflow, d0_dup, d0_drop, d0_ring_gated;

static void v28_dispatch_phase_start(uint64_t now)
{
    if (gbp_walker_finished(&walker) || walker.index == v28_started_phase_index) return;
    v28_started_phase_index = walker.index;
    switch (gbp_walker_current_kind(&walker)) {
    case GBP_WALKER_DESCENT_3A:
        gbp_v28_3a_start(&s3a, live.tb_hz, now);
        d0_underruns = (uint32_t)ap2.underruns; d0_overflow = (uint32_t)adec2.overflow; d0_dup = (uint32_t)ap2.dup;
        d0_drop = (uint32_t)ap2.drop; d0_ring_gated = (uint32_t)ap2.ring_gated;       /* the first row starts HERE, not at boot */
        break;
    case GBP_WALKER_HOLD_3B: {
        /* 3a's own confirmed floor (Amendment 1, corrected at the Orchestrator's own freeze
         * review): gbp_v28_3a_confirmed_floor() -- the LOWEST HOLDING depth, never s3a.lo
         * directly (gbp_v28_3a.h's own header comment). Computed HERE, exactly once, at the
         * moment 3b is about to start: by construction 3a is already `finished` however this
         * point was reached (its own algorithm, gbp_v28_3a_cut()+depth_done() via v28_cut() for
         * a cap/session-cap/stop), so this reads the SAME final state regardless of which exit
         * path got us here -- never only the one 3a's own TICK_PHASE_COMPLETE branch used to
         * gate it on. */
        uint32_t floor_native = 0u;
        const int has_floor = gbp_v28_3a_confirmed_floor(&s3a, &floor_native);
        v28_anchor = gbp_v28_anchor(floor_native, has_floor);
        v28_anchor_computed = 1u;
        if (v28_anchor.source != GBP_V28_ANCHOR_NONE)
            gbp_v28_3b_start(&s3b, v28_anchor.target, live.tb_hz, now);
        /* GBP_V28_ANCHOR_NONE (the floor sits above T704, no ladder rung reaches it): 3b does not
         * hold at all -- gbp_v28_3b_start() is never called, s3b stays its own zero-initialised
         * state (holds_n==0, no V28_3B records), and the V28ANCHOR line (teardown, below) is the
         * ONLY record of this finding. */
        break;
    }
    case GBP_WALKER_SWEEP:
        gbp_v28_sweep_start(&sweep, live.tb_hz, now);
        break;
    case GBP_WALKER_NULLING:
        (void)gbp_v28_nulling_start(&nulling, &tr, &ap2, &adec2, now, sync_seed);
        break;
    case GBP_WALKER_LOSS:
#if defined(GBP_V28_PLAN_DIAG_LOSS)
        gbp_v28_loss_start(&loss, live.tb_hz, now);
#endif
        break;
    case GBP_WALKER_NAVIGATE:
    default:
        break;
    }
}

/* ---- SYNCPE: the phase-edge grammar (see the file header) ------------------------------------ */
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

#if defined(GBP_V28_PLAN_DIAG_3A_STALL)
/* Issue #131 (RUN 48's own diagnostic build): the same phase-edge slot SYNCPE already prints
 * from -- nothing here is timing-critical, it is read once per edge, the same as SYNCPE's own
 * lines. Answers, per edge: was the hand-off callback ever running (handed/mute_handed); did
 * production keep up (produced/dropped_front, target/ahead/ready, free pool); did 3a's own first
 * begin() ever land (begin_refused_active, s3a's own begin_pending_ticks); and when DMA actually
 * started/stopped (ai_started/ai_stopped, t_ai_start/t_ai_stop) -- the one question the
 * Orchestrator's own review named as mattering most.
 *
 * ONLY IN THIS PLAN: validation_run and perceptual_no_phase1 are untouched by this whole block --
 * their own SYNCPE lines and log format stay byte for byte what they were, per the Orchestrator's
 * own instruction not to disturb validation_run while this is under diagnosis. */
static void v28diag_edge(uint32_t p, const char *edge, uint64_t t)
{
    uint32_t free_pool = 0u, k;
    for (k = 0; k < GBP_APLAY2_POOL; k++)
        if (ap2.state[k] == GBP_APLAY2_FREE) free_pool++;
    ringlog_printf(keylog_rl,
                   "V28DIAG p=%lu edge=%s t=%llx handed=%lu mute_handed=%lu produced=%lu dropped_front=%lu "
                   "target=%lu ahead=%lu ready=%lu free_pool=%lu begin_refused=%lu begin_pending_ticks=%lu "
                   "ai_started=%u ai_stopped=%u t_ai_start=%llx t_ai_stop=%llx",
                   (unsigned long)p, edge, (unsigned long long)t,
                   (unsigned long)ap2.handed, (unsigned long)ap2.mute_handed, (unsigned long)ap2.produced,
                   (unsigned long)ap2.dropped_front, (unsigned long)ap2.target, (unsigned long)ap2.ahead,
                   (unsigned long)gbp_aplay2_ready(&ap2), (unsigned long)free_pool,
                   (unsigned long)tr.begin_refused_active, (unsigned long)s3a.begin_pending_ticks,
                   (unsigned int)ai_started, (unsigned int)ai_stopped,
                   (unsigned long long)t_ai_start, (unsigned long long)t_ai_stop);
}
#endif /* GBP_V28_PLAN_DIAG_3A_STALL */

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
#if defined(GBP_V28_PLAN_DIAG_3A_STALL)
            if (sync_line_admit())
                v28diag_edge(i, "start", r->t_start);
            else
                syncpe_lines_lost++;
#endif
        }
        if (r->ended && !syncpe_ended_seen[i]) {
            syncpe_ended_seen[i] = 1u;
            v28_phase_snap_take(&ph_end[i]);
            if (sync_line_admit())
                ringlog_printf(keylog_rl, "SYNCPE p=%lu edge=end t=%llx why=%s", (unsigned long)i,
                               (unsigned long long)r->t_end, syncpe_why(r->reason));
            else
                syncpe_lines_lost++;
#if defined(GBP_V28_PLAN_DIAG_3A_STALL)
            if (sync_line_admit())
                v28diag_edge(i, "end", r->t_end);
            else
                syncpe_lines_lost++;
#endif
        }
    }
}

/* Issue #137: how many underruns the AI DMA callback has counted since the last call (read from the pump slot only; the counter is
 * written by the callback, and a 32-bit aligned load is atomic on the Gekko). The snapshot advances whether or not a handler was
 * listening, so an underrun from an earlier phase never reads as new at the next phase's first tick. */
static uint32_t v28_underrun_new(void)
{
    static uint32_t seen;
    const uint32_t now_n = (uint32_t)ap2.underruns;
    const uint32_t fresh = now_n - seen;
    seen = now_n;
    return fresh;
}

static void live_step(void)
{
    const struct gbp_transport *t = in_transport;
    uint64_t now;
    int b;
    if (!t || !in_state.base) return;
    now = t->ticks64(t->ctx);
    gbp_alive_buttons(&live, now, (uint16_t)(PAD_ButtonsHeld(PAD_CHAN0) & 0xFFFFu));

    if (sync_started && !gbp_walker_finished(&walker)) {
        int wflags = 0;
        if (session.end_requested && z_can_act) {
            const enum gbp_walker_kind kind_before = gbp_walker_current_kind(&walker);
            wflags = gbp_walker_stop(&walker, now, tr.active);   /* Z: end the WHOLE walk (gbp_walker's own
                                                                    * semantics -- not gbp_async's "next phase") */
            if (wflags) v28_cut(kind_before, now);               /* applied (not refused busy): report the cut */
            z_can_act = 0;
        }
        if (!(PAD_ButtonsHeld(PAD_CHAN0) & PAD_BUTTON_Z)) { z_can_act = 1; session.end_requested = 0; }
        if (!(wflags & GBP_WALKER_TICK_FINISHED)) {
            const int active = tr.active;
            const enum gbp_walker_kind kind_before = gbp_walker_current_kind(&walker);
            /* Issue #137: the AI underrun counter's edge, read ONCE a slot whatever the phase, so the snapshot never lags a
             * phase behind (an underrun from an earlier phase must not read as new at the next phase's first tick) */
            const uint32_t underrun_now = v28_underrun_new();
            int tick_flags = gbp_walker_tick(&walker, now, active);
            /* gbp_walker_tick() only ever advances on TIMING (a phase/session cap): the handler's
             * own gbp_walker_phase_complete() calls below are the ONLY other way a phase ends, and
             * they are not this call -- so a PHASE_END bit here is always a cut, never a complete. */
            if (tick_flags & GBP_WALKER_TICK_PHASE_END) v28_cut(kind_before, now);
            switch (gbp_walker_current_kind(&walker)) {
            case GBP_WALKER_DESCENT_3A: {
                int f;
                /* Issue #137: the handler header's contract ("call whenever the caller observes underruns_total
                 * increase") had NO caller in this file until now -- a "clean" dwell was UNOBSERVED, not clean.
                 * The edge is read once a slot (above), before the tick that could end the dwell. */
                if (underrun_now) gbp_v28_3a_underrun_observed(&s3a, now);
                f = gbp_v28_3a_tick(&s3a, &tr, &ap2, &adec2, now);
                if (f & GBP_V28_3A_TICK_DEPTH_DONE) {
                    /* the POC supplies the dwell's own counter DELTAS; this checkpoint reads them
                     * directly from gbp_aplay2/gbp_adec2's cumulative counters at depth_done() time
                     * against the previous depth's own snapshot -- gbp_v28_3a itself tracks none of
                     * this (its own header: "this module reads no device"). */
                    gbp_v28_3a_depth_done(&s3a, 0u, ap2.underruns - d0_underruns, adec2.overflow - d0_overflow,
                                          ap2.dup - d0_dup, ap2.drop - d0_drop, 0u, ap2.ring_gated - d0_ring_gated);
                    d0_underruns = ap2.underruns; d0_overflow = adec2.overflow; d0_dup = ap2.dup;
                    d0_drop = ap2.drop; d0_ring_gated = ap2.ring_gated;
                }
                if (f & GBP_V28_3A_TICK_PHASE_COMPLETE)
                    /* Issue #131/#133 (RUN 50, Defect A): the anchor computation and
                     * gbp_v28_3b_start() used to live here, reachable ONLY when 3a's own
                     * algorithm decided this bit -- never when the walker's own phase cap cut 3a
                     * instead, which is exactly what RUN 50 hit. Both now happen in
                     * v28_dispatch_phase_start(), driven off the walker's own index advancing
                     * (below v28_cut()'s own definition), on every exit path alike. */
                    (void)gbp_walker_phase_complete(&walker, now, tr.active);
                break;
            }
            case GBP_WALKER_HOLD_3B: {
                int f;
                if (underrun_now) gbp_v28_3b_underrun_observed(&s3b, now);   /* Issue #137, see 3a's case */
                f = gbp_v28_3b_tick(&s3b, &tr, &ap2, &adec2, now);
                if (f & GBP_V28_3B_TICK_HOLD_DONE) gbp_v28_3b_hold_done(&s3b);
                if (f & GBP_V28_3B_TICK_PHASE_COMPLETE)
                    /* Issue #131/#133: the same move as 3a's own just above -- gbp_v28_sweep_start()
                     * used to live here, reachable only on 3b's own completion, never a cap cut.
                     * Now v28_dispatch_phase_start()'s own job, same as every other handler. */
                    (void)gbp_walker_phase_complete(&walker, now, tr.active);
                break;
            }
            case GBP_WALKER_SWEEP: {
                /* gbp_v28_sweep's own contract: call it AFTER this same tick's own produce/step below
                 * (its landing check reads the ring/READY level, which the pump slot's own call moves) --
                 * so the sweep dispatch happens further down, not here. */
                break;
            }
            case GBP_WALKER_LOSS: {
#if defined(GBP_V28_PLAN_DIAG_LOSS)
                /* Issue #137: the handler decides the cell and the entries, this file applies the arms and measures.
                 * Ticked BEFORE the slot's own produce/step call below (the entry's landing is read from tr.active). */
                int f;
                v28_snapshot(&loss_ctr);
                {
                    uint32_t u;
                    for (u = 0u; u < underrun_now && u < 64u; u++) gbp_v28_loss_underrun_observed(&loss, now);
                }
                f = gbp_v28_loss_tick(&loss, &tr, &ap2, &adec2, now, &loss_ctr, loss_hist);
                if (f & GBP_V28_LOSS_TICK_HOLD_DONE) gbp_v28_loss_hold_done(&loss);
                if (f & GBP_V28_LOSS_TICK_PHASE_COMPLETE) (void)gbp_walker_phase_complete(&walker, now, tr.active);
#endif
                break;
            }
            case GBP_WALKER_NULLING:
            case GBP_WALKER_NAVIGATE:
            default:
                break;
            }
            (void)tick_flags;
            (void)underrun_now;
        }
        v28_control(now);
        syncpe_edges();
        /* Issue #131/#133: AFTER every call above that could have advanced the walker's own
         * index this tick (gbp_walker_tick()'s own cap check, a handler's own
         * gbp_walker_phase_complete() inside the switch just above, v28_control()'s NAVIGATE
         * dispatch), and BEFORE the sweep-tick call below -- see v28_dispatch_phase_start()'s own
         * header comment for why that ordering is load-bearing, not stylistic. */
        v28_dispatch_phase_start(now);
        if (gbp_walker_finished(&walker)) live_end = 1;
    } else if (session.end_requested) {
        live_end = 1;
    }

    if (live.phase == GBP_ALIVE_WINDOW || (sync_started && !gbp_walker_finished(&walker) && live.phase == GBP_ALIVE_DONE)) {
        if (tr.active) { if (gbp_atrans2_step(&tr, &ap2, &adec2, now, &b)) { /* landed this call */ } }
        else {
            V28_TICKS(prod_t0);
            b = gbp_aplay2_produce(&ap2, &adec2);
            V28_NOTE(GBP_V28_H_PROD, prod_t0);
        }
        if (b >= 0) {
            DCFlushRange(ap2_pool + (size_t)b * GBP_APLAY2_CHUNK_BYTES, GBP_APLAY2_CHUNK_BYTES);
            gbp_aplay2_queue(&ap2, b);
            corr_note(ap2.chunk_corrections);
        }
        gbp_aplay2_process(&ap2);
        /* sweep's own tick, AFTER the pump slot's produce/step call above (see its header comment) */
        if (sync_started && !gbp_walker_finished(&walker) && gbp_walker_current_kind(&walker) == GBP_WALKER_SWEEP) {
            const int f = gbp_v28_sweep_tick(&sweep, &tr, &ap2, &adec2, now);
            if (f & GBP_V28_SWEEP_TICK_PHASE_COMPLETE) {
                (void)gbp_walker_phase_complete(&walker, now, tr.active);
                /* RUN 51 (Issue #131/#133/#135): sweep is validation_run's own LAST phase, and this
                 * is the ONLY call site of its own completion, positioned AFTER this tick's own
                 * earlier syncpe_edges() call (above, inside the sync_started/!finished block) --
                 * so a completion landing HERE never got observed that same tick, and once it makes
                 * the walker finished, that block's own `!gbp_walker_finished(&walker)` guard shuts
                 * syncpe_edges() out forever after. The result: SYNCPE p=3 edge=end is silently
                 * never printed for ANY validation_run that reaches sweep's own natural end -- RUN
                 * 51's own raw log has the proof (SYNCPE p=3 edge=start with no matching end,
                 * SYNCPH phase=3 ended=1 reason=complete with the real timestamps, since SYNCPH's
                 * own post-run loop is a SEPARATE, unconditional walk that main.c's own comment
                 * already calls "the backstop"). The domain data was never at risk -- only this one
                 * redundant edge-log line was missing, every time, for every run that ever finishes
                 * cleanly. syncpe_edges() is idempotent (its own syncpe_started_seen/
                 * syncpe_ended_seen arrays), so calling it again here, immediately, costs nothing
                 * and closes the gap for every future run. */
                syncpe_edges();
            }
        }
        /* Issue #131: gbp_aplay2_start_ready() -- never a literal >= 2u, which is unreachable at
         * AHEAD 1 by construction (gbp_aplay2.h's own comment on it). */
        if (!ai_started && gbp_aplay2_start_ready(&ap2, adec2.count)) {
            const uint8_t *first;
            ai_started = 1;
            t_ai_start = now;
            ap2.playing = 1u;
            first = gbp_aplay2_irq_handoff(&ap2, now);
            ap2.measuring = 1u;
            gbp_v28_dma_seed(&v28_dma, first);
            AUDIO_InitDMA((u32)(size_t)first, GBP_APLAY2_CHUNK_BYTES);
            AUDIO_StartDMA();
        }
    } else if (ai_started && !ai_stopped && (live_end || (sync_started && gbp_walker_finished(&walker)))) {
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

/* ---- GX LABEL (Issue #128 §7) -- see the file header for the design and its own evidence. */
static void submit_ready(int buf, struct gbp_vqueue *account)
{
    int xfb, cur;
    uint64_t t_dec;
    uint32_t t0, t1;
    char wanted[GBP_V28_LABEL_CHARS + 1];

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

    /* the label: same GX batch, same single draw-done token as the main quad above (see the file
     * header) -- ticks counted around this whole block, the cost §7 asks to measure in this slot */
    if (V28_LABEL_ON()) {       /* Issue #137's L arm: the whole label block is skipped while it is off */
        t0 = (uint32_t)gettick();
        v28_label_text(wanted, sizeof wanted, t_dec);
        if (strncmp(wanted, label_shown, sizeof label_shown) != 0) {
            /* the OTHER buffer: label_cur is still bound to whatever the GP may still be reading until
             * THIS call's own draw-done fires -- never rewritten here */
            const uint32_t next = label_cur ^ 1u;
            label_render(next, wanted);
            DCFlushRange(label_tex[next], sizeof label_tex[next]);
            strncpy(label_shown, wanted, sizeof label_shown - 1u);
            label_shown[sizeof label_shown - 1u] = '\0';
            label_cur = next;
            label_renders++;
        }
        GX_InitTexObj(&label_tex_obj, label_tex[label_cur], GBP_V28_LABEL_W, GBP_V28_LABEL_H,
                      GX_TF_RGB5A3, GX_CLAMP, GX_CLAMP, GX_FALSE);
        GX_InitTexObjFilterMode(&label_tex_obj, GX_NEAR, GX_NEAR);
        GX_LoadTexObj(&label_tex_obj, GX_TEXMAP0);
        draw_label_quad();
        t1 = (uint32_t)gettick();
        label_ticks_last = t1 - t0;
        if (label_ticks_last > label_ticks_max) label_ticks_max = label_ticks_last;
#if defined(GBP_V28_PLAN_DIAG_LOSS)
        gbp_v28_hist_note(&loss_hist[GBP_V28_H_LABEL], label_ticks_last);
#endif
    }

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

/* ---- the screen/live report, split by plan at COMPILE TIME (Issue #128 section 7 / Amendment C):
 * the perceptual branch below is the ONLY text this build can ever print or gecko_puts about the
 * §V28 session, and it names only SAFE fields. depths/plans/acted (Amendment C) are absent from
 * BOTH branches, universally -- not only the perceptual one. tests/host/test_v28_leak.py greps
 * this exact function pair for every NEVER field. */
/* Both functions below check gbp_walker_finished() FIRST, same reason and same fix as
 * v28_label_text(): gbp_walker_current_kind() falls back to NAVIGATE once finished
 * (gbp_walker.c:110), so a naive perceptual branch would report "phase 0"/nulling=false at
 * teardown even on a session that reached NULLING and completed normally -- indistinguishable from
 * one that never started, in the one place (the post-session report) a reader most needs that
 * distinction. Found while fixing the label (Issue #128/#129/#130); the same symmetric bug, not
 * asked for by name but the identical shape, so fixed alongside it rather than left for later. */
static void v28_screen_report(void)
{
    if (gbp_walker_finished(&walker)) {
        printf("  V28     done\n");
        return;
    }
#if defined(GBP_V28_PLAN_PERCEPTUAL)
    printf("  V28     %s\n", gbp_walker_current_kind(&walker) == GBP_WALKER_NULLING ? "nulling" : "phase 0");
    if (gbp_walker_current_kind(&walker) == GBP_WALKER_NULLING)
        printf("  V28     setting %lu\n", (unsigned long)nulling.settings_n);
#else
    printf("  V28     phase %lu of %lu, running\n", (unsigned long)walker.index + 1u, (unsigned long)V28_PLAN->count);
#endif
}

static void v28_live_report(void)
{
    char line[160];
    if (gbp_walker_finished(&walker)) {
        gecko_puts("OPENGBP-V28 done\n");
        return;
    }
#if defined(GBP_V28_PLAN_PERCEPTUAL)
    snprintf(line, sizeof line, "OPENGBP-V28 phase=%s setting=%lu\n",
             gbp_walker_current_kind(&walker) == GBP_WALKER_NULLING ? "nulling" : "phase0",
             (unsigned long)nulling.settings_n);
#else
    snprintf(line, sizeof line, "OPENGBP-V28 phase=%lu of %lu finished=0\n", (unsigned long)walker.index + 1u,
             (unsigned long)V28_PLAN->count);
#endif
    gecko_puts(line);
}

/* The GX label's own text: the SAME plan-conditional split as the two functions just above --
 * never a TARGET/AHEAD figure or anything from atrans2/aplay2/adec2 in the perceptual build, only
 * the phase name, the SAFE "setting k", and a clock (elapsed seconds since the origin -- a raw tick
 * count would not be legible on a 16-pixel-tall strip). */
/* Issue #138 (RUN 54, GBP-HW-364): `H` used to change on EVERY hand-off, so the label's text changed 32 times a second and it re-rendered about 29 times a
 * second in the pump slot the drain's loss depends on (a 4.3k-tick call each; the label cost 0.41 percentage points of loss, 0.53 with the step fixed).
 * The liveness signal is a number that MOVES while hand-offs move: sampled once a second it still does (a stall is the number not changing between two
 * seconds), and the text now changes only when the clock does, so the label re-renders once a second. */
#if !defined(GBP_V28_PLAN_PERCEPTUAL)     /* the perceptual label is a clock only: it never reads ap2 */
static uint32_t label_h_second = 0xFFFFFFFFu, label_h_value;
static uint32_t label_handed_once_a_second(uint32_t elapsed_s)
{
    if (elapsed_s != label_h_second) {
        label_h_second = elapsed_s;
        label_h_value = (uint32_t)ap2.handed;
    }
    return label_h_value;
}
#endif

static void v28_label_text(char *out, size_t cap, uint64_t now)
{
    const uint32_t elapsed_s = live.tb_hz ? (uint32_t)((now - walker.t_origin) / live.tb_hz) : 0u;
    /* DONE is checked FIRST, in both branches: gbp_walker_current_kind() falls back to NAVIGATE
     * once w->finished (gbp_walker.c:110), so checking kind before finished would show the
     * perceptual label going back to "PHASE 0", indistinguishable from a restart in a blinded run
     * (the Orchestrator's own finding on 647be46). DONE is a SAFE, kind-independent instant, no
     * earlier than "setting k" already is. */
    if (gbp_walker_finished(&walker)) {
        snprintf(out, cap, "DONE %lus", (unsigned long)elapsed_s);
        return;
    }
#if defined(GBP_V28_PLAN_PERCEPTUAL)
    if (gbp_walker_current_kind(&walker) == GBP_WALKER_NULLING)
        snprintf(out, cap, "NULL SET %lu %lus", (unsigned long)nulling.settings_n, (unsigned long)elapsed_s);
    else
        snprintf(out, cap, "PHASE 0 %lus", (unsigned long)elapsed_s);
#else
    {
        /* index cannot reach count today (gbp_walker.c never advances it past its own last begun
         * value, on either the normal-completion or the cut path) -- but finished is already
         * handled above regardless, so this is a defensive clamp against a display-only "P5/4",
         * never load-bearing for DONE itself. */
        const unsigned long shown = (unsigned long)walker.index + 1u;
        const unsigned long count = (unsigned long)V28_PLAN->count;
        /* Issue #131: RUN 48 was silent for 310s with every counter looking healthy until
         * teardown; the Operator's ear was the only mid-run signal and silence is ambiguous (he
         * could be in a quiet spot in the game). A static "started" mark can't tell a stall from
         * healthy playback -- ap2.handed is the count of chunks actually handed to the AI DMA, so
         * showing it here makes a stall (the number frozen) as visible as a start (the number
         * appearing at all), without the Operator needing to know what "handed" means. Validation
         * branch only, same as the rest of this split -- ap2.handed is not a SAFE field for the
         * perceptual branch (comment above this function). */
        snprintf(out, cap, "P%lu/%lu H%lu RUN %lus", shown < count ? shown : count, count,
                 (unsigned long)label_handed_once_a_second(elapsed_s), (unsigned long)elapsed_s);
    }
#endif
}

#if defined(GBP_V28_PLAN_DIAG_LOSS)
/* Issue #137: the LOSS diagnostic's records, SD-only, read by tools/v28loss.py. One V28_LOSS line a hold (timing, arms, ring), one
 * V28_LOSSC line a window (the counters' deltas, wrap-safe), one V28_LOSSH line a histogram. Nothing here decides anything. */
static void v28_loss_report_ctr(struct ringlog *rl, uint32_t n, const char *win, const struct gbp_v28_loss_ctr *a,
                                const struct gbp_v28_loss_ctr *b)
{
    ringlog_printf(rl, "V28_LOSSC n=%lu win=%s blocks_in=%lu taps=%lu failed=%lu wrong=%lu underruns=%lu dup=%lu drop=%lu "
                       "starved=%lu produced=%lu handed=%lu gated=%lu",
                   (unsigned long)n, win, (unsigned long)(b->blocks_in - a->blocks_in), (unsigned long)(b->taps - a->taps),
                   (unsigned long)(b->taps_failed - a->taps_failed), (unsigned long)(b->wrong_len - a->wrong_len),
                   (unsigned long)(b->underruns - a->underruns), (unsigned long)(b->dup - a->dup),
                   (unsigned long)(b->drop - a->drop), (unsigned long)(b->starved - a->starved),
                   (unsigned long)(b->produced - a->produced), (unsigned long)(b->handed - a->handed),
                   (unsigned long)(b->ring_gated - a->ring_gated));
}

static void v28_loss_report(struct ringlog *rl)
{
    static const char *const HNAME[GBP_V28_NHIST] = {"tap", "decode", "prod", "pump", "label", "gap"};
    uint32_t i, k;
    ringlog_printf(rl, "V28LOSSCFG target=%lu ahead=%u ahead_final=%u warm_s=%u hold_s=%u late_s=%u final_s=%u cycles=%u "
                       "cells=%u step_full=%u step_half=%u tb_hz=%lu holds=%lu refused_done=%lu entry_refused_ticks=%lu",
                   (unsigned long)GBP_V28_T256, (unsigned)GBP_V28_A4, (unsigned)GBP_V28_A1, (unsigned)GBP_V28_LOSS_WARM_S,
                   (unsigned)GBP_V28_LOSS_HOLD_S, (unsigned)GBP_V28_LOSS_LATE_S, (unsigned)GBP_V28_LOSS_FINAL_S,
                   (unsigned)GBP_V28_LOSS_CYCLES, (unsigned)GBP_V28_LOSS_CELLS, (unsigned)GBP_V28_LOSS_STEP_FULL,
                   (unsigned)GBP_V28_LOSS_STEP_HALF, (unsigned long)live.tb_hz, (unsigned long)loss.holds_n,
                   (unsigned long)loss.refused_hold_done, (unsigned long)loss.begin_pending_ticks);
    for (i = 0u; i < loss.holds_n; i++) {
        const struct gbp_v28_loss_hold *h = gbp_v28_loss_hold_record(&loss, i);
        ringlog_printf(rl, "V28_LOSS n=%lu kind=%u cyc=%u L=%u S=%u ahead=%u target=%lu partial=%u late=%u hooks=%lu "
                           "t_start=%llx t_late=%llx t_end=%llx ring=%lu,%lu,%lu",
                       (unsigned long)i, (unsigned)h->kind, (unsigned)h->cyc, (unsigned)h->label_on, (unsigned)h->step_full,
                       (unsigned)h->ahead, (unsigned long)h->target, (unsigned)h->partial, (unsigned)h->has_late,
                       (unsigned long)h->underrun_hooks, (unsigned long long)h->t_start, (unsigned long long)h->t_late,
                       (unsigned long long)h->t_end, (unsigned long)h->c_start.ring, (unsigned long)h->c_late.ring,
                       (unsigned long)h->c_end.ring);
        /* the OBSERVED operating point at the three snapshots: the log verifies the fixed TARGET and AHEAD, the intent is not evidence */
        ringlog_printf(rl, "V28_LOSSO n=%lu obs_t=%lu,%lu,%lu obs_a=%lu,%lu,%lu", (unsigned long)i,
                       (unsigned long)h->c_start.target, (unsigned long)h->c_late.target, (unsigned long)h->c_end.target,
                       (unsigned long)h->c_start.ahead, (unsigned long)h->c_late.ahead, (unsigned long)h->c_end.ahead);
        v28_loss_report_ctr(rl, i, "full", &h->c_start, &h->c_end);
        if (h->has_late) v28_loss_report_ctr(rl, i, "late", &h->c_late, &h->c_end);
        for (k = 0u; k < GBP_V28_NHIST; k++) {
            const struct gbp_v28_hist *hh = &h->hist[k];
            ringlog_printf(rl, "V28_LOSSH n=%lu h=%s count=%lu sum=%llu max=%lu edges=%lu,%lu,%lu,%lu bins=%lu,%lu,%lu,%lu,%lu",
                           (unsigned long)i, HNAME[k], (unsigned long)hh->count, (unsigned long long)hh->sum,
                           (unsigned long)hh->max, (unsigned long)hh->edge[0], (unsigned long)hh->edge[1],
                           (unsigned long)hh->edge[2], (unsigned long)hh->edge[3], (unsigned long)hh->bin[0],
                           (unsigned long)hh->bin[1], (unsigned long)hh->bin[2], (unsigned long)hh->bin[3],
                           (unsigned long)hh->bin[4]);
        }
    }
}
#endif /* GBP_V28_PLAN_DIAG_LOSS */

/* Issue #138: two lines a phase (V28PHC: window and blocks; V28PHD: the corrector and the ring), every plan. Read by tools/v28verdict.py: loss = 1 - blocks_in / (4096 x seconds) over the snapshot times. */
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

    printf("\n  Open-GBP " TEST_ID "  Issue #128/#129/#130, THE VALIDATION ROUND (NOT PHYSICALLY VALIDATED)\n");
    printf("  Build : %s   Commit: %s   Plan: %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT,
#if defined(GBP_V28_PLAN_PERCEPTUAL)
           "perceptual_no_phase1");
#elif defined(GBP_V28_PLAN_DIAG_LOSS)
           "diag_loss");
#else
           "validation_run");
#endif
    printf("  libogc: %s   Gecko: %s\n", _V_STRING, gecko_present ? "yes" : "no");
    printf("  %s\n\n", opengbp_ident_marker);

    snprintf(line, sizeof line, "OPENGBP-V28 READY %s test=%s\n", ident_text, TEST_ID);
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
    gbp_atrans2_init(&tr);
    gbp_v28_dma_init(&v28_dma);
#if defined(GBP_V28_PLAN_DIAG_LOSS)
    gbp_v28_hists_init(loss_hist);
    ap2.step_pushes = loss_step_pushes;         /* the step arm; every chunk asks at its start, the answer is the cell's */
    ap2.step_pushes_user = 0;
#else
    /* Issue #138 (RUN 54): every other image takes the steady production step, 64 pushes a call, in every state (gbp_v28_step.h) */
    ap2.step_pushes = gbp_v28_step_hook;
    ap2.step_pushes_user = 0;
#endif
    DCFlushRange(ap2_silence, sizeof ap2_silence);
    cfg.audio_tap = live_tap;
    cfg.audio_tap_user = 0;

    t_selftest_begin = gettime();
    display_selftest();
    t_selftest_end = gettime();
    snprintf(line, sizeof line,
             "OPENGBP-V28 SELFTEST ok=%d converted=%d released=%d submits=%lu drawdone=%lu releases=%lu xfb=%lu sci_clean=%d inv_fail=%lu\n",
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
    ringlog_printf(&rl, "V28CFG plan=%s session_cap_s=%lu wall_s=%lu step_mute=%u start_mute=%u p2_lo=%lu p2_hi=%lu p2_step=%lu",
#if defined(GBP_V28_PLAN_PERCEPTUAL)
                   "perceptual_no_phase1",
#elif defined(GBP_V28_PLAN_DIAG_LOSS)
                   "diag_loss",
#else
                   "validation_run",
#endif
                   (unsigned long)V28_SESSION_CAP_S, (unsigned long)V28_WALL_S, (unsigned)GBP_V28_STEP_MUTE,
                   (unsigned)GBP_V28_START_MUTE, (unsigned long)GBP_V28_P2_LO, (unsigned long)GBP_V28_P2_HI,
                   (unsigned long)GBP_V28_P2_STEP);
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
            gecko_puts("OPENGBP-V28 STORAGE FATAL field=");
            gecko_puts(fault);
            gecko_puts("\n");
        }
    }

    AUDIO_Init(NULL);
    AUDIO_SetDSPSampleRate(AI_SAMPLERATE_32KHZ);
    AUDIO_RegisterDMACallback(live_dma_cb);

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);
    hsp_backend_irq_transport_ext(&hsp, &t);

    printf("  Sequence: the vstate-0004 service path VERBATIM.\n");
    printf("  Session:  HOLD Z for %lu ms to END THE SESSION. Wall %lu s (never a success).\n",
           (unsigned long)PLAY_SESSION_END_HOLD_MS, (unsigned long)PLAY_SAFETY_SECONDS);
    if (!gbp_transport_has_bulk_read(&t) || !gbp_transport_has_irq_reset(&t) || !gbp_transport_has_time64(&t)) {
        printf("\n  FATAL: the transport lacks the whole-block read, the record reset or the 64-bit time base.\n");
        printf("  Nothing was run. START = exit\n");
        for (;;) { VIDEO_WaitVSync(); PAD_ScanPads(); if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break; }
        exit(1);
    }
    printf("\x1b[2J\x1b[1;0H");
    printf("  Open-GBP " TEST_ID "  %s  %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("  Cartridge: a GBA game the Operator knows. Link Port: nothing. BBA: absent.\n");
    printf("  WAIT for the prompt below (about 5 s). Then press A within 45 s: the game appears.\n");
    printf("  C-stick DOWN = next phase.\n");

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

    /* ---- §V28's own records. EVERY one below is SD-only: nothing here reaches the screen or the
     * live/gecko channel -- Amendment C's own depths/plans/acted included, universally. ---- */
    if (sync_started) {
        ringlog_printf(&rl, "V28SEED seed=%08lx", (unsigned long)sync_seed);
        ringlog_printf(&rl, "V28C underruns=%lu overflow=%lu silences=%lu mute_handed=%lu dup=%lu drop=%lu produced=%lu "
                            "handed=%lu ring_gated=%lu",
                       (unsigned long)ap2.underruns, (unsigned long)adec2.overflow, (unsigned long)ap2.silences,
                       (unsigned long)ap2.mute_handed, (unsigned long)ap2.dup, (unsigned long)ap2.drop,
                       (unsigned long)ap2.produced, (unsigned long)ap2.handed, (unsigned long)ap2.ring_gated);
        ringlog_printf(&rl, "V28C2 discarded=%lu starved_steps=%lu lost=%lu blocks_in=%lu ring_discarded=%lu "
                            "trans_faults=%lu dropped_front=%lu cs=%lu acted=%lu syncpe_lost=%lu lines_lost=%lu",
                       (unsigned long)ap2.discarded_chunks, (unsigned long)ap2.starved_steps, (unsigned long)adec2.lost,
                       (unsigned long)adec2.blocks_in, (unsigned long)adec2.discarded, (unsigned long)tr.faults,
                       (unsigned long)ap2.dropped_front, (unsigned long)cs_events, (unsigned long)cs_acted,
                       (unsigned long)syncpe_lines_lost, (unsigned long)sync_lines_lost);
        ringlog_printf(&rl, "V28CORR n=%lu overflow=%lu min=%lu max=%lu mean_x100=%lu cap=%lu",
                       (unsigned long)corr_n, (unsigned long)corr_overflow,
                       (unsigned long)(corr_n ? corr_min : 0u), (unsigned long)corr_max,
                       (unsigned long)(corr_n ? (unsigned long)((corr_sum * 100u) / corr_n) : 0u),
                       (unsigned long)CORR_CAP);
        /* the label's own cost, in the SAME pump slot as the AHEAD-margin refill (Issue #128 §7) */
        ringlog_printf(&rl, "V28LABEL renders=%lu ticks_last=%lu ticks_max=%lu",
                       (unsigned long)label_renders, (unsigned long)label_ticks_last,
                       (unsigned long)label_ticks_max);
        /* Issue #137: the tap counters the live/sync images printed as LIVEN and this image never did -- so a loss could not be told
         * from a refused or short tap. taps == blocks_in with zero failed/wrong is what RUN 38-43 showed. */
        {   /* Issue #139: the AI DMA's hand-off semantics, as READ at every callback's entry (SD only) */
            uint32_t q;
            ringlog_printf(&rl, "V28DMA n=%lu prev1=%lu prev2=%lu none=%lu same12=%lu left_min=%lu left_max=%lu left_mean=%lu bins=%lu,%lu,%lu,%lu,%lu,%lu",
                           (unsigned long)v28_dma.n, (unsigned long)v28_dma.prev1, (unsigned long)v28_dma.prev2, (unsigned long)v28_dma.none,
                           (unsigned long)v28_dma.same12, (unsigned long)(v28_dma.n ? v28_dma.left_min : 0u), (unsigned long)v28_dma.left_max,
                           (unsigned long)(v28_dma.n ? v28_dma.left_sum / v28_dma.n : 0u), (unsigned long)v28_dma.bins[0],
                           (unsigned long)v28_dma.bins[1], (unsigned long)v28_dma.bins[2], (unsigned long)v28_dma.bins[3],
                           (unsigned long)v28_dma.bins[4], (unsigned long)v28_dma.bins[5]);
            for (q = 0u; q < v28_dma.raw_n && q < GBP_V28_DMA_RAW; q++)
                ringlog_printf(&rl, "V28DMAR i=%lu addr=%lx left=%lu ret1=%lx ret2=%lx dt=%lu", (unsigned long)q,
                               (unsigned long)v28_dma.raw[q].addr, (unsigned long)v28_dma.raw[q].left,
                               (unsigned long)v28_dma.raw[q].ret1, (unsigned long)v28_dma.raw[q].ret2,
                               (unsigned long)v28_dma.raw[q].dt);
        }
        ringlog_printf(&rl, "V28TAPS taps=%lu taps_failed=%lu wrong_len=%lu blocks_in=%lu gap_max=%llu gap_at=%llx",
                       (unsigned long)live_taps, (unsigned long)live_taps_failed, (unsigned long)live_wrong_len,
                       (unsigned long)adec2.blocks_in, (unsigned long long)live_gap_max, (unsigned long long)live_gap_at);
        v28_phase_report(&rl);
#if defined(GBP_V28_PLAN_DIAG_LOSS)
        v28_loss_report(&rl);
#endif
#if defined(GBP_V28_PLAN_VALIDATION)
        for (j = 0u; j < s3a.depths_n && j < GBP_V28_3A_DEPTH_CAP; j++) {
            const struct gbp_v28_3a_depth *d = gbp_v28_3a_depth_record(&s3a, j);
            ringlog_printf(&rl, "V28_3A n=%lu target=%lu kind=%u partial=%u underruns=%lu overflow=%lu dup=%lu drop=%lu "
                                "starved=%lu t_set=%llx t_done=%llx",
                           (unsigned long)j, (unsigned long)d->target, (unsigned)d->kind, (unsigned)d->partial,
                           (unsigned long)d->underruns, (unsigned long)d->overflow, (unsigned long)d->dup,
                           (unsigned long)d->drop, (unsigned long)d->starved, (unsigned long long)d->t_set,
                           (unsigned long long)d->t_done);
        }
        /* Amendment 1: the anchor 3b actually held at (or GBP_V28_ANCHOR_NONE, meaning 3b never
         * held at all) -- ONE line, since the anchor is constant for the whole phase; the only
         * record of an anchor=none finding, since s3b then has no V28_3B records of its own. */
        if (v28_anchor_computed)
            ringlog_printf(&rl, "V28ANCHOR target=%lu source=%s",
                           (unsigned long)v28_anchor.target, gbp_v28_anchor_source_name(v28_anchor.source));
        for (j = 0u; j < s3b.holds_n; j++) {
            const struct gbp_v28_3b_hold *h = gbp_v28_3b_hold_record(&s3b, j);
            ringlog_printf(&rl, "V28_3B n=%lu ahead=%lu anchor=%lu source=%s underrun_seen=%u partial=%u t_set=%llx "
                                "t_done=%llx min_ready=%lu min_ring=%lu samples=%lu",
                           (unsigned long)j, (unsigned long)h->ahead, (unsigned long)v28_anchor.target,
                           gbp_v28_anchor_source_name(v28_anchor.source), (unsigned)h->underrun_seen,
                           (unsigned)h->partial, (unsigned long long)h->t_set, (unsigned long long)h->t_done,
                           (unsigned long)h->min_ready, (unsigned long)h->min_ring, (unsigned long)h->samples);
            /* Issue #136: the ring at the first sample after the entry landing, and its minimum once the
             * hold has settled -- what min_ring = 256 in RUN 52 could not separate. */
            ringlog_printf(&rl, "V28_3BM n=%lu ring0=%lu min_ring_late=%lu samples_late=%lu mean_ring=%lu mean_cs=%lu "
                                "chunk_starts=%lu",
                           (unsigned long)j, (unsigned long)h->ring0, (unsigned long)h->min_ring_late,
                           (unsigned long)h->samples_late, (unsigned long)h->mean_ring,
                           (unsigned long)h->mean_chunk_start, (unsigned long)h->chunk_starts);
        }
        for (j = 0u; j < sweep.records_n && j < GBP_V28_SWEEP_N; j++) {
            const struct gbp_v28_sweep_record *r = gbp_v28_sweep_record_at(&sweep, j);
            ringlog_printf(&rl, "V28_SWEEP n=%lu klass=%u mech=%u from_t=%lu from_a=%lu to_t=%lu to_a=%lu outcome=%u "
                                "fail=%u residue=%ld unmasked=%u",
                           (unsigned long)j, (unsigned)r->klass, (unsigned)r->mechanism, (unsigned long)r->from_target,
                           (unsigned long)r->from_ahead, (unsigned long)r->to_target, (unsigned long)r->to_ahead,
                           (unsigned)r->outcome, (unsigned)r->fail_reason, (long)r->residue, (unsigned)r->unmasked);
            /* Issue #135: what the chain ACTUALLY was at the move's start and at its landing (the
             * line above prints the frozen table's own from_* assumption). A second line with the
             * same n, not more fields on the first: the first is already 112 characters and the
             * console log line is 256. */
            ringlog_printf(&rl, "V28_SWEEPM n=%lu meas_t=%lu meas_a=%lu meas_ring=%lu meas_ready=%lu ring=%lu "
                                "ready=%lu dup=%lu drop=%lu t_land=%llx",
                           (unsigned long)j, (unsigned long)r->meas_target, (unsigned long)r->meas_ahead,
                           (unsigned long)r->meas_ring, (unsigned long)r->meas_ready, (unsigned long)r->ring,
                           (unsigned long)r->ready, (unsigned long)r->dup, (unsigned long)r->drop,
                           (unsigned long long)r->t_land);
            /* Issue #136: where the ring's level was set (samples cut, and the hand-off period relative to the
             * first audible hand-off: negative is inside the mute, >= 0 is a cut AFTER unmute and fails the GATE row
             * as SPLICE), the rotations that rebuilt the queue after it, and whether the mute could fill the ring. */
            ringlog_printf(&rl, "V28_SWEEPC n=%lu cut=%lu cut_rel=%ld rot_post=%lu fill_short=%lu dwell_cut=%lu late=%u",
                           (unsigned long)j, (unsigned long)r->cut, (long)r->cut_rel, (unsigned long)r->rot_post,
                           (unsigned long)r->fill_short, (unsigned long)r->dwell_cut, (unsigned)r->late);
        }
        ringlog_printf(&rl, "V28_SWEEP_VERDICT v=%u", (unsigned)gbp_v28_sweep_verdict(&sweep));
#else
        for (j = 0u; j < nulling.settings_n && j < GBP_V28_NULLING_CAP; j++) {
            const struct gbp_v28_nulling_setting *s = gbp_v28_nulling_record(&nulling, j);
            ringlog_printf(&rl, "V28_NULL n=%lu start=%lu dir=%u steps=%lu deeper=%lu shallower=%lu target=%lu t=%llx",
                           (unsigned long)j, (unsigned long)s->start, (unsigned)s->direction, (unsigned long)s->steps,
                           (unsigned long)s->steps_deeper, (unsigned long)s->steps_shallower, (unsigned long)s->target,
                           (unsigned long long)s->t);
        }
#endif
        /* the backstop: EVERY phase index, INCLUDING 0 (sync-0001's own bug, section 7: its loop
         * started at j=1u) -- and what actually classifies why=probe vs why=z (see the file header). */
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

    printf("\n  HARDWARE status=%s (%s) reason=%s stop=%s restore=%s\n", res.status_name, res.status_class,
           res.reason ? res.reason : "-", gbp_vstate_stop_name(res.stop), res.restore_ok ? "ok" : "ERROR");
    printf("  SESSION %s: Z held %lu of %lu samples\n",
           res.stop == GBP_VSTATE_STOP_SESSION_END ? "ENDED (success)" : "NOT ended by the operator",
           (unsigned long)session.samples_held, (unsigned long)session.samples);
    printf("  RESTORE control=%d stop=%d cleanup=%d arinfo=%d handler=%d mask_ok=%d\n",
           a->control_restore_ok, a->irq_stop_write_ok, a->pi_cleanup_performed, a->arinfo_restore_ok,
           res.h.handler_restored, res.h.mask_ok);
    v28_screen_report();

    snprintf(line, sizeof line, "OPENGBP-V28 RESULT status=%s stop=%s service=%d deliveries=%lu restore=%d\n",
             res.status_name, gbp_vstate_stop_name(res.stop), res.service_ok, (unsigned long)res.deliveries,
             res.restore_ok);
    gecko_puts(line);
    v28_live_report();

    printf("\n  X = save log to SD    START = exit    POWER CYCLE REQUIRED\n");
    for (;;) {
        VIDEO_WaitVSync();
        PAD_ScanPads();
        if (!saved && (PAD_ButtonsDown(0) & PAD_BUTTON_X)) {
            char extra[240];
            int rc;
            snprintf(extra, sizeof extra,
                     "libogc=%s gecko=%d power_cycle_required=%d time_target=disabled safety_s=%lu "
                     "session_end=walker_or_Z hold_ms=%lu stop=%s status=%s",
                     _V_STRING, gecko_present, res.power_cycle_required,
                     (unsigned long)PLAY_SAFETY_SECONDS, (unsigned long)PLAY_SESSION_END_HOLD_MS,
                     gbp_vstate_stop_name(res.stop), res.status_name);
            rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl, status, sizeof status, line,
                            sizeof line);
            saved = (rc == 0);
            printf("  SAVE log     %s\n", status);
        }
        if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break;
    }
    gecko_puts("OPENGBP-V28 DONE\n");
    (void)t_program; (void)t_video_ready; (void)t_selftest_begin; (void)t_selftest_end; (void)t_probe_enter;
    return 0;
}
