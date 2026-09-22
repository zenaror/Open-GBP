# Open-GBP Project Handoff

## Purpose

This document is a **navigation and state index**. It is not evidence, and it
does not replace `docs/research/EVIDENCE.md`, `docs/research/HARDWARE_TESTS.md`
or any design document. Every conclusion below points at the source that owns
it; when this file and a source disagree, **the source wins** and the divergence
gets recorded.

Read `AGENTS.md` first.

## Current role assignment (ephemeral — the definition is in `AGENTS.md`)

| Responsibility | Currently held by | Changes |
|---|---|---|
| OPERATOR / HARDWARE OPERATOR | the human project/hardware operator (currently Rafael) | independently of the others |
| ORCHESTRATOR / VALIDATOR / PLANNER | an external validation/planning agent | independently of the others |
| EXECUTOR / CODING AGENT | the coding/research agent (currently Claude Fable 5.1) | independently of the others |

Names and products here are a snapshot. Swapping any seat — tool for tool,
human for AI or back — changes nothing about the scientific process, the
evidence vocabulary or the checkpoint discipline, all of which are defined in
`AGENTS.md` and `docs/RESEARCH_METHOD.md`.

## Operational coordination — GitHub (since 2026-09-20)

```text
canonical    https://github.com/zenaror/Open-GBP              local remote origin
archive      https://git.home.zsrv.com.br/zenaror/Open-GBP    local remote gitea-archive:
             non-canonical, retained, push disabled (no_push)
Issues       https://github.com/zenaror/Open-GBP/issues       the operational unit; comments = trail
Milestones   Phase 4 ... Phase 13 (numbers 1-10), mirroring docs/ROADMAP.md; no due dates
Labels       stage:* (exactly one on an active Issue) · area:* · type:* · needs:hardware
Project      "Open-GBP Development" https://github.com/users/zenaror/projects/2 (number 2,
             public, linked; Issue #4) -- views only: Board · Backlog / Ready · Hardware ·
             Validation · Roadmap; fields Area · Work Type · Hardware beside built-in Status
             (Todo / In Progress / Done); no evidence-status field, by design
Templates    .github/ISSUE_TEMPLATE/checkpoint.md · hardware-run.md · PULL_REQUEST_TEMPLATE.md
```

The Orchestrator owns the backlog and moves the `stage:*` labels; the Executor
consumes bounded Issues and posts its report on them; the Operator's hardware
declarations quoted in an Issue remain OPERATOR OBSERVATION. **No Issue, label,
milestone or Project field promotes evidence status**: this file,
`docs/research/EVIDENCE.md`, `docs/research/HARDWARE_TESTS.md` and the fixtures
keep the scientific state. Issues #1 and #2 are the completed history (run 11
and its ingestion, under milestone "Phase 4 — Video"); Issue #3 is the
migration itself.

## State baseline

```text
STATE BASELINE COMMIT   9683ea11689ae3b54149c469fc273778385dd62f
```

**What that means, precisely:** it is the **last commit whose scientific and
operational state was audited before this handoff snapshot was written**. It is
*not* "the expected current HEAD", and it is deliberately not this file's own
commit — a document cannot contain the hash of the commit that adds it. Expect
HEAD to be at least one commit ahead: the one carrying this text.

