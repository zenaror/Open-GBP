/*
 * tests/unit/v28_ahead.h — force-included into the PROBE copies of gbp_aplay.c and gbp_atrans.c that
 * test_v28_ahead_steps builds (GitHub Issue #122). Those copies are src/audio's files with every use of the
 * GBP_APLAY_AHEAD macro replaced by this runtime value; src/ itself is not changed before §V28's freeze.
 */
#ifndef OPENGBP_TEST_V28_AHEAD_H
#define OPENGBP_TEST_V28_AHEAD_H
#include <stdint.h>
extern uint32_t gbp_v28_ahead;          /* READY chunks kept ahead of the DMA, in force now */
#endif
