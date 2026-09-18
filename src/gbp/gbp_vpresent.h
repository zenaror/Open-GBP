/*
 * gbp_vpresent.h — the presentation ownership of GBP-VIDEO-004, extracted from
 * the POC so it can be TESTED (HARDWARE_TESTS §V5.26.2, §V5.26.8).
 *
 * ---- WHY THIS MODULE EXISTS -----------------------------------------------
 *
 * `stream-0001` was rejected before hardware for one defect: its draw-done
 * callback freed EVERY buffer in `TEX_SUBMITTED`, while a DrawDone token
 * certifies only the commands queued before it. With two frames in flight the
 * first token freed both, and the CPU could then refill a texture the GP was
 * still reading. The defect survived a green test suite because it lived in
 * `main.c`, which has no behavioural test: the host tests asserted only that the
 * string `on_draw_done` appeared in the source.
 *
 * So the rule is not "be more careful in main.c". The rule is that ownership
 * lives HERE, in a module that knows nothing about GX, VI or libogc2, and that a
 * host test can drive state by state.
 *
 * ---- THE SAFETY RULE, CHOSEN FOR PROVABILITY ------------------------------
 *
 * AT MOST ONE DRAW-DONE TOKEN IS EVER IN FLIGHT.
 *
 *     FREE -> CPU_FILLING -> READY -> SUBMITTED -> (draw-done) -> FREE
 *
 * Two texture buffers are still allowed, and they are still useful: one can be
 * READY, waiting, while another is being filled, and a READY buffer never blocks
 * the producer. But `gbp_vpresent_submit()` REFUSES while a token is pending, so
 * the callback's job is unambiguous — release the one submitted buffer, and
 * nothing else. A queue of tokens would also work and would be harder to prove;
 * §V5.26.9 asked for the version that can be proved.
 *
 * `gbp_vpresent_draw_done()` therefore releases exactly one buffer, by index,
 * and a callback that arrives with nothing submitted is counted as
 * `drawdone_spurious` rather than being allowed to free something.
 *
 * ---- THE XFB RULE, KEPT SEPARATE --------------------------------------------
 *
 * Texture lifetime and framebuffer lifetime are different things and are not
 * coupled here. A DrawDone says the GP finished READING THE TEXTURE. It says
 * nothing about whether the VI has finished SCANNING OUT a framebuffer.
 *
 * `stream-0001` copied into the framebuffer the VI was scanning out. This module
 * instead answers "which XFB may I copy into?" from two facts the caller reads
 * non-blockingly from the VI — which buffer is current, and which one we already
 * handed over — and returns -1 when neither is safe, so the caller skips a
 * present instead of waiting. NOTHING here waits for a retrace.
 *
 * ---- SYNCHRONISATION -------------------------------------------------------
 *
 * Exactly two functions may be called from the draw-done interrupt:
 * `gbp_vpresent_draw_done()` and nothing else. Every other entry point is
 * main-side. The shared state is `tex[]` (one byte each) and `submitted` (an
 * int), all `volatile`, all naturally aligned, and all written with single
 * stores — atomic on PowerPC. No barrier is required, because the "concurrency"
 * is one core and its own interrupt handler, not two masters or a DMA engine.
 *
 * The one ordering the caller MUST honour is stated on `gbp_vpresent_submit()`.
 */
#ifndef OPENGBP_GBP_VPRESENT_H
#define OPENGBP_GBP_VPRESENT_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Two is the minimum that lets one buffer wait while another is filled, and it
 * is what §V5.8 named. More would not make the one-token rule any safer. */
#define GBP_VPRESENT_TEX_BUFFERS 2u
#define GBP_VPRESENT_XFB_BUFFERS 2u

enum gbp_vpresent_tex_state {
    GBP_VPRESENT_FREE = 0,      /* nobody owns it; the CPU may take it          */
    GBP_VPRESENT_CPU_FILLING,   /* the CPU is writing it                        */
    GBP_VPRESENT_READY,         /* filled and flushed; waiting for a free token */
    GBP_VPRESENT_SUBMITTED      /* the GP owns it; ONLY the callback frees it   */
};

struct gbp_vpresent {
    /* ---- texture ownership ---- */
    volatile uint8_t tex[GBP_VPRESENT_TEX_BUFFERS];
    volatile int     submitted;      /* the ONE buffer the GP owns, or -1       */
    int              shutting_down;  /* no new acquisitions or submissions      */

    /* ---- XFB ownership, entirely separate from the above ---- */
    int xfb_pending;                 /* handed to the VI, not yet current, or -1 */

    /* ---- counters, all bounded, all plain increments ---- */
    uint32_t acquire_attempts;
    uint32_t acquire_no_free_texture;  /* NOT a GPU-safety counter: see the note */
    uint32_t fills_started;
    uint32_t fills_completed;
    uint32_t fills_abandoned;
    uint32_t submit_attempts;
    uint32_t submit_success;
    uint32_t submit_blocked_inflight;  /* a token was already pending           */
    uint32_t submit_blocked_shutdown;
    uint32_t drawdone_callbacks;
    uint32_t drawdone_spurious;        /* a callback with nothing submitted      */
    uint32_t texture_releases;
    uint32_t xfb_presents;
    uint32_t xfb_skipped_busy;         /* no XFB was safe to copy into           */

