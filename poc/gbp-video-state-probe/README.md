# poc/gbp-video-state-probe — GBP-VIDEO-002

**Test ID:** `GBP-VIDEO-002` — **Build ID:** `vstate-0004` — **PHYSICALLY EXECUTED 2026-09-17
(commit `b017e38`); PHYSICAL VALIDATION PASSED.** This probe has now run on hardware four times:
`vstate-0001` (2026-09-16, aborted on a semantic disagreement of the IRQ window), `vstate-0002`
(2026-09-17, the same abort with the bytes preserved), `vstate-0003` (2026-09-17, 120 s target
reached, 23 disagreements survived, diagnostics contaminated by a producer defect) and
`vstate-0004` (2026-09-17, 120 s target reached, **29 disagreements survived with correct
per-cycle attribution**, sidecar strict-valid as OGBPSEQ1 v5 — GBP-HW-108…115).

Every future physical candidate still requires a clean commit, a clean rebuild, the audits below
on that build, a recorded hash and an explicit authorization (`docs/research/HARDWARE_TESTS.md`,
CLAUDE.md §18). A `-dirty` build is never a candidate.

**Question:** over an observation at least as long as the nominal interval the Start-up Disc's own
detector spans, in a session **without a Game Pak**, does the VIDEO stream ever carry a frame other
than the uniform one — and if so when, for how long and with what content? GBP-VIDEO-001 saw only
39.2 ms of VIDEO, starting 107 ms after the CONTROL transform, and every block was uniform. The
Disc keeps its detector armed for a nominal 120 s (24 000 invocations of a 5.000 ms periodic
callback; 120 s is a **lower** bound because the scheduler drops missed periods). Answers
U-GBP-031, and gives U-GBP-030 a run whose cadence is uniform from the first useful frame. Full
design: `docs/research/HARDWARE_TESTS.md` "GBP-VIDEO-002"; static basis:
`docs/research/VIDEO_PATH.md` §9.

**The content is never a gate, and the runtime has no oracle.** The probe's result comes from
SERVICE, the frame capture, the baseline, the episode counts and RESTORE. It holds no reference
table, checksum, pixel or block range. Comparing an episode with the Start-up Disc's embedded frame
and GBI's two tables happens **offline**, in `tools/vstate.py oracle`, and only when the private
inputs are present; without them the verdict is `reference_content=unavailable`. Bytes that do not
match are new evidence, never a failure.

## What it does

```text
003A verbatim (PI masked, no handler) -> first latched cause -> IRQ_Request(26, 003B ext) ONCE
  [ CHECK_ADMISSION -> PREPARE (record reset, memory only) -> UNMASK x1 -> CONFIRM
    -> READ -> AUDIO 0x1000 -> VIDEO 0xF00 -> ACK pending|0x8000 -> PI clean
    -> per-block signature + frame assembly -> REARM IRQ := 0x0000 -> WAIT_NEXT (masked) ]*
  -> STOP -> minimal RAM snapshot -> HARDWARE TEARDOWN -> only then summaries and the save
```

Roughly 639 000 deliveries are expected over the window, so there is **no per-delivery record**.
The evidence is one vector of 40 semantic signatures per observed frame, a bounded event store, and
detailed cycle records only for the first eight cycles, the last eight, anomalies and the cycles
inside a preserved episode.

## Reuse: the interrupt path is not redesigned

