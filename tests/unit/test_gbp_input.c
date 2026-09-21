/*
 * test_gbp_input.c — the input path on the host (Issue #19).
 *
 * Every encoding test runs under ARBITRARY SYNTHETIC descriptors: it proves a
 * descriptor is applied bit for bit, never that the shipped assignment is the
 * physically right one. The shipped GBP_KEYPAD_DESCRIPTOR is only required to
 * be well-formed and to round-trip; no test here names the bit of L or R.
 * The write is asserted through the mock backend by address, length and
 * bytes, and through the replay backend by its script; the refresh policy is
 * exercised at its boundaries with a clock the test controls.
 */
#include <stdio.h>
#include <string.h>

#include "gbp_input.h"
#include "gbp_mock.h"
#include "gbp_replay.h"

static int fails, checks;
#define CHECK(c) do { checks++; if (!(c)) { fails++; printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

static const struct gbp_keypad_descriptor D_REVERSED = { { 15, 14, 13, 12, 11, 10, 9, 8, 7, 6 }, 1 };
static const struct gbp_keypad_descriptor D_SCRAMBLED = { { 3, 7, 1, 9, 0, 12, 5, 15, 11, 2 }, 1 };
static const struct gbp_keypad_descriptor D_ACTIVE_LOW = { { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9 }, 0 };
static const struct gbp_keypad_descriptor D_DUPLICATE = { { 0, 1, 2, 3, 4, 5, 6, 7, 8, 8 }, 1 };
static const struct gbp_keypad_descriptor D_OUT_OF_RANGE = { { 0, 1, 2, 3, 4, 5, 6, 7, 8, 16 }, 1 };
static const struct gbp_keypad_descriptor D_BAD_POLARITY = { { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9 }, 2 };

static struct gbp_pad_sample sample(uint16_t buttons)
{
    struct gbp_pad_sample s;
    memset(&s, 0, sizeof s);
    s.buttons = buttons;
    return s;
}

static void test_descriptors(void)
{
    const struct gbp_keypad_descriptor *valid[] = { &GBP_KEYPAD_DESCRIPTOR, &D_REVERSED, &D_SCRAMBLED, &D_ACTIVE_LOW };
    const struct gbp_keypad_descriptor *invalid[] = { &D_DUPLICATE, &D_OUT_OF_RANGE, &D_BAD_POLARITY };
    unsigned i, k;
    for (i = 0; i < sizeof valid / sizeof valid[0]; i++) {
        const struct gbp_keypad_descriptor *d = valid[i];
        const uint16_t mask = gbp_keypad_descriptor_mask(d);
        CHECK(gbp_keypad_descriptor_valid(d));
        /* the identity over every logical set, and no bit outside the mask */
        for (k = 0; k <= GBP_GBA_KEYS_MASK; k++) {
            const uint16_t w = gbp_keypad_encode((gbp_gba_keys)k, d);
            CHECK(gbp_keypad_decode(w, d) == (gbp_gba_keys)k);
            CHECK((w & (uint16_t)~mask) == 0u);
        }
        /* bit for bit: one key alone lands on its own position and nowhere else */
        for (k = 0; k < GBP_GBA_KEYS; k++) {
            const uint16_t w = gbp_keypad_encode(GBP_GBA_KEY_BIT(k), d);
            const uint16_t own = (uint16_t)(1u << d->bit[k]);
            if (d->pressed_is_one) CHECK(w == own);
            else CHECK(w == (uint16_t)(mask & (uint16_t)~own));
        }
        /* nothing pressed */
        CHECK(gbp_keypad_encode(0, d) == (d->pressed_is_one ? 0u : mask));
        /* everything pressed */
        CHECK(gbp_keypad_encode(GBP_GBA_KEYS_MASK, d) == (d->pressed_is_one ? mask : 0u));
    }
    for (i = 0; i < sizeof invalid / sizeof invalid[0]; i++) CHECK(!gbp_keypad_descriptor_valid(invalid[i]));
    CHECK(!gbp_keypad_descriptor_valid(0));
    /* the shipped table is well-formed and uses exactly ten bits; WHICH bits is not asserted here */
    CHECK(gbp_keypad_descriptor_valid(&GBP_KEYPAD_DESCRIPTOR));
    {
        unsigned n = 0;
        uint16_t m = gbp_keypad_descriptor_mask(&GBP_KEYPAD_DESCRIPTOR);
        while (m) { n += m & 1u; m = (uint16_t)(m >> 1); }
        CHECK(n == GBP_GBA_KEYS);
    }
    CHECK(gbp_input_selftest() == 1);
}

