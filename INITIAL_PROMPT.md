# INITIAL_PROMPT.md — Open-GBP First Claude Code Session

Read `CLAUDE.md` completely before doing anything else.

Then read the authoritative project documents referenced by it, especially:

- `README.md`
- `docs/ROADMAP.md`
- `docs/RESEARCH_METHOD.md`
- everything currently present under `docs/research/`

Treat those files as the project specification.

We are beginning **Phase 1 — Project and test infrastructure**.

Do not begin reverse engineering the Game Boy Player yet.

Do not use `libmobile`.

Do not implement Mobile Adapter functionality.

Do not access undocumented GBP registers during this first milestone.

Your goal for this session is to establish the first autonomous Open-GBP development loop.

## Confirmed local environment

The project already has a working Docker-based GameCube toolchain.

Expected container environment includes:

```text
DEVKITPRO=/opt/devkitpro
DEVKITPPC=/opt/devkitpro/devkitPPC
powerpc-eabi-gcc
powerpc-eabi-g++
powerpc-eabi-objdump
elf2dol
make
$(DEVKITPRO)/libogc2/gamecube_rules
```

The pinned libogc2 image is:

```text
ghcr.io/extremscorner/libogc2:20260805
```

Dolphin is already installed on the host via Flatpak:

```text
Application ID: org.DolphinEmu.dolphin-emu
Version: 2606a
```

Invoke it with:

```bash
flatpak run org.DolphinEmu.dolphin-emu
```

The Flatpak already has read-only access to the Open-GBP repository.

Confirmed useful options include:

```text
--exec=<file>
--batch
--debugger
--logger
--config=...
```

For an automated smoke test, a command similar to this is acceptable:

```bash
timeout 10s \
  flatpak run org.DolphinEmu.dolphin-emu \
  --batch \
  --exec="/absolute/path/to/generated.dol"
```

A timeout does not itself indicate success or failure. Establish a stronger POC-specific success criterion where practical.

Ghidra is also installed and validated on the host:

```text
Ghidra 12.1.3 PUBLIC
Java/OpenJDK 21
GameCubeLoader version 12.1
```

Path:

```text
/home/rafael/Tools/Open-GBP/ghidra_12.1.3_PUBLIC
```

Headless GameCube DOL imports have been verified with:

```text
-loader GameCubeLoader
-loader-autoloadMaps false
```

However, **Ghidra is not required for this first smoke-test milestone**.

Do not begin analysis of:

```text
input/gbp-disc.iso
input/gbi/apps/gbi/gbi.dol
input/gbi/apps/gbisr/gbisr.dol
input/gbi/apps/gbihf/gbihf.dol
```

during Phase 1.

## Tasks

1. Inspect the repository and existing Docker configuration.

2. Verify the development environment from inside the project container.

3. Verify that the known Dolphin Flatpak installation can still be invoked from the host.

4. Preserve the existing pinned Docker/libogc2 environment unless there is a concrete technical reason to change it.

5. Create the minimum useful host-side testing structure.

6. Create the project's first GameCube proof of concept under something similar to:

```text
poc/smoke-test/
```

Choose a better naming/layout only if justified.

7. The first POC must remain intentionally simple. Its purpose is to prove:

```text
source
  ↓
Docker
  ↓
devkitPPC + libogc2
  ↓
ELF
  ↓
DOL
  ↓
Dolphin smoke test
```

It must not manipulate undocumented Game Boy Player hardware.

8. Give the smoke-test DOL a visible build identity where practical, for example:

```text
Open-GBP Smoke Test
Build: smoke-0001
Commit: <short hash>
```

9. Make the build reproducible with a simple documented command.

Prefer a project-level command or a simple Docker Compose invocation.

10. Add automated checks that run without physical hardware.

At minimum validate that:

- host-side tests execute successfully;
- GameCube source compiles;
- linking succeeds;
- the expected ELF exists;
- the expected DOL exists;
- useful binary metadata can be inspected automatically.

11. Run the generated DOL in Dolphin using the confirmed Flatpak CLI.

Do not classify the test as PASS only because Dolphin stayed open until a timeout.

Use whatever autonomous evidence is practical for this minimal POC, such as:

- clean startup without immediate fatal error;
- deterministic screen output;
- Dolphin logger output;
- deterministic application state;
- generated test artifact;
- or another clearly documented success condition.

12. If Dolphin testing exposes an issue, debug it autonomously before asking for physical hardware validation.

13. Update:

```text
docs/research/DEVLOG.md
```

with:

- files created/changed;
- exact build command;
- exact test commands;
- tool versions observed;
- host-test results;
- PowerPC build result;
- ELF/DOL paths;
- Dolphin test method and result;
- failures or warnings;
- unresolved issues;
- recommended next step.

14. Update other research documentation only if the session produces information that belongs there.

15. Do not request a physical hardware test until all reasonable autonomous checks for this milestone have passed.

If physical validation becomes the next necessary step, provide a concise deterministic request containing:

```text
Test ID:
Build ID:
DOL path:
Swiss launch steps:
Expected screen/result:
What this test proves:
```

## Important constraints

The final project targets the **physical Game Boy Player**, but this first milestone is only the autonomous development infrastructure.

The user wants minimal manual hardware involvement.

Test everything you reasonably can yourself before requesting GameCube validation.

Do not install system packages with `sudo`.

Do not change Dolphin Flatpak permissions unless there is a demonstrated need.

Do not modify the installed Ghidra/GameCubeLoader environment during Phase 1 unless required to resolve a directly blocking infrastructure issue.

Do not commit or push automatically.

Do not modify or add proprietary binary inputs.

Do not start future roadmap phases merely because their code looks interesting.

At the end of the session, summarize:

1. files created/modified;
2. commands used to build;
3. tests run;
4. generated artifacts;
5. Dolphin result;
6. anything that failed;
7. whether physical hardware validation is now justified;
8. the single highest-value next step.
