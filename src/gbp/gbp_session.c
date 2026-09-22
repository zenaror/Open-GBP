#include "gbp_session.h"

void gbp_session_init(struct gbp_session *s, uint64_t hold_ticks)
{
    /* field by field, on purpose: this object has no outward edge, not even memset */
    s->hold_ticks = hold_ticks;
    s->t_hold_begin = 0u;
    s->t_requested = 0u;
    s->holding = 0;
    s->end_requested = 0;
    s->samples = 0u;
    s->samples_held = 0u;
    s->holds_begun = 0u;
    s->holds_released = 0u;
    s->samples_after = 0u;
}

int gbp_session_sample(struct gbp_session *s, int held, uint64_t now)
{
    s->samples++;
    if (s->end_requested) { s->samples_after++; return 0; }
    if (!held) {
        if (s->holding) { s->holding = 0; s->holds_released++; }
        return 0;
    }
    s->samples_held++;
    if (!s->holding) {
        s->holding = 1;
        s->holds_begun++;
        s->t_hold_begin = now;
    }
    if (now - s->t_hold_begin >= s->hold_ticks) {
        s->end_requested = 1;
        s->t_requested = now;
        return 1;
    }
    return 0;
}
