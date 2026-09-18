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

**Status: COMPLETE (2026-09-16).** Detection (seven GBP-attached runs, two
without the GBP), the CONTROL transform and the IRQ programming
(GBP-INIT-001…003A), the delivery of an HSP cause to the CPU (GBP-INIT-003B,
004) and the first complete service — drained AUDIO/VIDEO blocks,
acknowledge, re-arm, next cause captured while masked, stop sequence
(GBP-AV-SERVICE-001) — were executed on the physical GameCube + Game Boy
Player with independent code (`docs/research/HARDWARE_TESTS.md`,
`docs/protocol/INITIALIZATION.md` §14, DEVLOG 2026-09-16 "GBP-AV-SERVICE-001
executed"). The closing criterion recorded in the DEVLOG (first physical
service → re-arm → next cause) is met; the remaining microscopic unknowns
(U-GBP-027 investigative sub-items, U-GBP-028, the bit-15 mechanism of
U-GBP-007) are documented as non-blocking. Sustained operation over many
cycles is Phase 4 and later work.

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

**Status: IN PROGRESS (entered 2026-09-16).** Transport, block sequence and
**colour** are now physically established (GBP-AV-SERVICE-001, GBP-VIDEO-001,
GBP-VIDEO-003); rendering and a moving image are not. **U-GBP-011 closed
2026-09-18** by the pre-registered confirmatory run `color-0002`: the VIDEO
window exchanges the two outer 5-bit groups relative to the AGB framebuffer, so
the references' GX RGB5A3 reading is the displayed colour (GBP-HW-131). GBP-VIDEO-002 has now been run
physically **four** times (`vstate-0001`, `vstate-0002`, `vstate-0003`,
`vstate-0004`); the last two reached the 120 s target, and the fourth validated
the semantic-disagreement policy with trustworthy diagnostics, which **unblocks
GBP-VIDEO-003**. The entry experiment
GBP-AV-SERVICE-001 captured the first physical VIDEO (0xF00) and AUDIO
(0x1000) blocks with one whole-block DMA each and preserved them raw
(fixture + sidecar). Static basis fixed on 2026-09-16
(`docs/research/VIDEO_PATH.md`): both references read a block as 4 raster
lines × 240 pixels × 4 bytes (bytes 1/3 of each word), 40 blocks per frame,
frame flag on the first pixel, and 15 colour bits which both *read* in GX
RGB5A3 order — which was a property of the two decoders until GBP-VIDEO-003
measured the device and confirmed it (U-GBP-011 CLOSED); both embed the AGB idle screen
(an offline oracle without a cartridge). Short sequence:

* **GBP-VIDEO-001** (**PHYSICALLY EXECUTED 2026-09-16**, `video-0001`, commit
  `6930dde`; `poc/gbp-video-capture-probe/`): 209 cycles of repeated drained
  service, 88 VIDEO and 144 AUDIO blocks, one complete 40-block frame-start
  interval at 59.547 Hz, both predicates agreeing on all 88 blocks, a uniformly
  white frame matching the references exactly where they are white. Originally
  planned as:
  bounded repeated drained service, no cartridge — up to 88
  VIDEO blocks with timestamps, both frame-start predicates, the source
  pattern per cause; establishes blocks per frame, order, boundaries,
  cadence and repeated-service stability; offline assembly against the
  embedded idle screen.
