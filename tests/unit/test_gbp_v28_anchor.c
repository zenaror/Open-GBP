/*
 * tests/unit/test_gbp_v28_anchor.c — GitHub Issue #128/#129/#130, the Orchestrator's Amendment 1
 * on Issue #131's own freeze: `gbp_v28_anchor()` (src/audio/gbp_v28_ladder.h), the fix for 3b
 * holding AHEAD at 3a's own raw confirmed floor instead of the nearest perceptual-ladder rung at
 * or above it. Every floor value the Amendment names explicitly: exactly on a rung, one above it,
 * P3_MIN (well below every rung), above T704 (no rung reaches it), and no floor at all (3a never
 * held anything -- cut or a first depth that failed outright).
 */
#include <stdio.h>
#include "gbp_v28_ladder.h"

static int checks, failures;

static void eqi(long long got, long long want, const char *what)
{
    checks++;
    if (got != want) {
        failures++;
        printf("  FAIL: %s: got %lld, want %lld\n", what, got, want);
    }
}

static void check(int cond, const char *what)
{
    checks++;
    if (!cond) {
        failures++;
        printf("  FAIL: %s\n", what);
    }
}

static void expect(uint32_t floor_native, int has_floor, uint32_t want_target,
                   enum gbp_v28_anchor_source want_source, const char *what)
{
    const struct gbp_v28_anchor a = gbp_v28_anchor(floor_native, has_floor);
    char buf[160];
    snprintf(buf, sizeof buf, "%s: target", what);
    eqi(a.target, want_target, buf);
    snprintf(buf, sizeof buf, "%s: source", what);
    eqi(a.source, want_source, buf);
}

/* ---- exactly on a rung: the ladder's own five perceptual TARGETs, each fed back as the floor --
 * every one must anchor to ITSELF, by construction (the smallest rung >= itself is itself). ---- */
static void test_exactly_on_a_rung(void)
{
    expect(GBP_V28_T256, 1, GBP_V28_T256, GBP_V28_ANCHOR_RULE, "floor exactly T256");
    expect(GBP_V28_T320, 1, GBP_V28_T320, GBP_V28_ANCHOR_RULE, "floor exactly T320");
    expect(GBP_V28_T448, 1, GBP_V28_T448, GBP_V28_ANCHOR_RULE, "floor exactly T448");
    expect(GBP_V28_T576, 1, GBP_V28_T576, GBP_V28_ANCHOR_RULE, "floor exactly T576");
    expect(GBP_V28_T704, 1, GBP_V28_T704, GBP_V28_ANCHOR_RULE, "floor exactly T704");
}

/* ---- one native sample above a rung: must anchor to the NEXT rung up, never stay at the one
 * just below (the anchor is "at or above", never a floor read as "close enough"). ---- */
static void test_one_above_a_rung(void)
{
    expect(GBP_V28_T256 + 1u, 1, GBP_V28_T320, GBP_V28_ANCHOR_RULE, "one above T256");
    expect(GBP_V28_T320 + 1u, 1, GBP_V28_T448, GBP_V28_ANCHOR_RULE, "one above T320");
    expect(GBP_V28_T448 + 1u, 1, GBP_V28_T576, GBP_V28_ANCHOR_RULE, "one above T448");
    expect(GBP_V28_T576 + 1u, 1, GBP_V28_T704, GBP_V28_ANCHOR_RULE, "one above T576");
}

/* ---- P3_MIN, 2048 native: 3a's own deepest possible floor, well below every perceptual rung
 * (T256 = 4096) -- must anchor to T256, the ladder's own lowest rung, per #128 §3's own rule read
 * literally ("at or above"), not left unanchored. This is the exact defect scenario this whole fix
 * closes: gbp_v28_3b_start() used to receive P3_MIN directly. ---- */
static void test_p3_min_anchors_to_the_lowest_rung(void)
{
    expect(GBP_V28_P3_MIN, 1, GBP_V28_T256, GBP_V28_ANCHOR_RULE, "floor at P3_MIN (2048)");
    check(GBP_V28_P3_MIN < GBP_V28_T256, "test setup: P3_MIN really is below every ladder rung");
}

/* ---- above T704: no rung reaches it -- GBP_V28_ANCHOR_NONE, target meaningless (0), 3b does not
 * hold at all (main.c's own job, not this function's -- see the wiring test). ---- */
static void test_above_t704_has_no_anchor(void)
{
    expect(GBP_V28_T704 + 1u, 1, 0u, GBP_V28_ANCHOR_NONE, "one above T704");
    expect(GBP_V28_T704 * 2u, 1, 0u, GBP_V28_ANCHOR_NONE, "well above T704");
}

/* ---- no floor at all: 3a's own `have_hold` false (cut before any depth held, or the very first
 * depth already failed) -- the frozen default, T256, regardless of what floor_native happens to
 * hold (must be ignored when has_floor is 0). ---- */
static void test_no_floor_uses_the_frozen_default(void)
{
    expect(0u, 0, GBP_V28_T256, GBP_V28_ANCHOR_DEFAULT, "no floor, floor_native=0");
    expect(999999u, 0, GBP_V28_T256, GBP_V28_ANCHOR_DEFAULT, "no floor, floor_native garbage-nonzero");
}

static void test_source_names_are_distinct(void)
{
    check(gbp_v28_anchor_source_name(GBP_V28_ANCHOR_RULE)[0] != '?', "RULE has a real name");
    check(gbp_v28_anchor_source_name(GBP_V28_ANCHOR_DEFAULT)[0] != '?', "DEFAULT has a real name");
    check(gbp_v28_anchor_source_name(GBP_V28_ANCHOR_NONE)[0] != '?', "NONE has a real name");
}

int main(void)
{
    test_exactly_on_a_rung();
    test_one_above_a_rung();
    test_p3_min_anchors_to_the_lowest_rung();
    test_above_t704_has_no_anchor();
    test_no_floor_uses_the_frozen_default();
    test_source_names_are_distinct();
    printf("test_gbp_v28_anchor: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
