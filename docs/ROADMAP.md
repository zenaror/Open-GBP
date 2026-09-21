# Open-GBP Roadmap

This roadmap intentionally separates Game Boy Player research from later Mobile Adapter work.

Each phase should have explicit acceptance criteria before later layers are allowed to depend on it.

## Phase 0 — Reproducible development environment

Establish a reproducible GameCube development environment.

Requirements:

* pinned Docker image;
* devkitPPC available;
* libogc2 available;
* `gamecube_rules` available;
* `elf2dol` available;
* host files created with the normal user UID/GID;
* repeatable build commands.

Acceptance:

```text
A clean checkout can enter the development container and build
GameCube software without installing devkitPPC on the host.
```

## Phase 1 — Project and test infrastructure

Create the initial source layout and automated test framework.

The first GameCube program should be created by the development agent itself so that the build system is understood from the beginning.

Initial targets:

```text
poc/smoke-test/
tests/
tools/
```

Testing infrastructure should support:

* native host-side tests;
* mock hardware transports;
* deterministic test vectors;
* trace recording and replay;
* build identifiers;
* test IDs;
* machine-readable logs where useful.

Acceptance:

```text
Native tests run automatically.
A minimal GameCube DOL builds reproducibly.
The DOL can be smoke-tested without changing physical GBP state.
```

## Phase 2 — Reference analysis and hardware documentation

Study available sources before inventing behavior.

Primary references may include:

* original Game Boy Player Startup Disc owned by the user;
* Dolphin Game Boy Player HSP implementation;
* public libogc2 code;
* Game Boy Player Player hardware research;
* later, Game Boy Interface binaries owned by the user.

Enhanced mGBA may be used for generic GameCube infrastructure but must not be treated as an implementation of the physical Game Boy Player.

Produce documentation for:

```text
GameCube HSP
GBS-DOL
register map
transaction format
initialization
interrupt behavior
known/unknown bits
```

Acceptance:

```text
Every implemented hardware operation has documented provenance,
confidence level, and an automated representation where practical.
```

## Phase 3 — Physical GBP detection and initialization

**Status: COMPLETE (2026-09-16).** Detection (seven GBP-attached runs, two
without the GBP), the CONTROL transform and the IRQ programming
(GBP-INIT-001…003A), the delivery of an HSP cause to the CPU (GBP-INIT-003B,
004) and the first complete service — drained AUDIO/VIDEO blocks,
acknowledge, re-arm, next cause captured while masked, stop sequence
(GBP-AV-SERVICE-001) — were executed on the physical GameCube + Game Boy
Player with independent code (`docs/research/HARDWARE_TESTS.md`,
`docs/protocol/INITIALIZATION.md` §14, DEVLOG 2026-09-16 "GBP-AV-SERVICE-001
executed"). The closing criterion recorded in the DEVLOG (first physical
service → re-arm → next cause) is met; the remaining microscopic unknowns
(U-GBP-027 investigative sub-items, U-GBP-028, the bit-15 mechanism of
U-GBP-007) are documented as non-blocking. Sustained operation over many
cycles is Phase 4 and later work.

Create a standalone open-source GBP runtime/probe.

Goals:

* identify the physical GBP;
* perform the minimum safe initialization sequence;
* read relevant status;
* establish deterministic logging;
* avoid speculative writes to unknown registers.

Diagnostics should support:

* on-screen state;
* RAM event buffering;
* SD2SP2 trace/log export.

Acceptance:

```text
The software reliably detects and initializes the physical GBP
on real hardware without relying on proprietary runtime code.
```

## Phase 4 — Video

