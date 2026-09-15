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

## U-GBP-007 (P2, updated 2026-09-15 after GBP-INIT-003A) — IRQ register odd-bit polarity and bit 15

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

## U-GBP-008 (P2, partially answered 2026-09-14) — Read block layout

Observed for the IRQ window: byte-doubled `hh hh ll ll` per 32-bit word
(GBP-HW-004), matching DISC's and GBI's parsing and contradicting
Dolphin's `hh hh hh ll`. Byte registers (CONTROL) read as a uniform fill.
Still open: SIODATA layout, whether byte 0 of a block is ever reliable
(U-GBP-015), and whether the layout is the same for VIDEO/AUDIO reads.

## U-GBP-009 (P3) — Board-revision differences

DOL-GBS-01/10/20, CPU AGB A vs A E, 16 Mb vs 128 Mb RAM. No behavioral
difference is documented anywhere; the user's unit revision is unknown.

## U-GBP-010 (P2) — L/R bit order in KEYPAD

Dolphin maps hi byte bit 0 → L and bit 1 → R (swapped vs GBA KEYINPUT);
GBI's 0x0304 sets both. Phase 5 test with a game that distinguishes L/R.

## U-GBP-011 (P2) — VIDEO color bit order and exact word content

Dolphin uses GBA palette order (R in bits 0–4). GBI's frame-start test only
proves the byte-doubling of the high byte. Phase 4: capture one block
with a known-color test ROM.

## U-GBP-012 (P2) — AUDIO block format on hardware

Dolphin's PWM model ("1 bits contiguous and leading", 4096 Hz, 9-bit
samples) comes from making the DISC happy, not from measurement.
Phase 6: capture blocks while the AGB plays a known tone.

## U-GBP-013 (P3) — Meaning of the SRAM "GBS" word

libogc2 validates its fields (GBP-SRAM-001); DISC presumably stores the
user's screen/filter settings there. Not analyzed.

## U-GBP-014 (P2, first data point 2026-09-15) — VIDEO/AUDIO IRQ timing on hardware

**2026-09-15 (GBP-HW-030/031):** with no cartridge, CONTROL 0x8C and the
device masks written 0, the first 0x0400 (audio) source rose between 50.00
and 105.27 ms after A2 (106 ms after the CONTROL transform) and raised PI
INTSR bit 13; 0x0100 (video) followed within ≈1 ms. One data point; no
period measured (the window ended at the first cause).


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
constant, not a single bit.

## U-GBP-021 (P2, re-evaluated 2026-09-15) — Byte 0 carries additional, run-dependent bits; the transient bit 6 of GBP-INIT-001 did not reproduce

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
0x04/0x20/0x24 static in GBP-INIT-003A, GBP-HW-034). The
bit-6 transient stays recorded as a historical observation of one run,
not as a rule. Do not name any of it busy / ready / ack / interrupt /
latch; do not consume byte 0; no dedicated experiment.

## U-GBP-022 (P1, partially answered 2026-09-15) — Physical behavior of the PI HSP cause (bit 13): level or latched, and does W1C clear it while the GBS-DOL still asserts?

**Answered 2026-09-15 (GBP-HW-030/033, GBP-PI-004, FACT for bit 13):** the
cause is captured with INTMR bit 13 = 0; it is latched at the PI — it
stayed set after the device-side sources had been cleared by the stop
write — and one `INTSR := 0x2000` cleared it. **Still open:** whether the
GBS-DOL's HSP line is level or pulse, and what a W1C does while the device
still asserts (in this run the device sources were cleared before the
W1C). A handler experiment that acknowledges PI while a source is still
pending on the device would answer it: GBP-INIT-003B, specified 2026-09-15
(HARDWARE_TESTS.md "Planned tests"), reads INTSR right after the
handler's W1C and again ≈2.5 µs later and at the main loop's PREACK
snapshot, all before the device is acknowledged.


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
question is no longer on the critical path.


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
(`05 05 04 00`).

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
