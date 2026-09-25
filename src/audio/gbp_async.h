/*
 * gbp_async — the latency round's session: §V27's state machine and per-second
 * accountant (GitHub Issue #117, HARDWARE_TESTS §V27.0-§V27.13, sync-0001).
 *
 * WHAT IT IS. A pure state machine. The POC hands it ticks (40.5 MHz timebase)
 * and events -- a switch request, a three-way answer, a nulling step, a confirm,
 * every AUDIO block's completion tick with the ring's fill, the chain's running
 * counters -- and gets back decisions (does a switch begin? which transition plan
 * applies? has a dwell ended? is the session over?) and records (the seeded
 * schedule, every switch with its answer, every nulling setting, every Phase 3
 * depth with its counters, one row per whole second of the session). The POC
 * calls it from the pump slot and from the audio tap and logs what it exposes.
 *
 * WHAT IT IS NOT. It knows nothing of hardware: no device, no AI, no pad, no
 * ring. It never mutes, pauses or discards anything itself -- it hands the POC a
 * TRANSITION PLAN and the POC applies it to gbp_aplay / gbp_adec. It reads no
 * C-stick (the POC turns pad edges into the events below). Pure, bounded, no
 * allocation, no printing, no floating point, no blocking call.
 *
 * THE PHASES (§V27.2, §V27.3, §V27.11 §2, §V27.10's caps)
 *   0   from the origin (gbp_async_start) to the first switch request; the
 *       raw-block ride-along happens here, handled by the POC.
 *   1   the blinded A/B: 18 switches (12 REAL + 6 NULL) each followed by one
 *       three-way answer. Ends "complete" when all 18 are answered, "cap" at
 *       cap_p1_s from the FIRST SWITCH, "session" at the session cap, "z" when the
 *       POC asks. Phase 2 begins at the next tick after the running mute ends.
 *   2   nulling: a seeded start on the p2 grid, 128-sample steps under a short
 *       mute, a confirm records the setting and jumps to the next seeded start.
 *       Ends "cap" at cap_p2_s from its first START, "z", "session", or
 *       "complete" when GBP_ASYNC_P2_CAP settings are recorded. Phase 3 begins at
 *       the next tick after the running mute ends.
 *   3   the descent, automatic (§V27.11, the criterion re-frozen by §V27.14):
 *       p3_start down by p3_step per dwell of p3_dwell_s, each depth set WITHOUT
 *       a mute (the plan still carries the climb/discard so the fill lands on the
 *       level). A depth FAILS when, over its dwell, dup == 0 AND starved > 0: the
 *       correction stopped holding the level (the DUP cannot fire and the ring
 *       could not give a WANTED chunk -- `starved` is the POC's gbp_aplay
 *       ring_gated delta, not starved_steps, which also counts the benign wait
 *       after every chunk while READY is full). It is NOT "the depth at which the
 *       audio fails":
 *       the underrun that follows is inevitable but comes ~47 s later, longer
 *       than the dwell (§V27.14 §1-2). On the first failing depth bisect between
 *       the last holding depth (hi) and the failing one (lo): next = (lo + hi) / 2
 *       truncated, a holding result moves hi down, a failing one moves lo up,
 *       until hi - lo <= p3_bisect_width (2: §V27.14 §3), or until the next depth
 *       would equal lo or hi (the bracket cannot shrink any further). The bracket
 *       is then recorded closed (p3_bracket_closed) and, when p3_confirm_s > 0,
 *       a CONFIRM dwell holds the highest FAILING depth (lo) for up to
 *       p3_confirm_s looking for a real underrun (§V27.14 §4): the first underrun
 *       the POC's counters report ends the hold at once (p3_confirm_observed);
 *       otherwise the hold ends at p3_confirm_s and the row says NOT OBSERVED by
 *       its length, never "held". The phase then ends "complete". It also ends
 *       "complete" at p3_min without a failure, or when the first depth already
 *       fails (the bracket is then open: p3_have_hold == 0, no hold); "cap" at
 *       cap_p3_s from its first depth; "session"; "z". When Phase 3 ends the
 *       session is finished. A dwell cut before its end by a cap, the session cap
 *       or Z is still reported (DEPTH_DONE on every tick until depth_done() is
 *       called) and recorded partial with t_done = the cut's instant; a dwell that
 *       had already ended when the phase was cut is recorded whole with t_done =
 *       its own end. Budget: 9 x 6 + 4 x 6 + 60 = 138 s of the 180 s cap.
 *   The session cap (cap_session_s from the origin) ends whatever phase is
 *   running with "session" and finishes the session: gbp_async_finished() is then
 *   1 and the POC stops the AI and saves.
 *
 * THE TRANSITION PLAN (§V27.13: the build's arithmetic, adopted). Every level
 * change is a plan {seq, kind, from, to, mute_chunks, pause_chunks, discard, t}:
 *   seq            1.. over every plan of the session
 *   from, to       the target in force before the plan and the NEW TARGET IN
 *                  FORCE from the plan's instant on (a->target follows `to`)
 *   t              the plan's instant
 *   mech           the transition mechanism (§V27.15): ROTATE for a switch (REAL
 *                  and NULL alike) and a Phase 2 START -- the held queue rotated
 *                  out under the silence, the splice inside it, no artefact;
 *                  HELD for a Phase 2 STEP (mute 4 cannot rotate a whole queue:
 *                  §V27.13's held queue, its splice 125 ms after the silence);
 *                  UNMUTED for a Phase 3 depth. src/audio/gbp_atrans executes it
 *   mute_chunks    cfg.mute_chunks (18, §V27.15) for a switch (REAL or NULL alike)
 *                  and a Phase 2 START; cfg.step_mute_chunks (4) for a Phase 2
 *                  STEP; 0 for a Phase 3 depth -- and never less than the
 *                  mechanism needs for the climb: ROTATE pause + 4 (the climb and
 *                  4 rotations before the last silent hand-off, the worst phase
 *                  included), HELD pause + 1. A Phase 1 switch climbs at most 12:
 *                  16 <= 18, two chunks of margin; a STEP 1: 2 <= 4; a START
 *                  deepening by more than 1 792 mutes pause + 4, at most 29
 *                  chunks (0.906 s)
 *   pause_chunks   ceil((to - from) / 128) when to > from (the producer pauses
 *                  while the ring gains the difference), else 0
 *   discard        from - to when to < from (samples dropped from the ring's
 *                  head), else 0
 *   DEEP -> SHALLOW: discard 1536, pause 0.  SHALLOW -> DEEP: discard 0, pause
 *   12.  NULL: 0, 0 (the mute alone). At MUTE 18 the content skipped is 768 /
 *   2 304 / 3 840 samples (0.1875 / 0.5625 / 0.9375 s): the null at the midpoint. The "target in force" for the per-second
 *   rows changes to `to` at the plan's instant.
 *
 * THE SEED AND THE SCHEDULE (§V27.10; reproduced in Python by tools/v27report.py
 * from the logged seed, so this is the exact algorithm). The generator is
 * xorshift32, the same as tools/v24accept.py `_xorshift32`:
 *     x ^= x << 13;  x ^= x >> 17;  x ^= x << 5;      (all 32-bit)
 * A seed of 0 is replaced by 1 (xorshift32 is stuck at 0). Then, IN THIS ORDER:
 *   draw 1            initial level: bit 0 of x, 0 -> DEEP, 1 -> SHALLOW
 *   the schedule      s[0..real-1] = REAL, s[real..n-1] = NULL (n = real + null),
 *                     then Fisher-Yates: for i = n-1 down to 1: draw x,
 *                     j = x % (i + 1), swap s[i] and s[j]    (n - 1 draws);
 *                     if s[0] is NULL, swap it with the first REAL slot
 *                     (no draw)
 *   3 draws           Phase 2 starts k = 0, 1, 2: p2_lo + (x % nvals) * p2_step,
 *                     nvals = (p2_hi - p2_lo) / p2_step + 1 (26 on the frozen grid)
 *   3 draws           Phase 2 directions k = 0, 1, 2: bit 0 of x,
 *                     0 -> LEFT_DEEPER, 1 -> LEFT_SHALLOWER
 *   later             a setting beyond the third (k >= 3) draws its start and then
 *                     its direction, in that order, at the confirm that records
 *                     setting k - 1 (the generator state is kept in `rng`)
 * Every value derived is exposed in the struct for the SD log.
 *
 * THE PER-SECOND ROWS (§V27.12: tools/v27accept.py reads seconds[] with s, phase,
 * target, mute, settling, count, fill, underruns, overflow). Second s covers
 * [t_origin + s * tb_hz, t_origin + (s + 1) * tb_hz). A second is opened (its
 * target and phase taken as in force) by the first event at or past its start.
 *   count, fill_sum   from gbp_async_block(): AUDIO blocks completed in the
 *                     second, and the sum of the fill sampled before each push
 *                     (mean = fill_sum / count; gbp_async_fill_mean())
 *   mute              1 for every second overlapping the CLOSED interval
 *                     [t, t + mute_chunks * chunk_ticks] of a plan with
 *                     mute_chunks > 0, chunk_ticks = tb_hz * 128 / 4096
 *                     (1 265 625 at 40.5 MHz); marked at the plan's instant
 *   settling          1 for every second overlapping the half-open interval
 *                     [t_mute_end, t_mute_end + settling_s * tb_hz) of every plan
 *                     (mute 0 included: t_mute_end is then the plan's instant)
 *   underruns,        the deltas of the chain's running totals, attributed to the
 *   overflow          second of the gbp_async_second_counters() call that saw them
 * Seconds at or past GBP_ASYNC_SECONDS are counted in sec_overflow, never binned.
 *
 * Time is the POC's: every `now` and `t_done` is a 40.5 MHz timebase tick and
 * tb_hz says how many make a second. No wait is ever unbounded: every phase and
 * the session have a cap in seconds.
 */
