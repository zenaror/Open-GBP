/*
 * gbp_input.h — the input path (Phase 5; GitHub Issues #18 and #19).
 *
 *   PADStatus-shaped sample ─► gbp_input_map ─► logical GBA set ─► gbp_keypad_encode ─► u16 word ─► gbp_keypad_write ─► transport.write_block
 *                               (L3: POLICY, data)                   (L1: DESCRIPTOR, data)               (one 32-byte block, index 0xC)
 *
 * docs/research/INPUT_PATH.md §7 is the design this file implements; §1–§3
 * of that document are the three layers and their evidence status. The
 * layers stay apart in the code exactly as they do on paper:
 *
 *   L3  gbp_input_map()      controller -> logical set, driven by a policy
 *                            TABLE passed in as data (INPUT_PATH.md §3.2).
 *                            The policy is this project's choice, never a
 *                            device fact; every threshold is a value in the
 *                            table, never a truth compiled into the code.
 *   L2  enum gbp_gba_key     the logical set in GBATEK's KEYINPUT numbering
 *                            (A = 0 … DOWN = 7, R = 8, L = 9). 1 = pressed in
 *                            this LOGICAL representation, which is neither
 *                            the AGB register's polarity nor the window's.
 *   L1  gbp_keypad_encode()  logical set -> the 16-bit KEYPAD word under a
 *                            DESCRIPTOR (ten bit positions and the pressed
 *                            polarity), applied bit for bit; the six unused
 *                            bits stay 0. gbp_keypad_block() lays the word
 *                            out in the 32-byte block; gbp_keypad_write()
 *                            sends it through the EXISTING transport boundary
 *                            (real backend, mock, replay): no new transport,
 *                            no new backend.
 *
 * THE BIT ASSIGNMENT LIVES IN EXACTLY ONE PLACE: GBP_KEYPAD_DESCRIPTOR in
 * gbp_input.c. Nothing else in the repository names a word bit for a logical
 * key; every consumer — the POC, the tests, the self-test — applies whatever
 * that table says. Its status is CORROBORATED, NOT FACT (EVIDENCE GBP-KEY-004;
 * UNKNOWNS U-GBP-010 stays OPEN); the definition carries the falsifier.
 *
 * The stateful step (struct gbp_input, gbp_input_step()) decides WHEN to
 * write: on the first pass, on a change of the word, and as a periodic
 * refresh every GBP_INPUT_REFRESH_MS (frozen by Issue #19; see the constant).
 * It runs in the pump slot of the service cycle — after the RE-ARM, under the
 * cause-pending yield rule, from the main loop — never in the ISR, never
 * between the service read and the re-arm, never overlapping a service DMA:
 * the write is the transport's synchronous, completion-polled 32-byte
 * transfer, the same class as the RE-ARM's IRQ write.
 *
 * INPUT_PATH.md §8: `t_poll` and `t_write` are FIELDS of the state, on the
 * transport's 64-bit time base; no latency figure is derived from them.
 * Issue #27 (GBP-KEY-009) SPENDS that guarantee: every write that is not a
 * refresh — first / change / retry — leaves a struct gbp_input_event with
 * the word, the logical set, the action and three instants of the same time
 * base (t_poll, t_attempt, t_done), which the caller renders as ONE ringlog
 * line (GBP_INPUT_EVENT_FMT, "KEY …") under a bound the caller owns. A
 * refresh never produces an event (RUN 14: 7 849 refreshes against 42
 * changes): it is counted, not recorded.
 *
 * Nothing here touches libogc, a clock or the device except through the
 * transport pointer the caller supplies: the whole module builds and runs on
 * the host (tests/unit/test_gbp_input.c).
 */
#ifndef OPENGBP_GBP_INPUT_H
#define OPENGBP_GBP_INPUT_H

#include <stddef.h>
#include <stdint.h>
#include "gbp_transport.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ---- L2: the logical GBA button set ---------------------------------------
 * GBATEK "4000130h - KEYINPUT" numbering (external/gbatek 64b5087a). */