```text
LAST PHYSICAL EVIDENCE INGESTED
  GBP-INPUT-001 / stream-0014 @ 0ff8355 + the Enhanced Control Checker, executed 2026-09-21 -- RUN 14 (walk A)
  and RUN 15 (walk B), the first physical KEYPAD writes
  GBP-HW-261 ... GBP-HW-265; GBP-KEY-008 (the ENVINPUT clip), GBP-KEY-009 (the one-log-line finding)
  STANDING: EXECUTED · QUESTION M = PASS · QUESTION O = AS-ASSIGNED, both runs (HARDWARE_TESTS §V7.2);
  U-GBP-010 CLOSED; the routing CORROBORATED, not FACT

  Machine side (the only machine facts the write-only window allows): INPUT attempts = completed =
  7 892 (RUN 14) / 7 895 (RUN 15), failed 0, retry 0, first 1, change 42 = 2 x 21 presses in each,
  refresh 7 849 / 7 852, last_word 0000; INPUTT write 30/30/38 ticks, step 98/169/1046 (observational);
  transport / startup / Policy A clean (first hand-off 165.337728 / 165.338494 ms, +0.186 ms on RUN 13,
  recorded, no tolerance); both logs lines=686 dropped=0 TRUNCATED=1 = the ENVINPUT record clipped at
  248 of 266 characters (lost `ot_FACT selftest=1`, both recoverable; GBP-KEY-008).
  Human side, literal, relayed by the Orchestrator: tally vectors 1 2 · · · · 6 5 3 4 and
  1 2 3 4 5 6 · · · · = the walks' arithmetic expectation (blank = never incremented; the frozen
  gate's "reads 0" vs the instrument's blank recorded, not smoothed over). No per-press live record;
  photographs useless (no upscaler in the chain; no claim about the chain).
  Topology DECLARED after the runs (Issue #25): same GameCube; BBA connected without a network cable;
  video chain unchanged; a GENERIC third-party controller (the official pad owned, NOT used) -- so the
  L / R result is a third-party pad's digital click (the policy reads no analogue trigger); the same
  Game Boy Player by the Operator's DECLARED HARDWARE INVENTORY (exactly one GameCube, exactly one
  GBP -- a declaration, not an inference). Verdicts and gates unchanged.
  Independent machine-decodable record (FACT as data): the checker's tally screen is in every one
  of the 16 preserved OGBPFULL1 frames; the digits resolve pixel-exactly under the unmodified
  vfull.py parser; final state from s3 (+18.9 s after CONTROL), identical across s3..s7; the
  partials show the walk in its declared order; both final vectors equal the Operator's digit for
  digit (stated, never merged). vindex / vfull INCONCLUSIVE by construction (not OGBPCOORD1):
  recorded, not judged; sidecar CRCs valid; corrected vvi 2372/2372 and 2373/2373.
  Verdicts read from §V7.1.9 as written: M = PASS (every pressed button at its own counter, all
  ten across the two runs), O = AS-ASSIGNED (L = 1, R = 2). U-GBP-010 CLOSED on its own condition,
  descriptor kept. The routing stays CORROBORATED: the chain's fourth link -- the Operator pressed
  L exactly once -- is in no machine record (42 key changes, not which buttons); one log line, the
  word at each key change, would close it (GBP-KEY-009, recorded, NOT implemented).
  Ten raw files archived first under the reserved run14 / run15 names (RUN 15 arrived in
  logs/run15/, so nothing was overwritten); fixtures versioned (the tally frames byte-identical);
  tests/host/test_run14.py. Hardware Issue #21 CLOSED after validation; #24 / #25 validated;
  the consolidated pages promoted under Issue #26 (docs/protocol/INPUT.md; the keypad rows of
  REGISTERS.md, GBS-DOL.md, ARCHITECTURE.md; INITIALIZATION.md §15) -- the L/R order C, not FACT.
  RUN 16 NOT RUN. No rerun pre-registered.
  CANDIDATE stream-0015 @ da06500 (Issue #27; sha256 dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49; 514 880 B): the per-change
  KEY record (GBP-KEY-009 implemented -- FACT reachable, not actual) and the ENVINPUT repair
  (GBP-KEY-008) with a general payload guard; EXECUTED 2026-09-21 (RUN 17 / RUN 18 / RUN 16, Hardware Issue #32),
  staged with stream-0014 preserved to build/archive/ first.
  RUN 17 (walk A, generic pad) / RUN 18 (walk B, ORIGINAL pad) EXECUTED 2026-09-21 (Hardware Issue #32) and
  INGESTED (Issue #33, HARDWARE_TESTS §V7.4) against the gates pre-registered in §V7.3 (Issue #28): QUESTION J =
  FACT for all ten KEYPAD word bits -- bits 8 (L) and 9 (R) twice, on two independent controllers -- the runtime's
  KEY record joined to the checker's decoded counters by machine at both ends; QUESTION I EXACT in every interval;
  M = PASS, O = AS-ASSIGNED beside; THE ROUTING IS A PHYSICAL FACT (hw, the runs) (GBP-HW-266...271; GBP-KEY-004
  promoted; the consolidated pages moved to F (hw, run-scoped) with history). RUN 16 (the menu reading, ORIGINAL
  pad, executed last): UNDECIDED for the join by the rule (R_8 = R_9 = 8), M = PASS, O NOT READABLE (direction not
  reported, not inferred). truncated=0 in all three: GBP-KEY-008's repair physically validated. BBA / Ethernet /
  display chain DECLARED after the ingestion (Issue #35: BBA present, no cable; chain unchanged -- two STANDING
  declarations, in his words, until he announces a change; at ingestion recorded absent, not inferred; history kept).
  Phase 5's acceptance criterion (a real game) NOT assessed and now FURTHER AWAY. RUN 19 / RUN 20 (Issue #34,
  HARDWARE_TESTS §V7.5; AMENDED then WITHDRAWN BEFORE HARDWARE under Issue #37) are NOT RUN and their ten names are
  RETIRED: the Operator objected that the checker had served every controller test already, and the Orchestrator
  accepted it -- THE ROUTING DOES NOT DEPEND ON THE PAD (Question J reads word -> counter; the pad is upstream of the
  word), so a walk x pad matrix adds nothing to the FACT of §V7.4; what is given up is recorded (eight button x pad
  combinations without a machine-decoded pad -> word reading; his equivalence criterion to be answered on a game by his
  report). Kept: WarioWare: TWISTED evaluated and REJECTED (gyroscope); the two criteria apart (a test ROM is not a
  game); the build change ASSESSED in §V7.5.3 and NOT made (~40 s is enough for the checker; a real game needs it).
  The next run number is 21.
  ISSUE #38 (the runtime image fit for a game): ASSESSED, NOT BUILT -- STOP by the Issue's own rule. The subtraction of
  the research instrumentation is clean (the witness unbinds with one statement, null-safe; the full-frame sampler and
  the VI trace come out, and with the sampler the origin dependency of Issue #37 goes), but once the witness is gone the
  image has NO SUCCESS STOP: every remaining stop -- the 60 s safety budget, the 16384-frame store cap (274 s), the
  400 000 delivery cap -- is scored as the run going wrong, the status fields do not distinguish an ended session from a
  failed one, and the POC cannot end the run itself (the pump hook is void; the config has no session field). A usable
  image needs a success stop in CHECK_ADMISSION (src/gbp/gbp_vstate_probe) and a new POC with its own audit profile: a
  REDESIGN, its own checkpoint. INPUT_PATH.md §12 has the assessment; the input path and the KEY record stay untouched.
  ISSUE #39 (the playable image): BUILT, NOT RUN. play-0001 @ 2e48ca7 (sha256 d0ee3c29d04254d1b86d4f006291008876b5e886e07280d0421b7c1161c499de; 487 968 B) = stream-0015's runtime
  without its research instrumentation (the witness never bound, the sampler / VI trace / disposition trace and the
  four sidecars out), the input path and the KEY record BYTE-IDENTICAL (the two functions diffed by test), plus the
  operator's session end: Z held 250 ms -> gbp_session -> cfg.session_end -> stop=session_end status=ok_session_ended
  teardown=S5_session_end, THE ONLY SUCCESS (new stop / status / config field in src/gbp/gbp_vstate_probe, read once per
  admission after the safety budget and the store caps; unit-tested through the real run loop). Sized for 720 s
  (frame store 45056 = 754 s, events 16384, guard 6 M, ringlog 8192 with a 640-line reserve; +8.1 MB of stores and log
  against 11.05 MB freed; arena1_free 5 439 488 B measured in Dolphin). Zero warnings; two from-scratch builds
  byte-identical; play-audit 0 findings (handlers identical to GBP-VIDEO-001's; the profile fails the stream image
  both ways); Dolphin PASS on the absent-device abort path with the ceiling stated (the pump never runs there). THE
  SERVICE PASS IS SHORTER by the witness step (RUN 17: 5/70/1547 ticks per VIDEO block); the pre-witness shape has
  precedent (stream-0003 / 0004) but never with the input path: UNCHECKED until the image's first run, which is the
  measurement (INPUT_PATH.md §13.5). U-GBP-035 opened (long-session presentation: no instrument). Nothing staged, not
  exported (build/swiss/12-stream keeps stream-0015), no run name, nothing pre-registered, no game chosen.
  (The "105 findings" figure of that checkpoint is CORRECTED to 102: INPUT_PATH.md §13.8, Issue #41.)
  ISSUE #41 (2026-09-21): RUN 21 / RUN 22 PRE-REGISTERED as GBP-INPUT-004 (HARDWARE_TESTS §V7.6), NOT RUN, NOT
  AUTHORISED there, NOT STAGED. play-0001's first runs, on the ONE pair: QUESTION A = Phase 5's acceptance in the
  Operator's terms (W / S / K; his report is the game's channel, the KEY record beside it splitting every "did not
  work" into SENT and NOT SENT) and QUESTION T = the timing of the shortened service pass, SEPARATE GATES by §V6.13,
  with ONE interaction frozen (a run whose service failed had no session, so it is inconclusive for A too). A timing
  FAULT is an EXPECTED POSSIBLE OUTCOME, not a failed run. THREE CANDIDATE GAMES are named before the run and the
  Operator DECLARES AT RUN TIME which he used ("nomeie os 3 jogos por enquanto... Quando eu testar eu informo"), the
  same title and form in both runs: (1) WarioWare, Inc.: Mega Microgame$! -- the NORMAL one, not Twisted -- a ROM on the
  EZ-Flash NOR, the crispest feedback (a microgame demands one input and fails visibly), mostly D-pad and A so L / R /
  SELECT / B are expected N/A; (2) Pokemon Emerald, his note that it uses L and R, covering the most keys but at a
  slower pace, its cartridge RTC recorded as possibly absent or emulated from a flashcart -- which affects berries and
  tides, NOT input; (3) Yoshi's Island (Super Mario Advance 3), his BELIEF that it uses L and R, recorded as his
  statement and not asserted. Each candidate's cartridge hardware CHECKED, not presumed; Twisted stays rejected (owned
  as an original, JP and US). The choice got easier because Issue #39 removed the ~40 s window: the session now ends
  when he ends it. The attribution caveat rides every citation unless he declares an ORIGINAL. RUN 21 = ORIGINAL pad,
  RUN 22 = GENERIC pad, same game, same list. The action list LEANS ON ORDINARY PLAY with a short deliberate head and a
  closing sweep; N/A IS NOT A FINDING -- a game that never asks for L is not evidence that L fails. The session is the Operator's:
  Z held ~1 s -> stop=session_end, the only success; the whole session must fit inside 720 s. TWO gate items for him
  before the first boot: the cartridge declaration and that the Z hold is workable. Two raw names reserved (this image
  writes ONE file and no sidecars). Phase 5's closure NOT decided.

  Previous: RUN 13 --
  GBP-VIDEO-007 / GBP-VIDEO-008 / stream-0013 @ 7d7a6d8 + coord-0002, executed 2026-09-21 -- RUN 13
  GBP-HW-256 ... GBP-HW-260; no new finding
  STANDING: EXECUTED · GBP-VIDEO-007 = PASS (CLAIM-D only) · GBP-VIDEO-008 = PASS (CLAIM-A/B, eight
  sampled frames only) (HARDWARE_TESTS §V6.25)

  The shared source-window gate -- the one RUN 12 failed -- passed: frozen vindex.py
  OBSERVED_CONTIGUOUS, 2048 intact records, 2046/2046 decisive transitions +1, FRAME_ID
  52..2099, INVALID 0, FAULT 0; the four entries came +1 (479->480, 959->960, 1439->1440,
  1919->1920), so §V6.22's expectation for coord-0002 is read off the data (no new finding).
  OGBPFULL1 K=8 complete, unchanged vfull.py PASS 8/8, 0 mismatches in all 38 400 words of
  every sample -> GBP-VIDEO-008 = PASS for those eight frames only. OGBPVI1 2377 handed /
  2371 latched / 5 superseded; the CORRECTED vvi.py (§V6.21, used prospectively) reads
  2371/2371 top and bottom, L = 40/40/39/40 (one R_3 hand-over SUPERSEDED, frame_index 1754:
  instrumentation semantics only). Operator saw digits 1 2 3 4 in order, ~8 s apart (a human
  estimate, never timing evidence) -> GBP-VIDEO-007 = PASS as CLAIM-D: a digit bound to a
  40-frame appearance set, never to one frame; no pixel claim.
  Transport / startup / Policy A clean under the inherited gates: first hand-off
  165.151852 ms, frozen p99 0.308543 ms / max 1.005012 ms, 7 repeats (observational).
  Topology (operator declaration, confirmed after the return): same GameCube and GBP as
  RUN 12, BBA PRESENT, Ethernet DISCONNECTED, composite/RCA -> low-cost RCA-to-HDMI
  converter (1080p out) -> HYDIS HV150UX2 / M.NT68676.2A (a declaration; no pixel claim).
  Five raw files located by SHA-256 and archived first under the reserved run-13 names
  (their arrival in logs/ overwrote RUN 12's bare-name copies there; RUN 12's run-12
  archive verified intact); fixtures versioned; tests/host/test_run13.py. Hardware Issue
  #15 stays open until the Orchestrator validates this ingestion. No rerun pre-registered.

  Previous: RUN 12 --
  GBP-VIDEO-007 / GBP-VIDEO-008 / stream-0013 @ 7d7a6d8 + coord-0001, executed 2026-09-20
  GBP-HW-250 ... GBP-HW-255; GBP-VID-034 (MECHANISM RESOLVED, Issue #12), GBP-VID-035 (REPAIRED in software, Issue #11)
  STANDING: EXECUTED · GBP-VIDEO-007 INCONCLUSIVE · GBP-VIDEO-008 INCONCLUSIVE (HARDWARE_TESTS §V6.20)

  The shared source-window gate failed: frozen vindex.py OBSERVED_DISCONTINUITY --
  2048 intact records, two duplicate FRAME_ID transitions (479->479 at frame_index
  761->762, 1919->1919 at 2202->2203), INVALID 0, FAULT 0; mechanism RESOLVED by Issue #12
  (§V6.22): PREPARE-side missed VBlanks at the digit-1 and digit-4 entry frames, the
  stimulus's own scheduling, invisible to its FAULT latch (GBP-VID-034).
  Subordinate: OGBPFULL1 K=8 complete, frozen vfull.py PASS 8/8, 0 mismatches in all
  38 400 words of every sample -- NOT a GBP-VIDEO-008 experiment PASS. Operator saw
  digits 1 2 3 4 in order (observation, beside the chain). OGBPVI1 2377 handed / 2370
  latched; the analyzer FROZEN AT THE RUN read 0/2370 consistent -> L_k = 0 (history,
  GBP-HW-255); the defect GBP-VID-035 (a 24-bit mask before the flag shift) was
  REPAIRED in software by Issue #11 (§V6.21): the corrected post-run replay reads
  2370/2370 top, 2370/2370 bottom, L = 40/40/38/40 (two R_3 hand-overs SUPERSEDED,
  no latch record: instrumentation semantics only). Verdicts unchanged.
  Transport / startup / Policy A clean under the inherited gates: first hand-off
  165.152173 ms, frozen p99 0.308642 ms / max 1.004667 ms, 7 repeats (observational).
  Topology (operator declaration): same GameCube and GBP as runs 10-11, BBA PRESENT,
  Ethernet DISCONNECTED, composite/RCA -> low-cost RCA-to-HDMI converter (1080p out)
  -> HYDIS HV150UX2 / M.NT68676.2A (a declaration; no pixel claim). Five raw files
  archived first under the reserved run-12 names; fixtures versioned;
  tests/host/test_run12.py. No rerun pre-registered; nothing fixed.

  Previous: RUN 11 --
  GBP-VIDEO-006 / stream-0011 @ 97c78c2 + indexed-0003, executed 2026-09-20
  GBP-HW-244 ... GBP-HW-249; GBP-VID-033 PHYSICALLY VALIDATED
  STANDING: EXECUTED · PASS · NO DETECTED REGRESSION (HARDWARE_TESTS §V5.58.9)

  Topology held at run 10's (operator declaration): BBA PRESENT, Ethernet
  DISCONNECTED, same GameCube, same GBP. The reporting build was the intentional
  variable. Coordinated through GitHub Issue #2 -- the first checkpoint run
  through an Issue; the remote moved to GitHub in Issue #3 (2026-09-20).

  PRIMARY GATE, read directly off the log: lines=651 dropped=0 truncated=0;
  one complete WITELIG (167 chars) + one complete WITELIG2 (98);
  qual_streak_at_eligible=0 PRESENT, no derivation; counters agree.

  REGRESSION, reproduced: vindex.py OBSERVED_CONTIGUOUS, intact 2048 / INVALID 0,
  IDs 73..2120; eligibility 5.000143926 s; first hand-off 165.158691 ms
  (+177 ticks vs run 10, recorded, no tolerance); transport 254 864, zero
  errors; join 2047 SELECTED_NEW + capture edge, interior 0, reorder 0, depth 1;
  frozen latency p99 0.486790 ms / max 1.000914 ms; 7 display repeats
  (sixth run running, OBSERVATIONAL).

  Media double check: PENDING for runs 9, 10 and 11.

  Previous: run 10 (GBP-BBA-001, stream-0010, BBA present, PASS, GBP-HW-239…243);
  run 9 (not-before gate, stream-0010, PASS 14/14, GBP-HW-231…238); run 8
  (GBP-VIDEO-005 retail cartridge, stream-0009, GBP-HW-223…230); run 7 (normal
  startup, stream-0009, GBP-HW-213…222); run 6 (Policy A, stream-0008,
  GBP-HW-202…212); run 5 (stream-0007, the first downstream trace, GBP-HW-192…201);
  run 4 (stream-0006, OBSERVED_CONTIGUOUS, GBP-HW-180…191). Each keeps its own
  record in HARDWARE_TESTS.md and is never re-judged.
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
| **Phase 5 — Input, implemented and physically executed (GBP-INPUT-001, GBP-INPUT-002: the routing FACT)** | **Issue #18 (2026-09-21)** reconstructed the path (`docs/research/INPUT_PATH.md`: three layers kept apart; U-GBP-010 RESOLVED STATICALLY at CORROBORATED and OPEN). **Issue #19 (2026-09-21)** implemented it: `src/gbp/gbp_input.c` behind the existing transport boundary — the mapping as a policy table, the encoding descriptor as data in ONE place filled with the CORROBORATED assignment by the Operator's decision (status and falsifier at the definition; flipping it is one line), one 32-byte write, write-on-change plus a 5 ms refresh — the step as the first statement of the stream probe's pump slot, host tests (8 453 C checks; the Python pins), and the candidate **`stream-0014` = commit `0ff8355`, 513 152 B, SHA-256 `ef76a170c10d335e62c017e53f74c60e410e44f5ce2fbca6774ab43c68ec0b9c`**. **Issue #20 / #23** pre-registered and amended before hardware (§V7.1). **EXECUTED 2026-09-21 (Hardware Issue #21) AND INGESTED (§V7.2, Issue #24): RUN 14 (the Enhanced Control Checker's counted walk A) and RUN 15 (walk B) on the unchanged image — Question M = PASS · Question O = AS-ASSIGNED in both.** Machine side: INPUT attempts = completed = 7 892 / 7 895, failed 0, 42 key changes each (the runtime polled, encoded and wrote; the window is write-only). Human side: the Operator's tally vectors `1 2 · · · · 6 5 3 4` and `1 2 3 4 5 6 · · · ·` = the walks' expectation. Independently: the checker's screen in the preserved OGBPFULL1 frames decodes pixel-exactly to the same vectors (FACT as data). **The physical keypad record held these two runs and nothing else until Issue #33 added RUN 17 / RUN 18 / RUN 16 (below).** U-GBP-010 CLOSED with the descriptor kept; **the routing stays CORROBORATED, not FACT** (the Operator having pressed L exactly once is in no machine record; one log line would close it — GBP-KEY-009, not implemented); `truncated=1` in both logs = the clipped ENVINPUT record (GBP-KEY-008). Not established: latency, the refresh's necessity, other pads / cartridges, rumble, the display chain, the acceptance criterion (a real game; NOT assessed). RUN 16 NOT RUN. **Promoted (Issue #26):** `docs/protocol/INPUT.md` written; the keypad rows of `REGISTERS.md` (§2, §2.3), `GBS-DOL.md` and `ARCHITECTURE.md` and `INITIALIZATION.md` §15 carry the state — the L/R order C, not FACT, with the generic-pad scope beside it; no status changed. **Issue #27 (2026-09-21):** GBP-KEY-009 implemented and GBP-KEY-008 repaired in the candidate `stream-0015` (`da06500`, `dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49`) — one `KEY` line per non-refresh write, bounded, in the sidecars' time base; NOT executed, not staged; FACT for the routing reachable by a run, not actual (GBP-KEY-010). **Issue #28 (2026-09-21):** RUN 17 (walk A) / RUN 18 (walk B) PRE-REGISTERED as GBP-INPUT-002 in §V7.3 — the whole-run join of the KEY record to the frames can take the routing to FACT per bit (Question One answered: per-press and latency out of reach, the interval check recorded only, pacing excluded). **EXECUTED AND INGESTED (Hardware Issue #32; Issue #33, §V7.4):** RUN 17 (generic pad) / RUN 18 (original pad) / RUN 16 (the menu reading, executed last) on `stream-0015` — Question J = FACT for all ten word bits, bits 8 and 9 on two controllers: **the routing a physical FACT (hw, the runs)**, GBP-HW-266…271; Question I EXACT everywhere; RUN 16 UNDECIDED by the rule, M = PASS, O not readable; `truncated=0`: GBP-KEY-008 validated; GBP-KEY-004 promoted; `REGISTERS.md`, `GBS-DOL.md`, `ARCHITECTURE.md`, `INITIALIZATION.md` §15 and `INPUT.md` moved to F (hw, run-scoped) with history. Not established: latency, the refresh, pads beyond the two, a game. **Issue #34 (2026-09-21):** the acceptance pair PRE-REGISTERED as GBP-INPUT-003 in §V7.5; **AMENDED, then WITHDRAWN BEFORE HARDWARE (Issue #37):** RUN 19 / RUN 20 NOT RUN, their names retired — the routing does not depend on the pad (J reads word → counter), so a checker run on the other pad adds nothing to §V7.4's FACT; what is given up recorded; WarioWare: Twisted REJECTED; the two criteria apart; the build change assessed, not made; the phase's closure not decided there, and further away. | `docs/research/INPUT_PATH.md`; `docs/protocol/INPUT.md`; `EVIDENCE.md` GBP-KEY-002…010, GBP-HW-261…271; `UNKNOWNS.md` U-GBP-010 (CLOSED); `docs/ROADMAP.md` Phase 5; `HARDWARE_TESTS.md` §V7.1–§V7.4 |
| **GBP-INPUT-001** (the first physical KEYPAD write; L/R order) | **RUN 14 AND RUN 15 EXECUTED 2026-09-21 AND INGESTED (§V7.2; Hardware Issue #21, ingestion Issue #24): Question M = PASS · Question O = AS-ASSIGNED, in both runs — each inside its pre-registered boundary (§V7.1.9, frozen before the runs) and nothing wider.** Two runs of the unchanged `stream-0014` (`0ff8355`, `ef76a170…`) with the Enhanced Control Checker (`76924c13…`, the Operator's media on the EZ-Flash NOR): walk A (L 1, R 2, A 3, B 4, SELECT 5, START 6) and walk B (L 1, R 2, UP 3, DOWN 4, LEFT 5, RIGHT 6), 21 presses each, ended at the witness target. INPUT machine gate met in both (attempts = completed = 7 892 / 7 895, failed 0, 42 key changes = 2 × 21, descriptor `0,1,2,3,4,5,6,7,9,8` as data); inherited transport / startup / Policy A clean; `truncated=1` = the ENVINPUT record clipped at 248 of 266 characters, lost fields recoverable (GBP-KEY-008). The Operator's vectors (`1 2 · · · · 6 5 3 4`, `1 2 3 4 5 6 · · · ·`) and the vectors decoded from the OGBPFULL1 frames agree digit for digit and are recorded apart; a blank counter is read as never incremented (the frozen gate says 0; the instrument prints nothing — recorded). U-GBP-010 CLOSED on its own condition, descriptor kept; the routing CORROBORATED, not FACT (GBP-HW-265); the finding: one log line — the word at each key change — would make it FACT (GBP-KEY-009, not implemented). Video path recorded not judged (vindex / vfull INCONCLUSIVE by construction on non-OGBPCOORD1 content; vdisp, Policy A, corrected vvi clean; RUN 15 `frame_index` 1169 latched two retraces after its hand-over — instrumentation semantics). Topology declared after the runs (Issue #25): same GameCube; BBA present without a network cable; video chain unchanged; a GENERIC third-party controller (the official pad owned, not used) — so the L / R result is the digital click of a third-party pad, encouraging and a limit (the official pad not exercised); the same Game Boy Player by the Operator's declared hardware inventory (exactly one GameCube, exactly one GBP — a declaration, not an inference). Ten raw files archived first; tally frames versioned; `tests/host/test_run14.py`. No rerun pre-registered; RUN 16 NOT RUN; nothing under `src/`, `poc/`, `tools/`, `Makefile` moved | `HARDWARE_TESTS.md` §V7.1, §V7.2; GBP-HW-261…265; GBP-KEY-008, GBP-KEY-009 |
| **Phase 4 — Video, against its acceptance criterion** | **Phase 4 ASSESSED 2026-09-21 (GitHub Issue #17): `PHASE 4 VERDICT: SATISFIED WITH NAMED RESIDUALS`.** The criterion — a real cartridge running on the physical GBP produces stable, correct video through the open-source runtime — is satisfied for the video path as a path: a retail cartridge ran three times with transport, NORMAL startup and Policy A measured clean on retail content (GBP-HW-138…151, 224…226) and the picture observed by the operator (GBP-HW-144, 152, 227); the path's correctness — geometry GBP-HW-081, composition GBP-HW-076/077, colour GBP-HW-131, full-frame fidelity on eight sampled frames GBP-HW-258, scanout as CLAIM-D GBP-HW-260 — is FACT on controlled stimuli inside each run's boundary. The named residuals and their owners: correctness of retail content by measurement (**Phase 7**); presentation / scaling / pixel-perfect GBP-VID-032 (**Phase 9**); physical pixel equality and per-frame scanout accounting (**not scheduled**); stability duration and breadth, GB/GBC (**Phase 12**, **Phase 7**); the colour intra-group limit (**not scheduled**); U-GBP-029 / 034 / 030 / 033 (open research residuals); rate conversion (**Phase 9**); audio (**Phase 6**), input (**Phase 5**); BBA / Ethernet (**Phase 11**); production UX (**Phase 9**, **Phase 12**). The assessment re-judges no run, promotes no status, closes no unknown, mints no id and **does not authorise Phase 9 work** or any run. Promoted with ids: `docs/protocol/VIDEO.md` (new) and the video rows of `docs/hardware/ARCHITECTURE.md`, `docs/hardware/GBS-DOL.md`, `docs/protocol/REGISTERS.md` | `docs/research/PHASE4_ASSESSMENT.md`; `docs/ROADMAP.md` Phase 4 "Phase 4 assessment"; `docs/protocol/VIDEO.md` |
| **GBP-VIDEO-007 / GBP-VIDEO-008** (physical scanout; full-frame fidelity) | **RUN 13 EXECUTED 2026-09-21 AND INGESTED (§V6.25; Hardware Issue #15, ingestion Issue #16): GBP-VIDEO-007 = PASS · GBP-VIDEO-008 = PASS — each inside its pre-registered boundary and nothing wider.** The shared prospective source-window gate passed — frozen `tools/vindex.py` reads `OBSERVED_CONTIGUOUS` (2048 intact, INVALID 0, FAULT 0, 2046/2046 decisive transitions +1, FRAME_ID 52..2099); the four appearance entries came +1, so §V6.22's expectation for `coord-0002` is read off the data (no new finding). GBP-VIDEO-008 = PASS is CLAIM-A / CLAIM-B for the eight prospectively sampled frames only: unchanged `tools/vfull.py` 8/8, 0 mismatches in all 38 400 words of every sample, texture == Python == host C == tiled oracle; no physical pixel equality, nothing about the 2 040 unsampled frames. GBP-VIDEO-007 = PASS is CLAIM-D only: the corrected `tools/vvi.py` (§V6.21, used prospectively) reads 2371/2371 and L = 40/40/39/40 (the one R_3 hand-over not in L_3, `frame_index` 1754, is SUPERSEDED — instrumentation semantics, never non-scanout), and the operator saw 1, 2, 3, 4 in order (~8 s apart, a human estimate, never timing evidence) under the declared composite → RCA-to-HDMI converter → HYDIS HV150UX2 chain; a digit is bound to a 40-frame appearance set, never to one frame; no pixel, tearing, presentation, scaling or converter claim. Transport / startup / Policy A clean. **RUN 12 (§V6.20; Hardware Issue #9, ingestion Issue #10) remains historical: GBP-VIDEO-007 INCONCLUSIVE · GBP-VIDEO-008 INCONCLUSIVE.** The shared prospective source-window gate failed there — frozen `tools/vindex.py` reads `OBSERVED_DISCONTINUITY` (2048 intact, INVALID 0, FAULT 0, two duplicate FRAME_ID transitions 479→479 and 1919→1919; GBP-VID-034, mechanism RESOLVED by Issue #12 — PREPARE-side missed VBlanks at the digit-1 and digit-4 entry frames, §V6.22). Preserved beside the verdicts and promoting neither: the frozen `tools/vfull.py` full-frame dependent-variable analysis PASS 8/8 with 0 mismatches (subordinate; never a PASS of the GBP-VIDEO-008 experiment); the operator's literal report — digits 1, 2, 3, 4 in order, nothing missing or anomalous — under the declared composite → RCA-to-HDMI converter → HYDIS HV150UX2 chain; OGBPVI1 2377 handed / 2370 latched with frozen L_k = 0 (the `tools/vvi.py` frozen at the run masked the address before the flag shift — GBP-VID-035, analyzer defect, REPAIRED in software by Issue #11, §V6.21: the corrected post-run replay reads 2370/2370 and L = 40/40/38/40, and changes no verdict). Transport / startup / Policy A clean. No rerun pre-registered; `coord-0001`, the analyzers, the formats and the gates unchanged. **`coord-0002` (§V6.23) is the timing-safe re-implementation of the same picture: implemented, proven on its exact image (every entry PREPARE 176 863 cycles under the budget, zero ROM reads), physically executed once, in RUN 13 (pre-registered §V6.24, Issue #14; executed Hardware Issue #15; ingested §V6.25, Issue #16), where the source gate passed with no duplicate at any entry** | `HARDWARE_TESTS.md` §V6.19, §V6.20, §V6.22, §V6.23, §V6.24, §V6.25; GBP-HW-250…255, GBP-HW-256…260 |
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
| **OGBPCOORD1** | the coordinate stimulus WIRE format of `coord-0001`, frozen at `99496a6` / `7d7a6d8` (§V6.18.3): x = 0..55 byte-identical to OGBPIDX1 (FLAG, STRIP-L, GUARD-A), FIELD `y*183 + (x-56)` on x = 56..238 (injective, bit 15 clear, painted once), GUARD-C at 239, no STRIP-R, no bar; a 48×80 seven-segment digit (k mod 10) at (123, 40) plus six 8×8 counter squares at (123+8i, 128) for FRAME_ID in [k·480, k·480+40), k ≥ 1, colour 0x7FFF. The witness gate, `tools/vindex.py` and every regression gate apply unchanged. Second implementation `coord-0002` (§V6.23): same wire format, same picture, timing-safe entry frames, NOT run. **RUN in RUN 12** (§V6.20): 2048 intact witness records, FAULT 0, VMARGIN 38/39/54, and two duplicate FRAME_ID transitions (GBP-VID-034, mechanism RESOLVED by Issue #12 — PREPARE-side missed VBlanks at the digit-1 and digit-4 entry frames, §V6.22). Canonical ROM 3 496 B `90343b64…0a1f` | `stimulus/agb-coord/source/main.c`, `tools/icoord.py`, `HARDWARE_TESTS.md` §V6.18.3 |
| **OGBPFULL1 v1** | the FULL-FRAME SAMPLE sidecar, new in `stream-0013`: magic `"OGBPFULL"`, header 0x100, K ≤ 8 records of 0x80 meta + 153 600 raw + 76 800 big-endian texture = 230 528 B each, `"OGBPFEND"` footer, header / per-record / global CRC-32. Content-blind sample rule `origin + 256·i` from the witness window's first retained frame. A sample is COMPLETE only with 40/40 blocks of ONE lifecycle; generation or slot reuse → REFUSED, never mixed. Carries NO XFB CRC. **PHYSICALLY PRODUCED in RUN 12** (1 844 492 B `fb09a777…433c`, strict parse, 8/8 COMPLETE, frozen analysis PASS 8/8 — subordinate; §V6.20.6) | `src/gbp/gbp_vfulldump.h`, `tools/vfull.py`, `HARDWARE_TESTS.md` §V6.18.4 |
| **OGBPVI1 v1** | the HAND-OVER / VI-LATCH sidecar, new in `stream-0013`: magic `"OGBPVI1\0"`, header 0x100, ≤ 4096 records of 64 B (frame_index, life, xfb, flags LATCHED / SUPERSEDED, phys, t_handed, retrace_handed, retrace_latch, t_latch, VI[14] VI[15] VI[18] VI[19] read back at the latch), `"OGBPVEND"` footer, header / per-record / global CRC-32. The latch is the pump's first observation that libogc2 reports the handed XFB current: CLAIM-C, software, never scanout. **PHYSICALLY PRODUCED in RUN 12** (152 396 B `d301e96e…ddb0`, strict parse, 2377 handed / 2370 latched / 6 superseded; the reader's address-domain defect at the time of the run is GBP-VID-035, repaired in software afterwards, §V6.21; §V6.20.7) | `src/gbp/gbp_vvidump.h`, `tools/vvi.py`, `HARDWARE_TESTS.md` §V6.18.5 |
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
| **GBP-PLAY-001 / the playable image (Issue #39)** | `play-0001` | `2e48ca7` | `d0ee3c29d04254d1b86d4f006291008876b5e886e07280d0421b7c1161c499de` | **NOT PHYSICALLY EXECUTED; no run pre-registered; not staged; not exported.** 487 968 B; zero warnings, none suppressed; two from-scratch builds at `2e48ca7` byte-identical; `make play-audit` 0 findings (the ext and base one-shot handlers identical to the physically validated GBP-VIDEO-001 build's); Dolphin PASS, device absent (the abort path; the pump slot never runs there). The input path and the KEY record byte-identical to stream-0015's; the session end on Z is the only success; the service pass shorter by the witness step, UNCHECKED until the first run | `INPUT_PATH.md` §13; Issue #39 |
| GBP-VIDEO-004 (embedded id) / **GBP-INPUT-002 image, EXECUTED** | `stream-0015` | `da06500` | `dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49` | **EXECUTED 2026-09-21 — RUN 17, RUN 18 and RUN 16 (Hardware Issue #32; ingested §V7.4, Issue #33): the join closed FACT for all ten word bits; staged in `build/swiss/12-stream/` with stream-0014 preserved to `build/archive/` first (`ef76a170…0b9c`).** 514 880 B; stream-0014 plus the per-change `KEY` record (GBP-KEY-009: one line per first / change / retry write, the word and three instants in the sidecars' time base, bounded by the ringlog with a 64-line reserve) and the ENVINPUT repair (GBP-KEY-008: `ENVINPUT` + `ENVINPUT2`); zero warnings, none suppressed; two consecutive clean builds byte-identical; `make stream-audit` 0 findings (the ext and base one-shot handlers identical to the physically validated GBP-VIDEO-001 build); Dolphin absent / model on the stated conditions — the pump slot never runs there, so neither the write nor the record is exercised by it. The descriptor and the policy byte-equal to `0ff8355`. **Reproduce with `rm -rf build/poc && GIT_COMMIT=da06500 GIT_DIRTY= make build`** | `EVIDENCE.md` GBP-KEY-010; Issue #27 |
| GBP-VIDEO-004 (embedded id) / **GBP-INPUT-001** **last physically executed** | `stream-0014` | `0ff8355` | `ef76a170c10d335e62c017e53f74c60e410e44f5ce2fbca6774ab43c68ec0b9c` | **PHYSICALLY EXECUTED 2026-09-21 — RUN 14 (walk A) and RUN 15 (walk B), Hardware Issue #21; ingested §V7.2, Issue #24: Question M = PASS · Question O = AS-ASSIGNED in both; INPUT attempts = completed = 7 892 / 7 895, failed 0, 42 key changes each; `lines=686 dropped=0 truncated=1` (the clipped ENVINPUT record, GBP-KEY-008); the checker's tally screen decoded from the preserved OGBPFULL1 frames equals the Operator's vectors.** 513 152 B; stream-0013 plus the input path in the pump slot (Issue #19). Never rebuilt or re-labelled; stream-0013 preserved at `build/archive/` | `HARDWARE_TESTS.md` §V7.1, §V7.2; GBP-HW-261…265 |
| GBP-VIDEO-004 / **GBP-VIDEO-007 / GBP-VIDEO-008** **previously executed** | `stream-0013` | `7d7a6d8` | `5391c3fe962dc4b2f4e493f3846ac7407ded064c58f5d4bb583a51e5a725dd79` | **PHYSICALLY EXECUTED 2026-09-20 — RUN 12 (Hardware Issue #9; pre-registered §V6.19; ingested §V6.20, Issue #10): GBP-VIDEO-007 INCONCLUSIVE · GBP-VIDEO-008 INCONCLUSIVE — the shared source gate failed (`OBSERVED_DISCONTINUITY`, two duplicate FRAME_ID transitions, GBP-VID-034); transport / startup / Policy A clean (`lines=674 dropped=0 truncated=0`, first hand-off 165.152173 ms, frozen p99 0.308642 ms); frozen vfull 8/8 subordinate; GBP-HW-250…255. Historical; never rebuilt or re-labelled. EXECUTED AGAIN 2026-09-21 — RUN 13 (Hardware Issue #15; pre-registered §V6.24; ingested §V6.25, Issue #16) with coord-0002, the same bytes, NOT rebuilt: GBP-VIDEO-007 = PASS · GBP-VIDEO-008 = PASS inside their boundaries; the shared source gate passed (`OBSERVED_CONTIGUOUS`); GBP-HW-256…260.** 506 496 B, built twice from scratch at `7d7a6d8` and byte-identical (`cmp`), Swiss `build/swiss/12-stream/boot.dol` byte-identical, no `-dirty`, Dolphin PASS (normal and GBP profiles; auxiliary). Embeds `stream-0013 7d7a6d8` and TEST_ID `GBP-VIDEO-004`. **Reproduce with `rm -rf build/poc && GIT_COMMIT=7d7a6d8 GIT_DIRTY= make build`.** `stream-0012` plus the §V6 instrumentation: K = 8 content-blind full-frame samples (`OGBPFULL1 v1`, `-full.bin`) and the hand-over / VI-latch trace (`OGBPVI1 v1`, `-vi.bin`); `ENVFULL` reports `arena1_free=1658880` after 2 080 768 B of new static stores. No witness, transport, Policy A, display, startup or frozen-format semantics change; `gbp_vwitness.*` and every frozen tool unchanged since `97c78c2` (git) | `HARDWARE_TESTS.md` §V6.18 |
| GBP-VIDEO-004 **software-only, superseded as candidate** | `stream-0012` | `c465f5c` | `4495c8367b116910f9edb784732c4611a17bdcaedb7dce58eb07579a46ce7e73` | **NOT PHYSICALLY EXECUTED; no run pre-registered.** 495 168 B, built from scratch at `c465f5c`, Swiss `build/swiss/12-stream/boot.dol` byte-identical, Dolphin PASS. **Reproduce with `rm -rf build/poc && GIT_COMMIT=c465f5c GIT_DIRTY= make build`.** `stream-0011` with ONE configuration change (§V5.59, F5): the generic vstate time target is DISABLED by name (`gbp_vstate_config_disable_time_target`), so the witness target is the experiment's only success condition; 60 s safety cap, 5000 ms not-before, 64 closes and 2048 records unchanged; no witness, transport, display, startup or format semantics change. **Superseded as the stream line's candidate by `stream-0013` (§V6.18); never run, identity preserved** | `HARDWARE_TESTS.md` §V5.59 |
| GBP-VIDEO-004 / **GBP-VIDEO-006** | `stream-0011` | `97c78c2` | `df2873ee61caa75c885215b54e29e8d5357b233b9bcc0f10d5c0b1af75453e25` | **PHYSICALLY EXECUTED 2026-09-20 (run 11, GBP-VIDEO-006, BBA PRESENT / Ethernet DISCONNECTED by operator declaration) — PASS (§V5.58.9): `lines=651 dropped=0 truncated=0`, one complete `WITELIG` and one complete `WITELIG2`, `qual_streak_at_eligible=0` read directly; `OBSERVED_CONTIGUOUS` with 2048 intact / 0 invalid; first hand-off 165.158691 ms; frozen p99 0.486790 ms; 7 display repeats. GBP-VID-033 PHYSICALLY VALIDATED for this controlled run; media double check PENDING.** `stream-0010` with ONE reporting change: the `WITELIG` summary is two records, `WITELIG` and `WITELIG2`, so no field is clipped by the 248-character ringlog payload (worst-case 205 and 113). No witness, transport, display, startup or format semantics change; `gbp_vwitness.*` byte-identical. 495 104 B (+64 B), built twice from scratch and byte-identical (SHA-256 and `cmp`), Swiss `build/swiss/12-stream/boot.dol` identical, no `-dirty`. **Reproduce with `GIT_COMMIT=97c78c2 GIT_DIRTY= make build`.** Physical validation: GBP-VIDEO-006 / RUN 11, executed 2026-09-20, PASS (§V5.58.9; GBP-HW-244…249) | `HARDWARE_TESTS.md` §V5.58 |
| GBP-VIDEO-004 / **GBP-BBA-001** **previous runs** | `stream-0010` | `fbaea00` | `6b57d6696cf718baaac83cd0b9631c672bbe756f842e42bfd12d7a0ee3736180` | **PHYSICALLY EXECUTED 2026-09-20 twice: run 9 (BBA disconnected) — PASS 14/14 (§V5.56); run 10 (GBP-BBA-001, BBA PRESENT, Ethernet disconnected) — PASS (§V5.57.14), first hand-off 165.154321 ms, 2048 intact / 0 invalid, 7 display repeats; paired topology control, no detected regression.** Run 9: eligibility 5.000156691 s after CONTROL, window at 6.067209383 s, frozen `vindex.py` `OBSERVED_CONTIGUOUS` with `intact 2048 / INVALID 0`, startup 165.154741 ms (+18 ticks vs run 7), Policy A 2047/2047, 7 display repeats. One reporting defect: the `WITELIG` line is clipped at 248 chars (GBP-VID-033); the lost field is recovered exactly; no rerun required. BBA disconnected; media double check PENDING.** RESEARCH NOT-BEFORE GATE (§V5.55). `stream-0009`'s startup and pipeline, byte-for-byte on the user's path, plus ONE research addition: the scientific witness streak is not COUNTED until 5000 ms after the CONTROL transform, then counts from zero; 64 structurally clean closed frames; window at the next block 0; 2048 records; no reset. Content-blind. Transport, assembler, conversion, Policy A, GX, hand-off and everything the user sees are unchanged. 495 040 B, built twice from scratch and byte-identical (SHA-256 and `cmp`), no `-dirty`. **Reproduce with `GIT_COMMIT=fbaea00 GIT_DIRTY= make build`** | `HARDWARE_TESTS.md` §V5.55 |
| GBP-VIDEO-004 / **GBP-VIDEO-005** **previous run** | `stream-0009` | `59d2f57` | `4d0337bb2cc7fe6e9acc1fb167e05a29caf7c497297ee7a1618d7e61a4d8c955` | **PHYSICALLY EXECUTED 2026-09-19 (run 7, indexed) and 2026-09-20 (run 8, RETAIL — GBP-VIDEO-005 PASS with a debug-UX note, §V5.54.11; first hand-off 164.696 ms, logo seen by the operator, CORROBORATED GBP-HW-229).** Run 7: — STARTUP PASSED 8/8: first real hand-off 165.154 ms after CONTROL, nothing synthetic handed over, no wait. Policy A clean (2244 hand-offs in order, 7 repeats / 0 drops over the join). Frozen `vindex.py`: `OBSERVED_CONTIGUOUS` with `intact 1988 / INVALID_CANONICAL_STRIP 60` — the structural window opened 3.840 s after CONTROL, the stimulus began at 4.845 s (§V5.53). No new continuity record for this build until a run with a valid steady-state window.** NORMAL STARTUP (§V5.52). `stream-0008`'s pipeline with the diagnostic experience removed from the normal path: the synthetic self-test runs HEADLESS (no framebuffer claimed, so nothing synthetic reaches the video interface), `prehandler_wait_ms` is 0, and both stream framebuffers are cleared to black before the VI is pointed at one. Policy A, the source assembler, the qualification, OGBPIDX and OGBPDISP2 are untouched. A diagnostic image — visible self-test, 5000 ms wait — is still buildable with `make build STARTUP_MODE=GBP_STARTUP_DIAGNOSTIC`. 494 176 B. Built twice from scratch and byte-identical both times (SHA-256 and `cmp`); Swiss `build/swiss/12-stream/boot.dol` identical; 15/15 mutants refused; Dolphin PASS in both profiles with `xfb=0` normal against `xfb=1` diagnostic. **Reproduce with `GIT_COMMIT=59d2f57 GIT_DIRTY= make build`** | `HARDWARE_TESTS.md` §V5.52 |
| GBP-VIDEO-004 **previous run** | `stream-0008` | `5126a19` | `a9efe181d46928d11a20623276a77f352db45b9795681173185e9a60d4e81282` | **PHYSICALLY EXECUTED 2026-09-19 (run 6) — SOURCE-LOSSLESS IN ORDER. 2047/2047 interior scientific frames handed off, 0 drops, 0 supersessions, 0 reorder, max deferred depth 1, p99 0.4946 ms / max 1.1353 ms, and 7 display repeats against a same-run requirement of [7, 8]. Twelve of twelve pre-registered gates passed (§V5.50).** POLICY A: two-XFB asynchronous deferral (§V5.49). A frame that finds no writable framebuffer is DEFERRED and offered again by `pump()`, in age order, instead of being discarded. No third XFB, no extra texture, no VI callback, no `VIDEO_WaitVSync`, no queue-depth change. Downstream sidecar bumped to `OGBPDISP2` because a non-terminal DEFER cannot be expressed in v1 without overloading `HOLD_PREVIOUS_FRAME`. 492 416 B. Built twice from scratch and byte-identical both times; Swiss `build/swiss/12-stream/boot.dol` identical; MEM1 keeps 4.58 MiB free after the framebuffers. 15/15 mutants refused. **Reproduce with `GIT_COMMIT=5126a19 GIT_DIRTY= make build`** | `HARDWARE_TESTS.md` §V5.49 |
| GBP-VIDEO-004 **previous run** | `stream-0007` | `ddf8db6` | `74b7488630153ce3baaa42831a9af8ef03a2bce80399d840062965a34906eb36` | **PHYSICALLY EXECUTED 2026-09-19 (run 5) — source `OBSERVED_CONTIGUOUS` again, and the first downstream trace.** 491 040 B. Adds the OBSERVATIONAL downstream disposition trace and the `OGBPDISP1` sidecar (§V5.46) and nothing else: no pacing, queue depth, conversion, GX, XFB or VI change, and the interrupt path is byte-identical to the physically validated GBP-VIDEO-001 build. Byte-identical across two from-scratch builds; Swiss `build/swiss/12-stream/boot.dol` identical. **Reproduce with `GIT_COMMIT=ddf8db6 GIT_DIRTY= make build`** | `HARDWARE_TESTS.md` §V5.46 |
| GBP-VIDEO-004 **source-continuity candidate** | `stream-0006` | `c629445` | `a9b8b969ef462bfe11b833f9dd77d56f7aa4a3387d61124f99b72901c9cb0379` | **PHYSICALLY EXECUTED 2026-09-19 (run 4) — `OBSERVED_CONTIGUOUS`.** 483 008 B. Adds the PRE-REGISTERED structural window (§V5.44) and nothing else: `OGBPIDX1`, `OGBPIDXCAP1 v1`, the analyzer and the stimulus are untouched, and the interrupt path is byte-identical to the physically validated GBP-VIDEO-001 build. Byte-identical across two from-scratch builds; Swiss `build/swiss/12-stream/boot.dol` identical. **Reproduce with `GIT_COMMIT=c629445 GIT_DIRTY= make build`** — which now actually works, see `c629445` | `HARDWARE_TESTS.md` §V5.44 |
| GBP-VIDEO-004 **previous candidate** | `stream-0005` | `10250a4` | `35bbbdd684c2d0048d58661df1c079b613e01dee2d2cced12ba8f2f1e4d87092` | **AUDITED — DECISION A. NOT PHYSICALLY EXECUTED.** 481 664 B; source-layer retention proved unbiased against the real assembler, target stop proved safe (after ACK and RE-ARM), no off-by-one at 2048, no filesystem in the capture path, 9/9 adversarials caught. **Reproduce with `GIT_COMMIT=10250a4 GIT_DIRTY= make build`** | `HARDWARE_TESTS.md` §V5.39, §V5.40 |
| GBP-VIDEO-004 **stimulus** | `indexed-0001` | — | `379df0f7019ef7f1330bd4ad55274bde062a69d03d1c8cc1dc2a01018bdbc543` | 2 460 B. **PHYSICALLY EXECUTED 2026-09-19 — INVALID FOR DECISIVE CLAIM** (FAULT from its first update, 14.9x over the VBlank budget). Historical; never rerun | `HARDWARE_TESTS.md` §V5.41; GBP-HW-157…159 |
| GBP-VIDEO-004 **stimulus** | `indexed-0002` | — | `44651f0ba60141f23cfb6b8b01f5b7a871ef1037412c7dae2ac9d9743c7b7b2f` | 2 876 B. **PHYSICALLY EXECUTED 2026-09-19 — TEARING FIXED (FAULT clear, VMARGIN 24, 0 mixed), but 2:1 CADENCE.** Historical; never rerun | `HARDWARE_TESTS.md` §V5.42; GBP-HW-160…166 |
| GBP-VIDEO-004 **stimulus** | `indexed-0003` | — | `37119bb6ac68398dbd3fa75e6ad5c51c8aeb543277ac8d3b03b57f7a6f0caaca` | 2 880 B canonical. **PHYSICALLY EXECUTED 2026-09-19 — PRODUCER CORRECT: 1:1 cadence, 0 duplicates, 0 mixed, FAULT clear, VMARGIN 24.** The verdict is `OBSERVED_DISCONTINUITY` on one startup-resync gap, not on the producer | `HARDWARE_TESTS.md` §V5.43; GBP-HW-167…174 |
| GBP-VIDEO-004 **stimulus, derived** | `indexed-0003` | — | `9f04916b88308e7045f207136f5fc681e5bab33ac9b22d2e19be12c16b8d9cc2` | 2 880 B; logo from the colour cartridge that booted twice, payload past 0x0C0 byte-identical to the canonical ROM. Never committed. The `indexed-0001` (`abb31e6a…0769`) and `indexed-0002` (`55fe72d5…e559e9`) delivery images are historical and must not be rerun | `HARDWARE_TESTS.md` §V5.42.10 |
| GBP-VIDEO-007 / -008 **stimulus** | `coord-0001` | — | `90343b64eda9602c173364171637cd1068f265c385464361b40ec073b11f0a1f` | 3 496 B canonical, `build/stimulus/agb-coord/agb-coord.gba`, built twice from scratch and byte-identical (the ROM embeds no commit). **PHYSICALLY EXECUTED 2026-09-20 (RUN 12, through its delivery image): the first run of OGBPCOORD1 — 2048 intact witness records, FAULT 0, VMARGIN 38/39/54, two duplicate FRAME_ID transitions (GBP-VID-034, mechanism RESOLVED by Issue #12 — PREPARE-side missed VBlanks at the digit-1 and digit-4 entry frames, §V6.22); not labelled a stimulus defect.** OGBPCOORD1: OGBPIDX1's witness bytes, an injective coordinate field, the 48×80 digit every 480 frames | `HARDWARE_TESTS.md` §V6.18.3 |
| GBP-VIDEO-007 / -008 **stimulus, derived** | `coord-0001` | — | `a769cc11afcb93cfc1cf89bf9bb59554533662c051e25b475f3943e7bdbb994f` | 3 496 B, `build/physical/agb-coord-cart.gba`; logo from the colour cartridge that booted twice, payload past 0x0C0 byte-identical to the canonical ROM (`tools/gbaderive.py`). Never committed. **FLASHED AND RUN 2026-09-20 (RUN 12); the operator's pre-flash `sha256sum` matched (Issue #9).** The cartridge was re-flashed with this exact image for RUN 12; the "do not re-flash" rule of runs 6–11 applied to `indexed-0003` only | `HARDWARE_TESTS.md` §V6.18.2 |
| **coord-0002 stimulus, canonical** — the timing-safe second implementation of OGBPCOORD1 | `coord-0002` | `74f9f4f` | `319dacb759dd2f78b420691a896387b727accf5d9483f152a6a096865c95093f` | 3 620 B, `build/stimulus/agb-coord2/agb-coord2.gba`, built twice from scratch and byte-identical (the ROM embeds no commit); copy versioned as `captures/fixtures/stimulus-coord-0002-canonical.gba`. **PHYSICALLY EXECUTED 2026-09-21 in RUN 13 through its delivery image (pre-registered §V6.24, ingested §V6.25): the shared source gate passed — no duplicate transition at any entry, §V6.22's expectation read off the data; one run consistent with the cycle model, not a calibration of it.** Same published picture as coord-0001 (word for word against the unchanged `tools/icoord.py` and against coord-0001, §V6.23.6); the ten digit tables are built at boot (80 000 B EWRAM, NOLOAD), the entry PREPARE selects one: every entry 86 972 cycles, 176 863 under the budget (§V6.23.4) | `HARDWARE_TESTS.md` §V6.23 |
| **coord-0002 stimulus, derived** | `coord-0002` | — | `276ad987c4cd0cefc7d7c532b86a7f5c336cf6603a32509f80f17aac9a56f700` | 3 620 B, `build/physical/agb-coord2-cart.gba`; logo from the colour cartridge that booted twice, payload past 0x0C0 byte-identical to the canonical ROM (`tools/gbaderive.py`). Never committed. **The RUN 13 delivery image: FLASHED (NOR / Mode B) and RUN on 2026-09-21 (Hardware Issue #15; §V6.25); the operator's pre-run hash matched.** Header title OPENGBPCOOR2 / code CGB2 tells it from coord-0001 in the cartridge menu | `HARDWARE_TESTS.md` §V6.23.1, §V6.24.2 |

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

**Phase 5's first physical runs are done and ingested (Issue #24,
`HARDWARE_TESTS.md` §V7.2):** RUN 14 and RUN 15 of the unchanged `stream-0014`
(`0ff8355`, SHA-256 `ef76a170…`) with the Enhanced Control Checker read
Question M = PASS and Question O = AS-ASSIGNED — the first KEYPAD words
Open-GBP wrote reached the cartridge as the presses made, L at L and R at R;
U-GBP-010 is CLOSED with the descriptor kept; the routing stays CORROBORATED,
not FACT, because the machine record holds 42 key changes and not which
buttons (GBP-HW-265). No blocker. Issues #24 and #25 are validated, Hardware
Issue #21 is closed, and the consolidated pages carry the keypad plane
(Issue #26: `docs/protocol/INPUT.md`; the keypad rows of `REGISTERS.md`,
`GBS-DOL.md`, `ARCHITECTURE.md`; `INITIALIZATION.md` §15) with the order stated,
since Issue #33, as a physical FACT (hw, the runs) with its history kept:
RUN 17 / RUN 18 / RUN 16 ran on `stream-0015` (Hardware Issue #32) and were
ingested as §V7.4 — the KEY record joined to the checker's counters closed
Question J = FACT for all ten KEYPAD word bits, bits 8 and 9 on two
controllers; U-GBP-010 stays CLOSED, now on a machine record; `truncated=0`
validated GBP-KEY-008's repair. The next front is Phase 5's real acceptance
with a commercial game, which the Operator schedules and which is not
pre-registered: the checker is a test ROM, and no game has been played
through the input path. Nothing below changed for Phase 4.

**No blocker for Phase 4. Phase 4 was assessed against its acceptance criterion on
2026-09-21 (GitHub Issue #17): SATISFIED WITH NAMED RESIDUALS — the verdict
is stated in `docs/ROADMAP.md` (Phase 4, "Phase 4 assessment") and in the
scientific-state table above, and the full argument, term by term with its
evidence ids, is `docs/research/PHASE4_ASSESSMENT.md`.** The current question
is the Orchestrator's and the Operator's: which phase opens next. The
ROADMAP's order puts Phase 5 (input) next; presentation and pixel-perfect
scaling are Phase 9 by the ROADMAP's own text and by the runtime's
(`poc/gbp-video-stream-probe/source/main.c`), and nothing in the assessment
moves them earlier. No run is pre-registered, no build is a physical
candidate, and the promoted pages (`docs/protocol/VIDEO.md` and the video rows
of `docs/hardware/` and `docs/protocol/REGISTERS.md`) carry only claims with
an id in `EVIDENCE.md`. What follows is the history of the last Phase-4 runs.

> **RUN 12 ran and is ingested: GBP-VIDEO-007 INCONCLUSIVE, GBP-VIDEO-008
> INCONCLUSIVE (§V6.20).** `stream-0013` at `7d7a6d8` (506 496 B, `5391c3fe…dd79`)
> with `coord-0001` ran on 2026-09-20 under Hardware Issue #9 on the declared
> topology, and the shared prospective source-window gate failed: frozen
> `tools/vindex.py` reads `OBSERVED_DISCONTINUITY` — 2048 intact records, FAULT 0,
> INVALID 0, and two duplicate FRAME_ID transitions (479→479, 1919→1919;
> GBP-VID-034, mechanism RESOLVED by Issue #12 — PREPARE-side missed VBlanks at the digit-1 and digit-4 entry frames, §V6.22). Everything else read clean; the subordinate
> full-frame analysis is PASS 8/8 and promotes nothing; the operator saw 1, 2,
> 3, 4 in order; the frozen VI reader's zero is an analyzer defect (GBP-VID-035,
> since REPAIRED in software by Issue #11, §V6.21 — the corrected post-run replay
> reads 2370/2370 and L = 40/40/38/40, changing no verdict). No rerun is
> pre-registered (GBP-HW-250…255).

**RUN 13 was EXECUTED (Hardware Issue #15, 2026-09-21) and INGESTED (§V6.25,
Issue #16): GBP-VIDEO-007 = PASS (CLAIM-D only) and GBP-VIDEO-008 = PASS
(CLAIM-A / CLAIM-B, the eight sampled frames only)** — the same two experiments
with `coord-0002` on the unchanged `stream-0013`, RUN 12's topology; the
shared source gate RUN 12 failed passed. Hardware Issue #15 stays open until
the Orchestrator validates the ingestion; no further run is pre-registered.
**GitHub Issue #6 designed
the next Phase-4 experiments (§V6): `GBP-VIDEO-007` (physical scanout) and
`GBP-VIDEO-008` (full-frame fidelity), two experiments that one run may serve
without conflating them. GitHub Issue #7 then built that design — IMPLEMENTED IN SOFTWARE, NOT PHYSICALLY EXECUTED, no run name reserved (§V6.18).**
The build (`stream-0013` at `7d7a6d8`, 506 496 B, `5391c3fe…dd79`), the
stimulus (`coord-0001`, contract `OGBPCOORD1`, canonical `90343b64…0a1f`,
delivery `a769cc11…994f`), the two new sidecars (`OGBPFULL1 v1`, `OGBPVI1 v1`)
and the offline tools (`tools/icoord.py`, `tools/vfull.py`, `tools/vvi.py`)
exist with frozen software identities; the XFB-region CRC of the design was
dropped by decision (CLAIM-B stops at the converted texture); K = 8 samples
every 256 frames fit with `arena1_free=1658880`; the embedded TEST_ID stays
`GBP-VIDEO-004`. **GitHub Issue #8 PRE-REGISTERED RUN 12 (§V6.19)** — the operator's display
chain (composite / RCA → low-cost RCA-to-HDMI converter at 1080p → HYDIS
HV150UX2 panel, M.NT68676.2A controller, a custom iMac G3 modification —
recorded as topology, never as a fidelity claim), the same console and GBP as
runs 10–11 with BBA PRESENT / Ethernet DISCONNECTED, the five raw names, and
the gates and verdicts of GBP-VIDEO-007 and GBP-VIDEO-008, fixed prospectively
and independently. **Hardware Issue #9 executed RUN 12 on 2026-09-20 and Issue
#10 ingested it (§V6.20): both verdicts INCONCLUSIVE for the one shared
reason — the frozen source analyzer reads `OBSERVED_DISCONTINUITY`, two
duplicate FRAME_ID transitions in 2048 otherwise intact records.** What the run
did establish is kept as exactly what it is: the K = 8 full-frame samples match
the injective oracle in all 38 400 words each and the texture matches the
Python, the C and the tiled conversion (subordinate, GBP-HW-252); the operator's
literal report of 1, 2, 3, 4 in order (GBP-HW-254); clean transport, startup
and Policy A (GBP-HW-253); the OGBPVI1 container facts (GBP-HW-255) with the
frozen reader's 0/2370 explained by GBP-VID-035 (the address was masked before
the flag shift; the raw unmasked cross-check is 2370/2370 — an analyzer defect,
repaired in software by Issue #11, §V6.21: the corrected replay derives
L = 40/40/38/40, the two R_3 hand-overs outside L_3 being SUPERSEDED in the raw
file). The future Morph 2K paths (S-Video primary, Bitfunx composite
alternate, Samsung Q80T) are different topologies and are not part of RUN 12.
**GitHub Issue #5 closed
the three items carried to the next functional checkpoint — F3, F8, F5 —**
in software (§V5.59): every audit now declares and rebuilds what it consumes,
`tools/poc_audit.py` sees data relocations, and the indexed stream experiment
has exactly one success condition. The resulting `stream-0012` was the
software-only candidate and is now superseded by `stream-0013`: neither has
been physically executed, and no run is pre-registered for either.

**What run 11 changed, and only that:** the reporting defect two physical runs
had demonstrated is now repaired on hardware, for this controlled run. Runs 9
and 10 keep `truncated=1` as `stream-0010` facts and are interpreted by the
counter derivation as before; run 11 needs no derivation. `gbp_vwitness.*`,
every frozen tool and format, transport, display, startup, Policy A and the
5000 ms threshold are byte-identical to `stream-0010`.

**Established and unchanged:** GBP-BBA-001 / RUN 10 PASS — the BBA-present /
Ethernet-disconnected baseline within its exact scoped control, now with a
second run (11) on the same topology and a different build; the normal
startup (runs 7–11); Policy A on six runs; the not-before gate (runs 9–11).
Not established: Ethernet-connected behaviour, BBA initialisation, networking,
network code. Phase 11 does not move.

**And the slice position is still PLAUSIBLE BUT UNMEASURED as a property**,
carried unchanged: 27.88 / 33.60 / 41.06 µs and 28.32 / 34.07 / 41.33 µs,
yielding 24.95 % / 25.01 %, pre-streaming window median **42.8** µs, p25
**1.9** µs. Runs 7–10 showed no transport failure; a run without a failure
still does not measure the margin.

## Next safe action

**Issue #41 (2026-09-21) PRE-REGISTERED RUN 21 and RUN 22
(`HARDWARE_TESTS.md` §V7.6, GBP-INPUT-004): `play-0001`'s first runs, the
Phase 5 acceptance pair on a real game — three candidates named, the Operator
declaring at run time which he used — on both pads, with Question T, the
timing of the shortened service pass, on the same runs under a separate gate. NOT RUN, NOT
AUTHORISED there, NOT STAGED. The next safe action is the Orchestrator's:
validate the pre-registration against `origin/main`
(`tests/host/test_run21_prereg.py`), obtain the Operator's two gate items
(the cartridge declaration; that holding Z for 250 ms is workable), and open
the Hardware Issue that stages Swiss slot `13-play` onto the SD and moves RUN
21 and then RUN 22 to him.**

**Issue #39 (2026-09-21) BUILT the playable image `play-0001` (`2e48ca7`,
SHA-256 `d0ee3c29d04254d1b86d4f006291008876b5e886e07280d0421b7c1161c499de`): NOT RUN, not staged, not
pre-registered there; its runs are pre-registered by Issue #41, above.**

**RUN 14 and RUN 15 are EXECUTED, INGESTED and VALIDATED (Hardware Issue
#21 closed; Issues #24 / #25; `HARDWARE_TESTS.md` §V7.2): M = PASS, O =
AS-ASSIGNED, both runs — and PROMOTED (Issue #26): `docs/protocol/INPUT.md`,
the keypad rows of `REGISTERS.md`, `GBS-DOL.md` and `ARCHITECTURE.md`, and
`INITIALIZATION.md` §15, with the L/R order stated as CORROBORATED, not FACT,
and the generic-pad scope beside it.** **Issue #27 (2026-09-21) implemented
GBP-KEY-009 and repaired GBP-KEY-008 in `stream-0015` (`da06500`, SHA-256
`dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49`) — EXECUTED 2026-09-21.** **Issue #28
(2026-09-21) pre-registered RUN 17 / RUN 18 (GBP-INPUT-002,
`HARDWARE_TESTS.md` §V7.3); Hardware Issue #32 ran them, and RUN 16, the same
day; Issue #33 ingested all three as §V7.4: THE ROUTING IS FACT (hw, the
runs).** The next safe action is the Orchestrator's: validate the ingestion
against `origin/main` (`tests/host/test_run17.py` — the join recomputed from
the versioned fixtures, every KEY line verbatim; §V7.1 / §V7.2 / §V7.3
untouched; GBP-KEY-004 and the consolidated pages promoted with history),
then (Hardware Issue #32 CLOSED; the BBA / Ethernet / display-chain
declaration for these runs recorded under Issue #35 — two STANDING
declarations, cited from now on instead of asked) design Phase 5's
acceptance run with a commercial game — its PAIR (Issue #34; `HARDWARE_TESTS.md`
§V7.5, RUN 19 / RUN 20, GBP-INPUT-003) was pre-registered, AMENDED and then
WITHDRAWN BEFORE HARDWARE under Issue #37: the routing does not depend on
the pad, a checker run on the other pad repeats what §V7.4 already holds, and
the Operator's own criterion "ambos os controles funcionam e tem que
apresentar o mesmo comportamento" will be answered by his report on a game;
the ROADMAP's acceptance stays open and unscheduled (a game that passes
through the button path, and the build change assessed in §V7.5.3 and not
made). The next safe action is the Orchestrator's — validate the withdrawal,
close Hardware Issue #36 as withdrawn-before-execution, and, when the
Operator has a game, write the real-game run's own contract (and the
input-session build's, if it is to be made). Whether Phase 5 then closes is
an assessment step of its own (Issue #17's precedent), and it is further
away, not nearer. The
`desc_status=CORROBORATED_not_FACT` label the runtime prints is now stale — a
one-line label change in a future build, recorded, not made.

**Phase 4 is assessed (Issue #17, 2026-09-21: SATISFIED WITH NAMED
RESIDUALS, `docs/research/PHASE4_ASSESSMENT.md`).**
The next safe action is the Orchestrator's: validate the assessment and the
promotion against `origin/main`, then hand the Executor the next bounded Issue
for whichever phase the Operator chooses — Phase 5 (input) is the ROADMAP's
next; Phase 9 (presentation, GBP-VID-032) is not opened by Phase 4's closure
and crossing to it needs the blocking-feasibility justification `CLAUDE.md`
§26 demands. The residual that Phase 7 owns — correctness of retail content by
measurement — is named, not scheduled. Nothing below this paragraph is
pending; it is the Phase-4 trail.

**No physical run is pending and none is pre-registered.** Issues #3 and #4
established the GitHub workflow (remote, milestones, labels, templates, the
Project "Open-GBP Development" at https://github.com/users/zenaror/projects/2);
Issue #5 closed F3 / F8 / F5 (§V5.59); Issue #6 wrote the design of the next
Phase-4 experiments, `HARDWARE_TESTS.md` §V6 — `GBP-VIDEO-007` (physical
scanout, an operator observation bound to hand-over and VI-latch records) and
`GBP-VIDEO-008` (full-frame fidelity of the source → texture projection against
an injective coordinate oracle); Issue #7 implemented that design in software
(§V6.18): `stream-0013` at `7d7a6d8`, `coord-0001`, `OGBPFULL1 v1`, `OGBPVI1 v1`
and the offline tools, all with frozen software identities, NOT PHYSICALLY
EXECUTED; Issue #8 pre-registered RUN 12 for them (§V6.19); Hardware
Issue #9 executed it and Issue #10 ingested it (§V6.20): GBP-VIDEO-007
INCONCLUSIVE, GBP-VIDEO-008 INCONCLUSIVE, the shared source gate failed on two
duplicate FRAME_ID transitions (GBP-VID-034, mechanism RESOLVED by Issue #12 — PREPARE-side missed VBlanks at the digit-1 and digit-4 entry frames, §V6.22); the VI reader's
address-domain defect (GBP-VID-035) was REPAIRED in software by Issue #11
(§V6.21) with the corrected post-run replay reading 2370/2370 and
L = 40/40/38/40 — no verdict changed. The sequence after this is the
Orchestrator's, after independently validating the persisted evidence and
closing Issue #9: validating the GBP-VID-034 root cause (§V6.22: the entry
PREPARE of the sparse digits runs past the VBlank; a cycle model of the frozen
image reproduces the run's M--M pattern with no fitted parameter, the R_2 / R_3
margin stated at 0.8 % / 1.5 %); `coord-0002` — the timing-safe
re-implementation, implemented by Issue #13 and proven on its exact image
(§V6.23: every entry PREPARE 86 972 cycles, 176 863 under the budget, zero ROM
reads, the same picture as coord-0001 word for word) — ran once: Issue #14
pre-registered RUN 13 for it (§V6.24), Hardware Issue #15 executed it on
2026-09-21 and Issue #16 ingested it (§V6.25). The shared source gate passed
(`OBSERVED_CONTIGUOUS`, the four entries +1); GBP-VIDEO-008 = PASS for the
eight sampled frames (CLAIM-A / CLAIM-B); GBP-VIDEO-007 = PASS as CLAIM-D
(the corrected `tools/vvi.py` L = 40/40/39/40 beside the operator's 1-2-3-4).
The sequence after this is the Orchestrator's: independent validation of the
ingestion and the closing of Hardware Issue #15, then the next Phase-4 design
(presentation and pixel-perfect scaling, GBP-VID-032, remain future work; a
Morph 2K topology needs its own declaration and pre-registration). Scanout
(CLAIM-D) and fidelity for eight sampled frames (CLAIM-A / CLAIM-B) are now
experiment results of RUN 13 inside those boundaries and nothing wider; RUN
12's subordinate 8/8 stays what it was, evidence and never a verdict. Presentation and pixel-perfect scaling were NOT started;
`stream-0012` is superseded, never run.

```text
run 11      ingested; GBP-VIDEO-006 PASS; GBP-VID-033 PHYSICALLY VALIDATED (§V5.58.9)
issue 5     F3 / F8 / F5 CLOSED in software (§V5.59); stream-0012 NOT PHYSICALLY EXECUTED
issue 6     GBP-VIDEO-007 / -008 DESIGNED (§V6)
issue 7     GBP-VIDEO-007 / -008 IMPLEMENTED IN SOFTWARE (§V6.18): stream-0013 @ 7d7a6d8,
            coord-0001, OGBPFULL1 v1, OGBPVI1 v1, tools; NOT PHYSICALLY EXECUTED
