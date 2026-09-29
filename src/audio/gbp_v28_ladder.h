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

/* THE TWO MUTES. Both AMENDED by GitHub Issue #136 (2026-09-28, the Orchestrator's decisions on RUN 52's
 * short landings and on the audible splice the old landing trim made): STEP 6 -> 7 (#128 section 3's figure was
 * 6, "no splice heard at any loss"), START 8 -> 10 (#128 section 7). Same class of amendment as 3a's
 * 138 -> 168 s, carried here with its derivation so a mute is never a bare constant again. A chunk count,
 * unconverted, like AHEAD above; every nulling step, every refused step, 3b's own AHEAD-lowering entry and the
 * step sweep use STEP_MUTE, the sweep's two START transitions, its repositioning move and the perceptual run's
 * STARTs use START_MUTE. NOT 3a's own descent, which stays UNMUTED.
 *
 * WHY A MUTE HAS A FLOOR (gbp_atrans2.h, "THE ROTATE LEVEL IS SET IN SILENCE"): every discontinuity of a step
 * (the one discard that sets the ring's level) happens inside the mute, and `ahead` chunks are built from the cut
 * ring, so that everything HEARD is built after it. Those builds consume ahead x PUSHES from the ring, and the
 * only source of samples is the feed, one PUSHES per hand-off period, so
 *     mute >= ahead + ceil((climb + the ring's deficit at the start) / PUSHES)
 * periods, `climb` being how far the target rises. The deficit is MEASURED, not assumed: RUN 52's V28_SWEEPM
 * records (meas_ring - from_target, 17 moves) put the ring at the start of a move 956 to 1878 samples BELOW
 * target (the corrector is saturated on the DUP side, the feed is ~0.5 % slow), and 2666 below for the prelude,
 * the state 3b's hold leaves. An earlier version of this comment derived 12 for START from a host that began
 * every move ABOVE target; the adversarial review found it.
 *
 *   STEP : the worst is a +PUSHES climb at AHEAD 4:  4 + ceil((2048 + 1878) / 2048) = 6
 *   START: T256 -> T704 at AHEAD 4:                  4 + ceil((7168 + 2666) / 2048) = 9
 *
 * Both were also measured on the console-calibrated host (tests/unit/test_v28_sweep_landing.c: 124.8 pump
 * calls per period and a feed 0.5 % slow, both from the RUN 52 log; the smallest mute at which the landing is in
 * band for all 25 begin phases, four feeds, the measured begin rings): 6 and 9, unchanged by a 1 % feed deficit.
 * One period of margin is kept on top of each, the margin an ordinary constant of this project keeps.
 *
 * COST, for the Operator, who hears it: STEP_MUTE 6 -> 7 adds +31.25 ms of silence to EVERY step (every nulling step
 * included: 187.5 -> 218.75 ms); START_MUTE 8 -> 10 adds +62.5 ms to START moves ONLY (250 -> 312.5 ms). Both stay single
 * uniform constants, so no gap depends on TARGET, AHEAD or direction (#122 section 1(c)). The 1 % feed deficit sizes
 * neither: the measured needs (6 and 9) are the same at exact, 0.5 % and 1 % slow feeds; 1 % is where the corrector
 * collapses in steady state, not an operating point.
 *
 * The build-time check #128 required: the mutes are BUILT from the ladder's own numbers, so a change that raises
 * a climb (T704, the step, AHEAD 4) fails the build here instead of landing short on the console. */
