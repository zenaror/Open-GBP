"""
tests/host/test_guard_shape.py — the guards on the guards (GitHub Issue #29).

Issue #29 records three instances of one shape: a check that reports clean
while the thing it checks is unverified. Two of them are structural and are
enforced here, for EVERY test of the shape and not only the ones that failed:

  1. A "nothing else moved" guard must ask git a question that includes
     UNTRACKED files. `git diff` alone does not, which is how fifteen fixtures
     sat on disk while two guards reported clean (the second instance). The
     rule enforced: no host test may run `git diff --name-only` or
     `git ls-files` itself; the question goes through `guards.py`, which asks
     both halves in one call.
  2. Every skip reason must be registered in `skip_ledger.py` with its class
     and with what covers the risk instead (the third instance). This half is
     static — it reads the reasons out of the sources — so it runs under
     pytest and under `unittest discover` alike.
"""
import ast
import os
import re
import unittest

import guards
import skip_ledger

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOST = os.path.join(ROOT, "tests", "host")
SELF = ("guards.py", "test_guard_shape.py")


def host_tests():
    return sorted(f for f in os.listdir(HOST) if f.startswith("test_") and f.endswith(".py"))


def read(f):
    with open(os.path.join(HOST, f), encoding="utf-8") as fh:
        return fh.read()


