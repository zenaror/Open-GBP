#---------------------------------------------------------------------------------
# Open-GBP AOUT-HW-001 -- make the GameCube play it (GitHub Issue #86)
#
#     make -C poc/audio-output-replay        (inside the project container)
#
# Outputs go to build/poc/audio-output-replay/ (ignored by Git).
#
# AN OUTPUT-PATH TEST, NOT A GAME BOY PLAYER AUDIO TEST. It reads RUN 33's
# AUDIO-window sidecar from the SD card, builds the listening sequence with
# src/audio/gbp_alisten (the #81 decoder and resampler, unchanged) and plays it
# through the AI DMA at 32 kHz. NOTHING of the Game Boy Player is linked: no
# transport, no HSP backend, no GBP register write, no interrupt of its own.
# The `aout` audit profile (tools/poc_audit.py) proves it on the real listings.
#
# Run it with: make -C . aout-audit   (repository root)
#---------------------------------------------------------------------------------
.SUFFIXES:

ifeq ($(strip $(DEVKITPPC)),)
$(error "Please set DEVKITPPC in your environment. export DEVKITPPC=<path to>devkitPPC")
endif

include $(DEVKITPRO)/libogc2/gamecube_rules

#---------------------------------------------------------------------------------
# Identity
#---------------------------------------------------------------------------------
APP_NAME   := audio-output-replay
# Issue #86. aout-0001 is the first build. NOT PHYSICALLY EXECUTED; the run is
# staged by a separate Hardware Issue, bundled with GBP-AUDIO-005's.
BUILD_ID   := aout-0001
# EMBED=1 builds the DOLPHIN FLOW variant and nothing else: RUN 33's fixture is
# linked into the image (Dolphin has no SD2SP2), under its OWN build id and in its
# OWN output directory. It is never exported to Swiss and never run on the
# console -- the console image reads the fixture from the card, and refuses
# anything that is not RUN 33's.
EMBED ?= 0
ifeq ($(EMBED),1)
BUILD_ID   := aout-0001-dolphin
endif
GIT_COMMIT ?= $(shell git -C "$(CURDIR)" rev-parse --short=7 HEAD 2>/dev/null || echo unknown)
GIT_DIRTY  ?= $(shell git -C "$(CURDIR)" diff --quiet HEAD -- 2>/dev/null || echo -dirty)
COMMIT_ID  := $(GIT_COMMIT)$(GIT_DIRTY)

#---------------------------------------------------------------------------------
# Layout
#---------------------------------------------------------------------------------
ROOT    := $(abspath $(CURDIR)/../..)
OUTDIR  := $(ROOT)/build/poc/$(APP_NAME)$(if $(filter 1,$(EMBED)),-dolphin,)
OBJDIR  := $(OUTDIR)/obj
TARGET  := $(OUTDIR)/$(APP_NAME)

vpath %.c $(CURDIR)/source $(ROOT)/src/common $(ROOT)/src/log $(ROOT)/src/platform $(ROOT)/src/audio $(ROOT)/src/gbp

# the smoke test's list PLUS the #81 audio modules, the listening sequence, and the
# sidecar parser they use (gbp_awindump.c, with gbp_awin.c and gbp_crc32.c it
# references). No transport, no backend, no service path.
SRCS := main.c opengbp_ident.c ringlog.c sdlog.c gbp_alisten.c gbp_adec.c gbp_asrc.c gbp_aresamp.c gbp_awindump.c gbp_awin.c gbp_crc32.c
ifeq ($(EMBED),1)
SRCS += fixture_embed.S
endif
vpath %.S $(CURDIR)/source
OBJS := $(addprefix $(OBJDIR)/,$(patsubst %.S,%.o,$(SRCS:.c=.o)))
DEPS := $(OBJS:.o=.d)

#---------------------------------------------------------------------------------
# Flags
#---------------------------------------------------------------------------------
INCLUDE  := -I$(ROOT)/src/common -I$(ROOT)/src/log -I$(ROOT)/src/platform -I$(ROOT)/src/audio -I$(ROOT)/src/gbp -I$(LIBOGC_INC)
DEFINES  := -DOPENGBP_APP_NAME=\"$(APP_NAME)\" \
            -DOPENGBP_BUILD_ID=\"$(BUILD_ID)\" \
            -DOPENGBP_GIT_COMMIT=\"$(COMMIT_ID)\"
ifeq ($(EMBED),1)
DEFINES  += -DAOUT_EMBEDDED=1
endif

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

# EMBED=1 only: the fixture, decompressed from the versioned .gz, then linked by .incbin.
$(OUTDIR)/run33-audio.bin: $(ROOT)/captures/fixtures/hw-gamecube-gbp-2026-09-23-stream-0016-run33-audio.bin.gz | $(OBJDIR)
	$(SILENTMSG) fixture ... $(notdir $@)
	$(SILENTCMD)python3 -c "import gzip,sys; sys.stdout.buffer.write(gzip.open(sys.argv[1]).read())" $< > $@

$(OBJDIR)/%.o: %.S $(OUTDIR)/run33-audio.bin | $(OBJDIR)
	$(SILENTMSG) $(notdir $<)
	$(SILENTCMD)$(CC) -x assembler-with-cpp $(MACHDEP) -Wa,-I$(OUTDIR) -c $< -o $@

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
