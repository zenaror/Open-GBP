# poc/gbp-av-service-probe — GBP-AV-SERVICE-001

**Test ID:** `GBP-AV-SERVICE-001` — **Build ID:** `avsvc-0001` — **IMPLEMENTED 2026-09-16 — NOT
PHYSICALLY EXECUTED.** The build of this working tree is a **DIRTY BUILD — NOT A PHYSICAL
CANDIDATE** (commit `5ed9d93-dirty`, DOL SHA-256
`4564e42a2c8239161ee19440d9292818d42d18ac31a7b9b73bfc3dd5c34eb52d`, 404000 bytes, after the
micro-audit of 2026-09-16): it exists for
review only and must never reach the hardware. A physical candidate requires a clean commit, a
clean rebuild, the audits below on that build, a recorded hash and an explicit authorization.

**Question:** after one validated delivery of an HSP cause (GBP-INIT-003B / 004, FACT), does ONE
reference-style service pass — read the IRQ register (pending), drain every pending AV block with
one whole-block DMA each (AUDIO 0x1000 at index 0x8, then VIDEO 0xF00 at index 0x1: the order of
both references), acknowledge `pending | 0x8000`, re-arm `IRQ := 0x0000` — lead to a NEW PI HSP
cause with a valid AV source within a bound, with the CPU masked throughout and no second
delivery? Secondary: the raw content of the two blocks (length, DMA duration, CRC-32, byte windows;
the whole bytes in the block sidecar). Full design: `docs/research/HARDWARE_TESTS.md` "Planned
tests — GBP-AV-SERVICE-001"; implementation record: `docs/research/DEVLOG.md` 2026-09-16
"GBP-AV-SERVICE-001 implemented".

## Provenance and rules

- **No fourth copy of the initialization.** The 003A stage (`src/gbp/gbp_initirqa_probe.c`, stage
  API) runs verbatim, PI masked, no handler, until INTSR bit 13 = 1 (EVENT). The delivery, the
  ACK/POSTACK/single-main-W1C step and the teardown hook are `src/gbp/gbp_irq_service.{h,c}`
  (the 003B cycle service; its ACK step was split so a caller can acknowledge a value it read
  earlier — `gbp_irq_service_ack_write_postack` — and the 003B/004 records stay byte-identical,
  pinned by their physical fixtures). The teardown is the 003A one.
- **Handler: the 003B extended one-shot** (`hsp_backend_oneshot_isr_ext`, physically executed
  2026-09-15), installed ONCE after the first latched cause, previous handler kept and restored.
  A second delivery is forbidden by design, so no generation wrapper (the 004 multi-cycle object
  `hsp_backend_irq_multi.c` is **not** linked; nor is `hsp_backend_intmr.c`). INTMR changes only
  through `__UnmaskIrq` (one call site, `h_irq_unmask`, reached exactly once from
  `gbp_irq_service_deliver`, itself called exactly once by the probe) and `__MaskIrq`.
- **PREUNMASK** (abort, never adjust): the 003B checks plus the AV rule — an AV source
  (0x0100 | 0x0400) pending, **no source outside AV**.
- **PRESVC is the authoritative snapshot** (PI ×2, CONTROL, IRQ) taken after the delivery and the
  main re-mask: reads ok, Disc reading = GBI reading, CONTROL 0x8C, INTMR bit 13 = 0, no source
  outside AV, an AV source pending, odd bits / bit 15 / bits 12–14 = 0. Its semantic value is
  `pending_irq`; it selects the block set (`pending & 0x0400` → AUDIO, `pending & 0x0100` → VIDEO)
  and it is the value the ACK writes. No later read changes either: a VIDEO source that appears
  during the AUDIO DMA is not added to the pass, and the ACK does not acknowledge it (the
  references read once and acknowledge what they read).
