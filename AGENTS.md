# Open-GBP Agent Instructions

This file is the entry point for **any** coding agent or person picking this
repository up — Claude, Codex, another model, a local one, or a human with no
prior context. It is deliberately short: it is a door, not the building.

Open-GBP is an independently implemented open-source runtime, documentation set
and research environment for the **physical Nintendo Game Boy Player**. Most of
its value is *evidence about undocumented hardware*, and evidence is easy to
destroy by being careless with a word like "proven". The rules below exist to
stop that.

## Mandatory read order

1. **`AGENTS.md`** — this file.
2. **`docs/HANDOFF.md`** — current state, current blocker, next safe action.
3. **`docs/README.md`** — how the documentation is organised.
4. **`docs/RESEARCH_METHOD.md`** — the evidence process and promotion rules.
5. **`docs/research/EVIDENCE.md`** — every classified claim.
6. **`docs/research/HARDWARE_TESTS.md`** — executed and planned physical tests,
   and the design documents of each experiment.
7. **`docs/research/UNKNOWNS.md`** — open questions.
8. The design section of the experiment you are about to touch, inside
   `docs/research/HARDWARE_TESTS.md`.

`CLAUDE.md` holds the permanent project policies (build environment, private
inputs, commit discipline, hardware-safety rules). It applies to every agent,
not only to Claude; read it before changing anything.

## Authority

```text
REAL PHYSICAL HARDWARE                                  final authority
  > official Game Boy Player Start-up Disc               primary software reference
  > Game Boy Interface (GBI)                             independent mature implementation
  > Dolphin / mGBA                                       AUXILIARY ONLY, never physical truth
```

Divergences between these are **preserved and documented**, never resolved by
quietly picking one.

## Evidence vocabulary

Every claim carries one of these, and they are not interchangeable:

| status | meaning |
| --- | --- |
| **FACT** | observed on physical hardware, or a property of code/data that can be recomputed |
| **CORROBORATED** | two or more independent sources agree; no single one is decisive |
| **HYPOTHESIS** | consistent with what was observed, not isolated by an experiment |
| **UNKNOWN** | explicitly open; say so instead of guessing |

An inference is **never** promoted to FACT.

## Mandatory rules

- Never turn emulator behaviour into a physical FACT. Dolphin and mGBA are
  auxiliary; their models are incomplete by design.
- Never change a frozen binary format silently. A frozen contract changes by a
  **new version**, never by an edit. See "Frozen contracts" in `docs/HANDOFF.md`.
- Never reinterpret a historical fixture to make it agree with a newer theory.
  The old observation stays exactly as recorded, including its known defects.
- **Never claim an artifact was physically executed unless its exact identity
  matches the recorded run.** A rebuilt binary inherits the *source behaviour*
  of a validated variant and **not** its physical status: this project embeds the
  commit in its images, so a rebuild at another commit has a different hash.
  Compare the SHA-256 against the one recorded in `EVIDENCE.md` /
  `HARDWARE_TESTS.md` before using the words "physically tested".
- Distinguish **variant/source validation** from **exact binary validation** in
  every sentence where it matters.
- Do not use proprietary ROM or disc material as a donor for anything unless the
  project policy explicitly allows it (`CLAUDE.md` §7). Do not commit it, ever.
- Do not manufacture evidence IDs. Read the file, find the highest in use, and
  allocate the next free one.
- Read `docs/HANDOFF.md` before implementing anything.
- If the handoff looks stale relative to the repository history, **stop and
  reconcile** before trusting it. The procedure is in that file.
- After a scientific checkpoint, update the handoff.

## Roles and responsibilities

Three RESPONSIBILITIES, deliberately separated. They are not products, vendors,
models or people: swapping the orchestrator for another tool, the executor for
another agent, or a human for an AI in any seat (or back) **must not change the
scientific process**. `docs/HANDOFF.md` may name who currently holds each seat;
that assignment is ephemeral and is never the definition.

### OPERATOR / HARDWARE OPERATOR

- controls and physically operates the real GameCube / Game Boy Player, the
  media and the topology (cartridge, SD, BBA present or absent);
