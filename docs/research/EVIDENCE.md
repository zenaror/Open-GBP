# Evidence Register

Claims about hardware, tools, and reference software, each with an explicit
status as defined in `docs/RESEARCH_METHOD.md`:

```text
FACT          directly observed / reproducible
CORROBORATED  multiple independent sources agree
HYPOTHESIS    plausible, not yet demonstrated
UNKNOWN       no defensible interpretation yet
```

ID prefixes:

```text
ENV-   development environment, toolchain, emulator behavior (not GBP hardware)
GBP-   physical Game Boy Player / HSP / GBS-DOL behavior
```

`GBP-` entries come from Phase 2 static analysis (2026-09-13). None has
been verified on physical hardware by this project yet; "FACT" below
means "directly observed in the named source", not "observed on hardware".

Source shorthands used below:

```text
DISC     Game Boy Player Start-up Disc, UGPE01 v2, image sha256 947a5523…; main.dol sha256
         3dd3692f5931516b80915b38e795aa6092e4d4db43cd652bc396e0cba2b11b5d (1859680 bytes,
         extracted with tools/gciso.py; Dolphin SDK Dec 2002 build). Analyzed with Ghidra
         12.1.3 headless + tools/ghidra/*.java. Function addresses are DISC virtual addresses.
GBI      Game Boy Interface Standard Edition; gbi.dol sha256 8083636c1b341e712859f40356bf5934
         f4622fab7e7a658bd7e8cb4feeb616b1 (packed); unpacked image sha256 0b2c44ea75f85aa8d64a
         c3ad167c400f778becc58e886c53a44b9a67f46384b0 (734732 bytes, load 0x80003100) via
         tools/gbi_unpack.py. libogc-rice r2191.
DOLPHIN  dolphin-emu/dolphin master c185d27ede09771fe93a3b520c576f646f937ed9 (2026-09-12) and tag
         2606a c77bbaa0…; Source/Core/Core/HW/HSP/*, HW/DSP.cpp, HW/ProcessorInterface.h,
         Data/Sys/GameSettings/UGP.ini. GBP device added by PR #14535 (jordan-woyak, co-authored
         by endrift, merged 2026-04-01).
LIBOGC2  extremscorner/libogc2 ca03fb7534a9b67d3348ef76e3a3b379aee9392a (2026-09-12): libogc/aram.c,
         libogc/irq.c, include/ogc/irq.h, include/ogc/system.h.
YAGCD    hitmen.c02.at/files/yagcd/yagcd (consulted 2026-09-13): 5 (DSP regs), 6.1.5.2/6.2.1
         (PI/HSP interrupt), 6.2.8 (DSP interrupts), 11/11.1 (HSP devices, "to do").
GBATEK   mgba-emu/gbatek gh-pages 64b5087aa45cd0187b8b239d77e54ee5eb2917d1: gba.md "GBA Gameboy
         Player", "SIO Normal Mode", "SIO JOY BUS Mode".
GBPP     endrift/gbpp f71afcdbdce1745ccc12ce4dcae7168cb9899530 + article endrift.com/2015/03/24/gbpp/.
GBHWDB   gbhwdb.gekkio.fi/consoles/gbs/ (consulted 2026-09-13, 10 units).
```

---

## ENV-DOL-001 — Dolphin 2606a requires 32-byte-aligned DOL sections

**Claim:** Dolphin 2606a refuses to boot a DOL whose text or data sections
have a load address or a size that is not a multiple of 32 bytes. The
failure is fatal (the DOL is treated as invalid, emulation never starts),
not a warning.

**Status:** FACT

**Confidence:** high

**Sources:**

- Dolphin log, 2026-09-13, from `build/poc/smoke-test` first run:
  `E[BOOT]: Text section 0 is not 32-byte aligned: address = 0x80003100, size = 0x2a1d8`
  followed by no boot, no EXI device creation, no frames.
- Dolphin source tag `2606a`, `Source/Core/Core/Boot/DolReader.cpp`,
  `DolReader::Initialize`: checks `(address & 31) != 0 || (size & 31) != 0`
  for text and data sections and returns `false`.
- Dolphin `master` at the same date only logs a warning for unaligned sizes;
  the behavior differs between versions.

**Hardware tests:** none. Physical loaders (IPL, Swiss) are believed to
accept unaligned sizes, but this project has not verified it and does not
depend on it: the build always produces 32-byte-padded DOLs.

**Notes:**

