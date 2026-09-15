# High Speed Port (HSP) — what GameCube software sees

The HSP is the connector on the underside of the GameCube used by the
Game Boy Player. YAGCD lists it as a PI interrupt source (bit 13) with
"3 sources: TX mailbox, RX mailbox, ID" (6.2.1) and, in chapter 11, notes
that HSP devices "seem to be accessable through the ARAM interface with
offsets beyond 16MB". Phase 2 confirmed the second statement from three
independent code bases and found no software that uses anything like
mailboxes.

## 1. Access mechanism

The GBS-DOL is reached through the ARAM DMA engine of the DSP interface.
The relevant GameCube registers (all 16-bit, big-endian, at `0xCC005xxx`):

| Address | Bits | Role | Source |
|---------|------|------|--------|
| `0x500A` | 9 | ARAM DMA in progress | DISC `0x80089c1c`; Dolphin `DSPCR` |
| `0x500A` | 5 | ARAM DMA complete interrupt flag; write 1 to clear | DISC `0x80089cc8`; libogc `__ARHandler`; YAGCD 6.2.8 |
| `0x5012` | 0–2 | internal ARAM size code (0 = 2 MB … 3 = 16 MB, 4 = 32 MB) | libogc2 `__ARCheckSize`; DISC `0x80089aac` |
| `0x5012` | 3–5 | expansion ARAM size code; **set to 3 before GBP use** | DISC `0x80089b60`; GBI `0x8001123c` (`\|= 0x18`) |
| `0x5020/22` | | main-memory address (bits 25–16 / 15–5) | libogc `AR_StartDMA`; DISC `0x80089c3c` |
| `0x5024/26` | | ARAM address | idem |
| `0x5028/2A` | 15 of high half | direction: 0 = main→ARAM (write), 1 = ARAM→main (read); rest = length | idem, YAGCD |

A GBP register access is one DMA of 32·n bytes whose ARAM address is
`internal_size + (index << 20) + offset`. Dolphin implements exactly
this: `Do_ARAM_DMA` forwards any transfer with `ARAddr >= aram.size` (after
masking to 64 MB) to the HSP device in 32-byte chunks
(`Source/Core/Core/HW/DSP.cpp`, `HSP_Device.h TRANSFER_SIZE = 32`).

### Why the expansion size code matters (hypothesis)

libogc's `__ARCheckSize` normally probes for expansion ARAM by DMAing
test patterns to `internal_size + 0`; with a GBP attached those probes
land on the inverting TEST register, the readback differs, and libogc
concludes "no expansion" and leaves bits 3–5 at 0. Both DISC and GBI then
explicitly write code 3. Dolphin routes to the HSP regardless of these
bits. **H (U-GBP-004):** on hardware the SDRAM controller may only
forward DMA beyond the internal size to the HSP when an expansion size
is programmed. Phase 3 should test the TEST handshake with and without
this write (read-only on the GBP side; the write is to a GameCube
register).

## 2. Interrupt

