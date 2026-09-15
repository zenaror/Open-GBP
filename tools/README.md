# Tools

Development, analysis, trace-processing, binary-inspection, and
reverse-engineering utilities used by Open-GBP.

Tools should prefer deterministic and scriptable operation so they can
be executed autonomously by development agents and CI.

| Tool | Purpose |
|------|---------|
| `dolinfo.py` | Parse/validate a GameCube DOL header; `--json` for machine output; `--require-aligned` enforces Dolphin's 32-byte rule |
| `dolpad.py` | Pad DOL section sizes to 32-byte multiples (build step; see ENV-DOL-001) |
| `dolphin_smoke.py` | Run a DOL in the Dolphin Flatpak with an isolated user directory, collect USB Gecko output, Dolphin log and an X11 screenshot, and judge a POC-specific success condition. Dolphin's on-screen display is disabled per run by the runner's own override (`Dolphin.Interface.OnScreenDisplayMessages=False`), so screenshots show only the POC's framebuffer |
| `gciso.py` | Read-only GameCube disc image parser: `info` and `extract` (boot.bin, bi2.bin, apploader, main.dol, FST, files, manifest with SHA-256) |
| `gbi_unpack.py` | Recover the executable image from a packed Game Boy Interface DOL (XOR with the 40-byte copyright string, then XZ) |
| `bin2dol.py` | Wrap a raw PowerPC memory image into a one-section DOL so GameCubeLoader/dolinfo can load it |
| `probelog.py` | Parse device logs (SD file or USB Gecko capture): `parse` → JSON, `fixture` → replay script for `src/gbp/gbp_replay.c` (`--note` adds comment lines, used to mark synthetic scripts; GBP-INIT-003A records `IRQW`/`CTLW t_after=`/`SNAP tag=EVENT poll_intsr=`/`WINDOW t_end=` become `W`+`T`, `T`+`P p`, `T`; GBP-INIT-003B records `HANDLERPI intsr_at_entry=…`/`HANDLERPI2` extend the `I u` line by five numbers and `MAINPICLEANUP … performed=1` becomes `P a`; record kinds may carry a digit), `check` → interpretation of TEST/RAW records |
| `isr_audit.py` | Static audit of a one-shot PI HSP handler as linked (`--symbol`, default `hsp_backend_oneshot_isr`; `hsp_backend_oneshot_isr_ext` for GBP-INIT-003B): only `__MaskIrq` callable, no indirect call, no denied symbol, PI base and time base referenced, exactly one store to PI INTSR (value 0x2000, after the `__MaskIrq` call), no store to PI INTMR, loops allowed, instruction count reported; register values from `poc_audit.track_registers`; `make initirq-audit` / `make initirqb-audit` |
| `poc_audit.py` | Static audit of every object linked into a POC, per profile (`--profile 003a`, default: PI HSP masked for the whole run — no interrupt-path object/symbol, INTSR store only in `h_write_intsr`, 3 IRQ-register write sites; `--profile 003b`: `hsp_backend_irq.o` required, `__UnmaskIrq` from `h_irq_unmask` only, `IRQ_Request` from the install/restore pair only, `__MaskIrq` from the mask primitive and the two handlers only, INTSR stores in those three functions only, 3 + 1 IRQ-register write sites, `main.o` uses the ext constructor), stores to PI INTMR always forbidden (register values tracked by a forward data-flow pass over each function's control-flow graph: `lis`/`ori`/`addi`…, branch targets merge by agreement, loops converge, calls clobber the volatile GPRs, relocated immediates unknown), CONTROL write call sites (2), ELF symbol presence; `make initirqa-audit` / `make initirqb-audit` |
| `blockdiff.py` | Byte/u16/u32 views, distinct values, period and per-offset anomaly detection of 32-byte blocks; `--pair` two logs byte by byte; `--snapshots` S0–S5 timing and bit deltas of a GBP-INIT log |
| `ghidra/OpenGbpScan.java` | Headless Ghidra: functions, MMIO references, `lis` constants, strings → TSV reports |
| `ghidra/OpenGbpFunc.java` | Headless Ghidra: `decomp` selected functions, `callsites` with constant arguments, `refs` to an address |

Reverse-engineering workflow (reproducible, no GUI):

```bash
# 1. extract / unpack private inputs (outputs stay under input/, ignored by Git)
tools/gciso.py extract input/gbp-disc.iso input/extracted/gbp-disc
tools/gbi_unpack.py input/gbi/apps/gbi/gbi.dol input/extracted/gbi/gbi-unpacked.bin
tools/bin2dol.py input/extracted/gbi/gbi-unpacked.bin 80003100 input/extracted/gbi/gbi-unpacked.dol
# 2. import + analyze (project under build/ghidra, ignored)
GHIDRA=~/Tools/Open-GBP/ghidra_12.1.3_PUBLIC
$GHIDRA/support/analyzeHeadless "$PWD/build/ghidra" OpenGBP \
  -import input/extracted/gbp-disc/sys/main.dol input/extracted/gbi/gbi-unpacked.dol \
  -loader GameCubeLoader -loader-autoloadMaps false \
  -scriptPath "$PWD/tools/ghidra" -postScript OpenGbpScan.java "$PWD/build/analysis/ghidra"
# 3. targeted queries
$GHIDRA/support/analyzeHeadless "$PWD/build/ghidra" OpenGBP -process main.dol -noanalysis \
  -scriptPath "$PWD/tools/ghidra" \
  -postScript OpenGbpFunc.java "$PWD/build/analysis/ghidra" decomp 8008a930 \
  -postScript OpenGbpFunc.java "$PWD/build/analysis/ghidra" callsites 80089c3c
```

Decompiled output under `build/analysis/` derives from proprietary
binaries and must never be committed; only behavior descriptions go into
`docs/`.

All tools are Python 3 standard library only, except that
`dolphin_smoke.py` uses Pillow for screenshot analysis when available and
the host programs `flatpak`, `xdotool` and ImageMagick `import`.
