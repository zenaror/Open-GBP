/*
 * gbp_asplit — Run B's chunk assignment (GitHub Issue #105; HARDWARE_TESTS §V24, §V24.7 (r6)).
 *
 * Each AI chunk is produced in FULL steps (16 pushes a call) or HALF steps (8), pair-balanced: chunks
 * 2j and 2j+1 take opposite arms, and which comes first is bit j of xorshift32 seeded 0x9E3779B9
 * (x ^= x << 13; x ^= x >> 17; x ^= x << 5). Bit j is bit (j mod 32) of the (j div 32 + 1)-th output
 * word; bit 1 puts chunk 2j in the HALF arm. tools/v24accept.py regenerates the same sequence and
 * refuses a run whose recorded arms disagree with it.
 *
 * gbp_asplit_step_pushes() is the gbp_aplay step-size hook: it is asked once per chunk, at the chunk's
 * start, with the chunk's production sequence number, and counts what it handed out. No allocation, no
 * device, no I/O; tests/unit/test_gbp_asplit.c exercises it with no hardware.
 */
#ifndef OPENGBP_GBP_ASPLIT_H
#define OPENGBP_GBP_ASPLIT_H

#include <stdint.h>

#define GBP_ASPLIT_SEED         0x9E3779B9u
#define GBP_ASPLIT_HALF_PUSHES  8u
#define GBP_ASPLIT_FULL_PUSHES  16u

struct gbp_asplit {
    uint32_t x;                  /* the last word generated */
    uint32_t n_words;            /* how many have been generated */
    uint32_t chunks_half, chunks_full;
};

void gbp_asplit_init(struct gbp_asplit *s);
/* 1 = HALF, 0 = FULL, for chunk `seq` (any order; sequential use is O(1)) */
int gbp_asplit_arm(struct gbp_asplit *s, uint32_t seq);
/* the gbp_aplay hook: `user` is a struct gbp_asplit */
uint32_t gbp_asplit_step_pushes(void *user, uint32_t seq);

#endif
