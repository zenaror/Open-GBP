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

**A procedure exists, added 2026-09-22 (GitHub Issue #30). The status does not
change: this stays OPEN, P3, and NO revision is attributed to the Operator's
unit.** Before this, the second sentence above was an open question with no
stated way to answer it. It now has one, and knowing *how* a question would be
answered is worth recording even when the decision is not to answer it:

```text
where the revision is    printed on the PCB itself, as DOL-GBS-xx beside the "© 2003 Nintendo" line -- so answering
                         it is a matter of LOOKING, not of measuring
what catalogues them     Gekkio's Game Boy hardware database (external/README.md, "Web references"), which documents
                         individual units -- e.g. gekkio-1, a DOL-GBS-10 -- with component lists and PCB photographs.
                         IT DOCUMENTS SOMEBODY ELSE'S CONSOLE. Nothing there says anything about this project's unit,
                         and no revision may be inferred from it for ours.
what it would cost       opening the Game Boy Player.
THE STANDING DECISION    THE OPERATOR WILL NOT BE ASKED TO OPEN HIS UNIT. This item is P3, no behavioural difference
                         between revisions is documented anywhere, and nothing in the roadmap depends on it; opening
                         the unit is invasive and the return today is low. Recorded so the decision is not revisited
                         by accident.
when that is revisited   if a divergence appears between what this project measures and what another source reports
                         for the same behaviour -- and then the procedure above is already known.
```

## U-GBP-010 (P2 — **CLOSED 2026-09-21** by GBP-INPUT-001, RUN 14 and RUN 15 (`HARDWARE_TESTS.md` §V7.2, Issue #24): Question O = AS-ASSIGNED in both runs — L = 1 and R = 2 in the Operator's tally vectors and, independently, in the machine-decoded frames; the descriptor kept; the routing stays CORROBORATED, not FACT — GBP-HW-265) — L/R bit order in KEYPAD — **2026-09-21, Issue #33: the routing FACT (hw, the runs) by the machine join of RUN 17 / RUN 18, GBP-HW-270; stays CLOSED**

Dolphin maps hi byte bit 0 → L and bit 1 → R (swapped vs GBA KEYINPUT);
GBI's 0x0304 sets both. Phase 5 test with a game that distinguishes L/R.

**2026-09-21, static attempt (Issue #18, `docs/research/INPUT_PATH.md` §5,
GBP-KEY-002…004).** Decompiled: the Start-up Disc's controller → KEYPAD
mapping `0x8000822c` puts L at word bit 8 and R at bit 9 in its default mode
(its alternate mode moves Y and X there and says nothing about L/R); GBI's
service thread `0x8000bf30` does the same for GameCube pads (digital L / R
or trigger > 100) and, through the N64 wire format, for N64 pads; Dolphin's model reads bit 8 as L and bit 9 as R and says the triggers
"need to be flipped". So the three sources agree on the encoding the
software targets — bit 8 = L, bit 9 = R, the reverse of KEYINPUT — which is
**CORROBORATED** (two independent implementations, one official, plus the
auxiliary model) and **not FACT**: nothing measured on this project's
hardware shows what the GBS-DOL does with those two bits, the window is
write-only in every reference and the AGB is the only observer. GBI's
`0x0304` was not used as evidence (it sets both bits). **Outcome: RESOLVED
STATICALLY at CORROBORATED; NOT closed** — this item's own closing condition
is a physical test, unchanged: a game that distinguishes L/R (OPERATOR
OBSERVATION), or, for FACT, a project-owned stimulus that publishes
KEYINPUT into its frames joined to the runtime's write schedule. No order
is adopted or defaulted in Open-GBP until then; `REGISTERS.md` keeps
Dolphin's order at H.

**2026-09-21, Issue #19:** implemented as data — the runtime's one-place
descriptor (`src/gbp/gbp_input.c`) carries this CORROBORATED assignment by
the Operator's decision, so that the first physical run falsifies or keeps
it (GBP-KEY-006; the candidate `stream-0014` is not executed). **Still
OPEN:** nothing physical was added and the closing condition is unchanged.

**2026-09-21, Issue #20:** the closing test is pre-registered as GBP-INPUT-001
(RUN 14 / RUN 15, `HARDWARE_TESTS.md` §V7.1, NOT RUN): AS-ASSIGNED closes
this item with the assignment kept, SWAPPED closes it with the descriptor's
two entries swapped; neither makes the routing a physical FACT (that needs
the project-owned stimulus recorded there as a future option). **Still
OPEN.**

**2026-09-21, Issue #22:** the Operator's recollection of the Start-up Disc
on this hardware (with its swap option on, Y acts as L) composes with the
Disc's static alternate-mode mapping (Y → word bit 8, GBP-KEY-002) to bit 8
= L — the assignment GBP-KEY-004 records, reached with one hardware-side
term (GBP-KEY-007; `docs/research/INPUT_PATH.md` §10.3). It is OPERATOR
OBSERVATION and a recollection, not a recorded observation; had the X/Y
attribution been remembered the other way round the same composition would
give the opposite answer. It changes nothing here: **still OPEN** for RUN 14,
status CORROBORATED, the descriptor unchanged; the written Disc
re-verification of §10.3 would make it a recorded observation, never FACT.

**2026-09-21, CLOSED (Issue #24; `HARDWARE_TESTS.md` §V7.2; GBP-HW-263,
GBP-HW-264, GBP-HW-265).** The closing condition this item stated — "a game
that distinguishes L/R (OPERATOR OBSERVATION)" — was met by GBP-INPUT-001 on
the Enhanced Control Checker (a test ROM that counts each button separately):
RUN 14 (walk A) and RUN 15 (walk B), both on the unchanged `stream-0014`, read
**Question O = AS-ASSIGNED** — the L tally 1 and the R tally 2 in the
Operator's literal vectors (`1 2 · · · · 6 5 3 4`, `1 2 3 4 5 6 · · · ·`) and,
independently, in the checker's screen preserved in the OGBPFULL1 frames and
decoded pixel-exactly with the frozen parser (FACT as data). Closed with the
descriptor kept exactly as it is (`src/gbp/gbp_input.c`: bit 8 = L, bit 9 = R,
unchanged since `0ff8355`); GBP-KEY-004's falsifier did not fire. **What the
closure does not do, per §V7.1.10:** the routing of the two bits stays
CORROBORATED, not FACT — the chain's fourth link ("the Operator pressed L
exactly once") is in no machine record (the log counts 42 key changes, not
words; the frames show the cartridge's display, not the GameCube's word).
The missing piece for FACT is one log line — the word at each key change
(GBP-KEY-009, recorded, not implemented); the project-owned stimulus remains
the latency instrument. `REGISTERS.md` keeps H until the Orchestrator updates
`docs/protocol/` with these ids.

**2026-09-21, Issue #26:** promoted — `REGISTERS.md`, `GBS-DOL.md`,
`ARCHITECTURE.md` and the new `docs/protocol/INPUT.md` state the order as
CORROBORATED, not FACT (was H), with the generic-pad scope and GBP-KEY-009
beside it; no status changed here.

**2026-09-21, Issue #27:** GBP-KEY-009 is IMPLEMENTED in `stream-0015`
(`da06500`; not executed) — FACT for the routing is now reachable by a run
that joins the KEY record to an instrument showing what the AGB received;
this item stays CLOSED and the routing stays CORROBORATED until that run.

**2026-09-21, Issue #33:** that run happened — RUN 17 (generic third-party
pad) and RUN 18 (original Nintendo pad) on `stream-0015`, Hardware Issue #32,
ingested `HARDWARE_TESTS.md` §V7.4. The KEY record joined to the checker's
decoded counters reads Question J = FACT for bits 8 and 9 in both runs (and
for bits 0–7 across them): **bit 8 → L, bit 9 → R is a physical FACT (hw,
the runs)** with no human count in the chain (GBP-HW-270). This item stays
CLOSED; its closing now rests on a machine record; the descriptor is
unchanged; the consolidated pages carry F (hw, run-scoped) with the history.
RUN 16 (the menu reading, executed last) reads UNDECIDED for the join by the
rule (R_8 = R_9 = 8) and its directional question is NOT readable (no
convention declared, no direction per trigger reported; not inferred).

## U-GBP-011 (P2 — **CLOSED 2026-09-18** by GBP-VIDEO-003 / `color-0002`, the pre-registered confirmatory run: the outer 5-bit groups are exchanged, `CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP`, promoting the colour order from CORROBORATED to **FACT**. Two residuals were never part of this item and stay open: bit 15's origin, now U-GBP-034, and the bytes 0/2 deviations, U-GBP-029) — VIDEO color bit order and exact word content

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

**2026-09-17: the experiment is designed (GBP-VIDEO-003, HARDWARE_TESTS §V3).**
Four physical runs have now established the transport, the geometry and the
policy, and not one of them could touch this question: every check made so far —
frame-start predicates, block checksums, the byte-for-byte comparison against the
Disc's embedded frame — is **invariant under exchanging the outer 5-bit groups**,
which is exactly the difference between the two candidate readings. The design
answers it with a controlled AGB Mode 3 stimulus of eight 30-pixel bars whose
values are known by construction, three of which carry a single bit each so that
an intra-channel reversal cannot hide behind full-scale primaries, and two of
which (`0x0000`, `0x7FFF`) are invariant under any bit permutation and therefore
serve as complement and stuck-bit controls. The stimulus never writes bit 15, so
whatever bit 15 the window carries is observably not the colour value.

Nothing about the answer is anticipated: the design requires **exactly one**
candidate transformation to reproduce all eight observed values, and calls the
run INCONCLUSIVE if two fit or none does. It is blocked for execution only by a
documented **dependency**: this repository knows no way to run a controlled GBA
ROM on the physical unit (§V3.7), and neither the design nor the implementation
invents one.

**2026-09-17, implemented.** The stimulus ROM, the probe, the `OGBPCOL1` v1
sidecar and the offline analyser all exist and are exercised by host tests; none
of it has touched hardware. The analyser reaches a verdict only when exactly one
candidate transformation reproduces all eight observed values, and its synthetic
corpus includes the cases where it must refuse to: two survivors, none, a bar
that is not uniform, and a mirrored frame.

