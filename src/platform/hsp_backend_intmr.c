#include "hsp_backend_intmr.h"

#include <gccore.h>

#define PI_INTMR (*(vu32 *)0xCC003004u)

static gbp_status h_write_intmr(void *ctx, uint32_t intmr)
{
    (void)ctx;
    /* Same register write libogc2's __SetInterrupts performs (_piReg[1] = imask).
     * Used by GBP-INIT-001 only; later probes go through __MaskIrq/__UnmaskIrq. */
    PI_INTMR = intmr;
    return GBP_OK;
}

void hsp_backend_intmr_transport(struct hsp_backend *b, struct gbp_transport *t)
{
    (void)b;
    t->write_intmr = h_write_intmr;
}
