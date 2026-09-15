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
- KEYPAD rewritten on every IRQ by the Start-up Disc and GBI; GBI presses L+R+Select (0x0304) on the sleep IRQ. (GBP-KEY-001)
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
- Dolphin ignores `0xCC005012` bits 3–5; the Start-up Disc and GBI set them.

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

---

## 2026-09-14 — SMOKE-HW-001 passed on the real GameCube; GBP-PROBE-001 released

**Physical result (gate 1):** SMOKE-HW-001 = PASS. Build `smoke-0002`,
commit `55ed6c1`, DOL SHA-256 `4175f21d…54fe88`, launched through Swiss;
identity block shown, heartbeat counted (537 frames in 8 s, NTSC), X wrote
`sd:/open-gbp/SMOKE-HW-001_smoke-0002.log` via SD2SP2, START returned to
Swiss. Recorded as ENV-HW-001; U-ENV-002 closed; HARDWARE_TESTS.md holds
the log verbatim. The Game Boy Player was not exercised and no GBP
evidence changed.

**Code:** none changed. The probe artifact stays
`build/poc/gbp-probe/gbp-probe.dol`, build `probe-0001`, commit `55ed6c1`,
SHA-256 `36d8b23b14afbc191899ca0ddf4ad9b845cedf6c09a26b3d6a6187a8c2862994`
(verified against the working tree; documentation-only edits do not
affect it).

**Gate 2 released:** GBP-PROBE-001 requested with the procedure in
`poc/gbp-probe/README.md`. Cartridge: not required by the implementation
(TEST handshake and raw reads of CONTROL/IRQ do not depend on it); the
request asks for **no cartridge** to reduce variables, and to record the
GBP attachment state. Link Port: nothing connected. Primary evidence will
be the raw 32-byte blocks and AR_INFO values in the device log, not the
`present=` summary fields.

**When the probe log arrives:** keep the original file untouched, record
its SHA-256, run `tools/probelog.py check`, derive a `.gbpreplay` fixture
with `tools/probelog.py fixture`, run the replay backend against it,
then compare the physical bytes with Start-up Disc, GBI and Dolphin and
update EVIDENCE/UNKNOWNS (U-GBP-004, U-GBP-008) — hardware is the final
authority; contradictions are preserved, not smoothed over.

---

## 2026-09-14 — GBP-PROBE-001 executed: first physical observations of the GBS-DOL

**Physical result:** the probe ran to completion on the real GameCube +
Game Boy Player, 28/28 DMA transfers completed, AR_INFO restored, log
saved. Setup metadata, the verbatim log and its hash are in
`HARDWARE_TESTS.md`; facts are GBP-HW-001…006 in `EVIDENCE.md`. **No
code was changed**; `probe-0001` (`36d8b23b…2994`) remains the executed
artifact.

### Evidence preservation