issue 8     RUN 12 PRE-REGISTERED (§V6.19): identities, five raw names, topology, gates, verdicts
issue 9     RUN 12 EXECUTED 2026-09-20 by the Operator (hardware Issue; the Orchestrator closes it
            after validating the persisted evidence)
issue 10    RUN 12 INGESTED (§V6.20): GBP-VIDEO-007 INCONCLUSIVE · GBP-VIDEO-008 INCONCLUSIVE
            (frozen vindex OBSERVED_DISCONTINUITY, two duplicate FRAME_IDs: GBP-VID-034);
            vfull PASS 8/8 subordinate; operator saw 1 2 3 4; vvi.py defect GBP-VID-035 found;
            GBP-HW-250..255; fixtures + tests/host/test_run12.py; NOTHING FIXED, NO RERUN
issue 11    GBP-VID-035 REPAIRED in software (§V6.21): tools/vvi.py compares in the full physical
            domain (libogc2 __setFbbRegs rule cited from source); corrected post-run replay of the
            RUN 12 OGBPVI1: 2370/2370 top, 2370/2370 bottom, L = 40/40/38/40; verdicts unchanged;
            the frozen-at-run 0/2370 kept as history; no fixture, format, runtime or gate change
issue 12    GBP-VID-034 MECHANISM RESOLVED (§V6.22): tools/coordtime.py, a cycle model of the frozen
            coord-0001 image calibrated on the run's VMARGIN 54/39/38 -- the digit-1 and digit-4 entry
            PREPAREs (287 787 / 287 179 cycles) exceed the 263 839..263 953 budget and skip a VBlank
            (N-1 captured twice, FAULT blind to it); digits 2/3 (261 723 / 260 043) do not; M--M with
            no fitted parameter; verdicts unchanged; research only, nothing changed, no RUN 13
