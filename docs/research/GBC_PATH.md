# GB / GBC mode — the static basis for Phase 7 (2026-09-21, GitHub Issue #31)

**Status of this document: research, DESIGN ONLY.** It records two Operator
observations, checks his architectural account against this project's own
consolidated pages rather than adopting it, derives one result from logs the
project already holds, and designs the first GB/GBC experiments with their
gates written before any hardware. **It authorises nothing.** Phase 5 is
current; Phase 7 is two gates ahead; `CLAUDE.md` §26 permits crossing a gate
early only for a blocking feasibility question and none of this is one. No run,
no pre-registration, no code, no evidence id, no status change.

Read with `docs/ROADMAP.md` Phase 7, whose own warning governs everything
below: *"Do not assume behavior observed in GBA mode also applies to GB/GBC
mode."*

---

## 1. The two Operator observations, as his

Both are **OPERATOR OBSERVATION** (`AGENTS.md`'s vocabulary): his report, not a
recorded test, and not promoted by being written down.

**1.1 — a GB/GBC cartridge under the current runtime.** With the stream-series
probe in the `12-stream` slot and a GB/GBC cartridge inserted, the probe
*"simply runs the tests and ends to generate the LOG"*: it runs its normal
course and terminates. **What this separates, and it is worth having:** this is
*mode not supported*, not *the runtime breaks on unexpected media* — no crash,
no hang, no aborted teardown. It is consistent with the code: nothing under
`src/` or `poc/` mentions GB, GBC or DMG anywhere, so GB/GBC handling is work
not started rather than a regression.

**1.2 — the Start-up Disc's L/R behaviour in GB/GBC mode.** On the official
Start-up Disc, **L and R make a GB/GBC game's image fill the screen or not**,
as on a real console. Recorded explicitly as **a recollection of using the
Disc**, not a test performed for this project.

**No log of 1.1 exists in this repository.** `captures/local/` holds 34
physical logs and none of them is a GB/GBC boot (§3 lists what they do hold).
The "free Phase-7 evidence" that a surviving log would have been is therefore
**not available**, and §4.1 says what it would cost to obtain.

---

## 2. His architectural framing, checked against the project's own pages

His framing, relayed: *the GBP is internally essentially Game Boy Advance
hardware, and the GBS-DOL is the part that handles the GBP↔GameCube link and
the signal; so with a GB/GBC cartridge the AGB should recognise it and behave
as the console does, the Disc passing the same commands through.*

```text
WHERE THE PAGES AGREE
  the GBS-DOL's place   docs/hardware/GBS-DOL.md: "the NEC custom chip on the Game Boy Player board that sits between
                        the GameCube HSP and the CPU AGB A". His "handles the link and the signal" is that sentence.
  what it exposes       power/reset of the AGB (CONTROL 0x04/0x08), CARTRIDGE SENSING (CONTROL 0x01 type, 0x02
                        present), keypad injection, video and audio capture, a serial bridge, the Game Pak and sleep
                        events. Every one is a function OVER the AGB, none of them replaces it.
  who runs the game     the AGB does: the board "does no synchronization", the AGB "free-runs at 59.73 Hz", and the
                        VIDEO IRQ "comes at the AGB's rate" (GBS-DOL.md, frame timing). The GameCube side observes.
  the references agree  the Disc and GBI both READ the cartridge-type bit to choose the words "Game Boy" and "Game Boy
                        Advance" (REGISTERS.md §3, bit 0x01, status C). Software that must ask which kind of Game Pak
                        is present is software that expects both kinds to run.
WHERE THE PAGES ARE SILENT, so his account is not confirmed by them
  the AGB's GB core     nothing in docs/ says how a CPU AGB A runs a GB/GBC cartridge -- that it has the CGB
                        compatibility core on-die, how the mode is entered, or what selects it. It is general Game Boy
                        Advance knowledge, not a finding of this project, and this document does not adopt it.
  the stretch's owner   THE SHARPER POINT, and it changes the experiment: on a retail GBA the L / R screen stretch in
                        GB/GBC mode is the AGB's OWN behaviour, not the game's and not the host's. If that also holds
                        on the GBP's AGB, then the Disc is not "passing a command through" -- it is injecting L or R
                        through the KEYPAD window exactly as it does in GBA mode, and the AGB does the rest. THIS
                        PROJECT'S RUNTIME ALREADY INJECTS THAT WORD (GBP-KEY-010; the routing FACT of §V7.4), so the
                        prediction of §4.2 needs no new runtime capability at all -- which is what makes it cheap.
                        It is a PREDICTION, not a claim: the GBP's AGB may differ, and the experiment is what decides.
  "as the console does" the GBP's video path is not a console's: the AGB's picture reaches the GameCube through the
                        VIDEO window and is scaled and presented by the host runtime (VIDEO_PATH.md). A stretch
                        applied INSIDE the AGB changes the pixels the window carries; a stretch applied by the HOST
                        would not. That distinction is the one the experiment reads, and it is why "the image fills
                        the screen" must be reported as WHAT CHANGED IN THE PICTURE, never as "it looked right".
```

**Nothing in his framing contradicts the pages.** It goes further than they do
in one place (the AGB's GB compatibility core), and that part stays his account
until an experiment or a reference says otherwise.

---

## 3. What the archive already answers, for free — the CONTROL cartridge bits

`docs/protocol/REGISTERS.md` §3 records CONTROL bit `0x01` as the cartridge
**type** flag (Dolphin's model names it `CART_IS_GB`, 1 = GB/GBC game pak; the
Disc reads a "type" status flag; GBI uses it to select the strings "Game Boy"
and "Game Boy Advance") and bit `0x02` as **present** (`CART_INSERTED`; GBI
appends "Game Pak"). Both are **C** — corroborated across the three references,
never measured against a controlled cartridge state on hardware. `U-GBP-017`
(OPEN) says so in as many words: its reading of the idle `0x90` is
*"pattern-matching against a model, not evidence"*, and its **Needs:** list
asks for *"a run with a cartridge"*.

**That run has happened twenty-two times.** Every physical log this project
holds records the original CONTROL byte before any write (`CONTROL semantic
orig=…`), and they split exactly:

```text
orig = 0x90   12 logs   init-0001, initirq-0001, initirqa-0001, initirqb-0001, initirq4-0001, avsvc-0001,
                        video-0001, vstate-0001, -0002, -0003, -0004, vstate-prewait-5000
                        -- the era BEFORE the physical ROM delivery route was resolved (§V3.7). GBP-VIDEO-002's own
                        normative question is "in a session WITHOUT a Game Pak ..." (gbp_vstate_probe.h), so these
                        runs are cartridge-less BY DESIGN and by their own records, not by inference.
orig = 0x92   22 logs   color-0001 and color-0002; stream-0003 .. stream-0015 (runs 2 - 18, including run 8's
                        GBP-VIDEO-005 log) -- every run from the moment a cartridge was in the slot.
the difference          exactly bit 0x02, in every one of the 34 logs, with no exception in either direction.
bit 0x01                READ 0 IN ALL THIRTY-FOUR. Every run used either no cartridge or a GBA cartridge, so the
                        type bit has never been observed in its other state. THIS IS THE GAP A GB/GBC BOOT FILLS.
```

**What this supports, stated carefully and NOT promoted here.** The
present-bit half of §3's table now has a hardware discriminator: 12 runs
without a Game Pak read `0x90`, 22 with one read `0x92`, and bit `0x02` is the
only difference. That is a promotion-grade observation about **bit 0x02**, and
promoting it belongs to a **promotion checkpoint** the Orchestrator opens —
with the reconciliation sweep of `RESEARCH_METHOD.md` run over
`REGISTERS.md`, `GBS-DOL.md` and `U-GBP-017`, and with the caveats the data
carries: one console, one GBP, one flashcart as the only cartridge, and the
reading taken at one instant of one sequence. **This document mints no
evidence id and changes no status.**

**What it does NOT support.** Nothing about bit `0x01`, which has one observed
state; nothing about what `0x90`'s other bits mean (`U-GBP-017` stays open on
`0x10` and `0x80`); nothing about `0x94`; and nothing about GB/GBC mode itself.

---

## 4. The experiments this generates — designed, gates first, NOT authorised

Two, in the order their cost and their dependencies put them. Neither is
pre-registered: a pre-registration is its own checkpoint, written when Phase 7
opens, in `HARDWARE_TESTS.md`, with reserved names and an identity gate.

### 4.1 EXPERIMENT ONE — the cartridge type bit, at the cost of one boot

**Question.** With a **GB/GBC** cartridge in the slot, does the GBP report
CONTROL bit `0x01` set — i.e. does the hardware carry the type flag the Disc,
GBI and Dolphin all read?

**Why it is nearly free.** It needs **no new code and no new image**: every
Open-GBP probe from `init-0001` onward already reads and logs the original
CONTROL byte before it writes anything. The existing staged image would answer
it on the way to doing whatever else it does.

**The prediction, written before the data.**

```text
if the references' reading holds on hardware      orig = 0x93   (0x90 | present 0x02 | type 0x01)
if the type bit is not carried at that instant    orig = 0x92   (indistinguishable from a GBA cartridge)
if the Game Pak is not sensed at all in GB mode   orig = 0x90   (a different and more interesting result)
anything else                                     recorded as it fell; the byte is 8 bits and three of them are H or U
```

**Gates, before the hardware.** The run is admissible if the log carries the
`CONTROL semantic orig=` record and the identity gate passes; the reading is
`INCONCLUSIVE` if the probe aborts before that record, or if the cartridge's
presence in the slot is not declared. **The verdict is the byte**, not an
interpretation of it: `0x93` CONFIRMS the type bit for that cartridge on that
run; `0x92` REFUTES the type bit at that instant and is a divergence from all
three references, which is a finding and not a failure.

**What it would not establish.** Anything about GB/GBC video, input, audio or
timing; anything about another cartridge; the meaning of bits `0x10`, `0x20`,
`0x40`, `0x80`.

### 4.2 EXPERIMENT TWO — the L/R stretch, the Operator's prediction made testable

**Question.** With a GB/GBC game running on the GBP, does a KEYPAD word
carrying **L** or **R**, written by Open-GBP's own input path, change the
picture the VIDEO window delivers — the GB image filling the screen or not —
as the Start-up Disc does it?

**Why this is the right second experiment.** It reuses everything: the input
path whose routing is a physical FACT for all ten word bits (§V7.4), the KEY
record that states what was sent (GBP-KEY-010), and — with `play-0001` — a
session the Operator ends himself, which a GB/GBC game needs as much as a GBA
one. The only new variable is the cartridge.

**The design, in the shape this project uses.**

```text
instrument      a GB/GBC title delivered by the Everdrive GB X7 (§5), chosen so that its normal screen has a large
                uniform border or a distinctive edge -- the stretch must be legible as a CHANGE IN THE PICTURE and not
                as an aesthetic judgement. The title, its form and its boot path are declared per run.
the arms        (a) the game running, no L and no R pressed: the baseline picture;
                (b) L held / pressed as the mode expects; (c) R likewise. Each with its own KEY record line, and the
                Operator reporting WHAT CHANGED in the picture, in his words.
the machine     the KEY record says the word was SENT (the SENT / NOT SENT split of §V7.6.11 applies unchanged); the
 half           VIDEO path says what arrived: a stretch applied inside the AGB changes the pixels of the window, so
                the frame records and, if an image with the sampler is used, the retained frames differ between the
                arms. THE MACHINE CANNOT SAY the picture "filled the screen"; it can say the delivered frames changed
                at the instant the word was sent, which is the falsifiable half.
verdicts        CHANGED       the picture changed in arm (b) or (c) and not in (a), and the KEY record shows the word
                              was sent. MEANS: the AGB acted on an L/R the host injected, in GB/GBC mode.
                NOT CHANGED   the word was sent (KEY record) and nothing changed. A REAL RESULT: it says the GBP's AGB
                              does not apply the stretch, or not at that moment, or not from an injected key -- and it
                              is the first divergence between GBA and GB/GBC mode this project would have measured.
                NOT SENT      the word never left the runtime: an input-path finding, not a GB/GBC finding.
                INCONCLUSIVE  the game never reached a playable screen; the picture is not legible enough to judge; the
                              log is missing; the mode was not entered (§4.1's byte says so).
what it does    that GB/GBC mode "works"; anything about GB/GBC audio, timing, saves or the serial path; anything
 NOT decide     about a second title; Phase 7's acceptance, which is its own criterion and its own assessment.
```

**The order matters.** §4.1 before §4.2: if the GBP does not report a GB/GBC
cartridge at all, the stretch experiment is reading a mode nobody has
established the console entered.

---

## 5. Delivery — the Everdrive GB X7, and what must be verified with it

The Operator has an **Everdrive GB X7** and unofficial GB/GBC cartridges
(titles not identified at the time of writing). The flashcart does for GB/GBC
what the EZ-Flash Omega DE does for GBA: **controlled delivery of a chosen
image**, which is the precondition of every controlled experiment this project
has run (`indexed-0003`, `color-0002`, `coord-0001`, `coord-0002` all reached
the hardware that way). It also opens a **project-owned GB/GBC stimulus**
later, on the same principle as the GBA ones — not designed here.

**WHICH CARTRIDGE IS A GATE ITEM, answered at the launch and not a premise of
this design.** The Operator has the X7 and unofficial GB/GBC cartridges whose
**titles he does not know** — they are "paralelos" of unidentified games. A
design that needed the title settled now would be blocked on something nobody
can answer from here, and would invite guessing later. So it is written as
§V7.6.4 writes it for GBA: the candidates are named when there are candidates,
and at the launch he **declares** which cartridge is in the machine, its form on
the three-value axis, its title **if he can read it from the game's own title
screen**, and how it booted. "Title unknown, an unofficial GB/GBC cartridge,
booted straight in" is a complete and admissible declaration — the attribution
caveat is what it costs, and §4.2's instrument requirement (a picture whose
stretch is legible) is judged on the day from what is on screen, not from a
title nobody has.

