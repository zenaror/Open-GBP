---
name: Checkpoint / work item
about: A bounded operational checkpoint for the Executor (code, docs, tests, builds, audits, evidence ingestion)
title: "[Area] Short imperative title"
labels: ["stage:backlog"]
---

<!--
Roles: the Orchestrator writes and owns this Issue; the Executor executes it;
the Operator decides project direction when a decision is needed.
Labels: exactly one `stage:*`, plus `area:*` and `type:*`. Milestone = ROADMAP phase.
This Issue coordinates work. It never promotes evidence status: that belongs to
docs/research/EVIDENCE.md, docs/research/HARDWARE_TESTS.md and the fixtures.
-->

## Status

Backlog / Ready for Executor

## Role owner

Orchestrator (author) → Executor (executes) → Orchestrator (validates).

## Objective

One paragraph: what this checkpoint delivers and why now.

## Authorised scope

- files / modules / documents that may change;
- what "done" looks like.

## NOT authorised

- runtime, analyzers, frozen formats, fixtures, evidence status, roadmap order,
  hardware, networking … (list what is explicitly out of scope).

## Acceptance / pre-registered gates

- tests, audits, emulator checks, document consistency;
- for any physical claim: the gate must already be pre-registered in
  `docs/research/HARDWARE_TESTS.md` before the hardware is touched.

## Hardware requirement

None / Required — if required, open a **Physical hardware run** Issue, link it
here and add `needs:hardware`.

## Artifact identity (when a DOL or stimulus is involved)

build id · commit (clean, no `-dirty`) · DOL SHA-256 · size · Swiss slot ·
stimulus SHA-256. Computed by the Executor first; the operator's media hash is a
double check.

## Tests / evidence expected

Focused tests, full applicable suites, audits, Dolphin where useful; fixtures
and research records to update.

## Commits / push

Logical commits, one technical purpose each (`CLAUDE.md` §24). Push to
`origin` (GitHub) is authorised by this Issue when it says so.

## Stop condition

Post the executor report here (starting HEAD, commits, files, tests, hashes,
final HEAD, `git status`), then STOP. Close only when this Issue says the
Executor may; otherwise move it to `stage:validation`.
