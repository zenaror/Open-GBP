/*
 * tests/unit/test_gbp_async.c — the latency round's session with no device
 * (GitHub Issue #117, §V27.0-§V27.13).
 *
 * The schedule's shape and determinism from three seeds, and the module's own
 * output for seed 0x9E3779B9 pinned as a vector so the generator cannot drift;
 * Phase 1's flow with its refusals and transition plans; Phase 2's steps, clamps,
 * direction mapping and confirms; Phase 3's descent, the bisection on an underrun
 * at 128 and at 160, the dwell timing and the caps; the per-second rows: counts,
 * fill means, the mute and settling flags around a switch at a known time, the
 * counter deltas; the session cap and Z.
 *
 * The review's five defects, each with the test that would have caught it: a
 * dwell already ended when the phase is cut stays whole (partial 0, t_done its
 * own end); a step value that is not a stick is refused, never mapped; an odd
 * bracket under p3_bisect_width 1 closes, a 0 width is a cfg fault, and the
 * shrink guard closes a bracket the midpoint cannot narrow; `to` is the target in
 * force after every plan; DEPTH_DONE is repeated on every tick after a cut until
 * depth_done() is called.
 */
#include <stdio.h>
#include <string.h>
#include "gbp_async.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

#define TB      40500000ull
#define CHUNK   1265625ull                  /* 128 samples at 4096/s in 40.5 MHz ticks */
#define MUTE_N  18u                         /* §V27.15: MUTE 18 chunks, fixed and symmetric */
#define MUTE16  (MUTE_N * CHUNK)            /* the switch's mute in ticks (the name kept from MUTE 16's days) */
#define MUTE4   (4u * CHUNK)
#define T0      1000ull
#define SEED    0x9E3779B9u

/* THE PINNED VECTOR for seed 0x9E3779B9: the module's own output, run once and
 * frozen here so it cannot drift. tools/v27report.py regenerates it in Python
 * from the algorithm documented in gbp_async.h (a 4-seed reproduction in Python
 * matched these values when the vector was taken). */
static const char VEC_SCHED[] = "RNRNRRNRRRNRRRRRNN";
static const uint32_t VEC_STARTS[3] = { 2560u, 1280u, 1024u };
static const uint8_t VEC_DIRS[3] = { GBP_ASYNC_LEFT_DEEPER, GBP_ASYNC_LEFT_DEEPER, GBP_ASYNC_LEFT_DEEPER };
#define VEC_INITIAL GBP_ASYNC_SHALLOW
#define VEC_RNG     0x02e9f4a2u
/* the 4th setting's start and direction, drawn at the 3rd confirm from VEC_RNG */
#define VEC_START4  1152u
#define VEC_DIR4    GBP_ASYNC_LEFT_SHALLOWER

static void started(struct gbp_async *a, uint32_t seed)
{
    gbp_async_init(a, NULL);
    gbp_async_start(a, T0, seed);
}

static void test_the_generator_and_the_shape(void)
{
    static const uint32_t seeds[3] = { SEED, 1u, 0xDEADBEEFu };
    struct gbp_async a, b;
    uint32_t k, i;
    eqi(gbp_async_xorshift32(1u), 270369, "xorshift32(1) = 0x42021, v24accept's generator");
    for (k = 0; k < 3u; k++) {
        uint32_t real = 0, null = 0;
        started(&a, seeds[k]);
        started(&b, seeds[k]);
        eqi(a.n_sched, 18, "18 switches");
        for (i = 0; i < a.n_sched; i++) {
            if (a.schedule[i] == GBP_ASYNC_KIND_REAL) real++;
            else if (a.schedule[i] == GBP_ASYNC_KIND_NULL) null++;
        }
        eqi(real, 12, "12 REAL"); eqi(null, 6, "6 NULL");
        eqi(a.schedule[0], GBP_ASYNC_KIND_REAL, "the first switch is REAL");
        eqi(memcmp(a.schedule, b.schedule, sizeof a.schedule), 0, "same seed, same schedule");
        eqi(memcmp(a.p2_start, b.p2_start, sizeof a.p2_start), 0, "same starts");
        eqi(memcmp(a.p2_dir, b.p2_dir, sizeof a.p2_dir), 0, "same directions");
        eqi(a.initial, b.initial, "same initial level");
        eqi(a.rng, b.rng, "same generator state after the draws");
        for (i = 0; i < 3u; i++) {
            eqi(a.p2_start[i] >= 384u && a.p2_start[i] <= 3584u, 1, "a start inside the grid");
            eqi((a.p2_start[i] - 384u) % 128u, 0, "a start on the grid");
        }
        eqi(a.p2_seeded, 3, "three starts seeded");
    }
    started(&a, 1u); started(&b, 0u);
    eqi(memcmp(a.schedule, b.schedule, sizeof a.schedule), 0, "seed 0 is replaced by 1");
    eqi(b.seed, 0, "but the seed logged is the one given");
}

static void test_the_pinned_vector(void)
{
    struct gbp_async a;
    uint32_t i;
    started(&a, SEED);
    eqi(a.initial, VEC_INITIAL, "initial SHALLOW");
    eqi(a.target, 512, "the target follows the initial level");
    for (i = 0; i < 18u; i++) {
        checks++;
        if ((a.schedule[i] == GBP_ASYNC_KIND_REAL ? 'R' : 'N') != VEC_SCHED[i]) {
            failures++;
            printf("  FAIL: schedule[%u] differs from the pinned vector\n", i);
        }
    }
    for (i = 0; i < 3u; i++) {
        eqi(a.p2_start[i], VEC_STARTS[i], "a pinned start");
        eqi(a.p2_dir[i], VEC_DIRS[i], "a pinned direction");
    }
    eqi(a.rng, VEC_RNG, "the generator state after the six Phase 2 draws");
    eqi(a.cfg_faults, 0, "the default configuration has no fault");
    eqi(a.cfg.cap_session_s, 720, "session cap 720"); eqi(a.cfg.cap_p1_s, 300, "p1 cap 300");
    eqi(a.cfg.cap_p2_s, 240, "p2 cap 240"); eqi(a.cfg.cap_p3_s, 180, "p3 cap 180");
    eqi(a.cfg.mute_chunks, 18, "mute 18 (§V27.15)"); eqi(a.cfg.step_mute_chunks, 4, "step mute 4");
}

static void test_a_bad_configuration_is_replaced(void)
{
    struct gbp_async a;
    struct gbp_async_cfg c = gbp_async_cfg_default;
    c.real = 20u;
    c.tb_hz = 0u;
    gbp_async_init(&a, &c);
    eqi(a.cfg_faults, 2, "two fields out of bounds");
    eqi(a.cfg.real, 12, "real back to 12"); eqi(a.cfg.null, 6, "null back to 6");
    eqi(a.cfg.tb_hz, 40500000, "tb_hz back to 40.5 MHz");
}

