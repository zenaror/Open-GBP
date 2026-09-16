# poc/gbp-init-irq-service-probe — GBP-INIT-004

**Test ID:** `GBP-INIT-004` — **Build ID:** `initirq4-0001` — **IMPLEMENTED, NOT PHYSICALLY
EXECUTED.** The current build is a **DIRTY BUILD — NOT A PHYSICAL CANDIDATE**: it was produced
from an uncommitted tree for review only. A physical candidate requires the user's checkpoint,
a clean rebuild, the release-candidate audit and an explicit authorization
(`docs/research/HARDWARE_TESTS.md` "Planned tests — GBP-INIT-004"). No hardware run is requested.

**Question:** after a real HSP cause has been delivered and serviced as in GBP-INIT-003B
(physically executed 2026-09-15: latched cause → IRQ 26 → handler mask + one PI W1C → device
ACK `IRQ := read | 0x8000`), does GBI's end-of-pass write `IRQ := 0x0000` (the re-arm,
GBP-IRQ-004) let the GBS-DOL raise the **next** cause, and does the **same installed handler**
service it again — three cycles, two re-arms — without a storm, without a lost cause, with
every boundary observed and no acknowledge that was not derived from a read? How long after
the re-arm does the next cause arrive? Every outcome is a valid observation. Full design:
`docs/research/HARDWARE_TESTS.md` "Planned tests — GBP-INIT-004"; implementation record:
`docs/research/DEVLOG.md` 2026-09-15 "GBP-INIT-004 implemented".

## Provenance and rules

- **No third copy of the sequence.** The 003A stage (`src/gbp/gbp_initirqa_probe.c`, stage
  API) runs verbatim, PI masked, no handler, until INTSR bit 13 = 1 (EVENT). The per-cycle
  service is `src/gbp/gbp_irq_service.{h,c}`, extracted verbatim from the executed 003B probe
  (unmask → delivery → re-mask → record; PREACK → ACK → POSTACK → the cycle's single main W1C;
  the teardown hook); the 003B probe now calls the same functions and its physical fixture pins
  every record byte for byte. The handler body is the unchanged 003B extended one-shot
  (`gbp_irq_oneshot_service_ext`) behind the generation wrapper `gbp_irq_multicycle_service`
  (`src/gbp/gbp_irq_oneshot.h`): the slot index published by the main loop selects a
  write-once record slot; a generation out of range is counted and serviced through a
  poisoned slot (count = 1 at the install) that never acknowledges. Exactly one call of the
  body, so the linked handler has exactly one INTSR store (`tools/isr_audit.py`).
- **Handler installed once** (`IRQ_Request(26, hsp_backend_oneshot_isr_multi)` after the
  first latched cause, previous handler kept and restored exactly). The interrupt-path object
  is `src/platform/hsp_backend_irq_multi.c`; `hsp_backend_irq.c` (the 002/003B handlers) and
  `hsp_backend_intmr.c` (a direct INTMR store) are **not** linked. INTMR changes only through
  `__UnmaskIrq` (one call site, `hm_irq_unmask`) and `__MaskIrq`.
- **Generation discipline.** `expected_gen := n` is published only while INTMR bit 13 = 0
  (evidence: the last PI read — EVENT for cycle 0, REARMPOST/NEXTCAUSE afterwards) and only
  when cycle n is ready for PREUNMASK; the handler reads it once; slot n must be clean and the
  bookkeeping consistent (`expected_gen == n`, `entries_total == deliveries`, no generation
  error) before any unmask. An entry that lands outside slot n, a second entry of a slot, or a
  generation error ends the run (`anomaly_reentry` / `anomaly_generation`), no ACK, teardown.
- **PREUNMASK-n** (abort, never adjust): the 003B checks (two PI samples latched and masked,
  CONTROL vote = 0x8C = byte 0x1F, Disc reading = GBI reading, some source of 0x0555, odd bits
  / bit 15 / bits 12–14 = 0, slot clean) plus the 004 rules: an AV source (0x0100 | 0x0400)
  pending, **no source outside AV**, and for n > 0 the cause strictly after the previous
  re-arm. Otherwise no unmask: `abort_pre_unmask_state`, `anomaly_unexpected_source`,
  `anomaly_control_changed`.
