/*
 * gbp_vdisp.h — the DOWNSTREAM DISPOSITION TRACE of GBP-VIDEO-004
 * (HARDWARE_TESTS §V5.46). Observational only: it answers what happened to a
 * source frame after the assembler closed it, and it changes no policy.
 *
 * ---- WHY THIS EXISTS -------------------------------------------------------
 *
 * Run 4 established source continuity inside a prospectively qualified window:
 * 2 048 retained records, FRAME_ID 85..2132, no member missing. Over the SAME
 * capture the consumer converted 2 113 frames and 17 of them never reached a
 * framebuffer. The aggregate counters prove the PARTITION — 2 113 = 2 096 + 17 —
 * and say nothing about the CAUSE, because a counter is incremented after the
 * decision and keeps no record of the state that produced it.
 *
 * This module records that state. It does not fix anything.
 *
 * ---- WHAT THE ARCHITECTURE ACTUALLY IS, MEASURED BEFORE DESIGNING ----------
 *
 * There is no VI-driven display loop in this runtime. `VIDEO_WaitVSync()` is
 * never called in the capture path and no retrace callback is installed. A
 * "presentation opportunity" is therefore NOT a retrace: it is one call to
 * `submit_ready()`, which happens when a conversion completes (or when a READY
 * texture whose submit was refused is re-offered). Presents are SOURCE-driven.
 *
 * That is why this trace has two dimensions and not one:
 *
 *   LIFECYCLE   one record per source frame that entered the consumer, from
 *               take to terminal disposition
 *   EVENT       one record per DECISION — a submit_ready() call that got past
 *               the token gate and chose between an XFB and the previous image
 *
 * A refusal at the token gate is NOT an event. It is a counter on the lifecycle
 * record, because `pump()` runs 224 561 times in a 35 s run and one event per
 * refusal would be unbounded. (In run 4 `submit_blocked_inflight` was 0, so the
 * gate never refused at all; the counter exists so a future run cannot hide it.)
 *
 * ---- THE KEY IS GENERIC, AND THAT IS A RULE --------------------------------
 *
 * The trace keys on `gbp_vstate_frame.index`, the assembler's own monotonic
 * source-frame ordinal, which `struct gbp_vqueue_desc` already carries. It
 * never decodes OGBPIDX1, never reads a pixel, never learns what the stimulus
 * is. Joining a lifecycle to a FRAME_ID is an OFFLINE operation against
 * OGBPIDXCAP1, so the scientific witness and the consumer trace stay
 * independent and neither can contaminate the other.
 *
 * Lifetime and width of the key: assigned once in `close_frame()`, strictly
 * monotonic, `uint32_t`, and additionally bounded by the frame store's capacity
 * (16 384) within one run. It cannot wrap in any run this experiment can
 * perform. `GBP_VDISP_KEY_NONE` is the sentinel for "no frame", which is what
 * the synthetic display self-test uses — it must never acquire a real key.
 *
 * ---- CALLBACK SAFETY -------------------------------------------------------
 *
 * Exactly one entry point runs at interrupt time, `gbp_vdisp_drawdone()`. It
 * does no allocation, no formatting, no filesystem, no scan and no locking: it
 * indexes `life_of_tex[]` (written by main before the token was armed) and
 * writes two fields. Everything else is main-side.
 *
 * ---- FAIL CLOSED -----------------------------------------------------------
 *
 * Nothing wraps and nothing is overwritten. When either array is full the
 * module sets an overflow flag and stops recording, so a trace is either
 * complete or visibly incomplete, never silently rotated.
 */
#ifndef OPENGBP_GBP_VDISP_H
#define OPENGBP_GBP_VDISP_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Derived from the experiment, not chosen for roundness: run 4 closed 2 118
 * source frames, published 2 114 and took 2 113, and the scientific target is
 * 2 048 records plus a warm-up that has never exceeded 71 frames. 4 096 is
 * ~1.9x the largest population any run of this shape has produced. */
