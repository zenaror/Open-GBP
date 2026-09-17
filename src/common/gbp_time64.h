/*
 * gbp_time64.h — the 64-bit time base GBP-VIDEO-002 requires, and the
 * wrap-safe arithmetic every persistent timestamp of that experiment uses.
 *
 * Why 64 bits (docs/research/HARDWARE_TESTS.md "GBP-VIDEO-002" §4): the
 * GameCube time base runs at 40.5 MHz, so 2^32 ticks = 106.049 s — SHORTER
 * than the 120.000 s scientific target. A 32-bit tick counter wraps inside a
 * single run and would silently corrupt ordering. The hard safety budget
 * itself, 7 290 000 000 ticks, does not fit in 32 bits either.
 *
 * The mechanism is the standard PowerPC three-instruction retry: read TBU,
 * read TBL, read TBU again, repeat while the two TBU reads differ. A carry
 * from TBL into TBU between the two TBU reads is detected and the read is
 * repeated, so the pair is never taken from either side of the carry.
 *
 * WHICH IMPLEMENTATION THE PROBE USES, recorded here rather than left open:
 * libogc2's `gettime()` (external/libogc2/libogc/timesupp.c, commit
 * ca03fb75) is EXACTLY that loop —
 *     1: mftbu %0 ; mftb %1 ; mftbu %2 ; cmpw %0,%2 ; bne 1b
 * — so the real backend calls it (src/platform/hsp_backend.c, transport
 * operation `ticks64`) instead of adding a second hand-written copy. The
 * composition and retry RULE lives here as a pure function so the host can
 * test it, including across the low-word wrap 0xFFFFFFFF -> 0x00000000, and
 * `gbp_time64_read()` runs the same loop over any pair of readers (the mock's
 * scripted counter in tests, the SPRs on hardware).
 *
 * Short per-operation waits (T_DMA, T_DELIVERY, T_NEXT_CAUSE) keep the
 * transport's existing 32-bit `ticks` operation: a wrap-safe unsigned
 * difference over a sub-second interval is already correct and physically
 * exercised. The contract is explicit — u32 deltas for short waits, u64 for
 * every recorded timestamp — and nothing here changes it.
 */
#ifndef OPENGBP_GBP_TIME64_H
#define OPENGBP_GBP_TIME64_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The nominal GameCube time base: 40.5 MHz (bus clock 162 MHz / 4). Used to
 * derive the design's tick constants; the probe always takes the real value
 * from its configuration, never from this constant. */
#define GBP_TIME64_NOMINAL_HZ 40500000u

/* Which special-purpose register a reader is asked for. */
#define GBP_TIME64_TBU 0
#define GBP_TIME64_TBL 1

/* Maximum retries gbp_time64_read() performs before giving up; a genuine
 * carry needs one retry, so anything beyond this is a broken reader. */
#define GBP_TIME64_MAX_RETRIES 8u

typedef uint32_t (*gbp_time64_spr_fn)(void *ctx, int which);

/* The composition rule of one attempt (pure): valid only when the two TBU
 * reads agree, in which case *out = (tbu1 << 32) | tbl. Returns 1 when the
 * sample is valid, 0 when the caller must retry. *out is left untouched on 0. */
int gbp_time64_compose(uint32_t tbu1, uint32_t tbl, uint32_t tbu2, uint64_t *out);

/* The retry loop over any reader (the same rule the backend's gettime()
 * executes in hardware). `retries`, when non-NULL, receives the number of
 * repeated attempts. Returns the composed value; on a reader that never
 * settles it returns the last attempt's composition after
 * GBP_TIME64_MAX_RETRIES and reports the retries, never spinning forever. */
uint64_t gbp_time64_read(gbp_time64_spr_fn f, void *ctx, unsigned *retries);

/* Halves and composition. */
uint64_t gbp_time64_make(uint32_t hi, uint32_t lo);
uint32_t gbp_time64_hi(uint64_t v);
uint32_t gbp_time64_lo(uint64_t v);

/* Monotonic difference: later - earlier, or 0 when later precedes earlier.
 * The time base is monotonic, so a negative difference is a defect, not a
 * wrap; it is reported as 0 rather than as a huge unsigned value. */
uint64_t gbp_time64_delta(uint64_t earlier, uint64_t later);

/* 1 when `now` is at or past `start + span` (no overflow: span is bounded by
 * the caller's budget, which is far below 2^64). */
int gbp_time64_reached(uint64_t start, uint64_t span, uint64_t now);

/* Conversions (tb_hz == 0 gives 0). */
uint64_t gbp_time64_from_seconds(uint32_t tb_hz, uint32_t seconds);
uint64_t gbp_time64_from_ms(uint32_t tb_hz, uint32_t ms);
uint32_t gbp_time64_to_ms(uint32_t tb_hz, uint64_t ticks);
/* Whole seconds and the milliseconds part, for reporting without floats. */
uint32_t gbp_time64_seconds(uint32_t tb_hz, uint64_t ticks);
uint32_t gbp_time64_millis_part(uint32_t tb_hz, uint64_t ticks);

#ifdef __cplusplus
}
#endif
#endif