static void test_mapping_every_button(void)
{
    const struct gbp_input_policy *p = &GBP_INPUT_POLICY_DEFAULT;
    struct gbp_pad_sample s;
    /* every controller button under the default policy, one at a time */
    s = sample(GBP_PAD_BUTTON_A);     CHECK(gbp_input_map(&s, p) == GBP_GBA_KEY_BIT(GBP_GBA_A));
    s = sample(GBP_PAD_BUTTON_B);     CHECK(gbp_input_map(&s, p) == GBP_GBA_KEY_BIT(GBP_GBA_B));
    s = sample(GBP_PAD_BUTTON_X);     CHECK(gbp_input_map(&s, p) == GBP_GBA_KEY_BIT(GBP_GBA_SELECT));
    s = sample(GBP_PAD_BUTTON_Y);     CHECK(gbp_input_map(&s, p) == GBP_GBA_KEY_BIT(GBP_GBA_SELECT));
    s = sample(GBP_PAD_BUTTON_START); CHECK(gbp_input_map(&s, p) == GBP_GBA_KEY_BIT(GBP_GBA_START));
    s = sample(GBP_PAD_BUTTON_RIGHT); CHECK(gbp_input_map(&s, p) == GBP_GBA_KEY_BIT(GBP_GBA_RIGHT));
    s = sample(GBP_PAD_BUTTON_LEFT);  CHECK(gbp_input_map(&s, p) == GBP_GBA_KEY_BIT(GBP_GBA_LEFT));
    s = sample(GBP_PAD_BUTTON_UP);    CHECK(gbp_input_map(&s, p) == GBP_GBA_KEY_BIT(GBP_GBA_UP));
    s = sample(GBP_PAD_BUTTON_DOWN);  CHECK(gbp_input_map(&s, p) == GBP_GBA_KEY_BIT(GBP_GBA_DOWN));
    s = sample(GBP_PAD_BUTTON_L);     CHECK(gbp_input_map(&s, p) == GBP_GBA_KEY_BIT(GBP_GBA_L));
    s = sample(GBP_PAD_BUTTON_R);     CHECK(gbp_input_map(&s, p) == GBP_GBA_KEY_BIT(GBP_GBA_R));
    s = sample(GBP_PAD_BUTTON_Z);     CHECK(gbp_input_map(&s, p) == 0);              /* reserved for the runtime */
    s = sample(0);                    CHECK(gbp_input_map(&s, p) == 0);
    /* combinations are the OR of their parts */
    s = sample(GBP_PAD_BUTTON_A | GBP_PAD_BUTTON_B | GBP_PAD_BUTTON_START | GBP_PAD_BUTTON_L | GBP_PAD_BUTTON_R);
    CHECK(gbp_input_map(&s, p) == (GBP_GBA_KEY_BIT(GBP_GBA_A) | GBP_GBA_KEY_BIT(GBP_GBA_B) | GBP_GBA_KEY_BIT(GBP_GBA_START) |
                                   GBP_GBA_KEY_BIT(GBP_GBA_L) | GBP_GBA_KEY_BIT(GBP_GBA_R)));
    /* every bit the controller can set, at once: the ten keys, opposites filtered */
    s = sample(0xFFFFu);
    CHECK(gbp_input_map(&s, p) == (GBP_GBA_KEYS_MASK & (gbp_gba_keys)~(GBP_GBA_KEY_BIT(GBP_GBA_UP) | GBP_GBA_KEY_BIT(GBP_GBA_DOWN) |
                                                                      GBP_GBA_KEY_BIT(GBP_GBA_LEFT) | GBP_GBA_KEY_BIT(GBP_GBA_RIGHT))));
    /* an invalid sample releases everything, whatever the bits say */
    s = sample(0xFFFFu); s.err = GBP_PAD_ERR_NO_CONTROLLER; CHECK(gbp_input_map(&s, p) == 0);
    s = sample(GBP_PAD_BUTTON_A); s.err = -2; CHECK(gbp_input_map(&s, p) == 0);
    /* the policy is DATA: a synthetic table follows the table, not the code */
    {
        struct gbp_input_policy q;
        memset(&q, 0, sizeof q);
        q.button_mask[GBP_GBA_SELECT] = GBP_PAD_BUTTON_Z;     /* GBI's choice */
        q.button_mask[GBP_GBA_L] = GBP_PAD_BUTTON_Y;          /* the Disc's alternate mode */
        q.button_mask[GBP_GBA_R] = GBP_PAD_BUTTON_X;
        s = sample(GBP_PAD_BUTTON_Z); CHECK(gbp_input_map(&s, &q) == GBP_GBA_KEY_BIT(GBP_GBA_SELECT));
        s = sample(GBP_PAD_BUTTON_Y); CHECK(gbp_input_map(&s, &q) == GBP_GBA_KEY_BIT(GBP_GBA_L));
        s = sample(GBP_PAD_BUTTON_X); CHECK(gbp_input_map(&s, &q) == GBP_GBA_KEY_BIT(GBP_GBA_R));
        s = sample(GBP_PAD_BUTTON_A); CHECK(gbp_input_map(&s, &q) == 0);
    }
}

