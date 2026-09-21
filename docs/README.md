# Open-GBP Documentation

```text
ROADMAP.md              phases and acceptance criteria
RESEARCH_METHOD.md      evidence classes and promotion rules

hardware/ARCHITECTURE.md   physical + logical topology (GameCube ↔ HSP ↔ GBS-DOL ↔ CPU AGB)
hardware/HSP.md            how the High Speed Port is reached (ARAM DMA, PI IRQ 13)
hardware/GBS-DOL.md        externally observable behavior of the bridge chip

protocol/REGISTERS.md      register windows, transfer format, bit tables (Phase 2 reconstruction;
                           rows citing a GBP-HW- id are hardware-verified)
protocol/INITIALIZATION.md detection / start / IRQ service / stop sequences (same rule)
protocol/VIDEO.md          the VIDEO path consolidated after Phase 4 (block, frame, service,
                           startup, presentation-path structure), every row with its id
protocol/INPUT.md          the KEYPAD / input path consolidated after GBP-INPUT-001 (window, word,
                           bit assignment with its status, cadence, the mapping as POLICY)

research/EVIDENCE.md       every claim with sources and status
research/UNKNOWNS.md       open questions, prioritized
research/HARDWARE_TESTS.md physical tests executed, and designs not yet executed
research/DEVLOG.md         chronological log
research/PHASE4_ASSESSMENT.md  Phase 4 against its acceptance criterion, term by term (2026-09-21)

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

As of 2026-09-21 the project has executed physical runs through Phase 4
(detection, initialization, the interrupt path, the service cycle, the video
state scans, the controlled-colour runs, and the streaming runs `stream-0003`
… `stream-0013` / runs 1–13 with real and controlled cartridges), and Phase 4
has been assessed against its acceptance criterion: `PHASE 4 VERDICT` in
`ROADMAP.md` (SATISFIED WITH NAMED RESIDUALS), argued term by term in
`research/PHASE4_ASSESSMENT.md`. The consolidated video-path reference that
came out of it is `protocol/VIDEO.md`. The current state and the next safe
action are in `HANDOFF.md`. The normative binary layouts of the video state
scans (the 160-byte diagnostic record, the 1024-byte semantic block, the
OGBPSEQ1 v4/v5 header) live in `research/HARDWARE_TESTS.md` as subsections
R3.24 to R3.29 and R4.7; the frozen formats of the streaming runs
(OGBPIDX1, OGBPIDXCAP1, OGBPDISP2, OGBPCOORD1, OGBPFULL1, OGBPVI1) are listed
under "Frozen contracts" in `HANDOFF.md`. The table below is the format
history of the state-scan family as of 2026-09-17, kept as written.

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
