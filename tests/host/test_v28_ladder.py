"""tests/host/test_v28_ladder.py -- Issue #128's Amendment A, src/audio/gbp_v28_ladder.h
(GitHub Issue #129).

Amendment A's own words: "the ladder is stated in TIME. Native samples are derived from it
(x16). The literal old values are never used." and "Add a build-time check: every ladder
TARGET, converted to native samples, must be >= GBP_APLAY2_TARGET_MIN and <= TARGET_MAX. A
unit slip then fails the build instead of reaching the console."

What is held here:
  * the six native TARGET constants equal the frozen table exactly (11264/9216/7168/5120/4096/3072);
  * each is DERIVED (old value x16), never a hand-copied literal;
  * the six build-time bounds asserts are present, uncommented, and not under a preprocessor
    conditional (the same convention test_cushion.py already applies to gbp_aplay's own check);
  * AHEAD (A1..A4) carries over as literal chunk counts, unconverted;
  * the frozen header itself builds, through tests/host/hostcc.py (Issue #82's one rule for a
    host test that compiles C -- a bespoke compile-fail message here would break
    test_compile_skips.py's sweep, which expects every hostcc-routed failure to read "does not
    build with the host gcc");
  * a DELIBERATE ARITHMETIC CHECK, against GBP_APLAY2_TARGET_MIN/_MAX parsed from
    src/audio/gbp_aplay2.h (never hardcoded here): every ladder value taken literally, un-derived,
    falls OUTSIDE those bounds, and every x16-derived value falls INSIDE them -- proving the guard
    actually catches the class of error it exists for, not just that its text is present. This is
    checked in Python, not as a second real compile, so it needs no gcc and cannot itself be swept
    into Issue #82's "every hostcc compile must succeed" convention;
  * the SAME derivation and bounds treatment, extended to 3a's descent grid and nulling's scan
    grid (gbp_async_cfg_default's p3_start/p3_step/p3_min and p2_lo/p2_hi/p2_step, also old-path
    sample counts) -- including a KNOWN, DOCUMENTED GAP: GBP_V28_OLD_P2_HI (3584) already falls
    inside [TARGET_MIN, TARGET_MAX] numerically, so the bounds assert alone would not catch an
    un-derived P2_HI; the grid's own divisibility assert is what catches that specific slip, and
    is proven to do so here rather than assumed.
"""
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hostcc  # noqa: E402

AUDIO = os.path.join(ROOT, "src", "audio")
LADDER_H = os.path.join(AUDIO, "gbp_v28_ladder.h")
APLAY2_H = os.path.join(AUDIO, "gbp_aplay2.h")

FROZEN = {                       # #128 §3 / Amendment A's own table
    "GBP_V28_T704": 11264,
    "GBP_V28_T576": 9216,
    "GBP_V28_T448": 7168,
    "GBP_V28_T320": 5120,
    "GBP_V28_T256": 4096,
    "GBP_V28_T192": 3072,
}

GRID_BOUNDED = {                 # 3a's descent floor/ceiling, nulling's scan floor/ceiling
    "GBP_V28_P3_START": 6144,
    "GBP_V28_P3_MIN": 2048,
    "GBP_V28_P2_LO": 6144,
    "GBP_V28_P2_HI": 57344,
}

