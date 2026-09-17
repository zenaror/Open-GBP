# Tests

Host-side automated tests, synthetic hardware models, mocks, trace replay,
and other tests that do not require physical GameCube hardware.

Physical hardware interaction should be requested only when the same
question cannot reasonably be answered here.

## Layout

```text
tests/unit/     C unit tests for hardware-independent modules under src/,
                compiled with the host compiler (make -C tests/unit):
                  test_ident.c       build identity formatter
                  test_ringlog.c     RAM record log (truncation, drop counter)
                  test_gbp_probe.c   GBP-PROBE-001 logic against tests/mocks/gbp_mock.c
                  test_gbp_init.c    GBP-INIT-001 logic: preconditions, snapshots, restore, fail-safe,
                                     replay scripts from the physical handshakes
                  test_gbp_replay.c  trace/replay backend (+ replay of the hardware fixture when given as argv[1])
                  test_gbp_init_irq.c GBP-INIT-002 logic: one-shot handler order, mask/unmask, synthetic
                                     interrupt delivery, physical initirq-0001 replay
                  test_gbp_initirqa.c GBP-INIT-003A logic: A1/A2 writes with PI masked against the
                                     synthetic source/mask model, every abort/restore path, event order,
                                     "never" properties, physical prefixes up to the first experimental
                                     write, the complete physical run initirqa-0001 (2026-09-15) replayed
                                     with the console's time base; --dump-log / --replay modes
                  test_gbp_initirqb.c GBP-INIT-003B logic (delivery of a latched HSP cause): the 003A stage
                                     reused, handler install after the EVENT, one unmask, the extended
                                     one-shot body run by the mock (mask before W1C, one W1C, second read),
                                     device ACK, main W1C budget, every abort/anomaly/restore path, event
                                     order and "never" properties, the TEARDOWN pi_policy label, the physical
                                     003A fixture as the prefix up to the EVENT, the complete physical run
                                     initirqb-0001 (2026-09-15) replayed with the console's time base and the
                                     physical handler record; --dump-log / --replay modes
                  test_gbp_initirq4.c GBP-INIT-004 logic (bounded repeated service: three cycles, two re-arms,
                                     one installed handler): the 003A stage and the 003B cycle service reused,
                                     generation discipline of the multi-cycle handler run by the mock (write-once
                                     slots, poisoned out-of-range slot, one W1C per delivery), REARMPOST A–F,
                                     next-cause wait, every abort/anomaly/restore path of the specification,
                                     the §43 event order and the "never" properties, attempted/completed at the
                                     transport call for every ACK and re-arm, worst-case lines, wrap, ring
                                     overflow; the physical 003A fixture (stops at the install) and the physical
                                     003B fixture as the real prefix of cycle 0 (cut before its CONTROL restore:
                                     the first re-arm meets an exhausted script) and the physical 004 run
                                     initirq4-0001 (2026-09-16) replayed to its real result: one delivery, one
                                     ACK, POSTACK 0x8400, anomaly_source_not_cleared, no re-arm; --dump-log /
                                     --replay modes
                  test_gbp_avdump.c  CRC-32 vectors, the raw AV block helpers (window offsets, summary, records),
                                     the block sidecar (serialize → parse round trips: audio only / video only /
                                     both / none / failed read, every error code), the mock's whole-block read
                                     model, the replay's "B" line with an attached block source
                  test_gbp_avseq.c   GBP-VIDEO-001 sequence core: the VIDEO slots and the AUDIO ping-pong
                                     (a failed drain never overwrites the last valid capture), both frame-start
                                     predicates over all 65536 byte pairs (GBI ⇒ Disc; byte 0 alone never decides),
                                     the boundary lists and intervals, the post-loop summaries, and the OGBPSEQ1
                                     sidecar (round trip, the maximal store, every parse error, identities never
                                     truncated, deterministic bytes)
                  test_gbp_video.c   GBP-VIDEO-001 state machine against the mock: one cycle, the 88-block capture
                                     target, 320 record reuses, alternating and combined sources, snapshot
                                     immutability, eleven predicate cases, the seven admission-budget cases, the
                                     caps, the AUDIO ping-pong, every anomaly and early abort, the handler
                                     lifecycle, the sidecar of a real run and the log capacity; plus the PHYSICAL
                                     GBP-AV-SERVICE-001 fixture replayed as the exact prefix of cycle 0 (that run
                                     is one cycle of this loop: 132 operations, 0 mismatches, the second cycle
                                     refused at the admission point), and the PHYSICAL GBP-VIDEO-001 run of
                                     2026-09-16 (video-0001, commit 6930dde) replayed end to end from its own
                                     fixture and OGBPSEQ1 sidecar: 209 cycles, 232 whole-block reads, 88 VIDEO
                                     CRCs verified, 135 AUDIO reads reported missing because their payload was
                                     never preserved, boundaries 0/25/65, the 40-block frame and the 688 byte-0
                                     exceptions all pinned. Every mock scenario is SYNTHETIC.
                  test_gbp_vsig.c    GBP-VIDEO-002 signature and time base: the per-block checksum against its
                                     PHYSICAL anchor (0xFF0FFF0F / 0x7F0FFF10, reproduced from constructed bytes),
                                     the proof that byte 0 and byte 2 are never read, both predicates exhaustively
                                     over 65 536 byte pairs, the bounded cost histogram (median and p95 taken from
                                     buckets, never from the mean), and the 64-bit time base across the low-word
                                     wrap 0xFFFFFFFF → 0x00000000, including the retry and the proof that a
                                     truncated u32 path really would see time go backwards
                  test_gbp_video_state.c also the GBP-VIDEO-002-R3 policy: the three disagreement classes,
                                     the authoritative composition, the independent unexpected-source guard
                                     (fatal even when the two readings AGREE on 0x0104), the nonfatal
                                     source-serviced path, the majority-extra VIDEO quarantine, the
                                     disc-extra deferral that fabricates nothing, the follow-up lifecycle
                                     across consecutive disagreements, the bounded store and its cap, the
                                     gap statistics, and the v4 round trip and strictness
                  test_gbp_vstate.c  GBP-VIDEO-002 state model: the frame assembler (complete_40, incomplete short
                                     and long, an interval that is not 40, resync, predicate disagreement — 40 is
                                     never assumed and no boundary is ever synthesised), the baseline of three, the
                                     early candidate, the episode state machine with N_STABLE = 3 and
                                     EPISODE_MAX_FRAMES = 60, MAX_EPISODES = 4 with the monitor continuing past it,
                                     the frame and event store caps (which do end a run), the bounded tail, the
                                     safety cap winning over both, the AUDIO ping-pong and the exact memory
                                     arithmetic of every resident store. Every scenario is SYNTHETIC.
                  test_gbp_video_state.c  GBP-VIDEO-002 probe against the mock: nominal_negative, the safety cap
                                     before the target and with an episode open, the two-episode scenario that
                                     removed the early positive stop, the bounded finalisation tail,
                                     no_next_cause, the delivery guard, the AUDIO aggregate policy, predicate
                                     disagreements, byte-0 immunity, the streamed sidecar with its strict parser
                                     and every corruption code, a save failure after a successful teardown, the
                                     immediate-teardown ordering asserted at the hardware moment, and the FULL
                                     nominal scan (798 640 synthetic deliveries, 399 321 VIDEO blocks, 9 983
                                     frames, 120.0 s of valid observation, absolute timestamps crossing the
                                     32-bit boundary, no counter overflow). Every scenario is SYNTHETIC and
                                     there is NO physical GBP-VIDEO-002 fixture.
                  test_gbp_avsvc.c   GBP-AV-SERVICE-001 logic (one delivery → PRESVC → AUDIO/VIDEO whole-block
                                     drains → ACK from the PRESVC value → POSTACK → PI clean → re-arm → next cause
                                     observed, never delivered): the success paths, the §35 event order, snapshot
                                     immutability, unexpected sources at every site, every DMA failure, write and
                                     restore failures, POSTACK 0x8000/0x8100/0x8400/0x8500, the PI cleanup budget,
                                     REARMPOST A–F, next cause immediate / delayed / none, zero second unmask or
                                     delivery, the teardown closing a latched cause, attempted/completed at the
                                     transport call, raw buffers preserved, wrap, worst-case lines, ring overflow,
                                     the "never" properties; the physical 003A fixture (stops at the install) and
                                     the physical 003B / 004 fixtures cut before their ACK as prefixes up to the
                                     PRESVC reads; the physical GBP-AV-SERVICE-001 fixture with its sidecar end to
                                     end (every result field, the sidecar identities/CRCs, the raw bytes in the
                                     buffers, the records; without the sidecar both blocks missing); --dump-log
                                     (log + sidecar) / --replay (fixture [+ sidecar]) modes
tests/mocks/    scripted device models behind src/gbp/gbp_transport.h (PI model, synthetic
                interrupt path with the base, the extended and the multi-cycle handler bodies, synthetic
                IRQ-register source/mask model with an optional re-latch after a W1C, scheduled source
                (re)assertions after the Nth IRQ write, a PI latch lagging the source, ineffective ACK,
                sticky re-arm read-back, generation corruption, CONTROL changing by itself, failure injection,
                a whole-block read model with a deterministic pattern per block, per-index failure injection,
                a drain-clears-the-source rule, a source asserting during the Nth read, a phantom PI cause)
tests/host/     Python tests (pytest or python3 -m unittest):
                  test_dolinfo.py    synthetic DOL header vectors
                  test_dolpad.py     32-byte padding tool
                  test_gciso.py      disc image parser/extractor (synthetic image)
                  test_gbi_unpack.py GBI unpacker and bin2dol (synthetic packed DOL)
                  test_probelog.py   device-log parser / fixture generator (incl. the "B" whole-block read lines)
                  test_avdump.py     tools/avdump.py: the block sidecar parser against the C serializer and against
                                     synthetic files (every error code, the CLI); the physical avsvc-0001 sidecar
                                     (identities whole, every CRC, the raw byte positions recorded not interpreted)
                  test_avseq.py      tools/avseq.py: the Python parser against the C writer on a real synthetic
                                     run, both predicates, the boundary lists, the reference transform and GBI's
                                     per-block checksum (anchored to the PHYSICAL avsvc-0001 block, 0x7F0FFF10 =
                                     entry 0 of both reference tables), and the offline oracle — which reports
                                     reference_content=unavailable without the private inputs and is never a gate
                  test_vstate.py     tools/vstate.py: the format-2, format-3 AND format-4 parsers against the C writer's own
                                     files, the frame / event / episode / cycle decoders, the interval histogram,
                                     the ordering of events by sequence number, the offline oracle, the proof that
                                     the three formats can never misread each other, and the byte-0 property
                                     re-checked on the host implementation. Also the two PHYSICAL sidecars: the
                                     frozen v2 of build vstate-0001 (2026-09-16) must keep parsing with the same
                                     CRCs and section offsets it had the day it was consolidated, and the v3 of
                                     build vstate-0002 (2026-09-17) is re-derived from disk — identity, CRCs,
                                     bounds, the 96-byte semantic-disagreement record, its eight replicas, both
                                     readings and the 0x0400 difference between them. Format 4 (vstate-0003,
                                     not physically executed) adds the 160-byte record array, the 1024-byte
                                     semantic block, the histogram index and every strictness rule of R3.19
                  test_video_replay.py synthetic GBP-VIDEO-001 log → fixture + sequence sidecar → replay round trip
                                     (the regenerated run equals the original) and the physical GBP-AV-SERVICE-001
                                     fixture as the first cycle; asserts that no GBP-VIDEO-001 fixture exists
                  test_avsvc_replay.py synthetic GBP-AV-SERVICE-001 log → fixture + sidecar → replay round trip
                                     (the same result with the sidecar; missing blocks reported without it; a
                                     tampered sidecar rejected); the physical 003A fixture (stops at the install)
                                     and the physical 003B / 004 fixtures cut before their ACK through the probe
                                     (abort_bulk_unavailable at the drain, 0 mismatches); the physical AVSVC
                                     fixture of 2026-09-16 with its sidecar (the physical result, 0 mismatches),
                                     without it (blocks missing, exit 1) and with a tampered sidecar (rejected)
                  test_hw_fixture.py exact bytes of the hardware captures (probe-0001, init-0001,
                                     initirq-0001, initirqa-0001, initirqb-0001, initirq4-0001, video-0001, avsvc-0001 with its
                                     block sidecar: header hashes, regeneration from the raw log, the "B" lines,
                                     the sidecar windows, the raw block positions), what each known driver
                                     would read from them, blockdiff findings, the interrupt path of the
                                     003B run as it happened, the documented label defect of its log
                  test_dolphin_smoke.py runner command line (isolated user dir, OSD override)
                  test_isr_audit.py  one-shot handler audit (synthetic listings incl. the extended body
                                     with its bounded loop, negative controls: second/missing/wrong-value
                                     INTSR store, INTMR store; the built GBP-INIT-002, 003B, 004 and
                                     GBP-AV-SERVICE-001 objects — the multi-cycle handler with its two
                                     compiler-duplicated mask sites; both handlers of the AVSVC build)
                  test_poc_audit.py  object audit, profiles 003a, 003b, 004, avsvc and video (synthetic listings in both
                                     GCC encodings, the built objects, negative controls on the GBP-INIT-002
                                     interrupt-path object and the GBP-INIT-001 INTMR object, profiles
                                     mutually exclusive on the builds; the ACK call site in the shared
                                     service object since GBP-INIT-004; the avsvc call-site counts, forbidden
                                     symbol prefixes and the compiled cache sequence of the whole-block read)
                  test_initirqa_replay.py synthetic GBP-INIT-003A log → fixture → replay round trip
                                     (no physical data; files stay under build/)
                  test_initirqb_replay.py synthetic GBP-INIT-003B log → fixture → replay round trip
                                     (14-number "I u" line, POSTACK "P a"); the physical 003A fixture
                                     through the 003B probe (stops at the handler install); the physical
                                     003B fixture replayed end to end (111 operations, 0 mismatches)
                  test_initirq4_replay.py synthetic GBP-INIT-004 three-cycle log → fixture → replay round
                                     trip (optional "I p <gen>" lines, identical without them); the physical
                                     003A fixture through the 004 probe (stops at the install); the physical
                                     003B fixture as the prefix of cycle 0 (exhausted at the first re-arm,
                                     0 mismatches); the physical 004 fixture (2026-09-16) replayed end to end
                                     to its real result (112 operations, 0 mismatches, no re-arm)
                  test_artifacts.py  checks on the built ELF/DOL (skipped
                                     until `make build` has run)
```

## Running

```bash
make test-host          # both suites
make -C tests/unit      # C only
pytest -q tests/host    # Python only (or: python3 -m unittest discover -s tests/host)
```

Rules of thumb:

- every protocol transformation that can be tested without hardware gets
  a test here first;
- shared C code under `src/` must compile on the host with
  `-Wall -Wextra -Wpedantic -Wconversion` and stay free of libogc
  dependencies, so the same source is verified natively and on PowerPC;
- test files must not contain proprietary data.
