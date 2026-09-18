/*
 * Open-GBP GBP-VIDEO-004, build stream-0001 — the first sustained-streaming
 * candidate (HARDWARE_TESTS §V5). IMPLEMENTED AND HOST-VALIDATED; it has never
 * touched hardware, and nothing here claims sustained streaming works.
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
 * The slice size is argued from measurement, not taste: `gbp_vsig_block()`
 * already reads 3840 bytes inside this same path and cost 777-799 ticks
 * (19.2-19.7 us) in `color-0002`, against 164 us of slack between deliveries.
 * One tile row reads the same 3840 bytes and writes 1920. That is an argument
 * for the SIZE; whether it holds is what the physical run measures.
 *
 * ---- TEXTURE OWNERSHIP, ON THE REAL API ---------------------------------
 *
 * GX consumes a texture asynchronously, so "the CPU may refill this buffer" is a
 * question only the GP can answer. libogc2 answers it with
 * `GX_SetDrawDoneCallback()` + `GX_SetDrawDone()`: the GP raises the callback
 * when it has finished the submitted commands. Two texture buffers, each in one
 * of three states, and the CPU only ever fills a FREE one:
 *
 *     FREE  ->  CPU_FILLING  ->  SUBMITTED  ->  (draw-done callback)  ->  FREE
 *
 * `GX_DrawDone()` would have been simpler and it BLOCKS, which §V5.7 forbids in
 * this path. The callback form is the non-blocking one, and it is why the CPU
 * can never overwrite a texture the GP might still be reading.
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
 * Streaming does not need GBP-VIDEO-002's change detector, so the episode raw
 * store (2.81 MiB) is not allocated at all and the frame table is far smaller
 * than the colour probe's 16384 entries: this probe reports pacing aggregates,
 * not a per-frame history. The raw ring keeps FOUR slots, which is what gives
 * the generation guard its margin (§V3.24, §V5.7). */
#define STREAM_MAX_FRAMES 4096u
static struct gbp_vstate_frame frame_store[STREAM_MAX_FRAMES];                     /* 0.75 MiB */
static struct gbp_vstate_event event_store[GBP_VSTATE_MAX_EVENTS];                 /* 0.25 MiB */
static uint8_t raw_ring[GBP_VSTATE_RAW_RING_BYTES_4] ATTRIBUTE_ALIGN(32);          /* 0.70 MiB, DMA target */
static uint8_t audio_raw[GBP_VSTATE_AUDIO_RAW_BYTES] ATTRIBUTE_ALIGN(32);          /* 12 KiB, DMA target */
static struct gbp_vstate_cycle cyc_first[GBP_VSTATE_CYC_FIRST];
static struct gbp_vstate_cycle cyc_last[GBP_VSTATE_CYC_LAST];
static struct gbp_vstate_cycle cyc_anomaly[GBP_VSTATE_CYC_ANOMALY];
static struct gbp_vstate_cycle cyc_episode[GBP_VSTATE_CYC_EPISODE];
static struct gbp_vstate vstate;
static struct gbp_vstate_diag diag_store[GBP_VSTATE_MAX_DISAGREEMENTS];
static struct gbp_vqueue vq;

/* ---- the two texture buffers, and their ownership ---------------------- */
enum tex_state { TEX_FREE = 0, TEX_CPU_FILLING, TEX_SUBMITTED };
#define STREAM_TEX_BUFFERS 2u
static uint16_t tex_buf[STREAM_TEX_BUFFERS][GBP_VPIX_TEX_BYTES / 2u] ATTRIBUTE_ALIGN(32);  /* 2 x 75 KiB */
static volatile uint8_t tex_state[STREAM_TEX_BUFFERS];
static GXTexObj tex_obj;

/* A texture buffer must be a whole number of 32-byte cache lines, or a flush of
 * its exact size would touch memory it does not own. */
