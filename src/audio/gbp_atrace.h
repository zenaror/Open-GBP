/*
 * gbp_atrace — Run A's read-only timing records (GitHub Issue #101; HARDWARE_TESTS §V23,
 * with §V23.8's confirmed readings).
 *
 * WHAT IT KEEPS, all in the console's 40.5 MHz timebase, all in storage the caller
 * preallocates, nothing allocated, nothing printed, nothing written until the caller
 * emits it AFTER the session and off the drain path (§V23.4, CLAUDE.md §13):
 *
 *   AUDIO    §V23.1: every decoded sample of C's window, as it left the decoder, and a
 *            u16 completion-tick delta to the previous one. A delta that does not fit
 *            is stored as 0xFFFF and its full tick goes to a side ring.
 *   VIDEO    §V23.7: every VIDEO completion of the session, as a u16 whose bit 15 flags
 *            a frame-start block and whose bits 0..14 are the delta. 0x7FFF saturates,
 *            with the full tick in a side ring. Every vblank lands there.
 *   CALLBACK every AI DMA callback: its entry tick and its duration (the ISR window).
 *   STEP     the chain's pump-slot steps §V23.8 (a) names -- produce, flush_queue,
 *            process -- with start, duration and the RECORDER'S OWN write time. A
 *            flush_queue is always kept; a produce or a process is kept when it lasts
 *            at least GBP_ATRACE_STEP_FLOOR ticks, and every call lands in a histogram.
 *   COST     §V23.8 (s): the recorder's other writes (the taps' per-block stores, the
 *            callback records, and the histogram write of a step not kept) are timed by
 *            the caller and accumulated per AI callback cycle, with the largest single
 *            one. Each timed interval includes the cost of measuring itself; the
 *            accumulation into the cycle, a few instructions after the second read of
 *            the clock, is the one part outside it.
 *
 * A full buffer is counted, never overflowed. The emitted file is big-endian, CRC-32
 * terminated, and tools/v23report.py turns it into the report tools/v23accept.py reads.
 * tests/unit/test_gbp_atrace.c exercises it with no hardware.
 */
#ifndef OPENGBP_GBP_ATRACE_H
#define OPENGBP_GBP_ATRACE_H

#include <stddef.h>
#include <stdint.h>

#define GBP_ATRACE_A_MAX       266240u   /* C's 64 s x 4096 decoded samples, and one second of margin */
#define GBP_ATRACE_V_MAX       294912u   /* the session's VIDEO completions: ~123 s at ~2390/s, past
                                            the 120 s safety cap, since the prompt has no deadline.
                                            The WHOLE session, not only C's window, and not waste:
                                            §V23.8 (f) asks whether the incomplete frames are
                                            confined to the AI span, which needs records outside
                                            it to compare against (§V23.10) */
#define GBP_ATRACE_A_SAT_MAX     1024u
#define GBP_ATRACE_V_SAT_MAX     8192u   /* every vblank, ~60/s, for the same 120 s */
#define GBP_ATRACE_CB_MAX        4096u   /* ~2050 AI callbacks in 64 s */
#define GBP_ATRACE_STEP_MAX     49152u   /* kept steps; the rest are counted and histogrammed */
#define GBP_ATRACE_CYCLES_MAX    4097u   /* index 0: before the first callback */
#define GBP_ATRACE_STEP_FLOOR     200u   /* 4.9 us: below it a produce or process is counted, not kept */
#define GBP_ATRACE_HIST_BINS       32u   /* log2 of the duration in ticks */

#define GBP_ATRACE_A_SAT       0xFFFFu
#define GBP_ATRACE_V_START     0x8000u
#define GBP_ATRACE_V_SAT       0x7FFFu

enum gbp_atrace_kind {
    GBP_ATRACE_PRODUCE = 1,
    GBP_ATRACE_FLUSH_QUEUE = 2,
    GBP_ATRACE_PROCESS = 3
};

struct gbp_atrace_sat { uint32_t index; uint64_t t; };
struct gbp_atrace_cb { uint64_t entry; uint32_t dur; uint32_t rec; };
struct gbp_atrace_step { uint32_t start_rel; uint32_t dur; uint16_t rec; uint8_t kind; };

struct gbp_atrace_storage {
    int16_t *a_decoded;                 /* GBP_ATRACE_A_MAX */
    uint16_t *a_delta;                  /* GBP_ATRACE_A_MAX */
    struct gbp_atrace_sat *a_sat;       /* GBP_ATRACE_A_SAT_MAX */
    uint16_t *v_rec;                    /* GBP_ATRACE_V_MAX */
    struct gbp_atrace_sat *v_sat;       /* GBP_ATRACE_V_SAT_MAX */
    struct gbp_atrace_cb *cb;           /* GBP_ATRACE_CB_MAX */
    struct gbp_atrace_step *step;       /* GBP_ATRACE_STEP_MAX */
    uint32_t *cycles;                   /* GBP_ATRACE_CYCLES_MAX */
};

struct gbp_atrace {
    struct gbp_atrace_storage s;
    uint32_t tb_hz;
    uint32_t a_n, a_sat_n, v_n, v_sat_n, step_n, cycles_n;
    volatile uint32_t cb_n;             /* written by the ISR */
    uint32_t a_dropped, a_sat_dropped, v_dropped, v_sat_dropped, cb_dropped, step_dropped;
    uint64_t a_first, a_last, v_first, v_last, step_base;
    uint32_t cost_max;                  /* the largest single non-step recorder write */
    uint32_t calls[4];                  /* every call, by kind */
    uint32_t hist[4][GBP_ATRACE_HIST_BINS];
    int step_armed;
};

void gbp_atrace_init(struct gbp_atrace *tr, const struct gbp_atrace_storage *s, uint32_t tb_hz);

/* §V23.1, from the AUDIO tap, in C's window only */
void gbp_atrace_audio(struct gbp_atrace *tr, int16_t decoded, uint64_t t_done);
/* §V23.7, from the VIDEO tap, the whole session */
void gbp_atrace_video(struct gbp_atrace *tr, int frame_start, uint64_t t_done);
/* the ISR: its entry and exit ticks; returns the record written, for its own write time */
struct gbp_atrace_cb *gbp_atrace_callback(struct gbp_atrace *tr, uint64_t entry, uint64_t exit_);
/* the pump slot: the chain step's start and end; the step base is the first step's start */
struct gbp_atrace_step *gbp_atrace_step(struct gbp_atrace *tr, enum gbp_atrace_kind kind, uint64_t start, uint64_t end);
/* the recorder's own write of a step, measured by the caller right after gbp_atrace_step:
 * kept, it is the step's rec; not kept (under the floor, or the buffer full), it goes to
 * the cycle's cost like every other recorder write */
void gbp_atrace_step_rec(struct gbp_atrace *tr, struct gbp_atrace_step *st, uint64_t end, uint64_t rec_end);
/* every other recorder write, timed by the caller, into the current AI callback cycle */
void gbp_atrace_cost(struct gbp_atrace *tr, uint32_t ticks);

/* The sidecar, streamed through `put` in pieces of at most `cap` bytes staged in `stage`;
 * returns the bytes emitted, or 0 when `put` failed. */
typedef int (*gbp_atrace_put)(void *ctx, const uint8_t *bytes, uint32_t n);
uint32_t gbp_atrace_emit(const struct gbp_atrace *tr, gbp_atrace_put put, void *ctx, uint8_t *stage, uint32_t cap);

#endif
