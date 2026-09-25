/*
 * gbp_async — see gbp_async.h.
 */
#include "gbp_async.h"

#include <string.h>

const struct gbp_async_cfg gbp_async_cfg_default = {
    2048u, 512u, 384u,          /* deep, shallow, floor */
    18u, 4u,                    /* mute_chunks (18: §V27.15, two chunks of margin), step_mute_chunks */
    384u, 3584u, 128u,          /* p2_lo, p2_hi, p2_step */
    384u, 32u, 6u, 2u, 128u,    /* p3_start, p3_step, p3_dwell_s, p3_bisect_width (2: §V27.14), p3_min */
    60u,                        /* p3_confirm_s (§V27.14) */
    300u, 240u, 180u, 720u,     /* cap_p1_s, cap_p2_s, cap_p3_s, cap_session_s */
    12u, 6u,                    /* real, null */
    2u,                         /* settling_s */
    40500000u                   /* tb_hz */
};

uint32_t gbp_async_xorshift32(uint32_t x)
{
    x ^= (uint32_t)(x << 13);
    x ^= (uint32_t)(x >> 17);
    x ^= (uint32_t)(x << 5);
    return x;
}

/* ---- small helpers ---------------------------------------------------------- */

static uint64_t chunk_ticks(const struct gbp_async *a)
{
    return (uint64_t)a->cfg.tb_hz * GBP_ASYNC_CHUNK / GBP_ASYNC_RATE;
}

static uint64_t sec_of(const struct gbp_async *a, uint64_t t)
{
    return (t - a->t_origin) / (uint64_t)a->cfg.tb_hz;               /* t >= t_origin by the callers */
}

static uint32_t p2_nvals(const struct gbp_async *a)
{
    return (a->cfg.p2_hi - a->cfg.p2_lo) / a->cfg.p2_step + 1u;
}

static void draw_p2(struct gbp_async *a, uint32_t k)
{
    if (k >= GBP_ASYNC_P2_CAP) return;
    a->rng = gbp_async_xorshift32(a->rng);
    a->p2_start[k] = a->cfg.p2_lo + (a->rng % p2_nvals(a)) * a->cfg.p2_step;
    a->rng = gbp_async_xorshift32(a->rng);
    a->p2_dir[k] = (uint8_t)((a->rng & 1u) ? GBP_ASYNC_LEFT_SHALLOWER : GBP_ASYNC_LEFT_DEEPER);
}

/* Marks the seconds a plan silences and the seconds after it that settle. */
static void mark_seconds(struct gbp_async *a, uint64_t t, uint32_t mute_chunks)
{
    const uint64_t t_mute_end = t + (uint64_t)mute_chunks * chunk_ticks(a);
    uint64_t s, s_end;
    if (mute_chunks) {
        s_end = sec_of(a, t_mute_end);
        for (s = sec_of(a, t); s <= s_end && s < (uint64_t)GBP_ASYNC_SECONDS; s++) a->sec_mute[s] = 1u;
    }
    if (a->cfg.settling_s) {
        const uint64_t t_settle_end = t_mute_end + (uint64_t)a->cfg.settling_s * a->cfg.tb_hz;
        s_end = sec_of(a, t_settle_end - 1u);
        for (s = sec_of(a, t_mute_end); s <= s_end && s < (uint64_t)GBP_ASYNC_SECONDS; s++) a->sec_settling[s] = 1u;
    }
    a->t_mute_end = t_mute_end;
}

