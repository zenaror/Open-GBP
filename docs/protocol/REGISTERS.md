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
ids refer to `docs/research/EVIDENCE.md`. **Nothing here has been
verified on physical hardware by this project yet.**

Names in this document are neutral working names. Where Dolphin uses a
different name it is given in parentheses; the Dolphin name is not
evidence of hardware semantics.

## 1. Addressing

| Item | Value | Status | Evidence |
|------|-------|--------|----------|
| Transport | GameCube ARAM DMA engine (`0xCC005020` MMADDR, `0xCC005024` ARADDR, `0xCC005028` CNT with bit 31 = direction 1 → ARAM/HSP→main memory) | C | GBP-HSP-001 |
| Base | `internal ARAM size` as reported by `0xCC005012` bits 0–2 (retail: `0x01000000`) | C (DISC reads it; GBI uses `AR_GetInternalSize()`; DOLPHIN uses `≥ ARAM size`) | GBP-HSP-001 |
| Prerequisite | `0xCC005012` bits 3–5 := `3` ("16 MB expansion" code) before any GBP access | C (DISC + GBI) — not modeled by DOLPHIN | GBP-HSP-002, U-GBP-004 |
| Register select | ARAM address bits 20–23: `base + (index << 20)` | C | GBP-HSP-001 |
| Window size | 1 MB per register index; the register responds at least at offsets `0x00000` (DISC, GBI, DOLPHIN mask `addr>>20`) and `0xFFFE0` (GBI writes a 64-byte block at `0xCFFFE0` covering KEYPAD+IRQ and reads 64 bytes at `0x4FFFE0` covering CONTROL+SIOCTL) | C | GBP-HSP-004 |
| Transfer unit | 32 bytes, 32-byte-aligned main-memory buffer (cache flushed/invalidated around the DMA) | C | GBP-HSP-003 |
| Completion | poll `0xCC00500A` bit 5 (ARAM DMA interrupt flag), then write bit 5 back to clear; DISC also refuses to start while bit 9 (DMA busy) or bit 5 is set and times out after 1 s | F (DISC) / GBI uses libogc ARQ | GBP-HSP-003 |
| Memory mirror | ARAM addresses mirror every 64 MB in Dolphin ("verified on real HW" comment in DSP.cpp) | H for GBP purposes | — |

## 2. Register map

Index = ARAM address bits 20–23 relative to `base`. "Block" = the 32-byte
transfer; byte offsets are within that block.

| Index | Working name | Dir | Payload | DISC | GBI | DOLPHIN | Status | Evidence |
|------:|--------------|-----|---------|------|-----|---------|--------|----------|
| 0x0 | TEST | W/R | 32 bytes, echoed back **inverted** (`~x`) | write 4 patterns C3/3C/FF/00, read back byte 0x1F == ~pattern; repeated every 5 ms as removal detection | write C3, read ~C3, write ~C3, read C3; then same with FF | stores `data ^ 0xFF`, returns it | C | GBP-TEST-001 |
| 0x1 | VIDEO | R | 0xF00 bytes = 4 scanlines × 240 pixels × 4 bytes | 40 buffers of 0xF00 per frame (160 lines) | reads 0xF00 to a frame buffer on IRQ bit 8 | 0x400 × 16-bit RGB5, each byte doubled to 32 bits | C (size/geometry) | GBP-VID-001 |
| 0x4 | CONTROL | W/R | 1 byte at offset 0x1F (write); read byte 0x1F (DISC) / block (DOLPHIN fills all 32) | see §3 | see §3 | see §3 | C | GBP-CTL-001 |
| 0x5 | SIOCTL | W/R | 1 byte at 0x1F | used by the internal-serial state machine | written together with CONTROL (64-byte DMA) | read → `IGBPlayer::ReadSIOControl` (stub returns 0); write → stub | F (exists), H (semantics) | GBP-SIO-001 |
| 0x8 | AUDIO | R | 0x1000 bytes | 70 buffers of 0x1000; consumed on IRQ bit 10 | reads 0x1000 on IRQ bit 10 | 0x400 PWM bytes, each mirrored ×4; refilled at 4096 Hz | C (size), H (format) | GBP-AUD-001 |
| 0x9 | SIODATA | W/R | 32-bit: write bytes 0x1C–0x1F; read assembled from bytes 0x19,0x1B,0x1D,0x1F (DISC) | serial state machine; write data, then SIOCTL \|= 0x80 | read on IRQ bit 6; written from a message queue | stub; read model fills block with the u32 repeated | F (exists), U (byte layout, semantics) | GBP-SIO-001, U-GBP-002 |
| 0xC | KEYPAD | W | 16-bit at bytes 0x1E–0x1F, 1 = pressed | written on every HSP IRQ and every 5 ms tick | written on every IRQ (with IRQ ack in the same 64-byte block); 0 at start; `0x0304` (= L+R+Select) on sleep IRQ | lo byte = GBA keys 0–7; hi bit0→L(key 9), bit1→R(key 8) | C (existence/format), H (L/R bit order) | GBP-KEY-001 |
| 0xD | IRQ | W/R | 16-bit: read bytes 0x1D (hi) and 0x1F (lo); write bytes 0x1E–0x1F | see §4 | see §4 | see §4 | C | GBP-IRQ-001 |

