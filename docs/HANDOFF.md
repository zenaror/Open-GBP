# Open-GBP Project Handoff

## Purpose

This document is a **navigation and state index**. It is not evidence, and it
does not replace `docs/research/EVIDENCE.md`, `docs/research/HARDWARE_TESTS.md`
or any design document. Every conclusion below points at the source that owns
it; when this file and a source disagree, **the source wins** and the divergence
gets recorded.

Read `AGENTS.md` first.

## State baseline

```text
STATE BASELINE COMMIT   8bde4ca9c91dd3aef500e34980d6a7e4f5ef6cb3
```

**What that means, precisely:** it is the **last commit whose scientific and
operational state was audited before this handoff snapshot was written**. It is
*not* "the expected current HEAD", and it is deliberately not this file's own
commit — a document cannot contain the hash of the commit that adds it. Expect
HEAD to be at least one commit ahead: the one carrying this text.

```text
LAST PHYSICAL EVIDENCE INGESTED
  GBP-VIDEO-004 / stream-0007 + indexed-0003, executed 2026-09-19 — RUN 5
  GBP-HW-192 … GBP-HW-201, GBP-VID-019
  STANDING: EXECUTED · SOURCE CONTIGUITY REPLICATED · HOLD CAUSE IDENTIFIED

  THE SOURCE GATE PASSED AGAIN, on a different build with the trace running:
  OBSERVED_CONTIGUOUS, 2048/2048 records, FRAME_ID 85..2132 complete, FAULT
  clear, VMARGIN 24. First evidence that the instrumentation did not disturb
  the source result.

  THE FIRST DOWNSTREAM TRACE. 2114 lifecycles, 2114 decisions, 19 holds.
  Joined by exact frame_index (NOT by the in_window flag):
      2048 source records = 2030 SELECTED_NEW + 17 HOLD + 1 capture-edge residual

  EVERY HOLD IS A PHASE CONDITION, from recorded state:
    reason XFB_BUSY · xfb_target NONE · current and pending holding both slots
    newest_source NONE at ALL 2114 decisions -- nothing was ever queued
    convert cost identical to selected frames (56 229 vs 56 237 ticks)
    submit_refusals 0, blocked_inflight 0, no_texture 0
  -> H2 and H3 NOT SUPPORTED. H1 CORROBORATED. H4 is the policy, by design.

  VI period by feasibility: 675 675.00 ticks = 59.940 06 Hz (NTSC nominal).
  Every hold falls in the final 0.580 ms of a 16.683 ms interval (3.48 %).
  Of the 16 decisions sharing a sampled retrace with their predecessor, ALL 16
  were holds and NONE was a select.
  Beat: 59.727 083 into 59.940 060 Hz predicts 280.44 source frames; observed
  cluster gaps mean 280.07 -- 99.87 %, stable across thresholds 15..30.

  A CORRECTION to the previous round: §V5.46.6 called held frames "already
  drawn". The DrawDone follows the decision in 2047 of 2047 cases. The
  conclusions survive -- they rest on the back-pressure counters -- but the
  word was wrong. §V5.47.6.

  AN OFF-BY-ONE IN OUR OWN INSTRUMENTATION, NOT FIXED HERE: OGBPDISP1's
  in_window covers 69..2116 while the scientific window is 70..2117, and
  tools/vdisp.py inherits it (GBP-VID-019). Frozen during ingestion; every
  number above came from the exact frame_index join.

  Previous: stream-0003 (GBP-HW-138…145), the FIRST real stream smoke, which
  found P1 and P2; stream-0002 (GBP-HW-134…137), ABORTED PRE-SERVICE, corrected
  in stream-0003 (§V5.30) and NOT a streaming failure — streaming was never
  reached.

  Previous: color-0002 (GBP-HW-127…133), CONFIRMATORY,
  CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP, U-GBP-011 CLOSED — the colour order is
  FACT; color-0001 (GBP-HW-120…126), INCONCLUSIVE under its own frozen contract,
  permanently, and never re-judged; PRE-HANDLER MASKED WAIT 5000 ms
  (GBP-HW-116…119).
```

### Staleness check — run this before trusting anything below

This file is **not automatically true because it exists**. Before relying on the
"current state" section:

```sh
git rev-parse HEAD
git status --short
git log --oneline $(sed -n 's/^STATE BASELINE COMMIT *//p' docs/HANDOFF.md)..HEAD
```

If that range contains commits, read them and decide whether any changes the
scientific or operational state. If it does, this handoff may be **STALE**:
reconcile against the authoritative sources first, and never update this file
silently before doing so.

## Mandatory read order

1. [`AGENTS.md`](../AGENTS.md)
2. this file
3. [`docs/README.md`](README.md)
4. [`docs/RESEARCH_METHOD.md`](RESEARCH_METHOD.md)
5. [`docs/research/EVIDENCE.md`](research/EVIDENCE.md)
6. [`docs/research/HARDWARE_TESTS.md`](research/HARDWARE_TESTS.md)
7. [`docs/research/UNKNOWNS.md`](research/UNKNOWNS.md)
8. [`docs/research/DEVLOG.md`](research/DEVLOG.md) — chronological decisions
9. [`CLAUDE.md`](../CLAUDE.md) — permanent project policies, all agents

## Source-of-truth hierarchy

```text
physical raw log (logs/, never versioned) and its fixture (captures/fixtures/)
    ↓
docs/research/EVIDENCE.md          classified claims
    ↓
docs/research/HARDWARE_TESTS.md    executed tests and experiment designs
    ↓
docs/hardware/ and docs/protocol/  consolidated reference, promoted only per RESEARCH_METHOD.md
    ↓
docs/HANDOFF.md                    this index
    ↓
README.md                          entry point
```

On conflict, use the source closest to the evidence and record the divergence.

## Current scientific state