/* The plan the POC applies: the pause/discard arithmetic of §V27.13. */
static void make_plan(struct gbp_async *a, uint64_t t, uint8_t kind, uint32_t to, uint32_t mute_chunks)
{
    const uint32_t from = a->target;
    uint32_t need;
    a->plan.seq++;
    a->plan.kind = kind;
    a->plan.mech = kind == GBP_ASYNC_KIND_DEPTH ? GBP_ASYNC_MECH_UNMUTED :
                   kind == GBP_ASYNC_KIND_STEP ? GBP_ASYNC_MECH_HELD : GBP_ASYNC_MECH_ROTATE;
    a->plan.from = from;
    a->plan.to = to;
    a->plan.pause_chunks = (to > from) ? (to - from + GBP_ASYNC_CHUNK - 1u) / GBP_ASYNC_CHUNK : 0u;
    /* a mute outlasts what its mechanism must do under it (gbp_atrans.h): ROTATE the climb and four
     * rotations before the last silent hand-off, pause + 4; HELD the climb, pause + 1. Only a Phase 2
     * START can need more than cfg's (a switch: 12 + 4 = 16 <= 18; a STEP: 1 + 1 <= 4); a START
     * deepening far holds silence for pause + 4, else the level would be reached by the DUP's slew over
     * half a minute while the rows said it was in force (caught by review before the commit). */
    need = a->plan.mech == GBP_ASYNC_MECH_ROTATE ? a->plan.pause_chunks + 4u :
           a->plan.mech == GBP_ASYNC_MECH_HELD ? a->plan.pause_chunks + 1u : 0u;
    if (mute_chunks && need > mute_chunks) mute_chunks = need;
    a->plan.mute_chunks = mute_chunks;
    a->plan.discard = (to < from) ? from - to : 0u;
    a->plan.t = t;
    a->target = to;
    mark_seconds(a, t, mute_chunks);
}

static void end_phase(struct gbp_async *a, uint8_t reason, uint64_t t_end)
{
    struct gbp_async_phase_rec *r;
    if (a->phase > GBP_ASYNC_P3) return;
    r = &a->ph[a->phase];
    if (!r->started || r->ended) return;
    r->ended = reason;
    r->t_end = t_end;
    if (a->phase == GBP_ASYNC_P3) {
        if (a->p3_dwell_active) {                                     /* the dwell is cut before its end: still reportable, partial */
            a->p3_depth_pending = 1u;
            a->p3_dwell_active = 0u;
            a->p3_dwell_cut = 1u;
        }                                                             /* a dwell already ended stays whole: p3_dwell_cut untouched */
        a->finished = 1u;
    }
}

static void begin_phase(struct gbp_async *a, enum gbp_async_phase p, uint64_t t)
{
    a->phase = p;
    a->ph[p].started = 1u;
    a->ph[p].t_start = t;
}

static uint32_t phase_cap_s(const struct gbp_async *a)
{
    switch (a->phase) {
    case GBP_ASYNC_P1: return a->cfg.cap_p1_s;
    case GBP_ASYNC_P2: return a->cfg.cap_p2_s;
    case GBP_ASYNC_P3: return a->cfg.cap_p3_s;
    default: return 0u;
    }
}

/* Opens the seconds up to `now` and applies the caps. Begins nothing (that is the
 * tick's job, because a beginning carries a plan). */
static int advance(struct gbp_async *a, uint64_t now)
{
    uint64_t s;
    if (!a->started || now < a->t_origin) return 0;
    s = sec_of(a, now);
    while ((uint64_t)a->secs_used <= s && a->secs_used < GBP_ASYNC_SECONDS) {
        a->sec_target[a->secs_used] = (uint16_t)(a->target > 0xFFFFu ? 0xFFFFu : a->target);
        a->sec_phase[a->secs_used] = (uint8_t)(a->phase > GBP_ASYNC_P3 ? GBP_ASYNC_P3 : a->phase);
        a->secs_used++;
    }
    if (a->finished) return 1;
    /* the running phase's own cap, then the session's: whichever instant came first */
    if (a->phase >= GBP_ASYNC_P1 && a->phase <= GBP_ASYNC_P3 && a->ph[a->phase].started && !a->ph[a->phase].ended) {
        const uint64_t t_cap = a->ph[a->phase].t_start + (uint64_t)phase_cap_s(a) * a->cfg.tb_hz;
        if (now >= t_cap && t_cap <= a->t_session_end) end_phase(a, GBP_ASYNC_END_CAP, t_cap);
    }
    if (now >= a->t_session_end) {
        end_phase(a, GBP_ASYNC_END_SESSION, a->t_session_end);
        a->finished = 1u;
    }
    return 1;
}

/* ---- init / start ------------------------------------------------------------ */