static void test_thresholds_at_the_boundary(void)
{
    struct gbp_input_policy p = GBP_INPUT_POLICY_DEFAULT;
    struct gbp_pad_sample s;
    const int t = p.stick_threshold;
    CHECK(t == GBP_INPUT_POLICY_STICK_THRESHOLD && t > 0);
    /* the stick: strictly beyond the threshold, on both axes and both signs */
    s = sample(0); s.stick_x = (int8_t)t;        CHECK(gbp_input_map(&s, &p) == 0);
    s = sample(0); s.stick_x = (int8_t)(t + 1);  CHECK(gbp_input_map(&s, &p) == GBP_GBA_KEY_BIT(GBP_GBA_RIGHT));
    s = sample(0); s.stick_x = (int8_t)-t;       CHECK(gbp_input_map(&s, &p) == 0);
    s = sample(0); s.stick_x = (int8_t)(-t - 1); CHECK(gbp_input_map(&s, &p) == GBP_GBA_KEY_BIT(GBP_GBA_LEFT));
    s = sample(0); s.stick_y = (int8_t)t;        CHECK(gbp_input_map(&s, &p) == 0);
    s = sample(0); s.stick_y = (int8_t)(t + 1);  CHECK(gbp_input_map(&s, &p) == GBP_GBA_KEY_BIT(GBP_GBA_UP));
    s = sample(0); s.stick_y = (int8_t)-t;       CHECK(gbp_input_map(&s, &p) == 0);
    s = sample(0); s.stick_y = (int8_t)(-t - 1); CHECK(gbp_input_map(&s, &p) == GBP_GBA_KEY_BIT(GBP_GBA_DOWN));
    s = sample(0); s.stick_x = 127; s.stick_y = -128;
    CHECK(gbp_input_map(&s, &p) == (GBP_GBA_KEY_BIT(GBP_GBA_RIGHT) | GBP_GBA_KEY_BIT(GBP_GBA_DOWN)));
    /* the C-stick is never read */
    s = sample(0); s.substick_x = 127; s.substick_y = -128; CHECK(gbp_input_map(&s, &p) == 0);
    /* threshold 0 = the stick is not read at all */
    p.stick_threshold = 0;
    s = sample(0); s.stick_x = 127; s.stick_y = 127; CHECK(gbp_input_map(&s, &p) == 0);
    /* a different threshold is just data */
    p.stick_threshold = 100;
    s = sample(0); s.stick_x = 100; CHECK(gbp_input_map(&s, &p) == 0);
    s = sample(0); s.stick_x = 101; CHECK(gbp_input_map(&s, &p) == GBP_GBA_KEY_BIT(GBP_GBA_RIGHT));
    /* the analogue triggers: off by default, strictly above the threshold when on */
    p = GBP_INPUT_POLICY_DEFAULT;
    CHECK(p.trigger_threshold == 0);
    s = sample(0); s.trigger_l = 255; s.trigger_r = 255; CHECK(gbp_input_map(&s, &p) == 0);
    p.trigger_threshold = 100;
    s = sample(0); s.trigger_l = 100; CHECK(gbp_input_map(&s, &p) == 0);
    s = sample(0); s.trigger_l = 101; CHECK(gbp_input_map(&s, &p) == GBP_GBA_KEY_BIT(GBP_GBA_L));
    s = sample(0); s.trigger_r = 100; CHECK(gbp_input_map(&s, &p) == 0);
    s = sample(0); s.trigger_r = 101; CHECK(gbp_input_map(&s, &p) == GBP_GBA_KEY_BIT(GBP_GBA_R));
    s = sample(GBP_PAD_BUTTON_L); s.trigger_r = 255;
    CHECK(gbp_input_map(&s, &p) == (GBP_GBA_KEY_BIT(GBP_GBA_L) | GBP_GBA_KEY_BIT(GBP_GBA_R)));
    /* analogue A / B: off by default, strictly above the threshold when on */
    p = GBP_INPUT_POLICY_DEFAULT;
    CHECK(p.analog_ab_threshold == 0);
    s = sample(0); s.analog_a = 255; s.analog_b = 255; CHECK(gbp_input_map(&s, &p) == 0);
    p.analog_ab_threshold = 100;
    s = sample(0); s.analog_a = 100; CHECK(gbp_input_map(&s, &p) == 0);
    s = sample(0); s.analog_a = 101; CHECK(gbp_input_map(&s, &p) == GBP_GBA_KEY_BIT(GBP_GBA_A));
    s = sample(0); s.analog_b = 101; CHECK(gbp_input_map(&s, &p) == GBP_GBA_KEY_BIT(GBP_GBA_B));
}

