# CLAUDE.md — Open-GBP Development Rules

> **Read [`AGENTS.md`](AGENTS.md) and [`docs/HANDOFF.md`](docs/HANDOFF.md)
> first.** `AGENTS.md` is the agent-neutral entry point — the authority
> hierarchy, the evidence vocabulary and the rules every agent must follow, not
> only Claude. `docs/HANDOFF.md` carries the current state, the current blocker
> and the next safe action.
>
> This file holds the **permanent project policies**: build environment, private
> inputs, testing and commit discipline, hardware-safety rules. They apply to
> every agent and to human contributors; nothing here is Claude-specific except
> the file's name and history. Where this file and `AGENTS.md` overlap,
> `AGENTS.md` is the authority on evidence handling and `CLAUDE.md` on project
> policy.

## 1. Read this first

Before modifying code or documentation, read completely:

1. `README.md`
2. `docs/ROADMAP.md`
3. `docs/RESEARCH_METHOD.md`
4. `docs/research/EVIDENCE.md`
5. `docs/research/UNKNOWNS.md`
6. `docs/research/HARDWARE_TESTS.md`
7. `docs/research/DEVLOG.md`

These files define the project scope, research methodology, development order, and current knowledge.

`docs/HANDOFF.md` indexes where the project currently stands and what the next
safe action is; read it alongside the list above.

Do not infer project goals solely from source code or previous conversation context.

---

## 2. Project mission

Open-GBP is an independently implemented, open-source runtime, documentation set, research environment, and tooling ecosystem for the **physical Nintendo Game Boy Player**.

The final target is the real hardware path:

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

Open-GBP must not use GBA/GB/GBC software emulation as the final execution path.

The long-term runtime should support normal Game Boy Player use with functionality comparable to mature software such as Game Boy Interface, while remaining independently implemented and open source.

The compatibility goal is functional parity with the Nintendo Game Boy
Player Start-up Disc and with GBI for normal Game Boy Player use, plus the
additional future extension over the GameCube BBA that implements a virtual
Mobile Adapter GB. The goal is NOT merely "boot games and show video": the
final runtime must aim to reproduce every relevant behavior the existing
implementations already support.

Expected long-term functionality includes:

- real GBA cartridges;
- real GB cartridges;
- real GBC cartridges;
- video;
- audio;
- GameCube controller input;
- timing and behavior the games expect;
- physical Link Port compatibility: Link Cable multiplayer with another
  physical Game Boy, official and compatible third-party Link Port
  accessories, the physical Mobile Adapter GB, PicoAdapterGB (one concrete
  regression fixture, not the scope);
- rumble through the GameCube controller in GBP-aware games;
- special modes and Game Boy Player-specific behaviors that games recognize;
- the IRQs, registers and mechanisms those features require;
- correct startup and stop sequences;
- useful configuration and presentation functionality;
- robust normal Game Boy Player operation;
- every other feature supported by the Start-up Disc and/or GBI;
- internal serial research;
- GameCube Broadband Adapter networking;
- optional Mobile Adapter GB functionality.

Do not assume in advance how rumble or the other special modes work:
research the mechanisms from the references and from the hardware.

Mobile Adapter support is an **extension**, not the foundation of the runtime.

---

## 3. Hard requirement: preserve normal Link Port behavior

The user's PicoAdapterGB already works through the physical Game Boy Player Link Port.

Therefore this is already established:

```text
physical cartridge
       ↕
real AGB serial/link hardware
       ↕
physical GBP Link Port
       ↕
PicoAdapterGB
```

Do not waste research time trying to prove that ordinary external Link Port communication exists.

Instead, preserve it.

**Physical Link Port compatibility is the permanent requirement**
(`docs/ROADMAP.md` Phase 8). Its scope is the physical Link Port itself and
every normal use of it: Link Cable multiplayer with another physical Game
Boy, official accessories, the physical Mobile Adapter GB, compatible
third-party accessories, PicoAdapterGB, and the other serial modes
cartridges exercise through the port. PicoAdapterGB is one concrete
regression fixture with existing physical evidence, not the compatibility
target.

