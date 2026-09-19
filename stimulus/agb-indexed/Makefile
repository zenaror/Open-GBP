#---------------------------------------------------------------------------------
# Open-GBP GBP-VIDEO-004 — CONTROLLED INDEXED video stimulus, OGBPIDX1 (devkitARM)
#
# Run from inside the project container, e.g. from the repository root:
#
#     make stimulus                  # top-level wrapper (docker compose)
#
# or directly inside the container:
#
#     make -C stimulus/agb-indexed
#
# Outputs go to build/stimulus/agb-indexed/ (ignored by Git):
#     agb-indexed.elf        linked ELF
#     agb-indexed.gba        the ROM, header complement check patched
#     agb-indexed.map, build-info.txt, obj/main.o
#
# THE ROM IS A DEVELOPMENT ARTIFACT. It has never been run on hardware, and
# this repository documents no way to deliver it to the Game Boy Player's
# internal AGB (HARDWARE_TESTS §V3.7, PHYSICAL EXECUTION DEPENDENCY).
#
# devkitARM ships the GBA link script, crt0 and header, but this image has no
# `gbafix`, so the header's complement check byte (0x0BD) is computed and
# patched by tools/gbahdr.py, which also VERIFIES the 156-byte Nintendo logo
# area against the bytes the crt0 emitted and prints the whole header. Nothing
# about the ROM is assumed: the check is recomputed from the file itself.
#---------------------------------------------------------------------------------
.SUFFIXES:

ifeq ($(strip $(DEVKITARM)),)
export DEVKITARM := $(DEVKITPRO)/devkitARM
endif
ifeq ($(wildcard $(DEVKITARM)/bin/arm-none-eabi-gcc),)
$(error "devkitARM not found at $(DEVKITARM); this must be built inside the project container")
endif

#---------------------------------------------------------------------------------
# Identity
#---------------------------------------------------------------------------------
APP_NAME   := agb-indexed
STIM_ID    := indexed-0002
GAME_TITLE := OPENGBPINDEX
GAME_CODE  := IGBP
MAKER_CODE := OG
GIT_COMMIT ?= $(shell git -C "$(CURDIR)" rev-parse --short=7 HEAD 2>/dev/null || echo unknown)
GIT_DIRTY  ?= $(shell git -C "$(CURDIR)" diff --quiet HEAD -- 2>/dev/null || echo -dirty)
COMMIT_ID  := $(GIT_COMMIT)$(GIT_DIRTY)

#---------------------------------------------------------------------------------
# Layout
#---------------------------------------------------------------------------------
ROOT     := ../..
OUT      := $(ROOT)/build/stimulus/$(APP_NAME)
OBJ      := $(OUT)/obj
SRC      := source
TARGET   := $(OUT)/$(APP_NAME)

PREFIX   := $(DEVKITARM)/bin/arm-none-eabi-
CC       := $(PREFIX)gcc
OBJCOPY  := $(PREFIX)objcopy
OBJDUMP  := $(PREFIX)objdump
PYTHON   ?= python3

#---------------------------------------------------------------------------------
# Flags. -O2 with no library: the program calls nothing, so nothing is linked
# beyond devkitARM's GBA crt0. ARM (not Thumb) for the single function, because
# the ROM is written once and speed is irrelevant while auditability is not.
#---------------------------------------------------------------------------------
ARCH     := -mthumb-interwork -marm -mcpu=arm7tdmi -mtune=arm7tdmi
CFLAGS   := $(ARCH) -O2 -std=gnu11 -Wall -Wextra -Wpedantic -Wshadow -Wconversion \
            -fno-strict-aliasing -ffunction-sections -fdata-sections
LDFLAGS  := $(ARCH) -specs=gba.specs -Wl,-Map,$(TARGET).map -nostartfiles -Wl,--gc-sections

.PHONY: all clean info
all: $(TARGET).gba info

$(OBJ):
	@mkdir -p $(OBJ)

$(OBJ)/main.o: $(SRC)/main.c | $(OBJ)
	@echo "cc  $<"
	@$(CC) $(CFLAGS) -c $< -o $@

# -nostartfiles is NOT passed to the final link: gba.specs supplies gba_crt0.o,
# which is what emits the ROM header (entry branch, Nintendo logo area, title,
# codes and the complement-check placeholder).
$(TARGET).elf: $(OBJ)/main.o
	@echo "link $(@F)"
	@$(CC) $(ARCH) -specs=gba.specs -Wl,-Map,$(TARGET).map -Wl,--gc-sections $< -o $@

$(TARGET).gba: $(TARGET).elf
	@echo "objcopy -O binary"
	@$(OBJCOPY) -O binary $< $@
	@echo "header  $(@F)"
	@$(PYTHON) $(ROOT)/tools/gbahdr.py fix $@ --title "$(GAME_TITLE)" --game-code "$(GAME_CODE)" --maker "$(MAKER_CODE)"

info: $(TARGET).gba
	@printf '%s\n' "---- stimulus-info ----" > $(OUT)/build-info.txt
	@printf 'app=%s\n' "$(APP_NAME)"                >> $(OUT)/build-info.txt
	@printf 'stimulus_id=%s\n' "$(STIM_ID)"         >> $(OUT)/build-info.txt
	@printf 'commit=%s\n' "$(COMMIT_ID)"            >> $(OUT)/build-info.txt
	@printf 'rom=%s\n' "$(abspath $(TARGET).gba)"   >> $(OUT)/build-info.txt
	@printf 'elf=%s\n' "$(abspath $(TARGET).elf)"   >> $(OUT)/build-info.txt
	@printf 'cc=%s\n' "$$($(CC) --version | head -n1)" >> $(OUT)/build-info.txt
	@printf 'size_bytes=%s\n' "$$(wc -c < $(TARGET).gba)" >> $(OUT)/build-info.txt
	@printf 'sha256_rom=%s\n' "$$(sha256sum $(TARGET).gba | cut -d' ' -f1)" >> $(OUT)/build-info.txt
	@printf 'sha256_elf=%s\n' "$$(sha256sum $(TARGET).elf | cut -d' ' -f1)" >> $(OUT)/build-info.txt
	@printf 'status=%s\n' "IMPLEMENTED, NOT PHYSICALLY EXECUTED - development artifact" >> $(OUT)/build-info.txt
	@cat $(OUT)/build-info.txt

clean:
	@rm -rf $(OUT)
