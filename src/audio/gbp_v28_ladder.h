/*
 * gbp_v28_ladder -- the §V28 latency ladder (GitHub Issue #128, frozen by the Orchestrator's
 * Amendment A, GitHub Issue #129), expressed in NATIVE (gbp_aplay2, 65 536 Hz) units.
 *
 * #122 designed the ladder, the L(T, A) formula, the -16.5 DUP edge and the 129-sample gate for
 * the OLD 4 096 Hz path (gbp_aplay, 128-sample chunks). #128 §5 makes the native 65 536 Hz path
 * (gbp_aplay2) the audio path -- and on that path TARGET is counted in 65 536 Hz samples. Taken
 * literally, the old path's raw TARGET numbers would be 16x too small here: T256 read as 256
 * native samples is 3.91 ms, below GBP_APLAY2_TARGET_MIN's 2048 (31.25 ms), and would be
 * rejected or would underrun immediately -- the same class of error as the k = 8 unit slip
 * (Amendment A's own words).
 *
 * FROZEN (Amendment A): the ladder is stated in TIME. Native samples are DERIVED from the old
 * path's own TARGET by the rate ratio (x16) -- the literal old values are never used as native
 * ones. Every derived native TARGET is checked at build time against GBP_APLAY2_TARGET_MIN and
 * GBP_APLAY2_TARGET_MAX below: a unit slip then fails the build instead of reaching the console.
 *
 * AHEAD carries over UNCONVERTED: one chunk is 31.25 ms on both paths (128 samples at 4096 Hz,
 * 2048 samples at 65536 Hz), so an AHEAD count is already path-agnostic -- it is a chunk count,
 * not a sample count, and needs no x16.
 *
 * L(T, A)'s own small constants (the DUP edge, the +8 offset) are calibrated on RUN 43, which ran
 * the OLD path, and are PROVISIONAL on this path until the validation run re-measures them here
 * (Amendment A). This header carries only the ladder's TARGET/AHEAD rungs, not the formula, and
 * not the rungs' order within 3a/3b/the step sweep -- that is the session/plan design's own scope.
 */
#ifndef OPENGBP_GBP_V28_LADDER_H
#define OPENGBP_GBP_V28_LADDER_H

#include "gbp_aplay2.h"

