/*
 * test_gbp_asplit.c — Run B's chunk assignment (GitHub Issue #105, §V24.7 (r6)), with no hardware.
 *
 * Pinned: xorshift32 from 0x9E3779B9 is the textbook one; the assignment is pair-balanced and its first
 * sixteen arms are the ones tools/v24accept.py regenerates; random access agrees with sequential use;
 * and the gbp_aplay hook hands out 8 pushes for HALF and 16 for FULL, counting each.
 */
#include <stdio.h>
#include "gbp_asplit.h"

static int checks, failures;
#define CHECK(c) do { checks++; if (!(c)) { failures++; printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)

int main(void)
{
    struct gbp_asplit s, r;
    static const int first16[16] = { 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 0, 1 };
    static int seq_arm[4000];
    uint32_t i, half = 0u;
    uint32_t x = GBP_ASPLIT_SEED;
    printf("-- the assignment: textbook xorshift32, pair-balanced, the host's sequence\n");
    gbp_asplit_init(&s);
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    (void)gbp_asplit_arm(&s, 0u);
    CHECK(s.x == x && s.n_words == 1u);
    for (i = 0; i < 16u; i++) CHECK(gbp_asplit_arm(&s, i) == first16[i]);
    for (i = 0; i < 4000u; i++) { seq_arm[i] = gbp_asplit_arm(&s, i); half += (uint32_t)seq_arm[i]; }
    CHECK(half == 2000u);
    for (i = 0; i < 4000u; i += 2u) CHECK(seq_arm[i] != seq_arm[i + 1u]);
    gbp_asplit_init(&r);
    for (i = 3999u; i < 4000u; i -= 7u) CHECK(gbp_asplit_arm(&r, i) == seq_arm[i]);   /* backwards: random access */
    printf("-- the hook: 8 for HALF, 16 for FULL, counted\n");
    gbp_asplit_init(&r);
    for (i = 0; i < 100u; i++)
        CHECK(gbp_asplit_step_pushes(&r, i) == (seq_arm[i] ? GBP_ASPLIT_HALF_PUSHES : GBP_ASPLIT_FULL_PUSHES));
    CHECK(r.chunks_half == 50u && r.chunks_full == 50u);
    printf("test_gbp_asplit: %d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