```text
to be verified when Phase 7 opens, never assumed
  it fits and boots      the GBP's slot is a Game Boy Advance slot and accepts GB/GBC media; that the X7 specifically
                         is recognised through the GBP -- rather than only in a handheld -- is the first thing its
                         first boot reports, and §4.1's CONTROL byte is exactly that report.
  its menu is in the measurement
                         the X7's own menu runs as GB/GBC software, so launching a ROM from it puts the menu's presses
                         into the KEY record BEFORE anything else -- the same question the EZ-Flash menu raised for
                         GBA, answered there by making the boot screen an explicit topology item and cutting the
                         menu's presses off at the list's first key (§V7.6.11). The same treatment applies.
  the status axis        the three-value axis is kept: an ORIGINAL cartridge / an UNOFFICIAL cartridge / a ROM
                         DELIVERED BY THE FLASHCART. His unofficial GB/GBC cartridges are the second value, the X7 the
                         third, and the attribution caveat rides every citation exactly as it does in §V7.6.4.
  nothing is inferred from the GBA route
                         that a GB/GBC ROM runs correctly from the X7 through the GBP is not established by its
                         working in a handheld, nor by the EZ-Flash working through the GBP. It is checked, per §4.1
                         and by the game reaching a playable screen.
```

---

## 6. What this document does not do

No run, no pre-registration, no reserved name, no identity gate, no code, no
image, no evidence id, no status change, no promotion, no phase-gate crossing.
It does not decide which GB/GBC title is used, it does not schedule anything,
and it does not read the Operator's recollection (§1.2) as a measurement. The
promotion the archive now supports (§3, CONTROL bit `0x02`) is **offered to a
promotion checkpoint**, not performed here. When Phase 7 opens, §4's designs
are the starting point and each becomes a pre-registration of its own.
