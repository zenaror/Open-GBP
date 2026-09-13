# Development Log

Chronological record of project decisions, results, and discoveries.
Newest entry last. Keep entries at the level of "what changed and what we
learned", not a command transcript.

---

## 2026-09-13 — Phase 1: autonomous development loop established

**Goal:** establish the first trustworthy autonomous loop
(source → Docker → devkitPPC/libogc2 → ELF → DOL → Dolphin) with host-side
tests, without touching Game Boy Player hardware.

**Result:** achieved. `make all` (build + inspect + host tests + Dolphin
smoke test) passes end to end. No physical hardware test was needed.

### Environment observed

| Component | Version |
|-----------|---------|
| Docker / Compose | 29.8.0 / v5.4.0 |
| Image | `ghcr.io/extremscorner/libogc2:20260805` (Debian 12), unchanged |
| devkitPPC | r50; `powerpc-eabi-gcc (devkitPPC) 16.1.0`; binutils 2.46.0.20260210 |
| libogc2 | `libogc2 r2442.094b250` (2026-08-05) |
| Dolphin | Flatpak `org.DolphinEmu.dolphin-emu` 2606a, OpenGL backend on AMD/Mesa 26.1.6 |
| Host | Python 3.12.3, pytest 9.1.1, gcc 13.3.0, ImageMagick `import`, xdotool, Pillow 10.2 |

The container runs as the host UID/GID (1000:1000) and sees the repo at
`/workspace`; host files it creates are owned by the user.

### Files created / changed

```text
Makefile                          top-level driver (build/test/inspect/smoke-dolphin/all/shell/clean)
src/common/opengbp_ident.{h,c}    build-identity formatter, shared by PPC and host builds
poc/smoke-test/Makefile           libogc2 build; outputs to build/poc/smoke-test/
poc/smoke-test/source/main.c      the smoke test (console, heartbeat, optional USB Gecko output)
poc/smoke-test/README.md          purpose, outputs, success criteria, hardware procedure
tools/dolinfo.py                  DOL header parser/validator (+ 32-byte alignment report)
tools/dolpad.py                   pads DOL section sizes to 32 bytes (build step)
tools/dolphin_smoke.py            Dolphin runner with Gecko/log/screenshot success criteria
tests/unit/{Makefile,test_ident.c}   host C unit tests (9 checks)
tests/host/test_dolinfo.py        synthetic DOL vectors (13 tests)
tests/host/test_dolpad.py         padding tool (8 tests)
tests/host/test_artifacts.py      checks on the built ELF/DOL (11 tests)
tests/README.md, tools/README.md  updated
docs/research/EVIDENCE.md         ENV-DOL-001, ENV-EXI-001
docs/research/UNKNOWNS.md         U-ENV-001..004
docs/research/HARDWARE_TESTS.md   initialized (no physical tests yet)
.gitignore                        removed two stray heredoc lines; ignore Python caches
```

### Commands

```bash
make env-check        # toolchain inside the container
make build            # DOL:  build/poc/smoke-test/smoke-test.dol
make test             # build + inspect + C unit tests + pytest
make smoke-dolphin    # Dolphin run with evidence collection
make all              # test + smoke-dolphin
```

Direct forms: `docker compose run --rm -T dev make -C poc/smoke-test`,
`make -C tests/unit`, `pytest -q tests/host`,
`python3 tools/dolphin_smoke.py --dol build/poc/smoke-test/smoke-test.dol --build-info build/poc/smoke-test/build-info.txt`.

### Results

- **Host tests:** 9/9 C checks, 32/32 pytest, no compiler warnings on either target
  (`-Wall -Wextra -Wshadow` on PPC; `-Wpedantic -Wconversion` added on host).
- **PowerPC build:** ELF 32-bit big-endian `EM_PPC`, entry `0x80003100`;
  DOL 226080 bytes, 1 text + 1 data section, BSS `0x2A7F4`.
  `build-info.txt` records app/build id/commit/toolchain/SHA-256.