#ifndef OPENGBP_GBP_ASYNC_H
#define OPENGBP_GBP_ASYNC_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_ASYNC_CHUNK          128u   /* decoded samples per chunk (gbp_aplay's PUSHES) */
#define GBP_ASYNC_RATE          4096u   /* decoded samples per second, AUDIO blocks per second */
#define GBP_ASYNC_SWITCH_CAP      18u   /* Phase 1: real + null never exceeds this */
#define GBP_ASYNC_P2_CAP          16u   /* Phase 2 settings, starts and directions */
#define GBP_ASYNC_DEPTH_CAP       64u   /* Phase 3 depths */
#define GBP_ASYNC_SECONDS        728u   /* 720 s session + margin */

enum gbp_async_phase { GBP_ASYNC_P0 = 0, GBP_ASYNC_P1 = 1, GBP_ASYNC_P2 = 2, GBP_ASYNC_P3 = 3, GBP_ASYNC_DONE = 4 };
enum gbp_async_level { GBP_ASYNC_DEEP = 0, GBP_ASYNC_SHALLOW = 1 };
enum gbp_async_kind  { GBP_ASYNC_KIND_NONE = 0, GBP_ASYNC_KIND_REAL, GBP_ASYNC_KIND_NULL,
                       GBP_ASYNC_KIND_START, GBP_ASYNC_KIND_STEP, GBP_ASYNC_KIND_DEPTH };