void gbp_async_init(struct gbp_async *a, const struct gbp_async_cfg *cfg)
{
    const struct gbp_async_cfg *d = &gbp_async_cfg_default;
    if (!a) return;
    memset(a, 0, sizeof *a);
    a->cfg = cfg ? *cfg : *d;
    if (a->cfg.tb_hz == 0u) { a->cfg.tb_hz = d->tb_hz; a->cfg_faults++; }
    if (a->cfg.real == 0u || a->cfg.real + a->cfg.null > GBP_ASYNC_SWITCH_CAP) {
        a->cfg.real = d->real; a->cfg.null = d->null; a->cfg_faults++;
    }
    if (a->cfg.p2_step == 0u || a->cfg.p2_hi < a->cfg.p2_lo) {
        a->cfg.p2_lo = d->p2_lo; a->cfg.p2_hi = d->p2_hi; a->cfg.p2_step = d->p2_step; a->cfg_faults++;
    }
    if (a->cfg.p3_step == 0u || a->cfg.p3_start < a->cfg.p3_min) {
        a->cfg.p3_start = d->p3_start; a->cfg.p3_step = d->p3_step; a->cfg.p3_min = d->p3_min; a->cfg_faults++;
    }
    if (a->cfg.deep == a->cfg.shallow) { a->cfg.deep = d->deep; a->cfg.shallow = d->shallow; a->cfg_faults++; }
    if (a->cfg.p3_bisect_width == 0u) { a->cfg.p3_bisect_width = d->p3_bisect_width; a->cfg_faults++; }   /* >= 1: a bracket of 1 must close */
    a->phase = GBP_ASYNC_P0;
    a->n_sched = a->cfg.real + a->cfg.null;
}

void gbp_async_start(struct gbp_async *a, uint64_t t_origin, uint32_t seed)
{
    uint32_t i, k, x;
    if (!a || a->started) return;
    a->started = 1u;
    a->t_origin = t_origin;
    a->t_session_end = t_origin + (uint64_t)a->cfg.cap_session_s * a->cfg.tb_hz;
    begin_phase(a, GBP_ASYNC_P0, t_origin);
    /* the seed: draw 1, the initial level */
    a->seed = seed;
    x = seed ? seed : 1u;
    x = gbp_async_xorshift32(x);
    a->initial = (uint8_t)((x & 1u) ? GBP_ASYNC_SHALLOW : GBP_ASYNC_DEEP);
    a->level = a->initial;
    a->target = (a->level == GBP_ASYNC_DEEP) ? a->cfg.deep : a->cfg.shallow;
    /* the schedule: real REALs then null NULLs, Fisher-Yates from the top */
    for (i = 0; i < a->n_sched; i++)
        a->schedule[i] = (uint8_t)(i < a->cfg.real ? GBP_ASYNC_KIND_REAL : GBP_ASYNC_KIND_NULL);
    for (i = a->n_sched - 1u; i >= 1u; i--) {
        uint32_t j;
        uint8_t tmp;
        x = gbp_async_xorshift32(x);
        j = x % (i + 1u);
        tmp = a->schedule[i]; a->schedule[i] = a->schedule[j]; a->schedule[j] = tmp;
    }
    if (a->schedule[0] == GBP_ASYNC_KIND_NULL) {                       /* the first switch is REAL */
        for (k = 1; k < a->n_sched; k++) {
            if (a->schedule[k] == GBP_ASYNC_KIND_REAL) {
                a->schedule[k] = GBP_ASYNC_KIND_NULL;
                a->schedule[0] = GBP_ASYNC_KIND_REAL;
                break;
            }
        }
    }
    /* three starts, then three directions */
    a->p2_seeded = 3u;
    for (k = 0; k < 3u; k++) {
        x = gbp_async_xorshift32(x);
        a->p2_start[k] = a->cfg.p2_lo + (x % p2_nvals(a)) * a->cfg.p2_step;
    }
    for (k = 0; k < 3u; k++) {
        x = gbp_async_xorshift32(x);
        a->p2_dir[k] = (uint8_t)((x & 1u) ? GBP_ASYNC_LEFT_SHALLOWER : GBP_ASYNC_LEFT_DEEPER);
    }
    a->rng = x;
}

/* ---- the tick ------------------------------------------------------------------- */

static void set_depth(struct gbp_async *a, uint64_t now, uint32_t target, uint8_t kind)
{
    make_plan(a, now, GBP_ASYNC_KIND_DEPTH, target, 0u);
    a->p3_cur = target;
    a->p3_cur_kind = kind;
    a->p3_dwell_active = 1u;
    a->p3_depth_pending = 0u;
    a->t_dwell_end = now + (uint64_t)(kind == GBP_ASYNC_DEPTH_CONFIRM ? a->cfg.p3_confirm_s : a->cfg.p3_dwell_s) * a->cfg.tb_hz;
}