Unused indices (0x2, 0x3, 0x6, 0x7, 0xA, 0xB, 0xE, 0xF) are not touched by
DISC or GBI; Dolphin logs a warning. Their behavior is **unknown**
(U-GBP-005). Do not probe them with writes.

### 2.1 Read data layout

DISC extracts 16-bit values from bytes 0x1D/0x1F and 32-bit values from
bytes 0x19/0x1B/0x1D/0x1F, i.e. it treats read data as **byte-doubled**
(each 8-bit value occupies two consecutive bytes). This is the same
doubling Dolphin applies to VIDEO (16-bit color → 4 bytes `hh hh ll ll`).
Dolphin's IRQ/SIODATA read models place the bytes differently
(`hh hh hh ll`, and the u32 repeated) but agree at 0x1D/0x1F. Therefore:

- bytes 0x1D/0x1F of a 16-bit read, and 0x19/0x1B/0x1D/0x1F of a 32-bit
  read, are the safe ones to consume (**C**);
- the exact content of the other bytes is **U** (U-GBP-008).

### 2.2 VIDEO word format

| Bits (32-bit word, big-endian) | Meaning | Status |
|---|---|---|
| 31–24 and 23–16 | high byte of a 16-bit color, doubled | C (DOLPHIN + GBI check `& 0x80800000`) |
| 15–8 and 7–0 | low byte of the color, doubled | C |
| bit 15 of the 16-bit color (→ mask `0x80800000` after doubling) on the **first pixel** of a 0xF00 block | first scanline of a frame | C (DOLPHIN sets it; GBI tests it; DISC pre-fills a dummy first block with `0x80` in byte 0) |
| color encoding | GBA palette order (bits 0–4 red, 5–9 green, 10–14 blue) in DOLPHIN (`M_RGB8_TO_RGB5`) | H |

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
| 2 | 0x0004 | callback slot 3: stop sequence + video reset ("game pak" event) | — | `IRQ::GamePak` | C |
| 4 | 0x0010 | callback slot 2: CONTROL \|= 0x10, state → 3 | write KEYPAD `0x0304` (L+R+Select) | `IRQ::Sleep` | C |
| 6 | 0x0040 | callback slot 1: serial operation completion | read SIODATA | `IRQ::Serial` | C |
| 8 | 0x0100 | callback slot 5: read VIDEO block (0xF00) | read VIDEO | `IRQ::Video` (every 4 lines) | C |
| 10 | 0x0400 | callback slot 4: read AUDIO block (0x1000) | read AUDIO | `IRQ::Audio` | C |
| odd bits 1,3,5,7,9,11 | 0x0002…0x0800 | "mask" bits: DISC computes `enable = Σ(1<<(2k+1))` for sources with a registered callback and `disable` for the others, then writes `(cur & ~enable) \| disable` | — | Dolphin comment: "software appears to use the odd bits to mask the even bits" | C (usage), H (polarity: 1 = masked) |
| 15 | 0x8000 | written at IRQ entry (`mask \| 0x8000`) | — | `IRQ_ASSERTED`; writing a 1 clears the bit | H |

Acknowledge sequence (DISC, in the PI handler): write IRQ (mask\|0x8000)
→ write `0x2000` to PI `0xCC003000` → read IRQ → if any of `0x0555` is
set, **write the read value back** (clears those sources) → dispatch.
GBI: PI ack in the raw handler, then in the worker thread read IRQ, act,
write the read value back in the same DMA as KEYPAD, and write 0 to IRQ
at the end of each loop. Dolphin: `m_irq &= ~written_value`. → **C**.

## 5. GameCube-side registers involved

| Address | Name (YAGCD/libogc) | Use here | Status |
|---------|--------------------|----------|--------|
| `0xCC003000` | PI INTSR | bit 13 (0x2000) = HSP interrupt; write 1 to acknowledge | C (DISC, GBI, libogc `irq.c`, Dolphin `INT_CAUSE_HSP`, YAGCD 6.1.5.2) |
| `0xCC003004` | PI INTMR | bit 13 enables the HSP interrupt (OS interrupt number 26 in SDK and libogc) | C |
| `0xCC00500A` | DSP CSR | bit 9 DMA busy, bit 5 ARAM-DMA interrupt flag (write 1 to clear) | C (DISC, libogc, YAGCD 6.2.8) |
| `0xCC005012` | AR_INFO / AR_SIZE | bits 0–2 internal size code (3 = 16 MB), bits 3–5 expansion size code; DISC and GBI write 3 into bits 3–5 | C (libogc2 `__ARCheckSize`, DISC, GBI) |
| `0xCC005020/24/28` | AR DMA MMADDR / ARADDR / CNT | the transfer itself | C |

## 6. Open questions

See `docs/research/UNKNOWNS.md` U-GBP-001 … U-GBP-010. The most
important for Phase 3: whether `0xCC005012` bits 3–5 are required
(U-GBP-004), the exact read byte layout (U-GBP-008), and everything about
SIOCTL/SIODATA (U-GBP-001/002).
