/*
 * Open-GBP GBP-VIDEO-004, build stream-0002 — the corrected streaming candidate
 * (HARDWARE_TESTS §V5, fixes §V5.26). IMPLEMENTED AND HOST-VALIDATED; it has
 * never touched hardware, and nothing here claims sustained streaming works.
 * `stream-0001` is historical and REJECTED: do not run it.
 *
 * WHAT IS NEW, AND WHAT IS NOT
 *
 * The capture is the service path `vstate-0004` physically validated and
 * `color-0001`/`color-0002` reused unchanged: the 003A stage, the 003B extended
 * one-shot handler, READ -> AUDIO -> VIDEO -> ACK -> PI clean -> signature and
 * frame assembly -> RE-ARM -> wait next cause, with the R3 semantic-disagreement
 * policy exactly as it stands. Not one device operation is added, removed or
 * reordered.
 *
 * What is new is a CONSUMER and a SCREEN. This file owns both, and that
 * ownership is the architecture: `src/gbp/` gained two pure modules
 * (`gbp_vpix`, `gbp_vqueue`) that know nothing about GX, and every graphics call
 * in the whole program lives in this file. `tools/poc_audit.py` profile `stream`
 * enforces exactly that — `GX_` is permitted in `main.o` and forbidden in every
 * other object.
 *
 * ---- THE THREE RULES THE EARLIER ROUNDS PAID FOR -------------------------
 *
 * 1. NO FRAME WORK IN THE SERVICE PATH (§V3.23, §V5.7). What crosses from the
 *    producer is a descriptor of integers. `gbp_vqueue_publish()` copies no
 *    pixel and cannot block; a consumer that has fallen behind loses a frame,
 *    the device never waits.
 *
 * 2. NEVER SYNTHESISE PIXELS (§V5.9). An incomplete, anomalous or quarantined
 *    frame is counted and never published, HOLD_PREVIOUS_FRAME keeps the last
 *    frame that really arrived on screen, and a conversion that loses its race
 *    is discarded whole. Two generations never mix in one image.
 *
 * 3. NOTHING IS CALLED "FAST ENOUGH" WITHOUT MEASURING IT (§V5.22). Every slice
 *    is timed into bounded aggregates and reported; this file makes no timing
 *    claim of its own.
 *
 * ---- WHERE THE CONSUMER'S CPU TIME COMES FROM ---------------------------
 *
 * §V5 fixed the boundary and the policy but not the execution site, because the
 * probe is single-threaded and `gbp_vstate_probe_run()` owns the loop. The site
 * chosen here is the most conservative one available: a BOUNDED SLICE, one tile
 * row, run from `gbp_vqueue_pump()` immediately after the RE-ARM — the pass's
 * last device access, with the next cause already invited. Never between the ACK
 * and the RE-ARM, and never a whole frame in one call.
 *
 * THE SLICE SIZE IS NOT JUSTIFIED BY A TIMING CLAIM, and the claim it used to
 * carry was wrong. `stream-0001` said "164 us of slack between deliveries"; that
 * figure is `capture_elapsed / deliveries`, the mean cycle PERIOD, not slack.
 * The audit measured the real RE-ARM→next-cause window from `vstate-0004`'s 80
 * physical cycles: median 42.8 us, p25 **1.9 us**, with 34 % of cycles at 1.9 us
 * — the next cause is usually already latched when the RE-ARM completes.
 *
 * One tile row is therefore kept as a CONSERVATIVE bounded quantum and not as a
 * proven fit, and two things follow. The cause is read BEFORE the slice and the
 * slice is skipped when one is already pending (`pump_skipped_cause_pending`),
 * and the slice cost plus the cause state either side of it are recorded so the
 * first physical run MEASURES the effect instead of inheriting an assumption.
 * The position remains PLAUSIBLE BUT UNMEASURED until that run.
 *
 * ---- WHAT stream-0001 GOT WRONG, AND WHERE THE FIX LIVES -----------------
 *
 * `stream-0001` was REJECTED before hardware (§V5.26). Its draw-done callback
 * freed EVERY buffer in `TEX_SUBMITTED`, but a DrawDone token certifies only the
 * commands queued before it: with two frames in flight the first token freed
 * both, and the CPU could then refill a texture the GP was still reading. The
 * defect survived a green suite because it lived in this file, which had no
 * behavioural test — the host tests asserted only that `on_draw_done` appeared
 * in the source.
 *
 * So the ownership is no longer here. `src/gbp/gbp_vpresent.{h,c}` holds it, it
 * knows nothing about GX or VI, and a host test drives it state by state. The
 * rule it enforces is the one that can be proved: AT MOST ONE DRAW-DONE TOKEN IN
 * FLIGHT, and the callback releases exactly one buffer BY INDEX.
 *
 *     FREE -> CPU_FILLING -> READY -> SUBMITTED -> (draw-done) -> FREE
 *
 * `GX_DrawDone()` would be simpler and it BLOCKS, which §V5.7 forbids in this
 * path; `GX_SetDrawDone()` plus a callback is the non-blocking form.
 *
 * ---- AND THE FRAMEBUFFER, WHICH IS A DIFFERENT QUESTION ------------------
 *
 * `stream-0001` copied into the framebuffer the VI was scanning out. A DrawDone
 * says the GP finished reading the TEXTURE; it says nothing about the VI.
 * `stream-0002` therefore keeps TWO stream framebuffers and asks
 * `gbp_vpresent_xfb_target()` which one is safe, from two non-blocking VI reads:
 * `VIDEO_GetCurrentFramebuffer()` and the hand-over we are still waiting on.
 * When neither is safe the present is SKIPPED and counted. Nothing here waits
 * for a retrace, and no second asynchronous machine was introduced to do it.
 *
 * SD save on X - the text log - START to exit. Nothing is read from the
 * controller before the probe has returned from its teardown. Every run ends
 * with "POWER CYCLE REQUIRED".
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
#include "gbp_vwitness.h"
#include "gbp_vidxdump.h"
#include "gbp_vdisp.h"
#include "gbp_vdispdump.h"
#include "hsp_backend.h"
#include "hsp_backend_irq.h"
#include "sdlog.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "gbp-video-stream-probe"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
#define TEST_ID "GBP-VIDEO-004"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT " OPENGBP_APP_NAME " " OPENGBP_BUILD_ID " " OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1

#define LOG_LINES 1024
#define LOG_LINE_LEN 256
#define DMA_TIMEOUT_MS 200

/* ---- the capture window (§V5.20, §V5.23) --------------------------------
 *
 * DESIGN DECISION REQUIRED, and it stays required. §V5.5 asks for a duration
 * justified against a real interval, the way GBP-VIDEO-002's 120 s was justified
 * against the Start-up Disc's own detector window. No such interval has been
 * established for streaming, so the value below is PROVISIONAL: it is long
 * enough to exercise the machinery over roughly 1800 AGB frames at the measured
 * 59.727 Hz, and it is NOT a scientific threshold. §V5.21's PASS criterion is
 * "the invariants hold for the whole DECLARED duration", so the criterion works
 * for any declared value — which is exactly why choosing this one decides
 * nothing. The pre-hardware audit fixes it. */
#define STREAM_CAPTURE_SECONDS   30u
#define STREAM_SAFETY_SECONDS    60u    /* the safety cap, a different thing entirely */
#define STREAM_MAX_DELIVERIES    400000u

/* One tile row per pump call: 3840 bytes read, 1920 written. See the header
 * comment for why this size and not a frame. */
#define STREAM_SLICE_TILE_ROWS   1u

static char log_storage[LOG_LINES * LOG_LINE_LEN];
static uint8_t dma_buffer[GBP_BLOCK_SIZE] ATTRIBUTE_ALIGN(32);

