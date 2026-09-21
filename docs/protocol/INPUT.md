# Game Boy Player — KEYPAD / input path (consolidated after GBP-INPUT-001, 2026-09-21)

What GameCube software writes into the KEYPAD window and what the Open-GBP
runtime does with it, consolidated after the first physical KEYPAD writes
(`docs/research/HARDWARE_TESTS.md` §V7.2 — RUN 14 and RUN 15; the static
basis is `docs/research/INPUT_PATH.md`). **Every row carries the evidence id
that supports it and the status `docs/research/EVIDENCE.md` gives it** —
**F** fact (observed on this project's hardware unless marked *(static)*,
*(code)* or *(software)*), **C** corroborated. Nothing whose status is
HYPOTHESIS or UNKNOWN is stated here as a property of the device; open
questions are pointed at by their id and nothing more. A claim measured in
one run is written as such. **The physical record behind this page is
thinner than the video plane's:** two runs of one instrument — a counting
test ROM, not a game — on one cartridge with one generic third-party
controller; this page says so wherever a reader could take more from it.
Addressing, the service cycle and the IRQ register are in `REGISTERS.md`
and `INITIALIZATION.md`; this page does not repeat them.

## 1. The window and the word

| Property | Value | Status | Evidence |
| --- | --- | --- | --- |
| Window | register index 0xC, ARAM address `base + (0xC << 20)`; written and never read by every reference and by Open-GBP — the AGB is the only observer of what arrives | F (static) for the references; F (software) for the runtime | GBP-KEY-001, GBP-KEY-002, GBP-KEY-003, GBP-KEY-006 |
| Transfer | one 32-byte block (the Start-up Disc, Open-GBP), or the first half of GBI's 64-byte block at `base + 0xCFFFE0` whose second half is the IRQ acknowledge; the window answers at offsets `0x00000` and `0xFFFE0` | F (static) for what each writer does; C for the device answering at both offsets | GBP-KEY-002, GBP-KEY-003, GBP-HSP-004 |
| Field | a 16-bit big-endian value in bytes 0x1E–0x1F of the block (`value >> 8` at 0x1E, `value & 0xFF` at 0x1F); the Disc leaves the other 30 bytes as the previous transfer left them, GBI replicates the u16 sixteen times, Open-GBP uses GBI's replicated layout | F (static) for each reference; F (software) for the runtime | GBP-KEY-002, GBP-KEY-003, GBP-KEY-006 |
| Polarity | **1 = pressed** — the opposite of the AGB's KEYINPUT, which reads 0 = pressed | C: the official driver sets bits to press, and an external AGB-side observation sees the same bits cleared at KEYINPUT (bits 4–7 only, GBATEK); in RUN 14 / RUN 15 the cartridge counted presses under this polarity | GBP-KEY-005; GBP-HW-264, GBP-HW-265 |
| A written word reaches the cartridge as key presses | Open-GBP's first physical writes, 2026-09-21: 7 892 and 7 895 completed 32-byte writes in two runs, none failed, none retried, 42 key changes each; the Enhanced Control Checker counted every pressed button at its own counter — all ten buttons across the two runs — with no unpressed counter moving and nothing moving without a press; the checker's tally screen preserved in the runs' full frames decodes to the same counts as the Operator read (Question M = PASS, both runs) | F (hw, run-scoped): two runs, one test ROM, one cartridge, one generic pad; the frames are FACT as data and the Operator's report is OPERATOR OBSERVATION — they agree and are recorded apart | GBP-HW-262 (the writes), GBP-HW-263 (the report), GBP-HW-264 (the frames), GBP-HW-265 (the verdict) |
| Bits 10–15 | never set by any reference; written 0 by Open-GBP | F (static); F (software) | GBP-KEY-002, GBP-KEY-003, GBP-KEY-006 |

## 2. The bit assignment, and its status

| Bits | Buttons | Status | Evidence |
| --- | --- | --- | --- |
| 0–7 | A, B, Select, Start, Right, Left, Up, Down — the KEYINPUT order | C: every reference writes it so (F static, each); bits 4–7 corroborated from the AGB side by the Disc's detection handshake; in RUN 14 / RUN 15 each of the eight, pressed a distinct number of times, was counted at its own counter | GBP-KEY-002, GBP-KEY-003, GBP-KEY-005; GBP-HW-264, GBP-HW-265 |
| 8, 9 | **bit 8 = L, bit 9 = R** — the reverse of KEYINPUT's bit 8 = R, bit 9 = L | C, not FACT — the paragraph below is part of this row | GBP-KEY-004; GBP-HW-261, GBP-HW-263, GBP-HW-264, GBP-HW-265; U-GBP-010 (CLOSED) |

