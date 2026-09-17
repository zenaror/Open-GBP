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
research/HARDWARE_TESTS.md physical tests executed, and designs not yet executed
research/DEVLOG.md         chronological log

mobile-adapter/            reserved for Phase 13
```

Consolidated pages (`hardware/`, `protocol/`) only contain claims that
have an id in `research/EVIDENCE.md`; their status letters (F/C/H/U) are
copied from there.

## Where the current state lives

`research/HARDWARE_TESTS.md` is the authority for what has and has not touched
hardware. Every entry says so in its heading, and the two states are kept apart on
purpose:

```text
PHYSICALLY EXECUTED       the run happened; its raw log is under logs/ (never
                          versioned), its fixture under captures/fixtures/, and its
                          measurements carry GBP-HW-… ids in research/EVIDENCE.md
DESIGNED / NOT IMPLEMENTED  a specification only. No code, no DOL, no observation.
                          Nothing in such an entry is evidence about the device
```

As of 2026-09-17 the project has executed physical runs through Phase 4
(detection, initialization, the interrupt path, one complete service cycle, a
VIDEO sequence capture and two long-run video state scans), and the next step —
`GBP-VIDEO-002-R3` / build `vstate-0003` — is **DESIGNED and HARDENED, NOT
IMPLEMENTED, NOT PHYSICALLY EXECUTED**. Its normative binary layouts (the
160-byte diagnostic record, the 1024-byte semantic block, the OGBPSEQ1 v4 header)
live in that file as subsections R3.24 to R3.29.

Sidecar formats of the GBP-VIDEO family, all dispatched strictly by version and
none able to read another's file:

```text
OGBPSEQ1 v1   GBP-VIDEO-001, build video-0001    historical, frozen
OGBPSEQ1 v2   GBP-VIDEO-002, build vstate-0001   historical, frozen
OGBPSEQ1 v3   GBP-VIDEO-002, build vstate-0002   historical, frozen
OGBPSEQ1 v4   GBP-VIDEO-002-R3, vstate-0003      implemented, not physically executed
```
