"""
tests/host/skip_ledger.py — every reason a host test may skip, classified
(GitHub Issue #29, the third instance).

WHY. A skip is indistinguishable from a pass in a summary line. On 2026-09-21
`make test-python` went from "2 skipped" to "7 skipped" with nothing failing,
and five of the new skips were ARTIFACT-IDENTITY guards that went quiet at
exactly the moment a new POC build made the risk they exist for possible. A
person checked the staged image by hand; the suite did not.

WHAT THIS IS. A registry: every skip reason a test may give must match ONE
entry here, and each entry states the CLASS of "cannot check", why skipping is
the honest answer for it, and — the part that matters — WHAT COVERS THE RISK
INSTEAD. A skip reason that is not registered fails the suite, statically
(`test_guard_shape.py` reads the sources) and at run time (`conftest.py`
watches the session under pytest). So a new kind of silence has to be written
down and justified before it is allowed, which is the cheapest form of the
answer this Issue was asking for.

WHAT IT DOES NOT DO. It does not fix a guard that should never have skipped;
that is done per guard. `IDENTITY_NOT_CURRENT` is the class where that applies,
and every entry in it names the test that now fails loudly in its place.
"""
import re

# class -> what it means
CLASSES = {
    "HISTORY_ABSENT": "the git object a freeze compares against is not in this checkout (a shallow or partial clone). "
                      "Nothing about the tree is wrong; the comparison simply cannot be made here.",
    "NOT_BUILT": "an artifact the test reads is produced by a build (`make build`, `make -C tests/unit`, a stimulus or "
                 "a derivation target) and has not been produced in this tree. The build is not the suite's business.",
    "TOOLCHAIN_ABSENT": "the host has no compiler for the check (a C mutation or a compile-time assertion test).",
    "AUDIT_INPUT_ABSENT": "the disassembly listings an audit reads are produced by a separate `make <x>-audit` target "
                          "that needs the Docker toolchain; `make test-python` neither has it nor should start it.",
    "LOCAL_ARTIFACT_ABSENT": "the file is under captures/local/ or logs/ — ignored by design, the Operator's raw drops "
                             "and local copies, never versioned. A clone legitimately has none of them.",
    "PRIVATE_INPUT_ABSENT": "the file is a private reference input under input/ (the Start-up Disc dump, the GBI "
                            "binaries). Never committed; absent on any machine but the Operator's.",
    "IDENTITY_NOT_CURRENT": "THE DANGEROUS CLASS. The test compares a built or staged artifact against an identity the "
                            "records freeze, and the local tree holds a DIFFERENT build — usually because a later "
                            "checkpoint rebuilt the POC at its own commit. Skipping is honest (the local file is not "
                            "the artifact the record names) but it is also exactly when a staged image could have been "
                            "disturbed. Every entry here MUST name what covers the risk instead.",
    "NOT_APPLICABLE": "the fixture or record the test would read does not carry the thing being tested (a synthetic "
                      "file with no ACK, an observational record that does not exist in that version).",
}

