# poc/gbp-init-probe — GBP-INIT-001

**Test ID:** `GBP-INIT-001` — **Build ID:** `init-0001` — commit `a3d9668` — DOL SHA-256
`6068d1348792928b179bdd054bd2ce013fe5e0b7b25c8da7ac781c5f43b2a1e5` — executed on hardware 2026-09-15 (attached and removed)

**Hypothesis (single variable):** applying GBI's CONTROL transform
`(v & ~0x10) | 0x0C` to the semantic CONTROL value read at runtime, while
the PI HSP interrupt (bit 13) stays masked, produces which observable
changes in CONTROL, in the IRQ block and in PI INTSR?

No functional meaning is assigned to bits 0x04, 0x08 or 0x10 here.

## Provenance of the operation

```text
Selected reference for experiment:
GBI Standard control-write semantics

Reason:
write occurs before PI IRQ unmask,
does not require GBP IRQ block writes,
uses a known working implementation,
and is more causally isolated than the Startup Disc start sequence.
```

GBI is an independent, mature implementation, **not** official Nintendo
software; the Nintendo Game Boy Player Start-up Disc remains the official
reference (its start sequence clears bit 0x10 in a separate write after
`| 0x04`, with the PI interrupt already unmasked and the IRQ block
programmed — `docs/protocol/INITIALIZATION.md` §8). This probe reproduces
only the GBI transform, in the same PI-masked regime, and **not** the
rest of GBI's start (`IRQ_Request(26)` / `__UnmaskIrq(0x20)` are not
executed). GBI also writes `KEYPAD := 0` right before; static analysis
shows no dependency between that write and the CONTROL value (separate
ARQ transfers, the value comes only from the CONTROL read), so KEYPAD is
left untouched to keep one variable.

## Sequence

```text
S0 entry   identity → AR_INFO orig → bits 3-5 := 3 (readback) → TEST handshake (C3,3C,FF,00)
           verdict must be PRESENT (both criteria, all patterns, all transfers) else ABORT
PI         read INTSR/INTMR; if INTMR bit 13 is set (enabled, libogc2 polarity), clear only that
           bit and confirm by readback; else leave INTMR untouched. No handler, no unmask.
S0         INTSR/INTMR, CONTROL raw, IRQ raw, TEST raw; semantic v = GBI majority vote,
           cross-checked with byte 0x1F (disagreement → ABORT "control_ambiguous")
shape      require (v & 0x10) != 0 and (v & 0x0C) == 0 (idle shape seen on hardware) else ABORT
EXP write  CONTROL := (v & ~0x10) | 0x0C, GBI layout (byte replicated ×32); raw block logged
S1, S2, S3 INTSR/INTMR, CONTROL raw, IRQ raw — back to back, no delay (neither reference has one)
RESTORE    CONTROL := v (the ORIGINAL semantic value, same GBI layout; not an inverse expression)
S4         INTSR/INTMR, CONTROL raw, IRQ raw; control_restored = (vote == v)
restore    INTMR (only if changed) → readback; AR_INFO → readback
S5         INTSR/INTMR, CONTROL raw, IRQ raw under the restored AR_INFO
```

Fail-safe: any abort before the write restores INTMR/AR_INFO and ends;
any transfer error after the write still runs RESTORE, S4, INTMR and
AR_INFO restores; every DMA has the backend's 200 ms timeout and busy
refusal; the screen and the X/START loop are reached in every path.

## Writes and read-only registers

| Side | Written | Read only |
|------|---------|-----------|
| GameCube | `0xCC005012` bits 3–5 (restored); `0xCC003004` INTMR bit 13 only if it was set (restored) | `0xCC003000` INTSR (never acknowledged), DSP CSR |
| GBP | TEST (detection handshake only); CONTROL twice: experimental value, then original value | IRQ block (S0–S5), TEST (S0) |
| Not touched | VIDEO, AUDIO, KEYPAD, SIOCTL, SIODATA | |

## Log records

`IDENT`, `ENV`, `INIT start`, `ARINFO orig/exp/restore`, `TESTW/TESTR tag=DET`,
`DET verdict=`, `PI tag=PRE|S0..S5 intsr= intmr= intsr13= intmr13=`,
`INTMR mask|unchanged|restore`, `SNAP tag=Sn ticks= since_write=`,
`RAW Sn idx=4 … sem_vote= sem_b1f= data=`, `RAW Sn idx=d … sem_disc= sem_gbi= data=`,
`RAW S0 idx=0 … data=`, `CONTROL semantic orig= exp= method= transform=`,
`CTLW tag=EXP|RESTORE addr= semantic= rc= … layout=gbi-replicated data=`,
`TRANSITION s1_s2=`, `CONTROL restore … ok=`, `INIT end status= reason= …`,
`STATS`. Raw blocks are never replaced by interpretations. Saved on X to
`sd:/open-gbp/GBP-INIT-001_init-0001.log`; also dumped over USB Gecko as
`OPENGBP-INIT LOG …` and summarized as `OPENGBP-INIT DONE …`.

## Validation

`make test` (C: `test_gbp_init.c` — present, absent `C0`, inconsistent,
bit 0x10 set/clear, bits 0x0C set, byte-0 anomaly `94 90…`, ambiguous
read, INTMR masked/unmasked/unmaskable, PI unreadable, INTSR bit 13
set, timeouts before/at/after the write, restore ignored, ring overflow,
truncation; replay scripts built from the physical MODE B handshakes —
no-GBP bytes never reach the CONTROL write), `make init-dolphin` (no HSP
device → `abort_not_present`, Dolphin GBPlayer model → full sequence and
restore; Dolphin proves nothing about the physical bits).

## Physical procedure (to be requested only from a clean build)

Same configuration as the two previous runs: GBP attached, no Game Pak,
Link Port empty, no PicoAdapterGB, BBA attached without cable, one
controller, one Memory Card, SD2SP2, Swiss. Steps: launch, wait for the
summary, photograph, X to save, START to exit, return
`/open-gbp/GBP-INIT-001_init-0001.log`. Success = a clean, restorable
observation, whatever changed or did not.

## Result (2026-09-15)

Attached: PRESENT (4/4 both criteria), `CONTROL 0x90 → 0x8C → 0x90`
accepted and restored, IRQ bytes 1–31 `0x8AAE` throughout, PI INTSR bit
13 = 0 in S0–S5 with INTMR untouched (`0x1FA`), transient bit 6 in byte
0 of CONTROL and IRQ after each CONTROL write, S5 under expansion code 0
read `00`/`9090`; 23 transfers, 0 errors. Removed: `C1`×32, ABSENT, no
CONTROL write, AR_INFO restored. Logs, facts and analysis:
`docs/research/HARDWARE_TESTS.md`, `EVIDENCE.md` GBP-HW-011…020, DEVLOG
2026-09-15; `tools/blockdiff.py --snapshots <log>` reproduces the
timing/bit table.
