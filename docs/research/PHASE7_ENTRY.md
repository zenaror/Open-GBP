# Phase 7 entry — GBA breadth, GB/GBC mode and the GBP-aware features, assessed (2026-09-29, GitHub Issue #143)

**Status: research, DESIGN AND ASSESSMENT ONLY. It authorises nothing** — no
build, no image, no hardware, no pre-registration, no reserved run name, no
evidence id, no status change, no promotion. Phase 7 is **not entered** by this
document (the precedent is `PHASE6_ENTRY.md`, Issue #45). It was written while
RUN 58 (Issue #142) waits for the Operator, and it touches nothing that run
depends on: no card, no slot, no pin, nothing under `poc/gbp-audio-v28/`,
`src/audio/` or `tools/v28*.py`.

**THE HEADLINE: the first Phase 7 step is not a run, and the three families are
not at the same distance.** GBA breadth is *composition and volunteers* — the
parts exist, the vehicle does not, and every row of the matrix is the Operator's
to declare (§1, §2, §5). GB/GBC is *a policy problem before it is a measurement
problem*: all four GB/GBC boots this project holds ended at a guard that the
runtime wrote for GBA, so no picture, no input and no audio has ever been
observed in that mode (§3). Rumble is *not reachable from Phase 7 alone*: the
accepted references put it on the internal serial path, which is Phase 10's
question, and the cheapest honest step is a static reading, not hardware (§4).

The reader who wants only the ordering goes to §6.

---

## 1. What is already established for GBA mode on retail media

Read from the records, not from the summaries. Each line carries its boundary;
the boundary is the part a later reader drops first.

```text
VIDEO   stream-0003, stream-0004 and run 8 (GBP-VIDEO-005): one retail title, three runs of about 44 s of
        streaming each. Transport, the NORMAL startup (first real hand-off 164.696 ms after CONTROL, GBP-HW-224)
        and Policy A measured clean on retail content (GBP-HW-138..152, GBP-HW-223..230): FACT for the logs.
        The picture as seen: OPERATOR OBSERVATION (GBP-HW-144, GBP-HW-152, GBP-HW-227).
        BOUNDARY (PHASE4_ASSESSMENT.md 2.1): no oracle exists for a retail picture, so no colour, geometry or
        full-frame fidelity verdict exists FOR RETAIL CONTENT; those are FACT only on controlled stimuli
        (GBP-HW-081, -131, -258). No scanout binding for retail content. One title.
INPUT   play-0001, RUN 21 and RUN 22 (Yoshi's Island, both pads), and the scripted RUN 25 / RUN 26:
        all ten KEYPAD word bits rose in ordinary play on both pads (GBP-HW-279); five of the six frozen gates were met in
        every session, and the one unmet, RUN 21's SESSION gate, was foreseen in the pre-registration (GBP-HW-280); the two pads produced
        identical ordered press sequences (K = AGREE, GBP-HW-283); the game responded in character, reported
        globally by the Operator (GBP-HW-284, OPERATOR OBSERVATION). The routing of the ten bits is a physical
        FACT from the checker's counters (GBP-HW-266..271), inherited, not re-argued by a game.
        BOUNDARY: per-key W is INCONCLUSIVE in all four runs; the delivery was a ROM on the EZ-Flash in NOR /
        Mode B, so the attribution caveat of HARDWARE_TESTS 7.6.11 is PERMANENT for this instrument
        (PHASE5_ASSESSMENT.md 3.1; the DEVLOG entry that answered R3); one title; a session is bounded at about
        274 s by the event store (GBP-HW-282).
AUDIO   game-0001 (RUN 41) and game-0002 (RUN 42) on Yoshi's Island: RUN 42 met all four frozen gates over
        gameplay and closed Phase 6 (GBP-HW-337, ROADMAP Phase 6); RUN 43 put a real cartridge under the
        Operator's ear for the cushion question (GBP-HW-341..343). The V28 series (RUN 48 onward) then
        characterised the rebuilt native path on the same physical cartridge (HARDWARE_TESTS 28.x).
        BOUNDARY: the audio path carries an audio-behind-video offset the references do not have (U-GBP-046,
        open) and a residual block loss (U-GBP-045, U-GBP-050, open); the start-up window before AUDIO carries
        cartridge sound has its own entry and amendment (GBP-HW-299). Phase 6's gates do not measure
        latency and did not fail on it. The audio runs measure the CHAIN on one title; they are not a
        statement about other titles' audio.
```

**What the record does NOT establish, and which is the whole of Phase 7's GBA half:**

```text
BREADTH OF TITLES      Every retail-content result above is ONE title per family of runs (Yoshi's Island for
                       input and audio; one further retail title for the early video runs). "Representative
                       GBA cartridges" (ROADMAP Phase 7 acceptance) is unmet by construction: zero titles
                       beyond those.
THE FORM OF THE        RUN 21 / 22 / 25 / 26: a ROM on the EZ-Flash in NOR / Mode B, the third value of the axis (R3).
CARTRIDGE              RUN 41 onward: HARDWARE_TESTS 25.9's procedure says to REMOVE the EZ-Flash and insert "the Yoshi's
                       Island cartridge"; the Operator's declaration of 2026-09-29 (section 5.1, verbatim) lists no
                       separate Yoshi's Island Game Pak among his GBA cartridges and says the EZ-Flash's NOR holds it.
                       THE TWO TEXTS ARE NOT RECONCILED HERE AND NOTHING IS INFERRED. Which object sat in the slot from
                       RUN 41 on is one question (section 7.2, item 1); if it was the EZ-Flash, the permanent attribution
                       caveat rides the audio citations of section 1 as well.
SAVE TYPES             Nothing cited above concerns cartridge save memory: no save was written, read back or
                       lost under this runtime in any entry read. Which titles save, and how, is unmeasured.
CARTRIDGE HARDWARE     RTC, solar sensor, tilt / gyro and the motor of a rumble cartridge: none exercised.
                       HARDWARE_TESTS 7.6.4 recorded that no sensor, rumble or clock is KNOWN to be involved in
                       Yoshi's Island (a "not known", not a check), and that the Operator owns WarioWare:
                       Twisted (a Z-axis gyro and cartridge rumble, per GBATEK "GBA Cart Rumble") as an original
                       in two regional versions, "unused here, and a regional comparison is Phase 7's
                       business". The cartridge's GPIO lines and whether the GBP's slot passes them are
                       UNKNOWN; 7.6.4 says a flashcart may leave the RTC absent or emulated.
LONG SESSIONS          The longest continuous retail sessions are of the order of minutes. play-0001 was sized for 720 s and bound
                       at about 274 s by its event store (GBP-HW-282); the video state model's store fills at
                       about one event per frame, 249.7 s in RUN 43 (GBP-HW-344); Phase 5's R5 priced this and
                       assigned the resize to Phase 12.
GBA-MODE PER-TITLE     Nothing here says a title that runs "looks right": the retail picture has no oracle. Its
CORRECTNESS            correctness is the Operator's judgement per title, recorded as OPERATOR OBSERVATION with
                       the attribution caveat its form carries.
```

## 2. The vehicle — which image a Phase 7 run would use

A Phase 7 GBA run needs video, input and audio **together**, ending when the
Operator ends it, on a title the Operator declares. Three families of image
carry parts of that:

```text
image                    video   input   audio                   session end     what it is
play-0001                yes     yes     drained, not played     Z (720 s)       Phase 5's acceptance image; event store binds at ~274 s (GBP-HW-282)
game-0002 (live family)  yes     yes     the Phase 6 chain       Z, 120 s bound  Phase 6's closure image (~1.5 min); the chain it closed with is the pre-V28 one
gbp-audio-v28            yes     yes     the V28 native chain    Z               a RESEARCH chassis: its plans are the two research plans of src/audio/gbp_v28_plans.h,
                                                                                 with the leak rules, the GX label and per-plan store sizing
```

The V28 chassis is the one that already composes video, input and the native
audio chain in one binary (`poc/gbp-audio-v28/source/main.c` header: "video, vstate, vqueue, vpresent,
GX, input, session, keylog, SD save/teardown, startup profile -- ALL carried over
UNCHANGED"). It is not a play image: it runs a plan, and both of
its plans are research plans with caps of hundreds of seconds.

**What composing a Phase 7 vehicle requires — what exists and what does not:**

```text
EXISTS      the modules under src/ that the chassis links (video path, input path, session, the native audio
            chain, the SD log and teardown); the Z session end; the KEY record; the CONTROL record; the
            identity (build id + commit) in the header; the standing rules for a hardware candidate.
DOES NOT    (a) a PLAY PLAN: navigate, then free play until Z, with no research phase, no label and no
                walker-driven audio changes. The plans are a shared table between gbp_v28_plans.h and
                tools/v28budget.py, pinned by a test; a third plan is a change to both.
            (b) A SESSION LONG ENOUGH TO PLAY: the chassis sizes its chunk-correction store and its event
                budget from the plan's wall time (main.c header; tools/v28budget.py). Minutes of play on
                several titles need the stores sized for a stated bound (GBP-HW-282, GBP-HW-344, Phase 5's R5).
            (c) THE AUDIO SETTING THE RUNTIME SHIPS. It is DECIDED BY RUN 58's INGESTION. This document
                names none, and the vehicle's design does not depend on which it is: the setting is one
                constant handed to the chain.
            (d) A CARTRIDGE DECLARATION IN THE LOG: title, form on the three-value axis, mode — today the
                Operator's declaration lives in a chat message and a HARDWARE_TESTS section; a matrix needs
                it beside the run's own bytes.
            (e) A GB/GBC POLICY (section 3): the chassis's guards abort a GB/GBC session before any frame.
            (f) A RUMBLE PATH (section 4): nothing in the tree drives a controller motor or an internal
                serial word.
```

**One rule shapes the build and is stated here so it is not rediscovered:** the
V28 chassis is an *executed* image. Its sources are frozen; a Phase 7 vehicle is a
NEW POC that links the same `src/` modules, not an edit of `poc/gbp-audio-v28`
(library defaults may move, images reproduce at their own commit —
HARDWARE_TESTS 23.9). The vehicle is a code checkpoint **after** RUN 58's
ingestion, which is why nothing in this document builds it.

**GBA only.** The audio decode assumes the GBA's AUDIO window layout
(GBP-HW-313, as the game-image record states); `docs/protocol/AUDIO.md` lists
"GB/GBC-mode audio (Phase 7)" as not established. The vehicle above is a GBA
vehicle; a GB/GBC vehicle inherits §3's problem first.

## 3. GB/GBC mode

Starting points: `GBC_PATH.md` (3, 4, 5), RUN 24 / RUN 27 (`GBP-HW-274`, `-275`,
`-276`) and RUN 28 / RUN 29 (`HARDWARE_TESTS.md` 7.10). The ROADMAP's own warning
governs: *do not assume behaviour observed in GBA mode also applies to GB/GBC mode.*

### 3.1 What four boots established

Four GB/GBC boots exist, all on `stream-0015` @ `da06500`: RUN 24 and RUN 27
(Pokémon Crystal, JP), RUN 28 (Everdrive GB X7) and RUN 29 (Samurai Spirits, an
unofficial DMG cartridge). In all four:

```text
CONTROL        orig = 0x92, exp = 0x8e: bit 0x01 CLEAR in the original byte -- the same byte a GBA cartridge
               gives (GBP-HW-274). Then bit 0x01 is SET after the transform write and stays: 186..636 us for the
               three ordinary cartridges, 698..1148 us for the Everdrive (GBP-HW-275; HARDWARE_TESTS 7.10.4).
               FACT for the transition; its meaning is scoped by 275's own amendment: "reads 1 with GB/GBC media in
               the slot after the transform", NOT "reports the cartridge type"; it does not separate DMG from CGB.
THE SESSION    PREUNMASK ok=0 reason=control_changed, control=8f, teardown S2_before_unmask, zero unmasks, no
               service cycle and no frame captured (GBP-HW-276). The restore wrote 0x92 and read 0x93, so
               restore=error and power_cycle_required=1.
THE OPERATOR   the Start-up Disc's L / R make a GB/GBC image fill the screen or not (GBC_PATH 1.2): a recollection
               of using the Disc, OPERATOR OBSERVATION, never a measurement.
```

### 3.2 Why the session stops — and that it is the guard working, not a defect

The chain is in `GBP-HW-276` and the code is in `src/gbp/gbp_avsvc_probe.c`:
`common_checks()` requires the CONTROL vote to equal the value the runtime wrote
(`control_exp`) at every snapshot — PREUNMASK, PRESVC, POSTDRAIN, POSTACK,
REARMPOST — and the teardown requires the read-back after the restore to equal
the original. The guard's premise is that only the runtime writes CONTROL, so any change is
an anomaly worth aborting on. In GB/GBC mode **the device itself sets bit 0x01**, a
bit the runtime never wrote. The guard sees a change and refuses, exactly as it
was written to. **Nothing about the transport, the log or the media is implicated**
(`GBP-HW-276`).

### 3.3 What must change for a GB/GBC picture to reach the screen

Proposed, in the order the dependencies fall; none of it is built or decided here.

```text
1. THE CONTROL-EQUALITY POLICY, in BOTH places (the mid-session guard and the restore's read-back).
   The change is narrow: a bit the device reports and the runtime never writes -- 0x01, FACT on four runs --
   must not count as "CONTROL changed under us"; every other bit stays fully strict.
   WHY NOT A TIME WINDOW: the arrival window moves with the cartridge (RUN 28's is disjoint from the other
   three, 698 us against 636 us), so "0x8f is expected after N us" would encode one cartridge.
   GATES, FIRST: (a) every archived GBA log gives the same guard verdicts under the masked check (the whole
   captures/local archive is the fixture); (b) a synthetic change of ANY other bit still trips it; (c) a GBA
   cartridge that ever showed 0x01 set would be a finding, not a pass.
   FIRST VERSION LOGS AND TOLERATES; it does not branch on the mode. Branching on bit 0x01 is a later step,
   after DMG-versus-CGB and the Everdrive's late arrival are understood.
2. EVERYTHING DOWNSTREAM IS UNMEASURED IN GB MODE, and a session that gets past the guard is the first
   observation of each: whether the AV service cycle raises the same IRQ causes; whether the VIDEO window
   carries frames with the GBA frame structure (frame ids, geometry -- GBP-HW-081 is FACT for GBA content
   only); whether the AUDIO window keeps the GBA layout; whether an injected KEYPAD word reaches a GB/GBC
   game as its joypad. That the AGB presents a GB/GBC game inside its own output is general Game Boy Advance
   knowledge (GBC_PATH 2), NOT a finding of this project.
3. THE RESTORE AND THE POWER CYCLE. Until 1 is done the rule stays as HARDWARE_TESTS 7.7 wrote it: a console
   left after a GB/GBC run is power-cycled before the next run.
4. THE PICTURE IS THE FIRST QUESTION, AND ANY GB PROGRAM ANSWERS IT. "Does the VIDEO window deliver frames
   when a GB-mode program runs" needs no particular title. Three instrument families are now declared (section
   5.1): the X7, whose own OS is always in the measurement; original Japanese cartridges; and a flashcart that
   boots straight into a ROM (the MBC3000 v4, 3.4). None is preferred here.
```

### 3.4 The Everdrive GB X7 constraint

His words (Issue #55, `GBC_PATH.md` 5, recorded verbatim there): *the X7 always
runs its own menu and operating system, loaded from its SD card.* So **its menu
is always in the measurement**, and any experiment on it tests "GBP + Everdrive
OS", not "GBP + game". Three consequences, stated as design reasoning and not as
findings:

- For §3.3's question 4 the X7's own menu **is** a GB/GBC program, so a first
  picture in GB mode may legitimately be the X7's menu. That answers *does a
  picture arrive*; it answers nothing about a title.
- For anything that needs a title's behaviour (the L / R stretch of GBC_PATH 4.2,
  a game's input, its audio) the X7 is an instrument with its own firmware between
  the game and the AGB. A plain GB/GBC cartridge is the cleaner instrument; the
  cartridges of RUN 24 / 27 (Pokémon Crystal) and RUN 29 (an unofficial DMG
  cartridge) are candidates, each with the attribution caveat its form carries.
  The Operator's declaration of 2026-09-29 lists an original Pokémon Crystal
  (JP); that it is the cartridge of RUN 24 / 27 is by title only and is not stated.
- **A second GB/GBC flashcart is in his inventory, the MBC3000 v4** (section 5.1),
  and by his words it **boots straight into the game, with no menu**; it supports
  MBC3, MBC30 and MBC5 only, and it currently holds his REON Crystal ROM set to
  MBC30. So the X7's constraint is the X7's and does not hold for this card, for
  ROMs on those mappers. **Two consequences, as design constraints, not findings:**
  (a) it is a menu-less GB/GBC instrument whose form is *a ROM delivered by a
  flashcart*; (b) **it is his setup: nothing in this document requires
  re-flashing it, and any design that would must ask him first.** Whether the
  REON Crystal ROM is the same game as his original Crystal is not stated; if it
  is, an original cartridge and a menu-less flashcart ROM of ONE title would
  separate the cartridge from its delivery. That is a lead, asked in 7.2, not an
  assumption.
- The menu's presses enter the KEY record before anything else. The EZ-Flash
  treatment (an explicit topology item, cut at the list's first key —
  HARDWARE_TESTS 7.6.11) applies unchanged.

### 3.5 Static reading of the Disc and GBI — PROPOSED, not performed

**The bounded step.** Read, from the private reference binaries only and by the
project's own headless Ghidra route (`CLAUDE.md` 6.5), how the Start-up Disc and
`gbi.dol` behave when CONTROL bit 0x01 is set: what else besides the "Game Boy"
versus "Game Boy Advance" strings depends on it (`REGISTERS.md` 3 records the
strings, status C); whether either tolerates CONTROL changing under it, which is
exactly §3.3's item 1; what each does for L / R; whether the serial state
machine differs.

```text
COST      one bounded round; no build; no hardware; no Operator minutes; a moderate reading effort.
OUTPUT    static EVIDENCE entries (FACT for the code, never for the hardware), UNKNOWNS updates, and a sharper
          §3.3. The inputs stay private (CLAUDE.md 7); the entries describe behaviour, not text.
WHY FIRST it may make item 1 of 3.3 a copy of a solved problem, and it is the only Phase 7 step with no cost to
          the Operator. Whether it crosses a phase gate is not in question -- it IS Phase 7 work -- which is why it
          waits for the Orchestrator to open the phase, not for a §26 argument.
```

## 4. GBP-aware features, rumble first (U-GBP-026)

`ROADMAP.md` Phase 7 puts these in the phase as **normal compatibility, not an
optional feature**, and says the mechanism *is not assumed*; `U-GBP-026` names
the leading candidate — the AGB-side protocol GBATEK documents — and says the
mechanism is to be established from the Disc, GBI, physical behaviour and games
known to exercise the feature (Phase 7 / 9 / 10).

### 4.1 What the accepted references say, with sources and status

```text
SOURCE                        SAYS                                                                     STATUS
GBATEK "GBA Gameboy          Detection: a 240x160 logo of the Game Boy Player, held for a few frames;    a REFERENCE statement about the AGB
 Player" -- "Unlocking and   KEYINPUT switches between 03FFh (2 frames) and 030Fh (1 frame, Left+Right+    side, with its own hedges ("maybe at
 Detecting"                  Up+Down pressed) while it is shown.                                          least 3-4 frames? not sure")
GBP-KEY-005 (the Disc)       The Disc, after 40 matching logo blocks, ORs 0x00F0 into the keypad word     FACT (static) for the Disc;
                             for five ticks and clears it for five, for up to 24 000 ticks.               CORROBORATED that bits 4-7 reach
                                                                                                           KEYINPUT 4-7 (with GBATEK)
GBATEK "Rumble"              After detection, init RCNT / SIOCNT to 32-bit normal mode, EXTERNAL clock,   reference statement; NOT observed by
                             SO high, IRQ enabled, start bit; receive a fixed sequence (about once per    any Open-GBP measurement
                             frame) and answer; the sequence spells "NINTENDO" in 16-bit fragments with
                             bitwise inversions, and then a word ending in a byte yy: 04h = RumbleOff,
                             26h = RumbleOn. THE yy BYTE IS IN THE GAME'S RESPONSE COLUMN of GBATEK's table.
GBP-SIO-001 (the Disc)       The internal serial path exists and is exercised by official software:      FACT that the path exists; the
                             write SIODATA, SIOCTL |= 0x80, wait on IRQ bit 6 or a 1 s timeout, read      SEMANTICS of every bit UNKNOWN
                             SIODATA or SIOCTL; it fails if CONTROL bit 0x20 is set                        (U-GBP-001..003)
                             (INITIALIZATION.md 7).
GBI                          Reads SIODATA on IRQ bit 6 and writes SIODATA from a queue.                  static; purpose "not analyzed"
                                                                                                           (INITIALIZATION.md 7)
Dolphin                      The SIO paths are stubs that log and return 0.                               no help as a model (GBP-SIO-001)
INITIALIZATION.md 7          "The AGB-side protocol GBATEK documents ... is presumably what travels       the link is NOT ESTABLISHED, in the
                             here, but that link is not established."                                      page's own words
```

**The one derived reading, labelled as such.** In GBATEK's table the rumble byte
travels in the *game's* response, and the words the game receives come from the
Game Boy Player side. If the Disc's state machine is the GameCube half of that
exchange, its state 0 (write SIODATA, start) and state 1 (read SIODATA) are the
two steps a rumble exchange needs, and the GameCube side would then turn the
byte into the controller's motor. **That is a consistency argument between two
descriptions, an INFERENCE, not a statement of either source and not an
observation** (`RESEARCH_METHOD.md`).

**The controller half is not the GBP's.** Driving a GameCube pad's motor is the
GameCube-side pad API's business; whether the API and the pad support it is a
reference to be read on the day. **One standing declaration bears on it**: the
generic third-party pad is the default "unless a run strictly requires the
original" (DEVLOG, Issue #42's entry; `HANDOFF.md` records the official pad as
owned and not used). Whether that pad has a motor is a question
for the Operator (section 7).

**Cartridge rumble is a different mechanism and stays out of this section.**
GBATEK's "GBA Cart Rumble" puts a motor *in the cartridge*, switched by a GPIO
line. It belongs to §1's *cartridge hardware* column (does the slot pass the
line at all) and not to the GBP's serial exchange. GBATEK notes one title as
possibly doing both and marks it with a question mark.

**Which titles.** GBATEK is the one accepted reference in this repository that
names them, and it lists seven as having a Game Boy Player rumble feature,
hedging one (Drill Dozer: "BOTH handheld-rumble and GBP-rumble?"): Mario & Luigi:
Superstar Saga; Pokémon Pinball: Ruby & Sapphire; Shikakui Atama wo Marukusuru
Advance: Kokugo Sansu Rika Shakai; Shikakui Atama wo Marukusuru Advance: Kanji
Keisan; Summon Night Craft Sword Monogatari: Hajimari no Ishi; Super Mario
Advance 4: Super Mario Bros. 3. **That list is reference material, not a
project finding, and no title on it is assumed to be owned by the Operator.**

### 4.2 The dependency on Phase 10, made explicit

```text
detection             the runtime must present the KEYPAD pattern while the game shows its logo. That is KEYPAD
                      writes, on a path that is a physical FACT for ten bits (GBP-HW-266..271) -- NOT an SIO
                      write. But nothing in Open-GBP implements the Disc's logo-match and 0x00F0 cycle, and
                      where a game re-checks it is unmeasured. Phase 7 owns this.
the exchange          the game is the EXTERNAL-clock side (GBATEK), so the GameCube side must clock: WRITE words
                      to SIODATA and start, and READ the game's replies. That is BOTH of Phase 10's milestones,
                      A (observe a deterministic serial event from software on the GBP) and B (drive a
                      deterministic response the GBP software observes), and neither has been reached.
so                    Phase 7's rumble requirement cannot be MET without Phase 10's internal-SIO research. What
                      Phase 7 can do is prepare it and say so.
```

### 4.3 Does a narrow read-only feasibility observation qualify under `CLAUDE.md` 26?

**Conditionally, and not first.** §26 allows an early crossing only for *a
blocking feasibility question*, kept narrow, with the reason written down, and
never as an architectural dependency. The candidate:

```text
QUESTION   With a GBP-aware title running after the runtime has unlocked it through the KEYPAD path, is ANY
           SIO-plane state observable from the GameCube side -- SIOCTL, the IRQ's bit 6 -- with NO SIO write?
WHY IT MAY BLOCK
           it decides whether U-GBP-026 can advance before Phase 10's write research, or waits for it.
CONDITIONS it qualifies only if ALL hold:
           (a) reads only, and only registers whose reads are not known to have a side effect. THE SIDE-EFFECT
               QUESTION IS ITSELF UNKNOWN: the Disc reads SIODATA only after the IRQ, and a read outside that
               pattern is unexamined, so SIODATA is NOT in the first read set;
           (b) no IRQ-mask write is added: whether the raw IRQ register shows bit 6 without unmasking it is
               UNKNOWN and is part of what the static reading (3.5) should read first;
           (c) one bounded boot per title, its gates written first, and the unlock uses the existing KEYPAD path;
           (d) the result creates no dependency: a "nothing observable" is a finding, not a failure.
RECOMMENDATION
           not before the static reading. It may answer (b) and (a) by itself, or reshape the observation; and
           a hardware run whose premises are unread is the "chained unverified assumptions" CLAUDE.md 18 forbids.
           Any such run needs the Orchestrator's explicit, recorded section-26 decision.
```

### 4.4 Can GBP rumble be observed from a flashcart-delivered ROM?

The Operator's third declaration says Drill Dozer would be run as a ROM from a
flashcart; he does not own the cartridge (section 5.1). The question is a
design one, and it is answered from the sources, not assumed.

```text
WHAT THE SOURCE SAYS   GBATEK puts GBP rumble in the AGB program's own serial exchange (4.1), and names three
                       homebrew programs (RumblePong, Remudvance, Goomba) as implementing it. Nothing in the
                       section ties it to the cartridge's hardware, so a ROM delivered by a flashcart runs the
                       same AGB-side code path. STATUS: a reference statement; NOT observed by this project.
WHAT DOES NOT MOVE     the motor inside a rumble CARTRIDGE (a GPIO line, 4.1) is absent on a flashcart. That is
                       the cartridge-rumble mechanism, not this one.
THE AMBIGUITY A       a retail title's silence would have four readings that one run cannot separate: the title
 RETAIL ROM CARRIES    has no GBP support (GBATEK itself hedges Drill Dozer with a question mark), the ROM on a
                       flashcart lacks something the title probes, the unlock (4.2) did not take, or the runtime
                       has no serial path yet. THE INSTRUMENT WOULD NOT DISCRIMINATE.
THE DESIGN QUESTION    a PROJECT-OWNED AGB-side stimulus that performs GBATEK's exchange, delivered by the
                       EZ-Flash, would make the AGB side a known quantity -- the principle behind
                       stimulus/agb-tone in PHASE6_ENTRY.md, an independent implementation of documentation, not of
                       anyone's code. A retail title then adds "does a real game do it". It is a candidate (E10),
                       not a proposal to build.
WHICH FLASHCART        not stated. A third flashcart is declared (an EverDrive he calls "5x mini"); its family and
                       its boot behaviour are not stated and are not assumed (7.2).
```

## 5. The compatibility matrix — skeleton only

`ROADMAP.md` Phase 7 requires the matrix, and asks for a second one specific to
GBP-aware features, rumble included. **No row is invented here. Every row comes
from a run the Operator performed and a title he declared.**

```text
column                     values / rule
title as declared          his words; "title unknown" is admissible. A title he can read from the game's own screen
                           is recorded as read; nothing is inferred from the file or the cartridge label.
form (three-value axis)    ORIGINAL cartridge / UNOFFICIAL cartridge / a ROM delivered by a FLASHCART (HARDWARE_TESTS
                           7.6.4). The attribution caveat rides every citation of a non-original, permanently where
                           it was asked and kept (Phase 5 R3). A form not declared makes the row INCONCLUSIVE on
                           that item.
mode                       GBA / GB / GBC as the run observed it (CONTROL bit 0x01 after the transform, GBP-HW-275) --
                           NOT DMG versus CGB, which that bit does not carry.
cartridge hardware         RTC / solar / tilt-gyro / cartridge rumble / none KNOWN -- "none known" and "checked" are
                           different values and the column says which.
GBP-aware feature          detection unlock / GBP rumble / palette / other -- only as the run OBSERVED it, never as a
                           reference's list says it should be.
video / input / audio      each: NOT RUN / OBSERVED (Operator) / MEASURED (evidence id) / FAILED, with the boundary
                           of section 1 for what "MEASURED" reaches.
evidence id                the entry that carries the row; a row without one is not a row.
```

The matrix lives in `HARDWARE_TESTS.md` (or a page the Orchestrator names) when
the phase opens. Two skeletons: one for cartridge compatibility, one for the
GBP-aware features. **Both start with no OUTCOME cell filled that a run has not
earned**; what the Operator has already declared is the inventory below.

### 5.1 The rows the Operator's declarations already supply (2026-09-29)

**OPERATOR OBSERVATION, verbatim** (Issue #143, comments 5901197211,
5901202292 and 5901239793; asked by the Orchestrator in pt-BR; recorded before it is read into
any row):

> *1 - de GBA tenho apenas o simpsons road rage (paralelo), ez-flash omega DE (que tem o Yoshi Island na NOR), WarioWare twisted (JP e US), Kingdom Hearts Chain of Memories (JP original)*
> *2 - DrillDozer é um jogo que libera vibracao no controle*
> *3 - Samurai Spirits,  double dragon, fighting simulator... mas tenho pokemon crystal original JP, pokemon pinball, toda gen1, gold e silver (Jogo com suporte a paletas no color, mas funciona no GB original tb)*
> *meus jogos de pokemon sao todos japoneses...*
> *tb tenho o flashcart MBC3000 v4*
>
> *Seria pelo flashcart... esqueci de falar que tenho o everdrive 5x mini tambem* (on Drill Dozer: owns the cartridge, or only knows it rumbles?)
> *originais* (on the form of Pokémon Pinball, Gen 1, Gold and Silver)
> *liga direto... mas ele so suporta MBC3, MBC30 e MBC5... e atualmente esta setado para MBC30, com a rom da REON do Crystal* (on whether the MBC3000 v4 boots straight into the game)

**Rows, each cell either his word, an earlier record with its id, or `not stated`.**
Nothing is inferred to fill a cell: an unstated form stays unstated, and no title
is said to carry rumble or cartridge hardware on the strength of this list.

```text
family  title as declared                         form                                        earlier evidence in this repository
GBA     Yoshi's Island (SMA3)                      a ROM on the EZ-Flash's NOR ("na NOR");     video, input, audio: section 1, with its
                                                   third value of the axis, per the            boundaries; RUN 41+ object: see 7.2 item 1
                                                   Orchestrator's reading of the declaration
GBA     The Simpsons: Road Rage                    "paralelo" (his word: unofficial)           none: not run
GBA     WarioWare: Twisted (JP and US)             original in both regions per HARDWARE_TESTS  none: not run. Rejected in Issue #37 ONLY as
                                                   7.6.4; the 2026-09-29 answer lists them     an INPUT instrument (most of its interaction
                                                   without a form                              leaves the button path, 7.5); that reason
                                                                                               answers a Phase 5 question and is not carried
GBA     Kingdom Hearts: Chain of Memories (JP)     "original" (his word)                       none: not run
GBA     the EZ-Flash Omega DE                      a flashcart (NOR, Mode B)                   the delivery route of section 1's input runs
GB/GBC  Pokémon Crystal (JP)                       "original" (his word)                       RUN 24 / RUN 27 booted a Pokémon Crystal (JP):
                                                                                               bit 0x01 set after the transform, no frame
                                                                                               (GBP-HW-275, -276); that it is THIS cartridge
                                                                                               is by title only, not stated
GBA     Drill Dozer                                not owned as a cartridge; "Seria pelo       none: not run. His statement: a game that
                                                   flashcart" -- a ROM from a flashcart (which  makes the controller vibrate; GBATEK hedges
                                                   one: not stated)                             whether that is through the GBP (4.1, 4.4)
GBA     the EverDrive "5x mini"                    a flashcart; family and boot behaviour       none: not run
                                                   not stated
GB/GBC  Pokémon Pinball                            "originais", Japanese releases; which        none: not run
                                                   Pinball title is not stated
GB/GBC  "toda gen1" (all of gen 1), Gold, Silver   "originais", Japanese releases; the Gen 1    none: not run
                                                   titles are not enumerated
GB/GBC  Samurai Spirits                            unofficial, a DMG cartridge, per the         RUN 29: bit 0x01 set after the transform, no
                                                   relay recorded in HARDWARE_TESTS 7.10.1      frame (GBP-HW-275, -276)
GB/GBC  Double Dragon, Fighting Simulator          not stated per title (he named them in       none: not run
                                                   answer to which unofficial cartridges he
                                                   can read a title from)
GB/GBC  the Everdrive GB X7                        a flashcart whose own menu always runs       RUN 28 (GBP-HW-275, -276; 7.10.4)
GB/GBC  the MBC3000 v4                             a GB flashcart that "liga direto" (boots      none: not run. MBC3 / MBC30 / MBC5 only;
                                                   straight in, no menu); it currently holds     holds his REON Crystal ROM set to MBC30;
                                                   a ROM delivered by a flashcart                his setup, not to be re-flashed unasked
```

**Not rows, and why.** **His parenthetical** — *"Jogo com suporte a paletas no
color, mas funciona no GB original tb"* — follows the list of Gold and Silver and
does not say which title it describes; it is recorded and attached to no title.
**A name
collision is left as it is**: *Pokémon Pinball* appears in his Game Boy answer,
and GBATEK's rumble list names *Pokémon Pinball: Ruby & Sapphire*, a GBA title.
Which of the two he owns, if either, is not stated, and the two are not assumed
to be the same game.

## 6. Ordered candidate experiments

None is pre-registered. Each would be, as its own checkpoint, with reserved names
and an identity gate, when the phase opens. Costs are boots / builds / Operator
minutes, estimated from the runs already executed.

```text
E1  STATIC READING of the Disc and GBI: CONTROL bit 0x01, L / R, the serial state machine, what a GBP-aware
    title needs of the host, and whether the raw IRQ register shows bit 6 unmasked.
    cost 0 boots, 0 builds, 0 Operator minutes; one bounded reading round.   depends on: the phase opening.
    gates first: entries FACT for the code only; nothing about hardware is concluded from it.
E2  THE CONTROL-EQUALITY POLICY, host-side (3.3 item 1): the masked check, the whole GBA archive as the fixture,
    the synthetic every-other-bit case. cost: 0 boots, 1 code checkpoint.   depends on: E1 (it may supply the
    reference's own tolerance).   gates first: 3.3's (a), (b), (c).
E3  THE FIRST GB-MODE PICTURE (3.3 item 4): one boot of a tolerant image with any GB/GBC program in the slot; the
    X7's own menu qualifies. cost: 1 image, 1 boot per cartridge, about 10 Operator minutes including the power
    cycle. depends on: E2.   instrument options (3.3 item 4): the X7's menu, an original Japanese cartridge, or
    the MBC3000 v4's straight-boot ROM -- one instrument per run, declared, none preferred here.   question: do VIDEO frames, AUDIO blocks and the AV service cycle arrive, and in what
    structure. gates first: the byte-level verdicts of the existing tools on the log; INCONCLUSIVE if the mode was
    not entered (CONTROL says so) or the log is missing. What it does not decide: anything about a title.
E4  THE L / R STRETCH (GBC_PATH 4.2, unchanged): needs a GB/GBC title whose stretch is legible and, preferably, a
    plain cartridge or a straight-boot ROM (3.4). cost: 1 boot per arm set, about 10 Operator minutes.   depends on: E3.
    gates first: the KEY record's SENT / NOT SENT half and the frames' change at the instant of the word.
E5  THE GBA BREADTH SESSION: the vehicle of section 2, one boot per declared title, a few minutes of play each,
    the cartridge declaration in the log, per-title Operator observation (video, input, audio).
    cost: the vehicle (a code checkpoint after RUN 58's ingestion) and about 5-10 Operator minutes per title.
    depends on: the vehicle; the audio setting from RUN 58's ingestion; the Operator's declarations.
    gates first: the existing per-run gates (transport, startup, Policy A, the KEY record, the audio gates) applied
    unchanged; a title that fails is a ROW, not a failed run.
E6  A SAVE / LOAD PROBE on titles that save: play, save, power cycle, reload. cost: 1 boot per title inside E5's
    session, plus the risk that an original cartridge's save is altered -- the Operator decides per cartridge.
    depends on: E5's vehicle.
E7  CARTRIDGE HARDWARE: a title with each of RTC / tilt-gyro / cartridge rumble, per the Operator's declaration
    (WarioWare: Twisted is recorded as owned). cost: 1 boot per title; the question is whether the GBP's slot passes
    the line, so a "did nothing" is a finding. depends on: E5's vehicle.
E8  GBP DETECTION UNLOCK (4.2 first row): implement the KEYPAD pattern at the logo and record whether a title
    changes behaviour (GBATEK says the palette is adjusted). cost: 1 code checkpoint, 1 boot per title.
    depends on: E1 and E5's vehicle.   It does not touch SIO.
E9  THE READ-ONLY SIO OBSERVATION (4.3): only if the Orchestrator records the section-26 decision, only after E1.
    cost: 1 boot per title, reads only.   The rumble DRIVE itself waits for Phase 10.
E10 A PROJECT-OWNED AGB-SIDE RUMBLE STIMULUS (4.4): GBATEK's exchange implemented independently and delivered by the
    EZ-Flash, so the AGB side is known. cost: 1 stimulus ROM build, 1 boot; depends on: E1, and on Phase 10 for the
    GameCube side. A retail ROM (Drill Dozer, from a flashcart) is the second instrument, not the first.
```

**The order the dependencies impose:** E1, then E2 and E5's vehicle in
parallel (the vehicle waits for RUN 58's ingestion, not for E1), then E3, E4;
E5 to E7 as titles come; E8 and E9 last. **E1 is the only step that needs nothing
from the Operator, and it is the one that changes the most of what follows.**

## 7. What the Operator must declare

For the Orchestrator to relay; written in English here, the Orchestrator
translates. No hardware run is being requested by this list — it is what the
matrix and the vehicle need before their first run can be designed.

### 7.1 Already declared (2026-09-29)

His GBA and GB/GBC inventory, the form of the Pokémon titles, that Drill Dozer
would come from a flashcart, and the MBC3000 v4's straight boot and mapper limits
are recorded verbatim in section 5.1. Those questions are not asked again.

### 7.2 Still open

```text
 1. WHICH PHYSICAL OBJECT held Yoshi's Island from RUN 41 on: the EZ-Flash's NOR, or a separate Game Pak? (Section 1's
    form row: the 25.9 procedure says a swap, the declaration lists no separate Game Pak.)
 2. DRILL DOZER: is the ROM in hand, and on which flashcart would it run? The EverDrive "5x mini": which family, and
    does it boot into a menu?
 3. WHICH POKEMON PINBALL, which Gen 1 titles, and the form of Double Dragon and Fighting Simulator (original or
    unofficial). Whether his original Crystal is the cartridge of RUN 24 / 27.
 4. THE REON CRYSTAL ROM on the MBC3000 v4: is it the same game as his original Crystal, or a different ROM? (Nothing
    here requires re-flashing the card; any design that would asks him first.)
 5. CARTRIDGE HARDWARE he KNOWS a cartridge to carry -- a clock, a solar / tilt / gyro sensor, a rumble motor -- for
    the titles above other than WarioWare: Twisted. "I don't know" is admissible and is not "none".
 6. SAVES: which cartridges keep a save, and whether he accepts a save / reload probe on an original cartridge, or
    wants a backup first. His decision per cartridge, never a default.
 7. THE PAD: does the generic third-party pad he uses have a rumble motor? Does the original pad, which he owns, and
    would he use it for a rumble run?
 8. THE BUDGET: how many minutes per title, and how many cartridges in one session.
 9. Anything he saw with the Start-up Disc or GBI in GB / GBC mode beyond L / R filling the screen -- as a
    recollection, recorded verbatim, never as a measurement.
```

## 8. What this document does not do

It does not enter Phase 7, build, stage, schedule or pre-register anything. It
mints no evidence id, moves no status, promotes nothing and closes no unknown. It
does not answer `U-GBP-026`, `U-GBP-036` or `U-GBP-001..003`, and it does not read
the Operator's recollection of the Disc (`GBC_PATH.md` 1.2) as a measurement. It
does not touch the card, `build/swiss`, `build/physical`, a slot pin, the V28
sources or tools, or Issue #142. It chooses no audio setting and states no
expectation of RUN 58. It names no retail title as a rumble title except through
GBATEK's own list, attributed and hedged as GBATEK hedges it. It does not
authorise the static reading of §3.5, the observation of §4.3 or any experiment
of §6: each waits for the Orchestrator to open the phase and for its own
checkpoint.

---

## Amendment — 2026-09-29 (Issue #144): what the static reading changed in §3.3 and §3.5

The committed text above is unchanged. This paragraph records what E1 (§3.5, narrowed by the Orchestrator to
three questions) found, in the evidence entries `GBP-CTL-002`, `GBP-CTL-003` and `GBP-KEY-011`. **Everything
here is FACT for the code of the two references and nothing about the hardware.** Phase 7 is ENTERED (ROADMAP
status line, Issue #144).

```text
Q1  CONTROL after the transform. NEITHER reference compares CONTROL with a value it wrote. The Disc derives a
    status word from each read (the type bit becomes one bit of it) and writes only read-modify-writes of a fresh
    read; GBI mirrors the byte it read and writes that byte back, with its own changes, every pass. Neither waits
    for or times bit 0x01, and neither restores the original byte at exit.
    WHAT THIS CHANGES IN 3.3 ITEM 1: the guard is the PROJECT'S OWN, stricter than either reference, so it was not
    "a copy of a solved problem" -- the references' solution is the absence of the check, not a mask. Two options
    now stand next to the mask: derive-and-tolerate (compare only the bits the runtime writes) and the references'
    read-modify-write on both the guard's and the restore's side. The choice is E2's. U-GBP-036's remark that a
    restore comparing a read-back with what was written fails after a GB/GBC session is about OUR restore only.
    GBI forces CONTROL bit 0x80 when the type bit is set (GBP-CTL-003 site 1); a tolerant first image should log
    CONTROL and NOT copy that.
Q2  What depends on bit 0x01. The Disc: exactly one thing, the duration of a ramp (300 or 1000) when present and
    type are both set; nothing on its video, keypad or timing path reads the type bit. GBI: six sites --
    on-screen text, the KEYPAD word (L and R), a frame-conversion routine choice, a bounds computation over the GX
    framebuffer window, an aspect computation in its presentation code, and the serial queue with CONTROL bit
    0x80. THE REFERENCES DIVERGE, and it is preserved: GBI has a GB-specific picture path and the Disc, in the
    code read, has none. What E3 will measure (whether the VIDEO window's frames differ in GB mode) is not
    decided by either.
Q3  L / R in GB type. The Disc forwards L and R to the AGB in every mode; GBI removes them from the word when the
    type bit is set. In neither was a host-side scaling on L or R found (for the Disc the search was not
    exhaustive). E4's prediction (GBC_PATH 4.2) is unchanged and gains a second reading: an L / R sent by our
    runtime that does nothing in GB mode would match GBI's behaviour and refute nothing about the Disc.
```

**Leads, written down and not followed (the Issue stops at three questions):** the three frame-conversion
routines GBI chooses between; what GBI's bit 0x80 and its skipped serial queue mean in GB type (serial
semantics are Phase 10's, U-GBP-026); the Disc's other consumers of the pad structure. §3.5's remaining items
(the serial state machine in GB mode) were NOT read.
