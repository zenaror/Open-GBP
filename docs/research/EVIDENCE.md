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
