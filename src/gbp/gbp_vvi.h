/*
 * gbp_vvi.h — the VI HAND-OVER / LATCH trace of GBP-VIDEO-007 (HARDWARE_TESTS
 * §V6.4, §V6.8; GitHub Issue #7). Pure, hardware-free, host-tested: no
 * allocation, no clock, no device, no filesystem, no blocking, no callback.
 *
 * ---- WHAT IT RECORDS, AND WHAT IT DOES NOT PROVE --------------------------
 *
 * One record per hand-over: which lifecycle, which XFB, when the runtime wrote
 * VIDEO_SetNextFramebuffer (CLAIM-C), and -- when the pump later observes that
 * libogc2's bookkeeping now reports that XFB as the current one -- the time,
 * the retrace count and the four VI framebuffer-base register halves read
 * back at that moment. `VIDEO_GetCurrentFramebuffer()` is libogc2's own
 * variable (`currentFb = nextFb` in its retrace handler), NOT a hardware
 * readback; the register readback is the closest read-only evidence the VI
 * gives, and it is STILL SOFTWARE EVIDENCE. Nothing here proves physical
 * scanout: that is the operator's observation (§V6.4), which no parser of this
 * file may classify.
 *
 * The observation happens where the pump already reads the current XFB. No VI
 * callback, no VIDEO_WaitVSync, nothing in the service path. A hand-over that
 * is followed by another before it was observed current is marked SUPERSEDED,
 * never invented as latched.
 */
#ifndef OPENGBP_GBP_VVI_H
#define OPENGBP_GBP_VVI_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_VVI_CAP          4096u
#define GBP_VVI_F_LATCHED    0x0001u   /* observed current after the hand-over */
#define GBP_VVI_F_SUPERSEDED 0x0002u   /* another hand-over came first */

struct gbp_vvi_rec {
    uint32_t frame_index;      /* the lifecycle's source key */
    uint32_t life;             /* the OGBPDISP2 lifecycle index */
    int16_t  xfb;              /* the stream XFB handed over (0 or 1) */
    uint16_t flags;
    uint32_t phys;             /* physical address of that XFB, what the VI registers should name */
    uint64_t t_handed;         /* the decision clock, the same instant OGBPDISP2 records */
    uint32_t retrace_handed;
    uint64_t t_latch;          /* first pump observation of current == xfb, or 0 */
    uint32_t retrace_latch;
    uint16_t vi14, vi15, vi18, vi19;   /* VI TFBL hi/lo, BFBL hi/lo, read at the latch */
};

struct gbp_vvi {
    struct gbp_vvi_rec *rec;
    uint32_t cap, n, overflow;
    int32_t  awaiting;         /* record index handed and not yet observed current, or -1 */
    uint32_t handed, latched, superseded, observe_calls;
};

void gbp_vvi_init(struct gbp_vvi *v, struct gbp_vvi_rec *recs, uint32_t cap);

/* A hand-over happened (VIDEO_SetNextFramebuffer + VIDEO_Flush). Returns the
 * record index, or -1 on overflow (counted). */
int gbp_vvi_handed(struct gbp_vvi *v, uint32_t frame_index, uint32_t life, int16_t xfb,
                   uint32_t phys, uint64_t t, uint32_t retrace);

/* The XFB whose latch is awaited, or -1: the caller reads the VI registers
 * ONLY when this equals the current XFB. One compare, no work otherwise. */
int gbp_vvi_awaiting(const struct gbp_vvi *v);

/* The pump saw the awaited XFB as current: close the record. Returns 1 when a
 * record was closed, 0 when nothing was awaited (counted as an observe call). */
int gbp_vvi_latch(struct gbp_vvi *v, uint64_t t, uint32_t retrace,
                  uint16_t vi14, uint16_t vi15, uint16_t vi18, uint16_t vi19);

#ifdef __cplusplus
}
#endif
#endif
