/* F8 negative control 3: an exact call-site contract must count CALLS only.
 * gbp_initirqa_probe.o is pinned by profile 003a to exactly 3 gbp_regwrite_irq_u16
 * and 2 gbp_regwrite_control_byte call sites. This object makes exactly those calls
 * AND, on top, takes gbp_regwrite_irq_u16's address twice -- once in a data table
 * (a .rodata/.data relocation) and once in text (lis/addi, R_PPC_ADDR16_HA/LO).
 * Neither address-taking may inflate the count of 3. */
#include <stdint.h>
extern int gbp_regwrite_irq_u16(void *t, uint16_t v);
extern int gbp_regwrite_control_byte(void *t, uint8_t v);
typedef int (*irq_writer_fn)(void *, uint16_t);
const irq_writer_fn gbp_initirqa_irq_table[1] __attribute__((used)) = { gbp_regwrite_irq_u16 };
int gbp_initirqa_probe_run(void *t)
{
    int rc = 0;
    rc |= gbp_regwrite_control_byte(t, 0x92u);
    rc |= gbp_regwrite_irq_u16(t, 0x8AAEu);
    rc |= gbp_regwrite_irq_u16(t, 0x0000u);
    rc |= gbp_regwrite_irq_u16(t, 0x8FAAu);
    rc |= gbp_regwrite_control_byte(t, 0x90u);
    return rc;
}
uintptr_t gbp_initirqa_probe_writer_address(void)
{
    return (uintptr_t)gbp_regwrite_irq_u16;   /* address-taken in TEXT, not a call */
}
