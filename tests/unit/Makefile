# Host-side C unit tests.
#
# These compile shared, hardware-independent modules from src/ with the
# host compiler and run them natively. No devkitPPC required.
#
#   make -C tests/unit          build and run all tests
#   make -C tests/unit clean
#
# Paths are kept relative to this directory on purpose: GNU make cannot
# handle absolute paths containing spaces, and the repository may live in
# such a directory.

ROOT     := ../..
OUTDIR   := $(ROOT)/build/tests/unit
CC       ?= cc
CFLAGS   ?= -std=gnu11 -O1 -g -Wall -Wextra -Wpedantic -Wshadow -Wconversion
CPPFLAGS += -I$(ROOT)/src/common -I$(ROOT)/src/log -I$(ROOT)/src/gbp -I$(ROOT)/tests/mocks

TESTS    := test_ident test_ringlog test_gbp_detect test_gbp_probe test_gbp_replay test_gbp_init test_gbp_init_irq test_gbp_initirqa
BINS     := $(addprefix $(OUTDIR)/,$(TESTS))

COMMON_SRC := $(ROOT)/src/common/opengbp_ident.c
LOG_SRC    := $(ROOT)/src/log/ringlog.c
GBP_SRC    := $(ROOT)/src/gbp/gbp_transport.c $(ROOT)/src/gbp/gbp_probe.c $(ROOT)/src/gbp/gbp_replay.c $(ROOT)/src/gbp/gbp_detect.c $(ROOT)/src/gbp/gbp_init_probe.c $(ROOT)/src/gbp/gbp_rawlog.c $(ROOT)/src/gbp/gbp_init_irq_probe.c $(ROOT)/src/gbp/gbp_regwrite.c $(ROOT)/src/gbp/gbp_initirqa_probe.c
MOCK_SRC   := $(ROOT)/tests/mocks/gbp_mock.c

.PHONY: all run clean
all: run

HW_FIXTURE_GBP   := $(ROOT)/captures/fixtures/hw-gamecube-gbp-2026-09-14-probe-0001.gbpreplay
HW_FIXTURE_NOGBP := $(ROOT)/captures/fixtures/hw-gamecube-nogbp-2026-09-14-probe-0001.gbpreplay
MODEL_FIXTURE_P  := $(ROOT)/captures/fixtures/dolphin-2606a-gbplayer-model-present.gbpreplay
MODEL_FIXTURE_A  := $(ROOT)/captures/fixtures/dolphin-2606a-gbplayer-model-absent.gbpreplay
HW_INIT_GBP      := $(ROOT)/captures/fixtures/hw-gamecube-gbp-2026-09-15-init-0001.gbpreplay
HW_INIT_NOGBP    := $(ROOT)/captures/fixtures/hw-gamecube-nogbp-2026-09-15-init-0001.gbpreplay
HW_INITIRQ_GBP   := $(ROOT)/captures/fixtures/hw-gamecube-gbp-2026-09-15-initirq-0001.gbpreplay

run: $(BINS)
	@set -e; for t in $(BINS); do echo "== $$t"; if [ "$$t" = "$(OUTDIR)/test_gbp_replay" ]; then "$$t" "$(HW_FIXTURE_GBP)" "$(HW_FIXTURE_NOGBP)" "$(MODEL_FIXTURE_P)" "$(MODEL_FIXTURE_A)"; elif [ "$$t" = "$(OUTDIR)/test_gbp_init" ]; then "$$t" "$(HW_INIT_GBP)" "$(HW_INIT_NOGBP)"; elif [ "$$t" = "$(OUTDIR)/test_gbp_init_irq" ]; then "$$t" "$(HW_INIT_GBP)" "$(HW_INIT_NOGBP)" "$(HW_INITIRQ_GBP)"; elif [ "$$t" = "$(OUTDIR)/test_gbp_initirqa" ]; then "$$t" "$(HW_INIT_GBP)" "$(HW_INIT_NOGBP)" "$(HW_INITIRQ_GBP)"; else "$$t"; fi; done

$(OUTDIR)/test_ident: test_ident.c $(COMMON_SRC) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_ident.c $(COMMON_SRC)

$(OUTDIR)/test_ringlog: test_ringlog.c $(LOG_SRC) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_ringlog.c $(LOG_SRC)

$(OUTDIR)/test_gbp_detect: test_gbp_detect.c $(LOG_SRC) $(GBP_SRC) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_detect.c $(LOG_SRC) $(GBP_SRC)

$(OUTDIR)/test_gbp_probe: test_gbp_probe.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_probe.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_replay: test_gbp_replay.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_replay.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_init: test_gbp_init.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_init.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_init_irq: test_gbp_init_irq.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(ROOT)/src/gbp/gbp_irq_oneshot.h | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_init_irq.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_initirqa: test_gbp_initirqa.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(ROOT)/src/gbp/gbp_irq_oneshot.h | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_initirqa.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR):
	mkdir -p $@

clean:
	rm -rf $(OUTDIR)
