#---------------------------------------------------------------------------------
# Open-GBP GBP-AUDIO-013 — `agb-route`, `agb-sweep`'s stimulus with its LEFT/RIGHT routing as a build mode and
# SOUNDBIAS read three times (GitHub Issue #124, Round C), built with devkitARM
#
# FOUR IMAGES from one source, one value apart:
#     route-both      SOUNDCNT_L 0x1177  `agb-sweep`'s APU writes byte for byte (the archived stimulus)
#     route-left      SOUNDCNT_L 0x1077  channel 1 on the LEFT only
#     route-right     SOUNDCNT_L 0x0177  channel 1 on the RIGHT only
#     route-bias0200  route-both, and SOUNDBIAS written to its documented default 0x0200 at entry, AFTER the read
#
# Run from inside the project container, e.g. from the repository root:
#
#     make stimulus-route            # top-level wrapper (docker compose)
#
# or directly inside the container:
#
#     make -C stimulus/agb-route
#
# Outputs go to build/stimulus/agb-route/<variant>/ (ignored by Git):
#     agb-route-<variant>.elf / .gba / .map, crt0.dis (the linked entry path, disassembled), build-info.txt
#
# THE ENTRY. source/entry.S reads SOUNDBIAS before devkitARM's crt0; tools/gbaentry.py points the header's entry
# branch at it after the link and refuses any first word but crt0's own branch (or its own, on a rebuild). Then
# tools/gbahdr.py computes the header's complement, as for every stimulus here.
#
# THE ROM IS A DEVELOPMENT ARTIFACT until it is delivered (§V3.7 route 1, tools/gbaderive.py into build/physical/),
# and #124 authorises no delivery and no run. stimulus/agb-sweep IS NOT TOUCHED: it is the archived stimulus's
# source, and this ROM copies it rather than editing it.
#---------------------------------------------------------------------------------
.SUFFIXES:
# a recipe that fails (tools/gbaentry.py refusing, above all) leaves no half-made image that a later make would trust
.DELETE_ON_ERROR:

ifeq ($(strip $(DEVKITARM)),)
export DEVKITARM := $(DEVKITPRO)/devkitARM
endif
ifeq ($(wildcard $(DEVKITARM)/bin/arm-none-eabi-gcc),)
$(error "devkitARM not found at $(DEVKITARM); this must be built inside the project container")
endif

#---------------------------------------------------------------------------------
# Identity
#---------------------------------------------------------------------------------
APP_NAME   := agb-route
STIM_ID    := route-0001
GAME_TITLE := OPENGBPROUTE
GAME_CODE  := SGBR
MAKER_CODE := OG
GIT_COMMIT ?= $(shell git -C "$(CURDIR)" rev-parse --short=7 HEAD 2>/dev/null || echo unknown)
GIT_DIRTY  ?= $(shell git -C "$(CURDIR)" diff --quiet HEAD -- 2>/dev/null || echo -dirty)
COMMIT_ID  := $(GIT_COMMIT)$(GIT_DIRTY)

VARIANTS       := both left right bias0200
MIX_both       := 0x1177u
MIX_left       := 0x1077u
MIX_right      := 0x0177u
MIX_bias0200   := 0x1177u
FORCE_bias0200 := 0x0200

#---------------------------------------------------------------------------------
# Layout
#---------------------------------------------------------------------------------
ROOT     := ../..
SRC      := source
PREFIX   := $(DEVKITARM)/bin/arm-none-eabi-
CC       := $(PREFIX)gcc
OBJCOPY  := $(PREFIX)objcopy
OBJDUMP  := $(PREFIX)objdump
PYTHON   ?= python3
CRT0     := $(DEVKITARM)/arm-none-eabi/lib/gba_crt0.o

ARCH     := -mthumb-interwork -marm -mcpu=arm7tdmi -mtune=arm7tdmi
CFLAGS   := $(ARCH) -O2 -std=gnu11 -Wall -Wextra -Wpedantic -Wshadow -Wconversion \
            -fno-strict-aliasing -ffunction-sections -fdata-sections

.PHONY: all clean
ifeq ($(VARIANT),)
all:
	@for v in $(VARIANTS); do $(MAKE) --no-print-directory VARIANT=$$v || exit 1; done

clean:
	@rm -rf $(ROOT)/build/stimulus/$(APP_NAME)
