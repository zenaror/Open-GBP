# Game Boy Player — VIDEO path (consolidated after Phase 4, 2026-09-21)

What GameCube software receives from the VIDEO window and what the Open-GBP
runtime does with it, consolidated from the physical runs of Phase 4
(`docs/research/HARDWARE_TESTS.md` §V5–§V6, runs `video-0001` through
RUN 13). **Every row carries the evidence id that supports it and the status
`docs/research/EVIDENCE.md` gives it** — **F** fact (observed on this
project's hardware unless marked *(code)* or *(software)*), **C**
corroborated. Nothing whose status is HYPOTHESIS or UNKNOWN is stated here as
a property of the device; open questions are pointed at by their `U-GBP-`
id and nothing more. A claim measured in one run or one window is written as
such. Register-level addressing, the IRQ register and the service cycle are
in `REGISTERS.md` and `INITIALIZATION.md`; this page does not repeat them.

## 1. The block

| Property | Value | Status | Evidence |
| --- | --- | --- | --- |
| Size and trigger | 0xF00 bytes per VIDEO IRQ (IRQ register bit 8 = 0x0100), read as one ARAM DMA from index 0x1 | F | GBP-HW-051, GBP-HW-064, GBP-HW-138 (105 841 transfers, all completed) |
| Geometry | 4 raster lines × 240 pixels × 4 bytes, line stride 960 bytes; reconstructing preserved raw frames this way produced a legible, animated 240 × 160 logotype | F | GBP-HW-081; the references' model: C, GBP-VID-002 |
| Pixel word | `hh hh ll ll` — a 16-bit value with each byte doubled; the pixel is bytes 1 and 3, `(b1 << 8) \| b3`, exactly as both reference decoders consume it | F (code) for the references; F for physical consistency | GBP-VID-003; GBP-HW-058, GBP-HW-132 (bytes 1/3 identical in 38 400 of 38 400 words across two runs) |
| Bytes 0 and 2 | consumed by neither reference; vary between consumed-identical physical frames of the same picture; **do not consume them** | F (that they vary) | GBP-HW-126, GBP-HW-133; meaning open, U-GBP-029 |
| Colour | 15 bits: the window exchanges the two outer 5-bit groups relative to the AGB framebuffer (AGB bits 4–0 → word bits 14–10 and vice versa, 9–5 unchanged), so under the reading bit 15 flag / 14–10 R / 9–5 G / 4–0 B the delivered colour is the AGB's intended colour; `CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP` under a pre-registered contract, one of seven candidates, reproduced by a second run | F | GBP-HW-130, GBP-HW-131, GBP-HW-132 |
| Colour, stated limit | a permutation fixing bits 0, 5 and 10 and each group as a set while rearranging only bits 1–4 inside a group is not excluded by the stimulus used | F (the limit, recorded before the run) | GBP-HW-131; `HARDWARE_TESTS.md` §V3.19 |
| Bit 15 | set on exactly one consumed word per frame, at pixel (0, 0), in every physical frame captured; the AGB wrote 0 there, so the bit is added on the path and is not the colour value | F | GBP-HW-129, GBP-HW-077; origin open, U-GBP-034 |

## 2. The frame

| Property | Value | Status | Evidence |
| --- | --- | --- | --- |
| Blocks per frame | 40 blocks of 4 lines = 160 lines; 477 of 489 measured frame intervals were exactly 40 blocks; 2 048 consecutive retained frames of 40/40 blocks in each qualified window | F | GBP-HW-076, GBP-HW-081, GBP-HW-184 |
| Frame start | the first pixel word of the frame's first block carries bit 15; the Start-up Disc's predicate (bit 7 of byte 1) and GBI's (bit 7 of bytes 0 and 1) agreed on all 19 601 blocks measured; the block index restarts at the marker | F | GBP-HW-066, GBP-HW-077; the predicates: F (code), GBP-VID-004 |
| Order | blocks in ascending order from the marker, block `i` = lines `4i..4i+3` | F | GBP-HW-081; the references: F (code), GBP-VID-005 |
| Source cadence | 59.727 Hz measured as the median of 465 consecutive complete frames in one run and as 59.7271 FRAME_ID/s over 34.27 s in another; 59.547 Hz in a single early interval; reported as measurements, no nominal rate promoted | F (measurements, run-scoped) | GBP-HW-078, GBP-HW-187, GBP-HW-067 |
| Startup region | the first ≈ 3.4 s of structured startup after the AGB is started are the same on two cartridges and without a cartridge; the boot animation begins ≈ 0.5 s after the AGB starts and settles ≈ 3.6 s | F | GBP-HW-226, GBP-HW-079, GBP-HW-080 |
| Startup region, short intervals | frame intervals of 30/34/38 blocks occur in the startup region of every run and nowhere else; a startup signature that predates streaming; **not** source loss — whether blocks were lost, boundaries observed early or late, or causes coalesced is open | C | GBP-HW-141, GBP-HW-216; U-GBP-030 |

## 3. Service, as the streaming runtime exercises it

The per-interrupt cycle itself is `INITIALIZATION.md` §4 / §14 and the IRQ
register model is `REGISTERS.md` §4. What Phase 4 adds is its behaviour under
sustained video service:

| Property | Value | Status | Evidence |
| --- | --- | --- | --- |
| Cycle | drain every block named by the service read → ACK `pending \| 0x8000` → PI clean → `IRQ := 0` → next cause; the next cause arrived 43.9 µs after the first physical re-arm | F (one cycle), then repeated | GBP-HW-053, GBP-HW-054, GBP-HW-055 |
| Sustained service | 209, 51 751, 1 114 007 and 1 114 005 consecutive cycles, then 280 621 and 280 672 cycles with a consumer, a converter and a GX display attached, then 240 754 on a retail cartridge and 254 8xx on each of runs 9–13 — every one with `unmasks = deliveries = acks = rearms`, 0 timeouts, 0 busy, 0 uncertain, 0 errors | F (each run) | GBP-HW-062, 074, 099, 109, 138, 150, 225, 236, 241, 247, 253, 259 |
| Whole-block DMA | one DMA of 0xF00 (VIDEO) and 0x1000 (AUDIO) per source, the same routine as the 32-byte accesses; 61.4 / 66.5 µs around the call on the first physical read | F | GBP-HW-050, GBP-HW-051 |
| IRQ-window reading | the eight replicas of one read are not guaranteed to carry one value; GBI's bitwise majority is the authoritative reading and the `SOURCE_SERVICED` disagreement is serviced as a counted, nonfatal event — 23, 29 and 42 events survived in three workloads, the omitted AUDIO source present in the next ordinary read every time | F (the events and the policy's outcome); C (the same behaviour under a streaming workload) | GBP-HW-100, GBP-HW-110, GBP-HW-113, GBP-HW-142; mechanism open, U-GBP-033 |
| Consumer slice | frame work outside the service path, in slices of 28–41 µs that yield to a pending cause; ≈ 25 % of pump calls found a cause pending; no observable transport effect in any run; the timing margin has not been measured | F (measurements) | GBP-HW-140, GBP-HW-150 |