- devkitPro `elf2dol` (devkitppc r50 / devkitPPC tools in
  `ghcr.io/extremscorner/libogc2:20260805`) emits section sizes equal to the
  ELF `PT_LOAD` `p_filesz`, which are generally unaligned (observed
  `0x2A1D8` text, `0xCD90` data for the smoke test).
- GNU ld 2.46 `INSERT AFTER .text` cannot augment the devkitPPC `ogc.ld`
  script passed via `-T` (`ld: .text not found for insert`), so the fix is
  a post-link step: `tools/dolpad.py` pads sizes to 32 bytes with
  zero bytes and verifies the result. `tools/dolinfo.py --require-aligned`
  checks it.

**Open questions:** none blocking. Whether Swiss/IPL accept the padded DOL
identically is expected (padding only adds zero bytes into linker gaps or
BSS) and will be confirmed by the first physical smoke test.

---

## ENV-EXI-001 — libogc2 polls an EXI register mirror that Dolphin does not map

**Claim:** libogc2 r2442 (`libogc/exi.c`, `EXI_Sync`) waits for an
immediate EXI transfer by polling `_exiReg[7 + chn][0]`, i.e. physical
address `0x0C00688C + chn * 0x14` (a +0x80 mirror of the channel's CR
register at `0x0C00680C + chn * 0x14`). Dolphin 2606a maps only the three
documented channels (stride 0x14, 5 registers) and logs
`E[MI]: Trying to read 32 bits from an invalid MMIO (addr=0c00688c|0c0068a0)`
for each poll, returning 0. Because the returned value has bit 0 clear, the
wait loop exits immediately; EXI immediate transfers still complete in
Dolphin, and the USB Gecko output of the smoke test is received intact.

**Status:** FACT (observed behavior in Dolphin; source visible in libogc2)

**Confidence:** high for the observed behavior. The reason the mirror
exists is documented by the libogc2 author, not by this project.

**Sources:**

- Disassembly of `build/poc/smoke-test/smoke-test.elf`, `EXI_ImmEx`
  (with `EXI_Sync` inlined): `addis r10,r10,-13312 ; addi r10,r10,26764`
  (`0xCC00688C`) then `lwz/andi./bne` spin on bit 0.
- libogc2 source `libogc/exi.c`: `while(_exiReg[7+nChn][0]&0x0001);`
- libogc2 commit `47cea34b64e521fffa1aed175265464bd938c81a` (2025-11-09):
  "Use a memory mirror to work around Dolphin emulation inaccuracies";
  related commits `837eba02` (2024-11-26) and `af141410` (2024-07-28).
- Dolphin 2606a `Source/Core/Core/HW/EXI/EXI.cpp` (3 channels, 5 registers,
  stride 20) and `Source/Core/Core/HW/MMIO.cpp` (invalid read returns 0).
- Dolphin log from `make smoke-dolphin`, 2026-09-13: 10 reads at
  `0c00688c` during libogc init (channel 0: RTC/SRAM), 383 reads at
  `0c0068a0` during USB Gecko output (channel 1).

**Hardware tests:** none. This project has not observed the mirror on
physical hardware.

**Notes:** `tools/dolphin_smoke.py` classifies exactly these log lines as
known-benign and reports their count; any other error-level line still
fails the run.

**Open questions:**

- Whether the physical EXI register block mirrors at +0x80 is implied by
  libogc2 working on real hardware, but is not verified here
  (see UNKNOWNS `U-ENV-001`). It is irrelevant to Open-GBP unless
  Open-GBP writes its own EXI driver.

---

## GBP-PHY-001 — Physical composition and revisions

**Claim:** The Game Boy Player board (DOL-GBS) carries a stock **CPU AGB A**
(one catalogued unit: CPU AGB A E), an NEC custom **GBS-DOL**, a work-RAM
chip of 16 Mb or 128 Mb from various vendors, and a Kinseki crystal.
Three board revisions are catalogued: DOL-GBS-01, -10, -20.

**Status:** CORROBORATED — **Confidence:** high

