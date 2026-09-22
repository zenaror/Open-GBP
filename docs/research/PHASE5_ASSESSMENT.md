# Phase 5 — assessment against its acceptance criterion (2026-09-22, GitHub Issue #42)

**VERDICT: SATISFIED WITH NAMED RESIDUALS.**

This document assesses **Phase 5 — Input** against its own acceptance
criterion, as Issue #17 did for Phase 4. It **reads the result**; it does not
anticipate it. It promotes nothing, mints no evidence id, changes no status and
authorises no run.

**One thing is excluded from the evidence before anything else is weighed.**
The past two days added guards, a skip ledger, promotions, `tools/v7611.py`,
the amendments of §V7.6.15 and §V7.9, and the reconciliation sweep. Those
improved **how this project decides things**. **None of them is a game being
controlled**, and none of them appears below as support for the criterion. If
the criterion is met, it is met by the runs.

---

## 1. The criterion, and how it is read

`docs/ROADMAP.md` Phase 5:

> **A real game can be controlled reliably using the GameCube controller.**

And the Operator's definition of *reliably*, **fixed before any data existed**
and therefore binding on this assessment:

> *"ambos os controles funcionam e tem que apresentar o mesmo comportamento…
> tanto o paralelo como original."*

Two halves: **both controllers work**, and **they present the same
behaviour**. The project operationalised them before the data in §V7.6.11 —
`W` per key, `S` per key, `K` as the machine half of *"o mesmo
comportamento"* — and that operationalisation is what this assessment holds
the evidence against. **Where the evidence is coarser than the instrument the
project chose, that is said rather than smoothed.**

## 2. What the four sessions are

```text
RUN 21   ORIGINAL pad   ordinary play, 273.810 s   ended event_store_cap     GBP-HW-278
RUN 22   GENERIC  pad   ordinary play, 201.995 s   ended Z
RUN 25   GENERIC  pad   the scripted head          ended Z
RUN 26   ORIGINAL pad   the scripted head          ended Z
```

All four on `play-0001` (`2e48ca7`), the image §V7.6.5 names, not rebuilt; the
instrument **Yoshi's Island — Super Mario Advance 3** in all four, his
declaration. §V7.8 is the ingestion record.

---

## 3. Term by term

### 3.1 "A real game" — **MET, with an attribution caveat that could not be lifted**

A retail Game Boy Advance title, played by a person for minutes, twice. Not a
test ROM whose counters this project decodes: **every earlier input result came
from the Enhanced Control Checker**, and this is the first time the instrument
was a game (§V7.6.4; RUN 14 – 18).

**What it does not reach.** §V7.6.4 required the cartridge's **FORM** on the
three-value axis — an original cartridge, an unofficial cartridge, or a ROM
delivered by the flashcart — to be declared per run. It was not declared when
this assessment was first written, which made the runs INCONCLUSIVE on that
item under §V7.6.10's TOPOLOGY gate.

**ANSWERED 2026-09-22, and the answer keeps the caveat** (residual R3, now
closed as a question and permanent as a limit). The Operator's words:
*"EZ-Flash. Gravei a ROM na NOR e coloquei o flashcart no modo B"* — **a ROM
delivered by the flashcart**, the third value of the axis. §V7.6.11 lifts the
caveat only *"if he declares an ORIGINAL"*, so:

**the attribution caveat of §V7.6.11 STANDS, and it is now PERMANENT for this
instrument rather than pending an answer.** Behaviour that looked right cannot
be attributed with certainty between the runtime and the delivery path, and
neither could behaviour that looked wrong. **The distinction matters in a
citation**: this is not a caveat nobody asked about, it is one that was asked,
answered, and kept.

### 3.2 "using the GameCube controller" — **MET, and this is the strongest term**

- **The routing of all ten KEYPAD word bits is a physical FACT on both pads**
  (§V7.4, `GBP-HW-266`…`271`), established by machine on both ends before these
  runs and **inherited here rather than re-argued**.
- **Every one of the ten bits rose on both pads during real play**
  (`GBP-HW-279`): RUN 21 and RUN 22 between them carry 404 and 308 rising
  edges covering all ten keys on each pad.
- **Every write attempt completed**: 54 004 and 39 845 attempts, `completed =
  attempts`, `failed = 0`, `retry = 0`, in both runs (`GBP-HW-280`).
- **The KEY record is clean in all four**: `events = emitted`, `lost =
  truncated = overwritten = 0`, every line parsing with `n` increasing by one.

**What it does not reach.** The FACT covers the **digital click only**
(`trigger_threshold = 0`); nothing about the analogue trigger value is
established, and nothing about ports 2–4, a third pad, or a pad of another
make.

