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
#   make initirqa-dolphin run the gbp-init-irq-program-probe DOL in Dolphin (absent → abort; GBPlayer model → shape abort)
#   make initirqa-audit  disassemble every object of gbp-init-irq-program-probe: no INTMR store, no unmask/handler
#                       symbols, exactly three IRQ-register write sites (tools/poc_audit.py)
#   make initirqb-dolphin run the gbp-init-irq-deliver-probe DOL in Dolphin (absent → abort_inconsistent; GBPlayer model → shape abort)
#   make initirqb-audit  audit gbp-init-irq-deliver-probe: both one-shot handlers (tools/isr_audit.py) and every object
#                       (tools/poc_audit.py --profile 003b: one __UnmaskIrq site, no INTMR store, four IRQ-register write sites)
#   make initirq4-dolphin run the gbp-init-irq-service-probe DOL in Dolphin (absent → abort_inconsistent; GBPlayer model → shape abort)
#   make initirq4-audit  audit gbp-init-irq-service-probe: the multi-cycle handler (tools/isr_audit.py) and every object
#                       (tools/poc_audit.py --profile 004: one __UnmaskIrq site, no INTMR store, five IRQ-register write sites)
#   make avsvc-dolphin  run the gbp-av-service-probe DOL in Dolphin (absent → abort_inconsistent; GBPlayer model → shape abort)
#   make video-dolphin  run the gbp-video-capture-probe DOL in Dolphin (absent → abort_inconsistent; GBPlayer model → shape abort)
#   make video-audit    audit gbp-video-capture-probe: both 002/003B handlers and every object (profile video)
#   make vstate-dolphin run the gbp-video-state-probe DOL in Dolphin (absent -> abort_inconsistent; GBPlayer model -> shape abort)
#   make swiss          export every built DOL to build/swiss/NN-short/boot.dol with an
#                       INDEX.txt, so the right build is obvious in Swiss (numbers are
#                       stable; the copy is byte-identical and build/poc stays the authority)
#   make swiss-check    validate tools/swiss-layout.tsv without building anything
#   make prehandler-wait build the pre-handler masked-wait DIAGNOSTIC (default 5000 ms;
#                       PREWAIT_MS=N to change). Separate build id and directory: it is
#                       NOT GBP-VIDEO-003 and NOT the vstate-0004 reference DOL
#   make vstate-audit   audit gbp-video-state-probe: both 002/003B handlers and every object (profile vstate:
#                       one __UnmaskIrq site, no INTMR store, 3 + 1 + 3 IRQ-register write sites, the 64-bit
#                       time base through gettime() only, and NO filesystem reference in the capture path)
#   make avsvc-audit    audit gbp-av-service-probe: both 002/003B handlers (tools/isr_audit.py) and every object
#                       (tools/poc_audit.py --profile avsvc: one __UnmaskIrq site, no INTMR store, five IRQ-register write sites,
#                       two whole-block read sites, no KEYPAD/SIO/BBA/GX/audio-output symbol)
#   make all            test + smoke-dolphin + probe-dolphin + init-dolphin + initirq-dolphin + initirqa-dolphin + initirqb-dolphin + initirq4-dolphin + avsvc-dolphin
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

POCS      := smoke-test gbp-probe gbp-init-probe gbp-init-irq-probe gbp-init-irq-program-probe gbp-init-irq-deliver-probe gbp-init-irq-service-probe gbp-av-service-probe gbp-video-capture-probe gbp-video-state-probe gbp-video-color-probe gbp-video-stream-probe
AVSVC_OUT := build/poc/gbp-av-service-probe
AVSVC_DOL := $(AVSVC_OUT)/gbp-av-service-probe.dol
VIDEO_OUT := build/poc/gbp-video-capture-probe
VIDEO_DOL := $(VIDEO_OUT)/gbp-video-capture-probe.dol
VSTATE_OUT := build/poc/gbp-video-state-probe
VSTATE_DOL := $(VSTATE_OUT)/gbp-video-state-probe.dol
COLOR_OUT := build/poc/gbp-video-color-probe
STREAM_OUT := build/poc/gbp-video-stream-probe
STREAM_DOL := $(STREAM_OUT)/gbp-video-stream-probe.dol
COLOR_DOL := $(COLOR_OUT)/gbp-video-color-probe.dol
STIM_OUT  := build/stimulus/agb-color-bars
STIM_ROM  := $(STIM_OUT)/agb-color-bars.gba
INITIRQ4_OUT := build/poc/gbp-init-irq-service-probe
INITIRQ4_DOL := $(INITIRQ4_OUT)/gbp-init-irq-service-probe.dol
INITIRQB_OUT := build/poc/gbp-init-irq-deliver-probe
INITIRQB_DOL := $(INITIRQB_OUT)/gbp-init-irq-deliver-probe.dol
INITIRQA_OUT := build/poc/gbp-init-irq-program-probe
INITIRQA_DOL := $(INITIRQA_OUT)/gbp-init-irq-program-probe.dol
INITIRQ_OUT := build/poc/gbp-init-irq-probe
INITIRQ_DOL := $(INITIRQ_OUT)/gbp-init-irq-probe.dol
INIT_OUT  := build/poc/gbp-init-probe
INIT_DOL  := $(INIT_OUT)/gbp-init-probe.dol
SMOKE_OUT := build/poc/smoke-test
SMOKE_DOL := $(SMOKE_OUT)/smoke-test.dol
PROBE_OUT := build/poc/gbp-probe
PROBE_DOL := $(PROBE_OUT)/gbp-probe.dol