| item | status | owner |
| --- | --- | --- |
| **GBP-VIDEO-002-R3** (semantic disagreement policy) | **PHYSICAL VALIDATION COMPLETE** | `HARDWARE_TESTS.md` §R3/§R4; GBP-HW-108…115 |
| **PRE-HANDLER MASKED WAIT 5000 ms** | **PHYSICALLY VALIDATED — only for the 5 s duration and the position exercised** | `HARDWARE_TESTS.md`, "PRE-HANDLER MASKED WAIT"; GBP-HW-116…119 |
| **Physical delivery of a controlled GBA ROM** | **RESOLVED** for the validated EZ-Flash Omega DE NOR / Mode B route | `HARDWARE_TESTS.md` §V3.7 and the route section below |
| **GBP-VIDEO-003 / `color-0001`** | **PHYSICALLY EXECUTED 2026-09-18 — INCONCLUSIVE UNDER ITS ORIGINAL FULL-RAW CONTRACT, permanently, and it is never re-judged** | `HARDWARE_TESTS.md` "GBP-VIDEO-003 / color-0001"; GBP-HW-120…126 |
| **GBP-VIDEO-003 / `color-0002`** | **PHYSICALLY EXECUTED 2026-09-18 — CONFIRMATORY CONTRACT PASS. `CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP`: the outer 5-bit groups are exchanged** | `HARDWARE_TESTS.md` §V4.10; GBP-HW-127…133 |
| **GBP-VIDEO-003 overall** | **COMPLETE for the controlled colour objective.** Do not re-open, re-run or re-derive it | §V4.10; `UNKNOWNS.md` U-GBP-011 |
| **GBP-VIDEO-004 downstream disposition** | **INSTRUMENT BUILT, QUESTION FROZEN, NOT EXECUTED.** `stream-0007` adds an observational lifecycle/decision trace and the `OGBPDISP1` sidecar. The audit that preceded it found that this runtime has NO VI-driven display loop, so presents are source-driven and every one of run 4's 17 holds was already converted, submitted and drawn (GBP-VID-017). **No cause is claimed and no pacing was changed** | `HARDWARE_TESTS.md` §V5.46; GBP-VID-015…018 |
| **GBP-VIDEO-004** (sustained streaming) | **SOURCE-FRAME CONTINUITY CLOSED for the qualified window.** `stream-0006` PHYSICALLY EXECUTED 2026-09-19 (run 4): the unmodified analyzer returned **`OBSERVED_CONTIGUOUS`** over 2 046 decisive transitions, 2 048/2 048 complete records, FRAME_ID 85..2132 with no member missing, FAULT clear, VMARGIN 24. Runs 1–3 on `stream-0005` keep their own verdicts permanently — run 3 stays `OBSERVED_ID_GAP` / `OBSERVED_DISCONTINUITY` and is NOT re-judged. Consumer/display disposition is the NEXT gate, not closed | `HARDWARE_TESTS.md` §V5.38–§V5.45; GBP-HW-180…191 |
| **`stream-0003`** | **PHYSICALLY EXECUTED 2026-09-18 — REAL CARTRIDGE VIDEO ON SCREEN.** Historical; never rebuilt or re-labelled. It found P2 and P1 | `HARDWARE_TESTS.md` §V5.34; GBP-HW-138…145 |
| **CONTROLLED indexed stimulus** (`stimulus/agb-indexed`) | **ROM, ANALYZER AND RUNTIME RETENTION IMPLEMENTED** to the frozen `OGBPIDX1` contract. ROM 2 460 B `379df0f7…c543`; renders 38 400/38 400 words identically to `tools/istim.py`. `stream-0005` retains the canonical witness at the SOURCE layer into the new `OGBPIDXCAP1` sidecar, bounded by a 2048-record target. **The ROM HAS NEVER RUN anywhere, and its DELIVERY image cannot be produced in this environment** (no `gbafix`) | `HARDWARE_TESTS.md` §V5.33, §V5.35, §V5.39 |
| **Dolphin's emulated Game Boy Player** | **EXISTS and is REACHABLE from a homebrew DOL** in the installed 2606a (`HSPDevice=2` + `GBPlayerRom`; no BIOS, no Start-up Disc). The exact `stream-0003` reaches the CONTROL gate on it and stops there: Dolphin's power-on CONTROL is `0x02`, hardware's is `0x90`. **AUXILIARY only** | `HARDWARE_TESTS.md` §V5.31 |
| **`stream-0002`** | **PHYSICALLY EXECUTED 2026-09-18 — ABORTED PRE-SERVICE: `store_or_bounds_invalid`.** GX self-test physically PASSED; **GBP stream capture never started**; `deliveries=0 acks=0 rearms=0 handler_installed=0`. Historical; never rebuilt, never re-labelled, and **not** a streaming failure | `HARDWARE_TESTS.md` §V5.29; GBP-HW-134…137 |
| **`stream-0001`** | **REJECTED before hardware — DO NOT RUN.** Historical; its identity is preserved and was not reused | §V5.26; `stream-0002` supersedes it |
| **Texture ownership** | **FIXED and TESTABLE**: moved to `src/gbp/gbp_vpresent.{h,c}`, at most ONE draw-done token in flight, the callback releases exactly one buffer by index | §V5.27.1 |
| **Physical ROM delivery dependency (§V3.7)** | **RESOLVED** — route 1, EZ-Flash Omega DE NOR / Mode B, two physical runs | §V3.7 resolution note |
| **VIDEO colour bit order** | **FACT** — measured with a known-colour stimulus, twice; promoted into `docs/hardware/GBS-DOL.md` and `docs/protocol/REGISTERS.md` | GBP-HW-131 |
| **Operator visual arming** | **REJECTED**: the stimulus is not observable during the pre-handler interval | `HARDWARE_TESTS.md` §V3.27 |
| **Procedure** | **FIXED PRE-HANDLER WAIT 5000 ms — PHYSICALLY SUFFICIENT for this stimulus at this position** | GBP-HW-120 |
| **Bytes 0/2 of a pixel word** | **vary between consumed-identical physical frames, in this run and in earlier fixtures; cause UNKNOWN** | GBP-HW-126; `UNKNOWNS.md` U-GBP-029 |
| **U-GBP-011** — VIDEO colour bit order | **CLOSED 2026-09-18**, on the conditions the item set for itself before the data existed | `UNKNOWNS.md`; GBP-HW-131 |
| **U-GBP-034** — what sets bit 15 of the VIDEO pixel word | **OPEN** (newly opened; not blocking). The bit is observably not the colour value and is added on the path; its origin is not established | `UNKNOWNS.md`; GBP-HW-129 |
| **U-GBP-029** — bytes 0/2: data or read-path artifact | **OPEN**, best test so far is `color-0001` | `UNKNOWNS.md`; GBP-HW-126 |
| **U-GBP-033** — mechanism behind semantic non-uniformity | **OPEN** | `UNKNOWNS.md` |

## Current physical delivery route

```text
canonical stimulus                stimulus/agb-color-bars  ->  agb-color-bars.gba
  sha256 867bb8d681e815793792e5e85bf031967eec11c07d00dcb16e68b6c96520f3ba  (1076 B)
  logo area EMPTY: this repository does not supply those bytes
        |
        |  LOCAL delivery packaging, official devkitPro gbafix (gba-tools v1.2.0),
        |  outside Git, into an ignored path. Only the header's logo area changes;
        |  the payload past 0x0C0 is byte-identical.
        v
derived cartridge image           build/physical/agb-color-bars-cart.gba   (not versioned)
        |
        v
EZ-Flash Omega DE  ->  NOR / Mode B  ->  physical GBA and physical Game Boy Player
```

The **canonical** artifact is the source authority and is reproducible from this
repository. The **derived** artifact exists only for physical delivery, is never
committed, and never replaces the canonical one. No proprietary bytes enter the
repository at any point.

## Frozen contracts

Changing any of these means a **new version**, never an edit.

