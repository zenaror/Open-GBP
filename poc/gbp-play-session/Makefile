#---------------------------------------------------------------------------------
# Open-GBP GBP-PLAY-001 — the playable runtime image (GitHub Issue #39)
#
#     make -C poc/gbp-play-session        (inside the project container)
#
# Outputs go to build/poc/gbp-play-session/ (ignored by Git).
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
# THE AUDIT PROFILE IS `play` (tools/poc_audit.py): the `stream` profile pins
# the four sidecar streams and the witness call sites from main, so a smaller
# image fails it by construction, and the `play` profile fails the stream
# image the same way (the instrumentation objects are FORBIDDEN there). The
# ext / base one-shot handlers are compared byte for byte with the physically
# validated GBP-VIDEO-001 build's, as every video-family probe's are.
#
# Run it with: make -C . play-audit   (repository root)
#---------------------------------------------------------------------------------
.SUFFIXES:

ifeq ($(strip $(DEVKITPPC)),)
$(error "Please set DEVKITPPC in your environment. export DEVKITPPC=<path to>devkitPPC")
endif

include $(DEVKITPRO)/libogc2/gamecube_rules

#---------------------------------------------------------------------------------
# Identity
#---------------------------------------------------------------------------------
APP_NAME   := gbp-play-session
# Issue #39. play-0001 is the first build of the playable image: stream-0015's
# runtime minus its research instrumentation, plus the operator's session end
# (Z held for PLAY_SESSION_END_HOLD_MS -> stop=session_end, a SUCCESS) and the
# stores sized for a PLAY_SAFETY_SECONDS session (frame records, event records,
# the delivery guard, the ringlog and its post-run reserve). The descriptor,
# the policy, the input path and the KEY record are stream-0015's, byte for
# byte; the service path's device operations, their order and Policy A are
# unchanged; the service pass is SHORTER by the witness step it no longer
# runs (stated, not assumed benign: docs/research/INPUT_PATH.md §13). NOT
# PHYSICALLY EXECUTED; no run is pre-registered for it; not staged.
BUILD_ID   := play-0001

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

# stream-0015's list WITHOUT gbp_vidxdump.c gbp_vdisp.c gbp_vdispdump.c
# gbp_vfull.c gbp_vfulldump.c gbp_vvi.c gbp_vvidump.c, PLUS gbp_session.c.
# gbp_vwitness.c stays: the service-path module references its predicates
# (under `if (cfg->witness)`, never taken here); no store exists for it.
SRCS := main.c opengbp_ident.c ringlog.c gbp_transport.c gbp_detect.c gbp_rawlog.c gbp_regwrite.c gbp_initirqa_probe.c gbp_irq_service.c gbp_crc32.c gbp_avblock.c gbp_time64.c gbp_vsig.c gbp_vstate.c gbp_vpix.c gbp_vqueue.c gbp_vpresent.c gbp_vwitness.c gbp_vcolor.c gbp_vstate_probe.c gbp_vstatedump.c gbp_input.c gbp_session.c hsp_backend.c hsp_backend_irq.c sdlog.c
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