- **Dolphin:** PASS in ~6 s. Evidence: READY line with matching
  identity + 3 monotonic heartbeats over the emulated USB Gecko (TCP
  55020); BOOT log names the DOL, no unexplained error lines; X11
  screenshot of the render window shows the console (4.5 % lit pixels).
  Framebuffer self-measurement: ~6.3 k lit pixels before the first
  heartbeat line, identity-row hash constant across heartbeats.

### Problems found and how they were resolved

1. **Dolphin rejected the first DOL** (`Text section 0 is not 32-byte
   aligned`, fatal in 2606a; ENV-DOL-001). `elf2dol` emits unaligned
   sizes. GNU ld `INSERT AFTER .text` cannot augment the devkitPPC `-T`
   script (`.text not found for insert`), so the build now post-processes
   the DOL with `tools/dolpad.py` (zero padding, overlap-checked,
   unit-tested). The unpadded DOL is kept next to it.
2. **393–667 error-level Dolphin log lines** `invalid MMIO (addr=0c00688c|0c0068a0)`.
   Traced by disassembly to libogc2 `EXI_Sync` polling a +0x80 EXI
   register mirror, which the libogc2 author added on purpose as a Dolphin
   workaround (commit `47cea34`, 2025-11-09). Harmless in Dolphin;
   allow-listed by exact pattern in the runner with counts reported
   (ENV-EXI-001).
3. **Orphaned Dolphin process** after SIGTERM to `flatpak run`; the runner
   now also `flatpak kill`s the app and refuses to start if an instance is
   already running (Gecko port clash).
4. **Framebuffer hash changed between heartbeats.** The heartbeat is on
   console row 12, not 11 as first assumed; the hashed region now ends one
   full row above the heartbeat row and the geometry (`con=80x30
   font_h=15 hb_row=12 hash_rows=185`) is reported in the READY line.
   The exact console row→pixel mapping was not pinned down; the margin
   makes the check robust regardless.
5. **Dolphin frame dump never produced output** (U-ENV-004). Replaced by an
   X11 screenshot of the render window, which is simpler and inspectable.
6. **Path with spaces:** the repository lives under a directory containing
   a space, which GNU make cannot handle in absolute paths. The host unit
   Makefile uses relative paths; the PPC build runs at `/workspace` inside
   the container and is unaffected.

### Rejected hypotheses

- "Dolphin shows a black screen for CPU-written XFBs unless
  `Graphics.Hacks.XFBToTextureEnable=False`." Rejected: screenshots with
  the default (`True`) and with `False` both show the console. The
  override was removed from the runner.
- "Dolphin `--batch` exits by itself when the DOL finishes." Not
  observed; the runner always terminates Dolphin (U-ENV-003).

### Newly confirmed behavior

See `EVIDENCE.md`: ENV-DOL-001 (Dolphin 2606a DOL alignment rule),
ENV-EXI-001 (libogc2 EXI mirror vs Dolphin). Nothing about the Game Boy
Player was learned or attempted, by design.

### Unresolved

U-ENV-001..004 in `UNKNOWNS.md`. None blocks Phase 2.

### Physical hardware validation

Not justified yet: every Phase 1 acceptance criterion was met without it,
and the only open question it would answer (U-ENV-002, padded DOL through
Swiss) is low-risk. The procedure is written up as SMOKE-HW-001 in
`poc/smoke-test/README.md` and should be folded into the first Phase 3
hardware session.

### Next highest-value step

Phase 2 — reference analysis: document the GameCube HSP / GBS-DOL
interface from Dolphin's HSP model, libogc2, public research and the
user's Startup Disc (hash first, then headless Ghidra import), producing
`docs/hardware/` and `docs/protocol/` drafts with provenance and evidence
ids, before any Phase 3 probe touches the hardware.

---

## 2026-09-13 — Phase 2: reference analysis and first hardware documentation

**Goal:** understand, with explicit evidence levels, how the GameCube
reaches the Game Boy Player, before any Phase 3 hardware probe.