#define GBP_GBA_KEYS 10u
enum gbp_gba_key {
    GBP_GBA_A = 0, GBP_GBA_B = 1, GBP_GBA_SELECT = 2, GBP_GBA_START = 3,
    GBP_GBA_RIGHT = 4, GBP_GBA_LEFT = 5, GBP_GBA_UP = 6, GBP_GBA_DOWN = 7,
    GBP_GBA_R = 8, GBP_GBA_L = 9
};
/* A logical set: bit k = key k pressed. 1 = pressed, LOGICAL polarity. */
typedef uint16_t gbp_gba_keys;
#define GBP_GBA_KEY_BIT(k) ((gbp_gba_keys)(1u << (k)))
#define GBP_GBA_KEYS_MASK ((gbp_gba_keys)0x03FFu)

/* ---- the controller sample -------------------------------------------------
 * libogc2's PADStatus (external/libogc2 ca03fb75, include/ogc/pad.h) in this
 * project's own type, so the host can build it. The button bits and the error
 * codes below are libogc2's; the POC asserts them against the library's own
 * macros at compile time. `err` == GBP_PAD_ERR_NONE is the only valid sample;
 * any other value is treated as "no usable controller" and releases every key
 * (GBI skips a pad whose err is nonzero: GBP-KEY-003). */
struct gbp_pad_sample {
    uint16_t buttons;
    int8_t stick_x, stick_y;
    int8_t substick_x, substick_y;
    uint8_t trigger_l, trigger_r;
    uint8_t analog_a, analog_b;
    int8_t err;
};
#define GBP_PAD_BUTTON_LEFT  0x0001u
#define GBP_PAD_BUTTON_RIGHT 0x0002u
#define GBP_PAD_BUTTON_DOWN  0x0004u
#define GBP_PAD_BUTTON_UP    0x0008u
#define GBP_PAD_BUTTON_Z     0x0010u
#define GBP_PAD_BUTTON_R     0x0020u
#define GBP_PAD_BUTTON_L     0x0040u
#define GBP_PAD_BUTTON_A     0x0100u
#define GBP_PAD_BUTTON_B     0x0200u
#define GBP_PAD_BUTTON_X     0x0400u
#define GBP_PAD_BUTTON_Y     0x0800u
#define GBP_PAD_BUTTON_START 0x1000u
#define GBP_PAD_ERR_NONE 0
#define GBP_PAD_ERR_NO_CONTROLLER (-1)

/* ---- L3: the policy, as data ------------------------------------------------
 * `button_mask[k]`: any of these controller button bits presses logical key k.
 * `stick_threshold` > 0: a main-stick deflection STRICTLY beyond it presses the
 *   direction (x > t Right, x < -t Left, y > t Up, y < -t Down); 0 = the stick
 *   is not read. libogc2's PAD_ScanPads() does not clamp (pad.c: PAD_Clamp is
 *   commented out), so the values are the raw signed bytes of the SI response.
 * `trigger_threshold` > 0: an analogue trigger STRICTLY above it presses L / R;
 *   0 = the analogue triggers are not read (the digital click still counts
 *   through button_mask).
 * `analog_ab_threshold` > 0: analogue A / B STRICTLY above it presses A / B;
 *   0 = not read.
 * `filter_opposites` 1: an opposite pair held together (Up + Down, Left +
 *   Right) is cleared, as the Start-up Disc's keypad setter does (GBP-KEY-002). */
struct gbp_input_policy {
    uint16_t button_mask[GBP_GBA_KEYS];
    int8_t stick_threshold;
    uint8_t trigger_threshold;
    uint8_t analog_ab_threshold;
    uint8_t filter_opposites;
};
/* The default stick threshold, NAMED because it is a policy value and not
 * evidence: Enhanced mGBA's ANALOG_DEADZONE (0x30) under the same libogc pad
 * path (external/mgba 8692b26b, src/platform/wii/main.c); GBI uses 50 or 25
 * depending on its table and the Disc's value is not traced (INPUT_PATH.md
 * §3.1). Phase 5's own physical test validates or revises it. */
