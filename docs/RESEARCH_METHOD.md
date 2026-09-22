# Open-GBP Research Method

Open-GBP combines reverse engineering, synthetic testing, emulator-assisted testing, and physical hardware experiments.

The purpose of this document is to prevent assumptions from silently becoming implementation facts.

## Evidence classifications

Every material hardware claim should be classified as one of the following.

### FACT

Directly observed in a primary source or reproducible experiment.

Examples:

* a specific instruction in the official Startup Disc writes a known register;
* a hardware trace repeatedly reports a specific value under a controlled condition;
* a register address is directly visible in a verified implementation.

### CORROBORATED

Supported independently by multiple credible sources or experiments.

Example:

```text
Dolphin model
+
Startup Disc analysis
+
matching physical hardware behavior
```

### HYPOTHESIS

A plausible interpretation that has not yet been experimentally demonstrated.

Hypotheses may guide tests but must not be used as stable API behavior without an explicit warning.

### UNKNOWN

Observed or suspected behavior for which no defensible interpretation currently exists.

Unknown bits should remain unknown.

Do not assign names merely to make a register map look complete.

## Evidence hierarchy

For behavior of the physical Game Boy Player, use evidence approximately in this order:

```text
repeatable physical hardware observation
        ↓
official Game Boy Player software analysis
        ↓
multiple independent hardware-oriented references
        ↓
Dolphin hardware model
        ↓
other open-source implementations/research
        ↓
single-source speculation
```

This is not absolute. A hardware observation with an uncontrolled experiment can be weaker than careful static analysis.

Record the reasoning.

## Independence of design, execution, observation and validation

Four things are kept in different hands, or at least in different steps that
each leave a record (`AGENTS.md`, "Roles and responsibilities"):

- **experiment design and pre-registration** — the question and the PASS/FAIL
  gates are written down and committed *before* the hardware is touched, and
  are not renegotiated after the result is seen;
- **execution** — implementation, builds and evidence ingestion, within a
  bounded checkpoint;
- **physical observation** — what a human saw or heard, recorded literally as
  OPERATOR OBSERVATION;
- **post-run validation** — independent recomputation of the important claims
  from the artifacts themselves.

A claim keeps the status its *source* gives it, never the status of whoever
states it. The seats may be held by humans or AIs and may change independently.

**Operational tracking is not evidence.** GitHub Issues, milestones, labels and
the Project record who is doing what and in which order (`AGENTS.md`,
"Operational coordination — GitHub"). Opening, labelling or closing an Issue
changes no classification; only this document's process does, through
`docs/research/EVIDENCE.md`, `docs/research/HARDWARE_TESTS.md` and the
fixtures. A pre-registered gate may be *linked* from an Issue, but it is frozen
in `HARDWARE_TESTS.md`, and an operator declaration quoted in an Issue stays
OPERATOR OBSERVATION.

## Research records

Use:

```text
docs/research/EVIDENCE.md
```

for claims and their supporting evidence.

Suggested structure:

```text
ID: GBP-SIO-001
Claim:
Status:
Confidence:
Sources:
Hardware tests:
Notes:
Open questions:
```

Use:

```text
docs/research/UNKNOWNS.md
```

for unanswered questions that require future investigation.

Use:

```text
docs/research/DEVLOG.md
```

for chronological project decisions and discoveries.

Use:

```text
docs/research/HARDWARE_TESTS.md
```

for experiments actually executed on physical hardware.

## Documentation promotion

Research notes are not automatically public protocol documentation.

Information should generally move through:

```text
observation
    ↓
research note
    ↓
hypothesis
    ↓
test
    ↓
corroboration
    ↓
docs/protocol or docs/hardware
```

When information is promoted into the consolidated documentation, preserve references to the evidence that supports it.


### Reconciliation sweep — before promoting anything (GitHub Issue #29, 2026-09-21)

Consolidated pages drift from `EVIDENCE.md` because nothing in the process
compares the two layers. The project found it twice, by accident both times:
Issue #17 found four Phase-2 pages **understating** what EVIDENCE already
carried, and Issue #26 found `ARCHITECTURE.md`'s keypad plane **contradicting**
`GBP-KEY-001` / `GBP-KEY-005` on the polarity. So, as part of every promotion:

1. **Run the sweep** for the evidence the checkpoint touches:

   ```text
   tools/reconcile.py GBP-KEY-004 GBP-HW-270     # the ids by name
   tools/reconcile.py --since <commit>           # the ids whose EVIDENCE entries changed
   ```

   It prints every line of every page in `docs/protocol/` and `docs/hardware/`
   that cites those ids, with EVIDENCE's status beside it. **It judges
   nothing.**

2. **Read the lines it prints** and **record what you found in the checkpoint,
   including "nothing"**. A sweep that found nothing is a result and is written
   down as one; a sweep nobody records is indistinguishable from a sweep nobody
   ran.

3. **A sweep relocates or corrects WORDING.** A genuine disagreement between a
   page and `EVIDENCE.md` — a page claiming more than the evidence, or the
   opposite of it — is **escalated**, never resolved by editing the page to
   match a guess, and never by editing the evidence to match the page.

**Why this is an instruction and not a test.** Measured on 2026-09-21: of 278
table rows in the consolidated pages, only 44 carry both a status letter and an
id `EVIDENCE.md` defines, and 8 of those 44 read "weaker" than their evidence
under a mechanical comparison — all 8 correctly, because a page row carries a
**compound, aspect-scoped** status ("C (format and polarity …); F (hw,
run-scoped)") while an evidence entry carries one status for one claim. A gate
built on that comparison would be wrong about a fifth of what it could see and
blind to the rest, and it would be switched off within two checkpoints. What IS
mechanical is the half that cannot be argued about: every id a page cites must
exist (`tests/host/test_page_citations.py`, every run).
## Synthetic-first testing policy

Manual physical hardware interaction should be minimized.

Before requesting a GameCube hardware test, determine whether the question can be answered through:

```text
static analysis
host-side unit tests
synthetic inputs
mock transports
recorded trace replay
PowerPC compile/link validation
Dolphin
```

Only request physical testing when the hardware itself is material to the answer.

The development agent should perform all other testing autonomously.

## Hardware abstraction

Code interacting with GBP registers or HSP should be designed so the hardware transport can be substituted where practical.

Conceptual model:

```text
GBP logic
   │
   ▼
transport interface
   ├── real HSP backend
   ├── mock backend
   └── trace/replay backend
```

This allows high-level logic to be tested on the development host without requiring a GameCube.

Avoid spreading direct MMIO access throughout unrelated code.

## Trace-driven testing

Physical tests should generate compact deterministic traces when useful.

Timing-critical events must first be written to a preallocated RAM buffer.

Do not perform synchronous SD writes from a timing-critical IRQ or serial path.

Preferred flow:

```text
hardware event
   ↓
RAM ring buffer
   ↓
noncritical flush
   ↓
SD2SP2
```

A recorded trace should contain enough metadata to reproduce its context:

```text
test ID
build ID / Git commit
GBP execution mode
cartridge or test program
physical Link Port state
BBA state
relevant configuration
overflow/error counters
```

Once captured, the trace should be usable by automated replay tests whenever practical.

## Hardware test requests

A hardware test request should be small and deterministic.

It should identify:

```text
build/test ID
DOL to execute
required cartridge/test program
physical cable/peripheral state
exact user actions
expected output/log file
what question the experiment answers
```

Do not ask the user to perform broad exploratory debugging that software or static analysis could perform.

## Failed experiments

A failed test is evidence.

Record:

* what was expected;
* what occurred;
* whether the failure was repeatable;
* relevant logs;
* whether the hypothesis was rejected or remains unresolved.

Do not delete failed hypotheses from the research history merely because a later explanation was found.

## Emulator use

Dolphin is an auxiliary tool.

It is useful for:

* DOL smoke tests;
* PowerPC execution debugging;
* detecting obvious memory corruption;
* testing generic GameCube code;
* comparing known HSP behavior.

It is not automatically authoritative for incompletely emulated GBP functionality.

When emulator and physical hardware behavior differ, record the difference and investigate it.

## Proprietary binary analysis

Locally owned binaries may be inspected for interoperability research.

Rules:

* never modify the original input in place;
* calculate and record hashes;
* keep proprietary files under ignored local directories;
* do not commit or redistribute proprietary data;
* document behavior and independently written code rather than copying proprietary implementation text.

## Mobile Adapter isolation

Mobile Adapter protocol implementation is deliberately a late-stage concern.

Before that phase, the GBP runtime, physical Link regression, internal SIO behavior, and BBA networking must be understandable and independently testable.

This prevents Mobile Adapter-specific assumptions from contaminating the hardware research and makes the resulting GBP documentation useful beyond a single application.
