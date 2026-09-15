# poc/gbp-init-irq-program-probe — GBP-INIT-003A

**Test ID:** `GBP-INIT-003A` — **Build ID:** `initirqa-0001` — commit `d956b1b` — DOL SHA-256
`8c225bd101a215982ac59d096630a9e13b34557e3cdf4eb8354298855232bfa5` — **PHYSICALLY EXECUTED
2026-09-15** (log sha256 `ae911745…2ef8`, 13231 bytes; see "Result" below). Builds after
`d956b1b` differ from the executed one by the `intsr13_in_phase` field of the WINDOW records
(a logging correction, see "Result"); they are not the executed binary.

**Question:** with the PI HSP interrupt masked for the whole run, what do the two
writes of GBI's first loop pass change in the GBP IRQ register as read back —
**A1** `IRQ := irq_read | 0x8000` (GBI's acknowledge: the bits that read 1 are
written 1) and then **A2** `IRQ := 0` (GBI's end-of-pass write) — and does a source
that becomes visible after A2 raise INTSR bit 13 while delivery to the CPU stays
masked? The two writes are separated so that source acknowledge (A1) and mask/control
programming (A2) are observed one at a time. Neither reference reads the register
back between its writes; Dolphin models neither the masks nor bit 15 as the hardware
shows them (DEVLOG 2026-09-15, HARDWARE_TESTS.md "Planned tests — GBP-INIT-003A").

Every outcome is a valid observation: sources cleared / not cleared / re-asserted by
A1; masks answering or not answering A2; bit 15 changing in any way; INTSR bit 13
staying 0 or rising at any point; another block layout. Hypotheses (GBP-IRQ-005:
even bits = sources, W1C; odd bits = level-written masks; bit 15 = global hold or
pending summary) stay hypotheses until the log says otherwise.

## Provenance and rules

- A1 and A2 are literally the values GBI (an independent mature implementation)
  writes in its first pass (GBP-IRQ-004), in GBI's order and in GBI's 16-bit layout:
  the u16 replicated 16 times, `hi lo hi lo …`, one 32-byte DMA at `base + 0xD00000`
  (`0x80015da4`; `IRQ := 0` is `0x80015da0`, 32 × 00). Not GBI's 64-byte KEYPAD+IRQ
  write: KEYPAD is never touched.
- The stop word is the Nintendo Start-up Disc's (the official reference): `IRQ :=
  read | 0x8AAA` — bit 15 plus the odd mask bits of the six serviced slots
  (`0x8008be04`, shadow set by `0x8008bf84`; GBP-IRQ-002/006). Its init issues the
  same formula with shadow 0 (`IRQ := read`, PI masked), the official precedent for A1.
- PI HSP (interrupt 26) is **never unmasked**: no handler is installed, no
  `__UnmaskIrq`/`__MaskIrq`, no `IRQ_Request`/`IRQ_Free`, INTMR is only read. The
  interrupt-path object `src/platform/hsp_backend_irq.c` is not linked; `make
  initirqa-audit` proves it on the objects (below).
- Preconditions abort, never adjust: PRESENT (both criteria, all patterns); INTMR bit
  13 == 0 and INTSR bit 13 == 0 at the start; CONTROL idle shape `(v & 0x10) != 0`,
  `(v & 0x0C) == 0`, vote == byte 0x1F; IRQ shape `(v & 0x0AAA) == 0x0AAA`, `(v &
  0x8000) != 0`, `(v & 0x7000) == 0`, Start-up Disc reading == GBI reading (even
  source bits may vary). INTMR bit 13 is re-checked at P0 and at A2PRE.
- An INTSR bit 13 that rises inside the window is observed, never acknowledged there;
  the teardown performs at most one `INTSR := 0x2000`, only if bit 13 is set while masked.
- Writing the BASE raw block back is not a restore and is never done.
- Byte 0 of any block is raw evidence only; no decision reads it.
- **A console power cycle is mandatory** after any run that attempted a CONTROL or IRQ
  write; the screen says `POWER CYCLE REQUIRED` in that case.

## Sequence

```text
ARINFO     read original → bits 3-5 := 3 → readback
DET        TEST handshake (C3,3C,FF,00); PRESENT required (ABSENT → abort_not_present,
           anything else → abort_inconsistent); nothing else is written on those paths
PRE        INTSR/INTMR read; bit 13 of both must be 0 (abort_pi_precondition)
BASE       INTSR/INTMR, CONTROL raw, IRQ raw, TEST raw; CONTROL shape (abort_control_read /
           abort_control_shape); IRQ shape (abort_irq_shape) — no write yet
EXP        CONTROL := (v & ~0x10) | 0x0C, byte replicated ×32 (validated transform)
P0         INTSR/INTMR, CONTROL, IRQ, TEST; INTMR bit 13 re-checked
--- experimental region: captured into structures, formatted only after the window ---
A1PRE      IRQ read (raw + both readings); shape re-checked
A1         IRQ := irq_a1pre | 0x8000   (u16 replicated 16×; "IRQW tag=A1")
A1-0       immediately: INTSR/INTMR, CONTROL, IRQ; then A1-50US and A1-500US (time-base
           deadlines; INTSR polled in between, counter only)
A2PRE      IRQ read (irq_before_zero) + INTSR/INTMR; INTMR bit 13 re-checked (else no A2)
A2         IRQ := 0x0000                (32 × 00; "IRQW tag=A2")
A2-0       immediately; then A2-50US, A2-500US, A2-5MS, A2-50MS, A2-500MS, A2-2000MS with
           INTSR polled between deadlines; first INTSR bit 13 == 1 → t_first_intsr13 and an
           EVENT snapshot (INTSR/INTMR, CONTROL, IRQ of the same moment); the window then
           ends early (configurable). No W1C inside the window.
--- end of the experimental region (log records are formatted here) ---
TEARDOWN   1 CONTROL := v (original), readback   2 IRQ read   3 stop = read | 0x8AAA
           4 IRQ := stop (u16 layout; "IRQW tag=STOP")   5 IRQ read   6 INTSR/INTMR read
           7 if INTSR bit 13 == 1 (and INTMR bit 13 == 0): ONE INTSR := 0x2000, one re-read
             (pi_cleanup_sticky=1 if still set; never a loop)
           8 AR_INFO := original, readback   9 FINAL (INTSR/INTMR, CONTROL, IRQ)
POWER CYCLE REQUIRED
```

If A1's transfer fails there is no A2 (`abort_transport a1_write_failed`); if the
CONTROL write fails there is neither A1 nor A2; the teardown runs on every path
with what was actually attempted (the stop word only after an IRQ write was
attempted). Deadlines are operational bounds (time-base distances), not properties of
the Game Boy Player. No DMA, formatting, SD or screen work happens between the
samples; the screen and the X/START loop come only after the teardown.

## Writes and read-only registers

| Side | Written | Read only |
|------|---------|-----------|
| GameCube | `0xCC005012` bits 3–5 (restored); INTSR := 0x2000 at most once, teardown only | INTSR, INTMR (INTMR is **never written**, directly or through libogc2), DSP CSR |
| GBP | TEST (handshake); CONTROL twice (transform, original value); IRQ register three times: A1 = read \| 0x8000, A2 = 0, STOP = read \| 0x8AAA | IRQ register (BASE, P0, every sample, teardown reads), TEST (BASE, P0) |
| Not touched | KEYPAD, VIDEO, AUDIO, SIOCTL, SIODATA, BBA; no interrupt handler, no unmask | |

`irq_attempted` counts transfers issued, `irq_completed` those that reported
completion; both appear in the summary, the log and on screen. For every
experimental write the pair `attempted/completed` is a safety state, not a
statistic: `attempted = 1` is stored **before** the transport is invoked and
`completed = 1` only after it returned ok, so a timeout, a busy refusal or an
unscripted replay operation all leave `attempted=1 completed=0` — the device may
have taken the write — and `power_cycle_required` is raised at the first attempt,
never cleared by a later failure or by a successful restore. The `WRITES` record and
the summary list `ctl_exp`, `a1`, `a2`, `stop` and `ctl_restore` as `attempted/completed`
plus `uncertain` (attempted without completion); the screen prints the same line and
`DEVICE STATE UNCERTAIN` when that count is not 0.

## Result codes

Experimental result (`status=`): `ok_no_pi_cause_observed`, `ok_pi_cause_observed`
(INTSR bit 13 seen set at any point after the CONTROL write), `abort_arinfo`,
`abort_not_present`, `abort_inconsistent`, `abort_pi_precondition`
(`pi_unavailable` / `intmr13_unmasked` / `intsr13_set` / `intmr13_unmasked_p0` /
`intmr13_unmasked_a2pre`), `abort_control_read`, `abort_control_shape`,
`abort_irq_shape` (`irq_ambiguous` / `irq_masks_not_set` / `irq_bit15_clear` /
`irq_high_bits_set`), `abort_transport` (`control_write_failed` / `p0_read_failed` /
`a1pre_read_failed` / `a1_write_failed` / `a2pre_read_failed` / `a2_write_failed`).
Restore, reported separately and per step: `control_restore_ok`, `irq_stop_write_ok`,
`irq_stop_readback_ok` (+ `stop_masks_readback`, `stop_bit15_readback` as
observations), `pi_cleanup_performed`, `pi_cleanup_ok`, `pi_cleanup_sticky`,
`arinfo_restore_ok`; `restore=error restore_reason=` names the first failed step.

## Log records

`IDENT`, `ENV … a1_obs_us= a2_obs_us=`, `INITIRQA start …`, `INITIRQA window …`, `ARINFO
orig/exp/restore`, `TESTW/TESTR tag=DET`, `DET verdict=`, `PI tag=PRE`, `PRECOND …`, `SNAP
tag=BASE ticks= since_control= since_a1= since_a2= polls_before=` + `PI tag=BASE` + `RAW BASE
idx=4|d|0`, `CONTROL semantic …`, `IRQSHAPE tag=BASE|A1PRE disc= gbi= agree= masks_ok=
bit15_ok= high_ok= … ok= reason=`, `CTLW tag=EXP|RESTORE … t_after= layout=gbi-replicated
data=`, `SNAP tag=P0` (+PI, RAW×3), `P0CHK …`, `RAW A1PRE idx=d`, `A1 before= ack_or=
ack_value=`, `IRQW tag=A1|A2|STOP addr= before= write= layout=gbi-u16-replicated rc= ticks=
polls= dspcr= t_after= data=<64 hex>`, `SNAP tag=A1-0|A1-50US|A1-500US|A2-0|A2-50US|…|
A2-2000MS|EVENT` (+PI, RAW×2; EVENT adds `poll_intsr=`), `WINDOW tag=A1|A2 deadlines=
polls= … intsr13_seen= t_first_intsr13= first_phase= [t_end= elapsed_ticks= elapsed_us=]`,
`RAW A2PRE idx=d`, `PI tag=A2PRE`, `A2CHK …`, `A2 before= value=0000`, `REGION
log_count_start= log_count_end= formatted_inside=0`, `TEARDOWN start …`, `RAW TDCTL idx=4`,
`CONTROL restore …`, `RAW IRQSTOPPRE idx=d`, `IRQSTOP pre … stop_value= formula=read|stop_or
comment=startup-disc-stop-shadow`, `RAW IRQSTOPPOST idx=d`, `IRQSTOP post …`, `PI
tag=CLEANUPCHK`, `CLEANUP performed=0|1 …`, `PI tag=CLEANUP`, `ARINFO restore …`, `SNAP
tag=FINAL` (+PI, RAW×2), `FINAL …`, `INITIRQA end status= reason= restore= restore_reason=
power_cycle_required= errors= transport_ok=`, `WRITES control_written= irq_attempted=
irq_completed= ctl_exp=a/c a1=a/c a2=a/c stop=a/c ctl_restore=a/c uncertain= power_cycle_required=`,
`OBSERVED intsr13_seen= t_first_intsr13= first_phase= first_value= polls_at_first= event=
ended_early=`, `RESTORE control_restore_ok= …`, `STATS`. The `WINDOW` records carry
`intsr13_in_phase=` (phase-local; build initirqa-0001 printed the run-global
`intsr13_seen=` there instead — see "Result"). Every CONTROL/IRQ record carries the raw 32 bytes next
to both readings; the `REGION` record proves that nothing was formatted inside the
experimental region. Saved on X to `sd:/open-gbp/GBP-INIT-003A_initirqa-0001.log`; dumped
over USB Gecko as `OPENGBP-INITIRQA LOG …`, summarized as `OPENGBP-INITIRQA DONE …`.

## Validation (host, no hardware)

`make test` — C: `tests/unit/test_gbp_initirqa.c` against the mock's **synthetic**
source/mask model of the IRQ register (even bits W1C, odd bits level, bit 15 as a level
or as a W1C summary, programmable re-assertion; nothing physical): nominal no-cause run,
cause after A2 (EVENT, early end, stop word acknowledges it, one cleanup / none under a
level model), sticky cleanup, cause visible at A2-0, bit-15 summary reading, window
continuing after the event, device ignoring the writes, A1 / A2 / stop write failures,
CONTROL write / P0 / A1PRE / A2PRE / in-window read failures, CONTROL restore ignored,
AR_INFO restore failure, IRQ shape aborts (bit 15 clear, masks not set, high bits set,
ambiguous readings, shape changed at A1PRE), PI preconditions at start / P0 / A2PRE,
absent / inconsistent, CONTROL shapes (0x80, 0x9C, Dolphin's 0x03, ambiguous, read
failure), transports without time base or INTSR polling, polling disabled, ring
overflow, line-length regression with a wrapping time base, the write primitive's
layouts byte by byte, plus the event-order and "never" assertions (zero handler
installs, zero unmasks, zero INTMR writes, zero KEYPAD/VIDEO/AUDIO/SIO accesses, IRQ
writes only to index D with exactly the three computed values, BASE raw block never
written back). Physical fixtures: the GBP-attached init-0001 and initirq-0001 prefixes
drive the gate, the PI preconditions, BASE and both shape checks on physical bytes and
end at the first experimental write (unanswered → `abort_transport`, no IRQ write); the
no-GBP fixture aborts ABSENT verbatim. **No physical GBP-INIT-003A fixture exists**;
`tests/host/test_initirqa_replay.py` round-trips a mock log through `tools/probelog.py`
into a replay script (marked SYNTHETIC, kept under `build/`) and back through the probe.

`make initirqa-audit` — `tools/poc_audit.py` on every object linked into the DOL:
`hsp_backend_irq.o` absent; no relocation to `__UnmaskIrq`, `IRQ_Request`, `IRQ_Free`,
`hsp_backend_oneshot_isr` (a `__MaskIrq` reference would be reported for investigation);
no store to PI INTMR (`lis -13312` + displacement 12292); `gbp_regwrite_irq_u16` called
exactly three times from `gbp_initirqa_probe.o` and from nowhere else;
`gbp_regwrite_control_byte` exactly twice; the ELF defines neither the one-shot handler
nor the GBP-INIT-001/002 probe entry points.

`make initirqa-dolphin` — no HSP device → `abort_not_present`; Dolphin GBPlayer model →
`abort_control_shape` (idle CONTROL 0x03). Neither run writes CONTROL or the IRQ
register; preconditions are not weakened for Dolphin, and Dolphin proves nothing about
the physical register.

## Physical procedure (NOT to be requested from this dirty build)

Same configuration as GBP-INIT-002: GBP attached, no Game Pak, Link Port empty, no
PicoAdapterGB, BBA attached without cable, one controller, one Memory Card, SD2SP2,
Swiss. Steps, once a clean candidate exists: launch, do not press anything until the
summary (the experiment lasts at most ≈ 2 s plus the DMAs), photograph the screen,
**X** to save, **START** to return to Swiss, then **switch the console off** — no other
test or software before the power cycle. Return `/open-gbp/GBP-INIT-003A_initirqa-0001.log`.
Success = a clean, restorable observation, whatever A1 and A2 changed.

## Risks (accepted in the design)

A device line asserted for up to ≈ 2 s with PI masked (no CPU effect); a model error
that leaves the device asserted behind CONTROL 0x10 (the mandatory power cycle covers
it); bits 12–14 written 0 by A2 (both references do the same); a stop word that the
device answers differently from the model (observed, logged, power cycle). Cartridge
not introduced; byte 0 kept as raw evidence only.

## Result (2026-09-15, commit d956b1b, DOL 8c225bd1…bfa5)

`status=ok_pi_cause_observed restore=ok`, 44 transfers, 0 errors, every write
attempted = completed, `power_cycle_required=1` (console power-cycled). PRESENT
4/4; PI `0x00010000` / `0x000001FA` throughout the preconditions; BASE CONTROL
`0x90`, IRQ `0x8AAE`; CONTROL `0x90 → 0x8C`. **A1** `IRQ := 0x8AAE` read back
`0x8AAA` 0.47 µs later and at +50 µs / +500 µs (source bit 0x0004 cleared by
writing 1; masks and bit 15 kept). **A2** `IRQ := 0x0000` read back `0x0000` at
+0.54 µs, +50 µs, +500 µs, +5 ms, +50 ms with CONTROL `0x8C` and INTSR bit 13 = 0.
**EVENT** 105.273 ms after A2 (4263568 ticks): INTSR `0x00012000` with INTMR
`0x000001FA` — the HSP cause captured at the PI while masked, no CPU exception —
CONTROL `0x8C`, IRQ `0x0400`; window ended early. Teardown: CONTROL `0x90`, IRQ
read `0x0500` (0x0100 risen after the EVENT), stop `IRQ := 0x8FAA` → `0x8AAA`
(both sources cleared, masks and bit 15 read 1), INTSR still `0x00012000` after
the device sources were gone, one `INTSR := 0x2000` → `0x00010000`, AR_INFO
`0x005B → 0x0043`, FINAL under code 0 `00` / `9090`. Evidence GBP-HW-027…034,
GBP-PI-004, GBP-IRQ-007; log verbatim in HARDWARE_TESTS.md; fixture
`captures/fixtures/hw-gamecube-gbp-2026-09-15-initirqa-0001.gbpreplay` replays
the whole run with the console's time base (`tests/unit/test_gbp_initirqa.c`,
`tests/host/test_hw_fixture.py`).

**Logging defect of build initirqa-0001:** record `WINDOW tag=A1 … intsr13_seen=1`
printed the run-global first-sighting flag after the whole window had ended. The
primary A1 records (A1-0, A1-50US, A1-500US, A2PRE) all read INTSR bit 13 = 0 and
`OBSERVED first_phase=A2` places the first sighting in the A2 window: there was no
INTSR bit 13 during A1. The log is preserved as written; later builds print a
phase-local `intsr13_in_phase=` in both WINDOW records, the replay of the fixture
through the corrected probe reports `intsr13_in_phase=0` for A1 and `=1` for A2,
and the mock scenario "cause after A2" pins it.
