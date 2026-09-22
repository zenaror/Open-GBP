# Phase 6 entry — the audio stream, assessed (2026-09-22, GitHub Issue #45)

**Status: research, DESIGN AND ASSESSMENT ONLY. It authorises nothing** — no
build, no hardware, no pre-registration, no evidence status, no id. Phase 6 is
not entered by this document.

**THE HEADLINE: the Operator's instrument is a KNOWN tone, and the source says
so.** The Enhanced Control Checker's beep was assumed unknown, which is what
split this phase's entry into two stages. It is not unknown: its frequency,
duty, envelope and stop behaviour are all determined by the program, and this
document states them a priori. **Stage A and Stage B collapse into one
experiment, and `stimulus/agb-tone` becomes a FALLBACK rather than a
prerequisite. He has removed a build from the phase.**

---

## 1. What was read, and under what terms

The instrument is the ROM already on his EZ-Flash NOR — the one RUN 14, 15, 17
and 18 used — pinned by §V7.1's amendment on 2026-09-21 to
`github.com/nataliethenerd/enhancedcontrolcheckerGBA`, branch `main`, commit
`76924c1371d7bf761f8b1ed45ab36f195cd1374f`, **CC BY-SA 4.0**.

**Read at that commit, outside the project tree, and nothing from it enters the
repository** — no image, no source, no asset (`CLAUDE.md` §7; the same handling
`external/gbhwdb` received, and for the same share-alike reason). The prebuilt
image at that commit hashes to `53c212c73e814875…2b6e` at 69 348 B, which is
byte-for-byte what §V7.1 pinned.

**What follows is a DESCRIPTION of behaviour derived from reading the program,
not a reproduction of it.** The description is this project's own work; the
source text is not, and is not quoted here.

## 2. What the tone actually is

The program's beep routine writes six APU registers and then stops the channel.
Decoded against `external/gbatek/gba.md` (the register semantics below are
GBATEK's, cited rather than assumed):

```text
what the program asks for                              consequence
master enable            SOUNDCNT_X bit 7 set          the PSG is powered
PSG mix                  SOUNDCNT_L = 0x1177           channel 1 enabled on BOTH sides, PSG master volume 7/7
sweep                    SOUND1CNT_L sweep shift 0     NO sweep: the frequency does not glide
duty / envelope / length SOUND1CNT_H                   initial envelope volume 15, direction DECREASE,
                                                       envelope step time 7 = 7/64 s = 109.4 ms per step,
                                                       length data 0, and THE DUTY CYCLES PER PRESS
frequency / control      SOUND1CNT_X = restart + length flag + frequency value 1200
                                                       f = 131072 / (2048 - 1200) = 131072 / 848 = 154.57 Hz
a bounded busy-wait      a fixed count of volatile iterations -- a few milliseconds, not calibrated
the "stop"               SOUND1CNT_X written all-zero  frequency value 0 -> f = 131072 / 2048 = 64.0 Hz,
                                                       AND THE LENGTH FLAG IS CLEARED
```

**THE DUTY CYCLES PER PRESS, and this is the most useful property in the whole
instrument.** Successive presses select 12.5 %, 25 %, 50 %, 75 % and repeat,
from a four-entry table advanced on every call. **Four presses give four
different duty ratios at the same frequency** — a within-run, four-point slope
that no single free-running tone provides.

**It does not differ per button.** Every button calls the same routine; the
cycling is by press *order*, not by which key.

### 2.1 The stop does not stop it — and that is knowable a priori

GBATEK: `SOUND1CNT_X` bit 14 is the **Length Flag**, *"1 = Stop output when
length in NR11 expires"*. The program **sets** it on the restart and then
**clears** it in the write it uses to stop the tone, while writing the
frequency field to zero and never disabling the channel.

```text
so, per press, the EMISSION this project predicts:
  ~ the busy-wait (a few ms)     154.57 Hz square at the press's duty, envelope at/near 15
  then, until the envelope dies  64.0 Hz square at the same duty, envelope stepping 15 -> 0
  the decay                      15 steps x 109.4 ms = 1.64 s to silence
```

**The program appears to intend a short 154.57 Hz beep and the hardware is
asked for something else**: the write that was meant to end the sound removes
the only stop that was armed. **This is an a-priori prediction, not an
observation**, and the experiment tests it — which is a feature: the capture
checks the reading of the code at the same time as it answers the real
question.

### 2.2 The one register the program never writes

`SOUNDCNT_H` — the PSG-to-output volume ratio and the DMA-sound mixing — is
**never written**. Its value during the run is whatever the reset or the boot
path left. **That is a declared assumption, not a derived fact**, and it scales
the PSG's contribution to the output. It does not affect frequency, duty or the
envelope's *shape*, which is where the discriminating power is.

## 3. The decisive question, answered: **YES, it is predictable enough**

*Is the resulting tone predictable a priori in the sample domain, enough to
distinguish PWM from PCM from the byte-0 phenomenon?*

**Yes — and by three independent shapes rather than one.** Using the drain
cadence recomputed from RUN 17's archive (4 096.0 bytes per drain exactly,
**4 094.4 drains/s**, 16.77 MB/s; §V7.8.6's neighbourhood and the #45
correction), one block is **0.244 ms**:

```text
SHAPE 1  A TWO-LEVEL SQUARE at a known frequency. 64.0 Hz -> period 15.6 ms ~= 64 blocks; the first
         few ms are 154.57 Hz -> period 6.47 ms ~= 27 blocks. A square is the strongest possible
         probe of a sample format because its transitions are where the models disagree most.
SHAPE 2  A KNOWN DUTY, AND A FOUR-POINT SLOPE ACROSS PRESSES. 12.5 / 25 / 50 / 75 % at the SAME
         frequency. Any format that carries amplitude must reproduce the mark-space ratio; the byte-0
         phenomenon cannot produce four different ratios on demand.
SHAPE 3  A 15-STEP STAIRCASE DECAY with a known step duration. 109.4 ms per step ~= 448 blocks per
         step, 1.64 s ~= 6 700 blocks total. An amplitude ramp in 15 equal steps is a signature no
         transfer artefact imitates.
what each model predicts
  PWM (Dolphin's)   a bit-stream whose leading-1-bit count per byte follows the waveform: two counts
                    alternating at the square's period, their RATIO following the duty, and the counts
                    contracting toward the midpoint in 15 steps.
  PCM              sample values taking two levels at the square's period, the high level falling in
                    15 steps, the mark-space ratio following the duty.
  BYTE-0 ONLY      no relationship to the press at all: the same sparse pattern before, during and
                    after, with only byte 0 of each 32-byte line non-zero (U-GBP-021).
```

**The prediction is written before any capture exists, which is the whole
point.** A model that can absorb any block is not a model (§V3.19).