#define GBP_VDISP_LIFE_CAP   4096u
#define GBP_VDISP_EVENT_CAP  8192u

#define GBP_VDISP_KEY_NONE   0xFFFFFFFFu   /* the self-test, and nothing else */
#define GBP_VDISP_TEX_SLOTS  2u

/* Terminal disposition of ONE source frame. Every value below corresponds to
 * exactly one reachable branch; none is inferred offline. */
enum gbp_vdisp_disposition {
    GBP_VDISP_D_OPEN = 0,           /* still in flight when the run ended       */
    GBP_VDISP_D_SELECTED_NEW,       /* VIDEO_SetNextFramebuffer() called for it */
    /* HISTORICAL. stream-0007 discarded a frame's presentation when no XFB was
     * writable. Policy A never produces it: the frame is DEFERRED instead. It
     * is kept so run-5 sidecars keep their meaning, and it must NEVER be reused
     * to mean "temporarily deferred" (§V5.49.5). */
    GBP_VDISP_D_HOLD_PREVIOUS,
    GBP_VDISP_D_SLOT_OVERRUN,       /* the generation guard failed after convert*/
    GBP_VDISP_D_ABANDONED_NO_RAW,   /* the ring block went unreadable mid-convert*/
    /* NON-TERMINAL. The frame is alive, still READY, and will be offered again.
     * A lifecycle in this state at the end of the run is a TERMINAL_PENDING,
     * never a loss. */
    GBP_VDISP_D_DEFERRED,
    GBP_VDISP_D_TERMINAL_PENDING,   /* alive and un-handed-off when the run ended*/
    GBP_VDISP_D_COUNT
};

/* WHY a decision went the way it did. Observational: each maps to one exact
 * predicate in gbp_vpresent_xfb_target(), never to a motive. */
enum gbp_vdisp_reason {
    GBP_VDISP_R_NONE = 0,           /* an XFB was free; nothing to explain      */
    GBP_VDISP_R_XFB_BUSY,           /* current and pending were both spoken for */
    GBP_VDISP_R_XFB_SHUTDOWN,       /* the module was shutting down             */
    GBP_VDISP_R_COUNT
};

#define GBP_VDISP_F_IN_WINDOW  0x0001u  /* the witness was ARMED when taken     */
#define GBP_VDISP_F_SELFTEST   0x0002u  /* synthetic; never a source frame      */
#define GBP_VDISP_F_CONVERTED  0x0004u
#define GBP_VDISP_F_SUBMITTED  0x0008u
#define GBP_VDISP_F_DRAWDONE   0x0010u
#define GBP_VDISP_F_DECIDED    0x0020u
#define GBP_VDISP_F_EVER_DEFERRED 0x0040u  /* it was held back at least once    */
#define GBP_VDISP_F_ALL        0x007Fu

/* 128 bytes in OGBPDISP2. Timestamps are the GameCube Time Base (tb_hz reported by the
 * capture); 0 means "this stage never happened", which is why nothing here is
 * invented for a stage that cannot be observed.
 *
 * THERE IS NO SEPARATE PUBLISH TIMESTAMP, and that is a measurement, not an
 * omission. `gbp_vqueue_publish()` is called inside the SAME service cycle that
 * closed the frame, from the frame's own timestamps, and the publish hook
 * "reads no clock of its own". SOURCE CLOSE and PUBLISH are therefore one
 * event with one time, and recording it twice would be recording a stage this
 * architecture does not have. */
