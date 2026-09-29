#---------------------------------------------------------------------------------
# Open-GBP §V28 -- the latency validation round (GitHub Issue #128, frozen; #129/#130
# the follow-up execution checkpoint)
#
#     make -C poc/gbp-audio-v28                          (validation_run, the default)
#     make -C poc/gbp-audio-v28 PLAN=perceptual_no_phase1
#
# Outputs go to build/poc/gbp-audio-v28-<plan>/ (ignored by Git) -- a SEPARATE directory
# per plan, so both images can exist on disk at once.
#
# WHAT THIS IS. poc/gbp-audio-sync (frozen, untouched) with the WHOLE audio pipeline
# replaced by its native ("2") counterpart -- gbp_adec2/gbp_aresamp2/gbp_aplay2/gbp_atrans2 --
# and gbp_async's own P0..P3 session replaced by gbp_walker sequencing #128's own two frozen
# plans (src/audio/gbp_v28_plans.h): validation_run (navigate -> 3a -> 3b -> sweep, automatic)
# and perceptual_no_phase1 (navigate -> nulling, operator-driven). ONE source, TWO images,
# selected by PLAN at build time -- the perceptual image compiles the leak-prone fields out
# entirely (GBP_V28_PLAN_PERCEPTUAL), rather than hiding them at runtime (Issue #128 §7).
#
# Everything about video/vstate/vqueue/vpresent/GX/input/session/keylog/SD-save/teardown/
# startup-profile/safety-wall carries over from gbp-audio-sync UNCHANGED.
#---------------------------------------------------------------------------------
.SUFFIXES:

ifeq ($(strip $(DEVKITPPC)),)
$(error "Please set DEVKITPPC in your environment. export DEVKITPPC=<path to>devkitPPC")
endif

include $(DEVKITPRO)/libogc2/gamecube_rules

#---------------------------------------------------------------------------------
# Identity
#---------------------------------------------------------------------------------
APP_NAME   := gbp-audio-v28
PLAN       ?= validation_run
ifeq ($(PLAN),validation_run)
BUILD_ID     := v28-validation-0001
PLAN_DEFINE  := GBP_V28_PLAN_VALIDATION
else ifeq ($(PLAN),perceptual_no_phase1)
BUILD_ID     := v28-perceptual-0001
PLAN_DEFINE  := GBP_V28_PLAN_PERCEPTUAL
else ifeq ($(PLAN),diag_3a_stall)
BUILD_ID     := v28-diag3a-0001
PLAN_DEFINE  := GBP_V28_PLAN_DIAG_3A_STALL
else ifeq ($(PLAN),diag_loss)
BUILD_ID     := v28-diagloss-0001
PLAN_DEFINE  := GBP_V28_PLAN_DIAG_LOSS
else
$(error "Unknown PLAN '$(PLAN)': must be validation_run, perceptual_no_phase1, diag_3a_stall or diag_loss")
endif

STARTUP_MODE ?= GBP_STARTUP_NORMAL
GIT_COMMIT ?= $(shell git -C "$(CURDIR)" rev-parse --short=7 HEAD 2>/dev/null || echo unknown)
GIT_DIRTY  ?= $(shell git -C "$(CURDIR)" diff --quiet HEAD -- 2>/dev/null || echo -dirty)
COMMIT_ID  := $(GIT_COMMIT)$(GIT_DIRTY)

#---------------------------------------------------------------------------------
# Layout
#---------------------------------------------------------------------------------
ROOT    := $(abspath $(CURDIR)/../..)
OUTDIR  := $(ROOT)/build/poc/$(APP_NAME)-$(PLAN)
OBJDIR  := $(OUTDIR)/obj
TARGET  := $(OUTDIR)/$(APP_NAME)-$(PLAN)

vpath %.c $(CURDIR)/source $(ROOT)/src/common $(ROOT)/src/log $(ROOT)/src/gbp $(ROOT)/src/audio $(ROOT)/src/platform

# The native ("2") audio chain (gbp_adec2/gbp_aresamp2/gbp_aplay2/gbp_atrans2) replaces
# gbp_adec/gbp_aresamp/gbp_aplay/gbp_atrans; gbp_walker + the four §V28 handlers replace
# gbp_async; gbp_awr is DROPPED (Orchestrator's own decision, Issue #129/#130: no ride-along
# in either image). Everything else is gbp-audio-sync's own SRCS list, unchanged.
SRCS := main.c opengbp_ident.c ringlog.c gbp_transport.c gbp_detect.c gbp_rawlog.c gbp_regwrite.c gbp_initirqa_probe.c gbp_irq_service.c gbp_crc32.c gbp_avblock.c gbp_time64.c gbp_vsig.c gbp_vstate.c gbp_vpix.c gbp_vqueue.c gbp_vpresent.c gbp_vwitness.c gbp_vcolor.c gbp_vstate_probe.c gbp_vstatedump.c gbp_input.c gbp_session.c gbp_awin.c gbp_aperiod.c gbp_adec2.c gbp_aresamp2.c gbp_alive.c gbp_aplay2.c gbp_atrans2.c gbp_walker.c gbp_v28_3a.c gbp_v28_3b.c gbp_v28_loss.c gbp_v28_dma.c gbp_v28_sweep.c gbp_v28_nulling.c hsp_backend.c hsp_backend_irq.c sdlog.c
OBJS := $(addprefix $(OBJDIR)/,$(SRCS:.c=.o))
DEPS := $(OBJS:.o=.d)

#---------------------------------------------------------------------------------
# Flags
#---------------------------------------------------------------------------------
INCLUDE  := -I$(ROOT)/src/common -I$(ROOT)/src/log -I$(ROOT)/src/gbp -I$(ROOT)/src/audio -I$(ROOT)/src/platform -I$(LIBOGC_INC)
DEFINES  := -DOPENGBP_APP_NAME=\"$(APP_NAME)-$(PLAN)\" \
            -DOPENGBP_BUILD_ID=\"$(BUILD_ID)\" \
            -DOPENGBP_GIT_COMMIT=\"$(COMMIT_ID)\" \
            -DGBP_STARTUP_MODE=$(STARTUP_MODE) \
            -D$(PLAN_DEFINE)

CFLAGS   := -std=gnu11 -g -O2 -Wall -Wextra -Wshadow $(MACHDEP) $(INCLUDE) $(DEFINES)
LDFLAGS  := -g $(MACHDEP) -Wl,-Map,$(TARGET).map
LIBPATHS := -L$(LIBOGC_LIB)
LIBS     := -lfat -logc
LD       := $(CC)

export DEPSDIR := $(OBJDIR)

#---------------------------------------------------------------------------------
# Targets
#---------------------------------------------------------------------------------
.PHONY: all clean info both

all: $(TARGET).dol $(OUTDIR)/build-info.txt info

# Builds both plan images in one invocation, into their own separate output directories.
both:
	$(MAKE) -C $(CURDIR) PLAN=validation_run
	$(MAKE) -C $(CURDIR) PLAN=perceptual_no_phase1

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
	  echo "app=$(APP_NAME)-$(PLAN)"; \
	  echo "plan=$(PLAN)"; \
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
	@echo "---- build-info ($(PLAN)) ----"
	@cat $<

clean:
	@echo clean ...
	@rm -rf $(ROOT)/build/poc/$(APP_NAME)-validation_run $(ROOT)/build/poc/$(APP_NAME)-perceptual_no_phase1 \
	        $(ROOT)/build/poc/$(APP_NAME)-diag_3a_stall $(ROOT)/build/poc/$(APP_NAME)-diag_loss

-include $(DEPS)
