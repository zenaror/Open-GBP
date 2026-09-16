# poc/gbp-video-capture-probe — GBP-VIDEO-001

**Test ID:** `GBP-VIDEO-001` — **Build ID:** `video-0001` — **PHYSICALLY EXECUTED
2026-09-16** on the clean candidate commit `6930dde` (DOL SHA-256
`856d3e912626c5d0c686196e683bf4f398e9203ae9e835e0975e170ba760b5a6`; release audit of 2026-09-16,
PHYSICAL CANDIDATE READY). Result: `ok_video_sequence_capture`, `capture=target_reached`,
`restore=ok` — 209 cycles, 88 VIDEO and 144 AUDIO blocks, one complete 40-block frame-start
interval at 59.547 Hz. See "Result" below and `docs/research/HARDWARE_TESTS.md` "Executed tests —
GBP-VIDEO-001". Any later build of a modified tree is a new, unaudited artifact: a physical
candidate requires a clean commit, a clean rebuild, the audits below on that build, a recorded hash
and an explicit authorization.

**Question:** over a bounded sequence of delivered HSP causes serviced the reference way — read
the IRQ register, drain AUDIO if `0x0400`, drain VIDEO if `0x0100`, acknowledge `pending |
0x8000`, clean the PI, re-arm `IRQ := 0x0000`, observe the next cause — what is the physical VIDEO
block stream? On which blocks is each frame-start predicate true (GBI's and the Start-up Disc's,
separately), how many blocks lie between two consecutive true predicates, in which order do the
blocks arrive, at what intervals do the sources appear, and does the repeated service stay stable
(no reentry, no lost cause, no transport uncertainty)? Full design:
`docs/research/HARDWARE_TESTS.md` "Planned tests — GBP-VIDEO-001"; static basis:
`docs/research/VIDEO_PATH.md`.

**The content is never a gate.** The probe's status comes from SERVICE, CAPTURE and RESTORE only.
Comparing the captured blocks with the idle-screen frame both references embed happens **offline**,
in `tools/avseq.py oracle`, and only when the private inputs are present; without them the verdict
is `reference_content=unavailable`. Bytes that do not match are new evidence, never a failure.

## Result (2026-09-16, one physical run)

| Dimension | Value |
|---|---|
| SERVICE | ok — 209 cycles, 0 reentry, 0 unexpected source, 0 uncertain write, 0 DMA failure |
| CAPTURE | `target_reached` — 88 VIDEO, 144 AUDIO, 209 deliveries, next cause latched at the end |
| BOUNDARIES_GBI / _DISC | 3 each, positions 0, 25, 65, intervals 25 and 40, **0 divergences over 88 blocks** |
| COMPLETE_INTERVAL | yes for both predicates — one interval of exactly **40** blocks (seq25 → seq65) |
| REFERENCE_CONTENT | offline: matches both references exactly where they are white, differs exactly at their logotype blocks |
| RESTORE | ok — handler restored once, INTMR bit 13 = 0, AR_INFO `005b → 0043` |

Counters: 209 unmasks / 209 ISR entries / 209 ACK / 209 re-arms; W1C ISR 209,
main 0, teardown 1. `bulk_transfers=232`, `bulk_bytes=927744`. ISR latency 34
ticks median (0.84 µs). Log 1794 of 3000 ring lines, 0 dropped, 0 truncated.

Timing of that run: one frame = 680 138 ticks = 16.794 ms = **59.547 Hz**, made
of 39 block gaps of ~11 891 ticks (0.294 ms) and one closing gap of 216 079
ticks (5.335 ms) spanned by 22 consecutive AUDIO-only cycles.

Payload: exactly two semantic payloads over the 88 blocks — 960 × `0x7FFF`, and
`0xFFFF` + 959 × `0x7FFF` on the three frame starts. The complete frame is a
uniformly white 240 × 160 image under the references' geometry. Byte 0 differed
from byte 1 in 688 of 84 480 words (always `ff`/`7f`, never on the first word of
a 32-byte DMA line) without changing that payload.

**Known follow-up, not a defect of the run:** `finish()` computes the summaries
and formats the lean-cycle records **before** the hardware teardown, which added
64.99 ms between the last observation and the CONTROL restore. The teardown then
succeeded and the latched cause was closed normally. A future build should tear
the hardware down first and summarise afterwards.

