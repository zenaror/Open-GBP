# GBS-DOL — behavior summary

The GBS-DOL is the NEC custom chip on the Game Boy Player board that sits
between the GameCube HSP and the CPU AGB A. Nothing about its internals
is documented publicly; this page summarizes its *externally observable*
behavior as reconstructed in Phase 2 (see `docs/protocol/REGISTERS.md`
for the register-level detail and `docs/research/EVIDENCE.md` for
provenance). Status letters: F/C/H/U.

## Presents itself as

- An ARAM-expansion device on the HSP: eight 1 MB windows at
  `internal_ARAM_size + (0x0,0x1,0x4,0x5,0x8,0x9,0xC,0xD) << 20`, each
  answering 32-byte DMA transfers. **C**
- An interrupt source on PI bit 13 with a 16-bit device-side IRQ
  register holding six even-bit sources and six odd-bit masks. **C**

## Identification

- No version/ID register is used by DISC, GBI or Dolphin. **F (absence)**
- Presence is established by the TEST window returning the bitwise
  inverse of what was written. **C**
- Whether board revisions (DOL-GBS-01/10/20, CPU AGB A vs A E) differ in
  behavior is **U** (U-GBP-009).

## Functions exposed to the GameCube

| Function | Window | Observed behavior | Status |
|----------|--------|-------------------|--------|
| Power / reset of the AGB | CONTROL bits 0x04, 0x08 | set to run, cleared to stop; Dolphin resets the emulated GBA on 0→1 | C (usage) / H (meaning) |
| Cartridge sensing | CONTROL bits 0x01 (GB-type), 0x02 (present) | read by the Start-up Disc and GBI to pick "Game Boy"/"Game Boy Advance" and "Game Pak" | C |
| Interrupt mask | CONTROL bit 0x10 | 1 = masked | C |
| Sleep / link related | CONTROL bits 0x20, 0x40, 0x80 | read/written by DISC around serial operations and stop; names from Dolphin comments only | H |
| Keypad injection | KEYPAD (16-bit, 1 = pressed, GBA key order low byte; L/R in bits 8/9, order per Dolphin swapped) | refreshed on every IRQ by the Start-up Disc and GBI; `0x0304` used to wake from sleep (GBI) | C / H (L/R order) |
| Video capture | VIDEO window, 4 raster lines × 240 px × 32-bit per 0xF00 read (line stride 960 B), pixel word of which both references consume bytes 1/3 as `(b1 << 8) | b3`; **the 15 colour bits arrive with the two outer 5-bit groups exchanged relative to the AGB's framebuffer** (AGB bits 4–0 → word bits 14–10 and vice versa, bits 9–5 unchanged), so the references' GX RGB5A3 reading — bit 15 flag, 14–10 R, 9–5 G, 4–0 B — is the displayed colour; bit 15 observed set on exactly one word per frame, the first pixel; IRQ bit 8 per block (40 per frame). Bytes 0 and 2 are consumed by neither reference and vary physically between frames of the same picture — meaning UNKNOWN (U-GBP-029) | colour order: **two physical confirmatory runs with a known-colour stimulus**, GBP-VIDEO-003 `color-0002` under the contract pre-registered in `HARDWARE_TESTS.md` §V4 (GBP-HW-127…133), corroborated by `color-0001`; geometry and byte picking: the Start-up Disc and GBI (`docs/research/VIDEO_PATH.md`), Dolphin cross-checked, physical block read GBP-HW-051/058 | **colour order F (hw)**; geometry C; block read F (hw) |
| Audio capture | AUDIO window, 0x1000 bytes per IRQ bit 10; PWM bit-stream per Dolphin | the Start-up Disc and GBI read 0x1000; format H | C / H |
| Serial bridge to the AGB SIO | SIOCTL (byte) + SIODATA (32-bit) + IRQ bit 6 | DISC drives a write/start/read protocol; GBI reads on IRQ; Dolphin stubs | F (exists) / U (semantics) |
| Game Pak event | IRQ bit 2 | DISC stops on it | C |
| Sleep event | IRQ bit 4 | DISC masks IRQ and enters state 3; GBI presses L+R+Select | C |

## Frame timing

The AGB free-runs at 59.73 Hz while the GameCube side is at 59.94 Hz; the
board does no synchronization and "adds frames where it needs to"
(endrift, hardware observation, **F**). The VIDEO IRQ therefore comes at
the AGB's rate; software must handle a frame arriving late/early
relative to VI. Dolphin ties video IRQs to the audio tick (**H**).

## What the GBS-DOL is *not* known to do

- No JoyBus/SI traffic is involved on the GameCube side: DISC and GBI
  never touch SI for the GBP (the SDK "GBA" library present in DISC is
  used for a separate feature and calls the DSP, not the HSP). **F**
- No mailbox-style registers were found despite YAGCD's "TX/RX mailbox"
  wording. **F (absence)**
