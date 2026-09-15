# poc/gbp-init-irq-deliver-probe — GBP-INIT-003B

**Test ID:** `GBP-INIT-003B` — **Build ID:** `initirqb-0001` — **IMPLEMENTED 2026-09-15,
NOT PHYSICALLY EXECUTED.** The build under review is a **DIRTY BUILD — NOT A PHYSICAL
CANDIDATE** (base HEAD `fa6f35e`, tree dirty; DOL SHA-256
`ee34d93ad2774a9365fa9afd8485558f78e2f53df939b35ee1a84220f581df80`, 383232 bytes). A
checkpoint commit, a clean rebuild, a clean audit and a recorded hash precede any physical
run; nothing here is a hardware request.

**Question:** with a real HSP cause already latched at the PI (INTSR bit 13 = 1) while IRQ 26
is masked (INTMR bit 13 = 0) — the state GBP-INIT-003A produced ≈105 ms after its write A2 —
does `__UnmaskIrq(IM_PI_HSP)` deliver it to the CPU handler at once? And what does INTSR do
after the handler's write-1-to-clear while the GBS-DOL source is still pending on the device
(the level/pulse discriminator, U-GBP-022)? Every outcome is a valid observation; the
level/pulse readings are observations, never pass/fail. Full design and validation criteria:
`docs/research/HARDWARE_TESTS.md` "Planned tests — GBP-INIT-003B"; implementation record:
`docs/research/DEVLOG.md` 2026-09-15 "GBP-INIT-003B implemented".

## Provenance and rules

- The whole programming sequence is the physically executed GBP-INIT-003A code path
  (`src/gbp/gbp_initirqa_probe.c`, stage API), run verbatim with PI HSP masked and no
  handler until INTSR bit 13 = 1 is observed (EVENT). Nothing of that experiment is copied.
- Handler installation point **B**: `IRQ_Request(26, oneshot_ext)` only after the latched
  cause has been observed; the previous handler (NULL in GBP-INIT-002) is kept and restored;
  the install must leave a clean record. An unmask never happens without a handler.
- PREUNMASK preconditions (abort, never adjust): INTSR bit 13 = 1 in both PI samples, INTMR
  bit 13 = 0, CONTROL vote = 0x8C, both IRQ readings equal, at least one even source bit
  (0x0555) set, odd bits and bit 15 = 0, bits 12–14 = 0. Otherwise `abort_pre_unmask_state`
  (`read_failed` / `record_not_clear` / `cause_lost` / `intmr13_unmasked` /
  `control_changed` / `semantic_disagree` / `irq_state_unexpected`): no unmask, teardown.
- Exactly one `__UnmaskIrq(IM_PI_HSP)` call site in the binary (`h_irq_unmask`); INTMR is
  never stored directly (the GBP-INIT-001 INTMR object `hsp_backend_intmr.c` is not linked);
  `__MaskIrq` is called by the handler, the main loop and the teardown.
- Handler (`gbp_irq_oneshot_service_ext`, `src/gbp/gbp_irq_oneshot.h`, audited on the linked
  object by `tools/isr_audit.py`): t_entry → INTSR → INTMR → count++ → `__MaskIrq` → INTMR →
  INTSR → exactly one `INTSR := 0x2000` → INTSR → bounded ≈100-tick time-base wait (2.5 µs,
  capped at 4096 reads) → t_second → INTSR → INTMR → fired. A second entry re-masks, records
  `reentry_t/intsr/intmr`, does not acknowledge. No DMA, no GBP access, no formatting, no
  allocation, no callbacks, no semaphores.
- PI INTSR W1C budget: handler exactly 1; main loop at most 1 (after the device ACK if bit 13
  reads 1 — POSTACK — else at CLEANUPCHK), never repeated; sticky recorded. Maximum 2 per run.
- Device ACK (fired path only): `IRQ := irq_pending | 0x8000` derived from the PREACK read,
  through `gbp_regwrite_irq_u16` (GBI's u16-replicated layout; A1's physically validated
  form) under the running CONTROL 0x8C, before any restore; skipped if the PREACK IRQ read
  failed or its two readings disagree. Timeout / anomaly paths perform no device ACK: the
  stop word acknowledges the pending sources.