**Sources:** GBHWDB (10 units, table in DEVLOG); GBPP article ("a stock CPU
AGB A chip … along with a custom chip labeled GBS-DOL that bridges the
High Speed Port … and the CPU AGB A's signals").

**Hardware tests:** none by this project. **Open:** U-GBP-009 (revision differences).

## GBP-PHY-002 — Test points expose AGB keypad, reset and vsync

**Claim:** TP33–TP42 are the AGB keypad inputs, TP25 the AGB reset, TP29
the LCD SPS (vsync) signal. **Status:** FACT (GBPP hardware mod, pin table
in `gbpp/gbpp/gbpp.ino`). **Confidence:** high. Not needed by Open-GBP;
recorded because it proves the keypad is driven electrically into the
AGB, i.e. KEYPAD-register writes end up as AGB key lines.

## GBP-PHY-003 — No frame-rate synchronization between AGB and GameCube

**Claim:** The AGB runs at 59.73 Hz, the GameCube output at ~59.94 Hz, and
the GBP "does not do any fancy synchronization and just adds frames where
it needs to". **Status:** FACT (GBPP author's hardware observation).
**Confidence:** medium-high (single observer). Consequence: VIDEO IRQs
arrive at the AGB's cadence; the runtime must tolerate frame slip.

## GBP-LINK-001 — External Link Port works independently of the GameCube

**Claim:** A cartridge running in the GBP communicates through the
physical Link Port with external devices (PicoAdapterGB) without any
GameCube-side support. **Status:** FACT (user's established setup,
`CLAUDE.md` §3). Regression reference for all later phases.

## GBP-HSP-001 — The GBS-DOL is addressed through ARAM DMA above the internal ARAM size

**Claim:** GameCube software reaches the GBP with ordinary ARAM DMA
transfers (`0xCC005020/24/28`) whose ARAM address is
`internal_ARAM_size + (register_index << 20) [+ offset]`, 32-byte
granularity. Register indices used: 0x0, 0x1, 0x4, 0x5, 0x8, 0x9, 0xC, 0xD.

**Status:** CORROBORATED — **Confidence:** high

**Sources:**
- DISC `0x80089c3c` (programs the six DMA half-registers, direction in
  CNT bit 15) called by wrappers that add `base + 0x000000/0x100000/
  0x400000/0x500000/0x800000/0x900000/0xC00000/0xD00000`, base being the
  size read from `0xCC005012` bits 0–2 (`0x80089aac`, `0x80089da0`).
- GBI `0x8000be48/0x8000bea4/0x80011c14`: `ARQ_PostRequest` with
  `AR_GetInternalSize() + same offsets` (call sites in the worker thread
  `0x8000bf30`, e.g. `0x900000/0x20`, `0x800000/0x1000`, `0x100000/0xF00`,
  `0xC00000`, `0x400000`, `0xD00000`).
- DOLPHIN `DSP.cpp Do_ARAM_DMA`: `ARAddr >= m_aram.size` → `HSPManager::Read/Write`
  in `TRANSFER_SIZE = 32` chunks; `HSP_DeviceGBPlayer.cpp` `GBPRegister = address >> 20`
  = 0x10, 0x11, 0x14, 0x15, 0x18, 0x19, 0x1C, 0x1D.
- YAGCD 11: "HSP devices seem to be accessable through the ARAM interface with offsets beyond 16MB".

**Hardware tests:** none. **Open:** U-GBP-004, U-GBP-005.

## GBP-HSP-002 — Expansion-size code 3 is written to 0xCC005012 before GBP use

**Claim:** Both drivers write `3` into bits 3–5 of `0xCC005012` (AR_INFO)
before any GBP transfer: DISC `0x80089b60(0x1000000)` → `(v & 0xFFC7) | (3 << 3)`;
GBI `0x8001123c` → `(v & 0xFFC7) | 0x18`. In LIBOGC2 `__ARCheckSize` the
same bits encode the detected expansion ARAM size (0x18 = 16 MB). Dolphin
does not consult these bits for HSP routing.

**Status:** CORROBORATED (both drivers) — **Confidence:** high for the
write, **HYPOTHESIS** that it is required (U-GBP-004).

## GBP-HSP-003 — Transfer format: 32-byte blocks, value in the last bytes, completion via DSP CSR bit 5

**Claim:** Register writes place the value at the end of the 32-byte
block (byte 0x1F for 8-bit, 0x1E–0x1F for 16-bit, 0x1C–0x1F for 32-bit);
reads are consumed from byte 0x1F (8-bit), 0x1D/0x1F (16-bit) and
0x19/0x1B/0x1D/0x1F (32-bit). DISC waits for completion by polling
`0xCC00500A` bit 5 and clears it by writing bit 5 back (`0x80089cc8`,
1 s timeout); it refuses to start a transfer while bit 9 (busy) or bit 5
is set.

**Status:** CORROBORATED (DISC wrappers `0x80089e40…0x8008a3c4`; DOLPHIN
`Write`: `data[0x1f]`, `swap16(data+0x1e)`, `swap32(data+0x1c)`; GBI byte
helpers `0x80015b08/0x80015c64` read the same positions) —
**Confidence:** high for the written positions, medium for the read layout
(U-GBP-008).

## GBP-HSP-004 — Registers respond at more than one offset inside their 1 MB window

**Claim:** GBI writes KEYPAD+IRQ as one 64-byte DMA at `base + 0xCFFFE0`
and reads CONTROL+SIOCTL as one 64-byte DMA at `base + 0x4FFFE0`; DISC
uses offset 0 of each window. Hence at least offsets 0x00000 and 0xFFFE0
of a window select the same register.

**Status:** CORROBORATED (GBI `0x8000bf30`; DISC; DOLPHIN `address >> 20`
ignores low bits) — **Confidence:** high. **Open:** whether every 32-byte
slot mirrors (U-GBP-005).

## GBP-TEST-001 — TEST register echoes the inverse of the written block

**Claim:** Writing a 32-byte block to index 0x0 and reading it back yields
the bitwise complement. DISC handshakes with patterns C3, 3C, FF, 00 and
checks byte 0x1F; GBI with C3 and FF in a write/read/write-back/read
cycle; Dolphin stores `data ^ 0xFF`. DISC repeats one pattern every 5 ms
while running to detect removal (error 5).

**Status:** CORROBORATED — **Confidence:** high. **Hardware tests:** none
(this is the proposed first Phase 3 experiment).

## GBP-IRQ-001 — Interrupt path and IRQ register semantics

**Claim:** The GBP interrupts on PI bit 13 (`0x2000`), OS interrupt 26 in
both SDK (DISC `OSSetInterruptHandler(26, …)`, dispatcher `0x80069ff0`
maps cause 0x2000 → index 26) and libogc (`IRQ_PI_HSP = 26`; GBI
`IRQ_Request(0x1a, …)`, `__UnmaskIrq(0x20)`). Device-side, the 16-bit IRQ
register at index 0xD holds sources on even bits 0/2/4/6/8/10 and their
masks on the odd bits; software acknowledges by writing the pending value
back; bit 15 is written together with the mask at IRQ entry. PI is
acknowledged by writing 0x2000 to `0xCC003000`. CONTROL bit 0x10 masks
the line.

**Status:** CORROBORATED (DISC `0x8008af08`, tables at 0x801B34C8/0x801B34D4
= {0x0001,0x0040,0x0010,0x0004,0x0400,0x0100} / {0x0002,0x0080,0x0020,
0x0008,0x0800,0x0200}; GBI `0x8000b400`, `0x8000bf30`; DOLPHIN
`AssertIRQ`/`UpdateInterrupts`; YAGCD 6.1.5.2) — **Confidence:** high for
bit positions and ack; medium for mask polarity and bit 15 (U-GBP-007).

Source-to-function mapping (which bit means what) rests on what each
driver *does* on that bit: 0x0100 → VIDEO read, 0x0400 → AUDIO read,
0x0040 → serial, 0x0010 → sleep handling, 0x0004 → stop. Names
Link/GamePak/Sleep/Serial/Video/Audio are Dolphin's.

## GBP-CTL-001 — CONTROL register usage

**Claim:** Index 0x4 is an 8-bit register. Bits 0x01/0x02 are read as
cartridge type/presence; 0x04 and 0x08 are set to run and cleared to
stop; 0x10 masks the interrupt; 0x20/0x40/0x80 are read/written around
serial operations and stop. Dolphin: `CART_IS_GB, CART_INSERTED, 3V, 5V,
MASK_IRQ` (+ commented `SLEEP, LINK_CABLE, LINK_ENABLE`), reset on
(0x04|0x08) 0→1, stop on →0, write mask 0xFC.

**Status:** CORROBORATED for usage of 0x01–0x10 (DISC `0x8008bf84`,
`0x8008be04`, `0x8008c26c`, `0x8008bd50`, `0x8008bcc4`; GBI start
`(v&0xE7)|0x0C`, stop `(v&0xE3)|0x10`, strings "Game Boy"/"Game Boy
Advance"/"Game Pak" chosen from bits 0/1); **HYPOTHESIS** for the meaning
of 0x20–0x80 and for the names "3V/5V" (U-GBP-006).

## GBP-KEY-001 — KEYPAD register

**Claim:** Index 0xC accepts a 16-bit value in bytes 0x1E–0x1F, 1 =
pressed, low byte in GBA KEYINPUT order (A,B,Select,Start,Right,Left,Up,
Down), L/R in bits 8–9. Both drivers rewrite it on every HSP interrupt
(DISC also every 5 ms). GBI writes 0 at start and 0x0304 (L+R+Select) on
the sleep IRQ.

**Status:** CORROBORATED (DISC `0x80089e40`; GBI; DOLPHIN `Keypad` write
→ `SetKeys`) — **Confidence:** high for format/polarity, **HYPOTHESIS**
for the L/R bit order (Dolphin swaps: hi bit0 → L, hi bit1 → R; U-GBP-010).

## GBP-VID-001 — VIDEO data format and cadence

**Claim:** Index 0x1 delivers 0xF00 bytes per VIDEO IRQ = 4 scanlines ×
240 pixels × 4 bytes; 40 blocks per 160-line frame. Each 32-bit word is a
16-bit color with both bytes doubled; bit 15 of the first pixel of a
frame's first block is set (mask 0x80800000 after doubling).

**Status:** CORROBORATED (DISC: 0xF00 reads, 40 ring buffers of 0xF00,
frame buffer stride 0x25800 = 240×160×4, dummy first block with byte 0
|= 0x80; GBI: 0xF00 reads on bit 0x100, frame-start test
`(word0 & 0x80800000) == 0x80800000`, 40-entry ring `% 0x28`; DOLPHIN
`PrepareScanlineData`/`Read(Video)`; PR #14535 "mirroring aligns with actual
hardware behavior per hardware researcher consultation") —
**Confidence:** high for geometry/flag, medium for color bit order (Dolphin
`M_RGB8_TO_RGB5`, GBA palette order) — U-GBP-011.

## GBP-AUD-001 — AUDIO data size and cadence

**Claim:** Index 0x8 delivers 0x1000 bytes per AUDIO IRQ; DISC keeps 70
ring buffers and feeds them to its audio pipeline; GBI reads 0x1000 on
bit 0x400. Dolphin models the content as 0x400 PWM bytes each mirrored ×4,
produced at 4096 Hz, 1 bit per 32-bit word after mirroring, and notes the
DISC only accepts words whose 1-bits are contiguous and leading.

**Status:** CORROBORATED for size/IRQ; **HYPOTHESIS** for the PWM format
(Dolphin only) — U-GBP-012.

## GBP-SIO-001 — Internal serial path exists and is used by the official disc

**Claim:** Indices 0x5 (SIOCTL, byte) and 0x9 (SIODATA, 32-bit) plus IRQ
bit 6 form a GameCube-side serial interface to the AGB. DISC
(`0x8008c42c`) runs: write SIODATA → SIOCTL |= 0x80 → wait IRQ bit 6 /
1 s timeout → read SIODATA or SIOCTL → SIOCTL &= ~0x08; it sets CONTROL
bit 0x80 before use and fails if CONTROL bit 0x20 is set. GBI reads
SIODATA on IRQ bit 6 and writes SIODATA from a queue. Dolphin's
`ReadSIOControl/WriteSIOControl/ReadSIOData/WriteSIOData` are stubs
(`DEBUG_LOG` only, return 0).

**Status:** FACT that the path exists and is exercised by official
software; **UNKNOWN** semantics of every bit and how it maps to the
AGB's SIO/JoyBus (U-GBP-001..003). This is the Phase 10 starting point.

## GBP-SDK-001 — No SI/JoyBus traffic is used for the GBP itself

**Claim:** Neither DISC nor GBI touches the SI (`0xCC0064xx`) to
communicate with the GBP; DISC's SDK "GBA" library (strings `GBAKey.c`,
`GBAPadInit : ClientImageSize`) is the JoyBus GBA-as-controller library
and uses the DSP, not the HSP. **Status:** FACT (absence, by MMIO
reference scan) — **Confidence:** medium (a scan can miss computed
addresses).

## GBP-SRAM-001 — The GameCube SRAM keeps a "GBS" settings word

**Claim:** libogc2 exposes `SYS_GetGBSMode/SYS_SetGBSMode` on a 16-bit
`gbs` field of the extended SRAM ("Game Boy Player Start-Up Disc
settings"), validated as bits 10–14 < 20, bits 6–7 != 3, bits 0–5 < 60.
**Status:** FACT (LIBOGC2 `system.c`). Not analyzed in DISC yet
(U-GBP-013).
