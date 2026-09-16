# The VIDEO path of the references — static analysis for GBP-VIDEO-001 (2026-09-16)

Status of this document: **research**. Everything here is static analysis of
the two reference programs (the Start-up Disc `main.dol`, sha256
`3dd3692f…`; GBI Standard `gbi-unpacked.dol`, sha256 `0b2c44ea…`; Ghidra
12.1.3 headless, decompilations under `build/analysis/ghidra/`, never
committed), of Dolphin's model (`external/dolphin`, commit `c185d27`) and of
the one physical VIDEO block captured so far (GBP-AV-SERVICE-001,
2026-09-16, GBP-HW-058). Evidence levels: **F(code)** = what the reference
software does, as read in its instructions; **F(hw)** = observed on the
physical GameCube + Game Boy Player; **C** = corroborated by independent
sources but not observed physically; **H** = hypothesis; **U** = unknown.
Nothing in this document is promoted to a physical FACT by being in the
binaries. Addresses are those of the analysed builds. Descriptions are of
behavior; no proprietary code or asset is reproduced.

## 1. Summary

| Question | Start-up Disc | GBI Standard | Dolphin | Physical (one block) |
|---|---|---|---|---|
| Block size / read | 0xF00, one DMA from `base + 0x100000` | 0xF00, one ARQ read of `0x100000` | 0xF00 (`AV_REGION_SIZE` × 4 words) | 0xF00 read by one DMA (F hw) |
| Lines per block, pixels per line | 4 × 240, **raster order, line stride 960 bytes** (conversion loop `FUN_8008efb4`) | 4 × 240 raster (linear copy, then 4-row tiling in the renderer) | 4 × 240 raster (`PrepareScanlineData`) | untestable on one uniform block |
| Bytes per pixel, packing | 4: `hh hh ll ll`; **consumes bytes 1 and 3** | 4: `hh hh ll ll`; **consumes bytes 1 and 3** | writes `hh hh ll ll` | 955/960 words `hh hh ll ll`; the 5 exceptions differ in byte 0 only |
| 16-bit pixel | bit 15 flag; **bits 14–10 R, 9–5 G, 4–0 B** (GX RGB5A3 texture, bit 15 forced to 1) | same order (PNG writer maps bits 14–10 → R; renderer forces bit 15 for RGB5A3) | mGBA macro on its 32-bit buffer: **GBA order (bits 0–4 R) if mGBA's default color format applies** — divergence to verify | white `0x7FFF` under any order |
| Frame-start predicate | `(halfword0 >> 7) & 1` = **bit 7 of byte 1** | `(word0 & 0x80800000) == 0x80800000` = **bit 7 of byte 0 AND byte 1** | sets pixel 0 `|= 0x8000` on the frame's first block (both copies after doubling) | first word `FF FF FF FF`: true for both predicates (F hw) |
| Blocks per frame | 40, explicit (`< 0x28`, `== 0x28`, ring of 40, 41-deep queue, dummy frame 1 + 39) | 40, explicit (`== 0x27` completes a frame, `(i + 1) % 0x28`, 40-entry checksum tables) | 160 / 4 | untested |
| Order inside a frame | block index × 4 lines; index reset by the flag; blocks with index ≥ 40 and no flag are **dropped** | index × 4 lines; reset by the flag; **wraps** mod 40 without a flag | sequential | untested |
| Embedded knowledge of a frame | a full 240×160 RGB5A3 frame at `0x801B45A0` (the AGB boot / no-cartridge screen), compared block by block when enabled | two 40-entry per-block checksum tables (`0x800B0E78`, `0x800B0F18`) of two frames | — | **the physical block equals block 0 of both** (§6) |

## 2. Start-up Disc (`main.dol`)

### 2.1 Acquisition (per HSP interrupt, slot 5 = source 0x0100)

`FUN_8008ed68` (slot 5 callback) → `FUN_8008a480(&cur_video_buf, done_cb)`:

```text
idx := (idx + 1); if idx > 39: idx := 0                       # byte at r13-0x7064, ring index 0..39
buf := ring[idx]                                              # ring table DAT_801B3310[40] of pointers
if buf != 0:                                                  # slot still owned by the consumer
    cur_video_buf := 0; return false                          # the block is NOT read (dropped)
buf := 0x801E4A80 + idx * 0xF00                               # 40 × 0xF00 = 0x25800 bytes of ring storage
ring[idx] := buf
DCInvalidate(buf, 0xF00)                                      # FUN_800687dc
dma_done_callback := done_cb                                  # FUN_8008aca8 (FUN_8008edac)
AR_DMA(buf, base + 0x100000, 0xF00, dir=1)                    # FUN_80089c3c: MMADDR/ARADDR/CNT with bit 15
cur_video_buf := buf; return true                             # true suppresses the handler's immediate re-arm
```

DMA-done handler `FUN_8008b14c`: clear CSR bits (`& 0xFF77`), run the
callback, re-arm the IRQ register when nothing is pending. Completion
callback `FUN_8008edac`: `DCInvalidate(buf, 0xF00)`; `OSSendMessage(queue
0x80258DD8, buf)`.

### 2.2 Consumer thread `FUN_8008ede8` (created by `FUN_8008e994`)

```text
fill the 5 frame buffers fb[0..4] (0x12C00 bytes = 240 × 160 × 2 each) with FILL   # FILL = halfword at r13-0x7838
fb_cur := 1; blk := 0
drain the queue (41 entries); clear the ring table (FUN_8008a61c: 40 × 4 bytes := 0, idx := 0)
loop:
    buf := OSReceiveMessage(queue, BLOCK)
    if FUN_8008a588(*(u16 *)buf):                             # == (halfword0 >> 7) & 1  → bit 7 of BYTE 1
        blk := 0                                              # frame start
    if blk < 40:
        dst := fb[fb_cur] + blk * 0x780                       # 0x780 = 4 lines × 240 px × 2 bytes
        FUN_8008efb4(buf, dst)                                # convert (2.3)
        if compare_enabled: FUN_8008f080(dst, REF + blk * 0x780, blk)   # compare with the embedded frame (2.4)
    FUN_8008a590(buf)                                         # free the ring slot (ring[i] == buf → 0)
    blk := blk + 1
    if blk == 40: fb_cur := (fb_cur + 1); if fb_cur > 4: fb_cur := 0
```

Consequences (F code): the vertical position of a block is `blk × 4` lines;
`blk` is reset only by the flag; after 40 blocks without a flag the extra
blocks are dropped (not converted) until the next flag; the frame buffer
advances after the 40th block; there is no repeat of a missing block. On
stop/reset (`FUN_8008ec34`, from `FUN_8008b1ac` / `FUN_8008bdb0`) the Disc
injects a synthetic frame through the same queue: one dummy block whose
**first halfword was OR-ed with 0x0080** (bit 7 of byte 1 — the flag as the
Disc's own predicate reads it) followed by 39 all-zero blocks (the two dummy
blocks live at fb base + 0x5DC00 / + 0x5EB00). Earlier notes in this
project that said "byte 0 |= 0x80" and "frame buffer stride 0x25800 =
240×160×4" were wrong: the halfword OR sets byte 1, and 0x25800 is the
40-block raw ring; the frame buffers are 0x12C00 (16-bit pixels).

### 2.3 Conversion `FUN_8008efb4(src, dst)` — raster block → GX 4×4 tiles

```text
for col in 0..59:                                             # 60 groups of 4 pixels = 240 pixels
    p := src + col * 16                                       # 4 pixels × 4 bytes
    for row in 0..3:                                          # the 4 lines of the block
        for k in 0..3:
            b := p + k * 4                                    # one pixel word b[0] b[1] b[2] b[3]
            dst[k] := (b[3]) | FILL | ((b[1] << 8) & 0xFFFF)  # from `(u16)(b3) | FILL | (u16)(((u32)hw0 << 9) >> 1)`
        dst := dst + 4 halfwords
        p := p + 960                                          # 0x1E0 halfwords = next line of the block
```

