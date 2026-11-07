# Research and hardware safety method

This is the public method for implementing and reviewing Open-GBP. It defines
compatibility requirements, claim boundaries, reproducible evidence and safe
hardware procedures. It does not track individual work sessions or current
assignments. Public format and validation entry points are in [VALIDATION.md](VALIDATION.md).

## Authority hierarchy

The project's authority hierarchy is:

```text
REAL PHYSICAL HARDWARE
        >
official Game Boy Player Start-up Disc
        >
Game Boy Interface
        >
Dolphin / mGBA and other emulators
```

Physical Game Boy Player behavior is the final authority for the target
runtime.

The official Start-up Disc is the primary software reference.

GBI is an independent mature implementation and behavioral/reverse-engineering
reference.

Dolphin and mGBA are auxiliary references and never replace physical
observation.

Divergences between these sources must be preserved and documented. Never
silently select whichever source agrees with the current implementation.

## Evidence vocabulary

Every research claim must use the project's evidence vocabulary:

| Status           | Meaning                                                                                         |
| ---------------- | ----------------------------------------------------------------------------------------------- |
| **FACT**         | Observed on physical hardware, or a property of code/data that can be independently recomputed. |
| **CORROBORATED** | Supported by two or more independent sources, with no single source being decisive.             |
| **HYPOTHESIS**   | Consistent with observations but not isolated or established by an adequate experiment.         |
| **UNKNOWN**      | Explicitly unresolved.                                                                          |

An inference is never promoted to `FACT` merely because it appears plausible.

In particular:

* emulator behavior is not physical `FACT`;
* an implementation claim is not evidence merely because the implementation
  produced it;
* an Operator observation remains an `OPERATOR OBSERVATION` unless separately
  supported by machine evidence;
* a GitHub Issue, label, milestone, or Project field never promotes evidence
  status.

The rules below apply to every implementation and published result.

## Historical and binary identity rules

Never reinterpret a historical fixture to make it agree with a newer theory.

The original observation remains exactly as recorded, including known defects.

Never claim that an artifact was physically executed unless its exact identity
matches the recorded run.

A rebuilt binary inherits the source behavior of a validated variant, but does
**not** inherit its physical validation status.

This project embeds commit identity in hardware-testable images. A rebuild at
another commit can therefore have a different hash.

Before using the words **physically tested**, compare the artifact's SHA-256
against the exact hash recorded in:

* the original immutable run record and its artifact manifest;
* the corresponding fixture and its provenance.

See `docs/VALIDATION.md` for historical record access.

Always distinguish:

```text
variant/source validation
```

from:

```text
exact binary validation
```

No hardware is ever tested with a `-dirty` build.

## Frozen contracts

Never silently change a frozen binary or data format.

A frozen contract changes by introducing a **new version**, not by modifying
the meaning of an existing version.

Historical fixtures must remain interpretable according to the contract under
which they were created.

See `docs/VALIDATION.md` for the regression reference and published format sources.

## Scientific role independence

No evidence status derives from a role title.

Examples:

* hardware evidence is hardware evidence;
* code-derived facts are code-derived facts;
* Operator observations are human observations;
* an Executor's implementation claim is not self-validating because the
  Executor wrote the code;
* an Orchestrator's analysis is not physical evidence because the Orchestrator
  reviewed a run.

## Normal physical Link Port behavior is a permanent requirement

The existing PicoAdapterGB already works through the physical Game Boy Player
Link Port.

Therefore the following path is established and must not be unnecessarily
re-proven:

```text
physical cartridge
       ↕
real AGB serial/link hardware
       ↕
physical GBP Link Port
       ↕
PicoAdapterGB
```

Do not waste research time proving ordinary external Link Port communication
exists.

Instead, preserve it.

Physical Link Port compatibility is a permanent requirement of the project,
including:

* Link Cable multiplayer with another physical Game Boy;
* official accessories;
* compatible third-party accessories;
* physical Mobile Adapter GB;
* PicoAdapterGB;
* other normal serial modes exercised through the physical port.

PicoAdapterGB is a concrete regression fixture, not the entire compatibility
target.

The two Mobile Adapters must remain conceptually separate.

The **physical Mobile Adapter GB** is a normal physical Link Port accessory
and must continue working like other accessories.

The **virtual Mobile Adapter GB** is an additional Open-GBP extension over the
GameCube BBA.

Conceptually:

```text
NORMAL MODE

cartridge
   ↕
physical Link Port
   ↕
PicoAdapterGB / cable / peripheral
```

versus:

```text
MOBILE ADAPTER MODE

cartridge
   ↕
internal serial path
   ↕
GBS-DOL / HSP
   ↕
Open-GBP
   ↕
virtual Mobile Adapter
   ↕
BBA
   ↕
Ethernet
```

Do not assume the internal serial path works as required. Prove it
experimentally.

