"""tests/host/test_v28_label_position.py -- GitHub Issue #131 (RUN 48): the label's own y0 sat
inside ordinary overscan, and a real TV cropped it -- the Operator read "P2/4" as "F2/4". main.c
cannot be compiled or driven on the host (tests/unit/test_v28_zero_feed_integration.c's own header
comment; no such harness exists anywhere in this project), so this is the structural companion
test_v28_anchor_wiring.py's own shape already established: it reads main.c's OWN source text and
confirms draw_label_quad()'s y0 is computed from the display mode's own efbHeight with a real
safe-area margin, never the fixed small constant (8.0f) that produced the defect.
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


def label_quad_body(src):
    i = src.index("static void draw_label_quad(void)")
    j = src.index("static void", i + 1)
    return src[i:j]


class LabelPosition(unittest.TestCase):
    def test_y0_is_not_a_small_fixed_constant(self):
        """The exact defect RUN 48 found: y0 = 8.0f, a fixed offset that assumes no overscan at
        all. Never again, whatever the replacement expression looks like."""
        body = label_quad_body(read())
        self.assertNotRegex(body, r"\by0\s*=\s*8\.0f\s*;",
                            "y0 is back to the fixed 8.0f offset RUN 48 found cropped by a real TV")
        m = re.search(r"\by0\s*=\s*([0-9.]+)f\s*;", body)
        if m:
            self.assertGreaterEqual(float(m.group(1)), 24.0,
                                    "y0 is a fixed constant smaller than a plausible overscan margin (24px)")

    def test_y0_scales_with_the_display_mode_s_own_height(self):
        """A fixed pixel count cannot be safe across every mode this project targets (NTSC, PAL,
        interlaced/progressive efbHeight all differ) -- y0 must be computed FROM rmode->efbHeight,
        not a literal."""
        body = label_quad_body(read())
        self.assertRegex(body, r"\by0\s*=\s*\(f32\)\s*rmode\s*->\s*efbHeight\s*\*\s*([0-9.]+)f\s*;",
                         "y0 is not computed from rmode->efbHeight")

    def test_the_margin_fraction_is_a_real_safe_area_inset(self):
        """A fraction near 0 would reproduce the same defect in different clothing. The standard
        broadcast title-safe inset is 10% (SMPTE RP 218); require at least 5% so a future edit
        cannot quietly shrink the margin back toward the cropped case."""
        body = label_quad_body(read())
        m = re.search(r"\by0\s*=\s*\(f32\)\s*rmode\s*->\s*efbHeight\s*\*\s*([0-9.]+)f\s*;", body)
        self.assertIsNotNone(m, "could not find y0's own margin fraction")
        self.assertGreaterEqual(float(m.group(1)), 0.05,
                                "the margin fraction is too small to be a real overscan safe area")

    def test_the_fix_is_scoped_to_the_label_quad_not_the_game_quad(self):
        """draw_quad() (the 240x160 game picture) must stay centred exactly as it was -- this fix
        is about the LABEL's own placement, not a wholesale change to the video path."""
        src = read()
        i = src.index("static void draw_quad(void)")
        j = src.index("static void draw_label_quad")
        game_quad = src[i:j]
        self.assertRegex(game_quad, r"\by0\s*=\s*\(\(f32\)rmode->efbHeight - h\)\s*\*\s*0\.5f\s*;",
                         "draw_quad()'s own centring changed; only the label was meant to move")


if __name__ == "__main__":
    unittest.main()
