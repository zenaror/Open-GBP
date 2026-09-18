/*
 * test_gbp_vstate.c — the GBP-VIDEO-002 state model: the stateful frame
 * assembler, the frame-signature store, the learned baseline, the episode
 * state machine, the bounded event store, the raw preservation policy, the
 * cap behaviours (which are three different things) and the streamed sidecar.
 *
 * EVERY SCENARIO IS SYNTHETIC and none of it is physical evidence. No
 * reference table, checksum, pixel or block range of the Start-up Disc or of
 * GBI appears anywhere in this file — the whole point of the design is that
 * the runtime has no oracle, and neither do its tests.
 */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#include "gbp_vstate.h"
#include "gbp_vsig.h"
#include "gbp_time64.h"

static unsigned checks, failures;

static void ok(int cond, const char *what)
{
    checks++;
    if (!cond) { failures++; printf("  FAIL %s\n", what); }
}

static void eq_u32(uint32_t got, uint32_t want, const char *what)
{
    checks++;
    if (got != want) { failures++; printf("  FAIL %s: got %lu want %lu\n", what, (unsigned long)got, (unsigned long)want); }
}

static void eq_u64(uint64_t got, uint64_t want, const char *what)
{
    checks++;
    if (got != want) { failures++; printf("  FAIL %s: got %llu want %llu\n", what,
                                          (unsigned long long)got, (unsigned long long)want); }
}

/* ---- storage, static as on the console -------------------------------- */
static struct gbp_vstate_frame frames[GBP_VSTATE_MAX_FRAMES];
static struct gbp_vstate_event events[GBP_VSTATE_MAX_EVENTS];
static uint8_t raw_ring[GBP_VSTATE_RAW_RING_BYTES];
static uint8_t episode_raw[GBP_VSTATE_EPISODE_RAW_BYTES];
static uint8_t audio_raw[GBP_VSTATE_AUDIO_RAW_BYTES];
static struct gbp_vstate st;

/* one frame period at the cadence GBP-VIDEO-001 measured: 680 138 ticks / 40 blocks */
#define BLOCK_TICKS 17003u
#define FRAME_TICKS (BLOCK_TICKS * 40u)

static uint64_t clock_t64;

