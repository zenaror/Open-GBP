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
VIDEO sequence capture and four long-run video state scans). The last two reached
the 120 s scientific target. `GBP-VIDEO-002-R3` / build `vstate-0003` proved the
nonfatal-disagreement policy but produced contaminated diagnostics (GBP-HW-104);
`GBP-VIDEO-002-R4` / build `vstate-0004` re-ran the same policy with correct
attribution — **29 disagreements survived, 29 of 29 records internally coherent,
sidecar strict-valid** — which makes **R3's physical validation COMPLETE** and
**unblocks `GBP-VIDEO-003`** (GBP-HW-108…115), whose controlled-colour
experiment is now **DESIGNED and IMPLEMENTED 2026-09-17, NOT PHYSICALLY
EXECUTED** (§V3.0 to §V3.25): an AGB stimulus ROM, a GameCube probe reusing the
validated service path, the `OGBPCOL1` v1 sidecar and an offline analyser that
decides the mapping from raw bytes alone. Its first implementation was blocked by
a microaudit for doing full-frame work between the ACK and the RE-ARM; the
capture now decides stability from the per-block signatures the model already
computes and never touches a frame's bytes (§V3.23 to §V3.25). Execution waits on one documented
dependency: a way to deliver a controlled GBA ROM to the physical unit. The normative binary layouts (the
160-byte diagnostic record, the 1024-byte semantic block, the OGBPSEQ1 v4/v5
header) live in that file as subsections R3.24 to R3.29 and R4.7.

Sidecar formats of the GBP-VIDEO family, all dispatched strictly by version and
none able to read another's file:

```text
OGBPSEQ1 v1   GBP-VIDEO-001, build video-0001    historical, frozen
OGBPSEQ1 v2   GBP-VIDEO-002, build vstate-0001   historical, frozen
OGBPSEQ1 v3   GBP-VIDEO-002, build vstate-0002   historical, frozen
OGBPSEQ1 v4   GBP-VIDEO-002-R3, vstate-0003      historical, frozen, PHYSICALLY
                                                 EXECUTED, KNOWN PRODUCER DEFECT
OGBPCOL1 v1   GBP-VIDEO-003, color-0001         IMPLEMENTED, not physically executed;
                                                 LAYOUT FROZEN at the implementation
                                                 checkpoint - a later change is a new
                                                 version, never an edit of v1;
                                                 a DEDICATED format - frame history,
                                                 certified window (slot, order and
                                                 signatures), the shared R3 record and
                                                 whole raw frames streamed straight from
                                                 the state model's ring. Never OGBPSEQ1
OGBPSEQ1 v5   GBP-VIDEO-002-R4, vstate-0004      PHYSICALLY EXECUTED 2026-09-17;
                                                 same layout as v4, stricter producer
                                                 contract enforced by cross-field invariants;
                                                 VALIDATED ON THE EXERCISED
                                                 SOURCE_SERVICED / Disc-extra PATH
```

The v4 defect is GBP-HW-104: in the physical `vstate-0003` file the current-cycle
fields of a diagnostic record (authoritative value, service decision, ACK and
re-arm words and their timestamps) may belong to a **later** cycle than the
disagreement the record opened. The format stays frozen and its parser keeps
accepting the file exactly as before — refusing real evidence would lose it.
`tools/vstate.py diag` instead reports the cross-field contradictions as
**PRODUCER WARNINGS**, so the defect is detectable offline without a reparse
rule. The trusted and untrusted field split for that file is written into
`captures/fixtures/hw-gamecube-gbp-2026-09-17-vstate-0003.gbpreplay`.
