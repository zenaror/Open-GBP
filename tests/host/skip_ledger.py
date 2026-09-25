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

# THE ORDER MATTERS, and that is recorded rather than engineered away (Issue #83, pattern I
# of HARDWARE_TESTS §V18.9.6). `classify()` returns the FIRST entry that matches, so a reason
# such as "run `make build initirq-audit` to produce the audit inputs" lands in NOT_BUILT
# rather than AUDIT_INPUT_ABSENT because the NOT_BUILT pattern appears earlier. Both classes
# are honest for that reason and both name the same `make` target as the cover, so this is
# cosmetic; the classifier was deliberately NOT restructured for it. A NEW entry that must
# win over an existing one has to be placed ABOVE it, not merely written more specifically.

# (regex on the skip reason, class, what covers the risk instead)
LEDGER = [
    (r"^the (base|candidate|frozen) commit .*is not (available|in this checkout)", "HISTORY_ABSENT",
     "the freeze is also pinned by the records themselves (the part's own text) and re-checked on any full clone"),
    (r"^the base commit %s is not in this checkout", "HISTORY_ABSENT",
     "same; this is guards.assert_confined's own wording, and since Issue #83 it is ALSO the one "
     "reason every frozen-module test gives. Nine per-module reasons were retired with the "
     "`git log -1 --grep` lookup they belonged to (HARDWARE_TESTS §V18.9.3): the base is pinned by "
     "HASH in tests/host/frozen.py now, and what covered each module still covers it -- each frozen "
     "tool is also exercised on synthetic vectors by its own tests/host/test_*.py, which never skip, "
     "and the constants each module holds are quoted in the part that froze it"),
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
    # Issue #82: these fire from `raise unittest.SkipTest(...)`, which the static extractor did not
    # see until #82, so they were registered nowhere. Each reads a RAW capture or log under logs/ or
    # captures/local/; the fixtures DERIVED from those runs are versioned and read unconditionally.
    (r"^(the (run-[0-9]+|%s) (witness )?capture is not on this machine|the run-8 log is not on this machine"
     r"|run-8 log absent)$", "LOCAL_ARTIFACT_ABSENT",
     "the derived fixtures of those runs live under captures/fixtures/ and are read without a guard "
     "(test_disp_run5.py opens the run-5 disp fixture and pins its hash; test_disp_run6.py now FAILS "
     "if that versioned fixture is missing); the raw captures are the provenance, hashed in the records"),
    # Issue #82: §V18 quotes four drain figures from the RUN 33 / RUN 34 logs, which are raw drops.
    (r"^the RUN 33 / RUN 34 logs are not in this checkout \(logs/ is ignored\)$", "LOCAL_ARTIFACT_ABSENT",
     "every block-structure figure of §V18 is recomputed from the VERSIONED fixtures by tests that never "
     "skip; the drain lines are quoted verbatim in §V18 with the logs' hashes (captures/README.md)"),
    # Issue #83 (pattern H): build/archive/ was pinned by nothing at all until this checkpoint.
    (r"^no preserved archive is in this checkout \(build/ is not versioned\)$", "LOCAL_ARTIFACT_ABSENT",
     "the same test asserts UNCONDITIONALLY that each archive's hash is still in the document that "
     "names it (§V4 / HANDOFF); only the byte comparison needs the file, and build/ is never versioned"),
    # Issue #83 (pattern D): two reasons that did not exist before, because these two checks
    # used to be `if os.path.exists(...)` blocks that passed having checked nothing.
    (r"^external/gbhwdb is not in this checkout$", "LOCAL_ARTIFACT_ABSENT",
     "the same test asserts UNCONDITIONALLY that the photographs are not under logs/; what needs "
     "external/gbhwdb is only the second half, that they were MOVED there rather than deleted"),
    (r"^the preserved stream-0014 archive is not in this checkout$", "LOCAL_ARTIFACT_ABSENT",
     "build/ is not versioned; §V7.3's own text carries the archive's size and hash, and the "
     "staged slot is checked separately by test_staged_artifacts.py and by this file's own "
     "test_the_staged_slot_holds_one_of_the_two_named_images, neither of which needs build/archive"),
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
    # Issue #84: the seven session logs AMENDMENT 4's prior and GBP-HW-317 are read from.
    (r"^the seven drain-prior session logs are not archived in this checkout \(captures/local is ignored\)$",
     "LOCAL_ARTIFACT_ABSENT",
     "every figure §V19.11 and GBP-HW-317 quote is on the page with each log's full hash, and pinned "
     "from the SOURCES by tests that never skip (the rows, the verbatim sentence, the claims it must "
     "not make, the Makefiles' source lists); the Operator's machine, where the logs are, runs the suite first"),
    # Issue #91: RUN 37's d2 file, under captures/local, ignored by design (it is the 0xA5 fill pattern).
    (r"^RUN 37's d2 file is not archived in this checkout \(captures/local is ignored\)$", "LOCAL_ARTIFACT_ABSENT",
     "the file carries no data (65 536 x 0xA5); its hash and size are on the page (§V19.14.2), and every D2 "
     "figure is recomputed from the VERSIONED RUN 37 log by tests that never skip"),
    # Issue #90: RUN 36's archived copy and the live Gecko capture, under captures/local, ignored by design.
    (r"^the RUN 36/37 Gecko capture is not archived in this checkout$", "LOCAL_ARTIFACT_ABSENT",
     "§V21.9 quotes the capture's hash, size, line counts and every RUN 36 line it carries, and the log "
     "itself is VERSIONED (captures/fixtures/hw-gamecube-gbp-2026-09-23-aout-0002-run36.log), from which "
     "the played order and the class are recomputed by tests that never skip; the Operator's machine, "
     "where the capture is, runs the suite first"),
    (r"^RUN 36's archived copy is not in this checkout \(captures/local is ignored\)$", "LOCAL_ARTIFACT_ABSENT",
     "the versioned fixture is the same bytes and its hash is pinned by a test that never skips; this "
     "check only confirms the local copy has not diverged from it"),
    # Issue #85: RUN 35, under captures/local and logs/, ignored by design.
    (r"^RUN 35 is not archived in this checkout \(captures/local is ignored\)$", "LOCAL_ARTIFACT_ABSENT",
     "§V20's hashes, verdict, rows and the write-happened check are quoted on the page and pinned from "
     "the SOURCES by tests that never skip (the verdict-first rule, GBP-HW-305's FACT pointer, the gate's "
     "freeze by hash); the Operator's machine, where the files are, runs the suite first"),
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
        # Issue #69: tools/v11sweep.py is frozen the same way, found by its commit message.
    # Issue #75: tools/v13sep.py is frozen the same way, found by its commit message.
    # §V14: tools/v14repeat.py (a measurement method, no gate) is frozen the same way.
    # Issue #79: tools/v16bitgate.py, the repaired gate, frozen the same way.
    # Issue #80: tools/v17pred.py, the predictions frozen before the decoder, and the decoder.
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
    # Issue #82: the ONLY compiler skip. It is exact, so the old "gcc unavailable: <the compiler's
    # error>" -- a COMPILE FAILURE reported as a skip, which seven files did until #82 -- no longer
    # classifies anywhere, statically or at run time.
    (r"^gcc unavailable on this host$", "TOOLCHAIN_ABSENT",
     "tests/host/hostcc.py skips ONLY when the host has no gcc; a gcc that exists and fails to build "
     "a harness FAILS the test, and tests/host/test_compile_skips.py runs every C-compiling test under "
     "both conditions to pin it. `make test-unit` compiles the C sources with the same compiler"),
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
     "NOT INDEX.txt, which the same export writes (Issue #88 corrected this cover, which named it): "
     "tests/host/test_staged_artifacts.py checks the staged bytes against the EXECUTED identity the "
     "records carry (color-0002 = d3c1f09e @ 39f1980), and INDEX.txt's row must read UNPINNED-COPY"),
    (r"^the candidate's identity is pinned by the docs checkpoint", "IDENTITY_NOT_CURRENT",
     "the docs checkpoint's own test pins the hash; test_staged_artifacts.py covers the staged copy"),
    (r"^RUN 17's log is a local capture", "LOCAL_ARTIFACT_ABSENT",
     "the run's figures are quoted in §V7.4 and §V7.6.3 and re-derived from the versioned fixtures where they exist"),
    (r"^nothing is staged under build/swiss", "NOT_BUILT",
     "there is nothing to disturb; the moment a slot exists the same test checks it and cannot skip"),
    (r"^the SD is not mounted on this host", "LOCAL_ARTIFACT_ABSENT",
     "the card is the Operator's hardware, absent from any other machine; build/swiss is checked in the same file and "
     "the identity gate of the part re-verifies the card before each boot"),
    # Issue #120 (RUN 43). Each reads a file under captures/local/, ignored by design; what the record quotes from it
    # is pinned without it, as each cover says.
    (r"^RUN (%d|[0-9]+) is not archived in this checkout \(captures/local is ignored\)$", "LOCAL_ARTIFACT_ABSENT",
     "only RUN 21 and RUN 22 (play-0001) may skip: tests/host/test_vevents.py opens RUN 41-43 from the VERSIONED "
     "fixtures unconditionally, so a missing fixture fails; RUN 21/22's rates are GBP-HW-282's, quoted with their "
     "logs' hashes"),
]

_COMPILED = [(re.compile(p), c, cover) for p, c, cover in LEDGER]


def classify(reason):
    """(class, what covers the risk) for a skip reason, or None when unregistered."""
    r = (reason or "").strip()
    for rx, cls, cover in _COMPILED:
        if rx.search(r):
            return cls, cover
    return None