| contract | frozen at | definition |
| --- | --- | --- |
| **OGBPSEQ1 v5** | physically produced; v2/v3/v4 are historical and frozen with their known defects | `src/gbp/gbp_vstatedump.h`, `tools/vstate.py` |
| **OGBPCOL1 v1** | frozen at the implementation checkpoint `e10423c`; `cert_rec` is **40** bytes | `src/gbp/gbp_vcoldump.h`, `tools/vcolor.py` |
| **OGBPIDX1** | the indexed stimulus WIRE format, frozen at §V5.33: layout, 54-bit payload, CRC-8, symbols, 24-bit ID, STATUS, canonical witness coordinates, classification rules. `stream-0005` changed the experiment's PROTOCOL, not this; **`stream-0006` changed neither** — it changes only WHICH frames are retained | `stimulus/agb-indexed/`, `tools/istim.py`, `tools/vindex.py` |
| **OGBPIDXCAP1 v1** | the witness CAPTURE sidecar, new in `stream-0005`. A new magic, never an OGBPSEQ1 version: header 0x180, record 4368 (48 B metadata + 40 x 54 big-endian u16, each record CRC-sealed), `"OGBPEND1"` footer. **`stream-0006` did NOT change it** (§V5.44.9): the window is reported in the `.log` `WITQUAL` line and is visible here as `record[0].frame_index != 0` | `src/gbp/gbp_vidxdump.h`, `tools/vidxcap.py` |
| **OGBPDISP2 v2** | the DOWNSTREAM sidecar as `stream-0008` writes it: header 0x140, lifecycle 128 B, event 40 B, `"OGBPDEND"`, three CRC-32s. Adds the defer aggregate (`t_first_attempt`, `t_first_defer`, `t_last_defer`, `defer_attempts`), the non-terminal `DEFERRED` and edge `TERMINAL_PENDING` dispositions, and a header block of source-disposition counters. It carries NO scientific-membership field on purpose: the population is the exact `frame_index` join. **PHYSICALLY EXERCISED in run 6** (2114 lifecycles, 2165 events, all four CRCs verified independently, `decisions 2114 + deferred 51 = 2165 = event_n`) | `src/gbp/gbp_vdispdump.h`, `tools/vdisp.py`, `HARDWARE_TESTS.md` §V5.49.5 |
| **OGBPDISP1 v1** | the DOWNSTREAM disposition sidecar, new in `stream-0007`. A new magic, never a version of OGBPIDXCAP1: header 0x100, lifecycle record 96 B, event record 40 B, `"OGBPDEND"` footer, three CRC-32s (header, per section, global). Keys on the assembler's generic `frame_index`; carries no pixels and no FRAME_ID. **PHYSICALLY EXERCISED in run 5** (2114 lifecycles, 2114 decisions, all four CRCs verified) and still parsed by `tools/vdisp.py`. KNOWN DEFECT: `in_window` is one frame early — GBP-VID-019. Superseded for new builds by OGBPDISP2, and NEVER reinterpreted | `src/gbp/gbp_vdispdump.h`, `tools/vdisp.py`, `HARDWARE_TESTS.md` §V5.46.12 |
| **OGBPIDX1 WINDOW POLICY** | pre-registered at §V5.44 BEFORE the run it judges: 64 consecutive structurally qualifying frames, arming at a block-0 boundary, one-way. Structural terms only — no `FRAME_ID`, `STATUS`, `SYNC`, `CRC-8`, colour or expected payload. **PHYSICALLY EXERCISED in run 4** (warm-up 70 frames, 4 disqualified, 1 reset, armed at a block-0 boundary). Changing N now requires a new build id and a new pre-registration | `src/gbp/gbp_vwitness_drive.h`, `HARDWARE_TESTS.md` §V5.44 |
| **`color-0001` analysis contract** | frozen at `bfbca70`; full-raw A/B/C byte equality. It refused `color-0001` and that verdict is permanent — `tools/vcolor.py` gains no option that could change it | `tools/vcolor.py`, `HARDWARE_TESTS.md` §V3.25 |
| **`color-0002` analysis contract** | pre-registered before the run it judges; consumed-word equality over 38 400 words, bit 15 included. Changing it after `color-0002` has run requires **`color-0003`** | `tools/vcolor2.py`, `HARDWARE_TESTS.md` §V4 |

## Exact physical artifacts

**A rebuilt binary does not inherit physical status.** This project embeds the
commit identity in its images, so the same source at another commit produces a
different hash. Match the SHA-256 before saying "physically tested".

