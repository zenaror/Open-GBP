# External References

Local checkouts of external reference projects may be placed here.

External repositories are not vendored into Open-GBP. Only this README
is tracked.

Checkouts used for conclusions in `docs/` (shallow clones; re-clone at the
listed commit to reproduce):

| Directory | URL | Branch | Commit | Consulted | Files relied on |
|-----------|-----|--------|--------|-----------|-----------------|
| `dolphin/` | https://github.com/dolphin-emu/dolphin | master (+ tag 2606a) | c185d27ede09771fe93a3b520c576f646f937ed9 (2606a = c77bbaa0f372c3f72281602a8b087206706542cb) | 2026-09-13 | Source/Core/Core/HW/HSP/*, HW/DSP.cpp, HW/DSP.h, HW/ProcessorInterface.h, HW/GBACore.cpp, Config/MainSettings.cpp, Data/Sys/GameSettings/UGP.ini, ID-gbi*.ini, Core/Boot/DolReader.cpp |
| `libogc2/` | https://github.com/extremscorner/libogc2 | master | ca03fb7534a9b67d3348ef76e3a3b379aee9392a | 2026-09-13 | libogc/aram.c, libogc/irq.c, libogc/exi.c, libogc/system.c, libogc/console.c, include/ogc/irq.h, include/ogc/system.h, include/ogc/aram.h, libogc/irq_handler.S, libogc/exception.c, libogc/mmce.c, include/ogc/timesupp.h, include/ogc/machine/processor.h |
| `gbpp/` | https://github.com/endrift/gbpp | master | f71afcdbdce1745ccc12ce4dcae7168cb9899530 | 2026-09-13 | gbpp/gbpp.ino (test-point table) |
| `gbatek/` | https://github.com/mgba-emu/gbatek | gh-pages | 64b5087aa45cd0187b8b239d77e54ee5eb2917d1 | 2026-09-13 | gba.md: "GBA Gameboy Player", "SIO Normal Mode", "SIO JOY BUS Mode"; 2026-09-21: "4000130h - KEYINPUT", "Gameboy Player (Gamecube Joypad)", "Unlocking and Detecting Gameboy Player Functions" |
| `mgba/` (Enhanced mGBA) | https://github.com/extremscorner/mgba | 20251124 (the repository's default branch) | 8692b26b6d882c049bc70958e0ef8ba0e607a4b7 | 2026-09-21 | src/platform/wii/main.c (`_pollGameInput`, `_mapKey` bindings, `mInputBindAxis`, ANALOG_DEADZONE), include/mgba/internal/gba/input.h (`enum GBAKey`); src/platform/gamecube/ holds only a CMake toolchain file. Authority: GameCube-side controller polling and mapping only — never the physical KEYPAD format (`CLAUDE.md` §6.6); it is an emulator and does not touch the HSP window. Not the same tree as `dolphin/Externals/mGBA`, which is Dolphin's vendored core |

## Web references — consulted, NOT checked out, NOTHING vendored

A page is not a repository: there is no commit to pin, so what is recorded is
the URL, the date it was read, exactly what was taken from it, and **whose
hardware or code it documents**. Nothing from these is committed to Open-GBP.

| Reference | URL | Read | Licence | What it documents — and what it does NOT |
|---|---|---|---|---|
| Gekkio's Game Boy hardware database — the GBS console unit `gekkio-1` | https://gbhwdb.gekkio.fi/consoles/gbs/gekkio-1.html | 2026-09-21 (the Operator); 2026-09-22 (licence and contents read by the Executor) | **CC BY-SA 4.0** for the data and photographs (the site states it; the site's source code is MIT) | **SOMEBODY ELSE'S Game Boy Player**, catalogued as `gekkio-1`: board revision `DOL-GBS-10`, and a component list whose entries the page gives as U1 CPU AGB A, U2 WRAM `D442012AGY`, U4 `GBS-DOL`, U5/U6 `MM1592F` regulators, Y1 33.554432 MHz crystal, all dated to weeks 18–20 of 2003. **It is NOT evidence about the Operator's unit** and it scopes, qualifies or explains NOTHING about any run this project has executed. Its use is in `UNKNOWNS.md` U-GBP-009: it shows that a board revision is *readable on the PCB* and that the variants are catalogued — a PROCEDURE, not an answer. |

**Why the photographs are not in the repository.** The Operator placed two of
that page's images in `logs/` on 2026-09-21; `logs/` is the raw drop of
physical runs (`CLAUDE.md` §12) and a third-party board photograph is not a run
artifact. They were **moved, not deleted**, to `external/gbhwdb/`
(`gekkio-1_03_pcb_front.jpg` `b45f1768…a1bb`, `gekkio-1_04_pcb_back.jpg`
`2c5f1a63…00cb`), which this repository ignores like every other `external/`
checkout. The licence would in fact permit redistribution with attribution —
and that is exactly why they stay out: CC BY-SA's share-alike term would reach
a repository that carries them, and a URL costs nothing and avoids the question
(GitHub Issue #30).

**One discrepancy, recorded rather than resolved.** Issue #30's own reading of
the front photograph names *"`U3` as an NEC `D442012A0Y`"*; the page's component
list, read on 2026-09-22, gives the WRAM as **U2** `D442012AGY` and the GBS-DOL
as **U4**. Nothing in this project depends on either reading — it is a
third-party page about a unit that is not ours — so the difference is noted and
left open.

Toolchain image: `ghcr.io/extremscorner/libogc2:20260805` ships
`libogc2 r2442.094b250` (`gamecube/include/ogc/libversion.h`, built Aug 5
2026), which is what every Open-GBP DOL links. That commit is not in the
shallow `libogc2/` checkout above; for the interrupt-path conclusions
(EVIDENCE ENV-IRQ-001/002) the image's `libogc.a` members
`irq.o`/`irq_handler.o` were disassembled with `powerpc-eabi-objdump`
inside the container (2026-09-15) and matched the analyzed source. See
UNKNOWNS U-ENV-005.