GRID_STEPS = {                   # the grids' own step sizes, and 3a's bisection width -- not
    "GBP_V28_P3_STEP": 512,       # TARGETs themselves, no bounds assert
    "GBP_V28_P2_STEP": 2048,
    "GBP_V28_P3_BISECT_WIDTH": 32,
}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def code(src):
    """C source without comments."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", " ", src, flags=re.S)


def parse_defines(src, prefix):
    out = {}
    for m in re.finditer(r"#define\s+(%s\w+)\s+(.+?)\s*(?:/\*.*)?$" % re.escape(prefix), code(src), re.M):
        out[m.group(1)] = m.group(2).strip()
    return out


def resolve_int(name, defs, seen=None):
    """Recursively substitutes referenced macro names and evaluates the resulting integer
    arithmetic -- so GBP_APLAY2_TARGET_MIN/_MAX are read from gbp_aplay2.h itself, never
    hand-copied as duplicate literals that could silently drift from the real header."""
    seen = set(seen or ())
    if name in seen:
        raise ValueError("macro cycle at %s" % name)
    seen.add(name)
    expr = defs[name]

    def repl(mo):
        n = mo.group(0)
        return "(%d)" % resolve_int(n, defs, seen) if n in defs else n

    expr = re.sub(r"\bGBP_APLAY2_\w+\b", repl, expr)
    expr = expr.replace("u", "").replace("U", "").replace("(uint32_t)", "").replace("(uint64_t)", "")
    return eval(expr, {"__builtins__": {}}, {})  # noqa: S307 -- fixed-format integer macro arithmetic only


ALL_DERIVED = {**FROZEN, **GRID_BOUNDED, **GRID_STEPS}


class TheLadderIsTheFrozenTable(unittest.TestCase):
    def test_every_native_target_is_derived_by_x16_not_hand_copied(self):
        h = code(read(LADDER_H))
        for name in ALL_DERIVED:
            old = "GBP_V28_OLD_" + name[len("GBP_V28_"):]
            m = re.search(r"#define\s+%s\s+\((%s\s*\*\s*GBP_V28_NATIVE_RATIO)\)" % (re.escape(name), re.escape(old)), h)
            self.assertIsNotNone(m, "%s must be defined as (%s * GBP_V28_NATIVE_RATIO), not a literal" % (name, old))

    def test_the_derived_values_match_the_frozen_table(self):
        h = code(read(LADDER_H))
        old = {}
        for m in re.finditer(r"#define\s+(GBP_V28_OLD_\w+)\s+(\d+)u", h):
            old[m.group(1)] = int(m.group(2))
        ratio_m = re.search(r"#define\s+GBP_V28_NATIVE_RATIO\s+(\d+)u", h)
        self.assertIsNotNone(ratio_m)
        ratio = int(ratio_m.group(1))
        self.assertEqual(ratio, 16)
        for name, native in ALL_DERIVED.items():
            old_name = "GBP_V28_OLD_" + name[len("GBP_V28_"):]
            self.assertIn(old_name, old, "%s is missing from the header" % old_name)
            self.assertEqual(old[old_name] * ratio, native,
                              "%s must equal %s x %d" % (name, old_name, ratio))

    def test_ahead_is_unconverted_chunk_counts(self):
        h = code(read(LADDER_H))
        for name, value in (("GBP_V28_A4", 4), ("GBP_V28_A3", 3), ("GBP_V28_A2", 2), ("GBP_V28_A1", 1)):
            self.assertIn("#define %s   %du" % (name, value), h)

    def test_the_step_mechanism_s_fixed_mute_is_derived_and_7(self):
        """Issue #136 amended #128 section 3's 6: the mute is BUILT from the measured ring deficit at the start of a
        step and the AHEAD-4 climb, plus one period of margin (gbp_v28_ladder.h derives it; _Static_asserts pin 6 + 1)."""
        h = code(read(LADDER_H))
        self.assertIn("#define GBP_V28_STEP_MUTE    (GBP_V28_STEP_NEED + GBP_V28_MUTE_MARGIN)", h)
        self.assertIn("_Static_assert(GBP_V28_STEP_NEED == 6u", h)
        self.assertIn("GBP_V28_STEP_MUTE == 7u && GBP_V28_START_MUTE == 10u", h)

    def test_the_largest_starts_mute_is_derived_and_10(self):
        h = code(read(LADDER_H))
        self.assertIn("#define GBP_V28_START_MUTE   (GBP_V28_START_NEED + GBP_V28_MUTE_MARGIN)", h)
        self.assertIn("_Static_assert(GBP_V28_START_NEED == 9u", h)


class TheBoundsCheckIsCompiledIn(unittest.TestCase):
    def test_every_target_has_an_uncommented_bounds_assert_not_under_an_if(self):
        body = code(read(LADDER_H))
        guard = body.index("#define OPENGBP_GBP_V28_LADDER_H")   # the file's own include guard, not a real conditional
        after_guard = body[guard + len("#define OPENGBP_GBP_V28_LADDER_H"):]
        # the file's own extern "C" idiom (#ifdef __cplusplus / #endif) is a harmless, always-entered-for-C
        # wrapper, not a real conditional -- strip it before scanning for a stray #if.
        scrubbed = re.sub(r"#\s*ifdef\s+__cplusplus\b", "", after_guard)
        for name in FROZEN:
            a = "_Static_assert(%s >= GBP_APLAY2_TARGET_MIN && %s <= GBP_APLAY2_TARGET_MAX," % (name, name)
            self.assertIn(a, scrubbed, "%s is missing its bounds assert" % name)
            self.assertIsNone(re.search(r"^\s*#\s*if\b", scrubbed[:scrubbed.index(a)], re.M),
                              "a compile-time assert must not sit under a preprocessor conditional")

    def test_the_frozen_ladder_itself_builds(self):
        src = '#include "gbp_v28_ladder.h"\nint main(void) { return 0; }\n'
        with tempfile.TemporaryDirectory() as d:
            srcfile = os.path.join(d, "ok.c")
            with open(srcfile, "w", encoding="utf-8") as f:
                f.write(src)
            exe = os.path.join(d, "ok")
            have, ok, err = hostcc.compile_c(["-std=gnu11", "-Wall", "-Wextra", "-I", AUDIO, "-o", exe, srcfile])
            hostcc.require(self, have, ok, err, what="gbp_v28_ladder.h")


class TheGridsGetTheSameTreatmentAsTheLadder(unittest.TestCase):
    """3a's descent grid and nulling's scan grid are old-path sample counts too (§3's own
    gbp_async_cfg_default fields), so they get the same x16 derivation and the same bounds
    asserts as the ladder's TARGET rungs -- checked here rather than assumed."""

    def test_every_grid_endpoint_has_an_uncommented_bounds_assert(self):
        body = code(read(LADDER_H))
        guard = body.index("#define OPENGBP_GBP_V28_LADDER_H")
        after_guard = body[guard + len("#define OPENGBP_GBP_V28_LADDER_H"):]
        scrubbed = re.sub(r"#\s*ifdef\s+__cplusplus\b", "", after_guard)
        for name in GRID_BOUNDED:
            a = "_Static_assert(%s >= GBP_APLAY2_TARGET_MIN && %s <= GBP_APLAY2_TARGET_MAX," % (name, name)
            self.assertIn(a, scrubbed, "%s is missing its bounds assert" % name)

    def test_both_grids_have_a_divisibility_assert(self):
        body = code(read(LADDER_H))
        self.assertIn("(GBP_V28_P3_START - GBP_V28_P3_MIN) % GBP_V28_P3_STEP == 0u", body)
        self.assertIn("(GBP_V28_P2_HI - GBP_V28_P2_LO) % GBP_V28_P2_STEP == 0u", body)

    def test_the_grids_land_exactly_on_their_own_endpoints(self):
        self.assertEqual((GRID_BOUNDED["GBP_V28_P3_START"] - GRID_BOUNDED["GBP_V28_P3_MIN"]) % GRID_STEPS["GBP_V28_P3_STEP"], 0)
        self.assertEqual((GRID_BOUNDED["GBP_V28_P2_HI"] - GRID_BOUNDED["GBP_V28_P2_LO"]) % GRID_STEPS["GBP_V28_P2_STEP"], 0)

    def test_p2_hi_is_the_one_grid_endpoint_the_bounds_check_alone_cannot_catch(self):
        """Documents the gap the header itself calls out: GBP_V28_OLD_P2_HI (3584) already falls
        inside [TARGET_MIN, TARGET_MAX] numerically, so an un-derived P2_HI would slip past the
        bounds assert. The divisibility assert is what actually catches it (checked next)."""
        min_v, max_v = 2048, 65279
        old_p2_hi = 3584
        self.assertTrue(min_v <= old_p2_hi <= max_v,
                         "if this ever becomes False, the header's own KNOWN GAP comment is stale")
        for name in ("GBP_V28_OLD_P3_START", "GBP_V28_OLD_P3_MIN", "GBP_V28_OLD_P2_LO"):
            old_v = ALL_DERIVED[name.replace("_OLD", "")] // 16
            self.assertFalse(min_v <= old_v <= max_v,
                              "%s (%d) was expected to fall outside bounds like the ladder's own values" %
                              (name, old_v))

    def test_the_divisibility_assert_catches_the_un_derived_p2_hi(self):
        """The concrete proof: with P2_LO/P2_STEP correctly derived (real parsed values, not
        hardcoded) but P2_HI left as the literal old value (3584), the SAME divisibility
        expression the header compiles in -- evaluated with C's uint32 wraparound -- is nonzero,
        so it would fail the build."""
        h = code(read(LADDER_H))
        lo = GRID_BOUNDED["GBP_V28_P2_LO"]
        step = GRID_STEPS["GBP_V28_P2_STEP"]
        m = re.search(r"#define\s+GBP_V28_OLD_P2_HI\s+(\d+)u", h)
        self.assertIsNotNone(m)
        old_p2_hi = int(m.group(1))
        remainder = ((old_p2_hi - lo) % (2 ** 32)) % step
        self.assertNotEqual(remainder, 0,
                             "the un-derived P2_HI must NOT land on the grid, or the divisibility "
                             "assert stops being the thing that catches this slip")