| experiment | build id | commit | exact DOL SHA-256 | status | reference |
| --- | --- | --- | --- | --- | --- |
| GBP-VIDEO-002-R4 | `vstate-0004` | `b017e38` | `b0ed33f06e257d1e775d382f86116a59b756d90b528c0be3f233e086d00597c5` | PHYSICALLY EXECUTED | GBP-HW-108…115 |
| pre-handler masked wait | `vstate-prewait-5000` | `500429a` | `b5f0060a46d2e6429f494a9fa53d14acf07a97f61d01847acf0b6cb807a48709` | PHYSICALLY EXECUTED | GBP-HW-116…119 |
| GBP-VIDEO-003 | `color-0001` | `e10423c` | `32ea371cd3b51c52f8459e5b67e91c8a046b2ea8ab58a48668494290f668164b` | superseded: no pre-handler wait | `HARDWARE_TESTS.md` §V3 |
| GBP-VIDEO-003 | `color-0001` | `9d8302d` | `cc88e4c45559f11047ca657b78045e2fd2c5d646a1b68e7e453fcf796d177cf4` | **PHYSICALLY EXECUTED 2026-09-18** | GBP-HW-120…125 |
| GBP-VIDEO-003 | `color-0002` | `39f1980` | `d3c1f09efb105a0027d3bc596528448c579a234cbbe8306469d7f1222cbf29c1` | **PHYSICALLY EXECUTED 2026-09-18 — the confirmatory run** | GBP-HW-127…133 |
| GBP-VIDEO-004 | `stream-0001` | `0816cbe` | `0dc2c50101b5cc6c3906e89f845b89d4d218ccd7ee05ff04764de68b1169d275` | **REJECTED before hardware — DO NOT RUN** | `HARDWARE_TESTS.md` §V5.26 |
| GBP-VIDEO-004 | `stream-0002` | `2457d51` | `76fa1ff797a05aee37d50fe2b2ae1c7c7ffb2d57fb97166a1322a9c54f24831d` | **PHYSICALLY EXECUTED 2026-09-18 — ABORTED PRE-SERVICE (`store_or_bounds_invalid`).** 466 272 B. Historical; never rebuilt, never re-labelled. Superseded by `stream-0003` | `HARDWARE_TESTS.md` §V5.29; GBP-HW-134…137 |
| GBP-VIDEO-004 | `stream-0003` | `03b32a9` | `2f8e362e40b7e7dae1b3c2069a2a0fdb6376d22f43e3476cc7b28d7c13d199e3` | **PHYSICALLY EXECUTED 2026-09-18 — REAL CARTRIDGE VIDEO ON SCREEN.** 471 648 B. Historical; never rebuilt or re-labelled | `HARDWARE_TESTS.md` §V5.34; GBP-HW-138…145 |
| GBP-VIDEO-004 | `stream-0004` | `e11df66` | `56f2687377f261a865ec05efb8d71ec71c79b664389fec8b31dc038545977c43` | **PHYSICALLY EXECUTED 2026-09-19 — P1 AND P2 CONFIRMED FIXED.** 472 160 B. Historical; never rebuilt or re-labelled | `HARDWARE_TESTS.md` §V5.38; GBP-HW-146…152 |
| GBP-VIDEO-004 **last physically executed** | `stream-0008` | `5126a19` | `a9efe181d46928d11a20623276a77f352db45b9795681173185e9a60d4e81282` | **PHYSICALLY EXECUTED 2026-09-19 (run 6) — SOURCE-LOSSLESS IN ORDER. 2047/2047 interior scientific frames handed off, 0 drops, 0 supersessions, 0 reorder, max deferred depth 1, p99 0.4946 ms / max 1.1353 ms, and 7 display repeats against a same-run requirement of [7, 8]. Twelve of twelve pre-registered gates passed (§V5.50).** POLICY A: two-XFB asynchronous deferral (§V5.49). A frame that finds no writable framebuffer is DEFERRED and offered again by `pump()`, in age order, instead of being discarded. No third XFB, no extra texture, no VI callback, no `VIDEO_WaitVSync`, no queue-depth change. Downstream sidecar bumped to `OGBPDISP2` because a non-terminal DEFER cannot be expressed in v1 without overloading `HOLD_PREVIOUS_FRAME`. 492 416 B. Built twice from scratch and byte-identical both times; Swiss `build/swiss/12-stream/boot.dol` identical; MEM1 keeps 4.58 MiB free after the framebuffers. 15/15 mutants refused. **Reproduce with `GIT_COMMIT=5126a19 GIT_DIRTY= make build`** | `HARDWARE_TESTS.md` §V5.49 |
| GBP-VIDEO-004 **previous run** | `stream-0007` | `ddf8db6` | `74b7488630153ce3baaa42831a9af8ef03a2bce80399d840062965a34906eb36` | **PHYSICALLY EXECUTED 2026-09-19 (run 5) — source `OBSERVED_CONTIGUOUS` again, and the first downstream trace.** 491 040 B. Adds the OBSERVATIONAL downstream disposition trace and the `OGBPDISP1` sidecar (§V5.46) and nothing else: no pacing, queue depth, conversion, GX, XFB or VI change, and the interrupt path is byte-identical to the physically validated GBP-VIDEO-001 build. Byte-identical across two from-scratch builds; Swiss `build/swiss/12-stream/boot.dol` identical. **Reproduce with `GIT_COMMIT=ddf8db6 GIT_DIRTY= make build`** | `HARDWARE_TESTS.md` §V5.46 |
| GBP-VIDEO-004 **source-continuity candidate** | `stream-0006` | `c629445` | `a9b8b969ef462bfe11b833f9dd77d56f7aa4a3387d61124f99b72901c9cb0379` | **PHYSICALLY EXECUTED 2026-09-19 (run 4) — `OBSERVED_CONTIGUOUS`.** 483 008 B. Adds the PRE-REGISTERED structural window (§V5.44) and nothing else: `OGBPIDX1`, `OGBPIDXCAP1 v1`, the analyzer and the stimulus are untouched, and the interrupt path is byte-identical to the physically validated GBP-VIDEO-001 build. Byte-identical across two from-scratch builds; Swiss `build/swiss/12-stream/boot.dol` identical. **Reproduce with `GIT_COMMIT=c629445 GIT_DIRTY= make build`** — which now actually works, see `c629445` | `HARDWARE_TESTS.md` §V5.44 |
| GBP-VIDEO-004 **previous candidate** | `stream-0005` | `10250a4` | `35bbbdd684c2d0048d58661df1c079b613e01dee2d2cced12ba8f2f1e4d87092` | **AUDITED — DECISION A. NOT PHYSICALLY EXECUTED.** 481 664 B; source-layer retention proved unbiased against the real assembler, target stop proved safe (after ACK and RE-ARM), no off-by-one at 2048, no filesystem in the capture path, 9/9 adversarials caught. **Reproduce with `GIT_COMMIT=10250a4 GIT_DIRTY= make build`** | `HARDWARE_TESTS.md` §V5.39, §V5.40 |
| GBP-VIDEO-004 **stimulus** | `indexed-0001` | — | `379df0f7019ef7f1330bd4ad55274bde062a69d03d1c8cc1dc2a01018bdbc543` | 2 460 B. **PHYSICALLY EXECUTED 2026-09-19 — INVALID FOR DECISIVE CLAIM** (FAULT from its first update, 14.9x over the VBlank budget). Historical; never rerun | `HARDWARE_TESTS.md` §V5.41; GBP-HW-157…159 |
| GBP-VIDEO-004 **stimulus** | `indexed-0002` | — | `44651f0ba60141f23cfb6b8b01f5b7a871ef1037412c7dae2ac9d9743c7b7b2f` | 2 876 B. **PHYSICALLY EXECUTED 2026-09-19 — TEARING FIXED (FAULT clear, VMARGIN 24, 0 mixed), but 2:1 CADENCE.** Historical; never rerun | `HARDWARE_TESTS.md` §V5.42; GBP-HW-160…166 |
| GBP-VIDEO-004 **stimulus** | `indexed-0003` | — | `37119bb6ac68398dbd3fa75e6ad5c51c8aeb543277ac8d3b03b57f7a6f0caaca` | 2 880 B canonical. **PHYSICALLY EXECUTED 2026-09-19 — PRODUCER CORRECT: 1:1 cadence, 0 duplicates, 0 mixed, FAULT clear, VMARGIN 24.** The verdict is `OBSERVED_DISCONTINUITY` on one startup-resync gap, not on the producer | `HARDWARE_TESTS.md` §V5.43; GBP-HW-167…174 |
| GBP-VIDEO-004 **stimulus, derived** | `indexed-0003` | — | `9f04916b88308e7045f207136f5fc681e5bab33ac9b22d2e19be12c16b8d9cc2` | 2 880 B; logo from the colour cartridge that booted twice, payload past 0x0C0 byte-identical to the canonical ROM. Never committed. The `indexed-0001` (`abb31e6a…0769`) and `indexed-0002` (`55fe72d5…e559e9`) delivery images are historical and must not be rerun | `HARDWARE_TESTS.md` §V5.42.10 |

The colour run's device log records the commit and the build id, **not** a DOL
hash, so `cc88e4c4…` is the build tree's hash at the declared commit `9d8302d`.
Rebuild with `make build` and compare `build/poc/gbp-video-color-probe/build-info.txt`
before calling any DOL the tested artifact; `build/swiss/11-color/boot.dol` is a
byte copy of it, not a second identity.

**`color-0001` can no longer be built from HEAD**, and that is deliberate: the
POC now declares `color-0002`. A run that has already happened should not be
silently reproducible under its own id. Its DOL hash above is what the record
keeps.

### The GBP-VIDEO-004 candidate, in full — `stream-0003`

```text
Test ID     GBP-VIDEO-004
Build ID    stream-0003     (stream-0001 REJECTED; stream-0002 EXECUTED and
                             ABORTED PRE-SERVICE — neither is ever rebuilt)
commit      03b32a9   (CLEAN, no -dirty suffix)
DOL         build/poc/gbp-video-stream-probe/gbp-video-stream-probe.dol
            471 648 B   sha256 2f8e362e40b7e7dae1b3c2069a2a0fdb6376d22f43e3476cc7b28d7c13d199e3
Swiss       build/swiss/12-stream/boot.dol   (byte-identical copy, hash verified)
toolchain   powerpc-eabi-gcc (devkitPPC) 16.1.0, libogc2 r2442.094b250,
            ghcr.io/extremscorner/libogc2:20260805 — zero warnings
memory      text 363 744 B, data 107 680 B, bss 8 204 404 B
            three framebuffers (two for the stream, one for the console) 1.76 MiB
            MEM1 committed 10.03 MiB of 24.00; 13.96 MiB of arena left
            bss measured 8 204 412 B at the clean build (8 204 404 at the dirty
            one; the 8 B are the shorter commit string, and 40 B above the
            5 308 416 prediction is linker alignment)
fix         §V5.30: the full GBP-VIDEO-002 store set (16384 frame records AND the
            2.81 MiB episode store, the two things stream-0002 omitted); the
            capacities derived from the arrays; six _Static_asserts over the
            actual arrays; required-vs-configured named apart; the abort names
            the failing field; R1 retired (the self-test accounts for itself and
            gbp_vqueue_pristine() asserts it); R8 latched (the ownership module
            audits every transition, main and ISR counted apart)
unchanged   R3 PE FINISH behaviour, post-RE-ARM pump placement, one-tile-row
            slice, RGB5A3 mapping, generation guard, source-disagreement and
            F_SOURCE_DEFERRED policies, mailbox semantics, R5, R7, the
            controlled-stimulus design, and ALL timing instrumentation
software    19 unit binaries / 792 077 checks / 0 failures; 574 host tests OK;
            poc_audit profile `stream` 0 findings; both one-shot ISRs
            byte-identical to the physically validated GBP-VIDEO-001 build;
            Dolphin PASS with COUNTERS balanced=1 sci_clean_at_probe=1 inv_fail=0
            consistent_at_end=1 storage_fault=- and the probe reaching stage_a
            (auxiliary — it says nothing about the device)
PHYSICAL    NOT EXECUTED. No evidence id is allocated to it.
procedure   HARDWARE_TESTS.md §V5.20 (setup) and §V5.21 (pass/inconclusive/fail)
```