static void test_opposite_directions(void)
{
    struct gbp_input_policy p = GBP_INPUT_POLICY_DEFAULT;
    struct gbp_pad_sample s;
    CHECK(p.filter_opposites == 1);
    s = sample(GBP_PAD_BUTTON_LEFT | GBP_PAD_BUTTON_RIGHT); CHECK(gbp_input_map(&s, &p) == 0);
    s = sample(GBP_PAD_BUTTON_UP | GBP_PAD_BUTTON_DOWN);    CHECK(gbp_input_map(&s, &p) == 0);
    /* a stick against the D-pad is an opposite pair too */
    s = sample(GBP_PAD_BUTTON_LEFT); s.stick_x = 127;        CHECK(gbp_input_map(&s, &p) == 0);
    s = sample(GBP_PAD_BUTTON_DOWN); s.stick_y = 127;        CHECK(gbp_input_map(&s, &p) == 0);
    /* only the pair is cleared; the other axis and the buttons survive */
    s = sample(GBP_PAD_BUTTON_LEFT | GBP_PAD_BUTTON_RIGHT | GBP_PAD_BUTTON_UP | GBP_PAD_BUTTON_A);
    CHECK(gbp_input_map(&s, &p) == (GBP_GBA_KEY_BIT(GBP_GBA_UP) | GBP_GBA_KEY_BIT(GBP_GBA_A)));
    /* a stick and the D-pad agreeing is one press */
    s = sample(GBP_PAD_BUTTON_RIGHT); s.stick_x = 127;       CHECK(gbp_input_map(&s, &p) == GBP_GBA_KEY_BIT(GBP_GBA_RIGHT));
    /* the filter is policy: off, both go through */
    p.filter_opposites = 0;
    s = sample(GBP_PAD_BUTTON_LEFT | GBP_PAD_BUTTON_RIGHT);
    CHECK(gbp_input_map(&s, &p) == (GBP_GBA_KEY_BIT(GBP_GBA_LEFT) | GBP_GBA_KEY_BIT(GBP_GBA_RIGHT)));
}

