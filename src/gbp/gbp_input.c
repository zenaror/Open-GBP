#include "gbp_input.h"

#include <string.h>
#include "gbp_regwrite.h"
#include "gbp_time64.h"

/*
 * THE KEYPAD BIT ASSIGNMENT — the only place in the repository that names a
 * word bit for a logical key. Entry k is the word bit of logical key k, in
 * the order A, B, SELECT, START, RIGHT, LEFT, UP, DOWN, R, L (gbp_input.h,
 * GBATEK KEYINPUT numbering); the last field is the value a pressed key's bit
 * takes.
 *
 * STATUS: CORROBORATED, NOT FACT (docs/research/EVIDENCE.md GBP-KEY-004;
 * docs/research/UNKNOWNS.md U-GBP-010, which stays OPEN). The Start-up Disc
 * (0x8000822c, default mode), GBI (0x8000bf30, GameCube and N64 tables) and
 * Dolphin's model all write the L role at word bit 8 and the R role at bit 9
 * — the REVERSE of KEYINPUT's bit 8 = R, bit 9 = L — and bits 0–7 in
 * KEYINPUT's order, 1 = pressed. No measurement on this project's hardware
 * has shown what the GBS-DOL does with bits 8 and 9: the window is
 * write-only in every reference and only the AGB observes it. The Operator
 * chose (2026-09-21, Issue #19) to implement this assignment and let the
 * first physical run falsify it, rather than build a ten-bit stimulus first.
 *
 * WHAT FALSIFIES IT: a physical run with a game that distinguishes L from R
 * in which the GameCube L trigger acts as the GBA's R (OPERATOR OBSERVATION),
 * or a project-owned stimulus that publishes KEYINPUT into its video frames
 * and shows word bit 8 arriving on the R line. Then the two entries marked
 * below swap — ONE line — and nothing else in the runtime, the tests or the
 * documents changes, because every other place consumes this table.
 */
const struct gbp_keypad_descriptor GBP_KEYPAD_DESCRIPTOR = {
    { 0, 1, 2, 3, 4, 5, 6, 7, /* R -> bit */ 9, /* L -> bit */ 8 }, 1
};

const struct gbp_input_policy GBP_INPUT_POLICY_DEFAULT = {
    /* button_mask[k]: A, B, SELECT, START, RIGHT, LEFT, UP, DOWN, R, L */
    { GBP_PAD_BUTTON_A, GBP_PAD_BUTTON_B, GBP_PAD_BUTTON_X | GBP_PAD_BUTTON_Y, GBP_PAD_BUTTON_START,
      GBP_PAD_BUTTON_RIGHT, GBP_PAD_BUTTON_LEFT, GBP_PAD_BUTTON_UP, GBP_PAD_BUTTON_DOWN,
      GBP_PAD_BUTTON_R, GBP_PAD_BUTTON_L },
    GBP_INPUT_POLICY_STICK_THRESHOLD,   /* main stick as the D-pad */
    0,                                  /* analogue triggers: not read (digital click only) */
    0,                                  /* analogue A / B: not read */
    1                                   /* opposite directions filtered, as the Disc's setter */
};

/* ---- L3 ------------------------------------------------------------------- */

gbp_gba_keys gbp_input_map(const struct gbp_pad_sample *s, const struct gbp_input_policy *p)
{
    unsigned k;
    unsigned keys = 0;
    if (s->err != GBP_PAD_ERR_NONE) return 0;
    for (k = 0; k < GBP_GBA_KEYS; k++)
        if (s->buttons & p->button_mask[k]) keys |= 1u << k;
    if (p->stick_threshold > 0) {
        const int t = p->stick_threshold;
        if (s->stick_x > t) keys |= 1u << GBP_GBA_RIGHT;
        if (s->stick_x < -t) keys |= 1u << GBP_GBA_LEFT;
        if (s->stick_y > t) keys |= 1u << GBP_GBA_UP;
        if (s->stick_y < -t) keys |= 1u << GBP_GBA_DOWN;
    }
    if (p->trigger_threshold > 0) {
        if (s->trigger_l > p->trigger_threshold) keys |= 1u << GBP_GBA_L;
        if (s->trigger_r > p->trigger_threshold) keys |= 1u << GBP_GBA_R;
    }
    if (p->analog_ab_threshold > 0) {
        if (s->analog_a > p->analog_ab_threshold) keys |= 1u << GBP_GBA_A;
        if (s->analog_b > p->analog_ab_threshold) keys |= 1u << GBP_GBA_B;
    }
    if (p->filter_opposites) {
        const unsigned ud = (1u << GBP_GBA_UP) | (1u << GBP_GBA_DOWN);
        const unsigned lr = (1u << GBP_GBA_LEFT) | (1u << GBP_GBA_RIGHT);
        if ((keys & ud) == ud) keys &= ~ud;
        if ((keys & lr) == lr) keys &= ~lr;
    }
    return (gbp_gba_keys)(keys & GBP_GBA_KEYS_MASK);
}