issue 13    coord-0002 IMPLEMENTED (§V6.23): a new stimulus identity, the same OGBPCOORD1 picture
            (word for word vs tools/icoord.py and vs coord-0001), the ten digit tables built at boot
            (80 000 B EWRAM NOLOAD), entry PREPARE = 86 972 cycles for every digit, 176 863 under
            the budget, zero ROM reads; canonical 319dacb7… 3 620 B, delivery 276ad987… (not
            flashed); coord-0001 untouched; NOT PHYSICALLY EXECUTED, no RUN 13
remote      origin = GitHub (canonical); gitea-archive = Gitea (archive, no push)
issue 14    RUN 13 PRE-REGISTERED (§V6.24): GBP-VIDEO-007 / -008 with coord-0002 (319dacb7… /
            276ad987…) on the unchanged stream-0013 (5391c3fe…), verified on disk, NOT rebuilt;
            five …-run13… names reserved; RUN 12's topology; source gate first; corrected vvi.py;
            (NOT RUN at that checkpoint)
issue 15    RUN 13 EXECUTED 2026-09-21 by the Operator (Hardware Issue): coord-0002 delivery 276ad987… on
            NOR / Mode B, the same stream-0013; five raws + literal report + topology declaration
            returned; stage:validation, OPEN -- the Orchestrator closes it after validating the ingestion