int gbp_async_tick(struct gbp_async *a, uint64_t now)
{
    int flags = 0;
    if (!a || !a->started) return 0;
    if (!advance(a, now)) return 0;
    if (a->finished) {
        flags |= GBP_ASYNC_TICK_FINISHED;
        if (a->phase != GBP_ASYNC_DONE) {                             /* the first tick past the end */
            flags |= GBP_ASYNC_TICK_PHASE;
            a->phase = GBP_ASYNC_DONE;
        }
        if (a->p3_depth_pending) flags |= GBP_ASYNC_TICK_DEPTH_DONE;  /* on every tick until depth_done() clears it */
        return flags;
    }
    if (gbp_async_mute_active(a, now)) return flags;                 /* nothing begins under a mute */
    switch (a->phase) {
    case GBP_ASYNC_P1:
        if (a->ph[GBP_ASYNC_P1].ended) {                              /* Phase 2: its first START */
            begin_phase(a, GBP_ASYNC_P2, now);
            a->p2_index = 0u;
            a->p2_steps = 0u;
            make_plan(a, now, GBP_ASYNC_KIND_START, a->p2_start[0], a->cfg.mute_chunks);
            flags |= GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE;
        }
        break;
    case GBP_ASYNC_P2:
        if (a->ph[GBP_ASYNC_P2].ended) {                              /* Phase 3: its first depth */
            begin_phase(a, GBP_ASYNC_P3, now);
            set_depth(a, now, a->cfg.p3_start, GBP_ASYNC_DEPTH_STEP);
            flags |= GBP_ASYNC_TICK_PLAN | GBP_ASYNC_TICK_PHASE;
        }
        break;
    case GBP_ASYNC_P3:
        if (a->p3_dwell_active && now >= a->t_dwell_end) {
            a->p3_dwell_active = 0u;
            a->p3_depth_pending = 1u;
        }
        if (a->p3_depth_pending) flags |= GBP_ASYNC_TICK_DEPTH_DONE;
        break;
    default:
        break;
    }
    return flags;
}

/* ---- Phase 1 --------------------------------------------------------------------- */

int gbp_async_switch(struct gbp_async *a, uint64_t now)
{
    uint8_t kind;
    uint32_t to;
    struct gbp_async_switch *s;
    if (!a || !a->started || !advance(a, now) || a->finished) return 0;
    if (a->phase == GBP_ASYNC_P0) {
        end_phase(a, GBP_ASYNC_END_COMPLETE, now);
        begin_phase(a, GBP_ASYNC_P1, now);
    }
    if (a->phase != GBP_ASYNC_P1 || a->ph[GBP_ASYNC_P1].ended) { a->refused_switch_phase++; return 0; }
    if (a->pending) { a->refused_switch_unanswered++; return 0; }
    if (gbp_async_mute_active(a, now)) { a->refused_switch_mute++; return 0; }
    if (a->switches >= a->n_sched) { a->refused_switch_exhausted++; return 0; }
    kind = a->schedule[a->switches];
    if (kind == GBP_ASYNC_KIND_REAL) {
        a->level = (uint8_t)(a->level == GBP_ASYNC_DEEP ? GBP_ASYNC_SHALLOW : GBP_ASYNC_DEEP);
    }
    to = (a->level == GBP_ASYNC_DEEP) ? a->cfg.deep : a->cfg.shallow;
    s = &a->sw[a->switches];
    s->seq = a->switches + 1u;
    s->kind = kind;
    s->from = a->target;
    s->to = to;
    s->t = now;
    s->answer = GBP_ASYNC_ANSWER_NONE;
    s->t_answer = 0u;
    make_plan(a, now, kind, to, a->cfg.mute_chunks);
    s->discard = a->plan.discard;
    a->switches++;
    a->pending = 1u;
    return 1;
}