/* ---- L1 ------------------------------------------------------------------- */

int gbp_keypad_descriptor_valid(const struct gbp_keypad_descriptor *d)
{
    unsigned k, seen = 0;
    if (!d || d->pressed_is_one > 1u) return 0;
    for (k = 0; k < GBP_GBA_KEYS; k++) {
        const unsigned b = d->bit[k];
        if (b > 15u) return 0;
        if (seen & (1u << b)) return 0;
        seen |= 1u << b;
    }
    return 1;
}

uint16_t gbp_keypad_descriptor_mask(const struct gbp_keypad_descriptor *d)
{
    unsigned k, m = 0;
    for (k = 0; k < GBP_GBA_KEYS; k++) m |= 1u << (d->bit[k] & 15u);
    return (uint16_t)m;
}

uint16_t gbp_keypad_encode(gbp_gba_keys keys, const struct gbp_keypad_descriptor *d)
{
    unsigned k, word = 0;
    for (k = 0; k < GBP_GBA_KEYS; k++) {
        const unsigned pressed = (keys >> k) & 1u;
        const unsigned value = pressed ? d->pressed_is_one : (d->pressed_is_one ^ 1u);
        if (value) word |= 1u << (d->bit[k] & 15u);
    }
    return (uint16_t)word;
}

gbp_gba_keys gbp_keypad_decode(uint16_t word, const struct gbp_keypad_descriptor *d)
{
    unsigned k, keys = 0;
    for (k = 0; k < GBP_GBA_KEYS; k++) {
        const unsigned value = (word >> (d->bit[k] & 15u)) & 1u;
        if (value == d->pressed_is_one) keys |= 1u << k;
    }
    return (gbp_gba_keys)keys;
}

uint32_t gbp_keypad_addr(uint32_t base)
{
    return gbp_block_addr(base, GBP_KEYPAD_INDEX, 0);
}

void gbp_keypad_block(uint16_t word, uint8_t out[GBP_BLOCK_SIZE])
{
    gbp_regwrite_u16_layout(word, out);
}

void gbp_keypad_write(const struct gbp_transport *t, uint32_t base, uint16_t word,
                      struct gbp_keypad_write_result *out)
{
    memset(out, 0, sizeof *out);
    out->word = word;
    out->addr = gbp_keypad_addr(base);
    gbp_keypad_block(word, out->raw);
    out->attempted = 1;
    out->rc = t->write_block(t->ctx, out->addr, out->raw, &out->info);
    out->completed = (out->rc == GBP_OK) ? 1 : 0;
}

/* ---- the step --------------------------------------------------------------- */

void gbp_input_init(struct gbp_input *in, const struct gbp_input_policy *policy,
                    const struct gbp_keypad_descriptor *desc, uint32_t tb_hz)
{
    memset(in, 0, sizeof *in);
    in->policy = policy;
    in->desc = desc;
    in->refresh_ticks = gbp_time64_from_ms(tb_hz, GBP_INPUT_REFRESH_MS);
}

void gbp_input_set_base(struct gbp_input *in, uint32_t base)
{
    in->base = base;
}

enum gbp_input_action gbp_input_decide(const struct gbp_input *in, uint16_t word, uint64_t now)
{
    if (in->last_failed)
        return gbp_time64_reached(in->t_last_attempt, in->refresh_ticks, now) ? GBP_INPUT_WRITE_RETRY
                                                                              : GBP_INPUT_NONE;
    if (!in->written) return GBP_INPUT_WRITE_FIRST;
    if (word != in->word_written) return GBP_INPUT_WRITE_CHANGE;
    if (gbp_time64_reached(in->t_last_write, in->refresh_ticks, now)) return GBP_INPUT_WRITE_REFRESH;
    return GBP_INPUT_NONE;
}

static void note_write_ticks(struct gbp_input *in, uint32_t ticks)
{
    if (in->write_ticks_n == 0u || ticks < in->write_ticks_min) in->write_ticks_min = ticks;
    if (ticks > in->write_ticks_max) in->write_ticks_max = ticks;
    in->write_ticks_n++;
    in->write_ticks_sum += ticks;
}