#define GBP_INPUT_POLICY_STICK_THRESHOLD 48
/* INPUT_PATH.md §3.2's recommendation: A, B, Start and the D-pad 1:1; X and Y
 * = Select; Z reserved for the runtime and never sent; L / R on the digital
 * click only; the main stick as the D-pad; the C-stick unused; opposite
 * directions filtered; port 1 only. */
extern const struct gbp_input_policy GBP_INPUT_POLICY_DEFAULT;

/* Pure. Returns the logical set for one sample under one policy. */
gbp_gba_keys gbp_input_map(const struct gbp_pad_sample *s, const struct gbp_input_policy *p);

/* ---- L1: the descriptor and the word ----------------------------------------
 * `bit[k]` is the word bit that carries logical key k (0..15, all ten distinct);
 * `pressed_is_one` is the value that bit takes when the key is pressed. */
struct gbp_keypad_descriptor {
    uint8_t bit[GBP_GBA_KEYS];
    uint8_t pressed_is_one;
};
/* THE one place (gbp_input.c). */
extern const struct gbp_keypad_descriptor GBP_KEYPAD_DESCRIPTOR;

/* 1 when the ten positions are distinct and below 16 and the polarity is 0 or 1. */
int gbp_keypad_descriptor_valid(const struct gbp_keypad_descriptor *d);
/* The word bits the descriptor uses (the other bits are never written). */
uint16_t gbp_keypad_descriptor_mask(const struct gbp_keypad_descriptor *d);
/* Pure. Applies the descriptor bit for bit: the bit of every key takes
 * pressed_is_one when the key is pressed and its complement otherwise; the
 * bits outside the descriptor's mask are 0. */
uint16_t gbp_keypad_encode(gbp_gba_keys keys, const struct gbp_keypad_descriptor *d);
/* Pure. The inverse: decode(encode(keys)) == keys for a valid descriptor. */
gbp_gba_keys gbp_keypad_decode(uint16_t word, const struct gbp_keypad_descriptor *d);

/* The KEYPAD window: register index 0xC (REGISTERS.md; GBP-KEY-001). */
#define GBP_KEYPAD_INDEX 0xCu
/* base + (0xC << 20), offset 0 — the offset both references use. */
uint32_t gbp_keypad_addr(uint32_t base);
/* THE BLOCK LAYOUT, chosen once: the u16 replicated sixteen times, hi byte
 * first (GBI's builders 0x80015da0/0x80015da4, GBP-KEY-003) — so bytes 0x1E
 * and 0x1F carry hi/lo exactly where the Start-up Disc writes them
 * (GBP-KEY-002) and the other thirty bytes carry copies instead of the
 * previous transfer's leftovers. The same layout gbp_regwrite_u16_layout()
 * already uses for the IRQ register. */
void gbp_keypad_block(uint16_t word, uint8_t out[GBP_BLOCK_SIZE]);

/* attempted / completed: the same safety semantics as gbp_regwrite_result —
 * attempted is set BEFORE the transport is invoked, completed only on GBP_OK;
 * attempted && !completed means the device may have taken the data. */
struct gbp_keypad_write_result {
    uint16_t word;
    int attempted;
    int completed;
    gbp_status rc;
    struct gbp_xfer_info info;
    uint32_t addr;
    uint8_t raw[GBP_BLOCK_SIZE];
};
/* One 32-byte write of `word` at the KEYPAD window through the transport. */
void gbp_keypad_write(const struct gbp_transport *t, uint32_t base, uint16_t word,
                      struct gbp_keypad_write_result *out);

/* ---- the step: when to write ------------------------------------------------
 *
 * THE REFRESH PERIOD — the single named constant. Issue #19 froze the policy:
 * write on change PLUS a periodic refresh at this period.
 *
 * Why 5 ms: it is the Start-up Disc's reference value — its periodic callback
 * rewrites KEYPAD on every 5.000 ms tick while the AGB runs (GBP-KEY-002), and
 * GBI rewrites it on every interrupt (GBP-KEY-003). NEITHER reference proves
 * that the device NEEDS a refresh for a held key; both simply do it. Matching
 * the known-good official behaviour before experimenting is what CLAUDE.md §18
 * asks, so the refresh is on, at the Disc's period, and whether a held key
 * ever drops without it is a question for a physical run, not for this
 * constant. */