**R1 is retired for `stream-0003` only.** The pre-registered correction
`converted == (presented − SELFTEST.xfb) + overrun` remains the right way to read
`stream-0002`'s log and is not withdrawn; `stream-0003` needs no correction and
prints `balanced=1` on its own.

**The hash above belongs to the last commit before this handoff was written**,
because the commit identity is embedded in the image and a hash recorded in this
file can only ever be the previous commit's. Rebuild, read
`build/poc/gbp-video-stream-probe/build-info.txt`, and confirm the commit there
carries no `-dirty` suffix before calling any DOL the candidate.

**`color-0002`'s hash is exact, not inferred.** It was built clean at commit
`39f1980` before the run, with no `-dirty` suffix, and the device log declares the
same commit and build id. That is the strongest identity link any physical run in
this project has, and it is the pattern to repeat: build, read
`build/poc/<poc>/build-info.txt`, confirm the commit matches HEAD and carries no
`-dirty` suffix, and record that hash with the run. Hardware is never tested with
a dirty build (`CLAUDE.md` §18).

## Open questions

- ~~**U-GBP-011** — the VIDEO colour bit order~~ — **CLOSED 2026-09-18** by
  `color-0002`. The window exchanges the two outer 5-bit groups relative to the
  AGB framebuffer, so the references' GX RGB5A3 reading is the displayed colour.
  Two residuals stay open and were never part of that item: bit 15's origin
  (U-GBP-034) and the bytes 0/2 deviations (U-GBP-029).
- **U-GBP-034** — what sets bit 15 of the VIDEO pixel word, and can it appear
  anywhere but the first pixel of a frame? The AGB wrote zero there and the
  delivered word has it set, so the bit is added on the path; what sets it is
  not established. Not blocking.
- **U-GBP-029** — are the byte-0 / byte-2 deviations block data or a read-path
  artifact? `color-0001` is the strongest test so far (a non-uniform picture,
  every deviation confined to bytes 0 and 2, none in 1 or 3) and still not
  decisive.
- **U-GBP-033** — what mechanism produces semantic non-uniformity among the
  eight replicas of the IRQ window. Three physical runs corroborate the
  *policy*; none explains the *cause*.
- ~~Whether the fixed 5000 ms pre-handler wait is sufficient~~ — **ANSWERED**
  2026-09-18: sufficient for this stimulus at this position (GBP-HW-120). The
  claim is that duration and that position, nothing more.
- What the Game Boy Player does with PI masked for **longer** than 5 s at that
  position. Only 5 s was exercised.

## Current blocker / current question

> **Policy A is physically confirmed for one scoped run. The open question is no
> longer pacing — it is what the VIDEO stream carries, with a Game Pak inserted,
> between the CONTROL transform and the first captured frame.**

There is no blocker. Run 6 answered the pacing question against gates frozen
before the cartridge was powered on: **2047 of 2047 interior consumer-reached
scientific source frames handed off in order, 0 interior drops, 0 supersessions,
0 reorder, deferred depth never above 1, p99 0.4946 ms and max 1.1353 ms against
1.0 / 2.5 ms**, and **7 display repeats beside 0 source drops**, within the
`[7, 8]` bracket this run's own source and VI rates require (§V5.50, GBP-HW-202
… GBP-HW-212).

The causal identity is the result: run 5 discarded 17 frames and needed 24
repeated VI intervals, run 6 discarded none and needed 7, and both runs consumed
exactly 2053 VI intervals over spans differing by one microsecond. **24 − 7 = 17.**

**Decision A** — physically confirmed for this scoped run; replication
establishes repeatability, is recommended, and is NOT required to record the
fact (§V5.50.13).

**The new question is the startup one, and it is NOT a GBP-VIDEO-004 result.**
The operator sees a rainbow/checkerboard for 5.1777 s at startup. It is the
synthetic `display_selftest()` pattern — diagnostic GameCube output, identified
from source (GBP-VID-027) — and 5.000 s of that is the `PREHANDLERWAIT`
diagnostic, during which the AGB is running, PI is masked and nothing is
serviced. `vstate-0001` (no wait) captured the animated GAME BOY logotype
0.5014 s after capture start; `vstate-prewait-5000` (same 5 s wait) reported
`STRUCTURED not_observed`. The animation happens inside the wait, which is what
the wait is for. Nothing prevents starting video earlier — the wait is a
configurable diagnostic, default OFF in the module. See §V5.51.

**And the slice position is still PLAUSIBLE BUT UNMEASURED as a property.**
Carried unchanged through every round since it was first measured, because a
later round WILL reuse the wrong number otherwise — which is how the original
error got in. Two runs measure the pump — 27.88 / 33.60 / 41.06 µs and
28.32 / 34.07 / 41.33 µs, yielding to a latched cause on 24.95 % and 25.01 % of
calls — and neither caused an observable transport failure. Neither measures the
MARGIN it consumes. The pre-streaming window it rests on is unchanged at median
**42.8** µs with **p25 = 1.9** µs. Run 6 adds the deferral bookkeeping on top of
that and showed no transport failure — `timeouts 0, busy 0, errors 0, 224 547
unmasks = deliveries = acks = rearms` — but a run without a failure still does
not measure the margin.

## Next safe action

**A startup/UX experiment with its own build ID, its own question, and no reuse
of a GBP-VIDEO-004 artifact.** The pacing milestone is closed; do not reopen it
to chase the checkerboard.

```text
question   with a Game Pak inserted, what does the VIDEO stream carry from the
           CONTROL transform onward -- and when does the cartridge's first
           rendered frame reach it?
why now    no existing run answers it. vstate-0001 had NO cartridge; every
           stream run waits 5 s and starts capturing after the boot is over.
shape      start the VIDEO service at, or close to, the CONTROL transform, the
           way vstate-0001 already did, WITH the cartridge present
must not   reuse stream-0008's identity, change Policy A, change the source
           path, change qualification, or perturb the pacing evidence
```

**Before any of that, three read-only items are already written down and cost
nothing to honour:**

```text
1  tools/vdisp.py `usable()` does not test order_violations. A trace with a
   reordering would still be called usable for a disposition claim. It did not
   affect run 6 (0 by counter AND by reconstruction). Fixing it is a rule
   ADDITION, so it needs its own authorisation -- GBP-VID-026.
2  src/gbp/gbp_vqueue.h still declares gbp_vqueue_note_repeat() and comments
   that `repeats = xfb_skipped`. Policy A makes that coupling FALSE
   (repeats 0, xfb_skipped 129). Accurate history, misleading as an invariant.
3  `xfb_skipped` must never be compared across stream-0007 and stream-0008 as
   if it meant one thing: 17 terminal drops there, 129 resolved defer attempts
   here (GBP-HW-207).
```

