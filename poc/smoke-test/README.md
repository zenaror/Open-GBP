# poc/smoke-test — Open-GBP Smoke Test

**Build ID:** `smoke-0002` (smoke-0001 + SD2SP2 report on X)
**Question answered:** does the autonomous development loop work end to end?

```text
source → Docker (devkitPPC 16.1.0 + libogc2 r2442) → ELF → DOL → Dolphin → (physical GameCube)
```

The program touches only generic GameCube facilities: video framebuffer
console, controller, and an optional USB Gecko in memory-card slot B. It
never accesses Game Boy Player / HSP hardware.

## What it does

1. Initializes video, prints an identity block:

   ```text
   Open-GBP Smoke Test
   Build : smoke-0001
   Commit: <short git hash>[-dirty]
   libogc: libogc2 r2442.094b250
   Video : 640x480 NTSC/other
   Gecko : detected (slot B) | absent
   OPENGBP-IDENT app=smoke-test build=smoke-0001 commit=<hash>
   Press START to exit to loader.
   ```

2. Once per second rewrites a heartbeat line in place with the VSync
   count, the number of lit framebuffer pixels and a hash of the static
   identity rows.

3. If a USB Gecko is present on EXI channel 1 (Dolphin emulates one when
   `Core.SlotB=7`), emits the same information as machine-readable lines:

   ```text
   OPENGBP-SMOKE READY app=smoke-test build=smoke-0001 commit=<hash> con=80x30 font_h=15 hb_row=12 hash_rows=185
   OPENGBP-SMOKE HEARTBEAT n=1 frames=60 xfb_lit=6289 xfb_hash=<8 hex>
   ```

4. X writes a short report (identity, video mode, heartbeat state, buttons
   seen) to `sd:/open-gbp/SMOKE-HW-001_smoke-0002.log` through the same
   ring-buffer → SD2SP2 path the GBP probe relies on. Failure to mount the
   card is reported on screen and is not fatal.
5. START exits to the loader.

## Build

From the repository root, on the host:

```bash
make build          # docker compose run --rm -T dev make -C poc/smoke-test
```

Outputs (`build/poc/smoke-test/`, ignored by Git):

| File | Purpose |
|------|---------|
| `smoke-test.elf` | linked ELF (debug info included) |
| `smoke-test.unpadded.dol` | raw `elf2dol` output |
| `smoke-test.dol` | **final DOL**: section sizes padded to 32 bytes by `tools/dolpad.py` |
| `smoke-test.map` | linker map |
| `build-info.txt` | app, build id, commit, toolchain versions, SHA-256 of the DOL |

The padding step exists because Dolphin 2606a rejects DOLs whose section
sizes are not multiples of 32 bytes (`docs/research/EVIDENCE.md`,
ENV-DOL-001). Physical loaders are expected to accept either file.

## Automated checks

```bash
make test           # build + inspect + host C unit tests + Python tests
make smoke-dolphin  # run in Dolphin and verify the success criteria below
make all            # both
```

`tools/dolphin_smoke.py` passes only when **all** of the following hold:

| Check | Evidence |
|-------|----------|
| gecko | READY line whose app/build/commit equal `build-info.txt`, followed by ≥ 3 monotonic HEARTBEAT lines with a plausible lit-pixel count and a constant identity-row hash |
| log | Dolphin's log names the DOL in a BOOT line and contains no unexplained error-level lines (the libogc2 EXI-mirror reads, ENV-EXI-001, are counted and reported) |
| screen | an X11 screenshot of Dolphin's render window shows mostly black with a few percent lit pixels (console text) — saved as `dolphin-screen.png` |

A timeout without a READY line is a failure. The JSON report is written to
`build/poc/smoke-test/dolphin-report.json`.

## Physical hardware procedure — SMOKE-HW-001

```text
Test ID:            SMOKE-HW-001
Build ID:           smoke-0002
Commit:             see build/poc/smoke-test/build-info.txt (commit= line) and the screen
DOL:                build/poc/smoke-test/smoke-test.dol  (sha256 in build-info.txt; padded by tools/dolpad.py)
Cartucho:           none required
GBP:                may stay attached; it is not accessed
Link Port:          irrelevant
BBA:                irrelevant
SD2SP2:             inserted, FAT32, with the DOL on it
Passos:
  1. Copy smoke-test.dol to the SD card.
  2. Launch it through Swiss.
  3. Confirm the identity block: "Build : smoke-0002", the Commit line, "Gecko : absent".
  4. Watch the heartbeat line count for ~5 s (frames should advance by 60/s NTSC or 50/s PAL).
  5. Press X once; wait for "SD: saved 3 lines to sd:/open-gbp/SMOKE-HW-001_smoke-0002.log".
  6. Press START; Swiss should reappear.
  7. Return the log file and, if anything looked wrong, a photo of the screen.
Resultado esperado: identity block + counting heartbeat; X saves; START returns to Swiss;
                    no freeze, no unexpected reset.
Log esperado:       header (test_id, build_id, commit), IDENT, VIDEO, STATE lines, dropped=0
Pergunta respondida: does the Docker/libogc2/elf2dol/dolpad pipeline produce a DOL that runs on the
                    real GameCube through Swiss (U-ENV-002), including video, pad and SD2SP2 logging?
Risco:              none beyond running homebrew; the GBP is not touched.
```