### 3.3 "controlled" — **MET at the level the evidence carries, which is the session and not the key**

The machine half is complete: the runtime polled, encoded and wrote a word for
every key, and the words reached the cartridge (the routing FACT). The human
half is the Operator's, verbatim (`GBP-HW-284`):

> *"o jogo reagiu.... entrando em menus, saindo, pulando cutscenes... ele
> respondeu aos toques de acordo com a tela que ele estava no momento... ou
> seja... agiu normal"*

**A game responded to its player, in character with the screen it was on, for
minutes, on both controllers.** That is what "controlled" asks for and it is
answered.

**What it does not reach, and it is the hinge of this assessment.** The report
is **global**. §V7.6.11 defines `WORKS` **per key** — *"he reports RESPONDED
for the key at a step where the game uses it, AND the KEY record carries
R_b > 0"* — and **`W` is INCONCLUSIVE for every key in all four runs**, not
because anything failed but because the per-key channel was never produced
(§V7.8.5). **A global impression is not ten verdicts**, and this assessment
does not convert it into them.

### 3.4 "reliably" — **PARTLY MET: the Operator's second half is answered by machine, his first half is not measured at the resolution the project chose**

**(b) *"tem que apresentar o mesmo comportamento"* — the machine half is
answered, and cleanly.** `K = AGREE` (`GBP-HW-283`): RUN 25 and RUN 26 produced
**identical ordered press sequences over all 17 presses**, and each equals
§V7.6.9's list press for press. It was computed by `tools/v7611.py`, written
from the frozen text **before these logs existed** and not edited for the
reading — so the answer could not have been tuned to it.

Its limits, stated: 17 presses on an idle screen, **not** minutes of play; and
the Operator's own half is **"no difference between the pads was reported"** —
which is not a comparison he made side by side and is not the same statement as
*"he reported them identical"*.

**(a) *"ambos os controles funcionam"* — supported in aggregate, unmeasured per
key.** Both pads delivered all ten keys with zero failed writes and a game
responded normally on each. What the project's own instrument would have
added — a per-step report joined to the KEY record, per key, per pad — **was
never produced**.

**And one scripted absence bears directly on the word.** §V7.6.9's **step 15,
the closing sweep of the ten keys AFTER minutes of play, was never performed on
either pad.** The question *"do the ten keys still work after minutes of
play?"* — which is what *reliably* means over time — has **no scripted
evidence at all**. The ordinary-play runs carry per-bit counts but no per-key
report and no controlled order.