**If a Policy-A replication is run instead**, it is a REPEATABILITY claim, not a
re-decision. Same build `stream-0008` at `5126a19`, same cartridge, the same
frozen gates in §V5.49.15, and the same non-negotiable analysis order:
identities, `tools/vindex.py`, `OBSERVED_CONTIGUOUS` or stop, container
integrity, the exact `frame_index` join, disposition, defer/retry, latency,
queue depth, then the estimated display cadence. **Never pacing first and source
later.** Display repeats are compared against a range derived from THAT run's own
timing — never a fixed 7.

**BEFORE the run, protect the raw record.** The SD workflow names every run
identically and run 3 overwrote run 1's log in `logs/`; only the
`captures/local/` archive saved it. Copy both files off the card under a
run-distinguishing name before re-populating the card.

**Carried to the next FUNCTIONAL checkpoint** (untouched for four rounds — the
stability is deliberate, it is what made the three-run comparison causal):

```text
F3  `make <x>-audit` has no source prerequisite and can audit stale objects.
    The stream and colour audits also COMPARE against the video POC's ISR dump,
    so `make video-audit` has to run first or the comparison reads a stale or
    absent file and reports DIFFERENT for no reason.
F8  `tools/poc_audit.py` walks the relocations of FUNCTIONS (objdump -dr of the
    text). A forbidden symbol reached through a DATA initialiser -- a function
    pointer in a table, a callback field -- produces a .data relocation and is
    invisible to both the deny-lists and the allowlists. Found in §V5.46 while
    writing a mutation that accidentally took the address of `fopen` instead of
    calling it; the CALL form is caught. Narrow, but real, and not fixed here:
    changing the audit tool needs its own validation round.
F5  cfg.min_valid_observation_s = 30 is armed as a success condition. Under
    OGBPIDX1 it is UNREACHABLE (no baseline can form, valid_s stays 0), but the
    indexed experiment should still have exactly one success condition.
```

**Historical identities, kept so no one picks up the wrong artifact:**
`stream-0001` — **REJECTED before hardware — DO NOT RUN**, sha256
`0dc2c50101b5cc6c3906e89f845b89d4d218ccd7ee05ff04764de68b1169d275`.
`stream-0002` — PHYSICALLY EXECUTED, **ABORTED PRE-SERVICE**
(`store_or_bounds_invalid`, `gbp_vstate_probe.c:790`, field `episode_raw_null`);
**not a streaming failure**, streaming was never reached, and its two traps are
in §V5.29 (`static_bytes=6922240` was a capacity constant, not a footprint; the
build had configured `1 798 144`).
`stream-0003` — PHYSICALLY EXECUTED, the first real cartridge video on screen,
sha256 `2f8e362e40b7e7dae1b3c2069a2a0fdb6376d22f43e3476cc7b28d7c13d199e3`.
`stream-0004` — PHYSICALLY EXECUTED, P1 and P2 confirmed fixed, sha256
`56f2687377f261a865ec05efb8d71ec71c79b664389fec8b31dc038545977c43`.
`indexed-0001` — PHYSICALLY EXECUTED, **FAULTED**, 6:1 captures per ID,
canonical `379df0f7…bdbc543`, delivery `abb31e6a…0769`.
`indexed-0002` — PHYSICALLY EXECUTED, **tearing fixed, 2:1 cadence**, canonical
`44651f0b…7b7b2f`, delivery `55fe72d5…e559e9`.
**None of these is ever rebuilt, re-labelled or rerun.**

**The milestones, and their exact scope.** PHYSICAL REAL-CARTRIDGE VIDEO OUTPUT
ACHIEVED, and basic sustained streaming operationally reached — both unchanged.

**NEW, and authorised by the frozen analyzer, not by preference: CONTROLLED
STEADY-STATE SOURCE-FRAME CONTINUITY OBSERVED ON PHYSICAL GBP.** It was made
conditional on `OBSERVED_ID_CONTIGUOUS`, and run 4 returned exactly that
(GBP-HW-188/189). Its scope is the sentence and nothing wider:

> Within the prospectively qualified OGBPIDX1 scientific window of the
> `stream-0006` physical run, the preserved source-frame IDs were contiguous and
> ordered across all analyzer-decisive transitions; all 2 048 retained records
> contained the expected 40 block indices and one consistent FRAME_ID.

**It does NOT prove** zero loss before the qualified window, zero loss after the
last retained record, zero loss for arbitrary durations, full 240x160 pixel
fidelity, that every source frame reached the XFB, zero downstream repeats,
universal 59.7271 Hz operation, or identical behaviour for other cartridges and
software. OGBPIDX1 witnesses STRIP-L, local row 0, x = 1..54 — 4 320 B per frame.
The phrases ZERO FRAME LOSS PROVEN, PERFECT 60 FPS, LOSSLESS DISPLAY PIPELINE and
PIXEL-PERFECT FULL FRAME remain forbidden.

**After the fourth run**, the next unresolved GBP-VIDEO-004
objectives in roadmap order are the **downstream consumer/display loss policy**
(this run still shows 2 043 converted, 2 026 presented, 17 repeats — a *later*
pipeline stage that the source witness says nothing about) and **frame pacing**.
Neither is started here.

Do **not** implement scaling, aspect correction, filtering, audio playback, A/V
sync, KEYPAD or any network path; do not edit `OGBPCOL1` v1, `OGBPIDX1`,
`OGBPIDXCAP1` v1, `tools/vcolor.py`, `tools/vcolor2.py`, `tools/vindex.py`, the
§V4 contract or any fixture; do not re-label or rebuild `stream-0001` …
`stream-0005`, `indexed-0001` … `indexed-0003`.

## Do not rediscover

Each of these has sufficient evidence. Re-deriving them wastes a session; if you
believe one is wrong, argue against the source, do not re-run the discovery.