int gbp_async_answer(struct gbp_async *a, uint64_t now, uint8_t answer)
{
    struct gbp_async_switch *s;
    if (!a || !a->started || !advance(a, now)) return 0;
    if (a->phase != GBP_ASYNC_P1 || a->ph[GBP_ASYNC_P1].ended || !a->pending ||
        answer < GBP_ASYNC_MORE || answer > GBP_ASYNC_SAME) {
        a->refused_answer++;
        return 0;
    }
    s = &a->sw[a->switches - 1u];
    s->answer = answer;
    s->t_answer = now;
    a->pending = 0u;
    a->answered++;
    if (a->answered >= a->n_sched) end_phase(a, GBP_ASYNC_END_COMPLETE, now);
    return 1;
}

/* ---- Phase 2 --------------------------------------------------------------------- */

int gbp_async_step(struct gbp_async *a, uint64_t now, uint8_t stick)
{
    int deeper;
    uint32_t to;
    if (!a || !a->started || !advance(a, now) || a->finished) return 0;
    if (a->phase != GBP_ASYNC_P2 || a->ph[GBP_ASYNC_P2].ended) { a->refused_step_phase++; return 0; }
    if (stick != GBP_ASYNC_LEFT && stick != GBP_ASYNC_RIGHT) { a->refused_step_value++; return 0; }   /* not a stick: never mapped */
    if (gbp_async_mute_active(a, now)) { a->refused_step_mute++; return 0; }
    deeper = (stick == GBP_ASYNC_LEFT) == (a->p2_dir[a->p2_index] == GBP_ASYNC_LEFT_DEEPER);
    if (deeper) {
        if (a->target >= a->cfg.p2_hi) { a->refused_step_end++; return 0; }
        to = a->target + a->cfg.p2_step;
        a->p2_steps_deeper++;
    } else {
        if (a->target <= a->cfg.p2_lo) { a->refused_step_end++; return 0; }
        to = a->target - a->cfg.p2_step;
        a->p2_steps_shallower++;
    }
    a->p2_steps++;
    make_plan(a, now, GBP_ASYNC_KIND_STEP, to, a->cfg.step_mute_chunks);
    return 1;
}

int gbp_async_confirm(struct gbp_async *a, uint64_t now)
{
    struct gbp_async_setting *s;
    if (!a || !a->started || !advance(a, now) || a->finished) return 0;
    if (a->phase != GBP_ASYNC_P2 || a->ph[GBP_ASYNC_P2].ended || gbp_async_mute_active(a, now) ||
        a->settings_n >= GBP_ASYNC_P2_CAP) {
        a->refused_confirm++;
        return 0;
    }
    s = &a->settings[a->settings_n];
    s->seq = a->settings_n + 1u;
    s->start = a->p2_start[a->p2_index];
    s->direction = a->p2_dir[a->p2_index];
    s->steps = a->p2_steps;
    s->target = a->target;
    s->t = now;
    a->settings_n++;
    if (a->settings_n >= GBP_ASYNC_P2_CAP) {                            /* the store is full: the phase is over */
        end_phase(a, GBP_ASYNC_END_COMPLETE, now);
        return 0;
    }
    a->p2_index = a->settings_n;
    if (a->p2_index >= a->p2_seeded) draw_p2(a, a->p2_index);
    a->p2_steps = 0u;
    make_plan(a, now, GBP_ASYNC_KIND_START, a->p2_start[a->p2_index], a->cfg.mute_chunks);
    return 1;
}

/* ---- Phase 3 --------------------------------------------------------------------- */

/* the bracket is closed: the hold at the highest failing depth (§V27.14 §4), or the end */
static int confirm_or_end(struct gbp_async *a)
{
    a->p3_bracket_closed = 1u;
    if (a->cfg.p3_confirm_s) {
        a->p3_confirming = 1u;
        set_depth(a, a->t_dwell_end, a->p3_lo, GBP_ASYNC_DEPTH_CONFIRM);
        return 1;
    }
    end_phase(a, GBP_ASYNC_END_COMPLETE, a->t_dwell_end);
    return 0;
}

