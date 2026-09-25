# Game Boy Player — AUDIO path (consolidated after Phase 6's research runs, 2026-09-24)

What GameCube software receives from the AUDIO window, how to turn it into sound, and
what draining it costs. Consolidated from the physical runs of Phase 6
(`docs/research/HARDWARE_TESTS.md` §V8–§V22, RUN 30 through RUN 38), with one timing
requirement from §V24 (RUN 40, 2026-09-24, GitHub Issue #107). **Every row carries
the evidence id that supports it and the status `docs/research/EVIDENCE.md` gives it**:
**F** fact, **C** corroborated. Hardware observations come from this project's hardware
unless marked *(code)*.

Several rows carry a **compound** status, one letter per aspect, because their
entries do. Nothing whose status is HYPOTHESIS or UNKNOWN is stated here as a
property of the device; open questions are pointed at by their `U-GBP-` id and
nothing more. A claim measured in one run says so. Every run used one GameCube and
one Game Boy Player, which is this project's permanent condition.

**Where it is written.** Register-level addressing and the IRQ register are in
`REGISTERS.md`; the service cycle is in `INITIALIZATION.md`; the whole-block DMA
routine is shared with VIDEO (`VIDEO.md` §3). This page does not repeat them.

**Hardware and this project's design are kept apart.** §6 describes how this
project plays the stream on a GameCube. Its numbers (ring size, correction band,
chunk size, the 200-block minimum) are this project's design choices, not
properties of the Game Boy Player, and they are marked as such. §5's stall rows
describe this project's service path, and they say so too.

## 1. The window and the rate

| Property | Value | Status | Evidence |
| --- | --- | --- | --- |
| Where and when | 0x1000 bytes read from index 0x8 per AUDIO cause (IRQ source bit 0x0400), in one ARAM DMA. The Start-up Disc and GBI both read it this way *(code)*. | C (the size and the IRQ bit, from the references); F (hw) that a single 0x1000 DMA from index 0x8 completes. 272 145 of them in two runs, 0 failures. | GBP-AUD-001, GBP-HW-050, GBP-HW-316 |
| Transfer time | 66.5 µs around the call on the first read; 63.8–68.7 µs per 0x1000 DMA in RUN 33 / RUN 34. Call overhead is included, so this is not a transfer rate. | F (the logged figures) | GBP-HW-050, GBP-HW-316 |
| Block rate | **4 096 blocks per second.** Two windows each independently imply 4 096.0 from a known note (128 and 512 Hz). This is the rate Dolphin's model uses. | **C** (two windows of one run) | GBP-HW-301, GBP-AUD-001; the repeat that would make it FACT: `U-GBP-037` |
| Block rate, as drained | A full-read drain completed 4 096 ± 1 blocks in each of the 57 whole 1.000 s windows it counted, and 245 757 blocks in 60.000017 s of the GameCube's timebase. | F (the measurement, one run) | GBP-HW-319 |
| One block, one sample | The AGB's audio is the modulation **across** blocks, each block behaving as one sample of it. A block is not a time series of the note. | F (the measurement); **C** (the reading) | GBP-HW-298 |
| Byte rate, arithmetic | 4 096 blocks/s × 4 096 B = 16 777 216 B/s = 2^24 B/s, one byte per AGB cycle at the AGB's documented 2^24 Hz clock. This is arithmetic and inherits the rate's **C**. It claims no transfer mechanism. | C (inherited from the rate) | GBP-HW-301; `HARDWARE_TESTS.md` §V18.6 |

## 2. Inside one block

| Property | Value | Status | Evidence |
| --- | --- | --- | --- |
| Pulse | A **1-bit PWM pulse**, not a byte pattern. Each 256-byte cell is ~120 bytes of `0xFF`, ~120 of `0x00`, and a few partial bytes at the edges. Every distinct byte value seen across three runs is a run of contiguous one-bits. The sample is the pulse's width **in bits**. | F (the structure, three runs) | GBP-HW-304, GBP-HW-287 |
| Cell | Sixteen cells of exactly **256 bytes** (2 048 bits) per block, with 0 exceptions over 1 280 blocks. The cell is present with the AGB's sound hardware provably disabled, so it belongs to the transfer, not to any tone. | F (run-scoped, two runs) | GBP-HW-287, GBP-HW-296 |
| Rest | Duty 128/256 in every block of the two runs' control windows, one of them with the AGB's sound hardware disabled. The edge bytes differ between the two cartridges (`01`/`FE` against `03`/`07`/`FC`), which is recorded and not explained. The decode measures its resting level per run and never assumes it. | F (run-scoped) | GBP-HW-288, GBP-HW-296 |
| Block shape | Over its sixteen 256-byte slices, every block of RUN 33 and RUN 34 (2 560 blocks) is **flat** (spread ≤ 3 bits) or **one step**; no other shape occurs. | F (a recomputable property of the archive) | GBP-HW-314; the 1–3-bit spread: `U-GBP-043` |
| Steps | The step blocks are exactly the programmed edges. The first plateau of each step equals the previous block's level, and the second equals the next block's, within 1.25 bits. All 304 transitions fall on an **even** slice. A block therefore records where in its interval a level change fell, at two-slice granularity. | F (the coincidence); **C** (that slice order is time order) | GBP-HW-315; slice uniformity and the grid's origin: `U-GBP-041` |
| Counting | Count **bits**, not bytes. Byte duty is quantised to 8 bits **and** phase-sensitive: the same pulse width reads as a different byte duty depending on where its edge falls within a byte. | F (two runs, same volume; the mechanism is a recomputable property of code and data) | GBP-HW-309, GBP-HW-312 |
| Dolphin's byte layout | Dolphin's layout — 0x400 PWM bytes, each mirrored ×4, with the 1-bits contiguous and leading — is **refused** by every block with a cartridge running. Only the byte layout is refused; the rate stands. | F (the refusal, run-scoped) | GBP-HW-287, GBP-HW-296, GBP-AUD-001 (amendment) |
| No Game Pak | The one capture made with no cartridge has 3 969 of its 4 096 bytes zero and only the values `00`/`01`/`11`. It is recorded raw and not interpreted. | F (the bytes of one block) | GBP-HW-057; byte-0 class: `U-GBP-021` |

## 3. Decoding it

| Property | Value | Status | Evidence |
| --- | --- | --- | --- |
| The layout | Each sample is the block's one-bit count minus the run's resting level, at 4 096 samples/s. This decodes RUN 33 and RUN 34 to the AGB's programmed tones: periods of 32 / 8 / 16 / 4 samples, which is 128 / 512 / 256 / 1 024 Hz exactly, with uniformity 1.000 in all eight windows and a DFT peak at the same frequencies. | **C** (one decode construction against one set of predictions, one cartridge) | GBP-HW-313 |
| Amplitude law | The deviation from rest is **linear** in the AGB's envelope volume, about 2.0/256 per volume unit with an intercept near 0. It was judged in one run by a gate frozen before that run. | F | GBP-HW-305 (FACT since Issue #85) |
| At 1 024 Hz | A period holds four levels: the extremes, plus two made by a step inside the block. The lower modal "deviation" there is a tie-break in the summary, not an attenuation. | C (as `GBP-HW-313`); the steps: F (as `GBP-HW-315`) | GBP-HW-313, GBP-HW-315 |
| Slice decode (2026-09-24, Issue #118) | Decoded by slice PAIRS instead of one value per block, RUN 33's and RUN 34's blocks are the programmed square waves sampled at 32 768/s nominal (correlation ≥ 0.99998; the same odd harmonics to the 127th; 2.5–18.7 % of each tone's energy above 2 048 Hz). The one-value-per-block decode has its Nyquist at 2 048 Hz, so none of that energy can be in it; and being a boxcar-and-decimate with no anti-alias stage, it folds part of it onto in-band bins (at 512 Hz its |H3|/|H1| is 0.263 against 0.334). For these tones the bytes hold at least 8× the bandwidth the runtime decodes. **No game's blocks exist in the archive.** | F (arithmetic on the archive); the Hz axis is conditional on uniform slices (`U-GBP-041`) | GBP-HW-340; the cost, in today's units, is there too |

What each block integrates over, and so the exact transfer function from the AGB's
output to a sample, stays **open** (`U-GBP-012`, narrowed by `U-GBP-041`). The
reading that a block integrates over its interval is a HYPOTHESIS inside
`GBP-HW-313` and is not stated here.

## 4. When the window carries sound

This page states **no carriage latency** in either direction. The early runs saw
windows carry nothing for seconds after the AGB began to emit. **Those delays are
refuted as properties of the path**, first against the CONTROL transform
(`GBP-HW-299`'s amendment, `GBP-HW-307`) and then against the first emission
(`GBP-HW-307`'s Issue #78 amendment).

What replaced them is not promoted. `GBP-HW-308` and `GBP-HW-311` record that the
emitting window itself carried in RUN 33 and RUN 34, but neither entry carries a
status. `GBP-HW-311` also leaves two dead windows of the earlier runs unexplained.
The instrument's first-press defect is `U-GBP-040`.

## 5. Draining it

| Property | Value | Status | Evidence |
| --- | --- | --- | --- |
| Failures are not coverage | 272 145 whole 0x1000 reads with 0 failures still fell 68 blocks short of 4 096/s over each of two captures. The DMA's failure count cannot see a missed block, and the block carries no sequence number. **A drain must count coverage against the timebase, not DMA completions.** | F (the counts); where the audio loss sits is an inference | GBP-HW-316 |
| Steady state | With whole-block reads the drain keeps up: 4 096 ± 1 blocks in every 1.000 s window from 3 s to 60 s, with a largest completion gap of 0.473 ms. | F (the measurement, one run) | GBP-HW-319 |
| Start-up stalls — this project's service path, not the device | This project's shared service path (`gbp_vstate`) shows the same start-up signature in all seven archived sessions: 13 incomplete frames, 26 resyncs and the same four preserved episodes, over sessions of 27.9 s to 273.8 s. The ~70-block deficit of earlier sessions is a start-up cost. | F (the signature, a property of the archive); **C** ("a start-up cost") | GBP-HW-317, GBP-HW-319; what produces the stalls: `U-GBP-044` |
| Short reads | A 32-byte read at index 0x8 does **not** keep the drain in sequence: the decoded period is 4–8 against the programmed 32. The full-read recovery window after it decoded 63 periods of exactly 32 and one of 18, which is NO-RECOVERY. **Read whole blocks.** | F (the gate's result); the mechanism is unknown | GBP-HW-321; 0x100 and 0x400 untested: `U-GBP-042` |
| An SD write inside the drain | One 65 536-byte SD2SP2 write, made synchronously in the drain's pump slot, took 24.43 ms and cost **100 blocks, lost and not delayed**: that second counted 3 996, and the seconds either side counted 4 096. | F (one write, one card, one size) | GBP-HW-320 |
| A producer stretch between services | Measured on this project's service loop, where producer work runs in a slot between two service cycles. **One uninterrupted stretch of about 0.2 of a block period (~49 µs) measurably costs blocks.** The same work split into half-size calls (~0.1 of a period) cut the gaps with an undrained block per AI cycle to **0.341** of the full-size calls' (90 % CI 0.306–0.379), a 62–69 % reduction. That came from an interleaved, pair-balanced comparison inside one session. The requirement it implies for any runtime: **keep each uninterrupted stretch of work between AUDIO services short.** Halving the stretch is **not a cure**: the half-size calls still lost 0.25 gaps per cycle, and what causes the rest is open. **2026-09-24, Issue #116, restated on top:** those figures integrate over a 10 s test-instrument window (L2) whose cost fell mostly on the half-size arm. Outside it, the ratio is **0.270** (90 % CI 0.235–0.308), a 69–77 % reduction, and the half-size calls lost **0.198** gaps per cycle (`GBP-HW-339`). The effect is larger than first stated, and the residue stands. | F (the result, one run); **C** (that the stretch's length is what starves the drain: one manipulation, one run) | GBP-HW-332, GBP-HW-327, GBP-HW-329; the rest: `U-GBP-045` |

## 6. Playing it on a GameCube — this project's design, not the device

| Property | Value | Status | Evidence |
| --- | --- | --- | --- |
| Output path | The GameCube's AI played this project's decoded samples of recorded windows, resampled by 125/16 to 32 000 Hz. The listener heard four distinct pitches, in the sealed relative order. That is a result about the relations between the pitches, never about absolute pitch. | F (what played); OPERATOR OBSERVATION (what was heard) | GBP-HW-318 |
| The live chain | Drain → decode → counted clock correction → resample → AI, all live, was run once (`HARDWARE_TESTS.md` §V22.12, RUN 38); its results are the next row. The following are **design choices, not properties of the device**: the ring of 4 096 decoded samples, the 200-block minimum (twice the largest stall measured in `GBP-HW-320`, a rule frozen before that measurement), the ±16-sample correction band, the 1 000-frame chunks, and, since GitHub Issue #109, **8-push production calls** (62.5 frames a call). That size was measured in RUN 40 and is the smallest measured one; the path's requirement it serves is §5's producer-stretch row, and 1-push calls cannot keep up with the pump slot. | — (design) | §V19.3, §V22.0, §V22.10, §V24.10 |
| The live chain, run once | The chain is bit-exact over a 10 s window: the host reproduced the CRC of the bytes handed to the AI DMA (L2 PASS). Over 64 s the AI was never handed silence and the ring never overflowed (C PASS). Composed, the drain lost 0.62 % of AUDIO blocks (4 060–4 081 per second; **2026-09-24, Issue #116:** 0.60 % outside the 10 s L2 window, 0.74 % inside it, `GBP-HW-339`), so `QUESTION L` was INCONCLUSIVE, and the correction band duplicated about 30 samples per second. What costs the drain is open (`U-GBP-045`). **2026-09-24, Issue #118:** `L2 PASS` means the chain reproduces on the host what it produced on the console; it never meant the chain captures what the cartridge played (`GBP-HW-340`). | F (the gates' results and the counts, one run) | GBP-HW-322, GBP-HW-323, GBP-HW-324 |
| The AI's rate | 32 028.483 Hz in the console's own timebase over 2 030 DMA callbacks: +0.42 ppm from Dolphin's 108 MHz / 3372 and +890 ppm from 32 000. It corroborates Dolphin's model. | F (the measurement, one run) | GBP-HW-325 |
| The cushion (`TARGET`) | **0.125 s since 2026-09-25 (GitHub Issue #121); 0.5 s before.** The fill the counted correction holds is a latency, so the value is set in time and the sample count is recomputed from the decoder's rate: 512 decoded samples at today's 4 096 per second. RUN 43 ran 0.125 s as an arm, interleaved with 0.5 s inside one session on a real cartridge. **No increase in AUDIO loss was detected at 0.125 s, and a lower loss is not established.** The primary statistic is the exact permutation of the 12 dwells, one-sided p 0.068, which holds its size under the design's own null: 16 of 400 simulations at one-sided 0.05 (`ThePermutationsSize`). The percentile interval, 0.798–0.977, is descriptive and anti-conservative by a measured 15.75 % against 10 % (`tests/host/test_v27derive.py`, `TheIntervalsCoverage`). No underrun and no overflow occurred in 71 s, which puts the underrun rate below 3/71 = 0.042 per second at 95 % only (rule of three). **It reduces the audio-behind-video offset and does not remove it:** the chain still holds this cushion, the READY queue, the DMA chunk and the FIR (`U-GBP-046`, open). Nothing shallower is adopted: 0.094 s was only visited in Phase 2's exploration, and the correction's floor is unmeasured (`U-GBP-045`). It is the chain's default, `GBP_APLAY_TARGET`. The default was 0.5 s (2048 samples) in every build before #121; each executed image reproduces at its own commit (`HARDWARE_TESTS.md` §V23.9), and `sync-0001`, which set its own levels through `gbp_aplay_set_target` (2048 / 512 / 384, literals in `gbp_async.c`) and so ran 0.125 s and 0.094 s in RUN 43, keeps them. | — (design) | GBP-HW-343, GBP-HW-341, §V27.20.7, §V27.20.13 |

## 7. Not established — pointers only

- **`U-GBP-012`:** what each AUDIO block integrates over, and so the exact transfer
  function from the AGB's output to a sample. Since Issue #118 the format half is answered for the archived tones (`GBP-HW-340`); a game's needs a raw-block capture.
- **`U-GBP-041`:** whether the sixteen slices are uniform in time, and whether the
  two-slice grid comes from the path or the source. That the grid is the AGB's
  32 768/s PWM rate is a HYPOTHESIS inside `GBP-HW-315`.
- **`U-GBP-043`:** the 1–3-bit spread between the slices of a flat block, and whether
  a slice's bit arrangement carries anything its count does not.
- **`U-GBP-042`:** reads of 0x100 and 0x400. The question is answered NO for 0x20
  only.
- **`U-GBP-044`:** what produces the start-up stalls, and where the three the log
  does not locate fall.
- **`U-GBP-045`:** what costs the composed runtime's drain about 25 AUDIO blocks per
  second (24.50 outside the L2 instrument's window, `GBP-HW-339`), and whether that is the perturbation the Operator heard. Since RUN 40, most of
  that cost is a producer stretch (§5). What stays open is what causes the rest, including
  the gaps no recorded step overlaps.
- **`U-GBP-037`:** the repeat that would make the rate FACT.
- **`U-GBP-014`:** AUDIO/VIDEO IRQ timing.
- **`U-GBP-021`:** the byte-0 class of the cartridge-less capture.
- **`U-GBP-040`:** the instrument's first-press defect. It is a property of the test
  ROM, not of the path.

These are also not established, and have no `U-GBP` id:
- the carriage latency (§4);
- whether the one pulse per block is the AGB's left, right or mixed output;
- GB/GBC-mode audio (Phase 7);
- synchronisation with video.
