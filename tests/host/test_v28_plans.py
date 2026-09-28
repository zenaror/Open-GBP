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
