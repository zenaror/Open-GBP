# Game Boy Player — Detection, Start, IRQ Service and Stop (preliminary)

Sequences reconstructed from the Start-up Disc (DISC) and Game Boy
Interface (GBI), cross-checked against Dolphin. Register names are the
working names of `REGISTERS.md`. Status letters as in `REGISTERS.md`;
evidence ids in `docs/research/EVIDENCE.md`. Not yet verified on
hardware by this project.

Function addresses are given so the analysis can be reproduced with
`tools/ghidra/` on the private binaries; they are not part of the
documentation contract.

## 1. Detection (safe, read-mostly)

```text
1. Ensure the ARAM DMA engine is idle:      0xCC00500A bit 9 == 0 and bit 5 == 0   (DISC 0x80089c1c/0x80089c2c)
2. Read the internal ARAM size code:         0xCC005012 bits 0-2  →  base (retail 0x01000000)
3. Program the expansion size code:          0xCC005012 bits 3-5 := 3               (DISC 0x80089b60(0x1000000); GBI 0x8001123c)
4. TEST handshake at base + 0x000000:
      DISC: for p in C3, 3C, FF, 00: write 32×p ; read 32 ; require byte[1] == ~p           (0x8008ae3c, `lbz r3,13(r1)` with the buffer at r1+12)
      GBI : for p in C3, FF:  write 32×p ; read 32 ; vote each bit over the 32 bytes → b ; require b == ~p ;
            write 32×b ; read ; vote ; require == p                                          (0x80011c94, 0x80015b08)
   Hardware 2026-09-14 (GBP-HW-003/007/010): with the GBP attached, bytes 1–31 == ~p in 8/8
   handshakes (byte 0 wrong in 3/8) and both official checks pass 8/8; with the GBP removed
   every read is C0×32 and both fail 8/8. A whole-block comparison fails 3/8 with the GBP.
   DMA completion is identical in both cases and is NOT a presence signal (GBP-HW-008).
   Open-GBP policy: src/gbp/gbp_detect.h — PRESENT only if every handshake completed and
   passed BOTH criteria; transport success is reported separately.
   Any mismatch ⇒ "no Game Boy Player" (DISC error code 5, GBI "Game Boy Player not detected").
```

Status **C**, first hardware confirmation on 2026-09-14 (with and without
step 3 — see GBP-HW-002/005 for what step 3 changes). GBI additionally requires that libogc's `__ARCheckSize`
found **no** ARAM expansion (`AR_GetSize() <= AR_GetInternalSize()`),
which is what happens when the probes at 16 MB hit the GBP's inverting
TEST register. DISC does not run a size probe of its own.

Note for Phase 3: step 4 is the first physical experiment. It writes only
the TEST block, which both official and homebrew software write first.

## 2. Interrupt plumbing

```text
DISC (SDK):   OSSetInterruptHandler(6 /*DSP ARAM DMA*/, NULL)         // DMA completion is polled instead
              OSSetInterruptHandler(26 /*PI HSP*/, hsp_handler)       // 0x8008af08
              periodic alarm every ~5 ms (200 Hz)                     // 0x8008b1ac, period (bus/500000*5000)>>3 ticks
GBI (libogc): IRQ_Request(IRQ_PI_HSP = 26, raw_handler)               // 0x8000b400: writes 0x2000 to PI, wakes a thread
              __UnmaskIrq(IRQMASK(26) = 0x20)
```

PI interrupt number 26 ↔ cause bit 13 (0x2000) is confirmed in the DISC
dispatcher (0x80069ff0), libogc `irq.c`, YAGCD 6.1.5.2 and Dolphin. **C**.

## 3. Start sequence

DISC (0x8008bf84 "start", then 0x8008c26c "run"):