When Mobile Adapter functionality is disabled, Open-GBP must not prevent normal external Link Port devices from working.

Keep the two Mobile Adapters apart: the **physical Mobile Adapter GB** is
a normal Link Port accessory that must keep working like any other; the
**virtual Mobile Adapter GB over the BBA** is an additional, additive
extension of Open-GBP.

The later Mobile Adapter mode should conceptually add another path:

```text
NORMAL MODE

cartridge
   ↕
physical Link Port
   ↕
PicoAdapterGB / cable / peripheral
```

versus:

```text
MOBILE ADAPTER MODE

cartridge
   ↕
internal serial path
   ↕
GBS-DOL / HSP
   ↕
Open-GBP
   ↕
virtual Mobile Adapter
   ↕
BBA
   ↕
Ethernet
```

Do not assume this internal serial path works as required. Prove it experimentally.

---

## 4. Mobile Adapter and libmobile are late-stage work

Do not begin integrating `libmobile`, PicoAdapterGB Mobile Adapter code, mGBA Mobile Adapter code, BGB-related Mobile Adapter work, or other Mobile Adapter implementations during early GBP development.

The required order is defined by `docs/ROADMAP.md`.

Establish independently:

1. reproducible build environment;
2. test infrastructure;
3. physical GBP detection and initialization;
4. video;
5. input;
6. audio;
7. GBA compatibility;
8. GB/GBC compatibility;
9. physical Link Port regression;
10. useful standalone runtime / GBI-class functionality;
11. internal SIO behavior;
12. BBA/network behavior;
13. stable runtime architecture.

Only after those foundations are sufficiently understood should Mobile Adapter protocol integration begin.

The purpose of this rule is to prevent Mobile Adapter-specific assumptions from contaminating the Game Boy Player research.

The future integration `GBP / GBS-DOL → GameCube → BBA → virtual Mobile
Adapter GB` is an **additive** feature of Open-GBP. It must not replace,
break or degrade: the physical Link Port and every normal accessory on it
(the physical Mobile Adapter GB and PicoAdapterGB among them); rumble; the
GBP-aware game features; normal GB/GBC/GBA compatibility; behavior already
reproduced from the Start-up Disc / GBI. Mobile Adapter / libmobile remains
a late stage of the project.

---

## 5. Documentation is a primary deliverable

Open-GBP is not only a software implementation.

A major project output is technical documentation that should eventually allow another developer to program the physical Game Boy Player without repeating the original reverse engineering.

Treat documentation with the same importance as source code.

The intended distinction is:

```text
docs/research/
    exploratory observations
    evidence
    hypotheses
    unknowns
    failed experiments
    hardware tests

docs/hardware/
    consolidated hardware architecture

docs/protocol/
    consolidated programming/protocol reference
```

Research information must not silently become authoritative documentation.

Follow the evidence and promotion process defined in `docs/RESEARCH_METHOD.md`.

Whenever a hardware discovery is made:

1. record the observation;
2. record the source/test;
3. assign an evidence status;
4. record unresolved ambiguity;
5. create a synthetic or replay test where practical;
6. only then promote sufficiently supported information into `docs/hardware/` or `docs/protocol/`.

Do not invent names or bit meanings merely to make documentation look complete.

Unknown behavior should remain explicitly unknown.

---

## 6. Primary research sources

Use multiple independent sources where possible.

### 6.1 Physical hardware

Physical GameCube + Game Boy Player behavior is the final authority for the target runtime.

However, physical tests should be requested only when necessary.

Evidence authority, in order: physical hardware is the final authority; the
official Nintendo Start-up Disc is the primary software reference; GBI is
an independent mature implementation, not official software; Dolphin is
auxiliary and never replaces physical observation. Divergences between
hardware, Start-up Disc, GBI and Dolphin are preserved and documented,
never resolved by silently picking one. Every claim is classified as
FACT, CORROBORATED, HYPOTHESIS or UNKNOWN (`docs/RESEARCH_METHOD.md`); an
inference is never promoted to FACT.

---

### 6.2 Official Game Boy Player Startup Disc

The user owns an original-disc dump.

Local path:

```text
input/gbp-disc.iso
```

