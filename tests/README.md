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
tests/mocks/    scripted device models behind src/gbp/gbp_transport.h (PI model, synthetic
                interrupt path, synthetic IRQ-register source/mask model, failure injection)
tests/host/     Python tests (pytest or python3 -m unittest):
                  test_dolinfo.py    synthetic DOL header vectors
                  test_dolpad.py     32-byte padding tool
                  test_gciso.py      disc image parser/extractor (synthetic image)
                  test_gbi_unpack.py GBI unpacker and bin2dol (synthetic packed DOL)
                  test_probelog.py   device-log parser / fixture generator
                  test_hw_fixture.py exact bytes of the hardware captures (probe-0001, init-0001,
                                     initirq-0001, initirqa-0001), what each known driver would read
                                     from them, blockdiff findings
                  test_dolphin_smoke.py runner command line (isolated user dir, OSD override)
                  test_isr_audit.py  one-shot handler audit (synthetic listings + the built object)
                  test_poc_audit.py  GBP-INIT-003A object audit (synthetic listings in both GCC
                                     encodings, the built objects, negative control on the
                                     GBP-INIT-002 interrupt-path object)
                  test_initirqa_replay.py synthetic GBP-INIT-003A log → fixture → replay round trip
                                     (no physical data; files stay under build/)
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
