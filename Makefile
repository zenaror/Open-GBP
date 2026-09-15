# Open-GBP top-level build/test driver.
#
# GameCube code is compiled inside the pinned Docker image (see Dockerfile,
# compose.yaml). Host tests and Dolphin runs execute on the host.
#
#   make env-check      verify container toolchain
#   make build          build every POC (poc/smoke-test, poc/gbp-probe) -> build/poc/*/
#   make test-host      host C unit tests + Python tests (needs build for artifact tests)
#   make inspect        dump ELF/DOL metadata of every POC
#   make test           build + inspect + test-host   (no emulator, no hardware)
#   make smoke-dolphin  run the smoke-test DOL in Dolphin and verify the success criteria
#   make probe-dolphin  run the gbp-probe DOL in Dolphin (HSP device absent and present)
#   make init-dolphin   run the gbp-init-probe DOL in Dolphin (absent → abort; present → full sequence)
#   make initirq-dolphin run the gbp-init-irq-probe DOL in Dolphin (absent → abort; GBPlayer model → shape abort)
#   make initirq-audit  disassemble the one-shot IRQ handler of gbp-init-irq-probe and check what it calls
#   make all            test + smoke-dolphin + probe-dolphin + init-dolphin + initirq-dolphin
#   make shell          interactive shell in the container
#   make clean

SHELL := /bin/bash

export LOCAL_UID ?= $(shell id -u)
export LOCAL_GID ?= $(shell id -g)

COMPOSE     := docker compose
# -T: no pseudo-TTY, so the target also works from scripts/CI.
IN_CONTAINER := $(COMPOSE) run --rm -T dev

PYTHON ?= python3
PYTEST := $(shell command -v pytest 2>/dev/null)

POCS      := smoke-test gbp-probe gbp-init-probe gbp-init-irq-probe
INITIRQ_OUT := build/poc/gbp-init-irq-probe
INITIRQ_DOL := $(INITIRQ_OUT)/gbp-init-irq-probe.dol
INIT_OUT  := build/poc/gbp-init-probe
INIT_DOL  := $(INIT_OUT)/gbp-init-probe.dol
SMOKE_OUT := build/poc/smoke-test
SMOKE_DOL := $(SMOKE_OUT)/smoke-test.dol
PROBE_OUT := build/poc/gbp-probe
PROBE_DOL := $(PROBE_OUT)/gbp-probe.dol

.PHONY: help env-check build inspect test-host test-unit test-python test smoke-dolphin probe-dolphin init-dolphin initirq-dolphin initirq-audit all shell clean

help:
	@sed -n '2,18p' $(firstword $(MAKEFILE_LIST))

env-check:
	$(IN_CONTAINER) sh -c 'set -e; \
	  echo "DEVKITPRO=$$DEVKITPRO"; echo "DEVKITPPC=$$DEVKITPPC"; \
	  for t in powerpc-eabi-gcc powerpc-eabi-g++ powerpc-eabi-objdump elf2dol make git; do printf "%-22s %s\n" $$t "$$(command -v $$t)"; done; \
	  powerpc-eabi-gcc --version | head -n1; \
	  test -f $$DEVKITPRO/libogc2/gamecube_rules && echo "gamecube_rules: ok"; \
	  sed -n "s/^#define _V_STRING //p" $$DEVKITPRO/libogc2/gamecube/include/ogc/libversion.h'

build:
	$(IN_CONTAINER) sh -c 'set -e; for p in $(POCS); do make --no-print-directory -C poc/$$p; done'

inspect:
	@for p in $(POCS); do test -f build/poc/$$p/$$p.dol || { echo "missing build/poc/$$p/$$p.dol; run make build"; exit 1; }; done
	$(IN_CONTAINER) sh -c 'for p in $(POCS); do powerpc-eabi-size build/poc/$$p/$$p.elf; done'
	@for p in $(POCS); do echo "== $$p"; $(PYTHON) tools/dolinfo.py --require-aligned build/poc/$$p/$$p.dol; done

test-unit:
	$(MAKE) --no-print-directory -C tests/unit

test-python:
ifeq ($(PYTEST),)
	$(PYTHON) -m unittest discover -s tests/host -v
else
	$(PYTEST) -q tests/host
endif

test-host: test-unit test-python

test: build inspect test-host

smoke-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(SMOKE_DOL) --build-info $(SMOKE_OUT)/build-info.txt \
	  --report $(SMOKE_OUT)/dolphin-report.json --screen-png $(SMOKE_OUT)/dolphin-screen.png