_Static_assert(GBP_VPIX_TEX_BYTES % 32u == 0u, "texture size must be cache-line aligned");
_Static_assert(GBP_VPIX_TEX_BYTES == 240u * 160u * 2u, "texture is 240x160 16-bit");
_Static_assert(GBP_VPIX_FRAME_BYTES == 40u * 0xF00u, "a frame is 40 blocks of 0xF00");
_Static_assert(STREAM_TEX_BUFFERS >= 2u, "GX may still be reading one buffer while the CPU fills the other");

/* ---- the conversion in progress (consumer state) ----------------------- */
static struct {
    struct gbp_vqueue_desc desc;
    uint32_t next_row;             /* tile rows converted so far, 0..40 */
    uint8_t  buf;                  /* which texture buffer is CPU_FILLING */
    uint8_t  active;
    uint32_t ticks;                /* accumulated slice cost for this frame */
    struct gbp_vpix_stats stats;
} conv;

static uint32_t flag15_last_count;
static uint32_t flag15_last_x, flag15_last_y;
static uint32_t slices_done, presents_submitted, no_free_buffer;
static uint32_t slice_ticks_min = 0xFFFFFFFFu, slice_ticks_max;
static const struct gbp_vstate *pump_state;

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

/* The GP has finished the submitted commands, so the texture it read is free.
 * This runs at interrupt time: it stores one byte and does nothing else. */
static void on_draw_done(void)
{
    uint32_t i;
    for (i = 0; i < STREAM_TEX_BUFFERS; i++)
        if (tex_state[i] == TEX_SUBMITTED) tex_state[i] = TEX_FREE;
}