issue 16    RUN 13 INGESTED (§V6.25): source gate OBSERVED_CONTIGUOUS (2046/2046 +1) -> ADMISSIBLE;
            GBP-VIDEO-007 = PASS (CLAIM-D) · GBP-VIDEO-008 = PASS (CLAIM-A/B, eight frames);
            GBP-HW-256…260; fixtures + tests/host/test_run13.py; RUN 12 untouched
issue 17    PHASE 4 ASSESSED: SATISFIED WITH NAMED RESIDUALS (docs/research/PHASE4_ASSESSMENT.md;
            ROADMAP Phase 4 "Phase 4 assessment"); promotion with ids into docs/protocol/VIDEO.md and
            the video rows of docs/hardware/ and docs/protocol/REGISTERS.md; no status promoted, no id
            minted, no unknown closed, no run re-judged; docs and tests only
issue 18    PHASE 5 ENTERED, research / design only (docs/research/INPUT_PATH.md): L1 / L2 / L3 kept
            apart; reference survey with provenance (Enhanced mGBA obtained: external/mgba @ 8692b26b);
            U-GBP-010 static attempt = RESOLVED STATICALLY at CORROBORATED (Disc, GBI, Dolphin agree:
            L at bit 8, R at bit 9, the reverse of KEYINPUT), NOT closed, no order adopted; input
            architecture on paper behind the transport boundary, in the pump slot; latency
            observability guaranteed, nothing instrumented; GBP-KEY-002…005 (static); no KEYPAD write
