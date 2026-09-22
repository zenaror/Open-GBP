#---------------------------------------------------------------------------------
# Open-GBP GBP-AUDIO-001 — the audio window image (GitHub Issue #59)
#
#     make -C poc/gbp-audio-window-probe        (inside the project container)
#
# Outputs go to build/poc/gbp-audio-window-probe/ (ignored by Git).
#
# WHAT THIS BUILDS. stream-0015's runtime — the transport and the 003B one-shot
# handler, the service path (src/gbp/gbp_vstate_probe), the presentation path
# with Policy A, the input path and the KEY record (byte-identical: tests/host/
# test_play_image.py diffs the two functions) — WITHOUT the research
# instrumentation (the OGBPIDX1 witness is never bound and has no store; the
# full-frame sampler, the VI latch trace, the disposition trace and their four
# sidecars are not linked), PLUS the one thing Issue #38 found missing: a
# SUCCESS stop the operator controls (Z held: gbp_session -> the state
# machine's `session_end` flag -> stop=session_end, a normal end).
#
# THE AUDIT PROFILE IS `awin` (tools/poc_audit.py), and it DISCRIMINATES both
# ways: it requires main.o to reference the window and its sidecar, which the
# play image does not, and it forbids the video research instrumentation, which
# the stream image carries. The ext / base one-shot handlers are compared byte
# for byte with the physically validated GBP-VIDEO-001 build's, as every
# video-family probe's are.
#
# Run it with: make -C . awin-audit   (repository root)
#---------------------------------------------------------------------------------
.SUFFIXES:

ifeq ($(strip $(DEVKITPPC)),)
$(error "Please set DEVKITPPC in your environment. export DEVKITPPC=<path to>devkitPPC")
endif

include $(DEVKITPRO)/libogc2/gamecube_rules

#---------------------------------------------------------------------------------
# Identity
#---------------------------------------------------------------------------------
APP_NAME   := gbp-audio-window-probe
# Issue #59. stream-0016 is the AUDIO WINDOW image: play-0001's runtime -- and
# so stream-0015's service, presentation and input paths -- plus the retention
# and emission HARDWARE_TESTS §V8 needs. input_step() is byte-identical to
# play-0001's; keylog_emit() and pump() differ by ONE line each, and
# tests/host/test_awin_image.py names them. The service path gains ONE optional
# config field (cfg.awin) and ONE call after the AUDIO drain and its commit: no
# device operation is added, removed or reordered.
#
# THE ID KEEPS THE `stream-` FAMILY because §V8.7 named stream-0016 and §V8.9
# reserved the run's raw-file names with it. NOT PHYSICALLY EXECUTED; the run
# is pre-registered (§V8, GBP-AUDIO-001) and NOT authorised; not staged.
BUILD_ID   := stream-0016

# NORMAL by default, as stream-0009 onwards: no visible synthetic frame and no
# pre-handler masked wait. The diagnostic image exists for reproducing a
# historical experiment only:
#   make build STARTUP_MODE=GBP_STARTUP_DIAGNOSTIC
STARTUP_MODE ?= GBP_STARTUP_NORMAL
GIT_COMMIT ?= $(shell git -C "$(CURDIR)" rev-parse --short=7 HEAD 2>/dev/null || echo unknown)
GIT_DIRTY  ?= $(shell git -C "$(CURDIR)" diff --quiet HEAD -- 2>/dev/null || echo -dirty)
COMMIT_ID  := $(GIT_COMMIT)$(GIT_DIRTY)

#---------------------------------------------------------------------------------
# Layout
#---------------------------------------------------------------------------------
ROOT    := $(abspath $(CURDIR)/../..)
OUTDIR  := $(ROOT)/build/poc/$(APP_NAME)
OBJDIR  := $(OUTDIR)/obj
TARGET  := $(OUTDIR)/$(APP_NAME)

vpath %.c $(CURDIR)/source $(ROOT)/src/common $(ROOT)/src/log $(ROOT)/src/gbp $(ROOT)/src/platform

