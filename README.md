# Open-GBP

Independent open-source runtime research, documentation and tools for the
**physical Nintendo Game Boy Player**, controlled through the GameCube High-Speed
Port. GB, GBC and GBA software runs on the Player's real AGB CPU, not an emulator.

## Status and scope

This is a research prototype with diagnostic POCs, host regressions and documented
hardware interfaces. It is not a finished replacement for the Nintendo Start-up
Disc or Game Boy Interface. Build success or a synthetic test does not establish
hardware compatibility or general lossless video/audio behavior.

The target includes normal cartridge play, video, input, audio, GBP-aware features,
rumble and physical Link Port peripherals. Virtual Mobile Adapter support is a
later additive extension. See the [product roadmap](docs/ROADMAP.md).

## Build

Use a full clone and restore the original historical commit objects required by
existing regression pins:

```sh
git clone https://github.com/zenaror/Open-GBP.git
cd Open-GBP
python3 tools/history_recover.py
```

GameCube programs use rootless Podman with its Compose provider and the pinned
libogc2/devkitPPC image in `Dockerfile`/`compose.yaml`; no host devkitPPC installation
is required:

```sh
systemctl --user start podman.socket
make env-check
make build
```

A host C compiler, Python 3 and pytest are used for host validation. The complete
Python suite also inspects PowerPC artifacts, so run the build above first:

```sh
make test-unit
make test-python
```

`make test` also builds and inspects GameCube executables. See
[development](docs/DEVELOPMENT.md), [validation](docs/VALIDATION.md) and
[tools](tools/README.md) for dependencies, outputs and optional analysis inputs.

## Hardware use

POCs are purpose-specific diagnostic programs, not interchangeable game launchers.
Read the relevant program's documentation and the [research/safety
method](docs/RESEARCH_METHOD.md) before preparing a physical test. Preserve exact
accepted images before rebuilding; identify every candidate by a clean commit,
build ID and SHA-256. A freshly built image is not automatically physically tested.
Logs should use SD2SP2 outside timing-critical code paths.

## Organization

| Responsibility | Location |
| --- | --- |
| Contributor entry | [AGENTS.md](AGENTS.md) |
| Architecture and public interfaces | [docs/](docs/README.md), `docs/hardware/`, `docs/protocol/` |
| Runtime, transport, logging and audio | `src/` |
| GameCube diagnostics and cartridge stimuli | `poc/`, `stimulus/` |
| Reproducible host validation | `tests/`, `captures/fixtures/`, `Makefile` |
| Analysis, parsers and build utilities | `tools/` |
| Product goals | [docs/ROADMAP.md](docs/ROADMAP.md) |

Third-party checkouts under `external/` and legally supplied references under
`input/` are not Open-GBP dependencies to redistribute. Raw captures and reference
inputs stay unmodified. Generated `build/` outputs may contain exact accepted
binaries or analysis annotations and are not automatically disposable.

## Contributing

Keep implementation and evidence claims separate. Public architecture, formats,
validation instructions and limitations must stand on their own. Follow
[AGENTS.md](AGENTS.md) and the [research method](docs/RESEARCH_METHOD.md); use normal,
reviewable commits and preserve unrelated work. Existing historical regression
oracles are immutable data, not current project assignments or implementation plans.

Changes are summarized in [CHANGELOG.md](CHANGELOG.md).

## AI Notice

Parts of this project were developed with assistance from AI tools, including
code generation, research, analysis and documentation. Existing human credits
and the evidence classifications of published technical material remain applicable.