# Dolphin cannot answer U-GBP-004; these runs only validate runtime, flow
# control, timeouts, logging and the absence of crashes. Run 1: no HSP
# device (GBP absent). Run 2: Dolphin's GBPlayer model (HSPDevice=2).
probe-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(PROBE_DOL) --build-info $(PROBE_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-PROBE DONE .*a_present=0 b_present=0 .*restored=1' \
	  --report $(PROBE_OUT)/dolphin-report-absent.json --screen-png $(PROBE_OUT)/dolphin-screen-absent.png
	$(PYTHON) tools/dolphin_smoke.py --dol $(PROBE_DOL) --build-info $(PROBE_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-PROBE DONE .*a_present=1 b_present=1 .*restored=1' \
	  -C Dolphin.Core.HSPDevice=2 \
	  --report $(PROBE_OUT)/dolphin-report-present.json --screen-png $(PROBE_OUT)/dolphin-screen-present.png

# Dolphin only validates runtime/flow/restore paths for the init probe; its
# GBPlayer model says nothing about the physical CONTROL/IRQ/INTSR behavior.
# Run 2 note: Dolphin's model presents CONTROL = 0x03 at idle (mGBA cartridge
# bits), not the idle shape 0x90 seen on hardware, so the probe correctly
# stops at the shape precondition; the write/restore path is covered by the
# host mocks and replay scripts (tests/unit/test_gbp_init.c).
init-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(INIT_DOL) --build-info $(INIT_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-INIT DONE status=abort_not_present .*written=0 .*arinfo_restored=1' \
	  --report $(INIT_OUT)/dolphin-report-absent.json --screen-png $(INIT_OUT)/dolphin-screen-absent.png
	$(PYTHON) tools/dolphin_smoke.py --dol $(INIT_DOL) --build-info $(INIT_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-INIT DONE status=abort_control_shape reason=control_not_idle_shape verdict=present det=4/4 written=0 .*arinfo_restored=1' \
	  -C Dolphin.Core.HSPDevice=2 \
	  --report $(INIT_OUT)/dolphin-report-present.json --screen-png $(INIT_OUT)/dolphin-screen-present.png

# GBP-INIT-002 in Dolphin: no HSP device → abort_not_present; GBPlayer
# model → abort_control_shape (its idle CONTROL is 0x03, not the 0x90
# shape seen on hardware). Neither run reaches the handler install or the
# unmask; the interrupt path is covered by tests/unit/test_gbp_init_irq.c
# against the synthetic mock. Preconditions are never weakened for Dolphin.
initirq-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(INITIRQ_DOL) --build-info $(INITIRQ_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-INITIRQ DONE status=abort_not_present .*written=0 .*arinfo_restored=1' \
	  --report $(INITIRQ_OUT)/dolphin-report-absent.json --screen-png $(INITIRQ_OUT)/dolphin-screen-absent.png
	$(PYTHON) tools/dolphin_smoke.py --dol $(INITIRQ_DOL) --build-info $(INITIRQ_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-INITIRQ DONE status=abort_control_shape reason=control_not_idle_shape restore=ok .*verdict=present det=4/4 written=0 fired=0 .*arinfo_restored=1' \
	  -C Dolphin.Core.HSPDevice=2 \
	  --report $(INITIRQ_OUT)/dolphin-report-present.json --screen-png $(INITIRQ_OUT)/dolphin-screen-present.png

# Static audit of the one-shot handler actually linked into the DOL: the
# function may only reference the two PI registers, the time base and
# libogc2's __MaskIrq (docs/protocol/INITIALIZATION.md §9 R8).
initirq-audit:
	@test -f $(INITIRQ_OUT)/obj/hsp_backend.o || { echo "missing $(INITIRQ_OUT)/obj/hsp_backend.o; run make build"; exit 1; }
	$(IN_CONTAINER) sh -c 'powerpc-eabi-objdump -dr $(INITIRQ_OUT)/obj/hsp_backend.o > $(INITIRQ_OUT)/hsp_backend.objdump.txt; powerpc-eabi-nm $(INITIRQ_OUT)/gbp-init-irq-probe.elf > $(INITIRQ_OUT)/gbp-init-irq-probe.nm.txt'
	$(PYTHON) tools/isr_audit.py $(INITIRQ_OUT)/hsp_backend.objdump.txt --report $(INITIRQ_OUT)/isr-audit.txt

all: test smoke-dolphin probe-dolphin init-dolphin initirq-dolphin

shell:
	$(COMPOSE) run --rm dev bash

clean:
	rm -rf build/poc build/tests