int gbp_async_depth_done(struct gbp_async *a, uint32_t fill_mean_x16, uint32_t underruns,
                         uint32_t overflow, uint32_t dup, uint32_t drop, uint32_t lost, uint32_t starved)
{
    /* §V27.14 §1: a depth FAILS when the correction stopped holding the level over its dwell -- the
     * DUP could not fire and the ring could not give a wanted chunk (the POC passes gbp_aplay's ring_gated)
     * -- not when the audio failed (that underrun comes ~47 s
     * later, longer than the dwell) */
    const int failing = dup == 0u && starved > 0u;
    const uint32_t cur = a ? a->p3_cur : 0u;
    uint32_t next;
    uint8_t over, partial;
    if (!a || !a->p3_depth_pending) { if (a) a->refused_depth_done++; return 0; }
    a->p3_depth_pending = 0u;
    over = (uint8_t)((a->phase != GBP_ASYNC_P3 || a->ph[GBP_ASYNC_P3].ended) ? 1u : 0u);   /* the phase is gone: nothing follows */
    partial = a->p3_dwell_cut;                                         /* the dwell itself was cut before its end */
    a->p3_dwell_cut = 0u;
    if (a->depths_n < GBP_ASYNC_DEPTH_CAP) {
        struct gbp_async_depth *d = &a->depths[a->depths_n++];
        d->target = cur;
        d->kind = a->p3_cur_kind;
        d->partial = partial;
        d->fill_mean_x16 = fill_mean_x16;
        d->underruns = underruns; d->overflow = overflow;
        d->dup = dup; d->drop = drop; d->lost = lost;
        d->starved = starved;
        d->t_set = a->plan.t;
        d->t_done = partial ? a->ph[GBP_ASYNC_P3].t_end : a->t_dwell_end;   /* a whole dwell ends at its own end */
    } else {
        a->depths_overflow++;
    }
    if (over) return 0;                                                /* cut by a cap, the session or Z: nothing follows */
    if (a->p3_cur_kind == GBP_ASYNC_DEPTH_CONFIRM) {                    /* §V27.14 §4: the hold is the last word */
        end_phase(a, GBP_ASYNC_END_COMPLETE, a->t_dwell_end);
        return 0;
    }
    if (!a->p3_bisecting) {
        if (failing) {
            if (!a->p3_have_hold) {                                     /* the first depth fails: open bracket */
                end_phase(a, GBP_ASYNC_END_COMPLETE, a->t_dwell_end);
                return 0;
            }
            a->p3_lo = cur;
            a->p3_hi = a->p3_last_hold;
            a->p3_bisecting = 1u;
        } else {
            a->p3_have_hold = 1u;
            a->p3_last_hold = cur;
            if (cur <= a->cfg.p3_min) {                                 /* the floor holds: nothing to bracket */
                end_phase(a, GBP_ASYNC_END_COMPLETE, a->t_dwell_end);
                return 0;
            }
            next = (cur - a->cfg.p3_min < a->cfg.p3_step) ? a->cfg.p3_min : cur - a->cfg.p3_step;
            set_depth(a, a->t_dwell_end, next, GBP_ASYNC_DEPTH_STEP);
            return 1;
        }
    } else {
        if (failing) a->p3_lo = cur; else a->p3_hi = cur;
    }
    if (a->p3_hi - a->p3_lo <= a->cfg.p3_bisect_width) return confirm_or_end(a);
    next = (a->p3_lo + a->p3_hi) / 2u;
    if (next == a->p3_lo || next == a->p3_hi) return confirm_or_end(a);   /* the bracket cannot shrink: the same depth would be re-set every dwell */
    set_depth(a, a->t_dwell_end, next, GBP_ASYNC_DEPTH_BISECT);
    return 1;
}

/* ---- Z ------------------------------------------------------------------------------ */

void gbp_async_skip(struct gbp_async *a, uint64_t now)
{
    if (!a || !a->started || !advance(a, now) || a->finished) return;
    if (a->phase == GBP_ASYNC_P0) {
        end_phase(a, GBP_ASYNC_END_COMPLETE, now);
        begin_phase(a, GBP_ASYNC_P1, now);
    }
    end_phase(a, GBP_ASYNC_END_Z, now);
}

void gbp_async_stop(struct gbp_async *a, uint64_t now)
{
    if (!a || !a->started || !advance(a, now) || a->finished) return;
    end_phase(a, GBP_ASYNC_END_Z, now);
    a->finished = 1u;
}

/* ---- the per-second rows ----------------------------------------------------------- */

