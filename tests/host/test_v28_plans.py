"""tests/host/test_v28_plans.py -- src/audio/gbp_v28_plans.h against tools/v28budget.py's own
PLANS table (GitHub Issue #129, the Orchestrator's architecture review point 3: "one source for
the plans, shared with tools/v28budget.py ... with a test that they agree, so a later edit can't
let them drift apart").

tools/v28budget.py's own PLANS dict is imported directly (not re-parsed from its text) and
compared field by field against the C header, parsed from its own source. Neither file is
treated as the source of truth over the other -- this test is what keeps them equal.
"""
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v28budget  # noqa: E402
import hostcc  # noqa: E402

AUDIO = os.path.join(ROOT, "src", "audio")
PLANS_H = os.path.join(AUDIO, "gbp_v28_plans.h")

# tools/v28budget.py's own phase-name strings -> the C enum tokens gbp_walker.h declares.
PHASE_KIND_C_NAME = {
    "p0": "GBP_WALKER_NAVIGATE",
    "3a": "GBP_WALKER_DESCENT_3A",
    "3b": "GBP_WALKER_HOLD_3B",
    "sweep": "GBP_WALKER_SWEEP",
    "nulling": "GBP_WALKER_NULLING",
}

# tools/v28budget.py's own name -> this header's own array/plan names.
PLAN_C_NAME = {
    "validation_run": "GBP_V28_VALIDATION_RUN",
    "perceptual_no_phase1": "GBP_V28_PERCEPTUAL_NO_PHASE1",
    "diag_3a_stall": "GBP_V28_DIAG_3A_STALL",
}

MAIN = os.path.join(ROOT, "poc", "gbp-audio-v28", "source", "main.c")

# Issue #131/#133 (RUN 50, Defect A): the ONE place every handler start is now issued from,
# driven off the walker's own phase index advancing -- never a specific handler's own completion
# flag or a specific caller. See its own header comment in main.c for the full reasoning.
DISPATCH_FN = "v28_dispatch_phase_start"

# GBP_WALKER_* kind -> the module-level function that must actually be CALLED (never merely
# declared) somewhere main.c can reach, before that phase's own tick()/step() does anything real.
# GBP_WALKER_NAVIGATE is deliberately absent: it has no separate handler struct of its own (it is
# the walker's own phase 0), so there is nothing to start.
KIND_START_FN = {
    "GBP_WALKER_DESCENT_3A": "gbp_v28_3a_start",
    "GBP_WALKER_HOLD_3B": "gbp_v28_3b_start",
    "GBP_WALKER_SWEEP": "gbp_v28_sweep_start",
    "GBP_WALKER_NULLING": "gbp_v28_nulling_start",
}


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def code(src):
    return re.sub(r"/\*.*?\*/|//[^\n]*", " ", src, flags=re.S)


def python_plan(name):
    """(phase_names, seconds, session_cap) for a v28budget.py plan whose every phase has an
    explicit (non-None) duration -- true of validation_run and perceptual_no_phase1, so no RUN 43
    fixture is needed to resolve a `None` entry."""
    rows, cap = v28budget.PLANS[name]
    names = [p for p, s, _what in rows]
    secs = [s for _p, s, _what in rows]
    if any(s is None for s in secs):
        raise AssertionError("%s has a None-duration phase; this test only handles plans that don't" % name)
    total = sum(secs)
    if cap is None:
        import math
        cap = int(math.ceil(total + v28budget.SLACK_S))
    return names, secs, cap


def c_plan_array(header, array_name):
    """[(kind_token, cap_s), ...] for a GBP_V28_..._PHASES[] array, in declared order."""
    m = re.search(r"static const struct gbp_walker_phase_def %s\[\d+\] = \{(.*?)\};" % re.escape(array_name),
                  header, re.S)
    if not m:
        raise AssertionError("%s not found in gbp_v28_plans.h" % array_name)
    body = m.group(1)
    return re.findall(r"\{\s*(GBP_WALKER_\w+)\s*,\s*([\w()+]+)\s*\}", body)


def function_body(src, name):
    """The DEFINITION's own body text -- `{...}` matched by brace depth, starting at the first
    `name(...)\\n{` in `src` (a forward declaration with no body, `name(...);`, never matches this
    pattern, so a name declared earlier in the file cannot be mistaken for its own definition)."""
    m = re.search(r"\b%s\s*\([^\n;]*\)\s*\n\{" % re.escape(name), src)
    if not m:
        raise AssertionError("%s's own definition was not found in main.c" % name)
    i = m.end() - 1   # at the opening brace
    depth = 0
    j = i
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    raise AssertionError("%s's own body never closes its opening brace" % name)