**2026-09-18, EXECUTED — and the answer is still not taken.** `color-0001` ran on
the physical unit with the stimulus cartridge. The runtime reached its own target
(`stop=color_certified`, three eligible frames with identical `sig[40]`, clean
service and restore — GBP-HW-120, GBP-HW-121). The **analyser refused it**: the
three certified frames are not byte-identical over the full 153 600-byte raw
frame, so `tools/vcolor.py` stopped at `inconclusive_certified_raw_mismatch`
before interpreting one pixel (GBP-HW-122). That verdict stands and this item is
**not closed by it**.

What the run does show, as a *post-gate diagnostic projection* only: every
differing byte is in position 0 or 2 of its group, never 1 or 3, so under the
pre-existing consumer projection `word = (b1 << 8) | b3` the three frames are
identical in 38 400 of 38 400 words (GBP-HW-123); and the eight bars then read
`0x0000 0x7C00 0x03E0 0x001F 0x7FFF 0x0400 0x0020 0x0001` against a stimulus of
`0x0000 0x001F 0x03E0 0x7C00 0x7FFF 0x0001 0x0020 0x0400` — the outer-group swap,
H1, on **8/8** bars, with H2 surviving only on the four swap-invariant controls
(GBP-HW-124).

**Why that is not promoted.** The experiment pre-registered its acceptance
criterion, the run failed it, and a result that is read only after relaxing the
criterion that rejected it is not the result the experiment was designed to
produce. Changing the gate now and calling the same bytes conclusive would be
choosing the analysis after seeing the data. The order therefore stays
**CORROBORATED** exactly where 2026-09-17 left it, and the projection above is
recorded as a strong, reproducible, independently pinned observation that
*agrees* with it.

**What closes it.** A pre-registered `color-0002`: an analysis contract written
down *before* the run that states which bytes are in the acceptance gate and
why (the consumed projection, on the pre-existing authority of GBP-VID-003 and
U-GBP-029, with the full-raw comparison kept and reported as a separate
diagnostic rather than as the gate), a new analyser version rather than an edit
to the frozen one, and a fresh physical run judged by it. `OGBPCOL1` v1 stays
FROZEN and `color-0001` is never re-labelled.

---

## CLOSED — 2026-09-18, GBP-VIDEO-003 / `color-0002`

**Every condition this item set for itself was met, in the order it set them.**
The contract was written down first (`HARDWARE_TESTS.md` §V4, commit `a86b079`),
as a new analyser (`tools/vcolor2.py`) rather than an edit to the frozen one, and
a fresh physical run — build `color-0002`, commit `39f1980`, DOL sha256
`d3c1f09e…`, built clean at that exact commit — was judged by it. Neither the
contract nor the analyser was touched between the pre-registration and the run.

```text
STANDING: CONFIRMATORY
VERDICT:  CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP
```

**The answer.** The VIDEO window's consumed pixel word carries the AGB's fifteen
colour bits with the two outer 5-bit groups **exchanged**: what the AGB wrote in
bits 4–0 arrives in bits 14–10, and what it wrote in bits 14–10 arrives in bits
4–0; bits 9–5 are unchanged. Under the reading both reference decoders implement
— bit 15 flag, bits 14–10 R, 9–5 G, 4–0 B — the displayed colour is therefore the
AGB's intended colour, and the Start-up Disc's embedded idle frame renders as its
author intended. **This is the promotion the item was waiting for**: its own text
said "CORROBORATED, not FACT: no physical pixel of a known color has been
captured". Eight have now been captured, uniform over 4800 pixels each, in three
certified frames, twice.

Supporting evidence, all recomputed from the raw bytes rather than taken from the
analyser: GBP-HW-127 (runtime PASS), GBP-HW-128 (38 400 of 38 400 consumed words
identical across A, B and C), GBP-HW-129 (flag15 stable), GBP-HW-130 (the colour
vector, every pixel of every bar), GBP-HW-131 (the unique exact match),
GBP-HW-132 (the same picture in both physical runs), GBP-HW-133 (the full-raw
diagnostic).

**The exact width of the closure, and what stays outside it.**

- It is about `colour15` in the consumed pixel word, for AGB Mode 3 video on the
  path these runs exercised. Nothing wider.
- Within a 5-bit group the stimulus pins bit 0, bit 5 and bit 10 individually and
  each group as a set. **A permutation fixing those three while rearranging only
  bits 1–4 inside a group is not excluded by this pattern.** That limit was
  written into the design before the run (§V3.19), which also records the
  follow-up pattern that would close it; the run produced no residual ambiguity,
  so the follow-up is not triggered and no new item is opened for it.
- It says **nothing** about bytes 0 and 2 — `U-GBP-029` stays OPEN, and this run
  is its fifth corroboration, not its answer.
- It does **not** explain bit 15. That bit is observably *not* the colour value
  and is added on the path — the AGB wrote zero there — but what sets it and when
  is now **U-GBP-034**.
- It does not touch `U-GBP-033`.
- It does **not** make `color-0001` confirmatory in retrospect. `color-0001`
  failed its own pre-registered gate and stays `INCONCLUSIVE_CERTIFIED_RAW_MISMATCH`
  permanently; `tools/vcolor.py` is unchanged and still prints that verdict.

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

## U-GBP-012 (P2 — **STILL OPEN**; 2026-09-22, Issue #58: the first experiment against it is PRE-REGISTERED, `HARDWARE_TESTS.md` §V8, GBP-AUDIO-001 — **NOT RUN, NOT AUTHORISED**, and a pre-registration answers nothing — **RUN 30 EXECUTED AND INGESTED 2026-09-22 (Issue #62, §V8.13): the first data with a cartridge running. AU = CARRIES / OTHER SHAPE. The prerequisite is answered; the FORMAT is not, and this item STAYS OPEN**) — AUDIO block format on hardware

Dolphin's PWM model ("1 bits contiguous and leading", 4096 Hz, 9-bit
samples) comes from making the DISC happy, not from measurement.
Phase 6: capture blocks while the AGB plays a known tone. **2026-09-16
(GBP-HW-057):** the first physical AUDIO block, no cartridge: 3969 of 4096
bytes zero, values `00`/`01`/`11` only, the non-zero bytes at offset 0 of
123 of the 128 32-byte lines (`01` ×121, `11` ×2) plus four isolated `01`.
Not called silence, PCM or PWM; the per-line byte 0 may be payload or the
transfer's byte-0 phenomenon (U-GBP-021) — undecidable from one block.