/* ---- the state model's stores -------------------------------------------
 *
 * THE FULL GBP-VIDEO-002 STORE SET, and the reason is physical.
 *
 * `stream-0002` shipped a reduced set — 4096 frame records and NO episode raw
 * store — on the strength of §V5.22's claim that a streaming run does not need
 * the change detector. Its first physical run aborted at the probe's first gate
 * with `store_or_bounds_invalid`, before touching the device (GBP-HW-136), and
 * the gate was RIGHT: `gbp_vstate_probe.c` memsets through `episode_raw` and
 * `preserve_frame()` writes a whole frame into it whenever an episode opens,
 * neither of them checking for NULL. A NULL store is not a smaller model, it is
 * a 2.81 MiB write to address 0.
 *
 * So the POC now satisfies the contract instead of arguing with it. The sizes
 * below are exactly what `vstate-0004` and `color-0002` — the two physically
 * validated builds — carry. The raw ring keeps FOUR slots, which is what gives
 * the generation guard its margin (§V3.24, §V5.7).
 *
 * Cost of the correction: +2 359 296 B of frame table and +2 949 120 B of
 * episode store = +5 308 416 B. See HARDWARE_TESTS §V5.30 for the measured
 * footprint that resulted. */
static struct gbp_vstate_frame frame_store[GBP_VSTATE_MAX_FRAMES];                 /* 3.00 MiB */
static struct gbp_vstate_event event_store[GBP_VSTATE_MAX_EVENTS];                 /* 0.25 MiB */
static uint8_t raw_ring[GBP_VSTATE_RAW_RING_BYTES_4] ATTRIBUTE_ALIGN(32);          /* 0.70 MiB, DMA target */
static uint8_t episode_raw[GBP_VSTATE_EPISODE_RAW_BYTES] ATTRIBUTE_ALIGN(32);      /* 2.81 MiB */
static uint8_t audio_raw[GBP_VSTATE_AUDIO_RAW_BYTES] ATTRIBUTE_ALIGN(32);          /* 12 KiB, DMA target */

/* The contract, checked where it cannot be argued with: at compile time, over
 * the ACTUAL arrays. A future edit that shrinks either store stops the build
 * instead of costing another physical run. */
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
static struct gbp_vstate_cycle cyc_first[GBP_VSTATE_CYC_FIRST];
static struct gbp_vstate_cycle cyc_last[GBP_VSTATE_CYC_LAST];
static struct gbp_vstate_cycle cyc_anomaly[GBP_VSTATE_CYC_ANOMALY];
static struct gbp_vstate_cycle cyc_episode[GBP_VSTATE_CYC_EPISODE];
static struct gbp_vstate vstate;
static struct gbp_vstate_diag diag_store[GBP_VSTATE_MAX_DISAGREEMENTS];
static struct gbp_vqueue vq;

/* ---- the OGBPIDX1 witness store (HARDWARE_TESTS §V5.39) -----------------
 *
 * 2048 frames x 4320 bytes = 8 847 360 B of canonical witness, plus 2048 x 48 B
 * of per-frame metadata. The metadata is a SEPARATE 98 304 B and is reported
 * separately: the 8.4375 MiB figure that was audited is the witness itself, and
 * it is not quietly made to include something else.
 *
 * The count is 2048 and is NOT raised to match the ~2648 frames `stream-0004`
 * closed. The target is what BOUNDS the run (§V5.39.3); growing the store to
 * swallow a longer run would put the memory budget back where the old
 * time-bounded premise had it, which is the premise GBP-HW-151 disproved. */
static uint16_t witness_store[GBP_VWITNESS_TARGET][GBP_VWITNESS_FRAME_WORDS] ATTRIBUTE_ALIGN(32);
static struct gbp_vwitness_meta witness_meta[GBP_VWITNESS_TARGET];
static struct gbp_vwitness wit;

_Static_assert(sizeof witness_store == GBP_VWITNESS_STORE_BYTES,
               "the witness store must be exactly the audited 8 847 360 bytes");
_Static_assert(GBP_VWITNESS_FRAME_BYTES == 4320u, "54 words x 40 blocks x 2 bytes");
_Static_assert(GBP_VWITNESS_WORDS == 54u && GBP_VWITNESS_BLOCKS == 40u,
               "the canonical witness geometry is fixed by the frozen OGBPIDX1 contract");
_Static_assert(GBP_VIDXDUMP_RECORD_SIZE == GBP_VWITNESS_FRAME_BYTES + 48u,
               "one sidecar record is 48 bytes of metadata plus the witness");

/* ---- the texture buffers; the OWNERSHIP lives in src/gbp/gbp_vpresent ---- */
#define STREAM_TEX_BUFFERS GBP_VPRESENT_TEX_BUFFERS
static uint16_t tex_buf[STREAM_TEX_BUFFERS][GBP_VPIX_TEX_BYTES / 2u] ATTRIBUTE_ALIGN(32);  /* 2 x 75 KiB */
static struct gbp_vpresent present;
static GXTexObj tex_obj;

/* A texture buffer must be a whole number of 32-byte cache lines, or a flush of
 * its exact size would touch memory it does not own. */
_Static_assert(GBP_VPIX_TEX_BYTES % 32u == 0u, "texture size must be cache-line aligned");
_Static_assert(GBP_VPIX_TEX_BYTES == 240u * 160u * 2u, "texture is 240x160 16-bit");
_Static_assert(GBP_VPIX_FRAME_BYTES == 40u * 0xF00u, "a frame is 40 blocks of 0xF00");
_Static_assert(STREAM_TEX_BUFFERS >= 2u, "GX may still be reading one buffer while the CPU fills the other");
_Static_assert(GBP_VPRESENT_XFB_BUFFERS == 2u, "the stream needs two framebuffers so the VI is never written under");
/* P1: the queue's conservation identity allows a bounded residual of converted
 * frames still waiting for a submit — one per texture buffer. gbp_vqueue.h may
 * not include gbp_vpresent.h, so the coupling is asserted HERE, where both are
 * visible, instead of being an unchecked comment in two files. */
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
    int      life;                 /* §V5.46 downstream lifecycle index, or -1 */
} conv;

/* ---- the downstream disposition trace (§V5.46) --------------------------
 *
 * OBSERVATIONAL ONLY. Nothing below changes a scheduling decision, a queue
 * depth, a buffer count or an XFB policy; it records the state that the
 * existing decisions were taken in, because a counter incremented after a
 * branch cannot say what the branch saw.
 *
 * `tex_life[]` is the MAIN-side texture -> lifecycle map. The module keeps its
 * own copy for the interrupt path; this one exists because submit_ready() can
 * be reached from the re-offer loop, which knows a texture index and nothing
 * else. -1 means "no scientific frame", which is what the self-test carries. */
static struct gbp_vdisp_life  disp_life[GBP_VDISP_LIFE_CAP];
static struct gbp_vdisp_event disp_ev[GBP_VDISP_EVENT_CAP];
static struct gbp_vdisp disp;
static int tex_life[STREAM_TEX_BUFFERS];
static struct gbp_vdispdump_info disp_info;
static uint8_t disp_chunk[GBP_VDISPDUMP_HEADER_SIZE];
static long disp_saved_bytes;
static int  disp_save_rc;

static uint32_t conv_abandoned_no_raw;
static int gx_drained_at_teardown, gx_callback_restored;
static uint32_t flag15_last_count;
static uint32_t flag15_last_x, flag15_last_y;
static const struct gbp_vstate *pump_state;

/* ---- the two stream framebuffers, plus the console's own ---------------- */
static void *xfb_stream_buf[GBP_VPRESENT_XFB_BUFFERS];