**Status: ASSESSED 2026-09-21 against the acceptance criterion below (GitHub
Issue #17) — the verdict and the named residuals are in the "Phase 4
assessment" subsection at the end of this section; the full term-by-term
assessment is `docs/research/PHASE4_ASSESSMENT.md`, and the consolidated
programming reference for the video path is `docs/protocol/VIDEO.md`.**
Physically established over runs `video-0001` … RUN 13 (entered 2026-09-16):
transport, block sequence and **colour** (GBP-AV-SERVICE-001, GBP-VIDEO-001,
GBP-VIDEO-003); real cartridge video on screen (`stream-0003`, `stream-0004`,
run 8 / GBP-VIDEO-005: GBP-HW-144, 152, 224…229); source-frame continuity
`OBSERVED_CONTIGUOUS` within a prospectively qualified window on seven indexed
runs (GBP-HW-188/189, 193, 203, 232, 240, 246, 257) and its one exception
explained by the stimulus's own scheduling (GBP-HW-251, GBP-VID-034 RESOLVED);
a source-lossless two-framebuffer presentation policy, Policy A, clean on
eight consecutive runs including the retail cartridge (GBP-HW-205…211, 217,
225, 236, 241, 247, 253, 259); a NORMAL startup that shows the user real video
~165 ms after the CONTROL transform with no synthetic frame and no wait
(GBP-HW-214…215, 224, 229, 235, 241, 247, 253, 259); full-frame source →
texture fidelity on eight prospectively sampled frames, GBP-VIDEO-008 = PASS
(GBP-HW-258); physical scanout as CLAIM-D, GBP-VIDEO-007 = PASS (GBP-HW-260);
and a research-only witness eligibility gate (GBP-HW-237). **Still not
established:** correctness of retail content by measurement, physical pixel
equality, per-frame scanout accounting, presentation/scaling (see the
pixel-perfect requirement under Phase 9), audio, input, and any
Ethernet-connected or BBA-initialised topology. **BBA physically present,
Ethernet disconnected** is a paired topology control against run 9 with no
detected regression (GBP-BBA-001, §V5.57.14) — a baseline, not BBA validation,
and Phase 11 does not move. The controlled video sequence that kept the BBA
disconnected is closed (§V5.56.12). **U-GBP-011 closed
2026-09-18** by the pre-registered confirmatory run `color-0002`: the VIDEO
window exchanges the two outer 5-bit groups relative to the AGB framebuffer, so
the references' GX RGB5A3 reading is the displayed colour (GBP-HW-131). GBP-VIDEO-002 has now been run
physically **four** times (`vstate-0001`, `vstate-0002`, `vstate-0003`,
`vstate-0004`); the last two reached the 120 s target, and the fourth validated
the semantic-disagreement policy with trustworthy diagnostics, which **unblocks
GBP-VIDEO-003**. The entry experiment
GBP-AV-SERVICE-001 captured the first physical VIDEO (0xF00) and AUDIO
(0x1000) blocks with one whole-block DMA each and preserved them raw
(fixture + sidecar). Static basis fixed on 2026-09-16
(`docs/research/VIDEO_PATH.md`): both references read a block as 4 raster
lines × 240 pixels × 4 bytes (bytes 1/3 of each word), 40 blocks per frame,
frame flag on the first pixel, and 15 colour bits which both *read* in GX
RGB5A3 order — which was a property of the two decoders until GBP-VIDEO-003
measured the device and confirmed it (U-GBP-011 CLOSED); both embed the AGB idle screen
(an offline oracle without a cartridge). Short sequence:

* **GBP-VIDEO-001** (**PHYSICALLY EXECUTED 2026-09-16**, `video-0001`, commit
  `6930dde`; `poc/gbp-video-capture-probe/`): 209 cycles of repeated drained
  service, 88 VIDEO and 144 AUDIO blocks, one complete 40-block frame-start
  interval at 59.547 Hz, both predicates agreeing on all 88 blocks, a uniformly
  white frame matching the references exactly where they are white. Originally
  planned as:
  bounded repeated drained service, no cartridge — up to 88
  VIDEO blocks with timestamps, both frame-start predicates, the source
  pattern per cause; establishes blocks per frame, order, boundaries,
  cadence and repeated-service stability; offline assembly against the
  embedded idle screen.
* **GBP-VIDEO-002** (**PHYSICALLY EXECUTED 2026-09-16**, `vstate-0001`, commit
  `e8f3a69`, `poc/gbp-video-state-probe/`): 51 751 service cycles over 8.187 s,
  489 frames, 477 intervals of exactly 40 blocks at 59.727 Hz, and a structured
  screen that appears 0.5 s after the AGB starts, animates, and settles into a
  state matching **GBI reference table B in all forty blocks**. Reconstructing
  the preserved raw frames gives a legible animated GAME BOY logotype at
  240 × 160, which promotes the block geometry to a physical fact
  (GBP-HW-074…087). The service ABORTED at cycle 51 750 on a semantic
  disagreement between the two readings of the IRQ register whose bytes were not
  preserved (U-GBP-032), so the 120 s negative target was not reached and this
  run makes no negative claim. Originally designed as: a **120-second**
  frame-signature scan without a Game Pak, sized
  to the nominal interval of the Start-up Disc's own detector window (24 000
  invocations of a 5.000 ms periodic callback, proved from the binary; 120 s is a
  lower bound because the scheduler drops missed periods). Per-frame signatures of 40
  checksums instead of per-delivery records (~639 000 deliveries are expected),
  a u64 time base because a u32 tick wraps at 106 s, a learned baseline, and an
  episode state machine that preserves raw frames around a change and closes when
  the changed state repeats, with **no early stop** — the runtime has no oracle,
  so it cannot know which stable state is the one sought, and the run observes
  the whole window and records every episode for offline classification. The
  120 s are counted **after** baseline_valid,
  because only then is there a reference to compare against; the frame store and
  a 180 s hard wall-clock limit are safety caps, not the window. Answers whether the screen
  both references recognise ever reaches the VIDEO stream without a cartridge
  (U-GBP-031) and gives a cadence uniform from the first useful frame
  (U-GBP-030). The implementation reuses the physically validated interrupt path
  byte for byte, adds a 64-bit time base because a 32-bit tick counter wraps
  inside the window, tears the hardware down before it summarises anything, and
  streams its multi-megabyte sidecar rather than staging it. Its full nominal
  scan runs in the host suite at about 800 000 synthetic deliveries.