static void video_setup(void)
{
    VIDEO_Init();
    rmode = VIDEO_GetPreferredMode(NULL);
    /* TWO framebuffers, which is how the text report and the GX output stop
     * competing for one (§V5.15 named this as the open question). The console
     * owns xfb_text and is shown while the probe reports; GX copies into
     * xfb_stream and that one is shown while the capture runs. */
    xfb_stream = MEM_K0_TO_K1(SYS_AllocateFramebuffer(rmode));
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
    GX_CopyDisp(xfb_stream, GX_TRUE);
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

    GX_SetDrawDoneCallback(on_draw_done);
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

static int find_free_buffer(void)
{
    uint32_t i;
    for (i = 0; i < STREAM_TEX_BUFFERS; i++) if (tex_state[i] == TEX_FREE) return (int)i;
    return -1;
}

/* THE CONSUMER SLICE. Called once per service cycle, after the RE-ARM, and it
 * does a bounded amount of work and returns. It never blocks, never waits for
 * the GP or the VI, and never touches the device. */
static void pump(void *user)
{
    uint32_t t0, t1, row, n;
    (void)user;

    if (!conv.active) {
        int buf;
        /* Nothing in flight: take the newest published frame, if the GP has
         * given a buffer back. With no free buffer the descriptor is LEFT in the
         * mailbox, so the producer's newest-wins rule keeps it fresh rather than
         * this code choosing which frame to lose. */
        buf = find_free_buffer();
        if (buf < 0) { no_free_buffer++; return; }
        if (!gbp_vqueue_take(&vq, &conv.desc)) return;
        conv.buf = (uint8_t)buf;
        tex_state[buf] = TEX_CPU_FILLING;
        conv.next_row = 0u;
        conv.ticks = 0u;
        conv.active = 1u;
        memset(&conv.stats, 0, sizeof conv.stats);
    }

    t0 = (uint32_t)gettick();
    for (n = 0; n < STREAM_SLICE_TILE_ROWS && conv.next_row < GBP_VPIX_BLOCKS; n++) {
        const uint8_t *blk;
        row = conv.next_row;
        blk = gbp_vstate_ring_block(pump_state, conv.desc.slot, row);
        if (!blk) { conv.next_row = GBP_VPIX_BLOCKS; break; }   /* no raw: abandon, guard below rejects */
        (void)gbp_vpix_block(blk, row, tex_buf[conv.buf],
                             GBP_VPIX_TEX_BYTES / 2u, &conv.stats);
        conv.next_row++;
    }
    t1 = (uint32_t)gettick();
    {
        uint32_t d = t1 - t0;
        conv.ticks += d;
        if (d < slice_ticks_min) slice_ticks_min = d;
        if (d > slice_ticks_max) slice_ticks_max = d;
        slices_done++;
    }

    if (conv.next_row < GBP_VPIX_BLOCKS) return;      /* more slices to come */

    /* The frame is converted. Step 3 and 4 of the generation guard (§V5.7):
     * only now do we ask whether the producer reused the slot underneath us. */
    if (!gbp_vqueue_commit(&vq, gbp_vqueue_still_valid(&vq, &conv.desc), conv.ticks)) {
        /* Consumer overrun. The half-and-half image is discarded whole and the
         * screen keeps the previous frame; two generations never mix. */
        tex_state[conv.buf] = TEX_FREE;
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

    GX_InvalidateTexAll();
    GX_InitTexObj(&tex_obj, tex_buf[conv.buf], GBP_VPIX_WIDTH, GBP_VPIX_HEIGHT,
                  GX_TF_RGB5A3, GX_CLAMP, GX_CLAMP, GX_FALSE);
    GX_InitTexObjFilterMode(&tex_obj, GX_NEAR, GX_NEAR);   /* no filtering: Phase 9 */
    GX_LoadTexObj(&tex_obj, GX_TEXMAP0);
    draw_quad();
    tex_state[conv.buf] = TEX_SUBMITTED;
    GX_SetDrawDone();                 /* NON-blocking: on_draw_done() frees the buffer */
    GX_CopyDisp(xfb_stream, GX_TRUE);
    GX_Flush();
    presents_submitted++;
    gbp_vqueue_note_presented(&vq);
    conv.active = 0u;
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
    gbp_vstate_init(&vstate, frame_store, STREAM_MAX_FRAMES, event_store, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, 0, 0, audio_raw, sizeof audio_raw);
    gbp_vstate_diag_store(&vstate, diag_store, GBP_VSTATE_MAX_DISAGREEMENTS);
    cfg.st = &vstate;

    gbp_vqueue_init(&vq, gbp_vstate_ring_slots(&vstate));
    pump_state = &vstate;
    vq.pump = pump;
    vq.pump_user = 0;
    cfg.stream = &vq;

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
    ringlog_printf(&rl, "ENVBUF frames=%08lx events=%08lx raw_ring=%08lx audio_raw=%08lx texA=%08lx texB=%08lx fifo=%08lx log_lines=%u",
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(frame_store), (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(event_store),
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(raw_ring), (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(audio_raw),
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(tex_buf[0]), (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(tex_buf[1]),
                   (unsigned long)MEM_VIRTUAL_TO_PHYSICAL(gx_fifo), (unsigned)LOG_LINES);

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

    /* Back to the console for the report: the two framebuffers never fight. */
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
    ringlog_printf(&rl, "STREAMCONS taken=%lu converted=%lu presented=%lu overrun=%lu dropped_before_convert=%lu no_free_buffer=%lu balanced=%d",
                   (unsigned long)vq.consumer_frames_taken, (unsigned long)vq.consumer_frames_converted,
                   (unsigned long)vq.consumer_frames_presented, (unsigned long)vq.consumer_slot_overrun,
                   (unsigned long)vq.dropped_before_convert, (unsigned long)no_free_buffer,
                   gbp_vqueue_balanced(&vq));
    ringlog_printf(&rl, "STREAMPACE publish_min=%lu publish_max=%lu publish_mean=%lu n=%lu convert_min=%lu convert_max=%lu convert_mean=%lu n=%lu",
                   (unsigned long)(vq.publish_interval_n ? vq.publish_interval_min : 0u),
                   (unsigned long)vq.publish_interval_max, (unsigned long)gbp_vqueue_publish_interval_mean(&vq),
                   (unsigned long)vq.publish_interval_n,
                   (unsigned long)(vq.convert_ticks_n ? vq.convert_ticks_min : 0u),
                   (unsigned long)vq.convert_ticks_max, (unsigned long)gbp_vqueue_convert_ticks_mean(&vq),
                   (unsigned long)vq.convert_ticks_n);
    ringlog_printf(&rl, "STREAMSLICE slices=%lu min=%lu max=%lu submitted=%lu tile_rows_per_slice=%u",
                   (unsigned long)slices_done, (unsigned long)(slices_done ? slice_ticks_min : 0u),
                   (unsigned long)slice_ticks_max, (unsigned long)presents_submitted,
                   (unsigned)STREAM_SLICE_TILE_ROWS);
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
    printf("  CONSUMER taken=%lu converted=%lu presented=%lu  overrun=%lu superseded=%lu no_free_buf=%lu  counters %s\n",
           (unsigned long)vq.consumer_frames_taken, (unsigned long)vq.consumer_frames_converted,
           (unsigned long)vq.consumer_frames_presented, (unsigned long)vq.consumer_slot_overrun,
           (unsigned long)vq.dropped_before_convert, (unsigned long)no_free_buffer,
           gbp_vqueue_balanced(&vq) ? "BALANCE" : "DO NOT BALANCE");
    printf("  PACING  publish %lu/%lu/%lu ticks (min/mean/max, n=%lu)   convert %lu/%lu/%lu (n=%lu)\n",
           (unsigned long)(vq.publish_interval_n ? vq.publish_interval_min : 0u),
           (unsigned long)gbp_vqueue_publish_interval_mean(&vq), (unsigned long)vq.publish_interval_max,
           (unsigned long)vq.publish_interval_n,
           (unsigned long)(vq.convert_ticks_n ? vq.convert_ticks_min : 0u),
           (unsigned long)gbp_vqueue_convert_ticks_mean(&vq), (unsigned long)vq.convert_ticks_max,
           (unsigned long)vq.convert_ticks_n);
    printf("  SLICE   %lu slices, %lu..%lu ticks each, %lu frames submitted to GX\n",
           (unsigned long)slices_done, (unsigned long)(slices_done ? slice_ticks_min : 0u),
           (unsigned long)slice_ticks_max, (unsigned long)presents_submitted);
    printf("  FLAG15  last frame carried %lu set word(s), first at (%lu,%lu) — REPORTED, NOT INTERPRETED (U-GBP-034)\n",
           (unsigned long)flag15_last_count, (unsigned long)flag15_last_x, (unsigned long)flag15_last_y);
    printf("  RESTORE control=%d stop=%d cleanup=%d arinfo=%d handler=%d mask_ok=%d\n",
           a->control_restore_ok, a->irq_stop_write_ok, a->pi_cleanup_performed, a->arinfo_restore_ok,
           res.h.handler_restored, res.h.mask_ok);
    printf("\n  THIS RUN PROVES NOTHING ON ITS OWN. Sustained streaming is judged offline against\n");
    printf("  HARDWARE_TESTS §V5.21, and the duration is still a DESIGN DECISION (§V5.5).\n");

    printf("\n  X = save log to SD    START = exit    POWER CYCLE REQUIRED\n");
    for (;;) {
        VIDEO_WaitVSync();
        PAD_ScanPads();
        if (!saved && (PAD_ButtonsDown(0) & PAD_BUTTON_X)) {
            char path[128] = "";
            char extra[200];
            int rc;
            /* No sidecar: this experiment's result is counters and aggregates,
             * which the bounded log carries in full. §V5.24's rule is that a new
             * frozen format is created only when the existing ones cannot hold
             * the data — here they are not even needed. */
            snprintf(extra, sizeof extra,
                     "libogc=%s gecko=%d power_cycle_required=%d sidecar=none capture_s=%lu safety_s=%lu",
                     _V_STRING, gecko_present, res.power_cycle_required,
                     (unsigned long)STREAM_CAPTURE_SECONDS, (unsigned long)STREAM_SAFETY_SECONDS);
            rc = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl,
                            status, sizeof status, path, sizeof path);
            saved = (rc == 0);
            printf("  SAVE %s\n", status);
        }
        if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break;
    }
    for (i = 0; i < 1; i++) gecko_puts("OPENGBP-STREAM DONE\n");
    return 0;
}