This file is private and intentionally ignored by Git.

Known SHA-256 at project bootstrap:

```text
947a5523e7be9b93a986d1e4daca9e335713827df48adcb1dfe79c6a00ed177d
```

Never:

- commit it;
- redistribute it;
- modify it in place;
- embed its proprietary content into project outputs.

When it becomes useful, analyze it as a primary reference for software that actually controls the physical Game Boy Player.

Relevant research targets may include:

- GBS-DOL initialization;
- HSP transactions;
- register access;
- interrupts;
- video transfer;
- audio transfer;
- keypad/input;
- SIO/Link-related behavior;
- timing;
- startup/shutdown sequences.

Any extracted proprietary executable is also private and must remain outside Git.

Record SHA-256 hashes of extracted/analyzed binaries.

---

### 6.3 Game Boy Interface

A complete local GBI distribution is available under:

```text
input/gbi/
```

Primary binaries currently available:

```text
input/gbi/apps/gbi/gbi.dol
input/gbi/apps/gbisr/gbisr.dol
input/gbi/apps/gbihf/gbihf.dol
```

Treat them as:

```text
gbi.dol     -> Standard Edition; primary behavioral/reverse-engineering reference
gbisr.dol   -> Speedrunning Edition
gbihf.dol   -> High-Fidelity Edition
```

Do not delete the rest of the GBI package. It may later provide useful context or supporting assets.

GBI is a behavioral and reverse-engineering reference.

It is not the required runtime dependency of Open-GBP.

The long-term goal is a standalone open-source implementation.

GBI may be especially useful for:

- compatibility behavior;
- initialization;
- optimized hardware handling;
- video/audio behavior;
- Link Port handling;
- networking;
- configuration;
- timing;
- discovering undocumented hardware behavior.

Never redistribute or commit proprietary GBI input binaries.

Never overwrite the original binaries.

A GBI binary patch may be useful as a temporary experiment, but Open-GBP must not become dependent on proprietary GBI code.

---

### 6.4 Dolphin

Dolphin is a valuable open-source hardware model and execution/debugging environment.

Its Game Boy Player HSP implementation is an important reference.

Use Dolphin for:

- DOL smoke tests;
- PowerPC execution debugging;
- generic GameCube testing;
- HSP model comparison;
- detecting crashes;
- validating code that does not depend on missing hardware behavior.

Do not assume Dolphin perfectly reproduces all physical GBP behavior.

In particular, incomplete or stubbed functionality in Dolphin must not be treated as hardware truth.

When Dolphin and physical GBP behavior differ, document the difference.

#### Local Dolphin environment

Dolphin is installed on the host through Flatpak.

Current installation at project bootstrap:

```text
Application ID: org.DolphinEmu.dolphin-emu
Version: 2606a
Architecture: x86_64
```

Invoke it with:

```bash
flatpak run org.DolphinEmu.dolphin-emu
```

The Flatpak already has **read-only** access to the Open-GBP repository.

Useful CLI options confirmed on this host:

```text
--exec=<file>       Load the specified file
--batch             Run without the normal UI
--debugger          Enable debugger UI
--logger            Enable logger
--config=...        Override Dolphin configuration values
--user=<path>       Set the Dolphin user directory
```

To launch a generated DOL:

```bash
flatpak run org.DolphinEmu.dolphin-emu \
  --exec="/absolute/path/to/generated.dol"
```

For an automated smoke test:

```bash
timeout 10s \
  flatpak run org.DolphinEmu.dolphin-emu \
  --batch \
  --exec="/absolute/path/to/generated.dol"
```

A timeout exit by itself does **not** mean the DOL failed. A homebrew application may intentionally remain running indefinitely.

A successful smoke test should use stronger evidence where practical, for example:

- process starts without immediate crash;
- expected Dolphin log output;
- deterministic screen state;
- deterministic program exit where appropriate;
- expected file/log artifact;
- debugger/logger evidence;
- a POC-specific success condition.

Do not classify a test as PASS only because Dolphin remained open until `timeout`.

Claude may automate Dolphin invocation from the host after building in Docker.

Do not change Flatpak permissions unless there is a demonstrated need.