/* Phase 1 over the pinned schedule; every plan checked against the level oracle. */
static void test_phase_1_flow(void)
{
    struct gbp_async a;
    uint64_t t = T0 + 10u * TB;
    uint32_t i, level, deep_to_shallow = 0, shallow_to_deep = 0, nulls = 0, exp_unanswered = 0;
    started(&a, SEED);
    eqi(gbp_async_tick(&a, T0 + 5u * TB), 0, "a tick in Phase 0 does nothing");
    eqi(gbp_async_answer(&a, T0 + 5u * TB, GBP_ASYNC_MORE), 0, "an answer with no switch is refused");
    eqi(a.refused_answer, 1, "and counted");
    level = a.initial;
    for (i = 0; i < 18u; i++) {
        const uint8_t kind = a.schedule[i];
        const uint32_t from = (level == GBP_ASYNC_DEEP) ? 2048u : 512u;
        uint32_t to;
        if (kind == GBP_ASYNC_KIND_REAL) level = (level == GBP_ASYNC_DEEP) ? GBP_ASYNC_SHALLOW : GBP_ASYNC_DEEP;
        to = (level == GBP_ASYNC_DEEP) ? 2048u : 512u;
        eqi(gbp_async_switch(&a, t), 1, "the switch begins");
        if (i == 0) {
            eqi(a.phase, GBP_ASYNC_P1, "the first switch opens Phase 1");
            eqi((long long)a.ph[1].t_start, (long long)t, "Phase 1 starts at the first switch");
            eqi(a.ph[0].ended, GBP_ASYNC_END_COMPLETE, "Phase 0 is over");
            eqi(a.plan.seq, 1, "the first plan");
        }
        eqi(a.plan.kind, kind, "the plan's kind is the schedule's");
        eqi(a.plan.from, from, "from"); eqi(a.plan.to, to, "to");
        eqi(a.plan.mute_chunks, MUTE_N, "a switch mutes MUTE chunks, REAL and NULL alike");
        eqi(a.plan.mech, GBP_ASYNC_MECH_ROTATE, "and rotates (§V27.15's (A))");
        eqi((long long)a.plan.t, (long long)t, "the plan's instant");
        if (to < from) {
            eqi(a.plan.discard, 1536, "DEEP -> SHALLOW discards 1536"); eqi(a.plan.pause_chunks, 0, "and pauses 0");
            deep_to_shallow++;
        } else if (to > from) {
            eqi(a.plan.discard, 0, "SHALLOW -> DEEP discards 0"); eqi(a.plan.pause_chunks, 12, "and pauses 12");
            shallow_to_deep++;
        } else {
            eqi(a.plan.discard, 0, "NULL discards 0"); eqi(a.plan.pause_chunks, 0, "and pauses 0");
            eqi(kind, GBP_ASYNC_KIND_NULL, "only a NULL keeps the level");
            nulls++;
        }
        eqi(a.sw[i].seq, i + 1u, "the switch's seq"); eqi(a.sw[i].kind, kind, "its kind");
        eqi(a.sw[i].from, from, "its from"); eqi(a.sw[i].to, to, "its to");
        eqi(a.sw[i].discard, a.plan.discard, "its discard"); eqi(a.sw[i].answer, GBP_ASYNC_ANSWER_NONE, "unanswered");
        eqi(a.target, to, "the target in force is the new one");
        eqi(gbp_async_mute_active(&a, t + MUTE16 - 1u), 1, "the mute runs MUTE chunks");
        eqi(gbp_async_mute_active(&a, t + MUTE16), 0, "and ends exactly there");
        eqi(gbp_async_switch(&a, t + MUTE16 + TB), 0, "a switch while unanswered is refused");
        exp_unanswered++;
        eqi(a.refused_switch_unanswered, exp_unanswered, "and counted");
        eqi(gbp_async_tick(&a, t + TB), 0, "a tick during Phase 1 begins nothing");
        if (i == 1) {                                             /* the second switch: answer inside the mute, then ask again inside it */
            eqi(gbp_async_switch(&a, t + 10u), 0, "a switch during the mute while unanswered is refused as unanswered");
            exp_unanswered++;
            eqi(a.refused_switch_unanswered, exp_unanswered, "the unanswered refusal comes first");
            eqi(gbp_async_answer(&a, t + 20u, GBP_ASYNC_SAME), 1, "an answer during the mute is taken");
            eqi(gbp_async_switch(&a, t + 30u), 0, "a switch during the mute is refused");
            eqi(a.refused_switch_mute, 1, "and counted as such");
            eqi(a.sw[i].answer, GBP_ASYNC_SAME, "recorded");
        } else {
            eqi(gbp_async_answer(&a, t + 2u * TB, 9u), 0, "an answer outside MORE/LESS/SAME is refused");
            eqi(gbp_async_answer(&a, t + 2u * TB, (uint8_t)(1u + i % 3u)), 1, "the answer is taken");
            eqi(a.sw[i].answer, (uint8_t)(1u + i % 3u), "and recorded");
            eqi((long long)a.sw[i].t_answer, (long long)(t + 2u * TB), "with its instant");
            eqi(gbp_async_answer(&a, t + 3u * TB, GBP_ASYNC_SAME), 0, "a second answer is refused");
        }
        t += 5u * TB;
    }
    eqi(a.switches, 18, "18 switches"); eqi(a.answered, 18, "18 answers");
    eqi(deep_to_shallow, 6, "6 DEEP -> SHALLOW"); eqi(shallow_to_deep, 6, "6 SHALLOW -> DEEP"); eqi(nulls, 6, "6 NULL");
    eqi(a.ph[1].ended, GBP_ASYNC_END_COMPLETE, "Phase 1 ends complete at the 18th answer");
    eqi(gbp_async_switch(&a, t), 0, "a 19th switch is refused");
    eqi(a.refused_switch_phase, 1, "as out of phase");
    eqi(a.phase, GBP_ASYNC_P1, "the phase changes only at the tick");
    eqi(gbp_async_tick(&a, t), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "the tick begins Phase 2 with a plan");
    eqi(a.phase, GBP_ASYNC_P2, "Phase 2");
    eqi((long long)a.ph[2].t_start, (long long)t, "at the tick's instant");
    eqi(a.plan.kind, GBP_ASYNC_KIND_START, "a START");
    eqi(a.plan.to, VEC_STARTS[0], "to the first seeded start");
    eqi(a.plan.mute_chunks, a.plan.pause_chunks + 4u > MUTE_N ? a.plan.pause_chunks + 4u : MUTE_N, "under a mute that fits its rotation (MUTE, or pause + 4)");
    eqi(a.plan.mech, GBP_ASYNC_MECH_ROTATE, "a START rotates");
    eqi(a.plan.from, a.sw[17].to, "from the last switch's level");
    eqi(a.plan.seq, 19, "the 19th plan");
}