* **GBP-VIDEO-003**: colour. **DESIGN FINALIZED and IMPLEMENTED 2026-09-17
  (HARDWARE_TESTS §V3.0 to §V3.25); PHYSICALLY EXECUTED twice on 2026-09-18 — the
  result is in the dedicated bullet below and in §V4.10.** The first
  implementation was blocked by the microaudit for doing full-frame
  `memcmp`/`memcpy` between the ACK and the RE-ARM; the capture now decides
  stability from the 40 per-block signatures the model already computes, never
  touches a frame's bytes, and the certified frames stay in a four-slot ring
  until the writer streams them after the teardown (§V3.23 to §V3.25). Three components
  exist: the AGB stimulus (`stimulus/agb-color-bars`), the probe
  (`poc/gbp-video-color-probe`, Build ID `color-0001`) and the offline analyser
  (`tools/vcolor.py`), with the `OGBPCOL1` v1 sidecar between them. A controlled AGB Mode 3
  stimulus of eight 30-pixel bars — three full 5-bit groups, three single low
  bits, plus `0x0000` and `0x7FFF` as permutation-invariant controls, with bit 15
  never written — captured through the validated service path into a dedicated
  `OGBPCOL1` sidecar that preserves whole raw blocks. Exactly one candidate
  transformation must reproduce all eight observed values or the run is
  INCONCLUSIVE. The execution dependency this bullet used to carry — no known way
  to deliver a controlled GBA ROM to the physical unit — was **RESOLVED on
  2026-09-18** by the operator's EZ-Flash Omega DE in NOR / Mode B, route 1 of
  §V3.7, with the predicted `CONTROL orig=92` presence bit observed.

  The gate that used to block this step is gone. It was a run surviving the
  semantic disagreement of the IRQ window with trustworthy diagnostics, and
  `vstate-0004` delivered it: **29 `SOURCE_SERVICED` disagreements, none fatal,
  correct current-cycle attribution in 29 of 29, 120.009 s of valid observation**
  (GBP-HW-108…115). It was never gated on U-GBP-033, which stays open — the
  mechanism behind the replica non-uniformity does not have to be understood,
  only survived, and it has now been survived 52 times across two long runs.

  The experiment needs a source whose true appearance is known independently of
  the references, because a reference comparison can only show that two encodings
  agree, never which channel is which. That is what the eight-bar stimulus is:
  every value known by construction, the low-bit bars making an intra-channel
  reversal falsifiable, and the popcount fingerprint letting the probe recognise
  the pattern without assuming the answer.
  Rendering the frames on the GameCube is deliberately **not** part of this
  experiment: the mapping is decided from preserved raw bytes offline, and a
  texture drawn under an assumed channel order would prove nothing about the
  device. First rendered frames and KEYPAD writes belong to a later step. The
  gate that guarded this one existed because both early GBP-VIDEO-002 runs ended
  on a semantic disagreement of the IRQ window (2026-09-16 at cycle 51 750,
  2026-09-17 at cycle 517), and a colour capture cannot afford an abort at an
  arbitrary point; the nonfatal policy validated by `vstate-0004` is what removed
  that risk, and GBP-VIDEO-003 reuses it unchanged (§V3.9).
* **GBP-VIDEO-002-R3** (build `vstate-0003`): the intervening step, **PHYSICALLY
  EXECUTED 2026-09-17**. It reached the 120 s scientific target, observed the
  structured change again, and survived 23 semantic disagreements without stopping
  — the policy behaviour is strongly corroborated. Its diagnostic records, however,
  carry current-cycle fields belonging to later cycles (GBP-HW-104), so R3's
  physical validation is **INCOMPLETE** and **GBP-VIDEO-002-R4** (build
  `vstate-0004`, OGBPSEQ1 v5, **designed 2026-09-17, not implemented**) must fix the
  attribution and be run before the gate below opens. Makes a disagreement confined to the two
  serviced source bits a counted, preserved, nonfatal anomaly serviced from GBI's
  bitwise majority; keeps every other difference fatal, and keeps the independent
  `anomaly_unexpected_source` guard firing on the authoritative value whatever the
  delta is. Records, for each event, whether the source the majority omitted was
  present in the next cause and how long after the re-arm — as observations, with
  no runtime label claiming a source could not be new. Quarantines any VIDEO block
  drained only because the majority carried a source the Disc reading did not, so
  it can never form a baseline, count toward valid observation, validate a
  structured change or feed colour evidence. Adds a bounded 256-record diagnostic
  store (+41 728 B) and OGBPSEQ1 v4; v1, v2 and v3 stay frozen.
* **GBP-VIDEO-002-R4** (build `vstate-0004`): **PHYSICALLY EXECUTED 2026-09-17,
  PHYSICAL VALIDATION PASSED.** It reached the 120 s target again (1 114 005
  cycles over 175.848 s), survived **29** semantic disagreements, and produced a
  sidecar in which every record carries the authoritative value, service decision,
  ACK and re-arm of its own cycle — strict-valid under the v5 cross-field rules,
  zero producer warnings. That completed R3's physical validation. Fixes the one
  defect the physical
  `vstate-0003` run exposed: the v4 producer addresses the current cycle's
  diagnostic record as "the last record opened", so a record that is not closed in
  its own cycle absorbs the authoritative value, service decision, ACK and re-arm
  of later cycles (GBP-HW-104). R4 replaces that with an explicit record handle
  carried by the cycle, separates the two lifetimes (current-cycle fields end with
  the cycle, follow-up fields stay open across cycles) and emits OGBPSEQ1 v5, whose
  semantic block records which fields each record actually owns. The observed
  policy behaviour does not change: the same three disagreement classes, the same
  authority composition, the same independent pending guard, the same
  quarantine. OGBPSEQ1 v4 stays frozen as the historical format of the
  `vstate-0003` run. Design, implementation and physical result in HARDWARE_TESTS
  §R4.1 to §R4.10a. Only the `SOURCE_SERVICED` / Disc-extra path was exercised
  physically; the producer's other branches stay host- and mock-tested.
