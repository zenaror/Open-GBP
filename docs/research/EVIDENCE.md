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

`GBP-` entries up to GBP-SRAM-001 come from Phase 2 static analysis
(2026-09-13); `GBP-HW-` entries are physical observations (2026-09-14/15);
`GBP-PI-`, `GBP-IRQ-002/003` and `ENV-IRQ-` entries come from the
interrupt-path audit of 2026-09-15 (static, no hardware). Unless an entry
cites a `GBP-HW-` id or a HARDWARE_TESTS run, "FACT" means "directly
observed in the named source", not "observed on hardware".

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
LIBOGC2  extremscorner/libogc2 ca03fb7534a9b67d3348ef76e3a3b379aee9392a (2026-09-12, shallow clone):
         libogc/aram.c, libogc/irq.c, libogc/irq_handler.S, libogc/exception.c, libogc/system.c,
         libogc/mmce.c, include/ogc/irq.h, include/ogc/system.h, include/ogc/timesupp.h,
         include/ogc/machine/processor.h.
LIBOGC2-BIN
         the libogc2 actually linked into every Open-GBP DOL: libogc.a from the Docker image
         ghcr.io/extremscorner/libogc2:20260805, _V_STRING "libogc2 r2442.094b250" (built Aug 5 2026),
         members irq.o / irq_handler.o disassembled with powerpc-eabi-objdump inside the container
         (2026-09-15). Commit 094b250 is not in the shallow LIBOGC2 history (U-ENV-005).
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

**Open questions:** none. Swiss loaded and ran the padded DOL on real
hardware on 2026-09-14 (ENV-HW-001; U-ENV-002 closed). Whether the IPL
or other loaders behave the same is untested and not needed.

---

## ENV-HW-001 — The build pipeline produces DOLs that run on the real GameCube

**Claim:** A DOL built by the project pipeline (Docker image
`ghcr.io/extremscorner/libogc2:20260805`, devkitPPC 16.1.0, libogc2
r2442, `elf2dol`, `tools/dolpad.py` 32-byte padding) loads through Swiss
on the user's GameCube, initializes libogc2 (video 640×480 NTSC, pad),
runs its main loop at 60 Hz, writes a file to the SD2SP2 card through
libfat (`__io_gcsd2`), and returns to Swiss on `exit()`.

**Status:** FACT (physical observation) — **Confidence:** high for this
artifact; one run, one console.

**Sources:** HARDWARE_TESTS.md SMOKE-HW-001 (2026-09-14): build
`smoke-0002`, commit `55ed6c1`, DOL SHA-256 `4175f21d…54fe88`; the log
file written by the GameCube (`IDENT`, `VIDEO 640x480 tvmode=0`,
`STATE seconds=8 frames=537 lit=7363 buttons_seen=0400`) and the user's
confirmation that START returned to Swiss.

**Hardware tests:** SMOKE-HW-001.

**Notes:** the same ring-buffer → `sdlog.c` path is used by
`poc/gbp-probe`; its reliability on hardware is therefore established
before the first GBP experiment. This entry says nothing about the Game
Boy Player, the HSP or ARAM DMA (none of them were exercised).

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

## ENV-IRQ-001 — libogc2 r2442.094b250 external-interrupt dispatch: no automatic mask, no automatic acknowledge, one handler per exception

**Claim:** In the libogc2 linked into Open-GBP DOLs, the external-interrupt
exception is handled by `irq_exceptionhandler` (irq_handler.S), which
saves the context, raises the interrupt-nesting count in SPRG0, calls
`c_irqdispatcher` and returns with `rfi` (the saved SRR1 restores
MSR[EE]). `c_irqdispatcher` (irq.c) does, in this order: read PI INTSR
(`0xCC003000`) and clear bit 16; read PI INTMR (`0xCC003004`); if the
cause is 0 or `cause & mask` is 0, count a spurious interrupt and
return; translate the cause bits (for PI bit 13: `IRQMASK(IRQ_PI_HSP)` =
`0x20`); drop the bits that are masked in the software shadows
(`prevIrqMask | currIrqMask`); pick **one** interrupt by the `_irqPrio`
priority table (PI HSP is the seventh entry, alone); call
`g_IRQHandler[irq]` if it is non-NULL; return. It never writes INTSR or
INTMR, never masks the interrupt it is dispatching, and runs the handler
with MSR[EE] = 0 on the interrupt stack (0x4000 bytes).

**Status:** FACT (source ca03fb7 and the container binary agree) — **Confidence:** high.

**Sources:**

- LIBOGC2 `libogc/irq.c` `c_irqdispatcher` (lines 119–260), `_irqPrio`,
  `__irq_init`; `libogc/irq_handler.S` `irq_exceptionhandler`
  (`bl c_irqdispatcher` … `__thread_dispatch` … `rfi`);
  `libogc/exception.c:128` (`__exception_sethandler(EX_INT, irq_exceptionhandler)`).
- LIBOGC2-BIN `irq.o`: `c_irqdispatcher` starts with `lis r10,-13312 ;
  ori r10,r10,0x3000 ; lwz r9,0(r10) ; lwz r7,4(r10) ; rlwinm. r8,r9,0,16,14
  ; beq spurious ; and. r8,r8,r7 ; beq spurious`; no store to `0xCC0030xx`
  anywhere in `c_irqdispatcher`; `irq_handler.o` contains the `bl
  c_irqdispatcher`, `bl __thread_dispatch` and `rfi` of the source.
- The same structure exists in the SDK dispatcher of the Start-up Disc
  (`0x80069ff0`: reads INTSR, masks bit 16, reads INTMR, `cause & mask`,
  removes `0x800000C4 | 0x800000C8`, priority table `0x801AD740`, one
  handler call, no INTSR/INTMR write) and in the libogc embedded in GBI
  (`0x80058360`, identical logic including the spurious counter).

**Hardware tests:** none needed for the software part. The physical
consequence (what happens on the PI line) is GBP-PI-003 / U-GBP-022.

**Notes:**

- Consequence 1: if the cause bit is still set and unmasked when the
  handler returns, the exception is taken again immediately after `rfi`
  (PowerPC external interrupts are level-triggered at the CPU pin).
- Consequence 2: an unmasked cause with `g_IRQHandler[irq] == NULL` is
  the same situation — nothing clears the cause — and the CPU never
  leaves the exception loop. **Never unmask IRQ 26 without a handler
  installed.**
- `spuriousIrq` is a static counter; it is not reachable from a POC.

---

## ENV-IRQ-002 — libogc2 IRQ mask API: shadow masks rebuild INTMR; IRQ_Request/IRQ_Free return the previous handler; __MaskIrq is usable from a handler

**Claim:** (1) `__MaskIrq(mask)` / `__UnmaskIrq(mask)` update the
software shadow `prevIrqMask` and then call `__SetInterrupts`, which
recomputes the **whole** PI INTMR value from `prevIrqMask | currIrqMask`
(`imask = 0xF0`, then one bit per unmasked PI source, bit 13 for
`IM_PI_HSP`) and stores it. A value written directly to `0xCC003004`
without updating the shadows is therefore overwritten by the next mask
change of any PI-group interrupt; INTMR observed as `0x1FA` on hardware
(GBP-HW-012), not the boot value `0xF0`, is such a rebuild. (2)
`IRQ_Request(nIrq, handler)` stores the new handler and returns the
previous one; `IRQ_Free(nIrq)` stores NULL and returns the previous one;
`IRQ_GetHandler(nIrq)` reads it. All three only toggle MSR[EE] around a
table access. (3) `__MaskIrq` executed inside an interrupt handler is
safe: it saves MSR, clears EE (already 0 in a handler), loops over
`__SetInterrupts`, restores the saved EE bit (still 0), uses 16 bytes of
stack, allocates nothing, blocks nowhere and performs no DMA.

**Status:** FACT (source and container binary) — **Confidence:** high.

**Sources:**

- LIBOGC2 `libogc/irq.c`: `__SetInterrupts` (PI group: `imask = 0xf0; …
  if(!(nMask&IM_PI_HSP)) imask |= 0x00002000; _piReg[1] = imask;`),
  `__UnmaskIrq`, `__MaskIrq`, `__irq_init` (`_piReg[1] = 0xf0; __MaskIrq(-32)`),
  `IRQ_Request`, `IRQ_Free`, `IRQ_GetHandler`; `include/ogc/irq.h`
  (`IRQ_PI_HSP 26`, `IM_PI_HSP IRQMASK(IRQ_PI_HSP)`, prototypes of
  `__MaskIrq`/`__UnmaskIrq`, `irq_handler_t` =
  `void (*)(u32 irq, frame_context *ctx)`).
- LIBOGC2-BIN `irq.o`: `IRQ_Request` = `mfmsr/rlwinm/mtmsr` (EE off) →
  `lwzx r3,g_IRQHandler[nIrq]` (return value = old) → `stwx r4` (new) →
  EE restore → `blr`; `IRQ_Free` identical with `li r7,0` stored;
  `__MaskIrq`/`__UnmaskIrq`: `stwu r1,-16`, save r30/r31, EE off, update
  `prevIrqMask` (SDA), `bl __SetInterrupts` in a loop until it returns 0,
  EE restore, `blr`. Container `libversion.h`: `_V_STRING "libogc2
  r2442.094b250"`; container `irq.h` line 143:
  `irq_handler_t IRQ_Request(u32 nIrq, irq_handler_t pHndl);`, lines
  180–181: `void __MaskIrq(u32 nMask); void __UnmaskIrq(u32 nMask);`.
- Runtime PI-group mask changes exist in libogc2 itself (`mmce.c` masks
  and unmasks `IM_PI_DEBUG`; the init-time unmasks of VI/SI/EXI/AI/DSP/
  MEM/RSW produced the `0x1FA` seen on hardware), so the rebuild is not
  theoretical.
- The Start-up Disc's SDK does the same: `0x80069ef0` (`OSMaskInterrupts`)
  and `0x80069f70` (`OSUnmaskInterrupts`) update the shadow words at
  `0x800000C4`/`0x800000C8` and call `0x80069ca0`, which rebuilds INTMR
  (`0xF0` + one bit per unmasked source; OS mask bit `0x20` ↔ INTMR bit
  13); `0x80069c38` (init) writes `0xF0` and masks everything;
  `0x80069c0c` (`OSSetInterruptHandler`) returns the previous handler.

**Hardware tests:** none (software behavior). GBP-HW-012 shows the
rebuilt value on hardware.

**Notes:** libogc2 installs no handler for IRQ 26 itself (no use of
`IRQ_PI_HSP`/`IM_PI_HSP` outside irq.c/irq.h), so the previous handler
returned by `IRQ_Request(IRQ_PI_HSP, …)` in a POC is expected to be NULL;
a POC must still record and restore whatever it gets.

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

**Status:** CORROBORATED (Start-up Disc + GBI) — **Confidence:** high for the
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
`Write`: `data[0x1f]`, `swap16(data+0x1e)`, `swap32(data+0x1c)`).
Correction 2026-09-14: GBI does **not** read fixed positions — it majority-
votes each bit over the 32 bytes for byte registers (`0x80015b08`) and
over bytes ≡1 mod 4 (high) / ≡3 mod 4 (low) for 16-bit registers
(`0x80015c64` called on `buf` and `buf+2`); its writes replicate the value
over the whole block (`0x80015d9c` byte, `0x80015da0` u16 as `hh ll hh ll…`).
**Confidence:** high for the written positions; the read layout is now a
hardware observation (GBP-HW-004).

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
checks **byte 1** of the 32-byte read (`0x8008ae3c`: `lbz r3,13(r1)` on a
buffer at `r1+12`; corrected 2026-09-14 — Phase 2 wrongly said 0x1F);
GBI with C3 and FF in a write/read/write-back/read cycle, comparing a
byte obtained by **majority vote of each bit over all 32 bytes**
(`0x80015b08`); Dolphin stores `data ^ 0xFF`. DISC repeats one pattern
every 5 ms while running to detect removal (error 5).

**Status:** CORROBORATED, and observed on hardware on 2026-09-14
(GBP-HW-003): bytes 1–31 were the complement in all 8 handshakes; byte 0
carried extra bits in 3 of them. **Confidence:** high.

## GBP-IRQ-001 — Interrupt path and IRQ register semantics

**Claim:** The GBP interrupts on PI bit 13 (`0x2000`), OS interrupt 26 in
both SDK (DISC `OSSetInterruptHandler(26, …)`, dispatcher `0x80069ff0`
maps cause 0x2000 → index 26) and libogc (`IRQ_PI_HSP = 26`; GBI
`IRQ_Request(0x1a, …)`, `__UnmaskIrq(0x20)`). Device-side, the 16-bit IRQ
register at index 0xD holds sources on even bits 0/2/4/6/8/10 and their
masks on the odd bits; software acknowledges by writing the pending value
back; bit 15 is written together with the mask at IRQ entry. PI is
acknowledged by writing 0x2000 to `0xCC003000` (W1C). CONTROL bit 0x10
masks the line. The exact per-driver order of device-side and PI-side
acknowledges is GBP-IRQ-002 (Start-up Disc: GBP → PI → GBP → GBP) and
GBP-IRQ-003 (GBI: PI in the raw handler → GBP in a thread); the PI
semantics are GBP-PI-001…003.

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

**Pointers added 2026-09-22 (GitHub Issue #48). THE STATUS LINE ABOVE IS
UNCHANGED and nothing here revises it.** This entry's claim is what the
SOFTWARE does with the register, read out of three reference implementations;
**the byte the DEVICE reports is a different proposition**, and it is carried
by its own ids: the presence bit's split over 36 runs and the causal reading it
supports (`GBP-HW-272` **with its 2026-09-22 amendment**, `GBP-HW-273`), and
the type bit's measured transition with its read-point distinction and its open
question (`GBP-HW-274`, `GBP-HW-275`, `U-GBP-036`). **Neither upgrades the
other**, which is the distinction `docs/protocol/REGISTERS.md` §3 sets out in
the paragraph beginning *"The usage column and the hardware column are
different claims"*. The hardware pages now carry both, stated apart:
`docs/hardware/GBS-DOL.md` (cartridge sensing) and
`docs/hardware/ARCHITECTURE.md` (control/status).

## GBP-KEY-001 — KEYPAD register

**Claim:** Index 0xC accepts a 16-bit value in bytes 0x1E–0x1F, 1 =
pressed, low byte in GBA KEYINPUT order (A,B,Select,Start,Right,Left,Up,
Down), L/R in bits 8–9. Both drivers rewrite it on every HSP interrupt
(DISC also every 5 ms). GBI writes 0 at start and 0x0304 (L+R+Select) on
the sleep IRQ.

**Status:** CORROBORATED (DISC `0x80089e40`; GBI; DOLPHIN `Keypad` write
→ `SetKeys`) — **Confidence:** high for format/polarity, **HYPOTHESIS**
for the L/R bit order (Dolphin swaps: hi bit0 → L, hi bit1 → R; U-GBP-010).

## GBP-KEY-002 — The Start-up Disc's keypad path: the write primitive, the state setter, the cadence and the controller → KEYPAD mapping — FACT (static)

Decompiled headlessly on 2026-09-21 from `sys/main.dol` (`3dd3692f…1b5d`,
Issue #18; `docs/research/INPUT_PATH.md`). **Write primitive `0x80089e40`:**
stores `value >> 8` at byte 0x1E and `value & 0xFF` at byte 0x1F of the
32-byte staging buffer at `0x801E4A60`, flushes it and DMAs it to
`base + 0xC00000` (direction write) — the other 30 bytes are whatever the
previous transfer left, the same convention as the IRQ write `0x80089ff4`.
**State setter `0x8008ad30(word, callback)`:** when the detection injection
is not active, stores the caller's word into the small-data global
`r13 − 0x7028` after clearing an opposite pair held together (`(v & 0xC0) ==
0xC0 → v &= ~0xC0`; `(v & 0x30) == 0x30 → v &= ~0x30`); while injecting, it
keeps the injected bits 0xF0 and takes the caller's other bits (`& 0xFF0F`).
**Cadence:** the handler `0x8008af08` writes the word to the device at `+0x74`
on every HSP interrupt that carries a pending source, right after the IRQ
write-back and before the callbacks — and the setter's second argument, a
one-shot callback kept at `r13 − 0x7024`, is invoked right after that write
and cleared; the 5.000 ms periodic callback
`0x8008b1ac` writes it on every tick while the session is running (state 2),
at two sites (`0x8008b900`, `0x8008bac4`). **Mapping `0x8000822c`** (the
application's caller of the setter; the other caller `0x8000a2e8` sends 0 =
release all): from the SDK pad word at `+0x18` of the disc's pad structure,
default mode — bit 8 (A) → word bit 0, bit 9 (B) → 1, bits 10 and 11 (X, Y)
→ 2, bit 12 (Start) → 3, bit 1 (Right) → 4, bit 0 (Left) → 5, bit 3 (Up) → 6,
bit 2 (Down) → 7, **bit 6 (L) → 8, bit 5 (R) → 9**, with four flag bits
24–27 of the extended word feeding the same four direction bits
(stick-derived, H for the identification); alternate mode (`+0x8c == 1`):
L and R → 2 (Select), **Y → 8, X → 9**, with bits 16–19 as a second direction
source. Z does not appear in the mapping (GBATEK: the Disc's own menu).
**Status:** FACT (static) for every instruction-level statement; the
identification of the extended flag bits as stick directions is H. Nothing
here is a physical observation of the device.

## GBP-KEY-003 — GBI's keypad path: the word, its builders, the per-pass 64-byte block, the sleep pulse and the controller tables — FACT (static)

Decompiled headlessly on 2026-09-21 from the unpacked image
(`0b2c44ea…84b0`, wrapped at `0x80003100`; Issue #18). `_SDA_BASE_ =
0x800b4b20` from the entry code, so the keypad word `r13 + 0x37c` is
`0x800b4e9c`; it is written at `0x8000c04c` (`:= 0` at thread start),
`0x8000c0f0`, `0x8000c904` and `0x8000cbc4`, read at `0x8000c174`. **Block
builders:** `0x80015da0` replicates a u16 into a u32 (`rlwimi`) and falls
through into `0x80015da4`, which fills the eight words of a 32-byte block
with that u32 and flushes it — the u16 sixteen times, `hi lo hi lo …`;
`0x80015ddc(buf, a, b)` builds a 64-byte block whose first half is `a` and
second half `b` in that layout. **Per pass:** built at `0x8000c184`, written
at `0x8000c194` as `0x8000bea4(0xcfffe0, block, 0x40)`
with `a` = the keypad word and `b` = `IRQ read | 0x8000` — the first half
lands at offset 0xFFFE0 of the KEYPAD window, the second at `base +
0xD00000`; `KEYPAD := 0` once at `0x8000c060` (32 B at `base + 0xC00000`,
built by `0x80015da0` at `0x8000c050`) before the CONTROL transform. **Sleep
source 0x0010:** built at `0x8000c4b4`, written at `0x8000c4c4` as
`0x8000bea4(0xc00000, block, 0x40)` with `0x0304` in the first half and
`0x0300` in the second — the second half lands at offset 0x20 of the KEYPAD
window; 0x0304 sets bits 2, 8 and 9 together and therefore discriminates
nothing about bits 8/9. **Controller tables** (service thread, every table OR-ed into one word):
four entries of 12-byte stride (the libogc `PADStatus` layout) — A 0x100 →
bit 0, B 0x200 → 1, Z 0x10 → 2 (Select), Start 0x1000 → 3, Right 0x2 or
stick X > 50 → 4, Left 0x1 or stick X < −50 → 5, Up 0x8 or stick Y > 50 →
6, Down 0x4 or stick Y < −50 → 7, **L 0x40 or trigger L > 100 → 8, R 0x20
or trigger R > 100 → 9**, Y 0x800 → 2 unless an option (`0x800b0a54`)
redirects it to a flag, with two sub-tables chosen by an analogue signature
(not traced); four entries of 10-byte stride — the same buttons, analogue
A / B > 100 counting as A / B, stick X at ±25, the same **L → 8, R → 9**;
four N64 entries of 6-byte stride — A 0x80 → 0, B 0x40 → 1, Z 0x20 → 2,
Start 0x10 → 3, D-pad or stick at ±40 → 4–7, **L 0x2000 → 8, R 0x1000 → 9**
(the N64 wire format's byte 1 bits 5 and 4); one device read at
`r13 + 0x1a8` — 0x1400 → 8, 0x2800 → 9 (not traced). **Status:** FACT (static) for the code; GBI is
an independent mature implementation, not official software.

## GBP-KEY-004 — The static result on the L/R order: the Start-up Disc, GBI and Dolphin's model all put L at word bit 8 and R at word bit 9, the reverse of KEYINPUT — CORROBORATED for the encoding the references target; the physical routing NOT established — **2026-09-21, Issue #33: the physical routing ESTABLISHED as FACT (hw, the runs) for bits 8 and 9, and for bits 0–7, by the machine join of RUN 17 / RUN 18 (GBP-HW-270, §V7.4)**

From GBP-KEY-002 and GBP-KEY-003, lined up against GBATEK's KEYINPUT order
(bit 8 = R, bit 9 = L): the official Start-up Disc's default mode writes L at
bit 8 and R at bit 9 (`0x8000822c`; its alternate mode moves Y and X there
and says nothing about L/R); GBI does the same for GameCube pads and,
independently through the N64 wire format, for N64 pads (`0x8000bf30`);
Dolphin's model reads block byte 0x1E bit 0 as GBA key 9 (L) and bit 1 as
key 8 (R) and says "L/R triggers (need to be flipped)"
(`HSP_DeviceGBPlayer.cpp:601–605`, commit `c185d27`). GBI's sleep value
`0x0304` sets both bits and is **not** evidence for the order. **Status:**
FACT (static) for what each reference writes; **CORROBORATED** for the
encoding the two independent implementations target (one of them official),
with the auxiliary model agreeing; **NOT a physical FACT** — no measurement
on this project's hardware shows the GBS-DOL routing bit 8 to the AGB's L
line, the window is write-only in every reference and the AGB is the only
observer. Consequence: `REGISTERS.md`'s **H** for Dolphin's order stands;
no order is adopted, implemented, tabulated as Open-GBP's own or defaulted
(Issue #18); U-GBP-010 stays OPEN on its own closing condition, with this
result recorded there. What would make it FACT: a project-owned stimulus that
publishes KEYINPUT into its video frames, joined to the runtime's own write
schedule, on this hardware.

**2026-09-21, Issue #19 (software, not evidence about the device):** by the
Operator's decision the runtime now implements this CORROBORATED assignment
as data, in exactly one place (`src/gbp/gbp_input.c`, `GBP_KEYPAD_DESCRIPTOR`,
with this status and its falsifier at the definition), so that the first
physical run falsifies or keeps it. The status of this row is unchanged:
CORROBORATED, not FACT; `REGISTERS.md` keeps H; U-GBP-010 stays OPEN
(GBP-KEY-006 carries the implementation facts).

**2026-09-21, Issue #26 (promotion; no status change):** after RUN 14 / RUN 15
(GBP-HW-263, GBP-HW-264, GBP-HW-265; U-GBP-010 CLOSED) the consolidated pages
carry this order as CORROBORATED, not FACT — `REGISTERS.md` §2 / §2.3 (H
until 2026-09-21), `docs/hardware/GBS-DOL.md`, `docs/hardware/ARCHITECTURE.md`
and the new `docs/protocol/INPUT.md` — each with the generic-pad scope
(GBP-HW-261) and GBP-KEY-009 beside it. The status of this row is unchanged.

**2026-09-21, Issue #33 (the falsifier's outcome; promotion):** the
descriptor's assignment — bit 8 = L, bit 9 = R, kept since `0ff8355` "so that
the first physical run falsifies or keeps it" — was put to the machine join
of §V7.3.9 in RUN 17 (generic third-party pad) and RUN 18 (original Nintendo
pad) on `stream-0015`: the runtime's own KEY record of the word it sent at
each change, joined to the checker's counters decoded from the preserved
frames, reads Question J = FACT for bits 8 and 9 in both runs and for bits
0–7 across them (GBP-HW-267, GBP-HW-269, GBP-HW-270; `HARDWARE_TESTS.md`
§V7.4.7). **The physical routing of the KEYPAD word to the AGB's keys is a
FACT (hw, the runs): the GBS-DOL delivers word bit 8 to L and word bit 9 to
R — the reverse of KEYINPUT, as this row's static result said — on this
hardware, through two controllers, with no human count in the chain.** The
static result above stays what it is (FACT for what each reference writes;
CORROBORATED for the encoding they target); what changed is that the physical
routing is now established, by GBP-HW-270, not by anything here. The
consolidated pages carry F (hw, run-scoped) with this history
(`REGISTERS.md` §2 / §2.3, `GBS-DOL.md`, `ARCHITECTURE.md`,
`INITIALIZATION.md` §15, `INPUT.md`); U-GBP-010 stays CLOSED; the descriptor
does not change. Scope: latency, the refresh, pads other than the two
declared, other ports or cartridges and a game are not established (GBP-HW-270).

## GBP-KEY-005 — The Disc's detection handshake on the keypad side, and GBATEK's AGB-side observation of it — FACT (static) for the Disc; CORROBORATED for polarity and the direction bits 4–7 at the window

Once its embedded logo frame (GBP-VID-010, the 44-colour Game Boy Player
logo GBATEK's "Unlocking and Detecting Gameboy Player Functions" describes)
has matched for 40 consecutive blocks, the Disc's `0x8008c31c`, called from
the 5 ms tick, ORs `0x00F0` into the keypad word for five ticks and clears it
(`& 0xFF0F`) for five, a 10-tick cycle of 50 ms, for up to 24 000 ticks
(GBP-VID-011, GBP-VID-014). GBATEK records, from the AGB side, KEYINPUT
switching between `0x03FF` (2 frames) and `0x030F` (1 frame) — bits 4–7 low,
Right, Left, Up and Down pressed — while the logo is shown. The bits the
Disc sets at word bits 4–7 are the bits the AGB observes cleared at KEYINPUT
bits 4–7. **Status:** FACT (static) for the Disc's behaviour; CORROBORATED
(the official driver plus an external hardware observation) that at this
window 1 = pressed and that word bits 4–7 reach KEYINPUT bits 4–7 in the same
order. Width: those four bits only; nothing about bits 0–3 or 8–9; not an
Open-GBP measurement.

## GBP-KEY-006 — The input path implemented as software: the module, the one-place descriptor, the block layout, the placement, the refresh policy and the candidate `stream-0014` — FACT (software); nothing physical

Issue #19 (2026-09-21), commit `0ff8355`. **Module** `src/gbp/gbp_input.{h,c}`,
pure and host-tested: `gbp_input_map` (L3, a policy table as data —
`GBP_INPUT_POLICY_DEFAULT`: A, B, Start and the D-pad 1:1, X and Y = Select,
Z reserved and never sent, L / R on the digital click, the main stick as the
D-pad beyond ±48, opposite directions filtered, port 1); `gbp_keypad_encode`
/ `gbp_keypad_decode` (L1, a descriptor applied bit for bit, unused bits 0);
`gbp_keypad_block` (GBI's u16-replicated layout, bytes 0x1E/0x1F = hi/lo);
`gbp_keypad_write` (one 32-byte `write_block` at `base + (0xC << 20)` through
the existing transport: real backend, mock, replay); `gbp_input_step` (write
on the first pass, on change, and every `GBP_INPUT_REFRESH_MS` = 5 ms, the
Disc's period, with a one-period back-off after a failed write). **The
descriptor** `GBP_KEYPAD_DESCRIPTOR` is defined once, as data, with its
status — CORROBORATED, NOT FACT (GBP-KEY-004; U-GBP-010 OPEN) — and its
falsifier at the definition; flipping it is one line, and no test depends on
its L/R positions (`tests/host/test_input_impl.py` pins all of this).
**Placement** (`poc/gbp-video-stream-probe/source/main.c`): `input_step()` is
the first statement of `pump()`, i.e. inside the slot `gbp_vqueue_pump()`
admits after the RE-ARM only when no cause is pending; `PAD_ScanPads()` from
the main loop; every instant through the transport's `ticks` / `ticks64`, so
the stream audit's `gettime` sites are unchanged (`pump` 5, `main` 8); the
consumer slice's own measurement starts after it. `t_poll` / `t_write` are
fields; nothing emits them. The service path, Policy A, the witness layer,
the disposition trace, the frozen writers, `tools/`, `docs/protocol/` and
`docs/hardware/` are byte-identical to `a877284`. **Candidate**
`build/poc/gbp-video-stream-probe/gbp-video-stream-probe.dol`: `stream-0014`,
embedded commit `0ff8355` (clean, no `-dirty`), 513 152 bytes, SHA-256
`ef76a170c10d335e62c017e53f74c60e410e44f5ce2fbca6774ab43c68ec0b9c`; built in
`ghcr.io/extremscorner/libogc2:20260805` with **zero warnings**, none
suppressed; two consecutive clean builds byte-identical; ELF text 402 900 /
data 109 936 / bss 20 093 452; `make stream-audit`: 0 findings, interrupt
path identical to the GBP-VIDEO-001 reference. **Not executed on hardware; no
run name reserved; no run pre-registered.** **Host tests:**
`tests/unit/test_gbp_input.c`, 8 453 checks (every button; the stick, trigger
and analogue thresholds at the boundary; the filtering; arbitrary synthetic
descriptors; the write through the mock by address, length and bytes and
through the replay by its script; the refresh policy at its boundaries; the
back-off); `make test-python` green. **Dolphin (AUXILIARY, never physical):**
device absent and Dolphin's GBP model both PASS on the stated conditions —
READY identity = build-info, `SELFTEST ok=1`, `INPUTSELFTEST ok=1` (the
module's pure self-test executed on the target, no device touched),
`COUNTERS balanced=1`, `INPUT selftest=1 steps=0 attempts=0 completed=0
failed=0`; the probe stopped before any service cycle in both (absent; the
model refused at the CONTROL shape as it did for stream-0013), so the slot,
and with it the KEYPAD write, never ran in Dolphin. No Open-GBP build has
ever issued a KEYPAD write anywhere. **Status:** FACT for what the software
is and does; nothing here is evidence about the device.

## GBP-KEY-007 — The Start-up Disc's controller behaviour on this hardware as recalled by the Operator, and its composition with the Disc's static alternate-mode mapping — OPERATOR OBSERVATION (recollection); changes no status

Issue #22 (2026-09-21), relayed by the Orchestrator; `docs/research/INPUT_PATH.md`
§10.2–§10.3. **The recollection:** from past use of the official Start-up Disc
on this hardware — X and Y act as SELECT; L and R act as L and R; an OSD
option inverts this (L and R → SELECT, Y → L, X → R); the left analogue stick
and the D-pad have the same effect; the C stick has no effect; Start is
START; Z opens the Disc's OSD. **Classification: OPERATOR OBSERVATION, and a
recollection of past use rather than an observation under a pre-registered
procedure** — weaker than RUN 14's report will be; not verified by the
Executor. **Corroboration:** every item agrees with the implemented default
policy (GBP-KEY-006: X and Y → Select, L / R on their clicks, the stick as
the D-pad, the C stick unread, Start → Start, Z reserved and never sent); the
policy rested on the Disc's decompiled code (GBP-KEY-002) and now also on its
observed behaviour, as a recollection. Z unmapped is the button the Disc
reserves for its OSD. **The composition:** T1 (FACT, static, GBP-KEY-002) —
the alternate mode sends PAD Y to word bit 8 and PAD X to bit 9; T2 (this
recollection) — with the swap option on, Y acts as L and X as R; under the
identification of the option with the decompiled mode (supported by the
match of all three roles and the code's two modes), the two compose to
word bit 8 = L, bit 9 = R — the assignment GBP-KEY-004 records, reached with
one hardware-side term, independent of the static agreement of the Disc,
GBI and Dolphin. It holds as logic on two conditions: that identification,
and the exact X/Y attribution — remembered the other way round, the same
composition gives the opposite answer. **Consequence:** GBP-KEY-004 stays
CORROBORATED, not FACT; U-GBP-010 stays OPEN for RUN 14; the descriptor is
unchanged; `REGISTERS.md` keeps H. What would make it a recorded
observation: the written Disc re-verification of INPUT_PATH.md §10.3 —
still OPERATOR OBSERVATION, never FACT. **Status:** OPERATOR OBSERVATION
(recollection); nothing physical was measured by this project.

## GBP-KEY-008 — The `ENVINPUT` record of `stream-0014` exceeds the 248-character ringlog payload and is clipped after `desc_status=CORROBORATED_n` (`truncated=1` in RUN 14 and RUN 15) — FACT (software); NOT repaired here

Both RUN 14 and RUN 15 logs carry `lines=686 dropped=0 truncated=1`
(GBP-HW-262). Derived exactly as runs 9 and 10 derived their `WITELIG` clip
(GBP-VID-033, §V5.58.1): `LOG_LINE_LEN 256` minus the 7-character `%06u `
prefix and the NUL leaves 248 payload characters; the one record at 248 in
each log is `ENVINPUT` (seq 3), new in `stream-0014` (Issue #19,
`poc/gbp-video-stream-probe/source/main.c:1216`), whose format renders to 266
characters with this build's values (recomputed by rendering the source
format) and is therefore clipped after `desc_status=CORROBORATED_n`;
`src/log/ringlog.c:46` counts the cut. Lost: `ot_FACT selftest=1` — the
descriptor's status label (a constant of the format string) and the selftest
flag (repeated verbatim in the `INPUT` record, which is complete). The next
longest payload is `STARTUPT` at 218; the four binary sidecars are unaffected;
no gate figure is derived from the clipped fields. It is the same reporting
class `stream-0011` repaired for `WITELIG` and the guard GBP-VID-033 asked for
("no required summary line can exceed the payload") was never added, so the
new line was never checked. Consequence: the §V7.1.8 IDENTITY / LOG line's
`truncated=0` is met with this one recorded exception, the INPUT machine gate
reads from complete records, and the Orchestrator's classification stands.
Repair — split or shorten the line and add the host guard — belongs to a
functional Issue; nothing under `src/`, `poc/` or `tools/` moved here.

**2026-09-21, REPAIRED IN SOFTWARE (Issue #27, `stream-0015` @ `da06500`;
physical validation PENDING).** The record is emitted as two, the way
`stream-0011` repaired `WITELIG`: `ENVINPUT` (port, policy, the thresholds,
the filter, refresh_ms, refresh_ticks, layout — worst case 229 of 248 at the
maximum width of every conversion) and `ENVINPUT2` (index, desc,
pressed_is_one, desc_status, selftest — worst case 222); every field name
unchanged, no buffer enlarged, `ringlog.c` untouched, both emitted before the
run in that order. The guard this row asked for exists and is GENERAL:
`tests/host/test_ringlog_payloads.py` renders every `ringlog_printf` of the
probe at the worst case of every conversion, with every `%s` bounded by the
vocabulary of its source, and fails a test — not a run — for any record
over the payload (GBP-KEY-010 records its two tiers). RUN 14 and RUN 15 keep
`truncated=1` as `stream-0014` facts; their fixtures and derivations are
unchanged. **Nothing here is hardware-validated.**

**2026-09-21, Issue #33: REPAIRED and PHYSICALLY VALIDATED.** The repair of
Issue #27 (GBP-KEY-010: `ENVINPUT` + `ENVINPUT2`) ran in RUN 17 / RUN 18 / RUN
16 on `stream-0015`: all three logs read `truncated=0` with ENVINPUT at 170
and ENVINPUT2 at 105 characters, both complete, and the §V7.3.8 gate that
made `truncated=0` a requirement again is met (GBP-HW-267; §V7.4.4). RUN 14 /
RUN 15 keep `truncated=1` as `stream-0014` facts.

## GBP-KEY-009 — What would make the L/R routing a FACT is one log line: the word written at each key change, binding every press to what the runtime sent — FINDING (software / data); recorded, NOT implemented

§V7.1.10 supposed that FACT for U-GBP-010 needed a project-owned stimulus
publishing KEYINPUT into its own video frames. RUN 14 and RUN 15 (GBP-HW-262,
GBP-HW-264, GBP-HW-265) show the missing link is smaller: the routing chain's
only non-machine link is "the Operator pressed L exactly once", because the
`INPUT` record counts key changes (42) without the words, while the preserved
frames record what the cartridge displayed. One log line — the word written
at each key change, timestamped in the frames' time base (`change` is already
counted and the word is in hand at the write) — would bind every press to
what the runtime sent and close the join by machine end to end: word sent
(log) ↔ counter that moved (frames). Any later checker run carrying that
line would hold the fourth link as data. The project-owned stimulus remains
the instrument the latency question needs (`INPUT_PATH.md` §8) and stays a
recorded future option. Neither is authorised by Issue #24; the module and the
POC are unchanged since `0ff8355`; the routing stays CORROBORATED (GBP-HW-265).

**2026-09-21, IMPLEMENTED IN SOFTWARE (Issue #27, `stream-0015` @ `da06500`;
NOT executed, no run name, not staged).** Every KEYPAD write that is not a
refresh — first, change, retry — leaves one ringlog line, `KEY n= act= keys=
word= t_poll= t_attempt= t_done= xfer= rc=`, emitted from the pump slot right
after the write it describes, with the three instants in the transport's
ticks64 base — the base of OGBPIDXCAP1, OGBPDISP2 and OGBPVI1 — so the join a
future run needs (the word sent at `t_attempt..t_done` ↔ the first source
frame that shows the cartridge's reaction, by `t_first_block` / `t_take`)
needs no conversion; a refresh never produces a line. Bounded by the ringlog
itself with a 64-line reserve for the post-run records, counted when refused
(GBP-KEY-010 has the facts). **The routing stays CORROBORATED: FACT is now
REACHABLE by a run that joins this record to an instrument showing what the
AGB received; only such a run makes it actual.**

**2026-09-21, Issue #33: the run happened and the join closed.** RUN 17 and
RUN 18 (`stream-0015`, Hardware Issue #32) carried the line; joined to the
checker's counters exactly as §V7.3.9 froze it, Question J = FACT for every
pressed word bit — bits 8 and 9 on two controllers (GBP-HW-270; §V7.4.7).
The finding this row recorded is spent: the routing is FACT (hw, the runs).

## GBP-KEY-010 — The per-change KEYPAD record and the ENVINPUT repair as software: the KEY line, its bound, the general payload guard and the candidate `stream-0015` — FACT (software); nothing physical

Issue #27 (2026-09-21), commits `cee9165` (the record) and `da06500` (the
repair and the guard). **The record** (`src/gbp/gbp_input.{h,c}`): every write
whose action is FIRST, CHANGE or RETRY fills `struct gbp_input_event` — the
event number, the action, the logical set, the word, `t_poll` (the caller's
instant after `PAD_ScanPads()`), `t_attempt` (the transport's instant before
`write_block`) and `t_done` (after a completed write; 0 otherwise), the
completion wait and the status — and the caller takes it once
(`gbp_input_take_event`); a REFRESH never does (RUN 14: 7 849 refreshes
against 42 changes). THE ONE FORMAT `GBP_INPUT_EVENT_FMT` = `KEY n=%lu act=%s
keys=%04x word=%04x t_poll=%llx t_attempt=%llx t_done=%llx xfer=%lu rc=%s`,
rendered by `gbp_input_event_render()` on the host and by the probe's
`ringlog_printf` with the same argument list; worst case over every conversion
**158** characters (derived in `tests/unit/test_gbp_input.c` and
`tests/host/test_input_keylog.py`; the two `%s` are 7-character vocabularies),
against the 248-character payload. **The emission point**
(`poc/gbp-video-stream-probe/source/main.c`, `keylog_emit()`): in
`input_step()`, right after the write and after the step's own measurement,
from the pump slot — never from the ISR, never inside the service transaction
— through the transport's clock (the stream audit's `gettime` pins of `pump()`
and `main()` unchanged); armed with the run (`keylog_rl`) like
`in_transport`. **The bound** (CLAUDE.md §13): the store is the ringlog
itself, preallocated (`LOG_LINES 1024`, never grown); a line is admitted only
while `KEYLOG_TAIL_RESERVE` = 64 lines stay free for the post-run summary
records (27, counted by the test), so a run with more changes than the
headroom holds — ≈ 700 lines after the pre-run records — keeps every summary,
keeps `dropped=0`, and counts the surplus in `KEYLOG lost`; `truncated` and
`overwritten` are counted and 0 by construction; the line's cost is measured
with the transport's ticks (`KEYLOG emit_ticks`) outside the INPUTT step
aggregate, so RUN 14 / RUN 15's step figures stay comparable. **The repair**
(GBP-KEY-008): `ENVINPUT` 229 / `ENVINPUT2` 222 at the worst case, every field
kept. **The general guard** (`tests/host/test_ringlog_payloads.py`): every
`ringlog_printf` of the probe rendered at the worst case of every conversion
for powerpc-eabi (ILP32), every `%s` bounded by the vocabulary of its source
and the vocabularies checked against the code, every conversion matched to
an argument; STRICT for ENVINPUT, ENVINPUT2, KEY, KEYLOG, WITELIG, WITELIG2;
a RATCHET for the four older records that exceed 248 at the pure type width —
ENVSTORE 303, INPUT 269, WITQUAL 307, DISPTRACE 253 — frozen at today's
value (any growth, or any new record over 248, fails a test rather than a
run; their largest physical rendering in the versioned RUN 14 / RUN 15
records is far below the payload), and the `stream-0014` ENVINPUT shown to
exceed it, so the guard can fail. **Unchanged:** the descriptor and the
policy (byte-equal to `0ff8355`, pinned), the witness layer, the service path,
Policy A, the disposition trace, every frozen format, `tools/`,
`docs/protocol/`, `docs/hardware/`, `HARDWARE_TESTS.md` §V7. **Candidate**
`build/poc/gbp-video-stream-probe/gbp-video-stream-probe.dol`: `stream-0015`,
embedded commit `da06500` (clean, no `-dirty`), 514 880 bytes, SHA-256
`dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49`; built in `ghcr.io/extremscorner/libogc2:20260805` with
zero warnings, none suppressed; two consecutive clean builds byte-identical; ELF text 404044 / data 110508 / bss 20093556; `make
stream-audit`: 0 findings (the ext and base one-shot handlers identical to the physically validated GBP-VIDEO-001 build). **Host tests:** `tests/unit/test_gbp_input.c` 8 505
checks (52 new: the events, the render at the worst case, the bound);
`make test-python` green. **Dolphin (AUXILIARY, never physical):** device
absent — RESULT PASS (4.2 s) on the stated conditions: READY build=stream-0015 commit=da06500, INPUTSELFTEST ok=1 device_touched=0, COUNTERS balanced=1 sci_clean_at_probe=1 inv_fail=0 storage_fault=-; Dolphin's GBP model — RESULT PASS (4.1 s) on the same conditions (HSPDevice=2, GBPlayerRom). In both the
probe stops before any service cycle (the model refuses at the CONTROL shape,
as for stream-0013 / 0014), so the pump slot never runs there: neither the
KEYPAD write nor the KEY record is exercised by Dolphin, and nothing about them
is covered by it. **NOT executed on hardware; no run name reserved; nothing
pre-registered; `build/swiss/` untouched** (staging belongs to a hardware
checkpoint). **Status:** FACT for what the software is and does; nothing here
is evidence about the device; the routing stays CORROBORATED (GBP-KEY-009).

**2026-09-21, Issue #33: EXECUTED on hardware** — RUN 17, RUN 18 and RUN 16
(Hardware Issue #32; `HARDWARE_TESTS.md` §V7.4): the record behaved exactly as
designed on its first exercise — `KEYLOG events = emitted = 43 / 43 / 33, lost
0, truncated 0, overwritten 0`, every line parsed under the one format, the
64-line reserve never approached, emit cost 871–1 748 ticks outside the INPUTT
aggregate; ENVINPUT / ENVINPUT2 complete, `truncated=0` (GBP-HW-267). Joined to
the frames, the record made the routing FACT (GBP-HW-270). The
`desc_status=CORROBORATED_not_FACT` label this image prints is now stale — a
one-line label change in a future build, recorded, not made.

## GBP-VID-001 — VIDEO data format and cadence

**Claim:** Index 0x1 delivers 0xF00 bytes per VIDEO IRQ = 4 scanlines ×
240 pixels × 4 bytes; 40 blocks per 160-line frame. Each 32-bit word is a
16-bit color with both bytes doubled; bit 15 of the first pixel of a
frame's first block is set (mask 0x80800000 after doubling).

**Status:** CORROBORATED (DISC: 0xF00 reads, a ring of 40 × 0xF00 = 0x25800
bytes, frame buffers of 0x12C00 = 240×160×2 (RGB5A3), a dummy first block
whose first halfword is OR-ed with 0x0080 = bit 7 of byte 1; GBI: 0xF00
reads on bit 0x100, frame-start test `(word0 & 0x80800000) == 0x80800000`,
block index `(i + 1) % 0x28`; DOLPHIN `PrepareScanlineData`/`Read(Video)`;
PR #14535 "mirroring aligns with actual hardware behavior per hardware
researcher consultation"; corrected and detailed 2026-09-16 in
`docs/research/VIDEO_PATH.md`, GBP-VID-002…007) —
**Confidence:** high for geometry/flag, medium for color bit order (Dolphin
`M_RGB8_TO_RGB5`, GBA palette order) — U-GBP-011. **Hardware 2026-09-16
(GBP-AV-SERVICE-001, GBP-HW-051/058):** one DMA of 0xF00 bytes from index
0x1 completed (61.4 µs around the call) on the first VIDEO request after
the initialization, with no cartridge; first word `0xFFFFFFFF` — the GBI
frame-start predicate true on the first block read; 954 of the 960 groups
`7F 7F FF FF`, five `FF 7F FF FF` (byte doubling broken in those five),
no zero byte. Recorded raw, not interpreted; the geometry (4 lines × 240)
is not tested by one block (a DMA of the requested length completes
regardless), so the status stays CORROBORATED.

## GBP-AUD-001 — AUDIO data size and cadence — **2026-09-22, Issue #67: the model splits in two and the halves get DIFFERENT answers — the RATE (4096 Hz) is CORROBORATED BY HARDWARE to four figures (`GBP-HW-301`), the BYTE LAYOUT is REFUSED (`GBP-HW-287`, `GBP-HW-296`); read the amendment before copying a status from these words**

**Claim:** Index 0x8 delivers 0x1000 bytes per AUDIO IRQ; DISC keeps 70
ring buffers and feeds them to its audio pipeline; GBI reads 0x1000 on
bit 0x400. Dolphin models the content as 0x400 PWM bytes each mirrored ×4,
produced at 4096 Hz, 1 bit per 32-bit word after mirroring, and notes the
DISC only accepts words whose 1-bits are contiguous and leading.

**Status:** CORROBORATED for size/IRQ; **HYPOTHESIS** for the PWM format
(Dolphin only) — U-GBP-012. **Hardware 2026-09-16 (GBP-AV-SERVICE-001,
GBP-HW-050/057):** one DMA of 0x1000 bytes from index 0x8 completed
(66.5 µs around the call) on the first AUDIO request, no cartridge; 3969
zero bytes, values `00`/`01`/`11` only, the non-zero bytes at offset 0 of
123 of the 128 32-byte lines plus four isolated bytes. Recorded raw; the
PWM model is neither confirmed nor rejected by it.

**AMENDED 2026-09-22 (GitHub Issue #67's validation) — the model has TWO parts
and RUN 31 answers them DIFFERENTLY. Do not read "Dolphin was wrong".**

```text
THE RATE        Dolphin says 4096 Hz. RUN 31 measures 4 096.0 blocks/s with ONE BLOCK = ONE SAMPLE,
                recovered INDEPENDENTLY from two windows at two known frequencies (GBP-HW-298, GBP-HW-301).
                -> CORROBORATED BY HARDWARE TO FOUR FIGURES.
THE BYTE LAYOUT Dolphin says 0x400 PWM bytes mirrored x4, 1 bit per 32-bit word, 1-bits contiguous and
                leading. RUN 30 and RUN 31 refuse it: the bytes are not contiguous-leading (GBP-HW-287),
                the 256-byte cell is the TRANSFER's and is present with the APU provably off
                (GBP-HW-296), and the audio is the modulation ACROSS blocks, not within one.
                -> REFUSED, and that is the half U-GBP-012 still carries.
```

**Why the distinction is worth minting rather than leaving implicit:** *"the
PWM model is refused"* is what the last three entries say, and a later reader
would take it to mean the whole model failed. **It did not: the cadence
Dolphin's model was built around is exactly the cadence the hardware
delivers**, and only the arrangement of bytes inside a block is wrong.

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

---

## Physical observations — GBP-PROBE-001, 2026-09-14

All entries below come from one run on the user's GameCube + Game Boy
Player (setup in HARDWARE_TESTS.md; log sha256 `98ba20d5…f014`). "FACT"
means observed in that run; one console, one run, no cartridge.

## GBP-HW-001 — AR_INFO state and the controlled A/B change

**Claim:** At probe start `0xCC005012` read `0x0043` (size code 3 = 16 MB,
expansion code 0, bit 6 set). Writing `(0x0043 & ~0x0038) | 0x0018` gave
`0x005B` (read back twice); writing `0x0043` back restored it (read back
`0x0043`). The DSP CSR read `0x0804` throughout (DSPINIT|HALT in libogc2
naming). **Status:** FACT. **Confidence:** high.

## GBP-HW-002 — All 28 ARAM-DMA transfers to the expansion window completed, in both modes

**Claim:** 12 reads and 8 writes (MODE A and B, TEST/CONTROL/IRQ windows at
`0x01000000 + idx<<20`) plus 8 handshake reads completed with CSR bit 5
set after 7–10 polls, 30–37 time-base ticks (≈0.75–0.9 µs at 40.5 MHz)
each, no timeout, no busy refusal — with AR_INFO expansion code 0 (MODE A)
as well as 3 (MODE B). **Status:** FACT. **Confidence:** high.
**Consequence:** the DMA engine does not stall or refuse when the
expansion code is 0; U-GBP-004 is not "required for the DMA to run".

## GBP-HW-003 — TEST inversion observed in both modes; byte 0 anomalies

**Claim:** For every handshake (C3, 3C, FF, 00 in MODE A and again in
MODE B) the read-back had bytes 1–31 equal to the complement of the
pattern. Byte 0 differed in three cases, always by *extra* set bits:
MODE A C3→`7C` (expected `3C`, extra `0x40`), MODE A 3C→`C7` (expected
`C3`, extra `0x04`, and byte 6 also `C7`), MODE B 3C→`C7` (extra `0x04`).
MODE B C3 and all FF/00 handshakes were uniform. **Status:** FACT.
**Confidence:** high for the bytes; no explanation yet (U-GBP-015).
Software causes were audited and excluded (DEVLOG 2026-09-14): buffer
`0x80058080`, 32-byte aligned, own cache line, zero-filled + `dcbf/sc`
then `dcbi` before the DMA and `dcbi` after; a stale line would show the
zero fill or the previous 32 bytes, not a single extra bit.

## GBP-HW-004 — Read block layout of the IRQ window is byte-doubled `hh hh ll ll`

**Claim:** In MODE B the IRQ window read `ae 8a ae ae | 8a 8a ae ae ×7`:
words 1–7 are `8A 8A AE AE`, i.e. a 16-bit value `0x8AAE` with each byte
repeated; word 0 has the byte-0 anomaly (`AE` where the pattern predicts
`8A`). Bytes 0x1D/0x1F (DISC) and bytes ≡1/≡3 mod 4 (GBI vote) both yield
`0x8AAE`. Dolphin's IRQ read model `hh hh hh ll` would put `8A` at
0x1E; hardware put `AE` there. **Status:** FACT (layout for this register
in this run). **Confidence:** high for the bytes; the byte-doubling rule
is CORROBORATED by DISC's parsing and GBI's vote positions and now one
hardware block — U-GBP-008 partially answered.

## GBP-HW-005 — CONTROL and IRQ windows read differently in MODE A and MODE B

**Claim:** MODE A (exp code 0): CONTROL `00×32` (both dumps), IRQ
`90×32` (both dumps). MODE B (exp code 3): CONTROL `94 90×31` then
`90×32`; IRQ `ae 8a ae ae 8a 8a ae ae…` (both dumps). TEST read `00×32`
in every raw dump of both modes. Changing only AR_INFO bits 3–5 therefore
changed what the CONTROL and IRQ windows return, while the TEST handshake
worked in both modes. **Status:** FACT. **Confidence:** high for the
bytes. **Not established:** whether MODE A values come from the GBS-DOL,
from the ARAM controller or from the bus (U-GBP-004 reformulated,
U-GBP-016); what `0x90`, `0x94`, `0x8AAE` mean (U-GBP-017).

## GBP-HW-006 — TEST window reads 00 when not immediately following a write

**Claim:** Every raw TEST dump (before the handshake and right after its
last read) returned `00×32`, although the last handshake write had been
32×`00` (whose read-back was `FF×32`). The complement is therefore only
observed on the read that follows the write; a second read returned
zeros. **Status:** FACT for this sequence. **Confidence:** medium (the
zero fill of the DMA buffer is also `00`, so a DMA that transferred
nothing would look identical — see DEVLOG limitation L2). Dolphin's model
(persistent `data ^ 0xFF`) would have returned `FF×32`.

---

## Physical observations — GBP-BASELINE-NOGBP-001, 2026-09-14 (GBP removed)

## GBP-HW-007 — Without the Game Boy Player every window read `C0`×32

**Claim:** With the GBP physically removed and everything else unchanged,
the same DOL (`probe-0001`) read `C0` in all 32 bytes of TEST, CONTROL
and IRQ, in both raw dumps of both modes, and every TEST handshake
read-back was also `C0`×32 (0/8 by any criterion). AR_INFO behaved
identically to the GBP run (`0043 → 005B → 0043`). **Status:** FACT
for this configuration. **Confidence:** high (one run). **Origin of
`0xC0` is UNKNOWN** (U-GBP-019) — it is not to be called open-bus, ARAM
or "HSP default".

## GBP-HW-008 — DMA completion does not depend on the GBP: it is not presence detection

**Claim:** All 28 transfers completed with `rc=ok`, 7–10 polls, 31–38
time-base ticks, CSR `0x0804` after acknowledge — the same numbers as
with the GBP attached (GBP-HW-002). **Status:** FACT. **Consequence
(rule):** *DMA completion is NOT GBP presence detection.* A completed
transfer only says the ARAM DMA engine finished; presence must be judged
from the handshake content.

## GBP-HW-009 — Behaviors that depended on the physical presence of the GBP

**Claim:** In the tested configuration, removing only the GBP changed
every one of the 20 read blocks (640/640 bytes differ,
`tools/blockdiff.py --pair`): the TEST inversion (bytes 1–31 = ~pattern,
8/8) disappeared (0/8, `C0`); the byte-0 extra bits disappeared; CONTROL
`00`/`94`/`90` fills and IRQ `90`/`AE 8A…` patterns were replaced by
`C0`×32; and the difference between expansion code 0 and 3 in
CONTROL/IRQ disappeared (both `C0`). **Status:** FACT (dependency
observed) — no functional meaning is assigned to `90`, `94`, `AE`, `8A`
or `C0`. **Confidence:** high for the dependency (single pair of runs).

## GBP-HW-010 — Official TEST criteria applied to both physical runs

**Claim:** On the physical blocks, the Start-up Disc criterion (byte 1 ==
~pattern) and the GBI criterion (per-bit majority vote == ~pattern) both
pass 8/8 with the GBP attached and fail 8/8 without it, for all four
patterns in both modes; the whole-block criterion of probe-0001 passes
5/8 with the GBP and 0/8 without. **Status:** FACT (computed from the
captures; `tests/host/test_hw_fixture.py`, `tests/unit/test_gbp_detect.c`).

---

## Physical observations — GBP-INIT-001 (attached) and GBP-INIT-BASELINE-NOGBP-001 (removed), 2026-09-15

Same console and setup as 2026-09-14; DOL `init-0001`, commit `a3d9668`.
"FACT" = observed in that run; one run per state.

## GBP-HW-011 — The presence policy classified the physical GBP correctly in both states

**Claim:** With the GBP attached, the TEST handshake (C3, 3C, FF, 00, expansion
code 3) passed the Start-up Disc byte-1 criterion 4/4 and the GBI vote
criterion 4/4 (whole-block 3/4: the C3 response was `7C 3C…`), verdict
PRESENT. With the GBP removed both criteria failed 4/4 (all read-backs
`C1`×32), verdict ABSENT, and the probe wrote nothing to CONTROL and
restored AR_INFO. **Status:** FACT. This is the physical validation of
the safety gate of `gbp_init_probe`.

## GBP-HW-012 — PI state during the experiment

**Claim:** `INTSR = 0x00010000` and `INTMR = 0x000001FA` in every read
(PRE, S0…S5); bit 13 was 0 in both, so INTMR was left untouched. Bit 16
of INTSR (RSWST per YAGCD) was set throughout. **Status:** FACT.

## GBP-HW-013 — GBI's CONTROL transform was accepted and read back

**Claim:** With expansion code 3, CONTROL read semantically `0x90` (S0
raw `98 90×31`, vote = byte 0x1F = 0x90). The probe wrote
`(0x90 & ~0x10) | 0x0C = 0x8C` as `8C`×32 (GBI layout); the transfer
completed (rc ok, 31 ticks, 8 polls). CONTROL then read `0x8C` in S1,
S2 and S3 (bytes 1–31 all `8C`). Writing the original `0x90` as `90`×32
made CONTROL read `0x90` again in S4 (bytes 1–31 all `90`). **Status:**
FACT. No meaning is attached to bits 0x04/0x08/0x10.

## GBP-HW-014 — No observable PI INTSR bit-13 assertion, IRQ block unchanged in bytes 1–31

**Claim:** In the tested sequence — CONTROL `0x90 → 0x8C` with PI HSP
masked in INTMR, snapshots at 1.4 µs, 68 µs, 141 µs after the write,
and after the restore at 228 µs — PI INTSR bit 13 stayed 0 and the IRQ
block bytes 1–31 stayed `8A 8A AE AE` (semantic `0x8AAE`, both by the
disc's and GBI's reading). **Status:** FACT, restricted to this
sequence. It does not say that CONTROL bit 0x10 is unrelated to
interrupts: the rest of the GBI/Start-up Disc start (IRQ_Request,
unmask, IRQ-block programming) was not reproduced.

## GBP-HW-015 — Byte 0 of CONTROL and IRQ changed over time after CONTROL writes

**Claim (exact bytes, `tools/blockdiff.py --snapshots`):**

| Snapshot | ticks after EXP write | CONTROL byte 0 (bytes 1–31) | IRQ byte 0 (bytes 1–31 pattern) |
|---|---|---|---|
| S0 | before | `98` (`90`) | `AA` (`8A 8A AE AE`) |
| S1 | 56 (1.38 µs) | `EC` (`8C`) | `EA` (same) |
| S2 | 2756 (68.05 µs) | `AC` (`8C`) | `AA` (same) |
| S3 | 5719 (141.2 µs) | `AC` (`8C`) | `AA` (same) |
| S4 | 9231 (227.9 µs), after the RESTORE write | `98` (`90`) | `EA` (same) |
| S5 | 13787 (340.4 µs), after AR_INFO → 0x0043 | `00` (`00`) | `98` (`90`) |

Between S1 and S2 the only change in either block was bit 6 (`0x40`)
clearing in byte 0 of both (`EC→AC`, `EA→AA`); this is what
`TRANSITION s1_s2=1` recorded. S2→S3: identical. After the restore
write, IRQ byte 0 read `EA` again (bit 6 set) while CONTROL byte 0 read
`98` as in S0. **Status:** FACT for the bytes and timings. Bit 6 is not
named (U-GBP-021); CONTROL and IRQ byte-0 bits are not asserted to be
one signal.

## GBP-HW-016 — Restoration verified

**Claim:** `control_restored=1` (S4 vote and byte 0x1F = 0x90),
`arinfo_restored=1` (readback 0x0043), INTMR unchanged, 23 transfers,
0 timeouts, 0 busy, 0 errors, 0 dropped/truncated records. **Status:** FACT.

## GBP-HW-017 — Expansion code 3 → 0 changed the CONTROL/IRQ view again (second independent observation)

**Claim:** After AR_INFO was restored from 0x005B to 0x0043, S5 read
CONTROL `00`×32 and IRQ `98 90×31` (semantic `0x9090`), the same view
GBP-PROBE-001 MODE A showed with code 0 (`00`/`90`), while with code 3
the view was `0x90`/`0x8AAE` in both runs. **Status:** CORROBORATED by
two runs with different sequences (code 0 first vs code 3 first).
Meaning unknown (U-GBP-004); not "enable".

## GBP-HW-018 — Snapshot timing

**Claim:** Time-base ticks since the write at the start of each
snapshot: S1 56, S2 2756, S3 5719, S4 9231, S5 13787 (40.5 MHz). Every
DMA took 29–34 ticks (7–9 polls). The gaps between snapshots are the
probe's own logging cost (four `vsnprintf` records per snapshot), not
deliberate delays. **Status:** FACT.

## GBP-HW-019 — Without the GBP the uniform value was `C1`, not `C0`

**Claim:** In GBP-INIT-BASELINE-NOGBP-001 all eight TEST read-backs were
`C1`×32 (with expansion code 3 set before the first transfer); in
GBP-BASELINE-NOGBP-001 (probe-0001, 2026-09-14) all reads were `C0`×32
with codes 0 and 3. The two values differ in bit 0 of every byte.
**Status:** FACT. Generalization "no GBP = C0" is withdrawn; see
U-GBP-019 for the candidate explanations (none selected).

## GBP-HW-020 — Transport does not distinguish the two states

**Claim:** With and without the GBP, every transfer completed with the
same tick/poll counts (29–34 / 7–9) and CSR 0x0804. **Status:** FACT
(re-confirms GBP-HW-008).

---

## Static audit of the interrupt path — 2026-09-15 (no hardware)

Inputs: DISC (`0x8008a930`, `0x8008bf84`, `0x8008af08` + helpers
`0x80089ff4`/`0x8008a31c`/`0x8008a1dc`/`0x80089edc`/`0x80089e40`/
`0x8008bcc4`, `0x8008be04`, SDK `0x80069ff0`/`0x80069ca0`/`0x80069ef0`/
`0x80069f70`/`0x80069c38`/`0x8006b1d4`/`0x800a243c`; every reference to
`0xCC003000` and `0xCC003004` in main.dol enumerated with
`OpenGbpFunc.java refs`), GBI (`0x8000b400`, `0x8000bf30`, `0x80058360`,
`0x800580e4`, `0x800586a8`, `0x8005863c`, `0x800585d0`, `0x80058724`,
`0x80058780`, `0x80058c70`, `0x80058b88`, `0x80053eb0`, `0x80052f04`;
same enumeration), LIBOGC2 + LIBOGC2-BIN, DOLPHIN
`ProcessorInterface.cpp`/`HSP_DeviceGBPlayer.cpp`, YAGCD PI section.
Decompiles under `build/analysis/ghidra/*/decomp/` (ignored, private).

## GBP-PI-001 — PI INTSR is the interrupt-cause register and is visible independently of INTMR; INTMR only gates delivery to the CPU

**Claim:** `0xCC003000` (INTSR) holds one cause bit per PI source (bit 13
= HSP) plus bit 16 (reset-switch state, read by libogc2
`SYS_ResetButtonDown`, by GBI `0x8005378c`/`0x80052f04` and by the Disc
`0x8006b2d0`); `0xCC003004` (INTMR) holds one enable bit per source (bit
13 = HSP). A cause bit is readable while its mask bit is 0; the mask bit
decides only whether the CPU external-interrupt exception is raised.

**Status:** CORROBORATED — **Confidence:** high for the software
contract; no direct hardware observation of bit 13 = 1 yet.

**Sources:**

- YAGCD PI section: INTSR "interrupt cause" and INTMR "interrupt mask"
  with identical bit lists (bit 13 HSP); no clearing semantics stated.
- All three dispatchers read INTSR and INTMR separately and test
  `cause & mask` (ENV-IRQ-001); the test would be meaningless if the
  hardware already masked the cause register.
- DISC stop `0x8008be04`: `OSMaskInterrupts(0x20)` **first**, four
  CONTROL writes, IRQ-register write, then `INTSR := 0x2000` with the
  mask still off — an acknowledge written while masked presumes the
  cause can be latched/visible while masked.
- DOLPHIN `ProcessorInterfaceManager`: `m_interrupt_cause` and
  `m_interrupt_mask` are separate; `SetInterrupt` sets the cause
  regardless of the mask; `UpdateException` raises the CPU exception iff
  `cause & mask` (model).
- Hardware (GBP-HW-012): INTSR bit 13 read 0 in every snapshot while
  INTMR bit 13 was 0 — consistent, not a proof of independence.

**Hardware tests:** none dedicated. GBP-INIT-002 (planned) reads INTSR
before and after unmasking and after re-masking.

**Notes:** IRQ 26 ↔ bit 13 ↔ software mask `0x20` is FACT in the three
code bases: libogc2 `IRQ_PI_HSP = 26`, `IM_PI_HSP = 0x20`, dispatcher
`0x2000 → IRQMASK(26)`, `__SetInterrupts` `IM_PI_HSP → 0x2000`; SDK
dispatcher `0x2000 → 0x20`, `0x80069ca0` `0x20 → 0x2000`, DISC
`OSSetInterruptHandler(0x1a, 0x8008af08)`; GBI `IRQ_Request(0x1a, 0x8000b400)`,
`__UnmaskIrq(0x20)`.

## GBP-PI-002 — INTSR bits are cleared by writing 1 (write-1-to-clear)

**Claim:** Writing a value to `0xCC003000` clears the cause bits that are
set in the value and leaves the others unchanged. Every known INTSR
write is an acknowledge of one source: libogc2 `_piReg[0] = 2` (reset
switch, `__RSWHandler`) and `_piReg[0] = 1 << 12` (debugger,
`mmce.c DbgHandler`); SDK in the Disc `0x8006b1d4` (`:= 2`, reset switch)
and `0x800a243c` (`:= 0x1000`, debugger); GBI `0x80053eb0`/`0x80052f04`
(`:= 2`); DISC `0x8008af08`/`0x8008be04` and GBI `0x8000b400`
(`:= 0x2000`, HSP). These are the **only** INTSR writes in main.dol and
in gbi.dol (complete reference enumeration, `refs.tsv`).

**Status:** CORROBORATED (four independent code bases + Dolphin
`m_interrupt_cause &= ~val`) — **Confidence:** high for "write 1 clears";
whether the HSP bit can be cleared while the device still asserts the
line is U-GBP-022.

**Hardware tests:** none. GBP-INIT-002 (planned) re-reads INTSR
immediately after the W1C inside the handler.

## GBP-PI-003 — Retrigger and interrupt-storm mechanics

**Claim:** After a handler returns, `rfi` restores MSR[EE] = 1; if
`INTSR & INTMR` is still non-zero at that instant the CPU takes the
external-interrupt exception again before executing the interrupted
code. Neither libogc2 nor the SDK dispatcher bounds this. The only
mechanisms that end it are: clearing the cause (INTSR W1C, if the source
no longer asserts), removing the source at the device, or clearing the
INTMR bit. Clearing INTMR bit 13 through `__MaskIrq(IM_PI_HSP)` **inside
the handler** ends it regardless of what the device does — it is the
mechanism the Disc relies on at stop (mask first, then touch the device)
and the mechanism every libogc/SDK driver relies on for masking.

**Status:** FACT for the CPU/dispatcher part (PowerPC architecture +
ENV-IRQ-001); **FACT (hardware, 2026-09-15, GBP-HW-022)** that
`__UnmaskIrq(IM_PI_HSP)` / `__MaskIrq(IM_PI_HSP)` set and clear INTMR bit
13 on the console (`0x1FA → 0x21FA → 0x1FA`, other bits unchanged);
CORROBORATED that a masked cause is not delivered (libogc2, SDK, Dolphin
all depend on it; no HSP cause has occurred on hardware yet, so the
gating itself has not been exercised); **UNKNOWN** whether the physical
HSP cause is level (follows the GBS-DOL line) or latched at the PI
(U-GBP-022).

**Notes:** GBI acknowledges PI in the raw handler and writes the device
IRQ register only later, in a thread, with INTMR bit 13 left enabled; a
purely level-mirrored cause would keep GBI in the exception loop until
the thread ran, which cannot happen — so either the PI latches the HSP
cause and W1C clears it, or the GBS-DOL deasserts by itself shortly
after asserting. HYPOTHESIS, not promoted; it is one of the two outcomes
GBP-INIT-002 is designed to distinguish.

## GBP-IRQ-002 — Start-up Disc HSP interrupt service: GBP → PI → GBP → GBP

**Claim:** Handler `0x8008af08` is installed by `0x8008a930` (init) with
`OSSetInterruptHandler(0x1a, …)` while INTMR bit 13 is masked (the stop
routine `0x8008be04`, which calls `OSMaskInterrupts(0x20)`, runs earlier
in the same init). Start `0x8008bf84` executes, in this order:
`OSUnmaskInterrupts(0x20)` → read IRQ → build two 16-bit shadows from
the callback table (one starts at `0x8000`, the other at 0) → write
`IRQ := (read & ~shadowA) | shadowB` → read CONTROL → write CONTROL
`| 0x04` → write CONTROL `& ~0x10`. The handler, entered with EE = 0 and
with every GBP access a synchronous polled DMA under
`OSDisableInterrupts`:

```text
 1. write IRQ := shadowB | 0x8000            (device, first action)
 2. INTSR := 0x2000                          (PI W1C; INTSR is never read)
 3. read IRQ → pending (16-bit: byte 0x1D << 8 | byte 0x1F)
 4. if (pending & 0x0555) != 0:
      write IRQ := pending                   (device: write back the value read)
      keep = pending & (pending ^ (pending >> 1))   — bit i survives only if bit i+1 is 0
      write KEYPAD := keypad shadow
      one-shot callback (if set), then cleared
      read CONTROL; mask word := map(CONTROL) | 1 | extra   (0x8008bcc4)
      pre-callback (if set)
      callback slots 0–3: if keep & tbl[i] and slot set → cb(0)
      slot 4: if keep & tbl[4] → cb(1) if keep & tbl2[4] else (cb(0) != 0 → suppress); counter4++
      slot 5: if keep & tbl[5] → (cb(0) != 0 → suppress); counter5++
 5. post-callback if slot 4 fired
 6. if !suppress: write IRQ := shadowB       (device, last action)
 7. return
```

No wait loop, no re-read; several pending sources are served in one
pass; an entry with no known source still performs steps 1, 2, 3 and 6.

**Status:** FACT (disassembly + decompile of `0x8008af08`,
`0x80089ff4` = IRQ write, `0x8008a31c` = IRQ read, `0x8008a1dc` =
CONTROL read, `0x80089edc` = CONTROL write, `0x80089e40` = KEYPAD write,
`0x8008bcc4`, `0x8008bf84`, `0x8008be04`, `0x8008a930`) —
**Confidence:** high.

**Notes:** ACK order classification: **GBP → PI → GBP → GBP** (device
first, PI second, then two more device writes). Do not summarize it as
"ack PI". The Nintendo Start-up Disc is the official reference for this
order. Bit 15 (`0x8000`) is part of the first device write; its meaning
stays H (U-GBP-007).

## GBP-IRQ-003 — GBI HSP interrupt service: PI first in the raw handler, GBP later in a thread

**Claim:** GBI's worker thread `0x8000bf30` performs `KEYPAD := 0` →
read CONTROL (vote) → write CONTROL `(v & ~0x18) | 0x0C` →
`IRQ_Request(0x1a, 0x8000b400)` → `__UnmaskIrq(0x20)`. The raw handler
`0x8000b400` is four instructions: `INTSR := 0x2000` (W1C, INTSR never
read) → signal the thread's semaphore (`0x80058c70` = `LWP_SemPost`,
`__lwp_sema_surrender` at `0x80072c14`) → return; no mask change, no
DMA. **Correction 2026-09-15 (GBP-IRQ-004):** the wait `0x80058b88` is
`LWP_SemWait` (blocking without timeout: `0x80072c8c` enqueues the thread
when the count is 0), but the semaphore is created with
`LWP_SemInit(&sem, 1, 1)` at `0x800113a0` (`li r4,1; li r5,1`), so the
**first pass of the loop runs before any interrupt** and performs the
IRQ-register writes described below before the thread ever blocks. The
thread, per pass: read IRQ (32 bytes at
`base+0xD00000`, voted; 16-bit value = vote(bytes ≡1 mod 4) << 8 |
vote(bytes ≡3 mod 4)) → per bit `0x400` AUDIO read, `0x100` VIDEO read,
`0x040` SIODATA read (asynchronous ARQ), `0x010` KEYPAD write → one
64-byte write at `base+0xCFFFE0` (KEYPAD + IRQ := value_read | 0x8000)
→ 64-byte read at `base+0x4FFFE0` (CONTROL, SIOCTL) → … → 32-byte write
IRQ := 0 at the end of the iteration → loop. Exit: `__MaskIrq(0x20)` →
`IRQ_Free(0x1a)` → CONTROL `(v & 0xE3) | 0x10`.

**Status:** FACT (decompiles of `0x8000b400`, `0x8000bf30`, `0x80058c70`,
`0x80058b88`, `0x80058724` = IRQ_Request, `0x80058780` = IRQ_Free,
`0x8005863c` = __MaskIrq, `0x800585d0` = __UnmaskIrq) — **Confidence:**
high for the order; the payload of the 64-byte writes is described only
to the level needed here.

**Notes:** ACK order classification: **PI (raw handler) → GBP (thread)**,
with scheduling latency between the two and INTMR bit 13 left enabled
in between. With no known source pending the thread runs the same
sequence; with a persistent source there is no protection beyond the PI
W1C. GBI is an independent, mature implementation, not Nintendo
software; the order above is GBI's, not an official one.

---

## Physical observations — GBP-INIT-002, 2026-09-15 (GBP attached)

Same console and setup as the 2026-09-15 runs; DOL `initirq-0001`,
clean commit `4e3cb43`, DOL sha256 `1bd2bcf3…43f2`; log
`logs/GBP-INIT-002_initirq-0001.log` (6585 bytes, sha256 `e7ec3d83…ea1d`,
verbatim in HARDWARE_TESTS.md; fixture
`captures/fixtures/hw-gamecube-gbp-2026-09-15-initirq-0001.gbpreplay`
replays the whole run through `gbp_initirq_probe_run`, physical time base
included, `tests/unit/test_gbp_init_irq.c`). "FACT" = observed in that
run; one run.

## GBP-HW-021 — Detection and preconditions of the run

**Claim:** PRESENT by both criteria 4/4 (`vote_ok=4 b1_ok=4`); whole-block
1/4 (responses `3D 3C…`, `D3 C3…`, `11 00…`, `FF`×32) — the 32/32
criterion fails again with the GBP attached and is not a presence gate.
PI before anything experimental: INTSR `0x00010000`, INTMR `0x000001FA`
(bit 13 clear in both, as required). CONTROL idle `0x90` (raw `91 90×31`),
IRQ idle `0x8AAE` (raw `9B 8A AE AE 8A 8A AE AE…`), TEST after the
handshake `11 00×31`. **Status:** FACT.

## GBP-HW-022 — libogc2's mask API physically toggles PI INTMR bit 13

**Claim:** With the handler installed and CONTROL at `0x8C`,
`__UnmaskIrq(IM_PI_HSP)` changed INTMR from `0x000001FA` to `0x000021FA`
(bit 13 0 → 1) within 33 ticks (0.81 µs, PI read after the call), and
`__MaskIrq(IM_PI_HSP)` at the end of the window changed it back to
`0x000001FA` (S2, S2b, S3, MASKCHK, S4). Bits 1–8 (`0x1FA`) never changed.
INTSR read `0x00010000` before, right after and 2 s after the unmask.
**Status:** FACT for INTMR bit 13 and for these two libogc2 calls; not
extrapolated to any other PI interrupt. It upgrades the "mask/unmask
effect" part of GBP-PI-003; the delivery gating itself was not exercised
(no cause occurred).

## GBP-HW-023 — No IRQ 26 within 2000 ms under this sequence

**Claim:** Under the physical conditions tested — GBP attached, no
cartridge, AR_INFO expansion code 3, CONTROL transformed to `0x8C` by the
GBI byte-replicated write, one-shot handler installed, PI HSP unmasked
(INTMR bit 13 = 1), GBP IRQ register never written — no IRQ 26 was
observed within 2000 ms: the handler never entered (`fired=0 count=0
t_entry=0`, every HANDLERPI field 0), INTSR bit 13 read 0 in all 12 PI
reads of the run, and the wait ended by its operational bound after
81000012 ticks (2.0000003 s at 40.5 MHz; S2 at 2.000035 s after the
unmask). The 13871306 polls (≈144 ns each) describe the loop, not the
hardware. **Status:** FACT, restricted to this sequence. It does **not**
say "the GBP does not generate IRQs" or "CONTROL does not generate IRQs":
the sequence left the GBP's own IRQ register untouched (GBP-IRQ-005).

## GBP-HW-024 — IRQ register `0x8AAE → 0x8FAE` during the window, CONTROL unchanged, persisting after the CONTROL restore

**Claim (exact bytes):**

| Snapshot | ticks after unmask | CONTROL raw → semantic | IRQ raw → semantic (Disc / GBI reading) |
|---|---|---|---|
| S1 (before the unmask, 124 ticks after the write) | — | `9D 8C×31` → 0x8C | `9B 8A AE AE 8A 8A AE AE …` → 0x8AAE / 0x8AAE |
| S2 (masked again) | 81001422 (2.000035 s) | `9D 8C×31` → 0x8C (identical block) | `9F 8F AF AE 8F 8F AF AE …` → 0x8FAE / 0x8FAE |
| S3 (after CONTROL := 0x90) | 81007648 | `91 90×31` → 0x90 | identical to S2 → 0x8FAE |
| S4 (after AR_INFO → 0x0043) | 81013634 | `11 00×31` → 0x00 | `91 90×31` → 0x9090 |

S1 → S2: 24 of 32 bytes changed; offsets ≡ 3 mod 4 unchanged; XOR per
4-byte group `05 05 01 00` (group 0: `04 05 01 00`). Semantic
`0x8AAE ^ 0x8FAE = 0x0500`: bits 0x0400 and 0x0100 became set; the odd
bits (0x0AAA) and bit 15 stayed set. In the new state the two "low" bytes
of each group differ (`AF AE`): offsets ≡ 2 mod 4 carry bit 0 set,
offsets ≡ 3 mod 4 do not; both reference readings (Disc bytes 0x1D/0x1F,
GBI vote over ≡ 1 / ≡ 3 mod 4) ignore offset ≡ 2 and agree on 0x8FAE
(U-GBP-025). CONTROL was byte-for-byte identical in S1 and S2. After the
CONTROL restore to 0x90 the IRQ block still read 0x8FAE (S3). **Status:**
FACT. **Not known:** when inside the 2 s window the change happened, and
whether it was caused by elapsed time with CONTROL = 0x8C, by the PI
unmask, by internal GBS-DOL activity, or a combination (U-GBP-024); "the
unmask caused 0x8FAE" is not asserted.

## GBP-HW-025 — Expansion code 3 → 0 changed the view a third time

**Claim:** S4, taken after AR_INFO went back from 0x005B to 0x0043, read
CONTROL `00`×32 (byte 0 `11`) and IRQ `91 90×31` (0x9090), the same view as
GBP-PROBE-001 MODE A and GBP-INIT-001 S5, although under code 3 the same
registers had just read 0x90 / 0x8FAE. **Status:** FACT; with GBP-HW-005 and
GBP-HW-017 this is the third independent observation → "AR_INFO[5:3] = 3
reproducibly changes what CONTROL/IRQ return with the GBP present" is
CORROBORATED. Its function stays U-GBP-004; not "enable".

## GBP-HW-026 — Teardown validated physically; byte-0 extras of this run

**Claim:** CLEANUP not performed (INTSR bit 13 = 0 with IRQ 26 masked);
`IRQ_Request(26, old)` restored the NULL previous handler (rc ok); MASK
final INTMR `0x1FA`; AR_INFO `0x0043` read back; S4 taken; `restore=ok`,
21 transfers, 0 DMA timeouts/busy, 0 errors, 60 log lines, 0
dropped/truncated. Byte-0 extras relative to the voted value in this run:
CONTROL `91` (0x90 + 0x01), `9D` (0x8C + 0x11), `11` (0x00 + 0x11); IRQ
`9B` (0x8A + 0x11), `9F` (0x8F + 0x10), `91` (0x90 + 0x01); TEST responses
`3D`, `D3`, `11`, `FF` (extras 0x01, 0x10, 0x11, none). The transient bit 6
of GBP-INIT-001 (byte 0 `EC → AC`, `EA → AA`) did **not** appear: no
snapshot of this run had bit 6 extra in byte 0. **Status:** FACT
(U-GBP-015/020/021 updated).

---

## Static re-audit after GBP-INIT-002 — 2026-09-15 (no hardware)

## GBP-IRQ-004 — GBI programs the GBP IRQ register before it ever blocks: the semaphore starts at 1

**Claim:** The semaphore the GBI worker thread waits on (`r13+0x158`) is
created by `LWP_SemInit(&sem, 1, 1)` at `0x800113a0` (`li r4,1; li r5,1;
addi r3,r13,344; bl 0x80058ad4`, inside the GBP init function
`0x8001123c` that also writes AR_INFO `|= 0x18`). `0x80058ad4` is
`LWP_SemInit` (object type 4, `__lwp_sema_initialize` at `0x80072bc8`);
`0x80058b88` is `LWP_SemWait` (`0x80058a28(sem, 0, 0, 0)` →
`__lwp_sema_seize` `0x80072c8c`, which decrements a non-zero count and
returns, or enqueues the thread when the count is 0); `0x80058c70` is
`LWP_SemPost` (`__lwp_sema_surrender` `0x80072c14`), called only by the
raw handler `0x8000b400`. Therefore the first pass of the loop runs
without any interrupt and, in order: reads IRQ (`0x80011c14(0xD00000,
0x20)`, voted), dispatches on the value read (0x0400 → ARQ read AUDIO
`0x800000`/0x1000 with callback `0x8000b75c`; 0x0100 → ARQ read VIDEO
`0x100000`/0xF00; 0x0040 → ARQ read SIODATA `0x900000`/0x20 with callback
`0x8000fa58` → message queue; 0x0010 → 64-byte KEYPAD write 0x0304/0x0300),
writes 64 bytes at `0xCFFFE0` = KEYPAD := pad state (0) **+ IRQ :=
value_read | 0x8000** (u16 replicated `hh ll hh ll …`), reads 64 bytes at
`0x4FFFE0` (CONTROL, SIOCTL), optional SIODATA traffic, and ends with **IRQ
:= 0** (32 bytes of zeros at `0xD00000`); only then does `LWP_SemWait`
block until the handler posts. Every IRQ-register write in gbi.dol is in
this loop (`0xCFFFE0`/64 at `0x8000c194`, `0xD00000`/32 at `0x8000c360`;
`OpenGbpFunc.java callsites 8000bea4`).

**Status:** FACT (disassembly + decompiles `0x8001123c`, `0x80058ad4`,
`0x80058a28`, `0x80072c8c`, `0x80058c70`, `0x80072c14`, `0x8000bf30`,
`0x8000be48`, `0x80015ddc`, `0x80015da0`) — **Confidence:** high.

**Notes:** This corrects the reading recorded in GBP-IRQ-003 and in
INITIALIZATION.md §3/§4 ("GBI waits without programming the IRQ block"):
GBI does program it — with the value it read plus bit 15, then with 0 —
before its first blocking wait, and GBP-INIT-002 reproduced GBI's start
*except* these two writes (the GBP IRQ register was read-only by design).
GBI also writes `KEYPAD := 0` before the CONTROL transform, which
GBP-INIT-002 did not reproduce either.

## GBP-IRQ-005 — Source/mask pairing of the GBP IRQ register: what the references write, what the hardware showed

**Claim:** (1) Both drivers treat the even bits as sources: GBI dispatches
on 0x0400 (AUDIO read), 0x0100 (VIDEO read), 0x0040 (SIODATA read),
0x0010 (KEYPAD writes) — GBP-IRQ-004; the Disc's callback slots 0–5 are
keyed by `0x801B34C8 = {0x0001, 0x0040, 0x0010, 0x0004, 0x0400, 0x0100}`,
slot 4 (0x0400) → `0x8008cdc4` → `0x8008a764` = DMA read of `base +
0x800000`, 0x1000 bytes into a 70-entry ring, slot 5 (0x0100) →
`0x8008ed68` → `0x8008a480` = DMA read of `base + 0x100000`, 0xF00 bytes
into a 40-entry ring; slots 4/5 are registered by the audio/video init
(`0x8008c7c0`, `0x8008e994`, called from the library init `0x8008f1fc`
right after `0x8008a930`, i.e. before the start `0x8008bf84`; skipped when
the init mode argument is 3). **FACT (code).** (2) The Disc pairs each
even bit with the odd bit above it: `0x801B34D4 = {0x0002, 0x0080,
0x0020, 0x0008, 0x0800, 0x0200}`; its handler only dispatches a source
whose paired bit is clear (`keep = pending & (pending ^ (pending >> 1))`
= bit i kept iff bit i set and bit i+1 clear); its start writes `IRQ :=
(read & ~(0x8000 | odd bits of slots WITH a callback)) | (odd bits of
slots WITHOUT a callback)`, its handler writes `shadow | 0x8000` at entry
and `shadow` at exit, its stop writes `read | (0x8000 | odd bits of
enabled slots)`. **FACT (code).** (3) Hardware: at idle the register
reads 0x8AAE = bit 15 + all six odd bits + source bit 2; after the
CONTROL transform, with PI HSP unmasked for 2 s and the register never
written, source bits 0x0400 and 0x0100 became set (0x8FAE) while the odd
bits and bit 15 stayed set, and no PI IRQ arrived (GBP-HW-023/024). **FACT
(hardware).**

**Status:** source bit → function in each driver: FACT (code); the
even/odd pairing as source/mask: CORROBORATED (Disc tables + handler
filter + start formula, GBI's "ack with bit 15 then write 0", hardware
consistency); polarity "odd bit 1 = masked, bit 15 = 1 = masked" and
"the pending sources 0x0400/0x0100 are the audio/video streams of the
powered AGB": HYPOTHESIS — consistent with everything observed, not yet
demonstrated by a write (U-GBP-007, U-GBP-024).

**Notes — what the Disc would have written from 0x8AAE.** Normal flow
(callbacks in all six slots before start): shadow "disable" = 0x8000 |
0x0AAA = 0x8AAA, shadow "enable-value" = 0 → `IRQ := (0x8AAE & ~0x8AAA) | 0
= 0x0004` — bit 15 and every odd bit cleared, the pending source bit 2
written back as 1. Init mode 3 (no AV callbacks): `IRQ := (0x8AAE & ~0x80AA)
| 0x0A00 = 0x0A04` — audio/video kept masked, the rest enabled. No
callbacks at all (a configuration the Disc never has): `IRQ := 0x0AAE` —
only bit 15 cleared. GBI's first pass: `IRQ := 0x8AAE | 0x8000 = 0x8AAE`
(or `0x8FAE` if the sources were already pending) then `IRQ := 0` — bit 15
and every odd bit cleared. Under the polarity hypothesis both references
therefore un-mask the audio/video sources before waiting, and
GBP-INIT-002, which left 0x8AAE in place, could not receive them.
Whether that programming would have made 0x0400/0x0100 reach PI HSP is
exactly what the next experiment tests (DEVLOG 2026-09-15). Dolphin's
model (`m_irq &= ~value` on any write; line asserted iff `irq & 0x8000
&& !(control & 0x10)`) ignores the odd bits and predicts an interrupt for
the hardware's idle state; the hardware showed none for 2 s — the model
is not evidence here.

## GBP-IRQ-006 — The Start-up Disc's first IRQ-register write is a write-back of the value read, with PI HSP masked

**Claim:** The library init `0x8008a930` calls the stop routine
`0x8008be04` right after the TEST handshake, before any callback is
registered and before any start. Stop does `OSMaskInterrupts(0x20)`,
four CONTROL writes (`& ~0x04`, `& ~0x08`, `| 0x10`, `| 0x80` — no change
from the idle value 0x90), reads the IRQ register and writes
`read | shadow` where `shadow` (SDA `r13 - 0x7050`, address
`0x80272050`) is 0 at that moment: it lives in the DOL's BSS (zero at
load; `_SDA_BASE_` = `0x802790A0` from `lis r13,0x8027 ; ori
r13,r13,0x90a0` at `0x80003288`) and is only set by start and cleared by
stop. The official disc's first write to the register is therefore
`IRQ := value_read`, issued with PI HSP masked, followed by `INTSR :=
0x2000`. Under the field model (GBP-IRQ-005) it acknowledges the pending
sources and leaves masks and bit 15 as read; for the idle value seen on
this console (0x8AAE, bit 15 already 1) it is byte-for-byte the value
GBI's first pass writes (`read | 0x8000`, GBP-IRQ-004).

**Status:** FACT (decompiles `0x8008a930`, `0x8008be04`, `0x8008bf84`;
DOL section map) — **Confidence:** high.

**Notes:** precedent for GBP-INIT-003A's write A1 (`read | 0x8000`) under a
masked PI; the stop formula `read | 0x8AAA` used by 003A's teardown is
the same routine's write once all six slots have been enabled (start
sets `shadow = 0x8000 | odd bits of the slots with a callback` =
`0x8AAA` in the disc's normal flow).

---

## Physical observations — GBP-INIT-003A, 2026-09-15 (GBP attached, PI HSP masked throughout)

Log `logs/GBP-INIT-003A_initirqa-0001.log` (13231 bytes, sha256
`ae9117457039727026f00e9ccb349d4af3c85ee6f4f436d290cd40cc0e672ef8`),
build `initirqa-0001`, commit `d956b1b` (clean), DOL sha256
`8c225bd101a215982ac59d096630a9e13b34557e3cdf4eb8354298855232bfa5`;
verbatim in HARDWARE_TESTS.md; preserved copy `captures/local/`; fixture
`captures/fixtures/hw-gamecube-gbp-2026-09-15-initirqa-0001.gbpreplay`.
Setup identical to GBP-INIT-002 (no Game Pak, Link Port empty, BBA without
cable). Time base 40.5 MHz. PI INTMR bit 13 was 0 in every read and was
never written (no handler, no unmask — audited on the objects). Every
claim below is **FACT (hardware)** unless marked otherwise; interpretations
are kept apart from observations.

## GBP-HW-027 — Detection, preconditions and baseline of the run

Handshake: `C3 → 3C`×32; `3C → C7 C3×31` (byte 0 extra 0x04); `FF → 00`×32;
`00 → FF`×32 — vote 4/4, byte-1 4/4, whole-block 3/4 → PRESENT (the
whole-block criterion is reporting only, GBP-HW-010). PI `PRE`, `BASE` and
`P0`: INTSR `0x00010000`, INTMR `0x000001FA`. BASE: CONTROL `90`×32 (no
byte-0 extra) → 0x90; IRQ `AE 8A AE AE / 8A 8A AE AE ×7` → 0x8AAE by both
readings; TEST `00`×32; shape checks passed. CONTROL := 0x8C accepted (P0,
981 ticks later: `AC 8C×31` → 0x8C); IRQ still 0x8AAE at P0 and at A1PRE.
After GBP-INIT-002 had left the register at 0x8FAE and the console was
power-cycled, the register read its idle value 0x8AAE again (U-GBP-023).

## GBP-HW-028 — A1 `IRQ := 0x8AAE` (= read | 0x8000) cleared source bit 0x0004 and nothing else

A1PRE 0x8AAE; write `8A AE`×16 (u16 replicated, one 32-byte DMA at
`base + 0xD00000`, completed); A1-0, 19 ticks (0.47 µs) after the write's
completion, read `AE 8A AA AA / 8A 8A AA AA ×7` → 0x8AAA by both readings;
A1-50US (2029 ticks) and A1-500US (20255 ticks) identical; A2PRE 0x8AAA.
CONTROL `AC 8C×31` in all; INTSR `0x00010000` in all. `0x8AAE ^ 0x8AAA =
0x0004`: the even bit written as 1 cleared, the six odd bits and bit 15
written as 1 read back 1. **FACT (hardware):** writing 1 to bit 2 while it
read 1 cleared it (write-1-to-clear behavior of that bit); bits 1, 3, 5,
7, 9, 11 and 15 written 1 read 1. **FACT (code), separate:** bit 2 is the
Disc's callback slot 3 (`0x801B34C8[3] = 0x0004`, stop sequence + video
reset, "game pak" event; Dolphin `IRQ::GamePak`). The physical function of
bit 2 was not tested.

## GBP-HW-029 — A2 `IRQ := 0x0000` read back 0x0000 for at least 50 ms; CONTROL unchanged

A2PRE 0x8AAA; write `00`×32 (completed); A2-0 22 ticks (0.54 µs) later
`00`×32 → 0x0000 by both readings; A2-50US (2025 ticks), A2-500US (20251),
A2-5MS (202503), A2-50MS (2025005 ticks = 50.0 ms) all `00`×32; CONTROL `AC
8C×31` in all five; INTSR `0x00010000` in all five. **FACT:** the six odd
bits and bit 15, which read 1 before, read 0 after being written 0 and
stayed 0 for ≥ 50 ms with no even bit set; bits 12–14 written 0 read 0. No
function is claimed from this observation alone.

## GBP-HW-030 — First HSP cause: PI INTSR bit 13 = 1 with INTMR bit 13 = 0, 105.27 ms after A2, IRQ register 0x0400

The INTSR poll at time-base 4155517524 (= t_a2 + 4263568 ticks = 105.2733
ms after A2's completion; 105.79 ms after A1; 105.92 ms after the CONTROL
write; the 740497th poll of the window, ≈0.14 µs per poll) returned
`0x00012000`. The EVENT snapshot taken at once read INTSR `0x00012000`,
INTMR `0x000001FA`, CONTROL `AC 8C×31` (0x8C), IRQ `04 04 04 00 ×8` →
0x0400 by both readings. The previous sample (A2-50MS, 50.00 ms after A2)
had read INTSR bit 13 = 0 and IRQ 0x0000, so the source and the PI bit
both rose between 50.00 ms and 105.27 ms after A2. Nothing was written
inside the window; the CPU took no exception (the program continued
normally; INTMR bit 13 = 0 throughout). **FACT (restricted):** with PI
HSP masked at the CPU (INTMR bit 13 = 0), after A1 and A2 of the GBI
pattern, the GBS-DOL produced source 0x0400 and PI INTSR bit 13 was
observed set ≈105.27 ms after A2. **Not claimed:** delivery of IRQ 26 (it
was masked and nothing was delivered); the exact rise time inside the
55 ms gap.

## GBP-HW-031 — Source 0x0100 appeared after the EVENT and before the stop write

IRQSTOPPRE, read ≈1.0 ms after the EVENT (after CONTROL had been restored
to 0x90 at +0.905 ms), returned `05 05 04 00 / 05 05 05 00 ×7` → 0x0500 by
both readings. **FACT:** bit 8 (0x0100) rose after the EVENT snapshot and
before the stop write; no finer timestamp exists (the two reads are not
temporal samples of the same phase). Order only: 0x0400 first, then
0x0500. Same pair as GBP-INIT-002's 0x8FAE (GBP-HW-024). **FACT (code):**
bit 8 is the Disc's slot 5 (`0x8008ed68 → 0x8008a480`, VIDEO block read)
and GBI's VIDEO read (0xF00); bit 10 is the Disc's slot 4 (`0x8008cdc4 →
0x8008a764`, AUDIO block read) and GBI's AUDIO read (0x1000) — GBP-IRQ-005.
**CORROBORATED (interpretation):** the physical event was the GBS-DOL's
audio (0x0400) followed by video (0x0100) request of the running AGB; not
FACT because no AUDIO/VIDEO block was read and no cartridge was present.

## GBP-HW-032 — Stop word `IRQ := 0x8FAA` (= 0x0500 | 0x8AAA) read back 0x8AAA

Write `8F AA`×16 (completed); IRQSTOPPOST `AE 8A AA AA / 8A 8A AA AA ×7` →
0x8AAA by both readings (`masks_readback=1 bit15_readback=1`). **FACT:**
the even bits 8 and 10 written as 1 cleared (second and third even bits
with write-1-to-clear behavior after bit 2); the odd bits and bit 15
written 1 read 1 with no even bit set. The Start-up Disc's stop formula
(`read | 0x8AAA`, GBP-IRQ-006) therefore did what the code analysis
predicted on the device side.

## GBP-HW-033 — PI INTSR bit 13 stayed set after the device sources were cleared and was cleared by a single W1C 0x2000

CLEANUPCHK, read after CONTROL := 0x90 and after the stop write had
cleared 0x0500 from the device register: INTSR `0x00012000`, INTMR
`0x000001FA`. One `INTSR := 0x2000`; re-read `0x00010000`; `sticky=0`, no
second write. **FACT:** the PI keeps bit 13 set after the device-side
sources are gone (latched at the PI, not a live mirror of the device
register's even bits), and one write-1-to-clear of 0x2000 cleared it.
**Not resolved:** whether the GBS-DOL line is level or pulse, and what a
W1C does while the device still asserts (the sources had been cleared on
the device side before the W1C) — U-GBP-022 remaining part.

## GBP-HW-034 — Teardown, expansion-code view, byte-0 extras, statistics

CONTROL restore 0x90 → readback `90`×32; stop and cleanup as above; AR_INFO
`0x005B → 0x0043` read back; FINAL under code 0: CONTROL `00`×32, IRQ
`90`×32 (0x9090), INTSR `0x00010000`, INTMR `0x000001FA` — fourth
observation of the code-3 → code-0 view change (U-GBP-004). `restore=ok`;
every write attempted = completed (`ctl_exp 1/1, a1 1/1, a2 1/1, stop 1/1,
ctl_restore 1/1, uncertain=0`); 44 transfers, 0 timeouts, 0 busy, 0
errors, 102 lines, 0 dropped, 0 truncated; `REGION formatted_inside=0`.
Byte-0 extras of this run: CONTROL 0x8C → `AC` (+0x20), 0x90 → `90` and
0x00 → `00` (none); IRQ 0x8A → `AE` (+0x24) in every 0x8AAE/0x8AAA read,
0x04 → `04`, 0x05 → `05`, 0x90 → `90` (none); TEST C3 → `C7` (+0x04),
others none — a fourth distinct pattern across runs (U-GBP-021). One
group-0 anomaly: the 0x0500 read has `05 05 04 00` in group 0 against
`05 05 05 00` in groups 1–7 (offset 2 of group 0 differs, U-GBP-025).
**Logging defect of this build, not a hardware observation:** the record
`WINDOW tag=A1 … intsr13_seen=1` printed the run-global flag after the
window had ended; every A1 record (A1-0, A1-50US, A1-500US, A2PRE) has
INTSR bit 13 = 0 and `OBSERVED first_phase=A2 t_first_intsr13=4155517524`;
there was no INTSR bit 13 during A1 (DEVLOG 2026-09-15). Corrected for
later builds (`intsr13_in_phase`); the log stays as written.

## GBP-PI-004 — PI INTSR bit 13 is captured independently of INTMR bit 13, latched, and cleared by W1C 0x2000 (hardware)

**Claim:** the HSP cause bit of INTSR (bit 13) was observed set while
INTMR bit 13 was 0 (GBP-HW-030), stayed set after the device-side sources
had been cleared (GBP-HW-033), and was cleared by one `INTSR := 0x2000`
(GBP-HW-033); no CPU exception occurred while it was set with the mask
closed. **Status:** FACT (hardware), restricted to bit 13 / HSP on this
console — promotes GBP-PI-001 (cause visible independently of the mask)
and GBP-PI-002 (write-1-to-clear) to FACT for bit 13, and the "masked
cause is not delivered" part of GBP-PI-003 to FACT for bit 13. Not
extrapolated to other PI sources. **Open:** level/pulse nature of the
GBS-DOL line and W1C-while-asserted (U-GBP-022).

## GBP-IRQ-007 — IRQ-register field semantics after GBP-INIT-003A (model update)

| Bit(s) | Observation (hardware, 2026-09-15) | Reference usage (code, FACT) | Status of the semantics |
|---|---|---|---|
| 2 (0x0004) | read 1 at idle; written 1 (A1) → read 0 (GBP-HW-028) | Disc slot 3 (stop / video reset); Dolphin GamePak | W1C **FACT**; function "game pak / stop event" FACT (code), physically untested |
| 8 (0x0100) | rose by itself with CONTROL 0x8C (GBP-INIT-002: within 2 s; 003A: between the EVENT and +1.0 ms); written 1 (stop) → read 0 (GBP-HW-032) | Disc slot 5 → VIDEO read; GBI VIDEO read 0xF00 | W1C **FACT**; "video request of the AGB" **CORROBORATED** |
| 10 (0x0400) | rose by itself 50–105 ms after A2 and raised PI INTSR bit 13 with masks 0 / bit 15 0 (GBP-HW-030); written 1 (stop) → read 0 | Disc slot 4 → AUDIO read; GBI AUDIO read 0x1000 | W1C **FACT**; propagation to PI **FACT** (in the A2 state); "audio request of the AGB" **CORROBORATED** |
| 0, 4, 6 | never seen set | Disc slots 0, 2, 1 (user callback, sleep → CONTROL 0x10, serial) | by pairing/code only: **CORROBORATED** W1C, functions per code |
| 1, 3, 5, 7, 9, 11 (0x0AAA) | idle 1; written 1 (A1, stop) → 1; written 0 (A2) → 0 for ≥ 50 ms; with all six = 1 (and bit 15 = 1) pending 0x0400/0x0100 raised no PI cause for 2 s (INIT-002); with all six = 0 (and bit 15 = 0) the next 0x0400 raised the PI cause (003A) | Disc: per-slot mask levels, handler filter `pending & ~(pending >> 1)`; GBI: all 0 before waiting | level-written **FACT**; pairing **CORROBORATED**; polarity 1 = masked / 0 = enabled **CORROBORATED** — not FACT because the two runs also differ in bit 15, so the odd bits alone were not isolated |
| 12–14 | written 0 by A2 → 0; never seen 1 | never used | **UNKNOWN** function; keep 0 |
| 15 (0x8000) | idle 1; written 0 (A2) → 0 for ≥ 50 ms with no source pending; written 1 (stop) → 1 with no source pending (GBP-HW-029/032); the PI cause arrived while it read 0 | Disc: 1 at handler entry and at stop, 0 at start/exit; GBI: `read \| 0x8000` then 0; Dolphin: `IRQ_ASSERTED`, set by any source, W1C, drives the line | **FACT:** writable and persistent as 0 and as 1 under the conditions tested. Reading (ii) "W1C pending summary" **REJECTED** (a summary written 1 with nothing pending would not read 1; it read 1). Reading (i) "level-written global hold/mask, 1 = held" remains consistent — **HYPOTHESIS**, because its effect was never isolated from the odd bits. Dolphin's condition `irq & 0x8000` for asserting the line is contradicted (the cause came with bit 15 = 0) |
| Write layout | u16 replicated 16× (`hi lo …`) accepted for 0x8AAE, 0x0000, 0x8FAA; read-back layout `hh hh ll' ll` with `ll' = ll \| (hi & 0x05)` in all six states seen (U-GBP-025, pattern only) | GBI 0x80015da4 | layout **FACT** for the three values written |

**Consequence for initialization:** GBP-INIT-002 (idle masks left in
place, PI unmasked) saw no cause in 2 s with the sources pending; 003A
(sources acknowledged, masks and bit 15 written 0, PI masked) saw the
cause at the PI within 105 ms. The blocker of INIT-002 was the device's
own IRQ register state, not PI INTMR — **CORROBORATED** (two runs, one
variable group changed; bit 15 and the odd bits changed together).

## Physical observations — GBP-INIT-003B, 2026-09-15 (GBP attached; first delivery of an HSP cause to the CPU)

Log `logs/GBP-INIT-003B_initirqb-0001.log` (17471 bytes, sha256
`bedb1f013176fec1b3de7c63c4147dfa6770f1eae8c9ec29ee82b027f9d7cf7c`),
build `initirqb-0001`, commit `d3da8cd` (clean, release-audited), DOL
sha256 `821aa2b2893b6d66fd1398eaeb7de7c475862728e55dc0922d74042d0e9cb757`;
verbatim in HARDWARE_TESTS.md; preserved copy `captures/local/`; fixture
`captures/fixtures/hw-gamecube-gbp-2026-09-15-initirqb-0001.gbpreplay`
(111 operations, replays with 0 mismatches, carries the physical handler
record). Setup identical to GBP-INIT-003A. Time base 40.5 MHz. PI HSP was
masked until the handler had been installed after a latched cause, then
unmasked exactly once; INTMR was changed only through libogc2's mask API
(audited on the objects: one `__UnmaskIrq` call site, no INTMR store).
Every claim below is **FACT (hardware)** unless marked otherwise;
interpretations are kept apart from observations. Every µs value is a
tick count divided by 40.5 MHz; no µs value is a hardware specification.

## GBP-HW-035 — The GBP-INIT-003A sequence reproduced: same baseline, same A1/A2 read-backs, the first cause 105.29 ms after A2

Handshake `C3→3C`, `3C→C3`, `FF→00`, `00→FF`, all 32 bytes uniform (no
byte-0 extra; vote, byte-1 and whole-block criteria 4/4). PI PRE/BASE/P0
INTSR `0x00010000`, INTMR `0x000001FA`. BASE CONTROL `90×32` → 0x90; IRQ
`8A 8A AE AE ×8` → 0x8AAE; TEST `00×32`. CONTROL := 0x8C read back
`8C×32` (no extra) at P0 and in every later read up to POSTACK. A1
`IRQ := 0x8AAE` → `8A 8A AA AA ×8` (0x8AAA) at +22 ticks, +50 µs, +500 µs
and at A2PRE. A2 `IRQ := 0x0000` → `00×32` at +18 ticks, +50 µs, +500 µs,
+5 ms, +50 ms, INTSR bit 13 = 0 throughout. The INTSR poll at time base
3679890204 (= t_a2 + 4264071 ticks = 105.286 ms after A2; 105.93 ms after
the CONTROL write; the 709727th poll) returned `0x00012000`; the EVENT
snapshot read INTSR `0x00012000`, INTMR `0x000001FA`, CONTROL 0x8C, IRQ
`04 04 04 00 ×8` (0x0400). **FACT:** the A1/A2 read-backs of GBP-HW-028/029
and the first cause of GBP-HW-030 reproduced in a second run; the
EVENT-after-A2 interval differed from 003A's by 503 ticks (12.4 µs):
105.286 ms vs 105.273 ms. Two data points, both with no cartridge; no
mechanism claimed (U-GBP-014/024).

## GBP-HW-036 — Second source 0x0100 between the EVENT and PREUNMASK; the pre-unmask baseline

PREUNMASK snapshot 36756 ticks (907.6 µs) after the EVENT (the window's
records were formatted in between), after `IRQ_Request(26, handler)` had
returned NULL and the record read count 0 / fired 0: INTSR `0x00012000`
in both PI samples, INTMR `0x000001FA` in both, CONTROL `8C×32` (0x8C),
IRQ `05 05 00 00 / 05 05 05 00 ×7` → 0x0500 by both readings. **FACT:** bit
8 (0x0100) rose after the EVENT snapshot and before PREUNMASK (≤ 907.6 µs;
003A: ≤ ≈1.0 ms), with masks 0 and bit 15 = 0; the latched PI cause did
not change and the CPU took no exception (INTMR bit 13 = 0). This is the
state immediately before the first delivery: cause latched, mask closed,
two sources pending on the device, CONTROL running.

## GBP-HW-037 — `__UnmaskIrq(IM_PI_HSP)` delivered the latched cause to the handler as IRQ 26 inside the call; one entry; the handler observed INTMR bit 13 = 1 and closed it

`t_unmask = 3679931504` read immediately before `__UnmaskIrq`; the call
returned at `t_post = 3679931761` (257 ticks = 6.35 µs) with INTSR
`0x00010000`, INTMR `0x000001FA` and the record already `fired=1`. Record
(copied after the main re-mask, formatted outside the handler):
`t_entry = 3679931582` (78 ticks = 1.926 µs after t_unmask), INTSR at entry
`0x00012000`, INTMR at entry `0x000021FA` (bit 13 = 1), INTMR after
`__MaskIrq` `0x000001FA`, `count=1`, `fired=1`, `reentry_t/intsr/intmr = 0`.
The wait loop found `fired` at its first poll; `REMASKCHK` read INTMR
`0x000001FA` (the main re-mask was idempotent). **FACT (restricted):** a
PI HSP cause that had been latched while INTMR bit 13 = 0 was delivered
to the registered IRQ 26 handler once `__UnmaskIrq(IM_PI_HSP)` opened the
mask; the exception was taken before the call returned (ENV-IRQ-003); the
handler saw INTMR bit 13 = 1 at entry and `__MaskIrq` from inside the
handler cleared it; the handler was entered exactly once. **Latency
observed:** 78 ticks ≈ 1.926 µs from the time-base read before the call
to the handler's own first time-base read — a single observation of this
software (libogc2 r2442.094b250, this handler, this DOL), not a hardware
timing specification. Not extrapolated to other PI interrupts.

## GBP-HW-038 — The handler's W1C cleared the latched PI cause while both device sources stayed pending; no re-assert for ≥ 324 µs

Inside the handler, after the mask: INTSR before the W1C `0x00012000`;
one `INTSR := 0x2000`; INTSR immediately after `0x00010000`; 148 ticks
(3.654 µs) after the entry: INTSR `0x00010000`, INTMR `0x000001FA`. Main
loop: UNMASKPOST `0x00010000`, REMASKCHK `0x00010000`, PREACK 7277 ticks
(179.7 µs) after the entry `0x00010000` in both samples with CONTROL 0x8C
and IRQ `05 05 05 00 ×8` (0x0500: both device sources still pending, odd
bits 0, bit 15 = 0 — the same device state in which the cause had been
raised), POSTACK 13118 ticks (323.9 µs) after the entry `0x00010000` in
both samples (25 µs after the device ACK). **FACT:** with sources 0x0400
and 0x0100 pending on the device, masks 0, bit 15 = 0 and CONTROL 0x8C,
one W1C of INTSR bit 13 cleared it and it stayed clear in every read for
at least 179.7 µs before the device was acknowledged and 323.9 µs
overall. **Interpretation (U-GBP-022):** the simple model "the HSP input
to the PI is a sustained level held while an enabled source is pending"
is **REJECTED** for these conditions (a held level would have re-set the
latch after the W1C). Still admissible, not distinguished by this run: a
pulse per event; an edge/event assertion; a transient line; a device-side
deassert mechanism separate from the source latch (for instance a line
that drops once the PI has captured it, or that follows something other
than the source bits). "HSP is pulse" is **not** promoted to FACT.

## GBP-HW-039 — Device ACK `IRQ := 0x8500` (= 0x0500 | 0x8000) read back 0x8000: both sources cleared, bit 15 read 1, odd bits 0; PI unchanged

PREACK IRQ 0x0500 by both readings (Disc = GBI, `semantic_disagree`
not raised); write `85 00 ×16` (u16 replicated, one 32-byte DMA,
completed); POSTACK snapshot 1018 ticks (25 µs) after the write's
completion: IRQ `80 80 00 00 ×8` → 0x8000 by both readings, CONTROL 0x8C,
INTSR `0x00010000` twice, INTMR `0x000001FA`. **FACT:** the even bits 8
and 10 written as 1 while pending cleared (write-1-to-clear, third
observation for these bits); bit 15 written 1 read 1 with no source
pending; the odd bits written 0 read 0; the PI cause did not rise. The
ACK is GBI's form (`read | 0x8000`, GBP-IRQ-003/004) and A1's physically
validated write; no main-loop PI W1C was needed (`isr_pi_w1c=1
main_pi_w1c=0`: the only INTSR W1C of the run was the handler's).

## GBP-HW-040 — The device sources re-set within ≈143 µs of the ACK, after CONTROL had been restored; no PI cause followed; stop word validated again

CONTROL := 0x90 (`90×32` read back) 5780 ticks (142.7 µs) after the
POSTACK snapshot; IRQSTOPPRE, read right after, returned
`85 85 00 00 / 85 85 00 00 / 85 85 04 00 / 85 85 04 00 / 85 85 00 00 /
85 85 04 00 / 85 85 00 00 / 85 85 04 00` → 0x8500 by both readings: bits 8
and 10 set again, bit 15 still 1, odd bits 0. Stop `IRQ := 0x8500 |
0x8AAA = 0x8FAA` (`8F AA ×16`, completed) → IRQSTOPPOST `8A 8A AA AA ×8`
(0x8AAA, `masks_readback=1 bit15_readback=1`). CLEANUPCHK, MASKCHK and
FINAL read INTSR `0x00010000`, INTMR `0x000001FA`. **FACT:** sources
0x0100 and 0x0400 were set again at most ≈143 µs after having been
cleared by the ACK (lower bound unknown; the CONTROL restore lies in
between), and no PI cause was raised afterwards while bit 15 = 1 and
CONTROL = 0x90; the Start-up Disc stop word cleared them and re-armed the
odd bits and bit 15 (second physical validation, GBP-HW-032). **Not
claimed:** which of bit 15 = 1 and CONTROL 0x10 kept the cause away (they
changed together, as in GBP-INIT-002), or what re-set the sources (the
running AGB's next audio/video requests is the consistent HYPOTHESIS;
sources reasserted after the ACK and before the stop, under the teardown
state — that is all this run shows).

## GBP-HW-041 — Teardown, restores, expansion-code view, byte-0 and offset-2 observations, statistics, logging defect

Handler restore `IRQ_Request(26, NULL)` returned the experiment's handler
(`ok=1`); MASKCHK INTMR `0x000001FA` (`mask_ok=1`); AR_INFO `0x005B →
0x0043` read back; FINAL under code 0: CONTROL `00×32`, IRQ `90×32`
(0x9090), INTSR `0x00010000`, INTMR `0x000001FA` — fifth observation of
the code-3 → code-0 view change (U-GBP-004). `restore=ok`; writes
`ctl_exp 1/1, a1 1/1, a2 1/1, ack 1/1, stop 1/1, ctl_restore 1/1,
uncertain=0`; 51 transfers, 0 timeouts, 0 busy, 0 errors, 140 lines, 0
dropped, 0 truncated; `REGION formatted_inside=0`. **Byte 0:** no extra
bit in any block of this run (TEST, CONTROL 0x8C/0x90/0x00, IRQ
0x8AAE/0x8AAA/0x0400/0x0500/0x8000/0x8500/0x9090) — the first run without
any (U-GBP-020/021). **Offset ≡ 2 mod 4:** the empirical `lo | (hi &
0x05)` pattern (U-GBP-025) held for 0x8AAE, 0x8AAA, 0x0000, 0x0400, the
PREACK 0x0500, 0x8000, 0x8AAA and 0x9090 reads and for groups 1–7 of the
PREUNMASK 0x0500 read, but not for group 0 of that read (`00`) and not for
any group of the IRQSTOPPRE 0x8500 read (`00` or `04` where the pattern
predicts `05`, varying within one 32-byte DMA) — the pattern is not a
rule; both references ignore that byte. **Logging defect of this build,
not a hardware observation:** `TEARDOWN start … pi_policy=never_unmasked`
printed the shared 003A teardown's fixed label in a run that had unmasked
once (`RESTOREB unmasked=1 masked_again=1`); corrected for later builds
(`pi_policy=unmasked_once`), the log stays as written (DEVLOG 2026-09-15).
`irq_attempted=3` in that record counts A1, A2 and the ACK before the stop
word; the final `WRITES` record counts 4/4.

## GBP-PI-005 — A latched PI HSP cause is delivered to the CPU as IRQ 26 when INTMR bit 13 opens; the handler can close the mask and clear the cause; the cause does not re-assert while the device sources stay pending

**Claim:** with INTSR bit 13 latched and INTMR bit 13 = 0, opening the
mask with libogc2's `__UnmaskIrq(IM_PI_HSP)` delivered one external
interrupt to the IRQ 26 handler before the call returned (GBP-HW-037);
inside the handler INTMR bit 13 read 1, `__MaskIrq(IM_PI_HSP)` cleared it,
one `INTSR := 0x2000` cleared bit 13 and it stayed clear with the device
sources still pending (GBP-HW-038); the handler was entered once, the
device was acknowledged afterwards by the main loop with `read | 0x8000`
(GBP-HW-039), and the previous handler and the masked state were restored
(GBP-HW-041). **Status:** FACT (hardware), restricted to bit 13 / HSP on
this console with libogc2 r2442.094b250 and the one-shot handler of
`gbp_irq_oneshot.h` — the first physical validation of CPU delivery of
IRQ 26 in Open-GBP; promotes the delivery half of GBP-PI-003 to FACT for
bit 13. Latency 78 ticks: one observation, no specification. Not
extrapolated to other PI sources. **Open (U-GBP-022):** the nature of the
device line (pulse / edge / transient / separately deasserted); only the
sustained-level model is rejected.

## ENV-IRQ-003 — Hardware confirmation of the libogc2 unmask analysis: the pending exception is taken inside `__UnmaskIrq`

**Claim:** `__UnmaskIrq` rebuilds INTMR under `_CPU_ISR_Disable` and
restores MSR[EE] at its end, so a cause that is already latched is taken
as an exception before the call returns (ENV-IRQ-002, source and binary
analysis). GBP-HW-037 observed exactly that: the handler's entry time base
lies between the read before the call and the read after it
(3679931504 < 3679931582 < 3679931761), and the read after the call
already showed the handler's effects (INTSR cleared, INTMR closed, record
fired). **Status:** FACT (hardware) for this libogc2 build. Consequence
for measurements: a "post-unmask" time base is not a lower bound of the
delivery; the latency of a latched cause is t_entry − t_unmask, taken
before the call (the 003B probe does this).

## GBP-IRQ-008 — IRQ-register model after GBP-INIT-003B (per bit; supersedes GBP-IRQ-007 where stated)

| Bit(s) | Hardware observations (003A + 003B, 2026-09-15) | Reference usage (code, FACT) | Status of the semantics |
|---|---|---|---|
| 2 (0x0004) | idle 1; written 1 (A1) → 0, twice (GBP-HW-028/035) | Disc slot 3 (stop / video reset); Dolphin GamePak | source, W1C **FACT**; function "game pak / stop event" FACT (code), physically untested |
| 8 (0x0100) | rose by itself ≤ 1 ms after 0x0400 in both runs; written 1 while pending (stop 003A, ACK 003B, stop 003B) → 0 three times; re-set within ≈143 µs after the ACK (GBP-HW-040) | Disc slot 5 → VIDEO read; GBI VIDEO read 0xF00 | source, W1C **FACT**; "video request of the AGB" **CORROBORATED** (drivers) |
| 10 (0x0400) | rose by itself 105.27 / 105.29 ms after A2 in both runs and raised PI INTSR bit 13 with masks 0 / bit 15 0 (GBP-HW-030/035); written 1 while pending → 0 three times; re-set within ≈143 µs after the ACK | Disc slot 4 → AUDIO read; GBI AUDIO read 0x1000 | source, W1C **FACT**; propagation to the PI **FACT** (in the A2 state); "audio request of the AGB" **CORROBORATED** (drivers) |
| 0, 4, 6 | never seen set | Disc slots 0, 2, 1 (user callback, sleep → CONTROL 0x10, serial) | by pairing/code only: **CORROBORATED** W1C, functions per code |
| 1, 3, 5, 7, 9, 11 (0x0AAA) | idle 1; written 1 (A1, stop) → 1; written 0 (A2, ACK) → 0 for ≥ 50 ms; with all six = 1 (and bit 15 = 1) pending sources raised no PI cause for 2 s (INIT-002); with all six = 0 (and bit 15 = 0) the next 0x0400 raised the cause twice (003A, 003B) | Disc: per-slot mask levels, handler filter `pending & ~(pending >> 1)`; GBI: all 0 before waiting | level-written **FACT**; pairing **CORROBORATED**; polarity 1 = masked / 0 = enabled **CORROBORATED** (bit 15 still moved with them in every run) |
| 12–14 | written 0 by A2 / ACK / stop → 0; never seen 1 | never used | **UNKNOWN** function; keep 0 |
| 15 (0x8000) | idle 1; written 0 (A2) → 0 for ≥ 50 ms; written 1 (stop 003A, ACK 003B) → 1 with no source pending; the PI cause arrived twice while it read 0; after the ACK left it 1, the sources re-set under CONTROL 0x90 and no PI cause followed (GBP-HW-040) | Disc: 1 at handler entry and at stop, 0 at start/exit; GBI: `read \| 0x8000` then 0; Dolphin: `IRQ_ASSERTED` | **FACT:** level-written and persistent both ways under the conditions tested (three writes read back). "W1C pending summary" **REJECTED**. Functional reading "global hold / mask, 1 = held" **HYPOTHESIS**: consistent with every run, never isolated (in 003B's IRQSTOPPRE state CONTROL 0x10 had already been set again). Do not name it |
| PI bit 13 | captured while masked, latched, W1C-cleared (GBP-PI-004); delivered as IRQ 26 on unmask, masked from inside the handler, W1C-cleared while the sources stayed pending, no re-assert ≥ 324 µs (GBP-PI-005) | libogc2 dispatch `cause & mask` (ENV-IRQ-001) | **FACT** for bit 13; device line nature **UNKNOWN** minus the rejected sustained-level model (U-GBP-022) |
| Service protocol | ISR: mask → one PI W1C; main: `IRQ := read \| 0x8000` under the running CONTROL → stop word — one full cycle validated (GBP-HW-037…040) | GBI order PI → GBP; Disc order GBP → PI → GBP → GBP | one cycle **FACT**; re-arm (`IRQ := 0` after the ACK) and repeated service **never exercised** |
| Write layout | u16 replicated 16× accepted for 0x8AAE, 0x0000, 0x8500, 0x8FAA; read-back offset-2 byte is not a rule (GBP-HW-041, U-GBP-025) | GBI 0x80015da4 | layout **FACT** for the four values written |

## GBP-HW-042 — GBP-INIT-004 (2026-09-16): the 003A sequence and the first cause reproduced a third time; byte-0 extras present

**Observation** (log `logs/GBP-INIT-004_initirq4-0001.log`, 19247 bytes,
sha256 `c9167224…775b`; build initirq4-0001, commit 741630b, DOL
`1da0d7b4…010c`; fixture
`hw-gamecube-gbp-2026-09-16-initirq4-0001.gbpreplay`, 112 operations, 0
mismatches): PRESENT 4/4 (one byte-0 extra in the handshake: pattern 3C
read `C7 C3 …`, `all32_ok=3`); PI `0x00010000` / `0x000001FA`; BASE
CONTROL 0x90, IRQ 0x8AAE (`8E 8A AE AE …`); CONTROL 0x90 → 0x8C (every 0x8C
read `AC 8C 8C …`); A1 `IRQ := 0x8AAE` → 0x8AAA at +18 ticks / +50 µs /
+500 µs; A2 `IRQ := 0x0000` (`t_after=1048847666`) → 0x0000 at +18 ticks …
+50 ms with CONTROL 0x8C and INTSR bit 13 = 0; EVENT at 1053111645 =
4263979 ticks = **105.283 ms** after A2 (003A 105.273, 003B 105.286):
INTSR `0x00012000`, INTMR `0x000001FA`, CONTROL 0x8C, IRQ 0x0400; 0x0100
appeared within 971.8 µs (PREUNMASK-0 read 0x0500). **Status:** FACT
(hardware), third observation of the same sequence and cadence
(GBP-HW-028…031, GBP-HW-035/036). The delay after A2 is repeatable to
≈13 µs across three runs with no cartridge (U-GBP-014).

## GBP-HW-043 — Second CPU delivery of a latched HSP cause, through the multi-cycle handler with its generation bookkeeping

**Observation:** `IRQ_Request(26, hsp_backend_oneshot_isr_multi)` returned
NULL after the latched cause; slot 0 clean; generation 0 published with
INTMR bit 13 = 0; PREUNMASK-0: INTSR bit 13 = 1 twice, INTMR bit 13 = 0
twice, CONTROL 0x8C, IRQ 0x0500, Disc == GBI. `__UnmaskIrq(IM_PI_HSP)` at
`t_unmask=1053156576` delivered IRQ 26 inside the call (`t_post` +256
ticks with INTSR `0x00010000`, INTMR `0x000001FA`, `fired=1` — ENV-IRQ-003
again). Handler record, slot 0: `t_entry=1053156665` (89 ticks = 2.198 µs;
003B: 78), INTSR at entry `0x00012000`, INTMR at entry `0x000021FA`, INTMR
after `__MaskIrq` `0x000001FA`, INTSR before the W1C `0x00012000`, after
the one W1C `0x00010000`, second read 142 ticks (3.506 µs) after the entry
`0x00010000` / `0x000001FA`; `count=1 fired=1 reentry=0`;
`expected_gen=0 entries_total=1 generation_errors=0 anomaly_count=1
anomaly_fired=0`. Main re-mask idempotent (`main_mask_ok=1`). **Status:**
FACT (hardware) — a physical confirmation of GBP-PI-005 with a different
handler body (the 003B extended body behind the generation wrapper of
`gbp_irq_oneshot.h`): the mask-first / one-W1C / latched-and-cleared
mechanics hold; the bookkeeping (one entry, slot 0, no generation error)
worked. An additional observation of the same semantics, not a new
independent discovery. Latency 89 ticks: one observation, no
specification (two values so far: 78, 89).

## GBP-HW-044 — PREACK: both AV sources still pending 209.8 µs after the entry, PI bit 13 clear; no incidental acknowledge

**Observation:** PREACK-0 at 1053165161 (8496 ticks after the entry):
INTSR `0x00010000` in both samples, INTMR `0x000001FA`, CONTROL 0x8C, IRQ
0x0500 (Disc == GBI; `85 05 04 00 / 05 05 05 00 ×7`). The handler had
written only `INTSR := 0x2000`; no device write happened between the
delivery and this read. **Status:** FACT (hardware), second observation of
GBP-HW-039 (the PI cause does not re-assert after its W1C while the device
sources stay pending under bit 15 = 0, masks 0, CONTROL 0x8C).

## GBP-HW-045 — After the ACK: 0x0400 present with bit 15 = 1, CONTROL 0x8C and PI INTSR bit 13 = 0 (26 µs); 0x0100 absent; no PI cause through the end of the run

**Observation:** ACK-0 `IRQ := 0x0500 | 0x8000 = 0x8500` (u16 replicated,
rc ok, attempted 1 / completed 1, `t_after=1053170192`). POSTACK-0 snapshot
at 1053171245 = **1053 ticks = 26.000 µs later**: IRQ **0x8400** (`84 84 04
00 ×8`, Disc == GBI), INTSR `0x00010000` in **both** samples, INTMR
`0x000001FA`, CONTROL 0x8C. IRQSTOPPRE, after the CONTROL restore (≈+195 µs
after the ACK): 0x8400 again. CLEANUPCHK and FINAL (≥ 0.76 ms after the
handler's W1C): INTSR `0x00010000`; the main loop never wrote INTSR
(`main_w1c=0 teardown_w1c=0`), and bit 13 is latched (GBP-HW-033), so no
HSP cause was captured in that interval. **Status:** FACT (hardware),
restricted to the observed conditions: **a source 0x0400 can be present in
the IRQ register with CONTROL 0x8C and bit 15 = 1 (odd bits 0) while PI
INTSR bit 13 remains 0**; the source 0x0100 was cleared by the same write
and stayed clear for ≥ 195 µs. **Not distinguished by this run:** (A) the
W1C of bit 10 in the ACK did not clear 0x0400, from (B) 0x0400 cleared and
re-asserted within the 26 µs before the sample (U-GBP-028). **Not claimed:**
"the ACK failed" (the write completed and cleared bit 8); the mechanism of
the reappearance; a period. **Model consequence:** "a present source implies
an immediately latched HSP cause" is rejected under bit 15 = 1 / CONTROL
0x8C; the hypotheses "bit 15 holds or gates the request", "status and
request generation are separate", "the re-request needs a new event or the
drain of the block" stay HYPOTHESIS (U-GBP-007, U-GBP-027). Compared with
003B (0x8000 at +25.1 µs, both sources back at ≈+168 µs after CONTROL 0x90),
the reappearance no longer requires the CONTROL change; two runs establish
no cadence.

## GBP-HW-046 — Teardown of the aborted cycle: STOP 0x8400 | 0x8AAA = 0x8EAA → 0x8AAA; every restore ok; no re-arm written

**Observation:** teardown variant `S3_cycle_aborted` with the CPU masked:
CONTROL 0x8C → 0x90 (`t_after=1053177991`, read back `90 ×32`); IRQSTOPPRE
0x8400; stop word `IRQ := 0x8EAA` read back 0x8AAA (`masks_readback=1
bit15_readback=1`); CLEANUPCHK INTSR `0x00010000` → no cleanup; handler
restored (`old_handler=null`); MASKCHK INTMR `0x000001FA`; AR_INFO 0x005B →
0x0043; FINAL under code 0 `00` / `9090`. `restore=ok`, 51 transfers, 0
timeouts / busy / errors, 152 lines, 0 dropped / truncated, `WRITES
irq_attempted=4 irq_completed=4 uncertain=0` (A1, A2, ACK, STOP),
`rearms 0/0`, `next_causes 0`, `completed_cycles 0` (the boundary was not
reached; one delivery and one ACK happened). **Status:** FACT (hardware).
Third stop-word combination validated physically (0x8FAA twice before);
**no `IRQ := 0` after an acknowledge was written in this run** — nothing
here is evidence about the re-arm (U-GBP-027).

## GBP-HW-047 — Byte 0 and offset-2 observations of GBP-INIT-004

**Observation:** byte-0 extras in this run: TEST `C7` (3C pattern), CONTROL
`AC` in all thirteen 0x8C reads, IRQ `8E` in every 0x8AAE / 0x8AAA read
(BASE, P0, A1PRE, A1-0 … A2PRE, IRQSTOPPOST), `8D` at PREUNMASK-0 (0x0500),
`85` at PREACK-0 (0x0500); none at EVENT (0x0400), POSTACK-0 / IRQSTOPPRE
(0x8400), FINAL (0x9090), CONTROL 0x90 / 0x00, TEST 3C / 00 / FF. Disc and
GBI readings agreed in every read, `vote == byte 0x1F` everywhere; no
decision used byte 0. Offset ≡ 2 mod 4: the `lo | (hi & 0x05)` pattern
held for every read except group 0 of the two 0x0500 reads (`04` where it
predicts `05`; 003B: `00`). **Status:** FACT (hardware) for the bytes;
the extras are run-dependent (none in 003B, GBP-HW-041; 0x04/0x20/0x24 in
003A, GBP-HW-034; 0x04/0x20/0x80/0x88 here) — U-GBP-020/021/025 unchanged
in substance: byte 0 is not a reliable source for semantic decisions.

## GBP-IRQ-009 — IRQ-register model after GBP-INIT-004 (delta over GBP-IRQ-008)

| Element | Added by GBP-INIT-004 (2026-09-16) | Status |
|---|---|---|
| Bit 10 (0x0400) | rose 105.283 ms after A2 (third run); cleared by A1 twice before; after the ACK `0x8500` it read **1 again 26 µs later** while bit 8 read 0 (GBP-HW-045) — cleared-and-re-set or never cleared: undetermined | source, W1C **F** (three runs); behavior after an ACK without a drain: **U** (U-GBP-028) |
| Bit 8 (0x0100) | appeared within 0.97 ms of 0x0400; cleared by the ACK and absent for ≥ 195 µs (003B: back within ≈143 µs after the CONTROL restore) | W1C **F**; re-set timing **U** |
| Bit 15 (0x8000) | written 1 by the ACK; **with bit 15 = 1, odd bits 0, CONTROL 0x8C and 0x0400 present, no PI cause for ≥ 140 µs; with CONTROL 0x90 afterwards, none through FINAL (≥ 0.76 ms from the handler's W1C)** | level-written **F**; "hold / gate" **H** (consistent again, still not isolated); "source present ⇒ PI latched" **rejected** under bit 15 = 1 |
| PI bit 13 | delivered a second time (multi-cycle handler), cleared by the handler's single W1C while two sources were pending, no re-assert with the sources pending under bit 15 = 0 (209.8 µs) nor with 0x0400 present under bit 15 = 1 (to FINAL) | GBP-PI-005 **F** confirmed; latched-bit semantics **F** |
| Service cycle | cause → delivery → mask-first → one W1C → device ACK `read \| 0x8000`: **second physical cycle**; the ACK's readback contradicts "sources zero after an ACK" as a general property | one cycle **F** (×2); **re-arm `IRQ := 0` after an ACK never written** (U-GBP-027) |
| Stop word | `read \| 0x8AAA` from 0x8400 → wrote 0x8EAA → read 0x8AAA | layout / effect **F** (third value) |
| Clean-boundary premise of 004 | "acknowledged sources gone at POSTACK" did not hold 26 µs after the ACK; the references never read the register between the ACK and the re-arm and never require it (decompiles, DEVLOG 2026-09-16) | design premise **rejected as a requirement** (not a hardware property) |

## Physical observations — GBP-AV-SERVICE-001, 2026-09-16 (GBP attached; first drained service, first re-arm, next cause)

Source for every entry: `logs/GBP-AV-SERVICE-001_avsvc-0001.log` (23154
bytes, sha256 `d0324b6d…3713`) and the block sidecar
`logs/GBP-AV-SERVICE-001_avsvc-0001-blocks.bin` (8204 bytes, sha256
`1c17a2d7…dc1e`), build avsvc-0001, commit d3a6d23, DOL `d9e6dccd…56ff`;
log verbatim in HARDWARE_TESTS.md; fixture
`hw-gamecube-gbp-2026-09-16-avsvc-0001.gbpreplay` + `-blocks.bin` (132
operations, 0 mismatches, 0 exhausted, 0 blocks missing, 0 CRC mismatches).
Time base 40.5 MHz (1 tick = 24.69 ns). One run: no entry below claims a
period, a rate or a universal temporal rule.

## GBP-HW-048 — The 003A sequence and the first cause reproduced a fourth time; third CPU delivery, through the 003B extended one-shot

**Observation:** detection PRESENT (4/4), AR_INFO 0x0043 → 0x005B, BASE
CONTROL 0x90 / IRQ 0x8AAE, transform to 0x8C, A1 `IRQ := 0x8AAE` → 0x8AAA,
A2 `IRQ := 0` → 0x0000 in five samples; PI INTSR bit 13 = 1 with INTMR bit
13 = 0 at `t_event=3391329164` = **4264215 ticks = 105.289 ms after A2**
(003A 105.273, 003B 105.286, 004 105.283 ms; four runs within 16 µs, no
cartridge), IRQ 0x0400; 0x0500 at PREUNMASK 0.92 ms later with the PI cause
still latched. `__UnmaskIrq` delivered the cause inside the call: entry
**72 ticks = 1.778 µs** after t_unmask (003B 78, 004 89), INTSR
`0x00012000`, INTMR `0x000021FA`; mask-first, one W1C → `0x00010000`,
second read 147 ticks later unchanged, `count=1 reentry=0`; the main
re-mask idempotent. **Status:** FACT (hardware), fourth / third observation
of GBP-HW-030/035/042 and GBP-PI-005; the latencies are observations of
three builds, not a specification.

## GBP-HW-049 — PRESVC: both AV sources pending 188.0 µs after the handler entry, PI clear, bit 15 = 0 — the authoritative service read

**Observation:** snapshot at 3391379306 (7612 ticks after the entry): INTSR
`0x00010000` in two samples, INTMR `0x000001FA`, CONTROL 0x8C, IRQ
**0x0500** (`17 05 01 00 / 05 05 05 00 ×7`, Disc == GBI), odd bits 0, bit
15 = 0, high bits 0. The pass derived `pending=0500 drain=0500 ack=8500`
from this read alone. **Status:** FACT (hardware); the same device state as
003B's PREACK (+179.7 µs) and 004's PREACK-0 (+209.8 µs): a pending pair
does not re-latch the PI after the handler's W1C under bit 15 = 0.

## GBP-HW-050 — First whole-block AUDIO read: one DMA of 0x1000 bytes from index 0x8 completed in 66.5 µs

**Observation:** `AUDIOREAD idx=8 addr=01800000 len=1000 selected=1
attempted=1 completed=1 rc=ok t_start=3391385098 t_end=3391387790 dt=2692
wait_ticks=2475 polls=760 csr_before=0804 csr_after=0804`: one ARAM → main
memory DMA of the whole block (the 32-byte routine with the length field
0x1000; `DCFlushRange` before, `DCInvalidateRange` after), **2692 ticks =
66.47 µs around the call, 2475 ticks (61.1 µs) of completion wait**, DSP CSR
0x0804 before and after (no DMA in progress, no stale flag), no timeout, no
busy refusal; the 4096 bytes reached the buffer (CRC-32 `FEC5E4E7` in the
log's BLOCK record and in the sidecar, windows equal). ≈ 21.0 time-base
ticks (519 ns) per 32 bytes. **Status:** FACT (hardware) for the transfer
(the device accepts a single DMA of 0x1000 from the AUDIO index and
completes it; GBP-AUD-001 size corroborated by a completed read of that
length, not proven by it). **Not claimed:** a transfer rate (one run, call
overhead included; Dolphin's model gives 506 ns per 32 bytes — a
coincidence to note, not a promotion); the content (GBP-HW-057).

## GBP-HW-051 — First whole-block VIDEO read: one DMA of 0xF00 bytes from index 0x1 completed in 61.4 µs

**Observation:** `VIDEOREAD idx=1 addr=01100000 len=0f00 selected=1
attempted=1 completed=1 rc=ok t_start=3391387818 t_end=3391390303 dt=2485
wait_ticks=2319 polls=712 csr_before=0804 csr_after=0804`: **2485 ticks =
61.36 µs around the call, 2319 ticks (57.3 µs) of wait**, started 28 ticks
after the AUDIO completion (never two DMAs in flight), CRC-32 `FE45FF08`
in the log and the sidecar. Service `dt_service=10997` ticks = 271.5 µs
from the PRESVC snapshot to this completion (the probe's own reads and
logging included). **Status:** FACT (hardware) for the transfer; the
duration and the service time are measurements of this probe, not
hardware properties; the block's true size and geometry are not tested by
a DMA of the requested length (GBP-VID-001 stays CORROBORATED).

## GBP-HW-052 — POSTDRAIN: after both blocks were read the register still read 0x0500 and no PI cause latched during the drain

**Observation:** snapshot at 3391394064, 3761 ticks = 92.9 µs after the
VIDEO completion: IRQ **0x0500** (`17 05 01 00 / 05 05 05 00 ×4 / 05 05 04
00 / 05 05 05 00 ×2`), INTSR `0x00010000` twice, INTMR `0x000001FA`, CONTROL
0x8C; `relatch=0`. From the handler's W1C to this read (≥ 552 µs) both
sources stayed pending under bit 15 = 0 and the PI captured nothing.
**Status:** FACT (hardware), observational: reading the two blocks did not
by itself clear the source bits within ≈ 93 µs, and did not raise a PI
cause. **Not concluded:** that a block read never changes the device's
internal state (request bookkeeping, buffer pointers, the next event) —
only the register's bits at one instant were observed; the references
never read the register here.

## GBP-HW-053 — ACK after the drain: `IRQ := 0x8500` read back 0x8000 25.9 µs later, PI clear, no main W1C; contrast with the undrained ACK of GBP-INIT-004

**Observation:** `IRQ := 0x0500 | 0x8000 = 0x8500` (u16 replicated, rc ok,
`t_after=3391399980`); POSTACK at 3391401028 = **1048 ticks = 25.88 µs**:
IRQ **0x8000** (`81 80 00 00 / 80 80 00 00 ×7`, Disc == GBI) — both sources
0, bit 15 = 1, odd bits 0, high bits 0 — INTSR `0x00010000` in both
samples, INTMR `0x000001FA`, CONTROL 0x8C; `source_after_ack=0000
relatch=0 main_w1c=0`; PICLEAN (177 µs later, immediately before the
re-arm) INTSR `0x00010000` / INTMR `0x000001FA`. Bit 15 read 1 with sources
0 and PI clear for the whole ACK → re-arm interval (≥ 203 µs).
**Status:** FACT (hardware) for the readings. **Safe conclusion:** in this
run a service that drained both blocks before its ACK was followed by a
source-clean read-back at the distance at which the undrained ACK of 004
read 0x8400 (26.0 µs; the undrained ACK of 003B read 0x8000 at 25.1 µs):
the observable state after the ACK differed between the drained and the
undrained pass in the direction the references' order (drain before the
re-arm) predicts. **Not concluded:** a microscopic causality (that the
drain consumed or released the 0x0400 request; that 004's 0x0400 was a
level the drain would have cleared; a period). U-GBP-028 partially closed:
an ACK after a drain can produce a source-clean snapshot; the undrained
case stays undetermined and non-blocking.

## GBP-HW-054 — First physical re-arm `IRQ := 0x0000` after a serviced cycle

**Observation:** with `pi_clean=1` (INTSR `0x00010000`, INTMR `0x000001FA`)
verified immediately before, `IRQW tag=REARM before=8000 write=0000` (`00
×32`), rc ok, attempted 1 / completed 1, `t_rearm=3391408218`,
`t_after=3391408974`, 7190 ticks = 177.5 µs after the POSTACK snapshot —
GBI's `IRQ := 0` after its ACK, written for the first time by Open-GBP after
an acknowledged and drained cycle (004 stopped before it). **Status:** FACT
(hardware) for the write and its completion; its effect is GBP-HW-055.

## GBP-HW-055 — Next HSP cause after the re-arm: PI INTSR bit 13 = 1 with IRQ 0x0400, 43.9 µs after `IRQ := 0`, IRQ 26 masked, never delivered (REARMPOST outcome B)

**Observation:** REARMPOST snapshot at 3391409996 = **1778 ticks = 43.90 µs
after t_rearm**: INTSR **`0x00012000` in both samples**, INTMR `0x000001FA`
(bit 13 = 0), CONTROL 0x8C, IRQ **0x0400** (`15 04 00 00 / 04 04 04 00 ×7`),
odd bits 0, bit 15 = 0, high bits 0, unexpected 0 → `outcome=B_latched`;
`NEXTCAUSE found=1 immediate=1 since_rearm=1778 polls=0 delivered=0`;
`unmasks=1 deliveries=1`: no second unmask, no second handler entry; the
cause stayed latched until the teardown's W1C (GBP-HW-056). **Status:**
FACT (hardware): after delivery → drained service → ACK → PI clean →
`IRQ := 0`, a new HSP cause with a valid AV source was captured by the PI
within 43.9 µs while the CPU stayed masked, and a masked latched cause
survives to be cleared later. **Not concluded:** that the 0x0400 request
arose after the re-arm (a new event) rather than being held under bit 15 =
1 and released by the write — the register was not sampled between PICLEAN
and REARMPOST and the 43.9 µs include the write; a period; what a second
cycle would show. Data point for U-GBP-007 (bit 15: 1 with sources 0 and
no cause for ≥ 203 µs; 0 with a cause within 43.9 µs), U-GBP-022 (bit 13
latched again after the re-arm, cleared once), U-GBP-014 and U-GBP-027.

## GBP-HW-056 — Teardown with the second cause latched: stop 0x0500 | 0x8AAA = 0x8FAA → 0x8AAA, one PI W1C, every restore ok

**Observation:** variant `S4B_next_cause_latched`, CPU masked: CONTROL 0x8C
→ 0x90 (`t_after=3391417891`, read back 0x90); IRQSTOPPRE **0x0500** —
0x0100 had joined 0x0400 between the REARMPOST read and this one (≤ 12203
ticks = 301 µs after REARMPOST, an upper bound; 003B: both sources back
≈ 168 µs after its ACK, 004: 0x0100 absent for ≥ 195 µs); stop `IRQ :=
0x8FAA` (`8F AA ×16`) read back **0x8AAA** (`masks_readback=1
bit15_readback=1`; fourth stop-word validation: 0x8FAA ×3, 0x8EAA ×1);
CLEANUPCHK INTSR `0x00012000` → **one W1C 0x2000 → `0x00010000`, `sticky=0`**;
handler restored (`old_handler=null`); MASKCHK INTMR `0x000001FA`; AR_INFO
0x005B → 0x0043 (read back); FINAL under code 0 `00` / `9090`, INTSR
`0x00010000`; `restore=ok`, 58 transfers (2 whole-block, 7936 bytes), 0
timeouts / busy / errors, 182 lines, 0 dropped / truncated, `WRITES
irq_attempted=5 irq_completed=5 uncertain=0` (A1, A2, ACK, RE-ARM, STOP),
`w1c_total=2` (ISR 1, main 0, teardown 1; budget 3). **Status:** FACT
(hardware): a latched, undelivered HSP cause is cleared by one W1C after
the device was stopped, with nothing sticky.

## GBP-HW-057 — Raw content of the first AUDIO block (recorded, not interpreted)

**Observation:** 4096 bytes, CRC-32 `FEC5E4E7` (log BLOCK record ==
sidecar), 3969 zero bytes, 3 distinct values (`00`, `01`, `11`), first word
`0x01000000`. The 127 non-zero bytes: 123 at offset 0 of a 32-byte line
(`01` in 121 lines, `11` in lines 31 and 61; lines 3, 22, 33, 41, 74
entirely zero) and four isolated `01` at absolute offsets 0x08C, 0x49E,
0x8A8, 0xCBA (in-line offsets 12, 30, 8, 26). Log windows 0x000 / 0x540 /
0xAA0 / 0xFE0 == sidecar bytes. **Status:** FACT (hardware) for the bytes
of one block, no cartridge, first request after initialization.
**Not claimed:** PCM, PWM, silence, a sample rate, a word format
(U-GBP-012 stays HYPOTHESIS); whether the per-line byte 0 is payload or
the transfer's byte-0 phenomenon (U-GBP-021: one nearly constant non-zero
byte per 32-byte transfer unit resembles the register reads' extras — a
hypothesis for repeated captures, not a fact).

## GBP-HW-058 — Raw content of the first VIDEO block (recorded, not interpreted)

**Observation:** 3840 bytes, CRC-32 `FE45FF08`, 0 zero bytes, 2 distinct
values (`7F`, `FF`), first word **`0xFFFFFFFF`**, GBI frame-start predicate
`(w & 0x80800000) == 0x80800000` **true**. 960 four-byte groups: group 0
`FF FF FF FF`, 954 groups `7F 7F FF FF`, five groups `FF 7F FF FF` (groups
41, 165, 186, 426, 578; in-line offsets 4, 20, 8, 8, 8). Byte doubling `hh
hh ll ll` (GBP-HW-004 for the register reads) holds in 955 groups and
breaks in those five (byte 0 ≠ byte 1); windows 0x000 / 0x500 / 0xA00 /
0xEE0 == sidecar. **Status:** FACT (hardware) for the bytes of one block,
no cartridge. **Not claimed:** the image or its colors (U-GBP-011), the
line geometry (U-GBP-008: a DMA of 0xF00 completes whatever the block's
true size), the meaning of the five undoubled groups (content, transfer
artifact, or the byte-0 class of U-GBP-021).

## GBP-HW-059 — Byte 0 and offset-2 observations of GBP-AV-SERVICE-001

**Observation:** byte-0 extras — TEST `7F` (0x43 over 3C), `D3` (0x10 over
C3), `11` (0x11 over 00), none over FF, `01` over 00 at BASE/P0; CONTROL `93`
(0x03 over 90), `9F` (0x13 over 8C) in all fifteen 0x8C reads, `91` (0x01
over 90) at TDCTL, `01` over 00 at FINAL; IRQ `9B` (0x11 over 8A) in every
0x8AAE / 0x8AAA read, `01` over 00 in the five 0x0000 reads, `15` (0x11 over
04) in both 0x0400 reads, `17` (0x12 over 05) in the five 0x0500 reads, `81`
(0x01 over 80) at POSTACK, `91` (0x01 over 90) at FINAL. Disc and GBI agreed
in every read, `vote == byte 0x1F` everywhere; no decision used byte 0.
Offset ≡ 2 mod 4: `lo | (hi & 0x05)` held for every 0x8AAE / 0x8AAA /
0x0000 / 0x8000 / 0x9090 read except group 0 of A2PRE (`BB` for `AA`; that
read took 41 ticks / 11 polls instead of 34 / 9), for groups 1–7 of the
0x0400 / 0x0500 reads (group 0 `00` / `01` for `04` / `05`), and broke in
group 5 of POSTDRAIN (`04` for `05`). **Status:** FACT (hardware) for the
bytes (pinned by `tests/host/test_hw_fixture.py`); the extras are
run-dependent (none in 003B; 0x04/0x20/0x24 in 003A; 0x04/0x20/0x80/0x88 in
004; 0x01/0x03/0x10/0x11/0x12/0x13/0x43 here) — U-GBP-020/021/025 unchanged
in substance and non-blocking: byte 0 and offset 2 of a raw block never
decide.

## GBP-HW-060 — The block sidecar written on hardware: format 2 intact, identities whole, every CRC verified

**Observation:** `GBP-AV-SERVICE-001_avsvc-0001-blocks.bin`, 8204 bytes =
0x100 header + 0x1000 + 0xF00 + 12 footer; magic `OGBPBLK1`, version 2,
header size 0x100, flags 0xF (both blocks present and valid),
pending/drain 0x0500, lengths 0x1000 / 0xF00, indices 8 / 1, rc ok / ok,
wait 2475 / 2319, dt 2692 / 2485, tb_hz 40500000; identity fields
`GBP-AV-SERVICE-001` (18 characters, whole), `avsvc-0001`,
`gbp-av-service-probe`, `d3a6d23`, zero padded; header CRC-32 `6174E52D`,
AUDIO `FEC5E4E7`, VIDEO `FE45FF08`, footer `OGBPEND1` + total `18E966CF` —
all four recomputed on the host and equal; the log's BLOCK / BLOCKW
records equal the sidecar's summaries and windows; the log header names
the sidecar. **Status:** FACT (tooling on hardware): the SD write path
(log first, sidecar second) and the format-2 serializer worked on the
console; version 1 (truncating identities) never reached hardware.

## GBP-IRQ-010 — IRQ-register model after GBP-AV-SERVICE-001 (delta over GBP-IRQ-009)

| Element | Added by GBP-AV-SERVICE-001 (2026-09-16) | Status |
|---|---|---|
| Bit 10 (0x0400) | rose 105.289 ms after A2 (fourth run); pending at PRESVC under bit 15 = 0; **still 1 ≈ 93 µs after its block was read** (POSTDRAIN); cleared by the drained ACK `0x8500` (0 at +25.9 µs); **1 again 43.9 µs after the re-arm `IRQ := 0`, with the PI cause latched** | source, W1C **F**; "a drain alone clears the status" **rejected** for ≤ 93 µs (one run); post-re-arm request retained vs new **U** |
| Bit 8 (0x0100) | joined within 0.92 ms; still 1 at POSTDRAIN; cleared by the ACK; absent at REARMPOST (+43.9 µs after the re-arm); back by IRQSTOPPRE (≤ 301 µs after REARMPOST) | W1C **F**; re-set timing **U** (upper bounds only) |
| Bit 15 (0x8000) | 0 during the drain (PRESVC, POSTDRAIN); **1 from the ACK to the re-arm with both sources 0, PI clear, no cause for ≥ 203 µs**; 0 after `IRQ := 0` with a cause captured within 43.9 µs | level-written **F**; "holds / gates the request" **H** (consistent again, still not named) |
| PI bit 13 | not re-latched by two pending sources under bit 15 = 0 for ≥ 552 µs (drain included); not latched by bit 15 = 1 with sources 0 (≥ 203 µs); **latched within 43.9 µs of the re-arm with 0x0400 visible, the CPU masked**; cleared once by the teardown W1C, nothing sticky | latched, W1C **F**; capture after a re-arm **F** (one run); line nature **U** |
| Service cycle | cause → delivery → mask-first → one W1C → **drain AUDIO 0x1000 + VIDEO 0xF00 (one DMA each)** → ACK `read \| 0x8000` → **re-arm `IRQ := 0`** → next cause: the **first complete reference-style cycle** on hardware | one cycle **F**; repeated service **U** (never run) |
| Whole-block reads | one DMA of the full length from index 0x8 and 0x1, 66.5 / 61.4 µs, CSR 0x0804 before/after, content recorded raw | transfer **F**; block size / geometry unchanged (**C**); content **U** |
| Stop word | `read \| 0x8AAA` from 0x0500 with a latched PI cause → wrote 0x8FAA → read 0x8AAA; one W1C cleared the cause | layout / effect **F** (fourth value) |
| Phase 3 | delivery (003B/004) + service, re-arm, next cause (this run): the criterion of DEVLOG 2026-09-16 met | **COMPLETE 2026-09-16**; microscopic unknowns non-blocking |

## Static observations — the VIDEO path of the references, 2026-09-16 (GBP-VIDEO-001 design; `docs/research/VIDEO_PATH.md`)

Source: Ghidra decompilations of the Start-up Disc `main.dol` and GBI
`gbi-unpacked.dol` (private, `build/analysis/ghidra/`), Dolphin
`HSP_DeviceGBPlayer.cpp` (`external/dolphin` c185d27), and the physical
block of GBP-AV-SERVICE-001. "F (code)" = what the software does; nothing
below is a physical fact about the Game Boy Player.

## GBP-VID-002 — Block geometry in both references: 4 raster lines of 240 pixels × 4 bytes, line stride 960 bytes, 40 blocks of 4 lines per frame

**Observation:** Disc `FUN_8008EFB4` converts a block with an outer loop of
60 groups of 4 pixels (240 per line), an inner loop of 4 rows that advances
the source by 0x1E0 halfwords (960 bytes) per row, and writes 4 × 4 texels
(one GX tile, 32 bytes) per group — 0x780 bytes per block, 40 blocks per
0x12C00 frame; its consumer (`FUN_8008EDE8`) places block `i` at `i × 0x780`
and accepts `i < 0x28`. GBI (`FUN_8000BF30`) consumes the block as 240 groups
of 4 consecutive pixels into a linear 16-bit raster at `blk × 0x780` (480
bytes per line), completes a frame at `blk == 0x27`, wraps with `% 0x28`; its
renderer tiles 4 linear rows at a time. Dolphin fills 960 pixels of 4
scanlines in raster order. **Status:** F (code) for the references' model,
CORROBORATED for the hardware format (three independent models agree; a
physical block cannot show geometry until a frame is captured —
GBP-VIDEO-001). The constant 40 is explicit in both binaries (`0x27` /
`0x28`, ring of 40, queue of 41, 40-entry tables), i.e. 160 / 4 written
out, not a measured value.

## GBP-VID-003 — Pixel word: both references consume only bytes 1 and 3; 16-bit pixel = bit 15 flag + 5-5-5 color in GX RGB5A3 order (R high)

**Observation:** Disc: `pixel = (b3) | FILL | ((hw0 << 9) >> 1)` = byte 3 |
byte 1 << 8, FILL forced into every pixel, the frame drawn as
`GX_TF_RGB5A3` (format 5) 240×160 textures with no non-identity swap-table
call in the presenter; its embedded reference frame has bit 15 set in every
halfword (FILL = 0x8000, C) and shows the boot logo in the color R = 12, G =
0, B = 25 (of 31) under the RGB5A3 reading — the logo's indigo; under the
GBA-native order it would be crimson. GBI: the thread packs `b1 << 8 | b3`
per pixel, the renderer emits 4×4 RGB5A3 tiles with `| 0x80008000`, and the
PNG writer maps bits 14–10 → R, 9–5 → G, 4–0 → B. Bytes 0 and 2 of a pixel
word are read by neither program (the register reads: same classes ≡ 1 / ≡ 3
mod 4). Dolphin writes `b0 = b1 = hi`, `b2 = b3 = lo`; its color order comes
from mGBA's `M_RGB8_TO_RGB5` on mGBA's 32-bit buffer — GBA-native (R low) if
mGBA's default format applies, i.e. the opposite of the references (not
verified: the macro is outside the sparse checkout). **Status:** bytes 1/3
and the `hh hh ll ll` doubling: F (code) ×2, physical bytes consistent
(GBP-HW-058); R-high color order: CORROBORATED (two references + the
reference frame's color), FACT only after a known-color cartridge
(U-GBP-011, VIDEO-002); Dolphin's order: H, flagged divergence.

## GBP-VID-004 — Frame-start predicates, exact

**Observation:** GBI: `(u32 at offset 0 & 0x80800000) == 0x80800000` — bit 7
of byte 0 AND bit 7 of byte 1; on true the block index is reset to 0.
Disc: `FUN_8008A588(u16 at offset 0) = (hw >> 7) & 1` — bit 7 of byte 1
only; its synthetic first block sets that bit by `halfword |= 0x0080`
(earlier project notes said "byte 0": wrong). Dolphin sets pixel 0 `|=
0x8000` on the frame's first block, which after doubling sets bit 7 of
bytes 0 and 1. Open-GBP's `gbi_frame_start` is GBI's predicate exactly; the
physical first word `FF FF FF FF` satisfies both predicates (a mask test,
not an equality with 0x80800000). **Status:** F (code) ×2; physical
occurrence on one block F (hw); absence on the other blocks of a frame: U
until GBP-VIDEO-001.

## GBP-VID-005 — Order, wrap and drop policies

**Observation:** Disc: block `i` → lines `4i..4i+3`; index reset only by the
flag; after 40 blocks without a flag the extra blocks are consumed and
freed but not converted (dropped) until the next flag; the frame buffer
(five of them) advances after the 40th block; a block whose ring slot is
still owned by the consumer is not read at all (skipped); no repeat. GBI:
same placement; wraps `% 40` without a flag (keeps overwriting from the
top); one buffer, conversion in the thread before the next pass; a frame is
dropped when the render queue refuses it (triple buffer). **Status:** F
(code); the hardware's own behavior on a missed block: U.

## GBP-VID-006 — Both references embed the AGB idle screen; the physical block equals its first block in both

**Observation:** the Disc keeps a 240×160 RGB5A3 frame at `0x801B45A0`
(0x12C00 bytes, before its frame-buffer table): white everywhere except
lines 56–100 / columns 39–201 (the "GAME BOY" logotype and "Nintendo®",
one main color plus 42 anti-aliasing shades), compared block by block with
the converted stream when enabled (40 consecutive matches raise a flag).
GBI keeps two 40-entry tables of per-block checksums (`0x800B0E78`: content
in blocks 14–25 — the Disc frame's layout; `0x800B0F18`: content in blocks
12–19), every other entry equal to the checksum of a white block, entry 0
equal to a white block with the flag; on a match it injects key states
(boot-screen automation). Host checks 2026-09-16: the GBI-style checksum of
the physical VIDEO block is `0x7F0FFF10` = entry 0 of both tables; the
Disc-style conversion of the physical block (FILL 0x8000) equals the
reference frame's block 0 byte for byte. **Status:** F (code) for the
embedded data; CORROBORATED that the physical block is the first block of
the idle screen as both references model it (the five byte-0 deviations
are in bytes neither program reads). **Consequence:** GBP-VIDEO-001 has an
offline oracle without a cartridge — a captured frame can be checked block
by block against two independent references (the assets themselves stay
private; only the comparison results are documented).

## GBP-VID-007 — Dolphin's video model, divergences to keep in mind

**Observation:** video IRQ scheduled on the audio IRQ phase ("separately
timed video IRQs break the game"); blocks of 4 raster lines; flag on pixel
0; color order via mGBA's macro (see GBP-VID-003); 32-byte reads modelled
without byte-0 extras. **Status:** model data; never physical truth; the
color-order divergence is testable by a Dolphin screenshot of the Disc's
logo, not scheduled.

## GBP-HW-061 — Positional statistics of the two physical blocks (from GBP-HW-057/058)

**Observation:** VIDEO: 5 deviations from the uniform pattern, all `+0x80`,
all at offset ≡ 0 mod 4 (byte 0 of a pixel word: absolute 0x0A4, 0x294,
0x2E8, 0x6A8, 0x908; in-unit offsets 4, 20, 8, 8, 8 of their 32-byte
units), none at bytes 1–3; bytes ≡ 1 mod 4 are `7F` in 959 of 960 words (the
flagged pixel excepted), bytes ≡ 2 and ≡ 3 mod 4 are `FF` in all 960.
AUDIO: 127 non-zero bytes — 123 at ≡ 0 mod 32 (`01` ×121, `11` ×2; five
32-byte units without one), two at ≡ 0 mod 4 (0x08C, 0x8A8) and two at ≡ 2
mod 4 (0x49E, 0xCBA); period-match fractions 0.994–0.995 for periods that
are multiples of 32 and 0.938 otherwise, i.e. the only structure is the
32-byte unit. The same run's 32-byte register reads carried byte-0 extras
`0x01 / 0x03 / 0x10 / 0x11 / 0x12 / 0x13 / 0x43` and offset-2 deviations
(GBP-HW-059). **Status:** FACT (hardware) for the positions and values; the
classification — block data vs an artifact of the read path in the byte
positions the references discard — is **UNKNOWN** (U-GBP-029); the
positional coincidence with the register reads' extras is noted as
HYPOTHESIS; no byte is corrected; GBP-VIDEO-001 tests reproducibility.

### GBP-HW-062 — repeated drained service is stable over 209 cycles — FACT

GBP-VIDEO-001 (2026-09-16, `video-0001`, commit `6930dde`). One install of the
003B extended one-shot handler served **209 consecutive deliveries**: 209
unmasks, 209 handler entries, 209 ACKs (`pending | 0x8000`), 209 re-arms
(`IRQ := 0x0000`), 0 reentry, 0 missed entry, 0 unexpected source, 0 uncertain
write. Every cycle read INTSR bit 13 set at the ISR entry and clear after the
handler's single W1C. Restricted to this run and this sequence length.

### GBP-HW-063 — the W1C budget held for every cycle — FACT

Same run: ISR W1C 209 (exactly one per delivery), main-loop W1C **0**, teardown
W1C 1 — 210 total. No main-loop PI write occurred between a re-arm and the next
unmask in any of the 209 cycles.

### GBP-HW-064 — 88 VIDEO and 144 AUDIO whole-block DMAs, all successful — FACT

Same run: 88 VIDEO blocks of 0xF00 at `0x01100000` and 144 AUDIO blocks of
0x1000 at `0x01800000`, every one completed; 0 timeouts, 0 busy, 0 backend
errors. `bulk_transfers=232`, `bulk_bytes=927744` = 88 × 0xF00 + 144 × 0x1000.

### GBP-HW-065 — source distribution of this run — FACT (measurement, not a rate)

Same run, 209 pending snapshots: 121 × `0x0400` (AUDIO only), 65 × `0x0100`
(VIDEO only), 23 × `0x0500` (both). This is one run's distribution; nothing about
a universal AUDIO : VIDEO ratio follows from it.

### GBP-HW-066 — one physical frame-start interval of exactly 40 VIDEO blocks — FACT

Same run: both frame-start predicates (GBI's bit 7 of bytes 0 AND 1; the Disc's
bit 7 of byte 1) are true on blocks 0, 25 and 65 of the captured sequence and
**agree on all 88 blocks — 0 divergences**. The interval seq25 → seq65 contains
exactly **40** VIDEO blocks. The general "40 blocks per frame" model is
CORROBORATED (Disc constants + GBI constants + this interval); one interval does
not establish a period.

### GBP-HW-067 — frame timing of this run — FACT (measurement)

Same run, time base 40.5 MHz: seq25 → seq65 = 680 138 ticks = 16.794 ms =
**59.547 Hz**; within it, seq25 → seq64 = 464 059 ticks (11.458 ms) over 39
block gaps and seq64 → seq65 = 216 079 ticks (5.335 ms). Steady per-block gap
11 891 ticks (0.294 ms) median.

### GBP-HW-068 — a 22-cycle AUDIO-only gap closes the frame — FACT

Same run: between the VIDEO blocks seq64 (cycle 141) and seq65 (cycle 164) there
are exactly 22 consecutive cycles whose pending value is `0x0400`, with no VIDEO
source, spanning the 5.335 ms gap of GBP-HW-067. Reading that gap as the AGB's
vertical blanking is CORROBORATED by both references' frame structure, not
established by this run alone.

### GBP-HW-069 — the captured frame is semantically uniform — FACT

Same run: under the byte 1 / byte 3 picking both references perform, the 88
blocks carry exactly two payloads — 85 × (960 × `0x7FFF`) and 3 × (`0xFFFF` +
959 × `0x7FFF`), the latter exactly on the three frame starts. The complete
frame seq25..seq64 is 38 400 elements, uniform apart from the start marker.

### GBP-HW-070 — byte 0 varies without changing the payload — FACT

Same run: over 84 480 pixel words, byte 0 differs from byte 1 in **688** words,
always `ff`/`7f`; byte 2 never differs from byte 3 (0 cases). The exceptions
never fall on the first word of a 32-byte DMA line (0 of 10 560) and appear at
~0.9 % at each of the other seven positions. The byte 1 / byte 3 payload of the
first captured block is **byte-identical** to the GBP-AV-SERVICE-001 physical
block though the raw CRC-32s differ (`fe45ff08` vs `ef18fc8d`) and the exception
counts differ (5 vs 9); both yield GBI checksum `0x7F0FFF10`. Byte 0 variability
therefore does not alter what either reference reads. Its cause stays open
(U-GBP-029); nothing here identifies a DMA fault.

### GBP-HW-071 — the physical frame matches the references exactly where they are white — CORROBORATED

Same run, offline comparison with the private inputs, aligned on the complete
interval (seq25 = frame position 0): GBI table A matches 28/40 with the 12
mismatches **exactly at blocks 14..25**; table B 32/40 with the 8 mismatches
**exactly at blocks 12..19**; the Disc's embedded frame 28/40 with mismatches
**exactly at 14..25**. Those are precisely the blocks the static analysis says
carry the "GAME BOY / Nintendo" logotype. The physical per-block checksums are
exactly `0xFF0FFF0F` (39 blocks) and `0x7F0FFF10` (1 block) — table A entries 1
and 0, the all-white block without and with the frame flag. Conclusion: the AGB
was displaying a **blank white screen**, a device state different from the boot
logotype the references embed. This corroborates the block geometry, the byte
picking and the 40-block frame model; it does not indicate any fault.

### GBP-HW-072 — the final latched cause was closed by the teardown, never delivered — FACT

Same run: the capture stopped at `target_reached` with a 210th cause latched at
the PI. The admission point refused it, no further unmask occurred, and the
teardown closed it with its single W1C (`00012000 → 00010000`, not sticky) after
the stop word `IRQ := 0x8FAA` read back `0x8AAA`. Handler restored once, INTMR
bit 13 = 0, AR_INFO `005b → 0043`, `restore=ok`.

### GBP-VID-008 — the OGBPSEQ1 sidecar of a physical run is self-verifying — FACT

The GBP-VIDEO-001 sidecar (403 948 B, sha256 `ce5134ff…e229`) parses with the
documented layout, header CRC `593d4082` and total CRC `d38bf828` both
recomputed, all 12 reserved bytes zero, no trailing byte, and **every one of the
88 VIDEO blocks re-CRCed against its table entry**. The 135 AUDIO drains whose
payload was not preserved carry `raw_index = 0xFFFF` and `crc32 = 0`: absence of
a measurement, never a fabricated one.

### GBP-VID-009 — the AUDIO last-valid policy behaved as designed on hardware — FACT

Same run: of 144 successful AUDIO drains, exactly 9 payloads were preserved —
the first 8 (cycles 0, 1, 2, 3, 4, 6, 8, 10) and the last valid one (cycle 207).
The first eight carry 16–36 nonzero bytes of 4096; the last carries 2178. No
audio format is inferred.

### GBP-VID-010 — the Disc's embedded frame is a comparison oracle, never drawn — FACT (static)

Start-up Disc `main.dol`, traced 2026-09-16. `0x801B45A0` carries no data
reference; it appears as the arithmetic immediate `-0x7FE4BA60` in the video
service loop `FUN_8008EDE8`. That loop converts each live block into the frame
buffer (`FUN_8008EFB4`, the only writer of the frame buffer) and then, when a
gate byte is set, calls `FUN_8008F080(converted_block, 0x801B45A0 + blk*0x780,
blk)`. `FUN_8008F080` compares 960 halfwords — one block — and sets a "detected"
flag only after **40 consecutive blocks** match; any mismatch resets it. The
reference is never copied to a frame buffer and never rendered.

### GBP-VID-011 — the detection drives KEYPAD injection — FACT (static)

Same binary. `FUN_8008C26C` (session start) reads CONTROL (`base + 0x400000`
byte 0x1F), sets bit `0x08`, writes it back and arms the detector. `FUN_8008B1AC`
polls the flag for up to **24 000 invocations of a 5.000 ms periodic callback
(120.0 s)**; on the rising edge it calls
`FUN_8008C31C`, which drives bits `0xF0` of a 16-bit value in a 5-frames-on /
5-frames-off cycle; that value reaches `FUN_80089E40`, which writes a 32-byte
block to **`base + 0xC00000` — KEYPAD (index 0xC)**. So the Disc recognises one
AGB screen in order to press buttons past it. No KEYPAD write is needed to
*reach* the screen; KEYPAD is used only to dismiss it.

### GBP-VID-012 — GBI's two tables are 40-entry screen signatures with one reader — FACT (static)

`gbi-unpacked.dol`. Table A (`0x800B0E78`) is read only at `0x8000CE68` and
table B (`0x800B0F18`) only at `0x8000CDA0`, both inside the video service thread
`FUN_8000BF30`. Each is a 40-iteration word-by-word comparison against the run's
per-block checksums in which **all 40 must match**; any mismatch exits
immediately. The selection is by configuration, not content: a byte at `r13+885`
selects table A, otherwise a word at `r13+896` equal to `-2` or `-1` selects
table B.

### GBP-VID-013 — the Disc's embedded frame and GBI's table A are the same screen — FACT (derived)

Computing GBI's own per-block checksum over the Disc's embedded frame, with bit
15 cleared to match GBI's service-thread convention, reproduces **39 of the 40
entries of table A**; the only difference is block 0, where table A stores the
all-white-with-frame-flag value and the Disc's copy stores it without the flag
(the Disc takes the frame start from the live stream instead). Against table B
the same computation matches 25 of 40. Structurally the Disc's frame is uniform
outside blocks 14..25 and carries content inside them, table A's non-uniform
entries are exactly blocks 14..25, and table B's are exactly blocks 12..19: table
A and the Disc frame describe one screen, table B a second, different one. Which
AGB states they correspond to is not decided by the code read so far
(U-GBP-031). No reference pixel or table value is stored in this repository.

### GBP-HW-073 — GBP-VIDEO-001 observed 39.2 ms starting 107 ms after the AGB was started — FACT

Recomputed from the physical log: the CONTROL transform `0x90 → 0x8C` at
t = 1 849 601 875, A2 at +0.645 ms, the first HSP cause 105.285 ms after A2, the
first unmask (t0) at t = 1 853 935 409 and the last observation at
t = 1 855 524 244. So the whole 209-cycle capture spanned **1 588 835 ticks =
39.230 ms ≈ 2.34 frames**, beginning **107.001 ms** after the AGB was started.
The uniform payload of that run is therefore a statement about a very short,
very early window, not about the session as a whole.

### GBP-VID-014 — the Disc's detector window is 120 s, not a frame count — FACT (static)

Start-up Disc `main.dol`. The window is 24 000 iterations of the counter at
`r13-0x7014`, incremented once per invocation of `FUN_8008B1AC` while the session
state is 2 and no completion callback is pending. `FUN_8008B1AC` is not a
per-frame callback: `FUN_8008A930` registers it through `FUN_80067F24` — which
stores its sixth argument as a period at `struct+0x1C` and takes its seventh as
the callback — with a period computed from the bus clock at `0x800000F8` as
`((bus >> 2) / 125000) * 5000 >> 3`. With the measured bus clock of 162 MHz that
is **202 500 ticks of the 40.5 MHz time base = 5.000 ms exactly**, so the window
is nominally **24 000 x 5 ms = 120.000 s**. `FUN_80067C4C`, the scheduler insert,
detects a deadline already past, divides the lateness by the period and advances
the next fire time by (lateness / period) + 1 periods: missed periods are
**dropped, never replayed**. Reaching 24 000 therefore takes **at least** 120 s
and longer whenever an invocation is skipped, so 120 s is a LOWER bound and the
value 24 000 establishes no upper wall-clock bound. Two earlier notes in this
repository are withdrawn: one read the counter as per-frame and gave ~400 s, the
other called 120 s an upper bound.

---

## GBP-VIDEO-002 — first long-run physical observation (2026-09-16)

Source for every entry below: the single physical run of `GBP-VIDEO-002`,
build `vstate-0001`, commit `e8f3a69e3ba190daf5db6954015a6fdae9aef6d7`, DOL
SHA-256 `c73d49fa…19b9`, GameCube + Game Boy Player, **no Game Pak**. Raw
inputs `logs/GBP-VIDEO-002_vstate-0001.log` (81 380 B, SHA-256 `4f30d1cd…6cfc`)
and `logs/GBP-VIDEO-002_vstate-0001-vstate.bin` (2 432 396 B, SHA-256
`6406f244…2639`), preserved in `captures/local/` and derived into
`captures/fixtures/hw-gamecube-gbp-2026-09-16-vstate-0001*`. Every number was
recomputed from those bytes, not copied from the run's own summary.

### GBP-HW-074 — 51 751 consecutive admitted service cycles on one installed handler — FACT

The repeated drained service ran **51 751 cycles in 8.187 s** through a single
installed 003B one-shot handler: 51 751 unmasks, 51 751 ISR entries, **0
reentry**, 51 750 ACKs and 51 750 re-arms completed, **0 main-loop W1C**, 0
teardown W1C, 0 DMA timeouts, 0 busy refusals, 0 uncertain writes, 0 counter
overflows, 208 298 transfers and 52 981 whole-block reads totalling
212 014 848 bytes. The 51 751st cycle is the one that aborted (GBP-HW-083);
every cycle before it completed in full. GBP-VIDEO-001 had shown 209 cycles;
this extends the observation by two orders of magnitude.

### GBP-HW-075 — the source pattern over 51 750 serviced causes — FACT

Derived from the counters: **AUDIO-only 32 237, VIDEO-only 18 282, both
1 231**, giving 33 468 AUDIO and 19 513 VIDEO drains. AUDIO outnumbers VIDEO
**1.715 : 1**. Only 2.4 % of causes carried both sources. This is a
measurement of this run, not a device property.

### GBP-HW-076 — 489 frame intervals, 477 of exactly 40 VIDEO blocks — FACT

Segmentation on the Start-up Disc predicate produced **490 boundaries** over
19 513 VIDEO blocks and 489 intervals: **477 of exactly 40 blocks**, one of 30,
four of 34, seven of 38. No boundary was ever synthesised and no interval was
corrected. This raises "40 blocks per frame" from a reference constant to a
directly and repeatedly observed physical interval.

### GBP-HW-077 — both frame-start predicates agreed on all 19 513 blocks — FACT

GBI's predicate (bit 7 of bytes 0 AND 1) and the Disc's (bit 7 of byte 1) each
gave **490 boundaries** and **zero disagreements** over 19 513 physical blocks.
Together with GBP-VIDEO-001's 88 blocks that is 19 601 blocks with no observed
divergence.

### GBP-HW-078 — frame cadence 59.727 Hz in this run — FACT

Over **465 consecutive pairs of complete 40-block frames**: median 678 084
ticks = **16.7428 ms = 59.727 Hz**; min 16.6743 ms, max 16.8116 ms, p5 16.6788,
p95 16.8069. GBP-VIDEO-001's single interval gave 59.547 Hz. The two runs differ
by 0.30 %. Reported as two measurements; no universal frequency is claimed.

### GBP-HW-079 — the AGB reaches a structured screen without a Game Pak — FACT

The stream began uniform (frames 1..29, 0.480 s), changed structurally at
**frame 30, 0.5014 s after capture start**, animated through 156 distinct
signature vectors, and settled. Seven states were stable by the probe's own
threshold of three identical consecutive complete frames:

| frames | n | start | duration | content blocks |
|---|---|---|---|---|
| 1..29 | 29 | 0.016 s | 0.480 s | none (uniform) |
| 187..189 | 3 | 3.130 s | 0.045 s | 12..19 |
| 196..199 | 4 | 3.281 s | 0.062 s | 12..19 |
| 200..204 | 5 | 3.348 s | 0.078 s | 12..19 |
| 205..209 | 5 | 3.431 s | 0.078 s | 12..19 |
| 210..214 | 5 | 3.515 s | 0.078 s | 12..19 |
| 215..488 | **274** | 3.599 s | **4.582 s** | 12..19 |

This answers the observational half of U-GBP-031: a structured state does reach
the VIDEO stream of a session without a cartridge, about half a second after the
AGB is started.

### GBP-HW-080 — the settled state matches GBI reference table B in all forty blocks — FACT

The vector held for frames 215..488 is, block for block,
`7f0fff10`, `ff0fff0f` ×11, then `d7447c83 86c6c4c5 cc9a6539 fe7375d1 45e5ce86
a11718b6 56c6f385 f703c183` at blocks 12..19, then `ff0fff0f` ×20. Compared at
analysis time against the private inputs (read from `input/extracted/`, never
stored here):

| reference | exact 40/40 matches | best partial |
|---|---|---|
| **GBI table B** | **274 frames, 215..488, 4.5823 s, contiguous** | 40/40 |
| GBI table A | none | 28/40 |
| Start-up Disc embedded frame | none | 27/40 |

This is the first physical observation of the Game Boy Player producing a frame
that a reference program's recognition machinery would accept. It also confirms
from hardware the static finding that table B's content occupies blocks 12..19
while table A and the Disc's frame occupy 14..25.

### GBP-HW-081 — the physical geometry, reconstructed and legible — FACT

Reading the preserved raw frames exactly as both references do — 0xF00 bytes as
4 raster lines of 240 pixels of 4 bytes, pixel = **byte 1 : byte 3**, bit 15 the
frame marker, 40 blocks per frame — produces a **legible, animated "GAME BOY"
logotype at 240 × 160**. The marker was set on block 0 and on no other block of
every reconstructed frame. A wrong line count, pixel count, block count, block
order or byte pick could not produce coherent readable text. This promotes the
geometry from the references' constants to a physical fact: 0xF00 = 960 semantic
pixels, 4 lines per block, 240 pixels per line, 40 blocks and 160 lines per
frame, blocks in ascending order from the frame marker.

### GBP-HW-082 — the signature cost on real hardware — FACT

19 513 samples on the 40.5 MHz time base: **min 777 ticks (19.185 µs)**, max 868
ticks (21.432 µs), mean 778 ticks (19.212 µs). The histogram reports median and
p95 as the upper bound of bucket 241 (ticks 760..823), i.e. **≤ 20.321 µs with a
64-tick, 1.58 µs resolution — an approximation, not an exact quantile**; the
sampled per-cycle values (min 777, median 778, max 808) place the true median at
about 19.2 µs. The cost is **0.121 % of a frame period** and 4.85 % of one
inter-block gap. In the sampled cycles ACK→REARM measured 20.395 µs median with
a VIDEO block and 0.272 µs without: the signature accounts for the entire
difference and runs only where a block arrived. The design's pre-run estimate was
"about 20 µs".

### GBP-HW-083 — one semantic disagreement in the IRQ register after 51 750 clean reads — FACT

At cycle 51 750 the ISR fired normally (latency 34 ticks, the run's usual value;
INTSR bit 13 set at entry, cleared by the handler's single W1C), the 32-byte read
of the IRQ window returned `rc=ok`, and the two semantic interpretations of that
block disagreed. The probe treats that as fatal: it stopped before any ACK or
re-arm. The two readings are
`gbp_irq_value_disc` = bytes 0x1D and 0x1F, and `gbp_irq_value_gbi` = a majority
vote over the eight replicas at offsets ≡1 and ≡3 mod 4. **The offending 32
bytes, the two conflicting values and the pending source were not recorded**
(U-GBP-032).

### GBP-HW-084 — replica deviations in the IRQ window have always landed on discarded bytes — FACT

Across **353 IRQ-window reads whose bytes are recorded in every physical log to
date** (003A, 003B, 004, AVSVC, VIDEO-001, VIDEO-002) there are **220 byte-level
deviations** from the majority replica group, and **every one falls on an offset
≡ 0 or ≡ 2 mod 4** — bytes that neither semantic reading consumes. Zero landed on
a consumed byte. Two such absorbed deviations appear in this run's own log,
including one at the teardown's IRQSTOPPRE read. The disagreement of GBP-HW-083
requires a deviation on a consumed byte, which no logged read has ever shown;
but only 29 of this run's 51 751 reads had their bytes recorded, so the logged
sample cannot establish a rate.

### GBP-HW-085 — the episode raw store filled and monitoring continued — FACT

Nine episodes were opened; four received descriptors and raw frames, and from the
fifth on `episode_store_full` was set and `episodes_not_preserved` counted five.
All nine were still classified (seven stable, two capped at
EPISODE_MAX_FRAMES = 60). No earlier episode was overwritten: the four
descriptors hold 15 raw frames and **all 600 preserved blocks reproduce their
stored signatures exactly**. The run did not stop for this. The design's policy B
behaved as specified on hardware.

### GBP-HW-086 — clean teardown after a service failure — FACT

After the abort: CONTROL restored 0x8C → 0x90 with a confirming readback; the IRQ
window still showed `0x0500` pending (the cause that was never acknowledged); the
stop word `0x0500 | 0x8AAA = 0x8FAA` was written and read back as `0x8AAA` with
its masks and bit 15 set; CLEANUPCHK found INTSR bit 13 already clear so **no
teardown W1C was needed**; the handler was restored once; INTMR bit 13 read 0;
AR_INFO restored to 0x0043. The FINAL state is byte-identical to the one
GBP-VIDEO-001 and GBP-AV-SERVICE-001 reached: `arinfo=0043 intsr=00010000
intmr=000001fa control=00 irq=9090`.

### GBP-HW-087 — the OGBPSEQ1 v2 sidecar survived a real multi-megabyte streamed save — FACT

2 432 396 bytes written after the teardown in 64 KiB chunks. Recomputed on
analysis: header CRC `947083c4` and total CRC `9bef714b` both verify, every
section is contiguous and monotonic with zero overlap (489 frames × 192, 209
events × 64, 4 episodes × 512, 81 cycles × 128, 15 × 40 × 0xF00 of raw, 2 ×
0x1000 of AUDIO), the strict parser accepts it, and the log recorded 621 of 1024
ring lines with **0 dropped and 0 truncated**.

## GBP-VIDEO-002 vstate-0002 — the semantic disagreement, caught with its bytes (2026-09-17)

Second physical run of GBP-VIDEO-002, build `vstate-0002`, commit `8cbb28d`, DOL
SHA-256 `8661e914…b91b`. Log `fb127d79…de2a` (40 013 B), sidecar `f2ed596e…8c91`
(12 588 B). The run ended the same way the first one did — `READ_semantic_disagree`
— but this time the read that caused it was preserved. Everything below is
recomputed from those two files, not taken from the run's own summary.

### GBP-HW-088 — the OGBPSEQ1 v3 sidecar written and validated on hardware — FACT

12 588 bytes streamed after the teardown. Recomputed on analysis: header CRC
`bd2a5f27` and total CRC `08514baa` both verify; magic `OGBPSEQ1`, version 3,
header 0x200; the sections are exactly contiguous with zero overlap (5 frames ×
192 at 512, 10 events × 64 at 1472, 0 episodes, 17 cycles × 128 at 2112, **one
96-byte diagnostic at 0x10C0**, 0 raw VIDEO, 2 × 0x1000 AUDIO at 4384, footer
`OGBPEND1` at 12 576); `off_diag` = 0x10C0, `diag_count` = 1, `diag_rec_size` =
96, and the header bytes 0x1EA..0x1FB are zero. The strict parser accepts it, and
the log recorded 308 of 1024 ring lines with **0 dropped and 0 truncated**. This
is the first physical file of the family to carry a diagnostic section.

### GBP-HW-089 — the 32 bytes of a semantic disagreement, preserved — FACT

At cycle 517 the IRQ-window read returned, verbatim:

```text
01 01 01 00  01 01 01 00  01 01 01 00  01 01 01 00
01 01 01 00  01 01 01 00  01 01 01 00  05 05 05 00
```

The same 32 bytes appear in the sidecar's diagnostic record and in the log's
`READDISAGREE` line, written through two independent paths, and they agree byte
for byte. Context recorded with them: read site LEAN/READ, attempts 1, frame 5,
block-in-frame 5, `t = 0x794981cf07f9e7`, latency 35 ticks, transfer 34 ticks /
9 polls, DSPCR `0804` before and after, INTSR `0x00012000` at ISR entry and
`0x00010000` after the handler's single W1C, INTMR `0x000021FA` at entry, CONTROL
`0x8C`. This closes the recording half of U-GBP-032.

### GBP-HW-090 — seven replicas held one value and the eighth held another, coherently — FACT

Decomposing that window into its eight 4-byte groups: groups 0..6 are
`01 01 01 00` and group 7 is `05 05 05 00`. Under the reading both references
use — high byte at offset `4k+1`, low byte at `4k+3` — the eight semantic values
are `0100 ×7` then `0500`. The eighth group is **not malformed**: its first three
bytes moved together exactly as the first three of every other group do, and its
fourth byte is `00` like all the others. A one-bit flip, a torn byte or a garbled
DMA line would be expected to break that intra-group agreement; this did not.

### GBP-HW-091 — the two references' readings of ONE read: 0x0500 and 0x0100 — FACT

From those bytes, recomputed offline: the Start-up Disc's reading
`(raw[0x1D] << 8) | raw[0x1F]` = **0x0500**; GBI's bitwise majority over the eight
replicas = **0x0100** (the high byte's bit 2 is set in 1 of 8 replicas and is
voted down 7 : 1; the low byte is `00` in all eight). Both values were also
computed by the runtime at the moment of the read and persisted in the record,
and the recomputation reproduces both exactly. This is the first physical
demonstration that the two mature references can derive different values from a
single 32-byte read.

### GBP-HW-092 — the difference is exactly the AUDIO source bit — FACT

`0x0500 ^ 0x0100 = 0x0400`. With the project's established source map (0x0100 →
VIDEO read, 0x0400 → AUDIO read; GBP-HW-024/065), the majority says VIDEO-only
and the last replica says VIDEO + AUDIO. The disagreement is not an arbitrary bit:
it is one source present in one reading and absent in the other. **No physical
cause is claimed here** — this records what the two readings were, not why.

### GBP-HW-093 — the discarded bytes move WITHIN a single block, in this same run — FACT

Of the 15 IRQ windows this run logged in full, the ones reading `0x0500` show the
byte at offset `4k+2` — which neither reference consumes — taking different values
in different groups of the *same* 32-byte read: `04 05 05 05 05 04 00 05`,
`04 05 05 05 00 05 05 05`, `04 04 05 05 00 05 05 05`, `05 05 04 05 05 05 05 05`
and `04 05 05 04 05 05 00 05` are five such blocks, while the consumed bytes stay
constant across all eight groups and both readings agree. The windows reading
`0x8AAE`, `0x8AAA`, `0x8000`, `0x8100`, `0x0400`, `0x0000` and `0x9090` are
uniform except for the known byte-0 extra (U-GBP-029). So a single block is
**already known not to be uniform** in this run, on bytes that are discarded — and
the fatal read is the first time the non-uniformity reached a consumed byte.

### GBP-HW-094 — the event recurs across independent runs, at very different times — FACT

Two runs, two physically distinct sessions, same class of event: vstate-0001 at
cycle 51 750 after 8.186 s of capture, vstate-0002 at cycle 517 after 0.0842 s.
The second run's abort came long before the structured screen that dominated the
first (first change at 0.5014 s), so the event is not tied to the logotype
content. **Two events support recurrence and nothing else**: no rate, no
distribution and no dependence on anything is claimed from n = 2.

### GBP-HW-095 — no transport anomaly at the fatal read — FACT

The read reported `rc=ok`, 34 ticks, 9 polls, DSPCR `0804` before and after. Every
one of the 61 fully logged block reads of this run has the identical signature
(34 ticks, 9 polls, `0804`); the 17 register writes have 30–31 ticks and 7–8
polls. The ISR fired once (INTSR bit 13 set at entry, cleared by its single W1C,
INTMR bit 13 set at entry), latency 35 ticks, 0 reentry. Run totals: 2 149
transfers, **0 timeouts, 0 busy, 0 uncertain writes, 0 counter overflows**, and
`transport_ok`. At the transport level the fatal read is indistinguishable from
the 517 that preceded it.

### GBP-HW-096 — a source present after an ACK that did not write it, and a next cause 74 ticks after the re-arm — FACT (measurement) / CORROBORATED (the model)

**FACT — what was measured**, from the 64-bit clocks of this run's cycle records
and from the verify cycles' own reads:

* verify cycle 3 acknowledged `0x0500` (ACK `0x8500`) and the POSTACK read
  returned `0x8100`: a source **present in the register after** an acknowledge,
  with bit 15 set and CONTROL 0x8C. The run continued normally;
* when a cycle acknowledged only AUDIO (`pending 0x0400`, ACK `0x8400`), the next
  cause was observed **74 ticks = 1.83 µs** after the re-arm (cycles 5 and 7), and
  it carried `0x0100` — VIDEO, which was not in the ACK value;
* when a cycle acknowledged both sources, the next cause took 26–28 µs (cycles
  0–3) or 215 µs (cycle 4); when it acknowledged only VIDEO, 71 µs;
* gaps between causes of the same source, as observed in that window: AUDIO
  9 885–11 303 ticks (244.1–279.1 µs), VIDEO 10 202–11 896 ticks (251.9–293.7 µs).

So the 74 ticks are **134× to 153× shorter than any previously observed
AUDIO-source gap in this run** — about 2.1 orders of magnitude. That is a
comparison against what this run happened to observe. **No physical lower bound on
how soon a genuinely new source may arrive has been established**, here or
anywhere in this repository, and none is claimed.

**CORROBORATED — the model these measurements support**, together with GBP-HW-028
(writing 1 to a source bit that reads 1 clears it): the ACK clears exactly the
source bits it writes as 1, the others stay pending, and the re-arm
`IRQ := 0x0000` releases them. The POSTACK observation is direct; the 74-tick
latency is consistent with it and with nothing else that has been observed, but a
new assertion arriving in that interval has not been excluded by any measurement.

**UNKNOWN, and not covered here:** the effect of an ACK writing 1 to a source bit
that reads 0. GBP-HW-028 established only the 1-on-1 case.

### GBP-HW-097 — clean teardown after the diagnostic abort — FACT

CONTROL restored 0x8C → 0x90 with a confirming readback (vote and byte 0x1F both
0x90); the IRQ window read `0x0500` and the stop word `0x0500 | 0x8AAA = 0x8FAA`
was written and read back as `0x8AAA` with its masks and bit 15 set; CLEANUPCHK
found INTSR bit 13 already clear so **no teardown W1C was needed**; the handler
was restored once (old handler null); INTMR bit 13 read 0 against an original 0;
AR_INFO restored to 0x0043 with a confirming readback. FINAL state
`arinfo=0043 intsr=00010000 intmr=000001fa control=00 irq=9090`, byte-identical
to the one GBP-VIDEO-001, GBP-AV-SERVICE-001 and vstate-0001 reached. The
teardown took 15 145 ticks = 0.37 ms and began 51 ticks after the stop. A service
failure caused by the diagnostic abort left the device in the same state a
successful run does.

## GBP-VIDEO-002-R3 vstate-0003 — the policy survived, the bookkeeping did not (2026-09-17)

Third physical run of GBP-VIDEO-002, build `vstate-0003`, commit `8c25df2`, DOL
SHA-256 `baea30f5…b486`. Log `9f81f19f…2e57` (86 378 B), sidecar `0a45d487…e6bc`
(4 359 724 B). The first run of this test to reach its scientific target, and the
first to carry a **known producer defect**. Every value below is recomputed from
those two files; where a field of the sidecar is contaminated it is named as such
and is not used.

### GBP-HW-098 — the OGBPSEQ1 v4 sidecar, written and structurally validated on hardware — FACT

4 359 724 bytes streamed after the teardown. Recomputed on analysis: header CRC
`888afeb1` and total CRC `df719b16` both verify; magic `OGBPSEQ1`, version 4,
header 0x200; `diag_count` 23, `diag_rec_size` 160, `semantic_size` 1024,
`diag_flags` 0, header bytes 0x1F4..0x1FB zero. Sections exactly contiguous with
zero overlap and zero orphan bytes: header `0x000000`, frames `0x000200`
(10 503 × 192), events `0x1EC740` (210 × 64), episodes `0x1EFBC0` (4 × 512),
cycles `0x1F03C0` (80 × 128), **semantic block** `0x1F2BC0` (1 024),
**diagnostics** `0x1F2FC0` (23 × 160), raw VIDEO `0x1F3E20` (2 304 000), raw AUDIO
`0x426620` (8 192), footer `OGBPEND1` at `0x428620`, ending exactly at the file
size. The log recorded 657 of 1 024 ring lines with **0 dropped and 0 truncated**.
**The format is sound**: the defect recorded in GBP-HW-104 is producer
attribution, not storage, layout or CRC.

### GBP-HW-099 — the scientific target was reached, with the service never interrupted — FACT

1 114 007 admitted cycles over **175.848 s**, of which **120.009 s** of valid
post-baseline observation against a 120 s target; `stop=nominal_negative`,
`status=ok_structured_change_observed`, SERVICE ok, RESTORE ok, `transport_ok=1`,
`errors=0`. 1 114 007 unmasks, deliveries, ISR entries, ACKs and re-arms — the four
counts are equal — with 1 114 003 lean cycles and 4 verify. 420 073 VIDEO and
720 210 AUDIO whole-block drains (1 140 283 bulk transfers, 268 093 184 bytes,
4 482 370 transfers total). **0 reentry, 0 timeouts, 0 busy, 0 uncertain writes,
0 main-loop W1C, 1 teardown W1C, 0 counter overflows.** Frame capture: 10 503
frames, 10 491 complete, 12 incomplete, 24 resync, 10 476 counted, baseline valid
at 0.077 s; structured change **observed**, 9 episodes, 7 stable, 2 unstable.

### GBP-HW-100 — twenty-three semantic disagreements, all survived — FACT

23 disagreements in the run, **all** classified `SOURCE_SERVICED`, 0
`SOURCE_OTHER`, 0 `NON_SOURCE`; 23 with a Disc-extra source, 0 with a
majority-extra source, 0 in both directions; 23 preserved, 0 not preserved, the
store never capped. Recomputed **directly from each record's own 32 bytes**,
without trusting any stored value: `Disc = 0x0500`, `GBI majority = 0x0100`,
`delta = 0x0400`, `disc_extra = 0x0400` (AUDIO), `majority_extra = 0x0000`,
class `SOURCE_SERVICED` — in 23 of 23. The stored copies of those derived fields
agree with the recomputation in all 23.

**Frequency, descriptive only.** In this run: 23 events in 1 114 007 deliveries
(≈ 1 per 48 435) and 23 in 175.848 s (≈ 1 per 7.65 s). These are two ratios of
this one run, **not a rate**: nothing here models an arrival process, a
probability per cycle or a per-second expectation, and no such model is implied by
their being computable. They are also **not comparable** with the denominators of
`vstate-0001` (51 751 cycles) or `vstate-0002` (518 cycles): those runs **stopped
at their first event**, so their denominators are the time to the first
disagreement, not an exposure over which further events could have been counted.

### GBP-HW-101 — the non-uniformity is a contiguous suffix, in every event — FACT

Decomposing each window into its eight replicas, the `0x0500` values always form a
**contiguous suffix at the end of the window**:

```text
21 records   0100 0100 0100 0100 0100 0100 0100 0500     suffix length 1
 1 record    0100 0100 0100 0100 0100 0100 0500 0500     suffix 2, cycle 839272
 1 record    0100 0100 0100 0100 0100 0500 0500 0500     suffix 3, cycle 1015782
```

Never scattered, never a prefix, never interleaved. **CORROBORATED:** the
non-uniformity is ordered rather than randomly distributed across replicas.
**UNKNOWN and not claimed here:** that the suffix is "the newer value", the real
temporal order, the replica update order, the order the DMA reads them, whether
the source changed during the transfer, and the mechanism inside GBS-DOL
(U-GBP-033).

### GBP-HW-102 — the omitted AUDIO source was present in the next ordinary read, 23 of 23 — FACT

Every record carries `next_pending_gbi = next_pending_disc = 0x0400` and
`followup_state = source_present_next`; derived per bit, `present = 0x0400` and
`absent = 0x0000` in all 23. These fields are trustworthy under this producer
because they are written once, through the follow-up handle, which is cleared in
the same act (GBP-HW-105). **No next cause of any of the 23 events contained
VIDEO `0x0100`.**

### GBP-HW-103 — read-to-next-cause, measured on the two clocks that are trustworthy — FACT

Using only the diagnostic's own `t` and `t_next_cause`: **3 492 to 4 310 ticks,
86.22 to 106.42 µs**. The per-record AUDIO gap snapshot taken before each event is
5 858 ticks for the first record and 5 480 for the rest, so in **23 of 23** the
read-to-next-cause interval was shorter than the shortest AUDIO cause-to-cause gap
observed up to that point of the run. The re-arm necessarily happens after the
read, so the true re-arm-to-next-cause is shorter still — **but the persisted
`t_rearm` is contaminated (GBP-HW-104) and is not used here**. This is a
description of two measured clocks; it is **not** evidence that the source
observed afterwards is the same assertion.

### GBP-HW-104 — the diagnostic's current-cycle fields do not belong to the cycle that opened the record — FACT (defect)

Measured over the 23 records of this file:

```text
t_ack  > t_next_cause                                23/23   (by seconds, not microseconds)
t_rearm > t_next_cause                               23/23
(authoritative & SRC_MASK) != (gbi & SRC_MASK)       22/23
ack_value != authoritative | 0x8000                   0/23
service_selected != authoritative & AV_MASK           0/23
ACK_WRITTEN or REARM_WRITTEN missing                  0/23
```

Record 0 is typical: the read is at `t = 0x7949e3aaf935bc`, its next cause at
`0x7949e3aaf94692` (4 310 ticks later), and the stored `t_ack` is
`0x7949e3d695702e` — **18.066 s after its own next cause**, which is impossible for
one transaction. The persisted `t_ack` of record *i* falls **118 to 170 µs before
the read of disagreement *i+1***, and for the last record 96.1 µs before the run's
stop: the signature of a record that keeps absorbing later cycles. The stored
values are internally coherent with each other (`ack == auth | 0x8000` in 23/23),
which is precisely why internal consistency cannot be used as evidence of correct
attribution. 22 of 23 carry `auth = 0x0400`; the one that carries `0x0100`
(cycle 1 098 203) matches by coincidence because the overwriting cycle happened to
be VIDEO-only.

### GBP-HW-105 — which fields of this file are trustworthy — FACT (from the committed source)

```text
TRUSTED, written once at open:      t, cycle, valid, disc_value, gbi_value, read_kind,
                                    attempts, raw[32], intsr_entry, intsr_after_w1c,
                                    intmr_entry, latency_ticks, xfer_ticks, xfer_polls,
                                    dma_status, dma_status_before, control_exp,
                                    frame_index, block_in_frame, delta, disc_extra_sources,
                                    majority_extra_sources, classification,
                                    gap_min_before_ticks, gap_count_before
TRUSTED, written once through the follow-up handle, which is cleared in the same act:
                                    t_next_cause, next_pending_gbi, next_pending_disc,
                                    followup_state, followup_reason, record_flags bit 0
NOT RELIABLE for current-cycle attribution:
                                    authoritative_value, service_selected, ack_value,
                                    t_ack, t_rearm
POTENTIALLY CONTAMINATED under the same defect, never exercised in this run:
                                    payload_source/crc32/first_word and record_flags
                                    bits 1..5 (payload, quarantine, deferred, incomplete)
```

The split follows from the committed code, not from the data: the first group has
exactly one write site, in `gbp_vstate_diag_open()`; the second has exactly one, in
`gbp_vstate_diag_followup()`, which clears `diag_wait`; the third is written by
setters that address `diags[diags_n - 1]` and run on every service cycle.

### GBP-HW-106 — the hardware service itself — CORROBORATED (strong), not FACT

The evidence that the runtime really serviced VIDEO and acknowledged `0x8100` in
each of the 23 disagreement cycles, rather than the `0x8400` its contaminated
record claims:

* the next cause of every one of the 23 events is `0x0400` in **both** readings and
  contains no VIDEO bit. Had the cycle acknowledged only AUDIO, the VIDEO bit would
  not have been written as 1, would not have been cleared (GBP-HW-028) and would
  have appeared in that next cause;
* the follow-up is filled by the immediately following read, 86–106 µs later, so no
  intervening cycle could have cleared it;
* in the committed source the service and the ACK use a cycle-local value derived
  from the majority, and the defective setters write only the RAM record — they
  cannot change what was sent to the device;
* the run continued for 1.1 M deliveries with 0 errors and reached its target.

**Why it is not FACT:** none of the 23 disagreement cycles appears in the 80
sampled cycle records (they are the first 8, last 8, anomalies and episode
cycles), so no independent record of the acknowledge word exists for them. The
exact ACK value was not observed twice, and this project does not promote an
inference to FACT.

### GBP-HW-107 — clean teardown after a successful long run — FACT

CONTROL restored 0x8C → 0x90 with a confirming readback; the stop word written and
read back with its masks and bit 15; PI cleanup **performed** this time
(`intsr_before=00012000 → intsr_after=00010000`, sticky 0, ok 1) because a next
cause was latched at the end; the handler restored once; INTMR bit 13 read 0;
AR_INFO restored to 0x0043 with a confirming readback. FINAL state
`arinfo=0043 intsr=00010000 intmr=000001fa control=00 irq=9090`, byte-identical to
the one GBP-VIDEO-001, GBP-AV-SERVICE-001, vstate-0001 and vstate-0002 reached.
Teardown variant `S5_target`, `next_cause_at_end=1`.

### GBP-HW-108 — the OGBPSEQ1 v5 sidecar, written and structurally validated on hardware — FACT

4 360 684 bytes streamed after the teardown by build `vstate-0004` (commit
`b017e38`, DOL `b0ed33f0…97c5`). Recomputed on analysis, independently of this
repository's parser: magic `OGBPSEQ1`, version **5**, header 0x200, `diag_count`
**29**, `diag_rec_size` 160, `semantic_size` 1024, `diag_flags` 0; header CRC
`5baa1a83` and total CRC `1e16aee5` both verify; footer `OGBPEND1` at
`0x004289E0`, ending exactly at the file size. Sections exactly contiguous with
zero overlap and zero orphan bytes: header `0x000000`, frames `0x000200`
(10 503 × 192), events `0x1EC740` (210 × 64), episodes `0x1EFBC0` (4 × 512),
cycles `0x1F03C0` (80 × 128), semantic block `0x1F2BC0` (1 024), diagnostics
`0x1F2FC0` (29 × 160), raw VIDEO `0x1F41E0` (2 304 000), raw AUDIO `0x4269E0`
(8 192), footer `0x4289E0`. The log recorded 657 of 1 024 ring lines with **0
dropped and 0 truncated**. Both parsers of this repository — C
(`gbp_vstatedump_parse_v5`) and Python (`tools/vstate.py`) — **strict-validate**
it, which for a v5 file includes every cross-field invariant of §R4.8.

### GBP-HW-109 — the scientific target reached again, with the service never interrupted — FACT

**1 114 005** admitted cycles over **175.848 s**, of which **120.009 s** of valid
post-baseline observation against a 120 s target; `stop=nominal_negative`,
`status=ok_structured_change_observed`, SERVICE ok, RESTORE ok, `transport_ok=1`,
`errors=0`. 1 114 005 unmasks, deliveries, ACKs, re-arms and ISR entries — the
five counts are equal — with 1 114 001 lean cycles and 4 verify. 420 073 VIDEO and
720 210 AUDIO whole-block drains (1 140 283 bulk transfers, 268 093 184 bytes,
4 482 364 transfers total). **0 reentry, 0 timeouts, 0 busy, 0 uncertain writes,
0 main-loop W1C, 1 teardown W1C, 0 counter overflows.** Frame capture: 10 503
frames, 10 491 complete, 12 incomplete, 24 resync, baseline valid at 0.077 s;
structured change **observed**, 9 episodes, 7 stable, 2 unstable.

### GBP-HW-110 — twenty-nine semantic disagreements, all survived — FACT

29 disagreements, **all** classified `SOURCE_SERVICED`, 0 `SOURCE_OTHER`, 0
`NON_SOURCE`, 0 majority-extra, 0 observational; 29 preserved, 0 not preserved,
the store never capped. Recomputed **directly from each record's own 32 bytes**,
without trusting any stored value: `Disc = 0x0500`, `GBI majority = 0x0100`,
`delta = 0x0400`, `disc_extra = 0x0400` (AUDIO), `majority_extra = 0x0000`, class
`SOURCE_SERVICED` — in 29 of 29. The run did not stop for any of them, and the
first and last are 1 106 523 cycles apart (4 303 and 1 110 826).

### GBP-HW-111 — the current-cycle attribution is correct in this producer — FACT

The defect of `vstate-0003` (GBP-HW-104) **does not occur once** in this file.
In 29 of 29 records, recomputed from the record's own bytes:

```text
authoritative_value  0x0100   == (disc & ~SRC_MASK) | (gbi & SRC_MASK)
service_selected     0x0100   == authoritative & AV_MASK
ack_value            0x8100   == authoritative | 0x8000
record_flags         0x01c1   = SERVICE_WRITTEN | ACK_WRITTEN | REARM_WRITTEN | FOLLOWUP_FILLED
timing chain                    t <= t_ack <= t_rearm <= t_next_cause
```

Zero cross-field invariant failures in either parser. For comparison, the v4 file
of the previous run had `t_ack > t_next_cause` in 23 of 23 records and an
authoritative value that was not the majority in 22 of 23. Here: **0 of 29 and
0 of 29**. `tools/vstate.py diag` reports **zero producer warnings**.

### GBP-HW-112 — the timing of one service transaction, on clocks that are all trustworthy — FACT

Measured over the 29 events, time base 40.5 MHz, using only fields this producer
writes once in the cycle that owns them:

```text
READ  -> ACK          2 600 .. 2 756 ticks     64.20 ..  68.05 us
ACK   -> REARM          828 .. 1 445 ticks     20.44 ..  35.68 us
REARM -> NEXT CAUSE        77 ..    94 ticks     1.90 ..   2.32 us
READ  -> NEXT CAUSE     3 505 .. 4 128 ticks    86.54 .. 101.93 us
```

These are measurements of this run. They are **not** physical bounds, and no
internal causality is asserted from them.

### GBP-HW-113 — the omitted AUDIO source was present in the next ordinary read, 29 of 29 — FACT

`next_pending_gbi = next_pending_disc = 0x0400` in every one of the 29 records,
and the follow-up state is `FU_SOURCE_PRESENT_NEXT` in 29 of 29 with
`DF_FOLLOWUP_FILLED` set — the per-source split leaves `absent = 0x0000`. The
next cause arrives **77 to 94 ticks (1.90 to 2.32 µs) after the re-arm**, and
this time the re-arm timestamp belongs to the same cycle as the read, so the
interval is measured rather than inferred.

**What this supports, and how strongly.** A model in which the ACK clears VIDEO,
the AUDIO assertion stays pending across it, and the re-arm is what releases the
pending source, is **CORROBORATED — VERY STRONG**: it accounts for 29 of 29
events, for the ordering of all four intervals above, and for the 23 events of
the previous run. It is **not** FACT: no observation in this repository
distinguishes a source that survived the ACK from a new assertion arriving in
that 1.9 to 2.3 µs window, and nothing here reads the device's internal state.
The distinction stays **UNKNOWN** (U-GBP-033).

### GBP-HW-114 — the non-uniformity is a contiguous suffix again, and the corpus is now 52 events — FACT

Decomposing each window into its eight replicas, the `0x0500` values always form
a **contiguous suffix at the end of the 32-byte window**: 29 of 29 in this run,
with lengths 24 × 1, 2 × 2 (cycles 113 805 and 1 030 312) and 3 × 3 (cycles
941 104, 1 042 937 and 1 110 826). Combined with `vstate-0003` (23 events,
21 × 1, 1 × 2, 1 × 3) the physical corpus is:

```text
52 physical semantic disagreements, two long runs, one build family
45 x suffix length 1     3 x length 2     4 x length 3
52/52 contiguous 0x0500 suffix
52/52 AUDIO present in the next ordinary read
```

This is a description of two runs, not a model: no rate, no distribution and no
extrapolation is claimed from it, and only `vstate-0004` has a trustworthy
`t_rearm`, so the REARM-to-next interval above is stated for its 29 events alone.

### GBP-HW-115 — clean teardown after the second successful long run — FACT

Handler installed once and restored once (`old_handler=null`), `mask_ok=1`,
`intmr_final=0x000001FA`, `pi_sticky_final=0`, one teardown W1C, AR_INFO restored
with a confirming readback, `power_cycle_required=1`, teardown variant
`S5_target`, `next_cause_at_end=1`. The final state matches the one every
physical run of this family has reached.

### GBP-HW-116 — the Game Boy Player tolerated a 5-second masked pause between stage A and the handler install, and nothing observable moved — FACT

Build `vstate-prewait-5000`, commit `500429a`, on the physical unit. After stage
A put CONTROL in the running shape the probe waited, with PI still masked, no
handler installed and no service transaction in flight:

```text
requested    5000 ms          want_ticks   202 500 000
elapsed      202 500 009 ticks @ 40.5 MHz = 5.000 000 22 s
iterations   78 307 256       done=1 (the time bound, not the iteration cap)
```

Read-only snapshots either side of the pause (`WAITPRE` / `WAITPOST`):

```text
CONTROL      8c -> 8c
IRQ semantic 0500 -> 0500      (Disc and GBI readings agreed on both)
INTSR        00012000 -> 00012000
INTMR        000001fa -> 000001fa
```

The pause began 4 325 699 ticks (106.8 ms) after the CONTROL transform and ended
206 829 535 ticks (5.107 s) after it. **The claim is exactly the duration and the
position exercised**: 5 s at that point, on this unit, under these conditions.
Nothing here licenses 10 s, 30 s or an unbounded wait, and nothing here says what
the AGB was displaying — the probe reads no VIDEO before the handler exists.

### GBP-HW-117 — normal service resumed after the pause and stayed 1:1 for 1 108 063 transactions — FACT

Immediately after the wait the handler installed (`rc=ok`, `old_handler=null`),
PREUNMASK passed (`ok=1`, `control=8c`, `irq=0500/0500`), and the first delivery
arrived with a handler latency of **89 ticks (~2 µs)** — the same shape every
earlier run of this family measured.

```text
unmasks 1 108 063   deliveries 1 108 063   acks 1 108 063   rearms 1 108 063
transport  timeouts 0   busy 0   uncertain 0   overflow 0
frames     10 446 observed (10 445 complete, 1 incomplete, 2 resync)
baseline   valid at frame 4
```

Every ACK has its RE-ARM and every delivery has both. A pause of this length at
this position did not leave the device in a state that broke the sequence that
follows it.

### GBP-HW-118 — clean teardown and restore after the diagnostic — FACT

`CONTROL restore semantic=90 rc=ok readback_vote=90 ok=1`; IRQ stop written and
read back (`write_ok=1 readback_ok=1 masks_readback=1 bit15_readback=1`); PI
cleanup performed with no sticky bit; AR_INFO restored to `0043` with a
confirming readback; handler restored; `mask_ok=1`; `intmr_final=000001fa`;
`next_cause_at_end=1`; `power_cycle_required=1`. The final state matches every
physical run of this family.

### GBP-HW-119 — the R3 policy behaved identically in a third long run — CORROBORATED

38 semantic disagreements preserved, and the shape is the one `vstate-0003` and
`vstate-0004` established:

```text
total 38   SOURCE_SERVICED 38   SOURCE_OTHER 0   NON_SOURCE 0
disc-extra 38   majority-extra 0   both-direction 0
quarantined 0   deferred 0   follow-up present 38/38
```

This is a third corroboration of the policy under an unusual startup, not new
information about the mechanism: **U-GBP-033 stays OPEN** and nothing here is
used to argue a cause.

## GBP-VIDEO-003 / color-0001 — first physical run, 2026-09-18

Build `color-0001`, commit `9d8302d`, DOL sha256 `cc88e4c4...`, on the physical
unit with a Game Pak present (`CONTROL orig=92`, bit `0x02` set) carrying the
controlled eight-bar AGB colour stimulus. Fixture
`captures/fixtures/hw-gamecube-gbp-2026-09-18-color-0001.gbpreplay` and its
OGBPCOL1 v1 sidecar `…-color-0001-color.bin` (sha256 `95595f9d…`, 461 684 B).
Raw log `GBP-VIDEO-003_color-0001.log`, sha256 `28c5a06c…`, 40 790 B, kept in
`captures/local/` and never versioned.

### GBP-HW-120 — a fixed 5000 ms pre-handler wait was sufficient in its intended position — FACT

`PREHANDLERWAIT ms=5000 want_ticks=202500000 elapsed=202500008` — 5.000 000 20 s
at 40.5 MHz — `iters=78307393 done=1`, the time bound and not the iteration cap.
Read-only snapshots either side: `CONTROL 8e -> 8e`, IRQ semantic `0500 -> 0500`,
`INTSR 00012000 -> 00012000`. Capture then opened and the frame sequence was
`0 not_complete (1 block) · 1 resync · 2, 3, 4 eligible`, certifying on the
third consecutive eligible frame. **The claim is the duration and the position
exercised, and nothing more:** 5000 ms at that point, on this unit, under these
conditions, with this stimulus. Nothing here licenses another duration, and
nothing here says the AGB had finished booting rather than merely reached a
state whose picture stayed stable — the probe reads no VIDEO before the handler
exists.

### GBP-HW-121 — the runtime certified, serviced and restored cleanly — FACT

`stop=color_certified (8)`. Capture 0.072 s; 5.179 s of the 30 s safety budget
consumed, nearly all of it the wait. 440 deliveries = acks = rearms = unmasks
(162 VIDEO, 288 AUDIO); 0 timeouts, 0 busy, 0 uncertain, 0 overflow, 0 errors;
R3 reported **0** semantic disagreements in this run. Teardown restored CONTROL,
IRQ, PI, AR_INFO and the handler with readback, `intmr_final=000001fa`. The
sidecar validates offline: magic `OGBPCOL1`, version 1, header `0x200`, header
CRC `96002fc9` and total CRC `19ebfbda` both recomputed and matching, footer
`OGBPCEND` at `0x70B68`, size == `off_footer + 12`. Three certified records,
frame_index 2/3/4, 40 blocks each, raw offsets 0 / 153 600 / 307 200, ring slots
2 / 3 / 0, all three with `sig0 7780f781` and `sig39 f780f780`.

### GBP-HW-122 — the three certified frames are NOT byte-identical over the full raw frame — FACT

`tools/vcolor.py`, run unmodified, reports `VERDICT: INCONCLUSIVE - CERTIFIED
RAW MISMATCH`. First difference at byte `0x108` — block 0, x = 66, y = 0, byte 0
of the group — `83` vs `03`. Pairwise differing bytes: A/B **2125**, B/C
**2073**, A/C **2137**, touching all 40 blocks and all 160 rows. The runtime's
`sig[40]` agreement was therefore not byte agreement, which is exactly the case
the gate exists to catch. **This run is INCONCLUSIVE under the frozen analyser
and stays that way**; no result below changes that verdict.

### GBP-HW-123 — every one of those differences is in a byte neither reference decoder reads — FACT

Differing bytes by position in the four-byte group:

```text
pair    byte0   byte1   byte2   byte3
A/B      1878       0     247       0
B/C      1815       0     258       0
A/C      1860       0     277       0
```

Bytes 1 and 3 — the only bytes the Start-up Disc and GBI consume (GBP-VID-003,
recorded 2026-09-16, two days before this run) — differ in **zero** positions
across all three pairs. Under the pre-existing projection
`word = (b1 << 8) | b3` the three certified frames are identical in **38 400 of
38 400** words. This is a recomputable property of the versioned sidecar, pinned
by `tests/host/test_vcolor.py::PhysicalColor0001`.

### GBP-HW-124 — post-gate diagnostic projection of the eight bars — FACT for the vector, HYPOTHESIS for the mapping

Because GBP-HW-122 did not pass, what follows is a **diagnostic projection and
not a measurement the experiment's own gate accepted**. Every bar is uniform —
one distinct `colour15` across its 30 × 160 pixels — and identical in A, B and C:

```text
bar        0       1       2       3       4       5       6       7
stimulus  0x0000  0x001F  0x03E0  0x7C00  0x7FFF  0x0001  0x0020  0x0400
observed  0x0000  0x7C00  0x03E0  0x001F  0x7FFF  0x0400  0x0020  0x0001
```

H1 — the outer-group swap, i.e. the references' RGB5A3 reading with R = bits
14–10 — matches **8/8** bars exactly. H2 — verbatim AGB BGR555 — matches 4/8,
and those four (`0x0000`, `0x03E0`, `0x7FFF`, `0x0020`) are precisely the
swap-invariant colours, which carry no discriminating information at all; H2
fails on every bar that can tell the two apart. The popcount multiset is
preserved, so no bit was gained or lost.

**Status:** FACT for the observed vector (a recomputable property of the
versioned sidecar); **HYPOTHESIS** for "the Game Boy Player presents colour in
the references' order", because the run that produced it did not satisfy its own
pre-registered acceptance gate. The correct sentence is *the post-gate
diagnostic projection matches H1 exactly*. **U-GBP-011 remains OPEN.**

### GBP-HW-125 — bit 15 observed separated from the colour payload for the first time — FACT

Exactly one word per certified frame has bit 15 set, at x = 0, y = 0, and here
that word is exactly **`0x8000`**: flag set, `colour15 = 0x0000`, because the
stimulus paints bar 0 black and writes bit 15 as zero everywhere. Every earlier
physical frame had `0xFFFF` at that word — the flag over white `0x7FFF`, where
bit 15 is indistinguishable from the colour. Count and position reproduce the
earlier fixtures exactly: one per frame at word 0 in `vstate-0001` / `-0003` /
`-0004`, and 3 of 88 stored blocks in GBP-VIDEO-001, all at word 0.

**Status:** FACT for the count, the position and the value in this run.
Everything beyond that — that bit 15 is a frame-start marker the device sets
rather than a colour bit the AGB happened not to write, and that it would behave
this way for any picture — stays as it was: the predicates are F (code) ×2
(GBP-VID-004) and the device-side meaning is not isolated by this run. The
stimulus writing bit 15 as zero is what makes the separation visible; it does
not prove who sets it.

### GBP-HW-126 — bytes 0 and 2 vary between consumed-identical physical frames, in earlier fixtures as well — FACT

Re-measured this round over the already-versioned fixtures, restricted to frame
pairs the runtime's own `sig[40]` calls identical, differing bytes by group
position:

```text
fixture                    byte0  byte1  byte2  byte3   blocks touched
vstate-0001 f190 vs f194     584      0     46      0        40/40
vstate-0003 f190 vs f194      97      0     25      0         8/40
vstate-0004 f190 vs f194     292      0     19      0        39/40
color-0001  A vs B          1878      0    247      0        40/40
```

GBP-VIDEO-001, at block granularity over 88 stored blocks and 84 480 words:
byte 0 differs from byte 1 in **688** words and byte 2 never differs from byte 3
— reproducing GBP-HW-070 exactly from the stored fixture — and between blocks
with an identical consumed projection only byte 0 differs (11–15 bytes per pair).

**Byte 0 is pre-existing evidence** (GBP-HW-058, GBP-HW-070, cause open in
U-GBP-029; U-GBP-021 already forbids consuming it, and `src/gbp/gbp_vsig.h`
excludes bytes 0 and 2 from the runtime signature citing exactly that).
**Byte 2 variability is NEW**: GBP-HW-070 recorded zero cases in GBP-VIDEO-001,
and it is present in the 2026-09-16/17 vstate fixtures (8712, 8679 and 8907
words of 576 000) and in this run. It was latent in bytes already committed and
had never been measured or registered. Nothing here says the device changed —
the earlier measurement was made on a different, uniform picture. Recorded
against **U-GBP-029**, which stays OPEN.

## GBP-VIDEO-003 / color-0002 — confirmatory physical run, 2026-09-18

Build `color-0002`, commit `39f1980`, DOL sha256
`d3c1f09efb105a0027d3bc596528448c579a234cbbe8306469d7f1222cbf29c1` — built
clean at that exact commit, with no `-dirty` suffix, before the run. Physical
unit with the same eight-bar AGB stimulus as `color-0001`. Fixture
`captures/fixtures/hw-gamecube-gbp-2026-09-18-color-0002.gbpreplay` and its
OGBPCOL1 v1 sidecar `…-color-0002-color.bin` (sha256 `f49c4cf2…`, 461 684 B).
Raw log sha256 `194f92f9…`, 40 900 B, in `captures/local/`, never versioned.

**This run was judged by a contract written before it existed**
(`HARDWARE_TESTS.md` §V4, commit `a86b079`) using an analyser that already
existed at that commit (`tools/vcolor2.py`), neither modified afterwards.

### GBP-HW-127 — the confirmatory run serviced, certified and restored cleanly — FACT

`stop=color_certified`. 440 unmasks = deliveries = acks = rearms; 162 of 162
VIDEO completed, 288 AUDIO; 1840 transfers, 1 801 728 bulk bytes; `timeouts=0`,
`busy=0`, `uncertain=0`, `overflow=0`, `errors=0`, `transport_ok=1`.
`SEMANTIC total=0` — zero R3 disagreements, as in `color-0001`. Teardown restored
CONTROL, the IRQ stop word with readback, PI with `pi_cleanup_sticky=0`, AR_INFO
and the handler; `mask_ok=1`, `intmr_final=000001fa`, `pi_sticky_final=0`.
Capture 0.072 s of a 5.179 s / 30 s safety budget; certification completed
66.635 ms after the capture opened. Three certified frames, indices 2/3/4,
40 blocks each, ring slots 2/3/0, every one with `sig0 7780f781` and
`sig39 f780f780` — the same runtime signatures `color-0001` produced.

The pre-handler wait: `ms=5000 want_ticks=202500000 elapsed=202500011 iters=78307097
done=1` — 5.000 000 27 s at 40.5 MHz, overshooting by 11 ticks (0.27 µs) — with
`CONTROL 8e -> 8e`, `IRQ 0500 -> 0500`, `INTSR 00012000 -> 00012000`,
`INTMR 000001fa -> 000001fa`. Second physical confirmation that 5000 ms suffices
at that position in this setup. The log header reads `lines=318 dropped=0
**truncated=0**`: the two records that replaced the 266-character line are
complete on hardware, including the trailing `intmr_post` both earlier physical
runs lost.

### GBP-HW-128 — the three certified frames carry exactly one picture — FACT

Under `word = (b1 << 8) | b3`, bit 15 included and nothing masked:

```text
A vs B    0 of 38400 words differ
B vs C    0 of 38400 words differ
A vs C    0 of 38400 words differ
```

Recomputed directly from the raw bytes, independently of the analyser. This is
the pre-registered acceptance gate of §V4B and it **passed**.

### GBP-HW-129 — bit 15: one word per frame, at the origin, over a black pixel — FACT

Exactly one word per certified frame has bit 15 set, at x = 0, y = 0, and the
word is `0x8000` — flag set, `colour15 = 0x0000`, because the stimulus paints
bar 0 black and never writes bit 15 anywhere. The three bitmaps are identical
(`FLAG15_STABLE`).

**Status:** FACT for the count, the position and the value across three frames of
this run, reproducing `color-0001` (GBP-HW-125) and every earlier physical frame.
**`FLAG15_STABLE` means reproducible, not understood.** What sets the bit, and
under what conditions it could appear elsewhere, is **not** established by this
run and is now **U-GBP-034**. What the run does establish is narrower and worth
separating: the AGB wrote zero there and the delivered word has it set, so bit 15
is **not** the colour value and is added on the path.

### GBP-HW-130 — the observed colour vector, every pixel of every bar — FACT

Each of the eight 30-pixel bars holds exactly **one** `colour15` across all 4800
of its pixels, in all three certified frames, and the three vectors are identical:

```text
bar        0       1       2       3       4       5       6       7
stimulus  0x0000  0x001F  0x03E0  0x7C00  0x7FFF  0x0001  0x0020  0x0400
observed  0x0000  0x7C00  0x03E0  0x001F  0x7FFF  0x0400  0x0020  0x0001
```

Orientation consistent: the two permutation-invariant bars sit where the stimulus
put them (`0x0000` at bar 0, `0x7FFF` at bar 4), so the frame is not read
mirrored.

### GBP-HW-131 — the Game Boy Player exchanges the outer 5-bit groups — FACT

`tools/vcolor2.py`, run unmodified on the physical sidecar:

```text
STANDING: CONFIRMATORY
VERDICT: CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP
```

Exactly one of the seven pre-registered transformations reproduces all eight
observed values. The others fail, first at bar 1 (`H2_identity`, `H3_byte_swap`,
`H4_intra_group_reversal`, `H1_H3`), bar 0 (`H5_complement`) and bar 5
(`H1_H4`). Comparison is exact equality on all eight values; there is no score
and no tolerance.

**The claim, stated at its exact width.** In the VIDEO window the consumed pixel
word carries the AGB's 15 colour bits with the two outer 5-bit groups
**exchanged**: what the AGB wrote in bits 4–0 arrives in bits 14–10 and vice
versa, bits 9–5 unchanged. Under the reading both reference decoders implement
(bit 15 flag, 14–10 R, 9–5 G, 4–0 B) the displayed colour is therefore the AGB's
intended colour. **This promotes the colour order from CORROBORATED to FACT**: a
physical pixel of known colour has now been captured, which is precisely what
U-GBP-011 said it was waiting for.

**What it is not.** It is not a statement about bytes 0 or 2 (U-GBP-029 stays
OPEN), nor about why bit 15 is set (U-GBP-034), nor about U-GBP-033. Within a
5-bit group this stimulus pins bit 0, bit 5 and bit 10 individually and each
group as a set; a permutation fixing those three while rearranging only bits 1–4
inside a group is not excluded by it. That limit was written into the design
**before** the run (§V3.19), which also records the follow-up pattern that would
close it; the run produced no residual ambiguity, so that follow-up is not
triggered. The evidence is about AGB Mode 3 video on the path this run exercised
and about nothing else.

### GBP-HW-132 — two independent runs deliver the identical picture — FACT

The three certified frames of `color-0001` and `color-0002` — separate physical
runs, different commits, separate power cycles — are **byte-identical in the
consumed projection**: 38 400 of 38 400 words in all three corresponding pairs.
Their full raws still differ (2514, 2449 and 2481 bytes), entirely in bytes 0 and
2 and never in 1 or 3.

Recorded as corroboration only: `color-0002` confirms itself under its own
contract without this comparison, and **`color-0001` is not re-judged** — it
remains INCONCLUSIVE under its own frozen contract, permanently.

### GBP-HW-133 — the full-raw diagnostic, a fifth independent corroboration — FACT

Reported on every `color-0002` run because U-GBP-029 is open, and never used as a
gate. The three certified frames are **not** byte-identical over the full
153 600-byte raw frame:

```text
pair    total   byte0   byte1   byte2   byte3
A/B      2434    2222       0     212       0
B/C      2483    2244       0     239       0
A/C      2485    2264       0     221       0
```

40 of 40 blocks and 160 of 160 lines touched; first difference at `0x110` —
block 0, x = 68, y = 0, byte 0, `83` vs `03`. Bytes 1 and 3 differ in **zero**
positions in every pair. This identifies no mechanism and promotes no meaning;
it is evidence for U-GBP-029 and nothing else.

### GBP-HW-134 — the GX display path ran on real hardware, and the draw-done token came back — FACT

First physical execution of a GX path in this repository. `stream-0002`'s
pre-probe display self-test, which converts a synthetic 240×160 frame, uploads it
as `GX_TF_RGB5A3`, draws one quad, arms a draw-done token and copies to a
framebuffer, reported on hardware:

```text
drawdone=1  releases=1  xfb_presents=1  consistent=1  cb_restored=1
```

`on_draw_done` has no call site anywhere in the linked image — it appears once,
as its own symbol at `0x80004788`, and its address is materialised only at
`main.c:319` into `GX_SetDrawDoneCallback` (§V5.28.10). So `drawdone=1` can only
have come from the physical PE FINISH interrupt. The ownership machine of
`src/gbp/gbp_vpresent.c` began and ended the self-test in a consistent state, and
the previous draw-done callback was restored.

This says nothing about the Game Boy Player, about sustained streaming or about
pacing: the self-test runs before any capture opens and touches no device. It is
evidence about the GameCube display path only.

### GBP-HW-135 — the pre-registered R1 offset reproduced exactly — FACT

§V5.28.10 and §V5.28.14 predicted, before physical execution, that
`gbp_vqueue_balanced()` would read false on every run with a deterministic **+1**
presentation offset introduced by the pre-probe self-test. The hardware printed:

```text
converted=0  presented=1  SELFTEST.xfb=1  balanced=0
```

which is the predicted state exactly. The pre-registered identity
`converted == (presented − SELFTEST.xfb) + overrun` gives `0 == (1 − 1) + 0`,
which holds.

The value of this entry is methodological: a defect found by reading the source,
quantified before the run and confirmed by the run. It remains a **reporting**
defect and carries no claim about the device.

### GBP-HW-136 — `stream-0002` aborted before any device access, at its first storage gate — FACT

```text
VSTATE abort reason=store_or_bounds_invalid
VSTATE end   status=abort_store_unavailable
```

The abort is `gbp_vstate_probe.c:790`, `!st || !gbp_vstate_storage_ok(st)`, the
first gate of `gbp_vstate_probe_run()` and the statement before any transport,
register or interrupt work. The failing predicate is `!s->episode_raw`
(`gbp_vstate.c:72`): the POC passed `episode_raw = NULL, episode_raw_cap = 0` and
`frames_cap = 4096` against a required 16384 (`main.c:569-570`, `:163`). Three of
the twelve predicates were false; short-circuit evaluation means the NULL store is
the one that fired. Reproduced on the host, bit for bit, including the logged
`static_bytes=6922240` (§V5.29.9).

The refusal is **correct**: `gbp_vstate_probe.c:812` would have executed
`memset(NULL, 0, 2 949 120)` over GameCube low memory before the first device
access, and `gbp_vstate.c:739` writes into the same store whenever an episode
opens. Neither site checks for NULL.

The physical memory layout printed by the same run is clean — no overlap, no
misalignment, no overflow, 2.78 MiB of MEM1's 24 MiB in use (§V5.29.5). This was
never a memory-availability problem.

### GBP-HW-137 — nothing of the GBP service was exercised — FACT (a negative)

```text
deliveries=0  acks=0  rearms=0  frames=0  handler_installed=0
```

The run never installed a handler, never unmasked, never touched the Game Boy
Player. **No claim about video, streaming, pacing, the service path or the device
may be derived from this run**, in either direction. It is evidence that the
storage gate fires before the device does, and nothing else.

Its correct description is: PHYSICAL EXECUTION ATTEMPTED · GX SELF-TEST
PHYSICALLY PASSED · GBP STREAM CAPTURE NOT STARTED · ABORTED PRE-SERVICE.

### GBP-HW-138 — the storage contract passed on hardware, and the service conserved 280 621 cycles with a consumer attached — FACT

First physical run of `stream-0003` (commit `03b32a9`, 471 648 B,
`2f8e362e…199e3`). Log `logs/GBP-VIDEO-004_stream-0003.log`, 88 705 B, sha256
`62996c7d4fb282b1833c1d53060828baf3395d40154922c92e0add63004fa4ec`,
`dropped=0 truncated=0`.

```text
ENVSTORE … configured_bytes=7106560 required_bytes=6922240 fault=- ok=1
unmasks = deliveries = acks = rearms = 280 621
VIDEO 105 841 selected / 105 841 completed · AUDIO 181 481
timeouts=0 busy=0 overflow=0 uncertain=0 errors=0 transport_ok=1
transfers=1 129 255 bulk_transfers=287 322 bulk_bytes=1 149 775 616
```

The `stream-0002` pre-service abort is resolved on hardware. `bulk_transfers`
exceeds `deliveries` by 6 701 because that many causes carried both an AUDIO and
a VIDEO block. **This is the first time the service path conserved with a
consumer, a converter and a GX display attached**; `vstate-0004` conserved for
longer but had none of them.

### GBP-HW-139 — the stream consumer and the GX ownership machine ran on hardware, and the invariants held throughout — FACT

```text
taken=2298 converted=2298 presented=2286 overrun=0 dropped_before_convert=0
repeats=12 no_cpu_texture=0 abandoned_no_raw=0
submit=2299/2299 blocked_inflight=0 drawdone=2299 spurious=0 releases=2299
xfb_presents=2287 xfb_skipped=12 consistent_at_end=1 inflight_at_end=0
STREAMINV checks=246548 failures=0 main=0/244249 isr=0/2299
```

`2 299 = 2 298 scientific + 1 self-test` for submits, draw-dones and releases.
Every published frame was taken and converted; **no frame was superseded in the
mailbox and none overran the generation guard**. The R8 latch makes the strong
statement possible: the invariants held **throughout**, across 246 548 checks on
both the main and the interrupt side, not merely at the final instant.

`drained=0` is correct, not a failure: `inflight_at_end=0`, so the teardown's
blocking drain was never needed.

### GBP-HW-140 — the consumer slice, measured on hardware for the first time — FACT

```text
calls=280621 slices=91920 completed=2298
skipped_cause_pending=70025 pending_before=70025
pending_after=21527 arrived_during=21527
ticks_min=1129 ticks_max=1663 ticks_mean=1361   (tb_hz = 40 500 000)
```

```text
min  27.8765 us · max  41.0617 us · mean  33.6049 us
skipped_cause_pending / calls = 24.95 %
arrived_during / slices       = 23.42 %
slices per completed frame    = 40.0 exactly (one tile row each)
publish_mean 780 519 ticks = 19.27 ms · convert_mean 54 478 ticks = 1.345 ms
```

A quarter of all pump calls found a GBP cause already latched and yielded the
cycle. **`arrived_during` is a coincidence count and no causality may be read
from it.** The placement moves from PLAUSIBLE BUT UNMEASURED to **measured, with
no observed transport effect**; it is **not** timing-safe on one run.

### GBP-HW-141 — the incomplete intervals are a startup-region signature that predates streaming — CORROBORATED

```text
stream-0003  frames=2648 incomplete=13 resync=26
             INTERVALS 1:1, 33:1, 34:3, 38:8, 40:2635
             all 13 within the first 408 frames; zero in the remaining 2 240
             clusters: {11,14,18} {217,220,223} {251,254,257} {402,405,408}
vstate-0004  frames=10503 incomplete=12 resync=24   (NO streaming consumer)
             INTERVALS 30:1, 34:4, 38:7, 40:10491
             at indices 1, 32, 35, 38, 92, 95, 98, 192, 196
```

The same 34/38/38 cluster shape, the same confinement to the startup region, and
nearly the same absolute count across a 4× duration difference — which is what a
fixed startup cost looks like and is not what a per-frame rate looks like.

**Streaming did not measurably change them.** Whether blocks were lost, or
boundaries observed early or late, or causes coalesced, is **UNKNOWN**: this run
has no ground truth, and **none of these may be called source-frame loss**.

### GBP-HW-142 — R3 replicated under a real streaming workload — CORROBORATED

```text
SEMANTIC  total=42 serviced=42 other=0 non_source=0 disc_extra=42 maj_extra=0
          both=0 quarantined=0 deferred=0
SEMANTIC2 preserved=42 fu_present=42 fu_absent=0 fu_no_next=0 fu_unknown=0
```

42 disagreements, all `disc_extra`, all serviced, all with a follow-up cause
present — under a workload none of the earlier runs had, a real game repainting
continuously. **The mechanism stays UNKNOWN and U-GBP-033 remains OPEN.**

`STREAMFLAG15 last_count=1 first_x=0 first_y=0`: one bit-15 word per frame at
(0,0), consistent with every previous physical run. **U-GBP-034 stays OPEN.**

### GBP-HW-143 — `power_cycle_required=1` is a by-construction latch, reproduced identically by two validated runs — FACT

`power_cycle_required` is set to 1 **before every IRQ register write**
(`gbp_initirqa_probe.c:409`, `gbp_vstate_probe.c:1329`, `:1437`). This run made
561 244 of them, all completed, `uncertain_writes=0`. The `FINAL` snapshot is
taken *"under the restored AR_INFO"* (`gbp_initirqa_probe.c:483`), so its
`control`/`irq` are not comparable with values read under the experimental
AR_INFO.

| run | FINAL | flag |
| --- | --- | --- |
| `vstate-0004` (physically validated) | `control=00 irq=9090` | 1 |
| `color-0002` (physically validated) | `control=00 irq=9292` | 1 |
| `stream-0003` | `control=00 irq=9292` | 1 |

`stream-0003` reproduces `color-0002` exactly, and both validated runs carry the
same flag with accepted teardowns. **It is not evidence that the hardware
remained in a state requiring a power cycle.** The standing operator instruction
to power-cycle before the next run is unchanged.

### GBP-HW-144 — real cartridge video was presented through Open-GBP on physical GameCube output — FACT (log) + OPERATOR OBSERVATION

**LOG FACT:** 2 286 scientific GX presentations, 2 298 frames published,
converted and submitted, 105 841 VIDEO transfers completed, ownership invariants
held throughout.

**OPERATOR OBSERVATION**, with two photographs preserved in `captures/local/`
(`…-1.jpeg` `564cb781d7fd9a3dceba68ea27daa103713c300a1329bbc8e177de6b6a467d86`,
`…-2.jpeg` `326fbdd608025cfe8da6ae1019c291b4158f8b27e03845c0970f39d7f8d424d0`):
a rainbow checkerboard appeared first, then the actual cartridge game; the Game
Boy boot logo was not seen; the image looked normal; the picture was small and
centred near native size.

**The startup image is the display self-test, confirmed from the rendering code,
not inferred from appearance.** `display_selftest()` writes
`((x>>3)<<10) | ((y>>3)<<5) | ((x^y)&0x1F)` presented as `GX_TF_RGB5A3`, so
R = x>>3 left→right, G = y>>3 top→bottom, B = (x^y)&0x1F — a 30 × 20 grid of
8-pixel cells with exactly the photographed gradient and checkerboard.

**The small centred picture is by design**, confirmed from source: a 240×160
`GX_NEAR` texture drawn as a quad at `x0 = (640−240)/2 = 200`,
`y0 = (480−160)/2 = 160`, covering 37.5 % × 33.3 % of the framebuffer. §V5.16
specified exactly this and left scaling to Phase 9. **Not a rendering defect.**

**The missing boot logo is expected for this POC**: the AGB begins executing at
console power-on and its logo sequence finishes before Swiss has loaded the DOL,
let alone before the 5 000 ms pre-handler wait. **No number of skipped source
frames may be inferred from elapsed time** — that is the leading-edge limitation
OGBPIDX1 already pre-registered.

**Scope of the milestone:** real DOL-017, real cartridge, Open-GBP runtime,
physical GameCube output, native-size presentation, sustained for this 44.3 s
smoke. It does **not** imply GBP-VIDEO-004 complete, zero source-frame loss, a
timing-safe pump, correct pacing, absence of tearing, or final UI.

### GBP-HW-145 — two software defects found by the run, neither fixed — FACT

**P2, HIGH.** `GBP_VSTATE_F_MAJORITY_EXTRA` (`gbp_vstate.h:109`) and
`GBP_VSTATE_F_EPISODE_STABLE` (`gbp_vstate.h:121`) are **both `0x1000` in the
same frame-flag word**. `gbp_vstate.c:1052` writes the latter into `f->flags`;
`gbp_vqueue_classify()` tests the former first and returns `QUARANTINED`. The run
shows the collision exactly: **324 episodes, all closed as stable → 324 frames
quarantined**, while the R3 machinery reported `maj_extra=0 quarantined=0`.

Effect: **324 of 2 635 complete frames refused (12.30 %)**, cadence 59.74 Hz →
51.85 Hz, independently confirmed by `publish_mean` 19.27 ms = 51.89 Hz. The
underlying trigger is ordinary changing cartridge video driving the structured-
change detector (324 episodes in 44.3 s, against 9 in 175.8 s for `vstate-0004`'s
static picture) — but the *mechanism* of the loss is the bit collision, not a
policy.

**P1, MEDIUM.** `gbp_vqueue_balanced()` asserts
`converted == presented + overrun` and omits the third legitimate terminal state
of a converted frame: **repeated** — submitted and drawn, but both framebuffers
spoken for, so the XFB copy was skipped. The run conserves exactly under the
correct identity: `2 298 == 2 286 + 0 + 12`, with `xfb_skipped=12 == repeats=12`.
**`balanced=0` is an accounting predicate missing a state, not a conservation
failure.**

Both are `src/gbp` changes, both are proposed and **not applied**, and both are
locked as passing unit tests that assert the current behaviour together with the
arithmetic showing why it is wrong.

**STATUS, added after the fact and kept separate from the finding above.** Both
defects were fixed in `stream-0004` (§V5.36) and the fix was audited (§V5.37,
DECISION A): P2 by moving `F_MAJORITY_EXTRA` to `0x4000` — the flag never written
to any file, so **zero historical bytes change meaning** — behind a compile-time
uniqueness guard, and P1 by adding the `repeated` terminal plus a residual
bounded by the texture-buffer count. **The observations recorded above are not
amended.** `stream-0003`'s counters stand exactly as logged, and neither defect is
**physically** resolved until a new physical run says so.

---

## GBP-VIDEO-004 / `stream-0004`, executed 2026-09-19 — the corrections, physically confirmed

Source: `logs/GBP-VIDEO-004_stream-0004.log`, 88 854 bytes, sha256
`2ec3ada282caf86885345486b82ff61f9122f2953d0e53f9cc6f12941c212dda`,
`test_id=GBP-VIDEO-004 build_id=stream-0004 commit=e11df66`, `dropped=0
truncated=0`. Every number below was recomputed from that file, never retyped
from a report.

### GBP-HW-146 — P2 is PHYSICALLY CONFIRMED FIXED — FACT

The pre-registered gate (§V5.37.17) was `SEMANTIC.quarantined ==
STREAMSRC.quarantined`. It reads **0 == 0**.

What makes this decisive is that the SOURCE population is the same in both runs.
`FRAMECAP` is identical in every field — `frames=2648 complete=2635
incomplete=13 resync=26 anomaly_region=13 counted=2619 blocks=105841` — as are
`video=105841/105841`, `audio=181481` and `capture_s=44.323`. The two runs
therefore decompose the **same 2 635 complete source frames** differently:

```text
stream-0003   2635 = 2298 published + 324 quarantined + 13 anomaly
stream-0004   2635 = 2622 published +   0 quarantined + 13 anomaly
```

`2622 − 2298 = 324`, **exactly** the count the aliased bit had been refusing. The
functional diff between the two builds is a recomputable property of the source:
`gbp_vstate_probe.c`, `gbp_irq_service.c`, `gbp_transport.c`, `gbp_avblock.c`,
`gbp_vsig.c` and `hsp_backend_irq.c` have **zero changed lines**, and
`gbp_vstate.c`'s only change is a compile-time typedef with no runtime effect.
There is no other causal candidate.

This does **not** retro-correct `stream-0003`. Its counters stand exactly as
logged; what changed is which of them the software produces.

### GBP-HW-147 — P1 is PHYSICALLY CONFIRMED FIXED — FACT

```text
STREAMDISP converted=2621 presented=2603 overrun=0 repeated=18 undispositioned=0
2621 == 2603 + 0 + 18 + 0        balanced=1
```

Four independent counters that the identity does not use agree with it:

```text
xfb_skipped   18 == repeated 18                      one branch of submit_ready()
xfb_presents 2604 == 2603 scientific + 1 self-test
submit 2622  == 2621 converted + 1 self-test,  blocked_shutdown=0
                                                 -> nothing was left READY, so the
                                                    residual is 0 by a counter and
                                                    not merely by arithmetic
fills_started 108249 == 2622 completed + 105626 abandoned + 1 IN FLIGHT
                                                 -> and `taken − converted = 1`
                                                    names the same frame
```

The audit's ingest rule (§V5.37.10) — `undispositioned > 0` is acceptable only
with `blocked_shutdown > 0` — holds trivially: both are 0. The stop caught one
conversion mid-flight, which the ownership identity closes exactly and which
`stream-0003`, stopping between conversions, did not have.

### GBP-HW-148 — the publication cadence after the false quarantine was removed — FACT

```text
publish_mean = 684 292 ticks / 40 500 000 Hz = 16.8961 ms = 59.1853 Hz
2 622 published / 44.323 wall seconds        =              59.157 Hz
stream-0003: 19.2721 ms = 51.889 Hz
```

Removing the false quarantine restored the observed publication cadence **in
this run** to approximately the observed source closure rate (`2648 / 44.323 s =
59.743 Hz`). This is a measurement of one run with one cartridge, **not** a frame
rate the runtime guarantees and not a claim that any other workload will behave
this way.

### GBP-HW-149 — ownership invariants held across a second independent run — CORROBORATED

```text
submit 2622/2622   drawdone 2622   releases 2622   spurious 0
consistent_at_end 1   inflight_at_end 0   cb_restored 1
STREAMINV checks=221741 failures=0   main=0/219119   isr=0/2622
```

Two physical runs, different consumer populations (2 298 and 2 621 converted
frames), **zero** invariant failures in 246 548 + 221 741 = 468 289 checks. The
rule under test — at most one draw-done token in flight, and the callback
releases exactly one buffer by index — is now corroborated rather than observed
once.

### GBP-HW-150 — the consumer slice, replicated — CORROBORATED

```text
ticks_min 1147 = 28.321 us   mean 1380 = 34.074 us   max 1674 = 41.333 us
skipped_cause_pending 70 205 / 280 672 = 25.01 %
arrived_during        25 352 / 104 841 = 24.18 %
```

Against `stream-0003`'s 27.88 / 33.60 / 41.06 µs and 24.95 %. The permitted claim
is unchanged and deliberately narrow: **the pump did not cause an observable
transport failure in this run.** `unmasks == deliveries == acks == rearms =
280 672`, `timeouts=0 busy=0 overflow=0 uncertain=0 errors=0 transport_ok=1`,
every W1C from the ISR and none from the main thread. That is not a claim that
the slice position is universally timing-safe, and nothing here measures the
margin it consumes.

### GBP-HW-151 — the valid clock is NOT wall time, and the old witness sizing premise is disproven — FACT

```text
CLOCKSEC  capture_s = 44.323   valid_s = 30.001   target_s = 30
frames closed = 2648            wall/valid = 1.4774
```

`valid_observation_elapsed` accumulates the **span of each counted frame**, not
the time between frames, so 30 valid seconds took 44.3 wall seconds and closed
**2 648** frames. The sizing premise the indexed experiment was designed around —
"30 s → ~1 792 source frames" — is wrong by a factor of 1.48, and it was wrong in
`stream-0003` too (identical clocks); nobody had checked it against a closed-frame
count.

Consequence, recorded before the next run rather than after it: **a witness store
must be bounded by a COUNT of retained frames, never by a target expressed in
valid seconds** (§V5.39.3). This is a methodological correction to the
experiment's protocol; the OGBPIDX1 wire format is unaffected and is not
re-versioned.

### GBP-HW-152 — the operator saw no visible change — OPERATOR OBSERVATION

The operator reports that the visual behaviour appeared **essentially the same as
`stream-0003`**: real cartridge video, visibly normal, native-sized, with nothing
new apparent. No new photographs were taken because nothing looked different.

Recorded separately from the machine-log facts above, and weaker than any of
them: it is an unaided human impression of a 44-second run, it measures no
cadence and can resolve no 12 % publication difference. It is **consistent with**
an accounting-and-cadence correction that changes no geometry, no colour and no
UI — which is what `stream-0004` is — but it corroborates nothing on its own, and
nothing here is promoted because of it.

---

## GBP-VIDEO-004 / `stream-0005`, the FIRST indexed run, executed 2026-09-19

Sources, both verified before anything was read from them:
`logs/GBP-VIDEO-004_stream-0005.log`, 66 427 B, sha256
`165a3e32df7faf0d81bdaf4841852ba5e3fa7b6f0a7722cf01e2327cb3486eaf`; and
`logs/GBP-VIDEO-004_stream-0005-idxcap.bin`, 8 946 060 B, sha256
`6c822d63cfaa2bd19554054b26b0b8d7264723eca946dbc5c3d39037b85a193d`.
`build_id=stream-0005 commit=10250a4`, `dropped=0 truncated=0`. Every figure was
recomputed from those bytes, twice — once by `tools/`, once by an independent
reimplementation that shares no code with them.

### GBP-HW-153 — the count-bounded stop worked on hardware — FACT

`stop=witness_target_reached`. The run ended because the 2048th witness record
closed, not because a clock expired: `STREAMWIT records=2048/2048 target=2048
frames_seen=2048 discarded=0 staged=81876 placed=81876 out_of_range=0
store_full=0 target_reached=1`, and `FRAMECAP frames=2048 store_full=0`.

Transport was conserved across the whole run: `unmasks == deliveries == acks ==
rearms = 217 120`, `video=81876/81876`, `timeouts=0 busy=0 overflow=0
uncertain=0 errors=0 transport_ok=1`, every W1C from the ISR and none from the
main thread. This is the first physical confirmation that an experiment in this
project can be bounded by a **count of retained evidence** instead of by time.

### GBP-HW-154 — the OGBPIDXCAP1 sidecar is structurally valid — FACT

Parsed independently of `tools/vidxcap.py`: magic `OGBPIDXC`, version 1, header
0x180, record 4368, capacity 2048, count 2048, header CRC-32 `a7c14cfb`, footer
`OGBPEND1`, global CRC-32 `e2762908`, and **2048 of 2048 per-record CRC seals
valid**. The file is exactly 8 946 060 bytes — the size §V5.40.10 derived from
the layout before the run existed.

### GBP-HW-155 — witness retention under a real physical workload — FACT

81 876 blocks staged and placed, 0 out of range, 0 scratches discarded. The
added critical-path work measured `min 35 / mean 69 / max 1561` ticks at
40.5 MHz = **0.864 / 1.704 / 38.543 µs**, one sample per block, totalling
**0.1395 s of the 34.277 s run — 0.407 %**. The single 38.5 µs outlier is
recorded descriptively; nothing here attributes a cause to it.

Under that load the runtime behaved exactly as `stream-0004` did:
`STREAMCONS taken=2044 converted=2043 presented=2026 overrun=0 repeats=17
undispositioned=0 balanced=1`; `2043 == 2026 + 0 + 17 + 0`; `xfb_skipped ==
repeats`; `submit == drawdone == releases == 2044`, `spurious=0`,
`consistent_at_end=1`; `STREAMINV checks=169245 failures=0`; `sci_clean=1`.

**Witness retention caused no observable transport or ownership failure in this
run.** That is not a claim of universal timing safety.

### GBP-HW-156 — the canonical witness decodes perfectly — FACT

Of the 2 046 records that carry all 40 blocks, **all 81 840 canonical strips
decode**: every symbol is ZERO or ONE, every SYNC is `0xB2`, every CRC-8 matches,
and `BLOCK_INDEX == witness slot` in **81 840 of 81 840** cases. Not one complete
record fails for canonical-strip corruption.

Observed FRAME_ID values span **1 .. 343 with no value missing** inside that
range.

### GBP-HW-157 — the stimulus reports itself FAULTED — FACT, and it is right

Every canonical strip carries exactly one STATUS per FRAME_ID:

```text
FRAME_ID 1        STATUS 0x7f      11 strips   FAULT=0, the initial sentinel
FRAME_ID >= 2     STATUS 0x80  81 829 strips   FAULT=1, VMARGIN=0
```

By the frozen contract STATUS in frame *f* certifies updates through *f−1* and
never *f* itself, so the first update reported as failing is **the very first
update the ROM performed**, and FAULT is sticky thereafter.

The mandatory consequence: **`STIMULUS_INVALID_FOR_DECISIVE_CLAIM`**, and
**SOURCE FRAME CONTINUITY = INCONCLUSIVE**. `tools/vindex.py` reaches that
verdict on its own and makes no loss claim.

### GBP-HW-158 — the mixed-ID staircase is a PRODUCER artifact — FACT

**1 705 of the 2 046 complete records carry two FRAME_IDs — 83.3333 %** — and
341 carry one. The pattern is not noise; it is a perfectly regular staircase. In
every one of the 1 705 mixed records the newer ID occupies a **leading
contiguous run of blocks**, and that run takes exactly five values:

```text
newer id occupies   3 blocks : 340 records
                   12 blocks : 341
                   21 blocks : 341
                   30 blocks : 342
                   39 blocks : 341
then one single-ID record, and the cycle repeats
```

339 of the 341 cycles are exactly *five mixed records then one single-ID record*.
The write front advances **9 blocks = 36 raster lines per captured GBP frame**.

**This is not GBP frame loss, reorder or duplication, and must never be reported
as such.** It is the AGB producer publishing one image progressively across
several of its own frames while the GBP faithfully captures each intermediate
state. The root cause is established separately in GBP-HW-159.

### GBP-HW-159 — the root cause, and the previous budget estimate was wrong — FACT

`update_frame()` wrote the whole 240×160 picture directly into VRAM inside what
the design called one VBlank. The real cost, derived from GBP-HW-158's staircase
rather than from any estimate:

```text
VRAM stores per source frame  54 + 54 + 8 + 8 = 124 per row x 160 = 19 840
measured advance              9 blocks = 36 rows per captured frame
one full image                4.44 AGB frames = 74.4 ms = 1 248 000 cycles
per VRAM store                62.9 cycles
VBlank budget                 83 776 cycles (1309 ticks at F/64)
OVERRUN                       14.9 x        -- only 10.7 of 160 rows fit
```

**Why the original estimate was wrong:** it counted VRAM stores and assumed a
store costs a cycle or two. It never accounted for INSTRUCTION FETCH. The ROM
never set `WAITCNT`, so the loop executed from cartridge ROM at the reset wait
states (4/2, no prefetch), and fetch — not the store — dominated at ~63 cycles
per written word. The FAULT bit was therefore correct, and relaxing it would
have destroyed the only signal that caught this.

Fixed in `indexed-0002` by splitting prepare from publish (§V5.41). **The
OGBPIDX1 wire format is unchanged and is not re-versioned**: this was a producer
implementation defect, not a contract defect.

---

## GBP-VIDEO-004 / `stream-0005` run 2 — `indexed-0002`, executed 2026-09-19

Sources, verified before anything was read from them. The operator's SD card
carried them under the same names as run 1, so they are preserved separately:
`logs/GBP-VIDEO-004_stream-0005-run2.log`, 66 515 B, sha256
`e02d1160d0aa887d408e9af892c433c026348778e615c344fa23bc1082e12ae8`; and
`logs/GBP-VIDEO-004_stream-0005-run2-idxcap.bin`, 8 946 060 B, sha256
`111ea227eefe600e81416be7fce34bd13d8ff7d5de26efe825bbbfa5b08ec42d`.
Run 1's files are untouched. **The GameCube runtime is byte-identical to run 1**
(`stream-0005`, `commit=10250a4`), so the cartridge is the only variable.

### GBP-HW-160 — `indexed-0002` publishes inside the VBlank — FACT

**FAULT is clear.** Every one of the 81 840 canonical strips of the 2 046
complete records carries `STATUS = 0x18`: `FAULT = 0`, `VMARGIN = 24`. Not one
strip disagrees, and `tools/vindex.py` reports `stimulus fault seen False`.

Against run 1, where every FRAME_ID from 2 onward carried `0x80` and the update
overran the VBlank by 14.9×, **the prepare/publish split fixed the overrun
physically.** This is a validated result *for this run* and not a universal
timing guarantee.

### GBP-HW-161 — the measured VBlank margin is 24 scanlines — FACT

`VMARGIN` is the monotone minimum of `VCOUNT_LAST − vc1` over the run, so the
worst publication observed ended at `VCOUNT = 227 − 24 = 203`.

VBlank is lines 160..227, i.e. 68 lines. The worst publication therefore consumed
**203 − 160 + 1 = 44 of the 68 available lines**, about **65 %** of the window,
leaving 24 lines of headroom. The pre-hardware estimate was ~60 %; the physical
measurement is 65 %, and **the measurement is the authority**.

### GBP-HW-162 — zero mixed-ID frames, and exact block indices — FACT

```text
complete records                       2 046
records carrying exactly ONE FRAME_ID  2 046   (MIXED_BLOCK_IDS = 0)
valid symbols                     81 840 / 81 840
SYNC                              81 840 / 81 840
CRC-8                             81 840 / 81 840
BLOCK_INDEX == witness slot       81 840 / 81 840
```

Run 1 had 1 705 mixed records of 2 046 — **83.3333 %**. Run 2 has **none**. The
progressive tearing of `indexed-0001` is physically closed.

### GBP-HW-163 — the FRAME_ID population is gapless and monotone — FACT

Over the 2 046 complete records: minimum **7**, maximum **1030**, **1024 unique
values**, and the observed set is exactly `7 .. 1030` with **no value missing**.
Deltas between consecutive complete records:

```text
delta  0 : 1 022        delta +1 : 1 023
delta > +1 : none       delta < 0 : none
```

No `OBSERVED_ID_GAP`, no `OBSERVED_REORDER`, no `UNRESOLVED_HALF_RANGE`.

### GBP-HW-164 — every FRAME_ID was captured exactly twice — FACT

**1 022 of the 1 024 observed IDs appear in exactly two consecutive complete
records**; run lengths of identical consecutive IDs are `{2: 1022, 1: 2}`. Only
IDs 7 and 1030 appear once, and those are the leading and trailing edges. ID 9's
second appearance falls inside the 33-block startup/resync record, which is
excluded from the complete-frame population by contract.

By the frozen classification `delta == 0` is **`OBSERVED_DUPLICATE_ID`**, and the
official analyzer reports exactly that — 1 021 duplicates and 1 023 contiguous
over its 2 044 decisive transitions, verdict `OBSERVED_DISCONTINUITY`. It does
**not** promote duplicates to contiguous.

Rates: the capture closed 2 048 frames in 34.277 s = **59.75 Hz** and completed
2 046 = 59.69 Hz, while unique FRAME_IDs advanced at **1 024 / 34.277 s = 29.87
Hz**. The ratio is **2.00 captured frames per source ID**, and it is regular to
1 022 of 1 022.

### GBP-HW-165 — the duplication is PRODUCER-side, and the mechanism is exact — FACT

The ROM's loop waits like this:

```c
prepare_frame(...);                             /* visible period            */
while (REG_VCOUNT >= VCOUNT_VBLANK_FIRST) { }   /* wait until NOT in VBlank  */
while (REG_VCOUNT <  VCOUNT_VBLANK_FIRST) { }   /* wait until VBlank starts  */
publish_frame();                                /* VBlank                    */
```

If `prepare_frame()` returns while `VCOUNT` is **still inside a VBlank**, the
first loop waits for that VBlank to end and the second waits for the next one:
**a publication opportunity is skipped entirely**, and the GBP captures the
unchanged framebuffer a second time.

Publication ends at `VCOUNT = 203` (GBP-HW-161), leaving `25 + 160 = 185` lines
= **227 920 cycles** before the next VBlank begins. The observed cadence — always
2:1, **never 1:1 and never 3:1** — bounds the preparation without any estimate:

```text
227 920  <=  T_prepare  <  508 816 cycles      0.811 .. 1.811 AGB frames
```

(The upper edge is not the end of the skipped VBlank: landing in the *visible*
period of the following frame still publishes in that frame's VBlank, so 2:1
persists until the overrun reaches the VBlank after it.)

Corroborated independently from the code: `prepare_frame` is 195 ARM
instructions at **`0x080002ac` — cartridge ROM** — driving ~8 640 symbol stores
and 2 160 bit writes per frame; at ROM wait states that is ~253 000 cycles,
**inside the measured band**. `publish_frame` was at `0x03000000` (IWRAM) since
`indexed-0002`; `prepare_frame` was left behind.

**ATTRIBUTION: the AGB producer, not the Game Boy Player.** Four independent
reasons: the ROM's own loop structure predicts 2:1 quantitatively; the bound
derived from the cadence matches the code's cost; the GBP captured 2 046 complete
frames in both runs at its normal ~59.7 Hz while the *cartridge* changed; and a
capture-side mechanism would have to duplicate every frame exactly once, 1 022
times, without a single miss.

**Duplicate FRAME_IDs here are NOT GBP frame duplication, loss or reorder.**
Source-frame continuity remains **INCONCLUSIVE**: the GBP faithfully delivered
every frame it was shown, and it was shown each picture twice.

### GBP-HW-166 — the startup/resync record explains ID 9 — FACT

Two incomplete records, both excluded from the complete population by contract:

```text
record 0   1 block,  all-ONE symbols, SYNC decodes as 0xff -> pre-stimulus edge
record 5  33 blocks, every decoded strip carries FRAME_ID 9
           witness slot -> decoded BLOCK_INDEX: 0->0, 1->1, then 2->9, 3->10, ...
```

The assembler resynchronised mid-frame, so source blocks 2..8 never reached this
record. That is why ID 9 has only **one** complete-record occurrence while its
neighbours have two — not a lost source frame, a record the contract excludes.

---

## GBP-VIDEO-004 / `stream-0005` run 3 — `indexed-0003`, executed 2026-09-19

### GBP-HW-167 — the exact run-3 artifacts, and a filename collision that cost a raw log — FACT

```text
log      logs/GBP-VIDEO-004_stream-0005-run3.log          66 356 B
         sha256 1c8e2aaac7588716fb51f93ba4d55eedde8453406c230c4b66b3daed6bf02bf3
sidecar  logs/GBP-VIDEO-004_stream-0005-run3-idxcap.bin 8 946 060 B
         sha256 6eb7585cb0b4cad1813aa9b9bd2a5127312722777796f77443f53cf7ab5a035a
runtime  stream-0005, commit 10250a4, 481 664 B
         sha256 35bbbdd684c2d0048d58661df1c079b613e01dee2d2cced12ba8f2f1e4d87092
stimulus indexed-0003, source commit 8840050, arm-none-eabi-gcc (devkitARM) 15.2.0
  canonical build/stimulus/agb-indexed/agb-indexed.gba   2 880 B
            sha256 37119bb6ac68398dbd3fa75e6ad5c51c8aeb543277ac8d3b03b57f7a6f0caaca
            logo area EMPTY by policy
  delivery  build/physical/agb-indexed-cart.gba          2 880 B
            sha256 9f04916b88308e7045f207136f5fc681e5bab33ac9b22d2e19be12c16b8d9cc2
            logo area from the colour cartridge that booted twice; payload past
            0x0C0 BYTE-IDENTICAL to the canonical ROM; never committed
```

**The SD workflow names every run identically**, and run 3 was handed over under
the un-suffixed names that had held run 1. Run 1's raw bytes survived **only**
because `captures/local/` had archived them, which is exactly why that policy
exists. All three runs are now stored unambiguously as `…-run1`, `…-run2`,
`…-run3`, each verified against its own SHA-256.

### GBP-HW-168 — the GameCube runtime replicated a third time — FACT

```text
stop=witness_target_reached · unmasks == deliveries == acks == rearms = 217 117
video 81876/81876 · timeouts/busy/overflow/uncertain/errors all 0 · transport_ok=1
FRAMECAP 2048 / 2046 / 2 / resync 4 / anomaly_region 2 / 81 876 · store_full 0
STREAMWIT 2048/2048, staged == placed == 81 876, out_of_range 0, discarded 0
STREAMCONS 2043 == 2026 + 0 + 17 + 0, balanced=1 · STREAMGX 2044/2044, spurious 0
STREAMINV 169 243 checks / 0 failures · sci_clean=1
witness copy 0.864 / 1.704 / 38.568 us over 81 876 samples
```

**No observable regression of `stream-0005` transport or ownership in this run.**
Not a universal timing guarantee. Presence bits sum to **81 875** against
`staged == placed == 81 876`; the assembler's own `blocks` field agrees at
81 875 and **no record is short** — the extra block is the boundary block that
closed record 2047, as in both earlier runs.

### GBP-HW-169 — `indexed-0003` preserved the VBlank correction — FACT

`STATUS = 0x18` on **all 81 840** canonical strips of the 2 046 complete
records: **FAULT = 0, VMARGIN = 24**. VBlank is `VCOUNT` 160..227 = 68 lines, so
the worst publication finished at `VCOUNT = 203`, consuming **44 of 68 lines =
64.7 %**. Identical to `indexed-0002`: moving `prepare_frame` into IWRAM did not
disturb the publication.

Valid **for this physical run**; not a universal timing guarantee.

### GBP-HW-170 — zero mixed frames, exact block indices — FACT

```text
complete records carrying exactly ONE FRAME_ID   2 046 / 2 046
MIXED_BLOCK_IDS                                  0
valid symbols / SYNC / CRC-8                     81 840 / 81 840 each
BLOCK_INDEX == witness slot                      81 840 / 81 840
MISPLACED_BLOCK_INDEX                            0
INVALID_CANONICAL_STRIP                          0
```

### GBP-HW-171 — the producer cadence is now 1:1 — FACT

Every one of the 2 046 complete records carries a **distinct** FRAME_ID.
Duplicates: **0**, against 1 022 in run 2. The raw observed ID set, including
the incomplete record, is **16 .. 2062 — 2 047 consecutive values with none
missing**.

Cadence from the capture's own time base, between the first and last complete
records rather than count ÷ wall clock:

```text
id 16 at t=34146918906555185 · id 2062 at t=34146920293914609
2 046 FRAME_ID increments over 34.255788 s  ->  59.7271 Hz
```

That is one FRAME_ID per AGB refresh. **Observed indexed source cadence in this
run**, not a guaranteed frequency.

### GBP-HW-172 — the frozen verdict is OBSERVED_DISCONTINUITY, on one startup gap — FACT

`tools/vindex.py`, unmodified, on the run-3 sidecar:

```text
container  2048/2048 records, seals valid, header CRC cdacc494, global 271e84ea
stimulus   fault seen FALSE
decisive   2 044 transitions, first 0x000010 last 0x00080d
           OBSERVED_ID_CONTIGUOUS  2 043
           OBSERVED_ID_GAP             1
VERDICT    OBSERVED_DISCONTINUITY
```

The single non-contiguous transition is **record 3 (id 18) → record 5 (id 20)**.
Record 4 carries **id 19 with 34 of 40 blocks**: the assembler resynchronised
mid-frame — its witness slots map 0→0, 1→1, then 2→8 — so blocks 2..7 never
entered the record. The frozen adapter passes only all-40-block records to the
analyzer core, so id 19 is absent from the decisive population and 18→20 reads
as a gap.

**This is NOT source-frame loss.** ID 19 was produced by the AGB and captured by
the Game Boy Player; 34 of its 40 blocks are in the sidecar and decode perfectly,
and the raw ID set has no missing value. The gap is the contract declining — 
correctly and conservatively — to bridge an incomplete record.

The startup signature (`incomplete=2, resync=4`) is identical in all three
indexed runs and in `stream-0003`/`stream-0004`: the known startup-region
artifact of GBP-HW-141, which predates streaming.

**No frozen rule trims an interior resync**, and none was invented after seeing
the data. A contiguity claim would require a rule — for instance one defining
where the decisive interval begins relative to the startup region — **written
and frozen before the next run**, never after this one.

### GBP-HW-173 — three runs, one runtime, three producer behaviours — FACT

The GameCube runtime was byte-identical in all three: `stream-0005`,
`commit=10250a4`, `35bbbdd6…d87092`. Only the cartridge changed.

| run / stimulus | complete | mixed | unique IDs | dup | STATUS | captures per ID |
| --- | --- | --- | --- | --- | --- | --- |
| 1 / `indexed-0001` | 2 046 | **1 705** | 341 | 0 | `0x80` (FAULT) | **6.00 : 1** |
| 2 / `indexed-0002` | 2 046 | 0 | 1 024 | **1 022** | `0x18` | **2.00 : 1** |
| 3 / `indexed-0003` | 2 046 | 0 | **2 046** | **0** | `0x18` | **1.00 : 1** |

Run 1 carried `0x7f` on 11 strips (the sentinel) and `0x80` on 81 829. The
observed failure mode changed exactly with each producer fix, and only with it.

**Attribution, now promoted:** the run-1 mixed-ID staircase was caused by the
stimulus rendering directly into VRAM across several of its own frames, and the
run-2 2:1 duplication by `prepare_frame` overrunning the visible period from
cartridge ROM. **Neither was evidence of Game Boy Player frame loss, duplication
or reorder.** Scoped to these three runs.

### GBP-HW-174 — the operator's impression — OPERATOR OBSERVATION

The operator reports that **the image appeared to run progressively faster
across the successive versions of the indexed stimulus**.

Recorded separately from every machine fact above, and weaker than all of them:
it is an unaided visual impression, it measures nothing, and no conclusion rests
on it. It is **consistent with** the measured series — 6.00:1, then 2.00:1, then
1.00:1 captured frames per source ID — and that is the whole of its evidentiary
weight.

### GBP-HW-175 — the baseline NEVER establishes on an indexed stimulus — FACT

All three physical runs report it in the raw log, identically:

```text
BASELINE valid=0 frames_seen=1 frame_index=0 t_valid=0
         sig0=00000000 sig39=00000000 reference_updates=0 early_candidates=2043
MATRIX   ... baseline=never_established structured=not_observed
CLOCKS   ... baseline_elapsed=0 valid=0 valid_at_target=0
```

and the sidecars agree: `F_PRE_BASELINE` is set on **2048 of 2048** records in
runs 1, 2 and 3.

The mechanism is not a defect. The assembler's baseline waits for a frame to
*repeat*; the indexed stimulus changes every frame by construction (the 24-bit
`FRAME_ID` increments and the bar moves), so the reference signature can never
stabilise and `reference_updates` stays at 0.

**Why this is load-bearing.** It rules out an entire family of otherwise
attractive qualification criteria. Any rule that waited for `baseline_valid`, a
stable episode or a repeated reference would wait for ever on this stimulus.
The rule adopted in §V5.44 uses region and geometry terms only, which is both
what the design required and the only thing that works here.

### GBP-HW-176 — the startup transient has the same shape in all three runs — FACT

Replaying the recorded structure of each capture (frame `blocks`, `flags`,
`completeness` — no `FRAME_ID`, no `STATUS`, no pixel):

| run | non-qualifying record indices | disqualified | streak resets | all inside |
| --- | --- | --- | --- | --- |
| 1 | 0, 1, 4, 5 | 4 | 1 | first 7 frames |
| 2 | 0, 1, 5, 6 | 4 | 1 | first 7 frames |
| 3 | 0, 1, 4, 5 | 4 | 1 | first 7 frames |

After that point **2 041+ consecutive frames qualify without a single
exception** in every run. The disturbance is a startup episode, it is short, and
it reproduced three times under three different producer behaviours — which is
what makes it attributable to startup rather than to any one stimulus.

### GBP-HW-177 — what the UNMODIFIED analyzer returns on the windowed populations — FACT

A computation over recorded evidence, not an observation of a new run. The
analyzer (`tools/istim.py`, `tools/vindex.py`) was **not modified**; it was given
the records the §V5.44 window would have retained.

| run | window opens at frame | retained | as captured | windowed |
| --- | --- | --- | --- | --- |
| 1 | 70 | 1 978 | `STIMULUS_INVALID_FOR_DECISIVE_CLAIM` | `STIMULUS_INVALID_FOR_DECISIVE_CLAIM` |
| 2 | 71 | 1 977 | `OBSERVED_DISCONTINUITY` | `OBSERVED_DISCONTINUITY` |
| 3 | 70 | 1 978 | `OBSERVED_DISCONTINUITY` | `OBSERVED_CONTIGUOUS` |

Run 3's single non-contiguous transition is `0x000012 → 0x000014`, carried by
**record 5** — far inside the transient, and cleared by a window of N=2 upward.

**The recorded verdicts do not change.** Run 3 stands as `OBSERVED_DISCONTINUITY`
permanently. This row is what a rule fixed in advance would have retained, not a
re-reading of the capture.

### GBP-HW-178 — the window cannot rescue a faulty or a duplicating producer — FACT

Tested from N=1 to N=1024 on the real state machine:

```text
run 1 (STATUS.FAULT latched)     STIMULUS_INVALID_FOR_DECISIVE_CLAIM at every N
run 2 (every source frame twice) OBSERVED_DISCONTINUITY               at every N
```

This is the control that matters. A startup window that could also clear a
latched FAULT or hide a systemic 2:1 duplication would be a verdict-laundering
device rather than a measurement rule. It removes a startup transient and
demonstrably nothing else.

### GBP-HW-179 — `stream-0006` will return `OBSERVED_CONTIGUOUS` — HYPOTHESIS, **TESTED AND UPHELD 2026-09-19 by run 4** (result: GBP-HW-188/189)

Not a fact and not evidence. It is the prediction the round exists to test, and
it is stated in advance so the next run can refute it.

**It is refuted by:** any non-contiguous decisive transition in the windowed
population; a `STATUS.FAULT`; a warm-up that never completes; `records_n` short
of 2048; or `blocks_out_of_range != 0`.

**It is not confirmed by** a contiguous run alone — one run replicates neither
the producer nor the GBP. Confirmation needs the pre-registered verdict from a
capture that also satisfies `vidxcap.usability()`.

**OUTCOME.** Run 4 met every refutation condition without triggering one: the
warm-up completed (70 frames), `records_n` reached 2 048, `blocks_out_of_range`
was 0, no FAULT was latched, and the unmodified analyzer returned
`OBSERVED_CONTIGUOUS` with `decisive-claim ready True`. The prediction was
written before the run and is recorded here as made, not edited after the fact;
what it predicted is now GBP-HW-188 and GBP-HW-189.

### GBP-HW-180 — the exact run-4 artifacts — FACT

The fourth indexed physical run, and the first executed with a scientific window
that was defined **before** the run rather than after it.

```text
GameCube runtime   stream-0006   commit c629445 (CLEAN, no -dirty stamp)
  DOL              483 008 B  a9b8b969ef462bfe11b833f9dd77d56f7aa4a3387d61124f99b72901c9cb0379
  Swiss            Open-GBP/12-stream/boot.dol, byte-identical to the source DOL
  embedded strings stream-0006 · c629445 · GBP-VIDEO-004 · gbp-video-stream-probe

cartridge          indexed-0003, the SAME physical cartridge as run 3
  delivery         2 880 B  9f04916b88308e7045f207136f5fc681e5bab33ac9b22d2e19be12c16b8d9cc2
  canonical        2 880 B  37119bb6ac68398dbd3fa75e6ad5c51c8aeb543277ac8d3b03b57f7a6f0caaca
  relation         bytes 0x0C0..end BYTE-IDENTICAL between the two; the 154 bytes
                   that differ are confined to 0x000..0x0C0, the gbafix header
                   and Nintendo logo region

log                62 513 B  299294ba183ccb5bfcaae2b21b9cf8048c552ea34ce328172a04990a4125d360
sidecar            8 946 060 B  91feed165ec6430434aa0a2ecee61c4c9ea9dd68c419a797c53ea6ca4e98ee89
  header           test_id=GBP-VIDEO-004 build_id=stream-0006 commit=c629445
                   format=OGBPIDXCAP1_v1 witness_target=2048
                   lines=522 dropped=0 truncated=0
```

Archived immutably as `…stream-0006-run4.log` / `…-run4-idxcap.bin` in `logs/`
and `captures/local/`, verified byte-identical to the delivered files, **before**
any other operation. Runs 1–3 were not touched.

Transport conserved and clean: `unmasks = deliveries = acks = rearms = 224 561`,
`audio=145 185`, `video=84 676/84 676`, `overflow=0`, `uncertain=0`,
`timeouts=0`, `busy=0`, `errors=0`, `transport_ok=1`,
`bulk_transfers=229 861` (= 145 185 + 84 676) and `bulk_bytes=919 833 600`,
which is exactly 84 676 × 0xF00 + 145 185 × 0x1000. Stop was
`witness_target_reached` at 35.449 s against a 60 s safety cap — **not** a safety
or time stop.

### GBP-HW-181 — the prospective structural window was PHYSICALLY EXERCISED — FACT

The §V5.44 qualification ran on real hardware for the first time, and the line it
emitted is reproduced verbatim:

```text
WITQUAL policy=consecutive_structural_complete required=64 state=2
        streak_max=64 resets=1 warmup_frames=70 warmup_disqualified=4
        qualify_frame=69 qualified=1 armed=1 window_first_block=0
        first_record_frame=70
```

Every value the software-only replay predicted from runs 1–3 was reproduced by
the physical run: **required 64, streak_max 64, warm-up 70 frames, 4
disqualified, exactly 1 streak reset, armed, first retained frame 70**. The
window opened at a block-0 boundary (`window_first_block=0`), and the 2 048-record
target was reached (`records=2048/2048`, `target_reached=1`,
`out_of_range=0`, `store_full=0`, `discarded=0`).

This promotes the qualification from software-validated to **PHYSICALLY
EXERCISED** for this run. No FRAME_ID, STATUS, SYNC, CRC-8 or pixel took part in
the decision; the rule read only the assembler's verdict on frame shape.

### GBP-HW-182 — warm-up suppression reconciles to the block — FACT

`stream-0005` staged every block it was delivered (run 3: `video=81876`,
`staged=81876`, equal). `stream-0006` must not, and the independent cross-check
registered before the run confirms it did not:

```text
total VIDEO blocks delivered        84 676     (COUNTERS video=84676/84676)
scientific blocks staged/placed     81 921     (STREAMWIT)
difference                           2 755
```

The 2 755 is **not** 70 × 40 = 2 800. It is the exact structural population of
the frames before the window, read from the capture's own interval histogram
(`INTERVALS 1:1,34:1,40:2116`, `FRAMECAP frames=2118 blocks=84676`):

```text
  1 leading incomplete frame          1 block
  1 second incomplete frame          34 blocks
 68 complete warm-up frames      68 x 40 = 2 720 blocks
                                   ----------
 70 warm-up frames                  2 755 blocks
```

and the whole capture closes to the block with nothing unaccounted:

```text
 2 755 warm-up  +  81 920 scientific  +  1 trailing-open  =  84 676
```

The trailing `+1` is the boundary block that OPENED frame 2118; that frame never
closed, so the block was staged into a scratch that was never committed. It is
why `staged = 81 921` while the sidecar serializes `2 048 × 40 = 81 920` present
blocks. Both numbers are correct and they differ by exactly one block, derived
rather than assumed.

### GBP-HW-183 — the run-4 sidecar container is intact — FACT

Recomputed independently of `tools/`, from the frozen `OGBPIDXCAP1 v1` layout:

```text
file size            8 946 060 B, and the header's own declared total_size agrees
magic / version      OGBPIDXC / v1, header 0x180
header CRC-32        0x3DEE4E8A stored, 0x3DEE4E8A recomputed      MATCH
record_size/cap/n    4368 / 2048 / 2048
record seals         2048 / 2048 valid
footer               "OGBPEND1"
global CRC-32        0x4FDEA327 stored, 0x4FDEA327 recomputed      MATCH
```

The global CRC covers the file **up to but not including** the footer magic. A
first recomputation that included those 8 bytes disagreed; the error was in the
recomputation, not the file, and it is recorded because the distinction is easy
to get wrong and the frozen writer is the authority.

### GBP-HW-184 — 2048 of 2048 scientific records are structurally complete — FACT

Every retained record, checked field by field against the record metadata:

```text
blocks == 40                    2048 / 2048
blocks_captured == 40           2048 / 2048
presence bitmap == all 40       2048 / 2048
completeness == COMPLETE_40     2048 / 2048
ANOMALY|DISAGREEMENT|OVERLONG|RESYNC on any record        0
predicate disagreements, total                            0
frame_index                     70, 71, 72, … 2117 — strictly consecutive +1
```

No incomplete record, no resync record, no missing index, no rotation and no
overwrite (`store_full=0`, `frames_discarded=0`). Every record carries flags
`0x0029` = `COMPLETE | PRE_BASELINE | EARLY_CANDIDATE`, which is the signature
GBP-HW-175 predicts: the baseline cannot establish on an indexed stimulus, so
`F_PRE_BASELINE` stands on all 2 048 records — and the §V5.44 predicate
deliberately does not reject on it.

### GBP-HW-185 — the canonical witness decodes perfectly across the window — FACT

Decoded independently from the frozen rules of §V5.33.5/§V5.33.6 — a
reimplementation that imports nothing from `tools/`, and whose CRC-8 reproduced
all ten frozen vectors and the documented single-bit sensitivity over all 38
payload positions before it touched physical bytes.

```text
scientific block witnesses            81 920   (2 048 x 40)
valid ZERO/ONE symbols                81 920 / 81 920
SYNC == 0xB2                          81 920 / 81 920
CRC-8 match over the 38-bit payload   81 920 / 81 920
BLOCK_INDEX == witness slot           81 920 / 81 920

INVALID_CANONICAL_STRIP                    0
MISPLACED_BLOCK_INDEX                      0
MIXED_BLOCK_IDS                            0   (2 048 / 2 048 single-ID records)
```

Frame composition was decoded from the witness bits themselves, not inferred
from record metadata.

**A bounded observation on U-GBP-034, which it does not close:** bit 15 was set
on **0 of 4 423 680** canonical-strip word coordinates (81 920 blocks × 54
words). The canonical witness is STRIP-L, local row 0, x = 1..54, and the bit-15
sighting that opened U-GBP-034 was at the frame's FIRST pixel, x = 0 — a
coordinate this witness does not preserve. The observation therefore bounds where
bit 15 is *not*, and says nothing about where it was seen. **U-GBP-034 stays
OPEN.**

### GBP-HW-186 — FAULT clear and VMARGIN 24 across the whole scientific window — FACT

```text
STATUS = 0x18 on 81 920 / 81 920 scientific block witnesses
         bit 7  FAULT   = 0
         bits 6..0 VMARGIN = 24
```

A single STATUS value, everywhere, with no other value observed. Under the frozen
sticky-FAULT / monotone-minimum-VMARGIN semantics this means the producer never
latched a fault and its worst observed VBlank margin over the window was 24.

**Scope:** this licenses the statement that `indexed-0003`'s VBlank publication
remained physically valid throughout this run's scientific window. It is not a
universal timing guarantee for other software, other cartridges or other
durations.

### GBP-HW-187 — the retained FRAME_IDs are a strict +1 sequence — FACT

```text
first scientific FRAME_ID      85      (0x000055)
last scientific FRAME_ID     2132      (0x000854)
unique FRAME_IDs             2048
sequence                     85, 86, 87, … 2132 — exact, no member missing
```

Classified with the frozen modulo-2^24 rules, never naïve signed subtraction,
over the 2 047 adjacent transitions of the retained population:

```text
CONTIGUOUS (delta +1)          2 047
OBSERVED_DUPLICATE_ID              0
OBSERVED_ID_GAP                    0
OBSERVED_REORDER                   0
UNRESOLVED_HALF_RANGE              0
```

**Observed source cadence**, from the record timestamps and not from the rounded
`CLOCKSEC` line: `t_first(record 0) → t_first(record 2047)` spans **34.272 56 s**
over exactly 2 047 intervals, giving **59.7271 FRAME_ID/s**. Measuring
first-block-to-last-block instead spans 34.284 03 s, which overcounts by one
frame's block-accumulation span (11.456 ms) and must not be used for a rate.

The per-frame interval is extremely regular: minimum 675 259 ticks, maximum
680 913, median 678 083, mean 678 084.3 at `tb_hz = 40 500 000` — a total
excursion of ±0.42 % around the median with **zero** intervals beyond twice the
median. Describe this as the observed indexed source cadence in this physical
window, not as a nominal frame rate.

### GBP-HW-188 — the unmodified official analyzer returns OBSERVED_CONTIGUOUS — FACT

`tools/vindex.py` was **not modified**; its last change is commit `10250a4`,
four commits before this ingestion, and `git status` reports `tools/` clean.

```text
OGBPIDXCAP1 sidecar
  identity              GBP-VIDEO-004 / stream-0006 / gbp-video-stream-probe / c629445
  records               2048 of 2048 (target 2048)
  blocks staged/placed  81921 / 81921  (out of range 0)
  all-40-block frames   2048
  stop                  GBP_VSTATE_STOP_WITNESS_TARGET (11)
  flags                 target_reached, service_ok, stop_is_target
  header/total CRC-32   3dee4e8a / 4fdea327
  decisive-claim ready  True

OGBPIDX1 analyzer report
  observed frames       2048 (intact 2048)
  first/last observed   0x000055 .. 0x000854
  first/last decisive   0x000055 .. 0x000853
  decisive transitions  2046
      OBSERVED_ID_CONTIGUOUS   2046
  excluded from the decisive set:
      trailing_frame_uncertified   frame id 0x000854
      leading_edge / trailing_edge
  stimulus fault seen   False
  VERDICT               OBSERVED_CONTIGUOUS
```

**Two transition counts, both correct, and the difference is the frozen rule.**
The independent decode reports **2 047** adjacent transitions across all 2 048
retained records. The analyzer reports **2 046** DECISIVE transitions, because
`decisive = intact[:-1]` drops the final intact frame: no later STATUS certifies
its own update, so that one transition is excluded by contract rather than by
observation. Quote 2 046 for the analyzer-decisive claim and 2 047 for the
retained population.

### GBP-HW-189 — source-frame continuity within the qualified window — FACT

Within the prospectively qualified OGBPIDX1 scientific window of the
`stream-0006` physical run, the preserved source-frame IDs were **contiguous and
ordered across all analyzer-decisive transitions**; all 2 048 retained records
contained the expected 40 block indices and one consistent FRAME_ID.

```text
first retained metadata frame index   70
last retained metadata frame index  2117
retained records                    2048
adjacent record transitions         2047  (all delta +1)
analyzer-decisive transitions       2046  (all OBSERVED_ID_CONTIGUOUS)
FRAME_ID observed                     85 .. 2132
FAULT                                clear throughout
VMARGIN minimum                       24
```

**This does not prove** zero loss before the qualified window, zero loss after
the final retained record, zero loss for arbitrary durations, full 240×160 pixel
fidelity, that every source frame reached the XFB, zero downstream repeats,
universal 59.7271 Hz operation, or identical behaviour for other cartridges and
software. OGBPIDX1 witnesses STRIP-L, local row 0, x = 1..54 — 4 320 B per frame
— and the claim is exactly that wide.

### GBP-HW-190 — the witness copy-cost statistic changed meaning, and it is not a regression — FACT

```text
run 3 (stream-0005)   copy_ticks min 35  max 1562  mean 69  n 81 876
run 4 (stream-0006)   copy_ticks min  4  max 1379  mean 68  n 84 676
```

`n` rose to the TOTAL VIDEO block count because `gbp_vwitness_note_ticks()` times
the whole `gbp_vwitness_step()` call, and that call now runs — and refuses — for
the 2 755 warm-up blocks as well. Those refusals cost almost nothing, which is
why the minimum fell from 35 ticks to 4.

The aggregate is therefore "cost of a witness step, staged or not", not "cost of
a canonical copy". The mean is essentially unchanged (69 → 68) because the
refusals are 3.3 % of the samples. **Nobody should read `min 4` as the cost of a
40-block copy.** No change was made to the instrumentation this round.

### GBP-HW-191 — downstream disposition in run 4, kept separate from the source — FACT

```text
STREAMSRC    closed=2118 complete=2114 incomplete=2 quarantined=0 anomaly=2 published=2114
STREAMCONS   taken=2113 converted=2113 presented=2096 overrun=0
             dropped_before_convert=0 repeats=17 no_cpu_texture=0
             abandoned_no_raw=0 balanced=1
STREAMGX     drawdone=2114 spurious=0 releases=2114 xfb_presents=2097
             xfb_skipped=17 consistent_at_end=1 inflight_at_end=0 cb_restored=1
STREAMINV    checks=175176 failures=0 (main 0/173062, isr 0/2114)
SELFTEST     ok=1 sci_clean=1
```

No observable `stream-0006` transport or ownership regression in this run:
ownership balanced, zero invariant failures over 175 176 checks, zero overruns,
zero spurious draw-done callbacks, callback restored.

**These are downstream disposition facts and they are a different layer.** 2 113
converted, 2 096 presented and 17 repeats do **not** weaken GBP-HW-189, because
the source witness is taken before any consumer sees a frame. They equally mean
GBP-HW-189 does **not** close consumer/display pacing: source continuity and
presentation disposition are separate questions and neither answers the other.

### GBP-VID-015 — what `presented`, `repeats`, `xfb_presents` and `xfb_skipped` actually count — FACT (software, from the source)

Established by reading the code, not by inference from aggregates. This is
recorded because one of these words has been carrying more weight than it can
support.

| counter | incremented where | EXACTLY what it means |
| --- | --- | --- |
| `STREAMCONS presented` | `gbp_vqueue_note_presented()` ← the `xfb >= 0` branch of `submit_ready()` | **`VIDEO_SetNextFramebuffer()` was called** for this frame. It does **not** mean the VI scanned it out |
| `STREAMCONS repeats` | `gbp_vqueue_note_repeat()` ← the `xfb < 0` branch | a frame that was converted, submitted **and drawn** found no writable framebuffer, so the screen kept the previous image |
| `STREAMGX xfb_presents` | `gbp_vpresent_xfb_handed()` | the same event as `presented`, plus the display self-test |
| `STREAMGX xfb_skipped` | `gbp_vpresent_xfb_target()` returning −1 | the same event as `repeats`, plus a shutdown refusal |
| `STREAMOWN blocked_inflight` | `gbp_vpresent_submit()` refusing while a token is in flight | back-pressure at the token gate |

Presentation stages, and the strongest one this runtime can observe:

```text
A  GX_RENDER_COMPLETE   observable — the DrawDone callback
B  XFB_SELECTED         observable — this is what `presented` counts
C  VI_LATCHED           observable only by SAMPLING, at the next decision
D  ACTUAL SCANOUT       NOT OBSERVABLE
```

**No claim of "displayed" is available.** Any future statement about these 17
events must say stage B.

### GBP-VID-016 — the run-4 aggregate identity, proven from the state machine — FACT (software, from the source)

Not an arithmetic coincidence. These are the predicates inside
`gbp_vqueue_balanced()`, which returned 1 for run 4:

```text
published = taken + dropped_before_convert + (has_pending ? 1 : 0)
    2114  =  2113 +          0             +          1

converted = presented + overrun + repeated  (+ a residual bounded by the
    2113  =    2096   +    0    +    17        texture buffer count; 0 here)

xfb_presents 2097 = 2096 presented + 1 self-test
xfb_skipped    17 =   17 repeats   + 0
drawdone     2114 = 2113 stream    + 1 self-test  (releases likewise)
```

**The `published − taken = 1` is a TERMINAL residual, not a loss.** From the
first identity it is `has_pending = 1`: a descriptor still in the mailbox when
the capture stopped. An INTERIOR unconsumed frame has its own counter —
`dropped_before_convert`, incremented when a new publish replaces an untaken
descriptor — and it was **0**.

### GBP-VID-017 — this runtime has no VI-driven display loop, which rules out a whole family of explanations — FACT (software, from the source)

`VIDEO_WaitVSync()` is never called in the capture path, no retrace callback is
installed, and the only VI observation is a non-blocking
`VIDEO_GetCurrentFramebuffer()`. A "presentation opportunity" is one
`submit_ready()` call, which happens **because a conversion finished**.

```text
Presents are SOURCE-DRIVEN. An opportunity cannot precede its own frame.
```

Two consequences:

1. **"A display opportunity found no new source frame" cannot happen here.** The
   hypothesis is not weak, it is inapplicable, and no test was written for a
   branch that does not exist.
2. **Every one of run 4's 17 holds was already converted and submitted.**
   A conversion or GX deadline miss cannot produce a hold — it would produce a
   token-gate refusal, and run 4 reported `blocked_inflight=0`, `no_texture=0`,
   `submit=2114/2114`.

   > **CORRECTED 2026-09-19 by GBP-HW-197.** This read "converted, submitted and
   > **drawn**". Run 5 measured the order: the DrawDone follows the decision in
   > 2047 of 2047 cases. The conclusion survives — it rests on the back-pressure
   > counters — but the ordering word was wrong.

What remains is the framebuffer branch: with **two** XFBs,
`gbp_vpresent_xfb_target()` returns −1 when the VI is scanning one and the other
has been handed over but not yet latched.

**This does not explain the 17 events.** It narrows what could have caused them
to something a trace can record, which is the whole purpose of `stream-0007`.
No cause is claimed here and no hardware has run.

### GBP-VID-018 — OGBPDISP1 and its trace, frozen before hardware — FACT (software, design)

A separate sidecar for a separate layer; `OGBPIDXCAP1 v1` is untouched. A future
run delivers three artifacts: the `.log` (the qualification is not encoded in
the witness sidecar), `OGBPIDXCAP1` (what was preserved) and `OGBPDISP1` (what
happened to it).

```text
key          gbp_vstate_frame.index — the assembler's own ordinal, already in
             the descriptor. Never a pixel, never a FRAME_ID. The join to
             OGBPIDXCAP1 is OFFLINE.
lifecycle    96 B per frame that entered the consumer, take → terminal
event        40 B per DECISION, including `newest_source` -- the frame the
             queue had waiting -- which separates "the framebuffer was busy"
             from "the pipeline was behind". A token-gate refusal is a COUNTER,
             not an event, because pump() runs ~224 000 times per run
window       the trace opens at capture start; F_IN_WINDOW comes from the
             witness's own ARMED latch, so OGBPIDX1 takes no part in marking it
self-test    gets a lifecycle, carries GBP_VDISP_KEY_NONE and F_SELFTEST, and is
             excluded by FLAG rather than by position
overflow     fails closed: nothing wraps, nothing is overwritten, and the header
             says so
integrity    three CRC-32s (header, per section, global), none of them computed
             in the capture path
cost         4 096 + 4 096 records = 557 112 B of .bss; arena headroom falls
             from 7 511 584 to 6 946 368 B; at most 557 324 B serialized
hot path     0 added writes on the common pump path; 44 writes, 5 clock reads
             and 2 retrace reads per presented frame; the callback is 76 bytes
```

`VIDEO_GetRetraceCount()` is read rather than a retrace callback being
installed: libogc2's handler already exists, so the ordinal costs **no interrupt
load and no new callback**.

**Not established:** that the trace does not perturb what it measures. No
hardware has run, and no statement here is a physical observation.

### GBP-HW-192 — the exact run-5 artifacts — FACT

The fifth indexed physical run, and the first to carry a downstream trace.

```text
GameCube runtime   stream-0007   commit ddf8db6 (CLEAN, no -dirty stamp)
  DOL              491 040 B  74b7488630153ce3baaa42831a9af8ef03a2bce80399d840062965a34906eb36
  Swiss            byte-identical to the source DOL
  embedded         stream-0007 · ddf8db6 · GBP-VIDEO-004

cartridge          indexed-0003, the SAME physical cartridge as runs 3–4
  delivery         2 880 B  9f04916b88308e7045f207136f5fc681e5bab33ac9b22d2e19be12c16b8d9cc2

log                66 838 B      73def124d9f63d9b86b5479255cf91f19e96c2bff4e73678ca9a8a9da7b1f250
OGBPIDXCAP1        8 946 060 B   853c62a3687d43d9e0f487480e8c4b599d0f05122f255df6d69bd3371dd2aa87
OGBPDISP1          287 772 B     8bf23585543bbd386bc1e2362f6540a2ede1b507981b6c1ec1c49e14c8ca34a2
```

Archived as `…stream-0007-run5.{log,-idxcap.bin,-disp.bin}` in `logs/` and
`captures/local/`, every copy verified byte-identical, **before** any other
operation. Runs 1–4 untouched.

Transport conserved and clean: `unmasks = deliveries = acks = rearms = 224 564`,
`audio=145 185`, `video=84 676/84 676`, `timeouts=0`, `busy=0`, `overflow=0`,
`uncertain=0`, `errors=0`, `transport_ok=1`. Stop `witness_target_reached` at
35.449 s against a 60 s cap. `FRAMECAP frames=2118 complete=2116 incomplete=2
resync=4 anomaly_region=2 blocks=84676`, `INTERVALS 1:1,34:1,40:2116` — the same
startup shape as every previous run, and the warm-up reconciliation is again
exact: `84 676 − 81 921 = 2 755 = 1 + 34 + 68×40`.

### GBP-HW-193 — source-frame continuity REPLICATED on a second runtime — FACT

The unmodified `tools/vindex.py` (unchanged since `10250a4`) returned
**`OBSERVED_CONTIGUOUS`** again, on a different build:

```text
records 2048 of 2048 · staged/placed 81921/81921 · out of range 0
stop GBP_VSTATE_STOP_WITNESS_TARGET · decisive-claim ready True
observed 0x000055 .. 0x000854 · decisive 2046 · OBSERVED_ID_CONTIGUOUS 2046
stimulus fault seen False · VERDICT OBSERVED_CONTIGUOUS
```

Independent decode, importing nothing from `tools/` and reproducing all ten
frozen CRC-8 vectors first: 2048/2048 record seals, header CRC `E82C47F0` and
global CRC `B2C145CE` both recomputed, frame_index 70..2117 strictly
consecutive, **81 920/81 920** valid symbols, SYNC, CRC-8 and BLOCK_INDEX,
`MIXED_BLOCK_IDS=0`, STATUS `0x18` everywhere (FAULT=0, VMARGIN=24), FRAME_ID
**85..2132** with all 2 047 adjacent deltas `+1`, and bit 15 set on 0 of
4 423 680 strip coordinates.

**Observed source cadence: 59.727083 Hz**, from first-block-to-first-block over
2 047 intervals (34.272 56 s).

GBP-HW-189 was established on `stream-0006` (run 4); this repeats it on
`stream-0007` with the trace instrumentation active. **The instrumentation did
not disturb the source result**, which is the first evidence on that question —
though one replication is not a general timing guarantee.

### GBP-HW-194 — the run-5 OGBPDISP1 container is intact — FACT

Recomputed independently of `tools/`, from the frozen layout:

```text
size 287 772 B · magic OGBPDISP · v1 · header 0x100 · life 96 B · event 40 B
identity  GBP-VIDEO-004 / stream-0007 / gbp-video-stream-probe / ddf8db6
life      2114 of 4096      events 2114 of 4096      decisions 2114
life_overflow 0   event_overflow 0   drawdone_unmatched 0
tb_hz 40 500 000 · tex_slots 2 · xfb_slots 2 · window_first_frame 69
header    CRC32 0x443DD4D6   MATCH
lifecycle CRC32 0xC4A9FCB3   MATCH
event     CRC32 0x0F23B179   MATCH
global    CRC32 0xB90822F4   MATCH
footer OGBPDEND · reserved bytes zero · geometry self-consistent
```

The official parser agrees and reports `intact, window_opened` with
`disposition-claim ready True`.

### GBP-HW-195 — the exact scientific disposition identity — FACT

Joined by the GENERIC `frame_index`, not by the `in_window` flag (see
GBP-VID-019 for why that distinction matters):

```text
OGBPIDX scientific source records      2048   frame_index 70..2117
  with a downstream lifecycle          2047   frame_index 70..2116
  SELECTED_NEW                         2030
  HOLD_PREVIOUS                          17
  no lifecycle at all                     1   frame 2117

identity      2030 + 17 + 1 = 2048
```

**Frame 2117 is a CAPTURE-EDGE residual, not interior loss**, and the trace
proves it rather than assuming it: it is the LAST source record, nothing after
it reached a terminal, and the queue's own `dropped_before_convert` — which
counts a publish landing on an untaken descriptor — is **0**.

Across the whole trace there are 19 `HOLD_PREVIOUS` at frame_index
61, 63, 334, 336, 345, 609, 620, 891, 893, 904, 1175, 1177, 1188, 1457, 1460,
1471, 1744, 2017, 2028. Two (61, 63) fall before the scientific window; **17**
are inside it.

### GBP-HW-196 — the machine state at every hold — FACT

All 17 scientific holds share the same recorded state, with no exception:

```text
reason                     XFB_BUSY on 17 of 17
xfb_target                 NONE (-1) on 17 of 17
xfb_current / xfb_pending  one is 0 and the other is 1, on 17 of 17
newest_source              NONE (0xffffffff) on 17 of 17
converted                  yes on 17 of 17
submitted                  yes on 17 of 17
a later DrawDone arrived    yes on 17 of 17
```

`newest_source` is NONE on **all 2 114 decisions in the run**, not only the
holds: at every decision the producer's mailbox was empty. **No hold can be
attributed to a queued backlog**, because at no decision in the entire run was
there anything queued.

### GBP-HW-197 — the stage order, and what it rules out — FACT

Measured from the lifecycle timestamps, and it corrects an ambiguity this
project introduced itself:

```text
DrawDone AFTER the XFB decision   2047 of 2047
DrawDone BEFORE the decision         0
order: convert → submit → XFB DECISION → asynchronous DrawDone
submit → decision     n=2047  164 / 224 / 308 ticks (min/p50/max)
decision → DrawDone   n=2047  3 159 / 3 285 / 5 099 ticks
```

**Saying a held frame was "already drawn" when the decision was taken is
FALSE.** §V5.46.6 and GBP-VID-017 used "drawn" that way and are corrected in
§V5.47.6. What is true, and is what the evidence supports: the frame reached the
submit/decision stage with no backlog, and its DrawDone completed normally
afterwards.

**H2 (conversion deadline miss) is NOT supported for these holds.** Conversion
cost is indistinguishable between the two populations:

```text
                 convert_ticks (mean)   wall span first→last slice (mean)
SELECTED (2030)      56 237  = 1.389 ms          7.777 ms
HOLD     (  17)      56 229  = 1.388 ms          7.636 ms
```

**H3 (GX deadline / back-pressure) is NOT supported as the immediate cause.**
`submit_refusals` is 0 across every scientific lifecycle, and the log reports
`no_texture=0`, `blocked_inflight=0`, `submit=2114/2114`, `drawdone=2114`,
`spurious=0`, `drawdone_unmatched=0`.

### GBP-HW-198 — the VI period, and the phase every hold falls in — FACT

The retrace count is a SAMPLED counter, so a span ratio is biased by the phase
difference between the first and last sample — it gives 675 531.65 ticks and
residuals wider than the period itself, which is how the error announces
itself. Estimating by FEASIBILITY instead — a period is admissible only if every
residual `t − P·retrace` fits inside one window of width `P`:

```text
admissible period   675 674.54 .. 675 676.22 ticks   (a 1.68-tick interval)
tightest fit        675 675.00 ticks = 16.683 33 ms = 59.940 06 Hz
```

which is NTSC nominal to five decimal places.

```text
decision phase inside the 16.683 33 ms interval
  SELECTED_NEW  n=2094   0.0000 .. 16.6680 ms   (the whole interval)
  HOLD          n=  19  16.1036 .. 16.6659 ms
```

**Every hold in the run falls in the final 0.580 ms — 3.48 % of the interval.**
Only 60 of 2 094 selected decisions (2.87 %) fall in that same band.

### GBP-HW-199 — a second decision inside one sampled retrace is always a hold — FACT

```text
decisions sharing a sampled retrace with their predecessor   16
  of which HOLD_PREVIOUS                                     16
  of which SELECTED_NEW                                       0
```

16 of the 19 holds (14 of the 17 scientific) are such second decisions. With two
framebuffers this is the DEFINED outcome and not a coincidence: the first
decision took the free buffer and handed it over, the VI had not yet latched it,
so the second found `current` and `pending` occupying both slots and
`xfb_target()` had nothing to return.

The remaining **3** holds are ones where the retrace had advanced. In all three
the previous frame's hand-over was requested very close to the next sampled
retrace — an upper bound of 15.31, 15.80 and 16.00 µs — and by the following
decision the pending buffer had still not become current. The retrace origin is
itself only pinned to a 15.4 µs window by sampled data, so the admissible range
for those figures is 0.4 .. 16.0 µs. **No latch deadline is claimed**; the
sampled counter cannot locate one.

### GBP-HW-200 — hold recurrence matches the source↔VI beat — CORROBORATED

```text
source cadence (this run)   59.727 083 Hz
VI cadence     (this run)   59.940 060 Hz
difference                   0.212 977 Hz
predicted beat period        4.6954 s = 280.44 source frames
```

Holds cluster, and the clusters recur. Grouping consecutive holds separated by
≤20 source decisions gives 8 clusters with centre-to-centre gaps of
276.3, 276.2, 281.5, 284.0, 282.7, 281.3, 278.5 — **mean 280.07 source frames,
which is 99.87 % of the predicted 280.44.**

Sensitivity, as required before the result is believed: the clustering is
**identical for thresholds 15, 20, 25 and 30** (8 clusters, the same gaps, mean
280.1) and fragments at threshold 10 into 13 clusters. The result is stable over
the range where a cluster is a cluster, and the threshold was fixed before the
gaps were computed.

**CORROBORATED, not FACT**: the agreement is between a predicted beat period and
an observed recurrence interval over seven gaps in one run. It is strong, it is
not a mechanism proof, and it is not evidence for any particular remedy.

### GBP-HW-201 — what this run does NOT establish — SCOPE

```text
- no cause is claimed for the 3 holds where the retrace advanced beyond the
  observation that the previous hand-over was recent;
- no latch deadline, no scanout transition time and no nanosecond boundary:
  VIDEO_GetRetraceCount() is sampled, and the origin is pinned only to 15.4 µs;
- `presented` remains stage B, VIDEO_SetNextFramebuffer(). Nothing here says a
  frame was physically displayed;
- one run. The beat agreement, the phase concentration and the
  instrumentation's harmlessness to the source result each rest on a single
  physical capture;
- nothing about which pacing or buffering policy is preferable. That is UNKNOWN
  and this round deliberately does not narrow it.
```

### GBP-VID-019 — three instrumentation semantics that need correcting, none of them changed here — FACT (software, from the source)

**1. `in_window` is one frame early at the leading edge.** The flag is
`gbp_vwitness_armed()` sampled at the moment the consumer TAKES a descriptor.
Within one service cycle the probe runs `gbp_vwitness_step()` (line 1445, which
arms at the block-0 boundary), then `gbp_vqueue_publish()` (1479), then
`gbp_vqueue_pump()` (1531). Frame 69 is therefore published and taken *after*
the witness has already armed, and is flagged in-window although it is not an
OGBPIDX record.

```text
OGBPIDX scientific window   70 .. 2117   2048 source records
OGBPDISP in_window flag     69 .. 2116   2048 lifecycles
```

Same count, shifted by one at both ends. The implementation matches its own
documented definition; what is wrong is that §V5.46.16 also said an analyzer may
select the scientific population with it.

**2. `tools/vdisp.py` inherits it.** `scientific()` filters on the flag, so the
official report says `SELECTED_NEW 2031` and `open 0` while the exact
`frame_index` join says `SELECTED_NEW 2030` and one capture-edge residual. Both
numbers appear in the same output, which is how it was found.

**3. the `drawn` column is ambiguous.** It reports `life_flags & F_DRAWDONE`,
which is set when the DrawDone eventually fires — always after the decision
(GBP-HW-197) — so it is `yes` on every row and says nothing about the state the
decision was taken in.

A fourth, smaller one: the log now emits **two different `STREAMDISP` lines**,
the pre-existing conservation identity and the new trace summary. A parser
keying on the tag alone would conflate them.

**None of these is changed in this round.** This is an evidence-ingestion
checkpoint, the semantics are frozen while a physical run is being interpreted,
and every number in GBP-HW-195 … GBP-HW-200 was computed from the exact
`frame_index` join rather than from the flag.

### GBP-VID-020 — source loss, display repeat and rate conversion are three different things — FACT (software, arithmetic on the physical run)

A correction to §V5.47.13, which said 59.727 Hz into 59.940 Hz "cannot be
lossless". If "lossless" means source frames, that is wrong.

```text
f_vi > f_src, so the display has MORE intervals than the source has frames.
run 5's scientific span: 2053 display intervals for 2047 source frames.
display repeats REQUIRED by the rate difference over that span:  7
interior source frames the current policy actually lost:        17
```

Every source frame can have its own display interval, in order, with intervals
left over; those leftovers must repeat the previous image. **Source-lossless is
achievable. Display repeats are not avoidable.** The 17 are not the 7 — they are
a scheduling outcome, not an arithmetic necessity.

```text
SOURCE LOSS      an interior source frame never gets an eligible hand-off
DISPLAY REPEAT   a display interval shows the previous image again
RATE CONVERSION  N source frames onto M display intervals, M > N
```

`STREAMCONS repeats` stands for both of the first two at once, which is how they
came to be confused: every hold is simultaneously one dropped frame and one
repeated interval.

### GBP-VID-021 — the VI hand-over model, fitted and exact — FACT (software, fitted to the physical run)

Two parameters, neither assumed:

```text
VI PERIOD (feasibility)   admissible 675675.00 .. 675676.00 ticks
                          best 675675.00 = 16.683333 ms = 59.940060 Hz
LATCH SETUP MARGIN        650 .. 877 ticks = 16.05 .. 21.65 us
```

With the margin the model reproduces **all 2114** recorded `(xfb_current,
xfb_pending)` pairs of run 5, and therefore every SELECTED/HOLD decision.
Without it exactly **three** disagree — the three holds where the sampled
retrace had advanced, which is how the margin was discovered: a hand-over issued
within roughly 16–22 µs of a boundary does not take effect at that boundary.

The retrace origin is itself pinned only to a 15.4 µs window by sampled data, so
the margin's absolute value inherits that uncertainty. What is exact is that a
NON-ZERO margin is required and that some value in that range reproduces
everything.

The source model is fitted on `frame_index`, never on the decision ordinal:
17 frames are missing from the decision sequence, and an ordinal fit folds them
into the slope and turns sub-millisecond jitter into a 33 ms artefact. Fitted
slope 678 083.8 ticks against the witness's 678 084.3 — 0.5 ticks apart.

### GBP-VID-022 — two-XFB deferral is source-lossless; a third framebuffer is not the answer — FACT (software, simulation)

Physical replay of run 5, 2047 scientific frames:

| policy | source drops | superseded | never displayed | display repeats | max queue | max latency |
| --- | --- | --- | --- | --- | --- | --- |
| baseline `stream-0007` | 17 | 0 | **17** | 24 | 0 | 0 |
| **A — defer, 2 XFB** | **0** | **0** | **0** | **7** | **1** | 1.264 ms |
| B — VI-paced | 0 | 0 | 0 | 7 | 1 | 4.171 ms |
| C — 3 XFB, hand over at once | 0 | **17** | **17** | 24 | 1 | 0 |
| D — cadence converter | 0 | 0 | 0 | 7 | 1 | 1.264 ms |

**The third framebuffer converts 17 drops into 17 SUPERSESSIONS.**
`VIDEO_SetNextFramebuffer` latches once per retrace however many buffers exist,
so a second hand-over before the boundary overwrites the first and that frame
never reaches the screen. A policy counting hand-offs rather than latches would
have reported it as a success; the simulator counts supersession as a
first-class outcome for that reason.

A, B and D converge: with an in-order queue and one deferred frame they are the
same scheduler with different triggers.

Robustness of A:

```text
1024 initial phases x 600 frames, observed jitter   0 drops, 0 superseded, maxQ 1
10 minutes / 35 836 frames / ~128 beat periods      0 drops, maxQ 1, no drift,
    display repeats 128 against a rate requirement of exactly 128
2x, 4x and a labelled 10x jitter stress             0 drops, maxQ 1
```

**Not a hardware claim.** It is a model that reproduces run 5 exactly and
predicts nothing until hardware says otherwise.

### GBP-VID-023 — the analyzer no longer substitutes the legacy flag — FACT (software)

`OGBPDISP1` bit 0 is `gbp_vwitness_armed()` at TAKE and is now named
`WITNESS_ARMED_AT_TAKE`. `tools/vdisp.py::scientific()` requires an
OGBPIDXCAP1 and performs the exact `frame_index` join; without one it raises
rather than falling back, because a caller with no witness must not be handed a
population that looks like one.

The report prints both, labelled, and the contradictory pair it used to emit
(2031 from the flag beside 2030 from the join) is gone. **No sidecar byte was
changed and run 5 is not reclassified**: 2030 SELECTED_NEW, 17 HOLD, 1 terminal
edge, exactly as GBP-HW-195 records.

**OGBPDISP2 is not proposed.** The format already carries what is needed; a
version bump to rename a bit would create a second competing definition of the
source window.

---

### GBP-VID-024 — with exactly two framebuffers, the presentation precheck cannot go stale — FACT (software, proof from the source)

`stream-0008` asks `gbp_vpresent_xfb_target()` **before** submitting to GX, so a
frame that cannot be presented consumes no token. That reordering is only sound
if the answer survives until it is used, and it does, by construction rather
than by timing:

```text
xfb_target() returns X only when X is neither `current` nor `pending`
  -> with GBP_VPRESENT_XFB_BUFFERS == 2 that forces xfb_pending == -1
  -> with nothing handed over, the VI has nothing to latch at the next retrace
  -> therefore a retrace cannot change `current` under the decision
```

The remaining ways the answer could change are enumerated and closed: no other
caller claims a stream framebuffer (`submit_ready()` is the only site), and the
single draw-done ISR touches textures only, never the framebuffer state. The
precheck is in fact **safer than the order it replaces**, which asked after the
submit and left a longer window between the question and the copy.

**Scope.** This is a statement about THIS code with exactly two framebuffers. It
does not generalise to three, and three is not proposed — see GBP-VID-022.

A mutation that re-reads the target after `gbp_vpresent_submit()` is refused by
a wiring pin that requires exactly one call site, because the first version of
that pin matched only the FIRST occurrence and would have let the second call in
(`HARDWARE_TESTS.md` §V5.49.13).

---

### GBP-VID-025 — OGBPDISP2 exists because DEFER is non-terminal, not to rename a bit — FACT (software, design)

GBP-VID-023 ended with "**OGBPDISP2 is not proposed.**" That statement was
correct on its own terms and is **not** withdrawn: it refused a version bump
whose only purpose was to rename `WITNESS_ARMED_AT_TAKE`, which would have
created a second competing definition of the source window. Nothing here renames
that bit, and the population is still the exact `frame_index` join.

The bump has a different cause. Policy A introduces a disposition that is
**non-terminal** — deferred now, handed off later — and v1 was built around one
decision per lifecycle. Expressing it in v1 would mean overloading
`HOLD_PREVIOUS_FRAME`, a word that already names 17 physically discarded frames
in run 5 (GBP-HW-195); reusing it would silently reinterpret an existing
capture. So v2 adds, rather than redefines:

```text
lifecycle 96 -> 128 B   t_first_attempt, t_first_defer, t_last_defer,
                        defer_attempts
dispositions            DEFERRED (non-terminal), TERMINAL_PENDING (edge)
header                  source_handoffs, source_deferred_frames,
                        source_defer_attempts, source_dropped_interior,
                        terminal_pending, max_deferred_depth, order_violations
events 4096 -> 8192     at most two events per frame, since defer attempts are
                        aggregated rather than evented
```

`tools/vdisp.py` reads both versions, and **a v1 file carrying a v2 disposition
is rejected rather than reinterpreted**. Run 5's sidecar keeps its meaning
unchanged.

The counters are also the round's vocabulary fix. One `repeats` counter used to
stand for several different things; SOURCE_DEFERRED, SOURCE_HANDED_OFF,
SOURCE_DROPPED, SOURCE_SUPERSEDED and TERMINAL_PENDING are now distinct, and
DISPLAY_REPEAT_INTERVAL is a property of the VI measured offline — not a lost
frame (GBP-VID-020).

**Not physically executed.** `stream-0008` is a candidate; `stream-0007` remains
the last runtime that ran on hardware.

---

### GBP-HW-202 — the run-6 artifacts, hashed here and matched against the card — FACT

Every identity below was computed in the repository, from the artifact, before
any value the operator reported was looked at. The operator's two figures are
DOUBLE CHECKS of the physical copies, never the source of the identity.

```text
stream-0008 DOL   build/poc/gbp-video-stream-probe/gbp-video-stream-probe.dol
                  492 416 B
                  a9efe181d46928d11a20623276a77f352db45b9795681173185e9a60d4e81282
Swiss boot.dol    build/swiss/12-stream/boot.dol
                  492 416 B, byte-identical to the DOL above
indexed-0003      canonical build/stimulus/agb-indexed/agb-indexed.gba
                  2 880 B  37119bb6ac68398dbd3fa75e6ad5c51c8aeb543277ac8d3b03b57f7a6f0caaca
                  delivery  build/physical/agb-indexed-cart.gba
                  2 880 B  9f04916b88308e7045f207136f5fc681e5bab33ac9b22d2e19be12c16b8d9cc2
run-6 log         66 968 B  89f54f35a1f614656ee67a12dc69494127f5e37b9544c3bb3391a4c0f093b843
run-6 OGBPIDXCAP1 8 946 060 B 311a26a78a19d8573b54fadb463dc50fd411984b97d8679287066e5de45a8d54
run-6 OGBPDISP2   357 524 B  36b684610b32219d9585126fba8abc4ee58e31de0a6d8044ccca4fb75803a44e
```

The operator's SD `boot.dol` and EZ-Flash `agb-indexed-cart.gba` hashes match the
DOL and the delivery ROM exactly. The log's own header carries
`build_id=stream-0008 commit=5126a19`, with no `-dirty` stamp, and both sidecars
repeat the same four identity strings internally.

Archived as `captures/local/GBP-VIDEO-004_stream-0008-run6{,-idxcap,-disp}.*`,
byte-identical to the raw drop in `logs/`, which was not modified.

---

### GBP-HW-203 — source-frame continuity replicates a THIRD time under a changed presentation policy — FACT

`tools/vindex.py`, unmodified, on the run-6 `OGBPIDXCAP1`:

```text
records              2048 of 2048 (target 2048), 0 discarded
blocks staged/placed 81 921 / 81 921, out of range 0
all-40-block frames  2048
first/last observed  FRAME_ID 0x000055 .. 0x000854   (85 .. 2132)
decisive transitions 2046, every one OBSERVED_ID_CONTIGUOUS
header/total CRC-32  2941a236 / f0ae62a7
VERDICT              OBSERVED_CONTIGUOUS
```

An independent byte-level decode — own record iteration and own sequence
analysis, using only `istim` for the frozen symbol/CRC-8 contract — agrees on
every quantity: 2048/2048 record seals valid, header and global CRC valid,
81 920/81 920 valid symbols with SYNC `0xB2`, valid CRC-8 and
`BLOCK_INDEX == slot`, `MIXED_BLOCK_IDS` 0, `STATUS 0x18` in all 81 920,
`FAULT` 0, `VMARGIN` 24, `frame_index` 70..2117 strictly +1, `FRAME_ID`
85..2132 with 2048 unique values and adjacent delta +1 in 2047 of 2047 — no
duplicate, no gap, no reorder.

Source cadence, first-to-first over 2047 intervals: **59.727084 Hz**.

This matters because the policy under test sits DOWNSTREAM of the source layer.
Run 6 changed how frames are presented and changed nothing about how they are
captured, and the source result is unchanged — which is what makes run 5 and
run 6 comparable at all.

---

### GBP-HW-204 — the first physical OGBPDISP2 is structurally perfect — FACT

Independently recomputed from the frozen v2 writer rules:

```text
magic/version/header   OGBPDISP / 2 / 0x140 (320 B)
records                lifecycle 128 B, event 40 B
lifecycles             2114 of 4096      events 2165 of 8192
decisions              2114
flags                  0x0011 = INTACT | WINDOW_OPENED
overflow / unmatched   life 0, event 0, drawdone 0, order_violations 0
header   CRC-32        ec3c150e   recomputed ec3c150e
lifecycle CRC-32       5e815e8b   recomputed 5e815e8b
event    CRC-32        38e01a34   recomputed 38e01a34
footer OGBPDEND, global CRC-32 dd4e7781, recomputed dd4e7781
size identity          320 + 2114*128 + 2165*40 + 12 = 357 524 = total_size = file
reserved 0x108..0x13B  all zero
```

**The v2 event identity holds: `decisions 2114 + deferred_frames 51 = 2165 =
event_n`.** The v1 identity (`decisions == event_n`) is FALSE here, which is
correct and expected — see GBP-VID-026 for the analyzer defect that fact exposed.

---

### GBP-HW-205 — every interior source frame the consumer was offered reached a framebuffer — FACT

The join is the exact `frame_index` equality between the `OGBPIDXCAP1`
scientific population and the `OGBPDISP2` lifecycles. The armed bit is NOT used
(GBP-VID-019).

```text
source scientific records           2048   frame_index 70..2117
with a lifecycle                    2047   frame_index 70..2116
without a lifecycle                    1   [2117], the target-stop edge
identity                            2048 = 2047 + 1

disposition of all 2047             SELECTED_NEW  2047
                                    everything else 0
```

Nothing was HOLD_PREVIOUS, SLOT_OVERRUN, ABANDONED_NO_RAW, still DEFERRED, or
OPEN. `terminal_pending = 0`: no frame was alive and un-handed-off at the stop.

Frame 2117 is a **capture-edge residual, not a loss**: the source layer published
2114 descriptors and the consumer took 2113 (`STREAMSRC published=2114` vs
`STREAMCONS taken=2113`), because the run stopped on the witness target before
the last descriptor was offered. No disposition decision was ever made about it,
so no policy can have lost it.

---

### GBP-HW-206 — the order was preserved, and the sequence was rebuilt to prove it — FACT

`order_violations = 0` is the counter; this is the reconstruction. Sorting the
2047 successful hand-offs by `t_decision` gives

```text
70, 71, 72, ... , 2114, 2115, 2116
```

exactly, with no duplicate hand-off, no skip inside the span, and no frame
handed off twice. For each of the 48 frames that deferred, no frame with a
LOWER index appears after it in the sequence.

This was the specific risk found before the run: `gbp_vpresent_acquire()` hands
out the lowest FREE texture and the old retry loop scanned from slot 0, so a
newer frame in a lower slot could have overtaken a deferred older one. The
age-ordered offer was built for exactly this, and the hardware shows it holding.

**Supersessions: 0.** Each `frame_index` appears on exactly one lifecycle and
each lifecycle reaches at most one hand-off, so no frame was replaced by a newer
one while waiting.

---

### GBP-HW-207 — the physical deferral population, and what the counter that used to mean "lost" now means — FACT

```text
whole trace      deferred_frames 51   defer_attempts 129
                 = 48 scientific + 3 warm-up + 0 self-test
scientific       48 frames deferred over 124 attempts
attempts/frame   1:13  2:12  3:11  4:7  5:4  6:1
every one        eventually handed off, in order
reason           XFB_BUSY on every defer event, xfb_target -1 on every one
events           51 defer events, exactly one per deferred frame (aggregated)
```

**Every single deferral resolved on the very next retrace**: for all 48
scientific deferred frames, `retrace_decision == retrace(first defer event) + 1`,
without exception. The frame was held back because both framebuffers were spoken
for, and the next retrace freed exactly one.

**`xfb_skipped` changed meaning, and the run proves it numerically.**
`gbp_vpresent_xfb_target()` increments `xfb_skipped_busy` on one branch — both
framebuffers spoken for — and `submit_ready()` calls it once per offer.

```text
stream-0007   STREAMGX xfb_skipped 17   ==  17 frames TERMINALLY discarded
stream-0008   STREAMGX xfb_skipped 129  ==  129 DEFER ATTEMPTS (DISPSRC), all resolved
              STREAMCONS repeats 0, DISPSRC dropped_interior 0
```

The same counter, the same branch, the opposite consequence. It must never be
read across the two builds as if it meant one thing.

---

### GBP-HW-208 — the deferral queue never held more than one frame — FACT

`max_deferred_depth = 1` over the whole run, matching the offline model's
prediction for two framebuffers exactly. The deepest observed retry count is 6
attempts on one frame (`frame_index 612`), and even there only that one frame
was waiting.

---

### GBP-HW-209 — both pre-registered latency gates pass, with the definition fixed before the run — FACT

`ready` is `t_convert_done` (the frame becomes READY), `hand-off` is
`t_decision`, the population is EVERY scientific hand-off, and the percentile
convention is `tools/vpace.py`'s `s[min(n-1, int(n*q))]`. All four were frozen
in §V5.49.15 before the cartridge was powered on.

```text
gate population, n = 2047
  min 0.0008   p50 0.0014   p95 0.0016   p99 0.4946   max 1.1353 ms   mean 0.0123

  PRE-REGISTERED   p99 <= 1.0 ms    observed 0.4946   PASS (49.5 % of budget)
                   max <= 2.5 ms    observed 1.1353   PASS (45.4 % of budget)

breakdown, reported and NOT the gate population
  never deferred, n = 1999   max 0.0027 ms
  deferred only,  n =   48   min 0.0864  p50 0.4774  p99 1.1353  max 1.1353 ms
```

The observed maximum, 1.1353 ms, is BELOW the model's own physical-replay worst
case of 1.264 ms and well below the 1.422 ms sweep maximum the 2.5 ms bound was
derived from. The undeferred path costs under 3 µs.

---

### GBP-HW-210 — seven repeated display intervals, which is what this run's own rates require — FACT

Computed separately from source disposition, as the frozen rule demands.

```text
adjacent scientific hand-off transitions   2046
retrace-count delta histogram              {1: 2039, 2: 7}
VI intervals consumed                      2053
DISPLAY_REPEAT_INTERVALS                   7
SOURCE_DROPPED                             0
```

The VI period was re-derived from THIS run by the feasibility estimator, not
reused from run 5: the admissible range collapses to a single point,
**675 675.00 ticks = 16.683333 ms = 59.940060 Hz**. The span-ratio estimator
gives 675 771.82 with a residual spread of 830 612 ticks, wider than its own
period — INFEASIBLE, replicating the §V5.48 rejection.

Rate conservation over the hand-off span of 34.255791 s, with this run's own
source cadence of 59.727125 Hz:

```text
VI intervals required   2053.294
source transitions      2046
rate-required extras    7.294   ->  integer bracket [7, 8]
observed extras         7       ->  WITHIN the same-run requirement
```

A repeated interval is the VI showing one framebuffer for one extra period. It
is not a lost frame, and this run separates the two for the first time
physically: 7 repeats beside 0 drops.

---

### GBP-HW-211 — the causal comparison: the repeats fell by exactly the frames that are no longer discarded — FACT

Same stimulus, same cartridge, same qualification, same VI, same span. One
policy changed.

```text
                                   stream-0007 (run 5)   stream-0008 (run 6)
source verdict                     OBSERVED_CONTIGUOUS   OBSERVED_CONTIGUOUS
consumer-overlap scientific frames 2047                  2047
successful hand-offs               2030                  2047
source frames lost downstream      17                    0
max deferred depth                 0 (no deferral)       1
VI period (re-derived per run)     675675.00 ticks       675675.00 ticks
hand-off span                      34.255790 s           34.255791 s
VI intervals consumed              2053                  2053
retrace delta histogram            {1:2007, 2:20, 3:2}   {1:2039, 2:7}
DISPLAY_REPEAT_INTERVALS           24                    7
rate-required extras (same run)    24.294 -> [24,25]     7.294 -> [7,8]
observed within requirement        yes                   yes
```

**The VI consumed exactly 2053 intervals in both runs**, over spans that differ
by one microsecond. The display had to fill the same amount of time either way;
what changed is what filled it.

```text
run 5:  2029 transitions + 24 extras = 2053
run 6:  2046 transitions +  7 extras = 2053
        24 - 7 = 17 = exactly the interior source frames run 5 discarded
```

Every frame run 5 threw away forced the display to repeat once. Policy A stopped
throwing them away, and the repeats fell to the 7 that rate conversion alone
requires. That identity is the experiment.

---

### GBP-HW-212 — what run 6 does NOT establish — SCOPE

- **Not physical scanout.** `VIDEO_SetNextFramebuffer()` is a hand-over to the
  VI. A successful hand-off is not a proof that the frame was scanned out, and
  "display repeat" remains an ESTIMATE under sampled VI semantics.
- **Not universal losslessness.** One run, 34.26 s, one stimulus, one
  cartridge, one console, one qualified window of 2047 consumer-reached frames.
  It says nothing about other content, longer durations or other phase offsets.
- **Not a claim about frame 2117** or anything outside 70..2116.
- **Not pixel fidelity**, which no part of this round measured.
- **Nothing about what the AGB displayed before the handler existed** — the
  probe reads no VIDEO before that point (see GBP-VID-027).
- The 0 supersessions result is a property of two framebuffers. A third would
  reintroduce them (GBP-VID-022), and a third is still not proposed.

---

### GBP-VID-026 — the v2 analyzer carried the v1 readiness rule, and the first physical Policy-A trace exposed it — FACT (software)

`tools/vdisp.py` contained two versions of one identity, eleven lines apart:

```text
parse()   i["decisions"] + i["source_deferred_frames"] != i["event_n"]   (v2, correct)
usable()  info["decisions"] != info["event_n"]                           (v1, stale)
```

`parse()`'s form is the one the C parser enforces and the one
`gbp_vdisp_intact()` uses in the runtime. `usable()` was never updated when
OGBPDISP2 was introduced, so the run-6 trace — structurally perfect, all four
CRCs valid, flagged INTACT by the console that wrote it — was reported
`disposition-claim ready False` with the reason "decisions 2114 but only 2165
events stored", a sentence that is arithmetically backwards.

**Under v1 the two forms coincide**, because a v1 trace has no deferrals. That
is precisely why it survived review: the defect is invisible until a frame
defers, and no v1 frame ever did.

A second defect in the same report: the title was the literal string
`OGBPDISP1` whatever the file's version, so a v2 trace was printed under the v1
name.

Both are **analyzer-only**. No sidecar byte, no runtime behaviour and no
physical result depended on either, and run 5 re-parses unchanged — still
`OGBPDISP1`, still ready, still 2030 SELECTED_NEW and 17 HOLD_PREVIOUS. Fixed
under §V5.50 with regressions that state the rule in the dangerous direction
and pin the two call sites as being the same rule.

**Also recorded, not fixed this round** (out of scope, no functional change
authorised):

- `usable()` does not test `order_violations`, so a trace with a reordering
  could still be called usable for a disposition claim. It did not affect run 6,
  where `order_violations = 0` both by counter and by reconstruction.
- `src/gbp/gbp_vqueue.h` still declares `gbp_vqueue_note_repeat()` and carries a
  comment asserting `repeats = xfb_skipped`. Policy A removed the call from the
  runtime, and under stream-0008 that coupling is FALSE (repeats 0, xfb_skipped
  129). The comment is accurate history and misleading as a current invariant.

---

### GBP-VID-027 — the rainbow/checkerboard is the synthetic self-test, and the AGB boots inside the masked wait — FACT (software and source, with physical timing)

**OPERATOR OBSERVATION (run 6).** "The rainbow/checkerboard is still visible
during startup; expected perhaps to see the Game Boy boot/logo by now."

**The pattern is identified from source, not guessed.** `display_selftest()`
builds every pixel as

```c
w = ((x >> 3) << 10) | ((y >> 3) << 5) | ((x ^ y) & 0x1F)
```

and `gbp_vpix` places R in bits 14-10, G in 9-5, B in 4-0. So R is a horizontal
ramp in 8-pixel steps, G a vertical ramp in 8-pixel steps, and B is an XOR
producing a nested checkerboard of 32-pixel period. Rendering it reproduces a
rainbow gradient overlaid with a checkerboard — the operator's description
exactly. It is a coordinate gradient by construction and **knows no stimulus
value**, which is why it cannot teach the runtime what the experiment is looking
for (§V3.11).

**FACT: the visible checkerboard is diagnostic GameCube-side output, never Game
Boy source video.**

**Startup chronology, from the run-6 log (t = 0 at the CLOCKS epoch):**

```text
-0.0235 s  self-test takes, converts and HANDS OFF the synthetic frame
+0.1074 s  PREHANDLERWAIT begins  -- CONTROL = 0x8e, the AGB is RUNNING,
                                     PI masked, no handler, nothing serviced
+5.1074 s  PREHANDLERWAIT ends    -- CONTROL = 0x8e, unchanged
+5.1079 s  capture_start
+5.1464 s  first real source frame taken (frame_index 2)
+5.1542 s  first real frame handed off  <- the checkerboard is replaced HERE
+6.2849 s  qualification window opens (frame_index 70)
```

The synthetic pattern is the only thing in the stream framebuffers for
**5.1777 s**, and 5.000 s of that — 96.6 % — is the diagnostic wait.

**The cartridge is executing throughout.** `gbp_vstate_probe.c` states it at the
wait: "Stage A has put CONTROL in the running shape, so the AGB is executing; PI
is still masked and NO handler exists". The physical log corroborates:
`PREHANDLERWAITSTATE control_pre=8e control_post=8e`.

**Why no boot logo is captured — answered by an experiment already in the repo.**
GBP-VIDEO-002 (`vstate-0001`), with no pre-handler wait, saw the structured
screen appear **0.5014 s after capture start**, animate for about three seconds
and settle (GBP-HW-074…087). The control run `vstate-prewait-5000`, with the
SAME 5000 ms wait, reported `BASELINE valid=1 frames_seen=3 frame_index=4` and
`STRUCTURED status=not_observed` over 10 446 frames and 174.892 s: with the wait
in place the screen is already static when capture opens. The animation happens
entirely inside the masked wait, and the wait exists for exactly that reason —
§V3.26 records that without it "the colour capture would certify inside the AGB's
boot".

Run 6 is the same situation with a Game Pak: by `capture_start` the stimulus ROM
is already running and producing indexed frames.

**INFERENCE, not fact** — `tools/vindex.py` excludes frames below the window as
`leading_edge`, "AGB frames before id 0x000055 are unobservable". Within the
observed range `FRAME_ID = frame_index + 15` exactly (2047/2047 deltas of +1).
Extrapolating that cadence below the window, `frame_index 2` would carry
`FRAME_ID ~17`, i.e. about 0.28 s of stimulus output, leaving roughly 4.75 s of
the 5.04 s between "AGB running" and "first captured frame" for the GBA boot
sequence and the cartridge's own initialisation. This is offered as arithmetic,
not as an observation.

**Nothing here is a new physical machine observation beyond what the operator
reported.** The probe reads no VIDEO before the handler exists, so this round
makes no claim about what the AGB actually displayed during the wait.

---

### GBP-VID-028 — the diagnostic startup is separable from the normal one, and neither half of it is a protocol requirement — FACT (software and design)

**No hardware ran for this entry.** It is a claim about the code and about
experiments already recorded, not a new machine observation.

`stream-0008` showed the operator a synthetic pattern for 5.1777 s. Two
independent causes, and the source classifies both:

```text
the visible image   display_selftest() -> submit_ready(buf, 0) ->
                    VIDEO_SetNextFramebuffer(xfb_stream_buf[x])   (GBP-VID-027)
the 5.000 s         cfg.prehandler_wait_ms, whose module default is ZERO:
                    gbp_vstate_probe.c:50
                    "the diagnostic is OFF unless a build asks for it"
```

**Neither is required by the protocol.** The mandatory prefix before the first
VIDEO read is DET probes, the CONTROL transform, the self-terminating A1 and A2
windows, the handler install, the PREUNMASK safety check and the first unmask.
`stream-0009` removes the two diagnostic items and **moves nothing** in that
prefix.

The evidence that the wait is what hides the boot was already physical and
needed no new run: `vstate-0001` (no wait) saw the structured screen 0.5014 s
after capture start and captured the animated GAME BOY logotype
(GBP-HW-074…087); `vstate-prewait-5000` (the same 5000 ms) reported
`STRUCTURED not_observed` over 10 446 frames. §V3.26 records why the wait was
introduced — without it "the colour capture would certify inside the AGB's
boot" — which is a requirement of a MEASUREMENT, not of the runtime.

**The separation.** `src/gbp/gbp_startup.h` resolves one profile from one enum,
once. NORMAL: headless self-test, zero wait, framebuffers cleared to black.
DIAGNOSTIC: visible self-test, the 5000 ms GBP-HW-120 validated, same clear. An
unknown mode resolves to NORMAL, so a typo costs a diagnostic, never a user.

**The self-test still runs in both profiles**, because it validates the path
`stream-0001` shipped without ever executing (§V5.26.4). In the normal profile
it claims NO framebuffer, rather than merely skipping the present:
`gbp_vpresent_xfb_handed()` sets `xfb_pending`, which clears only when the VI is
observed to have latched that buffer, so bookkeeping without a buffer would
leave it set and — with two framebuffers — make every real frame defer for the
whole run. Dolphin measures the difference directly: `SELFTEST … xfb=0` in
normal mode against `xfb=1` in diagnostic, with `submits=1 drawdone=1
releases=1` in both.

**Policy A is untouched, not merely unchanged.** `selftest_submit_headless()`
calls nothing in `submit_ready()`, `submit_ready()` contains no reference to the
profile, and `gbp_vdisp.*`, `gbp_vdispdump.*`, `gbp_vpresent.*`, `gbp_vqueue.c`,
`gbp_vstate.*`, `gbp_vwitness*`, `gbp_vidxdump.c`, `gbp_vpix.c` and the stimulus
are byte-identical. The §V5.50 physical result is not reinterpreted by anything
here.

**Predicted, not measured:** with the wait removed, run 6's own stage timings
put the first real hand-off **0.1532 s** after the CONTROL transform. The frozen
gate is 400 ms, derived by letting the dominant self-terminating term (the A2
window, 105.773 ms in run 6, which ended early) more than double.

**A discrepancy recorded rather than resolved:** `UNKNOWNS.md` phrases the
logotype's first appearance as 0.5014 s "after capture start" and `ROADMAP.md`
as "after the AGB starts"; those differ by the ~0.107 s prefix. The 400 ms gate
holds under either reading, and the run's own `STARTUPV` line will settle it.

**Not claimed:** that a boot logo will appear — that depends on the cartridge;
that anything was seen on a screen — `xfb=0` is instrumentation; that the F8
auditor blind spot is fixed — one build was inspected by hand.

---

### GBP-VID-029 — two analyzer and documentation semantics corrected after the Policy-A run — FACT (software)

**A reordering is not a warning.** `tools/vdisp.py::usable()` tested lifecycle
overflow, event overflow and unmatched draw-done tokens, but not
`order_violations`. The disposition claim this function gates is "every interior
source frame reached a framebuffer **in order**", so a trace that recorded an
out-of-order hand-off could not support it whatever else was clean. `parse()`
already refused such a file when it ALSO set INTACT; `usable()` now refuses the
CLAIM even when the flag is honestly clear. Every existing capture carries 0
here, so `stream-0007` and `stream-0008` are not reclassified.

**`repeats = xfb_skipped` is history, not an invariant.** `gbp_vqueue.h`
asserted the coupling as current, and the physical measurement behind it is
real: up to `stream-0007` that state was reachable and a run confirmed
`repeats = 12 = xfb_skipped` from one branch of `submit_ready()`. Policy A makes
the equality FALSE and the caller unreachable:

```text
stream-0007   xfb_skipped 17   = 17 frames TERMINALLY discarded
stream-0008   xfb_skipped 129  = 129 DEFER ATTEMPTS, every one resolved
                                 (repeats 0, dropped_interior 0) — GBP-HW-207
```

The measurement stays in the header as labelled history; the claim that it still
holds does not. **No counter and no behaviour changed** — the function is kept
so existing captures keep their meaning, and a wiring test asserts the runtime
does not call it.

---

### GBP-HW-213 — the run-7 artifacts, hashed here first — FACT

Computed from the repository before any operator figure was read:
`stream-0009` DOL 494 176 B `4d0337bb…c955` (rebuilt from `59d2f57` at HEAD
`ee2e0f1`, hash reproduced), Swiss `boot.dol` byte-identical, `indexed-0003`
canonical `37119bb6…caaca` and delivery `9f04916b…8d9cc2` (2 880 B each), run-7
log 86 051 B `424ff1e2…352e`, OGBPIDXCAP1 8 946 060 B `1e502bc8…02e9`, OGBPDISP2
379 340 B `edf38428…ce45`. The log header carries `build_id=stream-0009
commit=59d2f57` with no `-dirty`. **No physical-media double check was supplied
for this run: PENDING, not assumed.** Archived under run-7 names in
`captures/local/`, byte-identical to the untouched raw drop.

---

### GBP-HW-214 — the NORMAL startup profile ran on hardware, and nothing synthetic was handed to the video interface — FACT

`STARTUP mode=normal selftest_run=1 selftest_visible=0 prehandler_wait_ms=0
clear_fb=1 normal_clean=1 presented_synthetic=0 headless_submits=1`, and
`STREAMSELFTEST ok=1 converted=1 released=1 own_presents=0`. The self-test
EXECUTED — converted, drawn, token released in 12.219 ms — and was NOT SHOWN:
its lifecycle ends TERMINAL_PENDING with `F_SELFTEST`, never `SELECTED_NEW`.
These are two facts and both are in the machine trace. No `PREHANDLERWAIT` line
exists in the log, which is what the probe's source promises when the wait is
zero. `VIDEO_SetNextFramebuffer` is a hand-over; nothing here calls it scanout.

---

### GBP-HW-215 — first real hand-off 165.154 ms after the CONTROL transform; the 400 ms gate passes — FACT

`ticks_control_to_first_handoff=6688749` at 40 500 000 Hz = **0.165154296 s**.
Program entry to first real hand-off 211.120 ms; CONTROL to capture_start
107.663 ms; capture_start to first hand-off 57.491 ms; first frame was
`frame_index 2`. §V5.52.15 predicted 153.2 ms from run 6's stage timings.
Eight of eight pre-registered startup gates passed (§V5.53.2), none of them
dependent on when the stimulus began.

---

### GBP-HW-216 — the boot's structural transient was captured, and its early episodes match the physically identified logotype sequence descriptor for descriptor — CORROBORATED

With capture open 0.154 s after CONTROL, run 7 recorded 13 incomplete frames,
26 resyncs, 13 anomaly regions and 43 structured episodes in the first
seconds, where run 6 (capture at 5.107 s) recorded 2, 4, 2 and none — not a
regression, the boot being seen for the first time. Of the four preserved
episodes, episodes 1 and 2 (frames 30..89 and 90..149, 60 frames each, flags
`0006`, `sig0 00000000`, followed by `7f0fff10` at frame 150) are **identical in
open frame, close frame, length, flags and signature** to `vstate-0001`'s first
two episodes — the run whose raw frames reconstructed to "a legible animated
GAME BOY logotype" (GBP-HW-074…087). After frame 189 they diverge, as a run with
a cartridge must. **CORROBORATED, not FACT:** the stream sidecars carry no raw
episode pixels, so visual identity is established by equivalence, and the
operator's observation for this run was not supplied.

---

### GBP-HW-217 — Policy A was clean over the whole run and over the frozen join — FACT

Total run: 2244 hand-offs, `frame_index` 2..2269, strictly increasing, no
duplicate; 44 deferred over 108 attempts, every one resolved on the very next
retrace, max depth 1, none overtaken; interior drops 0; p99 0.4591 ms, max
1.0005 ms. The 24 indices absent from the sequence all have NO lifecycle — the
source layer never published them (13 incomplete + 13 anomaly, minus frames 0
and 1), all in the boot, none inside the join. `xfb_skipped = 108 =
defer_attempts` (GBP-HW-207). Over the analyzer's frozen join (source records
223..2270): 2047 SELECTED_NEW, 1 TERMINAL_PENDING (frame 2270, the last taken),
p99 0.4360 ms, max 1.0005 ms, retrace deltas `{1: 2039, 2: 7}` — **7 display
repeats beside 0 source drops, the same seven as run 6.** OGBPDISP2 CRCs
`ec80c5c7 / a56cccca / 1526984e / a896dafb` recomputed and matched;
`2244 + 44 = 2288 = event_n`. Recorded, not fixed: the log's `DISPSRC
terminal_pending=0` is printed before `gbp_vdisp_finish()`, the header's 2
after; both are true.

---

### GBP-HW-218 — the frozen source analyzer's verdict for run 7, verbatim — FACT

`tools/vindex.py`, unmodified at `ee2e0f1`: **`VERDICT OBSERVED_CONTIGUOUS`**
with `observed frames 2048 (intact 1988)`, `INVALID_CANONICAL_STRIP 60`,
`OBSERVED_ID_CONTIGUOUS 1986`, first/last observed `0x000000..0x0007c3`,
decisive `0x000000..0x0007c2`, `header/total CRC-32 52e3e27d / de0d3cf9`,
`decisive-claim ready True`. **This is the run's official source verdict, with
its composition, and nothing else is written in its place.** The analyzer's own
rule forms the decisive population from intact frames and reports the invalid
strips beside it; it was not changed to make this run read differently.

---

### GBP-HW-219 — retained records 0..59 hold AGB startup content with no OGBPIDX framing — FACT

Independent decode, own record iteration and seals, `istim` only for the frozen
symbol/CRC-8 contract: container header CRC `52e3e27d` and global `de0d3cf9`
recomputed and matched, 2048/2048 seals, reserved zero, `frame_index` 223..2270
strictly +1. **Records 0..59: 0 valid canonical blocks of 2400** — 2218 fail
SYNC, 182 fail the ZERO/ONE symbol test. Record 60 (`frame_index 283`) is the
first with 40/40 valid blocks: **FRAME_ID 0, STATUS 0x7F**; record 61 FRAME_ID 1,
STATUS 0x7F; record 62 FRAME_ID 2, STATUS 0x18. The retained window therefore
begins with 60 frames of whatever the AGB was showing before the stimulus ROM
rendered anything, then the ROM's own two initialisation frames.

---

### GBP-HW-220 — the 1986-record tail is contiguous, and is a diagnostic, not the verdict — FACT

Records 62..2047: 1986 records, FRAME_ID 2..1987, 1985 adjacent deltas of +1,
STATUS 0x18 in every block, one FRAME_ID per record, `BLOCK_INDEX == slot` in
all 79 440, cadence 59.727200 Hz. **This explains why the decisive population is
what it is. It is not promoted to a verdict, is not written as
`OBSERVED_CONTIGUOUS` for a trimmed window, and no window was trimmed.**

---

### GBP-HW-221 — the structural scientific window opened 1.0045 s before the stimulus, and the stimulus enters 4.845 s after CONTROL in every indexed run — FACT

Run 7, measured: first retained record 3.84047 s after CONTROL; FRAME_ID 0 at
4.84498 s; first STATUS 0x18 at 4.87846 s. Runs 4, 5 and 6 (each with the
5000 ms wait): window at 6.2681 s, record 0 carrying FRAME_ID 85, hence ID 0
**inferred** at 4.8450 s by `leading_edge` extrapolation — within 20 µs of run
7's direct measurement, which validates the extrapolation. The cartridge's own
boot and initialisation is the invariant; the wait only pushed the window past
it (to 1.42 s after ID 0), and removing the wait let the content-blind
qualifier succeed on the boot's clean frames 1.00 s before it. **A coupling
between normal-startup UX and research-window orchestration; not a defect in
the qualifier, the assembler, the transport or Policy A**, all of which the
same run shows clean.

---

### GBP-HW-222 — what run 7 does NOT establish — SCOPE

No operator visual observation; no pixel-level logo identity; no new
GBP-VIDEO-004 continuity claim for a normal-startup build until a run with a
valid steady-state window exists; no physical-media double check (PENDING); no
claim about other cartridges or consoles (the 4.845 s is this cartridge on this
console, four times); no scanout claim; nothing about the 5.000 s not-before
gate, which is analysed in §V5.53.12 and not implemented.

---

### GBP-VID-030 — research-window orchestration for early-video builds: a not-before gate on the STRUCTURAL streak, content-blind, 5.000 s after CONTROL — DESIGN (not implemented)

Transport, assembler, conversion, Policy A and hand-off run from capture_start
exactly as `stream-0009` does; only the 64-frame structural qualification
streak is not COUNTED until `T_gate` after the CONTROL transform, then counts
from zero, opens the window at the next block-0 boundary, retains 2048 records
and never resets — the §V5.44 method with a deferred start and nothing else
changed. `T_gate = 5.000 s` is chosen from the whole history, not fitted to
4.878 s: ID 0 at 4.845 s in four of four runs, STATUS 0x18 two frames later,
runs 4–6 decisive with windows at 6.27 s; the gate yields an earliest window at
≈6.07 s, inside that known-good regime and comparable with it, with the
existing 60 s cap unchanged. It guarantees nothing about another cartridge and
does not replace `vindex.py` as the decisive offline check. Rejected as window
solutions: any sleep, `PREHANDLERWAIT`, any `VIDEO_WaitVSync` loop, any
transport suppression — all delay what the user sees. Startup transients remain
in the log because nothing upstream of the witness is touched. **A final normal
runtime needs none of this: it is laboratory instrumentation.** Not authorised
in this round; recorded so the next one starts from evidence.

---

### GBP-HW-223 — the run-8 artifacts (GBP-VIDEO-005, run B), hashed here first — FACT

Log 86 192 B `8768d1e6…193f`, OGBPIDXCAP1 8 946 060 B `d93d7781…2202`, OGBPDISP2
379 300 B `2edadb49…5a34`, all recomputed in the repository before the operator's
figures were read, and matching them. The binary was `stream-0009` at `59d2f57`,
494 176 B `4d0337bb…c955`, verified before the run and not rebuilt; the embedded
id stays `GBP-VIDEO-004` by design. The drop reused run 7's file names and
**overwrote run 7's raw copies in `logs/`**; run 7 is intact in `captures/local/`.
Run 8 archived as `captures/local/GBP-VIDEO-005_stream-0009-run8*`. Media double
check: PENDING.

---

### GBP-HW-224 — the NORMAL startup repeated on a retail cartridge: no synthetic hand-off, no wait, first real hand-off 164.696 ms after CONTROL — FACT

`STARTUP mode=normal presented_synthetic=0 headless_submits=1`, no
`PREHANDLERWAIT` line, `STREAMSELFTEST own_presents=0`, self-test lifecycle
TERMINAL_PENDING with `F_SELFTEST`. `ticks_control_to_first_handoff=6670174` =
**164.695654 ms**, against run 7's 165.154 ms: +0.459 ms on a different
cartridge. Program → first hand-off 210.664 ms, CONTROL → capture 107.203 ms,
capture → first hand-off 57.493 ms, headless self-test 12.218 ms. Eight of eight
pre-registered machine gates, second time. `VIDEO_SetNextFramebuffer` is a
hand-over, not scanout.

---

### GBP-HW-225 — Policy A and the transport are clean on retail content — FACT

240 754 = 240 754 = 240 754, `timeouts 0 busy 0 errors 0`. OGBPDISP2
`c4e03fd8 / 3e079124 / e51713ee / 3b796f07` recomputed; `2244 + 43 = 2287`.
2244 hand-offs in strict order, no duplicate; 43 deferred over 97 attempts, every
one resolved on the next retrace, depth 1, `xfb_skipped 97 = defer_attempts`,
p99 0.3341 ms, max 1.0030 ms, 0 interior drops. Over the frozen join 223..2270:
**7 display repeats beside 0 drops — the third consecutive run with exactly
seven** (runs 6, 7, 8). The retail witness was validated as a container only
(header `a550891d`, global `fd2a435e`, 2048/2048 seals) and **no strip was
decoded and no OGBPIDX verdict exists for it.**

---

### GBP-HW-226 — the structural startup transient is the same on two different cartridges — FACT

`FRAMECAP 2271 / 2258 / 13 / 26 / 13`, `WITQUAL resets 12, warmup 223,
disqualified 26, qualify_frame 222, first_record_frame 223`, and the four
preserved episodes 8..25 / 30..89 / 90..149 / 150..197 with flags
0005/0006/0006/0005 and `sig0 7f0fff10 / 00000000 / 00000000 / 7f0fff10` are
**identical between run 7 (indexed-0003) and run 8 (retail)**, and episodes 1–2
identical to `vstate-0001` (no cartridge). The first ~3.4 s of structured
startup therefore belongs to the AGB/Game Boy Player boot, not to the
cartridge. Content-independence of the qualifier is what makes the comparison
possible, and no content equivalence is inferred from it. After that, STRUCTURED
diverges as content must: 218 episodes / 216 stable (a game holding screens)
against 43 / 7 (a stimulus changing every frame) — not a regression.

---

### GBP-HW-227 — OPERATOR OBSERVATION, run 8 — recorded literally

A: the boot/logo appeared — SIM. B: appeared complete; "if it cut anything, it
was only milliseconds at the very beginning; without audio I could not notice
anything definite" (kept as the operator's uncertainty, not as a cut). C: before
the logo, an almost instantaneous black flash with some text visible on it.
D: transition to the game appeared clean. E: game appeared stable. F: time to
useful image almost immediate, nothing abnormal. G: no relevant problem; the
operator notes the Start-up Disc and GBI appear to initialise their own
environment before starting the Game Boy path and considers the current
behaviour understandable for a debug/research runtime — context, not a claim
about their internals.

---

### GBP-HW-228 — the brief black/text flash is the probe's own console, visible for one field — FACT (source and timing)

`video_setup()` points the video interface at the console framebuffer
(`VIDEO_SetNextFramebuffer(xfb_text)`, main.c:373); `main()` prints its banner
there (identity, self-test result, sequence, `"Running ..."`, main.c:890–1072)
and moves the interface to the cleared black stream framebuffer only at
main.c:1075, immediately before the probe runs. `STARTUPT` places that at
`t_video` +15.092 ms → `t_probe_enter` +33.155 ms: **18.06 ms of black console
with light text**, then 177.5 ms of black, then the Game Boy Player's first
frame at 210.664 ms. This matches the operator's C exactly. It is not the
synthetic self-test (`presented_synthetic=0`) and not Game Boy video.
Classified **DEBUG/RESEARCH UX ARTIFACT**; not changed in this round. Whether
Swiss contributes anything before the DOL takes over cannot be excluded from
this repository's source.

---

### GBP-HW-229 — NORMAL startup exposes the real cartridge startup sequence to the user — CORROBORATED

Machine (runs 7 and 8): normal profile, no synthetic hand-off, first real frame
at ~165 ms, early structured episodes descriptor-identical across two
cartridges and to the run whose pixels reconstructed to the animated GAME BOY
logotype (GBP-HW-074…087). Operator (run 8): logo seen, complete, transition
clean, game stable. The two sources are kept apart; pixel identity is not
machine-established and is not claimed. **GBP-VIDEO-005: PASS, with a
DEBUG-UX NOTE.** The NORMAL-startup milestone is physically validated for the
seven properties listed in §V5.54.11 X; final production UX is not claimed.

---

### GBP-HW-230 — what runs 7 and 8 do NOT establish — SCOPE

No pixel-level logo identity; no OGBPIDX verdict for retail content; no media
double check for run 8; nothing about Swiss's own pre-DOL output; no
production-UX claim; nothing about the 5 s gate, which no hardware has run.

---

### GBP-VID-031 — the research not-before gate: witness eligibility deferred to 5000 ms after CONTROL, content-blind, everything else immediate — FACT (software), `stream-0010`

A latch in `gbp_vwitness` with no clock: `gate_streak()` at init,
`release_streak(t)` once, from `pump()`, when `now − t_control_transform ≥
5000 ms` — one 64-bit compare per call until release, then nothing. While
gated, every closed frame is still counted as seen (startup evidence is never
hidden) but the streak is neither built nor broken; at release the streak
starts from zero; afterwards the existing rule runs untouched — 64 structurally
clean closed frames, window at the next block 0, 2048 records, no reset.
Transport, assembler, conversion, Policy A, GX, hand-off and the startup
display are byte-for-byte `stream-0009`'s on the user's path. Default OFF in the
module: a witness never gated is field-for-field the old behaviour, so every
earlier build and test is unchanged. The threshold is prospective — ID 0 at
4.845 s in four of four indexed runs — and the earliest window lands at ≈6.07 s,
inside the regime runs 4–6 established. Content independence is pinned by a
word-bounded source scan of the module, the drive header and the gate block.
Research instrumentation only; a final runtime has no witness to gate.
`WITELIG` reports eligibility as its own line.

**Provenance and status.** This SOFTWARE design was recorded on 2026-09-20 before any
hardware ran it, and the sentence that stood here — "Not physically executed" — was
true when written. `stream-0010` was subsequently physically exercised twice on
2026-09-20: run 9 (BBA disconnected, §V5.56, GBP-HW-237) and run 10 (BBA present,
Ethernet disconnected, §V5.57.14, GBP-HW-242), both PASS. The gate is physically
validated within those runs' scope; the design text above is left as written.

---

### GBP-VID-032 — presentation requirement: pixel-perfect scaling must preserve the source pixel lattice — DESIGN REQUIREMENT (from the operator, 2026-09-20)

Recorded as a requirement, not as evidence, because the project's scheme uses
GBP-VID for software and design facts and this is a constraint on work not yet
begun. When presentation/upscale work starts, a pixel-perfect mode must map
every source pixel to an equal-size output rectangle under an integer
nearest-neighbour scale — no non-uniform X/Y stretch, no anisotropic
deformation, no silent fractional stretch, no smoothing as the default of that
mode. If the output surface does not admit a full-screen integer scale, use
borders / a centred viewport / an explicitly selected alternate policy rather
than deforming pixels. "Pixel-perfect" means preserving the source grid under
the selected integer scale, not a 1× output. Separate from transport, Policy A,
startup timing and research qualification; **nothing was implemented** and no
resolution or viewport was chosen.

---

### GBP-HW-231 — the run-9 artifacts, hashed here first, archived under reserved names — FACT

Log 86 313 B `298eeff4…8e57`, OGBPIDXCAP1 8 946 060 B `247bae66…c7d1`, OGBPDISP2
401 796 B `7a4b032a…4c67`, recomputed in the repository before the orchestrator's
figures were read and matching them. Binary `stream-0010` at `fbaea00`,
495 040 B `6b57d669…6180`, verified before the run and not rebuilt; stimulus
`indexed-0003` delivery `9f04916b…8d9cc2`, not re-flashed. Archived FIRST under
the reserved `captures/local/GBP-VIDEO-004_stream-0010-run9*` names with
`cp --update=none` and `cmp`; run 7 and run 8 archives re-verified intact. BBA
disconnected. Media double check: PENDING.

---

### GBP-HW-232 — the frozen source analyzer on run 9: OBSERVED_CONTIGUOUS with 2048 intact and 0 invalid — FACT

`tools/vindex.py`, unmodified at `f2de217`: `observed frames 2048 (intact
2048)`, no `INVALID_CANONICAL_STRIP` line (0), `first/last observed 0x000049 ..
0x000848` (73..2120), `decisive transitions 2046`, all `OBSERVED_ID_CONTIGUOUS`,
`header/total CRC-32 7fbd6129 / 4d0c702d`, flags `target_reached, service_ok,
stop_is_target`, **`VERDICT OBSERVED_CONTIGUOUS`**. Independent decode agrees on
every block: 81 920/81 920 valid canonical strips with `BLOCK_INDEX == slot`,
`MIXED_BLOCK_IDS` 0, FRAME_ID 73..2120 with 2047 adjacent deltas of +1, STATUS
0x18 throughout, FAULT never set, VMARGIN 24 throughout; 2048/2048 record seals,
reserved zero, `frame_index` 356..2403 strictly +1. **The composition is the
result**: run 7 under the same frozen tool read `intact 1988 / INVALID 60`.

---

### GBP-HW-233 — the not-before gate released at 5.000156691 s after CONTROL and the window opened at 6.067209383 s, 64 clean closes later — FACT

`WITELIG policy=time_not_before origin=control not_before_ms=5000 released=1
still_gated=0 ticks_control_to_eligible=202506346
frames_seen_before_eligible=292 disqualified_before_eligible=26`;
`202 506 346 / 40 500 000 = 5.000156691 s`, an overshoot of 156.7 µs inside
`pump()`'s cadence. `WITQUAL required=64 resets=0 warmup_frames=356
warmup_disqualified=26 qualify_frame=355 first_record_frame=356
window_first_block=0`. First retained record 6.067209383 s after CONTROL,
1.067052692 s after eligibility; record 0 is `frame_index 356` at block 0. 292
frames closed before eligibility, 26 of them disqualifying, none able to build
or break a streak; frames 292..355 — exactly 64 — closed clean after it. No
retrospective trim: `frame_index` 356..2403 with nothing filtered.

---

### GBP-HW-234 — `qual_streak_at_eligible` was lost to a text-line truncation and is recovered exactly — FACT (reporting defect, value derived)

The log header carries `truncated=1`. Exactly one record line reaches the
ringlog limit: `WITELIG`, seq 640, payload 248 characters, ending
`qual_streak_at_e`; the next-longest line is 218. Root cause from source:
`LOG_LINE_LEN 256` (main.c:137), a 7-character `%06u ` prefix (ringlog.c:35),
`vsnprintf` into `line_len − 7`, so 248 usable characters; ringlog.c:46 counts
the cut. Neither sidecar was truncated (all CRCs verified), the witness latch
has no dependency on the log, and device service was unaffected.

The lost field is 0 by contract (§V5.55.3) and is recovered **exactly**: `356 −
292 = 64 = required`, `qualify_frame 355 = 292 + 64 − 1`, `resets 0`,
`warmup_disqualified 26 = disqualified_before_eligible 26`; and replaying those
counters through the frozen `gbp_vwitness.c` (identical to what `fbaea00`
compiled) reproduces `qualify_frame=355` **only** for a streak of 0 at release
(1 → 354, 10 → 345). DIRECT FIELD: lost. SEMANTIC VALUE: 0, exact. Classified
**REPORTING / INSTRUMENTATION DEFECT**; no rerun required; the fix belongs to a
later functional checkpoint (GBP-VID-033).

---

### GBP-HW-235 — the gate did not touch the startup: first real hand-off 165.154741 ms, 18 ticks from run 7 — FACT

`STARTUP mode=normal selftest_visible=0 prehandler_wait_ms=0
presented_synthetic=0 headless_submits=1`; `STARTUPV
ticks_control_to_first_handoff=6688767` = **165.154740741 ms** against run 7's
6 688 749 = 165.154296 ms (+0.444 µs). Headless self-test 12.220 ms, program →
first hand-off 211.109 ms, CONTROL → capture 107.665 ms, capture → first
hand-off 57.490 ms. The gate releases 4.892 s after capture_start; the first
real frame reached a framebuffer 4.7 s before that. `FRAMECAP 2404 / 2391 / 13 /
26 / 13`, `STRUCTURED 45 episodes`, and the four preserved episodes identical to
runs 7 and 8: the transient was recorded, not hidden.

---

### GBP-HW-236 — Policy A, run 9: 2047/2047 over the join, 7 display repeats for the fourth run running — FACT

OGBPDISP2 `a219548c / 6298f601 / 7d6cf2f2 / 4d2b81cc` recomputed and matched;
`2377 + 50 = 2427 = event_n`; `usable_for_disposition_claim True`;
`terminal_pending` header 1 = the headless self-test (log 0 is pre-finish, as in
runs 7–8). Join over source 356..2403: 2047 `SELECTED_NEW`, one without a
lifecycle — `[2403]`, the last retained frame, never taken: a capture-edge
residual, interior missing 0. Hand-off order rebuilt `== 356..2402` exactly, no
duplicate, none overtaken. 46 deferred / 112 attempts in the join (50 / 124 whole
trace), every one resolved on the next retrace, all `XFB_BUSY`, depth 1,
`xfb_skipped 124 = defer_attempts`. Runtime: taken = converted = presented =
2377, `repeats 0`, `balanced 1`, `STREAMINV 200 206 / 0`. Latency under the
pre-registered definition over all 2047: **p99 0.472000 ms, max 1.000148 ms**;
under first-attempt → decision over the 46 deferred: p99 = max = 0.998370 ms.
Cadence, separately: retrace deltas `{1: 2039, 2: 7}` — **7 display-repeat
intervals** beside `SOURCE_DROPPED 0`; runs 6, 7, 8 and 9 all read exactly
seven. Transport `254 873 = 254 873 = 254 873`, `timeouts 0 busy 0 overflow 0
uncertain 0 errors 0`.

---

### GBP-HW-237 — RUN 9 PASSES all fourteen pre-registered gates: the content-independent 5.000 s not-before witness eligibility gate is physically validated for this controlled indexed experiment on this console — FACT (scoped)

A–N of §V5.55.7 / §V5.56.8, every one PASS, D by exact counter derivation.
Established: normal transport and display live from startup; eligibility not
before the prospective threshold; streak from zero; 64 qualifying closes
required; window at the next block-0 boundary; all 2048 retained records valid;
all observed intact IDs contiguous and ordered; no retrospective trimming. No
official tool disagreed with any expected item. **No rerun required.**

---

### GBP-HW-238 — what run 9 does NOT establish — SCOPE

That startup transients no longer exist (they do, §V5.56.6); that every
cartridge is steady-state at 5 s; that 5 s is a protocol or final-runtime
requirement — it is research instrumentation and user-visible video began at
165 ms; physical scanout of any frame; full-frame pixel fidelity; anything about
the BBA, which was disconnected; a media double check, which is PENDING. The
controlled video sequence that required the BBA to stay disconnected is closed
(§V5.56.12); that closure removes a methodology restriction and is **not** BBA
validation.

---

### GBP-VID-033 — the `WITELIG` summary line exceeds the ringlog payload — FACT (software); REPAIRED in `stream-0011`, PHYSICALLY VALIDATED 2026-09-20 (run 11, GBP-HW-245/248)

`LOG_LINE_LEN 256` with a 7-character sequence prefix leaves 248 usable
characters; the `WITELIG` format (main.c:1232) renders to more than that and is
clipped after `qual_streak_at_e`, which `ringlog.c:46` counts as `truncated`.
Every other line in run 9 is ≤ 218. The clipped field is the one §V5.55.3
defined as 0 by contract. Future fix, in a functional checkpoint: preserve every
`WITELIG` field, change no gate semantics, split into stable machine-readable
lines or shorten safely, and add a host test that no required summary line can
exceed the payload — the same class of guard the log-tag uniqueness test is.
Not authorised in the run-9 ingestion checkpoint.

**2026-09-20, deferral noted.** The fix is deliberately postponed until AFTER
`GBP-BBA-001` (RUN 10, §V5.57): that control must reuse the exact run-9 binary
so that BBA presence is the only intentional variable, and a new functional
build here would confound the two. The truncation is EXPECTED to recur in run
10 and is not a BBA regression; the clipped field is derived from counters as
in §V5.56.4.

**2026-09-20, FIXED IN SOFTWARE / PHYSICAL VALIDATION PENDING (§V5.58).**
Functional commit `97c78c2`, build `stream-0011` (495 104 B,
`df2873ee61caa75c885215b54e29e8d5357b233b9bcc0f10d5c0b1af75453e25`, Swiss
byte-identical). Root cause confirmed from source: `LOG_LINE_LEN 256` minus the
7-character `%06u ` prefix and the NUL leaves 248 characters, and the single
record rendered to 310 at the worst case of its conversions. The fix is a split
and nothing else: `WITELIG` (policy, origin, not_before_ms, gated_at_init,
released, still_gated, t_eligible, ticks_control_to_eligible; worst case 205) and
`WITELIG2` (frames_seen_before_eligible, disqualified_before_eligible,
qual_streak_at_eligible=0; worst case 113) — two records with unique tags, every
field name unchanged, no buffer enlarged, `ringlog.c` untouched, both emitted
after the probe run and after `WITQUAL`. A permanent host guard
(`tests/host/test_witelig_len.py`) renders every conversion at the maximum width
of its C type on powerpc-eabi and requires both records ≤ 248, both tags exactly
once, all eleven fields present, and proves the old record would not fit. The
literal `qual_streak_at_eligible=0` is documented as a contract assertion pinned
by the C suite, not a detector. `gbp_vwitness.*` and every frozen tool and
format are byte-identical to `stream-0010`; 12 191 witness checks unchanged.
**Nothing here is hardware-validated**: `GBP-VIDEO-006` (run 11, §V5.58.7) is
pre-registered to validate it, on run 10's topology, and has not run. Runs 9 and
10 remain `stream-0010` evidence with `truncated=1`; their fixtures and
derivations are unchanged.

**2026-09-20, PHYSICALLY VALIDATED (run 11, §V5.58.9; GBP-HW-244…249).** The
exact `stream-0011` artifact ran on run 10's topology and its log came back
`lines=651 dropped=0 truncated=0` with one complete `WITELIG` (167 characters)
and one complete `WITELIG2` (98), `qual_streak_at_eligible=0` present directly,
the counter cross-check agreeing, and every regression gate passing. Scope:
that controlled run; nothing about networking, the BBA beyond its presence,
or Phase 11. Runs 9 and 10 keep `truncated=1` as `stream-0010` facts.

---

### GBP-HW-239 — the run-10 artifacts and the operator's topology declaration (GBP-BBA-001) — FACT

Log 87 468 B `16b387ec…e6b7`, OGBPIDXCAP1 8 946 060 B `1cba0fd7…e95f`, OGBPDISP2
401 796 B `53c67572…9235`, recomputed in the repository before the orchestrator's
figures were read and matching them. Supplied as `…-bba.log` / `…-idxcap-bba.bin`
/ `…-disp-bba.bin` (kept as metadata) and archived FIRST under the reserved
`captures/local/GBP-VIDEO-004_stream-0010-run10*` names with `cp --update=none`
and `cmp`; runs 1–9 untouched. Binary: the exact run-9 `stream-0010 @ fbaea00`,
495 040 B `6b57d669…6180`, not rebuilt; stimulus `9f04916b…8d9cc2`, not
re-flashed; embedded id `GBP-VIDEO-004` by design. **OPERATOR OBSERVATION /
TOPOLOGY DECLARATION, recorded literally:** BBA PRESENTE SIM · Ethernet
DESCONECTADO · mesmo GameCube do RUN 9 SIM · mesmo GBP do RUN 9 SIM. Media
double check: PENDING.

---

### GBP-HW-240 — with the BBA present and Ethernet disconnected, the frozen source analyzer reads exactly as run 9: OBSERVED_CONTIGUOUS, 2048 intact, 0 invalid — FACT

`tools/vindex.py` unmodified: `observed 2048 (intact 2048)`, no
`INVALID_CANONICAL_STRIP` line (0), `0x000049..0x000848` (73..2120), 2046
decisive transitions all `OBSERVED_ID_CONTIGUOUS`, CRC `e410094e / f771828c`,
flags `target_reached, service_ok, stop_is_target`, **`OBSERVED_CONTIGUOUS`**.
Independent decode: 81 920/81 920 valid canonical strips, index ok, MIXED 0,
FRAME_ID 73..2120 with 2047 deltas of +1, STATUS 0x18, FAULT 0, VMARGIN 24;
2048/2048 seals, `frame_index` 356..2403. Every count equals run 9's.

---

### GBP-HW-241 — with the BBA present, the gate, the startup and Policy A read within tens of ticks of run 9 — FACT

`WITELIG released=1 still_gated=0 ticks_control_to_eligible=202506351` =
5.000156815 s (+5 ticks vs run 9); `WITQUAL 292 → 355 → 356`, resets 0, streak
at release 0 by the same exact derivation and the same frozen replay; first
retained record 6.067209136 s (−10 ticks). `STARTUP mode=normal … presented_synthetic=0`,
`ticks_control_to_first_handoff=6688750` = **165.154321 ms** (−17 ticks =
−0.420 µs vs run 9), `< 400 ms`. Transport 254 873 = 254 873 = 254 873, `errors 0
timeouts 0 busy 0 overflow 0 uncertain 0`, numerically identical to run 9.
OGBPDISP2 `3e547a48 / 423a9cfb / 49300560 / a5fb2a5c`, `2377 + 50 = 2427`, ready;
join 2047 `SELECTED_NEW` + `[2403]` capture-edge, interior 0, order `== 356..2402`,
46/112 deferred in the join on the next retrace, depth 1; frozen latency **p99
0.471778 ms, max 1.000765 ms** (alternate first-attempt diagnostic p99 = max =
0.998963 ms); **7 display-repeat intervals** beside 0 drops — the fifth
consecutive run reading seven, observational. The known `WITELIG` truncation
(GBP-VID-033) recurred exactly as pre-registered and is not a BBA finding.

---

### GBP-HW-242 — GBP-BBA-001 / RUN 10 PASSES; runs 9 and 10 form a paired topology control — FACT (scoped)

Every §V5.57 gate passed under the operator-declared topology. **Under this
exact controlled topology and observation window, with the same GameCube, Game
Boy Player, `stream-0010` binary and `indexed-0003` stimulus, physical BBA
presence with Ethernet disconnected produced no detected regression in the
established Open-GBP video transport / source / display / startup metrics.**
The pair supports only NO DETECTED REGRESSION UNDER THIS CONTROL; the
numerical near-identity of the two runs is an observation, and no mechanism for
the absence of a difference is claimed.

---

### GBP-HW-243 — what run 10 does NOT establish — SCOPE

That the BBA is safe, irrelevant, or can never affect the GBP; anything about
an Ethernet-connected topology, BBA initialisation, networking or network code;
Phase 11, which does not move; universal hardware independence; a media double
check (PENDING); scanout or pixel fidelity. The causal reason for postponing
GBP-VID-033 has expired — the exact run-9 binary was reused successfully — and
the fix belongs to the next functional checkpoint.

---

### GBP-HW-244 — the run-11 artifacts and the operator's topology declaration (GBP-VIDEO-006) — FACT

Log 86 338 B `c1987d2f…228b`, OGBPIDXCAP1 8 946 060 B `9b62415b…4b51`, OGBPDISP2
401 956 B `04feeca9…b3e7`, recomputed in the repository before the orchestrator's
figures were read and matching them. Supplied under the console's generated
names (`GBP-VIDEO-004_stream-0011.log` / `-idxcap.bin` / `-disp.bin`, kept as
metadata) and archived FIRST under the reserved
`captures/local/GBP-VIDEO-004_stream-0011-run11*` names with `cp --update=none`
and `cmp`; runs 1–10 untouched. Binary: `stream-0011 @ 97c78c2`, 495 104 B
`df2873ee…3e25`, verified on disk, in the Swiss copy (`cmp` identical) and in
the log header; stimulus `9f04916b…8d9cc2`, not re-flashed; embedded id
`GBP-VIDEO-004` by design. `tools/`, `src/`, `stimulus/` unchanged since
`fbaea00`. **OPERATOR OBSERVATION / TOPOLOGY DECLARATION, recorded literally:**
BBA PRESENT YES · Ethernet DISCONNECTED · same GameCube as RUN 10 YES · same
GBP as RUN 10 YES. Media double check: PENDING.

---

### GBP-HW-245 — the repaired summary arrived whole: `dropped=0 truncated=0`, one complete `WITELIG`, one complete `WITELIG2`, `qual_streak_at_eligible=0` read directly — FACT

Log header `lines=651 dropped=0 truncated=0`. Record 640 `WITELIG` (policy,
origin, not_before_ms, gated_at_init, released, still_gated, t_eligible,
ticks_control_to_eligible; 167 characters) and record 641 `WITELIG2`
(frames_seen_before_eligible=292, disqualified_before_eligible=26,
qual_streak_at_eligible=0; 98 characters), each exactly once, consecutive; all
eleven names of the `stream-0010` contract present; the longest payload in the
log is `STARTUPT` at 218 of 248. The zero needs no derivation; the counter
cross-check still agrees (`356 − 292 = 64`, `355 = 292 + 63`, `resets 0`,
`26 = 26`), and because the counters equal run 10's the frozen-`gbp_vwitness.c`
replay of §V5.57.14 IV applies unchanged. This is the first physical log of the
stream family with `truncated=0` since the not-before gate was added.

---

### GBP-HW-246 — the frozen source analyzer on run 11: OBSERVED_CONTIGUOUS, 2048 intact, 0 invalid — FACT

`tools/vindex.py` unmodified: `observed 2048 (intact 2048)`, no
`INVALID_CANONICAL_STRIP` line (0), `0x000049..0x000848` (73..2120), 2046
decisive transitions all `OBSERVED_ID_CONTIGUOUS`, CRC `ae45abb9 / 1ea96c60`,
flags `target_reached, service_ok, stop_is_target`, **`OBSERVED_CONTIGUOUS`**.
Independent decode: 81 920/81 920 valid canonical strips, index ok, MIXED 0,
FRAME_ID 73..2120 with 2047 deltas of +1, STATUS 0x18, FAULT 0, VMARGIN 24;
2048/2048 seals, `frame_index` 356..2403, cadence 59.727289 Hz. Every count
equals runs 9 and 10 — an observation.

---

### GBP-HW-247 — on the repaired build the gate, the startup, the transport and Policy A read as runs 9 and 10 did — FACT

`WITELIG released=1 still_gated=0 ticks_control_to_eligible=202505829` =
5.000143926 s (−522 ticks vs run 10); `WITQUAL 292 → 355 → 356`, resets 0;
first retained record 6.067192864 s after CONTROL (−16.3 µs). `STARTUP
mode=normal … presented_synthetic=0`, `ticks_control_to_first_handoff=6688927` =
**165.158691 ms** (+177 ticks = +4.370 µs vs run 10; +160 vs run 9), `< 400 ms`.
Transport 254 864 = 254 864 = 254 864 = 254 864, `video 96 110/96 110`, `errors 0
timeouts 0 busy 0 overflow 0 uncertain 0 transport_ok 1`. OGBPDISP2 `92f11ee3 /
d7b7e03a / 51a66d21 / 839a6ba5`, `2377 + 54 = 2431`, ready; join 2047
`SELECTED_NEW` + `[2403]` capture-edge, interior 0, order `== 356..2402`, 50/128
deferred in the join on the next retrace, depth 1; frozen latency **p99
0.486790 ms, max 1.000914 ms** (alternate first-attempt diagnostic p99 = max =
0.999309 ms); **7 display-repeat intervals** beside 0 drops — the sixth
consecutive run reading seven, observational, and no exact-seven gate exists or
is added. The tick differences from run 10 are recorded; no tolerance is
derived from them.

---

### GBP-HW-248 — GBP-VIDEO-006 / RUN 11 PASSES; the GBP-VID-033 reporting repair is physically validated — FACT (scoped)

Every §V5.58.7 gate passed under the operator-declared topology, the primary
reporting gate among them. **The GBP-VID-033 reporting repair is physically
validated for this controlled run — `stream-0011` on the same GameCube, Game
Boy Player, `indexed-0003` stimulus and BBA-present / Ethernet-disconnected
topology as run 10 — with no detected regression in the established source /
transport / Policy-A / startup metrics.** The orchestrator's PASS classification
is reproduced, not reinterpreted.

---

### GBP-HW-249 — what run 11 does NOT establish — SCOPE

Anything about an Ethernet-connected topology, BBA initialisation, networking
or network code; Phase 11, which does not move; the BBA was present only
because run 10 is the immediate baseline. Not universal hardware independence;
not a tolerance on startup, eligibility or latency; not scanout or pixel
fidelity; not a media double check (PENDING). Runs 9 and 10 stay `stream-0010`
evidence with `truncated=1`, their fixtures, derivations and tests untouched.

---

### GBP-HW-250 — the RUN 12 artifacts and the operator's declarations (GBP-VIDEO-007 / GBP-VIDEO-008) — FACT

Five raw files, hashed here on receipt before anything was read into an
interpretation and matching the orchestrator's figures: log 89 514 B
`0b64b677…882b`, OGBPIDXCAP1 8 946 060 B `fe1c1c0a…afd8`, OGBPDISP2
401 356 B `91c2f805…23a4`, OGBPFULL1 1 844 492 B `fb09a777…433c`, OGBPVI1
152 396 B `d301e96e…ddb0`. Supplied under the console's generated names
(`GBP-VIDEO-004_stream-0013.log` / `-idxcap.bin` / `-disp.bin` / `-full.bin` /
`-vi.bin`, kept as metadata) and archived FIRST under the reserved
`captures/local/GBP-VIDEO-004_stream-0013-run12*` names (§V6.19.4) with
`cp --update=none` and `cmp`; runs 1–11 untouched. Binary: `stream-0013 @
7d7a6d8`, 506 496 B `5391c3fe…dd79`, verified on disk, in the Swiss copy
(`cmp` identical), in `build-info.txt` and in the log header
(`test_id=GBP-VIDEO-004 build_id=stream-0013 commit=7d7a6d8`); no runtime,
tool or stimulus source changed between `7d7a6d8` and the ingestion HEAD.
Stimulus: `coord-0001` delivery image 3 496 B `a769cc11…994f` (canonical
`90343b64…0a1f`), re-flashed for this run on the EZ-Flash Omega DE NOR / Mode
B route — the first physical run of OGBPCOORD1. **OPERATOR OBSERVATION /
TOPOLOGY DECLARATION, recorded literally:** same GameCube as RUN 10 / RUN 11
YES · same GBP as RUN 10 / RUN 11 YES · BBA PRESENT · Ethernet DISCONNECTED ·
display chain as pre-registered: GameCube → composite / RCA → low-cost
RCA-to-HDMI converter (HDMI output configured to 1080p) → HYDIS HV150UX2
panel on an M.NT68676.2A controller (custom iMac G3 modification). The chain
is a topology declaration only; the 1080p is the converter's output. The
future Morph 2K paths are outside RUN 12. Media double check: the operator's
pre-run `sha256sum` of the DOL and of the delivery image matched (Issue #9).

---

### GBP-HW-251 — the frozen source analyzer on RUN 12: 2048 intact structural records, two duplicate FRAME_ID transitions, `OBSERVED_DISCONTINUITY`; the shared gate failed — FACT

`tools/vindex.py` unmodified (identical since `fbaea00`): records 2048/2048,
0 discarded, 81 921/81 921 staged/placed, out of range 0, every record 40/40
blocks, flags `target_reached, service_ok, stop_is_target`, CRC
`c5b117ae / c209449b`; `observed 2048 (intact 2048)`, first/last observed
`0x00004a .. 0x000847` (74..2119), first/last decisive 74..2118, **2046
decisive transitions: `OBSERVED_ID_CONTIGUOUS 2044`, `OBSERVED_DUPLICATE_ID
2`**, stimulus fault seen False, **VERDICT `OBSERVED_DISCONTINUITY`**.
Independent decode (own iteration, seals, strips, timing): header and global
CRCs match, 2048/2048 seals, `frame_index` 356..2403 strictly +1, **81 920 /
81 920 valid canonical blocks, index ok in all, MIXED 0, INVALID 0**, FRAME_ID
74..2119 with 2046 distinct ids, adjacent deltas `{0: 2, 1: 2045}`, STATUS
values 0x26 (1120 records) / 0x27 (520) / 0x36 (408), **FAULT 0 throughout**,
VMARGIN 38 / 39 / 54, cadence 59.727105 Hz, first record 6.067206 s after
CONTROL. The two duplicates, exactly: `frame_index 761 → 762`, FRAME_ID
**479 → 479**, STATUS 0x36; `frame_index 2202 → 2203`, FRAME_ID **1919 →
1919**, STATUS 0x26. No gap and no reorder anywhere else. Consequence, per
the prospective §V6.19.7 gate: RUN 12 is NOT admissible for either
experiment (§V6.20.1). The mechanism is not inferred (GBP-VID-034); that both
duplicated ids are the frame immediately before an appearance start (480,
1920) is an observation and nothing more.

---

### GBP-HW-252 — OGBPFULL1 on RUN 12: K = 8 complete, the full-frame dependent-variable analysis PASS 8/8; GBP-VIDEO-008 nevertheless INCONCLUSIVE — FACT (scoped)

`tools/vfull.py` unmodified (since `7d7a6d8`), strict parse: CRC
`b037ecc2 / 6ee7077c`, flags `0x2` (ORIGIN_SET; no truncation, no capacity
skip), K 8, spacing 256, **origin 356** = the first retained witness
`frame_index`, mechanically; `want_calls 2377 wanted 8 opened 8 completed 8
refused 0 skipped_capacity 0 blocks_copied 320`. Samples `frame_index` 356,
612, 868, 1124, 1380, 1636, 1892, 2148 → FRAME_ID 74, 330, 585, 841, 1097,
1353, 1609, 1865 (STATUS 0x36, 0x36, 0x27, 0x27, 0x26, 0x26, 0x26, 0x26).
**Every one of the eight: 40/40 coherent blocks; colour15 oracle mismatches
0 / 38 400; preserved texture vs the Python conversion 0; vs the host-built
`gbp_vpix.c` 0; vs the tiled oracle 0; bit 15 exactly once, at (0, 0); bytes
0/2 observed (34 232 – 34 281 deviating words per sample) and reported, never
judged.** The frozen tool's own verdict is `PASS -- every sample: CLAIM-A and
CLAIM-B, at the texture`, boundary "source → converted texture only". **Positive
subordinate evidence: all eight prospectively sampled frames satisfy
CLAIM-A/CLAIM-B's full-frame source→texture dependent-variable checks. The
formal GBP-VIDEO-008 experiment verdict is nevertheless INCONCLUSIVE because
RUN 12 failed the shared source-window admissibility gate.** Nothing here is
a display, VI or XFB claim, and nothing is claimed for the 2 040 frames not
sampled.

---

### GBP-HW-253 — transport, startup and Policy A on RUN 12 read clean under the inherited gates — FACT

Log header `lines=674 dropped=0 truncated=0`; one `WITELIG`, one `WITELIG2`,
one each of `WITQUAL`, `FULLSTORE`, `VISTORE`, `DISPSRC`, `STREAMWIT`;
longest payload `STARTUPT` at 218 of 248. `stop=witness_target_reached`,
`254 858 = 254 858 = 254 858 = 254 858` (unmasks = deliveries = acks =
re-arms), `video 96 110/96 110`, `timeouts 0 busy 0 overflow 0 uncertain 0
errors 0 transport_ok 1`, `irq_attempted = irq_completed = 509 719`.
`WITQUAL required=64 state=2 streak_max=64 resets=0 warmup_frames=356
warmup_disqualified=26 qualify_frame=355 first_record_frame=356`; `WITELIG
released=1 still_gated=0 ticks_control_to_eligible=202506231` (5.000154 s);
`WITELIG2 frames_seen_before_eligible=292 disqualified_before_eligible=26
qual_streak_at_eligible=0`, read directly; `STREAMWIT records=2048/2048
target_reached=1`. Startup NORMAL, `ticks_control_to_first_handoff=6688663`
= **165.152173 ms** (< 400 ms; run 11: 165.158691 ms, −264 ticks, recorded,
no tolerance). OGBPDISP2 `0c5d3024 / afb8d304 / fb966694 / b34b802e`
recomputed and matched, `2377 + 39 = 2416 = event_n`, `ready True`;
`DISPSRC handoffs=2377 deferred_frames=39 defer_attempts=86
dropped_interior=0 terminal_pending=0 max_defer_depth=1 order_violations=0`
(header `terminal_pending 1` = the headless self-test, as established). Join
over 356..2403: **2047 `SELECTED_NEW`, `[2403]` the capture-edge residual,
interior 0, order rebuilt == 356..2402, reorder 0**; 36 deferred / 79 attempts
in the join, every one resolved on the next retrace, depth 1. **Frozen
latency (ready = `t_convert_done` → `t_decision`, all 2047): p99 0.308642 ms,
max 1.004667 ms — gates 1.0 / 2.5 PASS**; alternate diagnostic (first attempt →
decision, 36 deferred): p99 = max = 1.003531 ms. Cadence, separately: retrace
deltas `{1: 2039, 2: 7}` → 7 display-repeat intervals, the seventh run in a
row, observational. `ENVFULL arena1_free=1658880` on hardware equals the
Dolphin figure of §V6.18.6 (observation). Every inherited gate except the
source-window gate of GBP-HW-251 passes; none was narrowed and none added.

---

### GBP-HW-254 — the operator saw the digits 1, 2, 3, 4, in order, under the declared composite → converter → HYDIS chain — OPERATOR OBSERVATION

Recorded literally from Hardware Issue #9 and the ingestion contract, never
rewritten into a frame-accurate claim: digits seen **1 2 3 4**; order **1 2 3
4**; approximate interval **≈ 7 s**; approximate visible duration **≈ 2 s
each**; missing digit **no**; repeated digit **no**; unexpected digit **no**;
visual anomaly **no**. The timings are approximate human observation only.
The four appearance sets R_1..R_4 (FRAME_ID 480–519, 960–999, 1440–1479,
1920–1959) are all inside the retained population, each with 40/40 distinct
ids retained and 40 handed (GBP-HW-255), so the report is COHERENT with the
machine chain up to the hand-over. It is placed beside that chain and does not
enter it: under the frozen gates it classifies nothing, because the shared
source gate failed (GBP-HW-251) and because the frozen tool establishes no
latched frame (GBP-HW-255). No photograph was taken.

---

### GBP-HW-255 — OGBPVI1 on RUN 12: the container facts and the frozen analyzer's result — FACT

`tools/vvi.py` unmodified (since `7d7a6d8`), strict parse: CRC `81888c2a /
61a03d15`, 2377/2377 record seals, records 2377 of 4096, **handed 2377,
latched 2370, superseded 6** (`frame_index` 86, 631, 1754, 1757, 2041, 2315),
overflow 0, observe_calls 2370, one record awaiting at the end (`frame_index`
2402); every latch is the retrace after its hand-over (2370/2370), `t_latch −
t_handed` 0.095–16.927 ms. **The frozen `regs_consistent()`: 0 / 2370 latched
records name the handed XFB as TFBL; 0 bottom fields plausible; therefore
frozen L_k = 0 for k = 1, 2, 3, 4** while |R_k| = 40, retained 40, H_k = 40
for each — an independent reason GBP-VIDEO-007 cannot pass under the frozen
tool, in addition to the failed shared source gate. The raw cross-check that
explains the zero without modifying the tool is GBP-VID-035; it does not
change this result, which stands as the frozen analyzer's output on RUN 12.

---

### GBP-HW-256 — the RUN 13 artifacts, their receipt and the operator's declarations (GBP-VIDEO-007 / GBP-VIDEO-008 with coord-0002) — FACT

Five raw files, located by full SHA-256 and hashed here on receipt before
anything was read into an interpretation, matching the Orchestrator's
independent measurements on the live SD card: log 87 200 B `4d86ef32…b49a`,
OGBPIDXCAP1 8 946 060 B `dcbcfd3e…2280`, OGBPDISP2 401 396 B `c75e986a…8131`,
OGBPFULL1 1 844 492 B `cb884e27…304b`, OGBPVI1 152 396 B `2a772ae0…f1b4`.
Generated under the console's names (`GBP-VIDEO-004_stream-0013.log` /
`-idxcap.bin` / `-disp.bin` / `-full.bin` / `-vi.bin`, kept as metadata);
found at ingestion in `logs/` under those same bare names, moved there from
the SD card between the Orchestrator's location check and the ingestion — not
by the Executor — which overwrote RUN 12's raw-drop copies under the same
names (the collision `captures/README.md` describes); RUN 12's run-12 archive
re-hashed at ingestion, all five equal to GBP-HW-250, and its versioned
fixtures unchanged. Archived FIRST under the reserved
`captures/local/GBP-VIDEO-004_stream-0013-run13*` names (§V6.24.4) with
`cp --update=none` and `cmp`; `logs/` left as found. Binary: `stream-0013 @
7d7a6d8`, 506 496 B `5391c3fe…dd79` — the RUN 12 image, NOT rebuilt, verified
on disk, in the Swiss copy (`cmp` identical), in `build-info.txt` and in the
log header (`test_id=GBP-VIDEO-004 build_id=stream-0013 commit=7d7a6d8`); no
runtime, tool or stimulus source changed between `9683ea1` (the ingestion
HEAD) and any analyzer's last commit. Stimulus: `coord-0002` delivery image
3 620 B `276ad987…6f700` (canonical `319dacb7…093f`, source `74f9f4f`),
flashed for this run on the EZ-Flash Omega DE NOR / Mode B route — the first
physical run of coord-0002; coord-0001 stays RUN 12's artifact. **OPERATOR
OBSERVATION / TOPOLOGY DECLARATION, recorded literally (Hardware Issue #15):**
same GameCube as RUN 12 YES · same GBP as RUN 12 YES · BBA PRESENT · Ethernet
DISCONNECTED · display chain as pre-registered: GameCube → composite / RCA →
low-cost RCA-to-HDMI converter (HDMI output configured to 1080p) → HYDIS
HV150UX2 panel on an M.NT68676.2A controller (custom iMac G3 modification),
confirmed after the raw return. The chain is a topology declaration only; the
1080p is the converter's output. The future Morph 2K paths are outside RUN 13.
Media double check: the operator's pre-run hashes of the DOL and of the
delivery image matched (Issue #15).

---

### GBP-HW-257 — the frozen source analyzer on RUN 13: 2048 intact structural records, 2046 / 2046 decisive transitions +1, `OBSERVED_CONTIGUOUS`; the shared gate passed — FACT

`tools/vindex.py` unmodified (identical since `fbaea00`): records 2048/2048,
0 discarded, 81 921/81 921 staged/placed, out of range 0, every record 40/40
blocks, flags `target_reached, service_ok, stop_is_target`, CRC
`800a1097 / 781de3b8`; `observed 2048 (intact 2048)`, first/last observed
`0x000034 .. 0x000833` (52..2099), first/last decisive 52..2098, **2046
decisive transitions: `OBSERVED_ID_CONTIGUOUS 2046`, no duplicate, no gap, no
reorder**, stimulus fault seen False, **VERDICT `OBSERVED_CONTIGUOUS`**.
Independent decode (own iteration, seals, strips, timing): header and global
CRCs match, 2048/2048 seals, `frame_index` 356..2403 strictly +1, **81 920 /
81 920 valid canonical blocks, index ok in all, MIXED 0, INVALID 0**, FRAME_ID
52..2099 with 2048 distinct ids, adjacent deltas `{1: 2047}`, STATUS values
0x26 (1579 records) / 0x27 (40) / 0x36 (429), **FAULT 0 throughout**, VMARGIN
38 / 39 / 54, cadence 59.727133 Hz, first record 6.067203 s after CONTROL.
R_1..R_4 each retained 40/40 distinct ids, and the transitions into them are
+1: `frame_index 783 → 784` FRAME_ID 479 → 480, `1263 → 1264` 959 → 960,
`1743 → 1744` 1439 → 1440, `2223 → 2224` 1919 → 1920. Consequence, per the
prospective §V6.24.7 gate: RUN 13 is ADMISSIBLE for both experiments — this is
the gate RUN 12 failed (GBP-HW-251). §V6.22's falsifiable expectation for
coord-0002 (no PREPARE-side duplicate at any entry) agrees with the data; that
is one physical run consistent with the software cycle model of §V6.23, not a
calibration of it, and no new finding is opened.

---

### GBP-HW-258 — OGBPFULL1 on RUN 13: K = 8 complete, the full-frame analysis PASS 8/8; the formal verdict GBP-VIDEO-008 = PASS for the eight sampled frames — FACT (scoped)

`tools/vfull.py` unmodified, strict parse: CRC `b037ecc2 / 3e926833`, flags
`0x2` (ORIGIN_SET; no truncation, no capacity skip), K 8, spacing 256,
**origin 356** = the first retained witness `frame_index`, mechanically;
`want_calls 2377 wanted 8 opened 8 completed 8 refused 0 skipped_capacity 0
blocks_copied 320`. Samples `frame_index` 356, 612, 868, 1124, 1380, 1636,
1892, 2148 → FRAME_ID 52, 308, 564, 820, 1076, 1332, 1588, 1844 (the witness
ids at those indices; STATUS 0x36, 0x36, 0x26, 0x26, 0x26, 0x26, 0x26, 0x26).
**Every one of the eight: 40/40 coherent blocks; colour15 oracle mismatches
0 / 38 400; preserved texture vs the Python conversion 0; vs the host-built
`gbp_vpix.c` 0; vs the tiled oracle 0; bit 15 exactly once, at (0, 0); bytes
0/2 observed (33 829 – 33 850 deviating words per sample) and reported, never
judged.** The tool's own verdict is `PASS -- every sample: CLAIM-A and
CLAIM-B, at the texture`, boundary "source → converted texture only"; the
oracle was not retuned. **The shared source gate passed (GBP-HW-257), so the
formal experiment verdict is GBP-VIDEO-008 = PASS, within its pre-registered
boundary (§V6.24.8): CLAIM-A / CLAIM-B for the eight prospectively selected
K = 8 frames only** — each sampled source frame acquired completely and its
full 240 × 160 consumed colour15 image equal to the unchanged OGBPCOORD1
oracle; the preserved texture equal to the Python conversion, the host
`gbp_vpix.c` conversion and the tiled oracle. Nothing here is a display, VI
or XFB claim; nothing is claimed for the 2 040 frames not sampled; no physical
pixel equality is claimed.

---

### GBP-HW-259 — transport, startup and Policy A on RUN 13 read clean under the inherited gates — FACT

Log header `lines=658 dropped=0 truncated=0`; one `WITELIG`, one `WITELIG2`,
one each of `WITQUAL`, `FULLSTORE`, `VISTORE`, `DISPSRC`, `STREAMWIT`;
longest payload `STARTUPT` at 218 of 248. `stop=witness_target_reached`,
`254 862 = 254 862 = 254 862 = 254 862` (unmasks = deliveries = acks =
re-arms), `video 96 110/96 110`, `timeouts 0 busy 0 overflow 0 uncertain 0
errors 0 transport_ok 1`, `irq_attempted = irq_completed = 509 727`.
`WITQUAL required=64 state=2 streak_max=64 resets=0 warmup_frames=356
warmup_disqualified=26 qualify_frame=355 first_record_frame=356`; `WITELIG
released=1 still_gated=0 ticks_control_to_eligible=202506118` (5.000151 s);
`WITELIG2 frames_seen_before_eligible=292 disqualified_before_eligible=26
qual_streak_at_eligible=0`, read directly; `STREAMWIT records=2048/2048
target_reached=1`. Startup NORMAL, `ticks_control_to_first_handoff=6688650`
= **165.151852 ms** (< 400 ms; RUN 12: 165.152173 ms, −13 ticks, recorded,
no tolerance). OGBPDISP2 `98c08390 / c97b54dd / 19cfc51f / 0e88b3ff`
recomputed and matched, 2378 lifecycles, `2377 + 40 = 2417 = event_n`,
`ready True`; `DISPSRC handoffs=2377 deferred_frames=40 defer_attempts=88
dropped_interior=0 terminal_pending=0 max_defer_depth=1 order_violations=0`.
Join over 356..2403: **2047 `SELECTED_NEW`, `[2403]` the capture-edge
residual, interior 0, order rebuilt == 356..2402, reorder 0**; 37 deferred /
81 attempts in the join, every one resolved on the next retrace, depth 1.
**Frozen latency (ready = `t_convert_done` → `t_decision`, all 2047): p99
0.308543 ms, max 1.005012 ms — gates 1.0 / 2.5 PASS**; alternate diagnostic
(first attempt → decision, 37 deferred): p99 = max = 1.003802 ms. Cadence,
separately: retrace deltas `{1: 2039, 2: 7}` → 7 display-repeat intervals,
the eighth run in a row, observational. `ENVFULL arena1_free=1658880` equals
RUN 12 and the Dolphin figure of §V6.18.6 (observation). Every inherited gate
passes; none was narrowed and none added.

---

### GBP-HW-260 — OGBPVI1 on RUN 13 with the corrected analyzer: 2371 / 2371 register-consistent latches, L = 40 / 40 / 39 / 40; the operator saw 1, 2, 3, 4 in order; the formal verdict GBP-VIDEO-007 = PASS as CLAIM-D — FACT (the software chain) · OPERATOR OBSERVATION (the visual report)

`tools/vvi.py`, the corrected implementation of the GBP-VID-035 repair
(commit `0ee8aac`, §V6.21), unchanged since and used prospectively as
§V6.24.2 pre-registered — never to re-derive RUN 12: strict parse, CRC
`a11e9209 / c480f86f`, 2377/2377 record seals, records 2377 of 4096, **handed
2377, latched 2371, superseded 5** (`frame_index` 86, 631, 1754, 2041, 2315),
overflow 0, observe_calls 2371, one record awaiting at the end (`frame_index`
2402); every latch is the retrace after its hand-over (2371/2371), `t_latch −
t_handed` 0.095–16.927 ms; VI flag 1 and xof 0 in every latched record; two
distinct addresses, 0x013a8420 and 0x0143e440, encoded exactly as libogc2
does. **Corrected register model: 2371 / 2371 latched records name the handed
XFB as TFBL; 2371 / 2371 bottom fields plausible. Software chain, from records
marked LATCHED and register-consistent only: |R_k| = 40, retained 40, H_k = 40
for each of k = 1..4; L_1 = 40, L_2 = 40, L_3 = 39, L_4 = 40.** The one R_3
member not in L_3 — `frame_index 1754` (FRAME_ID 1450) — is SUPERSEDED in the
raw file: the next hand-over came one retrace later, before the pump observed
it current, so no latch was recorded; instrumentation semantics only, never
evidence of physical non-scanout. **OPERATOR OBSERVATION, recorded literally
from Hardware Issue #15 and never rewritten into a frame-accurate claim:**
digits seen **1 2 3 4**; order **1 2 3 4**; approximate interval **≈ 8 s**
between digits (a human estimate, never timing evidence); missing digit
**no**; repeated digit **no**; unexpected digit **no**; visual anomaly **no**;
no photograph. The report is placed beside the chain and does not enter it.
**The §V6.24.9 rule, applied by the Orchestrator and reproduced here: the
shared run is admissible (GBP-HW-257); the qualifying appearances under the
decisive range 52..2098 are R_1..R_4; each has L_k ≥ 1; the coherent report
contains the digit k mod 10 for each, in order — the formal experiment
verdict is GBP-VIDEO-007 = PASS, as CLAIM-D only:** at least one
source-derived frame from every qualifying appearance was physically visible
through the declared RUN 13 display chain (GBP-HW-256). The observation is
bound to a 40-frame appearance set, never to one frame; nothing about pixels,
tearing, presentation, scaling, the converter, the panel, Morph 2K or Q80T.

---

### GBP-HW-261 — the RUN 14 / RUN 15 artifacts, their receipt and identity, and the Operator's declarations as relayed (GBP-INPUT-001: the Enhanced Control Checker's walks A and B on `stream-0014`) — FACT (artifacts, identity) · OPERATOR OBSERVATION (declarations)

Ten raw files, archived FIRST under the reserved run14 / run15 names of
§V7.1.5 (verified absent, `cp --update=none`, `cmp` identical) and hashed by
the Executor before anything was read into an interpretation, matching the
Orchestrator's independent measurements: RUN 14 — log 90 652 B
`e2ba3d82…1d54`, OGBPIDXCAP1 8 946 060 B `d42ebb1a…1de2`, OGBPDISP2 400 396 B
`82bc7434…40c7`, OGBPFULL1 1 844 492 B `30c144d7…1b3c`, OGBPVI1 152 396 B
`ef0a1261…927a`; RUN 15 — log 90 734 B `1cab151b…034e`, OGBPIDXCAP1 8 946 060 B
`be1785ce…94a8`, OGBPDISP2 400 436 B `7577a72b…133b`, OGBPFULL1 1 844 492 B
`0c3e5612…54b7b`, OGBPVI1 152 396 B `fb6d12a7…f79f` (full hashes in
`HARDWARE_TESTS.md` §V7.2.3 and the struct fixtures). Generated under the
console's names (`GBP-VIDEO-004_stream-0014.log` / `-idxcap.bin` / `-disp.bin`
/ `-full.bin` / `-vi.bin`, kept as metadata); moved by the Operator off the SD
card — RUN 14's into `logs/` under the bare names (mtimes 09:41 local), RUN
15's into `logs/run15/`, a per-run subdirectory, so the second run did not
overwrite the first; the card copies are deleted after the move, so `logs/`
was the only copy until each archive existed; archived at 13:13 and 13:17 on
the Orchestrator's request, reported on Hardware Issue #21; `logs/` left as
found. Binary: `stream-0014 @ 0ff8355`, 513 152 B `ef76a170…0b9c` — Issue
#19's candidate, NOT rebuilt, verified on disk, in the Swiss copy (`cmp`
identical), in `build-info.txt` and in both log headers
(`test_id=GBP-VIDEO-004 build_id=stream-0014 commit=0ff8355`); stream-0013
preserved at `build/archive/` as `5391c3fe…dd79`, unchanged; no runtime, tool,
format or gate file changed between `ed7dea2` (the ingestion HEAD) and any
analyzer's last commit. Instrument: the Enhanced Control Checker GBA
(github.com/nataliethenerd/enhancedcontrolcheckerGBA, main =
`76924c1371d7bf761f8b1ed45ab36f195cd1374f`, CC BY-SA 4.0; the repository's
prebuilt ROM 69 348 B `53c212c7…b6e`, hashed from a scratchpad clone), the
Operator's media on the EZ-Flash Omega DE NOR, booted straight into; the
flashed image was not hashed by the Executor; nothing from it enters the
repository. **OPERATOR DECLARATION, given after the runs and relayed by the
Orchestrator (Issue #25, 2026-09-21), mapped onto §V7.1.4:** the same
GameCube — DECLARED; the same Game Boy Player — DECLARED, on the basis of
the Operator's declared hardware inventory (2026-09-21: he owns exactly one
GameCube and exactly one Game Boy Player, so every run of this project uses
the same two units; not to be questioned on this again) — an operator
declaration, not an inference from the console declaration (an inference
about a topology item is what makes a run inconclusive; the Operator had
first declared the console only and the Game Boy Player was recorded as not
separately declared until the inventory was stated, the same day); BBA
PRESENT, Ethernet DISCONNECTED
— DECLARED, in his words "BBA conectado sem cabo de rede"; display chain
UNCHANGED — DECLARED (the chain of §V7.1.4 / §V6.24.3: GameCube → composite
/ RCA → low-cost RCA-to-HDMI converter, 1080p out → HYDIS HV150UX2 /
M.NT68676.2A; topology only); controller — ONE GENERIC, third-party GameCube
controller in port 1, on record for the first time; the official Nintendo pad
the Operator also owns was NOT the one used; the checker on the NOR as the
boot screen (as relayed, Issue #24); no network code; no deviation reported.
**Declaration history, kept:** at ingestion (Issue #24) no literal post-run
declaration existed on Hardware Issue #21 (its comments are the staging
report, the Orchestrator's staging verification and the two archiving
reports) or on #24, and the controller model was recorded as absent, not
inferred; the declaration above replaced that note under Issue #25. **Scope
the pad puts on the L / R result (GBP-HW-265):** the policy reads L and R by
their digital click only (`trigger_threshold=0`; GBP-KEY-006) and L and R were
the first two buttons of both walks, so what the runs establish about L and
R is established through the digital click of a third-party pad —
encouraging, and a limit: the official pad was not exercised and the project
has no data on it. The
Operator's photographs of the tally screen were useless as an aid — the chain
has no upscaler and the 240 × 160 console text does not survive the camera
(relayed); an observation about the aid, no claim about the chain. The
unregistered trial of 2026-09-21 (§V7.1.2) left no file and no leftover was
found. The SD copy and its pre-boot hash check were the Operator's (§V7.1.6
step 4).

---

### GBP-HW-262 — the first physical KEYPAD writes: `INPUT` attempts = completed = 7 892 / 7 895, failed 0, 42 key changes in each run, the descriptor and policy as pre-registered; transport, startup and Policy A clean under the inherited gates; `truncated=1` is the clipped `ENVINPUT` record — FACT

**RUN 14:** `INPUT selftest=1 steps=183931 invalid=0 no_base=0 key_changes=42
attempts=7892 completed=7892 failed=0 first=1 change=42 refresh=7849 retry=0
last_word=0000 last_rc=ok`; `INPUTT write_ticks=30/30/38 n=7892
step_ticks=98/169/1046 n=183931` (min/mean/max). **RUN 15:** `INPUT selftest=1
steps=183942 invalid=0 no_base=0 key_changes=42 attempts=7895 completed=7895
failed=0 first=1 change=42 refresh=7852 retry=0 last_word=0000 last_rc=ok`;
`INPUTT write_ticks=30/30/38 n=7895 step_ticks=98/169/1045 n=183942`.
**Both:** `ENVINPUT port=1 policy=default stick_threshold=48
trigger_threshold=0 analog_ab_threshold=0 filter_opposites=1 refresh_ms=5
refresh_ticks=202500 layout=gbi-u16-replicated index=12
desc=0,1,2,3,4,5,6,7,9,8 pressed_is_one=1 desc_status=CORROBORATED_n` — the
one-place descriptor of GBP-KEY-006 reported as data, unchanged. The §V7.1.8
INPUT machine gate is met in both runs: selftest 1, steps > 0, attempts > 0,
completed = attempts, failed = 0, first = 1, refresh > 0, change ≥ 4,
invalid / no_base / retry 0, `last_rc=ok`, and `attempts = first + change +
refresh + retry` closes. `key_changes = 42 = 2 × 21` in each run — each press
a change to the word and back, each walk 21 presses — is CONSISTENT with the
declared walks and is not a record of which buttons changed (the log carries
counts, not words). `INPUTT` is observational: the 32-byte write 30 ticks
(0.74 µs) at mean, 38 at most; the whole step 98 / 169 / 1 046 ticks (2.4 /
4.2 / 25.8 µs) over ~184 000 passes of the pump slot. **These are the only
machine facts of the experiment: the runtime issued 7 892 and 7 895 completed
KEYPAD writes, none failed, none retried; whether any word reached the
cartridge is not in these records** (GBP-HW-263, GBP-HW-264). Inherited
gates, both runs: `stop=witness_target_reached`, restore ok; unmasks =
deliveries = acks = re-arms = 254 618 (RUN 14) / 254 621 (RUN 15); video
96 109/96 109; timeouts 0 busy 0 overflow 0 uncertain 0 errors 0 transport_ok
1; WRITES irq 509 239 / 509 239 and 509 245 / 509 245; STATS transfers
1 032 712 / 1 032 723, bulk 260 900 / 260 899. Startup NORMAL,
`ticks_control_to_first_handoff` 6 696 178 = **165.337728 ms** and 6 696 209 =
**165.338494 ms** (< 400 ms; +0.186 ms on RUN 13's 165.151852 ms, recorded, no
tolerance, not explained). WITQUAL 64 / 356 / 26 / 355 / 356, WITELIG released
1, `ticks_control_to_eligible` 202 507 660 (5.000189 s) / 202 507 561
(5.000187 s), WITELIG2 292 / 26 / 0, STREAMWIT 2048/2048. Policy A over
356..2403 in both: 2047 `SELECTED_NEW`, `[2403]` the capture edge, interior 0,
order rebuilt, reorder 0, depth 1; 12 / 14 and 13 / 17 deferred / attempts in
the join; frozen latency p99 0.003210 / 0.003185 ms, max 0.475383 / 0.475753
ms (gates 1.0 / 2.5 PASS; the p99 fell below RUN 13's 0.308543 ms because the
deferred count fell below 1 % of 2047 — arithmetic on the distribution, not a
latency claim); cadence `{1: 2039, 2: 7}` → 7 repeats, observational. Log
headers `lines=686 dropped=0 truncated=1` in both: the clipped record is
`ENVINPUT` (seq 3, 248 of a rendered 266 characters; lost tail `ot_FACT
selftest=1`, both recoverable — GBP-KEY-008); every other payload ≤ 218
(`STARTUPT`); the sidecars are unaffected and no gate figure is derived from
the clipped fields. `ENVFULL arena1_free=1650688`, 8 192 B below RUN 13
(observation, cause not established). Every inherited gate passes with that
one recorded exception; none was narrowed and none added.

---

### GBP-HW-263 — the Operator's tally vectors after walk A and walk B: `1 2 · · · · 6 5 3 4` and `1 2 3 4 5 6 · · · ·`, equal to the walks' arithmetic expectation, L = 1 and R = 2 in both — OPERATOR OBSERVATION (literal, relayed by the Orchestrator)

Recorded literally from Issue #24 (2026-09-21), in the checker's order L, R,
UP, DOWN, LEFT, RIGHT, START, SELECT, A, B with `·` a blank counter: **RUN 14
(walk A: L ×1, R ×2, A ×3, B ×4, SELECT ×5, START ×6) `1 2 · · · · 6 5 3 4`;
RUN 15 (walk B: L ×1, R ×2, UP ×3, DOWN ×4, LEFT ×5, RIGHT ×6) `1 2 3 4 5 6 · ·
· ·`** — each equal to its walk's expectation (§V7.1.9) with a blank where the
expectation says 0. Every walk completed; no tally moved without a press (as
relayed); no per-press live-channel record was relayed (§V7.1.9 makes the
vector the channel the verdict is read from and the live channel a
corroboration when seen); the photographs were useless as an aid
(GBP-HW-261). Prior exposure (§V7.1.2) is on record: the Operator had seen the
unregistered trial's informal answer; the mitigation was the distinct-count
scheme ("what number is on the screen"). This row is the human channel; it
is placed beside the machine channel of GBP-HW-264, never fed into a tool and
never merged with it — their agreement is stated in GBP-HW-264.

---

### GBP-HW-264 — the OGBPFULL1 frames of RUN 14 and RUN 15 carry the checker's tally screen; the counts, decoded pixel-exactly with the frozen parser, equal the walks' expectation with L = 1 and R = 2 in both; the machine vector agrees with the Operator's digit for digit — FACT (data, recomputable)

Each run preserved K = 8 complete full-frame samples at `frame_index` 356 +
256·i (the same content-blind OGBPFULL1 of RUN 12 and RUN 13; CRCs `33f665a5 /
b48b2526` and `33f665a5 / 166c946e`; 8/8 COMPLETE, want_calls 2377, blocks
copied 320). Under the UNMODIFIED `tools/vfull.py` (`load()`,
`consumed_words()`: word16 = (byte1 << 8) | byte3 in raster order, GBP-VID-003)
every one of the 16 samples shows the checker's console screen — title row lit
522 pixels, three distinct words, the (0,0) word `0xc578` = the checker's
`RGB15(17,11,24)` in R-high order with the reported-not-interpreted flag bit —
and the tally field at console column 22 of rows 4–13 reads, by exact 8 × 8
glyph match against a six-glyph table transcribed from the frames (an unknown
bitmap aborts, never guesses; no tens digit anywhere): **RUN 14 — s0 (+6.084 s
after CONTROL) `1 · · · · · · · · ·`; s1 (+10.370) `1 2 · · · · · · 3 2`; s2
(+14.656) `1 2 · · · · 3 5 3 4`; s3 (+18.943) through s7 (+36.087) `1 2 · · · ·
6 5 3 4`. RUN 15 — s0 `1 · · · · · · · · ·`; s1 `1 2 3 2 · · · · · ·`; s2 `1 2 3
4 5 1 · · · ·`; s3 through s7 `1 2 3 4 5 6 · · · ·`.** The final state is
reached by s3 and identical across the last five samples (17.1 s); the
partials show the counters advancing in the declared walk order with L at 1
before R moved. In both runs the final vector equals the walk's arithmetic
expectation with a blank read as "never incremented", L = 1 and R = 2, and it
agrees with the Operator's vector (GBP-HW-263) digit for digit — stated, not
merged. The preserved texture equals the Python conversion of the preserved
raw in all 16 samples (content-independent, checked outside the tool's oracle
path). **FACT as data, classified by the Orchestrator and held: the preserved
frames show the checker's tally screen with counts equal to the walks'
expectation, reproducible from the archived files with the frozen parser —
not operator observation. Not in the frames: which GameCube button was
pressed** (GBP-HW-265). The tool's own verdict on these files is INCONCLUSIVE
(STRIP-L inconsistent on every sample) because its oracle is OGBPCOORD1 —
recorded, not judged, like `tools/vindex.py`'s
`INCONCLUSIVE_TOO_FEW_INTACT_FRAMES` (2048 records, all 40 blocks, canonical
strip INVALID on every frame by construction; CRCs `c4d18caf / 03716e77` and
`5b3b8523 / ec26bd10`). Versioned byte-identical as
`captures/fixtures/hw-gamecube-gbp-2026-09-21-stream-0014-run14-full.bin` and
`…-run15-full.bin`; recomputed by `tests/host/test_run14.py`.

---

### GBP-HW-265 — GBP-INPUT-001 verdicts: Question M = PASS and Question O = AS-ASSIGNED in RUN 14 and in RUN 15; U-GBP-010 CLOSED on its stated condition with the descriptor kept; the blank-vs-0 reading recorded — FACT (the verdict record) · CORROBORATED (the routing), not FACT

Read from §V7.1.9 as frozen before the runs, per run, from the Operator's
vector (GBP-HW-263) and independently from the machine vector (GBP-HW-264):
no zero where a count was expected; no unexpected non-zero where 0 was
expected; no tally moved without a press; no walk cut; with all counts
distinct exactly one permutation is consistent with each vector, the
identity. **Question M = PASS** — RUN 14 for L, R, A, B, SELECT, START; RUN 15
for L, R, UP, DOWN, LEFT, RIGHT; each run complete for what it answers, a
button not pressed in a run "not observed" in that run, all ten observed
across the two: a KEYPAD word written by Open-GBP reaches the cartridge as
key presses, for the buttons pressed; nothing about latency, the refresh, or
unpressed buttons. **Question O = AS-ASSIGNED** — L = 1 and R = 2 with no 1 or
2 at a counter that expected 0: the GameCube L reached the checker's L and R
its R. **The blank:** §V7.1.9 says an unpressed counter "reads 0"; the
instrument prints a tally only on a press (`updateButtonTally` after
`keysDown()`), so an unpressed counter is BLANK — read as "never incremented",
the gate's substance; the wording mismatch is recorded here, in §V7.2.7 and in
the fixtures, and the frozen text is not edited. **U-GBP-010 CLOSED** on its
own condition — a game that distinguishes L from R, OPERATOR OBSERVATION —
with the descriptor of `src/gbp/gbp_input.c` kept exactly (bit 8 = L, bit 9 =
R; unchanged since `0ff8355`); supported by the Operator's report AND,
independently, by the frames; `REGISTERS.md` still tabulates Dolphin's order
at H (`docs/protocol/` is the Orchestrator's to update). **The routing —
GameCube L reaching the AGB's L line — stays CORROBORATED, not FACT**, exactly
as §V7.1.10 said after either outcome: its chain is the descriptor (code,
GBP-KEY-006), the checker's `countL` on `KEY_L` (source), the L counter at 1
and no other at 1 (data), and the Operator having pressed L exactly once —
which no machine record contains (42 key changes, not which buttons; frames
show what the cartridge displayed, not what the GameCube sent). The
distinct-count design makes a wrong walk overwhelmingly unlikely to produce
the expected vector — an argument, not a record. Classified by the
Orchestrator (Issue #24) and reproduced here; no gate, threshold or verdict
definition moved after the data was seen; GBP-KEY-004 unchanged, its
falsifier did not fire; RUN 16 not run; Phase 5's acceptance criterion (a real
game) not assessed. **Scope of the pad (Issue #25):** both readings of L and R
are readings of the digital click of a GENERIC, third-party GameCube controller
(the Operator's post-run declaration, GBP-HW-261; the policy does not read the
analogue triggers); the official Nintendo pad was not exercised and the project
has no data on it — the verdicts are unchanged and their scope now names the
pad; the same Game Boy Player by the Operator's declared inventory (GBP-HW-261).

---

### GBP-HW-266 — the RUN 17 / RUN 18 / RUN 16 artifacts, their receipt and identity, the execution order, the naming with the retired names, and the Operator's declarations as relayed (GBP-INPUT-002 on `stream-0015`; RUN 16 the menu reading, executed last) — FACT (artifacts, identity, order) · OPERATOR OBSERVATION (declarations)

Executed 2026-09-21 under Hardware Issue #32 on `stream-0015` (`da06500`,
514 880 B, `dd545c01…3a49` — in `build-info.txt`, in the Swiss copy staged by
§V7.3.6 steps 1–3 with stream-0014 preserved FIRST at `build/archive/` as
`ef76a170…0b9c`, verified independently by the Orchestrator, and in all three
log headers; NOT rebuilt); the Enhanced Control Checker of §V7.1.3 on the
EZ-Flash NOR for RUN 17 / RUN 18, the EZ-Flash menu for RUN 16 (the
Operator's media; nothing enters the repository). **Fifteen raw files**, each
moved by the Operator into a per-run subdirectory under `logs/` and archived
FIRST under its `captures/local/` name (verified absent, `cp --update=none`,
`cmp`, SHA-256 from the copies; `logs/` left as found; all fifteen matched the
Orchestrator's independent snapshot; reported on Hardware Issue #32): RUN 17
log 96 396 B `85d89637…`, idxcap 8 946 060 B `e32af1a6…`, disp 400 716 B
`f3c9bcf6…`, full 1 844 492 B `75c94bdb…`, vi 152 396 B `ae8c484d…`; RUN 18
log 95 265 B `242821fc…`, idxcap `6be30f15…`, disp 400 676 B `c95bb27f…`,
full `4a724784…`, vi `69eff4d1…`; RUN 16 log 93 996 B `20d0be5a…`, idxcap
`e07cb0b4…`, disp 400 796 B `9da66d6e…`, full `3cfb7dd9…`, vi `f98d0974…`
(full hashes in `HARDWARE_TESTS.md` §V7.4.3 and the struct fixtures).
**Execution order:** raw write times run17 14:13:32, run18 14:19:30, run16
14:22:08 (−03:00) — the walks first, the menu test LAST; the numbering follows
§V7.3.2 (a reserved number belongs to its experiment whenever it runs), not
the order; both recorded. **Naming:** RUN 16's files went first under a
provisional name because the run used `stream-0015` while its reserved names
assumed `stream-0014`; after the Orchestrator's explicit resolution they were
renamed (`mv -n`) to the `stream-0015-run16` names; the five
`stream-0014-run16` names of §V7.1.5 are RETIRED — reserved on a wrong
assumption, never used, never reassigned. **Declarations (OPERATOR
OBSERVATION, relayed by the Orchestrator, Issue #33):** the console and the
Game Boy Player by the declared inventory (GBP-HW-261; cited, not asked);
controllers per run — RUN 17 the GENERIC third-party pad of RUN 14 / RUN 15,
RUN 18 and RUN 16 the ORIGINAL Nintendo pad (its first time on record); boot
screens — RUN 17 / RUN 18 straight into the checker, RUN 16 the menu
(corroborated by machine: the KEY record holds no navigation word); RUN 16's
presses 4 × R, 4 × L, 4 × R, 4 × L, nothing else. **Not declared:** BBA /
Ethernet state and the display chain for these runs — recorded as ABSENT,
not inferred; no deviation reported; neither is part of the join (§V7.4.2,
§V7.4.4). The Operator's boot-presentation observation is GBP-HW-271.

**2026-09-21, Issue #35 (declared after the ingestion; the note above kept as
history):** the Operator declared, for RUN 16 / 17 / 18, BBA PRESENT with no
Ethernet cable — "BBA como sempre (presente mas nao conectado no cabo)" — and the
display chain UNCHANGED — "video inalterado" — and made two of these
STANDING declarations, operator declarations WITH A STATED DURATION, in his
words: the display chain "video inalterado e ira permanecer assim ate que eu anuncie o contrario"; the BBA "BBA também permanecera presente e sem cabo, ate que seja solicitado para remover ou conectar o cabo". They hold until he announces a change, like the hardware inventory
(Issue #25); future pre-registrations cite them instead of asking; they are
NOT a licence to infer — each item stays DECLARED, by him, until he says
otherwise, and a run whose record does not reflect an announced change is
INCONCLUSIVE on that item (§V7.1.4). What still needs a per-run declaration:
the cartridge and its boot screen, and the controller (both his pads have
been used; never assumed). §V7.4.2 / §V7.4.4 carry the declaration with the
history; no verdict, gate or status changes; no new id.

---

### GBP-HW-267 — the KEY record's first hardware exercise: `KEYLOG` 43 / 43 / 33 events, none lost, none truncated, none overwritten, every line parsed, the word the runtime sent at every change; `truncated=0` with ENVINPUT (170) and ENVINPUT2 (105) complete — GBP-KEY-008's repair physically validated; INPUT 7 898 / 7 898 / 7 890 completed writes, failed 0; transport, startup and Policy A clean — FACT

All three logs (`HARDWARE_TESTS.md` §V7.4.4, §V7.4.5): `dropped=0
truncated=0`; ENVINPUT and ENVINPUT2 both present and complete — the record
that clipped at 266 characters in RUN 14 / RUN 15 (GBP-KEY-008) is split in
`stream-0015` (Issue #27, GBP-KEY-010) and both halves are complete on
hardware, so the §V7.3.8 gate `truncated=0` is met and the repair is
PHYSICALLY VALIDATED, as run 11 validated WITELIG's; the longest payload is
now STARTUPT at 218. **The KEY record:** `KEYLOG events=43 emitted=43 lost=0
truncated=0 overwritten=0 reserve=64` (RUN 17, emit_ticks 924/1580/1707), the
same 43 / 43 (RUN 18, 871/1585/1748), 33 / 33 (RUN 16, 909/1567/1722); the
number of KEY lines in each log equals `emitted`; every line parses under
`GBP_INPUT_EVENT_FMT` with n increasing by one from 1, every `rc=ok`, every
`act` in {first, change}, `t_poll ≤ t_attempt ≤ t_done`, `t_attempt`
monotonic; events = INPUT first + change + retry (1 + 42 + 0; 1 + 42 + 0; 1 +
32 + 0); the 32-byte write cost 30–37 ticks per line; the 64-line reserve was
never approached. **The words, in order:** RUN 17 `0000`, then `0100`/`0000`,
`0200`/`0000` × 2, `0001` × 3, `0002` × 4, `0004` × 5, `0008` × 6 (each press a
word and its release) — walk A; RUN 18 `0100`, `0200` × 2, `0040` × 3, `0080`
× 4, `0020` × 5, `0010` × 6 — walk B; RUN 16 `0200` × 4, `0100` × 4, `0200` ×
4, `0100` × 4 — exactly the declared 4 × R, 4 × L, 4 × R, 4 × L; no other
word anywhere: the runtime sent no navigation press in any run (the machine's
answer to how each booted). First change at +5.773 / +5.557 / +8.309 s after
CONTROL, last at +14.499 / +17.518 / +19.921 s. **INPUT (§V7.1.8 gate, all
three MET):** `selftest=1 invalid=0 no_base=0 failed=0 retry=0 first=1
last_word=0000 last_rc=ok`; steps 184 953 / 184 956 / 184 929; attempts =
completed = 7 898 / 7 898 / 7 890; change 42 / 42 / 32; refresh 7 855 / 7 855
/ 7 857; `attempts = first + change + refresh + retry` in each; the descriptor
reported as data `0,1,2,3,4,5,6,7,9,8`, pressed = 1, unchanged since
`0ff8355` (ENVINPUT2's `desc_status` label still prints
`CORROBORATED_not_FACT`: a label of the image, now stale, recorded).
INPUTT 30/30/38 write ticks; step ticks 95/160/1106, 95/160/1100,
95/160/1105 (observational). **Transport:** unmasks = deliveries = acks =
re-arms 254 723 / 254 728 / 254 722; video 96 109/96 109; timeouts, busy,
overflow, uncertain, errors all 0; transport_ok 1; restore ok; WRITES irq
509 449 / 509 459 / 509 447 attempted = completed; transfers 1 033 033 /
1 033 048 / 1 033 022. **Startup** NORMAL, first hand-off 165.336148 /
165.338272 / 165.341407 ms (< 400 ms; recorded, no tolerance). **Policy A**
(inherited, recorded): join 2047 SELECTED_NEW, interior 0, reorder 0, depth
1; deferred 18 / 29, 18 / 25, 18 / 25; frozen p99 0.003753 / 0.003728 /
0.003728 ms, max 0.733506 / 0.585975 / 0.583210 ms — gates PASS; STREAMINV
189 258 / 189 264 / 189 210 checks, 0 failures; every sidecar with valid CRCs;
all three ended at `stop=witness_target_reached`. What this establishes: the
runtime wrote, and — for the first time — RECORDED WHAT IT WROTE at every
change, with the bound of GBP-KEY-010 holding as designed; what the cartridge
received is GBP-HW-269, and the join is GBP-HW-270.

---

### GBP-HW-268 — the Operator's channel for RUN 17 / RUN 18 / RUN 16: the tally vectors `1, 2, 0, 0, 0, 0, 6, 5, 3, 4` and `1, 2, 3, 4, 5, 6, 0, 0, 0, 0` ("the same numbers as RUN 14 / RUN 15"); RUN 16's report — the tabs moved under L and under R, the direction per trigger NOT reported; the controllers per run — OPERATOR OBSERVATION (literal, relayed by the Orchestrator)

Relayed in Issue #33 (2026-09-21) and recorded literally in
`HARDWARE_TESTS.md` §V7.4.2, beside the machine channel and never fed into
the join. RUN 17 (walk A, generic third-party pad): `1, 2, 0, 0, 0, 0, 6, 5,
3, 4` — "the same numbers as RUN 14"; RUN 18 (walk B, ORIGINAL Nintendo pad):
`1, 2, 3, 4, 5, 6, 0, 0, 0, 0` — "the same as RUN 15"; both equal the walks'
arithmetic expectation, L = 1 and R = 2 in both, relayed with 0 where the
instrument prints no tally (0 and the blank of GBP-HW-265 are one reading);
no walk cut, no tally moved without a press (as relayed); no live per-press
channel relayed. RUN 16 (the menu reading, ORIGINAL pad, executed last):
"as abas funcionaram perfeitamente; usei apenas L e R, não apertei mais
nada"; presses 4 × R, 4 × L, 4 × R, 4 × L. **The limit, recorded:** the
direction per trigger was NOT separately reported and no convention was
declared before booting (§V7.1.7 RUN 16 step 3); the report establishes that
both triggers reached the menu and produced tab movement he judged correct
and yields no per-direction datum; the Orchestrator asked once and received
the same substance twice; the direction is NOT inferred — from his words, from
the frames, or from RUN 17 / RUN 18's FACTs. The two vectors agree with the
machine-decoded end states of GBP-HW-269 digit for digit (stated, never
merged); the RUN 16 press pattern is exactly the word sequence the runtime
recorded (GBP-HW-267).

---

### GBP-HW-269 — the OGBPFULL1 frames of RUN 17 and RUN 18 carry the checker's tally screen, decoded pixel-exactly with the frozen parser to the walks' expectation, L = 1 and R = 2 in both; the end state stable from s2 / s3; RUN 16's frames carry the EZ-Flash menu, nothing about the tabs decoded — FACT (data, recomputable)

Under the UNMODIFIED `tools/vfull.py` (`load()`, `consumed_words()`) and the
§V7.2.6 six-glyph exact match, `HARDWARE_TESTS.md` §V7.4.6: every one of the
16 samples of RUN 17 / RUN 18 shows the checker's screen (title row 522 lit
pixels, three distinct words, background `0xc578`) and every tally cell
decodes; texture == the Python conversion in all 16 (and in RUN 16's 8).
RUN 17: s0 (+6.084 s) `1 · · · · · · · · ·`; s1 (+10.370 s) `1 2 · · · · · · 3
1`; s2 (+14.656 s) through s7 (+36.087 s) `1 2 · · · · 6 5 3 4` — FINAL from
s2, six identical samples after the last KEY line (+14.499 s). RUN 18: s0
`1 · …`; s1 `1 2 3 · …`; s2 `1 2 3 4 5 · …`; s3 (+18.943 s) through s7
`1 2 3 4 5 6 · · · ·` — FINAL from s3, five identical samples after the last
KEY line (+17.518 s). Both end states equal the walks' expectation with a
blank read as "never incremented" (the wording mismatch of GBP-HW-265,
recorded again) and agree with the Operator's vectors (GBP-HW-268) digit for
digit. **RUN 16:** s0 (+6.084 s) a near-blank screen (3 distinct words,
background `0xf7bd`, 1 005 lit pixels: the menu not yet on screen); s1–s7 a
rich screen (background `0x829a`, 92 / 83 / 127 / 83 / 83 / 83 / 83 distinct
words: the menu); all eight raw samples byte-distinct; the tally reader, run
anyway, ABORTS at s0 row 9 column 22 on a bitmap that is none of the six
glyphs — recorded verbatim in the struct fixture, never guessed; **nothing
about the tabs — which is selected, which way it moved — is decoded** (RUN
16's direction was not reported and is not inferred from pixels). The tools'
own verdicts (vindex INCONCLUSIVE_TOO_FEW_INTACT_FRAMES, vfull INCONCLUSIVE:
the oracle is OGBPCOORD1) are recorded, not judged; RUN 16's frames 357–410
carry the `sync` reason instead of `symbol` (the boot-screen frames before
the menu), recorded. Classification held from GBP-HW-264: FACT as data,
reproducible from the versioned fixtures with the frozen parser; and, with
the run's own KEY record, one of the two machine ends of the join.

---

### GBP-HW-270 — GBP-INPUT-002 verdicts: Question J = FACT for every pressed word bit in RUN 17 (bits 0, 1, 2, 3, 8, 9) and in RUN 18 (bits 4, 5, 6, 7, 8, 9) — the runtime's KEY record joined to the checker's decoded counters by machine at both ends: the GBS-DOL delivers each KEYPAD word bit to the AGB key the descriptor assigns, L at bit 8 and R at bit 9, on two independent controllers; Question I EXACT in every interval; the channels agree; RUN 16 UNDECIDED by the rule, M = PASS, O NOT READABLE — FACT (the verdict record) · FACT (hw, the runs: the routing)

Read from `HARDWARE_TESTS.md` §V7.3.9 as frozen before the runs (Issue
#28), computed in §V7.4.7 and recomputed by `tests/host/test_run17.py` from
the versioned fixtures (every KEY line verbatim; the full frames
byte-identical). **The join:** for each run, R_b = the number of 0 → 1
transitions of word bit b across the completed words (`rc=ok`, n order, from
`0000`); T_c = the count at counter c in the END STATE — the tally vector
common to every sample after the last completed KEY line, at least two,
identical (six in RUN 17, five in RUN 18); c(b) = the descriptor's expected
key. RUN 17: R_8 (L) = 1, R_9 (R) = 2, R_0 (A) = 3, R_1 (B) = 4, R_2 (SELECT)
= 5, R_3 (START) = 6, every other bit 0; end state L 1, R 2, START 6, SELECT
5, A 3, B 4, the rest blank; sum 21 = 21. RUN 18: R_8 = 1, R_9 = 2, R_6 (UP)
= 3, R_7 (DOWN) = 4, R_5 (LEFT) = 5, R_4 (RIGHT) = 6; end state L 1, R 2, UP
3, DOWN 4, LEFT 5, RIGHT 6, the rest blank; sum 21 = 21. In both: every
pressed bit's total distinct from every other pressed bit's; exactly one
counter reads each total; that counter is c(b) in every case; no counter
moved by a value no pressed bit was sent; every unpressed counter blank.
**Question J = FACT for all twelve readings** (bits 8 and 9 in both runs);
FACT-SWAPPED, NOT CLOSED and UNDECIDED did not arise; the assumptions A1–A3
were not contradicted. MEANS: on this hardware the GBS-DOL delivers KEYPAD
word bit b to the AGB's key c(b) for b = 0…9 — bits 0–3 through the generic
third-party pad (RUN 17), bits 4–7 through the original Nintendo pad (RUN
18), bits 8 and 9 through BOTH (RUN 17 generic, RUN 18 original) — the
descriptor's assignment is the measured one, bit 8 = L and bit 9 = R
included, with no human count in the chain: descriptor (code) → the KEY
record (the runtime's own log) → the counters (the frames) → arithmetic.
**Question I (recorded, never a gate):** EXACT in all sixteen intervals —
each interval's counter increments equal the rising edges whose `t_attempt`
falls in it, button for button; no press within B = 3 source frames of a
boundary, so NO observation of the write-to-display delay's order of
magnitude arose and NO latency figure is derived. **Question M = PASS and
Question O = AS-ASSIGNED** in RUN 17 and RUN 18, read from the Operator's
vectors alone (GBP-HW-268); the vectors and the decoded end states agree
digit for digit, stated, never merged. **RUN 16:** R_8 = R_9 = 8 (4 + 4
presses each), not distinct — **UNDECIDED** for bits 8 and 9 by §V7.3.9's own
rule, and the frames carry no tally: the verdict working, not a failure (RUN
16 was never designed for the join); **M = PASS** on §V7.1.9's RUN 16 terms
from the Operator's report (the tab moved under L and under R); **O = NOT
READABLE** (no convention declared before booting, no direction per trigger
reported — the datum does not exist; not inferred). **Scope, stated where
the verdicts are read:** both pads read by their digital click
(`trigger_threshold=0`); bits 8 and 9 are bound on two independent
controllers, which lifts the generic-pad limit of GBP-HW-265 for L and R
only; bits 0–3 are bound on the generic pad only and bits 4–7 on the original
pad only. **What this does not establish:** input latency of any kind; the
refresh's necessity; the stick threshold or any policy value as more than
policy; any pad beyond the two declared, any other port or cartridge; RUN
16's direction; rumble, the Link Port, audio, the display chain; Phase 5's
acceptance criterion (a real game, NOT assessed). Consequences, made by the
ingestion under Issue #33 (§V7.3.10): GBP-KEY-004's row promoted by its own
falsifier's outcome; `REGISTERS.md` §2 / §2.3, `GBS-DOL.md`,
`ARCHITECTURE.md`, `INITIALIZATION.md` §15 and `INPUT.md` carry F (hw,
run-scoped) with the history kept; U-GBP-010 stays CLOSED, now on a machine
record; the descriptor's data unchanged (it was right); the `desc_status`
label the image prints is stale (recorded, not changed). Classified against
the frozen text; no gate, threshold or verdict definition moved after the
data was seen.

---

### GBP-HW-271 — the Operator reports that the runtime now boots showing the Game Boy boot logo, no checkerboard, and that it is "fazendo o boot semelhante ao comportamento do Startup disc e GBI" — OPERATOR OBSERVATION (qualitative, not a measurement; confirms what §V5.57 explicitly declined to claim; the presentation-parity comparison is Phase 9 work, not started)

Relayed by the Orchestrator with Issue #33 (2026-09-21), from the RUN 16 /
17 / 18 session on `stream-0015`. Two halves, kept apart. **The logo:** the
records predicted the mechanism and explicitly declined the claim — §V5.57,
"Not claimed: that a boot logo will appear — that depends on the cartridge" —
and `vstate-0001` had captured the animated logotype without the wait
(GBP-HW-074…087); the observation therefore confirms something the project
deliberately left open, on the EZ-Flash cartridge, by eye. **The parity:**
the project documents the Start-up Disc's and GBI's INITIALISATION SEQUENCES
(`docs/protocol/INITIALIZATION.md`) and has never recorded a comparison of
how startup PRESENTS to a user, which is the parity `CLAUDE.md` §2 sets as
the goal; the Operator's judgement of similarity is the first such statement
on record. **Limits:** a qualitative judgement, not a measurement; it does
not say the sequences match, and nothing here compares frames, timings or
the sequence of screens. What would make it more: a frame-by-frame
comparison of the three (Open-GBP, the Disc, GBI) on the same cartridge —
Phase 9 work, not started, not pre-registered. No status changes; no
consolidated page moves on this row.

---

### GBP-HW-272 — the original CONTROL byte splits all 34 archived physical logs exactly at bit `0x02`: the 12 cartridge-less runs read `0x90`, the 22 runs with a cartridge read `0x92` — **FACT for the split**; that the bit REPORTS Game Pak presence is **HYPOTHESIS**, with an empty diagonal and a named breaker — **2026-09-22, Issue #47: the empty diagonal cell filled by RUN 23 (GBP-HW-273), so CLAIM 2 moved HYPOTHESIS → CORROBORATED in the amendment at the end of this entry — read it before copying a status from these words; CLAIM 1 unchanged and now over 36 logs; still NOT FACT**

Found in the archive by Issue #31 while writing `GBC_PATH.md` §3, which
offered it and promoted nothing; recomputed independently by the Orchestrator;
promoted here under Issue #46. **No hardware was run for it: every byte was
already on disk.**

**CLAIM 1 — the split. FACT.** Every Open-GBP probe from `init-0001` onward
records the original CONTROL byte before it writes anything, as
`CONTROL semantic orig=<byte> exp=<byte> method=gbi-majority-vote
transform=(v&~10)|0c`. Over the 34 physical logs in `captures/local/`:

```text
orig = 0x90   12 logs   init-0001, initirq-0001, initirqa-0001, initirqb-0001, initirq4-0001, avsvc-0001, video-0001,
                        vstate-0001, vstate-0002, vstate-0003, vstate-0004, vstate-prewait-5000
orig = 0x92   22 logs   color-0001, color-0002, stream-0003, stream-0004, stream-0005, stream-0005-run2,
                        stream-0005-run3, stream-0006-run4, stream-0007-run5, stream-0008-run6, stream-0009-run7,
                        stream-0009-run8, stream-0010-run9, stream-0010-run10, stream-0011-run11, stream-0013-run12,
                        stream-0013-run13, stream-0014-run14, stream-0014-run15, stream-0015-run16,
                        stream-0015-run17, stream-0015-run18
difference              bit 0x02, and nothing else: 0x90 ^ 0x92 == 0x02, in every one of the 34, with no exception in
                        either direction
bit 0x01                reads 0 in ALL 34. One observed state is not a result: every run used no cartridge or a GBA
                        cartridge, so the type bit has never been seen in its other state (GBC_PATH.md §4.1).
```

**The selection rule is mechanical, not curated: every log in
`captures/local/` that carries the field, all of them.** The directory holds 40
files and 6 carry no such record — `probe-0001` and its transcript and the two
`smoke-0002` logs, which predate the record; and the two runs made deliberately
with no Game Boy Player attached (`init-0001-semGBP`, `probe-0001` of
`GBP-BASELINE-NOGBP-001`), where the probe aborts at `DET verdict=absent` /
`status=abort_not_present` before any register is read. **None of the six was
dropped by a judgement about what it showed**; there is nothing to drop,
because the device was not there or the field did not yet exist.

The 12 are the era before the physical ROM delivery route existed (§V3.7) and
are cartridge-less **by their own records** — GBP-VIDEO-002's normative
question is *"in a session WITHOUT a Game Pak…"* (`gbp_vstate_probe.h`), and
the early setups are recorded as "no cartridge" in `HARDWARE_TESTS.md`. The 22
are every run from the moment a cartridge was in the slot. **This is FACT
because anyone can re-derive it from the files**, not because of who found it:

```text
grep -ho 'CONTROL semantic orig=[0-9a-f]*' captures/local/*.log | sort | uniq -c
     12 CONTROL semantic orig=90
     22 CONTROL semantic orig=92
```

**That output is the archive AS IT STOOD when this entry was written.** It grew
the same day; the amendment below carries the current counts and the same
command produces them.

**CLAIM 2 — that bit `0x02` reports Game Pak presence. HYPOTHESIS. Not FACT,
and not CORROBORATED either.** The two-by-two has an empty diagonal:

```text
                  early builds      late builds (color / stream)
no Game Pak       12 logs  0x90     NONE
Game Pak          NONE              22 logs  0x92
```

"Bit `0x02` tracks the cartridge" and "bit `0x02` tracks something the later
builds do at startup" are **not separated by this archive**. What makes the
second unlikely rather than excluded: the record has the same form and position
in both families, is taken before any experimental write, and `exp` is the
deterministic `(orig & ~0x10) | 0x0C` in both — nothing in the later builds
transforms `orig`. Unlikely is not measured.

**And Dolphin is not corroboration for this.** Its `CART_INSERTED` names
CONTROL bit `0x02` in its own model, but its *"GamePak source"* is bit 2 of the
**IRQ** register (index `0xD`) — a different bit in a different register, and
whether the two are related is open. The Start-up Disc's "present" status flag
and GBI's "Game Pak" string are one line of reasoning about what the SOFTWARE
does with the bit (`GBP-CTL-001`, CORROBORATED for usage), not a second
independent measurement of what the DEVICE reports.

**THE BREAKER, named so nobody rediscovers it: one boot of `12-stream` with
the cartridge REMOVED** fills the empty "late build, no Game Pak" cell. It
needs no new build, no new code and no new write — `12-stream` is staged, has
run five times, and logs the field. `play-0001` cannot do it (it logs
`t_control`, not the byte). **Not pre-registered and not authorised here**; it
is not folded into RUN 21 / RUN 22, whose one variable is the controller and
whose cartridge must be identical in both.

**What this answers, and what it leaves open.** `U-GBP-017`'s Needs list has
read *"repeat run, run with a cartridge, run after a controlled stop
sequence"* since 2026-09-14; **the second item is answered from the archive for
bit `0x02` only**, and the item stays OPEN at P2 — `0x10`, `0x80` and `0x94`
are untouched by this, and so is the meaning of the other bits of `0x90`.

**THE RECONCILIATION SWEEP (`RESEARCH_METHOD.md`), run before this entry was
written, outcome recorded INCLUDING "nothing".** `tools/reconcile.py` was run
over `GBP-CTL-001`, `GBP-HW-004`, `GBP-HW-005`, `GBP-HW-024` and `U-GBP-017`,
and the consolidated pages that speak about CONTROL were read against it:
`REGISTERS.md` §3, `GBS-DOL.md`, `ARCHITECTURE.md`'s control/status row.
**Nothing had to be corrected, relocated or weakened, and that is the finding
rather than an absence of one** — because every existing statement is about the
REFERENCES' USAGE of the bit (`GBP-CTL-001`: "CORROBORATED for usage of
0x01–0x10"; `ARCHITECTURE.md`: "C for usage, H for names") and this entry is
about the DEVICE'S OWN BYTE. Two different propositions about the same bit, so
neither displaces the other and both stay on the page. **If the sweep had found
a page asserting the causal claim, that page would have been corrected here.**
The sweep also improved its own tool: it printed "-" for every entry whose
status lives in a body `**Status:**` line rather than in the heading, which is
how the older entries are written, so `tools/reconcile.py` now reads that line
and reports a compound status verbatim instead of collapsing it to a letter.

**Limits.** One console, one Game Boy Player, one flashcart as the only
cartridge ever inserted; one instant of one sequence (before the first
experimental write); nothing about a GB/GBC cartridge, another cartridge, or
another unit. No consolidated page gains a causal claim from this row:
`REGISTERS.md` §3 carries the split as `F (hw, 34 logs)` beside the references'
usage `C`, and the causal reading as `H`.

**AMENDMENT 2026-09-22 (GitHub Issue #47), the same day, written on top and
changing nothing above it.** The empty cell was filled the morning this entry
was written, by two runs the Operator performed on his own initiative before
either of us knew of them. **RUN 23 is a LATE build (`stream-0015`) with NO
Game Pak and it reads `0x90`** (`GBP-HW-273`). The rival reading this entry
could not exclude — "bit `0x02` tracks something the later builds do at
startup" — is therefore **DISCONFIRMED BY MEASUREMENT**, not argued away, and
the two-by-two now has three of its four cells filled with the fourth (an
early build with a Game Pak) unobtainable, since those builds are historical.
**CLAIM 2 accordingly moves from HYPOTHESIS to CORROBORATED** — the three
references' usage and the hardware contrast across 35 runs and both build eras
now agree, which is this project's definition of the status — and it is still
NOT FACT: presence is inferred from a correlation with what was in the slot,
on one console, one Game Boy Player and two kinds of cartridge, never from
watching the bit change while the cartridge changed and nothing else did.
**That remains the named falsifier**, and it is the one experiment this entry
asked for. CLAIM 1 is untouched: it was FACT over 34 logs and is FACT over 36,
and the same one-line derivation now prints

```text
grep -ho 'CONTROL semantic orig=[0-9a-f]*' captures/local/*.log | sort | uniq -c
     13 CONTROL semantic orig=90
     33 CONTROL semantic orig=92
```

The six logs added the same day are RUN 23 (`stream-0015-run23`, no cartridge,
`0x90`), RUN 24 (`stream-0015-run24`, a Game Boy Color cartridge, `0x92`), and
the four sessions of **RUN 21, RUN 22, RUN 25 and RUN 26** (`play-0001-run21`,
`play-0001-run22`, `play-0001-run25` and `play-0001-run26`, a GBA cartridge,
`0x92` — GitHub Issue #52). **The last four are a THIRD IMAGE**: `play-0001` is not `stream-0015`
and carries none of its research instrumentation, yet it records the same field
and falls in the same family, so the split now holds over **43 logs across
three images and both build eras** — the latest are RUN 27, RUN 28 and RUN 29
(`stream-0015-run27`, `stream-0015-run28` and `stream-0015-run29`; three
different GB/GBC cartridges, all `0x92`, GitHub Issue #55). **Bit `0x01` is still 0 in all 43 ORIGINAL
bytes** — RUN 24 sets it only later, which is `GBP-HW-275` and not this
entry's subject.

**2026-09-22, Issue #62 — a FOURTH IMAGE, and the split holds.** RUN 30
(`stream-0016-run30`, the audio window image, a GBA flash cartridge in the
slot) records `orig=92`, so the count above is now **13 at `0x90` and 31 at
`0x92`, 44 logs across four images.** `stream-0016` shares `stream-0015`'s
service path and none of its research instrumentation, and it is the first
image of the family built for a question that is not video. **CLAIM 1 stays
FACT and gains a log; CLAIM 2's status is untouched by it** — a 44th
cartridge-present log reading `0x92` adds a sample to the same cell, not a new
kind of evidence, and the diagonal it would take to move CLAIM 2 is the one
`GBP-HW-273` already filled.

**2026-09-22, Issue #67 — RUN 31 (`stream-0016-run31`) makes it 45 logs, and
the cartridge is this project's own.** The same image on `stimulus/agb-tone`, a ROM this project
wrote and delivered through the flashcart, records `orig=92`: **13 at `0x90`
and 32 at `0x92`.** It adds nothing to CLAIM 2 — another cartridge-present log
is another sample in the same cell — but it is the first entry in the family
whose cartridge content is entirely under this project's control, which is
worth noting for any future attempt on the diagonal.


**2026-09-23, Issue #72 — RUN 32 (`stream-0016-run32`) makes it 46 logs**, on
`stimulus/agb-sweep`, again a cartridge whose content is entirely this
project's: **13 at `0x90` and 33 at `0x92`**, from the same one-line derivation
above. **CLAIM 1 stays FACT and gains a log; CLAIM 2's status is untouched** —
a 46th cartridge-present log reading `0x92` is another sample in a cell that is
already full.
---

### GBP-HW-273 — RUN 23: a LATE build with NO Game Pak reads CONTROL `0x90` — the empty diagonal cell of `GBP-HW-272` filled, and the build-era reading disconfirmed by measurement — FACT (recomputable from the archived log)

Executed 2026-09-22 by the Operator on his own initiative, **NOT
pre-registered** (§V7.7 states that plainly and what it costs). `stream-0015`
(`da06500`), the image already staged in the `12-stream` slot, with no
cartridge in the machine; log 91 182 B
`83b4f0e706c6a7d4538a730b9b88009017146bc90ca37ec1beb83afacebecaea`.

```text
000031 RAW BASE idx=4 ... sem_vote=90 sem_b1f=90
000034 CONTROL semantic orig=90 exp=8c method=gbi-majority-vote transform=(v&~10)|0c
```

**What it settles.** `GBP-HW-272` recorded 12 cartridge-less logs at `0x90`
and 22 cartridge logs at `0x92` and could not separate CARTRIDGE from BUILD
ERA, because every cartridge-less log came from an early build. This run is
the same late build as 11 of the `0x92` logs, run with an empty slot, and it
reads `0x90`. **A build-era explanation now contradicts a measurement.**

**What it does not settle.** That the bit *reports* presence remains an
inference from correlation; see `GBP-HW-272`'s amendment for the status
argument and the falsifier. Nothing here speaks about `0x10`, `0x80` or
`0x94`.

**The Operator's channel, kept as his:** *"rodei o 12-stream sem cartucho. ele
chamou o boot logo do Gameboy Advance, e não avançou mais, comportamento
similar ao console e esperado."* — **OPERATOR OBSERVATION**, his words,
consistent with a real console with an empty slot and not a measurement by
this project. The machine record is the byte above.

---

### GBP-HW-274 — RUN 24: with a **Game Boy Color** Game Pak inserted the ORIGINAL CONTROL byte is `0x92`, bit `0x01` CLEAR — the same byte a Game Boy Advance cartridge gives, so at the power-on read point the byte does not distinguish the two media — FACT (recomputable), and a NEGATIVE that closes a stated expectation — **2026-09-22, Issue #55: REPRODUCED by RUN 27 with a guaranteed power cycle, element for element; the preceding-state confound CLOSED; the MEANING still C, not F, on this entry's own condition — a second, different GB/GBC cartridge — read the amendment at the end of this entry before copying a status**

Executed 2026-09-22 by the Operator on his own initiative, **NOT
pre-registered**. Same image `stream-0015` (`da06500`), a **Pokémon Crystal
(JP)** Game Boy Color cartridge in the slot (his declaration; the title is
his, not read by any instrument here); log 22 415 B
`8599bc0f5b57999bd0d368d31f6d5e41734192ce499304fe417dc0e71227f443`.

```text
000031 RAW BASE idx=4 ... sem_vote=92 sem_b1f=92
000034 CONTROL semantic orig=92 exp=8e method=gbi-majority-vote transform=(v&~10)|0c
```

**Why this is a result and not a disappointment.** `GBC_PATH.md` §3 stated the
expectation in advance and in public (commit `f99bc96`, before these runs
existed): bit `0x01` had read 0 in all 34 archived logs because every run used
no cartridge or a GBA cartridge, and the other state was named *"THE GAP A
GB/GBC BOOT FILLS"*. The gap is filled and the answer at that read point is
**NO**: `0x92`, bit `0x01` clear, byte-identical to what 22 GBA-cartridge runs
give. **A prediction that fails is evidence.**

**Read this narrowly.** It is a statement about ONE read point — the original
byte, sampled before any write — and `GBP-HW-275` shows the same run answering
differently a fraction of a millisecond later. It says nothing about whether
the Game Pak was sensed at all, and nothing about GB/GBC mode.

**AMENDMENT 2026-09-22 (GitHub Issue #55): three more runs, three distinct
cartridges.** RUN 27 (the same cartridge, a guaranteed power cycle), RUN 28 (an
Everdrive GB X7) and RUN 29 (an unofficial *Samurai Spirits*, a **DMG**
cartridge) all read `orig=92 exp=8e` — **the original byte is `0x92` with bit
`0x01` CLEAR in every one**, so this entry's observation now rests on four runs
across three cartridges and two media families. **It is the reason the FACT of
`GBP-HW-275` must always carry "the bit is NOT in the original byte"**: a
reader who samples CONTROL before the transform write learns nothing about the
medium. §V7.10.

---

### GBP-HW-275 — RUN 24: bit `0x01` of CONTROL becomes 1 **after** the transform write, within 186–636 µs, and stays set through teardown — while four GBA-cartridge runs and one cartridge-less run of the same build hold their value — FACT for the transition and the contrast; the MEANING stays an inference — **2026-09-22, Issue #55: REPRODUCED by RUN 27 with a guaranteed power cycle, element for element; the preceding-state confound CLOSED; the MEANING still C, not F, on this entry's own condition — a second, different GB/GBC cartridge — read the amendment at the end of this entry before copying a status**

The whole trajectory, majority vote over the 32 replicas, one run per column:

```text
                       RUN 23          RUN 24          RUN 18 / RUN 17 / RUN 15 / color-0002
                       no Game Pak     GBC Game Pak    GBA Game Pak (four runs)
BASE   (original)      90              92              92
       written (exp)   8c              8e              8e
P0                     8c              8e              8e
A1-0                   8c              8e              8e
A1-50US                8c              8e              8e
A1-500US               8c              8f   <- HERE    8e
A2-0 / A2-50MS         8c              8f              8e
EVENT / PREUNMASK      8c              8f              8e
restore: wrote / read  90 / 90 ok      92 / 93 FAIL    92 / 92 ok
```

**The window.** The `SNAP` records bound it: `since_control=7518` ticks at
`A1-50US` (still `0x8e`) and `since_control=25742` at `A1-500US` (already
`0x8f`), at `tb_hz=40500000` — **between 185.6 µs and 635.6 µs after the
CONTROL transform write**, equivalently 50.1 µs to 500.0 µs after the `A1` IRQ
write. It is not instantaneous with the write and it is not late.

**Why the contrast carries weight.** The same binary, the same fixed sequence
and the same read points are exercised by five other physical runs in this
archive. Four of them have a GBA cartridge and hold `0x8e` at every one of
those points; one has an empty slot and holds `0x8c`. **The only run in which
any bit of the byte changes under the runtime's feet is the one with the
GB/GBC cartridge**, and the change is bit `0x01` — the bit the Disc reads as a
"type" flag, GBI uses to choose between the strings "Game Boy" and "Game Boy
Advance", and Dolphin's model names `CART_IS_GB` (`REGISTERS.md` §3,
`GBP-CTL-001`).

**Replica 0 is excluded deliberately and it matters.** The first of the 32
replicas is noisy in every run of this family — `8a` against `8c` in RUN 23,
`be` then `fe` then `be` in RUN 18, `ee`/`ef` in RUN 24 — which is why the
runtime takes a majority. **In RUN 24 the change is in all 31 stable replicas
as well as in replica 0**, which is what makes it a reading of the device
rather than of the anomaly.

**AND THE CLAIM IS UNANIMITY AND PERSISTENCE, NOT THE VALUE.** Checking those
replicas turned up four reads, out of 48 across these six runs, where one of
the 31 deviates — and **two of them are an isolated replica reading `0x8f` in
RUN 17, which had a GBA cartridge** (`A2-50MS` replica 26, `PREUNMASK` replica
20; the other two are RUN 23 `A2-50MS` replica 14 = `8a` and RUN 15 `P0`
replica 18 = `9e`). **So a single replica showing `0x8f` proves nothing**, and
anyone reading these logs later must not take one for the type bit. What is
unique to RUN 24 is that the change is **unanimous across all 32 replicas** and
**persists from `A1-500US` to the end of the run**, including the restore
read-back. §V7.7 carries the list and a host test pins it exactly.

**Status, argued.** The transition, the window and the five-run contrast are
**FACT**: they recompute from the archived files with no interpretation. That
the bit **means** "a GB/GBC Game Pak is present" is an inference, and with the
three references agreeing on that usage it is **CORROBORATED, not FACT** — one
run, one cartridge, one console, one Game Boy Player. **What would make it
FACT:** a repeat with the same cartridge and a run with a second, different
GB/GBC cartridge, and the same window measured again.

**What is NOT established, and must not be read into this.** Why the bit
appears late rather than at the original read. Whether the transform's power /
reset bits (`0x04`/`0x08`) cause the sensing, or whether time or the `A1`
write does. Whether a GBA cartridge would ever set it. Anything about GB/GBC
video, input, audio, timing or mode entry. See `U-GBP-036`.

**AMENDMENT 2026-09-22 (GitHub Issue #55) — three more runs, three distinct
cartridges, one confound closed, one candidate pair excluded, and THE MEANING
MOVED TO FACT with its scope stated.**

**The runs.** RUN 27 repeated RUN 24 with the same cartridge and **a power
cycle the Operator guaranteed beforehand**, unprompted; RUN 28 used an
**Everdrive GB X7**; RUN 29 an unofficial ***Samurai Spirits***, a **DMG**
cartridge through the GBC's backward compatibility. All four give `orig=92
exp=8e` — bit `0x01` **clear in the original byte, every time** — then the bit
set, persisting to the end, with `PREUNMASK ok=0 reason=control_changed` and
the restore writing `0x92` and reading `0x93` in every one (§V7.10).

**WHAT CLOSES.** RUN 24's console state beforehand was never declared, so
*"something the previous session left behind"* was an available explanation for
the late arrival. **It is no longer available**: RUN 27 guaranteed the power
cycle and the bit still arrives late.

**THE NEW FINDING — the arrival window is CARTRIDGE-DEPENDENT, and the two
windows are DISJOINT.** The three ordinary cartridges flip between 185 µs and
636 µs after the transform write; the **Everdrive flips between 698 µs and
1148 µs**, three probe points later, with no overlap. The probe's sequence is
identical in all four runs, so **elapsed time alone and the `A1` write alone
are both EXCLUDED as sufficient explanations** — each predicts the same window
for every cartridge. What remains is **the cartridge/AGB side**. That is the
first separation among `U-GBP-036`'s three candidates, and **it does not close
the item**: one flashcart against three ordinary cartridges is a contrast, not
a mechanism.

**A NEGATIVE RESULT.** RUN 29's DMG cartridge behaves **identically** to the
CGB title of RUN 24 and RUN 27. **At this read point the bit separates the
GB/GBC family from Game Boy Advance and nothing finer: it does not distinguish
DMG from CGB.**

**THE STATUS, ARGUED RATHER THAN AWARDED.** This entry set its own bar before
any of these runs existed — *"a repeat with the same cartridge **and** a run
with a second, different GB/GBC cartridge"* — and the bar is met twice over:
one repeat and **three distinct cartridges**. A bar being met is a reason to
write the argument, not a substitute for it, so here it is.

```text
WHAT BECOMES FACT   with GB/GBC media in the slot, CONTROL bit 0x01 reads 1 after the transform write and
  (hw, four runs,   holds to the end of the run; with a Game Boy Advance cartridge, or with an empty slot, it
   three cartridges) reads 0 throughout. DIRECTLY MEASURED in every case, never inferred from a model: four
                    GB/GBC runs across three cartridges and two media families (CGB and DMG) against four
                    GBA-cartridge runs and one cartridge-less run of the same image.
WHY THIS IS NOT     bit 0x02's causal step stayed CORROBORATED because a rival explanation -- the build era --
 BIT 0x02's CASE    was not excluded by the archive. Here no rival survives: the cartridge is the only thing
                    that varied, the contrast is complete over three slot states, and the one remaining
                    alternative reading -- that the bit follows what the AGB DOES with the medium rather than
                    what is inserted -- is a REFINEMENT of the same observation and is named below rather
                    than left implicit.
THE SCOPE, WHICH    one console, one Game Boy Player; this read sequence and no other; and -- the part that
 TRAVELS WITH IT    must never be dropped -- THE BIT IS NOT IN THE ORIGINAL BYTE. A reader who samples CONTROL
                    before the transform write gets 0x92 and learns nothing about the medium (GBP-HW-274).
WHAT STAYS OPEN     WHY it arrives late and WHAT triggers it (U-GBP-036, narrowed but open). Whether the bit
                    reports the MEDIUM or the AGB's response to it -- and RUN 28's cartridge-dependent window
                    is evidence for the second, since a static slot property would not move with the
                    cartridge. Nothing about DMG versus CGB, which this run shows it does not carry.
```

**So the MEANING moves from CORROBORATED to FACT, stated as the observation it
is and scoped as above** — and `REGISTERS.md` §3 carries it with the same
scope. The refinement in the last row is why the FACT is worded as *"reads 1
with GB/GBC media in the slot"* and not as *"reports the cartridge type"*: the
first is what was measured, the second is a name for it.

---

### GBP-HW-276 — RUN 24 captured nothing because the runtime's own pre-unmask guard refused the session: `PREUNMASK ok=0 reason=control_changed`, teardown `S2_before_unmask`, zero unmasks — the machine explanation for five near-empty files, and a restore that failed for the same reason — FACT (read from the log)

The Operator reported that the GBC run *"nem chamou o boot logo do
GameBoy... ficou só no terminal (tela com textos) e apareceu a opção para
gerar o log direto"* (**OPERATOR OBSERVATION**). The log gives the mechanism
and it is not a defect:

```text
000098 PREUNMASK ok=0 reason=control_changed ... control=8f irq=0500/0500
000099 TEARDOWN start control_written=1 irq_attempted=2 irq_completed=2 uncertain_writes=0
000102 CONTROL restore semantic=92 rc=ok readback_rc=ok readback_vote=93 readback_b1f=93 ok=0
000121 VSTATE end status=anomaly_control_changed class=anomaly reason=control_changed_PREUNMASK
       stop=failure restore=error restore_reason=control_restore_failed teardown=S2_before_unmask
       power_cycle_required=1 errors=0 transport_ok=1
```

**The chain, end to end.** The runtime writes `0x8e` and, before installing
the handler and unmasking, re-reads CONTROL and compares it with what it
wrote. The device is reporting `0x8f` (`GBP-HW-275`), so the guard refuses,
the run takes the teardown path at stage S2, **no handler is unmasked
(`unmasks=0`), no service cycle runs, no frame is captured** — hence
`t_capture_start=0`, `STREAMWIT records=0/2048`, `VISTORE handed=0`,
`DISPSRC handoffs=0`, and the four sidecars holding nothing but their headers
(396 / 460 / 268 / 268 B against RUN 23's 8 946 060 / 401 372 / 1 844 492 /
152 524). The text console with the save option is the teardown's own screen.
**No boot logo appeared because no frame was ever captured or presented**, not
because the AGB was known to be held in reset — that part is not measured.

**The restore failure has the same single cause.** The runtime writes the
original `0x92` back and reads `0x93`: bit `0x01` is still set, so
`control_restore_ok=0` and `power_cycle_required=1`. **The device is reporting
a bit the runtime never wrote**, which is the guard working, not a runtime
defect. The hardware-safety consequence is recorded in §V7.7: a console left
in that state is power-cycled before the next run.

**`transport_ok=1` and `errors=0` throughout**, `dropped=0 truncated=0`, the
log complete to its `# --- end ---`: nothing about the transport, the log or
the media is implicated.

---

### GBP-HW-277 — RUN 23: the full streaming path reaches its witness target with NO Game Pak — 2048 / 2048 records, `stop=witness_target_reached`, restore ok, 0 errors — FACT (read from the log)

```text
000250 VSTATE end status=ok_structured_change_observed class=ok reason=- stop=witness_target_reached
       restore=ok teardown=S5_witness_target power_cycle_required=1 errors=0 transport_ok=1
000685 STREAMWIT records=2048/2048 target=2048 frames_seen=2048 discarded=0 target_reached=1
000679 VISTORE handed=2379 latched=2372 superseded=6 overflow=0
000681 DISPSRC handoffs=2379 deferred_frames=31 defer_attempts=44 dropped_interior=0 order_violations=0
```

254 746 unmasks, a clean restore (`control_restore_ok=1`, readback `0x90`), and
the four sidecars at full size. **The video capture path does not need a Game
Pak**: with an empty slot the AGB produces its own screen and the GBS-DOL
delivers 2379 frames of it through the same path, to the same target, with the
same accounting as a cartridge run. Previously every cartridge-less run in the
archive came from an early build that never reached this stage, so this is the
first time the streaming path has been exercised without media.

**Not claimed:** anything about the content of those frames, which no
instrument in this run judged; any comparison with a cartridge run's picture;
any acceptance criterion.

---

### GBP-HW-278 — RUN 21 / RUN 22 / RUN 25 / RUN 26: **four sessions**, their artifacts and identity, and what the Operator actually did — §V7.6.9 performed in two halves, in separate sessions — FACT (artifacts, identity, the split as recorded) · OPERATOR OBSERVATION (his reports)

Executed 2026-09-22 on `play-0001` (`2e48ca7`), the image §V7.6.5 names, NOT
rebuilt. Archived first under the reserved names, both drops carrying the same
filename: RUN 21 log 195 301 B
`cae3ecfcd16ae319ad19968190560f900c0989ed7463f54da45e1dd5a4fc09c4`, RUN 22 log
168 773 B `a7bf2dbf014b6dca059e7b6a436e6bd81a1b01b28310bbd383cdea7b0d005c14`;
both complete (`dropped=0 truncated=0`, closing `# --- end ---`); both matching
the Orchestrator's independent hashes. Cartridge **Yoshi's Island — Super Mario
Advance 3** in both (his declaration); **RUN 21 the ORIGINAL pad, RUN 22 the
GENERIC pad**, §V7.6.6's one variable.

**WHAT WAS DONE.** The Operator performed the pre-registered list **in two
halves, in separate sessions**: *"apenas abri o jogo e fiz uma jogatina
normal.. na 22 usei a saida pelo Z, na 21 ele saiu automatico"* and *"favor
olhar os logs com -head no fim do nome... esses foram os que fiz HEAD e depois
Z"* — **OPERATOR OBSERVATION**, both messages, recorded as what was done and
never as a fault of his or of the runs.

```text
RUN 21  ORIGINAL pad  ordinary play only (step 13)    ended event_store_cap   195 301 B  cae3ecfc...09c4
RUN 22  GENERIC  pad  ordinary play only (step 13)    ended Z                 168 773 B  a7bf2dbf...5c14
RUN 25  GENERIC  pad  the scripted head (steps 2-12)  ended Z                  94 398 B  70b24767...42a2
RUN 26  ORIGINAL pad  the scripted head (steps 2-12)  ended Z                  94 354 B  5fb2161b...2f15d
```

**The numbering does not encode the pad.** RUN 21 / RUN 22 keep the meaning the
Operator's folders give them; the head sessions take the next free numbers **by
the logs' own time base** (`t_control` `7959be75…` before `7959c04e…`), which
puts the generic pad at RUN 25 and the original at RUN 26 and therefore inverts
the pad order of the first pair. **By the same time base the generic pad ran
before the original in BOTH pairs**, the reverse of the order §V7.6's numbering
suggests; recorded as a deviation, and **no gate depends on execution order**
(§V7.8.1).

---

### GBP-HW-279 — every one of the ten KEYPAD word bits rose on both pads during ordinary play: R_b per bit per run, the pre-registered reading of step 13 — FACT (recomputable from the two logs)

§V7.6.11 provides for exactly this: step 13's words *"are reported as counts
per bit and never compared press for press"*. Recomputed with `tools/v7611.py`
from each log alone (a `KEY` line counts only with `rc=ok`, the completed words
in `n` order from `0000`, R_b = the rising edges of bit b):

```text
START 7 / 2 · A 118 / 83 · B 54 / 22 · SELECT 9 / 2 · RIGHT 94 / 62 · LEFT 66 / 45
UP 6 / 34 · DOWN 17 / 14 · L 8 / 18 · R 25 / 26        (RUN 21 / RUN 22)
totals 404 and 308 rising edges over 273.918 s and 202.103 s
```

**All ten bits rose in both runs**: the runtime encoded and wrote a word
carrying each of the ten keys, on the original Nintendo pad and on the generic
third-party pad, during ordinary play of a title the Operator says uses all
ten.

**What this is NOT.** Not S, not K, and not evidence that the game responded to
any of them — a rising edge is the runtime sending a word (the routing itself
is FACT since §V7.4 and is not re-derived). Not evidence that the pads behave
alike: two different play sessions produce different counts for reasons that
have nothing to do with the controller, and §V7.6.11 forbids comparing these
press for press.

---

### GBP-HW-280 — the §V7.6.10 gates: five met in every session, and RUN 21's SESSION gate the only unmet one, exactly as the pre-registration wrote in advance — FACT (read from the logs)

IDENTITY / LOG, KEY RECORD, TRANSPORT, STARTUP and INPUT are met in both runs.
RUN 22's SESSION gate is met — `stop=session_end`, `status=ok_session_ended`,
`teardown=S5_session_end`, with `SESSION requested=1 holds=1 held=1155` — which
is §V7.6.10's only success for that gate: **the Operator's own end on Z, and
the first time this project's session-end mechanism has been exercised on
hardware.** RUN 21's is not: `stop=event_store_cap`,
`teardown=S5_event_store_cap`. **RUN 25 and RUN 26 also ended on Z**
(`requested=1 holds=1` in both), so the session-end mechanism is exercised
three times out of four, on both pads.

The KEY record is clean in both (798 and 599 lines, every one parsing under
`GBP_INPUT_EVENT_FMT`, `n` increasing by one, `events = emitted`, `lost =
truncated = overwritten = 0`), and so is the input path (`attempts = completed`
= 54 004 and 39 845, `failed = 0`, `retry = 0`).

**RUN 21's unmet gate diminishes nothing else about it**, and the
pre-registration said so before the run: a store cap *"is recorded EXACTLY as
it fell and is NOT a success: … the run is INCONCLUSIVE for the session gate
alone — not for W, S or T"*.

---

### GBP-HW-281 — Question T measured on the two PLAY sessions (RUN 21 / RUN 22; the head sessions were not read for T in this checkpoint): the VIDEO ACK → RE-ARM gap SHORTER and the AUDIO-only control UNCHANGED, with the frozen construction returning ANOMALOUS on a statistic the text does not specify — FACT for the measurement; **the verdict is NOT declared here**

The measurement, recomputed from the bounded cycle records and split by what
each cycle carried (ticks at 40.5 MHz):

```text
VIDEO cycles      RUN 17  1197  895  886  885  854  869  3112
                  RUN 21  1093  876  867  868  849  872  1748
                  RUN 22  1094  876  871  869  848  878  837  840  837  838
AUDIO-only        RUN 17    13   22   13   12   13   13   13   12   12
                  RUN 21    15   12   12   12   13   13   12   12   12
                  RUN 22    17   12   12   12   12   14
delivery rate     6328.8 / 6330.6 / 6329.7 per second      skipped_cause_pending 27.39 / 27.08 / 27.08 %
```

The first three VIDEO records compare element for element against RUN 17 at
−104 / −19 / −19 and −103 / −19 / −15; the AUDIO-only body is 12–13 ticks in
all three runs. **That is the direction the removal predicts, on the quantity
it predicts, with the within-run control unmoved** (§V7.6.3's differential).

**The frozen construction nevertheless returns ANOMALOUS on both runs**,
naming the AUDIO-only *mean* (12.6 and 13.2 against 13.7) and
`skipped_cause_pending` (27.08 % against 27.39 %). `tools/v7611.py` was written
before these logs existed and **was not edited**: §V7.6.11 says NOMINAL
requires the AUDIO-only gap *"unchanged"* and ANOMALOUS names a figure *"far
from"* the reference, and **the frozen text does not say which statistic
decides either** — nor is §V7.6.3's per-index reference portable, since `CYCLT
i=6` carries a VIDEO block in both new runs and an AUDIO-only cycle in RUN 17.

**So no T verdict is recorded.** Declaring NOMINAL would resolve an ambiguity
after seeing the data, which is what the freeze exists to prevent. The
measurement stands; the reading is the Orchestrator's to amend, dated
(§V7.8.6).

---

### GBP-HW-282 — `play-0001` is bounded at about 274 s by its EVENT STORE, not by the 720 s it was sized for, and the store fills at the frame rate rather than with input — FACT (measured on RUN 21, corroborated by RUN 22)

RUN 21 ran 273.918 s from the CONTROL transform to teardown and stopped at
`stop=event_store_cap` with `EVENTS n=16384 store_full=1 dropped=3`. RUN 22 ran
202.103 s, ended on Z, and reached 11 894 events — 73 % of the same cap.

```text
event store     16384 events    binds at ~274 s    <-- what actually stopped RUN 21
frame store     45056 frames    would bind ~756 s
max_deliveries  6 000 000       would bind ~948 s
safety budget   720 s           never approached (273.918 s reached)
```

**The store fills at the FRAME rate, not with the Operator's input**: 16 384
events over 273.918 s is 59.81/s against a published-frame rate of 59.61/s, and
the retained event lines are consecutive `episode_stabilising` records carrying
consecutive frame indices. Key changes are 2.91/s (RUN 21) and 2.96/s (RUN 22),
and **the pad that filled the store produced FEWER key changes per second** —
RUN 21 hit the cap because it RAN LONGER, not because of its pad.

**And the store filled before the run could record its own ending:** RUN 21's
`dropped=3` are exactly the three terminal events RUN 22 retained (`stop`,
`teardown_begin`, `teardown_end`).

**What this is about.** The image, not the run: a session of `play-0001` is
bounded at about 38 % of the length it was sized for. Recorded as an addendum
to `U-GBP-035`; **no new unknown is opened**, because nothing here is
unexplained.

---

### GBP-HW-283 — Question K = **AGREE** over steps 2–12: the two pads produced IDENTICAL ordered press sequences, each matching §V7.6.9's list press for press — FACT (recomputed by a construction that predates the logs)

RUN 25 (generic pad) and RUN 26 (original pad), the scripted-head sessions.
`tools/v7611.py` was written under Issue #50 from the frozen text with **no
data in reach**, narrowed to steps 2–12 by §V7.6.15 under Issue #51, and **was
not touched for this reading**.

```text
RUN 25   START A A DOWN DOWN UP RIGHT RIGHT RIGHT LEFT LEFT B B L R SELECT A
RUN 26   START A A DOWN DOWN UP RIGHT RIGHT RIGHT LEFT LEFT B B L R SELECT A
list     START A A DOWN DOWN UP RIGHT RIGHT RIGHT LEFT LEFT B B L R SELECT A     (§V7.6.9 steps 2-12)
```

**Two results.** `question_K_head` returns **AGREE** — *"identical press
sequences over the common prefix of the list"*, §V7.6.11's own words, over all
17 presses. And **each sequence equals the list exactly**, with the right keys
in the right order and the right counts, which is the machine's witness that
the list was made as listed (§V7.6.10's THE LIST).

Both records are clean: `KEYLOG events = emitted = 35`, `lost = truncated =
overwritten = 0`, every line parsing with `n` increasing by one; both sessions
ended on Z.

**What AGREE does NOT say.** That the game responded to any of it — that is W,
which has no per-key report and is INCONCLUSIVE (`GBP-HW-284`). That the pads
are alike in any sense beyond the words they produced. Anything past the
seventeen presses of the head: **K's tail stays `NOT DEFINED BY THE
PRE-REGISTRATION`** (§V7.6.15), because step 15 was not performed in these
sessions either.

**This is the machine half of the Operator's criterion** (*"o mesmo
comportamento"*) for the scripted head, and only that half.

---

### GBP-HW-284 — the Operator's channel for the head sessions: the game responded in character on both pads, reported GLOBALLY and not per key — OPERATOR OBSERVATION (global, qualitative); **W stays INCONCLUSIVE per key and is not inferred from it**

Asked what he observed in RUN 25 and RUN 26, verbatim:

> *"o jogo reagiu.... entrando em menus, saindo, pulando cutscenes... ele
> respondeu aos toques de acordo com a tela que ele estava no momento... ou
> seja... agiu normal"*

**What it carries.** Across the scripted head, on both pads, the game acted in
character with the screen it was on: menus entered and left, cutscenes skipped.
Beside it, the machine shows all seventeen presses of the list sent in each
session with `lost = 0` and the two sequences identical (`GBP-HW-283`).

**What it does not carry, and why that is recorded rather than smoothed over.**
It is **not a per-key report**. §V7.6.11 defines `WORKS` per key — *"he reports
RESPONDED for the key at a step where the game uses it, AND the KEY record
carries R_b > 0 for that key's bit at that point"* — so **this is not expanded
into ten WORKS verdicts** and **W stays INCONCLUSIVE per key**. The per-key
resolution was never produced because he was asked for what he remembered of
sessions already performed, not asked to re-run them against a form: **a
limitation of the evidence, not a fault of the run.**

**For S: no difference between the pads was reported.** That is the exact
statement — not *"he reported them identical"*, which he was not asked and did
not claim. The identity claim lives in the machine half (`GBP-HW-283`).

---

### GBP-VID-034 — RUN 12 carries two duplicate OGBPCOORD1 FRAME_ID transitions (479 → 479, 1919 → 1919) — FACT of this run; MECHANISM RESOLVED 2026-09-20 (Issue #12, software analysis, CORROBORATED): PREPARE-side missed VBlanks at the digit-1 and digit-4 entry frames

Observed by the frozen analyzer and reproduced by an independent decode
(GBP-HW-251): at `frame_index 761 → 762` the canonical witness carries FRAME_ID
479 twice (STATUS 0x36 both), and at `frame_index 2202 → 2203` FRAME_ID 1919
twice (STATUS 0x26 both); all 40 blocks of each of the four records are
valid, index-correct, CRC-correct and mutually consistent, FAULT clear, and
no other transition in 2046 deviates from +1. Both duplicated ids are the
frame immediately before an appearance start (R_1 at 480, R_4 at 1920); the
transitions into R_2 (959 → 960) and R_3 (1439 → 1440) are +1. **That
adjacency is an observation. No mechanism is inferred here, no causality is
assigned, and the finding is NOT labelled a source loss, a stimulus defect,
a transport defect or a display artefact until proven.** Runs 4–11 with
`indexed-0003` (no glyph, no VBlank-heavy frames) never showed a duplicate;
that is context, not a cause. Consequence: the shared source-window gate of
§V6.19.7 fails and both RUN 12 verdicts are INCONCLUSIVE. Investigation
belongs to a later research checkpoint; nothing was changed in this
ingestion.

**2026-09-20, MECHANISM RESOLVED (GitHub Issue #12; HARDWARE_TESTS §V6.22;
software analysis, no hardware).** Root cause: on the ENTRY frame of an
appearance, `prepare_frame` (IWRAM) builds the 80 × 50 digit table in EWRAM
with, per pixel, a reload of `sc->digit`, a ROM byte read of
`seg_of_digit[digit]` (not hoisted by the compiler) and up to seven segment
tests; unlit pixels also read `glyph_erase` from EWRAM. For the sparse digits
1 (3 200 unlit pixels) and 4 (2 592) that PREPARE costs 287 787 and 287 179
cycles — more than an AGB frame — against a budget of 263 839 … 263 953 cycles
between the end of the previous ordinary PUBLISH and the next VBlank; it
returns ≈ 19 lines inside VBlank v+1, the two-loop VCOUNT wait skips that
VBlank, VRAM keeps the previous frame one AGB frame longer and the GBP
captures the previous FRAME_ID twice (N−1, N−1, N — exactly the observed 479,
479, 480 and 1919, 1919, 1920). Digits 2 and 3 (2 240 unlit each) cost 261 723
and 260 043 cycles and return 2 116 … 3 910 cycles before the VBlank: no
duplicate, as observed. STATUS cannot see it: the latch brackets
`publish_frame` only (`vc0` is read after both wait loops), so FAULT = 0 and
the unchanged VMARGIN on the duplicate records are what the mechanism
predicts. The model (`tools/coordtime.py`: a minimal ARM7TDMI interpreter
over the exact frozen image with GBATEK bus costs; `tests/host/test_coordtime.py`)
is calibrated on three hardware facts of RUN 12 — the ordinary, entry and exit
PUBLISH end lines (VMARGIN 54 / 39 / 38–39, reproduced, the last as the
knife-edge the run itself showed) — and reproduces the four-entry pattern
M--M with no parameter fitted to the duplicates. Margins: the duplicates are
over by 23 226 / 23 834 cycles (8–9 %); the non-duplicates under by 2 116 /
3 796 (0.8 % / 1.5 %), the weakest link, stated as such; exits, steady and
ordinary frames are below a third of the budget. Same mechanism class as
GBP-HW-165, now proven for `coord-0001` in IWRAM at the margin instead of in
ROM on every frame. Not a source loss, not a transport or capture defect, not
a display artefact: the stimulus's own scheduling. Assumptions: datasheet
ARM7TDMI cycles, EWRAM 2 wait states (corroborated), ROM reads at the
`WAITCNT 4317h` the ROM writes, DMA 2I overhead (corroborated). Falsifiable:
a future run of this exact image retaining k ≥ 6 duplicates before digits 6,
7, 8, 9 and not before digit 5. The RUN 12 verdicts do not change: the gate
failed because of these two duplicates, and it still fails. Nothing in
`coord-0001`, the runtime, the analyzers, the formats or the gates was
touched; no RUN 13.

---

### GBP-VID-035 — frozen `tools/vvi.py::regs_consistent()` masks the recorded physical address before the flag-induced shift, so no MEM1 address carried with the VI flag can ever match — SOFTWARE ANALYZER DEFECT, FACT; REPAIRED (software) 2026-09-20 (Issue #11); the frozen-at-RUN-12 output is preserved as history

The frozen function computes `phys = rec["phys"] & 0xFFFFFF`, reconstructs
`top` / `bottom` from the register halves, and then `if flag: top <<= 5;
bottom <<= 5`. For a MEM1 address carried WITH the VI address flag (every RUN
12 record: `phys` 0x013a8420 or 0x0143e440, flag 1, xof 0) the compare domain
is inconsistent: the reconstruction yields the full address (e.g.
0x0143e440) while the recorded address has been masked to 0x0043e440, so the
frozen result is 0 / 2370 (GBP-HW-255). Independent raw cross-check, without
modifying the analyzer: reconstructed top vs the **unmasked** recorded `phys`
**2370 / 2370 match**; bottom vs the unmasked `phys` or `phys + 1280`
**2370 / 2370** (always +1280, one line of 640 × 2 B). **Required
interpretation: this is a software analyzer/model defect discovered by RUN
12, not evidence that all 2370 raw VI register readbacks disagreed with the
recorded handoff addresses. It does not retrospectively change RUN 12's
frozen analyzer output or formal verdict.** The tool's own docstring
assumption ("for a MEM1 address flag bit 12 is 0") is contradicted by the
raw records (flag 1, address stored >> 5). Not fixed in the ingestion
checkpoint; no physical rerun is required to fix or analyse the tool;
`tests/host/test_run12.py` pins the divergence as a known finding until a
functional checkpoint repairs it and retires the pin.

**2026-09-20, REPAIRED (software), GitHub Issue #11 — post-run analysis
only.** The rule was taken from the source, not inferred from the run:
`external/libogc2` @ `ca03fb7534a9b67d3348ef76e3a3b379aee9392a`,
`libogc/video.c` — `__calcFbbs` (2446–2464) converts both bases with
`MEM_VIRTUAL_TO_PHYSICAL` and sets `bfbb = tfbb + bytesPerLine`
(`(wordPerLine << 5) & 0x1fe0` = 1280 B for 640 px) unless single-field;
`__setFbbRegs` (2466–2503) sets `flag = 1` unless EVERY base is
`< 0x01000000`, then shifts every base `>> 5`, and writes `regs[14] = flag<<12
| xof<<8 | tfbb>>16`, `regs[15] = tfbb & 0xffff`, `regs[18] = bfbb>>16`,
`regs[19] = bfbb & 0xffff` — no flag bit in reg 18 (Dolphin
`VideoInterface.h` @ `c185d27`: `POFF` "1: fb address is (address>>5)", and
"POFF for XFB bottom is connected to POFF for XFB top"). The recorded `phys`
is `MEM_VIRTUAL_TO_PHYSICAL(xfb_stream_buf[xfb])` (`main.c:938`), the same
domain. RUN 12's buffers (`0x013a8420`, `0x0143e440`) lie above 16 MiB in the
24 MiB MEM1, so the registers carried the page-offset form — exactly as the raw
records show. Root cause: the 24-bit mask on `phys` (a leftover of the false
"MEM1 means flag 0" assumption) compared a full-domain reconstruction against
a truncated target, and would also have aliased bases differing above bit 23.
The repair (commit A of Issue #11) removes the mask, makes `bytes_per_line`
explicit (default 1280) and corrects the docstring; nothing else in the tool
changes. Synthetic matrix (`tests/host/test_vvi.py::TheAddressDomain`): flag
clear ordinary address; flag set / shifted address reproducing RUN 12's exact
register halves (`0x100a 0x1f22 0x000a 0x1f4a`, `0x1009 0xd421 0x0009
0xd449`); genuinely wrong TFBL fails in both forms; bottom plausibility not
vacuous and stride-explicit; no alias between `0x0043e440` and `0x0143e440`
in either direction; a misaligned base under the shifted form is a mismatch;
libogc2's flag rule versus the frozen tool's 16 MiB assumption. **Corrected
post-run replay of the versioned RUN 12 OGBPVI1: top 2370 / 2370, bottom
2370 / 2370; software chain L_1 = 40, L_2 = 40, L_3 = 38, L_4 = 40,
derived by the tool from records marked LATCHED and register-consistent.** The
two R_3 members not in L_3 — `frame_index 1754` (FRAME_ID 1471) and `1757`
(FRAME_ID 1474) — are SUPERSEDED in the raw file: the next hand-over came one
retrace later, before the pump observed them current, so no latch was
recorded. That is instrumentation semantics only; it says nothing about
whether either frame was or was not physically scanned out. **What does not
change:** the analyzer frozen at RUN 12 returned 0 / 2370 and L_k = 0
(GBP-HW-255, §V6.20.7) and that stays the historical record; GBP-VIDEO-007
remains INCONCLUSIVE and GBP-VIDEO-008 remains INCONCLUSIVE, because the
shared source-window gate failed independently (GBP-HW-251); GBP-VID-034 is
untouched and OPEN; no fixture byte, format, runtime or gate changed; no
hardware, no RUN 13. The §V6.19.9 gate asked for at least one
handed-and-latched frame per qualifying appearance; all four corrected sets
are non-empty, and that satisfies the software-chain population requirement
of a future admissible run, not of this one.

### GBP-HW-285 — RUN 30's sidecar is INTACT: `OGBPAW1` parsed strictly, every CRC recomputed from the bytes, and only then found to agree with what the image recorded — **FACT (this run)**

`captures/local/GBP-AUDIO-001_stream-0016-run30-audio.bin`, 5 243 788 B, sha256
`b3597b72adeae0cb8627e5c1b00584ca8a30bb2ff592c4b645e98cd9428ac564`, archived
from the Operator's untouched drop `logs/run30/…-audio.bin` of the same hash.

Read with `tools/awinparse.py` against the frozen contract of
`src/gbp/gbp_awindump.h`: magic, version, record size and block size accepted;
the header CRC-32 over the first 0xFC bytes is `7491c1e7`; the footer magic is
present and the CRC-32 over the whole body is `73a74a49`; all five anchors'
own CRC-32s and reserved bytes accepted; the size is exactly
`0x100 + 5×128 + 1280×4096 + 12`.

**The run's own log recorded `header_crc=7491c1e7 total_crc=73a74a49
written=5243788`** — recomputed first, compared second, which is the only order
in which the agreement carries information. `HARDWARE_TESTS.md` §V8.13.1.

### GBP-HW-286 — RUN 30's capture is COMPLETE, and the rising-edge anchor is confirmed on hardware: four presses produced FOUR windows, not eight — **FACT (this run)**

5 windows armed and 5 closed, 1 280 blocks stored, 0 failed, 0 skipped, no
window INCOMPLETE and none flagged GAP; `arms=5 refused_busy=0
refused_full=0`; `presses=4 releases=4`; KEY events 8 emitted 8, `lost=0
truncated=0`.

**The four releases armed nothing and the first event — the policy's
`KEYPAD := 0` with nothing held — armed nothing, because neither sets a bit
the previous word did not.** The anchor rule was introduced in Issue #59 from
reading the input module, before any run. Had it been a key-event rule, window
1 would have been spent on the boot's initialising write and the run would have
returned three windows of tone and one of silence — **a partial result rather
than a visible fault.** §V8.13.2.

### GBP-HW-287 — with a cartridge running, the GBP's AUDIO window carries a two-level square of EXACTLY 256-byte period; it is neither the cartridge-less byte-0 pattern nor PWM-shaped — **FACT (this run, 1 280 blocks)**

Every one of the 1 280 stored blocks: byte values drawn from
`{00, 01, FE, FF}` in the control and press 1, run lengths `01×8, FF×120,
FE×8, 00×120` repeating, **sixteen whole cycles per 4096-byte block**. Over all
1 280 blocks, **zero** have an inter-edge interval other than exactly 256
bytes.

**It is not `GBP-HW-057`'s pattern:** that capture, with no Game Pak, had 3 969
of 4 096 bytes zero and the non-zero bytes at offset 0 of each 32-byte line.
Here non-zero bytes are everywhere. **And it is not PWM:** `0x01` and `0xFE`
do not have contiguous leading 1 bits, so Dolphin's model (`U-GBP-012`) refuses
every block of this run rather than fitting it loosely.

**NO FREQUENCY IS CLAIMED.** 256 bytes is a length; turning it into a frequency
needs the region's sample rate, which this project has never measured
(`U-GBP-037`). §V8.13.3.

### GBP-HW-288 — the within-run control of RUN 30 is NOT silence-shaped: the standing square is already there before any press — **FACT (this run)**

Window 0, armed 5.045 s before the first press: four byte values, duty
`128/256 = 0.500` in every one of its 256 blocks, and **245 of the 256 blocks
byte-identical to each other**.

**This changes how the presses are read**, which is why §V8.5.1 requires the
control to be read first: *"a wave appears"* was not an available
discriminator, and what the presses can show is a **change in a wave that is
already there**. Whether the standing square is the AGB's output, the GBP's, or
the region's reset content is **not determined** by this run. §V8.13.3.

### GBP-HW-289 — the AUDIO window CHANGES with the press, ONE GBA FRAME LATER, by the appearance of intermediate levels — **FACT (this run, three of four presses)**

Three byte values that occur **nowhere** in the control window or in press 1's
— `0x80`, `0x81` and the pair `0xF8`/`0xFA` — appear in presses 2, 3 and 4.
`0x80` is mid-scale between the `0x00` and `0xFF` the standing square already
uses.

**The counts, both of them, over the 256 STORED blocks of each window**
(`0x80` alone was the only one first published, introduced as *"their count"*,
which a reader could take either way — §V8.13.4.1, appended on validation):

```text
A  bytes not in {00,01,FE,FF}   0, 0, 23 234, 24 608, 26 709   -- grows, composition shifts
B  the byte 0x80 alone          0, 0,  5 564, 10 749, 19 309   -- MONOTONE; a subset of A
per value  w2  80:5 564  81:326    F8:15 165  FA:2 179
           w3  80:10 749 81:659    F8:11 544  FA:1 656
           w4  80:19 309 81:1 176  F8: 5 441  FA:  783
```

**"Grows monotonically" is a claim about B.** A also grows, but its composition
changes direction — `0x80` rises 3.5× across the three presses while `0xF8`
falls 2.8× — and nothing here reads a meaning into either.

**The onset, measured from the GBP-side key change:** block 75 = **18.32 ms**,
block 65 = **15.88 ms**, block 50 = **12.21 ms** — bracketing the **16.74 ms**
of one GBA frame, which is the latency §V8.3.1 predicted and the reason the
window was corrected from 128 blocks to 256 before the run.

**PRESS 1 SHOWS NO CHANGE AT ALL** in its 62.5 ms window and that is recorded
as observed, not explained (`U-GBP-038`). §V8.13.4.

### GBP-HW-290 — **QUESTION AU = CARRIES / OTHER SHAPE**, by §V8.5.2's construction frozen before the image existed

`tools/v8audio.py`, not one line edited for this run, over the four press
windows against the within-run control: three of the four differ from the
control and the differences repeat with the press; none matches the predicted
shape.

**Neither half of §V8.5's prediction is present.** The alternation period was
predicted to change from ~26.5 to ~64 **blocks** at the transition — no period
changes anywhere. The mark-space ratio was predicted to run 1:7, 1:3, 1:1, 3:1
across the four presses — the duty takes `104/256`, `128/256`, `160/256` and a
few values between, in no order across the presses.

**The reason the prediction missed is structural:** it assumed the level
alternates ACROSS blocks (§V8.2's "one 64.00 Hz period = 63.98 blocks", from
the premise that a block is 0.2442 ms of audio), and the wave is INSIDE one
block. **That premise is what the run falsified.** The construction keeps its
words; the amendment is `U-GBP-037` and a future pre-registration.
§V8.13.5.

### GBP-HW-291 — **QUESTION SP = NOT OBSERVED**, which §V8.5.3 separates from "the stop worked"

No window shows the two predicted periods either side of a split, because no
window shows any period but 256 bytes. **Nothing is concluded about the
checker's stop sequence**, and `PHASE6_ENTRY.md` §2.1's a-priori prediction is
neither confirmed nor refuted by this run. §V8.13.5.

### GBP-HW-292 — **QUESTION T′ = NOMINAL**, §V7.9's first real answer

`tools/tprime.py` over CYCF/CYCFT and CYCL/CYCLT only, 16 cycles per run, 0
excluded, classified by `v=1/1`, against RUN 17 recomputed from its own log by
the same rule.

```text
CONTROL (read first)   AUDIO-only median 13 ticks against 13 -> UNCHANGED (|0| <= 1 tick)
                       12,13,13,13,13,13,13,16,16   against   12,12,12,13,13,13,13,13,22
treatment              VIDEO median 870 against 886 -> NOT LONGER (a direction, no magnitude)
                       845,863,867,870,878,952,1097 against 854,869,885,886,895,1197,3112
delivery rate          6 328.62/s against 6 328.69/s = 0.999989x, bound 0.995 (§V7.9.7)
skipped_cause_pending  26.940 % against 27.391 %, 0.451 pp apart, bound 5 pp
```

`tools/tprime.py` was written at this ingestion because no implementation
existed — the one thing about this entry worth distrusting — so every figure it
used is printed here and in §V8.13.5. §V7.9.1's bar holds: T′ is **not**
applied to RUN 17, 21, 22, 25 or 26 as a verdict.

### GBP-HW-293 — the cost of the window's copy IN the service path, measured: 1 / 19 / 1 399 ticks over 89 203 blocks — **FACT (this run)**

At the run's own 40.5 MHz time base that is **0.025 µs / 0.47 µs / 34.5 µs**
(min / mean / max) per received AUDIO block, for the 4096-byte copy Issue #59
added after the drain and its commit. 89 203 audio drains were seen and 1 280
were copied; the other 87 923 cost the branch alone.

The service pass around it is unchanged by measurement, not by assertion:
`GBP-HW-292`'s control class is identical to RUN 17's to within one tick.
§V8.13.2.

### GBP-HW-294 — the Operator heard nothing, and that carries NO information about SP — **OPERATOR OBSERVATION, framed**

Verbatim: *"Logs do run30 na pasta, não ouvi nenhum som"*.

**The image links no audio library.** `poc/gbp-audio-window-probe/Makefile` is
`LIBS := -lfat -logc`; the AUDIO blocks are drained and stored and **nothing
is ever sent to the GameCube's audio output**, exactly as in `play-0001`. So
silence is this image's designed behaviour and was never going to be otherwise.

**The question was a NEGATIVE control and is kept as one:** had he heard
anything, audio would have reached the television by a path nobody has
modelled, and that would have been a finding. §V8.10's prose said his answer
*"bears on SP"* — **that sentence is wrong and was wrong when written**; §V8.4
defines SP from the bytes and always did. Corrected on top in §V8.10.1, with
the wrong words kept, and the briefing gap recorded: the Orchestrator relayed
the action list without warning that the image cannot play audio.

### GBP-HW-295 — RUN 31's sidecar is intact and the run is admissible; **§V9.6's two independent press counts RAN AND AGREED on their first use** — **FACT (this run)**

`captures/local/GBP-AUDIO-002_stream-0016-run31-audio.bin`, 5 243 788 B, sha256
`8ff09d34006a485d2adaf96d5e008d25a9b27735c717b964940c2c2133cd2e07`; the log
90 070 B, sha256 `487c0c4935cbb33483f47eb76aa899c7b17ada6b819e557673ac0add57975bc7`.
Header CRC `9390bc85`, total CRC `d5d225b6`, every anchor accepted — recomputed
from the bytes and **then** compared with the run's own `AWINSAVE` record.

5 windows armed and closed, 1 280 blocks stored, 0 failed, 0 skipped,
`presses=4 releases=4`, KEY events 8 emitted 8 `lost=0`, service
`ok_session_ended`, `main_w1c=0`, `transport_ok=1`. Press spacing 3.303 /
3.320 / 3.136 s.

**The cross-check §V9.6 was built for ran for the first time and agreed.** The
Operator, verbatim: *"ainda não ouvi nada. Mas apareceu as cores Vermelho,
verde, azul e saiu no quarto aperto"* — three colours seen and the session
ending itself on the fourth press, which is the capture completing: **four by
his count, four by the machine's.** He heard nothing, which is the designed
behaviour of the image and of the ROM and bears on nothing.

### GBP-HW-296 — the 256-byte square in the AUDIO window is present **with the AGB's sound hardware provably disabled**: it is a property of the PATH, not of any tone — **FACT (this run)**

RUN 31's control window, armed 5.000 s after the CONTROL transform and 0.924 s
before the first press: five byte values `{00, 03, 07, FC, FF}`, structure
`07×1 03×7 FF×120 FC×8 00×120` repeating, **period exactly 256 bytes in all
256 blocks** with uniformity 1.0, duty `128/256` throughout.

**What makes this decisive and `GBP-HW-288` not:** `agb-tone` writes all six
APU registers to zero at reset and does not enable the master until the first
press, and that is demonstrated on the host by running the ROM's own code
(§V9.14.2). So the square is present **with the instrument's sound hardware
disabled by construction**, on a cartridge unrelated to RUN 30's.

The transition bytes differ between the two cartridges — `{01, FE}` in RUN 30,
`{03, 07, FC}` here — and that is recorded, not explained.
`HARDWARE_TESTS.md` §V9.15.3.

### GBP-HW-297 — **QUESTION R = RATIO DOES NOT HOLD**, by the construction frozen before the ROM existed

`tools/v9tone.py`, not one line edited — its third outing and **the first where
it decides against us**. §V9.8's estimator over the 1 280 stored blocks:
**256 bytes in every one of them**, uniformity 1.0, zero `PERIOD ABSENT`, in
the control and in all four press windows alike. Predicted 128 bytes for F1 and
32 for F2; `period(F1)/period(F2) = 1.0000` against the predicted `4.0000`.

§V9.4's own words for this outcome: *"A REAL RESULT, not a failed run"*.
**The period does not follow the note.** §V9.15.4.

### GBP-HW-298 — the AGB's audio IS in the window, at the predicted ratio, as the modulation ACROSS blocks — **FACT for the measurement (this run); the reading of it is CORROBORATED by two windows and not yet FACT**

The presses changed the **duty** of the 256-byte cell and never its length, and
the duty changes **from block to block**. Read as a series across blocks and
measured with **§V9.8's unmodified estimator**:

```text
w3 (F1 = 128.0 Hz, after its onset at block 44)   32 blocks   6 edges   uniformity 1.000
w4 (F2 = 512.0 Hz, whole window)                   8 blocks  30 edges   uniformity 0.966
w1, w2                                             PERIOD ABSENT -- no edges at all
ratio 32 / 8 = 4.0000            <- §V9.4's predicted ratio, exactly
as time      7.8156 ms and 1.9539 ms at the drain cadence of §V7.8.6
as frequency 127.95 Hz and 511.80 Hz against the ROM's 128.0 and 512.0 -- 0.04 %
and each window independently implies a drain rate of 4 096.0 blocks/s
```

**This is a MEASUREMENT reported beside §V9's verdict, not a gate that was
passed**, and one decision inside it is named rather than buried: w4 passes over
the whole window, **w3 needs the slice after its onset, and that slice was
chosen after seeing the data.**

**What it supports:** one drained block behaves as **one sample** of the AGB's
output, so the region is re-read rather than being a time series inside one
block — and §V9's construction measured the transfer's own cell instead of the
audio. That is the second of the two readings Issue #67 put forward, and the
bytes support it. **It is one run and one cartridge**; a repeat and a third
frequency are what would make it FACT. §V9.15.5.

### GBP-HW-299 — the AUDIO window does not carry the cartridge's sound until **(10.045, 12.547] s after the CONTROL transform** — **CORROBORATED across two runs, two cartridges and two instruments**; it ANSWERS `U-GBP-038` — **2026-09-23, Issue #72: REFUTED AS A FIXED PROPERTY OF THE PATH by RUN 32, whose interval (29.264, 32.634] s is DISJOINT from this one (`GBP-HW-307`); these words stay TRUE OF RUN 30 AND RUN 31 and are false as a property — read the amendment before citing the interval**

Read against the CONTROL transform rather than against the press ordinal, RUN
30 and RUN 31 agree:

```text
RUN 31  press 1   +5.924 s   no        RUN 31  press 3  +12.547 s  YES (+10.75 ms after the press)
RUN 31  press 2   +9.227 s   no        RUN 30  press 2  +14.182 s  YES (+18.32 ms)
RUN 30  press 1  +10.045 s   no        RUN 30  press 3  +18.153 s  YES
                                        RUN 31  press 4  +15.684 s  YES, from block 0 -- press 3's tone
                                                                    was still sounding
```

**Which press it is has nothing to do with it.** `U-GBP-038` asked why RUN 30's
first press changed nothing; the answer is that it was **early**, not first.

**RUN 31 sharpens it in a way RUN 30 could not:** its ROM enabled the APU at
**+5.924 s** and the Operator's colours confirm the ROM was running, so **the
AGB was emitting for roughly six seconds before the window carried anything.**

**The mechanism is NOT determined** — an initialisation the GBS-DOL performs, a
buffer that must fill, or something else — and `U-GBP-039` opens for it.
§V9.15.6.

### GBP-HW-300 — reusing an image across experiments makes the console's filenames stop identifying the experiment — **a defect recorded with its cost, not a measurement**

`stream-0016` was reused unchanged for RUN 31 (§V9.9, and the reuse was right:
no new build, no new identity, no staging risk). Its embedded `TEST_ID` is
`GBP-AUDIO-001`, so **it wrote RUN 30's two filenames again**.

RUN 30's copies had already been taken off the card, so **nothing was lost** —
but had they been there, RUN 31 would have overwritten them silently, which is
the collision class that has destroyed a raw drop twice before.

```text
the standing consequence   the archive name must distinguish runs the CONSOLE does not, so the archive
                           name and the file's own test_id WILL disagree -- here the copies say
                           AUDIO-002 and their contents say AUDIO-001, and that is correct
what a pre-registration    reserve names from the IMAGE's TEST_ID, not from the experiment's
 must do
what the SD-state check    it must be run against the names THE IMAGE WRITES, not the names the
 must compare              experiment reserved
```

§V9.15.1.

### GBP-HW-301 — Dolphin's AUDIO **RATE** is corroborated by hardware to four figures; only its **byte layout** is refused — **CORROBORATED (two windows of one run, two frequencies)**

`GBP-AUD-001` records Dolphin's model as *0x400 PWM bytes each mirrored ×4,
**produced at 4096 Hz***. RUN 31 measures the across-block modulation of two
known notes and each window independently implies **4 096.0 blocks/s** with
**one block = one sample** (`GBP-HW-298`): 32 blocks at 128.0 Hz, 8 at 512.0 Hz.

```text
Dolphin's rate      4096 Hz
measured            4 096.0 blocks/s from F1 and 4 096.0 from F2, independently
this project's own  4 094.4 drains/s, the cadence recomputed from RUN 17's archive (§V7.8.6) --
 drain cadence      0.04 % from the figure the two notes give
```

**What is refused is the LAYOUT and not the rate** (`GBP-HW-287`,
`GBP-HW-296`): the bytes are not contiguous-leading, the 256-byte cell belongs
to the transfer and survives the APU being off, and the audio lives **across**
blocks. **"Dolphin was wrong" is too coarse and would mislead a later reader**
— the cadence its model was built around is the cadence the hardware delivers.

**Not FACT:** one run, one cartridge, two windows, and one of the two needed a
slice chosen after the data (§V9.15.5). A repeat and a third frequency are what
would make it FACT. `GBP-AUD-001` amended; `U-GBP-012` carries the open half.

### GBP-HW-302 — `U-GBP-039`'s cheapest probe RAN, and it **cannot discriminate**: the four candidate epochs sit within 163 ms of each other — **a NEGATIVE result, from logs already in hand**

`U-GBP-039` listed *"the bound against `t_capture_start` rather than the CONTROL
transform, which the existing logs already carry and which costs one analysis
rather than one run"* as its cheapest probe. It was run over RUN 30's and
RUN 31's logs:

```text
epoch              RUN 30 / RUN 31, relative to t_control      the delay bound it gives
t_program                    -0.055 s                          (10.099, 12.602] s
t_video                      -0.032 s                          --
t_probe_enter                -0.013 s                          (10.058, 12.560] s
t_control                     0.000 s                          (10.045, 12.547] s
t_capture_start              +0.108 s                          ( 9.937, 12.440] s
```

**Every candidate epoch is within 163 ms of every other, and the bound is 2.5 s
wide.** So the probe **cannot** separate *"an initialisation the GBS-DOL
performs"* from *"something the runtime's capture start triggers"* from
*"elapsed time since the program began"*: in this image they all happen within
a sixth of a second of each other. **The cheap probe is exhausted and it says
the epochs are CONFOUNDED**, which is worth knowing before a run is spent
assuming otherwise.

**What WOULD separate them, and it already exists.** The service-path module
carries `prehandler_wait_ms` — a bounded wait inserted **after** stage A has put
CONTROL in its running shape and **before** the handler is installed
(`gbp_vstate_probe.h`), with physical precedent at 5000 ms (`GBP-HW-120`). A
run with that wait set **moves `t_capture_start` away from `t_control` by the
wait**, and the delay then follows whichever one it belongs to. It costs a
rebuild with an existing option, **no new code**, and it is not authorised
here. `U-GBP-039` records it.

### GBP-HW-303 — **`QUESTION V` = INCONCLUSIVE**, by `tools/v11sweep.py` frozen before the ROM existed — two of four windows carried nothing

RUN 32, `agb-sweep` on the EZ-Flash NOR, `stream-0016` unchanged. All four
presses were the pad's **B** (`keys=0002` in every press anchor), so §V11.8's
derivation reads the run under the V schedule and refuses no window.

```text
press 1 (V=15)  CARRIAGE FAILURE   flat within one byte of rest in all 160 sliced blocks
press 2 (V=11)  CARRIAGE FAILURE   the same
press 3 (V= 7)  CARRIES            duty 112 / 144 of 256
press 4 (V= 3)  CARRIES            duty 120 / 136 of 256
```

**§V11.4.1's refusal is what makes this a failure and not a reading:** no
schedule entry predicts a flat window, so a flat window is a carriage failure
and never "volume 15 encodes nothing". `GBP-HW-305` and `GBP-HW-306` show how
right that was. The construction was not adjusted. §V11.16.4.

### GBP-HW-304 — the AUDIO block is a **1-bit PWM pulse**, not a byte pattern — **FACT for the structure (three runs)**

A 4096-byte block is ~120 bytes of `0xFF`, ~120 of `0x00`, and a few partial
bytes at the two edges; every distinct value seen across RUN 30, RUN 31 and
RUN 32 (`00 01 03 07 83 f0 f1 fc fe ff`) is a run of **contiguous one-bits**.
The sample is the pulse's width **in bits**, so §V11.4's byte-counting `duty()`
quantises it to 8 bits: the levels a window settles at are multiples of 8 from
rest, while blocks in transition between the levels take intermediate values.

**This does not change any verdict** — a flat window is flat at either
resolution — and §V11.4's construction keeps its definition. §V11.16.7.

### GBP-HW-305 — the duty's deviation is **LINEAR in the envelope volume**, three points across two runs, intercept **+0.046/256** — **CORROBORATED, not FACT**

Read at bit resolution (`GBP-HW-304`), with the anchor taken from the run that
actually measured envelope volume 15:

```text
  V     deviation /256      dev / V              source
 15        30.0625           2.0042              RUN 31, agb-tone, both carrying windows, identical
  7        14.0547           2.0078              RUN 32 press 3
  3         6.0547           2.0182              RUN 32 press 4

least-squares line through the three:  slope 2.0007 /256 per volume unit, INTERCEPT +0.0515 /256
LINEAR re-anchored on V=15:            predicts 14.03 and 6.01 -- errors 0.03 and 0.04
COMPRESSIVE re-anchored on V=15:       predicts 22.55 and 15.03 -- errors 8.49 and 8.98
```

**The linear model is closer by a factor of 258**, and §V11.4.1's null — the
intercept of the fit — lands **0.0515 bytes from the origin**.

**This is a MEASUREMENT beside an INCONCLUSIVE verdict, not a gate that was
passed.** One of the three points comes from a different run and a different
ROM, which the pre-registration did not authorise; it is one instrument, one
cartridge, one console. **`U-GBP-012` is not closed and H-PWM is not promoted.**
§V11.16.7.

### GBP-HW-306 — `agb-sweep` **does not emit on its first press**, reproduced on hardware **off the GBP entirely** — an INSTRUMENT DEFECT, not a path observation

**OPERATOR OBSERVATION, 2026-09-23:** *"testei no console no primeiro toque nada
é reproduzido também .. só a partir do segundo"* — the ROM in his own Game Boy
Advance makes no sound on press 1 and does from press 2 onward.

**It explains RUN 32's window 1 completely and does NOT explain window 2**,
which his console says should have emitted.

```text
what is ruled out   the write ORDER. apu_play() sets the master enable BEFORE any channel register,
                    which is what GBATEK requires (external/gbatek/gba.md, SOUNDCNT_X).
what is known       the only difference between press 1 and press 2 is the master enable's 0 -> 1
                    transition; agb-tone's apu_play() is structurally identical, so the defect is
                    very probably not new to agb-sweep
the mechanism       NOT DETERMINED, and not guessed. U-GBP-040.
mGBA                would NOT have caught it: its model takes the reset branch only on DISABLE and
                    honours every channel write after a 0 -> 1 enable, so it emits where the hardware
                    does not (a static reading of external/mgba, not a run)
```

His console is an **undeclared unit** and this says nothing about the GBP's
internal AGB. §V11.16.8.

### GBP-HW-307 — `GBP-HW-299`'s bound is **REFUTED as a fixed property of the path**; measured from the AGB's first emission the runs agree — **two readings, NOT separated**

`GBP-HW-299` recorded *(10.045, 12.547] s after the CONTROL transform*,
corroborated across RUN 30 and RUN 31. **RUN 32's interval is
(29.264, 32.634] s — disjoint from it.** No common bound exists against that
epoch, and §V11.8 had already said the interval was the earliest a window was
*observed* to carry and not a hardware property.

```text
                        vs the CONTROL transform      vs the AGB's FIRST EMISSION
RUN 30  dead/alive       (10.045, 14.182]              the checker's APU timing is not ours
RUN 31  dead/alive       ( 9.227, 12.547]              (3.303, 6.623]
RUN 32  dead/alive       (29.264, 32.634]              (3.103, 6.473]
```

With `GBP-HW-306` the first emission is **press 2**, not press 1, and then RUN 31
and RUN 32 agree that **the window in which emission begins carries nothing and
the next one carries**, +3.320 s and +3.370 s later.

```text
READING A  ELAPSED TIME from the first emission     ~3.1 to ~3.4 s
READING B  WINDOW ORDINAL from the first emission   the emitting window is dead, the next is alive
```

**Both fit all three runs and this run does not separate them**, because every
run so far spaced its presses 3.1–3.4 s apart. **The separator is a long gap
after the first emitting press**, and it needs no new ROM and no new image.

`GBP-HW-299` keeps its words: it remains true of RUN 30 and RUN 31 and is false
as a property of the path. **`U-GBP-038` is REOPENED.** §V11.16.9.