struct gbp_vdisp_life {
    uint32_t frame_index;        /* 0x00 the GENERIC source key                 */
    uint32_t seq;                /* 0x04 publish sequence                       */
    uint64_t t_close;            /* 0x08 closed AND published: one event        */
    uint64_t t_take;             /* 0x10 consumer took it                       */
    uint64_t t_convert_first;    /* 0x18 first conversion slice                 */
    uint64_t t_convert_done;     /* 0x20 40th tile row                          */
    uint64_t t_first_attempt;    /* 0x28 first presentation attempt             */
    uint64_t t_first_defer;      /* 0x30 first time it was held back            */
    uint64_t t_last_defer;       /* 0x38 last time it was held back             */
    uint64_t t_submit;           /* 0x40 token armed                            */
    uint64_t t_drawdone;         /* 0x48 GP released the texture (ISR)          */
    uint64_t t_decision;         /* 0x50 the TERMINAL decision                   */
    uint32_t retrace_take;       /* 0x58 VIDEO_GetRetraceCount() at take        */
    uint32_t retrace_decision;   /* 0x5C and at the terminal decision           */
    uint32_t convert_ticks;      /* 0x60 accumulated slice cost                 */
    uint32_t submit_refusals;    /* 0x64 token-gate refusals before it got in   */
    /* Defer attempts are AGGREGATED, not evented. The retry runs from pump(),
     * about every 158 us, so one event per attempt would be unbounded; the
     * count plus the first and last timestamps say the same thing in 16 bytes
     * (§V5.49.3). */
    uint32_t defer_attempts;     /* 0x68                                        */
    uint16_t slot;               /* 0x6C raw ring slot                          */
    uint16_t tex;                /* 0x6E texture buffer index                   */
    uint16_t disposition;        /* 0x70 enum gbp_vdisp_disposition             */
    uint16_t reason;             /* 0x72 enum gbp_vdisp_reason                  */
    uint32_t src_flags;          /* 0x74 the assembler's frame flags, verbatim  */
    uint32_t life_flags;         /* 0x78 GBP_VDISP_F_*                          */
    uint32_t reserved;           /* 0x7C zero                                   */
};

/* 40 bytes. One per DECISION. `xfb_current` and `xfb_pending` are the exact
 * inputs gbp_vpresent_xfb_target() saw, so the branch is reproducible offline
 * rather than trusted. */
struct gbp_vdisp_event {
    uint64_t t;                  /* 0x00                                        */
    uint32_t ordinal;            /* 0x08 decision number, from 0                */
    uint32_t retrace;            /* 0x0C VI retrace count at the decision       */
    uint32_t frame_index;        /* 0x10 the frame being offered                */
    uint32_t prev_index;         /* 0x14 the last frame that reached an XFB     */
    int16_t  xfb_current;        /* 0x18 what the VI was scanning               */
    int16_t  xfb_pending;        /* 0x1A handed over, not yet latched           */
    int16_t  xfb_target;         /* 0x1C what the module returned               */
    uint8_t  tex;                /* 0x1E                                        */
    uint8_t  decision;           /* 0x1F enum gbp_vdisp_disposition             */
    uint8_t  reason;             /* 0x20 enum gbp_vdisp_reason                  */
    uint8_t  tex_state[2];       /* 0x21 both texture states at the decision    */
    uint8_t  inflight;           /* 0x23 a token was pending                    */
    /* The newest frame the QUEUE knew about when the decision was taken, or
     * KEY_NONE when the mailbox was empty. It is what separates "the pipeline
     * was behind" from "the framebuffer was busy": a hold with a newer frame
     * already waiting is a different event from a hold with nothing behind it. */
    uint32_t newest_source;      /* 0x24                                        */
};

struct gbp_vdisp {
    struct gbp_vdisp_life  *life;
    struct gbp_vdisp_event *ev;
    uint32_t life_cap, ev_cap;
    uint32_t life_n, ev_n;
    uint32_t life_overflow, ev_overflow;
    /* main writes this before arming a token; the ISR reads it. -1 = none. */
    int32_t  life_of_tex[GBP_VDISP_TEX_SLOTS];
    uint32_t prev_selected;      /* last frame that reached an XFB              */
    uint32_t drawdone_unmatched; /* a token fired with no lifecycle attached    */
    uint32_t decisions;          /* == ev_n unless the event array overflowed   */
    /* §V5.49.6: disposition counters with NON-OVERLAPPING meanings. The
     * runtime's legacy `repeats` stood for a source drop and a display repeat
     * at once; nothing here does. */
    uint32_t source_handoffs;        /* frames that reached VIDEO_SetNextFramebuffer */
    uint32_t source_deferred_frames; /* frames held back at least once          */
    uint32_t source_defer_attempts;  /* total held-back offers, all frames      */
    uint32_t source_dropped_interior;/* must stay 0 under policy A              */
    uint32_t terminal_pending;       /* alive and un-handed-off at the end      */
    uint32_t max_deferred_depth;     /* READY-and-unhanded textures at once     */
    uint32_t order_violations;       /* a newer frame handed off before an older*/
    uint32_t last_handoff_index;     /* for the ordering invariant              */
    int      have_last_handoff;
};