So (F code): the source is **raster**, 240 pixels of 4 bytes per line, 4
lines, line stride 960 bytes; the 16-bit pixel is **byte 1 (high) and byte 3
(low)**; bytes 0 and 2 are never read; the output is a GX **4×4 tiled
16-bit texture** (16 texels = 32 bytes per tile, 60 tiles per 4 lines =
0x780 bytes, 40 × 0x780 = 0x12C00 per frame). FILL is OR-ed into every
pixel; the presenter (`FUN_80009044`) creates the frame textures with
`GX_InitTexObj(obj, fb, 240, 160, 5 = GX_TF_RGB5A3, CLAMP, CLAMP, no mipmap)`
(three objects for the three most recent frames, two TEV stages), and the
embedded reference frame has bit 15 set in all 38400 halfwords, so FILL =
0x8000 (C: inferred from the format and from the comparison in 2.4, which
could never succeed otherwise): **RGB5A3 with bit 15 = 1 is 5-5-5 RGB with
R in bits 14–10**. No TEV swap-table call with non-identity arguments was
found in the presenter; the plain repack is drawn as-is.

### 2.4 Embedded reference frame and comparison `FUN_8008f080`

`REF = 0x801B45A0`, 0x12C00 bytes, tiled RGB5A3, immediately before the
frame-buffer pointer table (`DAT_801C71A0`). Decoded (locally, never
reproduced in this repository) it is the AGB boot / no-cartridge screen:
white everywhere except lines 56–100 (blocks 14–25), columns 39–201, which
hold the "GAME BOY" logotype and "Nintendo®" in one main color `0x3019` (+
0x8000) with 42 anti-aliasing shades. Under the RGB5A3 reading that color is
R = 12, G = 0, B = 25 of 31 — the indigo of the real boot logo; under the
GBA-native order it would be crimson (R = 25, B = 12). The comparison: each
converted block is compared halfword by halfword (0x3C0 = 960 halfwords)
with `REF + blk × 0x780`; a run of 40 consecutive matches sets a flag
(r13-0x6FB7) — the Disc detects "the AGB is showing its idle screen".

## 3. GBI Standard (`gbi-unpacked.dol`)

### 3.1 Service thread `FUN_8000BF30` (video part)

```text
read IRQ (32 B at 0xD00000, vote of offsets ≡ 1 / ≡ 3 mod 4) → pending
if pending & 0x0400: ARQ read AUDIO 0x800000 → 0x8017A320, 0x1000, callback FUN_8000B75C
if pending & 0x0100: ARQ read VIDEO 0x100000 → 0x80179420, 0xF00,  callback FUN_8000A8E0   # the callback touches no data
… sync 64-byte write KEYPAD + IRQ := pending | 0x8000 (FIFO behind the reads: the blocks are in memory) …
if pending & 0x0100:
    src := 0x80179420
    if (*(u32 *)src & 0x80800000) == 0x80800000: blk := 0; signal(frame)       # bit 7 of byte 0 AND of byte 1
    else if blk == 0: signal(frame)
    dst := FB[fb] + blk * 0x780                                                # FB[3] of 0x12CC0 bytes (triple buffer)
    sum := 0
    for it in 0..239:                                                          # 240 × 4 pixels = 960 pixels
        w0..w3 := 4 source words
        d0 := (b1(w0) << 24) | (b3(w0) << 16) | (b1(w1) << 8) | b3(w1)          # pixel = byte 1 : byte 3
        d1 := (b1(w2) << 24) | (b3(w2) << 16) | (b1(w3) << 8) | b3(w3)
        dst[0], dst[1] := d0, d1; dst += 8 bytes                               # linear 16-bit raster, 480 bytes per line
        sum := sum + d0 + d1 (64-bit; stored as low32 + carry count)
    checksum[fb][blk] := sum                                                   # at FB + 0x12C00 + blk × 4
    timestamp[fb] := gettime()                                                 # FB + 0x12CA0
    if blk == 39:
        frames := frames + 1
        post FB[fb] to the render queue (r13+0x18C) and, if accepted, to the writer queue (r13+0x448); fb := (fb + 1) % 3
        compare checksum[0..39] with table A (0x800B0E78) or table B (0x800B0F18) → key injection (boot-screen automation)
    blk := (blk + 1) % 40
IRQ := 0                                                                       # re-arm, last device access
```