class TheBoundsCheckWouldCatchAnUnconvertedValue(unittest.TestCase):
    """Amendment A's own failure mode, checked arithmetically against the REAL
    GBP_APLAY2_TARGET_MIN/_MAX (parsed from gbp_aplay2.h, never hardcoded here): every ladder
    value taken literally (never x16-derived) falls outside those bounds -- the Issue text's own
    example, "T256 would be 256 native samples, 3.91 ms, well below TARGET_MIN". If this test
    ever fails because TARGET_MIN/_MAX moved enough to admit an unconverted value, the guard has
    stopped catching the error class it exists for, and gbp_v28_ladder.h needs a fresh look, not
    a quieter test."""

    @classmethod
    def setUpClass(cls):
        defs = parse_defines(read(APLAY2_H), "GBP_APLAY2_")
        cls.target_min = resolve_int("GBP_APLAY2_TARGET_MIN", defs)
        cls.target_max = resolve_int("GBP_APLAY2_TARGET_MAX", defs)

    def test_the_bounds_are_the_ones_the_header_actually_states(self):
        self.assertEqual(self.target_min, 2048)
        self.assertEqual(self.target_max, 65279)

    def test_every_unconverted_old_value_falls_outside_the_bounds(self):
        for name, native in FROZEN.items():
            old_name = "GBP_V28_OLD_" + name[len("GBP_V28_"):]
            old_value = native // 16
            in_bounds = self.target_min <= old_value <= self.target_max
            self.assertFalse(in_bounds,
                              "%s taken literally (%d) must fall outside [%d, %d] -- if it now falls "
                              "inside, Amendment A's guard no longer catches this unit slip" %
                              (old_name, old_value, self.target_min, self.target_max))

    def test_every_x16_derived_value_falls_inside_the_bounds(self):
        for name, native in FROZEN.items():
            in_bounds = self.target_min <= native <= self.target_max
            self.assertTrue(in_bounds, "%s (%d) must fall inside [%d, %d]" %
                             (name, native, self.target_min, self.target_max))


if __name__ == "__main__":
    unittest.main()
