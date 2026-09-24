/*
 * gbp_asplit.c — Run B's chunk assignment (GitHub Issue #105, §V24.7 (r6)). See gbp_asplit.h.
 */
#include "gbp_asplit.h"

void gbp_asplit_init(struct gbp_asplit *s)
{
    s->x = GBP_ASPLIT_SEED;
    s->n_words = 0u;
    s->chunks_half = s->chunks_full = 0u;
}

static uint32_t word_at(struct gbp_asplit *s, uint32_t w)
{
    if (w + 1u < s->n_words) {               /* asked for an earlier word: start again from the seed */
        s->x = GBP_ASPLIT_SEED;
        s->n_words = 0u;
    }
    while (s->n_words < w + 1u) {
        uint32_t x = s->x;
        x ^= x << 13;
        x ^= x >> 17;
        x ^= x << 5;
        s->x = x;
        s->n_words++;
    }
    return s->x;
}

int gbp_asplit_arm(struct gbp_asplit *s, uint32_t seq)
{
    const uint32_t j = seq >> 1;
    const int bit = (int)((word_at(s, j >> 5) >> (j & 31u)) & 1u);
    return (seq & 1u) ? 1 - bit : bit;
}

uint32_t gbp_asplit_step_pushes(void *user, uint32_t seq)
{
    struct gbp_asplit *s = (struct gbp_asplit *)user;
    if (gbp_asplit_arm(s, seq)) {
        s->chunks_half++;
        return GBP_ASPLIT_HALF_PUSHES;
    }
    s->chunks_full++;
    return GBP_ASPLIT_FULL_PUSHES;
}