```text
 1. clear IRQ counters/ring buffers
 2. install DMA-done handler (0x8008b14c) on OS interrupt 6 and unmask PI HSP (OS mask bit 0x20)
 3. read IRQ
 4. compute enable/disable masks from the callback table (odd bits, see REGISTERS §4)
 5. write IRQ := (read & ~enable) | disable
 6. read CONTROL
 7. write CONTROL := value | 0x04
 8. write CONTROL := value & ~0x10                (unmask device IRQ)
    … later, when the caller starts the AGB:
 9. write CONTROL := read | 0x08                  (state 2 = running)
10. prime the VIDEO ring (dummy first block with the frame-start flag) and the AUDIO ring
```

GBI (worker thread 0x8000bf30):

```text
 1. write KEYPAD := 0
 2. read CONTROL
 3. write CONTROL := (read & 0xE7) | 0x0C          (set 0x04|0x08, clear 0x10 and 0x08's old state)
 4. IRQ_Request(26, handler); __UnmaskIrq(0x20)
```

Dolphin resets the emulated GBA when bits 0x04|0x08 go from 0 to non-0.
Status **C** for the bit usage; the physical meaning of 0x04/0x08 (Dolphin
calls them 3V and 5V) is **H**.

## 4. IRQ service (per HSP interrupt)

DISC handler 0x8008af08:

```text
 1. write IRQ := saved_mask | 0x8000
 2. PI ack: 0xCC003000 := 0x2000
 3. read IRQ  → pending
 4. if pending & 0x0555:
      write IRQ := pending                          (acknowledge sources)
      write KEYPAD := current pad state
      read CONTROL → status flags
      for each source bit with a callback: call it
        bit 0x0400 (audio): read AUDIO block 0x1000 into the next of 70 ring buffers
        bit 0x0100 (video): read VIDEO block 0xF00 into the next of 40 ring buffers
        bit 0x0040 (serial): serial-operation completion
        bit 0x0010 (sleep): CONTROL |= 0x10, state := 3
        bit 0x0004 (game pak): stop sequence, video reset
        bit 0x0001: user callback
 5. write IRQ := saved_mask                          (unless a callback asked to keep it masked)
```

GBI thread loop (after the raw handler acked PI and signalled it):

```text
 1. read IRQ → pending (bytes 0x1D/0x1F)
 2. bit 0x0400 → ARQ read AUDIO 0x1000 ; bit 0x0100 → ARQ read VIDEO 0xF00 ; bit 0x0040 → ARQ read SIODATA 0x20
 3. bit 0x0010 (sleep) → write KEYPAD := 0x0304 (L+R+Select)
 4. one 64-byte write at base+0xCFFFE0: KEYPAD := pad state, IRQ := pending (ack)
 5. one 64-byte read  at base+0x4FFFE0: CONTROL, SIOCTL
 6. optional SIODATA write from a message queue, then 64-byte write of CONTROL + SIOCTL
 7. write IRQ := 0
```

Both drivers therefore: acknowledge by writing back the pending bits,
refresh KEYPAD on every interrupt, and read CONTROL every interrupt.
Status **C**.

