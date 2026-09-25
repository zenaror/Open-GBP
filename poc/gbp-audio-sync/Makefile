#---------------------------------------------------------------------------------
# Open-GBP GBP-AUDIO-012 — the latency round, sync-0001 (GitHub Issue #117, HARDWARE_TESTS §V27)
#
#     make -C poc/gbp-audio-sync       (inside the project container)
#
# Outputs go to build/poc/gbp-audio-sync/ (ignored by Git).
#
# WHAT THIS IS (§V27, ONE VARIABLE: the chain's TARGET). poc/gbp-audio-game2 (game-0002, RUN 42's image)
# with the L2 keep removed and the session added: src/audio/gbp_async (the three phases, the seeded
# schedule, the transition plans, the per-second series), src/gbp/gbp_awr (the raw AUDIO blocks of the
# session's first 640, ridden along and written after the session), the transition executor (the mute,
# the held queue, produce-and-discard), the C-stick as the Operator's only control and Z as "next phase".
# Nothing on the screen or the live channel is derived from the arm, the target, the fill, the
# corrections or the answers (§V27.9 O6, §V27.10): every figure goes to the SD log. The rest of this
# file is game-0002's Makefile but for the identity and the two sources added.
#
# THE AUDIT PROFILE IS `sync` (tools/poc_audit.py): the `game` profile with its deltas named.
#
# Run it with: make -C . sync-audit   (repository root)
#---------------------------------------------------------------------------------
.SUFFIXES:

ifeq ($(strip $(DEVKITPPC)),)
$(error "Please set DEVKITPPC in your environment. export DEVKITPPC=<path to>devkitPPC")
endif

include $(DEVKITPRO)/libogc2/gamecube_rules

#---------------------------------------------------------------------------------
# Identity
#---------------------------------------------------------------------------------
APP_NAME   := gbp-audio-sync
# Issue #92. live-0001 is the first build of Phase 6's acceptance image (§V22 with
# §V22.8's readings and §V22.9 AMENDMENT 1). NOT PHYSICALLY EXECUTED; the run is
# staged by a separate Hardware Issue and is not authorised here.
BUILD_ID   := sync-0001
# Issue #117. sync-0001 is the latency round (§V27): game-0002's chain with the L2 keep never
# armed, the ring's cushion switchable at run time under a fixed mute, a blinded seeded schedule
# of switches, a nulling phase and a mechanistic descent, and a 640-block raw window riding along.
# NOT PHYSICALLY EXECUTED; staging and the run are the Orchestrator's.

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

vpath %.c $(CURDIR)/source $(ROOT)/src/common $(ROOT)/src/log $(ROOT)/src/gbp $(ROOT)/src/audio $(ROOT)/src/platform

# play-0001's list, as drain-0001 carried it, with gbp_adrain.c OUT and the chain IN:
# gbp_alive.c and gbp_aplay.c (Issue #92), and the #81 modules gbp_adec.c and
# gbp_aresamp.c, UNCHANGED. gbp_aperiod.c stays: it is the positive control's period
# decoder (§V19.11 A4.7). gbp_awin.c is linked for the reason drain-0001 gave: the
# service-path module references the window's two functions under `if (cfg->awin)`,
# never taken here. gbp_awindump.c, gbp_asrc.c and gbp_adrain.c are NOT linked.
SRCS := main.c opengbp_ident.c ringlog.c gbp_transport.c gbp_detect.c gbp_rawlog.c gbp_regwrite.c gbp_initirqa_probe.c gbp_irq_service.c gbp_crc32.c gbp_avblock.c gbp_time64.c gbp_vsig.c gbp_vstate.c gbp_vpix.c gbp_vqueue.c gbp_vpresent.c gbp_vwitness.c gbp_vcolor.c gbp_vstate_probe.c gbp_vstatedump.c gbp_input.c gbp_session.c gbp_awin.c gbp_aperiod.c gbp_adec.c gbp_aresamp.c gbp_alive.c gbp_aplay.c gbp_async.c gbp_atrans.c gbp_awr.c hsp_backend.c hsp_backend_irq.c sdlog.c
OBJS := $(addprefix $(OBJDIR)/,$(SRCS:.c=.o))
DEPS := $(OBJS:.o=.d)

#---------------------------------------------------------------------------------
# Flags
#---------------------------------------------------------------------------------
INCLUDE  := -I$(ROOT)/src/common -I$(ROOT)/src/log -I$(ROOT)/src/gbp -I$(ROOT)/src/audio -I$(ROOT)/src/platform -I$(LIBOGC_INC)
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
