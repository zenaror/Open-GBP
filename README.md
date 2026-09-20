# Open-GBP

Open-source research, documentation, tooling, and software for programming the **physical Nintendo Game Boy Player** from the GameCube.

The project focuses on the real Game Boy Player hardware attached to the GameCube High-Speed Port. It does **not** use software emulation of the Game Boy, Game Boy Color, or Game Boy Advance as the final execution path.

## Project scope

The long-term goal of Open-GBP is to provide an open-source runtime for the
physical Nintendo Game Boy Player with compatibility and functionality
comparable to mature solutions such as Game Boy Interface.

The project should ultimately support the normal Game Boy Player use cases
without sacrificing existing hardware functionality:

- real GB, GBC, and GBA cartridges;
- video;
- audio;
- GameCube controller input;
- physical Link Port peripherals;
- existing devices such as PicoAdapterGB;
- GBP-aware game features supported by the Start-up Disc and/or GBI, such as
  rumble on the GameCube controller and GBP-dependent game modes, with their
  controller/input behavior (part of normal compatibility, not an option);
- configurable presentation and runtime features where practical.

Mobile Adapter GB support is an additional feature built on top of this
foundation. It must not replace or break the normal physical Link Port path.

## Goals

Open-GBP aims to:

* document the GameCube ↔ High-Speed Port ↔ GBS-DOL ↔ AGB hardware interface;
* document Game Boy Player initialization, registers, interrupts, video, audio, input, Link/SIO behavior, and other relevant protocols;
* provide open-source tooling and reusable code for controlling the physical Game Boy Player;
* provide small diagnostic and proof-of-concept applications;
* build a reproducible test framework using mocks, synthetic tests, trace replay, Dolphin where applicable, and real hardware validation;
* preserve normal physical Link Port functionality;
* eventually investigate internal serial communication through the Game Boy Player for applications such as a virtual Mobile Adapter GB.

## Hardware target

The authoritative target is:

```text
GameCube
   │
   │ High-Speed Port
   ▼
Game Boy Player
   │
   ├── GBS-DOL
   │
   └── real AGB CPU
          │
          ▼
     physical cartridge
```

Game Boy, Game Boy Color, and Game Boy Advance software must run through the real Game Boy Player hardware.

## Current known hardware behavior

The physical Game Boy Player Link Port is already known to work normally with external peripherals.

In particular, **PicoAdapterGB has been successfully used through the physical Game Boy Player Link Port**.

Therefore, normal external serial capability is not an open research question.

One important research question is whether GameCube software can independently observe and drive that serial communication through the internal GBS-DOL/HSP interface.

## Mobile Adapter GB

Mobile Adapter GB support is a planned application of the project, not the initial implementation target.

Two different things carry that name. The **physical Mobile Adapter GB** is
a normal Link Port accessory: it must keep working through the physical
Game Boy Player Link Port like every other accessory (Link Cable
multiplayer with another Game Boy, official and compatible third-party
devices, PicoAdapterGB as one concrete regression case) — physical Link
Port compatibility is the permanent requirement of `docs/ROADMAP.md`
Phase 8. The **virtual Mobile Adapter GB over the GameCube BBA** is an
additional Open-GBP extension; it must not replace or degrade that path.

The development order is intentionally:

```text
Game Boy Player control
        ↓
video / input / audio
        ↓
GBA and GB/GBC compatibility
        ↓
physical Link Port regression
        ↓
internal SIO research
        ↓
BBA/network support
        ↓
Mobile Adapter integration
```

`libmobile` or equivalent Mobile Adapter protocol integration must not become a dependency of the early Game Boy Player implementation.

## Research philosophy

Hardware behavior should not be inferred from a single source when it can be verified independently.

The project distinguishes between:

* confirmed observations;
* corroborated behavior;
* hypotheses;
* unknown behavior.

Experimental findings are first recorded under `docs/research/`. Once sufficiently established, they are promoted into the technical documentation under `docs/hardware/` or `docs/protocol/`.

The long-term objective is to produce documentation useful in the same spirit as projects such as Pan Docs: documentation that allows another developer to program the hardware without having to repeat the original reverse engineering.

## Testing philosophy

Physical hardware is the final authority, but manual hardware testing should be minimized.

Before requesting a GameCube test, the project should use as many of the following as applicable:

```text
host-side unit tests
        ↓
synthetic hardware models / mocks
        ↓
recorded trace replay
        ↓
PowerPC compilation checks
        ↓
Dolphin
        ↓
physical GameCube + Game Boy Player
```