static void test_block_layout(void)
{
    uint8_t blk[GBP_BLOCK_SIZE];
    unsigned i;
    gbp_keypad_block(0xABCDu, blk);
    for (i = 0; i < GBP_BLOCK_SIZE; i += 2u) { CHECK(blk[i] == 0xABu); CHECK(blk[i + 1u] == 0xCDu); }
    CHECK(blk[0x1E] == 0xABu && blk[0x1F] == 0xCDu);
    gbp_keypad_block(0x0000u, blk);
    for (i = 0; i < GBP_BLOCK_SIZE; i++) CHECK(blk[i] == 0u);
    CHECK(gbp_keypad_addr(0x01000000u) == 0x01C00000u);
    CHECK(gbp_keypad_addr(0x00200000u) == 0x00E00000u);
    CHECK(gbp_keypad_addr(0) == 0x00C00000u);
}

static uint32_t mock_base(struct gbp_mock *m)
{
    uint32_t base = gbp_internal_size_from_arinfo(m->arinfo);
    if (!base) { m->arinfo = 0x0003u; base = gbp_internal_size_from_arinfo(m->arinfo); }
    return base;
}

static void test_write_through_the_mock(void)
{
    struct gbp_mock m;
    struct gbp_transport t;
    struct gbp_keypad_write_result r;
    uint8_t expect[GBP_BLOCK_SIZE];
    uint32_t base;
    int op;
    gbp_mock_init(&m);
    m.present = 1;
    gbp_mock_transport(&m, &t);
    base = mock_base(&m);
    CHECK(base != 0);

    gbp_keypad_write(&t, base, 0x0123u, &r);
    CHECK(r.attempted == 1 && r.completed == 1 && r.rc == GBP_OK);
    CHECK(r.addr == base + 0x00C00000u);
    gbp_keypad_block(0x0123u, expect);
    CHECK(memcmp(r.raw, expect, GBP_BLOCK_SIZE) == 0);
    op = gbp_mock_first_op(&m, MOCK_WR, base, 0xC);
    CHECK(op >= 0);
    if (op >= 0) {
        CHECK(m.ops[op].addr == base + 0x00C00000u);
        CHECK(memcmp(m.ops[op].data, expect, GBP_BLOCK_SIZE) == 0);
        CHECK(m.ops[op].rc == GBP_OK);
    }
    CHECK(gbp_mock_count_block_ops(&m, MOCK_WR, base, 0xC) == 1u);
    CHECK(gbp_mock_writes_outside(&m, base, 0xC) == 0u);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_RD, base, 16) == 0u);   /* the write reads nothing */

    /* a failing transfer: attempted, not completed, rc reported */
    m.fail_at_op = m.transfers + 1u;
    m.fail_rc = GBP_ERR_TIMEOUT;
    gbp_keypad_write(&t, base, 0x0001u, &r);
    CHECK(r.attempted == 1 && r.completed == 0 && r.rc == GBP_ERR_TIMEOUT);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_WR, base, 0xC) == 2u);
}