enum gbp_async_dir   { GBP_ASYNC_LEFT_DEEPER = 0, GBP_ASYNC_LEFT_SHALLOWER = 1 };
enum gbp_async_stick { GBP_ASYNC_LEFT = 0, GBP_ASYNC_RIGHT = 1 };
enum gbp_async_answer { GBP_ASYNC_ANSWER_NONE = 0, GBP_ASYNC_MORE = 1, GBP_ASYNC_LESS = 2, GBP_ASYNC_SAME = 3 };
enum gbp_async_end   { GBP_ASYNC_END_NONE = 0, GBP_ASYNC_END_COMPLETE, GBP_ASYNC_END_CAP,
                       GBP_ASYNC_END_SESSION, GBP_ASYNC_END_Z };
enum gbp_async_depth_kind { GBP_ASYNC_DEPTH_STEP = 0, GBP_ASYNC_DEPTH_BISECT = 1, GBP_ASYNC_DEPTH_CONFIRM = 2 };

/* gbp_async_tick()'s return: a bitmask */
#define GBP_ASYNC_TICK_PLAN        1    /* a new transition plan is in a->plan: apply it */
#define GBP_ASYNC_TICK_DEPTH_DONE  2    /* a Phase 3 dwell ended: call gbp_async_depth_done() */
#define GBP_ASYNC_TICK_PHASE       4    /* a phase began or ended during this tick */
#define GBP_ASYNC_TICK_FINISHED    8    /* the session is over: stop the AI, save */