## Provenance and rules

- **No fourth copy of the initialization, no new ISR.** The 003A stage
  (`src/gbp/gbp_initirqa_probe.c`) runs verbatim, PI masked, no handler, until INTSR bit 13 = 1.
  The handler is the **003B extended one-shot** (`hsp_backend_oneshot_isr_ext`, physically executed
  2026-09-15), installed **ONCE** after the first latched cause and restored once at the teardown;
  its two bodies are byte-identical to the GBP-AV-SERVICE-001 build's (pinned by
  `tests/host/test_isr_audit.py`). The delivery, the ACK/POSTACK step and the teardown hook are the
  shared 003B cycle service (`src/gbp/gbp_irq_service.{h,c}`); the drains are `src/gbp/gbp_avblock.c`;
  the teardown is the 003A one.
- **Record reuse instead of a second handler.** Between deliveries the shared one-shot record is
  reset through a new transport operation, `irq_record_reset` — **memory only**, never a PI
  register, and refused by the real backend while INTMR bit 13 is set. The reuse is safe because
  the ISR can run only between `__UnmaskIrq` and its own first `__MaskIrq`, and the main loop
  touches the record only after its own re-mask with INTMR bit 13 **read** as 0. No generation
  counter, no slot array (the 004 multi-cycle object is not linked).
- **Admission budget, not a wall-clock kill.** `MAX_RUNTIME_MS` (1000 ms) gates the **admission of
  new cycles**. A cycle whose CONFIRM held is **transactional**: READ → AUDIO → VIDEO → ACK →
  PICLEAN → REARM completes in full whatever the clock says, each step under its own bound, no
  retry. The deadline expiring between AUDIO and VIDEO changes nothing: VIDEO is drained, the ACK
  is `pending | 0x8000` for the **whole** pending value (never partial), the re-arm is written.