* **GBP-VIDEO-003** (**PHYSICALLY EXECUTED twice 2026-09-18**): `color-0001`
  certified but failed its own pre-registered full-raw gate and stays
  INCONCLUSIVE permanently; `color-0002`, judged by the contract
  pre-registered in HARDWARE_TESTS §V4, returned
  `CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP` and closed U-GBP-011
  (GBP-HW-120…126, GBP-HW-127…133).
* **GBP-VIDEO-004** — **NEXT**: sustained streaming with a real cartridge (frame
  pacing, dropped-block policy, output modes) — the bridge to Phase 7.
  **DESIGN / PRE-REGISTRATION written 2026-09-18, HARDWARE_TESTS §V5; not
  implemented, not run.** It defines the producer/consumer boundary that keeps
  every frame operation out of the validated service path, a bounded drop-oldest
  queue, `HOLD_PREVIOUS_FRAME` as the display policy with no synthesised pixels, a
  `GX_TF_RGB5A3` output path that needs no channel arithmetic because GBP-HW-131
  established the device already performs the swap, and a CONTROLLED motion
  stimulus with an embedded frame index so that frame loss is measured rather
  than inferred. This is also where the "first rendered frames" that
  GBP-VIDEO-003 deliberately deferred belong. **Since that date, EXECUTED** —
  `stream-0003` and `stream-0004` (real cartridge video on screen, §V5.34,
  §V5.38; GBP-HW-138…152); runs 1–6 on the indexed stimulus (§V5.41–§V5.50:
  the stimulus corrected twice, the prospective window, the downstream trace,
  Policy A; GBP-HW-153…212); run 7 NORMAL startup (§V5.53; GBP-HW-213…222);
  run 8 = **GBP-VIDEO-005**, the retail cartridge on the NORMAL startup, PASS
  with a debug-UX note (§V5.54; GBP-HW-223…230); run 9 the research not-before
  gate (§V5.56; GBP-HW-231…238); run 10 = **GBP-BBA-001** (§V5.57;
  GBP-HW-239…243); run 11 = **GBP-VIDEO-006** (§V5.58; GBP-HW-244…249); then
  **GBP-VIDEO-007 / GBP-VIDEO-008** (§V6): RUN 12 INCONCLUSIVE / INCONCLUSIVE
  on the stimulus's own scheduling (§V6.20, §V6.22; GBP-HW-250…255) and RUN 13
  with `coord-0002` GBP-VIDEO-007 = PASS · GBP-VIDEO-008 = PASS inside their
  pre-registered boundaries (§V6.25; GBP-HW-256…260).

No further micro-probes unless one of these raises a blocking question.

Implement and document the physical GBP video path.

Automated tests should cover:

* packet/register encoding;
* buffer boundaries;
* frame conversion where applicable;
* deterministic synthetic frame inputs;
* recorded hardware trace replay.

Acceptance:

```text
A real cartridge running on the physical GBP produces stable,
correct video through the open-source runtime.
```

### Phase 4 assessment (2026-09-21, GitHub Issue #17)

Assessed term by term against the criterion above, on the evidence ids of
`docs/research/EVIDENCE.md` and nothing else; the full assessment is
`docs/research/PHASE4_ASSESSMENT.md` and the verdict is repeated in
`docs/HANDOFF.md` in the same words:

```text
PHASE 4 VERDICT: SATISFIED WITH NAMED RESIDUALS
```

*Real cartridge:* a retail cartridge ran through the runtime on the physical
Game Boy Player three times (`stream-0003`, `stream-0004`, run 8), with the
transport, the NORMAL startup and Policy A measured clean on retail content
(GBP-HW-138…151, 224…226) and the picture observed by the operator (GBP-HW-144,
152, 227). *Stable:* zero transport faults in every streaming run, source-frame
continuity within every prospectively qualified window except the one the
stimulus itself explained, zero interior source drops with bounded hand-off
latency on eight runs, and the same ~165 ms startup on eight runs
(GBP-HW-188…259 as cited in the assessment). *Correct video:* geometry
(GBP-HW-081), frame composition (GBP-HW-076, 077), colour order (GBP-HW-131),
full-frame source → texture fidelity on eight sampled frames (GBP-HW-258) and
physical scanout as CLAIM-D (GBP-HW-260) are FACT on controlled stimuli within
their boundaries. *Through the open-source runtime:* every run executed a DOL
built from this repository with its identity recorded (ENV-HW-001; the
artifact rows of every run), with the Start-up Disc and GBI used as static
references only.