issue 19    INPUT PATH IMPLEMENTED, software-only: src/gbp/gbp_input.c (policy table, ONE descriptor
            filled CORROBORATED by the Operator's decision, one 32-byte write, change + 5 ms refresh),
            first statement of the stream probe's pump slot, 8 453 C checks + Python pins; candidate
            stream-0014 = 0ff8355, 513 152 B, sha256 ef76a170...0b9c, 0 warnings, audit clean,
            Dolphin PASS (auxiliary; the slot never ran); NOT EXECUTED, no run pre-registered;
            GBP-KEY-006 (software facts); no GBP-HW id
issue 20    RUN 14 / RUN 15 PRE-REGISTERED as GBP-INPUT-001 (HARDWARE_TESTS §V7.1), NOT RUN: Question One
            answered from the code (the witness target ends a run ~40.4 s after CONTROL and tears the device
            down; two staged runs of the same stream-0014 image, RUN 15 conditional on RUN 14); Swiss slot
            12-stream reused with stream-0013 preserved first and reproducible from 7d7a6d8; ten names
            reserved; recovery procedure frozen; FAIL reachable, SWAPPED informative; U-GBP-010 restated,
            OPEN; no hardware, no flash, no build, no GBP-HW id
issue 21    HARDWARE ISSUE, orchestrator-owned: RUN 14 (RUN 15 conditional) moved to the Operator; the
            Executor performed steps 1-3 of §V7.1.6 on the host (stream-0013 preserved as
            build/archive/gbp-video-stream-probe-stream-0013-7d7a6d8.dol 5391c3fe...dd79; make swiss without a
            rebuild; build/swiss/12-stream/boot.dol = 513 152 B ef76a170...0b9c, INDEX row stream-0014 /
            0ff8355); step 4 (the SD) is the Operator's; not run at the time of this line
issue 22    OPERATOR INPUTS RECORDED outside the frozen §V7: the homebrew input-test ROM rejected against
            the window (INPUT_PATH §10.1); the Start-up Disc recollection corroborating the L3 policy and
            its composition (Y -> bit 8 static + Y acts as L observed => bit 8 = L) evaluated as OPERATOR
            OBSERVATION / recollection, GBP-KEY-007; U-GBP-010 OPEN, descriptor unchanged, §V7 byte-identical
issue 23    PRE-HARDWARE AMENDMENT of §V7.1: the Enhanced Control Checker GBA (76924c13..., prebuilt 69 348 B
            53c212c7...; the Operator's media on the EZ-Flash NOR, booted straight into; nothing enters the repo;
            AGS as fallback) is the instrument of the FIRST executed run -- RUN 14 = walk A L1 R2 A3 B4 SELECT5
            START6, RUN 15 = walk B L1 R2 UP3 DOWN4 LEFT5 RIGHT6 (21 presses each; 55 in one window fits only at
            2/s with ~3 s to spare), the EZ-Flash menu tabs = the OPTIONAL, independent RUN 16; the single-press
            walk forbidden (its end state cannot see a permutation); two channels (live row + final vector);
            verdicts read from the vector; run numbers = order of execution, names reassigned explicitly; Hardware
            Issue #21 authorises RUN 14 and is the Orchestrator's to align; the Operator's unregistered incomplete
            trial recorded for what it is (hazard did not occur; prior exposure; optional photo of the final tally
            screen; trial leftovers on the SD moved aside); Question One, the shared gates, the recovery procedure
            and the U-GBP-010 part byte-identical to 848007a; U-GBP-010 OPEN; no GBP-HW id
issue 21    (continued) RUN 14 and RUN 15 EXECUTED 2026-09-21 by the Operator on the staged stream-0014 with the
            checker on the NOR; ten raw files moved to logs/ (RUN 15 into logs/run15/) and archived FIRST by the
            Executor under the reserved run14 / run15 names, hashes matching the Orchestrator's; stage:validation
issue 24    RUN 14 / RUN 15 INGESTED (§V7.2): Question M = PASS · Question O = AS-ASSIGNED, both runs, read from
            §V7.1.9 as frozen; INPUT 7 892 / 7 895 completed, failed 0, 42 key changes each; truncated=1 = the
            ENVINPUT clip (GBP-KEY-008); the Operator's vectors and the frame-decoded vectors agree digit for digit,
            recorded apart (blank = never incremented, recorded); U-GBP-010 CLOSED, descriptor kept; the routing
            CORROBORATED, not FACT; the one-log-line finding (GBP-KEY-009, not implemented); GBP-HW-261...265;
            fixtures (the tally frames byte-identical) + tests/host/test_run14.py; §V7.1 byte-identical; no code
issue 25    TOPOLOGY DECLARATION recorded (§V7.2.2, GBP-HW-261; the scope in §V7.2.1 and GBP-HW-265): given after
            the runs -- same GameCube; BBA connected without a network cable ("BBA conectado sem cabo de rede");
            video chain unchanged; a GENERIC third-party controller (the official pad owned, NOT used) -- the L / R
            result is a third-party pad's digital click, encouraging and a limit; the Game Boy Player first NOT
            SEPARATELY DECLARED, then DECLARED the same day by the Operator's hardware inventory (exactly one GameCube,
            exactly one GBP -- a declaration, not an inference); struct fixtures regenerated for that section only; no
            verdict, gate or status change
issue 26    PROMOTION of the input path into the consolidated documentation: docs/protocol/INPUT.md (window,
            word, polarity, bit assignment with its status, cadence, the mapping as POLICY, not established);
            INITIALIZATION.md "KEYPAD, never written" superseded on its date with a §15; REGISTERS.md KEYPAD row
            and §2.3 -- the L/R order C, not FACT, was H until 2026-09-21; GBS-DOL.md and ARCHITECTURE.md keypad
            rows refreshed (ARCHITECTURE's "active-low" contradicted GBP-KEY-001 / 005: fixed to 1 = pressed);
            VIDEO.md pointer dated; indexes; the generic-pad scope and GBP-KEY-009 beside every statement of the
            order; no status changed, no id minted, §V7 untouched; tests/host/test_input_promotion.py
issue 27    GBP-KEY-009 IMPLEMENTED and GBP-KEY-008 REPAIRED, software-only: one KEY ringlog line per first /
            change / retry write (word, logical set, t_poll / t_attempt / t_done in the sidecars' ticks64 base;
            worst case 158 of 248), emitted from the pump slot after the write, bounded by the ringlog with a
            64-line reserve (KEYLOG counts lost / truncated / overwritten; dropped stays 0); ENVINPUT + ENVINPUT2
            (229 / 222); tests/host/test_ringlog_payloads.py -- the GENERAL payload guard (strict for the owned
            records, a ratchet for four older ones); candidate stream-0015 = da06500, 514 880 B, sha256
            dd545c01cfa99ee2437cd3a53fad44cb01439e3c794991c8cae94407373a3d49, zero warnings, none suppressed; two consecutive clean builds byte-identical, audit 0 findings (the ext and base one-shot handlers identical to the physically validated GBP-VIDEO-001 build), Dolphin auxiliary only (the slot never runs there); NOT executed,
            no run name, NOT staged; the descriptor and the policy unchanged; GBP-KEY-010; no GBP-HW id
issue 28    RUN 17 / RUN 18 PRE-REGISTERED as GBP-INPUT-002 (HARDWARE_TESTS §V7.3), NOT RUN: Question One answered
            from the code and RUN 14 / RUN 15's data before any gate -- per-press join NOT supported by K = 8 every
            256 frames; the interval-wise join a consistency check only (within an interval the counts are not
            distinct: RUN 14 R +2 and B +2, RUN 15 R +2 and DOWN +2); the WHOLE-RUN join binds by the distinct
            totals, FACT reachable per bit, no timing, no pacing (pacing EXCLUDED), latency out of reach; numbering
            resolved (RUN 16 keeps the menu reading and its names; RUN 17 walk A, RUN 18 walk B, ten names reserved);
            stream-0014 preserved to build/archive/ first, reproducible from 0ff8355, SD path and hash dd545c01...3a49
            in the checklist, staging not performed; recovery procedure byte-identical; verdicts per bit FACT /
            FACT-SWAPPED / NOT CLOSED (informative, a failed join reachable) / UNDECIDED / INCONCLUSIVE; the
            Operator's channel beside, never merged; INPUT.md's "not implemented" corrected on its date in its own
            commit (the routing still C); no GBP-HW id; no code; no build; no staging
issue 32    HARDWARE: stream-0014 preserved to build/archive/ (ef76a170...0b9c) and stream-0015 staged into
            build/swiss/12-stream/ without a rebuild (the Executor, verified by the Orchestrator); the Operator ran
            RUN 17 (walk A, generic pad, 14:13), RUN 18 (walk B, ORIGINAL pad, 14:19) and RUN 16 (the menu reading,
            ORIGINAL pad, 14:22); fifteen raw files archived with cp --update=none / cmp / sha256 from the copies
            (RUN 16 first under a provisional name, then renamed to the stream-0015-run16 names by the
            Orchestrator's resolution; the stream-0014-run16 names retired, never used)
issue 33    RUN 17 / RUN 18 / RUN 16 INGESTED as HARDWARE_TESTS §V7.4 against §V7.3's frozen gates: the join
            recomputed from the KEY record and the tally frames -- R_b per bit, the end state, T_c, Question J per
            bit = FACT for all six bits of each join run (bits 8 / 9 on two controllers), Question I EXACT x16, the
            channels agreeing and kept apart; RUN 16 UNDECIDED by the rule (R_8 = R_9 = 8), M = PASS, O NOT READABLE
            (not inferred); truncated=0 x3 = GBP-KEY-008 validated; KEYLOG 43/43/33 lost 0; BBA / chain NOT declared
            (recorded absent); the boot-logo / parity observation recorded as OPERATOR OBSERVATION (GBP-HW-271);
            GBP-HW-266...271; GBP-KEY-004 promoted by its falsifier's outcome; U-GBP-010 stays CLOSED; the
            consolidated pages moved to F (hw, run-scoped) with history; fifteen fixtures; tests/host/test_run17.py
            recomputes everything; §V7.1 / §V7.2 / §V7.3 byte-identical; no code, no build, no gate change
issue 35    the RUN 16 / 17 / 18 topology declaration recorded with its history (at ingestion recorded absent, not
            inferred; declared the same day after the ingestion): BBA PRESENT without the Ethernet cable, display chain
            UNCHANGED; two STANDING declarations in the Operator's words (the chain "ate que eu anuncie o contrario"; the
            BBA "ate que seja solicitado para remover ou conectar o cabo") -- declarations WITH A STATED DURATION, cited
            by future pre-registrations, never a licence to infer; per-run declarations reduce to the cartridge / boot
            screen and the controller; §V7.4.2 / V7.4.4 / V7.4.10, GBP-HW-266 addendum, the three struct fixtures'
            topology block, "Do not rediscover"; no verdict, gate, status or id; no code
issue 34    RUN 19 / RUN 20 PRE-REGISTERED as GBP-INPUT-003 (HARDWARE_TESTS §V7.5), NOT RUN: the Phase 5 acceptance pair --
            the criterion in the Operator's words, read in his terms and not reinterpreted; a pair (the generic pad, the
            original pad) with the same literal 13-step / 19-press action list covering all ten keys, sized for the
            ~40 s window of a stream-0015 session (recorded; a longer session = a build change, not proposed); W
            ("funcionam") per pad and S ("o mesmo comportamento") for the pair from his per-step reports; K, the machine
            half, from the two KEY records (press sequences; AGREE / EXPLAINED / FINDING / INCONCLUSIVE), beside W / S,
            never merged; failure reachable and informative (DOES NOT WORK / DIFFERENT / FINDING); the cartridge and its
            status (original / unofficial / a ROM from the EZ-Flash) declared before each run -- WarioWare ORIGINAL
            recommended with the reason, Road Rage unofficial named with the caveat, the Operator's "ez-flash e o road
            rage paralelo" sentence recorded as a relayed intention with its ambiguity; the standing declarations cited;
            ten names reserved; Phase 5's closure NOT decided; no code, no build, no id
issue 37     §V7.5 AMENDED BEFORE HARDWARE (Issue #23's precedent; dated, never silent): WarioWare: TWISTED evaluated and
            REJECTED (the gyroscope title; most interaction bypasses the button path; the "WarioWare original"
            recommendation withdrawn -- the title matters, not the originality); the instrument is the Enhanced Control
            Checker: RUN 19 = walk A on the ORIGINAL pad, RUN 20 = walk B on the GENERIC pad, completing the walk x pad
            matrix with RUN 17 / 18 -- W per key by §V7.3.9's join, S per key across pads, K the word level, the
            Operator's channel beside; the two criteria kept apart (the checker answers HIS, never the ROADMAP's; Phase
            5 stays NOT ASSESSED and its closure is further away); the build change assessed from the source and NOT
            made (the one success stop GBP_VWITNESS_TARGET 2048; the safety cap 60 s and delivery cap 400 000 would
            end an unbounded run as failures; the witness can be UNBOUND, null-safe, freeing 8.85 MB; the OGBPFULL1
            origin must move off the witness; the KEY record survives; the disp / vi traces overflow past ~68 s,
            counted; ~40 s is enough for the checker, a real game needs the build); the 13-step game list superseded
            for this pair; frozen kept: the criterion's words, the status axis, the standing declarations, the recovery
            block, the ten names, §V7.1-§V7.4; no code, no build, no id
issue 37    (continued) RUN 19 / RUN 20 WITHDRAWN BEFORE HARDWARE on the Operator's objection (the checker had served every
            controller test already), accepted by the Orchestrator: the routing does not depend on the pad (J reads
            word -> counter; the pad is upstream of the word), so the walk x pad matrix informed the routing not at all
            -- the framing was the Orchestrator's, accepted unchecked, compounded by the Executor's "every button
            machine-read on both pads", caught by the Operator; what is given up recorded (the D-pad on the generic pad
            with a human-count link only, RUN 15; A / B / SELECT / START on the original pad with no reading; the
            equivalence criterion answered on a game by his report); the ten names RETIRED, the numbers consumed (next
            run 21); the amendment had landed (ad4151e, ba8edb7) before the stop, so the withdrawal sits on top, dated;
            everything else of #37 kept; Hardware Issue #36 closed by the Orchestrator as withdrawn-before-execution
issue 38    the runtime image fit for a game ASSESSED, NOT BUILT (INPUT_PATH.md §12): the subtraction of the witness, the
            full-frame sampler and the VI trace is clean (cfg.witness = NULL, null-safe stops; ~11 MB freed; the origin
            dependency goes with the sampler; the input path and the KEY record byte-identical) but it touches pump()
            and submit_ready() textually and, decisively, leaves NO SUCCESS STOP: the safety budget (60 s), the frame
            store cap (16384 frames = 274 s) and the delivery cap (400 000, ~63 s) all end the run as "gone wrong",
            finish() scores them all OK_NO_CHANGE_INCONCLUSIVE, gbp_vstate_main_status reports ok_structured_change_
            observed either way, the pump hook is void and the config has no session field; a usable image needs a
            success stop in CHECK_ADMISSION (a new stop reason, an operator end on Z or a session target), raised caps,
            a larger frame store or a stated 274 s bound, a larger ringlog (~350 presses at 1024 lines), a new POC with
            its own Makefile, BUILD_ID, poc_audit profile, Dolphin conditions and Swiss number, and its own
            pre-registration -- a REDESIGN, stopped per the Issue's rule; no code, no build, no id
