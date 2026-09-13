# Game Boy Player — System Architecture

Consolidated description of how the physical Game Boy Player (DOL-017,
board DOL-GBS) attaches to the GameCube and how GameCube software reaches
it. Every statement carries an evidence id from `docs/research/EVIDENCE.md`;
statements without an id are context only.

Status legend: **F** fact, **C** corroborated, **H** hypothesis, **U** unknown.

## 1. Physical topology

```text
┌──────────────────────────────────────────────────────────────┐
│ GameCube (DOL-001)                                           │
│                                                              │
│  Gekko CPU ── Flipper ── ARAM / SDRAM controller ──┐         │
│                 │  PI interrupt bit 13 "HSP"       │         │
│                 └──────────────────────────────────┼─ HSP ── │  bottom connector
└────────────────────────────────────────────────────┼─────────┘  ("High Speed Port",
                                                     │             serial port 3 area)
┌────────────────────────────────────────────────────┼─────────┐
│ Game Boy Player (DOL-017, board DOL-GBS-01/10/20)  │         │
│                                                    ▼         │
│   GBS-DOL (NEC custom bridge) ◄──────────────► CPU AGB A     │
│        ▲  video / audio / keypad / IRQ / SIO        │ (stock GBA SoC)
│        │                                            ├── work RAM (16 Mb or 128 Mb chip)
│        │                                            ├── Link Port (external, physical)
│        └── 32-byte DMA "register" window            └── Game Pak slot (GB/GBC/GBA)
└──────────────────────────────────────────────────────────────┘
```

| Claim | Status | Evidence |
|-------|--------|----------|
| The GBP contains a stock **CPU AGB A** (one unit with CPU AGB A E) plus an NEC custom **GBS-DOL** that bridges the HSP to the AGB signals | C | GBP-PHY-001 (gbpp article + gbhwdb) |
| Three known board revisions: DOL-GBS-01, -10, -20; RAM chip varies (16 Mb or 128 Mb parts from Hynix/BSI/NEC/ST); Kinseki crystal | F | GBP-PHY-001 (gbhwdb, 10 units) |
| The AGB's keypad lines, reset and the LCD vsync (SPS) are exposed on board test points (TP25 reset, TP29 vsync, TP33–42 keys) | F | GBP-PHY-002 (gbpp) |
| The AGB runs at its native 59.73 Hz; the GameCube side outputs 59.94 Hz and the GBP "adds frames where it needs to" | F (observation by endrift) | GBP-PHY-003 |
| The GBP's Link Port is the AGB's own serial port and works with external devices without GameCube involvement | F (user's PicoAdapterGB) | GBP-LINK-001 |

## 2. Logical path from the Gekko to the AGB

GameCube software never sees the AGB directly. It sees the GBS-DOL as an
**ARAM-expansion device**: the same DMA engine that moves data between
main memory and the 16 MB ARAM (registers `0xCC005020`–`0xCC00502A`)
reaches the GBS-DOL when the ARAM address is at or above the internal
ARAM size (`0x01000000`).

```text
Gekko  ──writes DMA regs──►  DSP/ARAM DMA engine  ──ARAM addr ≥ 16 MB──►  HSP  ──►  GBS-DOL
                                                                             ◄──  PI IRQ bit 13
```

| Claim | Status | Evidence |
|-------|--------|----------|
| GBP "registers" are 32-byte blocks reached by ARAM DMA at ARAM address `internal_size + (reg << 20)` (+ intra-block offset for the AV buffers) | C | GBP-HSP-001 (Startup Disc + GBI + Dolphin + YAGCD §11) |
| Before talking to the GBP, both official and GBI software set ARAM-info register `0xCC005012` bits 3–5 to `3` (expansion size code for 16 MB) | C | GBP-HSP-002 |
| Every transfer is a multiple of 32 bytes; register writes carry the value in the **last bytes** of the block, register reads replicate the value across the block | C | GBP-HSP-003 |
| The GBS-DOL raises PI interrupt bit 13 (0x2000, OS interrupt number 26 in both SDK and libogc); software acknowledges by writing 0x2000 to `0xCC003000` after clearing the device-side IRQ register | C | GBP-IRQ-001 |
| The HSP interrupt line is described by YAGCD as having 3 sources (TX mailbox, RX mailbox, ID); this project has not observed any of that | U | U-GBP-006 |

## 3. Data planes

| Plane | Direction | Mechanism | Status |
|-------|-----------|-----------|--------|
| Video | GBP → GC | 0xF00-byte DMA reads of the *video* block: 4 AGB scanlines × 240 px, one 32-bit word per pixel holding a 15-bit RGB value with each byte doubled; bit 15 of the first pixel marks the first line of a frame; a *video* IRQ (bit 8) signals each 4-line batch | C (format from Dolphin + disc buffer geometry; exact hardware word layout H) | GBP-VID-001 |
| Audio | GBP → GC | 0x1000-byte DMA reads of the *audio* block, delivered as PWM bit-streams (Dolphin: 1 bit per byte-mirrored word, ~4096 blocks/s); *audio* IRQ (bit 10) per block | H (Dolphin model + disc geometry only) | GBP-AUD-001 |
| Keypad | GC → GBP | 32-byte write to the *keypad* block; 16-bit GBA key state in bytes 0x1E–0x1F, active-low like the AGB KEYINPUT register | C | GBP-KEY-001 |
| Control/status | both | 1-byte *control* register: cartridge type/presence flags, two "power" bits used as reset/stop, IRQ mask bit, link-related bits | C for usage, H for names | GBP-CTL-001 |
| Internal SIO | both | *SIO control* (byte) and *SIO data* (32-bit) blocks plus *serial* IRQ (bit 6); used by the Startup Disc for the AGB↔GameCube protocol that carries rumble and the GBP menu | F that the path exists and is used; semantics H/U | GBP-SIO-001, U-GBP-001..003 |

## 4. What the AGB side sees (for orientation only)

On the AGB the GameCube is a **JoyBus / SIO peer**: GBATEK documents that
GBA software detects the Game Boy Player by showing the GBP logo and
watching KEYINPUT return `0x030F` for a frame, then talks to it over SIO
normal 32-bit mode with a "NINTENDO"-string handshake (rumble protocol).
Which AGB SIO mode the GBS-DOL drives internally, and how that maps onto
the GameCube-side *SIO control*/*SIO data* blocks, is **unknown**
(U-GBP-001). Do not confuse AGB registers (`0x04000128 SIOCNT`,
`0x04000134 RCNT`, `0x04000140 JOYCNT`) with the GameCube-side blocks.

## 5. Sources and where the details live

- Register map and transfer format: `docs/protocol/REGISTERS.md`
- Detection, start, stop and IRQ sequences: `docs/protocol/INITIALIZATION.md`
- HSP / DMA mechanics: `docs/hardware/HSP.md`
- GBS-DOL behavior summary: `docs/hardware/GBS-DOL.md`
- Evidence and open questions: `docs/research/EVIDENCE.md`, `docs/research/UNKNOWNS.md`