**Result:** the GameCube→GBS-DOL interface is now documented from three
independent code bases that agree on every point that was compared
(register windows, transfer format, IRQ bit map, detection handshake,
start/stop bit usage). Nothing was run on hardware. Consolidated pages
created under `docs/hardware/` and `docs/protocol/`; 20 evidence entries
and 14 unknowns registered.

### References studied and what each contributed

| Reference | Used for | Note |
|-----------|----------|------|
| Start-up Disc `main.dol` (SDK Dec 2002, JKR libs, `TGbpSystem`) | primary: register layer, IRQ handler, start/stop, watchdog, serial state machine | extracted with `tools/gciso.py`; 2463 functions after Ghidra analysis |
| GBI Standard `gbi.dol` | corroboration: same offsets, handshake, AR_INFO write, IRQ 26, 64-byte combined accesses | packed (XOR + XZ), unpacked with `tools/gbi_unpack.py`; libogc-rice r2191; 1971 functions |
| Dolphin master c185d27e / 2606a c77bbaa0, `HW/HSP/*`, `HW/DSP.cpp`, `HW/ProcessorInterface.h`, `GameSettings/UGP.ini`, `ID-gbi*.ini` | model comparison; names used only as Dolphin names | HSP reached through ARAM DMA ≥ ARAM size; SIO paths are stubs; 1.25× overclock for the disc |
| Dolphin PR #14535 (via GitHub page) | provenance of the model (jordan-woyak + endrift), "mirroring per hardware researcher" | the 2606 progress-report page returned HTTP 403 and was not read |
| libogc2 ca03fb75 | `IRQ_PI_HSP = 26`, PI cause 0x2000, `__ARCheckSize` AR_INFO size codes, `SYS_GetGBSMode`, EXI mirror (Phase 1) | |
| YAGCD | PI bit 13 = HSP (6.1.5.2); "3 sources: TX/RX mailbox, ID" (6.2.1); DSP CSR bits (6.2.8); ch. 11 "HSP devices … ARAM interface with offsets beyond 16MB", 11.1 GB Player = "to do" | memory-map chapter 4 has nothing on HSP |
| GBATEK (mgba-emu, 64b5087a) | AGB-side view: GBP detection via logo + KEYINPUT 0x030F, rumble protocol over SIO normal 32-bit, JoyBus registers | kept separate from GameCube-side registers |
| endrift gbpp f71afcdb + article | physical composition (CPU AGB A + GBS-DOL), test points, no frame sync | |
| gbhwdb.gekkio.fi/consoles/gbs | board revisions DOL-GBS-01/10/20, CPU AGB A (one A E), RAM variants | 10 units |
| mGBA / mooneye | not needed in this phase | |

External checkouts with commits: `external/README.md`.

### Binaries analyzed

| File | SHA-256 | Size | Origin |
|------|---------|------|--------|
| `input/gbp-disc.iso` | `947a5523e7be9b93a986d1e4daca9e335713827df48adcb1dfe79c6a00ed177d` | 1459978240 | user's dump, UGPE01 v2 "Game Boy Player Start-up Disc for US" |
| `input/extracted/gbp-disc/sys/main.dol` | `3dd3692f5931516b80915b38e795aa6092e4d4db43cd652bc396e0cba2b11b5d` | 1859680 | ISO offset 0x1EC00 |
| `…/sys/apploader.img` | `fff1386be75156d3fed0056c2e426ca41ed4a90071adb5212891e05d058cf6bc` | 116484 | ISO offset 0x2440, date 2002/09/05 |
| `…/files/binary_us.arc`, `…/files/opening.bnr` | `b1f74de1…`, `9b6de91e…` | 458880, 6496 | FST (2 entries) |
| `input/gbi/apps/gbi/gbi.dol` | `8083636c1b341e712859f40356bf5934f4622fab7e7a658bd7e8cb4feeb616b1` | 337320 | GBI package |
| `input/extracted/gbi/gbi-unpacked.bin` | `0b2c44ea75f85aa8d64ac3ad167c400f778becc58e886c53a44b9a67f46384b0` | 734732 | unpacked, load 0x80003100 |
| `input/gbi/apps/gbisr/gbisr.dol`, `gbihf.dol` | `c887877f…`, `47598482…` | 329322, 302186 | not analyzed yet (differential step deferred) |

