/*
 * tests/unit/test_gbp_aresamp2.c — GitHub Issue #126, Round B: gbp_aresamp2_init/_push tested
 * DIRECTLY, not only indirectly through gbp_aplay2_produce (review round, #126: the frozen
 * gbp_aresamp path has its own direct unit tests, tests/unit/test_gbp_adec.c's
 * test_resampler_is_exact/test_resampler_dc_and_identity; this engine had none before this file).
 *
 * gbp_aresamp2 is the SAME push-driven polyphase accumulator as the frozen gbp_aresamp, at the
 * opposite ratio direction: L = 125 < M = 256 (net DOWNSAMPLE, 65 536 -> 32 000 Hz), so at most one
 * output emerges per push instead of several. Because of that, phase 0's row is NOT a delta (it is
 * a genuine anti-aliasing lowpass kernel, unlike the frozen upsampler's phase 0): pushing a single
 * impulse does not reproduce it exactly on any later output. What IS true regardless of the
 * filter's shape, and is what these tests check: the accumulator's whole-period arithmetic (a
 * period of GBP_ARESAMP2_M pushes returns acc to exactly 0 and has produced exactly
 * GBP_ARESAMP2_L outputs, since gcd(125,256) == 1 makes 256 pushes one full period visiting every
 * phase once), a settled DC input reproduces exactly (every phase's row sums to exactly 32768,
 * proved separately by tests/host/test_v126_resampler2.py and tests/host/test_resampler_tables.py),
 * and a single impulse's dominant response lobe carries the SAME SIGN as the impulse -- the
 * property an int32 coefficient table or an accumulator/history indexing bug could flip or scramble.
 * The exact impulse-response sequence below was independently traced from the committed table with
 * a plain reimplementation of the push algorithm (q15_round2's rounding rule) in Python, not copied
 * from gbp_aresamp2.c; it exercises the RUNTIME's history/accumulator indexing, which the table's
 * own correctness checks do not.
 */
#include <stdio.h>
#include "gbp_aresamp2.h"
#include "gbp_aresamp2_coef.h"       /* GBP_ARESAMP2_L/M/TAPS */

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

/* GBP_ARESAMP2_M (256) pushes of silence: one full accumulator period, gcd(125,256) == 1, so the
 * accumulator visits every one of the 125 phases exactly once and returns to 0 -- proved a whole
 * number of times over (100 periods), mirroring test_gbp_adec.c's test_resampler_is_exact. */
static void test_resampler_is_exact(void)
{
    struct gbp_aresamp2 r;
    int16_t out[GBP_ARESAMP2_MAX_OUT];
    uint32_t i, total = 0u;
    gbp_aresamp2_init(&r);
    for (i = 0; i < GBP_ARESAMP2_M * 100u; i++)
        total += gbp_aresamp2_push(&r, 0, out);
    eqi((long long)total, (long long)GBP_ARESAMP2_L * 100, "256 inputs -> exactly 125 outputs, a whole number of times");
    eqi((long long)r.acc, 0, "the accumulator is back at phase 0 after a whole period");
    eqi((long long)r.in_count, (long long)GBP_ARESAMP2_M * 100, "in_count");
    eqi((long long)r.out_count, (long long)GBP_ARESAMP2_L * 100, "out_count");
}

/* After the 16-sample history fills and one settling period passes, a constant input reproduces
 * EXACTLY at every phase (every row sums to exactly 32768, GBP-HW-351) -- the property a Q15
 * rounding or coefficient-sum bug in THIS runtime (not just in the table) would break. */
static void test_resampler_dc(void)
{
    struct gbp_aresamp2 r;
    int16_t out[GBP_ARESAMP2_MAX_OUT];
    uint32_t i, k, n;
    int ok = 1, saw_any = 0;
    gbp_aresamp2_init(&r);
    for (i = 0; i < 300u; i++) {
        n = gbp_aresamp2_push(&r, 1000, out);
        if (i >= GBP_ARESAMP2_TAPS)
            for (k = 0; k < n; k++) {
                saw_any = 1;
                if (out[k] != 1000) ok = 0;
            }
    }
    eqi(saw_any, 1, "the settled window produced at least one output to check");
    eqi(ok, 1, "a settled constant input reproduces exactly at every phase");
}

/* A single impulse (10000) amid zeros: the exact nonzero output sequence, independently traced
 * from the committed table by a plain Python reimplementation of this push algorithm (not copied
 * from gbp_aresamp2.c). Not a delta response (this filter's phase 0 is a lowpass kernel, not an
 * identity, at this ratio) -- but it is EXACT and DETERMINISTIC, and its dominant lobe (4024) has
 * the SAME SIGN as the impulse, the property a coefficient sign-flip or a history/phase indexing
 * bug in the runtime would break. */
static void test_resampler_impulse_response(void)
{
    struct gbp_aresamp2 r;
    int16_t out[GBP_ARESAMP2_MAX_OUT];
    static const int32_t want[] = { -49, 202, -575, 1890, 4024, -820, 295, -87 };
    uint32_t i, n, k, seen = 0u;
    int mismatch = 0;
    int32_t peak = 0, peak_abs = 0;
    gbp_aresamp2_init(&r);
    for (i = 0; i < 40u; i++) {
        n = gbp_aresamp2_push(&r, (int16_t)(i == 20u ? 10000 : 0), out);
        for (k = 0; k < n; k++) {
            if (out[k] != 0) {
                if (seen >= sizeof want / sizeof want[0] || out[k] != want[seen]) mismatch = 1;
                {
                    const int32_t mag = out[k] > 0 ? out[k] : -out[k];
                    if (mag > peak_abs) { peak_abs = mag; peak = out[k]; }
                }
                seen++;
            }
        }
    }
    eqi((long long)seen, (long long)(sizeof want / sizeof want[0]), "the impulse response has exactly the traced number of nonzero taps");
    eqi(mismatch, 0, "every nonzero output matches the independently traced sequence exactly");
    eqi(peak > 0, 1, "the dominant lobe carries the same sign as the (positive) impulse");
}

int main(void)
{
    test_resampler_is_exact();
    test_resampler_dc();
    test_resampler_impulse_response();
    fprintf(stderr, "test_gbp_aresamp2: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
