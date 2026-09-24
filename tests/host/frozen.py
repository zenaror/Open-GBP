"""
tests/host/frozen.py — the commits the freeze tests compare against, BY HASH
(GitHub Issue #83, pattern F of `HARDWARE_TESTS.md` §V18.7).

WHY THIS EXISTS. Seventeen freeze tests located their base with

    git log --format=%H -1 --grep "<phrase from the commit message>"

`-1` takes the NEWEST match. So a later commit whose message repeats the phrase
silently moves the base of a freeze test, and the test then compares a frozen
tool against a commit that is not the one that froze it — passing either way,
and saying nothing. The freeze tests are what make "frozen before the data"
checkable at all; a freeze test that can drift is not one.

THE RULE. The hash is the identity and it is recorded here. The phrase is kept
and CHECKED rather than searched: `base()` fails when the phrase no longer
matches the pinned commit, and — the case this exists for — when it matches MORE
than one commit, because that is the collision itself, caught at the moment it
appears instead of silently changing an answer.

Adding an entry is deliberate: a checkpoint that freezes a new module records
its own hash here, in the commit that does the freezing.
"""
import subprocess
import unittest

import guards

# phrase in the commit message -> the commit that actually froze the thing
BASES = {
    "Issue #58 -- Phase 6's first physical run pre-registered":
        "892dee2618fb46116488796bd02178cb62da22dc",
    "Issue #58 -- the three models in code before the build exists":
        "cb63d0a035b2280d94ea3317d3af1590c751bbf8",
    "Issue #64 -- agb-tone designed and pre-registered":
        "3bec80be92295a25d2f37d9278971e6408857759",
    "Issue #65 -- agb-tone built":
        "338bcece78c67e66e6d1392ac0984e3750e9d906",
    "Issue #69 -- the sweep pre-registered":
        "9cf5acbaed6c4d508fb7e0e04767231da196e067",
    "Issue #75 -- U-GBP-038's separator pre-registered":
        "0cbc6bb6ebb507b30c3d4afde8cacc6bbe7a5de6",
    "Issue #79 -- GBP-HW-305 decided":
        "f9510794118c51229316cb30cbf4abcb8fe010f7",
    "Issue #80 -- predictions frozen":
        "078b25ae37d3a6e0209b1db6e4b6320b2798879a",
    "RUN 34 pre-registered":
        "ca3ed787501dbe370cd9ba0dd218f7f4909d9abb",
    # Issue #84: §V19's three gates, frozen before GBP-AUDIO-005 runs
    "Issue #84 -- §V19 transcribed":
        "364be8416e674427ad4c377d6706046a86c35398",
    # Issue #84: the drain log -> report builder, frozen with the image, before GBP-AUDIO-005 runs
    "Issue #84 -- the drain report builder":
        "897ea6c42e5d104ad85dcfc631758d2ba2e00481",
    # Issue #86: AOUT-HW-001's scope and gate, frozen before the run
    "Issue #86 -- §V21 pre-registers AOUT-HW-001":
        "2f140289aa1ffd421102c0cc8e27d74180cb9771",
    # Issue #92: Phase 6's acceptance (§V22), transcribed and frozen before the POC exists. The key is the
    # commit's own subject: a shorter phrase also matched the pin commit's body, which base() caught
    "Issue #92 -- §V22 transcribed, Phase 6's acceptance gates frozen":
        "94b478d579bc579ae7ba54e8f3ff5e81e0d3ca15",
    # Issue #92: §V22.9 AMENDMENT 1 changed L2's absent arm and added the silence fraction; the gates'
    # bytes are pinned HERE from now on (the text's frozen start stays the one above)
    # Issue #92: the live image's log -> report builder, frozen with the image, before any run
    "Issue #92 -- live-0001 and its report builder":
        "feaf380fb0c08669570e34e0b97425d0de7d5493",
    "Issue #92 -- §V22 AMENDMENT 1 applied":
        "dfb0a965ec73120c55f75b2a0146e5d10a1d45c6",
}


def _matches(phrase):
    r = subprocess.run(["git", "-C", guards.ROOT, "log", "--format=%H", "--grep", phrase],
                       capture_output=True, text=True)
    return [h for h in r.stdout.split() if h] if r.returncode == 0 else []


def base(phrase):
    """The pinned commit for `phrase`.

    Raises SkipTest when this checkout does not have it (a shallow clone: a real
    "cannot check here"). Raises AssertionError when the phrase has stopped
    identifying it — either it no longer matches the pinned commit, or it matches
    more than one, which is the drift this module exists to catch.
    """
    assert phrase in BASES, (
        "no pinned commit for %r. A freeze test must not search for its own base: "
        "record the hash in tests/host/frozen.py in the commit that freezes the thing." % phrase)
    pinned = BASES[phrase]
    if not guards.base_available(pinned):
        raise unittest.SkipTest(
            "the base commit %s is not in this checkout, so the freeze cannot be checked here" % pinned)
    hits = _matches(phrase)
    if len(hits) > 1:
        raise AssertionError(
            "%r now matches %d commits (%s). Under the old `git log -1 --grep` this would have moved "
            "the freeze test's base to the newest of them, silently. Give the new commit a distinct "
            "message, or pin the freeze to a different phrase."
            % (phrase, len(hits), ", ".join(h[:8] for h in hits)))
    if hits and hits[0] != pinned:
        raise AssertionError(
            "%r identifies %s, but this module pins %s. One of the two is wrong and the freeze test "
            "must not pick for itself." % (phrase, hits[0][:8], pinned[:8]))
    return pinned


def source(phrase, path):
    """`path` as of the commit pinned for `phrase` (via guards.show, so a missing
    path in a present commit fails rather than skipping)."""
    return guards.show(base(phrase), path)
