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

### A reference figure is defined by what the element CONTAINS, never by its position (2026-09-22, GitHub Issue #53)

**The rule.** When a pre-registration freezes a comparison against a reference
run, it must identify the reference elements by **what they contain**, not by
where they sit. "The AUDIO-only cycles" is a reference; "`CYCLT i=6,7`" is not,
even when i=6 and i=7 happen to be the AUDIO-only cycles in the run the table
was written from.

**The case that produced it**, and it is worth keeping because the failure is
not obvious in advance. §V7.6.3 tabulated Question T's baseline from RUN 17 by
record index — *"ACK → RE-ARM, AUDIO-only cycles: CYCLT i=6,7: 12 ticks"*. In
RUN 21 and RUN 22, `CYCLT i=6` **carries a VIDEO block**. The index is a
position in a bounded ring of recent cycles; **what that position holds depends
on what the device was doing when the ring was captured**, so the same index
denotes different kinds of thing in different runs. Comparing `i=6` to `i=6`
compares an AUDIO-only cycle with a VIDEO-carrying one — a category error,
found only when the gate was applied in code to real logs (Issue #52), and the
reason Question T was recorded **INCONCLUSIVE** (`HARDWARE_TESTS.md` §V7.8.10).

**Why this one could be fixed after the data and the others could not.** The
defect is wrong **independently of the answer it produces**: it can be
demonstrated by pointing at the two records, without knowing what verdict
either reading gives. **A defect that can only be recognised by disliking its
output is not safe to act on after the data**, and must be reported and left
(`HARDWARE_TESTS.md` §V7.8.6, where the unnamed-statistic half was).

**How to satisfy the rule.** State the predicate that selects the elements —
"every cycle whose record shows a VIDEO block", "every frame whose FRAME_ID is
in the sampled set" — and have the analysis apply that predicate to **both**
sides. A reference table may still print index labels as provenance; it may not
use them as the matching key.

### A heading that outlived its status — append the pointer, never rewrite the words (recognised 2026-09-22, GitHub Issue #49)

A record is amended **on top**: the original words stay, and the correction is
added below them with its date and its Issue. That is why "Failed experiments"
below says not to delete a rejected hypothesis merely because a later
explanation was found, and it is how every correction in this project has been
made.

**It has one consequence that is easy to miss, and this project has already
been bitten by it.** When the amendment changes a **status**, the heading keeps
saying what it said — and a heading is the first thing a reader meets, and the
only thing most tools read. Issue #48 found `tools/reconcile.py` reporting
`GBP-HW-272` as `HYPOTHESIS` while the amendment in its body had moved that
claim to `CORROBORATED`, in the one checkpoint whose rule was that statuses are
copied. The tool was fixed to flag such entries; the document had to be fixed
too.

**So: when an amendment changes a claim's status, the heading gains a POINTER,
appended after its existing words. The existing words are not reordered, not
softened and not requalified.** The pointer carries the date, the Issue and the
status the amendment actually holds.

**This is recognised here, not introduced.** The project has done it for a long
time in at least two places:

```text
UNKNOWNS.md   ## U-GBP-010 (P2 — CLOSED 2026-09-21 by … GBP-HW-265) — L/R bit order in KEYPAD —
              **2026-09-21, Issue #33: the routing FACT (hw, the runs) by the machine join of
              RUN 17 / RUN 18, GBP-HW-270; stays CLOSED**
                   ^ the original heading intact, each checkpoint's outcome appended after it
HARDWARE_TESTS.md
              ## V7 — … RUN 14 / RUN 15 … · RUN 17 / RUN 18 … · RUN 19 / RUN 20 … WITHDRAWN …
              · RUN 21 / RUN 22 … · RUN 23 / RUN 24 … (Issue #47, §V7.7)
                   ^ the same, appended across seven checkpoints
```

**Appending a pointer is not a status change.** The status changed when the
amendment was authorised; the pointer records that it did, where a reader who
stops at the heading will see it. Changing the status itself is a separate
decision with its own checkpoint.

`tests/host/test_amended_headings.py` holds the rule to its population: any
entry `tools/reconcile.py` reports with a later amendment in its body must
carry a pointer in its heading.

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