| Item | Value |
|------|-------|
| Original log (user's copy) | `logs/GBP-PROBE-001_probe-0001.log` (now ignored by Git) |
| Preserved copy, unmodified | `captures/local/GBP-PROBE-001_probe-0001.log`, 4945 bytes, sha256 `98ba20d5bcc32ba65138962dab37abe360659b634512c25423e1b879b96ff014` |
| Transcription made before the file arrived | `captures/local/GBP-PROBE-001_probe-0001.transcript.log` — the 20 data blocks are byte-identical to the original; it lacks the per-transfer ticks/polls/dspcr |
| `tools/probelog.py check` | 45 records, `anomalies=0`; mode A: 2 uniform inverse + 2 "byte1F-only"; mode B: 3 + 1 |
| Replay fixture (versioned) | `captures/fixtures/hw-gamecube-gbp-2026-09-14-probe-0001.gbpreplay`, SOURCE = physical GameCube + GBP; generated from the original; identical to the one generated from the transcription |
| Replay result | `test_gbp_replay <fixture>`: probe logic on the host reproduces the device run exactly — AR_INFO 0043→005b→0043, match_all 2/4 and 3/4, match_1f 4/4 and 4/4, present 0/0, errors 0, byte-0 anomalies logged verbatim (see test) |
| Regressions added | `tests/unit/test_gbp_replay.c` (fixture replay), `tests/unit/test_gbp_probe.c` (sentinel/partial/0x90 blocks kept verbatim), `tests/host/test_hw_fixture.py` (exact bytes, driver readings, blockdiff findings) |

### Byte-level analysis (`tools/blockdiff.py`, full output reproducible from the log)

| Block | MODE A | MODE B | A xor B / note |
|-------|--------|--------|----------------|
| TEST raw (before and after) | `00`×32 | `00`×32 | identical; also `00` *after* the handshake in both modes |
| CONTROL raw #1 | `00`×32 | `94 90`×31 | every byte gains bits 4,7; byte 0 also bit 2 |
| CONTROL raw #2 | `00`×32 | `90`×32 | `94→90` between the two MODE B reads (handshake in between) |
| IRQ raw #1, #2 | `90`×32 | `ae 8a ae ae` + `8a 8a ae ae`×7 | period 4 from offset 1; word 0 differs from words 1–7 only in byte 0 (`ae` vs `8a`) |
| TEST C3 → expect 3C | `7c 3c`×31 | `3c`×32 | A byte 0 has extra bit 6 |
| TEST 3C → expect C3 | `c7 c3×5 c7 c3×25` | `c7 c3`×31 | extra bit 2 at byte 0 (both modes) and at byte 6 (A only) |
| TEST FF → expect 00 | `00`×32 | `00`×32 | clean |
| TEST 00 → expect FF | `ff`×32 | `ff`×32 | clean |

Word views: MODE B IRQ as u32 = `ae8aaeae 8a8aaeae ×7`; as u16 =
`ae8a aeae 8a8a aeae…`; reading it the Start-up Disc way (bytes
0x1D/0x1F) or the GBI way (vote over bytes ≡1 and ≡3 mod 4) gives
`0x8AAE` either way. Every anomaly is an *extra set bit* (never a cleared
one), always at byte 0 except one occurrence at byte 6.

### Timing recorded on hardware

Every transfer: 7–10 polls, 30–37 time-base ticks (TB = 40.5 MHz →
0.74–0.91 µs) between programming CNT_L and seeing CSR bit 5; CSR after
acknowledge `0x0804` (DSPINIT|HALT). Dolphin's model uses 246 CPU cycles
per 32 bytes (≈0.5 µs at 486 MHz) — same order of magnitude; no
difference between MODE A and MODE B; no difference between a window
that answered "nothing" (TEST `00`) and one that answered data.

### DMA/cache backend audit (`src/platform/hsp_backend.c`, compiled object, linker map)

| # | Check | Finding |
|---|-------|---------|
| 1–3 | buffer alignment | `dma_buffer` at `0x80058080`, 32 bytes, `ATTRIBUTE_ALIGN(32)`; next symbol at `0x800580a0` → exactly one Gekko cache line (32 B), shared with nothing |
| 4 | RAM→HSP | `memcpy` into the buffer, then `DCFlushRange` = `dcbf` loop + `sc` (libogc2 `cache_asm.S`), then DMA |
| 5–7 | HSP→RAM | zero-fill, `DCFlushRange`, `DCInvalidateRange` (`dcbi`) **before** the DMA, DMA, `DCInvalidateRange` **after**, then `lwz`×8 copy-out. Same order as the Start-up Disc's read wrapper (`0x8008a13c`: `DCInvalidateRange` before, none after) and GBI (`dcbi` loop before the ARQ read, `0x8005485c`) |
| 8–10 | sync/eieio | none between the six `sth` to `0xCC0050xx`; identical to libogc2 `__ARReadDMA` and to the disc's `0x80089c3c` (plain stores). Cache-inhibited/guarded stores are performed in order on the 750; `DCFlushRange` ends with `sc` (sync in the handler) |
| 11–13 | buffer reuse / stale content | reused for every transfer; before a read it holds the zero fill flushed to RAM; a stale line would return `00` or the previous 32 bytes, never a single extra bit |
| 14 | line sharing | none (see 1–3) |
| 15–18 | size/addresses/direction (from the object code) | `CNT_L = 32`; MMADDR = physical buffer address (`& 0x3FF` high, `& 0xFFE0` low); ARADDR = requested; direction bit 15 of CNT_H = 1 for reads, 0 for writes (libogc convention) |
| 19–20 | CSR bits / completion | refuse on `0x0200` (DMA busy) or `0x0020` (stale flag); poll `0x0020`; acknowledge by writing the CSR with bit 5 set and bits 3/7 cleared (does not ack AI/DSP flags) — same as libogc2 `__ARClearInterrupt` |
| 21 | CPU read before coherence | copy-out only after the flag, the ack and a second `dcbi`; interrupts disabled throughout; no load of the buffer inside the polling loop |
| 22–24 | declared alignment / compiler / volatile | registers are `volatile u16`; stores emitted in source order (disassembly checked); the `& 0xFFE0` on the ARADDR low half was folded away by GCC because callers guarantee 32-byte alignment (harmless) |

Conclusion: no software path explains a single extra bit in byte 0 (or
byte 6). The anomalies are attributed to the bus/device side pending the
baseline experiment (U-GBP-015). What the audit *did* find as
limitations of probe-0001 (not defects in the data):

- **L1 — over-strict "present":** requires all 32 bytes equal to the
  complement; neither official driver does that (below). This is why
  `present=0` was printed with the GBP attached and answering.
- **L2 — zero sentinel:** the buffer is zero-filled before each read, so
  a transfer that moved nothing is indistinguishable from a device
  returning `00` (relevant to GBP-HW-006, TEST reads `00`).
- **L3 — CSR logged after the ack:** `dspcr=0804` never shows bit 5;
  logging the pre-ack value would be more informative.
- L4 — no `sync` between the completion flag and the copy-out beyond
  `dcbi`; equal to the Start-up Disc and GBI, but cheap to add.

### TEST semantics in the Start-up Disc (`0x8008ae3c`, disassembly)

```text
for i in 0..3:
    buf[0..31] = pattern[i]                 // memset(r1+12, p, 32)
    write_block(base+0, buf)                // 0x80089da8: memcpy → staging, DCFlushRange, DMA, wait
    read_block(base+0, buf)                 // 0x8008a13c: DCInvalidateRange(staging), DMA, wait, memcpy(buf, staging, 32)
    if buf[1] != (~pattern[i] & 0xFF): return 5   // lbz r3,13(r1)  ← byte offset 1, 8-bit compare
return 0
```

Pattern table at `0x80272878` = `C3 3C FF 00`. The periodic removal
check (`0x8008b1ac`) does the same with one rotating pattern and also
compares byte 1. **Phase 2 stated "byte 0x1F"; that was wrong for the
TEST check** (0x1F is what the CONTROL/IRQ wrappers use). Corrected in
GBP-TEST-001, REGISTERS.md and INITIALIZATION.md.

### TEST semantics in GBI (`0x80011c94`, `0x80015b08`, `0x80015d9c`)

```text
write_byte(0, p):  block = 32 × p (u32 replicated, dcbz + stores + dcbf + sync)
b = read_byte(0):  dcbi block; ARQ read 32 bytes;
                   for each bit k: count = number of the 32 bytes with bit k set;
                   bit k of b = (count >= 16)              // majority vote
if b != ~p: fail
write_byte(0, b); if read_byte(0) != p: fail
patterns: C3 then FF
```

16-bit reads (`0x80015c64` on `buf` and `buf+2`) vote over bytes
≡1 mod 4 (high byte) and ≡3 mod 4 (low byte). Writes of 16-bit values
replicate `hh ll` over the block (`0x80015da0`).

### Why `present=0`

The probe's `match_all` needs 32/32 bytes; hardware returned 31/32 (or
30/32) in three handshakes. Applying the official rules to the physical
blocks: the disc's byte-1 check passes 8/8; GBI's vote passes 8/8
(`tests/host/test_hw_fixture.py` computes both). `present=` is therefore
a reporting artifact of probe-0001; the Game Boy Player answered the TEST
handshake in both modes.