#ifdef __cplusplus
extern "C" {
#endif

/* the rate ratio between the native path (gbp_adec2, GBP_ADEC2_RATE) and the old path (gbp_async's
 * own documented decode rate, GBP_ASYNC_RATE) -- 65536 / 4096 = 16, exact by construction. */
#define GBP_V28_NATIVE_RATIO   16u

_Static_assert(GBP_V28_NATIVE_RATIO == 65536u / 4096u,
    "gbp_v28_ladder: the native ratio no longer matches 65536/4096 -- recompute the whole ladder");
_Static_assert(65536u % 4096u == 0u,
    "gbp_v28_ladder: the native ratio must be exact, or every derived TARGET below is wrong");

/* the old path's own TARGET rungs (#122's ladder, #128 §3, 4096 Hz units) -- documentation only,
 * NEVER used directly as a native sample count. */
#define GBP_V28_OLD_T704   704u
#define GBP_V28_OLD_T576   576u
#define GBP_V28_OLD_T448   448u
#define GBP_V28_OLD_T320   320u
#define GBP_V28_OLD_T256   256u   /* the perceptual anchor (#128 §3's own resolution) */
#define GBP_V28_OLD_T192   192u   /* validation ladder only -- kept off the perceptual anchor */

/* native TARGET, samples -- derived by x16, never hand-copied from the old values above. */
#define GBP_V28_T704   (GBP_V28_OLD_T704 * GBP_V28_NATIVE_RATIO)   /* 11264, 171.88 ms */
#define GBP_V28_T576   (GBP_V28_OLD_T576 * GBP_V28_NATIVE_RATIO)   /*  9216, 140.62 ms */
#define GBP_V28_T448   (GBP_V28_OLD_T448 * GBP_V28_NATIVE_RATIO)   /*  7168, 109.38 ms */
#define GBP_V28_T320   (GBP_V28_OLD_T320 * GBP_V28_NATIVE_RATIO)   /*  5120,  78.12 ms */
#define GBP_V28_T256   (GBP_V28_OLD_T256 * GBP_V28_NATIVE_RATIO)   /*  4096,  62.50 ms */
#define GBP_V28_T192   (GBP_V28_OLD_T192 * GBP_V28_NATIVE_RATIO)   /*  3072,  46.88 ms */

/* Amendment A's own build-time check: every ladder TARGET, converted to native samples, must be
 * able to start a chunk (>= TARGET_MIN) and must fit the ring (<= TARGET_MAX). */
_Static_assert(GBP_V28_T704 >= GBP_APLAY2_TARGET_MIN && GBP_V28_T704 <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_T704 is out of GBP_APLAY2's TARGET bounds");
_Static_assert(GBP_V28_T576 >= GBP_APLAY2_TARGET_MIN && GBP_V28_T576 <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_T576 is out of GBP_APLAY2's TARGET bounds");
_Static_assert(GBP_V28_T448 >= GBP_APLAY2_TARGET_MIN && GBP_V28_T448 <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_T448 is out of GBP_APLAY2's TARGET bounds");
_Static_assert(GBP_V28_T320 >= GBP_APLAY2_TARGET_MIN && GBP_V28_T320 <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_T320 is out of GBP_APLAY2's TARGET bounds");
_Static_assert(GBP_V28_T256 >= GBP_APLAY2_TARGET_MIN && GBP_V28_T256 <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_T256 is out of GBP_APLAY2's TARGET bounds");
_Static_assert(GBP_V28_T192 >= GBP_APLAY2_TARGET_MIN && GBP_V28_T192 <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_T192 is out of GBP_APLAY2's TARGET bounds");

/* AHEAD, chunk counts -- unconverted (see the header comment above). */
#define GBP_V28_A4   4u
#define GBP_V28_A3   3u
#define GBP_V28_A2   2u
#define GBP_V28_A1   1u

/* The step mechanism's own fixed mute (#128 §3's resolution: mute 6, not 5, for the T256 anchor --
 * "no splice heard at any loss" at mute 6 against mute 5's D2-class risk, Item 4's own host test).
 * A chunk count, unconverted, like AHEAD above -- every nulling step, every refused step, 3b's own
 * AHEAD-lowering entry and the step sweep all use it. NOT 3a's own descent, which stays UNMUTED. */
#define GBP_V28_STEP_MUTE   6u

/* The largest START's OWN mute (Issue #129/#130, the Orchestrator's direction after the ROTATE
 * landing trim): the step sweep's two START transitions (T256A1 <-> T704A4, #129's frozen
 * sequence) climb the whole ladder in one plan -- the perceptual run's own STARTs never use
 * GBP_V28_STEP_MUTE either (#128 §7). GBP_ATRANS2_ROTATE needs `pause + ahead` (gbp_atrans2.h's
 * own gbp_atrans2_min_mute()); `pause` is the climb in chunks, the same ceiling-division formula
 * gbp_v28_3a.c's own UNMUTED descent uses for a climb (`(to - from + PUSHES - 1) / PUSHES`), at
 * the ladder's own largest span (T256 -> T704) and its own largest AHEAD (A4). A build-time
 * constant, like STEP_MUTE above -- not computed per call, and not the fixed mute an ordinary
 * rung or a refused step uses. */
#define GBP_V28_START_PAUSE   ((GBP_V28_T704 - GBP_V28_T256 + GBP_APLAY2_PUSHES - 1u) / GBP_APLAY2_PUSHES)
#define GBP_V28_START_MUTE    (GBP_V28_START_PAUSE + GBP_V28_A4)   /* 4 + 4 = 8 */

_Static_assert(GBP_V28_START_PAUSE == 4u,
    "gbp_v28_ladder: the T256->T704 climb's own pause changed -- recompute GBP_V28_START_MUTE");
_Static_assert(GBP_V28_START_MUTE == 8u, "gbp_v28_ladder: GBP_V28_START_MUTE no longer 8 -- check the derivation");
_Static_assert(GBP_V28_START_MUTE > GBP_V28_STEP_MUTE,
    "gbp_v28_ladder: the largest START needs MORE mute than an ordinary rung, or STEP_MUTE already covers it "
    "and this constant is not needed");

/* ---- the auto-search grids (#122/gbp_async_cfg_default's p3/p2 fields) -----------------------
 *
 * 3a's descent (TARGET 384 -> 128 by 32, bisected) and nulling's scan (384..3584 by 128) are ALSO
 * old-path (4096 Hz) sample counts -- the same unit slip Amendment A guards the ladder against
 * applies here too, so they are derived the same way: stated as the old value, x16, never a
 * hand-copied native literal. mute_chunks/step_mute_chunks/dwell/confirm/cap are chunk counts or
 * seconds already, so they carry over unconverted (see AHEAD, above) and are not repeated here --
 * the session/plan design (#129's own next slice) is what places these grids into a phase. */
#define GBP_V28_OLD_P3_START   384u
#define GBP_V28_OLD_P3_STEP     32u
#define GBP_V28_OLD_P3_MIN     128u
#define GBP_V28_OLD_P2_LO      384u
#define GBP_V28_OLD_P2_HI     3584u
#define GBP_V28_OLD_P2_STEP    128u

#define GBP_V28_P3_START   (GBP_V28_OLD_P3_START * GBP_V28_NATIVE_RATIO)   /* 6144 */
#define GBP_V28_P3_STEP    (GBP_V28_OLD_P3_STEP  * GBP_V28_NATIVE_RATIO)   /*  512 */
#define GBP_V28_P3_MIN     (GBP_V28_OLD_P3_MIN   * GBP_V28_NATIVE_RATIO)   /* 2048 == GBP_APLAY2_TARGET_MIN */
#define GBP_V28_P2_LO      (GBP_V28_OLD_P2_LO    * GBP_V28_NATIVE_RATIO)   /*  6144 */
#define GBP_V28_P2_HI      (GBP_V28_OLD_P2_HI    * GBP_V28_NATIVE_RATIO)   /* 57344 */
#define GBP_V28_P2_STEP    (GBP_V28_OLD_P2_STEP  * GBP_V28_NATIVE_RATIO)   /*  2048 */

/* the grid's own endpoints must be reachable TARGETs, same as every ladder rung above.
 *
 * KNOWN GAP, stated rather than hidden: unlike the ladder's own T-values (all well under
 * TARGET_MIN when read literally), GBP_V28_OLD_P2_HI (3584) already numerically falls inside
 * [TARGET_MIN, TARGET_MAX] on its own -- so this bounds check alone would NOT catch a slip that
 * left P2_HI un-derived while P2_LO/P2_STEP stayed correct. The divisibility check right below
 * this one is what catches that specific case (3584 does not land on the grid P2_LO/P2_STEP
 * derive), and tests/host/test_v28_ladder.py proves it does. */
_Static_assert(GBP_V28_P3_START >= GBP_APLAY2_TARGET_MIN && GBP_V28_P3_START <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_P3_START is out of GBP_APLAY2's TARGET bounds");
_Static_assert(GBP_V28_P3_MIN >= GBP_APLAY2_TARGET_MIN && GBP_V28_P3_MIN <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_P3_MIN is out of GBP_APLAY2's TARGET bounds");
_Static_assert(GBP_V28_P2_LO >= GBP_APLAY2_TARGET_MIN && GBP_V28_P2_LO <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_P2_LO is out of GBP_APLAY2's TARGET bounds");
_Static_assert(GBP_V28_P2_HI >= GBP_APLAY2_TARGET_MIN && GBP_V28_P2_HI <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_P2_HI is out of GBP_APLAY2's TARGET bounds");

/* the descent/scan must land exactly on its own floor/ceiling -- a non-exact step would silently
 * drift the search grid away from the values above. */
_Static_assert((GBP_V28_P3_START - GBP_V28_P3_MIN) % GBP_V28_P3_STEP == 0u,
    "GBP_V28_P3_START..P3_MIN is not an exact number of P3_STEPs");
_Static_assert((GBP_V28_P2_HI - GBP_V28_P2_LO) % GBP_V28_P2_STEP == 0u,
    "GBP_V28_P2_LO..P2_HI is not an exact number of P2_STEPs");

/* ---- 3a's bisection width -- the SECOND unit gap found by reading, not the first (the
 * Orchestrator, #129/#130): p3_bisect_width (2, old-path units) is compared directly against
 * hi - lo, which are TARGET-domain values (same unit as the ladder/grid above), so it needs the
 * same x16 derivation -- 32 native samples, keeping the frozen design's 0.49 ms bisection
 * resolution (2 old-path samples = 0.49 ms at 4096 Hz; 32 native samples = 0.49 ms at 65536 Hz,
 * the SAME width, not sixteen times coarser or finer). It is not one of gbp_async_cfg's own
 * p2_lo/p2_hi/p2_step/p3_start/p3_step/p3_min fields the earlier grid pass ported, which is
 * exactly why it was missed once already -- see the enumeration below, which is what closes the
 * class instead of the next instance. */
#define GBP_V28_OLD_P3_BISECT_WIDTH   2u
#define GBP_V28_P3_BISECT_WIDTH   (GBP_V28_OLD_P3_BISECT_WIDTH * GBP_V28_NATIVE_RATIO)   /* 32, 0.49 ms */

/* ---- THE ENUMERATION (the Orchestrator, #129/#130): every TARGET-domain constant
 * gbp_async.h/gbp_async.c and gbp_atrans.h/gbp_atrans.c compare against or assign to a sample
 * count, closed as a CLASS rather than caught one instance at a time (the ladder was the first
 * gap found this way, p3_bisect_width above the second). Checked directly against both files'
 * current text, not from memory.
 *
 *   TARGET-domain, derived x16 above:
 *     p2_lo, p2_hi, p2_step         (nulling's scan grid)              GBP_V28_P2_LO/HI/STEP
 *     p3_start, p3_step, p3_min     (3a's descent grid)                GBP_V28_P3_START/STEP/MIN
 *     p3_bisect_width               (3a's bisection convergence width) GBP_V28_P3_BISECT_WIDTH
 *
 *   TARGET-domain, but NOT NEEDED for #128's design (Phase 1 is dropped from BOTH runs, #128 §2
 *   point 3 / #122's own accepted decision) -- deliberately left unconverted, not missed:
 *     deep = 2048, shallow = 512, floor = 384   (Phase 1's own blinded A/B levels)
 *
 *   Chunk-relative, already re-derived by FORMULA rather than a literal (no gap):
 *     GBP_ATRANS_AIM = 64 (half a chunk)  ->  GBP_ATRANS2_AIM = GBP_APLAY2_PUSHES / 2 (gbp_atrans2.h)
 *     GBP_APLAY_BAND = 16 (gbp_aplay.h)   ->  GBP_APLAY2_BAND = 256 (gbp_aplay2.h, its own comment:
 *                                             "16 x gbp_aplay's BAND, the same 3.906 ms width")
 *
 *   NOT TARGET-domain at all (chunk counts, seconds, or the hardware timebase -- correctly
 *   unconverted, carrying over exactly as AHEAD does above):
 *     mute_chunks = 18, step_mute_chunks = 4   (chunk counts; ALSO superseded by #128 §3's own
 *                                                fixed mute = 6 for the new step mechanism -- not
 *                                                used by #128's design at all, converted or not)
 *     p3_dwell_s = 6, p3_confirm_s = 60, settling_s = 2                  (seconds)
 *     cap_p1_s = 300, cap_p2_s = 240, cap_p3_s = 180, cap_session_s = 720 (seconds; p1's is moot,
 *                                                                          Phase 1 dropped)
 *     real = 12, null = 6                       (Phase 1's own switch-schedule counts, moot)
 *     tb_hz = 40 500 000                        (the GameCube's own hardware timebase, not audio)
 *     GBP_ASYNC_SWITCH_CAP = 18, GBP_ASYNC_P2_CAP = 16, GBP_ASYNC_DEPTH_CAP = 64,
 *     GBP_ASYNC_SECONDS = 728                   (array-size/record caps, not sample thresholds)
 *
 * A later constant belongs in the FIRST list, converted here with the same x16 discipline and a
 * bounds/divisibility assert where one applies, or the SECOND, with the same reason named -- not
 * a fresh instance of this comment. */

#ifdef __cplusplus
}
#endif
#endif
