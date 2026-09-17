# Captures

Hardware traces and captured test data.

Public, sanitized traces that are useful for automated regression tests
may be committed to this directory.

Local or private captures belong under:

- `captures/local/`
- `captures/private/`

Those directories are intentionally ignored by Git.

## fixtures/

| File | Origin | Status |
|------|--------|--------|
| `dolphin-2606a-gbplayer-model-present.gbpreplay` | Dolphin 2606a, `Core.HSPDevice=2`, probe build probe-0001 | **model data**, not hardware |
| `dolphin-2606a-gbplayer-model-absent.gbpreplay` | Dolphin 2606a, no HSP device | **model data**, not hardware |
| `hw-gamecube-nogbp-2026-09-14-probe-0001.gbpreplay` | **SOURCE = physical GameCube, GBP_PRESENT=no** (GBP-BASELINE-NOGBP-001), same DOL probe-0001, log sha256 `03e930ff…c8f9` kept under `captures/local/` | hardware capture, sanitized |
| `hw-gamecube-gbp-2026-09-15-init-0001.gbpreplay` | **SOURCE = physical GameCube, GBP_PRESENT=yes**, GBP-INIT-001 build init-0001 commit a3d9668, log sha256 `d1e90daf…956e` (5497 B) | hardware capture: detection, PI, S0–S5, CONTROL writes |
| `hw-gamecube-nogbp-2026-09-15-init-0001.gbpreplay` | **SOURCE = physical GameCube, GBP_PRESENT=no**, same DOL, log sha256 `97f7cc70…6c5e` (2090 B) | hardware capture: `C1`×32, aborted before any CONTROL write |
| `hw-gamecube-gbp-2026-09-15-initirq-0001.gbpreplay` | **SOURCE = physical GameCube, GBP_PRESENT=yes**, GBP-INIT-002 build initirq-0001 commit 4e3cb43, log sha256 `e7ec3d83…ea1d` (6585 B) | hardware capture: detection, PI, S0–S4, CONTROL writes, physical time base (`T`), interrupt path as it happened (`I i/u/m/r`; the handler never ran, so no IRQ is replayed) |
| `hw-gamecube-gbp-2026-09-15-initirqa-0001.gbpreplay` | **SOURCE = physical GameCube, GBP_PRESENT=yes**, GBP-INIT-003A build initirqa-0001 commit d956b1b, DOL sha256 `8c225bd1…bfa5`, log sha256 `ae911745…2ef8` (13231 B) | hardware capture: detection, PI, BASE/P0, CONTROL transform, IRQ-register writes A1 `0x8AAE` / A2 `0x0000` / stop `0x8FAA` with every raw read, physical time base (`T`), the INTSR poll that saw bit 13 (`P p 00012000`), the single PI W1C (`P a`); PI HSP masked throughout (no `I` lines) |
| `hw-gamecube-gbp-2026-09-15-initirqb-0001.gbpreplay` | **SOURCE = physical GameCube, GBP_PRESENT=yes**, GBP-INIT-003B build initirqb-0001 commit d3da8cd, DOL sha256 `821aa2b2…b757`, log sha256 `bedb1f01…cf7c` (17471 B) | hardware capture: the 003A sequence again (A1 `0x8AAE`, A2 `0x0000`, first cause `0x0400` at the PI 105.29 ms after A2), the handler installed after the latched cause (`I i null`), one unmask with the physical handler record (`I u …`: delivered with INTMR bit 13 = 1, masked inside the handler, one W1C, PI clear afterwards), the main re-mask (`I m`), device ACK `0x8500` read back `0x8000`, stop `0x8FAA`, handler restored (`I r`); no main-loop PI W1C; the source log's `pi_policy=never_unmasked` label is a documented defect of that build |
| `hw-gamecube-gbp-2026-09-16-initirq4-0001.gbpreplay` | **SOURCE = physical GameCube, GBP_PRESENT=yes**, GBP-INIT-004 build initirq4-0001 commit 741630b, DOL sha256 `1da0d7b4…010c`, log sha256 `c9167224…775b` (19247 B) | hardware capture: the 003A sequence again (first cause `0x0400` 105.283 ms after A2, `0x0500` by PREUNMASK-0), the handler installed once (`I i null`), the generation published masked (`I p 0`), one unmask with the physical multi-cycle handler record (`I u …`: delivered with INTMR bit 13 = 1, masked inside, one W1C, PI clear 142 ticks later; latency 89 ticks), the main re-mask (`I m`), device ACK `0x8500` and — 26.0 µs later — POSTACK-0 `0x8400` (source 0x0400 present under bit 15 = 1, CONTROL 0x8C, PI bit 13 clear): the conservative clean boundary ended the run (`anomaly_source_not_cleared`), **no re-arm was written** (4 IRQ writes: A1, A2, ACK, stop `0x8EAA`), handler restored (`I r`); the multi-cycle continuation stays SYNTHETIC |
| `hw-gamecube-gbp-2026-09-16-avsvc-0001.gbpreplay` + `hw-gamecube-gbp-2026-09-16-avsvc-0001-blocks.bin` | **SOURCE = physical GameCube, GBP_PRESENT=yes**, GBP-AV-SERVICE-001 build avsvc-0001 commit d3a6d23, DOL sha256 `d9e6dccd…56ff`, log sha256 `d0324b6d…3713` (23154 B), sidecar sha256 `1c17a2d7…dc1e` (8204 B, format 2, byte-identical copy of the console's file) | hardware capture: the 003A sequence again (first cause `0x0400` 105.289 ms after A2, `0x0500` at PREUNMASK), one delivery through the 003B extended one-shot (`I u`, 72 ticks), PRESVC `0x0500`, AUDIO 0x1000 and VIDEO 0xF00 read by one whole-block DMA each (`B` lines with CRC-32 `fec5e4e7` / `fe45ff08`; bytes in the sidecar), POSTDRAIN `0x0500`, ACK `0x8500`, POSTACK `0x8000`, no main W1C, RE-ARM `0x0000`, REARMPOST `0x0400` with PI bit 13 = 1 (outcome B) 43.9 µs later, next cause never delivered, teardown S4B (stop `0x8FAA` → `0x8AAA`, one `P a`), physical time base; 132 operations replay with 0 mismatches / 0 exhausted / 0 blocks missing / 0 CRC mismatches to `ok_service_rearm_cause_observed`; the same script without the sidecar reports both blocks missing (exit 1) |
| `hw-gamecube-gbp-2026-09-16-video-0001.gbpreplay` + `hw-gamecube-gbp-2026-09-16-video-0001-seq.bin` | **SOURCE = physical GameCube, GBP_PRESENT=yes**, GBP-VIDEO-001 build video-0001 commit 6930dde, DOL sha256 `856d3e91…fd65`, log sha256 `ec3c366c…6527` (270580 B), sidecar sha256 `ce5134ff…e229` (403948 B, `OGBPSEQ1` v1, byte-identical copy of the console's file) | hardware capture: 209 cycles of the repeated drained service through ONE installed 003B one-shot (209 unmasks / 209 ISR entries / 209 ACK / 209 re-arms / 0 reentry / 0 main W1C / 1 teardown W1C), 88 VIDEO 0xF00 and 144 AUDIO 0x1000 whole-block reads all completed, sources 121×0400 / 65×0100 / 23×0500, frame starts at 0, 25, 65 with both predicates agreeing on all 88 blocks, one complete 40-block interval (seq25→seq65, 16.794 ms, 59.547 Hz), target reached with the 210th cause latched and closed by the teardown; status `ok_video_sequence_capture`, restore ok, errors 0. **Only 9 of the 144 AUDIO payloads were preserved by design** (first 8 + last valid): the other 135 `B` lines carry address, length, rc and timing but no bytes and **no CRC**, and the replay reports them as missing blocks. A `B` line carries a CRC-32 only where one was measured: 88/88 VIDEO, 9/144 AUDIO |
| `hw-gamecube-gbp-2026-09-16-vstate-0001.gbpreplay` + `hw-gamecube-gbp-2026-09-16-vstate-0001-vstate.bin` | **SOURCE = physical GameCube, GBP_PRESENT=yes**, GBP-VIDEO-002 build vstate-0001 commit e8f3a69, DOL sha256 `c73d49fa…19b9`, log sha256 `4f30d1cd…576c` (81380 B), sidecar sha256 `6406f244…2639` (2432396 B, `OGBPSEQ1` **v2**, byte-identical copy of the console's file) | hardware capture: 51751 admitted cycles over 8.186 s through ONE installed 003B one-shot; **the script is only the prefix the log records** (003A stage, the four verify cycles, teardown) because the other 51746 cycles are lean by design and kept no per-delivery record. The sidecar is the primary evidence: 489 frame signature records, 209 events, 4 episode descriptors, 81 sampled cycles, 15 preserved raw frames. The settled 274-frame state matches GBI reference table B in all forty blocks. **SERVICE ABORTED at cycle 51750 on a semantic disagreement whose 32 bytes this format could not preserve** — the header says so explicitly and they are not reconstructed |
| `hw-gamecube-gbp-2026-09-17-vstate-0002.gbpreplay` + `hw-gamecube-gbp-2026-09-17-vstate-0002-vstate.bin` | **SOURCE = physical GameCube, GBP_PRESENT=yes**, GBP-VIDEO-002 build vstate-0002 commit 8cbb28d, DOL sha256 `8661e914…b91b`, log sha256 `fb127d79…de2a` (40013 B), sidecar sha256 `f2ed596e…8c91` (12588 B, `OGBPSEQ1` **v3**, byte-identical copy of the console's file) | hardware capture: 518 cycles over 0.0842 s, same prefix-only script rule (513 lean cycles are not in it). **The first physical file of the family carrying a semantic-disagreement diagnostic**: the 96-byte record at `off_diag` 0x10C0 holds the 32 raw bytes of the read that aborted the run (`0101010001010100…05050500`), seven replicas at 0x0100 and the eighth at 0x0500, Disc 0x0500 against GBI 0x0100, differing by exactly the AUDIO source bit 0x0400. Header CRC `bd2a5f27`, total CRC `08514baa`. No structured state was observed and none is claimed: the abort came 0.42 s before the change vstate-0001 recorded |
| `hw-gamecube-gbp-2026-09-14-probe-0001.gbpreplay` | **SOURCE = physical GameCube + Game Boy Player**, GBP-PROBE-001 build probe-0001 commit 55ed6c1, derived from the device log sha256 `98ba20d5…f014` (kept unmodified under `captures/local/`) | hardware capture, sanitized (records only; header/setup in HARDWARE_TESTS.md) |

`.gbpreplay` files are scripts for `src/gbp/gbp_replay.c` (format in its
header), generated by `tools/probelog.py fixture <log>` with the metadata
header prepended; the raw device logs stay unmodified under
`captures/local/` (ignored) and are identified by SHA-256 in the header.

Whole-block reads (GBP-AV-SERVICE-001, executed 2026-09-16) appear in a
script as `B <addr> <len> <rc> [<crc32>]` lines that carry no bytes: the
bytes of a run live in its block sidecar `<TestID>_<BuildID>-blocks.bin`
(format: `src/gbp/gbp_avdump.h`; parser: `tools/avdump.py`), which the
physical fixture keeps next to the script as `<fixture>-blocks.bin`
(`# BLOCKS=`, `# BLOCKS_SHA256=`, `# BLOCKS_SIZE=` in the script's header);
the replay verifies every block it is given against the script's CRC-32
and reports missing blocks instead of inventing them (the probe's buffers
then hold its pre-fill, never physical bytes, and the run exits 1). The
physical GBP-AV-SERVICE-001 fixture above replays end to end with its
sidecar (`tests/host/test_avsvc_replay.py`, `tests/unit/test_gbp_avsvc.c`,
`tests/host/test_hw_fixture.py`, `tests/host/test_avdump.py`); the same
test file also round-trips a synthetic log and sidecar under `build/` and
drives the probe with the physical 003B and 004 fixtures cut before their
device ACK (the delivery and the PRESVC reads are physical; the drain meets
a transport without whole-block reads — nothing after a physical record is
invented). GBP-VIDEO-001 (**physically executed 2026-09-16**) uses a
second, independent sidecar format for a whole bounded capture: `OGBPSEQ1`
(`<TestID>_<BuildID>-seq.bin`, format 1 — the cycle table, the VIDEO and AUDIO
tables and the raw blocks; layout `src/gbp/gbp_avseqdump.h`, parser
`tools/avseq.py`). It does not replace or change the `OGBPBLK1` block sidecar
of GBP-AV-SERVICE-001, which stays at format 2 and byte-identical. The physical
GBP-VIDEO-001 fixture and its sidecar are listed above;
`tests/host/test_video_replay.py` pins their hashes and asserts that no AUDIO
payload was invented for the 135 drains that preserved none. The host round trip
keeps its synthetic log, fixture and sidecar under `build/` only. The physical GBP-AV-SERVICE-001
fixture above doubles as the exact prefix of that experiment's first cycle —
that run is one cycle of its repeated service — and replays through it end to
end with 0 mismatches.

The raw AUDIO / VIDEO bytes of the sidecar are evidence,
recorded and not interpreted (EVIDENCE.md GBP-HW-057/058).

The GBP-INIT-003A fixture above is physical. The same tooling path is also
exercised by `tests/host/test_initirqa_replay.py` on a script generated
from the host mock (marked `# SYNTHETIC` by `--note`) and kept under
`build/`; synthetic scripts are never placed in this directory.
`tests/host/test_initirqb_replay.py` round-trips a mock log of the delivery
stage the same way (its `I u` line carries the extended handler record, the
POSTACK main-loop W1C becomes `P a`), replays the physical 003A fixture
through the 003B probe (it is the real prefix up to the EVENT and stops at
the handler install because that run had no interrupt path) and replays the
physical 003B fixture end to end. The 003B fixture's source log carries
`TEARDOWN start … pi_policy=never_unmasked`, a label defect of build
initirqb-0001 (the shared 003A teardown printed its own fixed policy in a
run that had unmasked once; the same log's `RESTOREB … unmasked=1
masked_again=1` is the primary record); the log and the fixture are kept as
written, later builds print `pi_policy=unmasked_once`, and the replay through
the corrected probe reports that label. The GBP-INIT-004 fixture (2026-09-16)
replays the whole physical run to its real result: one delivery and one ACK,
then `anomaly_source_not_cleared` at POSTACK-0 with no re-arm written — it
carries `I p 0` (the generation publication) and the multi-cycle handler's
record, and no evidence whatsoever about `IRQ := 0` after an ACK or about a
second delivery. `tests/host/test_initirq4_replay.py` also round-trips a
synthetic three-cycle mock log (with the optional `I p <gen>` lines) under
`build/` and drives the 004 probe with the physical 003B fixture cut before
its CONTROL restore — cycle 0 verbatim up to the POSTACK, then the first
re-arm meets an exhausted script; nothing after a physical record is ever
invented. The grammar
has an optional `P p <intsr>` line (the value the next `poll_intsr`
returns) for the INTSR-polling loops of that probe; the polling loops
replay with one time-base read per sample, so poll counters differ from
the device run while every other value is verbatim. The source log of the
003A fixture carries `WINDOW tag=A1 intsr13_seen=1`, a formatter defect of
build initirqa-0001 (the global flag was printed in the A1 record); the
primary records show INTSR bit 13 = 0 throughout A1, the fixture keeps the
log's chronology, and the corrected probe reports `intsr13_in_phase=0`
when it replays it.