struct gbp_async_cfg {
    uint32_t deep, shallow, floor;          /* samples: 2048 / 512 / 384 */
    uint32_t mute_chunks, step_mute_chunks; /* 18 (§V27.15) / 4 */
    uint32_t p2_lo, p2_hi, p2_step;         /* 384 .. 3584 step 128 */
    uint32_t p3_start, p3_step, p3_dwell_s, p3_bisect_width, p3_min;   /* 384, 32, 6, 2, 128 (width 2: §V27.14) */
    uint32_t p3_confirm_s;                  /* 60: the hold at the highest failing depth (§V27.14) */
    uint32_t cap_p1_s, cap_p2_s, cap_p3_s, cap_session_s;              /* 300, 240, 180, 720 */
    uint32_t real, null;                    /* 12, 6 */
    uint32_t settling_s;                    /* 2 */
    uint32_t tb_hz;                         /* 40 500 000 */
};
extern const struct gbp_async_cfg gbp_async_cfg_default;

/* the transition mechanism a plan asks for (§V27.15; gbp_atrans's modes, same values) */
enum gbp_async_mech { GBP_ASYNC_MECH_UNMUTED = 0, GBP_ASYNC_MECH_HELD = 1, GBP_ASYNC_MECH_ROTATE = 2 };

struct gbp_async_plan {
    uint32_t seq;                           /* 1.. over every plan of the session */
    uint8_t  kind;                          /* enum gbp_async_kind */
    uint8_t  mech;                          /* enum gbp_async_mech: REAL/NULL/START ROTATE, STEP HELD, DEPTH UNMUTED */
    uint32_t from, to;                      /* targets, samples */
    uint32_t mute_chunks, pause_chunks, discard;
    uint64_t t;                             /* the plan's instant */
};

struct gbp_async_switch {
    uint32_t seq;                           /* 1..18 */
    uint8_t  kind;                          /* REAL or NULL */
    uint32_t from, to;                      /* targets */
    uint64_t t;
    uint32_t discard;
    uint8_t  answer;                        /* enum gbp_async_answer, NONE until answered */
    uint64_t t_answer;
};

struct gbp_async_setting {
    uint32_t seq;                           /* 1.. */
    uint32_t start;                         /* the seeded start, samples */
    uint8_t  direction;                     /* enum gbp_async_dir */
    uint32_t steps;                         /* step events taken in the setting */
    uint32_t target;                        /* the confirmed target */
    uint64_t t;
};

struct gbp_async_depth {
    uint32_t target;
    uint8_t  kind;                          /* enum gbp_async_depth_kind */
    uint8_t  partial;                       /* the dwell was cut before its end by a cap, the session cap or Z */
    uint32_t fill_mean_x16, underruns, overflow, dup, drop, lost;
    uint32_t starved;                       /* steps that WANTED a chunk and found the ring short (gbp_aplay ring_gated, §V27.14) */
    uint64_t t_set, t_done;
};