* **GBP-VIDEO-002** (**PHYSICALLY EXECUTED 2026-09-16**, `vstate-0001`, commit
  `e8f3a69`, `poc/gbp-video-state-probe/`): 51 751 service cycles over 8.187 s,
  489 frames, 477 intervals of exactly 40 blocks at 59.727 Hz, and a structured
  screen that appears 0.5 s after the AGB starts, animates, and settles into a
  state matching **GBI reference table B in all forty blocks**. Reconstructing
  the preserved raw frames gives a legible animated GAME BOY logotype at
  240 × 160, which promotes the block geometry to a physical fact
  (GBP-HW-074…087). The service ABORTED at cycle 51 750 on a semantic
  disagreement between the two readings of the IRQ register whose bytes were not
  preserved (U-GBP-032), so the 120 s negative target was not reached and this
  run makes no negative claim. Originally designed as: a **120-second**
  frame-signature scan without a Game Pak, sized
  to the nominal interval of the Start-up Disc's own detector window (24 000
  invocations of a 5.000 ms periodic callback, proved from the binary; 120 s is a
  lower bound because the scheduler drops missed periods). Per-frame signatures of 40
  checksums instead of per-delivery records (~639 000 deliveries are expected),
  a u64 time base because a u32 tick wraps at 106 s, a learned baseline, and an
  episode state machine that preserves raw frames around a change and closes when
  the changed state repeats, with **no early stop** — the runtime has no oracle,
  so it cannot know which stable state is the one sought, and the run observes
  the whole window and records every episode for offline classification. The
  120 s are counted **after** baseline_valid,
  because only then is there a reference to compare against; the frame store and
  a 180 s hard wall-clock limit are safety caps, not the window. Answers whether the screen
  both references recognise ever reaches the VIDEO stream without a cartridge
  (U-GBP-031) and gives a cadence uniform from the first useful frame
  (U-GBP-030). The implementation reuses the physically validated interrupt path
  byte for byte, adds a 64-bit time base because a 32-bit tick counter wraps
  inside the window, tears the hardware down before it summarises anything, and
  streams its multi-megabyte sidecar rather than staging it. Its full nominal
  scan runs in the host suite at about 800 000 synthetic deliveries.
* **GBP-VIDEO-003**: colour. **DESIGN FINALIZED and IMPLEMENTED 2026-09-17
  (HARDWARE_TESTS §V3.0 to §V3.25); PHYSICALLY EXECUTED twice on 2026-09-18 — the
  result is in the dedicated bullet below and in §V4.10.** The first
  implementation was blocked by the microaudit for doing full-frame
  `memcmp`/`memcpy` between the ACK and the RE-ARM; the capture now decides
  stability from the 40 per-block signatures the model already computes, never
  touches a frame's bytes, and the certified frames stay in a four-slot ring
  until the writer streams them after the teardown (§V3.23 to §V3.25). Three components
  exist: the AGB stimulus (`stimulus/agb-color-bars`), the probe
  (`poc/gbp-video-color-probe`, Build ID `color-0001`) and the offline analyser
  (`tools/vcolor.py`), with the `OGBPCOL1` v1 sidecar between them. A controlled AGB Mode 3
  stimulus of eight 30-pixel bars — three full 5-bit groups, three single low
  bits, plus `0x0000` and `0x7FFF` as permutation-invariant controls, with bit 15
  never written — captured through the validated service path into a dedicated
  `OGBPCOL1` sidecar that preserves whole raw blocks. Exactly one candidate
  transformation must reproduce all eight observed values or the run is
  INCONCLUSIVE. The execution dependency this bullet used to carry — no known way
  to deliver a controlled GBA ROM to the physical unit — was **RESOLVED on
  2026-09-18** by the operator's EZ-Flash Omega DE in NOR / Mode B, route 1 of
  §V3.7, with the predicted `CONTROL orig=92` presence bit observed.

  The gate that used to block this step is gone. It was a run surviving the
  semantic disagreement of the IRQ window with trustworthy diagnostics, and
  `vstate-0004` delivered it: **29 `SOURCE_SERVICED` disagreements, none fatal,
  correct current-cycle attribution in 29 of 29, 120.009 s of valid observation**
  (GBP-HW-108…115). It was never gated on U-GBP-033, which stays open — the
  mechanism behind the replica non-uniformity does not have to be understood,
  only survived, and it has now been survived 52 times across two long runs.

  The experiment needs a source whose true appearance is known independently of
  the references, because a reference comparison can only show that two encodings
  agree, never which channel is which. That is what the eight-bar stimulus is:
  every value known by construction, the low-bit bars making an intra-channel
  reversal falsifiable, and the popcount fingerprint letting the probe recognise
  the pattern without assuming the answer.
  Rendering the frames on the GameCube is deliberately **not** part of this
  experiment: the mapping is decided from preserved raw bytes offline, and a
  texture drawn under an assumed channel order would prove nothing about the
  device. First rendered frames and KEYPAD writes belong to a later step. The
  gate that guarded this one existed because both early GBP-VIDEO-002 runs ended
  on a semantic disagreement of the IRQ window (2026-09-16 at cycle 51 750,
  2026-09-17 at cycle 517), and a colour capture cannot afford an abort at an
  arbitrary point; the nonfatal policy validated by `vstate-0004` is what removed
  that risk, and GBP-VIDEO-003 reuses it unchanged (§V3.9).