## 4. Startup, up to the first real hand-off

| Property | Value | Status | Evidence |
| --- | --- | --- | --- |
| Prefix | detection probes → CONTROL transform → the IRQ-register first-pass writes (A1, A2) → handler install → PREUNMASK check → first unmask; the two diagnostic items of research builds (a visible self-test, a 5 000 ms masked wait) are not part of it | F (software, from the source) | GBP-VID-028 |
| First real hand-off | 164.696–165.155 ms after the CONTROL transform on eight runs and two cartridges (`ticks_control_to_first_handoff` 6 670 174 … 6 688 767 at 40.5 MHz); CONTROL → capture start ≈ 107 ms; nothing synthetic handed to the video interface in the NORMAL profile | F | GBP-HW-215, 224, 235, 241, 247, 253, 259; GBP-HW-214 |
| What the user sees | the cartridge's own boot sequence, exposed from ≈ 165 ms; on a retail cartridge the operator saw the logo appear complete, a clean transition and a stable game | C (the sequence); OPERATOR OBSERVATION (the eye) | GBP-HW-229, GBP-HW-227 |
| Research builds | a 5 000 ms masked wait before the handler hides the AGB boot entirely (the animation happens inside the wait) and the Game Boy Player tolerates that pause; a content-blind not-before gate at 5.000 s after CONTROL keeps the research witness out of the boot without touching the startup | F | GBP-VID-027, GBP-HW-120, GBP-HW-116, GBP-HW-233, GBP-HW-235 |

