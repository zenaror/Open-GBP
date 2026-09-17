# Unknowns

Open questions that require future investigation. Entries are removed only
when answered, and the answer is recorded in `EVIDENCE.md`.

Prefixes follow `EVIDENCE.md`: `U-ENV-` environment/tooling, `U-GBP-`
physical Game Boy Player.

`U-GBP-` entries were opened in Phase 2 (2026-09-13). Priorities: **P1**
blocks Phase 3, **P2** needed before Phase 4–6, **P3** later phases.

---

## U-ENV-001 — Does the physical EXI register block mirror at +0x80?

libogc2 deliberately polls `0xCC00688C + chn*0x14` (see `ENV-EXI-001`).
Not verified on hardware by this project. Low priority: Open-GBP uses
libogc2's EXI driver and does not need the answer unless it implements
its own EXI access.

## U-ENV-002 — CLOSED 2026-09-14

Physical loader behavior with 32-byte-padded DOLs: answered by
SMOKE-HW-001 (Swiss loads and runs the padded DOL). See ENV-HW-001.

## U-ENV-003 — Dolphin behavior on `exit()` from a libogc2 DOL

The smoke test exits to the loader on START. What Dolphin 2606a does when
libogc2's `exit()` runs without a loader stub (hot reset via PI) has not
been observed; the runner terminates Dolphin itself after collecting
evidence. Relevant only if a future POC wants "deterministic exit" as a
Dolphin success criterion.

## U-ENV-004 — Dolphin 2606a Flatpak produced no frame dump

With `-C Dolphin.Movie.DumpFrames=True -C Dolphin.Movie.DumpFramesSilent=True`
(and an isolated `--user` directory whose `Dump/Frames/` is writable),
Dolphin 2606a wrote nothing to `Dump/Frames/` while displaying the smoke
test for 12 s, although `dolphin-emu` links libavcodec/libavformat and
Present.cpp dumps whenever `IsFrameDumping() && m_xfb_entry`. Not
investigated further: `tools/dolphin_smoke.py` captures the render window
from X11 instead (`import -window`), which is sufficient and simpler.
Frame dumping remains available as an opt-in (`--frame-dump`) for whoever
wants to debug it.

## U-ENV-005 — `external/libogc2` checkout is not the commit built into the toolchain image

The image `ghcr.io/extremscorner/libogc2:20260805` ships
`libogc2 r2442.094b250` (libversion.h, Aug 5 2026); the shallow checkout
under `external/libogc2` is `ca03fb7` (2026-09-12) and `094b250` is not
in its history, so a source-level diff is not available. For the IRQ
conclusions (ENV-IRQ-001/002) the container's `irq.o`/`irq_handler.o`
were disassembled and matched the analyzed source. Low priority: pin the
checkout to `094b250` (or record the source of the image build) before
relying on any *other* libogc2 detail at source level.

---

## U-GBP-001 (P3) — Semantics of SIOCTL bits and of the serial IRQ

DISC sets SIOCTL bit 0x80 to start a transfer and clears bit 0x08
afterwards; reads SIOCTL as a "result". Which bits mean busy/done/error,
what the AGB-side transfer looks like (normal 32-bit? JoyBus?), and
whether the GBS-DOL is the SIO master are unknown. Phase 10, read-only
first: log SIOCTL/SIODATA/IRQ while a known cartridge talks.

## U-GBP-002 (P3) — SIODATA read byte layout and width

DISC assembles a 32-bit value from bytes 0x19/0x1B/0x1D/0x1F; Dolphin's
stub repeats the u32. Only a hardware read of a known value can settle
the layout (and whether reads are destructive).

## U-GBP-003 (P3) — Relation between the internal serial path and the physical Link Port

Unknown whether they share the AGB's single SIO (exclusive), whether
CONTROL 0x40/0x80 route between them, and whether enabling the internal
path breaks PicoAdapterGB (regression reference GBP-LINK-001).

## U-GBP-004 (P1, updated 2026-09-15) — What is the function of AR_INFO[5:3] on the GBP path?

Known: with the GBP attached, codes 0 and 3 both complete DMA and pass
the TEST handshake; the CONTROL/IRQ view differs between them
(`00`/`9090` vs `0x90`/`0x8AAE`), now observed in two independent
sequences (GBP-HW-005, GBP-HW-017); without the GBP the code makes no
difference (`C0`/`C1` uniform fills). So the code changes what CONTROL
and IRQ return *when the device is present*. Not known: whether it
selects a decoding of the index bits, a different register set, a
timing regime, or a device state; whether values 1, 2, 4 differ; and
whether writes (CONTROL) under code 0 reach the device at all. Do not
call it "enable". Third observation 2026-09-15 (GBP-HW-025): S4 of
GBP-INIT-002 read `00` / `9090` again right after code 3 → 0 while the same
registers had just read 0x90 / 0x8FAE — the *reproducibility* of the
view change is now CORROBORATED (three runs, three sequences); the
function is still unknown, and every experiment uses code 3 as both
references do. Fourth observation 2026-09-15 (GBP-HW-034, GBP-INIT-003A):
FINAL under code 0 read `00` / `9090` again right after code 3 had shown
0x90 / 0x8AAA. Still not "enable": nothing shows what the code selects.

## U-GBP-005 (P2) — Unused register indices and full mirroring inside a window

Indices 0x2, 0x3, 0x6, 0x7, 0xA, 0xB, 0xE, 0xF are never touched. Reads
of them are probably harmless but unverified; **do not write** them.
Whether every 32-byte slot of a 1 MB window mirrors the register (GBI
uses offset 0xFFFE0, DISC 0x00000) is unverified.

## U-GBP-006 (P2) — Physical meaning of CONTROL bits 0x04/0x08/0x20/0x40/0x80

Dolphin's names (3V, 5V, sleep, link cable, link enable) are not sourced.
Only the usage is known (GBP-CTL-001). Phase 3 can observe 0x20/0x40
read-back with/without a cartridge and link cable; 0x04/0x08 should be
driven only in the documented order.

## U-GBP-007 (P2, updated 2026-09-16 after GBP-AV-SERVICE-001) — IRQ register odd-bit polarity and bit 15

**2026-09-16, GBP-AV-SERVICE-001 (GBP-HW-053/055, GBP-IRQ-010):** the
by-product arrived as predicted and adds the complementary state: bit 15
read 1 from the drained ACK to the re-arm (≥ 203 µs) with **both sources 0**,
CONTROL 0x8C and PI bit 13 = 0 in every sample — no cause; 43.9 µs after
`IRQ := 0` (bit 15 → 0) the register read 0x0400 and the PI had latched a
cause with the CPU masked. So across 004 and this run: bit 15 = 1 with a
present source → no cause (004); bit 15 = 1 with no source → no cause
(here); bit 15 = 0 with a source → a cause (here, 003A/B). Consistent with
"bit 15 holds or gates the request" and equally with "the request is a
new event that happened to occur within 44 µs of the re-arm" (the register
was not sampled in between). Still HYPOTHESIS; not named; non-blocking:
the runtime follows the references (bit 15 = 1 from the ACK to the re-arm,
0 otherwise) and needs no more. Distinguishing the two readings would take
several samples in the first 50 µs after a re-arm — a Phase 4 by-product,
not a scheduled experiment.