/* Which stream framebuffer the VI is scanning out, as an INDEX, or -1 when it
 * is showing neither (the console). One pointer comparison, no blocking. */
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
 * texture is free. This runs at interrupt time and does exactly one thing: it
 * calls the ownership module, which releases exactly one buffer by index.
 *
 * `stream-0001`'s version looped over every buffer and freed each one that was
 * SUBMITTED, which is how the CPU could take back a texture the GP still owned
 * (§V5.26.2). Nothing else may be added here: no conversion, no drawing, no
 * filesystem, no formatted logging, and nothing that touches GBP service state. */
static void on_draw_done(void)
{
    /* §V5.46: the release index is what identifies the frame, so the trace call
     * takes it straight from the ownership module rather than searching. Two
     * field writes, no allocation, no formatting, no filesystem, no scan. */
    const int idx = gbp_vpresent_draw_done(&present);
    gbp_vdisp_drawdone(&disp, idx, gettime());
}

static void video_setup(void)
{
    VIDEO_Init();
    rmode = VIDEO_GetPreferredMode(NULL);
    /* TWO framebuffers, which is how the text report and the GX output stop
     * competing for one (§V5.15 named this as the open question). The console
     * owns xfb_text and is shown while the probe reports; GX copies into
     * xfb_stream and that one is shown while the capture runs. */
    /* TWO stream framebuffers, so a copy never lands in the one the VI is
     * scanning out (§V5.26 F8), plus the console's own so the text report and the
     * image never compete. */
    xfb_stream_buf[0] = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
    xfb_stream_buf[1] = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
    xfb_stream = xfb_stream_buf[0];
    xfb_text   = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
    CON_Init(xfb_text, 20, 20, rmode->fbWidth, rmode->xfbHeight, rmode->fbWidth * VI_DISPLAY_PIX_SZ);
    VIDEO_Configure(rmode);
    VIDEO_SetNextFramebuffer(xfb_text);
    VIDEO_SetBlack(false);
    VIDEO_Flush();
    VIDEO_WaitVSync();
    if (rmode->viTVMode & VI_NON_INTERLACE) VIDEO_WaitVSync();
}

/* Minimal GX: one RGB5A3 texture drawn as one quad, orthographic, no lighting,
 * no filter, no effect. Every call here is in the official libogc2 texture
 * example's init sequence; nothing is added for convenience (§V5.12, §V5.16). */
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
    /* GX_REPLACE: the texel reaches the framebuffer unmodified. No TEV maths, no
     * lighting, no channel arithmetic — the device already did the only colour
     * transformation there is (GBP-HW-131). */
    GX_SetTevOp(GX_TEVSTAGE0, GX_REPLACE);
    GX_SetTevOrder(GX_TEVSTAGE0, GX_TEXCOORD0, GX_TEXMAP0, GX_COLORNULL);
    GX_SetNumTevStages(1);

    guOrtho(proj, 0.0f, (f32)rmode->efbHeight, 0.0f, (f32)rmode->fbWidth, 0.0f, 300.0f);
    GX_LoadProjectionMtx(proj, GX_ORTHOGRAPHIC);
    guMtxIdentity(mv);
    GX_LoadPosMtxImm(mv, GX_PNMTX0);

    gx_prev_drawdone_cb = GX_SetDrawDoneCallback(on_draw_done);
}

/* Native 240x160, centred, unscaled. Scaling and aspect are Phase 9 policy and
 * are deliberately absent (§V5.16). */
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

/* THE CONSUMER SLICE. Called once per service cycle, after the RE-ARM, and it
 * does a bounded amount of work and returns. It never blocks, never waits for
 * the GP or the VI, and never touches the device. */
/* `account` is the queue the presentation belongs to, or NULL when it belongs to
 * nothing scientific. R1: `stream-0002` passed the self-test's synthetic frame
 * straight into `vq`, which put `consumer_frames_presented` one ahead of
 * `consumer_frames_converted` for the whole run (GBP-HW-135). The self-test now
 * accounts for itself, in its own two counters, and the queue never sees it. */
static void submit_ready(int buf, struct gbp_vqueue *account);

/* ---- the display self-test (§V5.26.4) -----------------------------------
 *
 * `stream-0001` was called "smoke-tested" while its whole display path had never
 * executed: Dolphin matched a line printed BEFORE the probe ran, and without a
 * Game Boy Player no frame ever closes, so the conversion, the flush, the
 * texture setup, the draw, the token and the callback were all dead code.
 *
 * This walks the identical path once, before the probe, from a SYNTHETIC raw
 * frame this file builds. It knows no stimulus value — a gradient derived from
 * the pixel coordinates — so it cannot teach the runtime what the experiment is
 * looking for (§V3.11). It runs unconditionally because a path that is only
 * exercised when someone remembers to ask is the path that rots; it costs one
 * frame before the capture opens and touches no device.
 *
 * It does NOT prove timing, pacing or anything about the Game Boy Player. It
 * proves the code runs and the ownership machine ends where it started. */
static uint8_t selftest_raw[GBP_VPIX_FRAME_BYTES] ATTRIBUTE_ALIGN(32);
static int selftest_ok, selftest_released, selftest_converted, selftest_sci_clean;
/* The self-test's OWN presentation accounting, kept out of `vq` entirely. */
static uint32_t selftest_presents, selftest_repeats;

