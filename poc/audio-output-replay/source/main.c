/*
 * Open-GBP AOUT-HW-001, build aout-0002 — MAKE THE GAMECUBE PLAY IT (GitHub
 * Issue #86). IMPLEMENTED AND HOST-VALIDATED; NOT PHYSICALLY EXECUTED; the run
 * is staged by a separate Hardware Issue.
 *
 * AN OUTPUT-PATH TEST, NOT A GAME BOY PLAYER AUDIO TEST. It proves -- or fails
 * to prove -- ONE thing: that the console can be made to emit the samples the
 * project's decoder produces. It says nothing about live capture, continuous
 * drain or timing, and a PASS here is NOT Phase 6's acceptance. The Game Boy
 * Player is not touched: no transport, no HSP backend, no GBP register, no
 * interrupt of its own is linked (the `aout` audit profile proves it).
 *
 * WHAT IT DOES.
 *   1. Reads RUN 33's AUDIO-window sidecar from the SD card
 *      (AOUT_FIXTURE_PATH, the decompressed captures/fixtures file), and
 *      refuses anything that is not RUN 33: the size and the sidecar's own
 *      total CRC must be the recorded ones.
 *   2. Builds the listening sequence with src/audio/gbp_alisten -- the #81
 *      decoder and resampler, UNCHANGED -- as 32 000 Hz stereo, the same sample
 *      in both channels (tests/host/test_audio_listen.py: bit-identical to the
 *      #80 / #81 reference on the same fixture).
 *   2b. aout-0002 (HARDWARE_TESTS §V21.6): REORDERS the four tones into a
 *      SEALED play order, drawn by a random draw before this code existed and
 *      kept in aout_order.h. The reorder moves whole (tone + gap) segments and
 *      is exact (gbp_alisten_permute checks why). The order reaches the SD log
 *      only -- never the screen, never the Gecko.
 *   3. Plays it through the AI DMA at the console's native 32 kHz, in
 *      AOUT_CHUNK_BYTES blocks queued from the DMA callback, then
 *      AOUT_REST_CHUNKS of silence, and again, until START.
 *
 * THE SCREEN shows which tone of four is playing, a pass counter and a
 * heartbeat, so a silent console is distinguishable from a crashed one
 * (CLAUDE.md §14). It does NOT show the frequencies: the Operator's gate is
 * whether he hears four distinct pitches and in what order, and a number on
 * the screen would make his ears a formality. The frequencies are in the log.
 *
 * X saves the log to SD; START stops the audio and exits.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <gccore.h>
#include <ogc/libversion.h>
#include <fat.h>
#include <sdcard/gcsd.h>

#include "opengbp_ident.h"
#include "ringlog.h"
#include "sdlog.h"
#include "gbp_alisten.h"
#include "aout_order.h"

#ifndef OPENGBP_APP_NAME
#define OPENGBP_APP_NAME "audio-output-replay"
#endif
#ifndef OPENGBP_BUILD_ID
#define OPENGBP_BUILD_ID "unknown"
#endif
#ifndef OPENGBP_GIT_COMMIT
#define OPENGBP_GIT_COMMIT "unknown"
#endif
/* NOT the GBP-AUDIO family, on purpose: this is not a Game Boy Player audio test. */
#define TEST_ID "AOUT-HW-001"

static const char opengbp_ident_marker[] =
    "OPENGBP-IDENT " OPENGBP_APP_NAME " " OPENGBP_BUILD_ID " " OPENGBP_GIT_COMMIT;

#define GECKO_CHANNEL EXI_CHANNEL_1

/* ---- the fixture: RUN 33, as recorded ------------------------------------ */
#define AOUT_FIXTURE_PATH  "sd:/open-gbp/aout/run33-audio.bin"
#define AOUT_FIXTURE_BYTES 5243788u                 /* captures/README.md, RUN 33's raw sidecar */
#define AOUT_FIXTURE_CRC   0xD3DBD9A6u              /* its OGBPAWND total CRC */
#define AOUT_FIXTURE_CAP   (6u << 20)