* **GBP-VIDEO-002-R3** (build `vstate-0003`): the intervening step, **PHYSICALLY
  EXECUTED 2026-09-17**. It reached the 120 s scientific target, observed the
  structured change again, and survived 23 semantic disagreements without stopping
  — the policy behaviour is strongly corroborated. Its diagnostic records, however,
  carry current-cycle fields belonging to later cycles (GBP-HW-104), so R3's
  physical validation is **INCOMPLETE** and **GBP-VIDEO-002-R4** (build
  `vstate-0004`, OGBPSEQ1 v5, **designed 2026-09-17, not implemented**) must fix the
  attribution and be run before the gate below opens. Makes a disagreement confined to the two
  serviced source bits a counted, preserved, nonfatal anomaly serviced from GBI's
  bitwise majority; keeps every other difference fatal, and keeps the independent
  `anomaly_unexpected_source` guard firing on the authoritative value whatever the
  delta is. Records, for each event, whether the source the majority omitted was
  present in the next cause and how long after the re-arm — as observations, with
  no runtime label claiming a source could not be new. Quarantines any VIDEO block
  drained only because the majority carried a source the Disc reading did not, so
  it can never form a baseline, count toward valid observation, validate a
  structured change or feed colour evidence. Adds a bounded 256-record diagnostic
  store (+41 728 B) and OGBPSEQ1 v4; v1, v2 and v3 stay frozen.
* **GBP-VIDEO-002-R4** (build `vstate-0004`): **PHYSICALLY EXECUTED 2026-09-17,
  PHYSICAL VALIDATION PASSED.** It reached the 120 s target again (1 114 005
  cycles over 175.848 s), survived **29** semantic disagreements, and produced a
  sidecar in which every record carries the authoritative value, service decision,
  ACK and re-arm of its own cycle — strict-valid under the v5 cross-field rules,
  zero producer warnings. That completed R3's physical validation. Fixes the one
  defect the physical
  `vstate-0003` run exposed: the v4 producer addresses the current cycle's
  diagnostic record as "the last record opened", so a record that is not closed in
  its own cycle absorbs the authoritative value, service decision, ACK and re-arm
  of later cycles (GBP-HW-104). R4 replaces that with an explicit record handle
  carried by the cycle, separates the two lifetimes (current-cycle fields end with
  the cycle, follow-up fields stay open across cycles) and emits OGBPSEQ1 v5, whose
  semantic block records which fields each record actually owns. The observed
  policy behaviour does not change: the same three disagreement classes, the same
  authority composition, the same independent pending guard, the same
  quarantine. OGBPSEQ1 v4 stays frozen as the historical format of the
  `vstate-0003` run. Design, implementation and physical result in HARDWARE_TESTS
  §R4.1 to §R4.10a. Only the `SOURCE_SERVICED` / Disc-extra path was exercised
  physically; the producer's other branches stay host- and mock-tested.
* **GBP-VIDEO-003** (**PHYSICALLY EXECUTED twice 2026-09-18**): `color-0001`
  certified but failed its own pre-registered full-raw gate and stays
  INCONCLUSIVE permanently; `color-0002`, judged by the contract
  pre-registered in HARDWARE_TESTS §V4, returned
  `CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP` and closed U-GBP-011
  (GBP-HW-120…126, GBP-HW-127…133).
* **GBP-VIDEO-004** — **NEXT**: sustained streaming with a real cartridge (frame
  pacing, dropped-block policy, output modes) — the bridge to Phase 7.
  **DESIGN / PRE-REGISTRATION written 2026-09-18, HARDWARE_TESTS §V5; not
  implemented, not run.** It defines the producer/consumer boundary that keeps
  every frame operation out of the validated service path, a bounded drop-oldest
  queue, `HOLD_PREVIOUS_FRAME` as the display policy with no synthesised pixels, a
  `GX_TF_RGB5A3` output path that needs no channel arithmetic because GBP-HW-131
  established the device already performs the swap, and a CONTROLLED motion
  stimulus with an embedded frame index so that frame loss is measured rather
  than inferred. This is also where the "first rendered frames" that
  GBP-VIDEO-003 deliberately deferred belong.

No further micro-probes unless one of these raises a blocking question.

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