Timing model (Dolphin, **H**): AUDIO IRQ at 4096 Hz; VIDEO IRQ every 4
scanlines but aligned to the audio tick ("sending separately timed video
IRQs breaks the game — I think the IRQs can't be cleared fast enough").
Dolphin also ships `UGP.ini` with a 1.25× CPU overclock "to work around
sporadic audio/video stream failures", which matches the DISC watchdog
below.

## 5. DISC watchdog (periodic alarm, 200 Hz)

```text
- keep 50-entry ring buffers of the video and audio IRQ counters
- if a counter did not change for 50 consecutive ticks (≈250 ms): set failure flag 0x200 (video) / 0x400 (audio) → stop, state 4
- every tick in the running state: one TEST handshake with a rotating pattern (C3/3C/FF/00); mismatch ⇒ error 5 (GBP removed)
- after a CONTROL bit 0x02 (cart present) 1→0 edge: 61 ticks (~300 ms) debounce before acting
- refresh KEYPAD and read CONTROL each tick when the AGB is running
```

Status **F** (DISC only).

## 6. Stop sequence

DISC 0x8008be04:

```text
 1. require DMA idle
 2. reset AV rings; notify pending serial operation with code 5
 3. mask PI HSP (OS mask bit 0x20)
 4. read CONTROL; write CONTROL := v & ~0x04 ; write := v & ~0x08 ; write := v | 0x10 ; write := v | 0x80
 5. read IRQ; write IRQ := read | saved_disable_mask
 6. PI ack 0xCC003000 := 0x2000
 7. restore the previous OS interrupt-6 handler; state := 0
```

GBI (thread exit): `__MaskIrq(0x20)`, `IRQ_Free(26)`, then
`CONTROL := (read & 0xE3) | 0x10` (clear 0x04, 0x08, 0x10 then set 0x10).
Dolphin stops the emulated GBA when 0x04|0x08 both become 0. Status **C**.

## 7. Internal serial (SIOCTL / SIODATA) — description only

DISC 0x8008c42c runs a small state machine driven from the IRQ handler:

```text
state 0: write SIODATA := word ; read SIOCTL ; write SIOCTL := read | 0x80 ; start a 1 s timeout alarm
state 1: read SIODATA → result, complete
state 2: read SIOCTL → result, complete
state 3: read SIOCTL ; write SIOCTL := read & ~0x08, complete
before any of these: if CONTROL bit 0x20 is set → fail with code 3;
                     if the link is not enabled → write CONTROL := read | 0x80
completion is reported to a caller-supplied callback with codes 0 (ok), 3, 4 (timeout), 5 (stopped), 6
```

GBI reads SIODATA on IRQ bit 6 and writes SIODATA from a queue (purpose
not analyzed). Dolphin's SIO paths are stubs. The AGB-side protocol that
GBATEK documents for the GBP (SIO normal 32-bit, "NINTENDO" handshake,
rumble) is presumably what travels here, but that link is **not
established**. See U-GBP-001..003. Phase 10 starts here — read-only.

## 8. Provenance of every CONTROL bit 0x10 manipulation (2026-09-15, disassembly)

Neutral name: *CONTROL bit 0x10*. No semantics assigned here.

### 8.1 Start-up Disc (`main.dol` sha256 3dd3692f…)

Access primitives (both use the 32-byte staging buffer at `0x801E4A60`
and the DMA routine `0x80089c3c`, transfers of exactly 32 bytes, ARAM
address `base + 0x400000`):

```text
write CONTROL  0x80089edc:  stb  value,0x1F(staging)     ← only byte 0x1F is updated; bytes 0..0x1E
                            DCFlushRange(staging,32)        keep whatever the previous transfer left there
                            DMA MRAM→ARAM 32 bytes, wait (bit 5 of DSP CSR, 1 s timeout)
read CONTROL   0x8008a1dc:  DCInvalidateRange(staging,32); DMA ARAM→MRAM 32 bytes; wait
                            lbz value,0x1F(staging)       ← semantic value = byte 0x1F
```

Every manipulation of bit 0x10 (read-modify-write on that byte):

| Site | Sequence (exact order) | INTMR state at the write | IRQ block | Delay |
|------|------------------------|--------------------------|-----------|-------|
| start `0x8008bf84` (+0x260…+0x2b4) | … `OSUnmaskInterrupts(0x20)` [interrupt 26 = PI HSP] → read IRQ → write IRQ := (read & ~enable) \| disable → read CONTROL → write CONTROL := v \| 0x04 → write CONTROL := v & ~0x10 (`rlwinm r0,r0,0,28,26`) → state \|= 8 | PI HSP **enabled** (unmasked a few instructions earlier, handler `0x8008af08` installed since init) | written (mask programming) just before | none besides DMA completion |
| run `0x8008c26c` | read CONTROL → write := v \| 0x08 → state := 2 | enabled | — | — |
| stop `0x8008be04` (+0xa4…+0x120) | `OSMaskInterrupts(0x20)` → read CONTROL → write v & ~0x04 → write v & ~0x08 → write v \| 0x10 → write v \| 0x80 → read IRQ → write IRQ := read \| disable → PI INTSR := 0x2000 (ack) | PI HSP **masked** just before | written after | none |
| sleep-IRQ callback `0x8008bd50` | read CONTROL → write := v \| 0x10 → state := 3 | enabled (inside the HSP handler) | handled by the caller | — |

INTSR is never read for observation; it is only written (0x2000) to acknowledge.

### 8.2 GBI Standard (`gbi-unpacked` sha256 0b2c44ea…)

Access primitives: byte written replicated over all 32 bytes
(`0x80015d9c`: u32 `bb bb bb bb` ×8, `dcbz`+stores+`dcbf`+`sync`) and
queued through libogc ARQ (`0x8000bea4`); byte read by per-bit majority
vote over the 32 bytes (`0x80015b08`, `0x80011c6c`). In the running loop
CONTROL is written together with SIOCTL as one 64-byte block at
`base + 0x4FFFE0`.

| Site | Sequence (exact order, `0x8000c03c…`) | INTMR state at the write | IRQ block | Delay |
|------|-----------|-----------|-----------|-------|
| thread start `+0x1c…+0x68` | write KEYPAD := 0 → read CONTROL (vote) → write CONTROL := (v & ~0x10) \| 0x04 \| 0x08 (`rlwinm …,28,26` ; `ori 4` ; `rlwimi …,3,28,28`) → `IRQ_Request(26, handler)` → `__UnmaskIrq(0x20)` | PI HSP **masked** (unmasked *after* the write) | not written | none |
| thread exit `0x8000c37c` | `__MaskIrq(0x20)` → `IRQ_Free(26)` → (if not running) read CONTROL → write := (v & ~0x04 & ~0x08) \| 0x10 (`rlwimi` ×3) | masked | not written | none |

### 8.3 Comparison and consequence for the proposed experiment

| Aspect | Start-up Disc | GBI | Same? |
|--------|---------------|-----|-------|
| Semantic value | byte 0x1F of the block | majority vote of 32 bytes | different method, same 8-bit value on hardware |
| Write layout | byte 0x1F only, other 31 bytes stale | byte replicated ×32 | **different** |
| How bit 0x10 is cleared | own write, *after* a separate `\| 0x04` write | in the same write as `\| 0x04 \| 0x08` | **different** |
| PI HSP interrupt when 0x10 is cleared | already unmasked, handler installed | still masked; unmasked afterwards | **different** |
| IRQ block before clearing 0x10 | mask bits written | untouched | **different** |
| Isolated toggle `0x90 → 0x80 → 0x90` | not present | not present | neither |
| Isolated *set* of 0x10 (`v \| 0x10` alone) | yes (sleep callback) | no (combined with clearing 0x0C) | — |
| Delays | none (DMA completion only) | none | same |

Neither reference (official disc or GBI) ever clears bit 0x10 while leaving bits 0x04/0x08 as
they were; both clear it as part of powering the AGB (0x04, 0x08 set),
and they disagree on the order relative to the PI mask and on whether
the IRQ block is programmed first. The experiment "clear only bit 0x10,
observe INTSR bit 13, restore" is therefore **not an operation observed
in known software**. Per the Phase 3 rules it was not implemented;
see DEVLOG 2026-09-15 for the options put to the user.

### 8.4 Experiment selected for GBP-INIT-001 (2026-09-15)

```text
Selected reference for experiment:
GBI Standard control-write semantics

Reason:
write occurs before PI IRQ unmask,
does not require GBP IRQ block writes,
uses a known working implementation,
and is more causally isolated than the Startup Disc start sequence.
```

This choice does not make GBI official software: the Nintendo Game Boy
Player Start-up Disc is the official reference; GBI is an independent
mature implementation. The probe applies only `(v & ~0x10) | 0x0C` with
the GBI byte-replicated layout, keeps PI HSP masked, never writes the
IRQ block, leaves KEYPAD untouched (no dependency found in GBI between
its `KEYPAD := 0` and the CONTROL value), and restores the original
semantic value rather than an inverse expression. See
`poc/gbp-init-probe/README.md` and `src/gbp/gbp_init_probe.h`.