- Every path after the CONTROL write ends in the 003A teardown extended by the handler
  restore and the mask verification: CONTROL restore → IRQ read → Disc stop word `read |
  0x8AAA` (whenever an IRQ write was attempted) → CLEANUPCHK (budget) → `IRQ_Request(26,
  previous)` → INTMR bit 13 must read 0 (one retry) → AR_INFO → FINAL. No silent return.
- `attempted = 1` is stored before the transport is invoked and `completed = 1` only after
  it returned ok; `power_cycle_required` is raised at the first experimental attempt and never
  cleared. **A console power cycle is mandatory** after any run that attempted a write.
- Never touched: KEYPAD, VIDEO, AUDIO, SIOCTL, SIODATA, BBA. Byte 0 of any block is raw
  evidence only. Writing a previously read block back is never a restore.

## Sequence

```text
003A stage  AR_INFO exp=3 → PRESENT gate → PI preconditions → BASE (CONTROL/IRQ shape)
            → CONTROL := (v & ~0x10) | 0x0C → P0 → A1PRE → A1: IRQ := read | 0x8000 → A1-0, +50 µs,
            +500 µs → A2PRE → A2: IRQ := 0 → A2-0 … samples with INTSR polling up to 2000 ms, PI MASKED
            no INTSR bit 13 within the bound → NO unmask → teardown → no_cause_within_tmax
EVENT       first INTSR bit 13 = 1: snapshot (INTSR/INTMR, CONTROL, IRQ), window ends → "CAUSE"
INSTALL     IRQ_Request(26, oneshot_ext); previous handler kept; record must be clean
PREUNMASK   PI ×2, CONTROL, IRQ → preconditions above (else abort_pre_unmask_state, no unmask)
UNMASK      UNMASKPRE PI → t_unmask := time base → __UnmaskIrq ×1 → t_post_unmask → UNMASKPOST PI
            [the exception is taken when __UnmaskIrq restores EE: the handler may run inside the call]
WAIT        record polled only (no DMA, no formatting) up to T_DELIVERY = 100 ms (operational)
REMASK      __MaskIrq (idempotent) → REMASKCHK: INTMR bit 13 must read 0 (one retry) → record copied
            not fired: abort_unmask (INTMR bit 13 never opened) or delivery_timeout; no device ACK
            count > 1: anomaly_reentry; INTMR bit 13 still 1: anomaly_mask_failure — no device ACK
PREACK      PI ×2, CONTROL, IRQ  (the source is still pending on the device: level/pulse readings)
ACK         IRQ := irq_pending | 0x8000 (u16 replicated; "IRQW tag=ACK")
POSTACK     PI ×2, CONTROL, IRQ → if INTSR bit 13 = 1: ONE main-loop INTSR := 0x2000 + re-read
TEARDOWN    CONTROL := original → IRQ read → IRQ := read | 0x8AAA → IRQ read → CLEANUPCHK (budget)
            → handler restore → MASKCHK (INTMR bit 13 = 0, one retry) → AR_INFO := original → FINAL
POWER CYCLE REQUIRED
```

## Writes and read-only registers

| Side | Written | Read only |
|------|---------|-----------|
| GameCube | `0xCC005012` bits 3–5 (restored); INTSR := 0x2000: handler exactly once, main loop at most once; INTMR only through `__UnmaskIrq` (once) and `__MaskIrq` — never stored directly | INTSR, INTMR, DSP CSR |
| GBP | TEST (handshake); CONTROL twice (transform, original value); IRQ register four times at most: A1 = read \| 0x8000, A2 = 0, device ACK = read \| 0x8000 (fired path), STOP = read \| 0x8AAA | IRQ register (every snapshot and teardown read), TEST (BASE, P0) |
| Not touched | KEYPAD, VIDEO, AUDIO, SIOCTL, SIODATA, BBA | |

## Result codes