/* `life` and `ev` are caller-owned arrays. Returns 0, or -1 on a bad argument. */
int  gbp_vdisp_init(struct gbp_vdisp *d, struct gbp_vdisp_life *life, uint32_t life_cap,
                    struct gbp_vdisp_event *ev, uint32_t ev_cap);

/* Opens a lifecycle at the moment the consumer TAKES a descriptor. Returns the
 * record index, or -1 when the array is full (which latches `life_overflow`
 * and records nothing). */
int  gbp_vdisp_take(struct gbp_vdisp *d, uint32_t frame_index, uint32_t seq,
                    uint16_t slot, uint32_t src_flags, uint64_t t_close,
                    uint64_t t_take, uint32_t retrace,
                    uint16_t tex, int in_window, int selftest);

void gbp_vdisp_convert_first(struct gbp_vdisp *d, int life, uint64_t t);
void gbp_vdisp_convert_done(struct gbp_vdisp *d, int life, uint64_t t, uint32_t ticks);
void gbp_vdisp_abandon(struct gbp_vdisp *d, int life, uint16_t disposition);
void gbp_vdisp_submit_refused(struct gbp_vdisp *d, int life);

/* Arms the texture->lifecycle mapping the ISR will use. Call it where the token
 * is armed and NOT before: the mapping must never name a frame the GP is not
 * yet working on. */
void gbp_vdisp_submit(struct gbp_vdisp *d, int life, uint64_t t);

/* NON-TERMINAL. The frame found no writable framebuffer and stays alive. The
 * FIRST call emits one event; every later call only advances the aggregate, so
 * a retry running every 158 us cannot flood the trace. */
void gbp_vdisp_defer(struct gbp_vdisp *d, int life, uint64_t t, uint32_t retrace,
                     int xfb_current, int xfb_pending, uint16_t reason,
                     const uint8_t *tex_state, uint32_t depth);

/* Closes every lifecycle still alive at the end of the run as TERMINAL_PENDING,
 * which is an edge state and never an interior loss. */
void gbp_vdisp_finish(struct gbp_vdisp *d);

/* THE ONLY INTERRUPT-TIME ENTRY POINT. `tex` is what gbp_vpresent_draw_done()
 * returned; a negative index or an unmapped slot increments
 * `drawdone_unmatched` and writes nothing. */
void gbp_vdisp_drawdone(struct gbp_vdisp *d, int tex, uint64_t t);

/* Records ONE decision and closes the lifecycle. `target` is what
 * gbp_vpresent_xfb_target() returned; `reason` explains a negative one. */
void gbp_vdisp_decision(struct gbp_vdisp *d, int life, uint64_t t, uint32_t retrace,
                        int xfb_current, int xfb_pending, int xfb_target,
                        uint16_t reason, const uint8_t *tex_state, int inflight,
                        uint32_t newest_source);

const struct gbp_vdisp_life  *gbp_vdisp_life_at(const struct gbp_vdisp *d, uint32_t i);
const struct gbp_vdisp_event *gbp_vdisp_event_at(const struct gbp_vdisp *d, uint32_t i);

/* 1 when nothing was lost: neither array overflowed and every token that fired
 * matched a lifecycle. A trace that is not intact cannot support a claim. */
int  gbp_vdisp_intact(const struct gbp_vdisp *d);

#ifdef __cplusplus
}
#endif
#endif
