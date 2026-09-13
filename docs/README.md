# Open-GBP Documentation

```text
ROADMAP.md              phases and acceptance criteria
RESEARCH_METHOD.md      evidence classes and promotion rules

hardware/ARCHITECTURE.md   physical + logical topology (GameCube ↔ HSP ↔ GBS-DOL ↔ CPU AGB)
hardware/HSP.md            how the High Speed Port is reached (ARAM DMA, PI IRQ 13)
hardware/GBS-DOL.md        externally observable behavior of the bridge chip

protocol/REGISTERS.md      register windows, transfer format, bit tables (preliminary)
protocol/INITIALIZATION.md detection / start / IRQ service / stop sequences (preliminary)

research/EVIDENCE.md       every claim with sources and status
research/UNKNOWNS.md       open questions, prioritized
research/HARDWARE_TESTS.md physical tests executed (none yet) and planned
research/DEVLOG.md         chronological log

mobile-adapter/            reserved for Phase 13
```

Consolidated pages (`hardware/`, `protocol/`) only contain claims that
have an id in `research/EVIDENCE.md`; their status letters (F/C/H/U) are
copied from there. As of Phase 2 nothing has been verified on physical
hardware by this project.