All extracted/derived files live under `input/extracted/` and
`build/analysis/`, both ignored by Git.

### Tools created

- `tools/gciso.py` — read-only disc parser/extractor with manifest and hashes (+ tests).
- `tools/gbi_unpack.py` — GBI stub format: payload XOR'd with the 40-byte copyright string, then XZ (+ tests).
- `tools/bin2dol.py` — wrap a raw image for GameCubeLoader (+ test).
- `tools/dolinfo.py --read ADDR:LEN` — hex dump by load address.
- `tools/ghidra/OpenGbpScan.java` — functions / MMIO refs / `lis` constants / strings.
- `tools/ghidra/OpenGbpFunc.java` — `decomp`, `callsites` (decompiler-derived constant arguments), `refs`; creates a function on the fly for handlers reached only via pointers.

Ghidra 12.1.3 headless imported both DOLs in under a minute each; the
`callsites` mode was the key instrument (it exposed the 14 DISC register
wrappers and the GBI ARQ calls with their constant offsets).

### Facts discovered (see EVIDENCE for ids)

- GBP registers = 32-byte ARAM DMA blocks at `internal_ARAM_size + (index << 20)`; indices 0x0 TEST, 0x1 VIDEO (0xF00), 0x4 CONTROL, 0x5 SIOCTL, 0x8 AUDIO (0x1000), 0x9 SIODATA, 0xC KEYPAD, 0xD IRQ. (GBP-HSP-001)
- Both drivers write expansion code 3 into `0xCC005012` bits 3–5 first. (GBP-HSP-002)
- TEST echoes the complement; DISC patterns C3/3C/FF/00, GBI C3/FF. (GBP-TEST-001)
- PI bit 13 ↔ OS interrupt 26 in SDK and libogc; IRQ register even bits = sources {0x1,0x4,0x10,0x40,0x100,0x400}, odd bits = masks, ack by writing back. (GBP-IRQ-001)
- VIDEO: 4 lines × 240 px × 32-bit, 40 blocks/frame, frame-start flag 0x80800000 on the first word; DISC pre-fills a dummy block with it. (GBP-VID-001)
- KEYPAD rewritten on every IRQ by both drivers; GBI presses L+R+Select (0x0304) on the sleep IRQ. (GBP-KEY-001)
- DISC runs a 200 Hz watchdog: 50 unchanged IRQ counts (≈250 ms) → stream failure; a TEST pattern every tick → removal detection. Dolphin needs a 1.25× overclock to satisfy it.
- DISC drives an internal serial path (SIODATA write → SIOCTL|=0x80 → IRQ bit 6 → read) with a 1 s timeout. Dolphin stubs it. (GBP-SIO-001)
- GBI HSP raw handler only acks PI and wakes a thread; the thread does 64-byte combined DMAs (KEYPAD+IRQ at 0xCFFFE0, CONTROL+SIOCTL at 0x4FFFE0). (GBP-HSP-004)

### Corroborated across DISC + GBI + Dolphin

Register indices and offsets; 32-byte format with the value at the block
end; TEST inversion; AR_INFO expansion code (DISC + GBI only); IRQ bit
positions and ack; CONTROL bit usage 0x01–0x10; VIDEO geometry and flag;
AUDIO size; KEYPAD format and refresh policy; PI bit/OS interrupt number.

### Hypotheses (Dolphin-only or single-source)

CONTROL bit names (3V/5V/sleep/link); L/R order in KEYPAD; PWM audio
format and 4096 Hz cadence; video color bit order; IRQ bit 15 semantics;
the necessity of the AR_INFO write; YAGCD's "3 HSP interrupt sources".

### Contradictions between sources