- **Drains: AUDIO then VIDEO**, one whole-block DMA each (`gbp_avblock_read` → the transport's
  `read_bulk`), into static 32-byte-aligned buffers of the full length, pre-filled with zeros
  outside the timed region and never touched by the CPU during the transfer. The real backend
  (`src/platform/hsp_backend.c`) programs the same registers and polls the same completion flag
  as every 32-byte access, with the length field set to 0x1000 / 0xF00 (both references issue one
  DMA of the whole length: Disc `0x80089c3c`, GBI's ARQ hi queue `0x800617b4`); it refuses to
  start while the engine is busy, bounds the wait (200 ms, operational), never retries, never
  chunks. The argument rule (`gbp_bulk_args_ok`, checked before anything is programmed): length
  > 0, a multiple of 32, ≤ 1 MB; source and destination 32-byte aligned; neither range wraps; the
  transfer stays inside the 1 MB register window of its address (a block never crosses into the
  next register index). Cache: `DCFlushRange` (dcbf: write back + invalidate — no dirty line can be written
  back over the DMA data, the pre-fill reaches memory) before the DMA, `DCInvalidateRange` (dcbi)
  after completion — the Start-up Disc invalidates (`0x800687dc` = dcbi) before its block DMA and
  again in its DMA-done callback, libogc2 invalidates before every EXI/ARAM read DMA. Nothing is
  formatted until both drains are done; VIDEO is never started if the selected AUDIO read failed.
- **A failed drain** (busy / timeout / backend) ends the run: no ACK, no re-arm, statuses
  `audio_dma_busy|timeout|error` / `video_dma_busy|timeout|error`, `drain_uncertain = 1` on a
  timeout (a started DMA whose completion was not seen), teardown `S3_dma_failed`.
- **POSTDRAIN** (PI ×2, CONTROL, IRQ) is an observation only: it never changes `pending_irq`, the
  block set or the ACK value; it must still be consistent (reads ok, Disc = GBI, CONTROL, INTMR,
  no source outside AV — a new unexpected source there means no ACK at all).
- **ACK** exactly once: `IRQ := pending_irq | 0x8000` (u16 replicated, from the PRESVC value),
  attempted before the transport call, completed on rc ok; a failure is `ack_write_failed`,
  uncertain = 1, no re-arm.
- **POSTACK — no source requirement:** the AV bits may read 0 (`boundary=clean`) or 0x0100 /
  0x0400 / 0x0500 (`boundary=pending_av`): data, never `anomaly_source_not_cleared` (that status
  does not exist here). Mandatory: reads ok, Disc = GBI, CONTROL 0x8C, INTMR bit 13 = 0, no
  source outside AV, odd bits 0, **bit 15 = 1**, bits 12–14 = 0 (else `anomaly_postack_shape`).
- **PI clean before the re-arm:** INTSR bit 13 = 0 → no main W1C; = 1 → exactly ONE main W1C and
  one re-read; still 1 → `anomaly_pi_sticky_after_service`, no re-arm. A relatch during the
  service (`relatch=1` at POSTDRAIN / POSTACK) is recorded, not a failure.
- **REARM** exactly once, CPU masked: `t_rearm` read before the call, `IRQ := 0x0000` u16
  replicated; a failure is `rearm_write_failed`, no continuation. **REARMPOST** (PI ×2, CONTROL,
  IRQ, never a W1C): CONTROL 0x8C, INTMR bit 13 = 0, Disc = GBI, odd / bit 15 / high bits 0
  mandatory; the state is classified A (source 0, PI 0), B (AV source, PI 1: the next cause is
  already there), C (AV source, PI 0: keep observing), D (outside AV), E (invalid read-back),
  F (PI 1 without an AV source).
- **NEXTCAUSE:** INTSR polled while masked up to T_NEXT_CAUSE = 500 ms since `t_rearm`
  (operational bound; nothing logged per poll, no W1C); valid only with INTSR bit 13 = 1, an AV
  source and nothing outside AV. None within the bound: `no_next_cause_after_service` — a VALID
  physical result, not a transport failure. **The second cause is never delivered:** INTMR bit 13
  stays 0, `__UnmaskIrq` is never called again, no second ISR, no second service; the teardown's
  stop word `read | 0x8AAA` acknowledges its sources and its single W1C closes the PI bit.
- **W1C budget by construction:** handler 1, main ≤ 1 (POSTACK), NEXTCAUSE 0, teardown ≤ 1 —
  three at most.
- **CONTROL** is written once (the 003A transform) and restored once; a spontaneous change at any
  check is `anomaly_control_changed`.
- **Teardown on every path**, CPU masked first: CONTROL restore → IRQ read → stop word `read |
  0x8AAA` → CLEANUPCHK (≤ 1 W1C) → handler restore → INTMR bit 13 = 0 verified → AR_INFO → FINAL.
  Variants (`TEARDOWNAV variant=`): `stage_a`, `S2_before_unmask`, `S3_service_aborted`,
  `S3_dma_failed`, `S4_ack_failed`, `S3_pi_sticky`, `S4_rearm_failed`, `S4C_rearmpost_invalid`,
  `S4A_rearmed_no_next_cause`, `S4B_next_cause_latched` (also the success path). No silent return
  after the first experimental write; `power_cycle_required` is never cleared; **a console power
  cycle is mandatory** after any run that attempted a write — a completed run too.
- **Raw evidence:** the block buffers are never modified after their DMA; the summaries (CRC-32,
  zero / distinct counts, four 32-byte windows, the first word and GBI's frame-start test on it as
  a raw flag) are computed after the teardown; the whole bytes go to the sidecar
  `GBP-AV-SERVICE-001_avsvc-0001-blocks.bin` (format version 2, `src/gbp/gbp_avdump.h`, parsed by
  `tools/avdump.py`) written on X together with the text log, never during the run. Its 256-byte
  header carries the four identities of the run in 32-byte fields — Test ID
  `GBP-AV-SERVICE-001`, Build ID `avsvc-0001`, app `gbp-av-service-probe`, commit — under a
  strict rule (1 to 31 printable ASCII characters, zero padded; an identity that does not fit is
  an error of the serializer, never a truncation), the pending / drain masks, lengths, per-block
  CRC-32, rc and timings: the same values the text log's header and `SVC` / `BLOCK` records carry,
  so log, sidecar and (later) fixture correlate by identity and by content. A block that was not
  selected is "not present" (length 0 in the sidecar); a failed read is stored as it was left,
  flagged not valid.
- Not a runtime: no framebuffer, video conversion, frame sync, audio playback, KEYPAD, SIO, Link
  Port, BBA, Mobile Adapter, Game Pak logic, callbacks or unbounded loop. Byte 0 of any block never
  feeds a decision.

## Sequence

```text
003A stage  AR_INFO exp=3 → PRESENT gate → PI preconditions → BASE → CONTROL := (v & ~0x10) | 0x0C → P0
            → A1: IRQ := read | 0x8000 → A2: IRQ := 0 → window with INTSR polling ≤ 2000 ms, PI MASKED
            none → no_initial_cause (S2)
CAUSE       EVENT: INTSR bit 13 = 1 (snapshot) → IRQ_Request(26, ext) ONCE → PREUNMASK (003B checks + AV rule)
DELIVERY    __UnmaskIrq ×1 → handler (mask, one W1C, second read) → __MaskIrq (verified)
PRESVC      PI ×2, CONTROL, IRQ → pending_irq (authoritative), drain set = pending & 0x0500
DRAIN       AUDIO 0x1000 (index 8) → VIDEO 0xF00 (index 1), one DMA each, CPU masked, nothing formatted
POSTDRAIN   observation only
ACK         IRQ := pending_irq | 0x8000 → POSTACK (no source requirement) → PI clean (≤ 1 main W1C)
REARM       IRQ := 0x0000 → REARMPOST (A/B/C/D/E/F) → NEXTCAUSE ≤ 500 ms, observed, NEVER delivered
TEARDOWN    CONTROL := original → IRQ read → IRQ := read | 0x8AAA → IRQ read → CLEANUPCHK (≤ 1 W1C)
            → handler restore → MASKCHK → AR_INFO := original → FINAL
POWER CYCLE REQUIRED
```

## Writes and read-only registers

| Side | Written | Read only |
|------|---------|-----------|
| GameCube | `0xCC005012` bits 3–5 (restored); INTSR := 0x2000: handler once, main loop ≤ 1 (POSTACK), teardown ≤ 1; INTMR only through `__UnmaskIrq` (once) and `__MaskIrq` — never stored directly; DSP AR-DMA registers for every transfer | INTSR, INTMR, DSP CSR |
| GBP | TEST (handshake); CONTROL twice (transform, original value); IRQ register at most five times: A1 = read \| 0x8000, A2 = 0, ACK = pending \| 0x8000, REARM = 0, STOP = read \| 0x8AAA | IRQ register (every snapshot), TEST (BASE, P0), **AUDIO block (one whole read), VIDEO block (one whole read)** |
| Not touched | KEYPAD, SIOCTL, SIODATA, BBA | |

## Result codes

`status=` (class in parentheses): `ok_service_rearm_cause_observed` (ok);
`no_next_cause_after_service`, `no_initial_cause`, `first_delivery_timeout` (observation);
`service_completed_with_errors` (errors: the chain completed but restore / transport /
uncertainty not clean; the reason names the first); `abort_stage_a` (reported with the 003A status
name), `abort_handler_install`, `abort_pre_unmask_state`, `abort_unmask`, `abort_bulk_unavailable`
(host only), `abort_presvc_state`, `abort_read_inconsistent` (abort); `abort_transport`,
`ack_write_failed`, `rearm_write_failed` (transport); `audio_dma_busy` / `_timeout` / `_error`,
`video_dma_busy` / `_timeout` / `_error` (dma); `anomaly_reentry`, `anomaly_mask_failure`,
`anomaly_unexpected_source` (reason names the site), `anomaly_control_changed`,
`anomaly_postack_shape`, `anomaly_pi_sticky_after_service`, `anomaly_rearm_state` (anomaly).

## Log records

The 003A stage records (`INITIRQA`, `ARINFO`, `TESTW/TESTR`, `DET`, `PRECOND`, `SNAP/PI/RAW`,
`CONTROL`, `IRQSHAPE`, `CTLW`, `IRQW`, `A1`, `A2`, `WINDOW`, `REGION`), the 003B delivery / ACK
records (`CAUSE`, `IRQ install`, `PREUNMASK`, `UNMASK`, `WAIT`, `HANDLER`, `HANDLERPI`,
`HANDLERPI2`, `DELIVERY`, `ACK`, `POSTACK`, `MAINPICLEANUP`, `IRQ restore`, `MASK`), plus:
`AVSVC start/blocks/policy/policy2/end`, `PREUNMASKAV`, `PRESVC`, `SVC start`, `AUDIOREAD`,
`VIDEOREAD`, `SVCEND`, `POSTDRAIN`, `POSTACKAV`, `PICLEAN`, `REARM`, `REARMPOST`, `NEXTCAUSE`,
`TEARDOWNAV`, `SERVICE pass/rearm`, `COUNTERS`, `BLOCK`, `BLOCKW` (four 32-byte windows per
completed block), `TIMING`, `RESTOREAV`, `STATS`. `tools/probelog.py fixture` turns a run into a
replay script whose `B` lines carry address / length / rc / CRC-32 of each whole-block read; the
bytes come from the sidecar (`tools/avdump.py`).

## Validation (host, no hardware)

`tests/unit/test_gbp_avsvc.c` (3046 checks): the success paths (audio only, video only, both),
the §35 event order, snapshot immutability (0x0400 → 0x0500 during the AUDIO DMA; 0x0500 with a
source change), unexpected sources at PREUNMASK / PRESVC / POSTDRAIN / POSTACK / REARMPOST /
NEXTCAUSE, every DMA failure (busy / timeout / error, AUDIO and VIDEO), ACK / REARM / STOP /
handler-restore / AR_INFO-restore failures, POSTACK 0x8000 / 0x8100 / 0x8400 / 0x8500, PI cleanup
unnecessary / once / sticky, REARMPOST A–F, next cause immediate / delayed / none, zero second
unmask and delivery, the teardown closing a latched cause, the early aborts, attempted/completed
at the transport call, raw buffers preserved, time-base wrap, worst-case lines, ring overflow, the
"never" properties on every run, and the physical prefixes (003A stops at the install; 003B and
004 cut before their ACK: the delivery and the PRESVC reads are physical, the drain meets a
transport with no whole-block read). `tests/unit/test_gbp_avdump.c` (3935 checks): CRC-32
vectors, block summaries, the sidecar round trips and error codes, the mock's bulk model, the
replay's `B` line. Python: `test_avsvc_replay.py` (synthetic log → fixture + sidecar → replay to
the same result; without the sidecar the blocks are reported missing; the physical prefixes),
`test_avdump.py`, `test_poc_audit.py` (profile `avsvc`, synthetic and on the build, the compiled
cache sequence), `test_isr_audit.py` (both handlers of the build), `test_probelog.py`,
`test_artifacts.py`. `make avsvc-audit`: 0 findings; both handlers CLEAN. `make avsvc-dolphin`:
absent → `abort_inconsistent`, GBPlayer model → `abort_control_shape` (Dolphin never reaches the
service; preconditions are never weakened for it).

