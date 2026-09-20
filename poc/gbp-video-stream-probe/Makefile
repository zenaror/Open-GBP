#---------------------------------------------------------------------------------
# Open-GBP GBP-VIDEO-004 — GameCube build (devkitPPC + libogc2)
#
#     make -C poc/gbp-video-stream-probe        (inside the project container)
#
# Outputs go to build/poc/gbp-video-stream-probe/ (ignored by Git).
#
# THE AUDIT PROFILE IS `stream`, and it differs from every other profile in one
# way: `GX_` is PERMITTED in main.o and forbidden in every other object. That is
# HARDWARE_TESTS §V5.7's architectural boundary turned into a machine check —
# the display path lives in the POC, and nothing under src/gbp may reach the
# graphics pipeline. The profile also pins the two new call sites exactly:
# gbp_vqueue_publish exactly once inside gbp_vstate_probe_run, and gbp_vpix_frame
# never inside it at all.
#
# Run it with: make -C . stream-audit   (repository root)
#---------------------------------------------------------------------------------
.SUFFIXES:

ifeq ($(strip $(DEVKITPPC)),)
$(error "Please set DEVKITPPC in your environment. export DEVKITPPC=<path to>devkitPPC")
endif

include $(DEVKITPRO)/libogc2/gamecube_rules

#---------------------------------------------------------------------------------
# Identity
#---------------------------------------------------------------------------------
APP_NAME   := gbp-video-stream-probe
# §V5.52. stream-0009 is stream-0008's pipeline with a NORMAL startup: no
# visible synthetic frame and no pre-handler masked wait. The stream line is
# kept because the pipeline under test is the same one, which is what makes the
# comparison with the stream-0008 physical run direct.
# §V5.55. stream-0010 is stream-0009's startup and pipeline with ONE research
# addition: the scientific witness streak is not counted until 5000 ms after the
# CONTROL transform. Nothing the user sees changes; only when the window may open.
BUILD_ID   := stream-0010

# NORMAL by default. A diagnostic image -- visible self-test, 5000 ms wait -- is
#   make build STARTUP_MODE=GBP_STARTUP_DIAGNOSTIC
# and it is deliberately NOT the artifact that ships or that a physical run uses
# unless the run is explicitly reproducing a historical experiment.
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

SRCS := main.c opengbp_ident.c ringlog.c gbp_transport.c gbp_detect.c gbp_rawlog.c gbp_regwrite.c gbp_initirqa_probe.c gbp_irq_service.c gbp_crc32.c gbp_avblock.c gbp_time64.c gbp_vsig.c gbp_vstate.c gbp_vpix.c gbp_vqueue.c gbp_vpresent.c gbp_vwitness.c gbp_vidxdump.c gbp_vdisp.c gbp_vdispdump.c gbp_vcolor.c gbp_vstate_probe.c gbp_vstatedump.c hsp_backend.c hsp_backend_irq.c sdlog.c
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
