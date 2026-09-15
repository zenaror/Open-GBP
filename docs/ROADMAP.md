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

### GBP-aware game features (requirement added 2026-09-15)

Parity with the Nintendo Game Boy Player Start-up Disc and with GBI is not
limited to video, audio, input and cartridge boot. Some games behave
differently when they detect that they run on a Game Boy Player, and the
Start-up Disc / GBI support that behavior; the runtime must aim to
reproduce it as part of normal compatibility, not as an optional feature:

* rumble on the GameCube controller for games that support it through
  the Game Boy Player;
* any GBP-dependent game mode or behavior supported by the Start-up Disc
  and/or GBI;
* the controller/input behavior associated with those features;
* every GBS-DOL signal, register, IRQ or path required to reproduce them.

The mechanism (which path carries the GBP detection and the rumble
commands — the internal serial path documented by GBATEK's "GBA Gameboy
Player" section is the leading candidate, U-GBP-026) is not assumed; it
is researched from the Start-up Disc, GBI, physical behavior, games known
to exercise the feature, and the references already accepted. When the
controller/cartridge-compatibility phases are reached, a compatibility
matrix specific to GBP-aware features, rumble included, is created.

Compatibility goal:

```text
If a game has a special behavior supported by the original Game Boy
Player or by GBI, Open-GBP must aim to reproduce that behavior.
```

## Phase 8 — Physical Link Port compatibility regression

The physical Game Boy Link Port is a first-class compatibility requirement.

Open-GBP must preserve the normal external serial behavior of the Game Boy
Player and must not make the Link Port dependent on Open-GBP-specific hardware
or protocols.

PicoAdapterGB is one known-good regression device and provides existing
physical evidence that normal serial communication through the GBP Link Port
works, but it is only one test case.

The scope of this phase is the physical Link Port itself and the normal
accessories/protocols used through it, including, where applicable:

- Game Boy Link Cable communication with another physical Game Boy;
- multiplayer/link features used by compatible games;
- official Game Boy Link Port accessories;
- physical Mobile Adapter GB;
- PicoAdapterGB;
- compatible third-party accessories;
- other normal serial modes exercised by cartridges through the Link Port.

Normal external communication must remain a transparent hardware path:

cartridge
   ↕
physical GBP Link Port
   ↕
external accessory / another Game Boy

Open-GBP must not require knowledge of a particular external accessory for this
path to operate normally.

Tests should therefore include multiple representative Link Port use cases,
rather than treating PicoAdapterGB as the compatibility target.

Acceptance:

- normal physical Link Port behavior remains compatible with the original
  Game Boy Player environment;
- multiplayer communication with a physical compatible Game Boy continues to
  work;
- PicoAdapterGB continues to work;
- physical accessories are not broken by Open-GBP initialization, IRQ,
  controller, audio/video, or shutdown handling;
- future internal serial functionality does not alter the external Link Port
  path when that functionality is disabled.

The future virtual Mobile Adapter implementation over the GameCube BBA is an
additive Open-GBP feature. It must not replace the physical Link Port or make
physical Link Port compatibility dependent on the virtual Mobile Adapter
implementation.

This is a permanent regression requirement for all later phases.

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

GBI-class parity includes the GBP-aware game features listed under
Phase 7 (rumble and GBP-dependent modes); their compatibility matrix
belongs to this phase and to Phase 7, with Phase 10 supplying the serial
mechanism if that is where the feature lives.

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

The Mobile Adapter extension over the BBA is **additive**. It must not
break or replace: the physical Link Port; PicoAdapterGB; rumble and the
other GBP-aware game features; normal GB/GBC/GBA operation; behavior
compatible with the Start-up Disc / GBI.

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
