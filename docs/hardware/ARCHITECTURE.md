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
| Three known board revisions: DOL-GBS-01, -10, -20; RAM chip varies (16 Mb or 128 Mb parts from Hynix/BSI/NEC/ST); Kinseki crystal | C | GBP-PHY-001 (gbhwdb, 10 units; no hardware test by this project). This row read F until Issue #96, more than the entry's CORROBORATED |
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
| The GBS-DOL raises PI interrupt cause bit 13 (`0xCC003000` bit 13 = 0x2000; mask `0xCC003004` bit 13; OS interrupt number 26 = software mask 0x20 in both SDK and libogc). PI is acknowledged by writing 0x2000 (W1C); the Start-up Disc writes the device-side IRQ register first and then PI (GBP → PI → GBP → GBP), GBI writes PI first in its raw handler and the device register later in a thread (PI → GBP). The cause is visible independently of the mask; whether the line is level or latched at the PI is unknown | C (F for the two orders) | GBP-IRQ-001/002/003, GBP-PI-001/002/003, U-GBP-022 |
| The HSP interrupt line is described by YAGCD as having 3 sources (TX mailbox, RX mailbox, ID); this project has not observed any of that | U | U-GBP-006 |

## 3. Data planes

| Plane | Direction | Mechanism | Status |
|-------|-----------|-----------|--------|
| Video | GBP → GC | 0xF00-byte DMA reads of the *video* block: 4 AGB scanlines × 240 px, one 32-bit word per pixel holding a 15-bit RGB value with each byte doubled (the pixel is bytes 1 and 3; bytes 0 and 2 vary and are not consumed, U-GBP-029); 40 blocks per 160-line frame; bit 15 set on exactly one word per frame, the first pixel, added on the path (origin U-GBP-034); the 15 colour bits arrive with the two outer 5-bit groups exchanged relative to the AGB framebuffer, so the GX RGB5A3 reading is the displayed colour; a *video* IRQ (bit 8) signals each 4-line batch; source cadence 59.727 Hz measured (run-scoped) | F (hw): geometry reconstructed legible, 40-block composition, colour order, bit-15 count; details and every id in `../protocol/VIDEO.md` | GBP-VID-001 (references); GBP-HW-081, GBP-HW-076, GBP-HW-077, GBP-HW-131, GBP-HW-129, GBP-HW-078 |
| Audio | GBP → GC | 0x1000-byte DMA reads of the *audio* block, one per *audio* IRQ (bit 10); 4 096 blocks per second, each block one sample of the AGB's audio; inside a block the sample is the width, in bits, of a 1-bit PWM pulse over sixteen 256-byte cells; Dolphin's byte layout (0x400 bytes mirrored ×4, 1-bits leading) is refused on hardware | C (the rate, two windows of one run; the decode layout); F (hw) for the pulse structure and the 256-byte cell; Dolphin's byte layout REFUSED; history: H (Dolphin model + disc geometry only) until RUN 30 / RUN 31, 2026-09-22; details and every id in `../protocol/AUDIO.md` | GBP-AUD-001 (references); GBP-HW-301, GBP-HW-298, GBP-HW-304, GBP-HW-287, GBP-HW-296, GBP-HW-313 |
| Keypad | GC → GBP | 32-byte write to the *keypad* block; a 16-bit GBA key word in bytes 0x1E–0x1F, **1 = pressed** (the opposite polarity of the AGB's KEYINPUT, which reads 0 = pressed); bits 0–7 in KEYINPUT order, L at bit 8 and R at bit 9 (the reverse of KEYINPUT's, as every reference writes it); written by Open-GBP on hardware on 2026-09-21 and read by the cartridge as presses in five runs (RUN 14 / RUN 15 on `stream-0014`; RUN 17 / RUN 18 / RUN 16 on `stream-0015`, the word sent at each change recorded) | C (format and polarity: GBP-KEY-001, GBP-KEY-005); F (hw, run-scoped) for the mechanism; **F (hw, run-scoped) for the L/R order since 2026-09-21** — the machine join of RUN 17 / RUN 18 (the runtime's KEY record against the checker's counters) bound bit 8 to L and bit 9 to R, and bits 0–7 each to its key, on two controllers (the generic third-party pad; the original Nintendo pad) with no human count in the chain (GBP-HW-270); history: C, not FACT, from the promotion of that day until the join — the chain then rested on the Operator's press count (GBP-KEY-009), observed through the digital click of a generic third-party pad; details and every id in `../protocol/INPUT.md` | GBP-KEY-001, GBP-KEY-004, GBP-KEY-005, GBP-HW-261, GBP-HW-262, GBP-HW-264, GBP-HW-265, GBP-HW-267, GBP-HW-269, GBP-HW-270 |
| Control/status | both | 1-byte *control* register: cartridge type/presence flags, two "power" bits used as reset/stop, IRQ mask bit, link-related bits. **The cartridge-sensing bits have been read on hardware since 2026-09-22 and the two behave differently.** *Presence* (0x02): the byte sampled before any write is `0x90` without a Game Pak and `0x92` with one, this bit alone, in 36 archived runs spanning both build eras and three slot states. *Type* (0x01): **the read point is the result** — with a Game Boy Color cartridge the bit is CLEAR in the original byte, indistinguishable from a GBA cartridge's, and becomes set 186–636 µs after the transform write, persisting through teardown so that a read-back-comparing restore fails and a power cycle is required; **why it arrives late is UNKNOWN** (U-GBP-036). The value is not the discriminator on its own: byte 0 of the block prints `8f` in 23 of RUN 17's 26 reads and RUN 17 had a **GBA** cartridge, so what is unique to the GB/GBC run is unanimity across the 31 stable replicas plus persistence. The other bits are untouched by this | C for usage, H for names — **and the usage and the hardware columns are different claims; neither upgrades the other** (`../protocol/REGISTERS.md` §3). Presence: **F (hw, 36 logs)** for the split, **C, not F, for the causal reading** — *nobody has yet watched the bit change while only the cartridge changed*. Type: **F (hw, RUN 24, run-scoped)** for the transition and the contrast, **C, not F, for the MEANING**, one run and one cartridge | GBP-CTL-001 (usage, status unchanged), GBP-HW-272 (with its 2026-09-22 amendment), GBP-HW-273, GBP-HW-274, GBP-HW-275, U-GBP-036 |
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
- KEYPAD word and the input path: `docs/protocol/INPUT.md`
- HSP / DMA mechanics: `docs/hardware/HSP.md`
- GBS-DOL behavior summary: `docs/hardware/GBS-DOL.md`
- Evidence and open questions: `docs/research/EVIDENCE.md`, `docs/research/UNKNOWNS.md`