### Comparison of sources

| Behavior | Hardware (this run) | Start-up Disc | GBI Standard | Dolphin | Class | Conf. |
|---|---|---|---|---|---|---|
| AR_INFO expansion code | DMA + TEST work with code 0 and 3; CONTROL/IRQ contents differ | writes 3 first | writes 3 first | ignores bits 3–5 | FACT (effect exists) / UNKNOWN (semantics) | high / — |
| TEST inversion | bytes 1–31 = ~p, 8/8 | expects byte 1 = ~p | expects vote = ~p | all 32 = ~p | FACT | high |
| TEST byte semantically used | byte 0 unreliable | byte 1 | vote over 32 | any | FACT (byte 0), CORROB. (avoid byte 0) | high |
| TEST persistence | second read `00` | reads once per pattern | reads once per pattern | persistent | FACT for this sequence (L2 caveat) | medium |
| CONTROL read layout | uniform fill (byte 0 transient `94`) | byte 0x1F | vote | fill | FACT | high |
| CONTROL value at idle | `00` (code 0) / `90` (code 3) | — | — | `00`/`03` depending on ROM | FACT (value) / UNKNOWN (meaning) | — |
| IRQ read layout | `hh hh ll ll` per u32, byte 0 anomalous | bytes 0x1D/0x1F | bytes ≡1/≡3 mod 4 | `hh hh hh ll` | FACT; **contradicts Dolphin at byte 0x1E** | high |
| IRQ value at idle | `9090` (code 0) / `8AAE` (code 3) | — | — | `0000` | FACT (value) / UNKNOWN (meaning) | — |
| DMA size / unit | 32 B, 28/28 ok | 32 B (0xF00/0x1000 for AV) | 32 B (+64 B combined) | 32 B chunks | CORROBORATED + FACT | high |
| Endianness | big-endian bytes as DMA'd; 16-bit value assembled hi at lower offset | same | same | same | CORROBORATED | high |
| Readback timing | 0.74–0.91 µs per 32 B | — | — | 246 cycles model | FACT (one console) | medium |
| Byte-0 extra bits | 4/20 reads | avoided | outvoted | never | FACT; **not modeled anywhere** | high (occurrence) |

