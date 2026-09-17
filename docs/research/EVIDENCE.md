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

## GBP-AUD-001 — AUDIO data size and cadence

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
