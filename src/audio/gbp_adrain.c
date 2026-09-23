/*
 * gbp_adrain — see gbp_adrain.h.
 */
#include "gbp_adrain.h"

/* popcount of a byte, as gbp_adec.c builds it: no libgcc call, no table lookup
 * the compiler could turn into one. */
#define B2(n)  n,     (n) + 1,     (n) + 1,     (n) + 2
#define B4(n)  B2(n), B2((n) + 1), B2((n) + 1), B2((n) + 2)
#define B6(n)  B4(n), B4((n) + 1), B4((n) + 1), B4((n) + 2)
static const uint8_t POPCOUNT8[256] = { B6(0), B6(1), B6(1), B6(2) };

uint32_t gbp_adrain_n_for_step(uint32_t step)
{
    switch (step) {
    case 0u: return GBP_ADRAIN_N0;
    case 1u: return GBP_ADRAIN_N1;
    case 2u: return GBP_ADRAIN_N2;
    default: return GBP_ADRAIN_AUDIO_BLOCK;
    }
}

int gbp_adrain_legal_n(uint32_t n)
{
    return (n != 0u && n <= GBP_ADRAIN_AUDIO_BLOCK
            && (n & (GBP_ADRAIN_DMA_GRANULE - 1u)) == 0u) ? 1 : 0;
}

int32_t gbp_adrain_sample_from_short_read(const uint8_t *data, uint32_t n)
{
    uint32_t i, pc = 0u;
    if (!data || !gbp_adrain_legal_n(n))
        return -1;
    for (i = 0u; i < n; i++)
        pc += POPCOUNT8[data[i]];
    /* AMENDMENT 2 B4: exact on flat AUDIO blocks, never at an edge (§V18.5).
     * The division is exact because N divides 4096 for every legal N that is a
     * power of two; for any other legal N it truncates, which is stated rather
     * than hidden -- the PERIOD does not depend on it. */
    return (int32_t)(pc * (GBP_ADRAIN_AUDIO_BLOCK / n));
}

void gbp_adrain_init(struct gbp_adrain *d, uint32_t tb_hz)
{
    uint32_t i;
    if (!d) return;
    d->tb_hz = tb_hz;
    d->phase = GBP_ADRAIN_PROMPT;
    d->t_phase = 0u;
    d->t_b = 0u;
    d->t_accept = 0u;
    d->t_tone = 0u;
    for (i = 0u; i < GBP_ADRAIN_MAX_SECONDS; i++)
        d->sec[i] = 0u;
    d->secs_used = 0u;
    d->sec_overflow = 0u;
    d->blocks_in = 0u;
    d->failures = 0u;
    d->a_step = 0u;
    d->control1_ok = 0u;
    d->control2_ok = 0u;
    d->sync_lost = 0u;
    d->recovered = 0u;
    d->control1_gave_up = 0u;
    d->control1_early = 0u;
}

uint32_t gbp_adrain_read_len(const struct gbp_adrain *d)
{
    if (!d) return GBP_ADRAIN_AUDIO_BLOCK;
    /* Only PHASE A reads short. Every other phase, including both controls, is a
     * full AUDIO block -- the controls are anchored on the known-good length. */
    if (d->phase == GBP_ADRAIN_A)
        return gbp_adrain_n_for_step(d->a_step);
    return GBP_ADRAIN_AUDIO_BLOCK;
}

void gbp_adrain_block(struct gbp_adrain *d, uint64_t tick)
{
    if (!d) return;
    d->blocks_in++;
    if (d->phase == GBP_ADRAIN_PROMPT || d->phase == GBP_ADRAIN_CONTROL1)
        return;                                   /* before PHASE B: total only */
    if (d->tb_hz == 0u || tick < d->t_b)
        return;
    {
        uint64_t s = (tick - d->t_b) / (uint64_t)d->tb_hz;
        if (s >= (uint64_t)GBP_ADRAIN_MAX_SECONDS) {
            d->sec_overflow++;                    /* counted, never dropped silently */
            return;
        }
        d->sec[(uint32_t)s]++;
        if ((uint32_t)s + 1u > d->secs_used)
            d->secs_used = (uint32_t)s + 1u;
    }
}

void gbp_adrain_failure(struct gbp_adrain *d)
{
    if (d) d->failures++;                          /* NOT coverage (§V19.2) */
}

void gbp_adrain_tone_started(struct gbp_adrain *d, uint64_t now)
{
    if (!d || d->phase != GBP_ADRAIN_PROMPT) return;
    d->phase = GBP_ADRAIN_CONTROL1;
    d->t_phase = now;
    d->t_tone = now;
}

void gbp_adrain_set_accept(struct gbp_adrain *d, uint64_t t_accept)
{
    if (d) d->t_accept = t_accept;
}

void gbp_adrain_sync_lost(struct gbp_adrain *d, uint64_t now)
{
    if (!d || d->phase != GBP_ADRAIN_A) return;
    d->sync_lost = 1u;
    d->phase = GBP_ADRAIN_RECOVERY;              /* the sweep stops at the first SYNC-LOST */
    d->t_phase = now;
}

