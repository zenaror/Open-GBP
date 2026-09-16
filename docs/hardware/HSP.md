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
| Cause vs mask | INTSR shows the cause independently of INTMR; INTMR only gates the CPU exception — **F** for bit 13 (GBP-PI-004: bit 13 read 1 with INTMR bit 13 = 0 and no exception, GBP-INIT-003A; GBP-PI-005: the same latched cause was delivered to the IRQ 26 handler as soon as INTMR bit 13 was opened, GBP-INIT-003B 2026-09-15); C for the other sources (GBP-PI-001) | all three dispatchers test `cause & mask`; the Disc acknowledges while masked; Dolphin model; hardware GBP-HW-030/037 |
| Clearing INTSR | write 1 to clear — **F** for bit 13 (one `INTSR := 0x2000` cleared a latched cause after the device sources were gone, GBP-HW-033, and one written from inside the handler cleared it while both device sources were still pending, with no re-assert for ≥ 324 µs, GBP-HW-038); C for the other sources (GBP-PI-002); every known INTSR write is a single-source acknowledge (2, 0x1000, 0x2000) | libogc2 `system.c`/`mmce.c`, DISC `0x8006b1d4`/`0x800a243c`/`0x8008af08`/`0x8008be04`, GBI `0x80052f04`/`0x80053eb0`/`0x8000b400`, Dolphin `cause &= ~val`, hardware GBP-HW-033/038 |
| Mask/unmask through libogc2 on hardware | `__UnmaskIrq(IM_PI_HSP)` set INTMR bit 13 (`0x1FA → 0x21FA`), `__MaskIrq` cleared it, other bits unchanged — **F** (GBP-INIT-002, 2026-09-15); with a cause already latched, `__UnmaskIrq` delivered IRQ 26 **inside the call** (the handler's time base lies between the reads before and after it) and `__MaskIrq` from inside the handler closed the mask (INTMR `0x21FA` at entry → `0x1FA`) — **F** (GBP-INIT-003B, GBP-HW-037, ENV-IRQ-003); not extrapolated to other PI interrupts | GBP-HW-022/037 |
| Level or latched at the PI | **Latched at the PI — F** (GBP-HW-033): bit 13 stayed set after the device-side sources had been cleared and was cleared only by the W1C. **W1C while the device still asserts — F** (GBP-HW-038): the handler's W1C cleared bit 13 with both sources pending (odd bits 0, bit 15 = 0, CONTROL 0x8C) and it stayed clear ≥ 179.7 µs before the device ACK, ≥ 323.9 µs overall. The simple sustained-level model of the device line is **rejected**; pulse / edge / transient / separate deassert remain **U** (U-GBP-022, P2) | GBP-INIT-003A/003B 2026-09-15 |
| Delivery latency | 78 ticks ≈ 1.93 µs (GBP-INIT-003B, one-shot handler) and 89 ticks ≈ 2.20 µs (GBP-INIT-004, multi-cycle handler) from the time-base read before `__UnmaskIrq` to the handler's first read — two observations of this software and toolchain, **not a hardware specification** | GBP-HW-037, GBP-HW-043 |
| Device-side IRQ register | 16-bit: even bits = sources (audio 0x0400, video 0x0100, game-pak/stop 0x0004, serial 0x0040, sleep 0x0010, …), write-1-to-clear (**F** for bits 2, 8, 10 — cleared by A1, by the stop word twice and by the 003B acknowledge `read \| 0x8000` while pending); odd bits = paired masks, level-written (**F**), 1 = masked / 0 = enabled (**C**); bit 15 level-writable and persistent both ways (**F**: A2 → 0, stop → 1, ACK → 1), function **H** (global hold, never isolated); idle reads 0x8AAE; both references write it before waiting for interrupts (Disc: computed mask word at start; GBI: `read \| 0x8000` then `0` in an unprompted first pass) — with the GBI pair of writes applied and PI masked, the first 0x0400 source raised the PI cause ≈105.28 ms after the second write in two runs (GBP-HW-030/035), 0x0100 followed within 1 ms, and after the 003B acknowledge both sources were set again within ≈143 µs (GBP-HW-040) | GBP-IRQ-004/005/007/008, GBP-HW-024/028…040 |
| Acknowledge order, Start-up Disc | device IRQ write (`mask \| 0x8000`) → `INTSR := 0x2000` → device IRQ read → device write-back (`pending`) → … → device re-arm (`mask`): **GBP → PI → GBP → GBP** (F, GBP-IRQ-002) | DISC `0x8008af08` |
| Acknowledge order, GBI | `INTSR := 0x2000` in the raw handler, device write (`pending \| 0x8000`, with KEYPAD) later in a thread: **PI → GBP** (F, GBP-IRQ-003) | GBI `0x8000b400`, `0x8000bf30` |
| Device-side gating | CONTROL bit `0x10`: set by both references at stop, cleared at start (Dolphin: `set_interrupt = !(control & 0x10) && (irq & 0x8000)`) | DISC/GBI usage, Dolphin |
| libogc2 dispatch (r2442.094b250, verified in the linked binary) | reads INTSR and INTMR, `cause & mask`, one handler per exception by priority, EE = 0 in the handler, `rfi`; no automatic mask, no automatic acknowledge; INTMR is rebuilt from shadow masks by `__MaskIrq`/`__UnmaskIrq` (never write it directly) | ENV-IRQ-001/002 |
| Retrigger / storm | a handler returning with `INTSR & INTMR` bit 13 still set re-enters immediately after `rfi`; so does an unmasked bit 13 with no handler. Ended with certainty only by clearing INTMR bit 13 inside the handler (GBP-PI-003). **Hardware:** the mask-first one-shot handler of GBP-INIT-003B was entered once and returned; no reentry, no storm (GBP-HW-037) | PowerPC + libogc2/SDK dispatchers; GBP-INIT-003B |

The two references disagree on the order of the PI and device
acknowledges but agree on the rest: PI is acknowledged by W1C, the
device register is written back with the value read, CONTROL is read
and KEYPAD written on every interrupt, at stop PI is masked before the
device is touched, and — decisively — both program the device's IRQ
register before waiting for an interrupt. GBP-INIT-002 (2026-09-15)
reproduced everything except that programming and saw no interrupt in
2 s while the register showed the audio/video source bits set under
their masks (GBP-HW-023/024). GBP-INIT-003A (2026-09-15) then applied
GBI's two first-pass writes with PI masked: the acknowledge cleared the
pending source bit, the zero write cleared the masks and bit 15, and the
next audio source raised PI INTSR bit 13 ≈105 ms later while INTMR kept
it from the CPU; the Start-up Disc's stop word cleared the sources and
re-armed the masks, and one W1C cleared the latched PI cause
(GBP-HW-028…033). GBP-INIT-003B (2026-09-15) then installed a handler
after such a latched cause and unmasked once: the cause was delivered as
IRQ 26 inside `__UnmaskIrq`, the handler masked first, wrote one W1C
while both device sources were still pending and the PI bit stayed clear
(the sustained-level model is out; the line's exact nature is still
open), the main loop acknowledged the device with `read | 0x8000` (sources
cleared, bit 15 = 1) and the Disc's stop word closed the run
(GBP-HW-035…041, GBP-PI-005). GBP-INIT-004 (2026-09-16) repeated the cycle
through a multi-cycle handler (second delivery, 89 ticks) and, 26 µs after
its acknowledge, read the audio source set again under bit 15 = 1 with
CONTROL 0x8C and the PI cause clear; its conservative rule "sources must
read 0 before a re-arm" ended the run there — a rule neither reference
applies: both drain the AUDIO/VIDEO block and re-arm without reading the
register (GBP-HW-042…047, GBP-IRQ-009, INITIALIZATION.md §13). Still not
exercised: GBI's re-arm `IRQ := 0` after the acknowledge and repeated
service (U-GBP-027; next experiment GBP-AV-SERVICE-001, a drained service —
AUDIO 0x1000 then VIDEO 0xF00, one whole-block DMA each, as both references
— followed by the re-arm; GBP-INIT-004B, a re-arm with the source pending,
is optional). The Dolphin model
(cause re-set on every device event, masks ignored, line asserted only
with bit 15 = 1) predicted an interrupt the hardware did not produce in
INIT-002 and asserts on a condition (bit 15 = 1) the hardware contradicted
in 003A and 003B. Open-GBP's handler rules are in
`docs/protocol/INITIALIZATION.md` §9; the register model in §10/§11/§12.

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
| PI HSP cause | re-set on every device event, cleared on INTSR W1C; `irq & 0x8000` with CONTROL 0x10 clear asserts the line | hardware: the cause is latched at the PI and cleared by W1C (agrees, GBP-HW-033/038); it rose with bit 15 = 0 and the odd bits = 0 (GBP-HW-030/035) and did not rise in 2 s with bit 15 = 1 and the odd bits = 1 (GBP-HW-023) — the model's assertion condition is not the hardware's; delivery to the CPU on unmask agrees (GBP-HW-037); after the handler's W1C the hardware showed no re-assert with the sources pending (GBP-HW-038); the device line itself (pulse / edge / transient / separate deassert) is still U (U-GBP-022) |

None of these differences is a Dolphin bug for the purpose of running
the DISC or GBI; they mark where Dolphin is *not* evidence.