#define GBP_INPUT_REFRESH_MS 5u

enum gbp_input_action {
    GBP_INPUT_NONE = 0,           /* nothing written this step */
    GBP_INPUT_WRITE_FIRST = 1,    /* the first write of the session: the device's state is unknown */
    GBP_INPUT_WRITE_CHANGE = 2,   /* the word differs from the last one the device accepted */
    GBP_INPUT_WRITE_REFRESH = 3,  /* GBP_INPUT_REFRESH_MS elapsed since the last completed write */
    GBP_INPUT_WRITE_RETRY = 4     /* the previous attempt failed; one refresh period has passed since it */
};

struct gbp_input {
    /* configuration */
    const struct gbp_input_policy *policy;
    const struct gbp_keypad_descriptor *desc;
    uint32_t base;                 /* ARAM base; 0 until the caller knows it (no write before that) */
    uint64_t refresh_ticks;        /* GBP_INPUT_REFRESH_MS on the caller's time base; 0 = refresh on every step */
    /* state */
    int written;                   /* a write has COMPLETED since init */
    int last_failed;               /* the last attempt did not complete: retry no sooner than one period later */
    uint16_t word_written;         /* the last word the device accepted (valid when `written`) */
    uint64_t t_last_write;         /* time base right after the last completed write */
    uint64_t t_last_attempt;       /* time base at the last attempt, completed or not */
    gbp_gba_keys keys_last;        /* the last mapped set */
    uint16_t word_last;            /* the last encoded word (written or not) */
    /* INPUT_PATH.md §8 — the head instants of the latency chain; no figure is
     * derived from them. Since Issue #27 they are carried into the per-change
     * event below (never into a sidecar). */
    uint64_t t_poll;               /* the caller's instant right after its poll returned */
    uint64_t t_write;              /* the transport's instant right after the last completed write */
    /* Issue #27 (GBP-KEY-009): the last non-refresh write, until the caller takes it */
    struct gbp_input_event {
        uint32_t n;                /* 1-based: the events recorded since init, this one included */
        enum gbp_input_action action;   /* FIRST, CHANGE or RETRY -- never REFRESH, never NONE */
        gbp_gba_keys keys;         /* the logical set the word encodes */
        uint16_t word;             /* the word written, or attempted */
        uint64_t t_poll;           /* the caller's instant right after the poll (transport ticks64 base) */
        uint64_t t_attempt;        /* the transport's instant right before write_block */
        uint64_t t_done;           /* the transport's instant right after a COMPLETED write; 0 otherwise */
        uint32_t xfer_ticks;       /* the transport's completion wait of a completed write; 0 otherwise */
        gbp_status rc;
        uint8_t completed;
        uint8_t pending;           /* 1 from the step that produced it until gbp_input_take_event() */
    } event;
    uint32_t events_recorded;      /* non-refresh writes, completed or not */
    uint32_t events_overwritten;   /* a pending event replaced before the caller took it (0 when the caller takes every one) */
    /* counters (bounded increments; no log line per step) */
    uint32_t steps;
    uint32_t samples_invalid;      /* err != GBP_PAD_ERR_NONE: the set was released */
    uint32_t keys_changes;         /* the logical set differed from the previous step's */
    uint32_t skipped_no_base;      /* steps before the ARAM base was known */
    uint32_t attempts;
    uint32_t writes_completed;
    uint32_t writes_failed;
    uint32_t writes_first, writes_change, writes_refresh, writes_retry;
    gbp_status last_rc;
    struct gbp_keypad_write_result last_write;
    /* the transport's completion wait of completed writes (xfer_info.ticks) */
    uint32_t write_ticks_min, write_ticks_max, write_ticks_n;
    uint64_t write_ticks_sum;
    /* the whole slot step as the caller measured it (poll + map + encode + write) */
    uint32_t step_ticks_min, step_ticks_max, step_ticks_n;
    uint64_t step_ticks_sum;
};

