# poc/gbp-init-irq-probe — GBP-INIT-002

**Test ID:** `GBP-INIT-002` — **Build ID:** `initirq-0001` — commit `4e3cb43` — DOL SHA-256
`1bd2bcf3f361e6482c888a523d45ea2fa2dc073f41918ebfab7803b1177343f2` — **executed on hardware
2026-09-15** (log sha256 `e7ec3d83…ea1d`, 6585 bytes; see "Result" below).

**Question:** after the CONTROL transform validated by GBP-INIT-001
(`(v & ~0x10) | 0x0C`, GBI layout), is a PI HSP interrupt (IRQ 26) observed within a
bounded window once the PI mask is opened, and what does INTSR do around the
handler's write-1-to-clear, after re-masking, and after CONTROL is restored?

No functional meaning is assigned to CONTROL bits 0x04/0x08/0x10, to IRQ-register
bit 15, or to the physical level/edge nature of the line (U-GBP-022).

## Provenance and rules

Reference order followed: GBI's — CONTROL transform → `IRQ_Request(26)` →
`__UnmaskIrq(0x20)` (docs/protocol/INITIALIZATION.md §3, GBP-IRQ-003). GBI is an
independent mature implementation, not Nintendo software; the official Start-up
Disc unmasks *before* programming the device and is not what this probe
reproduces (§8.3). The handler is Open-GBP's own one-shot, self-masking handler
(`src/gbp/gbp_irq_oneshot.h`), not GBI's thread signal. Rules R1–R8 of
INITIALIZATION.md §9 bind the implementation; the mock proves the order.

There is **no idle-unmask stage**: the first (and only) unmask happens after the
transform, with the handler installed and the masked snapshot taken.

## Sequence

```text
ARINFO     read original → bits 3-5 := 3 → readback (both references do this before the handshake)
DET        TEST handshake (C3,3C,FF,00); verdict must be PRESENT (both criteria, all patterns,
           all transfers) else ABORT — no handler, no CONTROL write, no unmask
PRE        read INTSR/INTMR; require INTSR bit 13 == 0 and INTMR bit 13 == 0, else ABORT
           (never masked or acknowledged silently: a different initial state is a different experiment)
S0         INTSR/INTMR, CONTROL raw, IRQ raw, TEST raw; v = GBI majority vote, cross-checked with
           byte 0x1F (disagreement → ABORT); shape (v & 0x10) != 0 and (v & 0x0C) == 0 else ABORT
IRQ        old = irq_install (libogc2 IRQ_Request(IRQ_PI_HSP, handler)); old kept verbatim, NULL or not
EXP        CONTROL := (v & ~0x10) | 0x0C, byte replicated ×32; raw block logged
S1         INTSR/INTMR, CONTROL raw, IRQ raw — IRQ 26 still masked
UNMASK     PI read; t_unmask = time base; __UnmaskIrq(IM_PI_HSP); PI read; (no formatting in between)
WAIT       until the handler fired or T_MAX = 2000 ms (operational bound, not a GBP property)
MASK       __MaskIrq(IM_PI_HSP) (idempotent with the handler's own mask); copy the handler record
S2         INTSR sampled twice, INTMR, CONTROL raw, IRQ raw
RESTORE    CONTROL := v (original semantic value, same layout) → S3
CLEANUP    if INTSR bit 13 is still set while masked: one INTSR := 0x2000, re-read (never a loop)
IRQ        previous handler back (IRQ_Request(26, old)); mask state verified (expected: masked)
ARINFO     original value back → readback → S4 (INTSR/INTMR, CONTROL raw, IRQ raw)
```

Handler (entry order = code order, `src/gbp/gbp_irq_oneshot.h`): time base →
INTSR → INTMR → count++ → **`__MaskIrq(IM_PI_HSP)`** → **INTSR := 0x2000** → INTSR →
INTMR → first-entry fields stored → `fired = 1` → return. A second entry re-masks,
re-acknowledges once, keeps its view; the main loop reports `reentry=1`. Nothing in
the handler allocates, blocks, formats, logs, performs DMA or touches the GBP.

