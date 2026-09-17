# Game Boy Player — Register / Transaction Reference (preliminary)

How GameCube software addresses the GBS-DOL. Everything here was derived
in Phase 2 from three independent sources and is labeled accordingly:

```text
DISC   Game Boy Player Start-up Disc (UGPE01 v2, main.dol sha256 3dd3692f…), static analysis
GBI    Game Boy Interface Standard Edition 2026 (gbi.dol sha256 8083636c…, unpacked image 0b2c44ea…), static analysis
DOLPHIN Dolphin master c185d27e / tag 2606a, Source/Core/Core/HW/HSP/HSP_DeviceGBPlayer.cpp
YAGCD  §11 "HSP devices seem to be accessable through the ARAM interface with offsets beyond 16MB" (no register detail)
```

Status: **F** fact (directly observed in a source), **C** corroborated
(≥2 independent sources agree), **H** hypothesis, **U** unknown. Evidence
ids refer to `docs/research/EVIDENCE.md`. **Rows that cite a `GBP-HW-`
id have been observed on this project's hardware; everything else is
static analysis.**

Names in this document are neutral working names. Where Dolphin uses a
different name it is given in parentheses; the Dolphin name is not
evidence of hardware semantics.

## 1. Addressing

| Item | Value | Status | Evidence |
|------|-------|--------|----------|
| Transport | GameCube ARAM DMA engine (`0xCC005020` MMADDR, `0xCC005024` ARADDR, `0xCC005028` CNT with bit 31 = direction 1 → ARAM/HSP→main memory) | C | GBP-HSP-001 |
| Base | `internal ARAM size` as reported by `0xCC005012` bits 0–2 (retail: `0x01000000`; read `0x0043` on the user's console with and without the GBP) | C (DISC reads it; GBI uses `AR_GetInternalSize()`; DOLPHIN uses `≥ ARAM size`) | GBP-HSP-001, GBP-HW-001/007 |
| Prerequisite | `0xCC005012` bits 3–5 := `3` ("16 MB expansion" code) before any GBP access | C (DISC + GBI) — not modeled by DOLPHIN. **Hardware 2026-09-14:** DMA and the TEST inversion also work with code 0, but CONTROL/IRQ then read differently (`00`/`90` fills) — what the code changes is open | GBP-HSP-002, GBP-HW-002/005, U-GBP-004 |
| Register select | ARAM address bits 20–23: `base + (index << 20)` | C | GBP-HSP-001 |
| Window size | 1 MB per register index; the register responds at least at offsets `0x00000` (DISC, GBI, DOLPHIN mask `addr>>20`) and `0xFFFE0` (GBI writes a 64-byte block at `0xCFFFE0` covering KEYPAD+IRQ and reads 64 bytes at `0x4FFFE0` covering CONTROL+SIOCTL) | C | GBP-HSP-004 |
| Transfer unit | 32 bytes, 32-byte-aligned main-memory buffer (cache flushed/invalidated around the DMA) | C | GBP-HSP-003 |
| Completion | poll `0xCC00500A` bit 5 (ARAM DMA interrupt flag), then write bit 5 back to clear; DISC also refuses to start while bit 9 (DMA busy) or bit 5 is set and times out after 1 s. **Completion does not depend on the GBP being present** (28/28 transfers completed with and without it) — it is not a presence signal | F (DISC) / GBI uses libogc ARQ / F hardware | GBP-HSP-003, GBP-HW-008 |
| Memory mirror | ARAM addresses mirror every 64 MB in Dolphin ("verified on real HW" comment in DSP.cpp) | H for GBP purposes | — |

## 2. Register map

Index = ARAM address bits 20–23 relative to `base`. "Block" = the 32-byte
transfer; byte offsets are within that block.

| Index | Working name | Dir | Payload | DISC | GBI | DOLPHIN | Status | Evidence |
|------:|--------------|-----|---------|------|-----|---------|--------|----------|
| 0x0 | TEST | W/R | 32 bytes, echoed back **inverted** (`~x`) on the read that follows the write; a later read returned `00` on hardware | write 4 patterns C3/3C/FF/00, read back, compare **byte 1** == ~pattern; repeated every 5 ms as removal detection | write C3, read (majority-vote byte) == ~C3, write ~C3, read == C3; then same with FF | stores `data ^ 0xFF`, returns it persistently | **F (hardware 2026-09-14)**: bytes 1–31 inverted in 8/8 handshakes, byte 0 anomalous in 3/8; second read `00` | GBP-TEST-001, GBP-HW-003, GBP-HW-006 |
| 0x1 | VIDEO | R | 0xF00 bytes = 4 scanlines × 240 pixels × 4 bytes | 40 buffers of 0xF00 per frame (160 lines) | reads 0xF00 to a frame buffer on IRQ bit 8 | 0x400 × 16-bit RGB5, each byte doubled to 32 bits | C (size/geometry); **hardware 2026-09-16:** one DMA of 0xF00 from this index completed (61.4 µs around the call), first word `FFFFFFFF` (GBI frame-start predicate true), content recorded raw — the size/geometry stays C (a DMA of the requested length completes regardless); **2026-09-16 GBP-VIDEO-001:** 88 consecutive DMAs of 0xF00 from this index all completed, one complete frame-start interval of exactly **40** blocks (16.794 ms, 59.547 Hz), both frame-start predicates agreeing on all 88 blocks, payload uniform white under the byte 1 / byte 3 picking; 40 blocks/frame now **CORROBORATED** by hardware, the 4×240 line geometry still C | GBP-VID-001, GBP-HW-051/058, GBP-HW-064/066/067/069 |
| 0x4 | CONTROL | W/R | 1 byte at offset 0x1F (write, DISC) or replicated over the block (GBI); read byte 0x1F (DISC) / majority vote (GBI) / block fill (DOLPHIN) | see §3 | see §3 | see §3 | C; hardware read `00×32` with exp code 0, `94/98 90×31` with exp code 3 (meaning U-GBP-017); GBI-layout writes `8C`×32 / `90`×32 accepted and read back (GBP-HW-013) | GBP-CTL-001, GBP-HW-005/013/017 |
| 0x5 | SIOCTL | W/R | 1 byte at 0x1F | used by the internal-serial state machine | written together with CONTROL (64-byte DMA) | read → `IGBPlayer::ReadSIOControl` (stub returns 0); write → stub | F (exists), H (semantics) | GBP-SIO-001 |
| 0x8 | AUDIO | R | 0x1000 bytes | 70 buffers of 0x1000; consumed on IRQ bit 10 | reads 0x1000 on IRQ bit 10 | 0x400 PWM bytes, each mirrored ×4; refilled at 4096 Hz | C (size), H (format); **hardware 2026-09-16:** one DMA of 0x1000 from this index completed (66.5 µs), 3969 of 4096 bytes zero, content recorded raw; **2026-09-16 GBP-VIDEO-001:** 144 consecutive DMAs of 0x1000 all completed, 9 payloads preserved (16–36 nonzero bytes in the first eight, 2178 in the last), 22 consecutive AUDIO-only causes spanned the 5.335 ms gap that closes a video frame; the 4096 Hz refill rate and the PWM format stay H | GBP-AUD-001, GBP-HW-050/057, GBP-HW-064/065/068, GBP-VID-009 |
| 0x9 | SIODATA | W/R | 32-bit: write bytes 0x1C–0x1F; read assembled from bytes 0x19,0x1B,0x1D,0x1F (DISC) | serial state machine; write data, then SIOCTL \|= 0x80 | read on IRQ bit 6; written from a message queue | stub; read model fills block with the u32 repeated | F (exists), U (byte layout, semantics) | GBP-SIO-001, U-GBP-002 |
| 0xC | KEYPAD | W | 16-bit at bytes 0x1E–0x1F, 1 = pressed | written on every HSP IRQ and every 5 ms tick | written on every IRQ (with IRQ ack in the same 64-byte block); 0 at start; `0x0304` (= L+R+Select) on sleep IRQ | lo byte = GBA keys 0–7; hi bit0→L(key 9), bit1→R(key 8) | C (existence/format), H (L/R bit order) | GBP-KEY-001 |
| 0xD | IRQ | W/R | 16-bit: read bytes 0x1D (hi) and 0x1F (lo) (DISC) / vote over bytes ≡1 and ≡3 mod 4 (GBI); write bytes 0x1E–0x1F (DISC) or `hh ll` replicated (GBI) | see §4 | see §4 | see §4 | C; hardware read `90×32` with exp code 0 and `ae 8a ae ae 8a 8a ae ae…` (= `0x8AAE` byte-doubled, byte 0 anomalous) with exp code 3. **2026-09-15:** within 2 s of CONTROL `0x8C` (AGB powered) it read `0x8FAE` — bits 0x0400/0x0100 set, odd bits and bit 15 unchanged — with no PI IRQ (register never written), persisting after CONTROL went back to 0x90 (GBP-HW-024) | GBP-IRQ-001, GBP-IRQ-005, GBP-HW-004/005/024 |

Unused indices (0x2, 0x3, 0x6, 0x7, 0xA, 0xB, 0xE, 0xF) are not touched by
DISC or GBI; Dolphin logs a warning. Their behavior is **unknown**
(U-GBP-005). Do not probe them with writes.

**Baseline without a Game Boy Player (hardware, 2026-09-14/15):** every
read returned a uniform fill that does not respond to TEST — `C0`×32 in
one run (both expansion codes), `C1`×32 in another run/build
(GBP-HW-007/019). The value is not fixed and its origin is unknown
(U-GBP-019); any uniform fill fails both detection criteria.

### 2.1 Read data layout

DISC extracts 16-bit values from bytes 0x1D/0x1F and 32-bit values from
bytes 0x19/0x1B/0x1D/0x1F, i.e. it treats read data as **byte-doubled**
(each 8-bit value occupies two consecutive bytes). GBI majority-votes
each bit over the block (8-bit) or over bytes ≡1 mod 4 / ≡3 mod 4
(16-bit), which presumes the same doubling. **Hardware (2026-09-14):**
the IRQ window read `8A 8A AE AE` in words 1–7 — byte-doubled `hh hh ll
ll` — and a uniform fill for CONTROL and TEST (GBP-HW-004/005). Dolphin's
IRQ read model `hh hh hh ll` and its "u32 repeated" SIODATA model do not
match this; they agree with hardware only at bytes 0x1D/0x1F.

- **Byte 0 of a block is not reliable**: it carries extra set bits in
  many hardware reads, and a bit 6 that appears ~1.4 µs after a CONTROL
  write and is gone by ~68 µs (GBP-HW-003/004/015, U-GBP-015/021).
  Neither the Start-up Disc nor GBI consumes byte 0. Do not consume it.
- Safe positions: byte 1 or any byte ≥ 1 of a uniform fill (8-bit);
  0x1D/0x1F (16-bit); GBI's vote is the most robust known method.
- **The two "low" copies are not always equal:** in the `0x8FAE` state of
  GBP-INIT-002 every group read `8F 8F AF AE` — offset ≡ 2 mod 4 carries
  bit 0 set, offset ≡ 3 mod 4 does not (U-GBP-025). Both references read
  only offsets ≡ 1 / ≡ 3 mod 4; do the same.
- SIODATA and VIDEO/AUDIO layouts remain **U** (U-GBP-008).

### 2.2 VIDEO word format

| Bits (32-bit word, big-endian) | Meaning | Status |
|---|---|---|
| 31–24 and 23–16 | high byte of a 16-bit color, doubled; **both references consume byte 1 (bits 23–16) only**; GBI's frame test also reads byte 0 | C (DISC + GBI code, DOLPHIN writes both; physical block consistent — GBP-VID-003, GBP-HW-058) |
| 15–8 and 7–0 | low byte of the color, doubled; **both references consume byte 3 (bits 7–0) only** | C (same) |
| bit 15 of the 16-bit color on the **first pixel** of a 0xF00 block | first block of a frame: block index := 0 | C (DOLPHIN sets it; GBI tests `(w & 0x80800000) == 0x80800000` = bytes 0 and 1; DISC tests `(hw >> 7) & 1` = byte 1 and pre-fills its dummy first block with `halfword |= 0x0080`; physical first block: set — GBP-VID-004) |
| color encoding | **bits 14–10 R, 9–5 G, 4–0 B (GX RGB5A3 order)**: DISC uploads bytes 1/3 with bit 15 forced as `GX_TF_RGB5A3` with no visible swap and its embedded idle-screen frame is indigo under this order (crimson under the GBA order); GBI's PNG writer maps bits 14–10 → R; DOLPHIN's mGBA macro may yield the GBA order (bits 0–4 R) — divergence to verify | C (two references); FACT after a known-color cartridge (VIDEO-002) — U-GBP-011 |
| geometry of a block | 4 raster lines × 240 pixels × 4 bytes, line stride 960 bytes; 40 blocks per 160-line frame; block `i` → lines `4i..4i+3` | C (DISC conversion loop, GBI copy + tiler, DOLPHIN); physical: GBP-VIDEO-001 (designed) — GBP-VID-002/005 |

## 3. CONTROL register bits

Bit values are as they appear in the byte. Usage columns describe what
the software does, not what the bit "is".

| Bit | DISC usage | GBI usage | DOLPHIN name / model | Status |
|----:|-----------|-----------|----------------------|--------|
| 0x01 | read → status flag "type" | read → selects "Game Boy" vs "Game Boy Advance" strings | `CART_IS_GB` (1 = GB/GBC game pak) | C |
| 0x02 | read → status flag "present"; a 1→0 edge arms a 61-tick timer | read → appends "Game Pak" | `CART_INSERTED` | C |
| 0x04 | set in *start*, cleared in *stop* | set in *start* (`\|= 0x0C`), cleared in *stop* (`& 0xE3`) | `CONTROL_3V`; 0→1 of (0x04\|0x08) resets the emulated GBA | C (usage), H (name) |
| 0x08 | set when the AGB is started (after *start*), cleared in *stop* | set in *start*, cleared in *stop* | `CONTROL_5V`; both cleared → GBA stopped | C (usage), H (name) |
| 0x10 | set in *stop* and on the *sleep* IRQ; cleared at the end of *start* | cleared in *start* (`& 0xE7`), set in *stop* | `CONTROL_MASK_IRQ`: 1 blocks the PI interrupt | C |
| 0x20 | read; if set during a serial operation the operation fails with code 3 | — | commented `CONTROL_SLEEP` | H |
| 0x40 | read → status flag | — | commented `CONTROL_LINK_CABLE` | H |
| 0x80 | set in *stop*; toggled by the serial state machine (set before a data write, cleared when idle) | — | commented `CONTROL_LINK_ENABLE` | H |

Dolphin masks writes with `0xFC` (bits 0–1 read-only). DISC never writes
bits 0–1 deliberately; consistent, but unverified on hardware.

## 4. IRQ register (16-bit)

| Bit | Value | DISC | GBI | DOLPHIN | Status |
|----:|------:|------|-----|---------|--------|
| 0 | 0x0001 | callback slot 0 (user callback) | — | `IRQ::Link` | C (position), H (meaning) |
| 2 | 0x0004 | callback slot 3: stop sequence + video reset ("game pak" event) | — | `IRQ::GamePak` | C (function). **Hardware 2026-09-15:** reads 1 at idle; written 1 (`IRQ := 0x8AAE`) it cleared — write-1-to-clear **F** (GBP-HW-028) |
| 4 | 0x0010 | callback slot 2: CONTROL \|= 0x10, state → 3 | write KEYPAD `0x0304` (L+R+Select) | `IRQ::Sleep` | C |
| 6 | 0x0040 | callback slot 1: serial operation completion | read SIODATA | `IRQ::Serial` | C |
| 8 | 0x0100 | callback slot 5 (`0x8008ed68` → `0x8008a480`): read VIDEO block (0xF00) | read VIDEO 0xF00 (`0x8000be48(0x100000, …)`) | `IRQ::Video` (every 4 lines) | driver action F; "video request of the AGB" C. **Hardware:** set within 2 s of CONTROL 0x8C (GBP-HW-024); rose ≤ 1 ms after 0x0400 in GBP-INIT-003A and 003B; written 1 while pending (stop word twice, ACK once) it cleared — W1C **F** (GBP-HW-031/032/039); set again ≤ 143 µs after the ACK (GBP-HW-040) |
| 10 | 0x0400 | callback slot 4 (`0x8008cdc4` → `0x8008a764`): read AUDIO block (0x1000) | read AUDIO 0x1000 (`0x8000be48(0x800000, …)`) | `IRQ::Audio` | driver action F; "audio request of the AGB" C. **Hardware:** set within 2 s of CONTROL 0x8C (GBP-HW-024); with the odd bits and bit 15 written 0 it rose 105.27 / 105.29 ms after that write in two runs and raised PI INTSR bit 13 while INTMR bit 13 was 0 (GBP-HW-030/035); written 1 while pending (stop word twice, ACK once) it cleared — W1C **F** (GBP-HW-032/039); set again ≤ 143 µs after the ACK (GBP-HW-040) |
| odd bits 1,3,5,7,9,11 | 0x0002…0x0800 | "mask" bits paired with the even bit below: DISC computes `enable = Σ(1<<(2k+1))` for sources with a registered callback and `disable` for the others, writes `(cur & ~(0x8000 \| enable)) \| disable` at start, and its handler dispatches a source only if its odd bit is clear (`pending & ~(pending >> 1)`) | first loop pass writes `read \| 0x8000` then `0` (all odd bits cleared) before blocking (GBP-IRQ-004) | Dolphin comment: "software appears to use the odd bits to mask the even bits"; its model ignores them | C (pairing); level-written **F** (written 1 → 1, written 0 → 0 for ≥ 50 ms, GBP-HW-028/029/032/039); polarity 1 = masked / 0 = enabled **C** (all six = 1 with sources pending: no PI cause in 2 s, GBP-HW-023/024; all six = 0: the next 0x0400 raised the PI cause in two runs, GBP-HW-030/035 — bit 15 changed together with them, so not F). **Hardware:** all six read 1 at idle (0x0AAA) |
| 12–14 | 0x1000–0x4000 | never written as 1, never tested (`pending & 0x0555` ignores them; not in the slot tables) | never tested | unused | U. **Hardware:** 0 in every expansion-code-3 read; written 0 (A2, stop) they read 0 |
| 15 | 0x8000 | written 1 at IRQ entry (`mask \| 0x8000`) and at stop, 0 at start / exit / DMA done; never tested | written 1 after reading (`read \| 0x8000`), 0 with `IRQ := 0`; never tested | `IRQ_ASSERTED`: set with any source, W1C, drives the line | Not a pair with bit 14. **Hardware 2026-09-15 (GBP-HW-029/032/039/040):** written 0 (A2) it read 0 for ≥ 50 ms with nothing pending; written 1 (stop word, and the 003B ACK with two sources pending) it read 1 with nothing pending — writable and persistent both ways, **F**; the PI cause arrived twice while it read 0; with it left at 1 after the ACK the sources re-set and no PI cause followed, but CONTROL 0x10 had been set again in between (not isolated). Reading (ii) "pending summary, W1C" is therefore **rejected**; reading (i) "global hold/mask, level, 1 = held" stays **H** (never isolated from the odd bits and CONTROL 0x10; U-GBP-007/027). Dolphin's `irq & 0x8000` assertion condition does not match the hardware |

Acknowledge sequence, DISC (`0x8008af08`): write IRQ := mask \| 0x8000 →
PI W1C `0xCC003000 := 0x2000` → read IRQ → if any of `0x0555` is set,
**write the read value back** → dispatch → write IRQ := mask. Order
**GBP → PI → GBP → GBP** (F, GBP-IRQ-002). GBI: PI W1C in the raw
handler `0x8000b400`, then in the worker thread read IRQ, act, write
`read \| 0x8000` back in the same 64-byte DMA as KEYPAD, and write 0 to
IRQ at the end of each loop. Order **PI → GBP** (F, GBP-IRQ-003).
Dolphin: `m_irq &= ~written_value` (model). Common elements → **C**;
the meaning of bit 15 stays H (U-GBP-007). Before its first blocking
wait GBI already writes the register twice (first pass, no interrupt:
`IRQ := read \| 0x8000`, then `IRQ := 0`), and the Disc programs it at
start — GBP-INIT-002 wrote nothing there and saw no interrupt
(INITIALIZATION.md §10). **Hardware 2026-09-15, GBP-INIT-003B
(GBP-HW-037…040, GBP-PI-005):** one complete service cycle in GBI's order
— the PI cause delivered as IRQ 26, `INTSR := 0x2000` inside the handler
(after `__MaskIrq`), then `IRQ := 0x0500 \| 0x8000` from the main loop
under CONTROL 0x8C, then the Disc's stop word — is **F**; the PI cause did
not re-assert after its W1C although the device sources stayed pending
until the ACK. **Hardware 2026-09-16, GBP-INIT-004 (GBP-HW-042…047,
GBP-IRQ-009):** the same cycle a second time through the multi-cycle
handler; 26 µs after the ACK `IRQ := 0x8500` the register read **0x8400**
(0x0400 set again or never cleared, 0x0100 cleared, bit 15 = 1, odd bits 0)
with CONTROL 0x8C and PI bit 13 = 0 in two samples, and no PI cause
followed to the end of the run (U-GBP-007: bit 15 = 1 observed with a
pending source and without the CONTROL change; U-GBP-028: cleared-and-re-set
vs never-cleared undetermined); the stop word from 0x8400 wrote 0x8EAA and
read back 0x8AAA. GBI's re-arm `IRQ := 0` after the ACK was not exercised
by 004 (the run stopped on its clean-boundary rule before it); the
references drain the AUDIO/VIDEO block before their re-arm and never
require the sources to read 0 (INITIALIZATION.md §13). **Hardware
2026-09-16, GBP-AV-SERVICE-001 (GBP-HW-048…060, GBP-IRQ-010; INITIALIZATION.md
§14):** the first complete reference-style cycle — PRESVC **0x0500** (PI
clear, bit 15 = 0) → AUDIO 0x1000 and VIDEO 0xF00 read by one DMA each →
POSTDRAIN still **0x0500**, PI clear (the drain alone did not clear the
status within ≈ 93 µs) → ACK `IRQ := 0x8500` → **0x8000** 25.9 µs later, PI
clear, no main W1C (the undrained ACK of 004 read 0x8400 at the same
distance) → PI clean → **re-arm `IRQ := 0x0000`** (first physical) → **43.9
µs later 0x0400 with PI INTSR bit 13 = 1**, INTMR bit 13 = 0, CONTROL 0x8C
(the next cause, captured while masked, never delivered) → by the stop
0x0500 again (≤ 301 µs) → stop `0x0500 \| 0x8AAA = 0x8FAA` read back 0x8AAA,
one PI W1C. Whether the post-re-arm 0x0400 was a request held under bit
15 = 1 and released by the write or a new event is **U** and non-blocking
(U-GBP-007/027); the model of bit 15 stays H. Phase 3 complete.

**Hardware 2026-09-17, GBP-VIDEO-002 build vstate-0002 (GBP-HW-096):** a source
bit that the ACK does **not** write as 1 survives the acknowledge and the re-arm,
and fires again almost immediately. In two cycles of that run the ACK carried only
AUDIO (`pending 0x0400`, `IRQ := 0x8400`) and the next cause — `0x0100`, VIDEO —
was observed **74 ticks = 1.8 µs** after the re-arm `IRQ := 0x0000`, against a
physical source cadence of 244–294 µs in the same window — the 74 ticks are 134 to
153 times shorter than any previously observed gap between causes of that source in
that run, about 2.1 orders of magnitude, though no lower bound on how soon a new
source may arrive has been established; a third cycle acknowledged `0x0500` and read `0x8100` back at POSTACK, VIDEO
pending again, and continued normally. With GBP-HW-028 (writing 1 to a source bit
that reads 1 clears it) this gives the working model: **the ACK clears exactly the
source bits it writes as 1, the others stay pending, and the re-arm releases them
within microseconds** — **F** for "an un-ACKed source is not lost", **H** for the
per-bit clear mechanism. This does not settle U-GBP-028 (cleared-and-re-set vs
never-cleared for a bit the ACK *did* write), which remains **U**. Its practical
consequence is recorded with the semantic-disagreement policy analysis in the
DEVLOG of 2026-09-17: acknowledging the majority value when a minority replica
claimed an extra source costs one extra service cycle and loses nothing.

**Hardware 2026-09-16/17, both GBP-VIDEO-002 runs (GBP-HW-089…093, U-GBP-033):**
the eight replicas of one 32-byte read of this register are **not guaranteed to
carry the same value**. Preserved bytes from the second run: seven groups
`01 01 01 00` and one `05 05 05 00`, i.e. `0x0100` seven times and `0x0500` once,
from which the Start-up Disc's reading (bytes 0x1D/0x1F) derives `0x0500` and
GBI's bitwise majority derives `0x0100` — a difference of exactly `0x0400`, the
AUDIO source bit. The eighth group is internally coherent, so this is not a flipped
or torn byte. The same run also shows the non-consumed byte at `4k+2` differing
between groups of a single read on windows where both readings agree. Any code
that reads this register must therefore choose a reading explicitly and must not
assume the window is one instant's snapshot. The mechanism is **U** (U-GBP-033).

**Hardware 2026-09-17, GBP-VIDEO-002-R3 build vstate-0003 (GBP-HW-100…103,
GBP-HW-106):** the same condition occurred **23 times** in one 175.848 s run and
the service survived every one of them under the majority-authoritative policy.
All 23 recompute from their own preserved bytes to Disc `0x0500` / GBI `0x0100` /
delta `0x0400`, and in **all 23** the `0x0500` replicas form a **contiguous suffix**
at the end of the window (21 of length 1, one of length 2, one of length 3): the
non-uniformity is **ordered**, not scattered. That the suffix is "the newer value"
is **not** established, and neither is the mechanism. In **23 of 23** the AUDIO
source the majority omitted was present in the **next** ordinary read, 3 492 to
4 310 ticks (86.22 to 106.42 µs) later, so servicing the majority value costs one
extra cycle and loses no source — measured, not assumed. Frequency in that run,
descriptive only: 23 in 1 114 007 deliveries (≈ 1 per 48 435) and 23 in 175.848 s
(≈ 1 per 7.65 s). **No rate is modelled from it**, and those denominators are not
comparable with the earlier runs, which stopped at their first event.

**Hardware 2026-09-17, GBP-VIDEO-002-R4 build vstate-0004 (GBP-HW-110…114):** the
same condition occurred **29 times** in a second 175.848 s run, again all
`SOURCE_SERVICED`, again all Disc `0x0500` against the majority's `0x0100`, and
again with the `0x0500` replicas forming a contiguous suffix (24 × 1, 2 × 2,
3 × 3). Across the two long runs the physical corpus is **52 events, 45/3/4,
contiguous in 52 of 52, with AUDIO present in the next ordinary read in 52 of
52**. This run's diagnostics are the first with correct per-cycle attribution, so
the whole service transaction can be timed on trustworthy clocks:

```text
READ  -> ACK          2 600 .. 2 756 ticks     64.20 ..  68.05 us
ACK   -> REARM          828 .. 1 445 ticks     20.44 ..  35.68 us
REARM -> NEXT CAUSE        77 ..    94 ticks     1.90 ..   2.32 us
READ  -> NEXT CAUSE     3 505 .. 4 128 ticks    86.54 .. 101.93 us
```

A model in which the ACK clears VIDEO, the AUDIO assertion survives it and the
re-arm releases the pending source accounts for all 52 events and for that
ordering — **CORROBORATED, very strong, and still not FACT**: nothing observed
here distinguishes a source that survived the ACK from a new assertion arriving
in that 1.9 to 2.3 µs window. Servicing the majority value therefore costs one
extra cycle and loses no source, measured twice, on two producers.

## 5. GameCube-side registers involved

| Address | Name (YAGCD/libogc) | Use here | Status |
|---------|--------------------|----------|--------|
| `0xCC003000` | PI INTSR (interrupt **cause**) | bit 13 (0x2000) = HSP; bit 16 = reset-switch state. **Hardware 2026-09-15 (GBP-HW-030/033/037/038, GBP-PI-004/005):** bit 13 read 1 while INTMR bit 13 was 0 (captured independently of the mask, no CPU exception), stayed 1 after the device-side sources had been cleared (latched at the PI), was delivered to the IRQ 26 handler when INTMR bit 13 was opened, and one `INTSR := 0x2000` cleared it — also from inside the handler while the device sources were still pending, with no re-assert for ≥ 324 µs — **F** for bit 13. Every INTSR write in libogc2, the SDK, GBI and the Disc is such a single-source acknowledge: 2 (reset switch), 0x1000 (debugger), 0x2000 (HSP). The sustained-level model of the device line is rejected; pulse / edge / transient / separate deassert stay **U** (U-GBP-022) | F (bit 13) / U (line) |
| `0xCC003004` | PI INTMR (interrupt **mask**) | bit 13 enables delivery of the HSP cause to the CPU; OS interrupt 26 = software mask 0x20 in the SDK and in libogc. libogc2 and the SDK rebuild the whole register from shadow masks — under libogc2 change bit 13 only with `__MaskIrq`/`__UnmaskIrq` (ENV-IRQ-002). Hardware: `0x1FA` throughout GBP-INIT-001; **`__UnmaskIrq(IM_PI_HSP)` → `0x21FA`, `__MaskIrq` → `0x1FA` in GBP-INIT-002 (F, GBP-HW-022)**; in GBP-INIT-003B the unmask with a latched cause delivered IRQ 26 inside the call, the handler read `0x21FA` at entry and `__MaskIrq` from inside it gave `0x1FA` (F, GBP-HW-037, ENV-IRQ-003) | F (software contract, bit-13 toggle, delivery) |
| `0xCC00500A` | DSP CSR | bit 9 DMA busy, bit 5 ARAM-DMA interrupt flag (write 1 to clear) | C (DISC, libogc, YAGCD 6.2.8) |
| `0xCC005012` | AR_INFO / AR_SIZE | bits 0–2 internal size code (3 = 16 MB), bits 3–5 expansion size code; DISC and GBI write 3 into bits 3–5 | C (libogc2 `__ARCheckSize`, DISC, GBI) |
| `0xCC005020/24/28` | AR DMA MMADDR / ARADDR / CNT | the transfer itself | C |

## 6. Open questions

See `docs/research/UNKNOWNS.md`. The most important for Phase 3 after
GBP-INIT-003B: the re-arm and repeated-service question (U-GBP-027),
whether `0xCC005012` bits 3–5 are required (U-GBP-004), the function of
bit 15 (U-GBP-007), the nature of the device line (U-GBP-022, P2), the
read byte layout details (U-GBP-008/025), and everything about
SIOCTL/SIODATA (U-GBP-001/002).