/* tb_hz: the time base the caller's instants are on (the transport's ticks64). */
void gbp_input_init(struct gbp_input *in, const struct gbp_input_policy *policy,
                    const struct gbp_keypad_descriptor *desc, uint32_t tb_hz);
void gbp_input_set_base(struct gbp_input *in, uint32_t base);

/* Pure: the decision for `word` at instant `now`, from the state alone. */
enum gbp_input_action gbp_input_decide(const struct gbp_input *in, uint16_t word, uint64_t now);

/* One step: map, encode, decide, and write when the decision says so. The
 * caller polled the controller into `s` and took `t_poll` right after the
 * poll returned; `now` for the decision and `t_write` come from the
 * transport's ticks64 (falling back to t_poll when it has none). Never
 * blocks beyond the transport's own bounded transfer; never fails the
 * caller: a failed write is counted and retried one period later. */
enum gbp_input_action gbp_input_step(struct gbp_input *in, const struct gbp_transport *t,
                                     const struct gbp_pad_sample *s, uint64_t t_poll);

/* ---- Issue #27 (GBP-KEY-009): the per-change record ------------------------
 * THE ONE FORMAT of the "KEY" ringlog line, rendered by gbp_input_event_render()
 * on the host and by the caller's ringlog_printf() on the target with the same
 * argument list (GBP_INPUT_EVENT_ARGS). Fields: the event number, the action,
 * the logical set, the word, the three instants (hex, the transport's ticks64
 * base -- the same as OGBPIDXCAP1 / OGBPDISP2 / OGBPVI1, so a join needs no
 * conversion), the transport's completion wait and its status. Its rendered
 * length never exceeds GBP_INPUT_EVENT_RENDER_MAX, proven at the worst case of
 * every conversion by tests/unit/test_gbp_input.c and tests/host/
 * test_input_keylog.py -- below the ringlog's 248-character payload. */
#define GBP_INPUT_EVENT_FMT "KEY n=%lu act=%s keys=%04x word=%04x t_poll=%llx t_attempt=%llx t_done=%llx xfer=%lu rc=%s"
#define GBP_INPUT_EVENT_ARGS(e) \
    (unsigned long)(e)->n, gbp_input_action_name((e)->action), (unsigned)(e)->keys, (unsigned)(e)->word, \
    (unsigned long long)(e)->t_poll, (unsigned long long)(e)->t_attempt, (unsigned long long)(e)->t_done, \
    (unsigned long)(e)->xfer_ticks, gbp_status_name((e)->rc)
#define GBP_INPUT_EVENT_RENDER_MAX 160u
/* Copies the pending event into *out and clears it; returns 1, or 0 (and
 * leaves *out untouched) when no event is pending. */
int gbp_input_take_event(struct gbp_input *in, struct gbp_input_event *out);
/* Renders GBP_INPUT_EVENT_FMT into dst (cap bytes, NUL included); returns the
 * length the full line has, as snprintf does. */
int gbp_input_event_render(const struct gbp_input_event *e, char *dst, size_t cap);
/* The caller's bound, pure: 1 when a line may be added to a store of
 * `capacity` lines holding `used` while keeping `reserve` lines free for
 * whatever must still be written after the run; 0 otherwise (the caller
 * counts the event as lost -- never blocks, never drops silently). */
int gbp_input_keylog_admit(uint32_t used, uint32_t capacity, uint32_t reserve);

/* The caller reports what the whole slot step cost, in its own tick unit. */
void gbp_input_note_step_ticks(struct gbp_input *in, uint32_t ticks);
uint32_t gbp_input_write_ticks_mean(const struct gbp_input *in);
uint32_t gbp_input_step_ticks_mean(const struct gbp_input *in);
const char *gbp_input_action_name(enum gbp_input_action a);

/* Pure, device-free: the shipped descriptor is well-formed, encode/decode is
 * the identity over every logical set with the unused bits 0, the default
 * policy maps a synthetic sample and filters an opposite pair, and the block
 * layout carries hi/lo at bytes 0x1E/0x1F. Returns 1 when everything holds.
 * It asserts nothing about WHICH bit carries L or R. */
int gbp_input_selftest(void);

#ifdef __cplusplus
}
#endif
#endif