When Mobile Adapter functionality is disabled, Open-GBP must not prevent
normal external Link Port devices from working.

## Mobile Adapter is late-stage work

Do not integrate:

* `libmobile`;
* PicoAdapterGB Mobile Adapter code;
* mGBA Mobile Adapter code;
* BGB-related Mobile Adapter code;
* other Mobile Adapter implementations;

during early Game Boy Player development.

The required progression is defined by `docs/ROADMAP.md`.

Establish independently:

1. reproducible build environment;
2. test infrastructure;
3. physical GBP detection and initialization;
4. video;
5. input;
6. audio;
7. GBA compatibility;
8. GB/GBC compatibility;
9. physical Link Port regression;
10. useful standalone runtime / GBI-class functionality;
11. internal SIO behavior;
12. BBA/network behavior;
13. stable runtime architecture.

Only after these foundations are sufficiently understood should Mobile
Adapter protocol integration begin.

Mobile Adapter support must remain additive and must not replace or degrade:

* physical Link Port behavior;
* physical Mobile Adapter GB support;
* PicoAdapterGB;
* rumble;
* GBP-aware game features;
* GB/GBC/GBA compatibility;
* Start-up Disc / GBI-derived behavior.

## Hardware research safety

When interacting with undocumented hardware:

1. Prefer read-only observation first.
2. Reproduce known official initialization before experimenting.
3. Change one variable at a time.
4. Record original state where possible.
5. Avoid speculative writes to unknown control bits.
6. Document uncertainty.
7. Make experimental writes explicitly opt-in.
8. Provide a clear reset/recovery procedure where relevant.

Permanent physical-experiment rules:

* a new physical write requires justification from a known reference or
  explicit experimental authorization;
* prefer one new variable per experiment;
* preserve and restore state whenever possible;
* every operational wait must have a bounded timeout;
* a timeout is an operational bound, never automatically a discovered
  hardware property;
* hardware is never tested with a `-dirty` build;
* a physical candidate requires a clean commit, rebuild, passing tests, and
  recorded artifact hash;
* power-cycle the console after experiments that may leave device state
  unresolved when the procedure specifies it.

Do not chain several unverified assumptions into a single hardware test.

## Minimize physical hardware intervention

Before requesting a physical GameCube test, determine whether the question can
be answered using:

1. static analysis;
2. host-native unit tests;
3. synthetic vectors;
4. mock hardware transports;
5. trace replay;
6. PowerPC compilation/link validation;
7. binary inspection;
8. Dolphin;
9. Ghidra/static analysis when authorised by the roadmap.

Only request physical hardware when real hardware behavior is material to the
question.

Do not ask the Operator to manually debug something that can be tested
autonomously.

Physical experiments should answer a specific research question.

Avoid requests such as:

> Try this and tell me what happens.

## Hardware test request format

When a physical test is genuinely required, provide:

```text
Test ID:
Build ID:
DOL:
Required cartridge/test ROM:
Physical Link Port state:
BBA state:
Steps:
Expected result/log:
Question answered:
```

Prefer a bounded procedure such as:

```text
1. Copy DOL to SD.
2. Launch through Swiss.
3. Wait for READY.
4. Perform one defined action.
5. Press X to save the report.
6. Return the generated log.
```

After the Operator reports a result, preserve its exact artifact identity, literal
observations, derived conclusions and unresolved questions in a durable run record.
Publish reusable, non-proprietary fixtures and regression tests when practical.

Do not leave important hardware knowledge only in chat history.

## Build identification

Every hardware-testable DOL must be identifiable.

Prefer embedding or displaying:

* semantic application/POC name;
* build ID;
* short Git commit hash when available.

Example:

```text
Open-GBP HSP Probe
Build: hsp-0007
Commit: a83f2cd
```

Generated logs must contain the same identity.

This is required to tie hardware observations to exact source.

## Autonomous testing

Hardware-specific code should be isolated behind testable boundaries whenever
practical.

Prefer a structure conceptually similar to:

```text
higher-level GBP logic
        │
        ▼
GBP transport/API
        │
        ├── real HSP backend
        ├── mock backend
        └── trace/replay backend
```

Avoid spreading direct MMIO or HSP transaction code throughout unrelated
modules.

The purpose is to enable:

* deterministic host tests;
* hardware simulation;
* failure injection;
* trace replay;
* regression testing;
* fewer physical hardware runs.

Timing-sensitive code may require lower-level specialization. Preserve
testability where doing so does not compromise correctness.

## Synthetic tests

Every protocol transformation that can be tested without hardware should have
automated tests.

Examples:

* register encoding/decoding;
* interrupt bit handling;
* keypad encoding;
* video packet parsing;
* frame/buffer boundaries;
* ring-buffer wraparound;
* log encoding;
* trace parsing;
* timeout/state-machine behavior;
* malformed data;
* queue overflow behavior;
* networking state machines.