/* ---- the output ---------------------------------------------------------- */
#define AOUT_RATE          32000u                   /* the AI's native rate; gbp_alisten's output */
#define AOUT_FRAME_BYTES   4u                       /* s16 left + s16 right, native big-endian */
#define AOUT_CHUNK_FRAMES  8000u                    /* 0.25 s */
#define AOUT_CHUNK_BYTES   (AOUT_CHUNK_FRAMES * AOUT_FRAME_BYTES)
#define AOUT_REST_CHUNKS   8u                       /* 2 s of silence between passes */
#define AOUT_MAX_CHUNKS    ((GBP_ALISTEN_MAX_FRAMES + AOUT_CHUNK_FRAMES - 1u) / AOUT_CHUNK_FRAMES)
_Static_assert(AOUT_CHUNK_BYTES % 32u == 0u, "an AI DMA block is a whole number of 32-byte units");
_Static_assert(AOUT_CHUNK_BYTES / 32u < 0x8000u, "the AI DMA length field is 15 bits of 32-byte units");
_Static_assert(GBP_ALISTEN_OUT_RATE == AOUT_RATE, "the sequence is built at the rate the AI plays");

static const char *const TONE_HZ[GBP_ALISTEN_MAX_TONES] = { "128", "512", "256", "1024" };   /* log only */

#define LOG_LINES 256
#define LOG_LINE_LEN 256
static char log_storage[LOG_LINES * LOG_LINE_LEN];

static uint8_t fixture[AOUT_FIXTURE_CAP] ATTRIBUTE_ALIGN(32);
static int16_t built[AOUT_MAX_CHUNKS * AOUT_CHUNK_FRAMES * 2u] ATTRIBUTE_ALIGN(32);  /* window order */
static int16_t pcm[AOUT_MAX_CHUNKS * AOUT_CHUNK_FRAMES * 2u] ATTRIBUTE_ALIGN(32);    /* the sealed play order */
static struct gbp_alisten_info built_info;
static uint8_t silence[AOUT_CHUNK_BYTES] ATTRIBUTE_ALIGN(32);
static struct gbp_alisten_info info;

/* ---- the DMA queue: one block programmed ahead, from the AI DMA callback -- */
static uint32_t seq_chunks;                          /* the sequence, padded to whole chunks */
static uint32_t cycle_chunks;                        /* the sequence plus the rest */
static volatile uint32_t dma_irqs;                   /* one per block the AI started */
static volatile uint32_t playing;                    /* the cycle position of the block playing now */
static volatile uint32_t programmed;                 /* the cycle position programmed next */
static volatile uint32_t passes;                     /* whole cycles completed: counted when block 0 starts again */

static uint32_t chunk_addr(uint32_t pos)
{
    return pos < seq_chunks ? (uint32_t)(size_t)((uint8_t *)pcm + (size_t)pos * AOUT_CHUNK_BYTES)
                            : (uint32_t)(size_t)silence;
}

/* Interrupt context. The block programmed last time has just started; queue the
 * next one. No print, no allocation, no file, nothing that can wait. */
static void dma_cb(void)
{
    dma_irqs++;
    playing = programmed;
    if (playing == 0u && dma_irqs > 1u) passes++;   /* block 0 again: one whole cycle has played */
    programmed = (programmed + 1u) % cycle_chunks;
    AUDIO_InitDMA(chunk_addr(programmed), AOUT_CHUNK_BYTES);
}

static void *xfb;
static GXRModeObj *rmode;
static int gecko_present;

static void gecko_puts(const char *line)
{
    if (gecko_present) usb_sendbuffer_safe(GECKO_CHANNEL, line, (int)strlen(line));
}

static void wait_start(void)
{
    for (;;) {
        VIDEO_WaitVSync();
        PAD_ScanPads();
        if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break;
    }
}

#ifdef AOUT_EMBEDDED
/* THE DOLPHIN FLOW VARIANT (EMBED=1): the same bytes, linked in, because Dolphin
 * has no SD2SP2. Its own build id, its own output directory, never staged. */
extern const uint8_t aout_embedded_fixture[], aout_embedded_fixture_end[];