def c_macro_value(header, name, seen=None):
    """Resolves a #define, recursively substituting any GBP_V28_* macro names its own expression
    references, then evaluates the resulting integer arithmetic."""
    seen = set(seen or ())
    if name in seen:
        raise AssertionError("macro cycle at %s" % name)
    seen.add(name)
    m = re.search(r"#define\s+%s\s+\(([^)]*)\)" % re.escape(name), header)
    if m:
        expr = m.group(1)
    else:
        m = re.search(r"#define\s+%s\s+(\S+)" % re.escape(name), header)
        if not m:
            raise AssertionError("%s not defined in gbp_v28_plans.h" % name)
        expr = m.group(1)

    def repl(mo):
        n = mo.group(0)
        return "(%d)" % c_macro_value(header, n, seen) if n != name and re.search(r"#define\s+%s\s" % re.escape(n),
                                                                                   header) else n

    expr = re.sub(r"\bGBP_V28_\w+\b", repl, expr)
    expr = expr.replace("u", "").replace("U", "")
    return eval(expr, {"__builtins__": {}}, {})  # noqa: S307 -- fixed-format integer macro arithmetic only


class TheTwoPlansAgreeWithVBudget(unittest.TestCase):
    def test_every_v28budget_plan_this_header_claims_is_present(self):
        header = code(read(PLANS_H))
        for py_name, c_name in PLAN_C_NAME.items():
            self.assertIn(py_name, v28budget.PLANS, "%s is missing from tools/v28budget.py's own PLANS" % py_name)
            self.assertIn(c_name, header, "%s is missing from gbp_v28_plans.h" % c_name)

    def test_phase_names_order_and_seconds_match(self):
        header = code(read(PLANS_H))
        for py_name, c_name in PLAN_C_NAME.items():
            py_names, py_secs, _py_cap = python_plan(py_name)
            c_entries = c_plan_array(header, c_name + "_PHASES")
            self.assertEqual(len(c_entries), len(py_names),
                              "%s: phase count differs (py %d, C %d)" % (py_name, len(py_names), len(c_entries)))
            for (py_n, py_s, (c_kind, c_cap_expr)) in zip(py_names, py_secs, c_entries):
                self.assertEqual(PHASE_KIND_C_NAME.get(py_n), c_kind,
                                  "%s: phase %r maps to %r in C, not %r" % (py_name, py_n, c_kind,
                                                                            PHASE_KIND_C_NAME.get(py_n)))
                if re.fullmatch(r"\d+[uU]?", c_cap_expr):
                    c_cap = int(c_cap_expr.rstrip("uU"))
                else:
                    c_cap = c_macro_value(header, c_cap_expr)
                self.assertEqual(c_cap, py_s, "%s: phase %r's seconds differ (py %d, C %d)" %
                                  (py_name, py_n, py_s, c_cap))

    def test_session_cap_matches(self):
        header = code(read(PLANS_H))
        for py_name, c_name in PLAN_C_NAME.items():
            _py_names, _py_secs, py_cap = python_plan(py_name)
            c_cap = c_macro_value(header, c_name + "_CAP_S")
            self.assertEqual(c_cap, py_cap, "%s: session cap differs (py %d, C %d)" % (py_name, py_cap, c_cap))

    def test_p0_allowance_and_slack_match(self):
        header = code(read(PLANS_H))
        self.assertEqual(c_macro_value(header, "GBP_V28_P0_ALLOWANCE_S"), v28budget.P0_ALLOWANCE_S)
        self.assertEqual(c_macro_value(header, "GBP_V28_SLACK_S"), v28budget.SLACK_S)

    def test_phase_1_is_in_neither_plan(self):
        for py_name in PLAN_C_NAME:
            names, _secs, _cap = python_plan(py_name)
            self.assertNotIn("p1", names, "%s must not carry Phase 1 (#128 §2 point 3)" % py_name)