Dolphin is an intermediate validation layer:

```text
host tests
    ↓
PowerPC build
    ↓
Dolphin
    ↓
physical GameCube + Game Boy Player
```

Passing in Dolphin does not prove correct behavior on the physical Game Boy Player.

Every automated Dolphin run disables the on-screen display through the
per-run override `Dolphin.Interface.OnScreenDisplayMessages=False`, which
`tools/dolphin_smoke.py` applies automatically: screenshots must show only
the Open-GBP framebuffer, never Dolphin's yellow messages. Dolphin stays an
auxiliary tool for execution flow, logging, error paths, screenshots and
regressions; the behavior of its Game Boy Player model is never physical
truth.

---

### 6.5 Ghidra and GameCubeLoader

Ghidra is installed on the host for later reverse engineering work.

Current validated environment:

```text
Ghidra: 12.1.3 PUBLIC
Java/OpenJDK: 21
Ghidra path:
/home/rafael/Tools/Open-GBP/ghidra_12.1.3_PUBLIC
```

The GameCubeLoader extension is installed at:

```text
/home/rafael/Tools/Open-GBP/ghidra_12.1.3_PUBLIC/Ghidra/Extensions/GameCubeLoader
```

The installed extension identifies itself as:

```text
name=GameCubeLoader
version=12.1
```

This exact combination has been verified to successfully import a GameCube DOL in headless mode.

Confirmed loader/language:

```text
Loader:
Nintendo GameCube/Wii Binary (Executable)

Language:
PowerPC:BE:32:Gekko_Broadway:default
```

#### Headless DOL import

Use:

```bash
GHIDRA="$HOME/Tools/Open-GBP/ghidra_12.1.3_PUBLIC"

"$GHIDRA/support/analyzeHeadless" \
  <project-directory> \
  <project-name> \
  -import "<dol-path>" \
  -loader GameCubeLoader \
  -loader-autoloadMaps false
```

The `GameCubeLoader` enables automatic symbol-map loading by default.

In headless mode, if no corresponding map file is available, that default behavior can cause the extension to attempt to display a Swing dialog and fail with:

```text
java.awt.HeadlessException
```

Therefore, unless a map file is deliberately being supplied, headless DOL imports must use:

```text
-loader-autoloadMaps false
```

A disposable no-analysis import test may use:

```bash
rm -rf /tmp/open-gbp-ghidra-test

"$GHIDRA/support/analyzeHeadless" \
  /tmp/open-gbp-ghidra-test \
  LoaderTest \
  -import "<dol-path>" \
  -loader GameCubeLoader \
  -loader-autoloadMaps false \
  -noanalysis \
  -deleteProject
```

The following behavior was verified successfully against:

```text
input/gbi/apps/gbi/gbi.dol
```

and produced:

```text
Using Loader: Nintendo GameCube/Wii Binary (Executable)
Using Language/Compiler: PowerPC:BE:32:Gekko_Broadway:default
REPORT: Import succeeded
```

Do not interpret GameCubeLoader Sleigh warnings such as:

```text
NOP constructors found
Unreferenced table
unnecessary extensions/truncations
```

as import failure when the import itself succeeds.

Ghidra headless may later be used autonomously for static analysis of locally owned private reference binaries such as:

```text
input/gbi/apps/gbi/gbi.dol
input/gbi/apps/gbisr/gbisr.dol
input/gbi/apps/gbihf/gbihf.dol
```

and the executable extracted from:

```text
input/gbp-disc.iso
```

Do not begin reference-binary reverse engineering before the appropriate roadmap phase.

Prefer headless/scriptable workflows when practical so reverse-engineering results can be reproduced and do not depend on manual GUI actions.

---

### 6.6 Enhanced mGBA

Enhanced mGBA is an emulator-based GameCube/Wii application.

It does **not** use the physical Game Boy Player as its GBA execution path.

Do not treat it as an implementation of GBS-DOL/HSP hardware control.

It may still be useful as a reference for generic surrounding infrastructure such as:

- GameCube application structure;
- GX/video code;
- input;
- networking;
- configuration;
- libogc2 usage;
- code shared with or historically related to the GBI ecosystem.

