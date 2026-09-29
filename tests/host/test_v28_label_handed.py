"""tests/host/test_v28_label_handed.py -- GitHub Issue #131 (RUN 48 / RUN 50 prep). RUN 48 was
silent for 310s with every counter looking healthy until teardown; the Operator's ear was the only
mid-run signal and silence is ambiguous (he could be standing in a quiet spot in the game). A
static "started" mark cannot distinguish a stall from healthy playback -- only a number that MOVES
while hand-offs move can. `v28_label_text()`'s validation branch (main.c, `#else` of
`GBP_V28_PLAN_PERCEPTUAL`) now shows `ap2.handed`, the count of chunks actually handed to the AI
DMA, alongside the phase/clock it already showed.

main.c cannot be compiled or driven on the host (tests/unit/test_v28_zero_feed_integration.c's own
header comment; no such harness exists anywhere in this project), so this is the same structural
shape as test_v28_label_position.py and test_v28_leak.py: read main.c's own source text and check
the two `#if defined(GBP_V28_PLAN_PERCEPTUAL)`/`#else` branches of `v28_label_text()` directly,
rather than trust a description of what the function does.
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")


def read():
    with open(MAIN, encoding="utf-8") as f:
        return f.read()


def label_text_body(src):
    """The function's DEFINITION, not the forward declaration a few hundred lines above it
    (`static void v28_label_text(char *out, size_t cap, uint64_t now);`, no body) -- a plain
    src.index() on the name finds that declaration first."""
    m = re.search(r"static void v28_label_text\([^\n;]*\)\n\{", src)
    assert m, "v28_label_text()'s definition was not found"
    i = m.start()
    j = src.index("static uint64_t t_video_ready", i)
    return src[i:j]


def split_branches(body):
    """(perceptual, validation) source text of the one `#if defined(GBP_V28_PLAN_PERCEPTUAL)
    ... #else ... #endif` block inside v28_label_text()'s body."""
    m = re.search(r"#if\s+defined\(GBP_V28_PLAN_PERCEPTUAL\)\n(.*?)#else\n(.*?)#endif\n", body, re.S)
    assert m, "v28_label_text() has no GBP_V28_PLAN_PERCEPTUAL split -- the function shape changed"
    return m.group(1), m.group(2)


class TheValidationLabelShowsAMovingHandoffCount(unittest.TestCase):
    def test_the_validation_branch_reads_ap2_handed(self):
        """The count that actually moves while the AI DMA hands off chunks -- not a static
        "started" flag RUN 48 taught us not to trust."""
        _, validation = split_branches(label_text_body(read()))
        # Issue #138: sampled once a second by label_handed_once_a_second(), which reads ap2.handed (RUN 54: a value that changed on
        # every hand-off re-rendered the label ~29 times a second and cost 0.41 points of loss)
        self.assertIn("label_handed_once_a_second(elapsed_s)", validation,
                      "the validation label no longer shows the hand-off count -- RUN 48's stall would "
                      "again look identical to healthy playback on screen")
        m = re.search(r"static uint32_t label_handed_once_a_second\(uint32_t elapsed_s\)\n\{(.*?)\n\}", read(), re.S)
        self.assertIsNotNone(m)
        self.assertIn("(uint32_t)ap2.handed", m.group(1))

    def test_the_marker_is_formatted_as_a_number_not_a_static_flag(self):
        """A fixed string like " A" once ai_started fires proves the DMA started once; it cannot
        show started-then-stalled, the exact case RUN 48 turned out to be. Require an actual %lu
        conversion of ap2.handed in the snprintf call, not a literal substring."""
        _, validation = split_branches(label_text_body(read()))
        self.assertRegex(validation, r'snprintf\([^;]*"[^"]*H%lu[^"]*"[^;]*\(unsigned long\)label_handed_once_a_second\(elapsed_s\)',
                         "the hand-off count is not passed through a %lu conversion in the label's snprintf")

    def test_the_perceptual_branch_never_reads_ap2(self):
        """v28_label_text()'s own header comment: "never ... anything from atrans2/aplay2/adec2 in
        the perceptual build". The handed marker is validation-only; confirm it did not leak into
        the SAFE branch (Issue #128 section 7 / Amendment C's own NEVER list, tests/host/
        test_v28_leak.py's own rule, extended here to this function since that file does not cover
        v28_label_text())."""
        perceptual, _ = split_branches(label_text_body(read()))
        self.assertNotIn("ap2.", perceptual,
                         "v28_label_text()'s perceptual branch now reads ap2 -- not a SAFE field")

    def test_the_split_extractor_actually_narrows_the_text(self):
        """Sanity check on the extractor itself, same shape as test_v28_leak.py's own: if the
        #if/#else split were mis-parsed and split_branches silently returned the same text for both
        branches, test_the_perceptual_branch_never_reads_ap2 above would pass vacuously."""
        perceptual, validation = split_branches(label_text_body(read()))
        self.assertIn("label_handed_once_a_second", validation)
        self.assertNotIn("ap2.handed", perceptual)
        self.assertNotIn("label_handed_once_a_second", perceptual)


if __name__ == "__main__":
    unittest.main()