### New facts, rejected hypotheses, reformulated unknowns

- Facts: GBP-HW-001…006.
- Rejected: "the expansion code is required for the DMA/TEST path to
  work" (GBP-HW-002/003); "TEST returns a persistent inverted copy"
  (GBP-HW-006, with the L2 caveat); "Dolphin's `hh hh hh ll` IRQ layout"
  (GBP-HW-004); Phase 2's "DISC checks byte 0x1F of TEST".
- Reformulated: U-GBP-004 (what does the code change?), U-GBP-008
  (partially answered). New: U-GBP-015 (byte-0 bits), U-GBP-016 (are
  MODE A values device responses?), U-GBP-017 (meaning of `90`/`94`/
  `8AAE`), U-GBP-018 (TEST read-once vs zero-sentinel).

### Next experiment — evaluation

| Option | Information gained | Variables | Risk | Distinguishes |
|---|---|---|---|---|
| A — baseline with the GBP physically removed (console off) | whether TEST inversion, `90`/`00` fills, `8AAE` and the byte-0 bits require the device; open-bus/ARAM-controller behaviour of the window with code 0 and 3 | one (device present/absent); same DOL, same setup otherwise | low (unplugging with power off; same writes as today, to a window that then has no device) | (c) "bus values" from (a)/(b) in U-GBP-004; U-GBP-016; whether U-GBP-015 needs the GBP |
| B — repeat identical run | stability of byte-0 bits, of `94→90`, of `8AAE`; timing spread | none | lowest | only reproducibility; cannot tell device from bus |
| C — minimal official handshake (byte-1 / vote) | that the official criterion passes | changes the software, not the physics | low | nothing the log does not already prove offline (test_hw_fixture.py) |