- **Sources outside AV** (0x0001 / 0x0004 / 0x0010 / 0x0040) at any observation point
  (PREUNMASK, PREACK, POSTACK, REARMPOST, NEXTCAUSE) are **observed**: raw block, PI, CONTROL,
  cycle and timestamps preserved; status `anomaly_unexpected_source`, reason
  `unexpected_source_cycle_N`; never acknowledged, never a transport failure; no unmask if not
  yet delivered, no re-arm if after a delivery; the teardown's stop word `read | 0x8AAA` is the
  only write that touches them (as in 003A/003B).
- **ACK** exactly once per cycle: `IRQ := irq_pending | 0x8000` from the PREACK read (u16
  replicated, no hard-coded value), only with an AV source pending (a source gone before the
  ACK is `anomaly_source_lost_before_ack`), only with CONTROL 0x8C and INTMR bit 13 = 0 at
  PREACK. A failed ACK is `abort_transport` (`ack_write_failed_cycle_N`), uncertain = 1, no
  re-arm.
- **Clean boundary before any re-arm (POSTACK-n):** Disc = GBI, CONTROL 0x8C, INTMR bit 13 = 0,
  `irq & 0x0555 == 0` (else `anomaly_source_not_cleared`, no second ACK), PI bit 13 = 0 after at
  most the cycle's single main W1C (`anomaly_pi_sticky_after_ack` otherwise). Only then
  `completed_cycles` counts the cycle.
