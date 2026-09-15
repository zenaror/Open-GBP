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
| `gbatek/` | https://github.com/mgba-emu/gbatek | gh-pages | 64b5087aa45cd0187b8b239d77e54ee5eb2917d1 | 2026-09-13 | gba.md: "GBA Gameboy Player", "SIO Normal Mode", "SIO JOY BUS Mode" |

Toolchain image: `ghcr.io/extremscorner/libogc2:20260805` ships
`libogc2 r2442.094b250` (`gamecube/include/ogc/libversion.h`, built Aug 5
2026), which is what every Open-GBP DOL links. That commit is not in the
shallow `libogc2/` checkout above; for the interrupt-path conclusions
(EVIDENCE ENV-IRQ-001/002) the image's `libogc.a` members
`irq.o`/`irq_handler.o` were disassembled with `powerpc-eabi-objdump`
inside the container (2026-09-15) and matched the analyzed source. See
UNKNOWNS U-ENV-005.
