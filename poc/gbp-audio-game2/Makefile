#---------------------------------------------------------------------------------
# Open-GBP GBP-AUDIO-011 — Phase 6's acceptance, second attempt, game-0002 (GitHub Issue #113, HARDWARE_TESTS §V26)
#
#     make -C poc/gbp-audio-game2       (inside the project container)
#
# Outputs go to build/poc/gbp-audio-game2/ (ignored by Git).
#
# WHAT THIS IS (§V26.2, ONE VARIABLE). poc/gbp-audio-game (game-0001, RUN 41's image) with ONE record added
# after the session: each before-AI incomplete frame's store index and block times (LIVEVBEF). The rest of
# this file is game-0001's Makefile but for the identity.
#
# WHAT THIS IS (§V25.7 5, (r8)). poc/gbp-audio-live (live-0001, RUN 38's image) with the three
# things that stood on the stimulus ROM's tone replaced -- the press origin instead of the
# positive control, the game on screen from the press until the window closes, a prompt that
# invites presses -- the decoder's clip counter and calibration spread logged, and the video's
# location read from the frame store after the session. No §V23 recorder, no §V24 split: the
# chain produces in gbp_aplay's adopted 8-push calls (Issue #109). The rest of this file is
# live-0001's Makefile but for the identity.
#
# WHAT THIS BUILDS (HARDWARE_TESTS §V22). play-0001 as RUN 37's image took it --
# the transport and the 003B one-shot handler, the service path draining AUDIO AND
# VIDEO in whole 0x1000 blocks, the presentation path, the input path and the Z
# session end, behaviour unchanged -- PLUS the composition §V22 accepts: the
# accounting (src/audio/gbp_alive), the chain (src/audio/gbp_aplay), and, UNCHANGED,
# the decoder (gbp_adec), the resampler (gbp_aresamp) and the positive control's
# period decoder (gbp_aperiod). ONE service hook (cfg.audio_tap), the AI DMA
# callback, and a VI that stays on the text console. No SD write during the run.
#
# THE AUDIT PROFILE IS `live` (tools/poc_audit.py): the `play` profile with its
# deltas named.
#
# Run it with: make -C . live-audit   (repository root)
#---------------------------------------------------------------------------------
.SUFFIXES:

ifeq ($(strip $(DEVKITPPC)),)
$(error "Please set DEVKITPPC in your environment. export DEVKITPPC=<path to>devkitPPC")
endif

include $(DEVKITPRO)/libogc2/gamecube_rules

#---------------------------------------------------------------------------------
# Identity
#---------------------------------------------------------------------------------
APP_NAME   := gbp-audio-game2
# Issue #92. live-0001 is the first build of Phase 6's acceptance image (§V22 with
# §V22.8's readings and §V22.9 AMENDMENT 1). NOT PHYSICALLY EXECUTED; the run is
# staged by a separate Hardware Issue and is not authorised here.
BUILD_ID   := game-0002
# Issue #113. game-0002 is Phase 6's second attempt: game-0001 plus §V26.2's read-only record.
# NOT PHYSICALLY EXECUTED; staging and the run are the Orchestrator's.
# Issue #110. game-0001 is the first build of Phase 6's acceptance on a real cartridge.
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
SRCS := main.c opengbp_ident.c ringlog.c gbp_transport.c gbp_detect.c gbp_rawlog.c gbp_regwrite.c gbp_initirqa_probe.c gbp_irq_service.c gbp_crc32.c gbp_avblock.c gbp_time64.c gbp_vsig.c gbp_vstate.c gbp_vpix.c gbp_vqueue.c gbp_vpresent.c gbp_vwitness.c gbp_vcolor.c gbp_vstate_probe.c gbp_vstatedump.c gbp_input.c gbp_session.c gbp_awin.c gbp_aperiod.c gbp_adec.c gbp_aresamp.c gbp_alive.c gbp_aplay.c hsp_backend.c hsp_backend_irq.c sdlog.c
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
