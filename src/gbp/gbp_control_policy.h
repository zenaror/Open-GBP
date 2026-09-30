/*
 * gbp_control_policy -- what "CONTROL still reads what this runtime wrote" means (Issue #145, Phase 7's E2;
 * docs/research/PHASE7_ENTRY.md, section 3.3 item 1 and its Issue #144 amendment).
 *
 * THE RULE. The runtime's guards and its restore read-back compare the CONTROL byte the device reports with the
 * byte the runtime expects. The comparison ignores exactly ONE bit, 0x01, and is fully strict on the other seven.
 *
 * WHY THAT BIT. With GB/GBC media in the slot the device sets CONTROL bit 0x01 by itself a few hundred
 * microseconds after the runtime's transform write and holds it to the end of the run (GBP-HW-275, FACT, four runs,
 * three cartridges): a bit the runtime never wrote. Before this policy every guard read that as "CONTROL changed
 * under us" and aborted the session at PREUNMASK (GBP-HW-276), so no GB/GBC frame was ever captured. The two
 * references never had the check at all (GBP-CTL-002, GBP-CTL-003, FACT for the code); opening ours by one bit is
 * the smallest change that lets a GB/GBC session proceed. It is a policy of THIS project, not a claim about the
 * bit's meaning: U-GBP-036 (why it arrives late) stays open, and DMG versus CGB is not distinguished by it.
 *
 * IT IS SYMMETRIC: the comparison ignores the bit in either direction (a device that sets it, or clears it where the runtime
 * had written it). Real GB/GBC runs have it clear in the expected byte and set in the read one; nothing exercised the other.
 *
 * WHAT IT IS NOT. It is not a mode branch: nothing branches on bit 0x01, it is only tolerated and logged (the
 * CONTROLTOL record). It writes nothing: no new CONTROL write exists, and the GBI's forced bit 0x80 is not copied.
 * The two-reading consistency check (majority vote against byte 0x1F) stays strict on every bit.
 *
 * To widen the tolerance is a decision, never an edit of this constant alone: every test that names the seven strict
 * bits fails when it changes (tests/unit/test_gbp_control_policy.c).
 */
#ifndef OPENGBP_GBP_CONTROL_POLICY_H
#define OPENGBP_GBP_CONTROL_POLICY_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define GBP_CONTROL_TOLERATED_MASK 0x01u

/* 1 if the byte read agrees with the byte expected on every bit the policy does not tolerate. */
static inline int gbp_control_agrees(uint8_t read, uint8_t expected)
{
    return (uint8_t)((uint8_t)(read ^ expected) & (uint8_t)~GBP_CONTROL_TOLERATED_MASK) == 0u;
}

/* 1 if the two bytes differ ONLY in the tolerated bit: the case the policy exists for, and the case that is logged. */
static inline int gbp_control_tolerance_exercised(uint8_t read, uint8_t expected)
{
    return gbp_control_agrees(read, expected) && (uint8_t)((uint8_t)(read ^ expected) & (uint8_t)GBP_CONTROL_TOLERATED_MASK) != 0u;
}

#ifdef __cplusplus
}
#endif

#endif