issue 39    THE PLAYABLE IMAGE BUILT, NOT RUN: play-0001 = 2e48ca7, 487 968 B, sha256 d0ee3c29d04254d1b86d4f006291008876b5e886e07280d0421b7c1161c499de,
            zero warnings, none suppressed; two from-scratch builds byte-identical; play-audit 0 findings (handlers
            identical to GBP-VIDEO-001's; the `play` profile finds 105 things wrong with the stream image, the `stream`
            profile 33 with this one); Dolphin PASS on the absent-device path with the ceiling stated. stream-0015's
            runtime minus the witness (never bound), the sampler, the VI trace, the disposition trace and the sidecars;
            keylog_emit / input_step byte-identical; Policy A and the GX order unchanged (the lines that moved are
            enumerated in INPUT_PATH.md §13.2); the session end on Z (250 ms hold) as the only success -- a new stop,
            status and config field in the service-path module, read once per admission after the safety budget and
            the store caps, unit-tested through the real run loop; sized for 720 s (45056 frame records, 16384 events,
            6 M deliveries, 8192 log lines with a 640-line reserve, the costs stated); the service pass shorter by the
            witness step, UNCHECKED until the first run; U-GBP-035 opened; a finding about stream-0015's 64-line reserve
            recorded, not acted on; the freeze-guard pins of nine earlier checkpoints moved with their reasons
issue 41    RUN 21 / RUN 22 PRE-REGISTERED as GBP-INPUT-004 (HARDWARE_TESTS §V7.6), NOT RUN, NOT STAGED: play-0001's
            first runs, TWO QUESTIONS on ONE pair with SEPARATE GATES (§V6.13) -- A = Phase 5's acceptance in the
            Operator's terms (W / S / K, his report as the game's channel, the KEY record beside it splitting a "did
            not work" into SENT and NOT SENT, which is the one honest half a game leaves the machine) and T = the
            timing of the shortened service pass against RUN 17's figures, whose FAULT is an EXPECTED POSSIBLE
            OUTCOME; ONE interaction frozen (no session -> A inconclusive too), otherwise neither reads the other's
            evidence. THREE CANDIDATES named before the run, the Operator declaring at run time which he used and in
            which form, the same in both runs: WarioWare NORMAL (a ROM on the NOR; crispest feedback; L / R / SELECT /
            B expected N/A), Pokemon Emerald (his note: uses L and R; most keys, softer judgement; its RTC possibly
            absent or emulated from a flashcart, which touches berries and tides and NOT input), Yoshi's Island (his
            BELIEF about L and R, recorded as his statement, not asserted). Each one's cartridge hardware CHECKED,
            not presumed; the attribution caveat beside the verdicts unless he declares an original; Twisted stays
            rejected and is recorded as owned original, JP and US. The choice got easier because Issue #39 removed
            the ~40 s window.
            RUN 21 = ORIGINAL pad, RUN 22 = GENERIC pad. The list leans on ORDINARY PLAY with a deliberate head and
            a closing sweep, in the SEPARATED NOTATION (button and count apart, × and whitespace, dual names) -- its
            first use, the frozen lists untouched; L / R / SELECT / B expected N/A, and N/A is an answer. The session
            is the Operator's (Z ~1 s -> stop=session_end, the only success; the whole session inside 720 s). Two raw
            names reserved (one file per run, no sidecars). Two gate items for the Operator. The 105 -> 102 audit
            figure of #39 corrected (INPUT_PATH.md §13.8). Phase 5's closure NOT decided; nothing staged, no id
