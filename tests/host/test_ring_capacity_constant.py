"""tests/host/test_ring_capacity_constant.py -- GitHub Issue #139: the decoder ring's CAPACITY is one constant, GBP_APLAY2_RING, and nothing else in the audio chain
hard-codes its value.

The ring was 65 536 samples; the decode's RATE is 65 536 Hz (GBP_ADEC2_RATE): one number, two meanings. Doubling the ring to 131 072 (the nulling grid's top left it within
two chunks of full) touches every modulo and capacity check on it; a place that says `65536` and MEANS the capacity would silently keep the old size. This test fails on any
such literal in the audio chain's sources: every occurrence of 65536 / 65 536 / 0x10000 / 65535 / 131072 in code (comments stripped) under the audio modules, the v28 image and
the audio unit tests must be on the allowlist below, each one a RATE, a ratio of rates or a random-number scale, never a capacity.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AUDIO_H = os.path.join(ROOT, "src", "audio", "gbp_aplay2.h")

# (relative path, the stripped line) of every literal that is NOT the ring's capacity, with what it is
ALLOWED = {
    ("src/audio/gbp_adec2.h", "#define GBP_ADEC2_RATE      65536u"): "the decode's sample RATE, Hz",
    ("src/audio/gbp_v28_ladder.h", "_Static_assert(GBP_V28_NATIVE_RATIO == 65536u / 4096u,"): "a ratio of rates",
    ("src/audio/gbp_v28_ladder.h", '"gbp_v28_ladder: the native ratio no longer matches 65536/4096 -- recompute the whole ladder");'): "its message",
    ("src/audio/gbp_v28_ladder.h", "_Static_assert(65536u % 4096u == 0u,"): "a ratio of rates",
    ("src/audio/gbp_atrace.h", "#define GBP_ATRACE_SAMPLE_MAX   65536u"): "a trace store's record count, unrelated to the ring",
    ("src/audio/gbp_aplay2.h", "#define GBP_APLAY2_RING        131072u"): "THE definition: the one place the capacity is a number",
    ("src/audio/gbp_atrace.h", "#define GBP_ATRACE_A_SAT       0xFFFFu"): "a 16-bit saturation, a trace record's field",
    ("poc/gbp-audio-v28/source/main.c", "#define GBP_V28_LABEL_FG   0xFFFFu"): "an RGB5A3 colour",
    ("tests/unit/test_v28_latency_tag.c", "#define RESAMPLER_US (8.0 * 1e6 / 65536.0)"): "the RATE, in a delay",
    ("tests/unit/test_v28_stock.c", "#define FEED_HZ         65536.0"): "the game's own sample RATE",
}
ALLOWED_PREFIX = (
    ("src/audio/gbp_async.c", "a->sec_target[a->secs_used] = (uint16_t)(a->target > 0xFFFFu"),
    ("src/audio/gbp_atrace.c", "st->rec = (uint16_t)(r > 0xFFFFu ? 0xFFFFu : r);"),
    ("poc/gbp-audio-v28/source/main.c", "s.buttons = (uint16_t)(PAD_ButtonsHeld(PAD_CHAN0) & 0xFFFFu);"),
    ("poc/gbp-audio-v28/source/main.c", "gbp_alive_buttons(&live, now, (uint16_t)(PAD_ButtonsHeld(PAD_CHAN0) & 0xFFFFu));"),
    ("tests/unit/test_gbp_aplay2.c", 'eqi((long long)GBP_APLAY2_TARGET, 8192, "0.125 s at 65 536 Hz'),
    ("tests/unit/test_v28_latency_tag.c", "const double feedhz = 65536.0"),
    ("tests/unit/test_v28_latency_tag.c", "const double delta = (rate - 65536.0"),
    ("tests/unit/test_v28_latency_tag.c", "full = stock_only + (o.c_mean - (2048.0 - 65536.0"),
    ("tests/unit/test_v28_sweep_landing.c", "double dt = spread == 0.0 ? base : base * (1.0 - spread"),
    ("tests/unit/test_v28_sweep_landing.c", "if (stall_p > 0.0 && (double)(rnd() & 0xFFFFu)"),
)
LITERAL = re.compile(r"65536|65 536|0x10000|65535|131072|0xFFFF\b|0xFFFFu\b")


def strip(src):
    src = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def audio_sources():
    out = []
    for base, pred in (("src/audio", lambda f: f.startswith(("gbp_a", "gbp_v28", "gbp_walker"))),
                       ("poc/gbp-audio-v28/source", lambda f: f.endswith(".c")),
                       ("tests/unit", lambda f: re.match(r"test_(gbp_a(dec2|play2|resamp2|trans2)|gbp_v28|v28|gbp_walker)", f))):
        for dp, _dn, fn in os.walk(os.path.join(ROOT, base)):
            for f in sorted(fn):
                if f.endswith((".c", ".h")) and pred(f):
                    out.append(os.path.join(dp, f))
    return out


def offenders(paths, root=ROOT):
    bad = []
    for p in paths:
        rel = os.path.relpath(p, root)
        with open(p, encoding="utf-8", errors="replace") as f:
            text = strip(f.read())
        for n, line in enumerate(text.split("\n"), 1):
            if not LITERAL.search(line):
                continue
            s = line.strip()
            if (rel, s) in ALLOWED or any(rel == r and s.startswith(pre) for r, pre in ALLOWED_PREFIX):
                continue
            bad.append((rel, n, s[:110]))
    return bad


class TheRingCapacityIsOneConstant(unittest.TestCase):
    def test_the_constant_and_what_it_derives(self):
        h = open(AUDIO_H, encoding="utf-8").read()
        self.assertRegex(h, r"#define GBP_APLAY2_RING\s+131072u")
        self.assertIn("#define GBP_APLAY2_TARGET_MAX   (GBP_APLAY2_RING - GBP_APLAY2_BAND - 1u)", h)

    def test_no_place_in_the_audio_chain_hard_codes_a_ring_or_rate_number_outside_the_allowlist(self):
        paths = audio_sources()
        self.assertGreater(len(paths), 40, "the population went silently small")
        bad = offenders(paths)
        self.assertEqual(bad, [], "a literal that may mean the ring's capacity: %s" % bad)

    def test_every_allowlist_entry_is_still_present_so_the_list_cannot_rot(self):
        seen = set()
        for p in audio_sources():
            rel = os.path.relpath(p, ROOT)
            for line in strip(open(p, encoding="utf-8", errors="replace").read()).split("\n"):
                s = line.strip()
                if (rel, s) in ALLOWED:
                    seen.add((rel, s))
        self.assertEqual(sorted(set(ALLOWED) - seen), [], "an allowlist entry no longer exists in the source")

    def test_the_check_itself_catches_a_literal_capacity(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.c")
            with open(p, "w", encoding="utf-8") as f:
                f.write("static int16_t ring[65536];\n/* 65536 in a comment is fine */\nuint32_t m = (h + n) % 65536u;\n")
            bad = offenders([p], root=d)
            self.assertEqual([b[1] for b in bad], [1, 3])

    def test_every_ring_in_the_sources_is_sized_by_the_constant(self):
        for p in audio_sources():
            text = strip(open(p, encoding="utf-8", errors="replace").read())
            for m in re.finditer(r"\bint16_t\s+(\w*ring\w*)\s*\[\s*([^\]]+)\]", text):
                nums = [int(x) for x in re.findall(r"\b\d+\b", m.group(2))]
                if nums and max(nums) < 4096 and "GBP_APLAY2_RING" not in m.group(2):
                    continue          # a deliberately tiny ring a module test wraps by hand (test_gbp_adec2.c)
                if re.fullmatch(r"\s*GBP_APLAY_RING\s*", m.group(2)):
                    continue          # the OLD 4096 Hz path's own ring (gbp_aplay.h), a different chain
                self.assertIn("GBP_APLAY2_RING", m.group(2), "%s: %s is not sized by GBP_APLAY2_RING" % (os.path.relpath(p, ROOT), m.group(1)))


class TheMemoryPaysForIt(unittest.TestCase):
    """Doubling the ring adds 131 072 B of static store (int16_t x 65 536). tools/v28budget.py's plans keep the arena floor with room (validation_run: +4 497 408 B
    above `HEAP_FLOOR` without the ride-along, RUN 43's fixture; the image's own bss_end is 0x80f7a3b8, 7 880 776 B under arena1_hi before the framebuffers); the ring's
    growth must leave that room above the floor."""

    def test_the_arena_floor_is_kept_with_the_ring_doubled(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import v28budget
        with open(v28budget.RUN43, encoding="utf-8", errors="replace") as f:
            out = v28budget.analyse(f.read())
        growth = (131072 - 65536) * 2
        for plan in ("validation_run", "diag_loss", "perceptual_no_phase1"):
            room = out["plans"][plan]["awr_dropped"]["above_floor"]
            self.assertGreater(room - growth, 3_000_000, "%s: %d B above the floor, %d B after the ring's growth" % (plan, room, room - growth))
        self.assertEqual(growth, 131072)


if __name__ == "__main__":
    unittest.main()