static long load_fixture(char *why, size_t why_cap)
{
    const size_t n = (size_t)(aout_embedded_fixture_end - aout_embedded_fixture);
    if (n > sizeof fixture) {
        snprintf(why, why_cap, "the embedded fixture does not fit (%lu bytes)", (unsigned long)n);
        return -3;
    }
    memcpy(fixture, aout_embedded_fixture, n);
    snprintf(why, why_cap, "EMBEDDED copy, %lu bytes (DOLPHIN FLOW BUILD, never for the console)", (unsigned long)n);
    return (long)n;
}
#else
/* Reads the whole fixture. Returns the bytes read, or a negative code. */
static long load_fixture(char *why, size_t why_cap)
{
    FILE *f;
    size_t n;
    if (!fatMountSimple("sd", &__io_gcsd2)) {
        snprintf(why, why_cap, "SD mount failed (no SD2SP2 / no card / not FAT)");
        return -1;
    }
    f = fopen(AOUT_FIXTURE_PATH, "rb");
    if (!f) {
        snprintf(why, why_cap, "%s not found on the card", AOUT_FIXTURE_PATH);
        fatUnmount("sd");
        return -2;
    }
    n = fread(fixture, 1, sizeof fixture, f);
    fclose(f);
    fatUnmount("sd");
    snprintf(why, why_cap, "read %lu bytes from %s", (unsigned long)n, AOUT_FIXTURE_PATH);
    return (long)n;
}
#endif

