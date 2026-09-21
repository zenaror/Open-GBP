# Phase 4 — assessment against its acceptance criterion (2026-09-21, GitHub Issue #17)

Status of this document: **assessment**. It is not evidence and it creates
none: every statement below cites the evidence id that carries it
(`EVIDENCE.md`, `UNKNOWNS.md`), keeps the status that source gives it, and
the verdict is a reading of that evidence against the criterion
`docs/ROADMAP.md` Phase 4 wrote before any of it existed. No run is
re-judged, no status is promoted, no id is minted. The verdict is stated once
here, once in `ROADMAP.md` and once in `HANDOFF.md`, in the same words.

## 1. The criterion, and how it is read

Quoted from `docs/ROADMAP.md` Phase 4:

> A real cartridge running on the physical GBP produces stable, correct video
> through the open-source runtime.

Four terms, assessed one by one: **real cartridge**, **stable**, **correct
video**, **through the open-source runtime**. For each: the physical evidence
that supports it, by id and status; what that evidence does not reach; and
the phase that owns what is missing. The criterion is not rewritten, widened
or narrowed; where a term admits more than one reading, both readings are
assessed and the verdict is drawn under the stricter one.

Vocabulary of the runs (all in `HARDWARE_TESTS.md`): `stream-0003` and
`stream-0004` are the two retail-cartridge smokes of 2026-09-18/19
(§V5.34, §V5.38); runs 1–13 are the numbered indexed and coordinate runs of
`stream-0005` … `stream-0013` (§V5.41–§V5.58, §V6.19–§V6.25); run 8 is the
retail-cartridge run of GBP-VIDEO-005 (§V5.54). The controlled stimuli are
`indexed-0003` (OGBPIDX1, runs 4–11), `coord-0001` (RUN 12) and `coord-0002`
(RUN 13); the "witness" is the frozen OGBPIDX1 strip that only a controlled
stimulus can carry.

## 2. Term by term

### 2.1 "A real cartridge"

**Supports it.** A retail cartridge has run through the runtime on the
physical Game Boy Player three times, on the same console and GBP as every
other run:

- `stream-0003` (GBP-HW-138…145): the service path conserved 280 621 cycles
  with the consumer, the converter and the GX display attached; 2 298 frames
  published, converted and submitted; 105 841 VIDEO transfers completed
  (FACT); the operator saw the actual cartridge game, looking normal, small
  and centred by design, with two photographs preserved (GBP-HW-144:
  FACT for the log, OPERATOR OBSERVATION for the picture). The run also found
  two software defects, P1 and P2 (GBP-HW-145).
- `stream-0004` (GBP-HW-146…152): P1 and P2 physically confirmed fixed;
  2 622 frames published from the same 2 635 complete source frames;
  publication cadence back to the source closure rate in that run
  (GBP-HW-148, a measurement of one run); the operator saw no visible change
  from `stream-0003` (GBP-HW-152, OPERATOR OBSERVATION).
- run 8, GBP-VIDEO-005 (GBP-HW-223…230): the NORMAL startup on retail content
  — no synthetic hand-off, no wait, first real hand-off 164.696 ms after the
  CONTROL transform (GBP-HW-224, FACT); transport balanced at 240 754 with
  zero timeouts, busy or errors, and Policy A clean on retail content — 2 244
  hand-offs in strict order, 0 interior drops, depth 1, p99 0.3341 ms, max
  1.0030 ms, 7 display repeats beside 0 drops over the frozen join (GBP-HW-225,
  FACT); the structural startup transient identical to the indexed run and to
  the no-cartridge run (GBP-HW-226, FACT); the operator saw the boot logo
  appear complete, a clean transition and a stable game (GBP-HW-227, OPERATOR
  OBSERVATION); "NORMAL startup exposes the real cartridge startup sequence to
  the user" (GBP-HW-229, CORROBORATED, GBP-VIDEO-005 PASS with a debug-UX
  note).

**Does not reach.** No OGBPIDX verdict exists for retail content and none may
be written: the retail witness was validated as a container only, and no strip
was decoded (GBP-HW-225, GBP-HW-230). No oracle-based check of colour,
geometry or full-frame fidelity exists on retail content, because a retail
picture has no independent oracle; no scanout binding (CLAIM-D) exists for
retail content, because it needs known digits. One retail title, three runs,
each about 44 s of streaming; no GB/GBC-mode cartridge has been run (Phase 7
distinguishes the two families explicitly). The media double check for run 8
is PENDING (GBP-HW-223).