#define GBP_V28_BEGIN_DEFICIT_STEP    1878u   /* the ring below target at the start of a step, RUN 52's worst of 17 */
#define GBP_V28_BEGIN_DEFICIT_START   2666u   /* ... and at the prelude, the state 3b leaves */
#define GBP_V28_MUTE_MARGIN           1u
#define GBP_V28_STEP_NEED    (GBP_V28_A4 + (GBP_APLAY2_PUSHES + GBP_V28_BEGIN_DEFICIT_STEP + GBP_APLAY2_PUSHES - 1u) / GBP_APLAY2_PUSHES)
#define GBP_V28_STEP_MUTE    (GBP_V28_STEP_NEED + GBP_V28_MUTE_MARGIN)
#define GBP_V28_START_PAUSE  ((GBP_V28_T704 - GBP_V28_T256 + GBP_APLAY2_PUSHES - 1u) / GBP_APLAY2_PUSHES)
#define GBP_V28_START_NEED   (GBP_V28_A4 + (GBP_V28_T704 - GBP_V28_T256 + GBP_V28_BEGIN_DEFICIT_START + GBP_APLAY2_PUSHES - 1u) / GBP_APLAY2_PUSHES)
#define GBP_V28_START_MUTE   (GBP_V28_START_NEED + GBP_V28_MUTE_MARGIN)

_Static_assert(GBP_V28_A4 == 4u, "gbp_v28_ladder: the deepest AHEAD changed -- re-measure both mutes (Issue #136)");
_Static_assert(GBP_V28_STEP_NEED == 6u, "gbp_v28_ladder: a step's mute need changed from the measured 6 -- re-measure");
_Static_assert(GBP_V28_START_NEED == 9u, "gbp_v28_ladder: the largest climb's mute need changed from the measured 9 -- re-measure");
_Static_assert(GBP_V28_STEP_MUTE == 7u && GBP_V28_START_MUTE == 10u,
    "gbp_v28_ladder: the mutes no longer 7 and 10 -- check the derivation and tell the Orchestrator (the Operator hears it)");
/* the step's own need assumes no ordinary rung climbs more than one chunk: a wider rung needs a longer mute */
_Static_assert(GBP_V28_T704 - GBP_V28_T576 <= GBP_APLAY2_PUSHES && GBP_V28_T576 - GBP_V28_T448 <= GBP_APLAY2_PUSHES &&
               GBP_V28_T448 - GBP_V28_T320 <= GBP_APLAY2_PUSHES && GBP_V28_T320 - GBP_V28_T256 <= GBP_APLAY2_PUSHES,
    "gbp_v28_ladder: an ordinary rung climbs more than one chunk -- GBP_V28_STEP_NEED must grow (Issue #136)");
_Static_assert(GBP_V28_START_PAUSE == 4u,
    "gbp_v28_ladder: the T256->T704 climb's own pause changed -- recompute GBP_V28_START_MUTE");
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

#define GBP_V28_P3_START   (GBP_V28_OLD_P3_START * GBP_V28_NATIVE_RATIO)   /* 6144 */
#define GBP_V28_P3_STEP    (GBP_V28_OLD_P3_STEP  * GBP_V28_NATIVE_RATIO)   /*  512 */
#define GBP_V28_P3_MIN     (GBP_V28_OLD_P3_MIN   * GBP_V28_NATIVE_RATIO)   /* 2048 == GBP_APLAY2_TARGET_MIN */
/* Issue #141: there is NO P2 grid any more. The first nulling handler was a port of gbp_async's Phase 2 (TARGET only, 6144..57344 in 2048 steps, at whatever AHEAD was in force);
 * it did not belong to the frozen design, which nulls on the eight-rung ladder below (GBP_V28_RUNG). Its floor was a rung above the validated one and its far starts landed short;
 * the constants that described it (GBP_V28_P2_LO/HI/STEP, and the un-derived-P2_HI test they needed) are removed so nobody takes them for part of the design. */