class TheHandlersAreStarted(unittest.TestCase):
    """Issue #131: `gbp_v28_3a_start()` was never called anywhere in main.c -- 3a sat at its
    static zero-init state for its entire phase, tick() fell through every call, and the phase
    only ever ended via the walker's own timeout. Checking what a general version of this test
    would find, before writing it, turned up the SAME gap for `gbp_v28_sweep_start()` and
    `gbp_v28_nulling_start()` -- no handler in this POC was ever started (the Orchestrator's own
    words). Driven from the shared plans table, with no exemption list: a plan or handler added
    later is checked the same way automatically, and this file does not get to decide any handler
    is allowed to stay broken.

    THE CLASS OF BUG THIS FIXES: tests/unit/test_v28_zero_feed_integration.c's own harness
    reproduced "main.c's own DESCENT_3A wiring call-for-call" and passed -- because it called
    start() itself, modelling the wiring as INTENDED rather than as WRITTEN. That is the same
    shape as a test that agrees with the bug: the harness and the buggy code shared an
    assumption, so the harness could not see the gap. Grepping the REAL main.c is what breaks
    that symmetry -- main.c cannot be compiled or driven on the host, so this is the only way to
    check what it actually does, the same shape test_v28_anchor_wiring.py already established."""

    def test_every_handler_a_plan_uses_is_actually_started(self):
        src = read(MAIN)
        header = code(read(PLANS_H))
        needed = set()
        for py_name, c_name in PLAN_C_NAME.items():
            for kind_token, _cap_expr in c_plan_array(header, c_name + "_PHASES"):
                if kind_token in KIND_START_FN:
                    needed.add(KIND_START_FN[kind_token])
        self.assertTrue(needed, "no handler kind to check -- the population went silently empty")
        for fn in sorted(needed):
            calls = re.findall(r"\b%s\s*\(" % re.escape(fn), src)
            self.assertGreater(len(calls), 0,
                               "%s is declared but never called anywhere in main.c -- its own "
                               "handler struct stays at its static zero-init state for its "
                               "entire phase" % fn)

    def test_every_handler_start_has_exactly_one_call_site_and_it_is_in_the_shared_dispatcher(self):
        """RUN 50 (Issue #133): `gbp_v28_3b_start()` WAS called somewhere in main.c -- the previous
        test above would have passed -- but only inside DESCENT_3A's own `TICK_PHASE_COMPLETE`
        branch, reachable when 3a's own algorithm decided it was done and UNREACHABLE when the
        walker's own phase cap cut 3a instead, which is exactly what happened. "A start reachable
        on only one of two exit paths is the same shape as a start reachable on no path" (the
        Orchestrator's own framing) -- the general, durable form of this lesson: a handler start
        must have EXACTLY ONE call site in main.c, and that call site must sit inside
        v28_dispatch_phase_start(), the one place driven off the walker's own index advancing
        rather than any specific exit reason. A second call site (even a correct-looking one)
        risks a double start -- gbp_v28_3a_start()/gbp_v28_3b_start()/gbp_v28_sweep_start() all
        memset() their own struct, so calling one twice for the same phase would silently wipe
        real progress -- so "more than one" fails this exactly as hard as "none"."""
        src = read(MAIN)
        header = code(read(PLANS_H))
        needed = set()
        for py_name, c_name in PLAN_C_NAME.items():
            for kind_token, _cap_expr in c_plan_array(header, c_name + "_PHASES"):
                if kind_token in KIND_START_FN:
                    needed.add(KIND_START_FN[kind_token])
        self.assertTrue(needed, "no handler kind to check -- the population went silently empty")
        stripped = code(src)   # comments stripped: a call-site count must not be inflated by a
                                # doc comment that merely MENTIONS a function's own name in prose
        dispatcher = function_body(stripped, DISPATCH_FN)
        for fn in sorted(needed):
            pat = r"\b%s\s*\(" % re.escape(fn)
            calls = re.findall(pat, stripped)
            self.assertEqual(len(calls), 1,
                             "%s has %d call sites in main.c, not exactly 1 -- a start reachable "
                             "on more than one path (or none) risks the same defect RUN 50 found, "
                             "in one direction or the other" % (fn, len(calls)))
            self.assertRegex(dispatcher, pat,
                             "%s's own one call site is not inside %s() -- it is reachable only "
                             "from whatever OTHER path calls it, the exact shape RUN 50 found for "
                             "gbp_v28_3b_start()" % (fn, DISPATCH_FN))


class TheMakefileCleanTarget(unittest.TestCase):
    """Issue #131: `make clean` for gbp-audio-v28 removed the wrong set of plan directories --
    its own `clean:` target hardcoded validation_run and perceptual_no_phase1 and had never heard
    of diag_3a_stall, so `make PLAN=diag_3a_stall clean; make PLAN=diag_3a_stall` silently relinked
    a STALE cached build (the commit string embedded in it never advanced past an old dirty
    build), the same "a routine command whose safety depends on state nothing checks" class this
    project has hit before (RUN 43's own staging incident, `docs/research/DEVLOG.md`). Driven from
    PLAN_C_NAME, not a hardcoded list, so a fourth plan is caught the same way automatically."""

    def test_clean_removes_every_plan_this_header_knows_about(self):
        mk = os.path.join(ROOT, "poc", "gbp-audio-v28", "Makefile")
        with open(mk, encoding="utf-8") as f:
            text = f.read()
        m = re.search(r"^clean:\n(?:.*\n)*?\t@rm -rf ((?:[^\n]*\\\n)*[^\n]*)", text, re.M)
        self.assertIsNotNone(m, "clean: target's own rm -rf line could not be found")
        rm_line = re.sub(r"\\\n\s*", " ", m.group(1))
        for plan_name in v28budget.PLANS:
            if plan_name not in PLAN_C_NAME:
                continue          # not a real gbp-audio-v28 build (v27_as_frozen etc.), no directory to clean
            self.assertIn("$(APP_NAME)-%s" % plan_name, rm_line,
                          "clean: does not remove %s's own build directory" % plan_name)


class TheHeaderBuilds(unittest.TestCase):
    def test_the_plans_header_itself_builds(self):
        src = '#include "gbp_v28_plans.h"\nint main(void) { return (int)GBP_V28_VALIDATION_RUN.count; }\n'
        with tempfile.TemporaryDirectory() as d:
            srcfile = os.path.join(d, "ok.c")
            with open(srcfile, "w", encoding="utf-8") as f:
                f.write(src)
            exe = os.path.join(d, "ok")
            have, ok, err = hostcc.compile_c(["-std=gnu11", "-Wall", "-Wextra", "-I", AUDIO, "-o", exe, srcfile])
            hostcc.require(self, have, ok, err, what="gbp_v28_plans.h")


if __name__ == "__main__":
    unittest.main()
