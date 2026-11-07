# Open-GBP contributor instructions

Open-GBP implements an independent runtime and tooling for the **physical
Nintendo Game Boy Player**. Real GB/GBC/GBA software runs on the real AGB CPU;
software emulation is not the final execution path.

## Public entry points

- [README.md](README.md): scope, limitations, build and first use.
- [docs/RESEARCH_METHOD.md](docs/RESEARCH_METHOD.md): evidence vocabulary,
  compatibility requirements and mandatory hardware safety contracts.
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): container/toolchain and optional
  reference-analysis workflows.
- [docs/VALIDATION.md](docs/VALIDATION.md): tests, immutable historical oracles,
  artifact identity and reproducibility requirements.
- [docs/ROADMAP.md](docs/ROADMAP.md): public product goals and acceptance criteria.
- `src/`, `poc/`, `stimulus/`: runtime modules and diagnostic programs.
- `tests/`, `tools/`, `Makefile`: host regressions and deterministic tooling.

Read the relevant public contracts before changing a subsystem. Keep changes
bounded and reviewable, preserve unrelated local work, and stage paths explicitly.
Do not change a frozen gate, binary format or evidence interpretation silently.

## Essential commands

```sh
python3 tools/history_recover.py
make test
```

A full Git clone is needed for historical regressions. `make test-unit` can run
independently; the complete Python suite also requires the PowerPC artifacts from
`make build`. `make build` uses rootless
Podman and the pinned image; `make test` also builds and inspects GameCube POCs.
See the development and validation guides before invoking hardware-specific steps.

## Local technical constraints

- Physical hardware is final authority; the official disc and GBI are references.
  Emulators and synthetic fixtures never establish a physical hardware fact.
- Keep FACT, CORROBORATED, HYPOTHESIS, UNKNOWN and OPERATOR OBSERVATION distinct.
- Tie hardware observations to exact build/commit identity and SHA-256. A rebuild
  does not inherit physical validation. Never run a dirty build on hardware.
- Preserve ordinary physical Link Port peripherals, rumble, GBP-aware behavior
  and GB/GBC/GBA compatibility. Virtual Mobile Adapter support is additive and
  remains gated by the product roadmap.
- Prefer read-only hardware observation; justify writes, change one variable,
  use bounded waits, and specify reset/recovery. No USB Gecko or logic analyzer
  is required. Buffer timing-critical logs in RAM and flush outside the hot path.
- Preserve raw bytes, saves, original/reference inputs, accepted binaries,
  annotations and fixtures. Ignored/untracked does not mean disposable.
- Clean only enumerated task-owned temporary outputs after durable preservation
  and checking active users. `make clean` removes all `build/poc` and `build/tests`;
  it is not automatic cleanup in a shared checkout.
- Never redistribute proprietary binaries or decompiled output. Publish behavior,
  source attribution and reproducible interfaces instead.
- Do not force-push, rewrite history, discard another contributor's work or add
  automatic AI coauthor trailers. Preserve human credits and the README AI notice.