### 2.2 "stable"

Read as: the video path neither loses source frames nor faults, within bounded
latency, for as long as it has been observed. Three layers, each measured
separately and kept separate by the evidence:

**Transport and service.** Zero timeouts, busy refusals, uncertain writes or
transport errors in every run that streamed video: 209 cycles (GBP-HW-062),
51 751 cycles in 8.2 s (GBP-HW-074), 1 114 007 and 1 114 005 cycles over
175.848 s twice, without a cartridge and without presentation (GBP-HW-099,
GBP-HW-109), 1 108 063 transactions after a 5 s masked pause (GBP-HW-117),
280 621 and 280 672 cycles with the consumer, converter and GX display attached
on a retail cartridge (GBP-HW-138, GBP-HW-150), 240 754 on run 8 (GBP-HW-225),
and 254 8xx on each of runs 9–13 (GBP-HW-236, 241, 247, 253, 259) — all FACT.
The semantic-disagreement policy of the IRQ window survived 23, 29 and 42
events in three workloads, including a retail game repainting continuously
(GBP-HW-100, 110: FACT; GBP-HW-142: CORROBORATED); its mechanism stays
UNKNOWN (U-GBP-033).

**Source-frame continuity.** Within a prospectively qualified 2 048-record
window the frozen `tools/vindex.py` returned `OBSERVED_CONTIGUOUS` on runs 4,
5, 6, 9, 10, 11 and 13 (GBP-HW-188/189, 193, 203, 232, 240, 246, 257: FACT),
and on run 7 with its composition — 1 988 intact, 60 invalid strips, the
window having opened before the stimulus (GBP-HW-218…221: FACT). The one
`OBSERVED_DISCONTINUITY` among the indexed runs with a qualified window, RUN 12,
is the stimulus's own scheduling — two PREPARE-side missed VBlanks of
`coord-0001` — resolved from a cycle model of its exact image (GBP-HW-251;
GBP-VID-034, mechanism RESOLVED, CORROBORATED) and absent in RUN 13 with
`coord-0002` (GBP-HW-257: FACT). Each verdict is scoped to its window: it says
nothing about frames before or after it, about arbitrary durations, or about
other content (GBP-HW-189, GBP-HW-212).

**Presentation, Policy A.** Two framebuffers with asynchronous deferral: every
interior source frame the consumer was offered reached a framebuffer, in order,
with the deferral queue never deeper than one, and a hand-off latency of p99
≤ 0.4946 ms and max ≤ 1.1353 ms against the pre-registered gates of 1.0 / 2.5
ms — on runs 6, 7, 8 (retail), 9, 10, 11, 12 and 13 (GBP-HW-205…211, 217, 225,
236, 241, 247, 253, 259: FACT). The seven repeated display intervals per
≈ 34 s window are what the source (59.727 Hz) into the VI (59.940 Hz) rate
difference requires, and they are not lost frames (GBP-HW-210, 211: FACT;
GBP-VID-020: FACT, software; GBP-PHY-003: FACT, the board does not
synchronise).

**Startup.** The NORMAL profile hands the first real frame to the video
interface 164.7–165.2 ms after the CONTROL transform, with no synthetic frame
shown and no wait, on eight runs and two cartridges (GBP-HW-215, 224, 235,
241, 247, 253, 259: FACT). The AGB's own boot animation begins about half a
second after the AGB is started and settles about three seconds later
(GBP-HW-079/080: FACT, no cartridge), and the first ≈ 3.4 s of structured
startup is the same on two cartridges and no cartridge (GBP-HW-226: FACT).

**Does not reach.** The longest continuous streaming observation with a
cartridge and presentation is ≈ 44 s (GBP-HW-138…151) and the qualified
windows are ≈ 34 s; the 175 s runs had no consumer and no display. Nothing is
established for minutes or hours, for thermal drift, for other consoles or
other Game Boy Players, or for other titles. The consumer slice position is
measured (28–41 µs, ≈ 25 % of pump calls yielding to a pending cause) and has
caused no observable transport failure in eight runs, but its timing margin has
never been measured (GBP-HW-140, 150; HANDOFF "slice position"). The
incomplete frame intervals of the startup region (30/34/38 blocks) are a
startup-region signature that predates streaming; whether blocks were lost,
boundaries observed early or late, or causes coalesced is UNKNOWN (GBP-HW-141:
CORROBORATED; U-GBP-030).