**Question T is INCONCLUSIVE** (§V7.8.10, Issue #53): the frozen reference was
positional and no statistic was named, so **nothing about the shortened service
pass's timing is established by these runs.** The measurements exist and are
recorded as measurements; they are not a verdict and are not used as one here.

---

## 4. The asymmetries, stated

```text
the instrument         a real game at last -- but its FORM was never declared, so the attribution caveat
                       cannot be lifted (§3.1). One message to the Operator would retire it.
the per-key resolution the project chose W per key BEFORE the data and then did not produce it. The evidence
                       is one step coarser than the instrument it committed to, and the gap is not filled by
                       the aggregate being strong.
the pads               §V7.4's per-bit FACT is asymmetric by run (bits 0-3 on the generic pad, 4-7 on the
                       original, 8-9 on both). RUN 25 / 26 add a sample CONSISTENT with the routing for all
                       ten on both pads -- each sequence matched the list press for press -- but that chain
                       rests on the Operator having pressed the list in order, with no independent witness,
                       so it CORROBORATES and promotes nothing. No status is changed by this assessment.
the trigger path       the digital click only. The analogue value is untouched by everything above.
duration and breadth   one title, one session per pad per half, no repetition, and play-0001 bounded at
                       ~274 s by its event store rather than at the 720 s it was sized for (GBP-HW-282).
timing                 Question T INCONCLUSIVE; T' (§V7.9) is pre-registered and unscheduled.
presentation           U-GBP-035: no instrument for a long real-content session, the disposition trace having
                       been removed from play-0001 by decision (Issue #39).
```

---

## 5. Verdict

**PHASE 5 VERDICT: SATISFIED WITH NAMED RESIDUALS.**

**Why not NOT SATISFIED.** A real retail game was played for minutes on both
controllers; every one of the ten keys reached the cartridge with zero failed
writes out of 93 849 attempts; the two pads produced **identical** ordered
press sequences over the scripted list, by a construction that predates the
logs; and the Operator reports the game behaving normally under his own
criterion. **The phase's goal was demonstrated.** To call that unmet would be
to demand evidence the criterion does not ask for.

**Why not SATISFIED.** The criterion's operative word is *reliably*, the
Operator's definition of it is binding, and **its first half was measured only
in aggregate**: `W` is INCONCLUSIVE per key in all four runs and **step 15 was
never performed**, so *"the ten keys still work after minutes of play"* has no
scripted evidence on either pad. The project chose a per-key instrument before
the data and did not produce it; an assessment that called this SATISFIED would
be quietly lowering the bar the project set for itself.

**The middle is not a compromise, it is the accurate description**: the
criterion is met at the resolution the evidence actually carries — session,
pad, and aggregate — and is not met at the resolution the pre-registration
defined. The residuals below say exactly what is missing and what it costs.

---

## 6. Named residuals — each with what retires it and what that costs

**A residual without a price is a wish.** Each of these is priced in what the
Operator would have to do.

```text
R1  PER-KEY RELIABILITY ON A GAME  (the hinge)
    what is missing   W per key, per pad: "RESPONDED / NO RESPONSE / OTHER / N/A" for each of the ten keys,
                      recorded AT THE TIME rather than remembered afterwards.
    what retires it   ONE run per pad of §V7.6.9's list performed AS ONE SESSION, with the per-step column
                      filled while it happens.
    what it costs     about five minutes per pad, plus a ten-row form in his hand during the session. NO new
                      build, NO new code: play-0001 already writes the KEY record, and the reading is already
                      written (§V7.6.11, tools/v7611.py).
    the catch         it must be filled DURING the run. #52's lesson is that a report gathered afterwards is
                      global by nature, and a global report cannot become ten verdicts.
R2  THE CLOSING SWEEP AFTER MINUTES OF PLAY  (step 15)
    what is missing   any evidence that the ten keys still work after the game has been played for minutes.
    what retires it   the same run as R1 -- it IS step 15 of that list.
    what it costs     seconds, inside R1. Free if R1 is done.
R3  THE CARTRIDGE'S FORM -- **ANSWERED 2026-09-22, AND THE ANSWER KEEPS THE CAVEAT**
    what was missing  which of the three values the instrument was: original, unofficial, or a ROM on the
                      flashcart. Without it the attribution caveat could be neither lifted NOR confirmed.
    what retired it   one question to the Operator. It was asked and he answered, verbatim:
                        "EZ-Flash. Gravei a ROM na NOR e coloquei o flashcart no modo B"
    the answer        THE THIRD VALUE of §V7.6.4's axis: A ROM DELIVERED BY THE FLASHCART -- not an original
                      cartridge. §V7.6.11 lifts the caveat only "if he declares an ORIGINAL".
    THE OUTCOME       **THE ATTRIBUTION CAVEAT IS NOT LIFTED, AND IT IS NOW PERMANENT FOR THIS INSTRUMENT**,
                      exactly as this row's own pre-written handling said it would be. Retiring it would need
                      an original cartridge of a title this project has no reason to believe he owns.
                      RECORDED AS PERMANENT, NOT PAID OFF. It WAS the cheapest item on this list, and it was
                      paid: the answer simply was not the one that lifts anything.
    the distinction   an UNANSWERED caveat and an ANSWERED-AND-KEPT caveat look identical in a citation unless
                      the record says which. This one was asked, answered and kept -- the same distinction
                      GBP-HW-276 / -277 draw between an id CONSIDERED AND LEFT and one OVERLOOKED.
    his two details   volunteered, not asked for by §V7.6.4, and recorded because a later reader comparing
                      runs on this flashcart will want them: THE ROM IS IN NOR, and THE CARTRIDGE WAS IN
                      MODE B. "NOR / Mode B" is this project's own validated delivery route -- §V3.7's
                      route 1, RESOLVED over two physical runs and used by every delivered stimulus since
                      `color-0001` -- so it is cited as that and NOT interpreted further: what Mode B does
                      inside the flashcart is not a claim this project makes.
R4  THE TIMING OF THE SHORTENED SERVICE PASS
    what is missing   any verdict on Question T (§V7.8.10 INCONCLUSIVE).
    what retires it   one run read under T' (§V7.9), whose statistic, content-matching rule and thresholds
                      are already fixed and derived (§V7.9.7).
    what it costs     one session of any length that reaches the service loop; no new build, no new code, no
                      new analysis to write. It can ride on R1's run -- THE SAME SESSION ANSWERS BOTH.
R5  DURATION, REPETITION AND BREADTH
    what is missing   more than one title, more than one session per pad, and a session longer than ~274 s.
    what retires it   repetition, other titles, and -- for length -- resizing play-0001's event store, which
                      binds at ~274 s and not at the 720 s the image was sized for (GBP-HW-282).
    what it costs     the first two are the Operator's time. THE THIRD NEEDS A CODE CHANGE AND A REBUILD, and
                      it belongs to Phase 12 rather than here.
R6  THE ANALOGUE TRIGGER, PORTS 2-4, OTHER PADS
    what is missing   everything: the FACT covers the digital click on two pads in port 1.
    what retires it   a run designed for it, with its own pre-registration.
    what it costs     a checkpoint of its own; nothing here is blocked by it.
```

**R1 + R2 + R4 are ONE run per pad.** That is the shape of the cheapest
closure: two sessions, a form in his hand, and nothing to build.

---

## 7. What Phase 5 does NOT establish, and which phase owns it

```text
audio                                            Phase 6
cartridge compatibility, other titles, GB/GBC    Phase 7 (and GBC_PATH.md's designs)
the physical Link Port                           Phase 8
presentation, scaling, the pixel-perfect goal    Phase 9
duration, margin, long-session instrumentation   Phase 12 (with U-GBP-035)
the analogue trigger, ports 2-4, other pads      not scheduled; a checkpoint of its own
the timing of the shortened service pass         T' (§V7.9), unscheduled
why CONTROL bit 0x01 arrives late                U-GBP-036, not blocking Phase 5
```

---

## 7b. An older ambiguity, closed by the same answer (2026-09-22)

**POINTER, appended 2026-09-22 (GitHub Issue #56), the words below unchanged.**
The principle this section states is no longer only here: it is a method rule,
**"A later direct answer outranks a better reading of an earlier ambiguous
one"** in `docs/RESEARCH_METHOD.md`, with its operational half pointed at from
`AGENTS.md`'s ORCHESTRATOR section. **This section remains the case**, and the
rule cites it. Appending rather than rewriting is #49's convention, applied to
a document instead of a heading.

On 2026-09-21 the Operator wrote *"na RUN estou usando ez-flash e o road rage
paralelo apenas"*, which was relayed as a settled choice of instrument and was
**not** one — the sentence names two things and settles neither for the runs
that were eventually performed. That ambiguity was flagged at the time rather
than resolved, which was right.

**It is settled now, and not by interpreting the old sentence**: the direct
declaration above is about the actual runs, and it says the instrument was a
ROM on the EZ-Flash in NOR / Mode B. The 2026-09-21 wording is left as it
stands, unread; **a later, direct answer about the runs themselves is better
evidence than a better reading of an earlier ambiguous one.**

## 8. The Operator's standing declaration, with its condition

> *"se o comportamento dos 2 gamepads forem iguais. então nao usarei mais o
> original, conforme ja tinha falado (a não ser que seja estritamente
> necessário)"*

Recorded as a standing topology declaration beside the two of Issue #35: **from
now on the generic third-party pad, unless a run strictly requires the
original.** It holds until he announces a change.

**Its condition is conditional on the pads behaving alike, and what now
supports that is `K = AGREE` over the scripted head** — identical ordered press
sequences on both pads, each matching the list. **That is exactly what supports
it, and no more**: it is 17 presses on an idle screen, the machine half only,
and it says nothing about what the game did with them.

---

## 9. The reconciliation sweep (Issue #29), and its outcome

Run with `tools/reconcile.py` over the input evidence the consolidated pages
cite — `GBP-KEY-001`, `002`, `004`, `005`, `008`, `009`, `010`, `GBP-HW-265`,
`GBP-HW-270`, `U-GBP-010` — and over the four ids this ingestion produced.

**Outcome: nothing to correct.** `INPUT.md`, `REGISTERS.md`, `ARCHITECTURE.md`
and `GBS-DOL.md` state the keypad rows at the statuses `EVIDENCE.md` carries,
including the run-scoped qualification on the L/R order. **This is recorded
including the "nothing"**, as `RESEARCH_METHOD.md` requires.

**Two observations, neither a defect.** `GBP-HW-279`, `280`, `283` and `284`
are **cited by no consolidated page** — correct, because this assessment
promotes nothing and no page claims what they carry; **checked and left, not
overlooked.** And the sweep reports `-` for `GBP-HW-284`'s status because its
heading carries `OPERATOR OBSERVATION`, which is not one of the tool's status
words; the entry is correctly labelled and the tool is honest about not finding
a word it knows.

---

## 10. What this assessment does not do

It promotes nothing and mints no evidence id. It changes no status: the routing
stays FACT (run-scoped) exactly as §V7.4 left it, `W` stays INCONCLUSIVE, `T`
stays INCONCLUSIVE, and the per-pad corroboration of §4 is **not** a promotion.
It authorises no run, no build and no hardware. It does not decide the
criterion's meaning beyond the two readings already on the record, and it does
not close Phase 6, 7, 8, 9 or 12 in any respect. **It does not count this
project's tooling as evidence that a game can be controlled.**