static void reset_state(void)
{
    gbp_vstate_init(&st, frames, GBP_VSTATE_MAX_FRAMES, events, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
    clock_t64 = 1000u;
}

/* Feeds one VIDEO block. `screen` selects the payload (so two screens give two signature vectors),
 * `boundary` sets the Disc frame-start bit, `gbi_too` also sets GBI's, `real_sig` computes the real
 * checksum over the bytes (slow, used where the content matters) instead of a cheap stand-in. */
static void feed(int screen, int boundary, int gbi_too, int real_sig, struct gbp_vstate_step *step)
{
    uint8_t *tgt = gbp_vstate_video_target(&st);
    uint8_t first4[4];
    uint32_t sig;
    struct gbp_vstate_step local;
    if (!step) step = &local;
    ok(tgt != 0, "a DMA target is always available");
    if (!tgt) return;
    if (real_sig) {
        uint32_t k;
        for (k = 0; k < GBP_VSTATE_VIDEO_BLOCK_SIZE; k += 4u) {
            tgt[k] = 0x7F; tgt[k + 1] = 0x7F;
            tgt[k + 2] = (uint8_t)(0xFFu - (unsigned)screen);
            tgt[k + 3] = (uint8_t)(0xFFu - (unsigned)screen);
        }
    } else {
        tgt[0] = 0x7F; tgt[1] = 0x7F; tgt[2] = 0xFF; tgt[3] = 0xFF;
    }
    if (boundary) { tgt[1] = 0xFF; if (gbi_too) tgt[0] = 0xFF; }
    first4[0] = tgt[0]; first4[1] = tgt[1]; first4[2] = tgt[2]; first4[3] = tgt[3];
    sig = real_sig ? gbp_vsig_block(tgt, GBP_VSTATE_VIDEO_BLOCK_SIZE) : (uint32_t)(0x1000u + (unsigned)screen);
    clock_t64 += BLOCK_TICKS;
    gbp_vstate_block(&st, tgt, GBP_VSTATE_VIDEO_BLOCK_SIZE, first4, clock_t64, sig, 40u, step);
}

/*
 * One interval of `screen`: a boundary block followed by `blocks - 1` ordinary ones, both
 * predicates agreeing on the boundary.
 *
 * CLOSED FRAMES LAG BY ONE, deliberately, because that is how the hardware works: an interval is
 * only complete when the NEXT boundary arrives. So N calls to emit_frame() close N-1 frames and
 * leave the Nth open, and every scenario below is written that way rather than by synthesising a
 * closing boundary that the device never sent.
 */
static void emit_frame(int screen, unsigned blocks)
{
    unsigned i;
    feed(screen, 1, 1, 0, 0);
    for (i = 1; i < blocks; i++) feed(screen, 0, 0, 0, 0);
}

/* The last closed episode descriptor, or NULL when there is none (so a failed expectation
 * reports a failure instead of reading past the array). */
static const struct gbp_vstate_episode *last_ep(void)
{
    if (st.episodes_n == 0u) return 0;
    return &st.episodes[st.episodes_n - 1u];
}

static uint32_t ep_field(const struct gbp_vstate_episode *e, uint32_t v)
{
    return e ? v : 0xFFFFFFFFu;
}

/* ---- the frame assembler --------------------------------------------- */
static void test_assembler(void)
{
    printf("-- frame assembler: 40 is never assumed, only ever observed\n");
    reset_state();
    /* blocks before the first boundary belong to no frame and are counted, never turned into one */
    feed(0, 0, 0, 0, 0);
    feed(0, 0, 0, 0, 0);
    eq_u32(st.frames_n, 0u, "no frame is created without an anchor");
    eq_u32(st.blocks_before_first_boundary, 0u, "the orphan blocks are not counted until the anchor arrives");
    emit_frame(0, 40);
    eq_u32(st.blocks_before_first_boundary, 2u, "the two orphan blocks are counted once the anchor arrives");
    eq_u32(st.frames_n, 0u, "the first interval is still open: only the NEXT boundary closes it");
    emit_frame(0, 40);
    eq_u32(st.frames_n, 1u, "the next boundary closes it");
    eq_u32(frames[0].blocks, 40u, "40 blocks were really observed between two boundaries");
    eq_u32(frames[0].completeness, GBP_VSTATE_FRAME_COMPLETE_40, "complete_40");
    ok((frames[0].flags & GBP_VSTATE_F_COMPLETE) != 0u, "the COMPLETE flag is set because it was observed");
    eq_u32(st.frames_complete, 1u, "counted as complete");
    eq_u32(st.interval_hist[40], 1u, "the interval histogram recorded 40");

    printf("-- incomplete_short: a boundary before the 40th block\n");
    reset_state();
    emit_frame(0, 40);
    emit_frame(0, 25);                      /* a 25-block interval */
    emit_frame(0, 40);
    eq_u32(st.frames_n, 2u, "the short interval is recorded as a frame, not discarded");
    eq_u32(frames[1].blocks, 25u, "with the block count it really had");
    eq_u32(frames[1].completeness, GBP_VSTATE_FRAME_INCOMPLETE_SHORT, "incomplete_short");
    eq_u32(st.interval_hist[25], 1u, "and its interval is in the histogram, never a failure");
    ok(st.anomalies_region >= 1u, "a boundary at an unexpected position is a region anomaly (class b)");

    printf("-- an interval other than 40 is a measurement: histogram only, no synthesised boundary\n");
    reset_state();
    emit_frame(0, 40);
    emit_frame(0, 41);
    emit_frame(0, 40);
    eq_u32(st.interval_hist[41], 1u, "41 is recorded as 41");
    eq_u32(frames[1].blocks, 41u, "the frame kept its real block count");
    ok((frames[1].flags & GBP_VSTATE_F_OVERLONG) != 0u, "over 40 blocks is flagged over-long");
    eq_u32(st.boundaries_disc, 3u, "exactly the three boundaries the device sent");

    printf("-- incomplete_long: 48 blocks and not one boundary\n");
    reset_state();
    emit_frame(0, 40);
    emit_frame(0, GBP_VSTATE_FRAME_MAX_BLOCKS);      /* 48 blocks, the last one forces the close */
    eq_u32(st.frames_n, 2u, "the over-long interval is closed at 48 without inventing a boundary");
    eq_u32(frames[1].blocks, GBP_VSTATE_FRAME_MAX_BLOCKS, "48 blocks recorded");
    eq_u32(frames[1].completeness, GBP_VSTATE_FRAME_INCOMPLETE_LONG, "incomplete_long");
    ok((frames[1].flags & GBP_VSTATE_F_OVERLONG) != 0u, "flagged over-long");
    ok((frames[1].flags & GBP_VSTATE_F_ANOMALY) != 0u, "and frame-invalidating (class a)");
    eq_u32(st.interval_hist[GBP_VSTATE_FRAME_MAX_BLOCKS + 1u], 1u,
           "the histogram marks 'no boundary within 48' in its own slot");
    ok(st.resync_pending == 1, "and the assembler reports it lost synchronisation");

    printf("-- predicate disagreement: recorded, never corrected, segmentation unaffected\n");
    reset_state();
    feed(0, 1, 1, 0, 0);                     /* frame start, both predicates */
    feed(0, 0, 0, 0, 0);
    feed(0, 1, 0, 0, 0);                     /* Disc = 1, GBI = 0: the only informative disagreement */
    eq_u32(st.disagreements_total, 1u, "the disagreement is counted");
    ok(st.disagreement_seen == 1, "and its first occurrence is kept");
    eq_u32(st.disagreement_first4[1], 0xFFu, "with byte 1 exactly as the device presented it");
    eq_u32(st.disagreement_first4[0], 0x7Fu, "and byte 0 too, uncorrected");
    eq_u32(st.boundaries_disc, 2u, "the Disc predicate segmented on it");
    eq_u32(st.boundaries_gbi, 1u, "the GBI predicate did not, and no boundary was fabricated for it");
    eq_u32(st.frames_n, 1u, "segmentation continued on the Disc predicate");
    eq_u32(frames[0].blocks, 2u, "closing the two-block interval it really delimited");

    printf("-- a 40-block frame carrying a disagreement is flagged but NOT marked incomplete\n");
    reset_state();
    emit_frame(0, 40);
    feed(0, 1, 0, 0, 0);                     /* the opening boundary of frame 1 is a disagreement */
    { unsigned i; for (i = 1; i < 40u; i++) feed(0, 0, 0, 0, 0); }
    emit_frame(0, 40);                       /* a clean boundary closes it at exactly 40 */
    eq_u32(st.frames_n, 2u, "two frames closed");
    eq_u32(frames[1].blocks, 40u, "the second at exactly 40 blocks");
    eq_u32(frames[1].completeness, GBP_VSTATE_FRAME_COMPLETE_40, "and it is NOT marked incomplete");
    ok((frames[1].flags & GBP_VSTATE_F_DISAGREEMENT) != 0u, "but it IS flagged disagreement");
    ok((frames[1].flags & GBP_VSTATE_F_ANOMALY) != 0u, "which makes it frame-invalidating (class a)");
    eq_u32(frames[1].disagreements, 1u, "and the count is stored per frame");
}

/* ---- baseline and early candidates ----------------------------------- */
static void emit_frames(int screen, unsigned n)
{
    unsigned i;
    for (i = 0; i < n; i++) emit_frame(screen, 40);
}

static void test_baseline(void)
{
    printf("-- baseline: three consecutive identical complete frames, and nothing less\n");
    reset_state();
    emit_frames(0, 3);                        /* two closed frames */
    eq_u32(st.frames_n, 2u, "two frames closed");
    eq_u32(st.baseline_frames_seen, 2u, "two identical frames are not a baseline");
    ok(st.baseline_valid == 0, "baseline still not valid after two");
    emit_frame(0, 40);
    ok(st.baseline_valid == 1, "the third identical complete frame establishes it");
    eq_u32(st.baseline_frames_seen, 3u, "exactly three");
    eq_u32(GBP_VSTATE_BASELINE_FRAMES, 3u, "the constant is 3");
    eq_u32(st.original_baseline_sig[0], 0x1000u, "the baseline vector is the one that repeated");
    eq_u32(st.current_reference_sig[0], 0x1000u, "and the current reference starts equal to it");

    printf("-- a 39- or 41-block interval does not establish a baseline\n");
    reset_state();
    emit_frame(0, 40);
    emit_frame(0, 39);
    emit_frame(0, 41);
    emit_frame(0, 40);
    ok(st.baseline_valid == 0, "no baseline from intervals that were not 40");

    printf("-- early candidate: a differing frame before baseline_valid is preserved, not discarded\n");
    reset_state();
    emit_frames(0, 2);                        /* one closed screen-0 frame */
    emit_frame(7, 40);                        /* closes the second screen-0 frame: two identical so far */
    eq_u32(st.baseline_frames_seen, 2u, "two so far, one short of a baseline");
    ok(st.baseline_valid == 0, "the baseline is deliberately not yet valid");
    emit_frame(7, 40);                        /* closes a screen-7 frame: the difference */
    eq_u32(st.early_candidates, 1u, "it is recorded as an early candidate");
    ok((frames[2].flags & GBP_VSTATE_F_EARLY_CANDIDATE) != 0u, "the frame carries the flag");
    ok((frames[2].flags & GBP_VSTATE_F_PRE_BASELINE) != 0u, "and the pre-baseline flag");
    eq_u32(st.episodes_n, 1u, "one descriptor holds it");
    ok((st.episodes[0].flags & GBP_VSTATE_EPF_EARLY) != 0u, "flagged EARLY, not a post-baseline episode");
    ok(st.episodes[0].raw_frames >= 1u, "with its raw preserved");
    eq_u32(st.baseline_frames_seen, 1u, "and the baseline candidate restarted from it");
    eq_u64(st.valid_observation_elapsed, 0u, "pre-baseline time never counts toward the negative result");
    eq_u32(st.episode_count, 0u, "an early candidate is NOT an episode");
}

/* ---- the scientific clock -------------------------------------------- */
static void make_baseline(void)
{
    reset_state();
    emit_frames(0, 4);                        /* three closed identical frames: baseline valid */
    ok(st.baseline_valid == 1, "baseline established");
}

static void test_valid_observation(void)
{
    uint64_t before;
    printf("-- the scientific clock advances only on clean complete frames, only after baseline_valid\n");
    make_baseline();
    before = st.valid_observation_elapsed;
    eq_u64(before, 0u, "nothing counted while the baseline was being learned");
    emit_frame(0, 40);
    ok(st.valid_observation_elapsed > before, "the first clean complete frame after it adds its duration");
    eq_u64(st.valid_observation_elapsed - before, (uint64_t)BLOCK_TICKS * 39u,
           "the frame's own span is added (block 0 to block 39: conservative by one block)");

    printf("-- a frame-invalidating anomaly does not add its duration, and pauses the clock\n");
    emit_frame(0, 30);                        /* this call closes the PREVIOUS complete frame, which counts */
    before = st.valid_observation_elapsed;    /* so the reference is taken after it */
    emit_frame(0, 40);                        /* and THIS call closes the 30-block interval */
    eq_u64(st.valid_observation_elapsed, before, "the short frame added nothing");
    ok(st.resync_pending == 1, "and it paused the clock (class b)");
    eq_u32(st.anomalies_region, 1u, "one region anomaly");

    printf("-- the pause holds until a clean complete frame returns, which itself is not counted\n");
    before = st.valid_observation_elapsed;
    emit_frame(0, 40);                        /* closes the resync-exit frame */
    eq_u64(st.valid_observation_elapsed, before, "the frame that re-establishes sync is not counted");
    ok(st.resync_pending == 0, "but it ends the pause");
    ok(st.resync_frames >= 2u, "and the skipped frames are counted as resync frames");
    before = st.valid_observation_elapsed;
    emit_frame(0, 40);
    ok(st.valid_observation_elapsed > before, "the frame after it counts again");
    eq_u32(st.frames_counted, 3u, "exactly three frames were ever counted: the short one and the resync exit were not");
}

/* ---- episodes --------------------------------------------------------- */
static void test_episodes(void)
{
    const struct gbp_vstate_episode *ep;
    printf("-- episode state machine: ARMED -> CHANGED -> STABILISING -> CLOSED\n");
    make_baseline();
    emit_frame(0, 40);
    eq_u32(st.episode_count, 0u, "a matching frame opens nothing");
    emit_frame(5, 40);                        /* closes a screen-0 frame */
    eq_u32(st.episode_count, 0u, "still nothing");
    emit_frame(5, 40);                        /* closes the first screen-5 frame: the change */
    eq_u32(st.episode_count, 1u, "a differing signature opens an episode");
    ok(st.episode_open == 1, "the episode is open");
    ep = last_ep();
    eq_u32(ep_field(ep, ep ? ep->state : 0u), GBP_VSTATE_EP_CHANGED, "state CHANGED");
    eq_u32(ep_field(ep, ep ? ep->stable_count : 0u), 1u, "stable_count 1");
    ok(ep && ep->raw_frames >= 2u, "the last reference frame and the first changed frame are preserved");
    emit_frame(5, 40);
    ep = last_ep();
    eq_u32(ep_field(ep, ep ? ep->stable_count : 0u), 2u, "a repeat advances stability");
    ok(st.episode_open == 1, "still open at 2 of N_STABLE = 3");
    emit_frame(5, 40);
    ok(st.episode_open == 0, "the third repeat closes it");
    eq_u32(st.stable_episodes, 1u, "as a stable episode");
    ok((st.episodes[0].flags & GBP_VSTATE_EPF_STABLE_FOUND) != 0u, "flagged stable_found");
    eq_u32(st.episodes[0].raw_frames, 3u, "with the stable state's raw frame added");
    eq_u32(GBP_VSTATE_N_STABLE, 3u, "N_STABLE is 3, the same threshold the baseline uses");

    printf("-- original_baseline_signature is never overwritten; current_reference advances\n");
    eq_u32(st.original_baseline_sig[0], 0x1000u, "the original baseline vector is untouched");
    eq_u32(st.current_reference_sig[0], 0x1005u, "the current reference advanced to the settled state");
    eq_u32(st.reference_updates, 1u, "one reference update");

    printf("-- no early positive stop: monitoring continues and a second episode is detectable\n");
    emit_frame(5, 40);
    eq_u32(st.episode_count, 1u, "a frame equal to the NEW reference opens nothing");
    emit_frame(9, 40);
    emit_frame(9, 40);
    eq_u32(st.episode_count, 2u, "a change relative to the CURRENT reference opens episode 2");
    emit_frame(9, 40);
    emit_frame(9, 40);
    eq_u32(st.stable_episodes, 2u, "and it closes stable too");
    eq_u32(st.original_baseline_sig[0], 0x1000u, "the original baseline is STILL the original");
    eq_u32(st.current_reference_sig[0], 0x1009u, "the current reference advanced again");

    printf("-- the first stable change is not necessarily the one we came for: both are kept\n");
    ok(st.episodes_n >= 2u, "both episodes have descriptors");
    ok(st.episodes_n >= 2u && st.episodes[0].final_sig[0] == 0x1005u && st.episodes[1].final_sig[0] == 0x1009u,
       "each episode's settled signature is its own; the withdrawn early stop would have lost the second");

    printf("-- an episode that never stabilises closes at EPISODE_MAX_FRAMES, unstable\n");
    make_baseline();
    {
        unsigned i;
        int screen = 1;
        emit_frame(screen, 40);
        emit_frame(screen, 40);               /* opens the episode */
        ok(st.episode_open == 1, "an episode is open");
        for (i = 0; i < GBP_VSTATE_EPISODE_MAX_FRAMES + 8u && st.episode_open; i++) {
            screen++;
            emit_frame(screen, 40);           /* never repeats */
        }
        ok(st.episode_open == 0, "the episode closed");
        eq_u32(st.unstable_episodes, 1u, "as unstable");
        ep = last_ep();
        ok(ep && (ep->flags & GBP_VSTATE_EPF_CAPPED) != 0u, "flagged capped");
        eq_u32(ep_field(ep, ep ? ep->frames : 0u), GBP_VSTATE_EPISODE_MAX_FRAMES, "at exactly 60 frames");
        eq_u32(GBP_VSTATE_EPISODE_MAX_FRAMES, 60u, "EPISODE_MAX_FRAMES is 60");
        eq_u32(st.reference_updates, 0u, "no new baseline is invented without a stable state");
        eq_u32(st.current_reference_sig[0], st.original_baseline_sig[0],
               "the reference is unchanged after an unstable episode");
        ok(st.episode_count == 1u, "it was one episode, and monitoring is armed again");
    }
}

static void test_episode_raw_store_full(void)
{
    unsigned i;
    printf("-- MAX_EPISODES: the raw store filling does NOT stop the monitor\n");
    make_baseline();
    for (i = 0; i < GBP_VSTATE_MAX_EPISODES + 3u; i++) {
        int screen = 20 + (int)i;
        emit_frame(screen, 40);               /* closes the previous state's last frame */
        emit_frame(screen, 40);               /* the change */
        emit_frame(screen, 40);
        emit_frame(screen, 40);               /* stabilises: closes */
        ok(st.episode_open == 0, "each episode closed stable");
    }
    eq_u32(st.episode_count, GBP_VSTATE_MAX_EPISODES + 3u, "every episode was detected");
    eq_u32(st.episodes_n, GBP_VSTATE_MAX_EPISODES, "only four have descriptors");
    eq_u32(GBP_VSTATE_MAX_EPISODES, 4u, "MAX_EPISODES is 4");
    ok(st.episode_store_full == 1, "episode_store_full is set");
    eq_u32(st.episodes_not_preserved, 3u, "and the rest are counted as not preserved");
    eq_u32(st.stable_episodes, GBP_VSTATE_MAX_EPISODES + 3u, "ALL of them are classified, preserved or not");
    ok(st.frame_store_full == 0, "the frame store is untouched by this");
    ok(st.event_store_full == 0, "and so is the event store");
    eq_u32(st.current_reference_sig[0], (uint32_t)(0x1000u + 20u + GBP_VSTATE_MAX_EPISODES + 2u),
           "the reference kept advancing through the unpreserved episodes");
    ok(st.episodes[0].index == 1u && st.episodes[3].index == 4u, "descriptors 1..4 are intact");
    ok(st.episodes[0].final_sig[0] == 0x1014u, "episode 1 still holds its own settled signature");
    ok(st.episodes[0].raw_frames > 0u, "and its raw frames were never overwritten");
}

/* ---- caps that DO end the run ---------------------------------------- */
static void test_frame_store_cap(void)
{
    unsigned i;
    printf("-- frame store cap: no overwrite, no wrap, the run is told to stop\n");
    reset_state();
    for (i = 0; i < GBP_VSTATE_MAX_FRAMES + 8u; i++) {
        emit_frame(0, 40);
        if (st.frame_store_full) break;
    }
    ok(st.frame_store_full == 1, "the store reports full");
    eq_u32(st.frames_n, GBP_VSTATE_MAX_FRAMES, "exactly MAX_FRAMES frames are stored");
    eq_u32(GBP_VSTATE_MAX_FRAMES, 16384u, "MAX_FRAMES is 16384");
    eq_u32(frames[0].index, 0u, "frame 0 is still frame 0 - nothing wrapped over it");
    eq_u32(frames[GBP_VSTATE_MAX_FRAMES - 1u].index, GBP_VSTATE_MAX_FRAMES - 1u, "and the last is the last");
    eq_u64((uint64_t)GBP_VSTATE_MAX_FRAMES * GBP_VSTATE_FRAME_REC, 3145728u, "16384 x 192 B = 3.00 MiB exactly");
}

static void test_event_store_cap(void)
{
    unsigned i;
    uint32_t seq_first, seq_last;
    printf("-- event store: monotonic sequence numbers, a hard cap, nothing overwritten\n");
    reset_state();
    seq_first = gbp_vstate_event(&st, 100u, GBP_VSTATE_EV_CAPTURE_START, 1u, 2u, 3u, 4u);
    eq_u32(seq_first, 1u, "the first sequence number is 1");
    for (i = 1; i < GBP_VSTATE_MAX_EVENTS; i++) gbp_vstate_event(&st, 100u, GBP_VSTATE_EV_ANOMALY, i, 0u, 0u, 0u);
    eq_u32(st.events_n, GBP_VSTATE_MAX_EVENTS, "the store is exactly full");
    ok(st.event_store_full == 1, "and says so");
    seq_last = gbp_vstate_event(&st, 100u, GBP_VSTATE_EV_ANOMALY, 0u, 0u, 0u, 0u);
    eq_u32(seq_last, 0u, "a further event is refused");
    eq_u32(st.events_dropped, 1u, "and counted, never silently lost");
    eq_u32(st.events_n, GBP_VSTATE_MAX_EVENTS, "nothing was overwritten");
    eq_u32(events[0].seq, 1u, "event 0 still carries sequence 1");
    eq_u32(events[0].a, 1u, "with its own payload");

    printf("-- two events sharing one tick are still ordered by their sequence numbers\n");
    reset_state();
    gbp_vstate_event(&st, 4242u, GBP_VSTATE_EV_EPISODE_OPEN, 0u, 0u, 0u, 0u);
    gbp_vstate_event(&st, 4242u, GBP_VSTATE_EV_EPISODE_STABILISING, 0u, 0u, 0u, 0u);
    eq_u64(events[0].t, events[1].t, "the timestamps are identical");
    ok(events[1].seq == events[0].seq + 1u, "but the sequence numbers are not: the order is unambiguous");
    eq_u64((uint64_t)GBP_VSTATE_MAX_EVENTS * GBP_VSTATE_EVENT_REC, 262144u, "4096 x 64 B = 0.25 MiB exactly");

    printf("-- a long run produces no event per delivery\n");
    reset_state();
    emit_frames(0, 200);                      /* 199 frames = 8000 blocks */
    ok(st.events_n < 40u, "8000 blocks produced a handful of events, not thousands");
    ok(st.event_store_full == 0, "and the store is nowhere near full");
    eq_u64(st.blocks_total, 200u * 40u, "every block was still processed");
}

/* ---- the tail, the safety cap and their precedence -------------------- */
static void test_tail_and_safety(void)
{
    const struct gbp_vstate_episode *ep;
    printf("-- the scientific target with no episode open: the caller may stop at once\n");
    make_baseline();
    ok(gbp_vstate_target_reached(&st, clock_t64) == 0, "no tail is needed");
    ok(st.tail_active == 0, "and none was opened");

    printf("-- the scientific target with an episode OPEN: a bounded finalisation tail\n");
    make_baseline();
    emit_frame(3, 40);
    emit_frame(3, 40);                        /* opens an episode */
    ok(st.episode_open == 1, "an episode is open");
    ok(gbp_vstate_target_reached(&st, clock_t64) == 1, "a tail is opened instead of cutting mid-episode");
    ok(st.tail_active == 1, "the tail is active");
    ep = last_ep();
    ok(ep && (ep->flags & GBP_VSTATE_EPF_TAIL) != 0u, "the episode is marked as finishing in the tail");
    {
        uint32_t before = st.episode_count;
        emit_frame(3, 40);
        emit_frame(3, 40);                    /* stabilises and closes */
        ok(st.episode_open == 0, "the open episode closed normally inside the tail");
        emit_frame(44, 40);
        emit_frame(44, 40);                   /* a change during the tail */
        eq_u32(st.episode_count, before, "no new episode was opened during the tail");
        ok(st.tail_frames > 0u, "tail_frames is reported");
        ok(st.tail_ticks > 0u, "and so is tail_ticks");
    }

    printf("-- a store cap during the tail truncates it and is NOT a fatal service error\n");
    make_baseline();
    emit_frame(3, 40);
    emit_frame(3, 40);
    gbp_vstate_target_reached(&st, clock_t64);
    ok(st.tail_active == 1, "tail open");
    gbp_vstate_tail_truncate(&st, clock_t64);
    ok(st.tail_active == 0, "the tail ended");
    ok(st.tail_truncated_by_cap == 1, "tail_truncated_by_cap is set");
    ok(st.episode_open == 1, "the episode is still open and will be reported exactly as it is");

    printf("-- the hard safety cap WINS over an open episode and over the tail\n");
    make_baseline();
    emit_frame(3, 40);
    emit_frame(3, 40);
    gbp_vstate_target_reached(&st, clock_t64);
    ok(st.tail_active == 1 && st.episode_open == 1, "an episode is open inside a tail");
    gbp_vstate_safety_stop(&st, clock_t64 + 1000u);
    ok(st.episode_open == 0, "the safety cap closed the episode immediately");
    ok(st.tail_active == 0, "and ended the tail: a cap extensible by 60 frames would not be hard");
    ep = last_ep();
    ok(ep && (ep->flags & GBP_VSTATE_EPF_TRUNCATED_BY_SAFETY) != 0u, "the episode is marked truncated_by_safety");
    eq_u32(st.unstable_episodes, 1u, "and classified as unstable, never as stable");
}

/* ---- AUDIO ------------------------------------------------------------ */
static void test_audio(void)
{
    unsigned slot = 99;
    uint8_t *b;
    printf("-- AUDIO: aggregate counters, first and last preserved, a failure never destroys a capture\n");
    reset_state();
    b = gbp_vstate_audio_target(&st, &slot);
    ok(b == audio_raw, "the first drain targets slot 0");
    eq_u32(slot, 0u, "slot 0");
    memset(b, 0xA1, GBP_VSTATE_AUDIO_BLOCK_SIZE);
    gbp_vstate_audio_commit(&st, slot, 1, GBP_VSTATE_AUDIO_BLOCK_SIZE, 7u);
    ok(st.audio.first_valid == 1, "slot 0 is now the preserved first drain");
    eq_u32(gbp_vstate_audio_raw_count(&st), 1u, "one raw block worth keeping");

    b = gbp_vstate_audio_target(&st, &slot);
    eq_u32(slot, 1u, "the next drain goes to the ping-pong pair, never back over the first");
    memset(b, 0xB2, GBP_VSTATE_AUDIO_BLOCK_SIZE);
    gbp_vstate_audio_commit(&st, slot, 1, GBP_VSTATE_AUDIO_BLOCK_SIZE, 8u);
    eq_u32((uint32_t)st.audio.last_valid, 1u, "slot 1 holds the last valid capture");

    b = gbp_vstate_audio_target(&st, &slot);
    eq_u32(slot, 2u, "the next attempt uses the OTHER ping-pong buffer");
    memset(b, 0xCC, GBP_VSTATE_AUDIO_BLOCK_SIZE);
    gbp_vstate_audio_commit(&st, slot, 0, 0u, 9u);                 /* it FAILS */
    eq_u32((uint32_t)st.audio.last_valid, 1u, "the failure did not become the last valid capture");
    eq_u32(gbp_vstate_audio_bytes(&st, 1u)[0], 0xB2u, "and the last valid bytes are intact");
    eq_u32(gbp_vstate_audio_bytes(&st, 0u)[0], 0xA1u, "as are the first drain's");
    eq_u32(st.audio.failures, 1u, "the failure is counted");
    eq_u32(st.audio.completed, 2u, "completions are counted");
    eq_u64(st.audio.bytes, 2u * GBP_VSTATE_AUDIO_BLOCK_SIZE, "bytes are accumulated in 64 bits");
    eq_u32(gbp_vstate_audio_raw_count(&st), 2u, "exactly two raw blocks are worth storing");

    b = gbp_vstate_audio_target(&st, &slot);
    eq_u32(slot, 2u, "after a failure the next attempt still avoids the last valid slot");
    gbp_vstate_audio_commit(&st, slot, 1, GBP_VSTATE_AUDIO_BLOCK_SIZE, 10u);
    eq_u32((uint32_t)st.audio.last_valid, 2u, "a completion promotes the new slot");
}

/* ---- capacity arithmetic --------------------------------------------- */
static void test_memory_arithmetic(void)
{
    printf("-- exact memory arithmetic of every resident store\n");
    eq_u32(sizeof(struct gbp_vstate_frame), GBP_VSTATE_FRAME_REC, "one frame record is exactly 192 bytes");
    eq_u32(sizeof(struct gbp_vstate_event), GBP_VSTATE_EVENT_REC, "one event record is exactly 64 bytes");
    eq_u64((uint64_t)GBP_VSTATE_RAW_FRAME_BYTES, 184320u, "a raw frame slot is 48 x 0xF00 = 184 320 B");
    eq_u64((uint64_t)GBP_VSTATE_RAW_RING_BYTES, 552960u, "the working ring is 3 slots = 552 960 B = 0.53 MiB");
    /* GBP-VIDEO-002 runs at THREE slots and the refactor that made the count
     * configurable must never have moved it: this state was initialised from the
     * same 552 960-byte buffer every physical run used. */
    eq_u64(gbp_vstate_ring_slots(&st), 3u, "this experiment's ring is three slots, as it always was");
    ok(gbp_vstate_storage_ok(&st) == 1, "and the storage contract accepts it");
    eq_u64((uint64_t)GBP_VSTATE_EPISODE_RAW_BYTES, 2949120u, "the episode store is 4 x 4 x 184 320 = 2 949 120 B = 2.81 MiB");
    eq_u64((uint64_t)GBP_VSTATE_AUDIO_RAW_BYTES, 12288u, "AUDIO raw is 3 x 0x1000 = 12 KiB");
    eq_u64(gbp_vstate_static_bytes(), 3145728u + 262144u + 552960u + 2949120u + 12288u,
           "the resident total is the sum of the five stores");
    eq_u64(gbp_vstate_static_bytes(), 6922240u, "which is 6.60 MiB");
    ok(gbp_vstate_static_bytes() < 24u * 1024u * 1024u, "well inside MEM1");
    ok(gbp_vstate_storage_ok(&st) == 1, "the storage check accepts the real buffers");
    {
        struct gbp_vstate small;
        gbp_vstate_init(&small, frames, 8u, events, GBP_VSTATE_MAX_EVENTS, raw_ring, sizeof raw_ring,
                        episode_raw, sizeof episode_raw, audio_raw, sizeof audio_raw);
        ok(gbp_vstate_storage_ok(&small) == 0, "and refuses an undersized frame store");
    }
}

/* DIAGNOSTIC, added after the first physical smoke of `stream-0002` aborted with
 * `store_or_bounds_invalid` (HARDWARE_TESTS §V5.29).
 *
 * The POC had supplied episode_raw = NULL, because §V5.22 proposed dropping the
 * episode store for a streaming run. `gbp_vstate_storage_ok()` refused, and it
 * was RIGHT to: the model dereferences `episode_raw` in two places that check
 * nothing —
 *
 *     gbp_vstate_probe.c:812   memset(st->episode_raw, 0, 2 949 120)
 *     gbp_vstate.c:739         preserve_frame() writes one 184 320 B frame
 *
 * — so a NULL store is not a smaller model, it is a write to address 0. This
 * test exists to stop the tempting wrong fix: relaxing the validator instead of
 * giving the model the buffer it dereferences. If the episode store is ever
 * made genuinely optional, BOTH sites must be guarded first, and only then may
 * this expectation change. */
static void test_a_null_episode_store_must_stay_refused(void)
{
    struct gbp_vstate cut;
    printf("-- a NULL episode store is refused, because two sites dereference it unguarded\n");
    gbp_vstate_init(&cut, frames, GBP_VSTATE_MAX_FRAMES, events, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, 0, 0, audio_raw, sizeof audio_raw);
    ok(cut.episode_raw == 0, "the store really is absent");
    eq_u32(cut.episode_raw_cap, 0u, "and its capacity is zero");
    ok(gbp_vstate_storage_ok(&cut) == 0, "storage_ok() refuses it");

    /* the exact configuration stream-0002 shipped: reduced frame table too */
    gbp_vstate_init(&cut, frames, 4096u, events, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, 0, 0, audio_raw, sizeof audio_raw);
    ok(gbp_vstate_storage_ok(&cut) == 0, "and refuses the stream-0002 configuration verbatim");

    /* the same reduced frame table WITH the episode store is still refused, so
     * the frame-table capacity is a second, independent reason */
    gbp_vstate_init(&cut, frames, 4096u, events, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw,
                    audio_raw, sizeof audio_raw);
    ok(gbp_vstate_storage_ok(&cut) == 0, "a 4096-entry frame table is refused on its own");

    /* and the full model is accepted, so the refusals above are not vacuous */
    gbp_vstate_init(&cut, frames, GBP_VSTATE_MAX_FRAMES, events, GBP_VSTATE_MAX_EVENTS,
                    raw_ring, sizeof raw_ring, episode_raw, sizeof episode_raw,
                    audio_raw, sizeof audio_raw);
    ok(gbp_vstate_storage_ok(&cut) == 1, "while the complete store set is accepted");
}

int main(void)
{
    printf("== test_gbp_vstate (GBP-VIDEO-002 state model; every scenario SYNTHETIC)\n");
    test_assembler();
    test_baseline();
    test_valid_observation();
    test_episodes();
    test_episode_raw_store_full();
    test_frame_store_cap();
    test_event_store_cap();
    test_tail_and_safety();
    test_audio();
    test_memory_arithmetic();
    test_a_null_episode_store_must_stay_refused();
    printf("%u checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