### 2.3 "correct video"

Read as: what the runtime shows is the picture the cartridge rendered, in
geometry and in colour, and it reaches the screen. Measured where an oracle
exists; observed where none can.

**Geometry and frame composition (FACT).** 0xF00 bytes per VIDEO IRQ = 4
raster lines × 240 pixels × 4 bytes, 40 blocks per 160-line frame, blocks in
ascending order from the frame marker: reconstructing the preserved raw frames
this way produced a legible, animated GAME BOY logotype at 240 × 160
(GBP-HW-081). 477 of 489 frame intervals were exactly 40 blocks (GBP-HW-076);
both references' frame-start predicates agreed on all 19 601 blocks measured
(GBP-HW-066, 077). The references' model of the same geometry is
CORROBORATED static analysis (GBP-VID-002) and the hardware confirmed it.

**Pixel word (FACT for what is consumed; UNKNOWN for what is not).** Both
references consume bytes 1 and 3 of each 32-bit word (GBP-VID-003, F (code)),
and every physical frame is consistent with it: bytes 1 and 3 identical across
certified frames of one run and across two runs (38 400 of 38 400 words,
GBP-HW-132), while bytes 0 and 2 vary between consumed-identical frames
(GBP-HW-126, 133: FACT) — meaning UNKNOWN (U-GBP-029). Bit 15 is set on
exactly one word per frame, at (0, 0), and is added on the path, not the
AGB's colour value (GBP-HW-129: FACT); what sets it is UNKNOWN (U-GBP-034).

**Colour (FACT, with a stated limit).** The window exchanges the two outer
5-bit groups relative to the AGB framebuffer, so under the reading both
reference decoders implement (bit 15 flag, 14–10 R, 9–5 G, 4–0 B) the displayed
colour is the AGB's intended colour: `CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP`
under a contract pre-registered before the run, exactly one of seven candidate
transformations reproducing all eight known values, corroborated by a second
run (GBP-HW-130, 131, 132; U-GBP-011 CLOSED). Limit, recorded before the run:
a permutation fixing bits 0, 5 and 10 and each group as a set while rearranging
only bits 1–4 inside a group is not excluded (GBP-HW-131, §V3.19).

**Full-frame fidelity, source → converted texture (FACT, eight frames).** RUN
13: eight prospectively sampled frames, every one 40/40 coherent blocks, all
38 400 consumed words equal to the injective OGBPCOORD1 oracle, the preserved
texture equal to the Python conversion, the host-built `gbp_vpix.c`
conversion and the tiled oracle — GBP-VIDEO-008 = PASS, CLAIM-A / CLAIM-B for
those eight frames only (GBP-HW-258). RUN 12's 8/8 is the same dependent
variable on an inadmissible run and stays subordinate evidence (GBP-HW-252).

**Physical scanout (FACT for the chain, OPERATOR OBSERVATION for the eye).**
RUN 13: every hand-over of the four appearance sets was latched by the video
interface with register-consistent read-backs (L = 40/40/39/40, 2371/2371),
and the operator saw the digits 1, 2, 3, 4 in order through the declared
composite → RCA-to-HDMI converter → HYDIS HV150UX2 chain — GBP-VIDEO-007 =
PASS, CLAIM-D only: at least one source-derived frame of each qualifying
appearance was physically visible; a digit is bound to a 40-frame set, never to
one frame (GBP-HW-260, GBP-HW-256).

**Retail content (OPERATOR OBSERVATION, beside a content-blind path).** The
same runtime path showed a retail game that looked normal on three runs
(GBP-HW-144, 152, 227) with the same machine-side metrics as the controlled
runs (GBP-HW-224…226).