- **REARM-n** (cycles 0 and 1 only): `t_rearm` read before the call, `IRQ := 0x0000` u16
  replicated (GBI's end-of-pass write), attempted before / completed on rc ok; a failure is
  `abort_transport` (`rearm_write_failed_cycle_N`), no unmask afterwards. **REARMPOST-n**
  (ticks, PI ×2, CONTROL, IRQ, **never a W1C**): CONTROL 0x8C, INTMR bit 13 = 0, Disc = GBI,
  odd / bit 15 / high bits 0 are mandatory; the source is classified A (none, PI 0: wait),
  B (AV pending, PI 1: the next cause is already there), C (AV pending, PI 0: keep observing
  within the bound), D (outside AV: anomaly), E (invalid bits: `anomaly_rearm_state`), F (PI 1
  without a source: `anomaly_rearm_state`).
- **NEXTCAUSE-n:** INTSR polled while masked up to T_NEXT_CAUSE = 500 ms since `t_rearm`
  (operational bound, nothing logged per poll); on bit 13 one snapshot at the poll's own time
  base (PI, CONTROL, IRQ), valid only with an AV source and nothing outside AV. None within the
  bound: `no_next_cause` (`no_next_cause_cycle_N`), no unmask, teardown S4A. The next
  generation is published only after the re-arm completed, REARMPOST valid, CPU masked and the
  next cause validated.
- **CONTROL** is written once (the 003A transform) and restored once; **never rewritten per
  cycle** — an intentional difference from GBI's per-pass CONTROL write-back; a spontaneous
  change at any check is `anomaly_control_changed`.
- **W1C budget by construction:** handler exactly one per delivery, main loop at most one per
  cycle (POSTACK), none at REARMPOST or during the wait, teardown at most one: seven at most.
- **Teardown on every path**, CPU masked: CONTROL restore → IRQ read → stop word `read |
  0x8AAA` (from a register that reads 0 after a completed re-arm this is 0x8AAA, the Disc's
  stop shadow itself — reference-backed, never exercised physically from read = 0) → CLEANUPCHK
  (≤ 1 W1C) → handler restore → INTMR bit 13 = 0 verified → AR_INFO → FINAL. Variants are
  labelled (`TEARDOWN4 variant=`): `final_cycle`, `S2_before_unmask`, `S3_cycle_aborted`,
  `S4_rearm_failed`, `S4A_rearmed_no_next_cause`, `S4B_next_cause_latched`,
  `S4C_rearmpost_invalid`, `stage_a`. No silent return after the first experimental write;
  `power_cycle_required` is never cleared; **a console power cycle is mandatory** after any
  run that attempted a write — a completed run too (the screen says so).
- Not a runtime: no VIDEO/AUDIO DMA, KEYPAD, SIO, Link Port, BBA, Mobile Adapter, Game Pak,
  callbacks or unbounded loop. Byte 0 of any block never feeds a decision.

## Sequence

```text
003A stage  AR_INFO exp=3 → PRESENT gate → PI preconditions → BASE → CONTROL := (v & ~0x10) | 0x0C → P0
            → A1: IRQ := read | 0x8000 → A2: IRQ := 0 → window with INTSR polling ≤ 2000 ms, PI MASKED
            none → no_initial_cause (S2)
CAUSE n=0   EVENT: INTSR bit 13 = 1 (snapshot) → IRQ_Request(26, multi) ONCE; slots clean, anomaly poisoned
cycle n     PREPARE gen=n (masked) → PREUNMASK-n → __UnmaskIrq ×1 → handler (mask, one W1C, second read)
            → __MaskIrq (verified) → PREACK-n → IRQ := read | 0x8000 → POSTACK-n (sources 0, PI clean)
            n < 2: REARM-n IRQ := 0x0000 → REARMPOST-n (A/B/C/D/E/F) → NEXTCAUSE-n ≤ 500 ms → cycle n+1
            n = 2: no re-arm
TEARDOWN    CONTROL := original → IRQ read → IRQ := read | 0x8AAA → IRQ read → CLEANUPCHK (≤ 1 W1C)
            → handler restore → MASKCHK (INTMR bit 13 = 0, one retry) → AR_INFO := original → FINAL
POWER CYCLE REQUIRED
```

## Writes and read-only registers

| Side | Written | Read only |
|------|---------|-----------|
| GameCube | `0xCC005012` bits 3–5 (restored); INTSR := 0x2000: handler once per delivery (≤ 3), main loop ≤ 1 per cycle, teardown ≤ 1; INTMR only through `__UnmaskIrq` (≤ 3, one per cycle) and `__MaskIrq` — never stored directly | INTSR, INTMR, DSP CSR |
| GBP | TEST (handshake); CONTROL twice (transform, original value); IRQ register at most eight times: A1 = read \| 0x8000, A2 = 0, ACK-n = read \| 0x8000 (×3), REARM-n = 0 (×2), STOP = read \| 0x8AAA | IRQ register (every snapshot), TEST (BASE, P0) |
| Not touched | KEYPAD, VIDEO, AUDIO, SIOCTL, SIODATA, BBA | |

## Result codes

`status=`: `ok_cycles_completed` (only with 3 completed cycles, 3 deliveries, 3 ACKs, 2
re-arms, 2 next causes, no unexpected source / reentry / sticky PI / uncertain write, transport
ok, CONTROL stable, restore ok), `cycles_completed_with_errors` (the cycles completed, the
rest not: reason = the first deviation), `no_initial_cause`, `no_next_cause`,
`delivery_timeout` (`delivery_timeout_cycle_N`), the 003A-stage aborts by their own names,
`abort_handler_install` (`irq_multi_ops_unavailable` / `install_failed` / `prepare_failed_cycle_N`),
`abort_pre_unmask_state` (003B reasons plus `no_av_source`, `cause_not_after_rearm`),
`abort_unmask`, `abort_read_inconsistent` (Disc ≠ GBI at a per-cycle read), `abort_transport`
(`ack_write_failed_cycle_N`, `rearm_write_failed_cycle_N`, `*_read_failed_cycle_N`),
`anomaly_reentry`, `anomaly_generation`, `anomaly_mask_failure`, `anomaly_unexpected_source`,
`anomaly_source_lost_before_ack`, `anomaly_source_not_cleared`, `anomaly_pi_sticky_after_ack`,
`anomaly_rearm_state`, `anomaly_control_changed`. Every reason of a per-cycle deviation carries
its cycle (`…_cycle_N`). Unexpected hardware events are never transport failures.

## Log records

The 003A records, then `INITIRQ4 start …`, `INITIRQ4 policy …`, `CAUSE n=0 …`, `IRQ install …`,
`MULTI install …` and per cycle: `CYCLE n= start`, `PREPARE n= gen= rc= intmr13= expected_gen=
entries_total= generation_errors= slot_count= slot_fired=`, `SNAP tag=PREUNMASK-n` (+ PI ×2,
RAW ×2), `PREUNMASK n= ok= reason= …`, `PREUNMASK4 n= av= unexpected= expected_gen= …`, the
003B delivery records with ` n=` / `-n` (`PI tag=UNMASKPRE-n`, `UNMASK n= t_unmask=`, `PI
tag=UNMASKPOST-n`, `IRQ mask tag=MAIN n=`, `WAIT n=`, `PI tag=REMASKCHK-n`, `HANDLER n=`,
`HANDLERPI n=`, `HANDLERPI2 n=`, `DELIVERY n=`), `HANDLER4 n= expected_gen= entries_total= …`,
`SNAP tag=PREACK-n`, `PREACK n=`, `ACK n= before= ack_or= ack_value=` (or `ACK n= skipped=1
reason=`), `IRQW tag=ACK-n`, `SNAP tag=POSTACK-n`, `POSTACK n=`, `MAINPICLEANUP n=`, `PICLEAN
n= intsr= intmr= … ok=`, `BOUNDARY n= ok=1 completed_cycles=`, `REARM n= t_rearm= before=
value=0000 …`, `IRQW tag=REARM-n`, `SNAP tag=REARMPOST-n`, `REARMPOST n= … outcome= ok=`,
`SNAP tag=NEXTCAUSE-n … poll_intsr=`, `NEXTCAUSE n= found=1 immediate= t_next_cause=
since_rearm= since_prev_cause= …` or `NEXTCAUSE n= found=0 timed_out=1 t_end= …`; then
`TEARDOWN4 variant=`, the 003A teardown records, `IRQ restore`, `MASK final`, `INITIRQ4 end
status= reason= restore= restore_reason= teardown= …`, `WRITES`, `OBSERVED`, `RESTORE`,
`CYCLES requested= completed= causes= deliveries= acks= rearms= next_causes= reentry=
unexpected= timeouts= isr_w1c= main_w1c= teardown_w1c=`, per cycle `CYCLE n= end …` (×3
lines) and `TIMING n= cause_to_isr= isr_second= isr_to_preack= ack_to_postack=
postack_to_rearm= rearm_to_next_cause=` (individual deltas, no statistics), `MULTI
expected_gen= entries_total= generation_errors= anomaly_count= anomaly_fired= unmasks=`,
`RESTORE4 …`, `STATS`. Saved on X to `sd:/open-gbp/GBP-INIT-004_initirq4-0001.log`; dumped over
USB Gecko as `OPENGBP-INITIRQ4 LOG …`, summarized as `OPENGBP-INITIRQ4 DONE …`. Nothing is
formatted inside the handler, between an unmask and its re-mask, or per poll of a wait.

## Validation (host, no hardware)

`make test` — C: `tests/unit/test_gbp_initirq4.c` against the mock's **synthetic** models
(three cycles with next causes after a quiet re-arm / already latched at REARMPOST / visible
before the PI latch; VIDEO/AUDIO in every order and alone; a source outside AV at PREUNMASK,
PREACK, POSTACK, REARMPOST, NEXTCAUSE; ACK ineffective; PI sticky after the ACK; invalid re-arm
read-back (odd / bit 15 / high) and PI latched without a source; no next cause after either
re-arm, a late next cause within the bound; reentry in cycle 0 and cycle 1; a generation out of
range; a slot that already fired; a dirty slot; ACK failure in every cycle; re-arm failure in
both; stop / handler / AR_INFO / CONTROL restore failures; mask failure in cycle 0 and from
cycle 1's handler mask on; CONTROL changed at POSTACK / REARMPOST / PREUNMASK; delivery timeout
in cycle 0 and cycle 1; unmask ineffective; source lost before the ACK; no initial cause; the
stage-A aborts; install failure; no multi path; every PREUNMASK-0 abort; readings that
disagree; failed reads; attempted/completed sampled at the transport call for every ACK and
re-arm; wrapping time base; worst-case line widths; ring overflow; the console time base; the
mock's multi-cycle engine by hand) plus the event-order proofs of §43 and the "never"
properties (INTMR never stored, one install, ≤ 3 unmasks each with the cause latched, every
generation published masked, handler W1C ≤ 3, main W1C ≤ 4, ≤ 7 in total, IRQ writes ≤ 8 to
index D only, CONTROL ≤ 2, no KEYPAD/VIDEO/AUDIO/SIO access). The physical 003A fixture drives
the stage up to the EVENT (no interrupt path: stops at the install); the physical 003B fixture
drives cycle 0 verbatim up to its POSTACK and, cut before the CONTROL restore, meets an
exhausted script at REARM-0 — **no physical GBP-INIT-004 fixture exists and none is
fabricated**. `tests/host/test_initirq4_replay.py` round-trips a mock log through
`tools/probelog.py` (marked SYNTHETIC, under `build/`; the optional `I p <gen>` lines).

`make initirq4-audit` — `tools/isr_audit.py --symbol hsp_backend_oneshot_isr_multi` on the
linked handler (only `__MaskIrq` called, no indirect call, exactly one INTSR store of 0x2000
after the mask, no INTMR store, bounded loop allowed) and `tools/poc_audit.py --profile 004`
on every object (`hsp_backend_irq_multi.o` linked; `hsp_backend_irq.o`, `hsp_backend_intmr.o`,
the 001/002/003B probes not; `__UnmaskIrq` only from `hm_irq_unmask`; `IRQ_Request` only from
`hm_irq_install` / `hm_irq_restore`; `__MaskIrq` only from `hm_irq_mask` and the handler; INTMR
stores 0; INTSR stores exactly in `h_write_intsr` and the handler; `gbp_regwrite_irq_u16`
3 + 1 + 1 logical call sites; `main.o` uses `hsp_backend_irq_transport_multi`). The audit proves
call sites, never executions: the eight IRQ-register writes of a complete run (A1, A2, ACK ×3,
REARM ×2, STOP) are proven by the unit tests' operation trace (`test_attempted_at_call_time`
pins the value sequence and the counters at every call) and by the log's `WRITES` record.

`make initirq4-dolphin` — no HSP device → `abort_inconsistent`; Dolphin GBPlayer model →
`abort_control_shape` (idle CONTROL 0x03). Neither run writes CONTROL or the IRQ register,
installs the handler, unmasks or reaches the multi-cycle path; preconditions are not weakened
for Dolphin, the OSD is disabled by the runner, and Dolphin proves nothing about the physical
service loop.

## Physical procedure (NOT to be requested from this dirty build)

Same configuration as GBP-INIT-003B: GBP attached, no Game Pak, Link Port empty, no
PicoAdapterGB, BBA attached without cable, one controller, one Memory Card, SD2SP2, Swiss.
Steps, once a clean, audited and authorized candidate exists: launch, do not press anything
until the summary (≈ 2.1 s + 2 × 0.6 s bounds at most), photograph the screen, **X** to
save, **START** to return to Swiss, then **switch the console off**. Return
`/open-gbp/GBP-INIT-004_initirq4-0001.log`. Success = a clean, restorable observation,
whatever the number of cycles that completed.

## Risks (accepted in the design)

The same as 003B for every cycle (audited handler; `__MaskIrq` physically proven; a level
line re-latching after the handler's W1C has no CPU effect while masked), plus: a next cause
that never comes after `IRQ := 0` (bounded, `no_next_cause`, stop word from a register that
reads 0 → 0x8AAA); a source outside AV raised by the re-arm (observed, never acknowledged);
device masks open with bit 15 = 0 while the CPU is masked between cycles (GBI's steady state
with the CPU unmasked — here shorter than the bound). A persistent cause with an ineffective
mask would hang the CPU whichever handler is installed — the mandatory power cycle covers it.
