"""tests/host/test_v28_leak.py -- GitHub Issue #128 section 7 / Amendment C: the perceptual image
compiles the leak-prone fields OUT at build time (GBP_V28_PLAN_PERCEPTUAL), rather than hiding them
at runtime. This proves it statically: the text this build's preprocessor branch would ACTUALLY
compile can never contain a NEVER field, because that text is never even parsed by the compiler
under the other plan -- a stronger guarantee than a runtime `if`, and provable without a build.

Amendment C (universal, no exemption, BOTH images): depths/plans/acted are never checked here
because they must never appear in EITHER plan's screen/live functions at all -- see
test_no_amendment_c_field_anywhere_in_the_report_functions below.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

MAIN = os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")

# Issue #128 section 7's own NEVER list, in the perceptual run: accepted step counts, plans, acted,
# C-stick event counts, refusal/busy counters, any visible LEFT/RIGHT response, his answers (which
# stick direction is deeper, p2_dir), the TARGET/AHEAD in force or anything read from
# gbp_atrans2/gbp_aplay2/gbp_adec2, or the target/fill rows.
NEVER = (
    r"cs_events", r"cs_acted", r"\bacted\b", r"\bplans\b", r"depths",
    r"refused_step", r"cs_busy", r"refused_confirm", r"refused_step_busy", r"refused_step_end",
    r"nulling\.steps\b", r"nulling\.steps_deeper", r"nulling\.steps_shallower", r"nulling\.target",
    r"p2_dir", r"\btarget\b", r"\bahead\b", r"\bap2\.", r"\badec2\.", r"\btr\.",
    r"GBP_V28_NULLING_LEFT", r"GBP_V28_NULLING_RIGHT",
)

# Amendment C, universal: these three must never appear in EITHER plan's screen/live report.
AMENDMENT_C = (r"\bdepths\b", r"\bplans\b", r"\bacted\b")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def functions(src):
    """name -> body text of every top-level `static ... name(...) {...}` in a C file."""
    out = {}
    for m in re.finditer(r"^(?:static\s+)?(?:const\s+)?(?:inline\s+)?[A-Za-z_][\w \t\*]*?\b(\w+)\s*\([^\n;{]*\)\s*\n\{",
                         src, re.M):
        name = m.group(1)
        i = m.end()
        depth = 1
        while depth and i < len(src):
            c = src[i]
            depth += (c == "{") - (c == "}")
            i += 1
        out[name] = src[m.start():i]
    return out


def perceptual_branch(body):
    """The text a build with GBP_V28_PLAN_PERCEPTUAL defined would ACTUALLY compile from one
    `#if defined(GBP_V28_PLAN_PERCEPTUAL) ... #else ... #endif` block (not nested, as this file
    writes them): the segment between the #if and the #else. Concatenates every such block found in
    `body`, plus whatever text sits outside any #if/#else/#endif block entirely (unconditional, so
    it compiles into both plans)."""
    out = []
    i = 0
    pattern = re.compile(r"#if\s+defined\(GBP_V28_PLAN_PERCEPTUAL\)\n(.*?)#else\n(.*?)#endif\n", re.S)
    last = 0
    for m in pattern.finditer(body):
        out.append(body[last:m.start()])   # unconditional text before this block
        out.append(m.group(1))             # the PERCEPTUAL branch only -- never group(2), the validation one
        last = m.end()
    out.append(body[last:])
    return "".join(out)


class TheLeakRule(unittest.TestCase):
    def test_no_never_field_in_the_perceptual_screen_report(self):
        fs = functions(read(MAIN))
        branch = perceptual_branch(fs["v28_screen_report"])
        for pat in NEVER:
            self.assertIsNone(re.search(pat, branch), "v28_screen_report (perceptual branch): a %r leak" % pat)

    def test_no_never_field_in_the_perceptual_live_report(self):
        fs = functions(read(MAIN))
        branch = perceptual_branch(fs["v28_live_report"])
        for pat in NEVER:
            self.assertIsNone(re.search(pat, branch), "v28_live_report (perceptual branch): a %r leak" % pat)

    def test_the_perceptual_branch_is_actually_narrower_than_the_full_function(self):
        """A sanity check on the extractor itself: if the #if/#else split were mis-parsed and
        `perceptual_branch` silently returned the WHOLE function (validation branch included), the
        two tests above would still pass vacuously (the validation branch here never contains a
        NEVER pattern outside the phase index, which does not match NEVER). Confirm the extractor
        actually drops text: the validation-only line naming the phase count must NOT survive."""
        fs = functions(read(MAIN))
        full = fs["v28_screen_report"]
        branch = perceptual_branch(full)
        self.assertIn("V28_PLAN->count", full)
        self.assertNotIn("V28_PLAN->count", branch)

    def test_settings_n_is_the_one_safe_nulling_figure(self):
        """Issue #128 section 7's own SAFE line: "setting k" when settings_n changes -- confirm this
        is what the perceptual branch actually shows, not silently dropped along with everything else."""
        fs = functions(read(MAIN))
        branch = perceptual_branch(fs["v28_screen_report"])
        self.assertIn("nulling.settings_n", branch)

    def test_no_amendment_c_field_anywhere_in_the_report_functions(self):
        """Amendment C: depths/plans/acted are dropped UNIVERSALLY -- both plans, no exemption. Checked
        against the WHOLE function text (not just the perceptual branch), since validation_run may show
        anything else, but not these three."""
        fs = functions(read(MAIN))
        for name in ("v28_screen_report", "v28_live_report"):
            for pat in AMENDMENT_C:
                self.assertIsNone(re.search(pat, fs[name]), "%s: Amendment C field %r present" % (name, pat))

    def test_v28_control_never_prints_or_gecko_puts(self):
        """cs_events/cs_acted/p2_dir/step responses are computed in v28_control(); the leak rule is
        satisfied only if that function itself never reaches the screen or the live channel."""
        fs = functions(read(MAIN))
        body = fs["v28_control"].replace("ringlog_printf(", "")
        self.assertNotIn("printf(", body)
        self.assertNotIn("gecko_puts(", body)


if __name__ == "__main__":
    unittest.main()