| Item | Value | Source |
|------|-------|--------|
| PI cause / mask bit | 13 (`0x2000`) in `0xCC003000` (INTSR, cause) / `0xCC003004` (INTMR, mask) | YAGCD PI section, libogc `irq.c`, Dolphin `INT_CAUSE_HSP`, DISC dispatcher `0x80069ff0`, GBI dispatcher `0x80058360` |
| OS interrupt number | 26 in the Nintendo SDK (DISC `OSSetInterruptHandler(26, …)`, software mask `0x20`) and in libogc (`IRQ_PI_HSP = 26`, `IM_PI_HSP = 0x20`) | DISC `0x8008a930`/`0x80069ca0`, GBI `0x8000bf30`, libogc2 `irq.h`/`irq.c` |
| Cause vs mask | INTSR shows the cause independently of INTMR; INTMR only gates the CPU exception — **C** (GBP-PI-001) | all three dispatchers test `cause & mask`; the Disc acknowledges while masked; Dolphin model |
| Clearing INTSR | write 1 to clear — **C** (GBP-PI-002); every known INTSR write is a single-source acknowledge (2, 0x1000, 0x2000) | libogc2 `system.c`/`mmce.c`, DISC `0x8006b1d4`/`0x800a243c`/`0x8008af08`/`0x8008be04`, GBI `0x80052f04`/`0x80053eb0`/`0x8000b400`, Dolphin `cause &= ~val` |
| Mask/unmask through libogc2 on hardware | `__UnmaskIrq(IM_PI_HSP)` set INTMR bit 13 (`0x1FA → 0x21FA`), `__MaskIrq` cleared it, other bits unchanged — **F** (GBP-INIT-002, 2026-09-15); not extrapolated to other PI interrupts | GBP-HW-022 |
| Level or latched at the PI | **U** (U-GBP-022): never observed set on hardware (2 s unmasked window with the GBS-DOL's own IRQ masks left set produced no cause); no reference reads INTSR | GBP-HW-023 |
| Device-side IRQ register | 16-bit: even bits = sources (audio 0x0400, video 0x0100, serial 0x0040, sleep 0x0010, …), odd bits = paired masks, bit 15 = global flag; idle reads 0x8AAE (all masks + bit 15 set); both references write it before waiting for interrupts (Disc: computed mask word at start; GBI: `read \| 0x8000` then `0` in an unprompted first pass) — **C** for the pairing, **H** for the polarity | GBP-IRQ-004/005, GBP-HW-024 |
| Acknowledge order, Start-up Disc | device IRQ write (`mask \| 0x8000`) → `INTSR := 0x2000` → device IRQ read → device write-back (`pending`) → … → device re-arm (`mask`): **GBP → PI → GBP → GBP** (F, GBP-IRQ-002) | DISC `0x8008af08` |
| Acknowledge order, GBI | `INTSR := 0x2000` in the raw handler, device write (`pending \| 0x8000`, with KEYPAD) later in a thread: **PI → GBP** (F, GBP-IRQ-003) | GBI `0x8000b400`, `0x8000bf30` |
| Device-side gating | CONTROL bit `0x10`: set by both references at stop, cleared at start (Dolphin: `set_interrupt = !(control & 0x10) && (irq & 0x8000)`) | DISC/GBI usage, Dolphin |
| libogc2 dispatch (r2442.094b250, verified in the linked binary) | reads INTSR and INTMR, `cause & mask`, one handler per exception by priority, EE = 0 in the handler, `rfi`; no automatic mask, no automatic acknowledge; INTMR is rebuilt from shadow masks by `__MaskIrq`/`__UnmaskIrq` (never write it directly) | ENV-IRQ-001/002 |
| Retrigger / storm | a handler returning with `INTSR & INTMR` bit 13 still set re-enters immediately after `rfi`; so does an unmasked bit 13 with no handler. Ended with certainty only by clearing INTMR bit 13 inside the handler (GBP-PI-003) | PowerPC + libogc2/SDK dispatchers |

The two references disagree on the order of the PI and device
acknowledges but agree on the rest: PI is acknowledged by W1C, the
device register is written back with the value read, CONTROL is read
and KEYPAD written on every interrupt, at stop PI is masked before the
device is touched, and — decisively — both program the device's IRQ
register before waiting for an interrupt. GBP-INIT-002 (2026-09-15)
reproduced everything except that programming and saw no interrupt in
2 s while the register showed the audio/video source bits set under
their masks (GBP-HW-023/024). Nothing about the physical line (level vs
edge, assertion duration, effect of the W1C while asserted) has been
observed; the Dolphin model (cause re-set on every device event, cleared
on W1C, masks ignored) predicted an interrupt the hardware did not
produce. Open-GBP's handler rules are in `docs/protocol/INITIALIZATION.md`
§9; the register model in §10.

## 3. Bandwidth and timing (orientation)

- Dolphin's DMA model uses 246 ticks per 32 bytes ("measured on real hw",
  `DSP.cpp`), i.e. about 63 MB/s at 486 MHz. The GBP's demand under the
  Dolphin timing model is modest: VIDEO 0xF00 bytes × 40 blocks × ~60
  frames/s ≈ 9.2 MB/s, AUDIO 0x1000 bytes × 4096 blocks/s ≈ 16.8 MB/s.
  Model numbers, not measurements (**H**, U-GBP-014).
- DISC waits for each register DMA synchronously with interrupts disabled
  and a 1 s timeout; GBI queues them through libogc ARQ (chunk size 0x3C0)
  and processes IRQs in a thread.

## 4. Differences between the Dolphin model and the two real drivers

| Topic | Dolphin | DISC / GBI |
|-------|---------|------------|
| `0xCC005012` bits 3–5 | ignored | written (3) |
| Register mirror inside the 1 MB window | any offset (`addr >> 20`) | GBI relies on `0xFFFE0` offset working |
| IRQ 16-bit read layout | `hh hh hh ll` | DISC reads bytes 0x1D/0x1F only |
| SIODATA read layout | u32 repeated 8× | DISC assembles bytes 0x19/0x1B/0x1D/0x1F (byte-doubled model) |
| SIOCTL / SIODATA behavior | stubs (log only) | real state machine (DISC), queue (GBI) |
| Unknown indices | warning | never touched |
| PI HSP cause | re-set on every device event, cleared on INTSR W1C; `irq & 0x8000` with CONTROL 0x10 clear asserts the line | not observable in the references (INTSR never read); hardware idle IRQ read `0x8AAE` (bit 15 set) with CONTROL 0x10 cleared for 228 µs showed no INTSR bit 13 (GBP-HW-013/014) — the model's assertion condition did not reproduce in that window; level/edge U (U-GBP-022) |

None of these differences is a Dolphin bug for the purpose of running
the DISC or GBI; they mark where Dolphin is *not* evidence.
