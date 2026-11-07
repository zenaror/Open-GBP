# Reproducible validation

## Host and GameCube layers

Start with a full Git clone and `python3 tools/history_recover.py` so original
commit identities used by old freeze guards are available. Native C regressions
can run independently with `make test-unit`. The complete Python/fixture suite
includes mandatory PowerPC artifact checks: on a fresh clone run `make build inspect`
through the pinned container before `make test-python`. `make test` runs the build,
inspection and both host gates in that order. Dolphin is auxiliary; no emulator result proves physical Player behavior.

Private inputs, locally archived captures, analysis outputs and attached SD media
are optional comparisons. The registered skip ledger classifies those absences;
an unknown skip reason fails the host suite. Public fixtures and code checks remain
available without a private memory service. Never manufacture a hardware pass from
a skipped check or a compiler/build result.

## Immutable historical text oracles

Legacy scientific assertions refer to previously published designs, gates and
observations. Their text is read directly from the fixed reachable Git revision in
`tools/historical_documents.json`; every blob is checked against its SHA-256.
No copy of those working records is generated in the checkout or kept as a new
fixture directory. This is a historical test oracle, not a current work log.

`tools/historical_documents.py` refuses unlisted archive paths, checks every digest,
requires the recorded revision, and permits reads only. The explicit adapter used
by legacy host tests still reads all non-oracle files from the current working tree:
source mutations, missing public files and current binary fixtures remain visible.
It never downloads data or consults a private service. A shallow clone must obtain
the full history before running these historical regressions.

The original three entry-policy test modules are replayed **unchanged** in an
isolated local clone at that revision. Their individual JUnit cases and skips are
checked, not inferred from a process staying alive. Current public documentation
has separate checks for self-contained links, privacy and required safety rules.
Scientific threshold assertions and frozen parser/runtime modules are not replaced
with an aggregate approval.

## Formats and artifacts

Public protocol references and the writer/parser source define observable register
and sidecar layouts. Version-specific parsers and fixtures must keep historical
behavior, including known defects. Change a frozen format by adding a new version.
Use the fixture catalogue in `captures/README.md`, strict parsers under `tools/`
and the related host tests to reproduce checks. Exact build identity, format and
payload integrity are separate checks; a header or checksum does not prove a run.

Historical evidence IDs in consolidated hardware/protocol pages resolve through
the fixed regression catalogue; `tools/reconcile.py` reports their attributed
statuses without promoting a compound or amended claim. This catalogue cannot
supply current assignments or authorize a new hardware experiment.

## Physical evidence

Specify test/build IDs, exact DOL/hash, cartridge, Link/BBA state, bounded steps,
expected log and the single question answered. Record literal human observations
before interpreting machine evidence. Preserve original raw bytes and derive
replay fixtures separately. Compare exact binary hashes before claiming physical
execution; rebuilding another commit cannot inherit a prior run's validation.

## Cleanup

A report, binary or database may be unique even when ignored. Preserve accepted
results, exact images, relevant failures, source/environment identity and unique
annotations before cleaning enumerated task-owned intermediates. Never clean an
active process or another contributor's files. `make clean` removes the complete
`build/poc` and `build/tests` trees and must not be used as automatic checkpoint cleanup.

Historical citation labels such as `HARDWARE_TESTS.md`, `EVIDENCE.md` or names
prefixed `historical:` refer to that immutable oracle, not to active files in
the current checkout. They remain available for reproducing previously shipped
checks without restoring operational journals into the working tree.


Minimal public keypad/order excerpts under `captures/fixtures/key-order/` let the
historical sequence and run-order assertions execute without ignored raw captures.
Their provenance and exact selection are documented in `captures/fixtures/key-order/README.md`.
Complete-capture comparisons still require the original logs. An empty Swiss
staging area has no index to parse; any staged slot without its index remains a
failure, and the recorded-identity assertions still run without staged bytes.