The one asymmetry, argued rather than assumed: the measured correctness and
continuity rest on controlled synthetic stimuli (`indexed-0003`, `coord-0001`,
`coord-0002`), because each measurement needs what a retail cartridge cannot
supply — a frame index, an injective oracle, known digits. On retail content
the evidence is machine-side metrics identical to the controlled runs plus
operator observation; the transfer is an inference about a content-blind path,
CORROBORATED and not FACT. The ROADMAP places cartridge validation in Phase 7,
so that residual is named and owned rather than allowed to block the phase.

**What Phase 4 does not establish, and who owns it:**

| residual | owner |
| --- | --- |
| correctness of retail content by measurement (no oracle-based colour / geometry / fidelity check on a retail picture; operator observation plus a content-blind path) | **Phase 7** — representative cartridges, the compatibility matrix |
| presentation, scaling, aspect, filtering; the pixel-perfect requirement GBP-VID-032 | **Phase 9** — the requirement is written there and in the runtime (`poc/gbp-video-stream-probe/source/main.c`: "Scaling and aspect are Phase 9 policy"); crossing to it is not authorised by this assessment |
| physical pixel equality on any display; per-frame scanout accounting | **not scheduled** — established by nothing; a capture device on the video output would be the instrument |
| duration and breadth of stability (≈ 44 s with presentation, one console, one GBP, one retail title; the consumer slice's timing margin unmeasured); the GB/GBC family | **Phase 12** (duration, margin), **Phase 7** (titles, GB/GBC) |
| the colour result's intra-group limit (§V3.19) | **not scheduled** |
| bytes 0/2 of the pixel word (U-GBP-029), bit 15's origin (U-GBP-034), the startup-region short intervals (U-GBP-030), the IRQ-window non-uniformity's mechanism (U-GBP-033) | **Phase 4 research residuals**, open in `UNKNOWNS.md`, non-blocking |
| rate conversion (≈ 7 repeated display intervals per 34 s, GBP-PHY-003) | **Phase 9** — a presentation/timing policy, nothing to fix here |
| audio; input | **Phase 6**; **Phase 5** |
| Ethernet-connected or BBA-initialised topologies | **Phase 11** |
| production UX (debug console flash, research witness, no menu) | **Phase 9**, **Phase 12** |

This assessment re-judges no run, promotes no evidence status, closes no
unknown and mints no id; RUN 12 stays INCONCLUSIVE / INCONCLUSIVE and RUN 13's
two PASS verdicts keep their boundaries. The consolidated documentation it
produced is `docs/protocol/VIDEO.md` and the refreshed video rows of
`docs/hardware/ARCHITECTURE.md`, `docs/hardware/GBS-DOL.md` and
`docs/protocol/REGISTERS.md`, every sentence with its evidence id.

## Phase 5 — Input

**Status: ENTERED 2026-09-21 (GitHub Issue #18, research / design),
IMPLEMENTED AS SOFTWARE 2026-09-21 (GitHub Issue #19, candidate `stream-0014`)
and PHYSICALLY EXECUTED 2026-09-21 — RUN 14 and RUN 15, GBP-INPUT-001
(Hardware Issue #21; ingested `HARDWARE_TESTS.md` §V7.2, GitHub Issue #24):
Question M = PASS · Question O = AS-ASSIGNED in both runs — the first KEYPAD
words Open-GBP wrote reached the cartridge as the presses made, L at L and R
at R; U-GBP-010 CLOSED; the routing CORROBORATED, not FACT; the acceptance
criterion below is NOT yet assessed (the instrument is a test ROM, not a
game).** **EXECUTED AGAIN 2026-09-21 — RUN 17, RUN 18 and RUN 16 on
`stream-0015`, GBP-INPUT-002 (Hardware Issue #32; ingested §V7.4, GitHub
Issue #33): Question J = FACT for all ten KEYPAD word bits, bits 8 and 9 on
two controllers — the routing a physical FACT (hw, the runs); RUN 16 UNDECIDED
by the rule; the acceptance criterion still NOT assessed.** The keypad
path is reconstructed on paper in `docs/research/INPUT_PATH.md` in three
layers kept apart — the GBS-DOL KEYPAD window as the references write it
(L1), the logical GBA button set from GBATEK (L2), and the GameCube
controller → GBA mapping as this project's POLICY (L3). The physical record
starts from nothing: every keypad statement in the project is static
(GBP-KEY-001…005, GBP-VID-011). The static attempt on U-GBP-010 found the
Start-up Disc, GBI and Dolphin's model agreeing that the references write L
at word bit 8 and R at bit 9 (the reverse of KEYINPUT) — RESOLVED STATICALLY
at CORROBORATED, not FACT; U-GBP-010 stays OPEN on its own physical
condition and no order is adopted, implemented or defaulted. The input
architecture is designed behind the existing transport boundary (real /
mock / replay), additive to the validated service path in the pump slot, and
keeps the future poll-to-latch latency measurement expressible in the
`gbp_time64` time base without touching any sidecar (`INPUT_PATH.md` §7,
§8). Enhanced mGBA was obtained (`external/mgba`, commit `8692b26b…`) as a
GameCube-side polling / mapping reference only. **Next:** a functional
checkpoint that implements the module behind that boundary, and the first
physical KEYPAD write under its own pre-registration.

**Implemented 2026-09-21 (GitHub Issue #19), software-only:**
`src/gbp/gbp_input.c` behind the existing transport boundary (the mapping as
a policy table; the encoding descriptor as data in one place, filled with
the CORROBORATED assignment by the Operator's decision, status and falsifier
at the definition; one 32-byte write; write-on-change plus a 5 ms refresh),
the step as the first statement of the stream probe's pump slot, host tests,
and the build candidate `stream-0014` (`0ff8355`, SHA-256 `ef76a170c10d335e…`)
which is **not executed**: no run is pre-registered. The acceptance
criterion below is untested on hardware; U-GBP-010 stays OPEN (GBP-KEY-006).
**Pre-registered 2026-09-21 (GitHub Issue #20):** RUN 14 (stage 1, the
Enhanced Control Checker's counted walk A — L 1, R 2, A 3, B 4, SELECT 5,
START 6 — after the pre-hardware amendment of Issue #23), RUN 15 (walk B —
L 1, R 2, UP 3, DOWN 4, LEFT 5, RIGHT 6) and RUN 16 (the EZ-Flash menu's
L/R tabs, optional and independent) as GBP-INPUT-001 in `HARDWARE_TESTS.md`
§V7.1 — runs of the same `stream-0014` image, each ending at the witness
target ~40.4 s after the CONTROL transform — **NOT RUN / NOT AUTHORISED
HERE** at that checkpoint. RUN 14 was moved to the Operator by Hardware Issue
#21.

**Executed 2026-09-21 (Hardware Issue #21) and ingested 2026-09-21 (GitHub
Issue #24, `HARDWARE_TESTS.md` §V7.2; GBP-HW-261…265, GBP-KEY-008, GBP-KEY-009):**
RUN 14 (walk A) and RUN 15 (walk B) on the unchanged `stream-0014`, each
carried to the witness target. Machine side: `INPUT attempts = completed =
7 892 / 7 895, failed 0, 42 key changes` in each run — the runtime polled,
encoded and wrote, which is all the write-only window lets it show; transport,
startup and Policy A clean; `truncated=1` in both logs is the clipped
`ENVINPUT` record (GBP-KEY-008, a functional item). Human side: the Operator's
tally vectors `1 2 · · · · 6 5 3 4` and `1 2 3 4 5 6 · · · ·`, equal to the
walks' arithmetic expectation. Independently, the checker's tally screen is in
the preserved OGBPFULL1 frames of both runs and decodes pixel-exactly to the
same vectors (FACT as data). **Question M = PASS in both** (every pressed
button at its own counter, no unpressed counter moved, nothing moved without
a press; all ten buttons across the two runs) and **Question O = AS-ASSIGNED
in both** (L = 1, R = 2): U-GBP-010 CLOSED on its own condition with the
descriptor kept; the routing's classification stays CORROBORATED, not FACT,
because the Operator having pressed L exactly once is in no machine record —
the recorded finding is that one log line (the word at each key change,
GBP-KEY-009) would close that join by machine; not implemented. Not
established: latency of any kind, the need for the 5 ms refresh, any policy
value as more than policy, the official Nintendo pad (the runs used a generic
third-party controller's digital click — the Operator's post-run declaration,
Issue #25; the same Game Boy Player by his declared inventory) or other cartridges,
rumble, the display chain, and this phase's acceptance criterion — a real game
has not been played; RUN 16 was not run. **Promoted 2026-09-21 (GitHub Issue #26):** the
consolidated pages now carry the keypad plane — `docs/protocol/INPUT.md`
(window, word, polarity, bit assignment with its status, cadence, the
controller mapping as this project's POLICY, what is not established), the
keypad rows of `REGISTERS.md` (§2, §2.3), `GBS-DOL.md` and `ARCHITECTURE.md`,
and `INITIALIZATION.md` §15 — with the L/R order stated as CORROBORATED, not
FACT, the generic-pad scope beside it and GBP-KEY-009 named; no status
changed.

**Implemented 2026-09-21 (GitHub Issue #27), software-only:** GBP-KEY-009 —
every KEYPAD write that is not a refresh leaves one `KEY` ringlog line with
the word and three instants in the sidecars' time base, bounded, from the
pump slot — and the repair of GBP-KEY-008 (`ENVINPUT` + `ENVINPUT2`) with a
general payload guard, in the candidate `stream-0015` (`da06500`, SHA-256
`dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49`), **NOT executed, no run pre-registered, not staged** (GBP-KEY-010).
FACT for the L/R routing is now reachable by a run; it is not actual.
**Pre-registered 2026-09-21 (GitHub Issue #28):** RUN 17 (walk A) and RUN 18
(walk B) as GBP-INPUT-002 in `HARDWARE_TESTS.md` §V7.3 — the machine-join
runs of `stream-0015`. Question One was answered before any gate: the eight
OGBPFULL1 samples (one every 256 frames, 4.286 s) support no per-press join
and an interval-wise consistency check only, but the whole-run totals of the
KEY record against the decoded final tallies bind each pressed bit to its AGB
key uniquely by the distinct counts — FACT reachable per bit, without pacing
(excluded); latency stays out of reach. A failed join is reachable and
informative (NOT CLOSED), never a failed run. **NOT RUN / NOT AUTHORISED
HERE.** **Next:** the Hardware Issue the Orchestrator opens after validating
§V7.3 (RUN 17, then RUN 18, to the Operator); then this phase's real
acceptance with a commercial game, which the Operator schedules and which is
not pre-registered.

**Executed and ingested 2026-09-21 (GitHub Issues #32, #33):** RUN 17 (walk A,
the generic third-party pad), RUN 18 (walk B, the original Nintendo pad) and,
last, RUN 16 (the optional menu reading, original pad) on `stream-0015`;
`HARDWARE_TESTS.md` §V7.4. Read against §V7.3's frozen gates: the KEY record
joined to the checker's counters gives Question J = FACT for every pressed
word bit — all ten, bits 8 and 9 in both join runs — with no human count in
the chain; Question I EXACT in every interval; the Operator's vectors agree
and stay beside. **The routing of the KEYPAD word to the AGB's keys is a
physical FACT (hw, the runs)**: GBP-HW-266…271; GBP-KEY-004 promoted; the
consolidated pages moved to F (hw, run-scoped) with their history. RUN 16:
UNDECIDED for the join by the rule, M = PASS, O not readable (direction not
reported, not inferred). `truncated=0` in all three: GBP-KEY-008's repair
validated. Not established: latency, the refresh, pads beyond the two, a
game. **Next:** this phase's real acceptance with a commercial game — the
Operator schedules it, the Orchestrator writes its contract; not
pre-registered.

Implement and document GameCube controller → GBP keypad/input handling.

Automated tests should cover button combinations and encoding.

Acceptance:

```text
A real game can be controlled reliably using the GameCube controller.
```

## Phase 6 — Audio

Implement and document the GBP audio path.

Automated tests should cover buffering, state transitions, and malformed/edge input where practical.

Acceptance:

```text
A real cartridge produces stable audio without breaking video/input.
```

## Phase 7 — Cartridge compatibility

Validate both execution families:

```text
GBA mode
GB/GBC compatibility mode
```

Do not assume behavior observed in GBA mode also applies to GB/GBC mode.

Acceptance:

```text
Representative GBA and GB/GBC cartridges run with video, input,
and audio through the physical Game Boy Player.
```

### GBP-aware game features (requirement added 2026-09-15)

Parity with the Nintendo Game Boy Player Start-up Disc and with GBI is not
limited to video, audio, input and cartridge boot. Some games behave
differently when they detect that they run on a Game Boy Player, and the
Start-up Disc / GBI support that behavior; the runtime must aim to
reproduce it as part of normal compatibility, not as an optional feature:

* rumble on the GameCube controller for games that support it through
  the Game Boy Player;
* any GBP-dependent game mode or behavior supported by the Start-up Disc
  and/or GBI;
* the controller/input behavior associated with those features;
* every GBS-DOL signal, register, IRQ or path required to reproduce them.

The mechanism (which path carries the GBP detection and the rumble
commands — the internal serial path documented by GBATEK's "GBA Gameboy
Player" section is the leading candidate, U-GBP-026) is not assumed; it
is researched from the Start-up Disc, GBI, physical behavior, games known
to exercise the feature, and the references already accepted. When the
controller/cartridge-compatibility phases are reached, a compatibility
matrix specific to GBP-aware features, rumble included, is created.

Compatibility goal:

```text
If a game has a special behavior supported by the original Game Boy
Player or by GBI, Open-GBP must aim to reproduce that behavior.
```

## Phase 8 — Physical Link Port compatibility regression

The physical Game Boy Link Port is a first-class compatibility requirement.

Open-GBP must preserve the normal external serial behavior of the Game Boy
Player and must not make the Link Port dependent on Open-GBP-specific hardware
or protocols.

PicoAdapterGB is one known-good regression device and provides existing
physical evidence that normal serial communication through the GBP Link Port
works, but it is only one test case.

The scope of this phase is the physical Link Port itself and the normal
accessories/protocols used through it, including, where applicable:

- Game Boy Link Cable communication with another physical Game Boy;
- multiplayer/link features used by compatible games;
- official Game Boy Link Port accessories;
- physical Mobile Adapter GB;
- PicoAdapterGB;
- compatible third-party accessories;
- other normal serial modes exercised by cartridges through the Link Port.

Normal external communication must remain a transparent hardware path:

cartridge
   ↕
physical GBP Link Port
   ↕
external accessory / another Game Boy

Open-GBP must not require knowledge of a particular external accessory for this
path to operate normally.

Tests should therefore include multiple representative Link Port use cases,
rather than treating PicoAdapterGB as the compatibility target.

Acceptance:

- normal physical Link Port behavior remains compatible with the original
  Game Boy Player environment;
- multiplayer communication with a physical compatible Game Boy continues to
  work;
- PicoAdapterGB continues to work;
- physical accessories are not broken by Open-GBP initialization, IRQ,
  controller, audio/video, or shutdown handling;
- future internal serial functionality does not alter the external Link Port
  path when that functionality is disabled.

The future virtual Mobile Adapter implementation over the GameCube BBA is an
additive Open-GBP feature. It must not replace the physical Link Port or make
physical Link Port compatibility dependent on the virtual Mobile Adapter
implementation.

This is a permanent regression requirement for all later phases.

## Phase 9 — GBI-class functional parity

After the basic physical Game Boy Player runtime is stable, expand Open-GBP
toward functional parity with mature Game Boy Player software such as Game
Boy Interface.

This phase may include:

- additional video modes and presentation options;
- scaling and filtering controls;
- timing and latency improvements;
- configuration handling;
- compatibility fixes;
- runtime robustness;
- other features useful for normal Game Boy Player operation.

GBI may be analyzed as a behavioral and reverse-engineering reference, but
Open-GBP should remain an independently implemented open-source project.

Acceptance:

```text
Open-GBP can be used as a practical replacement for normal Game Boy Player
operation without requiring proprietary runtime software.
```

GBI-class parity includes the GBP-aware game features listed under
Phase 7 (rumble and GBP-dependent modes); their compatibility matrix
belongs to this phase and to Phase 7, with Phase 10 supplying the serial
mechanism if that is where the feature lives.


### Presentation requirement — pixel-perfect scaling (recorded 2026-09-20, GBP-VID-032)

Stated by the operator after GBP-VIDEO-005 and recorded here as a constraint on
work that has not begun. When presentation/upscale work starts:

* provide a **pixel-perfect mode** that preserves the source pixel lattice
  exactly: every source pixel maps to an equal-size output rectangle under an
  **integer nearest-neighbour** scale factor;
* no non-uniform X/Y stretching, no deformation of individual source pixels,
  no silent fractional stretch in that mode, and no smoothing as its default;
* if the output surface does not admit a full-screen integer scale, use
  letterbox/pillarbox, a centred viewport, or an explicitly selected alternate
  presentation policy — never deformed pixels;
* "pixel-perfect" means the source grid preserved under the selected integer
  scale, **not** a 1× output.

This is separate from video transport correctness, Policy A, startup timing and
research witness qualification, and nothing of it is implemented. No final
resolution or viewport is chosen here.

## Phase 10 — Internal SIO research

Investigate whether GameCube-side software can observe and/or drive the cartridge's serial communication internally through GBS-DOL/HSP.

Questions include:

* SIO control register semantics;
* SIO data register semantics;
* serial interrupt behavior;
* routing between internal HSP handling and the physical Link Port;
* GBA-mode behavior;
* GB/GBC-mode behavior;
* coexistence or exclusivity of internal and external communication.

Testing should begin read-only whenever possible.

Acceptance milestone A:

```text
GameCube software observes a deterministic serial event generated
by software running on the physical GBP.
```

Acceptance milestone B:

```text
GameCube software generates a deterministic response that is
observed by software running on the physical GBP.
```

Acceptance milestone C:

```text
The behavior required for GB/GBC operation is characterized.
```

## Phase 11 — Network/BBA

Network support is developed independently of Mobile Adapter logic.

Create a dedicated network POC and host-side test server.

Validate:

```text
BBA initialization
IP configuration
UDP
TCP
DNS if required
timeouts
nonblocking behavior
```

Timing-sensitive serial processing must never block on network I/O.

Acceptance:

```text
A standalone GameCube application can reliably exchange test traffic
with an automated host-side server.
```

## Phase 12 — Runtime stabilization and architecture

At this stage Open-GBP is expected to be a standalone open-source runtime
for the physical Game Boy Player.

Stabilize the architecture and public boundaries between:

- physical GBP/HSP transport;
- video, audio, input, and cartridge runtime;
- Link/SIO handling;
- networking;
- application-specific extensions.

Potential outputs include:

- the standalone Open-GBP application;
- a reusable GBP library;
- diagnostic applications;
- documentation;
- trace and research tools.

Integration with other frontends may be explored, but it is secondary to
the standalone Open-GBP runtime.

Game Boy Interface may continue to be used as a behavioral and
reverse-engineering reference. Open-GBP must not require GBI or another
proprietary runtime in order to operate.

Acceptance:

```text
Open-GBP has a stable standalone runtime and documented API boundaries
between GBP hardware transport, core runtime behavior, networking, and
application-specific extensions.
```

## Phase 13 — Mobile Adapter GB

Only after the previous GBP/SIO/network milestones are satisfied should Mobile Adapter integration begin.

The Mobile Adapter extension over the BBA is **additive**. It must not
break or replace: the physical Link Port; PicoAdapterGB; rumble and the
other GBP-aware game features; normal GB/GBC/GBA operation; behavior
compatible with the Start-up Disc / GBI.

Existing work from other projects/agents may then be consulted, including:

* PicoAdapterGB implementations;
* mGBA-related implementations;
* BGB/libmobile work;
* Mobile Adapter protocol documentation;
* existing libmobile code.

The preferred architecture is:

```text
physical cartridge
       ↓
real GBP serial interface
       ↓
Open-GBP SIO transport
       ↓
Mobile Adapter protocol layer
       ↓
nonblocking network backend
       ↓
GameCube BBA
```

The Mobile Adapter layer must remain separable from the GBP hardware layer.

Acceptance:

```text
A compatible real game running on the physical GBP communicates
through the GameCube as if a Mobile Adapter GB were attached,
while normal physical Link Port behavior remains available when
the feature is disabled.
```
