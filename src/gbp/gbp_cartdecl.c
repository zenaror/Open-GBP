#include "gbp_cartdecl.h"

#include <stdio.h>

/* The Operator's GBA inventory, PHASE7_ENTRY.md section 5.1 (2026-09-29). The order is the session's (HARDWARE_TESTS.md V31.6) and then the rest.
 * Nothing is inferred to fill a cell: a title he named without a form is UNDECLARED, and no title is said to carry anything on the strength of this list. */
static const struct gbp_cartdecl_entry TABLE[] = {
    { "UNDECLARED (nothing selected)",                              "UNDECLARED" },
    { "Yoshi's Island (SMA3) on the EZ-Flash Omega DE NOR",         "FLASHCART_DELIVERED" },
    { "Kingdom Hearts: Chain of Memories (JP)",                     "ORIGINAL" },
    { "The Simpsons: Road Rage (paralelo)",                         "UNOFFICIAL" },
    { "WarioWare: Twisted (JP)",                                    "ORIGINAL" },
    { "WarioWare: Twisted (US)",                                    "ORIGINAL" },
    { "Drill Dozer (a ROM on a flashcart)",                         "FLASHCART_DELIVERED" },
    { "another title, not in this list",                            "UNDECLARED" },
};

#define N ((uint32_t)(sizeof TABLE / sizeof TABLE[0]))

uint32_t gbp_cartdecl_count(void)
{
    return N;
}

const struct gbp_cartdecl_entry *gbp_cartdecl_entry_at(uint32_t idx)
{
    return idx < N ? &TABLE[idx] : NULL;
}

uint32_t gbp_cartdecl_step(uint32_t idx, int dir)
{
    if (idx >= N) idx = GBP_CARTDECL_UNDECLARED;
    if (dir > 0) return (idx + 1u) % N;
    if (dir < 0) return (idx + N - 1u) % N;
    return idx;
}

int gbp_cartdecl_fmt(char *out, size_t cap, uint32_t idx, int confirmed)
{
    const struct gbp_cartdecl_entry *e;
    if (!confirmed || idx >= N) idx = GBP_CARTDECL_UNDECLARED;
    e = &TABLE[idx];
    return snprintf(out, cap, "CARTDECL idx=%lu title=\"%s\" form=%s mode=GBA entered=%s", (unsigned long)idx,
                    e->title, e->form, confirmed ? "pad_selection_after_session" : "none");
}