/* the mock's ticks64 advances by 10 per call; the test moves the clock itself */
static void test_step_policy_through_the_mock(void)
{
    struct gbp_mock m;
    struct gbp_transport t;
    struct gbp_input in;
    struct gbp_pad_sample s;
    uint32_t base;
    const uint32_t tb_hz = 40500000u;
    const uint64_t period = (uint64_t)tb_hz * GBP_INPUT_REFRESH_MS / 1000u;
    uint8_t expect[GBP_BLOCK_SIZE];
    int op;

    gbp_mock_init(&m);
    m.present = 1;
    gbp_mock_transport(&m, &t);
    base = mock_base(&m);

    gbp_input_init(&in, &GBP_INPUT_POLICY_DEFAULT, &GBP_KEYPAD_DESCRIPTOR, tb_hz);
    CHECK(in.refresh_ticks == 202500u && in.refresh_ticks == period);
    CHECK(in.base == 0 && in.written == 0 && in.steps == 0);

    /* no base yet: mapped and counted, nothing written */
    s = sample(GBP_PAD_BUTTON_A);
    CHECK(gbp_input_step(&in, &t, &s, 1000u) == GBP_INPUT_NONE);
    CHECK(in.steps == 1 && in.skipped_no_base == 1 && in.attempts == 0);
    CHECK(in.keys_last == GBP_GBA_KEY_BIT(GBP_GBA_A) && in.keys_changes == 1);
    CHECK(in.word_last == gbp_keypad_encode(GBP_GBA_KEY_BIT(GBP_GBA_A), &GBP_KEYPAD_DESCRIPTOR));
    CHECK(in.t_poll == 1000u);
    CHECK(gbp_mock_count_block_ops(&m, MOCK_WR, base, 0xC) == 0u);

    /* the first step with a base always writes, whatever the word */
    gbp_input_set_base(&in, base);
    s = sample(0);
    CHECK(gbp_input_step(&in, &t, &s, 2000u) == GBP_INPUT_WRITE_FIRST);
    CHECK(in.written == 1 && in.writes_first == 1 && in.writes_completed == 1 && in.attempts == 1);
    CHECK(in.word_written == gbp_keypad_encode(0, &GBP_KEYPAD_DESCRIPTOR));
    CHECK(in.t_poll == 2000u);                                   /* the caller's instant, kept verbatim */
    CHECK(in.t_write == m.tick64_origin + m.tick64);            /* the transport's instant after the DMA */
    CHECK(in.t_write == in.t_last_write);
    op = gbp_mock_first_op(&m, MOCK_WR, base, 0xC);
    CHECK(op >= 0);
    gbp_keypad_block(gbp_keypad_encode(0, &GBP_KEYPAD_DESCRIPTOR), expect);
    if (op >= 0) CHECK(memcmp(m.ops[op].data, expect, GBP_BLOCK_SIZE) == 0);

    /* the same word inside the period: nothing */
    CHECK(gbp_input_step(&in, &t, &s, 2100u) == GBP_INPUT_NONE);
    CHECK(gbp_input_step(&in, &t, &s, 2200u) == GBP_INPUT_NONE);
    CHECK(in.attempts == 1 && gbp_mock_count_block_ops(&m, MOCK_WR, base, 0xC) == 1u);

    /* a change: written at once, the bytes are the new word's */
    s = sample(GBP_PAD_BUTTON_B | GBP_PAD_BUTTON_UP);
    CHECK(gbp_input_step(&in, &t, &s, 2300u) == GBP_INPUT_WRITE_CHANGE);
    CHECK(in.writes_change == 1 && in.writes_completed == 2);
    CHECK(in.word_written == gbp_keypad_encode(GBP_GBA_KEY_BIT(GBP_GBA_B) | GBP_GBA_KEY_BIT(GBP_GBA_UP), &GBP_KEYPAD_DESCRIPTOR));
    op = gbp_mock_last_op(&m, MOCK_WR, base, 0xC);
    gbp_keypad_block(in.word_written, expect);
    if (op >= 0) CHECK(memcmp(m.ops[op].data, expect, GBP_BLOCK_SIZE) == 0);

    /* the refresh boundary: one tick short of the period is nothing, the period itself is a refresh */
    {
        const uint64_t t0 = in.t_last_write;
        /* the mock's clock is at t0 (ticks64 advanced by 10 when t_write was read); steps advance it by 10 each */
        while (m.tick64_origin + m.tick64 + 10u < t0 + period - 10u) m.tick64 += 10u;
        /* now the next ticks64 read returns t0 + period - 10 .. t0 + period - 1: below the boundary */
        CHECK(gbp_input_step(&in, &t, &s, 3000u) == GBP_INPUT_NONE);
        CHECK(m.tick64_origin + m.tick64 < t0 + period);
        m.tick64 = t0 + period - 10u - m.tick64_origin;          /* the next read lands exactly on t0 + period */
        CHECK(gbp_input_step(&in, &t, &s, 3100u) == GBP_INPUT_WRITE_REFRESH);
        CHECK(in.writes_refresh == 1 && in.writes_completed == 3);
        CHECK(in.t_last_write >= t0 + period);
    }
    CHECK(gbp_mock_count_block_ops(&m, MOCK_WR, base, 0xC) == 3u);

    /* a failure: counted, the state keeps the last ACCEPTED word, and the retry waits one period */
    m.fail_at_op = m.transfers + 1u;
    m.fail_rc = GBP_ERR_BUSY;
    s = sample(GBP_PAD_BUTTON_A);
    CHECK(gbp_input_step(&in, &t, &s, 4000u) == GBP_INPUT_WRITE_CHANGE);
    CHECK(in.writes_failed == 1 && in.last_failed == 1 && in.last_rc == GBP_ERR_BUSY);
    CHECK(in.word_written == gbp_keypad_encode(GBP_GBA_KEY_BIT(GBP_GBA_B) | GBP_GBA_KEY_BIT(GBP_GBA_UP), &GBP_KEYPAD_DESCRIPTOR));
    CHECK(in.last_write.attempted == 1 && in.last_write.completed == 0);
    CHECK(gbp_input_step(&in, &t, &s, 4100u) == GBP_INPUT_NONE);          /* back-off */
    CHECK(in.attempts == 4);
    m.tick64 += period;
    CHECK(gbp_input_step(&in, &t, &s, 4200u) == GBP_INPUT_WRITE_RETRY);
    CHECK(in.writes_retry == 1 && in.last_failed == 0 && in.writes_completed == 4);
    CHECK(in.word_written == gbp_keypad_encode(GBP_GBA_KEY_BIT(GBP_GBA_A), &GBP_KEYPAD_DESCRIPTOR));

    /* an invalid sample releases every key: a change to word "nothing pressed" */
    s = sample(GBP_PAD_BUTTON_A); s.err = GBP_PAD_ERR_NO_CONTROLLER;
    CHECK(gbp_input_step(&in, &t, &s, 5000u) == GBP_INPUT_WRITE_CHANGE);
    CHECK(in.samples_invalid == 1 && in.word_written == gbp_keypad_encode(0, &GBP_KEYPAD_DESCRIPTOR));

    /* aggregates */
    CHECK(in.write_ticks_n == in.writes_completed);
    gbp_input_note_step_ticks(&in, 30u);
    gbp_input_note_step_ticks(&in, 10u);
    gbp_input_note_step_ticks(&in, 20u);
    CHECK(in.step_ticks_min == 10u && in.step_ticks_max == 30u && in.step_ticks_n == 3u && gbp_input_step_ticks_mean(&in) == 20u);
    CHECK(gbp_mock_writes_outside(&m, base, 0xC) == 0u);
    CHECK(m.violations == 0u);
    /* the pure decision agrees with what the step did, from the state alone */
    CHECK(gbp_input_decide(&in, in.word_written, in.t_last_write) == GBP_INPUT_NONE);
    CHECK(gbp_input_decide(&in, (uint16_t)(in.word_written ^ 1u), in.t_last_write) == GBP_INPUT_WRITE_CHANGE);
    CHECK(gbp_input_decide(&in, in.word_written, in.t_last_write + period) == GBP_INPUT_WRITE_REFRESH);
    CHECK(gbp_input_decide(&in, in.word_written, in.t_last_write + period - 1u) == GBP_INPUT_NONE);
    /* names, for the report */
    CHECK(strcmp(gbp_input_action_name(GBP_INPUT_WRITE_REFRESH), "refresh") == 0);
    CHECK(strcmp(gbp_input_action_name(GBP_INPUT_NONE), "none") == 0);
}