def _reason_of(node):
    """The skip reason a node gives, and how it was obtained.

    A reason is not always a literal: 27 of the suite's sites pass a %-formatted string, starting with
    guards.py's own "the base commit %s is not in this checkout…", which fires from every converted
    guard. A regex over string literals therefore reported clean over sites it never saw (GitHub Issue
    #44, item 2). `ast` sees them all, and for a non-literal the LITERAL PREFIX is what must classify:
    the left operand of a `%`, or the leading literal of an f-string. Anything with no literal prefix
    at all is returned as unextractable, and the test below fails on it rather than ignoring it.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, "literal"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        left, _how = _reason_of(node.left)
        return (left, "format-prefix") if left is not None else (None, "unextractable")
    if isinstance(node, ast.JoinedStr):
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value.strip():
                return v.value, "fstring-prefix"
        return None, "unextractable"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("format", "join"):
        return _reason_of(node.func.value)
    return None, "unextractable"


def skip_sites(files=None):
    """Every skip site in tests/host, by `ast`: (file, line, reason-or-None, how, kind).

    Reproducible from a shell, which is the point of reporting a figure at all:

        python3 -c "import sys; sys.path.insert(0,'tests/host'); import test_guard_shape as g; \
                    s=g.skip_sites(); print(len(s), 'sites,', len({r for _f,_l,r,_h,_k in s if r}), 'distinct reasons')"
    """
    out = []
    for f in (files if files is not None else sorted(x for x in os.listdir(HOST) if x.endswith(".py"))):
        if f == "test_guard_shape.py":
            continue                      # this file's own probes are not suite skips
        if f == "artifacts.py":
            continue                      # Issue #83: it RELAYS the caller's reason; the literals
                                          # live at the call sites, which the branch above reads
        tree = ast.parse(read(f), filename=f)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "skipTest":
                arg = node.args[0] if node.args else None
                r, how = _reason_of(arg) if arg is not None else (None, "unextractable")
                out.append((f, node.lineno, r, how, "call"))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("skipUnless", "skipIf"):
                arg = node.args[1] if len(node.args) > 1 else None
                r, how = _reason_of(arg) if arg is not None else (None, "unextractable")
                out.append((f, node.lineno, r, how, "decorator"))
            # Issue #82: `raise unittest.SkipTest(...)` skips exactly like .skipTest(...) and the
            # extractor did not see it -- eight such reasons were in no ledger entry at all.
            # Issue #83: artifacts.optional(tc, path, reason) / any_of(tc, paths, reason) skip
            # too. They are the D-pattern helper, and their reasons are literals at the CALL
            # SITE -- invisible here until this branch existed, which would have let a whole
            # new family of skips go unregistered.
            elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and node.func.attr in ("optional", "any_of")
                  and isinstance(node.func.value, ast.Name) and node.func.value.id == "artifacts"):
                arg = node.args[2] if len(node.args) > 2 else None
                r, how = _reason_of(arg) if arg is not None else (None, "unextractable")
                out.append((f, node.lineno, r, how, "call"))
            elif isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and (
                    (isinstance(node.exc.func, ast.Attribute) and node.exc.func.attr == "SkipTest")
                    or (isinstance(node.exc.func, ast.Name) and node.exc.func.id == "SkipTest")):
                arg = node.exc.args[0] if node.exc.args else None
                r, how = _reason_of(arg) if arg is not None else (None, "unextractable")
                out.append((f, node.lineno, r, how, "raise"))
    return out


class EveryGitQuestionGoesThroughTheHelper(unittest.TestCase):
    def test_no_test_asks_git_what_changed_by_itself(self):
        offenders = []
        for f in host_tests():
            if f in SELF:
                continue
            t = read(f)
            for pat in ('"diff", "--name-only"', '"ls-files", "--others"'):
                if pat in t:
                    offenders.append("%s uses %s directly; use guards.changed_since()" % (f, pat))
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_the_helper_asks_both_halves_and_says_what_it_omits(self):
        src = open(os.path.join(HOST, "guards.py"), encoding="utf-8").read()
        self.assertIn('"diff", "--name-only"', src)
        self.assertIn('"ls-files", "--others", "--exclude-standard"', src)
        self.assertIn("return tracked_changes(base, paths) | untracked(paths)", src)
        # the deliberate omission is documented where the function is
        for tok in ("does NOT report files that git IGNORES", "captures/local/", "logs/", "build/", "input/",
                    "must look at the files directly"):
            self.assertIn(tok, src, tok)

    def test_an_untracked_file_under_a_guarded_path_is_seen(self):
        """The property the whole Issue is about, proved rather than asserted."""
        probe = os.path.join(ROOT, "src", "__issue29_probe__.c")
        self.assertFalse(os.path.exists(probe))
        head = "HEAD"
        before = guards.changed_since(head, ["src"])
        try:
            with open(probe, "w", encoding="utf-8") as f:
                f.write("/* Issue #29 probe; removed by the test that wrote it */\n")
            after = guards.changed_since(head, ["src"])
            self.assertEqual(after - before, {"src/__issue29_probe__.c"},
                             "an untracked file under a guarded path must be visible to the guard")
            self.assertEqual(guards.tracked_changes(head, ["src"]), before - guards.untracked(["src"]),
                             "git diff alone is blind to it, which is why the helper unions the two")
        finally:
            if os.path.exists(probe):
                os.remove(probe)
        self.assertEqual(guards.changed_since(head, ["src"]), before)

    def test_an_ignored_file_is_not_seen_by_design(self):
        """captures/local/ is ignored by design and must not start failing guards."""
        d = os.path.join(ROOT, "captures", "local")
        if not os.path.isdir(d):
            self.skipTest("no local archive on this host (captures/local is ignored)")
        probe = os.path.join(d, "__issue29_probe__.log")
        self.assertFalse(os.path.exists(probe))
        try:
            with open(probe, "w", encoding="utf-8") as f:
                f.write("probe\n")
            self.assertEqual(guards.untracked(["captures"]), guards.untracked(["captures"]) - {"captures/local/__issue29_probe__.log"})
            self.assertNotIn("captures/local/__issue29_probe__.log", guards.changed_since("HEAD", ["captures"]))
        finally:
            if os.path.exists(probe):
                os.remove(probe)


class EverySkipIsRegisteredWithWhatCoversIt(unittest.TestCase):
    def skip_reasons(self):
        return [(f, r) for f, _l, r, _how, _k in skip_sites() if r is not None]

    def test_every_reason_in_the_sources_classifies(self):
        unregistered = ["%s: %s" % (f, r) for f, r in self.skip_reasons() if skip_ledger.classify(r) is None]
        self.assertEqual(unregistered, [], "unregistered skip reasons (add them to skip_ledger.py with their class "
                                           "and with what covers the risk instead):\n" + "\n".join(unregistered))

    def test_the_extractor_sees_every_site_including_the_formatted_ones(self):
        """Issue #44 item 2: a regex over literals reported clean over sites it never saw."""
        sites = skip_sites()
        kinds = {k: sum(1 for s in sites if s[4] == k) for k in ("call", "decorator", "raise")}
        hows = {h: sum(1 for s in sites if s[3] == h) for h in ("literal", "format-prefix", "fstring-prefix", "unextractable")}
        self.assertEqual(hows["unextractable"], 0,
                         "a skip reason with no literal prefix cannot be registered or reviewed: %s"
                         % [(f, l) for f, l, r, h, _k in sites if h == "unextractable"])
        self.assertGreater(hows["format-prefix"], 10, "the formatted reasons are the ones the regex missed; if this "
                                                      "collapses to zero the extractor is no longer proving anything")
        self.assertGreater(kinds["call"], 50)
        self.assertGreater(kinds["decorator"], 40)
        # Issue #82: the raise form is seen too -- fifteen sites when it was added, one of which (a
        # VERSIONED fixture) was turned into a failure in the same checkpoint
        self.assertGreaterEqual(kinds["raise"], 14)
        # guards.py's own formatted reason is in the set, which is the site the regex missed first
        self.assertTrue(any(f == "guards.py" and h == "format-prefix" for f, _l, _r, h, _k in sites))

    def test_the_ledger_is_well_formed_and_nothing_in_it_is_stale(self):
        reasons = [r for _f, r in self.skip_reasons()]
        self.assertGreater(len(reasons), 100)
        for pat, cls, cover in skip_ledger.LEDGER:
            self.assertIn(cls, skip_ledger.CLASSES, cls)
            self.assertGreater(len(cover), 30, pat)
            rx = re.compile(pat)
            hits = [r for r in reasons if rx.search(r)]
            # "nothing is staged under build/swiss" is this checkpoint's own new skip; it fires from a file the
            # ledger was written with, so it must match something too
            self.assertTrue(hits, "ledger entry matches no skip in the suite any more (stale): " + pat)

    def test_the_dangerous_class_always_names_its_cover(self):
        covers = [cover for _p, cls, cover in skip_ledger.LEDGER if cls == "IDENTITY_NOT_CURRENT"]
        self.assertGreaterEqual(len(covers), 4)
        for cover in covers:
            self.assertTrue("test_staged_artifacts.py" in cover or "pins the hash" in cover, cover)
        # and the cover exists and cannot itself skip when a staged slot is present
        staged = read("test_staged_artifacts.py")
        self.assertIn("def test_every_staged_slot_holds_what_the_records_name", staged)
        self.assertIn("nothing is staged under build/swiss", staged)

    def test_the_runtime_half_exists_and_states_its_limit(self):
        c = open(os.path.join(HOST, "conftest.py"), encoding="utf-8").read()
        self.assertIn("pytest_runtest_logreport", c)
        self.assertIn("session.exitstatus = 1", c)
        self.assertIn("a conftest is not loaded and this check does not run", re.sub(r"\s+", " ", c))


if __name__ == "__main__":
    unittest.main()