## 5. Presentation-path structure the runtime relies on

| Property | Value | Status | Evidence |
| --- | --- | --- | --- |
| Texture path | each 0xF00 block is repacked from bytes 1/3 into 4 × 4 `GX_TF_RGB5A3` tiles with bit 15 forced, exactly the references' conversion; no per-pixel colour arithmetic is needed because the device already delivers the RGB5A3 order | F (code) for the references; F for the runtime's texture equalling the oracle | GBP-VID-003; GBP-HW-258 (texture == Python == host C == tiled oracle, eight frames) |
| Display | a 240 × 160 `GX_NEAR` texture drawn as one quad at native size, centred in a 640 × 480 framebuffer; the GX draw-done token and the ownership machine (at most one token in flight, the callback releases exactly one buffer by index) ran on hardware with zero invariant failures in 468 289 checks | F | GBP-HW-134, GBP-HW-139, GBP-HW-149, GBP-HW-144 |
| Scaling, aspect, filtering | deliberately absent; Phase 9 policy (`ROADMAP.md`, GBP-VID-032) | F (design) | GBP-HW-144, GBP-VID-032 |
| Presentation opportunities | source-driven: a present happens because a conversion finished; there is no VI-driven display loop and no retrace callback | F (software, from the source) | GBP-VID-017 |
| Policy A | two framebuffers with asynchronous deferral: a frame that finds both framebuffers spoken for is deferred, in order, and handed over on the next retrace; a third framebuffer would turn deferrals into supersessions, not into presentations | F (software, simulation and proof from the source) | GBP-VID-022, GBP-VID-024, GBP-VID-025 |
| Policy A, physically | zero interior source drops, order preserved, deferral depth never above 1, hand-off latency p99 ≤ 0.4946 ms and max ≤ 1.1353 ms against gates of 1.0 / 2.5 ms, on runs 6–13 including a retail cartridge | F (each run) | GBP-HW-205, 206, 207, 208, 209, 217, 225, 236, 241, 247, 253, 259 |
| Rate conversion | the source (59.727 Hz) into the video interface (59.940 Hz) requires ≈ 7 repeated display intervals per 34 s window; they are the VI showing one framebuffer for one extra period, not lost frames; the board does no synchronisation | F (run-scoped); F (no synchronisation) | GBP-HW-210, GBP-HW-211; GBP-VID-020; GBP-PHY-003 |
| Hand-over vs scanout | `VIDEO_SetNextFramebuffer` is a hand-over; in RUN 13 every hand-over of the four appearance sets was observed latched with register-consistent read-backs (L = 40/40/39/40), and the operator saw the digits in order — GBP-VIDEO-007 = PASS as CLAIM-D only: at least one source-derived frame per appearance was physically visible through the declared chain, a digit bound to a 40-frame set, never to one frame | F (the chain); OPERATOR OBSERVATION (the eye) | GBP-HW-260, GBP-HW-256 |

## 6. Not established by Phase 4 — pointers only

Physical pixel equality on any display and per-frame scanout accounting
(GBP-HW-260 non-claims); fidelity of frames not sampled (GBP-HW-258);
correctness of retail content by measurement (GBP-HW-225, 230: no OGBPIDX
verdict on retail content); presentation and pixel-perfect scaling
(GBP-VID-032, Phase 9); the AUDIO block's format and cadence (U-GBP-012,
U-GBP-014, Phase 6; consolidated since in `AUDIO.md`); KEYPAD (Phase 5 — never written at the time of the
assessment; written on hardware 2026-09-21, `INPUT.md`); bytes 0/2 (U-GBP-029);
bit 15's origin (U-GBP-034); the startup-region short intervals (U-GBP-030);
the IRQ-window non-uniformity's mechanism (U-GBP-033). The assessment that
weighed these against Phase 4's acceptance criterion is
`docs/research/PHASE4_ASSESSMENT.md`.