- Read block layout: DISC treats reads as byte-doubled (u32 from bytes
  0x19/0x1B/0x1D/0x1F); Dolphin's IRQ read is `hh hh hh ll` and its
  SIODATA read repeats the u32 — both satisfy DISC only at bytes 0x1D/0x1F.
- YAGCD 6.2.1 describes HSP interrupt "mailboxes"; no driver uses anything like them.
- Dolphin ignores `0xCC005012` bits 3–5; both drivers set them.

### Unknowns opened

U-GBP-001 … U-GBP-014 (`UNKNOWNS.md`), prioritized: P1 = U-GBP-004
(AR_INFO requirement), P2 = read layout, IRQ polarity, CONTROL meanings,
L/R order, video colors, audio format, IRQ timing, mirroring; P3 = SIO
semantics, Link Port coexistence, revisions, SRAM word.

### Documentation created

`docs/README.md`, `docs/hardware/{ARCHITECTURE,HSP,GBS-DOL}.md`,
`docs/protocol/{REGISTERS,INITIALIZATION}.md`, `docs/hardware/README.md`,
`docs/protocol/README.md`; `EVIDENCE.md` (+20 entries), `UNKNOWNS.md`
(+14), `HARDWARE_TESTS.md` (GBP-PROBE-001 planned), `external/README.md`
(commit table), `tools/README.md`, `tests/README.md`.

### Not done / deferred

- GBI differential (`gbisr.dol`, `gbihf.dol`): deferred as instructed
  ("do not start here"); the unpacker works on all three.
- Startup Disc SDK "GBA" library (JoyBus GBA-as-controller, DSP-based)
  and the SRAM GBS settings word: noted, not analyzed.
- Dolphin 2606 progress report: HTTP 403, not read; PR #14535 page was.

### Recommended first Phase 3 experiment

`GBP-PROBE-001` in `HARDWARE_TESTS.md`: a read-only presence probe that
(1) dumps raw 32-byte reads of TEST, CONTROL and IRQ, (2) performs the
TEST inversion handshake with and without the `0xCC005012` expansion
code, (3) logs everything to screen and SD2SP2 with the build id. It
writes nothing but the TEST window and a GameCube-side register that
libogc already probes at boot. Its results settle U-GBP-004 and
U-GBP-008 and give the project its first hardware FACTs.

---

## 2026-09-13 — Phase 3 preparation: driver foundation, SMOKE-HW-001 and GBP-PROBE-001 ready

**Goal:** build the first physical experiments without touching hardware
yet: a re-validated smoke test (gate 1) and a conservative, fully
host-tested GBP presence probe (gate 2), on the transport architecture
that the future driver will keep.

**Result:** both DOLs build, pass host tests and Dolphin. Hardware
requests are written up; nothing has been run on the GameCube.

### Architecture introduced

```text
probe / driver logic          src/gbp/gbp_probe.c        (portable, tested on host)
        │ struct gbp_transport  src/gbp/gbp_transport.h   (read/write AR_INFO, read/write 32-byte block)
        ├── real backend        src/platform/hsp_backend.c (ARAM DMA regs, CSR polling, timeouts)
        ├── mock backend        tests/mocks/gbp_mock.c     (present/absent/expansion-required/faults/layouts)
        └── replay backend      src/gbp/gbp_replay.c       (scripts from tools/probelog.py fixture)
event log                     src/log/ringlog.c          → src/platform/sdlog.c (SD2SP2 flush on X)
```

### Files created / changed

