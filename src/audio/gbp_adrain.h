/*
 * gbp_adrain — GBP-AUDIO-005's phase machine and its COVERAGE counter
 * (GitHub Issue #84; `HARDWARE_TESTS.md` §V19 and its two amendments).
 *
 * TERMINOLOGY, binding since §V19 AMENDMENT 1 A1, because the collision has
 * already cost this project premise errors:
 *
 *     DMA GRANULE   32 bytes   -- GBP_BLOCK_SIZE, the transport's alignment unit
 *     AUDIO BLOCK   4096 bytes -- one H-PWM sample (GBP-HW-313)
 *
 * "block" unqualified is never used here.
 *
 * WHY THIS IS A MODULE AND NOT POC CODE (CLAUDE.md §10). The phase order, the
 * per-second counter, the positive control and the N sweep all decide what the
 * run means, and all of them are testable with no device: they are arithmetic
 * over a tick and a count. The POC supplies ticks and blocks; this decides what
 * phase the run is in and which window a block belongs to. tests/unit/
 * test_gbp_adrain.c drives it with no hardware at all.
 *
 * COVERAGE IS NOT `failures` (§V19.2, and GBP-HW-316 is why). The existing probe
 * reported `failures=0` for two runs that had each lost ~68 AUDIO blocks:
 * `failures` counts DMA completions, not whether the blocks that should have
 * arrived did. They are separate fields here and are never added together.
 *
 * THE COUNTER IS PREALLOCATED (§V19 AMENDMENT 1 A6, CLAUDE.md §13): a fixed
 * array, one u32 per second, bumped in the drain path with no allocation, no
 * I/O and no filesystem call. Without it QUESTION D1 cannot be evaluated at all.
 *
 * WINDOW BOUNDARIES ARE IN TICKS (§V19 AMENDMENT 2 B2). One millisecond is
 * 4.096 AUDIO blocks, which is the whole of D1's margin, so a millisecond
 * boundary could hide all of it; one tick is 0.000101 AUDIO blocks.
 *
 * No floating point, no allocation, no blocking call.
 */
#ifndef OPENGBP_GBP_ADRAIN_H
#define OPENGBP_GBP_ADRAIN_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_ADRAIN_AUDIO_BLOCK   4096u
#define GBP_ADRAIN_DMA_GRANULE     32u
#define GBP_ADRAIN_RATE          4096u    /* AUDIO blocks per second, GBP-HW-301 */

/* §V19 AMENDMENT 1 A3's budget. PHASE B is load-bearing and does not shrink. */
#define GBP_ADRAIN_B_SECONDS       60u
#define GBP_ADRAIN_C_SECONDS       10u
#define GBP_ADRAIN_A_STEP_SECONDS   3u
#define GBP_ADRAIN_A_STEPS          3u

/* §V19.11 AMENDMENT 4 A4.5 and A4.7: operational bounds of the drain image,
 * never properties of the hardware. CONTROL1 cannot pass before
 * GBP_ADRAIN_ACCEPT_S after the service's capture start, which keeps every
 * start-up stall out of PHASE B; and it gives up GBP_ADRAIN_CONTROL1_BOUND_S
 * after the A press, because a second A press would select 512 Hz and is not
 * the recovery. */
#define GBP_ADRAIN_ACCEPT_S         5u
#define GBP_ADRAIN_CONTROL1_BOUND_S 10u

/* One u32 per second of PHASE B, plus room for C and A so one array serves the
 * whole run and nothing is allocated later. */
#define GBP_ADRAIN_MAX_SECONDS    128u

/* §V19 AMENDMENT 1 A1: every N is a legal multiple of the DMA granule. */
#define GBP_ADRAIN_N0            0x020u
#define GBP_ADRAIN_N1            0x100u
#define GBP_ADRAIN_N2            0x400u

enum gbp_adrain_phase {
    GBP_ADRAIN_PROMPT = 0,   /* "PRESS A TO START THE TONE" -- the Operator's one press */
    GBP_ADRAIN_CONTROL1,     /* positive control at the prompt: recoverable while he is there */
    GBP_ADRAIN_B,            /* baseline coverage, full AUDIO-block reads */
    GBP_ADRAIN_C,            /* one timed SD write, issued OUTSIDE the ISR */
    GBP_ADRAIN_CONTROL2,     /* the control the gate is anchored on (AMENDMENT 2 B3) */
    GBP_ADRAIN_A,            /* the short reads: the one new variable, and it goes LAST */
    GBP_ADRAIN_RECOVERY,     /* one control window at full reads after the sweep (A4.7) */
    GBP_ADRAIN_DONE,
    GBP_ADRAIN_VOID          /* PHASE A lost sync and full reads did not recover */
};

