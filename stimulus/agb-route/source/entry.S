/*
 * stimulus/agb-route/source/entry.S -- GitHub Issue #124, Round C: the FIRST read of SOUNDBIAS, before devkitARM's
 * crt0 runs.
 *
 * tools/gbaentry.py points the ROM header's entry branch (0x08000000) here instead of at crt0's rom_header_end, so
 * this is the first code of ours the AGB executes, in ARM state as the BIOS enters a cartridge. It reads SOUNDBIAS,
 * stores the value and a marker in OBJ palette RAM (colours 14 and 15 of OBJ palette 15, 0x050003FC), and branches to
 * crt0's start_vector exactly where crt0's own header branch would have landed. crt0 clears EWRAM and IWRAM's bss
 * but never palette RAM, and mode 3 never displays it; main reads the two halfwords back.
 *
 * route-bias0200 only (FORCE_BIAS defined): AFTER the read, SOUNDBIAS is written to its documented default, 0x0200
 * (GBATEK, a LEAD). One new variable against route-both; E still reads what was there before.
 *
 * Registers r0-r3 are scratch here and crt0 sets every register it uses; nothing is assumed about their contents.
 */
    .section .text.bias_entry, "ax", %progbits
    .arm
    .align 2
    .global bias_entry
    .type bias_entry, %function
bias_entry:
    ldr     r0, =0x04000088         @ SOUNDBIAS
    ldrh    r1, [r0]                @ E: read before anything of ours has run
    ldr     r2, =0x050003FC         @ OBJ palette 15, colour 14
    strh    r1, [r2]                @ the value
    ldr     r3, =0xB1A5
    strh    r3, [r2, #2]            @ colour 15: the marker, the stub ran
#ifdef FORCE_BIAS
    ldr     r1, =FORCE_BIAS
    strh    r1, [r0]                @ route-bias0200: the documented default, after E
#endif
    ldr     r0, =start_vector       @ devkitARM crt0's reset path, ARM code
    bx      r0
    .pool
    .size   bias_entry, . - bias_entry