**Does not reach.** Physical pixel equality on any display; per-frame scanout
accounting; fidelity of frames not sampled; tearing; presentation, scaling and
the pixel-perfect requirement (GBP-VID-032, a Phase 9 design requirement, nothing
implemented); anything about the converter, the panel, the future Morph 2K or
Samsung Q80T topologies (GBP-HW-256, 260 non-claims); the intra-group
permutation limit of the colour result; colour, geometry or fidelity of retail
content by measurement.

### 2.4 "through the open-source runtime"

**Supports it (FACT).** Every physical run of this project executed a DOL built
from the repository source in the project's own toolchain — the Docker image,
devkitPPC and libogc2 — with the build identity embedded, recorded and
verified before and after each run (ENV-HW-001; GBP-HW-138, 180, 192, 202,
213, 223, 231, 239, 244, 250, 256). The video path is the repository's:
whole-block DMA service and re-arm (GBP-HW-050…055), the GX `GX_TF_RGB5A3`
texture path with the draw-done ownership machine (GBP-HW-134, 139, 149), the
two-framebuffer Policy A (GBP-VID-022, 024, 025 in software; GBP-HW-205…211
physically), and the NORMAL startup profile (GBP-VID-028; GBP-HW-214). The
Start-up Disc and Game Boy Interface were used as static references only
(`VIDEO_PATH.md`, `CLAUDE.md` §6); no proprietary code runs in any DOL and the
runtime depends on no proprietary runtime.