/* 3a's descent grid endpoints must be reachable TARGETs, same as every ladder rung above. */
_Static_assert(GBP_V28_P3_START >= GBP_APLAY2_TARGET_MIN && GBP_V28_P3_START <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_P3_START is out of GBP_APLAY2's TARGET bounds");
_Static_assert(GBP_V28_P3_MIN >= GBP_APLAY2_TARGET_MIN && GBP_V28_P3_MIN <= GBP_APLAY2_TARGET_MAX,
    "GBP_V28_P3_MIN is out of GBP_APLAY2's TARGET bounds");

/* the descent/scan must land exactly on its own floor/ceiling -- a non-exact step would silently
 * drift the search grid away from the values above. */
_Static_assert((GBP_V28_P3_START - GBP_V28_P3_MIN) % GBP_V28_P3_STEP == 0u,
    "GBP_V28_P3_START..P3_MIN is not an exact number of P3_STEPs");

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
 *     p2_lo, p2_hi, p2_step         (the OLD nulling grid)             NOT DERIVED: removed in Issue #141 -- the perceptual nulling walks GBP_V28_RUNG, not a grid
 *     p3_start, p3_step, p3_min     (3a's descent grid)                GBP_V28_P3_START/STEP/MIN
 *     p3_bisect_width               (3a's bisection convergence width) GBP_V28_P3_BISECT_WIDTH
 *
 *   TARGET-domain, but NOT NEEDED for #128's design (Phase 1 is dropped from BOTH runs, #128 §2
 *   point 3 / #122's own accepted decision) -- deliberately left unconverted, not missed:
 *     deep = 2048, shallow = 512, floor = 384   (Phase 1's own blinded A/B levels)
 *
 *   Chunk-relative, already re-derived by FORMULA rather than a literal (no gap):
 *     GBP_ATRANS_AIM = 64 (half a chunk)  ->  the aim of the old ROTATE loop (removed, Issue #136)
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

/* ---- THE ANCHOR (Issue #128/#129/#130, the Orchestrator's Amendment 1 on Issue #131's own
 * freeze): 3b holds AHEAD at THIS TARGET, never 3a's own raw confirmed floor directly. #128 §3's
 * own rule: "the lowest ladder TARGET (192 + 128k) at or above 3a's lowest holding depth", with
 * the frozen 320->256 override that already drops T192 from the perceptual ladder (#128 §3's own
 * words: "T192... stay on the validation ladder only... do not carry into the perceptual run's own
 * ladder"). So the anchor search is over the PERCEPTUAL ladder alone -- T256, T320, T448, T576,
 * T704 -- never T192, and never a literal `192 + 128k` grid point that the override already
 * excludes.
 *
 * The defect this closes: gbp_v28_3b_start() was called with 3a's own raw `last_hold`/`lo` --
 * 3a bisects as low as GBP_V28_P3_MIN (2048 native, below even T192), so 3b could hold AHEAD 1 at
 * a depth that sits on NO ladder rung at all, and the 32-tap reversal condition (`GBP-HW-351`)
 * would then be read at a TARGET nobody could act on. This function is the fix: main.c computes
 * 3a's own confirmed floor (see its own comment at the call site for exactly which gbp_v28_3a
 * fields that is) and passes it here; gbp_v28_3b_start() then only ever sees a real ladder rung, or
 * is not called at all (the NONE case, below). */
enum gbp_v28_anchor_source {
    GBP_V28_ANCHOR_RULE    = 0,   /* the smallest ladder rung >= 3a's own confirmed floor */
    GBP_V28_ANCHOR_DEFAULT = 1,   /* 3a produced no confirmed floor (cut or partial): T256, frozen */
    GBP_V28_ANCHOR_NONE    = 2    /* the floor sits above T704: no ladder rung reaches it */
};

struct gbp_v28_anchor {
    uint32_t target;              /* meaningful only if source != GBP_V28_ANCHOR_NONE */
    enum gbp_v28_anchor_source source;
};

/* `has_floor`/`floor_native`: 3a's own confirmed floor -- the LOWEST DEPTH WHOSE DWELL ACTUALLY
 * HELD, in native samples, meaningful only if `has_floor`. Compute both with
 * gbp_v28_3a_confirmed_floor() (gbp_v28_3a.h), never `lo` directly: `lo` is the CONFIRM dwell's
 * own target, the highest FAILING depth being re-tested, not the lowest holding one -- see that
 * function's own header comment for the full reasoning (a first attempt at this got it backwards,
 * caught only at Issue #131's own freeze). */
static inline struct gbp_v28_anchor gbp_v28_anchor(uint32_t floor_native, int has_floor)
{
    struct gbp_v28_anchor a;
    if (!has_floor) { a.target = GBP_V28_T256; a.source = GBP_V28_ANCHOR_DEFAULT; return a; }
    a.source = GBP_V28_ANCHOR_RULE;
    if (floor_native <= GBP_V28_T256)      a.target = GBP_V28_T256;
    else if (floor_native <= GBP_V28_T320) a.target = GBP_V28_T320;
    else if (floor_native <= GBP_V28_T448) a.target = GBP_V28_T448;
    else if (floor_native <= GBP_V28_T576) a.target = GBP_V28_T576;
    else if (floor_native <= GBP_V28_T704) a.target = GBP_V28_T704;
    else { a.target = 0u; a.source = GBP_V28_ANCHOR_NONE; }
    return a;
}

static inline const char *gbp_v28_anchor_source_name(enum gbp_v28_anchor_source s)
{
    switch (s) {
    case GBP_V28_ANCHOR_RULE:    return "rule";
    case GBP_V28_ANCHOR_DEFAULT: return "default";
    case GBP_V28_ANCHOR_NONE:    return "none";
    default:                     return "?";
    }
}

/* ---- THE PERCEPTUAL LADDER: the eight rungs the perceptual run's nulling walks (Issue #128 section 3, "the final ladder"; Issue #139 / #141, the nulling handler rebuilt on it).
 * Ordered DEEPEST FIRST: index 0 is the most latency, index GBP_V28_RUNGS - 1 the least (the validated floor, T256 at AHEAD 1). These are the sweep's own eight rungs
 * (gbp_v28_sweep.c's GATE rows 1-7: T704A4 -> T576A4 -> T448A4 -> T320A4 -> T256A4 -> T256A3 -> T256A2 -> T256A1), each held or stepped to by the validation run
 * (RUN 55, 56: the sweep 18 of 18, the AHEAD-1 hold clean). tests/host/test_v28_run57_perceptual.py pins this table against the sweep's own list.
 *
 * L(T, A), tools/v28latency.py (INFERENCE for the values; CORROBORATED for the DMA semantics they rest on since RUN 57): 324.4 / 293.1 / 261.7 / 230.4 / 214.7 / 183.5 / 152.2 / 121.0 ms
 * (the steps between rungs are 31.4, 31.4, 31.4, 15.7, 31.2, 31.2, 31.2 ms). */
#define GBP_V28_RUNGS 8u
struct gbp_v28_rung { uint32_t target, ahead; };
static const struct gbp_v28_rung GBP_V28_RUNG[GBP_V28_RUNGS] = {
    { GBP_V28_T704, GBP_V28_A4 }, { GBP_V28_T576, GBP_V28_A4 }, { GBP_V28_T448, GBP_V28_A4 }, { GBP_V28_T320, GBP_V28_A4 },
    { GBP_V28_T256, GBP_V28_A4 }, { GBP_V28_T256, GBP_V28_A3 }, { GBP_V28_T256, GBP_V28_A2 }, { GBP_V28_T256, GBP_V28_A1 },
};
/* the largest climb between any two rungs is the one START_MUTE was built from: T256 -> T704 */
_Static_assert(GBP_V28_T704 - GBP_V28_T256 <= GBP_V28_START_PAUSE * GBP_APLAY2_PUSHES,
    "gbp_v28_ladder: the widest rung-to-rung climb no longer fits GBP_V28_START_MUTE's derivation");

#ifdef __cplusplus
}
#endif
#endif
