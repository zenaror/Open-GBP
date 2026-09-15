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
