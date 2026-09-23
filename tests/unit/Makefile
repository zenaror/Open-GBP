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
CPPFLAGS += -I$(ROOT)/src/common -I$(ROOT)/src/log -I$(ROOT)/src/gbp -I$(ROOT)/src/audio -I$(ROOT)/tests/mocks

# HEADERS ARE PREREQUISITES. Without this a header edit leaves a stale binary and
# the suite silently reports the PREVIOUS build's result — which is exactly how an
# adversarial mutation of gbp_vpix.h was credited to the mutation that came after
# it (HARDWARE_TESTS §V5.27.9). Every test relinks whenever any shared header
# changes; these binaries build in about a second each, so the cost is nothing
# next to a wrong answer.
HEADERS := $(wildcard $(ROOT)/src/common/*.h $(ROOT)/src/log/*.h $(ROOT)/src/gbp/*.h $(ROOT)/src/audio/*.h $(ROOT)/tests/mocks/*.h)

TESTS    := test_ident test_ringlog test_gbp_vfull test_gbp_vvi test_gbp_detect test_gbp_probe test_gbp_replay test_gbp_init test_gbp_init_irq test_gbp_initirqa test_gbp_initirqb test_gbp_initirq4 test_gbp_avdump test_gbp_avsvc test_gbp_avseq test_gbp_video test_gbp_vsig test_gbp_vstate test_gbp_video_state test_gbp_vcolor test_gbp_vstream test_gbp_vwitness test_gbp_vdisp test_gbp_startup test_gbp_input test_gbp_session test_gbp_awin test_gbp_awindump test_gbp_adec
BINS     := $(addprefix $(OUTDIR)/,$(TESTS))

COMMON_SRC := $(ROOT)/src/common/opengbp_ident.c $(ROOT)/src/common/gbp_time64.c
LOG_SRC    := $(ROOT)/src/log/ringlog.c
GBP_SRC    := $(ROOT)/src/gbp/gbp_transport.c $(ROOT)/src/gbp/gbp_probe.c $(ROOT)/src/gbp/gbp_replay.c $(ROOT)/src/gbp/gbp_detect.c $(ROOT)/src/gbp/gbp_init_probe.c $(ROOT)/src/gbp/gbp_rawlog.c $(ROOT)/src/gbp/gbp_init_irq_probe.c $(ROOT)/src/gbp/gbp_regwrite.c $(ROOT)/src/gbp/gbp_initirqa_probe.c $(ROOT)/src/gbp/gbp_irq_service.c $(ROOT)/src/gbp/gbp_initirqb_probe.c $(ROOT)/src/gbp/gbp_initirq4_probe.c $(ROOT)/src/gbp/gbp_crc32.c $(ROOT)/src/gbp/gbp_avblock.c $(ROOT)/src/gbp/gbp_avdump.c $(ROOT)/src/gbp/gbp_avsvc_probe.c $(ROOT)/src/gbp/gbp_avseq.c $(ROOT)/src/gbp/gbp_avseqdump.c $(ROOT)/src/gbp/gbp_video_probe.c $(ROOT)/src/common/gbp_time64.c $(ROOT)/src/gbp/gbp_vsig.c $(ROOT)/src/gbp/gbp_vstate.c $(ROOT)/src/gbp/gbp_vcolor.c $(ROOT)/src/gbp/gbp_vpix.c $(ROOT)/src/gbp/gbp_vqueue.c $(ROOT)/src/gbp/gbp_vpresent.c $(ROOT)/src/gbp/gbp_vwitness.c $(ROOT)/src/gbp/gbp_vdisp.c $(ROOT)/src/gbp/gbp_vdispdump.c $(ROOT)/src/gbp/gbp_vstate_probe.c $(ROOT)/src/gbp/gbp_vstatedump.c $(ROOT)/src/gbp/gbp_vcoldump.c $(ROOT)/src/gbp/gbp_awin.c
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
HW_INITIRQA_GBP  := $(ROOT)/captures/fixtures/hw-gamecube-gbp-2026-09-15-initirqa-0001.gbpreplay
HW_INITIRQB_GBP  := $(ROOT)/captures/fixtures/hw-gamecube-gbp-2026-09-15-initirqb-0001.gbpreplay
HW_INITIRQ4_GBP  := $(ROOT)/captures/fixtures/hw-gamecube-gbp-2026-09-16-initirq4-0001.gbpreplay
HW_AVSVC_GBP     := $(ROOT)/captures/fixtures/hw-gamecube-gbp-2026-09-16-avsvc-0001.gbpreplay
HW_AVSVC_BLOCKS  := $(ROOT)/captures/fixtures/hw-gamecube-gbp-2026-09-16-avsvc-0001-blocks.bin
HW_VIDEO_GBP     := $(ROOT)/captures/fixtures/hw-gamecube-gbp-2026-09-16-video-0001.gbpreplay
HW_VIDEO_SEQ     := $(ROOT)/captures/fixtures/hw-gamecube-gbp-2026-09-16-video-0001-seq.bin

run: $(BINS)
	@set -e; for t in $(BINS); do echo "== $$t"; if [ "$$t" = "$(OUTDIR)/test_gbp_replay" ]; then "$$t" "$(HW_FIXTURE_GBP)" "$(HW_FIXTURE_NOGBP)" "$(MODEL_FIXTURE_P)" "$(MODEL_FIXTURE_A)"; elif [ "$$t" = "$(OUTDIR)/test_gbp_init" ]; then "$$t" "$(HW_INIT_GBP)" "$(HW_INIT_NOGBP)"; elif [ "$$t" = "$(OUTDIR)/test_gbp_init_irq" ]; then "$$t" "$(HW_INIT_GBP)" "$(HW_INIT_NOGBP)" "$(HW_INITIRQ_GBP)"; elif [ "$$t" = "$(OUTDIR)/test_gbp_initirqa" ]; then "$$t" "$(HW_INIT_GBP)" "$(HW_INIT_NOGBP)" "$(HW_INITIRQ_GBP)" "$(HW_INITIRQA_GBP)"; elif [ "$$t" = "$(OUTDIR)/test_gbp_initirqb" ]; then "$$t" "$(HW_INITIRQA_GBP)" "$(HW_INITIRQB_GBP)"; elif [ "$$t" = "$(OUTDIR)/test_gbp_initirq4" ]; then "$$t" "$(HW_INITIRQA_GBP)" "$(HW_INITIRQB_GBP)" "$(HW_INITIRQ4_GBP)"; elif [ "$$t" = "$(OUTDIR)/test_gbp_avsvc" ]; then "$$t" "$(HW_INITIRQA_GBP)" "$(HW_INITIRQB_GBP)" "$(HW_INITIRQ4_GBP)" "$(HW_AVSVC_GBP)" "$(HW_AVSVC_BLOCKS)"; elif [ "$$t" = "$(OUTDIR)/test_gbp_video" ]; then "$$t" "$(HW_AVSVC_GBP)" "$(HW_AVSVC_BLOCKS)" "$(HW_VIDEO_GBP)" "$(HW_VIDEO_SEQ)"; elif [ "$$t" = "$(OUTDIR)/test_gbp_video_state" ]; then "$$t" --long; else "$$t"; fi; done

$(OUTDIR)/test_ident: test_ident.c $(ROOT)/src/common/opengbp_ident.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_ident.c $(ROOT)/src/common/opengbp_ident.c

$(OUTDIR)/test_ringlog: test_ringlog.c $(LOG_SRC) $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_ringlog.c $(LOG_SRC)

$(OUTDIR)/test_gbp_detect: test_gbp_detect.c $(LOG_SRC) $(GBP_SRC) $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_detect.c $(LOG_SRC) $(GBP_SRC)

$(OUTDIR)/test_gbp_probe: test_gbp_probe.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_probe.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_replay: test_gbp_replay.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_replay.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_init: test_gbp_init.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_init.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_init_irq: test_gbp_init_irq.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(ROOT)/src/gbp/gbp_irq_oneshot.h $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_init_irq.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_initirqa: test_gbp_initirqa.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(ROOT)/src/gbp/gbp_irq_oneshot.h $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_initirqa.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_initirqb: test_gbp_initirqb.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(ROOT)/src/gbp/gbp_irq_oneshot.h $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_initirqb.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_initirq4: test_gbp_initirq4.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(ROOT)/src/gbp/gbp_irq_oneshot.h $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_initirq4.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_avdump: test_gbp_avdump.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_avdump.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_avsvc: test_gbp_avsvc.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(ROOT)/src/gbp/gbp_irq_oneshot.h $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_avsvc.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_avseq: test_gbp_avseq.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_avseq.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_video: test_gbp_video.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(ROOT)/src/gbp/gbp_irq_oneshot.h $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_video.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_vsig: test_gbp_vsig.c $(ROOT)/src/gbp/gbp_vsig.c $(ROOT)/src/common/gbp_time64.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_vsig.c $(ROOT)/src/gbp/gbp_vsig.c $(ROOT)/src/common/gbp_time64.c

$(OUTDIR)/test_gbp_vstate: test_gbp_vstate.c $(ROOT)/src/gbp/gbp_vstate.c $(ROOT)/src/gbp/gbp_vsig.c $(ROOT)/src/common/gbp_time64.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_vstate.c $(ROOT)/src/gbp/gbp_vstate.c $(ROOT)/src/gbp/gbp_vsig.c $(ROOT)/src/common/gbp_time64.c

# The long scan (~800 000 synthetic deliveries) runs here too: it takes about three seconds and it
# is the only test that proves the counters, the stores and the 64-bit clock at full scale.
$(OUTDIR)/test_gbp_vcolor: test_gbp_vcolor.c $(ROOT)/src/gbp/gbp_vcolor.c $(ROOT)/src/gbp/gbp_vcoldump.c $(ROOT)/src/gbp/gbp_vstate.c $(ROOT)/src/gbp/gbp_vstatedump.c $(ROOT)/src/gbp/gbp_vsig.c $(ROOT)/src/gbp/gbp_crc32.c $(ROOT)/src/gbp/gbp_rawlog.c $(ROOT)/src/gbp/gbp_detect.c $(ROOT)/src/gbp/gbp_transport.c $(ROOT)/src/log/ringlog.c $(ROOT)/src/common/gbp_time64.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_vcolor.c $(ROOT)/src/gbp/gbp_vcolor.c $(ROOT)/src/gbp/gbp_vcoldump.c $(ROOT)/src/gbp/gbp_vstate.c $(ROOT)/src/gbp/gbp_vstatedump.c $(ROOT)/src/gbp/gbp_vsig.c $(ROOT)/src/gbp/gbp_crc32.c $(ROOT)/src/gbp/gbp_rawlog.c $(ROOT)/src/gbp/gbp_detect.c $(ROOT)/src/gbp/gbp_transport.c $(ROOT)/src/log/ringlog.c $(ROOT)/src/common/gbp_time64.c

$(OUTDIR)/test_gbp_vstream: test_gbp_vstream.c $(ROOT)/src/gbp/gbp_vpix.c $(ROOT)/src/gbp/gbp_vqueue.c $(ROOT)/src/gbp/gbp_vpresent.c $(ROOT)/src/gbp/gbp_vstate.c $(ROOT)/src/gbp/gbp_vsig.c $(ROOT)/src/gbp/gbp_rawlog.c $(ROOT)/src/gbp/gbp_detect.c $(ROOT)/src/gbp/gbp_transport.c $(ROOT)/src/log/ringlog.c $(ROOT)/src/common/gbp_time64.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_vstream.c $(ROOT)/src/gbp/gbp_vpix.c $(ROOT)/src/gbp/gbp_vqueue.c $(ROOT)/src/gbp/gbp_vpresent.c $(ROOT)/src/gbp/gbp_vstate.c $(ROOT)/src/gbp/gbp_vsig.c $(ROOT)/src/gbp/gbp_rawlog.c $(ROOT)/src/gbp/gbp_detect.c $(ROOT)/src/gbp/gbp_transport.c $(ROOT)/src/log/ringlog.c $(ROOT)/src/common/gbp_time64.c

$(OUTDIR)/test_gbp_vwitness: test_gbp_vwitness.c $(ROOT)/src/gbp/gbp_vwitness.c $(ROOT)/src/gbp/gbp_vidxdump.c $(ROOT)/src/gbp/gbp_vstate.c $(ROOT)/src/gbp/gbp_vsig.c $(ROOT)/src/gbp/gbp_crc32.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_vwitness.c $(ROOT)/src/gbp/gbp_vwitness.c $(ROOT)/src/gbp/gbp_vidxdump.c $(ROOT)/src/gbp/gbp_vstate.c $(ROOT)/src/gbp/gbp_vsig.c $(ROOT)/src/gbp/gbp_crc32.c

$(OUTDIR)/test_gbp_vfull: test_gbp_vfull.c $(ROOT)/src/gbp/gbp_vfull.c $(ROOT)/src/gbp/gbp_vfulldump.c $(ROOT)/src/gbp/gbp_crc32.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_vfull.c $(ROOT)/src/gbp/gbp_vfull.c $(ROOT)/src/gbp/gbp_vfulldump.c $(ROOT)/src/gbp/gbp_crc32.c

$(OUTDIR)/test_gbp_vvi: test_gbp_vvi.c $(ROOT)/src/gbp/gbp_vvi.c $(ROOT)/src/gbp/gbp_vvidump.c $(ROOT)/src/gbp/gbp_crc32.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_vvi.c $(ROOT)/src/gbp/gbp_vvi.c $(ROOT)/src/gbp/gbp_vvidump.c $(ROOT)/src/gbp/gbp_crc32.c

$(OUTDIR)/test_gbp_video_state: test_gbp_video_state.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(ROOT)/src/gbp/gbp_irq_oneshot.h $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_video_state.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

$(OUTDIR)/test_gbp_startup: test_gbp_startup.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_startup.c

# Issue #19: the input path -- the mapping, the descriptor applied bit for bit under
# synthetic descriptors, the write through the mock and the replay, the refresh policy.
$(OUTDIR)/test_gbp_input: test_gbp_input.c $(ROOT)/src/gbp/gbp_input.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC) $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_input.c $(ROOT)/src/gbp/gbp_input.c $(LOG_SRC) $(GBP_SRC) $(MOCK_SRC)

# Issue #39: the operator's session end, a pure state machine with no outward edge.
$(OUTDIR)/test_gbp_session: test_gbp_session.c $(ROOT)/src/gbp/gbp_session.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_session.c $(ROOT)/src/gbp/gbp_session.c

# Issue #59: the AUDIO window and its sidecar. gbp_awin links alone -- it
# depends on stdint and string.h and nothing else, which is what lets the
# window be exercised on the host at all.
$(OUTDIR)/test_gbp_awin: test_gbp_awin.c $(ROOT)/src/gbp/gbp_awin.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_awin.c $(ROOT)/src/gbp/gbp_awin.c

$(OUTDIR)/test_gbp_awindump: test_gbp_awindump.c $(ROOT)/src/gbp/gbp_awindump.c $(ROOT)/src/gbp/gbp_awin.c $(ROOT)/src/gbp/gbp_crc32.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_awindump.c $(ROOT)/src/gbp/gbp_awindump.c $(ROOT)/src/gbp/gbp_awin.c $(ROOT)/src/gbp/gbp_crc32.c

# Issue #81: the AUDIO decoder and the 125/16 resampler. Integer only; they link
# alone, with no libogc and no device, and are checked on synthetic blocks here.
$(OUTDIR)/test_gbp_adec: test_gbp_adec.c $(ROOT)/src/audio/gbp_adec.c $(ROOT)/src/audio/gbp_aresamp.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_adec.c $(ROOT)/src/audio/gbp_adec.c $(ROOT)/src/audio/gbp_aresamp.c

$(OUTDIR)/test_gbp_vdisp: test_gbp_vdisp.c $(ROOT)/src/gbp/gbp_vdisp.c $(ROOT)/src/gbp/gbp_vdispdump.c $(ROOT)/src/gbp/gbp_crc32.c $(HEADERS) | $(OUTDIR)
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ test_gbp_vdisp.c $(ROOT)/src/gbp/gbp_vdisp.c $(ROOT)/src/gbp/gbp_vdispdump.c $(ROOT)/src/gbp/gbp_crc32.c

$(OUTDIR):
	mkdir -p $@

clean:
	rm -rf $(OUTDIR)