    /* ---- R8: the invariants, LATCHED, not only sampled at the end ----
     *
     * `stream-0002` evaluated `gbp_vpresent_consistent()` in its self-test and
     * in its final report and nowhere else, so it could only ever say the
     * invariants held AT ITS LAST INSTANT. A violation that healed before the
     * report would have been invisible (HARDWARE_TESTS §V5.28.16, R8).
     *
     * Every state transition now checks itself and LATCHES a failure, so a
     * transient impossible state is still counted after it heals. The main side
     * and the interrupt keep separate counters, because a read-modify-write on
     * one shared counter could lose the interrupt's increment; the report sums
     * them and never has to argue about it. Both saturate rather than wrap. */
    uint32_t invariant_checks;         /* main-side checks performed             */
    uint32_t invariant_failures;       /* main-side failures, LATCHED, saturating */
    uint32_t invariant_checks_isr;     /* the same, from the draw-done callback   */
    uint32_t invariant_failures_isr;
};

/* ---- lifecycle ---------------------------------------------------------- */
void gbp_vpresent_init(struct gbp_vpresent *p);

/* Stop accepting new fills and new submissions. Does NOT touch a buffer the GP
 * still owns: `gbp_vpresent_inflight()` stays true until the callback fires or
 * the caller decides to wait for it (which it may only do AFTER the GBP service
 * has been torn down and restored — §V5.26.9). */
void gbp_vpresent_shutdown(struct gbp_vpresent *p);

/* True when the GP still owns a texture. The teardown uses this to decide
 * whether it must wait before the buffers can be considered dead. */
int gbp_vpresent_inflight(const struct gbp_vpresent *p);

/* ---- texture ownership, main side --------------------------------------- */

/* A FREE buffer to fill, or -1 when none is available. -1 is NOT a safety
 * event: it means the CPU has nothing to write into right now, which is a
 * throughput observation. `stream-0001`'s `no_free_buffer` was read as though it
 * proved the GP was never raced; it did not, and this name says so. */
int gbp_vpresent_acquire(struct gbp_vpresent *p);

/* The CPU finished writing `idx`. The caller must already have flushed it.
 * Returns 0, or -1 if `idx` was not CPU_FILLING. */
int gbp_vpresent_fill_done(struct gbp_vpresent *p, int idx);

/* The CPU gives up on `idx` (the generation guard rejected the frame). Returns
 * it to FREE without ever having been shown. Returns 0, or -1 on a bad index. */
int gbp_vpresent_abandon(struct gbp_vpresent *p, int idx);

/* Hand `idx` to the GP. Returns 1 when the caller may issue the draw and the
 * draw-done token, 0 when it must not (a token is already pending, or the
 * module is shutting down, or `idx` is not READY).
 *
 * ORDERING THE CALLER MUST HONOUR: this function marks the buffer SUBMITTED
 * BEFORE it returns, so the caller must issue `GX_SetDrawDone()` only AFTER a
 * return of 1, and must not touch the buffer again until the callback has
 * released it. Marking first and arming second is what makes the callback
 * unable to observe a half-built state. */
int gbp_vpresent_submit(struct gbp_vpresent *p, int idx);

/* ---- texture ownership, INTERRUPT side ----------------------------------- */

/* The GP finished the commands up to the pending token, so the single submitted
 * buffer is free. THIS IS THE ONLY FUNCTION THE CALLBACK MAY CALL. It releases
 * exactly one buffer — by index, never "every SUBMITTED one" — and returns that
 * index, or -1 when nothing was submitted (counted as spurious). */
int gbp_vpresent_draw_done(struct gbp_vpresent *p);

/* ---- XFB ownership, kept apart from every line above ---------------------- */

/* Which stream framebuffer may be copied into, given the index the VI is
 * CURRENTLY scanning out (or -1 when the caller cannot tell). Returns -1 when
 * none is safe, and the caller then skips the present rather than waiting.
 *
 * The rule, in full: a buffer is unsafe if the VI is scanning it, and unsafe if
 * we already handed it over and the VI has not yet switched to it. With two
 * buffers that leaves exactly one candidate in the steady state. */
int gbp_vpresent_xfb_target(struct gbp_vpresent *p, int current);

/* The caller copied into `idx` and asked the VI to show it next. */
void gbp_vpresent_xfb_handed(struct gbp_vpresent *p, int idx);

/* Cheap, non-blocking: tell the module which buffer the VI is scanning now, so
 * a pending hand-over can be retired once the VI has picked it up. */
void gbp_vpresent_xfb_observe(struct gbp_vpresent *p, int current);

/* Every buffer is in exactly one state, at most one is SUBMITTED, and
 * `submitted` agrees with `tex[]`. Returns 1 when the invariants hold.
 *
 * PURE: it latches nothing and may be called from anywhere, as often as wanted.
 * It is what the module checks itself with at every transition. */
int gbp_vpresent_consistent(const struct gbp_vpresent *p);

/* R8: how many times the invariants were found broken DURING the run, main side
 * and interrupt side summed. Zero is the only acceptable value, and it means
 * something the end-of-run check alone never could — that no transition ever
 * produced an impossible state, not merely that the last one did not. */
uint32_t gbp_vpresent_invariant_failures(const struct gbp_vpresent *p);

/* How many checks produced that number, so a zero cannot be read as "never
 * looked". */
uint32_t gbp_vpresent_invariant_checks(const struct gbp_vpresent *p);

#ifdef __cplusplus
}
#endif
#endif
