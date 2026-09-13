# Open-GBP Roadmap

This roadmap intentionally separates Game Boy Player research from later Mobile Adapter work.

Each phase should have explicit acceptance criteria before later layers are allowed to depend on it.

## Phase 0 — Reproducible development environment

Establish a reproducible GameCube development environment.

Requirements:

* pinned Docker image;
* devkitPPC available;
* libogc2 available;
* `gamecube_rules` available;
* `elf2dol` available;
* host files created with the normal user UID/GID;
* repeatable build commands.

Acceptance:

```text
A clean checkout can enter the development container and build
GameCube software without installing devkitPPC on the host.
```

## Phase 1 — Project and test infrastructure

Create the initial source layout and automated test framework.

The first GameCube program should be created by the development agent itself so that the build system is understood from the beginning.

Initial targets:

```text
poc/smoke-test/
tests/
tools/
```

Testing infrastructure should support:

* native host-side tests;
* mock hardware transports;
* deterministic test vectors;
* trace recording and replay;
* build identifiers;
* test IDs;
* machine-readable logs where useful.

Acceptance:

```text
Native tests run automatically.
A minimal GameCube DOL builds reproducibly.
The DOL can be smoke-tested without changing physical GBP state.
```

## Phase 2 — Reference analysis and hardware documentation

Study available sources before inventing behavior.

Primary references may include:

* original Game Boy Player Startup Disc owned by the user;
* Dolphin Game Boy Player HSP implementation;
* public libogc2 code;
* Game Boy Player Player hardware research;
* later, Game Boy Interface binaries owned by the user.

Enhanced mGBA may be used for generic GameCube infrastructure but must not be treated as an implementation of the physical Game Boy Player.

Produce documentation for:

```text
GameCube HSP
GBS-DOL
register map
transaction format
initialization
interrupt behavior
known/unknown bits
```

Acceptance:

```text
Every implemented hardware operation has documented provenance,
confidence level, and an automated representation where practical.
```

## Phase 3 — Physical GBP detection and initialization

Create a standalone open-source GBP runtime/probe.

Goals:

* identify the physical GBP;
* perform the minimum safe initialization sequence;
* read relevant status;
* establish deterministic logging;
* avoid speculative writes to unknown registers.

Diagnostics should support:

* on-screen state;
* RAM event buffering;
* SD2SP2 trace/log export.

Acceptance:

```text
The software reliably detects and initializes the physical GBP
on real hardware without relying on proprietary runtime code.
```

## Phase 4 — Video

Implement and document the physical GBP video path.

Automated tests should cover:

* packet/register encoding;
* buffer boundaries;
* frame conversion where applicable;
* deterministic synthetic frame inputs;
* recorded hardware trace replay.

Acceptance:

```text
A real cartridge running on the physical GBP produces stable,
correct video through the open-source runtime.
```

## Phase 5 — Input

Implement and document GameCube controller → GBP keypad/input handling.

Automated tests should cover button combinations and encoding.

Acceptance:

```text
A real game can be controlled reliably using the GameCube controller.
```

## Phase 6 — Audio

Implement and document the GBP audio path.

Automated tests should cover buffering, state transitions, and malformed/edge input where practical.

Acceptance:

```text
A real cartridge produces stable audio without breaking video/input.
```

## Phase 7 — Cartridge compatibility

Validate both execution families:

```text
GBA mode
GB/GBC compatibility mode
```

Do not assume behavior observed in GBA mode also applies to GB/GBC mode.

Acceptance:

```text
Representative GBA and GB/GBC cartridges run with video, input,
and audio through the physical Game Boy Player.
```

## Phase 8 — Physical Link Port regression

The user's PicoAdapterGB already proves that the physical GBP Link Port supports normal serial communication.

This phase verifies that Open-GBP has not broken that behavior.

Tests should include the normal external path:

```text
cartridge
   ↕
physical GBP Link Port
   ↕
PicoAdapterGB
```