**2026-09-22 (Issue #58) — where the first real data would come from.** Every
AUDIO block archived so far was captured **with no Game Pak**, so this item has
no data from a running cartridge at all. `HARDWARE_TESTS.md` §V8
(`GBP-AUDIO-001`) pre-registers the experiment that would produce some: four
windows of 256 drained blocks each, anchored on a press of a cartridge whose
tone is known a priori, with the PWM, PCM and byte-0 models predicting
**different bytes for the same window** (§V8.5) and compared against a silent
control from the same run (§V8.5.1). **Nothing is authorised, nothing is run,
and this item is not answered by the pre-registration** — it is pointed at it.
The three-model prediction lives in code as `tools/v8audio.py`, written from
§V8's frozen text before any log exists.

**2026-09-22 (Issue #62) — RUN 30, and what it did and did not settle.**
`GBP-HW-287` … `GBP-HW-291`, `HARDWARE_TESTS.md` §V8.13.

```text
NOW KNOWN, on hardware, with a cartridge running -- none of it was known before:
  the window is NOT empty and NOT GBP-HW-057's sparse byte-0 pattern
  it carries a two-level square of EXACTLY 256-byte period, values {00,01,FE,FF}, 1280/1280 blocks
  it is NOT PWM-shaped: Dolphin's model refuses every block rather than fitting it loosely
  its content CHANGES when a button is pressed -- intermediate levels appear, ONE GBA FRAME after the
    GBP-side key change (18.32 / 15.88 / 12.21 ms), repeating across three presses and growing with them
  the within-run control is NOT silence: the square is already there before any press (GBP-HW-288)
STILL UNKNOWN, and this is why the item does not close:
  the sample rate, and therefore EVERY frequency (U-GBP-037)
  whether a block is a time series or a repeatedly re-read buffer (U-GBP-037)
  whether the standing square is the AGB's, the GBP's, or the region's reset content
  what a press actually adds -- a second channel, a mix, or something else
  why press 1 changed nothing (U-GBP-038)
```

**The prediction of §V8.5 failed structurally, not numerically**: it assumed
the level alternates ACROSS blocks and the wave is INSIDE one.
`tools/v8audio.py` keeps its constructions unedited (Issue #50); the next
instrument is the one §V8.5.2 already named — **`stimulus/agb-tone`, a ROM
whose output this project controls end to end**.

**2026-09-22 (Issue #67 and its validation) — RUN 31 SPLITS THIS ITEM IN TWO,
and the two halves now have different answers.** `stimulus/agb-tone` ran with
two known notes, and the result is that **§V8.5's original premise was right
after all**: the level alternates ACROSS blocks, and RUN 30's within-block
square was the transfer's own cell hiding it.

```text
THE RATE -- ANSWERED, and it is DOLPHIN'S OWN NUMBER
   one drained block = ONE SAMPLE, at 4 096.0 blocks/s recovered independently from two windows at
   two frequencies (GBP-HW-298, GBP-HW-301). GBP-AUD-001 records Dolphin's model as "produced at
   4096 Hz" -- CORROBORATED BY HARDWARE TO FOUR FIGURES.
THE BYTE LAYOUT -- STILL OPEN, and it is what this item now IS
   Dolphin's 0x400 bytes mirrored x4, one bit per 32-bit word, 1-bits contiguous and leading, is
   REFUSED: the bytes are not contiguous-leading (GBP-HW-287), and the 256-byte cell is the TRANSFER's
   -- present with the APU PROVABLY OFF (GBP-HW-296).
```

**"Dolphin was wrong" is too coarse and this item must not be read that way**:
the cadence its model was built around is the cadence the hardware delivers,
and only the arrangement of bytes inside a block is refused.

**A HYPOTHESIS, labelled as one and NOT promoted by this run** (the
Orchestrator's, on validating Issue #67): if a sample is carried as the **duty
of the 256-byte cell** — `96/256`, `128/256`, `160/256` are the three values
seen — then **the encoding IS pulse-width modulation, at the BLOCK level rather
than the 32-bit-word level**, and Dolphin would have had the mechanism right
and the scale wrong.

```text
what supports it   three duty values, symmetric about the control's 128/256, changing with the tone
what refuses it    nothing yet -- which is the problem: three values are not a curve
WHAT WOULD TEST IT a stimulus that sweeps AMPLITUDE rather than frequency. If the duty tracks the
                   envelope monotonically over many levels, the reading holds; if it takes only a few
                   values whatever the amplitude, it does not.
where it belongs   a pre-registration of its own, with the prediction written before the run. NOT here.
```

**2026-09-22, Issue #68 — THE TEST NAMED ABOVE IS NOW DESIGNED**, and only
designed: `HARDWARE_TESTS.md` **§V10**, GBP-AUDIO-003. Four envelope levels
(15 / 11 / 7 / 3) at a fixed 128.0 Hz, one level per press, with the predicted
duties written out and the **linear** map separated from a **compressive** one
by at least 5 bytes of 256 at every point that is not the anchor. **No ROM, no
build, no run, and nothing frozen**: §V10 is a design, its numbers become real
only when a pre-registration puts them in code before data exists, and **this
item stays exactly as OPEN as it was**. Two things §V10 adds that this entry
did not have: the null is tested as the **intercept** of the four points rather
than as a fifth window — because a zero-amplitude window and a window that has
not begun carrying are the same picture — and a **second candidate encoding**
rides along for free, since a run that records each window's byte **alphabet**
can see magnitude carried in the cell's LEVELS instead of its duty.

**2026-09-22, Issue #69 — PRE-REGISTERED, `HARDWARE_TESTS.md` §V11**, with the
constructions frozen in `tools/v11sweep.py` before `stimulus/agb-sweep` exists.
Three questions with separate gates — the amplitude sweep on the ORDER, the
frequency ladder on the RATIOS, the alphabet on the LEVELS — and neither
consults the other's evidence. **NOT RUN, NOT AUTHORISED; a pre-registration
answers nothing and this item STAYS OPEN.** What it adds to the entry above:
the null is the fit's intercept, so **any flat window is a carriage failure and
never a volume-0 reading**; a window with one distinct byte value is `NO CELL`,
a finding in its own right; and the schedule a run exercised is **derived from
the `KEY` record**, with a mismatched window **refused** rather than read as the
other question.


**2026-09-23 — RUN 34 PRE-REGISTERED as §V11's sweep REPEATED
(`HARDWARE_TESTS.md` §V14)**, under §V11's gates unedited. **Not run; this item
stays exactly as open as it was.** Two things it establishes before the run:
**a four-press run cannot deliver four carrying amplitude windows while
`U-GBP-038` holds**, because the first press is the emission and its window is
dead under either reading — so `question_V` will be INCONCLUSIVE by
construction, and the loss is free because the lost amplitude is V=15, already
measured twice in RUN 31; and **§V11.13's three-second spacing is inside T's
bound**, so RUN 34 spaces at five. What it would add: **V=11, the only amplitude
never measured**, and a like-for-like **repeat** of V=7 and V=3 — which is what
`GBP-HW-305` names as needed before its reading can be FACT.

**2026-09-23, Issue #78 — RUN 34 measured ALL FOUR amplitudes in one run**
(`GBP-HW-310`): V=11, never measured before, lands 0.06 bytes from the linear
prediction; the repeat of V=7, V=3 and V=15 agrees to under 0.08 bytes. **The
pre-registered `QUESTION V` returned INCONCLUSIVE** (byte duty is phase-sensitive
at V=3, `GBP-HW-309`), **so this item stays OPEN and H-PWM is not promoted.** The
layout half is better measured than it has ever been and still not answered by
the gate that was built to answer it.


**2026-09-23, Issue #80 — THE LAYOUT DECODES AND PLAYS** (`GBP-HW-313`,
CORROBORATED). Under H-PWM — one block = one sample, the one-bit fraction minus
the rest, 4096/s — RUN 33 decodes to exactly 128 / 512 / 256 / 1024 Hz and RUN 34
to 128 Hz falling in loudness with the volume. **What this narrowed:** the layout
is no longer a pattern that fits the numbers; it is a decode whose output is the
AGB's own tones, with WAV files anyone can play. **What it did not:** the item
stays OPEN. It is one construction agreeing with one prediction set, and the next
question has already appeared — **what each sample integrates over.** At 1024 Hz
the series has four levels per period, two of them edge-straddling and symmetric
about the rest, which is what an integrating sampler would give; that is a
HYPOTHESIS from one window.

**2026-09-23, Issue #82 — what a block carries beyond its sample** (`GBP-HW-314`,
`GBP-HW-315`, `HARDWARE_TESTS.md` §V18). The layout is not reopened and
`GBP-HW-313` stands. The H-PWM sample is the **sum of sixteen 256-byte slice
counts**, and every block is either flat over them or one step at a slice index
where the level changed. The steps are exactly the programmed edges, and every
transition falls on an even slice. So *"what each sample integrates over"* has a
concrete answer as far as the bytes go: sixteen time-ordered slices, ordered at
two-slice granularity. What stays open moves to `U-GBP-041` (are the slices
uniform in time?) and `U-GBP-043` (the 1–3-bit spread and the bit arrangement).
**The item stays OPEN.**

**2026-09-23, Issue #85 — `GBP-HW-305` is FACT, and this item stays OPEN.** RUN 35
(`HARDWARE_TESTS.md` §V20), §V14.10 repeated unchanged, was judged by
`question_L_bits` — frozen before it ran — and returned **LINEAR**, self-contained
in one run. That closes the two objections the paragraphs above named as standing
between `GBP-HW-305` and FACT: all four points now come from one run and one ROM,
and the pre-registered gate passed. **What it settles is how the envelope volume
scales the decoded amplitude — linearly. It does not settle this item's question**,
which since §V18 is what each AUDIO block integrates over and whether its sixteen
slices are uniform in time (`U-GBP-041`). **The item stays OPEN.**

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

**Needs, updated 2026-09-22 (GitHub Issue #46; `GBP-HW-272`). The item stays
OPEN at P2 and nothing here closes it.**

```text
repeat run                    STILL OPEN
run with a cartridge          ANSWERED FROM THE ARCHIVE, FOR BIT 0x02 ONLY, 2026-09-22. It had already happened 22
                              times: the original CONTROL byte reads 0x90 in the 12 cartridge-less logs and 0x92 in
                              the 22 with a cartridge, differing by bit 0x02 alone (GBP-HW-272, FACT for the split).
                              That the bit REPORTS presence stays HYPOTHESIS -- the archive pairs no late build with
                              an empty slot, so cartridge and build era are not separated, and Dolphin's "GamePak
                              source" is a bit of the IRQ register, not this one. The named breaker is one boot of
                              12-stream with the cartridge removed; it is not scheduled here.
run after a stop sequence     STILL OPEN
what is STILL UNKNOWN here    the meaning of 0x10 and 0x80 -- the two bits that make 0x90 what it is -- and of 0x94,
                              and of IRQ 0x8AAE at idle. The hypothesis in this item's first paragraph is untouched:
                              GBP-HW-272 speaks about ONE bit of the byte and says nothing about the rest.
```

**Needs, updated again 2026-09-22 the same day (GitHub Issue #47). The item
STILL stays OPEN at P2.**

```text
the breaker RAN, unbidden      The Operator performed it on his own initiative before anyone scheduled it: RUN 23,
                               12-stream with no cartridge, reads 0x90 (GBP-HW-273). The build-era rival is
                               disconfirmed BY MEASUREMENT and bit 0x02's causal reading moves H -> C. What is
                               still missing for FACT is unchanged and is not this item's: watching the bit change
                               while only the cartridge changes.
and bit 0x01 stopped being     RUN 24, with a Game Boy Color cartridge: the ORIGINAL byte is 0x92 with bit 0x01
  a one-state bit              CLEAR, and the bit becomes SET 186-636 us after the transform write, staying set
                               through a restore that consequently fails (GBP-HW-274, GBP-HW-275, GBP-HW-276).
                               The idle 0x90 this item is about is therefore a byte whose bit 0x01 can change
                               UNDER THE RUNTIME'S FEET when the media differ -- which is new, and which this
                               item's first paragraph never contemplated.
what this item still asks      the meaning of 0x10 and 0x80, of 0x94, and of IRQ 0x8AAE at idle. Untouched by
                               either run.
```

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

## U-GBP-029 (P2, opened 2026-09-16 after GBP-AV-SERVICE-001; re-measured twice on a NON-UNIFORM picture, 2026-09-18, and now ACROSS two independent physical runs — the deviations are still confined to bytes 0 and 2, and still unexplained) — Are the byte-0 / offset-2 deviations inside whole-block DMAs block data or a read-path artifact?

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

**2026-09-18, GBP-VIDEO-003 / color-0001 (GBP-HW-123, GBP-HW-126).** The
reproducibility question this item posed — *"only bytes 0/2? never bytes 1/3?"*
— now has its strongest answer. Three certified frames of a **non-uniform**
picture, 153 600 bytes each: 2125, 2073 and 2137 differing bytes pairwise, and
every single one of them at position 0 or 2 of its group. Bytes 1 and 3 differ in
**zero** positions across all three pairs, so the consumed projection is
identical in 38 400 of 38 400 words. Every earlier test of this was made on an
essentially uniform white screen, where most of the payload cannot show a
difference; this one was not.

**2026-09-18, `color-0002` (GBP-HW-132, GBP-HW-133) — the sharpest form of the
question so far, and it still does not answer it.** The confirmatory run
reproduces the shape exactly: A/B 2434 differing bytes, B/C 2483, A/C 2485, over
40 of 40 blocks and 160 of 160 lines, **byte 1 and byte 3 zero in every pair**.

What is new is the cross-run comparison. The three certified frames of
`color-0001` and `color-0002` — two physical runs, two commits, separate power
cycles — are **byte-identical in the consumed projection**, 38 400 of 38 400
words in all three corresponding pairs, while their full raws differ in 2514,
2449 and 2481 bytes, again entirely in bytes 0 and 2. So the device delivered the
*same picture* twice and *different* bytes 0/2 twice.

That is strong evidence the deviations do not carry picture data, and it is
still not evidence for (a), (b) or (c): a field that is not the picture may still
be data. **UNKNOWN stands.** Nothing here names a mechanism, and the raw bytes
remain the authority and are never corrected.

That is consistent with (b), a read-path artifact, and it is **still not
decisive**: nothing here excludes bytes 0 and 2 carrying data the references
simply ignore, and nothing here identifies a mechanism. **UNKNOWN stands.** Two
things are new and recorded rather than folded in: byte 2 deviates too, which
GBP-HW-070 had measured as zero cases on GBP-VIDEO-001 and which was latent and
unmeasured in the 2026-09-16/17 `vstate` fixtures; and the deviation rate rises
with picture complexity (~0.6 % of words on white, ~1.4 % here), which is a
correlation over four runs and not a rule.

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

### U-GBP-032 — one IRQ-register read whose two semantic interpretations disagreed, with the bytes not preserved — ANSWERED 2026-09-17 (the bytes exist; the mechanism moved to U-GBP-033)

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

**2026-09-17 — ANSWERED. The bytes were caught.** The instrumented build ran and
the event recurred, at cycle 517 of 518 after 0.0842 s of capture. The 32 bytes
are GBP-HW-089:

```text
01 01 01 00  01 01 01 00  01 01 01 00  01 01 01 00
01 01 01 00  01 01 01 00  01 01 01 00  05 05 05 00
```

Every part of this entry's "what is not known" list is now known **for this
occurrence**: the raw bytes, both conflicting values (Disc `0x0500`, GBI
`0x0100`, GBP-HW-091) and the pending source — the two readings differ by exactly
`0x0400`, the AUDIO source bit (GBP-HW-092). The list of candidates this entry
refused to choose between has also narrowed by observation rather than by
argument: it is **not** a one-bit flip and **not** a torn or garbled byte, because
the eighth group is internally coherent — its first three bytes moved together
exactly as every other group's do, and its fourth byte is `00` like all the others
(GBP-HW-090). What the read returned is eight well-formed replicas of which seven
carry one value and one carries another.

What that leaves is a question this entry never asked, because it could not: **why
do the replicas of one 32-byte read disagree at all?** That is a question about
the device, not about our instrumentation, and it is now U-GBP-033.

**Still not decided here**, and deliberately: whether a disagreement should stay
fatal, become a counted anomaly, or be retried. That decision now has evidence to
stand on (U-GBP-033 and GBP-HW-096) and is analysed in the DEVLOG entry of
2026-09-17, but nothing in the runtime has changed.

---

### U-GBP-033 — what mechanism produces semantic non-uniformity among the eight replicas of the IRQ window? — OPEN (mechanism unknown; the SERVICE POLICY it once blocked is now PHYSICALLY VALIDATED — 52 events survived across vstate-0003 and vstate-0004)

Two physical runs have now ended on a read whose eight replicas did not all carry
the same 16-bit value, and the second preserved the bytes. The question is **not**
a yes/no about atomicity — "is it a snapshot?" would be answered `no` by
GBP-HW-090 and GBP-HW-093 and would teach nothing. The question is what produces
the non-uniformity:

* does the source register change **during** the transfer, so that different
  groups of one 32-byte read reflect different instants?
* does GBS-DOL (or whatever publishes the window) update the eight replicas
  **non-atomically**, so that a read can catch the update half-done?
* is the replication itself a bus or fabric artefact, so that "replica" is the
  wrong mental model entirely?
* something else.

**Nothing here chooses.** The evidence that exists:

* the fatal read is transport-normal in every measurable way (GBP-HW-095): same
  34 ticks, same 9 polls, same DSPCR `0804` as all 61 fully logged reads;
* the transfer occupies 34 ticks = 0.84 µs, about 0.6 % of the ~142 µs mean
  interval between causes in the same window — so a change landing inside it is
  rare but not extraordinary;
* the same run shows **intra-block non-uniformity that is ordinary**: on windows
  reading `0x0500` the discarded byte at `4k+2` takes different values in
  different groups of the same read (GBP-HW-093), with no monotone order —
  `04 05 05 05 05 04 00 05` is one observed block. A block is therefore already
  known not to be one instant's snapshot, on bytes nobody consumes;
* the changed group is the **last** one, and the AUDIO/VIDEO alternation would
  have put a VIDEO cause at cycle 517 (509–516 alternate strictly), which matches
  the majority, with AUDIO appearing only in the last group. That is consistent
  with "group 7 is the most recent", but the AUDIO cadence in the same window
  (244–279 µs since the previous AUDIO cause) puts the next AUDIO **34–70 µs
  after** this read, not during it. The timing therefore neither supports nor
  refutes the temporal story, and the physical fill order of the window has never
  been established. **HYPOTHESIS, not more.**

What would answer it: a probe that reads the same window twice in quick
succession around a disagreement (which the current design forbids, for good
reason — the first requirement was preservation), or an experiment that correlates
the disagreeing group index with an independently timed source assertion. Neither
is designed yet, and neither is GBP-VIDEO-003.

**2026-09-17, refined by twenty-three physical events.** The `vstate-0003` run
produced 23 semantic disagreements in 1 114 007 deliveries and survived all of
them, so for the first time the phenomenon can be described from a population
rather than from single events (GBP-HW-100, GBP-HW-101).

**FACT, recomputed from each record's own 32 bytes:**

* 23 events, every one of them `Disc = 0x0500` against `GBI majority = 0x0100`,
  i.e. the same direction as both earlier events: the last replica carries a source
  the majority does not;
* the differing source is AUDIO `0x0400` in all 23;
* the `0x0500` replicas always form a **contiguous suffix at the end of the
  32-byte window** — never scattered, never a prefix, never interleaved;
* the suffix length distribution is 21 × 1, 1 × 2 (cycle 839 272), 1 × 3
  (cycle 1 015 782);
* the omitted AUDIO source was present in the next ordinary read in 23 of 23
  (GBP-HW-102), and no next cause contained VIDEO.

**CORROBORATED:** the non-uniformity is *ordered*. A window is not a set of eight
independently noisy copies; whatever produces the difference produces it at the
tail, in a run of consecutive replicas.

**Still UNKNOWN, and the point of this entry:** the mechanism. The contiguous
suffix constrains the space of explanations considerably, but it does not choose
among them, and this repository does not claim it does. Specifically it is NOT
established that the suffix is "the newer value": that reading requires knowing the
order in which the device updates the replicas, the order in which the transfer
reads them, and whether the source changed during the transfer. None of the three
has been observed. A suffix would look the same if the *first* groups were the
newer ones and the tail were stale.

What would separate them: an experiment that correlates the suffix boundary with
an independently timed source assertion, or one that reads the window twice around
a disagreement. Neither is designed, and neither is GBP-VIDEO-003.

**2026-09-17, a second long run: 29 more events, and the same shape.** Build
`vstate-0004` reproduced the phenomenon 29 times in 1 114 005 deliveries, this
time with a producer whose per-record attribution is correct (GBP-HW-110,
GBP-HW-114).

**FACT, recomputed from each record's own 32 bytes:**

* 29 events, every one `Disc = 0x0500` against `GBI majority = 0x0100`, the same
  direction as all 23 of the previous run;
* the `0x0500` replicas form a **contiguous suffix** in 29 of 29, with lengths
  24 × 1, 2 × 2 (cycles 113 805, 1 030 312) and 3 × 3 (cycles 941 104, 1 042 937,
  1 110 826);
* the omitted AUDIO source was present in the next ordinary read in 29 of 29;
* **combined corpus across the two long runs: 52 events, 45 × 1 / 3 × 2 / 4 × 3,
  contiguous in 52 of 52, AUDIO present in the next read in 52 of 52**;
* in `vstate-0004` only — where `t_rearm` belongs to the record's own cycle —
  the re-arm-to-next-cause interval is **77 to 94 ticks (1.90 to 2.32 µs)**
  (GBP-HW-112).

**CORROBORATED:** the non-uniformity is *ordered*. Two independent long runs, two
different producers, 52 events, and not one scattered pattern.

**Still UNKNOWN, and the point of this entry:**

* the internal mechanism;
* the temporal direction — whether the suffix is the newer value or the older
  one. The 1.9 to 2.3 µs figure does not settle it: it measures our own re-arm
  against our own next cause, not the order in which the device fills the window;
* the order in which the eight replicas are updated;
* how the DMA that reads the window interleaves with that update.

A second run reproducing the same shape **narrows nothing about the mechanism**.
It makes the shape a robust observation, which is what a corpus is for.

**2026-09-17, separation of concerns.** This unknown was first written as though
it blocked the service policy. It does not, and treating it that way would hold
the project hostage to a question about the device's internals. The policy
question — *which reading is authoritative, and must a disagreement end the run?*
— can be answered from the lifecycle evidence we already have (GBP-HW-028,
GBP-HW-096) without knowing the mechanism, and the `vstate-0003` design in
HARDWARE_TESTS does exactly that. The mechanism stays UNKNOWN here, and a future
experiment may still address it; nothing in the policy design claims to explain
it.

Related: U-GBP-029 (byte-0 extras) and GBP-HW-093 are very likely the same
phenomenon seen on bytes that are discarded; if they are, this unknown subsumes
both. That connection is itself a HYPOTHESIS.

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

### U-GBP-034 — what sets bit 15 of the VIDEO pixel word, and can it appear anywhere but the first pixel of a frame? — OPEN (opened 2026-09-18; not blocking)

**Why this is a separate item.** It was carried inside U-GBP-011 as "exact word
content" and never answered there, and closing that item without naming it would
lose it. The *consumption* side has never been in doubt: both reference decoders
treat bit 15 of the pixel word as the frame-start flag and force it on when they
draw — the Disc sets `FILL = 0x8000` in every pixel it converts, GBI ORs
`0x80008000` into its tiles, and the two frame-start predicates read it
(GBP-VID-003, GBP-VID-004, F (code) ×2). What is open is the *production* side.

**What is established physically.** Exactly one word per frame carries bit 15, at
x = 0, y = 0, in every physical frame this project has captured: `vstate-0001`,
`-0003`, `-0004`, 3 of 88 stored blocks in GBP-VIDEO-001 (all at word 0),
`color-0001` (GBP-HW-125) and `color-0002` (GBP-HW-129). In the two colour runs
the word is exactly `0x8000` — flag set, `colour15 = 0x0000` — because the
stimulus paints bar 0 black and **never writes bit 15 anywhere**. So the bit is
observably not the colour value and is added on the path between the AGB's
framebuffer and the VIDEO window. Earlier runs could not show this: their first
word was `0xFFFF`, flag over white, where the bit is indistinguishable from the
colour.

**What is NOT established.** Who sets it — the AGB side, the GBS-DOL, or the
transfer itself; whether it is a position marker, a transfer-boundary artifact or
something else; whether a picture, a mode or a timing exists in which it appears
at another coordinate, more than once, or not at all. `FLAG15_STABLE` in
`tools/vcolor2.py` means *reproducible across the three certified frames of one
run* and is deliberately worded to claim nothing further.

**Do not** name the bit anything the evidence does not carry, and do not promote
"frame start" from the references' *consumption* of it to a statement about what
the device *does*. **UNKNOWN.** Non-blocking: no current work depends on it, and
the runtime reads the bit exactly as both references do. A cheap future test
would be a stimulus whose first pixel is non-black and non-white together with a
capture spanning several frames, so position, count and periodicity are measured
rather than assumed — not scheduled, and not a reason to spend a physical run on
its own.

### U-GBP-035 — how does the presentation path behave over a long real-content session, and what would instrument it? — OPEN (opened 2026-09-21, Issue #39; no instrument yet; not blocking)

**Why this is an item.** Every physical stream run so far lasted under a
minute and was instrumented by the downstream disposition trace (§V5.46,
OGBPDISP2: 4 096 lifecycles, 8 192 events). The playable image of Issue #39
(`play-0001`, INPUT_PATH.md §13) is sized for a session of up to 720 s, and
the trace was taken OUT of it by decision: past ~68 s it would cover a
fraction of the session and count overflow for the rest, and a partial trace
is nearly useless as evidence about that session while still costing memory
and complexity. So the question the trace answered — what Policy A decided,
how often a frame deferred, how deep the deferral went, whether the order
held — has no instrument for a session of minutes with real game content.

**What is established.** Policy A's behaviour over the qualified windows of
the short runs (§V5.49, RUN 4–13); the balance identity and the invariant
checks the runtime keeps counting in every image (STREAMDISP / STREAMINV /
STREAMOWN are in `play-0001` too, as aggregates).

**What is NOT established.** Whether those aggregates suffice to detect a
degradation over minutes; whether a bounded, sampled or windowed trace can be
designed that stays useful at that length; what a real game's frame cadence
does to the deferral pattern. **UNKNOWN.** Non-blocking for Phase 5; it
belongs to Phase 9 (GBI-class functional parity) / Phase 12 (runtime
stabilization), as its own checkpoint, and no run of `play-0001` should be
read as answering it.

---

### U-GBP-036 — why does CONTROL bit `0x01` appear 186–636 µs AFTER the transform write rather than in the original byte, and what causes the sensing? — OPEN (opened 2026-09-22, Issue #47; P2; not blocking Phase 5)

**What is established** (`GBP-HW-274`, `GBP-HW-275`, both FACT for the
observation). With a Game Boy Color Game Pak inserted, the original CONTROL
byte is `0x92` — bit `0x01` clear, byte-identical to a GBA cartridge's. The
bit becomes set between 185.6 µs and 635.6 µs after the runtime writes the
transform `(v & ~0x10) | 0x0C`, in all 31 stable replicas, and stays set
through teardown, so the restore reads back `0x93` after writing `0x92`. Four
GBA-cartridge runs and one cartridge-less run of the same image hold their
value at the same read points.

**The question, in three parts, none of them answered.**

```text
WHAT triggers it     the transform sets bits 0x04 and 0x08, which the references describe as the AGB's power /
                     reset (REGISTERS.md §3, C for usage). "The GBS-DOL senses the Game Pak type once the AGB is
                     powered" is the obvious reading and it is NOT measured: the A1 IRQ-register write falls inside
                     the same window, and so does plain elapsed time. Three candidate causes, one observation.
WHY NOT AT POWER-ON  whether the bit is simply not sensed before the AGB runs, or is sensed and not exposed at that
                     address, or is exposed and clear for a reason of its own -- undetermined. The 13 cartridge-less
                     and 22 GBA-cartridge runs cannot separate these, because in all of them the bit stays 0.
IS THE WINDOW REAL   the bound comes from two SNAP records 450 us apart; the transition could be anywhere inside it
                     and could differ per cartridge or per power cycle. One run.
```

**Why it matters beyond curiosity.** Any Open-GBP code that reads the cartridge
type at startup would read it WRONG if it read the original byte, and a restore
that compares a read-back against what it wrote will legitimately fail after a
GB/GBC session (`GBP-HW-276`). Phase 7 will need to know when the byte may be
trusted; this item is where that question lives until then.

**Cheapest next step, NOT scheduled and NOT authorised here.** A repeat of RUN
24 with the same cartridge tells whether the window reproduces; a second,
different GB/GBC cartridge tells whether it is the medium. Both are Phase 7
work with a pre-registration of their own. Related: `U-GBP-017`,
`GBC_PATH.md` §3 and §4.1.

**SECOND DATA POINT 2026-09-22 (GitHub Issue #55). THE QUESTION IS
UNCHANGED.** RUN 27 repeated RUN 24 with the same cartridge and a guaranteed
power cycle, and the bit still arrives late, in the same scheduled bracket, and
persists (§V7.10; `GBP-HW-275`'s amendment). **One thing this item listed is
answered and it is not the question:** *"the bound comes from two SNAP records
450 µs apart … One run"* — it is now two runs, and the bracket is the same.

**Nothing else moves.** The three parts of the question stand exactly as
written: **what triggers it** is still undetermined, because the transform's
power/reset bits, the `A1` write and plain elapsed time all still fall inside
that one bracket — **two runs that agree separate them no better than one**;
**why not at power-on** is untouched; and the bracket is still 450 µs wide,
because it is the probe's own schedule and nothing in either run narrows it.
**A repeat answers "does it reproduce", never "what causes it".**

**ADDENDUM 2026-09-22 (GitHub Issue #52) — the first measurement of how far a
session of `play-0001` actually reaches, and it is not 720 s.** RUN 21 stopped
at `stop=event_store_cap` after **273.918 s**: the event store's 16 384 entries
filled at **59.81 events/s**, which is the published-frame rate (59.61/s) and
not the Operator's input rate (2.91 key changes/s). The frame store would have
bound at ~756 s, `max_deliveries` at ~948 s, and the 720 s safety budget was
never approached. RUN 22 corroborates it from the other side: 202.103 s, ended
on Z, 11 894 events — 73 % of the same cap — and a HIGHER key-change rate than
RUN 21, which is why the cap is not about the pad. `GBP-HW-282`.

**What it adds to this item.** The question here was what a long real-content
session does and what would instrument it. The answer so far is that the
instrument **stops at about 274 s**, a little over a third of the length the
image was sized for, and that what bounds it is an event stream tied to the
frame rate — so any future long-session instrument must either size that store
for the session it intends or sample it. **Nothing is unexplained**, so this
opens no new unknown; it narrows this one.

## U-GBP-037 (P1, opened 2026-09-22 after RUN 30 — **2026-09-22, Issue #64: the instrument this item names is now PRE-REGISTERED, `HARDWARE_TESTS.md` §V9, GBP-AUDIO-002 — NOT RUN, NOT AUTHORISED, the ROM does not exist, and a pre-registration answers nothing; the item STAYS OPEN** — **2026-09-22, Issue #67: RUN 31 EXECUTED. THE 256-BYTE PERIOD IS THE TRANSFER'S, NOT A TONE (`GBP-HW-296`, measured with the APU provably off), and the audio is the modulation ACROSS blocks at the predicted ratio (`GBP-HW-298`). The item's SECOND half is answered — a block is a re-read SAMPLE, not a time series — and its FIRST half changes shape: the rate that matters is the DRAIN rate, 4 096.0 blocks/s from two windows independently. **P1 → P3, and it stays OPEN for the repeat that would make it FACT**) — what the AUDIO region's 256-byte period IS: the sample rate, and whether a block is a time series or a re-read buffer

**The measurement is solid and the interpretation is empty.** RUN 30's 1 280
blocks all carry a two-level square whose period is **exactly 256 bytes**
(`GBP-HW-287`). Nothing in this project says what one byte is worth in time, so
**no frequency can be stated** — and §V8.5's whole prediction rested on an
assumption about that which the run falsified.

```text
what §V8.2 assumed      one 4096-byte block is 0.2442 ms of audio, so a 64 Hz period spans ~64 BLOCKS
what RUN 30 shows       sixteen whole cycles INSIDE one block, and 245 of 256 control blocks byte-identical
what that rules out     the assumed mapping. A source advancing at an audio rate would shift block to block
what it does NOT settle whether the region is a buffer the AGB rewrites in place and the drain re-reads, or
                        a time series at a rate far above audio, or something else
```

**Why it is P1.** Every frequency claim in Phase 6 — the transition, the duty
slope, the envelope — is unreadable until this is fixed, and the two questions
of §V8 could only return "other shape" without it.

**What would close it.** A stimulus whose emission this project controls end to
end: `stimulus/agb-tone`, playing a tone of **known** frequency, changed
between two known values inside one run. The period in bytes then gives the
sample rate directly, and a second tone checks it. **That is the instrument
§V8.5.2 already names for a `CARRIES / OTHER SHAPE` outcome**, and it needs no
new hardware access beyond one run.

**Not to be answered by reading a reference.** Dolphin's model and the Disc's
constants are what `U-GBP-012` already distrusts; this is a measurement.

**2026-09-22, on validation — AN INFERENCE, offered for the next
pre-registration and NOT a finding.** *If* the 256-byte period is the 64 Hz
wave the checker's stop leaves sounding, then one byte is **~61 µs** and a
4096-byte block is **~250 ms of audio** — delivered every **0.244 ms**, a
**~1 000× oversupply**.

```text
what that points at   a RE-READ BUFFER rather than a time series: the drain would be re-reading a region
                      the AGB refills far more slowly than it is read, which is also the simplest reading
                      of RUN 30's 245-of-256 byte-identical control blocks
what it is NOT        established. The premise ("the period IS the 64 Hz wave") is exactly what this item
                      says is unknown, so the arithmetic cannot be used to prove it -- that is circular,
                      and it is written here as an inference precisely so nobody inherits it as a fact
```

**AND IT GIVES `stimulus/agb-tone` A SHARP PREDICTION TO TEST, which is worth
more than the inference itself:** a tone of **known** frequency, changed between
**two** known values inside one run, should move the period **proportionally**
— halve the frequency and the period in bytes doubles. **If it does, the sample
rate follows directly and this item closes; if it does not, the buffer reading
is wrong and something else is producing the pattern.** Either way the run
decides, and the prediction is written down before it — which is the only form
this project accepts.

**2026-09-22 (Issue #64) — that prediction is now FROZEN in `HARDWARE_TESTS.md`
§V9 and executable in `tools/v9tone.py`, both written before the ROM exists.**
The instrument is `stimulus/agb-tone`, two notes in one run:

```text
F1   n = 1024   128.0 Hz exact   predicted 128 bytes   }  the ratio is 4.000000, and a RATIO of two
F2   n = 1792   512.0 Hz exact   predicted  32 bytes   }  periods is INDEPENDENT of the sample rate
THE TEST NEEDS NO RATE AND ASSUMES NONE -- the only reason one session can decide a question about a
rate nobody has measured. The sizing assumption above chose the notes and decides nothing.
RATIO HOLDS          this item's first half CLOSES and the rate follows from either window (R = f x period)
RATIO DOES NOT HOLD  the re-read-buffer reading is WRONG, the second half is answered in the NEGATIVE,
                     and that is a RESULT rather than a failed run
```

**A factor of FOUR, not two, and §V9.3.2 says why:** a half-period miscount
produces *exactly* a factor of 2, so a factor-2 design could not distinguish
*"F2 is twice F1"* from *"I counted the other edge"*. **Nothing is
authorised** — the ROM does not exist and no run is scheduled.

**2026-09-22 (Issue #67) — RUN 31 ANSWERED THE SECOND HALF AND MOVED THE
FIRST.** §V9's own frozen question returned `RATIO DOES NOT HOLD`
(`GBP-HW-297`) — the within-block period is 256 bytes in all 1 280 blocks and
never follows the note. **And the audio is there, on the feature §V9 did not
measure:**

```text
the 256-byte cell   is the TRANSFER's. It is present with the APU PROVABLY OFF (GBP-HW-296), so it is
                    not a tone and never was. The presses change its CONTENT, never its LENGTH.
the audio           is the modulation ACROSS blocks: 32 blocks at 128.0 Hz and 8 at 512.0 Hz, ratio
                    4.0000 -- §V9's predicted ratio, on the wrong feature (GBP-HW-298)
so a block          behaves as ONE SAMPLE of the AGB's output -- a RE-READ snapshot, which is this
                    item's second half answered in the AFFIRMATIVE rather than the negative
and the rate        is the DRAIN rate: 4 096.0 blocks/s, recovered independently from two windows at
                    two frequencies, against §V7.8.6's measured cadence of 4 094.4/s
```

**Why it does not CLOSE.** One run, one cartridge, and one of the two windows
needed a slice chosen **after** seeing the data to pass §V9.8's uniformity rule
(§V9.15.5 names that). **What closes it: a repeat, and a THIRD frequency** —
the same construction on a note neither run has used, predicted before the run,
which turns two points into three. The priority drops to **P3** because nothing
in front of Phase 6 now depends on it.

**What is still genuinely unknown:** what the 256-byte cell's internal
structure means, and why its transition bytes differ between cartridges
(`{01, FE}` in RUN 30, `{03, 07, FC}` in RUN 31).

## U-GBP-038 (P3, opened 2026-09-22 after RUN 30 — **ANSWERED AND CLOSED 2026-09-22, Issue #67, by RUN 31 read together with RUN 30: the press was not special, it was EARLY. The AUDIO window does not carry the cartridge's sound until (10.045, 12.547] s after the CONTROL transform, `GBP-HW-299`. The MECHANISM is not determined and moves to `U-GBP-039`**) — why the FIRST press changed nothing in its window while the next three did — **REOPENED 2026-09-23, Issue #72: RUN 32 refutes the bound as a property of the path (`GBP-HW-307`) and `GBP-HW-306` shows our own ROM emptied one of the windows the bound was drawn from. The question is live again and its epoch has changed** — **2026-09-23, Issue #78: RESCOPED. With the repaired instrument NO window is lost (RUN 33, RUN 34), so the phenomenon is not a property of the path (`GBP-HW-311`). What stays open is why RUN 30's press 1 and RUN 31/32's press 2 were dead**

**2026-09-23, Issue #72 — REOPENED, and the epoch has moved.** Two things
happened at once and they pull in the same direction.

**First, the bound is not fixed.** RUN 32's presses landed at +26.161, +29.264,
+32.634 and +36.021 s after the CONTROL transform, and its dead/alive boundary
is **(29.264, 32.634] s** — **disjoint** from the (10.045, 12.547] recorded
here. Measured from the CONTROL transform the three runs have **no common
bound** (`GBP-HW-307`).

**Second, part of the old evidence base was our own instrument.** `GBP-HW-306`:
`agb-sweep` does not emit on its **first press**, reproduced by the Operator on
his own Game Boy Advance with no GameCube involved — and `agb-tone`'s
`apu_play()` is structurally identical, so **RUN 31's press 1 was very probably
silent for a ROM-side reason, not a path-side one.** A bound drawn partly from
windows our ROM emptied cannot be read as a property of the path.

**What survives, and it is tighter.** Measured from the AGB's **first
emission** — which `GBP-HW-306` places at press **2** — RUN 31 and RUN 32 agree:
the window in which emission begins carries nothing and the next one carries,
+3.320 s and +3.370 s later.

```text
READING A  ELAPSED TIME from the first emission     ~3.1 to ~3.4 s before anything carries
READING B  WINDOW ORDINAL from the first emission   the emitting window is dead, the next is alive
```

**Both fit RUN 30, RUN 31 and RUN 32, and no run separates them**, because every
run so far spaced its presses 3.1–3.4 s apart — the spacing §V8.10 asked for,
for an unrelated reason. **THE SEPARATOR IS A SHORT GAP AFTER THE FIRST EMITTING PRESS** — corrected
2026-09-23 (Issue #75); the first version of this entry said a LONG one and was
wrong, because a long gap is where the two readings agree. They disagree only on
a window that opens **before** T. §V13 pre-registers a **ladder** of gaps, so the
run either refutes ORDINAL outright or tightens T by about an order of magnitude.
It needs **no new ROM and no new image**, and the ROM defect is fixed
(`sweep-0002`, §V11.17) so press 1 is no longer wasted.


**2026-09-23, Issue #78 — RESCOPED, and the question is now small.** RUN 33 and
RUN 34, both on `sweep-0002`, **carried from the emitting window on every
press** — eight presses, no window lost (`GBP-HW-311`). So ORDINAL and ELAPSED
are both refuted **as properties of the path**, and the operational rule this item
produced — wait, then space generously — **has no known job left**.

**What remains open is two dead windows in past runs:**

```text
RUN 31 / RUN 32 press 2   the Operator's GBA says sweep-0001 was AUDIBLE from press 2, yet the
                          capture's window 2 carried nothing
RUN 30 press 1            the Enhanced Control Checker, a different cartridge, not our ROM
```

**Leading candidate, SUPPORTED and NOT ESTABLISHED:** `U-GBP-040`'s first-press
defect left something in a state the speaker does not reveal and the AUDIO path
does. **Its test:** re-flash `sweep-0001` and run it with five-second spacing —
windows 1 and 2 dead again means the defect reproduces it. **It costs a flash, and
that is the Operator's to spend.** P3 unchanged.

## U-GBP-039 (P2, opened 2026-09-22 after RUN 31) — WHY the AUDIO window carries nothing for the first ~10–12 s after the CONTROL transform — **CLOSED 2026-09-23, Issue #78: PREMISE REFUTED. It asked for the mechanism of a delay counted from the CONTROL transform; `GBP-HW-307` refuted that epoch and RUN 33 and RUN 34 show no delay at all once the instrument works (`GBP-HW-311`). Nothing is left for it to explain; the residue is `U-GBP-038`'s two past windows**

`GBP-HW-299`: across two runs, two cartridges and two instruments, the AUDIO
window carries the cartridge's sound only from somewhere in **(10.045,
12.547] s** after the CONTROL transform. RUN 31 makes the gap unambiguous: its
ROM enabled the APU at **+5.924 s** and the Operator's on-screen counter
confirms the ROM was running, so **the AGB was emitting for about six seconds
before the window carried anything.**

```text
WHAT IS KNOWN        the bound, from two runs; that it does not depend on which press; that the window
                     carries the transfer's 256-byte cell throughout, before and after (GBP-HW-296)
CANDIDATES, none measured
   an initialisation the GBS-DOL performs on the audio path, finishing at its own pace
   a buffer that must fill before the region reflects anything
   an enable this project has never written, which something else eventually performs
   an AGB-side settling that has nothing to do with the GBP
WHAT WOULD NARROW IT CHEAPLY
   a run whose presses start LATER and are spaced WIDER: the bound tightens with no new code
   a run with the SAME image and NO cartridge: if the transition still happens, it is the path's and
     not the cartridge's, and the cartridge-less archive already holds the AUDIO blocks to compare
   the bound against t_capture_start rather than the CONTROL transform, which the existing logs
     already carry and which costs one analysis rather than one run
```

**Why P2.** It bounds every future audio experiment's action list — a run whose
presses land inside the first twelve seconds measures nothing — and the current
action list (§V9.12) does not say so.

**2026-09-22 — THE CHEAPEST PROBE HAS BEEN RUN, and it is a NEGATIVE result**
(`GBP-HW-302`). Measuring the same bound against `t_capture_start`,
`t_probe_enter` and `t_program` instead of the CONTROL transform, over the two
logs already in hand:

```text
t_program        -0.055 s from t_control        bound (10.099, 12.602] s
t_probe_enter    -0.013 s                       bound (10.058, 12.560] s
t_control         0.000 s                       bound (10.045, 12.547] s
t_capture_start  +0.108 s                       bound ( 9.937, 12.440] s
```

**All four epochs are within 163 ms of each other and the bound is 2.5 s wide,
so the probe cannot separate them.** In this image the program's start, the
CONTROL transform and the capture's start are **confounded**, and no analysis
of these logs can tell which one the delay is counted from. **The cheap probe
is exhausted**, and knowing that before a run is spent on the assumption is
what it bought.

**WHAT WOULD SEPARATE THEM, and it already exists as a build option.**
`gbp_vstate_probe.h`'s `prehandler_wait_ms` inserts a bounded wait **after**
stage A has put CONTROL in its running shape and **before** the handler is
installed, with physical precedent at 5000 ms (`GBP-HW-120`). Setting it moves
`t_capture_start` away from `t_control` **by the wait**, and the delay then
follows whichever epoch owns it:

```text
if the delay follows t_control           it is the GBP's own initialisation after the transform
if it follows t_capture_start            it is something the service path's start sets in motion
if it follows neither and stays ~11 s    it is elapsed time since power, and neither epoch matters
```

**It costs a rebuild with an existing option and no new code.** Not authorised
here; it is the obvious content of the next pre-registration that touches this
item, and it can ride on any audio run rather than needing one of its own.

**2026-09-22, Issue #68 — PRICED AGAINST THE NEXT RUN, AND DEFERRED.** §V10.7
assesses the rider on GBP-AUDIO-003 and recommends **against** it, for a reason
that is not its cost: `prehandler_wait_ms` moves the very delay that decides
whether the amplitude sweep's four windows carry anything, so riding it there
would put the primary question's **precondition** under the rider's variable.
§V6.13's precedent — two questions, separate gates — was two readings of **one
image and one run**; this needs a second image and therefore a second boot.
**The item is unchanged and still P2**: what moves is that the rider now has a
price and a stated better moment — any later run that already needs two images,
or one whose question does not depend on when the window starts carrying.

**2026-09-23, Issue #72 — the question this item asks has changed shape.** It
was opened to ask *why* the delay is counted from the CONTROL transform.
`GBP-HW-307` shows it is **not** counted from there at all: RUN 32's interval is
disjoint from RUN 30's and RUN 31's, and the epoch that fits is the AGB's own
first emission. **`prehandler_wait_ms` was the separator for the old epoch and
is not the separator for the new one** — varying the press spacing is
(`U-GBP-038`). This item stays open for the mechanism and its rider stays
deferred; what changed is that the epoch it was going to test has been refuted.


**2026-09-23, Issue #78 — CLOSED, PREMISE REFUTED.** This item asked *why* the
AUDIO window carries nothing for ~10–12 s after the CONTROL transform. RUN 32
refuted that epoch (`GBP-HW-307`), and RUN 33 and RUN 34 show **no delay at all**
once `U-GBP-040`'s defect is fixed (`GBP-HW-311`). **There is no phenomenon left
for a mechanism to explain.** `prehandler_wait_ms` — the separator it named —
would have been testing an epoch that no longer exists. The two unexplained dead
windows belong to `U-GBP-038`, rescoped. **Closed as refuted, not as answered.**

## U-GBP-040 (P1, opened 2026-09-23 after RUN 32 — an INSTRUMENT defect, reproduced on hardware off the GBP entirely) — why does the AGB emit nothing on the FIRST press after the master enable's 0 → 1 transition?

**`GBP-HW-306`.** The Operator put `agb-sweep` in his own Game Boy Advance:
*"testei no console no primeiro toque nada é reproduzido também .. só a partir
do segundo"*. **No sound on press 1; sound from press 2 onward.** No GameCube
involved, so this is **our ROM**, not the path — and `agb-tone`'s `apu_play()`
is structurally identical, so it is very probably not new to `agb-sweep`.

**P1 because it costs a window in every run of this family**, and because
`U-GBP-038`'s evidence base includes windows it may have emptied.

```text
WHAT IS RULED OUT   the write ORDER. apu_play() sets SOUNDCNT_X's master enable BEFORE any channel
                    register, which is exactly what GBATEK requires (external/gbatek/gba.md:
                    "all PSG registers at 4000060h..4000081h are reset to zero (and must be
                    re-initialized after re-enabling sound)"). The ordering is right.
WHAT IS KNOWN       the ONLY difference between press 1 and press 2 is the master enable's 0 -> 1
                    transition. Every other register write is identical.
WHAT IS NOT KNOWN   the mechanism. NOT GUESSED HERE.
WHAT mGBA SAYS      it would NOT have caught this. GBAAudioWriteSOUNDCNT_X and GBAudioWriteNR52 take
                    their reset branch only when the enable is CLEARED; on 0 -> 1 the model sets
                    frame = 7 and honours every subsequent channel write, so it emits where the
                    hardware does not. A static reading of external/mgba, not a run, and a MODEL.
```

**The cheapest probes, in order, and none is authorised here:**

```text
1  write apu_play()'s channel registers TWICE on each press -- idempotent for presses 2-4, and it
   PRESERVES "silent until the first press" exactly, so it settles nothing the Orchestrator owns
2  split the first press: enable on the press, write the channel registers on the NEXT frame edge
   -- also preserves silence until the first press
3  only if both fail: enable the master at BOOT with no channel triggered. THIS CONFLICTS with the
   "silent until the first press" requirement (Issue #65, carried into #70) and is the Orchestrator's
   to decide, not ours -- it would change what the control window observes
```

**Each is verified the same way and it costs nothing:** §V11.15.6's step 0.5, on
his own console, before any GBP run. **That step — his own idea — would have
caught this before RUN 32.** Related: [[U-GBP-038]], and `HARDWARE_TESTS.md`
§V11.16.8.

**2026-09-23, Issue #73 — PROBE 1 IS BUILT, AND IT MEASURES ITSELF**
(`HARDWARE_TESTS.md` §V11.17, `sweep-0002`). **The item STAYS OPEN**: a fix that
has not been on hardware answers nothing.

Every press now applies the register set **twice, unconditionally and without a
branch**, so no press takes a different path from another — which is the very
thing that went wrong. Between the two passes the R/W registers are **read back**
and one bit per register is kept for the screen:

```text
0x01 SOUNDCNT_X   0x02 SOUNDCNT_H   0x04 SOUNDCNT_L   0x08 SOUND1CNT_H
```

**`0x04` is the one the hypothesis implicates**, because `SOUNDCNT_L`
(0x4000080) is **inside** GBATEK's 0x60..0x81 reset range and carries the
channel's left/right routing, while `SOUNDCNT_H` (0x4000082) is outside it. A
channel that triggers with `SOUNDCNT_L` still zero runs and reaches neither
output. **If the mask reads `0x04` on the first press and clear on the others,
the mechanism is measured; if it reads clear and the sound is fixed anyway, the
defect is fixed and UNEXPLAINED — and this item stays open saying so.**

**Probe 3 was NOT taken.** Enabling the master at boot would change what the
control window observes at rest, and that window is the baseline RUN 30, RUN 31
and RUN 32 share. It remains the Orchestrator's call if probes 1 and 2 both
fail.

**2026-09-23, Issue #78 — the fix may have had a SECOND consequence nobody
predicted.** With `sweep-0002` the dead windows `U-GBP-038` described are gone
(`GBP-HW-311`). **If** the defect caused them, "fixed and unexplained" also fixed
`U-GBP-038`'s phenomenon — **SUPPORTED, NOT ESTABLISHED**, and it leaves RUN 31/32
press 2 and RUN 30 press 1 unexplained. The item stays open: the mechanism of the
first-press silence is still not determined.


## U-GBP-041 (P1, opened 2026-09-23, Issue #82) — are the sixteen slices of an AUDIO block UNIFORM in time, and is the two-slice transition grid the path's or the source's?

`GBP-HW-315`: slice order is time order between two-slice groups, and every
transition in RUN 33 / RUN 34 falls on an even slice. Uniform spacing would make
the slices 65 536 per second and the grid 32 768 per second. **The archive cannot
measure it**: every programmed tone has a whole-number period in blocks, so all of
a tone's edges share one k. A verifier's cross-press test (AGB frame = 68 blocks +
9.25 slices if uniform) fits at p ≈ 0.6–0.8 % but needs a model of the ROM and one
post-hoc allowance, and is recorded in §V18.4 as a HYPOTHESIS, not evidence.

**Why it matters to the drain:** if the slices are uniform, a runtime that reads
whole blocks already has audio at eight times the H-PWM rate, and the decoder
could use it. **What settles it (hardware):** a tone whose half-period is not a
whole number of two-slice units, so that k moves from edge to edge by a
predictable amount. Even that resolves only the 32 768/s grid, unless the
quantisation is the source's.

## U-GBP-042 (P1 → **P3**, opened 2026-09-23, Issue #82; **ANSWERED FOR N = 0x20 by RUN 37, Issue #91: NO** — 0x100 and 0x400 untested, the mechanism unknown, no longer blocking) — can the AUDIO block (index 0x8) be read SHORTER than 0x1000, and does the device then deliver the next block normally?

Every physical AUDIO read so far is the whole 0x1000: this project's 272 145 in
RUN 33 / RUN 34, the Start-up Disc and GBI (`GBP-AUD-001`). The transport accepts
any 32-byte multiple (`read_bulk`), but a shorter read has **never been
observed**. It matters because it is the difference between moving 16 MiB/s and
moving less. The data side does not rescue it: one slice reproduces the block
sample only where the block is flat, and never at an edge (§V18.5). **What
settles it (hardware):** one run that reads fewer bytes at index 0x8 and counts
delivered blocks against elapsed ticks. **Not authorised here.**

**2026-09-23, Issue #84 — THE TEST IS NOW PRE-REGISTERED (`HARDWARE_TESTS.md`
§V19, `QUESTION A`), and the item stays OPEN because a pre-registration answers
nothing.** GBP-AUDIO-005 sweeps `N` over {32, 256, 1024} bytes — all legal
multiples of the 32-byte DMA granule — low to high, stopping at the first
`SYNC-LOST`. The instrument is `GBP-HW-313`: a programmed tone whose decoded
period is exact if and only if the path stayed **sequence**-synchronised.
`sample(N) = popcount(N bytes read) * 4096/N` is frozen, and so is the thing that
would otherwise have refuted this item by accident: **a silent PHASE A reports
INCONCLUSIVE, never SYNC-LOST** — *"nothing was playing"* and *"the short read
broke it"* are different answers (AMENDMENT 2 B3). Edge degradation is measured
beside the verdict and never folded into it, because §V18.5 established that a
single slice cannot represent an edge block. **Not run, not authorised there.**

**2026-09-23, Issue #91: RUN 37 ANSWERS IT FOR N = 0x20, AND THE ANSWER IS NO**
(`HARDWARE_TESTS.md` §V19.14.5, `GBP-HW-321`).

- **The control held.** CONTROL2, immediately before, had 63 periods, all exactly
  32.
- **N = 0x20 failed.** 12 289 reads of 32 bytes decoded a period of 4–8 in all
  1 537 periods, against the programmed 32: **SYNC-LOST**.
- **The full-read window after it did not come back clean.** 63 of 64 periods were
  32 and one was 18, a 14-block discontinuity whose position is not recorded:
  **NO-RECOVERY** by the frozen rule.
- **The sweep stopped there, as frozen,** so **0x100 and 0x400 are untested**.

**Still open:**
- **why** 32-byte reads decode as 4–8: the device's sequence, or a 32-byte slice
  failing to carry the level (`U-GBP-043`);
- **where** the 14-block discontinuity fell;
- the two larger N.

**Priority drops to P3, because nothing is blocked any more.**
- The runtime reads whole AUDIO blocks, and RUN 37's D1 shows the drain carries
  16.8 MB/s in steady state (`GBP-HW-319`).
- A future experiment on N = 0x100 / 0x400 must start from a fresh power-cycle and
  run one N per session. Full reads did not recover cleanly after N = 0x20, so the
  steps cannot share a session.

## U-GBP-043 (P3, opened 2026-09-23, Issue #82) — the 1–3-bit spread between slices of a flat block, and whether a slice's bit arrangement carries anything its count does not

`GBP-HW-314`. The spread is present in both silent control windows (spread 1
only). It is only ever above the mode in RUN 33 (+1, once +2) and −2 to +3 in RUN 34, where it
touches 85 % of flat blocks against 23 %. It shows no bunching by slice index.
3 059 slice pairs have equal counts and different bytes, and each run has its own
slice-opening family (`07 03 …` in RUN 33, `01 01 …` in RUN 34; the runs also
rest at different levels, 1025 and 1024). **Cause not established; no decode
depends on it today.**

## U-GBP-044 (P2, opened 2026-09-23, decided on Issue #84) — what produces the 13 start-up stalls of the shared service path, and where are the three the log does not locate?

`GBP-HW-317`, FACT about the archive, is that the start-up signature is invariant.
All seven archived sessions (play-0001 RUN 21/22/25/26, stream-0016 RUN 33/34/35)
show 13 incomplete frames, 26 resyncs and the same four PRESERVED episodes, opening
at frames 8, 30, 90 and 150 and closing by frame 197, with `store_full=1
descriptors=4 raw_slots=16`. That holds however long the session runs (27.9 s to
273.8 s) and however many later episodes it has (11 to 540 not preserved). The
later episodes produce no incomplete frame.

**The HYPOTHESIS, not established.** Ten of the 13 are visible in the event log:
frame 0, then the open, +3 and +6 frames of the first three preserved episodes. The
same pattern at the fourth preserved episode (open 150) would put the other three
at about 151, 154 and 157, inside the range the log does not print (`EVENTS
shown=192`: its first 128 and last 64 events). So 13 = 1 + 3 × 4 fits every
session. That is consistent with PRESERVING an episode's raw frames (`raw=4/4`) being
what stalls the service, and with the stalls ending once the 4-descriptor store is
full. It is an arithmetic fit with three frames unlocated and no cost measured. That
the four episodes sit at the same frames in every session is consistent with the
AGB's start-up, which is the same for any cartridge; that is untested too.

**Why it matters.** If the preserved-episode capture is the cause, then the
runtime's start-up loss belongs to the research instrumentation, not to the
service, and a runtime without raw episode preservation would have none. §V19's
D1 is unaffected either way: A4.5 keeps every start-up stall out of its windows by
construction.

**What would settle it:** a log that prints the events in the unprinted range, or
the same image with raw episode preservation disabled, compared like for like.
Neither is planned.

## U-GBP-045 (P1, opened 2026-09-24 after RUN 38, Issue #99) — what costs the composed runtime's drain about 25 AUDIO blocks per second that the drain alone did not lose, and is that what the Operator heard as "vibrando"? — **2026-09-24, Issue #100: ONE cadence orders both losses, the AI chunk cycle (GBP-HW-327, CORROBORATED); which step of it is open** — **2026-09-24, Issue #103 (RUN 39): `P` names `produce` (GBP-HW-329); the direction, and K at the VIDEO resolution, are open**

**What is FACT.**
- **The composed image drained less than the drain alone.** RUN 38's `live-0001` (the
  drain, decode, resample and AI chain) drained 4 060 to 4 081 AUDIO blocks in every
  whole second of a 64 s window. That is a mean of 4 070.59/s, with 1 626 blocks not
  drained (`GBP-HW-322`). RUN 37's `drain-0001`, the same service path without the
  chain, drained 4 096 ± 1 (`GBP-HW-319`).
- **The losses are small and many, not stalls.** No gap between decoded blocks
  exceeded 0.537 ms, which is 2.2 block periods.
- **The video capture also lost frames.** The session's frame capture counted 82
  incomplete frames, against the start-up signature's 13 (`GBP-HW-317`).
- **The ring hid the loss.** The correction band kept the ring level with 1 965
  duplicated samples (`GBP-HW-324`). The Operator, having been shown figures that said
  otherwise, reported the tone "um pouco vibrando" (`GBP-HW-326`).

**The HYPOTHESES, none established.**
1. **The chain's work costs the drain.** `live-0001` is `drain-0001` with its drain
   module replaced by the chain (`HARDWARE_TESTS.md` §V22.10). The cost would then come
   from the chain's work in the pump slot: producing and resampling 1 000-frame chunks,
   handing them to the AI DMA, and servicing its interrupt. Which of these is not
   known. This is a single comparison of two images that each ran once.
2. **The duplications and drops are what he heard.** The ~30.7 duplicated samples and
   ~25.4 missing blocks per second, about 56 one-sample discontinuities per second in a
   128 Hz tone, would be what the Operator heard. His own hypothesis is his speaker or
   the volume.

**Why it matters.**
- While coverage stays below D1's 0.999, `QUESTION L` cannot be decided, and it stays
  INCONCLUSIVE.
- The played tone carries discontinuities at tens per second.

The output leg is not in question: L2 is bit-exact and C shows no underrun.

**What would settle it.**
- For hypothesis 1: the same image with the chain's per-chunk work moved or timed,
  compared like for like against `drain-0001`, or the pump slot's own cost measured
  in the composed image.
- For hypothesis 2: a run whose drain holds 4 096 ± 1, listened to the same way.

Neither run is designed yet.

**RESCOPED 2026-09-24 (GitHub Issue #100), on top; nothing above is rewritten.** The
fork "one starvation or two" is answered from the archive, at the level of cadence:
**one** (`GBP-HW-327`).
- **The audio losses.** They are phase-locked to the AI chunk period of 31.22 ms, and
  62 % of chunk periods carry one.
- **The video losses.** Every one is detected 1.5–11.7 ms after an AI DMA callback. The
  chance that random frames would do as well is under 1 in 20 000.

What stays open, and is now this item's question:
1. **Which step of the chunk cycle starves the service.** The candidates are the
   chunk's production in the pump slot, its flush and queueing, and the AI DMA
   interrupt. Whether the per-block decode inside the service transaction narrows the
   margin is also open. All are HYPOTHESES; the log times none of them.
2. **Whether individual audio and video losses coincide.** The archive cannot say:
   the kept stream has no absolute time, and a video event is quantised to its frame.
3. **Whether the perturbation the Operator heard is these discontinuities.** This is
   unchanged.

**What would settle 1 and 2** is a run that timestamps, in the one 40.5 MHz timebase:
- each AUDIO gap longer than 1.5 block periods;
- each missing video block;
- each AI callback;
- each chain step, with its start and end.

The image and the conditions stay those of RUN 38, and the timestamps are recorded
read-only. The design sketch is on Issue #100. The pre-registration is the
Orchestrator's.

**CORRECTED 2026-09-24 (GitHub Issue #101).** The "62 %" above is `GBP-HW-327`'s AUDIO
figure as first computed. A transition whose step sample was not drained had its loss
hidden by rounding. Corrected: 306 losses, 206 episodes, 65 % of chunk periods, R 0.957.
The question this item asks is unchanged.

**RESCOPED 2026-09-24 (GitHub Issue #103, RUN 39), on top; nothing above is rewritten.**
Run A (`trace-0001`, §V23) timed the losses, the AI callbacks and the chain's steps in one
timebase. Its observer gate HELD, and the recorder cost at most about 0.3 % of each AI
cycle (`GBP-HW-328`).

**Question 1 — which step.** `QUESTION P` names `produce`: the chain's production step is
the longest recorded activity inside 1 279 of 1 453 loss gaps. Losses and production
steps both sit in the first tenth of the AI cycle (`GBP-HW-329`). What stays open is the
**direction**. A long gap in that phase holds a production step whether or not a block
was lost (96.9 % against 95.9 %). The records therefore fit production delaying the drain,
and equally a longer interval holding more pump passes. The 173 `neither` gaps are
unresolved against the step floor at this resolution (§V23.12).

**Question 2 — one event?** `QUESTION K` says NOT COINCIDENT within one AUDIO block
(`GBP-HW-330`). The frozen window is narrower than the VIDEO channel's own step (1.13 T),
and 19 of 75 distances lie one VIDEO step away. So one event at the VIDEO resolution is
not decided.

**Question 3 — what the Operator heard.** Unchanged.

**What would settle 1** is a separating experiment on the production step, Run B, chosen
by `P`'s answer and pre-registered by the Orchestrator. It needs:
- per-step records without a floor, inside a bounded sample of gaps;
- a way to tell a step that delays the next completion from one that merely falls inside
  a long interval.