- **Caps** (operational, none a hardware property): 88 VIDEO blocks (the capture target and the
  array's capacity), 320 deliveries, `T_DELIVERY` 100 ms, `T_NEXT_CAUSE` 100 ms, `T_DMA` 200 ms,
  `T_FIRST_CAUSE` 2000 ms. The first four admitted cycles are **verify cycles** that take the full
  AVSVC snapshots; the rest run the lean path.
- **One snapshot decides the cycle.** The IRQ register is read once per cycle (Disc reading = GBI
  reading required); that value selects the blocks and is the value the ACK writes. A source that
  appears during a drain is observed, never added to the pass.
- **AUDIO before VIDEO**, the references' order, one whole-block DMA each into static 32-byte
  aligned buffers: `video_blocks[88][0xF00]` contiguous in sequence order (one slot per DMA, chosen
  after the bounds check, valid only after completion, never overwritten) and the AUDIO raw set
  (the first 8 successful drains plus a ping-pong pair for the last successful one — a failed drain
  lands in the other buffer and never overwrites the last valid capture). No malloc.
- **W1C budget per cycle:** handler 1, main ≤ 1 (PI clean), **none between the next cause and the
  next unmask**, teardown ≤ 1. The mock enforces the middle rule on every synthetic run.
- **Both predicates, per block, from the raw first four bytes**, never corrected:
  `gbi_frame_start := (u32 & 0x80800000) == 0x80800000` (bit 7 of bytes 0 **and** 1),
  `disc_frame_start := bit 7 of byte 1`. Neither is chosen as the truth; both lists are reported.
  **Byte 0 alone never decides anything.** The constant 40 is the references' hypothesis, never a
  gate: an interval N ≠ 40 is an important physical result, not a failure.
- **Failure policy:** unexpected source, cause without source, DMA busy/timeout/error, ACK or
  re-arm not completed, PI sticky after one W1C, reentry, missed entry, bad ISR state or capacity
  reached → the loop stops → bounded teardown → everything captured so far is saved. The caps, the
  admission deadline and an absent next cause are **not** failures.
- **Teardown on every path**, CPU masked first: CONTROL restore → IRQ read → stop word
  `read | 0x8AAA` → PI cleanup (≤ 1 W1C) → handler restore → INTMR bit 13 verified → AR_INFO →
  FINAL. **A console power cycle is mandatory** after any run that attempted a write.
- Not a runtime: no framebuffer, video conversion, frame sync, audio playback, KEYPAD, SIO, Link
  Port, BBA, Mobile Adapter, Game Pak logic, callbacks or unbounded loop.

## Result matrix

Every dimension is always reported; the main status never hides one.

| Dimension | Values |
|---|---|
| SERVICE | `ok` / `failed(<reason>)` |
| CAPTURE | `target_reached` / `delivery_cap` / `runtime_cap` / `no_next_cause` / `early_failure`, with counts and `next_cause_at_end` |
| BOUNDARIES_GBI / _DISC | count, positions, intervals |
| COMPLETE_INTERVAL | per predicate: yes iff two consecutive true predicates were captured |
| REFERENCE_CONTENT | computed **offline** by `tools/avseq.py oracle`, never by the probe |
| RESTORE | `ok` / `failed` |

Main statuses: `ok_video_sequence_capture`, `ok_target_not_reached_delivery_cap`,
`ok_target_not_reached_runtime_cap`, `observation_no_next_cause`,
`capture_completed_with_errors`, and the failure statuses (`anomaly_*`, `*_dma_*`,
`*_write_failed`, `abort_*`).

## Validation without hardware

- `tests/unit/test_gbp_video.c` — the state machine against the mock's synthetic models: one
  cycle, the capture target, 320 record reuses, alternating and combined sources, snapshot
  immutability, all eleven predicate cases, the seven admission-budget cases, the caps, the AUDIO
  ping-pong, every anomaly, the early aborts, the handler lifecycle, the sidecar of a real run,
  the raw buffers and the log capacity. **Every scenario is SYNTHETIC and never physical evidence.**
- **The physical GBP-AV-SERVICE-001 fixture is the exact prefix of cycle 0**: that run is one
  cycle of this loop, so with `max_deliveries = 1` it replays end to end — all 132 operations
  consumed in order, 0 mismatches, the physical blocks from its sidecar, the second cycle refused
  at the admission point and the latched cause acknowledged by the teardown.
- `tests/unit/test_gbp_avseq.c` — the records, buffers, predicates, boundaries and the `OGBPSEQ1`
  sidecar (round trip, bounds, every parse error).
- `tests/host/test_avseq.py`, `tests/host/test_video_replay.py` — the Python parser against the C
  writer, the offline oracle, and log → fixture → replay reproducing the same run.
- `make video-audit` — `tools/isr_audit.py` on both one-shot bodies (CLEAN, one INTSR store of
  0x2000 after the mask, no INTMR store) and `tools/poc_audit.py --profile video` on every object.
- `make video-dolphin` — both runs abort in the 003A stage (`abort_inconsistent` with no HSP
  device, `abort_control_shape` with Dolphin's GBPlayer model); neither reaches a CONTROL or IRQ
  write, the handler install, an unmask or a whole-block read. Preconditions are never weakened
  for Dolphin.

## Procedure (only after a clean commit, a clean rebuild, the audits and an authorization)

```text
Test ID:  GBP-VIDEO-001
Build ID: video-0001
DOL:      build/poc/gbp-video-capture-probe/gbp-video-capture-probe.dol
Cartridge / Game Pak: NONE
Physical Link Port:   empty (PicoAdapterGB disconnected)
BBA:      attached, no cable
Steps:
  1. Copy the DOL to the SD card, launch through Swiss, GBP attached, no Game Pak.
  2. Do not touch anything until the screen reports the status (<= 6 s worst case).
  3. Press X once (the log, then the sequence sidecar of about 0.4 MB), press START, power OFF.
Expected files: sd:/open-gbp/GBP-VIDEO-001_video-0001.log
                sd:/open-gbp/GBP-VIDEO-001_video-0001-seq.bin
Question answered: the physical VIDEO block sequence, both frame-start predicate lists, the
                   interval between consecutive boundaries, the source cadence, and whether the
                   repeated drained service stays stable over dozens of cycles.
```

A power cycle after the run is **mandatory**: the run writes the CONTROL transform and the IRQ
register (A1, A2, one ACK and one re-arm per cycle, the stop word).