A physical hardware test should answer a question that cannot reasonably be answered at an earlier level.

Hardware tests should produce persistent logs or traces whenever practical. SD2SP2 is available for this purpose.

Timing-critical HSP/SIO paths must record events into RAM first and flush them to storage outside the critical path.

## Repository layout

```text
docs/
    hardware/        Hardware architecture documentation
    protocol/        Consolidated programming/protocol reference
    research/        Evidence, experiments, unknowns, development log
    mobile-adapter/  Future Mobile Adapter-specific documentation

poc/                 Small GameCube proof-of-concept programs
tests/               Host-side and synthetic automated tests
tools/               Development and reverse-engineering utilities
captures/            Hardware traces and test captures
input/               Private local binary inputs, never committed
external/            Local reference repositories, never committed
build/               Generated build outputs
```

## Development environment

GameCube software is built in Docker using a pinned libogc2/devkitPPC environment.

Current base image:

```text
ghcr.io/extremscorner/libogc2:20260805
```

The host does not need a separate devkitPPC installation.

## Private reference material

Locally owned binaries such as the original Game Boy Player Startup Disc image or Game Boy Interface executables may be used for interoperability research.

They must remain under `input/`, must not be committed, and must not be redistributed as part of this project.

## Status

Early research and infrastructure stage.

The first implementation milestone is an open-source program capable of initializing and controlling the physical Game Boy Player while building a documented and testable understanding of the hardware interface.

Reached so far on physical hardware, each with a scope that is deliberately narrow and recorded in full in [`docs/HANDOFF.md`](docs/HANDOFF.md):

- **Physical real-cartridge video output** — a real GBA cartridge's picture, produced by the real Game Boy Player, presented on physical GameCube output.
- **Basic sustained streaming**, operationally reached for the window exercised.
- **Controlled steady-state source-frame continuity observed on physical GBP** — within a scientific window whose qualification rule was frozen *before* the run that produced it, the preserved source-frame IDs were contiguous and ordered across every transition the frozen analyzer treats as decisive.

The third of these says something precise and nothing more. It does **not** mean zero frame loss, guaranteed pacing, a lossless display pipeline, pixel-perfect full frames or 60 FPS, and it covers only the 4 320 bytes per frame that the indexed stimulus preserves as evidence. The exact wording, the numbers behind it and the list of what it does not prove live in [`docs/research/EVIDENCE.md`](docs/research/EVIDENCE.md) and [`docs/research/HARDWARE_TESTS.md`](docs/research/HARDWARE_TESTS.md); where this summary and those documents differ, they win.

## Continuing development with an AI or code agent

The supported way to pick this project up — with no chat history, by any agent
or by a person — is the handoff:

- **[`AGENTS.md`](AGENTS.md)** — the rules any agent must read before touching
  anything: the authority hierarchy, the evidence vocabulary, and what must
  never be claimed.
- **[`docs/HANDOFF.md`](docs/HANDOFF.md)** — the current scientific and
  operational state, the frozen contracts, the exact artifacts that were
  physically executed, the current blocker and the next safe action.

`docs/HANDOFF.md` is an index, not evidence: every entry points at the document
that owns it. It also carries a staleness check, because a handoff is not true
merely because it exists.

To hand the project to a new agent, paste the **canonical resume prompt** from
[`docs/HANDOFF.md`](docs/HANDOFF.md#canonical-resume-prompt). It is
vendor-neutral, it tells the agent to reconstruct the state from the repository
rather than from anyone's memory, and it stops the agent before implementation
so you can confirm what it reconstructed.


**Roles.** The project separates three responsibilities — OPERATOR (hardware
and human observation), ORCHESTRATOR (review, validation, planning, gates) and
EXECUTOR (implementation, tests, builds, evidence ingestion, commits). They are
responsibilities, not vendors or models; any seat may be a human or an AI and
may change independently. The permanent definition and the checkpoint discipline
live in [`AGENTS.md`](AGENTS.md); the current assignment is in
[`docs/HANDOFF.md`](docs/HANDOFF.md).

## AI Notice

AI tools such as Claude were used in this project.

They were used for research, analysis of captured hardware evidence, documentation
and code. Every hardware claim in `docs/` is classified (FACT, CORROBORATED,
HYPOTHESIS, UNKNOWN) and traceable to a physical log or a named reference, and the
physical logs under `logs/` and the fixtures under `captures/fixtures/` come from
the real console, not from a model.
