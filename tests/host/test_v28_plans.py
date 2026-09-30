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
    "loss": "GBP_WALKER_LOSS",
    "play": "GBP_WALKER_PLAY",
}

# tools/v28budget.py's own name -> this header's own array/plan names.
PLAN_C_NAME = {
    "validation_run": "GBP_V28_VALIDATION_RUN",
    "perceptual_no_phase1": "GBP_V28_PERCEPTUAL_NO_PHASE1",
    "diag_3a_stall": "GBP_V28_DIAG_3A_STALL",
    "diag_loss": "GBP_V28_DIAG_LOSS",
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
    "GBP_WALKER_LOSS": "gbp_v28_loss_start",
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


class ThePlayPlanAgreesWithVBudget(unittest.TestCase):
    """Issue #153 (HARDWARE_TESTS.md V31.1/V31.2): the play plan is checked against tools/v28budget.py the same way, but it is NOT a gbp-audio-v28 build (the play image is poc/gbp-play-gba,
    a separate POC), so it stays out of PLAN_C_NAME -- which also drives the V28 Makefile's clean-target test and the V28 handler-start tests, neither of which concerns it. GBP_WALKER_PLAY has no
    handler: there is nothing in KIND_START_FN for it, and the play image starts none."""

    def test_the_phases_the_seconds_and_the_cap_agree(self):
        header = code(read(PLANS_H))
        names, secs, cap = python_plan("play_gba")
        entries = c_plan_array(header, "GBP_V28_PLAY_GBA_PHASES")
        self.assertEqual([PHASE_KIND_C_NAME[n] for n in names], [k for k, _c in entries])
        self.assertEqual(names, ["p0", "play"])
        caps = [c_macro_value(header, c) if not re.fullmatch(r"\d+[uU]?", c) else int(c.rstrip("uU")) for _k, c in entries]
        self.assertEqual(caps, secs)
        self.assertEqual(secs, [60, 300])
        self.assertEqual(c_macro_value(header, "GBP_V28_PLAY_GBA_CAP_S"), cap)
        self.assertEqual(cap, 420)
        self.assertEqual(cap + v28budget.WALL_ABOVE_SESSION_S, 485)

    def test_the_play_kind_is_appended_and_no_kind_was_renumbered(self):
        h = read(os.path.join(AUDIO, "gbp_walker.h"))
        order = re.findall(r"^\s+(GBP_WALKER_\w+)", h[h.index("enum gbp_walker_kind"):h.index("enum gbp_walker_end_reason")], re.M)
        self.assertEqual(order, ["GBP_WALKER_NAVIGATE", "GBP_WALKER_DESCENT_3A", "GBP_WALKER_HOLD_3B", "GBP_WALKER_SWEEP", "GBP_WALKER_NULLING", "GBP_WALKER_LOSS", "GBP_WALKER_PLAY"],
                         "the executed images' kinds keep their values; PLAY is appended")

    def test_no_handler_is_named_for_play(self):
        self.assertNotIn("GBP_WALKER_PLAY", KIND_START_FN)
        self.assertNotIn("play_gba", PLAN_C_NAME)


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


# Issue #137 (the third growth of this structural test): what a handler header ASKS THE CALLER to call is a
# contract, and the contract is derived from the headers, not from a list kept here. Every public function of a
# handler header whose name ends in one of these suffixes is one the caller must call: `_start` (begin the phase),
# `_done` (a dwell/hold/depth ended: `depth_done`, `hold_done`), `_cut` (the walker cut the phase), and
# `_underrun_observed` (the caller saw the AI underrun counter rise). RUN 53 showed the class again after #131: both
# `_underrun_observed` hooks had no caller, so every "clean" hold was UNOBSERVED, and no test existed that could say so.
HANDLER_HEADERS = ("gbp_v28_3a.h", "gbp_v28_3b.h", "gbp_v28_sweep.h", "gbp_v28_nulling.h", "gbp_v28_loss.h")
CONTRACT_SUFFIXES = ("_start", "_done", "_cut", "_underrun_observed")


def strip_for_calls(src):
    """Comments, string and character literals and `#if 0` blocks removed (line structure kept): none of them is a call."""
    src = re.sub(r"/\*.*?\*/|//[^\n]*", lambda m: "\n" * m.group(0).count("\n"), src, flags=re.S)
    src = re.sub(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', '""', src)
    out, depth, skipping = [], 0, False
    for line in src.split("\n"):
        t = line.strip()
        if skipping:
            if re.match(r"#\s*if", t):
                depth += 1
            elif re.match(r"#\s*endif", t):
                depth -= 1
                if depth == 0:
                    skipping = False
            elif depth == 1 and re.match(r"#\s*(else|elif)\b", t):
                skipping = False
            out.append("")
            continue
        if re.match(r"#\s*if\s+0\b", t):
            skipping, depth = True, 1
            out.append("")
            continue
        out.append(line)
    return "\n".join(out)


def contract_functions(header_text):
    """Every function a header declares whose name ends in a contract suffix: any `gbp_...(` (whatever its column, whatever precedes
    it, on its own line or not) and any function-pointer member `(*gbp_...)`, macros excluded; comments already stripped."""
    text = "\n".join(l for l in header_text.split("\n") if not re.match(r"\s*#\s*define\b", l))
    names = set(re.findall(r"\b(gbp_\w+)\s*\(", text)) | set(re.findall(r"\(\s*\*\s*(gbp_\w+)\s*\)", text))
    return sorted(n for n in names if n.endswith(CONTRACT_SUFFIXES))


_NOT_FUNCTIONS = {"if", "for", "while", "switch", "return", "sizeof", "else", "do"}


def function_defs(src):
    """{name: body text} of every function DEFINED at column 0 of `src` (comments/literals already stripped), by brace matching."""
    defs = {}
    pat = re.compile(r"^(?![#\s])[A-Za-z_][\w \t\*]*?\b([A-Za-z_]\w*)\s*\((?:[^;{}()]|\([^()]*\))*\)\s*\n?\s*\{", re.M)
    for m in pat.finditer(src):
        name = m.group(1)
        if name in _NOT_FUNCTIONS:
            continue
        i = m.end() - 1
        depth = 0
        for j in range(i, len(src)):
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    defs[name] = src[i:j + 1]
                    break
    return defs


def reachable_functions(defs, root="main"):
    """Functions reachable from `root` by naming: a call, or a function's address taken (a callback assigned or registered)."""
    seen, todo = set(), [root]
    while todo:
        f = todo.pop()
        if f in seen or f not in defs:
            continue
        seen.add(f)
        for ident in set(re.findall(r"\b[A-Za-z_]\w*\b", defs[f])):
            if ident in defs and ident not in seen:
                todo.append(ident)
    return seen


def contract_callers(main_src, names):
    """{name: number of call sites in main.c that are REACHABLE: inside a function main() can get to, by call or by address taken}."""
    stripped = strip_for_calls(main_src)
    defs = function_defs(stripped)
    live = reachable_functions(defs)
    return dict((n, sum(len(re.findall(r"\b%s\s*\(" % re.escape(n), defs[f])) for f in live)) for n in names)


class TheContractCallsAreMade(unittest.TestCase):
    """No exemption list: a function a handler header names by the contract's suffixes needs a caller in main.c."""

    def population(self):
        pop = {}
        for h in HANDLER_HEADERS:
            pop[h] = contract_functions(code(read(os.path.join(AUDIO, h))))
        return pop

    def test_the_population_is_not_silently_empty(self):
        pop = self.population()
        for h, names in pop.items():
            self.assertTrue(names, "%s yielded no contract function: the parser or the header changed" % h)
        every = [n for names in pop.values() for n in names]
        for suffix in CONTRACT_SUFFIXES:
            self.assertTrue(any(n.endswith(suffix) for n in every), "no header declares a %s function" % suffix)
        for known in ("gbp_v28_3a_start", "gbp_v28_3a_depth_done", "gbp_v28_3a_cut", "gbp_v28_3a_underrun_observed",
                      "gbp_v28_3b_hold_done", "gbp_v28_3b_underrun_observed", "gbp_v28_sweep_cut",
                      "gbp_v28_nulling_start"):
            self.assertIn(known, every)

    def test_every_contract_function_has_a_caller_in_main_c(self):
        src = read(MAIN)
        for h, names in self.population().items():
            for n, calls in contract_callers(src, names).items():
                self.assertGreater(calls, 0, "%s (declared in %s, a function its header asks the caller to call) has "
                                             "no caller in main.c" % (n, h))

    def test_the_parser_finds_a_declaration_however_it_is_written(self):
        header = "void\ngbp_b_start(int);\n  void gbp_c_done(int);\nstruct x { void (*gbp_d_cut)(int); };\n" \
                 "#define gbp_e_start(x) 0\nint gbp_f_tick(int);\nvoid gbp_g_underrun_observed(struct s *, uint64_t);\n"
        self.assertEqual(contract_functions(header),
                         ["gbp_b_start", "gbp_c_done", "gbp_d_cut", "gbp_g_underrun_observed"])

    def test_a_call_that_main_cannot_reach_does_not_count(self):
        live = "static void a(void) { gbp_x_start(1); }\nint main(void)\n{\n    a();\n    return 0;\n}\n"
        dead = "static void a(void) { gbp_x_start(1); }\nint main(void)\n{\n    return 0;\n}\n"
        self.assertEqual(contract_callers(live, ["gbp_x_start"]), {"gbp_x_start": 1})
        self.assertEqual(contract_callers(dead, ["gbp_x_start"]), {"gbp_x_start": 0}, "a dead static function is not a caller")
        cb = "static void a(void) { gbp_x_start(1); }\nint main(void)\n{\n    cfg.cb = a;\n    return 0;\n}\n"
        self.assertEqual(contract_callers(cb, ["gbp_x_start"]), {"gbp_x_start": 1}, "a callback whose address is taken is reachable")

    def test_a_string_a_comment_and_an_if_zero_block_are_not_calls(self):
        src = ('int main(void)\n{\n    puts("gbp_x_start(1)");\n    /* gbp_x_start(2); */\n    // gbp_x_start(3);\n'
               '#if 0\n    gbp_x_start(4);\n#endif\n    return 0;\n}\n')
        self.assertEqual(contract_callers(src, ["gbp_x_start"]), {"gbp_x_start": 0})
        src2 = src.replace("#if 0\n    gbp_x_start(4);\n#endif", "#if 0\n#else\n    gbp_x_start(4);\n#endif")
        self.assertEqual(contract_callers(src2, ["gbp_x_start"]), {"gbp_x_start": 1}, "the #else of an #if 0 is live")

    def test_main_c_itself_parses_into_the_functions_the_wiring_relies_on(self):
        defs = function_defs(strip_for_calls(read(MAIN)))
        for f in ("main", "live_step", "live_tap", "live_tap_body", "pump", "pump_body", "v28_cut", "v28_dispatch_phase_start",
                  "submit_ready", "live_dma_cb"):
            self.assertIn(f, defs, "%s was not parsed as a function definition of main.c" % f)
        live = reachable_functions(defs)
        for f in ("live_step", "live_tap", "pump", "v28_cut", "v28_dispatch_phase_start", "submit_ready", "live_dma_cb"):
            self.assertIn(f, live, "%s is not reachable from main() by name: the reachability graph is broken" % f)

    def test_the_check_itself_fails_on_a_missing_caller(self):
        """The checker is run on main.c with each contract call renamed away: it must report zero callers. Without this
        the test above could go green on a parser that finds nothing (the class of test that agrees with the bug)."""
        src = read(MAIN)
        for h, names in self.population().items():
            for n in names:
                mutated = re.sub(r"\b%s\s*\(" % re.escape(n), "removed_call(", src)
                self.assertEqual(contract_callers(mutated, [n])[n], 0)


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
