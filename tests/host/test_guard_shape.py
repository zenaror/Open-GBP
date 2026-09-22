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
        src = read("../host/guards.py") if False else open(os.path.join(HOST, "guards.py"), encoding="utf-8").read()
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
        out = []
        for f in host_tests():
            if f == "test_guard_shape.py":
                continue
            t = read(f)
            for m in re.finditer(r'skipTest\(\s*("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')', t):
                out.append((f, m.group(1)[1:-1]))
            for m in re.finditer(r'@unittest\.skip(?:Unless|If)\((?:[^()]|\([^()]*\))*?,\s*\n?\s*("(?:[^"\\]|\\.)*")\s*\)', t):
                out.append((f, m.group(1)[1:-1]))
        return out

    def test_every_reason_in_the_sources_classifies(self):
        unregistered = ["%s: %s" % (f, r) for f, r in self.skip_reasons() if skip_ledger.classify(r) is None]
        self.assertEqual(unregistered, [], "unregistered skip reasons (add them to skip_ledger.py with their class "
                                           "and with what covers the risk instead):\n" + "\n".join(unregistered))

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
