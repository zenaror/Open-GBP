# Game Boy Player — Detection, Start, IRQ Service and Stop (preliminary)

Sequences reconstructed from the Start-up Disc (DISC) and Game Boy
Interface (GBI), cross-checked against Dolphin. Register names are the
working names of `REGISTERS.md`. Status letters as in `REGISTERS.md`;
evidence ids in `docs/research/EVIDENCE.md`. Hardware confirmations
are cited by `GBP-HW-` id; everything else is static analysis.

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
              OSSetInterruptHandler(26 /*PI HSP*/, hsp_handler)       // 0x8008af08, installed at init while masked
              periodic alarm every ~5 ms (200 Hz)                     // 0x8008b1ac, period (bus/500000*5000)>>3 ticks
GBI (libogc): IRQ_Request(IRQ_PI_HSP = 26, raw_handler)               // 0x8000b400: writes 0x2000 to PI, wakes a thread
              __UnmaskIrq(IRQMASK(26) = 0x20)                         // after the CONTROL transform
```

PI interrupt number 26 ↔ cause bit 13 (0x2000) ↔ software mask 0x20 is
confirmed in the DISC dispatcher (0x80069ff0) and mask routine
(0x80069ca0), libogc `irq.c`/`irq.h`, YAGCD and Dolphin. **F**.

PI side, from the 2026-09-15 audit (GBP-PI-001…003, ENV-IRQ-001/002):

| Item | Statement | Status |
|------|-----------|--------|
| Cause register | `0xCC003000` INTSR, bit 13 = HSP (bit 16 = reset-switch state, unrelated) | F (YAGCD, libogc2, SDK, GBI, Dolphin) |
| Mask register | `0xCC003004` INTMR, bit 13 = HSP; OS interrupt 26 = software mask `0x20` in both the SDK and libogc | F |
| Cause vs mask | INTSR shows a cause whether or not INTMR enables it; INTMR only decides whether the CPU exception is raised | C — all three dispatchers test `cause & mask`; the Disc acknowledges while masked; Dolphin model |
| Clearing | writing 1 to an INTSR bit clears it (W1C); every INTSR write in the four code bases is such an acknowledge (2, 0x1000, 0x2000) | C |
| Physical line | level or latched at the PI; whether W1C clears bit 13 while the GBS-DOL still asserts | **U** (U-GBP-022) |
| Dispatch (libogc2 r2442.094b250, verified in the linked binary) | read INTSR, read INTMR, `cause & mask`, one handler per exception chosen by priority, handler runs with EE = 0, return by `rfi`; no automatic mask, no automatic acknowledge | F |
| Retrigger | if `INTSR & INTMR` still has bit 13 set when the handler returns, the exception is taken again immediately; an unmasked bit 13 with no handler installed loops the same way | F (CPU + dispatcher) |
| Masking under libogc2 | only through `__MaskIrq(IM_PI_HSP)` / `__UnmaskIrq(IM_PI_HSP)`: the library rebuilds the whole INTMR from its shadow masks, so a direct write to `0xCC003004` can be undone by the next PI-group mask change (the SDK does the same through `OSMaskInterrupts`/`OSUnmaskInterrupts` and `0x800000C4/C8`) | F |
| Handler API | `IRQ_Request(26, h)` returns the previous handler; `IRQ_Free(26)` returns it and installs NULL; libogc2 installs none for 26 | F (binary) |

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

GBI (worker thread 0x8000bf30; corrected 2026-09-15, GBP-IRQ-004):

```text
 0. the thread's semaphore is created with LWP_SemInit(&sem, 1, 1)   (0x800113a0, inside the GBP init 0x8001123c)
 1. write KEYPAD := 0
 2. read CONTROL
 3. write CONTROL := (read & 0xE7) | 0x0C          (set 0x04|0x08, clear 0x10 and 0x08's old state)
 4. IRQ_Request(26, handler); __UnmaskIrq(0x20)        (handler first; PI HSP was masked during steps 1–3)
 5. LWP_SemWait(sem) returns at once (count 1 → 0): the FIRST pass of the service loop (§4) runs
    before any interrupt — read IRQ, dispatch on its bits, write KEYPAD + IRQ := read | 0x8000
    (64 bytes at base+0xCFFFE0), read CONTROL + SIOCTL, write IRQ := 0 (32 bytes at base+0xD00000)
 6. only then LWP_SemWait blocks until the raw handler posts the semaphore
```

Steps 5–6 are GBI's programming of the GBP IRQ register; GBP-INIT-002
reproduced steps 2–4 and left the register untouched (§10).

Dolphin resets the emulated GBA when bits 0x04|0x08 go from 0 to non-0.
Status **C** for the bit usage; the physical meaning of 0x04/0x08 (Dolphin
calls them 3V and 5V) is **H**.

## 4. IRQ service (per HSP interrupt)

DISC handler 0x8008af08 (entered from the SDK dispatcher with EE = 0;
every GBP access is a synchronous, polled 32-byte DMA under
`OSDisableInterrupts`; INTSR is never read):

```text
 1. write IRQ := shadowB | 0x8000                 (device — first action; shadowB = mask value built at start)
 2. PI ack: 0xCC003000 := 0x2000                  (W1C)
 3. read IRQ → pending  (byte 0x1D << 8 | byte 0x1F)
 4. if pending & 0x0555:
      write IRQ := pending                        (device — write back exactly the value read)
      keep := pending & (pending ^ (pending >> 1))   (bit i survives only if bit i+1 is 0)
      write KEYPAD := current pad state
      one-shot callback if set (then cleared)
      read CONTROL → status flags (0x8008bcc4 maps them into the mask word)
      pre-callback if set
      slots 0–3: if keep & table[i] and a callback is set: cb(0)
      slot 4 (bit 0x0400, audio): cb(1) if keep & table2[4], else cb(0); a non-zero return suppresses step 6; counter++
      slot 5 (bit 0x0100, video): cb(0); a non-zero return suppresses step 6; counter++
        (slot → source: 0x0001 user, 0x0040 serial, 0x0010 sleep, 0x0004 game pak, 0x0400 audio, 0x0100 video)
 5. post-callback if slot 4 fired
 6. write IRQ := shadowB                          (device — last action, unless suppressed)
 7. return
```

No wait loop and no re-read: several pending sources are served in one
pass, and an entry with nothing in `0x0555` still performs steps 1, 2,
3 and 6. **Acknowledge order: GBP → PI → GBP → GBP** (device write, PI
W1C, device write-back, device re-arm). Do not abbreviate this as "ack
PI". Status **F** (GBP-IRQ-002).

GBI raw handler 0x8000b400 (four instructions):

```text
 1. PI ack: 0xCC003000 := 0x2000
 2. signal the worker thread's wait object
 3. return                                        (no mask change, no DMA)
```

GBI thread loop 0x8000bf30 (the first pass runs before any interrupt
because the semaphore starts at 1; every later pass blocks in
`LWP_SemWait` — no timeout — until the raw handler posts; PI HSP stays
enabled throughout):

```text
 1. read IRQ (32 bytes at base+0xD00000) → pending = vote(bytes ≡1 mod 4) << 8 | vote(bytes ≡3 mod 4)
 2. bit 0x0400 → ARQ read AUDIO 0x1000 ; bit 0x0100 → ARQ read VIDEO 0xF00 ; bit 0x0040 → ARQ read SIODATA 0x20
 3. bit 0x0010 (sleep) → write KEYPAD := 0x0304 (L+R+Select)
 4. one 64-byte write at base+0xCFFFE0: KEYPAD := pad state, IRQ := pending | 0x8000   (device ack)
 5. one 64-byte read  at base+0x4FFFE0: CONTROL, SIOCTL
 6. optional SIODATA write from a message queue, then 64-byte write of CONTROL + SIOCTL
 7. write IRQ := 0
```

**Acknowledge order: PI (raw handler) → GBP (thread)**, with scheduling
latency in between and no protection against a persistent source
beyond the PI W1C. GBI is an independent mature implementation; this
order is GBI's, not Nintendo's. Status **F** (GBP-IRQ-003).

Both drivers therefore acknowledge PI with a W1C of `0x2000`, write the
value they read back into the IRQ register (Disc: `pending`; GBI:
`pending | 0x8000`), refresh KEYPAD on every interrupt, and read CONTROL
every interrupt — but in different orders relative to the PI
acknowledge. Status **C** for the common elements.

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

Step 3 precedes every device access, and step 6 is written with the
mask still off: the Disc acknowledges a cause that may be latched while
masked (GBP-PI-001), and masks PI before touching the device (the order
Open-GBP's teardown copies, §9).

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

### 8.5 GBP-INIT-001 result (2026-09-15, hardware)

With the GBP attached and PI HSP masked, `CONTROL 0x90 → 0x8C → 0x90`
(GBI transform and restore) was accepted and read back; IRQ bytes 1–31
stayed `0x8AAE`; PI INTSR bit 13 stayed 0 in six snapshots up to 340 µs;
byte 0 of both blocks showed a transient bit 6 after each CONTROL write
(GBP-HW-013…016, U-GBP-021). Restoring the expansion code to 0 changed
the CONTROL/IRQ view to `00`/`9090` again (GBP-HW-017). Without the
GBP the gate stopped the probe (`C1`×32, ABSENT). The next GBI
operations (`IRQ_Request(26)`, `__UnmaskIrq(0x20)`) have not been
reproduced.

GBP-INIT-002 (`poc/gbp-init-irq-probe`, build `initirq-0001`, executed
2026-09-15) added the first unmask of PI HSP after this transform, with
a one-shot self-masking handler and the GBP IRQ register read-only: no
IRQ 26 in 2 s, INTMR bit 13 physically toggled, IRQ register `0x8AAE →
0x8FAE` — see §10. The idle-unmask variant (DEVLOG "Option D") was
rejected on 2026-09-15.

## 9. Rules for servicing the HSP interrupt in Open-GBP (from the 2026-09-15 audit)

Consolidated from GBP-PI-001…003, GBP-IRQ-002/003, ENV-IRQ-001/002.
They bind every Open-GBP handler, experimental or not, until U-GBP-022
is answered.

| # | Rule | Basis | Status |
|---|------|-------|--------|
| R1 | Install the IRQ-26 handler (`IRQ_Request`) before any operation that can make the device interrupt and before unmasking; never unmask without a handler | ENV-IRQ-001 consequence 2; Disc installs at init, GBI immediately before unmasking | F |
| R2 | Change INTMR bit 13 only with `__MaskIrq(IM_PI_HSP)` / `__UnmaskIrq(IM_PI_HSP)`; never write `0xCC003004` directly | ENV-IRQ-002 | F |
| R3 | In an experimental handler, re-mask IRQ 26 (`__MaskIrq`) **before** relying on the INTSR acknowledge; treat INTSR after the W1C as an observation, not as the exit condition | GBP-PI-003, U-GBP-022 | binding |
| R4 | The PI acknowledge is `INTSR := 0x2000` (W1C); it has precedent in both references and is CORROBORATED, not a physical FACT | GBP-PI-002 | C |
| R5 | In the first interrupt experiment the unmask happens only **after** the validated CONTROL transform; no idle unmask (decision 2026-09-15) | DEVLOG 2026-09-15 | decision |
| R6 | The GBP IRQ register is read-only until a device-side write is authorized separately; neither reference's stop path depends on a prior device-side ack (both mask PI and set CONTROL 0x10). GBP-INIT-002 showed that leaving the register at its idle value (bit 15 + all odd bits set) also leaves the device's own masks in place: both references write it before waiting (§10), so the next experiment needs an authorized write | GBP-IRQ-002/003/004/005, §6, §10 | decision |
| R7 | Teardown order (idempotent, identical on abort): mask IRQ 26 → CONTROL original → observe PI → INTSR W1C only if bit 13 is set → previous handler back (`IRQ_Request(26, old)`) → original mask state → AR_INFO → final snapshot | Disc stop (mask first, ack last) + GBI exit (mask, free, CONTROL) | decision |
| R8 | A handler does no DMA, no filesystem, no formatting, no allocation, no blocking call; it shares 32-bit `volatile` fields with the main loop, which copies them only after IRQ 26 is masked again | libogc2 handler context (EE = 0, interrupt stack) | decision |

Implementation of these rules for GBP-INIT-002: `src/gbp/gbp_irq_oneshot.h`
(handler body, shared by the real backend and the host mock),
`src/platform/hsp_backend.c` (`hsp_backend_oneshot_isr`, `IRQ_Request`,
`__MaskIrq`/`__UnmaskIrq`), `src/gbp/gbp_init_irq_probe.c` (sequence and
teardown), `tests/mocks/gbp_mock.c` (order/invariant detector),
`tools/isr_audit.py` (static audit of the linked handler).

## 10. GBP-INIT-002 result and the IRQ-register model (2026-09-15)

Physical facts (GBP-HW-021…026, log verbatim in HARDWARE_TESTS.md): with
the GBP present, no cartridge, expansion code 3, CONTROL `0x90 → 0x8C`
(GBI transform), a one-shot handler installed and PI HSP unmasked —
`__UnmaskIrq(IM_PI_HSP)` set INTMR bit 13 and `__MaskIrq` cleared it
(**F**) — no IRQ 26 arrived within 2000 ms and INTSR bit 13 never read 1;
during the window the GBP IRQ register went from `0x8AAE` to `0x8FAE`
(source bits 0x0400 and 0x0100 set; odd bits and bit 15 unchanged) while
CONTROL stayed `0x8C`; `0x8FAE` persisted after CONTROL went back to
`0x90`; under expansion code 0 the view was `00` / `9090` again; every
restore succeeded. The timeout is an operational bound: "no IRQ 26
within 2 s", nothing more.

Model of the 16-bit IRQ register that fits the references and the
hardware (status per element):

| Element | References | Hardware 2026-09-15 | Status |
|---|---|---|---|
| Even bits = sources | GBI dispatches on 0x0400 → AUDIO read 0x1000, 0x0100 → VIDEO read 0xF00, 0x0040 → SIODATA read, 0x0010 → KEYPAD writes; Disc slots {0x0001, 0x0040, 0x0010, 0x0004, 0x0400, 0x0100}, slot 4 → AUDIO read (`0x8008a764`), slot 5 → VIDEO read (`0x8008a480`) | 0x0400 and 0x0100 became set within 2 s of powering the AGB (CONTROL 0x0C set) | source bit → driver action: **F** (code); "audio/video streams of the AGB": **H** |
| Odd bits = paired masks (bit i+1 masks bit i) | Disc tables {…} / {0x0002, 0x0080, 0x0020, 0x0008, 0x0800, 0x0200}; handler filter `pending & ~(pending >> 1)`; start writes 1 for slots without a callback, 0 for slots with one | idle 0x0AAA all set; sources pending under set masks → no PI IRQ | pairing **C**; polarity 1 = masked **H** |
| Bit 15 | Disc: written 1 at handler entry and at stop, 0 at start / exit / DMA done, never tested; GBI: written 1 after each read (`read \| 0x8000`), 0 with `IRQ := 0`, never tested; Dolphin: `IRQ_ASSERTED`, set with any source, cleared by writing 1, drives the line | 1 in every expansion-code-3 read (idle and 0x8FAE), never seen 0 | **two admissible readings, kept apart from the even/odd pairs:** (i) global hold/mask, level-written, 1 = masked; (ii) "any source pending" summary, W1C. Every driver write fits both. **U** which; a masked write of 0 followed by a read-back discriminates them (0 → level, still 1 → W1C) |
| Write semantics | Disc writes full 16-bit words: computed mask levels, pending sources written back as 1 (acknowledge); GBI writes `read \| 0x8000` (acknowledge) then `0` (enable); Dolphin clears the bits written | not tested (register read-only so far) | even bits write-1-to-clear **C** (Disc write-back, GBI write-back, Dolphin); odd bits level-written **C** (Disc computes 0/1 per slot, GBI writes 0); bit 15 **U**. Consequence: **writing back a value read earlier (e.g. 0x8AAE) is not a restore** — it acknowledges whatever source bits it carries; a teardown must use a known stop state instead (Disc stop: `read \| 0x8000 \| masks`) |

What both references do before waiting for an interrupt, and what
GBP-INIT-002 omitted:

```text
Disc  start:  OSUnmaskInterrupts(0x20) → IRQ := (read & ~(0x8000 | odd bits of serviced slots)) | (odd bits of unserviced slots)
              → CONTROL |0x04 → CONTROL &~0x10           from 0x8AAE with all six slots serviced: IRQ := 0x0004
GBI   start:  KEYPAD := 0 → CONTROL (v&~0x18)|0x0C → IRQ_Request → __UnmaskIrq → first pass: IRQ := read|0x8000 (with KEYPAD) … IRQ := 0
GBP-INIT-002: CONTROL (v&~0x10)|0x0C → IRQ_Request → __UnmaskIrq → (IRQ register never written) → no IRQ 26 in 2 s
```

Consequences for an implementation: R6 stands (no IRQ-register write
without authorization), but the next initialization step is exactly
such a write. Decided 2026-09-15: GBP-INIT-003A performs GBI's two
first-pass writes separately, `IRQ := read | 0x8000` (acknowledge) then
`IRQ := 0` (mask/control programming), with PI HSP masked throughout, no
handler and no unmask, snapshots between them and a Start-up-Disc-style
stop (`IRQ := read | 0x8AAA`; GBP-IRQ-006) — HARDWARE_TESTS.md "Planned
tests"; implemented and **executed 2026-09-15** as
`poc/gbp-init-irq-program-probe` (`src/gbp/gbp_initirqa_probe.c`) — result
and updated model in §11. Delivery (handler + unmask) is GBP-INIT-003B,
designed, implemented and **executed 2026-09-15**
(`poc/gbp-init-irq-deliver-probe`, `src/gbp/gbp_initirqb_probe.c`; result
and model in §12, log in HARDWARE_TESTS.md). Writing a previously read value back as a "restore" stays
prohibited. The
read layout in the 0x8FAE state is `hh hh ll' ll` with `ll' = ll | 0x01`
at offsets ≡ 2 mod 4 (U-GBP-025): keep reading offsets ≡ 1 / ≡ 3 mod 4
as both references do.

## 11. GBP-INIT-003A result and the updated IRQ-register model (2026-09-15)

Physical facts (GBP-HW-027…034, GBP-PI-004, GBP-IRQ-007; log verbatim in
HARDWARE_TESTS.md): with the GBP present, no cartridge, expansion code 3,
CONTROL `0x90 → 0x8C` and PI HSP masked for the whole run (INTMR bit 13 =
0, never written), the two writes of GBI's first pass behaved as follows.
**A1** `IRQ := read | 0x8000` (= 0x8AAE) cleared the pending even bit
0x0004 and left the six odd bits and bit 15 at 1 (read 0.47 µs, 50 µs and
500 µs later). **A2** `IRQ := 0` read back 0x0000 for at least 50 ms with
CONTROL unchanged. Then, 50–105 ms after A2, source 0x0400 was set on the
device and **PI INTSR bit 13 read 1 with INTMR bit 13 = 0** (captured,
not delivered; no exception); 0x0100 followed within ≈1 ms. The Start-up
Disc's stop word `IRQ := read | 0x8AAA` (= 0x8FAA) cleared both sources and
re-armed the odd bits and bit 15 (read 0x8AAA); INTSR bit 13 stayed set
after the device sources were gone and one `INTSR := 0x2000` cleared it.
Every restore succeeded. Combined with GBP-INIT-002 (same CONTROL state,
register left at 0x8AAE with sources pending, PI unmasked for 2 s, no
cause): the state that blocked the cause was the device's own IRQ
register, not PI INTMR — CORROBORATED (bit 15 and the odd bits changed
together, so they are not separated).

Model of the 16-bit IRQ register after this run (details and evidence
ids in EVIDENCE.md GBP-IRQ-007):

| Element | Status after 2026-09-15 |
|---|---|
| Even bits = sources, write-1-to-clear | **F** for bits 2, 8, 10 (cleared by writing 1 on hardware); C for 0, 4, 6 (pairing + code) |
| Source functions | F (code): 2 game-pak/stop (Disc slot 3), 8 video (slot 5 / GBI VIDEO), 10 audio (slot 4 / GBI AUDIO); "the physical 0x0400 then 0x0100 were the AGB's audio and video requests": C |
| Odd bits = paired masks, level-written | pairing C; level-written **F** (written 1 → 1, written 0 → 0 for ≥ 50 ms) |
| Polarity 1 = masked, 0 = enabled | **C** (INIT-002: all 1, sources pending, no cause in 2 s; 003A: all 0, next source raised the cause) — not F, bit 15 moved with them |
| Bit 15 | writable and persistent as 0 and as 1 with nothing pending: **F**; "W1C pending summary" **rejected**; "level global hold, 1 = held": **H**, never isolated |
| Bits 12–14 | written 0, read 0; function U |
| PI INTSR bit 13 | captured with INTMR bit 13 = 0, latched, cleared by one W1C 0x2000: **F** (GBP-PI-004); device line level/pulse and W1C-while-asserted: U (U-GBP-022) |
| Write layout | u16 replicated 16× accepted for 0x8AAE, 0x0000, 0x8FAA: F |

Rules R1–R8 (§9) stand. R6 is refined: device-side IRQ-register writes
are authorized in the three forms that have physical evidence —
`read | 0x8000` (acknowledge), `0` (enable all six slots, bit 15 cleared)
and `read | 0x8AAA` (Start-up Disc stop word) — each with the u16
replicated layout; any other value, and any write while PI HSP is
unmasked, needs its own authorization. Writing a previously read value
back as a "restore" stays prohibited (it acknowledges what it carries;
A1 demonstrated exactly that).

Initialization readiness after 003A — established on hardware: presence
detection (four runs), AR_INFO handling (four runs, function still
U-GBP-004), CONTROL transform and restore (three runs), source
acknowledge by W1C (three bits), mask programming (level writes both
ways), a real HSP cause captured at the PI while masked, PI acknowledge
by W1C, the Disc's stop word, full teardown with power cycle. Still
missing before "initialization" can be called functional: (1) delivery
of a real HSP cause to the CPU through IRQ 26 with a handler (never
exercised — INIT-002 unmasked with no cause, 003A had a cause with no
unmask); (2) the acknowledge protocol while the device still asserts
(does the PI W1C clear a cause whose source is still pending? does it
re-latch?), i.e. the remaining half of U-GBP-022; (3) the steady-state
service loop of the references (device acknowledge `read | 0x8000`,
re-enable `0`, KEYPAD written on every service — KEYPAD has never been
written *[true as of 2026-09-15; written on hardware 2026-09-21, §15]*) without losing causes; (4) CONTROL bits 0x04/0x08 (Disc start
`|0x04` then `&~0x10` vs GBI `(v & ~0x18) | 0x0C`, U-GBP-006). Reading
the AUDIO/VIDEO blocks belongs to Phases 4/6. No move to VIDEO before (1)
and (2) are answered; the next experiment, GBP-INIT-003B, was specified
(HARDWARE_TESTS.md "Planned tests — GBP-INIT-003B"), implemented as
`poc/gbp-init-irq-deliver-probe` / `src/gbp/gbp_initirqb_probe.c`,
release-audited on the clean build d3da8cd and **executed 2026-09-15**
(§12). Decisions it fixed, in addition to R1–R8: the handler is installed
only after a latched cause has been observed with PI masked and is
unmasked once; the PI W1C budget is one in the handler (after the mask)
plus at most one in the main loop; the device is acknowledged with `read |
0x8000` under the running CONTROL before any restore, and the run ends
with the Disc stop word. The implementation reuses the executed 003A
module for the whole programming sequence (`gbp_initirqa_run_cause` +
`gbp_initirqa_teardown`), so the physical 003A fixture replays through
the 003B probe verbatim up to the EVENT.

## 12. GBP-INIT-003B result: CPU delivery, one service cycle, the updated model, initialization readiness (2026-09-15)

Physical facts (GBP-HW-035…041, GBP-PI-005, ENV-IRQ-003, GBP-IRQ-008; log
verbatim in HARDWARE_TESTS.md; fixture
`hw-gamecube-gbp-2026-09-15-initirqb-0001.gbpreplay`): the 003A sequence
reproduced (same read-backs; the first cause 0x0400 at the PI 105.286 ms
after A2, 12 µs from 003A's value; 0x0100 within 0.9 ms). With the cause
latched and INTMR bit 13 = 0, the handler was installed
(`IRQ_Request(26)`, previous NULL), the PREUNMASK state was verified
(INTSR bit 13 = 1 twice, INTMR bit 13 = 0 twice, CONTROL 0x8C, IRQ 0x0500,
record clean) and `__UnmaskIrq(IM_PI_HSP)` was called once: **the handler
ran inside the call** (t_unmask + 78 ticks = 1.926 µs, single
observation), saw INTSR `0x00012000` and INTMR `0x000021FA`, masked IRQ 26
with `__MaskIrq` (INTMR `0x000001FA`), wrote one `INTSR := 0x2000` and
read `0x00010000` at once and 148 ticks later; it was entered once. The
main loop re-masked (idempotent), copied the record, and 179.7 µs after
the entry read PI bit 13 = 0 twice with the device still showing IRQ
0x0500 (both sources pending, odd bits 0, bit 15 = 0, CONTROL 0x8C): **the
PI cause did not re-assert after the W1C although the device sources
stayed pending**. The device ACK `IRQ := 0x0500 | 0x8000 = 0x8500` read
back 0x8000 (sources cleared, bit 15 = 1); PI stayed clear; no main-loop
W1C. Teardown: CONTROL 0x90; IRQSTOPPRE 0x8500 (sources set again ≤ 143 µs
after the ACK; no PI cause followed under bit 15 = 1 and CONTROL 0x90 —
not separable); stop `0x8FAA` → 0x8AAA; handler restored; INTMR final
`0x000001FA`; AR_INFO restored; FINAL 00 / 9090. Every restore succeeded.

Model of the IRQ register and of the PI cause after this run (evidence
ids in GBP-IRQ-008):

| Element | Status after 2026-09-15 (003B) |
|---|---|
| Even bits 2, 8, 10 = sources, write-1-to-clear | **F** (cleared when written 1 while pending: A1, stop ×2, ACK) |
| Source functions | F (code): 8 video (Disc slot 5 / GBI VIDEO), 10 audio (slot 4 / GBI AUDIO), 2 game-pak/stop; "0x0400 then 0x0100 are the AGB's audio and video requests": C; requests re-set ≤ 143 µs after an ACK (observation) |
| Odd bits = paired masks, level-written | pairing C; level-written **F**; polarity 1 = masked / 0 = enabled **C** (bit 15 moved with them in every run) |
| Bit 15 | level-written and persistent both ways: **F** (A2 → 0, stop → 1, ACK → 1); "global hold, 1 = held": **H**, never isolated (U-GBP-007); "W1C pending summary" rejected |
| PI INTSR bit 13 | captured while masked, latched, W1C-cleared: **F** (GBP-PI-004); **delivered to the CPU as IRQ 26 on unmask, masked from inside the handler, W1C-cleared while the device sources stayed pending, no re-assert for ≥ 324 µs: F** (GBP-PI-005) |
| Nature of the device line | simple sustained-level model **rejected**; pulse / edge / transient / separate deassert **U** (U-GBP-022, P2) |
| Delivery latency | 78 ticks ≈ 1.93 µs, one observation of this software; not a specification |
| Service cycle | ISR mask → PI W1C → main device ACK `read \| 0x8000` → stop word: one cycle **F**; re-arm `IRQ := 0` and repeated service **never exercised** (U-GBP-027) |
| Write layout | u16 replicated 16×: F for 0x8AAE, 0x0000, 0x8500, 0x8FAA |

Rules R1–R8 (§9) stand and are refined by the run:
- R3 (mask before the acknowledge) is physically confirmed: the handler
  observed INTMR bit 13 = 1 at entry and `__MaskIrq` closed it from
  inside the handler; no second entry occurred.
- R8 (handler restrictions) is confirmed as sufficient for delivery: the
  one-shot body of `gbp_irq_oneshot.h` was delivered, ran and returned
  with the recorded state; EE stayed 0 throughout (ENV-IRQ-003 for the
  unmask side).
- New R9 (acknowledge model): the PI cause is a latched bit cleared by
  one W1C; it does not follow the device sources. A service loop must
  therefore read the device register for the pending sources and must
  not wait for INTSR bit 13 to re-assert; one PI cause may cover several
  device events (to be measured, U-GBP-027).
- New R10 (measurement): the latency of a latched cause is measured from
  a time-base read taken **before** `__UnmaskIrq`; the read after the
  call may already lie after the handler.
- R6 (authorized device writes) now covers four forms with physical
  evidence: `read | 0x8000` (acknowledge, twice), `0` (enable all six
  slots, bit 15 cleared), `read | 0x8AAA` (Start-up Disc stop word,
  twice). `IRQ := 0` **after** an acknowledge (GBI's re-arm) has not been
  written yet and needs its own authorization.

Initialization readiness after 003B — established on hardware: presence
detection, AR_INFO handling, CONTROL transform and restore, source
acknowledge by W1C, local mask programming, a real HSP cause (twice,
≈105.28 ms after A2), PI capture while masked, **CPU IRQ 26 delivery,
handler entry with the delivered state, ISR mask-first, PI W1C inside the
ISR with the device still asserting, no reentry, device source ACK, the
Disc's stop word, handler restoration**, full teardown with power cycle.
The fundamental initialization and interrupt mechanics are established;
the runtime layer that is still missing is the steady state: (1) repeated
service with the re-arm write `IRQ := 0` after the ACK, without losing
causes (U-GBP-027); (2) KEYPAD, never written (both references write it
on every service; Phase 5) *[true as of 2026-09-15; written on hardware 2026-09-21, §15]*; (3) CONTROL bits 0x04/0x08 at runtime
(U-GBP-006); (4) AUDIO/VIDEO block reads (Phases 4/6); (5) the serial and
sleep sources and a cartridge present (Phase 7). The next experiment is
specified as GBP-INIT-004 (HARDWARE_TESTS.md "Planned tests — GBP-INIT-004",
DEVLOG 2026-09-15 "GBP-INIT-004 designed"): a bounded service loop that
adds only repetition and the re-arm `IRQ := 0` to the validated cycle
(three deliveries, two re-arms, CPU masked between cycles, continuation
only on the audio/video sources 0x0100/0x0400 with any other source
ending the run as an observed anomaly, a clean boundary before every
re-arm: acknowledged sources gone at POSTACK and PI bit 13 = 0);
implemented on 2026-09-15 as a dirty build (`initirq4-0001`, DEVLOG
"GBP-INIT-004 implemented"), NOT physically executed, not a physical
candidate, not authorized. Its causal success criterion and the
proposed closure of the fundamental part of Phase 3 with the start of
Phase 4 are stated there.

## 13. GBP-INIT-004 result: a second serviced cycle, the state after the acknowledge, the clean-boundary premise re-examined (2026-09-16)

Physical facts (GBP-HW-042…047, GBP-IRQ-009; log verbatim in
HARDWARE_TESTS.md; fixture `hw-gamecube-gbp-2026-09-16-initirq4-0001.gbpreplay`):
the 003A sequence reproduced a third time (first cause 105.283 ms after
A2, 0x0100 within 0.97 ms); the handler installed once (the multi-cycle
body of `gbp_irq_oneshot.h` behind its generation wrapper), generation 0
published with INTMR bit 13 = 0, PREUNMASK-0 verified, one
`__UnmaskIrq`: **the handler ran inside the call** (89 ticks = 2.198 µs;
second value after 003B's 78), saw INTSR `0x00012000` / INTMR
`0x000021FA`, masked, wrote its one W1C and read PI clear at once and 142
ticks later; slot 0 fired once, no generation error. PREACK-0 209.8 µs
later: sources 0x0500 still pending, PI clear (bit 15 = 0). Device ACK
`IRQ := 0x8500` completed. **POSTACK-0, 26.0 µs after the ACK: IRQ 0x8400
— 0x0400 present, 0x0100 absent, bit 15 = 1, odd bits 0 — with CONTROL
0x8C and PI bit 13 = 0 in two samples;** the 004 clean boundary
(`irq & 0x0555 == 0` before any re-arm) was not met, the run ended with
`anomaly_source_not_cleared`, **no re-arm was written**, and the teardown
restored everything (stop `0x8400 | 0x8AAA = 0x8EAA` → 0x8AAA). No PI cause
was captured from the handler's W1C to FINAL (≥ 0.76 ms) with 0x0400
present, first under bit 15 = 1 / CONTROL 0x8C, then under CONTROL 0x90.

What the run adds to the model (§12 table, deltas):

| Element | Status after 2026-09-16 (004) |
|---|---|
| CPU delivery, mask-first, single W1C, latched PI bit | **F**, second run, different handler body (GBP-HW-043) |
| Delivery latency | 78 and 89 ticks (≈1.9–2.2 µs) in two runs of two builds — observations, not a specification |
| Sources after an ACK without a drain | 0x0400 read 1 again 26 µs after `IRQ := 0x8500` while 0x0100 read 0 (GBP-HW-045): "cleared and re-set within 26 µs" vs "never cleared" **U** (U-GBP-028) |
| Bit 15 | with bit 15 = 1, masks 0, CONTROL 0x8C and 0x0400 present: no PI cause (≥ 140 µs), and none afterwards to FINAL — "hold / gate" **H** observed for the first time without the CONTROL change; "present source ⇒ PI latched" **rejected** under bit 15 = 1 (U-GBP-007) |
| Stop word | `read \| 0x8AAA` validated from a third pre-state (0x8400 → 0x8EAA → 0x8AAA) |
| Re-arm `IRQ := 0` after an ACK, repeated service | **never written; U-GBP-027 stays open** |

**The clean-boundary premise, re-examined against the references
(decompiles re-read 2026-09-16, DEVLOG "GBP-INIT-004 executed").** The
004 design required, before any re-arm, that the acknowledged sources read
0. Neither reference does that:

- GBI thread `0x8000bf30`, per pass: `LWP_SemWait` → read IRQ (`0x80011c14
  (0xD00000, 0x20)`) → for 0x0400 / 0x0100 / 0x0040 post **asynchronous ARQ
  reads** of AUDIO 0x1000 (`0x800000`), VIDEO 0xF00 (`0x100000`), SIODATA
  (`0x8000be48` → `ARQ_PostRequestAsync`, priority 1) → then the **synchronous**
  64-byte write KEYPAD + `IRQ := read | 0x8000` at `0xCFFFE0` (`0x8000bea4` →
  `ARQ_PostRequest`, same priority, waits for completion: FIFO behind the
  reads, so the blocks are drained before the ACK write completes) → read
  CONTROL/SIOCTL → optional SIODATA write → CONTROL/SIOCTL write-back → **`IRQ
  := 0`** (`0x80015da0(buf, 0)` + `0x8000bea4(0xD00000, buf, 0x20)`) as the last
  device access → wait again. No read of the IRQ register after the ACK.
- Start-up Disc handler `0x8008af08`: `IRQ := shadowB | 0x8000` (bit 15 = 1
  first) → `INTSR := 0x2000` → read IRQ → write the value read back (ACK) →
  KEYPAD → CONTROL read → callbacks: the audio slot (`0x8008cdc4` →
  `0x8008a764`) and the video slot (`0x8008ed68` → `0x8008a480`) **start the
  block DMA read** (0x1000 at `0x800000`, 0xF00 at `0x100000`, ring of 70 / 40
  buffers) and return non-zero, which **suppresses the handler's own re-arm**
  (`IRQ := shadowB`, the last statement, skipped when a read is in flight);
  the re-arm is then written from the DMA-done path (bit 15 → 0 "at DMA
  done", GBP-IRQ-002; DMA completion callbacks `0x8008ce3c` / `0x8008edac`
  invalidate the buffer and post it to the consumer's message queue). The
  register is never read again before the re-arm.

Consequence: **both references drain the event's block before the re-arm
and never require the source bits to read 0** — the drain, not a clean
read-back, is their boundary; bit 15 is 1 during the whole service and
returns to 0 with the re-arm. A POC that drains nothing (004) sees the
audio status again 26 µs after its ACK and cannot expect 0. The
requirement "sources == 0 before re-arming" was therefore an artificial
condition of the 004 design, not a hardware or reference property; it is
withdrawn for the successor. Rules R1–R10 (§9, §12) stand; draft R11 for
the runtime (HYPOTHESIS until GBP-AV-SERVICE-001, the Phase 4 entry): the re-arm follows the
consumption of the block(s), as in both references, and the PI cause is
expected to return only after the re-arm (bit 15 → 0) — whether a source
still pending at the re-arm produces the cause at once, at its next event,
or only after a drain is what GBP-INIT-004B (optional, not scheduled)
would isolate; GBP-AV-SERVICE-001 measures the reference case — the re-arm
after the drain — which is the one the runtime needs (DEVLOG 2026-09-16
"next step after GBP-INIT-004 decided").

Initialization readiness after 004: unchanged from §12 plus a second
delivered cycle and the post-ACK state. Still missing for the steady
state: the re-arm after a drained service (GBP-AV-SERVICE-001), then
repeated service, KEYPAD (Phase 5 — written on hardware 2026-09-21, §15), CONTROL
0x04/0x08 at runtime (U-GBP-006), the AUDIO/VIDEO block reads (Phases 4/6,
now known to be the references' boundary before their re-arm). Phase 3 is
**not** concluded by this run. State decided on 2026-09-16: **Phase 3
IRQ core validated; the re-arm validation is carried into the Phase 4
entry (GBP-AV-SERVICE-001); Phase 3 is not formally closed** — it closes
with the first physical service → re-arm → next cause; no intermediate
phase is created. (Closed the same day by GBP-AV-SERVICE-001: §14.)

## 14. GBP-AV-SERVICE-001 result: the drained service, the re-arm and the next cause; Phase 3 complete (2026-09-16)

Physical facts (GBP-HW-048…060, GBP-IRQ-010; log and sidecar verbatim /
described in HARDWARE_TESTS.md; fixture
`hw-gamecube-gbp-2026-09-16-avsvc-0001.gbpreplay` + `-blocks.bin`): the
003A sequence reproduced a fourth time (first cause 105.289 ms after A2,
0x0500 within 0.92 ms); one delivery through the 003B extended one-shot
(72 ticks = 1.78 µs; mask-first, one W1C, no reentry); **PRESVC 0x0500** with
PI clear 188 µs after the entry — the single authoritative read; **AUDIO
0x1000 from index 0x8 and VIDEO 0xF00 from index 0x1 each read by ONE DMA of
the full length** (66.5 / 61.4 µs around the call, CSR 0x0804 before and
after, no timeout, no busy, AUDIO completed before VIDEO started);
**POSTDRAIN 0x0500, PI clear** ≈ 93 µs after the last completion (the drain
alone did not clear the source bits; no cause latched during the drain);
**ACK `IRQ := 0x8500` → 0x8000 at +25.9 µs**, PI clear, no main W1C (004
without a drain: 0x8400 at +26.0 µs); PI clean verified; **re-arm `IRQ :=
0x0000` completed**; **43.9 µs later PI INTSR bit 13 = 1 with IRQ 0x0400**,
INTMR bit 13 = 0, CONTROL 0x8C (REARMPOST B) — the next cause found at once,
never delivered; teardown S4B: CONTROL 0x90, IRQSTOPPRE 0x0500 (0x0100 back
within ≤ 301 µs of REARMPOST), stop 0x8FAA → 0x8AAA, one PI W1C, handler
restored, AR_INFO 0x0043, FINAL 00 / 9090; `restore=ok`, 0 errors, 0
uncertain, `w1c_total=2`. Raw blocks: AUDIO 3969 zero bytes with one
non-zero byte at offset 0 of 123 of 128 lines; VIDEO `7F 7F FF FF` groups
with `FF FF FF FF` first (GBI frame-start predicate true) and five
undoubled groups — recorded, not interpreted (§ EVIDENCE GBP-HW-057/058).

What the run adds to the model (§13 table, deltas):

| Element | Status after 2026-09-16 (AVSVC) |
|---|---|
| Whole-block reads AUDIO 0x1000 / VIDEO 0xF00, one DMA each, same routine as the 32-byte accesses | **F** (one run each; durations are measurements of this probe) |
| Drain then ACK `read \| 0x8000` | **F**: 0x8000 read back 25.9 µs after the ACK, PI clear — the drained pass differs from 004's undrained one at the same distance; no microscopic causality claimed (U-GBP-028 partially closed) |
| Re-arm `IRQ := 0` after a drained, acknowledged cycle with PI clean | **F**: first physical re-arm, completed |
| Next HSP cause after the re-arm | **F** (one run): captured by the PI within 43.9 µs of `IRQ := 0` while IRQ 26 stayed masked; retained-and-released vs new request **U** (non-blocking) |
| Bit 15 | 1 from the ACK to the re-arm with sources 0 and no cause (≥ 203 µs); 0 after the re-arm with a cause within 43.9 µs — "holds / gates" **H** again, still unnamed |
| PI bit 13 | not re-latched by pending sources under bit 15 = 0 (≥ 552 µs, drain included); latched after the re-arm; cleared once at the teardown, nothing sticky — latched **F** (three runs) |
| Stop word from 0x0500 with a latched cause | `0x8FAA → 0x8AAA`, one W1C — **F** (fourth stop-word value) |
| Complete reference-style service cycle (cause → delivery → drain → ACK → re-arm → next cause) | **F** for one cycle; repeated service **U** |

**R11 promoted (2026-09-16, one cycle):** the re-arm follows the consumption
of the event's block(s), as in both references (§13); after the drain the
ACK `read | 0x8000` may leave the sources reading 0, and the next PI cause
returns after `IRQ := 0` (43.9 µs in this run) and is captured while the
CPU is masked. Rule for the runtime: **drain every block named by the
service read → ACK `pending | 0x8000` → verify PI clean (≤ 1 W1C) →
`IRQ := 0` → wait for the next PI cause with the mask closed** (R1–R10
unchanged). Not part of the rule (unknown, non-blocking): whether the
first cause after a re-arm is a retained request or a new event; the
request period; the behavior of a re-arm with an unconsumed block (004B,
optional).

**Initialization readiness after GBP-AV-SERVICE-001:** detection, the
CONTROL transform, the IRQ programming (A1 / A2), delivery, drained service,
ACK, re-arm, next cause and the stop sequence are all physically exercised.
**Phase 3 COMPLETE (2026-09-16)** by the criterion recorded in the DEVLOG
("next step after GBP-INIT-004 decided": first physical service → re-arm →
next cause): IRQ core validated by 003B / 004, service, re-arm and next
cause by this run; the remaining microscopic unknowns (U-GBP-027
investigative sub-items, U-GBP-028, U-GBP-007's mechanism) are
non-blocking. Still missing for the steady state, now Phase 4 and later
work: repeated service and its cadence, block interpretation and frame
timing (GBP-VIDEO-001 direction, DEVLOG 2026-09-16), KEYPAD (Phase 5 — written on hardware 2026-09-21, §15),
CONTROL 0x04/0x08 at runtime (U-GBP-006), audio (Phase 6).

## 15. KEYPAD written on hardware — GBP-INPUT-001, RUN 14 / RUN 15 (2026-09-21)

Until 2026-09-21 every "KEYPAD, never written" above was true: no Open-GBP
build had issued a KEYPAD write in any environment. On 2026-09-21 the
`stream-0014` build wrote it on this project's hardware in two runs
(`docs/research/HARDWARE_TESTS.md` §V7.2; Hardware Issue #21, ingestion
Issue #24): 7 892 and 7 895 completed 32-byte writes at index 0xC, none
failed, none retried (GBP-HW-262), and the written word reached the
cartridge as key presses — the Enhanced Control Checker counted every
pressed button at its own counter, all ten buttons across the two runs
(Question M = PASS; GBP-HW-264, GBP-HW-265). **Where the write sits:** in
Open-GBP it is not part of the interrupt service at all — the runtime writes
KEYPAD from the pump slot that opens after the re-arm (`IRQ := 0`) only while
no cause is pending, on the first pass, on every change of the word and every
5 ms otherwise (GBP-KEY-006); the references write it inside their service
pass (§4, §5). The cycle of §14 is unchanged by the addition: transport,
startup and the display path read clean in both runs (GBP-HW-262). The word
format, the bit assignment with its status — CORROBORATED, not FACT, for the
L/R order, observed through the digital click of a generic third-party pad —
and the runtime's mapping policy are consolidated in `INPUT.md`. Not
established: input latency, the need for the refresh, any other pad or
cartridge, a real game (GBP-HW-265).

**2026-09-21, later the same day — GBP-INPUT-002, RUN 17 / RUN 18 / RUN 16
(`HARDWARE_TESTS.md` §V7.4; Hardware Issue #32, ingestion Issue #33):** the
`stream-0015` build wrote KEYPAD 7 898 / 7 898 / 7 890 times in three more
runs and, for the first time, recorded the word it sent at every change
(GBP-HW-267); joined to the checker's counters, that record made the routing
of every KEYPAD word bit to the AGB's keys — L at bit 8, R at bit 9 included
— a physical FACT (hw, the runs), on two controllers (GBP-HW-270). The status
sentence above ("CORROBORATED, not FACT, for the L/R order") is history from
that point; `INPUT.md` carries the current statement with its scope. Still
not established: input latency, the need for the refresh, pads beyond the two
declared, any other cartridge, a real game.