| conclusion | source |
| --- | --- |
| The R3 source-disagreement policy (majority authoritative inside `SRC_MASK`, quarantine, fatal classes) | `HARDWARE_TESTS.md` §R3; GBP-HW-096…115 |
| OGBPSEQ1 v5's diagnostic-ownership fix, and that v4 carries producer defect GBP-HW-104 | `HARDWARE_TESTS.md` §R4; GBP-HW-104/105 |
| OGBPCOL1 v1 `cert_rec` is 40 bytes, frozen | `src/gbp/gbp_vcoldump.h`; commit `e10423c` |
| The colour capture must not do full-frame work between ACK and RE-ARM | `HARDWARE_TESTS.md` §V3.23 |
| Four raw-ring slots are required for A/B/C to survive certification | `HARDWARE_TESTS.md` §V3.24 |
| `gbafix` from devkitPro supplies the Nintendo logo; the canonical stimulus does not | `HARDWARE_TESTS.md` §V3.7 |
| EZ-Flash Omega DE NOR / Mode B boots the derived image on GBA and on the GBP | delivery route above |
| A 5 s masked pause between stage A and the handler install is tolerated | GBP-HW-116…118 |
| The operator cannot see the stimulus during the pre-handler interval | `HARDWARE_TESTS.md` §V3.27 |
| The colour capture opens only after the fixed wait, and holds no state before it | `HARDWARE_TESTS.md` §V3.28 |
| `frames_refused[MAJORITY_EXTRA]` reads 0 in real runs; `frames_quarantined` is the real counter | `HARDWARE_TESTS.md` §V3.24 |
| Bytes 0 and 2 of a pixel word are read by neither reference decoder, vary physically, and are NOT the picture | GBP-VID-003; GBP-HW-058/070/123/126 |
| `color-0001` failed its own pre-registered gate and stays INCONCLUSIVE; the H1 projection is a diagnostic, not a result | GBP-HW-122/124; `HARDWARE_TESTS.md` §V4.1 |
| The runtime's `sig[40]` consumes bytes 1 and 3 only — the same bytes the §V4 gate compares | `src/gbp/gbp_vsig.c:15`; §V4.1 |
| **The VIDEO window exchanges the two outer 5-bit colour groups relative to the AGB framebuffer** — measured, twice, with a known-colour stimulus | GBP-HW-131; `HARDWARE_TESTS.md` §V4.10 |
| The references' GX RGB5A3 reading is therefore the displayed colour, and Dolphin's mGBA-derived order is the divergent model | GBP-HW-131; GBP-VID-007 |
| Both physical colour runs deliver the identical picture in the consumed projection, 38 400/38 400 | GBP-HW-132 |
| A GBP word needs **no channel arithmetic** to become a `GX_TF_RGB5A3` texel — `texel = word \| 0x8000`; the device already swapped the groups | GBP-HW-131; §V5.10 |
| The AGB (~59.727 Hz) and the GameCube VI (~59.94 Hz) are not synchronised: ≈ 26 repeated display frames per 120 s are arithmetic, not loss | GBP-PHY-003; GBP-HW-078; §V5.6 |
| `poc/gbp-video-stream-probe` is the ONLY POC that initialises GX, and `main.o` is the only object permitted to name `GX_`; every other POC uses `VIDEO_Init` + `CON_Init` on a single XFB | `poc_audit` profile `stream`; §V5.4 |
| The frame assembler already classifies COMPLETE_40 / SHORT / LONG / PREDICATE_ANOMALY / RESYNC — streaming needs a *display* policy, not a new classification | `src/gbp/gbp_vstate.h`; §V5.9 |
| The ROM-delivery route is route 1, EZ-Flash Omega DE NOR / Mode B, and it sets `CONTROL orig=92` | §V3.7 resolution; GBP-HW-127 |
| A GBP word becomes a `GX_TF_RGB5A3` texel with `\| 0x8000` and no channel arithmetic; the only work is the 4×4 tile permutation | GBP-HW-131; `src/gbp/gbp_vpix.c` |
| `GX_DrawDone()` blocks and `GX_SetDrawDone()` + `GX_SetDrawDoneCallback()` do not — that is why the texture ownership uses the callback form | `ogc/gx.h` in `libogc2:20260805` |
| One block is exactly one 4×4 tile row: 0xF00 raw bytes → 0x780 tiled bytes, the same as the Disc's own converter | `VIDEO_PATH.md` §2.3; `gbp_vpix.h` |
| The pump runs with IRQ 26 ALREADY MASKED, so the GBP ISR cannot preempt a conversion; producer and consumer are one thread and need no barrier | `gbp_irq_service.c` step 7; §V5.26.1 |
| `wait_next()` is a busy poll on INTSR, so a cause arriving during a slice LATCHES and is found late rather than lost | `gbp_vstate_probe.c` `wait_next`; §V5.26.1 |
| The real RE-ARM→next-cause idle window is median 42.8 µs, p25 1.9 µs — NOT the 164 µs mean cycle period | `vstate-0004` cycle records; §V5.26.3 |
| A GBP word needs no byte-order conversion to be a GX_TF_RGB5A3 texel on PowerPC; verified against the physical `color-0002` frame | §V5.26.7 |
| A DrawDone token certifies only the commands queued BEFORE it, so a callback may free exactly the one buffer it names — never "every submitted one" | §V5.26.2, §V5.27.1 |
| `VIDEO_GetCurrentFramebuffer()` and `VIDEO_SetNextFramebuffer()` are non-blocking, so a double-XFB policy needs no retrace callback and no VSync wait | `ogc/video.h`; §V5.27.3 |
| A state machine that lives in a POC's `main.c` has no behavioural test, and source-string assertions are audit guards rather than coverage | §V5.26.8, §V5.27.1 |

## Do not assume

- **That 5000 ms guarantees the bars are already on screen.** `color-0001`
  showed 5000 ms was *sufficient in that setup* (GBP-HW-120). That is one run on
  one unit with one cartridge, not a boot-time guarantee.
- **That a rebuilt DOL equals the historical physical DOL.** It does not; the
  commit is embedded. Compare hashes.
- **That mGBA closes U-GBP-011.** mGBA knows the GBA's native framebuffer
  format; U-GBP-011 asks what the *Game Boy Player* presents to the GameCube.
  Only the physical GBP-VIDEO-003 run can answer it.
- **That the "pending source" model is FACT.** It is not; U-GBP-033 is open.
- **That the absence of majority-extra in one run proves it cannot happen.**
- **That a longer masked wait is safe** because 5 s was.
- **That `color-0001` became confirmatory once `color-0002` agreed with it.** It
  did not. It failed its own pre-registered gate and stays INCONCLUSIVE
  permanently; `tools/vcolor2.py` still reports it as RETROSPECTIVE.
- **That the closure of U-GBP-011 says anything about bits 1–4 inside a 5-bit
  group.** The stimulus pins bits 0, 5 and 10 individually and each group as a
  set; a permutation fixing those three and rearranging only bits 1–4 is not
  excluded. §V3.19 holds the pattern that would close it, and it is not
  scheduled.
- **That §V5 has been validated by anything.** It was implemented on 2026-09-18
  and the candidate was then REJECTED by its own pre-hardware audit. Nothing has
  run, and its estimates — conversion cost above all — are still explicitly *not*
  budgeted as properties (§V5.22).
- **That a commercial cartridge has been chosen.** §V5.18 records the properties
  one must have and deliberately names no title; the operator owns that choice.
- **That `stream-0001` has been validated on hardware.** It has not run. It is
  implemented and host-validated, no evidence id is allocated to it, and its
  30 s capture duration is still a DESIGN DECISION.
- **That the slice fits.** The argument for one tile row per service cycle rested
  on a misread number. The measured RE-ARM→next-cause idle window is median
  42.8 µs with **p25 = 1.9 µs**; 34 % of cycles have no usable slack at all
  (§V5.26.3). Nothing is lost, because the cause latches, but the placement is
  unmeasured.
- **That `stream-0001` is ready to run.** The pre-hardware audit rejected it:
  one BLOCKER and three HIGH findings (§V5.26). `stream-0002` supersedes it and
  `stream-0001` is never rebuilt or re-labelled.
- **That Dolphin has no Game Boy Player.** It does: 2606a ships
  `HSP::CHSPDevice_GBPlayer` backed by libmgba, reachable from a homebrew DOL
  with `Dolphin.Core.HSPDevice=2` and `Dolphin.GBA.GBPlayerRom`, with no BIOS and
  no Start-up Disc (§V5.31.5). The old claim was about the launch configuration,
  not the emulator.
- **That the emulated GBP can settle anything physical.** It cannot. Its
  power-on CONTROL is `0x02` where hardware presents `0x90`, and its VIDEO read
  duplicates bytes 0↔1 and 2↔3 where hardware does not — so it can never inform
  U-GBP-029, R3, the RE-ARM timing, bit 15 or frame loss (§V5.31.7, §V5.31.8).
- **That the P2 fix means every complete frame will now be published.** It does
  not. `F_ANOMALY`, `F_RESYNC`, incomplete intervals and a lost ring slot still
  exclude frames; only the aliased `EPISODE_STABLE` exclusion is gone. No
  publication count and no frame rate is pre-registered for the next run.