struct gbp_async_phase_rec {
    uint8_t  started, ended;                /* ended: enum gbp_async_end */
    uint64_t t_start, t_end;
};

struct gbp_async {
    struct gbp_async_cfg cfg;
    uint32_t cfg_faults;                    /* a field outside its bounds was replaced by the default */
    uint8_t  started, finished;
    enum gbp_async_phase phase;
    uint64_t t_origin, t_session_end;
    struct gbp_async_phase_rec ph[4];       /* [0] = Phase 0 .. [3] = Phase 3 */
    /* the seed and what it gave */
    uint32_t seed, rng;
    uint8_t  initial;                       /* enum gbp_async_level */
    uint32_t n_sched;                       /* real + null */
    uint8_t  schedule[GBP_ASYNC_SWITCH_CAP];/* enum gbp_async_kind, REAL or NULL */
    uint32_t p2_seeded;                     /* starts/dirs drawn at start (3) */
    uint32_t p2_start[GBP_ASYNC_P2_CAP];
    uint8_t  p2_dir[GBP_ASYNC_P2_CAP];      /* enum gbp_async_dir */
    /* the level in force */
    uint32_t target;
    uint8_t  level;                         /* enum gbp_async_level, Phase 1 */
    struct gbp_async_plan plan;
    uint64_t t_mute_end;
    /* Phase 1 */
    struct gbp_async_switch sw[GBP_ASYNC_SWITCH_CAP];
    uint32_t switches, answered;
    uint8_t  pending;                       /* a switch awaits its answer */
    uint32_t refused_switch_unanswered, refused_switch_mute, refused_switch_exhausted, refused_switch_phase;
    uint32_t refused_answer;
    /* Phase 2 */
    struct gbp_async_setting settings[GBP_ASYNC_P2_CAP];
    uint32_t settings_n, p2_index, p2_steps, p2_steps_deeper, p2_steps_shallower;
    uint32_t refused_step_mute, refused_step_end, refused_step_phase, refused_step_value, refused_confirm;
    /* Phase 3 */
    struct gbp_async_depth depths[GBP_ASYNC_DEPTH_CAP];
    uint32_t depths_n, depths_overflow;
    uint32_t p3_cur;
    uint8_t  p3_cur_kind, p3_dwell_active, p3_depth_pending, p3_bisecting, p3_have_hold, p3_bracket_closed;
    uint8_t  p3_dwell_cut;                  /* the pending dwell was cut before its end: recorded partial */
    uint8_t  p3_confirming, p3_confirm_observed;   /* §V27.14: the hold at the highest failing depth; an underrun seen in it */
    uint32_t p3_lo, p3_hi, p3_last_hold;
    uint64_t t_dwell_end;
    uint32_t refused_depth_done;
    /* per second */
    uint32_t secs_used, sec_overflow;
    uint16_t sec_target[GBP_ASYNC_SECONDS];
    uint8_t  sec_phase[GBP_ASYNC_SECONDS];
    uint8_t  sec_mute[GBP_ASYNC_SECONDS];
    uint8_t  sec_settling[GBP_ASYNC_SECONDS];
    uint32_t sec_count[GBP_ASYNC_SECONDS];
    uint32_t sec_fill_sum[GBP_ASYNC_SECONDS];
    uint32_t sec_underruns[GBP_ASYNC_SECONDS];
    uint32_t sec_overflow_ev[GBP_ASYNC_SECONDS];
    uint8_t  have_counters;
    uint32_t last_underruns, last_overflow, counter_faults;
    uint64_t blocks_in, blocks_before_origin;
};

/* Copies the configuration (NULL -> the default), replacing a field outside its
 * bounds by the default and counting it in cfg_faults. Phase 0 is not yet running. */
void gbp_async_init(struct gbp_async *a, const struct gbp_async_cfg *cfg);