int gbp_adrain_a_step_due(const struct gbp_adrain *d, uint64_t now)
{
    if (!d || d->phase != GBP_ADRAIN_A || d->tb_hz == 0u) return 0;
    return (now >= d->t_phase && now - d->t_phase >= (uint64_t)GBP_ADRAIN_A_STEP_SECONDS * d->tb_hz) ? 1 : 0;
}

const char *gbp_adrain_phase_name(enum gbp_adrain_phase p)
{
    switch (p) {
    case GBP_ADRAIN_PROMPT: return "prompt";
    case GBP_ADRAIN_CONTROL1: return "control1";
    case GBP_ADRAIN_B: return "B";
    case GBP_ADRAIN_C: return "C";
    case GBP_ADRAIN_CONTROL2: return "control2";
    case GBP_ADRAIN_A: return "A";
    case GBP_ADRAIN_RECOVERY: return "recovery";
    case GBP_ADRAIN_DONE: return "done";
    case GBP_ADRAIN_VOID: return "void";
    default: return "?";
    }
}

static uint64_t elapsed(const struct gbp_adrain *d, uint64_t now)
{
    return (now >= d->t_phase) ? (now - d->t_phase) : 0u;
}

enum gbp_adrain_phase gbp_adrain_step(struct gbp_adrain *d, uint64_t now, int tone_ok)
{
    uint64_t e;
    if (!d) return GBP_ADRAIN_VOID;
    if (d->phase == GBP_ADRAIN_DONE || d->phase == GBP_ADRAIN_VOID || d->tb_hz == 0u)
        return d->phase;
    e = elapsed(d, now);
    switch (d->phase) {
    case GBP_ADRAIN_PROMPT:
        break;                                     /* waits for the Operator's A */
    case GBP_ADRAIN_CONTROL1:
        /* Recoverable while he is still standing there: a failure here does not
         * void the run, it just says the tone is not established yet. */
        if (tone_ok && now < d->t_accept) {
            /* A4.5: a passing window before the bound does not count -- PHASE B
             * may not open while a start-up stall could still follow it. */
            d->control1_early++;
        } else if (tone_ok) {
            d->control1_ok = 1u;
            d->phase = GBP_ADRAIN_B;
            d->t_phase = now;
            d->t_b = now;                          /* D1's windows count from here */
        } else if (now >= d->t_tone &&
                   now - d->t_tone >= (uint64_t)GBP_ADRAIN_CONTROL1_BOUND_S * d->tb_hz) {
            /* A4.7: bounded. The run ends for a power cycle and a retry; a
             * second A press would select 512 Hz and is NOT the recovery. */
            d->control1_ok = 0u;
            d->control1_gave_up = 1u;
            d->phase = GBP_ADRAIN_DONE;
            d->t_phase = now;
        }
        break;
    case GBP_ADRAIN_B:
        if (e >= (uint64_t)GBP_ADRAIN_B_SECONDS * d->tb_hz) {
            d->phase = GBP_ADRAIN_C;
            d->t_phase = now;
        }
        break;
    case GBP_ADRAIN_C:
        if (e >= (uint64_t)GBP_ADRAIN_C_SECONDS * d->tb_hz) {
            d->phase = GBP_ADRAIN_CONTROL2;
            d->t_phase = now;
        }
        break;
    case GBP_ADRAIN_CONTROL2:
        /* AMENDMENT 2 B3: this is the one the gate is anchored on. If it fails,
         * PHASE A is not entered at all and reports INCONCLUSIVE -- never
         * SYNC-LOST. PHASE B and PHASE C stay valid and are still reported. */
        d->control2_ok = tone_ok ? 1u : 0u;
        d->phase = tone_ok ? GBP_ADRAIN_A : GBP_ADRAIN_DONE;
        d->t_phase = now;
        break;
    case GBP_ADRAIN_A:
        if (e >= (uint64_t)GBP_ADRAIN_A_STEP_SECONDS * d->tb_hz) {
            d->a_step++;
            d->t_phase = now;
            if (d->a_step >= GBP_ADRAIN_A_STEPS)
                d->phase = GBP_ADRAIN_RECOVERY;    /* the sweep is over: one full-read window */
        }
        break;
    case GBP_ADRAIN_RECOVERY:
        /* A4.7: the one control window at full reads after the sweep, or after
         * the first SYNC-LOST. Its verdict is RECOVERS or NO-RECOVERY. */
        d->recovered = tone_ok ? 1u : 0u;
        d->phase = tone_ok ? GBP_ADRAIN_DONE : GBP_ADRAIN_VOID;
        d->t_phase = now;
        break;
    default:
        break;
    }
    return d->phase;
}

uint32_t gbp_adrain_b_seconds(const struct gbp_adrain *d, uint64_t now)
{
    if (!d || d->tb_hz == 0u || d->t_b == 0u || now < d->t_b)
        return 0u;
    return (uint32_t)((now - d->t_b) / (uint64_t)d->tb_hz);
}

uint32_t gbp_adrain_budget_seconds(void)
{
    return GBP_ADRAIN_B_SECONDS + GBP_ADRAIN_C_SECONDS
           + GBP_ADRAIN_A_STEP_SECONDS * GBP_ADRAIN_A_STEPS;
}