When implementing new behavior, consider the host-side test before the hardware
test.

## Trace and replay infrastructure

Physical hardware experiments should generate reusable evidence when practical.

Preferred cycle:

```text
one physical test
      ↓
hardware trace
      ↓
sanitized fixture
      ↓
repeatable host regression tests
```

Public reusable fixtures may be stored under:

```text
captures/fixtures/
```

Private/local captures belong under:

```text
captures/local/
captures/private/
```

Never commit private information or proprietary binary data unintentionally.

Trace formats should be documented and machine-readable where practical.

## Raw log workflow

The permanent workflow is:

```text
logs/
    raw input handed over by the Operator
    never edited
    never normalized
    never versioned

captures/local/
    preserved local copy
    ignored by Git

captures/fixtures/
    derived replay fixtures
    versioned when appropriate
```

Hashes are computed directly from the original raw logs.

Raw bytes are primary evidence. Semantic interpretations are derived data and
must remain separate.

## SD2SP2 logging

The hardware setup may include SD2SP2 available.

Use it as the preferred persistent hardware logging destination when useful.

Never perform SD writes directly in timing-critical HSP/SIO paths.

Preferred architecture:

```text
hardware event
      ↓
preallocated RAM ring buffer
      ↓
safe/noncritical flush
      ↓
SD2SP2
```

Do not:

* allocate memory on every event;
* write one filesystem record per serial byte;
* block a serial IRQ on FAT/SD I/O.

If the event buffer fills, increment an overflow/lost-event counter rather
than blocking the critical path.

A useful log header should contain:

* build ID;
* Git commit when available;
* test ID;
* execution mode;
* cartridge/test software;
* physical Link Port state;
* BBA state;
* buffer capacity;
* overflow count;
* relevant runtime options.

Provide an on-screen summary so SD logging failure does not make a test
unusable.

## No USB Gecko or logic analyzer dependency

Assume the Operator does not have:

* USB Gecko;
* logic analyzer.

Do not make required workflows depend on them.

Diagnostics should prefer:

* on-screen status;
* counters;
* error/status codes;
* RAM ring-buffer event histories;
* SD2SP2 logs;
* later BBA telemetry when it does not interfere with the behavior under test.

Optional support for additional debug hardware may be added later, but it must
not be required for normal project development.

## Internal SIO research

Do not assume the following are solved:

* meaning of all `SIOControl` bits;
* meaning, width, and timing of `SIOData`;
* Serial IRQ semantics;
* GBA-mode internal serial behavior;
* GB/GBC-mode internal serial behavior;
* external Link Port routing;
* whether internal handling mirrors, redirects, disables, or competes with
  the external connector.

Normal external Link communication does not prove GameCube-side internal SIO
control.

Internal SIO research should begin read-only whenever possible.

A key eventual experiment is:

```text
known serial activity generated by physical cartridge/AGB
          ↓
observe through GameCube/HSP
```

before attempting:

```text
GameCube/HSP response
          ↓
physical cartridge/AGB observes response
```

## Network/BBA development

Network support must be developed independently of Mobile Adapter logic.

Before Mobile Adapter integration, build standalone BBA/network tests with an
automated host-side peer.

Test independently:

* BBA detection/init;
* IP configuration;
* UDP;
* TCP;
* DNS if required;
* reconnect behavior;
* timeout behavior;
* nonblocking behavior;
* queues/buffering.

Never perform blocking DNS/TCP/UDP operations from timing-critical serial
handling.

A likely architecture is:

```text
timing-critical SIO
       ↓
queue/ring buffer
       ↓
protocol worker
       ↓
network queue
       ↓
BBA worker
```

Do not introduce concurrency unnecessarily, but slow network operations must
never violate serial timing requirements.

## Phase gates

Follow:

```text
docs/ROADMAP.md
```

Do not skip forward merely because a later feature is more interesting.

A later phase may be investigated early only when it directly answers a
blocking feasibility question.

If that happens:

* keep the experiment narrow;
* document why the roadmap was crossed;
* do not allow the experiment to become an architectural dependency
  prematurely.

`libmobile` remains explicitly gated until the relevant GBP/SIO/network
foundations are validated.

Ghidra installation does not authorize early reverse engineering.

## GBI-class functionality

Once the basic runtime is stable, Open-GBP should progressively aim for
practical normal-use functionality comparable to mature GBP software.

Potential areas:

* presentation modes;
* scaling;
* filtering;
* latency/timing improvements;
* configuration;
* compatibility fixes;
* robust startup/shutdown;
* runtime usability.

Do not implement cosmetic parity before the underlying hardware runtime is
stable.

## What Open-GBP will not do

Physical experiments are cheap to get wrong and expensive to repeat.

Before requesting hardware, exhaust the applicable autonomous options:

```text
static analysis
    ↓
host tests
    ↓
synthetic vectors
    ↓
mock transports
    ↓
trace replay
    ↓
PowerPC build/link
    ↓
binary inspection
    ↓
Dolphin
    ↓
Ghidra when authorized
    ↓
physical Game Boy Player
```

No hardware is ever tested with a `-dirty` build.

Do not manufacture evidence IDs.

Read the canonical file, find the highest ID currently in use, and allocate
the next free one.

Do not use proprietary ROM/disc material as a donor unless explicitly permitted
by project policy.

Do not commit proprietary material.

Do not silently promote hypotheses into facts.

Do not reopen resolved questions without a new reason.

Do not use later-phase features to contaminate early-stage Game Boy Player
research.

## Experiment design, observation and independent review

Keep design, execution, physical observation and post-run validation in separate
steps with durable records. Pre-register the question, comparison and prospective
PASS/FAIL/INCONCLUSIVE gates before hardware execution. Do not renegotiate them
after seeing results. Independently recompute important claims from raw artifacts;
a role title or an Issue transition cannot substitute for that validation.

Record literal OPERATOR OBSERVATION before opening or interpreting new machine
logs. When a statement is ambiguous, ask about the underlying fact. A later direct
answer supersedes an interpretation of an earlier ambiguous statement; retain the
original wording and identify the later answer rather than retrofitting history.

A claim record identifies its ID, precise scope, status, confidence, sources,
artifact hashes, experiment/gates, notes and open questions. Unknown bits remain
unknown. Hypotheses may guide tests but cannot silently become stable API behavior.
An uncontrolled hardware observation can be weaker than careful static analysis;
explain the limits of each source even though physical behavior is the final target.

## Reference selection and amendments

Select comparison elements by their contents, never by ordinal position alone.
Apply the same explicit predicate to reference and candidate data. An index in a
bounded ring may identify different event types in different runs. Indices can be
provenance labels, but cannot silently become cross-run matching keys.

A post-data correction must be demonstrably defective independently of whether its
verdict is convenient. Otherwise report the defect and preserve the registered
verdict as inconclusive rather than changing a gate after seeing its output.

Amend records by appending the correction, date and provenance while retaining
the original words and rejected hypotheses. If an amendment changes a status,
append a visible pointer to the heading, without rewriting its original status.
The pointer locates the amendment; it does not itself authorize a status change.

## Measurement cost and frozen arithmetic

An instrument running inside a measurement window contributes to that measurement.
Measure and report its cost separately, or keep it outside the window. State when
it runs and what it adds per cycle. Report rates for the whole window, inside the
instrument span and outside it together. Locate the span in the data when possible.
Balanced or interleaved arms do not cancel a fixed or saturating measurement cost.

Freeze mechanisms with the same precision as thresholds: state accumulation rates,
capacities, bounds and worst-case arithmetic. The reviewer must recompute and record
the worst case before freezing. A mechanism that cannot be checked from its frozen
quantities is an assertion, not a validated freeze.

## Statistical calibration

When statistics disagree, calibrate them against the design that generated the
data instead of choosing the favorable answer. Simulate the design's null with
its own sampling units and exposures, measure false-positive rates, and state which
statistic is primary and why. Report the primary statistic, the other's measured
calibration and the supported conclusion together. Cite the reproducible calibration
test; an argument alone does not establish coverage or test size.

## Claim propagation and retained support

Before promoting research into consolidated hardware/protocol documentation, follow
the supporting citations and inspect amendments. Reconcile scoped and compound
claims individually; a naive comparison of status letters cannot promote a claim.
`tools/reconcile.py` is a report for that review, not an authority or an automatic
promotion gate. Preserve public attribution and reusable non-proprietary evidence.

A finding that contradicts an implemented assumption must name the affected code:
change it within authorized scope, or record why it remains knowingly unchanged.
Follow a design citation to its actual text; if it does not state the rule, identify
the true origin and correct the citation. A claim that something has not been done
requires reading the relevant records and local commit graph, as a positive claim does.

A deferral names the Issue, round or condition that resumes it. Without a successor,
record it explicitly as a decision not to do the work. Retain the analysis outputs
on which conclusions depend in recoverable storage, with hashes and provenance.
A path/hash manifest does not replace the content it identifies. Never erase unique
support merely because it lies in a generated or ignored directory.

## Core decision rule

When choosing what to do next, prefer the task that:

1. answers the most important unresolved technical question;
2. requires the fewest unsupported assumptions;
3. can be tested most autonomously;
4. produces reusable evidence;
5. advances the current roadmap phase;
6. minimizes unnecessary physical Operator intervention.

When uncertain, document the uncertainty rather than hiding it.

The project should optimize for **reproducible evidence and independently
validated behavior**, not merely for visible implementation progress.