Files whose names reference GBP do not automatically constitute a physical GBP driver.

Verify semantics before reusing conclusions.

---

### 6.7 Other reference projects

Other locally checked-out reference repositories belong under:

```text
external/
```

This directory is not vendored into Open-GBP.

Useful references may eventually include:

- Dolphin;
- libogc2;
- Game Boy Player Player research;
- gba-as-controller;
- Enhanced mGBA;
- later Mobile Adapter implementations.

Prefer recording repository URL and exact commit hash in research notes when conclusions depend on external source.

---

## 7. Private inputs and proprietary material

`input/` is reserved for locally owned analysis inputs.

Current examples:

```text
input/gbp-disc.iso
input/gbi/
```

Rules:

- never commit proprietary binaries;
- never redistribute them;
- never overwrite originals;
- hash inputs before analysis;
- store extracted private artifacts only in ignored/local analysis locations;
- independently implement behavior rather than copying proprietary source representation;
- documentation should describe hardware behavior, not reproduce proprietary implementation text.

---

## 8. Development environment

GameCube software is built through Docker.

Current base image:

```text
ghcr.io/extremscorner/libogc2:20260805
```

Expected environment:

```text
DEVKITPRO=/opt/devkitpro
DEVKITPPC=/opt/devkitpro/devkitPPC
```

`PATH` must contain:

```text
/opt/devkitpro/devkitPPC/bin
/opt/devkitpro/tools/bin
```

The container should expose:

```text
powerpc-eabi-gcc
powerpc-eabi-g++
powerpc-eabi-objdump
elf2dol
make
```

GameCube Makefiles using libogc2 should use the current libogc2 rules where appropriate:

```make
include $(DEVKITPRO)/libogc2/gamecube_rules
```

Do not install devkitPPC directly on the host unless explicitly requested.

Do not run `sudo` to modify the host development environment.

The repository resides on a filesystem mounted through `fuseblk` and does not preserve normal POSIX executable permission semantics. Do not treat file-mode differences as meaningful project changes.

Git is configured locally with:

```text
core.fileMode=false
```

---

## 9. Autonomous testing policy

The user wants minimal manual hardware intervention.

Before requesting a physical GameCube test, determine whether the question can be answered through:

1. static analysis;
2. host-native unit tests;
3. synthetic test vectors;
4. mock hardware transports;
5. trace replay;
6. PowerPC compilation/link validation;
7. binary inspection;
8. Dolphin;
9. later, Ghidra/static analysis when appropriate to the roadmap phase.

Only request physical hardware testing when the real Game Boy Player behavior is material to the answer.

Do not ask the user to manually debug something Claude can test autonomously.

---

## 10. Testable architecture

Hardware-specific code should be isolated behind testable boundaries whenever practical.

Prefer a design conceptually similar to:

```text
higher-level GBP logic
        │
        ▼
GBP transport/API
        │
        ├── real HSP backend
        ├── mock backend
        └── trace/replay backend
```

Avoid spreading direct MMIO or HSP transaction code throughout unrelated runtime modules.

The purpose is not abstraction for its own sake.

The purpose is to allow:

- deterministic host tests;
- hardware simulation;
- failure injection;
- trace replay;
- regression testing;
- less frequent physical hardware access.

Timing-sensitive code may require lower-level specialization. Preserve testability where it does not compromise correctness.

---

## 11. Synthetic tests

Every protocol transformation that can be tested without hardware should have automated tests.

Examples include:

- register encoding/decoding;
- interrupt bit handling;
- keypad encoding;
- video packet parsing;
- frame/buffer boundary handling;
- ring-buffer wraparound;
- log encoding;
- trace parser behavior;
- timeouts/state machines;
- malformed data;
- queue overflow behavior;
- networking state machines.

Do not wait until the project is large to add tests.

When implementing new behavior, consider the host-side test before the hardware test.

---

## 12. Trace/replay infrastructure

Physical hardware experiments should generate reusable evidence when practical.

The ideal cycle is:

```text
one physical test
      ↓
hardware trace
      ↓
sanitized fixture
      ↓
repeatable host regression tests
```

Public reusable fixtures may be stored under:

```text
captures/fixtures/
```

Private/local captures belong under:

```text
captures/local/
captures/private/
```

Never commit private information or proprietary binary data unintentionally.

Trace formats should be documented and machine-readable where practical.

Physical logs follow one permanent workflow:

- `logs/` (repository root): the raw input handed over by the user — never
  edited, never normalized, never versioned; hashes are computed directly
  from the original;
- `captures/local/`: the preserved local copy (ignored by Git);
- `captures/fixtures/`: derived replay fixtures, versioned when appropriate,
  identified by the hash and size of the raw log they come from.

Raw bytes are the primary evidence; semantic values are derived and stay
separate from them.

---

## 13. SD2SP2 logging

The user has SD2SP2 available.

Use it as the preferred persistent hardware logging destination when useful.

Do not perform SD writes directly in timing-critical HSP/SIO paths.

Preferred design:

```text
hardware event
      ↓
preallocated RAM ring buffer
      ↓
safe/noncritical flush
      ↓
SD2SP2
```

Do not:

- allocate memory on every event;
- write a filesystem record per serial byte;
- block a serial IRQ on FAT/SD I/O.

If the event buffer fills, increment an overflow/lost-event counter rather than blocking the critical path.

A useful log header should contain:

- build ID;
- Git commit if available;
- test ID;
- execution mode;
- cartridge/test software;
- physical Link Port state;
- BBA state;
- buffer capacity;
- overflow count;
- relevant runtime options.

Also provide an on-screen summary so SD logging failure does not make a test unusable.

---

## 14. No USB Gecko or logic analyzer dependency

Assume the user does not have:

- USB Gecko;
- logic analyzer.

Do not design required workflows around them.

Diagnostics should therefore prefer:

- on-screen status;
- counters;
- error/status codes;
- RAM ring-buffer event histories;
- SD2SP2 logs;
- later, BBA telemetry when it does not interfere with the behavior under test.

Optional support for other debug hardware may be added in the future, but it must not be necessary for normal project development.

---

## 15. Hardware test requests

When a real hardware test is required, minimize user effort.

Provide:

```text
Test ID:
Build ID:
DOL:
Required cartridge/test ROM:
Physical Link Port state:
BBA state:
Steps:
Expected result/log:
Question answered:
```

Prefer procedures such as:

```text
1. Copy DOL to SD.
2. Launch through Swiss.
3. Wait for READY.
4. Perform one action.
5. Press X to save report.
6. Return the generated log.
```

Avoid broad requests such as:

> Try this and tell me what happens.

A physical test should answer a specific research question.

After the user reports a result, record it in `docs/research/HARDWARE_TESTS.md`.

Important hardware findings should also be reflected in:

- `EVIDENCE.md`;
- `UNKNOWNS.md`;
- `DEVLOG.md`;
- automated fixtures/tests when practical.

Do not leave important hardware knowledge only in chat history.

---

## 16. Build identification

Every hardware-testable DOL should be identifiable.

Prefer embedding or displaying:

- semantic POC/application name;
- build ID;
- short Git commit hash when available.

Example:

```text
Open-GBP HSP Probe
Build: hsp-0007
Commit: a83f2cd
```

Generated logs must include the same identity.

This is required so hardware results can be tied to exact source.

---

## 17. First GameCube code

The development agent should create the first GameCube POC itself.

Do not assume an externally prepared hello-world project.

The first program should be deliberately small and prove:

- Docker compilation;
- Makefile correctness;
- libogc2 linkage;
- ELF → DOL generation;
- predictable build output;
- basic program execution;
- simple display/input if appropriate;
- Dolphin launch/smoke-test workflow.

Do not touch undocumented GBP hardware registers merely to make the first DOL more interesting.

---

## 18. Hardware research safety

When interacting with undocumented hardware:

1. prefer read-only observation first;
2. reproduce known official initialization before experimenting;
3. change one variable at a time;
4. record original state where possible;
5. avoid speculative writes to unknown control bits;
6. document uncertainty;
7. make experimental writes opt-in;
8. provide a clear reset/recovery procedure where relevant.

Do not chain multiple unverified assumptions into one hardware test.