.PHONY: help env-check build inspect test-host test-unit test-python test stimulus color-dolphin color-audit stream-audit stream-dolphin smoke-dolphin probe-dolphin init-dolphin initirq-dolphin initirq-audit initirqa-dolphin initirqa-audit initirqb-dolphin initirqb-audit initirq4-dolphin initirq4-audit avsvc-dolphin avsvc-audit video-dolphin video-audit vstate-dolphin vstate-audit prehandler-wait swiss swiss-check all shell clean

help:
	@sed -n '2,35p' $(firstword $(MAKEFILE_LIST))

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
# libogc2's __MaskIrq (docs/protocol/INITIALIZATION.md §9 R8). The same
# step dumps the GBP-INIT-001 INTMR object (the only direct INTMR store in
# the tree) as the negative-control input of tests/host/test_poc_audit.py.
initirq-audit:
	@test -f $(INITIRQ_OUT)/obj/hsp_backend_irq.o || { echo "missing $(INITIRQ_OUT)/obj/hsp_backend_irq.o; run make build"; exit 1; }
	$(IN_CONTAINER) sh -c 'powerpc-eabi-objdump -dr $(INITIRQ_OUT)/obj/hsp_backend_irq.o > $(INITIRQ_OUT)/hsp_backend_irq.objdump.txt; powerpc-eabi-nm $(INITIRQ_OUT)/gbp-init-irq-probe.elf > $(INITIRQ_OUT)/gbp-init-irq-probe.nm.txt; test -f $(INIT_OUT)/obj/hsp_backend_intmr.o && powerpc-eabi-objdump -dr $(INIT_OUT)/obj/hsp_backend_intmr.o > $(INIT_OUT)/hsp_backend_intmr.objdump.txt || true'
	$(PYTHON) tools/isr_audit.py $(INITIRQ_OUT)/hsp_backend_irq.objdump.txt --report $(INITIRQ_OUT)/isr-audit.txt