**The L/R order is CORROBORATED, not FACT.** The Start-up Disc, GBI (for
GameCube and N64 pads alike) and Dolphin's model all write L at bit 8 and R
at bit 9 (GBP-KEY-004: the static agreement of two independent
implementations, one official, with the auxiliary model agreeing); RUN 14
and RUN 15, written under exactly that assignment, read the checker's L
counter at 1 and its R counter at 2 after one press of L and two of R — in
the Operator's report and, independently, in the preserved frames (Question O
= AS-ASSIGNED in both runs, GBP-HW-265), which closed U-GBP-010 on its own
condition. **It is not a physical FACT:** the chain still rests on the
Operator having pressed L exactly once, which no machine record contains —
the log counts 42 key changes, not which buttons, and the frames show what
the cartridge displayed, not what the GameCube sent (GBP-HW-265). One log
line — the word written at each key change, binding every press to what the
runtime sent — would close that join by machine (GBP-KEY-009; recorded on
2026-09-21 as not implemented — implemented the same day in `stream-0015`
under Issue #27, GBP-KEY-010, executed nowhere yet; RUN 17 / RUN 18 are
pre-registered to spend it, `HARDWARE_TESTS.md` §V7.3). **Scope of the
observation:** the runtime reads L and R by
their digital click only (`trigger_threshold=0`, GBP-KEY-006), and both runs
were made with a **generic, third-party GameCube controller** — the official
Nintendo pad was not exercised and this project has no data on it
(GBP-HW-261, GBP-HW-265). GBI's sleep value `0x0304` sets bits 8 and 9
together and is not evidence for the order (GBP-KEY-004).

## 3. Write cadence

| Who | Cadence | Status | Evidence |
| --- | --- | --- | --- |
| Start-up Disc | on every HSP interrupt that carries a pending source, right after the IRQ write-back and before the callbacks; and on every 5.000 ms periodic tick while the AGB runs | F (static) | GBP-KEY-002 |
| GBI | once per service pass, in the same 64-byte DMA as the IRQ acknowledge; `KEYPAD := 0` once at thread start; `0x0304` (L + R + Select) on the sleep source | F (static) | GBP-KEY-003 |
| Open-GBP (`stream-0014`) | from the pump slot that opens after the re-arm, never from the interrupt service: a write on the first pass, on every change of the word, and every 5 ms otherwise (the Disc's period), with a one-period back-off after a failed write; in the two runs ≈ 7 850 refresh writes and 42 change writes each, the 32-byte write costing 30 ticks (0.74 µs) at mean and the whole poll-map-encode-write step 169 ticks (4.2 µs) at mean — observational, never a latency figure; whether the 5 ms refresh is needed or sufficient is not established | F (software) for the design; F (hw, run-scoped) for the counts and costs | GBP-KEY-006; GBP-HW-262, GBP-HW-265 |

## 4. This project's controller mapping — POLICY, not a device fact

The GameCube-controller → GBA-button mapping is a choice of this project,
revisable, and nothing about the device follows from it. It is stated here
because a reader of the runtime needs it in one place; its status is **F
(software)** — this is what `src/gbp/gbp_input.c` does — and never a property
of the GBS-DOL. The references disagree among themselves on several rows
(`docs/research/INPUT_PATH.md` §3.1); the policy follows the official
Start-up Disc where it decides.

| GameCube | GBA | Status | Evidence |
| --- | --- | --- | --- |
| A, B, Start, D-pad | A, B, Start, D-pad | F (software; POLICY): 1:1, as every reference | GBP-KEY-006; GBP-KEY-002, GBP-KEY-003 |
| X, Y | Select | F (software; POLICY): the Disc's default; the Operator's recollection of the Disc on this hardware agrees (OPERATOR OBSERVATION, a recollection) | GBP-KEY-006; GBP-KEY-002; GBP-KEY-007 |
| L, R | L, R | F (software; POLICY): on the digital click only; an analogue threshold is an option, off by default | GBP-KEY-006 |
| Main stick | D-pad beyond ±48 | F (software; POLICY): a threshold, not evidence; opposite directions held together are cleared, as the Disc's setter does | GBP-KEY-006; GBP-KEY-002 |
| Z | nothing | F (software; POLICY): reserved for the runtime's own use, never sent; the Disc reserves it for its menu | GBP-KEY-006; GBP-KEY-007 |
| C-stick | nothing | F (software; POLICY): no reference maps it by default | GBP-KEY-006 |
| Port | port 1 only | F (software; POLICY): the smallest correct thing; GBI reads four | GBP-KEY-006 |

## 5. Not established — pointers only

Input latency of any kind (no figure, no ordering claim; the instrument the
latency question needs is the project-owned stimulus recorded in
`docs/research/HARDWARE_TESTS.md` §V7.1.10, not started); whether the 5 ms
refresh is needed or sufficient; the physical routing of bits 8 and 9 — not
FACT; GBP-KEY-009 names the one log line that would carry it, implemented in
`stream-0015` (Issue #27) and not yet run — RUN 17 / RUN 18 (§V7.3) are the
pre-registered runs that could; behaviour
with the official Nintendo pad, any other pad, port or cartridge; rumble and
the GBP-aware features; the Link Port; a real game — Phase 5's acceptance
criterion ("a real game can be controlled reliably using the GameCube
controller") is **not assessed** by the two runs, which used a counting test
ROM (GBP-HW-265). The one reporting defect the runs exposed, the clipped
`ENVINPUT` log line, is a software finding (GBP-KEY-008), not a device
property.
