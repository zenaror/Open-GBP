/*
 * gbp_alive — see gbp_alive.h.
 */
#include "gbp_alive.h"

#include <string.h>

#define PREV_NONE ((int32_t)-2147483647 - 1)

void gbp_alive_period_reset(struct gbp_alive_period *p, uint32_t expected)
{
    if (!p) return;
    memset(p, 0, sizeof *p);
    p->expected = expected;
    p->prev = PREV_NONE;
}

void gbp_alive_period_feed(struct gbp_alive_period *p, int16_t s)
{
    if (!p) return;
    if (p->prev != PREV_NONE && p->prev <= 0 && (int32_t)s > 0) {    /* prev <= rest < cur */
        if (p->have_edge) {
            const uint32_t per = p->samples - p->last_edge;
            if (p->periods == 0u || per < p->pmin) p->pmin = per;
            if (per > p->pmax) p->pmax = per;
            if (per != p->expected) p->off++;
            p->periods++;
        }
        p->last_edge = p->samples;
        p->have_edge = 1u;
        p->edges++;
    }
    p->prev = (int32_t)s;
    p->samples++;
}

void gbp_alive_init(struct gbp_alive *a, uint32_t tb_hz)
{
    if (!a) return;
    memset(a, 0, sizeof *a);
    a->phase = GBP_ALIVE_CALIBRATE;
    a->tb_hz = tb_hz;
    gbp_alive_period_reset(&a->l, GBP_ALIVE_PERIOD);
}

void gbp_alive_start(struct gbp_alive *a, uint64_t t0)
{
    if (!a || a->t0) return;
    a->t0 = t0;
    a->t_calib = t0 + (uint64_t)GBP_ALIVE_CALIB_FROM_S * a->tb_hz;
    a->t_accept = t0 + (uint64_t)GBP_ALIVE_ACCEPT_S * a->tb_hz;
}

int gbp_alive_block(struct gbp_alive *a, uint64_t t_done, uint32_t ring_fill)
{
    if (!a || a->tb_hz == 0u || !a->t0) return GBP_ALIVE_DO_NOTHING;
    a->blocks_in++;
    switch (a->phase) {
    case GBP_ALIVE_CALIBRATE:
        if (t_done < a->t_calib) return GBP_ALIVE_DO_NOTHING;
        a->calib_blocks++;
        if (a->calib_blocks >= GBP_ALIVE_CALIB_BLOCKS) {
            /* an A that came before the prompt still starts the tone: go straight to the
             * control, and say so -- the span may have seen the tone begin */
            a->phase = a->presses_a ? GBP_ALIVE_CONTROL : GBP_ALIVE_PROMPT;
            if (a->presses_a) a->press_before_prompt = 1u;
        }
        return GBP_ALIVE_DO_CALIBRATE;
    case GBP_ALIVE_PROMPT:
        return GBP_ALIVE_DO_NOTHING;
    case GBP_ALIVE_CONTROL:
        return GBP_ALIVE_DO_CONTROL;
    case GBP_ALIVE_WINDOW: {
        uint64_t s;
        if (t_done < a->t_origin) return GBP_ALIVE_DO_NOTHING;   /* cannot happen: the origin is a block's own tick */
        if (t_done >= a->t_end) {
            a->phase = GBP_ALIVE_DONE;
            return GBP_ALIVE_DO_NOTHING;
        }
        s = (t_done - a->t_origin) / (uint64_t)a->tb_hz;
        if (s >= (uint64_t)GBP_ALIVE_MAX_SECONDS) {
            a->sec_overflow++;                                    /* counted, never silent */
            return GBP_ALIVE_DO_DECODE;
        }
        while (a->secs_used <= (uint32_t)s) {                     /* a window begins: its fill, as it begins */
            a->fill[a->secs_used] = ring_fill;
            a->secs_used++;
        }
        a->sec[(uint32_t)s]++;
        a->window_blocks++;
        return GBP_ALIVE_DO_DECODE;
    }
    default:
        return GBP_ALIVE_DO_NOTHING;
    }
}

void gbp_alive_control_window(struct gbp_alive *a, uint64_t t_done, int pass, uint32_t periods,
                              uint32_t pmin, uint32_t pmax, uint32_t blocks)
{
    if (!a || a->phase != GBP_ALIVE_CONTROL) return;
    a->control_windows++;
    a->control_periods = periods;
    a->control_pmin = pmin;
    a->control_pmax = pmax;
    a->control_blocks = blocks;
    if (pass && t_done < a->t_accept) {
        a->control_early++;                                       /* A4.5: does not count */
    } else if (pass) {
        a->control_passes++;
        a->control_ok = 1u;
        a->t_origin = t_done;                                     /* §V22.1: the ORIGIN */
        a->t_end = t_done + (uint64_t)GBP_ALIVE_WINDOW_S * a->tb_hz;
        a->phase = GBP_ALIVE_WINDOW;
    } else if (t_done >= a->t_press &&
               t_done - a->t_press >= (uint64_t)GBP_ALIVE_CONTROL_BOUND_S * a->tb_hz) {
        a->control_gave_up = 1u;                                  /* A4.7: bounded, and INCONCLUSIVE */
        a->phase = GBP_ALIVE_GAVE_UP;
        a->t_end = t_done;
    }
}

void gbp_alive_decoded(struct gbp_alive *a, int16_t sample)
{
    if (!a || a->phase != GBP_ALIVE_WINDOW) return;
    gbp_alive_period_feed(&a->l, sample);
    a->l_samples++;
}

void gbp_alive_buttons(struct gbp_alive *a, uint64_t t, uint16_t buttons)
{
    uint16_t rising;
    if (!a) return;
    buttons = (uint16_t)(buttons & GBP_ALIVE_PAD_BUTTONS);
    if (!a->have_buttons) {                                       /* the first sample opens the record */
        a->have_buttons = 1u;
        a->prev_buttons = 0u;
    }
    rising = (uint16_t)(buttons & (uint16_t)~a->prev_buttons);
    a->prev_buttons = buttons;
    if (!rising) return;
    if (a->phase == GBP_ALIVE_DONE || a->phase == GBP_ALIVE_GAVE_UP) {
        a->presses_after++;
        return;
    }
    if (rising & GBP_ALIVE_PAD_A) {
        a->presses_a++;
        if (a->presses_a == 1u) {
            a->t_first_a = t;
            a->t_press = t;
        }
        rising = (uint16_t)(rising & (uint16_t)~GBP_ALIVE_PAD_A);
    }
    {
        uint16_t r = rising;
        while (r) {                                               /* each other button counts once */
            a->presses_other++;
            r = (uint16_t)(r & (uint16_t)(r - 1u));
        }
    }
    if (a->phase == GBP_ALIVE_PROMPT && a->presses_a == 1u && a->t_first_a == t)
        a->phase = GBP_ALIVE_CONTROL;
}

int gbp_alive_finished(const struct gbp_alive *a)
{
    return (a && (a->phase == GBP_ALIVE_DONE || a->phase == GBP_ALIVE_GAVE_UP)) ? 1 : 0;
}

const char *gbp_alive_phase_name(enum gbp_alive_phase p)
{
    switch (p) {
    case GBP_ALIVE_CALIBRATE: return "calibrate";
    case GBP_ALIVE_PROMPT: return "prompt";
    case GBP_ALIVE_CONTROL: return "control";
    case GBP_ALIVE_WINDOW: return "window";
    case GBP_ALIVE_DONE: return "done";
    case GBP_ALIVE_GAVE_UP: return "gave_up";
    default: return "?";
    }
}
