"""tests/host/test_compile_skips.py — a compile failure is a FAILURE, never a skip (Issue #82).

The Issue #82 audit found that seven files turned ANY gcc failure into a skip
reading "gcc unavailable: <the compiler's error>": under a compiler that existed
and failed, 63 of their tests went silent and none failed. The honest case was
broken too: with no gcc at all, subprocess raised FileNotFoundError.

tests/host/hostcc.py now holds the one rule. This file pins it BEHAVIOURALLY, by
running every module that compiles C, in a fresh interpreter, under two
simulated conditions. Neither needs a real compiler, so neither can skip:

  BROKEN  gcc exists and every compile fails -> no compiler-reason skip at all,
          and every failure carries hostcc's "does not build" message;
  ABSENT  no gcc on the host                -> every compiler-dependent test skips
          with exactly "gcc unavailable on this host", and nothing fails.

And STATICALLY: no host test runs gcc except through hostcc, so a new C harness
cannot reintroduce the pattern without this file seeing it.
"""
import json
import os
import re
import subprocess
import sys
import unittest

HOST = os.path.dirname(os.path.abspath(__file__))

DRIVER = r'''
import io, json, subprocess, sys, types, unittest
sys.path.insert(0, sys.argv[1])
import hostcc
mode, names = sys.argv[2], sys.argv[3:]
if mode == "broken":
    real = subprocess.run
    def run(args, **kw):
        if args and args[0] in ("gcc", "cc"):        # Issue #83 (E) brought `cc` harnesses in
            return subprocess.CompletedProcess(args, 1, "", "x.c:1:1: error: simulated compile failure")
        return real(args, **kw)
    hostcc.subprocess = types.SimpleNamespace(run=run)
    hostcc.shutil = types.SimpleNamespace(which=lambda n: "/simulated/bin/gcc")
elif mode == "absent":
    hostcc.shutil = types.SimpleNamespace(which=lambda n: None)
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
print(json.dumps({
    "run": res.testsRun,
    "skipped": [[t.id(), str(r)] for t, r in res.skipped],
    "failures": [[t.id(), tb] for t, tb in res.failures],
    "errors": [[t.id(), tb] for t, tb in res.errors],
}))
'''


def compiling_modules():
    out = []
    for f in sorted(os.listdir(HOST)):
        if f.endswith(".py") and f.startswith("test_") and f != "test_compile_skips.py":
            with open(os.path.join(HOST, f), encoding="utf-8") as fh:
                if re.search(r"^import hostcc\b", fh.read(), re.M):
                    out.append(f[:-3])
    return out


def drive(mode):
    r = subprocess.run([sys.executable, "-c", DRIVER, HOST, mode] + compiling_modules(),
                       capture_output=True, text=True, cwd=HOST, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


class NoHostTestRunsGccExceptThroughHostcc(unittest.TestCase):

    def test_the_only_gcc_invocation_is_in_hostcc(self):
        offenders = []
        for f in sorted(os.listdir(HOST)):
            if not f.endswith(".py") or f in ("hostcc.py", "test_compile_skips.py"):
                continue
            with open(os.path.join(HOST, f), encoding="utf-8") as fh:
                t = fh.read()
            if re.search(r"""\[\s*["']gcc["']""", t):
                offenders.append(f)
        self.assertEqual(offenders, [], "these run gcc directly; route them through tests/host/hostcc.py")

    def test_every_known_harness_file_is_covered(self):
        mods = compiling_modules()
        for m in ("test_agb_coord", "test_agb_coord2", "test_agb_indexed", "test_istim", "test_vfull",
                  "test_vidxcap", "test_vvi", "test_audio_runtime",
                  "test_agb_tone", "test_agb_sweep"):    # the two `cc` harnesses, Issue #83 (E)
            self.assertIn(m, mods)

    def test_no_host_test_runs_a_bare_cc_either(self):
        """Issue #83 (E): the static pin above only looked for "gcc", so two harnesses
        calling "cc" were invisible to it."""
        offenders = []
        for f in sorted(os.listdir(HOST)):
            if not f.endswith(".py") or f in ("hostcc.py", "test_compile_skips.py"):
                continue
            with open(os.path.join(HOST, f), encoding="utf-8") as fh:
                if re.search(r"""\[\s*["']cc["']""", fh.read()):
                    offenders.append(f)
        self.assertEqual(offenders, [], "these run `cc` directly; route them through tests/host/hostcc.py")


class ACompileFailureFailsAndOnlyAMissingCompilerSkips(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.broken = drive("broken")
        cls.absent = drive("absent")

    def test_broken_compiler_no_test_skips_for_a_compiler_reason(self):
        gcc_skips = [t for t, r in self.broken["skipped"] if "gcc" in r]
        self.assertEqual(gcc_skips, [])

    def test_broken_compiler_every_harness_test_fails_and_says_why(self):
        bad = self.broken["failures"] + self.broken["errors"]
        # before Issue #82 this was 63 skips and 0 failures in the seven older files alone
        self.assertGreaterEqual(len(bad), 63 + 12)
        for tid, tb in bad:
            self.assertIn("does not build with the host gcc", tb, tid)
            self.assertIn("simulated compile failure", tb, tid)

    def test_no_compiler_every_harness_test_skips_with_the_one_reason_and_none_fails(self):
        self.assertEqual(self.absent["failures"] + self.absent["errors"], [])
        gcc_skips = [(t, r) for t, r in self.absent["skipped"] if "gcc" in r]
        self.assertGreaterEqual(len(gcc_skips), 63 + 12)
        self.assertEqual({r for _t, r in gcc_skips}, {"gcc unavailable on this host"})
        # and the SAME work: what a broken compiler fails is exactly what a missing one skips.
        # Compared per CLASS, because a skip raised in setUpClass is reported as
        # "setUpClass (mod.Class)" while a failure there is reported per test (Issue #83 E
        # brought two such harnesses in); the class is the unit either way.
        def classes(ids):
            out = set()
            for i in ids:
                i = i[len("setUpClass ("):-1] if i.startswith("setUpClass (") else i.rsplit(".", 1)[0]
                out.add(i)
            return out
        self.assertEqual(classes(t for t, _r in gcc_skips),
                         classes(t for t, _tb in self.broken["failures"] + self.broken["errors"]))