issue 43    HARDWARE (open): 13-play STAGED and hash-verified -- build/swiss/13-play/boot.dol and
            /media/rafael/SD_GC/Open-GBP/13-play/boot.dol both d0ee3c29...99de, 487 968 B, the hash read back FROM
            the card after sync; 12-stream untouched on both copies (dd545c01...3a49 before and after); no leftover
            console log on the SD; INDEX.txt row added in the exporter's format. `make swiss` was NOT used and must
            not be: it re-exports EVERY slot from build/poc, whose stream probe is now a rebuild at 2e48ca7
            (19666b54...), so the documented staging command would have overwritten the frozen 12-stream silently
            (recorded on #43 and on #29 as a fourth instance). Nothing else on the card was touched; the runs are
            the Operator's
issue 29    THE GUARD BLIND SPOTS, written properly: tests/host/guards.py is the ONE implementation of every
            "nothing moved" question (git diff UNIONED with the untracked list; the ignored paths excluded by design
            and documented where the function is), thirteen files converted, and test_guard_shape.py fails any host
            test that asks git directly -- and PROVES the property by writing an untracked file under a guarded path
            and showing git diff alone misses it. test_staged_artifacts.py covers what the five artifact-identity
            skips stopped covering and CANNOT skip when a slot exists (INDEX consistency, the frozen slots against
            the documented hashes, the hashes required to still be quoted in the documents, the SD when mounted; a
            missing INDEX with slots present is a FAILURE). skip_ledger.py registers all 63 skip reasons over 217
            sites in eight classes, each with what covers the risk; the dangerous class IDENTITY_NOT_CURRENT must
            name its cover; enforced statically (any runner) and at run time (conftest fails the pytest session on
            an unregistered reason -- verified by probe: exit 1 unregistered, 0 registered). The page-vs-EVIDENCE
            comparison was MEASURED and is NOT a gate: 44 of 278 rows are comparable, 8 read weaker, all 8 correctly
            (compound aspect-scoped statuses vs one status per claim), so tools/reconcile.py is a REPORT that judges
            nothing, RESEARCH_METHOD.md's promotion section instructs the sweep and requires the outcome recorded
            including "nothing", and test_page_citations.py gates the half that cannot be argued about (every cited
            id must exist; 175 ids over 545 citations resolve today)
issue 31    GB/GBC FOR PHASE 7, DESIGN ONLY (docs/research/GBC_PATH.md): no run, no pre-registration, no code, no
            evidence id, no status change, no gate crossing. The Operator's framing CHECKED against the pages (they
            agree on the GBS-DOL's place and on both references reading a cartridge-type bit; they are SILENT on how
            a CPU AGB A runs GB/GBC media, so that stays his account) with one sharpening: the L/R stretch is the
            AGB's OWN behaviour, so the Disc injects the same KEYPAD word this runtime already writes -- the
            prediction needs no new capability. AND ONE RESULT THE ARCHIVE ALREADY CARRIED: the original CONTROL byte
            splits 12 logs at 0x90 (the cartridge-less era; GBP-VIDEO-002's own question is "WITHOUT a Game Pak")
            against 22 at 0x92 (every run with a cartridge), the difference exactly bit 0x02 = CART_INSERTED, with no
            exception -- which is what U-GBP-017's Needs list asked for and had never been measured. NOT PROMOTED
            here: offered to a promotion checkpoint with its caveats. Bit 0x01 read 0 in all 34, so the type bit is
            the gap a GB/GBC boot fills: experiment one is one boot with NO new code and its prediction (0x93 / 0x92 /
            0x90) is written before the data; experiment two makes the stretch testable with NOT CHANGED reachable as
            a real result. Delivery solved by the Everdrive GB X7, with four things to verify rather than assume
next        orchestrator-owned: validate #41's pre-registration, #29 and #31; the Operator's declaration and the runs
            on #43; close #36. Executor: C (Issue #30)
forbidden   frozen analyzers and formats (OGBPIDX1, OGBPIDXCAP1, OGBPDISP2, and now OGBPCOORD1,
            OGBPFULL1 v1, OGBPVI1 v1), Policy A, witness semantics, evidence of runs 1-11,
            Phase 11, networking, BBA initialisation, Ethernet
```

**Networking does not start.** No Ethernet, no BBA initialisation, no network
code, no Phase 11 movement.

**Artifact identities are computed HERE first**; the operator's `sha256sum` is a
double check. Runs 9, 10 and 11 media checks: PENDING.

**Carried, read-only:**

```text
1  DISPSRC terminal_pending prints BEFORE gbp_vdisp_finish(); read the header.
2  the F8 auditor blind spot is CLOSED (§V5.59): tools/poc_audit.py reads the
   objdump -r listing of every object; a data-only forbidden reference is caught.
3  `xfb_skipped` = defer attempts under Policy A, never loss (GBP-HW-207).
4  the 18 ms console flash (GBP-HW-228) is a polish item for a non-debug profile.
5  `make stream-audit` builds the GBP-VIDEO-001 ISR reference it compares
   against (§V5.59, F3); no audit has to be run before another any more.
6  stream-0010's WITELIG line is clipped at 248 characters (GBP-VID-033); runs 9
   and 10 stay interpreted by the exact counter derivation. stream-0011 fixes it,
   and run 11 confirmed the fix on hardware (§V5.58.9): truncated=0, both records
   complete, the zero read directly.
```

**BEFORE the run, protect the raw record.** The console names every run of a
binary identically; run 3 overwrote run 1's log in `logs/`, and run 8 overwrote
run 7's. The rule — rename BEFORE copy, `cp --update=none`, hash on receipt,
never overwrite an earlier raw artifact — lives in `captures/README.md`
("Receiving a new physical run"). **Runs 9, 10 and 11 are archived under the `…-run9…`, `…-run10…` and
`…-run11…` names, which are now taken. RUN 12 was executed and ingested
(§V6.20); its five names are TAKEN:**

```text
captures/local/GBP-VIDEO-004_stream-0013-run12.log
captures/local/GBP-VIDEO-004_stream-0013-run12-idxcap.bin
captures/local/GBP-VIDEO-004_stream-0013-run12-disp.bin
captures/local/GBP-VIDEO-004_stream-0013-run12-full.bin
captures/local/GBP-VIDEO-004_stream-0013-run12-vi.bin
```

**RUN 13 was executed and ingested (§V6.25) under the SAME console-generated
names (the same build); its five archive names are TAKEN:**

```text
captures/local/GBP-VIDEO-004_stream-0013-run13.log
captures/local/GBP-VIDEO-004_stream-0013-run13-idxcap.bin
captures/local/GBP-VIDEO-004_stream-0013-run13-disp.bin
captures/local/GBP-VIDEO-004_stream-0013-run13-full.bin
captures/local/GBP-VIDEO-004_stream-0013-run13-vi.bin
```

**RUN 14 and RUN 15 (GBP-INPUT-001, `HARDWARE_TESTS.md` §V7.1 / §V7.2) were
EXECUTED 2026-09-21 and their ten files are ARCHIVED under the reserved run14
/ run15 names below (verified absent first, `cp --update=none`, `cmp`; sizes
and SHA-256 in GBP-HW-261; the RUN 15 drop arrived in `logs/run15/`, so
nothing was overwritten). RUN 16 (added by the pre-hardware amendment of
Issue #23) is NOT RUN; its five names stay RESERVED and TAKEN even if it is
never executed. The console writes the SAME names for all three runs
(`GBP-VIDEO-004_stream-0014.*`): each run's files are archived under its
own names BEFORE the next run boots.**

```text
captures/local/GBP-VIDEO-004_stream-0014-run14.log
captures/local/GBP-VIDEO-004_stream-0014-run14-idxcap.bin
captures/local/GBP-VIDEO-004_stream-0014-run14-disp.bin
captures/local/GBP-VIDEO-004_stream-0014-run14-full.bin
captures/local/GBP-VIDEO-004_stream-0014-run14-vi.bin
captures/local/GBP-VIDEO-004_stream-0014-run15.log
captures/local/GBP-VIDEO-004_stream-0014-run15-idxcap.bin
captures/local/GBP-VIDEO-004_stream-0014-run15-disp.bin
captures/local/GBP-VIDEO-004_stream-0014-run15-full.bin
captures/local/GBP-VIDEO-004_stream-0014-run15-vi.bin
captures/local/GBP-VIDEO-004_stream-0014-run16.log
captures/local/GBP-VIDEO-004_stream-0014-run16-idxcap.bin
captures/local/GBP-VIDEO-004_stream-0014-run16-disp.bin
captures/local/GBP-VIDEO-004_stream-0014-run16-full.bin
captures/local/GBP-VIDEO-004_stream-0014-run16-vi.bin
```

**RUN 21 and RUN 22 (GBP-INPUT-004, `play-0001`'s first runs,
`HARDWARE_TESTS.md` §V7.6, Issue #41) are PRE-REGISTERED and NOT RUN. TWO
names, not ten: `play-0001` writes ONE file per run and no sidecars. Verified
absent on 2026-09-21; RESERVED and TAKEN even if a run aborts, never starts,
or RUN 22 is never executed.**

```text
captures/local/GBP-PLAY-001_play-0001-run21.log
captures/local/GBP-PLAY-001_play-0001-run22.log
```

**RUN 17 and RUN 18 (GBP-INPUT-002, the machine-join runs of `stream-0015`,
`HARDWARE_TESTS.md` §V7.3 / §V7.4, Issues #28, #32, #33) were EXECUTED
2026-09-21 and are INGESTED; their ten names below are USED (the fifteen
hashes in §V7.4.3). RUN 16, the optional menu reading, was ALSO executed the
same day, LAST, on `stream-0015`: by §V7.3.2's rule its NUMBER stayed with the
menu experiment and its NAME follows the actual build — the five
stream-0015-run16 names below are USED; the five stream-0014-run16 names in
the block above are RETIRED (reserved on the assumption of stream-0014, never
used, never reassigned). The console writes the SAME names for every run
(`GBP-VIDEO-004_stream-0015.*`): each run's files were archived under their
own names before the next run booted.**

```text
captures/local/GBP-VIDEO-004_stream-0015-run17.log
captures/local/GBP-VIDEO-004_stream-0015-run17-idxcap.bin
captures/local/GBP-VIDEO-004_stream-0015-run17-disp.bin
captures/local/GBP-VIDEO-004_stream-0015-run17-full.bin
captures/local/GBP-VIDEO-004_stream-0015-run17-vi.bin
captures/local/GBP-VIDEO-004_stream-0015-run18.log
captures/local/GBP-VIDEO-004_stream-0015-run18-idxcap.bin
captures/local/GBP-VIDEO-004_stream-0015-run18-disp.bin
captures/local/GBP-VIDEO-004_stream-0015-run18-full.bin
captures/local/GBP-VIDEO-004_stream-0015-run18-vi.bin
captures/local/GBP-VIDEO-004_stream-0015-run16.log
captures/local/GBP-VIDEO-004_stream-0015-run16-idxcap.bin
captures/local/GBP-VIDEO-004_stream-0015-run16-disp.bin
captures/local/GBP-VIDEO-004_stream-0015-run16-full.bin
captures/local/GBP-VIDEO-004_stream-0015-run16-vi.bin
```

**RUN 19 and RUN 20 (GBP-INPUT-003, `HARDWARE_TESTS.md` §V7.5, Issue #34,
amended and then WITHDRAWN BEFORE HARDWARE under Issue #37) are NOT RUN;
their ten names below are RETIRED — reserved on 2026-09-21, verified absent,
never used, never reassigned (as the stream-0014-run16 names were); the
numbers 19 and 20 are consumed and the next run takes 21.**

```text
captures/local/GBP-VIDEO-004_stream-0015-run19.log
captures/local/GBP-VIDEO-004_stream-0015-run19-idxcap.bin
captures/local/GBP-VIDEO-004_stream-0015-run19-disp.bin
captures/local/GBP-VIDEO-004_stream-0015-run19-full.bin
captures/local/GBP-VIDEO-004_stream-0015-run19-vi.bin
captures/local/GBP-VIDEO-004_stream-0015-run20.log
captures/local/GBP-VIDEO-004_stream-0015-run20-idxcap.bin
captures/local/GBP-VIDEO-004_stream-0015-run20-disp.bin
captures/local/GBP-VIDEO-004_stream-0015-run20-full.bin
captures/local/GBP-VIDEO-004_stream-0015-run20-vi.bin
```

On 2026-09-21 RUN 13's files arrived in `logs/` under the bare console names
and overwrote RUN 12's raw-drop copies there — the second time the collision
`captures/README.md` describes has happened. RUN 12 survives in its run-12
archive (re-hashed at the RUN 13 ingestion, all five equal to GBP-HW-250) and
in its versioned fixtures; the `logs/` bare names now hold RUN 13's bytes.

An embedded build id does not mean the same physical run.



**Carried to the next FUNCTIONAL checkpoint: nothing.** F3, F8 and F5 — carried
untouched for four rounds so the three-run comparison stayed causal — were
closed by GitHub Issue #5 (HARDWARE_TESTS §V5.59) once run 11 had validated
`stream-0011`:

```text
F3  CLOSED  every *-audit is a file target rooted in the ELF, which depends on the
            sources; the GBP-VIDEO-001 ISR reference is a prerequisite the video
            probe's rules produce on demand; .DELETE_ON_ERROR; tests/host/test_make_audit_deps.py
F8  CLOSED  tools/poc_audit.py reads objdump -r of every object; non-text relocations
            feed every forbidden check as "data" origins; call-site contracts still
            count R_PPC_REL24 only; real PowerPC negative controls in
            tests/host/fixtures/poc_audit_f8; tests/host/test_poc_audit_data_reloc.py
F5  CLOSED  stream-0012: gbp_vstate_config_disable_time_target() -- the witness
            target is the only success; safety cap 60 s unchanged; 5000 ms / 64 / 2048
            unchanged; tests/host/test_stream_success.py, test_gbp_video_state.c
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
| The XFB-region CRC of the §V6 design was DROPPED by decision (Issue #7): no build computes one, CLAIM-B stops at source → converted texture, and CLAIM-C stays a register write plus a software mirror | `HARDWARE_TESTS.md` §V6.18.8 |
| The only VI facts a runtime can observe without a callback are the base registers read back (`VI[14,15,18,19]` at `0xCC002000`, read-only loads); `VIDEO_GetCurrentFramebuffer()` is libogc2's own bookkeeping, not a readback | `HARDWARE_TESTS.md` §V6.4, §V6.18.7 |
| `coord-0001` embeds no commit, so its ROM hash is stable across commits; the DOLs embed theirs, so a stream build's hash is not | `stimulus/agb-coord/Makefile`; §V6.18.2 |
| **The console and the Game Boy Player are the same two units in every run of this project** — the Operator's DECLARED HARDWARE INVENTORY (2026-09-21, Issue #25: exactly one GameCube, exactly one Game Boy Player; he asked not to be questioned on it again), a declaration, not an inference; future pre-registrations cite it instead of asking. **Two STANDING declarations (2026-09-21, Issue #35, after the ingestion of RUN 16 / 17 / 18), in the Operator's words as relayed:** the display chain is unchanged — "video inalterado e ira permanecer assim ate que eu anuncie o contrario" — and the BBA stays present with no Ethernet cable — "BBA também permanecera presente e sem cabo, ate que seja solicitado para remover ou conectar o cabo". They are operator declarations WITH A STATED DURATION: a future pre-registration cites them instead of asking; they are never a licence to infer and do not make the topology "known" — each item is DECLARED, by him, until he says otherwise, and if he announces a change and a run's record does not reflect it, that run is INCONCLUSIVE on that item (§V7.1.4). Until Issue #35 these two were declared per run (RUN 14 / RUN 15 under Issue #25; RUN 16 / 17 / 18 recorded as absent at ingestion, then declared). What still varies and MUST be declared per run: the cartridge and its boot screen, and the controller — he owns a generic third-party pad and an original Nintendo pad and has used both (RUN 14 / 15 / 17 the generic, RUN 16 / 18 the original), so it is never assumed | GBP-HW-261, GBP-HW-266; `HARDWARE_TESTS.md` §V7.2.2, §V7.4.2 |

## Do not assume

- **That RUN 21 / RUN 22 have run.** They are pre-registered (§V7.6) and the
  image is STAGED (Hardware Issue #43, 2026-09-21: `build/swiss/13-play` and
  the SD's `13-play`, both `d0ee3c29…99de`, verified from the card; `12-stream`
  untouched). Nothing has run, and gate item 1 (which cartridge, in which form)
  is answered by the Operator at the launch.
- **That `make swiss` is safe to run.** It re-exports EVERY enabled slot from
  `build/poc`, which holds whatever this tree last built. On 2026-09-21 it
  would have replaced the frozen `12-stream` (`dd545c01…3a49`, the image RUN
  16/17/18 executed) with a rebuild at another commit, silently and with a
  successful exit code. Stage ONE slot by hand until `tools/swiss_export.py`
  grows a `--only` option and a refusal to overwrite a slot whose hash differs
  from what it would write.
- **That a column of `N/A` in the acceptance runs is a finding.** A game that
  never asks for L is not evidence that L fails: which keys a title uses is a
  property of the title, and it differs across the three candidates
  (WarioWare's microgames are mostly the D-pad and A). `N/A` means the pad
  produced the press and the runtime sent the word and the game had nothing to
  do with it, which §V7.6.11 requires the KEY record to show. It is not "DOES
  NOT WORK".
- **That `play-0001` has run, or that its timing was checked.** It has not
  and it was not: the image is built and audited, its service pass is shorter
  than stream-0015's by the witness step (RUN 17: 5 / 70 / 1 547 ticks per
  VIDEO block), the pre-witness shape has precedent (stream-0003 / 0004) but
  never with the input path, and the only instrument that can check the gap
  is the first run (`INPUT_PATH.md` §13.5). "The device operations are the
  same" is a statement about the operation stream, not about timing.
- **That `stop=session_end` is anything but the only success of a play
  session.** A session that ended by the 720 s budget, a store cap or the
  guard has gone wrong, however well the game played.
- **That the disposition question is answered for a long session.** The
  trace is out of the playable image by decision; U-GBP-035 records that no
  instrument exists for presentation behaviour over minutes of real content.
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
- **That `stream-0015` is still unexecuted, or that the routing is still only
  CORROBORATED.** It ran three times on 2026-09-21 — RUN 17, RUN 18, RUN 16
  (Hardware Issue #32) — and the KEY record joined to the checker's counters
  made the routing of every KEYPAD word bit a physical FACT (hw, the runs):
  §V7.4, GBP-HW-270, Issue #33. In Dolphin the pump slot still never runs, so
  Dolphin covers none of it.
- **That the interval-wise join binds the routing.** It does not: within one
  sample interval the counts are not distinct (RUN 14 had R +2 and B +2 in the
  same interval), so an interval-local join cannot say which bit moved which
  counter; only the whole-run totals bind, and only for bits whose totals
  are distinct (§V7.3.1). The interval check is recorded, never a gate.
- **That RUN 14 / RUN 15 made the L/R routing a FACT, or that RUN 16 answered
  its directional question.** RUN 14 / RUN 15 left the routing CORROBORATED —
  the Operator having pressed L exactly once was in no machine record
  (GBP-HW-265); RUN 17 / RUN 18 made it FACT with the KEY record (GBP-HW-270).
  RUN 16 ran, last, on `stream-0015` with the original pad: M = PASS by the
  Operator's report, O NOT READABLE — no convention declared before booting,
  no direction per trigger reported, nothing inferred (§V7.4.8). The
  Operator's informal, unregistered, incomplete trial of 2026-09-21 remains
  NOT a run and supports no claim (§V7.1.2).
- **That the Operator's Start-up Disc recollection settles the L/R order.**
  It composes to bit 8 = L (GBP-KEY-007) but it is a recollection, not a
  recorded observation, and remembered the other way round it would give the
  opposite answer; U-GBP-010 closed on RUN 14 / RUN 15 (§V7.2), not on the
  recollection, and nothing is promoted by it.
- **That the input path is a finished feature because RUN 14 / RUN 15
  passed.** `stream-0014` (`0ff8355`, SHA-256 `ef76a170…`) ran twice and
  `stream-0015` (`da06500`, `dd545c01…`) three times with one instrument, a
  counting test ROM (and once the EZ-Flash menu), two pads by their digital
  click (the generic third-party pad; the original Nintendo pad), one
  cartridge; every pressed button reached its own counter and the join closed
  (GBP-HW-264, GBP-HW-265, GBP-HW-270). Nothing was measured about latency,
  about the 5 ms refresh being needed, about other pads, ports or cartridges,
  or about a real game; the descriptor's assignment survived its falsifier
  and is now the measured one — FACT (hw, the runs), which says nothing beyond
  those runs (GBP-KEY-006, GBP-KEY-009, GBP-KEY-010).
- **That the KEYPAD L/R routing is a physical FACT beyond the runs' scope, or
  that it was one before the join of 2026-09-21.** It IS a physical FACT (hw,
  the runs) since RUN 17 / RUN 18: bit 8 → L and bit 9 → R, and bits 0–7 each
  to its key, by the machine join of the runtime's KEY record to the
  checker's counters, on two controllers (GBP-HW-270, §V7.4); `REGISTERS.md`,
  `GBS-DOL.md`, `ARCHITECTURE.md`, `INITIALIZATION.md` §15 and
  `docs/protocol/INPUT.md` state it so with the history kept. What it is NOT:
  a statement about latency, the refresh, pads other than the two declared
  (bits 0–3 on the generic pad only, bits 4–7 on the original only), other
  ports or cartridges, or a game. And before that join the routing was
  CORROBORATED, not FACT — the link "the Operator pressed L exactly once" was
  in no machine record (GBP-HW-265) — history, not to be rewritten.
- **That RUN 19 / RUN 20 will run, or that Phase 5 is closed, or that a
  checker run on the other pad would add to the routing's FACT.** The pair
  (§V7.5, Issues #34 and #37) was pre-registered, amended and then WITHDRAWN
  BEFORE HARDWARE; its names are retired. The routing does not depend on the
  pad — Question J reads word → counter and the pad is upstream of the word
  — so §V7.4's FACT for all ten bits is complete as it stands; what a run on
  the other pad would have added is the pad → word link for eight button ×
  pad combinations, given up on record. A test ROM is not a real game, so
  Phase 5 stays NOT ASSESSED and its closure is further away (a game that
  passes through the button path, and the build change of §V7.5.3, are
  still needed).
- **That a smaller stream probe is an acceptance image.** Unbinding the
  witness and dropping the sampler and the traces leaves an image whose every
  stop is scored as the run going wrong (INPUT_PATH.md §12.3): the 60 s
  safety budget, the 274 s frame store cap, the ~63 s delivery cap. A session
  that ends by any of them is not a success, however well the game played;
  the success stop an acceptance run needs does not exist yet and lives in
  the service-path module (§12.4) — a redesign, not a subtraction. Issue #38
  assessed this and stopped; nothing was built.
- **That WarioWare is an instrument for an input test.** The Operator's
  WarioWare is WarioWare: TWISTED, the gyroscope title — most of its
  interaction bypasses the button path; evaluated and REJECTED (§V7.5.2);
  the "WarioWare original" recommendation of Issue #34 is withdrawn.
- **That the topology is known.** It is DECLARED: the console and the Game
  Boy Player by the inventory (Issue #25), the BBA (present, no cable) and the
  display chain (unchanged) by two STANDING declarations with a stated
  duration (Issue #35), each by the Operator until he says otherwise; the
  cartridge with its boot screen and the controller stay per-run
  declarations. A standing declaration is cited, never inferred from, and a
  run whose record does not reflect an announced change is INCONCLUSIVE on
  that item (§V7.1.4).
- **That the keypad plane inherits the video plane's confidence.** It does
  not: before RUN 14 every keypad statement in the project was static
  (GBP-KEY-001…005, GBP-VID-011); the physical record now holds four runs of
  one instrument plus one menu reading (GBP-HW-261…271) and nothing else.
- **That the Phase-4 verdict measured retail content.** It did not: the
  oracle-based colour, geometry and fidelity results are FACT on controlled
  stimuli; on retail content the evidence is machine-side metrics identical to
  the controlled runs plus operator observation, and the transfer is an
  inference about a content-blind path — CORROBORATED, never FACT
  (`docs/research/PHASE4_ASSESSMENT.md` §3, residual R1, owned by Phase 7).
- **That Phase 4's closure opens Phase 9.** Presentation, scaling and the
  pixel-perfect requirement (GBP-VID-032) are Phase 9 by the ROADMAP's text and
  by the runtime's; the assessment names them as a residual and authorises
  nothing. Phase 5 is the ROADMAP's next phase; the choice is the Operator's.
- **That RUN 12 established scanout or fidelity.** It did not: both
  GBP-VIDEO-007 and GBP-VIDEO-008 are INCONCLUSIVE because the shared source
  gate failed (§V6.20). The subordinate 8/8 full-frame result and the
  operator's 1-2-3-4 are preserved as evidence, not as verdicts.
- **That the frozen `tools/vfull.py` PASS 8/8 is a PASS of the GBP-VIDEO-008 experiment.** It is
  the dependent variable of an inadmissible run; the pre-registered gate
  decides admissibility first, and it failed.
- **That the two duplicate FRAME_IDs are a source loss, a transport defect or
  a capture defect.** They are the stimulus's own scheduling (GBP-VID-034,
  §V6.22): the entry PREPARE of digits 1 and 4 runs longer than an AGB frame
  and skips a VBlank; VRAM keeps the previous frame and the GBP captures it
  twice. Their adjacency to the R_1 and R_4 boundaries is the cause showing.
- **That the FAULT latch would have caught it.** It cannot: `vc0` is read after
  both wait loops and the timer brackets PUBLISH only; a PREPARE-side miss is
  invisible to STATUS by construction (§V6.22.3). A stimulus that wants to
  bound PREPARE has to measure PREPARE (§V6.22.10, design only).
- **That the model's margin is the same on both sides.** The duplicates are
  predicted with 8-9 % to spare; the non-duplicates at R_2 / R_3 with 0.8 % /
  1.5 %, and that side has no hardware calibration point of its own. Digits
  6-9 are predicted to duplicate and digit 5 not; a future run decides.
- **That `coord-0002`'s timing proof is a hardware measurement.** The cycle
  model (§V6.23) is software: the same picture as coord-0001, the entry PREPARE
  176 863 cycles under the budget on its exact image. RUN 13 (§V6.25) is one
  physical run in which the source gate passed with no duplicate at any entry
  — consistent with the model, not a calibration of it. coord-0001 stays RUN
  12's artifact and the GameCube runtime is unchanged.
- **That RUN 13 established more than its two boundaries.** GBP-VIDEO-007 =
  PASS is CLAIM-D only (a digit bound to a 40-frame appearance set, never to
  one frame; no pixel claim); GBP-VIDEO-008 = PASS is CLAIM-A / CLAIM-B for the
  eight sampled frames only. The ≈ 8 s spacing is a human estimate, never
  timing evidence; the one SUPERSEDED R_3 record (`frame_index` 1754) is
  instrumentation semantics, never evidence of physical non-scanout; nothing
  about presentation, pixel-perfect scaling (GBP-VID-032), the converter, the
  panel, Morph 2K or the Q80T.
- **That the 0/2370 of the analyzer frozen at RUN 12 means the VI registers
  disagreed with the hand-overs.** They did not: the corrected tool (Issue #11,
  §V6.21) reads 2370/2370 — the zero was a 24-bit mask before the flag shift
  (GBP-VID-035, repaired). The frozen-at-run result stays as history and the
  corrected replay is post-run software analysis; neither moves a verdict.
- **That the corrected L_3 = 38 says two frames were not shown.** SUPERSEDED
  means only that OGBPVI1 recorded no latch for those two hand-overs (the next
  hand-over came first); whether they were physically scanned out is not known.
- **That the RUN 12 display chain says anything about pixels.** Composite / RCA
  → a low-cost RCA-to-HDMI converter at 1080p → a HYDIS HV150UX2 panel is a
  topology DECLARATION. It supports no pixel-perfect, scaling, latency or
  native-1080p claim, and GBP-VIDEO-007's PASS binds a digit to a 40-frame
  appearance set, never to one frame.
- **That the future Morph 2K paths belong to RUN 12.** GameCube → S-Video →
  Morph 2K → Samsung Q80T (primary) and GameCube → Bitfunx composite → Morph
  2K → Samsung Q80T (alternate) are DIFFERENT topologies, declared for later;
  their results are never mixed with RUN 12 or with each other.

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

Slot `13-play` (`gbp-play-session`, Issue #39) exists in the manifest and
is NOT exported yet: `build/swiss/` was deliberately left as the Hardware
Issue #32 staging (`12-stream` = `stream-0015`), and a code checkpoint never
re-exports it. Exporting `13-play` is the staging step of a future
pre-registration, not of the build.

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
  state and the operator confirms continuation;
- the operational contract of a checkpoint is its GitHub Issue
  (https://github.com/zenaror/Open-GBP/issues): it bounds the scope and never
  sets evidence status.

Stop after the takeover report.
```
