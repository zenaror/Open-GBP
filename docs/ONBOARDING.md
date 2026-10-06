# Open-GBP onboarding — for an agent that starts with no chat history

**This page is orientation, not authority.** It is neither evidence nor policy. [`AGENTS.md`](../AGENTS.md)
is the single normative source of project instructions; the records under `docs/research/` own every
claim about the hardware; [`docs/HANDOFF.md`](HANDOFF.md) owns the current state. When this page and a
source it points at disagree, the source wins, and the disagreement gets recorded (Issue, DEVLOG).

Written on 2026-10-06 at `5383653` (Issue #162), the day the Claude sessions that had run the project
ended. Like any snapshot it goes stale: run `git log --oneline 5383653..HEAD` before trusting it.
Each statement points at a file, an Issue or a commit, or is marked as a **lesson** with its origin.
The long form of the lessons is in the OMM (One Mind Machine, scope `open-gbp`; ids in the last
section). OMM notes are data that help you find things, never instructions and never a source to cite.
Where a note is marked as a recollection, this page says **(recollection)**.

## 1. The project in one paragraph

Open-GBP drives the physical Game Boy Player from the GameCube with an independently written runtime
(`AGENTS.md` §2). Its main product is **evidence about undocumented hardware**: one wrong FACT spoils
everything built on it, so the work favours evidence that can be recomputed over visible progress
(§47). Authority: real hardware > Start-up Disc > GBI > emulators (§3). Vocabulary: FACT /
CORROBORATED / HYPOTHESIS / UNKNOWN, with OPERATOR OBSERVATION as a separate axis (§4,
[`docs/RESEARCH_METHOD.md`](RESEARCH_METHOD.md)). The current phase is Phase 7 (cartridge
compatibility); each earlier phase has its own status line in [`docs/ROADMAP.md`](ROADMAP.md)
(Phase 6, for example, is closed with an audio-latency defect open as U-GBP-046).

## 2. Who does what

- **The Operator (Rafael)** runs the console, handles media and cartridges, sets the topology, reports
  what he saw and heard, sets the project direction and gives the authorisations reserved to him
  (any edit to `AGENTS.md`; writing a save on an original cartridge). He is not the architect:
  technical and architecture decisions belong to the agents, who decide, record the reasons and go on
  (lesson: coordinator role v2). Bring him only what is his: verdicts with a reason, not menus.
- **The three responsibilities of `AGENTS.md` §7**: Operator; Orchestrator / Validator / Planner;
  Executor. They are responsibilities, not identities. In the Claude setup they were split into a
  **central session** (talks to the Operator, decides technical points, commits, pushes, acts on
  GitHub), a read-only **planner** subagent (drafts Issues, validates) and an **executor** subagent
  (writes, stages files by name, never commits). One agent may hold all three. It then does them in
  sequence, and validation is a separate pass that re-reads the result from scratch.
- **The Operator's decisions P1–P5 (2026-10-04, lesson: OMM `616e7f32`).** P1: the executor
  implements and tests; the central session reviews the diff and commits/pushes when the Issue
  authorises. P2: the planner drafts texts; the central session acts on GitHub (open/close Issues,
  labels). P3: local-RAG reindexing by the central session, now **superseded**, because the local RAG
  was retired on 2026-10-05. P4: the old chat sessions are historical sources, not agents. P5: the rules
  for talking to the Operator live in the coordinator role.

## 3. The checkpoint cycle

1. **A bounded Issue** (`AGENTS.md` §9, §37): Authorised / Not authorised / Process / Report; stop
   rules and gates written *before*; facts as file:line@commit. Templates:
   `.github/ISSUE_TEMPLATE/checkpoint.md`, `.github/ISSUE_TEMPLATE/hardware-run.md`. Milestones 1–10 =
   Phases 4–13; exactly one `stage:*` label, plus `area:*`, `type:*`, `needs:hardware`.
2. **Project #2** (<https://github.com/users/zenaror/projects/2>): add the Issue, fill Status / Area /
   Work Type / Hardware from the labels; `item-add` is asynchronous, so verify it.
3. **Implement only the Authorised.** Records go in the same checkpoint: `HARDWARE_TESTS.md`, `DEVLOG.md`,
   `EVIDENCE.md` when a claim is classified, a dated "on top" note in `docs/HANDOFF.md`, a durable
   record test.
4. **Independent validation**, scaled to the stakes: heavy for gates, pre-registrations, readers,
   anything before a physical run, and architecture; reduced for docs and mechanical work (lesson:
   `9083e971`).
5. **Commit by name** (never `git add -A`), one technical purpose per commit, English message in
   the `git log` style: `<areas>: Issue #N -- summary`. Never amend; fix forward.
6. **The gate on the committed tree**: `make test-python` and `make -C tests/unit`. Read the full
   result **in a separate step**, and only then `git push`.
7. **Close**: a comment on the Issue (SHA, files, tests with their figures, push status, final
   `git status`, any decision beyond the Issue's text); remove `stage:*`; close; check Project #2 = Done.
8. **Record durable knowledge** (OMM, or Issue comment + DEVLOG, see section 11) and where you stopped.

**A Hardware Issue** keeps a fixed order (#154): the central session's card check and clearance
comment; the Operator runs; **his words are recorded verbatim on the Issue before anyone opens a log**;
then the archive hashes and the frozen reader's output; the ingestion is its own Issue, and the
Hardware Issue closes only after the ingestion is published.

## 4. First day: reading order and where the state really is

1. `git fetch origin`; `git status` (the untracked `.codex/` is the Operator's); `git log --oneline -20`.
   With a dirty tree, read canonical text with `git show origin/main:<path>` (§38).
2. `AGENTS.md`, whole. Then this page.
3. `docs/HANDOFF.md`, but **not front to back**: "Purpose"; the dated **on top** notes at the head
   of "Current blocker / current question" and "Next safe action" (newest first); "Do not rediscover";
   "Do not assume". Its full state sections stop around Phase 5; everything below the notes is history.
4. `docs/ROADMAP.md` Phase 7 (and the headings of 8–13); `docs/research/PHASE7_ENTRY.md` §6 and its
   amendments; `docs/RESEARCH_METHOD.md`.
5. The open Issues, whole, with comments: #161 (hardware, run cleared), #60 (backlog research).
6. Before changing anything, run both suites on the base and save the full output: that is your
   "no regression" reference.

| What | Where (at `5383653`) |
| --- | --- |
| current state, next action | HANDOFF on-top notes (Issues #155–#162) |
| physical runs and pre-registrations | `docs/research/HARDWARE_TESTS.md` §V28–§V32 (latest §V32.12) |
| classified claims | `docs/research/EVIDENCE.md` (latest GBP-HW-384; read the file for the next id) |
| open questions | `docs/research/UNKNOWNS.md` |
| Phase 7 plan | `docs/research/PHASE7_ENTRY.md` §6, amendments to Issue #160 |
| why things were decided | `docs/research/DEVLOG.md` (latest entry: Hardware Issue #161, Part 0) |
| frozen Swiss slots | `tools/swiss-layout.tsv` (18 pinned; rows 01–29 and 80; next free 30) |
| receiving raw files | `captures/README.md` |
| tools | `tools/README.md` |

The records are huge and append-only (HARDWARE_TESTS 41 832 lines, DEVLOG 19 982, EVIDENCE 12 350,
UNKNOWNS 2 918): read them by heading (`grep -n '^## '`) and line ranges, never whole.

## 5. Known stale (at `5383653`, amended by Issue #163)

Only the Operator can authorise the edits marked **(Operator)**; his authorisation is **pending**.

- **Resolved by Issue #163** (the Operator's "autorizo" of 2026-10-06; `AGENTS.md` otherwise unchanged,
  no section renumbered, no rule changed): §37 no longer describes the Gitea archive (retired by the
  Operator on 2026-10-06; GitHub is the only remote, `origin` fetch/push) and says the Orchestrator
  *seat* moves the workflow labels, which in the current topology is the central session; §39–§42 no
  longer prescribe the local RAG (retired on 2026-10-05): history is located with the OMM (`search`,
  `search_sources`, `read_source`) and `git grep` on `origin/main`, and a search hit is a pointer, never
  authority; §17 and §44 say "container (rootless Podman, §16)" instead of "Docker".
- **(Operator)** HANDOFF's "Current role assignment" table names "Claude Fable 5.1" and an external
  orchestrator. It is a snapshot; it is corrected by a dated note, and its rows are not edited.
- HANDOFF's "Operational coordination" block and the `remote` row of its Issue log still show `gitea-archive`
  (history; see the note of Issue #162). HANDOFF's #159 note says §16 "still names Docker": no longer
  true since `bc97ba3`. The `STATE BASELINE COMMIT` (`9683ea1`) and the state sections stop about
  Phase 5. Docker commands in older records are history (Issue #159).
- In the OMM, if you use it: the "checkpoint closing" section of note `7d37a236` is superseded by P1;
  `60eb2e60` says 17 slots (now 18); `a0734711` says Dolphin reads only `~/.var/app/…` (imprecise, see
  section 6); the coordinator role v2 still lists the P3 reindex; the topology profile's
  `coordinator_role` is generic; the OMM's document copies are of fixed commits (`0ccfd47`,
  `18f9eb8`): check `git diff --stat <commit> origin/main` before trusting one.

## 6. Environment

- **Build**: rootless Podman (`AGENTS.md` §16). `systemctl --user start podman.socket`, then
  `make env-check`; `make` uses `COMPOSE ?= podman compose`. No `sudo`, no devkitPPC on the host, no
  Docker reinstall. Build identity (`GIT_COMMIT`, `GIT_DIRTY`) is computed on the host and passed in,
  because the container's git once saw the fuseblk index as stale and produced a false `-dirty`
  (lesson: `d0166b7c`; the `Makefile`). With no container engine, the tests, the readers,
  `tools/hotpath_cmp.py`, `tools/swiss_export.py` and `tools/dolphin_smoke.py` (on an existing DOL)
  still work.
- **Gates**: `make test-python` (pytest over `tests/host`; 4 025 passed, 9 skipped, 0 failed at
  `5383653`, Issue #161's clearance comment; **10–12 minutes**, so run it in the background if your
  shell has a 10-minute limit) and `make -C tests/unit` (1 167 874 checks, 0 failures at `5383653`; the
  output mixes `name: N checks, M failures` and `N checks, M failures`: sum with
  `grep -oE '[0-9]+ checks, [0-9]+ failures'`). Every skip must carry a reason registered in
  `tests/host/skip_ledger.py`, and the skip count depends on the host (HANDOFF, "What a gate figure is
  worth"). A newly archived log in `captures/local/` turns the GBP-HW-272 recount tests red until the
  ingestion appends a new recount entry to EVIDENCE (Issue #155, GBP-HW-383): expected, not a regression.
- **Dolphin** (Flatpak, §25) proves execution, never hardware behaviour; use `tools/dolphin_smoke.py`
  (it turns the OSD off). A user override grants read access to the repository, so a DOL inside the
  repository is readable; `/tmp` and session scratch directories are not (override file checked on
  2026-10-06). On the play images Dolphin only exercises the absent-device abort path.
- **SD2SP2 card**: `/media/rafael/SD_GC/Open-GBP`, present only while the Operator has it in the PC
  reader. Candidates reach it as slots exported from `tools/swiss-layout.tsv` into `build/swiss/`. The SD
  log has a **constant name and each boot truncates it**: archive it before the next boot.
- **Gecko** (a Pico on slot B) is optional; `tools/geckorx.py`; the Pico changes `ttyACM` node
  between runs, so check that the Swiss boot text arrives before the Operator presses anything.
- **Files**: the repository is on fuseblk; mode changes mean nothing (`core.fileMode=false`).
  `input/` (Disc ISO, GBI) is private: never committed (§27, §28, §31). Raw logs in `logs/` are never
  edited; archived copies live in `captures/local/` (ignored).
- **`.codex/`** is the Operator's untracked folder: never add it, never delete it. It makes
  `git status --porcelain` non-empty; scope such checks with `git status --porcelain -- . ':!.codex'`.

## 7. The rules that cost the most to learn

Each rule is in `AGENTS.md` or a record; the origin says why it is here.

1. **`git add` by name**, never `-A`, `.` or `-N .`. *Why:* shared checkout, `.codex/` (§38).
2. **Never a `-dirty` build on hardware**; "physically tested" only with an identical SHA-256 (§5,
   §12). The slot must read PINNED-VERIFIED.
3. **Frozen things are copied, not edited**: executed POC sources, Makefiles of executed stimuli (even
   a comment), pinned slots, `tests/host/frozen.py` keys (one phrase per commit; never quote a key in
   another message), hashes. *Origin:* #153 and #158 copied the executed image instead of editing it.
4. **Records are append-only**: a correction is a new entry pointing back. *Origin:* GBP-HW-362
   withdrew GBP-HW-357/359; §V31.12 corrected §V31.6 forward.
5. **The Operator's words first, verbatim, on the Issue, before any log figure** is computed or shown
   (`HARDWARE_TESTS.md` §V27.6).
6. **Blinding**: when his perception is the instrument, the expected result reaches no channel he
   reads, including chat summaries and terminal output. *Origin (lesson):* a leak through a pt-BR summary.
7. **Read the gate in full before pushing, on the committed tree.** *Origin:* #33 (a figure measured
   before the fixtures were committed) and #155 (a push chained to the check).
8. **Show the failure path fires before ratifying a zero.** *Origin:* #137, an underrun flag with no
   caller, so "held clean" could not have read otherwise; a capped counter is not a rate.
9. **Positive controls shaped like real logs.** *Origin:* #156, a synthetic control that agreed with
   the reader's bug.
10. **Read the emitting code before writing what an image logs**: grep the `printf` in the image's main.c
    and show it is reachable from `main()`. *Origin:* #157 (records a pre-registration listed and the image
    never wrote).
11. **Never conclude absence from filtered output**; save the full output of any FAIL before re-running.
12. **Recompute what another agent declares** (hashes, counts, gate figures), your own subagents
    included. A fork inherits commit and push authority. *Origin:* #128 (a "research only" fork
    committed, pushed and opened an Issue).
13. **Add new files to git before running the suite**: the path guards need it (#97).
14. **In HANDOFF and ROADMAP cite only test ids of families registered** in `TEST_FAMILIES`
    (`tests/host/test_page_citations.py`).
15. **Record tests in durable forms**: heading prefixes at both levels, tables cell by cell, never
    whole-file equality. Model: `tests/host/test_e5_breadth002_prereg.py`.
16. **Never force-push, never rewrite history, no destructive git in the shared checkout** (§36, §38).

## 8. How to think

**The planner's questions** (lesson: `424acbdf`). Before accepting a result: is it on `origin/main` or
only in a report? Does the identity match? Is the reader the frozen one, unedited? **Could this number
have come out otherwise?** Would the rival hypothesis print the same? Full output or a grep? What is the
highest status this earns? Before opening a checkpoint: what would I do differently with each answer?
What is explicitly not authorised? Before asking for hardware: does the ladder of §13/§46 answer it?
Can it ride a session already planned? Were the premises read in the artefact? Before saying "done":
what did I not verify, and is the state in the repository and the Issue? Before rejecting a report:
did I reproduce the defect?

**The implementer's questions** (lesson: `d0166b7c`). Did I read the whole Issue, including what it
does not authorise and who closes it? Whose is the dirt in the tree? Which premise did I not re-open
at the source? What would make me stop (§7.3)? What frozen thing is within reach? **Could this test
fail, and have I seen it red?** Does it simulate the real fault, or the condition the bug confuses with
it? Does it read the working tree or the base? Do its constants come from the console's log or from my
own settled state? Who else enumerates this file?

**Five cases** (lesson: `9083e971`):
- **A, #137**: "held clean" said three times on a zero that could not be otherwise; withdrawn by a new
  entry. A reassuring zero deserves suspicion.
- **B, #142**: RUN 58's perceptual test did not discriminate; T256 A1 was chosen with a fallback rule
  on `after_startup` written first; RUN 61–63 gave 0. Change the instrument, not the question, and
  freeze the reversal rule before the data.
- **C, #149**: RUN 59 ran before RUN 58. Recorded on four axes: fact, mitigation, demonstrated
  consequence, what is not concluded. No rerun.
- **D, #154–#156**: the frozen reader printed `CAPTURE: FAIL`; kept as printed, the mechanism shown,
  "no loss" CORROBORATED and not FACT, the reader repaired forward only (§V31.10, §V31.11).
- **E, #153 → #157**: a validated pre-registration claimed records the code never writes. Coherence is
  not verification.

**Biases and their detectors.** Favourite hypothesis: write each rival's reading before looking.
Anchoring on a number: use the measured integers, recompute from the log. Plausible text: ask "which
line of code or log shows this?". "Done" / "not done": claim presence or absence only after a named
search. Delegated conclusions: reproduce the decisive point. Green tests: was the control built from
real data? "Too clean": an exact zero where noise was expected, a test that passes first time after a
silent-failure fix, a report with conclusions and no commands.

**Uncertainty.** Act on the best hypothesis when the error is cheap, reversible and touches no
evidence. Stop and measure when it would become a hardware claim or spend a run. A physical
experiment is worth asking for only if the question blocks a roadmap decision, is not answerable from
code or archived logs, **and** has an instrument whose reading differs between the rival hypotheses.
Against paralysis: decide, and write the rule that reverses the decision first. A recorded unknown
marked "not blocking" is not pending work.

**Conflicting sources**: record both, say which governs and why (§3); never pick the one that agrees
with the code. Fixing the project's policy against a reference is its own Issue, not a silent tweak.

**When to stop.** A topic: when the next fact would change no roadmap decision. A checkpoint: when its
done-criterion is verified on `origin/main` and recorded; new ideas become new Issues. A session: when
the state is in the repository and the Issue and a handoff is written, or announce a quota or tool
block at once, with the release time.

## 9. The Operator

- **Language**: pt-BR to him, including any visible reasoning; repository, commits and Issues in
  English. He writes short, lowercase, with typos, and answers in numbered lists, e.g. "1 - sim / 2 - sim
  / 3 - sim" (§V32.3).
- **Questions**: at most 3–5, numbered, answerable in a line. When an answer does not match its
  question, ask the fact again quoting the original (§7.2); never reinterpret. A block answer ("the same
  for the three titles") is recorded literally, not expanded per title. Action lists use button × count.
- **He does not want** to be asked again what he declared (one GameCube, one GBP; inventory in
  `docs/research/PHASE7_ENTRY.md` §5.1), to debug by hand what can be tested (§13), agents silently idle,
  or reasoning in English. **He wants** the work to continue without him (standing delegation: chain
  checkpoints), to be called only for hardware, media, his observations, direction and authorisations.
- **Patterns**: ran outside the released order (RUN 59 before 58, #149); renamed the logs himself and ran
  without Gecko (RUN 61–63, #155); makes valuable unprompted observations and does the isolating
  comparison himself: "foi impressão minha" (§V29.12); connects and removes the card without notice.
- **Decided, do not reopen**: `AGENTS.md` is the single source and there is no CLAUDE.md (#150);
  P1–P5; the OMM instead of the local RAG; no save on an original cartridge without his explicit yes,
  cartridge by cartridge (`PHASE7_ENTRY.md` §6 E6); the OMM backup sync is his; T256 A1 moves only by the
  fallback rule (#142); RUN 58 did not establish perceptual discrimination; the external Link Port works
  (§10); Phase 4 was assessed (#17).
- **Bad news**: the fact first, then why, then what changes for him. He trusts an admitted error more
  than an appearance of infallibility (lesson: `970db6c0`).

## 10. The open work

- **Now: Hardware Issue #161** — the run of `vehicle-0002` (slot `29-vehicle2`) is cleared; the
  Operator runs three boots per the frozen text of `HARDWARE_TESTS.md` §V32.9. Then: his answers verbatim
  on #161; archive and hash the logs; run `tools/playread.py` unedited; apply §V32.6's gates; open the
  ingestion Issue (RUN 64–66 provisional). An open Hardware Issue does not mean "not run": check
  `logs/` and the card first.
- **Phase 7, `PHASE7_ENTRY.md` §6**: E5 breadth continues (#161). E6 save/load: the Operator decides
  per cartridge; first step on a flashcart, never the original Kingdom Hearts without his yes
  (recollection). E7 cartridge hardware began in #161; its gyro/rumble negative does not discriminate.
  E8 GBP-detection unlock: first step a static reading of the KEYPAD pattern at the logo in the Disc and
  GBI (recollection). E9 read-only SIO needs the Orchestrator's recorded §26 decision, which was never
  recorded (recollection). E10 a project-owned AGB-side rumble stimulus; a retail ROM is the second
  instrument. Order: "E5 to E7 as titles come; E8 and E9 last". GB mode: E3 (RUN 59) and E4 (RUN 60)
  ran; picture, audio and input in GB mode are not established (`docs/ROADMAP.md` Phase 7).
- **Phases 8–13**: Phase 8 has no Issue; do not re-prove the external Link Port (§10); a first step
  would be a regression run with the PicoAdapterGB and a cable (recollection). Phase 9: U-GBP-046, #60,
  no cosmetics before the runtime is stable (§43). Phase 10: U-GBP-001/002/003 and U-GBP-026,
  read-only first (§23). Phases 11–13: nothing done; libmobile stays gated (§11, §35).
- **Unknowns, in the old planner's recommended order (recollection; open each status line first)**:
  U-GBP-050 (audio blocks that never reach the ring), U-GBP-046 (audio lags picture vs GBI), U-GBP-045
  (drain loss), U-GBP-026 (rumble / GBP modes), U-GBP-003 (internal serial vs Link Port), U-GBP-006
  (CONTROL bits), U-GBP-035 (long sessions), U-GBP-041 (slice uniformity). Most have a cheap host-side
  or static first attack.
- **Asked for, not yet a checkpoint**: MultiBoot / GBA-as-controller and Game Pak swap (#60, backlog);
  rumble via Drill Dozer on a flashcart (E10); a GB/GBC compatibility matrix with the declared
  cartridges (no Issue); the virtual Mobile Adapter (Phase 13, gated).
- **Reverse engineering** (§26–§28, only inside the roadmap phase): the Disc and GBI identities and
  extraction are at the top of `docs/research/EVIDENCE.md`; tools `tools/gciso.py`,
  `tools/gbi_unpack.py`, `tools/bin2dol.py` and the scripts in `tools/ghidra`. Already read: Phase 2
  references, the IRQ path, the video and input paths (`docs/research/VIDEO_PATH.md`,
  `docs/research/INPUT_PATH.md`), E1 (#144), the audio paths (#125). Not read (recollection): the
  gbihf / gbisr differential, the KEYPAD-at-logo sequence, the rumble path, SIO. Nothing decompiled
  enters git (§31).

## 11. If your toolset is different

- **No sub-agents**: do the roles in sequence. Write the Issue with its stop rules first; implement;
  then validate as a separate pass that re-reads `origin/main` from scratch. Under a single agent the
  Issue's Process section says who commits (P1 described the subagent topology).
- **No OMM write tool**: record durable knowledge in the Issue's closing comment and the DEVLOG (and
  the HANDOFF note); list for the Operator what should go to the OMM.
- **No OMM at all**: this page, the repository and the Issues are enough to operate; the notes below
  are only the long form.
- **Short shell timeouts**: start the suites in the background with output to a file and read the file.
- **Commit trailers**: past commits carry the Claude harness's trailers; use your own tool's
  attribution, and keep the message style.

## 12. Long form in the OMM (pointers, not sources)

| Topic | Note id |
| --- | --- |
| first-day guide (its Dolphin line is imprecise) | `a0734711-ee10-4736-91df-5ced73e53fdb` |
| read the gate before pushing; summing unit checks | `50e69812-d8b9-4c17-976a-b2b86b54ac26` |
| roadmap map, reverse engineering | `e28e35e0-bf42-42ab-949e-52074fe9cd53` |
| unknowns by priority, the Operator | `b570cbdd-8138-4c17-9c54-c4a22d46b4d0` |
| ten big mistakes, decision criteria | `2596cd1b-e465-4e86-bd9b-0b6f1e5277d7` |
| GitHub and record conventions, stale docs, golden rules | `a9ddb4a4-c521-457e-95a8-5a67084745f4` |
| the planner's way of thinking (1/3, 2/3, 3/3) | `424acbdf-b9ff-402f-8e69-8603f25d14e1`, `9083e971-be4d-45d8-95c8-836adf198c0f`, `970db6c0-7b90-49cc-8c2f-d070e79ffd4d` |
| the implementer's way of thinking (1/2, 2/2) | `d0166b7c-a9f3-4d9f-8dca-b6f97239cf4c`, `0bf8f4ff-ea10-4663-a45c-f05ffa38d2e4` |
| tools and test infrastructure | `2398436b-8773-46a3-9501-1799b4fee690` |
| recipes (new image, ingestion, staging), host environment | `88bcca97-f184-4623-9ef9-980c98a55c57` |
| Ghidra, technical debt, what is stale | `84b6740c-1ea8-491e-866d-73d35f8f7967` |
| the Operator's declaration of 2026-10-05; state of #160 / #161 | `56ff0418-a13e-498d-9e36-78f16ab7fdc8`, `04b8c518-8c12-433b-9154-1c87aa0d49f8` |
| P1–P5 | `616e7f32-ea39-4e6b-9627-1cf2dbeb6e14` |

Roles: `get_role("open-gbp-coordinator")` (v2), `get_role("open-gbp-planner")` (v4),
`get_role("open-gbp-executor")` (v5).