enum gbp_input_action gbp_input_step(struct gbp_input *in, const struct gbp_transport *t,
                                     const struct gbp_pad_sample *s, uint64_t t_poll)
{
    gbp_gba_keys keys;
    uint16_t word;
    uint64_t now;
    enum gbp_input_action act;

    in->steps++;
    in->t_poll = t_poll;
    if (s->err != GBP_PAD_ERR_NONE) {
        in->samples_invalid++;
        keys = 0;
    } else {
        keys = gbp_input_map(s, in->policy);
    }
    if (keys != in->keys_last) in->keys_changes++;
    in->keys_last = keys;
    word = gbp_keypad_encode(keys, in->desc);
    in->word_last = word;
    if (!in->base) {
        in->skipped_no_base++;
        return GBP_INPUT_NONE;
    }
    now = t->ticks64 ? t->ticks64(t->ctx) : t_poll;
    act = gbp_input_decide(in, word, now);
    if (act == GBP_INPUT_NONE) return act;

    in->attempts++;
    in->t_last_attempt = now;
    switch (act) {
    case GBP_INPUT_WRITE_FIRST: in->writes_first++; break;
    case GBP_INPUT_WRITE_CHANGE: in->writes_change++; break;
    case GBP_INPUT_WRITE_REFRESH: in->writes_refresh++; break;
    case GBP_INPUT_WRITE_RETRY: in->writes_retry++; break;
    default: break;
    }
    gbp_keypad_write(t, in->base, word, &in->last_write);
    in->last_rc = in->last_write.rc;
    if (in->last_write.completed) {
        in->writes_completed++;
        in->written = 1;
        in->last_failed = 0;
        in->word_written = word;
        in->t_write = t->ticks64 ? t->ticks64(t->ctx) : t_poll;
        in->t_last_write = in->t_write;
        note_write_ticks(in, in->last_write.info.ticks);
    } else {
        in->writes_failed++;
        in->last_failed = 1;
    }
    return act;
}

void gbp_input_note_step_ticks(struct gbp_input *in, uint32_t ticks)
{
    if (in->step_ticks_n == 0u || ticks < in->step_ticks_min) in->step_ticks_min = ticks;
    if (ticks > in->step_ticks_max) in->step_ticks_max = ticks;
    in->step_ticks_n++;
    in->step_ticks_sum += ticks;
}

uint32_t gbp_input_write_ticks_mean(const struct gbp_input *in)
{
    return in->write_ticks_n ? (uint32_t)(in->write_ticks_sum / in->write_ticks_n) : 0u;
}

uint32_t gbp_input_step_ticks_mean(const struct gbp_input *in)
{
    return in->step_ticks_n ? (uint32_t)(in->step_ticks_sum / in->step_ticks_n) : 0u;
}

const char *gbp_input_action_name(enum gbp_input_action a)
{
    switch (a) {
    case GBP_INPUT_NONE: return "none";
    case GBP_INPUT_WRITE_FIRST: return "first";
    case GBP_INPUT_WRITE_CHANGE: return "change";
    case GBP_INPUT_WRITE_REFRESH: return "refresh";
    case GBP_INPUT_WRITE_RETRY: return "retry";
    default: return "?";
    }
}

int gbp_input_selftest(void)
{
    const struct gbp_keypad_descriptor *d = &GBP_KEYPAD_DESCRIPTOR;
    const uint16_t mask = gbp_keypad_descriptor_mask(d);
    struct gbp_pad_sample s;
    uint8_t blk[GBP_BLOCK_SIZE];
    unsigned k;

    if (!gbp_keypad_descriptor_valid(d)) return 0;
    for (k = 0; k <= GBP_GBA_KEYS_MASK; k++) {
        const uint16_t w = gbp_keypad_encode((gbp_gba_keys)k, d);
        if (w & (uint16_t)~mask) return 0;
        if (gbp_keypad_decode(w, d) != (gbp_gba_keys)k) return 0;
    }
    memset(&s, 0, sizeof s);
    s.buttons = GBP_PAD_BUTTON_A | GBP_PAD_BUTTON_UP | GBP_PAD_BUTTON_L;
    if (gbp_input_map(&s, &GBP_INPUT_POLICY_DEFAULT) !=
        (GBP_GBA_KEY_BIT(GBP_GBA_A) | GBP_GBA_KEY_BIT(GBP_GBA_UP) | GBP_GBA_KEY_BIT(GBP_GBA_L)))
        return 0;
    s.buttons = GBP_PAD_BUTTON_LEFT | GBP_PAD_BUTTON_RIGHT | GBP_PAD_BUTTON_Z;
    if (gbp_input_map(&s, &GBP_INPUT_POLICY_DEFAULT) != 0) return 0;
    gbp_keypad_block(0x1234u, blk);
    if (blk[0x1E] != 0x12u || blk[0x1F] != 0x34u || blk[0] != 0x12u || blk[1] != 0x34u) return 0;
    return 1;
}