```text
src/gbp/{gbp_transport.h,gbp_transport.c,gbp_probe.h,gbp_probe.c,gbp_replay.h,gbp_replay.c}
src/log/{ringlog.h,ringlog.c}
src/platform/{hsp_backend.h,hsp_backend.c,sdlog.h,sdlog.c}
tests/mocks/{gbp_mock.h,gbp_mock.c}
tests/unit/{test_ringlog.c,test_gbp_probe.c,test_gbp_replay.c,Makefile}
tests/host/{test_probelog.py,test_artifacts.py}
tools/probelog.py, tools/dolphin_smoke.py (--expect, --heartbeats 0, generic READY prefix)
poc/gbp-probe/{Makefile,README.md,source/main.c}
poc/smoke-test/{Makefile,README.md,source/main.c}   (build smoke-0002: X saves a report to SD2SP2)
Makefile (build/inspect both POCs, probe-dolphin target)
captures/fixtures/dolphin-2606a-gbplayer-model-{present,absent}.gbpreplay (+ captures/README.md)
docs/research/HARDWARE_TESTS.md
```

### What the probe does on hardware (exact)

- Reads `0xCC005012`; MODE A uses it as found. Reads 32-byte blocks at
  `base+0x000000`, `base+0x400000`, `base+0xD00000` (TEST, CONTROL, IRQ),
  raw, before and after the handshake. Handshake = write 32×C3, read;
  32×3C, read; 32×FF, read; 32×00, read — TEST block only.
- MODE B: writes `(orig & ~0x38) | 0x18` to `0xCC005012` (bits 3–5 := 3,
  everything else preserved), repeats the same sequence, then writes the
  original value back and reads it to confirm (`restored=`).
- Every DMA: refuse on CSR busy/stale flag, 200 ms timeout, polls and
  ticks logged, CSR after logged. Interrupts disabled during a transfer,
  as the Start-up Disc does. libogc AR/ARQ not initialized; PI HSP
  interrupt never unmasked.
- Records: `IDENT, ENV, PROBE, ARINFO×6, MODE×4, RAW×12, TESTW×8,
  TESTR×8, STATS` in a 160-line RAM ring (drop-newest + counter); dumped
  over USB Gecko when present; saved to
  `sd:/open-gbp/GBP-PROBE-001_probe-0001.log` on X.

### Tests

- Host C: 96 checks (ident 9, ringlog 17, probe-vs-mock 57, replay 13),
  `-Wall -Wextra -Wpedantic -Wshadow -Wconversion`, no warnings.
  Scenarios: GBP present, absent, expansion-code required, timeout,
  stuck-busy after timeout, DMA/backend error, unexpected block index,
  byte-doubled vs plain read layout, ring buffer full, AR_INFO restore,
  "writes only to TEST" policy, replay exhaustion/mismatch.
- Python: 49 tests (adds probelog parser/fixture/check; artifact checks
  now cover both POCs).
- PowerPC: both POCs compile without warnings; DOLs 32-byte aligned.
- Dolphin: `make smoke-dolphin` PASS; `make probe-dolphin` PASS twice —
  HSP device absent → `a_present=0 b_present=0 errors=0 restored=1`
  (only the FF pattern "matches" against zero fill, hence 4 patterns);
  Dolphin GBPlayer model → `a_present=1 b_present=1 errors=0 restored=1`.
  Dolphin reports AR_INFO = 0x0043 at start; its model ignores bits 3–5,
  so Dolphin cannot answer U-GBP-004 (as expected). Fixtures from both
  runs are stored as *model* data.

### Not done, by design

No video/audio/keypad/SIO/link code; no libmobile; no differential GBI
analysis; no writes to any GBP block other than TEST; no interpretation
promoted to fact.

### Next

1. User runs SMOKE-HW-001 (`poc/smoke-test/README.md`). On PASS: record
   in HARDWARE_TESTS/EVIDENCE (U-ENV-002 closes), then request
   GBP-PROBE-001 (`poc/gbp-probe/README.md`).
2. On receiving the probe log: `tools/probelog.py check`, keep the raw
   file under `captures/local/`, generate a sanitized fixture, add a
   replay test, update EVIDENCE/UNKNOWNS (U-GBP-004, U-GBP-008) and the
   consolidated docs only where the hardware justifies it.

Note: all build identities currently read `a982fb7-dirty` because the
Phase 1–3 work is uncommitted. Committing before the physical session
would tie the DOLs to an exact tree; the DOL SHA-256 in
`build-info.txt` identifies them regardless.
