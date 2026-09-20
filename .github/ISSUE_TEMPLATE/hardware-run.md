---
name: Physical hardware run
about: A pre-registered physical run on the real GameCube + Game Boy Player, performed by the Operator
title: "[Hardware] <EXPERIMENT-ID> — RUN <N> — <build-id>"
labels: ["stage:hardware", "type:hardware", "needs:hardware"]
---

<!--
Physical hardware is the final authority (AGENTS.md). A run is worth the trip
only after static analysis, host tests, synthetic vectors, replay and Dolphin
are exhausted. Gates are frozen BEFORE the hardware is touched and are not
renegotiated after the result is seen (docs/RESEARCH_METHOD.md).
Operator observations are recorded literally as OPERATOR OBSERVATION.
-->

## Experiment ID / global run number

`GBP-<AREA>-NNN` · RUN `<N>` (global run numbers are never reused).

## Question answered

One sentence. A run answers a specific research question.

## Artifact identity

build id · commit (CLEAN, no `-dirty`) · DOL SHA-256 · size · Swiss slot
(`build/swiss/NN-…/boot.dol` is a byte copy, not a second identity).

## Stimulus / cartridge

Name · SHA-256 · flashed or not since the previous run.

## Topology (Operator declares, literally)

BBA present / absent · Ethernet · Link Port state · same console and GBP as
run `<N-1>` · anything intentionally different (ONE variable per experiment).

## Pre-registered gates

Pointer to the `docs/research/HARDWARE_TESTS.md` section that freezes
PASS / FAIL / INCONCLUSIVE, and the list of gates reused unchanged.

## Reserved raw-file names

`captures/local/<EXPERIMENT>_<build>-run<N>.log` · `…-idxcap.bin` · `…-disp.bin`
— reserved BEFORE the run; the console's generated names never overwrite an
earlier run (`captures/README.md`).

## Operator procedure

1. Power fully OFF · 2. media / cartridge / topology as declared · 3. launch ·
4. do not interact · 5. wait for READY / the stop condition · 6. press X to
save · 7. power-cycle if the procedure says so · 8. return the files.

## Operator declaration and observations

Recorded literally, in the operator's words.

## Returned artifacts

Names as generated · sizes · the Operator's `sha256sum` (a double check; the
Executor recomputes identities first).

## Stop condition

The Executor ingests the run in a separate checkpoint Issue; classification
follows the pre-registered gates only.