static void test_phase_1_cap(void)
{
    struct gbp_async a;
    const uint64_t t1 = T0 + 10u * TB;
    started(&a, SEED);
    eqi(gbp_async_switch(&a, t1), 1, "the first switch");
    eqi(gbp_async_tick(&a, t1 + 300u * TB - 1u), 0, "one tick before the cap: nothing");
    eqi(a.ph[1].ended, GBP_ASYNC_END_NONE, "Phase 1 runs");
    eqi(gbp_async_tick(&a, t1 + 300u * TB + 7u), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "the cap ends it and Phase 2 begins");
    eqi(a.ph[1].ended, GBP_ASYNC_END_CAP, "ended: cap");
    eqi((long long)a.ph[1].t_end, (long long)(t1 + 300u * TB), "at the cap's own instant");
    eqi(a.sw[0].answer, GBP_ASYNC_ANSWER_NONE, "the pending switch stays unanswered");
    eqi(gbp_async_answer(&a, t1 + 301u * TB, GBP_ASYNC_MORE), 0, "an answer after the phase is refused");
    eqi(a.phase, GBP_ASYNC_P2, "Phase 2");
    /* the cap falling inside a mute: Phase 2 waits for the mute's end */
    started(&a, SEED);
    eqi(gbp_async_switch(&a, t1), 1, "switch 1");
    eqi(gbp_async_answer(&a, t1 + TB, GBP_ASYNC_MORE), 1, "answered");
    eqi(gbp_async_switch(&a, t1 + 300u * TB - 10u), 1, "switch 2 just before the cap");
    eqi(gbp_async_tick(&a, t1 + 300u * TB + 10u), 0, "the cap ends Phase 1 but the mute holds Phase 2");
    eqi(a.ph[1].ended, GBP_ASYNC_END_CAP, "ended: cap");
    eqi(gbp_async_tick(&a, t1 + 300u * TB - 10u + MUTE16), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 2 begins when the mute ends");
}

/* Phase 0 -> skip -> tick: Phase 2 at `t` with its START; returns the mute's end. */
static uint64_t into_phase_2(struct gbp_async *a, uint64_t t)
{
    started(a, SEED);
    gbp_async_skip(a, t - TB);
    eqi(a->ph[1].started, 1, "skip in Phase 0 opens Phase 1"); eqi(a->ph[1].ended, GBP_ASYNC_END_Z, "and ends it: z");
    eqi(gbp_async_tick(a, t), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 2 begins");
    eqi(a->plan.kind, GBP_ASYNC_KIND_START, "with a START");
    eqi(a->plan.from, 512, "from SHALLOW"); eqi(a->plan.to, 2560, "to the first start");
    eqi(a->plan.pause_chunks, 16, "pause ceil(2048/128)"); eqi(a->plan.discard, 0, "no discard");
    eqi(a->plan.mute_chunks, 20, "the mute fits the rotation: pause + 4 = 20 > MUTE");
    return t + 20u * CHUNK;                                   /* the mute's end */
}

/* a START whose climb outruns MUTE: the mute stretches to pause + 4, ROTATE's need (review before the
 * commit: at 16 the transition ended with the ring 1 152 short and the DUP slewed for ~40 s; the +1 is
 * the feed's worst phase, gbp_atrans.h) */
static void test_a_start_mute_covers_its_pause(void)
{
    struct gbp_async a;
    const uint64_t t = T0 + 20u * TB;
    started(&a, SEED);
    a.p2_start[0] = 3584u;                        /* the deepest seeded start, from SHALLOW */
    gbp_async_skip(&a, t - TB);
    eqi(gbp_async_tick(&a, t), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 2 begins");
    eqi(a.plan.kind, GBP_ASYNC_KIND_START, "with a START"); eqi(a.plan.from, 512, "from 512"); eqi(a.plan.to, 3584, "to 3584");
    eqi(a.plan.pause_chunks, 24, "pause ceil(3072/128) = 24"); eqi(a.plan.mute_chunks, 28, "and the mute is pause + 4 = 28, not 18");
    eqi(a.plan.discard, 0, "no discard");
    eqi(gbp_async_mute_active(&a, t + 27u * CHUNK), 1, "silent at chunk 27");
    eqi(gbp_async_mute_active(&a, t + 28u * CHUNK + 1u), 0, "over after chunk 28");
    eqi(gbp_async_step(&a, t + 17u * CHUNK, GBP_ASYNC_LEFT), 0, "a step at chunk 17 is still refused");
    eqi(a.refused_step_mute, 1, "and counted");
    eqi(a.sec_mute[20], 1, "the second of the plan is a mute second");
    /* a Phase 1 switch keeps exactly MUTE: its largest pause is 12, 12 + 4 = 16 <= 18 */
    started(&a, SEED);
    eqi(gbp_async_switch(&a, t), 1, "switch 1 (SHALLOW -> DEEP)");
    eqi(a.plan.pause_chunks, 12, "pause 12"); eqi(a.plan.mute_chunks, MUTE_N, "MUTE as frozen (§V27.15)");
    /* the deepest START of all: 384 -> 3584, pause 25, mute 29 = 0.906 s (§V27.15's "at most 29") */
    started(&a, SEED);
    a.p2_start[0] = 3584u;
    a.target = 384u;                               /* as if Phase 1 had ended at the floor */
    gbp_async_skip(&a, t - TB);
    eqi(gbp_async_tick(&a, t), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 2");
    eqi(a.plan.pause_chunks, 25, "pause 25"); eqi(a.plan.mute_chunks, 29, "mute 29, the most any plan takes");
    /* a STEP keeps 4: its pause is 1 */
    {
        const uint64_t t_free = into_phase_2(&a, t);          /* the START's (stretched) mute's end */
        eqi(gbp_async_step(&a, t_free, GBP_ASYNC_LEFT), 1, "a step");
    }
    eqi(a.plan.pause_chunks, 1, "pause 1"); eqi(a.plan.mute_chunks, 4, "mute 4 as frozen: 1 + 1 <= 4");
    eqi(a.plan.mech, GBP_ASYNC_MECH_HELD, "a STEP holds its queue (§V27.15)");
}

static void test_phase_2(void)
{
    struct gbp_async a;
    uint64_t t = into_phase_2(&a, T0 + 20u * TB);
    uint32_t k;
    eqi(gbp_async_step(&a, t - 1u, GBP_ASYNC_LEFT), 0, "a step during the START's mute is refused");
    eqi(a.refused_step_mute, 1, "and counted");
    eqi(gbp_async_confirm(&a, t - 1u), 0, "a confirm during the mute is refused");
    eqi(a.refused_confirm, 1, "and counted");
    /* LEFT_DEEPER for this seed: LEFT deepens */
    eqi(gbp_async_step(&a, t, GBP_ASYNC_LEFT), 1, "LEFT steps");
    eqi(a.plan.kind, GBP_ASYNC_KIND_STEP, "a STEP"); eqi(a.plan.to, 2688, "128 deeper");
    eqi(a.plan.mute_chunks, 4, "under a 4-chunk mute"); eqi(a.plan.pause_chunks, 1, "pause 1"); eqi(a.plan.discard, 0, "discard 0");
    eqi(gbp_async_step(&a, t + MUTE4 - 1u, GBP_ASYNC_RIGHT), 0, "a step inside the step mute is refused");
    t += MUTE4;
    eqi(gbp_async_step(&a, t, GBP_ASYNC_RIGHT), 1, "RIGHT steps");
    eqi(a.plan.to, 2560, "128 shallower"); eqi(a.plan.discard, 128, "discard 128"); eqi(a.plan.pause_chunks, 0, "pause 0");
    t += MUTE4;
    for (k = 0; k < 8u; k++) {                                   /* 2560 -> 3584 */
        eqi(gbp_async_step(&a, t, GBP_ASYNC_LEFT), 1, "a step up the grid");
        t += MUTE4;
    }
    eqi(a.target, 3584, "at the top");
    eqi(gbp_async_step(&a, t, GBP_ASYNC_LEFT), 0, "the grid's top refuses a deeper step");
    eqi(a.refused_step_end, 1, "and counts it");
    eqi(a.p2_steps, 10, "10 steps taken"); eqi(a.p2_steps_deeper, 9, "9 deeper"); eqi(a.p2_steps_shallower, 1, "1 shallower");
    eqi(gbp_async_confirm(&a, t), 1, "confirm records and begins the next start");
    eqi(a.settings_n, 1, "one setting");
    eqi(a.settings[0].seq, 1, "seq 1"); eqi(a.settings[0].start, 2560, "its start");
    eqi(a.settings[0].direction, GBP_ASYNC_LEFT_DEEPER, "its direction"); eqi(a.settings[0].steps, 10, "its steps");
    eqi(a.settings[0].target, 3584, "its target"); eqi((long long)a.settings[0].t, (long long)t, "its instant");
    eqi(a.plan.kind, GBP_ASYNC_KIND_START, "a START"); eqi(a.plan.to, 1280, "to the second seeded start");
    eqi(a.plan.discard, 2304, "discard 3584 - 1280"); eqi(a.plan.mute_chunks, MUTE_N, "a MUTE-chunk mute");
    t += MUTE16;
    /* the bottom of the grid */
    for (k = 0; k < 7u; k++) { eqi(gbp_async_step(&a, t, GBP_ASYNC_RIGHT), 1, "down the grid"); t += MUTE4; }
    eqi(a.target, 384, "at the bottom");
    eqi(gbp_async_step(&a, t, GBP_ASYNC_RIGHT), 0, "the grid's bottom refuses a shallower step");
    eqi(gbp_async_confirm(&a, t), 1, "setting 2");
    eqi(a.settings[1].steps, 7, "7 steps"); eqi(a.settings[1].target, 384, "at 384");
    eqi(a.plan.to, 1024, "to the third seeded start"); eqi(a.plan.pause_chunks, 5, "pause ceil(640/128)");
    t += MUTE16;
    eqi(gbp_async_confirm(&a, t), 1, "setting 3, no step");
    eqi(a.settings[2].steps, 0, "0 steps"); eqi(a.settings[2].target, 1024, "the start itself");
    eqi(a.settings[2].start, 1024, "its start");
    eqi(a.p2_index, 3, "a 4th setting begins");
    eqi(a.p2_start[3], VEC_START4, "its start drawn from the kept generator state");
    eqi(a.p2_dir[3], VEC_DIR4, "and its direction");
    eqi(a.plan.to, VEC_START4, "the START goes there");
    t += MUTE16;
    /* LEFT_SHALLOWER now: LEFT shallows */
    eqi(gbp_async_step(&a, t, GBP_ASYNC_LEFT), 1, "LEFT under LEFT_SHALLOWER");
    eqi(a.plan.to, VEC_START4 - 128u, "goes shallower");
    t += MUTE4;
    eqi(gbp_async_step(&a, t, GBP_ASYNC_RIGHT), 1, "RIGHT under LEFT_SHALLOWER");
    eqi(a.plan.to, VEC_START4, "goes deeper");
    eqi(a.ph[2].ended, GBP_ASYNC_END_NONE, "Phase 2 continues past three settings");
    /* the cap, from Phase 2's first START */
    eqi(gbp_async_tick(&a, a.ph[2].t_start + 240u * TB), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "the cap ends Phase 2 and Phase 3 begins");
    eqi(a.ph[2].ended, GBP_ASYNC_END_CAP, "ended: cap");
    eqi(a.phase, GBP_ASYNC_P3, "Phase 3");
    eqi(a.plan.kind, GBP_ASYNC_KIND_DEPTH, "its first depth"); eqi(a.plan.to, 384, "384");
    eqi(a.plan.mute_chunks, 0, "no mute"); eqi(a.plan.discard, VEC_START4 - 384u, "the discard still applies");
    eqi(gbp_async_step(&a, a.ph[2].t_start + 241u * TB, GBP_ASYNC_LEFT), 0, "a step in Phase 3 is refused");
    eqi(a.refused_step_phase, 1, "as out of phase");
}

/* Phase 0 -> Phase 3 at `t3`, the first depth set; returns t3. */
static uint64_t into_phase_3(struct gbp_async *a, uint64_t t3)
{
    (void)into_phase_2(a, t3 - 2u * TB);
    gbp_async_skip(a, t3 - TB);
    eqi(a->ph[2].ended, GBP_ASYNC_END_Z, "Phase 2 ended: z");
    eqi(gbp_async_tick(a, t3), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 3 begins with its first depth");
    eqi(a->phase, GBP_ASYNC_P3, "Phase 3"); eqi(a->plan.to, 384, "384"); eqi(a->plan.mute_chunks, 0, "no mute");
    eqi((long long)a->t_dwell_end, (long long)(t3 + 6u * TB), "the dwell is 6 s");
    return t3;
}

/* one dwell: ticks around its end, then the counters; returns depth_done's result */
static int dwell(struct gbp_async *a, uint64_t *t, uint32_t underruns)
{
    const uint64_t t_end = a->t_dwell_end;
    eqi(gbp_async_tick(a, t_end - 1u), 0, "one tick before the dwell's end: nothing");
    eqi(gbp_async_depth_done(a, 0u, 0u, 0u, 0u, 0u, 0u, 0u), 0, "depth_done before the dwell's end is refused");
    eqi(gbp_async_tick(a, t_end + 100u), GBP_ASYNC_TICK_DEPTH_DONE, "the dwell's end");
    eqi(gbp_async_tick(a, t_end + 200u), GBP_ASYNC_TICK_DEPTH_DONE, "repeated until reported");
    *t = t_end + 200u;
    /* §V27.14: a dwell FAILS by dup == 0 && starved > 0; the helper's `underruns` doubles as "this dwell
     * fails" (dup 0, starved 40) and is recorded on the row as given */
    return gbp_async_depth_done(a, a->p3_cur * 16u, underruns, 0u, underruns ? 0u : 3u, 0u, 1u, underruns ? 40u : 0u);
}

static void test_phase_3_descent_without_an_underrun(void)
{
    struct gbp_async a;
    uint64_t t = into_phase_3(&a, T0 + 30u * TB);
    uint32_t k;
    for (k = 0; k < 8u; k++) {
        eqi(dwell(&a, &t, 0u), 1, "a holding depth plans the next");
        eqi(a.plan.kind, GBP_ASYNC_KIND_DEPTH, "a depth"); eqi(a.plan.to, 384u - 32u * (k + 1u), "32 shallower");
        eqi(a.plan.discard, 32, "discard 32"); eqi(a.plan.mute_chunks, 0, "no mute");
        eqi((long long)a.plan.t, (long long)(T0 + 30u * TB + 6u * TB * (k + 1u)), "set at the dwell's end, on the 6 s grid");
        eqi((long long)a.t_dwell_end, (long long)(a.plan.t + 6u * TB), "the next dwell");
    }
    eqi(a.p3_cur, 128, "at the floor");
    eqi(dwell(&a, &t, 0u), 0, "the floor holds: nothing follows");
    eqi(a.ph[3].ended, GBP_ASYNC_END_COMPLETE, "ended: complete");
    eqi(gbp_async_finished(&a), 1, "the session is finished");
    eqi(a.depths_n, 9, "9 depths recorded");
    for (k = 0; k < 9u; k++) {
        eqi(a.depths[k].target, 384u - 32u * k, "the depth's target");
        eqi(a.depths[k].kind, GBP_ASYNC_DEPTH_STEP, "a STEP"); eqi(a.depths[k].partial, 0, "whole");
        eqi(a.depths[k].fill_mean_x16, (384u - 32u * k) * 16u, "its fill"); eqi(a.depths[k].underruns, 0, "no underrun");
        eqi(a.depths[k].dup, 3, "dup"); eqi(a.depths[k].lost, 1, "lost"); eqi(a.depths[k].starved, 0, "not starved");
    }
    eqi(a.p3_have_hold, 1, "a holding depth exists"); eqi(a.p3_bisecting, 0, "no bisection");
    eqi(a.p3_confirming, 0, "no failing depth: no confirm hold");
    eqi(gbp_async_tick(&a, t + 1u), GBP_ASYNC_TICK_PHASE | GBP_ASYNC_TICK_FINISHED, "the tick reports the end once");
    eqi(a.phase, GBP_ASYNC_DONE, "DONE");
    eqi(gbp_async_tick(&a, t + 2u), GBP_ASYNC_TICK_FINISHED, "then only FINISHED");
}

static void test_phase_3_bisects_to_width_2_then_holds_the_failing_depth(void)
{
    struct gbp_async a;
    uint64_t t = into_phase_3(&a, T0 + 30u * TB), t_hold;
    uint32_t k;
    for (k = 0; k < 8u; k++) eqi(dwell(&a, &t, 0u), 1, "down to 128");
    eqi(a.p3_cur, 128, "128");
    eqi(dwell(&a, &t, 2u), 1, "128 fails (dup 0, starved > 0): bisect");
    eqi(a.p3_lo, 128, "lo = the failing depth"); eqi(a.p3_hi, 160, "hi = the last holding depth");
    eqi(a.plan.to, 144, "next = (128 + 160) / 2"); eqi(a.plan.kind, GBP_ASYNC_KIND_DEPTH, "a depth");
    eqi(a.plan.pause_chunks, 1, "deepening by 16: pause 1"); eqi(a.plan.discard, 0, "no discard");
    eqi(a.p3_cur_kind, GBP_ASYNC_DEPTH_BISECT, "BISECT");
    eqi(dwell(&a, &t, 1u), 1, "144 fails");
    eqi(a.p3_lo, 144, "lo up"); eqi(a.plan.to, 152, "next = (144 + 160) / 2");
    eqi(dwell(&a, &t, 0u), 1, "152 holds");
    eqi(a.p3_hi, 152, "hi down"); eqi(a.plan.to, 148, "next = (144 + 152) / 2");
    eqi(dwell(&a, &t, 0u), 1, "148 holds");
    eqi(a.p3_hi, 148, "hi down"); eqi(a.plan.to, 146, "next = (144 + 148) / 2");
    eqi(dwell(&a, &t, 0u), 1, "146 holds: the bracket (144, 146] is 2 wide -- closed, and the hold follows");
    eqi(a.p3_hi, 146, "hi down"); eqi(a.p3_bracket_closed, 1, "closed");
    eqi(a.p3_confirming, 1, "the confirm hold"); eqi(a.p3_cur_kind, GBP_ASYNC_DEPTH_CONFIRM, "CONFIRM");
    eqi(a.plan.to, 144, "at the highest FAILING depth"); eqi(a.plan.kind, GBP_ASYNC_KIND_DEPTH, "a depth plan");
    eqi(a.plan.mute_chunks, 0, "no mute"); eqi(a.plan.discard, 2, "146 -> 144: discard 2");
    t_hold = a.plan.t;
    eqi((long long)a.t_dwell_end, (long long)(t_hold + 60u * TB), "the hold is 60 s");
    eqi(a.ph[3].ended, GBP_ASYNC_END_NONE, "Phase 3 continues through the hold");
    /* NOT OBSERVED: the hold runs its 60 s with no underrun */
    eqi(dwell(&a, &t, 0u), 0, "the hold ends at 60 s: nothing follows");
    eqi(a.ph[3].ended, GBP_ASYNC_END_COMPLETE, "ended: complete"); eqi(gbp_async_finished(&a), 1, "finished");
    eqi(a.p3_confirm_observed, 0, "no underrun observed");
    eqi(a.depths_n, 14, "9 + 4 + the hold");
    eqi(a.depths[8].target, 128, "128"); eqi(a.depths[8].starved, 40, "starved"); eqi(a.depths[8].dup, 0, "dup 0"); eqi(a.depths[8].kind, GBP_ASYNC_DEPTH_STEP, "STEP");
    eqi(a.depths[9].target, 144, "144"); eqi(a.depths[9].kind, GBP_ASYNC_DEPTH_BISECT, "BISECT"); eqi(a.depths[9].underruns, 1, "fail");
    eqi(a.depths[10].target, 152, "152"); eqi(a.depths[11].target, 148, "148"); eqi(a.depths[12].target, 146, "146");
    eqi(a.depths[12].dup, 3, "146 holds by the DUP"); eqi(a.depths[12].starved, 0, "not starved");
    eqi(a.depths[13].target, 144, "the hold at 144"); eqi(a.depths[13].kind, GBP_ASYNC_DEPTH_CONFIRM, "CONFIRM");
    eqi(a.depths[13].underruns, 0, "no underrun"); eqi(a.depths[13].partial, 0, "whole");
    eqi((long long)(a.depths[13].t_done - a.depths[13].t_set), (long long)(60u * TB), "its length: 60 s");
}

static void test_the_confirm_hold_ends_at_its_first_underrun(void)
{
    struct gbp_async a;
    uint64_t t = into_phase_3(&a, T0 + 30u * TB), t_hold;
    uint32_t k;
    gbp_async_second_counters(&a, t, 0u, 0u);                /* the baseline */
    for (k = 0; k < 8u; k++) eqi(dwell(&a, &t, 0u), 1, "down to 128");
    eqi(dwell(&a, &t, 2u), 1, "128 fails");
    eqi(dwell(&a, &t, 1u), 1, "144 fails");
    eqi(dwell(&a, &t, 0u), 1, "152 holds"); eqi(dwell(&a, &t, 0u), 1, "148 holds"); eqi(dwell(&a, &t, 0u), 1, "146 holds");
    eqi(a.p3_cur_kind, GBP_ASYNC_DEPTH_CONFIRM, "the hold");
    t_hold = a.plan.t;
    /* OBSERVED: the POC's counters report an underrun 20 s into the hold */
    gbp_async_second_counters(&a, t_hold + 10u * TB, 0u, 0u);
    eqi((long long)a.t_dwell_end, (long long)(t_hold + 60u * TB), "no underrun yet: the hold runs on");
    eqi(gbp_async_tick(&a, t_hold + 10u * TB), 0, "nothing at 10 s");
    gbp_async_second_counters(&a, t_hold + 20u * TB, 1u, 0u);
    eqi((long long)a.t_dwell_end, (long long)(t_hold + 20u * TB), "the underrun ends the hold at once");
    eqi(a.p3_confirm_observed, 1, "observed");
    eqi(gbp_async_tick(&a, t_hold + 20u * TB), GBP_ASYNC_TICK_DEPTH_DONE, "the dwell's end");
    eqi(gbp_async_depth_done(&a, 144u * 16u, 1u, 0u, 0u, 0u, 0u, 30u), 0, "recorded: nothing follows");
    eqi(a.ph[3].ended, GBP_ASYNC_END_COMPLETE, "ended: complete");
    eqi(a.depths[13].kind, GBP_ASYNC_DEPTH_CONFIRM, "CONFIRM"); eqi(a.depths[13].underruns, 1, "the underrun");
    eqi((long long)(a.depths[13].t_done - a.depths[13].t_set), (long long)(20u * TB), "the hold's length: 20 s");
    eqi(a.depths[13].partial, 0, "whole: it ended by its own rule");
    /* an underrun reported after the hold's end is not the hold's */
    t = into_phase_3(&a, T0 + 30u * TB);
    gbp_async_second_counters(&a, t, 0u, 0u);
    for (k = 0; k < 8u; k++) eqi(dwell(&a, &t, 0u), 1, "down to 128");
    eqi(dwell(&a, &t, 2u), 1, "128 fails"); eqi(dwell(&a, &t, 1u), 1, "144 fails");
    eqi(dwell(&a, &t, 0u), 1, "152"); eqi(dwell(&a, &t, 0u), 1, "148"); eqi(dwell(&a, &t, 0u), 1, "146");
    t_hold = a.plan.t;
    gbp_async_second_counters(&a, t_hold + 61u * TB, 1u, 0u);
    eqi((long long)a.t_dwell_end, (long long)(t_hold + 60u * TB), "past the end: the hold's end stands");
    eqi(a.p3_confirm_observed, 0, "not observed");
}

static void test_phase_3_bisects_from_160(void)
{
    struct gbp_async a;
    uint64_t t = into_phase_3(&a, T0 + 30u * TB);
    uint32_t k;
    for (k = 0; k < 7u; k++) eqi(dwell(&a, &t, 0u), 1, "down to 160");
    eqi(a.p3_cur, 160, "160");
    eqi(dwell(&a, &t, 1u), 1, "160 fails");
    eqi(a.p3_lo, 160, "lo"); eqi(a.p3_hi, 192, "hi"); eqi(a.plan.to, 176, "176");
    eqi(dwell(&a, &t, 0u), 1, "176 holds"); eqi(a.p3_hi, 176, "hi down"); eqi(a.plan.to, 168, "168");
    eqi(dwell(&a, &t, 0u), 1, "168 holds"); eqi(a.p3_hi, 168, "hi down"); eqi(a.plan.to, 164, "164");
    eqi(dwell(&a, &t, 0u), 1, "164 holds"); eqi(a.p3_hi, 164, "hi down"); eqi(a.plan.to, 162, "162");
    eqi(dwell(&a, &t, 0u), 1, "162 holds: (160, 162] is 2 wide, the hold follows");
    eqi(a.p3_lo, 160, "lo"); eqi(a.p3_hi, 162, "hi"); eqi(a.plan.to, 160, "the hold at 160");
    eqi(a.p3_cur_kind, GBP_ASYNC_DEPTH_CONFIRM, "CONFIRM");
    eqi(dwell(&a, &t, 0u), 0, "the hold ends: complete");
    eqi(a.depths_n, 13, "8 + 4 + the hold");
    /* the other branch: 176 fails */
    t = into_phase_3(&a, T0 + 30u * TB);
    for (k = 0; k < 7u; k++) eqi(dwell(&a, &t, 0u), 1, "down to 160");
    eqi(dwell(&a, &t, 1u), 1, "160 fails");
    eqi(dwell(&a, &t, 1u), 1, "176 fails");
    eqi(a.p3_lo, 176, "lo up"); eqi(a.plan.to, 184, "184");
    eqi(dwell(&a, &t, 0u), 1, "184 holds"); eqi(a.plan.to, 180, "180");
    eqi(dwell(&a, &t, 0u), 1, "180 holds"); eqi(a.plan.to, 178, "178");
    eqi(dwell(&a, &t, 0u), 1, "178 holds: (176, 178], the hold follows");
    eqi(a.plan.to, 176, "the hold at 176"); eqi(a.p3_cur_kind, GBP_ASYNC_DEPTH_CONFIRM, "CONFIRM");
    eqi(dwell(&a, &t, 1u), 0, "the hold ends with its underrun: complete");
    eqi(a.ph[3].ended, GBP_ASYNC_END_COMPLETE, "complete");
}

static void into_phase_3_cfg(struct gbp_async *a, const struct gbp_async_cfg *cfg, uint64_t t3);

/* The tap usually reaches the module first when a cap cuts a Phase 3 dwell (it runs inside the service
 * transaction, before the pump): gbp_async_block crosses the cap, `finished` is set with the cut dwell still
 * pending, and only a later tick delivers it. The POC therefore runs its tick path while a depth is pending
 * (review of round 3's fixes: the row was lost when it did not). */
static void test_a_cap_crossed_by_the_tap_still_reports_the_cut_dwell(void)
{
    struct gbp_async a;
    struct gbp_async_cfg c = gbp_async_cfg_default;
    uint64_t t;
    const uint64_t t3 = T0 + 30u * TB;
    c.cap_p3_s = 20u;
    into_phase_3_cfg(&a, &c, t3);
    (void)dwell(&a, &t, 0u); (void)dwell(&a, &t, 0u); (void)dwell(&a, &t, 0u);   /* 18 s: 384, 352, 320 hold */
    eqi(a.p3_dwell_active, 1, "the fourth dwell (288) is running");
    gbp_async_block(&a, t3 + 20u * TB + 1u, 300u);              /* the tap crosses the cap first */
    eqi(gbp_async_finished(&a), 1, "the cap finished the session");
    eqi(a.p3_depth_pending, 1, "with the cut dwell still pending");
    eqi(gbp_async_tick(&a, t3 + 20u * TB + 2u) & GBP_ASYNC_TICK_DEPTH_DONE, GBP_ASYNC_TICK_DEPTH_DONE,
        "a tick after `finished` still reports it");
    eqi(gbp_async_depth_done(&a, 288u * 16u, 0u, 0u, 20u, 0u, 0u, 0u), 0, "recorded; nothing follows");
    eqi(a.depths_n, 4, "four depths"); eqi(a.depths[3].target, 288, "the cut one"); eqi(a.depths[3].partial, 1, "partial");
    eqi(a.p3_depth_pending, 0, "nothing pending");
}

static void test_phase_3_caps_and_the_open_bracket(void)
{
    struct gbp_async a;
    uint64_t t3 = into_phase_3(&a, T0 + 30u * TB), t;
    /* the first depth fails: the bracket is open */
    eqi(dwell(&a, &t, 3u), 0, "384 underruns: nothing to bisect against");
    eqi(a.p3_have_hold, 0, "no holding depth"); eqi(a.p3_bracket_closed, 0, "the bracket is open");
    eqi(a.ph[3].ended, GBP_ASYNC_END_COMPLETE, "complete"); eqi(gbp_async_finished(&a), 1, "finished");
    eqi(a.depths_n, 1, "one depth");
    /* the phase cap cuts a dwell: with 4-sample steps the descent has 64 depths, more than
     * the 30 dwells the 180 s cap allows, so the 30th is cut at its own end */
    {
        struct gbp_async_cfg c = gbp_async_cfg_default;
        uint32_t n = 0;
        c.p3_step = 4u;
        gbp_async_init(&a, &c);
        gbp_async_start(&a, T0, SEED);
        t3 = T0 + 30u * TB;
        gbp_async_skip(&a, t3 - 3u * TB);
        eqi(gbp_async_tick(&a, t3 - 2u * TB), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 2");
        gbp_async_skip(&a, t3 - TB);
        eqi(gbp_async_tick(&a, t3), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 3");
        for (t = t3; a.t_dwell_end + 100u < t3 + 180u * TB && n < 64u; n++) eqi(dwell(&a, &t, 0u), 1, "holding");
        eqi(n, 29, "29 whole dwells before the cap"); eqi(a.p3_cur, 384u - 4u * 29u, "the 30th depth");
        eqi((long long)a.t_dwell_end, (long long)(t3 + 180u * TB), "ends exactly at the cap");
    }
    eqi(gbp_async_tick(&a, t3 + 180u * TB), GBP_ASYNC_TICK_PHASE | GBP_ASYNC_TICK_FINISHED | GBP_ASYNC_TICK_DEPTH_DONE, "the cap: finished, with the cut dwell to report");
    eqi(a.ph[3].ended, GBP_ASYNC_END_CAP, "ended: cap");
    eqi((long long)a.ph[3].t_end, (long long)(t3 + 180u * TB), "at the cap's instant");
    eqi(gbp_async_tick(&a, t3 + 180u * TB + 1u), GBP_ASYNC_TICK_FINISHED | GBP_ASYNC_TICK_DEPTH_DONE, "the next tick still carries the cut dwell");
    eqi(gbp_async_depth_done(&a, 100u, 0u, 0u, 0u, 0u, 0u, 0u), 0, "the cut depth is recorded, nothing follows");
    eqi(gbp_async_tick(&a, t3 + 180u * TB + 2u), GBP_ASYNC_TICK_FINISHED, "reported: the tick carries FINISHED alone");
    eqi(a.depths[a.depths_n - 1u].partial, 1, "marked partial");
    eqi((long long)a.depths[a.depths_n - 1u].t_done, (long long)(t3 + 180u * TB), "done at the cut");
    eqi(a.depths_n, 30, "180 / 6 = 30 dwells, the last cut");
    eqi(a.phase, GBP_ASYNC_DONE, "DONE");
}

/* Defect 1: a dwell that had ENDED (DEPTH_DONE already returned) when the phase is cut
 * by Z or by the session cap before depth_done() is called is a whole dwell: partial 0,
 * t_done its own end, not the cut's instant. A dwell cut mid-way stays partial. */
static void test_a_dwell_ended_before_the_cut_stays_whole(void)
{
    struct gbp_async a;
    struct gbp_async_cfg c = gbp_async_cfg_default;
    const uint64_t t3 = T0 + 30u * TB, t_end = t3 + 6u * TB;
    /* Z as stop after the dwell's end */
    (void)into_phase_3(&a, t3);
    eqi(gbp_async_tick(&a, t_end + 100u), GBP_ASYNC_TICK_DEPTH_DONE, "the dwell ends");
    eqi(a.p3_dwell_active, 0, "no dwell runs"); eqi(a.p3_depth_pending, 1, "one to report");
    gbp_async_stop(&a, t_end + 200u);
    eqi(a.ph[3].ended, GBP_ASYNC_END_Z, "Phase 3 ended: z"); eqi(gbp_async_finished(&a), 1, "finished");
    eqi(a.p3_dwell_cut, 0, "the dwell was not cut: it had ended");
    eqi(gbp_async_tick(&a, t_end + 300u), GBP_ASYNC_TICK_PHASE | GBP_ASYNC_TICK_FINISHED | GBP_ASYNC_TICK_DEPTH_DONE, "the tick still carries the dwell");
    eqi(gbp_async_depth_done(&a, 384u * 16u, 0u, 0u, 0u, 0u, 0u, 0u), 0, "recorded, nothing follows");
    eqi(a.depths_n, 1, "one depth");
    eqi(a.depths[0].partial, 0, "WHOLE: it ended before the Z");
    eqi((long long)a.depths[0].t_done, (long long)t_end, "done at the dwell's own end, not at the Z");
    eqi((long long)a.depths[0].t_set, (long long)t3, "set at Phase 3's start");
    eqi(a.depths[0].target, 384, "384"); eqi(a.depths[0].fill_mean_x16, 384u * 16u, "its fill");
    eqi(a.p3_dwell_cut, 0, "the flag stays clear");
    eqi(gbp_async_tick(&a, t_end + 400u), GBP_ASYNC_TICK_FINISHED, "then FINISHED alone");
    /* the same dwell cut mid-way by stop: partial, at the stop's instant */
    (void)into_phase_3(&a, t3);
    eqi(gbp_async_tick(&a, t3 + 3u * TB), 0, "mid-dwell: nothing");
    gbp_async_stop(&a, t3 + 3u * TB + 5u);
    eqi(a.p3_dwell_cut, 1, "the dwell is cut");
    eqi(gbp_async_tick(&a, t3 + 3u * TB + 6u), GBP_ASYNC_TICK_PHASE | GBP_ASYNC_TICK_FINISHED | GBP_ASYNC_TICK_DEPTH_DONE, "to report");
    eqi(gbp_async_depth_done(&a, 1u, 0u, 0u, 0u, 0u, 0u, 0u), 0, "recorded");
    eqi(a.depths[0].partial, 1, "PARTIAL"); eqi((long long)a.depths[0].t_done, (long long)(t3 + 3u * TB + 5u), "done at the stop");
    eqi(a.p3_dwell_cut, 0, "the flag is cleared by the report");
    /* the session cap one second after the dwell's end: whole too */
    c.cap_session_s = 37u;                                        /* t_session_end = T0 + 37 s; the dwell ends at 36 s */
    gbp_async_init(&a, &c);
    gbp_async_start(&a, T0, SEED);
    gbp_async_skip(&a, t3 - 3u * TB);
    eqi(gbp_async_tick(&a, t3 - 2u * TB), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 2");
    gbp_async_skip(&a, t3 - TB);
    eqi(gbp_async_tick(&a, t3), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 3");
    eqi(a.target, a.plan.to, "the plan's `to` is the target in force");
    eqi(gbp_async_tick(&a, t_end + 100u), GBP_ASYNC_TICK_DEPTH_DONE, "the dwell ends at 36 s");
    eqi(gbp_async_tick(&a, T0 + 37u * TB), GBP_ASYNC_TICK_PHASE | GBP_ASYNC_TICK_FINISHED | GBP_ASYNC_TICK_DEPTH_DONE, "the session cap at 37 s");
    eqi(a.ph[3].ended, GBP_ASYNC_END_SESSION, "Phase 3 ended: session");
    eqi(gbp_async_depth_done(&a, 2u, 0u, 0u, 0u, 0u, 0u, 0u), 0, "recorded");
    eqi(a.depths[0].partial, 0, "WHOLE: it ended before the session cap");
    eqi((long long)a.depths[0].t_done, (long long)t_end, "done at the dwell's end, not at the cap");
}

/* Defect 2: a stick value other than LEFT/RIGHT is refused and counted apart, never
 * mapped as RIGHT. The value check follows the phase check and precedes the mute check. */
static void test_a_step_value_that_is_not_a_stick_is_refused(void)
{
    struct gbp_async a;
    uint64_t t;
    uint32_t seq;
    started(&a, SEED);
    eqi(gbp_async_step(&a, T0 + TB, 9u), 0, "out of phase first: refused as such");
    eqi(a.refused_step_phase, 1, "counted out of phase"); eqi(a.refused_step_value, 0, "not as a value");
    t = into_phase_2(&a, T0 + 20u * TB);
    eqi(a.target, a.plan.to, "the plan's `to` is the target in force");
    seq = a.plan.seq;
    eqi(gbp_async_step(&a, t - 1u, 7u), 0, "a bad value inside the mute is refused");
    eqi(a.refused_step_value, 1, "as a value"); eqi(a.refused_step_mute, 0, "not as a mute");
    eqi(gbp_async_step(&a, t, 2u), 0, "a value of 2 is refused");
    eqi(a.refused_step_value, 2, "counted");
    eqi(gbp_async_step(&a, t, 255u), 0, "a value of 255 is refused");
    eqi(a.refused_step_value, 3, "counted");
    eqi(a.target, 2560, "the target is untouched"); eqi(a.plan.seq, seq, "no plan was made");
    eqi(a.p2_steps, 0, "no step taken"); eqi(a.p2_steps_deeper, 0, "none deeper"); eqi(a.p2_steps_shallower, 0, "none shallower");
    eqi(a.refused_step_mute, 0, "no mute refusal"); eqi(a.refused_step_end, 0, "no end refusal");
    eqi(gbp_async_step(&a, t, GBP_ASYNC_RIGHT), 1, "RIGHT still steps");
    eqi(a.plan.to, 2432, "128 shallower (LEFT_DEEPER for this seed)"); eqi(a.plan.seq, seq + 1u, "one plan");
    eqi(a.target, a.plan.to, "and `to` is the target in force");
    eqi(gbp_async_step(&a, t + MUTE4, GBP_ASYNC_LEFT), 1, "LEFT still steps");
    eqi(a.plan.to, 2560, "128 deeper");
    eqi(a.refused_step_value, 3, "the valid steps count nothing");
}

/* Phase 0 -> Phase 3 at `t3` under `cfg`. */
static void into_phase_3_cfg(struct gbp_async *a, const struct gbp_async_cfg *cfg, uint64_t t3)
{
    gbp_async_init(a, cfg);
    gbp_async_start(a, T0, SEED);
    gbp_async_skip(a, t3 - 3u * TB);
    eqi(gbp_async_tick(a, t3 - 2u * TB), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 2");
    gbp_async_skip(a, t3 - TB);
    eqi(gbp_async_tick(a, t3), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 3");
    eqi(a->plan.to, a->cfg.p3_start, "its first depth"); eqi(a->target, a->plan.to, "`to` is the target in force");
}

/* Phase 3 under a monotone model: a depth holds iff target >= hold_from. Runs dwells until
 * Phase 3 ends by itself, bounded at 64: a bisect depth must lie strictly inside the bracket
 * and no depth may be set twice in a row. Returns the number of dwells. */
static uint32_t descend(struct gbp_async *a, uint64_t *t, uint32_t hold_from)
{
    uint32_t n = 0, prev = 0;
    int r = 1;
    while (r == 1 && n < 64u) {
        const uint32_t cur = a->p3_cur;
        if (a->p3_cur_kind == GBP_ASYNC_DEPTH_CONFIRM) {
            eqi(cur, a->p3_lo, "the confirm hold is at the highest failing depth");
        } else {
            if (n) eqi(cur != prev, 1, "a depth is never re-set");
            if (a->p3_bisecting) eqi(cur > a->p3_lo && cur < a->p3_hi, 1, "a bisect depth lies strictly inside the bracket");
        }
        prev = cur;
        r = dwell(a, t, cur < hold_from ? 1u : 0u);
        n++;
    }
    eqi(r, 0, "Phase 3 ended by itself");
    return n;
}

/* Defect 3: p3_bisect_width 1 with an odd bracket (start 385: ... 161 holds, 129 fails)
 * closes at hi - lo = 1 without ever re-setting a depth; a width of 0 is a cfg fault; and
 * the shrink guard closes the bracket when the midpoint equals lo (width forced to 0
 * behind gbp_async_init's back: 159 fails against 160, the midpoint is 159 again). */
static void test_the_bisection_closes_an_odd_bracket(void)
{
    struct gbp_async a;
    struct gbp_async_cfg c = gbp_async_cfg_default;
    const uint64_t t3 = T0 + 30u * TB;
    uint64_t t;
    uint32_t k;
    c.p3_start = 385u;
    c.p3_bisect_width = 1u;
    into_phase_3_cfg(&a, &c, t3);
    eqi(a.cfg_faults, 0, "width 1 is in bounds");
    eqi(descend(&a, &t, 160u), 15, "385..161 hold (8), 129 fails, then 145 153 157 159 fail and 160 holds, then the hold at 159");
    eqi(a.p3_lo, 159, "lo 159"); eqi(a.p3_hi, 160, "hi 160"); eqi(a.p3_bracket_closed, 1, "closed at width 1");
    eqi(a.ph[3].ended, GBP_ASYNC_END_COMPLETE, "ended: complete"); eqi(gbp_async_finished(&a), 1, "finished");
    eqi(a.depths_n, 15, "14 depths and the hold");
    eqi(a.depths[14].target, 159, "the hold at 159"); eqi(a.depths[14].kind, GBP_ASYNC_DEPTH_CONFIRM, "CONFIRM");
    for (k = 0; k < 8u; k++) { eqi(a.depths[k].target, 385u - 32u * k, "the descent"); eqi(a.depths[k].kind, GBP_ASYNC_DEPTH_STEP, "STEP"); }
    eqi(a.depths[8].target, 129, "129"); eqi(a.depths[8].underruns, 1, "fails");
    eqi(a.depths[9].target, 145, "145"); eqi(a.depths[10].target, 153, "153"); eqi(a.depths[11].target, 157, "157");
    eqi(a.depths[12].target, 159, "159"); eqi(a.depths[12].underruns, 1, "fails");
    eqi(a.depths[13].target, 160, "160"); eqi(a.depths[13].underruns, 0, "holds"); eqi(a.depths[13].kind, GBP_ASYNC_DEPTH_BISECT, "BISECT");
    eqi(a.depths[13].partial, 0, "whole");
    /* the other outcome of the last odd bracket: 160 fails against 161 */
    into_phase_3_cfg(&a, &c, t3);
    eqi(descend(&a, &t, 161u), 15, "the same 14 dwells, 160 failing, then the hold at 160");
    eqi(a.p3_lo, 160, "lo 160"); eqi(a.p3_hi, 161, "hi 161"); eqi(a.p3_bracket_closed, 1, "closed");
    /* width 0 is a cfg fault */
    c = gbp_async_cfg_default;
    c.p3_bisect_width = 0u;
    gbp_async_init(&a, &c);
    eqi(a.cfg_faults, 1, "width 0 is out of bounds"); eqi(a.cfg.p3_bisect_width, 2, "back to 2 (§V27.14)");
    /* the shrink guard, reached only past the bound: width 0 forced in after init */
    c = gbp_async_cfg_default;
    into_phase_3_cfg(&a, &c, t3);
    a.cfg.p3_bisect_width = 0u;
    eqi(descend(&a, &t, 160u), 15, "384..160 hold (8), 128 fails, then 144 152 156 158 159 fail: the midpoint of [159, 160] is 159; then the hold");
    eqi(a.p3_lo, 159, "lo 159"); eqi(a.p3_hi, 160, "hi 160");
    eqi(a.p3_bracket_closed, 1, "closed by the guard: the bracket cannot shrink");
    eqi(a.ph[3].ended, GBP_ASYNC_END_COMPLETE, "ended: complete"); eqi(a.depths_n, 15, "14 depths, 159 set once as a bisect, then the hold");
    eqi(a.depths[13].target, 159, "the last bisect depth is 159"); eqi(a.depths[13].underruns, 1, "failing");
    eqi(a.depths[14].kind, GBP_ASYNC_DEPTH_CONFIRM, "the hold"); eqi(a.depths[14].target, 159, "at 159");
}

/* Defect 5: after a cut, DEPTH_DONE rides every tick until depth_done() is called, then
 * the tick carries FINISHED alone and a second depth_done() is refused. */
static void test_depth_done_is_repeated_after_a_cut(void)
{
    struct gbp_async a;
    const uint64_t t3 = T0 + 30u * TB, tz = t3 + TB;
    (void)into_phase_3(&a, t3);
    gbp_async_skip(&a, tz);
    eqi(a.ph[3].ended, GBP_ASYNC_END_Z, "Phase 3 ended: z"); eqi(gbp_async_finished(&a), 1, "finished");
    eqi(gbp_async_tick(&a, tz + 1u), GBP_ASYNC_TICK_PHASE | GBP_ASYNC_TICK_FINISHED | GBP_ASYNC_TICK_DEPTH_DONE, "the first tick past the end");
    eqi(gbp_async_tick(&a, tz + 2u), GBP_ASYNC_TICK_FINISHED | GBP_ASYNC_TICK_DEPTH_DONE, "the second still carries DEPTH_DONE");
    eqi(gbp_async_tick(&a, tz + 3u), GBP_ASYNC_TICK_FINISHED | GBP_ASYNC_TICK_DEPTH_DONE, "and the third");
    eqi(a.phase, GBP_ASYNC_DONE, "DONE meanwhile");
    eqi(gbp_async_depth_done(&a, 1u, 0u, 0u, 0u, 0u, 0u, 0u), 0, "reported");
    eqi(a.depths_n, 1, "one depth"); eqi(a.depths[0].partial, 1, "partial"); eqi((long long)a.depths[0].t_done, (long long)tz, "at the Z");
    eqi(gbp_async_tick(&a, tz + 4u), GBP_ASYNC_TICK_FINISHED, "then FINISHED alone");
    eqi(gbp_async_depth_done(&a, 1u, 0u, 0u, 0u, 0u, 0u, 0u), 0, "a second report is refused");
    eqi(a.refused_depth_done, 1, "and counted"); eqi(a.depths_n, 1, "still one depth");
}

static void test_the_seconds(void)
{
    struct gbp_async a;
    uint64_t k, t_switch;
    uint32_t s;
    started(&a, SEED);
    gbp_async_block(&a, T0 - 1u, 7u);
    eqi((long long)a.blocks_before_origin, 1, "a block before the origin is counted apart");
    eqi(a.secs_used, 0, "and opens nothing");
    gbp_async_second_counters(&a, T0 + TB / 2u, 5u, 0u);         /* the baseline */
    eqi(a.sec_underruns[0], 0, "the first totals are the baseline");
    /* 2.4375 s (block 9 984 exactly): MUTE 18 = 0.5625 s ends at 3.0 -- mute [2.4375, 3.0], settling [3.0, 5.0) */
    t_switch = T0 + 2u * TB + TB * 7u / 16u;
    for (k = 0; k < 4096u * 6u; k++) {
        const uint64_t t = T0 + k * TB / 4096u;                  /* block k lands in second k / 4096 */
        if (t == t_switch) eqi(gbp_async_switch(&a, t), 1, "the switch at 2.5 s");
        gbp_async_block(&a, t, 2000u + (uint32_t)(k / 4096u));
        if (k == 4096u + 800u) gbp_async_second_counters(&a, t, 7u, 1u);
        if (k == 4096u + 2800u) gbp_async_second_counters(&a, t, 7u, 1u);
        if (k == 4u * 4096u + 2000u) gbp_async_second_counters(&a, t, 8u, 1u);
        if (k == 5u * 4096u + 10u) gbp_async_second_counters(&a, t, 2u, 1u);
    }
    eqi(a.secs_used, 6, "six seconds opened");
    for (s = 0; s < 6u; s++) {
        eqi(a.sec_count[s], 4096, "4096 blocks in the second");
        eqi(gbp_async_fill_mean(&a, s), 2000u + s, "the second's mean fill");
        eqi(a.sec_fill_sum[s], (2000u + s) * 4096u, "its sum");
    }
    eqi(a.sec_target[0], 512, "target before the switch"); eqi(a.sec_target[2], 512, "second 2 opened before the switch");
    eqi(a.sec_target[3], 2048, "second 3 carries the new target"); eqi(a.sec_target[5], 2048, "and so on");
    eqi(a.sec_phase[2], 0, "Phase 0 at second 2's start"); eqi(a.sec_phase[3], 1, "Phase 1 at second 3's start");
    eqi(a.sec_mute[1], 0, "no mute at 1"); eqi(a.sec_mute[2], 1, "mute at 2"); eqi(a.sec_mute[3], 1, "mute at 3 (the closed end, 3.0)");
    eqi(a.sec_mute[4], 0, "no mute at 4");
    eqi(a.sec_settling[2], 0, "not settling at 2"); eqi(a.sec_settling[3], 1, "settling at 3"); eqi(a.sec_settling[4], 1, "settling at 4");
    eqi(a.sec_settling[5], 0, "settled at 5 (the half-open end, 5.0)");
    eqi(a.sec_underruns[1], 2, "the delta lands in second 1"); eqi(a.sec_overflow_ev[1], 1, "overflow too");
    eqi(a.sec_underruns[4], 1, "and in second 4"); eqi(a.sec_underruns[2], 0, "nothing in between");
    eqi(a.counter_faults, 1, "a total going backwards is a fault"); eqi(a.sec_underruns[5], 0, "and bins nothing");
    /* a switch at 2.25 s mutes only second 2; a step mute of 4 chunks at 7.0 s marks 7 only */
    started(&a, SEED);
    eqi(gbp_async_switch(&a, T0 + 2u * TB + TB / 4u), 1, "a switch at 2.25 s");
    eqi(a.sec_mute[2], 1, "mute at 2"); eqi(a.sec_mute[3], 0, "not at 3: the mute ends at 2.75");
    eqi(a.sec_settling[2], 1, "settling from 2.75"); eqi(a.sec_settling[3], 1, "through 3"); eqi(a.sec_settling[4], 1, "to 4.75");
    eqi(a.sec_settling[5], 0, "not 5");
    /* the store's end */
    started(&a, SEED);
    gbp_async_block(&a, T0 + 727u * TB, 1u);
    eqi(a.sec_count[727], 1, "second 727 is the last binned");
    gbp_async_block(&a, T0 + 728u * TB, 1u);
    eqi(a.sec_overflow, 1, "second 728 is counted as overflow");
    eqi(a.secs_used, 728, "the store is full");
}

static void test_the_session_cap_and_z(void)
{
    struct gbp_async a;
    struct gbp_async_cfg c = gbp_async_cfg_default;
    /* Phase 0 with the defaults: the session cap ends it */
    started(&a, SEED);
    eqi(gbp_async_tick(&a, T0 + 720u * TB - 1u), 0, "before the session cap: nothing");
    eqi(gbp_async_tick(&a, T0 + 720u * TB), GBP_ASYNC_TICK_PHASE | GBP_ASYNC_TICK_FINISHED, "the session cap in Phase 0");
    eqi(a.ph[0].ended, GBP_ASYNC_END_SESSION, "Phase 0 ended: session"); eqi(a.ph[1].started, 0, "Phase 1 never began");
    /* Phase 1 under a cap past the session's: the session cap wins with its own reason */
    c.cap_p1_s = 800u;
    gbp_async_init(&a, &c);
    gbp_async_start(&a, T0, SEED);
    eqi(gbp_async_switch(&a, T0 + 10u * TB), 1, "a switch");
    eqi(gbp_async_tick(&a, T0 + 720u * TB - 1u), 0, "before the session cap: nothing");
    eqi(gbp_async_tick(&a, T0 + 720u * TB), GBP_ASYNC_TICK_PHASE | GBP_ASYNC_TICK_FINISHED, "the session cap");
    eqi(a.ph[1].ended, GBP_ASYNC_END_SESSION, "Phase 1 ended: session");
    eqi((long long)a.ph[1].t_end, (long long)(T0 + 720u * TB), "at the cap");
    eqi(gbp_async_finished(&a), 1, "finished"); eqi(a.phase, GBP_ASYNC_DONE, "DONE");
    eqi(gbp_async_switch(&a, T0 + 721u * TB), 0, "nothing after");
    gbp_async_block(&a, T0 + 721u * TB, 3u);
    eqi(a.sec_count[721], 1, "blocks after the cap are still binned");
    /* Z as stop, with a pending switch */
    started(&a, SEED);
    eqi(gbp_async_switch(&a, T0 + 10u * TB), 1, "a switch");
    gbp_async_stop(&a, T0 + 12u * TB);
    eqi(a.ph[1].ended, GBP_ASYNC_END_Z, "Phase 1 ended: z"); eqi(gbp_async_finished(&a), 1, "finished");
    eqi(gbp_async_tick(&a, T0 + 13u * TB), GBP_ASYNC_TICK_PHASE | GBP_ASYNC_TICK_FINISHED, "the tick reports it");
    eqi(a.ph[2].started, 0, "Phase 2 never began");
    /* Z as skip in Phase 1 */
    started(&a, SEED);
    eqi(gbp_async_switch(&a, T0 + 10u * TB), 1, "a switch");
    gbp_async_skip(&a, T0 + 12u * TB);
    eqi(a.ph[1].ended, GBP_ASYNC_END_Z, "Phase 1 ended: z"); eqi(gbp_async_finished(&a), 0, "not finished");
    eqi(gbp_async_tick(&a, T0 + 13u * TB), GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE, "Phase 2 begins");
    /* Z as skip in Phase 3 finishes */
    (void)into_phase_3(&a, T0 + 30u * TB);
    gbp_async_skip(&a, T0 + 31u * TB);
    eqi(a.ph[3].ended, GBP_ASYNC_END_Z, "Phase 3 ended: z"); eqi(gbp_async_finished(&a), 1, "finished");
    eqi(gbp_async_tick(&a, T0 + 31u * TB + 1u), GBP_ASYNC_TICK_PHASE | GBP_ASYNC_TICK_FINISHED | GBP_ASYNC_TICK_DEPTH_DONE, "with the cut dwell to report");
    eqi(gbp_async_depth_done(&a, 1u, 0u, 0u, 0u, 0u, 0u, 0u), 0, "recorded");
    eqi(a.depths[0].partial, 1, "partial"); eqi((long long)a.depths[0].t_done, (long long)(T0 + 31u * TB), "at the Z");
    /* the names */
    eqi(strcmp(gbp_async_end_name(GBP_ASYNC_END_CAP), "cap") == 0, 1, "end name");
    eqi(strcmp(gbp_async_kind_name(GBP_ASYNC_KIND_NULL), "NULL") == 0, 1, "kind name");
    eqi(strcmp(gbp_async_answer_name(GBP_ASYNC_LESS), "LESS") == 0, 1, "answer name");
    eqi(strcmp(gbp_async_level_name(GBP_ASYNC_DEEP), "DEEP") == 0, 1, "level name");
    eqi(strcmp(gbp_async_dir_name(GBP_ASYNC_LEFT_SHALLOWER), "LEFT_SHALLOWER") == 0, 1, "dir name");
}

int main(void)
{
    test_the_generator_and_the_shape();
    test_the_pinned_vector();
    test_a_bad_configuration_is_replaced();
    test_phase_1_flow();
    test_phase_1_cap();
    test_phase_2();
    test_a_start_mute_covers_its_pause();
    test_phase_3_descent_without_an_underrun();
    test_phase_3_bisects_to_width_2_then_holds_the_failing_depth();
    test_the_confirm_hold_ends_at_its_first_underrun();
    test_phase_3_bisects_from_160();
    test_phase_3_caps_and_the_open_bracket();
    test_a_cap_crossed_by_the_tap_still_reports_the_cut_dwell();
    test_a_dwell_ended_before_the_cut_stays_whole();
    test_a_step_value_that_is_not_a_stick_is_refused();
    test_the_bisection_closes_an_odd_bracket();
    test_depth_done_is_repeated_after_a_cut();
    test_the_seconds();
    test_the_session_cap_and_z();
    printf("test_gbp_async: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
