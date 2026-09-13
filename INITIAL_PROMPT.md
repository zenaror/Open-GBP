# Open-GBP — Initial Claude Code Prompt

Read `CLAUDE.md` completely first.

Then read the project documents it references, especially:

* `README.md`
* `docs/ROADMAP.md`
* `docs/RESEARCH_METHOD.md`
* everything currently present under `docs/research/`

Treat those files as the authoritative project specification.

We are beginning **Phase 1 — Project and test infrastructure**.

Do not begin reverse engineering the Game Boy Player yet.

Do not use `libmobile`.

Do not implement Mobile Adapter functionality.

Do not access undocumented GBP registers during this first milestone.

Your goal for this session is to establish the first autonomous Open-GBP development loop.

## Tasks

1. Inspect the repository and existing Docker configuration.

2. Verify the development environment from inside the project container, including at least:

```text
DEVKITPRO
DEVKITPPC
powerpc-eabi-gcc
powerpc-eabi-g++
powerpc-eabi-objdump
elf2dol
make
$(DEVKITPRO)/libogc2/gamecube_rules
```

3. Preserve the existing pinned Docker/libogc2 environment unless there is a concrete technical reason to change it.

4. Create the minimum useful host-side testing structure.

5. Create the project's first GameCube proof of concept under something similar to:

```text
poc/smoke-test/
```

Choose the exact naming/layout if a better structure is justified.

6. The first POC should remain intentionally simple. Its purpose is to prove:

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
```

It should not manipulate undocumented Game Boy Player hardware.

7. Make the build reproducible with a simple documented command.

Prefer a workflow such as:

```text
docker compose run --rm dev make ...
```

or an equally simple project-level command.

8. Add automated checks that can run without physical hardware.

At minimum, validate that:

* host-side tests execute successfully;
* GameCube source compiles;
* linking succeeds;
* the expected ELF exists;
* the expected DOL exists;
* obvious binary metadata can be inspected automatically.

9. Give the generated DOL a visible build identity where practical.

10. If Dolphin is already available in a way that can be invoked without substantial manual configuration, perform an appropriate smoke test.

Do not spend this first session extensively configuring Dolphin if it is not immediately usable.

11. Update:

```text
docs/research/DEVLOG.md
```

with:

* what was created;
* exact build/test commands;
* test results;
* relevant environment/tool versions;
* unresolved issues;
* recommended next step.

Update other research documentation only if the session produces information that belongs there.

12. Do not request a physical hardware test until all autonomous checks for this milestone have passed.

If hardware validation becomes the next required step, provide a concise deterministic procedure containing:

```text
Test ID
Build ID
DOL path
Swiss launch instructions
Expected screen/result
What the test proves
```

## Important constraints

The final Open-GBP project targets the **physical Game Boy Player**, but this first milestone is only the development infrastructure.

The user wants minimal manual hardware involvement. Test everything you reasonably can yourself before requesting GameCube validation.

Do not install system packages with `sudo`.

Do not commit or push automatically.

Do not modify or add proprietary binary inputs.

Do not start future roadmap phases merely because their code looks interesting.

At the end of the session, summarize:

1. files created/modified;
2. commands used to build;
3. tests run;
4. generated artifacts;
5. anything that failed;
6. whether physical hardware validation is now justified;
7. the single highest-value next step.
