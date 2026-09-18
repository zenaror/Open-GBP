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
STATE BASELINE COMMIT   ef328b4dd58aa79683f3207c99c4ccaae1bea549
```

**What that means, precisely:** it is the **last commit whose scientific and
operational state was audited before this handoff snapshot was written**. It is
*not* "the expected current HEAD", and it is deliberately not this file's own
commit — a document cannot contain the hash of the commit that adds it. Expect
HEAD to be at least one commit ahead: the one carrying this text.

```text
LAST PHYSICAL EVIDENCE INGESTED
  GBP-VIDEO-003 / color-0002, executed 2026-09-18 — THE CONFIRMATORY RUN
  GBP-HW-127 … GBP-HW-133
  STANDING: CONFIRMATORY
  VERDICT: CONFIRMED_EXACT_H1_OUTER_GROUP_SWAP
  U-GBP-011 is CLOSED. The colour order is FACT, not CORROBORATED.

  Previous: color-0001 (GBP-HW-120…126), INCONCLUSIVE under its own frozen
  contract, permanently, and never re-judged; PRE-HANDLER MASKED WAIT 5000 ms
  (GBP-HW-116…119).
```

### Staleness check — run this before trusting anything below

This file is **not automatically true because it exists**. Before relying on the
"current state" section:

```sh
git rev-parse HEAD
git status --short
git log --oneline ee1d46b2d86c3287a88fff5526df206184791d9f..HEAD
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
| **GBP-VIDEO-004** (sustained streaming) | **DESIGN / PRE-REGISTERED 2026-09-18 — NOT IMPLEMENTED, NOT RUN.** Active experiment | `HARDWARE_TESTS.md` §V5 |
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

The colour run's device log records the commit and the build id, **not** a DOL
hash, so `cc88e4c4…` is the build tree's hash at the declared commit `9d8302d`.
Rebuild with `make build` and compare `build/poc/gbp-video-color-probe/build-info.txt`
before calling any DOL the tested artifact; `build/swiss/11-color/boot.dol` is a
byte copy of it, not a second identity.

**`color-0001` can no longer be built from HEAD**, and that is deliberate: the
POC now declares `color-0002`. A run that has already happened should not be
silently reproducible under its own id. Its DOL hash above is what the record
keeps.

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

> **Implement the smallest GBP-VIDEO-004 POC defined by the pre-registered design
> in `HARDWARE_TESTS.md` §V5.**

The design is written and nothing about it has been implemented or run. §V5 fixes
the parts that are decisions rather than code — the producer/consumer boundary,
the buffering shape, the frame-loss policy, the output scope, the pass criterion —
so that implementation is engineering rather than improvisation.

**Three items in §V5 are explicitly DESIGN DECISION REQUIRED** and must be settled
before or during the first implementation, each with a reason recorded:

1. **Run duration** (§V5.5) — justified against a real interval, the way
   GBP-VIDEO-002's 120 s was justified against the Disc's own detector window. Not
   a number that feels long.
2. **Converted-queue depth** (§V5.8) — deferred until the first measurement of
   conversion cost, because this repository has measured none.
3. **How the text report and the GX pipeline share the framebuffer** (§V5.15) —
   every existing probe calls `CON_Init` on the XFB, and GX wants it. **This may
   not be solved by moving reporting into the service path.**

**The colour question is finished and the delivery dependency is closed.**
GBP-VIDEO-003 is COMPLETE for its controlled colour objective, U-GBP-011 is
CLOSED, and §V3.7's ROM-delivery dependency is RESOLVED (route 1, EZ-Flash Omega
DE NOR / Mode B).

## Next safe action

Implement the first streaming POC exactly as §V5.20 specifies, and no more than
that:

```text
Test ID    GBP-VIDEO-004        Build ID  stream-0001   (not yet in any Makefile)
POC        poc/gbp-video-stream-probe/                  (does not exist yet)
new, pure, host-tested:  src/gbp/gbp_vpix.{h,c}    raster -> RGB5A3 tile
                         src/gbp/gbp_vqueue.{h,c}  bounded frame queue + counters
reused byte for byte:    gbp_vstate_probe, gbp_vstate, gbp_vsig, gbp_avblock,
                         gbp_irq_service, gbp_initirqa, the R3 policy, the teardown
```

Build the two pure modules and their host tests **first**, against synthetic
frames and against the physical `color-0002` fixture — which already carries eight
known colours in known positions and is therefore a real conversion oracle. Only
then add the POC and the GX path.

Hard rules carried from §V5, none of them negotiable:

- **Nothing new enters the service path.** No GX, no texture upload, no
  filesystem, no networking, no PAD, no full-frame work, no wait of any kind
  between the ACK and the RE-ARM. The handoff to the consumer is an integer
  (§V5.7), exactly as §V3.23 forced for the colour capture.
- **Never synthesise pixels.** An incomplete frame is recorded and not displayed;
  the previous frame is held and the hold is counted (§V5.9).
- **Never block the producer** to rescue a picture (§V5.14).
- A quarantined frame (`F_MAJORITY_EXTRA`) may never reach the screen, for the
  same reason it may never become colour evidence.
- Do **not** implement scaling, aspect correction, audio playback, A/V sync,
  KEYPAD or any network path. They are Phases 6, 9 and 11.
- Do **not** edit `OGBPCOL1` v1, `tools/vcolor.py`, `tools/vcolor2.py`, the §V4
  contract, or any existing fixture.

No hardware run is requested until the POC exists, its host tests pass, the tree
is clean and the build carries no `-dirty` suffix.

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
| No POC in this repository has ever initialised GX; every one uses `VIDEO_Init` + `CON_Init` on a single XFB | verified across `poc/` and `src/`; §V5.4 |
| The frame assembler already classifies COMPLETE_40 / SHORT / LONG / PREDICATE_ANOMALY / RESYNC — streaming needs a *display* policy, not a new classification | `src/gbp/gbp_vstate.h`; §V5.9 |
| The ROM-delivery route is route 1, EZ-Flash Omega DE NOR / Mode B, and it sets `CONTROL orig=92` | §V3.7 resolution; GBP-HW-127 |

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
- **That §V5 has been validated by anything.** It is a design. Not one line of it
  is implemented, nothing has run, and its estimates — conversion cost above all —
  are explicitly *not* budgeted as properties (§V5.22).
- **That a commercial cartridge has been chosen.** §V5.18 records the properties
  one must have and deliberately names no title; the operator owns that choice.
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
