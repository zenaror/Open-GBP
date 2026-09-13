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
| PI cause / mask bit | 13 (`0x2000`) in `0xCC003000` / `0xCC003004` | YAGCD 6.1.5.2, libogc `irq.c`, Dolphin `INT_CAUSE_HSP`, DISC dispatcher `0x80069ff0` |
| OS interrupt number | 26 in the Nintendo SDK (DISC `OSSetInterruptHandler(26, …)`) and in libogc (`IRQ_PI_HSP = 26`) | DISC `0x8008a930`, GBI `0x8000bf30` |
| Acknowledge | write `0x2000` to `0xCC003000` *after* clearing the device-side IRQ register (DISC) or immediately in the raw handler (GBI) | DISC `0x8008af08`, GBI `0x8000b400` |
| Device-side gating | CONTROL bit `0x10` masks the line (Dolphin: `set_interrupt = !(control & 0x10) && (irq & 0x8000)`) | DISC/GBI usage, Dolphin |

The line is level-like from the software's point of view: DISC masks it
at the device (IRQ register bit 15 + CONTROL 0x10) before servicing and
re-enables afterwards. Whether it is edge or level at the PI is **U**.

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

None of these differences is a Dolphin bug for the purpose of running
the DISC or GBI; they mark where Dolphin is *not* evidence.
