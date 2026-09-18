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

## What this repository will not do

Physical experiments are cheap to get wrong and expensive to repeat. Before
asking for a hardware run, exhaust: static analysis, host unit tests, synthetic
vectors, mock transports, trace replay, PowerPC compile/link checks, binary
inspection, Dolphin. Only then is the real Game Boy Player worth the trip.

No hardware is ever tested with a `-dirty` build.