struct gbp_adrain {
    uint32_t tb_hz;
    enum gbp_adrain_phase phase;
    uint64_t t_phase;              /* tick at which the current phase began */
    uint64_t t_b;                  /* tick at which PHASE B began; D1's windows count from it */
    uint64_t t_accept;             /* CONTROL1 cannot pass before this tick (A4.5); 0 = no bound */
    uint64_t t_tone;               /* the A press, as the input path wrote it */

    /* THE COVERAGE COUNTER: one AUDIO-block count per second of the run. */
    uint32_t sec[GBP_ADRAIN_MAX_SECONDS];
    uint32_t secs_used;            /* highest second index touched, plus one */
    uint32_t sec_overflow;         /* blocks that fell past the array: counted, never dropped silently */

    /* Reported separately at every point, and never added together (§V19.2). */
    uint64_t blocks_in;            /* AUDIO blocks whose DMA completed and were counted */
    uint32_t failures;             /* DMA completions that did not happen: NOT coverage */

    /* PHASE A */
    uint32_t a_step;               /* 0..GBP_ADRAIN_A_STEPS-1 */
    uint8_t  control1_ok, control2_ok;
    uint8_t  sync_lost, recovered;
    uint8_t  control1_gave_up;     /* CONTROL1 reached its bound without a passing window */
    uint32_t control1_early;       /* windows that passed before t_accept, and so did not count */
};

/* Every N the sweep uses, in the frozen order (low to high). */
uint32_t gbp_adrain_n_for_step(uint32_t step);

/* The transport's own rule: a positive multiple of the DMA granule, at most one
 * AUDIO block (gbp_transport.c gbp_bulk_args_ok). */
int gbp_adrain_legal_n(uint32_t n);

/* §V19 AMENDMENT 2 B4, frozen: sample(N) = popcount(N bytes read) * 4096 / N. */
int32_t gbp_adrain_sample_from_short_read(const uint8_t *data, uint32_t n);

void gbp_adrain_init(struct gbp_adrain *d, uint32_t tb_hz);

/* The length to ask the transport for, in the current phase. */
uint32_t gbp_adrain_read_len(const struct gbp_adrain *d);

/* One AUDIO block completed its DMA at `tick`. Counted into the second that
 * contains that tick, measured from PHASE B's start (§V19 AMENDMENT 1 A6:
 * DMA-completion, not IRQ arrival). Before PHASE B it is counted in blocks_in
 * only. */
void gbp_adrain_block(struct gbp_adrain *d, uint64_t tick);

/* A DMA that did not complete. Distinct from coverage at every point. */
void gbp_adrain_failure(struct gbp_adrain *d);

/* Advance the phase machine. `now` is the transport's tick; `tone_ok` is the
 * positive control's answer where one is due. Returns the phase after stepping.
 *
 * In the TIMED phases (B, C, A) `tone_ok` is ignored and the call may be made
 * as often as the caller likes. In the CONTROL phases (CONTROL1, CONTROL2,
 * RECOVERY) the call IS the verdict of one control window, and must be made
 * once per window and never otherwise. */
enum gbp_adrain_phase gbp_adrain_step(struct gbp_adrain *d, uint64_t now, int tone_ok);

/* A4.5: CONTROL1 cannot pass before `t_accept`. */
void gbp_adrain_set_accept(struct gbp_adrain *d, uint64_t t_accept);

/* PHASE A's current step has run its GBP_ADRAIN_A_STEP_SECONDS: the caller
 * evaluates it by the gate's rule BEFORE stepping, because the sweep must stop
 * at the first SYNC-LOST (§V19.4). */
int gbp_adrain_a_step_due(const struct gbp_adrain *d, uint64_t now);

/* The phase's name, for the report and the screen. */
const char *gbp_adrain_phase_name(enum gbp_adrain_phase p);

/* The Operator pressed A at the prompt. */
void gbp_adrain_tone_started(struct gbp_adrain *d, uint64_t now);

/* A step of PHASE A lost sync: the sweep stops there and the run goes to
 * RECOVERY, whose one control window decides RECOVERS or NO-RECOVERY. */
void gbp_adrain_sync_lost(struct gbp_adrain *d, uint64_t now);

/* Seconds elapsed in PHASE B, for the report. */
uint32_t gbp_adrain_b_seconds(const struct gbp_adrain *d, uint64_t now);

/* The whole-run budget in seconds, so the Operator knows what he commits to. */
uint32_t gbp_adrain_budget_seconds(void);

#ifdef __cplusplus
}
#endif
#endif
