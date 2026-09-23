"""tests/host/test_vacuous_pass.py — a test may not pass having checked nothing (Issue #83, pattern D).

§V18.7 listed nineteen `if os.path.exists(...)` blocks with asserts and no `else`.
When the file is absent such a test PASSES, having verified nothing, and — unlike
a skip — it appears nowhere in any figure the project publishes. Issue #82's
instrumentation found that one of the nineteen was ALREADY DEAD:
`test_run17_prereg.py`'s check of the staged `12-stream` slot sat behind three
`skipTest` calls, and its condition was never evaluated on this host at all.

TWO HALVES, because either alone is weak:

  STATIC     no `if <path check>:` block containing an assertion may exist without
             an `else` — the shape simply cannot come back, and the detector needs
             no exceptions because the three sites that were already correct were
             rewritten through the same helper.

  BEHAVIOURAL  the part that proves the fix. For each treated site: hide its file
             (os.path.exists and friends answer False for it, in a fresh
             interpreter, so `skipUnless` decorators see it too), run the exact
             test that reads it, and require the outcome to be SKIP or FAILURE.
             A pass is the defect, and it fails this file.

Nothing here writes to the repository; the files are hidden from the test
process, never from the disk.
"""
import ast
import glob
import json
import os
import re
import subprocess
import sys
import unittest

HOST = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HOST))

# (what is hidden, a path fragment, the tests that read it, the outcome required)
#   "skip" — the file may legitimately be absent, so the test must say so
#   "fail" — the file must be here; its absence is a defect, not an absence
CASES = [
    ("the POC's own DOL beside its build-info", "gbp-audio-window-probe.dol",
     ["test_awin_image.TheIdentityWhenBuilt.test_build_info_and_the_dol_agree"], "fail"),
    ("the vendored gbhwdb photographs", "external/gbhwdb",
     ["test_external_reference.NothingThirdPartyIsCommittedAndTheLogDropIsClean"
      ".test_they_are_out_of_the_raw_log_drop_and_where_the_reference_says"], "skip"),
    ("the vendored GBATEK", "external/gbatek",
     ["test_phase6_entry.TheToneArithmeticIsRecomputable.test_the_two_frequencies_follow_gbateks_formula",
      "test_phase6_entry.TheStopThatDoesNotStop.test_it_is_derived_from_the_reference_and_flagged_as_a_prediction"],
     "skip"),
    ("the unit-test binary the parser check drives", "test_gbp_video",
     ["test_vstate.StrictParsing.test_the_formats_never_misread_each_other"], "skip"),
    ("the Pico Gecko bring-up log", "GECKO-LIVE",
     ["test_run33_34.ThreeChannelsAgreeOnTheSidecarCRC.test_the_footer_crc_is_the_one_the_gecko_and_the_sd_log_carried"],
     "skip"),
    ("RUN 33 / RUN 34's raw drop", "logs/run3",
     ["test_run33_34.TheRawsAreArchivedAndTheIssuesTableWasSwapped.test_the_hashes_on_the_page_are_the_files_hashes"],
     "skip"),
    ("the AV-service raw log and its sidecar", "GBP-AV-SERVICE-001_avsvc-0001",
     ["test_hw_fixture.HardwareFixtureAvsvc.test_the_fixture_sidecar_is_the_consoles_file_byte_for_byte",
      "test_hw_fixture.HardwareFixtureAvsvc.test_the_local_raw_log_is_the_recorded_bytes"], "skip"),
    ("the local archive of the physical runs", "captures/local",
     ["test_run14.TheFixturesAreThePhysicalFiles.test_the_archives_if_present_on_this_host_are_the_recorded_bytes",
      "test_run17.TheFixturesAreThePhysicalFiles.test_the_archives_if_present_on_this_host_are_the_recorded_bytes",
      "test_run14_prereg.NamesAreReservedExactlyOnce"
      ".test_the_run_16_names_are_absent_and_the_run_14_15_archives_if_present_are_the_recorded_sizes"], "skip"),
    ("the preserved stream-0014 archive", "build/archive",
     ["test_run17_prereg.IdentitiesAreTheFrozenOnes.test_stream_0014_is_preserved_first_and_reproducible"], "skip"),
    ("the staged Swiss slot — THE SITE THAT WAS PROVABLY DEAD", "build/swiss",
     ["test_run17_prereg.IdentitiesAreTheFrozenOnes.test_the_staged_slot_holds_one_of_the_two_named_images"], "skip"),
    ("the 003A audit listings", "gbp-init-irq-program-probe/audit",
     ["test_poc_audit.PocAuditOnBuild003B.test_the_003a_objects_fail_the_003b_profile"], "skip"),
    ("the 003B audit listings", "gbp-init-irq-deliver-probe/audit",
     ["test_poc_audit.PocAuditOnBuild004.test_the_003b_objects_fail_the_004_profile",
      "test_poc_audit.PocAuditOnBuildAVSVC.test_the_003b_objects_fail_the_avsvc_profile"], "skip"),
    ("the 004 audit listings", "gbp-init-irq-service-probe/audit",
     ["test_poc_audit.PocAuditOnBuildAVSVC.test_the_004_objects_fail_the_avsvc_profile"], "skip"),
    ("the AV-service audit listings", "gbp-av-service-probe/audit",
     ["test_poc_audit.PocAuditOnBuildVIDEO.test_the_avsvc_objects_fail_the_video_profile"], "skip"),
]

