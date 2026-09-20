"""
tests/host/test_witelig.py — the research not-before gate, pinned by source
(HARDWARE_TESTS §V5.55).

Run 7 opened the structural scientific window 3.840 s after the CONTROL
transform; the indexed stimulus began at 4.845 s -- and at 4.845 s in all four
indexed runs. stream-0010 defers ONE thing: when the qualification streak may
be counted. These tests pin that it defers nothing else, that it knows nothing
about content, and that the profile the user gets is unchanged.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")
WH = os.path.join(ROOT, "src", "gbp", "gbp_vwitness.h")
WC = os.path.join(ROOT, "src", "gbp", "gbp_vwitness.c")
WD = os.path.join(ROOT, "src", "gbp", "gbp_vwitness_drive.h")
MAKE = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "Makefile")

# Word-bounded on purpose: the assembler's own GBP_VSTATE_F_RESYNC is
# STRUCTURAL and must stay allowed; the stimulus's SYNC byte must not.
OGBPIDX_TOKENS = (r"0xB2", r"\bSYNC\b", r"\bFRAME_ID\b", r"\bframe_id\b", r"\bSTATUS\b",
                  r"\bcrc8", r"\bCRC8", r"\bBLOCK_INDEX\b", r"\bistim\b", r"\bvindex\b",
                  r"\bvidxcap\b", r"OGBPIDX", r"\bID_BITS\b", r"\bPAYLOAD_BITS\b",
                  r"\bcanonical\b", r"indexed-0003", r"\bZERO\b", r"\bONE\b")


def read(p):
    with open(p) as f:
        return f.read()


def strip(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"//[^\n]*", " ", src)


def func(src, name):
    m = re.search(r"^static [^\n;]*\b%s\s*\([^)]*\)\s*\{" % re.escape(name), src, re.M)
    assert m, name
    i = src.index("{", m.start())
    d = 0
    for j in range(i, len(src)):
        d += src[j] == "{"
        d -= src[j] == "}"
        if d == 0:
            return src[i:j + 1]
    raise AssertionError(name)


class TheGateIsWhereItSaysAndNowhereElse(unittest.TestCase):
    def test_armed_once_at_init_released_once_in_pump(self):
        s = strip(read(MAIN))
        self.assertEqual(s.count("gbp_vwitness_gate_streak(&wit);"), 1)
        self.assertEqual(s.count("gbp_vwitness_release_streak(&wit, now);"), 1)
        self.assertIn("gbp_vwitness_release_streak", func(s, "pump"))
        self.assertLess(s.index("gbp_vwitness_set_qualification(&wit, GBP_VWITNESS_QUAL_REQUIRED);"),
                        s.index("gbp_vwitness_gate_streak(&wit);"))
        self.assertLess(s.index("gbp_vwitness_gate_streak(&wit);"),
                        s.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"))

    def test_the_threshold_is_5000_ms_from_the_control_transform(self):
        s = strip(read(MAIN))
        self.assertIn("#define STREAM_WIT_NOT_BEFORE_MS 5000u", read(MAIN))
        self.assertIn("wit_not_before_ticks = ((uint64_t)tb_hz * STREAM_WIT_NOT_BEFORE_MS) / 1000u;", s)
        body = func(s, "pump")
        self.assertIn("pump_res->t_control_transform", body)
        self.assertIn("now - pump_res->t_control_transform >= wit_not_before_ticks", body)

    def test_the_gate_is_a_compare_not_a_wait(self):
        """J. Nothing is delayed except the streak. The gate block in pump() is
        one clock read and one compare; it may not wait, spin, sleep or touch
        the device, and it may not be in the present path at all."""
        s = strip(read(MAIN))
        body = func(s, "pump")
        i = body.index("gbp_vwitness_streak_gated(&wit)")
        j = body.index("gbp_vwitness_release_streak(&wit, now);")
        block = body[i:j]
        for forbidden in ("VIDEO_WaitVSync", "while (", "for (", "usleep", "sleep",
                          "gbp_transport", "hsp_", "ringlog_printf", "printf"):
            self.assertNotIn(forbidden, block)
        self.assertNotIn("wit", func(s, "submit_ready"))
        self.assertNotIn("wit_not_before", func(s, "submit_ready"))

    def test_startup_and_display_are_untouched(self):
        """J/K. The user's path is stream-0009's: same profile, headless
        self-test, no wait, black framebuffers, first hand-off from capture."""
        s = strip(read(MAIN))
        self.assertIn("cfg.prehandler_wait_ms = startup.prehandler_wait_ms;", s)
        self.assertNotIn("cfg.prehandler_wait_ms = 5000", s)
        self.assertIn("selftest_submit_headless(buf);", func(s, "display_selftest"))
        self.assertIn("VIDEO_ClearFrameBuffer(rmode, xfb_stream_buf[0], COLOR_BLACK);", func(s, "video_setup"))
        # the gate is not consulted anywhere on the way to the first real frame
        for fn in ("video_setup", "display_selftest", "selftest_submit_headless",
                   "submit_ready", "offer_oldest_ready", "on_draw_done"):
            self.assertNotIn("streak", func(s, fn))

    def test_the_safety_cap_and_capture_targets_are_unchanged(self):
        """M."""
        s = read(MAIN)
        self.assertIn("#define STREAM_CAPTURE_SECONDS   30u", s)
        self.assertIn("#define STREAM_SAFETY_SECONDS    60u", s)
        self.assertIn("cfg.hard_wallclock_s = STREAM_SAFETY_SECONDS;", strip(s))

    def test_the_log_says_what_happened_in_one_line(self):
        s = strip(read(MAIN))
        self.assertEqual(s.count('"WITELIG policy=time_not_before origin=control'), 1)
        for field in ("not_before_ms=%lu", "released=%lu", "still_gated=%d", "t_eligible=%llx",
                      "ticks_control_to_eligible=%llu", "frames_seen_before_eligible=%lu",
                      "disqualified_before_eligible=%lu", "qual_streak_at_eligible=0"):
            self.assertIn(field, s)
        # after WITQUAL, after the teardown, never in the hot path
        self.assertLess(s.index('"WITQUAL policy='), s.index('"WITELIG policy='))
        self.assertLess(s.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"), s.index('"WITELIG'))


class TheGateKnowsNothingAboutContent(unittest.TestCase):
    """N. Eligibility is time >= threshold and the existing STRUCTURAL
    predicate. No OGBPIDX constant, decoder or field may reach the witness
    module, the drive header, or the gate block in the probe."""

    def test_the_witness_module_names_no_stimulus_field(self):
        for p in (WH, WC, WD):
            src = strip(read(p))
            for tok in OGBPIDX_TOKENS:
                self.assertIsNone(re.search(tok, src), "%s mentions %r" % (os.path.basename(p), tok))
            self.assertNotIn('#include "istim', read(p))
            self.assertNotIn('#include "gbp_vidx', read(p).replace('#include "gbp_vidxdump.h"', ""))

    def test_the_gate_block_in_the_probe_names_no_stimulus_field(self):
        s = strip(read(MAIN))
        body = func(s, "pump")
        i = body.index("gbp_vwitness_streak_gated(&wit)")
        j = body.index("gbp_vwitness_release_streak(&wit, now);")
        for tok in OGBPIDX_TOKENS:
            self.assertIsNone(re.search(tok, body[i:j]), tok)

    def test_the_latch_api_takes_only_a_witness_and_a_tick(self):
        h = strip(read(WH))
        self.assertIn("void gbp_vwitness_gate_streak(struct gbp_vwitness *w);", h)
        self.assertIn("void gbp_vwitness_release_streak(struct gbp_vwitness *w, uint64_t t);", h)
        self.assertIn("int gbp_vwitness_streak_gated(const struct gbp_vwitness *w);", h)

    def test_the_predicate_itself_is_the_old_one(self):
        d = strip(read(WD))
        self.assertIn("if (completeness != GBP_VSTATE_FRAME_COMPLETE_40) return 0;", d)
        self.assertIn("if (blocks != GBP_VWITNESS_BLOCKS) return 0;", d)
        self.assertNotIn("elig", d, "the drive header does not know the gate exists")


class TheBuildIsANewIdentity(unittest.TestCase):
    def test_build_id_is_stream_0010(self):
        m = re.search(r"^BUILD_ID\s*:=\s*(\S+)$", read(MAKE), re.M)
        self.assertEqual(m.group(1), "stream-0010")

    def test_it_is_research_instrumentation_and_says_so(self):
        self.assertIn("RESEARCH INSTRUMENTATION", read(MAIN))


if __name__ == "__main__":
    unittest.main()