else
OUT      := $(ROOT)/build/stimulus/$(APP_NAME)/$(VARIANT)
OBJ      := $(OUT)/obj
TARGET   := $(OUT)/$(APP_NAME)-$(VARIANT)
MIX      := $(MIX_$(VARIANT))
FORCE    := $(FORCE_$(VARIANT))
ifeq ($(MIX),)
$(error "unknown VARIANT $(VARIANT); one of: $(VARIANTS)")
endif
ASFLAGS  := $(ARCH) -x assembler-with-cpp $(if $(FORCE),-DFORCE_BIAS=$(FORCE))

all: $(TARGET).gba $(OUT)/crt0.dis $(OUT)/build-info.txt

$(OBJ):
	@mkdir -p $(OBJ)

$(OBJ)/main.o: $(SRC)/main.c Makefile | $(OBJ)
	@echo "cc  $< (ROUTE_MIX=$(MIX))"
	@$(CC) $(CFLAGS) -DROUTE_MIX=$(MIX) -c $< -o $@

$(OBJ)/entry.o: $(SRC)/entry.S Makefile | $(OBJ)
	@echo "as  $<$(if $(FORCE), (FORCE_BIAS=$(FORCE)))"
	@$(CC) $(ASFLAGS) -c $< -o $@

# gba.specs supplies gba_crt0.o (the header and start_vector); --require-defined keeps the stub, which nothing
# references until tools/gbaentry.py writes the branch to it
$(TARGET).elf: $(OBJ)/main.o $(OBJ)/entry.o
	@echo "link $(@F)"
	@$(CC) $(ARCH) -specs=gba.specs -Wl,-Map,$(TARGET).map -Wl,--gc-sections -Wl,--require-defined=bias_entry \
	    $^ -o $@

$(TARGET).gba: $(TARGET).elf
	@echo "objcopy -O binary"
	@$(OBJCOPY) -O binary $< $@
	@echo "entry   $(@F)"
	@$(PYTHON) $(ROOT)/tools/gbaentry.py $@ $< bias_entry
	@echo "header  $(@F)"
	@$(PYTHON) $(ROOT)/tools/gbahdr.py fix $@ --title "$(GAME_TITLE)" --game-code "$(GAME_CODE)" --maker "$(MAKER_CODE)"

# the entry path as linked, for the record (Issue #124: what crt0 clears): crt0's .crt0 section, then the stub, which
# the linker merges into .text (so it is selected by symbol, not by section)
$(OUT)/crt0.dis: $(TARGET).elf
	@$(OBJDUMP) -d -j .crt0 $< > $@
	@$(OBJDUMP) -d --disassemble=bias_entry $< >> $@

$(OUT)/build-info.txt: $(TARGET).gba $(OUT)/crt0.dis
	@printf '%s\n' "---- stimulus-info ----" > $@
	@printf 'app=%s\n' "$(APP_NAME)"                          >> $@
	@printf 'stimulus_id=%s-%s\n' "$(STIM_ID)" "$(VARIANT)"   >> $@
	@printf 'variant=%s\n' "$(VARIANT)"                       >> $@
	@printf 'route_mix=%s\n' "$(MIX)"                          >> $@
	@printf 'force_bias=%s\n' "$(if $(FORCE),$(FORCE),none)"   >> $@
	@printf 'commit=%s\n' "$(COMMIT_ID)"                      >> $@
	@printf 'rom=%s\n' "$(abspath $(TARGET).gba)"             >> $@
	@printf 'elf=%s\n' "$(abspath $(TARGET).elf)"             >> $@
	@printf 'cc=%s\n' "$$($(CC) --version | head -n1)"        >> $@
	@printf 'size_bytes=%s\n' "$$(wc -c < $(TARGET).gba)"     >> $@
	@printf 'sha256_rom=%s\n' "$$(sha256sum $(TARGET).gba | cut -d' ' -f1)" >> $@
	@printf 'sha256_elf=%s\n' "$$(sha256sum $(TARGET).elf | cut -d' ' -f1)" >> $@
	@printf 'sha256_gba_crt0=%s\n' "$$(sha256sum $(CRT0) | cut -d' ' -f1)"  >> $@
	@printf 'status=%s\n' "IMPLEMENTED, NOT PHYSICALLY EXECUTED - development artifact" >> $@
	@cat $@
endif