# play-0001's list PLUS gbp_awin.c and gbp_awindump.c, and nothing else. The
# video research instrumentation stays out (no gbp_vidxdump.c, gbp_vdisp.c,
# gbp_vdispdump.c, gbp_vfull.c, gbp_vfulldump.c, gbp_vvi.c, gbp_vvidump.c);
# gbp_vwitness.c stays because the service-path module references its
# predicates (under `if (cfg->witness)`, never taken here) and no store exists
# for it.
SRCS := main.c opengbp_ident.c ringlog.c gbp_transport.c gbp_detect.c gbp_rawlog.c gbp_regwrite.c gbp_initirqa_probe.c gbp_irq_service.c gbp_crc32.c gbp_avblock.c gbp_time64.c gbp_vsig.c gbp_vstate.c gbp_vpix.c gbp_vqueue.c gbp_vpresent.c gbp_vwitness.c gbp_vcolor.c gbp_vstate_probe.c gbp_vstatedump.c gbp_input.c gbp_session.c gbp_awin.c gbp_awindump.c hsp_backend.c hsp_backend_irq.c sdlog.c
OBJS := $(addprefix $(OBJDIR)/,$(SRCS:.c=.o))
DEPS := $(OBJS:.o=.d)

#---------------------------------------------------------------------------------
# Flags
#---------------------------------------------------------------------------------
INCLUDE  := -I$(ROOT)/src/common -I$(ROOT)/src/log -I$(ROOT)/src/gbp -I$(ROOT)/src/platform -I$(LIBOGC_INC)
DEFINES  := -DOPENGBP_APP_NAME=\"$(APP_NAME)\" \
            -DOPENGBP_BUILD_ID=\"$(BUILD_ID)\" \
            -DOPENGBP_GIT_COMMIT=\"$(COMMIT_ID)\" \
            -DGBP_STARTUP_MODE=$(STARTUP_MODE)

CFLAGS   := -std=gnu11 -g -O2 -Wall -Wextra -Wshadow $(MACHDEP) $(INCLUDE) $(DEFINES)
LDFLAGS  := -g $(MACHDEP) -Wl,-Map,$(TARGET).map
LIBPATHS := -L$(LIBOGC_LIB)
LIBS     := -lfat -logc
LD       := $(CC)

export DEPSDIR := $(OBJDIR)

#---------------------------------------------------------------------------------
# Targets
#---------------------------------------------------------------------------------
.PHONY: all clean info

all: $(TARGET).dol $(OUTDIR)/build-info.txt info

# %.elf: (link) comes from gamecube_rules. The .dol rule is explicit because
# we post-process elf2dol's output (see header comment).
$(TARGET).elf: $(OBJS)

$(TARGET).unpadded.dol: $(TARGET).elf
	$(SILENTMSG) output ... $(notdir $@)
	$(SILENTCMD)elf2dol $< $@

$(TARGET).dol: $(TARGET).unpadded.dol $(ROOT)/tools/dolpad.py $(ROOT)/tools/dolinfo.py
	$(SILENTMSG) dolpad ... $(notdir $@)
	$(SILENTCMD)python3 $(ROOT)/tools/dolpad.py $< $@

$(OBJDIR)/%.o: %.c | $(OBJDIR)
	$(SILENTMSG) $(notdir $<)
	$(SILENTCMD)$(CC) -MMD -MP -MF $(DEPSDIR)/$*.d $(CFLAGS) -c $< -o $@

$(OBJDIR):
	@mkdir -p $@

# Machine-readable identity used by host tests and the Dolphin runner.
$(OUTDIR)/build-info.txt: $(TARGET).dol
	@{ \
	  echo "app=$(APP_NAME)"; \
	  echo "build_id=$(BUILD_ID)"; \
	  echo "commit=$(COMMIT_ID)"; \
	  echo "elf=$(TARGET).elf"; \
	  echo "dol=$(TARGET).dol"; \
	  echo "dol_unpadded=$(TARGET).unpadded.dol"; \
	  echo "dol_padded_to_32=yes"; \
	  echo "cc=$$($(CC) --version | head -n1)"; \
	  echo "libogc2=$$(sed -n 's/^#define _V_STRING "\(.*\)"/\1/p' $(LIBOGC_INC)/ogc/libversion.h)"; \
	  echo "sha256_dol=$$(sha256sum $(TARGET).dol | cut -d' ' -f1)"; \
	} > $@

info: $(OUTDIR)/build-info.txt
	@echo "---- build-info ----"
	@cat $<

clean:
	@echo clean ...
	@rm -rf $(OUTDIR)

-include $(DEPS)