Permanent rules for physical experiments:

- a new physical write needs a justification in a known reference or an
  explicit experimental authorization;
- prefer one new variable per experiment;
- preserve and restore state whenever possible;
- no unbounded wait: every wait has an operational bound, never presented
  as a hardware property;
- hardware is never tested with a `-dirty` build; a physical candidate
  requires a clean commit, a rebuild, passing tests and a recorded hash;
- after an experiment that may leave device state not fully acknowledged,
  the console is power-cycled when the procedure specifies it.

---

## 19. Internal SIO research

Do not assume the following are already solved:

- meaning of all `SIOControl` bits;
- meaning/width/timing of `SIOData`;
- Serial IRQ semantics;
- GBA-mode internal serial behavior;
- GB/GBC-mode internal serial behavior;
- external Link Port routing;
- whether internal handling mirrors, redirects, disables, or competes with the external connector.

The existence of normal external Link communication does not prove GameCube-side internal SIO control.

Internal SIO research should begin read-only whenever possible.

An important eventual experiment is:

```text
known serial activity generated by physical cartridge/AGB
          ↓
observe through GameCube/HSP
```

before attempting:

```text
GameCube/HSP response
          ↓
physical cartridge/AGB observes response
```

---

## 20. Network/BBA development

Network support is developed independently of Mobile Adapter logic.

Before any Mobile Adapter integration, build a standalone BBA/network test with an automated host-side peer.

Test independently:

- BBA detection/init;
- IP configuration;
- UDP;
- TCP;
- DNS if required;
- reconnect behavior;
- timeout behavior;
- nonblocking behavior;
- queues/buffering.

Do not perform blocking DNS/TCP/UDP operations from timing-critical serial handling.

A likely later architecture is:

```text
timing-critical SIO
       ↓
queue/ring buffer
       ↓
protocol worker
       ↓
network queue
       ↓
BBA worker
```

Do not introduce concurrency unnecessarily, but never allow slow network operations to violate serial timing requirements.

---

## 21. GBI-class functionality

GBI is a compatibility/functionality reference, not a mandatory dependency.

Once the basic GBP runtime works, Open-GBP should progressively aim for practical normal-use functionality comparable to mature GBP software.

Possible areas include:

- presentation modes;
- scaling;
- filtering;
- latency/timing improvements;
- configuration;
- compatibility fixes;
- robust startup/shutdown;
- runtime usability.

Do not implement cosmetic parity before the underlying hardware runtime is stable.

---

## 22. Code quality

Prefer:

- small modules;
- explicit fixed-width integer types;
- explicit endianness handling;
- documented MMIO/HSP constants;
- symbolic names only when evidence supports them;
- no hidden blocking operations in timing-sensitive paths;
- preallocated buffers where timing matters;
- warnings enabled;
- deterministic builds where practical.

Do not silence compiler warnings merely to make builds pass.

Do not perform unrelated large refactors while investigating one hardware behavior.

---

## 23. Source organization

Allow the architecture to evolve, but prefer separation roughly along:

```text
src/
    platform/
    gbp/
    hsp/
    video/
    audio/
    input/
    sio/
    network/

tests/
    unit/
    mocks/
    replay/
    fixtures/

poc/
    smoke-test/
    hsp-probe/
    ...
```

Do not create all directories prematurely if there is no code for them yet.

---

## 24. Commit discipline

Prefer small commits with one technical purpose.

Examples:

```text
build: add GameCube smoke test
test: add mock HSP transport
docs: document observed GBP control register
poc: add read-only GBP IRQ probe
trace: add parser for HSP event logs
video: decode GBP frame metadata
net: add BBA UDP test
```

Do not mix:

- documentation discoveries;
- unrelated refactors;
- experimental register writes;
- formatting-only changes;

into one large commit.

Do not automatically commit/push unless the user has explicitly delegated that action.

---

## 25. Development log discipline

At meaningful checkpoints update:

```text
docs/research/DEVLOG.md
```

Record:

- date;
- goal;
- changes;
- tests executed;
- result;
- newly confirmed behavior;
- rejected hypotheses;
- new unknowns;
- next highest-value experiment.