`status=`: `ok_delivery_observed`, `delivery_timeout` (not a transport error),
`no_cause_within_tmax` (not a transport error), the 003A-stage aborts by their own names
(`abort_arinfo`, `abort_not_present`, `abort_inconsistent`, `abort_pi_precondition`,
`abort_control_read`, `abort_control_shape`, `abort_irq_shape`, `abort_transport`),
`abort_handler_install` (`irq_ops_unavailable` / `install_failed`), `abort_pre_unmask_state`
(reasons above), `abort_unmask` (`unmask_not_effective`), `anomaly_reentry`,
`anomaly_mask_failure`. Restore, per step: the 003A fields plus `handler_restored`,
`mask_ok`, `intmr_final`, `main_pi_w1c` + `site` + `sticky`, `pi_sticky_final`;
`restore=error restore_reason=` names the first failed step.

## Log records

The 003A records (see `poc/gbp-init-irq-program-probe/README.md`) plus `INITIRQB start
t_delivery_ms= … install_point=after_latched_cause`, `CAUSE t_event= since_a2= intsr= intmr=
… control= irq=`, `IRQ install rc= old_handler= record_count= record_fired=`, `SNAP
tag=PREUNMASK` (+ `PI tag=PREUNMASK`, `PI tag=PREUNMASKb`, RAW ×2), `PREUNMASK ok= reason=
intsr13=a,b intmr13=a,b control= irq=disc/gbi src= odd= bit15=`, `PI tag=UNMASKPRE`, `UNMASK
t_unmask= rc= t_post= dt_post=`, `PI tag=UNMASKPOST … fired=`, `IRQ mask tag=MAIN|RETRY rc=`,
`WAIT fired= timed_out= polls= wait_ticks= wait_us= t_delivery_ms= t_delivery_ticks=`, `PI
tag=REMASKCHK[2]`, `HANDLER fired= count= t_entry= t_unmask= latency_ticks= latency_us=
reentry=`, `HANDLERPI intsr_at_entry= intmr_at_entry= intmr_after_mask= intsr_before_w1c=
intsr_after_w1c= reentry_intsr= reentry_intmr=`, `HANDLERPI2 t_second= dt_second=
intsr_second= intmr_second= reentry_t=`, `DELIVERY …` (bit-13 views), `SNAP tag=PREACK`
(+ PI ×2, RAW ×2), `PREACK … src_pending=`, `ACK before= ack_or= ack_value= formula=read|ack_or`
or `ACK skipped=1 reason=`, `IRQW tag=ACK …`, `SNAP tag=POSTACK` (+ PI ×2, RAW ×2), `POSTACK
… bit15= ack=a/c`, `MAINPICLEANUP site=POSTACK performed=0|1 [value=]` (+ `PI tag=MAINCLEANUP`,
`MAINPICLEANUP result rc= … sticky=`), the 003A teardown records, `IRQ restore rc= ok=
old_handler=`, `PI tag=MASKCHK[2]`, `MASK final intmr= intmr13= orig_intmr13=0 ok=`, `INITIRQB
end status= reason= restore= restore_reason= power_cycle_required= errors= transport_ok=`,
`WRITES`, `OBSERVED`, `RESTORE`, `ACKS ack=a/c ack_value= irq_pending= skipped= reason=
isr_pi_w1c= main_pi_w1c= site= sticky= uncertain=`, `RESTOREB handler_installed=
handler_restored= old_handler= mask_ok= intmr_final= pi_sticky_final= unmasked=
masked_again=`, `STATS`. Saved on X to `sd:/open-gbp/GBP-INIT-003B_initirqb-0001.log`;
dumped over USB Gecko as `OPENGBP-INITIRQB LOG …`, summarized as `OPENGBP-INITIRQB DONE …`.

## Validation (host, no hardware)