### 3.2 Renderer `FUN_80003444` (video part)

Receives FB from the render queue, then for each of the 40 groups of 4
lines and each of the 60 groups of 4 pixels writes 8 words = one **4×4
RGB5A3 tile**, each word `| 0x80008000` (bit 15 forced in both pixels),
reading the 4 linear rows (stride 0x1E0 = 480 bytes) of the 16-bit frame.
The screenshot writer (`FUN_8000FACC`, PNG 240×160, color type 2) converts
each 16-bit pixel as `R = bits 14–10, G = bits 9–5, B = bits 4–0` (each
scaled by 8). Both paths therefore read the GBP pixel as **R high, B low**,
exactly like the Disc's RGB5A3 texture.

### 3.3 Frame checksum tables

Two 40-entry tables of per-block checksums (the `sum` above). Table A
(`0x800B0E78`) has content in blocks 14–25 and table B (`0x800B0F18`) in
blocks 12–19; every other entry equals the checksum of an all-white block
without the flag, and entry 0 of both equals the checksum of an all-white
block **with** the flag. Table A's layout (blocks 14–25) is the layout of
the Disc's embedded frame (§2.4): the same idle screen, recognized by two
independent programs.

## 4. Dolphin (`HSP_DeviceGBPlayer.cpp`, auxiliary)