static void display_selftest(void)
{
    struct gbp_vpix_stats st;
    uint32_t x, y, spins;
    int buf;

    for (y = 0; y < GBP_VPIX_HEIGHT; y++) {
        for (x = 0; x < GBP_VPIX_WIDTH; x++) {
            /* a coordinate gradient, and deliberately NOT any stimulus value */
            const uint16_t w = (uint16_t)(((x >> 3) << 10) | ((y >> 3) << 5) | ((x ^ y) & 0x1Fu));
            const size_t o = gbp_vpix_raw_offset(x, y);
            selftest_raw[o + 0] = 0x5Au;                  /* byte 0: never read */
            selftest_raw[o + 1] = (uint8_t)(w >> 8);
            selftest_raw[o + 2] = 0xA5u;                  /* byte 2: never read */
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
    /* §V5.46 / R1. The self-test DOES get a lifecycle, because a stage that is
     * traced only sometimes is a stage nobody can audit — but it is opened with
     * GBP_VDISP_KEY_NONE and the SELFTEST flag, so it can never be mistaken for
     * a source frame and can never acquire a real frame index. */
    tex_life[buf] = gbp_vdisp_take(&disp, GBP_VDISP_KEY_NONE, 0u, 0u, 0u,
                                   0u, gettime(), VIDEO_GetRetraceCount(),
                                   (uint16_t)buf, 0, 1);
    gbp_vdisp_convert_done(&disp, tex_life[buf], gettime(), 0u);
    submit_ready(buf, 0);        /* NULL: this frame is not a queue frame (R1) */

    /* Wait for the callback HERE and nowhere else: this runs before the capture
     * opens, so a bounded spin costs the device nothing. If the token never
     * fires, that is itself the finding and it is reported rather than hidden. */
    for (spins = 0; spins < 600u && gbp_vpresent_inflight(&present); spins++) VIDEO_WaitVSync();
    selftest_released = gbp_vpresent_inflight(&present) ? 0 : 1;
    /* R1, asserted rather than assumed: every scientific counter must still be
     * at its initial value. This is the state the probe is entered in, and a
     * future edit that routes the self-test back through the queue makes this
     * ZERO — which the Dolphin smoke fails on. */
    selftest_sci_clean = gbp_vqueue_pristine(&vq);
    selftest_ok = (selftest_converted && selftest_released && selftest_sci_clean &&
                   gbp_vpresent_consistent(&present) &&
                   gbp_vpresent_invariant_failures(&present) == 0u) ? 1 : 0;
}

static void pump(void *user)
{
    uint32_t t0, t1, row, n;
    (void)user;

    /* A READY buffer whose submit was refused because a token was still pending
     * gets another chance here, before any new work is started. Re-offering it
     * costs one state read and keeps the newest converted frame moving. */
    {
        uint32_t i;
        for (i = 0; i < GBP_VPRESENT_TEX_BUFFERS; i++)
            if (present.tex[i] == GBP_VPRESENT_READY) { submit_ready((int)i, &vq); break; }
    }

    if (!conv.active) {
        int buf;
        /* Nothing in flight: take the newest published frame, if the GP has
         * given a buffer back. With no free buffer the descriptor is LEFT in the
         * mailbox, so the producer's newest-wins rule keeps it fresh rather than
         * this code choosing which frame to lose. */
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
        /* §V5.46. The key is the ASSEMBLER's frame index, which the descriptor
         * already carries; nothing here decodes a stimulus or reads a pixel.
         * `in_window` is the witness's own ARMED latch, so the trace can say
         * which lifecycles belong to the qualified scientific population
         * without OGBPIDX1 taking any part in the decision. */
        conv.life = gbp_vdisp_take(&disp, conv.desc.frame_index, conv.desc.seq,
                                   conv.desc.slot, conv.desc.flags,
                                   conv.desc.t_last, gettime(),
                                   VIDEO_GetRetraceCount(), (uint16_t)buf,
                                   gbp_vwitness_armed(&wit), 0);
        tex_life[buf] = conv.life;
    }

    t0 = (uint32_t)gettick();
    if (conv.next_row == 0u) gbp_vdisp_convert_first(&disp, conv.life, gettime());
    for (n = 0; n < STREAM_SLICE_TILE_ROWS && conv.next_row < GBP_VPIX_BLOCKS; n++) {
        const uint8_t *blk;
        row = conv.next_row;
        blk = gbp_vstate_ring_block(pump_state, conv.desc.slot, row);
        if (!blk) {
            /* The raw is unreadable, which the ring's own bounds check makes
             * unreachable for a published descriptor. `stream-0001` marked the
             * frame complete here and claimed "the guard below rejects" — it does
             * not: the generation guard checks the publish distance, not whether
             * the conversion finished, so a half-converted texture would have
             * been presented (§V5.26 F5). Reject it HERE instead. */
            (void)gbp_vpresent_abandon(&present, (int)conv.buf);
            gbp_vdisp_abandon(&disp, conv.life, (uint16_t)GBP_VDISP_D_ABANDONED_NO_RAW);
            tex_life[conv.buf] = -1;
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
        /* Bounded aggregate, in the queue, so the first physical run can publish
         * the distribution of what the consumer cost (§V5.26.5). */
        gbp_vqueue_pump_slice(&vq, d, conv.next_row >= GBP_VPIX_BLOCKS);
    }

    if (conv.next_row < GBP_VPIX_BLOCKS) return;      /* more slices to come */

    /* The frame is converted. Step 3 and 4 of the generation guard (§V5.7):
     * only now do we ask whether the producer reused the slot underneath us. */
    if (!gbp_vqueue_commit(&vq, gbp_vqueue_still_valid(&vq, &conv.desc), conv.ticks)) {
        /* Consumer overrun. The half-and-half image is discarded WHOLE and the
         * screen keeps the previous frame; two generations never mix. The buffer
         * goes back through the module, which refuses to take back a SUBMITTED
         * one — it cannot be submitted yet, and that is asserted rather than
         * assumed. */
        (void)gbp_vpresent_abandon(&present, (int)conv.buf);
        gbp_vdisp_abandon(&disp, conv.life, (uint16_t)GBP_VDISP_D_SLOT_OVERRUN);
        tex_life[conv.buf] = -1;
        conv.active = 0u;
        return;
    }

    flag15_last_count = conv.stats.flag15_count;
    if (conv.stats.flag15_coords) {
        flag15_last_x = conv.stats.flag15_x[0];
        flag15_last_y = conv.stats.flag15_y[0];
    }

    /* Cache coherency, in the one order that is correct: the CPU has finished
     * writing, so flush EXACTLY this buffer, and only then may the GP be told
     * about it. Nothing above this line is visible to the GP; nothing below it
     * may write the buffer again until the draw-done callback frees it. */
    DCFlushRange(tex_buf[conv.buf], GBP_VPIX_TEX_BYTES);
    gbp_vdisp_convert_done(&disp, conv.life, gettime(), conv.ticks);
    (void)gbp_vpresent_fill_done(&present, (int)conv.buf);   /* CPU_FILLING -> READY */
    conv.active = 0u;
    submit_ready((int)conv.buf, &vq);
}

/* Hand a READY texture to the GP and put the result on screen — or decline,
 * without waiting for anything. Split out of `pump()` because it is the part
 * whose ORDERING is the safety argument, and because a READY buffer may have to
 * wait for the previous token before it can go. */
static void submit_ready(int buf, struct gbp_vqueue *account)
{
    int xfb, cur, pend, inflight;
    uint8_t tstate[2];
    uint64_t t_dec;
    uint32_t rt;
    const int life = tex_life[buf];

    /* ONE token in flight. A refusal here is normal back-pressure: the buffer
     * stays READY and is offered again on the next slice boundary, and the
     * producer is never involved.
     *
     * §V5.46: a refusal is COUNTED ON THE LIFECYCLE and is deliberately NOT an
     * event. pump() runs ~224 000 times in a 35 s run, so one event per refusal
     * would be unbounded; the count tells an analyzer how long a frame waited
     * without letting the trace explode. (Run 4 refused 0 times.) */
    if (!gbp_vpresent_submit(&present, buf)) { gbp_vdisp_submit_refused(&disp, life); return; }
    gbp_vdisp_submit(&disp, life, gettime());

    GX_InvalidateTexAll();
    GX_InitTexObj(&tex_obj, tex_buf[buf], GBP_VPIX_WIDTH, GBP_VPIX_HEIGHT,
                  GX_TF_RGB5A3, GX_CLAMP, GX_CLAMP, GX_FALSE);
    GX_InitTexObjFilterMode(&tex_obj, GX_NEAR, GX_NEAR);   /* no filtering: Phase 9 */
    GX_LoadTexObj(&tex_obj, GX_TEXMAP0);
    draw_quad();
    /* Marked SUBMITTED before the token is armed (gbp_vpresent_submit did it),
     * so the callback can never observe a half-built submission. */
    GX_SetDrawDone();                 /* NON-blocking: on_draw_done() releases it */

    /* The framebuffer is a SEPARATE question: a DrawDone says nothing about the
     * VI. Copy only into a buffer the VI is neither scanning nor about to. */
    cur = xfb_current_index();
    /* §V5.46: the clock and the retrace ordinal are read BEFORE the decision, so
     * the event timestamps the decision and not its consequences. */
    t_dec = gettime();
    rt = VIDEO_GetRetraceCount();
    xfb = gbp_vpresent_xfb_target(&present, cur);
    /* Read AFTER xfb_target() and BEFORE xfb_handed(): xfb_target() retires a
     * hand-over the VI has picked up, and xfb_handed() installs a new one, so
     * this is the only window in which `xfb_pending` is what the loop actually
     * used. Snapshotting it later would record the consequence as the cause. */
    pend = present.xfb_pending;
    inflight = gbp_vpresent_inflight(&present);
    tstate[0] = present.tex[0];
    tstate[1] = present.tex[1];
    if (xfb >= 0) {
        GX_CopyDisp(xfb_stream_buf[xfb], GX_TRUE);
        GX_Flush();
        VIDEO_SetNextFramebuffer(xfb_stream_buf[xfb]);
        VIDEO_Flush();                /* register write only; NEVER VIDEO_WaitVSync here */
        gbp_vpresent_xfb_handed(&present, xfb);
        /* R1: only a frame that came OUT of the queue goes back INTO its
         * counters. The self-test passes NULL and is counted separately. */
        if (account) gbp_vqueue_note_presented(account); else selftest_presents++;
    } else {
        GX_Flush();                   /* the draw still has to reach the GP */
        if (account) gbp_vqueue_note_repeat(account); else selftest_repeats++;
    }
    gbp_vdisp_decision(&disp, life, t_dec, rt, cur, pend, xfb,
                       (uint16_t)(present.shutting_down ? GBP_VDISP_R_XFB_SHUTDOWN
                                                        : GBP_VDISP_R_XFB_BUSY),
                       tstate, inflight,
                       /* what the producer had waiting, read from the mailbox
                        * the consumer takes from -- one field, no clock, no copy */
                       (account && account->has_pending)
                           ? account->pending.frame_index : GBP_VDISP_KEY_NONE);
    tex_life[buf] = -1;               /* the lifecycle is closed; the slot is free to be re-keyed */
}

/* The streaming sink: one SD write per record, and ONLY after the teardown has
 * completed and the Game Boy Player has been restored (§V5.39.8). No filesystem
 * call exists anywhere in the capture path; a card failure here is reported
 * separately and cannot change what the run observed. */
static int sink_sd(void *ctx, const uint8_t *data, uint32_t len)
{
    return sdlog_stream_write((struct sdlog_stream *)ctx, data, len);
}

/* The ONLY transient buffer the save uses: one record. The 8.4 MiB store is
 * never copied in full. */
static uint8_t dump_chunk[GBP_VIDXDUMP_RECORD_SIZE];

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

    video_setup();
    gx_setup();
    PAD_Init();
    gecko_present = usb_isgeckoalive(GECKO_CHANNEL);
    opengbp_ident_format(ident_text, sizeof ident_text, &ident);

    printf("\n  Open-GBP " TEST_ID "  (NOT PHYSICALLY VALIDATED — first streaming candidate)\n");
    printf("  Build : %s   Commit: %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("  libogc: %s   Gecko: %s\n", _V_STRING, gecko_present ? "yes" : "no");
    printf("  %s\n\n", opengbp_ident_marker);

    snprintf(line, sizeof line, "OPENGBP-STREAM READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);

    gbp_vstate_config_default(&cfg);
    gbp_vstate_config_timebase(&cfg, tb_hz);
    /* No episode raw store: streaming does not use GBP-VIDEO-002's change
     * detector, and 2.81 MiB of it would sit unused. */
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
        for (k = 0; k < STREAM_TEX_BUFFERS; k++) tex_life[k] = -1;
    }
    (void)gbp_vdisp_init(&disp, disp_life, GBP_VDISP_LIFE_CAP, disp_ev, GBP_VDISP_EVENT_CAP);
    conv.life = -1;
    pump_state = &vstate;
    vq.pump = pump;
    vq.pump_user = 0;
    cfg.stream = &vq;
    /* SOURCE-LAYER retention, and the run's PRIMARY stop condition. The
     * valid-seconds target stays configured as a BOUND, never as the thing that
     * ends the experiment: `stream-0004` showed 30 valid seconds are 44.3 wall
     * seconds and 2 648 closed frames (GBP-HW-151), so a witness store sized
     * from a clock is sized from the wrong quantity. */
    if (gbp_vwitness_init(&wit, &witness_store[0][0], witness_meta,
                          GBP_VWITNESS_TARGET, GBP_VWITNESS_TARGET) != 0) {
        printf("  WITNESS init FAILED\n");
        return 1;
    }
    /* THE PROSPECTIVE STRUCTURAL QUALIFICATION (§V5.44). The assembler runs
     * normally through the warm-up -- transport, service and frame assembly are
     * untouched -- but nothing is RETAINED until 64 consecutive structurally
     * qualifying frames have closed and a fresh block-0 boundary arrives. Run 3
     * measured a correct producer and was still refused because the startup
     * transient sat inside the population under test (GBP-HW-172); this moves
     * the boundary, and moves it ONLINE, without touching the analyzer. */
    gbp_vwitness_set_qualification(&wit, GBP_VWITNESS_QUAL_REQUIRED);
    cfg.witness = &wit;

    /* The display path, walked once from a synthetic frame BEFORE any device is
     * touched, so it stops being dead code (§V5.26.4). The result goes out on the
     * Gecko channel immediately, so an auxiliary Dolphin run can ASSERT that the
     * path executed instead of the operator assuming it did. */
    display_selftest();
    snprintf(line, sizeof line,
             "OPENGBP-STREAM SELFTEST ok=%d converted=%d released=%d submits=%lu drawdone=%lu releases=%lu xfb=%lu sci_clean=%d inv_fail=%lu\n",
             selftest_ok, selftest_converted, selftest_released,
             (unsigned long)present.submit_success, (unsigned long)present.drawdone_callbacks,
             (unsigned long)present.texture_releases, (unsigned long)selftest_presents,
             selftest_sci_clean, (unsigned long)gbp_vpresent_invariant_failures(&present));
    gecko_puts(line);
    printf("  SELF-TEST display path: %s (converted=%d, texture released by the GP=%d)\n",
           selftest_ok ? "ok" : "NOT OK", selftest_converted, selftest_released);
    /* R1, on screen as well as on the wire: the queue must be untouched here. */
    printf("  SELF-TEST accounting: %lu present / %lu repeat of its OWN, scientific counters %s\n",
           (unsigned long)selftest_presents, (unsigned long)selftest_repeats,
           selftest_sci_clean ? "CLEAN" : "CONTAMINATED");

    /* The validated pre-handler wait, unchanged (§V5.20, GBP-HW-120). */
    cfg.prehandler_wait_ms = 5000u;
    cfg.hard_wallclock_s = STREAM_SAFETY_SECONDS;
    cfg.hard_wallclock_ticks = (uint64_t)tb_hz * STREAM_SAFETY_SECONDS;
    cfg.max_deliveries = STREAM_MAX_DELIVERIES;
    /* The SCIENTIFIC capture duration and the SAFETY cap are different things
     * and are configured separately (§V5.23). The duration is what the run is
     * measured over; the safety cap only stops a run that has gone wrong. */
    cfg.min_valid_observation_s = STREAM_CAPTURE_SECONDS;
    cfg.min_valid_observation_ticks = (uint64_t)tb_hz * STREAM_CAPTURE_SECONDS;
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
    ringlog_printf(&rl, "ENVSTREAM capture_s=%lu safety_s=%lu slice_tile_rows=%u tex_buffers=%u tex_bytes=%u ring_slots=%lu",
                   (unsigned long)STREAM_CAPTURE_SECONDS, (unsigned long)STREAM_SAFETY_SECONDS,
                   (unsigned)STREAM_SLICE_TILE_ROWS, (unsigned)STREAM_TEX_BUFFERS,
                   (unsigned)GBP_VPIX_TEX_BYTES, (unsigned long)gbp_vstate_ring_slots(&vstate));
    /* THE STORES AS CONFIGURED, beside what the contract requires, and with the
     * first unmet field by name. `stream-0002` aborted here with a reason that
     * named the gate and not the field, and the line that should have shown the
     * mismatch printed compile-time constants instead (§V5.29.6). Both are
     * fixed: this is the POC's own diagnostic, the library's generic gate is
     * unchanged, and neither is weakened. */
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
            printf("  frames %lu/%lu  events %lu/%lu  raw_ring %lu/%lu (%lu/%lu slots)  episode_raw %lu/%lu  audio_raw %lu/%lu\n",
                   (unsigned long)vstate.frames_cap, (unsigned long)GBP_VSTATE_MAX_FRAMES,
                   (unsigned long)vstate.events_cap, (unsigned long)GBP_VSTATE_MAX_EVENTS,
                   (unsigned long)vstate.raw_ring_cap, (unsigned long)GBP_VSTATE_RAW_RING_BYTES,
                   (unsigned long)vstate.raw_ring_slots, (unsigned long)GBP_VSTATE_RAW_RING_SLOTS_MIN,
                   (unsigned long)vstate.episode_raw_cap, (unsigned long)GBP_VSTATE_EPISODE_RAW_BYTES,
                   (unsigned long)vstate.audio_raw_cap, (unsigned long)GBP_VSTATE_AUDIO_RAW_BYTES);
            printf("  configured %llu B, required %llu B. The probe was NOT entered.\n",
                   (unsigned long long)gbp_vstate_configured_bytes(&vstate),
                   (unsigned long long)gbp_vstate_required_capacity_bytes());
            gecko_puts("OPENGBP-STREAM STORAGE FATAL field=");
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
    /* §V5.39.11: the memory audit, MEASURED at run time rather than asserted
     * from a linker map. The witness store is the largest single object this
     * program owns, so the arena that survives it is a fact the log must carry —
     * a build that no longer fits would otherwise fail on the console, in front
     * of the operator, with the cartridge already running. */
    {
        extern char __bss_end[];
        uint32_t lo = (uint32_t)(size_t)SYS_GetArena1Lo();
        uint32_t hi = (uint32_t)(size_t)SYS_GetArena1Hi();
        ringlog_printf(&rl, "ENVMEM bss_end=%08lx arena1_lo=%08lx arena1_hi=%08lx arena1_free=%lu "
                            "witness=%lu witness_meta=%lu witness_rec=%lu xfb=3x%lu",
                       (unsigned long)(size_t)__bss_end, (unsigned long)lo, (unsigned long)hi,
                       (unsigned long)(hi > lo ? hi - lo : 0u),
                       (unsigned long)sizeof witness_store, (unsigned long)sizeof witness_meta,
                       (unsigned long)GBP_VIDXDUMP_RECORD_SIZE,
                       (unsigned long)VIDEO_GetFrameBufferSize(rmode));
    }

    hsp_backend_init(&hsp, dma_buffer, (uint32_t)millisecs_to_ticks(DMA_TIMEOUT_MS));
    hsp_backend_transport(&hsp, &t);
    hsp_backend_irq_transport_ext(&hsp, &t);

    printf("  Sequence: the vstate-0004 service path VERBATIM — 003A, one-shot handler, READ -> AUDIO\n");
    printf("            -> VIDEO -> ACK -> PI clean -> signature + assembly -> IRQ := 0000 -> next cause.\n");
    printf("  New:      after the RE-ARM, ONE bounded conversion slice (%u tile row). The screen is\n",
           (unsigned)STREAM_SLICE_TILE_ROWS);
    printf("            drawn from a converted frame only; an incomplete or quarantined frame NEVER is.\n");
    printf("  Pre-handler wait: %lu ms with the AGB running and PI masked, before any capture.\n",
           (unsigned long)cfg.prehandler_wait_ms);
    printf("  Capture %lu s, safety cap %lu s. DO NOT PRESS ANYTHING during the run.\n\n",
           (unsigned long)STREAM_CAPTURE_SECONDS, (unsigned long)STREAM_SAFETY_SECONDS);
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

    gbp_vstate_probe_run(&t, &rl, &cfg, &res);     /* returns only after the teardown */
    a = &res.a;

    /* ---- display shutdown, in the one order that is safe (§V5.26 F6) ----
     *
     * Everything below runs AFTER the probe has torn down and restored the Game
     * Boy Player, which is why a blocking GX wait is permissible here and would
     * never have been permissible in the service loop.
     *
     * 1. stop accepting new fills and submissions;
     * 2. drain the one token that may still be pending — bounded, and only now;
     * 3. restore the previous draw-done callback, so nothing can call into this
     *    program's state afterwards;
     * 4. only then may the buffers be considered dead.
     *
     * `stream-0001` did none of this: its callback stayed installed for ever. */
    gbp_vpresent_shutdown(&present);
    cfg.stream = 0;                     /* no further publish can reach the queue */
    vq.pump = 0;                        /* and no further slice can be pumped     */
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
    /* The counters, in three groups that must never be read as one another:
     * what the DEVICE did, what WE did to its frames, and what the SCREEN did. */
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
    /* P1: a converted frame still waiting for a submit is a real, bounded state.
     * Reporting it means a nonzero residual is visible instead of hiding inside
     * `balanced`. Zero is the expected value at a clean end. */
    ringlog_printf(&rl, "STREAMDISP converted=%lu presented=%lu overrun=%lu repeated=%lu undispositioned=%lu identity=converted==presented+overrun+repeated(+residual<=%u)",
                   (unsigned long)vq.consumer_frames_converted,
                   (unsigned long)vq.consumer_frames_presented,
                   (unsigned long)vq.consumer_slot_overrun,
                   (unsigned long)vq.display_frames_repeated,
                   (unsigned long)gbp_vqueue_undispositioned(&vq),
                   (unsigned)GBP_VQUEUE_MAX_UNDISPOSITIONED);
    /* The counters that answer §V5.26.5: what the slice cost, and what the GBP
     * was doing either side of it. */
    ringlog_printf(&rl, "STREAMPUMP calls=%lu slices=%lu completed=%lu skipped_cause_pending=%lu pending_before=%lu pending_after=%lu arrived_during=%lu",
                   (unsigned long)vq.pump_calls, (unsigned long)vq.pump_slices_started,
                   (unsigned long)vq.pump_slices_completed, (unsigned long)vq.pump_skipped_cause_pending,
                   (unsigned long)vq.cause_pending_before_pump, (unsigned long)vq.cause_pending_after_pump,
                   (unsigned long)vq.cause_arrived_during_pump);
    ringlog_printf(&rl, "STREAMPUMPT ticks_min=%lu ticks_max=%lu ticks_mean=%lu n=%lu tile_rows_per_slice=%u",
                   (unsigned long)(vq.pump_ticks_n ? vq.pump_ticks_min : 0u), (unsigned long)vq.pump_ticks_max,
                   (unsigned long)gbp_vqueue_pump_ticks_mean(&vq), (unsigned long)vq.pump_ticks_n,
                   (unsigned)STREAM_SLICE_TILE_ROWS);
    /* The ownership machine, whose defect rejected stream-0001. */
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
    /* R8: the two are DIFFERENT claims and are printed apart. `consistent_at_end`
     * is the last instant; `invariant_failures` is every transition of the run,
     * latched even if the state healed afterwards. */
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
    /* The retained population, and the cost of retaining it. These are three
     * different facts and they never share a line with the queue's: what the
     * SOURCE produced, what was STORED, and what the storing cost. */
    /* §V5.44.5: the warm-up is REPORTED, never hidden. A reader must be able to
     * see that a startup transient happened and that it fell outside the
     * scientific window, rather than take it on trust. */
    ringlog_printf(&rl, "WITQUAL policy=consecutive_structural_complete required=%lu state=%lu "
                        "streak_max=%lu resets=%lu warmup_frames=%lu warmup_disqualified=%lu "
                        "qualify_frame=%ld qualified=%d armed=%d "
                        "window_first_block=%d first_record_frame=%ld",
                   (unsigned long)wit.qual_required, (unsigned long)wit.qual_state,
                   (unsigned long)wit.qual_streak_max, (unsigned long)wit.qual_resets,
                   (unsigned long)wit.warmup_frames, (unsigned long)wit.warmup_disqualified,
                   (wit.qual_frame_index == 0xFFFFFFFFu) ? -1L : (long)wit.qual_frame_index,
                   gbp_vwitness_qualified(&wit), gbp_vwitness_armed(&wit),
                   /* MEASURED, not asserted: a literal 0 here would print the
                    * right answer even when the window opened mid-frame. */
                   (wit.n && (wit.meta[0].present & 1u)) ? 0 : -1,
                   wit.n ? (long)wit.meta[0].frame_index : -1L);
    {
        /* §V5.46. The aggregate the trace itself can be audited by: how many
         * lifecycles and decisions were recorded, whether either array filled,
         * and whether every token that fired found the frame it belonged to. */
        uint32_t k, in_win = 0u, held = 0u, selected = 0u;
        for (k = 0; k < disp.life_n; k++) {
            const struct gbp_vdisp_life *r = gbp_vdisp_life_at(&disp, k);
            if (!r) continue;
            if (r->life_flags & GBP_VDISP_F_IN_WINDOW) in_win++;
            if (r->disposition == GBP_VDISP_D_HOLD_PREVIOUS) held++;
            if (r->disposition == GBP_VDISP_D_SELECTED_NEW) selected++;
        }
        ringlog_printf(&rl, "STREAMDISP life=%lu/%lu events=%lu/%lu decisions=%lu in_window=%lu "
                            "selected_new=%lu hold_previous=%lu life_overflow=%lu event_overflow=%lu "
                            "drawdone_unmatched=%lu intact=%d tex_slots=%lu xfb_slots=%lu",
                       (unsigned long)disp.life_n, (unsigned long)disp.life_cap,
                       (unsigned long)disp.ev_n, (unsigned long)disp.ev_cap,
                       (unsigned long)disp.decisions, (unsigned long)in_win,
                       (unsigned long)selected, (unsigned long)held,
                       (unsigned long)disp.life_overflow, (unsigned long)disp.ev_overflow,
                       (unsigned long)disp.drawdone_unmatched, gbp_vdisp_intact(&disp),
                       (unsigned long)GBP_VDISP_TEX_SLOTS,
                       (unsigned long)GBP_VPRESENT_XFB_BUFFERS);
    }
    ringlog_printf(&rl, "STREAMWIT records=%lu/%lu target=%lu frames_seen=%lu discarded=%lu "
                        "staged=%lu placed=%lu out_of_range=%lu store_full=%d target_reached=%d",
                   (unsigned long)wit.n, (unsigned long)wit.cap, (unsigned long)wit.target,
                   (unsigned long)wit.frames_seen, (unsigned long)wit.frames_discarded,
                   (unsigned long)wit.blocks_staged, (unsigned long)wit.blocks_placed,
                   (unsigned long)wit.blocks_out_of_range,
                   gbp_vwitness_store_full(&wit), gbp_vwitness_target_reached(&wit));
    ringlog_printf(&rl, "STREAMWITT copy_ticks_min=%lu copy_ticks_max=%lu copy_ticks_mean=%lu n=%lu tb_hz=%lu",
                   (unsigned long)(wit.copy_ticks_n ? wit.copy_ticks_min : 0u),
                   (unsigned long)wit.copy_ticks_max,
                   (unsigned long)gbp_vwitness_copy_ticks_mean(&wit),
                   (unsigned long)wit.copy_ticks_n, (unsigned long)tb_hz);
    ringlog_printf(&rl, "STREAMPACE publish_min=%lu publish_max=%lu publish_mean=%lu n=%lu convert_min=%lu convert_max=%lu convert_mean=%lu n=%lu",
                   (unsigned long)(vq.publish_interval_n ? vq.publish_interval_min : 0u),
                   (unsigned long)vq.publish_interval_max, (unsigned long)gbp_vqueue_publish_interval_mean(&vq),
                   (unsigned long)vq.publish_interval_n,
                   (unsigned long)(vq.convert_ticks_n ? vq.convert_ticks_min : 0u),
                   (unsigned long)vq.convert_ticks_max, (unsigned long)gbp_vqueue_convert_ticks_mean(&vq),
                   (unsigned long)vq.convert_ticks_n);
    /* flag15 is REPORTED and never consumed: U-GBP-034 is open, and the texel's
     * bit 15 is a presentation rule, not a reading of this observation. */
    ringlog_printf(&rl, "STREAMFLAG15 last_count=%lu first_x=%lu first_y=%lu note=reported_not_interpreted",
                   (unsigned long)flag15_last_count, (unsigned long)flag15_last_x, (unsigned long)flag15_last_y);

    gbp_vstate_summary(&res, summary, sizeof summary);

    printf("\n  HARDWARE status=%s (%s) reason=%s stop=%s restore=%s teardown=%s\n", res.status_name, res.status_class,
           res.reason ? res.reason : "-", gbp_vstate_stop_name(res.stop), res.restore_ok ? "ok" : "ERROR",
           res.teardown_variant ? res.teardown_variant : "-");
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
    printf("  DISPOSE converted %lu = presented %lu + overrun %lu + repeated %lu, waiting %lu (bound %u)\n",
           (unsigned long)vq.consumer_frames_converted, (unsigned long)vq.consumer_frames_presented,
           (unsigned long)vq.consumer_slot_overrun, (unsigned long)vq.display_frames_repeated,
           (unsigned long)gbp_vqueue_undispositioned(&vq), (unsigned)GBP_VQUEUE_MAX_UNDISPOSITIONED);
    printf("  PACING  publish %lu/%lu/%lu ticks (min/mean/max, n=%lu)   convert %lu/%lu/%lu (n=%lu)\n",
           (unsigned long)(vq.publish_interval_n ? vq.publish_interval_min : 0u),
           (unsigned long)gbp_vqueue_publish_interval_mean(&vq), (unsigned long)vq.publish_interval_max,
           (unsigned long)vq.publish_interval_n,
           (unsigned long)(vq.convert_ticks_n ? vq.convert_ticks_min : 0u),
           (unsigned long)gbp_vqueue_convert_ticks_mean(&vq), (unsigned long)vq.convert_ticks_max,
           (unsigned long)vq.convert_ticks_n);
    printf("  PUMP    %lu calls, %lu slices (%lu..%lu ticks, mean %lu); SKIPPED %lu because a cause was already latched\n",
           (unsigned long)vq.pump_calls, (unsigned long)vq.pump_slices_started,
           (unsigned long)(vq.pump_ticks_n ? vq.pump_ticks_min : 0u), (unsigned long)vq.pump_ticks_max,
           (unsigned long)gbp_vqueue_pump_ticks_mean(&vq), (unsigned long)vq.pump_skipped_cause_pending);
    printf("  CAUSE   pending before %lu / after %lu; arrived DURING a slice %lu  (a coincidence count, not causality)\n",
           (unsigned long)vq.cause_pending_before_pump, (unsigned long)vq.cause_pending_after_pump,
           (unsigned long)vq.cause_arrived_during_pump);
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
    printf("  SELFTEST %s, its own presents %lu / repeats %lu, scientific counters %s (R1 retired)\n",
           selftest_ok ? "ok" : "NOT OK", (unsigned long)selftest_presents,
           (unsigned long)selftest_repeats, selftest_sci_clean ? "CLEAN" : "CONTAMINATED");
    printf("  FLAG15  last frame carried %lu set word(s), first at (%lu,%lu) — REPORTED, NOT INTERPRETED (U-GBP-034)\n",
           (unsigned long)flag15_last_count, (unsigned long)flag15_last_x, (unsigned long)flag15_last_y);
    printf("  RESTORE control=%d stop=%d cleanup=%d arinfo=%d handler=%d mask_ok=%d\n",
           a->control_restore_ok, a->irq_stop_write_ok, a->pi_cleanup_performed, a->arinfo_restore_ok,
           res.h.handler_restored, res.h.mask_ok);
    printf("\n  THIS RUN PROVES NOTHING ON ITS OWN. Sustained streaming is judged offline against\n");
    printf("  HARDWARE_TESTS §V5.21, and the duration is still a DESIGN DECISION (§V5.5).\n");

    /* The two verdicts an auxiliary run must be able to ASSERT without a screen:
     * the counters balance with NO correction of any kind (R1 retired), and the
     * ownership invariants never broke DURING the run (R8). `stream-0002` could
     * report neither — its counters were contaminated before the capture opened
     * and its invariants were only ever sampled at the end. */
    snprintf(line, sizeof line,
             "OPENGBP-STREAM COUNTERS balanced=%d sci_clean_at_probe=%d inv_fail=%lu inv_checks=%lu consistent_at_end=%d storage_fault=%s\n",
             gbp_vqueue_balanced(&vq), selftest_sci_clean,
             (unsigned long)gbp_vpresent_invariant_failures(&present),
             (unsigned long)gbp_vpresent_invariant_checks(&present),
             gbp_vpresent_consistent(&present),
             gbp_vstate_storage_fault(&vstate) ? gbp_vstate_storage_fault(&vstate) : "-");
    gecko_puts(line);

    printf("  WITQUAL required %lu, warm-up %lu frames (%lu disqualified, %lu resets), "
           "streak_max %lu, armed=%d\n",
           (unsigned long)wit.qual_required, (unsigned long)wit.warmup_frames,
           (unsigned long)wit.warmup_disqualified, (unsigned long)wit.qual_resets,
           (unsigned long)wit.qual_streak_max, gbp_vwitness_armed(&wit));
    printf("  WITNESS %lu/%lu records (target %lu), %lu blocks placed, store_full=%d, %lu ticks mean\n",
           (unsigned long)wit.n, (unsigned long)wit.cap, (unsigned long)wit.target,
           (unsigned long)wit.blocks_placed, gbp_vwitness_store_full(&wit),
           (unsigned long)gbp_vwitness_copy_ticks_mean(&wit));
    printf("\n  X = save log + witness sidecar to SD    START = exit    POWER CYCLE REQUIRED\n");
    for (;;) {
        VIDEO_WaitVSync();
        PAD_ScanPads();
        if (!saved && (PAD_ButtonsDown(0) & PAD_BUTTON_X)) {
            char path[128] = "";
            char extra[240];
            char status2[160] = "sidecar not attempted";
            struct sdlog_stream stream;
            struct gbp_vidxdump_info info;
            uint64_t written = 0;
            long n = -1;
            int rc, rc2 = -9;
            /* The log names the sidecar AND its format, so a reader never has to
             * guess which contract the bytes were written under. */
            snprintf(extra, sizeof extra,
                     "libogc=%s gecko=%d power_cycle_required=%d sidecar=%s_%s-idxcap.bin "
                     "format=OGBPIDXCAP1_v%u capture_s=%lu safety_s=%lu witness_target=%lu",
                     _V_STRING, gecko_present, res.power_cycle_required, TEST_ID, OPENGBP_BUILD_ID,
                     (unsigned)GBP_VIDXDUMP_VERSION,
                     (unsigned long)STREAM_CAPTURE_SECONDS, (unsigned long)STREAM_SAFETY_SECONDS,
                     (unsigned long)wit.target);
            rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl,
                            status, sizeof status, path, sizeof path);
            /* The witness sidecar, streamed record by record with a running
             * CRC-32 and a per-record CRC. The layout is proven before a byte is
             * written, and no second copy of the store exists at any point. */
            memset(&info, 0, sizeof info);
            info.tb_hz = tb_hz;
            info.stop_reason = (uint16_t)res.stop;
            info.status_code = (uint16_t)res.status;
            if (res.service_ok) info.flags |= GBP_VIDXDUMP_FLAG_SERVICE_OK;
            if (res.stop == GBP_VSTATE_STOP_WITNESS_TARGET) info.flags |= GBP_VIDXDUMP_FLAG_STOP_IS_TARGET;
            if (gbp_vidxdump_set_identity(&info, TEST_ID, OPENGBP_BUILD_ID,
                                          OPENGBP_APP_NAME, OPENGBP_GIT_COMMIT) != 0) {
                snprintf(status2, sizeof status2, "sidecar not written: an identity does not fit");
            } else if (sdlog_stream_open(&stream, TEST_ID, OPENGBP_BUILD_ID, "-idxcap.bin",
                                         status2, sizeof status2) != 0) {
                /* status2 already explains */
            } else {
                n = gbp_vidxdump_stream(&info, &wit, dump_chunk, sizeof dump_chunk,
                                        sink_sd, &stream, &written);
                rc2 = sdlog_stream_close(&stream, status2, sizeof status2);
                if (n < 0 && rc2 == 0) rc2 = -5;
            }
            /* §V5.46: the SECOND sidecar, a different layer and a different
             * file. It is written after the witness sidecar and after the
             * teardown, from fixed RAM, through the same streaming sink; there
             * is no filesystem call and no CRC anywhere in the capture path. */
            {
                struct sdlog_stream ds;
                char dstat[96];
                int drc = -1;
                memset(&disp_info, 0, sizeof disp_info);
                disp_info.tb_hz = tb_hz;
                disp_info.xfb_slots = GBP_VPRESENT_XFB_BUFFERS;
                if (gbp_vdispdump_set_identity(&disp_info, TEST_ID, OPENGBP_BUILD_ID,
                                               OPENGBP_APP_NAME, OPENGBP_GIT_COMMIT) != 0) {
                    snprintf(dstat, sizeof dstat, "disp sidecar not written: an identity does not fit");
                } else if (sdlog_stream_open(&ds, TEST_ID, OPENGBP_BUILD_ID, "-disp.bin",
                                             dstat, sizeof dstat) != 0) {
                    /* dstat already explains */
                } else {
                    uint64_t dw = 0;
                    disp_saved_bytes = gbp_vdispdump_stream(&disp_info, &disp, disp_chunk,
                                                            sizeof disp_chunk, sink_sd, &ds, &dw);
                    drc = sdlog_stream_close(&ds, dstat, sizeof dstat);
                    if (disp_saved_bytes < 0 && drc == 0) drc = -5;
                }
                disp_save_rc = drc;
                printf("  SAVE disp    %s   (OGBPDISP1 v%u, %lu life, %lu events)\n", dstat,
                       (unsigned)GBP_VDISPDUMP_VERSION, (unsigned long)disp_info.life_n,
                       (unsigned long)disp_info.event_n);
                snprintf(line, sizeof line,
                         "OPENGBP-STREAM SAVEDISP rc=%ld close=%d bytes=%lu life=%lu events=%lu "
                         "intact=%d header_crc32=%08lx total_crc32=%08lx\n",
                         disp_saved_bytes, drc, (unsigned long)disp_saved_bytes,
                         (unsigned long)disp_info.life_n, (unsigned long)disp_info.event_n,
                         gbp_vdisp_intact(&disp),
                         (unsigned long)disp_info.header_crc32, (unsigned long)disp_info.total_crc32);
                gecko_puts(line);
            }
            saved = (rc == 0 && rc2 == 0 && n > 0);
            printf("  SAVE log     %s\n", status);
            printf("  SAVE sidecar %s   (OGBPIDXCAP1 v%u, %lu records)\n", status2,
                   (unsigned)GBP_VIDXDUMP_VERSION, (unsigned long)info.records_n);
            snprintf(line, sizeof line,
                     "OPENGBP-STREAM SAVESIDECAR rc=%ld close=%d bytes=%lu records=%lu "
                     "header_crc32=%08lx total_crc32=%08lx\n",
                     n, rc2, (unsigned long)written, (unsigned long)info.records_n,
                     (unsigned long)info.header_crc32, (unsigned long)info.total_crc32);
            gecko_puts(line);
        }
        if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break;
    }
    for (i = 0; i < 1; i++) gecko_puts("OPENGBP-STREAM DONE\n");
    return 0;
}
