/*
 * gbp_awin.h — the AUDIO WINDOW store of GBP-AUDIO-001 (HARDWARE_TESTS §V8;
 * GitHub Issue #59). It retains whole runs of consecutive AUDIO blocks around
 * the presses that §V8.10 asks the Operator for, plus ONE window of the same
 * size taken before the first press: §V8.5.1's within-run silent control,
 * without which §V8.5.2 makes AU's positive verdict unavailable.
 *
 * WHY A WINDOW AND NOT THE WHOLE DECAY. §V8.3.2, frozen before any data
 * existed: one press emits ~6 717 blocks (27.5 MB) and four emit ~110 MB. The
 * discriminators that survive an unknown gain are the frequency transition and
 * the duty ratio, and both are readable in a few periods, so the capture is
 * four dense windows. THE SIZE IS NOT THIS MODULE'S TO CHOOSE: 256 blocks is
 * §V8.3.2's, derived there from the 16.74 ms the AGB may take to see the press
 * at all, and a build that quietly economised would answer a different
 * question than the one that was pre-registered.
 *
 * WHERE EACH HALF RUNS, AND WHY THAT IS SAFE.
 *
 *   gbp_awin_arm_press()  THE PUMP SLOT, from the input path, right after the
 *                         KEY write it describes. It touches the anchor and
 *                         then `active`; it never touches the store.
 *   gbp_awin_block()      THE SERVICE PATH, once per received AUDIO block,
 *                         after the drain and its commit. It copies 4096 bytes
 *                         in RAM. No device access, no allocation, no
 *                         filesystem, no clock read of its own (the caller
 *                         measures it and passes the ticks).
 *
 * The two never write the same field: `active` is SET only by an arm that
 * first read it negative, and CLEARED only by the fill that completed a
 * window; `filled` and the store are the fill's alone, and the arm may reset
 * them only while `active` is negative, i.e. while no fill can be running.
 * That is the whole concurrency argument, and it is why `active` is volatile.
 *
 * A PRESS THAT ARRIVES WHILE A WINDOW IS FILLING IS REFUSED AND COUNTED, and
 * so is one that arrives with every window used (§V8.7: "how the four windows
 * are armed so that a fifth press cannot silently overwrite the first"). A
 * refusal is never silent and never a failure: §V8.10 asks for three seconds
 * between presses and the refusal counter is how the run reports that it got
 * them.
 *
 * Nothing here includes libogc, a clock or the device: the module builds and
 * runs on the host (tests/unit/test_gbp_awin.c).
 */
#ifndef OPENGBP_GBP_AWIN_H
#define OPENGBP_GBP_AWIN_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* §V8.3.2, and GBP_VSTATE_AUDIO_BLOCK_SIZE for the block. These are the
 * pre-registration's numbers; the compile-time checks below are what stops a
 * later edit from changing the experiment by changing a constant. */
#define GBP_AWIN_BLOCK_SIZE     0x1000u
#define GBP_AWIN_BLOCKS         256u
#define GBP_AWIN_PRESS_WINDOWS  4u
#define GBP_AWIN_WINDOWS        (1u + GBP_AWIN_PRESS_WINDOWS)   /* + §V8.5.1's control */
#define GBP_AWIN_WINDOW_BYTES   (GBP_AWIN_BLOCKS * GBP_AWIN_BLOCK_SIZE)   /* 1 048 576 */
#define GBP_AWIN_STORE_BYTES    ((uint32_t)GBP_AWIN_WINDOWS * GBP_AWIN_WINDOW_BYTES)  /* 5 242 880 */

enum gbp_awin_kind {
    GBP_AWIN_CONTROL = 0,   /* §V8.5.1: taken before the first press */
    GBP_AWIN_PRESS   = 1
};

/* Window flags. CLOSED means the window reached its full block count; a window
 * the run ended inside is INCOMPLETE and says so. GAP means a drain that did
 * not complete was encountered while filling: the stored blocks are still
 * consecutive DRAINS but no longer consecutive in time, which the analysis has
 * to know before it estimates a period. */
#define GBP_AWIN_F_CLOSED       0x0001u
#define GBP_AWIN_F_INCOMPLETE   0x0002u
#define GBP_AWIN_F_GAP          0x0004u
#define GBP_AWIN_F_ALL          0x0007u