**2026-09-16, GBP-INIT-004 (GBP-HW-045, GBP-IRQ-009):** the isolating
state predicted below did occur: 26 µs after the ACK `0x8500` the register
read `0x8400` — source 0x0400 present, odd bits 0, **bit 15 = 1, CONTROL
still 0x8C** — and PI INTSR bit 13 read 0 in two samples; it stayed 0 while
that state persisted (≥ 140 µs, until the CONTROL restore) and afterwards to
the end of the run (≥ 0.76 ms after the handler's W1C, no main-loop W1C in
between). So a present AV source with bit 15 = 1 raised no HSP cause, this
time **without** CONTROL 0x10 in the picture. Compatible readings, none
promoted: bit 15 = 1 holds or gates the external request (the consistent
hypothesis since 003A, now observed without the CONTROL change); source
status and request generation are separate mechanisms (a request needs a
new event or the drain of the block); the re-request condition had simply
not occurred. What is rejected under these conditions: "a present source
implies an immediately latched HSP cause". Still HYPOTHESIS; do not name
bit 15 functionally. GBP-INIT-004B (designed 2026-09-16, now OPTIONAL and
not scheduled) would write `IRQ := 0` in exactly this state and read the
PI with the CPU masked; the scheduled next experiment, GBP-AV-SERVICE-001
(the Phase 4 entry, DEVLOG 2026-09-16 "next step after GBP-INIT-004
decided"), drains the blocks first and re-arms as the references do — bit
15 is observed there only as a by-product (1 from the ACK to the re-arm,
0 after, under a constant CONTROL 0x8C), which is all the runtime needs.

**2026-09-15, GBP-INIT-003B (GBP-HW-039/040, GBP-IRQ-008):** the device
ACK `IRQ := 0x0500 | 0x8000` wrote bit 15 = 1 while two sources were
pending; the read-back 25 µs later showed both sources cleared and bit 15
= 1 with the odd bits 0 (level-written both ways confirmed a third time).
Then, with bit 15 still 1, the sources re-set within ≈143 µs and no PI
cause followed — but CONTROL had been restored to 0x90 (bit 0x10 set) in
between, so bit 15's hold function is again not isolated from CONTROL
0x10. Still HYPOTHESIS, do not name it. The isolating observation is the
state a GBI-style service cycle passes through anyway: sources re-set
under CONTROL 0x8C with bit 15 = 1 and the odd bits 0, before `IRQ := 0`
is written — the next experiment (U-GBP-027) reads the PI in exactly that
state.

**2026-09-15, GBP-INIT-003A (GBP-HW-028…032, GBP-IRQ-007):** the first
authorized writes answered most of this. Even bits 2, 8 and 10 cleared when
written 1 (write-1-to-clear: FACT). The odd bits read 1 after being written
1 and 0 after being written 0, for ≥ 50 ms (level-written: FACT). With all
six odd bits (and bit 15) written 0, the next 0x0400 source raised PI INTSR
bit 13; with all six (and bit 15) left at 1 in GBP-INIT-002 the pending
sources raised nothing in 2 s → polarity "1 = masked, 0 = enabled":
CORROBORATED, not FACT, because bit 15 changed together with the odd bits
in both runs. Bit 15: written 0 it read 0 with nothing pending, written 1
it read 1 with nothing pending → the "W1C pending summary" reading is
REJECTED; "level-written global hold, 1 = held" stays the consistent
HYPOTHESIS, unproven in isolation (an experiment writing the odd bits 0
with bit 15 = 1, or the reverse, would separate them; not scheduled). Do not
name bit 15 functionally yet. Original text kept below for the history.


DISC writes `disable` bits as 1 and `enable` bits as 0 (1 = masked?),
and writes bit 15 with the mask at IRQ entry. Dolphin treats bit 15 as
"asserted" and clears written bits. Needs a hardware read of the register
while an IRQ is pending. Audit 2026-09-15 (GBP-IRQ-002/003): both
references write bit 15 = 1 in their first device-side acknowledge
write (Disc: `shadowB | 0x8000` at handler entry; GBI: `value_read |
0x8000` in the thread), and Dolphin clears whatever bits are written
(`m_irq &= ~value`). Still H. Hardware idle reads `0x8AAE` (bit 15 set)
with CONTROL 0x10 cleared for 228 µs produced no INTSR bit 13
(GBP-HW-013/014), so the Dolphin condition `irq & 0x8000` alone did not
reproduce in that window. **2026-09-15, GBP-INIT-002 (GBP-HW-023/024,
GBP-IRQ-005):** with the register left at its idle value (bit 15 + all
odd bits set) and PI HSP unmasked for 2 s, the source bits 0x0400 and
0x0100 became set and no PI IRQ arrived; the Disc's handler only
dispatches a source whose paired odd bit is clear, its start clears the
odd bits of the slots it services and bit 15, and GBI's first loop pass
writes `read | 0x8000` then `0` before it blocks (GBP-IRQ-004). Pairing
even/odd = source/mask: CORROBORATED; polarity "1 = masked" and bit 15 as
a global mask: HYPOTHESIS, consistent with every observation, to be tested
by the first authorized IRQ-register write. **Field semantics (write
analysis, DEVLOG 2026-09-15 "IRQ-register write/restore"):** even bits
write-1-to-clear (CORROBORATED: Disc writes the pending word back, GBI
writes `read | 0x8000`, Dolphin clears written bits); odd bits
level-written (CORROBORATED: the Disc computes and writes 0/1 per slot,
GBI writes 0); pairs exist only for bits 0–11 (six slots); bits 12–14 are
never used by any driver; bit 15 has two admissible readings — global
hold/mask (level) or pending summary (W1C) — and must stay outside the
pair model until a masked write of 0 is read back. Consequence: writing a
previously read value (0x8AAE) back is **not a restore** — it would
acknowledge the source bits it carries (bit 2 at idle); the only
supported end states are the Disc's stop write (`read | 0x8000 | masks`)
or GBI's "0 + CONTROL stop".

## U-GBP-008 (P2, statically answered for the AV blocks 2026-09-16; physical geometry pending GBP-VIDEO-001) — Read block layout

**2026-09-16, static (GBP-VID-002/003/004, `docs/research/VIDEO_PATH.md`):**
both references read a VIDEO block as 4 raster lines of 240 pixels × 4
bytes (line stride 960 bytes; Disc conversion loop, GBI copy + tiler) and a
pixel word as `hh hh ll ll` of which **only bytes 1 and 3 are consumed** —
the same classes as the register reads; the frame flag is bit 7 of byte 1
(Disc) / of bytes 0 and 1 (GBI). The physical block is consistent (955/960
words doubled, the 5 exceptions in byte 0). The physical geometry (lines
per block, blocks per frame, order) is what GBP-VIDEO-001 captures; the
AUDIO block's layout stays open (U-GBP-012).

Observed for the IRQ window: byte-doubled `hh hh ll ll` per 32-bit word
(GBP-HW-004), matching DISC's and GBI's parsing and contradicting
Dolphin's `hh hh hh ll`. Byte registers (CONTROL) read as a uniform fill.
Still open: SIODATA layout, whether byte 0 of a block is ever reliable
(U-GBP-015), and whether the layout is the same for VIDEO/AUDIO reads.
**2026-09-16, first raw data (GBP-HW-057/058):** the first VIDEO block read
on hardware is `hh hh ll ll`-shaped in 955 of its 960 four-byte groups
(`7F 7F FF FF`, first group `FF FF FF FF`) and not in five (`FF 7F FF FF`);
the first AUDIO block has one non-zero byte at offset 0 of 123 of its 128
32-byte lines and four isolated bytes elsewhere. Whether the exceptions
are content, a transfer artifact or the byte-0 class of U-GBP-021 is
unknown; the layout question for AV blocks is open with data, not closed.

## U-GBP-009 (P3) — Board-revision differences

DOL-GBS-01/10/20, CPU AGB A vs A E, 16 Mb vs 128 Mb RAM. No behavioral
difference is documented anywhere; the user's unit revision is unknown.

## U-GBP-010 (P2) — L/R bit order in KEYPAD

Dolphin maps hi byte bit 0 → L and bit 1 → R (swapped vs GBA KEYINPUT);
GBI's 0x0304 sets both. Phase 5 test with a game that distinguishes L/R.

## U-GBP-011 (P2, re-evaluated 2026-09-16: R-high order CORROBORATED by two references; FACT needs a known-color cartridge) — VIDEO color bit order and exact word content

**2026-09-16, static (GBP-VID-003/006, VIDEO_PATH.md §2.3–2.4, §3.2):** the
Disc draws the 16-bit pixel (bytes 1/3, bit 15 forced to 1) as a GX RGB5A3
texture with no visible channel swap, and its embedded idle-screen frame
shows the boot logo in R = 12 / G = 0 / B = 25 under that reading — indigo,
the logo's real color; the GBA-native order (bits 0–4 R) would make it
crimson. GBI's PNG writer maps bits 14–10 → R. So the hardware pixel is
read by both programs as **bit 15 flag, bits 14–10 R, 9–5 G, 4–0 B** (GX
order, not the GBA order Dolphin's mGBA macro may produce — GBP-VID-007).
CORROBORATED, not FACT: no physical pixel of a known color has been
captured; VIDEO-002 with a known-color cartridge or test ROM closes it.
GBP-VIDEO-001 (no cartridge) checks the raw values of the logo pixels
against the Disc's frame (0x3019 for the main color), which fixes the
bytes but not their color name; if a complete idle frame matches the
Disc's RGB5A3 frame byte for byte, the confidence increase is documented
and the decision whether that is enough for a promotion, or the controlled
cartridge stays necessary, is taken after the run — not anticipated here.

Dolphin uses GBA palette order (R in bits 0–4). GBI's frame-start test only
proves the byte-doubling of the high byte. Phase 4: capture one block
with a known-color test ROM. **2026-09-16 (GBP-HW-058):** the first
physical VIDEO block, no cartridge, is 0xF00 bytes of `7F 7F FF FF` groups
with `FF FF FF FF` first (GBI frame-start predicate true) and five `FF 7F
FF FF` groups; recorded raw, not interpreted as an image or a color. The
bit order stays open; the frame-start flag has its first hardware
occurrence on the first block of the first request. Direction: repeated
captures (block sequence, flag periodicity) before a known-color
cartridge (GBP-VIDEO-001 direction, DEVLOG 2026-09-16).

## U-GBP-012 (P2) — AUDIO block format on hardware

Dolphin's PWM model ("1 bits contiguous and leading", 4096 Hz, 9-bit
samples) comes from making the DISC happy, not from measurement.
Phase 6: capture blocks while the AGB plays a known tone. **2026-09-16
(GBP-HW-057):** the first physical AUDIO block, no cartridge: 3969 of 4096
bytes zero, values `00`/`01`/`11` only, the non-zero bytes at offset 0 of
123 of the 128 32-byte lines (`01` ×121, `11` ×2) plus four isolated `01`.
Not called silence, PCM or PWM; the per-line byte 0 may be payload or the
transfer's byte-0 phenomenon (U-GBP-021) — undecidable from one block.

## U-GBP-013 (P3) — Meaning of the SRAM "GBS" word

libogc2 validates its fields (GBP-SRAM-001); DISC presumably stores the
user's screen/filter settings there. Not analyzed.

## U-GBP-014 (P2, four data points 2026-09-16; first cadence capture designed: GBP-VIDEO-001) — VIDEO/AUDIO IRQ timing on hardware

**Next data: GBP-VIDEO-001 (designed 2026-09-16, HARDWARE_TESTS.md)** —
per-cycle pending values and time-base reads over up to 320 causes / 88
VIDEO blocks give the first VIDEO→VIDEO, flag→flag and AUDIO→AUDIO
intervals and the source pattern (0x0400 / 0x0100 / 0x0500 …) of one run;
reported as measurements, not frequencies. For orientation only (H, GBA
side, not GBP): a GBA frame is 16.74 ms, four visible lines 293.7 µs, the
vertical blank 4.99 ms; Dolphin's audio block rate is 4096 Hz.

**Fourth data point, GBP-AV-SERVICE-001 (GBP-HW-048/052/055/056):** 105.289
ms after A2 (four runs within 16 µs, no cartridge); 0x0100 within 0.92 ms.
After the drained service and the ACK (0x8000 at +25.9 µs, sources clear
for ≥ 203 µs under bit 15 = 1) the re-arm `IRQ := 0` was followed within
43.9 µs by 0x0400 with the PI cause latched, and 0x0100 was back within
≤ 301 µs of that read. **These are the first intervals measured after a
drained service; they bound nothing but themselves:** whether the 43.9 µs
is a retained request released by the re-arm or a new event is
undetermined, and no period of the requests is claimed from one cycle.
The period needs a bounded repeated-service capture (GBP-VIDEO-001
direction).

**Third data point, GBP-INIT-004 (GBP-HW-042/045):** 105.283 ms after A2
(003A 105.273, 003B 105.286 — repeatable to ≈13 µs over three runs with no
cartridge); 0x0100 within 0.97 ms. After the ACK, 0x0400 read set again
26.0 µs later while 0x0100 stayed clear for ≥ 195 µs; in 003B both were
clear at +25.1 µs and both set at ≈+168 µs. Two post-ACK samples in two
runs do not establish a period, a mechanism (re-assertion or never
cleared, U-GBP-028) or the relation between the two sources; no cadence is
claimed. The period of the requests stays unmeasured.

**2026-09-15 (GBP-HW-030/031):** with no cartridge, CONTROL 0x8C and the
device masks written 0, the first 0x0400 (audio) source rose between 50.00
and 105.27 ms after A2 (106 ms after the CONTROL transform) and raised PI
INTSR bit 13; 0x0100 (video) followed within ≈1 ms. One data point; no
period measured (the window ended at the first cause). **Second data
point, GBP-INIT-003B (GBP-HW-035/036/040):** 105.286 ms after A2 (12.4 µs
later than 003A's 105.273 ms), 0x0100 again within ≤ 0.9 ms; after the
device ACK cleared both sources they were set again at most ≈143 µs
later (the interval contains a CONTROL restore, so it bounds the cadence
only from above). The first-cause delay after the transform is
repeatable to ≈10 µs across two runs with no cartridge; the period of the
requests is still unmeasured (U-GBP-027).


Dolphin ties video IRQs to the 4096 Hz audio tick and needs a 1.25×
overclock to keep the DISC's 250 ms watchdog quiet. Real cadence, jitter
and the cost of a missed block are unknown. Phase 4/6: timestamped IRQ
log to SD2SP2.

## U-GBP-015 (P1, updated 2026-09-15) — Byte 0 of a read block carries extra set bits

Confirmed in the third and fourth runs: TEST C3 response `7C 3C…` again
(bit 6); CONTROL byte 0 `98`/`EC`/`AC`; IRQ byte 0 `AA`/`EA`. Byte 0
always has *extra* set bits relative to the rest of the block, never
missing ones. Both references avoid byte 0. The time-dependent part is
now U-GBP-021; the static part (`+0x08` on CONTROL `90`, `+0x20` on IRQ
`8A` in S0/S2/S3) is still unexplained. Do not consume byte 0.
GBP-INIT-002 (GBP-HW-026): extras of 0x01, 0x10 or 0x11 — CONTROL `91`,
`9D`, `11`; IRQ `9B`, `9F`, `91`; TEST `3D`, `D3`, `11`, `FF` — again all
*extra* set bits, again different from the previous runs.
GBP-INIT-003A (GBP-HW-034): extras of 0x04, 0x20 or 0x24 — CONTROL `AC` on
0x8C, none on 0x90/0x00; IRQ `AE` on 0x8A (every 0x8AAE/0x8AAA read), none
on 0x04/0x05/0x90; TEST `C7` on C3, none on the other three — a fourth
distinct pattern, again only extra set bits.

## U-GBP-016 — CLOSED 2026-09-15 (answered by GBP-BASELINE-NOGBP-001)

The MODE A readings (`00` CONTROL, `90` IRQ) and all MODE B readings
require the GBP: without it every window reads `C0`×32 (GBP-HW-007/009).
They are therefore device-dependent responses, not GameCube-side
constants. What they *mean* remains U-GBP-017; what `C0` is remains
U-GBP-019.

## U-GBP-017 (P2) — Meaning of CONTROL `0x90`/`0x94` and IRQ `0x8AAE` at idle

Hypothesis only (do not promote): in Dolphin's naming `0x90` = MASK_IRQ |
"link enable" bits — the same two bits the Start-up Disc sets in its stop
sequence — and `0x8AAE` = bit 15 | all six odd "mask" bits (0x0AAA) |
bit 2 (Dolphin: GamePak source), which would be plausible with no Game
Pak inserted. This is pattern-matching against a model, not evidence.
Needs: repeat run, run with a cartridge, run after a controlled stop
sequence — each a separate, justified experiment.

## U-GBP-018 (P2) — Is the TEST complement readable only once?

Raw TEST dumps after the handshake read `00` (GBP-HW-006). Either the
window clears on read / returns the complement only immediately after a
write, or the probe's zero-fill hid a transfer that wrote nothing. A
sentinel fill different from 0x00 in the next probe build settles the
second possibility.

## U-GBP-019 (P2, reformulated 2026-09-15) — Origin of the uniform value read without the GBP

Without the physical GBP the observed path returns a uniform 32-byte
value that does not respond semantically to TEST; the value was `0xC0`
in GBP-BASELINE-NOGBP-001 (probe-0001) and `0xC1` in
GBP-INIT-BASELINE-NOGBP-001 (init-0001). Differences between the two
runs that could matter, none selected as the cause (DEVLOG 2026-09-15):
different DOL (buffer addresses, code size), first transfer under
expansion code 3 vs 0, no raw reads before the first TEST write in the
second run, a separate power cycle and re-seating of the GBP, time of
day. Not open bus / ARAM / HSP default / floating / latch until shown.
Not blocking: any uniform fill fails both detection criteria.

## U-GBP-020 (P2, updated 2026-09-15) — Stability of the byte-0 extra bits across runs

Four physical runs now exist (two with the GBP). Static extras seen so
far: TEST C3 response byte 0 `7C` in both GBP runs (2/2 for that
pattern); 3C response `C7` in the first run (2/2 modes) but clean `C3`
in the second; IRQ byte 0 `AE`/`AA` (extra 0x24 / 0x20 vs `8A`);
CONTROL byte 0 `94`/`98` (extra 0x04 / 0x08 vs `90`). The extra bits
differ between runs for the same register, so they are not a fixed
constant. Every future run with the GBP adds samples. Fifth run
(GBP-INIT-002): TEST C3 response `3D` (not `7C`), 3C response `D3` (bit
4), FF response `11`, 00 response clean; CONTROL 0x90 → `91`, 0x8C → `9D`,
0x00 → `11`; IRQ 0x8AAE → `9B`, 0x8FAE → `9F`, 0x9090 → `91`. Across five runs
the extras were 0x40, 0x04, 0x08, 0x20, 0x24, 0x01, 0x10, 0x11: not a
constant, not a single bit. **Seventh run with the GBP (GBP-INIT-003B,
GBP-HW-041): no extra bit in any block of the whole run** — TEST, CONTROL
0x8C/0x90/0x00 and every IRQ value read byte 0 equal to the voted value.
The extras are therefore not even guaranteed to be present; a run can be
entirely clean. No mechanism, no consumption.

## U-GBP-021 (P2, re-evaluated 2026-09-16; reinforced non-blocking after GBP-AV-SERVICE-001) — Byte 0 carries additional, run-dependent bits; the transient bit 6 of GBP-INIT-001 did not reproduce

**2026-09-16, GBP-AV-SERVICE-001 (GBP-HW-059):** a fifth catalogue — TEST
`7F`/`D3`/`11` (0x43/0x10/0x11), CONTROL `93`/`9F`/`91` (0x03/0x13/0x01),
IRQ `9B`/`01`/`15`/`17`/`81`/`91` (0x11/0x01/0x11/0x12/0x01/0x01) — again
with every semantic reading agreeing (Disc == GBI == byte 0x1F) and no
decision fed by byte 0. **New:** the first raw AUDIO block shows one
non-zero byte at offset 0 of 123 of its 128 32-byte lines (GBP-HW-057) —
possibly the same per-32-byte-transfer phenomenon inside a whole-block DMA,
possibly payload; a HYPOTHESIS to test by repeated captures, never a rule.
The statement below stands and the item is non-blocking: byte 0 of any raw
block (register or AV) never decides, and the runtime reads AV blocks
whole and passes them on without consuming byte 0 as a status.

**2026-09-16, GBP-INIT-004 (GBP-HW-047):** extras again, and different
ones: TEST `C7` (0x04 over C3), CONTROL `AC` (0x20 over 8C) in every 0x8C
read, IRQ `8E` (0x04 over 8A) in every 0x8AAE/0x8AAA read, `8D` (0x88 over
05) at PREUNMASK-0 and `85` (0x80 over 05) at PREACK-0; none on 0x0400,
0x8400, 0x9090, CONTROL 0x90/0x00 or the other TEST patterns. Every
semantic reading (Disc, GBI vote, byte 0x1F) agreed and the detection was
PRESENT: byte 0 fed no decision. The 003B run without any extra
(GBP-HW-041) and this run with several are both consistent with the
statement below; nothing changes except the catalogue of observed values
(0x04, 0x20, 0x80, 0x88 added).

Observed once (GBP-HW-015, GBP-INIT-001): ~1.4 µs after the experimental
CONTROL write, byte 0 of CONTROL and of IRQ both had bit 6 (`0x40`) set
(`EC`, `EA`); by ~68 µs both had it clear (`AC`, `AA`); after the restore
write IRQ byte 0 read `EA` again. **Not reproduced** in GBP-INIT-002
(GBP-HW-026): the snapshots 3 µs and 2 s after the same CONTROL write
read byte 0 `9D` / `9D` (CONTROL) and `9B` / `9F` (IRQ), the restore gave
`91` / `9F`, and no snapshot had bit 6 extra. The safest statement is:
**byte 0 contains additional, variable bits that are not representative
of the voted semantic value, and their pattern varied between runs**
(0x40 transient in one run; 0x01/0x10/0x11 static in another;
0x04/0x20/0x24 static in GBP-INIT-003A, GBP-HW-034; none at all in
GBP-INIT-003B, GBP-HW-041). The
bit-6 transient stays recorded as a historical observation of one run,
not as a rule. Do not name any of it busy / ready / ack / interrupt /
latch; do not consume byte 0; no dedicated experiment.

## U-GBP-022 (P2, updated 2026-09-16 after GBP-AV-SERVICE-001) — Physical behavior of the PI HSP cause (bit 13): level or latched, and does W1C clear it while the GBS-DOL still asserts?

**2026-09-16, GBP-AV-SERVICE-001 (GBP-HW-052/053/055/056):** the data
points announced below arrived: no cause latched during the drain with
both sources pending under bit 15 = 0 (≥ 552 µs after the handler's W1C,
the two block DMAs included); none after the drained ACK with sources 0
under bit 15 = 1 (≥ 203 µs); **a cause latched within 43.9 µs of the re-arm
`IRQ := 0`** with 0x0400 visible and the CPU masked, held for ≥ 12 µs …
until the teardown, and cleared there by one W1C with nothing sticky. The
latched model stands (three runs); the sustained-level model stays
rejected; the line's nature (pulse, edge, device-side deassert) stays open
and unscheduled — the runtime does not depend on it.

**2026-09-16, GBP-INIT-004 (GBP-HW-043/044/045):** second observation of
the same facts with a different handler body: the W1C inside the handler
cleared bit 13 while both sources (0x0500) were pending under bit 15 = 0,
and bit 13 stayed clear for 209.8 µs until the ACK; after the ACK it stayed
clear with 0x0400 present under bit 15 = 1 (CONTROL 0x8C, then 0x90) to the
end of the run. The sustained-level model stays rejected; the line's
nature stays open and unscheduled; GBP-AV-SERVICE-001 (drained service,
re-arm, next cause; designed 2026-09-16) adds the next data points —
whether a cause latches during the drain with bit 15 = 0, and how soon
after the re-arm the next cause arrives; GBP-INIT-004B (a re-arm with a
source pending) is optional, not scheduled.

**Answered 2026-09-15 by GBP-INIT-003B (GBP-HW-037/038, GBP-PI-005, FACT
for bit 13):** the latched cause was delivered to the IRQ 26 handler when
INTMR bit 13 was opened; inside the handler `__MaskIrq` closed the mask
and one `INTSR := 0x2000` cleared bit 13 **while both device sources
(0x0400, 0x0100) were still pending, with the odd bits 0, bit 15 = 0 and
CONTROL 0x8C — the same device state that had raised the cause** — and
bit 13 stayed clear in every read for ≥ 179.7 µs before the device was
acknowledged and ≥ 323.9 µs overall. **Rejected:** the simple
sustained-level model "the HSP input to the PI stays asserted while an
enabled source is pending" (it would have re-set the latch after the
W1C). **Still admissible, not distinguished:** a pulse per event; an
edge/event assertion; a transient line; a device-side deassert mechanism
separate from the source latch (a line that drops once captured, or that
follows something other than the source bits). "HSP is pulse" is not
FACT. Priority lowered to P2: the service protocol no longer depends on
the answer (the PI cause is latched and W1C-cleared, the device is
serviced from its own register), and no experiment is planned for the
nature of the line alone; the re-arm/repeated-service experiment
(U-GBP-027) will add data (whether a source that re-sets while bit 13 is
already clear raises a new cause at once, and whether one cause can
cover two events). Original text kept below for the history.

**Answered 2026-09-15 (GBP-HW-030/033, GBP-PI-004, FACT for bit 13):** the
cause is captured with INTMR bit 13 = 0; it is latched at the PI — it
stayed set after the device-side sources had been cleared by the stop
write — and one `INTSR := 0x2000` cleared it. **Still open:** whether the
GBS-DOL's HSP line is level or pulse, and what a W1C does while the device
still asserts (in this run the device sources were cleared before the
W1C). A handler experiment that acknowledges PI while a source is still
pending on the device would answer it: GBP-INIT-003B (specified,
implemented and executed 2026-09-15 — answer above) read INTSR right
after the handler's W1C, again ≈3.7 µs later and at the main loop's
PREACK snapshot, all before the device was acknowledged.


Known (GBP-PI-001…003): software treats INTSR as a cause register
visible independently of INTMR (CORROBORATED), clears it by writing 1
(CORROBORATED), and both references acknowledge it with `0x2000`.
Unknown: whether the bit follows the device line (level) or is latched
at the PI (edge); whether a W1C write clears it while the device still
asserts; how long the GBS-DOL keeps its line asserted; and whether bit
13 ever reads 1 on this console at all (never observed — every read so
far was with INTMR bit 13 = 0 and an idle device). Not to be answered
by unmasking an idle device (rejected 2026-09-15, DEVLOG). To be
observed in GBP-INIT-002: INTSR inside the handler before and
immediately after the W1C, twice after re-masking, and after CONTROL is
restored.

**Safety note (binding for any experimental handler):** if the handler
returns with INTSR bit 13 = 1 AND INTMR bit 13 = 1, the CPU re-enters
the exception immediately after `rfi` (GBP-PI-003). The handler must
therefore re-mask IRQ 26 (`__MaskIrq(IM_PI_HSP)`) **before** relying on
the INTSR acknowledge, and the acknowledge must be treated as an
observation, not as the exit condition. Do not state that the physical
line is level or edge until observed.

**2026-09-15, GBP-INIT-002:** INTMR bit 13 was physically set and cleared
by `__UnmaskIrq`/`__MaskIrq` (GBP-HW-022, FACT), but no cause occurred in
2 s (GBP-HW-023): bit 13 of INTSR has still never been seen at 1, so the
level/edge question, the W1C behavior with an asserted line and the
delivery gating stay open. The GBP's own IRQ register was left with its
idle masks (GBP-IRQ-005); the next experiment programs it.

## U-GBP-023 — CLOSED 2026-09-15 (answered by GBP-INIT-003A's baseline)

After GBP-INIT-002 left the register at 0x8FAE and the console was
power-cycled, GBP-INIT-003A read the idle 0x8AAE at BASE (GBP-HW-027): the
pending sources did not survive the power cycle. Whether they would survive
without a power cycle was not tested and is no longer needed — every
experiment ends with an authorized stop write and a power cycle.


GBP-INIT-002 will, by design, leave the device without the write-back
that both references perform (Disc: `IRQ := pending`; GBI: `IRQ :=
value_read | 0x8000`). Whether a pending source then stays set inside
the GBS-DOL, whether CONTROL bit 0x10 (set again at restore) is enough
to quiesce it, and whether it survives a console power cycle are
unknown. Observable: the S0 IRQ read of the next run against the idle
`0x8AAE` baseline. Mitigation: power-cycle the console after the run.
**2026-09-15:** GBP-INIT-002 ended with the register reading `0x8FAE`
(source bits 0x0400/0x0100 pending) after the CONTROL restore and
`0x9090` under expansion code 0 (GBP-HW-024/025); the console was
power-cycled. Whether `0x8FAE` or `0x8AAE` is read at the next run's S0
tells whether the pending sources survive a power cycle.

## U-GBP-024 (P2, partially answered 2026-09-15) — When, inside the window, does the IRQ register go from 0x8AAE to 0x8FAE, and what drives it?

**2026-09-15 (GBP-HW-028…031):** after A1 acknowledged bit 2 and A2 wrote
the masks and bit 15 to 0 (0.5 ms after the CONTROL transform), the register
stayed 0x0000 for 50 ms, then 0x0400 was set (and the PI cause raised)
between 50.00 and 105.27 ms after A2, and 0x0500 read ≈1 ms later. The PI
mask state was constant (masked) in this run, so "the PI unmask drives it"
is excluded for these sources; "elapsed time with CONTROL 0x8C — the AGB's
audio/video streams starting" remains the consistent HYPOTHESIS
(CORROBORATED by the driver dispatch of 0x0400/0x0100 to AUDIO/VIDEO). The
INIT-002 transition time inside its 2 s window is still unmeasured; the
question is no longer on the critical path. **GBP-INIT-003B (GBP-HW-035,
GBP-HW-040):** the same 0x0400-then-0x0100 order at 105.286 ms after A2
(repeatable to 12 µs), and after the ACK both sources re-set within
≈143 µs — the register is driven by the running AGB's stream of requests
(HYPOTHESIS, consistent with the drivers' dispatch; cadence unmeasured,
U-GBP-027).


GBP-INIT-002 only brackets it: 0x8AAE 124 ticks (3 µs) after the CONTROL
transform (S1, before the unmask) and 0x8FAE 2.000035 s after the unmask
(S2, masked again); CONTROL read the same block in both. Candidate
drivers, none selected: elapsed time with CONTROL = 0x8C (the AGB's
audio/video streams starting), the PI unmask itself, internal GBS-DOL
activity, or a combination. "The unmask caused 0x8FAE" is not asserted.
A read-only temporal experiment (repeated IRQ reads under a masked PI
after the transform) would time it; it is not on the critical path if the
next experiment programs the register (DEVLOG 2026-09-15).

## U-GBP-025 (P2) — In the 0x8FAE state the two "low" bytes of each 4-byte group differ (`AF AE`)

Physical S2/S3 of GBP-INIT-002: every group reads `8F 8F AF AE` (group 0:
`9F 8F AF AE`), i.e. offsets ≡ 2 mod 4 carry bit 0 set while offsets ≡ 3
mod 4 do not, whereas at idle both read `AE`. Both references read only
offsets ≡ 1 and ≡ 3 mod 4 (Disc: bytes 0x1D/0x1F; GBI: majority votes
over those classes) and therefore agree on 0x8FAE; the meaning of the
extra bit at ≡ 2 mod 4 (a second register phase? a different bit of the
same word? noise?) is unknown. Do not consume offset ≡ 2 mod 4.
**2026-09-15 (GBP-HW-028…034):** four more states read on hardware —
0x8AAA `8A 8A AA AA`, 0x0400 `04 04 04 00`, 0x0500 `05 05 05 00`, plus
0x8AAE `8A 8A AE AE` and 0x9090 `90 90 90 90` again — and in all six states
seen so far the byte at offset ≡ 2 mod 4 equals `lo | (hi & 0x05)` (pinned
as an observation by `tests/host/test_hw_fixture.py`). An empirical
pattern with more than one possible explanation (bits 0/2 of the high byte
copied into the low byte's slot, a wiring artifact, a different register
phase); no meaning is assigned. Group 0 of the 0x0500 read broke it
(`05 05 04 00`). **GBP-INIT-003B (GBP-HW-041) broke it further:** group 0
of the PREUNMASK 0x0500 read carries `00`, and the IRQSTOPPRE 0x8500 read
carries `00` or `04` in every group (`85 85 00 00 / 85 85 04 00 …`) where
the pattern predicts `05` — the byte varies within one 32-byte DMA. The
pattern is not a rule; the exceptions are pinned byte by byte by the
003B fixture test. Both references read only offsets ≡ 1 and ≡ 3 mod 4,
and so does Open-GBP. **GBP-AV-SERVICE-001 (GBP-HW-059):** new exceptions —
group 0 of the A2PRE 0x8AAA read `BB` (for `AA`; the only read of the run
with 41 ticks / 11 polls instead of 34 / 9), group 0 of the 0x0400 / 0x0500
reads `00` / `01` (for `04` / `05`), group 5 of the POSTDRAIN 0x0500 read
`04`; pinned by the AVSVC fixture test. Same conclusion, non-blocking.

## U-GBP-026 (P2) — Mechanism of the GBP-aware game features (rumble, GBP-dependent modes)

Requirement (ROADMAP Phase 7): reproduce the special behaviors a game
shows when it runs on a Game Boy Player and the Start-up Disc / GBI
support them — GameCube-controller rumble first of all — including the
GBS-DOL signals, registers, IRQs and paths involved. Not assumed: which
path carries the game's GBP detection and its rumble commands. Leading
candidate from the accepted references: the AGB-side protocol GBATEK
documents under "GBA Gameboy Player" (SIO normal 32-bit mode, "NINTENDO"
handshake, rumble commands), which would travel over the internal serial
path the Start-up Disc drives (GBP-SIO-001, U-GBP-001…003) — the Disc's
serial state machine `0x8008c42c` and the *serial* IRQ (bit 0x0040) are
the natural places to look, and GBI's SIODATA read → message queue path
too. To be established from the Disc, GBI, physical behavior and games
known to exercise the feature (Phase 7/9/10); a GBP-aware compatibility
matrix, rumble included, is created when those phases are reached. Not
on the critical path of GBP-INIT-003A.


## U-GBP-027 (P1 → P2, functional part CLOSED 2026-09-16 by GBP-AV-SERVICE-001; investigative sub-items remain, non-blocking) — Re-arm after the acknowledge, repeated service and the cadence of the audio/video requests

**2026-09-16, GBP-AV-SERVICE-001 executed (GBP-HW-048…056, GBP-IRQ-010):
the functional objective is met for one cycle.** Delivery → PRESVC 0x0500 →
AUDIO 0x1000 and VIDEO 0xF00 read by one whole-block DMA each (66.5 /
61.4 µs) → POSTDRAIN still 0x0500, PI clear → ACK `0x8500` → 0x8000 at
+25.9 µs, PI clear, no main W1C → PI clean verified → **re-arm `IRQ := 0`
completed** → **43.9 µs later PI bit 13 = 1 with IRQ 0x0400** (REARMPOST B),
found at once, never delivered, cleared by one teardown W1C. Of the items
below: **(1) answered for one cycle** — after a drained ACK the re-arm was
followed by a PI cause within 43.9 µs (whether retained-and-released or
new: not distinguished, see the investigative list); **(2) not observed to
happen** — nothing was lost between the handler's W1C and the re-arm in
this run (one cause per delivery; a second one arrived only after the
re-arm) — one run, not a proof of impossibility; **(4) answered as a
by-product** (U-GBP-007: bit 15 = 1 with sources 0 raised no cause for
≥ 203 µs; bit 15 → 0 was followed by one); **(3) and (5) untouched** (one
interval, one cycle). The practical re-arm mechanics the runtime needs —
drain, ACK `read | 0x8000`, PI clean, `IRQ := 0`, the next cause returns and
is captured while masked — are physically validated; **R11 promoted**
(INITIALIZATION.md §14); **Phase 3 COMPLETE**. Remaining, investigative and
non-blocking, to be answered as by-products of the Phase 4 experiments
(GBP-VIDEO-001 direction): (a) retained vs new request after the re-arm
(several register samples in the first 50 µs); (b) the request period and
jitter with and without a cartridge; (c) the cost of a missed / late block;
(d) how many cycles the mask-first handler and the drained pass sustain
without reentry, timeout or a lost cause. 004B stays optional and
unscheduled.

**2026-09-16, next step decided (DEVLOG "next step after GBP-INIT-004
decided"): the scheduled experiment is GBP-AV-SERVICE-001** — one
reference-style service pass (read IRQ → drain AUDIO 0x1000 then VIDEO
0xF00 with one whole-block DMA each → ACK `pending | 0x8000` → re-arm
`IRQ := 0`), the CPU masked, then the next PI HSP cause observed and left
undelivered (HARDWARE_TESTS.md "Planned tests — GBP-AV-SERVICE-001"). If
it succeeds it answers (1) and (2) below for one cycle and (4) as a
by-product, and closes Phase 3; (3) and (5) need the repeated-service
experiment that follows. GBP-INIT-004B (below) is now optional, not
scheduled: it would re-arm with an unconsumed block, a state neither
reference enters.

**2026-09-16, GBP-INIT-004 executed (GBP-HW-042…047, GBP-IRQ-009): STILL
OPEN — the run wrote no re-arm.** One cycle was delivered and acknowledged;
26 µs after the ACK the register read 0x8400 (0x0400 present, bit 15 = 1,
CONTROL 0x8C, PI clear) and the conservative clean boundary of the design
("acknowledged sources gone before any re-arm") ended the run with
`anomaly_source_not_cleared`, `rearms 0/0`. Nothing of (1), (2), (5) and
the re-arm half of (4) was exercised; synthetic replays prove nothing here.
**Premise re-evaluated against the references (decompiles, DEVLOG
2026-09-16):** neither reference reads the IRQ register between its ACK
and its re-arm, and neither requires the sources to read 0; both drain the
AUDIO/VIDEO block before the re-arm (GBI: ARQ reads posted before the
synchronous ACK write, same queue; Disc: the immediate re-arm is suppressed
while a block DMA is in flight and written from the DMA-done path). The
"source == 0" boundary was an artificial requirement of a POC that drains
nothing. **Reformulated question (GBP-INIT-004B, designed 2026-09-16, now optional):**
with a pending AV source under bit 15 = 1, PI clear and the CPU masked,
does `IRQ := 0` (bit 15 → 0, masks 0) produce a PI HSP cause — at once
(hold released: `rearm_of_pending_source`), at the next event (~ms), or
not at all within 500 ms (the drain is needed)? Each outcome is
distinguishable by `t_hsp − t_rearm`. Sub-question kept: whether the
0x0400 status at +26 µs is a level that the ACK never cleared or a
re-assertion (U-GBP-028; not blocking for 004B).

One full service cycle is physically validated (GBP-PI-005, GBP-IRQ-008):
cause → delivery → handler mask + PI W1C → device ACK `read | 0x8000` →
stop word. What both references do next has never been exercised: GBI
writes `IRQ := 0` after its ACK (odd bits 0, bit 15 0) and waits for the
next cause; the Disc re-arms with its computed mask word. Unknown: (1)
whether a source that re-set between the ACK and the re-arm (003B: the
sources were set again ≤ 143 µs after the ACK) raises the PI cause at
once when `IRQ := 0` clears bit 15, or only at the next event; (2)
whether a cause can be lost between the handler's W1C and the re-arm
(one PI bit for several device events); (3) the period and jitter of the
0x0400 / 0x0100 requests with no cartridge (first delay repeatable at
≈105.28 ms after A2; U-GBP-014); (4) as a by-product, whether bit 15 = 1
alone holds the line — the state "sources re-set, odd bits 0, bit 15 = 1,
CONTROL 0x8C" occurs naturally between the ACK and the re-arm (U-GBP-007);
(5) how many cycles the audited mask-first handler sustains without
reentry. This is the question of the next experiment: **GBP-INIT-004,
specified 2026-09-15** (HARDWARE_TESTS.md "Planned tests — GBP-INIT-004";
DEVLOG 2026-09-15 "GBP-INIT-004 designed"; implemented 2026-09-15 as a
dirty build, DEVLOG "GBP-INIT-004 implemented"; NOT physically executed):
three
delivered causes, two re-arms `IRQ := 0`, the CPU masked between cycles,
continuation restricted to the audio/video sources (AV_SOURCE_MASK
0x0500; any other source at a service read ends the run as
anomaly_unexpected_source — observed, not serviced), a clean boundary
before every re-arm (acknowledged sources gone at POSTACK, PI bit 13 =
0, at most one main W1C), t_next_cause − t_rearm measured per cycle
and credited only when later than the re-arm, bit 15 observed under a
constant CONTROL 0x8C as a by-product, no AUDIO/VIDEO DMA, no KEYPAD.

## U-GBP-028 (P2 → P3, partially closed 2026-09-16 by GBP-AV-SERVICE-001; the undrained case stays undetermined, non-blocking) — After an acknowledge without a drain: is the audio source status "never cleared" or "cleared and re-asserted within 26 µs"?

**2026-09-16, GBP-AV-SERVICE-001 (GBP-HW-052/053):** the announced data
point read **0x8000** 25.9 µs after the drained ACK (both sources 0, bit 15
= 1, PI clear), and the sources stayed 0 through the PI-clean read before
the re-arm (≥ 203 µs). **Partial closure:** an ACK after a drain can
produce a source-clean snapshot at the distance at which 004's undrained
ACK read 0x8400 — the drained pass is consistent with the references'
order and is what the runtime does; nothing in the runtime depends on the
undrained case any more. **Still undetermined:** for the undrained ACK of
004, "never cleared" vs "cleared and re-asserted within 26 µs" (003B's
undrained ACK read 0x8000 at 25.1 µs, so both readings survive); and
exactly when the source is cleared or re-asserted internally around a
drained ACK (POSTDRAIN still showed 0x0500 ≈ 93 µs after the reads, so the
drain alone did not clear the status within that window; the ACK did).
No experiment scheduled; priority lowered.

GBP-HW-045: `IRQ := 0x8500` (W1C of bits 8 and 10 with bit 15 := 1) was
followed 26.0 µs later by a read of 0x8400: bit 8 clear, bit 10 set, bit 15
set, PI clear. Either the write did not clear bit 10 (a level status that
stays asserted while the audio block is unread, or a source that is not
W1C-clearable while pending), or it did and the source re-asserted within
26 µs (003B read 0x8000 at +25.1 µs and 0x8500 at ≈+168 µs, so a
re-assertion faster than 26 µs would be a new observation). A
finer-grained POSTACK sampling (several reads in the first 30 µs after the
ACK) would separate the two; it is **not blocking**: the references never
read the register after their ACK and re-arm regardless, and the drained
service of GBP-AV-SERVICE-001 (the scheduled next step; 004B is optional)
works either way — its POSTACK read after the drain, 0x8000 or 0x8400, is
the next data point. Scheduled only if that outcome makes the distinction
decisive for the runtime (e.g. an immediate re-request
on every re-arm would mean the runtime must drain before re-arming — which
the references do anyway).

## U-GBP-029 (P2, opened 2026-09-16 after GBP-AV-SERVICE-001) — Are the byte-0 / offset-2 deviations inside whole-block DMAs block data or a read-path artifact?

GBP-HW-061 / VIDEO_PATH.md §7: in the first physical VIDEO block the only
deviations from a uniform picture are five `+0x80` in byte 0 of a pixel word
(offset ≡ 0 mod 4); in the first AUDIO block the non-zero bytes sit at
offset 0 of 123 of the 128 32-byte units (`01` / `11`) plus four isolated
bytes at ≡ 0 or ≡ 2 mod 4; the same run's 32-byte register reads carried
extras of the same values in byte 0 and deviations at offset 2 (U-GBP-021,
U-GBP-025). Both references consume only bytes 1 and 3 of a pixel word and
only offsets ≡ 1 / ≡ 3 mod 4 of a register block, so whichever it is, the
references never see it — but for the AUDIO format (U-GBP-012) and for any
future use of a whole block it matters whether those bytes are (a) data,
(b) an artifact of the DMA / read path, or (c) undecidable. Evidence for
(b): positions (bytes the references discard; the first byte of 32-byte
units, as in the register reads), values (this run's own extras), the
AUDIO block otherwise all zero. Evidence for (a): none, but none against
either. **UNKNOWN.** Raw bytes stay the authority and are never corrected.
GBP-VIDEO-001 records per block the raw first four bytes, both frame-start
predicates separately (GBI: bytes 0 and 1; Disc: byte 1) and their
agreement, the count and positions of byte-0 exceptions and of undoubled
words: reproducibility across 88 blocks (same positions? only bytes 0/2?
never bytes 1/3? a Disc = 1 / GBI = 0 block?) is the test; the offline
boundary lists are kept per predicate, none chosen silently. The runtime rule
stands regardless: read pixels from bytes 1 and 3, as the references do.

### U-GBP-030 — why were only 25 VIDEO blocks observed between the first two frame starts? — OPEN (not blocking)

GBP-VIDEO-001 (2026-09-16) observed frame-start predicates true at captured
sequence positions 0, 25 and 65. The interval 25 is **not** a 25-block frame and
**no loss has been proven**. What the run establishes is narrower: *the host
observed only 25 VIDEO blocks between the first two frame-start predicates,
during the region where the four VERIFY cycles run.*

Facts around it: a verify cycle cost 34 792 ticks against 3 101 for a lean cycle;
the probe drained every VIDEO source it was signalled (88 selected, 88 attempted,
88 completed); the steady per-block cadence later in the run was 11 891 ticks;
the first interval spanned 628 474 ticks, which is **shorter** than the one
complete frame period measured afterwards (680 138 ticks).

The run does **not** distinguish between:

* source/event coalescing — several device blocks reported through one cause;
* the GBS-DOL advancing or overwriting its VIDEO block before the host drained it;
* a startup transient in which the device does not yet emit a full 40-block frame;
* some other behaviour not yet identified.

Nothing observed attributes the difference to the device rather than to the
host's timing, and the log carries no counter that would. Resolving it needs a
run whose first cycles are not the slow verify ones, so that the cadence is
uniform from the first useful frame. Does not affect the complete interval
seq25 → seq65, which is a clean 40 (GBP-HW-066).

### U-GBP-031 — which AGB state produces the all-white frame? — OPEN (not blocking)

The physical frame of GBP-VIDEO-001 is uniformly white with the frame-start
marker (GBP-HW-069) and matches both references exactly at every block they
define as white, differing exactly at the blocks where they embed the "GAME BOY /
Nintendo" logotype (GBP-HW-071). With no Game Pak inserted, the references'
embedded frame is the boot/idle logotype; the hardware showed a blank screen
instead. Whether that is a later phase of the same boot sequence, a state entered
without a cartridge, a pre-logotype state, or an AGB held in reset is unknown.
This is new evidence about the device state, not a fault: the transport, the
geometry and the byte picking all agree with the references.

**2026-09-16 static follow-up.** The reference asset is now traced (VIDEO_PATH.md
§9). In the Start-up Disc it is a *comparison oracle*: never drawn, compared
block by block against the converted live block, and when 40 consecutive blocks
match, the Disc injects KEYPAD bits to dismiss the screen. The detector is armed
at session start and kept armed for 24 000 invocations of a 5.000 ms periodic
callback — a nominal **120.0 s**, and a lower bound on the wall time since the
scheduler drops missed periods instead of replaying them — so the Disc itself
does not assume the screen appears promptly. Meanwhile GBP-VIDEO-001's capture window was
**39.2 ms (about 2.3 frames) starting 107 ms after the CONTROL transform that
starts the AGB**. The uniform payload is therefore consistent with having looked
very early and very briefly, and the question becomes a timing question: *when,
if ever, does the logotype screen appear on the VIDEO stream of a GBP session
without a Game Pak?* That is what GBP-VIDEO-002 is designed to answer.

**2026-09-16 — ANSWERED observationally by the physical GBP-VIDEO-002 run.** A
structured state does reach the VIDEO stream without a Game Pak: the screen
appeared 0.5014 s after capture start, animated for about three seconds, and
settled into a state held for 274 consecutive frames (4.582 s) that matches
**GBI reference table B in all forty blocks** (GBP-HW-079, GBP-HW-080). It
matches neither table A (28/40 at best) nor the Start-up Disc's embedded frame
(27/40). So the two references describe two different screens and the hardware,
without a cartridge, produces table B's. What remains open under this heading is
narrower: which AGB state table B corresponds to, and why the Disc arms a
detector for a screen (table A / its embedded frame) that this configuration
never produced. GBP-VIDEO-001's uniform white capture is now explained as timing:
it observed 39.2 ms starting 107 ms after the AGB was started, ending long before
the 0.5 s mark where the change begins.

**2026-09-16 implementation status.** GBP-VIDEO-002 is now implemented
(`poc/gbp-video-state-probe/`, Build ID `vstate-0001`) and passes every host
test, audit and Dolphin gate. It has **not** been physically executed, so
U-GBP-030 and U-GBP-031 stay exactly as open as they were: no observation in
this repository comes from it, and none of its synthetic scenarios is evidence
about the device. What the implementation does change is that the question now
has an instrument — 120 s of valid post-baseline observation, a cadence uniform
from the first useful frame (which is what U-GBP-030 asks for), per-frame
signatures over the whole window, and bounded raw preservation around any
structured change — waiting on a clean commit and an authorization.

### U-GBP-032 — one IRQ-register read whose two semantic interpretations disagreed, with the bytes not preserved — OPEN (blocking a clean long run)

At cycle 51 750 of GBP-VIDEO-002 the 32-byte read of the IRQ window returned
`rc=ok`, the ISR and the PI behaved exactly as in the 51 750 cycles before it
(latency 34 ticks, INTSR bit 13 set at entry and cleared by the handler's single
W1C), and the two readings of that block disagreed:

* the **Start-up Disc** reading takes bytes 0x1D and 0x1F — the last replica;
* the **GBI** reading takes a majority vote over the eight replicas at offsets
  ≡ 1 and ≡ 3 mod 4.

A disagreement therefore means the last replica differed from the majority of the
other seven, on a byte that both programs actually consume.

**What is not known, and cannot be recovered from this run:** the 32 raw bytes,
the two conflicting 16-bit values, and the pending source. The probe records
`pend=0000` for that cycle and keeps no payload for it, so nothing distinguishes
between a one-bit flip, a whole-byte substitution, a stale replica, a torn DMA
line and a genuine change of the register between replicas. **None of those is
assumed and no value is reconstructed.**

Context that does not resolve it (GBP-HW-084): across the 353 IRQ-window reads
whose bytes are recorded in every physical log to date there are 220 byte-level
deviations from the majority replica, and **every one landed on an offset ≡ 0 or
≡ 2 mod 4 — bytes neither reading consumes**. Two appear in this run's own log.
So deviations in that window are common and have always been absorbed; this is
the first observation of one reaching a consumed byte, if that is what it was.
But only 29 of this run's 51 751 reads had their bytes logged, so the sample says
nothing about the rate on consumed bytes.

Related: U-GBP-029 (byte-0 extras in block reads), which this narrows rather than
answers — U-GBP-029 concerns bytes the references discard, and this concerns a
byte they read.

**Not decided here:** whether a disagreement should stay fatal, become a counted
anomaly, or be retried. A retry would overwrite the very register state that
would explain it, so the first requirement is preservation, not recovery.

**Instrumented on 2026-09-16 — the question is unchanged, the evidence path is
not.** Build `vstate-0002` of the same probe preserves, at the moment of
detection and from the buffer the transport had already filled, the 32 raw bytes
of the offending read plus the context that describes the read: the two
conflicting 16-bit values, which of the two read sites saw it, the cycle, the
64-bit timestamp, the frame and block position, INTSR at ISR entry and after the
W1C, INTMR at entry, the IRQ latency, the transfer's ticks and polls, the DMA
status before and after, and the expected CONTROL shape. One record, the first
disagreement wins, later attempts are only counted. Nothing else moved: no
retry, no re-read, no second opinion, no extra access to the device, and the
disagreement remains fatal exactly as in `vstate-0001` — the operation stream of
an instrumented run is identical to that of a run without the capture. The
record travels in the sidecar as OGBPSEQ1 **v3**, under the same CRC as every
other section, and `tools/vstate.py diag` recomputes both readings offline and
names the replicas that differ. The physical cause is still UNKNOWN: the
instrumented build has not been executed on hardware, and the question closes
only when a physical run reproduces the event and the preserved bytes are read.
If a run never reproduces it, the unknown stays open — absence in one run is not
an answer.

---

**2026-09-16 refinements from GBP-VIDEO-001:**

* **U-GBP-029 (byte 0 extras in block reads)** — considerably narrowed. Over 84 480
  physical pixel words the exception is **always** `ff` where byte 1 reads `7f`,
  never the reverse, byte 2/byte 3 never disagree, and the exception **never**
  falls on the first word of a 32-byte DMA line (0 of 10 560; ~0.9 % at each of
  the other seven). Two physically independent captures of the same all-white
  flagged block differ in their raw bytes (5 vs 9 exceptions, CRC `fe45ff08` vs
  `ef18fc8d`) yet produce byte-identical byte 1 / byte 3 payloads and the same GBI
  checksum `0x7F0FFF10`. So the extras never reach what either reference reads.
  Still open: the mechanism. The 32-byte-line structure points at the transfer
  path rather than at the device's pixel data, but this is not established.

* **U-GBP-027 (repeated service stability)** — answered for a bounded sequence:
  209 consecutive deliveries through one installed one-shot handler with 0
  reentry, 0 lost cause, 0 uncertain write and a strict per-cycle W1C budget
  (GBP-HW-062, GBP-HW-063). Longer runs, and runs with a cartridge driving a
  moving image, remain untested.
