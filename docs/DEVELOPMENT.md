# Development environment and optional analysis tools

The build is containerized. The reference inputs described here are optional,
legally supplied inputs for specific analysis workflows; they are not distributed
and are not needed to understand the public API or run synthetic regressions.
Paths are relative to the checkout or configurable installation directories.
See [VALIDATION.md](VALIDATION.md) for the reproducible test workflow.

## Development environment

GameCube software is built in a container under rootless Podman (the Docker
engine is no longer installed on the development host; Issue #159). `make`
drives it through `$(COMPOSE)`, default `podman compose` (a shim over the
external `docker-compose` provider, which it points at Podman's own user
socket); the user socket must be active:
`systemctl --user start podman.socket`. The `Dockerfile` and `compose.yaml`
keep their Docker-compatible format.

Current base image:

```text
ghcr.io/extremscorner/libogc2:20260805
```

Verified on 2026-10-05 with Podman 4.9.3: image ID
`ba9cd72a4bd027736197633b7510d269e07a2bf2894ef95018a2f2606d32b859`, manifest
digest
`sha256:13bb658d3f18903816617223f5d7c6f776d3db3ea806aae67f8d35a7a69d4c85`.
A Podman build is "the project's build" because it reproduced
`vehicle-0001` (`a02bcfa3…5d2`, built at `6396851`) and `27-gbmode`
(`e33115e3…a497`, built at `4d6fe06`) byte for byte (`docs/VALIDATION.md`,
Issue #159); a divergence from a pinned image means the environment is not
equivalent, never that the pin is wrong.

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

Expected tools include:

```text
powerpc-eabi-gcc
powerpc-eabi-g++
powerpc-eabi-objdump
elf2dol
make
```

Do not install devkitPPC directly on the host unless explicitly requested.

Do not use `sudo` to modify the host development environment. Container
commands are `podman compose run --rm -T dev ...` (what `make` runs); do not
reinstall Docker.

The repository resides on a filesystem mounted through `fuseblk` and does not
preserve normal POSIX executable permission semantics.

Do not treat file-mode differences as meaningful project changes.

Git is configured locally with:

```text
core.fileMode=false
```

GameCube Makefiles using libogc2 should use:

```make
include $(DEVKITPRO)/libogc2/gamecube_rules
```

where appropriate.

## First GameCube smoke-test milestone

The first GameCube POC must be created by the development agent itself.

Do not assume an externally prepared hello-world project.

The first program must prove:

* container compilation (rootless Podman, §16);
* Makefile correctness;
* libogc2 linkage;
* ELF → DOL generation;
* predictable build output;
* basic execution;
* simple display/input where appropriate;
* Dolphin launch/smoke-test workflow.

Do not touch undocumented GBP hardware registers merely to make the first DOL
more interesting.

The first milestone establishes a trustworthy autonomous development loop.

## Dolphin

Dolphin is a valuable open-source GameCube execution and hardware-model
reference.

Use it for:

* DOL smoke tests;
* PowerPC execution debugging;
* generic GameCube testing;
* HSP model comparison;
* crash detection;
* code paths independent of missing physical hardware behavior.

Do not assume Dolphin perfectly reproduces the physical Game Boy Player.

Incomplete or stubbed Dolphin functionality is not hardware truth.

When Dolphin and physical hardware differ, document the difference.

## Local environment

Dolphin is installed through Flatpak.

Current validated installation:

```text
Application ID: org.DolphinEmu.dolphin-emu
Version: 2606a
Architecture: x86_64
```

Invoke it with:

```bash
flatpak run org.DolphinEmu.dolphin-emu
```

Useful confirmed CLI options:

```text
--exec=<file>
--batch
--debugger
--logger
--config=...
--user=<path>
```

Launch a generated DOL:

```bash
flatpak run org.DolphinEmu.dolphin-emu \
  --exec="/absolute/path/to/generated.dol"
```

Automated smoke test:

```bash
timeout 10s \
  flatpak run org.DolphinEmu.dolphin-emu \
  --batch \
  --exec="/absolute/path/to/generated.dol"
```

A timeout alone does **not** indicate failure.

A successful smoke test should use stronger evidence where practical:

* process starts without immediate crash;
* expected Dolphin log output;
* deterministic screen state;
* deterministic exit where appropriate;
* expected file/log artifact;
* debugger/logger evidence;
* a POC-specific success condition.

Never classify a test as PASS merely because Dolphin remained alive until
`timeout`.

Every automated Dolphin run must disable the on-screen display using the
per-run override:

```text
Dolphin.Interface.OnScreenDisplayMessages=False
```

`tools/dolphin_smoke.py` applies this automatically.

Screenshots must show only the Open-GBP framebuffer, not Dolphin's yellow
messages.

Dolphin remains an auxiliary validation layer:

```text
host tests
    ↓
PowerPC build
    ↓
Dolphin
    ↓
physical GameCube + Game Boy Player
```

Passing in Dolphin never proves correct physical Game Boy Player behavior.

Do not change Flatpak permissions unless there is a demonstrated need.

## Ghidra and GameCubeLoader

Ghidra is installed for reverse engineering when authorised by the roadmap.

Current validated environment:

```text
Ghidra: 12.1.3 PUBLIC
Java/OpenJDK: 21
```

Set `GHIDRA` to the absolute path of your local Ghidra installation. The
GameCubeLoader source directory may live separately; the extension used by
the validated setup is installed inside Ghidra at:

```text
$GHIDRA/Ghidra/Extensions/GameCubeLoader
```

Installation paths are local configuration. Check that
`$GHIDRA/support/analyzeHeadless` and the installed extension exist before use.
The successful import below is historical; relocating an installation does not
constitute a new validation.

Installed extension:

```text
name=GameCubeLoader
version=12.1
```

Validated loader/language:

```text
Loader:
Nintendo GameCube/Wii Binary (Executable)

Language:
PowerPC:BE:32:Gekko_Broadway:default
```

Headless import:

```bash
GHIDRA="/path/to/ghidra_12.1.3_PUBLIC"

"$GHIDRA/support/analyzeHeadless" \
  <project-directory> \
  <project-name> \
  -import "<dol-path>" \
  -loader GameCubeLoader \
  -loader-autoloadMaps false
```

Unless a map file is intentionally supplied, use:

```text
-loader-autoloadMaps false
```

Without it, GameCubeLoader may attempt to open a Swing dialog in headless mode
and fail with:

```text
java.awt.HeadlessException
```

Disposable import test:

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

This was successfully verified against:

```text
input/gbi/apps/gbi/gbi.dol
```

Successful import reports:

```text
Using Loader: Nintendo GameCube/Wii Binary (Executable)
Using Language/Compiler: PowerPC:BE:32:Gekko_Broadway:default
REPORT: Import succeeded
```

Do not interpret Sleigh warnings such as:

```text
NOP constructors found
Unreferenced table
unnecessary extensions/truncations
```

as import failure when the import itself succeeds.

Ghidra may be used autonomously for static analysis of locally owned private
reference binaries when the roadmap permits it.

Prefer headless/scriptable workflows when practical.

The presence of Ghidra does **not** authorize early reverse engineering outside
the roadmap phase.

## Official Start-up Disc

A contributor may supply an original-disc dump.

Local path:

```text
input/gbp-disc.iso
```

Known SHA-256 at project bootstrap:

```text
947a5523e7be9b93a986d1e4daca9e335713827df48adcb1dfe79c6a00ed177d
```

The file is private and intentionally ignored by Git.

Never:

* commit it;
* redistribute it;
* modify it in place;
* embed proprietary content into project outputs.

Extracted proprietary executables are also private.

When useful, analyze the disc as a primary reference for software controlling
the physical Game Boy Player.

Relevant research targets include:

* GBS-DOL initialization;
* HSP transactions;
* register access;
* interrupts;
* video transfer;
* audio transfer;
* keypad/input;
* SIO/Link behavior;
* timing;
* startup/shutdown sequences.

Record SHA-256 hashes of extracted/analyzed binaries.

## Game Boy Interface

A complete local GBI distribution is available under:

```text
input/gbi/
```

Primary binaries:

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

Do not delete the rest of the GBI package.

GBI is a behavioral and reverse-engineering reference.

It is not an Open-GBP runtime dependency.

Never redistribute or commit proprietary GBI binaries.

Never overwrite originals.

A GBI binary patch may be used for temporary experiments, but Open-GBP must
not become dependent on proprietary GBI code.

## Enhanced mGBA

Enhanced mGBA is an emulator-based GameCube/Wii application.

It does not use the physical Game Boy Player as its GBA execution path.

Do not treat it as an implementation of GBS-DOL/HSP physical hardware control.

It may still provide useful reference material for:

* GameCube application structure;
* GX/video code;
* input;
* networking;
* configuration;
* libogc2 usage;
* code historically related to the GBI ecosystem.

A filename containing `GBP` does not automatically constitute a physical GBP
driver.

Verify semantics before reusing conclusions.

## Other reference projects

Other locally checked-out reference repositories belong under:

```text
external/
```

This directory is not vendored into Open-GBP.

Potential references include:

* Dolphin;
* libogc2;
* Game Boy Player research;
* gba-as-controller;
* Enhanced mGBA;
* later Mobile Adapter implementations.

When conclusions depend on external source, record the repository URL and exact
commit hash where practical.

## Private inputs and proprietary material

`input/` is reserved for locally owned analysis inputs.

Examples:

```text
input/gbp-disc.iso
input/gbi/
```

Rules:

* never commit proprietary binaries;
* never redistribute them;
* never overwrite originals;
* hash inputs before analysis;
* store extracted private artifacts only in ignored/local analysis locations;
* independently implement behavior rather than copying proprietary source
  representation;
* documentation describes hardware behavior, not proprietary implementation
  text.

The following must not be published or embedded in derived artifacts:

* `input/`;
* raw proprietary material;
* proprietary binaries;
* private captures;
* raw logs where their inclusion would violate project policy.

## Source organization

Allow architecture to evolve, but prefer separation roughly along:

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

Do not create directories prematurely when no code requires them.

Prefer:

* small modules;
* explicit fixed-width integer types;
* explicit endianness;
* documented MMIO/HSP constants;
* symbolic names only when supported by evidence;
* no hidden blocking operations in timing-sensitive paths;
* preallocated buffers where timing matters;
* compiler warnings enabled;
* deterministic builds where practical.

Do not silence warnings merely to make builds pass.

Do not perform unrelated large refactors while investigating one hardware
behavior.
