"""
tests/host/test_startup.py — the NORMAL startup path, pinned by source
(HARDWARE_TESTS §V5.52).

`stream-0008` showed the operator a rainbow/checkerboard for 5.1777 s before any
Game Boy Player video appeared. It was the synthetic `display_selftest()`
pattern handed to the video interface, and 5.000 s of the wait was the
`prehandler_wait_ms` DIAGNOSTIC. Neither is a protocol requirement:
`vstate-0001` ran with no wait and captured the animated GAME BOY logotype
0.5014 s after capture start, while `vstate-prewait-5000` with the same 5 s
reported `STRUCTURED not_observed`.

These are WIRING tests. They read the source and pin the two things the normal
path must never do and the one thing it must always do. They can be defeated by
someone who edits them; they cannot be defeated by someone who forgets.

Behaviour of the profile itself is tested exhaustively in C, in
tests/unit/test_gbp_startup.c.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")
MAKE = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "Makefile")
HDR = os.path.join(ROOT, "src", "gbp", "gbp_startup.h")
VQUEUE = os.path.join(ROOT, "src", "gbp", "gbp_vqueue.h")


def read(p):
    with open(p) as f:
        return f.read()


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"//[^\n]*", " ", src)


def func(src, name):
    """The body of one static function, by brace matching."""
    m = re.search(r"^static [^\n;]*\b%s\s*\([^)]*\)\s*\{" % re.escape(name), src, re.M)
    assert m, "function %s not found" % name
    i = src.index("{", m.start())
    d = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            d += 1
        elif src[j] == "}":
            d -= 1
            if d == 0:
                return src[i:j + 1]
    raise AssertionError("unbalanced braces in %s" % name)


class ThereIsExactlyOnePlaceThatDecides(unittest.TestCase):
    def test_the_profile_header_exists_and_is_the_only_decider(self):
        self.assertTrue(os.path.exists(HDR))
        s = strip_comments(read(MAIN))
        self.assertIn("gbp_startup_profile(&startup, GBP_STARTUP_MODE);", s)
        self.assertEqual(s.count("gbp_startup_profile("), 1,
                         "the profile is resolved in exactly one place")

    def test_the_profile_is_resolved_before_anything_can_read_it(self):
        s = strip_comments(read(MAIN))
        i_profile = s.index("gbp_startup_profile(&startup, GBP_STARTUP_MODE);")
        self.assertLess(i_profile, s.index("video_setup();"),
                        "video_setup() reads clear_framebuffers")
        self.assertLess(i_profile, s.index("display_selftest();"))

    def test_the_default_mode_is_normal(self):
        """A build that forgets to say what it is must show the user nothing
        diagnostic, not a test pattern and a five-second pause."""
        s = read(MAIN)
        self.assertIn("#ifndef GBP_STARTUP_MODE", s)
        self.assertIn("#define GBP_STARTUP_MODE GBP_STARTUP_NORMAL", s)
        self.assertIn("STARTUP_MODE ?= GBP_STARTUP_NORMAL", read(MAKE))

    def test_the_diagnostic_build_is_reachable_from_the_makefile(self):
        mk = read(MAKE)
        self.assertIn("-DGBP_STARTUP_MODE=$(STARTUP_MODE)", mk)
        self.assertIn("GBP_STARTUP_DIAGNOSTIC", mk,
                      "the diagnostic image must remain buildable")


class TheNormalPathNeverWaitsForSeconds(unittest.TestCase):
    """§V5.52 hard guard. No intentional multi-second wait on the normal path."""

    def test_the_wait_comes_from_the_profile_and_not_from_a_literal(self):
        s = strip_comments(read(MAIN))
        self.assertIn("cfg.prehandler_wait_ms = startup.prehandler_wait_ms;", s)
        # exactly ONE assignment, and it is that one. The other reference is the
        # summary line that REPORTS the value, which is what a reader needs.
        self.assertEqual(len(re.findall(r"cfg\.prehandler_wait_ms\s*=", s)), 1)
        self.assertNotIn("cfg.prehandler_wait_ms = 5000", s)

    def test_the_five_second_value_lives_only_in_the_diagnostic_profile(self):
        """The wait's 5000 lives in the profile header and nowhere in main.c.
        §V5.55 introduced a SECOND 5000 in main.c -- STREAM_WIT_NOT_BEFORE_MS,
        the research witness eligibility threshold, which delays nothing the
        user sees -- so this guard names the thing it protects: no 5000 may
        reach a WAIT, and the eligibility constant may never be assigned to
        one either."""
        h = read(HDR)
        self.assertIn("#define GBP_STARTUP_DIAGNOSTIC_WAIT_MS 5000u", h)
        s = strip_comments(read(MAIN))
        others = s.replace("#define STREAM_WIT_NOT_BEFORE_MS 5000u", "")
        self.assertNotIn("5000", others, "a 5000 other than the witness threshold is in main.c")
        self.assertNotRegex(s, r"prehandler_wait_ms\s*=\s*(5000|STREAM_WIT_NOT_BEFORE_MS)")
        self.assertNotIn("VIDEO_WaitVSync", s[s.index("STREAM_WIT_NOT_BEFORE_MS"):s.index("STREAM_WIT_NOT_BEFORE_MS") + 400])

    def test_the_normal_profile_asks_for_zero(self):
        h = strip_comments(read(HDR))
        i_else = h.index("} else {")
        self.assertIn("s->prehandler_wait_ms = 0u;", h[i_else:])


class TheNormalPathNeverShowsSomethingSynthetic(unittest.TestCase):
    """§V5.52 hard guard. Nothing the GameCube invented may reach the VI."""

    def test_the_headless_submit_hands_over_no_framebuffer(self):
        body = strip_comments(func(read(MAIN), "selftest_submit_headless"))
        for forbidden in ("VIDEO_SetNextFramebuffer", "GX_CopyDisp",
                          "gbp_vpresent_xfb_target", "gbp_vpresent_xfb_handed"):
            self.assertNotIn(forbidden, body,
                             "the headless self-test grew a %r" % forbidden)

    def test_the_headless_submit_still_validates_the_path_it_exists_for(self):
        """Convert, upload, submit, draw, arm the token. Dropping any of these
        would make the normal build ship an unexercised display path again --
        which is the exact defect the self-test was created for (§V5.26.4)."""
        body = strip_comments(func(read(MAIN), "selftest_submit_headless"))
        for required in ("gbp_vpresent_submit(&present, buf)", "GX_InvalidateTexAll",
                         "GX_InitTexObj", "GX_LoadTexObj", "draw_quad();",
                         "GX_SetDrawDone();"):
            self.assertIn(required, body)

    def test_the_visible_path_is_gated_on_the_profile(self):
        body = strip_comments(func(read(MAIN), "display_selftest"))
        self.assertIn("if (startup.selftest_visible) {", body)
        self.assertIn("selftest_submit_headless(buf);", body)
        i_gate = body.index("if (startup.selftest_visible) {")
        i_submit = body.index("submit_ready(buf, 0);")
        i_headless = body.index("selftest_submit_headless(buf);")
        self.assertLess(i_gate, i_submit, "the visible present must be gated")
        self.assertLess(i_submit, i_headless, "headless is the else branch")

    def test_the_selftest_is_the_only_caller_of_submit_ready_with_no_account(self):
        s = strip_comments(read(MAIN))
        self.assertEqual(s.count("submit_ready(buf, 0);"), 1)

    def test_the_verdict_cannot_pass_without_the_profile_s_own_completion(self):
        """`selftest_released` is zero-safe -- nothing armed means nothing in
        flight. Each profile must prove its own path actually ran."""
        body = strip_comments(func(read(MAIN), "display_selftest"))
        self.assertIn("selftest_presents >= 1u", body)
        self.assertIn("selftest_headless >= 1u", body)
        self.assertIn("startup.selftest_visible ?", body)


class TheScreenIsBlackAndNotGarbage(unittest.TestCase):
    def test_both_stream_framebuffers_are_cleared_before_the_vi_sees_them(self):
        body = strip_comments(func(read(MAIN), "video_setup"))
        self.assertIn("VIDEO_ClearFrameBuffer(rmode, xfb_stream_buf[0], COLOR_BLACK);", body)
        self.assertIn("VIDEO_ClearFrameBuffer(rmode, xfb_stream_buf[1], COLOR_BLACK);", body)
        self.assertLess(body.index("VIDEO_ClearFrameBuffer"),
                        body.index("VIDEO_Configure(rmode);"),
                        "clear before the interface is configured")

    def test_the_clear_is_gated_on_the_profile_and_both_profiles_ask_for_it(self):
        self.assertIn("if (startup.clear_framebuffers) {",
                      strip_comments(func(read(MAIN), "video_setup")))
        h = strip_comments(read(HDR))
        self.assertEqual(h.count("s->clear_framebuffers = 1u;"), 2,
                         "neither profile benefits from showing memory garbage")


class PolicyAIsUntouched(unittest.TestCase):
    """§V5.52 changes startup scheduling. It may not touch the pacing policy."""

    def test_submit_ready_still_asks_the_framebuffer_question_first(self):
        body = strip_comments(func(read(MAIN), "submit_ready"))
        self.assertLess(body.index("gbp_vpresent_xfb_target(&present, cur);"),
                        body.index("if (!gbp_vpresent_submit(&present, buf))"))
        self.assertEqual(body.count("gbp_vpresent_xfb_target("), 1)
        self.assertIn("gbp_vdisp_defer(&disp, life, t_dec, rt, cur, pend,", body)

    def test_submit_ready_knows_nothing_about_the_startup_profile(self):
        """The one function Policy A lives in must not acquire a mode."""
        body = strip_comments(func(read(MAIN), "submit_ready"))
        self.assertNotIn("startup", body)

    def test_nothing_in_the_present_path_waits(self):
        s = strip_comments(read(MAIN))
        i_tgt = s.index("xfb = gbp_vpresent_xfb_target(&present, cur);")
        i_hand = s.index("gbp_vpresent_xfb_handed(&present, xfb);")
        for forbidden in ("VIDEO_WaitVSync", "while (", "for (", "usleep", "sleep"):
            self.assertNotIn(forbidden, s[i_tgt:i_hand])

    def test_the_headless_path_does_not_wait_either(self):
        body = strip_comments(func(read(MAIN), "selftest_submit_headless"))
        for forbidden in ("VIDEO_WaitVSync", "while (", "for (", "sleep"):
            self.assertNotIn(forbidden, body)

    def test_the_capture_hot_path_does_no_formatting_and_no_filesystem(self):
        """§V5.52 M15. `ringlog_printf` is bounded and in-memory, which is why
        every summary line uses it — but it FORMATS: varargs, integer to text,
        a scan of the format string. `submit_ready()` runs once per source
        frame and `pump()` about 224 000 times in a 35-second run, and this
        round added a startup trace whose natural home looks like exactly those
        functions. It is emitted once, after the teardown, and nothing of the
        kind may drift inwards.

        The mutation that found this gap inserted one `ringlog_printf` between
        `gbp_vpresent_inflight()` and `GX_CopyDisp()` and every other guard in
        the suite stayed green."""
        src = strip_comments(read(MAIN))
        for fn in ("submit_ready", "pump", "selftest_submit_headless",
                   "offer_oldest_ready", "on_draw_done"):
            body = func(src, fn)
            for forbidden in ("ringlog_printf", "printf", "snprintf", "sprintf",
                              "sdlog_", "fopen", "fwrite", "malloc", "free("):
                self.assertNotIn(forbidden, body,
                                 "%s() grew a %r in the capture path" % (fn, forbidden))

    def test_the_startup_trace_is_emitted_once_after_the_teardown(self):
        src = strip_comments(read(MAIN))
        self.assertEqual(src.count('"STARTUP mode=%s'), 1)
        self.assertEqual(src.count('"STARTUPT tb_hz=%lu'), 1)
        self.assertEqual(src.count('"STARTUPV have_first=%d'), 1)
        # after the probe returns, which is where every other summary line is
        self.assertLess(src.index("gbp_vstate_probe_run(&t, &rl, &cfg, &res);"),
                        src.index('"STARTUP mode=%s'))

    def test_the_counts_are_unchanged(self):
        s = read(os.path.join(ROOT, "src", "gbp", "gbp_vpresent.h"))
        self.assertIn("#define GBP_VPRESENT_XFB_BUFFERS 2", s)
        self.assertIn("#define GBP_VPRESENT_TEX_BUFFERS 2", s)


class TheSelfTestStillHasNoSourceIdentity(unittest.TestCase):
    def test_it_is_taken_with_the_sentinel_and_the_flag(self):
        s = strip_comments(read(MAIN))
        self.assertIn("gbp_vdisp_take(&disp, GBP_VDISP_KEY_NONE,", s)
        i = s.index("gbp_vdisp_take(&disp, GBP_VDISP_KEY_NONE,")
        self.assertIn("(uint16_t)buf, 0, 1);", s[i:i + 400])

    def test_the_headless_path_touches_no_scientific_counter(self):
        body = strip_comments(func(read(MAIN), "selftest_submit_headless"))
        self.assertNotIn("gbp_vqueue_note_presented", body)
        self.assertNotIn("&vq", body)


class TheStartupTraceReportsWhatActuallyHappened(unittest.TestCase):
    def test_it_reports_the_measured_counts_not_the_intention(self):
        s = strip_comments(read(MAIN))
        self.assertIn("presented_synthetic=%lu", s)
        self.assertIn("headless_submits=%lu", s)
        self.assertIn("selftest_presents", s)

    def test_it_records_the_first_real_handoff_against_the_control_transform(self):
        s = strip_comments(read(MAIN))
        self.assertIn("ticks_control_to_first_handoff=%llu", s)
        self.assertIn("res.t_control_transform", s)

    def test_the_first_real_lifecycle_excludes_the_selftest(self):
        s = strip_comments(read(MAIN))
        self.assertIn("(r->life_flags & GBP_VDISP_F_SELFTEST) == 0u", s)
        self.assertIn("r->frame_index != GBP_VDISP_KEY_NONE", s)

    def test_the_trace_does_no_filesystem_or_hot_path_work(self):
        """It runs once, after the teardown. `ringlog_printf` is the same
        bounded in-memory writer every other summary line uses."""
        s = strip_comments(read(MAIN))
        i = s.index('"STARTUP mode=%s')
        window = s[i:i + 3000]
        for forbidden in ("fopen", "fwrite", "sdlog_", "malloc", "VIDEO_WaitVSync"):
            self.assertNotIn(forbidden, window)


class TheStaleCounterCouplingIsCorrected(unittest.TestCase):
    """§V5.52. gbp_vqueue.h asserted `repeats = xfb_skipped`. Policy A makes
    that FALSE: run 6 measured repeats 0 against xfb_skipped 129."""

    def test_the_equality_survives_only_as_labelled_history(self):
        """The measurement was real and must not be erased -- `repeats = 12 =
        xfb_skipped` is what stream-0007 physically did. What must not survive
        is the claim that it is still TRUE. So the sentence stays, and it stays
        BELOW the line that says it stopped applying."""
        s = read(VQUEUE)
        self.assertIn("HISTORICAL FROM `stream-0008` ONWARD", s)
        self.assertIn("repeats = 12 = xfb_skipped", s)
        self.assertLess(s.index("HISTORICAL FROM `stream-0008` ONWARD"),
                        s.index("repeats = 12 = xfb_skipped"),
                        "the equality must be introduced as history, not asserted")
        self.assertIn("makes that equality FALSE", s)

    def test_it_says_what_xfb_skipped_means_under_policy_a(self):
        s = read(VQUEUE)
        self.assertIn("DEFER ATTEMPTS", s)
        self.assertIn("GBP-HW-207", s)
        self.assertIn("neither source loss nor a display-repeat count", s)

    def test_the_runtime_still_does_not_call_it(self):
        s = strip_comments(read(MAIN))
        self.assertNotIn("gbp_vqueue_note_repeat", s)


if __name__ == "__main__":
    unittest.main()