DRIVER = r'''
import io, json, os, os.path, sys, unittest
sys.path.insert(0, sys.argv[1])
FRAGMENT = sys.argv[2]
_orig = {n: getattr(os.path, n) for n in ("exists", "isfile", "isdir")}
def _wrap(name):
    f = _orig[name]
    def w(path):
        try:
            if FRAGMENT in str(path).replace("\\", "/"):
                return False
        except Exception:
            pass
        return f(path)
    return w
for n in _orig:
    setattr(os.path, n, _wrap(n))
res = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
    unittest.defaultTestLoader.loadTestsFromNames(sys.argv[3:]))
print(json.dumps({
    "run": res.testsRun,
    "skipped": [t.id() for t, _r in res.skipped],
    "failed": [t.id() for t, _tb in res.failures] + [t.id() for t, _tb in res.errors],
}))
'''


def run_hidden(fragment, names):
    r = subprocess.run([sys.executable, "-c", DRIVER, HOST, fragment] + names,
                       capture_output=True, text=True, cwd=HOST, timeout=900)
    assert r.returncode == 0, (fragment, r.stderr[-3000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


def d_sites():
    """Every `if <path check>:` whose body asserts and which has no `else`."""
    def checks(node):
        return [x for x in ast.walk(node)
                if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                and x.func.attr in ("exists", "isfile", "isdir")]

    def asserts(body):
        return any(isinstance(x, ast.Assert)
                   or (isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute)
                       and x.func.attr.startswith(("assert", "fail")))
                   for st in body for x in ast.walk(st))

    def escapes(body):
        return any((isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "skipTest")
                   or isinstance(x, (ast.Raise, ast.Return))
                   for st in body for x in ast.walk(st))

    out = []
    for f in sorted(glob.glob(os.path.join(HOST, "*.py"))):
        if os.path.basename(f) == os.path.basename(__file__):
            continue
        for n in ast.walk(ast.parse(open(f, encoding="utf-8").read(), filename=f)):
            if isinstance(n, ast.If) and checks(n.test) and not n.orelse and asserts(n.body) and not escapes(n.body):
                out.append("%s:%d" % (os.path.basename(f), n.lineno))
    return out


class TheShapeCannotComeBack(unittest.TestCase):

    def test_no_conditional_check_without_an_else_remains(self):
        """§V18.7 pattern D: nineteen sites, and the detector needs no exceptions —
        the three that were already correct were rewritten through artifacts.any_of."""
        self.assertEqual(d_sites(), [])

    def test_the_helper_states_the_three_outcomes_and_no_fourth(self):
        src = open(os.path.join(HOST, "artifacts.py"), encoding="utf-8").read()
        for name in ("def required(", "def optional(", "def any_of("):
            self.assertIn(name, src)
        self.assertIn("PASSES HAVING CHECKED NOTHING", src)


class AVersionedFixtureMayNotGoMissingQuietly(unittest.TestCase):
    """§V18.7 pattern C. Twenty-four `skipUnless(os.path.isfile(F))` guards name files that
    are VERSIONED under captures/fixtures/, classified LOCAL_ARTIFACT_ABSENT — the class for
    the Operator's ignored raw drops. Deleting one of those fixtures would therefore turn its
    tests into classified skips and the suite would stay green.

    Twelve of them guarded single test methods and were rewritten as `artifacts.required`.
    The other twelve decorate whole CLASSES, where a per-test assertion does not fit, so the
    rule lives here instead: ONE test, covering every such guard including any added later.
    A deleted versioned fixture now fails loudly, once, by name."""

    def resolve(self, src, name):
        m = re.search(r"^%s = (.+)$" % re.escape(name), src, re.M)
        if not m:
            return None
        env = {"os": os, "ROOT": ROOT, "FIX": os.path.join(ROOT, "captures", "fixtures")}
        for a, b in re.findall(r"^(\w+) = (.+)$", src, re.M):
            try:
                env.setdefault(a, eval(b, dict(env)))
            except Exception:
                pass
        try:
            return eval(m.group(1), env)
        except Exception:
            return None

    def guarded_versioned_paths(self):
        tracked = set(subprocess.run(["git", "-C", ROOT, "ls-files", "captures/fixtures"],
                                     capture_output=True, text=True, check=True).stdout.split())
        out = {}
        for f in sorted(glob.glob(os.path.join(HOST, "test_*.py"))):
            src = open(f, encoding="utf-8").read()
            for m in re.finditer(r"skipUnless\((.{0,400}?isfile.{0,400}?),\s*\n?\s*\"", src, re.S):
                for n in re.findall(r"isfile\((\w+)\)", m.group(1)):
                    p = self.resolve(src, n)
                    if p is None:
                        continue
                    rel = os.path.relpath(p, ROOT)
                    if rel in tracked:
                        out.setdefault(rel, set()).add(os.path.basename(f))
        return out

    def test_every_versioned_fixture_a_skip_guards_is_actually_here(self):
        guarded = self.guarded_versioned_paths()
        self.assertGreaterEqual(len(guarded), 6, "the scan found almost nothing; it has stopped proving anything")
        missing = {p: sorted(fs) for p, fs in guarded.items() if not os.path.isfile(os.path.join(ROOT, p))}
        self.assertEqual(missing, {},
                         "these fixtures are TRACKED by git and are not on disk. Their tests would have "
                         "skipped with a LOCAL_ARTIFACT_ABSENT reason and the suite would have stayed green:\n"
                         + "\n".join("  %s  (guards %s)" % (p, ", ".join(fs)) for p, fs in sorted(missing.items())))


class HidingTheFileNeverProducesAPass(unittest.TestCase):
    """The behavioural half. Each case hides one file and requires the tests that read
    it to say so — by skipping when its absence is legitimate, or by failing when it
    is not. Passing is the defect this Issue exists to remove."""

    @classmethod
    def setUpClass(cls):
        cls.out = {frag: run_hidden(frag, names) for _w, frag, names, _e in CASES}

    def test_every_treated_site_skips_or_fails_when_its_file_is_hidden(self):
        for what, frag, names, expect in CASES:
            got = self.out[frag]
            self.assertEqual(got["run"], len(names), (what, frag))
            for n in names:
                ids = got["skipped"] if expect == "skip" else got["failed"]
                other = got["failed"] if expect == "skip" else got["skipped"]
                self.assertIn(n, ids + other,
                              "%s: hiding %s left %s PASSING — it checked nothing" % (what, frag, n))
                self.assertIn(n, ids,
                              "%s: hiding %s made %s %s, and this site is meant to %s"
                              % (what, frag, n, "fail" if n in got["failed"] else "skip", expect))

    def test_the_dead_site_is_alive_now(self):
        """The one site Issue #82 proved was never evaluated: it used to sit behind three
        skipTest calls. It is its own test now, so hiding the slot reaches it."""
        got = self.out["build/swiss"]
        self.assertEqual(got["skipped"],
                         ["test_run17_prereg.IdentitiesAreTheFrozenOnes.test_the_staged_slot_holds_one_of_the_two_named_images"])

    def test_the_required_case_really_fails_rather_than_skips(self):
        """artifacts.required is the other half of the rule: a file whose absence is a
        defect must FAIL, or the rule would just be 'skip everywhere'."""
        got = self.out["gbp-audio-window-probe.dol"]
        self.assertEqual(got["skipped"], [])
        self.assertEqual(len(got["failed"]), 1)


if __name__ == "__main__":
    unittest.main()
