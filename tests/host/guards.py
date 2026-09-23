"""
tests/host/guards.py — the shared implementation of the project's "nothing else
moved" guards (GitHub Issue #29).

WHY THIS FILE EXISTS. Several host tests freeze a checkpoint by asking git what
changed under a set of paths since a base commit. Every one of them used

    git diff --name-only <base> -- <paths>

and `git diff` DOES NOT SEE UNTRACKED FILES. On Issue #33 that blind spot let a
guard report clean at an intermediate tree where the condition it exists to
enforce was already violated: fifteen fixture files existed on disk, untracked,
and the guards only failed once they were committed — after the moment when
catching it would have mattered (Issue #29, the second instance).

The fix is not "add a second command to the two tests that failed". It is this
module: ONE implementation, used by every guard of the shape, plus
`tests/host/test_guard_shape.py`, which fails if a host test asks git what
changed without going through it. A class of defect that is fixed only where it
was caught is a class that comes back.

WHAT COUNTS AS "CHANGED", AND THE DELIBERATE OMISSION. `changed_since()`
reports, under the given paths:

  * files that differ from the base commit (added, modified, deleted, renamed),
  * files that exist on disk and are NOT tracked by git,

and it does NOT report files that git IGNORES (`--exclude-standard` applies the
repository's .gitignore). That omission is deliberate and is part of the
contract: `captures/local/`, `logs/`, `build/` and `input/` are ignored BY
DESIGN — they hold the Operator's raw drops, local artifacts and private
inputs, none of which is a versioned project artifact, and all of which
legitimately change between one command and the next. A guard about THOSE paths
cannot be a git question at all and must look at the files directly (see
`tests/host/test_staged_artifacts.py`, which hashes what is actually staged).

Everything here is read-only: no command in this module writes to the
repository, the index or the working tree.
"""
import os
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _git(*args):
    r = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, text=True)
    return r


def base_available(base):
    """True when `base` is an object this checkout actually has."""
    return _git("cat-file", "-e", base).returncode == 0


def show(base, path):
    """The bytes of `path` as of `base`.

    TWO FAILURES, AND THEY ARE NOT THE SAME THING (GitHub Issue #83, pattern B of
    `HARDWARE_TESTS.md` §V18.7). `git show <commit>:<path>` exits non-zero both when
    the COMMIT is absent -- a shallow clone, and a real "cannot check here" -- and
    when the commit is present but the PATH is not in it, which means the file moved
    or the test names it wrongly. Fourteen sites turned both into the same skip, so a
    freeze test could go quiet about a file that had been renamed out from under it.
    That is Issue #81's defect exactly: an error condition rendered as an absence.

    Absent commit -> SkipTest, with the reason the ledger classifies.
    Absent path in a present commit -> AssertionError, because it is a defect.
    """
    if not base_available(base):
        raise unittest.SkipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % base)
    r = _git("show", "%s:%s" % (base, path))
    if r.returncode != 0:
        raise AssertionError(
            "%s IS in this checkout but %s is not in it. That is a moved or misnamed path, not an "
            "absent history, and it must not be skipped over: %s" % (base, path, r.stderr.strip()))
    return r.stdout


def tracked_changes(base, paths):
    """Paths under `paths` that DIFFER from `base` (git diff's answer alone)."""
    r = _git("diff", "--name-only", base, "--", *paths)
    assert r.returncode == 0, r.stderr
    return {p for p in r.stdout.split() if p}


def untracked(paths):
    """Paths under `paths` that exist on disk and are not tracked and not ignored."""
    r = _git("ls-files", "--others", "--exclude-standard", "--", *paths)
    assert r.returncode == 0, r.stderr
    return {p for p in r.stdout.split() if p}


def changed_since(base, paths):
    """THE guard question: everything under `paths` that is not as `base` left it.

    The union of `tracked_changes()` and `untracked()` — which is the whole
    point of this module, because either half alone reports clean in a state
    where the other half is already violated.
    """
    return tracked_changes(base, paths) | untracked(paths)


def assert_confined(tc, base, paths, allowed=(), why=""):
    """Fail `tc` unless everything changed under `paths` is in `allowed`.

    `allowed` is the set of paths a checkpoint was authorised to touch; each one
    should carry its reason in the calling test, next to the set. Skips only
    when the base commit is absent from this checkout — which is a real "cannot
    check", not a "nothing to check", so the skip reason says so.
    """
    if not base_available(base):
        tc.skipTest("the base commit %s is not in this checkout, so the freeze cannot be checked here" % base)
    changed = changed_since(base, paths)
    extra = sorted(changed - set(allowed))
    tc.assertEqual(extra, [], "changed against %s beyond what the checkpoint allows%s: %s"
                   % (base, (" (" + why + ")") if why else "", extra))
    return changed