**2026-09-22 (Issue #58) — that pointer is loose, and it is corrected here
rather than rewritten.** §V3.19 does not contain the sentence above. What it
holds is the same discipline in its own words — *"this design does not
manufacture hypotheses to defeat"*, a residual ambiguity written down **before**
the run — and that is what the citation was reaching for. `HARDWARE_TESTS.md`
§V8.5 cites it that way.

**What the source does NOT buy, and this is the limit.** It gives the a-priori
prediction of **what the program asks the APU for**. What the AGB's APU emits,
and what the GBP's AUDIO window carries, is still the measurement — **that gap
is the experiment**, and the source narrows the prediction rather than
answering `U-GBP-012`.

## 4. Stage A's feasibility, assessed against the images that actually exist

The blocker is real and it is not where the #45 design placed it. Verified by
reading the sources, not the design:

```text
gbp-video-capture-probe (Swiss slot 09-video)
   drives KEYPAD        NO -- it does not reference gbp_input at all
   audio blocks kept    10 slots (8 first + 2 last)
   emits the region     YES: links gbp_avseqdump, which writes off_audio_raw / audio_raw_count
gbp-video-stream-probe (stream-0015, slot 12-stream)
   drives KEYPAD        YES, with the KEY record
   audio blocks kept    3 slots, 2 kept (AUDIOAGG raw_kept=2)
   emits the region     NO audio sidecar: it links gbp_vstatedump, which CAN emit the region, but its
                        sidecars are disp / full / vi / idxcap
gbp-play-session (play-0001, slot 13-play)
   drives KEYPAD        YES, with the KEY record
   audio blocks kept    3 slots
   emits the region     NO: it links gbp_vstatedump and writes ONE log and no sidecar at all (sidecar=none)
gbp-video-color-probe
   drives KEYPAD        no
   audio blocks kept    3 slots
   emits the region     YES (vcoldump + vstatedump)
```

**So no image has input AND retention AND emission**, and the missing piece is
not the same one everywhere: the capture probe lacks the **press**, the stream
and play probes lack the **emission and the retention**.

**The smallest honest change**, now that the tone is known:

```text
THE CHEAPEST PATH        extend the STREAM probe, not the capture probe. It already has the input path,
                         the KEY record with t_poll / t_attempt / t_done in the shared time base, and it
                         already links the dump module that can write an audio region. What it needs is
                         (a) the audio raw slots raised from 3 and (b) the region emitted as a sidecar.
WHY NOT THE CAPTURE PROBE
                         it would need the whole input path added -- the module, the policy, the
                         descriptor, the KEY record -- to gain a press it has never had. That is more
                         code, and it would duplicate a path that is already a physical FACT (§V7.4).
HOW MANY BLOCKS          DERIVED, not chosen: one 64 Hz period is ~64 blocks, so periodicity needs >= 64
                         consecutive blocks and comfortably 128 for two periods; one envelope step is
                         ~448 blocks per step. At 4 096 B each, 128 blocks = 512 KB and 448 = 1.8 MB.
                         The full decay is ~ 6 700 blocks = ~27 MB, beyond any store this project has:
                         the capture must be a WINDOW, and the pre-registration must say which and why.
```

**That arithmetic is the reason item 5 of the #45 design cannot be skipped, and
it is now derived from the instrument rather than guessed.**

## 5. The question Stage A would have asked — and why it is now one experiment

**The question**: *does the AUDIO window carry the AGB's sound at all, and
when?* Every AUDIO block this project has archived was captured **with no Game
Pak**, so *"the blocks carry the AGB's audio"* has been assumed and never
observed.

```text
A POSITIVE ANSWER   blocks captured in the window following a press differ, in a way that repeats with
 in the bytes       the press, from blocks captured during silence in the SAME run -- the within-run
                    control that makes this a differential measurement rather than a comparison across
                    sessions.
A NEGATIVE ANSWER   the blocks are indistinguishable before, during and after presses, and carry the
                    same sparse byte-0 pattern the cartridge-less archive already shows. THAT IS A REAL
                    RESULT: it would mean the AUDIO window does not carry cartridge sound in this path,
                    which Phase 6 must know before anything else is designed.
AND THE TRAP        "the blocks changed after a press" must be distinguishable from "the blocks
 NAMED FIRST        changed". With an UNKNOWN tone it would not be: any change correlated with a press
                    could be the press's own side effects. WITH THE TONE KNOWN, the discriminator is
                    not "changed" but "changed INTO THE PREDICTED SHAPE" -- a 64 Hz square at a stated
                    duty with a 15-step decay. That is why knowing the tone collapses the stages: it
                    upgrades the answer from a correlation to a match against a prediction.
```

**Stage A does not disappear — it is answered by the same capture that answers
Stage B**, because the same blocks that show *whether* the window carries sound
also show *what the bytes mean* when compared against the three models.

## 6. Is it worth its cost, argued rather than assumed

**Yes, and the comparison is not close — but the reason changed.**

```text
BEFORE the source was read    Stage A cost one modified image and answered a prerequisite; Stage B needed
                              a project-owned ROM (stimulus/agb-tone) to answer U-GBP-012. Two runs, one
                              build, and Stage A's answer was a correlation rather than a match.
AFTER                         ONE capture on a cartridge the Operator already owns, with no ROM to write,
                              answers both -- because the tone is known well enough to predict the bytes.
                              THE BUILD THAT DISAPPEARS IS stimulus/agb-tone, which stays designed as a
                              FALLBACK for the case where the checker's emission does not match this
                              document's prediction.
WHAT WOULD MAKE THE FALLBACK NEEDED
                              if the capture shows the predicted shape, U-GBP-012 is decided by an
                              instrument that cost nothing to build. If it shows sound that is NOT the
                              predicted shape, the reading of the code or of the APU's behaviour is wrong
                              -- and a project-owned ROM whose output this project controls end to end is
                              then exactly the right next instrument.
```

**The honest caveat on the comparison**: the checker's tone is a **side effect
of a button press** in a program written for another purpose, and its emission
depends on a stop sequence this document predicts is not doing what its author
intended. `stimulus/agb-tone` would have none of that ambiguity. **The reason
to prefer the checker anyway is not that it is better — it is that it is free,
already flashed, already identity-pinned, and its prediction is falsifiable in
the same run.**

## 7. Limits, gates and what rides along

```text
IDENTITY IS A GATE AND IS RE-DECLARED
                         §V7.1's rule is unchanged and is NOT inherited from September: the hash of the
                         Operator's copy is HIS media and a double check, never a gate on its own -- and
                         if any identity differs on the day, DO NOT RUN. The ROM was flashed to his NOR
                         on 2026-09-21; any Phase 6 run re-declares it.
SOUNDCNT_H IS ASSUMED    the program never writes it, so the PSG-to-output ratio is whatever the boot
                         left. Declared here rather than discovered later.
THE SOURCE DOES NOT ANSWER U-GBP-012
                         it predicts what the program ASKS FOR. What the APU emits and what the AUDIO
                         window carries is the measurement, and that gap is the experiment.
R4 RIDES ALONG (Issue #57)
                         §V7.9's T' needs "one session of any length that reaches the service loop", so
                         whatever run comes out of this satisfies it -- no new build, no new analysis.
                         The eventual pre-registration carries T' as a rider.
NOTHING HERE IS AUTHORISED
                         no build, no hardware, no pre-registration, no evidence id, no status. If the
                         tone is usable -- and this document argues it is -- the pre-registration is the
                         NEXT checkpoint, not this one.
```

## 8. What this document does not do

It does not enter Phase 6, build anything, schedule anything or promote
anything. It does not answer `U-GBP-012`, `U-GBP-014` or `U-GBP-021`. It does
not touch `stream-0015`, `play-0001`, the staged slots or the card. It does not
decide the capture window, the image or the run — those belong to a
pre-registration written with the acceptance question in front of it. And it
does not treat Dolphin's PWM model as anything but **HYPOTHESIS**: a match with
it would be CORROBORATED, never FACT.
