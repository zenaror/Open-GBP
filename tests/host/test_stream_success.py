"""
tests/host/test_stream_success.py — F5 (HARDWARE_TESTS §V5.59): the indexed
stream experiment has exactly ONE success condition, the witness target.

The generic vstate time target (cfg.min_valid_observation_*) used to be armed
at 30 s as a second nominal success. Under OGBPIDX1 no baseline can form, so it
was unreachable — but "unreachable" is not "disarmed". It is now DISABLED by
name (gbp_vstate_probe.h), the safety cap is untouched, and the eligibility
threshold, the qualification length and the witness target are unchanged.
"""
import os
import re
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "source", "main.c")
HDR = os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.h")
PROBE_C = os.path.join(ROOT, "src", "gbp", "gbp_vstate_probe.c")
MAKEFILE = os.path.join(ROOT, "poc", "gbp-video-stream-probe", "Makefile")
UNIT = os.path.join(ROOT, "tests", "unit", "test_gbp_video_state.c")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def strip(code):
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return re.sub(r"//[^\n]*", "", code)


class ExactlyOneSuccessCondition(unittest.TestCase):
    def test_the_time_target_is_disabled_by_name_after_the_timebase_pass(self):
        s = strip(read(MAIN))
        self.assertIn("gbp_vstate_config_disable_time_target(&cfg);", s)
        self.assertLess(s.index("gbp_vstate_config_timebase(&cfg, tb_hz);"), s.index("gbp_vstate_config_disable_time_target(&cfg);"))
        self.assertNotRegex(s, r"cfg\.min_valid_observation_(s|ticks)\s*=")

    def test_the_provisional_capture_duration_is_gone(self):
        code = read(MAIN)
        self.assertNotIn("STREAM_CAPTURE_SECONDS", code)
        self.assertNotIn("PROVISIONAL", code)
        self.assertNotIn("DESIGN DECISION REQUIRED", code)
        self.assertIn("time_target=disabled", strip(code))
        self.assertNotIn("capture_s=", strip(code))
        self.assertIn("§V5.59", code)

    def test_the_named_constants_have_the_documented_semantics(self):
        h = read(HDR)
        self.assertIn("#define GBP_VSTATE_MIN_VALID_OBSERVATION_DISABLED_S     0u", h)
        self.assertIn("#define GBP_VSTATE_MIN_VALID_OBSERVATION_DISABLED_TICKS UINT64_MAX", h)
        self.assertIn("static inline void gbp_vstate_config_disable_time_target(struct gbp_vstate_config *cfg)", h)
        self.assertIn("static inline int gbp_vstate_config_time_target_disabled(const struct gbp_vstate_config *cfg)", h)
        self.assertIn("never a success", h)
        # the generic probe still compares with >= against the ticks: UINT64_MAX is unreachable by construction
        self.assertIn("st->valid_observation_elapsed >= cfg->min_valid_observation_ticks", strip(read(PROBE_C)))
        # and the generic defaults other POCs use did not move
        self.assertIn("#define GBP_VSTATE_MIN_VALID_OBSERVATION_SECONDS 120u", h)
        self.assertIn("#define GBP_VSTATE_HARD_WALLCLOCK_LIMIT_SECONDS  180u", h)

    def test_the_c_suite_proves_the_disabled_target_never_fires(self):
        u = read(UNIT)
        self.assertIn("test_time_target_disabled_never_fires();", u)
        self.assertIn("CHECK(res.stop != GBP_VSTATE_STOP_NOMINAL_NEGATIVE);", u)
        self.assertIn("CHECK(res.valid_observation_at_target == 0u);", u)


class WhatDidNotChange(unittest.TestCase):
    def test_the_safety_cap_is_still_armed_and_still_60_s(self):
        s = strip(read(MAIN))
        self.assertIn("#define STREAM_SAFETY_SECONDS    60u", read(MAIN))
        self.assertIn("cfg.hard_wallclock_s = STREAM_SAFETY_SECONDS;", s)
        self.assertIn("cfg.hard_wallclock_ticks = (uint64_t)tb_hz * STREAM_SAFETY_SECONDS;", s)

    def test_eligibility_qualification_and_target_are_unchanged(self):
        s = strip(read(MAIN))
        self.assertIn("#define STREAM_WIT_NOT_BEFORE_MS 5000u", read(MAIN))
        self.assertIn("gbp_vwitness_set_qualification(&wit, GBP_VWITNESS_QUAL_REQUIRED);", s)
        self.assertIn("GBP_VWITNESS_TARGET, GBP_VWITNESS_TARGET", s)
        self.assertRegex(read(os.path.join(ROOT, "src/gbp/gbp_vwitness.h")), r"#define GBP_VWITNESS_QUAL_REQUIRED\s+64u")
        self.assertRegex(read(os.path.join(ROOT, "src", "gbp", "gbp_vwitness.h")), r"#define GBP_VWITNESS_TARGET\s+2048u")

    def test_the_build_identity_moved_and_says_so(self):
        m = read(MAKEFILE)
        self.assertIn("BUILD_ID   := stream-0012", m)
        self.assertNotIn("BUILD_ID   := stream-0011", m)
        self.assertIn("NOT\n# PHYSICALLY EXECUTED", m)


if __name__ == "__main__":
    unittest.main()
