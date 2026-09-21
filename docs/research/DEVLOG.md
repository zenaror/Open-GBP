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

---

## 2026-09-15 — GBP-INIT-001 executed (attached + removed): consolidation

**Inputs:** `logs/GBP-INIT-001_init-0001.log` (5497 B, sha256
`d1e90daf…956e`) and `logs/GBP-INIT-001_init-0001-semGBP.log` (2090 B,
`97f7cc70…6c5e`), hashed from the originals, copied unmodified to
`captures/local/`; DOL `init-0001` from clean commit `a3d9668`, sha256
`6068d134…a1e5`. Fixtures `captures/fixtures/hw-gamecube-{gbp,nogbp}-2026-09-15-init-0001.gbpreplay`
with SOURCE/GBP_PRESENT/TEST_ID/BUILD_ID/COMMIT/log hash/size. Both
replay exactly through `gbp_init_probe` (`test_gbp_init.c`: attached →
status ok, 0x90→0x8C→0x90, byte-0 sequence, transition=1, S5 `00`/`9090`,
INTSR bit 13 = 0 everywhere; removed → ABSENT, no CONTROL write, `C1`×32
verbatim). `tools/blockdiff.py --snapshots` produces the per-snapshot
timing/bit table (`build/analysis/init-0001-snapshots.txt`).

### S0–S5 (GBP attached)

| Snap | µs after write | INTSR/INTMR | CONTROL raw → semantic | IRQ raw → semantic |
|------|---------------|-------------|------------------------|--------------------|
| S0 | — | 00010000 / 000001FA | `98 90×31` → 0x90 | `AA 8A AE AE …` → 0x8AAE |
| S1 | 1.38 | same | `EC 8C×31` → 0x8C | `EA 8A AE AE …` → 0x8AAE |
| S2 | 68.05 | same | `AC 8C×31` → 0x8C | `AA 8A AE AE …` → 0x8AAE |
| S3 | 141.2 | same | `AC 8C×31` → 0x8C | `AA …` → 0x8AAE |
| S4 (after RESTORE `90`×32) | 227.9 | same | `98 90×31` → 0x90 | `EA 8A AE AE …` → 0x8AAE |
| S5 (after AR_INFO → 0043) | 340.4 | same | `00`×32 → 0x00 | `98 90×31` → 0x9090 |

Bitwise deltas (set/cleared per offset): S0→S1 CONTROL every byte
`+0C −10` plus byte 0 `+64 −10`; IRQ byte 0 `+40`. S1→S2: CONTROL byte 0
`−40`, IRQ byte 0 `−40`, nothing else. S2→S3: identical. S3→S4: CONTROL
every byte `+10 −0C`, byte 0 `+10 −24`; IRQ byte 0 `+40`. S4→S5:
CONTROL every byte `−90` (byte 0 `−98`); IRQ bytes 1–31 `8A→90`/`AE→90`,
byte 0 `EA→98`.

- **`TRANSITION s1_s2=1` explained:** the probe compares the full 32
  bytes of CONTROL and IRQ and INTSR; the only difference was bit 6 of
  byte 0 in both blocks (`EC→AC`, `EA→AA`). Semantic values unchanged.
- **Bit 6 after the restore:** IRQ byte 0 read `EA` again at S4, taken a
  few µs after the RESTORE write (the S4 CONTROL read intervened);
  CONTROL byte 0 read `98`, as in S0. Recorded as a temporal
  *correlation* only (U-GBP-021); duration bracketed 1.4–68 µs.
- **S4→S5:** restoring the expansion code to 0 changed the view to
  `00`/`9090`, matching GBP-PROBE-001 MODE A. Second independent
  observation → GBP-HW-017 (CORROBORATED). Not "enable".
- Every DMA 29–34 ticks / 7–9 polls in both states; the snapshot spacing
  is the cost of formatting log records, not a delay.

### C0 vs C1 without the GBP (no cause selected)

| Aspect | GBP-BASELINE-NOGBP-001 (probe-0001) | GBP-INIT-BASELINE-NOGBP-001 (init-0001) |
|---|---|---|
| Uniform value | `C0` in every read (20 reads) | `C1` in every read (4 handshake reads) |
| Expansion code at first transfer | 0 (MODE A), later 3 | 3 (set before any transfer) |
| First transfers | three raw reads before any write | a TEST write before any read |
| DMA path | `hsp_backend.c` DMA/CSR code identical between commits 55ed6c1 and a3d9668 (only PI accessors added) | same |
| Handshake code | `gbp_probe.c` handshake | `gbp_detect_handshake` (same operations, `addr=` logged) |
| Buffer | `dma_buffer` 32-aligned, zero-filled+flushed before reads | same, different physical address (`0x800598E0` in init-0001; the probe-0001 address is in the `0x800580xx` region) |
| Build | different DOL size/layout, same toolchain | |
| Physical | separate day, separate power cycle, GBP re-seated between runs | |
| Timing per DMA | 31–38 ticks | 29–34 ticks |

The difference is bit 0 of every byte. Candidates: session/power-cycle
dependent idle level; dependence on the first access being under code 3
or on the absence of prior reads; build-dependent address effects. None
can be selected statically; no dedicated hardware test is proposed for
it (any uniform fill fails detection). Documentation "no GBP = C0"
withdrawn (GBP-HW-019, U-GBP-019).

### Facts / hypotheses / unknowns

New FACTs: GBP-HW-011…020. Kept as HYPOTHESIS: bit 6 correlation with
CONTROL writes; CONTROL/IRQ byte-0 bits as "one signal" — not asserted.
Unknowns: U-GBP-004 updated (code changes the view with device present;
function open), U-GBP-015/020 updated, U-GBP-019 reformulated,
U-GBP-021 new. Not promoted: any meaning for 0x40, 0x90, 0x8AAE, C0/C1,
bits 0x04/0x08/0x10.

### Phase 3 status

**Detection — ready.** Signal: TEST handshake content; criteria: byte 1
(Start-up Disc) AND majority vote (GBI), 4 patterns; validated on four
physical runs (2 attached PRESENT, 2 removed ABSENT) and on the Dolphin
model; transport success is separate. Limitations: one console; byte 0
unreliable (U-GBP-015/021); uniform no-GBP value not fixed (U-GBP-019).

**Initialization — started, not done.** Reproduced from known software:
expansion code 3 (both references), TEST handshake (both), GBI's CONTROL
transform `(v&~0x10)|0x0C` under a masked PI (one write, restored). Not
reproduced: the Start-up Disc's IRQ-block mask programming and its
`|0x04` / `&~0x10` two-write order; `IRQ_Request(26)` + unmask (GBI) /
handler + unmask (disc) with the device-side IRQ acknowledge protocol;
the disc's `|0x08` "run" write; any AV/keypad/SIO path. Divergences
Start-up Disc vs GBI are documented in INITIALIZATION.md §8. Blockers:
none technical; the next steps require unmasking PI HSP with a handler,
which is a new class of operation (interrupt service on the device).
Phase 3 completion criterion (ROADMAP): "reliably detects and
initializes the physical GBP without proprietary runtime code" —
detection met; initialization requires the AGB brought to a running
state with the IRQ path serviced and a documented stop sequence, none of
which has been executed.

### Next experiment — comparison (proposal only)

| Option | New writes | Variables | Reversible | Reference match | Information |
|---|---|---|---|---|---|
| A. Time-resolve bit 6: repeat the same CONTROL write with tighter snapshots (several reads in the first 70 µs, no logging in between) | none new (same 2 CONTROL writes) | 0 new | yes (same restore) | same GBI op | duration/shape of the transient; does not advance initialization |
| B. Next GBI operation: after the transform, `IRQ_Request(26)` + `__UnmaskIrq(0x20)` with a handler that only acks PI and records INTSR/IRQ, then restore (mask, IRQ_Free, CONTROL 0x90) | INTMR bit 13 set (unmask); PI INTSR ack (0x2000) in the handler | 2 (unmask, handler) | yes (mask + restore control) | GBI start, next step in order | whether the device asserts PI HSP after the transform, first IRQ-block change if any; may not fire at all (no cartridge) |
| C. Start-up Disc equivalent: IRQ-block mask write, then `|0x04`, `&~0x10` as two writes, with PI unmasked | IRQ block write + 2 CONTROL writes + unmask | 3+ | partially (disc stop sequence, 4 more writes) | official disc | most complete, most confounded |
| D. Observe IRQ/PI after unmask only (no CONTROL change): unmask bit 13 with an ack-only handler, then re-mask | INTMR bit 13; ack in handler | 1 | yes | neither reference does this alone | tells whether the idle IRQ state (0x8AAE, bit 15 set) already drives the PI line; isolates the PI path from the CONTROL transform |

**Proposed: D, then B.** D changes one variable (INTMR bit 13), writes
nothing on the GBP side, is fully reversible, and answers the question
that decides how to interpret B: does the idle device (IRQ `0x8AAE`,
CONTROL `0x90`) already assert the HSP line when the PI is unmasked?
Both references clear CONTROL 0x10 and unmask around the same point;
D separates the PI-side observation from the CONTROL write. B follows
GBI's actual order and is the real next initialization step. A is
cheaper but does not advance initialization and can be folded into B's
snapshots. C is deferred until the IRQ-block write semantics are
understood. The handler for D/B must only acknowledge PI (write 0x2000
to INTSR) and count/timestamp; no device-side IRQ acknowledge until
authorized separately. Not implemented, not requested.

**Superseded 2026-09-15 (IRQ-path audit, next entry):** Option D is
rejected as a separate physical test, and the idle-unmask stage is also
removed from the next experiment. B, redesigned as GBP-INIT-002 with a
one-shot self-masking handler, is the next step.

---

## 2026-09-15 — IRQ-path audit (analysis only): PI INTSR/INTMR semantics, the two real handlers, the libogc2 dispatcher; Option D rejected; GBP-INIT-002 designed

**Goal.** Before any unmask of PI HSP on hardware: establish what
triggers IRQ 26, how INTSR and INTMR interact, what must be
acknowledged, what the Start-up Disc and GBI handlers really do, and
what the libogc2 actually linked into Open-GBP does when a cause
persists. No code, no DOL, no hardware.

**Inputs.** Start-up Disc: `0x8008a930` (init/install), `0x8008bf84`
(start), `0x8008af08` (handler, disassembled instruction by
instruction), `0x8008be04` (stop), helpers `0x80089ff4` (IRQ write),
`0x8008a31c` (IRQ read), `0x8008a1dc` (CONTROL read), `0x80089edc`
(CONTROL write), `0x80089e40` (KEYPAD write), `0x8008bcc4`; SDK
`0x80069ff0` (dispatcher), `0x80069ca0` (INTMR rebuild), `0x80069ef0`/
`0x80069f70` (mask/unmask), `0x80069c38` (init), `0x8006b1d4`/
`0x800a243c` (reset-switch / debugger acknowledges); complete
enumeration of every reference to `0xCC003000`/`0xCC003004` in main.dol
(`OpenGbpFunc.java refs`: INTSR written only at `0x8008af08`,
`0x8008be04`, `0x8006b1d4`, `0x800a243c`; INTMR written only at
`0x80069c38`, `0x80069ca0`). GBI: `0x8000b400`, `0x8000bf30`,
`0x80058c70`/`0x80058b88` (signal/wait), `0x80058724`/`0x80058780`
(IRQ_Request/IRQ_Free), `0x8005863c`/`0x800585d0` (mask/unmask),
`0x800580e4` (__SetInterrupts), `0x800586a8` (__irq_init), `0x80058360`
(dispatcher), `0x80053eb0`/`0x80052f04` (reset-switch acknowledges);
same enumeration (INTSR written only at `0x8000b400`, `0x80053eb0`,
`0x80052f04`). libogc2: source `ca03fb7` (`irq.c`, `irq_handler.S`,
`exception.c`, `system.c`, `mmce.c`, headers) **and** the binary that is
actually linked, `libogc.a` of the toolchain image (`_V_STRING "libogc2
r2442.094b250"`, `irq.o`/`irq_handler.o` disassembled in the container).
Dolphin `ProcessorInterface.cpp`, `HSP_DeviceGBPlayer.cpp`. YAGCD PI
section.

### Findings

1. **PI.** INTSR `0xCC003000` = cause (bit 13 HSP, bit 16 reset-switch
   state), INTMR `0xCC003004` = mask (bit 13 HSP). IRQ 26 ↔ bit 13 ↔
   software mask `0x20` in the SDK and in libogc: FACT. Cause visible
   independently of the mask; mask gates delivery only: CORROBORATED
   (all three dispatchers test `cause & mask`; the Disc stop writes the
   acknowledge while masked; Dolphin model). Write-1-to-clear:
   CORROBORATED (every INTSR write in libogc2, the SDK, GBI and the Disc
   is a single-bit acknowledge: 2, 0x1000, 0x2000; Dolphin
   `cause &= ~val`). Physical level/edge and "does W1C clear while the
   device asserts": UNKNOWN (U-GBP-022). → GBP-PI-001/002/003.
2. **libogc2 r2442.094b250** (verified in the container binary):
   `c_irqdispatcher` reads INTSR, reads INTMR, tests `cause & mask`,
   maps bit 13 to `IRQMASK(26)`, removes the shadow-masked bits, picks
   one interrupt by priority, calls the handler with EE = 0, returns; it
   never masks the dispatched interrupt, never writes INTSR/INTMR, and
   `irq_exceptionhandler` returns by `rfi`. A persisting unmasked cause
   re-enters immediately; an unmasked cause without a handler does the
   same. `__MaskIrq`/`__UnmaskIrq` rebuild the whole INTMR from shadows,
   so a direct INTMR write can be silently undone (INTMR `0x1FA` on
   hardware is a rebuilt value). `IRQ_Request` returns the previous
   handler (`lwzx r3` before `stwx r4`), `IRQ_Free` too. `__MaskIrq` is
   usable inside a handler (EE save/clear/restore, 16 bytes of stack, no
   allocation, no blocking, no DMA). libogc2 installs no IRQ-26 handler
   itself. → ENV-IRQ-001/002. The source checkout (`ca03fb7`) is not the
   image's commit; the binary check covers the difference for irq.o and
   irq_handler.o only (U-ENV-005).
3. **Start-up Disc.** Handler installed at init while masked; start does
   `OSUnmaskInterrupts(0x20)` → IRQ-register programming → CONTROL
   `| 0x04` → CONTROL `& ~0x10`. Handler: IRQ write (`shadowB | 0x8000`)
   → `INTSR := 0x2000` → IRQ read → if `pending & 0x0555`: IRQ write
   (pending), `keep = pending & (pending ^ pending >> 1)`, KEYPAD write,
   CONTROL read, callbacks by slot → IRQ write (`shadowB`) unless a
   callback suppressed it. ACK order **GBP → PI → GBP → GBP**; no loop;
   several sources served in one pass; an entry with nothing pending
   still performs the two device writes and the PI acknowledge. →
   GBP-IRQ-002.
4. **GBI.** Thread: `KEYPAD := 0` → CONTROL `(v & ~0x18) | 0x0C` →
   `IRQ_Request(26)` → `__UnmaskIrq(0x20)`. Raw handler: `INTSR :=
   0x2000` → signal → return (no mask change). Thread after wake: IRQ
   read → AUDIO/VIDEO/SIODATA reads by bit → 64-byte KEYPAD+IRQ write
   (`IRQ := value_read | 0x8000`) → CONTROL/SIOCTL read → … → `IRQ := 0`
   → loop; exit `__MaskIrq(0x20)` → `IRQ_Free(26)` → CONTROL
   `(v & 0xE3) | 0x10`. ACK order **PI (handler) → GBP (thread)**, INTMR
   bit 13 enabled in between. No storm protection beyond the W1C. GBI is
   an independent mature implementation, not official software. →
   GBP-IRQ-003.
5. **Storm risk.** Real and unbounded in two cases: unmask without a
   handler; handler returns with `INTSR & INTMR` still set. Ended with
   certainty only by clearing INTMR bit 13 inside the handler
   (`__MaskIrq(IM_PI_HSP)`); the INTSR W1C is not a guaranteed exit
   while U-GBP-022 is open. The Disc masks first at stop; every
   libogc/SDK driver depends on INTMR gating. → GBP-PI-003, safety note
   in U-GBP-022.
6. **Inference (HYPOTHESIS, not promoted).** Because GBI leaves INTMR
   bit 13 enabled between its PI acknowledge and its device write and
   does not storm, either the PI latches the HSP cause and W1C clears
   it, or the GBS-DOL deasserts by itself. GBP-INIT-002 separates these.

### Decisions

- **Option D (unmask the idle device with an acknowledge-only handler)
  — rejected** as a separate physical test. INTSR bit 13 = 0 in every
  GBP-INIT-001 snapshot with INTMR bit 13 = 0 already says, given
  GBP-PI-001, that the idle state (CONTROL `0x90`, IRQ `0x8AAE`) holds
  no latched cause; unmasking would add risk and state without answering
  a needed question. An acknowledge-only handler is also unsafe
  (finding 5).
- **Idle-unmask stage removed** from the next experiment as well
  (`__UnmaskIrq` → short idle wait → `__MaskIrq` → transform): the first
  unmask happens only after the validated CONTROL transform, so the
  experiment has one state change (the transform) followed by one new
  observation channel (the unmask).
- The 340 µs window of GBP-INIT-001 says nothing about interrupt
  latency after the transform (GBI waits without a timeout). That, not
  the idle state, is what the next experiment measures.
- The device-side IRQ register stays **read-only**: neither reference's
  stop path depends on a prior device-side acknowledge (both mask PI and
  set CONTROL 0x10). Residual state is U-GBP-023.

### GBP-INIT-002 — design (approved conceptually; not implemented, not released)

Full specification in HARDWARE_TESTS.md "Planned tests"; rules
promoted to INITIALIZATION.md §9. Sequence:

```text
PRESENT (validated policy) → AR_INFO exp code 3 → PI snapshot
→ preconditions: INTMR bit 13 == 0, INTSR bit 13 == 0, CONTROL idle shape (abort otherwise; never adjust silently)
→ old = IRQ_Request(IRQ_PI_HSP, one-shot handler)        [handler BEFORE any experimental write]
→ CONTROL := (original & ~0x10) | 0x0C                    [validated transform, GBI layout]
→ S1: PI, CONTROL, IRQ (still masked)
→ t_unmask = gettick(); PI read; __UnmaskIrq(IM_PI_HSP)   [unmask AFTER the transform, never before]
→ wait: fired || gettick() - t_unmask >= T_MAX
→ __MaskIrq(IM_PI_HSP)  (idempotent; the handler already did it if it ran)
→ S2: PI (two reads), CONTROL, IRQ; copy of the handler fields
→ CONTROL := original ; S3: PI, CONTROL, IRQ
→ if INTSR bit 13 == 1: INTSR := 0x2000 (masked; Disc-stop precedent) → PI read
→ IRQ_Request(IRQ_PI_HSP, old)  [restore previous handler; expected NULL]
→ AR_INFO restore → S4: PI, CONTROL, IRQ; INTMR compared with S0
```

One-shot handler (conceptual; only PI MMIO, no DMA, no logging, no
allocation, no blocking): `tb_entry = gettick(); intsr_before = INTSR;
intmr_before = INTMR; count++; __MaskIrq(IM_PI_HSP); INTSR := 0x2000;
intsr_after = INTSR; intmr_after = INTMR; fired = 1; return`. Shared
state: `volatile uint32_t fired, count, tb_entry, intsr_before,
intmr_before, intsr_after, intmr_after` — 32-bit only (the project's
`gettick()` is the 32-bit time-base low word, `__builtin_ppc_mftb` in
`timesupp.h`; difference arithmetic wraps every ~106 s at 40.5 MHz; no
64-bit stores in the handler). The main loop copies the fields only
after IRQ 26 is masked again. A second entry (`count > 1`) is possible
only if INTMR gating failed; the handler re-masks and returns, the main
loop records it as an anomaly.

Mandatory order, to be proven by host regression when implemented:
`IRQ_Request` before the CONTROL experimental write; the CONTROL
experimental write before `__UnmaskIrq`; never unmask without a
handler; never unmask before the transform in this experiment.

Writes allowed: AR_INFO bits 3–5, TEST handshake, CONTROL transform and
restore (all validated), INTMR only through `__MaskIrq`/`__UnmaskIrq`,
INTSR W1C `0x2000` (precedent: Disc and GBI). Not written: GBP IRQ,
KEYPAD, VIDEO, AUDIO, SIO.

W1C policy: CORROBORATED, not a physical FACT; the handler masks first,
then writes `0x2000`, then re-reads INTSR; bit 13 still 1 after the W1C
is an observation, not an error — the main loop continues under mask.

Previous-handler policy: `IRQ_Request` returns the previous handler in
r2442.094b250 (binary-verified) and libogc2 installs none for IRQ 26;
the POC records the returned value and restores it with
`IRQ_Request(…, old)` (not `IRQ_Free`, which would drop a non-NULL
handler). The expected original mask state is "masked"; if IRQ 26 is
found unmasked at S0 the run aborts as an unexpected precondition.

Timeout: `T_MAX = 2000 ms`, an operational bound (screen + SD log must
always happen; GBI has none). Result on expiry: "no IRQ 26 observed
within T_MAX", never "the GBP does not interrupt". Re-evaluate the value
before implementation; any other value is justified as safety/usability
only.

Restore plan (idempotent, same order on every abort path): 1. ensure
IRQ 26 masked; 2. CONTROL original; 3. observe PI; 4. INTSR W1C only if
bit 13 is set; 5. previous handler; 6. original IRQ-26 mask state;
7. AR_INFO; 8. final snapshot. Teardown completes before the SD flush
and before returning to Swiss.

Residual risks: INTMR gating of bit 13 not yet observed on hardware
(CORROBORATED only); un-acknowledged device state (U-GBP-023, power
cycle after the run); AGB powered up to T_MAX with no cartridge and
then cut, as GBI's exit does; a timeout is ambiguous (no IRQ-register
mask programming is performed, unlike the Disc); libogc2 source/binary
version mismatch covered only for irq.o/irq_handler.o (U-ENV-005). Bit
6 of byte 0 (U-GBP-021) and C0/C1 (U-GBP-019) get no dedicated test;
S1–S4 will record byte 0 anyway.

### Docs updated (this entry)

EVIDENCE (ENV-IRQ-001/002, GBP-PI-001/002/003, GBP-IRQ-002/003; source
shorthands; GBP-IRQ-001 pointer), UNKNOWNS (U-ENV-005, U-GBP-007 note,
U-GBP-022, U-GBP-023), HARDWARE_TESTS (planned GBP-INIT-002),
INITIALIZATION (§2, §4, §6, §8.5, new §9), REGISTERS (§4, §5, header),
HSP.md (§2, §4), ARCHITECTURE.md (interrupt row), external/README
(libogc2 versions). No code, no DOL, no commit.

### Next

User checkpoint (commit of this documentation), then the implementation
of GBP-INIT-002 under the rules of INITIALIZATION.md §9 with host
regressions first: mock PI with programmable cause behavior (never
asserts / asserts once and W1C clears / level until CONTROL 0x10 is
restored / re-asserts after W1C), a storm detector counting handler
entries while the mock's INTMR bit 13 is set, order assertions
(request < transform < unmask), replay of the GBP-INIT-001 fixtures
through the new probe; Dolphin run (model: CONTROL `0x03` shape →
precondition abort, as for GBP-INIT-001); clean commit; only then a
hardware request.

---

## 2026-09-15 — GBP-INIT-002 implemented (build `initirq-0001`, NOT run on hardware)

**Base:** clean commit `21a2f3d` (IRQ-path audit checkpoint). Working
tree dirty during development; the development DOL is
`build/poc/gbp-init-irq-probe/gbp-init-irq-probe.dol`, commit
`21a2f3d-dirty`, SHA-256
`d1011fcb65767ee29969af1429665905238e356d2ed097fcaf06f8539a84c751`
(not a release artifact: a clean commit, rebuild and re-validation come
first; no hardware request was made).

**What was built.** `poc/gbp-init-irq-probe` (Test ID `GBP-INIT-002`,
gecko prefix `OPENGBP-INITIRQ`), `src/gbp/gbp_init_irq_probe.{h,c}`
(sequence + idempotent teardown), `src/gbp/gbp_irq_oneshot.h` (the
one-shot handler body, included by the real backend AND by the host
mock so both execute the same statements), `src/platform/hsp_backend.c`
(`hsp_backend_oneshot_isr`, `IRQ_Request`/`__MaskIrq`/`__UnmaskIrq`
operations, INTSR W1C), `src/gbp/gbp_transport.h` (`struct
gbp_irq_record`, optional `write_intsr` / `irq_install` / `irq_restore` /
`irq_mask` / `irq_unmask` / `irq_record`; `gbp_transport_has_irq_path`),
`src/gbp/gbp_rawlog.{h,c}` (logged block/PI reads shared by new probes;
GBP-INIT-001's executed code kept untouched), `tests/mocks/gbp_mock.*`
(synthetic interrupt model + order/invariant detector),
`tests/unit/test_gbp_init_irq.c`, `tools/isr_audit.py` +
`tests/host/test_isr_audit.py`, replay op `P a` (INTSR acknowledge) in
`gbp_replay.c` / `probelog.py`, Makefile targets `initirq-dolphin` and
`initirq-audit`.

**Sequence implemented (mandatory order, proven by the mock trace):**
AR_INFO bits 3–5 := 3 (readback) → presence gate (PRESENT only) → PI
preconditions (INTSR bit 13 == 0 AND INTMR bit 13 == 0, else
`abort_pi_precondition` with reason `intsr13_set` / `intmr13_unmasked` /
`pi_unavailable`; nothing is masked or acknowledged silently) → S0 (PI,
CONTROL, IRQ, TEST) + CONTROL shape (vote == byte 0x1F, bit 0x10 set,
bits 0x0C clear) → `irq_install` (previous handler kept verbatim,
NULL or not; `abort_handler_install` if the transport has no IRQ path)
→ CONTROL := (v & ~0x10) | 0x0C, GBI layout → S1 (masked) → PI read,
`t_unmask`, `__UnmaskIrq(IM_PI_HSP)`, PI read (no formatting inside)
→ `abort_unmask` if INTMR bit 13 did not become 1 and the handler never
ran → wait for `fired` or T_MAX (poll of the record + time base, no DMA)
→ `__MaskIrq` → copy of the record → S2 (INTSR twice) → teardown:
CONTROL := v → S3 → PI read → single INTSR W1C only if bit 13 is still
set (never a loop) → previous handler back → mask verified (one retry)
→ AR_INFO → S4. Result codes: `ok_irq_observed`,
`timeout_no_irq_observed` ("no IRQ 26 within T_MAX"), the aborts above,
`abort_control_read/shape`, `transport_error`; restore result separate
(`restore=ok|error`, reason `mask_failed` / `control_restore_failed` /
`handler_restore_failed` / `mask_not_restored` / `arinfo_restore_failed`).

**Handler** (code order = statement order): `gettick()` → INTSR → INTMR
→ `count++` → **`__MaskIrq(IM_PI_HSP)`** → **`INTSR := 0x2000`** → INTSR →
INTMR → first-entry fields → `fired = 1`. Second entry: re-mask,
re-acknowledge once, keep its view; main reports `reentry=1`. Shared
state: nine `uint32_t` fields, copied by the main loop only after the
re-mask; deltas by wrap-safe 32-bit subtraction, µs computed outside the
handler. Static audit of the linked object (`make initirq-audit`,
`build/poc/gbp-init-irq-probe/isr-audit.txt`): 70 instructions, the only
call is `bl __MaskIrq`, `mftb`, PI base `lis -13312` (0xCC00), `li 8192;
stw` after the `__MaskIrq` call, no indirect branch, no other symbol —
CLEAN.

**Tests.** C: `test_gbp_init_irq` 494 checks (present/no IRQ, IRQ at
unmask, IRQ after N ticks, IRQ past T_MAX, W1C clears / does not clear
INTSR, second entry despite the mask, mask ignored → storm cap and
`mask_not_restored`, absent `C1`, inconsistent, handshake transport
failure, INTSR bit 13 set, INTMR bit 13 unmasked, PI unavailable,
CONTROL 0x80 / 0x9C / Dolphin 0x03 / ambiguous / read failure, previous
handler NULL and non-NULL, install failure, transport without IRQ ops,
failures at the EXP write / S1 / S2, CONTROL restore ignored, handler
restore failure, unmask ineffective, ring overflow, line lengths with a
wrapping time base, the mock's inversion detector driven by hand
[unmask without handler; unmask before CONTROL; restore while unmasked;
AR_INFO before the IRQ teardown; DMA while unmasked], event-order
assertions on every full run; physical init-0001 fixtures: attached →
gate PRESENT, physical S0, preconditions pass, stops at
`abort_handler_install`/`irq_ops_unavailable` before any write, AR_INFO
restored, replay clean; removed → ABSENT verbatim, 13 replay steps).
All older suites unchanged (9+17+24+143+342+315). Python: 68 passed
(artifact identity/records of the new DOL, probelog `P a`, isr_audit
checker + the audit of the real object). Dolphin (`make
initirq-dolphin`): no HSP → `abort_not_present` (reason `inconsistent`,
Dolphin's zero fill passes the FF pattern), `written=0`,
`arinfo_restored=1`; GBPlayer model → `abort_control_shape`
(`control_orig=03`), `verdict=present det=4/4`, `written=0`, no handler
installed. Regressions `init-dolphin`, `probe-dolphin`, `smoke-dolphin`:
PASS. `make inspect`: every DOL 32-byte aligned, entry 0x80003100.

**Divergences from the design text.** (1) AR_INFO bits 3–5 are set
before the handshake (GBP-INIT-001 order; both references; needed for
verbatim fixture replay), not after the gate as the numbered list says;
every prerequisite still precedes anything experimental and the ABSENT
path restores AR_INFO. (2) S3 is taken inside the teardown right after
the CONTROL restore, and the final snapshot S4 is taken only when
something experimental happened (handler installed or CONTROL written),
so early aborts do not add reads that the physical fixtures never
recorded. (3) The handler also re-acknowledges on a second entry (one
W1C per entry, never a loop), a defensive addition to the design's
"re-mask and return". (4) T_MAX stays 2000 ms — re-evaluated: it bounds
the AGB power-on window and guarantees the screen/SD path; it is not a
GBP property.

**Residual risks (unchanged, U-GBP-022/023):** INTMR gating of bit 13
not yet observed on hardware; un-acknowledged device state after the
run → power-cycle; AGB powered up to T_MAX without a cartridge, then cut
(as GBI's exit does); a timeout is ambiguous; libogc2 source/binary
mismatch covered only for irq.o/irq_handler.o (U-ENV-005). Status:
**implemented, NOT physically executed.** Next: user checkpoint → clean
rebuild → HARDWARE_TESTS release fields (commit, DOL SHA-256) → hardware
request.

---

## 2026-09-15 — GBP-INIT-002 executed: consolidation, GBI start re-audited (semaphore starts at 1), IRQ-register model, next experiment

**Inputs.** `logs/GBP-INIT-002_initirq-0001.log`, 6585 bytes, sha256
`e7ec3d83212fb183d8209452e2ce46cf391a696ff8a41720fd9f7701dbf1ea1d`
(computed from `logs/`, matches the expected value; original untouched;
identical copy in `captures/local/`); DOL `initirq-0001`, clean commit
`4e3cb43`, sha256 `1bd2bcf3…43f2`. Fixture
`captures/fixtures/hw-gamecube-gbp-2026-09-15-initirq-0001.gbpreplay`
(metadata header + the 52 operations of the run). Replay extended only
as far as the physical observations required: `T <ticks>` lines carry
the console's time-base values so `since_write`/`since_unmask`/
`wait_ticks` replay exactly; `I i/u/m/r` carry the interrupt-path
operations as they happened; the `I u` record is all zeros because the
handler never ran — **no interrupt is invented**. `tools/probelog.py`
emits them from SNAP/CTLW/UNMASK/WAIT/IRQ/HANDLER records (the WAIT
time-base values are emitted before the `I m` that precedes them in the
log, matching the probe's call order); `tools/blockdiff.py --snapshots`
now reads the `PI tag=Sn` records of the new probes.
`test_gbp_init_irq` replays the run: 586 checks (all `now()` calls
matched by physical values, `tick_polls = 0`, `exhausted = mismatches =
0`); Python 74 passed (fixture bytes, order, timeline, generator).

### Physical result

`timeout_no_irq_observed` / `no_irq26_within_t_max`, `restore=ok`,
PRESENT 4/4 both criteria (32/32 only 1/4: `3D 3C…`, `D3 C3…`, `11 00…`,
`FF`×32 — the whole-block criterion is not a gate), `written=1`,
`fired=0 count=0 timed_out=1 reentry=0`, every restore ok, 21 transfers,
0 DMA timeouts/busy, 0 dropped/truncated. **Not an error:** no IRQ 26
within the 2000 ms operational window.

1. **INTMR gating, physically (GBP-HW-022).** Before the unmask INTSR
   `0x00010000` / INTMR `0x000001FA`; 33 ticks (0.81 µs) after
   `__UnmaskIrq(IM_PI_HSP)`: INTMR `0x000021FA` (bit 13 = 1), INTSR
   unchanged; after `__MaskIrq`: INTMR `0x000001FA` in S2, S2b, S3,
   MASKCHK, S4. Bits `0x1FA` never changed. The former "INTMR gating of
   bit 13 not observed physically" is superseded for the mask/unmask
   effect (now FACT); the delivery gating itself was not exercised (no
   cause). Not extrapolated to other PI interrupts.
2. **Window.** `t_max_ticks = 81000000`, `wait_ticks = 81000012` =
   2.0000003 s at 40.5 MHz (12 ticks = 0.3 µs overshoot); S2 at
   2.000035 s after the unmask. 13871306 polls = 144 ns per poll: a
   property of the loop, not of the hardware.
3. **No IRQ 26 (GBP-HW-023).** Restricted FACT: with the GBP present, no
   cartridge, CONTROL `0x8C`, expansion code 3, INTMR bit 13 = 1 and the
   GBP IRQ register never written, no IRQ 26 was observed in 2 s; the
   handler never entered (all HANDLERPI fields 0); INTSR bit 13 stayed 0
   in all 12 reads. Not recorded: "the GBP does not generate IRQs",
   "CONTROL does not generate IRQs".
4. **IRQ register `0x8AAE → 0x8FAE` (GBP-HW-024).** S1 (124 ticks after
   the transform, masked): `9B 8A AE AE 8A 8A AE AE …`; S2 (2 s later,
   masked again): `9F 8F AF AE 8F 8F AF AE …`. 24 of 32 bytes changed,
   offsets ≡ 3 mod 4 unchanged, XOR per group `05 05 01 00`; semantic
   `0x8AAE ^ 0x8FAE = 0x0500` = bits 0x0400 and 0x0100 set, odd bits and
   bit 15 unchanged. The two low copies now differ (`AF AE`): offset ≡ 2
   mod 4 has bit 0 set; both references read ≡ 1 / ≡ 3 mod 4 and agree on
   0x8FAE (U-GBP-025). CONTROL was byte-identical in S1 and S2 (`9D 8C×31`).
   After CONTROL := 0x90, S3 still read 0x8FAE. When inside the window
   the change happened, and whether elapsed time, the unmask, internal
   GBS-DOL activity or a combination drove it, is unknown (U-GBP-024);
   "the unmask caused 0x8FAE" is not asserted.
5. **AR_INFO restore (GBP-HW-025).** S4 under code 0: CONTROL `00`,
   IRQ `9090` — the MODE A view for the third time in three different
   sequences; "code 3 changes the view with the GBP present" is
   CORROBORATED (U-GBP-004 updated); still not "enable".
6. **Teardown (GBP-HW-026).** Cleanup W1C not needed (INTSR bit 13 = 0),
   previous handler (NULL) restored, INTMR final `0x1FA`, AR_INFO
   `0x0043`, S4 taken before any SD I/O. Byte-0 extras of this run: +0x01,
   +0x10, +0x11 (CONTROL `91`/`9D`/`11`, IRQ `9B`/`9F`/`91`, TEST `3D`/`D3`/`11`);
   the transient bit 6 of GBP-INIT-001 did not reproduce → U-GBP-021
   re-evaluated: byte 0 carries additional, run-dependent bits not
   representative of the voted value; the 0x40 transient is a historical
   observation of one run, not a rule (U-GBP-015/020 updated).

### Semantics of 0x0400 / 0x0100 — revalidated in the binaries

GBI thread `0x8000bf30`, after `read IRQ` (`0x80011c14(0xD00000, 0x20)`,
16-bit value = vote(≡1 mod 4) << 8 | vote(≡3 mod 4), `0x80015c64`):
`& 0x400` → `0x8000be48(0x800000, 0x8017A320, 0x1000, req, 0x8000b75c)` =
ARQ read of the AUDIO window, callback = audio consumer (converters
`0x8000a7e0`/`0x8001094c`/`0x80010a44`, `AUDIO_*` at `0x80051b98`/
`0x80051c2c`); `& 0x100` → `0x8000be48(0x100000, 0x80179420, 0xF00, req,
0x8000a8e0)` = VIDEO window read, later tested for the frame-start word
`0x80800000`; `& 0x40` → `0x8000be48(0x900000, …, 0x20, req, 0x8000fa58)`
= SIODATA read → message queue; `& 0x10` → 64-byte KEYPAD write
0x0304/0x0300. Disc: slots keyed by `0x801B34C8 = {0x0001, 0x0040,
0x0010, 0x0004, 0x0400, 0x0100}`; slot 4 → `0x8008cdc4` → `0x8008a764`:
DMA read `base + 0x800000`, 0x1000 bytes, 70-entry ring; slot 5 →
`0x8008ed68` → `0x8008a480`: `base + 0x100000`, 0xF00 bytes, 40-entry ring;
registered by `0x8008c7c0`/`0x8008e994` from the library init
`0x8008f1fc`, before start. So the bits that appeared physically are the
bits both drivers service as AUDIO (0x0400) and VIDEO (0x0100). Kept
separate: hardware observation = FACT; bit → driver action = FACT (code);
"the hardware was requesting audio/video" = HYPOTHESIS (no data read).
→ GBP-IRQ-005.

### Source/mask pairs

| Pair | Source candidate | Paired mask candidate | Polarity (H) | Reference writes | Expected effect on HSP | Confidence |
|---|---|---|---|---|---|---|
| bits 8/9 | 0x0100 video (both drivers) | 0x0200 (Disc table `0x801B34D4[5]`) | 1 = masked; idle 1 | Disc start: 0 if slot 5 has a callback (normal), 1 otherwise; GBI: `read \| 0x8000` then 0 | with 0x0200 = 1, a set 0x0100 does not reach PI | pairing C, polarity H |
| bits 10/11 | 0x0400 audio (both drivers) | 0x0800 (`0x801B34D4[4]`) | idem | idem | idem | idem |
| bit 15 | — | global flag | 1 = masked/servicing; idle 1 | Disc: 1 at handler entry and at stop, 0 at exit / DMA done; GBI: 1 after reading, 0 with `IRQ := 0` | with 1, nothing reaches PI (H) | H |
| bits 2/3 | 0x0004 (Disc slot 3 "game pak" stop) | 0x0008 | — | — | pending at idle on this console (no cartridge) | H |

The Disc handler's own filter `keep = pending & (pending ^ (pending >> 1))`
(bit i kept iff bit i set and bit i+1 clear) is the strongest code
evidence for the pairing. **Why INTSR bit 13 stayed 0 with 0x0400/0x0100
set and INTMR bit 13 = 1** — hypotheses weighed: (a) the paired mask bits
(0x0800, 0x0200) and/or bit 15 block propagation: consistent with the
idle value, with both references clearing them before waiting, and with
Dolphin's contrary prediction failing; not separable between "odd bits"
and "bit 15" yet; (b) sources latched but not IRQ-enabling by
themselves: subsumed by (a); (c) initialization incomplete: yes, in the
precise sense of (a) plus GBI's `KEYPAD := 0`; (d) no cartridge: the
sources asserted without one, so cartridge absence is not needed to
explain the missing PI IRQ; (e) another missing reference operation:
found — GBI's first-pass IRQ writes (below); (f) the source/mask
interpretation is wrong: possible, nothing supports it; the next
experiment discriminates. No new hypothesis invented.

### GBI re-audit: the operation GBP-INIT-002 omitted

The earlier reading ("GBI waits without programming the IRQ block") was
wrong. `0x80058b88` is `LWP_SemWait` (blocking, no timeout; `0x80072c8c`
enqueues when the count is 0), `0x80058c70` is `LWP_SemPost` (called only
from the raw handler), **and the semaphore is created with
`LWP_SemInit(&sem, 1, 1)` at `0x800113a0`** (`li r4,1; li r5,1; addi
r3,r13,344; bl 0x80058ad4`, inside `0x8001123c`, the same function that
writes AR_INFO `|= 0x18`). The first `LWP_SemWait` therefore returns at
once and the first pass of the loop runs before any interrupt: read IRQ →
dispatch by bits → 64-byte write at `0xCFFFE0` = KEYPAD := 0 + **IRQ :=
read | 0x8000** → 64-byte read at `0x4FFFE0` (CONTROL, SIOCTL) → … →
**IRQ := 0** (32 bytes at `0xD00000`) → only then block. These are the only
IRQ-register writes in gbi.dol (`callsites 8000bea4`); no other thread,
callback or earlier function writes it, and there is no cartridge
special case. → GBP-IRQ-004; INITIALIZATION.md §3/§4 corrected. GBI
additionally writes `KEYPAD := 0` before the transform.

### Start-up Disc equivalent

Disc: `OSUnmaskInterrupts(0x20)` → `IRQ := (read & ~(0x8000 | odd bits of
serviced slots)) | (odd bits of unserviced slots)` → CONTROL `| 0x04` →
`& ~0x10`. From the physical 0x8AAE: normal flow (all six slots serviced
before start) → `IRQ := 0x0004`; init mode 3 (no AV callbacks) → `IRQ :=
0x0A04`; no callbacks at all (never the case in the Disc) → `IRQ :=
0x0AAE`. Would that programming have let 0x0400/0x0100 propagate to PI
HSP? Under the polarity hypothesis, yes (0x0800/0x0200 and 0x8000
cleared); the values are FACT (code), the propagation is HYPOTHESIS —
CORROBORATED only in the sense that GBI's `IRQ := 0` clears the same bits
and GBI works. Not applied to hardware.

### Docs updated

HARDWARE_TESTS (executed entry, log verbatim, release fields), EVIDENCE
(GBP-HW-021…026, GBP-IRQ-004/005, GBP-PI-003 and GBP-IRQ-003 corrected),
UNKNOWNS (U-GBP-004/007/015/020/021/022/023 updated, U-GBP-024/025 new),
INITIALIZATION (§3/§4 GBI corrected, §8.5, §9 R6, new §10 register
model), REGISTERS (§2 IRQ row, §2.1 low-copy asymmetry, §4 bits 8/10/odd/15
with hardware, §5 INTMR toggle), HSP.md (§2 rows), captures/README, POC
README (executed, result). GBP-INIT-002 is marked PHYSICALLY EXECUTED.

### Phase 3 — initialization readiness

Physically validated: detection (five runs), AR_INFO expansion-code
handling and restore, CONTROL transform and restore, one-shot handler
installation/restoration with the previous handler preserved,
`__MaskIrq`/`__UnmaskIrq` on INTMR bit 13, safe timeout with full
teardown, no IRQ under this incomplete sequence, an evolving GBP IRQ
state (audio/video sources pending) while the AGB is powered. **Still
missing for "initialization functional":** (1) programming of the GBP IRQ
register the way a reference does before waiting (masks/bit 15) — no
IRQ 26 has ever been delivered; (2) the first physical PI HSP cause:
delivery gating, INTSR W1C with a real (possibly still asserted) source,
level/edge (U-GBP-022); (3) the device-side acknowledge protocol in
service (write-back of the pending bits, re-arm) without storms and with
the audio/video cadence; (4) KEYPAD refresh on every interrupt (both
references); (5) a documented stop sequence with the device re-masked
(Disc: `IRQ := read | disable`, CONTROL `& ~0x04`, `& ~0x08`, `| 0x10`,
`| 0x80`); (6) the meaning of the idle source bit 0x0004 and of a
cartridge being present (bit 0x02) — untested. Video is not started.

### Next experiment — comparison (after the source/mask analysis above)

| Option | New writes | Risk | Reversible | Reference match | Relevance to normal execution / video | Information |
|---|---|---|---|---|---|---|
| A. Program only the necessary GBP IRQ configuration per a reference | 1 IRQ write (GBI: `IRQ := 0`; or the Disc word `0x0004`) + 1 restore write (`IRQ := S0 value`) | medium: enables every source, incl. the idle-pending 0x0004; storms bounded by the one-shot handler's self-mask; device re-masked by the restore write and CONTROL 0x10 | yes (write back the S0 value; CONTROL 0x90; power cycle) | GBI (`IRQ := 0`) or Disc (mask word) | high: it is the step both references take before waiting | first PI HSP delivery, INTSR W1C behavior, mask-model polarity (U-GBP-007/022) |
| B. Reproduce GBI's first pass more faithfully | `KEYPAD := 0`, `IRQ := read \| 0x8000` (64-byte with KEYPAD), `IRQ := 0`, + restore | medium, more variables (KEYPAD, 64-byte layout) | yes | GBI exactly | high | same as A plus GBI's ack-write semantics; harder to attribute |
| C. Minimal Start-up Disc sequence | unmask first, then IRQ mask word, CONTROL `\| 0x04` then `& ~0x10` as two writes, stop sequence (4 CONTROL writes + IRQ write + INTSR ack) | medium-high, most writes, unmasked before the device programming | yes (Disc stop) | official Disc | high | official order; confounded by 6+ new writes |
| D. Repeat with a cartridge | none new | low | yes | — | low now | the sources asserted without a cartridge: not the blocking variable |
| E. Read-only timing of 0x8AAE → 0x8FAE (masked PI, repeated IRQ reads after the transform) | none | lowest | yes | neither | low (does not advance initialization) | U-GBP-024 only; can be folded into a later probe's snapshots |

**Recommendation: A, in two masked-first steps, as GBP-INIT-003 — one
new register, two new writes, both with precedent.** After the validated
sequence up to S1 (handler installed, CONTROL 0x8C, PI masked): (1) write
`IRQ := 0` (GBI's value, GBI layout 32 × 00) **with PI HSP still masked**,
then read PI: if INTSR bit 13 becomes 1 while masked, the cause is
observed with no exception at all (GBP-PI-001 confirmed physically) and
the device-side masks are shown to gate it; (2) `__UnmaskIrq` with the
one-shot handler and the same 2000 ms bound (a masked cause would
deliver at once; latency measured as before); (3) teardown as in
GBP-INIT-002 plus `IRQ := <S0 value>` written back before CONTROL 0x90
(restores the idle masks; the Disc's stop writes `read | disable` for
the same purpose), the cleanup W1C, handler and mask restore, AR_INFO,
S4; power cycle afterwards. The register's read-only status (R6) is
lifted only for these two values, only with authorization, and the IRQ
block keeps being read raw at every snapshot. Expected outcomes are
kept open: bit 13 = 1 after the write (mask polarity confirmed, first
cause), or no change (bit 15 or another requirement — then B/C).
Timeout stays an operational bound. Not implemented, not requested.

---

## 2026-09-15 — IRQ-register write/restore analysis before GBP-INIT-003 (analysis only)

**Why.** The previous recommendation ended the teardown with `IRQ := <value
read in S0>`. That is withdrawn: under the field semantics below, writing
0x8AAE back is not a restore — it acknowledges every source bit it
carries (bit 2, pending at idle on this console) and re-writes masks that
may already differ. No write, no DOL, no hardware in this step.

**Every known write to the IRQ register (index 0xD).** Start-up Disc
(primitive `0x80089ff4`: bytes 0x1E/0x1F of the staging buffer, the other
30 bytes stale from the previous transfer, 32-byte DMA to base+0xD00000):
start `0x8008bf84` → `(read & ~(0x8000 | odd bits of slots with a
callback)) | (odd bits of slots without)` — reconstructed from the
callback table, read-derived only for the bits it does not own; handler
entry `0x8008af08+0x28` → `shadowA | 0x8000` (constant); handler
write-back `+0x4c` → the 16-bit value just read, unmodified (only when
`pending & 0x0555`); handler exit `+0x228` → `shadowA` (constant; skipped
when an AV callback started a DMA); DMA-done `0x8008b14c` → `shadowA`
(constant); stop `0x8008be04` → `read | (0x8000 | odd bits of serviced
slots)` — read-derived, OR-ed. GBI (u16 replicated `hh ll` ×16, ARQ
writes): first and every pass `0x8000c194` → 64 bytes at 0xCFFFE0 =
KEYPAD := pad state, IRQ := `read | 0x8000` (read-derived, OR); end of
every pass `0x8000c360` → `IRQ := 0` (constant); no other write anywhere
(`callsites 8000bea4`), none at exit. Dolphin: `m_irq &= ~value` on every
write, `AssertIRQ` sets `source | 0x8000`, only Audio/Video are ever
asserted.

**Per-bit table (0..15).** Even bits 0/2/4/6/8/10 = the six Disc slots
{0x0001 app callback `0x8008c370`; 0x0004 "game pak" → stop `0x8008bdb0`;
0x0010 sleep → CONTROL |0x10; 0x0040 serial completion `0x8008c3a4`;
0x0100 video read; 0x0400 audio read} and GBI's tests {0x0400 audio,
0x0100 video, 0x0040 SIODATA, 0x0010 KEYPAD wake}; GBI ignores 0x0001,
0x0004 and every odd bit. Odd bits 1/3/5/7/9/11 = the Disc's paired
masks (`0x801B34D4`), written as levels, never tested by GBI. Bits 12–14:
no driver writes 1 or tests them; 0 on hardware. Bit 15: separate (below).
Hardware (expansion code 3): idle `0x8AAE` = bits 1,2,3,5,7,9,11,15; after
2 s with the AGB powered `0x8FAE` = same + 8, 10. Under code 0 the window
returns the uniform value 0x90 (`0x9090`), not an IRQ reading.

**Pairs.** 0/1, 2/3, 4/5, 6/7, 8/9, 10/11: paired by the Disc's two tables
and by its handler filter `pending & (pending ^ (pending >> 1))` (a source
is dispatched only when the bit above it is 0) — CORROBORATED; even bit =
source (both drivers act on it), odd bit = mask (only the Disc writes it,
as a level); polarity 1 = masked — HYPOTHESIS supported by the idle value
and by the fact that both references clear the odd bits before waiting;
source W1C — CORROBORATED (Disc write-back of the pending word, GBI
`read | 0x8000`, Dolphin); mask level-written — CORROBORATED (Disc writes
0/1 per slot, GBI writes 0). 12/13 and 14/15 are **not** pairs in any
driver: the rule is not generalized beyond bits 0–11.

**Bit 15, separately.** Disc: 1 at handler entry and at stop, 0 at start,
exit and DMA-done, never tested. GBI: 1 right after each read, 0 with
`IRQ := 0`, never tested. Dolphin: `IRQ_ASSERTED` (set with any source,
W1C, drives the line — masks ignored). Two readings fit every driver
write: (i) global hold/mask, level-written, 1 = masked (the Disc's
"mask → read → ack → unmask" and GBI's "ack+hold → process → release"
patterns); (ii) "any source pending" summary, W1C (Dolphin's model; the
hardware's 1 at idle with bit 2 pending and 1 in 0x8FAE fit too). Not
discriminated by anything observed. A masked write of 0 read back
decides: 0 → (i); still 1 → (ii). Kept outside the pair model.

**GBI first pass, exact order** (semaphore created with
`LWP_SemInit(&sem, 1, 1)` at `0x800113a0`):

```text
0x8000c060  KEYPAD := 0 (32 B, ARQ)                       PI HSP masked
0x8000c068  v = vote(read CONTROL)
0x8000c08c  CONTROL := (v & 0xE7) | 0x0C                   AGB powered
0x8000c09c  IRQ_Request(26, 0x8000b400)
0x8000c0a4  __UnmaskIrq(0x20)                              PI HSP enabled; GBP register still idle (masks set)
pass 1:     LWP_SemWait(sem) returns at once (1 → 0)       no interrupt involved
            read IRQ (0xD00000, 32 B, vote)                D: yes, reads before writing
            irq & 0x400 → ARQ read AUDIO; & 0x100 → VIDEO; & 0x40 → SIODATA; & 0x10 → KEYPAD wake   E: yes, if already pending
0x8000c194  write 64 B at 0xCFFFE0: KEYPAD := 0, IRQ := irq | 0x8000    A: first IRQ write, AFTER the unmask (acknowledge + bit 15)
0x8000c1a4  read 64 B at 0x4FFFE0 (CONTROL, SIOCTL)
0x8000c214  write 64 B at 0x4FFFE0: CONTROL := value read, SIOCTL := computed   (every pass)
0x8000c360  IRQ := 0 (32 B)                                B: BEFORE the first blocking wait; masks (and bit 15) → 0
pass 2:     LWP_SemWait(sem) blocks (count 0) until the raw handler posts
```

C: yes — from `__UnmaskIrq` until `IRQ := 0` PI is unmasked while the
device's masks are still the idle ones; under the model nothing can be
delivered in that window (and if something were, the post would only make
pass 2 not block). F: `KEYPAD := 0` is GBI's normal state initialization;
the first pass does not depend on it and rewrites KEYPAD anyway; whether
the device needs it is unknown (the Disc writes KEYPAD only from its
handler and its 5 ms tick). Note the context of GBI's `IRQ := 0`: it always
follows `read | 0x8000`, i.e. the pending sources have just been
acknowledged; it is an unmask (six masks and, under (i), bit 15), not an
acknowledge, performed with PI unmasked.

**GBI exit.** After the last completed pass (`IRQ := 0`), the exit path
`0x8000c37c` does `__MaskIrq(0x20)`, `IRQ_Free(26)`, CONTROL `(v & 0xE3) |
0x10`; no IRQ write, no restore of masks, no reset: the register is left
"0-programmed plus whatever the device raised since", gated by PI mask +
CONTROL 0x10 + the AGB powered off (0x0C cleared). Precedent for "IRQ = 0
+ CONTROL stop" as an exit state; normalization comes from the next
software's start or a power cycle.

**Disc stop.** Mask PI → CONTROL `&~0x04`, `&~0x08`, `|0x10`, `|0x80` →
read IRQ → `IRQ := read | 0x8000 | (odd bits of serviced slots)` → INTSR
W1C. Semantically reconstructed, read-derived only for the source bits
(written back = acknowledged): not a restore of the pre-start state but a
**known stop state** — everything masked, pending sources cleared. With
all six slots serviced the OR value is 0x8AAA.

**`IRQ := 0`, operationally (model):** source bits written 0 → untouched
(W1C not triggered; pending stays pending); all six masks → 0 (enabled);
bit 15 → 0 = global unmask under (i), no-op under (ii); not an
acknowledge. GBI issues it with PI unmasked, after acknowledging. Bits
12–14 written 0 as both references do.

**0x8FAE.** Sources 2 (game pak), 8 (video), 10 (audio) pending; masks
1,3,5,7,9,11 set; bit 15 set → explains the absence of any HSP cause under
the model. Minimal writes that change only the masks of 8/10 without
acknowledging anything: `IRQ := 0x80AA` (bit 15 kept), or `0x00AA` (bit 15
cleared too — required under (i)); no driver ever writes such a word.

**Strategies (bits changed from a 0x8FAE-like state, model assumed):**

| Strategy | Value | Bits changed | Writes | Precedent | Reversible | Storm risk (PI masked / unmasked) | Causality | Toward init |
|---|---|---|---|---|---|---|---|---|
| A GBI `IRQ := 0` | 0x0000 | bit 15 (if level) + 6 masks = 7; sources untouched | 1 | GBI, every pass (after an ack) | Disc stop write | none / bounded by the one-shot handler | all sources enabled at once | high |
| B masks of 8/10 only | 0x00AA (or 0x80AA) | 3 (or 2) | 1 | none literal | Disc stop write | none / bounded | best (audio/video only) | medium (model-dependent) |
| C Disc start word | `read & ~0x8AAA` → 0x0504 | 7 + acknowledges 3 sources = 10 | 1 | official | Disc stop write | none / bounded | ack and unmask confounded; next event needed | high |

**Teardown per strategy (all):** CONTROL := original (0x90) → read IRQ →
`IRQ := read | 0x8AAA` (Disc stop formula: all masks + bit 15, pending
acknowledged) → read IRQ → PI read → INTSR W1C once if bit 13 set → PI read →
AR_INFO → final snapshot → power cycle. Options compared: raw S0 write-back
— **rejected** (not a restore; acknowledges bit 2); GBI exit (leave 0 +
CONTROL 0x10) — precedent, but leaves the device unmasked; Disc stop word
— best supported (official, semantic); computed mask state — same as the
Disc word; "leave known + power cycle" — the safety net in every case.
Decision: Disc stop word, power cycle mandatory.

**One run or two.** Split: **GBP-INIT-003A** (PI never unmasked, no handler)
answers "what does the write change in IRQ/CONTROL/INTSR while delivery
stays blocked" and discriminates the field semantics by read-back
(masks 0 → level; bit 15 0 → (i) / 1 → (ii); sources still set → W1C;
INTSR bit 13 = 1 while masked → cause visible under mask, GBP-PI-001 to
FACT); it cannot storm (libogc keeps IRQ 26 masked, Swiss too). **003B**
then reproduces the proven programming with the one-shot handler and the
unmask. Reason against: one extra physical run; no technical reason.
Recommended: split, with strategy A in 003A.

**003A sequence (proposal, not implemented):** PRESENT → AR_INFO 3 → PI
preconditions → S0 (PI, CONTROL, IRQ, TEST) → CONTROL `(v & ~0x10) | 0x0C` →
S1 → (optional read-only samples of IRQ over ≤ 100 ms for U-GBP-024) →
read IRQ → `IRQ := 0` (GBI layout, 32 × 00) → S2 immediately (IRQ, PI,
CONTROL) → reads at ≈ 50 µs, ≈ 500 µs, ≈ 5 ms, ≈ 50 ms, ≈ 500 ms (time-base
spacing, PI masked, no invented hardware property) → teardown as above →
power cycle. Residual risks: an asserted line for ≤ 1 s with PI masked
(no CPU effect), a model error that leaves the device asserted behind
CONTROL 0x10 (power cycle), bits 12–14 written 0 (both references do it).
Cartridge not introduced (sources appear without one); byte 0 evidence only.

**Dolphin OSD (permanent requirement).** The yellow overlay lines are OSD
messages: "Video Info: …" (`OGLConfig.cpp:723`, `OSD::AddMessage`) and
"USBGecko: Listening on TCP port …" (`EXI_DeviceGecko.cpp:68`,
`Core::DisplayMessage`); `OSD::DrawMessages` draws them only when
`Config::MAIN_OSD_MESSAGES` = `[Interface] OnScreenDisplayMessages` is
true. The runner already passes per-run overrides with `-C
Dolphin.<Section>.<Key>=<Value>` into an isolated user directory, so the
fix is one entry in `dolphin_cmd()` of `tools/dolphin_smoke.py`:
`"Dolphin.Interface.OnScreenDisplayMessages=False"` (proposed, not
applied; no profile change). Every future screenshot then shows only the
POC's framebuffer.

---

## 2026-09-15 — GBP-INIT-003A design consolidated (A1/A2 with PI masked); Dolphin OSD disabled per run

**Decision applied.** GBP-INIT-003A does not write `IRQ := 0` over the
initial read-back. It reproduces GBI's first loop pass as two separate
writes with PI HSP masked for the whole run: A1 `IRQ := irq_read |
0x8000` (source acknowledge, the W1C GBI performs with the bits it read
as 1), snapshot, one or two read-only samples, `irq_before_zero` read,
then A2 `IRQ := 0` (mask/control programming), snapshot, temporal
samples (≈ 50 µs … ≤ 2 s, time-base spacing, structured records only),
then the Start-up-Disc-style stop. No handler, no `__UnmaskIrq`, no INTMR
write; INTMR bit 13 = 1 at the start aborts. An INTSR bit 13 = 1 inside
the window is observed only (no W1C there), with at least one snapshot
of INTSR + IRQ + CONTROL of the same moment; the window may end early
afterwards. Every outcome is valid; none is an error. GBP-INIT-003B
(handler + unmask + delivery) is future and depends on 003A's result.
Full sequence, properties and write list: HARDWARE_TESTS.md "Planned
tests — GBP-INIT-003A".

**Stop formula confirmed.** Disc stop `0x8008be04` writes `IRQ := read |
shadow`, `shadow = 0x8000 | odd bits of the slots with a callback` as
set by start `0x8008bf84`; with the six slots serviced (the disc's normal
flow, and the state 003A creates with A2 = 0) `shadow = 0x8AAA`, so
`stop_irq = read | 0x8AAA` is the applicable formula: masks of the six
slots + bit 15, pending sources written as 1 (acknowledged under W1C).
No slot/callback detail makes 0x8AAA inadequate for that configuration
(mode 3 of the disc, no AV callbacks, would give 0x80AA — not our case).
New fact (GBP-IRQ-006): the disc's init calls stop with `shadow = 0`
(`r13 - 0x7050` at `0x80272050` is BSS; `_SDA_BASE_ = 0x802790A0`), i.e.
its first IRQ write is `IRQ := read` with PI masked — for the idle value
0x8AAE byte-identical to GBI's `read | 0x8000`. Official precedent for A1
under a masked PI.

**GBI write layouts, from the binary.** 16-bit register writes (IRQ,
KEYPAD): the u16 replicated 16 times, `hh ll hh ll …` over 32 bytes
(`0x80015da4` fills 8 words of `value << 16 | value`); `IRQ := 0`:
`0x80015da0(buf, 0)` = 32 × 00; the KEYPAD+IRQ write is one 64-byte block
(`0x80015ddc`: first half keypad u16 replicated, second half irq u16
replicated) DMA'd at base+0xCFFFE0 so that the second half lands at
base+0xD00000; CONTROL/SIOCTL: byte replicated ×32 per half (`0x80015d9c`,
`0x80015dd4`). 003A writes only the 32-byte IRQ half at base+0xD00000 with
the same u16-replicated layout (bytes 0x1E/0x1F = hi/lo, the positions
the disc writes). Raw S0 write-back stays prohibited; the only end
states with precedent are the disc's stop word and GBI's "0 + CONTROL
stop"; 003A uses the disc's.

**Dolphin OSD (permanent requirement, applied).** `tools/dolphin_smoke.py`
now adds `Dolphin.Interface.OnScreenDisplayMessages=False` to the
per-run overrides (next to `UsePanicHandlers=False`); the key gates
`OSD::DrawMessages` (VideoCommon/OnScreenDisplay.cpp), which drew "Video
Info: …" (OGLConfig.cpp) and "USBGecko: Listening on TCP port …"
(EXI_DeviceGecko.cpp via Core::DisplayMessage). No other Dolphin setting
changed; nothing in the user's profile — the override lives in the
runner's isolated user directory for every run.
`tests/host/test_dolphin_smoke.py` asserts the command line carries the
override (and only the two Interface keys). Validation: `make
smoke-dolphin` PASS and a GBP-INIT-002 absent run PASS with the patched
runner; yellow-overlay pixels (R > 150, G > 150, B < 90) in the captured
frames: before ≈ 2400 (rows 21–110, the OSD boxes), after 0 in both
captures; visual check: only the POC's console text. Recorded as:
**Dolphin OSD disabled per-run by runner override.**

---

## 2026-09-15 — GBP-INIT-003A implemented (dirty build initirqa-0001); NOT physically executed

**Goal.** Implement the experiment designed in the previous entry as
`poc/gbp-init-irq-program-probe` (Test ID `GBP-INIT-003A`, Build ID
`initirqa-0001`) without executing it: A1 `IRQ := read | 0x8000`, A2
`IRQ := 0`, PI HSP masked for the whole run, Start-up-Disc stop word,
every write captured with its raw buffer, every outcome a valid
observation. No hardware run, no hardware request, no commit.

**Changes.**
- Real backend split: `src/platform/hsp_backend.c` keeps the DMA,
  AR_INFO, PI reads, the INTSR W1C, a new `poll_intsr` and the time base;
  `src/platform/hsp_backend_irq.c` holds the INTMR write, the one-shot
  handler and the `IRQ_Request`/`__MaskIrq`/`__UnmaskIrq` wrappers.
  GBP-INIT-001/002 link both (`hsp_backend_irq_transport()`); GBP-INIT-003A
  links only the base, so its binary cannot contain an unmask, a handler
  install or an INTMR store. `make initirq-audit` now disassembles
  `hsp_backend_irq.o` (result unchanged: CLEAN, calls only `__MaskIrq`).
- Transport: optional `poll_intsr` (cheap INTSR read for polling loops);
  replay grammar `P p <intsr>`, `poll_increment`, `last_intsr`.
- `src/gbp/gbp_regwrite.{h,c}`: capture-then-log write primitive. IRQ
  register = the u16 replicated 16× (`hi lo …`, GBI `0x80015da4`; bytes
  0x1E/0x1F are the Disc's positions), CONTROL = byte ×32. Records `IRQW`
  / `CTLW … t_after=` are formatted only when the caller asks.
  `gbp_rawlog.c` split into read and log halves for the same reason.
- `src/gbp/gbp_initirqa_probe.{h,c}`: AR_INFO 3 → PRESENT gate (ABSENT →
  `abort_not_present`, else `abort_inconsistent`) → PI preconditions →
  BASE (PI, CONTROL, IRQ, TEST) → CONTROL shape → IRQ shape
  (`(v & 0x0AAA) == 0x0AAA`, bit 15 set, `(v & 0x7000) == 0`, Disc reading
  == GBI reading) → CONTROL `(v & ~0x10) | 0x0C` → P0 (INTMR bit 13
  re-check) → A1PRE (shape re-check) → A1 → A1-0, +50 µs, +500 µs → A2PRE
  (INTMR re-check) → A2 → A2-0, +50 µs … +2000 ms with INTSR polling
  (counter only), EVENT snapshot at the first INTSR bit 13 = 1, early
  end → teardown: CONTROL restore + readback, IRQ read, `stop = read |
  0x8AAA`, write, re-read, PI, at most one W1C, AR_INFO, FINAL. The
  experimental region (A1PRE … end of the window) captures into
  structures and formats afterwards (`REGION formatted_inside=0`);
  attempted/completed counted per write; per-step restore flags;
  `power_cycle_required`; the BASE raw block is never written back.
- Mock: synthetic SOURCE_MASK model of the IRQ register (even bits W1C,
  odd bits level, bit 15 level or W1C summary, programmable re-assertion,
  INTSR bit 13 raised while INTMR stays masked), `poll_intsr`, failure
  knobs, wrap-safe timers.
- Tests: `tests/unit/test_gbp_initirqa.c` (14 scenario groups, event
  order, "never" properties, layouts byte by byte, physical init-0001 and
  initirq-0001 prefixes up to the first experimental write, `--dump-log`
  / `--replay` modes); `tests/host/test_poc_audit.py`;
  `tests/host/test_initirqa_replay.py` (synthetic round trip, files under
  `build/`); probelog extended (`IRQW`, `CTLW t_after`, `SNAP tag=EVENT
  poll_intsr`, `WINDOW t_end`, `--note`) with tests; artifact tests.
- Tools/build: `tools/poc_audit.py`; Makefile targets `initirqa-audit`,
  `initirqa-dolphin`; POC registered in `POCS`, `all` and the artifact
  tests. Docs: HARDWARE_TESTS planned entry marked IMPLEMENTED / NOT
  PHYSICALLY EXECUTED; INITIALIZATION.md pointer; tools, captures and
  tests READMEs; the POC README.

**Tests executed.** C (host): 9 + 17 + 24 + 143 + 342 + 315 + 586 + 1859
= 3295 checks, 0 failures; every earlier physical fixture still replays
(probe-0001 ×2, init-0001 ×2, initirq-0001). Python: 96 tests OK, none
skipped after the build. `make initirqa-audit`: 0 findings — objects
`gbp_detect gbp_initirqa_probe gbp_rawlog gbp_regwrite gbp_transport
hsp_backend main opengbp_ident ringlog sdlog`; `gbp_regwrite_irq_u16`
called 3× from the probe object only, `gbp_regwrite_control_byte` 2×;
INTMR stores 0; INTSR stores 1 (`h_write_intsr`); ELF without
`hsp_backend_oneshot_isr`, `gbp_initirq_probe_run`, `gbp_init_probe_run`,
`hsp_backend_irq_transport`; `__UnmaskIrq` defined by libogc2 only, no POC
object references it. Negative control on the real `hsp_backend_irq.o`:
6 findings (forbidden object, `__UnmaskIrq`, `IRQ_Request`, handler,
`__MaskIrq` to investigate, INTMR store in `h_write_intmr`). Dolphin
(runner OSD override, isolated user dir): smoke PASS; probe absent /
present PASS; init absent / present PASS; initirq absent / present PASS;
initirqa absent → `abort_inconsistent` PASS; initirqa GBPlayer model →
`abort_control_shape` PASS; 0 OSD-colored pixels in both new
screenshots. Divergence recorded: Dolphin without an HSP device answers
every read with zeros, so the FF handshake matches 1/4 and the verdict
is INCONSISTENT (the physical console without a GBP answered C1 ×32 =
ABSENT); GBP-INIT-003A splits the two statuses, GBP-INIT-002 did not.

**Result.** GBP-INIT-003A IMPLEMENTED — NOT PHYSICALLY EXECUTED. DIRTY
BUILD — NOT A PHYSICAL CANDIDATE: `gbp-init-irq-program-probe`, build
`initirqa-0001`, `commit=664f0de-dirty`, DOL 367 712 bytes, SHA-256
`52133dc93c164adb71d0dab52ff3fee0e4837f0cdeda22b7f52a601982923695`
(review only; the physical candidate is a clean build after the review
and a separate clean audit).

**Newly confirmed behavior.** None (no hardware run). **Rejected
hypotheses.** None. **New unknowns.** None; U-GBP-022…026 stay on 003A's
critical path. **Corrections found while implementing.** (a)
`tools/probelog.py` emitted the cleanup `P a` after the `PI tag=CLEANUP`
read; it belongs between the CLEANUPCHK and CLEANUP reads (never hit
before: no physical run performed a cleanup). (b) GCC encodes the PI
register stores as `lis; ori; stw 0(r)`, so an audit keyed on
displacements would miss an INTMR store; `poc_audit.py` tracks register
values instead and is proven against the real GBP-INIT-002 object.

**Next.** Review of this dirty tree → user checkpoint → separate clean
audit → clean build = physical candidate with its SHA-256 recorded →
hardware request per the POC README (power cycle mandatory afterwards).

**Micro-audit of attempted/completed (same day, before the checkpoint).**
Rule: for every write that may have reached the device, `attempted = 1`
is stored before the transport is invoked and `completed = 1` only after
rc == ok (`gbp_regwrite.h`). Found: the per-write flags already obeyed
it (`do_write` sets `attempted` before `write_block`), but the probe's
own counters and `control_written` / `power_cycle_required` were updated
after the call returned — no functional effect in synchronous code, yet a
deviation from the rule; moved before every transport call (CONTROL exp,
A1, A2, STOP). Also found and fixed: the single `INITIRQA end` record
could exceed the 255-byte line in a worst case (longest status + reason +
restore_reason with 10-digit time-base values), which would have cut
`power_cycle_required` off its tail — split into `INITIRQA end`,
`WRITES` (per-write attempted/completed, `uncertain`), `OBSERVED` and
`RESTORE`; `WINDOW` records shortened. The report's
`irq_writes_attempted == 0` on the physical-prefix replays is the probe's
safety counter (no IRQ-register write function was ever invoked on that
path; the unanswered write there is the CONTROL write, reported
`attempted=1 completed=0`, power cycle required) — not a mock counter;
the mock's device-side counter is `irq_writes`. Tests: the mock gained a
`write_hook` invoked at the entry of `write_block`, and
`test_attempted_flags_at_call_time` samples the flags at that moment for
the nominal run and for A1 / A2 / CONTROL / STOP failures;
`test_worst_case_line_lengths` drives the longest records. Busy refusals
(returned by `hsp_backend.c` before the DMA is programmed) are treated
like timeouts: attempted, not completed. `test_gbp_initirqa`: 1951
checks. DOL rebuilt (still `664f0de-dirty`, review only).

---

## 2026-09-15 — GBP-INIT-003A executed: first physical programming of the GBP IRQ register, first HSP cause captured at the PI; WINDOW A1 logging defect; next experiment analyzed

**Goal.** Consolidate the first physical run of GBP-INIT-003A (commit
`d956b1b`, DOL `8c225bd1…bfa5`, log `logs/GBP-INIT-003A_initirqa-0001.log`
13231 bytes sha256 `ae911745…2ef8`, verified from `logs/`; preserved
unchanged as `captures/local/GBP-INIT-003A_initirqa-0001.log`), resolve
the `WINDOW tag=A1 intsr13_seen=1` inconsistency, build the physical
fixture, replay it end to end, promote the evidence, and analyze (not
implement) the next experiment. No hardware run, no new DOL, no commit.

**Result of the run.** `ok_pi_cause_observed restore=ok`, 44 transfers,
0 timeouts/busy/errors, 102 lines, 0 dropped/truncated, every write
attempted = completed, `uncertain=0`, `power_cycle_required=1`. Detection
PRESENT 4/4 (whole-block 3/4: the 3C handshake had byte 0 `C7`; the
whole-block criterion is not a gate). PI `0x00010000` / `0x000001FA` at
PRE, BASE and P0. BASE CONTROL 0x90, IRQ 0x8AAE (`AE 8A AE AE / 8A 8A AE
AE …`), TEST 00. CONTROL → 0x8C. **A1** `IRQ := 0x8AAE`: readback 0x8AAA
19 ticks (0.47 µs) later and at +2029 / +20255 ticks — `0x8AAE ^ 0x8AAA =
0x0004`, the source bit written as 1 cleared, the odd bits and bit 15
stayed 1; INTSR bit 13 = 0 in A1-0, A1-50US, A1-500US and A2PRE. **A2**
`IRQ := 0x0000`: readback 0x0000 at +22 ticks, +50 µs, +500 µs, +5 ms,
+50 ms; CONTROL 0x8C throughout; INTSR bit 13 = 0 throughout. **EVENT** at
t = 4155517524 = t_a2 + 4263568 ticks = 105.2733 ms after A2 (105.79 ms
after A1, 105.92 ms after the CONTROL write; the 740497th poll, ≈0.14
µs/poll): INTSR `0x00012000`, INTMR `0x000001FA`, CONTROL 0x8C, IRQ
0x0400 (`04 04 04 00 ×8`); the previous sample at +50.00 ms had INTSR bit
13 = 0 and IRQ 0x0000, so both rose between 50.00 and 105.27 ms; the
window ended early (`deadlines=4/6`). Teardown: CONTROL 0x90 restored
(+0.905 ms after the EVENT); IRQSTOPPRE 0x0500 (`05 05 04 00 / 05 05 05
00 ×7`, bit 0x0100 risen after the EVENT, ≈1.0 ms); stop `IRQ := 0x8FAA`
→ readback 0x8AAA (both sources cleared, masks and bit 15 read 1);
CLEANUPCHK INTSR `0x00012000` still set with the device sources gone; one
`INTSR := 0x2000` → `0x00010000`; AR_INFO 0x005B → 0x0043; FINAL under
code 0: CONTROL 00, IRQ 0x9090, INTSR bit 13 = 0, INTMR 0x1FA.

**WINDOW A1 inconsistency — audited, logging defect, no A1 event.** The
record `000047 WINDOW tag=A1 … intsr13_seen=1` was formatted by
`flush_window()` after the whole A2 window had ended (the experimental
region defers all formatting), and the field printed `res->intsr13_seen`,
the run-global first-sighting flag (`gbp_initirqa_probe.c` at `d956b1b`,
line 230; the same string is in the executed DOL). `note_intsr13()` keeps
only the first sighting with its phase and timestamp: `OBSERVED
first_phase=A2 t_first_intsr13=4155517524 polls_at_first=740497` places it
in the A2 window at the EVENT; had any of the 3407 A1 polls seen bit 13,
the phase would read `A1` with an A1-range timestamp. The primary records
A1-0, A1-50US, A1-500US and A2PRE all read INTSR bit 13 = 0. **There was
no INTSR bit 13 during A1.** Fix for later builds: phase-local flags
`a1_intsr13_seen` / `a2_intsr13_seen` (set by the polls and snapshots of
each phase) printed as `intsr13_in_phase=` in both WINDOW records; the
global flag stays in OBSERVED. Tests: the mock scenario "cause after A2"
now requires `WINDOW tag=A1 … intsr13_in_phase=0`, a new scenario with a
cause visible from the CONTROL write on requires 1 in both, and the
physical fixture replay requires `intsr13_in_phase=0` (A1) / `=1` (A2).
The log is preserved as written; the fixture keeps the real chronology;
the replay ignores the WINDOW A1 fields (only `WINDOW tag=A2 t_end=` is
consumed, as a time-base read). No DOL was rebuilt: the executed binary
stays `d956b1b` / `8c225bd1…bfa5`, and the corrected source is not a
physical candidate until the next clean audit.

**Fixture and replay.** `captures/fixtures/hw-gamecube-gbp-2026-09-15-initirqa-0001.gbpreplay`,
generated by `tools/probelog.py fixture` from the preserved log with the
metadata header (SOURCE, GBP_PRESENT, TEST_ID, BUILD_ID, COMMIT,
DOL_SHA256, LOG_SHA256, LOG_SIZE, NOTEs); 85 operations, every raw block
and every time-base value verbatim, the INTSR poll that saw bit 13 as `P
p 00012000`, the single PI acknowledge as `P a 00002000` between the two
PI reads. `tests/unit/test_gbp_initirqa.c` replays it with the console's
deadlines: `exhausted=0 mismatches=0 tick_polls=0 step=85`, every value
above asserted (raw bytes included); poll counters are the replay's own
(1 per sample) and are documented as such. `tests/host/test_hw_fixture.py`
pins the header, the three IRQ writes, the acknowledge order, the 16 IRQ
reads byte for byte, the timeline and the offset-2 pattern. The old
physical fixtures regenerate identically with the HEAD and HEAD~1
generators (checked during the release audit) and keep passing.

**Evidence promoted (EVIDENCE.md).** GBP-HW-027…034 (run facts),
GBP-PI-004 (INTSR bit 13 captured independently of INTMR, latched,
cleared by W1C — FACT for bit 13; promotes GBP-PI-001/002 and the gating
part of GBP-PI-003 to FACT for bit 13), GBP-IRQ-007 (model update):
sources 2/8/10 write-1-to-clear FACT; odd bits level-written FACT,
polarity 1 = masked CORROBORATED (bit 15 moved with them in both runs);
bit 15 writable/persistent both ways FACT, "W1C pending summary" REJECTED,
"level global hold" HYPOTHESIS; `0x0400 → AUDIO`, `0x0100 → VIDEO` FACT
(code, GBP-IRQ-005 re-used: Disc slots 4/5 `0x8008cdc4 → 0x8008a764`,
`0x8008ed68 → 0x8008a480`; GBI reads 0x1000 / 0xF00), "the physical event
was the AGB's audio then video request" CORROBORATED. INIT-002 vs 003A:
same CONTROL state, opposite device-register state, opposite outcome →
the INIT-002 blocker was the device register, not PI INTMR
(CORROBORATED). UNKNOWNS: U-GBP-004 fourth observation (not "enable");
U-GBP-007 updated; U-GBP-014 first timing point (0x0400 at 50–105 ms
after A2, 0x0100 within ≈1 ms); U-GBP-015/021 fourth byte-0 extra pattern
(0x04 / 0x20 / 0x24); U-GBP-022 partially answered (latched + W1C FACT;
device line level/pulse and W1C-while-asserted open); U-GBP-023 CLOSED
(0x8AAE idle again after the power cycle); U-GBP-024 partially answered;
U-GBP-025 pattern `offset2 = lo | (hi & 0x05)` in all six states, group 0
of 0x0500 excepted (pattern only, no meaning). REGISTERS.md §4/§5,
HSP.md §2 and INITIALIZATION.md §11 carry the promoted statuses; the
Dolphin model's assertion condition (`irq & 0x8000`) is now contradicted
by hardware (cause with bit 15 = 0). HARDWARE_TESTS.md: 003A moved to
"Executed tests" with the verbatim log.

**Next experiment (analysis only; GBP-INIT-003B not implemented).**
Options compared for the first delivery of a real HSP cause to the CPU:

- A) runtime order (unmask before waiting, as both references do): closest
  to the references and measures source-to-delivery latency, but delivery
  and device programming become simultaneous new variables, the handler
  would run inside the experimental region, and the storm bound rests on
  the one-shot handler alone.
- B) unmask only after a latched cause: reproduce 003A exactly (PI masked)
  until INTSR bit 13 = 1 is observed (a state now known: source 0x0400
  pending on the device, cause latched at the PI, INTMR closed), with the
  one-shot handler installed before any experimental write (R1); then
  `__UnmaskIrq` and measure whether IRQ 26 is delivered at once (latency
  in ticks from the unmask); the handler masks first, records time base
  and INTSR/INTMR, writes `INTSR := 0x2000` and re-reads INTSR (R3/R8) —
  that re-read is the level/pulse discriminator of U-GBP-022 because the
  device source is still pending; then the main loop, masked again,
  reads the device register, acknowledges it with `read | 0x8000` (GBI's
  form, already physically exercised), observes INTSR again, and runs the
  Disc stop word and the full teardown. One new variable (delivery) on a
  physically reproduced state; clean causality; no reference order
  broken that matters for safety; bounded by the same 2000 ms window plus
  a short delivery bound.
- C) faithful GBI reproduction (KEYPAD in the same 64-byte write, CONTROL
  `(v & ~0x18) | 0x0C`, thread-based service, `IRQ := 0` per pass,
  AUDIO/VIDEO reads): the eventual runtime, but four or more new
  variables at once (KEYPAD, CONTROL 0x08, continuous service, block
  reads) — rejected as the next step.

Recommendation: **B**, as GBP-INIT-003B, designed and audited like 003A
(PI masked until the cause is latched, handler pre-installed and audited
by `isr_audit`, one unmask, self-masking one-shot handler, INTSR re-read
after the W1C while the device still asserts, main-loop device
acknowledge `read | 0x8000`, stop word, teardown, power cycle). A later
run in order A measures source-to-delivery latency once B has shown that
a latched cause is delivered and how the W1C behaves. No implementation
until authorized.

**Roadmap / governing docs.** `docs/ROADMAP.md` Phase 8 was rewritten by
the user by hand ("Physical Link Port compatibility regression": the
port itself and every normal use of it — Link Cable multiplayer,
official and third-party accessories, the physical Mobile Adapter GB,
PicoAdapterGB as one test case; the virtual Mobile Adapter over the BBA
additive) and is preserved verbatim. CLAUDE.md §2/§3/§4 and README.md
were synchronized to the same wording: physical Link Port compatibility
is the requirement, PicoAdapterGB one concrete regression fixture, the
physical Mobile Adapter GB a normal accessory that must keep working, the
virtual one an additive extension.

**Tests executed.** C: 9 + 17 + 24 + 143 + 342 + 315 + 586 + 2195 = 3631
checks, 0 failures (the 003A suite grew from 1951 by the physical replay
and the phase-flag scenarios). Python: 102 passed (6 new fixture tests).
No GameCube build was run: the executed DOL is the artifact under test
and no new experimental DOL is produced by this consolidation.

**Follow-up (separate, not done here).** Harden the POC Makefiles' dirty
check (`git update-index -q --refresh` before `git diff-index --quiet
HEAD --`), found during the release audit; it does not touch the
identity of the executed build `d956b1b`.

**Newly confirmed behavior.** See "Evidence promoted". **Rejected
hypotheses.** Bit 15 as a W1C pending summary. **New unknowns.** None
opened; U-GBP-022 narrowed, U-GBP-023 closed, U-GBP-024 narrowed.
**Next highest-value experiment.** GBP-INIT-003B, option B above,
pending authorization.

---

## 2026-09-15 — GBP-INIT-003B designed (delivery of a latched HSP cause to the CPU); analysis only

**Goal.** Specify the first controlled delivery of a real HSP cause to a
CPU handler as IRQ 26, on top of the physically executed GBP-INIT-003A.
No code, no build, no hardware, no request, no commit. Full
specification: HARDWARE_TESTS.md "Planned tests — GBP-INIT-003B".

**Decisions.**
- Handler installation point: **B** — reproduce 003A verbatim with PI
  masked until INTSR bit 13 = 1 is observed (the EVENT), then
  `IRQ_Request(26, oneshot)`, then a PREUNMASK snapshot and its
  preconditions, then one `__UnmaskIrq(IM_PI_HSP)`. Checked against
  libogc2 (`external/libogc2/libogc/irq.c`, ENV-IRQ-002): `IRQ_Request`
  only swaps the handler-table entry under `_CPU_ISR_Disable`, so
  installing while a cause is latched and masked changes nothing;
  `__UnmaskIrq` rebuilds INTMR under `_CPU_ISR_Disable` and restores EE
  at its end, so a latched `cause & mask` is taken as an exception before
  the call returns (t_unmask must be read before the call; t_post_unmask
  may already be after the handler). Options A (install before the
  CONTROL write, INIT-002 order) and C (install before A2) are safe but
  add nothing and change the 003A replica; rejected.
- Preconditions immediately before the unmask (after the install): INTSR
  bit 13 = 1, INTMR bit 13 = 0, handler installed with count 0, CONTROL
  vote = 0x8C, IRQ readings equal with at least one even source bit
  (0x0555) set, odd bits and bit 15 = 0 as A2 wrote them; otherwise
  `abort_pre_unmask_state`, no unmask.
- ISR: the audited one-shot of INIT-002 extended by an INTMR read
  between the mask and the W1C, and a second INTSR/INTMR read after a
  fixed ≈100-tick time-base loop; MASK → W1C order kept; exactly one W1C
  per run; a second entry re-masks, records, does not acknowledge.
- Level/pulse discriminator: the ISR's W1C happens while the device
  source is still pending (no device acknowledge before the main loop):
  bit 13 clear at `intsr_after_w1c`, `intsr_second` and PREACK →
  compatible with a pulse/edge-latched cause (not a proof of pulse); bit
  13 set again before the device ACK → strong evidence of a level line.
- PI W1C budget: ISR exactly 1; main loop at most 1, at the first point
  where bit 13 reads 1 while masked (after the device ACK, else at
  CLEANUPCHK); never repeated; sticky recorded; maximum 2 per run.
- Order: ISR → PREACK → device ACK `read | 0x8000` under CONTROL 0x8C →
  POSTACK → (main W1C) → CONTROL restore → Disc stop word → cleanup
  policy → handler restore → mask verified → AR_INFO → FINAL. Both
  references acknowledge under the running CONTROL and restore CONTROL
  only at stop; the ACK value is A1's physically validated form.
- Against GBI: PI-first handler order kept; one-shot mask-first instead
  of an open INTMR; no thread, no KEYPAD, no AUDIO/VIDEO/SIO reads, no
  `IRQ := 0` re-enable; stop right after. Against the Disc: its
  device-first handler write would blur the discriminator, so GBI's order
  stays for the handler and the Disc's word for the stop; no Disc element
  adds safety.
- T_DELIVERY 100 ms (software margin; a latched cause should be delivered
  inside `__UnmaskIrq`); timeout → `__MaskIrq`, PI read, status
  `delivery_timeout` (or `abort_unmask` if INTMR bit 13 never rose), no
  device-ACK step (the stop word acknowledges), teardown. No cause within
  2000 ms → `no_cause_within_tmax`, no unmask. Neither is a transport
  error. Handler install failure → no unmask. `count > 1` →
  `anomaly_reentry`, teardown, power cycle, no repeat before analysis.
- Writes: A1, A2, device ACK (fired path), stop — four IRQ-register
  write sites; INTMR only via `__UnmaskIrq` (once) / `__MaskIrq`; INTSR
  W1C ISR 1 + main ≤ 1; never KEYPAD/VIDEO/AUDIO/SIO/BBA. Power cycle
  mandatory after any experimental write.

**Validation criteria (fixed in advance).** Delivery validated iff fired
= 1, count = 1, small bounded latency, INTMR bit 13 = 1 at entry and 0
after the mask, INTSR bit 13 = 1 at entry, one ISR W1C, INTMR bit 13 = 0
in every later main read, device ACK completed with a consistent
read-back, handler restored, restore = ok. Level/pulse readings are
observations. Still missing afterwards: repeated service, KEYPAD, CONTROL
0x04/0x08 at runtime, AUDIO/VIDEO DMA, runtime-order unmask latency,
cartridge present, sleep/serial sources.

**Files the future implementation would touch (listed, not done).**
`src/gbp/gbp_irq_oneshot.h` (extended body and record), `src/gbp/
gbp_transport.h` (`gbp_irq_record` fields; replay `I u` extended
backward-compatibly), `src/platform/hsp_backend_irq.c` (record copy),
new `src/gbp/gbp_initirqb_probe.{h,c}` (the 003A stages reused through
`gbp_regwrite`/`gbp_rawlog`/`gbp_detect`, delivery stage added; 003A's
tested module left untouched), new `poc/gbp-init-irq-deliver-probe/`
(Test ID GBP-INIT-003B, Build ID initirqb-0001, gecko prefix
OPENGBP-INITIRQB, links `hsp_backend_irq.c`), `tests/mocks/gbp_mock.{c,h}`
(delivery on unmask with a latched cause is already modeled by
`irq_step`; add the re-latch-while-source-pending knob and main W1C
accounting), new `tests/unit/test_gbp_initirqb.c` + `tests/unit/Makefile`
(scenarios: pulse, level re-latch, delivery timeout, unmask ineffective,
no cause, install failure, pre-unmask state lost, reentry, ACK failures,
W1C budget, teardown, order/never assertions; the physical 003A fixture
as prefix up to the EVENT), `tests/host/test_artifacts.py`,
`tools/isr_audit.py` (accept the fixed-count time-base loop and the extra
PI reads; still only `__MaskIrq` callable), `tools/poc_audit.py` (a 003B
profile: `hsp_backend_irq.o` allowed, one `__UnmaskIrq` call site, four
IRQ write sites, no INTMR store), `tools/probelog.py` (new records →
replay lines), root `Makefile` (`initirqb-dolphin`, `initirqb-audit`,
POCS), docs (this planned entry → implemented, DEVLOG, INITIALIZATION §9
rule refinement, POC README).

**Roadmap / governing docs.** `docs/ROADMAP.md` Phase 8 (physical Link
Port compatibility as the permanent requirement, PicoAdapterGB one
fixture, the virtual Mobile Adapter additive) untouched; CLAUDE.md and
README as synchronized in the previous entry. The Makefile dirty-check
hardening stays a separate follow-up.

**Next.** Await authorization to implement GBP-INIT-003B as specified.

## 2026-09-15 — GBP-INIT-003B implemented (dirty build initirqb-0001); NOT physically executed

**Goal.** Implement the delivery experiment exactly as specified
(HARDWARE_TESTS.md "Planned tests — GBP-INIT-003B"), reusing the
physically executed 003A code path, with every property provable on the
host and on the final objects. No hardware, no request, no commit, no
push: the result is a dirty build for review; a checkpoint commit and a
clean audit precede any physical candidate.

**Changes.**
- `src/gbp/gbp_initirqa_probe.{h,c}`: the executed module split into
  stages without behavior change — `gbp_initirqa_run_cause()` (everything
  up to the EVENT / end of the window), `gbp_initirqa_teardown()` with
  options (PI-cleanup budget, a hook before the AR_INFO restore), shared
  snapshot helpers (optional second PI sample logged as `PI tag=<id>b`),
  `gbp_initirqa_probe_run()` = the two in sequence. Its 2195 checks and
  the physical initirqa-0001 replay are byte-for-byte unchanged.
- `src/gbp/gbp_irq_oneshot.h`: `gbp_irq_oneshot_service_ext()` — t_entry,
  INTSR, INTMR, count++, `__MaskIrq`, INTMR, INTSR, exactly one
  `INTSR := 0x2000`, INTSR, a bounded ≈100-tick time-base wait (also
  capped at 4096 reads), t_second, INTSR, INTMR, fired; a second entry
  re-masks, records `reentry_t/intsr/intmr`, never acknowledges. The
  GBP-INIT-002 body is untouched. `struct gbp_irq_record` gained
  `intsr_before_w1c`, `t_second`, `intsr_second`, `intmr_second`,
  `reentry_t` (appended; the replay `I u` line takes them as five
  optional numbers, 002 fixtures unchanged).
- `src/platform/hsp_backend_irq.{h,c}`: `hsp_backend_irq_transport_ext()`
  registers `hsp_backend_oneshot_isr_ext`; the record copy covers the new
  fields; the direct INTMR store of GBP-INIT-001 moved to the new
  `hsp_backend_intmr.{h,c}` (linked by `poc/gbp-init-probe` only), so the
  interrupt-path object contains no INTMR store at all.
- New `src/gbp/gbp_initirqb_probe.{h,c}`: 003A stage → `CAUSE` → point-B
  install (`IRQ_Request`, previous handler kept) → the install must leave
  a clean record → PREUNMASK (two PI samples, CONTROL, IRQ) with the
  preconditions → t_unmask, one `__UnmaskIrq`, t_post_unmask → wait on the
  record only (T_DELIVERY 100 ms operational) → `__MaskIrq` + REMASKCHK
  (+ one retry) → record copied and formatted → PREACK → device ACK
  `read | 0x8000` through `gbp_regwrite_irq_u16` (attempted before the
  call, completed on rc ok; skipped if the read failed or the readings
  disagree) → POSTACK → at most one main-loop W1C (POSTACK, else
  CLEANUPCHK via the 003A budget; sticky recorded) → the 003A teardown
  with the handler restore + mask verification hooked before AR_INFO →
  `INITIRQB end`, `ACKS`, `RESTOREB`. Statuses: `ok_delivery_observed`,
  `delivery_timeout`, `no_cause_within_tmax`, the 003A aborts by their
  own names, `abort_handler_install`, `abort_pre_unmask_state`,
  `abort_unmask`, `anomaly_reentry`, `anomaly_mask_failure`.
  `power_cycle_required` is never cleared. No formatting in the ISR; the
  003A no-formatting window kept (`REGION formatted_inside=0`).
- New POC `poc/gbp-init-irq-deliver-probe/` (Test ID GBP-INIT-003B,
  Build ID initirqb-0001, gecko prefix OPENGBP-INITIRQB, 224-line ring,
  POWER CYCLE REQUIRED banner, X save / START exit; links
  `hsp_backend_irq.c`, not `hsp_backend_intmr.c`). Root `Makefile`:
  `initirqb-dolphin`, `initirqb-audit`, POCS, `all`.
- Mock (`tests/mocks/gbp_mock.{c,h}`): the extended body runs inside the
  delivery engine with a moving time base; synthetic re-latch after a W1C
  while the source is pending (`pi_relatch_after_ticks`), delivery
  suppression, install-time state changes (cause lost, INTMR bit 13 set,
  CONTROL changed, IRQ changed, readings disagreeing, dirty record),
  handler W1C counter. Replay: `I u` extended.
- Tools: `tools/probelog.py` (003B record names, HANDLERPI2 → five extra
  `I u` numbers, `MAINPICLEANUP performed=1` → `P a`, record kinds may
  carry a digit — HANDLERPI2, A1/A2, P0CHK were silently dropped before);
  `tools/isr_audit.py` (exactly one INTSR store of 0x2000 after
  `__MaskIrq`, no INTMR store, loops allowed, instruction count, store
  offsets reported); `tools/poc_audit.py` (`--profile 003a|003b`: required
  / forbidden objects, exact call-site tables for `__UnmaskIrq` /
  `IRQ_Request` / `__MaskIrq`, INTSR store sites per function, main.o
  rules). **Audit defect found and fixed:** the register tracker of both
  tools was a linear scan; the extended handler keeps the PI base in a
  callee-saved register, and the early-return epilogue of its reentry
  path (`lwz r30,24(r1)`) sits before the first-entry path in the
  listing, so the tracker forgot the base and reported *zero* INTSR
  stores — the same blindness could have hidden an INTMR store. Replaced
  by a forward data-flow pass over each function's control-flow graph
  (`track_registers`: branch targets merge by agreement, loops iterate to
  a fixpoint, calls clobber the volatile GPRs, relocated immediates are
  unknown); negative controls added on synthetic listings and on the
  real 001/002 objects.
- Tests: new `tests/unit/test_gbp_initirqb.c` (1031 checks), new
  `tests/host/test_initirqb_replay.py`, extended `test_isr_audit.py`,
  `test_poc_audit.py`, `test_probelog.py`, `test_artifacts.py`,
  `tests/unit/Makefile`. Docs: this entry, HARDWARE_TESTS.md (003B entry
  → implemented, precisions listed), INITIALIZATION.md §11, UNKNOWNS.md
  U-GBP-022 pointer, tools/tests/captures READMEs, the POC README.

**Tests executed (this build).** C: 9 binaries, all green (003A 2195,
003B 1031 checks; the physical fixtures init-0001 ×2, initirq-0001,
initirqa-0001, probe-0001 ×2 replayed). Python: 124 passed, 0 skipped
(artifacts of all six POCs, both audits on the built objects, negative
controls, synthetic 003A and 003B round trips, the physical 003A fixture
through the 003B probe → `abort_handler_install / irq_ops_unavailable`,
every fixture line consumed). `make initirqb-audit`: isr_audit CLEAN for
`hsp_backend_oneshot_isr_ext` (82 instructions, INTSR store at 0xb8 =
0x2000 after `__MaskIrq`, INTMR stores 0) and `hsp_backend_oneshot_isr`
(70, store at 0x68); poc_audit profile 003b 0 findings (`__UnmaskIrq`:
`h_irq_unmask`=1; `IRQ_Request`: `h_irq_install`=1, `h_irq_restore`=1;
`__MaskIrq`: `h_irq_mask`=1 + both handlers; INTSR stores exactly
`h_write_intsr`, the two handlers; INTMR stores 0; IRQ write sites 3 + 1
= 4; `main.o` references `hsp_backend_irq_transport_ext` and
`gbp_initirqb_probe_run` only). `make initirqa-audit` / `initirq-audit`
still clean on the rebuilt 003A / 002 objects. Dolphin (OSD disabled by
the runner on every run, verified in the 11 reports): 003B absent →
`abort_inconsistent`, GBPlayer model → `abort_control_shape`, both with
`written=0 irq_attempted=0 handler=0 unmasked=0 fired=0`; the nine
previous runs (smoke, probe ×2, init ×2, initirq ×2, initirqa ×2) PASS.

**Result.** GBP-INIT-003B IMPLEMENTED — NOT PHYSICALLY EXECUTED. DIRTY
BUILD — NOT A PHYSICAL CANDIDATE: DOL sha256
`ee34d93ad2774a9365fa9afd8485558f78e2f53df939b35ee1a84220f581df80`,
383232 bytes, commit `fa6f35e-dirty`, devkitPPC GCC 16.1.0, libogc2
r2442.094b250. Identity anomaly recorded: `build/poc/smoke-test/build-info.txt`
still says `commit=d956b1b` (clean) because that POC was not rebuilt —
the commit id is baked at link time and is not a make dependency; the
Makefile `-dirty`/identity hardening stays the separate follow-up
already planned.

**Newly confirmed behavior.** None on hardware. Static, on the linked
binary: the extended handler's instruction order is the designed one
(t_entry → INTSR → INTMR → count++ → `__MaskIrq` → INTMR → INTSR → one
W1C → INTSR → bounded wait → t_second → INTSR → INTMR → fired; the
reentry path masks, records, returns without a W1C).

**Rejected hypotheses / new unknowns.** None; the level/pulse question
(U-GBP-022) stays open until the physical run.

**Next.** User checkpoint (commit of the reviewed tree) → clean rebuild
→ clean audit (Max) → recorded hash → only then the physical request per
the procedure in `poc/gbp-init-irq-deliver-probe/README.md`. No hardware
request from this dirty build.

## 2026-09-15 — GBP-INIT-003B release audit on the clean build d3da8cd: PHYSICAL CANDIDATE READY

**Goal.** Decide whether the checkpoint `d3da8cd` ("probe: add controlled
GBP IRQ delivery experiment") could be declared a physical candidate.
Analysis only; no code change; no hardware.

**Done.** Clean tree verified; `make clean` and a full Docker rebuild of
the six POCs (every build-info `commit=d3da8cd`, none `-dirty`; a forced
recompile reproduced every DOL byte for byte with 0 warnings). Identity
of the candidate: `gbp-init-irq-deliver-probe.dol`, 383200 bytes, entry
0x80003100, 1 text + 1 data section, 32-byte aligned, devkitPPC GCC
16.1.0, libogc2 r2442.094b250, sha256
`821aa2b2893b6d66fd1398eaeb7de7c475862728e55dc0922d74042d0e9cb757`
(build-info and `sha256sum` agree). C suite 4662 checks in 9 binaries
(003A 2195, 003B 1031), Python 124 passed / 0 skipped, `isr_audit` CLEAN
for both handlers (ext 82 instructions, one INTSR store of 0x2000 at
offset 0xb8 after `__MaskIrq`, no INTMR store), `poc_audit --profile
003b` 0 findings, physical 003A fixture replayed through both probes
(step 85, 0 mismatches, 0 exhausted), 11 Dolphin runs PASS with the OSD
override in every command and 0 yellow pixels in every screenshot. On
the linked binary: exception vector `ori r3,r3,48` / `mtsrr1` / `rfi`
(EE stays 0), `irq_exceptionhandler` sets only MSR_RI, `c_irqdispatcher`
has no `mtmsr` and dispatches by `bctr`, `__MaskIrq` restores the saved
EE (0) — nothing can nest before the handler's mask; the reentry path of
the extended handler (0x8000a80c…0x8000a844) never reaches the W1C store
(0x8000a868, reachability computed on the control-flow graph);
`__UnmaskIrq` is called by our code only from `h_irq_unmask`; the only
INTMR stores in the whole ELF are libogc2's own; the record's `fired`
is the last store of both handler paths; worst-case log lines 221 of 255
usable. The audit also found that the versioned 001 fixture lacks the
seven `T` lines the current `probelog` emits — a difference that
predates this work (the previous checkpoint's tool produces the same
output), not a reinterpretation. **Decision:** PHYSICAL CANDIDATE READY
for the DOL built from `d3da8cd`; the run was then authorized and
executed once (next entry).

## 2026-09-15 — GBP-INIT-003B executed: first physical delivery of an HSP cause to the CPU as IRQ 26; sustained-level model rejected; `pi_policy` label defect; next experiment analyzed

**Goal.** Consolidate the first physical run of GBP-INIT-003B (build
initirqb-0001, commit d3da8cd, DOL sha256 `821aa2b2…b757`). No new
hardware run, no new DOL, no next experiment, no commit.

**Preservation.** Raw log `logs/GBP-INIT-003B_initirqb-0001.log`, 17471
bytes, sha256 `bedb1f013176fec1b3de7c63c4147dfa6770f1eae8c9ec29ee82b027f9d7cf7c`
(computed directly from `logs/`, matches the expected values), untouched;
byte-identical copy in `captures/local/`; verbatim in HARDWARE_TESTS.md.
Fixture `captures/fixtures/hw-gamecube-gbp-2026-09-15-initirqb-0001.gbpreplay`
generated by `tools/probelog.py` from the preserved copy with the
physical metadata header: 111 operations (25 time-base reads, 25 PI reads,
41 block reads, 10 block writes, the INTSR poll that saw bit 13, 5
AR_INFO operations, and the interrupt path as it happened — `I i null`,
`I u` with the fourteen numbers of the physical handler record, `I m`,
`I r`); raw[32] verbatim; replays end to end through
`test_gbp_initirqb --replay` with step 111, 0 mismatches, 0 exhausted, 0
tick polls, and the summary equals the run's. Every earlier fixture is
untouched.

**Result.** `status=ok_delivery_observed restore=ok`; `fired=1 count=1
reentry=0`; `ack=1/1 ack_value=8500 irq_pending=0500`; `isr_pi_w1c=1
main_pi_w1c=0`; handler installed and restored (`old_handler=null`),
`mask_ok=1`; `uncertain=0`, 0 errors, 0 timeouts, 0 busy, 0 dropped, 0
truncated; `power_cycle_required=1` (console power-cycled). The 003A part
reproduced: BASE CONTROL 0x90 / IRQ 0x8AAE, A1 0x8AAE → 0x8AAA, A2 0x0000
(held ≥ 50 ms), EVENT 105.286 ms after A2 (003A: 105.273 ms) with INTSR
`0x00012000`, INTMR `0x000001FA`, CONTROL 0x8C, IRQ 0x0400; the second
source 0x0100 appeared between the EVENT and PREUNMASK (≤ 907.6 µs).
PREUNMASK: INTSR bit 13 = 1,1; INTMR bit 13 = 0,0; CONTROL 0x8C; IRQ 0x0500
(sources 0x0500, odd bits 0, bit 15 0); record 0/0 — a clean physical
baseline immediately before the first IRQ 26 delivery of the project.

**Newly confirmed behavior (FACT, hardware, restricted to bit 13 / this
libogc2 build).**
- **CPU delivery (GBP-HW-037, GBP-PI-005, ENV-IRQ-003):** after
  `__UnmaskIrq(IM_PI_HSP)` the handler ran inside the call (t_unmask
  3679931504 < t_entry 3679931582 < t_post 3679931761; the read after
  the call already showed the handler's effects). At entry INTSR
  `0x00012000`, INTMR `0x000021FA` (bit 13 = 1); after `__MaskIrq` INTMR
  `0x000001FA`. One entry, no reentry. The statement promoted: *a PI HSP
  cause previously latched with INTMR bit 13 = 0 was delivered to the
  IRQ 26 handler after `__UnmaskIrq`; the handler observed INTMR bit 13 =
  1 and masked it again.* Not generalized to other PI interrupts.
- **Latency (one observation, no specification):** 78 ticks / 40.5 MHz =
  1.926 µs from the time-base read before the call to the handler's
  first time-base read; `t_post − t_unmask` = 257 ticks (6.35 µs) — the
  ISR ran within the call, confirming the hypothesis used by the release
  audit (t_post is not a lower bound of anything).
- **PI W1C inside the ISR (GBP-HW-038):** INTSR before the W1C
  `0x00012000`, write `0x2000`, after `0x00010000`; second read 148 ticks
  (3.654 µs) after the entry `0x00010000` / INTMR `0x000001FA`. The W1C
  inside the ISR cleared the latched PI cause.
- **Level / re-assert — the critical result (GBP-HW-038, U-GBP-022):**
  PREACK 7277 ticks (179.68 µs) after the entry: INTSR bit 13 = 0 in both
  samples, INTMR bit 13 = 0, CONTROL 0x8C, IRQ 0x0500 — both sources
  still pending, odd bits 0, bit 15 = 0, the state that had raised the
  cause — and PI bit 13 did not re-assert; still 0 at POSTACK (323.9 µs
  after the entry). The simple sustained-level model is **REJECTED** for
  these conditions. Pulse, edge/event assertion, transient line and a
  deassert mechanism separate from the source latch remain admissible;
  "HSP is pulse" is **not** promoted to FACT.
- **Device sources stayed pending through the ISR (GBP-HW-038):** PREACK
  IRQ 0x0500 — no incidental acknowledge by the handler; the
  discriminator above was observed with the sources pending.
- **Device ACK (GBP-HW-039):** `0x0500 | 0x8000 = 0x8500` written (u16
  replicated); POSTACK 25 µs later IRQ 0x8000: 0x0100 and 0x0400 cleared
  (W1C, third observation for these bits), bit 15 read 1, odd bits 0;
  INTSR bit 13 = 0 in both samples; no main-loop W1C — the only PI W1C of
  the run was the ISR's.
- **Sources re-set before the stop (GBP-HW-040):** after CONTROL 0x8C →
  0x90, IRQSTOPPRE read 0x8500 (both sources set again ≤ 143 µs after the
  ACK) and no PI cause followed. CONTROL had already been restored, so
  this interval does not isolate bit 15: recorded only as "sources
  reasserted after the ACK and before the stop, under the teardown
  state". Stop `0x8500 | 0x8AAA = 0x8FAA` → read back 0x8AAA (second
  physical validation of the Disc's stop word).
- **Teardown (GBP-HW-041):** CONTROL restore ok; STOP ok; CLEANUP not
  needed (INTSR bit 13 already 0); handler restore ok (old NULL); INTMR
  final `0x000001FA`; AR_INFO 0x005B → 0x0043; FINAL under code 0:
  CONTROL 00, IRQ 9090; `restore=ok`. No byte-0 extra anywhere in this
  run (U-GBP-020/021); the offset-2 pattern of U-GBP-025 broke in the
  0x8500 read and in group 0 of the PREUNMASK 0x0500 read.

**Model update (GBP-IRQ-008; INITIALIZATION.md §12, REGISTERS.md §4,
HSP.md §2).** Physically established: 0x0004 source W1C; 0x0100 source
W1C, dispatched as VIDEO by the drivers; 0x0400 source W1C, dispatched as
AUDIO by the drivers; odd bits level-written, polarity 1 = masked / 0 =
enabled CORROBORATED; 0x8000 level-written and persistent both ways (A2
wrote 0 and read 0; the ACK wrote 1 and POSTACK read 1), exact global
function still HYPOTHESIS — IRQSTOPPRE 0x8500 is not used alone to
conclude anything about bit 15 because CONTROL had been restored. One
service cycle (ISR mask → PI W1C → device ACK → stop) FACT; re-arm and
repeated service never exercised (U-GBP-027).

**Logging defect (build initirqb-0001) and its correction for future
builds.** Record `000113 TEARDOWN start … pi_policy=never_unmasked` was
printed by the shared teardown of `gbp_initirqa_probe.c` (line 365), which
hard-coded the 003A policy label; the same log proves `unmasked=1
masked_again=1` and a real delivery. The label is not evidence; the
primary records are. Fix (future builds only): `struct
gbp_initirqa_teardown_opts` gained `pi_policy` (NULL keeps
`never_unmasked`, the 003A probe's own policy), the teardown prints it,
and the 003B probe passes `unmasked_once` when it unmasked and
`never_unmasked` otherwise. Regression tests: the 003B mock scenarios
assert the label per path (delivered / timeout → `unmasked_once`; no
cause / install failure → `never_unmasked`), the 003A test asserts its
default, the physical 003B fixture test asserts that the corrected probe
prints `unmasked_once` on the physical replay, and
`tests/host/test_hw_fixture.py` pins the raw log's defective label next
to its `RESTOREB unmasked=1 masked_again=1` record. The physical log and
the fixture are kept as written; the fixture header documents the
discrepancy. Builds after d3da8cd differ from the executed binary by this
label only (no rebuild was made in this consolidation). Also noted: the
record's `irq_attempted=3` (A1, A2, ACK) precedes the stop word; the final
`WRITES` counts 4/4 — expected, not an inconsistency.

**Tests executed.** C: 9 binaries, all green — test_ident 9, test_ringlog
17, test_gbp_detect 24, test_gbp_probe 143, test_gbp_replay 342,
test_gbp_init 315, test_gbp_init_irq 586, test_gbp_initirqa 2196,
test_gbp_initirqb 1107 (the physical 003B fixture: 76 checks on the exact
physical values and records) — total 4739. Python: 132 passed, 0 skipped
(new: the 003B fixture class in test_hw_fixture.py — header, regeneration
from the raw log, interrupt path as it happened, writes/polls, IRQ reads
verbatim, timeline, offset-2 exceptions; the end-to-end physical replay in
test_initirqb_replay.py). Every earlier physical fixture replays
unchanged. No Docker build, no Dolphin run (no binary changed for
hardware).

**Initialization readiness (Phase 3).** Physically established, each on
this console: presence detection (six runs), AR_INFO handling, CONTROL
transform and restore, source acknowledge by W1C (three bits, several
times), local mask programming (level writes both ways), a real HSP
cause produced twice at ≈105.28 ms, PI capture while masked, CPU IRQ 26
delivery, handler entry with the delivered state, ISR mask-first, PI W1C
inside the ISR with the device still asserting its sources, no reentry,
device source ACK, the Start-up Disc stop word (twice), handler
restoration, full teardown. **Assessment:** the fundamental
initialization and interrupt mechanics of the GBP path are now
established well enough to build a functional layer on them; what is
missing is not mechanics but the steady state — repeated service and the
re-arm write (`IRQ := 0` after the ACK; never done), KEYPAD (never
written), CONTROL runtime bits 0x04/0x08 (U-GBP-006), AUDIO/VIDEO block
reads (Phases 4/6), the serial and sleep sources, a cartridge present.
Phase 3's acceptance ("reliably detects and initializes") is not yet
claimable in the sense of a runtime that stays initialized: that needs
the repeated-service loop. No move to the next layer without an explicit
authorization.

**Next step (comparison, recommendation only — nothing implemented).**
- A) One more full IRQ cycle (ACK → `IRQ := 0` → next cause → second
  delivery): answers U-GBP-027 (1)(2), measures one request interval,
  isolates bit 15 as a by-product; small, but a microprobe that would be
  repeated by B anyway.
- B) A bounded GBI-like service loop: the 003B cycle as the first
  iteration, then re-arm (`IRQ := 0`), unmask again, service up to N
  causes or T ms with the audited mask-first handler generalized to
  re-armable (still: mask in the ISR, one W1C per entry, ACK and re-arm
  in the main loop, unmask after the re-arm), per-cause timestamps,
  sources, ACK values, lost-cause detection, stop word at the end, no
  KEYPAD, no AUDIO/VIDEO DMA. Answers everything A answers plus the
  cadence and jitter of the audio/video requests (U-GBP-014/024/027) and
  whether the handler sustains repeated delivery — the first functional
  layer, with one variable group (repetition) added to a validated cycle.
- C) KEYPAD / CONTROL runtime: needed for Phase 5 and for U-GBP-006, not
  for the interrupt mechanics; its first write would add a new register
  to an experiment that has no visible effect without a cartridge.
- D) VIDEO read path now: premature — video blocks arrive with each
  0x0100 request, so a service loop (B) must exist first; reading the
  VIDEO block is also the first DMA read of a data block, a separate
  variable.
- E) Nothing better in the references: both drivers proceed from this
  point to the service loop (GBI's `IRQ := 0` re-arm and wait; the Disc's
  callback dispatch), then to the data blocks.
**Recommendation: B, bounded, with A as its first cycle** — designed and
audited like 003A/003B (host mocks with a synthetic request cadence,
storm/loss invariants, the physical 003B fixture as the prefix up to the
first ACK, static audits of the handler and objects, clean candidate).
Not implemented; awaiting authorization.

**Requirements preserved.** Physical Link Port compatibility (Link Cable
multiplayer, official and third-party accessories, the physical Mobile
Adapter GB, PicoAdapterGB as one fixture) remains the permanent
requirement of `docs/ROADMAP.md` Phase 8; the virtual Mobile Adapter over
the BBA remains additive; parity with the Start-up Disc and GBI remains
the compatibility goal. Nothing in this run touched the Link Port (empty
throughout).

**Docs updated.** HARDWARE_TESTS.md (executed entry with the verbatim
log; planned entry marked executed), EVIDENCE.md (GBP-HW-035…041,
GBP-PI-005, ENV-IRQ-003, GBP-IRQ-008), UNKNOWNS.md (U-GBP-007, 014, 020,
021, 022 → P2, 024, 025; new U-GBP-027), INITIALIZATION.md §11 pointer
and new §12, REGISTERS.md §4/§5, HSP.md §2/§4, captures/README.md,
tests/README.md, the POC README. Git: nothing committed; the tree carries
the consolidation for the user's checkpoint.

## 2026-09-15 — GBP-INIT-004 designed (bounded repeated service: ACK → local re-arm → next cause → next delivery); analysis only

**Goal.** Specify the first steady-state experiment of Phase 3 on top of
the physically validated single cycle of GBP-INIT-003B. No code, no
build, no hardware, no request, no commit. Full specification:
HARDWARE_TESTS.md "Planned tests — GBP-INIT-004".

**Reference loops re-read from the binaries (Ghidra headless,
`build/analysis/`, not committed).** GBI thread `0x8000bf30`: after
`LWP_SemWait` (posted by the raw handler `0x8000b400`, whose only action
is `INTSR := 0x2000`) it reads IRQ, dispatches the ARQ reads (0x0400
AUDIO, 0x0100 VIDEO, 0x0040 SIODATA) and the sleep KEYPAD write (0x0010),
writes one 64-byte DMA at CFFFE0 = KEYPAD := pad state + IRQ := read |
0x8000 (the ACK), reads CONTROL+SIOCTL at 4FFFE0, optionally writes
SIODATA, writes CONTROL+SIOCTL back with the values read, does its video
bookkeeping, and **ends every pass with `IRQ := 0` (32 × 00 at D00000)**
before waiting again; the mask stays open; no second PI W1C; CONTROL is
written back unchanged every pass; KEYPAD every pass. Start-up Disc
handler `0x8008af08`: `IRQ := shadowB | 0x8000` → `INTSR := 0x2000` →
read IRQ → write back `pending` (ACK) → KEYPAD → callbacks → `IRQ :=
shadowB` (re-arm, bit 15 := 0; skipped when a callback signals a full
ring). Both references clear PI before the re-arm, set bit 15 = 1 while
servicing and 0 while waiting, and wait with INTMR bit 13 open.

**Decisions.**
- Cycle = ISR (mask → one PI W1C) → main re-mask → PREACK → ACK `read |
  0x8000` (one per cycle) → POSTACK as a clean boundary (ACK completed,
  readings agree, CONTROL 0x8C, INTMR bit 13 = 0, no reentry, mask
  confirmed, the acknowledged AV source bits gone — as 003B's 0x0500 →
  0x8500 → 0x8000; sources still set → anomaly_source_not_cleared, no
  REARM) → PI clean (≤ 1 main W1C only if bit 13 reads 1, one re-read;
  still 1 → anomaly_pi_sticky_after_ack, no REARM) → REARM `IRQ := 0`
  (GBI's write, u16 replicated, byte-identical to A2, its own record
  kind, t_rearm read before it) → REARMPOST (CONTROL 0x8C, INTMR bit 13
  = 0, odd bits 0, bit 15 0 required; source bits not required to be 0;
  outcomes A–E, E = anomaly_rearm_state) → masked wait for the next
  cause → PREUNMASK → unmask → ISR. Causal boundary: delivery → ACK →
  POSTACK clean → PI clear → t_rearm → IRQ := 0 | new source / PI →
  t_next_cause → next cycle; a cause is credited to a re-arm only when
  everything before the bar was established and t_next_cause > t_rearm.
  Option A of the ordering question (PI clear guaranteed before the
  re-arm), matching both references' principle; the Disc's hold-first
  entry write is not reproduced.
- Sources policy, AV-only continuation: AV_SOURCE_MASK = 0x0500 (0x0100,
  0x0400 or both, any order). At every service read after A2 or a REARM,
  `unexpected = irq & (0x0555 & ~0x0500)` ≠ 0 → anomaly_unexpected_source
  (reason unexpected_source_cycle_N): raw[32] and the snapshot preserved,
  the source recorded, no unmask if that cycle was not delivered yet, no
  REARM if it was seen after a delivery, safe teardown. Not a transport
  failure, not an "invalid" source — valid hardware outside this POC's
  scope (game pak, sleep, serial, user are not implemented). The
  initialization state is exempt: BASE 0x8AAE with the idle bit 2, A1 =
  read | 0x8000, A2 = 0 stay the physically validated path.
- MAX_CYCLES = 3 delivered causes, REARMS = 2 (none after cycle 3, so
  the run ends in 003B's validated state). Cycle 1 is the 003B path
  verbatim; the new variables (REARM, masked wait, next cause) enter
  only after the first ACK.
- One handler install for the run (option A); the audited extended
  one-shot body kept byte-for-byte per slot, wrapped by a generation
  selector. Generation semantics: cycles 0…MAX_CYCLES−1; slots write-once,
  zeroed at the install, never reused or cleared; `expected_gen`
  published by the main loop only while INTMR bit 13 = 0 and never
  changed while IRQ 26 could enter; the ISR reads it once at entry and
  uses only that slot; out of range → generation_error (anomaly_reentry
  class); a fired slot re-entered → the body's no-W1C reentry branch →
  anomaly_reentry; `completed_cycles` is a count, and the next
  `expected_gen` (= that count) is published only after the cycle was
  consumed by the main loop, with the CPU still masked, POSTACK passed,
  PI clear, REARM executed and validated; `entries_total` reports only.
- CPU masked between cycles (unmask only with a latched cause, as 003B);
  documented as a difference from the runtime, which waits unmasked.
- Per-unmask preconditions (cycles 2/3) = 003B's plus: the cause later
  than the corresponding t_rearm; source within AV_SOURCE_MASK and ≠ 0
  (any order), nothing outside it; odd bits 0, bit 15 0; the cycle's
  record clean; expected_gen correct. CONTROL must read 0x8C at every
  snapshot (never rewritten inside the run); KEYPAD/AV/SIO not touched
  (accepted deviation from the references).
- PI W1C budget per cycle: ISR 1, main ≤ 1 at POSTACK, none at
  REARMPOST (a bit 13 there is the next cause), teardown ≤ 1; maximum 7.
- Timeouts: T_CAUSE_FIRST 2000 ms, T_DELIVERY 100 ms per cycle,
  T_NEXT_CAUSE 500 ms per re-arm (operational). Statuses per cycle:
  ok_cycles_completed, no_initial_cause, no_next_cause, delivery_timeout,
  abort_unmask, abort_pre_unmask_state (+ generation_mismatch /
  cause_before_rearm), anomaly_unexpected_source, anomaly_reentry (+
  generation_error), anomaly_mask_failure, anomaly_source_not_cleared,
  anomaly_pi_sticky_after_ack, anomaly_rearm_state,
  anomaly_control_changed, abort_transport (ack/rearm write failures);
  none of the anomalies is a transport failure.
- Teardown from every state S0–S5 (no cause, delivered-not-acked,
  acked-not-rearmed, and after a REARM: (a) IRQ still 0 and no cause →
  STOP := 0 | 0x8AAA = 0x8AAA; (b) a new source appeared but no unmask →
  STOP := read | 0x8AAA acknowledges and closes it, then ≤ 1 PI W1C;
  (c) invalid REARM state → best-effort STOP with the current readback,
  no second re-arm; and all cycles done): CPU masked first, CONTROL
  restore, the STOP word, CLEANUPCHK ≤ 1 W1C, handler restore, MASKCHK,
  AR_INFO, FINAL. No ACK loop, one ACK per cycle.
- New measurement: t_next_cause − t_rearm per cycle (immediate = bit 15
  held the line; one request period = event-driven), plus cause-to-cause
  intervals — individual observations, no statistics. Bit 15 is observed
  as a by-product under a constant CONTROL 0x8C (the isolation U-GBP-007
  lacked); no isolated bit-15 write.
- The second ≈100-tick ISR read stays (audited object unchanged).

**Success criterion.** `ok_cycles_completed` = 3 valid deliveries; 2
complete boundaries ACK → POSTACK sources cleared → PI clear → REARM
validated; 2 subsequent causes attributable in time to their REARM and
delivered; zero unexpected sources, zero reentry, zero sticky PI, zero
transport uncertainty; CONTROL 0x8C throughout the cycles; final restore
ok — a causal criterion, stronger than a count of three.

**Phase-3 closure and Phase 4.** If 004 validates under that criterion,
the fundamental initialization/IRQ mechanics of Phase 3 are closed and
Phase 4 (VIDEO) starts on the 004 service loop with the VIDEO block read
as the next variable. Not blockers: bit 15's exact function, the line's
nature (P2), byte-0/offset-2 patterns, KEYPAD, CONTROL 0x04/0x08, AUDIO,
SIO, cartridge. A `no_next_cause` in cycle 2/3 would itself be decisive
for Phase 4's design (the stream needs consumption).

**Implementation impact (listed, not done).** Extract the 003B cycle
service (PREUNMASK check, unmask/wait/remask/record copy, PREACK/ACK/
POSTACK, main W1C) from `gbp_initirqb_probe.c` into a small internal
module (`src/gbp/gbp_irq_service.{h,c}`) reused by 003B (behavior
pinned by its physical fixture) and by the new `gbp_initirq4_probe.{h,c}`;
`gbp_irq_oneshot.h` gains a multicycle wrapper around the unchanged
extended body; `gbp_transport.h` two optional ops (`irq_prepare(gen)`,
`irq_record_slot(slot)`); `hsp_backend_irq.c` a records array, the
multicycle handler and its constructor; mock (records array, generation,
cause-after-rearm knobs, sticky-after-ACK, control change); replay `I p
<gen>`; probelog (PREPARE record, per-cycle `I u`); isr_audit on the new
symbol; poc_audit profile `004` (5 IRQ write sites, 4 INTSR store
functions); new POC `poc/gbp-init-irq-service-probe/` (Test ID
GBP-INIT-004, Build ID initsvc-0001, gecko prefix OPENGBP-INITSVC); root
Makefile targets; tests (≥ 40 mock scenarios, S0–S5 teardowns, the
physical 003B fixture as the prefix up to its POSTACK); docs.

**Requirements preserved.** Start-up Disc / GBI parity as the
compatibility goal; physical Link Port compatibility (Link Cable
multiplayer, official and third-party accessories, the physical Mobile
Adapter GB, PicoAdapterGB as one fixture) permanent; rumble and GBP-aware
game features; the virtual Mobile Adapter over the BBA additive. None of
them touched by this experiment.

**Next.** Await authorization to implement GBP-INIT-004 as specified.

---

## 2026-09-15 — GBP-INIT-004 implemented (dirty build initirq4-0001); NOT physically executed

**Goal.** Implement the bounded repeated-service experiment exactly as
specified (HARDWARE_TESTS.md "Planned tests — GBP-INIT-004"), reusing
the physically executed 003A stage and the physically executed 003B cycle
without a third copy of the sequence, with every property provable on the
host, on the replay of the physical fixtures and on the final objects.
No hardware, no request, no commit, no push: the result is a DIRTY BUILD
for review; a user checkpoint, a clean rebuild and a release-candidate
audit precede any physical candidate.

**Changes.**
- New `src/gbp/gbp_irq_service.{h,c}`: the 003B cycle service extracted
  verbatim from `gbp_initirqb_probe.c` — `gbp_irq_service_preunmask_check`
  / `_log_preunmask`, `gbp_irq_service_deliver` (UNMASKPRE, one unmask,
  UNMASKPOST, the record-only wait, the main re-mask with one retry, the
  record copy while masked, HANDLER/HANDLERPI/HANDLERPI2/DELIVERY),
  `gbp_irq_service_ack` (PREACK, `read | ack_or` through
  `gbp_regwrite_irq_u16`, POSTACK, the cycle's single main W1C; new
  optional `require_control` precondition for 004: CONTROL == 0x8C in
  both readings and INTMR bit 13 = 0 at PREACK, else skip reasons
  `control_changed` / `intmr13_set`), `gbp_irq_service_teardown_hook`.
  Two decorations (` n=N` after the record kind, `-N` on the tags) are
  empty for 003B. `gbp_initirqb_probe.{h,c}` now embed
  `struct gbp_irq_handler_state h`, `struct gbp_irq_delivery d`,
  `struct gbp_irq_ack k` and call the service. Equivalence proof: the
  physical initirqb-0001 fixture replays through the refactored probe
  with an identical summary, 111 steps, 0 mismatches, 137 log lines,
  and the `--dump-log` output of the synthetic scenario is byte-identical
  to the HEAD build's (diffed); the 1107 checks are unchanged.
- `src/gbp/gbp_transport.h`: `struct gbp_irq_multi` (expected_gen,
  entries_total, generation_errors, `slots[GBP_IRQ_MULTI_SLOTS = 3]`,
  `anomaly`), `struct gbp_irq_multi_status`, three optional operations
  `irq_prepare(gen)`, `irq_record_slot(slot)`, `irq_multi_status`,
  `gbp_transport_has_irq_multi_path()`.
- `src/gbp/gbp_irq_oneshot.h`: `gbp_irq_multicycle_service()` — reads
  `expected_gen` once, `entries_total++`, bounds check before any pointer
  arithmetic (out of range → `generation_errors++`, the poisoned
  `anomaly` slot), then ONE call of the unchanged 003B extended body. The
  002 and 003B bodies are untouched.
- New `src/platform/hsp_backend_irq_multi.{h,c}`: one static
  `struct gbp_irq_multi`, `hsp_backend_oneshot_isr_multi`, install (slots
  zeroed, `anomaly.count = 1`, `expected_gen = 0`, `IRQ_Request` with the
  previous handler kept), restore (exactly the previous handler),
  `__MaskIrq` / `__UnmaskIrq` primitives, prepare (rejects gen ≥ 3),
  slot copy, status copy; `hsp_backend_irq_transport_multi()`. The 002/003B
  object `hsp_backend_irq.c` is untouched and NOT linked by the 004 POC.
- New `src/gbp/gbp_initirq4_probe.{h,c}` (per the specification): 003A
  stage → `CAUSE n=0` → install once → per cycle PREPARE (INTMR bit 13 = 0
  by the last PI read, slot n clean, `expected_gen == n`, `entries_total ==
  deliveries`) → PREUNMASK-n (003B checks + AV source pending, no source
  outside AV, cause after the previous re-arm) → service deliver (slot n)
  → fired / reentry / generation / mask checks → service ack (AV only,
  source required, CONTROL required) → POSTACK clean boundary (`irq &
  0x0555 == 0`, CONTROL 0x8C, INTMR 13 = 0, Disc = GBI) → PICLEAN (after at
  most the cycle's one main W1C) → `completed_cycles++` → cycles 0/1:
  `t_rearm`, `IRQ := 0x0000` (attempted/completed), REARMPOST-n (A/B/C/D/
  E/F, never a W1C) → NEXTCAUSE-n (INTSR polled masked ≤ 500 ms, one
  snapshot at the poll's time base, AV validated) → cycle n+1; after cycle
  2 no re-arm. Every path ends in the 003A teardown with the 003B hook,
  labelled `TEARDOWN4 variant=`. Status `ok_cycles_completed` only under
  the causal criterion of the design; `cycles_completed_with_errors` when
  the cycles completed but restore / transport / uncertainty / CONTROL did
  not hold; `abort_read_inconsistent` for Disc ≠ GBI at a per-cycle read;
  every per-cycle reason carries `_cycle_N`. CONTROL is never rewritten
  per cycle (intentional difference from GBI). Records: `CYCLE n= start`,
  `PREPARE`, `PREUNMASK4`, `HANDLER4`, `PICLEAN`, `BOUNDARY`, `REARM`,
  `REARMPOST`, `NEXTCAUSE`, `TEARDOWN4`, `CYCLES`, `CYCLE n= end` (×3),
  `TIMING n=` (individual deltas, no statistics), `MULTI`, `RESTORE4`;
  nothing formatted in the handler, between an unmask and its re-mask, or
  per poll. W1C budget by control flow: handler 1 per delivery, main ≤ 1
  per cycle (POSTACK), none at REARMPOST, teardown ≤ 1 (max 7).
- `src/gbp/gbp_initirqa_probe.{h,c}`: `gbp_initirqa_snapshot_take_at()`
  (a snapshot stamped with the poll's own time base, logged as an EVENT-
  style snapshot) — the NEXTCAUSE snapshot; nothing else changed.
- Mock (`tests/mocks/gbp_mock.{h,c}`): `isr_multi` (deliveries run the
  multi-cycle body on `multi`), `MOCK_IRQ_PREPARE` op and the violation
  `PREPARE_WHILE_UNMASKED`, `src_sched[8]` (sources after the Nth IRQ
  write), `source_pi_delay` (PI latch lagging the source),
  `ack_ignored_at_write`, `rearm_sticky_bits` (+ `_from_write`),
  `force_expected_gen` (+ `force_gen_at_unmask`), `second_delivery_at`,
  `control_change_after_irq_write`, `mask_ignored_from_call`,
  `suppress_delivery_at`, `source_clear_at_delivery`,
  `irq_disagree_from_write`, the three multi operations. Everything
  SYNTHETIC; the 003A/003B suites are unchanged (2196 / 1107).
- Replay (`src/gbp/gbp_replay.{h,c}`): optional `I p <gen>` (consumed
  only when next; old fixtures never carry one), per-generation `I u`
  records, `irq_record_slot`, `irq_multi_status`; exposed with the
  interrupt path. `tools/probelog.py`: `PREPARE gen=` → `I p`, `REARM
  t_rearm=` → `T`, `NEXTCAUSE found=0 t_end=` → `T`; the per-cycle 003B
  records follow the existing rules (the handler-record search already
  stops at the next UNMASK). Old physical fixtures regenerate unchanged.
- Audits: `tools/poc_audit.py` profile `004` (`hsp_backend_irq_multi.o`
  required, `hsp_backend_irq.o` / `hsp_backend_intmr.o` / 001/002/003B
  probes forbidden, `__UnmaskIrq` from `hm_irq_unmask` only,
  `IRQ_Request` from `hm_irq_install` / `hm_irq_restore` only,
  `__MaskIrq` from `hm_irq_mask` and the handler — two sites there, see
  below — INTMR stores 0, INTSR stores exactly `h_write_intsr` + the
  handler, `gbp_regwrite_irq_u16` 3 + 1 + 1 logical sites, `main.o`
  uses the multi constructor); profile `003b` follows the moved ACK site
  (`gbp_irq_service.o`). `isr_audit` on `hsp_backend_oneshot_isr_multi`.
- New POC `poc/gbp-init-irq-service-probe/` (Test ID `GBP-INIT-004`, Build
  ID `initirq4-0001`, prefix `OPENGBP-INITIRQ4`, 320-line ring, the
  power-cycle banner also on a completed run, "NOT A PHYSICAL CANDIDATE"
  on screen); the 003B POC links `gbp_irq_service.c`. Root Makefile:
  POCS, `initirq4-dolphin`, `initirq4-audit`, `all`, help.
- Tests: `tests/unit/test_gbp_initirq4.c` (3210 checks, 17 groups: the
  §42 scenarios, the §43 event-order proofs, the "never" properties, the
  physical 003A fixture up to the EVENT, the physical 003B fixture cut
  before its CONTROL restore as the prefix of cycle 0 — exhausted at
  REARM-0, 0 mismatches — `--dump-log` / `--replay` modes marked
  SYNTHETIC); `tests/host/test_initirq4_replay.py` (round trip with and
  without the `I p` lines, both physical fixtures); `test_probelog.py`,
  `test_poc_audit.py` (profile 004 + negative controls, 003B layout),
  `test_isr_audit.py`, `test_artifacts.py` (004 identity; the 003B
  strings now carry the empty cycle field). READMEs of poc / tests /
  tools / captures; HARDWARE_TESTS, INITIALIZATION, UNKNOWNS pointers.

**Tests executed (this build).** C: 10 binaries, all green (7949
checks: 003A 2196, 003B 1107 with its physical fixture, 004 3210).
Python: 145 passed, 0 failed. `make build` (Docker, all seven POCs,
0 warnings), `make inspect` (every DOL 32-byte aligned, entry
0x80003100). Audits: `initirq-audit`, `initirqa-audit`, `initirqb-audit`
(profile 003b, 0 findings with the moved ACK site) and `initirq4-audit`:
`isr_audit` CLEAN on `hsp_backend_oneshot_isr_multi` — 107 instructions,
calls `__MaskIrq` twice, one INTSR store of 0x2000 at 0x11c after both,
no INTMR store — and `poc_audit --profile 004` 0 findings. Manual
inspection of the multi-cycle handler listing: `expected_gen` loaded once
(`lwz r31,0(r9)`), `entries_total++`, `cmplwi r31,2 / bgt` BEFORE the slot
arithmetic (`mulli r31,r31,56 / addi 12 / add`), no other index use; the
out-of-range path increments `generation_errors` and selects `&anomaly`
(offset 180 = 12 + 3 × 56); GCC duplicated the entry sequence (mftb, INTSR
and INTMR loads, count++, `bl __MaskIrq`) into both paths, each of which
masks before any store; the reentry path (count ≠ 1) stores
reentry_t/intsr/intmr and `fired` and returns without touching INTSR; the
first-entry path stores t_entry, the entry reads, INTMR-after-mask,
INTSR-before-W1C, the single `stw 0(r30)` of 0x2000, INTSR-after, the
bounded wait (ctr 2048 × 2 reads = the 4096 guard, 100-tick bound),
t_second, the second reads, `fired` last; no `mtmsr`, no indirect branch,
only loads at INTMR. Dolphin: 13 runs PASS (11 previous + the two 004
runs: `abort_inconsistent` without an HSP device, `abort_control_shape`
with the GBPlayer model — no write, no install, no unmask), every command
carrying `Dolphin.Interface.OnScreenDisplayMessages=False`; every
captured render window is a grayscale PNG (ImageMagick writes colour type
0 only when no pixel has colour — the OSD text is yellow), i.e. 0 yellow
pixels in all 13 screenshots. Synthetic 004 round trip: mock summary ==
replay summary, 182 steps, 0 mismatches, 0 unmatched polls. Physical
fixtures: 003A through the 004 probe (every line consumed, `irq_multi_ops_
unavailable`, the 003A teardown), 003B prefix (cycle 0 reproduces the
003B values: t_unmask 3679931504, latency 78 ticks, ACK 0x8500 → 0x8000,
POSTACK PI clear; then `abort_transport rearm_write_failed_cycle_0` with
`completed_cycles = 1`, `rearms 0/1`: the script is exhausted only after
the last recorded operation, the re-arm write is answered "unavailable" —
the physical prefix ends before the first re-arm variable, `attempted = 1`
is a synthetic boundary and never evidence of a re-arm). The first cycle
of 004 is **semantically equivalent to 003B at the protocol level** (the
same device transactions in the same order up to the POSTACK), NOT a
byte-identical handler: the multi-cycle body loads the generation, checks
the bounds, selects the slot and counts the entry before the entry
timestamp (107 instructions against 82); the main loop adds the PREPARE
publication and two bookkeeping copies (no device access) before
PREUNMASK, the AV rule at PREUNMASK/PREACK/POSTACK and the CONTROL/INTMR
precondition at PREACK. The static audit proves the 5 logical
`gbp_regwrite_irq_u16` call sites; the 8 executions of a complete run (A1,
A2, ACK ×3, REARM ×2, STOP) are proven by the unit tests' operation trace
and by the `WRITES irq_attempted=8` record, never by the audit.
Worst-case line widths (10-digit ticks, longest status / reason /
restore reason / variant) < 255 in every scenario; ring overflow and a
wrapping time base across the cycles handled.

**Result.** GBP-INIT-004 IMPLEMENTED — NOT PHYSICALLY EXECUTED. DIRTY
BUILD — NOT A PHYSICAL CANDIDATE: `gbp-init-irq-service-probe.dol`, Test
ID GBP-INIT-004, Build ID initirq4-0001, commit `23990c9-dirty` (base HEAD
`23990c9`, `git describe` `23990c9-dirty` — the dirty marker is correct,
no identity anomaly), 397280 bytes, entry 0x80003100, text 0x04A400 at
0x80003100 + data 0x016AE0 at 0x8004D500 (bss 277496 bytes), 32-byte
aligned, devkitPPC GCC 16.1.0, libogc2 r2442.094b250, sha256
`da19add0add883cf79c03bc1310b48adcac193cb3109f58cc025f39959ca0ef4`.
Rebuilt 003B binaries (commit `23990c9-dirty`, sha256 `402faf67…afa4`)
are not the executed `d3da8cd` binary and are not candidates either.
Phase 3 is not concluded; the mock is never evidence; no hardware run is
requested.

**Newly confirmed behavior.** None on hardware. Static, on the linked
binary: the multi-cycle handler keeps the 003B invariants (mask first,
exactly one INTSR store, no INTMR store, `fired` last) and adds the
generation bounds check before any slot access.

**Rejected hypotheses / new unknowns.** None; U-GBP-027 (repeated
service after the re-arm) stays open until the physical run.

**Requirements preserved.** Start-up Disc / GBI parity as the
compatibility goal; physical Link Port compatibility (Link Cable
multiplayer, official and third-party accessories, the physical Mobile
Adapter GB, PicoAdapterGB as one fixture) permanent; rumble and the
GBP-aware game features; the virtual Mobile Adapter over the BBA
additive. Nothing of them touched.

**Next.** User checkpoint (commit of the reviewed tree) → Ultracode →
Max → clean rebuild → release-candidate audit → only then a possible
hardware authorization of GBP-INIT-004. Not requested here.

---

## 2026-09-16 — GBP-INIT-004 release audit on the clean build 741630b: PHYSICAL CANDIDATE READY

**Goal.** Decide whether the checkpoint `741630b` ("probe: add bounded GBP
IRQ service experiment", parent `23990c9`, 41 files) could become the
physical candidate. Mode: audit only; no hardware, no commit.

**Done.** Clean tree verified; `make clean` and a full Docker rebuild of
the seven POCs twice: 0 warnings, every identity `741630b` (no `-dirty`),
21 artefacts (dol / elf / unpadded dol) hash-identical between the two
builds, the 004 DOL byte-identical; `make inspect` 7/7 aligned, entry
0x80003100. Regression on the final artefacts: C 10 binaries 7983 checks
(003A 2196, 003B 1107 with its physical fixture replayed at 111 ops / 0
mismatches / 0 exhausted, 004 3244), Python 145 passed, synthetic round
trips 004 (182 ops) and 003B (109 ops) with identical summaries, physical
003A through the 004 probe (85 ops, stops at the install), physical 003B
prefix through the 004 probe (95 ops consumed, exhausted at REARM-0, 0
mismatches, `rearms 0/1` documented as a synthetic boundary), `isr_audit`
CLEAN on the three handlers (multi-cycle: 107 instructions, one INTSR
store of 0x2000 at 0x11c after both mask calls, no INTMR store),
`poc_audit` 0 findings on the 003a / 003b / 004 profiles (004: 5 logical
IRQ-write sites), 13 Dolphin runs PASS with the OSD override and grayscale
captures. On the clean objects: `hm_irq_install` zeroes the slots and
poisons `anomaly.count = 1` before `IRQ_Request`; `hm_irq_prepare` bounds-
checks and stores once; the probe publishes the generation before the
PREUNMASK reads and the unmask (call order in the object); the handler
loads `expected_gen` once (0x10), bounds-checks (0x1c/0x40) before the slot
arithmetic (0x44–0x4c), masks before any PI store, stores `fired` last
(0x198); CFG enumeration: every path executes exactly one `__MaskIrq` and
at most one W1C (the out-of-range path reaches the W1C only with
`anomaly.count == 0`, excluded by the install poison — the only writers are
the install and the handler's increment; the symbol is local to its
object); libogc2: the exception stub sets IR/DR only, `irq_exceptionhandler`
sets RI only, `c_irqdispatcher` has no `mtmsr`, `__MaskIrq` restores the
saved EE bit. The ISR auditor's coverage was measured by mutation
(catches: missing / extra / wrong-value / pre-mask INTSR store, INTMR
store, no mask, indirect branch, foreign call; does not check: per-path
mask count, re-routed W1C, single generation load, bounds-before-index,
`fired` order — covered by CFG / manual reading).

**Result.** PHYSICAL CANDIDATE READY: Test ID GBP-INIT-004, Build ID
initirq4-0001, commit 741630b, DOL
`build/poc/gbp-init-irq-service-probe/gbp-init-irq-service-probe.dol`,
397280 bytes, entry 0x80003100, text 0x04A400 @ 0x80003100, data 0x016AE0 @
0x8004D500, bss 277512, devkitPPC GCC 16.1.0, libogc2 r2442.094b250, sha256
`1da0d7b4f47200e914aba46510921b4a49a9bb8f01fd40940ebf50bd94ad010c`
(different from the dirty `da19add0…0ef4`). Expected writes of a
successful physical run: AR_INFO exp + restore, TEST handshake, CONTROL
EXP + restore, IRQ A1 ×1 / A2 ×1 / ACK ×3 / REARM ×2 / STOP ×1 = 8, PI W1C
3 (ISR) + ≤ 3 (main) + ≤ 1 (teardown), INTMR only through the mask APIs,
handler install 1 / restore 1, power cycle mandatory. Recorded after the
fact (the audit itself modified no tracked file).

---

## 2026-09-16 — GBP-INIT-004 executed: second CPU delivery through the multi-cycle handler, ACK, 0x0400 present under bit 15 = 1 at POSTACK; the clean boundary stopped the run before any re-arm; premise re-examined; GBP-INIT-004B designed

**Goal.** Consolidate the single physical run of GBP-INIT-004 (build
initirq4-0001, commit 741630b, DOL `1da0d7b4…010c`), preserve the raw
evidence, decide what the run does and does not establish, re-read the
reference service loops on the point the run raised, and design the next
step. No implementation, no DOL, no hardware, no request, no commit.

**Preservation.** Raw log `logs/GBP-INIT-004_initirq4-0001.log`, 19247
bytes, sha256 `c9167224cb57f1c0df4858fbb147bbe0f1cd1f544b04a71a594786f4f2ee775b`
(computed from `logs/`, matching the announced values), untouched; copy
`captures/local/GBP-INIT-004_initirq4-0001.log` (byte-identical); fixture
`captures/fixtures/hw-gamecube-gbp-2026-09-16-initirq4-0001.gbpreplay`
(metadata header with build / commit / DOL and log hashes; raw blocks
verbatim, never normalized; the interrupt path as it happened: `I i null`,
`I p 0`, `I u` with the physical multi-cycle handler record, `I m`, `I r`;
no `P a`; the four IRQ-register writes — A1, A2, ACK, STOP — and no re-arm).
Replay through the 004 probe: 112 operations, 0 mismatches, 0 exhausted, 0
unmatched polls, the physical result reproduced (`anomaly_source_not_cleared`
/ `source_pending_after_ack_cycle_0`, `restore=ok`, 149 log lines); the
fixture regenerates from the raw log with `tools/probelog.py` (152 records,
53 record kinds incl. the digit-suffixed ones). Log verbatim in
HARDWARE_TESTS.md "Executed tests — GBP-INIT-004"; evidence GBP-HW-042…047,
GBP-IRQ-009; unknowns U-GBP-007/014/021/022/027 refined, U-GBP-028 opened;
INITIALIZATION.md §13; REGISTERS.md / HSP.md notes; POC README result.
**GBP-INIT-004 — PHYSICALLY EXECUTED 2026-09-16.**

**Integrity.** `dropped=0 truncated=0 errors=0 transport_ok=1 uncertain=0
timeouts=0 busy=0 power_cycle_required=1`, 51 transfers; counters
`requested=3 completed=0 causes=1 deliveries=1 acks=1 rearms=0
next_causes=0 reentry=0 unexpected=0 isr_w1c=1 main_w1c=0 teardown_w1c=0`.
`completed=0` is correct: `completed_cycles` counts a cycle only after its
clean boundary (ACK → POSTACK with the acknowledged sources gone → PI
clean); one delivery and one ACK occurred, the boundary did not. **No
re-arm was executed** (`rearm_attempted=0 rearm_completed=0`). The
experiment did not fail technically: its conservative clean boundary
prevented the re-arm.

**Result, step by step.** A1 `0x8AAE → 0x8AAA`; A2 `0x0000`
(`t_after=1048847666`); first cause at `t_event=1053111645`, **4263979
ticks = 105.283 ms** after A2 (one more point of the initial cadence: 003A
105.273, 003B 105.286); EVENT INTSR13=1, INTMR13=0, CONTROL 0x8C, IRQ
0x0400; PREUNMASK-0 (971.8 µs later) IRQ 0x0500. **Cycle 0 delivery:**
`t_unmask=1053156576`, `t_entry=1053156665` — **89 ticks ≈ 2.198 µs**;
`fired=1 count=1 reentry=0`; INTSR at entry `0x00012000`, INTMR at entry
`0x000021FA`, INTMR after the mask `0x000001FA`, INTSR before the W1C
`0x00012000`, after it `0x00010000`; second sample 142 ticks ≈ 3.506 µs
later, INTSR13 still 0; generation 0, `entries_total=1`, no generation
error. This physically confirms the 003B mechanism through the multi-cycle
handler — an additional confirmation, not a new independent discovery.
**PREACK-0:** IRQ 0x0500 (VIDEO 0x0100 + AUDIO 0x0400), INTSR13=0,
INTMR13=0, CONTROL 0x8C; no incidental acknowledge by the ISR. **ACK-0:**
`0x0500 | 0x8000 = 0x8500`, rc ok, attempted / completed correct — not a
transport failure. **POSTACK-0 (the central new result):** ACK
`t_after=1053170192`, snapshot `1053171245`: **1053 ticks = 26.000 µs**;
IRQ `0x8400`, INTSR13=0 in both samples, INTMR13=0, CONTROL 0x8C. At that
instant bit 15 = 1, source 0x0400 present, source 0x0100 absent, the PI HSP
latch clear, CONTROL still in the running state. Promoted as a restricted
FACT (GBP-HW-045): *a source 0x0400 can be present in the IRQ register with
CONTROL 0x8C and bit 15 = 1 while PI INTSR13 stays 0.* Not concluded: that
bit 15 is definitively a global interrupt hold.

**Not "ACK failed".** The POC's operational status is
`anomaly_source_not_cleared`, but the evidence does not distinguish (A)
0x0400 never cleared by the ACK's W1C from (B) 0x0400 cleared and
re-asserted within the 26 µs before the sample; the transport and the
write succeeded and bit 8 was cleared by the same write. Recorded as
U-GBP-028, explicitly not blocking.

**Comparison with 003B.** 003B: PREACK 0x0500, ACK 0x8500, POSTACK
≈25.1 µs later 0x8000; the sources reappeared before the stop (≈+168 µs)
but CONTROL had already been restored to 0x90. 004: PREACK 0x0500, ACK
0x8500, POSTACK 26.0 µs later **0x8400 with CONTROL still 0x8C**. The
CONTROL change 0x8C → 0x90 is therefore not a necessary condition for the
later presence of the source. No periodicity is concluded from two runs;
0x0100, present at 003B's IRQSTOPPRE, was absent in 004 at +26 µs and at
IRQSTOPPRE (≈+195 µs).

**Bit 15 (U-GBP-007), refined with caution.** The state IRQ 0x8400 /
CONTROL 0x8C / PI INTSR13=0 was observed and persisted; no PI cause was
captured from the handler's W1C to FINAL (≥ 0.76 ms; no main W1C, bit 13 is
latched). Source status can coexist with bit 15 = 1 without an HSP latch
in that window. Compatible hypotheses, none promoted to FACT: bit 15 acts
as a hold / gate of the external request; source status and request
generation have separate logic; another re-request condition (a new event,
the drain) had not occurred. Rejected in the observed conditions: "source
present implies HSP immediately latched".

**Byte 0 / raw variability (U-GBP-021).** Extras this run: TEST `C7 C3…`,
CONTROL 0x8C `AC 8C…` (all thirteen reads), IRQ 0x8AAE `8E 8A AE AE…`,
0x8AAA `8E 8A AA AA…`, PREUNMASK-0 `8D 05 04 00…`, PREACK-0 `85 05 04 00…`;
none on 0x0400, 0x8400, 0x9090, CONTROL 0x90/0x00. Disc / GBI semantics
agreed, vote == byte 0x1F, detection PRESENT: byte 0 is not a reliable
source for semantic decisions; the extra-free 003B run does not change
that. Offset-2 pattern (U-GBP-025): broken only in group 0 of the two
0x0500 reads (`04`).

**Teardown.** `variant=S3_cycle_aborted`: CONTROL 0x8C → 0x90 ok;
IRQSTOPPRE 0x8400; STOP `0x8400 | 0x8AAA = 0x8EAA`, readback 0x8AAA (a
third physically validated stop combination); PI cleanup not needed;
handler restored; INTMR13=0; AR_INFO 0x005B → 0x0043; FINAL CONTROL 00 /
IRQ 9090; `restore=ok`.

**The 004 did not test the re-arm — explicit.** `REARM attempted=0
completed=0`. This run provides no physical evidence about `IRQ := 0`
after the ACK, nor about ACK → re-arm → next HSP. Mock / synthetic replays
are not evidence. **U-GBP-027 remains open.**

**The clean-source premise re-evaluated against the binaries (decompiles
under `build/analysis/ghidra/`, re-read 2026-09-16).**
- *GBI thread `0x8000bf30`*: after `LWP_SemWait` it reads IRQ
  (`0x80011c14(0xD00000, 0x20)`); for 0x0400 / 0x0100 / 0x0040 it posts
  asynchronous ARQ reads of AUDIO 0x1000 at `0x800000`, VIDEO 0xF00 at
  `0x100000`, SIODATA (`0x8000be48` → `ARQ_PostRequestAsync`, priority 1);
  then the 64-byte KEYPAD + `IRQ := read | 0x8000` write at `0xCFFFE0`
  (`0x8000bea4` → `ARQ_PostRequest`, priority 1, **synchronous**: it waits
  for its own completion, and the queue is FIFO per priority, so the block
  reads complete before the ACK write does); CONTROL/SIOCTL read; optional
  SIODATA write; CONTROL/SIOCTL write-back; finally `IRQ := 0`
  (`0x80015da0(buf, 0)`, `0x8000bea4(0xD00000, buf, 0x20)`), the last device
  access of the pass. Bit 15 is 1 from the ACK write to the re-arm. The
  register is never read after the ACK.
- *Start-up Disc handler `0x8008af08`*: `IRQ := shadowB | 0x8000` (bit 15
  = 1 first) → `INTSR := 0x2000` → read IRQ → write the value read back
  (ACK) → KEYPAD → CONTROL read → callbacks: the audio slot (`0x8008cdc4` →
  `0x8008a764`: ring of 70 × 0x1000 buffers, DMA read from `0x800000`) and
  the video slot (`0x8008ed68` → `0x8008a480`: ring of 40 × 0xF00 buffers,
  DMA read from `0x100000`) **start the block DMA** and return non-zero,
  which suppresses the handler's final `IRQ := shadowB`; the ARAM-DMA-done
  handler `0x8008b14c` (interrupt 6, installed by the start routine) then
  runs the completion callback (`0x8008ce3c` / `0x8008edac`: invalidate the
  buffer, post it to the consumer queue) and **writes the re-arm `IRQ :=
  shadowB` (bit 15 = 0)** unless the stop flag is set. Bit 15 is 1 from
  the entry write to that DMA-done re-arm. The register is never read
  after the ACK.
- Conclusion: **both references drain the event's block(s) before their
  re-arm and neither requires the source bits to read 0** — their boundary
  is the drain, not a clean read-back. The 004 requirement "sources == 0 at
  POSTACK before REARM" was an artificial condition of a POC that drains
  nothing; the audio status read 26 µs after the ACK is what such a POC
  should expect. The premise is withdrawn for the successor.

**Three candidate designs compared.**
- *A) GBP-INIT-004B, pending-source re-arm.* After the ACK, continue if
  the CPU is masked, INTMR13=0, PI INTSR13=0, CONTROL 0x8C, Disc == GBI,
  bit 15 = 1, odd masks 0, the sources are only AV (0x0100 / 0x0400 /
  0x0500) and `unexpected == 0`; do not require `source == 0`. Then
  `t_rearm` → `IRQ := 0` → observe, CPU still masked, whether the HSP
  latches with the source pending. Question: "does clearing bit 15 /
  re-arming the block turn an already pending AV source into a new HSP
  request?" One new variable (the re-arm itself, in the state the run
  reached), no AV DMA, bounded, CPU masked while observing, the next cause
  classified `rearm_of_pending_source` (never `new_source_occurrence`).
  Outcomes distinguishable by `t_hsp − t_rearm`: microseconds (the hold
  released a pending request — then the runtime must drain before each
  re-arm or it re-interrupts at once, which is what the references do
  anyway), milliseconds (event-driven request generation, the status bit is
  only status), none within 500 ms (the request needs the drain — Phase 4
  must start with the drain). Two clean re-arms would close the
  fundamental re-arm mechanics of Phase 3.
- *B) Minimal AV drain before the ACK.* Read (and discard) the AUDIO 0x1000
  / VIDEO 0xF00 blocks of the pending sources before the ACK, as the
  references do, to try to reach `POSTACK source == 0`, then re-arm with the
  clean boundary. It represents the runtime more faithfully, but it crosses
  into Phase 4 / 6 (the block reads themselves: 128 + 120 DMAs of 32 bytes
  with the current backend, timing against the device's refill, buffer
  handling), introduces several variables at once, and still does not tell
  whether the re-arm works with a pending source — the very question A
  isolates. B is the natural *next* step after A, as the entry experiment of
  Phase 4 (VIDEO on 0x0100).
- *C) Ultra-fine POSTACK sampling.* Several reads in the first 30 µs after
  the ACK to separate "never cleared" from "cleared and re-asserted". Real
  gain: small — the references never read the register after their ACK and
  re-arm regardless, and A works with the source pending either way. Only if
  A's outcome makes the distinction decisive.

**Recommendation.** **A — GBP-INIT-004B — maximizes gain per variable:**
it reuses 004 verbatim except the POSTACK acceptance rule and the cause
classification, adds no DMA, keeps the CPU masked while the cause is
observed, tests directly the still-unknown re-arm semantics (U-GBP-027)
and clarifies bit 15 as a by-product (U-GBP-007). B is required later to
represent the runtime (the references' boundary is the drain), not to
answer the re-arm question; C only if A leaves the clear-then-reassert
question blocking. Conceptual design, safety envelope, statuses and the
success criterion: HARDWARE_TESTS.md "Planned tests — GBP-INIT-004B".

**Phase 3.** Not closed by this run. It confirmed the multi-cycle handler
(cycle 0), the ACK, the safety policy and the teardown; it did not execute
a re-arm, a next HSP cause or a second delivery. If 004B physically shows
two cycles of "ACK with PI clear → `IRQ := 0` → HSP latch → delivery"
repeatedly and safely, re-evaluate whether that suffices to close the
fundamental IRQ mechanics without an AV drain (the drain then opens Phase
4).

**Tests executed.** C: 10 binaries, all green (7983 → 8065 checks: 004
3326 with the physical 004 fixture replayed in full — 112 ops, 0
mismatches — the physical 003B prefix and the physical 003A prefix; 003A
2196, 003B 1107 unchanged). Python: 153 passed (new
`HardwareFixtureInitIrq4`: header, regeneration from the raw log, interrupt
path as it happened, writes / polls / acknowledge, IRQ and CONTROL reads
verbatim, timeline, offset-2 exceptions; `test_initirq4_replay.py`: the
physical 004 fixture to its result). No source, no DOL; the fixture and the
tests are the only new code. Requirements preserved: Start-up Disc / GBI
parity; physical Link Port compatibility (Link Cable multiplayer, official
and third-party accessories, the physical Mobile Adapter GB, PicoAdapterGB
as one fixture); rumble / GBP-aware features; the virtual Mobile Adapter
over the BBA additive — none touched.

**Next.** Design checkpoint by the user → implementation of GBP-INIT-004B
(a policy delta on the 004 probe) → dirty build for review → clean rebuild
and release audit → only then a possible authorization. Not requested here.

## 2026-09-16 — Next step after GBP-INIT-004 decided: GBP-INIT-004B deferred (optional); GBP-AV-SERVICE-001 designed as the Phase 4 entry (drained service → acknowledge → re-arm → next cause); analysis only

**Goal.** Decide the design of the first functional stage after the basic
IRQ mechanics (detection, start, register programming, cause, delivery,
mask-first service, W1C, ACK, stop — all physical FACT after 003A / 003B /
004) and record it as a specification. No code, no DOL, no hardware, no
request, no commit. Everything below comes from the decompiles under
`build/analysis/ghidra/` (re-read today: GBI `0x8000bf30`, `0x8000be48`,
`0x8000bea4`, `0x80011c14`, ARQ `0x80061a68` / `0x800617b4` / `0x80061820`
/ `0x80061b3c`; Disc `0x8008af08`, `0x8008cdc4` / `0x8008a764` /
`0x8008a654`, `0x8008ed68` / `0x8008a480`, `0x8008b14c`, `0x80089c3c`,
`0x80089cc8`, `0x80089ff4`, `0x8008a31c`), the physical results already
consolidated, and the ROADMAP.

**Decision on GBP-INIT-004B: NOT implemented — deferred as optional.**
Agreed with the reasons given for it: (a) it tests a state neither
reference enters — a re-arm `IRQ := 0` with an unconsumed block; both
drain first (INITIALIZATION.md §13); (b) a negative outcome (no cause in
500 ms) would be ambiguous between "the request needs the drain" and "the
next event had not come yet", and would not change the runtime, which
drains anyway; (c) a positive outcome would mainly characterize bit 15,
whose exact function blocks neither VIDEO nor the runtime (the references'
pattern — 1 from the ACK to the re-arm, 0 while waiting — is all that is
needed); (d) CPU delivery, ACK and teardown are already physically
validated twice. No strong reason to keep it was found: the one gain it
isolates (hold-released vs event-driven re-request with a pending block)
is not on the critical path of any phase. It stays in HARDWARE_TESTS.md
as an optional bit-15 experiment, not scheduled; U-GBP-007 / 022 / 027 /
028 point to the new probe instead. The 2026-09-16 recommendation "A =
004B" recorded in the previous entry is superseded by this decision.

**Phase 3 state — terminology chosen.** ROADMAP's Phase 3 acceptance is
"reliably detects and initializes the physical GBP"; the project's own
stricter criterion (this DEVLOG, 2026-09-15 "GBP-INIT-004 designed":
re-arm and repeated delivery) has not been met, and the references show
the re-arm is inseparable from the drain — so validating it in isolation
is not the right experiment, and validating it with the drain is a Phase 4
element. State recorded: **Phase 3 IRQ core validated; re-arm validation
carried into the Phase 4 entry (GBP-AV-SERVICE-001); Phase 3 not formally
closed.** It closes with the first physical service → re-arm → next cause.
No intermediate phase is created; the roadmap order is kept (the Phase 4
entry probe also completes a Phase 3 item, documented here as required by
CLAUDE.md §26).

**Name and scope: GBP-AV-SERVICE-001** (Test ID; Build ID `avsvc-0001`,
prefix `OPENGBP-AVSVC`, `poc/gbp-av-service-probe/`). Not GBP-VIDEO-001:
with no cartridge both AV sources are pending at the first delivery
(0x0500 in 003B and 004), and a VIDEO-only drain would leave the AUDIO
block unconsumed — precisely the pending-source re-arm of 004B. Not
GBP-SERVICE-001: only the AV sources are serviced. GBP-VIDEO-001 is
reserved for the first VIDEO-content experiment (frame structure with a
cartridge). Scope: stage A of 004 verbatim (delivery through the audited
multi-cycle handler), then one service pass with the CPU masked — read
IRQ → drain AUDIO 0x1000 then VIDEO 0xF00 (one whole-block DMA each) → ACK
`pending | 0x8000` → POSTACK (no source requirement) → re-arm `IRQ := 0` →
REARMPOST → wait for the next PI HSP cause (≤ 500 ms) → teardown. No
rendering, no playback, no loop, no KEYPAD, no SIO, no cartridge, no BBA,
no second delivery. Full specification: HARDWARE_TESTS.md "Planned tests —
GBP-AV-SERVICE-001".

**Source mapping, revalidated.** 0x0100 → VIDEO (index 0x1, 0xF00 at
base+0x100000) and 0x0400 → AUDIO (index 0x8, 0x1000 at base+0x800000)
are FACT in both reference codes (GBP-IRQ-005; GBI `& 0x400` → 0x800000 /
0x1000, `& 0x100` → 0x100000 / 0xF00). On hardware only the occurrence is
FACT: 0x0400 first, 0x0100 within 1 ms (three runs). The order of
appearance does not identify the blocks; the probe reads, per bit, the
block the references read for that bit.

**Blocks and DMA, revalidated.** Both references read each block with ONE
ARAM → main-memory DMA of the full length into a 32-byte-aligned,
cache-invalidated buffer: the Disc programs `len` (0x1000 / 0xF00) in
`0x80089c3c` and polls `0x80089cc8` with a 1 s bound; GBI posts every GBP
access at ARQ priority 1 — the hi queue, whose service `0x800617b4` starts
`AR_StartDMA` with the request's full length. The chunking (`0x80061820`,
chunk size at `r13+0x3380`) belongs to the lo queue and is never used for
GBP accesses; HSP.md §3's "GBI queues them through libogc ARQ (chunk size
0x3C0)" is therefore imprecise for the block reads and is listed for
correction with the implementation (not edited now). Consequence for
Open-GBP: a whole-block single DMA per source, never 120 / 128 separate
32-byte reads (not reference behavior; unknown device semantics). The
transfer is a read; the register programming and the polled completion
are the ones already exercised by every 32-byte access; the only new
variable class is the length. T_DMA = 200 ms per transfer stays
operational.

**GBI pass order, exact (`0x8000bf30`).** SemWait → read IRQ (voted) → set
bit 15 locally → async AUDIO read if 0x0400 → async VIDEO read if 0x0100 →
SIODATA read if 0x0040 → KEYPAD 0x0304/0x0300 if 0x0010 → one synchronous
64-byte write at 0xCFFFE0 (KEYPAD := pad, IRQ := pending | 0x8000): it is
queued in the same FIFO behind the block reads and its busy-wait returns
only after it completed, so the drains are complete before the ACK
completes → sync read CONTROL + SIOCTL → optional SIODATA write → sync
CONTROL + SIOCTL write-back → sync `IRQ := 0` → loop. PI HSP never masked;
the register never re-read after the ACK; the ACK value is the pre-service
read; bit 15 is 0 during the drain and 1 from the ACK to the re-arm.

**Disc order, exact (`0x8008af08`).** `IRQ := shadowB | 0x8000` → PI W1C →
read IRQ → write-back `IRQ := pending` (the ACK, before any drain) →
KEYPAD → CONTROL read → slot 4 (audio): synchronous DMA + polled wait when
VIDEO is pending too (`0x801b34ca[4]` = 0x0100 → `0x8008a654`), otherwise
asynchronous with a completion callback (`0x8008a764`, return 1 suppresses
the immediate re-arm) → slot 5 (video): asynchronous (`0x8008a480`,
suppress) → `IRQ := shadowB` only if nothing is in flight; otherwise the
ARAM-DMA-done handler `0x8008b14c` runs the completion callback
(invalidate + message post) and writes the re-arm. AUDIO before VIDEO;
never two block DMAs in flight; the re-arm only after the last block DMA
completed; bit 15 = 1 from the entry write to the re-arm.

**Strategy: A, GBI-like (drain → ACK → REARM).** Both references complete
the drain before the re-arm; the only difference is whether the ACK
precedes (Disc) or follows (GBI) the drain. A keeps the 004 chain ACK →
POSTACK → REARM → REARMPOST → NEXTCAUSE unchanged and inserts the drain
before the ACK; after a drain the ACK's W1C acts on consumed blocks, so the
POSTACK read (0x8000 or 0x8400) becomes a data point for U-GBP-028 at no
cost; the ACK value is the pre-drain read in both references. Recorded
deviations from GBI, all for observability or minimalism: CPU masked from
the delivery to the end; the 32-byte IRQ-only ACK of 003B/004 (not the
64-byte KEYPAD + IRQ write; KEYPAD untouched); CONTROL read, not written
back; SIOCTL / SIODATA untouched.

**AUDIO: drain without interpreting — and Phase 6.** The AUDIO block is
read to a static buffer, its CRC32, zero / distinct counts and four byte
windows are logged after the timed region, and the whole block goes to a
binary dump; nothing is decoded or played. This does not cross into Phase
6: ROADMAP's Phase 6 is the audio *path* (buffering, state transitions,
playback), whereas consuming the block the device requests is part of
servicing the interrupt in both references, in every pass, whether or not
audio is used. The evidence it produces (first raw AUDIO block, U-GBP-012)
is stored for Phase 6, not interpreted now.

**VIDEO: read to RAM, no render.** Same treatment; additionally the first
32-bit word and the result of GBI's frame-start test `(w0 & 0x80800000)
== 0x80800000` are logged as raw flags (GBI's test, not a claim). The
physical question "can the block be read repeatedly and stably under the
reference sequence" is NOT answered by one read; this probe establishes
one stable read per block under the reference sequence, and the
repeated-service experiment that follows measures stability across
services.

**Order when the source reads 0x0500.** AUDIO then VIDEO, as both
references; neither source is acknowledged before both blocks are drained
(the ACK comes after the drains); the ACK carries both source bits (the
value read before the drain). **IRQ value used for the ACK:** the
pre-service read (`pending | 0x8000`), never a re-read after the drains —
GBI's value, and the Disc's write-back of the value it read; a re-read
would be an invented step.

**PI policy during the service.** CPU masked from the ISR's mask to the
end; INTSR bit 13 observed after the ISR's W1C at PRESVC / POSTACK /
REARMPOST / NEXTCAUSE, never delivered; a relatch during the service is
recorded (`relatch=1`, a state GBI's unmasked design tolerates by
servicing again) and cleared by the one main W1C the 004 budget allows at
POSTACK; sticky → no re-arm, teardown. No W1C after the re-arm before the
cause is observed; teardown ≤ 1. The runtime will not use this policy
(GBI never masks; the Disc services inside the handler).

**REARM after the drain.** `IRQ := 0x0000` (GBI's value), CPU masked,
precondition INTSR / INTMR bit 13 = 0 on a fresh read; REARMPOST A–F as
004; NEXTCAUSE polled ≤ 500 ms with no W1C; the next cause is valid only
with INTSR bit 13 = 1, an AV source present, no unexpected source, and
t_hsp > t_rearm (wrap-safe). It is then left latched, not delivered, not
acknowledged (except by the teardown), and the run ends.

**Cycles.** One service + one re-arm + the observation of the next cause;
no second delivery. Sustained service is the next experiment.

**Success criterion, raw capture, records, teardowns, statuses.** As
specified in HARDWARE_TESTS.md: the causal chain delivery(0) < PRESVC <
AUDIOREAD < VIDEOREAD < ACK < POSTACK accepted < PI clean < REARM <
REARMPOST (A or B) < next cause (< 500 ms, t_hsp > t_rearm), with CONTROL
0x8C at every check, INTMR bit 13 = 0 in every main read, zero reentry,
transport errors 0, uncertain 0, restore ok, and both blocks preserved
(binary dump `<test_id>_<build_id>.bin` after the log; CRC32 + windows in
the log and on screen as the fallback). A `no_next_cause_after_service` is
a valid physical result and is reported as such. Teardowns S3 / S3-DMA /
S4-ACK / S3-PI / S4C / S4A / S4B, all CPU-masked first, STOP `read |
0x8AAA` best-effort, ≤ 1 teardown W1C, restores, power cycle mandatory.
`anomaly_source_not_cleared` does not exist in this design.

**Unknowns, classified for this step.** Blocking the Phase 4 entry: none.
Answered (for one cycle) by the probe if it succeeds: U-GBP-027 (1) and
(2), (4) as a by-product — Phase 3 closes; (3) cadence and (5) sustained
service stay open for the repeated-service experiment. Data point, not
closure: U-GBP-028 (POSTACK after a drain), U-GBP-007 (bit 15 = 1 from
the ACK to the re-arm, 0 after, under CONTROL 0x8C), U-GBP-022 (a latch
during the drain, the latency of the next cause), U-GBP-014 (one interval
t_hsp − t_rearm). First raw data, no interpretation: U-GBP-008 (block
layout for VIDEO / AUDIO reads), U-GBP-011, U-GBP-012. Non-blocking and
untouched: U-GBP-021 / 025 (byte 0, offset 2 — both readings avoid them),
U-GBP-006 (CONTROL bits), U-GBP-004 (AR_INFO), the SIO unknowns.

**Compatibility.** Start-up Disc / GBI parity is the target of the design
(the service pass reproduces the references' consumption-before-re-arm);
physical Link Port compatibility untouched (no SIOCTL / SIODATA / KEYPAD
access; PicoAdapterGB stays in the port as in every run); rumble /
GBP-aware features and the additive virtual Mobile Adapter unaffected; the
Phase 4 start changes nothing on the SIO path.

**Implementation impact (listed, not done).** Transport bulk-read
operation (length a multiple of 32, aligned caller buffer; mock / replay /
real), backend DMA routine with a length parameter, `gbp_av_service`
(service pass over the transport, reusing the 003B/004 records and the
ACK helper), `gbp_avsvc_probe` (statuses, teardowns, block summaries), the
POC, a blob writer in `sdlog`, mock knobs (block content and DMA duration
per source, failure at transfer n, source cleared / kept by the drain,
relatch during the drain), a replay op for bulk reads with a `-blocks.bin`
sidecar, probelog rules, poc_audit profile `avsvc` (5 logical IRQ write
sites: A1, A2, ACK, REARM, STOP; 2 bulk-read sites), unit / host tests,
Makefile targets. The handler is the audited 004 handler, unchanged.

**Tests executed.** None: no source changed, no DOL built, no hardware.
Documents updated: HARDWARE_TESTS.md (planned GBP-AV-SERVICE-001;
GBP-INIT-004B re-labelled optional; pointers), UNKNOWNS.md (U-GBP-007 /
022 / 027 / 028 pointers), INITIALIZATION.md §13 (R11 and the Phase 3
state), HSP.md (pointer), `poc/gbp-init-irq-service-probe/README.md`
(successor pointer), this entry. HSP.md §3's chunk-size sentence is left
as is and listed for correction with the implementation.

**Next.** Review of this specification by the user → implementation
checkpoint (host-side first: transport bulk read with mock / replay,
service pass, probe, tests, audits, Dolphin) → dirty build for review →
user checkpoint → clean rebuild and release audit → only then a possible
authorization of one physical run. Not requested here.

## 2026-09-16 — GBP-AV-SERVICE-001 implemented (dirty build avsvc-0001); NOT physically executed

**Goal.** Implement the Phase 4 entry probe specified in the previous entry
(HARDWARE_TESTS.md "Planned tests — GBP-AV-SERVICE-001"): one delivery of
an HSP cause, the PRESVC snapshot, the whole-block drains of the pending
AUDIO / VIDEO blocks, the ACK from the PRESVC value, POSTACK without a
source requirement, the PI cleanup budget, the re-arm, REARMPOST, the next
cause observed and never delivered, the teardown. No hardware, no
request, no commit. Working tree at the start: clean, HEAD `5ed9d93`
("research: design bounded GBP AV service probe"). Statuses confirmed
before coding: GBP-INIT-003A / 003B / 004 PHYSICALLY EXECUTED;
GBP-AV-SERVICE-001 planned, not implemented; Phase 3 "IRQ core validated,
re-arm carried into the Phase 4 entry".

**Architecture and reuse (no fourth copy of the initialization).** The
003A stage runs verbatim through `gbp_initirqa_run_cause`; the delivery,
the ACK / POSTACK / single-main-W1C step and the teardown hook are the
shared 003B service (`gbp_irq_service.{h,c}`), whose ACK step was split
into `gbp_irq_service_ack_write_postack` (the write + POSTACK + main W1C
for a value the caller already holds) called by the unchanged
`gbp_irq_service_ack` — the 003B and 004 physical fixtures still pin every
record byte for byte; the teardown is the 003A one with the 003B hook. New
modules: `gbp_avblock` (one raw block: whole-block read through the
transport, summary after the timed region, records), `gbp_avdump` (the
block sidecar), `gbp_crc32`, `gbp_avsvc_probe` (the probe). The transport
gained `read_bulk` (device → main memory, `len` a multiple of 32, aligned
buffer, one transfer, no retry) and `gbp_bulk_args_ok`; `gbp_xfer_info`
gained `dma_status_before`.

**Handler chosen.** The 003B extended one-shot (`hsp_backend_oneshot_isr_ext`,
physically executed 2026-09-15), installed once after the first latched
cause — the least ISR change: zero. A second delivery is forbidden by
design, so the 004 generation wrapper and `hsp_backend_irq_multi.c` are
not linked. `__UnmaskIrq` has one call site (`h_irq_unmask`), reached only
from `gbp_irq_service_deliver`, called exactly once by the probe (pinned
by the audit profile); INTMR is never stored directly.

**Backend DMA and cache (audited before coding).** The 32-byte routine
became `dma_len` (physical main-memory address, ARAM address, length): the
32-byte accesses call it with the backend's own buffer and 32, the
whole-block read with the caller's buffer and 0x1000 / 0xF00. Same
register programming (`0xCC005020/24/28` in 16-bit halves, direction bit
15 of CNT_H), same busy refusal (CSR bit 9 or bit 5 set), same polled
completion with the operational 200 ms bound, same single flag clear. The
references issue one DMA of the whole length: the Disc's `0x80089c3c`
with `len`, GBI's ARQ **hi queue** (`0x800617b4` starts `AR_StartDMA` with
the full length; the chunked `0x80061820` is the lo queue, never used for
the GBP — HSP.md §3 corrected). Cache: the Disc's `0x800687dc` is a `dcbi`
loop (before its block DMA and in its DMA-done callback), its `0x80068808`
a `dcbf` + `sync` loop (before writes); libogc2 invalidates before every
EXI / ARAM read DMA. Open-GBP: `DCFlushRange` before the DMA (write back +
invalidate: no dirty line can be written back over the DMA data, the zero
pre-fill reaches memory), `DCInvalidateRange` after; the compiled sequence
`gbp_bulk_args_ok → DCFlushRange → dma_len → DCInvalidateRange` is pinned
by `test_poc_audit.py` on the build.

**The service pass.** PRESVC (PI ×2, CONTROL, IRQ) is the single
authoritative snapshot: reads ok, Disc = GBI, CONTROL 0x8C, INTMR bit 13 =
0, no source outside AV, an AV source pending, odd / bit 15 / high bits 0;
`pending_irq` selects the block set and is the ACK value — never a later
read (a source that appears during a drain is observed at POSTDRAIN and
not added; the ACK does not acknowledge it). Drains AUDIO then VIDEO, one
DMA each, nothing formatted until both are done, VIDEO never started after
a failed AUDIO read; a failed drain ends the run without ACK or re-arm
(`audio_dma_busy|timeout|error`, `video_…`, `drain_uncertain` on a timeout,
teardown `S3_dma_failed`). POSTDRAIN observation only (with the mandatory
consistency checks). ACK `pending | 0x8000` (attempted before the call,
completed on rc ok; `ack_write_failed` otherwise, uncertain, no re-arm).
POSTACK: no source requirement (`boundary=clean|pending_av` is data), shape
mandatory (odd 0, bit 15 = 1, high 0 → else `anomaly_postack_shape`).
PICLEAN: ≤ 1 main W1C, sticky → `anomaly_pi_sticky_after_service`. REARM
`IRQ := 0x0000` once; REARMPOST A–F as 004; NEXTCAUSE polled ≤ 500 ms
while masked, valid with INTSR bit 13 + an AV source + nothing outside AV;
none → `no_next_cause_after_service` (observation class). The second cause
stays latched: no second unmask, no second ISR, no second service — the
teardown's stop word and single W1C close it. W1C budget: ISR 1, main ≤ 1,
NEXTCAUSE 0, teardown ≤ 1 (three at most; the relatch scenario reaches
exactly three). Statuses carry a class (ok / observation / errors / abort
/ transport / dma / anomaly).

**Sidecar.** `GBP-AV-SERVICE-001_avsvc-0001-blocks.bin`, written on X
after the log, outside every timed region: `OGBPBLK1`, a 128-byte
big-endian header (version, flags present/valid per block, pending mask,
drain mask, lengths, per-block CRC-32, rc, wait and dt ticks, tb_hz,
identity ×3, indices, header CRC-32), the AUDIO then the VIDEO bytes, an
`OGBPEND1` footer with the total CRC-32; a block never read has length 0
(nothing uninitialized), a failed read is stored as left and flagged not
valid. Parser: `tools/avdump.py` (info / json / extract). The text log
carries only CRC-32 and four 32-byte windows per block (`BLOCK`, `BLOCKW`);
the on-screen summary shows both CRC-32s so a failed SD write still leaves
a checkable value; a partial save (log only) is reported as such.

**Mock, replay, probelog, audits.** Mock: a whole-block read model
(deterministic pattern per index, per-index rc, partial-on-timeout,
drain-clears-the-source, a source asserting during the Nth read, a phantom
PI cause, a dropped bit 15). Replay: `B <addr> <len> <rc> [<crc32>]`
answered from an attached block source (the sidecar), missing blocks and
CRC mismatches counted, the operation exposed only by a script that has
such a line — older fixtures untouched. probelog: `AUDIOREAD` /
`VIDEOREAD` → `T`, `B`, `T`. poc_audit: profile `avsvc` (objects,
forbidden symbols and prefixes ARQ_/AR_/AUDIO_/ASND/AESND/GX_/net_/DSP_/
SI_/SIO, call-site counts: `gbp_avblock_read` ×2, `gbp_irq_service_deliver`
×1, `gbp_irq_service_ack_write_postack` ×1 from the probe and ×1 from the
shared ACK, `gbp_irq_service_ack` never, IRQ write sites 3 + 1 + 1, INTSR
stores in `h_write_intsr` and the two handlers, main.o calls the ext
constructor, the probe, the sidecar writer).

**Tests executed.** C: 12 binaries, 15046 checks, 0 failures
(`test_gbp_avsvc` 3046 incl. the three physical prefixes; `test_gbp_avdump`
3935; the earlier ten unchanged: 003A/003B/004 physical fixtures replay to
their recorded results). Python: 171 tests OK (`test_avsvc_replay.py`:
synthetic log → fixture + sidecar → replay to the identical summary, the
blocks reported missing without the sidecar, a tampered sidecar rejected,
the physical 003B / 004 prefixes to `abort_bulk_unavailable` with 0
mismatches, no AVSVC fixture under captures/; `test_avdump.py`;
`test_poc_audit.py` profile `avsvc` synthetic and on the build;
`test_isr_audit.py` both handlers of the build; `test_probelog.py`;
`test_artifacts.py`). Docker build: eight POCs, 0 warnings; `make
avsvc-audit`: 0 findings, `hsp_backend_oneshot_isr_ext` (82 instructions)
and `hsp_backend_oneshot_isr` (70) CLEAN; the 003A / 003B / 004 / 002
audits still clean on the rebuilt objects. Dolphin (OSD off): absent →
`abort_inconsistent`, GBPlayer model → `abort_control_shape`, both PASS —
Dolphin never reaches the service (preconditions not weakened).

**Dirty DOL identity.** app `gbp-av-service-probe`, Test ID
GBP-AV-SERVICE-001, Build ID avsvc-0001, base HEAD `5ed9d93`, describe
`5ed9d93-dirty`; DOL 403968 bytes, entry 0x80003100, one text section
0x80003100–0x8004E560, one data section 0x8004E560–0x80065A00, BSS
0x800659F0 + 0x479C8, sections 32-byte aligned (Dolphin-loadable);
devkitPPC gcc 16.1.0, libogc2 r2442.094b250; SHA-256
`f2e2de0a233c5e0bc63d36de60c11c9fe3349d9c5924d1930dedcbcbaf69dbc0`.
**NOT A PHYSICAL CANDIDATE.**

**Residual risks (for the review).** The whole-block DMA is the one new
variable class on hardware: the register programming and the completion
routine are those of every 32-byte access so far, but a 0x1000 / 0xF00
transfer through the HSP has never been executed by Open-GBP (the
references do it on every pass). The device semantics of a block read
(whether the drain clears the status bit before the ACK) are unknown and
observed, not assumed (POSTDRAIN / POSTACK). A DMA timeout may leave the
engine busy for the teardown's 32-byte accesses (best-effort, power
cycle). The main-loop W1C and the teardown W1C are the same budget as 004.
The mock's synthetic semantics (a drain clears nothing by default; the
level bit-15 model re-latches the PI only on register changes) are not
physical data.

**Documents updated.** HARDWARE_TESTS.md (planned entry status →
IMPLEMENTED — NOT PHYSICALLY EXECUTED, implementation notes a–h),
HSP.md §3 (the ARQ hi-queue precision replacing the old chunk sentence;
the cache sequence), `poc/gbp-av-service-probe/README.md`, tests/README.md,
captures/README.md (the `B` grammar and the sidecar association; no
fixture yet), this entry. Phase 3 stays "IRQ core validated, re-arm
carried into the Phase 4 entry"; no physical re-arm is claimed.
Requirements preserved: Start-up Disc / GBI parity; physical Link Port
compatibility (no SIOCTL / SIODATA / KEYPAD access); rumble / GBP-aware
features; the virtual Mobile Adapter over the BBA additive — none touched.

**Next.** Review of this implementation → micro-audit if needed → user
checkpoint → clean rebuild and release audit → only then a possible
authorization of one physical run. Not requested here.

## 2026-09-16 — GBP-AV-SERVICE-001 micro-audit (DMA / buffers / teardown): passed; two rules tightened, no defect

**Goal.** Before the implementation checkpoint, audit the properties this
POC introduces — the whole-block DMA, the raw buffers, the cache
sequence, the timeout / busy behavior of the teardown, the one-shot
delivery, the snapshot immutability, the sidecar — on the dirty build's
ELF, DOL and objects, with the host suites and the mock. No hardware, no
request, no commit. Base HEAD `5ed9d93`, tree clean before the
implementation; the tree stays dirty (the same files plus this entry).

**DATA / BSS.** ELF: `.sdata` ends at 0x800659F0 = the RW `PT_LOAD`'s
file-backed end; `.sbss` (NOBITS) starts there; the BSS `PT_LOAD` is
[0x800659F0, 0x800AD3B8). DOL: one data section [0x8004E560, 0x80065A00)
— 16 bytes longer than the ELF's file-backed range because
`tools/dolpad.py` rounds section sizes up to 32 bytes with zeros (Dolphin
refuses unaligned sizes). Those 16 bytes are the only DOL bytes inside the
BSS range: they are zero in the file, they are not ELF content (the DOL
payload equals the ELF segment bytes, verified), and libogc2's
`ogc_crt0.S` memsets `__bss_start..__bss_end` after the load. No loaded
content byte is in a zeroed region. The same padding exists in every
earlier build (8 to 24 bytes; 003B 16, 004 24 — both physically executed);
`tests/host/test_artifacts.py` now proves it for every POC (payload =
ELF bytes; added bytes are zero; no file-backed byte inside BSS; no
section overlap; BSS segment = DOL BSS; entry 0x80003100; MEM1). After the
rebuild the layout moved by 0x20 (text 0x80003100–0x8004E580, data
0x8004E580–0x80065A20 with the same 16-byte zero padding, BSS
0x80065A10 + 0x479C8). Not a blocker: rounding, not aggregation, not content.

**Buffers (nm, after the rebuild).** `audio_raw` 0x80068FE0 (0x1000),
`video_raw` 0x800680E0 (0xF00), `dma_buffer` 0x80069FE0 (0x20),
`log_storage` 0x8006A000 (0x14000), `dump_buffer` 0x80066148 (0x1F8C,
not a DMA target) — all static `.bss` symbols, 32-byte aligned where a
DMA lands, full lengths, adjacent without overlap, inside the BSS segment,
never on the stack, never shared with the ring log or the records.

**Source address.** `gbp_block_addr(base, index, 0)` = base + (index <<
20): AUDIO 0x01800000, VIDEO 0x01100000 under expansion code 3 (base
0x01000000), logged in the `AUDIOREAD` / `VIDEOREAD` records and pinned by
the tests; 0x1000 / 0xF00 stay inside their 1 MB windows. The argument
rule was tightened during this audit: `gbp_bulk_args_ok` now also refuses
a transfer whose source or destination range wraps and one that crosses
its register window (the compiled backend checks the rule before it
programs anything).

**DMA registers, direction, length (dma_len listing).** The CSR test
`andi. r10,r9,0x220` (bits 9 and 5) branches to the refusal path
(counter, `dma_status`, return BUSY) before any store; then six `sth` to
0xCC005020…0xCC00502A: MMADDR = destination physical address (>> 16 &
0x3FF / & 0xFFE0), ARADDR = source, CNT_H = (len >> 16 & 0x3FF) |
(dir << 15) with dir = 1 (ARAM → main memory, the Disc's `param_4 << 15`
and libogc's `AR_ARAMTOMRAM`), CNT_L = len & 0xFFE0 — one store, one
start, no loop over chunks. The 32-byte path calls the same routine with
its own buffer and 32; the poll clears bit 5 only on completion, never on
timeout.

**Cache.** libogc2 `cache_asm.S`: `DCFlushRange` = `dcbf` per 32-byte line
+ `sc` (the flush completion barrier), `DCInvalidateRange` = `dcbi` per
line; both cover the range rounded to lines. Compiled `h_read_bulk`:
`gbp_bulk_args_ok → DCFlushRange → dma_len → DCInvalidateRange` (pinned by
`test_poc_audit.py`). The zero pre-fill (`memset` in the probe's first
lines, before the 003A stage) precedes the flush by the whole
initialization; between the flush and the completion nothing touches the
buffers (the probe only records `t_start`, calls, records `t_end`); the
first CPU read of a block is `gbp_avblock_summarize`, called from the end
records after the teardown, i.e. after the invalidate. No dirty line can
be written back over DMA data (flushed before), no stale line can be read
(invalidated after). Not a blocker.

**Timeout / error.** A timed-out read keeps `attempted = 1, completed =
0`, `drain_uncertain = 1`; the block is present, not valid, never
summarized (no CRC as if complete), stored in the sidecar as left in memory
with its rc; a busy refusal programs nothing. New test: an AUDIO timeout
that leaves the engine busy — every later transfer (CONTROL restore, IRQ
reads, STOP) is refused without a register store, none started, no retry,
no VIDEO, no ACK, no re-arm, the teardown's fixed set of accesses bounded
(≤ 12 refused transfers), the interrupt path restored, `power_cycle_required
= 1`, `restore = error`, `uncertain = 2`. Every wait is bounded by the
200 ms transfer timeout; no loop waits for the engine.

**One-shot delivery.** `h_irq_install` loads
`hsp_backend_oneshot_isr_ext` when `use_ext_isr` (offset 40 of the
backend) is set — `hsp_backend_irq_transport_ext` stores 1 there and
main.o calls only that constructor — else the base handler; both symbols
are therefore referenced by the object and linked, the base one dead for
this POC (the 003B build, physically executed, had the same object). One
install, one `__UnmaskIrq` site reached once, mask before the single W1C
(isr_audit CLEAN on both bodies), no direct INTMR store, no DMA inside the
handler (its only calls: `__MaskIrq`).

**Immutability / order / ACK / POSTACK / PI / REARM / NEXTCAUSE.**
`pending_irq`, `drain_mask`, `audio.selected`, `video.selected` are each
assigned once (PRESVC); the ACK value is computed by the shared service
from that argument; POSTDRAIN assigns none of them. The event-order test
proves AUDIO start/complete < VIDEO start/complete < ACK < POSTACK <
PICLEAN < REARM < REARMPOST < NEXTCAUSE < teardown, with no IRQ write
between the drains. POSTACK 0x8000 / 0x8100 / 0x8400 / 0x8500 all accepted
(tests); no `irq & 0x0555 == 0` rule anywhere in the probe. PICLEAN: ≤ 1
main W1C, sticky aborts. `irq_unmask` has one call site in the tree
(`gbp_irq_service_deliver`), `write_intsr` two (POSTACK, teardown) plus
the handler: the absolute budget is three by construction and counted at
runtime (`COUNTERS w1c_total`).

**Sidecar.** Written only from main.c's X branch after
`gbp_avsvc_probe_run` returned (static order pinned by the on-build test:
probe entry < `sdlog_save` < `gbp_avsvc_dump_info` < `gbp_avdump_serialize`
< `sdlog_save_blob`); the service objects reference no file, SD,
serializer or gecko symbol. Buffer writers: the pre-fill memset and the
DMA, nothing else (the teardown never touches them; the summary and the
serializer read). Format audited field by field (big-endian put16/put32,
zeroed 128-byte header, 16-byte NUL-padded identities, no pointer, no
struct copy, absent block = length 0), C ↔ Python round trips; CRC-32 =
zlib variant (poly 0xEDB88320 reflected, init/xorout 0xFFFFFFFF, check
value 0xCBF43926) on `uint8_t`. Partial save: the log first, then the
blob; the screen and the gecko lines report each result and mark a
log-only save as PARTIAL; the run's result is unaffected.

**Replay / fixtures / mock.** `B` lines: exact address, length and rc
must match (mismatch counted), bytes only from the attached sidecar and
verified against the line's CRC-32, missing blocks counted and the
harness fails (zeros are never silent evidence); scripts without `B`
expose no bulk read (every older fixture replays unchanged). The physical
003B / 004 prefixes end before their device ACK — before any operation
those runs never made — with an explicit BOUNDARY comment. The mock now
refuses a bulk read that does not name the block's exact address (offset
0 of its window) and counts it; the tests assert the exact addresses and
lengths of every bulk operation.

**Audits / Dolphin (rebuilt).** Docker rebuild 0 warnings; `avsvc-audit`
0 findings, both handlers CLEAN; the 002/003A/003B/004 audits clean on the
rebuilt objects; Dolphin absent → `abort_inconsistent`, GBPlayer model →
`abort_control_shape`, no write, no unmask, no bulk read. Tests: C 12
binaries, 15385 checks, 0 failures; Python 174 tests OK. Dirty DOL after
the audit: 404000 bytes, entry 0x80003100, sha256
`4564e42a2c8239161ee19440d9292818d42d18ac31a7b9b73bfc3dd5c34eb52d`
(commit `5ed9d93-dirty`) — **NOT A PHYSICAL CANDIDATE**.

**Result.** GBP-AV-SERVICE-001 MICRO-AUDIT PASSED — READY FOR
IMPLEMENTATION CHECKPOINT — NOT A PHYSICAL CANDIDATE. Changes made by the
audit: the bulk argument rule (wrap / window), the mock's exact-address
rule, the new tests (section map, timeout-then-busy teardown, save
timing, exact addresses); no probe logic changed.

## 2026-09-16 — GBP-AV-SERVICE-001 sidecar / cache audit: identity fields were truncating (fixed, format version 2); the `sc` after `dcbf` confirmed

**Identity fields — defect found and fixed.** The sidecar's version-1
header held three 16-byte identity fields (test_id 0x40, build_id 0x50,
commit 0x60, NUL padded) and both the serializer and the probe's
description helper copied at most 16 characters: the official Test ID
`GBP-AV-SERVICE-001` (18 characters) was stored as `GBP-AV-SERVICE-0` —
a silent truncation of an identity used to correlate evidence, i.e. a
material format defect (the tests even asserted the truncated string).
Version 1 was never produced on hardware (no physical run) and no file of
it exists outside `build/`. Fix: **format version 2** — 256-byte header,
four 32-byte fields at 0x40 (test_id), 0x60 (build_id), 0x80 (app, new),
0xA0 (commit), indices at 0xC0/0xC4, 52 reserved zero bytes, header
CRC-32 at 0xFC, payload from 0x100, the same footer. Identity rule: 1 to
31 characters of printable ASCII without spaces (0x21..0x7E) for test_id
and build_id, 0 to 31 for app and commit, zero padded to the field (a NUL
is always present); a string that does not fit, an empty required field
or a bad byte is an ERROR — serializer `-2`, parser `-8`, Python
`ValueError` — never a truncation. `gbp_avdump_set_identity` /
`gbp_avsvc_dump_info` store nothing and set `identity_error` when a
string does not fit; main.c reports "identity does not fit the format"
instead of writing a sidecar. Round trips now compare byte by byte
`GBP-AV-SERVICE-001`, `avsvc-0001`, `gbp-av-service-probe` and
`5ed9d93-dirty` (C and Python; the C dump parsed by tools/avdump.py);
boundaries tested: 31 characters fit exactly, 32 are refused, required
empty refused, optional empty allowed, a space or a non-ASCII byte
refused, a field without NUL / with non-zero padding / non-zero reserved
bytes / version 1 refused by the parsers. The header is memset to zero
before the field-by-field writes (no struct copy, no pointer, no
uninitialized byte); the layout was re-verified byte by byte in the tests.

**Correlation log ↔ fixture ↔ sidecar ↔ DOL.** The sidecar carries the
full Test ID, Build ID, app and commit — the same strings as the log
header (`test_id=`, `build_id=`, `commit=`, `IDENT app=`), the DOL's
`OPENGBP-IDENT` marker and build-info, and a future fixture's header
(`# TEST_ID`, `# BUILD_ID`, `# COMMIT`, `# DOL_SHA256`, to which
`# BLOCKS_SHA256` will be added) — plus the pending / drain masks and the
per-block CRC-32 that the log's `SVC start` and `BLOCK` records also
carry. No SHA-256 of the DOL inside the sidecar (not part of the design).

**`sc` after `dcbf` — not a typo.** libogc2 `cache_asm.S` `DCFlushRange`:
`dcbf` per 32-byte line, then the `sc` instruction (0x44000002 in the
linked binary at 0x8002422C), then `blr`. libogc2 installs its own
system-call vector at 0xC00 (`exception.c` `__systemcall_init` →
`exception_handler.S` `systemcallhandler_start`): `mfhid0 r9; ori
r10,r9,0x0008; mthid0 r10; isync; sync; mthid0 r9; rfi` — HID0 bit 0x0008
(data cache flush assist) set, `isync` + `sync`, DCFA cleared — the SDK's
flush-completion idiom; the exception entry and `rfi` are context
synchronizing. So the pre-DMA flush ends with a full `sync` inside the
vector before the DMA registers are programmed. `DCInvalidateRange` is a
`dcbi` loop without a barrier, as in the SDK and the Start-up Disc
(`0x800687dc`); the first CPU read of a block (`gbp_avblock_summarize`,
after the teardown) is program-ordered after it. Sequence re-confirmed on
the rebuilt object: zero pre-fill (probe start) → `DCFlushRange` →
`dma_len` (one DMA, device → main memory) → completion → `DCInvalidateRange`
→ first CPU read after the teardown; no CPU access to the raw buffers in
between (writers: the pre-fill memset and the DMA only). No change to the
cache policy.

**Regression (the DOL changed).** C: 12 binaries, 15606 checks, 0
failures (`test_gbp_avdump` 4161 incl. the identity suite, `test_gbp_avsvc`
3380). Python: 175 tests OK. Docker rebuild: 0 warnings; audits avsvc /
004 / 003B / 003A / 002 clean; Dolphin absent → `abort_inconsistent`,
GBPlayer model → `abort_control_shape`, both PASS. New dirty DOL: 404736
bytes, entry 0x80003100, text 0x80003100–0x8004E780, data
0x8004E780–0x80065D00 (24 zero padding bytes into `.sbss`, verified), BSS
0x80065CE8 + 0x47A50, sha256
`969805185e281b0ae25c22c22d07403673929dccbacf56c60d773e463309a76b`
(commit `5ed9d93-dirty`); the previous dirty hash `4564e42a…b52d` is
discarded. **NOT A PHYSICAL CANDIDATE.**

**Result.** GBP-AV-SERVICE-001 SIDECAR/CACHE AUDIT PASSED — READY FOR
IMPLEMENTATION CHECKPOINT — NOT A PHYSICAL CANDIDATE.

## 2026-09-16 — GBP-AV-SERVICE-001 executed: first drained service, first re-arm, next HSP cause 43.9 µs after `IRQ := 0`; Phase 3 COMPLETE; consolidation

**Goal.** Consolidate the single physical run of GBP-AV-SERVICE-001 (build
avsvc-0001, clean commit d3a6d23 = `d3a6d237fbec43e512ac85da2bbe93a903ff0f0c`,
DOL `d9e6dccd6f6ac2a729cc1be904214dbaf6f0bd88ee2929244b185a5ba39556ff`):
preserve the raw evidence, verify every number from the files, decide what
the run establishes, close what it closes, and give the direction of the
next Phase 4 experiment. No implementation, no DOL, no hardware, no request,
no commit.

**Preservation.** Raw log `logs/GBP-AV-SERVICE-001_avsvc-0001.log`, 23154
bytes, sha256 `d0324b6d12f02984a0d748f896f1c16f724d69c0e3022bef5460f8ed32a03713`,
and raw sidecar `logs/GBP-AV-SERVICE-001_avsvc-0001-blocks.bin`, 8204 bytes,
sha256 `1c17a2d77fa60b4446863032ced62cc3d2390625de2a42b120a195eb074edc1e`
(both computed from `logs/`, matching the announced values, untouched);
copies `captures/local/GBP-AV-SERVICE-001_avsvc-0001.log` and
`…-blocks.bin` (byte-identical); fixture
`captures/fixtures/hw-gamecube-gbp-2026-09-16-avsvc-0001.gbpreplay`
(metadata header with build / commit / DOL, log and sidecar hashes and
sizes, `# BLOCKS=hw-gamecube-gbp-2026-09-16-avsvc-0001-blocks.bin`; raw
blocks verbatim; the interrupt path as it happened — `I i null`, `I u` with
the physical one-shot record, `I m`, `I r`; the two whole-block reads as `B
01800000 00001000 ok fec5e4e7` / `B 01100000 00000f00 ok fe45ff08` between
their time-base reads, bytes NOT in the script; five IRQ-register writes
A1, A2, ACK, RE-ARM, STOP; one teardown `P a 00002000`) next to
`hw-gamecube-gbp-2026-09-16-avsvc-0001-blocks.bin`, a byte-identical copy of
the console's sidecar. Replay through the AVSVC probe with the sidecar: 132
operations, **0 mismatches, 0 exhausted, 0 unmatched polls, 2 bulk reads, 0
blocks missing, 0 CRC mismatches**, the physical result reproduced
(`ok_service_rearm_cause_observed`, `restore=ok`, 179 log lines, every
record equal to the console's up to the poll counters of a scripted
transport); without the sidecar both blocks are reported missing and the
run exits 1 (the buffers keep the pre-fill; nothing is invented). The
fixture regenerates from the raw log with `tools/probelog.py` (182
records). **GBP-AV-SERVICE-001 — PHYSICALLY EXECUTED 2026-09-16.**

**Integrity.** `lines=182 dropped=0 truncated=0`; `AVSVC end
status=ok_service_rearm_cause_observed class=ok restore=ok
teardown=S4B_next_cause_latched errors=0 transport_ok=1`; `WRITES
irq_attempted=5 irq_completed=5 uncertain=0`; `STATS transfers=58
timeouts=0 busy=0 bulk_transfers=2 bulk_bytes=7936`; `COUNTERS unmasks=1
deliveries=1 acks=1 rearms=1 next_causes=1 unexpected=0000 isr_w1c=1
main_w1c=0 teardown_w1c=1 w1c_total=2 control_ok=1 uncertain=0`;
`power_cycle_required=1` (performed). **Sidecar:** magic `OGBPBLK1`, version
2, header 0x100, flags 0xF, 8204 = 0x100 + 0x1000 + 0xF00 + 12, identities
whole (`GBP-AV-SERVICE-001` / `avsvc-0001` / `gbp-av-service-probe` /
`d3a6d23`), header CRC `6174E52D`, AUDIO `FEC5E4E7`, VIDEO `FE45FF08`, total
`18E966CF` — all four recomputed independently on the host and equal; the
log's BLOCK / BLOCKW records equal the sidecar's summaries and windows
(GBP-HW-060).

**What the run established (every number from the files; evidence
GBP-HW-048…060, GBP-IRQ-010).** (1) 003A sequence reproduced a fourth time;
first cause **4264215 ticks = 105.289 ms after A2** (four runs within 16 µs),
IRQ 0x0400, then 0x0500 within 0.92 ms; delivery inside `__UnmaskIrq`, entry
**72 ticks = 1.778 µs** after t_unmask, INTSR `0x00012000` / INTMR
`0x000021FA`, mask-first, one W1C, no reentry (GBP-HW-048 — a confirmation of
established mechanics, not a discovery). (2) **PRESVC 0x0500**, PI clear, bit
15 = 0, 188 µs after the entry — the authoritative read (GBP-HW-049). (3)
**AUDIO 0x1000 from index 0x8 by one DMA: 2692 ticks = 66.47 µs around the
call, 2475 of wait, 760 polls, CSR 0x0804 before/after; VIDEO 0xF00 from
index 0x1: 2485 ticks = 61.36 µs, 2319, 712** — no timeout, no busy, AUDIO
completed before VIDEO started (GBP-HW-050/051, FACT for the transfers; ≈ 21
time-base ticks per 32 bytes, close to Dolphin's model, one run each, no
rate promoted). (4) `dt_service=10997` ticks = 271.5 µs — a measurement of
this probe. (5) **POSTDRAIN still 0x0500, PI clear** ≈ 93 µs after the last
completion: the drain alone did not clear the source bits in that window
and raised no cause; not concluded that a read never alters the internal
state (GBP-HW-052). (6) **ACK `0x8500` → 0x8000 at +25.9 µs**, PI clear, no
main W1C; 004's undrained ACK read 0x8400 at +26.0 µs, 003B's undrained
0x8000 at +25.1 µs: the drained pass produced a source-clean read-back
consistently with the references' order — no microscopic causality claimed
(GBP-HW-053). (7) **First physical re-arm `IRQ := 0` after a serviced cycle**,
with PI clean verified before (GBP-HW-054). (8) **REARMPOST 43.90 µs after
t_rearm: INTSR bit 13 = 1 in two reads, INTMR bit 13 = 0, IRQ 0x0400, CONTROL
0x8C — outcome B**, the next cause found at once and never delivered
(GBP-HW-055); whether that request was retained under bit 15 = 1 and
released or a new event is undetermined (not sampled in between) and
non-blocking. (9) Teardown with the second cause latched: CONTROL 0x90,
IRQSTOPPRE 0x0500 (0x0100 back within ≤ 301 µs of REARMPOST), **stop 0x8FAA →
0x8AAA**, **one W1C** `00012000 → 00010000`, handler restored, INTMR
`0x000001FA`, AR_INFO 0x005B → 0x0043, FINAL 00 / 9090, `restore=ok`
(GBP-HW-056). (10) Raw AUDIO: 3969 zero bytes, values 00/01/11, one non-zero
byte at offset 0 of 123 of the 128 32-byte lines plus four isolated bytes
(GBP-HW-057); raw VIDEO: `7F 7F FF FF` ×954, `FF FF FF FF` first (GBI
frame-start predicate true), `FF 7F FF FF` ×5 (GBP-HW-058) — recorded, not
interpreted. (11) Byte-0 extras in every register class (0x01 / 0x03 / 0x10 /
0x11 / 0x12 / 0x13 / 0x43), offset-2 exceptions (A2PRE `BB`, group 0 `00` /
`01`, POSTDRAIN group 5 `04`); no decision fed by them (GBP-HW-059).

**Unknowns.** U-GBP-027: functional part CLOSED (delivery → drained service
→ ACK → PI clean → re-arm → next cause, one cycle); investigative sub-items
(retained vs new request, period, missed-block cost, sustained cycles)
non-blocking follow-ups. U-GBP-028: partially closed (an ACK after a drain
can produce a source-clean snapshot; the undrained case stays undetermined,
priority lowered). U-GBP-007: bit 15 = 1 with sources 0 raised no cause for
≥ 203 µs, bit 15 → 0 was followed by one within 43.9 µs — still H, unnamed.
U-GBP-014: fourth data point; first post-drain intervals; no period.
U-GBP-021 / 025: new catalogue values, reinforced non-blocking; the AUDIO
per-line byte 0 noted as a hypothesis (payload vs transfer phenomenon).
U-GBP-022: latched model, three runs; cause captured after a re-arm. U-GBP-
008 / 011 / 012: first raw data, open.

**Phase 3 — formal decision.** The criterion recorded in "next step after
GBP-INIT-004 decided" (Phase 3 closes with the first physical service →
re-arm → next cause) is met: **PHASE 3 COMPLETE (2026-09-16)** — IRQ core
validated by 003B / 004, service, re-arm and next cause validated by this
run, remaining microscopic unknowns non-blocking. Phase 4 was entered by
this probe (first physical AUDIO/VIDEO blocks) and is not concluded.
ROADMAP Phase 3 marked COMPLETE, Phase 4 IN PROGRESS; INITIALIZATION.md §14
(R11 promoted for one cycle); CLAUDE.md untouched (no phase marker).

**Documentation.** HARDWARE_TESTS.md (executed entry with the log verbatim
and the analysis; planned entry → executed), EVIDENCE.md (GBP-HW-048…060,
GBP-IRQ-010; hardware notes on GBP-VID-001 / GBP-AUD-001), UNKNOWNS.md
(U-GBP-007/008/011/012/014/021/022/025/027/028), INITIALIZATION.md §13
pointer + §14, REGISTERS.md (VIDEO / AUDIO rows, §4 drained cycle), HSP.md
(§3 measured whole-block DMAs, §4 PI row), ROADMAP.md, captures/README.md
(fixture row, sidecar paragraph), tests/README.md, the POC README (status,
Result), this entry.

**Tests.** New: `tests/unit/test_gbp_avsvc.c` `test_hw_avsvc_gbp(fixture,
sidecar)` (argv[4]/[5]; every result field, the sidecar identities / CRCs,
the raw bytes in the buffers, the records, and the same script without the
sidecar → blocks missing), `tests/unit/Makefile` (`HW_AVSVC_GBP`,
`HW_AVSVC_BLOCKS`); `tests/host/test_hw_fixture.py` `HardwareFixtureAvsvc`
(header hashes, regeneration from the raw log, the interrupt path and the
`B` lines, writes / polls / ACK / re-arm, the 21 IRQ reads verbatim, the
timeline, the offset-2 exceptions); `tests/host/test_avsvc_replay.py`
(physical fixture with the sidecar → physical result; without → missing,
exit 1; tampered → rejected; the fixture-directory rule now admits exactly
the physical AVSVC fixture and its sidecar, and `B` lines only in a script
that names a sidecar); `tests/host/test_avdump.py` `AvdumpPhysicalSidecar`
(identities, every CRC, the raw byte positions, the CLI). Earlier fixtures
untouched. Results: C 12 binaries, **15682 checks, 0 failures**
(`test_gbp_avsvc` 3456, `test_gbp_avdump` 4161); Python **172 passed, 17
skipped** (every skip is an object-audit test that needs the Docker
`make build <poc>-audit` listings / objdumps, not produced in this session —
no build was run). No runtime code changed.

**GBP-VIDEO-001 — direction only (not designed).** From the physical data:
(a) the structure of the 0xF00 block — the references' 4 lines × 240
pixels × 4 bytes is untested by one DMA; a sequence of consecutive blocks is
needed; (b) the temporal block sequence under a bounded repeated service —
first the frame-start flag periodicity (every 40th block per the
references) and the per-block CRC / first word / flag in the log, with the
raw bytes kept (the sidecar generalized to N blocks or a ring is a design
decision, not taken here); (c) the request cadence as a by-product
(U-GBP-014, U-GBP-027 sub-items) with the same masked, drained, re-armed
cycle validated here; (d) the byte-doubling exceptions and the AUDIO
per-line byte 0 checked for reproducibility across blocks (content vs
transfer phenomenon, U-GBP-021); (e) the first controlled cartridge
(known-color pattern) only when the content question requires it —
cartridge-less captures come first. Everything else (buffer strategy,
bounds, second delivery, the KEYPAD write) is a new decision for the design
step.

**Git.** No commit, no push, no hardware. Expected working-tree changes:
the physical fixture and its sidecar (new), the raw copies under
`captures/local/` (ignored), the tests and Makefile above, the documents
above. **GBP-AV-SERVICE-001 PHYSICALLY EXECUTED 2026-09-16 — PHASE 3
COMPLETE — consolidation ready for review.**

## 2026-09-16 — GBP-VIDEO-001 designed: the VIDEO path of both references re-read, the physical block matched against their embedded idle screen, a bounded sequence capture specified; analysis only

**Goal.** Design the first dedicated Phase 4 experiment: the smallest
physical capture that establishes the structure of a 0xF00 VIDEO block, the
frame-start semantics, the block order and count per frame, and the
cadence, without rendering. Mode: reverse engineering / analysis /
specification. No implementation, no DOL, no hardware, no request, no
commit.

**References re-read (Ghidra headless on the private decompilations;
behavior in `docs/research/VIDEO_PATH.md`, evidence GBP-VID-002…007).**
Start-up Disc: slot 5 → `FUN_8008A480` reads 0xF00 from `base + 0x100000`
into a ring of 40 × 0xF00 (`0x801E4A80`, table `0x801B3310`), completion →
message queue (depth 41) → consumer thread `FUN_8008EDE8`: frame-start
predicate `FUN_8008A588` = `(first halfword >> 7) & 1` = **bit 7 of byte 1**
(the earlier note "byte 0" was wrong: the dummy block sets `halfword |=
0x0080`); block index reset by the flag, `< 0x28` gate, blocks beyond 40
dropped until the next flag, five frame buffers of 0x12C00 (240×160×2),
conversion `FUN_8008EFB4` = 60 groups × 4 rows with source stride 0x1E0
halfwords (**raster, 960 bytes per line**), pixel = **byte 3 | byte 1 << 8 |
FILL**, output GX 4×4 tiles (0x780 per block), presenter `FUN_80009044` =
`GX_InitTexObj(…, 240, 160, GX_TF_RGB5A3, …)` ×3; FILL inferred 0x8000. The
Disc embeds a full 240×160 RGB5A3 frame at `0x801B45A0` (the AGB idle screen:
"GAME BOY" / "Nintendo®", lines 56–100, one main color = indigo under the
RGB5A3 reading, crimson under the GBA order) and compares the live stream
with it block by block (`FUN_8008F080`). GBI: thread `FUN_8000BF30` — ARQ read
0xF00 to `0x80179420` (callback `FUN_8000A8E0` touches no data), after the
synchronous ACK: predicate `(u32 & 0x80800000) == 0x80800000` (**bytes 0 AND
1**), block index := 0 on true, copy 240 × 4 pixels as `b1 << 8 | b3` into a
linear 16-bit raster at `blk × 0x780` of a triple buffer of 0x12CC0, per-block
64-bit checksum, frame complete at `blk == 0x27`, `(blk + 1) % 0x28`; renderer
`FUN_80003444` tiles 4 rows at a time with `| 0x80008000` (RGB5A3); PNG writer
`FUN_8000FACC` maps bits 14–10 → R. GBI embeds two 40-entry per-block checksum
tables (`0x800B0E78` content blocks 14–25 = the Disc frame's layout;
`0x800B0F18` blocks 12–19) and injects key states on a match. Dolphin: 4
raster lines per block, flag `|= 0x8000` on pixel 0, `hh hh ll ll` on read,
video IRQ on the audio phase, color order from mGBA's macro (GBA order if
mGBA's default applies — divergence flagged, GBP-VID-007).

**Answers to the design questions.** (1) Block = 4 raster lines × 240 px × 4
bytes, 40 per frame: F (code) in both, C for hardware until a frame is
captured. (2) Pixel: both consume bytes 1 and 3 only; 16-bit = bit 15 flag +
5-5-5 in **GX RGB5A3 order (R high)**: C (two references + the reference
frame's color); FACT needs a known-color cartridge (U-GBP-011 re-evaluated).
(3) Predicates exact (GBP-VID-004); the logger's `gbi_frame_start` is GBI's
predicate; `first_word = FFFFFFFF` with `gbi_frame_start = 1` is consistent
(mask test, not equality). (4) The 40 is an explicit constant in both
binaries (160 / 4 written out), not a measurement. (5) The physical block
read the references' way is 960 × 0x7FFF with the flag on pixel 0: its
GBI checksum `0x7F0FFF10` equals entry 0 of both GBI tables, its Disc
conversion equals block 0 of the Disc's frame byte for byte (GBP-VID-006):
CORROBORATED as the first block of the idle screen; geometry and color
still untested. (6) Positional statistics (GBP-HW-061): VIDEO deviations
only in byte 0 of pixel words (+0x80, ≡ 0 mod 4), AUDIO non-zero bytes at
offset 0 of 123/128 32-byte units (`01`/`11`) + four strays; same values as
the run's register-read extras; classification data vs read-path artifact
**UNKNOWN** (U-GBP-029 opened); raw never corrected; both references are
blind to those bytes.

**GBP-VIDEO-001 decisions (HARDWARE_TESTS.md "Planned tests —
GBP-VIDEO-001").** Capture: **88 VIDEO blocks** (two frames + 8; 48 = one
frame + 8 is the minimum useful setting, same code) — the frame boundary is
the point of the experiment and two boundaries give a consistency check
without claiming a period; the jump from one delivery to ~100–300 is
bounded and the first 4 cycles keep the AVSVC verification snapshots
(VERIFY_CYCLES) so an early anomaly ends the run before the lean loop.
Bounds: MAX_DELIVERIES 320, MAX_VIDEO_BLOCKS 88, MAX_AUDIO_BLOCKS 320,
MAX_RUNTIME_MS 1000, T_DELIVERY 100 ms per cycle, T_FIRST_CAUSE 2000 ms,
T_DMA 200 ms; every MAX → teardown with the data kept. AUDIO: drained on
every cycle it is pending (AUDIO before VIDEO, the references' order), raw
kept for the first 8 and the last block, CRC/first word/unit-0 statistics
for all — never left pending to simplify VIDEO. Buffers: static
`video_blocks[88][0xF00]` (337 920 B) + 9 raw AUDIO + 1 scratch, 32-byte
aligned, bounds checked; no malloc. Sidecar: a new sequence format
`OGBPSEQ1` (identities as v2, cycle / VIDEO / AUDIO tables, raw blocks in
sequence order, per-section and total CRC-32; partial saves with actual
counts); v2 untouched. Handler: the 003B extended one-shot reused, its
record consumed under mask and zeroed before each unmask (`count == 1` per
cycle, else anomaly); the 004 multi-cycle generation/slot machinery is not
needed for dozens of cycles. Records: compact binary per cycle / per VIDEO
block / per AUDIO drain, formatted only after the loop; ring ≥ 640 × 192.
Failure policy: any unexpected source, DMA failure, ACK / re-arm failure, PI
sticky, reentry, capacity → stop, bounded teardown, save everything
captured. Success: stable repeated service, ≥ 48 blocks, ≥ 1 boundary,
blocks-per-frame recorded as observed (40 is not a gate), offline assembly
against the embedded idle screen, `restore=ok`, sidecar intact. Cartridge:
none — the idle screen is a known frame in both references; a known-color
cartridge belongs to VIDEO-002. No KEYPAD writes (one new variable:
repetition). Timing: time-base reads per cycle and per block; intervals
reported per run, never as frequencies. Compatibility preserved: AUDIO
drained, Link Port / SIO / BBA / Game Pak untouched.

**What VIDEO-001 can close / leaves.** Closes for one run: blocks per frame
and the flag's occurrence, block order, first cadence intervals
(U-GBP-014), repeated-service stability (U-GBP-027 (b), (d)), byte-0
reproducibility inside blocks (U-GBP-029), the AV-block layout part of
U-GBP-008. Leaves: color naming (VIDEO-002), rendering, output mode /
latency, cartridge content, the AUDIO format.

**Phase 4 sequence (ROADMAP):** VIDEO-001 capture / order / boundaries /
cadence (no cartridge) → VIDEO-002 first rendered frames + known-color
cartridge (color FACT; KEYPAD introduced there or in Phase 5) → VIDEO-003
sustained streaming with a real cartridge. No further micro-probes unless
VIDEO-001 raises a blocking question.

**Documentation.** New `docs/research/VIDEO_PATH.md`; HARDWARE_TESTS.md
planned GBP-VIDEO-001; EVIDENCE.md GBP-VID-001 corrected (dummy block byte
1; 0x25800 = ring, 0x12C00 = frame buffer), GBP-VID-002…007, GBP-HW-061;
UNKNOWNS.md U-GBP-008 / 011 / 014 updated, U-GBP-029 opened; REGISTERS.md
§2.2 (bytes consumed, predicates, color order, geometry); GBS-DOL.md row;
ROADMAP.md Phase 4 sequence; this entry. No code, no tests, no fixture, no
DOL. Future files and docs listed in the planned entry.

**Risks noted.** The first sustained loop (bounded); AUDIO overwritten under
lag (harmless here, visible in the cadence); a missed VIDEO block (flag
resync, gap recorded); the device possibly needing KEYPAD writes to keep
streaming (ends by T_DELIVERY — a finding); SD write ≈ 0.4 MB; capacity
ends the loop with the data kept; byte-0 extras never decide.

**Result.** GBP-VIDEO-001 DESIGNED — NOT IMPLEMENTED — NOT RELEASED. Stopped
for review.

## 2026-09-16 — GBP-VIDEO-001 specification review: operational success separated from the content oracle; 88 as capture target, complete interval = two consecutive boundaries; both frame-start predicates per block; explicit state machine, PI-latch policy, record reuse and hard runtime bound; analysis only

**Scope.** A targeted review of the design written earlier today
(HARDWARE_TESTS.md "Planned tests — GBP-VIDEO-001", VIDEO_PATH.md §5 / §8,
UNKNOWNS U-GBP-011 / 029). The static findings on GBI and the Disc stand
(no contradiction found). No implementation, no DOL, no hardware, no
commit.

**1. Success vs content.** The probe's status now derives only from
SERVICE (stable repeated service: one ISR entry per delivery, 0 reentry, 0
unexpected source, 0 uncertain writes, 0 DMA timeout / busy / error, every
serviced cycle's ACK and re-arm completed, INTMR13 = 0 in every main read),
CAPTURE (target_reached / delivery_cap / runtime_cap / no_next_cause /
early_failure) and RESTORE: `ok_video_sequence_capture`,
`ok_target_not_reached_delivery_cap`, `ok_target_not_reached_runtime_cap`,
`observation_no_next_cause`, or a failure. The comparison with the
embedded idle screen is an OFFLINE oracle (`tools/avseq.py`: matches_disc,
matches_gbi, first_mismatch_block, first_mismatch_offset, verdict
full_match / partial_match / mismatch / insufficient_data; reference data
read from the private inputs at run time, never stored). Non-matching bytes
are new evidence, not a failure.

**2. 48 / 88 corrected.** "48 = one frame + 8" was wrong: with an arbitrary
starting phase and the references' period of 40 (a hypothesis), the first
true predicate can come as late as block 40 and the next 40 later, so 80
blocks guarantee one complete boundary→boundary interval only if the
period is 40; 88 = target with 8 of margin; 48 guarantees at most one
boundary. Boundary result per predicate: count, positions[], intervals[];
COMPLETE_INTERVAL = yes iff two consecutive true predicates exist; N ≠ 40
is a result, 0 or 1 boundary leaves the objective unmet with the capture
operationally valid.

**3. Both predicates per block.** `raw_first4[4]` kept verbatim;
`gbi_frame_start = (u32_be & 0x80800000) == 0x80800000` (bytes 0 AND 1);
`disc_frame_start = ((u16_be >> 7) & 1) != 0` (byte 1, `FUN_8008A588`);
`flags_agree`; gbi ⇒ disc, so disc = 1 / gbi = 0 is the informative case
(byte 0 is where the variability lives, GBP-HW-061). Both stored in the
`OGBPSEQ1` VIDEO table; the offline tool keeps one boundary list per
predicate; none chosen silently; raw never corrected.

**4. State machine and PI latch.** S1 READ → S2 AUDIO → S3 VIDEO → S4 ACK →
S5 PICLEAN (≤ 1 main W1C, PI clear required) → S6 REARM → S7 WAIT (masked
read-only poll of INTSR13 until 1 or min(T_DELIVERY, remaining); no write;
timeout → `observation_no_next_cause`, nothing fabricated) → S8 PREPARE
(INTMR13 read 0; record consumed; record reset in memory only — never a PI
write; INTSR13 = 1 left intact) → S9 UNMASK (delivery inside the call) →
S10 CONFIRM (re-mask, INTMR13 read 0, fired == 1 / count == 1 / reentry ==
0 or stop). No W1C between S7 and S9; PI13 = 1 with an invalid source →
anomaly and teardown, never a W1C "to continue".

**5. Record reuse.** Invariants before every unmask: CPU masked (read),
previous record consumed, fired = count = reentry = 0, timestamps and
INTSR/INTMR fields zeroed, handler installed once and never re-installed
before the teardown, INTSR13 already 1 from a valid next cause; the
preparation writes only memory. Exclusive access follows from the mask
state, read before every access: the ISR runs only between __UnmaskIrq and
its own __MaskIrq; main touches the record only after its re-mask and an
INTMR read with bit 13 = 0.

**6. Runtime bound = HARD.** DEADLINE = t0 (first delivery) + 1000 ms,
wrap-safe; every wait runs to min(own timeout, remaining); an operation
starts only with remaining > 0; a started DMA completes under its own
timeout (the engine is never left busy); a cycle whose pending was read is
finished through ACK and re-arm; worst-case wall time ≤ MAX_RUNTIME + 4 ×
T_DMA = 1.8 s.

**7. Caps.** TARGET = MAX_VIDEO_BLOCKS = 88 (capacity, not hardware truth),
MAX_DELIVERIES 320; a cap before the target → `ok_target_not_reached_*`
with everything preserved, never a transport failure.

**8. AUDIO.** Always drained when selected; raw: first 8 successful drains +
last successful (ping-pong `audio_last[2]`, `last_valid` updated only after
a seen completion; a failed drain never overwrites or claims the last valid
capture); per cycle: selected / attempted / completed / rc / slot / CRC
(when completed).

**9–12.** Content oracle offline (above); color order stays CORROBORATED
and the promotion decision is post-run; result matrix SERVICE / CAPTURE /
BOUNDARIES_GBI / BOUNDARIES_DISC / COMPLETE_INTERVAL / REFERENCE_CONTENT /
RESTORE, always fully reported; fifteen mock scenarios listed for the
future tests (first-block flag, flag at 39, two flags 40 apart, ≠ 40 apart,
one flag, zero flags, Disc = 1 / GBI = 0, both 1, byte 0 altered only,
record reuse over ≥ 320 cycles, PI latch preserved, no main W1C between
next cause and unmask, delivery cap, runtime cap, last valid AUDIO
preserved after a failed drain).

**Docs.** HARDWARE_TESTS.md (entry rewritten), VIDEO_PATH.md §5 / §8,
UNKNOWNS.md U-GBP-011 / U-GBP-029, this entry. **GBP-VIDEO-001 SPEC
REVIEWED — NOT IMPLEMENTED — NOT RELEASED.** Stopped for review.

## 2026-09-16 — GBP-VIDEO-001 specification: MAX_RUNTIME_MS redefined as the service-loop admission budget; an admitted cycle is a bounded transaction; analysis only

**Inconsistency fixed.** The reviewed spec called MAX_RUNTIME_MS a "hard
wall-clock bound" while also requiring that a started DMA completes and
that a cycle whose pending was read is finished through ACK and re-arm —
ambiguous when the deadline expired between the AUDIO and the VIDEO drain
of a pending 0x0500. Final semantics (HARDWARE_TESTS.md "Planned tests —
GBP-VIDEO-001", supersedes the "hard bound" wording of the previous entry):

- **Admission budget.** MAX_RUNTIME_MS = 1000 ms limits the ADMISSION of
  new cycles: t0 = the first unmask of the loop, ADMISSION_DEADLINE = t0 +
  1000 ms (wrap-safe). CHECK_ADMISSION, before PREPARE / UNMASK of every
  cycle, requires remaining > 0, deliveries < MAX_DELIVERIES (320),
  video_blocks < TARGET_VIDEO_BLOCKS (88) and a latched cause; otherwise
  the loop ends normally (runtime_cap / delivery_cap / target_reached) and
  the teardown follows — no unmask, no new delivery, a latched cause is
  left for the teardown (next_cause_at_end = yes, deliveries unchanged). A
  next cause observed is not a cycle admitted.
- **Transaction.** Once the unmask ran and CONFIRM holds (fired 1, count
  1, reentry 0) the cycle completes in full — READ → AUDIO → VIDEO → ACK
  (the whole pending value, never partial) → PICLEAN → REARM — whatever the
  clock; each step keeps its own bound (DMA ≤ 200 ms, transfers ≤ 200 ms,
  ≤ 1 W1C, no retries); it ends only by completion or a real failure.
- **WAIT_NEXT** belongs to the cycle that re-armed: masked read-only poll
  to min(T_NEXT_CAUSE = 100 ms, remaining); a single read when remaining
  is already 0; the deadline arriving without a cause → runtime_cap with
  next_cause_at_end = no; a cause before the deadline stays latched and
  CHECK_ADMISSION decides. T_DELIVERY (100 ms) is kept only as the bound on
  the handler-entry wait after an unmask.
- **Bounded overrun** past the deadline = the one cycle in flight +
  WAIT_NEXT (never beyond the deadline) + teardown; counting every transfer
  at its 200 ms operational timeout (each would also be a failure): lean
  cycle ≤ 1.1 s, verify cycle ≤ 2.3 s, teardown ≤ 1.2 s, worst case ≈ 4.5 s
  wall time; typical overrun < 1 ms.
- **Caps.** MAX_DELIVERIES and TARGET_VIDEO_BLOCKS are evaluated at the
  same admission point; target reached → the final bounded WAIT_NEXT of
  the last cycle (an explicit observation, no unmask), then teardown; the
  AUDIO table is sized to MAX_DELIVERIES (no separate AUDIO cap).
- **Results.** CAPTURE gains next_cause_at_end; the example "cycle N
  completed, re-arm ok, next cause latched, deadline before the next
  UNMASK" is SERVICE ok / CAPTURE runtime_cap / next_cause_at_end yes /
  deliveries unchanged / teardown acknowledges — not a failure.
- **Tests added to the design:** deadline before the first new cycle;
  0x0500 with the deadline during AUDIO, between AUDIO and VIDEO, during
  VIDEO (VIDEO drained, ACK 0x8500, re-arm); next cause latched then
  deadline before UNMASK (no delivery, cause preserved); deadline during
  WAIT_NEXT without a cause; never a partial ACK; target reached with a
  cause latched after the last re-arm.

**Docs.** HARDWARE_TESTS.md (entry rewritten), this entry. No code, no DOL,
no hardware, no commit. **GBP-VIDEO-001 SPEC — ADMISSION BUDGET FIXED — NOT
IMPLEMENTED — NOT RELEASED.** Stopped for review.

---

## 2026-09-16 — GBP-VIDEO-001 implemented (not physically executed)

**Goal:** implement the repeated drained service designed and twice reviewed
earlier the same day, with no new initialization and no new ISR, and validate
it entirely without hardware.

**Result:** implemented. `GBP-VIDEO-001 IMPLEMENTED — NOT PHYSICALLY EXECUTED
— DIRTY BUILD, NOT A PHYSICAL CANDIDATE.` No hardware was run and none is
requested.

### What was built

| Piece | File |
|---|---|
| Sequence core: records, buffers, both predicates, boundary lists, compact log lines | `src/gbp/gbp_avseq.{h,c}` |
| `OGBPSEQ1` sidecar (format 1, independent of the v2 block sidecar) | `src/gbp/gbp_avseqdump.{h,c}` |
| The state machine: admission point, statuses, matrix, teardowns, summaries | `src/gbp/gbp_video_probe.{h,c}` |
| GameCube POC (`video-0001`, prefix `OPENGBP-VIDEO`) | `poc/gbp-video-capture-probe/` |
| Parser, listings, boundary lists, frame grouping, offline oracle | `tools/avseq.py` |

Reuse, not repetition: the 003A stage, the 003B extended one-shot handler, the
shared cycle service, `gbp_avblock` and the 003A teardown are all unchanged.

### Decisions taken during the implementation

- **The handler is installed once and its record reused.** A new transport
  operation `irq_record_reset` clears the shared one-shot record between
  deliveries — **memory only**; the real backend refuses it while INTMR bit 13
  reads 1 and when no handler is installed. Both ISR bodies came out
  byte-identical to the GBP-AV-SERVICE-001 build's, and the ISR audit reports
  CLEAN. The audit of the handler was the precondition for the whole design,
  and it held.
- **The delivery step was split** into a quiet variant (transport operations
  only) and a logging one. `gbp_irq_service_deliver` is now the two in
  sequence and is byte-identical to before: the physical 003B, 004 and AVSVC
  fixtures still replay unchanged. The probe calls the quiet variant only, so
  nothing is formatted between the unmask and the re-mask.
- **CHECK_ADMISSION had to move before the cycle record is bound.** The first
  version bound `cycles[n]` first and a full table therefore ended the run as
  `abort_capacity`; that is wrong — reaching the delivery cap is a normal end
  (`ok_target_not_reached_delivery_cap`). The 320-delivery test found it. A
  refused cycle now performs no record reset and no PI access at all.
- **Five compact records per cycle, not one.** The design said "one line per
  cycle"; five (`CYCU`, `CYCW`, `CYCH`, `CYCD`, `CYCR`) plus a `RAW READ-n`
  line for lean cycles carry every transport value, which is what lets a
  physical log regenerate a replay fixture. `tools/probelog.py` turns them
  into the same operation stream a verify cycle's detailed records produce and
  skips a verify cycle's compact records so nothing is emitted twice. Proven
  by the round trip, not by inspection.
- **Six IRQ-register write sites, not five.** The lean cycles write their ACK
  directly (no snapshot, no formatting), so the probe object has two sites
  (ACK and re-arm) beside the stage's three and the shared service's one. The
  audit pins six with the reason recorded.
- **The mock's "no main W1C between the re-arm and the next unmask" detector
  was wrong** and flagged the teardown's own legal W1C. The window now opens
  at a re-arm and closes at the next unmask **or at the next non-zero
  IRQ-register write** (the teardown's stop word).

### Validated without hardware

- C unit suite: 14 binaries, **19182 checks, 0 failures** (003A / 003B / 004 /
  AVSVC regressions unchanged).
- Python host suite: **235 passed, 0 skipped** (all audit listings generated).
- Static audits: `poc_audit --profile video` and `isr_audit` on both handler
  bodies — 0 findings; `avsvc`, `003b` and `004` still 0 findings.
- Docker build of all nine POCs, **zero warnings**; DOL padded, SHA-256
  recorded in the hardware-test entry.
- `make video-dolphin`: both runs abort in the 003A stage as designed
  (`abort_inconsistent` with no HSP device, `abort_control_shape` with
  Dolphin's GBPlayer model). Preconditions were not weakened for Dolphin.

### The physical AVSVC run is one cycle of this loop

The clearest validation available without new hardware: the physical
GBP-AV-SERVICE-001 fixture (2026-09-16, `avsvc-0001`, commit `d3a6d23`) is the
**exact prefix of cycle 0** of the repeated service. With `max_deliveries = 1`
it replays end to end — 132 operations consumed in order, 0 mismatches, 0
exhaustion, the physical blocks delivered from its sidecar, the second cycle
refused at the admission point, `next_cause_at_end = yes`, and the cause the
device left latched acknowledged by the teardown's single W1C. Every physical
number of that run (cause at 3391329164, entry at 3391371694, latency 72 ticks,
both block CRC-32s, the ACK `0x8500`, the re-arm, REARMPOST `0x0400`) is
asserted unchanged.

### The offline oracle is real, and it confirms the static reverse engineering

`tools/avseq.py oracle` implements GBI's per-block checksum exactly as
`VIDEO_PATH.md` §3.1 describes it: the repacked byte 1 : byte 3 words
accumulated in 64 bits, **stored as the low 32 bits plus the carry count**.
That last detail was recovered by the implementation — the naive low-32 sum is
short by exactly the carry count — and it makes the physical
GBP-AV-SERVICE-001 block produce `0x7F0FFF10`, the value §6 records as entry 0
of both of GBI's reference tables.

Read from the private inputs at run time (and never stored in this repository):
table A carries content in blocks 14–25, table B in 12–19, and the Disc's
embedded frame at `0x801B45A0` begins white. Three independent confirmations of
§2.4 and §3.3 straight from the binaries.

**No promotion.** None of this is a physical result for GBP-VIDEO-001. 40
blocks per frame remains a HYPOTHESIS, the colour naming remains CORROBORATED,
and the physical block format remains what the single AVSVC block showed.

**Next highest-value step:** a release audit on a clean commit (rebuild,
recorded DOL SHA-256, audits on that build) and then, if authorized, the
physical run — the first bounded sequence of the GBP video stream.

**Docs.** HARDWARE_TESTS.md (status and implementation notes), ROADMAP Phase 4,
VIDEO_PATH.md (experiment status), captures/README.md (the `OGBPSEQ1` sidecar
and the rule that no GBP-VIDEO-001 fixture may exist yet), tests/README.md,
tools/README.md, the POC README, this entry. No commit, no push.

---

## 2026-09-16 — GBP-VIDEO-001 physically executed and consolidated

**Goal:** run the released candidate on hardware and consolidate the first
physical VIDEO block sequence of the project.

**Result:** executed once, `ok_video_sequence_capture`, `capture=target_reached`,
`restore=ok`, `errors=0`. Build `video-0001`, clean commit `6930dde`, DOL SHA-256
`856d3e91…fd65`. Raw evidence preserved: log `ec3c366c…6527` (270 580 B) and
sequence sidecar `ce5134ff…e229` (403 948 B), both recomputed here and both
byte-identical in `captures/local/` and, for the sidecar, in `captures/fixtures/`.

### What the run settled

The repeated drained service is stable: **209 cycles through one installed
handler**, 209 unmasks / entries / ACKs / re-arms, 0 reentry, 0 unexpected
source, 0 uncertain write, 0 DMA failure. W1C: 209 ISR, **0 main**, 1 teardown.
232 whole-block DMAs moved exactly 927 744 bytes. That answers U-GBP-027 for a
bounded sequence (GBP-HW-062/063/064).

**One complete frame-start interval of exactly 40 VIDEO blocks** was captured
(seq25 → seq65), with GBI's predicate and the Disc's agreeing on **all 88
blocks, 0 divergences**. 40 blocks per frame moves from a constant read out of
two decompilations to CORROBORATED by hardware (GBP-HW-066). The frame took
680 138 ticks = 16.794 ms = **59.547 Hz**, made of 39 gaps of ~0.294 ms and one
closing gap of 5.335 ms spanned by exactly 22 consecutive AUDIO-only causes
(GBP-HW-067/068).

### The first interval of 25 is a startup transient, not a 25-block frame

The four VERIFY cycles cost 34 792 ticks each against 3 101 for a lean cycle.
The device's VIDEO block is single-buffered, so blocks produced while the probe
was still servicing were overwritten and never signalled. At the steady cadence
the first interval's time would carry ~37 blocks and 25 were captured — but the
interval is also *shorter in time* than a full frame, so "one frame minus 15"
does not fit either. The probe drained every source it saw (88/88/88): the loss
is on the device side and the log cannot pin the count. Opened as U-GBP-030. The
practical lesson for the next build: do not put the slow verify cycles at the
start of a capture.

### The reverse engineering checked out, and the AGB was showing white

Transforming our physical blocks by byte 1 : byte 3 and computing GBI's
per-block checksum reproduces the references' own all-white entries exactly —
`0xFF0FFF0F` (no flag) and `0x7F0FFF10` (with the flag), table A entries 1 and 0.
Aligned on the complete interval, the capture matches GBI table A at 28/40 with
the 12 mismatches **exactly at blocks 14..25**, table B at 32/40 with mismatches
**exactly at 12..19**, and the Disc's embedded frame at 28/40 with mismatches
**exactly at 14..25** — precisely the logotype blocks the static analysis
identified. So the geometry, the byte picking and the table layouts are all
confirmed, and the divergence is a **device-state** finding: the AGB was
displaying a blank white screen, not the boot logotype (GBP-HW-071, U-GBP-031).
Colour is untouched by this run: a uniform white frame carries no colour
information.

### Byte 0 narrowed considerably

Over 84 480 physical pixel words, byte 0 differs from byte 1 in **688**, always
`ff` against `7f`, never the reverse; byte 2 never differs from byte 3. The
exceptions **never** land on the first word of a 32-byte DMA line (0 of 10 560)
and sit at ~0.9 % on each of the other seven. Two physically independent captures
of the same block (this run's seq0 and the GBP-AV-SERVICE-001 block) have
different raw bytes and different exception counts yet **byte-identical byte 1 /
byte 3 payloads and the same GBI checksum**. The extras never reach what either
reference reads. The mechanism stays open (U-GBP-029); the 32-byte-line structure
points at the transfer path, which is a lead, not a conclusion. Nothing here
justifies calling it a DMA bug.

### Two defects found while consolidating

- **`tools/probelog.py` fabricated CRC-32 values.** 135 of the 144 AUDIO drains
  preserve no payload by design, and their cycle records carry `audio_crc32 = 0`.
  The fixture generator copied that zero onto the `B` line as if it were a
  measurement. It now emits a CRC only where one was actually taken: 88/88 VIDEO
  and 9/144 AUDIO lines, a blank field meaning "not measured". The same fix gave
  the four verify cycles' VIDEO reads their real CRCs (they were bare before,
  because the rule looked for an AVSVC-only `BLOCK` record); the new join is on
  the physical `t_start` of the transfer.
- **`finish()` summarises before it tears the hardware down.** 64.99 ms elapse
  between the last WAIT_NEXT and the teardown's first write, spent on CRC-32 and
  scans over 374 784 bytes plus 1 230 formatted records. The run is not
  invalidated — the cause stayed latched and the teardown succeeded — but the
  device sits in the experimental CONTROL state longer than it needs to. A
  future build should tear down first and summarise afterwards. Not changed now:
  altering the runtime during consolidation would invalidate the artefact this
  evidence belongs to.

Also noted: `tools/avseq.py oracle` aligns on the first boundary, so it used the
transient 25 interval and reported `partial_match`. The meaningful comparison is
the one above, aligned on the complete interval. The tool should prefer a
complete interval or accept an explicit phase — a follow-up, not a defect of the
run.

### Tests and fixtures

`captures/fixtures/hw-gamecube-gbp-2026-09-16-video-0001.gbpreplay` plus its
`OGBPSEQ1` sidecar replay the whole run: 0 mismatches, 0 exhausted, 232 bulk
reads, all 88 VIDEO CRCs verified, and **135 AUDIO reads reported missing**
because their payload was never preserved — never invented. Suites after the
consolidation: C 14 binaries / 20 789 checks / 0 failures; Python 239 passed, 0
skipped.

**Next highest-value step:** decide GBP-VIDEO-002. The uniform white frame means
a known-colour source is still needed for the colour question, but the transport,
the geometry and the frame structure no longer are. Not started here.

---

## 2026-09-16 — Phase 4 next step: the references' assets traced, GBP-VIDEO-002 designed

**Goal:** decide what follows GBP-VIDEO-001. The physical run captured a
uniform frame that matched both references exactly where they are background and
differed exactly where they hold a logotype. Before designing anything, find out
what those embedded assets actually are.

**Result:** the assets are recognition machinery, and the "divergence" is very
probably a timing artefact of our own capture window. GBP-VIDEO-002 is designed
as a long, low-memory scan. Nothing implemented, no hardware requested.

### The Disc's embedded frame is a comparison oracle

`0x801B45A0` has no data reference in the binary — it is the immediate
`-0x7FE4BA60` inside the video service loop. That loop converts each live block
into the frame buffer and then compares the converted block against the
reference at the same block index, 960 halfwords at a time. Forty consecutive
matching blocks set a "detected" flag. The reference is never drawn. When the
flag rises, the Disc drives bits `0xF0` of the KEYPAD register in a 5-on/5-off
cycle: it recognises one AGB screen in order to press buttons past it, and it
keeps the detector armed for 24 000 invocations of a 5 ms periodic callback, so
it plainly does not assume the screen shows up promptly.

Note for our own experiments: **no KEYPAD write is needed to reach that screen**;
KEYPAD is used only to dismiss it. GBP-VIDEO-001 already set CONTROL bit `0x08`
as part of the 003A transform, which is exactly what the Disc sets at session
start.

### GBI's two tables, and the fact they answer

Both tables are read from a single place each, inside the video service thread,
as 40-entry all-or-nothing comparisons against the run's per-block checksums.
Selection is by configuration, not content. Computing GBI's own checksum over
the Disc's embedded frame reproduces **39 of table A's 40 entries** — the one
difference being block 0, where table A carries the frame-start flag and the
Disc's copy does not. So the Disc's frame and GBI's table A are the same screen;
table B is a different one (content at blocks 12..19 rather than 14..25).

### The real reason our capture was uniform

Recomputing the timeline from the physical log: the capture spanned **39.2 ms,
about 2.3 frames, starting 107 ms after the CONTROL transform that starts the
AGB**. We looked very early and very briefly, at a device whose own driver is
prepared to wait two minutes for the screen in question. That reframes
U-GBP-031 from "the references describe a different state" to a timing question,
and it is the question GBP-VIDEO-002 asks.

I also corrected U-GBP-030. The previous wording said the block loss was "on the
device side"; the run does not show that. What it shows is narrower: the host
observed only 25 VIDEO blocks between the first two frame starts, during the
region where the four slow verify cycles run. Coalescing, an overwrite before
the drain, a startup transient and other behaviour are all still open.

### GBP-VIDEO-002: scan, do not hoard

Raw-capturing seconds of VIDEO is impossible — one second is about 9.1 MB. The
way through is the one both references already use: reduce each block to a
checksum. The design records checksum + flags + timestamp per block (12 bytes,
so a 65 536-entry ring covers ~27 s) and keeps raw bytes only for a baseline
frame, the first frames that differ from it, and a closing frame — three frames,
460 800 B. The checksum function is GBI's own and is already verified against
physical data.

Two deliberate changes from GBP-VIDEO-001, both from its own findings:

* **The verify cycles move out of the capture.** They cost 34 792 ticks against
  3 101 for a lean cycle and they sat exactly where the anomalous first interval
  appeared. The scanned interval must not contain a cycle 11× slower than its
  neighbours.
* **The hardware teardown runs first, summaries afterwards.** I audited the
  dependencies: `summarize()` reads only the store and the raw buffers,
  `log_lean_cycles()` reads only the cycle records and the two block addresses,
  and the teardown reads nothing either produces — so the reorder is safe. The
  one real coupling is the log order, because `tools/probelog.py` emits
  operations in record order; moving the per-cycle records after the teardown
  requires probelog to sort by the absolute timestamps those records already
  carry. That belongs to VIDEO-002, not to VIDEO-001's artefact.

### Why not go straight to a colour cartridge

Colour needs a source whose true appearance is known independently of the
references — a reference comparison can only show that two encodings agree,
never which channel is which. That is real, and it is designed as a follow-on
(GBP-VIDEO-003) with a concrete pattern requirement. But it should not come
first: our only physical frame is uniform, so a block reordering, duplication or
loss *inside* a frame would currently be invisible. A structured frame validates
that the capture preserves structure, and VIDEO-002 gets one without any new
hardware. Running a colour test on an unvalidated geometry risks reading a
geometry error as a colour error.

**Next step:** review the GBP-VIDEO-002 design, then implement it. No hardware
is requested until it is implemented, audited on a clean commit and authorised.

---

## 2026-09-16 — GBP-VIDEO-002 hardened before the checkpoint

**Goal:** make the scan design survive contact with the real time scale, and
fix an ambiguity I introduced myself.

**Result:** the envelope is proved rather than assumed, and it is **120 s, not
~400 s**. Several parts of the design changed as a consequence. Still nothing
implemented, no hardware requested.

### I had the detector window wrong

The previous entry said the Disc keeps its detector armed for "24 000 frames,
about 400 seconds". The 24 000 is real but it does not count frames. The counter
at `r13-0x7014` advances once per invocation of `FUN_8008B1AC`, and that function
is registered by `FUN_8008A930` through `FUN_80067F24` — which stores a period at
`struct+0x1C` and takes the callback as its seventh argument — with a period
computed from the bus clock as `((bus >> 2) / 125000) * 5000 >> 3`. At the
measured 162 MHz bus that is **202 500 ticks = 5.000 ms exactly**, so the window
is **120.0 s**. Corrected in VIDEO_PATH.md, UNKNOWNS, EVIDENCE (new GBP-VID-014)
and here. Good outcome: the target is half of what I claimed and the design gets
easier, not harder.

### What 120 s actually costs

From GBP-VIDEO-001's measured rates — 5 327 deliveries/s, 2 243 VIDEO blocks/s,
3 671 AUDIO blocks/s, 16.794 ms per frame — a 120 s run means about **639 000
deliveries, 269 000 VIDEO blocks and 7 150 frames**. A cycle record per delivery
and a log line per delivery are both out of the question. The store becomes
per-frame: 40 semantic checksums plus metadata, 192 bytes a frame, 8 192 frames
= 1.5 MB covering 137 s. Detailed records survive only for the first and last
few cycles, anomalies and preserved episodes.

### The time base was a real bug waiting to happen

A u32 tick counter at 40.5 MHz wraps at **106.049 s** — *inside* a 120 s run,
1.13 times. Every recorded timestamp becomes u64 from the 64-bit PowerPC time
base. The transport keeps its u32 `ticks` for the bounded per-operation waits,
where the wrap-safe difference is already correct and physically exercised; only
recorded timestamps change width. This gets an explicit test, including one that
fails if a u32 path sneaks back in.

### Other hardening

* **Segmentation on the Disc predicate**, with a physical reason rather than a
  preference: GBP-HW-070 found byte 0 disagreeing with byte 1 in 688 of 84 480
  words while byte 2 never disagreed with byte 3. Byte 0 is the unstable one;
  GBI's predicate uses bytes 0 and 1, the Disc's uses byte 1 alone. Both are
  still recorded and any disagreement is an event.
* **Baseline is learned, not assumed**: three consecutive complete 40-block
  intervals with identical checksum vectors. A structured frame arriving before
  that is kept as an early-change candidate, not discarded — VIDEO-001's first
  interval was exactly the kind of transient that would have poisoned a
  first-frame baseline.
* **Raw retention is whole frames, previous/trigger/next**, from a 3-slot ring
  of 48-block frames, and up to **three episodes** with a 30-frame separation —
  because the first difference may be only a transition and the stable screen
  may follow.
* **The checksum runs after REARM**, never between the DMA and the acknowledge,
  with the raw ring providing the double buffering. The ~20 µs estimate against
  a 294 µs block period is an estimate and the design says so: it must be
  measured before implementation. That is the VERIFY_CYCLES lesson applied in
  advance.
* **No private table in the runtime.** The console only decides "this frame
  differs from what this machine has been showing". Matching against the Disc
  and GBI tables stays offline.
* **Immediate teardown**, with the list of fields that must be snapshotted to
  RAM first, and a **monotonic sequence number** on every event so probelog can
  reconstruct the operation order once formatting happens after the teardown.
  Sorting by timestamp alone is not enough: two operations can share a tick.
* **Negative result is defined in advance.** Below 120 s, "no structured frame"
  is `insufficient_observation_window` and proves nothing. At or above it, it is
  a physical negative for that configuration, never a claim of impossibility.

Memory budget comes to about 4.87 MB of 24 MB, against 2.21 MB for
GBP-VIDEO-001 — a fourfold increase with over 19 MB left.

### Numbering audit

`GBP-VIDEO-003` existed only as a future roadmap bullet introduced in `bd841b6`;
it was never implemented, never executed, has no evidence ID and no executed-test
entry. Renumbering it to `GBP-VIDEO-004` was therefore legitimate. `GBP-VIDEO-003`
is now the colour experiment.

**Next step:** review this design, then implement it.

---

## 2026-09-16 — GBP-VIDEO-002 final correction before the checkpoint

**Goal:** close an inverted claim I wrote, and settle four design points that
were still soft.

**Result:** the design is corrected in six documents. Two of my own statements
are withdrawn. Still nothing implemented, no hardware requested.

### The 120 s bound was inverted, and the mechanism says so

I wrote that "skipped callbacks only delay the counter, therefore 120 s is an
upper bound". That is backwards: if skips prevent increments, reaching 24 000
takes *at least* 120 s.

The code settles it rather than the logic alone. `FUN_80067C4C`, the scheduler
insert, explicitly detects a deadline already in the past, divides the lateness
by the period and advances the next fire time by `(lateness / period) + 1`
periods. **Missed periods are dropped, never replayed — there is no catch-up.**
So the counter advances at most once per 5 ms and:

* nominal detector interval = 120.000 s
* minimum elapsed time to reach 24 000 = **≥ 120.000 s**
* actual wall time may be longer
* no upper wall-clock bound follows from the value 24 000 at all

Corrected in HARDWARE_TESTS, VIDEO_PATH, UNKNOWNS, EVIDENCE and ROADMAP — not
just retracted here, which was the other thing I got wrong last round.

### The checksum position was wrong too, and the references say where it goes

I had put the checksum after the re-arm to keep DMA→ACK short. Tracing GBI's
service thread in order: read IRQ (0xD00000) → ARQ read AUDIO → ARQ read VIDEO →
**ACK**, the 64-byte write at 0xCFFFE0 that spans the end of the KEYPAD window
into the IRQ window → conversion and per-block checksum → at block 0x27 the
40-entry table comparison → **RE-ARM** at 0xD00000, the last device access of
the pass.

So GBI does the work *between* the ACK and the re-arm. The Disc does not
serialise it at all — its compare lives in a thread fed by a queue. GBI is the
only reference with a single serial path, so it is the one that maps onto our
probe, and GBP-VIDEO-002 now does the same:

```
READ → AUDIO → VIDEO DMA → ACK → PICLEAN → checksum → REARM → WAIT_NEXT
```

This is also the safer position on its own terms: the re-arm is what invites the
next cause, so deferring it defers the next cause instead of leaving one latched
while we hash. GBP-VIDEO-001 showed a cause can latch almost immediately after a
re-arm, which is exactly the risk my previous position carried.

### The 30-frame cooldown could have hidden the answer

"Up to 3 episodes separated by 30 frames" would open an episode on a transition
frame and then skip the stable screen arriving two frames later. Replaced by a
state machine: ARMED → CHANGED → STABILISING → CLOSED, where a signature
repeating three times marks the state stable, one raw frame of it is preserved,
and the episode closes and immediately re-arms against its own final signature.
`N_STABLE = 3` is the same evidence threshold the baseline uses, so "stable"
means one thing in both places. A hard cap of 60 frames closes an episode that
never stabilises, so nothing is unbounded.

### Smaller things now pinned

* **Time base**: the mechanism is named — TBU/TBL/TBU with retry, which is what
  libogc2's `gettime()` does — and monotonicity across the low-word carry follows
  from the retry itself. u32 deltas stay legal for the short per-operation waits,
  and that contract is written down rather than implied.
* **Signature**: byte 1 and byte 3 only. Byte 0 is never read, so the 688
  exceptions GBP-HW-070 measured cannot forge a structured change — a property of
  the algorithm, not a tuning choice. The frame-start bit is inside the checksum
  by construction and, since block 0 always carries it, cannot by itself mark a
  frame changed.
* **Frame store** grows to 16 384 entries (3.00 MB, 275 s). At 8 192 the cap was
  likely to be the stop; now it is a backstop. Filling it stops the run cleanly
  with `frame_store_cap`, no overwrite and no wrap, and the negative-result
  classification keys on **elapsed valid observation**, never on which cap fired.
* **Sidecar is streamed**: the file is ~5.5 MB, written in 64 KB chunks with a
  running CRC after the teardown. No second full copy in MEM1 — the old 0.25 MB
  "staging buffer" obviously could not have held it.
* **Save is separate from hardware**: `hardware_result` and `save_result` are
  reported independently, a partial save names the sections written, and there is
  never an automatic re-run.
* **Checksum cost** gets a measurement plan (min/median/p95/max over ≥10 000
  blocks) and a review trigger stated in advance: p95 above 25 % of the median
  lean-cycle duration sends the position back for revision before any hardware
  request.

Memory comes to ~6.71 MB of 24 MB, ~17.3 MB free.

**Next step:** review this design, then implement it.

---

## 2026-09-16 — GBP-VIDEO-002: the stop condition made explicit, the 25 % gate withdrawn

**Goal:** close the last two ambiguities before the checkpoint. Nothing
implemented, no hardware requested.

### Where the 120 s start, and when the run ends

The target was stated but its starting point was not. It is now
**MIN_VALID_OBSERVATION = 120.000 s accumulated after baseline_valid**, not from
capture start. The reason is what the negative claim actually asserts: "a
structured state did not appear during a valid window of comparison". Before
baseline_valid there is no reference to compare against, so that time cannot
support the claim.

This means our window is **not placed where the Disc's is** — the Disc arms its
detector at session start because it does not learn a baseline, it has the
reference embedded. I wrote that difference down rather than papering over it.
Pre-baseline frames are not lost: they are recorded in full with a flag, and one
that differs from its neighbours opens an EARLY_CANDIDATE episode with raw
frames. An early screen is still captured as evidence; it just does not count as
negative evidence.

The stop condition is now a normative ladder — fatal error, positive episode,
temporal target, frame store, event store, safety budget, no next cause — and it
answers the case I had left open: if an episode is **open** when the target is
reached, the run does not cut mid-episode. It runs a bounded finalisation tail
governed by the EPISODE_MAX_FRAMES = 60 cap already defined, opens no new
episode, reports tail_frames separately, then tears down.

I also added the three clocks explicitly (capture_elapsed, baseline_elapsed,
valid_observation_elapsed, all u64) and a deliberately conservative anomaly
policy in three classes: a frame-invalidating anomaly excludes that frame's
duration, a resync pauses the clock until a clean complete frame returns, and
the existing fatal set ends the run. When in doubt the time does not count, so a
negative result can only understate the observation.

### The 25 % threshold is withdrawn

I had required "checksum p95 below 25 % of the median lean cycle". That number
had no physical basis — nothing in the evidence makes 25 % meaningful rather
than 15 % or 40 %, and inventing a gate is worse than having none because it
looks like a measurement.

What replaces it is a measurement and a comparison, both mandatory before a
physical candidate: the per-block cost as min/median/p95/max over at least
10 000 blocks, on host and on the built DOL; and the same synthetic scenario run
**with and without** the checksum, comparing service cadence, VIDEO and AUDIO
block rates, the ACK-to-REARM interval, next-cause timing, the latched interval
and any change in timeout or reentry behaviour. The gate is a review gate: the
report accompanies the release audit and no candidate ships while any of those
quantities has moved in a way the reviewer has not examined and accepted.

### Smaller consequences

* The frame store is now described as **capacity, not a temporal target**. Its
  ~275 s exist for baseline acquisition, cadence variation, incomplete intervals,
  the episode tail and structural margin. If it fills before the target the
  result is `ok_no_change_inconclusive`, and the classification always keys on
  valid_observation_elapsed rather than on which cap fired.
* A **wall-clock safety cap is kept**, with a concrete justification rather than
  habit: because valid_observation_elapsed only advances while the stream is
  interpretable, a pathological stream could accumulate 120 s arbitrarily slowly
  while the store fills slowly too, leaving the run with no guaranteed end. It is
  labelled a safety cap and never "the official window".
* **Positive stop** is defined: change detected, stabilised at N_STABLE, every
  owed raw frame preserved, episode closed, nothing mandatory outstanding. An
  episode that closed `unstable` at the 60-frame cap is explicitly not a positive
  stop. A positive stop stands independently of any private comparison; offline
  decides which screen it was.
* `ok_no_change_short_run` is renamed `ok_no_change_inconclusive`, because the
  run may be long and still inconclusive if a cap fired first.

Test list grew to 25, including the target reached with an episode open, the
bounded tail, the clock starting only at baseline_valid, an anomalous frame not
counting as negative evidence, and a benchmark test that asserts the report is
complete rather than that a number is below a constant.

**Next step:** review this design, then implement it.

---

## 2026-09-16 — GBP-VIDEO-002 closed: the safety limit fixed, the early stop removed

**Goal:** resolve the last two normative ambiguities. Nothing implemented, no
hardware requested.

### The hard wall-clock limit

**HARD_WALLCLOCK_LIMIT = 180 s = 7 290 000 000 ticks**, counted from
`t_control_transform` — the CONTROL write `0x90 → 0x8C` that starts the AGB.
That epoch rather than the first unmask, because a *safety* bound should cover
the whole time the device is out of its idle state, including the 003A cause
wait of up to 2 s.

The value is an experiment-safety policy and is **not** derived from the 24 000
callbacks. The reasoning is a three-way separation:

| scenario | what stops it |
|---|---|
| normal run | the scientific target at ~126 s, neither cap fires |
| slow-clock pathology | the 180 s safety cap |
| fast-frame pathology | frame_store_cap |

Normal worst case is baseline (5 s generous) + 120 s target + 1 s tail = 126 s,
so 180 s leaves +54 s of margin, and it sits at 65 % of the frame store's ~275 s
of capacity. Incidentally 7 290 000 000 does not fit in 32 bits, which is an
independent confirmation that the u64 base is mandatory and not merely tidy.

If the safety cap fires before the target, the result is
`ok_no_change_inconclusive` with stop reason `safety_budget` — never
`nominal_negative`.

### The early positive stop is gone

The conflict was real and I had created it. The runtime holds no oracle, so it
cannot know that the first stable changed state is the one the experiment is
about. Concretely: baseline uniform → an intermediate stable screen → the
expected screen twenty frames later. Stopping at the first stable state would
have preserved the intermediate screen and lost the one we came for.

I looked for any oracle-free condition that could justify an early stop and
found none worth having. "Stop on the first stable change" fails the case above.
"Stop at MAX_EPISODES" is a capacity condition wearing a scientific hat.
"Stop when a frame has content in the block range the references use" is the
private layout smuggled into the runtime. "Stop when the block checksums look
diverse" is an arbitrary heuristic that would fire on noise and still could not
tell the two screens apart. So **there is no early positive stop**: the probe
runs to the target, a cap, or a failure, and every episode is classified
offline. That is the outcome that gets the most out of one physical run.

### Consequences

* **MAX_EPISODES = 4**, up from 3, for a named reason: the scenario that removed
  the early stop needs two episodes, and VIDEO-001 showed an early transient that
  can consume one, so four leaves a spare. 4 preserved raw frames per episode ×
  48 × 0xF00 × 4 episodes = 2.81 MiB.
* **Filling the episode raw store does not end the run.** `episode_store_full`
  is set, raw preservation stops, and signature monitoring continues, counting
  `episodes_not_preserved`. The signatures are themselves primary evidence —
  GBI's table comparison is a checksum comparison — so an unpreserved episode
  still yields a comparable vector offline; only pixels are lost. Ending the run
  there would discard the remaining signature evidence for no safety benefit.
  No episode is ever overwritten.
* **Two signatures, kept apart**: `original_baseline_signature` is fixed at
  baseline_valid and never overwritten; `current_reference_signature` advances to
  each closed episode's final stable signature, so a second transition is detected
  relative to the state the device actually settled into.
* **STRUCTURED_CHANGE is no longer a boolean**: status plus episode_count,
  stable_episodes, unstable_episodes, episodes_not_preserved, and the
  episode_store_full / truncated_by_safety / tail_truncated_by_cap flags. An
  episode means "a change relative to the reference signature of the moment",
  never "the official frame was found".
* **Precedence is explicit**: fatal error > safety budget > store caps >
  scientific target > no_next_cause > delivery guard. The safety cap wins over an
  open episode's finalisation tail, because a hard cap extendable by 60 frames
  would not be hard. A store cap during a tail sets `tail_truncated_by_cap` and is
  not a fatal error.

Memory comes to ~7.41 MiB of 24 MiB, ~16.6 MiB free. The sidecar is ~6.3 MiB and
is streamed, never resident. The test list is now 32 items.

**Next step:** review, then implement.

---

## 2026-09-16 — GBP-VIDEO-002 implemented (NOT physically executed)

**Goal:** implement the long-duration VIDEO state scan from the design that was
closed the same day, reusing the physically validated interrupt path unchanged.

**Result:** implemented and fully covered on the host.
`poc/gbp-video-state-probe/` (Test ID `GBP-VIDEO-002`, Build ID `vstate-0001`)
builds with zero warnings in the pinned container, passes every audit and both
Dolphin gates. **No hardware has run it. No physical evidence exists for it.
DIRTY BUILD — NOT A PHYSICAL CANDIDATE.** Phase 4 stays IN PROGRESS and no
claim anywhere was promoted.

### What was built

The experiment is GBP-VIDEO-001's loop run for two to five minutes instead of
39 ms, so four things changed and nothing else:

1. **A 64-bit time base.** 2^32 ticks = 106.049 s at 40.5 MHz, shorter than the
   120 s scientific target, so every persistent timestamp is u64. The mechanism
   is libogc2's `gettime()`, chosen because its source really is the required
   `mftbu / mftb / mftbu / cmpw / bne` loop — verified by reading it, not
   assumed from the name — and the composition and retry rule lives in
   `src/common/gbp_time64.c` as a pure function so the host can test it across
   the wrap `0xFFFFFFFF -> 0x00000000`. Short per-operation waits keep the
   32-bit operation, where a wrap-safe difference is exact and already
   physically exercised.
2. **Per-frame evidence instead of per-delivery records.** About 639 000
   deliveries are expected; the store is 16 384 frames of 40 semantic
   signatures (192 B each, 3.00 MiB), a bounded event store, and detailed cycle
   records only for the first eight cycles, the last eight, anomalies and the
   cycles inside a preserved episode.
3. **State detection with no oracle in the runtime.** A learned baseline (three
   consecutive identical complete frames), then an episode state machine over
   signature changes. No reference table, checksum, pixel or block range is
   embedded anywhere; `tools/vstate.py oracle` does the comparison offline from
   the private inputs.
4. **The teardown runs first.** GBP-VIDEO-001 summarised before tearing down and
   put 64.99 ms between the last observation and the CONTROL restore. Here the
   order is stop -> minimal RAM snapshot -> hardware teardown -> only then
   summaries, checksums, formatting and the save, and a test asserts it at the
   hardware moment by watching the CONTROL write.

### What was deliberately NOT changed

The interrupt path. `make vstate-audit` diffs both one-shot handler bodies
against the build GBP-VIDEO-001 executed physically and reports them
**byte-identical**: 82 instructions, one `__MaskIrq` call, one INTSR store of
0x2000 after the mask, no INTMR store. One `__UnmaskIrq` call site,
`IRQ_Request` only from the install/restore pair, the same three INTSR store
sites. Any change there would be a blocker for review.

### Decisions the design left to the implementation, recorded rather than hidden

* **Three AUDIO raw buffers, not two.** The design's budget line says "first +
  last, 2 x 0x1000", but two buffers cannot satisfy that same section's rule
  that a failed drain never overwrites a valid capture, because a drain writes
  before its status is known. The first slot plus a ping-pong pair costs 12 KiB
  and still rounds to the same 0.01 MiB.
* **An early candidate consumes at most one episode descriptor.** Preserving
  every differing pre-baseline frame could exhaust all four before the baseline
  exists and leave none for a real episode. The first keeps its raw; the rest
  are counted.
* **"No boundary within 48 blocks" also pauses the scientific clock.** The
  design classifies it as frame-invalidating (class a); it also leaves the
  assembler without an anchor, so the region anomaly is raised too. That is the
  direction the design's own principle requires — when in doubt the time does
  not count — and both counters are incremented, so neither reading is hidden.
* **Seven IRQ-register write sites, not six.** GCC duplicates the single re-arm
  statement across the verify branch; the disassembly shows `li r7,0` at both
  copies, so both write 0x0000. Pinned by the audit profile.

### Measured, not predicted

| Quantity | Value |
|---|---|
| text + data | 0.41 MiB |
| evidence stores | 6.602 MiB (frames, events, ring, episode raw, AUDIO) |
| all probe statics | 6.929 MiB, zero overlaps, every DMA target 32-byte aligned |
| MEM1 headroom | 16.449 MiB (the design predicted ~16.6 MiB) |
| log lines before the teardown | 214, constant from 200 to 200 000 deliveries |
| full synthetic scan | 798 640 deliveries, 399 321 VIDEO blocks, 9 983 frames |
| valid observation in that scan | 120.0 s, crossing the 32-bit tick boundary |
| sidecar in the synthetic runs | ~1.4 MiB, streamed in 64 KiB chunks, never staged |

### The signature cost, measured rather than thresholded

Section 8 of the design requires a measurement and a with/without cadence
comparison, and explicitly forbids the arbitrary 25 % gate it withdrew. Both run
in the suite. On the host, over 20 000 blocks: min 260 ns, median 263 ns, p95
271 ns, max 4 489 ns, taken from the bounded 1 KiB histogram and never from the
mean. With and without the signature over the same 4 000-delivery scenario: the
delivery, VIDEO and AUDIO counts are identical, ACK -> REARM grows by 18 mock
ticks, and REARM -> next cause and cause -> ACK do not move at all — the cost
lands exactly where GBI puts the equivalent work. **Host and mock figures, not
hardware ones.** The physical half needs a real run; the probe already records
sig_ticks per cycle and the four quantiles in the sidecar header.

### Tests and audits

C: 17 binaries, 691 801 checks, 0 failures — including the existing physical
fixture replays (003A, 003B, 004, GBP-AV-SERVICE-001, GBP-VIDEO-001), which are
unchanged. Python: 260 passed. `make vstate-audit`: 0 findings.
`make vstate-dolphin`: both runs abort in the 003A stage exactly as every probe
since GBP-INIT-003A, without reaching a CONTROL or IRQ write, the handler
install, an unmask or a whole-block read — the long scan is never entered, and
no precondition was weakened to make Dolphin pass.


### Microaudit of the dirty implementation (same day)

Six defects, all small, all fixed, none structural — and all the same mistake in
different clothes: **a derived or reconstructed value reported as if it were
measured**. The safety epoch was fabricated ~25 s into the future when the stage
aborted before the CONTROL write; the reconstruction had no runtime check, only
an argument; `capture_elapsed` was computed from a start that never happened and
printed the absolute time base as a duration; `gbp_replay_transport()` left the
newly added `ticks64` operation indeterminate because, unlike the other two full
constructors, it never zeroed the struct; one log line was still formatted
between the stop decision and the first teardown write; and a comment claimed the
delivery guard had three orders of magnitude of margin when it has a factor of
two to three (three orders of magnitude is the margin of the u32 *type*).

The epoch now has a **measured bracket** rather than an argument: two real u64
reads are taken around the stage and the reconstruction must land between them,
falling back to the earlier end — which over-counts the safety budget rather than
under-counting it. The window is independently bounded at 12 transfers with no
polling loop, a 2.4 s worst case against the 106.049 s at which a 32-bit
difference could go ambiguous.

What the audit confirmed rather than changed: the interrupt path is still
byte-identical to the physically executed GBP-VIDEO-001 build; the five stop
conditions are all evaluated at the admission point and nowhere else;
`episode_store_full` is a flag and never a stop reason; every byte of the sidecar
contract is CRC-protected and a truncated file is always rejected; the capture
path cannot reach the filesystem; no private reference address appears in the
DOL; and the log holds 214 lines at teardown whether the run served 200 or
200 000 deliveries.

### New unknowns

None. U-GBP-030 and U-GBP-031 stay open and are what the physical run would
address.

### Next highest-value step

A physical GBP-VIDEO-002 run, once the tree is committed clean, rebuilt,
release-audited and explicitly authorized. Until then nothing here is evidence.

---

## 2026-09-16 — GBP-VIDEO-002 executed: the screen is real, and the service aborted on one register read

**Goal:** run the long VIDEO state scan on the physical Game Boy Player, no
Game Pak, and find out whether a structured frame ever reaches the stream.

**Result:** the screen is there, and it is GBI's table B. The service aborted
before the scientific target.

### What the run found

The stream was uniform white for 0.48 s, changed structurally at **frame 30,
0.5014 s after capture start**, animated through 156 distinct signature vectors
for about three seconds, and settled into a state it held for **274 consecutive
frames, 4.582 s**. That settled vector matches **GBI reference table B in all
forty blocks**. It matches neither table A (28/40 at best) nor the Start-up
Disc's embedded frame (27/40).

Reconstructing the preserved raw frames the way both references read them —
pixel = byte 1 : byte 3, bit 15 the frame marker, 4 lines of 240 pixels per
block, 40 blocks — produces a **legible animated GAME BOY logotype at
240 × 160**. That is what promotes the geometry from "the references' constants"
to a physical fact: no wrong line count, pixel count, block order or byte pick
produces readable text.

**The design decision that removed the early positive stop is now validated by
hardware.** Five intermediate states were stable by the probe's own threshold of
three identical frames, each lasting 45 to 78 ms, all differing from uniform in
blocks 12..19, and **none of them matching table B**. A probe that stopped at the
first stable state would have captured an animation frame and missed the screen
it was built to find, by about half a second.

### What went wrong

At cycle 51 750 of 51 751 the two semantic readings of the 32-byte IRQ register
disagreed and the probe stopped. The ISR, the PI and the transport all behaved
normally; only the interpretations differed. The Disc reading takes bytes 0x1D
and 0x1F, GBI's takes a majority vote over eight replicas, so the last replica
differed from the majority on a byte both programs consume.

**The offending bytes were not preserved.** That is the single real defect this
run exposed, and it is an instrumentation defect, not a transport one: the cycle
record holds `pend=0000` and no payload, so the two conflicting values are
unrecoverable. U-GBP-032 is open and is deliberately narrow: nothing is assumed
about what the bytes were.

Context that does not close it: across the 353 IRQ-window reads whose bytes any
physical log has ever recorded there are 220 byte-level deviations from the
majority replica, and **every one landed on a byte neither reading consumes**.
Two are in this run's own log. Deviations there are ordinary and have always been
absorbed; this is the first one that appears to have reached a consumed byte. But
only 29 of this run's 51 751 reads were logged, so that says nothing about a rate.

### What held up

Everything else. 51 751 cycles on one installed handler with 0 reentry, 0
main-loop W1C, 0 timeouts, 0 uncertain writes, 0 counter overflows. Both
frame-start predicates agreed on all 19 513 blocks. The episode raw store filled
after four episodes and the monitor kept running, classifying all nine, never
overwriting one, with all 600 preserved blocks reproducing their signatures
exactly. The teardown after the failure reached the same final device state as
GBP-VIDEO-001 and GBP-AV-SERVICE-001. The 2.4 MB sidecar streamed out after the
teardown with both CRCs verifying. The log used 621 of 1024 ring lines.

And the signature cost is now a physical number: **19.2 µs per block**, 0.121 %
of a frame period, against a pre-run estimate of "about 20 µs". The histogram's
median and p95 are bucket upper bounds with 1.58 µs resolution and are reported
as approximations, not exact quantiles.

### What this does not settle

**Colour.** The logotype pixels are all of the form `xx1f`: one channel
saturated, one zero, one ramping. Under the references' reading that is indigo;
under the GBA-native order it is crimson. There is no pixel-level asset for table
B — only checksums — and a checksum cannot resolve a channel permutation, because
it is computed over the same bytes either way. The colour order stays
CORROBORATED and GBP-VIDEO-003 with a known-colour source is still required.

### Next

Preserve first, then decide. The next run must record the raw bytes and both
values of any semantic disagreement before it tears down. Whether a disagreement
should stay fatal is a separate question that should not be answered before one
has been captured.

---

## 2026-09-16 — U-GBP-032 instrumented: the bytes will be kept, the question is not answered

Goal: make the next physical GBP-VIDEO-002 run able to explain the abort that
ended the first one, without changing anything the first one observed. Build
`vstate-0002`. Not executed on hardware.

### What was added

One 96-byte record in `struct gbp_vstate`, written at the instant a semantic
disagreement is detected, from the buffer the transport had already filled. It
holds the 32 raw bytes verbatim plus what describes that read: both conflicting
16-bit values, which of the two read sites saw it, the cycle, the 64-bit
timestamp, the frame index and block-in-frame, INTSR at ISR entry and after the
W1C, INTMR at entry, the IRQ latency, the transfer's ticks and polls, the DMA
status before and after, and the expected CONTROL shape. The first disagreement
wins; later ones increment a counter and change nothing.

Both detection sites are covered: the verify path inside `common_checks()` and
the lean READ path, which uses its untouched 32-byte stack local. The capture
happens before any formatting and before the teardown, because that is the only
point at which the bytes still exist.

### What deliberately did not change

The disagreement is still fatal at the same point. No retry, no re-read, no
second opinion, no masking of the condition, no extra access to the device. The
experiment, caps, admission rule, service cycle, stop precedence and teardown are
untouched, and the interrupt path stays byte-identical to the GBP-VIDEO-001 build
that was physically validated — `make vstate-audit` diffs both one-shot bodies
against that build's and reports "identical". A host run with the capture armed
produces an operation stream identical, operation by operation, to one with the
disagreement armed past the end of the run: 1 031 operations compared, 0
differences.

Cost: 96 bytes of .bss and nothing on the normal path. `struct gbp_vstate` goes
from 4 152 to 4 248 bytes, and it is the only `.bss` symbol that moved.

### The sidecar

OGBPSEQ1 **v3**: v2 plus one section, every existing offset unchanged, the new
section under the same CRC, three header fields taken from v2's reserved area.
v2 is frozen and stays readable — the physical file of this morning parses with
the same header and total CRCs — and the two versions are dispatched explicitly,
so neither can read the other's file by accident. `tools/vstate.py diag`
recomputes both readings offline from the preserved bytes, checks them against
the stored values, lists the eight replicas and names which ones differ and on
which offsets. Run against the physical v2 file it says plainly that this format
did not preserve the bytes.

### Tests

609 C checks and 272 Python tests pass. The new ones pin the two readings against
each other (including the fact that a majority tie at four resolves to 0, so the
GBI value need not equal any replica), prove that the historical deviations on
offsets ≡ 0 and ≡ 2 mod 4 cannot produce a disagreement, prove the 32 bytes reach
the sidecar byte-identical, prove first-wins, prove operational equivalence, and
prove all 96 bytes of the record are CRC-covered. Every static audit profile
passes and all 19 Dolphin scenarios pass.

### What this does not do

It does not explain the disagreement, and nothing here should be read as
narrowing it: no cause is assumed, no value is reconstructed, and whether a
disagreement should stay fatal is still undecided — that question should not be
answered before one has been captured. The build is dirty and is not a physical
candidate. U-GBP-032 remains OPEN.

### Next

A clean commit, a rebuild, the release audit, and only then the authorization for
a physical run. If that run reproduces the event, the record explains it; if it
does not, the unknown stays open, because absence in one run is not an answer.

---

## 2026-09-17 — microaudit of the U-GBP-032 instrumentation: two parser defects, and the abort path proved identical

Goal: decide whether build `vstate-0002` is observational in fact and not only by
intention. Nothing was implemented; two defects were fixed and the weak parts of
the evidence were replaced by measurements.

### What the audit proved that the implementation had only asserted

The disagreement path of `vstate-0002` is not merely "semantically equal" to
`vstate-0001`: it is **operationally identical**. The same scenario was run
against both builds — the committed one in a throwaway worktree at `80c356f`,
the instrumented one here — and every quantity matches: 44 IRQ-window reads, 306
recorded device operations, 38 bulk reads, 41 IRQ writes, 160 transfers, 20
deliveries, 19 ACKs, 19 re-arms, the same status, the same reason string, and
the same 306-operation stream (kind and address) byte for byte. Those numbers
are now pinned in the test instead of the bound that was there before, which
accepted any read count at or above the delivery count and therefore tested
nothing.

At machine level the capture contains exactly two calls: the 64-bit time base
and the store function. The store function has no relocations at all — the
32-byte copy was inlined. There is no MMIO, no DMA, no PI access anywhere in it.

### The two defects

Both are the same kind: the C and the Python parser of one format disagreed
about what a valid file is.

1. A v3 diagnostic record whose reserved word is not zero was **accepted by C and
   rejected by Python**. The format's rule everywhere else is that reserved means
   zero, so C now refuses it too (`-8`, the code it already used for the header's
   reserved area).
2. With no record present, C accepted `diag_rec_size` of 0 or 96 and refused
   anything else, while **Python accepted any value**. Python now applies the same
   rule.

Neither can change the hardware build, and the rebuild proves it: the linker
drops both parsers from the DOL — they are in `gbp_vstatedump.o` and absent from
the ELF — so the DOL is bit-identical to the one built before the fixes, SHA-256
`6f2f6b2c…6fe1`, 433 376 bytes.

### What was added to the evidence

The majority rule is now checked exhaustively on both sides: all 256 ways the
eight replicas can carry a bit, for all 8 bit positions, against "strictly more
than four". The 220 historical deviations are covered by an exhaustive
perturbation of every discarded byte over all 256 values — 4 096 cases, none of
which moves either reading. The 32 bytes are followed from the capture entry
point through the serializer, the C parser and into `tools/vstate.py` with 32
**distinct** values, so a transposition would be visible; that file also carries a
timestamp past the 32-bit wrap. The attempt counter is driven to 65 539 calls and
saturates at 65 535 without wrapping, with the first record untouched. A card
that fails before the diagnostic section reaches it yields a partial save, an
intact result in RAM and a file the strict parser refuses. And every structural
tampering — `off_diag`, `diag_count`, `diag_rec_size`, the record's reserved
word, the version field — is refused **with both CRCs recomputed**, so only the
rules can be doing the refusing. The same applies to a record whose persisted
`disc_value` or `gbi_value` was altered with valid CRCs: the tool recomputes from
the bytes and reports the inconsistency rather than printing the stored value.

### Unchanged

The ISR and both one-shot bodies remain byte-identical to the physically
validated GBP-VIDEO-001 build. The frozen v2 sidecar still parses with header CRC
`947083c4` and total CRC `9bef714b` over 2 432 396 bytes. The transport, the
mocks and the GBP-VIDEO-001 format are untouched. 19 Dolphin scenarios pass and
both vstate runs still abort at the stage-A gate without reaching the
experimental path.

U-GBP-032 remains OPEN. The build is dirty and is not a physical candidate.

---

## 2026-09-17 — GBP-VIDEO-002 vstate-0002 executed: the bytes are in hand, and the policy question is now answerable

The instrumented build ran and the event it was built to catch happened on the
first attempt, at cycle 517 of 518, 0.0842 s into the capture. The diagnostic
objective **succeeded**; the service abort is the same abort as before and is not
a failure of this experiment.

```text
raw 32 bytes   01 01 01 00 ×7  then  05 05 05 00
semantic       0100 ×7  then  0500
Start-up Disc  0x0500      GBI majority  0x0100      XOR  0x0400 = AUDIO source
```

Everything was recomputed from the log and the sidecar, independently of the
run's own summary, and the two channels agree byte for byte. Evidence
GBP-HW-088…097; the run is in HARDWARE_TESTS.

### What the bytes settled

The eighth group is **not damaged**. Its first three bytes moved together exactly
as every other group's do, and its fourth byte is `00` like all the others. That
rules out, by observation rather than argument, the one-bit flip and the torn or
garbled byte that U-GBP-032 listed and refused to choose between. What the read
returned is eight well-formed replicas carrying two different values.

It also turns out a block was **already** known not to be one instant's snapshot,
in this very run: on windows reading `0x0500`, the byte at `4k+2` — which neither
reference consumes — takes different values in different groups of the same read,
with no monotone order (`04 05 05 05 05 04 00 05` is one of five such blocks,
GBP-HW-093). The fatal read is the first time that non-uniformity reached a byte
somebody reads. U-GBP-029's byte-0 extras are very likely the same phenomenon.

U-GBP-032 is answered. The mechanism is now U-GBP-033, and it is open: the timing
does not decide it. The transfer is 0.84 µs against a ~142 µs mean interval
between causes, and the AUDIO cadence of the same window puts the next AUDIO
34–70 µs *after* this read rather than during it — so "the source changed inside
the transfer" is a hypothesis the data neither supports nor refutes, and the
physical fill order of the window has never been established.

### The measurement that changes the policy discussion

Timing the re-arms of this run produced something the design had reasoned about
but never observed (GBP-HW-096): **a source bit that is not in the ACK value
survives, and fires again within 1.8 µs of the re-arm.** Cycles 5 and 7
acknowledged AUDIO only (`0x8400`) and the next cause arrived 74 ticks later,
carrying VIDEO — **134 to 153 times** faster than the shortest observed AUDIO
gap in the same window (9 885 to 11 303 ticks against 74), about 2.1 orders of
magnitude — far shorter than any previously observed AUDIO-source gap in that run,
though no lower bound on a new source's arrival has been established. Verify cycle 3
shows the direct half of it: it acknowledged `0x0500` and POSTACK read `0x8100`, VIDEO pending
again, and the run continued normally.

With GBP-HW-028 (writing 1 to a source bit that reads 1 clears it), the model is:
the ACK clears exactly the bits it writes as 1; the rest stay pending; the re-arm
`IRQ := 0x0000` releases them immediately.

### What that implies for the two policies (analysis only — nothing implemented)

**If the runtime takes GBI's majority (`0x0100`) and ACKs `0x8100` while AUDIO
really was asserted:** the AUDIO bit is never written as 1, so it is not cleared.
It stays pending and is delivered as the next cause microseconds after the
re-arm. The cost is one extra service cycle and a sub-2 µs delay. **No source is
lost.** That is not a deduction from the datasheet we do not have — it is what
cycles 5 and 7 did on hardware.

**If the runtime takes the Disc's last replica (`0x0500`) and ACKs `0x8500` while
AUDIO was *not* asserted:** it performs a 0x1000 AUDIO block read for a buffer the
device may not have published, and that data enters the capture as if it were
real. It also writes 1 to a source bit that reads 0, whose effect has never been
tested (GBP-HW-028 only established the 1-on-1 case). The failure mode is
therefore silent contamination rather than a missed interrupt.

The asymmetry is the whole argument: majority errs toward *serving later*,
last-replica errs toward *serving something that may not be there*. For a
research runtime whose output is evidence, serving late is recoverable and
serving phantom data is not.

**Option A — GBI majority authoritative, Disc value kept as diagnostic.**
Preferred on the evidence. No source loss (GBP-HW-096), no phantom read, robust
against exactly the replica variability this hardware demonstrably has
(GBP-HW-090, GBP-HW-093), and it matches the mature independent implementation.
Costs: one extra cycle when the minority replica was the truthful one, and a
deliberate divergence from the Start-up Disc.

**Option B — Disc last replica authoritative, majority diagnostic.** Matches the
primary software reference, which is not a small thing: the Disc ships, works,
and reads exactly those two bytes. But every disagreement observed so far has the
minority on the *last* replica, which is the one B trusts, and B's failure mode
is the unrecoverable one.

**Option C — configurable, with a reference mode.** Attractive for research: run
the same capture twice under both readings and compare. Costs a policy branch in
the service path and doubles the behaviours any regression has to cover. Worth
having as an experiment switch, not as the runtime default.

**Option D — something better, proven.** Nothing qualifies yet. The obvious
candidate ("take the union, `disc | gbi`, and ACK both") is *not* neutral: it
ACKs a source that may never have been asserted, i.e. option B's failure mode
with extra steps.

### The second decision, kept separate

Whether a disagreement should **abort** is not the same question as which value
is authoritative, and the answer now looks different from the day the probe was
written. A disagreement is no longer an unexplained event with no evidence: it is
a known, recurring, transport-clean condition whose bytes we can preserve, and
under option A it has a defined, non-destructive outcome. The natural shape is
*authoritative = majority; disagreement = a counted, bounded diagnostic anomaly
that preserves its bytes and does not stop the run*. Two runs have now been ended
by a condition that, under that policy, would have cost one extra cycle.

**Nothing is implemented.** This is the analysis, not the change; the change
needs its own design, its own audit and its own physical candidate.

### GBP-VIDEO-003 is gated on this

Confirmed, not assumed. The colour experiment needs a long uninterrupted
observation of the same service loop, and both physical runs of GBP-VIDEO-002
ended on this condition — one after 8.19 s, one after 0.084 s. With the current
fatal policy the colour run would end at an arbitrary point, and a third run
spent re-learning that would answer nothing. The ROADMAP now records the gate.

### Preservation and tests

Raw log and sidecar copied to `captures/local/`; versioned fixture
`hw-gamecube-gbp-2026-09-17-vstate-0002.gbpreplay` + its byte-identical v3
sidecar added under `captures/fixtures/`, with a header that states plainly what
the script is (the logged prefix; the 513 lean cycles are not in it) and what the
run did and did not observe. The fixture is registered in the physical-fixture
allow-list, and `tests/host/test_vstate.py` gained a `PhysicalV3` class that
re-derives the identity, the CRCs, the section bounds, the 96-byte record, the
eight replicas, both readings and the `0x0400` difference from the file on disk.
287 → 295 host tests. No runtime code changed; no format changed; v1, v2 and the
vstate-0001 fixture are untouched.

---

## 2026-09-17 — vstate-0003 designed: a disagreement stops being an abort, without inventing semantics

Design only. No runtime, no DOL, no hardware. The full specification is
GBP-VIDEO-002-R3 in HARDWARE_TESTS; this entry records the decisions and the two
places where the previous consolidation had to be corrected.

### Two corrections to what I wrote yesterday

**Arithmetic.** I described 1.8 µs against a 244–279 µs source cadence as "three
orders of magnitude". It is 134× to 153×, about **2.1** orders of magnitude. The
qualitative conclusion is unchanged — 74 ticks is far shorter than any previously
observed gap between causes of that source in that run — but the number was wrong
and is now right in EVIDENCE, DEVLOG and REGISTERS.

**U-GBP-033's framing.** I wrote it as "is the replicated IRQ window an atomic
snapshot?", which is a yes/no that GBP-HW-090 and GBP-HW-093 already answer with
`no` while teaching nothing. Reworded to *what mechanism produces semantic
non-uniformity among the eight replicas?* — and, more importantly, decoupled from
the policy. Holding the service policy hostage to a question about the device's
internals would have blocked the project on something we may never get to observe
directly. The policy can be settled from the lifecycle evidence we already have.

### The scope decision that took the most thought

The tempting design is "any `disc != gbi` becomes nonfatal". That would be wrong.
The classification is three-way, on masks that already exist in the versioned
contract (`SRC_MASK 0x0555`, `AV_MASK 0x0500`, `ODD_MASK 0x0AAA`, `HIGH 0x7000`,
`BIT15 0x8000` — exhaustive and disjoint):

* **SOURCE_SERVICED** — the difference is inside `AV_MASK`, the two bits whose
  whole lifecycle is physically established. Nonfatal, majority-authoritative.
* **SOURCE_OTHER** — a source slot we do not drain (`0x0001`, `0x0004`, `0x0010`,
  `0x0040`). Stays fatal, and not out of timidity: such a source **already** ends
  the run through the independent `anomaly_unexpected_source` rule, so relaxing
  the disagreement rule there would open a path past a source with no drain.
* **NON_SOURCE** — anything touching the odd bits, bit 15 or the high bits. Stays
  fatal.

### How the authoritative value is composed

Not "use the majority". Outside `SRC_MASK` the two readings **must agree** — they
are never voted, never merged, never chosen between — and if they differ the run
ends. Only inside `SRC_MASK` is a choice made, and there it is GBI's bitwise
majority. So no field whose contract is still open (the odd bits, bit 15, bits
12–14) ever has semantics invented for it by a vote.

Worth recording: the probe **already** takes its service value from the GBI
reading at both read sites. What R3 removes is the refusal to proceed when the
Disc reading disagrees — a smaller change than the discussion around it suggests.

### Why majority, stated as what it is

A design decision with a physical basis, **not** a FACT about hardware intent.
The basis is the asymmetry of the two failure modes, and only one side of it has
been observed:

* majority omits a source the last replica has → the ACK never writes that bit as
  1, so by GBP-HW-028 it is not cleared, and by GBP-HW-096 the next cause follows
  the re-arm in 74 ticks, 134–153× faster than the shortest observed gap for that
  source. One extra cycle, nothing lost.
* majority carries a source the last replica has dropped → **never observed**. The
  runtime would drain a buffer the device may not have republished and would write
  1 to a source bit reading 0, a case GBP-HW-028 does not cover. Serving late is
  recoverable; serving phantom data is not.

That second case is made nonfatal too — ending the run would teach nothing — but
it is not declared safe by symmetry. It gets its own counters, its own histogram
and, uniquely, the CRC-32 and first word of the block that was drained for the
extra source, so the first physical occurrence arrives fully described.

### The follow-up record, and what it deliberately does not say

Each nonfatal event records whether the omitted source was **present in the next
cause**, the latency from the re-arm, and this run's own gap statistics for that
source up to that moment. The states are factual only — `FU_SOURCE_PRESENT_NEXT`,
`FU_SOURCE_ABSENT_NEXT`, `FU_NO_NEXT_CAUSE`, `FU_UNKNOWN` — and **no runtime label
is derived from any divisor of an observed gap**. An earlier draft of this design
had such a label; it was wrong, because it turned the smallest gap a run happened
to observe into a physical lower bound on how soon a new source may arrive. No such
bound exists. The quantitative comparison is computed offline, as a ratio, and
presented as a ratio.

Presence in the next cause proves the source was **observed after the re-arm** and
nothing more: whether it is the same assertion is an offline question, to be
classified CORROBORATED or HYPOTHESIS on the aggregate.

### Cost, with the quantities named properly

160-byte record (the v3 record's 96 bytes at the same offsets plus a 64-byte
follow-up block), 256 of them = 40 960 B, plus 768 B of histograms: an increment
of **41 728 B = 40.8 KiB**. Nothing per normal delivery. N was chosen from
footprint, not from a predicted rate — two events in two runs support no rate at
all.

An earlier draft of this entry called the result a "new static_bytes" against
6 922 240 B. That conflated two different things and is corrected in the design:

```text
resident_store_bytes  6 922 240 B  the probe's own stores, what gbp_vstate_static_bytes()
                                   reports and the log prints as `static_bytes`
total_bss (measured)  7 472 388 B  the .bss of the CLEAN vstate-0002 ELF (.sbss is a
                                   further 1 804 B; the DOL's BSS region is 7 474 192 B)
estimate after R3     7 514 116 B  ≈ 7.166 MiB, BEFORE alignment padding
authoritative value                from the linker map, at implementation time
```

The increment is 0.60 % of the resident stores and 0.56 % of `.bss`; either way it
is not close to any limit.

The sidecar becomes **OGBPSEQ1 v4**, which only adds: every v3 header field keeps
its meaning and its offset, and a fixed 1 024-byte semantic-coherence block joins
the layout before the record array. v1, v2 and v3 are historical and frozen. Also
named properly: `1 024 + 256 × 160 = 41 984 B` is the **maximum v4
semantic/diagnostic extension payload**, not a maximum sidecar size — the file
still carries the header, all four tables, the preserved raw and the footer, and
runs to megabytes at full length.

### The gate this unblocks

GBP-VIDEO-003 no longer waits on U-GBP-033. It waits on a vstate-0003 run that
observes at least one `SOURCE_SERVICED` disagreement, does not stop for it, loses
no observable source, restores cleanly and reaches a relevant window. A run with
zero disagreements would be *inconclusive*, not a pass — the policy would be
untested — and the design says so.

Next: implementation is a separate step, with its own ultracode pass, its own
microaudit and its own release audit. Nothing about the runtime has changed today.

---

## 2026-09-17 — R3 hardened: an inference I had smuggled in as a runtime label, and four mislabelled quantities

Design review of the vstate-0003 specification. Still no runtime, no build, no
hardware. Everything below is a correction to the design I wrote earlier today.

### The one that mattered

I had specified a follow-up state called `FU_TOO_FAST_FOR_FRESH`, awarded when the
re-arm→next-cause latency fell below **one eighth of the smallest gap that run had
happened to observe** for that source. That is exactly the move this project
forbids: it turns an observed minimum into a physical lower bound and then lets
the *runtime* stamp a causal conclusion on the evidence. No lower bound on how
soon a new source may arrive has ever been established here.

Removed. The follow-up states are now purely factual —
`FU_SOURCE_PRESENT_NEXT`, `FU_SOURCE_ABSENT_NEXT`, `FU_NO_NEXT_CAUSE`,
`FU_UNKNOWN`, plus `FU_PENDING` during the lifecycle — and what gets persisted is
`rearm_to_next_ticks`, presence or absence per source, and the run's own gap
statistics as **data**. The ratio ("134× shorter than anything seen so far") is
computed offline and presented as a ratio. GBP-HW-096 was rewritten the same way:
FACT for the measurements, CORROBORATED for the model they support, and an
explicit note that a new assertion arriving in that interval has not been excluded
by any measurement. The phrase "cannot be a fresh source" is gone from EVIDENCE,
DEVLOG and REGISTERS.

Presence in the next cause proves the source was observed after the re-arm. It
does not prove it is the same assertion, and nothing in the runtime may say it
does.

### The guard I described as a consequence when it is a precondition

I justified keeping `SOURCE_OTHER` fatal by pointing at the existing
`anomaly_unexpected_source` rule — but I never wrote down that the guard fires
**independently of the delta**. It has to, and now the order of checks is
normative: compose → non-source class → source class → **pending guard on the
authoritative value** → disagreement class → service. A read where both
interpretations agree on `0x0104` is still fatal, because `0x0004` has no drain in
this probe. That case is now a required test.

### The gap in the science path

If the majority carries a source the Disc reading does not, the runtime drains a
block the device may not have republished — and I had specified only a CRC and a
first word for it. That is enough to *notice* the case and not enough to keep it
out of the results. Now: the block is flagged `B_MAJORITY_EXTRA` at the point of
service, and for VIDEO the containing frame is flagged `F_MAJORITY_EXTRA` **and**
treated as an existing class (a) anomaly, so it never counts toward valid
observation, never forms a baseline, never validates a structured change, and is
excluded from colour evidence in GBP-VIDEO-003. Signatures and raw are still
preserved — quarantine removes it from the scientific path, not from the record —
and resync needs no special case: the frame closes on the next boundary like any
other and no block is fabricated.

The mirror case got the same treatment in the other direction: when the majority
omits VIDEO the drain is simply deferred, nothing is fabricated, and the
assembler's existing incomplete/resync rules decide what the short interval means.
A descriptive `F_SOURCE_DEFERRED` flag lets the offline analysis correlate the
two, and claims nothing about recovery.

### Ordering, which I had left implicit

Consecutive disagreements now have a mandatory sequence — cycle *n+1*'s read fills
record N's follow-up **before** record N+1 is created from that same read — and a
store that is full may still finalise a record already waiting. Both are required
tests, as is the rule that an observational (POSTDRAIN/POSTACK) disagreement is
counted and preserved but never carries a service-selection narrative, because no
service decision was taken there.

### Four quantities that were mislabelled

`6 922 240 B` is the probe's **resident stores**, not its static memory; the CLEAN
audit measured `.bss` at `7 472 388 B`. The post-R3 estimate is `7 514 116 B ≈
7.166 MiB` before alignment, and the authoritative number must come from the
linker map at implementation. And `41 984 B` is the **maximum v4 extension
payload**, not a maximum sidecar size. All four names are now explicit in the
design.

### Also recorded as open

The effect of an ACK writing 1 to a source bit whose last replica reads 0.
GBP-HW-028 covers 1-on-1 only, and I had leaned on it once too far. R3 assumes
nothing about the 1-on-0 case, performs no extra read to investigate it, and
preserves everything needed to describe the first occurrence.

Next: implementation, with its own ultracode pass, microaudit and release audit.

---

## 2026-09-17 — vstate-0003 implemented: a disagreement is now survivable, and nothing else moved

The design of GBP-VIDEO-002-R3 is implemented. No hardware, no physical
candidate, no commit. The versioned specification stayed the authority
throughout, and where the code and the specification disagreed the code changed.

### The shape of the change

One gate, in one place, in the normative order: classify, refuse the classes that
have no contract, compose the authoritative value, apply the pending guard, and
only then decide whether the disagreement is survivable. `semantic_gate()` in
`gbp_vstate_probe.c` is that order, and both read paths go through it — the lean
READ and the verify PRESVC — so it cannot drift between them.

The pending guard is the part most easily got wrong, and the implementation makes
it impossible to get wrong by accident: it fires on the **authoritative value**,
not on the delta, so `Disc = GBI = 0x0104` is still a fatal
`anomaly_unexpected_source`. That is a test, not a comment.

### What surprised me

Very little, which is the point of having specified the byte layouts first. Two
things worth recording:

**The log lines did not fit.** The first version of the disagreement records
overran the ring's 256-byte lines and the invariant check caught it immediately —
`truncated == 0` is asserted by every scenario. Split into four short lines
(`READDISAGREE`, `…RAW`, `…PI`, `…FU`) rather than made shorter by dropping
fields.

**A v4 file relabelled as v3 is refused by v3's own rule**, not by the version
check: `0x1EA..0x1FB` carry `diag_flags`, `off_semantic` and `semantic_size`, and
v3 requires that area to be zero. I had expected `-2` and got `-8`. The
expectation was wrong and the behaviour is exactly what the freeze is for, so the
test now pins `-8` and says why.

### The quarantine needed no new machinery

A VIDEO block drained only because the majority carried a source the Disc reading
did not sets `F_MAJORITY_EXTRA` **and** `F_ANOMALY` on the frame that consumes it.
`F_ANOMALY` already clears `clean`, and `clean` already gates `F_COUNTED`, the
baseline search and every episode decision. So the frame is out of the scientific
path through the existing rules rather than through a parallel one — 7 frames
quarantined in the synthetic scenario, 0 counted, 0 baseline, 0 episodes.

The mirror case fabricates nothing: when the majority omits VIDEO the drain simply
does not happen, `F_SOURCE_DEFERRED` marks the frame **only if one is open**, and
the assembler's own incomplete/resync rules decide what the short interval means.

### Cost, measured rather than estimated

```text
.bss        7 472 388 -> 7 515 316 B   +42 928 B (41.9 KiB)
diag_store                   40 960 B  exactly 256 x 160
struct gbp_vstate    4 248 -> 5 176 B  +928 for the aggregates and bookkeeping
```

The design estimated ~42 020 B and labelled the remainder `estimated bookkeeping
overhead`; the real figure is 652–908 bytes above it. The linker map is the
authority and the estimate is not being retrofitted to match.

### What did not change

The ISR and both one-shot bodies are byte-identical to the physically validated
GBP-VIDEO-001 build — `make vstate-audit` diffs them and says so. With no
disagreement the device operation stream is identical, operation for operation, to
vstate-0002's. With a disagreement the only difference is the service selection
the majority dictates: the same 44 IRQ reads, the same operation count, the same
transfers, no retry, no second read, no extra ACK or re-arm. Both are tests.

### Numbers

C 692 664 checks across 17 binaries, 0 failures. Python 302 passed. Seven audit
profiles, 0 findings. Docker, all POCs, zero warnings. Dolphin 19/19 PASS, both
vstate scenarios still stopping at the stage-A gate without reaching the
experimental path.

U-GBP-033 remains open — nothing here explains why the replicas differ. The build
is dirty and is not a physical candidate; the microaudit comes next.

---

## 2026-09-17 — microaudit of vstate-0003: two real defects, both in the parts that decide what counts as evidence

Audit of the implementation against the versioned design. Two defects found and
fixed, one defensive change, one published number corrected, and one suspected
design gap closed by measurement rather than by argument.

### Defect 1 — the quarantine could land on the wrong frame

`gbp_vstate_block()` applied `F_MAJORITY_EXTRA | F_ANOMALY` at the top of the
function, **before** the boundary logic. When the suspect VIDEO block was itself a
frame boundary, the flags therefore went onto `cur_flags` while it still belonged
to the *previous* frame — invalidating a frame that never contained the block, and
leaving the frame that did contain it apparently clean and eligible for the
baseline.

Fixed by moving the flag application to the point where the block is actually
accumulated, after any boundary has closed the previous frame. The test that would
have caught it exists now: a 40-block clean frame, then a majority-extra block
that is itself a boundary, then assertions that frame 0 is untouched and complete
and that the *new* frame carries the flags and never gets `F_COUNTED` or
`F_BASELINE`. A second case covers a suspect block in the middle of a frame: 20
clean blocks do not save the frame.

### Defect 2 — the follow-up collapsed multiple omitted sources into one answer

A disagreement can omit **more than one** source. The implementation asked
`if ((next_gbi | next_disc) & disc_extra_sources)` and called that
`FU_SOURCE_PRESENT_NEXT`. Two things wrong with it: it ORed the two readings of
the next cycle — mixing the two authorities inside one series, which is exactly
what this policy exists to prevent — and with `disc_extra = 0x0500` and a next
cause of `0x0100` it would have reported "present" although AUDIO never came back.

Fixed: the comparison is per source bit, against the **authoritative** source set
of the next read (`next_pending_gbi & SRC_MASK`), and the aggregate state is now
defined narrowly — `PRESENT_NEXT` only when **every** omitted source was there,
anything less is `ABSENT_NEXT`, which therefore covers the partial case. The
aggregate can no longer over-claim recovery. The exact split is derivable from two
stored fields, `tools/vstate.py` prints both masks and flags the partial case, and
R3.21's release gate now says to read the masks rather than the state.

### One defensive change

The stage-A abort returns without reaching `finish()`. No record can exist there —
the stage's reads never go through `semantic_gate()` — but the closing call is made
anyway, so "no record reaches the report as `FU_PENDING`" is a structural property
of every exit instead of an argument about one.

### The suspected design gap (§47) was not one

A nonfatal condition that can occur on a large fraction of cycles could, if it
emitted an event each time, fill the 4 096-entry event store and convert itself
into an `event_store_cap` stop — a silent behaviour change. It does not: the
semantic path emits **no** event, verified in the call graph and in the objdump of
the gate, and now pinned by a test. The 681-disagreement run uses 9 event slots.
The ring log prints the first 8 records in full plus one summary line and nothing
else scales with the count. Both bounds are now normative in R3.15b.

### A number I had published was wrong

I reported the vstate-0002 `.bss` baseline as 7 472 388 B. Rebuilding commits
`8cbb28d` and `caacbba` with the same command both give **7 472 372 B**; the figure
was 16 bytes off. The reconciliation now closes exactly, with no "misc" term:

```text
diag_store +40 960   sb.0 +1 024   vstate +936   res.2 +16   info.0 +8
sum +42 944   inter-symbol padding 14 677 -> 14 693 = +16   total +42 960
.bss 7 472 372 -> 7 515 332 = +42 960     residual 0
```

`sb.0` is the 1 024-byte staging buffer of the semantic block; it is write-only,
derived from `st->sem` immediately before the emit, touched only after the
teardown, and its purpose is documented at its definition. The service loop's
stack frame did not grow at all (568 B before and after); the only new frames are
`gbp_vstate_diag_open` at 96 B, on the disagreement path only, and 8 to 32 bytes
in the serializer and parser. Nothing scales with the number of disagreements.

### After the fixes

C 692 795 checks across 17 binaries, 0 failures. Python 302 passed. Seven audit
profiles, 0 findings, ISR byte-identical. Docker all POCs, zero warnings. Dolphin
19/19 PASS at the stage-A gate. v1, v2 and v3 unchanged, and the physical v3
diagnostic still recomputes to `disc 0500 / gbi 0100` from its own bytes.

The DOL changed because runtime code changed: the previously reported
`48982a56…` is discarded.

---

## 2026-09-17 — vstate-0003 executed: the target reached, the policy survived, the diagnostics misattributed

**Goal:** consolidate the physical `vstate-0003` run, freeze OGBPSEQ1 v4 as a
historical format with a known producer defect, and close the design of the fix.
No runtime change, no new DOL, no hardware.

### What the run did

The first run of GBP-VIDEO-002 to reach its scientific target: **1 114 007
admitted cycles over 175.848 s**, of which **120.009 s of valid post-baseline
observation** against a 120 s target, `stop=nominal_negative`,
`status=ok_structured_change_observed`, SERVICE ok, RESTORE ok, 0 errors, 0
reentry, 0 timeouts, 0 uncertain writes, 0 counter overflows, one teardown W1C.
420 073 VIDEO and 720 210 AUDIO whole-block drains; 10 503 frames, 9 episodes,
7 stable. The structured change was observed again (GBP-HW-098/099/107).

**Twenty-three semantic disagreements, none of them fatal.** All 23 are
`SOURCE_SERVICED`, and all 23 recompute from their own preserved 32 bytes —
without trusting any stored field — to Disc `0x0500`, GBI majority `0x0100`,
delta `0x0400`, `disc_extra` `0x0400` (AUDIO), `majority_extra` `0x0000`. That is
the policy R3 was built for, executed on hardware 23 times without stopping the
service (GBP-HW-100).

Two structural results came free with them. The replica non-uniformity is a
**contiguous suffix** in every single event — 21 of length 1, one of length 2
(cycle 839 272), one of length 3 (cycle 1 015 782) — which makes the ordering a
fact and the mechanism still unknown (GBP-HW-101, U-GBP-033). And the source the
majority omitted was present in the **next** ordinary read in **23 of 23** events,
at 3 492 to 4 310 ticks (86.22 to 106.42 µs) measured on the two clocks that
survive the defect below (GBP-HW-102, GBP-HW-103).

### The defect the run exposed

The v4 producer addresses the current cycle's diagnostic as *the newest record*:
every current-cycle setter does `d = &s->diags[s->diags_n - 1u]`, and those
setters run on **every** service cycle, not only on cycles that opened a record.
A record therefore keeps absorbing the authoritative value, service decision, ACK
and re-arm of later cycles until the next disagreement opens a new one. The
signature is unmistakable in the file: `t_ack > t_next_cause` in **23 of 23**
records, by seconds; `authoritative & SRC_MASK != gbi & SRC_MASK` in 22 of 23
(GBP-HW-104).

The file itself is not corrupted. Both CRCs verify, every section is exactly
contiguous with zero overlap and zero orphan bytes, the footer lands on the last
byte, and the log dropped nothing. The defect is producer **attribution**, not
storage, layout or CRC — which is why the fields written once at open (`t`,
`cycle`, `disc_value`, `gbi_value`, `raw[32]`, the classification, the deltas,
the gap snapshot) and the follow-up fields written through a handle cleared in the
same act (`t_next_cause`, `next_pending_*`, `followup_*`) remain trustworthy, and
the five current-cycle fields do not (GBP-HW-105).

The honest consequence for R3: **policy behaviour strongly corroborated,
diagnostic attribution failed, validation incomplete.** And one claim I could have
over-stated stays demoted: no next cause of the 23 events contained VIDEO
`0x0100`, which requires the ACK to have cleared it — but none of those 23 cycles
appears among the 80 sampled cycle records, so there is no independent observation
of the ACK. Correct hardware service is **CORROBORATED (strong)**, not FACT
(GBP-HW-106).

### What was preserved, and what was deliberately not changed

The raw log (`9f81f19f…2e57`, 86 378 B) and the sidecar (`0a45d487…e6bc`,
4 359 724 B) were copied to `captures/local/` and the sidecar to
`captures/fixtures/` byte for byte. The fixture's header NOTEs state the run's
facts, the defect, and the **exact trusted/untrusted field split**, so a reader who
finds this file in five years cannot mistake a contaminated field for a
measurement.

**OGBPSEQ1 v4 and its parser are frozen exactly as they were.** Adding the
cross-field invariants that would catch this defect would make the parser refuse
the only physical v4 file that exists — destroying evidence to enforce a rule
written after the evidence. Instead `tools/vstate.py diag` grew a non-fatal
**PRODUCER WARNINGS** section (`ack_after_next_cause`, `rearm_after_next_cause`,
`authority_not_majority`; 23, 23 and 22 on this file), and
`tests/host/test_vstate.py::PhysicalV4` pins both halves: the file still parses,
and the defect is still detectable offline.

### The fix, designed and not implemented

`GBP-VIDEO-002-R4` / build `vstate-0004` / OGBPSEQ1 **v5** (HARDWARE_TESTS §R4.1
to §R4.10): an explicit record handle carried by the cycle replaces "the newest
record", the two lifetimes are separated (current-cycle fields end with the cycle,
follow-up fields stay open across cycles), and v5 records which fields each record
actually owns. Observed policy behaviour does not move: same three classes, same
authority composition, same independent pending guard, same quarantine. Nothing
of it is implemented and nothing it produces is evidence yet.

GBP-VIDEO-003 stays **GATED**, now behind a successful `vstate-0004` run rather
than `vstate-0003`.

**Tests:** Python **312 passed, 0 skipped** (10 new in `PhysicalV4`); C
**671 997 checks across 17 binaries, 0 failures**. No runtime source changed in
this round, so no DOL was rebuilt and no Dolphin or Docker run was part of it.

One correction to the previous entry: it published **692 795** C checks "after the
fixes". That figure does not reproduce at this commit — the C sources are
untouched since it, the binaries are deterministic across repeated runs, and the
suite gives 671 997. The measurement was evidently taken before the last
`gbp_vstate.c` fix of that round (the quarantine-ordering change, which alters how
many per-frame invariants the suite iterates over). **671 997 is the reproducible
figure**; the published one is withdrawn.

---

## 2026-09-17 — vstate-0004 implemented: the diagnostic record gets an owner, and nothing else moves

**Goal:** implement GBP-VIDEO-002-R4 / OGBPSEQ1 v5 from the design versioned at
`1ed1629`, fixing the producer defect the physical `vstate-0003` run exposed
(GBP-HW-104) without touching one hardware operation. No hardware, no candidate,
no commit.

### The defect, and why a patch would not have been enough

In `vstate-0003` every current-cycle setter resolved its own target:

```c
d = &s->diags[s->diags_n - 1u];     /* "the newest record" */
```

and the service loop called all six of them on **every** cycle. A record
therefore kept absorbing the authoritative value, service decision, ACK and
re-arm of later cycles until the next disagreement opened a new one. It would
have been easy to patch the symptom — stop updating after the follow-up, say —
and that patch would have left the same class of error one refactor away. The
fix is structural: **the target is named by the caller and by nobody else.**

`diag_open()` returns a `gbp_vstate_diag_handle`, every current-cycle setter takes
it explicitly, `GBP_VSTATE_DIAG_INVALID` is a bounded no-op, and there is exactly
one function in the file that turns a handle into a record. No `diags_n`
arithmetic, no "latest" fallback, no current-record member: there is none to read.
The cycle carries the handle in a local that is born INVALID, receives a value
only from the read that selects the service, and dies with the iteration.

The microaudit of this work found one gap in that discipline and closed it: the
probe still wrote the read's transport and ISR context by indexing
`st->diags[idx]` directly — correct, because `idx` came from the `diag_open()` on
the line above, but it was the one record write that did not go through the
resolver. It is now `gbp_vstate_diag_context()`, a handle-taking setter like the
others, and **no file outside `gbp_vstate.c` writes a diagnostic record any
more**. The serializer and the ring log only read, through `const` pointers.

### Two lifetimes, kept apart

The service handle belongs to one transaction. The follow-up waiter belongs to
the *next* read and receives only `t_next_cause`, `next_pending_*` and
`followup_state/reason`. R4.6 also moved when the waiter is armed: after a
**written** re-arm, never at open — installing it earlier would claim a next cause
is expected after a re-arm that may never happen.

That change opened a hole worth naming: a record whose transaction dies before
the re-arm never becomes the waiter, so nothing would ever close it, and
`FU_PENDING` may not reach a file. `gbp_vstate_diag_close()` now closes the waiter
**and then sweeps** the store for any record still pending — bounded by 256, once,
after the teardown. "No record reaches the file as FU_PENDING" became a structural
property of every exit instead of an argument about one.

The same honesty rule was applied to the writes themselves: `diag_ack` is now
called only after the ACK write completed and `diag_rearm` only after the re-arm
completed. Before, both flags were set before the write was known to have
succeeded — a smaller instance of exactly the defect being fixed.

### OGBPSEQ1 v5: the same 160 bytes, a stricter promise

No field was missing, so no field was added. v5 has v4's layout byte for byte;
what it adds is a contract the parser enforces. Every derived value is
**recomputed** — both readings from `raw[32]`, then the delta, the two extra
masks, the classification, the composed authoritative value — and a record that
does not agree with its own bytes is refused. So are: an ACK that is not
`authoritative | 0x8000`, an ACK or re-arm flag with an invalid timestamp, a
plausible timestamp without its flag, a timing chain out of order, a follow-up
verdict that contradicts the per-bit split, a payload whose source was not
majority-extra or not serviced, a fatal-class record carrying an ACK, and an
observational record claiming any current-service effect.

One new record-flag bit was needed after all, and it is worth the paragraph:
`DF_SERVICE_WRITTEN` (0x0100, in v4's reserved byte). Without it
`service_selected == 0` is ambiguous between "no source was selected" and "no
decision was ever recorded here" — precisely the kind of zero §29 refuses to
leave undecidable. v4 files must still carry zero in bits 8..15, and their parser
still says so.

**The timing rule is read-kind dependent**, which is the subtlety the physical
file exposed: the chain `t ≤ t_ack ≤ t_rearm ≤ t_next_cause` applies to a
service-selecting record, and an observational POSTDRAIN/POSTACK record has no
such chain because those reads legitimately happen after the ACK. There is
deliberately no universal rule.

**v1, v2, v3 and v4 did not move.** Every entry point of the family judges a file
by its own version: the physical v4 sidecar still parses in both implementations,
and its defect is still a non-fatal **PRODUCER WARNING** (23 / 23 / 22, 68 in
total). Refusing it to enforce a rule written after it would destroy evidence.

### What did not change, and how that is known

The device stream. Four disagreement directions — Disc-extra AUDIO, majority-extra
AUDIO, majority-extra VIDEO, Disc-extra VIDEO — were run against reference runs
that agree on the value the policy services, and each pair has identical IRQ
reads, operations, bulk reads, IRQ writes and transfers. The setters compile to
leaf functions with **zero calls**; the capture path has one `bctrl`, which is the
time-base read it always had, plus `memset`. The ISR objects are **identical** to
the physically validated GBP-VIDEO-001 build's, ext and base, and no source under
`src/platform/` was touched. `.bss` did not grow by one byte (7 515 332, the same
figure a rebuild of `1ed1629` gives); `.text` grew 672 B and
`gbp_vstate_probe_run`'s frame 16 B.

One correction to the request's baseline figures: it quoted `.bss` 7 515 340 and
DOL BSS 7 517 144. Rebuilding `1ed1629` in a clean worktree gives **7 515 332**
and **7 517 136** — 8 bytes lower. The measured values are used here.

### Tests

New C batteries reproduce the physical defect's own shape (isolated events with
many ordinary cycles between them, and one event followed by thousands of
cycles), the three-record same-transaction case, the marker ownership, the
failure lifecycle, the INVALID-handle sweep and nine tampers a v5 parser must
refuse. The Python side runs the same tampers and puts **every one of them through
the C parser too** (`test_gbp_video_state --parse`), because two parsers that
disagree about what is a valid file are worse than one.

The microaudit added more: ownership through a store that runs out mid
transaction (0, 1, 2 and 3 free slots, with A keeping its markers whenever A
fitted at all), a byte-level proof that the teardown sweep touches only follow-up
bytes and an already-closed record not at all, the majority-extra-only case that
must never wait for a source nobody omitted, a 256-record v5 file that
strict-parses, and a whole-corpus parity check in which every physical file,
every synthetic file and every tamper is put through both parsers and they must
give the same verdict.

That corpus also settles how dispatch works, and the proof is pleasing: the
physical v4 file **violates v5's cross-field rules in 22 of its 23 records**, and
it is accepted by the entry point named for v5 — which is only possible because
the rules applied are the file's own, never the caller's.

C **672 740 checks across 17 binaries, 0 failures**; Python **328 passed, 0
skipped**; audits 69 passed with the ISR objects identical; Docker built every POC
with zero warnings; Dolphin **19/19 PASS**.

**Status: IMPLEMENTED — NOT PHYSICALLY EXECUTED. DIRTY BUILD — NOT A PHYSICAL
CANDIDATE.** No evidence ID was created, U-GBP-033 stays open, and GBP-VIDEO-003
stays gated.

---

## 2026-09-17 — vstate-0004 executed: the policy is now physically validated, and GBP-VIDEO-003 is unblocked

**Goal:** consolidate the physical `vstate-0004` run, complete R3's physical
validation and release the colour gate. No hardware, no GBP-VIDEO-003 work, no
runtime change.

### What the run did

1 114 005 admitted cycles over 175.848 s, of which **120.009 s of valid
post-baseline observation** against a 120 s target; `stop=nominal_negative`,
`status=ok_structured_change_observed`, SERVICE ok, RESTORE ok, `transport_ok=1`,
0 errors, 0 timeouts, 0 busy, 0 uncertain writes, 0 counter overflows, 0 reentry,
0 main-loop W1C. 420 073 VIDEO and 720 210 AUDIO drains. 10 503 frames, 9
episodes, 7 stable (GBP-HW-108/109/115).

**Twenty-nine semantic disagreements, all survived — and this time the records
can be believed.** All 29 recompute from their own 32 preserved bytes to Disc
`0x0500`, GBI `0x0100`, delta `0x0400`, `disc_extra` `0x0400`, class
`SOURCE_SERVICED`, and all 29 carry `authoritative = 0x0100`,
`service_selected = 0x0100`, `ack = 0x8100`, `record_flags = 0x01C1` and
`t ≤ t_ack ≤ t_rearm ≤ t_next_cause`. **Zero cross-field invariant failures in
either parser; zero producer warnings** (GBP-HW-110/111).

The defect of `vstate-0003` is simply absent. In the v4 file, 23 of 23 records
had `t_ack` after `t_next_cause` and 22 of 23 had an authoritative value that was
not the majority. Here: **0 of 29 and 0 of 29**. The explicit-handle design did
what it was built to do, and it did it on hardware.

### The transaction, timed on clocks that finally belong together

```text
READ  -> ACK          2 600 .. 2 756 ticks     64.20 ..  68.05 us
ACK   -> REARM          828 .. 1 445 ticks     20.44 ..  35.68 us
REARM -> NEXT CAUSE        77 ..    94 ticks     1.90 ..   2.32 us
READ  -> NEXT CAUSE     3 505 .. 4 128 ticks    86.54 .. 101.93 us
```

That third line is the one worth pausing on. The omitted AUDIO source appears in
the next ordinary read **29 times out of 29**, between 1.90 and 2.32 µs after our
re-arm — and unlike the previous run, the re-arm timestamp belongs to the same
cycle as the read, so this is measured rather than reconstructed.

A model in which the ACK clears VIDEO, the AUDIO assertion survives it, and the
re-arm releases the pending source accounts for all 52 physical events across the
two runs and for the ordering of all four intervals. It is **CORROBORATED, very
strong — and not FACT.** Nothing in this repository distinguishes a source that
survived the ACK from a new assertion arriving inside that 2 µs window, and
nothing here reads the device's internal state. Writing it down as a mechanism
would be the same mistake this project has avoided for four runs.

### The corpus, and what it does not buy

```text
vstate-0003   23 events   21 x 1  1 x 2  1 x 3
vstate-0004   29 events   24 x 1  2 x 2  3 x 3
combined      52 events   45 x 1  3 x 2  4 x 3
              52/52 contiguous 0x0500 suffix
              52/52 AUDIO present in the next ordinary read
```

Two long runs, two producers, the same shape. That makes the *shape* a robust
observation — and it narrows nothing about the mechanism. U-GBP-033 stays
**OPEN**: the internal mechanism, the temporal direction (whether the suffix is
the newer value or the older one), the replica update order and the DMA
interleaving are all still unknown, and the 1.9 µs figure does not settle any of
them because it measures our own re-arm against our own next cause.

### What changed in the status, and what deliberately did not

**GBP-VIDEO-002-R3: PHYSICAL VALIDATION COMPLETE.** Every condition of §R3.21 is
met, by re-observing the same policy on the same hardware with a producer whose
records are trustworthy. One criterion was conditional and never arose: no
majority-extra disagreement has ever occurred physically, so the quarantine path
remains host- and mock-tested, and the entry says so.

**OGBPSEQ1 v5: PHYSICALLY EXECUTED, validated on the exercised path.** The wording
is deliberately narrow. What ran was `SOURCE_SERVICED` with a Disc-extra source,
29 times. Majority-extra, observational POSTDRAIN/POSTACK, `SOURCE_OTHER`,
`NON_SOURCE`, the payload diagnostic and every failure path did **not** occur, and
claiming "v5 is validated" without that qualifier would be exactly the kind of
overreach the v4 file punished.

**GBP-VIDEO-003 is UNBLOCKED** — ready for a controlled colour experiment to be
designed and executed. It was never gated on understanding U-GBP-033, only on
surviving it, and it has now been survived 52 times.

One small offline-tool fix belonged to this round: `tools/vstate.py semantic`
still refused a v5 file, although v5 carries the same block at the same offset.
It now serves versions 4 and 5. And the POC README's procedure block, which had
said `Build ID: vstate-0001` since the first run, now names the build that
actually ran and how the probe derives the SD filenames.

**Tests:** C 17 binaries, 672 740 checks, 0 failures; Python **341 passed, 0
skipped** (13 new in `PhysicalV5`); audits 69 passed; Docker 10 POCs, 0 warnings;
Dolphin 19/19 PASS. The physical v4 file still parses with its 68 non-fatal
producer warnings, and v1, v2 and v3 are untouched.

---

## 2026-09-17 — GBP-VIDEO-003 designed: eight bars that cannot be misread

**Goal:** close the design of the controlled colour experiment from the checkpoint
`dee1f08`. No probe, no ROM, no hardware, no evidence IDs.

### The question, stated honestly

Four physical runs have established where the bytes are: 0xF00 per block, 240 ×
160 in 40 blocks of 4 raster lines, the word taken from bytes 1 and 3, bit 15
carrying the frame-start flag. What none of them established is what the fifteen
colour bits *mean* — and the reason is worth writing down, because it is the kind
of blind spot that is invisible until someone looks for it.

**Every check this project has made so far is invariant under exchanging the two
outer 5-bit groups.** The frame-start predicates read bit 15 only. The
byte-for-byte comparison against the Disc's embedded frame was made on a uniformly
white screen, and `0x7FFF` maps to itself under *any* bit permutation. The block
checksums agree with the reference tables because the bytes agree, which says
nothing about which bits are which channel. Four runs of white are four runs of no
information about colour order.

The two reference decoders do agree that R sits in bits 14–10 — but they agree
with each other, implementing the same convention, not with a pixel of known
colour. `VIDEO_PATH.md` §10 now says this in one place instead of leaving it
spread across three sections.

### The stimulus, and why these eight values

A static AGB Mode 3 image, eight vertical bars of 30 pixels: `0x0000`, `0x001F`,
`0x03E0`, `0x7C00`, `0x7FFF`, `0x0001`, `0x0020`, `0x0400`. All 160 lines
identical. Bit 15 never written.

Three of them isolate the 5-bit groups; three isolate the *least significant bit*
of each group; two are references. The low-bit bars are the ones that matter most
and are the easiest to leave out: an intra-channel bit reversal maps `0x001F` to
`0x001F`, so a pattern of full-scale primaries alone cannot see it, while
`0x0001` → `0x0010` makes it unmistakable. A design with only red, green and
blue bars would have looked complete and would have been unable to falsify one of
its own candidate hypotheses.

`0x0000` and `0x7FFF` earn their place for the same kind of reason: they are
invariant under every bit permutation, so they cannot help identify the
permutation — which is exactly what makes them good controls for the failures a
permutation cannot explain (complement, stuck bits, fill behaviour).

### Recognising the pattern without assuming the answer

The probe has to know the stimulus is on screen before it certifies a frame, and
the obvious way to do that — decode it and look for red — would decide the
question it is asking. Three properties avoid the circle, and all three survive
any bit permutation:

```text
structure   8 runs of exactly 30 identical groups, boundaries at x = 0,30,...,210
repetition  the 4 rows of a block identical; all 40 blocks identical except the
            frame-start flag in block 0
popcount    the multiset of popcounts of the eight values is {0,1,1,1,5,5,5,15}
```

A permutation moves bits; it cannot change how many are set. The popcount
fingerprint identifies the pattern while saying nothing about where anything went,
and the two invariant bars anchor orientation: the popcount-0 bar must be at
x 0–29 and the popcount-15 bar at x 120–149, or the analyser is mirrored. No
"wait a few seconds" rule appears anywhere in the design.

### What the design refuses to do

It does not name a GBP bit group "red" anywhere — they are `C14_10`, `C9_5` and
`C4_0` until a measurement says otherwise. It does not pick the hypothesis that
fits best: exactly one candidate must reproduce **all eight** observed values, and
two fits or zero fits are both INCONCLUSIVE with the raw preserved. It does not
inherit the vstate probe's 120 s and 180 s, which came from the Start-up Disc's
detector window and have nothing to do with this question; the caps here are a
10 s search window, a 30 s wall clock and three preserved frames, each justified
where it is written. And it does not stretch OGBPSEQ1: that contract belongs to
the vstate experiment, so VIDEO-003 gets a dedicated `OGBPCOL1` modelled on the
v1 discipline, reusing only the one piece that is genuinely shared — the 160-byte
disagreement record, because the R3 policy is shared and was physically validated.

### The dependency the design will not invent

**This repository documents no way to run a controlled GBA ROM on the physical
unit.** No flash cart, no multiboot cable, no loader of any kind appears in any
document or any executed test; every run so far was explicitly without a Game
Pak. The design records that as a **PHYSICAL EXECUTION DEPENDENCY**, lists the
candidate routes without claiming the operator owns any of them, and notes that
one of them — multiboot over the Link Port, the mechanism `gba-as-controller`
uses — would itself need proving on this hardware. Execution is blocked; design,
implementation and review are not.

**Status: GBP-VIDEO-003 DESIGN FINALIZED — NOT IMPLEMENTED — NOT PHYSICALLY
EXECUTED.** R3 stays COMPLETE, U-GBP-033 stays OPEN, U-GBP-011 now names the
experiment that closes it, and no evidence ID was created.

---

## 2026-09-17 — GBP-VIDEO-003 implemented: a stimulus, a probe that cannot recognise it, and an analyser that can

**Goal:** implement the controlled colour experiment from the design versioned at
`1b1199f`. No hardware, no candidate DOL, no claim that the ROM can be delivered.

### Three programs that must not know each other

The experiment only works if the pieces stay ignorant of one another, so that is
how they were built:

```text
stimulus/agb-color-bars      writes eight known 15-bit values, never sets bit 15,
                             knows nothing about the GBP
poc/gbp-video-color-probe    preserves three identical eligible frames, knows
                             nothing about the eight values
tools/vcolor.py              holds the eight values and the hypotheses, and never
                             touches hardware
```

The middle one is the interesting constraint. A probe that could recognise the
colour bars would need the values, and a runtime holding `0x001F` on the wire
would be deciding the experiment's question with the experiment's answer. So the
capture module decides only three things: is this frame eligible, are these bytes
identical to the last, and have three in a row arrived. A flash-cart menu that
held still for 50 ms would certify just as happily — and that costs nothing,
because the analyser is what decides whether the preserved bytes are the pattern.
A host test greps the runtime for `0x03E0` and `0x7C00`, the two stimulus values
that collide with nothing else in this project, and fails if either appears.

### Reuse that is actually reuse

`poc/gbp-video-color-probe` does not reimplement the service loop; it runs the
same one. `gbp_vstate_probe_run()` gained a capture hook that is `NULL` in every
GBP-VIDEO-002 build, so detection, the 003A stage, the 003B handler, the drains,
the ACK, the PI clean, the re-arm, WAIT_NEXT, the teardown and the whole R3
policy are the code `vstate-0004` executed on hardware — not a copy of it.

The proof is a test rather than a claim: the same mock scenario runs twice, with
and without the capture attached, and the device streams must match exactly.
They do — 224 IRQ reads, 2 471 operations, 400 whole-block reads either way.

### What the capture refuses

A frame becomes evidence only if it is complete at 40 blocks, unresynced,
anomaly-free, not quarantined by the majority-extra rule, not contaminated by a
deferred VIDEO drain, past the baseline and backed by real bytes. One predicate
answers that question, in the design's order, so the recorded reason is always
the *first* thing wrong with a frame. Fifty identical frames that carry a
majority-extra VIDEO block certify nothing at all, and there is a test that runs
exactly that.

Stability is `memcmp` over the whole 153 600 bytes — not a signature, not a
checksum, not a tolerance. The strongest comparison available, on the same bytes
that will later carry the conclusion.

### The format, and a bug the tests caught

`OGBPCOL1` v1 is a dedicated container: frame history, the certified window, the
shared R3 diagnostic record and the raw frames, with the same discipline as the
rest of the family (big-endian, fixed offsets, reserved bytes zero, header CRC,
total CRC, footer, streamed after the teardown). It is **not** OGBPSEQ1: that
contract belongs to the vstate experiment. The record is shared because the
policy is shared; the container is not, and neither may be called the other.

The round-trip test caught a real defect immediately: the writer computed the
total CRC *after* emitting the footer, so the value stored in the info struct
covered the footer bytes too. The file on disk was right and the parser agreed
with itself, which is exactly the kind of bug that survives a careless test.

### What the analyser will and will not say

It reaches a verdict only when **exactly one** candidate transformation
reproduces all eight observed values. Two survivors, none, a bar that is not
uniform, or a mirrored orientation are each reported as their own kind of
inconclusive, with the raw preserved. There is no score, no distance and no
closest fit anywhere in it.

The synthetic corpus covers identity, outer-group swap, byte swap, intra-group
reversal, complement, a transformation nobody proposed, a single damaged pixel,
a mirrored frame, and bit 15 present, absent and everywhere.

One test earns its place by proving a design claim mechanically: with only the
three full-group bars and the two references, **identity and intra-group reversal
predict the same five values** — indistinguishable. The three single-bit bars are
the entire reason the experiment can refuse H4, and a pattern of red, green and
blue alone would have looked complete while being unable to falsify one of its
own hypotheses.

The same test found something the design had not stated: a **byte swap is not a
permutation of the fifteen colour bits**. The high byte carries only seven of
them, so `0x7FFF` comes back as `0x7F7F` with one bit lost — which means the
white control discriminates the byte-swap family too. Recorded where it belongs,
in the test that discovered it.

### The dependency, still refused

devkitARM lives in the project container, so the ROM is built by the project's own
toolchain and is byte-identical across clean rebuilds. Its **physical delivery
format is unresolved**: the header is structurally valid, but the image is not
cartridge-bootable (devkitARM's crt0 leaves the 156-byte Nintendo logo area zero,
those bytes are Nintendo's, and CLAUDE.md §7 forbids vendoring them) and it is
not a BIOS multiboot image either, because `gba.specs` links it through
`gba_cart.ld` at 0x08000000 while multiboot runs from 0x02000000. The
implementation round called it "multiboot-ready"; the microaudit read the link
map, found that unsupported, and withdrew it from the tool and from both
documents. `tools/gbahdr.py` now computes the complement check, audits the
structural fields, says whether the logo area is empty as a byte test, and
classifies no boot format at all.

**This repository still documents no way to deliver a controlled GBA ROM to the
Game Boy Player's internal AGB.** The implementation does not invent one. Nothing
here can run until the operator resolves it.

**Status: GBP-VIDEO-003 / color-0001 IMPLEMENTED — NOT PHYSICALLY EXECUTED.
OGBPCOL1 v1 IMPLEMENTED — NOT PHYSICALLY EXECUTED. The stimulus IMPLEMENTED —
NOT PHYSICALLY EXECUTED. DIRTY BUILD — NOT A PHYSICAL CANDIDATE.** U-GBP-011
stays open, U-GBP-033 stays open, R3 stays COMPLETE, and no evidence ID was
created.

### Microaudit, same day: the capture is held

The directed microaudit passed every structural gate — circularity, the shared R3
record, the OGBPCOL1 layout and its checked arithmetic, the C/Python parser
parity, the hypothesis algebra, the ISR (byte-identical to the validated
reference), CONTROL, stop precedence, filesystem isolation, determinism — and
failed the one that matters most.

`gbp_vcolor_frame()` runs between the ACK and the RE-ARM and does up to
`memcmp` 153 600 + `memcpy` 153 600 there, at **every** eligible frame close. The
only work ever measured in that window is the 3 840-byte signature (median 823
ticks over 420 073 physical samples), and the only full-frame copy the
architecture already had there, `preserve_frame()`, ran **15 times in 175.848 s**
— not 60 times a second. That is ~81× the bytes and ~700× the frequency, in the
window that invites the next cause 1.90..2.32 µs later. Operation-stream
equivalence says nothing about this and was never evidence for it.

It is also avoidable: `sig[40]` already exists per frame, so stability can be
decided from 160 bytes in the runtime and byte-exact equality proven offline from
the preserved raw. **Decision: STRUCTURAL FIX REQUIRED — RETURN TO ULTRACODE. No
checkpoint, nothing committed, HEAD stays `1b1199f`.**

### The fix, same day

The capture no longer has a way to touch a frame. `gbp_vcolor_frame()` takes a
frame record and a **slot index**; the pointer parameter is gone, so the property
is enforced by the signature rather than measured after the fact. Stability is
decided from `sig[40]` — 40 word comparisons — and the whole hook is 170
instructions calling only a 27-instruction predicate and a 69-instruction record
writer. No `memcpy`, `memcmp` or `memmove` is reachable from it.

The certified frames are never copied. They stay in the state model's ring and
the sidecar streams them out after the teardown. That needed one lifecycle fact
to be established rather than assumed, and driving the real assembler settles it:
on the boundary block that closes C the assembler copies that block into
`cur+1` **before** closing C, so with three slots frame A dies at the instant it
becomes evidence (`A=0 B=1 C=2 filling=0`), and with four it does not
(`A=0 B=1 C=2 filling=3`). The slot count is now derived from the buffer the
caller supplies, so the vstate probe keeps three slots and its exact previous
behaviour while the colour probe passes four. Net BSS: +184 320 for the slot,
−460 800 for the staging buffer that no longer exists.

Two things fell out of that and both are improvements. The **hold window is
gone** — holding for 60 frames would have rotated the ring over the frames it was
protecting, and it was `REPORT ONLY`, never part of the success condition. And
**`F_PRE_BASELINE` is no longer an exclusion**: it was inherited from the vstate
change detector, which asks a different question.

The scientific claim is now split explicitly. The runtime says *three
signature-identical eligible frames*; `tools/vcolor.py` says *the three certified
raw frames are byte-for-byte equal*, checked over all 3 × 153 600 bytes before a
single pixel is interpreted, with `inconclusive_certified_raw_mismatch` and the
first differing offset when they are not. A host test builds a deliberate
signature collision to prove the offline gate is what makes the cheap runtime
check safe.

**Status: STRUCTURAL TIMING FIX IMPLEMENTED, NOT PHYSICALLY EXECUTED, DIRTY.**
Nothing was committed; the next step is a fresh microaudit.

### Second microaudit, same day

The timing fix held: no full-frame work in the capture path, A/B/C intact through
the teardown at every rotation of the ring, the writer reading them straight out
of the slots, and the offline byte-equality gate doing the job the runtime no
longer does. Five things were found and fixed, none of them structural.

The **slot count silently clamped**: a buffer of five slots was accepted as four.
A derived size whose one failure mode is silent reinterpretation is worse than a
constant, so the contract is now exactly three or four and anything else leaves
the model unusable — with a test over 0, 1, 2, 3, 4, 5, a partial frame and NULL.

The **timing wording overreached**. The first report said the new comparison sat
"below the resolution of one tick". That is not measured. The 823-tick figure
belongs to the existing per-VIDEO-BLOCK signature and to nothing else; the new
per-frame-close work is described only by what is true of it by construction —
40 word comparisons, ≤160 bytes copied, no device operation — and the header now
forbids the other phrasing explicitly.

The **design's HOLD lines still read as current** even though §V3.24 had replaced
them; they are kept verbatim, because they are what the implementation was
reviewed against, and annotated SUPERSEDED. Worth noting: the CERTIFY line was
always right — the design said "consecutive eligible frames whose raw per-block
signatures are identical", so the fix returned the code to the specification
rather than changing it.

The **Python analyser printed the stop reason as a bare number**, which made the
new `color_frame_cap` indistinguishable from `color_search_window` to a reader,
and `audio_raw_count` had no accepted-value test. Both closed.

And one that is documentation, not a bug: `GBP_VCOLOR_MAJORITY_EXTRA` is
**shadowed by construction**. The state model sets `F_MAJORITY_EXTRA` and
`F_ANOMALY` together and the predicate reports the first fault, so a quarantined
frame is refused under ANOMALY and that counter reads 0 in any real run. The
exclusion happens either way; the authoritative count is `frames_quarantined` at
0x1AC. Pinned by a test so nobody reads the zero as "none were quarantined".

Finally, a new **PHYSICAL PROCEDURE DEPENDENCY** (§V3.26). Because the run now
stops at certification, and because the probe holds no stimulus value by design,
any still picture that precedes the stimulus — a BIOS screen, an idle flash-cart
menu, a blank framebuffer — can certify within ~50 ms and end the run. It cannot
produce a false result (the analyser refuses non-uniform bars), but it wastes the
run. There is no readiness gate and one that recognised the stimulus would be the
circularity the design forbids. Recorded as a requirement to resolve alongside
ROM delivery; no arbitrary delay was added to hide it.

The microaudit also withdrew the "multiboot-ready" claim (see above) and recorded
two procedural caveats the design must carry: a menu-driven flash cart is not
automatically a delivery route, because this phase has no GameCube→AGB input; and
the 10 s SEARCH_WINDOW starts at capture start, so the stimulus has to be running
before the capture begins.

**Tests:** C 18 binaries, 673 035 checks, 0 failures; Python 366 passed; audits
69 passed with both ISR bodies identical to the physically validated build and
the new `color` profile at 0 findings; Docker 11 POCs plus the ROM, 0 warnings;
Dolphin 21/21 PASS.

## 2026-09-18 — the masked pause is safe, and the premise behind arming was wrong

**Goal.** Answer the one UNKNOWN blocking the GBP-VIDEO-003 arming decision: does
the unit tolerate several seconds between stage A and the handler install, with
PI masked?

**Result: yes, for 5 s at that position.** Build `vstate-prewait-5000`, commit
`500429a`, on the physical Game Boy Player. 5.000 000 22 s elapsed against 5 000
requested; CONTROL `8c`, IRQ `0500`, INTSR `00012000` and INTMR `000001fa`
identical either side; then handler install, PREUNMASK, first unmask and a first
delivery at 89 ticks of latency, followed by 1 108 063 transactions with
unmasks = deliveries = acks = rearms and a clean restore. GBP-HW-116 to
GBP-HW-119. The claim is the duration and the position exercised and nothing
more — not 10 s, not unbounded.

**Classified honestly:** the run ended on `safety_budget` with `valid_s=119.608`
against a 120 s target, because the 5 s pause sits inside the 180 s safety
budget. It is a diagnostic PASS, **not** a vstate run that reached its target,
and the docs say so in those words.

**A premise died, which is the more useful outcome.** The arming audit had
assumed the operator could watch for the colour bars and press a button. Reading
the source rather than assuming: the GBP has no display of its own; the probe
drains no VIDEO before the handler exists (every drain call site is inside the
service loop); and nothing in the repository ever renders a captured block — the
GameCube framebuffer is a text console and there is exactly one
`VIDEO_SetNextFramebuffer` in the tree, the console's own. The operator saw the
bars in the delivery tests because GBI and the Start-up Disc render them.
Open-GBP does not.

So controller-arm-on-sight is **not** implementable as reasoned, and I did not
implement it. The recommendation is Option F, the fixed pre-handler wait this run
just validated, audited against the colour build on five points (capture start
after the wait, search window measured from it, no colour state before it,
analyser protections intact, and a bad window resolving to INCONCLUSIVE rather
than a false mapping). **Not enabled yet**: that 5 s is *enough* for the cartridge
boot to reach the bars is not established by anything here.

**Also this round:** a Swiss launch layout. The build directories are named for
the source tree, and in a truncated list `gbp-init-irq-program-probe` and
`gbp-init-irq-deliver-probe` are the same thing — picking wrong spends a physical
run. `make swiss` now exports every launchable DOL as
`build/swiss/NN-short/boot.dol` with an `INDEX.txt`, numbered by the versioned
manifest `tools/swiss-layout.tsv`. Two digits because Swiss sorts lexically;
numbers are stable and never reused; 01-69 canonical, 80-89 physical
diagnostics. The copy is byte for byte and verified by hash — `build/poc` stays
the authority and nothing gains a second identity.

**Noted, not changed:** the log's `PREHANDLERWAIT` line hit the logger's
255-character limit (`truncated=1`). The WAITPRE/WAITPOST snapshots carry every
value it lost, so the run stands; if the diagnostic is kept, split the line.
Separately, `.unpadded.dol` being *larger* than `.dol` is documented behaviour,
not a bug: `dolpad` rounds section sizes up to 32 bytes **and** re-aligns file
offsets, and here removing a 32-byte inter-section gap outweighed 16 bytes of
size padding. Entry, BSS and section addresses are identical between the two.

**Next:** the first physical GBP-VIDEO-003 run is now gated on one decision —
whether to enable the fixed 5 s wait in `color-0001` — and on nothing else.
U-GBP-011 and U-GBP-033 stay OPEN.

## 2026-09-18 — color-0001 ran: the probe passed, the analyser refused, and the refusal is the right answer

**Goal:** execute and ingest the first physical GBP-VIDEO-003 run.

**What happened on the hardware.** Everything the runtime was built to do, it
did. The 5000 ms pre-handler wait elapsed in 5.000 000 20 s with CONTROL, IRQ and
INTSR unchanged across it; capture opened; the frames went `not_complete`,
`resync`, then three consecutive eligible frames with identical `sig[40]`;
`stop=color_certified`. 440 deliveries = acks = rearms = unmasks, zero errors of
any class, zero R3 disagreements, clean restore. The sidecar validates on every
CRC. This is the first run in the project to reach a colour target at all
(GBP-HW-120, GBP-HW-121).

**And the analyser said INCONCLUSIVE.** `tools/vcolor.py`, unmodified, compares
the three certified frames byte for byte over the full 153 600-byte raw frame
before interpreting a pixel, and they are not equal: 2125 / 2073 / 2137 differing
bytes pairwise, first at `0x108`. The gate did exactly what it was written to do
(GBP-HW-122).

**Where the differences are is the whole story.** Every single one is in byte 0
or byte 2 of its four-byte group. Bytes 1 and 3 — the only bytes the Start-up
Disc and GBI read — differ in **zero** positions across all three pairs. Under
the projection `word = (b1 << 8) | b3` the three frames are identical in 38 400
of 38 400 words (GBP-HW-123). Read through that projection, the eight bars come
back as the outer-group swap of the stimulus on 8/8 bars — H1 exactly, with H2
surviving only on the four colours that are swap-invariant and therefore say
nothing (GBP-HW-124).

**Why that is not being written down as the answer.** The experiment
pre-registered its acceptance criterion. The run failed it. Reading the same
bytes again under a criterion chosen after seeing them is choosing the analysis
to fit the data, and this project does not get to do that on the one question
four previous runs were structurally blind to. U-GBP-011 stays OPEN, the order
stays CORROBORATED where 2026-09-17 left it, and the projection is recorded as a
strong observation that agrees with it.

**The historical audit, which is what makes the case clean.** Bytes 0 and 2 were
not discovered by this run. GBP-VID-003 (2026-09-16) records that neither
reference decoder reads them. GBP-HW-058 records the physical byte-doubling
break; GBP-HW-070 measures 688 byte-0 exceptions in 84 480 words and states they
do not alter what either reference reads; U-GBP-021 forbids consuming byte 0;
U-GBP-029 holds the open question and already answers it operationally; and
`src/gbp/gbp_vsig.h` excludes bytes 0 and 2 from the runtime signature citing
exactly that. Re-measured this round on sig-identical pairs of the already
committed fixtures, the shape is the same as this run's: `vstate-0001` 584/0/46/0,
`vstate-0003` 97/0/25/0, `vstate-0004` 292/0/19/0 by byte class, and
GBP-VIDEO-001 reproduces GBP-HW-070's 688 exactly from the stored bytes. One
thing is genuinely new: **byte 2 deviates too**, which GBP-HW-070 had measured as
zero cases, and which was latent and unmeasured in the September 16–17 fixtures.
Registered as GBP-HW-126 against U-GBP-029, which stays OPEN.

**Free result.** The flag word at x=0, y=0 is exactly `0x8000` here — flag set,
colour 0 — because bar 0 is black and the stimulus never writes bit 15. Every
earlier physical frame had `0xFFFF` there, where the flag cannot be told from
white. First physical separation of bit 15 from the colour payload (GBP-HW-125).

**Ingested:** replay fixture and OGBPCOL1 sidecar versioned under
`captures/fixtures/`, raw log local and hashed, six evidence entries plus the
historical one, `HARDWARE_TESTS.md` result section, `U-GBP-011` and `U-GBP-029`
updated, and `tests/host/test_vcolor.py::PhysicalColor0001` pinning the gate
refusal, the byte-class distribution, the consumed-projection equality, the bar
vector and the flag word — so a future relaxation of the gate fails loudly
instead of quietly re-labelling this run.

**Noted, not changed:** `truncated=1` again, same `PREHANDLERWAIT` line, same
255-character limit, same conclusion — non-blocking, every value that matters is
intact before the cut. It belongs to whichever round touches the logger.

**Next:** pre-register `color-0002` — a new analyser version whose gate is the
consumed projection, justified from the evidence as it stood *before* any colour
run, with the full-raw comparison kept as a reported diagnostic; then a fresh
physical run judged by it. `OGBPCOL1` v1 stays FROZEN and `color-0001` is never
re-labelled. U-GBP-011, U-GBP-029 and U-GBP-033 stay OPEN.

## 2026-09-18 — color-0002 pre-registered: the gate written down before the run that judges it

**Goal:** make the next colour run mean something, without touching the last one.

**The problem, stated exactly.** `color-0001`'s bytes are known. Any acceptance
criterion written now can be shaped by them — not necessarily dishonestly, just
by knowing how it will come out. The only defence is to write the criterion first,
in a versioned file, under a distinct experiment id, and to make the analyser
mechanically incapable of applying it to the old run.

**What was decided, and on what authority.** Bytes 0 and 2 sit **outside the
dependent variable of this experiment**, resting entirely on evidence that
pre-dates any colour run: GBP-VID-003 (2026-09-16) records that neither reference
decoder reads them; GBP-HW-058 and GBP-HW-070 record their physical variability;
U-GBP-021 forbids consuming byte 0; U-GBP-029 holds the open question and already
answers it operationally. They are *not* declared don't-care in general — they
are preserved in full and the full-raw comparison is now a mandatory reported
diagnostic on every run, which is how U-GBP-029 keeps being fed. **Bit 15 is
inside the gate** and is never masked.

**The root cause, which had not been named before.** The runtime's stability
filter `sig[40]` has always consumed bytes 1 and 3 and nothing else
(`gbp_vsig.c:15`, odd indices only). `color-0001`'s offline gate compared all
four. The two halves of the experiment were looking at different data, and that
mismatch — not the device, not the capture — produced the refusal. Under §V4 they
look at the same bytes, and the offline comparison stays exact and authoritative
because a checksum can still collide.

**Implemented as a separate file, deliberately.** `tools/vcolor2.py`.
`tools/vcolor.py` is not modified and gains no option, so `color-0001`'s verdict
stays reproducible forever — a test asserts it through the CLI and asserts the
file has not changed since `bfbca70`. The stimulus and the seven hypotheses are
*imported from it as the same objects*, which is how the record shows they were
not tuned. A confirmatory verdict is keyed to `build_id == color-0002`; anything
else comes back `RETROSPECTIVE` with a verdict string of `retrospective_exact_*`,
never `confirmed_*`.

**The retrospective run, and what it is worth.** Running the new contract on the
`color-0001` fixture passes the gate 38 400/38 400, finds `FLAG15_STABLE` with one
flag per frame, and matches H1 on 8/8 bars. **That proves the analyser, not the
hypothesis**, and the tool says so in its own output. U-GBP-011 is untouched.

**`color-0002` can falsify H1.** A verbatim frame confirms H2 instead; one bar
off confirms nothing. No two of the seven hypotheses produce the same eight
values, so the stimulus discriminates the whole set and an ambiguous verdict
would mean something went wrong rather than that the experiment was weak.

**Also this round, two maintenance defects, in their own commits.** The
`PREHANDLERWAIT` record hit the logger's 255-character line in two physical runs;
it is now two records, split by subject, and a test drives the probe at the
physical magnitudes and asserts `truncated == 0` — it fails against the old
single line, which is how it was checked. And `test_vstate.py` had an ordering
dependency that only `unittest discover` exposed, plus two lines of dead refactor
residue that made it invisible; both runners are green now.

**Noted:** `EVIDENCE.md` uses `##` for its older 61 entries and `###` for the
newer 65. The handoff's citation check only accepted `###`, which it got away
with until the handoff cited GBP-HW-058. The check now scans both depths.

**Next:** one physical run of `color-0002` under §V4.9. `OGBPCOL1` v1,
`tools/vcolor.py` and the §V4 contract are all frozen for it; changing §V4 after
that run requires `color-0003`. U-GBP-011, U-GBP-029 and U-GBP-033 stay OPEN.

## 2026-09-18 — color-0002: the contract held, and U-GBP-011 is closed

**Goal:** ingest and judge the confirmatory run.

**The run.** Build `color-0002`, commit `39f1980`, DOL `d3c1f09e…` — built clean
at that exact commit before the run, the first colour candidate whose hash was
fixed that way. `stop=color_certified`, 440 deliveries = acks = rearms = unmasks,
0 errors, 0 R3 disagreements, clean restore, certification 66.635 ms after the
capture opened. The pre-handler wait elapsed 5.000 000 27 s, and the header reads
**`truncated=0`** — the first physical proof that splitting `PREHANDLERWAIT` into
two records fixed the defect that marked both earlier physical logs.

**The verdict, from an analyser nobody touched.** `tools/vcolor2.py` last changed
at `a86b079`, the commit that pre-registered it; `tools/vcolor.py` at `bfbca70`.
Run unmodified:

```text
STANDING: CONFIRMATORY
VERDICT:  CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP
```

The gate passed 38 400 of 38 400 consumed words, all eight bars uniform over all
4800 of their pixels in all three certified frames, `FLAG15_STABLE`, and exactly
one of the seven pre-registered transformations reproducing all eight values.
Every number was recomputed from the raw bytes before being accepted, not taken
from the analyser's own output.

**The answer.** The VIDEO window delivers the AGB's fifteen colour bits with the
two outer 5-bit groups exchanged: what the AGB wrote in bits 4–0 arrives in bits
14–10 and vice versa, bits 9–5 unchanged. So the reading both references
implement is the displayed colour, and Dolphin's mGBA-derived order is the
divergent model. **CORROBORATED → FACT**, which is exactly the promotion
U-GBP-011's own text said it was waiting for: *"no physical pixel of a known
color has been captured"*. Eight have now been captured, twice.

**U-GBP-011 is CLOSED**, and it closed on conditions it set for itself before the
data existed: a contract written down first, a new analyser rather than an edit
to the frozen one, and a fresh run judged by it. Promoted into
`docs/hardware/GBS-DOL.md` and `docs/protocol/REGISTERS.md`.

**What I deliberately did not close.** Bytes 0 and 2 — U-GBP-029 stays OPEN, and
this run is its fifth corroboration, not its answer: the full raws differ in
2434 / 2483 / 2485 bytes, entirely in bytes 0 and 2, never in 1 or 3. Bit 15 —
the run shows it is not the colour value and is added on the path, since the AGB
wrote zero there, and nothing more; **U-GBP-034 opened** for its origin, because
closing U-GBP-011 without naming that residual would have lost it. U-GBP-033 is
untouched. And within a 5-bit group, a permutation fixing bits 0, 5 and 10 while
rearranging bits 1–4 is not excluded — a limit §V3.19 wrote down *before* the
run, with the follow-up pattern already recorded; the run produced no residual
ambiguity, so it is not triggered.

**Cross-run, as corroboration only.** The three certified frames of `color-0001`
and `color-0002` are byte-identical in the consumed projection, 38 400 of 38 400
in all three pairs, across two runs at two commits with separate power cycles —
while their full raws differ in 2514, 2449 and 2481 bytes, again only in bytes 0
and 2. The device delivered the same picture twice and different bytes 0/2 twice.
`color-0002` confirms itself without this; it is recorded because it is what
U-GBP-029 needs.

**`color-0001` is not re-judged.** It failed its own pre-registered gate and stays
`INCONCLUSIVE_CERTIFIED_RAW_MISMATCH` permanently. The analyser refuses to do
otherwise: any build other than `color-0002` comes back RETROSPECTIVE.

**Next:** the colour question is answered, so the next real blocker is the one
the roadmap already names as following it inside Phase 4 — **GBP-VIDEO-004**,
sustained streaming with a real cartridge: frame pacing, the dropped-block policy
and output modes, which is the bridge to Phase 7. Everything the colour work
established feeds it directly, and nothing in it depends on U-GBP-029, U-GBP-033
or U-GBP-034, all of which stay OPEN.

## 2026-09-18 — GBP-VIDEO-004 designed: the streaming contract, before any of it exists

**Goal:** turn the roadmap's one-line entry for GBP-VIDEO-004 into a
specification precise enough to implement against. No code, no hardware.

**Started from the roadmap, not from an idea.** The requirement is five words —
*sustained streaming, real cartridge, frame pacing, dropped-block policy, output
modes* — plus Phase 4's acceptance sentence and GBP-VIDEO-003's own deferral:
"first rendered frames and KEYPAD writes belong to a later step". Everything in
`HARDWARE_TESTS.md` §V5 beyond those is labelled PROPOSED DESIGN.

**The dependency audit found almost everything already proved.** Service cycle,
40-block frame, geometry, frame classification, the R3 policy, the raw ring, the
signature, the teardown, the 5000 ms wait, the delivery route — all FACT, all
reusable unchanged. Two things are genuinely new: a *moving* source and a
*consumer*. One thing was a surprise worth writing down: **no POC in this
repository has ever called `GX_Init`** — every probe runs `VIDEO_Init` +
`CON_Init` on a single XFB and prints text. The display path is new code.

**The colour result makes the renderer almost trivial.** Because GBP-HW-131
established that the device already exchanges the outer 5-bit groups, the word
arriving from the VIDEO window *is* `GX_TF_RGB5A3` order. So `texel = word |
0x8000` — no channel arithmetic at all, and the only real work is the raster →
4×4-tile permutation, which is exactly what the Start-up Disc's own converter
does. Verified in the container that `GX_TF_RGB5A3 = 0x5` and `GX_InitTexObj`
exist in this toolchain's `ogc/gx.h`, so the recommendation rests on the real
libogc2 rather than on preference.

**Two cadences that are not one.** The AGB runs at 59.727 Hz (GBP-HW-078), the
GameCube VI at ~59.94 Hz, and GBP-PHY-003 already records that nothing
synchronises them. That is ≈ 26 repeated display frames in a 120 s run —
arithmetic, predicted here before the run so it can never be reported as frame
loss.

**The rules the previous rounds paid for are carried forward explicitly.** No
full-frame work between the ACK and the RE-ARM (§V3.23, the microaudit that saved
the colour capture): the producer hands the consumer an *integer*. Never
synthesise pixels: an incomplete frame is recorded and not displayed, the
previous frame is held, and the hold is counted. Never block the producer. A
quarantined frame may not reach the screen for the same reason it may not become
colour evidence.

**One race is designed to be detected rather than avoided by hope.** Four ring
slots at 59.7 Hz give the consumer roughly 50 ms, but that margin is unmeasured,
so the consumer checks a generation counter before and after converting and
counts `consumer_slot_overrun` if the producer reused the slot. A silent tearing
bug becomes a number.

**Three things are deliberately left open**, marked DESIGN DECISION REQUIRED
rather than given invented values: the run duration (which must be justified
against a real interval, the way GBP-VIDEO-002's 120 s was justified against the
Disc's detector window), the converted-queue depth (deferred until conversion
cost is measured, because this repository has measured none), and how the text
report and the GX pipeline share the framebuffer. **No timing is budgeted as a
property** — the first POC measures it.

**The physical matrix keeps three categories apart.** A CONTROLLED motion
stimulus with an embedded frame index is the decisive run, for the same reason
the eight-bar stimulus made `color-0002` decisive: it gives ground truth, so loss
is *measured* rather than inferred. A commercial cartridge gives realism and no
ground truth — a repeated frame cannot be told from a game that did not redraw —
and this design names no title, because the repository names none and the
operator owns that choice.

**None of the open unknowns blocks it**, and the design proves it rather than
asserting it: U-GBP-029's bytes never enter a texel, U-GBP-033's mechanism only
has to be survived and already has been 52 times, and U-GBP-034's bit is inert
for presentation because RGB5A3 sets it regardless.

**Also fixed, both genuinely stale:** §V3.7 still read "STATUS: unresolved" for
the ROM-delivery dependency that route 1 closed two runs ago, and the ROADMAP
carried two contradictory bullets for GBP-VIDEO-003, one saying NOT PHYSICALLY
EXECUTED. Both now say what happened, with the historical text preserved.

**Next:** implement the two pure modules — `gbp_vpix` (raster → RGB5A3 tile) and
`gbp_vqueue` (bounded queue + counters) — with host tests first, against
synthetic frames and against the physical `color-0002` fixture, which carries
eight known colours in known positions and is therefore a real conversion oracle.
Only then the POC and the GX path. U-GBP-029, U-GBP-033 and U-GBP-034 stay OPEN.

## 2026-09-18 — GBP-VIDEO-004 implemented: a consumer, a screen, and the first GX in this repository

**Goal:** build the smallest POC §V5 specified. No hardware, no redesign.

**What was built.** Two pure modules and a POC. `gbp_vpix` converts a raw frame
to a `GX_TF_RGB5A3` tiled texture and turns out to be almost nothing, because
`color-0002` already established the device exchanges the outer 5-bit groups
(GBP-HW-131): the delivered word *is* RGB5A3 order, so the colour step is
`texel = word | 0x8000` with no channel arithmetic and the only real work is the
raster→4×4-tile permutation — 0xF00 bytes in, 0x780 out per block, the same
transformation the Start-up Disc's own converter performs. `gbp_vqueue` is the
producer/consumer boundary, a depth-one mailbox because newest-complete-frame
wins, with the generation guard §V5.7 pre-registered. The POC owns every graphics
call in the program.

**The first GX pipeline here.** Every earlier probe ran `VIDEO_Init` +
`CON_Init` on one framebuffer and printed text. This one initialises GX minimally
— one texture, one quad, orthographic, `GX_REPLACE`, no lighting or filter — from
the sequence in libogc2's own texture example.

**Two of §V5's three open decisions got resolved, and the reasoning is recorded
rather than assumed.** Converted-queue depth is 2, the minimum §V5.8 itself
named. The text report and GX get **two framebuffers**, which answers §V5.15's
question without moving reporting into the service path.

**The decision §V5 did not make at all: where a single-threaded consumer
executes.** It fixed the boundary and the policy but not the site, and
`gbp_vstate_probe_run()` owns the loop. The implementation puts a bounded slice —
one tile row — immediately after the RE-ARM, the pass's last device access, with
the next cause already invited. The slice size is argued from measurement:
`gbp_vsig_block` already reads 3840 bytes in that same path and cost 777–799
ticks in `color-0002`, against 164 µs of slack between deliveries. **That is an
argument for the size, not a measurement of this code**, and the probe
instruments itself so the first run measures it.

**Texture ownership on the real API, not on a guess.** `GX_DrawDone()` would be
simpler and it *blocks*, which §V5.7 forbids here. `GX_SetDrawDone()` plus
`GX_SetDrawDoneCallback()` is the non-blocking form: the GP moves a buffer from
SUBMITTED back to FREE, the CPU only ever fills a FREE one, and with none free the
descriptor is left in the mailbox so the newest-wins rule decides rather than this
code.

**The architecture is machine-checked, not conventional.** `tools/poc_audit.py`
gained a `stream` profile and a per-object prefix exemption: `GX_` is permitted in
`main.o` and forbidden in every other object, `gbp_vqueue_publish` has exactly one
call site inside `gbp_vstate_probe_run`, and `gbp_vpix_block` has none there.
0 findings, and both one-shot ISRs are byte-identical to the physically validated
GBP-VIDEO-001 build.

**Tests found two real defects, both fixed in the module rather than accommodated:**
the pacing aggregate used `t_last_publish != 0` as "have we seen one", silently
discarding a frame published at tick 0; and my own wrap test miscounted the ring
distance. The strongest test uses the physical `color-0002` fixture as a
conversion oracle — converting it produces the eight bars measured on the device,
and converting its two certified frames, which differ in 2434 raw bytes all in
bytes 0 and 2, produces identical textures.

**Real memory, from the build rather than the estimate:** text 356 672 B, data
104 192 B, bss 2 742 204 B → **3.07 MiB of 24**, about 20.9 MiB free. The colour
probe used 8.20 MiB; dropping the episode store and shrinking the frame table is
where the difference went.

**Status, and its ceiling:** `stream-0001` at commit `0816cbe`, sha256
`0dc2c501…`, IMPLEMENTED · SOFTWARE/HOST VALIDATED · PHYSICAL CANDIDATE READY ·
**NOT PHYSICALLY VALIDATED**. No evidence id is allocated to it. Dolphin smoke
passes and says only that it boots and that GX init survives.

**Next:** an independent pre-hardware audit of the exact candidate. Two previous
audits caught things that would have cost a physical run — a 153 600-byte memcmp
in the service path, and a gate stricter than its own question — and this one has
three specific things to attack: the consumer's execution site, the still-open
run duration, and the texture-ownership scheme. Separately, the CONTROLLED motion
stimulus of §V5.18 does not exist yet, so a first run can measure the machinery
but cannot verify frame loss. U-GBP-029, U-GBP-033 and U-GBP-034 stay OPEN.

## 2026-09-18 — the pre-hardware audit of stream-0001 found a blocker

**Goal:** try to invalidate the candidate before spending a physical run. No
hardware, no functional change.

**It worked, for the third time.** The §V3.23 microaudit refused a 153 600-byte
`memcmp` in the service path; the §V4 audit refused a gate stricter than its own
question; this one refused a texture-ownership scheme that can hand the CPU a
buffer the GPU is still reading.

**The blocker.** `on_draw_done()` frees *every* buffer in `TEX_SUBMITTED`, but a
DrawDone token certifies only the commands queued before it. Simulating the real
state machine: frame 1 submits buffer 0, frame 2 submits buffer 1 before token1
fires, token1 then frees **both**, and frame 4 refills buffer 1 while the GP may
still be reading it. Two things make it worse than the arithmetic suggests. It is
**invisible** — `no_free_buffer` does not increment in that sequence, so the only
symptom is a torn frame, which §V5.21 refuses as a criterion. And it lives in code
that has **never executed**: Dolphin matched a line printed before the probe runs,
so `pump()` and every GX call inside it have never run anywhere.

**The number I got wrong last round, corrected from physical data.** I justified
the slice placement with "164 µs of slack between deliveries". That figure is
`capture_elapsed / deliveries` — the mean cycle *period*, work plus idle. The real
idle window is the RE-ARM→next-cause gap, and `vstate-0004`'s 80 cycle records
give median **42.8 µs with p25 = 1.9 µs**: on **34 % of cycles the next cause is
already latched when the RE-ARM completes**. A ~20 µs slice exceeds the whole
window a third of the time. Nothing is lost — `wait_next()` is a busy poll and the
cause latches — but the justification was void and the placement is PLAUSIBLE BUT
UNMEASURED, not proven safe.

**Two things the audit established that simplify the design.** The pump runs with
IRQ 26 **already masked** (`gbp_irq_service.c` step 7 re-masks before the drain),
so the GBP ISR cannot preempt a conversion; and producer and consumer are the
**same thread**, so the queue needs no barrier, no `volatile` and no critical
section. The entire synchronisation surface is one `volatile uint8_t[2]` — and it
has exactly one bug.

**What the audit cleared, so it is not re-litigated.** RGB5A3 byte order:
decoding the physical `color-0002` frame through the real tile mapping gives bytes
`80 00 / FC 00 / 83 E0 / 80 1F / …`, which GX reads as the eight measured colours
— big-endian `uint16_t` stores are exactly right and no conversion is needed. The
tile mapping, exhaustively. The flush size and ordering. The R3 policy, with both
one-shot ISRs byte-identical to the GBP-VIDEO-001 build and the `stream` audit
profile at 0 findings. Instrumentation cost: four `mulli`, zero `divw`. Memory:
4.23 MiB of 24 including both framebuffers.

**Test quality.** Eight mutations of the two pure modules — generation check
removed, incomplete published, quarantined published, tile row/column swapped,
byte 0 read instead of byte 1, presentation bit dropped, flag15 uncounted, mailbox
keeping the oldest — **all eight caught**. And the one that matters most cannot be
run: `main.c` has no behavioural test, and the host tests assert only that
`on_draw_done` *appears* in the source. That is exactly how the blocker got in,
and any fix that does not close that gap is a fix nobody can check.

**Decision: B — SOFTWARE FIX REQUIRED BEFORE HARDWARE.** Full finding list and
the fix order in `HARDWARE_TESTS.md` §V5.26.

**Next:** an implementation round for §V5.26.9, then a re-audit. U-GBP-029,
U-GBP-033 and U-GBP-034 stay OPEN and none of them is involved.

## 2026-09-18 — stream-0002: the ownership machine moves somewhere it can be tested

**Goal:** fix what the pre-hardware audit rejected, and produce a new candidate.
`stream-0001` stays REJECTED and was neither rebuilt nor re-labelled.

**The fix is not "be more careful in main.c".** The blocker survived a green
suite because the state machine lived in target-only code whose tests asserted
that a *string* appeared in the source. So ownership moved to
`src/gbp/gbp_vpresent.{h,c}`, which knows nothing about GX, VI or libogc2 and
which a host test drives state by state. The rule it enforces is the one that can
be proved rather than the one that is most general: **at most one draw-done token
in flight**, and the callback releases **exactly one buffer, by index**.

**A mutation caught a gap in my own tests, which is what mutations are for.**
Restoring `stream-0001`'s "free every SUBMITTED buffer" callback was **NOT**
caught by the behavioural suite — because with one token in flight two buffers can
never both be SUBMITTED in a legitimate sequence, so the defect is *neutralised by
the architecture* rather than detected. That is defence working, and it is also a
single point of failure: relax the one-token rule later and the callback becomes
dangerous again with nothing to say so. A white-box test now builds the
two-SUBMITTED state directly and requires the callback to release exactly the
indexed buffer.

**The number I had wrong is now load-bearing in the other direction.** The audit
showed the real RE-ARM→next-cause window is median 42.8 µs with **p25 = 1.9 µs** —
on about a third of cycles the next cause is already latched when the RE-ARM
completes. So the pump now reads the cause first and **does nothing at all when
one is pending**, at the cost of one extra `poll_intsr` per cycle. That does not
remove a cause arriving *during* a slice; `cause_arrived_during_pump` counts that,
defined mechanically as "not pending before, pending after", and claims nothing
about causality. The slice stays one tile row and stays **PLAUSIBLE BUT
UNMEASURED**.

**The framebuffer divergence was real and is fixed.** `stream-0001` said "two
framebuffers", which was true and misleading: they were the stream and the
console, not a double buffer, and GX copied into the one the VI was scanning.
`stream-0002` keeps three, and asks the module which is safe from two
non-blocking VI reads. When neither is, the present is **skipped and counted** —
never waited on. `VIDEO_WaitVSync()` appears nowhere in the consumer path and a
test asserts it.

**The display path is no longer dead code.** `display_selftest()` walks the whole
path once before the probe from a synthetic coordinate gradient — no stimulus
value, so it teaches the runtime nothing — and emits its result on the Gecko
channel, which Dolphin now *asserts*: `SELFTEST ok=1 converted=1 released=1
submits=1 drawdone=1 releases=1 xfb=1`. The draw-done callback really does fire
under Dolphin, so acquire → fill → flush → submit → token → callback → release
has now executed end to end somewhere. That is evidence about the code and
nothing about the device.

**Teardown got a lifecycle.** Shutdown stops publishing and pumping, drains the
one token that may be pending with the single `GX_DrawDone()` in the whole
program — permissible only because the Game Boy Player has already been restored —
and restores the *previous* draw-done callback instead of assuming this program
owns the hook for ever.

**Also corrected:** the `!blk` path that claimed "the guard below rejects" and did
not; `no_free_buffer` renamed `acquire_no_free_texture` and documented as a
throughput fact rather than the GPU-safety guarantee it was read as.

**And a mistake of my own, worth recording because it nearly produced three false
results.** The first mutation harness reverted with `git checkout`, which cannot
revert an untracked file — `gbp_vpresent.c` was new this round — and silently
reverts a legitimately modified one. So three mutations stacked on top of each
other, `gbp_vqueue.c` lost its uncommitted work mid-run, and two mutations
reported "NOT CAUGHT" when the truth was that the build was broken and no test
had run at all. The harness now backs up the file and refuses to report a result
when the compiler errors.

**Unchanged on purpose:** R3 and the service order (both ISRs still byte-identical
to the GBP-VIDEO-001 build, audit 0 findings), `F_SOURCE_DEFERRED` (checked
against §V5.9's exact words — the implementation and the contract agree), the
RGB5A3 mapping and the tile permutation.

**Status: `stream-0002`, IMPLEMENTED · SOFTWARE/HOST VALIDATED · PRE-HARDWARE FIX
COMPLETE · PHYSICAL CANDIDATE READY · NOT PHYSICALLY EXECUTED.** No evidence id.

**Next:** a focused re-audit of ownership, timing observability and teardown —
not a hardware run. Three previous audits each found something that would have
cost one. U-GBP-029, U-GBP-033 and U-GBP-034 stay OPEN.

## 2026-09-18 — the focused re-audit of stream-0002: DECISION A, with one reporting condition pre-registered

**Goal.** Decide whether the exact `stream-0002` artifact is safe enough and
observable enough for **one** supervised physical smoke. Not whether streaming
works — that is §V5.21's job, after a run exists. No hardware, no functional
change, no `stream-0003`.

**What was done.** §V5.28, in six areas: texture ownership and the one-token
rule, main ↔ callback synchronisation, XFB ownership, pump priority and
observability, the teardown callback lifecycle, and whether the display self-test
is valid. Everything else `stream-0002` did not touch was left alone.

**Method, and why it is worth naming.** Three things in this round were proved
from artifacts rather than from reasoning:

- the candidate **reproduces byte-for-byte** from a detached worktree at
  `2457d51` — 466 272 B, sha256 `76fa1ff7…` — once the embedded identity string is
  supplied, because inside the container a worktree cannot resolve `HEAD` and the
  Makefile falls back to `unknown-dirty`;
- the **compiler ordering** was read out of `powerpc-eabi-objdump`: both volatile
  stores in `gbp_vpresent_submit` retire before `blr`, and `GX_SetDrawDone()`
  lives behind a control dependency on that function's return value. "Single-core"
  was never used as the argument, because single-core settles preemption, not
  reordering;
- the **libogc2 semantics** every non-blocking claim rests on were re-read from
  the pinned source (`external/libogc2` @ `ca03fb75`), not from memory.

A breadth-first enumeration of a **superset** of the ownership machine — main may
start any entry point at any time, the interrupt may fire between any two shared
accesses, including adversarially with no token armed — visits 705 states with a
maximum of **one** simultaneously `SUBMITTED` buffer and no main-side write to a
buffer the GP owns. The checker was validated by injecting the defects into the
model: they break it.

**Result: DECISION A — `stream-0002` is safe enough for the first supervised
physical smoke**, with one known reporting condition recorded before execution.

The audit found **no defect in the service path, none in the ownership machine
and none in the teardown**. Every safety property it set out to check was proved.
That is what A means; it does not mean nothing was found — eight findings are
recorded in §V5.28.13.

**The reporting condition (R1, HIGH — reporting, not service or ownership).**
`display_selftest()` calls `submit_ready()`, whose success path calls
`gbp_vqueue_note_presented()`. The self-test frame is synthetic and never passes
through the queue, so `consumer_frames_converted` is not incremented — and
`gbp_vqueue_balanced()` carries a **deterministic +1 presentation offset** for the
whole run. The candidate binary already proves it: under Dolphin, with no Game
Boy Player attached, it prints `presented=1 … counters DO NOT BALANCE` on screen.

Nothing is corrupted, no invariant is touched and the device cannot observe it.
The raw counters remain authoritative; `gbp_vqueue_balanced()` is a derived
predicate and is the only thing the offset touches. The correction is exact, and
the run itself prints the field that selects it (`SELFTEST … xfb=`), so it was
**pre-registered before physical execution** rather than rationalised after:

```text
converted == (presented - SELFTEST.xfb) + overrun
```

**Frozen until that run exists:** artifact identity unchanged (`stream-0002`,
`2457d51`, 466 272 B, `76fa1ff7…`); **no rebuild**; **no `src/`, `poc/` or
`tools/` change**. The artifact that was audited is the artifact that runs. R1 and
R8 land in `stream-0003`, after the first run.

**Seven more findings, none blocking.** R3 is the one to watch: `IRQ_PI_PEFINISH`
is unmasked by `__GX_PEInit` and is never masked here, so the draw-done callback
**can** preempt the GBP service path between the ACK and the RE-ARM — a new
interrupt source `vstate-0004` did not have, ≤ 16 instructions, on roughly 6 % of
cycles, and visible afterwards as outliers in the existing per-cycle histogram.
R8: `gbp_vpresent_consistent()` is evaluated only in the self-test and the final
report, so the run can claim the invariants hold **at end**, not throughout. R7:
the re-offer loop takes the lowest-index `READY` buffer, so two simultaneously
ready buffers can be shown out of order. R2, R4, R5 are observability and
cosmetics.

**Newly confirmed.** The display path genuinely runs and the callback genuinely
comes from hardware: `on_draw_done` appears exactly once in the whole linked
image — as its own symbol — with no call site anywhere, so `drawdone=1` can only
have come from libogc2's PE FINISH handler. The teardown order
(shutdown → stop feeds → drain → restore) is confirmed in machine code, including
the case where `GX_DrawDone()`'s own second token fires after the restore.

**Rejected.** That a green suite meant the mutations were caught: the harness
restored files with `shutil.copy2`, which preserves mtime, so `make` re-ran the
**previous** mutant's binary and three of the seven results were stale. Fixed,
baseline rebuilt green, all seven re-run: **7/7 caught**, including A1 — the exact
`stream-0001` defect that the previous round's suite did **not** catch.

**Tests executed.** 19 unit binaries, 0 failures; 556 host tests, OK; Dolphin
smoke re-run on the exact candidate: PASS, `SELFTEST ok=1 converted=1 released=1
submits=1 drawdone=1 releases=1 xfb=1`. `make -C tests/unit` and `git status`
verified clean after every mutation, by sha256, with **no `git checkout` on any
file**.

**New unknowns.** None promoted. U-GBP-029, U-GBP-033 and U-GBP-034 stay OPEN.

**Next:** run the first supervised physical smoke of the exact `stream-0002`
artifact, under §V5.20/§V5.21, with the pre-registered R1 identity applied when
the report is read. R1 and R8 land in `stream-0003` afterwards; R3 is read out of
this run's cycle histogram before anyone calls the design timing-safe. The CONTROLLED indexed motion stimulus of §V5.18 still does not
exist, so no result from this run may be cited as evidence of zero dropped source
frames.

## 2026-09-18 — the first physical smoke of stream-0002 aborted at its first gate, and the gate was right

**Goal.** Locate exactly which predicate produced `store_or_bounds_invalid` on the
first physical run of `stream-0002`. No hardware, no behaviour change, no
silent fix.

**Result: found, reproduced on the host, and classified C — an allocation /
configuration bug in the POC**, with a contributing D (a capacity assumption in a
design document that was never checked against the code).

**The path is one statement.** `main.c:652 gbp_vstate_probe_run()` →
`gbp_vstate_probe.c:790 if (!st || !gbp_vstate_storage_ok(st))`. That is the first
gate of the probe and the statement before any transport, register or interrupt
work. Twelve predicates; **three** are false on this build; short-circuit
evaluation means **`!s->episode_raw` (`gbp_vstate.c:72`)** is the one that fired.

**The cause is one call.** `main.c:569-570` passes `episode_raw = NULL,
episode_raw_cap = 0` and `frames_cap = STREAM_MAX_FRAMES = 4096` against a
required 16384. Deliberate and documented — §V5.22 proposed dropping the episode
store for a streaming run — and **never checked against the model**.

**The gate was right, and this is the important part.** Two sites dereference
`episode_raw` with no NULL check: `gbp_vstate_probe.c:812` memsets 2 949 120 bytes
through it, and `gbp_vstate.c:739` (`preserve_frame`) writes a whole frame into it
whenever an episode opens, guarded only by `ep->raw_slot`, which is assigned from
`episodes_n` alone. Had the run started, the probe would have memset 2.81 MiB over
GameCube low memory **before touching the device**. So the fix is *not* to relax
the validator; a diagnostic unit test now pins that
(`test_a_null_episode_store_must_stay_refused`, +6 checks, green).

**The memory was never the problem.** Reconstructed from the run's own `ENVBUF`
line: gx_fifo, both textures, audio_raw, raw_ring, event_store and frame_store are
contiguous and disjoint, every DMA/GX target 32-byte aligned, highest static byte
`0x002c8920` = **2.78 MiB of MEM1's 24 MiB**, no overflow, all inside BSS
(`0x80074d4c`..`0x80337d98`, 2 895 948 B).

**`static_bytes=6922240` explained, and it is misleading.** It is
`gbp_vstate_static_bytes()`, computed **entirely from `#define`s** — the capacity
constants of the GBP-VIDEO-002 model. It reads no state. This build actually
allocated **1 798 144**; the 5 124 096 difference is a frame table and an episode
store that do not exist, less a raw ring larger than the constant assumed. For
every earlier build the constants and the allocation coincided, so the number was
accidentally true. Worse: the `VSTATE stores frames=16384 …` line prints the
constant too, so **the log line that should have exposed this defect concealed
it**.

**Why three audits missed it.** `git show 0816cbe` proves the same configuration
shipped in `stream-0001` — the defect is as old as the first streaming candidate,
and `stream-0001` would have aborted identically. §V5.28 scoped the memory design
out because "`stream-0002` did not touch it", which was true and beside the point:
the memory design *had* changed relative to `color-0002` and `vstate-0004`, both
physically validated, both of which pass 16384 frames and a real 2.81 MiB episode
store. **An audit's "unchanged, therefore out of scope" must be measured against
the last physically validated build, not against the previous candidate.** No test
covered it either: `gbp_vstate_storage_ok()` has unit tests, but nothing checked
the POC's *call* to it, and `main()` is not host-compiled.

**The GX self-test is not implicated**, checked rather than assumed: the predicate
reads only fields set by `gbp_vstate_init()`, `src/gbp/` contains no allocation of
any kind, and `main()` runs `video_setup()` → `gx_setup()` → `gbp_vstate_init()`
→ `display_selftest()`, so those fields were fixed before the self-test ran.

**Newly confirmed on hardware (GBP-HW-134…137).** The GX display path executed on
a real GameCube and the draw-done token came back (`drawdone=1 releases=1
xfb_presents=1 consistent=1 cb_restored=1`) — the first physical GX evidence in
this repository. R1 reproduced exactly as pre-registered (`converted=0
presented=1 SELFTEST.xfb=1 balanced=0`), which validates the pre-registration
method. And `deliveries=0 acks=0 rearms=0 handler_installed=0`: **nothing of the
service was exercised**, so no claim about video, streaming or the device follows
from this run in either direction.

**Rejected.** That "there is enough memory" answers the question — it does not;
the difference between 6 922 240 and 1 798 144 had to be resolved, and resolving
it is what identified the phantom stores. Also rejected: that the validator is
stale. Half of it is (the frame-table capacity, a safe reduction the contract
forbids), half of it is load-bearing (the episode store, which the model
dereferences).

**Proposed correction, NOT applied** (this round is not authorised to change
`src/` or `poc/`): allocate the full frame table and the episode store in the POC
— `poc/`-only, +5 308 416 B, bss 2 895 948 → 8 204 364 (7.82 MiB), about 10.0 MiB
of 24 MiB total, comparable to the validated colour probe. Alongside it: log the
**actual** capacities beside the constants, and add the host guard that parses the
POC's `gbp_vstate_init()` call.

**Next:** `stream-0003` — this store fix plus R1 and R8 — then its own
pre-hardware audit, scoped against `color-0002`/`vstate-0004`. `stream-0002`
stays historical and is never rebuilt or re-labelled.

## 2026-09-18 — stream-0003: the storage contract satisfied, R1 retired, R8 latched

**Goal.** Turn the physically identified cause of `stream-0002`'s pre-service
abort into a candidate that actually satisfies the contract, and retire the two
reporting defects the previous audit had left standing. No hardware.

**The fix is in the caller, not in the gate.** The POC now declares
`frame_store[GBP_VSTATE_MAX_FRAMES]` and `episode_raw[GBP_VSTATE_EPISODE_RAW_BYTES]`
and passes both to `gbp_vstate_init()`, with the capacities derived from the
arrays themselves so the declaration and the call cannot drift. **Not one
requirement of `gbp_vstate_storage_ok()` was weakened** — a host guard asserts
each one textually, and the gate is now *defined* as "`gbp_vstate_storage_fault()`
returns NULL", so the boolean and the diagnostic cannot diverge. Six
`_Static_assert`s over the actual arrays mean a future shrink stops the build
instead of costing a run.

**The two capacity ideas are named apart.** `gbp_vstate_static_bytes()` described
the model's constants and read like a footprint; it is now
`gbp_vstate_required_capacity_bytes()` — same value, 6 922 240, so historical logs
keep their meaning — beside a new `gbp_vstate_configured_bytes(s)` that counts
only stores that exist. Two log lines carry both, and the abort now names the
field: `reason=store_or_bounds_invalid field=episode_raw_null`.

**Measured, not inferred.** text 363 744, data 107 680, **bss 8 204 404** (the
prediction was 8 204 364; the 40 bytes are linker alignment), DOL 471 680. Every
store resolved from the linked ELF: no overlap, no misalignment, nothing outside
BSS, every DMA/GX target 32-byte aligned. **10.03 MiB of MEM1's 24.00 MiB**, with
13.96 MiB of arena left after the three XFBs.

**R1 retired.** `submit_ready()` takes the queue the presentation belongs to; the
self-test passes NULL and counts its own presents and repeats. `gbp_vqueue_pristine()`
is the new assertion — every scientific counter still at its initial value when
the probe is entered — and it is part of `selftest_ok`, of the Gecko line and of
the report. Proved behaviourally: one `note_presented()` from the self-test breaks
both `pristine()` and `balanced()`; a repeat breaks only `pristine()`, which is
why the POC asserts the stricter one.

**R8 latched.** `gbp_vpresent` audits itself at every transition and latches a
failure even if the state heals — main side and interrupt side in separate
counters, so neither can lose the other's increment. The audit reads state and
writes only counters; the valid state machine is byte-for-byte what `stream-0002`
had, and the `submit()` audit runs after both stores so the deliberate
one-instruction transient is never counted. The report separates
`consistent_at_end` from `invariant_failures` during the run.

**Dolphin says the gate is passed.** `COUNTERS balanced=1 sci_clean_at_probe=1
inv_fail=0 inv_checks=4 consistent_at_end=1 storage_fault=-`, and on screen
`status=abort_inconsistent … teardown=stage_a` — `stream-0002` never got past
`abort_store_unavailable`; `stream-0003` reaches stage A and stops there because
Dolphin has no Game Boy Player, exactly where `color-0002` and `vstate-0004` stop.
`balanced=1` with **no correction of any kind** is R1 retired, measured on the
binary.

**The lesson, mechanised.** A host guard now compares the stream POC's stores
against **`vstate-0004` and `color-0002`** — the builds that actually ran — and
not against the previous candidate. That is the §V5.29 finding turned into a
check: three audits said "unchanged" about a configuration that had changed
relative to every physically validated build.

**Unchanged on purpose:** R3's PE FINISH behaviour, the post-RE-ARM pump
placement, the one-tile-row slice, the RGB5A3 mapping, the generation guard, the
source-disagreement and `F_SOURCE_DEFERRED` policies, the mailbox semantics, R5,
R7 and the controlled-stimulus design. The timing instrumentation is identical,
and **the slice placement is still not claimed to be timing-safe**.

**Tests.** 19 unit binaries, 792 077 checks, 0 failures; 574 host tests OK;
`make stream-audit` clean with the interrupt path byte-identical to the
physically validated GBP-VIDEO-001 build; `make stream-dolphin` PASS. New
adversarial coverage: NULL episode store, episode store one byte short, frame cap
4096, frame cap max, AUDIO raw one byte short, a self-test presentation reaching
the scientific counters, a transient impossible ownership state, and the
required-versus-configured distinction.

**Not claimed.** Sustained streaming works. Nothing has streamed on hardware, and
`stream-0002` is **not** re-interpreted as a streaming failure — streaming was
never reached.

**A note on the environment, not the project:** the repository's fuseblk mount
lost directory entries under `build/` mid-build several times this round, which
presents as `mkdir: File exists` or vanishing `.o` files inside the container.
Recreating `build/` fixed it. It is a host filesystem artifact and no build
output was trusted until a clean rebuild reproduced it.

**Next:** a SMALL pre-hardware audit of `stream-0003`, limited to the storage
configuration against `vstate-0004`/`color-0002`, the address ranges, R1
isolation, the R8 latch, the unchanged instrumentation and the exact artifact
identity. Then, and only then, the physical run.

## 2026-09-18 — stream-0003 audited (DECISION A), and Dolphin turns out to have a Game Boy Player

**Two things, deliberately kept apart.** A short pre-hardware audit of the
`stream-0003` candidate, and the correction of a premise this project had been
carrying: that Dolphin has no Game Boy Player.

**The audit is short because §V5.28 already did the long one.** The ownership
machine, the compiler ordering, the libogc2 semantics, the XFB model, the cache
ordering and the teardown were proved there, and `stream-0003` did not touch any
of them. What was checked here is what changed:

```text
storage   frames_cap 16384, events_cap 4096, raw_ring 737280 (4 slots),
          episode_raw non-NULL 2 949 120, audio_raw 12288
          gbp_vstate_storage_fault() == NULL, storage_ok() == 1
R1        after the self-test's exact shape every scientific counter is 0,
          gbp_vqueue_pristine() == 1, balanced == 1 with NO correction
R8        a valid lifecycle latches 0 in 4 checks; an injected two-SUBMITTED
          state is LATCHED, survives healing, and consistent_at_end still
          recovers to 1 — the two claims are finally separate
memory    no overlap, no misalignment, all inside BSS; 10.03 MiB of 24.00
parity    gbp_vpix untouched; the pump placement, slice, cause precheck, timing
          counters, R3, PE FINISH policy, mailbox and generation guard unchanged
```

The candidate also **reproduced byte-for-byte** — `2f8e362e…` from the same
source with `GIT_COMMIT=03b32a9` — after a warning check accidentally rebuilt it
at HEAD. The exact artifact was restored and the accident became a proof.

**DECISION A: `stream-0003` is ready for the first physical GBP stream smoke.**

**Now the premise.** "Dolphin has no GBP" was wrong about the emulator and only
ever true of the launch configuration the smokes used — and
`docs/protocol/REGISTERS.md` had been citing Dolphin's GBP model for register
semantics all along, which should have been the clue.

The installed Flatpak (`stable`, **2606a**, flatpak commit `88a604c2…`, built
2026-08-11) contains `HSP::CHSPDevice_GBPlayer`, `HSP::CGBPlayer_mGBA` and the
config keys `HSPDevice` and `GBPlayerRom` — read out of the installed binary, not
inferred from master. Enabling it needs two session settings and nothing else:

```text
Dolphin.Core.HSPDevice  = 2    (None 0, ARAMExpansion 1, GBPlayer 2)
Dolphin.GBA.GBPlayerRom = <a .gba>

no GBA BIOS       GBACore sets useBios = 0 — mGBA's HLE BIOS is used
no Start-up Disc  HSPManager::Init() creates the device at hardware init
reachable         through ARAM DMA, which is the path Open-GBP already uses
```

**And it works, in the sense that matters: the emulated GBP is visible to
Open-GBP's protocol.** With everything else identical and an isolated Dolphin
profile:

```text
HSPDevice=0 (None)                → abort_inconsistent   / inconsistent
HSPDevice=2 + AGS-rom.gba         → abort_control_shape  / control_not_idle_shape
HSPDevice=2 + colour-bars cart    → abort_control_shape  / control_not_idle_shape
```

The abort changes and the only variable is the HSP device. AR_INFO succeeds, the
probe reads CONTROL from the emulated device, and rejects it.

**The first divergence, named exactly.** Open-GBP's 003A idle gate requires
CONTROL bit `0x10` (MASK_IRQ) SET and bits `0x0C` (3V|5V) CLEAR — hardware
presents `0x90`. Dolphin's model zero-initialises `m_control`, stores
`value & 0xFC` on a write, and ORs in only `0x02`/`0x01` on a read, so a host
reads `0x02` at power-on and **bit 0x10 is never set by the model**. The gate
fires deterministically.

That is a **model divergence, not an Open-GBP omission**, and nothing was
changed: relaxing a physically grounded gate to satisfy an emulator would invert
the authority hierarchy. A diagnostic-only emulator mode is a design question for
another round.

**A second divergence, recorded before someone trips on it:** Dolphin's VIDEO
read sets byte0 = byte1 and byte2 = byte3. Physically they differ (GBP-HW-133).
**Dolphin can never be evidence about U-GBP-029**, in either direction.

**Newly available, and worth having:** `make stream-dolphin-gbp` — the emulated
GBP as a reproducible pre-hardware gate, in an isolated profile with session-only
overrides that never touch the operator's own configuration. It cannot replace
hardware and cannot promote a FACT, but it now exercises strictly more of the
runtime than the old smoke did.

**Not claimed.** No video frame was produced by the emulated GBP — the probe
stops at the CONTROL gate — so there is no AGS picture to report and none is
asserted. Sustained streaming still works nowhere.

**Tests.** 19 unit binaries / 792 077 checks / 0 failures; 575 host tests OK;
`stream-audit` clean with both one-shot ISRs byte-identical to the physically
validated GBP-VIDEO-001 build; `stream-dolphin` PASS; zero compiler warnings.

**Next:** the first physical GBP stream smoke of the exact `stream-0003`
artifact — short, supervised, no rebuild, operational/timing/display only, and
explicitly not a decisive frame-loss validation.

## 2026-09-18 — the indexed stimulus met its own reference model, and two of its assumptions died

**Design round 2, offline only.** No ROM, no hardware, no change to `src/`,
`poc/` or the candidate. `stream-0003` is untouched and the next physical action
is unchanged: the first supervised GBP stream smoke of `2f8e362e…199e3`.

The previous round produced a design proposal. This round built
`tools/istim.py` — the reference model the ROM will later be verified against —
and ran the design against it. **Two assumptions did not survive, and finding
them cost nothing because no ROM existed yet.**

**The source observation point is safe, and now frozen.** Traced in the real
code: `gbp_vsig_block()` runs at block receipt (`gbp_vstate_probe.c:1394`),
`gbp_vstate_block()` accumulates it (`gbp_vstate.c:1143`), `close_frame()` writes
`f->sig[40]` (`:876`), and `gbp_vqueue_publish()` runs **after** that, guarded by
`step.frame_closed`. `frame_store[]` is never touched by the consumer, so no
mailbox, conversion or display loss can remove a frame from it. No STOP.

**Assumption 1 died: `sig[40]` cannot carry the frame ID, and the proof is
constructive, not statistical.** The complement-pair strip layout — rows
`4b+0/4b+2` painting the payload and `4b+1/4b+3` its complement — makes the count
of ONE symbols per parity class exactly **(92, 92)** for *every* frame ID. An
additive checksum sees only parity-weighted sums, so the ID is annihilated
exactly. What is left is the bar, with period 35: `sig(f,b) == sig(f+35,b)`,
verified. Within one period only 15 of 35 phases are even distinguishable. So
`sig[40]` cannot identify a frame and **cannot recover the bar phase either**.
Level 1 is rejected outright.

Adversarial characterisation made it concrete, and the results are locked as
tests: the checksum **detects** a single changed bit and a block from the
adjacent frame, and **misses** a block from frame+35, a duplicated row, a
compensating ±1 pair, and — decisively — **strips substituted from another frame
ID or another block index**. Collisions were *constructed*, which is a stronger
statement than failing to find one.

**Assumption 2 died: `barpos(f,b) = (f + 7·b) mod 35` was defective.**
`gcd(7,35) = 7`, so the 40 blocks collapsed onto **5** phases instead of
spreading. The multiplier is now 8. The bar remains a freshness witness and was
never an identifier, but a phase repeating every 5 blocks is still a defect, and
a geometry test caught it.

**The scientific population was too strong and is now narrowed.** "Every frame
the AGB presented during the capture window" cannot be claimed: frames before the
first stored frame and after the last are invisible, because blocks arriving
before the first boundary are counted and never become a frame. The claim is now
about *transitions between the first and last intact observed IDs*. **No anchor
was invented to rescue the old wording.**

**Three corrections of record.** Bit 15 cannot affect the ID decode — the decoder
reads `colour15 = word16 & 0x7FFF` and both symbols live below bit 15 — so an
unexpected flag coordinate is a **U-GBP-034 observation, not an integrity
failure**; but `gbp_vsig_block()` does *not* mask bit 15, so the flag at (0,0)
does shift `sig[0]` of block 0, and the model renders both variants. The
half-range delta `2^23` is now `UNRESOLVED_HALF_RANGE` and **never** a forward
gap. `SOURCE_DUPLICATE` became **`OBSERVED_DUPLICATE_ID`**, mechanism UNKNOWN,
because a repeated ID could be transport, stimulus or sampling.

**The honest cost of doing it properly.** Preserving consumed words verbatim:
all 8 strip copies = 52.8 MB for 30 s (does not fit), one L+R pair = 13.2 MB
(marginal against 13.96 MiB free), **one normalised copy per block = 6.59 MB
(fits)**. Raw frames would be 275 MB. But every one of those is
**stimulus-aware** — a fixed ROI at the strip columns is stimulus knowledge even
though it decodes nothing, and the design says so instead of disguising it. The
better option is a **per-block CRC-32** alongside the existing signature: 160 B
per frame, the same cost as `sig[40]`, stimulus-agnostic, and with a collision
structure that is actually usable. It is a `src/gbp/` change and was **not**
made.

**Verdict: B — one more revision before the ROM.** The stimulus itself survived
every test; the signature architecture did not. Three things must be settled
first: the witness strategy, whether an anchor for the unobservable edges is
wanted, and how the ROM will *measure* that its update fits in VBlank (ARM7TDMI
has no divide, so the `mod 35` must become a running counter). **None of them
blocks the first physical smoke.**

**Tests.** `tools/istim.py` plus 44 new host tests: geometry tiles 240 columns
and 160 rows exactly, the symbols are fixed points of the confirmed colour
mapping (so the ID decode does not depend on U-GBP-011), seven CRC known-answer
vectors, exhaustive single-bit CRC sensitivity, the eight-copy decoder with
inversion and reversal normalised, the wrap `0xFFFFFE→0x000001`, and a
compile-and-compare of the Python model against `src/gbp/gbp_vsig.c` itself.
619 host tests OK.

**Next:** decide the witness. Recommended: the stimulus-agnostic per-block
CRC-32, in a round that audits it like any other runtime change.

## 2026-09-18 — OGBPIDX1: the indexed stimulus contract is frozen

**Design round 3, offline only.** No ROM, no hardware, no `src/`, no `poc/`.
`stream-0003` is untouched and the next physical action is unchanged: the first
supervised GBP stream smoke of `2f8e362e…199e3`.

Round 2 ended at verdict B with three blockers. All three are resolved and the
contract is **frozen as format version OGBPIDX1**. Verdict **A**.

**Blocker 1 — the witness.** `gbp_vsig_block()` is accepted as not being an
identifier and is not tuned to become one. The decisive evidence is now **one
lossless strip copy per VIDEO block: STRIP-L, local row 0, i.e. screen row 4b,
54 words = 108 B per block, 4 320 B per frame.** That row was chosen because it
is the first line of the block on the wire, so a runtime copy is one stride at
the head of the delivery. The other seven copies stay in the picture as
diagnostic redundancy and carry no part of the decisive claim. **The witness does
not prove pixel-perfect equality of the frame** — it proves frame-ID sequence
integrity, block composition integrity and block position integrity, which are
three separate questions.

**Blocker 2 — the claim.** Narrowed to transitions between the first and last
intact IDs observed at the pre-publication capture layer. Frames before the
first and after the last are **unobservable and nothing is claimed about them**.
**No anchor was invented** to rescue a broader wording.

**Blocker 3 — the stimulus validates itself.** Mode 3 has one framebuffer, so the
ROM must prove it finished inside VBlank rather than assume it. Mechanism, from
GBATEK: **VCOUNT** (160..227 are the VBlank lines) plus **Timer 0 at F/64**
(262 144 Hz, 3.81 µs per tick, 1 309 ticks per VBlank) — both free-running reads.
The payload now carries `STATUS`: bit 7 a **sticky FAULT latch**, bits 6..0 a
**monotone-minimum VMARGIN** in remaining VBlank scanlines, initialised to 0x7F
("no update measured yet", unreachable since VBlank is 68 lines). FAULT seen
anywhere ⇒ `STIMULUS_INVALID_FOR_DECISIVE_CLAIM`.

**The layout had to change, and every number was recomputed.** STATUS cost 8
columns per strip: strips are 54 bits, CONTENT shrank from 144 px to 128 px, and
the bar period fell from 35 to **31** (prime; gcd(8,31)=1, so b=0..30 give all 31
phases and nine blocks repeat). The old 30-bit CRC vectors are **retired, not
carried forward** — ten new known-answer vectors are frozen, and a single-bit
flip anywhere in the 38-bit payload is still impossible to miss.

**The status delay is real and is written down.** STATUS in frame f certifies
updates 0..f−1, never f itself. So for observed intact frames A..Z the decisive
set is A..Z−1: one frame lost to the trailing edge, one to the delay. For ~1 792
observed frames that leaves ~1 790 decisive transitions, and the analyzer reports
both exclusions instead of dropping them quietly.

**Capacity derived, not picked.** 30 s × 59.737 Hz = 1 792.1 frames, +10 % for
clock tolerance and for the capture window being tick-bounded rather than
frame-bounded = 1 971.3, smallest power of two above it = **2 048 frames =
8.44 MiB**, against the 13.97 MiB `stream-0003` leaves free. 60 s would need
15.48 MB and does **not** fit, which is why the safety cap cannot be the basis.
`witness_store_full` stops storing and makes the claim INCONCLUSIVE; nothing is
ever silently overwritten.

**Said plainly:** canonical strip retention is **stimulus-aware** instrumentation.
A fixed ROI is stimulus knowledge even though it decodes nothing. Acceptable for
a specific scientific POC, under conditions written into the contract, and never
promoted into the generic runtime without a separate decision. Option D
(per-block CRC-32) is reclassified as a **generic diagnostic fingerprint** — not
decisive, not lossless, not a replacement — and is not implemented.

**VBlank estimate updated and still an estimate:** 19 840 VRAM-store cycles =
23.7 % of 83 776, before loop control, CRC generation, bit-to-symbol expansion
and the instrumentation reads. And a concrete implementation constraint:
`mod 31` must **not** become a divide, because ARM7TDMI has none — a running
counter with compare-and-subtract.

**Tests.** `tools/istim.py` now carries the witness, the frame classifier, the
decisive-population rule and the status semantics; 74 host tests for it, 649
overall, green, plus 19 unit binaries / 792 077 checks / 0 failures. The Python
model is still compile-and-compared against `src/gbp/gbp_vsig.c` itself.

**Open on purpose:** DDR-1 (Mode 4 page flipping) stays open — Mode 3 keeps the
baseline because it is the only mode with physical colour evidence — and the
VBlank figure stays an estimate until the ROM measures it.

**Next:** implement the ROM against this contract. It does not block the first
physical smoke.

## 2026-09-18 — real cartridge video reached the screen, and the run found two defects

Two independent tracks in one round: the **first physical GBP stream smoke of
`stream-0003`**, and the **OGBPIDX1 ROM and analyzer**. `src/` and `poc/` were
not touched and `stream-0003` is unchanged (`2f8e362e…199e3`, 471 648 B).

### The physical run

`logs/GBP-VIDEO-004_stream-0003.log`, 88 705 B, `62996c7d…4fa4ec`, `dropped=0
truncated=0`. Ingested as **GBP-HW-138…145**, with the operator's two
photographs preserved in `captures/local/`.

**It worked.** The storage contract that stopped `stream-0002` passed on hardware
(`fault=- ok=1`). The service conserved **280 621 cycles** with
unmask = deliver = ack = re-arm exactly and zero timeouts, busy, overflow,
uncertain or errors — the first time this project has done that **with a
consumer, a converter and a GX display attached**. The consumer took, converted
and submitted **2 298 frames**, overran nothing, superseded nothing, and the
ownership invariants held across **246 548 checks with zero failures** on both
the main and the interrupt side. R8 is what makes that last sentence sayable:
`stream-0002` could only ever have reported its final instant.

**And the operator saw the game.** The photographs show the display self-test's
checkerboard first — confirmed from the rendering code, not inferred: R = x>>3,
G = y>>3, B = (x^y)&0x1F gives exactly the photographed 30 × 20 grid of 8-pixel
cells with that gradient — and then a real GBA title screen, small and centred,
colours unswapped. The small picture is **by design**: a 240×160 texture drawn at
`x0 = (640−240)/2`, `y0 = (480−160)/2`, which §V5.16 specified and left scaling
to Phase 9. The missing Game Boy boot logo is **expected for this POC**: the AGB
starts at console power-on and finishes its logo long before Swiss has loaded the
DOL, let alone before the 5 000 ms pre-handler wait.

**Scoped milestone: PHYSICAL REAL-CARTRIDGE VIDEO OUTPUT ACHIEVED** — real
DOL-017, real cartridge, Open-GBP runtime, physical GameCube output, native-size
presentation, sustained for a 44.3 s smoke. It does **not** imply GBP-VIDEO-004
complete, zero source-frame loss, a timing-safe pump, or final UI.

**The pump was measured for the first time:** 27.88 / 33.60 / 41.06 µs
(min/mean/max over 91 920 slices), exactly 40.0 slices per completed frame, and
**24.95 % of all pump calls found a GBP cause already latched and yielded the
cycle** — the precheck doing exactly what it was built for. The strongest
justified wording is "the pump did not cause observable transport failure in this
run"; its effect on frame completeness stays **UNKNOWN**, and one run does not
make a placement timing-safe.

**Two defects, both in `src/gbp`, both reported and NOT fixed** (this round was
not authorised to change the runtime):

**P2, HIGH — a bit collision cost 12.3 % of the frames.**
`GBP_VSTATE_F_MAJORITY_EXTRA` (`gbp_vstate.h:109`) and
`GBP_VSTATE_F_EPISODE_STABLE` (`gbp_vstate.h:121`) are **both `0x1000` in the
same frame-flag word**. `gbp_vstate.c:1052` writes the latter into `f->flags`;
`gbp_vqueue_classify()` tests the former first and quarantines. The run shows it
exactly: **324 episodes, all closed as stable → 324 frames refused**, while the
R3 machinery reported `maj_extra=0`. Cadence 59.74 → 51.85 Hz, confirmed
independently by `publish_mean` = 19.27 ms = 51.89 Hz. The trigger is ordinary
changing cartridge video driving the structured-change detector — 324 episodes in
44.3 s against **9 in 175.8 s** for `vstate-0004`'s static picture — but the
mechanism of the loss is the aliasing, not a policy.

**P1, MEDIUM — `balanced=0` is an accounting predicate, not a conservation
failure.** A converted frame has three terminal states, not two: presented,
overrun, or **repeated** (submitted and drawn, but both framebuffers spoken for,
so the XFB copy was skipped). The run conserves exactly under
`converted == presented + overrun + repeated` → `2 298 == 2 286 + 0 + 12`, with
`xfb_skipped = repeats = 12`.

Both are locked as passing unit tests that assert the *current* behaviour
together with the arithmetic showing why it is wrong, so a fix has to be
deliberate.

**Two things that looked alarming and are not.** `power_cycle_required=1` is set
before **every** IRQ write by construction — 561 244 of them here — and both
physically validated runs carry it with accepted teardowns; `stream-0003`
reproduces `color-0002`'s FINAL `control=00 irq=9292` exactly. And `drained=0` is
correct: `inflight_at_end=0`, so the teardown's blocking drain was never needed.

**The 13 incomplete intervals are not source loss and must not be called that.**
All 13 fall in the first 408 of 2 648 frames, in four clusters of 34/38/38, and
`vstate-0004` — physically validated, **no streaming consumer at all** — shows
the same shapes in the same startup region with nearly the same absolute count
across a 4× longer capture. Whether blocks were lost or boundaries were observed
early or late is **UNKNOWN**, and it stays unknown until there is ground truth.

**44.323 s is wall time; 30.002 s is the science.** The scientific clock adds each
counted frame's own first-block-to-last-block span and never the inter-frame
idle (`gbp_vstate.c:884`). `vstate-0004` shows the same ratio (1.465 vs 1.477).

### The indexed stimulus

`stimulus/agb-indexed` implements OGBPIDX1 exactly: **2 460 B**, sha256
`379df0f7…c543`, devkitARM 15.2.0. Mode 3, polled VBlank, no interrupts, frame 0
complete before `REG_DISPCNT` is set, sticky FAULT latch from VCOUNT and a
free-running Timer 0 at F/64, monotone-minimum VMARGIN with an unreachable
`0x7F` sentinel, and **no division or modulo anywhere in the source** — every
period is a compare-and-subtract, because ARM7TDMI has no divide.

**It matches its model word for word:** 38 400 of 38 400 AGB words for nine
frame ids across eight STATUS values, and the canonical witness word-for-word for
all 40 blocks. The two hardware bases are the only thing the host test relocates,
and the ROM hash was byte-identical before and after that parameterisation.

`tools/vindex.py` is the analyzer. Adversarially tested against every frozen
classification — contiguous, gap, duplicate, reorder, half-range, wrap, mixed
IDs, wrong block index, OTHER symbol, wrong SYNC, wrong CRC, unexpected bit 15,
FAULT, status delay, too few frames — plus a test that its report contains
neither "dropped" nor "source loss".

**Not done, deliberately:** witness retention in the runtime (8.4375 MiB of
operational capacity, a separate audited round), and the ROM has never run
anywhere. The Nintendo logo area is empty, so delivery remains the same
unresolved question `agb-color-bars` carries.

**Tests.** 677 host tests OK (40 new), 19 unit binaries / 792 091 checks / 0
failures.

**Next, and it is a runtime fix, not a run:** P2 discards 12 % of the frames for
a reason that does not exist, and no pacing or continuity measurement made with
it in place can be trusted. **Do not request another physical run before it is
fixed and audited.**

## 2026-09-18 — stream-0004: the persistence audit inverted the obvious fix

P2 and P1, corrected. No hardware. Scope strictly the two defects:
`gbp_vstate_probe.c`, `gbp_vpix.c` and `gbp_vpresent.c` have **zero** changed
lines, so the service path, the pump, GX, the ownership machine, R3 and every
timing counter are untouched. `stream-0003` stays historical at `03b32a9`,
471 648 B, `2f8e362e…199e3`, and keeps the physical milestone.

**The audit changed the answer.** The naive fix — "move `F_EPISODE_STABLE`, it
is the newer, less load-bearing flag" — would have been wrong, and §4 existed
precisely to find that out before touching a bit.

`gbp_vstatedump.c:275` writes the frame flag word **verbatim** into every
OGBPSEQ1 frame record at offset 0x1A. So the flags are persisted and the choice
is an ABI question. And then:

```text
maj_extra = 0 in EVERY physical log ever produced
vstate-0001/-0003/-0004 each carry seven frames that closed an episode as
  stable — seven frames with bit 0x1000 SET, in validated sidecars
tools/vstate.py:117 already names 0x1000 "episode_stable"
```

**In every historical sidecar 0x1000 means EPISODE_STABLE, and the analyzer
already reads it that way.** So `F_MAJORITY_EXTRA` is the one that moved
(0x1000 → 0x4000): it has never been set in any file, so the change
re-interprets **exactly zero historical bytes** and needs no version bump.
Category B — persisted, versioned, interpretation preserved.

The audit also surfaced a second exposure: `gbp_vcolor.c:30` rejects
`F_MAJORITY_EXTRA` too, so the colour path had the same aliasing risk. It never
fired — both colour runs report `episodes=0 stable=0` — so **U-GBP-011's closure
is unaffected**. Worth knowing, and it would not have been found by looking only
at the stream path.

**The guard is the real deliverable.** `GBP_VSTATE_F_ALL` ORs every flag and a
compile-time check requires its popcount to equal the flag count — which can
only hold if every flag is a distinct power of two. Restoring the alias now
**breaks the build**, which mutation M1 confirms. It is deliberately not a test
for one pair: it catches the next collision too.

**P1 came out of the state machine, not the arithmetic.** Every destination of a
converted frame was enumerated: overrun (abandoned), presented (XFB free),
repeated (XFB busy) — and a refused submit, which is **not** a terminal because
the texture stays READY and is re-offered, incrementing nothing. So

```text
converted == presented + overrun + repeated + residual
```

and the residual is real and **bounded**: a converted frame still waiting for a
submit when a run ends, at most one per texture buffer.
`GBP_VQUEUE_MAX_UNDISPOSITIONED` expresses it, the POC asserts at compile time
that it equals `GBP_VPRESENT_TEX_BUFFERS`, and
`gbp_vqueue_undispositioned()` reports it so a nonzero value is visible instead
of hiding inside `balanced`. The physical run closes exactly — 2 298 == 2 286 +
0 + 12 — and `balanced()` now returns 1 for it.

P1 also corrected a comment that had never matched the code: `note_repeat()`'s
only caller with a real queue is `submit_ready()` after a **successful submit of
a converted frame**, so a repeat always has one converted frame behind it. The
run had already said so — `repeats = 12 = xfb_skipped`, both from that one
branch.

**Mutations 6/6 caught**, M1 at build time: restore the alias · mark a stable
frame as majority-extra · let a true majority-extra be eligible · drop repeats
from the identity · allow an unbounded residual · contaminate the scientific
counters from the self-test.

**The candidate:** `stream-0004`, commit `e11df66`, **472 160 B**, sha256
`56f2687377f261a865ec05efb8d71ec71c79b664389fec8b31dc038545977c43`, Swiss
`12-stream` byte-identical, zero warnings. Gates: 19 unit binaries / 792 301
checks / 0 failures; 677 host tests OK; `stream-audit` clean with both one-shot
ISRs byte-identical to the physically validated GBP-VIDEO-001 build;
`stream-dolphin` PASS with `balanced=1 sci_clean_at_probe=1 inv_fail=0
storage_fault=-`.

**Pre-registered without imposing a result:** if no true majority-extra event
occurs, frames formerly excluded solely by the aliased bit should now become
eligible. **No frame rate and no publication count is pre-registered** — and
fixing the alias does not mean every complete frame becomes published, because
anomaly, resync and incomplete exclusions are untouched.

**P2 is not physically resolved until a run says so.**

**An environment note, not a project finding:** the fuseblk mount lost
`tools/istim.py` from the container's view entirely — the file was visible on the
host and absent inside the container, which made `git diff` there report a
phantom deletion and stamped the build `-dirty`. Rewriting the file refreshed the
dentry; the clean build then reported `commit=e11df66` with no suffix. No build
output was trusted until that was resolved.

**Next:** a focused pre-hardware audit of `stream-0004` — flag uniqueness and
persistence, true majority-extra still quarantined, stable frames no longer
aliased, the balance conservation proof, R1 isolation, the exact artifact, and
the functional diff against `stream-0003`. Then, if clean, a short supervised
physical run.

---

## 2026-09-18 — focused pre-hardware audit of `stream-0004` — **DECISION A**

**Goal.** One question only: is the exact `stream-0004` artifact ready for a
second short supervised physical smoke? No hardware was executed, no functional
code was changed, OGBPIDX1 witness retention was not integrated, and
R3 / R5 / R7 / the pump position / scaling were deliberately left alone.

**The artifact.** `build/` was deleted and rebuilt from scratch **three times**
inside the pinned container. Every pass produced **472 160 B** and
`56f2687377f261a865ec05efb8d71ec71c79b664389fec8b31dc038545977c43`, with
`build_id=stream-0004 commit=e11df66` and no `-dirty`; the Swiss copy is
byte-identical. Three passes rather than one because this repository lives on a
`fuseblk` mount that has silently corrupted `build/` before. `git diff
e11df66..HEAD` over `src/ poc/ tools/ tests/ stimulus/ Makefile Dockerfile
compose.yaml` is **empty**, so the bytes compiled at `HEAD` are the bytes
committed at the candidate.

**P2.** All 15 frame flags are distinct powers of two, `F_ALL = 0x7fff`,
popcount == `F_COUNT`, `0x8000` still free. The compile-time guard was made to
**fire three different ways** — restoring the alias, adding a flag without
adding it to the mask, overflowing the word — and the header restored
byte-for-byte after each.

All **seven** `tools/vstate.py` modes produce **byte-identical output** on all
five historical sidecars, and `tools/vcolor2.py` on the `color-0002` fixture is
identical too, so **U-GBP-011's closure is untouched**.

**The strongest single result** is not an example. `F_EPISODE_STABLE` no longer
quarantining was settled by **enumerating all 2^15 flag words**: for every one,
setting or clearing that bit cannot change the classifier's answer. That is now a
permanent unit test.

**A true majority-extra frame is still quarantined** — alone, with `ANOMALY` as
the assembler actually emits it, and combined with `EPISODE_STABLE`, where
quarantine wins. R3.12 and the whole of `gbp_vstate_probe.c` are byte-identical
to `stream-0003`; **U-GBP-033 stays OPEN**.

**The causal proof was already inside the physical record.** `stream-0003` logged
`STRUCTURED episodes=324 stable=324`, `STREAMSRC quarantined=324`, and
`SEMANTIC maj_extra=0 quarantined=0`. The R3 machinery never fired; every one of
those quarantines came from the aliased bit. That is a retrodiction of an
existing record, **not** a retroactive correction of it.

**P1, and the residual question answered honestly: C, it depends on the stop
point.** The report *is* taken after the GX drain, and it still cannot force the
residual to zero: `GX_DrawDone()` waits for a submitted token, it never submits a
`READY` buffer, and `gbp_vpresent_shutdown()` — which runs first, deliberately —
makes any later submit impossible. A texture left `READY` at that instant is
permanently undispositioned. The bound is exactly `GBP_VPRESENT_TEX_BUFFERS = 2`
because every buffer can be `READY` at once, and a `SUBMITTED` buffer has
**already** been counted (the POC records the terminal at submit time), so the
drain retires a token and never a frame. It is not hidden behind the bound check:
it is printed on its own `STREAMDISP` / `DISPOSE` line and corroborated by
`blocked_shutdown`.

**`stream-0003`'s arithmetic closes, and three counters the identity does not use
agree with it:** `submit 2299 == 2298 + 1 self-test` with `blocked_shutdown=0`
(so nothing was left `READY` — the residual is 0 by an *independent* counter),
`xfb_presents 2287 == 2286 + 1`, `xfb_skipped 12 == repeats 12`,
`drawdone == releases == submit`, `acquire − fills == abandoned`.

**Mutations 6/6.** M6 was not left as a claim about a gate — the mutant DOL was
built and actually run under Dolphin, and three assertions fired together
(`SELFTEST ok=0`, `sci_clean=0`, `balanced=0`), the same R1 signature
`stream-0002` produced on hardware. **A harness defect was found and fixed inside
this round:** the first pass scored M5 as NOT CAUGHT because the command ended in
`| tail -6`, so the exit status examined was `tail`'s rather than `make`'s — while
that same run's transcript already contained the failing `_Static_assert`. Under
`pipefail` M5 is caught. Recorded because a mutation harness that cannot detect a
failure proves nothing, and the previous round was invalidated by a different
defect in the same harness.

**Findings: 6, none a blocker.** Two LOW comment defects in `gbp_vqueue` — the P1
in-body comment says "at most one texture buffer" where the constant it defends
is 2 (the constant is right), and `balanced()`'s doc comment was orphaned when
the `MAX_UNDISPOSITIONED` block was inserted above the declaration and now
overstates what the predicate checks. Three INFO observations, including that
stage 4 (`taken → converted`) is checked only as an unbounded inequality while
the quantity that closes it, `conv_abandoned_no_raw`, is reported but not
checked. One build-hygiene INFO: `build/swiss/11-color/boot.dol` is exported
labelled `e11df66-dirty` — not the candidate and not loaded by any procedure, but
run `make build` before the session so no `-dirty` DOL sits beside the candidate
on the SD card. **Nothing was fixed**; the round forbade functional changes and
every item is carried to the next functional candidate.

**Tests added (diagnostic, permanent):** the exhaustive 2^15 classification
enumeration, and a residual test that proves the residual is exactly the set of
`READY` textures, that a `SUBMITTED` buffer is already dispositioned, and that
shutdown makes a waiting frame permanent. Unit checks 118 946 → **217 267, 0
failures**; the whole suite is 19 binaries / **911 420 checks / 0 failures**, and
659 host tests pass.

**Next:** run the short supervised physical smoke of the exact `stream-0004`,
power-cycling first, with the ingest checks fixed beforehand (§V5.37.17) — the
decisive one being `SEMANTIC.quarantined == STREAMSRC.quarantined`, which
disagreed by exactly 324 in `stream-0003` and must now agree.

---

## 2026-09-19 — `stream-0004` ingested, P1/P2 physically closed, and `stream-0005` implements witness retention

**Goal.** Two fronts: ingest the second physical smoke and decide whether the two
corrections actually held on hardware; then implement lossless OGBPIDX1 witness
retention in a new candidate — correcting the experiment's operational protocol
in the light of what the run proved about the clock.

### A — the run

`logs/GBP-VIDEO-004_stream-0004.log`, 88 854 B, sha256 `2ec3ada2…c212dda`,
`build_id=stream-0004 commit=e11df66`, `dropped=0 truncated=0`. Every figure was
recomputed from the file; nothing was retyped from a report.

**The pre-registered P2 gate passed: `SEMANTIC.quarantined ==
STREAMSRC.quarantined` = `0 == 0`.** What makes that decisive is something I did
not expect to get: the two runs are a controlled comparison. `FRAMECAP` is
identical in all seven fields (2648 / 2635 / 13 / 26 / 13 / 2619 / 105 841), as
are the video and audio block counts and `capture_s` to three decimals. So the
**same 2 635 complete source frames** decompose as `2298 + 324 + 13` in
`stream-0003` and `2622 + 0 + 13` here — a published delta of exactly the 324 the
aliased bit had been refusing — while every file that can influence the source
population has **zero changed lines** between the two builds. There is no other
causal candidate. `stream-0003` is not rewritten; its counters stand as logged.

**P1 closes with four counters the identity does not use.** `2621 == 2603 + 0 +
18 + 0`, `balanced=1`, and independently: `xfb_skipped == repeated == 18`,
`xfb_presents 2604 == 2603 + 1 self-test`, `submit 2622 == 2621 + 1` with
`blocked_shutdown=0` (so the zero residual is a counter's answer, not the
identity's own), and `fills_started 108 249 == 2622 + 105 626 + 1 still filling`
— where `taken − converted = 1` names that same in-flight frame. The stop caught
one conversion mid-flight; `stream-0003`, stopping between conversions, did not.
Both close. The audit's ingest rule (residual only with `blocked_shutdown > 0`)
held trivially.

Cadence 51.89 → 59.19 Hz, against a source closure rate of 59.74 Hz. **One run,
one cartridge, 44 seconds — not a frame rate anything promises.** Transport
conserved over 280 672 cycles with zero timeouts and every W1C from the ISR;
ownership invariants 221 741 checks / 0 failures, which with `stream-0003` makes
468 289 checks and no failure across two runs.

The operator saw no visible change and took no new photographs. Recorded, and
weaker than every machine fact: an unaided impression of 44 seconds cannot
resolve a 12 % publication difference. It is consistent with an accounting fix;
it corroborates nothing alone.

**Milestone.** Basic sustained streaming is OPERATIONALLY REACHED for the window
exercised. Not zero source-frame loss, not a guaranteed frame rate, not timing
safety — those need the indexed stimulus.

### B — the finding that changed the next experiment

```text
capture_s 44.323   valid_s 30.001   frames closed 2648   wall/valid 1.4774
```

`valid_observation_elapsed` sums each counted frame's **span**, not the time
between frames. So "30 s → ~1 792 source frames", the premise the indexed
experiment was sized on, is wrong by a factor of 1.48 — and was equally wrong in
`stream-0003`, where nobody had checked it against a closed-frame count. A
witness store bounded by a clock is bounded by the wrong quantity.

**The OGBPIDX1 wire format is untouched and NOT re-versioned.** What was wrong
was the protocol around it. There is no OGBPIDX2.

### C — `stream-0005`

Retains the canonical witness — STRIP-L, local row 0, x = 1..54, 54 word16 per
block, 4 320 B per frame — at the **SOURCE-CAPTURE layer, above the publish**, so
quarantined, anomalous, incomplete and resync frames are all preserved. Retaining
only what the consumer accepted would make the population a function of consumer
eligibility, which is the one bias that would make a source-continuity claim
worthless. Bit 15 is stored exactly as the wire carried it, because what sets it
is U-GBP-034 and masking on the way in would destroy the only evidence this run
can gather about it.

**The stop is a count.** `WITNESS_TARGET = 2048`; the record that fills it ends
the run as `witness_target_reached` (NORMAL), and a commit refused for lack of
room is `witness_store_full` (INCONCLUSIVE). Two reasons, never folded into one,
with overflow checked first so a run that somehow did both reports the failure.

**The association is the part that cannot go wrong quietly.** A witness placed in
the wrong frame produces a plausible record of a frame that never existed, and no
later check recovers from that. So the assembler REPORTS where each block landed
and whether it belongs to the frame closing in the same call, and the rule lives
in `gbp_vwitness_drive.h` where unit tests drive it against the real assembler:
boundary → commit then place; 48-block give-up → place then commit; no anchor or
full frame store → discard. The static audit pins **two** call sites of
stage/place, because two is what the two orderings are.

**Memory, measured rather than asserted:** `.bss` 17 157 144 B ending at
`0x810D5BB8`, `Arena1Lo 0x810D5BC0`, `Arena1Hi 0x81800000` → 7 512 128 B free,
5 668 928 B after three framebuffers. The witness is the audited 8 847 360 B and
its 98 304 B of metadata is reported separately rather than folded into that
figure. The POC now prints `ENVMEM` at run time, so a build that stops fitting
says so in the log instead of on the console with a cartridge already running.

**OGBPIDXCAP1**, a new magic — OGBPSEQ1 and OGBPCOL1 stay frozen and untouched —
with the family's conventions and one addition: **every record carries its own
CRC-32**, on top of the whole-file one. That buys RECORD INTEGRITY AND CORRUPTION
LOCALISATION — damage is caught and the damaged record is named, so one bad
record does not condemn 2 047 good ones. It buys nothing about whether the
producer captured the right bytes: a checksum computed by the producer over its
own output passes whether that output is right or wrong. (An earlier draft of
this entry claimed more than that, and the stream-0005 audit corrected it,
§V5.40.11.) The host test flips every single byte of a one-record file, one at a
time, and all 4 560 are refused — corruption coverage, not producer proof. No filesystem call exists in the capture path; the sidecar
streams one record at a time after the teardown.

**The adapter refuses.** A capture is usable for a decisive claim only if it
parses with every CRC intact, stopped BECAUSE of the target, never refused a
commit and holds exactly the declared target; anything else forces
`INCONCLUSIVE_CAPTURE_NOT_DECISIVE`, and the per-frame classifications survive
while the verdict does not. `tools/vidxcap.py` reads the probe's stop enum out of
the C header rather than copying the numbers.

**Tests:** `test_gbp_vwitness` 12 020 checks, six of them driving the real
assembler; `test_vidxcap.py` 19 tests whose sidecars are written by the real C
writer, compiled and run — a Python writer checking a Python reader would prove
nothing about the bytes the GameCube produces. Suite: 19 binaries / 923 440
checks / 0 failures, 678 host tests. `stream-audit`, `vstate-audit` and
`color-audit` all 0 findings, both one-shot ISRs still byte-identical to the
physically validated GBP-VIDEO-001 build.

### Blocked, and it is operational rather than design

The OGBPIDX1 ROM's logo area is empty by policy and the derived delivery image
needs official devkitPro **`gbafix`, which is not in the pinned container image**
(`$DEVKITPRO/tools/bin` has no such tool). `build/physical/agb-indexed-cart.gba`
is currently a byte copy with the logo still empty and is NOT deliverable. The
route itself is proven — the colour stimulus took it twice — so what is missing
is the tool here, and the OGBPIDX1 payload is never altered to accommodate a
flashcart.

**Next:** the focused pre-hardware audit of `stream-0005`. No hardware before it,
and no indexed run at all until the delivery ROM exists — an indexed run without
the indexed cartridge measures nothing.

---

## 2026-09-19 — pre-hardware audit of `stream-0005` + the OGBPIDX1 delivery ROM — **DECISION A**

**Goal.** Is the exact candidate, with the exact delivery cartridge, ready for
the first *decisive* indexed run? No hardware, no functional change, no OGBPIDX1
redesign, no capacity increase, nothing touched in R3/R5/R7/pump/scaling.

**The critical question was §9 — can the 2048th record stop the run somewhere
unsafe? — and the answer is provable.** `gbp_vwitness.o` references exactly two
external symbols, `memset` and `__udivdi3`. It has no transport, no device, no
`finish()`, no way out of the probe. The only readers of the target and
store-full latches are one block inside CHECK_ADMISSION and two report lines in
`main`. So the order is forced: the 2048th frame closes at `gbp_vstate_probe.c:1425`,
the latch is set at 1445, the publish still runs at 1479, **the RE-ARM is still
written at 1485**, WAIT_NEXT still runs — and the stop is taken at the *next*
iteration's line 1083, before the UNMASK at 1174. The ACK happened at 1351,
before the latch. **The target cannot stop the run before the ACK or the RE-ARM.**

The same line numbers settle the placement question: the witness at 1445 is
strictly above the publish at 1479, so retention cannot inherit consumer
eligibility. Driven against the real assembler, a quarantined frame keeps its
witness and its `F_MAJORITY_EXTRA|F_ANOMALY`; a 12-block frame keeps
`present=0xFFF` with block 20 marked ABSENT rather than zero-valued; the
48-block give-up keeps its own block 39 and counts 40..47 out of range.

**2048, exhaustively.** The target fires on record index 2047 — the 2048th — and
not at 2046 or 2048; the 2049th commit is refused, `store_full` latches, record 0
is untouched. Over every `capacity 1..6 × target 1..capacity`, `target_reached`
is true exactly when `n >= target` and `store_full` only after a refusal.

**Cost and isolation, by call graph on the real ELF.** `gbp_vstate_probe_run`
reaches no CRC, no serializer, no filesystem symbol. The per-record CRC lives in
a static called only by `gbp_vidxdump_stream`, called only from `main`, after the
teardown. The serializer's only transient is `dump_chunk`, **4 368 bytes** — one
record — and the only object ≥ 8 MiB in the whole image is `witness_store`
itself. No duplicate full-file buffer exists.

**Three findings came from refusing to trust my own tools, and that is the real
lesson of this round.**

The mutation harness reported the two most important adversarials — a filesystem
call in the capture path, and a full-record CRC in the capture path — as CAUGHT.
They were not. A `| tail -20` had pushed the `poc_audit: 0 finding(s)` line out
of the text the detector searched: a **false positive**, and the third defect in
the same harness family. Re-running with a correct detector said NOT CAUGHT — but
`nm` showed the mutant symbols were not in the object at all, because
**`make stream-audit` has no dependency on the sources** and had audited the
previous build. Only the third attempt, with an explicit rebuild, gave the true
answer: `U fopen U fclose` and `U gbp_crc32` verifiably present,
`poc_audit: 0 finding(s)`. Both gaps were real.

The cause was specific and dull: `gbp_vwitness.o` was never added to the `stream`
profile's `object_must_not_reference` map when the module was created, and
`gbp_crc32` is in no per-object list because three objects use it by design.
Fixed **in the audit tool only** with a `_CAPTURE_SYMBOLS` set. A first attempt
at that fix silently did nothing — it added a duplicate dict key and Python kept
the later one — which I found by printing the loaded profile instead of trusting
the edit. Both mutations are now caught by name.

**A fourth finding is operational and would have bitten the operator.** `make
build` at HEAD does not produce the documented candidate: it embeds `8ee5566`
instead of `10250a4` and yields `58c96690…`. Exactly 12 bytes differ — two copies
of the commit string — so it is the same program, but `make swiss` exports the
mismatching DOL into the slot the operator loads, and the documented hash looks
unreproducible. It is reproducible, byte-identically and twice, with
`GIT_COMMIT=10250a4 GIT_DIRTY= make build`; that command is now in the HANDOFF
and in §V5.39.17, where it was missing.

**And a claim of mine was too strong.** §V5.39.7 said a per-record CRC catches "a
producer that built a record wrongly and then sealed the result". It does not — a
checksum computed by the producer over its own output passes whether that output
is right or wrong. The correct classification is **record integrity and
corruption localisation**. Correct capture comes from the frozen source-layer
placement, the model cross-check, the assembler-driven tests, the adversarials,
and decisively from OGBPIDX1's own CRC-8, which the **cartridge** computes — the
one check in the chain a GameCube-side producer cannot satisfy by being
consistently wrong. Corrected in §V5.40.11, in the DEVLOG entry above and in the
test comment that repeated it.

Also corrected: three arithmetic slips in §V5.39's memory table (`.text` 370 800,
arena free 7 512 896, post-XFB 5 669 696). No conclusion changed.

**Delivery.** The cartridge is `abb31e6a7fd9dd3185d4474065169bdf0c483bc9e5e01c7aefe8a455d0ce0769`,
2 460 B, differing from the canonical ROM in **154 bytes, all below 0x0A0**, with
the payload past 0x0C0 byte-identical and a logo area byte-identical to the
colour cartridge that booted physically twice. The supportable claim is exactly
that — *prepared for the same empirically validated Omega DE NOR/Mode-B path* —
and **not** a generic valid GBA header: the logo is never verified against an
authoritative reference, none exists here, and this project does not fetch such
bytes. UNRESOLVED, deliberately.

**Gates:** 19 unit binaries / 923 440 checks / 0 failures, 678 host tests, three
static audits at 0 findings with both one-shot ISRs byte-identical to the
physically validated GBP-VIDEO-001 build, `stream-dolphin` PASS, and the
candidate reproduced byte-identically twice from scratch.

**DECISION A.** Nothing found is a blocker; F3 and F5 need functional changes and
are carried to the next checkpoint.

**Next:** the first short supervised OGBPIDX1 physical run. Stop on
`witness_target_reached`, do not extend toward 30 valid seconds, return both the
log and the sidecar.

---

## 2026-09-19 — the first indexed physical run: runtime proved, stimulus disproved, ROM corrected

**The run did its job by failing in the right place.** Everything the last three
rounds built — the count-bounded stop, the source-layer witness, OGBPIDXCAP1 —
worked on hardware the first time. What did not work was the thing being
measured, and the stimulus said so itself.

**Runtime.** `stop=witness_target_reached`: the run ended because the 2048th
record closed, not because a clock ran out — the first time an experiment here
has been bounded by a count of retained evidence. 217 120 service cycles with
`unmasks == deliveries == acks == rearms` and every error counter at zero;
81 876 blocks staged and placed, none out of range, nothing discarded; the
sidecar exactly **8 946 060 bytes**, the size §V5.40.10 derived from the layout
before the file existed, with 2048/2048 record seals valid. The consumer behaved
as `stream-0004` did: `2043 == 2026 + 0 + 17 + 0`, balanced, 169 245 invariant
checks, zero failures. Witness retention cost **0.407 % of the run**.

**Stimulus.** All 81 840 canonical strips of the 2 046 complete records decode —
valid symbols, correct SYNC, correct CRC-8, `BLOCK_INDEX == slot` every time. The
payload is perfect. What it *says* is the problem: FRAME_ID 1 carries the 0x7F
sentinel and **every FRAME_ID from 2 onward carries 0x80 — FAULT set, VMARGIN
zero**. By the frozen contract the first update reported as failing is the very
first update the ROM ever performed. Verdict, mandatory and unarguable:
**STIMULUS_INVALID_FOR_DECISIVE_CLAIM**, source continuity **INCONCLUSIVE**.

**And 83.3333 % of complete records carry two FRAME_IDs** — 1 705 of 2 046, in a
staircase so regular it is practically a ruler: the newer ID always occupies a
leading contiguous run of 3, 12, 21, 30 or 39 blocks, then one single-ID record,
339 cycles out of 341. That is **not GBP frame loss** and is not reported as
such. It is the AGB publishing one image progressively while the GBP captures
each intermediate state faithfully.

**The staircase turned out to be the measurement.** 9 blocks = 36 rows per
captured frame → a full image takes 4.44 AGB frames = 1 248 000 cycles →
**62.9 cycles per VRAM store** → **14.9× the VBlank budget**, with only 10.7 of
160 rows fitting. `update_frame()` was writing the whole picture into VRAM inside
what the design called one VBlank.

**Why the original estimate was wrong, and it is worth being blunt about:** it
counted VRAM stores and assumed a store costs a cycle or two. It never accounted
for **instruction fetch**. The ROM never set `WAITCNT`, so the loop executed from
cartridge ROM at the reset wait states and fetch dominated. The FAULT bit is the
only reason this surfaced on run one instead of becoming a false continuity
claim, and nothing about it was relaxed — the validator is the authority on
whether its own stimulus is usable.

**The fix keeps the wire format frozen.** `indexed-0002` splits the work:
PREPARE during the visible period into IWRAM (CRC, bit packing, symbols, bar
arithmetic — touching no VRAM byte, so it cannot tear however long it takes),
PUBLISH during VBlank from IWRAM by DMA (computing nothing). `publish_frame` is
placed in `.iwram` — confirmed in the map at `0x03000000`, 312 bytes — and its
18.5 KiB of tables land in `.bss`, which is IWRAM on this target, leaving
12 756 bytes below the stack. `REG_WAITCNT` is set for the prepare path. The
published spans were widened to `x = 0..55` and `x = 184..239` so both are
4-byte aligned for 32-bit DMA, which adds the constant FLAG and GUARD columns to
every frame and **changes not one wire value**: 38 400/38 400 words still match
`tools/istim.py`, on both phases driven end to end.

Estimated publication cost ~60 % of the VBlank budget. **That is an estimate, and
the last estimate here was wrong by 14.9×**, so the ROM measures itself and
VMARGIN is the authority.

**The validator is now adversarially drivable.** The predicate was extracted
verbatim into `status_measure()`/`status_byte()` — no behaviour change — and six
tests drive it: an in-budget update keeps FAULT clear, an over-budget one and a
wrapped VCOUNT both set it, it is sticky, VMARGIN is a monotone minimum that a
larger margin cannot raise, and 0x7F is both the sentinel and the largest
representable margin so no measurement can forge it. Structural gates check that
the measured window contains `publish_frame()` and none of the preparation work.

**Two small reconciliations.** `staged == placed == 81 876` while the records'
presence bits sum to 81 875: the difference is the boundary block that closed
record 2047 and was then correctly placed as block 0 of a frame the target stop
ended before it could close. No record is short — the assembler's own `blocks`
field also sums to 81 875 and disagrees with the presence count nowhere. And the
old VSTATE baseline never formed (`valid_s = 0`), which is exactly right: OGBPIDX1
changes the FRAME_ID and the bar phase every frame, so no two consecutive frames
can ever share a signature. A useful side effect — the valid-seconds target
cannot compete with the witness target under this stimulus.

**`stream-0005` was not touched.** Same DOL, same hash, no `src/` or `poc/`
change. Reusing the identical capture runtime is what makes the next run an
experiment with one variable instead of an anecdote.

**Next:** the second indexed run — same `stream-0005`, new `indexed-0002`
cartridge (`55fe72d5…`). Check STATUS first: if FAULT is still set the
publication still overruns and the answer is INCONCLUSIVE again, and VMARGIN
says how close it came.

---

## 2026-09-19 — the second indexed run: tearing closed, a 2:1 cadence found and fixed

**The cartridge was the only variable.** Same `stream-0005` DOL, same commit,
same hash, no `src/` or `poc/` change — three physical runs now. That is what
made this an experiment rather than an anecdote.

**What `indexed-0002` fixed, physically.** `STATUS = 0x18` on **all 81 840**
canonical strips: **FAULT clear**, VMARGIN 24. Zero mixed-ID records, against
1 705 of 2 046 in run 1. 81 840/81 840 valid symbols, SYNC, CRC-8 and
`BLOCK_INDEX == slot`. The 14.9× VBlank overrun and the progressive top-down wipe
are closed. VMARGIN 24 means the worst publication ended at `VCOUNT = 203`,
consuming 44 of the 68 VBlank lines — **65 %**, against a pre-hardware estimate
of ~60 %. The measurement wins, and this time it was close.

**What the run then revealed.** 2 046 complete records but only **1 024 unique
FRAME_IDs**, spanning 7..1030 with no gap, no reorder and no half-range — and
**1 022 of them captured exactly twice**, run lengths `{2: 1022}`. Capture
59.75 Hz, unique IDs 29.87 Hz, ratio **2.00**, regular to 1 022 of 1 022.

**Producer or GBP?** That distinction was the whole job, and the answer is the
producer. The ROM's loop waits *until it is not in a VBlank*, then *until a
VBlank starts*. So if `prepare_frame()` returns while VCOUNT is still inside a
VBlank, that VBlank is skipped entirely and the GBP captures the unchanged
framebuffer again. Publication ends at VCOUNT 203, leaving 185 lines =
**227 920 cycles**; the observed cadence — always 2:1, never 1:1, never 3:1 —
bounds preparation at **227 920 ≤ T < 508 816 cycles** with no estimate
involved. Independently, `prepare_frame` turned out to be 195 ARM instructions at
**`0x080002ac` — cartridge ROM**, driving ~8 640 symbol stores per frame, which
at ROM wait states is ~253 000 cycles: **inside the measured band**.

`publish_frame` has been in IWRAM since `indexed-0002`. `prepare_frame` was
simply left behind — last round fixed half the problem and I did not notice the
asymmetry.

Four reasons the GBP is not responsible: the loop predicts 2:1 quantitatively;
the bound from the cadence matches the code's cost; the GBP captured 2 046
complete frames at ~59.7 Hz in *both* runs while only the cartridge changed; and
a capture-side mechanism would have to duplicate every frame exactly once, 1 022
consecutive times, without a miss. **Duplicate IDs here are not GBP frame loss,
duplication or reorder** — source continuity stays INCONCLUSIVE because the
producer showed each picture twice.

**I got the bound wrong once and the simulation caught it.** My first derivation
used 311 696 cycles as the upper edge, reasoning that anything past the skipped
VBlank would give 3:1. Wrong: landing in the *visible* period of the following
frame still publishes in that frame's VBlank, so 2:1 persists until the overrun
reaches the VBlank after it — 508 816. The state-machine test now derives the
edges instead of asserting my arithmetic.

**The fix is one line of placement.** `prepare_frame` moved to `.iwram`
alongside `publish_frame`. The work is unchanged, the arithmetic is unchanged,
and **not one wire value changes** — 38 400/38 400 still match the model.
Estimated `T_prepare` from IWRAM ~94 000 cycles, **41 % of the deadline**, a 2.4×
margin. IWRAM now holds both functions plus 18.9 KiB of tables: 20 024 B of
32 KiB, 11 976 B free.

**FAULT was not expanded to cover cadence.** That would have hidden this defect
behind the very mechanism meant to expose overruns. The producer must emit a new
ID on every refresh; the validator's job is the VBlank budget, and it did it.

**Proving cadence without hardware.** Render-output equality cannot catch this —
the pixels were always right, the *timing* was wrong. So the loop's own VCOUNT
waits are modelled and driven with a parameterised preparation cost: the model
reproduces 2:1 at ROM speed, gives 1:1 at IWRAM speed, locates the deadline at
227 920 cycles, and shows the cliff is a **whole frame wide** — which is why a
marginal overrun costs an entire source refresh. Static guards now assert that
*both* halves carry the `.iwram` attribute, so leaving one behind fails a test
instead of a run.

**Also reconciled, again from metadata rather than assumption:** presence bits
sum to 81 874 against staged/placed 81 875, the assembler's own `blocks` field
agrees at 81 874, and no record is short — the extra block closed record 2047 and
became block 0 of a frame the target stop ended first. And the 33-block resync
record explains why ID 9 has one complete occurrence where its neighbours have
two.

**Next:** the third indexed run — same `stream-0005`, new `indexed-0003`
cartridge (`9f04916b…`). Check FAULT stays clear, then check that duplicates
collapse to zero. Only then can source-frame continuity be decided.

---

## 2026-09-19 — the third indexed run: the producer is correct, and the contract still says no

**The producer is fixed.** Every one of the 2 046 complete records carries a
distinct FRAME_ID — zero duplicates, against 1 022 in run 2 — with zero mixed
frames, 81 840/81 840 on symbols, SYNC, CRC-8 and `BLOCK_INDEX == slot`, and
`STATUS 0x18` (FAULT clear, VMARGIN 24) on every strip. From the capture's own
time base, between the first and last complete records rather than count ÷ wall
clock: **2 046 FRAME_ID increments over 34.255788 s = 59.7271 Hz**. One new
picture per AGB refresh.

The three-run series, with the GameCube runtime byte-identical throughout —
`stream-0005`, `commit=10250a4`, `35bbbdd6…d87092`:

```text
run 1  indexed-0001   1 705 / 2 046 mixed   FAULT set     6.00 : 1
run 2  indexed-0002       0     mixed       FAULT clear   2.00 : 1
run 3  indexed-0003       0     mixed       FAULT clear   1.00 : 1
```

Only the cartridge ever changed, and the failure mode moved exactly with each
producer fix. That promotes the earlier attributions from argued to settled: the
run-1 staircase and the run-2 duplication were **both** generated by the
controlled stimulus, and **neither was evidence of Game Boy Player frame loss,
duplication or reorder**.

**And the contract still returned `OBSERVED_DISCONTINUITY`.** 2 043 of 2 044
decisive transitions are contiguous. The one that is not is record 3 (id 18) →
record 5 (id 20): record 4 holds **id 19 with 34 of 40 blocks**, because the
assembler resynchronised mid-frame — its witness slots map 0→0, 1→1, then 2→8.
The adapter passes only all-40-block records to the core, so id 19 never enters
the decisive population and 18→20 reads as a gap.

**I want to be exact about what that is and is not.** It is not source-frame
loss: id 19 was produced by the AGB, captured by the GBP, and 34 of its 40 blocks
sit in the sidecar decoding perfectly. The raw observed ID set is 16..2062 with
no value missing. What happened is that the contract declined to bridge an
*incomplete record* — conservative, and right.

**The temptation here was to write a rule.** `decisive_population()` excludes
only the trailing uncertified frame and the two unobservable edges; it has no
provision for trimming an interior resync. Adding one now — "the decisive
interval begins after the startup region" — would make this run pass, and would
be precisely the after-the-fact rule-fitting the method exists to prevent. So it
is **proposed and not applied**, and the next safe action is to decide and freeze
that rule *before* a fourth run judges anything.

So: **no milestone.** `CONTROLLED SOURCE-FRAME CONTINUITY` was made conditional
on `OBSERVED_ID_CONTIGUOUS`; the analyzer said otherwise, and the condition
holds. The classification is `OBSERVED_ID_GAP` (one, startup region) giving
`OBSERVED_DISCONTINUITY` — an existing frozen label, no new one invented.

**A process near-miss worth recording.** The SD workflow names every run
identically, and run 3 was handed over under the names that held run 1,
overwriting it in `logs/`. Run 1's raw bytes survived only because
`captures/local/` had archived them in an earlier round. All three runs are now
stored as `…-run1/2/3` with every hash verified, and the next handover should
copy the files off the card before the card is re-populated.

**Unchanged, deliberately:** `src/`, `poc/` and `stimulus/` were not touched.
`stream-0005` is still `35bbbdd6…d87092` and `indexed-0003` still
`37119bb6…0caaca` / delivery `9f04916b…8d9cc2`. Four rounds of runtime stability
is what made the three-run comparison causal in the first place.

**No unknown was closed and none was invented.** There is no existing UNKNOWN for
source-frame continuity; U-GBP-029, U-GBP-033 and U-GBP-034 stay open and
untouched.

**Next:** freeze the startup-region decision, then the fourth run with the same
artifacts. After that, the roadmap's next unresolved GBP-VIDEO-004 objectives are
the downstream consumer/display loss policy — this run still shows 2 043
converted, 2 026 presented, 17 repeats, a *later* stage the source witness says
nothing about — and frame pacing.

## 2026-09-19 — the prospective structural window: `stream-0006`

**Goal.** Write the amendment §V5.43.8 proposed and refused to apply: a rule
that says where the decisive interval begins, fixed **before** the run it
judges, so the next capture's startup transient is outside the population under
test instead of inside it. No hardware, no analyzer change, no stimulus change,
no new wire contract.

**The rule.** A frame qualifies when the ASSEMBLER calls it complete, 40 blocks,
`COMPLETE_40`, free of `ANOMALY | DISAGREEMENT | OVERLONG | RESYNC`, closed with
no region anomaly in the step and with `resync_pending` down. 64 consecutive
such frames open the window at the next block-0 boundary, and it never closes.
Not one term touches `FRAME_ID`, `STATUS`, `SYNC`, `CRC-8`, a colour or an
expected payload.

**The finding that shaped the rule.** The baseline **never establishes** on an
indexed stimulus (GBP-HW-175): `reference_updates=0`, `baseline=never_established`,
`F_PRE_BASELINE` on 2048 of 2048 records, in all three runs. The assembler's
baseline waits for a frame to repeat and an indexed stimulus never repeats one.
Every criterion built on content stability — `baseline_valid`, a stable episode,
a matched reference — would wait for ever. The rule that works is the rule the
design required anyway: region and geometry only.

**Cross-run replay, and the control that matters.** The real C state machine was
replayed over a structural projection of all three captures (`tools/vqual.py`,
`OGBPQUAL1`, 24 652 B, which cannot physically carry a stimulus word), and the
**unmodified** analyzer was run on what the window would have kept. The three
runs happen to be three different failures, which makes them a control set:

```text
run 1  producer FAULT latched      INVALID  -> INVALID          (no N rescues it)
run 2  every source frame twice    DISCONT. -> DISCONTINUITY    (no N rescues it)
run 3  one gap, inside startup     DISCONT. -> CONTIGUOUS
```

Runs 1 and 2 are the reason to believe run 3. A window that also cleared a
latched FAULT or hid a systemic duplication would be laundering verdicts; tested
from N=1 to N=1024 it clears neither.

**On whether 64 was fitted.** It was chosen for time margin (~1.07 s at 59.73 Hz,
>9x the observed 7-frame transient, and 70+2048 frames ≈ 35.4 s against the 60 s
cap). The run-3 verdict is the same for **every N from 2 to 128**: the gap sits
at record 5 and two qualifying frames already clear it. The answer is flat over a
64-fold range, so the number is a margin decision on a plateau, not a tuned one.

**What run 3 still is.** `OBSERVED_DISCONTINUITY`, permanently. The analyzer was
not taught to accept it and no capture was re-judged. "Find the last resync and
analyze what follows" stays forbidden; this rule is causal (it sees only closed
frames), structural (a static guard enforces it) and fixed in advance.

**A change deliberately not made.** A windowed sidecar would ideally say so in
its own header, and `OGBPIDXCAP1` has 116 reserved bytes that would fit it.
`OGBPIDXCAP1 v1` is a frozen contract and this round does not carry authority to
change it, so the window is reported in the `.log` `WITQUAL` line and is visible
in the sidecar as `record[0].frame_index != 0`. The cost — a sidecar read alone
shows *that* a window applied, not *which* — is recorded rather than hidden.

**Rejected hypotheses.** That the two live-latch terms (`step->resync`,
`st->resync_pending`) add discriminating power: they do not. Every region-anomaly
site already flags the frame or leaves `completeness != COMPLETE_40`, so
shape-clean implies both latches are down. They stay as defence in depth, a unit
test pins the invariant, and the mutation round records them as **equivalent
mutants rather than as test gaps** — which is also what makes the offline replay
exact rather than an earliest bound.

**New unknowns:** none. U-GBP-029, U-GBP-033, U-GBP-034 stay open and untouched.

**Next:** the fourth physical run, with the same `indexed-0003` cartridge and the
same procedure, to test GBP-HW-179. After that the downstream consumer/display
loss policy and frame pacing remain the open GBP-VIDEO-004 objectives; the source
witness says nothing about either.

## 2026-09-19 — the fourth indexed run: the rule held, and source continuity closes

**Goal.** Ingest the first physical run judged by a rule that existed before it,
reproduce the bytes independently, and then let the unmodified analyzer decide.
No hardware, no functional change to `src/`, `poc/`, `stimulus/`, the analyzer or
either protocol.

**Result.** `OBSERVED_CONTIGUOUS`. 2 048 of 2 048 retained records complete,
FRAME_ID 85..2132 with no member missing, FAULT clear, VMARGIN 24, and the
capture admissible under `vidxcap.usability()` (`decisive-claim ready True`,
stop on target, zero out-of-range).

**The window did what it was designed to do, to the block.** §V5.44 registered a
cross-check that needs no trust in the new code: `stream-0005` staged every block
it was delivered, so run 3's `video` and `staged` were equal at 81 876. If the
window really suppresses staging, run 4's must differ. They differ by **2 755** —
and the number is not 70 × 40 = 2 800. It is the exact structural population of
the frames before the window, read from the capture's own histogram:
1 + 34 + 68×40. The whole capture then closes with nothing unaccounted:
2 755 warm-up + 81 920 scientific + 1 trailing-open block = 84 676 = the VIDEO
counter. The trailing block is the boundary that opened a frame which never
closed, which is also why `staged = 81 921` against 81 920 serialized.

**Independent first, official second.** The container walk, symbol rules, 54-bit
unpack and CRC-8 were rewritten from the frozen spec text importing nothing from
`tools/`, and reproduced all ten frozen CRC-8 vectors plus the single-bit
sensitivity over 38 positions before touching a physical byte. Only then was
`tools/vindex.py` run. Agreement therefore means two implementations agree.

**Two errors were mine, not the data's, and both are recorded.** The global CRC-32
covers `data[:off_footer]`, excluding the footer magic — my first recomputation
included those 8 bytes and disagreed with a file that was correct. And the
cadence must be measured first-to-first over 2 047 intervals (34.272 56 s,
59.7271 ID/s); measuring first-block to last-block spans 2 048 frames of coverage
and overcounts by one frame's accumulation span, 11.456 ms.

**Two counts, both right.** The independent decode finds 2 047 adjacent
transitions over 2 048 records; the analyzer reports 2 046 DECISIVE ones, because
the frozen `decisive = intact[:-1]` drops the last intact frame — no later STATUS
certifies its own update. That is a contract exclusion, not an observation, and
the two numbers are quoted for different populations rather than reconciled away.

**Run 3 is not re-judged.** It stays `OBSERVED_ID_GAP` /
`OBSERVED_DISCONTINUITY` for ever. The startup transient is still fully visible
in run 4's log and FRAMECAP (2 118 frames, incomplete=2, resync=4, intervals
1:1 and 34:1) — nothing was hidden. What changed is that retention opened only
after a structural qualification decided online, from a rule frozen first. Runs 3
and 4 share the cartridge and the producer; the only difference is which frames
the runtime kept.

**Rejected framings.** That 70 × 40 describes the warm-up — the log disproves it.
That `min 4` copy ticks is a regression — `note_ticks` times the whole witness
step, which now also times 2 755 refusals, so the minimum is the cost of a
refusal and the mean barely moved (69 → 68). That downstream repeats weaken the
source claim — the witness is taken before any consumer sees a frame, and the two
layers answer different questions.

**New unknowns:** none, and none was invented to be closed. `U-GBP-029`,
`U-GBP-033` and `U-GBP-034` stay open. Run 4 *bounds* U-GBP-034 without touching
it: bit 15 was set on 0 of 4 423 680 canonical-strip coordinates, but the strip
is x = 1..54 and the sighting that opened the item was at x = 0, which the
witness does not preserve.

**Run 5:** recommended for repeatability, **not required** for the fact of run 4.

**Next:** the question run 4 sharpened rather than answered — 2 114 published,
2 096 presented, 17 repeats and 17 skipped XFB presents over a capture whose
SOURCE population was contiguous. Which frames the consumer/display path drops or
repeats, and why. Frame pacing follows it. Neither is started here.

## 2026-09-19 — the downstream disposition trace: instrument first, explain later

**Goal.** Source continuity closed in §V5.45; the next question is what happens
to a frame afterwards, and why 17 of run 4's 2 113 converted frames never
reached a framebuffer. Design and build the instrument. **Do not fix pacing, do
not "correct" the 17.** No hardware.

**The audit came before the design, and it changed the design.** Tracing the
real code first produced a finding that reshapes the hypothesis list: **this
runtime has no VI-driven display loop.** `VIDEO_WaitVSync()` is never called in
the capture path, no retrace callback is installed, and a presentation
opportunity is one `submit_ready()` call — which happens because a conversion
finished. Presents are source-driven and an opportunity cannot precede its own
frame.

So "a display opportunity found no new source frame" is not a weak hypothesis
here, it is **inapplicable**, and no test was written for a branch that does not
exist. And every one of the 17 holds was a frame that had already been
converted, submitted **and drawn** — `STREAMOWN` says `blocked_inflight=0`,
`no_texture=0`, `submit=2114/2114`, so there was no back-pressure anywhere. A
conversion or GX deadline miss cannot produce a hold; it would produce a
token-gate refusal. What remains is the framebuffer branch: two XFBs, and
`xfb_target()` returns −1 when the VI is scanning one while the other has been
handed over but not yet latched.

**`presented` does not mean displayed.** It means `VIDEO_SetNextFramebuffer()`
was called. Actual scanout is not observable in this runtime, and the new
vocabulary says stage B rather than borrowing a stronger word. The public
counters were not renamed — that would be churn across four documents and a
parser — but the mapping is now written down (GBP-VID-015).

**The generic key already existed.** `struct gbp_vqueue_desc` carries the
assembler's `frame_index`, so nothing had to be invented to have a
stimulus-independent identity; what was missing was carrying it past conversion,
which is a texture→lifecycle map written when the token is armed and cleared by
the release. The join to OGBPIDXCAP1 is offline.

**There is no publish timestamp, and that is a measurement.**
`gbp_vqueue_publish()` runs in the same service cycle that closed the frame,
from the frame's own timestamps, and reads no clock of its own. Close and
publish are one event. The field was removed from the record rather than
recorded twice.

**`VIDEO_GetRetraceCount()` instead of a retrace callback.** libogc2's handler
is already installed by `VIDEO_Init()`, so the ordinal costs no interrupt load
and no new callback — the stronger measurement without the risk §V5.46 warned
against taking.

**The audit caught something I did not set out to do.** The trace made
`submit_ready()` large enough that GCC stopped inlining it, so the pinned call
site moved from `{pump: 2, main: 1}` to `{submit_ready: 1}`. Code layout, not
behaviour — one call and return per presentation — but it is recorded rather
than quietly re-pinned, and the property the pin exists for is unchanged: the
submit is still unreachable from `gbp_vstate_probe_run`. A second pin had to be
dropped instead of updated, because `submit_ready` is `static` and its callers
carry no relocation: asserting them would have been asserting the unobservable.

**Two changes deliberately not made.** `OGBPIDXCAP1 v1` stays frozen — the
downstream trace is a new file, not a version. And the `STREAMWITT` metric split
(GBP-HW-190) was authorised but refused: the sample is taken inside
`gbp_vstate_probe.c`'s service path, and this round's whole audit rests on that
file being untouched. It is also redundant now — the trace records
`convert_ticks` per frame, which is attributable and excludes warm-up by
construction.

**New unknowns:** none. `U-GBP-029`, `U-GBP-033`, `U-GBP-034` stay open.

**Next:** one supervised physical run with `stream-0007` and the same
`indexed-0003` cartridge, returning THREE files. The source gate comes first —
the same run must pass `tools/vindex.py` with `OBSERVED_CONTIGUOUS` before any
downstream evidence is interpreted. Only after that trace exists may anyone
decide whether the answer is pacing, conversion scheduling, GX scheduling, XFB
policy, or that the holds are expected cadence behaviour.

## 2026-09-19 — the first downstream trace: the holds are a phase condition

**Goal.** Ingest run 5, require `OBSERVED_CONTIGUOUS` again before looking
downstream, and explain the holds from recorded state. No pacing change, no XFB
change, no hardware.

**Source first, and it replicated.** The unmodified analyzer returned
`OBSERVED_CONTIGUOUS` on a different build with the trace running — 2048/2048
records, FRAME_ID 85..2132 complete, FAULT clear, VMARGIN 24 — and an
independent decode reproduced every figure from the bytes. That is also the
first evidence that the instrumentation did not disturb the source result.

**The answer, in one line:** every hold is a frame that reached the XFB decision
with nothing queued behind it and found both framebuffers spoken for, and the
holds recur at the source↔VI beat period.

**What the trace could rule out.** Conversion cost is indistinguishable between
held and selected frames (56 229 vs 56 237 ticks). `submit_refusals` is 0 across
every lifecycle, `blocked_inflight=0`, `no_texture=0`. And `newest_source` is
NONE at **all 2 114 decisions** — at no point in the run was anything queued. H2
and H3 are not supported for these holds.

**A correction I have to make to my own last round.** §V5.46.6 said held frames
were "already converted, submitted and drawn". The DrawDone comes *after* the
decision in 2047 of 2047 cases; the order is convert → submit → decision →
asynchronous DrawDone. The conclusions survive because they rested on the
back-pressure counters and not on the word, but the word was wrong and §V5.47.6
says so.

**Two estimator lessons.** A span ratio over a sampled retrace counter is biased
by the phase difference between the first and last sample: it gave 675 531.65
ticks and residuals *wider than the period*, which is the estimator announcing
its own failure. Estimating by feasibility — a period is admissible only if every
residual fits one window of its own width — pins it to a 1.68-tick interval
around 675 675.00 ticks = 59.940 06 Hz, NTSC nominal to five decimals. And the
retrace origin is itself only pinned to 15.4 µs, so the three "how close to the
boundary" figures are reported as ranges, not as values.

**The phase result.** Every hold in the run falls in the final 0.580 ms of a
16.683 ms interval — 3.48 % of it — against selects that span the whole
interval. Sharper: of the 16 decisions that shared a sampled retrace with their
predecessor, **all 16 were holds and none was a select**. With two framebuffers
that is the defined outcome, not a coincidence.

**The beat.** 59.727 083 Hz source into 59.940 060 Hz display predicts a beat
every 280.44 source frames; the observed cluster gaps mean 280.07 — 99.87 % of
the prediction, stable across thresholds 15–30. Recorded as CORROBORATED, not
FACT: seven gaps in one run.

**An off-by-one in my own instrumentation, found and not fixed.** `in_window`
covers 69..2116 while the scientific window is 70..2117, because the flag is
`gbp_vwitness_armed()` sampled at TAKE time and the witness arms earlier in the
same service cycle. `tools/vdisp.py` inherits it and prints 2031 from the flag
beside 2030 from its own join, which is how it surfaced. This is an ingestion
checkpoint, so the semantics stay frozen, every number came from the exact
`frame_index` join, and a test now pins the defect so a fix has to name it.

**Trigger and policy are different things, and both are true.** The phase drift
creates the no-writable-XFB condition; the two-buffer hold policy decides what
to do about it and is working as specified. A future change must say which one
it addresses.

**Rejected framings.** That the holds are a backlog — nothing was ever queued.
That they are a conversion or GX miss — the costs are identical and nothing was
refused. That `repeats=0` would be an improvement on its own: 59.727 Hz into
59.940 Hz cannot be lossless, and a change that stops counting the dropped
frames would be worse than one that counts them.

**New unknowns:** none. U-GBP-029, U-GBP-033, U-GBP-034 stay open.

**Next:** the question is frozen in §V5.47.13 — what should the runtime do with
the frame that arrives when no framebuffer is writable, and by what metric is a
change an improvement rather than a different way of losing the same frame. Four
families are tabulated with what each tests and what would distinguish success
from hiding the drop. **None is selected and none is implemented.**

## 2026-09-19 — the cadence model: two framebuffers are enough

**Goal.** Decide, offline, which presentation policy preserves every interior
source frame while converting ~59.727 Hz into ~59.940 Hz. No runtime change, no
XFB change, no hardware.

**I had to correct myself first.** Last round I wrote that 59.727 into 59.940 Hz
"cannot be lossless". That is wrong if "lossless" means source frames. Because
f_vi > f_src the display has MORE intervals than the source has frames — 2053
for 2047 over run 5's span — so every frame can have its own interval with some
left over, and the leftovers must repeat. The rate difference requires **7**
display repeats over that span. The current policy lost **17 source frames**.
The 17 are not the 7; they are a scheduling outcome, and conflating them is
what the single `repeats` counter has been encouraging.

**The model had to earn its use.** Two fitted parameters: the VI period by
feasibility (675 675 ticks = 59.940060 Hz, admissible range one tick wide), and
a latch setup margin of 650–877 ticks. With the margin the model reproduces all
2114 recorded `(current, pending)` pairs and drops the same 17 frames; without
it exactly three events disagree — and those three are the three holds where the
sampled retrace had advanced. That is how the margin was found rather than
guessed: a hand-over issued within ~16–22 µs of a boundary misses it.

**The answer is A, and the margin is not close.** Two-XFB deferral loses nothing
across the physical replay, 1024 initial phases, a ten-minute horizon and up to
ten times the measured jitter. The deferred queue never exceeds ONE frame. Over
ten minutes it emits exactly the 128 display repeats the rate difference
requires and not one more. Latency p99 0.316 ms, max 1.264 ms, no drift.

**A third framebuffer is not the answer, and the way it fails is the point.** It
turns 17 drops into 17 SUPERSESSIONS: `VIDEO_SetNextFramebuffer` latches once
per retrace however many buffers exist, so a second hand-over before the
boundary overwrites the first and that frame never reaches the screen. A model
that counted hand-offs rather than latches would have called that a success — so
supersession became a first-class outcome in the simulator, and the mutation
round has a case for hiding it.

**The retry site already exists.** `pump()` re-offers any READY texture every
~158 µs. What terminates the frame today is that `submit_ready()` asks GX before
it asks the framebuffer. Asking about the framebuffer first would leave the
texture READY and let the existing loop retry it, with no new state, no new
callback and no extra memory. That is an illustrative shape, not code: nothing
was implemented.

**Two estimator lessons, both mine.** Fitting the source on the decision ORDINAL
instead of the frame_index folds the 17 missing frames into the slope and turns
sub-millisecond jitter into a 33 ms artefact; the numbers were absurd enough to
catch it. And modelling jitter as an accumulated interval perturbation is a
random walk that drifts the source off its own rate — the physical source is
locked to the AGB clock and what varies is where the decision lands, so the
offset is per-frame and not cumulative.

**The analyzer is corrected, the history is not.** `OGBPDISP1` bit 0 is now
named `WITNESS_ARMED_AT_TAKE`, and `scientific()` requires the witness and does
the exact frame_index join — without one it raises rather than falling back. The
contradictory pair the report used to print is gone. No sidecar byte changed and
run 5 still reads 2030 / 17 / 1.

**Mutations: 12 of 12**, after three rounds of fixing my own tests rather than
the mutants. Two were inert because the tests never exercised the paths (the
overtake clamp and the queue-depth counter), and one survived because nothing
pinned the baseline's display-repeat count — which is exactly the drop/repeat
separation this round exists to establish.

**New unknowns:** none. U-GBP-029, U-GBP-033, U-GBP-034 stay open.

**Next:** a pre-registered implementation round for policy A, with the gates in
§V5.48.10 frozen first — source `OBSERVED_CONTIGUOUS`, zero interior loss,
display repeats counted explicitly and within ±2 of the rate requirement,
ready→hand-off p99 under 1 ms, deferred depth never above 1.

---


## 2026-09-19 — policy A implemented: a frame that cannot be shown is kept, not dropped

**Goal.** Build the two-XFB asynchronous deferral the model chose, separate
source disposition from display cadence in the instrumentation, and audit it.
No hardware, no third framebuffer, no source-path change.

**The audit before the edit paid for itself twice.** First: the retry site
already existed — `pump()` re-offers a READY texture every ~158 µs — but the
ORDER did not. `gbp_vpresent_acquire()` hands out the lowest FREE texture and
the old loop scanned from index 0, so a newer frame converted into a lower slot
could have overtaken a deferred older one. Policy A could not simply reuse the
machinery; it needed the offer to go by AGE. That needs no second queue: the
READY state *is* the deferral, and one helper picks the oldest lifecycle index.

Second: the whole shape depends on asking the framebuffer question before the GX
submit, and that is only sound if the answer cannot go stale. It cannot, and it
is a proof rather than a hope: `xfb_target()` returns a slot only when
`xfb_pending == -1`, and with nothing handed over the VI has nothing to latch,
so a retrace cannot change which buffer is current. No other caller claims a
stream framebuffer and the one ISR touches textures only. The precheck is in
fact safer than the old order, which asked *after* the submit and left a longer
window.

**OGBPDISP2, because v1 honestly cannot say this.** Policy A introduces a
NON-TERMINAL event — defer now, hand off later — and v1 was built around one
decision per lifecycle. Expressing it there would mean overloading
`HOLD_PREVIOUS_FRAME`, a word that already names 17 physically discarded frames
in run 5. Reusing it would silently reinterpret an existing capture. So the
version is bumped, `tools/vdisp.py` reads both, and a v1 file carrying a v2
disposition is rejected rather than reinterpreted.

**Defer attempts are aggregated, not evented.** The retry runs from `pump()`;
one event per attempt would be unbounded and would perturb the thing it
measures. The first defer emits one event, the rest advance a count and a last
timestamp. At most two events per frame.

**The counters now mean one thing each.** `gbp_vqueue_note_repeat` is gone from
the runtime entirely — policy A never terminates a frame on a busy framebuffer —
and `dropped_interior` is a tripwire that must stay zero. The new summary line
is `DISPTRACE`, not `STREAMDISP`: the legacy tag already names the conservation
identity, and a test now refuses duplicate tags outright.

**Three tests had to be re-anchored, and one of them twice.** A guard that
forbids `VIDEO_WaitVSync` in the present path fired on the COMMENT that says
"NEVER VIDEO_WaitVSync here" — the same trap the §V5.44 predicate guard had to
be taught, and the same fix: strip comments first. Another pinned
`gbp_vqueue_note_repeat(account)`, which policy A deletes; its INTENT (the queue
is only ever notified through the account parameter) survives and is now
asserted as the call's absence. A third used a fixed byte window that the
reordering pushed its targets out of, and is now anchored on ORDER.

**The two parsers disagreed and now do not.** The C parser checks that each flag
agrees with the counter it summarises; the Python one did not, so a file
CLEARING `interior_loss` while carrying losses would have read as a clean run in
one language and been rejected in the other. The Python parser now enforces the
same rule, and a test exercises the dangerous direction rather than the harmless
one.

**Fifteen mutants, and the three that survived the first pass are the story.**
Twelve were refused immediately. **M5** — not clearing the texture→lifecycle map
after a hand-off — turned out to be behaviourally EQUIVALENT, and provably so:
the key is written when the texture is *acquired*, before the conversion starts,
and read only under a `READY` guard, so no reader can see the stale value. It is
pinned anyway, because the equivalence is a property of the guard and not of the
map. **M10** — dropping `ev_overflow++` on the defer path — was a real gap: the
trace still failed `intact()` through its own identity, but the file would have
reported `event_overflow == 0` beside missing events, pointing a future analyst
at a counting bug instead of at capacity. **M13** was the dangerous one: the
existing pin asserted the framebuffer question came before the submit using the
FIRST match, so a SECOND call inserted after `gbp_vpresent_submit()` left the
assertion true while handing `GX_CopyDisp` a fresh answer — possibly `-1` — and
discarding the very answer the safety proof is about. The pin now requires
exactly one call site. Both replacements are anchored on counts and on order,
never on a byte window; that failure mode has now cost this project four
separate guards.

**The self-test could have passed without displaying anything.** `released` is
zero-safe — with no token ever armed there is nothing in flight — and policy A
makes that reachable, because if all eight offers defer nothing is presented.
`selftest_ok` now requires a present explicitly.

**Object-level audit.** `gbp_vdisp.o` has `.data = 0`, `.bss = 0` and no data
relocation of ANY kind, which answers audit finding F8 by absence rather than by
enumeration; its only outward edges are `memset` in `init` and `take`, and every
capture-path function carries no relocation at all. `defer` and `decision` are
loop-free at 127 and 206 instructions, so those counts are hard bounds on a
whole call rather than averages.

**Tests executed.** 293 checks in `test_gbp_vdisp` (12 new), 828 host tests, the
full C suite green, nine POC object audits at 0 findings with the interrupt path
byte-identical to the physically validated GBP-VIDEO-001 build, and Dolphin PASS
with and without the Game Boy Player. `stream-0008` at `5126a19`, 492 416 B,
`a9efe181…81282`, built twice from scratch and byte-identical both times, no
`-dirty` stamp, Swiss export identical. MEM1 keeps 4.58 MiB free after the
framebuffers.

**New unknowns:** none. U-GBP-029, U-GBP-033, U-GBP-034 stay open.

**Next:** one supervised physical run with `stream-0008`, gates frozen in
§V5.49.15 — source `OBSERVED_CONTIGUOUS` first and always, then zero interior
loss, deferred depth ≤ 1, ready→hand-off p99 ≤ 1.0 ms and max ≤ 2.5 ms, and
display repeats reported separately against a range the analyzer derives from
that run's own cadence. Not a fixed 7, and never a failure by themselves.

---

## 2026-09-19 — policy A on hardware: 2047 of 2047, in order, and the repeats fell by exactly 17

**Goal.** Ingest the first physical `stream-0008` run, decide Policy A against
gates that were frozen before the cartridge was powered on, and — separately —
find out why the operator still sees a checkerboard at startup instead of the
Game Boy booting. No hardware, no runtime change.

**The result, in one line.** Run 5 lost 17 interior source frames downstream and
needed 24 repeated VI intervals; run 6, same stimulus and same VI, lost none and
needed 7. **24 − 7 = 17.** The display had to fill the same 2053 VI intervals
either way — the two runs' hand-off spans differ by one microsecond — and every
frame run 5 threw away had forced one repeat. Policy A stopped throwing them
away and the repeats fell to what rate conversion alone requires.

**Source first, and it replicated a third time.** `tools/vindex.py` unmodified:
`OBSERVED_CONTIGUOUS`. An independent byte-level decode — own record iteration,
own sequence analysis, `istim` only for the frozen symbol contract — agreed on
all 81 920 blocks: valid symbols, SYNC `0xB2`, CRC-8, `BLOCK_INDEX == slot`,
STATUS `0x18` everywhere, FAULT 0, VMARGIN 24, `FRAME_ID` 85..2132 with 2047 of
2047 adjacent deltas of +1. That gate had to pass before any downstream number
was allowed to mean anything, and the analysis order was not negotiable.

**The order was rebuilt, not trusted.** `order_violations = 0` is a counter, and
a counter is what a bug disables. Sorting the 2047 hand-offs by decision
timestamp gives `70, 71, …, 2116` exactly, and for each of the 48 deferred
frames no lower index appears after it. This was the specific risk found before
the run — `gbp_vpresent_acquire()` hands out the lowest FREE texture, so a newer
frame in a lower slot could have overtaken a deferred older one — and the
age-ordered offer held on hardware.

**The mechanism is visible, not inferred.** Every one of the 48 deferrals
resolved on the *very next* retrace: `retrace_decision == retrace(first defer) +
1`, 48 times out of 48. The deferrals also fall into seven clusters, which is the
same source↔VI beat that produced seven repeats.

**A counter changed meaning and the run proves it numerically.** `xfb_skipped`
counts one branch of `gbp_vpresent_xfb_target()`. In stream-0007 that branch was
terminal and `xfb_skipped = 17` was 17 discarded frames. In stream-0008 the same
branch defers, and `xfb_skipped = 129` equals `DISPSRC defer_attempts = 129`
exactly — every one resolved, `repeats = 0`, `dropped_interior = 0`. The two
builds must never be compared on that number as if it meant one thing.

**Both latency gates passed on definitions fixed in advance.** ready =
`t_convert_done`, hand-off = `t_decision`, population = every scientific
hand-off, percentiles by `vpace.py`'s convention. p99 0.4946 ms against 1.0, max
1.1353 ms against 2.5 — the maximum landing *below* the model's own replay worst
case of 1.264 ms. Twelve of twelve pre-registered gates passed and none was
renegotiated after the data was seen.

**The analyzer got it wrong first, and that was worth finding.** `tools/vdisp.py`
reported `disposition-claim ready False` on a structurally perfect trace: its
`usable()` still applied the v1 identity `decisions == event_n` while `parse()`,
eleven lines above, applied the v2 one `decisions + deferred == event_n` — the
rule the C parser and `gbp_vdisp_intact()` both use. Under v1 the two coincide,
because a v1 trace has no deferrals, so the defect was invisible until a frame
deferred. The file was proven intact independently *before* the tool was
touched; then the fix, with regressions stating the rule in the dangerous
direction and pinning both call sites as one rule. The report was also
hardcoded to print `OGBPDISP1` for any version. Run 5 re-parses unchanged.

Two related things were found and deliberately NOT fixed, being out of scope:
`usable()` does not test `order_violations`, and `gbp_vqueue.h` still carries a
comment asserting `repeats = xfb_skipped`, which Policy A makes false.

**The checkerboard is ours, and the boot logo was answered by a run we already
had.** `display_selftest()` builds `w = ((x>>3)<<10) | ((y>>3)<<5) | ((x^y)&0x1F)`
— a horizontal red ramp, a vertical green ramp and an XOR blue checkerboard.
Rendered, it is exactly what the operator described: diagnostic GameCube output,
never Game Boy video. It holds the stream framebuffers for 5.1777 s, of which
5.000 s is the `PREHANDLERWAIT` diagnostic, and the AGB is *running* throughout
— the probe says so at the wait and `control_pre=8e control_post=8e` confirms it.

Why no logo reaches the screen needed no new experiment. `vstate-0001`, with no
wait, saw the structured screen appear 0.5014 s after capture start and animate
for three seconds. `vstate-prewait-5000`, with the same 5 s wait, reported
`STRUCTURED not_observed` and a baseline valid by frame 4. The animation happens
entirely inside the masked wait — which is precisely what the wait is for:
without it the colour capture would certify inside the AGB's boot. Nothing
prevents starting video that early; the wait is a configurable diagnostic,
default OFF in the module. Recorded as a separate startup research gate, kept
out of the GBP-VIDEO-004 milestone wording on purpose.

**Tests executed.** 867 host tests (+39: 33 new run-6 regressions, 6 analyzer
regressions), the full C suite green, nine POC object audits at 0 findings,
Dolphin PASS with and without the Game Boy Player, and `stream-0008` rebuilt to
`a9efe181…81282` unchanged. The run-6 `OGBPDISP2` and a qualification projection
are versioned as fixtures, so `24 − 7 = 17` is recomputed wherever the suite runs.

**New unknowns:** none. U-GBP-029, U-GBP-033, U-GBP-034 stay open.

**Next:** decision A — Policy A is physically confirmed for this scoped run and
replication is recommended, not required. The highest-value next experiment is
no longer pacing: it is the startup question, as its own build with its own
identity, asking what the VIDEO stream carries with a Game Pak inserted from the
CONTROL transform onward. No existing run answers it.

---

## 2026-09-19 — the normal startup: black, then the Game Boy Player

**Goal.** Take the diagnostic experience off the path a user walks — no
synthetic test pattern, no five-second wait — start real video as early as the
protocol allows, and keep Policy A exactly as the hardware validated it. No
hardware this round.

**Two causes, both diagnostic, and the source said so.** The rainbow/checkerboard
is `display_selftest()`'s coordinate gradient reaching the video interface
through its own present. The five seconds are `cfg.prehandler_wait_ms`, whose
module default is already ZERO and whose own comment calls it "a DIAGNOSTIC,
default OFF". Between them they owned the screen for 5.1777 s, of which 96.6 %
was the wait.

**The A/B for the missing logo was already in the repo and I did not need a new
run.** `vstate-0001`, no wait, saw the structured screen 0.5014 s after capture
start and captured the animated GAME BOY logotype. `vstate-prewait-5000`, same
5000 ms, reported `STRUCTURED not_observed` over 10 446 frames. The animation
happens inside the wait — which is exactly what the wait is FOR: §V3.26 records
that without it the colour capture would certify inside the AGB's boot. That is
a requirement of a MEASUREMENT, and this round is the first to separate it from
a requirement of the runtime.

**I classified every startup operation before removing anything.** DET probes,
CONTROL transform, A1 and A2 (both self-terminating), handler install, PREUNMASK
check, first unmask: PROTOCOL- or SAFETY-REQUIRED, and all of them stayed
exactly where they were. Precisely two items were DIAGNOSTIC-ONLY, and those are
the two that left the normal path. Nothing was moved to gain time.

**One switch, not three `#ifdef`s.** `gbp_startup.h` resolves one profile from
one enum, once, at the top of `main()`. An unknown mode resolves to NORMAL on
purpose: a typo must cost a diagnostic, never a user.

**The self-test still runs — headless — and the reason it claims no framebuffer
is the interesting part.** Skipping only the present would have been a disaster:
`gbp_vpresent_xfb_handed()` sets `xfb_pending`, which clears only when the VI is
observed to have latched that buffer. Bookkeeping without a buffer leaves it set
forever, and with two framebuffers `xfb_target()` would then never return a slot
— every real frame would defer for the entire run. The safe split is the clean
one: touch the framebuffer state machine, or do not. Dolphin shows the result in
one field: `SELFTEST … xfb=0` in normal mode, `xfb=1` in diagnostic, with
`submits=1 drawdone=1 releases=1` in both.

**Black, not memory.** `SYS_AllocateFramebuffer` does not clear, so the old path
pointed the VI at whatever was in RAM until the self-test's copy landed. Both
stream framebuffers are now cleared to black in both profiles.

**Policy A is untouched rather than unchanged**, and it is testable:
`selftest_submit_headless()` calls nothing in `submit_ready()`, and
`submit_ready()` contains no reference to the profile at all. Every pacing
module is byte-identical and the interrupt path is still identical to the
physically validated GBP-VIDEO-001 build.

**The mutation that mattered was M15.** Fourteen were refused immediately. The
fifteenth inserted one `ringlog_printf` between `gbp_vpresent_inflight()` and
`GX_CopyDisp()` — a formatting call in the path that runs once per source frame
— and every existing guard stayed green. `ringlog_printf` is bounded and
in-memory, which is exactly why it looks harmless and why a startup trace would
drift there. The capture hot path now carries an explicit no-formatting,
no-filesystem guard, and M15 is CAUGHT only because of it.

**Two of my own guards also fired, correctly.** The `TheWiringInMainIsPinned`
pins started measuring the wrong function the moment a new function appeared
above `submit_ready()` — the third time anchor-on-first-match has misfired in
this suite, now scoped to the function body. And the tag-uniqueness guard caught
`STARTUPV` being emitted with two different layouts under one tag; it is now one
shape with `have_first=0|1`.

**Two audit pins moved deliberately**, with the arithmetic written down:
`gbp_vpresent_submit` gains the inlined headless submit, `gettime` rises from 2
to 8 in `main` (five startup timestamps plus the headless submit plus the two
that were there). `pump` and `submit_ready` are unchanged, and the property both
rules exist for — that `gbp_vstate_probe_run` is absent — still holds.

**Two semantic debts paid.** `usable()` now refuses `order_violations != 0`,
because the claim it gates says "in order". And `gbp_vqueue.h` no longer asserts
`repeats = xfb_skipped` as current: the measurement stays as labelled history,
the claim does not, and no counter changed.

**Tests executed.** 901 host tests, 67 new C checks for the profile alone, the
full C suite green, eight object audits at 0 findings, Dolphin PASS in both
profiles, 15/15 mutants refused. `stream-0009` at `59d2f57`, 494 176 B,
`4d0337bb…c955`, built twice from scratch and byte-identical by SHA-256 and by
`cmp`, no `-dirty`, Swiss export identical. The fuseblk incoherence recurred
three times, in both known forms.

**F8, for this build only.** `gbp_vdisp.o`, `gbp_vpresent.o` and `gbp_vqueue.o`
have no non-text relocation section at all. `main.o` has twelve bytes of
`.rodata` with three relocations, which I resolved and read back as
`"gbp-video-stream-probe"`, `"stream-0009"` and `"59d2f57"` — the build identity
struct, not a function-pointer table. The auditor's generic blind spot is NOT
fixed and I am not claiming it is.

**New unknowns:** one small documentation discrepancy, recorded rather than
guessed at: `UNKNOWNS.md` says the logotype appeared 0.5014 s "after capture
start" and `ROADMAP.md` says "after the AGB starts", which differ by the
~0.107 s prefix. The 400 ms startup gate holds under either reading.

**Next:** two physical runs that answer different questions. RUN A is the
controlled regression on `indexed-0003` — no synthetic frame, first real
hand-off within 400 ms of the CONTROL transform, and every Policy-A gate
unchanged. RUN B is a real cartridge, purely operator observation, and the
runtime must not depend on a logo appearing.

---

## 2026-09-20 — run 7: the startup passed, and the window opened one second early

**Goal.** Ingest the first physical normal-startup run, judge the startup by its
pre-registered gates, judge Policy A separately, run the frozen source analyzer
untouched and keep whatever it says, and explain the new interaction between
early video and the OGBPIDX scientific window. No trimming, no qualification
change, no new delay, no runtime change.

**Conclusion I — the startup did what it was built to do.** `STARTUP
mode=normal … presented_synthetic=0 headless_submits=1`, no `PREHANDLERWAIT`
line in the log at all, and the first real hand-off **165.154 ms** after the
CONTROL transform against a 400 ms gate — §V5.52 predicted 153.2 ms. The
self-test executed (12.2 ms, converted, drawn, released) and was not shown; its
lifecycle ends TERMINAL_PENDING with `F_SELFTEST`. Eight of eight machine
gates, and not one of them cares when the stimulus began. No operator visual
observation was supplied, so none is written down.

**Conclusion II — the frozen analyzer said `OBSERVED_CONTIGUOUS`, and I kept
its composition.** `intact 1988`, `INVALID_CANONICAL_STRIP 60`,
`OBSERVED_ID_CONTIGUOUS 1986`, IDs 0..1987. My own decode agrees to the block:
records 0..59 have zero valid canonical blocks of 2400 (2218 fail SYNC, 182 the
symbol test); record 60 is FRAME_ID 0 with STATUS 0x7F, 61 is ID 1, 62 is ID 2
with STATUS 0x18, and 62..2047 run ID 2..1987 with 1985 deltas of +1. The
window opened **3.840 s** after CONTROL; the stimulus began at **4.845 s**.
One second early.

**The number that explains everything is 4.845 s, four times.** I went back to
runs 4, 5 and 6 and inferred when ID 0 landed from record 0's FRAME_ID (85) and
the cadence: 4.8450 s in all three. Run 7 measured it directly at 4.84498 s.
The cartridge's boot is the invariant. The old 5 s wait never changed it — it
pushed the window to 6.27 s, 1.42 s past it. Remove the wait and the
content-blind qualifier does exactly what it is for on the boot's own clean
frames, 1.00 s before the stimulus exists. **That is a coupling between startup
UX and window orchestration, not a defect in anything that ran**, and the same
run shows the transport, the assembler, the qualifier and Policy A all clean.

**Policy A, whole run and join.** 2244 hand-offs in strict order, 44 deferred
over 108 attempts, every one on the very next retrace, depth 1, p99 0.4591 ms,
max 1.0005 ms. The 24 indices missing from the total sequence all have no
lifecycle: never published, 13 incomplete + 13 anomaly, all in the boot, none
in the join. Over the frozen join: 2047 handed, one TERMINAL_PENDING edge, and
**seven display repeats beside zero drops — the same seven as run 6.**

**The boot was captured, and it looks like the logotype run.** Episodes 1 and 2
(frames 30..89, 90..149) are identical in open, close, length, flags and
signature to `vstate-0001`'s — the run whose pixels reconstructed to the
animated GAME BOY logotype. CORROBORATED, not FACT: the stream sidecars carry no
raw pixels, and equivalence is not a photograph.

**Two things I recorded rather than fixed.** `DISPSRC terminal_pending=0` in the
log against 2 in the header: the line prints before `gbp_vdisp_finish()`. And
the 13/26/13 transient counts against run 6's 2/4/2, which are the boot being
seen, not a regression.

**Design, analysed and not built.** A content-blind not-before gate on the
structural streak only — transport, display, conversion and Policy A untouched —
at 5.000 s after CONTROL, chosen from the whole history so a future window lands
where runs 4–6 did (≈6.1–6.3 s). Rejected: any sleep, the old wait, any VSync
loop, any transport suppression. A final runtime needs none of it.

**RUN B can proceed now.** The startup passed on its own terms. The corrected
controlled run is a different question and no normal-startup build gets a new
GBP-VIDEO-004 continuity record until it exists.

**Tests executed.** 901 host (+20), full C suite, nine audits at 0 findings,
Dolphin PASS both profiles with `xfb=0`, `stream-0009` rebuilt to
`4d0337bb…c955` unchanged. Fixtures: the OGBPDISP2, a qualification projection
and a 230 KB structural projection carrying per-record validity, FRAME_ID,
STATUS and the verbatim verdict.

**New unknowns:** none. **Next:** RUN B with a real cartridge (operator
observation), and — separately authorised — the §V5.53.12 gate followed by a
corrected indexed run.

---

## 2026-09-20 — run B: a person saw the Game Boy boot; then the witness learned to wait

**Goal.** Ingest the first retail-cartridge run of the normal startup, keep the
operator's words separate from the machine's, classify GBP-VIDEO-005 against
criteria written before the run, and — only if nothing functional blocked it —
implement the research not-before gate designed in §V5.53.12. No hardware for
the gate. BBA still disconnected.

**First, a near miss with the archive.** The operator's files arrived under the
runtime's own names, `GBP-VIDEO-004_stream-0009*`, and overwrote run 7's raw
copies in `logs/`. Run 7 survives only because the previous round archived it
under a run-suffixed name in `captures/local/` — the exact hazard the HANDOFF
has carried since run 3 overwrote run 1. Run 8 went to
`captures/local/GBP-VIDEO-005_stream-0009-run8*`, byte-verified, before anything
else was done. The embedded id is still `GBP-VIDEO-004`; the binary was not
rebuilt for an experiment label, and that is intentional.

**The machine said the same thing as run 7, to half a millisecond.**
`STARTUP normal … presented_synthetic=0 headless_submits=1`, no wait line,
first real hand-off **164.696 ms** after CONTROL against run 7's 165.154 ms — on
a different cartridge. Policy A clean on retail content: 2244 hand-offs in
order, 43 deferred / 97 attempts all on the next retrace, p99 0.334 ms, and
**seven display repeats over the join for the third run running**. The retail
witness was checked as a container (CRCs, seals) and not decoded: no OGBPIDX
verdict exists for a game, and I did not manufacture one.

**The startup transient is the console's, not the cartridge's.** FRAMECAP,
WITQUAL and the four preserved structured episodes are *identical* between run
7 (indexed stimulus) and run 8 (retail game) — 13/26/13, 223/222/12/26,
8..25 / 30..89 / 90..149 / 150..197 with the same flags and signatures — and
episodes 1–2 remain identical to `vstate-0001` with no cartridge at all. The
first ~3.4 s of structure belong to the Game Boy Player's own boot. After that
the two runs diverge exactly as content should (218 stable episodes for a game
holding screens, 43 for a stimulus that changes every frame).

**The operator saw the logo.** A: yes. B: complete — "if it cut anything, only
milliseconds at the beginning; without audio I could not notice anything
definite", and that uncertainty stays uncertainty. C: an almost instantaneous
black flash with some text. D: clean. E: stable. F: almost immediate. Recorded
as observation and never promoted.

**The flash is ours, and the source proves it in one line each.**
`video_setup()` points the VI at the console; `main()` prints its banner there;
the VI moves to the black stream framebuffer only at the line before the probe
runs. `STARTUPT` puts that window at +15.092 → +33.155 ms: **eighteen
milliseconds of black console with light text**, one field, then black, then
the first real frame at 210.664 ms. DEBUG/RESEARCH UX ARTIFACT. Not the
self-test (`presented_synthetic=0`), not Game Boy video, not changed this round.

**GBP-VIDEO-005: PASS, with a DEBUG-UX NOTE.** Every pre-registered criterion
met; the note is the console flash, identified and outside the intended final
UX. CORROBORATED, with the two sources named apart: NORMAL startup exposes the
real cartridge startup sequence to the user. The NORMAL-startup milestone is
physically validated for the seven properties listed in §V5.54.11 X. Final
production UX is not claimed — the flash is why.

**Then the gate, because nothing blocked it.** `stream-0010` defers one thing:
when the 64-frame structural streak may be counted — 5000 ms after the CONTROL
transform, the epoch every safety budget already uses, chosen from four runs in
which the stimulus began at 4.845 s and never fitted to run 7. A latch in
`gbp_vwitness` with no clock; one 64-bit compare per `pump()` call until it
releases, then nothing; frames before eligibility still counted as seen, so
FRAMECAP, resyncs, BASELINE and STRUCTURED keep telling the startup's story;
streak from zero at release; everything after it the old rule, untouched.
Default OFF in the module — a witness never gated is field-for-field the old
behaviour, which is how 12 191 existing witness checks stayed green.

**Two of my guards fired, both correctly.** The startup guard forbids any
`5000` in `main.c`, and the new eligibility constant is a 5000. It was right to
fire and wrong in what it named; it now forbids what it protects — a 5000
reaching a *wait* — and still catches the old one. And the content-independence
scan I wrote for the gate tripped on `GBP_VSTATE_F_RESYNC`, the assembler's own
structural flag; word-bounded now, so the stimulus's `SYNC` is forbidden and the
assembler's resync is not.

**A requirement from the operator, recorded and not built.** When scaling
comes, a pixel-perfect mode must preserve the source pixel lattice under an
integer nearest-neighbour scale: no anisotropic stretch, no silent fractional
scale, borders rather than deformation. Roadmap and GBP-VID-032; nothing
implemented; no resolution chosen.

**Tests executed.** 944 host (+23), 12 191 witness checks (+8 latch tests),
full C suite, nine audits at 0 findings with the interrupt path identical to
GBP-VIDEO-001 (after `video-audit` first — the F3 ordering), Dolphin PASS in
both profiles with `xfb=0`. Run-8 OGBPDISP2 and a content-blind qualification
projection versioned.

**Next.** The controlled indexed run with `stream-0010`: what validates the gate
is `WITELIG released=1` at ≈5.0 s, a window opening after the stimulus's first
normal-status frame, `vindex.py` unmodified reporting `OBSERVED_CONTIGUOUS` with
`intact 2048 / INVALID 0`, and a startup still ~165 ms to first video with its
transient still in the log. BBA stays disconnected for that run.

---

## 2026-09-20 — run 9: the witness waited, and 2048 of 2048 came back clean

**Goal.** Ingest the controlled indexed run that §V5.55.7 pre-registered for the
research not-before gate, judge it only against those gates, and close the
controlled video sequence if they pass. Executor role: nothing redefined,
nothing rebuilt, nothing fixed.

**First the archive, then the hashes, then anything else.** The operator's
files carried the console's own names again. Following the rule written after
run 8, they went to the reserved `…-run9…` names with `cp --update=none` and
`cmp` before anything read them; runs 7 and 8 re-verified intact; all three
hashes matched the orchestrator's independent measurements. Media double check
still PENDING.

**Source first, frozen tool, verbatim.** `vindex.py` untouched at `f2de217`:
`OBSERVED_CONTIGUOUS` with **`intact 2048` and no `INVALID_CANONICAL_STRIP`
line** — the composition, which is the thing run 7 lacked (1988 / 60). My own
decode of every block agrees: 81 920 valid strips, IDs 73..2120 with 2047 deltas
of +1, STATUS 0x18 throughout, FAULT never, VMARGIN 24. Record 0 already carries
FRAME_ID 73, and ID 0 back-projects to 4.8450 s after CONTROL — the fifth run
at exactly that value.

**The gate did what §V5.55 said it would, on the machine's own clock.**
Eligibility at `202 506 346` ticks = 5.000156691 s after CONTROL, +156.7 µs —
one pump cadence, as the contract allowed. 292 frames had closed by then, 26 of
them disqualifying, and none of them counted. Then 64 clean closes, frames
292..355, `resets=0`, and the window opened at block 0 of frame 356, 6.067 s
after CONTROL, 1.22 s into the stimulus. Startup: first real hand-off
165.154741 ms, **eighteen ticks** from run 7. The transient is all still in
FRAMECAP and STRUCTURED. Policy A: 2047/2047 over the join, order rebuilt
exactly, p99 0.472000 ms, max 1.000148 ms, and seven display repeats for the
fourth run running.

**One line was cut, and I made sure it cost nothing it should not.** The header
said `truncated=1`. I measured every line: exactly one hits the ringlog limit —
`WITELIG`, 248 characters, ending `qual_streak_at_e`. Root cause in source:
`LOG_LINE_LEN 256`, seven characters of `%06u ` prefix, `vsnprintf` into what
is left. The lost field is `qual_streak_at_eligible`, which §V5.55.3 defined as
0 by contract and printed only so a broken contract would show. So I did not
assume it: `356 − 292 = 64 = required`, `qualify_frame 355 = 292 + 63`,
`resets 0`, and the 26 disqualified frames all precede eligibility — and then I
replayed those counters through the frozen `gbp_vwitness.c` itself. Only a
streak of 0 at release lands qualification on frame 355; 1 gives 354, 10 gives
345. DIRECT FIELD lost; SEMANTIC VALUE exact. REPORTING DEFECT, documented as
GBP-VID-033, not fixed in this checkpoint, and — checked against the contract's
refutation conditions, both absent — **no rerun required**.

**Fourteen of fourteen gates.** RUN 9: PASS. Physical validation of the
research-only, content-independent 5.000 s not-before witness eligibility gate,
under this controlled experiment on this console. Not a protocol requirement,
not a final-runtime delay, not a statement about other cartridges, not scanout,
not pixel fidelity, not BBA anything.

**The controlled video sequence is closed.** RUN B and RUN 9 were the two runs
the methodology restriction waited for. The BBA may now be considered as a
variable in the NEXT explicitly pre-registered topology/phase — which is a
sentence about method, not about the BBA.

**Fixtures.** The OGBPDISP2, a content-blind qualification projection and a
structural projection carrying the verdict with its composition, the WITELIG /
WITQUAL / STARTUP fields, the truncation finding with its derivation, and full
provenance (run, build, commit, DOL, raw sizes and hashes, topology, tool
identities). Fourteen new regression tests; run-7 and run-8 fixtures untouched.

**Next.** Reported to the orchestrator, not executed: what Phase 4 still
objectively lacks, the next roadmap candidates, what BBA PRESENT would actually
test, and whether a topology-control run should precede any network code.

---

## 2026-09-20 — run 10: the same binary, the adapter in the slot, the same numbers

**Goal.** Ingest `GBP-BBA-001`, the topology control the orchestrator placed
ahead of the `WITELIG` fix so that the exact run-9 binary could be re-run with
one intentional physical change — the Broadband Adapter present, Ethernet
disconnected — and nothing else. Executor role: gates pre-registered, nothing
redefined, nothing rebuilt, nothing fixed, no networking.

**The operator's four facts come first and stay the operator's.** BBA
presente: SIM. Ethernet: DESCONECTADO. Mesmo GameCube: SIM. Mesmo GBP: SIM.
Recorded as a topology declaration, never derived from a filename or a log.
The operator added `-bba` to the drop names — useful, kept as metadata — and
the files went FIRST to the reserved `…-run10…` names with `cp --update=none`
and `cmp`; run 9 re-verified intact; all three hashes matched the
orchestrator's before any of them was read into an interpretation.

**Source first, frozen tool, verbatim.** `vindex.py` untouched since `fbaea00`:
`OBSERVED_CONTIGUOUS`, `intact 2048`, no `INVALID_CANONICAL_STRIP` line, IDs
73..2120, 2046 decisive transitions. My own decode of every block agreed:
81 920 valid strips, 2047 deltas of +1, STATUS 0x18, FAULT never, VMARGIN 24 —
every count equal to run 9's.

**Then the rest, in order, and it read like run 9 to within ticks.**
Eligibility at 202 506 351 ticks (+5 vs run 9), first retained record
6.067209136 s (−10), first real hand-off 165.154321 ms (−17 ticks, −0.42 µs).
Transport 254 873 = 254 873 = 254 873, zero everything. OGBPDISP2 CRCs matched;
2047 of 2047 over the join in exact order; 46/112 deferrals all on the next
retrace; frozen latency p99 0.471778 ms, max 1.000765 ms; seven display
repeats for the fifth run in a row — observational, and I did not turn five
sevens into a gate. The known `WITELIG` cut recurred at 248 characters on the
same line, as the pre-registration said it would, and it is not a BBA finding.

**Fourteen of fourteen, again; PASS.** The only sentence the evidence licenses:
under this exact controlled topology and observation window, with the same
console, GBP, binary and stimulus, physical BBA presence with Ethernet
disconnected produced no detected regression in the established video control
metrics. Runs 9 and 10 are now a paired topology control. That is all they are.
Not "safe", not "irrelevant", not Ethernet, not initialisation, not
networking, not Phase 11.

**Fixtures.** The OGBPDISP2, a content-blind projection and a structural
projection that carries the operator's declaration as a declaration, the
supplied `-bba` names, the canonical paths, every hash, the verdict with its
composition, the gate and startup fields, the expected truncation, and the
run-9 comparison with a note that equality is an observation. Fourteen new
tests; run-9 and earlier fixtures untouched.

**What changes for the next checkpoint.** The reason for holding the `WITELIG`
fix has expired — the exact run-9 binary was reused successfully — so
GBP-VID-033 is the next functional checkpoint, and a new build there cannot
contaminate this comparison. Networking does not start; the orchestrator
decides after that repair is validated.

---

## 2026-09-20 — GBP-VID-033: the line that was too long is now two lines

**Goal.** Repair the one reporting defect two physical runs had demonstrated,
prove the repair cannot touch witness or runtime semantics, build a
deterministic artifact, and pre-register its physical validation. Executor
role; nothing else opened; no hardware; no networking.

**The defect, exactly.** `LOG_LINE_LEN 256`, a 7-character `%06u ` prefix, and
the NUL leave 248 characters of payload. `stream-0010`'s single `WITELIG`
record renders to 310 at the worst case of its conversions, and runs 9 and 10
each clipped it after `qual_streak_at_e`. Nothing else in either log came
within thirty characters of the limit.

**The fix is a split and I let it be nothing more.** `WITELIG` keeps policy,
origin, threshold, the three latch states and the two timestamps; `WITELIG2`
carries the two pre-eligibility counts and the contract zero. Two
`ringlog_printf` records, unique tags, every field name unchanged, no buffer
enlarged, `ringlog.c` untouched, both emitted after the probe returns and after
`WITQUAL`. Comments aside, the `main.c` diff is four lines.

**One comment was wrong and is now honest.** It said the literal
`qual_streak_at_eligible=0` was printed "so a future edit that breaks the
contract shows up in the record". A literal reads nothing; it cannot detect a
broken reset. What detects that is EL-B and EL-F in the C suite and the exact
counter derivations of runs 9 and 10. The comment now says exactly that.

**The guard is the part that outlives this fix.** `test_witelig_len.py` parses
both format strings from the source and renders every conversion at the
maximum width of its C type on powerpc-eabi — `%lu` 10, `%d` 11, `%llu` 20,
`%llx` 16 — and requires both records ≤ 248. WITELIG comes to 205, WITELIG2
to 113, and the reassembled `stream-0010` record to 310, which is how the guard
proves it can fail. It also pins both tags once, all eleven fields, and that
neither record sits inside the capture path.

**Proof it is reporting-only.** `src/`, `tools/`, `stimulus/` untouched;
`gbp_vwitness.*` byte-identical to what `stream-0010` compiled; 12 191 witness
checks unchanged; the ISR one-shot identical to GBP-VIDEO-001 with
`video-audit` run before `stream-audit`; ELF network symbols 0. The binary
differs from `stream-0010` by `.text +64 B` and `.rodata +8 B` and by its
identity.

**Artifact.** Checkpoint A `97c78c2`; `stream-0011`, 495 104 B,
`df2873ee…3e25`, built twice from scratch and byte-identical by SHA-256 and
`cmp`, Swiss identical, no `-dirty`, identity read back from the binary.
980 host tests, nine audits at 0 findings, Dolphin PASS in both profiles.

**Status, in the repository's words: FIXED IN SOFTWARE / PHYSICAL VALIDATION
PENDING.** Runs 9 and 10 stay what they were — `stream-0010` evidence with
`truncated=1` and the counter derivation — and their fixtures were not touched.

**Next, pre-registered and not run:** `GBP-VIDEO-006` / RUN 11 on run 10's
topology (BBA present, Ethernet disconnected, same indexed-0003), whose primary
new gate is `truncated=0` with `WITELIG` and `WITELIG2` both complete and the
zero present directly, plus every established regression gate. Run-11 names
reserved. Networking does not start.

---

## 2026-09-20 — RUN 11 ingested: the two lines arrived whole; GBP-VID-033 is physically validated

**Goal.** Ingest the pre-registered `GBP-VIDEO-006` / RUN 11 (GitHub Issue #2,
the first checkpoint coordinated through an Issue), which the orchestrator had
already classified PASS, and persist it: raw archive, fixtures, a regression
test, the research record. Executor role; no runtime, analyzer, format, Policy
A, witness, Phase 11 or remote change; no networking. The Gitea→GitHub
workflow migration is the next, separate checkpoint and was not started.

**Archive first, then hash, then read.** The console's three generated names
went to the reserved `…stream-0011-run11…` names with `cp --update=none` and
`cmp` before anything else; runs 1–10 untouched. Hashes recomputed here —
`c1987d2f…` (86 338 B), `9b62415b…` (8 946 060 B), `04feeca9…` (401 956 B) —
and only then compared with the orchestrator's: all three match. The artifact
on disk, in the Swiss copy and in the log header is `stream-0011 @ 97c78c2`,
`df2873ee…3e25`; the stimulus is run 10's; `tools/`, `src/`, `stimulus/` are
byte-identical to `fbaea00`.

**The primary gate, read straight off the log.** `lines=651 dropped=0
truncated=0`. One `WITELIG` (167 characters), one `WITELIG2` (98), consecutive,
eleven contract fields between them, `qual_streak_at_eligible=0` present with
no derivation. The longest line in the log is now `STARTUPT` at 218, the
runner-up of runs 9 and 10. The counter cross-check the pre-registration asked
for still agrees, and the counters equal run 10's, so the frozen replay stands.

**Everything else, reproduced, not copied.** Frozen `vindex.py`:
`OBSERVED_CONTIGUOUS`, intact 2048 / INVALID 0, 73..2120, 2046 decisive.
Independent decode: 81 920/81 920 strips, 2047 deltas of +1, STATUS 0x18,
FAULT 0. Transport clean, 254 864 everywhere. OGBPDISP2 four CRCs verified;
join 2047 `SELECTED_NEW` plus the capture edge; interior 0; reorder 0; 50/128
deferred in the join, depth 1; frozen latency p99 0.486790 ms, max 1.000914 ms;
seven display repeats for the sixth run running, recorded and not gated.
Startup NORMAL, first hand-off 165.158691 ms, +177 ticks from run 10, recorded
without a tolerance. `GBP-VIDEO-006 / RUN 11: PASS`, exactly as pre-registered.

**What it means, in one sentence.** The GBP-VID-033 reporting repair is
physically validated for this controlled run, with no detected regression.
Not networking, not Ethernet, not BBA initialisation, not Phase 11, not a
media double check, which stays PENDING for runs 9–11.

**Fixtures and test.** The OGBPDISP2 byte-identical, the content-blind qual
projection naming its raw witness, and the structural projection carrying the
declaration as a declaration, the names, the hashes, the header, both records
with their widths, the direct zero and its cross-check, the run-10 comparison
and the 2048 records. `test_disp_run11.py`: 20 tests, the run-9/run-10 gates
reused plus the reporting gate; host suite 1000 passed. Run-9 and run-10
fixtures untouched; run 10 keeps its `truncated=1`.

**Next.** The orchestrator validates these commits and opens the workflow
migration checkpoint (canonical remote, Issues, Milestones, Project, Roadmap
governance). No physical run is pending. Networking does not start.

---

## 2026-09-20 — Issue #5: the three carried items are closed, and the stream has one way to succeed

**Goal.** The first functional checkpoint run through a GitHub Issue: close
F3, F8 and F5 — carried in the handoff for four rounds so that runs 9, 10 and
11 stayed a causal comparison — now that run 11 has validated `stream-0011`.
Executor role; audit infrastructure and one stream configuration only; no
hardware, no evidence ID, no presentation, pixel-perfect, scanout, networking,
BBA or Ethernet work.

**F3 was a build-graph lie, not a tooling one.** Every `<x>-audit` disassembled
whatever objects were in `build/` and three of them compared against files only
`video-audit` wrote. The fix is to say what an audit consumes: the ELF depends on
the sources, the listings on the ELF, the reports on the listings, and the
comparing audits on the GBP-VIDEO-001 reference — which the video probe's own
rules now produce on demand. `.DELETE_ON_ERROR` so a failed audit cannot leave a
report behind. The demonstration I wanted was the hostile one: `build/poc`
recreated from scratch, no reference file anywhere, `make stream-audit` alone —
it built the reference and reported identical. The dry-run tests use `-W` and
`-o` against the real Makefile, so they answer without a container.

**F8 needed real objects, so it got them.** The auditor read `objdump -dr`,
which is the text; a function pointer to `fopen` in a data table produced a
`.sdata` relocation nobody read. `tools/audit_listings.sh` now writes `objdump
-r` beside every disassembly, and the auditor feeds the non-text sections to
every forbidden check with a `data <section>` origin the report keeps apart
from `from <function>`; call-site contracts still count branches only. The
negative controls are three objects compiled with the project compiler, kept
as listings with the command that made them: the data-only reference has no
`fopen` at all in `-dr` — that is the blind spot, in the file — and two findings
in `-r`; the call stays caught; the address-taken object keeps its 3 + 2 count.
Then the same mutation live in `gbp_vwitness.c`: rebuilt by dependency, two
findings naming `.sdata.f8_mutation_table`, report deleted on error, restored by
copy, clean again. Nine profiles through the new model: 0 findings, and no
external data reference anywhere in the tree — the hand inspection of
§V5.52.13, now a machine check for every build.

**F5 was a decision the comment kept postponing.** The 30 s capture target was
"PROVISIONAL", a "DESIGN DECISION REQUIRED", and it armed the generic vstate
success beside the witness target — unreachable under OGBPIDX1, but armed. The
decision: time does not end this experiment, only the target does. Two named
constants in the header (`DISABLED_S 0`, `DISABLED_TICKS UINT64_MAX`) and an
inline helper applied after the timebase pass; the generic probe and the other
POCs' defaults untouched; the log says `time_target=disabled`. The C scenario
that used to stop nominal_negative after six counted frames now runs to the
safety cap with the target disabled and `target_s=0` in the log.

**Artifact.** `stream-0012 @ c465f5c`, 495 168 B, `4495c836…7e73`, Swiss
byte-identical, Dolphin PASS, `.rodata` +48 B and `.bss` +16 B over
`stream-0011`. **NOT PHYSICALLY EXECUTED; no run pre-registered.**
`stream-0011 @ 97c78c2` keeps its physical status.

**Validation.** 1027 host tests; 22 C suites at 0 failures; nine audit
profiles at 0 findings; two from-scratch builds at c465f5c (rm -rf build/poc; GIT_COMMIT=c465f5c GIT_DIRTY= make build), byte-identical by sha256 and cmp.

**Next.** Nothing is carried to the next functional checkpoint. The
Orchestrator opens the next Phase-4 experiment as a GitHub Issue; if it is
physical, `stream-0012` is the candidate and the pre-registration comes first.

---

## 2026-09-20 — Issue #6: scanout and full-frame fidelity, designed as two claims

**Goal.** The ROADMAP names two Phase-4 facts still unestablished — scanout of
any frame, and pixel fidelity beyond the witness strip — and the two are easy
to blur into "the picture looks right". This checkpoint designs how to measure
them as separate claims, and keeps both away from presentation, scaling and
pixel-perfect policy (GBP-VID-032). Research/design only: nothing
implemented, nothing run, no evidence ID, no reserved run name.

**Two experiments, one run.** `GBP-VIDEO-007` (scanout) is decided by a literal
operator observation bound to hand-over and VI-latch records; `GBP-VIDEO-008`
(fidelity) by an offline byte comparison of preserved raw and texture against
an oracle. The dependent variables are disjoint, the sampling for B is
content-blind and the glyph for A is part of B's oracle, so one run may carry
both — with two gate sets, two verdicts, and the rule that neither promotes the
other. Five claims are named (A acquired, B converted, C handed, D scanned out,
E presented) and a result for one letter may not promote another.

**What is honest about scanout.** `VIDEO_GetCurrentFramebuffer()` is libogc2's
own bookkeeping (`currentFb = nextFb` in its retrace handler), not a readback;
retrace counters and OGBPDISP2 are CLAIM-C evidence. The design adds a VI-latch
record with the framebuffer-base registers read back, and still calls it
software. The physical claim comes from the operator seeing a large digit the
cartridge paints for 40 frames every 480 — the runtime synthesises no pixels,
so a digit on the screen came through the source stream — bound to the SET of
40 frames, never to one, because no declared equipment can do better. What a
capture device would add, and which claims are impossible without one, is
written down; the operator's television and cable are an undeclared dependency,
recorded rather than assumed.

**What is honest about fidelity.** `indexed-0003` was not reused: outside the
strips its rows 0/2 are identical, its ramp repeats every 64 px, its bar has 31
phases for 40 blocks. The proposed `coord-0001` keeps OGBPIDX1's witness bytes
identical — so `vindex.py`, the eligibility gate and every regression gate
apply unchanged — and fills the rest with `y*183 + (x-56)`: injective, bit 15
clear, and a host test now proves that every row or column shift, an axis
swap, any 4x4 tile permutation and any block displacement changes at least one
pixel. The dependent variable is the consumed word of all 38 400 pixels; bytes
0/2 and bit 15 are preserved and reported, never corrected, never in the
verdict. The claim stops at source → texture, and the section says why.

**Formats.** OGBPIDXCAP1 and OGBPDISP2 cannot hold a full-frame sample or a
latch instant, so two new names (`OGBPFULL1`, `OGBPVI1`) rather than a silent
extension; the sample copy is consumer work in bounded pump slices, never in
the service path; Policy A and the two XFBs are untouched.

**Left open, deliberately:** display/cable declaration, whether an XFB-region
CRC can be sliced without frame-sized work, K and the spacing against memory,
glyph geometry against the VBlank budget (the ROM's own FAULT latch decides),
which TEST_ID the build embeds, photographs, and one run versus two. Names are
proposed and verified unused; none is frozen and none is reserved.

**Next.** The Orchestrator validates §V6. Then an implementation Issue, then a
pre-registration with exact identities. No physical run until then.

## 2026-09-20 — Issue #7: coord-0001, the full-frame samples and the VI latch trace — built, tested, not run

**Goal.** Implement the §V6 design (Issue #6) as software, with frozen
identities, and nothing more: no physical run, no run name reserved, no
evidence ID. The Issue fixed the open decisions of §V6.17 in advance — K = 8
content-blind samples every 256 eligible frames, no XFB-region CRC, the glyph
at 48×80 / P 480 / W 40, the embedded TEST_ID stays `GBP-VIDEO-004`,
photograph optional, display / cable not invented.

**Changes, in four commits.** `99496a6` the stimulus `coord-0001`
(OGBPCOORD1: OGBPIDX1's FLAG / STRIP-L / GUARD-A byte-identical, then the
injective field `y*183 + (x-56)`, a guard at 239, no STRIP-R, no bar; the
seven-segment digit and six counter squares for 40 frames every 480; a
division-free schedule; prepare in the visible period, publish in VBlank by
DMA; erase tables in EWRAM `.sbss` so the ROM is 3 496 B) with `tools/icoord.py`
as its model and a host harness that compiles the ROM's own `main.c` and
proves word parity; `2c7ff0e` the two pure modules and their serializers —
`gbp_vfull` (the sample store: content-blind grid, one block per slice, a
generation or slot reuse refuses the sample) → OGBPFULL1 v1, and `gbp_vvi`
(hand-over → latch, supersede, overflow counted) → OGBPVI1 v1 — with
`tools/vfull.py` (three conversions compared, the frozen strip decoder, a
mismatch classifier with ten classes, bytes 0/2 and bit 15 reported apart) and
`tools/vvi.py` (register consistency, the R / H / L join, a report that says
it classifies nothing); `7d7a6d8` the stream integration as `stream-0013`, with
the audit profile pinning every new call site by function and every new
object's outward edges; then this documentation.

**What the built program says about memory.** `ENVFULL` on the final DOL:
2 080 768 B of new static stores declared, `arena1_free=1658880` after them
and the runtime allocations, against run 11's 3 751 936 — the arithmetic
closes to 12 288 B of bookkeeping. K = 8 fits; the hardware run's own line
must repeat it.

**Tests executed.** Host suite 1096 passed; C suite every test 0 failures
(`test_gbp_vfull` 663 checks, `test_gbp_vvi` 419); nine audits 0 findings with
the ISR comparison identical; twelve POCs from scratch with 0 warnings;
`stream-0013` twice from scratch byte-identical (506 496 B, `5391c3fe…dd79`),
Swiss parity; `coord-0001` twice from scratch byte-identical (`90343b64…0a1f`),
delivery re-derived (`a769cc11…994f`); Dolphin PASS on both profiles.

**What was decided rather than measured.** The XFB CRC is dropped, so
CLAIM-B ends at the converted texture; the VI latch reads four register
halves back and is still CLAIM-C. Where the implementation departs from the
§V6.8 sketch (64-byte VI records with four register halves, no CRC field in
the sample meta, ENVFULL instead of ENVSTORE) §V6.18.12 says so and the design
text is not rewritten. One pin moved: `test_vdisp` now expects the take clock
in a local (`t_take`) beside the unchanged key; and the design test's
"names unused anywhere" walk became "the design named them, no other id was
minted".

**Rejected / not done.** No RUN 12 name; no hardware; no classification; no
GBP-HW id. `stream-0012` is superseded as the candidate and keeps its
identity, never run.

**Next.** The Orchestrator validates §V6.18 against §V6 independently; the
operator declares display and cable; then a pre-registration Issue reserves
the run names and fixes the procedure against these exact identities. Until
then nothing about scanout or fidelity is known.

## 2026-09-20 — Issue #8: RUN 12 pre-registered for GBP-VIDEO-007 / GBP-VIDEO-008 — names reserved, topology declared, nothing run

**Goal.** Freeze the first physical run of the implemented §V6 experiments
BEFORE hardware, as a documentation-only checkpoint: identities, reserved raw
names, the operator-declared topology, the procedure, the shared admissibility
gates and the independent gates and verdicts of both experiments. No hardware,
no flashing, no booting, no classification, no evidence ID.

**What was persisted (HARDWARE_TESTS §V6.19).** RUN 12 is the next global run
(runs 1–11 are the highest referenced). The artifacts were verified on disk,
not rebuilt: `stream-0013` at `7d7a6d8` (506 496 B, `5391c3fe…dd79`, Swiss
byte-identical, embedded `gbp-video-stream-probe / stream-0013 / 7d7a6d8`,
TEST_ID `GBP-VIDEO-004`, no dirty string; `git diff 7d7a6d8..5c472ca` over
the runtime, tools, stimulus and unit tests is empty) and `coord-0001`
(canonical `90343b64…0a1f`, delivery `a769cc11…994f`, 3 496 B each, EZ-Flash
NOR / Mode B, re-flashed). The Operator declared the display chain for this
run — composite / RCA → a low-cost RCA-to-HDMI converter configured to 1080p
→ a custom display with a HYDIS HV150UX2 panel on an M.NT68676.2A controller
(a custom iMac G3 modification) — recorded as topology only: the 1080p is the
converter's output, and the chain supports no pixel-perfect, scaling, latency
or native-1080p claim. The console side stays as runs 10–11: same GameCube,
same GBP, BBA PRESENT, Ethernet DISCONNECTED, no network code. The future
Morph 2K paths (S-Video primary, Bitfunx composite alternate, Samsung Q80T)
are explicitly outside RUN 12. Five raw names are reserved and taken even if
the run aborts (`captures/local/GBP-VIDEO-004_stream-0013-run12.log`,
`-idxcap.bin`, `-disp.bin`, `-full.bin`, `-vi.bin`); the rename-before-copy /
`cp --update=none` rule is mandatory; a photograph is optional and never
frame-accurate by itself.

**Gates, prospective.** The inherited gates of runs 9–11, none narrowed:
identity and log integrity (`dropped=0`, `truncated=0`, no storage fault),
the 5000-ms not-before policy and the 64-close qualification, frozen
`tools/vindex.py` → `OBSERVED_CONTIGUOUS` / 2048 intact / 0 invalid /
`STATUS.FAULT = 0` with no FRAME_ID start value required, transport zero
errors and balanced accounting, NORMAL startup with the first hand-off under
400 ms, Policy A over the exact join (0 interior drops, 0 reorder, depth ≤ 1,
frozen p99 ≤ 1.0 ms / max ≤ 2.5 ms), and strict parse of all four sidecars.
GBP-VIDEO-008: the content-blind `origin + 256·i` rule, eight COMPLETE
samples, colour15 equal to `icoord.expected_video` on 38 400 words, texture
equal to the Python and the C conversion and to the tiled oracle; bytes 0/2
and bit 15 reported apart; the oracle is never retuned after a failure.
GBP-VIDEO-007: `R_k`, `H_k`, `L_k` from the three sidecars through the frozen
`tools/vvi.py`, the Operator's literal report beside them; PASS binds a digit
to an appearance set, never to one frame; which k fall in the window is
decided by the data. The two verdicts never consult each other's evidence.

**Changes.** HARDWARE_TESTS: the §V6 heading and head carry the
pre-registration status; §V6.18 keeps its text with a one-line note that the
reservation point is superseded; new §V6.19 with the twelve parts above and a
comparison table against run 11 with nothing pre-filled. HANDOFF: baseline,
scientific state, artifact rows, blocker, next safe action, the reserved names
in the "protect the raw record" paragraph, three do-not-assume bullets.
Tests: the design test's "no run name" ban now covers §V6.1–§V6.18 only, and
`tests/host/test_run12_prereg.py` pins the pre-registration (identities copied
exactly, the five names exactly once, prospective gates, independent verdicts,
topology recorded and not claimed, Morph 2K outside, no evidence ID).

**Not done, by contract.** No hardware execution, no flash, no boot, no
runtime / stimulus / analyzer / format change, no ingestion, no PASS / FAIL,
no network, no presentation work. The Orchestrator validates §V6.19
independently and only then opens the Hardware Issue that moves RUN 12 to the
Operator.

## 2026-09-20 — RUN 12 ingested: the gate the run was judged by failed on two duplicate FRAME_IDs; everything downstream of it held

**Goal.** Ingest RUN 12 (GBP-VIDEO-007 / GBP-VIDEO-008, `stream-0013` +
`coord-0001`, Hardware Issue #9) under the ingestion contract of GitHub Issue
#10, which persists the Orchestrator's classification against the
prospectively frozen §V6.19 gates: **GBP-VIDEO-007 INCONCLUSIVE, GBP-VIDEO-008
INCONCLUSIVE.** Executor role; no rerun, no fix to `coord-0001`, `tools/vvi.py`,
the runtime, the analyzers, the formats or the gates; no RUN 13; Issue #9 left
open for the Orchestrator.

**Archive first, then hash, then read.** The five console-generated files
were located by hash in `logs/`, copied FIRST to the reserved
`…stream-0013-run12…` names with `cp --update=none` and `cmp`, and hashed
before any interpretation: log 89 514 B `0b64b677…`, idxcap 8 946 060 B
`fe1c1c0a…`, disp 401 356 B `91c2f805…`, full 1 844 492 B `fb09a777…`, vi
152 396 B `d301e96e…` — all five exactly the identities the Issue states.
`stream-0013 @ 7d7a6d8` on disk, in the Swiss copy and in the log header; the
delivery image `a769cc11…` re-flashed; `tools/` clean, unchanged since
`7d7a6d8`.

**The one gate that failed, and it is the shared one.** Frozen `vindex.py`:
2048 records, all 40 blocks, 81 920/81 920 valid strips, INVALID 0, FAULT 0,
FRAME_ID 74..2119 — and two `OBSERVED_DUPLICATE_ID` transitions among 2046:
`frame_index 761 → 762` carrying 479 twice (STATUS 0x36) and `2202 → 2203`
carrying 1919 twice (STATUS 0x26). `OBSERVED_DISCONTINUITY`. §V6.19.7 required
`OBSERVED_CONTIGUOUS`, so RUN 12 is inadmissible for both experiments and both
verdicts are INCONCLUSIVE. Both duplicated ids are the frame before an
appearance start (480, 1920), while the R_2 and R_3 entries are +1; that is
written down as an observation and no mechanism is inferred (GBP-VID-034,
OPEN). Runs 4–11 with `indexed-0003` never showed a duplicate — context, not a
cause.

**What held, reproduced independently.** Transport clean (254 858 everywhere,
zero errors), NORMAL startup with the first hand-off at 165.152173 ms, the
not-before gate at 5.000154 s, the window at 356 with the direct zero, log
`lines=674 dropped=0 truncated=0`; OGBPDISP2 four CRCs verified, join 2047
`SELECTED_NEW` + the capture edge, interior 0, reorder 0, 36/79 deferred,
depth 1, frozen p99 0.308642 ms / max 1.004667 ms, seven display repeats for
the seventh run running. `ENVFULL arena1_free=1658880` on hardware equals the
Dolphin figure. **OGBPFULL1**, frozen `vfull.py` with the host-built C
conversion: K = 8, origin 356, 8/8 COMPLETE, and in every sample all 38 400
consumed words equal the injective oracle and the texture equals the Python,
the C and the tiled conversion; bit 15 once at (0, 0); bytes 0/2 reported.
**Positive subordinate evidence: all eight prospectively sampled frames
satisfy CLAIM-A/CLAIM-B's full-frame source→texture dependent-variable checks.
The formal GBP-VIDEO-008 experiment verdict is nevertheless INCONCLUSIVE
because RUN 12 failed the shared source-window admissibility gate.**

**The VI chain, and a defect in the frozen reader.** OGBPVI1 strict: 2377
handed, 2370 latched, 6 superseded, every latch on the retrace after its
hand-over; R_1..R_4 each 40 retained and 40 handed. Frozen `vvi.py`
`regs_consistent()`: 0/2370, so frozen L_k = 0 — an independent reason
GBP-VIDEO-007 cannot pass. The raw cross-check, without touching the tool:
the function masks `phys` to 24 bits and then shifts the reconstructed base
by 5 for the flag, so an address carried with the flag can never match;
reconstructed against the unmasked address, 2370/2370 top and 2370/2370
bottom (+1280). GBP-VID-035: a software analyzer defect discovered by RUN 12,
not evidence that the readbacks disagreed; it does not change RUN 12's frozen
output or verdict, and it is not fixed here. `test_run12.py` pins the
divergence as a known finding until a functional checkpoint repairs the tool.

**The operator, beside the chain.** Digits 1, 2, 3, 4, in order, ≈ 7 s apart,
≈ 2 s each, nothing missing, repeated, unexpected or anomalous, under the
declared composite → RCA-to-HDMI converter → HYDIS HV150UX2 chain (GBP-HW-254).
Coherent with four retained-and-handed appearance sets; classifying nothing
under the frozen gates.

**Fixtures and tests.** Byte-identical OGBPDISP2, OGBPFULL1 and OGBPVI1
fixtures, the content-blind qual projection naming the raw witness, and a
structural fixture (2048 per-record decodes, every identity, the declarations
as declarations, the literal report, the frozen tools' results, the raw VI
cross-check, both verdicts, both findings, the run-11 comparison) composed by
a generator that asserted every figure of the Issue before writing.
`tests/host/test_run12.py`: 27 tests, the inherited gates reused, the source
gate pinned as it failed, vfull 8/8 recomputed from the versioned file and
recorded as subordinate, the frozen L_k = 0, GBP-VID-035 pinned as a
divergence. Runs 9–11 fixtures and tests untouched. Evidence GBP-HW-250…255,
GBP-VID-034, GBP-VID-035; HARDWARE_TESTS §V6.20; captures/README rows.

**Next.** The Orchestrator validates the persisted evidence and closes Issue
#9. Then, in their order: a research checkpoint on GBP-VID-034, a functional
checkpoint repairing `tools/vvi.py` (GBP-VID-035), and only then whether a
further run is designed. No RUN 13 is pre-registered.

## 2026-09-20 — Issue #11: the VI analyzer compares in the right address domain; RUN 12 replayed afterwards, nothing reclassified

**Goal.** Repair GBP-VID-035 — the offline OGBPVI1 analyzer compared a
full-domain register reconstruction against a 24-bit-masked address — and
replay the versioned RUN 12 OGBPVI1 with the corrected tool, as post-run
software analysis only. Functional checkpoint; no hardware, no RUN 13, no
change to the runtime, the formats, the fixtures, `coord-0001`, `vindex.py`,
`vfull.py`, `icoord.py`, Policy A or the source-window gates; GBP-VID-034
untouched.

**The rule, from source, before editing.** libogc2 `ca03fb7`,
`libogc/video.c`: `__calcFbbs` (2446–2464) converts both bases with
`MEM_VIRTUAL_TO_PHYSICAL` and adds one line (1280 B for 640 px) for the
bottom; `__setFbbRegs` (2466–2503) sets the flag unless EVERY base is below
`0x01000000`, then stores every base `>> 5`, and writes reg 14 (flag, xof,
top high byte), reg 15, reg 18 (bottom high byte, no flag), reg 19. Dolphin
names the flag POFF, "fb address is (address>>5)", and ties the bottom's to
the top's. The probe records `MEM_VIRTUAL_TO_PHYSICAL(xfb_stream_buf[xfb])`.
RUN 12's buffers sit above 16 MiB in the 24 MiB MEM1, so the hardware
registers carried the page-offset form — flag 1 in all 2370 latched records.
The frozen tool's docstring assumed "MEM1 ⇒ flag 0" and masked `phys` to 24
bits; hence 0/2370 and an alias between bases differing above bit 23.

**The STOP, and the decision.** The candidate fix, run in a scratch copy
first, gave top 2370/2370 and bottom 2370/2370 but L_3 = 38: two R_3
hand-overs (frame_index 1754 → FRAME_ID 1471, 1757 → 1474) are SUPERSEDED in
the raw file — the next hand-over came one retrace later, before the pump
observed them current — so they have no latch record. The Issue's 40/40/40/40
expectation was not met, so the checkpoint stopped and reported without
weakening anything. The Orchestrator withdrew the over-constraint: L_k is
defined over LATCHED, register-consistent records; the prospective §V6.19.9
gate asked for at least one per appearance; the corrected expectation is
40/40/38/40. SUPERSEDED is instrumentation semantics only — nothing is
inferred about whether either frame was physically scanned out.

**The repair.** One function: `regs_consistent()` compares in the full
physical domain (no mask), takes an explicit `bytes_per_line` (1280), and its
docstring states the libogc2 rule. `tests/host/test_vvi.py::TheAddressDomain`:
flag clear / ordinary; flag set / shifted reproducing RUN 12's exact halves;
a wrong TFBL fails in both forms; bottom plausibility not vacuous and
stride-explicit; no alias `0x0043e440` ↔ `0x0143e440` either way; misaligned
base is a mismatch; libogc2's flag rule versus the 16 MiB assumption;
unlatched → no readback. `tests/host/test_run12.py` keeps the frozen-at-run
0/2370 and L_k = 0 as fixture metadata (history) and asserts the corrected
tool: 2370/2370, 2370/2370, every readback exactly libogc2's encoding of the
handed address, L = 40/40/38/40 with the two SUPERSEDED members identified.

**What did not change.** GBP-VIDEO-007 INCONCLUSIVE, GBP-VIDEO-008
INCONCLUSIVE (the source gate failed first); GBP-HW-250…255; §V6.19 and
§V6.20 as written (a pointer to §V6.21 only); the fixtures byte for byte;
GBP-VID-034 OPEN. GBP-VID-035 → REPAIRED (software).

**Next.** The Orchestrator validates the persisted evidence and closes Issue
#9; then a research checkpoint on GBP-VID-034; only then whether a further run
is designed. No RUN 13 is pre-registered.

## 2026-09-20 — Issue #12: why 479 and 1919 came twice — the entry PREPARE of digits 1 and 4 is longer than a frame

**Goal.** Root cause of GBP-VID-034 (the two duplicate FRAME_ID transitions
of RUN 12) from the frozen artifacts alone: the exact `coord-0001` source and
generated ARM code, the GBA publication and VBlank semantics, the STATUS/FAULT
coverage, exact timing paths and all four entry and exit boundaries. Research
only; nothing changed in the stimulus, the runtime, the analyzers, the
formats or the gates; no hardware, no RUN 13.

**What the code does, exactly.** VRAM is written only by `paint_background`
at boot and by `publish_frame` after the two-loop VCOUNT wait; PREPARE for
frame N runs after PUBLISH of N−1. If PREPARE(N) returns inside VBlank v+1,
the wait skips that VBlank and N−1 is captured twice — N−1, N−1, N — and the
latch cannot see it, because `vc0` is read after the wait loops and the
timer brackets PUBLISH only (RQ1, RQ2, from the disassembly of the frozen
build). The digit loop in PREPARE reloads `sc->digit` and reads
`seg_of_digit[digit]` from ROM for every one of the 3 840 glyph pixels (the
compiler did not hoist the byte load), evaluates up to seven tests, and for
unlit pixels reads and writes EWRAM; digits 1 and 4 leave 3 200 and 2 592
pixels unlit, digits 2 and 3 leave 2 240 (RQ3).

**The model.** `tools/coordtime.py`, a minimal ARM7TDMI interpreter that
runs the exact IWRAM image with GBATEK bus costs (IWRAM 1, EWRAM 3/3/6, ROM at
the WAITCNT the ROM writes, VRAM 1/1/2, DMA 2N+2(n−1)S+2I). It reproduces the
three PUBLISH end lines RUN 12 measured — VMARGIN 54, 39 and the 38/39
knife-edge — before it is asked anything about PREPARE. The entry budget is
263 839 … 263 953 cycles (a 114-cycle declared band, the ROM prefetch on the
loop tail). Entry PREPARE: digit 1 287 787, digit 4 287 179 (over by 23 k
cycles, ≈ 19 lines — 17.15 ms, longer than an AGB frame); digit 2 261 723,
digit 3 260 043 (under by 2.1 k / 3.8 k). Exits, steady and ordinary frames
are below a third of the budget. The four RUN 12 outcomes — M--M — come out
with no parameter fitted to them (RQ4, RQ5). The boundary table from the
versioned fixture shows the two duplicates exactly before 480 and 1920, none
before 960 and 1440, none at any exit, FAULT clear, and the only two STATUS
transitions are the two PUBLISH classes the model costs (RQ6). Same mechanism
class as GBP-HW-165: identical wait loops, PREPARE now in IWRAM and over the
line on two frame classes instead of every frame (RQ7).

**The verdict, and the margin.** GBP-VID-034 → MECHANISM RESOLVED (software
analysis, corroborated by the run's pattern). The gate's seven items are met;
item 5 is met with the margin stated: the non-duplicates at R_2 / R_3 are
under the budget by 0.8 % / 1.5 %, and the model's CPU-side residual has no
hardware calibration point of its own (its memory side is pinned to ≈ 0.2 %
by the DMA calibration; one extra cycle per ROM byte read would have
duplicated every entry, which the run rules out). Falsifiable predictions for
a future run retaining k ≥ 5: digits 6–9 duplicate, digit 5 does not. A
design-only note records the smallest source-side instrumentation
(`OGBPCOORD2`, VCOUNT at PREPARE completion plus an in-VBlank latch) and the
obvious source-side remedy (hoist the ROM byte, build the table one frame
early) for a future stimulus — neither implemented.

**Tests.** `tests/host/test_coordtime.py`: the interpreter's rules on
hand-assembled sequences, the frozen ROM fixture identity, the three-point
PUBLISH calibration, the budget band, the class costs, the M--M verdict, the
access counts that order the digits, the sensitivity at the calibrated terms,
and the RUN 12 fixture's duplicates at exactly the predicted entries.

**Next.** The Orchestrator validates §V6.22; the RUN 12 verdicts stand; a
future stimulus checkpoint may take the design note; no run is pre-registered.

## 2026-09-20 — Issue #13: coord-0002 — the same picture, with the digit tables built before the loop exists

**Goal.** A new stimulus identity that publishes exactly OGBPCOORD1 and
cannot repeat GBP-VID-034: the entry-frame PREPARE must build nothing.
Software only; coord-0001 stays the RUN 12 artifact byte for byte; the
GameCube runtime, the frozen analyzers, the formats, Policy A and the gates
are untouched; nothing flashed, nothing booted, no RUN 13.

**What was built.** `stimulus/agb-coord2/` (commit `74f9f4f`): coord-0001's
source with one structural change — `glyph_tables[10][80][50]` (80 000 B,
EWRAM `.sbss`, NOLOAD) is filled once by `glyph_tables_init()` at boot, after
the erase tables and before `paint_background()` and `REG_DISPCNT`; the
entry PREPARE does `glyph_sel = glyph_tables[sc->digit]` and nothing else
for the digit; PUBLISH DMAs `glyph_sel[r]` from EWRAM over the same span.
Header title OPENGBPCOOR2 / code CGB2 so the cartridge menu tells the two
images apart. Canonical `agb-coord2.gba` 3 620 B, `319dacb7…093f`, built twice
from scratch byte-identical (+124 B of ROM over coord-0001; the LOAD segment
for EWRAM carries 0 file bytes); delivery image `276ad987…6f700`, 3 620 B,
logo area only, not flashed. A copy of the canonical is versioned so the
proof recomputes from a clone.

**The proof, on the exact image.** `tools/coordtime.py` now carries
immutable profiles; coord-0001's numbers are the numbers of §V6.22 (its 21
pins untouched; one trailing row added, digit 0 at 280 683 — over, computed
not assumed). coord-0002's profile is read off its disassembly (prepare
0x03000000 / 0x348 B, publish 0x03000348, tail at 0x080006a4 with the
schedule at sp+16, first poll at 0x08000680). PUBLISH: 16 799 / 34 974 /
17 522 / 35 657 cycles — VMARGIN 54 / 39 / 53 / 39, the same classes RUN 12
read, the entry +320 cycles for a per-row pointer load, DMA cycles identical.
Budget 263 835 .. 263 951. PREPARE: ordinary 77 905, steady 86 827 / 86 443,
exit 77 914, and EVERY entry digit 0..9 at 86 972 — 176 863 cycles under the
conservative minimum (the Issue's gate: 50 000), zero GamePak ROM reads and
zero EWRAM writes in every class, nothing in the band, the sensitivity sweep
`----` in every cell. The real RUN 12 entry tuples (480/0x36, 960/0x27,
1440/0x26, 1920/0x26) and six alternates all cost 86 972; coord-0001's four
digits are equally payload-invariant. Boot precompute 4.66–7.48 M cycles
(278–446 ms), before the display is enabled.

**Parity, three ways.** `tests/host/test_agb_coord2.py`: the ROM's own
`main.c` on the host against the unchanged `tools/icoord.py`, word for word
over 240 × 160, for ordinary frames, every digit entry, steady frames as the
squares change, every exit with the field restored, the boundaries, the
witness with CRC and STATUS, bit 15; coord-0001 and coord-0002 driven
identically publish the same full frame in 29 cases; a static audit pins
the repair and coord-0001's source hash.

**Tests.** 16 + 21 + 21 new pins; the parity, timing, historical replay,
prior stimulus, RUN 12 fixture, design and pre-registration suites; the full
host suite.

**Not done, by contract.** No hardware, no flash, no RUN 13, no
pre-registration, no runtime rebuild, no verdict change. A separate research
pre-registration decides whether the next physical run uses coord-0002 with
the unchanged `stream-0013`.

## 2026-09-20 — Issue #14: RUN 13 pre-registered — the same two experiments, coord-0002, the same stream-0013; nothing run

**Goal.** Freeze the next physical run before hardware: GBP-VIDEO-007 and
GBP-VIDEO-008 with the timing-safe `coord-0002` (§V6.23) on the unchanged
`stream-0013`, as §V6.24. Pre-registration only: no hardware, no flash, no
boot, no rebuild, no re-derivation, no classification, no evidence ID; the
Hardware Issue is the Orchestrator's.

**Verified on disk, not rebuilt.** The RUN 12 DOL (506 496 B,
`5391c3fe…dd79`, embedded `stream-0013 7d7a6d8`, TEST_ID `GBP-VIDEO-004`,
zero "dirty" strings, the Swiss `12-stream` copy byte-identical); the
coord-0002 canonical (3 620 B, `319dacb7…093f`, equal to its versioned
fixture) and delivery (3 620 B, `276ad987…6f700`, payload from 0x0C0
identical to the canonical, 154 bytes differing only in the logo area);
coord-0001 untouched and named as the thing not to substitute; the
analyzers at their current accepted commits — `vvi.py` the corrected
implementation of `0ee8aac`, unchanged since. The optional run-numbered
Swiss copy (`13-stream`) was deliberately not created: the versioned layout
numbers builds, and a run is not a build; the pre-run gate is the hash.

**What §V6.24 freezes.** RUN 13 reserved, taken even if it aborts; one
session, two independent verdicts; RUN 12's topology held (same GameCube and
GBP, BBA present, Ethernet disconnected, composite → low-cost RCA-to-HDMI
converter at 1080p → HYDIS HV150UX2 / M.NT68676.2A, a declaration only;
Morph 2K and Samsung Q80T outside); five `…-run13…` archive names; the
pre-run identity gate; a fifteen-step procedure with no frame counting and
no stopwatch; the inherited admissibility gates with the source-window gate
— the one RUN 12 failed — named first and unchanged (`OBSERVED_CONTIGUOUS`,
2048 intact, INVALID 0, FAULT 0, no first FRAME_ID required); GBP-VIDEO-008
with the unchanged `vfull.py` and `icoord.py`; GBP-VIDEO-007 with the
corrected current `vvi.py`, SUPERSEDED kept as instrumentation semantics;
the non-claims; the analysis order and a comparison table against run 12
with nothing pre-filled, plus §V6.22's falsifiable expectation for
coord-0002 to be read off the data.

**Tests.** `tests/host/test_run13_prereg.py` pins the frozen identities,
the five names exactly once in §V6.24 and once in the handoff (the run12
names untouched), the prospective gates, the independent verdicts, the
corrected-vvi and SUPERSEDED wording, the topology boundaries, the fifteen
steps, and that no run13 archive exists; the RUN 12 pre-registration pin
allows §V6.24. Docs and tests only; no runtime, stimulus, analyzer, format,
fixture or evidence row changed.

**Next.** The Orchestrator validates §V6.24 and opens the Hardware Issue;
RUN 13 stays PRE-REGISTERED / NOT RUN until then.

## 2026-09-21 — Issue #16: RUN 13 ingested — the gate RUN 12 failed passed with coord-0002, and both experiments are PASS inside their boundaries

**Goal.** Ingest RUN 13 (GBP-VIDEO-007 / GBP-VIDEO-008, the unchanged
`stream-0013` + `coord-0002`, Hardware Issue #15) under the ingestion contract
of GitHub Issue #16, which persists the Orchestrator's classification against
the prospectively frozen §V6.24 gates: **GBP-VIDEO-007 = PASS (CLAIM-D only),
GBP-VIDEO-008 = PASS (CLAIM-A / CLAIM-B, the eight sampled frames only).**
Executor role; no rerun, no runtime, stimulus, analyzer, format or gate
change, no new GBP-VID finding, no new run pre-registered; Issue #15 left open
for the Orchestrator.

**Locate by hash, archive first, then read — and one collision.** The
Orchestrator had located the five console-generated files on the live SD card
and hashed them there. Between that check and this ingestion they were moved
into `logs/` under the same bare `stream-0013` names — not by this session —
which overwrote RUN 12's raw-drop copies there: the collision
`captures/README.md` warns about, for the second time. RUN 12 survives in its
run-12 archive (all five re-hashed, equal to GBP-HW-250) and in its versioned
fixtures. The RUN 13 files were identified by full SHA-256 in `logs/`, copied
FIRST to the reserved `…stream-0013-run13…` names with `cp --update=none` and
`cmp`, and hashed before any interpretation: log 87 200 B `4d86ef32…`, idxcap
8 946 060 B `dcbcfd3e…`, disp 401 396 B `c75e986a…`, full 1 844 492 B
`cb884e27…`, vi 152 396 B `2a772ae0…` — all five exactly the identities the
Issue froze. `stream-0013 @ 7d7a6d8` in the log header, the same bytes as RUN
12; the coord-0002 delivery image `276ad987…` flashed; `tools/` clean.

**The gate RUN 12 failed, passed.** Frozen `vindex.py`: 2048 records, all 40
blocks, 81 920/81 920 valid strips, INVALID 0, FAULT 0, FRAME_ID 52..2099 with
2048 distinct ids — **2046 of 2046 decisive transitions `OBSERVED_ID_CONTIGUOUS`,
`OBSERVED_CONTIGUOUS`.** The four entries that matter came +1 (479 → 480, 959 →
960, 1439 → 1440, 1919 → 1920); the digit-1 and digit-4 entries that
duplicated in RUN 12 did not duplicate here. That is §V6.22's falsifiable
expectation for coord-0002 read off the data — one run consistent with the
cycle model of §V6.23, not a calibration of it, and no new finding.

**Everything downstream held again, reproduced independently.** Transport
clean (254 862 everywhere, zero errors), NORMAL startup with the first
hand-off at 165.151852 ms (−13 ticks vs RUN 12, recorded), the not-before gate
at 5.000151 s, the window at 356 with the direct zero, `lines=658 dropped=0
truncated=0`; OGBPDISP2 four CRCs verified, join 2047 `SELECTED_NEW` + the
capture edge, interior 0, reorder 0, 37/81 deferred, depth 1, frozen p99
0.308543 ms / max 1.005012 ms, seven display repeats for the eighth run
running. **OGBPFULL1**, unchanged `vfull.py` with the host-built C conversion:
K = 8, origin 356, 8/8 COMPLETE, sampled FRAME_IDs 52, 308, …, 1844, and in
every sample all 38 400 consumed words equal the injective oracle and the
texture equals the Python, the C and the tiled conversion; bit 15 once at
(0, 0); bytes 0/2 reported. This time the run is admissible, so the formal
verdict is what the pre-registration said it would be: **GBP-VIDEO-008 =
PASS, for those eight frames.**

**The VI chain with the corrected reader, and the operator beside it.**
OGBPVI1 strict: 2377 handed, 2371 latched, 5 superseded, every latch on the
retrace after its hand-over; the corrected `vvi.py` (§V6.21, unchanged since
`0ee8aac`, used prospectively as §V6.24 pre-registered) reads 2371/2371 top
and 2371/2371 bottom and derives L = 40 / 40 / 39 / 40. The one R_3 member
not in L_3 (`frame_index 1754`, FRAME_ID 1450) is SUPERSEDED in the raw file —
instrumentation semantics, never evidence of non-scanout, and the rule never
asked for every frame. The operator saw 1, 2, 3, 4 in order, ≈ 8 s apart
(a human estimate, not timing evidence), nothing missing, repeated,
unexpected or anomalous, under the declared composite → RCA-to-HDMI converter
→ HYDIS HV150UX2 chain, confirmed after the return. The §V6.24.9 rule,
applied: **GBP-VIDEO-007 = PASS, CLAIM-D only** — a digit bound to a 40-frame
appearance set, never to one frame; nothing about pixels, presentation,
scaling or the converter.

**Fixtures and tests.** Byte-identical OGBPDISP2, OGBPFULL1 and OGBPVI1
fixtures, the content-blind qual projection naming the raw witness, and a
structural fixture (2048 per-record decodes, every identity, the receipt, the
declarations as declarations, the literal report, the tools' results, the
corrected register model, both verdicts with their boundaries, the RUN 12
comparison) composed by a generator that asserted every figure of the Issue
before writing. `tests/host/test_run13.py`: 29 tests, the inherited gates
reused, the source gate pinned as it passed with the four entries +1, vfull
8/8 recomputed from the versioned file and the formal verdict within its
boundary, the corrected 2371/2371 and L = 40/40/39/40 from latched records
only, the CLAIM-D wording, and the RUN 12 fixtures pinned untouched. Evidence
GBP-HW-256…260; HARDWARE_TESTS §V6.25; captures/README rows and the second
collision recorded. RUN 12 remains INCONCLUSIVE / INCONCLUSIVE; GBP-VID-034
and GBP-VID-035 remain history.

**Next.** The Orchestrator validates this ingestion and closes Hardware Issue
#15; the next Phase-4 design is theirs. No run is pre-registered.

## 2026-09-21 — Issue #17: Phase 4 assessed against its acceptance criterion — SATISFIED WITH NAMED RESIDUALS; the video path promoted with its ids

**Goal.** Assess Phase 4 against the criterion `docs/ROADMAP.md` wrote before
any of the evidence existed — "A real cartridge running on the physical GBP
produces stable, correct video through the open-source runtime" — term by
term, on existing evidence ids only, and promote into `docs/hardware/` and
`docs/protocol/` exactly what the `RESEARCH_METHOD.md` chain supports.
Documentation and assessment only: no code, no hardware, no run, no build, no
new id, no status promoted, no run re-judged; the Orchestrator's framing that
presentation / pixel-perfect is Phase 9 and not Phase 4 was verified against
the ROADMAP's Phase 9 section and the runtime's own comment before anything
was written.

**The assessment (`docs/research/PHASE4_ASSESSMENT.md`).** *Real cartridge:*
three retail runs — `stream-0003`, `stream-0004`, run 8 / GBP-VIDEO-005 —
with transport, NORMAL startup and Policy A clean on retail content
(GBP-HW-138…151, 224…226) and the picture observed by the operator
(GBP-HW-144, 152, 227); no OGBPIDX verdict and no oracle check exist on retail
content and none can. *Stable:* zero transport faults in every streaming run,
`OBSERVED_CONTIGUOUS` in every prospectively qualified window but RUN 12's
(explained by the stimulus, GBP-VID-034 RESOLVED), Policy A with zero interior
drops and bounded latency on eight runs, the same ~165 ms startup on eight
runs; the longest streaming observation with presentation is ≈ 44 s and the
slice margin is unmeasured. *Correct video:* geometry (GBP-HW-081),
composition (076, 077), colour (131, with §V3.19's intra-group limit),
full-frame fidelity on eight sampled frames (258) and scanout as CLAIM-D (260)
are FACT on controlled stimuli inside their boundaries; bytes 0/2 and bit 15's
origin stay UNKNOWN. *Through the open-source runtime:* every run executed a
DOL built from this repository with its identity recorded, the references used
statically only. **The asymmetry, argued and not assumed:** the measured
correctness rests on `indexed-0003` / `coord-0001` / `coord-0002` because an
oracle, a frame index and known digits are what a retail cartridge cannot
supply; the transfer to retail content is an inference about a content-blind
path, CORROBORATED by identical machine-side metrics and operator
observations, never FACT. The ROADMAP places cartridge validation in Phase 7,
so that gap is a named residual with an owner, not a block.

```text
PHASE 4 VERDICT: SATISFIED WITH NAMED RESIDUALS
```

Eleven residuals, each with an owner or "not scheduled": retail-content
measurement (Phase 7); presentation / scaling / GBP-VID-032 (Phase 9);
physical pixel equality and per-frame scanout accounting (not scheduled);
stability duration, breadth and the GB/GBC family (Phase 12, Phase 7); the
colour intra-group limit (not scheduled); U-GBP-029 / 034 / 030 / 033 (open
research residuals); rate conversion (Phase 9); audio and input (Phases 6 and
5); BBA / Ethernet (Phase 11); production UX (Phases 9, 12). No U-GBP was
closed: U-GBP-008, 014, 029, 030, 031, 033 and 034 were checked against the
conditions each set for itself and none is met.

**Promotion.** New `docs/protocol/VIDEO.md`: the block (size, geometry, pixel
word, bytes 0/2 not consumed, colour with its limit, bit 15), the frame (40
blocks, the marker, order, the measured cadence, the startup region), the
service under sustained video, the startup to the first real hand-off, and the
presentation-path structure the runtime relies on (texture path, native
display, source-driven presents, Policy A in software and physically, rate
conversion, hand-over vs scanout) — every row with its id and a status of F or
C, U items only as pointers. Refreshed to the status EVIDENCE already carries:
the Video row of `docs/hardware/ARCHITECTURE.md` (the "exact hardware word
layout H" of Phase 2 now cites GBP-HW-081 / 131 / 129), the Video capture row
and Frame timing of `docs/hardware/GBS-DOL.md` (geometry F (hw), the measured
cadence), the VIDEO row and §2.2 of `docs/protocol/REGISTERS.md` (GBP-HW-076 /
081 / 129), and `docs/protocol/README.md` (no longer "not yet verified on
hardware"). `docs/README.md` indexes the two new files.

**Tests.** `tests/host/test_phase4_assessment.py`: the verdict once and in the
same words in ROADMAP, HANDOFF and the assessment; the criterion verbatim and
Phase 9's ownership intact; every id cited by the promoted pages and the
assessment defined in EVIDENCE / UNKNOWNS; the highest ids unchanged
(GBP-HW-260, GBP-VID-035); every row of the video page with an id and an F / C
status; the four terms, the asymmetry and an owner per residual; no unknown
closed. `make test-python` green. No file under `src/`, `tools/`,
`stimulus/`, `poc/` or `Makefile` changed.

**Next.** The Orchestrator validates the assessment and the promotion; the
Operator chooses the next phase (Phase 5 is the ROADMAP's next; Phase 9 stays
gated by `CLAUDE.md` §26). No run is pre-registered.

## 2026-09-21 — Issue #18: Phase 5 entered on paper — the input path in three layers, the references decompiled, U-GBP-010 resolved statically at CORROBORATED and kept open, the architecture designed behind the boundary

**Goal.** Enter Phase 5 as research / design, software-only, at the
Operator's direction: reconstruct the keypad path in three layers kept
apart, survey the references with exact provenance, attempt U-GBP-010
statically, design the input architecture behind a testable boundary, and
guarantee the future poll-to-latch latency measurement stays expressible —
without implementing a KEYPAD write, touching the runtime, the service path,
Policy A, the witness layer or any frozen format, or minting a `GBP-HW-` id.
Nothing under `src/`, `poc/`, `tools/` or `Makefile` changed.

**The physical record starts from nothing.** No probe from GBP-PROBE-001 to
RUN 13 ever wrote the KEYPAD window; the only keypad evidence before this
checkpoint was static (GBP-KEY-001, GBP-VID-011), and everything added here
is static too (GBP-KEY-002…005). The document says so first.

**The references, re-verified rather than cited from memory.** The Disc's
`main.dol` was re-extracted from the ISO (`3dd3692f…`, the recorded identity)
and GBI's image re-unpacked (`0b2c44ea…`), both imported and analysed
headlessly with Ghidra 12.1.3 and the project's `OpenGbpFunc.java` (decomp,
refs, callsites) into `build/analysis/ghidra18/` (private). The keypad
globals were found by scanning both binaries for r13-relative half-word
stores (Disc `r13 − 0x7028`; GBI `r13 + 0x37c` = `0x800b4e9c` with
`_SDA_BASE_ 0x800b4b20` read from the entry code). Disc: the write primitive
`0x80089e40` (bytes 0x1E/0x1F, 32-byte DMA to `base + 0xC00000`), the setter
`0x8008ad30` (opposite-direction filtering on bits 4/5 and 6/7; the
injection override), the cadence (handler `+0x74` on every interrupt, the
5 ms tick at two sites), the injection `0x8008c31c` (bits 0xF0 five ticks
on / five off, up to 24 000 ticks), and the application mapping `0x8000822c`
(SDK pad bits → word bits, two modes). GBI: the thread `0x8000bf30` reads up
to four GameCube pads and N64 pads through tables, packs the word with
`0x80015ddc` into the first half of the 64-byte ACK block at `0xCFFFE0`,
writes `KEYPAD := 0` at start and the sleep pulse `0x0304` / `0x0300` as one
64-byte block at `0xC00000`. Dolphin `c185d27`: `data[0x1e]` bit 0 → key 9
(L), bit 1 → key 8 (R), "need to be flipped". GBATEK: KEYINPUT, the official
joypad figure, and the AGB-side detection observation (`0x030F` = the four
directions, which is exactly what the Disc injects at bits 4–7:
GBP-KEY-005, the one external corroboration, four bits wide). Enhanced mGBA
was **obtained**: `external/mgba` @ `8692b26b…` (branch `20251124`, shallow,
ignored), consulted for L2/L3 only; its `gamecube/` platform directory is a
toolchain file and the GameCube build uses the Wii sources; recorded in
`external/README.md` with the note that `dolphin/Externals/mGBA` is a
different tree. GBI's controller ROMs were hashed and not analysed.

**U-GBP-010, statically.** Lined up against KEYINPUT (bit 8 = R, bit 9 =
L), the Disc's default mode puts L at word bit 8 and R at bit 9 (its
alternate mode moves Y and X there), GBI does the same for GameCube and N64
pads, and Dolphin's model matches. Per the Issue's own rule that is **RESOLVED STATICALLY at
CORROBORATED** — the encoding two independent implementations target, one
official — and **not a physical FACT**: the window is write-only, the AGB is
the only observer, and nothing on this hardware has been measured. GBI's
`0x0304` was not used (it sets both bits). U-GBP-010 stays **OPEN** on its
own condition (a game that distinguishes L/R), with the result recorded;
`REGISTERS.md` keeps Dolphin's order at H; no order is adopted, implemented,
tabulated as Open-GBP's own or defaulted. Deliverable D was conditional on
NOT RESOLVABLE and was therefore not designed; the one-sentence instrument
that would raise CORROBORATED to FACT is named, not designed.

**Architecture and observability, on paper.** `gbp_input_map` (L3 policy as
data) → `gbp_keypad_encode` (an encoding descriptor as data, unfilled until
the physical result; host tests test the logic, never a hypothesised order)
→ `gbp_keypad_write` (one 32-byte `write_block` through the existing
transport, so mock and replay come for free), polled from the main loop in
the pump slot after the RE-ARM under the consumer slice's rule — skipped when
a cause is pending — never in the ISR, never inside the service transaction.
GBI's combined KEYPAD + ACK block and the Disc's in-handler write are
recorded as reference behaviour and not proposed, because the first would
change the ACK transaction and the second breaks R8. The stop-condition
check found nothing frozen that would have to move. For the latency chain
the head instants `t_poll` and `t_write` are `gbp_time64` fields (the SI
sample precedes the poll by at most one polling period, a bounded offset);
no existing sidecar changes, the reacting frame stays identifiable through
the `frame_index` join, and no timestamp is emitted and no figure is stated.

**Records.** `docs/research/INPUT_PATH.md` (new); EVIDENCE GBP-KEY-002…005;
UNKNOWNS U-GBP-010 (open, updated); ROADMAP Phase 5 status; HANDOFF;
`external/README.md`; `tests/host/test_input_path.py` pins the layers, the
single stated outcome, the open unknown, the absence of a new `GBP-HW-` id
and of any adopted order, and the mGBA row.

**Next.** The Orchestrator validates the entry; then a functional Issue for
the module behind the boundary, then a pre-registered first physical KEYPAD
write, which is also U-GBP-010's own closing test.

## 2026-09-21 — Issue #19: the input path implemented — one descriptor as data, the step in the pump slot, host tests, the candidate stream-0014 built and not executed

**Goal.** Implement `INPUT_PATH.md` §7 — mapping, encoding, write, poll —
with host tests through the existing mock and replay backends, and one build
candidate whose identity is computed and which is executed nowhere.
Software-only, no hardware. Untouchable and untouched: the video path, the
validated service path, Policy A, the witness layer, the disposition trace,
every frozen format, `tools/`, `docs/protocol/`, `docs/hardware/`.

**The Operator's decision, kept safe.** Issue #18 left the descriptor
unfilled; the Operator chose to implement the CORROBORATED assignment and let
the first physical run falsify it. The four conditions, and how each holds:
(1) the assignment lives in exactly one place, as data —
`GBP_KEYPAD_DESCRIPTOR` in `src/gbp/gbp_input.c`, ten positions and a
polarity; every consumer applies the table, and flipping it is one line
(`tests/host/test_input_impl.py` proves the initializer's sequence appears in
no other file); (2) the definition's comment states CORROBORATED, NOT FACT,
cites GBP-KEY-004 and U-GBP-010 and names what falsifies it; (3) nothing is
promoted — `REGISTERS.md` keeps H, U-GBP-010 stays OPEN, no document promotes
the order, no `GBP-HW-` id exists; (4) every encoding test runs
under arbitrary synthetic descriptors (reversed, scrambled, active-low) and
no test compares the L or R position with a number.

**What was built.** `gbp_input_map` (L3, `GBP_INPUT_POLICY_DEFAULT` as data:
A, B, Start, D-pad 1:1; X and Y = Select; Z reserved; L / R on the click;
stick beyond ±48, a named policy value from Enhanced mGBA's dead zone under
the same libogc pad path; opposites filtered as the Disc's setter);
`gbp_keypad_encode` / `decode` (L1, bit for bit, unused bits 0);
`gbp_keypad_block` (GBI's u16-replicated layout — bytes 0x1E/0x1F carry hi/lo
where the Disc writes them); `gbp_keypad_write` (one 32-byte `write_block` at
`base + (0xC << 20)`); `gbp_input_step` (first pass, change, and the refresh
every `GBP_INPUT_REFRESH_MS` = 5 ms — the Disc's tick, frozen by the Issue:
neither reference proves the device needs it, both do it, `CLAUDE.md` §18 —
with a one-period back-off after a failure); `gbp_input_selftest`, pure.

**Where it runs, and the clocks.** `input_step()` is the first statement of
the stream probe's `pump()`, i.e. inside the slot `gbp_vqueue_pump()` admits
after the RE-ARM only when no cause is pending — before the slice's early
returns, so it is unconditional within the slot, and before the slice's own
`t0`, so STREAMPUMPT still measures the conversion alone. `PAD_ScanPads()`
from the main loop; libogc2's implementation copies the SI hardware's last
poll (twice per frame at the default rate) and issues no synchronous
transfer. Every instant is read through the transport's `ticks` / `ticks64`,
never `gettime()`, because the stream audit pins the `gettime` sites of
`pump` (5) and `main` (8): both are unchanged. `t_poll` and `t_write` are
fields of the state; nothing emits them and no figure is derived.

**What changed in the probe, exactly.** `main.c` +136 lines: the include;
the input block before `pump()` (state, the transport pointer, two
`_Static_assert`s pinning libogc2's button bits and error codes,
`input_step()`); one call as the first statement of `pump()`;
`gbp_input_init` after the time base; the pure self-test and its
`INPUTSELFTEST` gecko line after the display self-test; an `ENVINPUT`
record; two banner lines; the transport pointer armed before
`gbp_vstate_probe_run` and disarmed with the pump after it; `INPUT` /
`INPUTT` ringlog records, one screen line, one `INPUT` gecko line. Nothing
else: the body of `pump()` below the call, `submit_ready`, the display and
witness paths, and every file under `src/gbp` other than the new module are
byte-identical to `a877284` (the test pins this through `git diff`). The
POC Makefile: `BUILD_ID := stream-0014`, `gbp_input.c` in `SRCS`, the
history note. `tests/unit/Makefile`: the new test.

**Verification.** `tests/unit/test_gbp_input.c`: 8 453 checks, 0 failures
(every button; the thresholds at the boundary; the filtering; synthetic
descriptors; the write through the mock by address, length and bytes and
through the replay by its script; the refresh policy and the back-off with a
controlled clock). `make -C tests/unit` green. `make test-python` green
(1 304 passed, 1 skipped: the RUN 12 build-info check skips when the tree
builds a later candidate). Built in `ghcr.io/extremscorner/libogc2:20260805` with zero
warnings, none suppressed; two consecutive clean builds byte-identical.
`make stream-audit`: 0 findings; the interrupt path identical to the
GBP-VIDEO-001 reference; `gbp_input.o` linked. Dolphin, auxiliary: device
absent and the GBP model both PASS on stated conditions (READY identity,
`SELFTEST ok=1`, `INPUTSELFTEST ok=1`, `COUNTERS balanced=1`, `INPUT
steps=0`); in both the probe stopped before any service cycle, so the slot
and the KEYPAD write never ran in Dolphin — the smoke proves the build
boots, the module executes and reports, and the abort path is unaffected;
it cannot exercise the write. **Candidate:**
`build/poc/gbp-video-stream-probe/gbp-video-stream-probe.dol`, `stream-0014`,
commit `0ff8355`, 513 152 B, SHA-256
`ef76a170c10d335e62c017e53f74c60e410e44f5ce2fbca6774ab43c68ec0b9c`, ELF text
402 900 / data 109 936 / bss 20 093 452. Not executed; no run pre-registered.

**Expired pins.** Four build-id pins written when stream-0013 was frozen
(RUN 12 and RUN 13 pre-registration, the stream success test, the WITELIG
test) asserted the tree still declared stream-0013; they now pin the series
and the Makefile's history, and the RUN 12 build-info check skips when the
tree builds a later candidate. `test_input_path`'s "no keypad code yet" pin
became "the module the design named". RUN 12 / RUN 13 records are untouched.

**Residuals, for the validator.** (1) `docs/protocol/INITIALIZATION.md`
still says KEYPAD "has never been written" — true of the hardware, and
untouchable here; it will need the Orchestrator's update when the candidate
runs. (2) Whether a held key needs the refresh is untested; the first run's
counters (`INPUT ... refresh=`) will say what the refresh cost, not whether
it was needed. (3) No release-all write at the teardown: the validated stop
sequence is untouched, so the device keeps the last word written. (4) The
stick threshold 48 and X/Y = Select are policy, revisable. (5) The first
physical input run will be the first KEYPAD write ever issued by Open-GBP.

**Next.** The Orchestrator validates #19; then a Hardware Issue
pre-registers the first physical input run (test ID, run name, archive
names, a game that distinguishes L from R, PASS / FAIL / INCONCLUSIVE), which
is also U-GBP-010's own closing test.

## 2026-09-21 — Issue #20: RUN 14 / RUN 15 pre-registered as GBP-INPUT-001, the first physical KEYPAD write — NOT RUN; no hardware, no flash, no build

**Goal.** Pre-register the first physical execution of Open-GBP's KEYPAD
write in `HARDWARE_TESTS.md` (§V7 / §V7.1), documentation only: Question One
first, then the identity, the Swiss slot, the topology, the reserved names,
the procedure with its recovery, the gates with FAIL reachable and a swapped
L/R informative, and U-GBP-010's closing condition restated. No hardware, no
flash, no build, no rebuild, nothing staged; `docs/protocol/` and
`docs/hardware/` untouched.

**Question One, from the code.** Reaching `GBP_VWITNESS_TARGET` (2048) makes
the probe's admission block call `finish(..., "S5_witness_target",
GBP_VSTATE_STOP_WITNESS_TARGET)`: the diagnostics close, `teardown_hardware()`
runs the R7 order (IRQ 26 masked, the stop word, CONTROL restored, PI
cleaned, the handler and AR_INFO restored), the probe returns, and `main()`
disables the pump and the input transport, drains GX, switches the
framebuffer back to the text console and waits for X / START with POWER
CYCLE REQUIRED. The AGB image leaves the screen and input stops; nothing
keeps the cartridge running with video. The window, on RUN 13's own record:
the not-before gate at 5.000151 s after CONTROL, the first retained record
at 6.067203 s (64 structural closes and a block-0 boundary), 2048 records at
59.727133 Hz = 34.27 s more — the target ~40.4 s after the CONTROL
transform; run 8 with a retail cartridge ended the same way, so the witness
is content-blind and the figure holds for a menu. Stage 1 (the EZ-Flash
tabs) fits with margin; stage 2 (launch the AGS ROM, the AGB reset with L+R
held, its controller test, ten buttons) plausibly needs 25–35 s and would
start 15–20 s in — one session cannot be relied on to carry both, and its
record would be ambiguous. **Consequence:** two runs of the same image, RUN
14 = stage 1 and RUN 15 = stage 2 conditional on RUN 14, each with its own
five reserved names; no code, constant, profile or build change is needed or
proposed (a single-session profile would be a separate functional Issue).

**What §V7.1 freezes.** The identity (stream-0014, `0ff8355`, 513 152 B,
`ef76a170…`, verified on disk, not rebuilt). The Swiss slot: 12-stream
REUSED, because the manifest numbers the build line and a new slot would
need a `tools/` change; the overwrite of stream-0013 (`5391c3fe…`, the RUN
12 / RUN 13 image, on the host and on the SD) is a recorded decision — its
bytes are preserved under `build/archive/` before staging and it is
reproducible from `7d7a6d8` in the same image, the build line being
deterministic; nothing in `build/physical`. The topology at RUN 13's plus one
controller in port 1 and the EZ-Flash configured to show its menu at boot;
the AGS test ROM policy (proprietary, the Operator's media, nothing enters
the repository). Ten reserved names, absent on disk, with the SD collision
between the two runs stated (the console writes the same names). The
procedure in two conditional stages, the recovery procedure frozen by the
Operator (power off at the button, wait, power on; never correct with the
controller) and the hazard that motivates it. The gates: the machine side is
the INPUT record only — steps, attempts, completed, failed, the action
split, last_word — because the window is write-only; the video-path
verdicts are recorded, not gates; Question M PASS / FAIL / INCONCLUSIVE with
FAIL reachable; Question O AS-ASSIGNED / SWAPPED / INCONCLUSIVE with SWAPPED
a recorded, expected-possible, informative outcome that falsifies
GBP-KEY-004's assignment and is not a failure of the run. U-GBP-010
restated: it closes either way as OPERATOR OBSERVATION and neither outcome
makes the routing FACT. The project-owned stimulus is recorded as a future
option (the Operator's authorisation), not started: RUN 14 first.

**Records.** `HARDWARE_TESTS.md` §V7 / §V7.1 (new); HANDOFF (the Phase-5
row, the ten reserved names, the issue trail, blocker, next action,
do-not-assume); ROADMAP Phase 5; UNKNOWNS U-GBP-010 (a pointer, still OPEN);
`tests/host/test_run14_prereg.py`; `test_run13_prereg.py`'s "no run-14+
name" pin relaxed to run-16+. No GBP-HW id; nothing under `src/`, `poc/`,
`tools/`, `Makefile`, `docs/protocol/` or `docs/hardware/`.

**Next.** The Orchestrator validates; then the Hardware Issue moves RUN 14
to the Operator (staging per §V7.1.6, checklist §V7.1.7); RUN 15 follows
conditionally.

## 2026-09-21 — Issue #22: two Operator inputs recorded after the pre-registration — a rejected instrument, the Start-up Disc recollection and its composition — §V7 frozen; no hardware, no code; and the host staging for Hardware Issue #21

**Goal.** Record, outside the frozen §V7, two pieces of Operator input that
arrived after Issue #20 closed: an instrument evaluated and rejected, and the
Operator's recollection of the official Start-up Disc's controller behaviour
on this hardware with the composition it allows. Every statement carries its
classification; nothing changes U-GBP-010, the descriptor, `docs/protocol/`
or `docs/hardware/`; §V7 is byte-identical to `848007a` and a test pins it.

**Item 1.** The homebrew input-test ROM `romhacking.net/homebrew/142`
(reported: ~21 s start after the boot logo, a START gate before the input
screen, no button combinations) is REJECTED against the ≈ 40 s window
§V7.1.1 derives — the start alone consumes about half the session, the START
gate costs more, and the missing combination support defeats the L +
R-together observation outright — `INPUT_PATH.md` §10.1, so it is not
re-proposed later.

**Item 2.** The recollection (X and Y = SELECT; L and R = L and R; an OSD
option inverts this with Y → L and X → R; the stick = the D-pad; the C stick
nothing; Start = START; Z = the Disc's OSD) corroborates every row of the
implemented L3 policy that the Disc decides, as OPERATOR OBSERVATION and a
recollection of past use (`INPUT_PATH.md` §10.2; GBP-KEY-007); the
implementation follows the Disc rather than GBI on SELECT, so Z stays
unmapped — the button the Disc reserves for its OSD, a free alignment for a
Phase 9 OSD. The composition "alternate mode: Y → word bit 8 (static,
GBP-KEY-002) + Y acts as L (observed) ⇒ bit 8 = L" was worked out rather than
asserted (§10.3): it holds as logic on two conditions — the swap option is
the decompiled mode 1 (supported by the match of all three roles and the
code's two modes), and the X/Y attribution is remembered exactly, since the
exchange would give the opposite answer — and its second term is a
recollection, weaker than RUN 14's report will be. It is the first
hardware-side term GBP-KEY-004's assignment has ever had, and it changes no
status: CORROBORATED, U-GBP-010 OPEN for RUN 14, the descriptor unchanged.
What would make it a recorded observation is written down (a short Disc
re-verification, official software only, not part of §V7, for the
Orchestrator to attach to a Hardware Issue if wanted).

**Records.** `INPUT_PATH.md` §10 (new) and a pointer in §3.2; EVIDENCE
GBP-KEY-007 (OPERATOR OBSERVATION, recollection; no GBP-HW id); UNKNOWNS
U-GBP-010 (still OPEN); HANDOFF (the issue trail: #21 open as the Hardware
Issue, #22; the staging state); `tests/host/test_input_addenda.py` pins §V7
byte-identical to `848007a`, the module and the descriptor unchanged, the
records and their classifications, and the untouchable paths.

**Staging for Hardware Issue #21 (operational, reported there).** At the
Orchestrator's authorisation the Executor performed steps 1–3 of §V7.1.6 on
the host: stream-0013's exact bytes preserved first as
`build/archive/gbp-video-stream-probe-stream-0013-7d7a6d8.dol` (506 496 B,
`5391c3fe…dd79`, cmp-identical to the slot copy it came from); `make swiss`
without a rebuild (the build/poc DOL `ef76a170…0b9c` unchanged before and
after, timestamps untouched); `build/swiss/12-stream/boot.dol` = 513 152 B,
`ef76a170…0b9c`, cmp-identical to build/poc; INDEX.txt's 12-stream row
reads stream-0014 / 0ff8355. Step 4 (the SD) is the Operator's; the card was
not touched. `build/` is ignored: nothing to commit.

**Next.** The Orchestrator validates #22; RUN 14 executes under Hardware
Issue #21 independently.

## 2026-09-21 — Issue #23: §V7.1 amended BEFORE HARDWARE — the Enhanced Control Checker is the instrument of RUN 14 and RUN 15 with distinct press counts, the EZ-Flash menu test becomes the optional RUN 16; the Operator's unregistered trial recorded for what it is; no hardware, no code

**Why legitimate, said in the section.** No run had executed and no result
existed; what the discipline forbids is changing a gate after seeing data.
The amendment is dated and labelled; Question One, the shared gates, the
recovery procedure with its hazard, and the U-GBP-010 part keep the bytes of
Issue #20 (`848007a`), pinned by `tests/host/test_run14_prereg.py`.

**The instrument, and why it moved to the first run.** Enhanced Control
Checker GBA (github.com/nataliethenerd/enhancedcontrolcheckerGBA, main =
`76924c1371d7bf761f8b1ed45ab36f195cd1374f`, 2024-08-11, CC BY-SA 4.0; the
repository's prebuilt ROM 69 348 B, SHA-256 `53c212c7…b6e`, hashed from a
scratchpad clone; nothing enters the tree), flashed by the Operator to the
EZ-Flash NOR and booted straight into. Verified in its source: ten
independent counters at rows 4–13, one `if` per button over `keysDown()` in
a `VBlankIntrWait()` loop (simultaneous presses each count; edge-triggered),
`consoleDemoInit()` then the loop (no splash, no menu, no START gate),
persistent two-digit tallies, a tone per press. Science: it answers M at
least as well as the menu tabs and O strictly better (a distinct-count
vector identifies any permutation, the tabs only L's direction against R's),
needs no menu boot screen, persists, and is verifiable from source; the
practical reason: the NOR now holds it, and requiring the menu would ask the
Operator to undo what he prepared for a weaker instrument. The AGS test ROM
is the fallback; the menu tabs are the optional, independent RUN 16.

**Numbering and authorisation, stated.** Run numbers are the order of
execution: RUN 14 = walk A (L 1, R 2, A 3, B 4, SELECT 5, START 6), RUN 15 =
walk B (L 1, R 2, UP 3, DOWN 4, LEFT 5, RIGHT 6), RUN 16 = the optional menu
tabs; the run14 / run15 names Issue #20 reserved now carry the walks and the
run16 names the menu test — stated explicitly, none used, the experiment
GBP-INPUT-001 in all three. Hardware Issue #21 authorises RUN 14 and is the
Orchestrator's to align; RUN 15 and RUN 16 need their own.

**The schedule as the primary gate.** One press per button leaves an end
state that cannot see a permutation, so the single-press walk is forbidden
in the procedure text; distinct counts make the end state self-describing.
Ten distinct positive counts cost at least 55 presses; with a NOR boot the
checker's screen is expected ~3–5 s after CONTROL and the tallies must be
read before ~40.4 s, so ~30 s of walk: 55 fits only at a sustained two
presses per second with ~3 s to spare — not with margin for a first-ever
run — hence two runs of 21 presses each, every count distinct within each,
L and R first and smallest twice. Both channels are used: which labelled row
moved at each press (live, when seen) and the final tally vector (always);
verdicts are read from the vector, the live channel corroborates or flags.
Reading rules: L=1, R=2 AS-ASSIGNED; L=2, R=1 SWAPPED (informative,
falsifies GBP-KEY-004's assignment, not a failure); a zero where a count
was expected is an M finding; an unexpected non-zero identifies the
misrouted button by its count; a cut walk keeps the completed buttons.

**The unregistered trial.** Before the amendment landed the Operator ran an
informal, unregistered, incomplete trial of the exact candidate with the
checker: not RUN 14, never RUN 14, no claim, no gate. Recorded as what they
are: the §18 hazard did not occur (an informal observation, never a result)
and the Operator's impression that the mapping was recognised as
implemented (informal; U-GBP-010 OPEN, the descriptor unchanged). Prior
exposure recorded: the Operator's report is no longer naive; the mitigation
is the distinct-count scheme ("what number is on the screen"), plus an
optional photograph of the final tally screen under §V6.10. A negative
control from the same trial, informal: every counter incremented except
under Z and the C stick, which produced nothing — as the policy intends (Z
unmapped, the C stick unread), consistent with the Disc's behaviour and
with the Z / OSD note; OPERATOR OBSERVATION supporting no claim. The trial
left no file on the SD (the Operator deletes the card copies after moving
them to `logs/`); the check stays in the procedure and a leftover, if ever
found, is moved aside, never deleted. Recorded, not acted on (outside §V7):
because the card copy is deleted after the move, the `logs/` copy is the
ONLY copy until the run-suffixed archive exists — the same exposure that
lost RUN 12's bare-name drop, and the argument for a per-run subdirectory
convention in `logs/`, for a later checkpoint.

**Records.** `HARDWARE_TESTS.md` §V7.1 (heading, intro, parts 2–7, 9, 11,
12); HANDOFF (the fifteen names, the issue trail, the Phase-5 row, a
do-not-assume note on the trial); ROADMAP Phase 5;
`tests/host/test_run14_prereg.py` reworked; `test_run13_prereg.py`'s
"no run-16+ name" pin moved to run-17+; `test_input_addenda.py`'s whole-§V7
pin narrowed to parts 1, 8 and 10. Nothing under `src/`, `poc/`, `tools/`,
`Makefile`, `docs/protocol/`, `docs/hardware/`.

**Next.** The Orchestrator validates #23 and aligns Hardware Issue #21; RUN
14 executes; RUN 15 follows in order; RUN 16 only if wanted.

## 2026-09-21 — Issue #24: RUN 14 and RUN 15 INGESTED (§V7.2) — GBP-INPUT-001, the first physical KEYPAD writes: Question M = PASS · Question O = AS-ASSIGNED in both runs; U-GBP-010 CLOSED; the routing stays CORROBORATED; the tally frames versioned as the machine-decodable record; no hardware, no code

**Goal.** Persist RUN 14 (walk A) and RUN 15 (walk B) — executed 2026-09-21
under Hardware Issue #21 on the unchanged `stream-0014` (`0ff8355`,
`ef76a170…`) with the Enhanced Control Checker on the EZ-Flash NOR — against
the gates frozen in §V7.1.9 before the runs, with the verdicts the Orchestrator
fixed in the Issue, without touching §V7.1, any gate, or anything under
`src/`, `poc/`, `tools/`, `Makefile`.

**Archiving, first.** Ten raw files: RUN 14's arrived in `logs/` under the
bare console names, RUN 15's in `logs/run15/` (the Operator's per-run
subdirectory — the convention Issue #23 argued for, so nothing was
overwritten); each run went to its reserved names with `cp --update=none` +
`cmp`, was hashed before any interpretation, and matched the Orchestrator's
hashes (reported on #21). Identities in §V7.2.3 / GBP-HW-261.

**Analyzers, as they are.** `vindex.py` → `INCONCLUSIVE_TOO_FEW_INTACT_FRAMES`
(2048 records, all 40 blocks, the canonical strip INVALID on every frame —
the content is the checker's console screen, not OGBPCOORD1; recorded, not a
gate); `vidxcap.py` intact containers, stop = witness target, valid CRCs;
`vfull.py` → INCONCLUSIVE 8/8 (STRIP-L inconsistent, by construction) but the
preserved texture equals the Python conversion in all 16 samples; `vdisp.py`
joined: 2047 `SELECTED_NEW`, `[2403]` edge, interior 0, reorder 0, depth 1,
frozen p99 0.003 ms / max 0.475 ms (the p99 fell because the deferred count
fell below 1 % of the join — arithmetic, not a latency claim), 7 repeats;
corrected `vvi.py` 2372/2372 and 2373/2373 (RUN 15 `frame_index` 1169 latched
two retraces after its hand-over — instrumentation semantics); `vpace.py`
prints nothing over the disp alone (recorded). Transport, startup (165.34 ms,
+0.186 ms on RUN 13, recorded, no tolerance) and the witness window clean.

**The machine gate.** `INPUT attempts = completed = 7 892 / 7 895, failed 0,
retry 0, first 1, change 42, refresh 7 849 / 7 852, last_word 0000`; `key_changes
= 42 = 2 × 21` in each run is consistent with the walks and records no
button; `INPUTT` write 30/30/38 ticks, step 98/169/1046 (observational). The
only machine facts the write-only window allows: the runtime polled, encoded
and wrote.

**Two honesty items.** (1) `truncated=1` in both logs: derived as runs 9 / 10
derived their WITELIG clip — the ENVINPUT record (new in stream-0014) renders
to 266 characters against the 248-character payload and is clipped after
`desc_status=CORROBORATED_n`; lost `ot_FACT selftest=1`, both recoverable;
nothing else affected; GBP-KEY-008, a functional item, not repaired here. (2)
§V7.1.9 says an unpressed counter "reads 0"; the checker prints a tally only
on a press, so it is BLANK — read as "never incremented", the substance of the
gate; recorded in §V7.2.7, GBP-HW-265 and the fixtures, the frozen text not
edited.

**Two channels, kept apart, in agreement.** The Operator's vectors, relayed
literally by the Orchestrator: `1 2 · · · · 6 5 3 4` and `1 2 3 4 5 6 · · · ·`
= the walks' arithmetic expectation (GBP-HW-263, OPERATOR OBSERVATION). The
checker's screen is AGB video and every one of the 16 preserved OGBPFULL1
frames shows it; under the unmodified `vfull.py` parser the tally digits
resolve by exact 8 × 8 glyph match (six glyphs transcribed from the frames; an
unknown bitmap aborts) — final state from s3 (+18.943 s after CONTROL),
identical across s3..s7, the partials in the declared walk order, L at 1
before R moved, L = 1 and R = 2 in both runs, digit for digit the Operator's
vectors (GBP-HW-264, FACT as data — recomputable, not operator observation).
No per-press live record was relayed; the photographs were useless (no
upscaler in the chain; the 240 × 160 text does not survive the camera; no
claim about the chain); the unregistered trial and the prior exposure
persisted from §V7.1.2.

**Verdicts, read from §V7.1.9 as written.** Question M = PASS in both (every
pressed button at its own counter, no unpressed counter moved, nothing moved
without a press; all ten buttons across the two runs). Question O =
AS-ASSIGNED in both (L = 1, R = 2). U-GBP-010 CLOSED on its own condition,
supported by the report and independently by the frames, the descriptor kept
exactly. **The routing stays CORROBORATED, not FACT:** the chain's fourth link
— the Operator pressed L exactly once — is in no machine record (42 key
changes, not which buttons); the distinct-count design makes a wrong walk
overwhelmingly unlikely to produce the vector, an argument, not a record.
**The finding:** §V7.1.10 supposed a project-owned stimulus was needed for
FACT; the missing piece is one log line — the word written at each key change
— which would close the join by machine end to end (GBP-KEY-009; recorded,
NOT implemented).

**Records.** `HARDWARE_TESTS.md`: the `## V7` heading and intro (outside
§V7.1), §V7.2 (12 parts; §V7.1 byte-identical to `ed7dea2`, pinned);
EVIDENCE GBP-HW-261…265, GBP-KEY-008, GBP-KEY-009; UNKNOWNS U-GBP-010 CLOSED
with the closing condition quoted; ROADMAP Phase 5 status (the acceptance
criterion NOT assessed — a test ROM, not a game); HANDOFF; captures/README.
Fixtures: the disp / full / vi sidecars of both runs byte-identical (the tally
frames are the machine-decodable record and the same OGBPFULL1 format RUN 12
and 13 versioned — no format change), the two qual projections, two struct
files with every identity, the declarations as relayed and what was NOT
posted, the summary records verbatim, the per-sample readings with the glyph
table, the verdicts with their boundaries and the RUN 13 comparison. Tests:
`tests/host/test_run14.py` recomputes from the fixtures (the INPUT gate
re-parsed, the ENVINPUT clip re-rendered from the source format, the tally
vectors re-decoded from the bytes, Policy A / vdisp / vvi / vfull recomputed,
§V7.1 byte-identical, nothing under the untouchable paths moved); the expiring
pins in `test_run14_prereg.py`, `test_input_addenda.py`, `test_input_impl.py`
and `test_input_path.py` updated for the executed state (U-GBP-010 CLOSED,
GBP-HW up to 265, GBP-KEY-008 / 009, the archives present, the fixtures added).

**Not done, on purpose.** No hardware; no code, build or rebuild; no change to
§V7.1, any gate, threshold or verdict definition; the per-change word logging
not implemented; the routing not promoted; RUN 12, RUN 13 and Phase 4 not
re-judged; `docs/protocol/` and `docs/hardware/` untouched (the Orchestrator's
to update); RUN 16 not run.

**Next.** The Orchestrator validates #24 and closes Hardware Issue #21; then
whether GBP-KEY-008 / GBP-KEY-009 become a functional checkpoint, and how the
Phase-5 acceptance criterion is assessed with a real game.

## 2026-09-21 — Issue #25: the Operator's post-run topology declaration for RUN 14 / RUN 15 recorded in §V7.2, and the controller scope stated where the verdicts are read; no hardware, no code, no gate or verdict change

**The declaration, given after the runs and relayed by the Orchestrator,**
mapped onto §V7.1.4: same GameCube — declared; BBA connected without a
network cable ("BBA conectado sem cabo de rede") — BBA PRESENT / Ethernet
DISCONNECTED, declared; video chain unchanged — declared; controller — a
GENERIC (third-party) GameCube controller, on record for the first time; the
official Nintendo pad the Operator also owns was NOT the one used. **Not
closed by inference:** the pre-registration asks for the same GameCube AND
the same Game Boy Player, tracked as distinct units; the Operator first
declared the console only, so the Game Boy Player was recorded as NOT
SEPARATELY DECLARED — and the same day he declared his hardware inventory
(exactly one GameCube, exactly one Game Boy Player; not to be questioned on
it again), which settles the Game Boy Player as DECLARED on the basis of that
inventory: an operator declaration, sound, and not an inference from the
console declaration (an inference about a topology item is what makes a run
inconclusive — the whole reason the Orchestrator refused to write it
earlier). Standing note for future pre-registrations (HANDOFF, do-not-assume):
the console / GBP identity cites this declaration; BBA and Ethernet state, the
display chain, the cartridge and its boot screen and the controller are still
declared per run. The "recorded as absent" note Issue #24 correctly left is
replaced, with its history kept (§V7.2.2, GBP-HW-261).

**The controller scope, stated where the verdicts are read** (§V7.2.1, §V7.2.7,
GBP-HW-265): the policy reads L and R by their digital click only
(`trigger_threshold=0` in both ENVINPUT records; the analogue value is not
read) and L and R were the first two buttons of both walks — so what RUN 14
and RUN 15 establish about L and R is established through the digital click
of a third-party pad. Both edges recorded: encouraging (the path worked with a
generic controller) and a limit (the official pad was not exercised; no data).
Verdicts, gates, §V7.1, evidence ids and classifications unchanged; the
§V7.1.8 TOPOLOGY gate's reading gains the declaration.

**Records.** §V7.2.1 / .2 / .4 / .7 / .10 / .11 / .12; GBP-HW-261 (the
declaration and its history) and GBP-HW-265 (the pad's scope); HANDOFF;
ROADMAP Phase 5; captures/README; the two struct fixtures regenerated for
the topology section only (`ingestion_head` kept at `ed7dea2`; M / O
unchanged — checked field by field); `tests/host/test_run14.py` pins the
declaration, the open item and the scope. No new evidence id.

**Next.** The Orchestrator validates #24 / #25 and closes Hardware Issue #21.

## 2026-09-21 — Issue #26: the input path promoted into the consolidated documentation — `docs/protocol/INPUT.md`; "KEYPAD, never written" superseded on its date; the L/R order CORROBORATED, not FACT, in every page that states it; no status changed, no id minted, no hardware, no code

**Decision: a short consolidated page, and not one step past the evidence.**
`docs/protocol/INPUT.md` in the role `VIDEO.md` plays for video, deliberately
thin and saying so: the window and the 16-bit word (F static per reference, F
software for the runtime), the polarity (C, GBP-KEY-005, and the runs counted
presses under it), the fact that a written word reaches the cartridge as key
presses (F hw, run-scoped — two runs, one test ROM, one cartridge, one generic
pad; the frames FACT as data and the Operator's report OPERATOR OBSERVATION,
recorded apart), the bit assignment with its status — bits 0–7 C; bits 8 / 9
**CORROBORATED, not FACT**, with the chain's missing link (the Operator's
press count, in no machine record), GBP-KEY-009 as what would close it and the
generic-pad scope in the same paragraph — the write cadence of the references
and of the runtime (observational costs, never a latency figure; the need for
the 5 ms refresh not established), the controller mapping marked as this
project's POLICY and never a device fact, and a section of what is not
established (latency, other pads, the official pad, a real game — Phase 5's
criterion NOT assessed). Every row has an id that exists and a status of F or
C; nothing HYPOTHESIS or UNKNOWN is stated as a device property.

**The stale statements, corrected with their history kept.**
`INITIALIZATION.md`: the two "never written" sentences of 2026-09-15 stay as
written and carry *[true as of 2026-09-15; written on hardware 2026-09-21,
§15]*; the two "KEYPAD (Phase 5)" pointers are dated the same way; a new §15
records the first physical writes (GBP-HW-262, GBP-HW-264, GBP-HW-265), where
the write sits in Open-GBP (the pump slot, not the service), that the cycle
of §14 is unchanged, and points at `INPUT.md`. `REGISTERS.md`: the KEYPAD row
now reads C for existence / format / polarity, F (hw, run-scoped) for the
mechanism, and **L/R bit order: C — was H until 2026-09-21, not FACT**; a §2.3
"KEYPAD word" table carries the same with its ids. `GBS-DOL.md`: the keypad
row refreshed the same way (the Dolphin-derived "order per Dolphin swapped" /
"H (L/R order)" wording gone). `ARCHITECTURE.md`: the keypad plane refreshed
— and its "active-low like the AGB KEYINPUT register" was found to contradict
GBP-KEY-001 / GBP-KEY-005 (1 = pressed at the window, the opposite of
KEYINPUT): corrected to what the evidence carries, the same kind of drift
Issue #17 found in the Phase-2 pages. `VIDEO.md` §6's pointer dated. The three
indexes list the new page. Dated notes on GBP-KEY-004 and U-GBP-010 record the
promotion (no status changed).

**The line held.** Nothing writes, implies or lets a reader conclude that
the GBS-DOL's routing of word bits 8 and 9 is FACT; every page that states the
order says CORROBORATED, not FACT, names GBP-KEY-009 and carries the
generic-pad scope (the digital click of a third-party pad; the official pad
not exercised) — pinned by `tests/host/test_input_promotion.py`, which also
checks that no "FACT" stands near a statement of the order without a
negation, that every id cited by the new page exists, that §V7 of
`HARDWARE_TESTS.md`, the evidence headings and U-GBP-010 are the bytes of
`4e54583`, and that nothing under `src/`, `poc/`, `tools/`, `Makefile` or
`captures/fixtures/` moved. Expiring pins updated with their reasons
(`test_input_addenda.py`, `test_input_impl.py`, `test_input_path.py`,
`test_run14.py`: REGISTERS.md no longer keeps H; `test_phase4_assessment.py`:
the promoted pages may now cite GBP-HW-261…265, the assessment still at 260).

**Not done, on purpose.** No hardware; no code; no change to §V7.1 or §V7.2,
to a verdict, a gate or an evidence status; the routing not promoted;
U-GBP-010 not reopened; GBP-KEY-009 not implemented; no GBP-HW id.

**Next.** The Orchestrator validates #26; then GBP-KEY-009 — the
per-key-change word logging that takes the routing to FACT — as a functional
checkpoint with its own pre-registration, and Phase 5's real acceptance with
a commercial game, which the Operator schedules.

## 2026-09-21 — Issue #27: GBP-KEY-009 implemented (one KEY line per key change, bounded, in the sidecars' time base) and GBP-KEY-008 repaired (ENVINPUT + ENVINPUT2) with a general payload guard; candidate `stream-0015` built, executed nowhere; no hardware

**Why this one matters.** The routing is CORROBORATED and not FACT for one
reason: the machine record of RUN 14 / RUN 15 knows 42 key changes and not
which buttons. This checkpoint closes that link in software: every write that
is not a refresh — first, change, retry — now leaves one ringlog line, `KEY
n= act= keys= word= t_poll= t_attempt= t_done= xfer= rc=`, with the word, the
logical set and three instants in the transport's ticks64 base, the base of
OGBPIDXCAP1 / OGBPDISP2 / OGBPVI1, so a future run's join needs no conversion
(INPUT_PATH.md §8's guarantee, spent; §11 added there). A refresh never
produces a line (RUN 14: 7 849 refreshes against 42 changes). FACT is now
reachable by a run; it is not actual.

**The four constraints, held.** (1) No flood: refreshes counted, never
recorded. (2) Bounded, never blocking (CLAUDE.md §13): the store is the
ringlog itself, preallocated, never grown; a line is admitted only while a
64-line reserve stays free for the 27 post-run records, so a run with more
changes than the ≈ 700-line headroom keeps every summary, keeps `dropped=0`,
and counts the surplus in `KEYLOG lost`; truncated and overwritten counted,
0 by construction; the line's cost measured (`KEYLOG emit_ticks`) outside the
INPUTT step aggregate. (3) The instants are the transport's ticks64. (4) The
worst-case rendering is DERIVED: 158 of 248, in the C unit test (every
conversion at its type's maximum, the longest names) and in the Python
guard; the emission is from the pump slot after the write, through the
transport's clock — the stream audit's `gettime` pins unchanged.

**Deliverable B.** ENVINPUT split as WITELIG was: `ENVINPUT` (229 at the worst
case) and `ENVINPUT2` (222), every field kept. And the guard made general:
`tests/host/test_ringlog_payloads.py` renders every `ringlog_printf` of the
probe at the worst case of every conversion, with every `%s` bounded by the
vocabulary of its source (checked against the code), in two tiers stated
honestly — STRICT for the owned records, a RATCHET for four older records
that exceed 248 at the pure type width (ENVSTORE 303, INPUT 269, WITQUAL 307,
DISPTRACE 253; frozen, so growth or any new over-long record fails a test,
and their physical renderings in the versioned RUN 14 / RUN 15 records are
far below the payload) — and it is shown able to fail on the stream-0014
ENVINPUT. Records emitted by the library probe code (src/gbp) are outside
its scope, stated.

**Candidate.** `stream-0015` = commit `da06500` (clean), 514 880 B, SHA-256
`dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49`, zero warnings, none suppressed; two consecutive clean builds byte-identical, `make stream-audit` 0 findings (the ext and base one-shot handlers identical to the physically validated GBP-VIDEO-001 build); Dolphin absent —
RESULT PASS (4.2 s) on the stated conditions: READY build=stream-0015 commit=da06500, INPUTSELFTEST ok=1 device_touched=0, COUNTERS balanced=1 sci_clean_at_probe=1 inv_fail=0 storage_fault=-; model — RESULT PASS (4.1 s) on the same conditions (HSPDevice=2, GBPlayerRom): in both the probe stops before any
service cycle, so the pump slot, the KEYPAD write and the KEY record are not
exercised there (said, not implied). NOT executed; no run name reserved;
nothing pre-registered; `build/swiss/` untouched.

**Records.** EVIDENCE GBP-KEY-010 (new, software) and dated addenda to
GBP-KEY-008 (REPAIRED, physical validation pending) and GBP-KEY-009
(IMPLEMENTED, FACT reachable); UNKNOWNS U-GBP-010 note; ROADMAP Phase 5;
HANDOFF (candidate row, state block, Phase-5 row, blocker, next action, trail,
do-not-assume); INPUT_PATH.md §11. `docs/protocol/INPUT.md` still says
"recorded, not implemented" for GBP-KEY-009: untouchable here, the
Orchestrator's to update after validation. Tests: 8 505 C checks;
`tests/host/test_input_keylog.py`; the Issue #19 pin "no format carries the
head instants" became "only the KEY format carries them"; the guards that
froze src/ and poc/ allow exactly the four files of this checkpoint.

**Two commits, one purpose each:** `cee9165` (the record) and `da06500`
(the repair and the guard); the docs follow with the identity.

**Next.** The Orchestrator validates #27 and designs the hardware checkpoint
that spends the candidate — pre-registration, staging, the instrument, the
KEY-to-frame join — for the Operator; then Phase 5's real acceptance with a
commercial game.

## 2026-09-21 — Issue #28: RUN 17 / RUN 18 PRE-REGISTERED as GBP-INPUT-002 (§V7.3), the machine-join runs of `stream-0015` — Question One answered first: FACT is reachable per bit by the whole-run join, not by an interval join and not per press; NOT RUN / NOT AUTHORISED HERE; INPUT.md corrected on its date; no hardware, no code, no build, no staging

**Question One, from the code and the data, before any gate.** OGBPFULL1
samples K = 8 every 256 frames (`GBP_VFULL_K 8u`, `GBP_VFULL_SPACING 256u`,
static-asserted): one frame every 4.286 s at 59.727 Hz, at +6.084 … +36.087 s
after CONTROL in RUN 14 / RUN 15. The walk of RUN 14 ran from before s0 to
between s2 and s3 (9–13 s, three intervals, several buttons each). Per press
in time: NOT supported (latency stays out of reach). Per interval: a
consistency check only — within one interval the counts are NOT distinct
(RUN 14: R +2 and B +2 in the same interval; RUN 15: R +2 and DOWN +2), so an
interval-local count join cannot bind which bit moved which counter. The
whole run: SUPPORTED, and it binds — the KEY record gives every word bit's
rising-edge total R_b, the last samples give every counter's final tally T_c
(FACT as data), and the walk's distinct counts make the map b → c unique from
the totals alone, with no timing, no boundary rule, no pacing and no human
link (the Operator produces presses, he no longer counts them; a miscount
degrades only the bits that tie). **FACT is reachable per bit with
`stream-0015` exactly as it is.** What would raise the granularity is
recorded, not proposed: a denser full-frame store (a build change, and K = 8
already holds 1.84 MB against 1.65 MB free), a per-frame record of the tally
cells (a new format), the project-owned stimulus publishing KEYINPUT into
the witnessed strip (the route to a per-press join and a latency figure);
pacing the walk is EXCLUDED. No stronger join was needed for FACT, so no
stop condition fired.

**What §V7.3 freezes.** The numbering resolved (RUN 16 keeps the optional
menu reading and its stream-0014 names; a reserved number belongs to its
experiment whenever it runs; RUN 17 = walk A, RUN 18 = walk B, ten
stream-0015 names reserved, verified absent); the identity (514 880 B,
`dd545c01…3a49`, `da06500`, NOT rebuilt); the Swiss slot reused again with
stream-0014 preserved first to `build/archive/gbp-video-stream-probe-stream-0014-0ff8355.dol`
(reproducible from `0ff8355`), the SD path and the exact hash in the
checklist, the staging not performed here; the topology by the declared
inventory for the units and per-run declarations for the rest, the generic
pad's scope travelling with any L/R statement; the recovery procedure
byte-identical to §V7.1.7's; the shared gates plus the KEY record's own
(`KEYLOG events = emitted, lost 0, truncated 0, overwritten 0`; `truncated=0`
a gate again, which also validates GBP-KEY-008's repair physically); the
join's definitions frozen so the ingestion cannot tune them (completed words
only, rising edges from 0000, the end state = the vector common to at least
two samples after the last KEY line, blank = 0 recorded again); verdicts per
word bit — FACT / FACT-SWAPPED / NOT CLOSED (informative, the failed join
reachable and read against the stated assumptions A1–A3) / UNDECIDED /
INCONCLUSIVE — with the interval check recorded under a pre-registered
boundary convention (B = 3 source frames) that is never a latency figure,
and the Operator's channel (M, O) beside the join, never merged; what a FACT
would change (GBP-KEY-004 and the consolidated pages, by the ingestion) and
what nothing here measures; the commercial-game run not pre-registered (a
game supplies only one end of the join).

**Also.** `docs/protocol/INPUT.md`'s "GBP-KEY-009; recorded, not implemented"
corrected in its own commit with its date kept (implemented the same day in
`stream-0015`, executed nowhere; RUN 17 / RUN 18 pre-registered to spend it);
the routing's status unchanged. HANDOFF (the ten names, the state block, the
Phase-5 row, the candidate row, blocker, next action, trail, two do-not-assume
bullets), ROADMAP Phase 5. `tests/host/test_run17_prereg.py` pins the part in
the style of `test_run14_prereg.py`; `test_run13_prereg.py` /
`test_run14_prereg.py` move their "no run-17+ name" pin to run-19+;
`test_input_promotion.py` and `test_run14.py` slice §V7 at §V7.3.

**Not done, on purpose.** No hardware; no staging; no build; no code; no
change to §V7.1 or §V7.2, a verdict, a gate or an evidence status; no
promotion; no GBP-HW id; the commercial-game run not pre-registered.

**Next.** The Orchestrator validates #28 and opens the Hardware Issue for RUN
17 (RUN 18 to follow under its own authorisation).
