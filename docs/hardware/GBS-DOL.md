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
| Cartridge sensing | CONTROL bits 0x01 (GB-type), 0x02 (present) | read by the Start-up Disc and GBI to pick "Game Boy"/"Game Boy Advance" and "Game Pak". **Open-GBP has now read both bits on hardware and they behave differently, so they are stated apart.** **Bit 0x02:** the original byte — sampled before any write — is `0x90` in the 13 archived cartridge-less runs and `0x92` in the 23 with a cartridge, differing by this bit alone with no exception, across **both build eras and three slot states** (no cartridge, a Game Boy Advance cartridge, a Game Boy Color cartridge). **Bit 0x01, and the READ POINT IS THE RESULT:** with a **GB/GBC** Game Pak inserted the bit is **CLEAR in the original byte** (`0x92`, indistinguishable from a GBA cartridge's), and becomes **SET between 186 µs and 636 µs after the transform write**, staying set through teardown — so a restore that compares its read-back against what it wrote legitimately fails (`0x92` written, `0x93` read) and the console needs a power cycle. **Why it arrives late is UNKNOWN** (U-GBP-036): the transform's own power/reset bits, the first IRQ-register write and plain elapsed time all fall inside that window and one run separates none of them. **And the value alone is not the discriminator:** byte 0 of the CONTROL block prints `8f` in 23 of RUN 17's 26 reads, and RUN 17 had a **GBA** cartridge — what is unique to the GB/GBC run is unanimity across the 31 stable replicas together with persistence to the end of the run | C (usage, both bits: GBP-CTL-001, whose status is unchanged and whose claim is what the SOFTWARE does with the register). **Bit 0x02 — F (hw, 36 logs)** for the split; **C, not F, for the causal reading** since RUN 23 filled the cell that made a build-era explanation possible: *nobody has yet watched the bit change while only the cartridge changed* (GBP-HW-272 **with its amendment**, GBP-HW-273). **Bit 0x01 — F (hw, RUN 24, run-scoped)** for the transition and the contrast; **C, not F, for the MEANING** "a GB/GBC Game Pak is present" — one run, one cartridge, and FACT would need a repeat and a second GB/GBC cartridge (GBP-HW-274, GBP-HW-275, U-GBP-036) |
| Interrupt mask | CONTROL bit 0x10 | 1 = masked | C |
| Sleep / link related | CONTROL bits 0x20, 0x40, 0x80 | read/written by DISC around serial operations and stop; names from Dolphin comments only | H |
| Keypad injection | KEYPAD (16-bit in bytes 0x1E–0x1F, 1 = pressed; bits 0–7 in the GBA KEYINPUT order; **bit 8 = L, bit 9 = R** — the reverse of KEYINPUT's, as the Start-up Disc, GBI and Dolphin's model all write it) | refreshed on every IRQ by the Start-up Disc (and every 5 ms) and by GBI; `0x0304` used to wake from sleep (GBI). **Open-GBP wrote it on hardware on 2026-09-21 (GBP-INPUT-001, RUN 14 / RUN 15): 7 892 / 7 895 completed writes, every pressed button counted at its own counter by the test ROM, L = 1 and R = 2 under that assignment — through the digital click of a generic third-party pad** (GBP-HW-262, GBP-HW-264, GBP-HW-265); **and on `stream-0015` in RUN 17 / RUN 18 / RUN 16 (7 898 / 7 898 / 7 890 completed writes) with the word sent at each change recorded — the join closed FACT** (GBP-HW-267, GBP-HW-270) | C (format, polarity: GBP-KEY-001, GBP-KEY-005); F (hw, run-scoped) that a written word reaches the cartridge as presses; **F (hw, run-scoped; L/R order) since 2026-09-21** — the machine join of RUN 17 (generic pad) and RUN 18 (original Nintendo pad): the runtime's KEY record joined to the checker's counters binds bit 8 to L and bit 9 to R, and every other bit to its key, with no human count in the chain (GBP-HW-267, GBP-HW-269, GBP-HW-270); history: **C (L/R order)** — H until 2026-09-21, not FACT until the join later that day, when the chain rested on the Operator's press count (GBP-KEY-009 named the log line, GBP-KEY-010 implemented it) and the official pad was not exercised (GBP-HW-261); details `docs/protocol/INPUT.md` |
| Video capture | VIDEO window, 4 raster lines × 240 px × 32-bit per 0xF00 read (line stride 960 B), pixel word of which both references consume bytes 1/3 as `(b1 << 8) | b3`; **the 15 colour bits arrive with the two outer 5-bit groups exchanged relative to the AGB's framebuffer** (AGB bits 4–0 → word bits 14–10 and vice versa, bits 9–5 unchanged), so the references' GX RGB5A3 reading — bit 15 flag, 14–10 R, 9–5 G, 4–0 B — is the displayed colour; bit 15 observed set on exactly one word per frame, the first pixel; IRQ bit 8 per block (40 per frame). Bytes 0 and 2 are consumed by neither reference and vary physically between frames of the same picture — meaning UNKNOWN (U-GBP-029) | colour order: **two physical confirmatory runs with a known-colour stimulus**, GBP-VIDEO-003 `color-0002` under the contract pre-registered in `HARDWARE_TESTS.md` §V4 (GBP-HW-127…133), corroborated by `color-0001`; geometry and byte picking: the Start-up Disc and GBI (`docs/research/VIDEO_PATH.md`), Dolphin cross-checked, physical block read GBP-HW-051/058, and **the physical geometry reconstructed legible from preserved raw frames** (GBP-HW-081), 477 of 489 frame intervals of exactly 40 blocks (GBP-HW-076), both frame-start predicates agreeing on 19 601 blocks (GBP-HW-077), bit 15 once per frame at (0, 0) (GBP-HW-129); consolidated in `docs/protocol/VIDEO.md` | **colour order F (hw)**; geometry F (hw); 40-block composition F (hw); block read F (hw) |
| Audio capture | AUDIO window, 0x1000 bytes per IRQ bit 10, 4 096 blocks per second, one sample per block carried as the width in bits of a 1-bit PWM pulse; Dolphin's byte layout is refused on hardware | the Start-up Disc and GBI read 0x1000 (GBP-AUD-001); on hardware: the rate (GBP-HW-301), the pulse (GBP-HW-304), the decode (GBP-HW-313), Dolphin's layout refused (GBP-HW-287, GBP-HW-296); consolidated in `docs/protocol/AUDIO.md` | C (size, rate, decode layout) / F (hw: pulse structure) / Dolphin's byte layout REFUSED; history: format H until 2026-09-22 |
| Serial bridge to the AGB SIO | SIOCTL (byte) + SIODATA (32-bit) + IRQ bit 6 | DISC drives a write/start/read protocol; GBI reads on IRQ; Dolphin stubs | F (exists) / U (semantics) |
| Game Pak event | IRQ bit 2 | DISC stops on it | C |
| Sleep event | IRQ bit 4 | DISC masks IRQ and enters state 3; GBI presses L+R+Select | C |

## Frame timing

The AGB free-runs at 59.73 Hz while the GameCube side is at 59.94 Hz; the
board does no synchronization and "adds frames where it needs to"
(endrift, hardware observation, **F**). The VIDEO IRQ therefore comes at
the AGB's rate; software must handle a frame arriving late/early
relative to VI. Measured on this project's hardware: the source frame
cadence read 59.727 Hz as the median of 465 consecutive complete frames in
one run and 59.7271 FRAME_ID/s over 34.27 s in another (GBP-HW-078,
GBP-HW-187 — measurements of those runs, **F**, no nominal rate promoted),
against a video-interface period of 59.940 Hz re-derived per run
(GBP-HW-210); the rate difference requires about seven repeated display
intervals per 34 s window, which are the VI showing one framebuffer for one
extra period and not lost frames (GBP-HW-210, GBP-HW-211, **F** for those
runs; GBP-VID-020). Dolphin ties video IRQs to the audio tick (**H**).

## What the GBS-DOL is *not* known to do

- No JoyBus/SI traffic is involved on the GameCube side: DISC and GBI
  never touch SI for the GBP (the SDK "GBA" library present in DISC is
  used for a separate feature and calls the DSP, not the HSP). **F**
- No mailbox-style registers were found despite YAGCD's "TX/RX mailbox"
  wording. **F (absence)**