`PrepareScanlineData`: every 4 GBA scanlines, 960 pixels in raster order
converted with mGBA's `M_RGB8_TO_RGB5` into `m_scanlines[i]`; `scanline[0]
|= 0x8000` when the scanline index is 0 (frame start). `Read(Video)`: per
32-bit word `b0 = b1 = color >> 8`, `b2 = b3 = color & 0xFF` (`hh hh ll
ll`). The video IRQ is scheduled on the audio IRQ phase ("Sending
separately timed video IRQs breaks the game"). The color order of the
model depends on mGBA's 32-bit color format: with mGBA's default
(`0x00BBGGRR`, red in the low byte) the macro yields the GBA-native order
(bits 0–4 R) — the **opposite** of both references. Not verified here
(mGBA's headers are not in the sparse checkout); flagged as a Dolphin
divergence to check by screenshot, never as hardware truth.

## 5. Exact predicates and the logger

| Source | Input | Test | Meaning assigned |
|---|---|---|---|
| GBI | big-endian u32 at block offset 0 | `(w & 0x80800000) == 0x80800000` | first block of a frame: block index := 0 |
| Disc | big-endian u16 at block offset 0 | `(hw >> 7) & 1` | same |
| Dolphin | pixel 0 of the block | `|= 0x8000` on the first 4 lines of a frame | sets bit 7 of bytes 0 and 1 after doubling |
| Open-GBP logger (`gbp_avblock_summarize`) | `first_word` = bytes 0..3 big-endian | `(first_word & 0x80800000) == 0x80800000` | `gbi_frame_start` — **identical to GBI's** |

The physical block's first word `FF FF FF FF` satisfies both predicates
(bit 7 of bytes 0 and 1); `first_word = FFFFFFFF` and `gbi_frame_start = 1`
are consistent, not contradictory: the predicate is a mask test, not an
equality with `0x80800000`.

**GBP-VIDEO-001 records both predicates per VIDEO block, separately, from
the raw first four bytes** (`raw_first4[4]`, kept verbatim in the record
and in the `OGBPSEQ1` sidecar next to the raw block):

```text
gbi_frame_start  := (u32_be(raw_first4) & 0x80800000) == 0x80800000      # bit 7 of byte 0 AND of byte 1
disc_frame_start := ((u16_be(raw_first4[0..1]) >> 7) & 1) != 0            # bit 7 of byte 1
flags_agree      := gbi_frame_start == disc_frame_start
```

`gbi ⇒ disc` by construction (GBI's condition contains the Disc's), so the
possible outcomes are (0, 0), (1, 1) and the informative one, disc = 1 /
gbi = 0: byte 1 carries the bit and byte 0 does not — the byte where the
observed variability lives (§7). The offline tool builds one boundary list
per predicate (positions and intervals) and reports both; neither is chosen
as the physical truth, and the raw bytes are never corrected. A future
`gbp_avblock` field `disc_frame_start` mirrors the logger's existing
`gbi_frame_start`.

## 6. The physical block against the references

GBP-HW-058: 3840 bytes, 954 words `7F 7F FF FF`, first word `FF FF FF FF`,
five words `FF 7F FF FF`. Read as the references read it (bytes 1 and 3):
960 pixels of `0x7FFF` with bit 15 set on pixel 0 only — the top four lines
of a white screen with the frame-start flag. Computed checks (host, 2026-09-16):

- GBI checksum of the physical block = `0x7F0FFF10` = entry 0 of table A =
  entry 0 of table B = the checksum of an ideal all-white flagged block.
- Disc conversion (§2.3, FILL 0x8000) of the physical block = block 0 of
  the embedded reference frame, byte for byte (0x780 bytes); with FILL 0 it
  is not (which is how FILL was inferred).

Status: **C (physical bytes ↔ two independent embedded references)** for
"the physical block is the first block of the idle screen as both
references model it". Not claimed: the geometry (a uniform block cannot
show it), the rest of the screen, the color order (white is white in any
order). The five byte-0 exceptions are invisible to both references.

## 7. Positional statistics of the two physical blocks (GBP-HW-061)

VIDEO: 5 deviations from the uniform pattern, all with the extra bit 0x80,
all at offset ≡ 0 mod 4 (byte 0 of a pixel word), at in-line offsets 4, 20,
8, 8, 8 of their 32-byte units (absolute 0x0A4, 0x294, 0x2E8, 0x6A8, 0x908),
never at bytes 1–3. AUDIO: 127 non-zero bytes, 123 at offset ≡ 0 mod 32
(the first byte of a 32-byte unit: `01` ×121, `11` ×2), four isolated `01`
at ≡ 0 mod 4 (offsets 0x08C, 0x8A8) and ≡ 2 mod 4 (0x49E, 0xCBA). In the
same run the 32-byte register reads carried byte-0 extras `0x01`, `0x11`,
`0x12`, `0x13`, `0x03`, `0x10`, `0x43` and offset-2 deviations (GBP-HW-059).
Reading: (a) real block data, (b) an artifact of the read/DMA path in the
byte positions the references discard, (c) unknown — the positions (only
bytes 0 and 2 of a word; byte 0 of most 32-byte units in AUDIO) and the
values (the run's own extras) favor (b), but nothing proves it; formally
**U** (U-GBP-029). Raw bytes stay the authority; no byte is ever
"corrected"; the next capture tests reproducibility across blocks.

## 8. What GBP-VIDEO-001 must capture (derived requirements; specification in HARDWARE_TESTS.md)

1. A bounded sequence of VIDEO blocks, target 88 (the array's capacity):
   under the references' period of 40 (a working hypothesis, not a
   requirement) the first true predicate can come as late as the 40th
   block and the next one 40 later, so 80 blocks guarantee one complete
   boundary→boundary interval only if the period is 40, and 88 leaves 8 of
   margin; 48 would guarantee at most one boundary. A **complete frame
   interval is observed only when two consecutive true predicates exist in
   the sequence**; its length is the measurement (N ≠ 40 is a result, not a
   failure; 0 or 1 boundary leaves that objective unmet with the capture
   still operationally valid).
2. Per block: the raw 0xF00 bytes, `raw_first4`, both predicates and their
   agreement, the cycle it came from, the pending value of that cycle, and
   time-base reads around its DMA.
3. Per cycle: the pending value (the source pattern 0x0400 / 0x0100 /
   0x0500 …), timestamps of cause, unmask, entry, read, drains, ACK and
   re-arm, the ISR record fields, the main W1C count.
4. AUDIO drained every time it is pending (the references never leave it),
   raw for the first eight successful drains and the last successful one
   (ping-pong buffers; the last valid capture is never overwritten by a
   failed drain), summarized for all.
5. Operational success separated from content: the probe's status comes
   only from SERVICE, CAPTURE and RESTORE (`ok_video_sequence_capture`,
   `ok_target_not_reached_delivery_cap`, `ok_target_not_reached_runtime_cap`,
   `observation_no_next_cause`, or a failure); the comparison with the
   idle screen of §2.4 / §3.3 is an OFFLINE oracle (`matches_disc`,
   `matches_gbi`, `first_mismatch_block`, `first_mismatch_offset`,
   verdict full / partial / mismatch / insufficient_data) — bytes that do
   not match the embedded frame are new evidence, never a transport
   failure. Whether a byte-for-byte match of a complete idle frame is
   enough to raise the color-order status is decided after the run.

## Experiment status

**GBP-VIDEO-001 — PHYSICALLY EXECUTED 2026-09-16** (build `video-0001`, commit
`6930dde`). Result `ok_video_sequence_capture`, 209 cycles, 88 VIDEO and 144
AUDIO blocks, target reached, restore ok. What it settled about this document:

* **The byte picking is right.** Transforming our physical blocks by byte 1 :
  byte 3 and computing GBI's per-block checksum reproduces the references'
  all-white entries exactly: `0xFF0FFF0F` (no flag) and `0x7F0FFF10` (with the
  flag) — table A entries 1 and 0. A wrong geometry or a wrong byte pick could
  not produce those values.
* **40 blocks per frame is CORROBORATED by hardware.** Both predicates agree on
  all 88 captured blocks and give one complete boundary-to-boundary interval of
  exactly 40 blocks (seq25 → seq65, 16.794 ms, 59.547 Hz in that run).
* **Both frame-start predicates agreed everywhere** — 0 divergences over 88
  blocks. §2.2 and §3.1 describe the same physical event on this data.
* **The embedded frames are the logotype screen; the hardware showed white.**
  Aligned on the complete interval, the capture matches the references at every
  block they define as white and differs at exactly blocks 14..25 (Disc and
  table A) and 12..19 (table B) — precisely the logotype blocks of §2.4 and
  §3.3. The divergence identifies a different AGB state (U-GBP-031), not a
  fault, and independently confirms the table layouts described here.
* **Colour is still not settled.** The captured frame is uniform white, which
  carries no colour information. §2.3's R-high reading stays CORROBORATED and
  needs a known-colour source.

The pre-execution status paragraph follows, kept for the history: implemented
(2026-09-16) and NOT physically executed: `poc/gbp-video-capture-probe/`,
`docs/research/HARDWARE_TESTS.md` "Planned tests — GBP-VIDEO-001". Nothing in
this document has been promoted by that implementation; every claim here keeps
the status `docs/research/EVIDENCE.md` gives it. In particular **40 blocks per
frame stays a HYPOTHESIS** drawn from the references' constants, the colour
naming stays CORROBORATED, and the physical block format stays what the single
GBP-AV-SERVICE-001 block showed.

The offline oracle `tools/avseq.py` implements §3.1's per-block checksum (the
repacked byte 1 : byte 3 words accumulated in 64 bits, stored as the low 32
bits plus the carry count) and reproduces `0x7F0FFF10` for the physical block
of GBP-AV-SERVICE-001 — the value §6 records as entry 0 of both tables. Read
from the private inputs at run time, table A carries content in blocks 14–25
and table B in 12–19, and the embedded frame at `0x801B45A0` begins white:
three independent confirmations of §2.4 and §3.3 from the binaries themselves.