## Physical procedure (NOT to be requested from this dirty build)

Identical to GBP-INIT-004: GBP attached, no cartridge, PicoAdapterGB in the Link Port untouched,
BBA idle, one controller, one Memory Card, SD2SP2, Swiss. Steps, once a clean, audited and
authorized candidate exists: launch, do not press anything until the screen reports the status
(≈ 3 s worst case), press X once (log + sidecar), press START, switch the console OFF. Expected
files: `sd:/open-gbp/GBP-AV-SERVICE-001_avsvc-0001.log` and
`sd:/open-gbp/GBP-AV-SERVICE-001_avsvc-0001-blocks.bin`.

## Risks (accepted in the design)

A whole-block DMA is the one new variable class (a read of 0x1000 / 0xF00 with the engine, the
registers and the completion routine of every 32-byte access so far; reference-backed in both
drivers); a block read that the device treats differently from the references' reads (unknown:
the POSTDRAIN / POSTACK / NEXTCAUSE readings are what says whether a drained source re-requests);
a DMA timeout leaving the engine busy (the teardown is best-effort; power cycle); a cause latched
during the drain with bit 15 = 0 (tolerated, cleared by the single main W1C); the second cause
left latched until the teardown (by design); every write has physical precedent (0x0000 = A2,
`read | 0x8000` = A1 / ACK, `read | 0x8AAA` = stop).
