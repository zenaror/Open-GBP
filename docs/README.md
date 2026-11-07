# Public technical documentation

- [DEVELOPMENT.md](DEVELOPMENT.md): container, toolchain, emulator and optional analysis setup.
- [RESEARCH_METHOD.md](RESEARCH_METHOD.md): evidence boundaries, hardware safety and compatibility contracts.
- [VALIDATION.md](VALIDATION.md): host tests, fixtures, formats and historical regression oracles.
- [ROADMAP.md](ROADMAP.md): product goals and acceptance criteria.
- [hardware/](hardware/README.md): topology, High-Speed Port and GBS-DOL architecture.
- [protocol/](protocol/README.md): initialization, registers, video, audio and input.
- [../tools/README.md](../tools/README.md): deterministic analysis and parser workflows.
- [../captures/README.md](../captures/README.md): published fixture catalogue and provenance.
- [maintenance/HISTORY_MIGRATION.md](maintenance/HISTORY_MIGRATION.md): historical Git identity recovery.

Evidence identifiers in technical pages describe narrowly scoped published
observations or code properties. The validation tools resolve legacy identifiers
against a fixed historical regression revision and verify its document digests;
these data are not a live operational journal. Current public interfaces and
limits are documented here without requiring a private account or service.