Fail-safe: every abort path runs the same idempotent teardown (mask → CONTROL →
PI → single cleanup W1C if needed → handler → mask check → AR_INFO → S4) driven by the
flags `arinfo_changed / handler_installed / control_written / irq_unmasked /
pi_ack_performed`; every DMA has the backend's 200 ms timeout and busy refusal; the
screen and the X/START loop are reached only after the teardown, so no SD I/O
happens while the interrupt path is engaged.

## Writes and read-only registers

| Side | Written | Read only |
|------|---------|-----------|
| GameCube | `0xCC005012` bits 3–5 (restored); INTMR bit 13 only through `__UnmaskIrq`/`__MaskIrq` (never a direct write); INTSR := 0x2000 in the handler and, at most once more, in the cleanup | DSP CSR |
| GBP | TEST (detection handshake only); CONTROL twice: experimental value, then original value | IRQ block (S0–S4), TEST (S0) |
| Not touched | GBP IRQ register (**never written, even after an interrupt**), KEYPAD, VIDEO, AUDIO, SIOCTL, SIODATA | |

## Result codes

Experimental result (`status=`): `ok_irq_observed`, `timeout_no_irq_observed` ("no
IRQ 26 observed within T_MAX", nothing more), `abort_arinfo`, `abort_not_present`,
`abort_pi_precondition` (`pi_unavailable` / `intmr13_unmasked` / `intsr13_set`),
`abort_control_read`, `abort_control_shape`, `abort_handler_install`
(`irq_ops_unavailable` / `install_failed`), `abort_unmask`, `transport_error`.
Restore result, separate (`restore=ok|error restore_reason=`): `mask_failed`,
`control_restore_failed`, `handler_restore_failed`, `mask_not_restored`,
`arinfo_restore_failed`.

## Log records

`IDENT`, `ENV … t_max_ms=`, `INITIRQ start`, `ARINFO orig/exp/restore`, `TESTW/TESTR
tag=DET`, `DET verdict=`, `PI tag=PRE`, `PRECOND …`, `SNAP tag=Sn ticks= since_write=
since_unmask=`, `PI tag=Sn`, `PI tag=S2b`, `RAW Sn idx=4 … sem_vote= sem_b1f=`, `RAW Sn
idx=d … sem_disc= sem_gbi=`, `RAW S0 idx=0`, `CONTROL semantic`, `IRQ install rc=
old_handler=null|nonnull`, `CTLW tag=EXP|RESTORE … layout=gbi-replicated data=`, `PI
tag=UNMASKPRE`, `UNMASK t_unmask= rc= t_post= dt_post=`, `PI tag=UNMASKPOST … fired=`, `IRQ
mask tag=MAIN|TEARDOWN|RETRY rc=`, `WAIT fired= timed_out= polls= wait_ticks= wait_us=
t_max_ms=`, `HANDLER fired= count= t_entry= t_unmask= latency_ticks= latency_us= reentry=`,
`HANDLERPI intsr_before_ack= intmr_at_entry= intsr_after_ack= intmr_after_mask=
reentry_intsr= reentry_intmr=`, `CONTROL restore … ok=`, `PI tag=CLEANUPCHK|CLEANUP`,
`CLEANUP performed= …`, `IRQ restore rc= ok=`, `PI tag=MASKCHK`, `MASK final intmr=
intmr13= ok=`, `FINAL arinfo= …`, `INITIRQ end status= reason= restore= …`, `STATS`. Raw
blocks are never replaced by interpretations. The handler writes nothing textual;
its record is turned into `HANDLER`/`HANDLERPI` lines by the main loop after the
re-mask. Saved on X to `sd:/open-gbp/GBP-INIT-002_initirq-0001.log`; dumped over USB
Gecko as `OPENGBP-INITIRQ LOG …`, summarized as `OPENGBP-INITIRQ DONE …`.

## Validation

`make test` — C: `tests/unit/test_gbp_init_irq.c` (494 checks) against the mock's
**synthetic** interrupt model: present with no IRQ, IRQ at the unmask, IRQ after N
ticks, IRQ just past T_MAX, W1C that clears / does not clear INTSR, second entry
despite the mask, mask ignored (storm cap), absent `C1`, inconsistent, transport
failure in the handshake, INTSR bit 13 set / INTMR bit 13 unmasked / PI unavailable,
CONTROL shapes (0x80, 0x9C, Dolphin's 0x03, ambiguous, read failure), previous handler
NULL / non-NULL, install failure, transport without IRQ ops, failures at the EXP
write / S1 / S2, CONTROL restore ignored, handler restore failure, unmask
ineffective, ring overflow, line-length regression with a wrapping time base, the
mock's inversion detector driven by hand, and event-order assertions (handler <
CONTROL write < unmask; re-mask before handler removal; AR_INFO after the IRQ
teardown; mask before W1C inside the handler; no DMA while unmasked; GBP IRQ,
KEYPAD, VIDEO, AUDIO, SIO never touched; INTMR never written directly). Physical
fixtures (init-0001): the attached fixture drives the gate, S0 and the
preconditions and stops at the handler install (a replay has no interrupt path)
without any write; the removed fixture aborts ABSENT verbatim. The initirq-0001
fixture (this probe's own physical run, 92 further checks) replays the whole
sequence with the console's time base and the interrupt path as it happened: no
interrupt occurred, so none is replayed or invented.

`make initirq-audit` — disassembles `hsp_backend_oneshot_isr` from the linked object
and checks it calls only `__MaskIrq`, reads the time base and the PI registers, has
no indirect call, and stores 0x2000 only after the mask (`tools/isr_audit.py`).

`make initirq-dolphin` — no HSP device → `abort_not_present`; Dolphin GBPlayer model →
`abort_control_shape` (its idle CONTROL is 0x03). Neither run reaches the handler;
preconditions are not weakened for Dolphin, and Dolphin proves nothing about the
physical bits.

## Physical procedure (to be requested only from a clean build)

Same configuration as GBP-INIT-001: GBP attached, no Game Pak, Link Port empty, no
PicoAdapterGB, BBA attached without cable, one controller, one Memory Card, SD2SP2,
Swiss. Steps: launch, wait for the summary (the experiment itself lasts at most
about 2 s plus the DMAs), photograph, X to save, START to exit, return
`/open-gbp/GBP-INIT-002_initirq-0001.log`, then **power-cycle the console** (the
GBP IRQ register is never acknowledged on the device side, U-GBP-023). Success = a
clean, restorable observation, whatever fired or did not.

## Divergence from the design text

The written design lists "presence gate, then AR_INFO"; this implementation sets
AR_INFO bits 3–5 before the handshake, exactly as GBP-INIT-001 did and as both
references do (Start-up Disc `0x80089b60` before `0x8008ae3c`; GBI `0x8001123c` before
`0x80011c94`). Both prerequisites still hold before anything experimental happens,
the ABSENT path restores AR_INFO, and the physical init-0001 fixtures replay
verbatim through the gate.

## Result (2026-09-15)

`status=timeout_no_irq_observed reason=no_irq26_within_t_max restore=ok`
— not an error: no IRQ 26 within the 2000 ms bound. PRESENT 4/4 (both
criteria); handler installed (previous NULL) and restored; CONTROL `0x90
→ 0x8C → 0x90`; `__UnmaskIrq` physically set INTMR bit 13 (`0x1FA →
0x21FA`) and `__MaskIrq` cleared it; INTSR bit 13 never set; handler never
entered; wait 81000012 ticks = 2.0000003 s; IRQ register `0x8AAE` (S0, S1)
→ `0x8FAE` (S2, S3: bits 0x0400/0x0100 set under their masks) while
CONTROL stayed `0x8C`, persisting after the CONTROL restore; S4 under the
original AR_INFO `00` / `9090`; cleanup not needed; 21 transfers, 0
errors. Evidence GBP-HW-021…026, GBP-IRQ-004/005; analysis and the next
experiment (an authorized write of the GBP IRQ register, which both
references perform before waiting) in DEVLOG 2026-09-15. The fixture
`captures/fixtures/hw-gamecube-gbp-2026-09-15-initirq-0001.gbpreplay`
replays the whole run, physical time base included
(`tests/unit/test_gbp_init_irq.c`, `tests/host/test_hw_fixture.py`).
