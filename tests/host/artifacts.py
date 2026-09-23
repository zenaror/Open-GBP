"""
tests/host/artifacts.py — how a host test may depend on a file that might not be here
(GitHub Issue #83, pattern D of `HARDWARE_TESTS.md` §V18.7).

WHY. Nineteen sites read

    if os.path.exists(p):
        self.assertEqual(...)          # and no else

A test shaped like that PASSES HAVING CHECKED NOTHING when the file is absent.
That is worse than the skip class Issue #82 closed: a skip at least appears in
the count and can be audited, as seven were. This is invisible to every metric
the project publishes, including `make test-python`'s own summary.

THE RULE. Three outcomes, and no fourth:

    required(tc, p, why)      the file MUST be here; its absence is a defect and FAILS
    optional(tc, p, reason)   the file legitimately may not be here; SKIP, with a reason
                              that `skip_ledger.py` must classify
    any_of(tc, paths, reason) check every one that IS here, and SKIP when none is

`any_of` is the pattern three sites had already got right by hand (a `seen`
counter and a `skipTest` when it stayed zero, e.g. test_run14.py); it is here so
the next one does not have to reinvent it, and so the shape is recognisable.

WHAT IS FORBIDDEN is the silent fourth: a conditional that checks something when
present and says nothing when absent. `test_vacuous_pass.py` enforces this both
ways — statically over the sources, and BEHAVIOURALLY, by hiding each file and
proving the tests that read it skip or fail rather than pass.
"""
import os


def required(tc, path, why):
    """The file must exist here. Absence is a defect of the checkout or of an
    earlier step, never a reason to check less."""
    tc.assertTrue(os.path.exists(path),
                  "%s is missing, and this test cannot be weakened into passing without it: %s"
                  % (os.path.relpath(path), why))
    return path


def optional(tc, path, reason):
    """The file may legitimately be absent (an ignored capture, a build output, a
    reference checkout). Skip, never pass quietly. `reason` must classify in
    tests/host/skip_ledger.py."""
    if not os.path.exists(path):
        tc.skipTest(reason)
    return path


def any_of(tc, paths, reason):
    """The ones that are here are checked; when none is, skip. Returns the subset
    that exists, which is never empty on return."""
    present = [p for p in paths if os.path.exists(p)]
    if not present:
        tc.skipTest(reason)
    return present
