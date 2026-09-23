"""
tests/host/hostcc.py — the ONE rule for a host test that compiles C (GitHub Issue #82).

WHY. Issue #81's new test reported a COMPILE ERROR as "gcc unavailable" and
skipped. The Issue #82 audit then found the same pattern in seven older files
(test_agb_coord, test_agb_coord2, test_agb_indexed, test_istim, test_vfull,
test_vidxcap, test_vvi): each ran gcc and, on ANY non-zero exit, skipped with
"gcc unavailable: <the compiler's error>". Under a gcc that exists and fails,
63 of their tests went silent and none failed. And a host with NO gcc at all
did not skip: subprocess raised FileNotFoundError. So the rule was inverted in
both directions: a defect was reported as a skip, and the honest skip crashed.

THE RULE, in one place:
  - no compiler on the host           -> SKIP, "gcc unavailable on this host";
  - a compiler that fails the harness -> FAIL, with the compiler's own output.
The second is a defect in the sources under test and is never a skip.
tests/host/test_compile_skips.py runs every C-compiling test under both
conditions and pins that this is what happens.
"""
import shutil
import subprocess
import unittest


def compile_c(args):
    """Run `gcc args...`. Returns (have, ok, err): have is False, and nothing is
    run, when the host has no gcc on its PATH."""
    if shutil.which("gcc") is None:
        return False, False, ""
    r = subprocess.run(["gcc"] + list(args), capture_output=True, text=True)
    return True, r.returncode == 0, r.stderr


def require(tc, have, ok, err, what="the C harness"):
    """In a TestCase: skip only when there is no compiler; fail when there is one
    and `what` does not build."""
    if not have:
        tc.skipTest("gcc unavailable on this host")
    if not ok:
        tc.fail("%s does not build with the host gcc -- a defect in the sources under test, "
                "never a skip:\n%s" % (what, (err or "")[:2000]))


def require_here(have, ok, err, what="the C harness"):
    """The same rule outside a TestCase method (a module-level helper)."""
    if not have:
        raise unittest.SkipTest("gcc unavailable on this host")
    if not ok:
        raise AssertionError("%s does not build with the host gcc -- a defect in the sources under test, "
                             "never a skip:\n%s" % (what, (err or "")[:2000]))