**Does not reach.** The runtime is a research probe with a debug console, a
witness store and no user interface (GBP-HW-228, GBP-HW-229 "final production
UX is not claimed"); "open-source runtime" is satisfied by provenance, not by
completeness — GBI-class functionality is Phase 9.

## 3. The asymmetry, stated

Continuity, Policy A over the frozen join, full-frame fidelity and scanout were
measured on controlled synthetic stimuli — `indexed-0003`, `coord-0001`,
`coord-0002` — because each measurement needs something a retail cartridge
cannot supply: an embedded frame index for the witness, an injective oracle for
the pixels, known digits for the eye. On retail content the project holds
three machine-side runs with the same transport, startup and Policy A metrics
as the controlled runs (GBP-HW-138…151, 224…226) and three operator
observations (GBP-HW-144, 152, 227), and nothing measured against an oracle.

The bridge between the two is an inference: the runtime path is content-blind
by construction — it recognises no expected answer at run time, the witness
retention is a research layer at the SOURCE that never qualifies on retail
content and touches nothing downstream, and the conversion, presentation and
service code is byte-identical between the controlled and the retail runs of
the same build — so what the controlled runs established about the path
transfers to retail content to the extent that the path is the same. That
inference is CORROBORATED (by the identical machine-side metrics on retail
content and by the operator's observations), and it is not FACT: no physical
measurement shows a retail pixel to be the cartridge's pixel.

Does the gap block the criterion? The criterion asks that a real cartridge
produce stable, correct video through the runtime. It does not ask that the
correctness be measured on the retail content itself, and the project's own
method cannot produce such a measurement without an oracle it does not have.
What the evidence establishes is: a retail cartridge did run, stably by the
machine-side FACTs, through a path whose correctness is FACT on controlled
content, with a human observation of a correct-looking picture on every retail
run. What it does not establish is a FACT-level pixel or colour claim on retail
content. Under the stricter reading the criterion would be NOT SATISFIED until
a retail-content measurement exists; under the reading the ROADMAP's own
Phase 7 implies — representative cartridges are exercised there, with a
compatibility matrix — the retail-content measurement is Phase 7's to design,
and Phase 4's job was the path. The assessment takes the second reading and
names the first as the residual that owns it, because the ROADMAP places
cartridge validation in Phase 7 explicitly and because nothing in Phase 4's
evidence contradicts the inference.

## 4. Verdict

```text
PHASE 4 VERDICT: SATISFIED WITH NAMED RESIDUALS
```

Phase 4's criterion is satisfied for the video path as a path: a real cartridge
ran on the physical Game Boy Player through the open-source runtime with the
transport, the startup and the presentation policy measured clean on retail
content, and the correctness of that path — geometry, colour, full-frame
source → texture fidelity and physical scanout — is FACT on controlled stimuli
within the boundaries each run pre-registered. The residuals below are what the
verdict does not cover; each names the phase that owns it or says that nothing
schedules it.

## 5. Named residuals and their owners

| # | residual | strongest evidence today | owner |
| --- | --- | --- | --- |
| R1 | Correctness on **retail content by measurement**: no oracle-based colour, geometry or fidelity check exists on a retail picture; the claim rests on the content-blind path plus operator observation (CORROBORATED, never FACT) | GBP-HW-144, 152, 224…229 | **Phase 7** (representative cartridges, the compatibility matrix); a retail-content check against a reference rendering would be designed there |
| R2 | **Presentation, scaling, aspect, filtering** and the pixel-perfect requirement; the picture is native 240 × 160, centred, unfiltered by design | GBP-VID-032; GBP-HW-144 | **Phase 9** (GBI-class parity), where the requirement is written; not started, and not authorised by Phase 4's closure |
| R3 | **Physical pixel equality** on any display and **per-frame scanout accounting**; CLAIM-D binds a digit to a 40-frame set and RUN 13's chain latches hand-overs, not pixels | GBP-HW-256, 260 (non-claims) | **not scheduled** — established by nothing; a capture device on the video output would be the instrument |
| R4 | **Duration and breadth of stability**: ≈ 44 s with presentation, ≈ 34 s qualified windows, one console, one GBP, one retail title; the consumer slice's timing margin unmeasured | GBP-HW-138…151, 189, 212; HANDOFF "slice position" | **Phase 12** (runtime stabilization) for duration and margin; **Phase 7** for titles and the GB/GBC family |
| R5 | The colour result's **intra-group limit**: a permutation of bits 1–4 inside a 5-bit group is not excluded | GBP-HW-131, `HARDWARE_TESTS.md` §V3.19 | **not scheduled**; §V3.19 records the stimulus pattern that would close it |
| R6 | **Bytes 0 and 2** of the pixel word (data or read-path artifact) and the **origin of bit 15** | U-GBP-029, U-GBP-034; GBP-HW-126, 129, 133 | **Phase 4 research residuals**, open in `UNKNOWNS.md`, non-blocking; the runtime consumes neither |
| R7 | **Startup-region incomplete intervals** (30/34/38 blocks) — a startup signature whose mechanism is unknown | GBP-HW-141, 216, 226; U-GBP-030 | **not scheduled**, non-blocking; recorded, never called source loss |
| R8 | **Rate conversion**: ≈ 7 repeated display intervals per 34 s are inherent to 59.727 Hz into 59.940 Hz with no synchronisation; any latency/timing change is a presentation policy | GBP-PHY-003; GBP-HW-210, 211; GBP-VID-020 | **Phase 9** (timing and latency improvements); nothing to fix in Phase 4 |
| R9 | **Audio** and **input** — named by the ROADMAP's Phase 4 status as not established; not part of this criterion | U-GBP-012; `INITIALIZATION.md` §14 (KEYPAD never written) | **Phase 6** (audio), **Phase 5** (input) |
| R10 | **Ethernet-connected or BBA-initialised topologies**; BBA-present / Ethernet-disconnected is a paired control only | GBP-HW-242, 243 | **Phase 11** |
| R11 | **Production UX**: the debug console flash, the research witness and the absence of any menu | GBP-HW-228, 229 | **Phase 9** and **Phase 12** |

## 6. What this assessment does not do

It does not re-judge any run: RUN 12 remains GBP-VIDEO-007 INCONCLUSIVE /
GBP-VIDEO-008 INCONCLUSIVE, `color-0001` remains INCONCLUSIVE, run 3 remains
`OBSERVED_DISCONTINUITY`, and RUN 13's two PASS verdicts keep their exact
boundaries. It promotes no evidence status and mints no id. It closes no
unknown: U-GBP-008, 014, 029, 030, 031, 033 and 034 were checked against the
conditions each set for itself, and none is met — U-GBP-008 still carries the
AUDIO layout, U-GBP-014 the request period, U-GBP-030 its four undistinguished
candidates, U-GBP-031 the AGB state behind table B — so they stay open.
It authorises nothing: no Phase 9 work, no run, no build. What information the
evidence supports in a consolidated form has been promoted into
`docs/protocol/VIDEO.md` and the video rows of `docs/hardware/` and
`docs/protocol/REGISTERS.md`, each sentence with its id, by the chain
`RESEARCH_METHOD.md` "Documentation promotion" prescribes.