- **That P2 is physically resolved.** It is fixed in software and proved in
  software. Nothing physical has run since.
- **That moving a persisted flag bit is free.** The frame flag word is written
  verbatim into every OGBPSEQ1 sidecar at offset 0x1A. `F_MAJORITY_EXTRA` could
  move because it has never been set in any file; `F_EPISODE_STABLE` could not,
  because validated fixtures carry it (§V5.36.2).
- **That `gbp_vsig_block()` can identify a frame.** It cannot. It is an additive
  checksum; the indexed stimulus's complement-pair strips make the frame ID
  contribute *nothing* to it, and it misses a strip substituted from another
  frame ID or another block index entirely (§V5.32.7, §V5.32.8). It is not
  "lossless" and must never be described as one.
- **That the indexed stimulus exists.** Its CONTRACT is frozen (`OGBPIDX1`,
  §V5.33); **no ROM has been written**. Until one is built and run, source-frame
  loss cannot be measured against ground truth by anything.
- **That the canonical witness proves the frame arrived pixel-perfect.** It does
  not. It decides frame-ID sequence integrity, block composition integrity and
  block position integrity — three separate questions. Pixel fidelity outside
  the strip is a fourth, and this experiment does not answer it.
- **That "zero observed gaps" would mean zero source-frame loss.** It would mean
  no observed transition had Δ ≠ 1, between the first and last intact observed
  ID. Frames before the first and after the last stored frame are
  **unobservable** (§V5.32.2).
- **That `stream-0003` needs the R1 correction.** It does not. `balanced=1` with
  no subtraction; `presented − SELFTEST.xfb` belongs to `stream-0002`'s log only.
- **That `stream-0002` is proved because its predecessor's blocker is fixed.**
  The fix is host-validated, Dolphin executes the display path end to end
  including the draw-done callback, and §V5.28 re-audited it and cleared the
  ownership machine by exhaustive enumeration. None of that says anything about
  the device.
- **That `counters DO NOT BALANCE` on a `stream-0002` run means the run failed.**
  It does not. R1 is a **reporting** defect: it makes that line appear on every
  run, off by exactly one, before the capture even opens (§V5.28.10). The
  pre-registered identity is `converted == (presented − SELFTEST.xfb) + overrun`,
  and the raw counters it is computed from remain authoritative.
- **That the audit's DECISION A means nothing was found.** Eight findings were
  recorded (§V5.28.13). A means every *safety* property held: nothing in the
  service path, the ownership machine or the teardown was defective. R1 and R8
  are reporting defects and are fixed in `stream-0003`, after the first run.
- **That `OWNER invariants HOLD` means they held for the whole run.** It means
  they held at the final instant; `gbp_vpresent_consistent()` is never evaluated
  during the capture (R8, §V5.28.16).
- **That the draw-done callback cannot disturb the service path.** `IRQ_PI_PEFINISH`
  is unmasked and is never masked by this program, so it can preempt the ACK →
  RE-ARM window (R3). It is small and bounded, and it is unmeasured.
- **That the slice position is settled.** It is not. The precheck removes the
  *already latched* case; a cause arriving mid-slice is counted, not prevented,
  and the slice's own cost has never been measured on hardware (§V5.27.4).
- **That bytes 0 and 2 are don't-care in general.** §V4 places them outside the
  dependent variable of *this experiment* only. U-GBP-029 is open, they are
  preserved in full, and every run reports the full-raw comparison.

## Raw evidence availability after a clone

Every physical run of this project keeps a **versioned replay fixture** under
`captures/fixtures/`, with the raw device log identified by SHA-256 in the
fixture header. The raw logs themselves live in `logs/` (never versioned) and
`captures/local/` (ignored) — the policy is in `captures/README.md`.

```text
PHYSICAL REPLAY EVIDENCE:  RECOVERABLE FROM A CLONE
RAW TEXT LOG:              NOT STORED IN GIT — IDENTITY PRESERVED BY SHA-256
```

Those are two different things and the distinction matters to anyone verifying a
claim. A fresh clone **does** get, for every physical run: the `.gbpreplay`
replay script, the sidecar binary where the run produced one, and a metadata
header tying both to a DOL hash, a log hash, a size and a commit — enough to
replay the run and recompute the evidence.

A clone **does not** get the original device text log. Those live in `logs/`
(never versioned) and `captures/local/` (ignored), and only their SHA-256 and
size are recorded. A hash does not permit replay; it permits *verification* of a
copy the operator supplies. So a claim traced to a fixture is re-checkable from
a clone alone; a claim traced only to a raw log line is not, until someone
provides the log.

## Swiss operator layout

`make swiss` exports every launchable DOL to `build/swiss/NN-short/boot.dol`
with an `INDEX.txt`, numbered by the versioned manifest
[`tools/swiss-layout.tsv`](../tools/swiss-layout.tsv). Numbers are stable and
never reused; `01-69` are canonical POCs and `80-89` physical diagnostics.

**An exported `boot.dol` gains no physical status by being exported.** It is a
byte-for-byte copy and the authority remains `build/poc/<out_dir>/<dol>`.
Physical status belongs to the exact SHA-256 and commit recorded in
`EVIDENCE.md` / `HARDWARE_TESTS.md` — and `build/swiss/80-prewait/boot.dol` rebuilt at any
commit other than `500429a` is **not** the DOL that ran on hardware.

## Handoff update policy

Update this file when any of these happens:

- a physical run is ingested;
- an evidence status changes;
- an unknown opens or closes;
- a frozen contract is introduced or versioned;
- the active experiment changes;
- the current blocker changes;
- the next safe action changes.

Do **not** update it for a typo, a refactor with no scientific effect, or a
cosmetic build change — unless that change alters an artifact identity that this
file records.

## Canonical resume prompt

Copy this verbatim into any agent to take the project over with no chat history.

```text
You are taking over development/research of the Open-GBP repository.

Do NOT modify anything yet.

First:

1. Read AGENTS.md completely.
2. Read docs/HANDOFF.md completely.
3. Follow the mandatory read order defined there.
4. Verify the repository HEAD and working-tree status.
5. Compare HEAD against the STATE BASELINE COMMIT recorded in docs/HANDOFF.md.
6. If HEAD contains commits newer than that baseline, inspect and reconcile them
   before trusting the "Current scientific state" section.
7. Reconstruct the current scientific state only from repository evidence.

Then report, without changing files:

- current HEAD and whether the tree is clean;
- whether the handoff is current or stale;
- physically established facts;
- corroborated findings;
- open hypotheses and unknowns;
- frozen binary/data-format contracts;
- the exact artifacts that were physically executed, with their hashes;
- the latest physical evidence ingested;
- the current blocker/question;
- the next safe action;
- any contradiction you found between docs/HANDOFF.md and the authoritative
  sources.

Important:

- real physical hardware is the final authority;
- emulator evidence (Dolphin, mGBA) is auxiliary unless the documentation
  explicitly says otherwise;
- do not convert CORROBORATED or HYPOTHESIS into FACT;
- do not claim a rebuilt binary was physically tested merely because the same
  source or variant was: this project embeds the commit in its images, so
  compare the SHA-256 against the recorded one;
- do not change frozen formats silently;
- do not create evidence IDs or physical-validation claims without source
  material;
- do not perform any implementation until you have reported the reconstructed
  state and the operator confirms continuation.

Stop after the takeover report.
```