# (regex on the skip reason, class, what covers the risk instead)
LEDGER = [
    (r"^the (base|candidate|frozen) commit .*is not (available|in this checkout)", "HISTORY_ABSENT",
     "the freeze is also pinned by the records themselves (the part's own text) and re-checked on any full clone"),
    (r"^the base commit %s is not in this checkout", "HISTORY_ABSENT",
     "same; this is guards.assert_confined's own wording"),
    # Issue #61: §V8.1 – §V8.11 are diffed against the commit that wrote them, found by its
    # message rather than by a pinned hash, so a rebase cannot silently disarm the check.
    (r"^no post-derivation build is archived in this checkout$", "LOCAL_ARTIFACT_ABSENT",
     "the check is that a LATER arrival stays out of §V7.9.7's derivation; with no later arrival on disk "
     "there is nothing to keep out, and the derivation's own seven builds are pinned by name in the "
     "same file"),
    # Issue #74: the Pico Gecko bring-up log lives under captures/local, ignored by design.
    (r"^the bring-up log is not archived in this checkout$", "LOCAL_ARTIFACT_ABSENT",
     "§V12.10's hash and the gecko=1 line are quoted on the page and pinned by tests that never "
     "skip; the cross-check's five quantities are all in the document"),
    # Issue #81: the runtime decoder is proved from the VERSIONED fixtures; the raw drops and
    # #80's WAVs are extra comparisons made only where they exist.
    (r"^the raw sidecars are not in this checkout \(logs/ is ignored\)$", "LOCAL_ARTIFACT_ABSENT",
     "the fixtures' own hashes and the raw sidecars' hashes (as §V15 records them) are pinned on "
     "the decompressed bytes by tests that never skip, and recompressing them reproduces the .gz"),
    (r"^the decoded WAVs of Issue #80 are not in this checkout \(captures/local is ignored\)$",
     "LOCAL_ARTIFACT_ABSENT",
     "the same samples are regenerated from the versioned fixtures by tools/v17decode.write_wav -- "
     "the code that wrote those WAVs -- and compared integer for integer, and that test never skips "
     "for want of a local file"),
    (r"^gcc unavailable on this host$", "TOOLCHAIN_ABSENT",
     "the fixtures' hashes, the coefficient table against its generator and the drain-path source "
     "pins do not need a compiler and never skip; a compiler that exists and fails to build the "
     "harness FAILS the test instead of skipping it"),
    # Issue #78: RUN 33 and RUN 34, under captures/local and logs/, ignored by design.
    (r"^RUN 33 or RUN 34 is not archived in this checkout$", "LOCAL_ARTIFACT_ABSENT",
     "§V15's hashes, offsets, verdicts and measurements are all on the page and pinned from the "
     "SOURCES by tests that never skip -- the frozen-tool diffs, the unknowns, the heading pointers "
     "and the new ids -- and the Operator's machine, where the files are, runs the suite first"),
    # Issue #72: the same for RUN 32, whose raws and 5.2 MB sidecar live under captures/local
    # and logs/, both ignored by design.
    (r"^(RUN 32 is not archived in this checkout( \(captures/local is ignored\))?"
     r"|RUN 32's sidecar is not in this checkout"
     r"|both references are needed and are not both archived here)$",
     "LOCAL_ARTIFACT_ABSENT",
     "§V11.16's figures are pinned from the SOURCES in the same file -- the frozen-construction "
     "diff, the reopened U-GBP-038, the GBP-HW-299 pointer and the new ids never skip -- and the "
     "Operator's machine, where the files are, runs the suite before every push"),
    # Issue #67: the same for RUN 31, plus the cases that need BOTH runs to compare.
    (r"^(RUN 31 is not archived in this checkout( \(captures/local is ignored\))?"
     r"|RUN 31's sidecar is not in this checkout"
     r"|RUN 30 is not archived in this checkout"
     r"|both runs are needed and are not both archived here)$",
     "LOCAL_ARTIFACT_ABSENT",
     "the document's own figures are pinned from the SOURCES in the same file -- the frozen-construction "
     "diff, the naming defect, the unknowns' statuses -- and the Operator's machine, where the files are, "
     "runs the suite before every push"),
    # Issue #62: RUN 30's raws and its 5.2 MB sidecar live under captures/local and logs/,
    # both ignored by design, so a clone has neither and every recomputation skips.
    (r"^(RUN 30 is not archived in this checkout \(captures/local is ignored\)"
     r"|the raw drop is not in this checkout \(logs/ is ignored\)"
     r"|RUN 30's sidecar is not in this checkout"
     r"|RUN 30 or its reference is not in this checkout"
     r"|RUN 30's archived copies are not in this checkout \(captures/local is ignored\))$",
     "LOCAL_ARTIFACT_ABSENT",
     "the document's own figures are pinned from the SOURCES in the same file -- the frozen-construction "
     "diff, the prose correction, U-GBP-012's status and the two new unknowns never skip -- and the "
     "Operator's machine, where the files are, runs the suite before every push"),
    # Issue #68: §V10 checks that stimulus/agb-tone was NOT edited by the design checkpoint,
    # finding its build commit by message rather than by a pinned hash.
    # Issue #70: the same for agb-sweep's own artifacts, which live under build/ (Git-ignored),
    # and for the two §V11 freezes this checkpoint checks by commit message.
    (r"^(neither build artifact is in this checkout \(build/ is ignored\)|the build artifacts are not in this checkout \(build/ is ignored\)|the commit that wrote §V11 is not in this checkout)$", "LOCAL_ARTIFACT_ABSENT",
     "§V11.15.1's two hashes and the 1 960-byte size are on the page and pinned by tests that never "
     "skip, and the ROM is rebuilt from source by `make stimulus-sweep` whenever it is needed"),
    # Issue #70 (§V11.15.7): the ROM's APU field layout is pinned against the VENDORED GBATEK,
    # which external/ does not ship in a clone.
    (r"^external/gbatek is not in this checkout$", "LOCAL_ARTIFACT_ABSENT",
     "the same constants are pinned against tools/v11sweep.py and against agb-tone's own word by "
     "tests that never skip, and §V11.15.7 quotes the four GBATEK lines on the page"),
    (r"^the commit that built agb-tone is not in this checkout$", "HISTORY_ABSENT",
     "the ROM's identity is pinned by hash and size in §V9.14 and in test_agb_tone.py, which do not "
     "skip; an edit that changed the bytes would break those first"),
    # Issue #69: tools/v11sweep.py is frozen the same way, found by its commit message.
    # Issue #75: tools/v13sep.py is frozen the same way, found by its commit message.
    # §V14: tools/v14repeat.py (a measurement method, no gate) is frozen the same way.
    # Issue #79: tools/v16bitgate.py, the repaired gate, frozen the same way.
    # Issue #80: tools/v17pred.py, the predictions frozen before the decoder, and the decoder.
    (r"^the commit that introduced tools/v17(pred|decode)\.py is not in this checkout$", "HISTORY_ABSENT",
     "the predictions are checked against the ROM's own tables and GBATEK's formula by tests that "
     "never skip, so a drifting edit breaks those first"),
    (r"^the commit that introduced tools/v16bitgate\.py is not in this checkout$", "HISTORY_ABSENT",
     "synthetic vectors reproduce the exact 0x80 defect and show the repair fixing it, and the "
     "one-substitution claim is checked against the source, whether or not the commit is present"),
    (r"^the commit that introduced tools/v14repeat\.py is not in this checkout$", "HISTORY_ABSENT",
     "a second test shows the module reproduces §V11.16.7's published figures on RUN 32 to the "
     "last digit, which pins the method whether or not the commit is present"),
    (r"^the commit that introduced tools/v13sep\.py is not in this checkout$", "HISTORY_ABSENT",
     "§V13's own text carries every constant the module holds -- the ladder, the floor, the bound "
     "on T -- and the tests that compare the two never skip"),
    (r"^the commit that introduced tools/v11sweep\.py is not in this checkout$", "HISTORY_ABSENT",
     "§V11's own text carries every constant the module holds -- the schedules, the 96-block slice, "
     "the thresholds -- and the tests that compare the two never skip; a drifting edit breaks those first"),
    (r"^the commit that introduced tools/v9tone\.py is not in this checkout$", "HISTORY_ABSENT",
     "the frozen constructions are also pinned by tests/host/test_v9tone.py, which exercises them on "
     "synthetic vectors and fails loudly if a construction changed behaviour"),
    (r"^the commit that introduced tools/v8audio\.py is not in this checkout$", "HISTORY_ABSENT",
     "the frozen constructions are also pinned by tests/host/test_v8audio.py, which exercises them on "
     "synthetic vectors and fails loudly if a construction changed behaviour"),
    (r"^the pre-registration's commit is not in this checkout$", "HISTORY_ABSENT",
     "§V8.12's own text states that §V8.1 – §V8.11 are untouched, and test_awin_image.py's other "
     "cases pin the new part's contents and the heading pointer without needing history"),
    (r"^(build the unit tests first|run `make -C tests/unit`)", "NOT_BUILT",
     "`make test-unit` builds and runs them; `make test` runs both halves"),
    (r"^(run `make build`|build output missing|no build metadata|build-info\.txt|elf\.nm\.txt|build$|audit$|map not built|stimulus not built)", "NOT_BUILT",
     "`make build` produces them and `make test` runs the suite after it"),
    (r"^(coord-000[12] not built here|delivery image not derived here)", "NOT_BUILT",
     "the named make target produces the artifact; the analysis it feeds is re-run when it exists"),
    (r"^run `make build && make swiss`", "NOT_BUILT",
     "test_staged_artifacts.py checks whatever IS staged, and fails rather than skips when it cannot"),
    # Issue #59: the audio window image's audit listings and build-info. The
    # profile is exercised against whichever images ARE built, in both
    # directions, so a checkout with neither built loses the comparison and
    # nothing else; the source-level pins of test_awin_image.py do not skip.
    (r"^(.*is not built in this checkout|the audio image is not built in this checkout|14-audio is not staged in this checkout)$", "NOT_BUILT",
     "`make build` and `make awin-audit` produce them; the subtraction, the budget and the window's "
     "constants are pinned from the SOURCES in the same file and never skip"),
    (r"^gcc unavailable", "TOOLCHAIN_ABSENT",
     "the same property is asserted statically by the source pins in the same file"),
    (r"^run `make [^`]*-audit", "AUDIT_INPUT_ABSENT",
     "`make <x>-audit` is run in the checkpoint that changes the code it audits, and its 0-finding result is reported "
     "there; the suite records the decision rather than silently depending on it. (The `ast` extractor of Issue #44 "
     "caught one site of this class that the literal-only regex never saw: test_play_image.py's decorator.)"),
    (r"^(physical .*(fixture|sidecar) (missing|is required)|raw log not available locally|local raw log not present|"
     r"no local archive on this host|the physical .*(sidecar|fixture).*|color-0001 sidecar missing|physical v3 sidecar missing|"
     r"the v5 replay fixture is missing)", "LOCAL_ARTIFACT_ABSENT",
     "the versioned fixtures under captures/fixtures/ carry what the project's conclusions rest on; the local copies are "
     "the raw provenance and are hashed in the records"),
    (r"^the private (reference inputs|GBI image)", "PRIVATE_INPUT_ABSENT",
     "CLAUDE.md §7: these are never committed; the analyses that used them recorded their hashes"),
    (r"^this synthetic (record|file)", "NOT_APPLICABLE",
     "the case is covered by the fixture that does carry the field"),
    (r"^the tree builds a (different|later) stream candidate", "IDENTITY_NOT_CURRENT",
     "tests/host/test_staged_artifacts.py: the STAGED image under build/swiss/ is hashed against what the records name, "
     "and it FAILS rather than skips when a slot exists and does not match"),
    (r"^the stream-0015 artifact on this host was rebuilt at another commit", "IDENTITY_NOT_CURRENT",
     "tests/host/test_staged_artifacts.py, as above; the executed identity is also frozen in the run records"),
    (r"^the play image on this host is built at", "IDENTITY_NOT_CURRENT",
     "tests/host/test_staged_artifacts.py, as above; §V7.6.8's identity gate re-verifies before each boot"),
    (r"^build/swiss/11-color is the export of an earlier build", "IDENTITY_NOT_CURRENT",
     "tests/host/test_staged_artifacts.py hashes every staged slot against build/swiss/INDEX.txt and fails on a mismatch"),
    (r"^the candidate's identity is pinned by the docs checkpoint", "IDENTITY_NOT_CURRENT",
     "the docs checkpoint's own test pins the hash; test_staged_artifacts.py covers the staged copy"),
    (r"^RUN 17's log is a local capture", "LOCAL_ARTIFACT_ABSENT",
     "the run's figures are quoted in §V7.4 and §V7.6.3 and re-derived from the versioned fixtures where they exist"),
    (r"^nothing is staged under build/swiss", "NOT_BUILT",
     "there is nothing to disturb; the moment a slot exists the same test checks it and cannot skip"),
    (r"^the SD is not mounted on this host", "LOCAL_ARTIFACT_ABSENT",
     "the card is the Operator's hardware, absent from any other machine; build/swiss is checked in the same file and "
     "the identity gate of the part re-verifies the card before each boot"),
]

_COMPILED = [(re.compile(p), c, cover) for p, c, cover in LEDGER]


def classify(reason):
    """(class, what covers the risk) for a skip reason, or None when unregistered."""
    r = (reason or "").strip()
    for rx, cls, cover in _COMPILED:
        if rx.search(r):
            return cls, cover
    return None
