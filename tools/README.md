# Tools

Development, analysis, trace-processing, binary-inspection, and
reverse-engineering utilities used by Open-GBP.

Tools should prefer deterministic and scriptable operation so they can
be executed autonomously by development agents and CI.

| Tool | Purpose |
|------|---------|
| `dolinfo.py` | Parse/validate a GameCube DOL header; `--json` for machine output; `--require-aligned` enforces Dolphin's 32-byte rule |
| `dolpad.py` | Pad DOL section sizes to 32-byte multiples (build step; see ENV-DOL-001) |
| `dolphin_smoke.py` | Run a DOL in the Dolphin Flatpak with an isolated user directory, collect USB Gecko output, Dolphin log and an X11 screenshot, and judge a POC-specific success condition |
| `gciso.py` | Read-only GameCube disc image parser: `info` and `extract` (boot.bin, bi2.bin, apploader, main.dol, FST, files, manifest with SHA-256) |
| `gbi_unpack.py` | Recover the executable image from a packed Game Boy Interface DOL (XOR with the 40-byte copyright string, then XZ) |
| `bin2dol.py` | Wrap a raw PowerPC memory image into a one-section DOL so GameCubeLoader/dolinfo can load it |
| `probelog.py` | Parse device logs (SD file or USB Gecko capture): `parse` → JSON, `fixture` → replay script for `src/gbp/gbp_replay.c`, `check` → interpretation of TEST/RAW records |
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
