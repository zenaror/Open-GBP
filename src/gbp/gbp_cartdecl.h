/*
 * gbp_cartdecl -- the cartridge declaration of the play vehicle's log (GitHub Issue #153, HARDWARE_TESTS.md V31.4): a compiled list of the
 * Operator's own GBA inventory (PHASE7_ENTRY.md section 5.1, his declarations of 2026-09-29, quoted there verbatim), the D-pad step through it, and the
 * ONE log line the selection produces.
 *
 * WHAT THE LINE IS. An OPERATOR DECLARATION, made at the console AFTER the session (before it the presses would reach the cartridge and the KEY
 * record), never a machine reading: nothing here can tell which cartridge is in the slot. If the declaration made before power-on (the procedure's
 * item 2) and this selection disagree, both are recorded and neither is resolved. The form is HIS word where he gave one (`ORIGINAL`, `UNOFFICIAL`
 * for "paralelo", `FLASHCART_DELIVERED` for a ROM on a flashcart; WarioWare: Twisted is `ORIGINAL` in both regions per HARDWARE_TESTS.md 7.6.4, the 2026-09-29 answer listing them without a form), and `UNDECLARED` where he gave none or nothing was selected.
 *
 * The first entry is UNDECLARED, and it is the default: an unconfirmed selection saves as idx=0 with `entered=none`.
 *
 * Pure: no device, no pad, no clock. The pad handling lives in the POC's final screen.
 */
#ifndef OPENGBP_GBP_CARTDECL_H
#define OPENGBP_GBP_CARTDECL_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_CARTDECL_UNDECLARED 0u

struct gbp_cartdecl_entry {
    const char *title;      /* plain ASCII, no double quote, at most 60 characters */
    const char *form;       /* ORIGINAL | UNOFFICIAL | FLASHCART_DELIVERED | UNDECLARED */
};

uint32_t gbp_cartdecl_count(void);
/* NULL when idx is out of range. */
const struct gbp_cartdecl_entry *gbp_cartdecl_entry_at(uint32_t idx);
/* dir > 0 steps forward, dir < 0 back, wrapping at both ends; an out-of-range idx is treated as UNDECLARED first. */
uint32_t gbp_cartdecl_step(uint32_t idx, int dir);
/* `CARTDECL idx=<k> title="<text>" form=<form> mode=GBA entered=<pad_selection_after_session|none>`; `confirmed` is whether the Operator pressed A on
 * the entry. An unconfirmed selection is written as the UNDECLARED entry whatever idx was stepped to. Returns the snprintf count. */
int gbp_cartdecl_fmt(char *out, size_t cap, uint32_t idx, int confirmed);

#ifdef __cplusplus
}
#endif
#endif