**Recommendation: Option A.** Every open question now hinges on knowing
which of the observed bytes need the Game Boy Player at all: if the TEST
inversion or the `8AAE` pattern survive without the device, they are
GameCube-side and the Phase 2 model is wrong in a way no repetition would
reveal; if they vanish, GBP-HW-003/004/005 become device facts and the
MODE A fills can be classified. Option B's information (stability) will
come for free from every later run with the device; Option C adds no
physical information. Option A also re-runs the same DOL, so it doubles
as a partial Option B for the GameCube-side behaviour. Not implemented
and not requested here; awaiting authorization.

---

## 2026-09-15 — Experimental pair: GBP attached vs GBP removed; detection policy rebuilt on official semantics

**Inputs:** GBP-PROBE-001 (GBP attached, log sha256 `98ba20d5…f014`) and
GBP-BASELINE-NOGBP-001 (GBP removed with the console off, log
`03e930ff25f10ed25e610cc1ed14e92cd521a4c91d3eef40f4c52079ba19c8f9`,
4944 bytes, preserved unmodified in `captures/local/`), same DOL
`probe-0001` (`36d8b23b…2994`), same console/BBA/controller/Memory
Card/SD2SP2/Swiss, no cartridge, no interaction. Both logs parse with
`tools/probelog.py` (45 records, anomalies=0) and replay exactly through
`src/gbp/gbp_replay.c` (`tests/unit/test_gbp_replay.c` with four
fixtures: two physical, two Dolphin-model).

### Pair diff (`tools/blockdiff.py --pair`, `build/analysis/pair-with-vs-without-gbp.txt`)

| Block | with GBP | without GBP | Allowed interpretation |
|-------|----------|-------------|------------------------|
| MODE A TEST initial / final | `00`×32 | `C0`×32 | differs |
| MODE A CONTROL (both dumps) | `00`×32 | `C0`×32 | `00` needed the GBP |
| MODE A IRQ (both dumps) | `90`×32 | `C0`×32 | `90` needed the GBP |
| MODE A TEST C3 / 3C / FF / 00 | `7c 3c…` / `c7 c3…c7…` / `00`×32 / `ff`×32 | `C0`×32 each | inversion needed the GBP |
| MODE B TEST initial / final | `00`×32 | `C0`×32 | differs |
| MODE B CONTROL #1 / #2 | `94 90…` / `90`×32 | `C0`×32 | `94`/`90` needed the GBP |
| MODE B IRQ (both) | `ae 8a ae ae 8a 8a ae ae…` | `C0`×32 | `AE/8A` needed the GBP |
| MODE B TEST C3 / 3C / FF / 00 | `3c`×32 / `c7 c3…` / `00`×32 / `ff`×32 | `C0`×32 each | inversion needed the GBP |
| AR_INFO orig / A / B / final | 0043 / 0043 / 005b / 0043 | identical | AR_INFO does not encode presence |
| transfers / timeouts / busy / errors | 28 / 0 / 0 / 0 | 28 / 0 / 0 / 0 | **DMA completion is NOT GBP presence detection** |
| per-transfer ticks / polls | 30–37 / 7–10 | 31–38 / 7–10 | indistinguishable |

20 of 20 blocks and 640 of 640 bytes differ. Every physically dependent
behavior of the first run (inversion, byte-0 extra bits, `00/90/94`,
`90/8AAE`, the exp-code effect on CONTROL/IRQ) vanished with the device.
No meaning is assigned to `90`, `94`, `AE`, `8A` or `C0`.

### Official TEST criteria on both runs