Acceptance:

```text
PicoAdapterGB continues to work when internal Mobile Adapter
functionality is disabled.
```

This is a permanent regression requirement for later phases.

## Phase 9 — GBI-class functional parity

After the basic physical Game Boy Player runtime is stable, expand Open-GBP
toward functional parity with mature Game Boy Player software such as Game
Boy Interface.

This phase may include:

- additional video modes and presentation options;
- scaling and filtering controls;
- timing and latency improvements;
- configuration handling;
- compatibility fixes;
- runtime robustness;
- other features useful for normal Game Boy Player operation.

GBI may be analyzed as a behavioral and reverse-engineering reference, but
Open-GBP should remain an independently implemented open-source project.

Acceptance:

```text
Open-GBP can be used as a practical replacement for normal Game Boy Player
operation without requiring proprietary runtime software.
```

## Phase 10 — Internal SIO research

Investigate whether GameCube-side software can observe and/or drive the cartridge's serial communication internally through GBS-DOL/HSP.

Questions include:

* SIO control register semantics;
* SIO data register semantics;
* serial interrupt behavior;
* routing between internal HSP handling and the physical Link Port;
* GBA-mode behavior;
* GB/GBC-mode behavior;
* coexistence or exclusivity of internal and external communication.

Testing should begin read-only whenever possible.

Acceptance milestone A:

```text
GameCube software observes a deterministic serial event generated
by software running on the physical GBP.
```

Acceptance milestone B:

```text
GameCube software generates a deterministic response that is
observed by software running on the physical GBP.
```

Acceptance milestone C:

```text
The behavior required for GB/GBC operation is characterized.
```

## Phase 11 — Network/BBA

Network support is developed independently of Mobile Adapter logic.

Create a dedicated network POC and host-side test server.

Validate:

```text
BBA initialization
IP configuration
UDP
TCP
DNS if required
timeouts
nonblocking behavior
```

Timing-sensitive serial processing must never block on network I/O.

Acceptance:

```text
A standalone GameCube application can reliably exchange test traffic
with an automated host-side server.
```

## Phase 12 — Runtime stabilization and architecture

At this stage Open-GBP is expected to be a standalone open-source runtime
for the physical Game Boy Player.

Stabilize the architecture and public boundaries between:

- physical GBP/HSP transport;
- video, audio, input, and cartridge runtime;
- Link/SIO handling;
- networking;
- application-specific extensions.

Potential outputs include:

- the standalone Open-GBP application;
- a reusable GBP library;
- diagnostic applications;
- documentation;
- trace and research tools.

Integration with other frontends may be explored, but it is secondary to
the standalone Open-GBP runtime.

Game Boy Interface may continue to be used as a behavioral and
reverse-engineering reference. Open-GBP must not require GBI or another
proprietary runtime in order to operate.

Acceptance:

```text
Open-GBP has a stable standalone runtime and documented API boundaries
between GBP hardware transport, core runtime behavior, networking, and
application-specific extensions.
```

## Phase 13 — Mobile Adapter GB

Only after the previous GBP/SIO/network milestones are satisfied should Mobile Adapter integration begin.

Existing work from other projects/agents may then be consulted, including:

* PicoAdapterGB implementations;
* mGBA-related implementations;
* BGB/libmobile work;
* Mobile Adapter protocol documentation;
* existing libmobile code.

The preferred architecture is:

```text
physical cartridge
       ↓
real GBP serial interface
       ↓
Open-GBP SIO transport
       ↓
Mobile Adapter protocol layer
       ↓
nonblocking network backend
       ↓
GameCube BBA
```

The Mobile Adapter layer must remain separable from the GBP hardware layer.

Acceptance:

```text
A compatible real game running on the physical GBP communicates
through the GameCube as if a Mobile Adapter GB were attached,
while normal physical Link Port behavior remains available when
the feature is disabled.
```
