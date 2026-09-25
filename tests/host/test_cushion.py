"""tests/host/test_cushion.py -- GitHub Issue #121: the chain's default cushion adopted at 0.125 s, set in time, on
RUN 43's interleaved arms (GBP-HW-343).

What is held here:
  * THE VALUE IS TIME. src/audio/gbp_aplay.h states the cushion in microseconds and derives GBP_APLAY_TARGET from it
    and from the decoder's rate (GBP_ADEC_RATE), so #118 changing the rate recomputes the count and renegotiates
    nothing; gbp_aplay_init() holds it; gbp_aplay.c asserts at compile time that it is a whole number of samples the
    clamp accepts;
  * THE PINS ARE KEPT. The default was 0.5 s in every build before #121; each executed image reproduces at its own
    commit (HARDWARE_TESTS §V23.9, the rule #109 applied when it moved the step default), and the frozen images'
    sources stay pinned byte for byte by their own image tests (test_game2_image and the others, through
    frozen.source); sync-0001, which set its own levels through gbp_aplay_set_target, keeps them as literals in
    gbp_async.c;
  * THE COST TRAVELS WITH THE VALUE. Every paragraph or table row of the records that names #121 and 0.125 s carries,
    in the same paragraph, "no increase in AUDIO loss was detected at 0.125 s, and a lower loss is not established",
    the primary statistic (the exact permutation, 0.068) and the interval's measured calibration (15.75 %) -- the
    three things docs/RESEARCH_METHOD.md's new rule asks for wherever the result is quoted; none renders as a setext
    heading; none says it costs nothing or is better; the records say it reduces the offset and does not remove it;
  * the method rule the adoption produced is in docs/RESEARCH_METHOD.md.
The chain's behaviour at the new default is checked in tests/unit/test_gbp_aplay.c.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APLAY_H = os.path.join(ROOT, "src", "audio", "gbp_aplay.h")
APLAY_C = os.path.join(ROOT, "src", "audio", "gbp_aplay.c")
ADEC_H = os.path.join(ROOT, "src", "audio", "gbp_adec.h")
COST = "No increase in AUDIO loss was detected at 0.125 s, and a lower loss is not established"
RECORDS = ("docs/protocol/AUDIO.md", "docs/research/EVIDENCE.md", "docs/research/UNKNOWNS.md",
           "docs/research/HARDWARE_TESTS.md", "docs/research/DEVLOG.md")


def read(p):
    with open(p if os.path.isabs(p) else os.path.join(ROOT, p), encoding="utf-8") as f:
        return f.read()


def flat(s):
    return " ".join(s.replace("`", "").replace("*", "").split())


def code(src):
    """C source without comments."""
    return re.sub(r"/\*.*?\*/|//[^\n]*", " ", src, flags=re.S)


def define(src, name):
    m = re.search(r"^#define %s\s+(.+?)\s*(?:/\*.*)?$" % name, src, re.M)
    return m.group(1).strip() if m else None


class TheValueIsTime(unittest.TestCase):
    def test_the_cushion_is_stated_in_microseconds_and_the_target_derived(self):
        h = read(APLAY_H)
        self.assertEqual(define(h, "GBP_APLAY_CUSHION_US"), "125000u")
        self.assertEqual(define(h, "GBP_APLAY_TARGET"),
                         "((uint32_t)(((uint64_t)GBP_ADEC_RATE * GBP_APLAY_CUSHION_US) / 1000000u))")
        rate = int(define(read(ADEC_H), "GBP_ADEC_RATE").rstrip("u"))
        self.assertEqual(rate, 4096)
        self.assertEqual((rate * 125000 // 1000000, rate * 125000 % 1000000), (512, 0))
        for future in (32768, 65536):                            # #118's candidates: whole samples either way
            self.assertEqual(future * 125000 % 1000000, 0)
        self.assertGreater(65536 * 125000, 2 ** 32 - 1)           # why the product is taken in 64 bits

    def test_it_is_checked_where_it_is_compiled_and_held_by_init(self):
        c = read(APLAY_C)
        body = code(c)                                         # a commented-out assert does not count
        a1 = "_Static_assert(((uint64_t)GBP_ADEC_RATE * GBP_APLAY_CUSHION_US) % 1000000u == 0u,"
        a2 = "_Static_assert(GBP_APLAY_TARGET >= GBP_APLAY_TARGET_MIN && GBP_APLAY_TARGET <= GBP_APLAY_TARGET_MAX,"
        self.assertIn(a1, body)
        self.assertIn(a2, body)
        self.assertIsNone(re.search(r"^\s*#\s*if", body[:body.index(a2)], re.M),
                          "a compile-time assert must not sit under a preprocessor conditional")
        init = body[body.index("void gbp_aplay_init("):]
        self.assertIn("p->target = GBP_APLAY_TARGET;", init[:init.index("\n}\n")])
        self.assertNotIn("gbp_aplay_init_runtime", c + read(APLAY_H))       # one default, not two


class ThePinsAreKept(unittest.TestCase):
    # A check that #121 touched no POC source would be an OPEN range over poc/ (Issue #97 closed those) and would fail
    # on the next image; the frozen sources are pinned byte for byte by their own image tests instead.
    def test_the_rule_that_keeps_them_is_the_record_s(self):
        self.assertIn("each executed image reproduces at its own commit", flat(read(APLAY_H)))
        self.assertIn("The consequence: an executed image reproduces at its own commit, not at HEAD.",
                      read("docs/research/HARDWARE_TESTS.md"))

    def test_sync_0001_pins_its_own_levels(self):
        self.assertIn("2048u, 512u, 384u,          /* deep, shallow, floor */", read("src/audio/gbp_async.c"))


class TheCostTravelsWithTheValue(unittest.TestCase):
    @staticmethod
    def adoption_paragraphs():
        """(record, raw chunk) for every non-heading paragraph or table row that names #121 and 0.125 s."""
        out = []
        for r in RECORDS:
            for p in re.split(r"\n\s*\n|\n(?=\|)", read(r)):
                if p.lstrip().startswith("#"):
                    continue                                    # a heading names the change; the body carries it
                f = flat(p)
                if "0.125 s" in f and "#121" in f:
                    out.append((r, p))
        return out

    def test_every_adoption_paragraph_carries_the_cost_the_primary_and_the_calibration(self):
        seen = self.adoption_paragraphs()
        self.assertGreaterEqual(len(seen), 6)
        self.assertEqual({r for r, _ in seen}, set(RECORDS))
        for r, p in seen:
            f = flat(p)
            for tok in (COST, "exact permutation", "0.068", "15.75 %"):
                self.assertIn(tok.lower(), f.lower(), "%s lacks %r: %s" % (r, tok, f[:160]))

    def test_no_adoption_paragraph_renders_as_a_heading(self):
        for r, p in self.adoption_paragraphs():
            self.assertIsNone(re.search(r"\n[ \t]*(-{3,}|=+)[ \t]*$", p.rstrip("\n")), "%s: %s" % (r, flat(p)[:120]))

    def test_no_adoption_paragraph_says_it_is_free_or_better(self):
        for r, p in self.adoption_paragraphs():
            for bad in ("costs nothing", "it is better", "0.125 s is better", "better than 0.5 s", "free of cost",
                        "at no cost to the drain", "a lower loss was"):
                self.assertNotIn(bad, flat(p).lower(), (r, bad))

    def test_the_offset_is_reduced_not_removed(self):
        self.assertIn("reduces the audio-behind-video offset and does not remove it", flat(read("docs/protocol/AUDIO.md")))
        u = flat(read("docs/research/UNKNOWNS.md"))
        self.assertIn("reduces the offset and does not remove it.", u)
        self.assertIn("The item stays OPEN. The check that the new default is better in use is the Operator's", u)

    def test_the_underrun_bound_keeps_its_confidence(self):
        a = flat(read("docs/protocol/AUDIO.md"))
        self.assertIn("below 3/71 = 0.042 per second at 95 % only (rule of three)", a)
        self.assertNotIn("bounds the underrun rate only below 0.042", a)


class TheMethodRule(unittest.TestCase):
    def test_the_rule_is_where_the_other_two_are(self):
        m = read("docs/RESEARCH_METHOD.md")
        h = ("### When two statistics disagree, calibrate them against the design instead of choosing "
             "(2026-09-25, GitHub Issue #121)")
        self.assertIn(h, m)
        self.assertLess(m.index("### A frozen mechanism carries its arithmetic"), m.index(h))
        self.assertLess(m.index(h), m.index("## Hardware test requests"))
        body = flat(m[m.index(h):m.index("## Hardware test requests")])
        for tok in ("63 of 400 simulations, 15.75 % against its nominal 10 %", "TheIntervalsCoverage",
                    "16 of 400 simulations, 4.0 %", "ThePermutationsSize",
                    "Cite the calibration by its test, not by an argument."):
            self.assertIn(tok, body, tok)


if __name__ == "__main__":
    unittest.main()