int main(void)
{
    struct ringlog rl;
    static char line[320];
    char why[160] = "-";
    char status[160] = "not saved (press X)";
    char ident_text[OPENGBP_IDENT_MAX];
    const struct opengbp_ident ident = { OPENGBP_APP_NAME, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT };
    long got;
    int rc, saved = 0, shown_tone = -2;
    uint32_t k, shown_pass = 0xFFFFFFFFu, beat = 0;
    static const char spin[4] = { '|', '/', '-', '\\' };

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
    PAD_Init();
    gecko_present = usb_isgeckoalive(GECKO_CHANNEL);
    opengbp_ident_format(ident_text, sizeof ident_text, &ident);
    ringlog_init(&rl, log_storage, LOG_LINE_LEN, LOG_LINES);

    printf("\x1b[2J\x1b[1;0H");
    printf("  Open-GBP " TEST_ID "  %s  %s\n", OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT);
    printf("  OUTPUT PATH TEST -- NOT a Game Boy Player audio test. The GBP is not touched.\n");
    printf("  It plays RUN 33's four captured tones, decoded by the project's own code.\n");
#ifdef AOUT_EMBEDDED
    printf("  *** DOLPHIN FLOW BUILD: the fixture is linked in. NEVER for the console. ***\n");
#endif
    printf("\n");
    snprintf(line, sizeof line, "OPENGBP-AOUT READY %s test=%s\n", ident_text, TEST_ID);
    gecko_puts(line);
    ringlog_printf(&rl, "IDENT test=%s app=%s build=%s commit=%s libogc=%s", TEST_ID, OPENGBP_APP_NAME,
                   OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, _V_STRING);
    ringlog_printf(&rl, "AOUT scope=output_path_only gbp_touched=0 fixture=%s bytes=%u crc=%08x rate=%u "
                        "format=s16_stereo_same_sample_native_be chunk_bytes=%u rest_chunks=%u",
                   AOUT_FIXTURE_PATH, (unsigned)AOUT_FIXTURE_BYTES, (unsigned)AOUT_FIXTURE_CRC, (unsigned)AOUT_RATE,
                   (unsigned)AOUT_CHUNK_BYTES, (unsigned)AOUT_REST_CHUNKS);

    /* 1. the fixture, and only RUN 33's */
    printf("  Loading RUN 33's fixture ...\n");
    got = load_fixture(why, sizeof why);
    rc = 0;
    if (got >= 0 && (unsigned long)got == AOUT_FIXTURE_BYTES) {
        rc = gbp_alisten_build(fixture, (size_t)got, built, AOUT_MAX_CHUNKS * AOUT_CHUNK_FRAMES, &built_info);
        /* §V21.6: the sealed order, applied as whole segments; `info` is the PLAY table from here on */
        if (rc == 0)
            rc = gbp_alisten_permute(&built_info, built, AOUT_PLAY_ORDER, (uint32_t)sizeof AOUT_PLAY_ORDER, pcm,
                                     AOUT_MAX_CHUNKS * AOUT_CHUNK_FRAMES, &info);
        else
            info = built_info;
    }
    ringlog_printf(&rl, "FIXTURE rc=%ld want_bytes=%u %s", got, (unsigned)AOUT_FIXTURE_BYTES, why);
    snprintf(line, sizeof line, "OPENGBP-AOUT FIXTURE rc=%ld %s\n", got, why);
    gecko_puts(line);
    if (got < 0 || (unsigned long)got != AOUT_FIXTURE_BYTES || rc != 0 || info.total_crc32 != AOUT_FIXTURE_CRC ||
        info.tones != GBP_ALISTEN_MAX_TONES) {
        printf("\n  NOT PLAYING: %s\n", got < 0 ? why :
               (unsigned long)got != AOUT_FIXTURE_BYTES ? "the file is not RUN 33's size" :
               rc != 0 ? "the sidecar did not parse or decode" :
               info.total_crc32 != AOUT_FIXTURE_CRC ? "the sidecar is not RUN 33's (CRC)" : "not four tones");
        printf("  Expected %u bytes, CRC %08x. Nothing was played. START = exit\n",
               (unsigned)AOUT_FIXTURE_BYTES, (unsigned)AOUT_FIXTURE_CRC);
        ringlog_printf(&rl, "REFUSED got=%ld build_rc=%d crc=%08x tones=%u", got, rc, (unsigned)info.total_crc32,
                       (unsigned)info.tones);
        snprintf(line, sizeof line, "OPENGBP-AOUT REFUSED got=%ld build_rc=%d crc=%08x tones=%u\n", got, rc,
                 (unsigned)info.total_crc32, (unsigned)info.tones);
        gecko_puts(line);
        wait_start();
        gecko_puts("OPENGBP-AOUT DONE\n");
        return 0;
    }

    /* 2. the sequence: built, padded to whole chunks, flushed for the DMA */
    seq_chunks = (info.out_frames + AOUT_CHUNK_FRAMES - 1u) / AOUT_CHUNK_FRAMES;
    memset(pcm + 2u * info.out_frames, 0, (size_t)(seq_chunks * AOUT_CHUNK_FRAMES - info.out_frames) * AOUT_FRAME_BYTES);
    cycle_chunks = seq_chunks + AOUT_REST_CHUNKS;
    DCFlushRange(pcm, seq_chunks * AOUT_CHUNK_BYTES);
    DCFlushRange(silence, sizeof silence);
    ringlog_printf(&rl, "ALISTEN rc=%d crc=%08x windows=%u tones=%u in=%u frames=%u blocks=%u lost=%u overflow=%u "
                        "seq_chunks=%u cycle_chunks=%u",
                   rc, (unsigned)info.total_crc32, (unsigned)info.windows, (unsigned)info.tones,
                   (unsigned)info.in_samples, (unsigned)info.out_frames, (unsigned)info.dec_blocks,
                   (unsigned)info.dec_lost, (unsigned)info.dec_overflow, (unsigned)seq_chunks, (unsigned)cycle_chunks);
    /* the SD log only: read after the run, never shown while it plays */
    for (k = 0u; k < info.tones; k++)
        ringlog_printf(&rl, "PLAY position=%u window=w%u expected_hz=%s keys=%04x sliced=%u repeats=%u first=%u frames=%u gap_first=%u gap_frames=%u",
                       (unsigned)k + 1u, (unsigned)info.source[k] + 1u, TONE_HZ[info.source[k]], (unsigned)info.keys[k],
                       (unsigned)info.sliced[k], (unsigned)info.repeats[k], (unsigned)info.seg_first[2u * k],
                       (unsigned)info.seg_frames[2u * k], (unsigned)info.seg_first[2u * k + 1u],
                       (unsigned)info.seg_frames[2u * k + 1u]);
    snprintf(line, sizeof line, "OPENGBP-AOUT BUILT rc=%d crc=%08x tones=%u frames=%u chunks=%u\n", rc,
             (unsigned)info.total_crc32, (unsigned)info.tones, (unsigned)info.out_frames, (unsigned)seq_chunks);
    gecko_puts(line);

    /* 3. the output path: the AI at 32 kHz, one block queued ahead */
    AUDIO_Init(NULL);
    AUDIO_SetDSPSampleRate(AI_SAMPLERATE_32KHZ);
    AUDIO_RegisterDMACallback(dma_cb);
    programmed = 0u;
    AUDIO_InitDMA(chunk_addr(0u), AOUT_CHUNK_BYTES);
    AUDIO_StartDMA();
    gecko_puts("OPENGBP-AOUT PLAYING\n");

    printf("\n  PLAYING. Listen: how many distinct pitches, in what order (low/high)?\n");
    printf("  It repeats after a 2 s pause.   X = save log   START = stop, exit\n");
    for (;;) {
        const uint32_t pos = playing, pass = passes;
        int seg = (pos < seq_chunks) ? gbp_alisten_segment(&info, pos * AOUT_CHUNK_FRAMES) : -1;
        const int tone = (seg >= 0 && (seg & 1) == 0) ? seg / 2 : -1;
        VIDEO_WaitVSync();
        PAD_ScanPads();
        beat++;
        if (tone != shown_tone || pass != shown_pass || (beat & 15u) == 0u) {
            printf("\x1b[11;0H  PASS %lu   %s   %c   (AI blocks started: %lu)          ",
                   (unsigned long)pass + 1u,
                   tone >= 0 ? (tone == 0 ? "TONE 1 of 4" : tone == 1 ? "TONE 2 of 4" : tone == 2 ? "TONE 3 of 4"
                                                                                                    : "TONE 4 of 4")
                             : (pos < seq_chunks ? "  (gap)    " : "  (pause)  "),
                   spin[(beat >> 4) & 3u], (unsigned long)dma_irqs);
            if (pass != shown_pass && pass > 0u) {
                snprintf(line, sizeof line, "OPENGBP-AOUT PASS %lu dma_irqs=%lu\n", (unsigned long)pass,
                         (unsigned long)dma_irqs);
                gecko_puts(line);
            }
            shown_tone = tone;
            shown_pass = pass;
        }
        if (!saved && (PAD_ButtonsDown(0) & PAD_BUTTON_X)) {
            char path[128] = "", extra[200];
            int src;
            ringlog_printf(&rl, "AOUTRUN dma_irqs=%lu passes=%lu playing=%lu", (unsigned long)dma_irqs,
                           (unsigned long)passes, (unsigned long)playing);
            snprintf(extra, sizeof extra, "libogc=%s gecko=%d scope=output_path_only gbp_touched=0", _V_STRING,
                     gecko_present);
            src = sdlog_save(TEST_ID, OPENGBP_BUILD_ID, OPENGBP_GIT_COMMIT, extra, &rl, status, sizeof status,
                             path, sizeof path);
            saved = (src == 0);
            printf("\x1b[13;0H  SAVE log: %s\n", status);
            snprintf(line, sizeof line, "OPENGBP-AOUT SAVELOG rc=%d path=%s\n", src, path);
            gecko_puts(line);
        }
        if (PAD_ButtonsDown(0) & PAD_BUTTON_START) break;
    }
    AUDIO_StopDMA();
    AUDIO_RegisterDMACallback(NULL);
    snprintf(line, sizeof line, "OPENGBP-AOUT STOPPED dma_irqs=%lu passes=%lu\n", (unsigned long)dma_irqs,
             (unsigned long)passes);
    gecko_puts(line);
    printf("\x1b[15;0H  Stopped after %lu pass(es). %s\n", (unsigned long)passes, opengbp_ident_marker);
    gecko_puts("OPENGBP-AOUT DONE\n");
    return 0;
}
