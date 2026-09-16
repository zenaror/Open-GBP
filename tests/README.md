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
                                     PRESVC reads; --dump-log (log + sidecar) / --replay (fixture [+ sidecar]) modes
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
                                     synthetic files (every error code, the CLI)
                  test_avsvc_replay.py synthetic GBP-AV-SERVICE-001 log → fixture + sidecar → replay round trip
                                     (the same result with the sidecar; missing blocks reported without it; a
                                     tampered sidecar rejected); the physical 003A fixture (stops at the install)
                                     and the physical 003B / 004 fixtures cut before their ACK through the probe
                                     (abort_bulk_unavailable at the drain, 0 mismatches); no AVSVC fixture exists
                  test_hw_fixture.py exact bytes of the hardware captures (probe-0001, init-0001,
                                     initirq-0001, initirqa-0001, initirqb-0001, initirq4-0001), what each known driver
                                     would read from them, blockdiff findings, the interrupt path of the
                                     003B run as it happened, the documented label defect of its log
                  test_dolphin_smoke.py runner command line (isolated user dir, OSD override)
                  test_isr_audit.py  one-shot handler audit (synthetic listings incl. the extended body
                                     with its bounded loop, negative controls: second/missing/wrong-value
                                     INTSR store, INTMR store; the built GBP-INIT-002, 003B, 004 and
                                     GBP-AV-SERVICE-001 objects — the multi-cycle handler with its two
                                     compiler-duplicated mask sites; both handlers of the AVSVC build)
                  test_poc_audit.py  object audit, profiles 003a, 003b, 004 and avsvc (synthetic listings in both
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