/* The origin (the second 0 begins here) and the seed: derives the initial level, the
 * schedule and the Phase 2 starts and directions as the header says. Once only. */
void gbp_async_start(struct gbp_async *a, uint64_t t_origin, uint32_t seed);

/* The pump's regular call. Opens seconds, applies the caps, begins Phase 2 / Phase 3
 * when due (a plan in a->plan), signals a dwell's end. Returns GBP_ASYNC_TICK_* bits. */
int gbp_async_tick(struct gbp_async *a, uint64_t now);

/* Phase 1: a switch request. 1 when a switch begins (a->plan holds it); 0 when refused:
 * a previous switch unanswered, a mute running, the schedule exhausted, the phase over. */
int gbp_async_switch(struct gbp_async *a, uint64_t now);

/* Phase 1: the three-way answer to the pending switch. 0 when none is pending, it was
 * already answered, or the value is not MORE/LESS/SAME. The 18th answer ends Phase 1. */
int gbp_async_answer(struct gbp_async *a, uint64_t now, uint8_t answer);

/* Phase 2: one 128-sample step, C-stick LEFT or RIGHT mapped through the setting's seeded
 * direction. 1 with a->plan (step mute); 0 out of phase, when `stick` is neither LEFT nor
 * RIGHT (refused_step_value), during a mute or at the grid's end. */
int gbp_async_step(struct gbp_async *a, uint64_t now, uint8_t stick);

/* Phase 2: records the setting and begins the next seeded start. 1 with a->plan. */
int gbp_async_confirm(struct gbp_async *a, uint64_t now);

/* Phase 3: the dwell's counters, after tick returned GBP_ASYNC_TICK_DEPTH_DONE (the bit is
 * repeated on every tick until this is called). Records the depth (partial when the dwell
 * was cut before its end) and plans the next one: 1 when a->plan holds it, 0 when Phase 3
 * is over. */
int gbp_async_depth_done(struct gbp_async *a, uint32_t fill_mean_x16, uint32_t underruns,
                         uint32_t overflow, uint32_t dup, uint32_t drop, uint32_t lost, uint32_t starved);

/* Z as "next phase": ends the running phase with "z"; the next begins at the next tick.
 * In Phase 0 it opens and closes Phase 1 at once. Ending Phase 3 finishes the session. */
void gbp_async_skip(struct gbp_async *a, uint64_t now);

/* Z as "end the session": ends the running phase with "z" and finishes. */
void gbp_async_stop(struct gbp_async *a, uint64_t now);

/* From the audio tap: every AUDIO block's completion tick and the ring's fill before
 * its push. Bins into the second. */
void gbp_async_block(struct gbp_async *a, uint64_t t_done, uint32_t fill_before_push);

/* Once per pump call: the chain's running totals; their deltas land in `now`'s second. */
void gbp_async_second_counters(struct gbp_async *a, uint64_t now, uint32_t underruns_total,
                               uint32_t overflow_total);

/* 1 while a plan's mute is still being handed at `now`. */
int gbp_async_mute_active(const struct gbp_async *a, uint64_t now);

/* 1 once the session is over. */
int gbp_async_finished(const struct gbp_async *a);

/* fill_sum / count of second s; 0 when the second has no block or is out of range. */
uint32_t gbp_async_fill_mean(const struct gbp_async *a, uint32_t s);

/* xorshift32, exposed so a test can pin the generator itself. */
uint32_t gbp_async_xorshift32(uint32_t x);

const char *gbp_async_kind_name(uint8_t kind);
const char *gbp_async_depth_kind_name(uint8_t kind);          /* STEP | BISECT | CONFIRM */
const char *gbp_async_end_name(uint8_t end);
const char *gbp_async_answer_name(uint8_t answer);
const char *gbp_async_level_name(uint8_t level);
const char *gbp_async_dir_name(uint8_t dir);

#ifdef __cplusplus
}
#endif
#endif