`make test` — C: `tests/unit/test_gbp_initirqb.c` (1031 checks) against the mock's
**synthetic** models: immediate delivery (pulse-like W1C), level re-assert, delayed re-latch
during and after the handler's wait (POSTACK main W1C), W1C budget at CLEANUPCHK and sticky
W1C, delivery timeout, unmask ineffective (`abort_unmask`), reentry, mask failure with and
without a synthetic storm, install failure, no IRQ path, every PREUNMASK abort, dirty record
after the install, non-NULL previous handler, ACK / stop / CONTROL restore / handler restore /
AR_INFO restore failures, PREACK and PREUNMASK read failures, no cause within the bound, the
003A-stage aborts, attempted/completed sampled at the transport call, wrapping time base,
worst-case line widths, ring overflow, the console time base, the mock's extended body driven
by hand, plus the event-order (CAUSE < install < PREUNMASK < unmask < ISR entry < ISR mask <
ISR W1C < main re-mask < PREACK < device ACK < POSTACK < CONTROL restore < stop < handler
restore < AR_INFO restore) and "never" assertions (INTMR never stored, at most one unmask,
handler W1C ≤ 1, main W1C ≤ 1, IRQ writes ≤ 4 to index D only, no KEYPAD/VIDEO/AUDIO/SIO
access). The physical GBP-INIT-003A fixture drives the probe verbatim up to the EVENT and,
having no interrupt path, stops at the install with the 003A teardown (every line consumed).
**No physical GBP-INIT-003B fixture exists**; `tests/host/test_initirqb_replay.py`
round-trips a mock log through `tools/probelog.py` (marked SYNTHETIC, under `build/`).

`make initirqb-audit` — `tools/isr_audit.py` on `hsp_backend_oneshot_isr_ext` and
`hsp_backend_oneshot_isr` as linked (only `__MaskIrq` called, no indirect call, exactly one
INTSR store of 0x2000 after the mask, no INTMR store; ext body 82 instructions, base 70) and
`tools/poc_audit.py --profile 003b` on every object (hsp_backend_irq.o linked, the
GBP-INIT-001 INTMR object and the 001/002 probes not; `__UnmaskIrq` only from `h_irq_unmask`;
`IRQ_Request` only from `h_irq_install` / `h_irq_restore`; `__MaskIrq` only from `h_irq_mask`
and the two handlers; INTMR stores 0; INTSR stores exactly in `h_write_intsr` and the two
handlers; `gbp_regwrite_irq_u16` 3 + 1 call sites; `main.o` uses `hsp_backend_irq_transport_ext`).

`make initirqb-dolphin` — no HSP device → `abort_inconsistent`; Dolphin GBPlayer model →
`abort_control_shape` (idle CONTROL 0x03). Neither run writes CONTROL or the IRQ register,
installs the handler or unmasks; preconditions are not weakened for Dolphin, the OSD is
disabled by the runner, and Dolphin proves nothing about the physical delivery.

## Physical procedure (NOT to be requested from this dirty build)

Same configuration as GBP-INIT-003A: GBP attached, no Game Pak, Link Port empty, no
PicoAdapterGB, BBA attached without cable, one controller, one Memory Card, SD2SP2, Swiss.
Steps, once a clean candidate exists: launch, do not press anything until the summary (at
most ≈ 2.1 s plus the DMAs), photograph the screen, **X** to save, **START** to return to
Swiss, then **switch the console off** — no other test or software before the power cycle.
Return `/open-gbp/GBP-INIT-003B_initirqb-0001.log`. Success = a clean, restorable
observation, whatever the delivery and the INTSR readings were.

## Risks (accepted in the design)

A storm if the mask-first order failed (mitigated: audited handler, `__MaskIrq` physically
proven in GBP-INIT-002); a level line re-latching after the handler's W1C (no CPU effect,
INTMR masked); device masks open with bit 15 = 1 between the ACK and the stop (≈1 ms, GBI's
steady state); a second source arriving between the EVENT and the unmask (allowed); every
write has physical precedent (A1/A2/stop in 003A; the ACK is A1's form). A persistent cause
with an ineffective mask would hang the CPU whichever handler is installed — the mandatory
power cycle covers it. Cartridge not introduced; byte 0 kept as raw evidence only.

## Result

None — NOT PHYSICALLY EXECUTED.