| Pattern | Disc criterion (byte 1) with / without | GBI criterion (vote) with / without | whole-block (probe-0001) with / without |
|---------|----------------|------------------|----------------|
| A C3 | PASS / FAIL | PASS / FAIL | FAIL / FAIL |
| A 3C | PASS / FAIL | PASS / FAIL | FAIL / FAIL |
| A FF | PASS / FAIL | PASS / FAIL | PASS / FAIL |
| A 00 | PASS / FAIL | PASS / FAIL | PASS / FAIL |
| B C3 | PASS / FAIL | PASS / FAIL | PASS / FAIL |
| B 3C | PASS / FAIL | PASS / FAIL | FAIL / FAIL |
| B FF | PASS / FAIL | PASS / FAIL | PASS / FAIL |
| B 00 | PASS / FAIL | PASS / FAIL | PASS / FAIL |

Comparison: the disc criterion is one byte compare, exactly Nintendo's;
it survives the byte-0 anomaly but would fail if byte 1 were ever hit
(byte 6 was, once). The GBI vote survives up to 15 corrupted bytes, costs
a 32×8 loop, and is also official (Extrems). Both agree 16/16 on the
physical data. **Policy adopted (`src/gbp/gbp_detect.h`):** compute both;
a mode is PRESENT only if every handshake completed *and* both criteria
passed for every pattern; ABSENT if both failed for every pattern;
otherwise INCONSISTENT (never treated as present). Transport success
(`rc=ok`) is reported separately (`transport_ok=`) and never implies
presence. The whole-block and byte-0x1F counts stay in the log for
continuity only.

### Code changed (build `probe-0002`)

`src/gbp/gbp_detect.{h,c}` (new; `gbp_test_startup_disc_style`,
`gbp_test_majority_vote`, `gbp_test_whole_block`, `gbp_presence_verdict`);
`src/gbp/gbp_probe.{h,c}` (per-handshake `match_b1`, `match_vote`,
`vote=`, per-mode `verdict=`, `transport_ok=`; `present[]` now follows the
policy); `poc/gbp-probe/source/main.c` screen line; build id
`probe-0002`. Raw logging, the transfer sequence, the writes (TEST block
only, AR_INFO bits 3–5) and the HSP backend are unchanged. One
regression caught by the host tests before any hardware run: the longer
`TESTR` records exceeded the 200-byte log line and would have truncated
the hex data; the ring log line is now 256 bytes and a test asserts the
longest record fits (`test_record_length_fits`). New DOL:
`build/poc/gbp-probe/gbp-probe.dol`, sha256
`3f3c7a4b09a5b0f481a28b7681c1ce6f737186d46891a3d53354042cf30a0dda`,
commit `55ed6c1-dirty` (uncommitted tree). **Not run on hardware; no
test requested.**

Validation: C unit tests (ident, ringlog, detect, probe-vs-mock, replay
of both physical fixtures + both Dolphin-model fixtures), Python 60
tests (exact bytes of both runs, pair non-equivalence 20/20 blocks and
640/640 bytes, criteria per pattern), PowerPC build without warnings,
DOL alignment, `make probe-dolphin`: HSP device absent → `a_present=0
b_present=0` (Dolphin returns zeros: 1/4 patterns "pass" → INCONSISTENT),
Dolphin GBPlayer model → `a_present=1 b_present=1`.

Limitations kept as separate items (not causes of anything observed):
L2 zero sentinel, L3 CSR logged after acknowledge, L4 no explicit `sync`
before the copy-out.

### Detection readiness (Phase 3, detection part)