- performs hardware procedures only after the experiment is ready and
  pre-registered;
- reports human visual / auditory / physical observations;
- supplies the raw artifacts a physical run produces;
- makes the final project-direction decisions when human approval is needed.

Operator observations stay **OPERATOR OBSERVATION** unless separately supported
by machine evidence. The operator need not be the same person forever.

### ORCHESTRATOR / VALIDATOR / PLANNER

- reconstructs project state from the repository and the evidence;
- reviews executor results;
- independently validates important claims against logs, artifacts, commits,
  diffs, tests and documentation wherever possible;
- detects inconsistencies and scope creep;
- designs the next research steps and experimental questions;
- establishes or reviews prospective PASS/FAIL gates **before** hardware;
- hands the executor bounded checkpoints;
- distinguishes historical facts from current state;
- prevents resolved questions from being reopened without a new reason.

The orchestrator normally does **not** modify source or execute the
implementation. It may be an AI or a human.

### EXECUTOR / CODING AGENT

- edits source and documentation within the authorised checkpoint;
- implements approved designs; writes tests and fixtures; builds; runs suites,
  static audits, binary audits and emulator checks;
- ingests supplied evidence; generates deterministic artifacts; maintains
  documentation; creates logical commits; pushes authorised commits;
- reports exact identities and the final working-tree state.

The executor does **not** silently redefine the experiment question, a
pre-registered gate, a hardware procedure, a scientific interpretation, a frozen
contract or the project direction. If implementation or analysis shows one of
those materially needs to change, it is surfaced to the orchestrator/operator
**before** the next physical run.

### Role independence

No evidence status comes from a role title. Hardware evidence is hardware
evidence; code-derived facts are code-derived facts; operator observations are
human observations. An executor's implementation claim is not self-validating
because that executor wrote the code; an orchestrator's analysis is not physical
evidence because it reviewed the run.

## Checkpoint discipline

Permanent policy for any meaningful work, in this order:

1. a **bounded checkpoint** (what is authorised, what is not);
2. implement only the authorised scope;
3. run the applicable tests, audits and emulator checks;
4. create logical commit(s), one technical purpose each (`CLAUDE.md` §24);
5. push the authorised commits;
6. report: commit SHA, files changed, test/audit results, push status, final
   `git status`.

A completed scientific or software checkpoint must never exist only in a chat
transcript. The repository must hold enough state — `docs/HANDOFF.md`, the
research records, the fixtures — for a different executor or orchestrator to
resume without that chat.

## Operational coordination — GitHub

The canonical repository is <https://github.com/zenaror/Open-GBP>; the former
Gitea remote is an **archive**, non-canonical, never pushed to. The operational
layer lives there and nowhere else:

- **Issues** are the unit of work: one bounded checkpoint each, written by the
  Orchestrator, executed by the Executor, decided by the Operator when a
  direction is needed. Comments are the handoff / status trail.
- **Milestones** mirror `docs/ROADMAP.md` phases; the ROADMAP owns their meaning.
- **Labels**: exactly one `stage:*` on an active Issue (`backlog`, `ready`,
  `executor`, `hardware`, `validation`, `blocked`), plus `area:*`, `type:*`
  and `needs:hardware`. The Orchestrator moves them.
- **Project "Open-GBP Development"** is a visualisation layer over the Issues
  (coarse Status, Area, Work Type, Hardware). It has no authority.

**An Issue, label, milestone or Project field never promotes evidence status.**
Scientific authority stays in `docs/research/EVIDENCE.md`,
`docs/research/HARDWARE_TESTS.md` and the fixtures; project state in
`docs/HANDOFF.md`; direction in `docs/ROADMAP.md`. Closing an Issue records
that work happened, not that a claim is true. Templates live under `.github/`.

## What this repository will not do

Physical experiments are cheap to get wrong and expensive to repeat. Before
asking for a hardware run, exhaust: static analysis, host unit tests, synthetic
vectors, mock transports, trace replay, PowerPC compile/link checks, binary
inspection, Dolphin. Only then is the real Game Boy Player worth the trip.

No hardware is ever tested with a `-dirty` build.
