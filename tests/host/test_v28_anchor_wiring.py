"""tests/host/test_v28_anchor_wiring.py -- GitHub Issue #128/#129/#130, the Orchestrator's
Amendment 1 on Issue #131's own freeze: proves main.c actually calls gbp_v28_anchor() with 3a's
own CORRECTLY-EXTRACTED confirmed floor, never 3a's own raw field passed straight into
gbp_v28_3b_start() (the exact defect this round fixes). main.c cannot be compiled or driven on the
host (tests/unit/test_v28_zero_feed_integration.c's own header comment; no such harness exists
anywhere in this project) -- this is the structural companion tests/unit/test_gbp_v28_anchor.c's
own direct function tests need, the same shape test_v28_leak.py already established.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
MAIN = os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")


def read():
    with open(MAIN, encoding="utf-8") as f:
        return f.read()


class Wiring(unittest.TestCase):
    def test_last_hold_is_never_passed_straight_into_3b_start(self):
        """The exact defect: gbp_v28_3b_start(&s3b, s3a.last_hold, ...)."""
        src = read()
        self.assertNotRegex(src, r"gbp_v28_3b_start\s*\([^)]*s3a\.last_hold")

    def test_gbp_v28_3b_start_is_called_with_the_anchor_s_own_target(self):
        src = read()
        self.assertRegex(src, r"gbp_v28_3b_start\s*\(\s*&s3b\s*,\s*v28_anchor\.target")

    def test_the_floor_extraction_uses_the_dedicated_accessor_not_lo_directly(self):
        """3a's own confirmed floor (the Orchestrator's own correction at #131's freeze): `lo` is
        the CONFIRM dwell's own target, the HIGHEST FAILING depth being re-tested, never the lowest
        HOLDING one -- main.c must call gbp_v28_3a_confirmed_floor() (gbp_v28_3a.h), never read
        s3a.lo directly at this call site."""
        src = read()
        self.assertRegex(src, r"has_floor\s*=\s*gbp_v28_3a_confirmed_floor\s*\(\s*&s3a\s*,\s*&floor_native\s*\)")
        # the exact first (backwards) attempt this test itself once passed against -- never again
        self.assertNotRegex(src, r"s3a\.bracket_closed\s*\?\s*s3a\.lo\s*:\s*s3a\.last_hold")
        self.assertNotRegex(src, r"gbp_v28_anchor\s*\([^;]*\bs3a\.lo\b")

    def test_gbp_v28_anchor_is_actually_called(self):
        src = read()
        self.assertRegex(src, r"v28_anchor\s*=\s*gbp_v28_anchor\s*\(\s*floor_native\s*,\s*has_floor\s*\)")

    def test_the_none_source_skips_the_hold(self):
        """GBP_V28_ANCHOR_NONE (the floor sits above T704): gbp_v28_3b_start() must not be called
        at all -- guarded, not called unconditionally after computing the anchor."""
        src = read()
        m = re.search(r"v28_anchor\s*=\s*gbp_v28_anchor\([^;]*\);(.*?)gbp_walker_phase_complete\(&walker",
                      src, re.S)
        self.assertIsNotNone(m, "could not find the anchor-computation-to-phase-complete block")
        block = m.group(1)
        self.assertIn("GBP_V28_ANCHOR_NONE", block)
        self.assertIn("gbp_v28_3b_start", block)
        # the call must be inside an `if` that excludes NONE, not a bare unconditional call
        self.assertRegex(block, r"if\s*\([^)]*!=\s*GBP_V28_ANCHOR_NONE[^)]*\)\s*\n?\s*gbp_v28_3b_start")

    def test_v28anchor_record_is_emitted(self):
        src = read()
        self.assertIn('"V28ANCHOR target=%lu source=%s"', src)

    def test_v28_3b_record_carries_the_anchor_and_its_source(self):
        """Robust to how the format string is split across source lines -- checks the actual
        printf call site's own format text and arguments, not one exact literal concatenation."""
        src = read()
        m = re.search(r'ringlog_printf\(&rl,\s*"V28_3B n=%lu ahead=%lu anchor=%lu source=%s '
                     r'underrun_seen=%u partial=%u t_set=%llx\s*"\s*\n\s*"t_done=%llx"', src)
        self.assertIsNotNone(m, "V28_3B's own format string must carry anchor=%lu source=%s")
        self.assertIn("v28_anchor.target", src)
        self.assertIn("gbp_v28_anchor_source_name(v28_anchor.source)", src)

    def test_v28anchor_only_prints_once_actually_computed(self):
        src = read()
        m = re.search(r'if\s*\(v28_anchor_computed\)\s*\n\s*ringlog_printf\(&rl, "V28ANCHOR', src)
        self.assertIsNotNone(m, "V28ANCHOR must be gated on v28_anchor_computed, not printed unconditionally")


if __name__ == "__main__":
    unittest.main()