Avoid turning the devlog into a transcript of every command.

---

## 26. Phase gates

Follow `docs/ROADMAP.md`.

Do not skip forward merely because a later feature is more interesting.

A later phase may be investigated early only when it directly answers a blocking feasibility question.

If this happens:

- keep the experiment narrow;
- document why the roadmap was temporarily crossed;
- do not allow the experiment to become an architectural dependency prematurely.

`libmobile` remains specifically gated until the relevant GBP/SIO/network foundations are validated.

Ghidra being installed and operational does not authorize early reverse engineering outside the roadmap phase.

---

## 27. First-session behavior

On the first development session:

1. Read the required project documents.
2. Inspect the repository.
3. Verify the Docker build environment.
4. Verify the known Dolphin Flatpak installation and CLI.
5. Note that Ghidra headless is installed and validated, but do not begin reference-binary reverse engineering.
6. Do not modify private inputs.
7. Do not require `gbp-disc.iso` or GBI binaries for the first build.
8. Create a minimal host-test structure.
9. Create the first GameCube smoke-test application.
10. Compile it entirely through the project Docker environment.
11. Inspect the generated ELF/DOL.
12. Run all host-side/autonomous tests.
13. Launch the DOL through Dolphin using the confirmed Flatpak CLI.
14. Use a bounded `timeout` for unattended runs when appropriate.
15. Do not call a Dolphin test PASS solely because it survived until timeout.
16. Record the work in `docs/research/DEVLOG.md`.
17. Report the generated DOL path and exact hardware test procedure only if real hardware validation is now the highest-value unresolved step.

Do not begin Game Boy Player register experimentation during the first smoke-test milestone.

The first milestone is to establish a trustworthy autonomous development loop.

---

## 28. Core decision rule

When choosing what to do next, prefer the task that:

1. answers the most important unresolved technical question;
2. requires the fewest unsupported assumptions;
3. can be tested most autonomously;
4. produces reusable evidence;
5. advances the current roadmap phase;
6. minimizes unnecessary physical user intervention.

When uncertain, document the uncertainty rather than hiding it.

---

## 29. Where the current state lives

`CLAUDE.md` holds permanent policies only. Detailed experimental results,
open questions and the next planned step are recovered from:

- `docs/research/DEVLOG.md` — chronological decisions and the latest status;
- `docs/research/EVIDENCE.md` — classified claims;
- `docs/research/HARDWARE_TESTS.md` — executed and planned physical tests;
- `docs/research/UNKNOWNS.md` — open questions;
- `docs/protocol/INITIALIZATION.md` and `docs/protocol/REGISTERS.md` — the
  consolidated protocol reference;
- GitHub Issues (§30) — the operational trail: who did what, in which
  checkpoint; never the scientific state.

Read them before proposing the next experiment.

---

## 30. Operational coordination — GitHub

Since 2026-09-20 the canonical repository is:

```text
https://github.com/zenaror/Open-GBP
```

Local remotes: `origin` = GitHub (fetch and push); `gitea-archive` =
`https://git.home.zsrv.com.br/zenaror/Open-GBP`, retained as an archive,
non-canonical, push disabled locally (`no_push`). Normal fetch, pull and push
go to `origin`. Never force-push; never rewrite history.

GitHub Issues are the operational unit of work (`AGENTS.md`, "Operational
coordination — GitHub"): an executor round starts from a bounded Issue and ends
with the executor report posted on it. Milestones mirror `docs/ROADMAP.md`
phases; `stage:*` labels carry the fine workflow state and the Orchestrator
moves them; the Project "Open-GBP Development" is views only. Templates:
`.github/ISSUE_TEMPLATE/checkpoint.md`, `.github/ISSUE_TEMPLATE/hardware-run.md`,
`.github/PULL_REQUEST_TEMPLATE.md`.

None of this changes §24: commits and pushes still need explicit delegation,
which an Issue may give in its own text. None of it changes §5, §6 or
`docs/RESEARCH_METHOD.md`: no Issue, label, milestone or Project field promotes
evidence status, and operator declarations quoted in an Issue remain
OPERATOR OBSERVATION.