static void test_zero_timebase_refreshes_every_step(void)
{
    struct gbp_mock m;
    struct gbp_transport t;
    struct gbp_input in;
    struct gbp_pad_sample s = sample(0);
    gbp_mock_init(&m);
    m.present = 1;
    gbp_mock_transport(&m, &t);
    gbp_input_init(&in, &GBP_INPUT_POLICY_DEFAULT, &GBP_KEYPAD_DESCRIPTOR, 0u);
    gbp_input_set_base(&in, mock_base(&m));
    CHECK(in.refresh_ticks == 0u);
    CHECK(gbp_input_step(&in, &t, &s, 0u) == GBP_INPUT_WRITE_FIRST);
    CHECK(gbp_input_step(&in, &t, &s, 0u) == GBP_INPUT_WRITE_REFRESH);
    CHECK(gbp_input_step(&in, &t, &s, 0u) == GBP_INPUT_WRITE_REFRESH);
}

/* the replay backend has no ticks64: `now` is the caller's t_poll */
static void test_step_through_the_replay(void)
{
    struct gbp_replay r;
    struct gbp_transport t;
    struct gbp_input in;
    struct gbp_pad_sample s = sample(GBP_PAD_BUTTON_START);
    const uint32_t base = 0x01000000u;
    const uint64_t period = 202500u;
    static const char script[] =
        "# two KEYPAD writes at base + 0xC00000, then the script ends\n"
        "W 01c00000 ok\n"
        "W 01c00000 ok\n";
    gbp_replay_init(&r, script);
    gbp_replay_transport(&r, &t);
    CHECK(t.ticks64 == 0);
    gbp_input_init(&in, &GBP_INPUT_POLICY_DEFAULT, &GBP_KEYPAD_DESCRIPTOR, 40500000u);
    gbp_input_set_base(&in, base);
    CHECK(gbp_input_step(&in, &t, &s, 0u) == GBP_INPUT_WRITE_FIRST);
    CHECK(in.writes_completed == 1 && in.t_write == 0u && in.t_last_write == 0u);
    CHECK(gbp_input_step(&in, &t, &s, period - 1u) == GBP_INPUT_NONE);
    CHECK(gbp_input_step(&in, &t, &s, period) == GBP_INPUT_WRITE_REFRESH);
    CHECK(in.writes_completed == 2 && in.t_write == period);
    CHECK(r.step == 2 && r.mismatches == 0 && r.exhausted == 0);
    /* the script is exhausted: the third write is attempted and not completed */
    CHECK(gbp_input_step(&in, &t, &s, 2u * period) == GBP_INPUT_WRITE_REFRESH);
    CHECK(in.writes_failed == 1 && in.last_rc == GBP_ERR_BACKEND && r.exhausted == 1);
    CHECK(in.last_write.attempted == 1 && in.last_write.completed == 0);
    /* a script that expects another address: the write is a mismatch, and fails */
    {
        static const char wrong[] = "W 01d00000 ok\n";
        gbp_replay_init(&r, wrong);
        gbp_replay_transport(&r, &t);
        gbp_input_init(&in, &GBP_INPUT_POLICY_DEFAULT, &GBP_KEYPAD_DESCRIPTOR, 40500000u);
        gbp_input_set_base(&in, base);
        CHECK(gbp_input_step(&in, &t, &s, 0u) == GBP_INPUT_WRITE_FIRST);
        CHECK(in.writes_failed == 1 && r.mismatches == 1);
    }
}

int main(void)
{
    test_descriptors();
    test_mapping_every_button();
    test_thresholds_at_the_boundary();
    test_opposite_directions();
    test_block_layout();
    test_write_through_the_mock();
    test_step_policy_through_the_mock();
    test_zero_timebase_refreshes_every_step();
    test_step_through_the_replay();
    printf("test_gbp_input: %d checks, %d failures\n", checks, fails);
    return fails ? 1 : 0;
}