| Item | State |
|------|-------|
| Signal | content of the TEST window read immediately after writing 32×p at `internal_ARAM_size + 0` |
| Criteria | byte 1 == ~p (Start-up Disc) AND per-bit majority vote == ~p (GBI), for each of C3, 3C, FF, 00; all handshakes must complete |
| Corroboration | Start-up Disc `0x8008ae3c`; GBI `0x80011c94`/`0x80015b08`; Dolphin model (uniform inverse) |
| With physical GBP | 8/8 PASS on both criteria (GBP-HW-003/010), with expansion code 0 and 3 |
| Without physical GBP | 0/8 (`C0`×32) (GBP-HW-007/010) |
| What it does not tell | why byte 0 is unreliable (U-GBP-015); what `C0` is (U-GBP-019); which AR_INFO code the runtime should use for the rest of the interface (U-GBP-004) |
| Sample size | one console, one run per state |
| Verdict | presence detection is implementable and validated offline on hardware captures; build `probe-0002` carries it but has not been run on hardware |

Phase 3 is **not** complete: initialization (bringing the AGB up and
observing the device's interrupt/AV state) has not started.

### Next initialization step — proposal only (not implemented, not requested)

Candidates from the official start sequences (INITIALIZATION.md §3):

| Candidate | Writes | Hypothesis tested | Restore | Risk |
|-----------|--------|-------------------|---------|------|
| (i) IRQ mask programming: write IRQ := read with all odd bits set, as the disc does before enabling anything | IRQ window | odd bits are writable masks; even bits are acknowledged by writing them | write back the value read | low, but writing even bits acknowledges sources we have not understood |
| (ii) CONTROL bit 0x10 cleared then restored (`90 → 80 → 90`), PI HSP interrupt kept masked in INTMR, observe PI INTSR bit 13 and the IRQ window before/after | CONTROL (1 bit) | bit 0x10 gates the device's interrupt line to the PI (the Start-up Disc and GBI clear it in start and set it in stop) | rewrite the original byte | low: no handler, PI mask untouched, no AGB power |
| (iii) CONTROL \|= 0x04 (disc step 7 / GBI `\|0x0C`) | CONTROL | powers/resets the AGB; IRQ/AV activity appears | disc stop sequence (clear 0x04/0x08, set 0x10/0x80) | medium: starts the AGB with no cartridge; needs the full stop sequence to be trusted |

**Proposed: (ii).** It is the smallest state change both official
drivers perform, touches one documented bit, is read-only on the PI side
(INTSR observation with INTMR bit 13 still 0), restores by rewriting the
byte that was read, and tests exactly one hypothesis whose outcome is
observable with what we already log (CONTROL, IRQ raw blocks) plus two
extra PI reads. It also settles whether IRQ `0x8AAE` bit 15 correlates
with the PI line, which (i) and (iii) would confound. Run with expansion
code 3 only (the only state where CONTROL/IRQ read as live), restoring
AR_INFO as today. Awaiting authorization before any build or request.

---

## 2026-09-15 — GBP-INIT-001 (CONTROL bit 0x10): provenance check stopped the implementation

**Task:** investigate whether clearing only CONTROL bit 0x10, "using the
same operation observed in the known drivers", changes the observable
interrupt state. Rule: if the Start-up Disc and GBI differ materially,
stop and report before implementing.

**Finding (INITIALIZATION.md §8, from disassembly of `0x8008bf84`,
`0x8008be04`, `0x8008bd50`, `0x80089edc`, `0x8008a1dc` and GBI
`0x8000c03c…`, `0x8000c37c…`):** the isolated operation
`0x90 → 0x80 → 0x90` exists in neither driver. The disc clears 0x10 in
its own write but only after `| 0x04` and with PI HSP already unmasked
and the IRQ mask bits written; GBI clears 0x10 in the same write that
sets 0x04|0x08, with PI still masked. Write layouts also differ (byte
0x1F only vs byte replicated ×32). Only the *set* direction (`| 0x10`)
appears alone (disc sleep callback), which would not change the idle
value 0x90 observed on hardware.

**Decision:** no POC created, no write designed, no build. Options for
the user (none chosen by the agent):

1. Authorize the isolated 0x10 toggle explicitly as a *non-official*
   experiment (single bit, PI masked, restore by rewriting the semantic
   byte). Cleanest for the hypothesis, but outside both references.
2. Follow GBI: one write `(v & ~0x10) | 0x0C` with PI masked, then
   restore via GBI's exit write `(v & ~0x0C) | 0x10`. Official, but the
   variable is no longer a single bit: it powers the AGB (bits 0x04/0x08).
3. Follow the disc: `| 0x04` then `& ~0x10` as two writes, restore with
   the disc's stop sequence (`& ~0x04`, `& ~0x08`, `| 0x10`, `| 0x80`).
   Official, but it also programs the IRQ mask bits first and expects
   the PI interrupt unmasked — two more variables and an IRQ-block write
   the current rules forbid.

Nothing else changed; artifacts `probe-0001` (executed) and
`probe-0002` (host/Dolphin validated) remain as documented.

---

## 2026-09-15 — GBP-INIT-001 implemented (build init-0001, not run on hardware)

**Decision received:** conservative variant of option 2 — GBI's CONTROL
transform under a masked PI HSP interrupt. Terminology: the Start-up Disc
is the official Nintendo reference; GBI is an independent mature
implementation (wording fixed across docs).

**Provenance used:** GBI `0x8000c03c…`: read CONTROL (vote) → write
`(v & ~0x10) | 0x04 | 0x08` (byte replicated ×32) → `IRQ_Request(26)` →
`__UnmaskIrq(0x20)`. Only the write is reproduced, in the PI-masked
regime; the two following calls are not executed. KEYPAD (`:= 0` in GBI
just before) is not reproduced: no functional dependency exists in the
code (separate ARQ transfers; the CONTROL value derives only from the
CONTROL read). INTMR polarity from libogc2 `__SetInterrupts`
(`if(!(nMask&IM_PI_HSP)) imask |= 0x2000; _piReg[1] = imask` → bit set =
enabled) and `__irq_init` (`_piReg[1] = 0xf0` → bit 13 masked at boot).

**Implementation:** `src/gbp/gbp_init_probe.{h,c}` (experiment logic,
S0–S5, fail-safe, restore of the original semantic value, GBI layout);
`src/gbp/gbp_detect.{h,c}` (shared `gbp_detect_handshake`, vote over n
bytes; `gbp_probe.c` now uses it, adding `addr=` to TESTW/TESTR records);
`src/gbp/gbp_transport.h` (+ optional `read_pi`, `write_intmr`, `ticks`);
`src/platform/hsp_backend.c` (PI at `0xCC003000/04`, `gettick`);
`tests/mocks/gbp_mock.{h,c}` (CONTROL/IRQ block models, PI model, faults);
`src/gbp/gbp_replay.{h,c}` (`P r`/`P w` records); `tools/probelog.py`
(PI/CTLW records, `addr=` preference); `poc/gbp-init-probe/*`; `Makefile`
(`init-dolphin`); `tests/unit/test_gbp_init.c`; `tests/host/test_artifacts.py`.

**Preconditions for the single new write:** verdict PRESENT (both
criteria, 4/4, all transfers ok); PI readable; INTMR bit 13 clear (only
that bit cleared if needed, readback-confirmed, restored later); CONTROL
vote == byte 0x1F; idle shape `(v & 0x10) != 0 && (v & 0x0C) == 0`;
transform not a no-op. Snapshots S1–S3 back to back without delay
(neither reference has one), then restore with the original value, S4,
INTMR/AR_INFO restore, S5.

**Validation:** see the report of this session (C/Python counts). Dolphin
without HSP device → `abort_not_present` (zeros → inconsistent). Dolphin
GBPlayer model → `abort_control_shape`: its CONTROL reads `0x03` at idle
(mGBA cartridge bits) instead of the `0x90` idle shape observed on
hardware, so the precondition stops the probe before the write — a
recorded Dolphin/hardware divergence; the write, snapshot and restore
paths are exercised by the host mocks and replay scripts, not by Dolphin. Build is `-dirty`; no hardware request until a
clean commit, rebuild and re-validation.
