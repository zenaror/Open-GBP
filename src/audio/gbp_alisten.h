/*
 * gbp_alisten — a captured AUDIO window turned into the LISTENING sequence the
 * console plays (GitHub Issue #86; an OUTPUT-PATH test, not a Game Boy Player
 * audio test).
 *
 * WHAT IT BUILDS. The construction of tools/v17decode.write_run's LISTEN copy --
 * the one #80 produced and the Operator's ears were asked to judge -- at the
 * runtime's own rate, through the runtime's own modules, UNCHANGED:
 *
 *   1. the sidecar is parsed by the replay backend (gbp_asrc, which uses the
 *      strict gbp_awindump_parse, CRCs included);
 *   2. the decoder (gbp_adec) is calibrated on the CONTROL window, as #80 and
 *      #81 did;
 *   3. each PRESS window's SLICED region -- blocks ONSET..end, ONSET = 96,
 *      v11sweep's ONSET_SLICE_BLOCKS (§V11.9), fixed before any data -- is
 *      decoded to one 4096 Hz sample per AUDIO block;
 *   4. that region is repeated round(4096 / length) times, about one second, as
 *      v17decode does: 160 samples is a whole number of periods at 128, 512, 256
 *      and 1024 Hz, so the loop joins without a click;
 *   5. GBP_ALISTEN_GAP_IN zero samples follow each tone -- the ONE thing the
 *      #80 LISTEN file did not have. It is there so four tones are counted as
 *      four, and it is silence, not data;
 *   6. everything goes through ONE frozen 125/16 resampler (gbp_aresamp),
 *      4096 -> 32 000 Hz, the console's native AI rate.
 *
 * THE OUTPUT is interleaved stereo, the same sample in both channels, as
 * NATIVE-endian int16 -- big-endian on the console, which is what the AI DMA
 * reads. Frames, not bytes, are counted everywhere.
 *
 * Pure: no device, no allocation, no floating point, no file access. The POC
 * reads the file and drives the AI; this decides every sample, and a host test
 * checks it against the #80/#81 reference on the versioned RUN 33 fixture.
 */
#ifndef OPENGBP_GBP_ALISTEN_H
#define OPENGBP_GBP_ALISTEN_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_ALISTEN_ONSET       96u      /* v11sweep.ONSET_SLICE_BLOCKS, §V11.9 */
#define GBP_ALISTEN_IN_RATE     4096u    /* one sample per AUDIO block */
#define GBP_ALISTEN_OUT_RATE    32000u   /* 4096 * 125 / 16 */
#define GBP_ALISTEN_GAP_IN      2048u    /* 0.5 s of silence after each tone, at 4096 Hz */
#define GBP_ALISTEN_MAX_TONES   4u
#define GBP_ALISTEN_MAX_SLICED  256u     /* a press window's sliced region, at most */
/* A bound on the output, for the caller's buffer: every tone at most ~1 s plus its gap. */
#define GBP_ALISTEN_MAX_FRAMES  (GBP_ALISTEN_MAX_TONES * ((GBP_ALISTEN_IN_RATE + GBP_ALISTEN_MAX_SLICED + GBP_ALISTEN_GAP_IN) * 125u / 16u + 8u))

/* What was built, for the log and the screen. Segment 2k is tone k, 2k+1 its gap. */
struct gbp_alisten_info {
    int      rc;                          /* 0, or the failure below */
    uint32_t total_crc32;                 /* the sidecar's own, as its parser read it */
    uint32_t windows, controls, tones;
    uint32_t keys[GBP_ALISTEN_MAX_TONES];           /* each tone's anchor keys */
    uint32_t sliced[GBP_ALISTEN_MAX_TONES];         /* decoded samples per tone, before repetition */
    uint32_t repeats[GBP_ALISTEN_MAX_TONES];
    uint32_t seg_first[2u * GBP_ALISTEN_MAX_TONES]; /* output frame where each segment begins */
    uint32_t seg_frames[2u * GBP_ALISTEN_MAX_TONES];
    uint32_t segs;
    uint32_t in_samples, out_frames;
    uint32_t dec_blocks, dec_lost, dec_overflow;
};

#define GBP_ALISTEN_ERR_PARSE    -1   /* the sidecar is not a valid OGBPAW1 file */
#define GBP_ALISTEN_ERR_CONTROL  -2   /* no CONTROL window to calibrate on */
#define GBP_ALISTEN_ERR_TONES    -3   /* no PRESS window, or one with nothing past the onset */
#define GBP_ALISTEN_ERR_CAPACITY -4   /* the caller's buffer is too small */
#define GBP_ALISTEN_ERR_ARG      -5

/* Build the sequence into `out` (2 * cap_frames int16). Returns 0 or a negative
 * GBP_ALISTEN_ERR_*; `info` says what was built either way. */
int gbp_alisten_build(const uint8_t *sidecar, size_t n, int16_t *out, uint32_t cap_frames,
                      struct gbp_alisten_info *info);

/* Which segment an output frame falls in: 2k for tone k, 2k+1 for its gap, -1 past the end. */
int gbp_alisten_segment(const struct gbp_alisten_info *info, uint32_t frame);

#ifdef __cplusplus
}
#endif
#endif
