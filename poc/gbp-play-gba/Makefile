#---------------------------------------------------------------------------------
# Open-GBP -- the GBA PLAY image (GitHub Issue #153, the build half; the design is docs/research/HARDWARE_TESTS.md V31)
#
#     make -C poc/gbp-play-gba
#
# Output goes to build/poc/gbp-play-gba/ (ignored by Git).
#
# WHAT THIS IS. poc/gbp-audio-v28's chassis, COPIED (that POC is an executed image whose sources are frozen), with the research handlers, the
# transition machine, the marked DMA block and the GX label left out, one plan (navigate -> play, src/audio/gbp_v28_plans.h GBP_V28_PLAY_GBA) and the
# native audio chain configured once at T256 A1. Everything in src/ it links is the shared code every image links.
#---------------------------------------------------------------------------------
.SUFFIXES:

ifeq ($(strip $(DEVKITPPC)),)
$(error "Please set DEVKITPPC in your environment. export DEVKITPPC=<path to>devkitPPC")
endif

include $(DEVKITPRO)/libogc2/gamecube_rules

#---------------------------------------------------------------------------------
# Identity (AGENTS.md section 15): the screen and the log carry the same app, build id and commit.
#---------------------------------------------------------------------------------
APP_NAME   := gbp-play-gba
BUILD_ID   ?= vehicle-0001

STARTUP_MODE ?= GBP_STARTUP_NORMAL
GIT_COMMIT ?= $(shell git -C "$(CURDIR)" rev-parse --short=7 HEAD 2>/dev/null || echo unknown)
# -dirty when a TRACKED file differs from HEAD or ANY file under the sources this image is built from is untracked (`git diff --quiet HEAD` alone never sees an untracked source file; review of the build half)
GIT_DIRTY  ?= $(shell { git -C "$(CURDIR)" diff --quiet HEAD -- 2>/dev/null && test -z "$$(git -C "$(CURDIR)" status --porcelain --untracked-files=normal -- ../../src ../../poc/gbp-play-gba ../../tools 2>/dev/null)"; } || echo -dirty)
COMMIT_ID  := $(GIT_COMMIT)$(GIT_DIRTY)

#---------------------------------------------------------------------------------
# Layout
#---------------------------------------------------------------------------------
ROOT    := $(abspath $(CURDIR)/../..)
OUTDIR  ?= $(ROOT)/build/poc/$(APP_NAME)
OBJDIR  := $(OUTDIR)/obj
TARGET  := $(OUTDIR)/$(APP_NAME)

vpath %.c $(CURDIR)/source $(ROOT)/src/common $(ROOT)/src/log $(ROOT)/src/gbp $(ROOT)/src/audio $(ROOT)/src/platform

# The V28 chassis' source list less gbp_atrans2, the four research handlers and gbp_v28_dma; plus gbp_play_under (V31.3) and gbp_cartdecl (V31.4).
SRCS := main.c opengbp_ident.c ringlog.c gbp_transport.c gbp_detect.c gbp_rawlog.c gbp_regwrite.c gbp_initirqa_probe.c gbp_irq_service.c gbp_crc32.c gbp_avblock.c gbp_time64.c gbp_vsig.c gbp_vstate.c gbp_vpix.c gbp_vqueue.c gbp_vpresent.c gbp_vwitness.c gbp_vcolor.c gbp_vstate_probe.c gbp_vstatedump.c gbp_input.c gbp_session.c gbp_awin.c gbp_aperiod.c gbp_adec2.c gbp_aresamp2.c gbp_alive.c gbp_aplay2.c gbp_walker.c gbp_play_under.c gbp_cartdecl.c hsp_backend.c hsp_backend_irq.c sdlog.c
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
	@rm -rf $(ROOT)/build/poc/$(APP_NAME)

-include $(DEPS)