# GBP-INIT-003A in Dolphin: no HSP device → abort_inconsistent (Dolphin
# answers every read with zeros, so the FF handshake matches 1/4 — the
# physical console without a GBP answered C1 ×32 = ABSENT, see the
# init-0001 nogbp fixture; GBP-INIT-002 reports the same run as
# abort_not_present/inconsistent because it does not split the two);
# GBPlayer model → abort_control_shape (its idle CONTROL is 0x03; the IRQ
# shape is checked only after CONTROL). Neither run reaches a CONTROL or
# IRQ write; the write path is covered by tests/unit/test_gbp_initirqa.c
# against the synthetic source/mask model. Preconditions are never
# weakened for Dolphin.
initirqa-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(INITIRQA_DOL) --build-info $(INITIRQA_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-INITIRQA DONE status=abort_inconsistent reason=inconsistent restore=ok restore_reason=- verdict=inconsistent det=1/4 written=0 irq_attempted=0 irq_completed=0 .*arinfo_restore_ok=1 power_cycle_required=0' \
	  --report $(INITIRQA_OUT)/dolphin-report-absent.json --screen-png $(INITIRQA_OUT)/dolphin-screen-absent.png
	$(PYTHON) tools/dolphin_smoke.py --dol $(INITIRQA_DOL) --build-info $(INITIRQA_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-INITIRQA DONE status=abort_control_shape reason=control_not_idle_shape restore=ok restore_reason=- verdict=present det=4/4 written=0 irq_attempted=0 irq_completed=0 .*arinfo_restore_ok=1 power_cycle_required=0' \
	  -C Dolphin.Core.HSPDevice=2 \
	  --report $(INITIRQA_OUT)/dolphin-report-present.json --screen-png $(INITIRQA_OUT)/dolphin-screen-present.png

# Static audit of every object linked into gbp-init-irq-program-probe
# (tools/poc_audit.py): hsp_backend_irq.o not linked, no reference to
# __UnmaskIrq / IRQ_Request / IRQ_Free / the one-shot handler, no store to
# PI INTMR, exactly three gbp_regwrite_irq_u16 call sites (A1, A2, STOP)
# and two gbp_regwrite_control_byte call sites (EXP, RESTORE).
initirqa-audit:
	@test -d $(INITIRQA_OUT)/obj || { echo "missing $(INITIRQA_OUT)/obj; run make build"; exit 1; }
	$(IN_CONTAINER) sh -c 'set -e; mkdir -p $(INITIRQA_OUT)/audit; rm -f $(INITIRQA_OUT)/audit/*.objdump.txt; for o in $(INITIRQA_OUT)/obj/*.o; do powerpc-eabi-objdump -dr "$$o" > "$(INITIRQA_OUT)/audit/$$(basename "$$o" .o).objdump.txt"; done; powerpc-eabi-nm $(INITIRQA_OUT)/gbp-init-irq-program-probe.elf > $(INITIRQA_OUT)/audit/elf.nm.txt'
	$(PYTHON) tools/poc_audit.py $(INITIRQA_OUT)/audit --report $(INITIRQA_OUT)/poc-audit.txt

# GBP-INIT-003B in Dolphin: the same two stage-A aborts as GBP-INIT-003A
# (no HSP device → abort_inconsistent; GBPlayer model → abort_control_shape
# on its idle CONTROL 0x03). Neither run reaches a CONTROL or IRQ write, the
# handler install or the unmask; the delivery stage is covered by
# tests/unit/test_gbp_initirqb.c against the synthetic mock. Preconditions
# are never weakened for Dolphin; the OSD is disabled by the runner.
initirqb-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(INITIRQB_DOL) --build-info $(INITIRQB_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-INITIRQB DONE status=abort_inconsistent reason=inconsistent restore=ok restore_reason=- verdict=inconsistent det=1/4 written=0 irq_attempted=0 irq_completed=0 ctl_exp=0/0 a1=0/0 a2=0/0 ack=0/0 stop=0/0 ctl_restore=0/0 uncertain=0 cause=0 t_event=0 handler=0 old=\? preunmask=0/- unmasked=0 fired=0 count=0 .*main_pi_w1c=0 site=- sticky=0 .*handler_restored=-1 mask_ok=-1 arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1' \
	  --report $(INITIRQB_OUT)/dolphin-report-absent.json --screen-png $(INITIRQB_OUT)/dolphin-screen-absent.png
	$(PYTHON) tools/dolphin_smoke.py --dol $(INITIRQB_DOL) --build-info $(INITIRQB_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-INITIRQB DONE status=abort_control_shape reason=control_not_idle_shape restore=ok restore_reason=- verdict=present det=4/4 written=0 irq_attempted=0 irq_completed=0 ctl_exp=0/0 a1=0/0 a2=0/0 ack=0/0 stop=0/0 ctl_restore=0/0 uncertain=0 cause=0 t_event=0 handler=0 old=\? preunmask=0/- unmasked=0 fired=0 count=0 .*main_pi_w1c=0 site=- sticky=0 .*handler_restored=-1 mask_ok=-1 arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1' \
	  -C Dolphin.Core.HSPDevice=2 \
	  --report $(INITIRQB_OUT)/dolphin-report-present.json --screen-png $(INITIRQB_OUT)/dolphin-screen-present.png

# Static audit of gbp-init-irq-deliver-probe: tools/isr_audit.py on both
# one-shot bodies linked into the DOL (only __MaskIrq called, exactly one
# INTSR store of 0x2000 after the mask, no INTMR store, loop allowed) and
# tools/poc_audit.py --profile 003b on every object (hsp_backend_irq.o
# linked, hsp_backend_intmr.o and the 001/002 probes not; __UnmaskIrq from
# h_irq_unmask only; IRQ_Request from h_irq_install/h_irq_restore only;
# __MaskIrq from h_irq_mask and the two handlers only; no INTMR store;
# gbp_regwrite_irq_u16 3 + 1 call sites; main.o uses the ext constructor).
initirqb-audit:
	@test -d $(INITIRQB_OUT)/obj || { echo "missing $(INITIRQB_OUT)/obj; run make build"; exit 1; }
	$(IN_CONTAINER) sh -c 'set -e; mkdir -p $(INITIRQB_OUT)/audit; rm -f $(INITIRQB_OUT)/audit/*.objdump.txt; for o in $(INITIRQB_OUT)/obj/*.o; do powerpc-eabi-objdump -dr "$$o" > "$(INITIRQB_OUT)/audit/$$(basename "$$o" .o).objdump.txt"; done; powerpc-eabi-nm $(INITIRQB_OUT)/gbp-init-irq-deliver-probe.elf > $(INITIRQB_OUT)/audit/elf.nm.txt'
	$(PYTHON) tools/isr_audit.py $(INITIRQB_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr_ext --report $(INITIRQB_OUT)/isr-audit-ext.txt
	$(PYTHON) tools/isr_audit.py $(INITIRQB_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr --report $(INITIRQB_OUT)/isr-audit-base.txt
	$(PYTHON) tools/poc_audit.py $(INITIRQB_OUT)/audit --profile 003b --report $(INITIRQB_OUT)/poc-audit.txt

# GBP-INIT-004 in Dolphin: the same two stage-A aborts as GBP-INIT-003A/003B
# (no HSP device → abort_inconsistent; GBPlayer model → abort_control_shape
# on its idle CONTROL 0x03). Neither run reaches a CONTROL or IRQ write, the
# handler install, an unmask or the multi-cycle path; the cycles are covered
# by tests/unit/test_gbp_initirq4.c against the synthetic mock. Preconditions
# are never weakened for Dolphin; the OSD is disabled by the runner.
initirq4-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(INITIRQ4_DOL) --build-info $(INITIRQ4_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-INITIRQ4 DONE status=abort_inconsistent reason=inconsistent restore=ok restore_reason=- teardown=stage_a verdict=inconsistent det=1/4 written=0 irq_attempted=0 irq_completed=0 ctl_exp=0/0 a1=0/0 a2=0/0 stop=0/0 ctl_restore=0/0 uncertain=0 cause=0 t_event=0 handler=0 old=\? cycles=0/3 completed=0 deliveries=0 acks=0 rearms=0/0 next_causes=0 unexpected=0 reentry=0 timeouts=0 gen_errors=0 entries=0 isr_w1c=0 main_w1c=0 teardown_w1c=0 control_ok=1 pi_sticky_final=0 .*handler_restored=-1 mask_ok=-1 arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1' \
	  --report $(INITIRQ4_OUT)/dolphin-report-absent.json --screen-png $(INITIRQ4_OUT)/dolphin-screen-absent.png
	$(PYTHON) tools/dolphin_smoke.py --dol $(INITIRQ4_DOL) --build-info $(INITIRQ4_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-INITIRQ4 DONE status=abort_control_shape reason=control_not_idle_shape restore=ok restore_reason=- teardown=stage_a verdict=present det=4/4 written=0 irq_attempted=0 irq_completed=0 ctl_exp=0/0 a1=0/0 a2=0/0 stop=0/0 ctl_restore=0/0 uncertain=0 cause=0 t_event=0 handler=0 old=\? cycles=0/3 completed=0 deliveries=0 acks=0 rearms=0/0 next_causes=0 unexpected=0 reentry=0 timeouts=0 gen_errors=0 entries=0 isr_w1c=0 main_w1c=0 teardown_w1c=0 control_ok=1 pi_sticky_final=0 .*handler_restored=-1 mask_ok=-1 arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1' \
	  -C Dolphin.Core.HSPDevice=2 \
	  --report $(INITIRQ4_OUT)/dolphin-report-present.json --screen-png $(INITIRQ4_OUT)/dolphin-screen-present.png

# Static audit of gbp-init-irq-service-probe: tools/isr_audit.py on the
# multi-cycle handler linked into the DOL (only __MaskIrq called, exactly one
# INTSR store of 0x2000 after the mask, no INTMR store, loop allowed) and
# tools/poc_audit.py --profile 004 on every object (hsp_backend_irq_multi.o
# linked; hsp_backend_irq.o, hsp_backend_intmr.o and the 001/002/003B probes
# not; __UnmaskIrq from hm_irq_unmask only; IRQ_Request from hm_irq_install/
# hm_irq_restore only; __MaskIrq from hm_irq_mask and the handler only; no
# INTMR store; gbp_regwrite_irq_u16 3 + 1 + 1 call sites; main.o uses the
# multi constructor).
initirq4-audit:
	@test -d $(INITIRQ4_OUT)/obj || { echo "missing $(INITIRQ4_OUT)/obj; run make build"; exit 1; }
	$(IN_CONTAINER) sh -c 'set -e; mkdir -p $(INITIRQ4_OUT)/audit; rm -f $(INITIRQ4_OUT)/audit/*.objdump.txt; for o in $(INITIRQ4_OUT)/obj/*.o; do powerpc-eabi-objdump -dr "$$o" > "$(INITIRQ4_OUT)/audit/$$(basename "$$o" .o).objdump.txt"; done; powerpc-eabi-nm $(INITIRQ4_OUT)/gbp-init-irq-service-probe.elf > $(INITIRQ4_OUT)/audit/elf.nm.txt'
	$(PYTHON) tools/isr_audit.py $(INITIRQ4_OUT)/audit/hsp_backend_irq_multi.objdump.txt --symbol hsp_backend_oneshot_isr_multi --report $(INITIRQ4_OUT)/isr-audit-multi.txt
	$(PYTHON) tools/poc_audit.py $(INITIRQ4_OUT)/audit --profile 004 --report $(INITIRQ4_OUT)/poc-audit.txt

# GBP-AV-SERVICE-001 in Dolphin: the same two stage-A aborts as GBP-INIT-003A/003B/004
# (no HSP device → abort_inconsistent; GBPlayer model → abort_control_shape on its
# idle CONTROL 0x03). Neither run reaches a CONTROL or IRQ write, the handler
# install, the unmask or a whole-block read; the service is covered by
# tests/unit/test_gbp_avsvc.c against the synthetic mock. Preconditions are never
# weakened for Dolphin (it is acceptable that Dolphin never executes the service);
# the OSD is disabled by the runner.
avsvc-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(AVSVC_DOL) --build-info $(AVSVC_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-AVSVC DONE status=abort_inconsistent class=abort reason=inconsistent restore=ok restore_reason=- teardown=stage_a verdict=inconsistent det=1/4 written=0 irq_attempted=0 irq_completed=0 ctl_exp=0/0 a1=0/0 a2=0/0 ack=0/0 rearm=0/0 stop=0/0 ctl_restore=0/0 uncertain=0 cause=0 t_event=0 handler=0 old=\? unmasked=0 fired=0 count=0 latency_ticks=0 pending=0000 drain=0000 drains=0/0/0 audio=-/0000 video=-/0000 drain_uncertain=0 ack_value=0000 postack_irq=0000 source_after_ack=0000 relatch=0/0 main_w1c=0 pi_clean=0 sticky=0 rearmpost=- next_cause=0 immediate=0 dt_next=0 unexpected=0000 site=- isr_w1c=0 teardown_w1c=0 control_ok=1 pi_sticky_final=0 .*arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1' \
	  --report $(AVSVC_OUT)/dolphin-report-absent.json --screen-png $(AVSVC_OUT)/dolphin-screen-absent.png
	$(PYTHON) tools/dolphin_smoke.py --dol $(AVSVC_DOL) --build-info $(AVSVC_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-AVSVC DONE status=abort_control_shape class=abort reason=control_not_idle_shape restore=ok restore_reason=- teardown=stage_a verdict=present det=4/4 written=0 irq_attempted=0 irq_completed=0 ctl_exp=0/0 a1=0/0 a2=0/0 ack=0/0 rearm=0/0 stop=0/0 ctl_restore=0/0 uncertain=0 cause=0 t_event=0 handler=0 old=\? unmasked=0 fired=0 count=0 latency_ticks=0 pending=0000 drain=0000 drains=0/0/0 audio=-/0000 video=-/0000 drain_uncertain=0 ack_value=0000 postack_irq=0000 source_after_ack=0000 relatch=0/0 main_w1c=0 pi_clean=0 sticky=0 rearmpost=- next_cause=0 immediate=0 dt_next=0 unexpected=0000 site=- isr_w1c=0 teardown_w1c=0 control_ok=1 pi_sticky_final=0 .*arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1' \
	  -C Dolphin.Core.HSPDevice=2 \
	  --report $(AVSVC_OUT)/dolphin-report-present.json --screen-png $(AVSVC_OUT)/dolphin-screen-present.png

# Static audit of gbp-av-service-probe: tools/isr_audit.py on both one-shot
# bodies of hsp_backend_irq.o (the 003B extended one is the handler installed;
# only __MaskIrq called, exactly one INTSR store of 0x2000 after the mask, no
# INTMR store) and tools/poc_audit.py --profile avsvc on every object
# (hsp_backend_irq.o linked; hsp_backend_irq_multi.o, hsp_backend_intmr.o and
# the 001/002/003B/004 probe objects not; __UnmaskIrq from h_irq_unmask only;
# IRQ_Request from h_irq_install/h_irq_restore only; __MaskIrq from h_irq_mask
# and the two handlers only; no INTMR store; gbp_regwrite_irq_u16 3 + 1 + 1
# call sites; gbp_avblock_read exactly twice from the probe; the deliver and
# the ACK-from-a-given-value service functions exactly once from the probe;
# no ARQ/AR/AUDIO/ASND/GX/net/DSP/SI symbol in any object; main.o uses the ext
# constructor, the probe entry and the sidecar writer).
avsvc-audit:
	@test -d $(AVSVC_OUT)/obj || { echo "missing $(AVSVC_OUT)/obj; run make build"; exit 1; }
	$(IN_CONTAINER) sh -c 'set -e; mkdir -p $(AVSVC_OUT)/audit; rm -f $(AVSVC_OUT)/audit/*.objdump.txt; for o in $(AVSVC_OUT)/obj/*.o; do powerpc-eabi-objdump -dr "$$o" > "$(AVSVC_OUT)/audit/$$(basename "$$o" .o).objdump.txt"; done; powerpc-eabi-nm $(AVSVC_OUT)/gbp-av-service-probe.elf > $(AVSVC_OUT)/audit/elf.nm.txt'
	$(PYTHON) tools/isr_audit.py $(AVSVC_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr_ext --report $(AVSVC_OUT)/isr-audit-ext.txt
	$(PYTHON) tools/isr_audit.py $(AVSVC_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr --report $(AVSVC_OUT)/isr-audit-base.txt
	$(PYTHON) tools/poc_audit.py $(AVSVC_OUT)/audit --profile avsvc --report $(AVSVC_OUT)/poc-audit.txt

# GBP-VIDEO-001 in Dolphin: the same two stage-A aborts as GBP-INIT-003A/003B/004 and
# GBP-AV-SERVICE-001 (no HSP device → abort_inconsistent; GBPlayer model → abort_control_shape
# on its idle CONTROL 0x03). Neither run reaches a CONTROL or IRQ write, the handler install,
# an unmask or a whole-block read, so the repeated service is never exercised here; it is
# covered by tests/unit/test_gbp_video.c against the synthetic mock and by the physical
# GBP-AV-SERVICE-001 fixture replayed as the first cycle. Preconditions are never weakened for
# Dolphin (it is acceptable that Dolphin never executes the loop); the OSD is disabled by the runner.
video-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(VIDEO_DOL) --build-info $(VIDEO_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-VIDEO DONE status=abort_inconsistent class=abort reason=inconsistent restore=ok restore_reason=- teardown=stage_a verdict=inconsistent det=1/4 written=0 irq_attempted=0 irq_completed=0 uncertain=0 service=failed service_reason=inconsistent capture=early_failure deliveries=0 video=0/0 audio=0/0 audio_raw=0 next_cause_at_end=0 boundaries_gbi=0 boundaries_disc=0 complete_gbi=0 complete_disc=0 reference_content=offline cause=0 t_event=0 handler=0 old=\? unmasks=0 lean=0 verify=0 t0=0 deadline=0 refusal=- unexpected=0000 site=- isr_w1c=0 main_w1c=0 teardown_w1c=0 control_ok=1 pi_sticky_final=0 .*arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1' \
	  --report $(VIDEO_OUT)/dolphin-report-absent.json --screen-png $(VIDEO_OUT)/dolphin-screen-absent.png
	$(PYTHON) tools/dolphin_smoke.py --dol $(VIDEO_DOL) --build-info $(VIDEO_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-VIDEO DONE status=abort_control_shape class=abort reason=control_not_idle_shape restore=ok restore_reason=- teardown=stage_a verdict=present det=4/4 written=0 irq_attempted=0 irq_completed=0 uncertain=0 service=failed service_reason=control_not_idle_shape capture=early_failure deliveries=0 video=0/0 audio=0/0 audio_raw=0 next_cause_at_end=0 boundaries_gbi=0 boundaries_disc=0 complete_gbi=0 complete_disc=0 reference_content=offline cause=0 t_event=0 handler=0 old=\? unmasks=0 lean=0 verify=0 t0=0 deadline=0 refusal=- unexpected=0000 site=- isr_w1c=0 main_w1c=0 teardown_w1c=0 control_ok=1 pi_sticky_final=0 .*arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1' \
	  -C Dolphin.Core.HSPDevice=2 \
	  --report $(VIDEO_OUT)/dolphin-report-present.json --screen-png $(VIDEO_OUT)/dolphin-screen-present.png

# Static audit of gbp-video-capture-probe: tools/isr_audit.py on both one-shot bodies of
# hsp_backend_irq.o (the 003B extended one is the handler installed; only __MaskIrq called,
# exactly one INTSR store of 0x2000 after the mask, no INTMR store) and tools/poc_audit.py
# --profile video on every object (hsp_backend_irq.o linked; hsp_backend_irq_multi.o,
# hsp_backend_intmr.o and the 001/002/003B/004/AVSVC probe objects not; __UnmaskIrq from
# h_irq_unmask only; IRQ_Request from h_irq_install/h_irq_restore only; __MaskIrq from
# h_irq_mask and the two handlers only; no INTMR store; gbp_regwrite_irq_u16 3 + 1 + 1 call
# sites; gbp_avblock_read exactly twice from the probe; the deliver and the ACK-from-a-given-value
# service functions once each from the probe; no ARQ/AR/AUDIO/ASND/GX/net/DSP/SI symbol in any
# object; main.o uses the ext constructor, the probe entry and the sidecar writer).
video-audit:
	@test -d $(VIDEO_OUT)/obj || { echo "missing $(VIDEO_OUT)/obj; run make build"; exit 1; }
	$(IN_CONTAINER) sh -c 'set -e; mkdir -p $(VIDEO_OUT)/audit; rm -f $(VIDEO_OUT)/audit/*.objdump.txt; for o in $(VIDEO_OUT)/obj/*.o; do powerpc-eabi-objdump -dr "$$o" > "$(VIDEO_OUT)/audit/$$(basename "$$o" .o).objdump.txt"; done; powerpc-eabi-nm $(VIDEO_OUT)/gbp-video-capture-probe.elf > $(VIDEO_OUT)/audit/elf.nm.txt'
	$(PYTHON) tools/isr_audit.py $(VIDEO_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr_ext --report $(VIDEO_OUT)/isr-audit-ext.txt
	$(PYTHON) tools/isr_audit.py $(VIDEO_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr --report $(VIDEO_OUT)/isr-audit-base.txt
	$(PYTHON) tools/poc_audit.py $(VIDEO_OUT)/audit --profile video --report $(VIDEO_OUT)/poc-audit.txt

# GBP-VIDEO-002 in Dolphin: the same two stage-A aborts as every probe since GBP-INIT-003A.
# Dolphin's GBPlayer model says nothing about the physical VIDEO stream, and the 003A
# preconditions are NEVER relaxed to make it "pass": both runs stop before any CONTROL or IRQ
# write, before the handler install, before any unmask and before any whole-block read, so the
# long scan itself is never entered. Its logic is covered by tests/unit/test_gbp_video_state.c
# against the synthetic mock. OSD messages are off (tools/dolphin_smoke.py).
vstate-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(VSTATE_DOL) --build-info $(VSTATE_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-VSTATE DONE status=abort_inconsistent class=abort reason=inconsistent stop=failure restore=ok restore_reason=- teardown=stage_a verdict=inconsistent det=1/4 service=failed service_reason=inconsistent deliveries=0 video=0/0 audio=0 frames=0 complete=0 incomplete=0 resync=0 baseline=never_established baseline_s=0.000 valid_s=0.000 capture_s=0.000 safety_s=0.000 target_s=120 limit_s=180 structured=not_observed episodes=0 stable=0 unstable=0 not_preserved=0 episode_store_full=0 tail_frames=0 tail_truncated=0 frame_store_full=0 event_store_full=0 events=0 boundaries_disc=0 boundaries_gbi=0 disagreements=0 reference_match=offline next_cause_at_end=0 handler=0 restored=-1 mask_ok=-1 isr_w1c=0 main_w1c=0 teardown_w1c=0 control_ok=1 pi_sticky_final=0 uncertain=0 overflow=0 arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1' \
	  --report $(VSTATE_OUT)/dolphin-report-absent.json --screen-png $(VSTATE_OUT)/dolphin-screen-absent.png
	$(PYTHON) tools/dolphin_smoke.py --dol $(VSTATE_DOL) --build-info $(VSTATE_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-VSTATE DONE status=abort_control_shape class=abort reason=control_not_idle_shape stop=failure restore=ok restore_reason=- teardown=stage_a verdict=present det=4/4 service=failed service_reason=control_not_idle_shape deliveries=0 video=0/0 audio=0 frames=0 complete=0 incomplete=0 resync=0 baseline=never_established baseline_s=0.000 valid_s=0.000 capture_s=0.000 safety_s=0.000 target_s=120 limit_s=180 structured=not_observed episodes=0 stable=0 unstable=0 not_preserved=0 episode_store_full=0 tail_frames=0 tail_truncated=0 frame_store_full=0 event_store_full=0 events=0 boundaries_disc=0 boundaries_gbi=0 disagreements=0 reference_match=offline next_cause_at_end=0 handler=0 restored=-1 mask_ok=-1 isr_w1c=0 main_w1c=0 teardown_w1c=0 control_ok=1 pi_sticky_final=0 uncertain=0 overflow=0 arinfo_restore_ok=1 power_cycle_required=0 errors=0 transport_ok=1' \
	  -C Dolphin.Core.HSPDevice=2 \
	  --report $(VSTATE_OUT)/dolphin-report-present.json --screen-png $(VSTATE_OUT)/dolphin-screen-present.png

# ---------------------------------------------------------------------------
# SWISS LAUNCH LAYOUT
#
# Swiss lists directories, and the build tree is named for the source: in a
# truncated list `gbp-init-irq-program-probe` and `gbp-init-irq-deliver-probe`
# look the same, and picking the wrong one spends a physical run. This exports
# every launchable DOL as build/swiss/NN-short/boot.dol, numbered by the
# versioned manifest tools/swiss-layout.tsv.
#
# The copy is byte for byte and the hash is verified afterwards: no build id, no
# commit and no byte of the image changes. The AUTHORITY stays build/poc/...;
# build/swiss is presentation, is ignored by Git, and is safe to delete.
swiss:
	$(PYTHON) tools/swiss_export.py --root .

# The manifest alone, without needing anything built.
swiss-check:
	$(PYTHON) tools/swiss_export.py --check

# ---------------------------------------------------------------------------
# PRE-HANDLER MASKED-WAIT DIAGNOSTIC
#
# The SAME vstate probe, built with one extra define, into its OWN output
# directory and under its OWN build id. It answers one question and no other:
# does the Game Boy Player tolerate several seconds between stage A putting
# CONTROL in the running shape and the 003B handler being installed, with PI
# still masked, and then service normally? That interval is where a future
# operator ARM step for GBP-VIDEO-003 would have to sit.
#
# This is NOT GBP-VIDEO-003 and NOT vstate-0004: different build id, different
# artifacts, different directory. The ordinary `make build` is untouched and
# still produces vstate-0004 with the wait at zero.
PREWAIT_MS  ?= 5000
PREWAIT_OUT := build/poc/gbp-video-state-probe-prewait
PREWAIT_DOL := $(PREWAIT_OUT)/gbp-video-state-probe.dol

prehandler-wait:
	$(IN_CONTAINER) sh -c 'set -e; make --no-print-directory -C poc/gbp-video-state-probe \
	  BUILD_ID=vstate-prewait-$(PREWAIT_MS) \
	  OUTDIR="$$PWD/$(PREWAIT_OUT)" \
	  EXTRA_DEFINES=-DGBP_VSTATE_PREHANDLER_WAIT_MS=$(PREWAIT_MS)'
	@echo
	@echo "  DIAGNOSTIC BUILD - not GBP-VIDEO-003, not vstate-0004"
	@echo "  wait: $(PREWAIT_MS) ms between stage A and the handler install"
	@sha256sum $(PREWAIT_DOL) $(PREWAIT_OUT)/gbp-video-state-probe.unpadded.dol

# The controlled AGB stimulus of GBP-VIDEO-003 (devkitARM, inside the same container).
# The ROM is a DEVELOPMENT ARTIFACT: it has never run on hardware, and this repository
# documents no way to deliver it to the Game Boy Player's internal AGB (HARDWARE_TESTS §V3.7).
stimulus:
	$(IN_CONTAINER) sh -c 'set -e; export DEVKITARM=$$DEVKITPRO/devkitARM; make --no-print-directory -C stimulus/agb-color-bars'
	@$(PYTHON) tools/gbahdr.py show $(STIM_ROM)

# GBP-VIDEO-003 colour probe under Dolphin. AUXILIARY ONLY: Dolphin's GBPlayer model is
# not physical truth and CANNOT say anything about colour mapping (§54 of the
# implementation contract). Both runs abort in the 003A stage exactly as the vstate
# probe does, which is what is being checked here: startup, the state machine's refusal
# to certify anything, the stop path and the teardown.
color-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(COLOR_DOL) --build-info $(COLOR_OUT)/build-info.txt 	  --heartbeats 0 --expect 'OPENGBP-COLOR DONE status=abort_inconsistent class=abort reason=inconsistent stop=failure' 	  --report $(COLOR_OUT)/dolphin-report-absent.json --screen-png $(COLOR_OUT)/dolphin-screen-absent.png
	$(PYTHON) tools/dolphin_smoke.py --dol $(COLOR_DOL) --build-info $(COLOR_OUT)/build-info.txt 	  --heartbeats 0 --expect 'OPENGBP-COLOR DONE status=abort_control_shape class=abort reason=control_not_idle_shape stop=failure' 	  -C Dolphin.Core.HSPDevice=2 	  --report $(COLOR_OUT)/dolphin-report-present.json --screen-png $(COLOR_OUT)/dolphin-screen-present.png

color-audit:
	$(IN_CONTAINER) sh -c 'set -e; mkdir -p $(COLOR_OUT)/audit; rm -f $(COLOR_OUT)/audit/*.objdump.txt; for o in $(COLOR_OUT)/obj/*.o; do powerpc-eabi-objdump -dr "$$o" > "$(COLOR_OUT)/audit/$$(basename "$$o" .o).objdump.txt"; done; powerpc-eabi-nm $(COLOR_OUT)/gbp-video-color-probe.elf > $(COLOR_OUT)/audit/elf.nm.txt'
	$(PYTHON) tools/isr_audit.py $(COLOR_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr_ext --report $(COLOR_OUT)/isr-audit-ext.txt
	$(PYTHON) tools/isr_audit.py $(COLOR_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr --report $(COLOR_OUT)/isr-audit-base.txt
	$(PYTHON) tools/poc_audit.py $(COLOR_OUT)/audit --profile color --report $(COLOR_OUT)/poc-audit.txt
	@echo "-- the interrupt path must be identical to the physically validated GBP-VIDEO-001 build:"
	@cmp -s $(COLOR_OUT)/isr-audit-ext.txt $(VIDEO_OUT)/isr-audit-ext.txt && echo "   ext one-shot: identical" || { echo "   ext one-shot: DIFFERENT"; exit 1; }
	@cmp -s $(COLOR_OUT)/isr-audit-base.txt $(VIDEO_OUT)/isr-audit-base.txt && echo "   base one-shot: identical" || { echo "   base one-shot: DIFFERENT"; exit 1; }

# Static audit of gbp-video-state-probe (GBP-VIDEO-002): tools/isr_audit.py on both one-shot
# bodies of hsp_backend_irq.o — which must stay BYTE-IDENTICAL to the GBP-VIDEO-001 build's, since
# that path was physically validated — and tools/poc_audit.py --profile vstate on every object.
vstate-audit:
	@test -d $(VSTATE_OUT)/obj || { echo "missing $(VSTATE_OUT)/obj; run make build"; exit 1; }
	$(IN_CONTAINER) sh -c 'set -e; mkdir -p $(VSTATE_OUT)/audit; rm -f $(VSTATE_OUT)/audit/*.objdump.txt; for o in $(VSTATE_OUT)/obj/*.o; do powerpc-eabi-objdump -dr "$$o" > "$(VSTATE_OUT)/audit/$$(basename "$$o" .o).objdump.txt"; done; powerpc-eabi-nm $(VSTATE_OUT)/gbp-video-state-probe.elf > $(VSTATE_OUT)/audit/elf.nm.txt'
	$(PYTHON) tools/isr_audit.py $(VSTATE_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr_ext --report $(VSTATE_OUT)/isr-audit-ext.txt
	$(PYTHON) tools/isr_audit.py $(VSTATE_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr --report $(VSTATE_OUT)/isr-audit-base.txt
	$(PYTHON) tools/poc_audit.py $(VSTATE_OUT)/audit --profile vstate --report $(VSTATE_OUT)/poc-audit.txt
	@echo "-- the interrupt path must be identical to the physically validated GBP-VIDEO-001 build:"
	@diff $(VSTATE_OUT)/isr-audit-ext.txt $(VIDEO_OUT)/isr-audit-ext.txt && echo "   ext one-shot: identical"
	@diff $(VSTATE_OUT)/isr-audit-base.txt $(VIDEO_OUT)/isr-audit-base.txt && echo "   base one-shot: identical"

# Dolphin is AUXILIARY (§27): this smoke test answers whether the program boots,
# whether the new GX initialisation survives, and whether it reaches its own
# abort path. It says NOTHING about GBP timing, frame pacing or source loss, and
# no result from it may be cited as evidence about the device.
stream-dolphin:
	$(PYTHON) tools/dolphin_smoke.py --dol $(STREAM_DOL) --build-info $(STREAM_OUT)/build-info.txt \
	  --heartbeats 0 --expect 'OPENGBP-STREAM SELFTEST ok=1' \
	  --report $(STREAM_OUT)/dolphin-report-absent.json --screen-png $(STREAM_OUT)/dolphin-screen-absent.png

stream-audit:
	$(IN_CONTAINER) sh -c 'set -e; mkdir -p $(STREAM_OUT)/audit; rm -f $(STREAM_OUT)/audit/*.objdump.txt; for o in $(STREAM_OUT)/obj/*.o; do powerpc-eabi-objdump -dr "$$o" > "$(STREAM_OUT)/audit/$$(basename "$$o" .o).objdump.txt"; done; powerpc-eabi-nm $(STREAM_OUT)/gbp-video-stream-probe.elf > $(STREAM_OUT)/audit/elf.nm.txt'
	$(PYTHON) tools/isr_audit.py $(STREAM_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr_ext --report $(STREAM_OUT)/isr-audit-ext.txt
	$(PYTHON) tools/isr_audit.py $(STREAM_OUT)/audit/hsp_backend_irq.objdump.txt --symbol hsp_backend_oneshot_isr --report $(STREAM_OUT)/isr-audit-base.txt
	$(PYTHON) tools/poc_audit.py $(STREAM_OUT)/audit --profile stream --report $(STREAM_OUT)/poc-audit.txt
	@echo "-- the interrupt path must be identical to the physically validated GBP-VIDEO-001 build:"
	@cmp -s $(STREAM_OUT)/isr-audit-ext.txt $(VIDEO_OUT)/isr-audit-ext.txt && echo "   ext one-shot: identical" || { echo "   ext one-shot: DIFFERENT"; exit 1; }
	@cmp -s $(STREAM_OUT)/isr-audit-base.txt $(VIDEO_OUT)/isr-audit-base.txt && echo "   base one-shot: identical" || { echo "   base one-shot: DIFFERENT"; exit 1; }

all: test smoke-dolphin probe-dolphin init-dolphin initirq-dolphin initirqa-dolphin initirqb-dolphin initirq4-dolphin avsvc-dolphin video-dolphin vstate-dolphin color-dolphin

shell:
	$(COMPOSE) run --rm dev bash

clean:
	rm -rf build/poc build/tests
