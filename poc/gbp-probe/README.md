# poc/gbp-probe — GBP-PROBE-001

**Build ID:** `probe-0001`
**Question answered:** does the GBS-DOL answer the ARAM-DMA TEST handshake
documented in Phase 2, is the `0xCC005012` expansion code required
(U-GBP-004), and what do raw 32-byte reads of TEST/CONTROL/IRQ look like
(U-GBP-008)?

Read `docs/protocol/REGISTERS.md` and `docs/research/HARDWARE_TESTS.md`
(GBP-PROBE-001) first. **Do not run this before SMOKE-HW-001 has passed.**

## Architecture

```text
poc/gbp-probe/source/main.c        GameCube glue: console, identity, pad, USB Gecko, SD save
        │
src/gbp/gbp_probe.c                probe sequence (host-testable, no hardware access)
        │  struct gbp_transport
        ├── src/platform/hsp_backend.c   real backend: ARAM DMA (0xCC005020/24/28), CSR polling, timeouts
        ├── tests/mocks/gbp_mock.c       scripted device model (present/absent/faults/layouts)
        └── src/gbp/gbp_replay.c         replays a recorded script (fixtures from tools/probelog.py)
        │
src/log/ringlog.c                  preallocated RAM record log  →  src/platform/sdlog.c (SD2SP2 flush, on X)
```

## Exact hardware interaction

| What | Where | Value | Why |
|------|-------|-------|-----|
| read | `0xCC005012` (AR_INFO) | — | original value, logged before anything else |
| read ×2 per mode | blocks `base+0x000000` (TEST), `base+0x400000` (CONTROL), `base+0xD00000` (IRQ), `base` = internal ARAM size from AR_INFO bits 0–2 | 32 bytes each, raw, before and after the handshake | U-GBP-008 |
| write ×4 per mode | block `base+0x000000` (TEST) only | 32 × `C3`, then `3C`, `FF`, `00` — the Start-up Disc's own patterns | GBP-TEST-001 |
| read after each write | TEST | expect 32 × `~pattern`; `match_all` and `match_1f` recorded, raw kept | |
| write (MODE B only) | `0xCC005012` | `(orig & ~0x0038) \| 0x0018` — bits 3–5 := 3, all other bits preserved | U-GBP-004 |
| write (end) | `0xCC005012` | original value; read back and compared (`restored=1`) | restoration |

No CONTROL, KEYPAD, SIO, VIDEO or AUDIO block is ever written. No PI
interrupt is unmasked. libogc's AR/ARQ subsystem is not initialized.

Order: identity → AR_INFO orig → MODE A (raw, handshake, raw) → AR_INFO
read-back → MODE B (write AR_INFO, raw, handshake, raw) → restore AR_INFO
→ read-back → summary → Gecko dump → wait for X/START.

## Timeouts and failure paths

- Every DMA: refuse if DSP CSR shows busy (bit 9) or a stale completion
  flag (bit 5) → `rc=busy`; otherwise poll bit 5 with a 200 ms time-base
  timeout → `rc=timeout`; polls and ticks are logged per transfer.
- A failed transfer never stops the sequence; the next step runs with
  its own timeout; MODE B and the AR_INFO restore always execute.
- If AR_INFO itself cannot be read the probe aborts before touching
  anything else (cannot happen on a GameCube, kept for the mock/replay).
- Logging is a fixed ring of 160 × 200-byte records; when full, new
  records are dropped and counted (`dropped=`), never blocking.

## Log format

RAM records, one per line, `NNNNNN KIND key=value ...`; `data=` is the
untouched 32-byte block as 64 hex digits. Record kinds: `IDENT`, `ENV`,
`PROBE`, `ARINFO`, `MODE`, `RAW`, `TESTW`, `TESTR`, `STATS`. The same
lines go to the USB Gecko as `OPENGBP-PROBE LOG ...` (Dolphin) and, on
X, to `sd:/open-gbp/GBP-PROBE-001_probe-0001.log` with a header
(test id, build id, commit) and footer (dropped count).
`tools/probelog.py parse|fixture|check` reads either form.

## Autonomous validation

```bash
make test           # host: ring log, probe vs mock (present/absent/expansion-required/timeout/
                    #       stuck-busy/DMA error/unexpected block/mirrored layout/ring full/restore),
                    #       replay backend, probelog parser; PPC build; ELF/DOL inspection
make probe-dolphin  # Dolphin twice: HSPDevice=None → expects a_present=0 b_present=0 restored=1
                    #                HSPDevice=2 (Dolphin GBPlayer model) → a_present=1 b_present=1 restored=1
```

Dolphin proves only runtime, flow control, timeouts, logging and absence
of crashes. It cannot answer U-GBP-004 (it ignores AR_INFO bits 3–5).

## Hardware test request (only after SMOKE-HW-001 = PASS)

```text
Test ID:            GBP-PROBE-001
Build ID:           probe-0001
Commit:             see build/poc/gbp-probe/build-info.txt (commit= line) and the screen
DOL:                build/poc/gbp-probe/gbp-probe.dol  (sha256 in build-info.txt)
Cartucho:           any GBA cartridge inserted in the GBP, or none — record which
GBP:                attached, as normally used
Link Port:          nothing connected
BBA:                irrelevant (not touched)
SD2SP2:             inserted, FAT32, with the DOL on it
Passos:
  1. Copy gbp-probe.dol to the SD card.
  2. Launch it through Swiss.
  3. Wait until the screen shows "X = save log" (the probe takes < 2 s).
  4. Press X once; wait for "SD: saved ... lines".
  5. Press START to return to Swiss.
  6. Return /open-gbp/GBP-PROBE-001_probe-0001.log and a photo of the screen.
Resultado esperado: screen shows AR_INFO orig/A/B/final with restored=yes, two MODE lines with
                    raw TEST/CTRL/IRQ hex, no crash. If the GBP answers only in MODE B,
                    U-GBP-004 is answered "required"; if in both, "not required".
Log esperado:       ~40 records: IDENT, ENV, ARINFO ×6, MODE ×4, RAW ×12, TESTW ×8, TESTR ×8, STATS, PROBE end
Pergunta respondida: U-GBP-004, U-GBP-008; first hardware confirmation of GBP-HSP-001/GBP-TEST-001
Risco:              low. GBP-side writes only to the TEST window (what every driver writes first);
                    GameCube-side only AR_INFO bits 3-5, restored. Worst case observed in the
                    mock: a DMA that never completes leaves the engine busy until reset — the
                    log still records everything up to that point.
```