Everything GBP-VIDEO-001 validated physically is reused unchanged and stays a requirement: the 003A
sequence, the 003B extended one-shot handler installed **once** (its two bodies are proven
**byte-identical** to the GBP-VIDEO-001 build's by `make vstate-audit`), the memory-only record
reset between deliveries, the quiet delivery, the whole-block drains, the ACK of the **whole**
pending value, the PI cleanup budget (ISR 1, main ≤ 1, none between the next cause and the next
unmask, teardown ≤ 1), the re-arm, the masked WAIT_NEXT and the 003A teardown with its handler
restore. **Any change to the ISR is a blocker for review.**

## What is new, and only this

| | |
|---|---|
| **64-bit time base** | 2^32 ticks = 106.049 s at 40.5 MHz, shorter than the 120 s target, so every persistent timestamp comes from the transport's `ticks64`. Short per-operation waits keep the 32-bit one. |
| **Per-frame evidence** | 16 384 frames x 192 B = 3.00 MiB of signature vectors instead of per-delivery records. |
| **State detection without an oracle** | a learned baseline, then an episode state machine over signature changes. |
| **Teardown first** | GBP-VIDEO-001 summarised before tearing down and left 64.99 ms between the last observation and the CONTROL restore. Corrected here: between the stop decision and the first teardown write the probe performs only scalar assignments, two time-base reads and two fixed-size event records, and formats **nothing at all**. |

The safety epoch deserves its own note, because it is the one value the probe cannot read directly.
The 003A stage records the CONTROL transform on the 32-bit time base, so the u64 epoch is
reconstructed — and then **checked**, not trusted: two real u64 reads bracket the stage and the
reconstruction must land between them, falling back to the earlier end, which over-counts the
safety budget rather than under-counting it. The window is independently bounded at 12 block
transfers with no polling loop, a 2.4 s worst case against the 106.049 s at which a 32-bit
difference could become ambiguous. When no CONTROL write happened at all, no epoch is invented:
the field carries the probe's own start and `epoch_ok` reads -1.

## The stop condition, in strict precedence

Evaluated once per admitted cycle, at the admission point, and **never inside an accepted
transaction** — which is what guarantees a cap can never produce a partial ACK or an unwritten
re-arm.

1. fatal service error → `failure`
2. `HARD_WALLCLOCK_LIMIT` expired → `safety_budget`. **Wins over an open episode and over the
   finalisation tail:** a cap that could be extended by 60 more frames would not be hard.
3. frame store full / event store full → `frame_store_cap` / `event_store_cap`
4. `baseline_valid` and `valid_observation_elapsed >= MIN_VALID_OBSERVATION` → `nominal_negative`,
   with a bounded finalisation tail first when an episode is open
5. no next cause within `T_NEXT_CAUSE` → `no_next_cause`
6. delivery guard reached → `delivery_cap`

**There is no early positive stop.** The runtime cannot know which stable changed state is the one
the experiment was built for — baseline, then an intermediate screen, then the expected one twenty
frames later is a concrete failure mode — so it observes the whole window and records every episode
for offline classification.

**The episode raw store filling is NOT a stop.** It sets `episode_store_full`, counts
`episodes_not_preserved`, keeps the signature monitor running and never overwrites an earlier
episode. That is a different condition from the two store caps, with different counters and a
different code path.

## Constants (operational; none is a property of the device)

```text
MIN_VALID_OBSERVATION      120 s, accumulated AFTER baseline_valid, on interpretable frames only
HARD_WALLCLOCK_LIMIT       180 s = 7 290 000 000 ticks, counted from the CONTROL transform
                           (the value does not fit in 32 bits: an independent proof of the u64 base)
MAX_FRAMES 16384 · MAX_EVENTS 4096 · MAX_EPISODES 4 · EPISODE_MAX_FRAMES 60 · N_STABLE 3
MAX_DELIVERIES 2 000 000 (a u32 guard) · T_DELIVERY 100 ms · T_NEXT_CAUSE 100 ms · T_DMA 200 ms
VERIFY_CYCLES 4 · raw working ring 3 x 48 x 0xF00 · episode raw 4 x 4 x 48 x 0xF00
```

40 blocks per frame is **never assumed**: a frame is `complete_40` only when two **observed**
boundaries really delimited 40 VIDEO blocks. An interval of any other length is a measurement,
recorded in the histogram, never a failure and never corrected by a synthesised boundary.

## The signature

GBI's own per-block checksum, applied to **our** bytes: for each group of four raw bytes it
consumes **byte 1 and byte 3** and nothing else, packs two pixels into a 32-bit word, accumulates
240 pairs in 64 bits and stores the low 32 bits plus the carry count. Bytes 0 and 2 are never read,
so the 688 byte-0 exceptions GBP-HW-070 measured **cannot** produce a false positive — a property
of the algorithm, not a tuning choice. The frame-start bit lives in byte 1, so it is inside the
checksum by construction and is seen consistently at the same block position on both sides of any
comparison. The host tests reproduce the physically anchored values `0xFF0FFF0F` (no flag) and
`0x7F0FFF10` (with it).

Its cost is **measured, not thresholded**: min, median, p95 and max from a bounded 1 KiB histogram
with one exact bucket per tick in the expected range. The design's earlier "p95 below 25 % of the
median lean cycle" had no physical basis and was withdrawn; what is required before any physical
candidate is the measurement plus a with/without cadence comparison, examined by a reviewer.

## Memory (measured on this build)

```text
text + data                                              0.41 MiB
frame signatures  16384 x 192                            3.00 MiB
episode raw       4 x 4 x 48 x 0xF00                     2.81 MiB
raw working ring  3 x 48 x 0xF00                         0.53 MiB
event store       4096 x 64                              0.25 MiB
   evidence stores subtotal                              6.60 MiB
log ring          1024 x 256                             0.25 MiB
sidecar chunk (only after the teardown)                  0.06 MiB
AUDIO raw, cycle records, state                          0.02 MiB
   every static of the probe                             6.93 MiB
                                                        ---------
image ends at 0x8078D038, MEM1 headroom                 16.449 MiB
```

Zero overlaps, every DMA target 32-byte aligned, nothing large on the stack, and the sidecar — about
1.4 MiB in the synthetic runs and several MiB on hardware — **never exists as a second full copy**:
it is streamed in 64 KiB chunks with a running CRC-32, after the teardown. The only static objects
above 1 MB are the frame store and the episode raw store.

The log does not grow with the run either: measured at 200, 2 000, 20 000 and 200 000 deliveries,
the ring holds **214 lines at the moment of the teardown in every one of them**, and 293 once the
report is written, with none dropped.

## Validation without hardware

- `tests/unit/test_gbp_vsig.c` — the signature against its physical anchor, the byte-0 property,
  both predicates exhaustively over 65 536 byte pairs, the cost histogram, and the 64-bit time base
  across the low-word wrap `0xFFFFFFFF -> 0x00000000`.
- `tests/unit/test_gbp_vstate.c` — the assembler (complete_40, incomplete short and long, resync,
  disagreement, intervals), the baseline, the early candidate, the episode state machine, the three
  cap behaviours, the tail, the safety cap, the AUDIO policy and the exact memory arithmetic.
- `tests/unit/test_gbp_video_state.c` — the probe against the mock, including the **full nominal
  scan**: about 800 000 deliveries, 399 000 VIDEO blocks, 9 983 frames, 120.0 s of valid
  observation, a run that crosses the 32-bit tick boundary, and no counter overflow.
- `tests/host/test_vstate.py` — `tools/vstate.py` against the sidecar the C writer produced, the
  strict parser's rejections, and the proof that format 1 and format 2 can never misread each other.
- `make vstate-audit` — both one-shot bodies (CLEAN, 82 instructions, one INTSR store of 0x2000
  after the mask, no INTMR store) and **byte-identical** to the GBP-VIDEO-001 build's, plus
  `tools/poc_audit.py --profile vstate` on every object: one `__UnmaskIrq` site, `IRQ_Request` only
  from the install/restore pair, 3 + 1 + 3 IRQ-register write sites, the 64-bit base only through
  `gettime()`, and **no filesystem reference anywhere in the capture path**.
- `make vstate-dolphin` — both runs abort in the 003A stage (`abort_inconsistent` with no HSP
  device, `abort_control_shape` with Dolphin's GBPlayer model); neither reaches a CONTROL or IRQ
  write, the handler install, an unmask or a whole-block read, so the long scan is never entered.
  Preconditions are never weakened for Dolphin, and Dolphin's timing is never treated as physical.

Every mock scenario is SYNTHETIC and none of it is physical evidence.

## Procedure (only after a clean commit, a clean rebuild, the audits and an authorization)

```text
Test ID:  GBP-VIDEO-002
Build ID: vstate-0004          (the identity the build embeds; check build-info.txt)
DOL:      build/poc/gbp-video-state-probe/gbp-video-state-probe.dol
Cartridge / Game Pak: NONE
Physical Link Port:   empty (PicoAdapterGB disconnected)
BBA:      attached, no cable
Steps:
  1. Copy the DOL to the SD card, launch through Swiss, GBP attached, no Game Pak.
  2. Do not touch anything until the screen reports the status. EXPECT TWO TO FIVE MINUTES.
  3. Press X once (the log, then the streamed sidecar of several MB), press START, power OFF.
Expected files: sd:/open-gbp/GBP-VIDEO-002_<BuildID>.log
                sd:/open-gbp/GBP-VIDEO-002_<BuildID>-vstate.bin
                (the probe names them from its own Build ID: the 2026-09-17 run
                 wrote GBP-VIDEO-002_vstate-0004.log and …-vstate.bin)
Question answered: whether a structured VIDEO state other than the uniform one ever reaches the
                   stream without a Game Pak, over at least 120 s of valid post-baseline
                   observation, and if so when, for how long and with what signature.
```

A power cycle after the run is **mandatory**: the run writes the CONTROL transform and the IRQ
register (A1, A2, one ACK and one re-arm per cycle, the stop word).

`hardware_result` and `save_result` are separate. A card failure after a successful teardown cannot
invalidate the result held in RAM, the screen says whether the sidecar is complete, partial or
failed, and there is never an automatic re-run: the hardware state after a run is not the state a
fresh run starts from.
