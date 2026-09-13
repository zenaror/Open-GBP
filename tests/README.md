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
                  test_gbp_replay.c  trace/replay backend
tests/mocks/    scripted device models behind src/gbp/gbp_transport.h
tests/host/     Python tests (pytest or python3 -m unittest):
                  test_dolinfo.py    synthetic DOL header vectors
                  test_dolpad.py     32-byte padding tool
                  test_gciso.py      disc image parser/extractor (synthetic image)
                  test_gbi_unpack.py GBI unpacker and bin2dol (synthetic packed DOL)
                  test_probelog.py   device-log parser / fixture generator
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