void gbp_async_block(struct gbp_async *a, uint64_t t_done, uint32_t fill_before_push)
{
    uint64_t s;
    if (!a || !a->started) return;
    if (t_done < a->t_origin) { a->blocks_before_origin++; return; }
    (void)advance(a, t_done);
    a->blocks_in++;
    s = sec_of(a, t_done);
    if (s >= (uint64_t)GBP_ASYNC_SECONDS) { a->sec_overflow++; return; }
    a->sec_count[s]++;
    a->sec_fill_sum[s] += fill_before_push;
}

void gbp_async_second_counters(struct gbp_async *a, uint64_t now, uint32_t underruns_total,
                               uint32_t overflow_total)
{
    uint64_t s;
    if (!a || !a->started || now < a->t_origin) return;
    (void)advance(a, now);
    if (!a->have_counters) {                                           /* the baseline: no delta yet */
        a->have_counters = 1u;
        a->last_underruns = underruns_total;
        a->last_overflow = overflow_total;
        return;
    }
    s = sec_of(a, now);
    if (underruns_total < a->last_underruns || overflow_total < a->last_overflow) {
        a->counter_faults++;                                           /* a total went backwards: counted, not binned */
    } else if (s < (uint64_t)GBP_ASYNC_SECONDS) {
        a->sec_underruns[s] += underruns_total - a->last_underruns;
        a->sec_overflow_ev[s] += overflow_total - a->last_overflow;
    }
    /* §V27.14 §4: the confirmation hold ends at its first underrun -- the inevitability OBSERVED */
    if (a->p3_dwell_active && a->p3_cur_kind == GBP_ASYNC_DEPTH_CONFIRM && underruns_total > a->last_underruns &&
        now < a->t_dwell_end) {
        a->t_dwell_end = now;
        a->p3_confirm_observed = 1u;
    }
    a->last_underruns = underruns_total;
    a->last_overflow = overflow_total;
}

/* ---- queries ------------------------------------------------------------------------- */

int gbp_async_mute_active(const struct gbp_async *a, uint64_t now)
{
    return (a && a->plan.seq && now < a->t_mute_end) ? 1 : 0;
}

int gbp_async_finished(const struct gbp_async *a)
{
    return (a && a->finished) ? 1 : 0;
}

uint32_t gbp_async_fill_mean(const struct gbp_async *a, uint32_t s)
{
    if (!a || s >= GBP_ASYNC_SECONDS || a->sec_count[s] == 0u) return 0u;
    return a->sec_fill_sum[s] / a->sec_count[s];
}

const char *gbp_async_depth_kind_name(uint8_t kind)
{
    return kind == GBP_ASYNC_DEPTH_BISECT ? "BISECT" : kind == GBP_ASYNC_DEPTH_CONFIRM ? "CONFIRM" : "STEP";
}

const char *gbp_async_kind_name(uint8_t kind)
{
    switch (kind) {
    case GBP_ASYNC_KIND_REAL: return "REAL";
    case GBP_ASYNC_KIND_NULL: return "NULL";
    case GBP_ASYNC_KIND_START: return "START";
    case GBP_ASYNC_KIND_STEP: return "STEP";
    case GBP_ASYNC_KIND_DEPTH: return "DEPTH";
    default: return "?";
    }
}

const char *gbp_async_end_name(uint8_t end)
{
    switch (end) {
    case GBP_ASYNC_END_NONE: return "null";
    case GBP_ASYNC_END_COMPLETE: return "complete";
    case GBP_ASYNC_END_CAP: return "cap";
    case GBP_ASYNC_END_SESSION: return "session";
    case GBP_ASYNC_END_Z: return "z";
    default: return "?";
    }
}

const char *gbp_async_answer_name(uint8_t answer)
{
    switch (answer) {
    case GBP_ASYNC_ANSWER_NONE: return "null";
    case GBP_ASYNC_MORE: return "MORE";
    case GBP_ASYNC_LESS: return "LESS";
    case GBP_ASYNC_SAME: return "SAME";
    default: return "?";
    }
}

const char *gbp_async_level_name(uint8_t level)
{
    return level == GBP_ASYNC_DEEP ? "DEEP" : level == GBP_ASYNC_SHALLOW ? "SHALLOW" : "?";
}

const char *gbp_async_dir_name(uint8_t dir)
{
    return dir == GBP_ASYNC_LEFT_DEEPER ? "LEFT_DEEPER" : dir == GBP_ASYNC_LEFT_SHALLOWER ? "LEFT_SHALLOWER" : "?";
}