struct gbp_awin_anchor {
    uint32_t kind;          /* enum gbp_awin_kind */
    uint32_t ordinal;       /* 0 for the control; 1..4 for the presses, in press order */
    uint32_t flags;
    uint32_t event_n;       /* the KEY event's n (gbp_input_event.n); 0 for the control */
    uint32_t word;          /* the word written for that press; 0 for the control */
    uint32_t keys;          /* the logical set the word encodes */
    uint32_t blocks;        /* blocks actually stored */
    uint32_t skipped;       /* drains refused inside this window because they did not complete */
    uint64_t t_poll;        /* the three KEY instants, in the transport's ticks64 base */
    uint64_t t_attempt;
    uint64_t t_done;
    uint64_t t_arm;         /* when the window was armed, same base */
    uint64_t first_cycle;   /* the service delivery index of the first stored block */
    uint64_t last_cycle;
};

/* What an arm carries. The fields are passed explicitly rather than as a
 * struct gbp_input_event so that this module depends on nothing but stdint:
 * the coupling would buy nothing and would drag the input path into every
 * host test of the window. */
struct gbp_awin_press {
    uint32_t event_n, word, keys;
    uint64_t t_poll, t_attempt, t_done, t_arm;
};

struct gbp_awin {
    uint8_t *store;
    uint32_t store_bytes;
    uint32_t block_size, blocks_per_window, windows;
    volatile int active;        /* the filling window, or -1 */
    uint32_t filled;            /* blocks stored in the active window */
    uint32_t next_press;        /* 1..GBP_AWIN_PRESS_WINDOWS */
    struct gbp_awin_anchor anchor[GBP_AWIN_WINDOWS];
    /* what the run saw, and what it did not keep */
    uint32_t blocks_seen;       /* gbp_awin_block() calls */
    uint32_t blocks_stored;
    uint32_t blocks_ignored;    /* seen with no window armed: the expected majority */
    uint32_t blocks_failed;     /* seen with a window armed but the drain had not completed */
    uint32_t arms, arm_refused_busy, arm_refused_full, arm_refused_no_store;
    uint32_t windows_closed;
    /* the cost of the copy, MEASURED by the caller and reported, never asserted */
    uint32_t ticks_min, ticks_max, ticks_n;
    uint64_t ticks_sum;
    int fault;
};

/* 0 on success; -1 with `fault` set otherwise. The store must be at least
 * GBP_AWIN_STORE_BYTES and 32-byte aligned (it is written from the service
 * path and read back by a DMA-free copy, but the alignment keeps the copy on
 * whole cache lines). */
int gbp_awin_init(struct gbp_awin *w, uint8_t *store, uint32_t bytes);
const char *gbp_awin_fault(const struct gbp_awin *w);

/* THE PUMP SLOT. Returns the window index armed, or -1 when refused; every
 * refusal increments a counter and none is an error. */
int gbp_awin_arm_control(struct gbp_awin *w, uint64_t t_arm);
int gbp_awin_arm_press(struct gbp_awin *w, const struct gbp_awin_press *p);

/* THE SERVICE PATH. One call per received AUDIO block, whether or not a window
 * is armed and whether or not the drain completed. */
void gbp_awin_block(struct gbp_awin *w, const uint8_t *bytes, uint32_t len,
                    uint64_t cycle, int completed);
void gbp_awin_note_ticks(struct gbp_awin *w, uint32_t dt);

/* THE TEARDOWN. Marks a window still filling as INCOMPLETE and disarms, so the
 * sidecar never claims a window that was not finished. */
void gbp_awin_finish(struct gbp_awin *w);

/* Every press window closed: §V8.3.2's capture is complete and the POC may end
 * the session. The control is not required for this — a run whose control was
 * never armed is a build fault, and §V8.5.2 reads it as INCONCLUSIVE rather
 * than as a reason to keep running. */
int gbp_awin_complete(const struct gbp_awin *w);
unsigned gbp_awin_ticks_mean(const struct gbp_awin *w);
const uint8_t *gbp_awin_window_bytes(const struct gbp_awin *w, unsigned index);
uint32_t gbp_awin_stored_total(const struct gbp_awin *w);

#ifdef __cplusplus
}
#endif
#endif
